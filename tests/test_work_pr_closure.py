"""Tests for closing work Issues after exact dev-branch merges."""

import argparse
import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from test_generated_runtime_boundary import minimal_render

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "pr_lifecycle.py"
# Issue #1294: the generated copy runs close-work in every verification
# mode, with or without the hosted sibling that only hosted renders keep.
RENDERS = {
    "generated-hosted": ("hosted", ("pr_lifecycle_hosted.py",)),
    "generated-local": ("local", ()),
    "generated-self-hosted": ("self-hosted", ()),
}
WORKFLOW_PATH = (
    Path(__file__).parents[1]
    / ".github"
    / "workflows"
    # #574 merged Work Issue closure into work-item-lifecycle.yml as a step
    # inside the shared "process" job; see tests/test_journey06_workflows.py
    # for that merged workflow's own structural regression tests.
    / "work-item-lifecycle.yml"
)


def load(name: str, path: Path) -> ModuleType:
    """Load one lifecycle module from its file."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT_MODULE = load("work_pr_closure", MODULE_PATH)


def rendered(tmp_path: Path, name: str) -> ModuleType:
    """Load the generated module from one mode's rendered script set."""
    mode, keep = RENDERS[name]
    project = minimal_render(tmp_path, *keep)
    (project / ".csarc" / "config.yml").write_text(
        f"languages: []\nverification_mode: {mode}\n", encoding="utf-8"
    )
    scripts = project / ".csarc" / "scripts"
    assert (scripts / "pr_lifecycle_hosted.py").exists() == bool(keep)
    return load(f"work_pr_closure_{mode}", scripts / "pr_lifecycle.py")


@pytest.fixture(params=["root", *sorted(RENDERS)])
def lifecycle(request: pytest.FixtureRequest, tmp_path: Path) -> ModuleType:
    """Return the root module or one mode's generated copy."""
    if request.param == "root":
        return ROOT_MODULE
    return rendered(tmp_path, request.param)


HEAD = "a" * 40
MERGE = "b" * 40


class FakeGitHub:
    """Keep one complete remote snapshot and record lifecycle writes."""

    def __init__(self) -> None:
        self.pull: dict[str, Any] = {
            "number": 44,
            "state": "closed",
            "merged": True,
            "merged_at": "2026-09-01T00:00:00Z",
            "merge_commit_sha": MERGE,
            "body": "Closes #42",
            "head": {
                "ref": "fix/42-complete-work",
                "sha": HEAD,
                "repo": {"full_name": "owner/repo"},
            },
            "base": {"ref": "dev/m8-docs"},
            "milestone": {"number": 8},
        }
        self.issue: dict[str, Any] = {
            "number": 42,
            "state": "open",
            "state_reason": None,
            "milestone": {"number": 8},
        }
        self.comments: list[dict[str, Any]] = []
        self.others: dict[str, dict[str, Any]] = {}
        self.writes: list[str] = []

    def get(self, _repo: str, path: str) -> object:
        if path == "":
            return {"default_branch": "main"}
        if path == "pulls/44":
            return self.pull
        if path in self.others:
            return self.others[path]
        if path == "issues/42":
            return self.issue
        raise AssertionError(path)

    def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
        assert path == "issues/42/comments"
        return self.comments

    def comment(self, _repo: str, number: int, body: str) -> dict[str, Any]:
        assert number == 42
        self.writes.append("comment")
        comment = {"body": body}
        self.comments.append(comment)
        return comment

    def close_issue(self, _repo: str, number: int) -> dict[str, Any]:
        assert number == 42
        self.writes.append("close")
        self.issue.update(state="closed", state_reason="completed")
        return self.issue


def arguments() -> argparse.Namespace:
    return argparse.Namespace(repo="owner/repo", pr_number=44, head_sha=HEAD)


def test_closed_event_checks_out_the_merge_commit() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "ref: ${{ github.event.pull_request.merge_commit_sha }}" in workflow
    assert "ref: ${{ github.event.pull_request.base.sha }}" not in workflow


def test_exact_merged_work_pr_closes_once_and_can_rerun(
    lifecycle: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()

    lifecycle.close_work_issue(arguments(), github)
    lifecycle.close_work_issue(arguments(), github)

    assert github.writes == ["comment", "close"]
    assert f'"head_sha":"{HEAD}"' in github.comments[0]["body"]
    assert "already closed" in capsys.readouterr().out


@pytest.mark.parametrize("head_ref", ["fix/42-hotfix", "feat/42-standalone"])
def test_default_branch_routes_keep_github_native_closure(
    lifecycle: ModuleType, head_ref: str, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.pull["base"] = {"ref": "main"}
    github.pull["head"]["ref"] = head_ref

    lifecycle.close_work_issue(arguments(), github)

    assert github.writes == []
    assert "GitHub-native" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda github: github.pull.update(merged=False), "identity"),
        (lambda github: github.pull["head"].update(sha="c" * 40), "or head"),
        (
            lambda github: github.pull.update(body="Closes #99"),
            "does not close its Issue",
        ),
        (
            lambda github: github.pull.update(body="Closes #42\nCloses #43"),
            "does not close its Issue",
        ),
        (
            lambda github: github.pull["base"].update(ref="dev/m9-other"),
            "disagrees",
        ),
    ],
)
def test_invalid_or_drifted_merge_fails_without_writing(
    lifecycle: ModuleType, change: Callable[[FakeGitHub], None], message: str
) -> None:
    github = FakeGitHub()
    change(github)

    with pytest.raises(RuntimeError, match=message):
        lifecycle.close_work_issue(arguments(), github)

    assert github.writes == []


def test_closed_unmerged_and_unknown_prior_closure_fail_closed(
    lifecycle: ModuleType,
) -> None:
    unmerged = FakeGitHub()
    unmerged.pull.update(merged=False)
    with pytest.raises(RuntimeError, match="identity"):
        lifecycle.close_work_issue(arguments(), unmerged)

    closed = FakeGitHub()
    closed.issue.update(state="closed", state_reason="completed")
    with pytest.raises(RuntimeError, match="without matching evidence"):
        lifecycle.close_work_issue(arguments(), closed)
    assert unmerged.writes == closed.writes == []


def earlier_pr(
    lifecycle: ModuleType, github: FakeGitHub, drift: dict[str, Any]
) -> None:
    """Record PR #43 as an earlier merged closure of Issue #42."""
    prior = {**github.pull, "number": 43, "merged_at": "2026-08-31T00:00:00Z"}
    prior.update(head={**github.pull["head"], "sha": "c" * 40})
    prior.update(merge_commit_sha="d" * 40)
    binding = {
        "base_ref": "dev/m8-docs",
        "head_sha": "c" * 40,
        "issue": 42,
        "merge_commit_sha": "d" * 40,
        "pull_request": 43,
        "repository": "owner/repo",
        "schema_version": 1,
    }
    binding.update(drift.get("binding", {}))
    prior.update({k: v for k, v in drift.items() if k != "binding"})
    github.others["pulls/43"] = prior
    message = lifecycle.work_closure_message(binding)
    github.comments.append({"body": message})


def test_reopened_issue_closes_with_the_later_merged_pr(
    lifecycle: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """Issue #1335: sequential PRs for one Issue close it with the last."""
    github = FakeGitHub()
    earlier_pr(lifecycle, github, {})

    lifecycle.close_work_issue(arguments(), github)
    lifecycle.close_work_issue(arguments(), github)

    assert github.writes == ["comment", "close"]
    assert '"pull_request":44' in github.comments[-1]["body"]
    assert "already closed" in capsys.readouterr().out
    replay = argparse.Namespace(
        repo="owner/repo", pr_number=43, head_sha="c" * 40
    )
    github.pull = github.others["pulls/43"]
    with pytest.raises(RuntimeError, match="conflicting closure evidence"):
        lifecycle.close_work_issue(replay, github)


@pytest.mark.parametrize(
    "drift",
    [
        {"merged": False},
        {"merged_at": "2026-09-02T00:00:00Z"},
        {"merge_commit_sha": "e" * 40},
        {"binding": {"issue": 41}},
        {"binding": {"base_ref": "dev/m9-other"}},
        {"binding": {"pull_request": 44}},
        {"binding": {"head_sha": "e" * 40}},
    ],
)
def test_conflicting_earlier_evidence_still_fails_closed(
    lifecycle: ModuleType, drift: dict[str, Any]
) -> None:
    """Only an earlier merged PR for the same Issue and route is accepted."""
    github = FakeGitHub()
    earlier_pr(lifecycle, github, drift)

    with pytest.raises(RuntimeError, match="conflicting closure evidence"):
        lifecycle.close_work_issue(arguments(), github)

    assert github.writes == []
