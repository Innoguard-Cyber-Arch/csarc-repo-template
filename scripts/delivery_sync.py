#!/usr/bin/env python3
"""Keep active delivery branches and their pull requests current with main."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

DELIVERY_BRANCH = re.compile(r"^dev/m([0-9]+)-[a-z0-9][a-z0-9-]*$")
ISOLATED_BRANCH = re.compile(r"^dev/i[0-9]+-[a-z0-9][a-z0-9-]*$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
CAPABILITY_STATES = {"allowed", "blocked", "unknown"}


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Never forward a GitHub bearer credential through a redirect."""

    def redirect_request(
        self,
        _request: urllib.request.Request,
        _file: object,
        _code: int,
        _message: str,
        _headers: object,
        _new_url: str,
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
    """One active delivery branch compared with the current main SHA."""

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


def require_response(status: int, payload: object, operation: str) -> object:
    """Return a successful API response or fail with concrete evidence."""
    if 200 <= status < 300:
        return payload
    raise RuntimeError(f"{operation} failed with HTTP {status}: {payload}")


def active_delivery_branches(
    refs: list[dict[str, Any]], open_milestones: set[int]
) -> list[tuple[str, str]]:
    """Select dev/next and branches backed by an open Milestone."""
    active: list[tuple[str, str]] = []
    for item in refs:
        ref = item.get("ref")
        sha = item.get("object", {}).get("sha")
        if not isinstance(ref, str) or not isinstance(sha, str):
            continue
        branch = ref.removeprefix("refs/heads/")
        match = DELIVERY_BRANCH.fullmatch(branch)
        if (
            branch == "dev/next"
            or ISOLATED_BRANCH.fullmatch(branch)
            or (match is not None and int(match.group(1)) in open_milestones)
        ):
            active.append((branch, sha))
    return sorted(active)


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


def gate(
    api: API,
    repo: str,
    base: str,
    head_sha: str,
    *,
    head_ref: str = "",
    pr_number: int = 0,
) -> str:
    """Fail stale PRs and unprotected direct dev/next promotions."""
    if base == "main":
        if head_ref != "dev/next":
            return "not-applicable"
        pull = validate_promotion(api, repo, pr_number, head_sha, merged=False)
        if ref_sha(api, repo, "main") != pull["base"].get("sha"):
            raise RuntimeError("Promotion base no longer matches current main")
        if ref_sha(api, repo, "dev/next") != head_sha:
            raise RuntimeError("dev/next no longer matches the promotion head")
        if (
            repository_settings(api, repo).get("delete_branch_on_merge")
            is False
        ):
            return (
                "temporary-auto-delete-disabled; after merge run "
                f"complete-dev-next for PR {pr_number}, head {head_sha}, "
                "and the merged main SHA"
            )
        if deletion_protection_state(api, repo) == "protected":
            return "deletion-protected"
        raise RuntimeError(
            "dev/next can be auto-deleted; run `python3 "
            "scripts/delivery_sync.py prepare-dev-next "
            f"--repo {repo} --pr-number {pr_number} --head-sha {head_sha}` "
            "with an administrator token, then rerun this check"
        )
    main_sha = read_main_sha(api, repo)
    compare_status = compare(api, repo, main_sha, head_sha)
    if not includes_main(compare_status):
        raise RuntimeError(
            f"PR head does not contain current main {main_sha}; "
            "merge main through a reviewed sync branch first"
        )
    return compare_status


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
    """Read one exact pull request."""
    status, payload = api.request("GET", f"repos/{repo}/pulls/{number}")
    data = require_response(status, payload, "read promotion pull request")
    if not isinstance(data, dict) or data.get("number") != number:
        raise RuntimeError("GitHub returned an invalid promotion pull request")
    return data


def validate_promotion(
    api: API,
    repo: str,
    number: int,
    head_sha: str,
    *,
    merged: bool,
) -> dict[str, Any]:
    """Bind preservation work to one same-repository dev/next promotion."""
    if number < 1 or FULL_SHA.fullmatch(head_sha) is None:
        raise RuntimeError("Promotion number and head SHA are required")
    pull = pull_request(api, repo, number)
    base = pull.get("base")
    head = pull.get("head")
    head_repo = head.get("repo") if isinstance(head, dict) else None
    if (
        pull.get("merged") is not merged
        or not isinstance(base, dict)
        or base.get("ref") != "main"
        or not isinstance(head, dict)
        or head.get("ref") != "dev/next"
        or head.get("sha") != head_sha
        or not isinstance(head_repo, dict)
        or head_repo.get("full_name") != repo
    ):
        raise RuntimeError("Live promotion does not match dev/next evidence")
    return pull


def repository_settings(api: API, repo: str) -> dict[str, Any]:
    """Read observable repository settings."""
    status, payload = api.request("GET", f"repos/{repo}")
    data = require_response(status, payload, "read repository settings")
    if not isinstance(data, dict):
        raise RuntimeError("GitHub returned invalid repository settings")
    return data


def deletion_protection_state(api: API, repo: str) -> str:
    """Classify effective deletion protection without trusting ambiguity."""
    status, payload = api.request(
        "GET", f"repos/{repo}/rules/branches/dev%2Fnext"
    )
    if status in {401, 403, 404}:
        return "blocked"
    if not 200 <= status < 300 or not isinstance(payload, list):
        return "unknown"
    if any(
        isinstance(rule, dict) and rule.get("type") == "deletion"
        for rule in payload
    ):
        return "protected"
    return "unprotected"


def set_auto_delete(api: API, repo: str, enabled: bool) -> None:
    """Set and verify automatic merged-branch deletion."""
    status, payload = api.request(
        "PATCH", f"repos/{repo}", {"delete_branch_on_merge": enabled}
    )
    action = "restore" if enabled else "disable"
    require_response(status, payload, f"{action} automatic branch deletion")
    if (
        repository_settings(api, repo).get("delete_branch_on_merge")
        is not enabled
    ):
        raise RuntimeError(f"Automatic branch deletion was not {action}d")


def prepare_dev_next(api: API, repo: str, number: int, head_sha: str) -> str:
    """Prevent auto-delete before one exact dev/next promotion merge."""
    pull = validate_promotion(api, repo, number, head_sha, merged=False)
    base = pull["base"]
    if ref_sha(api, repo, "main") != base.get("sha"):
        raise RuntimeError("Promotion base no longer matches current main")
    if ref_sha(api, repo, "dev/next") != head_sha:
        raise RuntimeError("dev/next no longer matches the promotion head")
    settings = repository_settings(api, repo)
    if settings.get("delete_branch_on_merge") is False:
        return "temporary-auto-delete-disabled"
    protection = deletion_protection_state(api, repo)
    if protection == "protected":
        return "deletion-protected"
    status, payload = api.request(
        "PATCH", f"repos/{repo}", {"delete_branch_on_merge": False}
    )
    require_response(status, payload, "disable automatic branch deletion")
    try:
        if (
            repository_settings(api, repo).get("delete_branch_on_merge")
            is not False
        ):
            raise RuntimeError("Automatic branch deletion was not disabled")
        if (
            ref_sha(api, repo, "main") != base.get("sha")
            or ref_sha(api, repo, "dev/next") != head_sha
        ):
            raise RuntimeError("Promotion refs changed while enabling fallback")
    except RuntimeError:
        set_auto_delete(api, repo, True)
        raise
    return f"temporary-auto-delete-disabled ({protection})"


def complete_dev_next(
    api: API, repo: str, number: int, head_sha: str, main_sha: str
) -> str:
    """Verify continuity after merge and restore normal branch cleanup."""
    if FULL_SHA.fullmatch(main_sha) is None:
        raise RuntimeError("Merged main SHA is required")
    pull = validate_promotion(api, repo, number, head_sha, merged=True)
    if pull.get("merge_commit_sha") != main_sha:
        raise RuntimeError("Promotion merge commit does not match main")
    if ref_sha(api, repo, "main") != main_sha:
        raise RuntimeError("Current main does not match the promotion merge")
    live_dev_next = ref_sha(api, repo, "dev/next")
    if live_dev_next != head_sha and (
        not includes_main(compare(api, repo, head_sha, live_dev_next))
        or not includes_main(compare(api, repo, main_sha, live_dev_next))
    ):
        raise RuntimeError("dev/next no longer preserves the promoted lineage")
    head_status, head_payload = api.request(
        "GET", f"repos/{repo}/git/commits/{head_sha}"
    )
    main_status, main_payload = api.request(
        "GET", f"repos/{repo}/git/commits/{main_sha}"
    )
    head_commit = require_response(
        head_status, head_payload, "read promotion head"
    )
    main_commit = require_response(
        main_status, main_payload, "read merged main"
    )
    head_tree = (
        head_commit.get("tree", {}).get("sha")
        if isinstance(head_commit, dict)
        else None
    )
    main_tree = (
        main_commit.get("tree", {}).get("sha")
        if isinstance(main_commit, dict)
        else None
    )
    if not isinstance(head_tree, str) or main_tree != head_tree:
        raise RuntimeError(
            "Merged main tree differs from the dev/next candidate"
        )
    if repository_settings(api, repo).get("delete_branch_on_merge") is False:
        set_auto_delete(api, repo, True)
        return "auto-delete-restored"
    return "auto-delete-already-enabled"


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
            f"--title 'chore(sync): merge main into {delivery_branch}' "
            "--label enhancement",
        ]
    )


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
        "Created by the delivery sync workflow; normal review and checks "
        "still apply."
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
    if not isinstance(number, int) or not isinstance(url, str):
        raise RuntimeError("GitHub returned an invalid pull request response")
    status, payload = api.request(
        "POST",
        f"repos/{repo}/issues/{number}/labels",
        {"labels": ["enhancement"]},
    )
    require_response(status, payload, "label sync PR")
    return url


def read_active_states(
    api: API, repo: str, main_sha: str, *, require_dev_next: bool = False
) -> list[DeliveryState]:
    """Read and compare every active delivery branch."""
    status, payload = api.request(
        "GET", f"repos/{repo}/git/matching-refs/heads/dev/?per_page=100"
    )
    refs = require_response(status, payload, "list delivery refs")
    status, payload = api.request(
        "GET", f"repos/{repo}/milestones?state=open&per_page=100"
    )
    milestones = require_response(status, payload, "list open Milestones")
    if not isinstance(refs, list) or not isinstance(milestones, list):
        raise RuntimeError("GitHub returned invalid delivery branch state")
    open_numbers = {
        item["number"]
        for item in milestones
        if isinstance(item, dict) and isinstance(item.get("number"), int)
    }
    active = active_delivery_branches(refs, open_numbers)
    if require_dev_next and not any(
        branch == "dev/next" for branch, _sha in active
    ):
        raise RuntimeError("Required delivery branch dev/next is missing")
    return [
        DeliveryState(branch, sha, includes_main(state), state)
        for branch, sha in active
        for state in [compare(api, repo, main_sha, sha)]
    ]


def update_open_pr_statuses(api: API, repo: str, main_sha: str) -> None:
    """Invalidate stale delivery PR checks whenever main advances."""
    status, payload = api.request(
        "GET", f"repos/{repo}/pulls?state=open&per_page=100"
    )
    pulls = require_response(status, payload, "list open pull requests")
    if not isinstance(pulls, list):
        raise RuntimeError("GitHub returned invalid pull request state")
    for pull in pulls:
        base = pull.get("base", {}).get("ref")
        head_sha = pull.get("head", {}).get("sha")
        if base == "main" or not isinstance(head_sha, str):
            continue
        current = includes_main(compare(api, repo, main_sha, head_sha))
        state = "success" if current else "failure"
        description = (
            "PR head contains current main"
            if current
            else "PR head must synchronize current main before merge"
        )
        status_code, status_payload = api.request(
            "POST",
            f"repos/{repo}/statuses/{head_sha}",
            {
                "state": state,
                "context": "delivery-sync",
                "description": description,
            },
        )
        require_response(
            status_code, status_payload, "update delivery-sync status"
        )


def reconcile(
    api: API,
    repo: str,
    main_sha: str,
    *,
    auto_requested: bool,
    external_token: bool,
    branch_strategy: str = "delivery",
) -> list[str]:
    """Report or create one deduplicated sync PR per stale active branch."""
    states = read_active_states(
        api,
        repo,
        main_sha,
        require_dev_next=branch_strategy == "delivery",
    )
    update_open_pr_statuses(api, repo, main_sha)
    stale = [state for state in states if not state.current]
    if not stale:
        return ["All active delivery branches contain current main."]

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
    for state in stale:
        if mode == "automatic":
            url = create_sync_pr(api, repo, state.branch, state.sha, main_sha)
            results.append(f"{state.branch}: {url}")
        else:
            results.append(
                f"{state.branch} is {state.compare_status}; run:\n"
                f"```bash\n{manual_commands(state.branch, main_sha)}\n```"
            )
    return results


def main() -> None:
    """Run the PR gate or main-push reconciliation mode."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("gate", "reconcile", "prepare-dev-next", "complete-dev-next"),
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--head-ref", default="")
    parser.add_argument("--main-sha", default="")
    parser.add_argument("--pr-number", type=int, default=0)
    parser.add_argument("--auto", choices=("true", "false"), default="false")
    parser.add_argument(
        "--branch-strategy",
        choices=("main", "dev", "delivery"),
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
        elif args.command == "prepare-dev-next":
            print(  # noqa: T201
                prepare_dev_next(api, args.repo, args.pr_number, args.head_sha)
            )
        elif args.command == "complete-dev-next":
            print(  # noqa: T201
                complete_dev_next(
                    api,
                    args.repo,
                    args.pr_number,
                    args.head_sha,
                    args.main_sha,
                )
            )
        else:
            main_sha = args.main_sha or read_main_sha(api, args.repo)
            for line in reconcile(
                api,
                args.repo,
                main_sha,
                auto_requested=args.auto == "true",
                external_token=args.token_kind == "external",  # noqa: S105
                branch_strategy=args.branch_strategy,
            ):
                print(line)  # noqa: T201
    except RuntimeError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
