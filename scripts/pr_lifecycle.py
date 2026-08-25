#!/usr/bin/env python3
"""Serialize pull-request lifecycle writes across local tasks."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from ci_tier import classify as classify_ci
from promotion_gate import (
    failed_pull_request_run_urls,
    has_exact_quota_note,
    require_zero_step_run,
)
from promotion_gate import (
    route_for as promotion_route_for,
)

LEASE_SCHEMA = 2
LEASE_STATUS_SCHEMA = 1
LEASE_STATUS_INTERFACE = "csarc-pr-lifecycle-lease-status/v1"
MAX_TTL_SECONDS = 7200
MIN_OPERATION_SECONDS = 30
MAINTAINER_ASSOCIATIONS = {"MEMBER", "OWNER"}
SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
OWNER = re.compile(r"[A-Za-z0-9._/@:-]{1,200}")
ACTOR = re.compile(r"[A-Za-z0-9_.-]+(?:\[bot\])?")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
UNCHECKED = re.compile(r"(?m)^\s*[-*+]\s+\[\s*\]")
CLOSING_REFERENCE = re.compile(
    r"(?i)\b(?:close(?:s|d)?|fix(?:es|ed)?|resolve(?:s|d)?)\s+"
    r"((?:https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/|"
    r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#)[1-9][0-9]*)(?!\d)"
)
LINKING_REFERENCE = re.compile(
    r"(?i)\b(?:close(?:s|d)?|fix(?:es|ed)?|resolve(?:s|d)?|refs?)\s+"
    r"((?:https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/|"
    r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#)[1-9][0-9]*)(?!\d)"
)
BLOCKER = re.compile(
    r"(?i)^(?:blocked|blocker)\s*:|^\[merge-blocker\]|^\[P[01]\]"
)
BLOCKER_RESOLVED = re.compile(
    r"(?i)^merge blocker resolved\s*:|^\[merge-blocker-resolved\]"
)
DRAFT_EVENTS = {"convert_to_draft", "converted_to_draft"}
SUCCESSFUL_CHECK_CONCLUSIONS = {"neutral", "skipped", "success"}
MAINTAINER_PERMISSIONS = {"admin", "maintain"}
LEASE_CORE_FIELDS = (
    "schema_version",
    "repository",
    "pull_request",
    "head_sha",
    "head_tree",
    "base_ref",
    "base_sha",
    "default_branch",
    "owner",
    "actor",
    "capability_digest",
    "acquired_at",
    "expires_at",
    "refs",
    "reclaimed_commits",
)


def canonical_json(value: object) -> str:
    """Return stable compact JSON for comments and commit messages."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def issue_references(
    body: str, repo: str, *, closing_only: bool = False
) -> list[tuple[str, int]]:
    """Return GitHub Issue links with an explicit repository identity."""
    references: list[tuple[str, int]] = []
    pattern = CLOSING_REFERENCE if closing_only else LINKING_REFERENCE
    for match in pattern.finditer(body):
        target = match.group(1)
        if target.startswith("#"):
            target_repo, number = repo, target[1:]
        elif target.casefold().startswith("https://github.com/"):
            path = target[len("https://github.com/") :]
            owner, name, _, number = path.split("/")
            target_repo = f"{owner}/{name}"
        else:
            target_repo, number = target.rsplit("#", 1)
        references.append((target_repo, int(number)))
    return references


def closing_issue_references(body: str, repo: str) -> list[tuple[str, int]]:
    """Return only closing GitHub Issue references."""
    return issue_references(body, repo, closing_only=True)


def parse_time(value: object, label: str) -> datetime:
    """Parse an aware GitHub timestamp or fail closed."""
    if not isinstance(value, str):
        raise RuntimeError(f"{label} has no timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError(f"{label} has an invalid timestamp") from error
    if parsed.tzinfo is None:
        raise RuntimeError(f"{label} timestamp has no timezone")
    return parsed.astimezone(UTC)


def run(
    command: list[str],
    *,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Run one local command and return stdout."""
    result = subprocess.run(  # noqa: S603
        command,
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed: {' '.join(command)}: {detail}")
    return result.stdout.strip()


class GitHub:
    """Small GitHub CLI adapter that never handles a token directly."""

    def get(self, repo: str, path: str) -> object:
        """Read one REST resource."""
        endpoint = f"repos/{repo}"
        if path:
            endpoint = f"{endpoint}/{path}"
        return json.loads(run(["gh", "api", endpoint]))

    def viewer(self, explicit_actor: str = "") -> str:
        """Return a verified user, or an explicitly supplied App actor."""
        if explicit_actor:
            if ACTOR.fullmatch(explicit_actor) is None:
                raise RuntimeError("Explicit GitHub actor is invalid")
            return explicit_actor
        try:
            payload = json.loads(run(["gh", "api", "user"]))
            login = payload.get("login") if isinstance(payload, dict) else None
            if isinstance(login, str) and login:
                return login
        except RuntimeError as error:
            raise RuntimeError(
                "Authenticated GitHub actor is unavailable; GitHub App "
                "callers must pass --actor from trusted action output"
            ) from error
        raise RuntimeError("Authenticated GitHub actor is unavailable")

    def pages(self, repo: str, path: str) -> list[dict[str, Any]]:
        """Read and flatten every page of a REST collection."""
        payload = json.loads(
            run(
                [
                    "gh",
                    "api",
                    "--paginate",
                    "--slurp",
                    "-H",
                    "Accept: application/vnd.github+json",
                    f"repos/{repo}/{path}",
                ]
            )
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"GitHub collection {path} is not a list")
        pages = (
            payload if payload and isinstance(payload[0], list) else [payload]
        )
        items = [item for page in pages for item in page]
        if not all(isinstance(item, dict) for item in items):
            raise RuntimeError(f"GitHub collection {path} has invalid entries")
        return items

    def collection(
        self,
        repo: str,
        path: str,
        key: str,
        response_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read one keyed collection across every REST response page."""
        payload = json.loads(
            run(
                [
                    "gh",
                    "api",
                    "--paginate",
                    "--slurp",
                    "-H",
                    "Accept: application/vnd.github+json",
                    f"repos/{repo}/{path}",
                ]
            )
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"GitHub collection {path} is not paginated")
        items: list[dict[str, Any]] = []
        for page in payload:
            if not isinstance(page, dict) or not isinstance(
                page.get(key), list
            ):
                raise RuntimeError(f"GitHub collection {path} has no {key}")
            if response_sha is not None and page.get("sha") != response_sha:
                raise RuntimeError(
                    f"GitHub collection {path} is for another SHA"
                )
            entries = page[key]
            if not all(isinstance(item, dict) for item in entries):
                raise RuntimeError(
                    f"GitHub collection {path} has invalid entries"
                )
            items.extend(entries)
        return items

    def merge(
        self, repo: str, pr_number: int, head_sha: str, title: str
    ) -> dict[str, Any]:
        """Synchronously merge one exact PR head through the REST API."""
        payload = run(
            [
                "gh",
                "api",
                "--method",
                "PUT",
                f"repos/{repo}/pulls/{pr_number}/merge",
                "--input",
                "-",
            ],
            input_text=json.dumps(
                {
                    "sha": head_sha,
                    "merge_method": "squash",
                    "commit_title": title,
                }
            ),
        )
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise RuntimeError("GitHub merge response is invalid")
        return result

    def comment(self, repo: str, pr_number: int, body: str) -> dict[str, Any]:
        """Create one audit comment."""
        payload = run(
            [
                "gh",
                "api",
                "--method",
                "POST",
                f"repos/{repo}/issues/{pr_number}/comments",
                "--input",
                "-",
            ],
            input_text=json.dumps({"body": body}),
        )
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise RuntimeError("GitHub comment response is invalid")
        return result

    def close_issue(self, repo: str, issue_number: int) -> dict[str, Any]:
        """Close one verified Issue as completed."""
        payload = run(
            [
                "gh",
                "api",
                "--method",
                "PATCH",
                f"repos/{repo}/issues/{issue_number}",
                "--input",
                "-",
            ],
            input_text=json.dumps(
                {"state": "closed", "state_reason": "completed"}
            ),
        )
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise RuntimeError("GitHub Issue close response is invalid")
        return result


class GitHubReader(Protocol):
    """Structural interface shared by read-only policy entrypoints."""

    def get(self, repo: str, path: str) -> object:
        """Read one REST resource."""


def remote_repository(url: str) -> str:
    """Resolve an origin URL to its GitHub owner/name identity."""
    patterns = (
        r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?$",
        r"ssh://git@github\.com/([^/]+/[^/]+?)(?:\.git)?$",
        r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, url)
        if match:
            return match.group(1)
    raise RuntimeError("origin must be the requested github.com repository")


def require_origin(repo: str) -> None:
    """Require local origin to be the requested GitHub repository."""
    origin = remote_repository(run(["git", "remote", "get-url", "origin"]))
    if origin.casefold() != repo.casefold():
        raise RuntimeError("origin does not match the requested repository")


def pr_ref(pr_number: int) -> str:
    """Return the repository-wide lock ref for one pull request."""
    return f"refs/heads/csarc/leases/pr-{pr_number}"


def base_lane_ref(base_ref: str) -> str:
    """Return one collision-resistant lease ref for a destination branch."""
    digest = hashlib.sha256(base_ref.encode()).hexdigest()
    return f"refs/heads/csarc/leases/base-{digest}"


def lease_refs(pull: dict[str, Any], default_branch: str) -> list[str]:
    """Lock the PR and its shared destination lane."""
    del default_branch
    base = pull.get("base") or {}
    base_ref = base.get("ref")
    if not isinstance(base_ref, str) or not base_ref:
        raise RuntimeError("Pull request base branch is unavailable")
    return [pr_ref(int(pull["number"])), base_lane_ref(base_ref)]


def live_pull(
    github: GitHubReader, repo: str, pr_number: int, head_sha: str
) -> dict[str, Any]:
    """Require one open pull request at the exact expected head."""
    payload = github.get(repo, f"pulls/{pr_number}")
    if not isinstance(payload, dict):
        raise RuntimeError("Live pull request response is invalid")
    head = payload.get("head") or {}
    if (
        payload.get("number") != pr_number
        or payload.get("state") != "open"
        or payload.get("merged") is not False
        or head.get("sha") != head_sha
    ):
        raise RuntimeError("Live pull request state or head has drifted")
    return payload


def branch_sha(github: GitHubReader, repo: str, branch: str) -> str:
    """Return the exact live commit of one destination branch."""
    payload = github.get(
        repo, f"git/ref/heads/{urllib.parse.quote(branch, safe='')}"
    )
    sha = (
        (payload.get("object") or {}).get("sha")
        if isinstance(payload, dict)
        else None
    )
    if not isinstance(sha, str) or SHA.fullmatch(sha) is None:
        raise RuntimeError("Destination branch ref is unavailable")
    return sha


def remote_ref(ref: str) -> str | None:
    """Return the exact origin ref SHA, rejecting ambiguous output."""
    output = run(["git", "ls-remote", "--refs", "origin", ref])
    if not output:
        return None
    lines = output.splitlines()
    if len(lines) != 1:
        raise RuntimeError(f"Remote lease ref is ambiguous: {ref}")
    try:
        sha, observed_ref = lines[0].split("\t", 1)
    except ValueError as error:
        raise RuntimeError(f"Remote lease ref is invalid: {ref}") from error
    if observed_ref != ref or SHA.fullmatch(sha) is None:
        raise RuntimeError(f"Remote lease ref is invalid: {ref}")
    return sha


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Atomically write evidence without following an output symlink."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise RuntimeError(f"Output must be a regular file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}."
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_lease(path: Path) -> dict[str, Any]:
    """Load structurally valid lease evidence."""
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Lease evidence must be a regular file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != LEASE_SCHEMA
    ):
        raise RuntimeError("Lease evidence schema is invalid")
    required = {
        "repository": str,
        "pull_request": int,
        "head_sha": str,
        "head_tree": str,
        "base_ref": str,
        "base_sha": str,
        "default_branch": str,
        "owner": str,
        "actor": str,
        "capability": str,
        "capability_digest": str,
        "acquired_at": str,
        "expires_at": str,
        "lease_commit": str,
        "refs": list,
        "reclaimed_commits": list,
        "audit_url": str,
    }
    if any(
        not isinstance(payload.get(key), kind) for key, kind in required.items()
    ):
        raise RuntimeError("Lease evidence is incomplete")
    if (
        SHA.fullmatch(payload["head_sha"]) is None
        or SHA.fullmatch(payload["head_tree"]) is None
        or SHA.fullmatch(payload["base_sha"]) is None
        or SHA.fullmatch(payload["lease_commit"]) is None
    ):
        raise RuntimeError("Lease evidence has an invalid SHA")
    if (
        REPOSITORY.fullmatch(payload["repository"]) is None
        or OWNER.fullmatch(payload["owner"]) is None
        or ACTOR.fullmatch(payload["actor"]) is None
        or SHA256.fullmatch(payload["capability"]) is None
        or SHA256.fullmatch(payload["capability_digest"]) is None
        or not payload["base_ref"]
        or not payload["default_branch"]
        or payload["pull_request"] < 1
    ):
        raise RuntimeError("Lease evidence has invalid identity fields")
    if set(payload) != {
        *LEASE_CORE_FIELDS,
        "capability",
        "lease_commit",
        "audit_url",
    }:
        raise RuntimeError("Lease evidence contains unexpected fields")
    if (
        hashlib.sha256(payload["capability"].encode()).hexdigest()
        != payload["capability_digest"]
    ):
        raise RuntimeError("Lease capability does not match its remote digest")
    if not all(
        isinstance(commit, str) and SHA.fullmatch(commit)
        for commit in payload["reclaimed_commits"]
    ):
        raise RuntimeError("Lease reclaim history is invalid")
    validate_audit_url(payload)
    validate_refs(payload)
    return payload


def validate_refs(lease: dict[str, Any]) -> None:
    """Limit evidence to the PR ref and deterministic destination lane."""
    refs = lease.get("refs")
    expected = [
        pr_ref(int(lease["pull_request"])),
        base_lane_ref(str(lease["base_ref"])),
    ]
    if (
        not isinstance(refs, list)
        or not all(isinstance(ref, str) for ref in refs)
        or refs != expected
    ):
        raise RuntimeError("Lease refs are invalid")


def audit_comment_id(lease: dict[str, Any]) -> str:
    """Validate and return the lease audit comment identifier."""
    parsed = urllib.parse.urlparse(str(lease.get("audit_url", "")))
    expected = f"/{lease['repository']}/pull/{lease['pull_request']}"
    match = re.fullmatch(r"issuecomment-([0-9]+)", parsed.fragment)
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() != "github.com"
        or parsed.path.casefold() != expected.casefold()
        or match is None
    ):
        raise RuntimeError("Lease audit URL is invalid")
    return match.group(1)


def validate_audit_url(lease: dict[str, Any]) -> None:
    """Reject evidence whose audit URL is not bound to its pull request."""
    audit_comment_id(lease)


def validate_audit_comment(lease: dict[str, Any], comment: object) -> None:
    """Bind an audit response to the exact PR, actor, and public evidence."""
    user = comment.get("user") or {} if isinstance(comment, dict) else {}
    expected_type = "Bot" if str(lease["actor"]).endswith("[bot]") else "User"
    if (
        not isinstance(comment, dict)
        or comment.get("html_url") != lease["audit_url"]
        or comment.get("issue_url")
        != "https://api.github.com/repos/"
        f"{lease['repository']}/issues/{lease['pull_request']}"
        or comment.get("body") != audit_message(lease)
        or str(user.get("login", "")).casefold()
        != str(lease["actor"]).casefold()
        or user.get("type") != expected_type
    ):
        raise RuntimeError("Remote lease audit comment is invalid")


def lease_core(lease: dict[str, Any]) -> dict[str, object]:
    """Return the exact fields committed as immutable lease evidence."""
    return {field: lease[field] for field in LEASE_CORE_FIELDS}


def lease_message(lease: dict[str, Any]) -> str:
    """Return the only valid lease commit message."""
    return (
        f"chore: lease PR #{lease['pull_request']}\n\n"
        f"{canonical_json(lease_core(lease))}"
    )


def audit_message(lease: dict[str, Any]) -> str:
    """Return public lease evidence without the raw capability."""
    public = {**lease_core(lease), "lease_commit": lease["lease_commit"]}
    return (
        "PR lifecycle lease acquired\n\n"
        f"`{canonical_json(public)}`\n\n"
        "All automated Ready, Draft, authorization, metadata, and merge "
        "writes for this PR are serialized by the refs above."
    )


def require_lease(
    github: GitHub,
    lease: dict[str, Any],
    repo: str,
    pr_number: int,
    head_sha: str,
) -> None:
    """Revalidate lease identity, scope, and immutable remote commit."""
    require_origin(repo)
    if (
        lease["repository"].casefold() != repo.casefold()
        or lease["pull_request"] != pr_number
        or lease["head_sha"] != head_sha
    ):
        raise RuntimeError("Lease does not match the requested pull request")
    validate_refs(lease)
    if parse_time(lease["expires_at"], "Lease") <= datetime.now(
        UTC
    ) + timedelta(seconds=MIN_OPERATION_SECONDS):
        raise RuntimeError(
            "Lease expired; fail closed and inspect it before release"
        )
    require_committed_lease(github, lease)
    pull = live_pull(github, repo, pr_number, head_sha)
    repository = github.get(repo, "")
    base = pull.get("base") or {}
    if (
        not isinstance(repository, dict)
        or lease["default_branch"] != repository.get("default_branch")
        or lease["base_ref"] != base.get("ref")
        or lease["base_sha"] != base.get("sha")
        or lease["refs"] != lease_refs(pull, lease["default_branch"])
    ):
        raise RuntimeError(
            "Pull request base or destination lease scope drifted"
        )
    if branch_sha(github, repo, lease["base_ref"]) != lease["base_sha"]:
        raise RuntimeError("Pull request destination branch advanced")


def require_committed_lease(github: GitHub, lease: dict[str, Any]) -> None:
    """Match mutable evidence to its canonical remote commit and refs."""
    capability = str(lease.get("capability", ""))
    digest = hashlib.sha256(capability.encode()).hexdigest()
    if not secrets.compare_digest(digest, str(lease["capability_digest"])):
        raise RuntimeError("Lease capability is invalid")
    refs = lease["refs"]
    for ref in refs:
        if remote_ref(ref) != lease["lease_commit"]:
            raise RuntimeError(f"Lease ownership changed or is missing: {ref}")
    repo = lease["repository"]
    head_sha = lease["head_sha"]
    lease_commit = github.get(repo, f"git/commits/{lease['lease_commit']}")
    head_commit = github.get(repo, f"git/commits/{head_sha}")
    if not isinstance(lease_commit, dict) or not isinstance(head_commit, dict):
        raise RuntimeError("Remote lease commit metadata is unavailable")
    parents = lease_commit.get("parents")
    tree = lease_commit.get("tree") or {}
    head_tree = head_commit.get("tree") or {}
    if (
        lease_commit.get("sha") != lease["lease_commit"]
        or lease_commit.get("message") != lease_message(lease)
        or not isinstance(parents, list)
        or [item.get("sha") for item in parents if isinstance(item, dict)]
        != [head_sha]
        or tree.get("sha") != lease["head_tree"]
        or head_tree.get("sha") != lease["head_tree"]
    ):
        raise RuntimeError(
            "Remote lease commit does not match canonical evidence"
        )
    comment_id = audit_comment_id(lease)
    comment = github.get(repo, f"issues/comments/{comment_id}")
    validate_audit_comment(lease, comment)


def require_caller(
    lease: dict[str, Any], owner: str, actor: str, github: GitHub
) -> None:
    """Require the task owner and actor that acquired the lease."""
    if lease["owner"] != owner:
        raise RuntimeError("Task owner does not hold this lifecycle lease")
    if str(lease["actor"]).casefold() != github.viewer(actor).casefold():
        raise RuntimeError(
            "Authenticated GitHub actor changed after lease acquisition"
        )


def release_refs(lease: dict[str, Any]) -> None:
    """Delete only refs that still point at this exact lease commit."""
    validate_refs(lease)
    commit = lease["lease_commit"]
    refs = lease["refs"]
    command = ["git", "push", "--atomic", "--porcelain"]
    command.extend(f"--force-with-lease={ref}:{commit}" for ref in refs)
    command.append("origin")
    command.extend(f":{ref}" for ref in refs)
    run(command)


def confirm_refs(lease: dict[str, Any]) -> None:
    """CAS every lease ref immediately before the merge mutation."""
    validate_refs(lease)
    if parse_time(lease["expires_at"], "Lease") <= datetime.now(UTC):
        raise RuntimeError("Lease expired before the merge mutation")
    commit = lease["lease_commit"]
    refs = lease["refs"]
    command = ["git", "push", "--atomic", "--porcelain"]
    command.extend(f"--force-with-lease={ref}:{commit}" for ref in refs)
    command.append("origin")
    command.extend(f"{commit}:{ref}" for ref in refs)
    run(command)


def create_refs(
    commit: str,
    refs: list[str],
    expected: dict[str, str | None] | None = None,
) -> None:
    """Atomically create absent lease refs without overwriting a winner."""
    expected = expected or {ref: None for ref in refs}
    command = ["git", "push", "--atomic", "--porcelain"]
    command.extend(
        f"--force-with-lease={ref}:{expected.get(ref) or ''}" for ref in refs
    )
    command.append("origin")
    command.extend(f"{commit}:{ref}" for ref in refs)
    run(command)


def remote_lease_core(
    github: GitHubReader, repo: str, commit_sha: str, held_ref: str
) -> dict[str, Any]:
    """Read and validate one canonical remote lease commit."""
    payload = github.get(repo, f"git/commits/{commit_sha}")
    if not isinstance(payload, dict) or payload.get("sha") != commit_sha:
        raise RuntimeError("Existing lease commit is unavailable")
    message = payload.get("message")
    if not isinstance(message, str) or "\n\n" not in message:
        raise RuntimeError("Existing lease commit is not canonical")
    _, encoded = message.split("\n\n", 1)
    try:
        core = json.loads(encoded)
    except json.JSONDecodeError as error:
        raise RuntimeError("Existing lease commit is not canonical") from error
    if (
        not isinstance(core, dict)
        or set(core) != set(LEASE_CORE_FIELDS)
        or core.get("schema_version") != LEASE_SCHEMA
        or str(core.get("repository", "")).casefold() != repo.casefold()
        or not isinstance(core.get("pull_request"), int)
        or int(core["pull_request"]) < 1
        or OWNER.fullmatch(str(core.get("owner", ""))) is None
        or ACTOR.fullmatch(str(core.get("actor", ""))) is None
        or not isinstance(core.get("refs"), list)
        or held_ref not in core["refs"]
        or not isinstance(core.get("reclaimed_commits"), list)
        or not all(
            isinstance(commit, str) and SHA.fullmatch(commit)
            for commit in core["reclaimed_commits"]
        )
        or SHA.fullmatch(str(core.get("head_sha", ""))) is None
        or SHA.fullmatch(str(core.get("head_tree", ""))) is None
        or SHA.fullmatch(str(core.get("base_sha", ""))) is None
        or SHA256.fullmatch(str(core.get("capability_digest", ""))) is None
        or payload.get("message") != lease_message(core)
    ):
        raise RuntimeError("Existing lease commit is not canonical")
    try:
        validate_refs(core)
        acquired_at = parse_time(core.get("acquired_at"), "Existing lease")
        expires_at = parse_time(core.get("expires_at"), "Existing lease")
    except (KeyError, RuntimeError) as error:
        raise RuntimeError("Existing lease commit is not canonical") from error
    ttl = (expires_at - acquired_at).total_seconds()
    if not 60 <= ttl <= MAX_TTL_SECONDS:
        raise RuntimeError("Existing lease commit is not canonical")
    parents = payload.get("parents")
    tree = payload.get("tree") or {}
    head = github.get(repo, f"git/commits/{core['head_sha']}")
    if (
        not isinstance(parents, list)
        or [item.get("sha") for item in parents if isinstance(item, dict)]
        != [core["head_sha"]]
        or tree.get("sha") != core["head_tree"]
        or not isinstance(head, dict)
        or (head.get("tree") or {}).get("sha") != core["head_tree"]
    ):
        raise RuntimeError("Existing lease commit parent or tree is invalid")
    return core


def expired_remote_lease(
    github: GitHubReader, repo: str, commit_sha: str, held_ref: str
) -> dict[str, Any]:
    """Validate one canonical expired lease before an atomic reclaim."""
    core = remote_lease_core(github, repo, commit_sha, held_ref)
    if parse_time(core["expires_at"], "Existing lease") > datetime.now(UTC):
        raise RuntimeError("Another owner already holds the PR lifecycle lease")
    return core


def lease_status_snapshot(
    github: GitHubReader, repo: str, pr_number: int, head_sha: str
) -> dict[str, object]:
    """Return read-only availability for one exact PR lifecycle lease."""
    result: dict[str, object] = {
        "schema_version": LEASE_STATUS_SCHEMA,
        "interface": LEASE_STATUS_INTERFACE,
        "repository": repo,
        "pull_request": pr_number,
        "head_sha": head_sha,
        "base_ref": None,
        "base_sha": None,
        "lease_refs": [],
        "state": "unknown",
        "reason": "live lease state has not been inspected",
    }
    try:
        if REPOSITORY.fullmatch(repo) is None or pr_number < 1:
            raise RuntimeError("Pull request identity is invalid")
        if SHA.fullmatch(head_sha) is None:
            raise RuntimeError("Head SHA is invalid")
        require_origin(repo)
        pull = live_pull(github, repo, pr_number, head_sha)
        repository = github.get(repo, "")
        base = pull.get("base") or {}
        base_ref = base.get("ref")
        base_sha = base.get("sha")
        if (
            not isinstance(repository, dict)
            or not isinstance(repository.get("default_branch"), str)
            or not isinstance(base_ref, str)
            or SHA.fullmatch(str(base_sha or "")) is None
        ):
            raise RuntimeError("Pull request base identity is unavailable")
        if branch_sha(github, repo, base_ref) != base_sha:
            raise RuntimeError("Pull request destination branch advanced")
        refs = lease_refs(pull, repository["default_branch"])
        result.update(
            {
                "base_ref": base_ref,
                "base_sha": base_sha,
                "lease_refs": refs,
            }
        )
        observed = {ref: remote_ref(ref) for ref in refs}
        commits = {commit for commit in observed.values() if commit is not None}
        if not commits:
            result.update(
                {
                    "state": "available",
                    "reason": (
                        "both lease refs are absent; atomic acquire may be "
                        "attempted"
                    ),
                }
            )
            return result
        if len(commits) != 1 or (observed[refs[0]] and not observed[refs[1]]):
            raise RuntimeError("Remote lease refs are inconsistent")
        commit = commits.pop()
        cores = [
            remote_lease_core(github, repo, commit, ref)
            for ref, value in observed.items()
            if value is not None
        ]
        if any(core != cores[0] for core in cores[1:]):
            raise RuntimeError("Remote lease refs do not share one lease")
        core = cores[0]
        expires_at = parse_time(core["expires_at"], "Existing lease")
        if expires_at <= datetime.now(UTC):
            result.update(
                {
                    "state": "available",
                    "reason": (
                        "canonical lease is expired; atomic reclaim may be "
                        "attempted"
                    ),
                }
            )
            return result
        result.update(
            {
                "state": "held",
                "reason": "a canonical unexpired lease holds a required ref",
                "holder": {
                    "pull_request": core["pull_request"],
                    "head_sha": core["head_sha"],
                    "base_ref": core["base_ref"],
                    "base_sha": core["base_sha"],
                    "owner": core["owner"],
                    "actor": core["actor"],
                    "expires_at": core["expires_at"],
                    "lease_commit": commit,
                },
            }
        )
    except (KeyError, RuntimeError) as error:
        result["reason"] = str(error)
    return result


def acquire(args: argparse.Namespace, github: GitHub) -> None:  # noqa: C901
    """Atomically acquire the PR and destination-lane refs."""
    if SHA.fullmatch(args.head_sha) is None:
        raise RuntimeError(
            "Head SHA must be 40 lowercase hexadecimal characters"
        )
    if OWNER.fullmatch(args.owner) is None:
        raise RuntimeError("Owner must be a stable task or human identifier")
    if not 60 <= args.ttl_seconds <= MAX_TTL_SECONDS:
        raise RuntimeError(
            f"Lease TTL must be between 60 and {MAX_TTL_SECONDS} seconds"
        )
    require_origin(args.repo)
    pull = live_pull(github, args.repo, args.pr_number, args.head_sha)
    repository = github.get(args.repo, "")
    if not isinstance(repository, dict) or not isinstance(
        repository.get("default_branch"), str
    ):
        raise RuntimeError("Repository default branch is unavailable")
    refs = lease_refs(pull, repository["default_branch"])
    base = pull.get("base") or {}
    if (
        not isinstance(base.get("ref"), str)
        or SHA.fullmatch(str(base.get("sha", ""))) is None
    ):
        raise RuntimeError("Pull request base identity is unavailable")
    if branch_sha(github, args.repo, base["ref"]) != base["sha"]:
        raise RuntimeError(
            "Pull request base does not match its destination ref"
        )
    observed = {ref: remote_ref(ref) for ref in refs}
    for ref, existing in observed.items():
        if existing is not None:
            expired_remote_lease(github, args.repo, existing, ref)
    acquired = datetime.now(UTC)
    tree = run(["git", "rev-parse", f"{args.head_sha}^{{tree}}"])
    capability = secrets.token_hex(32)
    core: dict[str, object] = {
        "schema_version": LEASE_SCHEMA,
        "repository": args.repo,
        "pull_request": args.pr_number,
        "head_sha": args.head_sha,
        "head_tree": tree,
        "base_ref": base["ref"],
        "base_sha": base["sha"],
        "default_branch": repository["default_branch"],
        "owner": args.owner,
        "actor": github.viewer(getattr(args, "actor", "")),
        "capability_digest": hashlib.sha256(capability.encode()).hexdigest(),
        "acquired_at": acquired.isoformat().replace("+00:00", "Z"),
        "expires_at": (acquired + timedelta(seconds=args.ttl_seconds))
        .isoformat()
        .replace("+00:00", "Z"),
        "refs": refs,
        "reclaimed_commits": sorted(
            {commit for commit in observed.values() if commit is not None}
        ),
    }
    commit_env = os.environ.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "CSARC PR lifecycle lease",
            "GIT_AUTHOR_EMAIL": "pr-lifecycle@invalid.example",
            "GIT_COMMITTER_NAME": "CSARC PR lifecycle lease",
            "GIT_COMMITTER_EMAIL": "pr-lifecycle@invalid.example",
        }
    )
    commit = run(
        ["git", "commit-tree", tree, "-p", args.head_sha],
        input_text=f"{lease_message(core)}\n",
        env=commit_env,
    )
    if SHA.fullmatch(commit) is None:
        raise RuntimeError("Git did not create a valid lease commit")
    create_refs(commit, refs, observed)
    evidence = {**core, "capability": capability, "lease_commit": commit}
    try:
        comment = github.comment(
            args.repo,
            args.pr_number,
            audit_message(evidence),
        )
        audit_url = comment.get("html_url")
        audit_user = comment.get("user") or {}
        if (
            not isinstance(audit_url, str)
            or not isinstance(audit_user, dict)
            or str(audit_user.get("login", "")).casefold()
            != str(evidence["actor"]).casefold()
        ):
            raise RuntimeError("Lease audit comment has invalid actor or URL")
        evidence["audit_url"] = audit_url
        validate_audit_url(evidence)
        validate_audit_comment(evidence, comment)
        write_json(args.output, evidence)
    except Exception:
        release_refs(evidence)
        raise


def authorization(
    github: GitHub, repo: str, pr_number: int, head_sha: str, url: str
) -> dict[str, Any]:
    """Require a maintainer authorization bound to the exact PR head."""
    parsed = urllib.parse.urlparse(url)
    expected_path = f"/{repo}/pull/{pr_number}"
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() != "github.com"
        or parsed.path.casefold() != expected_path.casefold()
        or re.fullmatch(r"issuecomment-(\d+)", parsed.fragment) is None
    ):
        raise RuntimeError(
            "Authorization URL must be a comment on this pull request"
        )
    comment_id = parsed.fragment.removeprefix("issuecomment-")
    payload = github.get(repo, f"issues/comments/{comment_id}")
    if not isinstance(payload, dict):
        raise RuntimeError("Authorization comment response is invalid")
    body = payload.get("body")
    user = payload.get("user") or {}
    expected_body = authorization_statement(repo, pr_number, head_sha)
    if (
        payload.get("html_url") != url
        or not str(payload.get("issue_url", "")).endswith(
            f"/issues/{pr_number}"
        )
        or payload.get("author_association") not in MAINTAINER_ASSOCIATIONS
        or not isinstance(user.get("login"), str)
        or user.get("type") != "User"
        or body != expected_body
    ):
        raise RuntimeError("Authorization is not an exact maintainer statement")
    permission = github.get(
        repo,
        "collaborators/"
        f"{urllib.parse.quote(user['login'], safe='')}/permission",
    )
    if (
        not isinstance(permission, dict)
        or permission.get("permission") not in MAINTAINER_PERMISSIONS
        or (permission.get("user") or {}).get("login") != user["login"]
    ):
        raise RuntimeError("Authorization actor lacks maintainer permission")
    parse_time(payload.get("created_at"), "Authorization")
    return payload


def authorization_statement(repo: str, pr_number: int, head_sha: str) -> str:
    """Return the exact affirmative authorization accepted by the tool."""
    binding = {
        "repository": repo,
        "pull_request": pr_number,
        "head_sha": head_sha,
    }
    return (
        "PR lifecycle merge authorization\n\n"
        f"`{canonical_json(binding)}`\n\n"
        "I authorize this exact pull request head for one merge attempt."
    )


def blocker_state(
    comments: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, datetime | None]:
    """Return the unresolved blocker and latest trusted blocker boundary."""
    latest_blocker: tuple[datetime, dict[str, Any]] | None = None
    latest_resolution: datetime | None = None
    for comment in comments:
        created = parse_time(comment.get("created_at"), "Comment")
        body = str(comment.get("body") or "").lstrip()
        if comment.get("author_association") not in MAINTAINER_ASSOCIATIONS:
            continue
        if BLOCKER_RESOLVED.search(body) and (
            latest_resolution is None or created > latest_resolution
        ):
            latest_resolution = created
        elif BLOCKER.search(body) and (
            latest_blocker is None or created >= latest_blocker[0]
        ):
            latest_blocker = (created, comment)
    boundary = max(
        (
            value
            for value in (
                latest_blocker[0] if latest_blocker else None,
                latest_resolution,
            )
            if value is not None
        ),
        default=None,
    )
    if latest_blocker is None or (
        latest_resolution is not None and latest_resolution > latest_blocker[0]
    ):
        return None, boundary
    return latest_blocker[1], boundary


def unresolved_blocker(comments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the latest unresolved merge-blocker marker."""
    return blocker_state(comments)[0]


def current_reviews(reviews: list[dict[str, Any]]) -> dict[str, str]:
    """Return each reviewer's current decisive state."""
    current: dict[str, str] = {}
    ordered = sorted(
        reviews,
        key=lambda item: (
            parse_time(item.get("submitted_at"), "Review")
            if item.get("submitted_at")
            else datetime.min.replace(tzinfo=UTC)
        ),
    )
    for review in ordered:
        user = review.get("user") or {}
        login = user.get("login")
        if not isinstance(login, str) or not review.get("submitted_at"):
            continue
        reviewer = login.casefold()
        state = str(review.get("state") or "")
        if state in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            current[reviewer] = state
    return current


def effective_protection(
    github: GitHubReader, repo: str, branch: str
) -> tuple[str, str, set[tuple[str, int | None]]]:
    """Prove review, last-push, thread, checks, and no-bypass enforcement."""
    try:
        rules = github.get(
            repo, f"rules/branches/{urllib.parse.quote(branch, safe='')}"
        )
    except RuntimeError as error:
        return "unknown", str(error), set()
    if not isinstance(rules, list):
        return "unknown", "effective branch rules are unavailable", set()
    pull_rules = [item for item in rules if item.get("type") == "pull_request"]
    check_rules = [
        item for item in rules if item.get("type") == "required_status_checks"
    ]
    pull = [item.get("parameters") or {} for item in pull_rules]
    checks = [item.get("parameters") or {} for item in check_rules]
    required_items = [
        item
        for parameters in checks
        for item in parameters.get("required_status_checks", [])
    ]
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("context"), str)
        or not item["context"]
        or (
            item.get("integration_id") is not None
            and not isinstance(item.get("integration_id"), int)
        )
        for item in required_items
    ):
        return "unknown", "required check rules are malformed", set()
    required_contexts = {
        (str(item["context"]), item.get("integration_id"))
        for item in required_items
        if isinstance(item, dict)
    }
    protected = (
        any(
            item.get("required_approving_review_count", 0) >= 1 for item in pull
        )
        and any(
            item.get("dismiss_stale_reviews_on_push") is True for item in pull
        )
        and any(item.get("require_code_owner_review") is True for item in pull)
        and any(item.get("require_last_push_approval") is True for item in pull)
        and any(
            item.get("required_review_thread_resolution") is True
            for item in pull
        )
        and bool(required_contexts)
    )
    if not protected:
        return (
            "blocked",
            "required approval, stale-review dismissal, CODEOWNER, last-push, "
            "thread, or check rules are missing",
            set(),
        )
    ruleset_ids = {
        item.get("ruleset_id")
        for item in pull_rules + check_rules
        if item.get("ruleset_id")
    }
    if not ruleset_ids:
        return (
            "unknown",
            "effective rules do not expose their Ruleset identity",
            set(),
        )
    for ruleset_id in ruleset_ids:
        try:
            ruleset = github.get(repo, f"rulesets/{ruleset_id}")
        except RuntimeError as error:
            return "unknown", str(error), set()
        if (
            not isinstance(ruleset, dict)
            or ruleset.get("enforcement") != "active"
            or ruleset.get("bypass_actors") != []
        ):
            return (
                "blocked",
                "an effective Ruleset is inactive or permits bypass",
                set(),
            )
    return (
        "enforced",
        "server-side merge controls are active without bypass",
        required_contexts,
    )


def require_successful_checks(
    github: GitHub,
    repo: str,
    head_sha: str,
    contexts: set[tuple[str, int | None]],
) -> None:
    """Require every protected context to succeed on the exact PR head."""
    check_runs = github.collection(
        repo,
        f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
        "check_runs",
    )
    statuses = github.collection(
        repo,
        f"commits/{head_sha}/status?per_page=100",
        "statuses",
        head_sha,
    )
    passing_runs = [
        item
        for item in check_runs
        if item.get("head_sha") == head_sha
        and item.get("status") == "completed"
        and item.get("conclusion") in SUCCESSFUL_CHECK_CONCLUSIONS
    ]
    passing_statuses = {
        item.get("context")
        for item in statuses
        if item.get("state") == "success"
    }
    missing = sorted(
        context
        for context, integration_id in contexts
        if not any(
            item.get("name") == context
            and (
                integration_id is None
                or (item.get("app") or {}).get("id") == integration_id
            )
            for item in passing_runs
        )
        and not (integration_id is None and context in passing_statuses)
    )
    if missing:
        raise RuntimeError(
            "Required checks have not succeeded on the exact head: "
            + ", ".join(missing)
        )


def merge_discussion_snapshot(
    github: GitHub, repo: str, pr_number: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], datetime | None]:
    """Read comments and reviews, rejecting every current merge blocker."""
    issue_comments = github.pages(
        repo, f"issues/{pr_number}/comments?per_page=100"
    )
    comments = [
        *issue_comments,
        *github.pages(repo, f"pulls/{pr_number}/comments?per_page=100"),
    ]
    reviews = github.pages(repo, f"pulls/{pr_number}/reviews?per_page=100")
    comments.extend(
        {**review, "created_at": review.get("submitted_at")}
        for review in reviews
        if review.get("state") == "COMMENTED"
        and review.get("submitted_at")
        and review.get("body")
    )
    blocker, boundary = blocker_state(comments)
    if blocker is not None:
        raise RuntimeError(
            "An unresolved blocking comment prevents merge: "
            + str(blocker.get("html_url") or "unknown URL")
        )
    requested = sorted(
        login
        for login, state in current_reviews(reviews).items()
        if state == "CHANGES_REQUESTED"
    )
    if requested:
        raise RuntimeError(
            "Changes are still requested by: " + ", ".join(requested)
        )
    return issue_comments, reviews, boundary


def require_complete_issue(
    github: GitHub,
    repo: str,
    issue_number: int,
    *,
    require_open: bool,
) -> dict[str, Any]:
    """Require one real Issue with complete acceptance."""
    issue = github.get(repo, f"issues/{issue_number}")
    if not isinstance(issue, dict) or issue.get("pull_request") is not None:
        raise RuntimeError(f"Closing reference #{issue_number} is not an Issue")
    if require_open and issue.get("state") != "open":
        raise RuntimeError(f"Closing Issue #{issue_number} is not open")
    if UNCHECKED.search(str(issue.get("body") or "")):
        raise RuntimeError(
            f"Issue #{issue_number} has an unchecked checklist item"
        )
    return issue


def require_single_closing_issue(
    github: GitHub,
    repo: str,
    pull: dict[str, Any],
    *,
    require_open: bool = True,
) -> int:
    """Require exactly one complete Issue closer in this repository."""
    closing = closing_issue_references(str(pull.get("body") or ""), repo)
    if len(closing) != 1 or closing[0][0].casefold() != repo.casefold():
        raise RuntimeError(
            "Pull request must have exactly one closing reference in this "
            "repository"
    )
    issue_number = closing[0][1]
    require_complete_issue(
        github, repo, issue_number, require_open=require_open
    )
    return issue_number


def validate_merge_issue_links(
    github: GitHub, repo: str, pull: dict[str, Any]
) -> list[int]:
    """Validate Issue closers while permitting an unlinked sync PR."""
    closing = closing_issue_references(str(pull.get("body") or ""), repo)
    if any(name.casefold() != repo.casefold() for name, _ in closing):
        raise RuntimeError(
            "Pull request must have closing references only in this repository"
        )
    head_ref = str((pull.get("head") or {}).get("ref") or "")
    issue_branch = re.fullmatch(
        r"[a-z][a-z0-9-]*/([1-9][0-9]*)-[a-z0-9][a-z0-9-]*",
        head_ref,
    )
    if issue_branch is not None:
        expected = int(issue_branch.group(1))
        if len(closing) != 1 or (
            closing[0][0].casefold(), closing[0][1]
        ) != (repo.casefold(), expected):
            raise RuntimeError(
                "Issue pull request must have exactly one closing reference "
                "to its matching local Issue"
            )
    for issue_number in sorted({number for _, number in closing}):
        require_complete_issue(
            github, repo, issue_number, require_open=True
        )
    return [number for _, number in closing]


def merge_snapshot(  # noqa: C901
    github: GitHub,
    lease: dict[str, Any],
    authorization_url: str,
    explicit_actor: str = "",
) -> dict[str, object]:
    """Re-read every mutable merge input while the lease is held."""
    repo = lease["repository"]
    pr_number = lease["pull_request"]
    head_sha = lease["head_sha"]
    require_lease(github, lease, repo, pr_number, head_sha)
    pull = live_pull(github, repo, pr_number, head_sha)
    if pull.get("draft") is not False:
        raise RuntimeError("Pull request is Draft at merge time")
    if UNCHECKED.search(str(pull.get("body") or "")):
        raise RuntimeError("Pull request has an unchecked checklist item")
    auth = authorization(github, repo, pr_number, head_sha, authorization_url)
    acquired_at = parse_time(lease["acquired_at"], "Lease")
    authorized_at = parse_time(auth.get("created_at"), "Authorization")
    if authorized_at < acquired_at:
        raise RuntimeError("Authorization predates the active lifecycle lease")

    timeline = github.pages(repo, f"issues/{pr_number}/timeline?per_page=100")
    if any(
        item.get("event") in DRAFT_EVENTS
        and parse_time(item.get("created_at"), "Draft event") >= authorized_at
        for item in timeline
    ):
        raise RuntimeError(
            "A newer Draft event invalidated merge authorization"
        )
    _, reviews, blocker_boundary = merge_discussion_snapshot(
        github, repo, pr_number
    )
    if blocker_boundary is not None and authorized_at <= blocker_boundary:
        raise RuntimeError(
            "Authorization does not postdate the latest blocker resolution"
        )
    review_states = current_reviews(reviews)
    actor = github.viewer(explicit_actor).casefold()
    if actor != str(lease["actor"]).casefold():
        raise RuntimeError(
            "Authenticated GitHub actor changed after lease acquisition"
        )
    approvers = sorted(
        login
        for login, state in review_states.items()
        if state == "APPROVED" and login != actor
    )
    if not approvers:
        raise RuntimeError("An independent approving review is required")
    issue_numbers = validate_merge_issue_links(github, repo, pull)

    base = pull.get("base") or {}
    base_ref = base.get("ref")
    if not isinstance(base_ref, str):
        raise RuntimeError("Pull request base branch is unavailable")
    head_ref = str((pull.get("head") or {}).get("ref") or "")
    issue_branch = re.fullmatch(
        r"[a-z][a-z0-9-]*/([1-9][0-9]*)-[a-z0-9][a-z0-9-]*",
        head_ref,
    )
    if issue_branch is not None:
        issue = github.get(repo, f"issues/{issue_numbers[0]}")
        if not isinstance(issue, dict):
            raise RuntimeError("Closing Issue identity is unavailable")
        route = open_issue_route_snapshot(
            github,
            repo,
            issue,
            pull,
            local_branch_strategy(),
            routine_only=False,
        )
        if base_ref != route.get("base"):
            raise RuntimeError(
                "Issue pull request must target its canonical integration "
                "branch before merge"
            )
    elif issue_numbers and base_ref != lease["default_branch"]:
        raise RuntimeError(
            "A non-default automation pull request cannot close Issues"
        )
    title = pull.get("title")
    if not isinstance(title, str) or not title.strip():
        raise RuntimeError("Pull request title is unavailable")
    protection, reason, required_contexts = effective_protection(
        github, repo, base_ref
    )
    authorization_actor = str((auth.get("user") or {}).get("login", ""))
    independently_authorized = authorization_actor.casefold() != actor
    if protection == "enforced" and not independently_authorized:
        protection = "blocked"
        reason = "merge authorization uses the executing GitHub actor"
    if protection == "enforced":
        require_successful_checks(github, repo, head_sha, required_contexts)
    require_lease(github, lease, repo, pr_number, head_sha)
    return {
        "repository": repo,
        "pull_request": pr_number,
        "head_sha": head_sha,
        "base_ref": lease["base_ref"],
        "base_sha": lease["base_sha"],
        "title": title,
        "authorization_url": authorization_url,
        "authorization_created_at": auth["created_at"],
        "authorization_actor": authorization_actor,
        "protection": protection,
        "merge_mode": "agent" if protection == "enforced" else "human-only",
        "protection_reason": reason,
        "close_issue": bool(
            issue_numbers and base_ref != lease["default_branch"]
        ),
    }


def local_branch_strategy() -> str:
    """Read the checked-in branch strategy used by this repository."""
    root = Path(__file__).resolve().parents[1]
    profile = root / ".csarc/profile.json"
    if not profile.exists():
        if (root / "copier.yml").is_file():
            return "delivery"
        raise RuntimeError("Repository profile is missing")
    payload = json.loads(profile.read_text(encoding="utf-8"))
    strategy = (
        payload.get("branch_strategy") if isinstance(payload, dict) else None
    )
    if strategy not in {"delivery", "dev", "main"}:
        raise RuntimeError("Repository branch strategy is missing or invalid")
    return str(strategy)


def open_issue_route_snapshot(
    github: GitHub,
    repo: str,
    issue: dict[str, Any],
    pull: dict[str, Any],
    strategy: str,
    *,
    routine_only: bool,
) -> dict[str, object]:
    """Require one live Issue PR chain to reach its canonical route."""
    from issue_path_status import _open_base_chain, route_for

    branches = {
        str(item["name"]): str((item.get("commit") or {})["sha"])
        for item in github.pages(repo, "branches?per_page=100")
        if isinstance(item.get("name"), str)
        and isinstance((item.get("commit") or {}).get("sha"), str)
    }
    route = route_for(issue, branches, strategy)
    elevated_routes = {
        "hotfix",
        "milestone-promotion",
        "isolated-promotion",
        "standalone-batch-promotion",
        "dev-promotion",
    }
    if not route.get("valid") or (
        routine_only and route.get("kind") in elevated_routes
    ):
        raise RuntimeError("Routine quota merge has no valid Issue route")
    pulls = github.pages(repo, "pulls?state=all&per_page=100")
    valid, members, _, reason = _open_base_chain(
        pull, pulls, str(route["base"]), repo
    )
    if not valid:
        raise RuntimeError(reason)
    for member in members:
        base = member.get("base") or {}
        head = member.get("head") or {}
        base_ref = str(base.get("ref") or "")
        head_ref = str(head.get("ref") or "")
        base_sha = str(base.get("sha") or "")
        head_sha = str(head.get("sha") or "")
        if (
            branches.get(base_ref) != base_sha
            or branches.get(head_ref) != head_sha
        ):
            raise RuntimeError("Routine quota PR chain drifted from live refs")
        comparison = github.get(repo, f"compare/{base_sha}...{head_sha}")
        if not isinstance(comparison, dict) or comparison.get("status") not in {
            "ahead",
            "identical",
        }:
            raise RuntimeError(
                "Routine quota PR chain does not contain its live base"
            )
    return route


def routine_quota_snapshot(  # noqa: C901
    github: GitHub,
    lease: dict[str, Any],
    explicit_actor: str = "",
) -> dict[str, object]:
    """Revalidate a routine zero-step exception without human authorization."""
    repo = str(lease["repository"])
    pr_number = int(lease["pull_request"])
    head_sha = str(lease["head_sha"])
    require_lease(github, lease, repo, pr_number, head_sha)
    pull = live_pull(github, repo, pr_number, head_sha)
    base = pull.get("base") or {}
    head = pull.get("head") or {}
    body = str(pull.get("body") or "")
    if (
        pull.get("draft") is not False
        or UNCHECKED.search(body)
        or base.get("ref") != lease["base_ref"]
        or base.get("sha") != lease["base_sha"]
        or (head.get("repo") or {}).get("full_name") != repo
    ):
        raise RuntimeError("Routine quota pull request identity is not final")
    if "Alpha 自行合併 / self-merged" not in body:
        raise RuntimeError(
            "Routine quota merge lacks the Alpha self-merge note"
        )
    labels = {
        str(item["name"])
        for item in pull.get("labels", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    strategy = local_branch_strategy()
    route = promotion_route_for(
        str(base.get("ref") or ""),
        str(head.get("ref") or ""),
        labels,
        strategy,
    )
    files = [
        str(item["filename"])
        for item in github.pages(repo, f"pulls/{pr_number}/files?per_page=100")
        if isinstance(item.get("filename"), str)
    ]
    plan = classify_ci(
        "pull_request",
        str(base.get("ref") or ""),
        str(head.get("ref") or ""),
        labels,
        files,
    )
    elevated = {"workflow", "governance", "dependency", "template", "unknown"}
    if (
        route.kind != "not-applicable"
        or bool(labels & {"promotion", "hotfix"})
        or not files
        or plan.tier == "full"
        or bool(set(plan.scopes) & elevated)
    ):
        raise RuntimeError(
            "Routine quota merge rejects promotion, hotfix, elevated, or "
            "unknown work"
        )
    issue_comments, _, blocker_boundary = merge_discussion_snapshot(
        github, repo, pr_number
    )
    issue_number = require_single_closing_issue(github, repo, pull)
    issue = github.get(repo, f"issues/{issue_number}")
    if not isinstance(issue, dict):
        raise RuntimeError("Closing Issue identity is unavailable")
    issue_route = open_issue_route_snapshot(
        github, repo, issue, pull, strategy, routine_only=True
    )
    if (pull.get("base") or {}).get("ref") != issue_route.get("base"):
        raise RuntimeError(
            "Routine quota merge must target the canonical integration branch"
        )
    if re.fullmatch(
        rf"[a-z][a-z0-9-]*/{issue_number}-[a-z0-9][a-z0-9-]*",
        str(head.get("ref") or ""),
    ) is None:
        raise RuntimeError(
            "Routine quota merge head does not match its closing Issue"
        )
    actor = github.viewer(explicit_actor).casefold()
    if actor != str(lease["actor"]).casefold():
        raise RuntimeError(
            "Authenticated GitHub actor changed after lease acquisition"
        )
    token = os.environ.get("GH_TOKEN", "")
    run_urls = failed_pull_request_run_urls(repo, head_sha, token)
    for url in run_urls:
        require_zero_step_run(
            url,
            repo,
            pr_number,
            str(head.get("ref") or ""),
            head_sha,
            token,
        )
    if not has_exact_quota_note(
        issue_comments,
        repo,
        pr_number,
        head_sha,
        run_urls,
        str(lease["actor"]),
        blocker_boundary,
    ):
        raise RuntimeError(
            "Exactly one canonical routine quota note must match every live "
            "failed run"
        )
    title = pull.get("title")
    if not isinstance(title, str) or not title.strip():
        raise RuntimeError("Pull request title is unavailable")
    require_lease(github, lease, repo, pr_number, head_sha)
    return {
        "repository": repo,
        "pull_request": pr_number,
        "head_sha": head_sha,
        "base_ref": lease["base_ref"],
        "base_sha": lease["base_sha"],
        "title": title,
        "risk": "routine",
        "blocked_run_urls": run_urls,
        "merge_mode": "routine-quota",
    }


def merged_issue_snapshot(  # noqa: C901
    github: GitHub,
    lease: dict[str, Any],
    explicit_actor: str = "",
) -> dict[str, object]:
    """Prove a merged PR reached its non-default integration route."""
    repo = str(lease["repository"])
    pr_number = int(lease["pull_request"])
    require_origin(repo)
    validate_refs(lease)
    if parse_time(lease["expires_at"], "Lease") <= datetime.now(
        UTC
    ) + timedelta(seconds=MIN_OPERATION_SECONDS):
        raise RuntimeError("Lease expired before the Issue close mutation")
    require_committed_lease(github, lease)
    if github.viewer(explicit_actor).casefold() != str(
        lease["actor"]
    ).casefold():
        raise RuntimeError(
            "Authenticated GitHub actor changed after lease acquisition"
        )
    repository = github.get(repo, "")
    pull = github.get(repo, f"pulls/{pr_number}")
    if not isinstance(repository, dict) or not isinstance(pull, dict):
        raise RuntimeError("Merged pull request identity is unavailable")
    base = pull.get("base") or {}
    head = pull.get("head") or {}
    merge_sha = pull.get("merge_commit_sha")
    if (
        pull.get("merged") is not True
        or pull.get("merged_at") is None
        or head.get("sha") != lease["head_sha"]
        or (head.get("repo") or {}).get("full_name") != repo
        or base.get("ref") != lease["base_ref"]
        or repository.get("default_branch") != lease["default_branch"]
        or SHA.fullmatch(str(merge_sha or "")) is None
    ):
        raise RuntimeError("Merged pull request does not match the lease")
    merge_commit = github.get(repo, f"git/commits/{merge_sha}")
    parents = (
        merge_commit.get("parents")
        if isinstance(merge_commit, dict)
        else None
    )
    if (
        not isinstance(parents, list)
        or [item.get("sha") for item in parents if isinstance(item, dict)]
        != [lease["base_sha"]]
    ):
        raise RuntimeError("Merged commit does not preserve the leased base")
    if UNCHECKED.search(str(pull.get("body") or "")):
        raise RuntimeError("Pull request has an unchecked checklist item")
    merge_discussion_snapshot(github, repo, pr_number)
    issue_number = require_single_closing_issue(
        github, repo, pull, require_open=False
    )
    if re.fullmatch(
        rf"[a-z][a-z0-9-]*/{issue_number}-[a-z0-9][a-z0-9-]*",
        str(head.get("ref") or ""),
    ) is None:
        raise RuntimeError("Merged pull request head does not match its Issue")
    issue = github.get(repo, f"issues/{issue_number}")
    if not isinstance(issue, dict):
        raise RuntimeError("Closing Issue identity is unavailable")

    branches = {
        str(item["name"]): str((item.get("commit") or {})["sha"])
        for item in github.pages(repo, "branches?per_page=100")
        if isinstance(item.get("name"), str)
        and isinstance((item.get("commit") or {}).get("sha"), str)
    }
    from issue_path_status import merged_base_chain, route_for

    route = route_for(issue, branches, local_branch_strategy())
    expected_base = route.get("base")
    if (
        not route.get("valid")
        or not isinstance(expected_base, str)
        or expected_base == lease["default_branch"]
    ):
        raise RuntimeError(
            "Issue close correction is limited to a valid non-default route"
        )
    pulls = github.pages(repo, "pulls?state=all&per_page=100")
    valid, chain, reason, terminal, containment = merged_base_chain(
        pull, pulls, expected_base, repo
    )
    if not valid:
        raise RuntimeError(reason)
    terminal_merge = terminal.get("merge_commit_sha")
    if SHA.fullmatch(str(terminal_merge or "")) is None:
        raise RuntimeError("Terminal merged PR has no immutable commit")
    proofs = [*containment, (str(terminal_merge), branches[expected_base])]
    for ancestor, descendant in proofs:
        comparison = github.get(repo, f"compare/{ancestor}...{descendant}")
        if not isinstance(comparison, dict) or comparison.get("status") not in {
            "ahead",
            "identical",
        }:
            raise RuntimeError(
                f"Merged commit {ancestor} is not contained in {descendant}"
            )
    return {
        "repository": repo,
        "pull_request": pr_number,
        "issue_number": issue_number,
        "issue_state": issue.get("state"),
        "head_sha": lease["head_sha"],
        "merge_sha": merge_sha,
        "route": route,
        "base_chain": chain,
    }


def mutate_state(args: argparse.Namespace, github: GitHub) -> None:
    """Change Draft state only while the exact lease remains live."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, getattr(args, "actor", ""), github)
    require_lease(github, lease, args.repo, args.pr_number, args.head_sha)
    pull = live_pull(github, args.repo, args.pr_number, args.head_sha)
    current = bool(pull.get("draft"))
    desired = args.state == "draft"
    if current == desired:
        raise RuntimeError(f"Pull request is already {args.state}")
    command = ["gh", "pr", "ready", str(args.pr_number), "--repo", args.repo]
    if desired:
        command.append("--undo")
    run(command)
    require_lease(github, lease, args.repo, args.pr_number, args.head_sha)
    updated = live_pull(github, args.repo, args.pr_number, args.head_sha)
    if bool(updated.get("draft")) != desired:
        raise RuntimeError(
            "Pull request Draft state did not change as requested"
        )


def read_body_file(body_file: Path | None) -> str | None:
    """Read an optional UTF-8 pull-request body."""
    if body_file is None:
        return None
    try:
        return body_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise RuntimeError(
            "Pull request body file is not valid UTF-8"
        ) from error


def edit_metadata(args: argparse.Namespace, github: GitHub) -> None:
    """Edit the body, labels, or milestone while the lease remains live."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, getattr(args, "actor", ""), github)
    require_lease(github, lease, args.repo, args.pr_number, args.head_sha)
    pull = live_pull(github, args.repo, args.pr_number, args.head_sha)
    labels = {
        item.get("name")
        for item in pull.get("labels", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    body_file = getattr(args, "body_file", None)
    requested_body = read_body_file(body_file)
    if not any(
        (
            body_file is not None,
            args.add_label,
            args.remove_label,
            args.milestone is not None,
            args.remove_milestone,
        )
    ):
        raise RuntimeError(
            "At least one body, label, or milestone edit is required"
        )
    if any(
        "\n" in label or not label
        for label in args.add_label + args.remove_label
    ):
        raise RuntimeError("Label names must be non-empty single-line values")
    expected_labels = (labels | set(args.add_label)) - set(args.remove_label)
    command = ["gh", "pr", "edit", str(args.pr_number), "--repo", args.repo]
    if requested_body is not None:
        command.extend(("--body-file", "-"))
    for label in args.add_label:
        command.extend(("--add-label", label))
    for label in args.remove_label:
        command.extend(("--remove-label", label))
    if args.milestone is not None:
        command.extend(("--milestone", args.milestone))
    elif args.remove_milestone:
        command.append("--remove-milestone")
    run(command, input_text=requested_body)
    require_lease(github, lease, args.repo, args.pr_number, args.head_sha)
    updated = live_pull(github, args.repo, args.pr_number, args.head_sha)
    updated_labels = {
        item.get("name")
        for item in updated.get("labels", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    milestone = updated.get("milestone") or {}
    milestone_matches = (
        args.milestone is None or milestone.get("title") == args.milestone
    ) and (not args.remove_milestone or updated.get("milestone") is None)
    body_matches = requested_body is None or (
        str(updated.get("body") or "").replace("\r\n", "\n").rstrip("\n")
        == requested_body.replace("\r\n", "\n").rstrip("\n")
    )
    if (
        updated_labels != expected_labels
        or not milestone_matches
        or not body_matches
    ):
        raise RuntimeError("Pull request metadata did not change as requested")


def check(args: argparse.Namespace, github: GitHub) -> None:
    """Print the live merge snapshot without mutating GitHub."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, getattr(args, "actor", ""), github)
    snapshot = merge_snapshot(
        github, lease, args.authorization_url, getattr(args, "actor", "")
    )
    sys.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")


def merge_exact(
    args: argparse.Namespace,
    github: GitHub,
    lease: dict[str, Any],
    title: str,
    *,
    close_issue: bool = False,
) -> None:
    """Perform and verify one synchronous SHA-bound squash merge."""
    if (
        str(lease["repository"]).casefold() != args.repo.casefold()
        or lease["pull_request"] != args.pr_number
        or lease["head_sha"] != args.head_sha
    ):
        raise RuntimeError("Lease does not match the requested pull request")
    confirm_refs(lease)
    if branch_sha(github, args.repo, lease["base_ref"]) != lease["base_sha"]:
        raise RuntimeError(
            "Pull request destination branch advanced before merge"
        )
    result = github.merge(args.repo, args.pr_number, args.head_sha, title)
    merge_sha = result.get("sha")
    if result.get("merged") is not True or not isinstance(merge_sha, str):
        raise RuntimeError(
            "GitHub did not synchronously merge the pull request"
        )
    merged = github.get(args.repo, f"pulls/{args.pr_number}")
    merge_commit = github.get(args.repo, f"git/commits/{merge_sha}")
    parents = (
        merge_commit.get("parents") if isinstance(merge_commit, dict) else None
    )
    if (
        not isinstance(merged, dict)
        or merged.get("merged") is not True
        or (merged.get("head") or {}).get("sha") != args.head_sha
        or merged.get("merge_commit_sha") != merge_sha
        or branch_sha(github, args.repo, lease["base_ref"]) != merge_sha
        or not isinstance(parents, list)
        or [item.get("sha") for item in parents if isinstance(item, dict)]
        != [lease["base_sha"]]
    ):
        raise RuntimeError(
            "Merged pull request state does not match the response"
        )
    if close_issue:
        close_merged_issue_under_lease(
            github, lease, getattr(args, "actor", "")
        )
    release_refs(lease)


def merge(args: argparse.Namespace, github: GitHub) -> None:
    """Merge only when both the lease and server-side controls are enforced."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, getattr(args, "actor", ""), github)
    snapshot = merge_snapshot(
        github, lease, args.authorization_url, getattr(args, "actor", "")
    )
    if snapshot["merge_mode"] != "agent":
        raise RuntimeError(
            "Agent merge is blocked: server-side protection is unavailable or "
            "incomplete; a human maintainer must merge manually"
        )
    snapshot = merge_snapshot(
        github, lease, args.authorization_url, getattr(args, "actor", "")
    )
    merge_exact(
        args,
        github,
        lease,
        str(snapshot["title"]),
        close_issue=bool(snapshot.get("close_issue")),
    )


def merge_quota(args: argparse.Namespace, github: GitHub) -> None:
    """Merge one routine exact-head zero-step exception under its lease."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, getattr(args, "actor", ""), github)
    routine_quota_snapshot(github, lease, getattr(args, "actor", ""))
    snapshot = routine_quota_snapshot(
        github, lease, getattr(args, "actor", "")
    )
    merge_exact(args, github, lease, str(snapshot["title"]), close_issue=True)


def close_merged_issue_under_lease(
    github: GitHub,
    lease: dict[str, Any],
    explicit_actor: str,
) -> dict[str, object]:
    """Close an integrated Issue after two current lease snapshots."""
    snapshot = merged_issue_snapshot(github, lease, explicit_actor)
    if snapshot["issue_state"] not in {"open", "closed"}:
        raise RuntimeError("Closing Issue state is unavailable")
    if snapshot["issue_state"] == "open":
        snapshot = merged_issue_snapshot(github, lease, explicit_actor)
        issue_number = snapshot["issue_number"]
        if not isinstance(issue_number, int):
            raise RuntimeError("Closing Issue identity is unavailable")
        result = github.close_issue(str(lease["repository"]), issue_number)
        if (
            result.get("number") != issue_number
            or result.get("state") != "closed"
        ):
            raise RuntimeError("GitHub did not close the exact Issue")
        issue = github.get(
            str(lease["repository"]), f"issues/{issue_number}"
        )
        if not isinstance(issue, dict) or issue.get("state") != "closed":
            raise RuntimeError("Closed Issue state could not be verified")
    return snapshot


def close_integrated_issue(args: argparse.Namespace, github: GitHub) -> None:
    """Close one integrated Issue and release its retained merge lease."""
    lease = read_lease(args.lease)
    if (
        str(lease["repository"]).casefold() != args.repo.casefold()
        or lease["pull_request"] != args.pr_number
        or lease["head_sha"] != args.head_sha
    ):
        raise RuntimeError("Lease does not match the requested pull request")
    require_caller(lease, args.owner, getattr(args, "actor", ""), github)
    snapshot = close_merged_issue_under_lease(
        github, lease, getattr(args, "actor", "")
    )
    release_refs(lease)
    sys.stdout.write(json.dumps(snapshot, sort_keys=True) + "\n")


def release(args: argparse.Namespace, github: GitHub) -> None:
    """Release only the exact lease held by this evidence file."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, getattr(args, "actor", ""), github)
    if (
        lease["repository"].casefold() != args.repo.casefold()
        or lease["pull_request"] != args.pr_number
    ):
        raise RuntimeError("Lease does not match the requested pull request")
    require_origin(args.repo)
    require_committed_lease(github, lease)
    release_refs(lease)


def authorization_template(args: argparse.Namespace, github: GitHub) -> None:
    """Print the exact statement a human maintainer may post."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, getattr(args, "actor", ""), github)
    require_lease(github, lease, args.repo, args.pr_number, args.head_sha)
    sys.stdout.write(
        authorization_statement(args.repo, args.pr_number, args.head_sha)
    )


def lease_status(args: argparse.Namespace, github: GitHub) -> None:
    """Print the canonical read-only lease status for one exact PR head."""
    snapshot = lease_status_snapshot(
        github, args.repo, args.pr_number, args.head_sha
    )
    sys.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")


def edit_standalone_issue(args: argparse.Namespace, github: GitHub) -> None:
    """Edit metadata only after proving the target is an Issue, not a PR."""
    values = [
        *args.add_label,
        *args.remove_label,
        *args.add_assignee,
        *([args.issue_type] if args.issue_type else []),
    ]
    if REPOSITORY.fullmatch(args.repo) is None or args.issue_number < 1:
        raise RuntimeError("Issue identity is invalid")
    if (not values and not args.remove_type) or any(
        not value or "\n" in value for value in values
    ):
        raise RuntimeError(
            "Issue metadata must use non-empty single-line values"
        )
    issue = github.get(args.repo, f"issues/{args.issue_number}")
    if (
        not isinstance(issue, dict)
        or issue.get("number") != args.issue_number
        or issue.get("pull_request") is not None
    ):
        raise RuntimeError("Target must be a standalone Issue")
    command = [
        "gh",
        "issue",
        "edit",
        str(args.issue_number),
        "--repo",
        args.repo,
    ]
    for label in args.add_label:
        command.extend(("--add-label", label))
    for label in args.remove_label:
        command.extend(("--remove-label", label))
    for assignee in args.add_assignee:
        command.extend(("--add-assignee", assignee))
    if args.issue_type:
        command.extend(("--type", args.issue_type))
    elif args.remove_type:
        command.append("--remove-type")
    run(command)


def compact_tokens(text: str) -> str:
    """Remove source-language separators without hiding command tokens."""
    return re.sub(r"[^a-z0-9_./@-]+", "", text.casefold())


def lifecycle_api_target(compact: str) -> bool:
    """Return whether text names a mutable pull-request or Issue endpoint."""
    repository = r"repos/(?:[^/?]+/)?[^/?]+"
    prefix = repository + r"/(?:pulls|issues)/[^/?]+"
    return bool(
        re.search(prefix + r"(?:[?]|$)", compact)
        or re.search(prefix + r"/(?:labels|milestones)(?:[/?-]|$)", compact)
        or re.search(repository + r"/pulls/.+?/merge(?:[?]|$)", compact)
    )


def declarative_writer_violations(text: str) -> list[str]:
    """Find GraphQL and action writers regardless of their host language."""
    compact = compact_tokens(text)
    graphql_writers = [
        "convert" + "pullrequest" + "todraft",
        "mark" + "pullrequest" + "readyforreview",
        "merge" + "pullrequest",
        "update" + "pullrequest",
        "add" + "labelstolabelable",
        "remove" + "labelsfromlabelable",
    ]
    violations = []
    if any(
        re.search(rf"(?:graphql|mutation).{{0,500}}{writer}", compact)
        for writer in graphql_writers
    ):
        violations.append("GraphQL PR lifecycle mutation")
    release_writer = "googleapis/" + "release-please-" + "action@"
    if release_writer in compact:
        violations.append("opaque release pull-request writer")
    return violations


def command_writer_violations(text: str) -> list[str]:
    """Find lifecycle writes in shell or YAML logical command blocks."""
    violations: list[str] = []
    shell = text.replace("\\\r\n", " ").replace("\\\n", " ")
    blocks = [*shell.splitlines(), shell]
    for block in blocks:
        compact = compact_tokens(block)
        if any(
            f"ghpr{operation}" in compact
            for operation in ("ready", "edit", "merge")
        ):
            violations.append("direct gh pr lifecycle command")
        if "ghprcreate" in compact and any(
            option in compact
            for option in ("--label", "--milestone", "--draft")
        ):
            violations.append(
                "PR creation with an unleased metadata/state write"
            )
        if "ghissueedit" in compact and any(
            option in compact
            for option in (
                "--add-label",
                "--remove-label",
                "--milestone",
                "--remove-milestone",
            )
        ):
            violations.append("gh issue metadata write")
        if "ghapi" in compact and lifecycle_api_target(compact):
            lowered = block.casefold()
            markers = re.findall(r"(?:--method|-x)", lowered)
            methods = re.findall(
                r"(?:--method|-x)[\s='\"`\\]*([a-z]+)", lowered
            )
            fields = any(
                option in compact
                for option in ("--field", "--raw-field", "--input", "-f")
            )
            if (
                len(methods) != len(markers)
                or any(
                    method not in {"get", "head", "options"}
                    for method in methods
                )
                or (not methods and fields)
            ):
                violations.append("REST pull-request or issue metadata write")

    return violations + declarative_writer_violations(text)


def ast_name(node: ast.AST, aliases: dict[str, str]) -> str:
    """Return a dotted call name, resolving imported module aliases."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        prefix = ast_name(node.value, aliases)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        name = ast_name(node.func, aliases)
        return f"{name}()" if name else ""
    return ""


def ast_text(node: ast.AST, values: dict[str, str]) -> str | None:
    """Resolve string constants while retaining safe dynamic placeholders."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return values.get(node.id)
    if isinstance(node, ast.JoinedStr):
        return "".join(
            value.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
            else "dynamic"
            for value in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = ast_text(node.left, values)
        right = ast_text(node.right, values)
        return None if left is None or right is None else left + right
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
    ):
        return "dynamic"
    return None


def ast_argv(
    node: ast.AST, values: dict[str, str], sequences: dict[str, list[str]]
) -> list[str] | None:
    """Resolve a constant subprocess argv, preserving dynamic arguments."""
    if isinstance(node, ast.Name):
        return sequences.get(node.id)
    if isinstance(node, (ast.List, ast.Tuple)):
        result: list[str] = []
        for item in node.elts:
            if isinstance(item, ast.Starred):
                expanded = ast_argv(item.value, values, sequences)
                if expanded is None:
                    return None
                result.extend(expanded)
                continue
            result.append(ast_text(item, values) or "dynamic")
        return result
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = ast_argv(node.left, values, sequences)
        right = ast_argv(node.right, values, sequences)
        return None if left is None or right is None else left + right
    text = ast_text(node, values)
    return [text] if text is not None else None


def python_writer_violations(text: str) -> list[str]:  # noqa: C901
    """Inspect Python calls structurally instead of flattening source text."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"

    values: dict[str, str] = {}
    sequences: dict[str, list[str]] = {}
    clients: dict[str, str] = {}
    violations: list[str] = []
    subprocess_calls = {
        "os.popen",
        "os.system",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.run",
    }
    write_methods = {"delete", "patch", "post", "put"}
    events = sorted(
        (
            node
            for node in ast.walk(tree)
            if isinstance(
                node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Call)
            )
        ),
        key=lambda node: (node.lineno, node.col_offset),
    )
    for node in events:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            value = node.value
            client = (
                ast_name(value.func, aliases).casefold().replace("()", "")
                if isinstance(value, ast.Call)
                else ""
            )
            resolved_text = (
                ast_text(value, values) if value is not None else None
            )
            resolved_argv = (
                ast_argv(value, values, sequences)
                if value is not None
                else None
            )
            for target_node in targets:
                if not isinstance(target_node, ast.Name):
                    continue
                values.pop(target_node.id, None)
                sequences.pop(target_node.id, None)
                clients.pop(target_node.id, None)
                if resolved_text is not None:
                    values[target_node.id] = resolved_text
                if resolved_argv is not None:
                    sequences[target_node.id] = resolved_argv
                if client in {
                    "httpx.asyncclient",
                    "httpx.client",
                    "requests.session",
                }:
                    clients[target_node.id] = client
            continue
        if isinstance(node, ast.AugAssign):
            if not isinstance(node.op, ast.Add) or not isinstance(
                node.target, ast.Name
            ):
                continue
            name = node.target.id
            added_text = ast_text(node.value, values)
            if name in values and added_text is not None:
                values[name] += added_text
            else:
                values.pop(name, None)
            added_argv = ast_argv(node.value, values, sequences)
            if name in sequences and added_argv is not None:
                sequences[name] = [*sequences[name], *added_argv]
            else:
                sequences.pop(name, None)
            clients.pop(name, None)
            continue

        name = ast_name(node.func, aliases)
        if name in subprocess_calls and node.args:
            argv = ast_argv(node.args[0], values, sequences)
            if argv is not None:
                violations.extend(command_writer_violations(" ".join(argv)))

        parts = name.casefold().replace("()", "").split(".")
        if parts and parts[0] in clients:
            parts = [*clients[parts[0]].split("."), *parts[1:]]
        root = parts[0] if parts else ""
        leaf = parts[-1] if parts else ""
        if root not in {"httpx", "requests", "urllib"}:
            continue
        keywords = {item.arg: item.value for item in node.keywords if item.arg}
        method: str | None = None
        url_node: ast.AST | None = None
        urllib_request = name.casefold().endswith("urllib.request.request")
        urllib_urlopen = name.casefold().endswith("urllib.request.urlopen")
        if urllib_request:
            url_node = node.args[0] if node.args else keywords.get("url")
            method_node = keywords.get("method")
            if method_node is not None:
                resolved = ast_text(method_node, values)
                method = resolved.casefold() if resolved is not None else None
            elif "data" in keywords or len(node.args) > 1:
                method = "post"
            else:
                method = "get"
        elif urllib_urlopen:
            url_node = node.args[0] if node.args else keywords.get("url")
            method = (
                "post" if "data" in keywords or len(node.args) > 1 else "get"
            )
        elif leaf in write_methods | {"get", "head", "options"}:
            method = leaf
            url_node = node.args[0] if node.args else keywords.get("url")
        elif leaf == "request":
            method_node = node.args[0] if node.args else keywords.get("method")
            url_node = (
                node.args[1] if len(node.args) > 1 else keywords.get("url")
            )
            resolved = (
                ast_text(method_node, values)
                if method_node is not None
                else None
            )
            method = resolved.casefold() if resolved is not None else None
        else:
            continue
        url = ast_text(url_node, values) if url_node is not None else None
        lifecycle_target = url is not None and lifecycle_api_target(
            compact_tokens(url)
        )
        unresolved_urllib = (urllib_request or urllib_urlopen) and (
            (method is None and lifecycle_target)
            or (url is None and method in write_methods)
        )
        if method in write_methods and (
            lifecycle_target
            or root in {"httpx", "requests"}
            or unresolved_urllib
        ):
            violations.append("Python HTTP client lifecycle mutation")
        elif method not in write_methods | {"get", "head", "options"} and (
            lifecycle_target
            or root in {"httpx", "requests"}
            or unresolved_urllib
        ):
            violations.append("Python HTTP method cannot be proven read-only")
    return violations


def writer_violations(text: str) -> list[str]:
    """Find lifecycle writes in scripts and workflows."""
    try:
        ast.parse(text)
    except SyntaxError:
        found = command_writer_violations(text)
    else:
        found = declarative_writer_violations(text)
        found.extend(python_writer_violations(text))
    return sorted(set(found))


def canonical_scanner_helper(root: Path, path: Path) -> bool:
    """Trust only exact in-root helper paths without symlink components."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if relative.as_posix() not in {
        "scripts/pr_lifecycle.py",
        "template/scripts/pr_lifecycle.py",
    }:
        return False
    current = root
    if current.is_symlink():
        return False
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return False
    try:
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except FileNotFoundError:
        return False
    except ValueError:
        return False
    return resolved == resolved_root / relative


def scan_writers(root: Path) -> None:
    """Fail when repository automation bypasses the lifecycle tool."""
    paths = [
        *root.glob(".github/workflows/*.yml"),
        *root.glob(".github/workflows/*.yaml"),
        *root.joinpath("scripts").rglob("*"),
        *root.glob("template/.github/workflows/*.yml"),
        *root.glob("template/.github/workflows/*.yaml"),
        *root.joinpath("template/scripts").rglob("*"),
    ]
    violations: list[str] = []
    for path in sorted(set(paths)):
        relative = path.relative_to(root)
        if (
            not path.is_file()
            or ("__pycache__" in relative.parts and path.suffix == ".pyc")
            or canonical_scanner_helper(root, path)
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise RuntimeError(
                f"Automation file is not valid UTF-8: {relative}"
            ) from error
        found = writer_violations(text)
        violations.extend(f"{relative}: {item}" for item in found)
    if violations:
        raise RuntimeError(
            "Unleased PR lifecycle writer:\n" + "\n".join(violations)
        )


def parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(required=True)
    acquire_command = commands.add_parser("acquire")
    acquire_command.add_argument("--repo", required=True)
    acquire_command.add_argument("--pr-number", required=True, type=int)
    acquire_command.add_argument("--head-sha", required=True)
    acquire_command.add_argument("--owner", required=True)
    acquire_command.add_argument("--actor", default="")
    acquire_command.add_argument("--ttl-seconds", type=int, default=3600)
    acquire_command.add_argument("--output", type=Path, required=True)
    acquire_command.set_defaults(handler=acquire)
    status_command = commands.add_parser("lease-status")
    status_command.add_argument("--repo", required=True)
    status_command.add_argument("--pr-number", required=True, type=int)
    status_command.add_argument("--head-sha", required=True)
    status_command.set_defaults(handler=lease_status)
    scan_command = commands.add_parser("scan-writers")
    scan_command.add_argument("--root", type=Path, default=Path.cwd())
    scan_command.set_defaults(scan_root=True)
    issue_edit = commands.add_parser("issue-edit")
    issue_edit.add_argument("--repo", required=True)
    issue_edit.add_argument("--issue-number", required=True, type=int)
    issue_edit.add_argument("--add-label", action="append", default=[])
    issue_edit.add_argument("--remove-label", action="append", default=[])
    issue_edit.add_argument("--add-assignee", action="append", default=[])
    issue_type = issue_edit.add_mutually_exclusive_group()
    issue_type.add_argument("--type", dest="issue_type")
    issue_type.add_argument("--remove-type", action="store_true")
    issue_edit.set_defaults(handler=edit_standalone_issue)

    for name in (
        "state",
        "edit",
        "check",
        "merge",
        "merge-quota",
        "close-issue",
        "authorization-template",
        "release",
    ):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        command.add_argument("--pr-number", required=True, type=int)
        command.add_argument("--lease", type=Path, required=True)
        command.add_argument("--owner", required=True)
        command.add_argument("--actor", default="")
        if name != "release":
            command.add_argument("--head-sha", required=True)
        if name in {"check", "merge"}:
            command.add_argument("--authorization-url", required=True)
        if name == "state":
            command.add_argument(
                "--state", choices=("ready", "draft"), required=True
            )
        if name == "edit":
            command.add_argument("--body-file", type=Path)
            command.add_argument("--add-label", action="append", default=[])
            command.add_argument("--remove-label", action="append", default=[])
            milestone = command.add_mutually_exclusive_group()
            milestone.add_argument("--milestone")
            milestone.add_argument("--remove-milestone", action="store_true")
        command.set_defaults(handler_name=name)
    return result


def main() -> None:  # noqa: C901
    """Run one fail-closed lifecycle operation."""
    args = parser().parse_args()
    github = GitHub()
    try:
        if hasattr(args, "scan_root"):
            scan_writers(args.root.resolve())
        elif hasattr(args, "handler"):
            args.handler(args, github)
        elif args.handler_name == "state":
            mutate_state(args, github)
        elif args.handler_name == "check":
            check(args, github)
        elif args.handler_name == "edit":
            edit_metadata(args, github)
        elif args.handler_name == "merge":
            merge(args, github)
        elif args.handler_name == "merge-quota":
            merge_quota(args, github)
        elif args.handler_name == "close-issue":
            close_integrated_issue(args, github)
        elif args.handler_name == "authorization-template":
            authorization_template(args, github)
        else:
            release(args, github)
    except (RuntimeError, json.JSONDecodeError) as error:
        sys.stderr.write(f"PR lifecycle blocked: {error}\n")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
