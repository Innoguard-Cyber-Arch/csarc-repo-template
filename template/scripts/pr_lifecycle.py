#!/usr/bin/env python3
"""Serialize pull-request lifecycle writes across local tasks."""

from __future__ import annotations

import argparse
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
from typing import Any

LEASE_SCHEMA = 2
MAX_TTL_SECONDS = 7200
MIN_OPERATION_SECONDS = 30
MAINTAINER_ASSOCIATIONS = {"MEMBER", "OWNER"}
SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
OWNER = re.compile(r"[A-Za-z0-9._/@:-]{1,200}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
UNCHECKED = re.compile(r"(?m)^\s*[-*+]\s+\[\s*\]")
CLOSING_ISSUE = re.compile(r"(?:Closes|Fixes|Resolves)\s+#(\d+)(?:\D|$)", re.I)
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
        return json.loads(run(["gh", "api", f"repos/{repo}/{path}"]))

    def viewer(self) -> str:
        """Return the authenticated user or GitHub App actor."""
        try:
            payload = json.loads(run(["gh", "api", "user"]))
            login = payload.get("login") if isinstance(payload, dict) else None
            if isinstance(login, str) and login:
                return login
        except RuntimeError:
            pass
        installation = json.loads(run(["gh", "api", "installation"]))
        slug = (
            installation.get("app_slug")
            if isinstance(installation, dict)
            else None
        )
        if not isinstance(slug, str) or not slug:
            raise RuntimeError("Authenticated GitHub actor is unavailable")
        return f"{slug}[bot]"

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


def lease_refs(pull: dict[str, Any], default_branch: str) -> list[str]:
    """Lock the PR and the shared promotion lane when it targets default."""
    refs = [pr_ref(int(pull["number"]))]
    base = pull.get("base") or {}
    if base.get("ref") == default_branch:
        refs.append("refs/heads/csarc/leases/promotion")
    return refs


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
        or not payload["actor"]
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
    """Limit evidence to the PR ref and optional promotion-lane ref."""
    refs = lease.get("refs")
    required = pr_ref(int(lease["pull_request"]))
    expected = [required]
    if lease.get("base_ref") == lease.get("default_branch"):
        expected.append("refs/heads/csarc/leases/promotion")
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
        raise RuntimeError("Pull request base or promotion lease scope drifted")
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
    user = comment.get("user") or {} if isinstance(comment, dict) else {}
    if (
        not isinstance(comment, dict)
        or comment.get("html_url") != lease["audit_url"]
        or not str(comment.get("issue_url", "")).endswith(
            f"/issues/{lease['pull_request']}"
        )
        or comment.get("body") != audit_message(lease)
        or str(user.get("login", "")).casefold()
        != str(lease["actor"]).casefold()
    ):
        raise RuntimeError("Remote lease audit comment is invalid")


def require_caller(lease: dict[str, Any], owner: str, github: GitHub) -> None:
    """Require the task owner and actor that acquired the lease."""
    if lease["owner"] != owner:
        raise RuntimeError("Task owner does not hold this lifecycle lease")
    if str(lease["actor"]).casefold() != github.viewer().casefold():
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
        or not isinstance(core.get("actor"), str)
        or not core["actor"]
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
    """Atomically acquire the PR and optional promotion-lane refs."""
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
        "actor": github.viewer(),
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
        if not isinstance(audit_url, str):
            raise RuntimeError("Lease audit comment has no URL")
        evidence["audit_url"] = audit_url
        validate_audit_url(evidence)
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


def effective_protection(
    github: GitHub, repo: str, branch: str
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


def merge_snapshot(  # noqa: C901
    github: GitHub,
    lease: dict[str, Any],
    authorization_url: str,
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
    comments = github.pages(repo, f"issues/{pr_number}/comments?per_page=100")
    blocker = unresolved_blocker(comments)
    if blocker is not None:
        raise RuntimeError(
            "An unresolved blocking comment prevents merge: "
            + str(blocker.get("html_url") or "unknown URL")
        )
    reviews = github.pages(repo, f"pulls/{pr_number}/reviews?per_page=100")
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
    actor = github.viewer().casefold()
    approvers = sorted(
        login
        for login, state in review_states.items()
        if state == "APPROVED" and login != actor
    )
    if not approvers:
        raise RuntimeError("An independent approving review is required")
    if actor != str(lease["actor"]).casefold():
        raise RuntimeError(
            "Authenticated GitHub actor changed after lease acquisition"
        )
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
    }


def mutate_state(args: argparse.Namespace, github: GitHub) -> None:
    """Change Draft state only while the exact lease remains live."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, github)
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


def edit_metadata(args: argparse.Namespace, github: GitHub) -> None:
    """Edit labels or milestone only while the exact lease remains live."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, github)
    require_lease(github, lease, args.repo, args.pr_number, args.head_sha)
    pull = live_pull(github, args.repo, args.pr_number, args.head_sha)
    labels = {
        item.get("name")
        for item in pull.get("labels", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if not (
        args.add_label
        or args.remove_label
        or args.milestone is not None
        or args.remove_milestone
    ):
        raise RuntimeError("At least one label or milestone edit is required")
    if any(
        "\n" in label or not label
        for label in args.add_label + args.remove_label
    ):
        raise RuntimeError("Label names must be non-empty single-line values")
    expected_labels = (labels | set(args.add_label)) - set(args.remove_label)
    command = ["gh", "pr", "edit", str(args.pr_number), "--repo", args.repo]
    for label in args.add_label:
        command.extend(("--add-label", label))
    for label in args.remove_label:
        command.extend(("--remove-label", label))
    if args.milestone is not None:
        command.extend(("--milestone", args.milestone))
    elif args.remove_milestone:
        command.append("--remove-milestone")
    run(command)
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
    if updated_labels != expected_labels or not milestone_matches:
        raise RuntimeError("Pull request metadata did not change as requested")


def check(args: argparse.Namespace, github: GitHub) -> None:
    """Print the live merge snapshot without mutating GitHub."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, github)
    snapshot = merge_snapshot(github, lease, args.authorization_url)
    sys.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")


def merge(args: argparse.Namespace, github: GitHub) -> None:
    """Merge only when both the lease and server-side controls are enforced."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, github)
    snapshot = merge_snapshot(github, lease, args.authorization_url)
    if snapshot["merge_mode"] != "agent":
        raise RuntimeError(
            "Agent merge is blocked: server-side protection is unavailable or "
            "incomplete; a human maintainer must merge manually"
        )
    snapshot = merge_snapshot(github, lease, args.authorization_url)
    title = str(snapshot["title"])
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
    require_caller(lease, args.owner, github)
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
    require_caller(lease, args.owner, github)
    require_lease(github, lease, args.repo, args.pr_number, args.head_sha)
    sys.stdout.write(
        authorization_statement(args.repo, args.pr_number, args.head_sha) + "\n"
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
    acquire_command.add_argument("--ttl-seconds", type=int, default=3600)
    acquire_command.add_argument("--output", type=Path, required=True)
    acquire_command.set_defaults(handler=acquire)

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
        if name != "release":
            command.add_argument("--head-sha", required=True)
        if name in {"check", "merge"}:
            command.add_argument("--authorization-url", required=True)
        if name == "state":
            command.add_argument(
                "--state", choices=("ready", "draft"), required=True
            )
        if name == "edit":
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
        if hasattr(args, "handler"):
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
