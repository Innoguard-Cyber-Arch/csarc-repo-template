#!/usr/bin/env python3
"""Keep pull request metadata aligned with its linked work Issue."""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

JsonObject = dict[str, Any]
Runner = Callable[[list[str], str | None], JsonObject]
CLASSIFICATION_LABELS = {"bug", "documentation", "enhancement"}
LOGGER = logging.getLogger(__name__)
BRANCH_ISSUE = re.compile(
    r"^(?:feat|feature|enhancement|fix|bug|docs|documentation|refactor|test|"
    r"build|ci|chore|revert)/(\d+)-"
)
CLOSING_ISSUE = re.compile(
    r"(?:Closes|Fixes|Resolves)\s+#(\d+)(?:\D|$)", re.IGNORECASE
)


class MetadataError(RuntimeError):
    """Raised when metadata cannot be synchronized safely."""


def _run_gh(arguments: list[str], stdin: str | None = None) -> JsonObject:
    """Run GitHub CLI and return one JSON object."""
    gh_binary = shutil.which("gh")
    if gh_binary is None:
        raise MetadataError("GitHub CLI (gh) is required")
    completed = subprocess.run(  # noqa: S603
        [gh_binary, *arguments],
        check=False,
        capture_output=True,
        input=stdin,
        text=True,
    )
    if completed.returncode != 0:
        raise MetadataError(completed.stderr.strip() or "gh api failed")
    try:
        value = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as error:
        raise MetadataError("gh api returned invalid JSON") from error
    if not isinstance(value, dict):
        raise MetadataError("gh api returned an unexpected response")
    return value


def linked_issue_number(head: str, body: str) -> int | None:
    """Read the work Issue from the branch first, then the PR body."""
    match = BRANCH_ISSUE.match(head) or CLOSING_ISSUE.search(body)
    return int(match.group(1)) if match else None


def issue_classification(issue: JsonObject) -> str:
    """Return the one cross-item label implied by Issue metadata."""
    labels: set[str] = {
        item["name"]
        for item in issue.get("labels", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    selected = labels & CLASSIFICATION_LABELS
    if len(selected) == 1:
        return selected.pop()
    if len(selected) > 1:
        raise MetadataError(
            "linked Issue has conflicting classification labels"
        )

    issue_type = issue.get("type")
    type_name = issue_type.get("name") if isinstance(issue_type, dict) else None
    if type_name == "Bug":
        return "bug"
    if type_name in {"Feature", "Task"}:
        return "enhancement"
    raise MetadataError("linked Issue has no usable classification")


def desired_pull_request_metadata(
    pull: JsonObject, issue: JsonObject
) -> JsonObject:
    """Build the minimal REST patch without removing unrelated metadata."""
    classification = issue_classification(issue)
    labels = [
        item["name"]
        for item in pull.get("labels", [])
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and item["name"] not in CLASSIFICATION_LABELS
    ]
    labels.append(classification)

    assignees = [
        item["login"]
        for item in pull.get("assignees", [])
        if isinstance(item, dict) and isinstance(item.get("login"), str)
    ]
    author = pull.get("user")
    if isinstance(author, dict) and author.get("type") == "User":
        login = author.get("login")
        if isinstance(login, str):
            assignees.append(login)

    milestone = issue.get("milestone")
    milestone_number = (
        milestone.get("number") if isinstance(milestone, dict) else None
    )
    return {
        "assignees": sorted(set(assignees)),
        "labels": sorted(set(labels)),
        "milestone": milestone_number,
    }


def sync_pull_request(repo: str, number: int, run: Runner = _run_gh) -> str:
    """Synchronize one PR and return a concise status line."""
    pull = run(["api", f"repos/{repo}/pulls/{number}"], None)
    issue_number = linked_issue_number(
        str(pull.get("head", {}).get("ref", "")), str(pull.get("body") or "")
    )
    if issue_number is None:
        return f"PR #{number}: no linked work Issue; metadata unchanged"

    issue = run(["api", f"repos/{repo}/issues/{issue_number}"], None)
    if "pull_request" in issue:
        raise MetadataError(f"#{issue_number} is not an Issue")
    current = run(["api", f"repos/{repo}/issues/{number}"], None)
    desired = desired_pull_request_metadata(current, issue)
    current_milestone = current.get("milestone")
    current_metadata = {
        "assignees": sorted(
            item["login"]
            for item in current.get("assignees", [])
            if isinstance(item, dict) and isinstance(item.get("login"), str)
        ),
        "labels": sorted(
            item["name"]
            for item in current.get("labels", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ),
        "milestone": (
            current_milestone.get("number")
            if isinstance(current_milestone, dict)
            else None
        ),
    }
    if current_metadata == desired:
        return f"PR #{number}: metadata already matches Issue #{issue_number}"
    run(
        [
            "api",
            "--method",
            "PATCH",
            f"repos/{repo}/issues/{number}",
            "--input",
            "-",
        ],
        json.dumps(desired),
    )
    return f"PR #{number}: synchronized from Issue #{issue_number}"


def main() -> int:
    """Run one metadata synchronization command."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    args = parser.parse_args()
    LOGGER.info("%s", sync_pull_request(args.repo, args.pr))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
