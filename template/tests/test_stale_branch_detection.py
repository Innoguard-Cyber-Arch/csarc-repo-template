"""Tests for stale delivery-branch detection (Issue #667)."""

from __future__ import annotations

import json
import runpy
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "stale_branch_detection.py")
)
is_protected_branch = MODULE["is_protected_branch"]
find_stale_branch_candidates = MODULE["find_stale_branch_candidates"]
describe_candidates = MODULE["describe_candidates"]
stale_branch_report = MODULE["stale_branch_report"]
StaleBranchCandidate = MODULE["StaleBranchCandidate"]
DEFAULT_STALE_DAYS = MODULE["DEFAULT_STALE_DAYS"]

NOW = datetime(2026, 9, 4, tzinfo=UTC)
FakeGh = Callable[[list[str]], str]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("main", True),
        ("dev/m9-decision-site-adoption", True),
        ("dev/m13-decision-site-adoption", True),
        ("csarc/leases/pr-42", True),
        ("csarc/dev-next-preservation-ledger", True),
        # A `dev/m`-prefixed name that does not match the real Milestone
        # branch shape (`dev/m<N>-<slug>`) must not be swept in by a naive
        # prefix match.
        ("dev/mysql-migration", False),
        ("feat/524-lightweight-render-engine", False),
        ("fix/441-delivery-manual-contract", False),
        ("type/524-lightweight-render-engine", False),
    ],
)
def test_is_protected_branch(name: str, expected: bool) -> None:
    """Only the trunk, Milestone branches, and machine refs are excluded."""
    assert is_protected_branch(name) is expected


def _gh_stub(
    branches: list[dict[str, Any]],
    open_heads: list[dict[str, Any]],
    commit_dates: dict[str, str],
) -> FakeGh:
    """Build a fake `gh` transport for `find_stale_branch_candidates`."""

    def fake_gh(arguments: list[str]) -> str:
        if arguments[:1] == ["api"] and "branches?" in arguments[-1]:
            return json.dumps(branches)
        if arguments[:2] == ["pr", "list"]:
            return json.dumps(open_heads)
        if arguments[:1] == ["api"] and "/commits/" in arguments[-1]:
            sha = arguments[-1].rsplit("/", 1)[-1]
            return json.dumps(
                {"commit": {"committer": {"date": commit_dates[sha]}}}
            )
        raise AssertionError(f"unexpected gh invocation: {arguments}")

    return fake_gh


def test_find_stale_branch_candidates_flags_only_the_true_debris() -> None:
    """Protected, in-progress, and open-PR branches never surface; the one
    branch with no open PR that has genuinely gone idle does."""
    branches = [
        {"name": "main", "commit": {"sha": "a"}},
        {"name": "dev/m9-decision-site-adoption", "commit": {"sha": "b"}},
        {"name": "csarc/leases/pr-42", "commit": {"sha": "c"}},
        {"name": "csarc/dev-next-preservation-ledger", "commit": {"sha": "d"}},
        {"name": "fix/441-delivery-manual-contract", "commit": {"sha": "e"}},
        {"name": "feat/999-in-progress", "commit": {"sha": "f"}},
        {"name": "feat/1000-open-pr", "commit": {"sha": "g"}},
        {"name": "feat/1001-forked-pr", "commit": {"sha": "h"}},
    ]
    commit_dates = {
        "a": "2026-09-04T00:00:00Z",
        "b": "2025-01-01T00:00:00Z",
        "c": "2025-01-01T00:00:00Z",
        "d": "2025-01-01T00:00:00Z",
        "e": "2026-07-01T00:00:00Z",  # 65 days idle -- the true candidate
        "f": "2026-08-30T00:00:00Z",  # 5 days idle -- too fresh
        "g": "2026-01-01T00:00:00Z",  # very old, but has an open same-repo PR
        # A same-named branch in this repo whose only "open PR" is actually
        # a cross-repository (fork) pull request must not be protected by
        # it -- that PR's headRefName lives in the fork, not here.
        "h": "2026-01-01T00:00:00Z",
    }
    open_heads = [
        {"headRefName": "feat/1000-open-pr", "isCrossRepository": False},
        {"headRefName": "feat/1001-forked-pr", "isCrossRepository": True},
    ]
    gh = _gh_stub(branches, open_heads, commit_dates)

    candidates = find_stale_branch_candidates("acme/project", now=NOW, gh=gh)

    names = [candidate.name for candidate in candidates]
    assert set(names) == {
        "fix/441-delivery-manual-contract",
        "feat/1001-forked-pr",
    }
    # Sorted with the longest-idle candidate first: "h" (2026-01-01) is far
    # older than "e" (2026-07-01).
    assert names[0] == "feat/1001-forked-pr"
    fix_candidate = next(
        candidate
        for candidate in candidates
        if candidate.name == "fix/441-delivery-manual-contract"
    )
    assert fix_candidate.last_commit_sha == "e"
    assert fix_candidate.days_idle == 65


def test_find_stale_branch_candidates_reports_none_when_all_are_covered() -> (
    None
):
    """No open-PR-less, unprotected, sufficiently idle branch exists."""
    branches = [
        {"name": "main", "commit": {"sha": "a"}},
        {"name": "feat/1000-open-pr", "commit": {"sha": "g"}},
    ]
    commit_dates = {
        "a": "2026-09-04T00:00:00Z",
        "g": "2026-01-01T00:00:00Z",
    }
    open_heads = [
        {"headRefName": "feat/1000-open-pr", "isCrossRepository": False}
    ]
    gh = _gh_stub(branches, open_heads, commit_dates)

    candidates = find_stale_branch_candidates("acme/project", now=NOW, gh=gh)

    assert candidates == []


def test_find_stale_branch_candidates_respects_custom_threshold() -> None:
    """A caller-supplied threshold changes what counts as idle."""
    branches = [{"name": "feat/2000-almost-stale", "commit": {"sha": "z"}}]
    commit_dates = {"z": "2026-08-20T00:00:00Z"}  # 15 days idle
    gh = _gh_stub(branches, [], commit_dates)

    assert (
        find_stale_branch_candidates(
            "acme/project", now=NOW, gh=gh, threshold_days=30
        )
        == []
    )
    assert [
        candidate.name
        for candidate in find_stale_branch_candidates(
            "acme/project", now=NOW, gh=gh, threshold_days=14
        )
    ] == ["feat/2000-almost-stale"]


def test_describe_candidates_no_candidates() -> None:
    """The empty-review message names the detection rule, not just "none"."""
    message = describe_candidates([], threshold_days=30)
    assert "No stale delivery branch candidates found" in message
    assert "30d" in message


def test_describe_candidates_lists_every_finding() -> None:
    """Each candidate's name and idle age are named for a human to review."""
    candidates = [
        StaleBranchCandidate("fix/441-x", "a" * 40, "2026-07-01T00:00:00Z", 65),
        StaleBranchCandidate("dev/m9-y", "b" * 40, "2026-06-01T00:00:00Z", 95),
    ]
    message = describe_candidates(candidates, threshold_days=30)
    assert "2 stale delivery branch candidate(s)" in message
    assert "fix/441-x (65d idle)" in message
    assert "dev/m9-y (95d idle)" in message
    assert "Not deleted automatically" in message


def test_stale_branch_report_available_serializes_candidates() -> None:
    """A successful detection run reports JSON-friendly candidate dicts."""
    branches = [{"name": "fix/441-x", "commit": {"sha": "e"}}]
    commit_dates = {"e": "2026-07-01T00:00:00Z"}
    gh = _gh_stub(branches, [], commit_dates)

    report = stale_branch_report("acme/project", now=NOW, gh=gh)
    candidates = find_stale_branch_candidates("acme/project", now=NOW, gh=gh)

    assert report["available"] is True
    assert report["reason"] is None
    assert report["threshold_days"] == DEFAULT_STALE_DAYS
    assert report["candidates"] == [
        {
            "name": candidate.name,
            "last_commit_sha": candidate.last_commit_sha,
            "last_commit_date": candidate.last_commit_date,
            "days_idle": candidate.days_idle,
        }
        for candidate in candidates
    ]
    assert "fix/441-x" in report["summary"]


def test_stale_branch_report_degrades_instead_of_raising() -> None:
    """A `gh` transport failure never propagates -- this check is purely
    advisory and must not block Milestone preflight or a release report."""

    def failing_gh(arguments: list[str]) -> str:
        del arguments
        raise RuntimeError("GitHub CLI (gh) is required")

    report = stale_branch_report("acme/project", gh=failing_gh)

    assert report["available"] is False
    assert report["candidates"] == []
    assert "GitHub CLI (gh) is required" in report["reason"]
    assert "Stale delivery branch check unavailable" in report["summary"]
