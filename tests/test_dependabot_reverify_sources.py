"""Reverified Dependabot squashes in clean sync and release (Issue #1284).

A Dependabot merge that #1264 reverified on a newer main has the test-merge
tree, not its head tree. Clean sync and release source resolution accept
that squash only through the reverification bound to its exact tree, its
one parent (the main verified on), and a test merge whose parents are that
main and the unchanged head. Generated projects ship no reverification, so
their checker keeps failing closed exactly as before.
"""

from __future__ import annotations

import importlib
import json
import runpy
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_dependabot_reverify import (
    HEAD,
    MAIN,
    MERGE,
    NUMBER,
    REPO,
    TREE,
    ReverifyGitHub,
    step_name,
)
from test_pr_lifecycle import MODULE
from test_verification_evidence import NOW
from test_verification_evidence import evidence as verify_evidence

ROOT = Path(__file__).resolve().parents[1]
ROOT_CHECKER = ROOT / "scripts/check-trusted-verification"
TEMPLATE_CHECKER = ROOT / "template/.csarc/scripts/check-trusted-verification"
SQUASH = "5" * 40
HEAD_TREE = "4" * 40
NEWER_MAIN = "6" * 40
SYNC_HEAD = "c" * 40
SYNC_TREE = "b" * 40
TOOLCHAIN = [
    "Set up Python 3.14",
    "Set up uv 0.12.15",
    "Set up pnpm 11.22.0",
    "Set up Node.js 24",
    "Set up Rust 1.98.0",
    "Set up Go 1.27.1",
]
ORIGINAL_ERROR = "Merged main tree does not match: source differs. Verify"


class SquashGitHub(ReverifyGitHub):
    """Serve one reverified Dependabot squash on main and its evidence."""

    def __init__(self) -> None:
        super().__init__()
        self.steps = [*TOOLCHAIN, step_name()]
        self.completed_at = (NOW - timedelta(minutes=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.squash_parents = [MAIN]
        self.squash_tree = TREE
        self.merge_parents = [MAIN, HEAD]
        self.merge_tree = TREE
        self.author = "dependabot[bot]"
        self.base_ref = "main"
        self.extra: dict[str, object] = {}
        self.sync_jobs: list[dict[str, Any]] = []

    def collection(
        self, _repo: str, path: str, key: str
    ) -> list[dict[str, Any]]:
        if path.startswith("actions/runs/300/jobs"):
            return self.sync_jobs
        return super().collection(_repo, path, key)

    def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
        if path.startswith(f"commits/{SQUASH}/pulls"):
            return [
                {
                    "number": NUMBER,
                    "merged_at": "2026-09-20T11:30:00Z",
                    "merge_commit_sha": SQUASH,
                    "base": {"ref": self.base_ref},
                    "head": {
                        "sha": HEAD,
                        "ref": f"dependabot/uv/main/routine-{NUMBER}",
                        "repo": {"full_name": REPO},
                    },
                    "user": {"login": self.author, "type": "Bot"},
                }
            ]
        return super().pages(_repo, path)

    def get(self, _repo: str, path: str) -> object:
        commits = {
            SQUASH: (self.squash_tree, self.squash_parents),
            MERGE: (self.merge_tree, self.merge_parents),
            HEAD: (HEAD_TREE, [MAIN[:39] + "0"]),
        }
        for sha, (tree, parents) in commits.items():
            if path == f"git/commits/{sha}":
                return {
                    "tree": {"sha": tree},
                    "parents": [{"sha": item} for item in parents],
                }
        if path in self.extra:
            return self.extra[path]
        return super().get(_repo, path)


def checker(path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Load one checker copy without leaking its directory into imports."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    return runpy.run_path(str(path))


def run_main(
    module: dict[str, Any],
    github: SquashGitHub,
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, Any]:
    """Run the checker CLI against a fake GitHub and return its JSON."""
    monkeypatch.setitem(
        module["main"].__globals__,
        "lifecycle",
        lambda: SimpleNamespace(GitHub=lambda: github),
    )
    monkeypatch.setattr(sys, "argv", ["check-trusted-verification", *argv])
    module["main"]()
    return json.loads(capsys.readouterr().out)


def freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the reverification freshness clock to the fixture time."""
    freshness = importlib.import_module("evidence_freshness")
    original = freshness.require_fresh

    def at_fixture_time(*args: object, **kwargs: object) -> object:
        kwargs["now"] = kwargs.get("now") or NOW
        return original(*args, **kwargs)

    monkeypatch.setattr(freshness, "require_fresh", at_fixture_time)


# --- AC1: clean sync and release accept the exact reverified squash ---------


def test_clean_sync_resolves_the_reverification_of_the_squash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC1: main's squash cites the run that verified its exact tree."""
    module = checker(ROOT_CHECKER, monkeypatch)
    freeze(monkeypatch)

    result = run_main(
        module,
        SquashGitHub(),
        [
            SQUASH,
            "--github-repo",
            REPO,
            "--resolve-merge-source",
            "--required-tier",
            "full",
        ],
        monkeypatch,
        capsys,
    )

    # ci.yml reads these three identities for the clean sync claim.
    assert (result["run_id"], result["job_id"], result["check_run_id"]) == (
        500,
        77,
        77,
    )
    assert result["reused"] is False
    assert result["tree_sha"] == TREE
    assert result["main_sha"] == MAIN
    assert result["merge_sha"] == MERGE
    assert result["tier"] == "full"
    assert result["base"] == "main"


def test_release_source_plans_a_reverified_squash_from_its_own_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1: release planning reads the squash, never the other head tree."""
    module = checker(ROOT_CHECKER, monkeypatch)
    freeze(monkeypatch)

    assert module["resolve_release_source"](SquashGitHub(), REPO, SQUASH) == ""


# --- AC2 / R1: anything but the exact verified tree fails closed -------------


@pytest.mark.parametrize(
    ("change", "message"),
    [
        # The accepted #1264 window: GitHub squashed onto a newer main.
        (
            {"squash_parents": [NEWER_MAIN], "squash_tree": "7" * 40},
            "none on main",
        ),
        ({"squash_tree": "7" * 40}, "was not verified"),
        # The test merge GitHub reports differs from the claimed tree.
        ({"squash_tree": "7" * 40, "merge_tree": "7" * 40}, "not verified"),
        ({"merge_tree": "7" * 40}, "was not verified"),
        ({"merge_parents": [NEWER_MAIN, HEAD]}, "was not verified"),
        ({"merge_parents": [MAIN, "8" * 40]}, "was not verified"),
        ({"squash_parents": [MAIN, HEAD]}, "no Dependabot reverification"),
        ({"author": "maintainer"}, "no Dependabot reverification"),
        ({"conclusion": "failure"}, "did not pass"),
    ],
)
def test_unverified_trees_fail_closed(
    change: dict[str, object],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2: a TOCTOU or other unverified tree never resolves a source."""
    module = checker(ROOT_CHECKER, monkeypatch)
    freeze(monkeypatch)
    github = SquashGitHub()
    for key, value in change.items():
        setattr(github, key, value)

    for resolve in ("resolve_merge_source", "resolve_release_source"):
        with pytest.raises(RuntimeError, match=message):
            module[resolve](github, REPO, SQUASH)


def test_stale_reverification_fails_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R1: the tightened freshness window still applies to the CLI."""
    module = checker(ROOT_CHECKER, monkeypatch)
    freeze(monkeypatch)
    github = SquashGitHub()
    github.completed_at = (NOW - timedelta(hours=3)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    with pytest.raises(RuntimeError, match=r"stale|older|fresh"):
        run_main(
            module,
            github,
            [
                SQUASH,
                "--github-repo",
                REPO,
                "--resolve-merge-source",
                "--max-age-hours",
                "1",
            ],
            monkeypatch,
            capsys,
        )


# --- AC3 / R2: generated projects and delivery branches are unchanged --------


def test_generated_checker_keeps_failing_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3: without the root-only module, the mismatch error is unchanged."""
    assert ROOT_CHECKER.read_bytes() == TEMPLATE_CHECKER.read_bytes()
    assert not (TEMPLATE_CHECKER.parent / "dependabot_reverify.py").exists()
    module = checker(TEMPLATE_CHECKER, monkeypatch)

    for resolve in ("resolve_merge_source", "resolve_release_source"):
        with pytest.raises(RuntimeError, match=ORIGINAL_ERROR):
            module[resolve](SquashGitHub(), REPO, SQUASH)


def test_delivery_branch_merges_keep_the_tree_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3: reverification exists only for main; other branches still fail."""
    module = checker(ROOT_CHECKER, monkeypatch)
    github = SquashGitHub()
    github.base_ref = "dev/m21-self-hosted-verification"

    with pytest.raises(RuntimeError, match="Merged dev/m21-self-hosted"):
        module["resolve_merge_source"](
            github, REPO, SQUASH, "dev/m21-self-hosted-verification"
        )


# --- AC1: the clean sync PR's own merge evidence cites the reverification ----


def sync_verification(
    monkeypatch: pytest.MonkeyPatch, github: SquashGitHub, source: int = 77
) -> dict[str, Any]:
    """Validate a clean sync verify job citing the reverification run."""
    check_run, workflow_run, job = verify_evidence(
        run_id=300,
        check_id=8,
        head=SYNC_HEAD,
        tree=SYNC_TREE,
        sync=(SQUASH, 500, source, source),
    )
    github.extra = {
        f"git/commits/{SYNC_HEAD}": {"tree": {"sha": SYNC_TREE}},
        f"check-runs/{source}": {**github.check(), "id": source},
    }
    github.sync_jobs = [job]
    require = MODULE["require_trusted_verification"]
    monkeypatch.setitem(
        require.__globals__,
        "trusted_required_check_runs",
        lambda *_args: ({("verify", 15368): check_run}, {300: workflow_run}),
    )
    return require(
        github, REPO, SYNC_HEAD, 15368, now=NOW, check_runs=[check_run]
    )


def test_sync_pull_request_evidence_accepts_the_reverification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1: the sync PR merge validates the cited reverification again."""
    result = sync_verification(monkeypatch, SquashGitHub())

    assert result["reused"] is True
    assert result["sync_main_sha"] == SQUASH
    assert result["source_check_run_id"] == 77
    assert result["executor"] == "trusted-base"
    assert result["toolchain"] == [
        "python-3.14",
        "uv-0.12.15",
        "pnpm-11.22.0",
        "node-24",
        "rust-1.98.0",
        "go-1.27.1",
    ]


@pytest.mark.parametrize(
    ("change", "source", "message"),
    [
        ({"squash_parents": [NEWER_MAIN]}, 77, "none on main"),
        ({"squash_tree": "7" * 40}, 77, "was not verified"),
        ({}, 78, "invalid producer"),
    ],
)
def test_sync_pull_request_evidence_fails_closed(
    change: dict[str, object],
    source: int,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2: a sync citing an unbound or other reverification is refused."""
    github = SquashGitHub()
    for key, value in change.items():
        setattr(github, key, value)

    with pytest.raises(RuntimeError, match=message):
        sync_verification(monkeypatch, github, source)


def test_shared_validator_takes_a_reverification_only_for_sync() -> None:
    """R1: a reuse claim can never substitute a pre-validated source."""
    validate = runpy.run_path(str(ROOT / "scripts/verification_evidence.py"))[
        "validate_verification_job"
    ]
    current = verify_evidence(run_id=300, check_id=8, reuse=(500, 77, 77))
    source = ({"id": 77}, {"id": 500}, {"id": 77}, SYNC_TREE)

    with pytest.raises(RuntimeError, match="no direct execution source"):
        validate(
            *current,
            repo="owner/repo",
            head_sha="a" * 40,
            tree_sha=SYNC_TREE,
            now=NOW,
            source_evidence=source,
            source_result={"head_sha": HEAD, "tree_sha": SYNC_TREE},
        )
