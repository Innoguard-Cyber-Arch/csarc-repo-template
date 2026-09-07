#!/usr/bin/env python3
"""Detect remote delivery branches that likely need manual cleanup review.

Issue #667. `delete_branch_on_merge` (`policies/repository.json`) already
deletes a branch's remote copy automatically the instant its pull request
merges -- see `docs/ci-policy.md`'s "合併後自動刪除一般來源 branch" note. The
one case it never reaches is a pull request that is **closed without
merging**: that setting only fires on merge, so the branch behind a
closed-not-merged pull request can sit on the remote indefinitely with no
automatic cleanup and, before this module, no detection at all. This is
exactly how the 9 debris branches found on 2026-09-04 accumulated (see
#667): every one of them corresponded to a closed-but-never-merged pull
request whose actual work had already landed under a different branch name.

This module only detects and reports candidates for a human to review; it
never deletes anything. A branch with no open pull request might simply be
in-progress work nobody has opened a pull request for yet, so automatic
deletion here would be far too risky -- see the Boundary section of #667.

Excluded from detection (never flagged, regardless of age or pull-request
state):
  - the repository's default branch (`main` unless overridden)
  - `dev/m<N>-<slug>` -- Milestone delivery branches (the same shape
    `promotion_gate.py`'s `MILESTONE_BRANCH` already recognizes), which
    follow their own manual-confirmation-and-evidence cleanup path
    documented in `docs/ci-policy.md`
  - `csarc/*` -- machine-managed infrastructure refs, not work branches:
    `csarc/leases/*` (`scripts/pr_lifecycle.py` PR lifecycle leases) and
    `csarc/dev-next-preservation-ledger` (a transaction ledger)

Reused from two call sites (Issue #667's explicit design, not a new
standalone scheduled workflow):
  - `scripts/sync_milestone_state.py preflight` -- a review-candidate list
    surfaced every time Milestone metadata is validated.
  - `scripts/release_policy.py preflight` -- the same list surfaced as
    advisory, non-blocking output alongside the existing release
    capability/integration report; a stale-branch finding never fails a
    release.

Threshold default: 30 days idle with no open pull request. A
closed-without-merge branch is permanently abandoned the moment its pull
request closes, so almost any threshold eventually catches it; the real
risk is the opposite direction -- flagging genuine in-progress work that
simply has not been opened as a pull request yet. This repository routinely
runs many concurrent, long-lived per-Issue branches (one worktree per task)
that can sit quietly for one to a few weeks during review or while blocked
on a dependency without being abandoned. 30 days comfortably clears that
normal pause window while still surfacing real debris within about a month
instead of letting it accumulate for months, as the 9 found branches did.
Override with `threshold_days` (or, from the two CLI wrappers, whatever
flag/argument they choose to expose).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

DEFAULT_STALE_DAYS = 30
DEFAULT_BRANCH = "main"
# Mirrors promotion_gate.py's MILESTONE_BRANCH -- kept as a private literal
# here rather than imported, since pulling in that much heavier module just
# for one regex would be a needless coupling for a read-only detector.
_MILESTONE_BRANCH = re.compile(r"^dev/m[1-9][0-9]*-[a-z0-9][a-z0-9-]*$")

RunGh = Callable[[list[str]], str]


def run_gh(arguments: list[str]) -> str:
    """Run GitHub CLI without a shell (default transport; tests replace it)."""
    executable = shutil.which("gh")
    if executable is None:
        raise RuntimeError("GitHub CLI (gh) is required")
    result = subprocess.run(  # noqa: S603
        [executable, *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _pages(raw: str) -> list[dict[str, Any]]:
    """Flatten a `gh api --paginate --slurp` response."""
    value = json.loads(raw)
    if not isinstance(value, list):
        raise RuntimeError("GitHub returned an invalid collection")
    if value and isinstance(value[0], list):
        value = [item for page in value for item in page]
    if not all(isinstance(item, dict) for item in value):
        raise RuntimeError("GitHub returned an invalid collection item")
    return value


def is_protected_branch(
    name: str, *, default_branch: str = DEFAULT_BRANCH
) -> bool:
    """Return whether one branch name is excluded from stale detection.

    See the module docstring's Excluded section for exactly what each of
    these three exclusions is for.
    """
    return (
        name == default_branch
        or name.startswith("csarc/")
        or _MILESTONE_BRANCH.match(name) is not None
    )


@dataclass(frozen=True)
class StaleBranchCandidate:
    """One remote branch flagged for human review; never auto-deleted."""

    name: str
    last_commit_sha: str
    last_commit_date: str
    days_idle: int


def _open_pull_request_heads(repo: str, gh: RunGh) -> set[str]:
    """Return head branch names of every open, same-repository pull request.

    A cross-repository (fork) pull request's `headRefName` is a branch name
    in the fork, not in this repository, so it is excluded here -- treating
    it as "protecting" a same-named branch in this repository would be
    wrong.
    """
    raw = gh(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--json",
            "headRefName,isCrossRepository",
            "--limit",
            "1000",
        ]
    )
    pulls = json.loads(raw)
    if not isinstance(pulls, list):
        raise RuntimeError("GitHub returned an invalid pull request list")
    return {
        pull["headRefName"]
        for pull in pulls
        if isinstance(pull, dict)
        and pull.get("isCrossRepository") is False
        and isinstance(pull.get("headRefName"), str)
    }


def _remote_branches(repo: str, gh: RunGh) -> list[dict[str, Any]]:
    """Return every remote branch's name and head commit sha."""
    raw = gh(
        ["api", "--paginate", "--slurp", f"repos/{repo}/branches?per_page=100"]
    )
    return _pages(raw)


def find_stale_branch_candidates(
    repo: str,
    *,
    default_branch: str = DEFAULT_BRANCH,
    threshold_days: int = DEFAULT_STALE_DAYS,
    now: datetime | None = None,
    gh: RunGh | None = None,
) -> list[StaleBranchCandidate]:
    """Return remote branches idle past the threshold with no open PR.

    Unprotected only (see `is_protected_branch`). Detection only:
    candidates are review material for a human, never deleted
    automatically. See the module docstring for exactly which branches are
    excluded and why, and for the threshold's reasoning. Sorted with the
    longest-idle candidate first.
    """
    transport = gh or run_gh
    current = (now or datetime.now(UTC)).astimezone(UTC)
    branches = _remote_branches(repo, transport)
    open_heads = _open_pull_request_heads(repo, transport)
    candidates: list[StaleBranchCandidate] = []
    for branch in branches:
        name = branch.get("name")
        sha = (branch.get("commit") or {}).get("sha")
        if not isinstance(name, str) or not isinstance(sha, str):
            continue
        if is_protected_branch(name, default_branch=default_branch):
            continue
        if name in open_heads:
            continue
        commit = json.loads(transport(["api", f"repos/{repo}/commits/{sha}"]))
        committer = (commit.get("commit") or {}).get("committer", {})
        date_text = committer.get("date")
        if not isinstance(date_text, str):
            continue
        commit_date = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        days_idle = (current - commit_date).days
        if days_idle < threshold_days:
            continue
        candidates.append(StaleBranchCandidate(name, sha, date_text, days_idle))
    candidates.sort(key=lambda candidate: candidate.days_idle, reverse=True)
    return candidates


def describe_candidates(
    candidates: list[StaleBranchCandidate],
    *,
    threshold_days: int = DEFAULT_STALE_DAYS,
) -> str:
    """Render one human-readable review-candidate summary line."""
    if not candidates:
        return (
            "No stale delivery branch candidates found "
            f"(no open PR, idle >= {threshold_days}d)."
        )
    listing = ", ".join(
        f"{candidate.name} ({candidate.days_idle}d idle)"
        for candidate in candidates
    )
    return (
        f"{len(candidates)} stale delivery branch candidate(s) for manual "
        f"review (no open PR, idle >= {threshold_days}d): {listing}. Not "
        "deleted automatically -- confirm each is truly abandoned before "
        "removing it."
    )


def stale_branch_report(
    repo: str,
    *,
    default_branch: str = DEFAULT_BRANCH,
    threshold_days: int = DEFAULT_STALE_DAYS,
    now: datetime | None = None,
    gh: RunGh | None = None,
) -> dict[str, Any]:
    """Return a JSON-friendly stale-branch review report; never raises.

    Detection only, and always advisory/non-blocking: any transport
    failure or unexpected GitHub response degrades to an
    `"available": False` report instead of raising, because this check
    must never block Milestone preflight or a release preflight report
    (see the module docstring).
    """
    try:
        candidates = find_stale_branch_candidates(
            repo,
            default_branch=default_branch,
            threshold_days=threshold_days,
            now=now,
            gh=gh,
        )
    except (
        RuntimeError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        return {
            "available": False,
            "reason": str(error),
            "threshold_days": threshold_days,
            "candidates": [],
            "summary": f"Stale delivery branch check unavailable: {error}",
        }
    return {
        "available": True,
        "reason": None,
        "threshold_days": threshold_days,
        "candidates": [asdict(candidate) for candidate in candidates],
        "summary": describe_candidates(
            candidates, threshold_days=threshold_days
        ),
    }


def _cli_main(arguments: list[str] | None = None) -> int:
    """Print the stale-branch review report for one repository, standalone.

    Not wired into any workflow; a convenience for a maintainer running
    this locally, mirroring the pattern of most other `scripts/*.py`
    tools in this repository.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--default-branch", default=DEFAULT_BRANCH)
    parser.add_argument(
        "--threshold-days", type=int, default=DEFAULT_STALE_DAYS
    )
    args = parser.parse_args(arguments)
    report = stale_branch_report(
        args.repo,
        default_branch=args.default_branch,
        threshold_days=args.threshold_days,
    )
    print(report["summary"])  # noqa: T201
    return 0 if report["available"] else 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())
