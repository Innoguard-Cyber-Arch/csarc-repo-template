#!/usr/bin/env python3
"""Create and verify delivery-promotion evidence."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    csarc_config = importlib.import_module("csarc_config")
    delivery_sync = importlib.import_module("delivery_sync")
else:
    csarc_config = importlib.import_module(f"{__package__}.csarc_config")
    delivery_sync = importlib.import_module(f"{__package__}.delivery_sync")

CLOSING_ISSUE = re.compile(
    r"(?<!\w)(?a:Closes|Fixes|Resolves)[ \t]+#([1-9][0-9]*)(?!\w)",
    re.IGNORECASE,
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


def check_route(args: argparse.Namespace) -> None:
    """Report the `promotion` required check for one ordinary pull request.

    Every pull request into `main` needs an explicit `promotion` check-run
    so `.csarc/policies/rulesets-required-checks.json`'s
    `required_status_checks`
    never stays permanently pending for it. A `not-applicable` or a
    recognized promotion route (milestone, isolated, hotfix, release
    recovery, release follow-up, or a merge-queue re-check) succeeds;
    only a `main`-targeting branch that matches none of those routes
    fails closed. This intentionally reuses `route_for()` rather than
    reimplementing branch/label classification, so this check and the
    `prepare()` evidence pipeline it feeds can never disagree silently.
    """
    if args.event != "pull_request":
        # A merge-queue commit was already classified when its source pull
        # request opened; `prepare()` uses the identical fallback for the
        # same reason.
        route = Route("merge-queue", False)
    else:
        event = json.loads(args.event_path.read_text(encoding="utf-8"))
        pull_request = event["pull_request"]
        labels = {
            item["name"]
            for item in pull_request.get("labels", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        base = pull_request["base"]["ref"]
        head = pull_request["head"]["ref"]
        route = route_for(base, head, labels, args.branch_strategy)
    write_outputs(
        args.github_output,
        {"route": route.kind, "relevant": route.relevant},
    )
    if route.kind == "invalid-main-route":
        write_summary(
            args.summary,
            ["- Promotion route — blocked: no recognized route targets `main`"],
        )
        raise RuntimeError(
            "Only a promotion, hotfix, release recovery, or release "
            "follow-up branch/label combination may target main; use a "
            "type/<issue-number>-short-slug topic branch or the matching "
            "promotion route. This check is read-only; GitHub closes an "
            "open pull request when its head branch is renamed"
        )
    write_summary(args.summary, [f"- Promotion route — {route.kind}"])
    print(f"Promotion route: {route.kind}")  # noqa: T201


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


def promotion_api(repo: str, token: str) -> DeliveryAPI:
    """Use the workflow token or the existing authenticated CLI session."""
    return delivery_sync.GitHubAPI(token) if token else GitHubCLIAPI(repo)


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
    route_command = commands.add_parser("check-route")
    route_command.add_argument("--event", required=True)
    route_command.add_argument("--event-path", type=Path, required=True)
    route_command.add_argument(
        "--branch-strategy", choices=("main", "delivery"), required=True
    )
    route_command.add_argument("--github-output", type=Path)
    route_command.add_argument("--summary", type=Path)
    route_command.set_defaults(handler=check_route)
    return root


def main() -> None:
    """Run the selected promotion evidence operation."""
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
