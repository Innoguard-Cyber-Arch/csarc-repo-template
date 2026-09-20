#!/usr/bin/env python3
"""Authenticate a Dependabot head before privileged template sync (#830).

The pull_request_target workflow runs this file only from the trusted base
revision. Live GitHub API metadata is treated as untrusted until it proves an
exact, same-repository, GitHub-signed Dependabot commit or a deterministic sync
child reconstructed from such a commit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

DEPENDABOT_LOGIN = "dependabot[bot]"
DEPENDABOT_HEAD_PREFIX = "dependabot/"
DEPENDABOT_COMMITTER = "web-flow"
DEPENDABOT_SYNC_BASE = "main"
DEPENDABOT_SYNC_HEAD_PREFIX = "dependabot/github_actions/main/"
DEPENDABOT_SYNC_PATH = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$")
DEPENDABOT_SYNC_COMMIT_MESSAGE = (
    "fix(deps): sync template copies of this dependency bump (#755)"
)
DEPENDABOT_SYNC_COMMIT_IDENTITY = {
    "name": "github-actions[bot]",
    "email": "actions@github.com",
}
GITHUB_COMPARE_FILES_LIMIT = 300
METADATA_ERRORS = (KeyError, TypeError)


def dependabot_coordinates_eligible(
    author: str, head_ref: str, head_repo: str, base_repo: str
) -> tuple[bool, str]:
    """Require Dependabot's exact login, branch namespace, and repository."""
    if author != DEPENDABOT_LOGIN:
        return (
            False,
            f"author {author!r} is not {DEPENDABOT_LOGIN!r}",
        )
    if not head_ref.startswith(DEPENDABOT_HEAD_PREFIX):
        return (
            False,
            f"head ref {head_ref!r} does not match the {author!r} "
            f"prefix {DEPENDABOT_HEAD_PREFIX!r}",
        )
    if not head_repo or head_repo != base_repo:
        return (
            False,
            "head repository is not this repository (a fork cannot be "
            "allowlisted)",
        )
    return (
        True,
        f"{author} on {head_ref!r} in {head_repo!r} has valid coordinates",
    )


def validated_dependabot_snapshot(
    pull_request: dict[str, Any], base_repo: str
) -> tuple[bool, str, str, str, str]:
    """Return exact live coordinates without authorizing the current commit."""
    try:
        state = pull_request["state"]
        author = pull_request["user"]["login"]
        base_ref = pull_request["base"]["ref"]
        base_name = pull_request["base"]["repo"]["full_name"]
        base_sha = pull_request["base"]["sha"]
        head_ref = pull_request["head"]["ref"]
        head_repo = pull_request["head"]["repo"]["full_name"]
        head_sha = pull_request["head"]["sha"]
    except METADATA_ERRORS:
        return False, "pull request metadata is incomplete", "", "", ""

    eligible, reason = dependabot_coordinates_eligible(
        author, head_ref, head_repo, base_repo
    )
    if not eligible:
        return False, reason, "", "", ""
    if state != "open":
        return False, "pull request is not open", "", "", ""
    if base_ref != DEPENDABOT_SYNC_BASE or base_name != base_repo:
        return (
            False,
            "pull request base is not this repository's main",
            "",
            "",
            "",
        )
    if (
        not isinstance(head_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", head_sha) is None
    ):
        return False, "pull request head SHA is invalid", "", "", ""
    if (
        not isinstance(base_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", base_sha) is None
    ):
        return False, "pull request base SHA is invalid", "", "", ""
    return True, reason, base_sha, head_ref, head_sha


def authenticated_dependabot_head(
    pull_request: dict[str, Any],
    commit: dict[str, Any],
    base_repo: str,
    expected_base_sha: str,
) -> tuple[bool, str]:
    """Authenticate the current PR head as a GitHub-signed Dependabot commit."""
    eligible, reason, base_sha, _, head_sha = validated_dependabot_snapshot(
        pull_request, base_repo
    )
    if not eligible:
        return eligible, reason
    if (
        re.fullmatch(r"[0-9a-f]{40}", expected_base_sha) is None
        or base_sha != expected_base_sha
    ):
        return False, "pull request base SHA does not match the workflow event"
    if commit.get("sha") != head_sha:
        return (
            False,
            "commit metadata does not match the current pull request head",
        )
    if (commit.get("author") or {}).get("login") != DEPENDABOT_LOGIN:
        return (
            False,
            "current head author is not the allowlisted pull request bot",
        )
    if (commit.get("committer") or {}).get("login") != DEPENDABOT_COMMITTER:
        return (
            False,
            "current head was not committed by GitHub's trusted signer",
        )
    verification = (commit.get("commit") or {}).get("verification") or {}
    if (
        verification.get("verified") is not True
        or verification.get("reason") != "valid"
    ):
        return False, "current head does not have a valid GitHub signature"
    parents = commit.get("parents")
    if not isinstance(parents, list) or len(parents) != 1:
        return False, "current head is not a single-parent Dependabot update"
    return (
        True,
        f"current head {head_sha} is an authenticated "
        f"{DEPENDABOT_LOGIN} commit",
    )


def dependabot_sync_eligibility(
    pull_request: dict[str, Any],
    commit: dict[str, Any],
    comparison: dict[str, Any],
    base_repo: str,
    expected_base_sha: str,
) -> tuple[bool, str]:
    """Return whether the authenticated head is an exact Actions sync input."""
    eligible, reason = authenticated_dependabot_head(
        pull_request, commit, base_repo, expected_base_sha
    )
    if not eligible:
        return eligible, reason

    head_ref = (pull_request.get("head") or {}).get("ref")
    if not isinstance(head_ref, str) or not head_ref.startswith(
        DEPENDABOT_SYNC_HEAD_PREFIX
    ):
        return False, f"head ref {head_ref!r} is not a GitHub Actions update"
    if comparison.get("ahead_by") != 1:
        return False, "Dependabot sync requires exactly one head commit"

    files = comparison.get("files")
    if not isinstance(files, list) or not files:
        return False, "Dependabot sync requires at least one changed workflow"
    if len(files) >= GITHUB_COMPARE_FILES_LIMIT:
        return False, "changed-file metadata reached GitHub's truncation limit"
    for changed in files:
        if not isinstance(changed, dict):
            return False, "changed-file metadata is malformed"
        path = changed.get("filename")
        if (
            changed.get("status") != "modified"
            or not isinstance(path, str)
            or DEPENDABOT_SYNC_PATH.fullmatch(path) is None
        ):
            return False, f"changed path {path!r} is outside the sync allowlist"
    return True, "authenticated Dependabot Actions head is eligible for sync"


def trusted_sync_child_candidate(  # noqa: C901
    pull_request: dict[str, Any],
    commit: dict[str, Any],
    parent_commit: dict[str, Any],
    parent_comparison: dict[str, Any],
    base_repo: str,
    expected_base_sha: str,
) -> tuple[bool, str, str, str]:
    """Recognize a sync child whose tree still needs trusted reconstruction."""
    eligible, reason, base_sha, head_ref, head_sha = (
        validated_dependabot_snapshot(pull_request, base_repo)
    )
    if not eligible:
        return False, reason, "", ""
    if (
        base_sha != expected_base_sha
        or not head_ref.startswith(DEPENDABOT_SYNC_HEAD_PREFIX)
        or commit.get("sha") != head_sha
    ):
        return False, "sync child coordinates are invalid", "", ""

    parents = commit.get("parents")
    if not isinstance(parents, list) or len(parents) != 1:
        return False, "sync child must have exactly one parent", "", ""
    parent_sha = (parents[0] or {}).get("sha")
    if (
        not isinstance(parent_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", parent_sha) is None
    ):
        return False, "sync child parent SHA is invalid", "", ""

    raw_commit = commit.get("commit") or {}
    if raw_commit.get("message") != DEPENDABOT_SYNC_COMMIT_MESSAGE:
        return False, "sync child commit message is unexpected", "", ""
    for role in ("author", "committer"):
        identity = raw_commit.get(role) or {}
        if any(
            identity.get(field) != expected
            for field, expected in DEPENDABOT_SYNC_COMMIT_IDENTITY.items()
        ):
            return False, f"sync child {role} identity is unexpected", "", ""

    parent_pull_request = {
        **pull_request,
        "head": {**pull_request["head"], "sha": parent_sha},
    }
    parent_eligible, parent_reason = dependabot_sync_eligibility(
        parent_pull_request,
        parent_commit,
        parent_comparison,
        base_repo,
        expected_base_sha,
    )
    if not parent_eligible:
        return (
            False,
            f"sync child parent is not trusted: {parent_reason}",
            "",
            "",
        )

    parent_parents = parent_commit.get("parents")
    if not isinstance(parent_parents, list) or len(parent_parents) != 1:
        return False, "Dependabot parent must have exactly one parent", "", ""
    source_base_sha = (parent_parents[0] or {}).get("sha")
    if (
        not isinstance(source_base_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_base_sha) is None
    ):
        return False, "trusted synchronizer base SHA is invalid", "", ""
    return (
        True,
        "current head is a candidate trusted sync child",
        parent_sha,
        source_base_sha,
    )


def _load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    """Print the eligibility reason and write the GitHub Actions output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-repo", required=True)
    parser.add_argument("--expected-base-sha", required=True)
    parser.add_argument("--pull-request-json", required=True)
    parser.add_argument("--commit-json", required=True)
    parser.add_argument("--comparison-json", required=True)
    parser.add_argument("--parent-commit-json", required=True)
    parser.add_argument("--parent-comparison-json", required=True)
    parser.add_argument(
        "--github-output",
        required=True,
        help="Append eligible=true|false to this file ($GITHUB_OUTPUT).",
    )
    args = parser.parse_args(argv)
    sync_eligible = False
    sync_child_candidate = False
    snapshot_valid = False
    base_sha = ""
    head_ref = ""
    head_sha = ""
    parent_sha = ""
    source_base_sha = ""
    try:
        pull_request = _load_json(args.pull_request_json)
        commit = _load_json(args.commit_json)
        comparison = _load_json(args.comparison_json)
        parent_commit = _load_json(args.parent_commit_json)
        parent_comparison = _load_json(args.parent_comparison_json)
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
            parent_sha,
            source_base_sha,
        ) = trusted_sync_child_candidate(
            pull_request,
            commit,
            parent_commit,
            parent_comparison,
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
        handle.write(f"parent_sha={parent_sha}\n")
        handle.write(f"source_base_sha={source_base_sha}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
