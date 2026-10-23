"""Hosted-only command line of `authenticate_dependabot_head.py` (#1177)."""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    library = importlib.import_module("authenticate_dependabot_head")
else:
    library = importlib.import_module(
        f"{__package__}.authenticate_dependabot_head"
    )

DEPENDABOT_HEAD_PREFIX = library.DEPENDABOT_HEAD_PREFIX
DEPENDABOT_LOGIN = library.DEPENDABOT_LOGIN
DEPENDABOT_SYNC_BASE = library.DEPENDABOT_SYNC_BASE
authenticated_dependabot_head = library.authenticated_dependabot_head
dependabot_sync_eligibility = library.dependabot_sync_eligibility
trusted_sync_child_candidate = library.trusted_sync_child_candidate
validated_dependabot_snapshot = library.validated_dependabot_snapshot

# Issue #1087: stable reason codes for the exact-merge candidate lookup. A
# zero-match lookup is ordinary "no work" and must not fail the workflow; many
# matches, incomplete identity, or contradictory state fail closed instead.
MERGE_CANDIDATE_MATCH = "merge"
MERGE_CANDIDATE_NO_OP = "no-op"
MERGE_CANDIDATE_REJECTED = "fail-closed"
NO_OP_NO_OPEN_EXACT_MATCH = "no-open-exact-dependabot-pull-request"
NO_OP_EVENT_OUTSIDE_IDENTITY = "event-outside-dependabot-identity"
_SHA = re.compile(r"[0-9a-f]{40}")


class MergeCandidateError(ValueError):
    """Raised when the candidate lookup cannot choose safely (fail closed)."""


def _nested(record: dict[str, Any], *keys: str) -> object:
    """Return a nested value, or None when any level is absent or not a map."""
    value: object = record
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _pull_request_records(value: object) -> list[object]:
    """Flatten one `gh api --paginate --slurp` result into PR records."""
    if not isinstance(value, list):
        raise MergeCandidateError("associated pull requests are not a list")
    if all(isinstance(page, list) for page in value):
        return [item for page in value for item in page]
    if all(isinstance(item, dict) for item in value):
        return list(value)
    raise MergeCandidateError("associated pull request pages are malformed")


def resolve_merge_candidate(  # noqa: C901
    pulls: object,
    base_repo: str,
    head_sha: str,
    head_repository: str,
    head_branch: str,
) -> tuple[str, int | None, str]:
    """Choose the single exact open Dependabot PR for a completed run."""
    if _SHA.fullmatch(head_sha or "") is None:
        raise MergeCandidateError("workflow event head SHA is invalid")
    if not base_repo:
        raise MergeCandidateError("base repository is missing")
    if head_repository != base_repo or not head_branch.startswith(
        DEPENDABOT_HEAD_PREFIX
    ):
        return MERGE_CANDIDATE_NO_OP, None, NO_OP_EVENT_OUTSIDE_IDENTITY

    expected: dict[tuple[str, ...], object] = {
        ("head", "sha"): head_sha,
        ("head", "ref"): head_branch,
        ("head", "repo", "full_name"): base_repo,
        ("base", "ref"): DEPENDABOT_SYNC_BASE,
        ("base", "repo", "full_name"): base_repo,
        ("user", "login"): DEPENDABOT_LOGIN,
        ("user", "type"): "Bot",
    }
    matches: dict[int, dict[str, Any]] = {}
    for record in _pull_request_records(pulls):
        if not isinstance(record, dict):
            raise MergeCandidateError("associated pull request is malformed")
        state = record.get("state")
        if not isinstance(state, str):
            raise MergeCandidateError("associated pull request has no state")
        if state != "open":
            # Closed and merged pull requests are never a substitute.
            continue
        values = {path: _nested(record, *path) for path in expected}
        if any(
            value is not None and value != expected[path]
            for path, value in values.items()
        ):
            # A present coordinate rules this record out of the identity.
            continue
        number = record.get("number")
        if any(value is None for value in values.values()) or not (
            isinstance(number, int) and not isinstance(number, bool)
        ):
            raise MergeCandidateError(
                "an open associated pull request has incomplete identity"
            )
        if (
            record.get("merged") is True
            or record.get("merged_at") is not None
            or record.get("closed_at") is not None
        ):
            raise MergeCandidateError(
                f"pull request #{number} is open but reports a closed state"
            )
        previous = matches.get(number)
        if previous is not None and previous != record:
            raise MergeCandidateError(
                f"pull request #{number} appears with conflicting snapshots"
            )
        matches[number] = record

    if not matches:
        return MERGE_CANDIDATE_NO_OP, None, NO_OP_NO_OPEN_EXACT_MATCH
    if len(matches) > 1:
        numbers = ", ".join(f"#{number}" for number in sorted(matches))
        raise MergeCandidateError(
            f"several open pull requests match the exact head: {numbers}"
        )
    (number,) = matches
    return MERGE_CANDIDATE_MATCH, number, f"exact open pull request #{number}"


def resolve_main(argv: list[str]) -> int:
    """Resolve the exact merge candidate and write GitHub Actions outputs."""
    parser = argparse.ArgumentParser(
        prog="authenticate_dependabot_head.py resolve-merge-candidate",
        description="Resolve the exact open Dependabot PR.",
    )
    parser.add_argument("--base-repo", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--head-repository", required=True)
    parser.add_argument("--head-branch", required=True)
    parser.add_argument(
        "--pulls-json",
        required=True,
        help="Output of gh api --paginate --slurp .../commits/SHA/pulls.",
    )
    parser.add_argument("--github-output", required=True)
    args = parser.parse_args(argv)
    number: int | None = None
    status = 0
    try:
        with open(args.pulls_json, encoding="utf-8") as handle:
            pulls = json.load(handle)
        outcome, number, reason = resolve_merge_candidate(
            pulls,
            args.base_repo,
            args.head_sha,
            args.head_repository,
            args.head_branch,
        )
    except (OSError, json.JSONDecodeError, MergeCandidateError) as error:
        outcome, reason, status = MERGE_CANDIDATE_REJECTED, str(error), 1
    if outcome == MERGE_CANDIDATE_NO_OP:
        sys.stderr.write(f"::notice::Dependabot exact merge no-op: {reason}\n")
    elif outcome == MERGE_CANDIDATE_REJECTED:
        sys.stderr.write(
            f"::error::Dependabot exact merge failed closed: {reason}\n"
        )
    else:
        sys.stderr.write(reason + "\n")
    matched = outcome == MERGE_CANDIDATE_MATCH
    with open(args.github_output, "a", encoding="utf-8") as handle:
        handle.write(f"outcome={outcome}\n")
        handle.write(f"reason={reason}\n")
        handle.write(f"number={number if matched else ''}\n")
        handle.write(f"head_sha={args.head_sha if matched else ''}\n")
    return status


def _load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    """Print the eligibility reason and write the GitHub Actions output."""
    arguments = sys.argv[1:] if argv is None else argv
    if arguments[:1] == ["resolve-merge-candidate"]:
        return resolve_main(arguments[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-repo", required=True)
    parser.add_argument("--expected-base-sha", required=True)
    parser.add_argument("--pull-request-json", required=True)
    parser.add_argument("--commit-json", required=True)
    parser.add_argument("--comparison-json", required=True)
    parser.add_argument("--parent-commit-json", required=True)
    parser.add_argument("--grandparent-commit-json", required=True)
    parser.add_argument("--grandparent-comparison-json", required=True)
    parser.add_argument(
        "--github-output",
        required=True,
        help="Append eligible=true|false to this file ($GITHUB_OUTPUT).",
    )
    args = parser.parse_args(arguments)
    sync_eligible = False
    sync_child_candidate = False
    snapshot_valid = False
    base_sha = ""
    head_ref = ""
    head_sha = ""
    sync_sha = ""
    dependabot_sha = ""
    try:
        pull_request = _load_json(args.pull_request_json)
        commit = _load_json(args.commit_json)
        comparison = _load_json(args.comparison_json)
        parent_commit = _load_json(args.parent_commit_json)
        grandparent_commit = _load_json(args.grandparent_commit_json)
        grandparent_comparison = _load_json(args.grandparent_comparison_json)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    snapshot_valid, _, base_sha, head_ref, head_sha = (
        validated_dependabot_snapshot(pull_request, args.base_repo)
    )
    eligible, reason = authenticated_dependabot_head(
        pull_request, commit, args.base_repo, args.expected_base_sha
    )
    if eligible:
        sync_eligible, sync_reason = dependabot_sync_eligibility(
            pull_request,
            commit,
            comparison,
            args.base_repo,
            args.expected_base_sha,
        )
        reason = f"{reason}; {sync_reason}"
    else:
        (
            sync_child_candidate,
            child_reason,
            sync_sha,
            dependabot_sha,
        ) = trusted_sync_child_candidate(
            pull_request,
            commit,
            parent_commit,
            grandparent_commit,
            grandparent_comparison,
            args.base_repo,
            args.expected_base_sha,
        )
        reason = f"{reason}; {child_reason}"
    sys.stderr.write(reason + "\n")
    with open(args.github_output, "a", encoding="utf-8") as handle:
        handle.write(
            f"snapshot_valid={'true' if snapshot_valid else 'false'}\n"
        )
        handle.write(f"eligible={'true' if eligible else 'false'}\n")
        handle.write(f"sync_eligible={'true' if sync_eligible else 'false'}\n")
        handle.write(f"base_sha={base_sha}\n")
        handle.write(f"head_ref={head_ref}\n")
        handle.write(f"head_sha={head_sha}\n")
        handle.write(
            "sync_child_candidate="
            f"{'true' if sync_child_candidate else 'false'}\n"
        )
        handle.write(f"sync_sha={sync_sha}\n")
        handle.write(f"dependabot_sha={dependabot_sha}\n")
    return 0
