#!/usr/bin/env python3
"""Keep active delivery branches and their pull requests current with main."""

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
ISOLATED_BRANCH = re.compile(r"^dev/i[0-9]+-[a-z0-9][a-z0-9-]*$")
CAPABILITY_STATES = {"allowed", "blocked", "unknown"}


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
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=20
            ) as response:
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


def gate(api: API, repo: str, base: str, head_sha: str) -> str:
    """Fail a non-main PR unless its proposed head contains current main."""
    if base == "main":
        return "not-applicable"
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


def read_active_states(
    api: API, repo: str, main_sha: str
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
    return [
        DeliveryState(branch, sha, includes_main(state), state)
        for branch, sha in active_delivery_branches(refs, open_numbers)
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
) -> list[str]:
    """Report or create one deduplicated sync PR per stale active branch."""
    states = read_active_states(api, repo, main_sha)
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
    parser.add_argument("command", choices=("gate", "reconcile"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--main-sha", default="")
    parser.add_argument("--auto", choices=("true", "false"), default="false")
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
            result = gate(api, args.repo, args.base, args.head_sha)
            print(f"delivery sync gate: {result}")  # noqa: T201
        else:
            main_sha = args.main_sha or read_main_sha(api, args.repo)
            for line in reconcile(
                api,
                args.repo,
                main_sha,
                auto_requested=args.auto == "true",
                external_token=args.token_kind == "external",  # noqa: S105
            ):
                print(line)  # noqa: T201
    except RuntimeError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
