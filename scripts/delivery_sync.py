#!/usr/bin/env python3
"""Synchronize one authorized Milestone delivery at its actual boundary."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

DELIVERY_BRANCH = re.compile(r"^dev/m([0-9]+)-[a-z0-9][a-z0-9-]*$")
ISOLATED_BRANCH = re.compile(r"^dev/i([0-9]+)-[a-z0-9][a-z0-9-]*$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CAPABILITY_STATES = {"allowed", "blocked", "unknown"}
MERGE_QUEUE_REF = re.compile(
    r"^refs/heads/gh-readonly-queue/main/pr-([1-9][0-9]*)-[A-Za-z0-9_-]+$"
)


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


class GitHubAPI:
    """Small GitHub REST client used by the synchronization workflow."""

    def __init__(
        self, token: str, base_url: str = "https://api.github.com"
    ) -> None:
        """Create a client restricted to an HTTPS API origin."""
        if urllib.parse.urlparse(base_url).scheme != "https":
            raise ValueError("GitHub API URL must use HTTPS")
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(RejectRedirects())

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, Any]:
        """Return the HTTP status and decoded response without retrying."""
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(  # noqa: S310
            f"{self.base_url}/{path.lstrip('/')}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                body = response.read().decode()
                return response.status, json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            body = error.read().decode()
            try:
                decoded: Any = json.loads(body) if body else None
            except json.JSONDecodeError:
                decoded = body
            return error.code, decoded
        except (OSError, TimeoutError) as error:
            return 0, {"message": str(error)}


@dataclass(frozen=True)
class DeliveryState:
    """One requested delivery branch compared with the current main SHA."""

    branch: str
    sha: str
    current: bool
    compare_status: str


class API(Protocol):
    """Describe the REST method required by synchronization decisions."""

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, Any]:
        """Return an HTTP status and decoded response."""
        ...


def issue_labels(payload: dict[str, Any]) -> set[str]:
    """Return the well-formed labels on a live pull request."""
    values = payload.get("labels")
    if not isinstance(values, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("name"), str)
        for item in values
    ):
        raise RuntimeError("GitHub returned invalid pull request labels")
    return {str(item["name"]) for item in values}


def require_response(status: int, payload: object, operation: str) -> object:
    """Return a successful API response or fail with concrete evidence."""
    if 200 <= status < 300:
        return payload
    raise RuntimeError(f"{operation} failed with HTTP {status}: {payload}")


def includes_main(compare_status: str) -> bool:
    """Return whether the compared head contains the selected main commit."""
    return compare_status in {"ahead", "identical"}


def capability_state(status: int) -> str:
    """Map a non-mutating validation probe to the shared tri-state model."""
    if status == 422:
        return "allowed"
    if status in {401, 403, 409}:
        return "blocked"
    return "unknown"


def select_auto_mode(
    requested: bool,
    external_token: bool,
    pull_request_capability: str,
    contents_capability: str,
) -> str:
    """Enable automation only with an external token and proven capabilities."""
    if {pull_request_capability, contents_capability} - CAPABILITY_STATES:
        raise ValueError("invalid capability state")
    if not requested:
        return "manual"
    if not external_token:
        return "manual"
    if pull_request_capability == contents_capability == "allowed":
        return "automatic"
    return "manual"


def compare(api: API, repo: str, main_sha: str, head_sha: str) -> str:
    """Compare a head commit with the exact main commit from this event."""
    status, payload = api.request(
        "GET",
        f"repos/{repo}/compare/{urllib.parse.quote(main_sha, safe='')}..."
        f"{urllib.parse.quote(head_sha, safe='')}",
    )
    data = require_response(status, payload, "compare main with delivery head")
    compare_status = data.get("status") if isinstance(data, dict) else None
    if not isinstance(compare_status, str):
        raise RuntimeError("GitHub returned an invalid compare response")
    return compare_status


def read_main_sha(api: API, repo: str) -> str:
    """Read the current main commit."""
    status, payload = api.request("GET", f"repos/{repo}/git/ref/heads/main")
    data = require_response(status, payload, "read main")
    main_sha = (
        data.get("object", {}).get("sha") if isinstance(data, dict) else None
    )
    if not isinstance(main_sha, str):
        raise RuntimeError("GitHub returned an invalid main ref")
    return main_sha


def merged_sync_pr_number(
    api: API,
    repo: str,
    delivery_branch: str,
    main_sha: str,
    proposed_head_sha: str,
) -> int | None:
    """Return a merged squash sync PR whose commit is in the proposed head."""
    sync_branch = sync_branch_name(delivery_branch, main_sha)
    owner = repo.split("/", 1)[0]
    query = urllib.parse.urlencode(
        {
            "state": "closed",
            "head": f"{owner}:{sync_branch}",
            "base": delivery_branch,
            "per_page": 100,
        }
    )
    status, payload = api.request("GET", f"repos/{repo}/pulls?{query}")
    pulls = require_response(status, payload, "find merged sync PR")
    if not isinstance(pulls, list):
        raise RuntimeError("GitHub returned invalid sync pull request state")
    for pull in pulls:
        if not isinstance(pull, dict):
            continue
        base = pull.get("base")
        head = pull.get("head")
        number = pull.get("number")
        merge_sha = pull.get("merge_commit_sha")
        if (
            not isinstance(base, dict)
            or not isinstance(head, dict)
            or not isinstance(number, int)
            or pull.get("state") != "closed"
            or not isinstance(pull.get("merged_at"), str)
            or base.get("ref") != delivery_branch
            or head.get("ref") != sync_branch
            or not isinstance(merge_sha, str)
            or not isinstance(head.get("sha"), str)
        ):
            continue
        sync_head_sha = head["sha"]
        if not includes_main(compare(api, repo, main_sha, sync_head_sha)):
            continue
        if includes_main(compare(api, repo, merge_sha, proposed_head_sha)):
            return number
    return None


def promotion_source(base: str, head_ref: str) -> str | None:
    """Return the delivery source only for a final main promotion."""
    if base != "main":
        return None
    if DELIVERY_BRANCH.fullmatch(head_ref) or ISOLATED_BRANCH.fullmatch(
        head_ref
    ):
        return head_ref
    if re.fullmatch(r"promote/m[0-9]+-[a-z0-9][a-z0-9-]*", head_ref):
        return "dev/" + head_ref.removeprefix("promote/")
    return None


def gate(
    api: API,
    repo: str,
    base: str,
    head_sha: str,
    *,
    head_ref: str = "",
    pr_number: int = 0,
) -> str:
    """Require latest main only at the final Milestone promotion boundary."""
    source = promotion_source(base, head_ref)
    if source is None:
        return "not-applicable"
    main_sha = read_main_sha(api, repo)
    compare_status = compare(api, repo, main_sha, head_sha)
    if includes_main(compare_status):
        return compare_status
    if head_ref == source:
        sync_pr = merged_sync_pr_number(api, repo, source, main_sha, head_sha)
        if sync_pr is not None:
            return f"squash-sync-pr-{sync_pr}"
    raise RuntimeError(
        f"Final promotion does not contain current main {main_sha} or its "
        "verified reviewed sync squash. Request exactly one reviewed sync "
        f"action: gh workflow run delivery-maintenance.yml -f "
        f"delivery_branch={source} -f reason=promotion -f "
        f"pr_number={pr_number}"
    )


def sync_branch_name(delivery_branch: str, main_sha: str) -> str:
    """Return the deterministic branch name used to deduplicate sync work."""
    key = delivery_branch.removeprefix("dev/")
    return f"sync/main-to-{key}-{main_sha[:12]}"


def ref_sha(api: API, repo: str, branch: str) -> str:
    """Read one exact branch ref without accepting a missing branch."""
    encoded = urllib.parse.quote(branch, safe="")
    status, payload = api.request(
        "GET", f"repos/{repo}/git/ref/heads/{encoded}"
    )
    data = require_response(status, payload, f"read {branch}")
    sha = data.get("object", {}).get("sha") if isinstance(data, dict) else None
    if not isinstance(sha, str):
        raise RuntimeError(f"GitHub returned an invalid {branch} ref")
    return sha


def pull_request(api: API, repo: str, number: int) -> dict[str, Any]:
    """Read one pull request from the repository."""
    status, payload = api.request("GET", f"repos/{repo}/pulls/{number}")
    data = require_response(status, payload, "read pull request")
    if not isinstance(data, dict):
        raise RuntimeError("GitHub returned invalid pull request state")
    return data


def associated_pull_requests(
    api: API, repo: str, commit_sha: str
) -> list[dict[str, Any]]:
    """Read every pull request associated with one exact commit."""
    pulls: list[dict[str, Any]] = []
    page = 1
    while True:
        status, payload = api.request(
            "GET",
            f"repos/{repo}/commits/{commit_sha}/pulls?per_page=100&page={page}",
        )
        data = require_response(
            status, payload, "read merge queue pull requests"
        )
        if not isinstance(data, list):
            raise RuntimeError("GitHub returned an invalid associated PR list")
        pulls.extend(item for item in data if isinstance(item, dict))
        if len(data) < 100:
            break
        page += 1
    return pulls


def merge_group_gate(
    api: API,
    repo: str,
    queue_ref: str,
    queue_sha: str,
    base_ref: str,
    base_sha: str,
) -> str:
    """Bind one merge-queue candidate to its live pull request and refs."""
    match = MERGE_QUEUE_REF.fullmatch(queue_ref)
    if (
        match is None
        or base_ref != "refs/heads/main"
        or FULL_SHA.fullmatch(queue_sha) is None
        or FULL_SHA.fullmatch(base_sha) is None
    ):
        raise RuntimeError("Merge queue event is not an exact main candidate")
    number = int(match.group(1))
    queue_branch = queue_ref.removeprefix("refs/heads/")
    if ref_sha(api, repo, queue_branch) != queue_sha:
        raise RuntimeError("Merge queue ref no longer matches this event")
    pulls = associated_pull_requests(api, repo, queue_sha)
    if len(pulls) != 1 or pulls[0].get("number") != number:
        raise RuntimeError("Merge queue commit has no unique pull request")
    candidate = pull_request(api, repo, number)
    base = candidate.get("base")
    head = candidate.get("head")
    head_repo = head.get("repo") if isinstance(head, dict) else None
    if (
        candidate.get("merged") is not False
        or candidate.get("state") != "open"
        or not isinstance(base, dict)
        or base.get("ref") != "main"
        or base.get("sha") != base_sha
        or not isinstance(head, dict)
        or not isinstance(head.get("ref"), str)
        or not isinstance(head.get("sha"), str)
        or not isinstance(head_repo, dict)
        or head_repo.get("full_name") != repo
    ):
        raise RuntimeError("Queued pull request does not match this event")
    head_ref = str(head["ref"])
    head_sha = str(head["sha"])
    if ref_sha(api, repo, "main") != base_sha:
        raise RuntimeError("Current main changed after merge queue entry")
    if ref_sha(api, repo, head_ref) != head_sha:
        raise RuntimeError("Pull request head changed after merge queue entry")
    if not includes_main(compare(api, repo, base_sha, queue_sha)):
        raise RuntimeError("Merge queue candidate does not contain its base")
    if not includes_main(compare(api, repo, head_sha, queue_sha)):
        raise RuntimeError("Merge queue candidate does not contain its head")
    return f"exact queue candidate for {head_ref}"


def manual_commands(delivery_branch: str, main_sha: str) -> str:
    """Return the portable reviewed-PR fallback for one branch."""
    sync_branch = sync_branch_name(delivery_branch, main_sha)
    return "\n".join(
        [
            f"git fetch origin main {delivery_branch}",
            f"git switch -c {sync_branch} origin/{delivery_branch}",
            "git merge --no-ff origin/main",
            f"git push -u origin {sync_branch}",
            f"gh pr create --base {delivery_branch} --head {sync_branch} "
            f"--title 'chore(sync): merge main into {delivery_branch}'",
            "# Add the enhancement label only through pr_lifecycle.py edit.",
        ]
    )


def lifecycle_command(arguments: list[str]) -> None:
    """Run one fail-closed PR lifecycle operation."""
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(Path(__file__).with_name("pr_lifecycle.py")),
            *arguments,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"PR lifecycle operation failed: {detail}")


def label_sync_pr(repo: str, number: int, head_sha: str) -> None:
    """Label a newly created sync PR while holding its exact remote lease."""
    owner = (
        "github-actions/"
        f"{os.environ.get('GITHUB_RUN_ID', 'local')}/"
        f"{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    )
    with tempfile.TemporaryDirectory(
        prefix="csarc-delivery-lease-"
    ) as directory:
        evidence = Path(directory) / "lease.json"
        common = [
            "--repo",
            repo,
            "--pr-number",
            str(number),
            "--owner",
            owner,
        ]
        lifecycle_command(
            [
                "acquire",
                *common,
                "--head-sha",
                head_sha,
                "--output",
                str(evidence),
            ]
        )
        try:
            lifecycle_command(
                [
                    "edit",
                    *common,
                    "--head-sha",
                    head_sha,
                    "--lease",
                    str(evidence),
                    "--add-label",
                    "enhancement",
                ]
            )
        finally:
            lifecycle_command(["release", *common, "--lease", str(evidence)])


def probe_capabilities(api: API, repo: str, main_sha: str) -> tuple[str, str]:
    """Probe branch and pull-request writes without creating resources."""
    pr_status, _ = api.request(
        "POST",
        f"repos/{repo}/pulls",
        {
            "title": "csarc delivery sync capability probe",
            "head": f"__csarc_sync_probe_{main_sha[:12]}__",
            "base": "main",
            "body": "This invalid head must never create a pull request.",
        },
    )
    ref_status, _ = api.request(
        "POST",
        f"repos/{repo}/git/refs",
        {"ref": "invalid-csarc-delivery-sync-probe", "sha": main_sha},
    )
    return capability_state(pr_status), capability_state(ref_status)


def create_sync_pr(
    api: API,
    repo: str,
    delivery_branch: str,
    delivery_sha: str,
    main_sha: str,
    reason: str,
    request_pr: int,
) -> str:
    """Create one deterministic branch, merge commit, and reviewed sync PR."""
    sync_branch = sync_branch_name(delivery_branch, main_sha)
    owner = repo.split("/", 1)[0]
    query = urllib.parse.urlencode(
        {
            "state": "open",
            "head": f"{owner}:{sync_branch}",
            "base": delivery_branch,
            "per_page": 1,
        }
    )
    status, payload = api.request("GET", f"repos/{repo}/pulls?{query}")
    existing = require_response(status, payload, "find existing sync PR")
    if isinstance(existing, list) and existing:
        return str(existing[0]["html_url"])

    encoded_branch = urllib.parse.quote(sync_branch, safe="")
    status, payload = api.request(
        "GET", f"repos/{repo}/git/ref/heads/{encoded_branch}"
    )
    if status == 404:
        status, payload = api.request(
            "POST",
            f"repos/{repo}/git/refs",
            {"ref": f"refs/heads/{sync_branch}", "sha": delivery_sha},
        )
        require_response(status, payload, "create sync branch")
    elif not 200 <= status < 300:
        require_response(status, payload, "read sync branch")

    status, payload = api.request(
        "POST",
        f"repos/{repo}/merges",
        {"base": sync_branch, "head": main_sha},
    )
    if status == 409:
        raise RuntimeError(
            f"main conflicts with {delivery_branch}; "
            f"resolve it on {sync_branch}"
        )
    require_response(status, payload, "merge main into sync branch")

    body = (
        "## Purpose\n\n"
        f"Synchronize `{main_sha}` into `{delivery_branch}`.\n\n"
        "## 完成清單\n\n"
        "- [x] Merge the selected main commit without direct-pushing "
        "the delivery branch.\n\n"
        "## 補充\n\n"
        f"Requested from PR #{request_pr} for `{reason}`. Created by the "
        "delivery sync workflow; normal review and checks still apply."
    )
    status, payload = api.request(
        "POST",
        f"repos/{repo}/pulls",
        {
            "title": f"chore(sync): merge main into {delivery_branch}",
            "head": sync_branch,
            "base": delivery_branch,
            "body": body,
        },
    )
    pull = require_response(status, payload, "create sync PR")
    number = pull.get("number") if isinstance(pull, dict) else None
    url = pull.get("html_url") if isinstance(pull, dict) else None
    head = pull.get("head") if isinstance(pull, dict) else None
    head_sha = head.get("sha") if isinstance(head, dict) else None
    if (
        not isinstance(number, int)
        or not isinstance(url, str)
        or not isinstance(head_sha, str)
    ):
        raise RuntimeError("GitHub returned an invalid pull request response")
    label_sync_pr(repo, number, head_sha)
    return url


def read_delivery_state(
    api: API, repo: str, main_sha: str, branch: str
) -> DeliveryState:
    """Read one open-Milestone delivery branch and compare it with main."""
    milestone_match = DELIVERY_BRANCH.fullmatch(branch)
    isolated_match = ISOLATED_BRANCH.fullmatch(branch)
    if milestone_match is None and isolated_match is None:
        raise RuntimeError("Sync requires one policy-named delivery branch")
    delivery_sha = ref_sha(api, repo, branch)
    if milestone_match is not None:
        number = int(milestone_match.group(1))
        status, payload = api.request(
            "GET", f"repos/{repo}/milestones/{number}"
        )
        milestone = require_response(status, payload, "read delivery Milestone")
        if (
            not isinstance(milestone, dict)
            or milestone.get("number") != number
            or milestone.get("state") != "open"
        ):
            raise RuntimeError(
                "Delivery sync requires its matching open Milestone"
            )
    else:
        if isolated_match is None:
            raise RuntimeError("Sync requires one policy-named delivery branch")
        number = int(isolated_match.group(1))
        status, payload = api.request("GET", f"repos/{repo}/issues/{number}")
        issue = require_response(status, payload, "read isolated Issue")
        if (
            not isinstance(issue, dict)
            or issue.get("number") != number
            or issue.get("state") != "open"
            or "promotion" not in issue_labels(issue)
        ):
            raise RuntimeError(
                "Isolated sync requires its matching open promotion Issue"
            )
    state = compare(api, repo, main_sha, delivery_sha)
    return DeliveryState(branch, delivery_sha, includes_main(state), state)


def require_sync_request(
    api: API,
    repo: str,
    delivery_branch: str,
    reason: str,
    request_pr: int,
    requester: str,
) -> None:
    """Authorize one final-promotion or explicitly dependent early sync."""
    if reason not in {"promotion", "explicit-dependency"}:
        raise RuntimeError(
            "Sync reason must be promotion or explicit-dependency"
        )
    if request_pr <= 0 or not requester:
        raise RuntimeError("Sync requires one requesting PR and its owner")
    pull = pull_request(api, repo, request_pr)
    base = pull.get("base")
    head = pull.get("head")
    head_repo = head.get("repo") if isinstance(head, dict) else None
    author = pull.get("user")
    if (
        pull.get("state") != "open"
        or pull.get("merged") is not False
        or not isinstance(base, dict)
        or not isinstance(head, dict)
        or not isinstance(head_repo, dict)
        or head_repo.get("full_name") != repo
        or not isinstance(author, dict)
        or str(author.get("login") or "").casefold() != requester.casefold()
    ):
        raise RuntimeError(
            "Sync request must be owned by one live repository PR"
        )

    if reason == "promotion":
        expected_heads = {delivery_branch}
        if DELIVERY_BRANCH.fullmatch(delivery_branch):
            expected_heads.add(
                "promote/" + delivery_branch.removeprefix("dev/")
            )
        if (
            base.get("ref") != "main"
            or head.get("ref") not in expected_heads
            or "promotion" not in issue_labels(pull)
        ):
            raise RuntimeError("Promotion sync requires its matching final PR")
        return

    dependency = re.search(
        r"(?im)^\s*-\s*Dependencies / non-parallel work:\s*(?!None\s*$)\S.+$",
        str(pull.get("body") or ""),
    )
    if base.get("ref") != delivery_branch or dependency is None:
        raise RuntimeError(
            "Early sync requires an owner PR with an explicit dependency"
        )


def reconcile(
    api: API,
    repo: str,
    main_sha: str,
    *,
    auto_requested: bool,
    external_token: bool,
    branch_strategy: str = "delivery",
    delivery_branch: str,
    reason: str,
    request_pr: int,
    requester: str,
) -> list[str]:
    """Report or create one reviewed sync for one authorized delivery."""
    if branch_strategy != "delivery":
        return ["Main-only profile has no delivery sync action."]
    require_sync_request(
        api, repo, delivery_branch, reason, request_pr, requester
    )
    state = read_delivery_state(api, repo, main_sha, delivery_branch)
    if state.current:
        return [f"{delivery_branch} already contains current main."]

    pr_capability = contents_capability = "unknown"
    if auto_requested and external_token:
        pr_capability, contents_capability = probe_capabilities(
            api, repo, main_sha
        )
    mode = select_auto_mode(
        auto_requested,
        external_token,
        pr_capability,
        contents_capability,
    )
    results = [
        f"Sync mode: {mode} (pull requests: {pr_capability}; "
        f"contents: {contents_capability})."
    ]
    if mode == "automatic":
        url = create_sync_pr(
            api,
            repo,
            state.branch,
            state.sha,
            main_sha,
            reason,
            request_pr,
        )
        results.append(f"{state.branch}: {url}")
    else:
        results.append(
            f"{state.branch} is {state.compare_status}; run:\n"
            f"```bash\n{manual_commands(state.branch, main_sha)}\n```"
        )
    return results


def main() -> None:
    """Run the PR gate or one explicitly requested sync action."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "gate",
            "merge-group-gate",
            "reconcile",
        ),
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--head-ref", default="")
    parser.add_argument("--main-sha", default="")
    parser.add_argument("--pr-number", type=int, default=0)
    parser.add_argument("--queue-ref", default="")
    parser.add_argument("--queue-sha", default="")
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--delivery-branch", default="")
    parser.add_argument(
        "--reason", choices=("promotion", "explicit-dependency"), default=""
    )
    parser.add_argument("--request-pr", type=int, default=0)
    parser.add_argument("--requester", default="")
    parser.add_argument("--auto", choices=("true", "false"), default="false")
    parser.add_argument(
        "--branch-strategy",
        choices=("main", "delivery"),
        default="delivery",
    )
    parser.add_argument(
        "--token-kind",
        choices=("github-token", "external"),
        default="github-token",
    )
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise SystemExit("GH_TOKEN is required")
    api = GitHubAPI(token)
    try:
        if args.command == "gate":
            if not args.base or not args.head_sha:
                raise RuntimeError("gate requires --base and --head-sha")
            result = gate(
                api,
                args.repo,
                args.base,
                args.head_sha,
                head_ref=args.head_ref,
                pr_number=args.pr_number,
            )
            print(f"delivery sync gate: {result}")  # noqa: T201
        elif args.command == "merge-group-gate":
            result = merge_group_gate(
                api,
                args.repo,
                args.queue_ref,
                args.queue_sha,
                args.base,
                args.base_sha,
            )
            print(f"delivery sync gate: {result}")  # noqa: T201
        else:
            main_sha = args.main_sha or read_main_sha(api, args.repo)
            for line in reconcile(
                api,
                args.repo,
                main_sha,
                auto_requested=args.auto == "true",
                external_token=args.token_kind == "external",  # noqa: S105
                branch_strategy=args.branch_strategy,
                delivery_branch=args.delivery_branch,
                reason=args.reason,
                request_pr=args.request_pr,
                requester=args.requester,
            ):
                print(line)  # noqa: T201
    except RuntimeError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
