#!/usr/bin/env python3
"""Verify the required usage trace for an Alpha/Beta bypass-merge (Issue #607).

Issue #607 requires every pull request actually merged with the Ruleset
self-approval bypass (`#580`, `docs/ci-policy.md` "Alpha 自我核准 bypass")
during `release_phase` "alpha" or "beta" to leave a structured trace
comment on that same PR before merging: `stage`, `actor`, and `reason`.

This module is the "at least one concrete, testable mechanism" Issue #607
asks for, alongside the documented format in `docs/ci-policy.md`: it
parses PR comments for a `bypass-trace:` line and reports whether one was
left, before the PR's merge time. Detecting *which* PRs actually used the
bypass automatically (by cross-referencing GitHub's observed review /
required-check state at merge time, the way
`scripts/generate_audit_trail.py` does for its own, differently-scoped
`governance_stage` classification -- see that module's docstring for the
naming-collision warning this repository already tracks) is intentionally
out of scope here: `generate_audit_trail.py` is not present on this
branch (Issue #535/#564, unmerged Milestone 13 work) and folding a
standalone governance-security fix into that unrelated, larger module
would be scope creep. This tool instead audits one identified PR at a
time -- the operator runs it right after (or as part of) an admin-bypass
merge, the same way `scripts/check-pr-policy-status` is run deliberately
per PR rather than on a schedule.

Required trace comment format (one line, anywhere in a PR comment body):

    bypass-trace: release_phase=<alpha|beta> actor=<login> reason=<text>

`scripts/check-bypass-trace` is the CLI entry point over this module.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from typing import Any

JsonObject = dict[str, Any]

TRACE_PATTERN = re.compile(
    r"^bypass-trace:\s*release_phase=(?P<phase>alpha|beta)\s+"
    r"actor=(?P<actor>\S+)\s+reason=(?P<reason>.+)$",
    re.MULTILINE,
)


def parse_trace(body: str) -> JsonObject | None:
    """Extract the first well-formed `bypass-trace:` line from a comment."""
    match = TRACE_PATTERN.search(body)
    if match is None:
        return None
    return {
        "release_phase": match.group("phase"),
        "actor": match.group("actor"),
        "reason": match.group("reason").strip(),
    }


def _parse_timestamp(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def find_bypass_trace(
    comments: list[JsonObject], merged_at: str | None
) -> JsonObject | None:
    """Return the trace recorded before `merged_at`, or None if missing.

    `comments` mirrors `gh pr view --json comments`: each entry has
    `body`, `createdAt`, and `author.login`. When `merged_at` is None (the
    PR is not merged yet), any well-formed trace comment counts. When a
    PR is merged, a trace comment posted *after* the merge does not
    satisfy the requirement -- the trace must exist before the bypass
    merge happens, not be backfilled afterward.
    """
    merged_at_dt = _parse_timestamp(merged_at) if merged_at else None
    candidates: list[JsonObject] = []
    for comment in comments:
        parsed = parse_trace(comment.get("body", ""))
        if parsed is None:
            continue
        created_at = comment.get("createdAt")
        posted_after_merge = (
            merged_at_dt is not None
            and created_at
            and _parse_timestamp(created_at) > merged_at_dt
        )
        if posted_after_merge:
            continue
        author = comment.get("author") or {}
        candidates.append(
            {
                **parsed,
                "created_at": created_at,
                "commenter": author.get("login", ""),
            }
        )
    if not candidates:
        return None
    # The most recent qualifying trace wins, in case more than one was left.
    candidates.sort(key=lambda item: item.get("created_at") or "")
    return candidates[-1]


def _fetch_pr(repo: str, pr_number: int) -> JsonObject:
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repo,
            "--json",
            "state,mergedAt,comments",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not read pull request #{pr_number} in {repo}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return json.loads(result.stdout)


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr_number", type=int)
    parser.add_argument("--repo", required=True, help="owner/repo")
    args = parser.parse_args(argv)

    try:
        pr = _fetch_pr(args.repo, args.pr_number)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)  # noqa: T201
        return 1

    if pr.get("state") != "MERGED":
        print(  # noqa: T201
            f"PR #{args.pr_number} in {args.repo} is not merged; "
            "nothing to audit yet."
        )
        return 0

    trace = find_bypass_trace(pr.get("comments", []), pr.get("mergedAt"))
    if trace is None:
        print(  # noqa: T201
            f"PR #{args.pr_number} in {args.repo} is merged but has no "
            "bypass-trace comment before its merge time. Required "
            "format: 'bypass-trace: release_phase=<alpha|beta> "
            "actor=<login> reason=<text>' (Issue #607).",
            file=sys.stderr,
        )
        return 1

    print(  # noqa: T201
        f"PR #{args.pr_number} in {args.repo}: bypass-trace found "
        f"(release_phase={trace['release_phase']}, "
        f"actor={trace['actor']}, reason={trace['reason']!r}, "
        f"left by @{trace['commenter']} at {trace['created_at']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
