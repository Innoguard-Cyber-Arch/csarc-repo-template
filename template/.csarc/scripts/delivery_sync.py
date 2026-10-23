#!/usr/bin/env python3
"""Synchronize one authorized Milestone delivery at its actual boundary."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

DELIVERY_BRANCH = re.compile(r"^dev/m([0-9]+)-[a-z0-9][a-z0-9-]*$")
ISOLATED_BRANCH = re.compile(r"^dev/i([0-9]+)-[a-z0-9][a-z0-9-]*$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
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
            raise ValueError("Bad URL: not HTTPS. Use HTTPS.")
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
        raise RuntimeError(
            "Bad GitHub reply: invalid PR labels. Rerun the failed job."
        )
    return {str(item["name"]) for item in values}


def require_response(status: int, payload: object, operation: str) -> object:
    """Return a successful API response or fail with concrete evidence."""
    if 200 <= status < 300:
        return payload
    raise RuntimeError(
        f"{operation} failed: HTTP {status} {payload}. Check GH_TOKEN access, "
        "then rerun the job."
    )


def includes_main(compare_status: str) -> bool:
    """Return whether the compared head contains the selected main commit."""
    return compare_status in {"ahead", "identical"}


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
        raise RuntimeError(
            "Bad GitHub reply: invalid compare. Rerun the failed job."
        )
    return compare_status


def read_main_sha(api: API, repo: str) -> str:
    """Read the current main commit."""
    status, payload = api.request("GET", f"repos/{repo}/git/ref/heads/main")
    data = require_response(status, payload, "read main")
    main_sha = (
        data.get("object", {}).get("sha") if isinstance(data, dict) else None
    )
    if not isinstance(main_sha, str):
        raise RuntimeError(
            "Bad GitHub reply: invalid main ref. Rerun the failed job."
        )
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
        raise RuntimeError(
            "Bad GitHub reply: invalid sync PR. Rerun the failed job."
        )
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
        f"Final promotion lacks main {main_sha}: no verified reviewed sync "
        "squash. Request exactly one reviewed sync action: 'gh workflow run "
        f"delivery-maintenance.yml -f delivery_branch={source} -f "
        f"reason=promotion -f pr_number={pr_number}'."
    )


def sync_branch_name(delivery_branch: str, main_sha: str) -> str:
    """Return the deterministic branch name used to deduplicate sync work."""
    key = delivery_branch.removeprefix("dev/")
    return f"sync/main-to-{key}-{main_sha[:12]}"


def validate_sync_identity(
    base_ref: str,
    head_ref: str,
    base_sha: str,
    head_sha: str,
    main_sha: str,
    parents: list[str],
    head_tree: str,
    merge_tree: str | None,
) -> bool:
    """Validate exact sync topology and report whether its merge was clean."""
    if (
        DELIVERY_BRANCH.fullmatch(base_ref) is None
        or head_ref != sync_branch_name(base_ref, main_sha)
        or any(
            FULL_SHA.fullmatch(value) is None
            for value in (base_sha, head_sha, main_sha, head_tree)
        )
        or parents != [base_sha, main_sha]
    ):
        raise RuntimeError(
            "Bad sync: not an exact main-to-delivery merge. Close it and "
            "request a new sync."
        )
    return merge_tree is not None and head_tree == merge_tree


def git_output(arguments: list[str]) -> str:
    """Read one local Git value or fail closed."""
    result = subprocess.run(  # noqa: S603
        ["git", *arguments],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def validate_sync_route(
    api: API,
    repo: str,
    pr_number: int,
    base_ref: str,
    base_sha: str,
    head_ref: str,
    head_sha: str,
) -> None:
    """Validate the current PR and its recorded authorized sync request."""
    pull = pull_request(api, repo, pr_number)
    base = pull.get("base")
    head = pull.get("head")
    head_repo = head.get("repo") if isinstance(head, dict) else None
    request = re.search(
        r"Requested from PR #([1-9][0-9]*) for "
        r"`(promotion|explicit-dependency)`\. Created by the "
        r"delivery sync workflow;",
        str(pull.get("body") or ""),
    )
    if (
        pull.get("state") != "open"
        or pull.get("merged") is not False
        or pull.get("title") != f"chore(sync): merge main into {base_ref}"
        or "enhancement" not in issue_labels(pull)
        or not isinstance(base, dict)
        or base.get("ref") != base_ref
        or base.get("sha") != base_sha
        or not isinstance(head, dict)
        or head.get("ref") != head_ref
        or head.get("sha") != head_sha
        or not isinstance(head_repo, dict)
        or head_repo.get("full_name") != repo
        or request is None
    ):
        raise RuntimeError(
            "Bad sync: route not authorized. Request the sync from the owner "
            "PR."
        )
    request_number = int(request.group(1))
    requesting_pull = pull_request(api, repo, request_number)
    requester = requesting_pull.get("user")
    requester_login = (
        requester.get("login") if isinstance(requester, dict) else None
    )
    if not isinstance(requester_login, str) or not requester_login:
        raise RuntimeError(
            "Bad sync: requester is unknown. Rerun the failed job."
        )
    require_sync_request(
        api,
        repo,
        base_ref,
        request.group(2),
        request_number,
        requester_login,
    )


def verify_sync(args: argparse.Namespace) -> None:
    """Validate the authorized route and exact sync topology before tests."""
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise RuntimeError(
            "Sync check: no GH_TOKEN. Set GH_TOKEN in the workflow step."
        )
    api = GitHubAPI(token)
    validate_sync_route(
        api,
        args.repo,
        args.pr_number,
        args.base,
        args.base_sha,
        args.head_ref,
        args.head_sha,
    )
    if ref_sha(api, args.repo, args.base) != args.base_sha:
        raise RuntimeError(
            "Stale sync: delivery base moved. Rerun the 'verify' job."
        )
    if ref_sha(api, args.repo, "main") != args.main_sha:
        raise RuntimeError("Stale sync: main moved. Rerun the 'verify' job.")
    if ref_sha(api, args.repo, args.head_ref) != args.head_sha:
        raise RuntimeError(
            "Stale sync: sync head moved. Rerun the 'verify' job."
        )
    commit = git_output(["rev-list", "--parents", "-n", "1", args.head_sha])
    fields = commit.split()
    if not fields or fields[0] != args.head_sha:
        raise RuntimeError(
            "Bad sync: no commit identity. Rerun the 'verify' job."
        )
    head_tree = git_output(["rev-parse", f"{args.head_sha}^{{tree}}"])
    merge = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "git",
            "merge-tree",
            "--write-tree",
            args.base_sha,
            args.main_sha,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    merge_tree = merge.stdout.splitlines()[0] if merge.returncode == 0 else None
    clean = validate_sync_identity(
        args.base,
        args.head_ref,
        args.base_sha,
        args.head_sha,
        args.main_sha,
        fields[1:],
        head_tree,
        merge_tree,
    )
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"clean={str(clean).lower()}\n")
    sys.stdout.write("clean\n" if clean else "manual-conflict-resolution\n")


def ref_sha(api: API, repo: str, branch: str) -> str:
    """Read one exact branch ref without accepting a missing branch."""
    encoded = urllib.parse.quote(branch, safe="")
    status, payload = api.request(
        "GET", f"repos/{repo}/git/ref/heads/{encoded}"
    )
    data = require_response(status, payload, f"read {branch}")
    sha = data.get("object", {}).get("sha") if isinstance(data, dict) else None
    if not isinstance(sha, str):
        raise RuntimeError(
            f"Bad GitHub reply: invalid {branch} ref. Rerun the failed job."
        )
    return sha


def pull_request(api: API, repo: str, number: int) -> dict[str, Any]:
    """Read one pull request from the repository."""
    status, payload = api.request("GET", f"repos/{repo}/pulls/{number}")
    data = require_response(status, payload, "read pull request")
    if not isinstance(data, dict):
        raise RuntimeError(
            "Bad GitHub reply: invalid PR. Rerun the failed job."
        )
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
            raise RuntimeError(
                "Bad GitHub reply: invalid PR list. Rerun the failed job."
            )
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
        raise RuntimeError(
            "Bad queue: not an exact main candidate. Add the PR to the queue "
            "again."
        )
    number = int(match.group(1))
    queue_branch = queue_ref.removeprefix("refs/heads/")
    if ref_sha(api, repo, queue_branch) != queue_sha:
        raise RuntimeError(
            "Stale queue: ref moved. Add the PR to the queue again."
        )
    pulls = associated_pull_requests(api, repo, queue_sha)
    if len(pulls) != 1 or pulls[0].get("number") != number:
        raise RuntimeError(
            "Bad queue: no unique pull request. Add the PR to the queue again."
        )
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
        raise RuntimeError(
            "Stale queue: PR changed. Add the PR to the queue again."
        )
    head_ref = str(head["ref"])
    head_sha = str(head["sha"])
    if ref_sha(api, repo, "main") != base_sha:
        raise RuntimeError(
            "Stale queue: main changed. Add the PR to the queue again."
        )
    if ref_sha(api, repo, head_ref) != head_sha:
        raise RuntimeError(
            "Stale queue: PR head changed. Add the PR to the queue again."
        )
    if not includes_main(compare(api, repo, base_sha, queue_sha)):
        raise RuntimeError(
            "Bad queue: base is missing. Add the PR to the queue again."
        )
    if not includes_main(compare(api, repo, head_sha, queue_sha)):
        raise RuntimeError(
            "Bad queue: head is missing. Add the PR to the queue again."
        )
    return f"exact queue candidate for {head_ref}"


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
            "Bad sync reason: not promotion or explicit-dependency. Pass one "
            "of them to '--reason'."
        )
    if request_pr <= 0 or not requester:
        raise RuntimeError(
            "Bad sync: no requesting PR or owner. Pass '--request-pr' and "
            "'--requester'."
        )
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
            "Bad sync: not owned by one live repository PR. Request it from "
            "your own open PR."
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
            raise RuntimeError(
                "Bad sync: no matching final PR. Request it from the open "
                "promotion PR."
            )
        return

    dependency = re.search(
        r"(?im)^\s*-\s*Dependencies / non-parallel work:\s*(?!None\s*$)\S.+$",
        str(pull.get("body") or ""),
    )
    if base.get("ref") != delivery_branch or dependency is None:
        raise RuntimeError(
            "Bad sync: owner PR lacks an explicit dependency. Fill "
            "'Dependencies / non-parallel work' in its body."
        )


def main() -> None:
    """Run the PR gate or one explicitly requested sync action."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "gate",
            "merge-group-gate",
            "verify-sync",
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
    parser.add_argument(
        "--branch-strategy",
        choices=("main", "delivery"),
        default="delivery",
    )
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "verify-sync":
            verify_sync(args)
            return
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            raise RuntimeError(
                "Sync failed: no GH_TOKEN. Set GH_TOKEN in the workflow step."
            )
        api = GitHubAPI(token)
        if args.command == "gate":
            if not args.base or not args.head_sha:
                raise RuntimeError(
                    "Bad gate: no --base/--head-sha. Pass '--base' and "
                    "'--head-sha'."
                )
            result = gate(
                api,
                args.repo,
                args.base,
                args.head_sha,
                head_ref=args.head_ref,
                pr_number=args.pr_number,
            )
            print(f"OK: Delivery sync gate: {result}.")  # noqa: T201
        elif args.command == "merge-group-gate":
            result = merge_group_gate(
                api,
                args.repo,
                args.queue_ref,
                args.queue_sha,
                args.base,
                args.base_sha,
            )
            print(f"OK: Delivery sync gate: {result}.")  # noqa: T201
    except RuntimeError as error:
        raise SystemExit(f"ERROR: {error}") from error


if __name__ == "__main__":
    main()
