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
    csarc_config = importlib.import_module("csarc_config")
    dependabot_auth = importlib.import_module("authenticate_dependabot_head")
    local_verification = importlib.import_module("local_verification")
    promotion_gate = importlib.import_module("promotion_gate")
    release_level = importlib.import_module("release_level")
    review_gate = importlib.import_module("review_gate")
    verification_evidence = importlib.import_module("verification_evidence")
else:
    csarc_config = importlib.import_module(f"{__package__}.csarc_config")
    dependabot_auth = importlib.import_module(
        f"{__package__}.authenticate_dependabot_head"
    )
    local_verification = importlib.import_module(
        f"{__package__}.local_verification"
    )
    promotion_gate = importlib.import_module(f"{__package__}.promotion_gate")
    release_level = importlib.import_module(f"{__package__}.release_level")
    review_gate = importlib.import_module(f"{__package__}.review_gate")
    verification_evidence = importlib.import_module(
        f"{__package__}.verification_evidence"
    )


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
PROMOTION_BRANCH = re.compile(r"^promote/m([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$")
RELEASE_BRANCH = re.compile(
    r"^release/v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-beta\.[1-9]\d*)?$"
)
ISSUE_WORK_BRANCH = re.compile(
    r"^(?:build|chore|ci|docs|feat|fix|refactor|revert|test)/"
    r"([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$"
)
ADMIN_BYPASS_MARKER = "Admin bypass / 管理員略過審核"
WORK_CLOSURE_MARKER = "Work Issue closure evidence"
HOTFIX_POST_REVIEW_MARKER = "Emergency hotfix post-review"
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
REVIEW_CHECK_CONTEXT = "review"
DEPENDABOT_ELIGIBILITY_CONTEXT = "dependabot-merge-eligible"
GITHUB_ACTIONS_APP_ID = 15368
SUCCESSFUL_CHECK_CONCLUSIONS = {"neutral", "skipped", "success"}
TRUSTED_CHECK_PRODUCERS: dict[str, tuple[str, frozenset[str]]] = {
    DEPENDABOT_ELIGIBILITY_CONTEXT: (
        ".github/workflows/dependabot-auto-merge.yml",
        frozenset({"pull_request_target"}),
    ),
    "title": (
        ".github/workflows/pr-policy.yml",
        frozenset({"merge_group", "pull_request_target"}),
    ),
    "verify": (
        ".github/workflows/ci.yml",
        frozenset({"merge_group", "pull_request_target"}),
    ),
    "review": (
        ".github/workflows/pr-review.yml",
        frozenset(
            {
                "issue_comment",
                "merge_group",
                "pull_request_review",
                "pull_request_target",
            }
        ),
    ),
}
MAINTAINER_PERMISSIONS = {"admin", "maintain"}
REVIEWED_MERGE_BYPASS_ACTORS = [
    {
        "actor_type": "RepositoryRole",
        "actor_id": 5,
        "bypass_mode": "pull_request",
    }
]
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
# Optional core field naming the still-live lease commit an explicit renewal
# replaced (Issue #1017). Its presence is what lets an exact-head
# authorization posted under the first lease of an unbroken renewal chain
# stay valid; an ordinary acquire never carries it.
RENEWAL_FIELD = "renews"
MAX_RENEWAL_CHAIN = 64


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

    def create_issue(
        self,
        repo: str,
        title: str,
        body: str,
        assignee: str,
    ) -> dict[str, Any]:
        """Create one governed post-review task with the repo wrapper."""
        command = [
            str(Path(__file__).with_name("gh-issue-create")),
            "--repo",
            repo,
            "--title",
            title,
            "--body",
            body,
            "--type",
            "Task",
            "--label",
            "enhancement",
            "--label",
            "needs-manual-review",
            "--assignee",
            assignee,
        ]
        url = run(command).splitlines()[-1].strip()
        if not url.startswith(f"https://github.com/{repo}/issues/"):
            raise RuntimeError("Hotfix post-review Issue URL is invalid")
        return {"html_url": url}

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
    if set(payload) - {RENEWAL_FIELD} != {
        *LEASE_CORE_FIELDS,
        "capability",
        "lease_commit",
        "audit_url",
    }:
        raise RuntimeError("Lease evidence contains unexpected fields")
    if RENEWAL_FIELD in payload and (
        not isinstance(payload[RENEWAL_FIELD], str)
        or SHA.fullmatch(payload[RENEWAL_FIELD]) is None
    ):
        raise RuntimeError("Lease renewal evidence is invalid")
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
    core = {field: lease[field] for field in LEASE_CORE_FIELDS}
    if RENEWAL_FIELD in lease:
        core[RENEWAL_FIELD] = lease[RENEWAL_FIELD]
    return core


def lease_message(lease: dict[str, Any]) -> str:
    """Return the only valid lease commit message."""
    return (
        f"chore: lease PR #{lease['pull_request']}\n\n"
        f"{canonical_json(lease_core(lease))}"
    )


def audit_message(lease: dict[str, Any]) -> str:
    """Return public lease evidence without the raw capability."""
    public = {**lease_core(lease), "lease_commit": lease["lease_commit"]}
    renewal = (
        f"This explicitly renews still-live lease commit "
        f"{lease[RENEWAL_FIELD]} for the same head, owner, actor, and "
        "capability; exact-head authorizations posted since the first "
        "lease of this renewal chain remain valid.\n\n"
        if RENEWAL_FIELD in lease
        else ""
    )
    return (
        "PR lifecycle lease "
        f"{'renewed' if RENEWAL_FIELD in lease else 'acquired'}\n\n"
        f"`{canonical_json(public)}`\n\n"
        f"{renewal}"
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
    core = canonical_remote_lease(github, repo, commit_sha, held_ref)
    if parse_time(core["expires_at"], "Existing lease") > datetime.now(UTC):
        raise RuntimeError("Another owner already holds the PR lifecycle lease")
    return core


def canonical_remote_lease(
    github: GitHub, repo: str, commit_sha: str, held_ref: str
) -> dict[str, Any]:
    """Validate one remote lease commit's canonical message, parent, tree."""
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
        or set(core) - {RENEWAL_FIELD} != set(LEASE_CORE_FIELDS)
        or (
            RENEWAL_FIELD in core
            and SHA.fullmatch(str(core[RENEWAL_FIELD])) is None
        )
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


RENEWAL_IDENTITY_FIELDS = (
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
    "refs",
)


def authorization_anchor(github: GitHub, lease: dict[str, Any]) -> datetime:
    """Return the earliest time an exact-head authorization may carry.

    An ordinary lease anchors at its own `acquired_at`. An explicit renewal
    (Issue #1017) walks its `renews` chain and anchors at the first lease,
    but only while every predecessor is a canonical remote lease commit with
    the identical repository, PR, head, base, owner, actor, and capability
    digest, and was still live when its successor replaced it. A released,
    expired, or differently owned lease breaks the chain, so an
    authorization posted before every lease on this exact head never counts.
    """
    anchor = parse_time(lease["acquired_at"], "Lease")
    current: dict[str, Any] = lease
    for _ in range(MAX_RENEWAL_CHAIN):
        predecessor_sha = current.get(RENEWAL_FIELD)
        if predecessor_sha is None:
            return anchor
        predecessor = canonical_remote_lease(
            github,
            str(lease["repository"]),
            str(predecessor_sha),
            pr_ref(int(lease["pull_request"])),
        )
        if any(
            predecessor.get(field) != lease[field]
            for field in RENEWAL_IDENTITY_FIELDS
        ):
            raise RuntimeError(
                "Lease renewal chain changed head, base, owner, actor, "
                "or capability"
            )
        renewed_at = parse_time(current["acquired_at"], "Lease")
        started_at = parse_time(predecessor["acquired_at"], "Renewed lease")
        ended_at = parse_time(predecessor["expires_at"], "Renewed lease")
        if not started_at < renewed_at <= ended_at:
            raise RuntimeError(
                "Lease renewal chain is not contiguous; a renewal must "
                "replace a still-live lease"
            )
        anchor = started_at
        current = predecessor
    raise RuntimeError("Lease renewal chain is too long")


def renewable_lease(
    args: argparse.Namespace, github: GitHub
) -> dict[str, Any] | None:
    """Return the still-live lease an explicit `--renew` replaces, if any.

    Renewal (Issue #1017) is only for the caller that already holds the
    exact lease: same evidence capability, owner, actor, PR, and head, with
    the remote refs, base, and destination still unchanged and the lease not
    yet expired. Anything else must release and acquire a fresh lease, which
    requires a new exact-head authorization.
    """
    path = getattr(args, "renew", None)
    if path is None:
        return None
    previous = read_lease(path)
    require_caller(previous, args.owner, getattr(args, "actor", ""), github)
    try:
        require_lease(
            github, previous, args.repo, args.pr_number, args.head_sha
        )
    except RuntimeError as error:
        raise RuntimeError(
            f"Lease cannot be renewed ({error}); release it and acquire a "
            "fresh lease, which requires a new exact-head authorization"
        ) from error
    return previous


def acquire(args: argparse.Namespace, github: GitHub) -> None:  # noqa: C901
    """Atomically acquire, or explicitly renew, the PR and lane refs."""
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
    previous = renewable_lease(args, github)
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
    if previous is not None:
        if refs != previous["refs"] or any(
            existing != previous["lease_commit"]
            for existing in observed.values()
        ):
            raise RuntimeError("Lease ownership changed before renewal")
    else:
        for ref, existing in observed.items():
            if existing is not None:
                expired_remote_lease(github, args.repo, existing, ref)
    acquired = datetime.now(UTC)
    tree = run(["git", "rev-parse", f"{args.head_sha}^{{tree}}"])
    capability = (
        str(previous["capability"])
        if previous is not None
        else secrets.token_hex(32)
    )
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
        "reclaimed_commits": []
        if previous is not None
        else sorted(
            {commit for commit in observed.values() if commit is not None}
        ),
    }
    if previous is not None:
        if any(
            core[field] != previous[field] for field in RENEWAL_IDENTITY_FIELDS
        ):
            raise RuntimeError(
                "Lease renewal cannot change head, base, owner, or actor"
            )
        core[RENEWAL_FIELD] = previous["lease_commit"]
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
        if previous is None:
            release_refs(evidence)
        else:
            # Restore the still-live lease rather than dropping it.
            create_refs(
                str(previous["lease_commit"]),
                refs,
                {ref: commit for ref in refs},
            )
        raise
    if previous is None:
        warn_prior_authorization(github, evidence)


def warn_prior_authorization(github: GitHub, lease: dict[str, Any]) -> None:
    """Say when a fresh lease strands an earlier exact-head authorization."""
    try:
        prior = find_exact_head_authorization(
            github,
            str(lease["repository"]),
            int(lease["pull_request"]),
            str(lease["head_sha"]),
        )
    except RuntimeError as error:
        sys.stderr.write(
            "PR lifecycle notice: could not check earlier authorizations: "
            f"{error}\n"
        )
        return
    if prior is None or parse_time(
        prior.get("created_at"), "Authorization"
    ) >= parse_time(lease["acquired_at"], "Lease"):
        return
    sys.stderr.write(
        "PR lifecycle warning: exact-head authorization "
        f"{prior.get('html_url') or 'comment'} predates this fresh lease and "
        "will not be accepted; a new authorization is required. To keep an "
        "authorization valid, renew a still-live lease with "
        "`acquire --renew <lease.json>` instead of releasing it.\n"
    )


def authorization(
    github: GitHub, repo: str, pr_number: int, head_sha: str, url: str
) -> dict[str, Any]:
    """Require a maintainer authorization bound to the exact PR head.

    The `collaborators/{login}/permission` lookup below, not the comment's
    `author_association`, is what proves the author is a maintainer (Issue
    #785): `author_association` is computed relative to what the querying
    credential can resolve, and a restricted `GITHUB_TOKEN` reports a real
    org member as `COLLABORATOR` rather than `MEMBER` -- see #549 for the
    identical problem, fixed the same way, in `sync_milestone_state.py`.
    """
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
        or not isinstance(user.get("login"), str)
        or user.get("type") != "User"
        or normalized_comment_body(body) != expected_body
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


def find_exact_head_authorization(
    github: GitHub, repo: str, pr_number: int, head_sha: str
) -> dict[str, Any] | None:
    """Return the newest exact-head maintainer authorization, if one exists.

    Unlike `authorization()`, which validates one comment a caller already
    points to (the merge attempt's own evidence), this scans every comment
    on the pull request to answer "has a maintainer authorized this exact
    head at all" -- used by `scripts/review_gate.py` to let the `review`
    required check recognize an admin-bypass authorization the same way
    it recognizes a native `APPROVED` review, without needing a lease or a
    specific comment URL threaded through.

    Deliberately does not check the comment's `author_association` (Issue
    #785): that field is computed relative to what the *querying*
    credential can resolve, not an absolute fact about the commenter, and
    the restricted `GITHUB_TOKEN` the `review` job runs under reports a
    genuine org member as `COLLABORATOR` instead of `MEMBER` -- #549 hit
    and fixed the identical problem in `sync_milestone_state.py`. The
    `collaborators/{login}/permission` lookup below is the authoritative,
    token-scope-independent check; requiring `admin`/`maintain` permission
    there is what actually enforces "a real maintainer wrote this."
    """
    expected_body = authorization_statement(repo, pr_number, head_sha)
    comments = github.pages(repo, f"issues/{pr_number}/comments?per_page=100")
    candidates: list[dict[str, Any]] = []
    for payload in comments:
        if not isinstance(payload, dict):
            continue
        user = payload.get("user") or {}
        if (
            normalized_comment_body(payload.get("body")) != expected_body
            or not isinstance(user.get("login"), str)
            or user.get("type") != "User"
        ):
            continue
        permission = github.get(
            repo,
            "collaborators/"
            f"{urllib.parse.quote(str(user['login']), safe='')}/permission",
        )
        permission_user = (
            permission.get("user") if isinstance(permission, dict) else None
        )
        if (
            not isinstance(permission, dict)
            or permission.get("permission") not in MAINTAINER_PERMISSIONS
            or not isinstance(permission_user, dict)
            or str(permission_user.get("login", "")).casefold()
            != str(user["login"]).casefold()
        ):
            continue
        if not isinstance(payload.get("created_at"), str):
            continue
        candidates.append(payload)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: parse_time(item.get("created_at"), "Authorization"),
    )


def normalized_comment_body(body: object) -> str | None:
    """Return a comment body with web-UI line endings and padding removed.

    GitHub stores a comment pasted through the web UI with CRLF line
    endings (Issue #991), so the exact statement is compared after
    normalizing CRLF to LF and stripping surrounding whitespace.
    """
    if not isinstance(body, str):
        return None
    return body.replace("\r\n", "\n").strip()


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


def hotfix_emergency_evidence(  # noqa: C901
    github: GitHub,
    repo: str,
    pull: dict[str, Any],
    authorization_payload: dict[str, Any],
) -> dict[str, object]:
    """Validate the beta+ admin hotfix exception and return its evidence."""
    labels = {
        str(label.get("name") or "").casefold()
        for label in pull.get("labels", [])
        if isinstance(label, dict)
    }
    if "hotfix" not in labels:
        raise RuntimeError("Emergency self-review is limited to hotfix PRs")
    issue_numbers = sorted(
        {
            int(value)
            for value in CLOSING_ISSUE.findall(str(pull.get("body") or ""))
        }
    )
    if len(issue_numbers) != 1:
        raise RuntimeError(
            "Emergency hotfix merge requires exactly one closing Issue"
        )
    issue_number = issue_numbers[0]
    issue = github.get(repo, f"issues/{issue_number}")
    if not isinstance(issue, dict) or issue.get("pull_request") is not None:
        raise RuntimeError("Emergency hotfix work item is not an Issue")
    issue_labels = {
        str(label.get("name") or "").casefold()
        for label in issue.get("labels", [])
        if isinstance(label, dict)
    }
    if (
        issue.get("state") != "open"
        or issue.get("milestone") is not None
        or "hotfix" not in issue_labels
    ):
        raise RuntimeError(
            "Emergency hotfix requires one open, standalone hotfix Issue"
        )
    actor = str((authorization_payload.get("user") or {}).get("login") or "")
    proposer = str((issue.get("user") or {}).get("login") or "")
    if not actor or actor.casefold() != proposer.casefold():
        raise RuntimeError(
            "Emergency hotfix authorization must come from the Issue proposer"
        )
    permission = github.get(
        repo,
        f"collaborators/{urllib.parse.quote(actor, safe='')}/permission",
    )
    if (
        not isinstance(permission, dict)
        or permission.get("permission") != "admin"
        or str((permission.get("user") or {}).get("login") or "").casefold()
        != actor.casefold()
    ):
        raise RuntimeError(
            "Emergency hotfix authorization requires admin permission"
        )
    reasons: list[tuple[datetime, str, str]] = []
    for comment in github.pages(
        repo, f"issues/{issue_number}/comments?per_page=100"
    ):
        user = comment.get("user") or {}
        body = comment.get("body")
        if (
            not isinstance(body, str)
            or str(user.get("login") or "").casefold() != actor.casefold()
            or user.get("type") != "User"
        ):
            continue
        command = next(
            (line.strip() for line in body.splitlines() if line.strip()), ""
        )
        prefix = "admin-approve:"
        if not command.casefold().startswith(prefix):
            continue
        reason = command[len(prefix) :].strip()
        url = comment.get("html_url")
        if reason and isinstance(url, str):
            reasons.append(
                (
                    parse_time(comment.get("created_at"), "Hotfix approval"),
                    reason,
                    url,
                )
            )
    if not reasons:
        raise RuntimeError(
            "Emergency hotfix requires `Admin-approve: <reason>` on its Issue"
        )
    _, reason, reason_url = max(reasons)
    return {
        "issue_number": issue_number,
        "actor": actor,
        "permission": "admin",
        "reason": reason,
        "reason_url": reason_url,
    }


def ensure_hotfix_post_review(
    github: GitHub,
    repo: str,
    pr_number: int,
    head_sha: str,
    release_level_name: str,
    authorization_url: str,
    evidence: dict[str, object],
) -> str:
    """Create or reuse the required human follow-up for an emergency hotfix."""
    actor = str(evidence["actor"])
    binding = canonical_json(
        {
            "actor": actor,
            "head_sha": head_sha,
            "pull_request": pr_number,
            "repository": repo,
        }
    )
    marker = f"<!-- {HOTFIX_POST_REVIEW_MARKER}: {binding} -->"
    for issue in github.pages(
        repo, "issues?state=all&labels=needs-manual-review&per_page=100"
    ):
        if marker in str(issue.get("body") or ""):
            url = issue.get("html_url")
            if isinstance(url, str):
                return url
    title = f"Review emergency hotfix PR #{pr_number}"
    body = (
        "### Problem\n\n"
        f"PR #{pr_number} was merged through the audited {release_level_name} "
        "emergency hotfix exception and still needs independent review.\n\n"
        "### Acceptance criteria\n\n"
        "- [ ] A maintainer other than the merge actor reviews the "
        "merged head.\n"
        "- [ ] Any findings are resolved or linked to follow-up work.\n\n"
        "### Evidence\n\n"
        f"- Pull request: https://github.com/{repo}/pull/{pr_number}\n"
        f"- Exact head: `{head_sha}`\n"
        f"- Merge actor: `@{actor}` (`admin`)\n"
        f"- Exact-head authorization: {authorization_url}\n"
        f"- Emergency reason: {evidence['reason']} "
        f"({evidence['reason_url']})\n\n"
        "## Release level / 發布層級\n\n"
        f"{release_level_name}\n\n"
        f"{marker}\n"
    )
    created = github.create_issue(repo, title, body, actor)
    url = created.get("html_url")
    if not isinstance(url, str):
        raise RuntimeError("Hotfix post-review Issue was not created")
    return url


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


def require_default_branch_issue_route(
    github: GitHub,
    repo: str,
    lease: dict[str, Any],
    pull: dict[str, Any],
) -> None:
    """Require a same-repository, Milestone-less Issue route into default.

    Deliberately separate from `require_routine_route`: that function is
    shared with `require_routine_quota_fallback` (the unrelated Actions
    quota/billing required-check fallback from #325), and its default-branch
    prohibition must stay intact for that path -- quota-fallback gaining
    reach onto `main` would bypass required status checks there, a much
    larger and unrelated risk. This checks the same "real, open, exactly
    one Issue" shape `require_routine_route`'s issue branch checks, but a
    Milestone-tracked Issue must use its `dev/mN` delivery branch instead
    (`AGENTS.md` working-loop step 8), so this route requires the opposite:
    no Milestone at all.
    """
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
    if (
        not isinstance(head_repo, str)
        or head_repo.casefold() != repo.casefold()
    ):
        raise RuntimeError(
            "Default-branch stable route requires a same-repository head"
        )
    work = ISSUE_WORK_BRANCH.fullmatch(str(head_ref)) if head_ref else None
    if work is None:
        raise RuntimeError(
            "Default-branch stable route requires an Issue work branch"
        )
    issue_number = int(work.group(1))
    closing_issues = [
        int(value)
        for value in CLOSING_ISSUE.findall(str(pull.get("body") or ""))
    ]
    if closing_issues != [issue_number]:
        raise RuntimeError(
            "Default-branch stable route must close its matching Issue exactly"
        )
    issue = github.get(repo, f"issues/{issue_number}")
    if (
        not isinstance(issue, dict)
        or type(issue.get("number")) is not int
        or issue["number"] != issue_number
        or issue.get("pull_request") is not None
        or issue.get("state") != "open"
    ):
        raise RuntimeError("Default-branch stable route Issue is not open")
    if issue.get("milestone") is not None:
        raise RuntimeError(
            "Default-branch stable route requires a Milestone-less Issue"
        )


def admin_bypass_opt_in(
    github: GitHub,
    repo: str,
    lease: dict[str, Any],
    pull: dict[str, Any],
) -> bool:
    """Validate the exact admin-bypass marker and its audited route."""
    marker_count = (
        str(pull.get("body") or "").splitlines().count(ADMIN_BYPASS_MARKER)
    )
    if marker_count == 0:
        return False
    if marker_count != 1:
        raise RuntimeError("Admin bypass marker must appear exactly once")
    base_ref = (pull.get("base") or {}).get("ref")
    if base_ref == lease["default_branch"]:
        head = pull.get("head") or {}
        head_ref = str(head.get("ref") or "")
        labels = {
            str(item.get("name") or "")
            for item in pull.get("labels", [])
            if isinstance(item, dict)
        }
        route = promotion_gate.route_for(str(base_ref), head_ref, labels)
        if RELEASE_BRANCH.fullmatch(head_ref) or route.kind == "milestone":
            head_repo = head.get("repo") or {}
            head_repo_name = str(head_repo.get("full_name") or "")
            if head_repo_name.casefold() != repo.casefold():
                raise RuntimeError(
                    "Admin-bypassed release or promotion requires a "
                    "same-repository head"
                )
            return True
        require_default_branch_issue_route(github, repo, lease, pull)
        return True
    route = require_routine_route(github, repo, lease, pull)
    if route not in {"issue", "sync"}:
        raise RuntimeError(
            "Admin bypass is only available for routine Issue or sync routes"
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


def current_reviews(
    reviews: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return each reviewer's current decisive review."""
    current: dict[str, dict[str, Any]] = {}
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
            current[reviewer] = review
    return current


def exact_head_approval(
    github: GitHub,
    repo: str,
    reviews: dict[str, dict[str, Any]],
    head_sha: str,
    actor: str,
) -> dict[str, Any] | None:
    """Return the newest independent maintainer approval for this head.

    Ignores `author_association` for the same reason `authorization()`
    does (Issue #785): the `collaborators/{login}/permission` lookup below
    is the token-scope-independent source of truth.
    """
    approved: list[dict[str, Any]] = []
    for login, review in reviews.items():
        user = review.get("user") or {}
        if (
            login == actor
            or review.get("state") != "APPROVED"
            or review.get("commit_id") != head_sha
            or not isinstance(user, dict)
            or user.get("type") != "User"
        ):
            continue
        permission = github.get(
            repo,
            "collaborators/"
            f"{urllib.parse.quote(str(user['login']), safe='')}/permission",
        )
        permission_user = (
            permission.get("user") if isinstance(permission, dict) else None
        )
        if (
            not isinstance(permission, dict)
            or permission.get("permission") not in MAINTAINER_PERMISSIONS
            or not isinstance(permission_user, dict)
            or str(permission_user.get("login", "")).casefold() != login
        ):
            continue
        parse_time(review.get("submitted_at"), "Review approval")
        approved.append(review)
    if not approved:
        return None
    return max(
        approved,
        key=lambda item: parse_time(
            item.get("submitted_at"), "Review approval"
        ),
    )


def effective_protection(  # noqa: C901
    github: GitHub,
    repo: str,
    branch: str,
    admin_bypass: bool = False,
    reviewed_merge: bool = False,
    copilot_mode: bool = False,
    local_mode: bool = False,
) -> tuple[str, str, set[tuple[str, int]], bool, bool]:
    """Prove review and check enforcement for an exact-head merge."""
    try:
        rules = github.get(
            repo, f"rules/branches/{urllib.parse.quote(branch, safe='')}"
        )
    except RuntimeError as error:
        return "unknown", str(error), set(), False, False
    if not isinstance(rules, list) or not all(
        isinstance(item, dict) for item in rules
    ):
        return (
            "unknown",
            "effective branch rules are unavailable",
            set(),
            False,
            False,
        )
    pull_rules = [item for item in rules if item.get("type") == "pull_request"]
    check_rules = [
        item for item in rules if item.get("type") == "required_status_checks"
    ]
    if any(
        not isinstance(item.get("parameters"), dict)
        for item in pull_rules + check_rules
    ):
        return (
            "unknown",
            "effective rule parameters are malformed",
            set(),
            False,
            False,
        )
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
        return (
            "unknown",
            "pull request rules are malformed",
            set(),
            False,
            False,
        )
    required_groups = [
        parameters.get("required_status_checks") for parameters in checks
    ]
    if any(not isinstance(items, list) for items in required_groups):
        return (
            "unknown",
            "required check rules are malformed",
            set(),
            False,
            False,
        )
    required_items = [item for items in required_groups for item in items]
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("context"), str)
        or not item["context"]
        or type(item.get("integration_id")) is not int
        or item["integration_id"] <= 0
        for item in required_items
    ):
        return (
            "unknown",
            "required check rules are malformed",
            set(),
            False,
            False,
        )
    required_contexts = {
        (str(item["context"]), int(item["integration_id"]))
        for item in required_items
        if isinstance(item, dict)
    }
    copilot_rules = [
        item for item in rules if item.get("type") == "copilot_code_review"
    ]
    level_check_controls = (
        bool(pull)
        and all(
            item.get("required_approving_review_count") == 0 for item in pull
        )
        and any(
            item.get("dismiss_stale_reviews_on_push") is True for item in pull
        )
        and any(
            item.get("required_review_thread_resolution") is True
            for item in pull
        )
        and any(
            context == REVIEW_CHECK_CONTEXT for context, _ in required_contexts
        )
    )
    if local_mode:
        review_controls = (
            bool(pull)
            and all(
                item.get("required_approving_review_count", 0) >= 1
                for item in pull
            )
            and any(
                item.get("dismiss_stale_reviews_on_push") is True
                for item in pull
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
            "local mode needs native review, stale-review dismissal, "
            "last-push approval, and thread controls"
        )
    elif admin_bypass:
        review_controls = level_check_controls
        missing_reason = (
            "level-aware zero-review, stale-review dismissal, thread, or "
            "`review` check rules are missing"
        )
    elif copilot_mode:
        # Issue #752: zero required approvals is only safe while Copilot
        # re-reviews every push and the `review` required check (which
        # accepts a clean exact-head Copilot review or a maintainer
        # approval) guards the merge.
        review_controls = (
            level_check_controls
            and any(
                isinstance(item.get("parameters"), dict)
                and item["parameters"].get("review_on_push") is True
                for item in copilot_rules
            )
            and any(
                context == REVIEW_CHECK_CONTEXT
                for context, _ in required_contexts
            )
        )
        missing_reason = (
            "Copilot review-on-push, stale-review dismissal, thread, or "
            "`review` check rules are missing"
        )
    else:
        native_review_controls = (
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
        review_controls = native_review_controls or level_check_controls
        missing_reason = (
            "native approval controls or the level-aware `review` check are "
            "missing"
        )
    if not review_controls or (not local_mode and not required_contexts):
        return (
            "blocked",
            missing_reason,
            set(),
            False,
            False,
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
            False,
            False,
        )
    ruleset_ids = set(ruleset_id_values)
    reviewed_bypass = False
    for ruleset_id in ruleset_ids:
        try:
            ruleset = github.get(repo, f"rulesets/{ruleset_id}")
        except RuntimeError as error:
            return "unknown", str(error), set(), False, False
        if not isinstance(ruleset, dict):
            return (
                "unknown",
                "effective Ruleset is malformed",
                set(),
                False,
                False,
            )
        bypass_actors = ruleset.get("bypass_actors")
        if ruleset.get("enforcement") != "active":
            return (
                "blocked",
                "an effective Ruleset is inactive",
                set(),
                False,
                False,
            )
        if local_mode:
            if bypass_actors == []:
                continue
            if (
                not reviewed_merge
                or bypass_actors != REVIEWED_MERGE_BYPASS_ACTORS
            ):
                return (
                    "blocked",
                    "local mode exposes an unverified admin pull-request "
                    "bypass",
                    set(),
                    False,
                    False,
                )
            reviewed_bypass = True
        elif bypass_actors != []:
            if (
                not reviewed_merge
                or bypass_actors != REVIEWED_MERGE_BYPASS_ACTORS
            ):
                return (
                    "blocked",
                    "an effective Ruleset permits an unverified bypass",
                    set(),
                    False,
                    False,
                )
            reviewed_bypass = True
    copilot_only_block_possible = all(
        item.get("type")
        in {
            "copilot_code_review",
            "non_fast_forward",
            "pull_request",
            "required_status_checks",
        }
        for item in rules
    ) and any(
        item.get("ruleset_id") in ruleset_ids
        and isinstance(item.get("parameters"), dict)
        and item["parameters"].get("review_on_push") is True
        for item in copilot_rules
    )
    return (
        "enforced",
        (
            "exact-head review and checks are revalidated by lifecycle"
            if reviewed_bypass
            else "server-side merge controls are active without bypass"
        ),
        required_contexts,
        reviewed_bypass,
        copilot_only_block_possible,
    )


def repository_root() -> Path:
    """Return the repository root for root and generated layouts."""
    parent = Path(__file__).resolve().parents[1]
    return parent.parent if parent.name == ".csarc" else parent


def configured_verification_mode() -> str:
    """Return the normalized local-or-hosted verification choice."""
    return str(
        csarc_config.load_config(repository_root() / ".csarc/config.yml")[
            "verification_mode"
        ]
    )


def require_local_pull_policy(repo: str, pull: dict[str, Any]) -> None:
    """Run the existing PR policy checker locally in read-only mode."""
    base = pull.get("base") or {}
    head = pull.get("head") or {}
    author = pull.get("user") or {}
    env = os.environ.copy()
    env.update(
        {
            "GITHUB_REPOSITORY": repo,
            "PR_AUTHOR": str(author.get("login") or ""),
            "PR_BASE": str(base.get("ref") or ""),
            "PR_BASE_SHA": str(base.get("sha") or ""),
            "PR_DRAFT": str(bool(pull.get("draft"))).lower(),
            "PR_HEAD": str(head.get("ref") or ""),
            "PR_HEAD_REPOSITORY": str(
                (head.get("repo") or {}).get("full_name") or ""
            ),
            "PR_HEAD_SHA": str(head.get("sha") or ""),
            "PR_NUMBER": str(pull.get("number") or ""),
            "PR_POLICY_READ_ONLY": "true",
            "PR_TITLE": str(pull.get("title") or ""),
        }
    )
    run([str(repository_root() / "scripts/validate-pr-policy")], env=env)


def check_run_matches_context(
    item: dict[str, Any], context: str, integration_id: int
) -> bool:
    """Match a check only when its pinned GitHub App identity is exact."""
    if item.get("name") != context:
        return False
    app = item.get("app")
    return (
        isinstance(app, dict)
        and type(app.get("id")) is int
        and app["id"] > 0
        and app["id"] == integration_id
    )


def trusted_check_run_matches_context(
    github: GitHub,
    repo: str,
    head_sha: str,
    item: dict[str, Any],
    context: str,
    integration_id: int,
    run_cache: dict[int, dict[str, Any]],
) -> bool:
    """Match a required check to its trusted workflow and event."""
    if item.get("head_sha") != head_sha or not check_run_matches_context(
        item, context, integration_id
    ):
        return False
    producer = TRUSTED_CHECK_PRODUCERS.get(context)
    if producer is None:
        return False
    try:
        run_url = actions_run_url(str(item.get("details_url") or ""), repo)
    except RuntimeError:
        return False
    run_id = int(run_url.rsplit("/", 1)[1])
    if run_id not in run_cache:
        payload = github.get(repo, f"actions/runs/{run_id}")
        if not isinstance(payload, dict):
            raise RuntimeError("Required check Actions run is malformed")
        run_cache[run_id] = payload
    run = run_cache[run_id]
    repository = run.get("repository")
    check_suite = item.get("check_suite")
    workflow_path, trusted_events = producer
    suite_matches = (
        isinstance(check_suite, dict)
        and type(check_suite.get("id")) is int
        and check_suite["id"] > 0
        and type(run.get("check_suite_id")) is int
        and run["check_suite_id"] == check_suite["id"]
    )
    published_review_matches = (
        context == REVIEW_CHECK_CONTEXT
        and isinstance(check_suite, dict)
        and type(check_suite.get("id")) is int
        and check_suite["id"] > 0
        and item.get("external_id") == f"csarc-review:{run_id}:{head_sha}"
        and item.get("details_url") == run.get("html_url")
    )
    return (
        type(run.get("id")) is int
        and run["id"] == run_id
        and (suite_matches or published_review_matches)
        and run.get("head_sha") == head_sha
        and isinstance(repository, dict)
        and repository.get("full_name") == repo
        and run.get("path") == workflow_path
        and run.get("event") in trusted_events
    )


def trusted_required_check_runs(
    github: GitHub,
    repo: str,
    head_sha: str,
    contexts: set[tuple[str, int]],
    check_runs: list[dict[str, Any]],
) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[int, dict[str, Any]]]:
    """Select each newest check once after validating trusted provenance."""
    run_cache: dict[int, dict[str, Any]] = {}
    required_runs: dict[tuple[str, int], dict[str, Any]] = {}
    for context, integration_id in contexts:
        candidates = [
            item
            for item in check_runs
            if trusted_check_run_matches_context(
                github,
                repo,
                head_sha,
                item,
                context,
                integration_id,
                run_cache,
            )
        ]
        if candidates:
            required_runs[(context, integration_id)] = max(
                candidates, key=lambda item: int(item["id"])
            )
    return required_runs, run_cache


def require_trusted_dependabot_head(
    github: GitHub,
    repo: str,
    pull: dict[str, Any],
    head_sha: str,
    base_sha: str,
) -> str:
    """Reauthenticate one exact Dependabot head and its trusted eligibility."""
    eligible, reason, live_base_sha, _, live_head_sha = (
        dependabot_auth.validated_dependabot_snapshot(pull, repo)
    )
    if not eligible or live_base_sha != base_sha or live_head_sha != head_sha:
        raise RuntimeError(f"Dependabot merge identity is invalid: {reason}")

    commit = github.get(repo, f"commits/{head_sha}")
    comparison = github.get(repo, f"compare/{base_sha}...{head_sha}")
    if not isinstance(commit, dict) or not isinstance(comparison, dict):
        raise RuntimeError("Dependabot head metadata is unavailable")
    direct, direct_reason = dependabot_auth.authenticated_dependabot_head(
        pull, commit, repo, base_sha
    )
    kind = "direct"
    if not direct:
        parents = commit.get("parents")
        parent_sha = (
            (parents[0] or {}).get("sha")
            if isinstance(parents, list) and len(parents) == 1
            else ""
        )
        if not isinstance(parent_sha, str) or SHA.fullmatch(parent_sha) is None:
            raise RuntimeError(
                "Dependabot head is not authenticated: " + direct_reason
            )
        parent_commit = github.get(repo, f"commits/{parent_sha}")
        parent_comparison = github.get(
            repo, f"compare/{base_sha}...{parent_sha}"
        )
        child, child_reason, _, _ = (
            dependabot_auth.trusted_sync_child_candidate(
                pull,
                commit,
                parent_commit if isinstance(parent_commit, dict) else {},
                (
                    parent_comparison
                    if isinstance(parent_comparison, dict)
                    else {}
                ),
                repo,
                base_sha,
            )
        )
        if not child:
            raise RuntimeError(
                "Dependabot head is not authenticated: "
                f"{direct_reason}; {child_reason}"
            )
        kind = "sync-child"

    check_runs = github.collection(
        repo,
        f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
        "check_runs",
    )
    identity = (DEPENDABOT_ELIGIBILITY_CONTEXT, GITHUB_ACTIONS_APP_ID)
    selected, _ = trusted_required_check_runs(
        github, repo, head_sha, {identity}, check_runs
    )
    check = selected.get(identity)
    if (
        check is None
        or check.get("status") != "completed"
        or check.get("conclusion") != "success"
    ):
        raise RuntimeError(
            "Dependabot head has no trusted merge eligibility on the exact head"
        )
    return kind


def require_trusted_verification(
    github: GitHub,
    repo: str,
    head_sha: str,
    integration_id: int,
    *,
    max_age_hours: float = 24.0,
    required_tier: str | None = None,
    now: datetime | None = None,
    check_runs: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    """Require fresh hosted execution evidence for one exact commit."""
    available = (
        check_runs
        if check_runs is not None
        else github.collection(
            repo,
            f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
            "check_runs",
        )
    )
    identity = ("verify", integration_id)
    selected, run_cache = trusted_required_check_runs(
        github, repo, head_sha, {identity}, available
    )
    check_run = selected.get(identity)
    if check_run is None:
        raise RuntimeError(
            "Required verify check has no trusted producer on the exact head"
        )
    run_url = actions_run_url(str(check_run.get("details_url") or ""), repo)
    run_id = int(run_url.rsplit("/", 1)[1])
    workflow_run = run_cache[run_id]
    commit = github.get(repo, f"git/commits/{head_sha}")
    tree = commit.get("tree") if isinstance(commit, dict) else None
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    if not isinstance(tree_sha, str):
        raise RuntimeError("Exact-head Git tree identity is unavailable")
    jobs = github.collection(
        repo,
        f"actions/runs/{run_id}/jobs?filter=latest&per_page=100",
        "jobs",
    )
    matching_jobs = [
        job
        for job in jobs
        if job.get("html_url") == check_run.get("details_url")
    ]
    if len(matching_jobs) != 1:
        raise RuntimeError("Trusted verify check has no unique Actions job")
    job = matching_jobs[0]
    annotations = (
        github.pages(
            repo,
            f"check-runs/{check_run['id']}/annotations?per_page=100",
        )
        if verification_evidence.needs_route_annotations(job)
        else []
    )
    source_evidence = None
    source_ids = verification_evidence.evidence_source_ids(job, annotations)
    if source_ids is not None:
        source_kind, source_run_id, source_job_id, source_check_id = source_ids
        source_check = github.get(repo, f"check-runs/{source_check_id}")
        source_run = github.get(repo, f"actions/runs/{source_run_id}")
        if not isinstance(source_check, dict) or not isinstance(
            source_run, dict
        ):
            raise RuntimeError(
                "Trusted verification reuse source is unavailable"
            )
        source_head = source_check.get("head_sha")
        if not isinstance(source_head, str) or (
            source_kind == "reuse" and source_head != head_sha
        ):
            raise RuntimeError(
                "Trusted verification reuse source head is invalid"
            )
        source_cache = {source_run_id: source_run}
        if not trusted_check_run_matches_context(
            github,
            repo,
            source_head,
            source_check,
            "verify",
            integration_id,
            source_cache,
        ):
            raise RuntimeError(
                "Trusted verification reuse source producer is invalid"
            )
        source_jobs = github.collection(
            repo,
            f"actions/runs/{source_run_id}/jobs?filter=latest&per_page=100",
            "jobs",
        )
        matching_sources = [
            source_job
            for source_job in source_jobs
            if source_job.get("id") == source_job_id
            and source_job.get("html_url") == source_check.get("details_url")
        ]
        if len(matching_sources) != 1:
            raise RuntimeError(
                "Trusted verification reuse source has no unique Actions job"
            )
        source_job = matching_sources[0]
        source_commit = (
            commit
            if source_head == head_sha
            else github.get(repo, f"git/commits/{source_head}")
        )
        source_tree = (
            source_commit.get("tree")
            if isinstance(source_commit, dict)
            else None
        )
        source_tree_sha = (
            source_tree.get("sha") if isinstance(source_tree, dict) else None
        )
        if not isinstance(source_tree_sha, str):
            raise RuntimeError(
                "Trusted verification reuse source tree is unavailable"
            )
        source_evidence = (
            source_check,
            source_run,
            source_job,
            source_tree_sha,
        )
    evidence = verification_evidence.validate_verification_job(
        check_run,
        workflow_run,
        job,
        repo=repo,
        head_sha=head_sha,
        tree_sha=tree_sha,
        now=now,
        max_age_hours=max_age_hours,
        required_tier=required_tier,
        source_evidence=source_evidence,
        annotations=annotations,
        commit_tree=lambda sha: commit_tree_sha(github, repo, sha),
        full_command=(
            "./scripts/verify-template.sh"
            if Path("scripts/verify-template.sh").is_file()
            else "./scripts/verify"
        ),
    )
    require_template_toolchain(evidence, Path("scripts/verify-template.sh"))
    return evidence


def commit_tree_sha(github: GitHub, repo: str, sha: str) -> str | None:
    """Return one commit's tree SHA, or None when GitHub cannot show it."""
    commit = github.get(repo, f"git/commits/{urllib.parse.quote(sha)}")
    tree = commit.get("tree") if isinstance(commit, dict) else None
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    return tree_sha if isinstance(tree_sha, str) else None


def require_template_toolchain(
    evidence: dict[str, object], marker: Path
) -> None:
    """Require only the template-repository toolchains used by this tier."""
    if not marker.is_file():
        return
    expected = {"python-3.14", "uv-0.12.15"}
    if evidence["tier"] == "full":
        expected.update({"pnpm-11.22.0", "node-24", "rust-1.98.0"})
    toolchain = evidence.get("toolchain")
    if not isinstance(toolchain, list) or set(toolchain) != expected:
        raise RuntimeError("Trusted verification toolchain evidence is invalid")


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
    contexts: set[tuple[str, int]],
    quota_run_urls: set[str] | None = None,
) -> str:
    """Require protected contexts to pass or have exact quota evidence."""
    check_runs = github.collection(
        repo,
        f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
        "check_runs",
    )
    authoritative_runs = authoritative_check_runs(check_runs, head_sha)
    required_runs, _run_cache = trusted_required_check_runs(
        github, repo, head_sha, contexts, check_runs
    )
    statuses = github.collection(
        repo,
        f"commits/{head_sha}/status?per_page=100",
        "statuses",
        head_sha,
    )
    missing = [
        (context, integration_id)
        for context, integration_id in contexts
        if (item := required_runs.get((context, integration_id))) is None
        or item.get("status") != "completed"
        or (
            item.get("conclusion") != "success"
            if context == "verify"
            else item.get("conclusion") not in SUCCESSFUL_CHECK_CONCLUSIONS
        )
    ]
    missing.sort()
    for context, integration_id in contexts:
        item = required_runs.get((context, integration_id))
        if (
            context == "verify"
            and item is not None
            and item.get("status") == "completed"
            and item.get("conclusion") == "success"
        ):
            require_trusted_verification(
                github,
                repo,
                head_sha,
                integration_id,
                check_runs=check_runs,
            )
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
        if any(context == "verify" for context, _integration_id in missing):
            raise RuntimeError(
                "Quota fallback cannot replace trusted verify "
                "execution evidence"
            )
        for context, integration_id in missing:
            failed_run = required_runs.get((context, integration_id))
            if (
                failed_run is None
                or failed_run.get("status") != "completed"
                or failed_run.get("conclusion") != "failure"
            ):
                break
            run_url = actions_run_url(
                str(failed_run.get("details_url") or ""), repo
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


def require_routine_quota_fallback(  # noqa: C901
    github: GitHub,
    lease: dict[str, Any],
    pull: dict[str, Any],
    authorization_payload: dict[str, Any],
    note_url: str,
) -> set[str]:
    """Validate a canonical routine-PR quota note and every bound run."""
    config_path = Path(__file__).resolve().parents[1] / ".csarc/config.yml"
    if (
        not config_path.is_file()
        or csarc_config.load_config(config_path).get("actions_fallback")
        != "admin"
    ):
        raise RuntimeError(
            "Actions billing fallback requires actions_fallback: admin"
        )
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
    authorization_url: str = "",
    explicit_actor: str = "",
    quota_fallback_note_url: str = "",
    require_dependabot_head: bool = False,
) -> dict[str, object]:
    """Re-read every mutable merge input while the lease is held."""
    repo = lease["repository"]
    pr_number = lease["pull_request"]
    head_sha = lease["head_sha"]
    require_lease(github, lease, repo, pr_number, head_sha)
    pull = live_pull(github, repo, pr_number, head_sha)
    dependabot_head = (
        require_trusted_dependabot_head(
            github, repo, pull, str(head_sha), str(lease["base_sha"])
        )
        if require_dependabot_head
        else ""
    )
    if pull.get("draft") is not False:
        raise RuntimeError("Pull request is Draft at merge time")
    if UNCHECKED.search(str(pull.get("body") or "")):
        raise RuntimeError("Pull request has an unchecked checklist item")
    level_decision = resolve_release_level(github, repo, pull)
    label_names = {
        str(label.get("name") or "").casefold()
        for label in pull.get("labels", [])
        if isinstance(label, dict)
    }
    admin_bypass = level_decision.review == "self" and admin_bypass_opt_in(
        github, repo, lease, pull
    )
    bypass_route = (
        level_decision.level
        if admin_bypass
        else "hotfix"
        if "hotfix" in label_names
        else None
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
        for login, review in review_states.items()
        if review.get("state") == "CHANGES_REQUESTED"
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
    approval = exact_head_approval(github, repo, review_states, head_sha, actor)
    hotfix_evidence: dict[str, object] | None = None
    review_mode, copilot_max_level = review_settings()
    copilot_mode = review_mode == "copilot"
    copilot_verdict = None
    if (
        approval is None
        and not admin_bypass
        and copilot_mode
        and level_decision.review == "self"
    ):
        allowed, cap_reason = review_gate.level_allows_copilot(
            copilot_max_level, level_decision.level
        )
        if not allowed:
            raise RuntimeError(cap_reason)
        copilot_verdict = review_gate.copilot_verdict(
            reviews,
            head_sha,
            lambda review_id: github.pages(
                repo,
                f"pulls/{pr_number}/reviews/{review_id}/comments?per_page=100",
            ),
        )
        if copilot_verdict.state != "clean":
            raise RuntimeError(
                "Copilot review of the exact head is not clean: "
                + copilot_verdict.reason
            )
    if approval is not None:
        auth = {
            **approval,
            "created_at": approval.get("submitted_at"),
        }
        authorization_source = "review"
        authorization_url = str(approval.get("html_url") or "")
    elif admin_bypass:
        if not authorization_url:
            raise RuntimeError(
                "Admin bypass requires an exact maintainer "
                "authorization comment"
            )
        auth = authorization(
            github, repo, pr_number, head_sha, authorization_url
        )
        if parse_time(
            auth.get("created_at"), "Authorization"
        ) < authorization_anchor(github, lease):
            raise RuntimeError(
                "Authorization predates the active lifecycle lease; renew a "
                "live lease with `acquire --renew` to keep an authorization"
            )
        auth_actor = str((auth.get("user") or {}).get("login") or "")
        if auth_actor.casefold() != actor:
            raise RuntimeError(
                "Admin-bypass authorization actor must be the merge actor"
            )
        permission = github.get(
            repo,
            f"collaborators/{urllib.parse.quote(actor, safe='')}/permission",
        )
        if (
            not isinstance(permission, dict)
            or permission.get("permission") != "admin"
            or str((permission.get("user") or {}).get("login") or "").casefold()
            != actor
        ):
            raise RuntimeError("Admin bypass requires live admin permission")
        authorization_source = "comment"
    elif copilot_verdict is not None and copilot_verdict.review is not None:
        auth = {
            **copilot_verdict.review,
            "created_at": copilot_verdict.review.get("submitted_at"),
        }
        authorization_source = "copilot"
        authorization_url = str(copilot_verdict.review.get("html_url") or "")
    elif level_decision.review == "peer" and "hotfix" in label_names:
        if not authorization_url:
            raise RuntimeError(
                "Emergency hotfix merge requires an exact-head "
                "authorization comment"
            )
        auth = authorization(
            github, repo, pr_number, head_sha, authorization_url
        )
        if parse_time(
            auth.get("created_at"), "Authorization"
        ) < authorization_anchor(github, lease):
            raise RuntimeError(
                "Emergency hotfix authorization predates the active lease"
            )
        auth_actor = str((auth.get("user") or {}).get("login") or "")
        if auth_actor.casefold() != actor:
            raise RuntimeError(
                "Emergency hotfix authorization actor must be the merge actor"
            )
        hotfix_evidence = hotfix_emergency_evidence(github, repo, pull, auth)
        authorization_source = "hotfix-emergency"
    else:
        raise RuntimeError(
            f"The {level_decision.level} release level requires an "
            "independent maintainer approval for the exact head"
        )
    authorized_at = parse_time(auth.get("created_at"), "Authorization")
    timeline = github.pages(repo, f"issues/{pr_number}/timeline?per_page=100")
    if any(
        item.get("event") in DRAFT_EVENTS
        and parse_time(item.get("created_at"), "Draft event") >= authorized_at
        for item in timeline
    ):
        raise RuntimeError(
            "A newer Draft event invalidated merge authorization"
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
    verification_mode = configured_verification_mode()
    if verification_mode == "local":
        require_local_pull_policy(repo, pull)
    (
        protection,
        reason,
        required_contexts,
        reviewed_bypass,
        copilot_only_block_possible,
    ) = effective_protection(
        github,
        repo,
        base_ref,
        admin_bypass,
        # Any exact-head authorization may safely coexist with the one
        # configured admin bypass actor; unknown bypass shapes still block.
        authorization_source
        in {"review", "copilot", "comment", "hotfix-emergency"},
        copilot_mode and level_decision.review == "self" and not admin_bypass,
        verification_mode == "local",
    )
    authorization_actor = str((auth.get("user") or {}).get("login", ""))
    mergeable_state = pull.get("mergeable_state")
    if reviewed_bypass and mergeable_state != "clean":
        reviewed_policy_block = mergeable_state == "blocked" and (
            verification_mode == "local"
            or (
                admin_bypass
                and authorization_source == "comment"
                and copilot_mode
                and copilot_only_block_possible
            )
        )
        if reviewed_policy_block:
            permission = github.get(
                repo,
                "collaborators/"
                f"{urllib.parse.quote(actor, safe='')}/permission",
            )
            permission_user = (
                permission.get("user") if isinstance(permission, dict) else None
            )
            if (
                not isinstance(permission, dict)
                or permission.get("permission") != "admin"
                or not isinstance(permission_user, dict)
                or str(permission_user.get("login", "")).casefold() != actor
            ):
                protection = "blocked"
                reason = "The merge actor is not the live admin bypass actor"
            elif review_gate.unresolved_threads(repo, pr_number):
                protection = "blocked"
                reason = "Unresolved review threads prevent admin bypass"
            else:
                reason = (
                    "exact-head authorization, verification, and review "
                    "threads are revalidated before the audited bypass"
                )
        else:
            protection = "blocked"
            reason = "GitHub does not report the reviewed pull request as clean"
    quota_run_urls = (
        require_routine_quota_fallback(
            github, lease, pull, auth, quota_fallback_note_url
        )
        if quota_fallback_note_url
        else set()
    )
    check_evidence = "not-enforced"
    local_evidence: dict[str, Any] | None = None
    if verification_mode == "local":
        if quota_run_urls:
            raise RuntimeError("Local verification cannot use quota fallback")
        local_evidence = local_verification.require(
            head_sha=str(head_sha),
            tree_sha=str(lease["head_tree"]),
            base_ref=str(lease["base_ref"]),
            base_sha=str(lease["base_sha"]),
            required_tier=level_decision.suite,
        )
        check_evidence = "local-self-attested"
    elif protection == "enforced" or quota_run_urls:
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
        "head_ref": (pull.get("head") or {}).get("ref"),
        "base_ref": lease["base_ref"],
        "base_sha": lease["base_sha"],
        "title": title,
        "authorization_url": authorization_url,
        "authorization_created_at": auth["created_at"],
        "authorization_actor": authorization_actor,
        "authorization_source": authorization_source,
        "release_level": level_decision.level,
        "required_review": level_decision.review,
        "bypass_route": bypass_route,
        "reviewed_bypass": reviewed_bypass,
        "protection": protection,
        "merge_mode": "agent" if protection == "enforced" else "human-only",
        "protection_reason": reason,
        "required_check_evidence": check_evidence,
        "local_verification": local_evidence,
        "admin_bypass": admin_bypass,
        "dependabot_head": dependabot_head,
        "hotfix_evidence": hotfix_evidence,
    }


def review_settings() -> tuple[str, str]:
    """Return this checkout's normalized Copilot review settings."""
    return review_gate.review_settings(
        Path(__file__).resolve().parents[1] / ".csarc/config.yml"
    )


def resolve_release_level(
    github: GitHub, repo: str, pull: dict[str, Any]
) -> release_level.Decision:
    """Resolve the live pull request's review requirement."""
    config = Path(__file__).resolve().parents[1] / ".csarc/config.yml"
    return release_level.resolve_pull(
        github, repo, pull, release_level.load_settings(config)
    )


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


def create_draft_pull(  # noqa: C901
    args: argparse.Namespace, github: GitHub
) -> None:
    """Create one clean, pushed pull request directly in Draft state."""
    if REPOSITORY.fullmatch(args.repo) is None:
        raise RuntimeError("Repository identity is invalid")
    if not args.title.strip() or "\n" in args.title:
        raise RuntimeError("Pull request title must be one non-empty line")
    body = read_body_file(args.body_file)
    if body is None or not body.strip():
        raise RuntimeError("Pull request body must not be empty")
    require_origin(args.repo)
    for branch in (args.base, args.head):
        run(["git", "check-ref-format", "--branch", branch])
    current_branch = run(["git", "branch", "--show-current"])
    if current_branch != args.head:
        raise RuntimeError("Current branch does not match --head")
    if run(["git", "status", "--porcelain"]):
        raise RuntimeError("Pull request creation requires a clean worktree")
    head_sha = run(["git", "rev-parse", "HEAD"])
    if SHA.fullmatch(head_sha) is None:
        raise RuntimeError("Current head commit is invalid")
    if branch_sha(github, args.repo, args.head) != head_sha:
        raise RuntimeError("Remote pull request branch is not at current HEAD")
    branch_sha(github, args.repo, args.base)
    output = run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            args.repo,
            "--base",
            args.base,
            "--head",
            args.head,
            "--title",
            args.title,
            "--body-file",
            "-",
            "--draft",
        ],
        input_text=body,
    )
    url = output.splitlines()[-1].strip() if output else ""
    match = re.fullmatch(
        rf"https://github\.com/{re.escape(args.repo)}/pull/([1-9][0-9]*)",
        url,
    )
    if match is None:
        raise RuntimeError("GitHub did not return a pull request URL")
    pull = github.get(args.repo, f"pulls/{int(match.group(1))}")
    head = pull.get("head") if isinstance(pull, dict) else None
    base = pull.get("base") if isinstance(pull, dict) else None
    actual_body = str(pull.get("body") or "") if isinstance(pull, dict) else ""
    if (
        not isinstance(pull, dict)
        or pull.get("state") != "open"
        or pull.get("draft") is not True
        or pull.get("title") != args.title
        or actual_body.replace("\r\n", "\n").rstrip("\n")
        != body.replace("\r\n", "\n").rstrip("\n")
        or not isinstance(head, dict)
        or head.get("ref") != args.head
        or head.get("sha") != head_sha
        or not isinstance(base, dict)
        or base.get("ref") != args.base
    ):
        raise RuntimeError("Created pull request did not match requested Draft")
    sys.stdout.write(url + "\n")


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
        getattr(args, "require_dependabot_head", False),
    )
    sys.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")


def revalidate_release_candidate(
    github: GitHub,
    lease: dict[str, Any],
    head_ref: str,
    release_phase_name: str,
) -> str:
    """Refresh the candidate status against the lease-bound current base."""
    release_candidate = RELEASE_BRANCH.fullmatch(
        head_ref
    ) or head_ref.startswith("release-please--branches--main--components--")
    promotion = PROMOTION_BRANCH.fullmatch(head_ref)
    root = Path(__file__).resolve().parents[1]
    config = csarc_config.load_config(root / ".csarc/config.yml")
    if config.get("release_ownership") != "csarc-owned":
        return ""
    repo = str(lease["repository"])
    pr_number = int(lease["pull_request"])
    head_sha = str(lease["head_sha"])
    require_lease(github, lease, repo, pr_number, head_sha)
    if head_ref.startswith("sync/main-to-"):
        pull = live_pull(github, repo, pr_number, head_sha)
        if require_routine_route(github, repo, lease, pull) != "sync":
            raise RuntimeError("Release bypass requires a formal sync route")
        return ""
    if promotion is not None:
        source_sha = run(["git", "-C", str(root), "rev-parse", f"{head_sha}^1"])
        return run(
            [
                sys.executable,
                str(root / "scripts" / "release_policy.py"),
                "verify-promotion-version",
                "--root",
                str(root),
                "--source-sha",
                source_sha,
                "--head-sha",
                head_sha,
                "--phase",
                release_phase_name,
            ]
        )
    if not release_candidate:
        pull = live_pull(github, repo, pr_number, head_sha)
        role = release_level.checkpoint_role(github, repo, pull)
        return run(
            [
                sys.executable,
                str(root / "scripts" / "release_policy.py"),
                "verify-delivery-version",
                "--root",
                str(root),
                "--base-sha",
                str(lease["base_sha"]),
                "--head-sha",
                head_sha,
                "--phase",
                release_phase_name,
                "--checkpoint-role",
                role,
            ]
        )
    with tempfile.TemporaryDirectory(
        prefix="csarc-release-candidate-"
    ) as directory:
        candidate = Path(directory) / "pull-request.json"
        candidate.write_text(
            json.dumps(
                {
                    "number": pr_number,
                    "sha": head_sha,
                    "headBranchName": head_ref,
                    "baseBranchName": lease["base_ref"],
                    "baseSha": lease["base_sha"],
                }
            ),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.update(
            {
                "GITHUB_REPOSITORY": repo,
                "GITHUB_SERVER_URL": "https://github.com",
                "GITHUB_RUN_ID": "pr-lifecycle",
                "RUNNER_TEMP": directory,
                "STATUS_URL": f"https://github.com/{repo}/pull/{pr_number}",
            }
        )
        return run(
            [
                str(root / "scripts" / "verify-release-candidate"),
                str(candidate),
            ],
            env=env,
        )


def merge(args: argparse.Namespace, github: GitHub) -> None:
    """Merge only when the lease and exact-head controls are enforced."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, getattr(args, "actor", ""), github)
    snapshot = merge_snapshot(
        github,
        lease,
        args.authorization_url,
        getattr(args, "actor", ""),
        getattr(args, "quota_fallback_note_url", ""),
        getattr(args, "require_dependabot_head", False),
    )
    if snapshot["merge_mode"] != "agent":
        raise RuntimeError(
            "Agent merge is blocked: server-side protection is unavailable or "
            "incomplete; a human maintainer must merge manually"
        )
    if snapshot.get("reviewed_bypass") is True:
        reason = (
            "exact-head-copilot-review"
            if snapshot.get("authorization_source") == "copilot"
            else "emergency-hotfix"
            if snapshot.get("authorization_source") == "hotfix-emergency"
            else "exact-head-review"
        )
        github.comment(
            args.repo,
            args.pr_number,
            "bypass-trace: "
            f"release_level={snapshot['release_level']} "
            f"route={snapshot['bypass_route']} "
            f"actor={lease['actor']} reason={reason}",
        )
    if snapshot.get("authorization_source") == "copilot":
        github.comment(
            args.repo,
            args.pr_number,
            "copilot-review-trace: "
            f"review={snapshot['authorization_url']} "
            f"head={lease['head_sha']} actor={lease['actor']}",
        )
    local_evidence = snapshot.get("local_verification")
    if isinstance(local_evidence, dict):
        github.comment(
            args.repo,
            args.pr_number,
            "local-verification-trace: "
            f"head={lease['head_sha']} tree={local_evidence['tree_sha']} "
            f"base={lease['base_sha']} tier={local_evidence['tier']} "
            f"scopes={','.join(local_evidence['scopes'])} "
            "trust=self-attested-local; this is not trusted hosted evidence",
        )
    candidate_evidence = revalidate_release_candidate(
        github,
        lease,
        str(snapshot.get("head_ref") or ""),
        str(snapshot.get("release_level") or ""),
    )
    if candidate_evidence:
        sys.stdout.write(candidate_evidence.rstrip() + "\n")
    snapshot = merge_snapshot(
        github,
        lease,
        args.authorization_url,
        getattr(args, "actor", ""),
        getattr(args, "quota_fallback_note_url", ""),
        getattr(args, "require_dependabot_head", False),
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
    hotfix_evidence = snapshot.get("hotfix_evidence")
    if isinstance(hotfix_evidence, dict):
        follow_up_url = ensure_hotfix_post_review(
            github,
            args.repo,
            args.pr_number,
            args.head_sha,
            str(snapshot["release_level"]),
            str(snapshot["authorization_url"]),
            hotfix_evidence,
        )
        github.comment(
            args.repo,
            args.pr_number,
            f"hotfix-post-review: {follow_up_url}",
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


def issue_body_arguments(body_file: Path | None) -> list[str]:
    """Validate and return the optional GitHub CLI body arguments."""
    if body_file is None:
        return []
    if not body_file.is_file():
        raise RuntimeError("Issue body file does not exist")
    return ["--body-file", str(body_file)]


def edit_standalone_issue(args: argparse.Namespace, github: GitHub) -> None:
    """Edit an Issue only after proving the target is not a pull request."""
    values = [
        *args.add_label,
        *args.remove_label,
        *args.add_assignee,
        *([args.issue_type] if args.issue_type else []),
    ]
    if REPOSITORY.fullmatch(args.repo) is None or args.issue_number < 1:
        raise RuntimeError("Issue identity is invalid")
    if (not values and not args.remove_type and args.body_file is None) or any(
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
    command.extend(issue_body_arguments(args.body_file))
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
    # A `\`` escaped backtick is a literal character inside a double-quoted
    # bash string, never command substitution, so text between a pair of
    # them is documentation (e.g. a human-facing message describing a
    # command to run), not something this file executes. Drop those spans,
    # and whole-line `#` comments for the same reason, before matching so
    # described commands cannot combine with unrelated text into a false
    # write (#643).
    shell = re.sub(r"\\`.*?\\`", "", shell, flags=re.DOTALL)
    lines = [
        "" if line.lstrip().startswith("#") else line
        for line in shell.splitlines()
    ]
    blocks = [*lines, "\n".join(lines)]
    for block in blocks:
        compact = compact_tokens(block)
        if any(
            f"ghpr{operation}" in compact
            for operation in ("ready", "edit", "merge")
        ):
            violations.append("direct gh pr lifecycle command")
        if "ghprcreate" in compact:
            violations.append("direct gh pr creation")
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


def _trusted_exact_path(
    root: Path, path: Path, trusted: frozenset[str]
) -> bool:
    """Trust only exact in-root paths from `trusted`, rejecting symlinks."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if relative.as_posix() not in trusted:
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


def canonical_scanner_helper(root: Path, path: Path) -> bool:
    """Trust only exact in-root helper paths without symlink components."""
    return _trusted_exact_path(
        root,
        path,
        frozenset(
            {
                "scripts/pr_lifecycle.py",
                "template/.csarc/scripts/pr_lifecycle.py",
            }
        ),
    )


def dependabot_auto_merge_exemption(root: Path, path: Path) -> bool:
    """Trust the two exact dependabot-auto-merge.yml paths (see #602).

    The only unleased write left in this workflow is the major-update
    `needs-manual-review` label/comment. It never authorizes or performs a
    merge; minor and patch updates use the separate exact-head workflow and
    `pr_lifecycle.py` lease. Keeping this narrow exemption avoids taking the
    shared main-lane lease for a non-merge classification notice.

    This is a positive list, not a pattern relaxation: only these two exact
    paths are trusted. A different file reusing the same unleased
    `gh pr edit --add-label` command text is still caught by scan_writers.

    Every scanner exemption must have its own tracking Issue (#602 is this
    one's), and all exemptions are re-reviewed once the project leaves
    beta — see docs/ci-policy.md's "PR lifecycle single-writer" section.
    """
    return _trusted_exact_path(
        root,
        path,
        frozenset(
            {
                ".github/workflows/dependabot-auto-merge.yml",
                "template/.github/workflows/dependabot-auto-merge.yml",
            }
        ),
    )


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
            or dependabot_auto_merge_exemption(root, path)
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
    acquire_command.add_argument(
        "--renew",
        type=Path,
        help="still-live lease evidence to renew for the same head and owner",
    )
    acquire_command.set_defaults(handler=acquire)
    scan_command = commands.add_parser("scan-writers")
    scan_command.add_argument("--root", type=Path, default=Path.cwd())
    scan_command.set_defaults(scan_root=True)
    create_command = commands.add_parser("create")
    create_command.add_argument("--repo", required=True)
    create_command.add_argument("--base", required=True)
    create_command.add_argument("--head", required=True)
    create_command.add_argument("--title", required=True)
    create_command.add_argument("--body-file", type=Path, required=True)
    create_command.set_defaults(handler=create_draft_pull)
    issue_edit = commands.add_parser("issue-edit")
    issue_edit.add_argument("--repo", required=True)
    issue_edit.add_argument("--issue-number", required=True, type=int)
    issue_edit.add_argument("--add-label", action="append", default=[])
    issue_edit.add_argument("--remove-label", action="append", default=[])
    issue_edit.add_argument("--add-assignee", action="append", default=[])
    issue_edit.add_argument("--body-file", type=Path)
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
            command.add_argument("--authorization-url", default="")
            command.add_argument("--quota-fallback-note-url", default="")
            command.add_argument(
                "--require-dependabot-head", action="store_true"
            )
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
