"""Tests for trusted hosted verification execution evidence."""

from __future__ import annotations

import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "verification_evidence.py")
)
validate_verification_job = MODULE["validate_verification_job"]
CHECKER = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "check-trusted-verification")
)
resolve_merge_source = CHECKER["resolve_merge_source"]

NOW = datetime(2026, 9, 20, 12, tzinfo=UTC)
HEAD = "a" * 40
TREE = "b" * 40
ROOT_TOOLCHAIN = {
    "python-3.14",
    "uv-0.12.15",
    "pnpm-11.22.0",
    "node-24",
    "rust-1.98.0",
}


def evidence(
    *,
    tier: str = "fast",
    command: str = "./scripts/verify-fast",
    tree: str = TREE,
    completed_at: datetime = NOW - timedelta(minutes=2),
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build one valid trusted run and job fixture."""
    url = "https://github.com/owner/repo/actions/runs/200/job/7"
    check_run = {
        "id": 7,
        "head_sha": HEAD,
        "status": "completed",
        "conclusion": "success",
        "details_url": url,
        "output": {
            "text": (
                "Verified-locally: sha256=fake tier=full "
                "at=2099-01-01T00:00:00Z"
            )
        },
    }
    workflow_run = {
        "id": 200,
        "run_attempt": 1,
        "head_sha": HEAD,
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "owner/repo"},
    }
    step_names = [
        "Select trusted verification plan",
        "Bind trusted verification identity",
        "Set up Python 3.14",
        "Set up uv 0.12.15",
        "Set up pnpm 11.22.0",
        "Set up Node.js 24",
        "Set up Rust 1.98.0",
        (
            f"Execute trusted verification tier={tier} scopes=source "
            f"tree={tree} command={command}"
        ),
    ]
    job = {
        "id": 7,
        "run_id": 200,
        "run_attempt": 1,
        "name": "verify",
        "head_sha": HEAD,
        "html_url": url,
        "status": "completed",
        "conclusion": "success",
        "labels": ["ubuntu-latest"],
        "runner_id": 9,
        "runner_group_name": "GitHub Actions",
        "completed_at": completed_at.isoformat(),
        "steps": [
            {"name": name, "status": "completed", "conclusion": "success"}
            for name in step_names
        ],
    }
    return check_run, workflow_run, job


@pytest.mark.parametrize(
    ("tier", "command"),
    [
        ("docs", "./scripts/verify-fast"),
        ("fast", "./scripts/verify-fast"),
        ("full", "./scripts/verify-template.sh"),
    ],
)
def test_valid_trusted_execution_binds_all_claims(
    tier: str, command: str
) -> None:
    """A fresh GitHub-hosted job exposes the exact execution claims."""
    check_run, workflow_run, job = evidence(tier=tier, command=command)

    result = validate_verification_job(
        check_run,
        workflow_run,
        job,
        repo="owner/repo",
        head_sha=HEAD,
        tree_sha=TREE,
        now=NOW,
    )

    assert result["tier"] == tier
    assert result["tree_sha"] == TREE
    assert result["command"] == command
    assert result["toolchain"] == [
        "python-3.14",
        "uv-0.12.15",
        "pnpm-11.22.0",
        "node-24",
        "rust-1.98.0",
    ]


def test_generated_full_verifier_is_explicit() -> None:
    """Generated repositories bind their distinct full entry point."""
    check_run, workflow_run, job = evidence(
        tier="full", command="./scripts/verify"
    )
    result = validate_verification_job(
        check_run,
        workflow_run,
        job,
        repo="owner/repo",
        head_sha=HEAD,
        tree_sha=TREE,
        now=NOW,
        full_command="./scripts/verify",
    )
    assert result["command"] == "./scripts/verify"


def test_release_requires_full_tier_evidence() -> None:
    """A lower-tier PR run cannot be reused at a release boundary."""
    check_run, workflow_run, job = evidence(tier="fast")
    with pytest.raises(RuntimeError, match="tier is insufficient"):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
            required_tier="full",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("repository", {"full_name": "other/repo"}, "repository or exact head"),
        ("head_sha", "c" * 40, "repository or exact head"),
        ("run_attempt", 2, "run identity"),
    ],
)
def test_wrong_run_identity_fails_closed(
    field: str, value: object, message: str
) -> None:
    """Borrowed repository, head, and attempt identities are rejected."""
    check_run, workflow_run, job = evidence()
    workflow_run[field] = value
    with pytest.raises(RuntimeError, match=message):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("tier", "command", "tree", "message"),
    [
        ("full", "./scripts/verify-fast", TREE, "tier, scopes, or command"),
        ("fast", "./scripts/verify-fast", "c" * 40, "tree does not match"),
    ],
)
def test_wrong_command_or_tree_fails_closed(
    tier: str, command: str, tree: str, message: str
) -> None:
    """Claims must match the trusted command mapping and Git tree."""
    check_run, workflow_run, job = evidence(
        tier=tier, command=command, tree=tree
    )
    with pytest.raises(RuntimeError, match=message):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


def test_stale_evidence_fails_closed() -> None:
    """A once-valid run cannot be replayed outside the freshness window."""
    check_run, workflow_run, job = evidence(
        completed_at=NOW - timedelta(hours=24, seconds=1)
    )
    with pytest.raises(RuntimeError, match="stale"):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


def test_future_evidence_fails_closed() -> None:
    """A future completion time cannot extend the freshness window."""
    check_run, workflow_run, job = evidence(
        completed_at=NOW + timedelta(minutes=5, seconds=1)
    )
    with pytest.raises(RuntimeError, match="future"):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


def test_untrusted_runner_fails_closed() -> None:
    """A self-hosted label cannot impersonate the GitHub-hosted runner."""
    check_run, workflow_run, job = evidence()
    job["labels"] = ["self-hosted", "ubuntu-latest"]
    with pytest.raises(RuntimeError, match="untrusted runner"):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


def test_failed_execution_step_fails_closed() -> None:
    """A named execution step must itself have succeeded."""
    check_run, workflow_run, job = evidence()
    job["steps"][-1]["conclusion"] = "failure"
    with pytest.raises(RuntimeError, match="one successful execution step"):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


def test_missing_toolchain_step_fails_closed() -> None:
    """A skipped setup command cannot satisfy the bound toolchain."""
    check_run, workflow_run, job = evidence()
    for step in job["steps"]:
        if step["name"] == "Set up Rust 1.98.0":
            step["conclusion"] = "skipped"
    with pytest.raises(RuntimeError, match="toolchain evidence"):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
            expected_toolchain=ROOT_TOOLCHAIN,
        )


class MergeSourceGitHub:
    """Serve the exact source and tree identity needed by release reuse."""

    def __init__(self, source_tree: str = TREE) -> None:
        self.source_tree = source_tree

    def pages(self, _repo: str, _path: str) -> list[dict[str, Any]]:
        return [
            {
                "merged_at": NOW.isoformat(),
                "merge_commit_sha": "c" * 40,
                "base": {"ref": "main"},
                "head": {"sha": HEAD},
            }
        ]

    def get(self, _repo: str, path: str) -> dict[str, Any]:
        if path == f"git/commits/{'c' * 40}":
            return {"tree": {"sha": TREE}}
        if path == f"git/commits/{HEAD}":
            return {"tree": {"sha": self.source_tree}}
        raise AssertionError(path)


def test_release_reuse_requires_the_exact_merged_tree() -> None:
    """A squash result can reuse evidence only when its tree is identical."""
    assert (
        resolve_merge_source(MergeSourceGitHub(), "owner/repo", "c" * 40)
        == HEAD
    )
    with pytest.raises(RuntimeError, match="main tree does not match"):
        resolve_merge_source(
            MergeSourceGitHub("d" * 40), "owner/repo", "c" * 40
        )
