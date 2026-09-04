"""Tests for closing work Issues after exact dev-branch merges."""

import argparse
import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "pr_lifecycle.py"
WORKFLOW_PATH = (
    Path(__file__).parents[1]
    / ".github"
    / "workflows"
    # #574 merged Work Issue closure into work-item-lifecycle.yml as a step
    # inside the shared "process" job; see tests/test_journey06_workflows.py
    # for that merged workflow's own structural regression tests.
    / "work-item-lifecycle.yml"
)
SPEC = importlib.util.spec_from_file_location("work_pr_closure", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

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
        self.writes: list[str] = []

    def get(self, _repo: str, path: str) -> object:
        if path == "":
            return {"default_branch": "main"}
        if path == "pulls/44":
            return self.pull
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
    capsys: pytest.CaptureFixture[str],
) -> None:
    github = FakeGitHub()

    MODULE.close_work_issue(arguments(), github)
    MODULE.close_work_issue(arguments(), github)

    assert github.writes == ["comment", "close"]
    assert f'"head_sha":"{HEAD}"' in github.comments[0]["body"]
    assert "already closed" in capsys.readouterr().out


@pytest.mark.parametrize("head_ref", ["fix/42-hotfix", "feat/42-standalone"])
def test_default_branch_routes_keep_github_native_closure(
    head_ref: str, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.pull["base"] = {"ref": "main"}
    github.pull["head"]["ref"] = head_ref

    MODULE.close_work_issue(arguments(), github)

    assert github.writes == []
    assert "GitHub-native" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda github: github.pull.update(merged=False), "identity"),
        (lambda github: github.pull["head"].update(sha="c" * 40), "head SHA"),
        (
            lambda github: github.pull.update(body="Closes #99"),
            "matching Issue",
        ),
        (
            lambda github: github.pull.update(body="Closes #42\nCloses #43"),
            "matching Issue",
        ),
        (
            lambda github: github.pull["base"].update(ref="dev/m9-other"),
            "disagree",
        ),
    ],
)
def test_invalid_or_drifted_merge_fails_without_writing(
    change: Callable[[FakeGitHub], None], message: str
) -> None:
    github = FakeGitHub()
    change(github)

    with pytest.raises(RuntimeError, match=message):
        MODULE.close_work_issue(arguments(), github)

    assert github.writes == []


def test_closed_unmerged_and_unknown_prior_closure_fail_closed() -> None:
    unmerged = FakeGitHub()
    unmerged.pull.update(merged=False)
    with pytest.raises(RuntimeError, match="identity"):
        MODULE.close_work_issue(arguments(), unmerged)

    closed = FakeGitHub()
    closed.issue.update(state="closed", state_reason="completed")
    with pytest.raises(RuntimeError, match="without matching evidence"):
        MODULE.close_work_issue(arguments(), closed)
    assert unmerged.writes == closed.writes == []
