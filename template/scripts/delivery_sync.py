#!/usr/bin/env python3
"""Keep active delivery branches and their pull requests current with main."""

from __future__ import annotations

import argparse
import base64
import hashlib
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
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
CAPABILITY_STATES = {"allowed", "blocked", "unknown"}
MAINTAINER_ASSOCIATIONS = {"MEMBER", "OWNER"}
MAINTAINER_PERMISSIONS = {"admin", "maintain"}
SYNC_SECRET = "CSARC_SYNC_TOKEN"  # noqa: S105
PRESERVATION_LEDGER_BRANCH = "csarc/dev-next-preservation-ledger"
PRESERVATION_LEDGER_PATH = "transaction.json"
PRESERVATION_STATES = {
    "preparing",
    "prepared",
    "restoring-complete",
    "restoring-abort",
    "completed",
    "aborted",
}
MERGE_QUEUE_REF = re.compile(
    r"^refs/heads/gh-readonly-queue/main/pr-([1-9][0-9]*)-[A-Za-z0-9_-]+$"
)


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


def is_delivery_branch(branch: str) -> bool:
    """Return whether a branch is a supported delivery destination."""
    return bool(
        branch == "dev/next"
        or DELIVERY_BRANCH.fullmatch(branch)
        or ISOLATED_BRANCH.fullmatch(branch)
    )


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


def gate(
    api: API,
    repo: str,
    base: str,
    head_sha: str,
    delivery_base: str = "",
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
        ledger_commit, record, _authorizations = require_prepared_preservation(
            api, repo, pr_number, str(pull["base"]["sha"]), head_sha
        )
        return (
            f"{record['mode']}; transaction "
            f"{record['operation_id']} at {ledger_commit}"
        )
    main_sha = read_main_sha(api, repo)
    compare_status = compare(api, repo, main_sha, head_sha)
    if includes_main(compare_status):
        return compare_status
    if delivery_base and is_delivery_branch(delivery_base):
        sync_pr = merged_sync_pr_number(
            api, repo, delivery_base, main_sha, head_sha
        )
        if sync_pr is not None:
            return f"squash-sync-pr-{sync_pr}"
    raise RuntimeError(
        f"PR head does not contain current main {main_sha} or its verified "
        "reviewed sync squash; synchronize main first"
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


def canonical_json(value: object) -> str:
    """Return the stable representation stored in the remote ledger."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def preservation_operation(
    repo: str, number: int, base_sha: str, head_sha: str
) -> str:
    """Derive one operation ID shared by contenders for the same promotion."""
    identity = canonical_json(
        {
            "base_sha": base_sha,
            "head_sha": head_sha,
            "pull_request": number,
            "repository": repo,
        }
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def validate_preservation_record(  # noqa: C901
    record: object,
) -> dict[str, Any]:
    """Reject malformed or ambiguous ledger records."""
    if not isinstance(record, dict):
        raise RuntimeError("Dev/next preservation ledger record is invalid")
    required = {
        "schema_version": 1,
        "repository": str,
        "pull_request": int,
        "base_ref": "main",
        "base_sha": str,
        "head_ref": "dev/next",
        "head_sha": str,
        "operation_id": str,
        "mode": str,
        "prior_auto_delete": bool,
        "state": str,
        "previous_ledger_commit": (str, type(None)),
    }
    for field, expected in required.items():
        value = record.get(field)
        if isinstance(expected, (tuple, type)):
            if not isinstance(value, expected):
                raise RuntimeError(
                    f"Dev/next preservation record has invalid {field}"
                )
        elif value != expected:
            raise RuntimeError(
                f"Dev/next preservation record has invalid {field}"
            )
    if (
        FULL_SHA.fullmatch(str(record["base_sha"])) is None
        or FULL_SHA.fullmatch(str(record["head_sha"])) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(record["operation_id"])) is None
        or record["mode"] not in {"ruleset-protected", "temporary-auto-delete"}
        or record["state"] not in PRESERVATION_STATES
        or (
            record["mode"] == "temporary-auto-delete"
            and record["prior_auto_delete"] is not True
        )
    ):
        raise RuntimeError("Dev/next preservation ledger record is invalid")
    main_sha = record.get("main_sha")
    if main_sha is not None and (
        not isinstance(main_sha, str) or FULL_SHA.fullmatch(main_sha) is None
    ):
        raise RuntimeError("Dev/next preservation record has invalid main_sha")
    prepared_commit = record.get("prepared_ledger_commit")
    if prepared_commit is not None and (
        not isinstance(prepared_commit, str)
        or FULL_SHA.fullmatch(prepared_commit) is None
    ):
        raise RuntimeError(
            "Dev/next preservation record has invalid prepared checkpoint"
        )
    previous_commit = record["previous_ledger_commit"]
    if (
        previous_commit is not None
        and FULL_SHA.fullmatch(previous_commit) is None
    ):
        raise RuntimeError(
            "Dev/next preservation record has invalid previous checkpoint"
        )
    if record["state"] in {"restoring-complete", "completed"} and (
        main_sha is None or prepared_commit is None
    ):
        raise RuntimeError("Completing preservation record is incomplete")
    terminal_fields = {"main_sha", "prepared_ledger_commit"}
    base_fields = set(required) | terminal_fields
    if (
        set(record) - base_fields
        or (
            record["state"]
            not in {
                "restoring-complete",
                "restoring-abort",
                "completed",
                "aborted",
            }
            and "prepared_ledger_commit" in record
        )
        or (
            record["state"] not in {"restoring-complete", "completed"}
            and "main_sha" in record
        )
    ):
        raise RuntimeError("Dev/next preservation record has unexpected fields")
    if str(record["state"]).startswith("restoring-") and (
        record["mode"] != "temporary-auto-delete"
    ):
        raise RuntimeError("Only temporary preservation may require restoring")
    return record


def read_preservation_commit(
    api: API, repo: str, commit_sha: str
) -> tuple[dict[str, Any], str]:
    """Read one canonical single-parent ledger commit and its parent."""
    status, payload = api.request(
        "GET", f"repos/{repo}/git/commits/{commit_sha}"
    )
    commit = require_response(status, payload, "read preservation checkpoint")
    parents = commit.get("parents") if isinstance(commit, dict) else None
    tree_sha = (
        commit.get("tree", {}).get("sha") if isinstance(commit, dict) else None
    )
    if (
        not isinstance(commit, dict)
        or commit.get("sha") != commit_sha
        or not isinstance(parents, list)
        or len(parents) != 1
        or not isinstance(parents[0], dict)
        or FULL_SHA.fullmatch(str(parents[0].get("sha", ""))) is None
        or not isinstance(tree_sha, str)
        or FULL_SHA.fullmatch(tree_sha) is None
    ):
        raise RuntimeError("GitHub returned an invalid preservation commit")
    status, payload = api.request("GET", f"repos/{repo}/git/trees/{tree_sha}")
    tree = require_response(status, payload, "read preservation tree")
    entries = tree.get("tree") if isinstance(tree, dict) else None
    matches = [
        item
        for item in entries or []
        if isinstance(item, dict)
        and item.get("path") == PRESERVATION_LEDGER_PATH
        and item.get("mode") == "100644"
        and item.get("type") == "blob"
        and isinstance(item.get("sha"), str)
        and FULL_SHA.fullmatch(str(item["sha"])) is not None
    ]
    if not isinstance(entries, list) or len(entries) != 1 or len(matches) != 1:
        raise RuntimeError("Preservation ledger has no unique transaction")
    status, payload = api.request(
        "GET", f"repos/{repo}/git/blobs/{matches[0]['sha']}"
    )
    blob = require_response(status, payload, "read preservation record")
    if (
        not isinstance(blob, dict)
        or blob.get("encoding") != "base64"
        or not isinstance(blob.get("content"), str)
    ):
        raise RuntimeError("GitHub returned an invalid preservation record")
    try:
        encoded_content = "".join(blob["content"].split())
        content = base64.b64decode(encoded_content, validate=True).decode()
        record = json.loads(content)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Preservation ledger record is not canonical JSON"
        ) from error
    validated = validate_preservation_record(record)
    if (
        content != canonical_json(validated) + "\n"
        or commit.get("message")
        != "csarc dev/next preservation "
        f"{validated['operation_id']} {validated['state']}"
    ):
        raise RuntimeError("Preservation ledger record is not canonical JSON")
    parent = str(parents[0]["sha"])
    expected_parent = (
        validated["previous_ledger_commit"] or validated["base_sha"]
    )
    if parent != expected_parent:
        raise RuntimeError(
            "Preservation ledger parent does not match its record"
        )
    return validated, parent


def same_preservation_operation(
    newer: dict[str, Any], older: dict[str, Any]
) -> bool:
    """Return whether adjacent records describe the same immutable operation."""
    fields = (
        "schema_version",
        "repository",
        "pull_request",
        "base_ref",
        "base_sha",
        "head_ref",
        "head_sha",
        "operation_id",
        "mode",
        "prior_auto_delete",
    )
    return all(newer[field] == older[field] for field in fields)


def valid_preservation_transition(  # noqa: C901
    newer: dict[str, Any], older: dict[str, Any], older_commit: str
) -> bool:
    """Return whether one canonical ledger state may follow another."""
    state = str(newer["state"])
    old_state = str(older["state"])
    same_operation = same_preservation_operation(newer, older)
    if state == "preparing":
        if same_operation or old_state not in {"completed", "aborted"}:
            return False
        if any(
            newer[field] != older[field]
            for field in ("repository", "base_ref", "head_ref")
        ):
            return False
        return old_state == "aborted" or newer["base_sha"] != older["base_sha"]
    if not same_operation:
        return False
    if state == "prepared":
        return old_state == "preparing"
    if state == "restoring-complete":
        return (
            newer["mode"] == "temporary-auto-delete"
            and old_state == "prepared"
            and newer.get("prepared_ledger_commit") == older_commit
        )
    if state == "completed":
        expected = (
            "restoring-complete"
            if newer["mode"] == "temporary-auto-delete"
            else "prepared"
        )
        if old_state != expected:
            return False
        if newer["mode"] == "temporary-auto-delete":
            return all(
                newer.get(field) == older.get(field)
                for field in ("main_sha", "prepared_ledger_commit")
            )
        return newer.get("prepared_ledger_commit") == older_commit
    if state == "restoring-abort":
        if newer["mode"] != "temporary-auto-delete":
            return False
        if old_state == "prepared":
            return newer.get("prepared_ledger_commit") == older_commit
        return (
            old_state == "preparing" and "prepared_ledger_commit" not in newer
        )
    if state == "aborted":
        expected_states = (
            {"restoring-abort"}
            if newer["mode"] == "temporary-auto-delete"
            else {"preparing", "prepared"}
        )
        return old_state in expected_states and (
            newer.get("prepared_ledger_commit")
            == older.get("prepared_ledger_commit")
        )
    return False


def read_preservation_record(
    api: API, repo: str
) -> tuple[str, dict[str, Any]] | None:
    """Read and validate the append-only preservation ledger history."""
    encoded = urllib.parse.quote(PRESERVATION_LEDGER_BRANCH, safe="")
    status, payload = api.request(
        "GET", f"repos/{repo}/git/ref/heads/{encoded}"
    )
    if status == 404:
        return None
    ref = require_response(status, payload, "read preservation ledger")
    commit_sha = (
        ref.get("object", {}).get("sha") if isinstance(ref, dict) else None
    )
    if (
        not isinstance(commit_sha, str)
        or FULL_SHA.fullmatch(commit_sha) is None
    ):
        raise RuntimeError("GitHub returned an invalid preservation ledger ref")
    head_sha = commit_sha
    record, parent = read_preservation_commit(api, repo, commit_sha)
    head_record = record
    seen_operations: set[str] = set()
    while True:
        if record["repository"] != repo:
            raise RuntimeError(
                "Preservation ledger belongs to another repository"
            )
        operation = str(record["operation_id"])
        seen_operations.add(operation)
        previous = record["previous_ledger_commit"]
        if previous is None:
            if record["state"] != "preparing" or parent != record["base_sha"]:
                raise RuntimeError("Preservation ledger has an invalid anchor")
            break
        older, older_parent = read_preservation_commit(api, repo, previous)
        if not valid_preservation_transition(record, older, previous):
            raise RuntimeError(
                "Preservation ledger has an invalid state transition"
            )
        if (
            older["operation_id"] != operation
            and str(older["operation_id"]) in seen_operations
        ):
            raise RuntimeError("Preservation ledger reuses an operation")
        record, parent = older, older_parent
    return head_sha, head_record


def append_preservation_record(
    api: API,
    repo: str,
    previous_commit: str | None,
    record: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Append one record with a create-only or non-force ref update."""
    validated = validate_preservation_record(
        {**record, "previous_ledger_commit": previous_commit}
    )
    status, payload = api.request(
        "POST",
        f"repos/{repo}/git/blobs",
        {"content": canonical_json(validated) + "\n", "encoding": "utf-8"},
    )
    blob = require_response(status, payload, "create preservation blob")
    blob_sha = blob.get("sha") if isinstance(blob, dict) else None
    if not isinstance(blob_sha, str) or FULL_SHA.fullmatch(blob_sha) is None:
        raise RuntimeError("GitHub returned an invalid preservation blob")
    tree_payload: dict[str, object] = {
        "tree": [
            {
                "path": PRESERVATION_LEDGER_PATH,
                "mode": "100644",
                "type": "blob",
                "sha": blob_sha,
            }
        ]
    }
    if previous_commit is not None:
        status, payload = api.request(
            "GET", f"repos/{repo}/git/commits/{previous_commit}"
        )
        previous = require_response(
            status, payload, "read previous preservation checkpoint"
        )
        base_tree = (
            previous.get("tree", {}).get("sha")
            if isinstance(previous, dict)
            else None
        )
        if (
            not isinstance(base_tree, str)
            or FULL_SHA.fullmatch(base_tree) is None
        ):
            raise RuntimeError("Previous preservation checkpoint is invalid")
        tree_payload["base_tree"] = base_tree
    status, payload = api.request(
        "POST", f"repos/{repo}/git/trees", tree_payload
    )
    tree = require_response(status, payload, "create preservation tree")
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    if not isinstance(tree_sha, str) or FULL_SHA.fullmatch(tree_sha) is None:
        raise RuntimeError("GitHub returned an invalid preservation tree")
    commit_payload: dict[str, object] = {
        "message": (
            "csarc dev/next preservation "
            f"{validated['operation_id']} {validated['state']}"
        ),
        "tree": tree_sha,
        "parents": [previous_commit or str(validated["base_sha"])],
    }
    status, payload = api.request(
        "POST", f"repos/{repo}/git/commits", commit_payload
    )
    commit = require_response(status, payload, "create preservation checkpoint")
    commit_sha = commit.get("sha") if isinstance(commit, dict) else None
    if (
        not isinstance(commit_sha, str)
        or FULL_SHA.fullmatch(commit_sha) is None
    ):
        raise RuntimeError("GitHub returned an invalid preservation checkpoint")
    encoded = urllib.parse.quote(PRESERVATION_LEDGER_BRANCH, safe="")
    if previous_commit is None:
        status, payload = api.request(
            "POST",
            f"repos/{repo}/git/refs",
            {
                "ref": f"refs/heads/{PRESERVATION_LEDGER_BRANCH}",
                "sha": commit_sha,
            },
        )
    else:
        status, payload = api.request(
            "PATCH",
            f"repos/{repo}/git/refs/heads/{encoded}",
            {"sha": commit_sha, "force": False},
        )
    if status in {409, 422}:
        raise RuntimeError("Preservation ledger changed concurrently")
    require_response(status, payload, "advance preservation ledger")
    observed = read_preservation_record(api, repo)
    if observed != (commit_sha, validated):
        raise RuntimeError("Preservation ledger did not retain the checkpoint")
    return commit_sha, validated


def preservation_evidence(
    ledger_commit: str, record: dict[str, Any]
) -> dict[str, Any]:
    """Return the exact remote checkpoint bound into other evidence."""
    return {
        "ledger_ref": f"refs/heads/{PRESERVATION_LEDGER_BRANCH}",
        "ledger_commit": ledger_commit,
        "transaction": record,
    }


def preservation_authorization_statement(
    repo: str,
    number: int,
    base_sha: str,
    head_sha: str,
    operation_id: str,
    prepared_commit: str,
) -> str:
    """Return the exact two-person fallback authorization statement."""
    binding = {
        "base_sha": base_sha,
        "head_sha": head_sha,
        "ledger_commit": prepared_commit,
        "operation_id": operation_id,
        "pull_request": number,
        "repository": repo,
    }
    return (
        "Dev/next preservation authorization\n\n"
        f"`{canonical_json(binding)}`\n\n"
        "I authorize this exact prepared preservation transaction."
    )


def paged_items(api: API, repo: str, path: str) -> list[dict[str, Any]]:
    """Read every page of one GitHub REST collection."""
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        separator = "&" if "?" in path else "?"
        status, payload = api.request(
            "GET", f"repos/{repo}/{path}{separator}per_page=100&page={page}"
        )
        data = require_response(status, payload, f"read {path}")
        if not isinstance(data, list) or not all(
            isinstance(item, dict) for item in data
        ):
            raise RuntimeError(f"GitHub returned invalid {path}")
        items.extend(data)
        if len(data) < 100:
            return items
        page += 1


def require_temporary_authorizations(
    api: API,
    repo: str,
    number: int,
    base_sha: str,
    head_sha: str,
    operation_id: str,
    prepared_commit: str,
) -> list[dict[str, str]]:
    """Require two distinct humans to bind the unprotected ledger commit."""
    expected = preservation_authorization_statement(
        repo, number, base_sha, head_sha, operation_id, prepared_commit
    )
    accepted: dict[str, dict[str, str]] = {}
    for comment in paged_items(api, repo, f"issues/{number}/comments"):
        user = comment.get("user") or {}
        login = user.get("login") if isinstance(user, dict) else None
        if (
            comment.get("body") != expected
            or comment.get("author_association") not in MAINTAINER_ASSOCIATIONS
            or not isinstance(login, str)
            or user.get("type") != "User"
            or not isinstance(comment.get("html_url"), str)
        ):
            continue
        status, payload = api.request(
            "GET",
            f"repos/{repo}/collaborators/"
            f"{urllib.parse.quote(login, safe='')}/permission",
        )
        permission = require_response(
            status, payload, "read preservation authorizer permission"
        )
        if (
            isinstance(permission, dict)
            and permission.get("permission") in MAINTAINER_PERMISSIONS
            and (permission.get("user") or {}).get("login") == login
        ):
            accepted[login.casefold()] = {
                "actor": login,
                "url": str(comment["html_url"]),
            }
    if len(accepted) < 2:
        raise RuntimeError(
            "Temporary preservation requires two distinct human "
            "authorizations for the exact prepared ledger commit"
        )
    return [accepted[key] for key in sorted(accepted)]


def sync_secret_state(api: API, repo: str) -> str:
    """Return whether the dedicated hosted restoration secret is configured."""
    status, payload = api.request(
        "GET", f"repos/{repo}/actions/secrets/{SYNC_SECRET}"
    )
    if (
        status == 200
        and isinstance(payload, dict)
        and payload.get("name") == SYNC_SECRET
    ):
        return "configured"
    if status == 404:
        return "missing"
    return "unknown"


def manual_restoration_command(
    action: str,
    repo: str,
    number: int,
    head_sha: str,
    *,
    main_sha: str = "",
    operation_id: str = "",
    prepared_commit: str = "",
) -> str:
    """Return the exact command required for human-only restoration."""
    command = [
        "GH_TOKEN=<admin-token>",
        "python3 scripts/delivery_sync.py",
        action,
        f"--repo {repo}",
        f"--pr-number {number}",
        f"--head-sha {head_sha}",
    ]
    if main_sha:
        command.append(f"--main-sha {main_sha}")
    if operation_id:
        command.append(f"--operation-id {operation_id}")
    if prepared_commit:
        command.append(f"--prepared-ledger-commit {prepared_commit}")
    return " ".join(command)


def prepared_preservation_evidence(
    api: API,
    repo: str,
    number: int,
    ledger_commit: str,
    record: dict[str, Any],
    *,
    include_completion_mode: bool = True,
) -> dict[str, Any]:
    """Describe the prepared checkpoint and optional hosted capability."""
    evidence = preservation_evidence(ledger_commit, record)
    if record["mode"] == "ruleset-protected":
        evidence["completion_mode"] = "ruleset-protected"
        return evidence
    evidence["authorization_body"] = preservation_authorization_statement(
        repo,
        number,
        str(record["base_sha"]),
        str(record["head_sha"]),
        str(record["operation_id"]),
        ledger_commit,
    )
    if not include_completion_mode:
        return evidence
    evidence["completion_mode"] = (
        "hosted"
        if sync_secret_state(api, repo) == "configured"
        else "human-only"
    )
    return evidence


def require_preservation_identity(
    record: dict[str, Any],
    repo: str,
    number: int,
    base_sha: str,
    head_sha: str,
    operation_id: str | None = None,
) -> None:
    """Require one ledger operation to match the exact promotion."""
    expected_operation = preservation_operation(
        repo, number, base_sha, head_sha
    )
    if (
        record.get("repository") != repo
        or record.get("pull_request") != number
        or record.get("base_ref") != "main"
        or record.get("base_sha") != base_sha
        or record.get("head_ref") != "dev/next"
        or record.get("head_sha") != head_sha
        or record.get("operation_id") != expected_operation
        or (operation_id is not None and operation_id != expected_operation)
    ):
        raise RuntimeError("Preservation ledger belongs to another promotion")


def require_prepared_preservation(
    api: API,
    repo: str,
    number: int,
    base_sha: str,
    head_sha: str,
) -> tuple[str, dict[str, Any], list[dict[str, str]]]:
    """Refetch the exact prepared operation and its live safeguards."""
    checkpoint = read_preservation_record(api, repo)
    if checkpoint is None:
        raise RuntimeError("Dev/next has no prepared preservation transaction")
    ledger_commit, record = checkpoint
    require_preservation_identity(record, repo, number, base_sha, head_sha)
    if record.get("state") != "prepared":
        raise RuntimeError("Dev/next preservation transaction is not prepared")
    if record.get("mode") == "ruleset-protected":
        if (
            deletion_protection_state(api, repo) != "protected"
            or ledger_protection_state(api, repo) != "protected"
        ):
            raise RuntimeError("Dev/next or ledger protection changed")
        authorizations: list[dict[str, str]] = []
    elif (
        record.get("mode") != "temporary-auto-delete"
        or record.get("prior_auto_delete") is not True
        or repository_settings(api, repo).get("delete_branch_on_merge")
        is not False
    ):
        raise RuntimeError("Prepared transaction no longer owns cleanup")
    else:
        authorizations = require_temporary_authorizations(
            api,
            repo,
            number,
            base_sha,
            head_sha,
            str(record["operation_id"]),
            ledger_commit,
        )
        if read_preservation_record(api, repo) != (ledger_commit, record):
            raise RuntimeError("Authorized preservation ledger ref changed")
    return ledger_commit, record, authorizations


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
        or pull.get("state") != ("closed" if merged else "open")
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


def ref_protection_state(
    api: API, repo: str, branch: str, required_rules: set[str]
) -> str:
    """Classify effective ref rules without trusting an unreadable result."""
    encoded = urllib.parse.quote(branch, safe="")
    status, payload = api.request(
        "GET", f"repos/{repo}/rules/branches/{encoded}"
    )
    if status in {401, 403, 404}:
        return "blocked"
    if not 200 <= status < 300 or not isinstance(payload, list):
        return "unknown"
    observed = {
        str(rule.get("type")) for rule in payload if isinstance(rule, dict)
    }
    if required_rules <= observed:
        return "protected"
    return "unprotected"


def deletion_protection_state(api: API, repo: str) -> str:
    """Classify effective dev/next deletion protection."""
    return ref_protection_state(api, repo, "dev/next", {"deletion"})


def ledger_protection_state(api: API, repo: str) -> str:
    """Require deletion and non-fast-forward protection for the ledger."""
    return ref_protection_state(
        api,
        repo,
        PRESERVATION_LEDGER_BRANCH,
        {"deletion", "non_fast_forward"},
    )


def require_ledger_protection(api: API, repo: str) -> None:
    """Fail closed unless the append-only ledger ref is protected."""
    if ledger_protection_state(api, repo) != "protected":
        raise RuntimeError("Preservation ledger protection is unavailable")


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


def finish_restoration(  # noqa: C901
    api: API,
    repo: str,
    ledger_commit: str,
    record: dict[str, Any],
    terminal: str,
    *,
    main_sha: str | None = None,
    prepared_commit: str | None = None,
    hosted: bool = False,
) -> tuple[str, dict[str, Any]]:
    """CAS ownership, restore cleanup, and append the terminal state."""
    restoring = f"restoring-{terminal}"
    if terminal not in {"complete", "abort"}:
        raise ValueError("invalid preservation terminal state")
    terminal_state = "completed" if terminal == "complete" else "aborted"
    if record["mode"] == "ruleset-protected":
        if (
            deletion_protection_state(api, repo) != "protected"
            or ledger_protection_state(api, repo) != "protected"
        ):
            raise RuntimeError("Dev/next or ledger protection changed")
        final = {**record, "state": terminal_state}
        if terminal == "complete":
            final.update(
                main_sha=main_sha,
                prepared_ledger_commit=prepared_commit,
            )
        return append_preservation_record(api, repo, ledger_commit, final)

    if record.get("prior_auto_delete") is not True:
        raise RuntimeError("Transaction does not own automatic deletion")
    if record["state"] != restoring:
        setting = repository_settings(api, repo).get("delete_branch_on_merge")
        if record["state"] == "prepared" and setting is True:
            raise RuntimeError(
                "Prepared preservation has external setting drift; "
                "manual recovery is required"
            )
        if record["state"] == "preparing" and setting is False:
            raise RuntimeError(
                "Preparing preservation has ambiguous setting ownership; "
                "manual recovery is required"
            )
        if setting not in {True, False}:
            raise RuntimeError(
                "Automatic branch deletion setting is unavailable"
            )
        if hosted:
            if sync_secret_state(api, repo) != "configured":
                action = f"{terminal}-dev-next"
                raise RuntimeError(
                    "Hosted restoration requires CSARC_SYNC_TOKEN. Run: "
                    + manual_restoration_command(
                        action,
                        repo,
                        int(record["pull_request"]),
                        str(record["head_sha"]),
                        main_sha=main_sha or "",
                        operation_id=str(record["operation_id"]),
                        prepared_commit=prepared_commit or "",
                    )
                )
            set_auto_delete(api, repo, setting)
        restoring_record = {**record, "state": restoring}
        if terminal == "complete":
            restoring_record.update(
                main_sha=main_sha,
                prepared_ledger_commit=prepared_commit,
            )
        elif record["state"] == "prepared":
            restoring_record["prepared_ledger_commit"] = prepared_commit
        ledger_commit, record = append_preservation_record(
            api, repo, ledger_commit, restoring_record
        )
    elif terminal == "complete" and (
        record.get("main_sha") != main_sha
        or record.get("prepared_ledger_commit") != prepared_commit
    ):
        raise RuntimeError("Restoring preservation checkpoint is invalid")

    if read_preservation_record(api, repo) != (ledger_commit, record):
        raise RuntimeError("Preservation transaction changed concurrently")
    setting = repository_settings(api, repo).get("delete_branch_on_merge")
    if setting is False:
        set_auto_delete(api, repo, True)
    elif setting is not True:
        raise RuntimeError("Automatic branch deletion setting is unavailable")
    if read_preservation_record(api, repo) != (ledger_commit, record):
        raise RuntimeError(
            "Restoration ownership changed; manual recovery is required"
        )
    final = {**record, "state": terminal_state}
    return append_preservation_record(api, repo, ledger_commit, final)


def prepare_dev_next(  # noqa: C901
    api: API, repo: str, number: int, head_sha: str
) -> str:
    """Prevent auto-delete under one remote, resumable transaction."""
    pull = validate_promotion(api, repo, number, head_sha, merged=False)
    base = pull["base"]
    base_sha = base.get("sha")
    if not isinstance(base_sha, str) or FULL_SHA.fullmatch(base_sha) is None:
        raise RuntimeError("Promotion base SHA is invalid")
    if ref_sha(api, repo, "main") != base_sha:
        raise RuntimeError("Promotion base no longer matches current main")
    if ref_sha(api, repo, "dev/next") != head_sha:
        raise RuntimeError("dev/next no longer matches the promotion head")
    settings = repository_settings(api, repo)
    protection = deletion_protection_state(api, repo)
    ledger_protection = ledger_protection_state(api, repo)
    setting = settings.get("delete_branch_on_merge")
    if not isinstance(setting, bool):
        raise RuntimeError("Automatic branch deletion setting is unavailable")
    mode = (
        "ruleset-protected"
        if protection == ledger_protection == "protected"
        else "temporary-auto-delete"
    )
    operation_id = preservation_operation(repo, number, base_sha, head_sha)
    checkpoint = read_preservation_record(api, repo)
    if checkpoint is not None:
        ledger_commit, record = checkpoint
        same_operation = record.get("operation_id") == operation_id
        if same_operation:
            require_preservation_identity(
                record, repo, number, base_sha, head_sha, operation_id
            )
            if record.get("state") not in {"preparing", "prepared"}:
                raise RuntimeError(
                    "Preservation transaction requires manual terminal recovery"
                )
        else:
            if record.get("state") not in {"completed", "aborted"} or (
                record.get("state") == "completed"
                and record.get("base_sha") == base_sha
            ):
                raise RuntimeError(
                    "Another preservation transaction owns this main base"
                )
            if mode == "temporary-auto-delete" and setting is not True:
                raise RuntimeError(
                    "Automatic deletion was disabled outside this transaction"
                )
            record = {
                "schema_version": 1,
                "repository": repo,
                "pull_request": number,
                "base_ref": "main",
                "base_sha": base_sha,
                "head_ref": "dev/next",
                "head_sha": head_sha,
                "operation_id": operation_id,
                "mode": mode,
                "prior_auto_delete": setting,
                "state": "preparing",
            }
            ledger_commit, record = append_preservation_record(
                api, repo, ledger_commit, record
            )
    else:
        if mode == "temporary-auto-delete" and setting is not True:
            raise RuntimeError(
                "Automatic deletion was disabled outside this transaction"
            )
        record = {
            "schema_version": 1,
            "repository": repo,
            "pull_request": number,
            "base_ref": "main",
            "base_sha": base_sha,
            "head_ref": "dev/next",
            "head_sha": head_sha,
            "operation_id": operation_id,
            "mode": mode,
            "prior_auto_delete": setting,
            "state": "preparing",
        }
        ledger_commit, record = append_preservation_record(
            api, repo, None, record
        )

    if record["mode"] != mode:
        raise RuntimeError("Preservation mode changed during preparation")
    if record["state"] == "prepared":
        if mode == "ruleset-protected":
            if (
                deletion_protection_state(api, repo) != "protected"
                or ledger_protection_state(api, repo) != "protected"
            ):
                raise RuntimeError("Dev/next or ledger protection changed")
        else:
            live_setting = repository_settings(api, repo).get(
                "delete_branch_on_merge"
            )
            if live_setting is True:
                raise RuntimeError(
                    "Prepared preservation has external setting drift; "
                    "manual recovery is required"
                )
            if live_setting is not False:
                raise RuntimeError(
                    "Automatic branch deletion setting is unavailable"
                )
            if read_preservation_record(api, repo) != (
                ledger_commit,
                record,
            ):
                raise RuntimeError(
                    "Preservation transaction changed concurrently"
                )
        return canonical_json(
            prepared_preservation_evidence(
                api, repo, number, ledger_commit, record
            )
        )

    if (
        validate_promotion(api, repo, number, head_sha, merged=False)[
            "base"
        ].get("sha")
        != base_sha
    ):
        raise RuntimeError("Promotion changed after transaction acquisition")
    if (
        ref_sha(api, repo, "main") != base_sha
        or ref_sha(api, repo, "dev/next") != head_sha
    ):
        raise RuntimeError(
            "Promotion refs changed after transaction acquisition"
        )
    observed = read_preservation_record(api, repo)
    if observed != (ledger_commit, record):
        raise RuntimeError("Preservation transaction changed concurrently")
    disable_attempted = False
    try:
        if mode == "ruleset-protected":
            if (
                deletion_protection_state(api, repo) != "protected"
                or ledger_protection_state(api, repo) != "protected"
            ):
                raise RuntimeError("Dev/next or ledger protection changed")
        else:
            live_setting = repository_settings(api, repo).get(
                "delete_branch_on_merge"
            )
            if live_setting is True:
                disable_attempted = True
                set_auto_delete(api, repo, False)
            elif live_setting is False:
                raise RuntimeError(
                    "Preparing preservation has ambiguous setting ownership; "
                    "manual recovery is required"
                )
            else:
                raise RuntimeError(
                    "Automatic branch deletion setting is unavailable"
                )
            if (
                repository_settings(api, repo).get("delete_branch_on_merge")
                is not False
            ):
                raise RuntimeError("Automatic branch deletion was not disabled")
        if (
            validate_promotion(api, repo, number, head_sha, merged=False)[
                "base"
            ].get("sha")
            != base_sha
        ):
            raise RuntimeError("Promotion changed while enabling preservation")
        if (
            ref_sha(api, repo, "main") != base_sha
            or ref_sha(api, repo, "dev/next") != head_sha
        ):
            raise RuntimeError(
                "Promotion refs changed while enabling preservation"
            )
        if read_preservation_record(api, repo) != (ledger_commit, record):
            raise RuntimeError("Preservation transaction changed concurrently")
        prepared = {**record, "state": "prepared"}
        ledger_commit, prepared = append_preservation_record(
            api, repo, ledger_commit, prepared
        )
    except RuntimeError as error:
        if disable_attempted:
            raise RuntimeError(
                "Cleanup update outcome is ambiguous; manual recovery is "
                "required"
            ) from error
        raise
    return canonical_json(
        prepared_preservation_evidence(
            api, repo, number, ledger_commit, prepared
        )
    )


def inspect_dev_next(api: API, repo: str, number: int, head_sha: str) -> str:
    """Return the prepared checkpoint without changing repository state."""
    pull = validate_promotion(api, repo, number, head_sha, merged=False)
    base_sha = pull.get("base", {}).get("sha")
    if not isinstance(base_sha, str) or FULL_SHA.fullmatch(base_sha) is None:
        raise RuntimeError("Promotion base SHA is invalid")
    if ref_sha(api, repo, "main") != base_sha:
        raise RuntimeError("Promotion base no longer matches current main")
    if ref_sha(api, repo, "dev/next") != head_sha:
        raise RuntimeError("dev/next no longer matches the promotion head")
    ledger_commit, record, authorizations = require_prepared_preservation(
        api, repo, number, base_sha, head_sha
    )
    evidence = prepared_preservation_evidence(
        api,
        repo,
        number,
        ledger_commit,
        record,
        include_completion_mode=False,
    )
    evidence["human_authorizations"] = authorizations
    return canonical_json(evidence)


def complete_dev_next(  # noqa: C901
    api: API,
    repo: str,
    number: int,
    head_sha: str,
    main_sha: str,
    operation_id: str,
    prepared_commit: str,
    *,
    hosted: bool = False,
    admin_api: API | None = None,
) -> str:
    """Verify continuity and close the exact remote transaction."""
    if FULL_SHA.fullmatch(main_sha) is None:
        raise RuntimeError("Merged main SHA is required")
    pull = validate_promotion(api, repo, number, head_sha, merged=True)
    base = pull.get("base")
    base_sha = base.get("sha") if isinstance(base, dict) else None
    if not isinstance(base_sha, str):
        raise RuntimeError("Merged promotion base SHA is invalid")
    checkpoint = read_preservation_record(api, repo)
    if checkpoint is None:
        raise RuntimeError("Preservation transaction is missing")
    ledger_commit, record = checkpoint
    require_preservation_identity(
        record, repo, number, base_sha, head_sha, operation_id
    )
    if record.get("mode") == "ruleset-protected":
        if deletion_protection_state(api, repo) != "protected":
            raise RuntimeError("Dev/next deletion protection changed")
        require_ledger_protection(api, repo)
    elif record.get("mode") == "temporary-auto-delete" and hosted:
        if admin_api is None:
            raise RuntimeError(
                "Hosted restoration requires CSARC_SYNC_TOKEN. Run: "
                + manual_restoration_command(
                    "complete-dev-next",
                    repo,
                    number,
                    head_sha,
                    main_sha=main_sha,
                    operation_id=operation_id,
                    prepared_commit=prepared_commit,
                )
            )
        if read_preservation_record(admin_api, repo) != checkpoint:
            raise RuntimeError("Authorized preservation ledger ref changed")
        pull = validate_promotion(
            admin_api, repo, number, head_sha, merged=True
        )
        api = admin_api
    if record.get("state") == "completed":
        if (
            record.get("main_sha") != main_sha
            or record.get("prepared_ledger_commit") != prepared_commit
            or (
                record.get("mode") == "temporary-auto-delete"
                and repository_settings(api, repo).get("delete_branch_on_merge")
                is not True
            )
        ):
            raise RuntimeError("Completed preservation transaction is invalid")
        if record.get("mode") == "temporary-auto-delete":
            require_temporary_authorizations(
                api,
                repo,
                number,
                base_sha,
                head_sha,
                operation_id,
                prepared_commit,
            )
        return canonical_json(preservation_evidence(ledger_commit, record))
    if record.get("state") not in {"prepared", "restoring-complete"}:
        raise RuntimeError(
            "Remote preservation checkpoint does not match evidence"
        )
    if record.get("prepared_ledger_commit", prepared_commit) != prepared_commit:
        raise RuntimeError(
            "Remote preservation checkpoint does not match evidence"
        )
    if record.get("state") == "prepared" and ledger_commit != prepared_commit:
        raise RuntimeError(
            "Remote preservation checkpoint does not match evidence"
        )
    if record.get("mode") == "temporary-auto-delete":
        require_temporary_authorizations(
            api,
            repo,
            number,
            base_sha,
            head_sha,
            operation_id,
            prepared_commit,
        )
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
    if read_preservation_record(api, repo) != (ledger_commit, record):
        raise RuntimeError("Preservation transaction changed concurrently")
    ledger_commit, completed = finish_restoration(
        api,
        repo,
        ledger_commit,
        record,
        "complete",
        main_sha=main_sha,
        prepared_commit=prepared_commit,
        hosted=hosted,
    )
    return canonical_json(preservation_evidence(ledger_commit, completed))


def abort_dev_next(  # noqa: C901
    api: API,
    repo: str,
    number: int,
    head_sha: str,
    operation_id: str | None,
    *,
    hosted: bool = False,
    admin_api: API | None = None,
) -> str:
    """Restore cleanup after an exact promotion was closed without merging."""
    pull = pull_request(api, repo, number)
    base = pull.get("base")
    head = pull.get("head")
    head_repo = head.get("repo") if isinstance(head, dict) else None
    base_sha = base.get("sha") if isinstance(base, dict) else None
    if (
        pull.get("state") != "closed"
        or pull.get("merged") is not False
        or not isinstance(base_sha, str)
        or not isinstance(base, dict)
        or base.get("ref") != "main"
        or not isinstance(head, dict)
        or head.get("ref") != "dev/next"
        or head.get("sha") != head_sha
        or not isinstance(head_repo, dict)
        or head_repo.get("full_name") != repo
    ):
        raise RuntimeError("Only an exact closed, unmerged promotion can abort")
    checkpoint = read_preservation_record(api, repo)
    if checkpoint is None:
        raise RuntimeError("Preservation transaction is missing")
    ledger_commit, record = checkpoint
    require_preservation_identity(
        record, repo, number, base_sha, head_sha, operation_id
    )
    if record.get("mode") == "ruleset-protected":
        if deletion_protection_state(api, repo) != "protected":
            raise RuntimeError("Dev/next deletion protection changed")
        require_ledger_protection(api, repo)
    elif record.get("mode") == "temporary-auto-delete" and hosted:
        if admin_api is None:
            raise RuntimeError(
                "Hosted restoration requires CSARC_SYNC_TOKEN. Run: "
                + manual_restoration_command(
                    "abort-dev-next",
                    repo,
                    number,
                    head_sha,
                    operation_id=str(record["operation_id"]),
                )
            )
        if read_preservation_record(admin_api, repo) != checkpoint:
            raise RuntimeError("Authorized preservation ledger ref changed")
        pull = pull_request(admin_api, repo, number)
        if pull.get("state") != "closed" or pull.get("merged") is not False:
            raise RuntimeError("Live promotion changed before abort")
        api = admin_api
    prepared_commit = (
        ledger_commit
        if record.get("state") == "prepared"
        else record.get("prepared_ledger_commit")
    )
    if record.get("mode") == "temporary-auto-delete" and record.get(
        "state"
    ) in {"prepared", "restoring-abort", "aborted"}:
        if not isinstance(prepared_commit, str):
            raise RuntimeError("Authorized prepared checkpoint is missing")
        require_temporary_authorizations(
            api,
            repo,
            number,
            base_sha,
            head_sha,
            str(record["operation_id"]),
            prepared_commit,
        )
    if record.get("state") == "aborted":
        if (
            record.get("mode") == "temporary-auto-delete"
            and repository_settings(api, repo).get("delete_branch_on_merge")
            is not True
        ):
            raise RuntimeError("Aborted preservation did not restore cleanup")
        return canonical_json(preservation_evidence(ledger_commit, record))
    if record.get("state") not in {
        "preparing",
        "prepared",
        "restoring-abort",
    }:
        raise RuntimeError("Preservation transaction cannot be aborted")
    ledger_commit, aborted = finish_restoration(
        api,
        repo,
        ledger_commit,
        record,
        "abort",
        prepared_commit=(
            prepared_commit if isinstance(prepared_commit, str) else None
        ),
        hosted=hosted,
    )
    return canonical_json(preservation_evidence(ledger_commit, aborted))


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
    if head_ref != "dev/next":
        return f"exact queue candidate for {head_ref}"
    ledger_commit, record, _authorizations = require_prepared_preservation(
        api, repo, number, base_sha, head_sha
    )
    return (
        f"{record['mode']}; transaction "
        f"{record['operation_id']} at {ledger_commit}"
    )


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


def invalidate_stale_pr_policy(api: API, repo: str, main_sha: str) -> None:
    """Invalidate the combined PR policy whenever main advances."""
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
        if includes_main(compare(api, repo, main_sha, head_sha)):
            continue
        status_code, status_payload = api.request(
            "POST",
            f"repos/{repo}/statuses/{head_sha}",
            {
                "state": "failure",
                "context": "title",
                "description": (
                    "PR head must synchronize current main before merge"
                ),
            },
        )
        require_response(
            status_code, status_payload, "invalidate stale PR policy"
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
    invalidate_stale_pr_policy(api, repo, main_sha)
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


def main() -> None:  # noqa: C901
    """Run the PR gate or main-push reconciliation mode."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "gate",
            "merge-group-gate",
            "reconcile",
            "prepare-dev-next",
            "inspect-dev-next",
            "complete-dev-next",
            "abort-dev-next",
        ),
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--delivery-base", default="")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--head-ref", default="")
    parser.add_argument("--main-sha", default="")
    parser.add_argument("--pr-number", type=int, default=0)
    parser.add_argument("--operation-id", default="")
    parser.add_argument("--prepared-ledger-commit", default="")
    parser.add_argument("--hosted", action="store_true")
    parser.add_argument("--queue-ref", default="")
    parser.add_argument("--queue-sha", default="")
    parser.add_argument("--base-sha", default="")
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
    sync_token = os.environ.get(SYNC_SECRET, "")
    admin_api = GitHubAPI(sync_token) if sync_token else None
    try:
        if args.command == "gate":
            if not args.base or not args.head_sha:
                raise RuntimeError("gate requires --base and --head-sha")
            result = gate(
                api,
                args.repo,
                args.base,
                args.head_sha,
                args.delivery_base,
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
        elif args.command == "prepare-dev-next":
            print(  # noqa: T201
                prepare_dev_next(api, args.repo, args.pr_number, args.head_sha)
            )
        elif args.command == "inspect-dev-next":
            print(  # noqa: T201
                inspect_dev_next(api, args.repo, args.pr_number, args.head_sha)
            )
        elif args.command == "complete-dev-next":
            if not args.operation_id or not args.prepared_ledger_commit:
                raise RuntimeError(
                    "complete-dev-next requires the prepared operation and "
                    "ledger commit"
                )
            print(  # noqa: T201
                complete_dev_next(
                    api,
                    args.repo,
                    args.pr_number,
                    args.head_sha,
                    args.main_sha,
                    args.operation_id,
                    args.prepared_ledger_commit,
                    hosted=args.hosted,
                    admin_api=admin_api,
                )
            )
        elif args.command == "abort-dev-next":
            print(  # noqa: T201
                abort_dev_next(
                    api,
                    args.repo,
                    args.pr_number,
                    args.head_sha,
                    args.operation_id or None,
                    hosted=args.hosted,
                    admin_api=admin_api,
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
