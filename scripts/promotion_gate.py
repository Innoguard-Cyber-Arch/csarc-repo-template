#!/usr/bin/env python3
"""Create and verify delivery-promotion evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    delivery_sync = importlib.import_module("delivery_sync")
else:
    delivery_sync = importlib.import_module(f"{__package__}.delivery_sync")

UNCHECKED = re.compile(r"(?m)^\s*-\s+\[\s*\]")
CLOSING_ISSUE = re.compile(
    r"(?<!\w)(?a:Closes|Fixes|Resolves)[ \t]+#([1-9][0-9]*)(?!\w)",
    re.IGNORECASE,
)
CHECKPOINT_ISSUES = re.compile(
    r"(?m)^<!-- csarc-promotion-checkpoint: "
    r"(#[1-9][0-9]*(?:, #[1-9][0-9]*)*) -->$"
)
MILESTONE_BRANCH = re.compile(r"^dev/m([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$")
PROMOTION_BRIDGE = re.compile(r"^promote/m([1-9][0-9]*)-([a-z0-9][a-z0-9-]*)$")
RECOVERY_BRANCH = re.compile(r"^fix/([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$")
ISOLATED_BRANCH = re.compile(r"^dev/i([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$")
WORK_BRANCH = re.compile(
    r"^(?:feat|fix|docs|refactor|test|build|ci|chore|revert)/"
    r"([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$"
)
CONVENTIONAL_TITLE = re.compile(
    r"^(feat|fix|docs|refactor|test|build|ci|chore|revert)"
    r"(?:\([a-z0-9._/-]+\))?(!)?: "
)
INTENT_RANK = {"no-release": 0, "patch": 1, "minor": 2, "major": 3}
MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER"}
REQUIRED_QUOTA_WORKFLOWS = {
    ".github/workflows/ci.yml",
    ".github/workflows/promotion.yml",
}
BILLING_GATE_ANNOTATION_MESSAGE = (
    "The job was not started because recent account payments have failed or "
    "your spending limit needs to be increased. Please check the 'Billing & "
    "plans' section in your settings"
)
PREFLIGHT_REFETCH = "promotion preflight live refetch"


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Never forward a GitHub bearer credential through a redirect."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        """Reject every redirect."""
        return None


@dataclass(frozen=True)
class Route:
    """Promotion route selected from pull request metadata."""

    kind: str
    relevant: bool
    milestone: int | None = None
    issue: int | None = None


@dataclass(frozen=True)
class Canary:
    """External canary capability configured by repository variables."""

    state: str
    reason: str
    environment: str | None


class DeliveryAPI(Protocol):
    """Describe the REST method required by synchronization evidence."""

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, Any]:
        """Return an HTTP status and decoded response."""
        ...


class GitHubCLIAPI:
    """Adapt authenticated GitHub CLI reads to the sync evidence API."""

    def __init__(self, repo: str) -> None:
        """Bind API reads to one repository."""
        self.repo = repo

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, Any]:
        """Read one repository endpoint through the authenticated CLI."""
        prefix = f"repos/{self.repo}/"
        if (
            method != "GET"
            or payload is not None
            or not path.startswith(prefix)
        ):
            raise RuntimeError(
                "Promotion sync evidence only supports GitHub reads"
            )
        return 200, github_get(self.repo, path.removeprefix(prefix), "")


def route_for(  # noqa: C901
    base: str, head: str, labels: set[str], branch_strategy: str = "delivery"
) -> Route:
    """Classify a pull request without accepting arbitrary main PRs."""
    if base != "main":
        return Route("not-applicable", False)
    if head.startswith(("release-please--", "release/v")):
        return Route("release-follow-up", False)
    if "release-recovery" in labels:
        recovery = RECOVERY_BRANCH.fullmatch(head)
        if recovery and "hotfix" not in labels:
            return Route("release-recovery", True, issue=int(recovery.group(1)))
        return Route("invalid-main-route", True)
    if branch_strategy == "main":
        return Route("not-applicable", False)
    match = MILESTONE_BRANCH.fullmatch(head)
    if match and "promotion" in labels:
        return Route("milestone", True, int(match.group(1)))
    bridge = PROMOTION_BRIDGE.fullmatch(head)
    if bridge and "promotion" in labels:
        return Route("milestone", True, int(bridge.group(1)))
    isolated = ISOLATED_BRANCH.fullmatch(head)
    if isolated and "promotion" in labels:
        return Route("isolated", True, issue=int(isolated.group(1)))
    if head.startswith("fix/") and "hotfix" in labels:
        return Route("hotfix", True)
    if WORK_BRANCH.fullmatch(head) or head.startswith(
        ("dependabot/", "automation/")
    ):
        return Route("not-applicable", False)
    return Route("invalid-main-route", True)


def classify_canary(command: str, environment: str) -> Canary:
    """Use an explicit tri-state instead of assuming an external environment."""
    if command and environment:
        return Canary(
            "allowed", "canary command and environment configured", environment
        )
    if not command and not environment:
        return Canary("blocked", "no external canary is configured", None)
    return Canary(
        "unknown",
        "canary command and environment must be configured together",
        environment or None,
    )


def issue_number(body: str) -> int | None:
    """Return the first Issue closed by a promotion pull request."""
    match = CLOSING_ISSUE.search(body)
    return int(match.group(1)) if match else None


def checkpoint_issue_numbers(body: str) -> list[int] | None:
    """Return the canonical work-Issue list for a checkpoint promotion."""
    occurrences = len(
        re.findall(
            "csarc-promotion-checkpoint:", body, re.IGNORECASE | re.ASCII
        )
    )
    matches = CHECKPOINT_ISSUES.findall(body)
    if occurrences == 0:
        return None
    if occurrences != 1 or len(matches) != 1:
        raise RuntimeError(
            "Checkpoint Issue marker must appear exactly once and be valid"
        )
    numbers = [int(item[1:]) for item in matches[0].split(", ")]
    if numbers != sorted(set(numbers)):
        raise RuntimeError(
            "Checkpoint Issues must be unique and sorted numerically"
        )
    return numbers


def pull_request_issue_number(pull_request: dict[str, Any]) -> int:
    """Bind a reviewed delivery commit to its work Issue."""
    head = pull_request.get("head")
    head_ref = head.get("ref") if isinstance(head, dict) else None
    if not isinstance(head_ref, str):
        raise RuntimeError("Included pull request head is incomplete")
    match = WORK_BRANCH.fullmatch(head_ref)
    if match is None:
        raise RuntimeError("Included pull request is not a work Issue")
    branch_issue = int(match.group(1))
    body = pull_request.get("body")
    if not isinstance(body, str):
        raise RuntimeError(
            "Included pull request does not close its branch Issue"
        )
    closing_issues = {int(number) for number in CLOSING_ISSUE.findall(body)}
    if branch_issue not in closing_issues:
        raise RuntimeError(
            "Included pull request does not close its branch Issue"
        )
    return branch_issue


def issue_labels(issue: dict[str, Any]) -> set[str]:
    """Normalize REST Issue labels."""
    labels = issue.get("labels", [])
    return {
        label["name"]
        for label in labels
        if isinstance(label, dict) and isinstance(label.get("name"), str)
    }


def same_repository(pull_request: dict[str, Any], repo: str) -> bool:
    """Reject same-named delivery branches supplied by a fork."""
    head = pull_request.get("head")
    head_repo = head.get("repo") if isinstance(head, dict) else None
    return isinstance(head_repo, dict) and head_repo.get("full_name") == repo


def sync_pull_request_main_sha(
    pull_request: dict[str, Any],
    repo: str,
    delivery_branch: str,
    current_main_sha: str,
    token: str,
    api: DeliveryAPI,
) -> str:
    """Return the exact historical main merged by a reviewed sync PR."""
    base = pull_request.get("base")
    head = pull_request.get("head")
    head_ref = head.get("ref") if isinstance(head, dict) else None
    head_sha = head.get("sha") if isinstance(head, dict) else None
    if (
        not isinstance(base, dict)
        or base.get("ref") != delivery_branch
        or not isinstance(head_ref, str)
        or not head_ref.startswith("sync/")
        or not isinstance(head_sha, str)
        or not same_repository(pull_request, repo)
    ):
        raise RuntimeError("Included sync pull request has invalid provenance")
    sync_commit = github_get(repo, f"git/commits/{head_sha}", token)
    if not isinstance(sync_commit, dict):
        raise RuntimeError(
            "Included sync pull request has invalid commit shape"
        )
    parents = sync_commit.get("parents")
    if not isinstance(parents, list) or len(parents) != 2:
        raise RuntimeError(
            "Included sync pull request has invalid commit shape"
        )
    main_parent = parents[1]
    delivery_parent = parents[0]
    synced_main_sha = (
        main_parent.get("sha") if isinstance(main_parent, dict) else None
    )
    if not isinstance(synced_main_sha, str):
        raise RuntimeError("Included sync pull request has invalid provenance")
    expected_ref = delivery_sync.sync_branch_name(
        delivery_branch, synced_main_sha
    )
    legacy_ref = f"{expected_ref.rsplit('-', 1)[0]}-{synced_main_sha[:7]}"
    if head_ref not in {
        expected_ref,
        legacy_ref,
    } or not delivery_sync.includes_main(
        delivery_sync.compare(api, repo, synced_main_sha, current_main_sha)
    ):
        raise RuntimeError("Included sync pull request has invalid provenance")
    if head_ref == legacy_ref:
        base_sha = base.get("sha")
        delivery_parent_sha = (
            delivery_parent.get("sha")
            if isinstance(delivery_parent, dict)
            else None
        )
        sync_tree = sync_commit.get("tree")
        sync_tree_sha = (
            sync_tree.get("sha") if isinstance(sync_tree, dict) else None
        )
        main_commit = github_get(repo, f"git/commits/{synced_main_sha}", token)
        main_tree = (
            main_commit.get("tree") if isinstance(main_commit, dict) else None
        )
        main_tree_sha = (
            main_tree.get("sha") if isinstance(main_tree, dict) else None
        )
        if (
            not isinstance(base_sha, str)
            or delivery_parent_sha != base_sha
            or not isinstance(sync_tree_sha, str)
            or sync_tree_sha != main_tree_sha
        ):
            raise RuntimeError(
                "Included legacy sync pull request has invalid provenance"
            )
    return synced_main_sha


def legacy_sync_reaffirmed(
    legacy_pull: dict[str, Any],
    canonical_pull: dict[str, Any],
    repo: str,
    delivery_branch: str,
    synced_main_sha: str,
    token: str,
) -> bool:
    """Accept one pure legacy sync only with its empty canonical successor."""
    legacy_head = legacy_pull.get("head")
    canonical_head = canonical_pull.get("head")
    canonical_base = canonical_pull.get("base")
    legacy_ref = (
        legacy_head.get("ref") if isinstance(legacy_head, dict) else None
    )
    canonical_ref = (
        canonical_head.get("ref") if isinstance(canonical_head, dict) else None
    )
    canonical_sha = (
        canonical_head.get("sha") if isinstance(canonical_head, dict) else None
    )
    expected_ref = delivery_sync.sync_branch_name(
        delivery_branch, synced_main_sha
    )
    expected_legacy_ref = (
        f"{expected_ref.rsplit('-', 1)[0]}-{synced_main_sha[:7]}"
    )
    legacy_merge_sha = legacy_pull.get("merge_commit_sha")
    canonical_base_sha = (
        canonical_base.get("sha") if isinstance(canonical_base, dict) else None
    )
    if (
        legacy_ref != expected_legacy_ref
        or canonical_ref != expected_ref
        or canonical_base_sha != legacy_merge_sha
        or not isinstance(canonical_sha, str)
        or not isinstance(legacy_merge_sha, str)
        or not same_repository(legacy_pull, repo)
        or not same_repository(canonical_pull, repo)
    ):
        return False
    canonical_commit = github_get(repo, f"git/commits/{canonical_sha}", token)
    legacy_merge = github_get(repo, f"git/commits/{legacy_merge_sha}", token)
    main_commit = github_get(repo, f"git/commits/{synced_main_sha}", token)
    if (
        not isinstance(canonical_commit, dict)
        or not isinstance(legacy_merge, dict)
        or not isinstance(main_commit, dict)
    ):
        return False
    parents = canonical_commit.get("parents")
    if not isinstance(parents, list) or len(parents) != 2:
        return False
    parent_shas = [
        parent.get("sha") if isinstance(parent, dict) else None
        for parent in parents
    ]

    def tree_sha(commit: dict[str, Any]) -> str | None:
        tree = commit.get("tree")
        return tree.get("sha") if isinstance(tree, dict) else None

    trees = {
        tree_sha(canonical_commit),
        tree_sha(legacy_merge),
        tree_sha(main_commit),
    }
    return parent_shas == [legacy_merge_sha, synced_main_sha] and (
        len(trees) == 1 and None not in trees
    )


def release_intent(title: str) -> str:
    """Map a validated pull-request title to its SemVer intent."""
    match = CONVENTIONAL_TITLE.match(title)
    if match is None:
        return "no-release"
    if match.group(2):
        return "major"
    if match.group(1) == "feat":
        return "minor"
    if match.group(1) in {"fix", "revert"}:
        return "patch"
    return "no-release"


def highest_release_intent(titles: list[str]) -> str:
    """Return the highest SemVer intent represented by a delivery batch."""
    return max(
        (release_intent(title) for title in titles),
        key=INTENT_RANK.__getitem__,
        default="no-release",
    )


def check_promotion_intent(args: argparse.Namespace) -> None:
    """Require a promotion title to retain the batch's highest intent."""
    if args.titles_json is not None:
        titles = json.loads(args.titles_json)
        if not isinstance(titles, list) or any(
            not isinstance(title, str) for title in titles
        ):
            raise RuntimeError("Promotion title fixture must be a string list")
    else:
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            raise RuntimeError("GH_TOKEN is required to inspect promotion work")
        included = included_pull_requests(
            args.repo,
            args.base_sha,
            args.head_sha,
            args.delivery_branch,
            token,
            args.milestone,
            args.bridge_head_sha,
        )
        titles = [str(item["title"]) for item in included]
    if not titles:
        raise RuntimeError(
            "Delivery promotion contains no merged pull requests"
        )
    expected = highest_release_intent(titles)
    actual = release_intent(args.title)
    if actual != expected:
        raise RuntimeError(
            "Promotion pull-request title must declare the batch's highest "
            f"SemVer intent ({expected})"
        )
    print(f"Promotion release intent is {expected}.")  # noqa: T201


def included_pull_requests(  # noqa: C901
    repo: str,
    base_sha: str,
    head_sha: str,
    delivery_branch: str,
    token: str,
    milestone: int | None = None,
    bridge_head_sha: str | None = None,
    *,
    track_work_issues: bool = False,
) -> list[dict[str, object]]:
    """Find merged pull requests represented by the exact delivery range."""
    included: dict[int, dict[str, object]] = {}
    sync_pull_requests: dict[int, str] = {}
    sync_pull_request_details: dict[int, dict[str, Any]] = {}
    sync_api = promotion_api(repo, token) if track_work_issues else None
    saw_bridge_head = bridge_head_sha is None
    page = 1
    while True:
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        comparison = github_get(
            repo, f"compare/{base_sha}...{head_sha}?{query}", token
        )
        if not isinstance(comparison, dict):
            raise RuntimeError("GitHub returned an invalid commit comparison")
        commits = comparison.get("commits", [])
        if not isinstance(commits, list):
            raise RuntimeError("GitHub returned an invalid commit list")
        for commit in commits:
            sha = commit.get("sha") if isinstance(commit, dict) else None
            if not isinstance(sha, str):
                if bridge_head_sha is not None:
                    raise RuntimeError(
                        "GitHub returned invalid bridge commit provenance"
                    )
                continue
            if sha == bridge_head_sha:
                saw_bridge_head = True
                continue
            pull_requests = github_get(repo, f"commits/{sha}/pulls", token)
            if not isinstance(pull_requests, list):
                raise RuntimeError(
                    "GitHub returned an invalid associated pull-request list"
                )
            matched = False
            for pull_request in pull_requests:
                if not isinstance(pull_request, dict):
                    continue
                base = pull_request.get("base")
                number = pull_request.get("number")
                title = pull_request.get("title")
                base_ref = base.get("ref") if isinstance(base, dict) else None
                base_milestone = (
                    MILESTONE_BRANCH.fullmatch(base_ref)
                    if isinstance(base_ref, str)
                    else None
                )
                if (
                    pull_request.get("merged_at") is None
                    or not isinstance(base, dict)
                    or (
                        base_ref != delivery_branch
                        and (
                            milestone is None
                            or base_milestone is None
                            or int(base_milestone.group(1)) != milestone
                        )
                    )
                    or not isinstance(number, int)
                    or not isinstance(title, str)
                ):
                    continue
                matched = True
                evidence: dict[str, object] = {
                    "number": number,
                    "title": title,
                    "intent": release_intent(title),
                }
                if track_work_issues:
                    pull_head = pull_request.get("head")
                    pull_head_ref = (
                        pull_head.get("ref")
                        if isinstance(pull_head, dict)
                        else None
                    )
                    if (
                        isinstance(pull_head_ref, str)
                        and pull_head_ref.startswith("sync/")
                        and sync_api is not None
                    ):
                        evidence["issue"] = None
                        sync_pull_requests[number] = sync_pull_request_main_sha(
                            pull_request,
                            repo,
                            delivery_branch,
                            base_sha,
                            token,
                            sync_api,
                        )
                        sync_pull_request_details[number] = pull_request
                    else:
                        evidence["issue"] = pull_request_issue_number(
                            pull_request
                        )
                included[number] = evidence
            if (
                bridge_head_sha is not None or track_work_issues
            ) and not matched:
                scope = (
                    "same-Milestone" if milestone is not None else "eligible"
                )
                raise RuntimeError(
                    f"Bridge commit {sha} has no {scope} merged PR"
                )
        if len(commits) < 100:
            break
        page += 1
    if not saw_bridge_head:
        raise RuntimeError("GitHub comparison omitted the promotion bridge")
    for number, synced_main_sha in sync_pull_requests.items():
        verified_sync = (
            delivery_sync.merged_sync_pr_number(
                sync_api,
                repo,
                delivery_branch,
                synced_main_sha,
                head_sha,
            )
            if sync_api is not None
            else None
        )
        if verified_sync != number and (
            verified_sync is None
            or sync_pull_requests.get(verified_sync) != synced_main_sha
            or not legacy_sync_reaffirmed(
                sync_pull_request_details[number],
                sync_pull_request_details[verified_sync],
                repo,
                delivery_branch,
                synced_main_sha,
                token,
            )
        ):
            raise RuntimeError(
                "Included sync pull request lacks reviewed merge provenance"
            )
    return [included[number] for number in sorted(included)]


def unfinished_milestone_issues(
    issues: list[dict[str, Any]], promotion_number: int
) -> list[int]:
    """Return non-promotion work that is open or has unchecked acceptance."""
    unfinished: list[int] = []
    for issue in issues:
        if "pull_request" in issue or issue.get("number") == promotion_number:
            continue
        if "promotion" in issue_labels(issue):
            continue
        body = issue.get("body") or ""
        if issue.get("state") != "closed" or UNCHECKED.search(body):
            number = issue.get("number")
            if isinstance(number, int):
                unfinished.append(number)
    return sorted(unfinished)


def milestone_included_issues(
    issues: list[dict[str, Any]],
    promotion_number: int,
    included_pull_requests: list[dict[str, object]],
    checkpoint: list[int] | None,
) -> list[dict[str, object]]:
    """Validate and return work Issues represented by this candidate."""
    issue_by_number = {
        issue["number"]: issue
        for issue in issues
        if "pull_request" not in issue
        and issue.get("number") != promotion_number
        and "promotion" not in issue_labels(issue)
        and isinstance(issue.get("number"), int)
    }
    actual = sorted(
        {
            number
            for pull_request in included_pull_requests
            if isinstance((number := pull_request.get("issue")), int)
        }
    )
    if checkpoint is None:
        unfinished = unfinished_milestone_issues(issues, promotion_number)
        if unfinished:
            rendered = ", ".join(f"#{item}" for item in unfinished)
            raise RuntimeError(f"Milestone work is not complete: {rendered}")
    elif checkpoint != actual:
        raise RuntimeError(
            "Checkpoint Issues do not match the candidate work Issues"
        )
    invalid = [
        number
        for number in actual
        if number not in issue_by_number
        or issue_by_number[number].get("state") != "closed"
        or UNCHECKED.search(str(issue_by_number[number].get("body") or ""))
    ]
    if invalid:
        rendered = ", ".join(f"#{item}" for item in invalid)
        raise RuntimeError(
            f"Included Milestone work is not closed and complete: {rendered}"
        )
    return [
        {"number": number, "title": issue_by_number[number].get("title", "")}
        for number in actual
    ]


def main_is_current(
    current_main: str, base_sha: str, contains_main: bool
) -> bool:
    """Require the reviewed base and delivery ancestry to match current main."""
    return current_main == base_sha and contains_main


def promotion_main_evidence(
    api: DeliveryAPI,
    repo: str,
    current_main: str,
    base_sha: str,
    delivery_branch: str | None,
    head_sha: str,
    contains_main: bool,
) -> str | None:
    """Return exact ancestry or reviewed squash evidence for a promotion."""
    if main_is_current(current_main, base_sha, contains_main):
        return "direct-ancestry"
    if current_main != base_sha or delivery_branch is None:
        return None
    sync_pr = delivery_sync.merged_sync_pr_number(
        api, repo, delivery_branch, current_main, head_sha
    )
    return f"squash-sync-pr-{sync_pr}" if sync_pr is not None else None


def github_get(repo: str, path: str, token: str) -> object:
    """Read one GitHub REST endpoint with the workflow token."""
    resource = f"repos/{repo}"
    if path:
        resource += f"/{path.lstrip('/')}"
    if not token:
        executable = shutil.which("gh")
        if executable is None:
            raise RuntimeError(
                "GH_TOKEN or an authenticated GitHub CLI is required"
            )
        result = subprocess.run(  # noqa: S603
            [executable, "api", resource],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)
    request = urllib.request.Request(
        f"https://api.github.com/{resource}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    opener = urllib.request.build_opener(RejectRedirects())
    with opener.open(request, timeout=20) as response:
        return json.load(response)


def repository_variables(repo: str, token: str) -> dict[str, str]:
    """Read every repository Actions variable without trusting one page."""
    variables: dict[str, str] = {}
    total: int | None = None
    page = 1
    while total is None or len(variables) < total:
        payload = github_get(
            repo, f"actions/variables?per_page=100&page={page}", token
        )
        items = payload.get("variables") if isinstance(payload, dict) else None
        count = (
            payload.get("total_count") if isinstance(payload, dict) else None
        )
        if not isinstance(items, list) or not isinstance(count, int):
            raise RuntimeError("Repository variable list is incomplete")
        if total is not None and count != total:
            raise RuntimeError("Repository variable count changed")
        total = count
        for item in items:
            name = item.get("name") if isinstance(item, dict) else None
            value = item.get("value") if isinstance(item, dict) else None
            if (
                not isinstance(name, str)
                or not isinstance(value, str)
                or name in variables
            ):
                raise RuntimeError("Repository variable list is invalid")
            variables[name] = value
        if not items and len(variables) < total:
            raise RuntimeError("Repository variable list is incomplete")
        page += 1
    if len(variables) != total:
        raise RuntimeError("Repository variable list is incomplete")
    return variables


def promotion_api(repo: str, token: str) -> DeliveryAPI:
    """Use the workflow token or the existing authenticated CLI session."""
    return delivery_sync.GitHubAPI(token) if token else GitHubCLIAPI(repo)


def milestone_issues(
    repo: str, milestone: int, token: str
) -> list[dict[str, Any]]:
    """Read every Issue in a Milestone across REST pages."""
    issues: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "milestone": milestone,
                "state": "all",
                "per_page": 100,
                "page": page,
            }
        )
        payload = github_get(repo, f"issues?{query}", token)
        if not isinstance(payload, list):
            raise RuntimeError(
                "GitHub returned an invalid Milestone Issue list"
            )
        page_items = [item for item in payload if isinstance(item, dict)]
        issues.extend(page_items)
        if len(payload) < 100:
            return issues
        page += 1


def git_output(*arguments: str) -> str:
    """Run a read-only Git command and return one line."""
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git is required")
    return subprocess.run(  # noqa: S603
        [executable, *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def promotion_bridge_source(
    repo: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    candidate_sha: str,
    milestone: int | None,
    token: str,
) -> dict[str, str] | None:
    """Verify a temporary bridge made only from source delivery and main."""
    match = PROMOTION_BRIDGE.fullmatch(branch)
    if match is None:
        return None
    if milestone is None or int(match.group(1)) != milestone:
        raise RuntimeError("Promotion bridge and Issue Milestones differ")
    source_ref = f"dev/m{match.group(1)}-{match.group(2)}"
    source = github_get(
        repo,
        f"git/ref/heads/{urllib.parse.quote(source_ref, safe='')}",
        token,
    )
    source_object = source.get("object") if isinstance(source, dict) else None
    source_sha = (
        source_object.get("sha") if isinstance(source_object, dict) else None
    )
    if not isinstance(source_sha, str):
        raise RuntimeError("GitHub returned an invalid bridge source reference")
    parents = git_output("rev-list", "--parents", "-n", "1", head_sha).split()
    if parents != [head_sha, source_sha, base_sha]:
        raise RuntimeError(
            "Promotion bridge must merge current main into source delivery"
        )
    source_tree = git_output("rev-parse", f"{source_sha}^{{tree}}")
    if (
        git_output("rev-parse", f"{head_sha}^{{tree}}") != source_tree
        or git_output("rev-parse", f"{candidate_sha}^{{tree}}") != source_tree
    ):
        raise RuntimeError("Promotion bridge must preserve the source tree")
    return {
        "source_ref": source_ref,
        "source_sha": source_sha,
        "source_tree": source_tree,
    }


def promotion_freshness_sha(
    head_sha: str, bridge: dict[str, str] | None
) -> str:
    """Return the delivery SHA that must contain current main."""
    if bridge is None:
        return head_sha
    source_sha = bridge.get("source_sha")
    if not isinstance(source_sha, str):
        raise RuntimeError("Promotion bridge source SHA is invalid")
    return source_sha


def contains_commit(ancestor: str, descendant: str) -> bool:
    """Return whether the delivery head contains the current main commit."""
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git is required")
    return (
        subprocess.run(  # noqa: S603
            [executable, "merge-base", "--is-ancestor", ancestor, descendant],
            check=False,
        ).returncode
        == 0
    )


def sha256(path: Path) -> str:
    """Hash a candidate archive without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_destination(path: Path) -> Path:
    """Reject a symlinked output or parent before opening anything."""
    destination = Path(os.path.abspath(path))
    for parent in (destination.parent, *destination.parent.parents):
        mode = os.lstat(parent).st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise RuntimeError("Output parent must be a real directory")
    try:
        mode = os.lstat(destination).st_mode
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISREG(mode):
            raise RuntimeError("Output destination must be a regular file")
    return destination


def atomic_output(path: Path, writer: Callable[[BinaryIO], object]) -> None:
    """Atomically replace a regular output without following any symlink."""
    destination = safe_destination(path)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        if os.name != "nt":
            directory = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def write_evidence(path: Path, evidence: dict[str, object]) -> None:
    """Write machine-readable evidence through the safe output path."""
    content = (json.dumps(evidence, indent=2) + "\n").encode()
    atomic_output(path, lambda stream: stream.write(content))


def require_distinct_paths(*paths: Path) -> None:
    """Reject aliases that could replace an input or candidate archive."""
    resolved = [safe_destination(path) for path in paths]
    if len({str(path) for path in resolved}) != len(resolved):
        raise RuntimeError("Evidence and archive paths must be distinct")
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if (
                left.exists()
                and right.exists()
                and os.path.samefile(left, right)
            ):
                raise RuntimeError(
                    "Evidence and archive paths must be distinct"
                )


def local_verification_command() -> list[str]:
    """Select the checked-in verifier for root or generated repositories."""
    for candidate in ("scripts/verify-template.sh", "scripts/verify"):
        path = Path(candidate)
        try:
            mode = os.lstat(path).st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISREG(mode):
            return [f"./{candidate}"]
    raise RuntimeError("No repository verification command is available")


def write_outputs(path: Path | None, values: dict[str, object]) -> None:
    """Append scalar outputs for later workflow jobs."""
    if path is None:
        return
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            rendered = (
                str(value).lower() if isinstance(value, bool) else str(value)
            )
            output.write(f"{key}={rendered}\n")


def write_summary(path: Path | None, lines: list[str]) -> None:
    """Append concise human-readable evidence to the run summary."""
    if path is None:
        return
    with path.open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")


def require_comment_url(
    url: str, repo: str, pr_number: int, expected_body: str, token: str
) -> dict[str, Any]:
    """Refetch an exact human maintainer statement on the promotion PR."""
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.path != f"/{repo}/pull/{pr_number}"
        or re.fullmatch(r"issuecomment-\d+", parsed.fragment) is None
    ):
        raise RuntimeError(
            "Fallback references must be GitHub comments on the promotion PR"
        )
    identifier = parsed.fragment.removeprefix("issuecomment-")
    comment = github_get(repo, f"issues/comments/{identifier}", token)
    user = comment.get("user") if isinstance(comment, dict) else None
    if (
        not isinstance(comment, dict)
        or comment.get("html_url") != url
        or comment.get("issue_url")
        != f"https://api.github.com/repos/{repo}/issues/{pr_number}"
        or comment.get("body") != expected_body
        or comment.get("author_association") not in MAINTAINER_ASSOCIATIONS
        or not isinstance(user, dict)
        or user.get("type") != "User"
        or not isinstance(user.get("login"), str)
    ):
        raise RuntimeError(
            "Fallback comment is not an exact maintainer statement"
        )
    return comment


def fallback_statement(
    kind: str, evidence: dict[str, Any], run_urls: list[str]
) -> str:
    """Bind a human statement to one exact promotion candidate."""
    fields = preflight_binding(evidence)
    fields["runs"] = sorted(run_urls)
    binding = json.dumps(
        fields,
        sort_keys=True,
        separators=(",", ":"),
    )
    statements = {
        "attestation": (
            "I have billing visibility and confirm this zero-step billing "
            "block is an authorized one-time exception for this exact "
            "evidence."
        ),
        "authorization": (
            "I authorize this exact one-time fallback without admin bypass or "
            "a successful Check Run."
        ),
    }
    return f"Actions quota fallback {kind}\n\n`{binding}`\n\n{statements[kind]}"


def quota_fallback_note(
    repo: str, pr_number: int, head_sha: str, run_urls: list[str]
) -> str:
    """Bind a routine pull request's quota fallback note to one commit."""
    fields = {
        "repository": repo,
        "pull_request": pr_number,
        "head_sha": head_sha,
        "runs": sorted(run_urls),
    }
    binding = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    statement = (
        "Every failing check on this exact commit is GitHub's zero-step "
        "billing gate, not a real failure; full local verification passed "
        "for this exact commit. This repository's plan structurally runs "
        "over its included Actions minutes, so this is a standing, "
        "accepted operating condition rather than an incident. No release, "
        "publishing, deployment, provenance, or canary success is claimed."
    )
    return f"Actions quota fallback note\n\n`{binding}`\n\n{statement}"


def preflight_binding(evidence: dict[str, Any]) -> dict[str, object]:
    """Return every security-relevant field from preflight evidence."""
    archive = evidence.get("candidate_archive") or {}
    canary = evidence.get("canary") or {}
    stable_canary = {
        key: value for key, value in canary.items() if key != "result"
    }
    binding: dict[str, object] = {
        "schema_version": evidence.get("schema_version"),
        "repository": evidence.get("repository"),
        "route": evidence.get("route"),
        "pull_request": evidence.get("pull_request"),
        "promotion_pull_request": evidence.get("promotion_pull_request"),
        "tracking_issue": evidence.get("tracking_issue"),
        "tracking_issue_state": evidence.get("tracking_issue_state"),
        "milestone_promotion": evidence.get("milestone_promotion"),
        "base_ref": evidence.get("base_ref"),
        "base_sha": evidence.get("base_sha"),
        "head_ref": evidence.get("head_ref"),
        "head_sha": evidence.get("head_sha"),
        "main_sync": evidence.get("main_sync"),
        "promotion_bridge": evidence.get("promotion_bridge"),
        "candidate_sha": evidence.get("candidate_sha"),
        "candidate_tree": evidence.get("candidate_tree"),
        "archive_sha256": archive.get("sha256"),
        "included_issues": evidence.get("included_issues"),
        "release": evidence.get("release"),
        "canary": stable_canary,
    }
    return binding


def require_same_preflight(
    evidence: dict[str, Any], rebuilt: dict[str, Any]
) -> None:
    """Reject local preflight JSON that differs from live reconstruction."""
    if preflight_binding(evidence) != preflight_binding(rebuilt):
        raise RuntimeError(
            "Promotion preflight evidence does not match live reconstruction"
        )


def require_run_url(url: str, repo: str) -> None:
    """Require a GitHub Actions run reference from the same repository."""
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or re.fullmatch(rf"/{re.escape(repo)}/actions/runs/\d+", parsed.path)
        is None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "Blocked runs must be GitHub Actions URLs from this repository"
        )


def failed_pull_request_run_urls(  # noqa: C901
    repo: str, head_sha: str, token: str
) -> list[str]:
    """Return every latest failed Actions run for one pull-request head."""
    check_runs: list[dict[str, Any]] = []
    total: int | None = None
    page = 1
    while total is None or len(check_runs) < total:
        payload = github_get(
            repo,
            f"commits/{head_sha}/check-runs?filter=latest&per_page=100&page={page}",
            token,
        )
        items = payload.get("check_runs") if isinstance(payload, dict) else None
        count = (
            payload.get("total_count") if isinstance(payload, dict) else None
        )
        if not isinstance(items, list) or not isinstance(count, int):
            raise RuntimeError("Pull request check runs are incomplete")
        if total is not None and count != total:
            raise RuntimeError(
                "Pull request check run count changed during pagination"
            )
        total = count
        check_runs.extend(item for item in items if isinstance(item, dict))
        if not items and len(check_runs) < total:
            raise RuntimeError("Pull request check runs are incomplete")
        page += 1
    if len(check_runs) != total:
        raise RuntimeError("Pull request check runs are incomplete")

    statuses = github_get(repo, f"commits/{head_sha}/status", token)
    status_items = (
        statuses.get("statuses") if isinstance(statuses, dict) else None
    )
    if not isinstance(status_items, list) or any(
        not isinstance(item, dict) or item.get("state") != "success"
        for item in status_items
    ):
        raise RuntimeError("Pull request has a non-success commit status")

    run_urls: set[str] = set()
    for check in check_runs:
        conclusion = check.get("conclusion")
        if conclusion in {"success", "neutral", "skipped"}:
            continue
        if conclusion != "failure":
            raise RuntimeError(
                "Pull request has an unfinished or unsupported check"
            )
        details_url = str(check.get("details_url") or "")
        parsed = urllib.parse.urlparse(details_url)
        match = re.fullmatch(
            rf"/{re.escape(repo)}/actions/runs/(\d+)(?:/job/\d+)?",
            parsed.path,
        )
        if (
            parsed.scheme != "https"
            or parsed.netloc != "github.com"
            or match is None
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("Pull request has a failed non-Actions check")
        run_urls.add(f"https://github.com/{repo}/actions/runs/{match.group(1)}")
    if not run_urls:
        raise RuntimeError("Pull request has no failed Actions run")
    return sorted(run_urls)


def require_zero_step_run(  # noqa: C901
    url: str,
    repo: str,
    pr_number: int,
    head_ref: str,
    head_sha: str,
    token: str,
    *,
    getter: Callable[[str, str, str], object] | None = None,
) -> str:
    """Prove one PR run was stopped by GitHub's zero-step billing gate."""
    get = getter or github_get
    run_id = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
    run = get(repo, f"actions/runs/{run_id}", token)
    if (
        not isinstance(run, dict)
        or type(run.get("id")) is not int
        or run["id"] != int(run_id)
        or run.get("head_sha") != head_sha
        or run.get("head_branch") != head_ref
        or run.get("event") != "pull_request"
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or not isinstance(run.get("repository"), dict)
        or run["repository"].get("full_name") != repo
        or not isinstance(run.get("head_repository"), dict)
        or run["head_repository"].get("full_name") != repo
    ):
        raise RuntimeError("Blocked run does not match the failed PR head")
    pull_requests = run.get("pull_requests")
    if (
        not isinstance(pull_requests, list)
        or not pull_requests
        or not all(
            isinstance(item, dict)
            and type(item.get("number")) is int
            and item["number"] > 0
            for item in pull_requests
        )
        or not any(item["number"] == pr_number for item in pull_requests)
    ):
        raise RuntimeError("Blocked run belongs to another pull request")
    jobs: list[dict[str, Any]] = []
    total: int | None = None
    page = 1
    while total is None or len(jobs) < total:
        payload = get(
            repo,
            f"actions/runs/{run_id}/jobs?per_page=100&page={page}",
            token,
        )
        items = payload.get("jobs") if isinstance(payload, dict) else None
        count = (
            payload.get("total_count") if isinstance(payload, dict) else None
        )
        if (
            not isinstance(items, list)
            or not all(isinstance(item, dict) for item in items)
            or type(count) is not int
            or count < 0
        ):
            raise RuntimeError("Blocked run jobs are incomplete")
        if total is not None and count != total:
            raise RuntimeError(
                "Blocked run job count changed during pagination"
            )
        total = count
        jobs.extend(items)
        if not items and len(jobs) < total:
            raise RuntimeError("Blocked run jobs are incomplete")
        page += 1
    if not jobs or len(jobs) != total:
        raise RuntimeError("Blocked run jobs are incomplete")
    if any(
        type(job.get("id")) is not int
        or job["id"] <= 0
        or not (
            job.get("runner_id") is None
            or (type(job.get("runner_id")) is int and job["runner_id"] == 0)
        )
        or not isinstance(job.get("steps"), list)
        or bool(job["steps"])
        or job.get("conclusion") not in {"failure", "skipped"}
        for job in jobs
    ):
        raise RuntimeError("Quota fallback requires zero-step hosted jobs")
    failed_jobs = [job for job in jobs if job.get("conclusion") == "failure"]
    if not failed_jobs:
        raise RuntimeError("Blocked run contains no failed hosted job")
    for job in failed_jobs:
        annotations: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = get(
                repo,
                f"check-runs/{job.get('id')}/annotations?per_page=100&page={page}",
                token,
            )
            if not isinstance(payload, list):
                raise RuntimeError("Blocked job annotations are incomplete")
            if not all(isinstance(item, dict) for item in payload):
                raise RuntimeError("Blocked job annotations are incomplete")
            annotations.extend(payload)
            if len(payload) < 100:
                break
            page += 1
        if (
            len(annotations) != 1
            or annotations[0].get("message") != BILLING_GATE_ANNOTATION_MESSAGE
        ):
            raise RuntimeError(
                "Blocked job does not match GitHub's zero-step billing gate"
            )
    return str(run.get("path", ""))


def rebuild_quota_preflight(
    evidence: dict[str, Any],
    pull: dict[str, Any],
    args: argparse.Namespace,
    token: str,
) -> dict[str, Any]:
    """Recreate preflight from live GitHub state and the checked-out head."""
    repo = str(evidence["repository"])
    variables = repository_variables(repo, token)
    strategy = "delivery"
    with tempfile.TemporaryDirectory(dir=args.archive.parent) as directory:
        root = Path(directory)
        event_path = root / "event.json"
        event_path.write_text(
            json.dumps(
                {"number": evidence["pull_request"], "pull_request": pull}
            ),
            encoding="utf-8",
        )
        output = root / "preflight.json"
        prepare(
            argparse.Namespace(
                event="pull_request",
                event_path=event_path,
                repo=repo,
                branch_strategy=strategy,
                candidate_sha=evidence["head_sha"],
                workflow_run=evidence.get("workflow_run", "local-fallback"),
                canary_command=variables.get("CSARC_CANARY_COMMAND", ""),
                canary_environment=variables.get(
                    "CSARC_CANARY_ENVIRONMENT", ""
                ),
                archive=root / args.archive.name,
                output=output,
                github_output=None,
                summary=None,
            )
        )
        rebuilt = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(rebuilt, dict):
        raise RuntimeError("Rebuilt promotion preflight is invalid")
    return rebuilt


def validate_quota_preflight(  # noqa: C901
    evidence: dict[str, Any],
    args: argparse.Namespace,
    token: str,
    *,
    validate_comments: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Refetch every mutable input for one exact quota fallback."""
    repo = str(evidence["repository"])
    pr_number = int(evidence["pull_request"])
    repository = github_get(repo, "", token)
    pull = github_get(repo, f"pulls/{pr_number}", token)
    base = pull.get("base") if isinstance(pull, dict) else None
    head = pull.get("head") if isinstance(pull, dict) else None
    if (
        not isinstance(repository, dict)
        or repository.get("full_name") != repo
        or repository.get("archived") is not False
        or repository.get("default_branch") != "main"
        or not isinstance(pull, dict)
        or pull.get("number") != pr_number
        or pull.get("state") != "open"
        or pull.get("merged") is not False
        or not isinstance(base, dict)
        or base.get("ref") != "main"
        or base.get("sha") != evidence.get("base_sha")
        or not isinstance(head, dict)
        or head.get("ref") != evidence.get("head_ref")
        or head.get("sha") != evidence.get("head_sha")
        or not same_repository(pull, repo)
    ):
        raise RuntimeError("Live promotion identity does not match evidence")
    labels = {
        item["name"]
        for item in pull.get("labels", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    route = evidence.get("route") or {}
    strategy = "delivery"
    if asdict(route_for("main", str(head["ref"]), labels, strategy)) != route:
        raise RuntimeError("Live promotion route does not match evidence")
    current_main = github_get(repo, "git/ref/heads/main", token)
    main_object = (
        current_main.get("object") if isinstance(current_main, dict) else None
    )
    current_main_sha = (
        main_object.get("sha") if isinstance(main_object, dict) else None
    )
    commit = github_get(repo, f"git/commits/{head['sha']}", token)
    tree = commit.get("tree") if isinstance(commit, dict) else None
    stored_bridge = evidence.get("promotion_bridge")
    delivery_branch = (
        str(stored_bridge["source_ref"])
        if isinstance(stored_bridge, dict)
        and isinstance(stored_bridge.get("source_ref"), str)
        else str(head["ref"])
        if route.get("kind") in {"milestone", "isolated"}
        else None
    )
    freshness_sha = promotion_freshness_sha(str(head["sha"]), stored_bridge)
    main_evidence = (
        promotion_main_evidence(
            promotion_api(repo, token),
            repo,
            current_main_sha,
            str(base["sha"]),
            delivery_branch,
            freshness_sha,
            contains_commit(str(base["sha"]), freshness_sha),
        )
        if isinstance(current_main_sha, str)
        else None
    )
    if (
        current_main_sha != evidence.get("base_sha")
        or not isinstance(tree, dict)
        or tree.get("sha") != evidence.get("candidate_tree")
        or main_evidence is None
        or evidence.get("main_sync") != main_evidence
        or git_output("status", "--porcelain")
        or git_output("rev-parse", "HEAD") != head["sha"]
        or git_output("rev-parse", "HEAD^{tree}")
        != evidence.get("candidate_tree")
    ):
        raise RuntimeError("Live promotion base, tree, or checkout changed")
    archive = evidence.get("candidate_archive") or {}
    try:
        archive_mode = os.lstat(safe_destination(args.archive)).st_mode
    except FileNotFoundError as error:
        raise RuntimeError("Candidate archive is missing") from error
    if (
        not stat.S_ISREG(archive_mode)
        or archive.get("name") != args.archive.name
        or sha256(args.archive) != archive.get("sha256")
    ):
        raise RuntimeError("Candidate archive does not match evidence")
    with tempfile.TemporaryDirectory(dir=args.archive.parent) as directory:
        rebuilt = Path(directory) / args.archive.name
        atomic_output(
            rebuilt,
            lambda stream: subprocess.run(  # noqa: S603
                [
                    shutil.which("git") or "git",
                    "archive",
                    "--format=tar.gz",
                    str(head["sha"]),
                ],
                check=True,
                stdout=stream,
            ),
        )
        if sha256(rebuilt) != archive.get("sha256"):
            raise RuntimeError("Candidate archive cannot be reproduced")
    require_same_preflight(
        evidence, rebuild_quota_preflight(evidence, pull, args, token)
    )
    run_urls = sorted(args.blocked_run_url)
    run_ids: list[int] = []
    for url in run_urls:
        require_run_url(url, repo)
        run_ids.append(int(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]))
    query = urllib.parse.urlencode(
        {"event": "pull_request", "head_sha": head["sha"]}
    )
    failed_ids: set[int] = set()
    page = 1
    total: int | None = None
    seen = 0
    while total is None or seen < total:
        payload = github_get(
            repo,
            f"actions/runs?{query}&per_page=100&page={page}",
            token,
        )
        runs = (
            payload.get("workflow_runs") if isinstance(payload, dict) else None
        )
        count = (
            payload.get("total_count") if isinstance(payload, dict) else None
        )
        if not isinstance(runs, list) or not isinstance(count, int):
            raise RuntimeError("Pull-request run list is incomplete")
        if total is not None and count != total:
            raise RuntimeError(
                "Pull-request run count changed during pagination"
            )
        total = count
        seen += len(runs)
        failed_ids.update(
            int(run["id"])
            for run in runs
            if isinstance(run, dict)
            and isinstance(run.get("id"), int)
            and run.get("conclusion") == "failure"
        )
        if any(
            not isinstance(run, dict)
            or run.get("status") != "completed"
            or run.get("conclusion")
            not in {"success", "skipped", "neutral", "failure"}
            for run in runs
        ):
            raise RuntimeError("A pull-request run has a non-quota failure")
        if not runs and seen < total:
            raise RuntimeError("Pull-request run list is incomplete")
        if len(runs) < 100:
            break
        page += 1
    if seen != total:
        raise RuntimeError("Pull-request run list is incomplete")
    if (
        not failed_ids
        or set(run_ids) != failed_ids
        or len(run_ids) != len(set(run_ids))
    ):
        raise RuntimeError(
            "Blocked URLs must cover every failed pull-request run"
        )
    paths = {
        require_zero_step_run(
            url,
            repo,
            pr_number,
            str(head["ref"]),
            str(head["sha"]),
            token,
        )
        for url in run_urls
    }
    if not REQUIRED_QUOTA_WORKFLOWS.issubset(paths):
        raise RuntimeError(
            "Required CI and promotion runs are not both blocked"
        )
    if not validate_comments:
        return {}, {}
    attestation = require_comment_url(
        args.attestation_url,
        repo,
        pr_number,
        fallback_statement("attestation", evidence, run_urls),
        token,
    )
    authorization = require_comment_url(
        args.authorization_url,
        repo,
        pr_number,
        fallback_statement("authorization", evidence, run_urls),
        token,
    )
    return attestation, authorization


def prepare(args: argparse.Namespace) -> None:  # noqa: C901
    """Validate promotion prerequisites and create the candidate bundle."""
    require_distinct_paths(args.archive, args.output)
    event = json.loads(args.event_path.read_text(encoding="utf-8"))
    evidence: dict[str, object]
    if args.event != "pull_request":
        route = Route("merge-queue", False)
        canary = classify_canary("", "")
        evidence = {"schema_version": 1, "route": asdict(route)}
    else:
        pull_request = event["pull_request"]
        labels = {
            item["name"]
            for item in pull_request.get("labels", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        base = pull_request["base"]["ref"]
        head = pull_request["head"]["ref"]
        route = route_for(base, head, labels, args.branch_strategy)
        canary = classify_canary(args.canary_command, args.canary_environment)
        evidence = {"schema_version": 1, "route": asdict(route)}
        if route.kind == "invalid-main-route":
            raise RuntimeError(
                "Only a promotion, hotfix, release recovery, or release "
                "follow-up may target main"
            )
        if route.relevant:
            if not same_repository(pull_request, args.repo):
                raise RuntimeError(
                    "Promotion, hotfix, and recovery branches must come from "
                    "this repository"
                )
            title = pull_request.get("title")
            body = pull_request.get("body") or ""
            if not isinstance(title, str) or not isinstance(body, str):
                raise RuntimeError(
                    "Promotion pull request metadata is incomplete"
                )
            number = issue_number(body)
            if number is None:
                raise RuntimeError(
                    "Promotion pull request must close its tracking Issue"
                )
            token = os.environ.get("GH_TOKEN", "")
            tracking_issue_state: dict[str, object] | None = None
            checkpoint: list[int] | None = None
            if number is not None:
                issue = github_get(args.repo, f"issues/{number}", token)
                if not isinstance(issue, dict) or issue.get("state") != "open":
                    raise RuntimeError(
                        "Promotion tracking Issue must exist and remain open"
                    )
                issue_body = issue.get("body") or ""
                if not isinstance(issue_body, str):
                    raise RuntimeError(
                        "Promotion tracking Issue metadata is incomplete"
                    )
                issue_title = str(issue.get("title") or "")
                if UNCHECKED.search(issue_body):
                    raise RuntimeError(
                        "Promotion Issue has unchecked acceptance criteria"
                    )
                tracking_labels = issue_labels(issue)
                if (
                    route.kind in {"milestone", "isolated"}
                    and "promotion" not in tracking_labels
                ):
                    raise RuntimeError(
                        "Promotion tracking Issue must use the promotion label"
                    )
                issue_milestone = (issue.get("milestone") or {}).get("number")
                if (
                    route.kind == "milestone"
                    and issue_milestone != route.milestone
                ):
                    raise RuntimeError(
                        "Promotion Issue and delivery branch Milestones differ"
                    )
                if route.kind == "isolated" and number != route.issue:
                    raise RuntimeError(
                        "Isolated delivery branch and Issue numbers differ"
                    )
                if route.kind == "release-recovery" and number != route.issue:
                    raise RuntimeError(
                        "Release recovery branch and Issue numbers differ"
                    )
                if (
                    route.kind not in {"milestone", "release-recovery"}
                    and issue_milestone is not None
                ):
                    raise RuntimeError(
                        "Standalone promotion or hotfix cannot use a Milestone"
                    )
                checkpoint = checkpoint_issue_numbers(issue_body)
                if checkpoint is not None and route.kind != "milestone":
                    raise RuntimeError(
                        "Checkpoint promotion requires a Milestone route"
                    )
                tracking_issue_state = {
                    "number": number,
                    "state": "open",
                    "title": issue_title,
                    "body_sha256": hashlib.sha256(
                        issue_body.encode()
                    ).hexdigest(),
                    "labels": sorted(tracking_labels),
                    "milestone": issue_milestone,
                }
            included: list[dict[str, object]] = []
            milestone_issue_snapshot: list[dict[str, Any]] = []
            if route.milestone is not None:
                if number is None:
                    raise RuntimeError(
                        "Milestone promotion requires a tracking Issue"
                    )
                milestone_issue_snapshot = milestone_issues(
                    args.repo, route.milestone, token
                )
            current_main = github_get(args.repo, "git/ref/heads/main", token)
            if not isinstance(current_main, dict):
                raise RuntimeError("GitHub returned an invalid main reference")
            main_object = current_main.get("object")
            current_main_sha = (
                main_object.get("sha")
                if isinstance(main_object, dict)
                else None
            )
            base_sha = pull_request["base"]["sha"]
            head_sha = pull_request["head"]["sha"]
            if not isinstance(current_main_sha, str):
                raise RuntimeError("GitHub returned an invalid main reference")
            bridge = promotion_bridge_source(
                args.repo,
                head,
                base_sha,
                head_sha,
                args.candidate_sha,
                route.milestone,
                token,
            )
            delivery_branch = (
                str(bridge["source_ref"])
                if bridge is not None
                else head
                if route.kind in {"milestone", "isolated"}
                else None
            )
            freshness_sha = promotion_freshness_sha(head_sha, bridge)
            main_evidence = promotion_main_evidence(
                promotion_api(args.repo, token),
                args.repo,
                current_main_sha,
                base_sha,
                delivery_branch,
                freshness_sha,
                contains_commit(base_sha, freshness_sha),
            )
            if main_evidence is None:
                raise RuntimeError(
                    "Delivery branch must contain current main before promotion"
                )
            if route.kind in {"hotfix", "isolated", "release-recovery"}:
                included_prs = [
                    {
                        "number": pull_request["number"],
                        "title": title,
                        "intent": release_intent(title),
                        "issue": number,
                    }
                ]
            else:
                included_prs = included_pull_requests(
                    args.repo,
                    base_sha,
                    head_sha,
                    str(bridge["source_ref"]) if bridge is not None else head,
                    token,
                    route.milestone if bridge is not None else None,
                    head_sha if bridge is not None else None,
                    track_work_issues=route.milestone is not None,
                )
                if not included_prs:
                    raise RuntimeError(
                        "Delivery promotion contains no merged pull requests"
                    )
            if route.milestone is not None and number is not None:
                included = milestone_included_issues(
                    milestone_issue_snapshot,
                    number,
                    included_prs,
                    checkpoint,
                )
            elif (
                route.kind in {"isolated", "release-recovery"}
                and number is not None
            ):
                included = [
                    {
                        "number": number,
                        "title": tracking_issue_state["title"]
                        if tracking_issue_state is not None
                        else "",
                    }
                ]
            intent = highest_release_intent(
                [str(item["title"]) for item in included_prs]
            )
            promotion_intent = release_intent(title)
            if promotion_intent != intent:
                raise RuntimeError(
                    "Promotion pull-request title must declare the batch's "
                    f"highest SemVer intent ({intent})"
                )
            candidate_sha = args.candidate_sha
            candidate_tree = git_output(
                "rev-parse", f"{candidate_sha}^{{tree}}"
            )
            atomic_output(
                args.archive,
                lambda stream: subprocess.run(  # noqa: S603
                    [
                        shutil.which("git") or "git",
                        "archive",
                        "--format=tar.gz",
                        candidate_sha,
                    ],
                    check=True,
                    stdout=stream,
                ),
            )
            milestone_promotion = None
            if route.milestone is not None:
                mode = "checkpoint" if checkpoint is not None else "final"
                milestone_promotion = {
                    "mode": mode,
                    "declared_issues": checkpoint,
                }
            evidence = {
                "schema_version": 1,
                "repository": args.repo,
                "route": asdict(route),
                "pull_request": pull_request["number"],
                "promotion_pull_request": {
                    "number": pull_request["number"],
                    "title": title,
                    "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "closing_issue": number,
                    "labels": sorted(labels),
                },
                "tracking_issue": number,
                "tracking_issue_state": tracking_issue_state,
                "base_ref": base,
                "base_sha": base_sha,
                "head_ref": head,
                "head_sha": head_sha,
                "main_sync": main_evidence,
                "promotion_bridge": bridge,
                "candidate_sha": candidate_sha,
                "candidate_tree": candidate_tree,
                "candidate_archive": {
                    "name": args.archive.name,
                    "sha256": sha256(args.archive),
                },
                "included_issues": included,
                "release": {
                    "intent": intent,
                    "promotion_title": title,
                    "included_pull_requests": included_prs,
                },
                "canary": asdict(canary),
                "workflow_run": args.workflow_run,
                "created_at": datetime.now(UTC).isoformat(),
            }
            if milestone_promotion is not None:
                evidence["milestone_promotion"] = milestone_promotion
    write_evidence(args.output, evidence)
    write_outputs(
        args.github_output,
        {
            "relevant": route.relevant,
            "kind": route.kind,
            "canary_state": canary.state,
            "canary_environment": canary.environment or "",
            "pr_number": event.get("number", "none"),
            "candidate_sha": args.candidate_sha,
            "head_sha": (event.get("pull_request") or {})
            .get("head", {})
            .get("sha", "none"),
        },
    )
    write_summary(
        args.summary,
        [
            "## Promotion preflight",
            "",
            f"- Route: `{route.kind}`",
            f"- Canary capability: `{canary.state}` — {canary.reason}",
        ],
    )


def finalize(args: argparse.Namespace) -> None:
    """Record canary outcome and the peer full-CI gate."""
    evidence = json.loads(args.input.read_text(encoding="utf-8"))
    canary = evidence.get("canary", {})
    state = canary.get("state")
    if state == "allowed" and args.canary_result != "success":
        raise RuntimeError("Configured canary did not succeed")
    if state not in {"allowed", "blocked", "unknown"}:
        raise RuntimeError("Promotion evidence has an invalid canary state")
    canary["result"] = "passed" if state == "allowed" else "artifact-only"
    evidence["full_check"] = {
        "context": "verify",
        "status": "required-peer-check",
    }
    evidence["gate"] = "passed"
    write_evidence(args.output, evidence)


def note_quota_fallback(args: argparse.Namespace) -> None:
    """Print a routine PR's quota fallback note after proving zero-step."""
    if not args.blocked_run_url:
        raise RuntimeError("At least one blocked Actions run is required")
    token = os.environ.get("GH_TOKEN", "")
    pull = github_get(args.repo, f"pulls/{args.pr}", token)
    base = pull.get("base") if isinstance(pull, dict) else None
    head = pull.get("head") if isinstance(pull, dict) else None
    if (
        not isinstance(pull, dict)
        or pull.get("number") != args.pr
        or pull.get("state") != "open"
        or pull.get("merged") is not False
        or not isinstance(base, dict)
        or not isinstance(head, dict)
        or not same_repository(pull, args.repo)
    ):
        raise RuntimeError("Pull request identity could not be resolved")
    head_sha = str(head.get("sha") or "")
    head_ref = str(head.get("ref") or "")
    if not head_sha or not head_ref:
        raise RuntimeError("Pull request head is incomplete")
    labels = {
        item["name"]
        for item in pull.get("labels", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    route = route_for(
        str(base.get("ref") or ""),
        str(head.get("ref") or ""),
        labels,
        args.branch_strategy,
    )
    base_ref = str(base.get("ref") or "")
    if route.kind != "not-applicable" or (
        base_ref == "main"
        and (
            MILESTONE_BRANCH.fullmatch(head_ref)
            or PROMOTION_BRIDGE.fullmatch(head_ref)
            or head_ref.startswith(("release-please--", "release/v"))
            or bool(labels & {"promotion", "hotfix", "release-recovery"})
        )
    ):
        raise RuntimeError(
            "Routine quota fallback only applies to non-promotion pull requests"
        )
    if git_output("status", "--porcelain"):
        raise RuntimeError("Routine quota fallback requires a clean worktree")
    if git_output("rev-parse", "HEAD") != head_sha:
        raise RuntimeError("Worktree HEAD must equal the pull request head")
    blocked_run_urls = failed_pull_request_run_urls(args.repo, head_sha, token)
    if set(args.blocked_run_url) != set(blocked_run_urls):
        raise RuntimeError(
            "Blocked run URLs must exactly match every live failed check"
        )
    for url in blocked_run_urls:
        require_run_url(url, args.repo)
        require_zero_step_run(
            url, args.repo, args.pr, head_ref, head_sha, token
        )
    sys.stdout.write(
        quota_fallback_note(
            args.repo, args.pr, head_sha, sorted(args.blocked_run_url)
        )
    )


def finalize_quota_fallback(args: argparse.Namespace) -> None:  # noqa: C901
    """Record a non-release promotion gate from exact local evidence."""
    require_distinct_paths(args.input, args.output, args.archive)
    evidence = json.loads(args.input.read_text(encoding="utf-8"))
    required = (
        "repository",
        "pull_request",
        "base_sha",
        "head_sha",
        "candidate_sha",
        "candidate_tree",
        "candidate_archive",
    )
    if any(not evidence.get(field) for field in required):
        raise RuntimeError("Promotion preflight evidence is incomplete")
    if (evidence.get("route") or {}).get("kind") not in {
        "milestone",
        "isolated",
    }:
        raise RuntimeError("Quota fallback only applies to a promotion gate")
    if evidence["candidate_sha"] != evidence["head_sha"]:
        raise RuntimeError("Local candidate must equal the pull request head")
    if (evidence.get("canary") or {}).get("state") == "allowed":
        raise RuntimeError("Quota fallback cannot replace a configured canary")
    if evidence.get("gate") is not None:
        raise RuntimeError("Quota fallback evidence was already finalized")
    if git_output("status", "--porcelain"):
        raise RuntimeError("Quota fallback requires a clean worktree")
    if git_output("rev-parse", "HEAD") != evidence["head_sha"]:
        raise RuntimeError("Worktree HEAD must equal the pull request head")

    repo = str(evidence["repository"])
    token = os.environ.get("GH_TOKEN", "")
    current_main = github_get(repo, "git/ref/heads/main", token)
    main_object = (
        current_main.get("object") if isinstance(current_main, dict) else None
    )
    current_main_sha = (
        main_object.get("sha") if isinstance(main_object, dict) else None
    )
    route_kind = (evidence.get("route") or {}).get("kind")
    route_milestone = (evidence.get("route") or {}).get("milestone")
    head_ref = evidence.get("head_ref")
    bridge = (
        promotion_bridge_source(
            repo,
            head_ref,
            str(evidence["base_sha"]),
            str(evidence["head_sha"]),
            str(evidence["candidate_sha"]),
            route_milestone if isinstance(route_milestone, int) else None,
            token,
        )
        if isinstance(head_ref, str)
        else None
    )
    if evidence.get("promotion_bridge") != bridge:
        raise RuntimeError("Promotion bridge evidence changed after preflight")
    delivery_branch = (
        str(bridge["source_ref"])
        if bridge is not None
        else head_ref
        if isinstance(head_ref, str) and route_kind in {"milestone", "isolated"}
        else None
    )
    freshness_sha = promotion_freshness_sha(str(evidence["head_sha"]), bridge)
    live_main_evidence = (
        promotion_main_evidence(
            promotion_api(repo, token),
            repo,
            current_main_sha,
            str(evidence["base_sha"]),
            delivery_branch,
            freshness_sha,
            contains_commit(str(evidence["base_sha"]), freshness_sha),
        )
        if isinstance(current_main_sha, str)
        else None
    )
    if live_main_evidence is None:
        raise RuntimeError("Promotion base or ancestry changed after preflight")
    if args.attestation_url == args.authorization_url:
        raise RuntimeError(
            "Attestation and authorization must be separate comments"
        )
    if not args.blocked_run_url:
        raise RuntimeError("At least one blocked Actions run is required")
    token = os.environ.get("GH_TOKEN", "")
    validate_quota_preflight(evidence, args, token, validate_comments=False)
    attestation, authorization = validate_quota_preflight(evidence, args, token)
    verification_command = local_verification_command()
    subprocess.run(verification_command, check=True)  # noqa: S603
    validate_quota_preflight(evidence, args, token)

    evidence["canary"]["result"] = "artifact-only"
    evidence["full_check"] = {
        "context": "verify",
        "status": "local-quota-attested",
        "commands": [verification_command[0], PREFLIGHT_REFETCH],
    }
    evidence["quota_fallback"] = {
        "attestation_url": args.attestation_url,
        "authorization_url": args.authorization_url,
        "attestation_author": attestation["user"]["login"],
        "authorization_author": authorization["user"]["login"],
        "blocked_run_urls": sorted(args.blocked_run_url),
        "created_at": datetime.now(UTC).isoformat(),
    }
    evidence["gate"] = "quota-fallback"
    evidence["release_eligible"] = False
    write_evidence(args.output, evidence)


def verify_main(args: argparse.Namespace) -> None:
    """Prove the merged main tree is the candidate that passed both gates."""
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    checks = json.loads(args.checks.read_text(encoding="utf-8"))
    if evidence.get("gate") != "passed":
        raise RuntimeError("Promotion gate evidence is incomplete")
    expected = {
        "repository": args.repo,
        "pull_request": args.pr_number,
        "head_sha": args.head_sha,
    }
    for field, value in expected.items():
        if evidence.get(field) != value:
            raise RuntimeError(
                f"Promotion evidence {field} does not match main"
            )
    current_tree = git_output("rev-parse", f"{args.main_sha}^{{tree}}")
    if current_tree != evidence.get("candidate_tree"):
        raise RuntimeError(
            "Merged main tree differs from the verified candidate tree"
        )
    check_runs = (
        checks.get("check_runs", []) if isinstance(checks, dict) else []
    )
    if not any(
        item.get("name") == "verify" and item.get("conclusion") == "success"
        for item in check_runs
        if isinstance(item, dict)
    ):
        raise RuntimeError("Candidate has no successful verify check")
    evidence["post_merge"] = {
        "main_sha": args.main_sha,
        "main_tree": current_tree,
        "tree_identity": "verified",
        "verified_at": datetime.now(UTC).isoformat(),
    }
    write_evidence(args.output, evidence)


def verify_quota_main(args: argparse.Namespace) -> None:  # noqa: C901
    """Verify main tree identity without converting fallback into CI success."""
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    if (
        evidence.get("gate") != "quota-fallback"
        or evidence.get("release_eligible") is not False
        or (evidence.get("full_check") or {}).get("status")
        != "local-quota-attested"
    ):
        raise RuntimeError("Promotion quota fallback evidence is incomplete")
    canary = evidence.get("canary")
    if (
        not isinstance(canary, dict)
        or canary.get("state") not in {"blocked", "unknown"}
        or canary.get("result") != "artifact-only"
    ):
        raise RuntimeError(
            "Promotion quota fallback canary evidence is invalid"
        )
    if evidence.get("post_merge") is not None:
        raise RuntimeError("Promotion quota fallback was already verified")
    expected = {
        "repository": args.repo,
        "pull_request": args.pr_number,
        "head_sha": args.head_sha,
    }
    for field, value in expected.items():
        if evidence.get(field) != value:
            raise RuntimeError(f"Fallback evidence {field} does not match main")
    token = os.environ.get("GH_TOKEN", "")
    repository = github_get(args.repo, "", token)
    current_main = github_get(args.repo, "git/ref/heads/main", token)
    main_object = (
        current_main.get("object") if isinstance(current_main, dict) else None
    )
    main_sha = (
        str(main_object.get("sha")) if isinstance(main_object, dict) else ""
    )
    pull = github_get(args.repo, f"pulls/{args.pr_number}", token)
    base = pull.get("base") if isinstance(pull, dict) else None
    head = pull.get("head") if isinstance(pull, dict) else None
    if (
        not isinstance(repository, dict)
        or repository.get("full_name") != args.repo
        or repository.get("archived") is not False
        or repository.get("default_branch") != "main"
        or main_sha != args.main_sha
        or not isinstance(pull, dict)
        or pull.get("number") != args.pr_number
        or pull.get("state") != "closed"
        or pull.get("merged") is not True
        or not pull.get("merged_at")
        or pull.get("merge_commit_sha") != main_sha
        or not isinstance(base, dict)
        or base.get("ref") != "main"
        or base.get("sha") != evidence.get("base_sha")
        or not isinstance(head, dict)
        or head.get("ref") != evidence.get("head_ref")
        or head.get("sha") != evidence.get("head_sha")
        or not same_repository(pull, args.repo)
    ):
        raise RuntimeError("Live merged promotion does not match evidence")
    commit = github_get(args.repo, f"git/commits/{main_sha}", token)
    tree = commit.get("tree") if isinstance(commit, dict) else None
    parents = commit.get("parents") if isinstance(commit, dict) else None
    if (
        not isinstance(tree, dict)
        or tree.get("sha") != evidence.get("candidate_tree")
        or not isinstance(parents, list)
        or len(parents) != 1
        or not isinstance(parents[0], dict)
        or parents[0].get("sha") != evidence.get("base_sha")
        or main_sha == evidence.get("head_sha")
    ):
        raise RuntimeError("Main is not the exact squash-merged candidate tree")
    sources: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = github_get(
            args.repo,
            f"commits/{main_sha}/pulls?per_page=100&page={page}",
            token,
        )
        if not isinstance(payload, list):
            raise RuntimeError("Main source pull-request list is incomplete")
        sources.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            break
        page += 1
    exact_sources = [
        item
        for item in sources
        if item.get("merge_commit_sha") == main_sha
        and item.get("merged_at")
        and isinstance(item.get("base"), dict)
        and item["base"].get("ref") == "main"
    ]
    if (
        len(exact_sources) != 1
        or exact_sources[0].get("number") != args.pr_number
    ):
        raise RuntimeError("Main commit has no unique promotion source")
    quota = evidence.get("quota_fallback") or {}
    run_urls = quota.get("blocked_run_urls")
    if not isinstance(run_urls, list) or any(
        not isinstance(url, str) for url in run_urls
    ):
        raise RuntimeError("Fallback evidence has no blocked-run binding")
    require_comment_url(
        str(quota.get("attestation_url", "")),
        args.repo,
        args.pr_number,
        fallback_statement("attestation", evidence, run_urls),
        token,
    )
    require_comment_url(
        str(quota.get("authorization_url", "")),
        args.repo,
        args.pr_number,
        fallback_statement("authorization", evidence, run_urls),
        token,
    )
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git is required")
    subprocess.run(  # noqa: S603
        [executable, "fetch", "--quiet", "origin", "main"], check=True
    )
    if git_output("status", "--porcelain"):
        raise RuntimeError("Main verification requires a clean worktree")
    if (
        git_output("rev-parse", "refs/remotes/origin/main") != main_sha
        or git_output("rev-parse", "HEAD") != main_sha
    ):
        raise RuntimeError(
            "Local checkout and origin/main must equal merged main"
        )
    current_tree = git_output("rev-parse", f"{main_sha}^{{tree}}")
    if current_tree != evidence.get("candidate_tree"):
        raise RuntimeError(
            "Merged main tree differs from the verified candidate tree"
        )
    evidence["post_merge"] = {
        "main_sha": main_sha,
        "main_tree": current_tree,
        "tree_identity": "verified-local-quota-fallback",
        "verified_at": datetime.now(UTC).isoformat(),
    }
    write_evidence(args.output, evidence)


def parser() -> argparse.ArgumentParser:
    """Build the command line interface."""
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    intent_command = commands.add_parser("check-intent")
    intent_command.add_argument("--title", required=True)
    intent_command.add_argument("--repo")
    intent_command.add_argument("--base-sha")
    intent_command.add_argument("--head-sha")
    intent_command.add_argument("--delivery-branch")
    intent_command.add_argument("--milestone", type=int)
    intent_command.add_argument("--bridge-head-sha")
    intent_command.add_argument("--titles-json")
    intent_command.set_defaults(handler=check_promotion_intent)
    prepare_command = commands.add_parser("prepare")
    prepare_command.add_argument("--event", required=True)
    prepare_command.add_argument("--event-path", type=Path, required=True)
    prepare_command.add_argument("--repo", required=True)
    prepare_command.add_argument(
        "--branch-strategy", choices=("main", "delivery"), required=True
    )
    prepare_command.add_argument("--candidate-sha", required=True)
    prepare_command.add_argument("--workflow-run", required=True)
    prepare_command.add_argument("--canary-command", default="")
    prepare_command.add_argument("--canary-environment", default="")
    prepare_command.add_argument("--archive", type=Path, required=True)
    prepare_command.add_argument("--output", type=Path, required=True)
    prepare_command.add_argument("--github-output", type=Path)
    prepare_command.add_argument("--summary", type=Path)
    prepare_command.set_defaults(handler=prepare)

    finalize_command = commands.add_parser("finalize")
    finalize_command.add_argument("--input", type=Path, required=True)
    finalize_command.add_argument("--output", type=Path, required=True)
    finalize_command.add_argument("--canary-result", required=True)
    finalize_command.set_defaults(handler=finalize)

    fallback_command = commands.add_parser("finalize-quota-fallback")
    fallback_command.add_argument("--input", type=Path, required=True)
    fallback_command.add_argument("--output", type=Path, required=True)
    fallback_command.add_argument("--archive", type=Path, required=True)
    fallback_command.add_argument("--attestation-url", required=True)
    fallback_command.add_argument("--authorization-url", required=True)
    fallback_command.add_argument(
        "--blocked-run-url", action="append", default=[]
    )
    fallback_command.set_defaults(handler=finalize_quota_fallback)

    note_command = commands.add_parser("note-quota-fallback")
    note_command.add_argument("--repo", required=True)
    note_command.add_argument("--pr", type=int, required=True)
    note_command.add_argument(
        "--branch-strategy", choices=("main", "delivery"), required=True
    )
    note_command.add_argument("--blocked-run-url", action="append", default=[])
    note_command.set_defaults(handler=note_quota_fallback)

    verify_command = commands.add_parser("verify-main")
    verify_command.add_argument("--repo", required=True)
    verify_command.add_argument("--pr-number", type=int, required=True)
    verify_command.add_argument("--head-sha", required=True)
    verify_command.add_argument("--main-sha", required=True)
    verify_command.add_argument("--evidence", type=Path, required=True)
    verify_command.add_argument("--checks", type=Path, required=True)
    verify_command.add_argument("--output", type=Path, required=True)
    verify_command.set_defaults(handler=verify_main)

    fallback_verify_command = commands.add_parser("verify-quota-main")
    fallback_verify_command.add_argument("--repo", required=True)
    fallback_verify_command.add_argument("--pr-number", type=int, required=True)
    fallback_verify_command.add_argument("--head-sha", required=True)
    fallback_verify_command.add_argument("--main-sha", required=True)
    fallback_verify_command.add_argument("--evidence", type=Path, required=True)
    fallback_verify_command.add_argument("--output", type=Path, required=True)
    fallback_verify_command.set_defaults(handler=verify_quota_main)
    return root


def main() -> None:
    """Run the selected promotion evidence operation."""
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
