#!/usr/bin/env python3
"""Keep pull request metadata aligned with its linked work Issue."""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]
JsonValue = JsonObject | list[Any]
Runner = Callable[[list[str], str | None], JsonValue]
MilestoneDetector = Callable[[str], tuple[int, str] | None]
CLASSIFICATION_LABELS = {"bug", "documentation", "enhancement"}
MILESTONE_REMINDER_MARKER = "<!-- csarc-milestone-safeguard:551 -->"
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


def _run_gh(arguments: list[str], stdin: str | None = None) -> JsonValue:
    """Run GitHub CLI and return one JSON object or array."""
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
    if not isinstance(value, (dict, list)):
        raise MetadataError("gh api returned an unexpected response")
    return value


def _object(value: JsonValue, description: str) -> JsonObject:
    """Require one object-shaped API response."""
    if not isinstance(value, dict):
        raise MetadataError(f"GitHub returned invalid {description}")
    return value


def _objects(value: JsonValue, description: str) -> list[JsonObject]:
    """Flatten one paginated GitHub response into validated objects."""
    if not isinstance(value, list):
        raise MetadataError(f"GitHub returned invalid {description}")
    if all(isinstance(item, dict) for item in value):
        return value
    if all(isinstance(page, list) for page in value):
        items = [item for page in value for item in page]
        if all(isinstance(item, dict) for item in items):
            return items
    raise MetadataError(f"GitHub returned invalid {description}")


def _detect_open_milestone(repo: str) -> tuple[int, str] | None:
    """Reuse the repository's conservative #551 Milestone heuristic."""
    detector = Path(__file__).with_name("detect-open-milestone")
    completed = subprocess.run(  # noqa: S603
        [str(detector), "--repo", repo],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    try:
        number_text, title = completed.stdout.rstrip("\n").split("\t", 1)
        return int(number_text), title
    except (TypeError, ValueError) as error:
        raise MetadataError(
            "detect-open-milestone returned invalid output"
        ) from error


def linked_issue_numbers(head: str, body: str) -> tuple[int, ...]:
    """Read every unique work Issue named by the branch or PR body."""
    numbers: list[int] = []
    branch_match = BRANCH_ISSUE.match(head)
    if branch_match:
        numbers.append(int(branch_match.group(1)))
    numbers.extend(
        int(match.group(1)) for match in CLOSING_ISSUE.finditer(body)
    )
    return tuple(dict.fromkeys(numbers))


def linked_issue_number(head: str, body: str) -> int | None:
    """Return the first linked work Issue for compatibility with callers."""
    numbers = linked_issue_numbers(head, body)
    return numbers[0] if numbers else None


def resolve_workflow_run_pr(
    repo: str,
    head_sha: str,
    head_repository: str,
    head_branch: str,
    run: Runner = _run_gh,
) -> int:
    """Resolve exactly one live PR associated with a completed policy run."""
    pulls = run(
        [
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            "--paginate",
            "--slurp",
            f"repos/{repo}/commits/{head_sha}/pulls",
        ],
        None,
    )
    candidates = _objects(pulls, "associated pull requests")

    matches = [
        pull
        for pull in candidates
        if isinstance(pull, dict)
        and pull.get("state") == "open"
        and pull.get("head", {}).get("sha") == head_sha
        and pull.get("head", {}).get("ref") == head_branch
        and pull.get("head", {}).get("repo", {}).get("full_name")
        == head_repository
        and pull.get("base", {}).get("repo", {}).get("full_name") == repo
        and isinstance(pull.get("number"), int)
    ]
    if len(matches) != 1:
        raise MetadataError(
            "policy run must resolve to exactly one open pull request; "
            f"found {len(matches)}"
        )
    return int(matches[0]["number"])


def issue_classification(issue: JsonObject) -> str:
    """Return the PR label implied by native Issue metadata or fallback."""
    labels: set[str] = {
        item["name"]
        for item in issue.get("labels", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    selected = labels & CLASSIFICATION_LABELS
    if len(selected) > 1:
        raise MetadataError(
            "linked Issue has conflicting classification labels"
        )

    issue_type = issue.get("type")
    type_name = issue_type.get("name") if isinstance(issue_type, dict) else None
    selected_label = next(iter(selected), None)
    if type_name == "Task" and selected_label == "documentation":
        return "documentation"
    if type_name in {"Bug", "Feature", "Task"} and selected_label is not None:
        raise MetadataError(
            "linked Issue has a redundant or conflicting work-kind label"
        )
    if type_name == "Bug":
        return "bug"
    if type_name in {"Feature", "Task"}:
        return "enhancement"
    if selected_label is not None:
        return selected_label
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
    pull = _object(
        run(["api", f"repos/{repo}/pulls/{number}"], None),
        "pull-request metadata",
    )
    issue_numbers = linked_issue_numbers(
        str(pull.get("head", {}).get("ref", "")), str(pull.get("body") or "")
    )
    if not issue_numbers:
        return f"PR #{number}: no linked work Issue; metadata unchanged"
    if len(issue_numbers) != 1:
        joined = ", ".join(f"#{value}" for value in issue_numbers)
        raise MetadataError(
            f"PR #{number} references multiple work Issues: {joined}"
        )
    issue_number = issue_numbers[0]

    issue = _object(
        run(["api", f"repos/{repo}/issues/{issue_number}"], None),
        "Issue metadata",
    )
    if "pull_request" in issue:
        raise MetadataError(f"#{issue_number} is not an Issue")
    current = _object(
        run(["api", f"repos/{repo}/issues/{number}"], None),
        "pull-request Issue metadata",
    )
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


def sync_issue_pull_requests(
    repo: str, issue_number: int, run: Runner = _run_gh
) -> str:
    """Resynchronize open PRs after their linked Issue changes Milestone."""
    pulls = _objects(
        run(
            [
                "api",
                "--paginate",
                "--slurp",
                f"repos/{repo}/pulls?state=open&per_page=100",
            ],
            None,
        ),
        "open pull requests",
    )
    numbers = sorted(
        {
            int(pull["number"])
            for pull in pulls
            if isinstance(pull.get("number"), int)
            and issue_number
            in linked_issue_numbers(
                str(pull.get("head", {}).get("ref", "")),
                str(pull.get("body") or ""),
            )
        }
    )
    for number in numbers:
        sync_pull_request(repo, number, run)
    return (
        f"Issue #{issue_number}: synchronized {len(numbers)} open pull "
        "request(s)"
    )


def remind_missing_milestone(
    repo: str,
    number: int,
    run: Runner = _run_gh,
    detect: MilestoneDetector = _detect_open_milestone,
) -> str:
    """Post the non-blocking #551 reminder from the trusted workflow."""
    pull = _object(
        run(["api", f"repos/{repo}/pulls/{number}"], None),
        "pull-request metadata",
    )
    issue_number = linked_issue_number(
        str(pull.get("head", {}).get("ref", "")), str(pull.get("body") or "")
    )
    if issue_number is None:
        return f"PR #{number}: no linked work Issue; no Milestone reminder"

    issue = _object(
        run(["api", f"repos/{repo}/issues/{issue_number}"], None),
        "Issue metadata",
    )
    current = _object(
        run(["api", f"repos/{repo}/issues/{number}"], None),
        "pull-request Issue metadata",
    )
    if (
        issue.get("milestone") is not None
        or current.get("milestone") is not None
    ):
        return f"PR #{number}: Milestone already selected"

    milestone = detect(repo)
    if milestone is None:
        return f"PR #{number}: no unambiguous open Milestone"
    milestone_number, milestone_title = milestone

    pages = run(
        [
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repo}/issues/{number}/comments",
        ],
        None,
    )
    if not isinstance(pages, list):
        raise MetadataError("GitHub returned invalid pull-request comments")
    comments = pages if all(isinstance(item, dict) for item in pages) else []
    if not comments and pages:
        if not all(isinstance(page, list) for page in pages):
            raise MetadataError("GitHub returned invalid pull-request comments")
        comments = [item for page in pages for item in page]
    if any(
        isinstance(comment, dict)
        and MILESTONE_REMINDER_MARKER in str(comment.get("body") or "")
        for comment in comments
    ):
        return f"PR #{number}: Milestone reminder already present"

    body = (
        f"{MILESTONE_REMINDER_MARKER}\n"
        f"Neither this pull request nor Issue #{issue_number} has a "
        "Milestone, and exactly one Milestone is currently open: "
        f"#{milestone_number} {milestone_title}.\n\n"
        "If this work belongs to it, attach the Milestone to the Issue "
        '(see docs/ci-policy.md, section "Milestone 掛勾與持續同步", for the '
        "closed-Milestone REST API workaround) and to this pull request. "
        "Otherwise no action is needed -- many Issues and pull requests "
        "are not tied to any Milestone."
    )
    _object(
        run(
            [
                "api",
                "--method",
                "POST",
                f"repos/{repo}/issues/{number}/comments",
                "--raw-field",
                f"body={body}",
            ],
            None,
        ),
        "Milestone reminder",
    )
    return f"PR #{number}: posted Milestone reminder"


def main() -> int:
    """Run one metadata synchronization command."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pr", type=int)
    target.add_argument("--issue", type=int)
    target.add_argument("--resolve-head-sha")
    parser.add_argument("--head-repository")
    parser.add_argument("--head-branch")
    args = parser.parse_args()
    if args.resolve_head_sha is not None:
        if args.head_repository is None or args.head_branch is None:
            parser.error(
                "--head-repository and --head-branch are required with "
                "--resolve-head-sha"
            )
        number = resolve_workflow_run_pr(
            args.repo,
            args.resolve_head_sha,
            args.head_repository,
            args.head_branch,
        )
        sys.stdout.write(f"{number}\n")
        return 0

    if args.issue is not None:
        LOGGER.info("%s", sync_issue_pull_requests(args.repo, args.issue))
        return 0
    if args.pr is None:
        parser.error("--pr or --issue is required")
    LOGGER.info("%s", sync_pull_request(args.repo, args.pr))
    try:
        LOGGER.info("%s", remind_missing_milestone(args.repo, args.pr))
    except MetadataError:
        LOGGER.warning(
            "::notice::Could not post the Milestone safeguard reminder "
            "(non-blocking, Issue #551)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
