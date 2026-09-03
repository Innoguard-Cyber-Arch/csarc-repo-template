#!/usr/bin/env python3
"""Serialize pull-request lifecycle writes across local tasks."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
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
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    promotion_gate = importlib.import_module("promotion_gate")
else:
    promotion_gate = importlib.import_module(f"{__package__}.promotion_gate")


LEASE_SCHEMA = 2
MAX_TTL_SECONDS = 7200
MIN_OPERATION_SECONDS = 30
MAINTAINER_ASSOCIATIONS = {"MEMBER", "OWNER"}
SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
OWNER = re.compile(r"[A-Za-z0-9._/@:-]{1,200}")
ACTOR = re.compile(r"[A-Za-z0-9_.-]+(?:\[bot\])?")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
DELIVERY_BRANCH = re.compile(r"^dev/m([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$")
ISSUE_WORK_BRANCH = re.compile(
    r"^(?:build|chore|ci|docs|feat|fix|refactor|revert|test)/"
    r"([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$"
)
ALPHA_SELF_MERGE_MARKER = "Alpha 自行合併 / self-merged"
WORK_CLOSURE_MARKER = "Work Issue closure evidence"
UNCHECKED = re.compile(r"(?m)^\s*[-*+]\s+\[\s*\]")
CLOSING_ISSUE = re.compile(
    r"(?<!\w)(?:Closes|Fixes|Resolves)[ \t]+#([1-9][0-9]*)(?!\w)"
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
        """Close one validated work Issue as completed."""
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
    github: GitHub, repo: str, pr_number: int, head_sha: str
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


def branch_sha(github: GitHub, repo: str, branch: str) -> str:
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


def expired_remote_lease(
    github: GitHub, repo: str, commit_sha: str, held_ref: str
) -> dict[str, Any]:
    """Validate one canonical expired lease before an atomic reclaim."""
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
    if expires_at > datetime.now(UTC):
        raise RuntimeError("Another owner already holds the PR lifecycle lease")
    return core


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


def require_routine_route(  # noqa: C901
    github: GitHub,
    repo: str,
    lease: dict[str, Any],
    pull: dict[str, Any],
) -> str:
    """Require a same-repository Issue or exact current-main sync route."""
    base_ref = (pull.get("base") or {}).get("ref")
    head = pull.get("head")
    if not isinstance(head, dict):
        raise RuntimeError("Routine pull request head is invalid")
    head_ref = head.get("ref")
    head_repo_payload = head.get("repo")
    head_repo = (
        head_repo_payload.get("full_name")
        if isinstance(head_repo_payload, dict)
        else None
    )
    if base_ref == lease["default_branch"]:
        raise RuntimeError(
            "Routine fallback is forbidden for default-branch routes"
        )
    if (
        not isinstance(base_ref, str)
        or DELIVERY_BRANCH.fullmatch(base_ref) is None
        or not isinstance(head_ref, str)
        or not isinstance(head_repo, str)
        or head_repo.casefold() != repo.casefold()
    ):
        raise RuntimeError(
            "Routine fallback requires a same-repository delivery route"
        )
    work = ISSUE_WORK_BRANCH.fullmatch(head_ref)
    if work:
        issue_number = int(work.group(1))
        closing_issues = [
            int(value)
            for value in CLOSING_ISSUE.findall(str(pull.get("body") or ""))
        ]
        if closing_issues != [issue_number]:
            raise RuntimeError(
                "Routine work branch must close its matching Issue exactly"
            )
        issue = github.get(repo, f"issues/{issue_number}")
        if (
            not isinstance(issue, dict)
            or type(issue.get("number")) is not int
            or issue["number"] != issue_number
            or issue.get("pull_request") is not None
            or issue.get("state") != "open"
        ):
            raise RuntimeError("Routine work branch Issue is not open")
        delivery = DELIVERY_BRANCH.fullmatch(base_ref)
        expected_milestone = int(delivery.group(1)) if delivery else None
        milestone = issue.get("milestone")
        if milestone is None:
            actual_milestone = None
        elif (
            isinstance(milestone, dict) and type(milestone.get("number")) is int
        ):
            actual_milestone = milestone["number"]
        else:
            raise RuntimeError("Routine work branch Issue Milestone is invalid")
        if actual_milestone != expected_milestone:
            raise RuntimeError(
                "Routine work branch Issue Milestone does not match its base"
            )
        return "issue"
    main_sha = branch_sha(github, repo, str(lease["default_branch"]))
    expected_sync = promotion_gate.delivery_sync.sync_branch_name(
        base_ref, main_sha
    )
    if head_ref != expected_sync:
        raise RuntimeError(
            "Routine fallback requires a work branch or the exact "
            "current-main sync branch"
        )
    head_sha = head.get("sha")
    base_sha = (pull.get("base") or {}).get("sha")
    if (
        not isinstance(head_sha, str)
        or SHA.fullmatch(head_sha) is None
        or not isinstance(base_sha, str)
        or SHA.fullmatch(base_sha) is None
    ):
        raise RuntimeError("Routine sync commit identity is invalid")
    comparison = github.get(
        repo,
        f"compare/{urllib.parse.quote(main_sha, safe='')}..."
        f"{urllib.parse.quote(head_sha, safe='')}",
    )
    compare_status = (
        comparison.get("status") if isinstance(comparison, dict) else None
    )
    if not isinstance(compare_status, str):
        raise RuntimeError("Routine sync comparison is invalid")
    if not promotion_gate.delivery_sync.includes_main(compare_status):
        raise RuntimeError("Routine sync head does not contain current main")
    commit = github.get(repo, f"git/commits/{head_sha}")
    parents = commit.get("parents") if isinstance(commit, dict) else None
    parent_shas = (
        [item.get("sha") for item in parents if isinstance(item, dict)]
        if isinstance(parents, list)
        else []
    )
    if parent_shas != [base_sha, main_sha]:
        raise RuntimeError(
            "Routine sync head must merge current main into the exact base"
        )
    return "sync"


def alpha_self_merge_opt_in(
    github: GitHub,
    repo: str,
    lease: dict[str, Any],
    pull: dict[str, Any],
) -> bool:
    """Validate the exact Alpha marker and its non-default routine route."""
    marker_count = (
        str(pull.get("body") or "").splitlines().count(ALPHA_SELF_MERGE_MARKER)
    )
    if marker_count == 0:
        return False
    if marker_count != 1:
        raise RuntimeError("Alpha self-merge marker must appear exactly once")
    route = require_routine_route(github, repo, lease, pull)
    if route != "issue":
        raise RuntimeError(
            "Alpha self-merge is only available for routine Issue routes"
        )
    return True


def unresolved_blocker(comments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the latest unresolved merge-blocker marker."""
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
    if latest_blocker is None:
        return None
    if latest_resolution is not None and latest_resolution > latest_blocker[0]:
        return None
    return latest_blocker[1]


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


def effective_protection(  # noqa: C901
    github: GitHub,
    repo: str,
    branch: str,
    alpha_self_merge: bool = False,
) -> tuple[str, str, set[tuple[str, int | None]]]:
    """Prove the route's review, check, and no-bypass enforcement."""
    try:
        rules = github.get(
            repo, f"rules/branches/{urllib.parse.quote(branch, safe='')}"
        )
    except RuntimeError as error:
        return "unknown", str(error), set()
    if not isinstance(rules, list) or not all(
        isinstance(item, dict) for item in rules
    ):
        return "unknown", "effective branch rules are unavailable", set()
    pull_rules = [item for item in rules if item.get("type") == "pull_request"]
    check_rules = [
        item for item in rules if item.get("type") == "required_status_checks"
    ]
    if any(
        not isinstance(item.get("parameters"), dict)
        for item in pull_rules + check_rules
    ):
        return "unknown", "effective rule parameters are malformed", set()
    pull = [item["parameters"] for item in pull_rules]
    checks = [item["parameters"] for item in check_rules]
    review_flags = (
        "dismiss_stale_reviews_on_push",
        "require_code_owner_review",
        "require_last_push_approval",
        "required_review_thread_resolution",
    )
    if any(
        type(parameters.get("required_approving_review_count")) is not int
        or parameters["required_approving_review_count"] < 0
        or any(
            type(parameters.get(field)) is not bool for field in review_flags
        )
        for parameters in pull
    ):
        return "unknown", "pull request rules are malformed", set()
    required_groups = [
        parameters.get("required_status_checks") for parameters in checks
    ]
    if any(not isinstance(items, list) for items in required_groups):
        return "unknown", "required check rules are malformed", set()
    required_items = [item for items in required_groups for item in items]
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("context"), str)
        or not item["context"]
        or (
            item.get("integration_id") is not None
            and (
                type(item.get("integration_id")) is not int
                or item["integration_id"] <= 0
            )
        )
        for item in required_items
    ):
        return "unknown", "required check rules are malformed", set()
    required_contexts = {
        (str(item["context"]), item.get("integration_id"))
        for item in required_items
        if isinstance(item, dict)
    }
    if alpha_self_merge:
        review_controls = bool(pull) and all(
            type(item.get("required_approving_review_count")) is int
            and item["required_approving_review_count"] == 0
            and item.get("required_review_thread_resolution") is True
            for item in pull
        )
        missing_reason = (
            "explicit zero-review Alpha policy, thread, or check rules are "
            "missing"
        )
    else:
        review_controls = (
            any(
                item.get("required_approving_review_count", 0) >= 1
                for item in pull
            )
            and any(
                item.get("dismiss_stale_reviews_on_push") is True
                for item in pull
            )
            and any(
                item.get("require_code_owner_review") is True for item in pull
            )
            and any(
                item.get("require_last_push_approval") is True for item in pull
            )
            and any(
                item.get("required_review_thread_resolution") is True
                for item in pull
            )
        )
        missing_reason = (
            "required approval, stale-review dismissal, CODEOWNER, last-push, "
            "thread, or check rules are missing"
        )
    if not review_controls or not required_contexts:
        return (
            "blocked",
            missing_reason,
            set(),
        )
    ruleset_id_values = [
        item.get("ruleset_id") for item in pull_rules + check_rules
    ]
    if not ruleset_id_values or any(
        type(value) is not int or value <= 0 for value in ruleset_id_values
    ):
        return (
            "unknown",
            "effective rules do not expose their Ruleset identity",
            set(),
        )
    ruleset_ids = set(ruleset_id_values)
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


def check_run_matches_context(
    item: dict[str, Any], context: str, integration_id: int | None
) -> bool:
    """Match a check only when its pinned GitHub App identity is exact."""
    if item.get("name") != context:
        return False
    if integration_id is None:
        return True
    app = item.get("app")
    return (
        isinstance(app, dict)
        and type(app.get("id")) is int
        and app["id"] > 0
        and app["id"] == integration_id
    )


def authoritative_check_runs(
    check_runs: list[dict[str, Any]], head_sha: str
) -> list[dict[str, Any]]:
    """Keep the newest check for each strict GitHub App identity."""
    candidate_runs = [
        item for item in check_runs if item.get("head_sha") == head_sha
    ]
    identities: list[tuple[str, int, int]] = []
    latest_ids: dict[tuple[str, int], int] = {}
    for item in candidate_runs:
        name = item.get("name")
        check_id = item.get("id")
        app = item.get("app")
        app_id = app.get("id") if isinstance(app, dict) else None
        if (
            not isinstance(name, str)
            or not name
            or type(check_id) is not int
            or check_id <= 0
            or type(app_id) is not int
            or app_id <= 0
        ):
            raise RuntimeError("Check run identity is malformed")
        identity = (name, app_id)
        identities.append((name, app_id, check_id))
        latest_ids[identity] = max(latest_ids.get(identity, 0), check_id)
    return [
        item
        for item, (name, app_id, check_id) in zip(
            candidate_runs, identities, strict=True
        )
        if latest_ids[(name, app_id)] == check_id
    ]


def require_successful_checks(  # noqa: C901
    github: GitHub,
    repo: str,
    head_sha: str,
    contexts: set[tuple[str, int | None]],
    quota_run_urls: set[str] | None = None,
) -> str:
    """Require protected contexts to pass or have exact quota evidence."""
    check_runs = github.collection(
        repo,
        f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
        "check_runs",
    )
    authoritative_runs = authoritative_check_runs(check_runs, head_sha)
    statuses = github.collection(
        repo,
        f"commits/{head_sha}/status?per_page=100",
        "statuses",
        head_sha,
    )
    passing_runs = [
        item
        for item in authoritative_runs
        if item.get("head_sha") == head_sha
        and item.get("status") == "completed"
        and item.get("conclusion") in SUCCESSFUL_CHECK_CONCLUSIONS
    ]
    passing_statuses = {
        item.get("context")
        for item in statuses
        if item.get("state") == "success"
    }
    missing = [
        (context, integration_id)
        for context, integration_id in contexts
        if not any(
            check_run_matches_context(item, context, integration_id)
            for item in passing_runs
        )
        and not (integration_id is None and context in passing_statuses)
    ]
    missing.sort(key=lambda item: (item[0], -1 if item[1] is None else item[1]))
    if quota_run_urls:
        non_quota_failures: set[str] = set()
        for item in authoritative_runs:
            name = str(item.get("name") or "unnamed check")
            if item.get("status") != "completed":
                non_quota_failures.add(name)
                continue
            if item.get("conclusion") in SUCCESSFUL_CHECK_CONCLUSIONS:
                continue
            if item.get("conclusion") != "failure":
                non_quota_failures.add(name)
                continue
            try:
                run_url = actions_run_url(
                    str(item.get("details_url") or ""), repo
                )
            except RuntimeError:
                non_quota_failures.add(name)
                continue
            if run_url not in quota_run_urls:
                non_quota_failures.add(name)
        non_quota_failures.update(
            str(item.get("context") or "unnamed status")
            for item in statuses
            if item.get("state") in {"error", "failure"}
        )
        if non_quota_failures:
            raise RuntimeError(
                "Non-quota check failures remain on the exact head: "
                + ", ".join(sorted(non_quota_failures))
            )
    if not missing:
        return "quota-fallback" if quota_run_urls else "success"
    if quota_run_urls:
        for context, integration_id in missing:
            failed_runs = [
                item
                for item in authoritative_runs
                if item.get("name") == context
                and item.get("head_sha") == head_sha
                and item.get("status") == "completed"
                and item.get("conclusion") == "failure"
                and check_run_matches_context(item, context, integration_id)
            ]
            if len(failed_runs) != 1:
                break
            run_url = actions_run_url(
                str(failed_runs[0].get("details_url") or ""), repo
            )
            if run_url not in quota_run_urls:
                break
        else:
            return "quota-fallback"
    raise RuntimeError(
        "Required checks have not succeeded on the exact head: "
        + ", ".join(context for context, _integration_id in missing)
    )


def actions_run_url(details_url: str, repo: str) -> str:
    """Normalize an exact-repository Actions check URL to its run URL."""
    parsed = urllib.parse.urlparse(details_url)
    match = re.fullmatch(
        rf"/{re.escape(repo)}/actions/runs/(\d+)(?:/job/\d+)?",
        parsed.path,
    )
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() != "github.com"
        or match is None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "Failed check has no exact-repository Actions run URL"
        )
    return f"https://github.com/{repo}/actions/runs/{match.group(1)}"


def require_routine_quota_fallback(
    github: GitHub,
    lease: dict[str, Any],
    pull: dict[str, Any],
    authorization_payload: dict[str, Any],
    note_url: str,
) -> set[str]:
    """Validate a canonical routine-PR quota note and every bound run."""
    repo = str(lease["repository"])
    pr_number = int(lease["pull_request"])
    head_sha = str(lease["head_sha"])
    require_routine_route(github, repo, lease, pull)
    parsed = urllib.parse.urlparse(note_url)
    expected_path = f"/{repo}/pull/{pr_number}"
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() != "github.com"
        or parsed.path.casefold() != expected_path.casefold()
        or re.fullmatch(r"issuecomment-(\d+)", parsed.fragment) is None
    ):
        raise RuntimeError(
            "Quota fallback URL must be a comment on this pull request"
        )
    comment_id = parsed.fragment.removeprefix("issuecomment-")
    payload = github.get(repo, f"issues/comments/{comment_id}")
    if (
        not isinstance(payload, dict)
        or payload.get("html_url") != note_url
        or not str(payload.get("issue_url", "")).endswith(
            f"/issues/{pr_number}"
        )
    ):
        raise RuntimeError("Quota fallback comment response is invalid")
    body = payload.get("body")
    prefix = "Actions quota fallback note\n\n`"
    if not isinstance(body, str) or not body.startswith(prefix):
        raise RuntimeError("Quota fallback note is not canonical")
    binding_end = body.find("`\n\n", len(prefix))
    if binding_end < 0:
        raise RuntimeError("Quota fallback note is not canonical")
    binding = json.loads(body[len(prefix) : binding_end])
    runs = binding.get("runs") if isinstance(binding, dict) else None
    if (
        not isinstance(runs, list)
        or not runs
        or not all(isinstance(item, str) for item in runs)
        or len(set(runs)) != len(runs)
        or body
        != promotion_gate.quota_fallback_note(repo, pr_number, head_sha, runs)
    ):
        raise RuntimeError("Quota fallback note is not canonical")
    note_created_at = parse_time(payload.get("created_at"), "Quota fallback")
    authorized_at = parse_time(
        authorization_payload.get("created_at"), "Authorization"
    )
    if note_created_at > authorized_at:
        raise RuntimeError("Quota fallback note postdates merge authorization")
    head_ref = (pull.get("head") or {}).get("ref")
    if not isinstance(head_ref, str) or not head_ref:
        raise RuntimeError("Pull request head branch is unavailable")

    def get(request_repo: str, path: str, _token: str) -> object:
        return github.get(request_repo, path)

    for run_url in runs:
        promotion_gate.require_run_url(run_url, repo)
        promotion_gate.require_zero_step_run(
            run_url,
            repo,
            pr_number,
            head_ref,
            head_sha,
            "",
            getter=get,
        )
    return set(runs)


def merge_snapshot(  # noqa: C901
    github: GitHub,
    lease: dict[str, Any],
    authorization_url: str,
    explicit_actor: str = "",
    quota_fallback_note_url: str = "",
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

    alpha_self_merge = alpha_self_merge_opt_in(github, repo, lease, pull)
    timeline = github.pages(repo, f"issues/{pr_number}/timeline?per_page=100")
    if any(
        item.get("event") in DRAFT_EVENTS
        and parse_time(item.get("created_at"), "Draft event") >= authorized_at
        for item in timeline
    ):
        raise RuntimeError(
            "A newer Draft event invalidated merge authorization"
        )
    comments = [
        *github.pages(repo, f"issues/{pr_number}/comments?per_page=100"),
        *github.pages(repo, f"pulls/{pr_number}/comments?per_page=100"),
    ]
    reviews = github.pages(repo, f"pulls/{pr_number}/reviews?per_page=100")
    comments.extend(
        {
            **review,
            "created_at": review.get("submitted_at"),
        }
        for review in reviews
        if review.get("state") == "COMMENTED"
        and review.get("submitted_at")
        and review.get("body")
    )
    blocker = unresolved_blocker(comments)
    if blocker is not None:
        raise RuntimeError(
            "An unresolved blocking comment prevents merge: "
            + str(blocker.get("html_url") or "unknown URL")
        )
    review_states = current_reviews(reviews)
    blockers = sorted(
        login
        for login, state in review_states.items()
        if state == "CHANGES_REQUESTED"
    )
    if blockers:
        raise RuntimeError(
            "Changes are still requested by: " + ", ".join(blockers)
        )
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
    if not approvers and not alpha_self_merge:
        raise RuntimeError("An independent approving review is required")
    for issue_number in sorted(
        {
            int(value)
            for value in CLOSING_ISSUE.findall(str(pull.get("body") or ""))
        }
    ):
        issue = github.get(repo, f"issues/{issue_number}")
        if not isinstance(issue, dict) or issue.get("pull_request") is not None:
            raise RuntimeError(
                f"Closing reference #{issue_number} is not an Issue"
            )
        if UNCHECKED.search(str(issue.get("body") or "")):
            raise RuntimeError(
                f"Issue #{issue_number} has an unchecked checklist item"
            )

    base = pull.get("base") or {}
    base_ref = base.get("ref")
    if not isinstance(base_ref, str):
        raise RuntimeError("Pull request base branch is unavailable")
    title = pull.get("title")
    if not isinstance(title, str) or not title.strip():
        raise RuntimeError("Pull request title is unavailable")
    protection, reason, required_contexts = effective_protection(
        github, repo, base_ref, alpha_self_merge
    )
    authorization_actor = str((auth.get("user") or {}).get("login", ""))
    independently_authorized = authorization_actor.casefold() != actor
    if (
        protection == "enforced"
        and not independently_authorized
        and not alpha_self_merge
    ):
        protection = "blocked"
        reason = "merge authorization uses the executing GitHub actor"
    quota_run_urls = (
        require_routine_quota_fallback(
            github, lease, pull, auth, quota_fallback_note_url
        )
        if quota_fallback_note_url
        else set()
    )
    check_evidence = "not-enforced"
    if protection == "enforced" or quota_run_urls:
        check_evidence = require_successful_checks(
            github,
            repo,
            head_sha,
            required_contexts,
            quota_run_urls,
        )
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
        "required_check_evidence": check_evidence,
        "alpha_self_merge": alpha_self_merge,
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
        github,
        lease,
        args.authorization_url,
        getattr(args, "actor", ""),
        getattr(args, "quota_fallback_note_url", ""),
    )
    sys.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")


def merge(args: argparse.Namespace, github: GitHub) -> None:
    """Merge only when both the lease and server-side controls are enforced."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, getattr(args, "actor", ""), github)
    snapshot = merge_snapshot(
        github,
        lease,
        args.authorization_url,
        getattr(args, "actor", ""),
        getattr(args, "quota_fallback_note_url", ""),
    )
    if snapshot["merge_mode"] != "agent":
        raise RuntimeError(
            "Agent merge is blocked: server-side protection is unavailable or "
            "incomplete; a human maintainer must merge manually"
        )
    snapshot = merge_snapshot(
        github,
        lease,
        args.authorization_url,
        getattr(args, "actor", ""),
        getattr(args, "quota_fallback_note_url", ""),
    )
    title = str(snapshot["title"])
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
    release_refs(lease)


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


def work_closure_message(binding: dict[str, object]) -> str:
    """Return exact, replay-safe evidence for one work Issue closure."""
    return f"{WORK_CLOSURE_MARKER}\n\n`{canonical_json(binding)}`"


def close_work_issue(  # noqa: C901
    args: argparse.Namespace, github: GitHub
) -> None:
    """Close one Issue only after its exact work PR reaches its dev branch."""
    if (
        REPOSITORY.fullmatch(args.repo) is None
        or args.pr_number < 1
        or SHA.fullmatch(args.head_sha) is None
    ):
        raise RuntimeError("Work Issue closure input is invalid")
    repository = github.get(args.repo, "")
    pull = github.get(args.repo, f"pulls/{args.pr_number}")
    if not isinstance(repository, dict) or not isinstance(pull, dict):
        raise RuntimeError("Work Issue closure state is unavailable")
    head = pull.get("head") or {}
    base = pull.get("base") or {}
    head_repo = head.get("repo") or {} if isinstance(head, dict) else {}
    merge_sha = pull.get("merge_commit_sha")
    if (
        pull.get("number") != args.pr_number
        or pull.get("state") != "closed"
        or pull.get("merged") is not True
        or not isinstance(pull.get("merged_at"), str)
        or not isinstance(head, dict)
        or head.get("sha") != args.head_sha
        or not isinstance(head_repo, dict)
        or str(head_repo.get("full_name", "")).casefold()
        != args.repo.casefold()
        or not isinstance(base, dict)
        or not isinstance(merge_sha, str)
        or SHA.fullmatch(merge_sha) is None
    ):
        raise RuntimeError(
            "Merged pull request identity or head SHA is invalid"
        )
    parse_time(pull["merged_at"], "Pull request merge")
    default_branch = repository.get("default_branch")
    base_ref = base.get("ref")
    head_ref = head.get("ref")
    if not isinstance(default_branch, str) or not isinstance(base_ref, str):
        raise RuntimeError("Pull request destination is unavailable")
    if base_ref == default_branch:
        sys.stdout.write(
            f"PR #{args.pr_number}: default-branch closing remains "
            "GitHub-native\n"
        )
        return
    delivery = DELIVERY_BRANCH.fullmatch(base_ref)
    work = ISSUE_WORK_BRANCH.fullmatch(str(head_ref or ""))
    if delivery is None or work is None:
        raise RuntimeError("Merged pull request is not a Milestone work route")
    issue_number = int(work.group(1))
    closing_issues = [
        int(value)
        for value in CLOSING_ISSUE.findall(str(pull.get("body") or ""))
    ]
    if closing_issues != [issue_number]:
        raise RuntimeError(
            "Work pull request must close its matching Issue exactly"
        )
    issue = github.get(args.repo, f"issues/{issue_number}")
    if (
        not isinstance(issue, dict)
        or issue.get("number") != issue_number
        or issue.get("pull_request") is not None
    ):
        raise RuntimeError("Work Issue identity is invalid")
    expected_milestone = int(delivery.group(1))
    issue_milestone = issue.get("milestone") or {}
    pull_milestone = pull.get("milestone") or {}
    if (
        not isinstance(issue_milestone, dict)
        or not isinstance(pull_milestone, dict)
        or issue_milestone.get("number") != expected_milestone
        or pull_milestone.get("number") != expected_milestone
    ):
        raise RuntimeError("Work Issue, pull request, and dev branch disagree")
    binding: dict[str, object] = {
        "base_ref": base_ref,
        "head_sha": args.head_sha,
        "issue": issue_number,
        "merge_commit_sha": merge_sha,
        "pull_request": args.pr_number,
        "repository": args.repo,
        "schema_version": 1,
    }
    message = work_closure_message(binding)
    comments = github.pages(args.repo, f"issues/{issue_number}/comments")
    evidence = [
        str(comment.get("body") or "")
        for comment in comments
        if str(comment.get("body") or "").startswith(WORK_CLOSURE_MARKER)
    ]
    if len(evidence) > 1 or (evidence and evidence != [message]):
        raise RuntimeError("Work Issue has conflicting closure evidence")
    state = issue.get("state")
    if state == "closed":
        if issue.get("state_reason") != "completed" or evidence != [message]:
            raise RuntimeError(
                "Work Issue was closed without matching evidence"
            )
        sys.stdout.write(
            f"Issue #{issue_number}: already closed by PR #{args.pr_number}\n"
        )
        return
    if state != "open":
        raise RuntimeError("Work Issue state is invalid")
    if not evidence:
        github.comment(args.repo, issue_number, message)
    result = github.close_issue(args.repo, issue_number)
    if (
        result.get("number") != issue_number
        or result.get("state") != "closed"
        or result.get("state_reason") != "completed"
    ):
        raise RuntimeError("GitHub did not confirm completed Issue closure")
    sys.stdout.write(
        f"Issue #{issue_number}: closed by merged PR #{args.pr_number}\n"
    )


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
    close_work = commands.add_parser("close-work")
    close_work.add_argument("--repo", required=True)
    close_work.add_argument("--pr-number", required=True, type=int)
    close_work.add_argument("--head-sha", required=True)
    close_work.set_defaults(handler=close_work_issue)

    for name in (
        "state",
        "edit",
        "check",
        "merge",
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
            command.add_argument("--quota-fallback-note-url", default="")
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


def main() -> None:
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
        elif args.handler_name == "authorization-template":
            authorization_template(args, github)
        else:
            release(args, github)
    except (RuntimeError, json.JSONDecodeError) as error:
        sys.stderr.write(f"PR lifecycle blocked: {error}\n")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
