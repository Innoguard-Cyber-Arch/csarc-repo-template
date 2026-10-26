#!/usr/bin/env python3
"""Serialize pull-request lifecycle writes across local tasks."""

from __future__ import annotations

import argparse
import ast
import base64
import contextlib
import hashlib
import importlib
import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    csarc_config = importlib.import_module("csarc_config")
else:
    csarc_config = importlib.import_module(f"{__package__}.csarc_config")


def _load_sibling(name: str) -> ModuleType:
    """Load one script module that sits beside this file."""
    path = Path(__file__).resolve().with_name(f"{name}.py")
    cached = sys.modules.get(name)
    cached_file = getattr(cached, "__file__", None)
    if (
        cached is not None
        and cached_file
        and Path(cached_file).resolve() == path
    ):
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(
            f"Sibling module {path}: unavailable. Run 'csarc update'."
        )
    module = importlib.util.module_from_spec(spec)
    # Register a first load so nested imports share it; a same-named module
    # from another directory keeps its registration.
    if cached is None:
        sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(name) is module:
            del sys.modules[name]
        raise
    return module


class SiblingModule:
    """Import one sibling script module only when a command first uses it."""

    def __init__(self, name: str) -> None:
        """Remember the sibling module name without importing it."""
        object.__setattr__(self, "_sibling_name", name)
        object.__setattr__(self, "_sibling_module", None)

    def _sibling(self) -> ModuleType:
        module = object.__getattribute__(self, "_sibling_module")
        if module is None:
            name = object.__getattribute__(self, "_sibling_name")
            if __package__ in {None, ""}:
                module = _load_sibling(name)
            else:
                module = importlib.import_module(f"{__package__}.{name}")
            object.__setattr__(self, "_sibling_module", module)
        return module

    def __getattr__(self, attribute: str) -> object:
        """Load the sibling on first use and read one attribute."""
        return getattr(self._sibling(), attribute)

    def __setattr__(self, attribute: str, value: object) -> None:
        """Write one attribute on the loaded sibling module."""
        setattr(self._sibling(), attribute, value)

    def __delattr__(self, attribute: str) -> None:
        """Delete one attribute from the loaded sibling module."""
        delattr(self._sibling(), attribute)


# Only the configuration reader is eager; every other sibling loads when the
# selected command first needs it.
ci_tier: Any = SiblingModule("ci_tier")
dependabot_auth: Any = SiblingModule("authenticate_dependabot_head")
evidence_freshness: Any = SiblingModule("evidence_freshness")
local_verification: Any = SiblingModule("local_verification")
merge_trace: Any = SiblingModule("merge_trace")
promotion_gate: Any = SiblingModule("promotion_gate")
release_level: Any = SiblingModule("release_level")
review_gate: Any = SiblingModule("review_gate")
risk_controls: Any = SiblingModule("risk_controls")
self_hosted_evidence: Any = SiblingModule("self_hosted_evidence")
verification_evidence: Any = SiblingModule("verification_evidence")


def require_milestones() -> None:
    """Fail when the render omits the Milestone scripts (#1208)."""
    try:
        promotion_gate.route_for  # noqa: B018 - loads the sibling
    except (FileNotFoundError, ModuleNotFoundError) as error:
        raise RuntimeError(
            "Milestone route: needs 'lifecycle: milestones'. Set it."
        ) from error


def main_route_kind(base_ref: str, head_ref: str, labels: set[str]) -> str:
    """Classify a route; without Milestones, keep the other recorded kinds."""
    try:
        require_milestones()
    except RuntimeError:
        pass
    else:
        return promotion_gate.route_for(base_ref, head_ref, labels).kind
    if base_ref != "main":
        return "not-applicable"
    if head_ref.startswith(("release-please--", "release/v")):
        return "release-follow-up"
    if "release-recovery" in labels:
        if RECOVERY_BRANCH.fullmatch(head_ref) and "hotfix" not in labels:
            return "release-recovery"
        return "invalid-main-route"
    if ISOLATED_BRANCH.fullmatch(head_ref) and "promotion" in labels:
        return "isolated"
    if head_ref.startswith("fix/") and "hotfix" in labels:
        return "hotfix"
    return "not-applicable"


# Hosted-only code; local renders omit it (#1177).
hosted_checks: Any = SiblingModule("pr_lifecycle_hosted")


def _hosted_globals(name: str) -> dict[str, Any]:
    """Return the hosted sibling namespace, sharing these globals."""
    try:
        shared = vars(hosted_checks._sibling())
    except (FileNotFoundError, ModuleNotFoundError) as error:
        raise RuntimeError(
            f"{name}: needs verification_mode: hosted. Set it."
        ) from error
    for key, value in globals().items():
        shared.setdefault(key, value)
    return shared


def _hosted_only(name: str) -> Callable[..., object]:
    """Forward one call to the hosted sibling."""

    def forward(*args: object, **kwargs: object) -> object:
        return _hosted_globals(name)[name](*args, **kwargs)

    return forward


def __getattr__(name: str) -> object:
    """Read one hosted-only name."""
    try:
        return _hosted_globals(name)[name]
    except (KeyError, RuntimeError) as error:
        raise AttributeError(name) from error


declared_required_contexts = _hosted_only("declared_required_contexts")
require_successful_checks = _hosted_only("require_successful_checks")
require_trusted_dependabot_head = _hosted_only(
    "require_trusted_dependabot_head"
)
close_work_issue = _hosted_only("close_work_issue")


# Shared next steps of raised messages (#1253).
GH_RETRY = "Run 'gh auth status' and rerun"
LS_LEASES = "Run 'git ls-remote origin csarc/leases'"
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
ISOLATED_BRANCH = re.compile(r"^dev/i([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$")
RECOVERY_BRANCH = re.compile(r"^fix/([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$")
RELEASE_BRANCH = re.compile(
    r"^release/v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-beta\.[1-9]\d*)?$"
)
ISSUE_WORK_BRANCH = re.compile(
    r"^(?:build|chore|ci|docs|feat|fix|refactor|revert|test)/"
    r"([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$"
)
ADMIN_BYPASS_MARKER = "Admin bypass / 管理員略過審核"
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
MAINTAINER_PERMISSIONS = {"admin", "maintain"}
REVIEWED_MERGE_BYPASS_ACTORS = [
    {
        "actor_type": "RepositoryRole",
        "actor_id": 5,
        "bypass_mode": "pull_request",
    }
]
# Issue #1076 (#1058 decisions 10 and 27): without a Ruleset the platform
# enforces nothing, so lifecycle may merge only when a complete readback
# observes exactly one writer. Unrecognized roles are never guessed.
WRITE_ROLES = frozenset({"write", "maintain", "admin"})
NON_WRITE_ROLES = frozenset({"read", "triage"})
WRITE_TEAM_PERMISSIONS = frozenset({"push", "maintain", "admin"})
NON_WRITE_TEAM_PERMISSIONS = frozenset({"pull", "triage"})
# Each protection state maps to exactly one merge route: `allowed` lets
# lifecycle merge, `manual-only` leaves a human merge recorded as untraced,
# and `blocked` has no route until the condition is fixed.
MERGE_ROUTES = {
    "enforced": "allowed",
    "single-writer": "allowed",
    "independent-approval": "allowed",
    "inconclusive": "manual-only",
    "multiple-writers": "manual-only",
    "unknown": "manual-only",
    "blocked": "blocked",
}
AGENT_PROTECTIONS = frozenset(
    state for state, route in MERGE_ROUTES.items() if route == "allowed"
)
DEPENDABOT_UPDATE_TYPE = re.compile(r"(?m)^\s*update-type:\s*(\S+)\s*$")
LOCAL_DEPENDABOT_UPDATE_TYPES = frozenset(
    {"version-update:semver-minor", "version-update:semver-patch"}
)
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
        raise RuntimeError(f"{label}: no timestamp. {GH_RETRY}.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError(
            f"{label}: invalid timestamp. {GH_RETRY}."
        ) from error
    if parsed.tzinfo is None:
        raise RuntimeError(f"{label}: timestamp has no timezone. {GH_RETRY}.")
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
        raise RuntimeError(
            f"Command failed: {' '.join(command)}: {detail}. Fix it and retry."
        )
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
                raise RuntimeError(
                    "GitHub actor: invalid --actor. Pass a GitHub login."
                )
            return explicit_actor
        try:
            payload = json.loads(run(["gh", "api", "user"]))
            login = payload.get("login") if isinstance(payload, dict) else None
            if isinstance(login, str) and login:
                return login
        except RuntimeError as error:
            raise RuntimeError(
                "GitHub actor: unavailable. GitHub App callers pass --actor "
                "from trusted action output."
            ) from error
        raise RuntimeError("GitHub actor: unavailable. Run 'gh auth login'.")

    def pages(self, repo: str, path: str) -> list[dict[str, Any]]:
        """Read and flatten every page of a REST collection."""
        return self.api_pages(f"repos/{repo}/{path}")

    def _slurp(self, endpoint: str) -> object:
        """Read every page of one REST endpoint as one JSON list."""
        return json.loads(
            run(
                [
                    "gh",
                    "api",
                    "--paginate",
                    "--slurp",
                    "-H",
                    "Accept: application/vnd.github+json",
                    endpoint,
                ]
            )
        )

    def _send(
        self,
        method: str,
        endpoint: str,
        body: dict[str, object],
        label: str,
        next_step: str = GH_RETRY,
    ) -> dict[str, Any]:
        """Send one JSON write and require an object response."""
        result = json.loads(
            run(
                ["gh", "api", "--method", method, endpoint, "--input", "-"],
                input_text=json.dumps(body),
            )
        )
        if not isinstance(result, dict):
            raise RuntimeError(f"{label}: invalid response. {next_step}.")
        return result

    def api_pages(self, endpoint: str) -> list[dict[str, Any]]:
        """Read and flatten every page of any REST collection endpoint."""
        payload = self._slurp(endpoint)
        if not isinstance(payload, list):
            raise RuntimeError(
                f"GitHub collection {endpoint}: not a list. {GH_RETRY}."
            )
        pages = (
            payload if payload and isinstance(payload[0], list) else [payload]
        )
        items = [item for page in pages for item in page]
        if not all(isinstance(item, dict) for item in items):
            raise RuntimeError(
                f"GitHub collection {endpoint}: invalid entries. {GH_RETRY}."
            )
        return items

    def collection(
        self,
        repo: str,
        path: str,
        key: str,
        response_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read one keyed collection across every REST response page."""
        payload = self._slurp(f"repos/{repo}/{path}")
        if not isinstance(payload, list):
            raise RuntimeError(
                f"GitHub collection {path}: not paginated. {GH_RETRY}."
            )
        items: list[dict[str, Any]] = []
        for page in payload:
            if not isinstance(page, dict) or not isinstance(
                page.get(key), list
            ):
                raise RuntimeError(
                    f"GitHub collection {path}: no {key}. {GH_RETRY}."
                )
            if response_sha is not None and page.get("sha") != response_sha:
                raise RuntimeError(
                    f"GitHub collection {path}: another SHA. {GH_RETRY}."
                )
            entries = page[key]
            if not all(isinstance(item, dict) for item in entries):
                raise RuntimeError(
                    f"GitHub collection {path}: invalid entries. {GH_RETRY}."
                )
            items.extend(entries)
        return items

    def merge(
        self,
        repo: str,
        pr_number: int,
        head_sha: str,
        title: str,
        message: str,
    ) -> dict[str, Any]:
        """Synchronously merge one exact PR head through the REST API."""
        return self._send(
            "PUT",
            f"repos/{repo}/pulls/{pr_number}/merge",
            {
                "sha": head_sha,
                "merge_method": "squash",
                "commit_title": title,
                "commit_message": message,
            },
            "GitHub merge",
            "Check the PR state on GitHub",
        )

    def comment(self, repo: str, pr_number: int, body: str) -> dict[str, Any]:
        """Create one audit comment."""
        return self._send(
            "POST",
            f"repos/{repo}/issues/{pr_number}/comments",
            {"body": body},
            "GitHub comment",
        )

    def edit_comment(
        self, repo: str, comment_id: int, body: str
    ) -> dict[str, Any]:
        """Replace the body of the lifecycle's one evidence summary."""
        return self._send(
            "PATCH",
            f"repos/{repo}/issues/comments/{comment_id}",
            {"body": body},
            "GitHub comment",
        )

    def create_issue(
        self,
        repo: str,
        title: str,
        body: str,
        assignee: str,
    ) -> dict[str, Any]:
        """Create one post-review task; a render has no gh-issue-create."""
        wrapper = Path(__file__).with_name("gh-issue-create")
        command = [
            *(
                [str(wrapper)]
                if wrapper.is_file()
                else ["gh", "issue", "create"]
            ),
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
            raise RuntimeError(
                f"Hotfix post-review Issue: invalid URL. {GH_RETRY}."
            )
        return {"html_url": url}

    def close_issue(self, repo: str, issue_number: int) -> dict[str, Any]:
        """Close one validated work Issue as completed."""
        return self._send(
            "PATCH",
            f"repos/{repo}/issues/{issue_number}",
            {"state": "closed", "state_reason": "completed"},
            "GitHub Issue close",
        )


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
    raise RuntimeError(
        "origin: not the requested github.com repository. Fix the remote."
    )


def require_origin(repo: str) -> None:
    """Require local origin to be the requested GitHub repository."""
    origin = remote_repository(run(["git", "remote", "get-url", "origin"]))
    if origin.casefold() != repo.casefold():
        raise RuntimeError(
            "origin: not the requested repository. Fix the remote."
        )


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
        raise RuntimeError(
            f"Pull request: base branch unavailable. {GH_RETRY}."
        )
    return [pr_ref(int(pull["number"])), base_lane_ref(base_ref)]


def live_pull(
    github: GitHub, repo: str, pr_number: int, head_sha: str
) -> dict[str, Any]:
    """Require one open pull request at the exact expected head."""
    payload = github.get(repo, f"pulls/{pr_number}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Live pull request: invalid response. {GH_RETRY}.")
    head = payload.get("head") or {}
    if (
        payload.get("number") != pr_number
        or payload.get("state") != "open"
        or payload.get("merged") is not False
        or head.get("sha") != head_sha
    ):
        raise RuntimeError(
            "Live pull request: state or head drifted. Recheck it."
        )
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
        raise RuntimeError(f"Destination branch: ref unavailable. {GH_RETRY}.")
    return sha


def remote_ref(ref: str) -> str | None:
    """Return the exact origin ref SHA, rejecting ambiguous output."""
    output = run(["git", "ls-remote", "--refs", "origin", ref])
    if not output:
        return None
    lines = output.splitlines()
    if len(lines) != 1:
        raise RuntimeError(f"Remote lease ref {ref}: ambiguous. {LS_LEASES}.")
    try:
        sha, observed_ref = lines[0].split("\t", 1)
    except ValueError as error:
        raise RuntimeError(
            f"Remote lease ref {ref}: invalid. {LS_LEASES}."
        ) from error
    if observed_ref != ref or SHA.fullmatch(sha) is None:
        raise RuntimeError(f"Remote lease ref {ref}: invalid. {LS_LEASES}.")
    return sha


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Atomically write evidence without following an output symlink."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise RuntimeError(f"Output {path}: not a regular file. Fix the path.")
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
        raise RuntimeError("Lease evidence: not a regular file. Fix the path.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != LEASE_SCHEMA
    ):
        raise RuntimeError(
            "Lease evidence: invalid schema. Reacquire the lease."
        )
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
        raise RuntimeError("Lease evidence: incomplete. Reacquire the lease.")
    if (
        SHA.fullmatch(payload["head_sha"]) is None
        or SHA.fullmatch(payload["head_tree"]) is None
        or SHA.fullmatch(payload["base_sha"]) is None
        or SHA.fullmatch(payload["lease_commit"]) is None
    ):
        raise RuntimeError("Lease evidence: invalid SHA. Reacquire the lease.")
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
        raise RuntimeError(
            "Lease evidence: invalid identity. Reacquire the lease."
        )
    if set(payload) - {RENEWAL_FIELD} != {
        *LEASE_CORE_FIELDS,
        "capability",
        "lease_commit",
        "audit_url",
    }:
        raise RuntimeError(
            "Lease evidence: unexpected fields. Reacquire the lease."
        )
    if RENEWAL_FIELD in payload and (
        not isinstance(payload[RENEWAL_FIELD], str)
        or SHA.fullmatch(payload[RENEWAL_FIELD]) is None
    ):
        raise RuntimeError(
            "Lease renewal evidence: invalid. Reacquire the lease."
        )
    if (
        hashlib.sha256(payload["capability"].encode()).hexdigest()
        != payload["capability_digest"]
    ):
        raise RuntimeError(
            "Lease capability: remote digest differs. Reacquire the lease."
        )
    if not all(
        isinstance(commit, str) and SHA.fullmatch(commit)
        for commit in payload["reclaimed_commits"]
    ):
        raise RuntimeError(f"Lease reclaim history: invalid. {LS_LEASES}.")
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
        raise RuntimeError(f"Lease refs: invalid. {LS_LEASES}.")


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
        raise RuntimeError(f"Lease audit URL: invalid. {LS_LEASES}.")
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
        raise RuntimeError(f"Remote lease audit comment: invalid. {LS_LEASES}.")


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
        raise RuntimeError("Lease: not for this pull request. Use its lease.")
    validate_refs(lease)
    if parse_time(lease["expires_at"], "Lease") <= datetime.now(
        UTC
    ) + timedelta(seconds=MIN_OPERATION_SECONDS):
        raise RuntimeError("Lease: expired. Inspect it before release.")
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
            "Lease scope: base or destination drifted. Reacquire the lease."
        )
    if branch_sha(github, repo, lease["base_ref"]) != lease["base_sha"]:
        raise RuntimeError("Destination branch: advanced. Update the branch.")


def require_committed_lease(github: GitHub, lease: dict[str, Any]) -> None:
    """Match mutable evidence to its canonical remote commit and refs."""
    capability = str(lease.get("capability", ""))
    digest = hashlib.sha256(capability.encode()).hexdigest()
    if not secrets.compare_digest(digest, str(lease["capability_digest"])):
        raise RuntimeError("Lease capability: invalid. Reacquire the lease.")
    refs = lease["refs"]
    for ref in refs:
        if remote_ref(ref) != lease["lease_commit"]:
            raise RuntimeError(
                f"Lease ownership {ref}: changed or missing. {LS_LEASES}."
            )
    repo = lease["repository"]
    head_sha = lease["head_sha"]
    lease_commit = github.get(repo, f"git/commits/{lease['lease_commit']}")
    head_commit = github.get(repo, f"git/commits/{head_sha}")
    if not isinstance(lease_commit, dict) or not isinstance(head_commit, dict):
        raise RuntimeError(
            f"Remote lease commit: metadata unavailable. {GH_RETRY}."
        )
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
        raise RuntimeError(f"Remote lease commit: not canonical. {LS_LEASES}.")
    comment_id = audit_comment_id(lease)
    comment = github.get(repo, f"issues/comments/{comment_id}")
    validate_audit_comment(lease, comment)


def caller_lease(args: argparse.Namespace, github: GitHub) -> dict[str, Any]:
    """Read the lease evidence and require the caller that acquired it."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, getattr(args, "actor", ""), github)
    return lease


def require_caller(
    lease: dict[str, Any], owner: str, actor: str, github: GitHub
) -> None:
    """Require the task owner and actor that acquired the lease."""
    if lease["owner"] != owner:
        raise RuntimeError(
            "Lifecycle lease: held by another owner. Use your lease."
        )
    if str(lease["actor"]).casefold() != github.viewer(actor).casefold():
        raise RuntimeError(
            "GitHub actor: changed after the lease. Reacquire the lease."
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
        raise RuntimeError(
            "Lease: expired before the merge. Reacquire the lease."
        )
    commit = lease["lease_commit"]
    create_refs(commit, lease["refs"], dict.fromkeys(lease["refs"], commit))


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
    github: GitHub, repo: str, commit_sha: str, held_ref: str, owner: str = ""
) -> dict[str, Any]:
    """Validate one canonical expired lease before an atomic reclaim."""
    core = canonical_remote_lease(github, repo, commit_sha, held_ref)
    left = parse_time(core["expires_at"], "Existing lease") - datetime.now(UTC)
    if left.total_seconds() > 0:
        raise RuntimeError(
            f"PR lifecycle lease: owner '{owner}' holds it for "
            f"{int(left.total_seconds())} more seconds. If you lost its "
            f"evidence file, run 'pr_lifecycle.py recover --repo {repo} "
            f"--pr-number {core['pull_request']} --head-sha "
            f"{core['head_sha']} --owner {owner}'."
            if core["owner"] == owner
            else "PR lifecycle lease: held by another owner. Wait for its "
            "release."
        )
    return core


def recover(args: argparse.Namespace, github: GitHub) -> None:
    """Release this caller's live lease after its evidence file is lost."""
    require_origin(args.repo)
    ref = pr_ref(args.pr_number)
    commit = remote_ref(ref)
    if commit is None:
        raise RuntimeError("Lease: none for this pull request. Acquire one.")
    lease = {
        **canonical_remote_lease(github, args.repo, commit, ref),
        "lease_commit": commit,
    }
    live_pull(github, args.repo, args.pr_number, args.head_sha)
    if (
        lease["owner"] != args.owner
        or lease["actor"].casefold() != github.viewer(args.actor).casefold()
        or lease["head_sha"] != args.head_sha
    ):
        raise RuntimeError(
            "Lease: owner, actor, or head differs. Wait for its release."
        )
    sys.stdout.write(
        f"NOTICE: Lease {commit} of '{args.owner}' expires "
        f"{lease['expires_at']}. Recovery deletes "
        f"{' and '.join(lease['refs'])}.\n"
    )
    if not args.apply:
        sys.stdout.write("NOTICE: Dry run only. Rerun with '--apply'.\n")
        return
    release_refs(lease)
    sys.stdout.write("OK: Lease released. Acquire a new lease.\n")


def canonical_remote_lease(
    github: GitHub, repo: str, commit_sha: str, held_ref: str
) -> dict[str, Any]:
    """Validate one remote lease commit's canonical message, parent, tree."""
    payload = github.get(repo, f"git/commits/{commit_sha}")
    if not isinstance(payload, dict) or payload.get("sha") != commit_sha:
        raise RuntimeError(f"Existing lease commit: unavailable. {GH_RETRY}.")
    message = payload.get("message")
    try:
        if not isinstance(message, str) or "\n\n" not in message:
            raise ValueError
        core = json.loads(message.split("\n\n", 1)[1])
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
            or message != lease_message(core)
        ):
            raise ValueError
        validate_refs(core)
        acquired_at = parse_time(core.get("acquired_at"), "Existing lease")
        expires_at = parse_time(core.get("expires_at"), "Existing lease")
        ttl = (expires_at - acquired_at).total_seconds()
        if not 60 <= ttl <= MAX_TTL_SECONDS:
            raise ValueError
    except (KeyError, RuntimeError, ValueError) as error:
        raise RuntimeError(
            f"Existing lease commit: not canonical. {LS_LEASES}."
        ) from error
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
        raise RuntimeError(
            f"Existing lease commit: invalid parent or tree. {LS_LEASES}."
        )
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
    """Return the earliest time an exact-head authorization may carry."""
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
                "Lease renewal chain: identity changed. Acquire a fresh lease."
            )
        renewed_at = parse_time(current["acquired_at"], "Lease")
        started_at = parse_time(predecessor["acquired_at"], "Renewed lease")
        ended_at = parse_time(predecessor["expires_at"], "Renewed lease")
        if not started_at < renewed_at <= ended_at:
            raise RuntimeError(
                "Lease renewal chain: not contiguous. Renew a still-live lease."
            )
        anchor = started_at
        current = predecessor
    raise RuntimeError("Lease renewal chain: too long. Acquire a fresh lease.")


def renewable_lease(
    args: argparse.Namespace, github: GitHub
) -> dict[str, Any] | None:
    """Return the still-live lease an explicit `--renew` replaces, if any."""
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
            f"Lease renewal: failed ({error}). Release it, acquire a fresh "
            "lease, and reauthorize the exact head."
        ) from error
    return previous


def acquire(args: argparse.Namespace, github: GitHub) -> None:  # noqa: C901
    """Atomically acquire, or explicitly renew, the PR and lane refs."""
    if SHA.fullmatch(args.head_sha) is None:
        raise RuntimeError(
            "Head SHA: not 40 lowercase hex characters. Pass 'git rev-parse "
            "HEAD'."
        )
    if OWNER.fullmatch(args.owner) is None:
        raise RuntimeError(
            "Owner: not a stable task or human ID. Pass --owner task/<name>."
        )
    if not 60 <= args.ttl_seconds <= MAX_TTL_SECONDS:
        raise RuntimeError(
            f"Lease TTL: out of range. Use 60 to {MAX_TTL_SECONDS} seconds."
        )
    require_origin(args.repo)
    previous = renewable_lease(args, github)
    pull = live_pull(github, args.repo, args.pr_number, args.head_sha)
    repository = github.get(args.repo, "")
    if not isinstance(repository, dict) or not isinstance(
        repository.get("default_branch"), str
    ):
        raise RuntimeError(
            f"Repository: default branch unavailable. {GH_RETRY}."
        )
    refs = lease_refs(pull, repository["default_branch"])
    base = pull.get("base") or {}
    if (
        not isinstance(base.get("ref"), str)
        or SHA.fullmatch(str(base.get("sha", ""))) is None
    ):
        raise RuntimeError(
            f"Pull request: base identity unavailable. {GH_RETRY}."
        )
    if branch_sha(github, args.repo, base["ref"]) != base["sha"]:
        raise RuntimeError(
            "Pull request: base differs from its destination ref. Run 'git "
            "fetch origin'."
        )
    observed = {ref: remote_ref(ref) for ref in refs}
    if previous is not None:
        if refs != previous["refs"] or any(
            existing != previous["lease_commit"]
            for existing in observed.values()
        ):
            raise RuntimeError(
                f"Lease ownership: changed before renewal. {LS_LEASES}."
            )
    else:
        for ref, existing in observed.items():
            if existing is not None:
                expired_remote_lease(
                    github, args.repo, existing, ref, args.owner
                )
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
                "Lease renewal: identity changed. Acquire a fresh lease."
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
        raise RuntimeError(
            "Lease commit: Git created an invalid one. Run 'pr_lifecycle.py "
            "acquire' again."
        )
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
            raise RuntimeError(
                f"Lease audit comment: invalid actor or URL. {LS_LEASES}."
            )
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
            f"WARNING: Earlier authorizations: not checked ({error}). "
            "Check the PR comments by hand.\n"
        )
        return
    if prior is None or parse_time(
        prior.get("created_at"), "Authorization"
    ) >= parse_time(lease["acquired_at"], "Lease"):
        return
    sys.stderr.write(
        "WARNING: Authorization "
        f"{prior.get('html_url') or 'comment'}: predates this fresh lease, "
        "so it is void. Post a new one; next time renew a live lease with "
        "'acquire --renew <lease.json>'.\n"
    )


def live_repository_role(github: GitHub, repo: str, login: str) -> str:
    """Return the live repository `role_name` of one user, or `unknown`."""
    try:
        permission = github.get(
            repo,
            f"collaborators/{urllib.parse.quote(login, safe='')}/permission",
        )
    except RuntimeError:
        return "unknown"
    if not isinstance(permission, dict):
        return "unknown"
    user = permission.get("user")
    role = permission.get("role_name")
    if (
        not isinstance(user, dict)
        or str(user.get("login") or "").casefold() != login.casefold()
        or not isinstance(role, str)
        or not role
    ):
        return "unknown"
    return role


def is_maintainer(github: GitHub, repo: str, login: str) -> bool:
    """Return whether a live `role_name` is `maintain` or `admin`."""
    return live_repository_role(github, repo, login) in MAINTAINER_PERMISSIONS


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
            "Authorization URL: not a comment on this PR. Fix the URL."
        )
    comment_id = parsed.fragment.removeprefix("issuecomment-")
    payload = github.get(repo, f"issues/comments/{comment_id}")
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Authorization comment: invalid response. {GH_RETRY}."
        )
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
        raise RuntimeError(
            "Authorization: not an exact maintainer statement. Run "
            "'pr_lifecycle.py authorization-template'."
        )
    if not is_maintainer(github, repo, user["login"]):
        raise RuntimeError(
            "Authorization actor: no maintainer permission. Ask a maintainer."
        )
    parse_time(payload.get("created_at"), "Authorization")
    return payload


def find_exact_head_authorization(
    github: GitHub,
    repo: str,
    pr_number: int,
    head_sha: str,
    *,
    require_admin: bool = False,
) -> dict[str, Any] | None:
    """Return the newest exact-head maintainer authorization, if one exists."""
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
        role = live_repository_role(github, repo, str(user["login"]))
        if role != "admin" and (
            require_admin or role not in MAINTAINER_PERMISSIONS
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
    """Return a comment body with web-UI line endings and padding removed."""
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
        raise RuntimeError(
            "Emergency self-review: hotfix PRs only. Use normal review."
        )
    issue_numbers = sorted(
        {
            int(value)
            for value in CLOSING_ISSUE.findall(str(pull.get("body") or ""))
        }
    )
    if len(issue_numbers) != 1:
        raise RuntimeError(
            "Emergency hotfix: needs one closing Issue. Fix the PR body."
        )
    issue_number = issue_numbers[0]
    issue = github.get(repo, f"issues/{issue_number}")
    if not isinstance(issue, dict) or issue.get("pull_request") is not None:
        raise RuntimeError(
            "Emergency hotfix work item: not an Issue. Fix the PR body."
        )
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
            "Emergency hotfix: needs one open standalone hotfix Issue. Link it "
            "in the PR body."
        )
    actor = str((authorization_payload.get("user") or {}).get("login") or "")
    proposer = str((issue.get("user") or {}).get("login") or "")
    if not actor or actor.casefold() != proposer.casefold():
        raise RuntimeError(
            "Emergency hotfix authorization: not the Issue proposer. Ask them."
        )
    if live_repository_role(github, repo, actor) != "admin":
        raise RuntimeError(
            "Emergency hotfix authorization: no admin permission. Ask an admin."
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
            "Emergency hotfix Issue: no 'Admin-approve: <reason>'. Add it."
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
        "### 補充\n\n"
        f"{risk_controls.LABEL}\n\n"
        "| ID | 類別 | 等級 | 風險 | 控制 | 預計證據 | Owner |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| R1 | security | high | Hotfix merged before independent review | "
        f"Another maintainer reviews it | PR #{pr_number} | @{actor} |\n\n"
        f"{marker}\n"
    )
    problems: list[str] = []
    risk_controls.parse_risks(body, problems)
    if problems or not risk_controls.parse_acs(body, problems):
        raise RuntimeError(
            "Hotfix post-review: invalid risk block. Edit the Issue's "
            "risk table."
        )
    created = github.create_issue(repo, title, body, actor)
    url = created.get("html_url")
    if not isinstance(url, str):
        raise RuntimeError("Hotfix post-review Issue: not created. Create it.")
    return url


def open_work_issue(
    github: GitHub,
    repo: str,
    pull: dict[str, Any],
    issue_number: int,
    route: str,
) -> dict[str, Any]:
    """Require the PR to close only its open work Issue, and return it."""
    closing_issues = [
        int(value)
        for value in CLOSING_ISSUE.findall(str(pull.get("body") or ""))
    ]
    if closing_issues != [issue_number]:
        raise RuntimeError(f"{route}: does not close its Issue. Fix the body.")
    issue = github.get(repo, f"issues/{issue_number}")
    if (
        not isinstance(issue, dict)
        or type(issue.get("number")) is not int
        or issue["number"] != issue_number
        or issue.get("pull_request") is not None
        or issue.get("state") != "open"
    ):
        raise RuntimeError(f"{route} Issue: not open. Reopen it.")
    return issue


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
        raise RuntimeError(
            "Routine pull request: invalid head. Fix the branch."
        )
    head_ref = head.get("ref")
    head_repo_payload = head.get("repo")
    head_repo = (
        head_repo_payload.get("full_name")
        if isinstance(head_repo_payload, dict)
        else None
    )
    if base_ref == lease["default_branch"]:
        raise RuntimeError(
            "Routine fallback: forbidden on default-branch routes. Use review."
        )
    if (
        not isinstance(base_ref, str)
        or DELIVERY_BRANCH.fullmatch(base_ref) is None
        or not isinstance(head_ref, str)
        or not isinstance(head_repo, str)
        or head_repo.casefold() != repo.casefold()
    ):
        raise RuntimeError(
            "Routine fallback: needs a same-repository delivery route. Push "
            "the branch here."
        )
    work = ISSUE_WORK_BRANCH.fullmatch(head_ref)
    if work:
        issue = open_work_issue(
            github, repo, pull, int(work.group(1)), "Routine work branch"
        )
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
            raise RuntimeError(
                "Routine work branch Issue: invalid Milestone. Set its "
                "Milestone."
            )
        if actual_milestone != expected_milestone:
            raise RuntimeError(
                "Routine work Issue: Milestone differs from the base. Retarget "
                "the PR."
            )
        return "issue"
    main_sha = branch_sha(github, repo, str(lease["default_branch"]))
    require_milestones()
    expected_sync = promotion_gate.delivery_sync.sync_branch_name(
        base_ref, main_sha
    )
    if head_ref != expected_sync:
        raise RuntimeError(
            "Routine fallback: needs a work branch or the current-main "
            "sync branch. Fix the head."
        )
    head_sha = head.get("sha")
    base_sha = (pull.get("base") or {}).get("sha")
    if (
        not isinstance(head_sha, str)
        or SHA.fullmatch(head_sha) is None
        or not isinstance(base_sha, str)
        or SHA.fullmatch(base_sha) is None
    ):
        raise RuntimeError(
            "Routine sync commit: invalid identity. Recreate the sync branch "
            "from main."
        )
    comparison = github.get(
        repo,
        f"compare/{urllib.parse.quote(main_sha, safe='')}..."
        f"{urllib.parse.quote(head_sha, safe='')}",
    )
    compare_status = (
        comparison.get("status") if isinstance(comparison, dict) else None
    )
    if not isinstance(compare_status, str):
        raise RuntimeError(f"Routine sync: invalid comparison. {GH_RETRY}.")
    if not promotion_gate.delivery_sync.includes_main(compare_status):
        raise RuntimeError("Routine sync head: lacks current main. Merge main.")
    commit = github.get(repo, f"git/commits/{head_sha}")
    parents = commit.get("parents") if isinstance(commit, dict) else None
    parent_shas = (
        [item.get("sha") for item in parents if isinstance(item, dict)]
        if isinstance(parents, list)
        else []
    )
    if parent_shas != [base_sha, main_sha]:
        raise RuntimeError(
            "Routine sync head: not main merged into the base. Recreate the "
            "sync branch from main."
        )
    return "sync"


def require_default_branch_issue_route(
    github: GitHub,
    repo: str,
    lease: dict[str, Any],
    pull: dict[str, Any],
) -> None:
    """Require a same-repository, Milestone-less Issue route into default."""
    head = pull.get("head")
    if not isinstance(head, dict):
        raise RuntimeError(
            "Routine pull request: invalid head. Fix the branch."
        )
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
            "Stable route: head is in another repository. Push the branch here."
        )
    work = ISSUE_WORK_BRANCH.fullmatch(str(head_ref)) if head_ref else None
    if work is None:
        raise RuntimeError(
            "Stable route: head is not an Issue work branch. Use "
            "type/<Issue>-<slug>."
        )
    issue = open_work_issue(
        github, repo, pull, int(work.group(1)), "Stable route"
    )
    if issue.get("milestone") is not None:
        raise RuntimeError("Stable route Issue: has a Milestone. Remove it.")


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
        raise RuntimeError(
            "Admin bypass marker: not exactly once. Fix the body."
        )
    base_ref = (pull.get("base") or {}).get("ref")
    if base_ref == lease["default_branch"]:
        head = pull.get("head") or {}
        head_ref = str(head.get("ref") or "")
        labels = {
            str(item.get("name") or "")
            for item in pull.get("labels", [])
            if isinstance(item, dict)
        }
        kind = main_route_kind(str(base_ref), head_ref, labels)
        if RELEASE_BRANCH.fullmatch(head_ref) or kind == "milestone":
            head_repo = head.get("repo") or {}
            head_repo_name = str(head_repo.get("full_name") or "")
            if head_repo_name.casefold() != repo.casefold():
                raise RuntimeError(
                    "Admin bypass: release or promotion head is in another "
                    "repository. Push the branch here."
                )
            return True
        require_default_branch_issue_route(github, repo, lease, pull)
        return True
    route = require_routine_route(github, repo, lease, pull)
    if route not in {"issue", "sync"}:
        raise RuntimeError(
            "Admin bypass: routine Issue or sync routes only. Use review."
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
    actor: str | set[str],
) -> dict[str, Any] | None:
    """Return the newest independent maintainer approval for this head."""
    excluded = {actor} if isinstance(actor, str) else actor
    approved: list[dict[str, Any]] = []
    for login, review in reviews.items():
        user = review.get("user") or {}
        if (
            login in excluded
            or review.get("state") != "APPROVED"
            or review.get("commit_id") != head_sha
            or not isinstance(user, dict)
            or user.get("type") != "User"
            or not is_maintainer(github, repo, str(user["login"]))
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


def effective_protection(
    github: GitHub,
    repo: str,
    branch: str,
    admin_bypass: bool = False,
    reviewed_merge: bool = False,
    copilot_mode: bool = False,
    local_mode: bool = False,
    local_fallback: bool = False,
    dependabot_route: bool = False,
) -> tuple[str, str, set[tuple[str, int]], bool, bool]:
    """Prove review and check enforcement for an exact-head merge."""
    result = _effective_protection(
        github,
        repo,
        branch,
        admin_bypass,
        reviewed_merge,
        copilot_mode,
        local_mode,
        local_fallback,
        dependabot_route,
    )
    if local_mode and result[0] == "unknown":
        return "inconclusive", result[1], set(), False, False
    return result


# Issue #1210: GitHub's exact answer when a private repository on the Free
# plan asks for branch rules; the plan cannot hold a Ruleset at all.
RULES_PLAN_UNSUPPORTED = (
    "Upgrade to GitHub Pro or make this repository public to enable this "
    "feature. (HTTP 403)"
)


def rules_plan_unsupported(error: RuntimeError) -> bool:
    """Return whether a rules read failed only because the plan lacks it."""
    return str(error).endswith(f"gh: {RULES_PLAN_UNSUPPORTED}")


def malformed_check(item: object) -> bool:
    """Return whether one required-check entry lacks its context or app."""
    return (
        not isinstance(item, dict)
        or not isinstance(item.get("context"), str)
        or not item["context"]
        or type(item.get("integration_id")) is not int
        or item["integration_id"] <= 0
    )


def _effective_protection(  # noqa: C901
    github: GitHub,
    repo: str,
    branch: str,
    admin_bypass: bool,
    reviewed_merge: bool,
    copilot_mode: bool,
    local_mode: bool,
    local_fallback: bool,
    dependabot_route: bool,
) -> tuple[str, str, set[tuple[str, int]], bool, bool]:
    """Classify the effective Ruleset shape for `effective_protection`."""
    try:
        rules = github.get(
            repo, f"rules/branches/{urllib.parse.quote(branch, safe='')}"
        )
    except RuntimeError as error:
        if not rules_plan_unsupported(error):
            return "unknown", str(error), set(), False, False
        # Issue #1210: the plan has no Ruleset, so the branch has none and
        # only the audited single-writer route may still let lifecycle merge.
        return (
            "none",
            "this private repository's GitHub plan does not support "
            "Rulesets, so no Ruleset enforces review or required checks",
            set(),
            False,
            False,
        )
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
    if not pull_rules and not check_rules:
        # Issue #1076: a complete read with no review or check rule means
        # the platform enforces nothing; only the audited single-writer
        # route in `merge_snapshot` may still let lifecycle merge.
        return (
            "none",
            "no Ruleset enforces review or required checks on this branch",
            set(),
            False,
            False,
        )
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
    if any(map(malformed_check, required_items)):
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

    def flag(field: str) -> bool:
        return any(item.get(field) is True for item in pull)

    zero_review = bool(pull) and all(
        item.get("required_approving_review_count") == 0 for item in pull
    )
    stale_and_threads = flag("dismiss_stale_reviews_on_push") and flag(
        "required_review_thread_resolution"
    )
    level_check_controls = (
        zero_review
        and stale_and_threads
        and any(
            context == REVIEW_CHECK_CONTEXT for context, _ in required_contexts
        )
    )
    local_e1_shape = False
    if local_mode:
        review_controls = (
            bool(pull)
            and all(
                item.get("required_approving_review_count", 0) >= 1
                for item in pull
            )
            and stale_and_threads
            and flag("require_last_push_approval")
        )
        # E1 fallback (#1058 decisions 4 and 5): local plus beta-only or
        # always needs no native approval but keeps stale-review dismissal,
        # thread resolution, and exactly the reviewed bypass actor below.
        local_e1_shape = (
            local_fallback
            and not review_controls
            and zero_review
            and stale_and_threads
        )
        review_controls = review_controls or local_e1_shape
        missing_reason = (
            "local mode needs native review, stale-review dismissal, "
            "last-push approval, and thread controls"
            + (", or the E1 fallback shape" if local_fallback else "")
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
        # approval) guards the merge; `level_check_controls` holds both.
        review_controls = level_check_controls and any(
            isinstance(item.get("parameters"), dict)
            and item["parameters"].get("review_on_push") is True
            for item in copilot_rules
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
            and stale_and_threads
            and flag("require_code_owner_review")
            and flag("require_last_push_approval")
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
    hidden_bypass = False
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
            if bypass_actors == [] and not local_e1_shape:
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
            # #1262: a non-admin token cannot read bypass actors; the
            # Dependabot route needs proof that it can never bypass.
            hidden = "bypass_actors" not in ruleset
            if hidden and not (
                dependabot_route
                and ruleset.get("current_user_can_bypass") == "never"
            ):
                return (
                    "blocked",
                    "an effective Ruleset hides its bypass actors; only a "
                    "Dependabot merge that can never bypass may proceed",
                    set(),
                    False,
                    False,
                )
            if not reviewed_merge or (
                not hidden and bypass_actors != REVIEWED_MERGE_BYPASS_ACTORS
            ):
                return (
                    "blocked",
                    "an effective Ruleset permits an unverified bypass",
                    set(),
                    False,
                    False,
                )
            reviewed_bypass = True
            hidden_bypass = hidden_bypass or hidden
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
            + (
                "; GitHub hides the bypass actors, and this token can never "
                "bypass"
                if hidden_bypass
                else ""
            )
            if reviewed_bypass
            else "server-side merge controls are active without bypass"
        ),
        required_contexts,
        reviewed_bypass,
        copilot_only_block_possible,
    )


def merge_route(protection: str) -> str:
    """Return the `allowed`, `manual-only`, or `blocked` merge route."""
    return MERGE_ROUTES.get(protection, "blocked")


def merge_identity(
    github: GitHub,
    repo: str,
    actor: str,
    protection: str,
    authorization_source: str,
    approver: str = "",
) -> tuple[str, str]:
    """Classify the merge actor; return a refusal reason when it is unfit."""
    if protection == "single-writer":
        return "sole-maintainer", ""
    if protection == "independent-approval":
        return "independent-approval", ""
    if protection != "enforced":
        return "none", ""
    if authorization_source in {"comment", "hotfix-emergency"}:
        return "admin-authorizer", ""
    if actor.endswith("[bot]"):
        return "app", ""
    role = live_repository_role(github, repo, actor)
    if role == "write":
        return "agent-write", ""
    if (
        authorization_source == "review"
        and role in MAINTAINER_PERMISSIONS
        and actor.casefold() == approver.casefold()
    ):
        return "approver", ""
    return (
        "agent-" + role,
        f"the agent-route merge actor {actor} has role {role!r}; a Ruleset "
        "route needs an independent write identity without maintain or "
        "admin",
    )


def _writer_logins(
    collaborators: list[dict[str, Any]],
) -> tuple[set[str], str]:
    """Return observed writer logins, or why the readback is incomplete."""
    writers: set[str] = set()
    for item in collaborators:
        login = item.get("login")
        role = item.get("role_name")
        if not isinstance(login, str) or not login:
            return set(), "a collaborator entry has no login"
        # #1058 decision 6: only `role_name` counts; a missing or custom
        # role is never mapped back through the legacy `permission`.
        if not isinstance(role, str) or not role:
            return set(), f"collaborator {login} has no role_name"
        if role in WRITE_ROLES:
            writers.add(login.casefold())
        elif role not in NON_WRITE_ROLES:
            return set(), f"collaborator {login} has the unknown role {role!r}"
    return writers, ""


def _team_writer_gap(
    github: GitHub, repo: str, writers: set[str]
) -> tuple[str, str]:
    """Check that every write-capable team is visible and fully observed."""
    try:
        teams = github.pages(repo, "teams?per_page=100")
    except (RuntimeError, json.JSONDecodeError) as error:
        return "inconclusive", f"the team readback is incomplete: {error}"
    organization = urllib.parse.quote(repo.split("/", 1)[0], safe="")
    for team in teams:
        slug = team.get("slug")
        permission = team.get("permission")
        if not isinstance(slug, str) or not slug:
            return "inconclusive", "a repository team has no slug"
        if permission in NON_WRITE_TEAM_PERMISSIONS:
            continue
        if permission not in WRITE_TEAM_PERMISSIONS:
            return (
                "inconclusive",
                f"team {slug} has the unknown permission {permission!r}",
            )
        endpoint = (
            f"orgs/{organization}/teams/"
            f"{urllib.parse.quote(slug, safe='')}/members?per_page=100"
        )
        try:
            members = github.api_pages(endpoint)
        except (RuntimeError, json.JSONDecodeError):
            return (
                "inconclusive",
                f"the members of write-capable team {slug} are hidden",
            )
        for member in members:
            login = member.get("login")
            if not isinstance(login, str) or not login:
                return (
                    "inconclusive",
                    f"team {slug} lists a member without a login",
                )
            if login.casefold() not in writers:
                return (
                    "inconclusive",
                    f"team {slug} grants write to {login}, who is missing "
                    "from the collaborator readback",
                )
    return "", ""


def single_writer_eligibility(
    github: GitHub,
    repo: str,
    actor: str,
    observed: dict[str, list[str]] | None = None,
) -> tuple[str, str]:
    """Classify the `server_enforcement=none` route (#1076, #1233)."""
    try:
        repository = github.get(repo, "")
        collaborators = github.pages(
            repo, "collaborators?affiliation=all&per_page=100"
        )
        keys = github.pages(repo, "keys?per_page=100")
    except (RuntimeError, json.JSONDecodeError) as error:
        return "inconclusive", f"the writer readback is incomplete: {error}"
    owner = repository.get("owner") if isinstance(repository, dict) else None
    owner_type = owner.get("type") if isinstance(owner, dict) else None
    if owner_type not in {"Organization", "User"}:
        return "inconclusive", "the repository owner type is unavailable"
    writers, reason = _writer_logins(collaborators)
    if reason:
        return "inconclusive", reason
    if owner_type == "Organization":
        state, reason = _team_writer_gap(github, repo, writers)
        if state:
            return state, reason
    if any(type(key.get("read_only")) is not bool for key in keys):
        return "inconclusive", "a deploy key has no read_only flag"
    write_keys = [key for key in keys if key["read_only"] is False]
    if observed is not None:
        observed["accounts"] = sorted(writers)
        observed["deploy_keys"] = sorted(
            str(key.get("id")) for key in write_keys
        )
    if len(writers) + len(write_keys) > 1:
        return (
            "multiple-writers",
            f"{len(writers)} writer account(s) and {len(write_keys)} write "
            "deploy key(s) can change this repository",
        )
    if writers != {actor.casefold()}:
        return (
            "inconclusive",
            f"the merge actor {actor} is not the one observed writer",
        )
    return "eligible", f"{actor} is the only observed writer"


def single_writer_opt_in(
    github: GitHub, repo: str, actor: str, merger: str, state: str, reason: str
) -> tuple[str, str]:
    """Apply the owner's `single_writer_merger` opt-in (Issue #1233)."""
    if state not in {"eligible", "multiple-writers"}:
        return state, reason
    refused = state if state == "multiple-writers" else "inconclusive"
    if actor.casefold() != merger.casefold():
        return refused, f"{reason}; only {merger} may merge by config"
    role = live_repository_role(github, repo, actor)
    if role not in WRITE_ROLES:
        return refused, f"{reason}; {merger} has live role {role!r}"
    return "eligible", f"single_writer_merger {merger} opted in; {reason}"


def configured_single_writer_merger() -> str:
    """Return the opted-in single-writer merger, or '' (Issue #1233)."""
    path = repository_root() / ".csarc/config.yml"
    try:
        config = csarc_config.load_config(path)
    except csarc_config.SettingsError as error:
        raise RuntimeError(str(error)) from error
    return str(config.get("single_writer_merger") or "")


def repository_root() -> Path:
    """Return the repository root for root and generated layouts."""
    parent = Path(__file__).resolve().parents[1]
    return parent.parent if parent.name == ".csarc" else parent


def configured_verification_mode(github: GitHub, repo: str) -> str:
    """Return the live-visibility mode; fail closed on drift (SPEC-011)."""
    config = csarc_config.load_config(repository_root() / ".csarc/config.yml")
    repository = github.get(repo, "")
    private = repository.get("private") if isinstance(repository, dict) else 0
    if not isinstance(private, bool):
        raise RuntimeError(f"Repository visibility: unavailable. {GH_RETRY}.")
    # ADR self-hosted D9 (#1287): warn only; the merge decision is unchanged.
    if text := merge_trace.retire_warning(
        repo,
        private,
        config.get("verification_mode_private"),
        lambda path: github.get(repo, path),
    ):
        sys.stderr.write(f"WARNING: {text}\n")
    mode = str(
        config[f"verification_mode_{'private' if private else 'public'}"]
    )
    flows = repository_root() / ".github/workflows"
    if (mode == "hosted", mode == "self-hosted") != (
        (flows / "pr-policy.yml").is_file(),
        (flows / "csarc-verify.yml").is_file(),
    ):
        raise RuntimeError(
            f"Verification mode {mode}: the rendered files do not match the "
            "current visibility. Run 'csarc update' to render again."
        )
    return mode


def trusted_executor_module() -> ModuleType:
    """Load the base-policy module beside this lifecycle (Issue #1069)."""
    if __package__ in {None, ""}:
        return importlib.import_module("trusted_executor")
    return importlib.import_module(f"{__package__}.trusted_executor")


def subject_repository_root() -> Path:
    """Return the Git checkout the operator runs the lifecycle from."""
    return Path(run(["git", "rev-parse", "--show-toplevel"])).resolve()


def run_from_trusted_base(args: argparse.Namespace) -> int | None:
    """Re-execute a merge decision from the lease's trusted base commit."""
    lease = read_lease(args.lease)
    base_sha = str(lease["base_sha"])
    executor = trusted_executor_module()
    if os.environ.get(executor.TRUSTED_BASE_ENV) == base_sha:
        return None
    subject = subject_repository_root()
    entry = Path(__file__).resolve().relative_to(repository_root())
    with executor.trusted_base_checkout(subject, base_sha) as base:
        script = base / entry
        if not script.is_file():
            raise RuntimeError(
                "Trusted base: no PR lifecycle entry point. Update the base."
            )
        sys.stdout.write(
            f"NOTICE: PR lifecycle {args.handler_name} runs from trusted base "
            f"{base_sha}.\n"
        )
        sys.stdout.flush()
        return subprocess.run(  # noqa: S603 - trusted base entry point
            [sys.executable, str(script), *sys.argv[1:]],
            env={**os.environ, executor.TRUSTED_BASE_ENV: base_sha},
            check=False,
        ).returncode


def bootstrap_trusted_base(args: argparse.Namespace) -> None:
    """Hand merge decisions to the trusted base before they start."""
    if getattr(args, "handler_name", "") not in {"check", "merge"}:
        return
    status = run_from_trusted_base(args)
    if status is not None:
        raise SystemExit(status)


def print_policy_self_test(snapshot: dict[str, object]) -> None:
    """Print the non-authoritative candidate policy comparison."""
    lines = snapshot.get("policy_self_test")
    if isinstance(lines, list):
        sys.stdout.writelines(f"{line}\n" for line in lines)


def base_policy_decision(
    lease: dict[str, Any], pull: dict[str, Any], labels: set[str]
) -> dict[str, Any]:
    """Select the merge route and path tier from the trusted base (#1069)."""
    executor = trusted_executor_module()
    subject = subject_repository_root()
    base_sha = str(lease["base_sha"])
    head_sha = str(lease["head_sha"])
    for sha in (base_sha, head_sha):
        executor.ensure_commit(subject, sha)
    git = ["git", "-C", str(subject)]
    merge_base = run([*git, "merge-base", base_sha, head_sha])
    listing = subprocess.run(  # noqa: S603 - fixed git arguments
        [
            *git,
            "diff",
            "--no-renames",
            "--name-only",
            "-z",
            merge_base,
            head_sha,
        ],
        capture_output=True,
        check=False,
    )
    if listing.returncode:
        raise RuntimeError(f"Changed paths: cannot list them. {GH_RETRY}.")
    base_config = repository_root() / ".csarc/config.yml"
    labels_csv = ",".join(sorted(labels))
    with tempfile.TemporaryDirectory(prefix="csarc-base-policy-") as scratch:
        candidate_config = Path(scratch) / "candidate-config.yml"
        candidate_config.write_text(
            run([*git, "show", f"{head_sha}:.csarc/config.yml"]) + "\n",
            encoding="utf-8",
        )
        provenance = Path(scratch) / "candidate-provenance.json"
        with contextlib.suppress(RuntimeError):
            provenance.write_text(
                run([*git, "show", f"{head_sha}:.csarc/provenance.json"])
            )
        try:
            candidate, schema_source = executor.read_candidate_config(
                candidate_config, labels, provenance
            )
            base_values = executor.read_config(base_config)
            decision = executor.classify_route(
                [
                    item.decode("utf-8", "surrogateescape")
                    for item in listing.stdout.split(b"\0")
                    if item
                ],
                base_values,
                candidate,
            )
        except (OSError, ValueError) as error:
            raise RuntimeError(
                f"Trusted base: cannot read the configuration: {error}. Fix "
                "'.csarc/config.yml'."
            ) from error
        executor.require_route(decision, labels)
        # Issue #1270: the repository side of the registration is the
        # Issue this pull request closes.
        issues = CLOSING_ISSUE.findall(str(pull.get("body") or ""))
        executor.require_registration(
            base_values, candidate, ", ".join(f"#{n}" for n in issues) or "-"
        )
        changed_files = Path(scratch) / "changed-files"
        changed_files.write_bytes(listing.stdout)
        plan = Path(scratch) / "ci-plan.json"
        run(
            [
                sys.executable,
                str(Path(__file__).resolve().with_name("ci_tier.py")),
                "--event",
                "pull_request",
                "--base",
                str(lease["base_ref"]),
                "--head",
                str((pull.get("head") or {}).get("ref") or ""),
                "--labels",
                labels_csv,
                "--files-from",
                str(changed_files),
                "--output-json",
                str(plan),
                "--draft",
                "false",
            ]
        )
        path_tier = str(json.loads(plan.read_text(encoding="utf-8"))["tier"])
        self_test = (
            executor.policy_self_test(
                subject,
                base_config=base_config,
                candidate_config=candidate_config,
                changed_files=changed_files,
                labels=labels_csv,
                trusted=decision,
            )
            if run([*git, "rev-parse", "HEAD"]) == head_sha
            else [
                "Candidate policy self-test skipped: the current checkout "
                "is not the candidate head."
            ]
        )
    return {
        "route": decision.route,
        "reasons": list(decision.reasons),
        "schema_source": schema_source,
        "path_tier": path_tier,
        "self_test": self_test,
    }


def configured_admin_bypass() -> str:
    """Return the normalized configured admin bypass scope."""
    return str(
        csarc_config.load_config(repository_root() / ".csarc/config.yml")[
            "admin_bypass"
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
    run(
        [str(repository_root() / ".csarc/scripts/validate-pr-policy")],
        env=env,
    )


def authenticated_dependabot_commit(
    github: GitHub,
    repo: str,
    pull: dict[str, Any],
    head_sha: str,
    base_sha: str,
) -> tuple[str, dict[str, Any]]:
    """Return the head kind and its GitHub-signed Dependabot commit."""
    eligible, reason, live_base_sha, _, live_head_sha = (
        dependabot_auth.validated_dependabot_snapshot(pull, repo)
    )
    if not eligible or live_base_sha != base_sha or live_head_sha != head_sha:
        raise RuntimeError(
            f"Dependabot merge identity: invalid: {reason}. Merge it manually."
        )

    commit = github.get(repo, f"commits/{head_sha}")
    comparison = github.get(repo, f"compare/{base_sha}...{head_sha}")
    if not isinstance(commit, dict) or not isinstance(comparison, dict):
        raise RuntimeError(
            f"Dependabot head: metadata unavailable. {GH_RETRY}."
        )
    direct, direct_reason = dependabot_auth.authenticated_dependabot_head(
        pull, commit, repo, base_sha
    )
    kind = "direct"
    if not direct:
        # Issue #1052: a synced head is release -> sync -> Dependabot.
        chain: list[dict[str, Any]] = []
        current = commit
        for _ in range(2):
            parents = current.get("parents")
            parent_sha = (
                (parents[0] or {}).get("sha")
                if isinstance(parents, list) and len(parents) == 1
                else ""
            )
            if (
                not isinstance(parent_sha, str)
                or SHA.fullmatch(parent_sha) is None
            ):
                raise RuntimeError(
                    "Dependabot head: not authenticated: "
                    + direct_reason
                    + ". Merge it manually."
                )
            parent = github.get(repo, f"commits/{parent_sha}")
            current = parent if isinstance(parent, dict) else {}
            chain.append(current)
        dependabot_sha = chain[1].get("sha")
        dependabot_comparison = (
            github.get(repo, f"compare/{base_sha}...{dependabot_sha}")
            if isinstance(dependabot_sha, str)
            and SHA.fullmatch(dependabot_sha) is not None
            else {}
        )
        child, child_reason, _, _ = (
            dependabot_auth.trusted_sync_child_candidate(
                pull,
                commit,
                chain[0],
                chain[1],
                (
                    dependabot_comparison
                    if isinstance(dependabot_comparison, dict)
                    else {}
                ),
                repo,
                base_sha,
            )
        )
        if not child:
            raise RuntimeError(
                "Dependabot head: not authenticated: "
                f"{direct_reason}; {child_reason}. Merge it manually."
            )
        kind = "sync-child"
        commit = chain[1]
    return kind, commit


def dependabot_update_scope(message: str) -> list[str]:
    """Return the minor/patch update types a signed Dependabot commit states."""
    _, separator, metadata = message.partition("updated-dependencies:")
    types = DEPENDABOT_UPDATE_TYPE.findall(metadata) if separator else []
    if not types:
        raise RuntimeError(
            "Dependabot update scope: missing in the signed commit. "
            "Merge it manually."
        )
    unsupported = sorted(set(types) - LOCAL_DEPENDABOT_UPDATE_TYPES)
    if unsupported:
        raise RuntimeError(
            "Dependabot update scope "
            + ", ".join(unsupported)
            + ": not automatic. Review and merge it manually."
        )
    return sorted(set(types))


def require_local_dependabot_head(
    github: GitHub,
    repo: str,
    pull: dict[str, Any],
    head_sha: str,
    base_sha: str,
) -> tuple[str, list[str]]:
    """Authenticate a local-mode Dependabot head and its update scope."""
    kind, commit = authenticated_dependabot_commit(
        github, repo, pull, head_sha, base_sha
    )
    message = (commit.get("commit") or {}).get("message")
    return kind, dependabot_update_scope(
        message if isinstance(message, str) else ""
    )


def commit_tree_sha(github: GitHub, repo: str, sha: str) -> str | None:
    """Return one commit's tree SHA, or None when GitHub cannot show it."""
    commit = github.get(repo, f"git/commits/{urllib.parse.quote(sha)}")
    tree = commit.get("tree") if isinstance(commit, dict) else None
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    return tree_sha if isinstance(tree_sha, str) else None


def require_routine_quota_fallback(
    github: GitHub,
    lease: dict[str, Any],
    pull: dict[str, Any],
    authorization_payload: dict[str, Any],
    note_url: str,
) -> set[str]:
    """Validate a canonical routine-PR quota note and every bound run."""
    raise RuntimeError(
        "Quota fallback: retired by SPEC-009. Use the "
        "governance-switch route for an Actions outage."
    )


def requirement_trace(
    github: GitHub, repo: str, pull: dict[str, Any], head: str, local: object
) -> dict[str, object] | None:
    """Check the closing Issue's trace; at merge also its `check:` runs."""
    body = str(pull.get("body") or "")
    numbers = sorted({int(value) for value in CLOSING_ISSUE.findall(body)})
    refs = [str((pull.get(key) or {}).get("ref")) for key in ("base", "head")]
    if not numbers or not risk_controls.traced_route(*refs):
        return None
    issue = github.get(repo, f"issues/{numbers[0]}")
    if len(numbers) != 1 or not isinstance(issue, dict):
        raise RuntimeError(
            "Traced pull request: must close one Issue. Fix the body."
        )
    files = github.pages(repo, f"pulls/{pull['number']}/files?per_page=100")
    keys = ("filename", "previous_filename")

    def read(path: str) -> str | None:
        quoted = urllib.parse.quote(path)
        with contextlib.suppress(RuntimeError):
            data = github.get(repo, f"contents/{quoted}?ref={head}")
            if isinstance(data, dict) and data.get("type") == "file":
                return base64.b64decode(str(data["content"])).decode()
        return None

    logins = [str(a.get("login")) for a in issue.get("assignees") or []]
    trace, problems, notes = risk_controls.ready(
        (numbers[0], str(issue.get("body") or ""), logins),
        body,
        sorted({str(f[key]) for f in files for key in keys if f.get(key)}),
        ci_tier.scope_for,
        read,
    )
    evidence = trace.get("evidence", {}).values()
    names = {v[6:] for v in evidence if v.startswith("check:")}
    if local is not None and (
        names := names - ({"verify"} if local else set())
    ):
        path = f"commits/{head}/check-runs?filter=latest&per_page=100"
        runs = github.collection(repo, path, "check_runs")
        passed = {
            r.get("name") for r in runs if r.get("conclusion") == "success"
        }
        problems += [f"RK31 check did not pass: {n}" for n in names - passed]
    if problems:
        raise RuntimeError(
            "Requirement trace: incomplete (SPEC-010).\n"
            + "\n".join(f"requirement-trace: {line}" for line in problems)
            + "\nFix each listed item."
        )
    sys.stdout.writelines(f"requirement-trace: {line}\n" for line in notes)
    return trace


def trace_command(args: argparse.Namespace, github: GitHub) -> None:
    """Run the Ready requirement-trace check for validate-pr-policy."""
    pull = live_pull(github, args.repo, args.pr_number, args.head_sha)
    requirement_trace(github, args.repo, pull, args.head_sha, None)


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
    verification_mode = configured_verification_mode(github, repo)
    # Self-hosted keeps the local governance; only its evidence differs.
    self_hosted = verification_mode == "self-hosted"
    if self_hosted:
        verification_mode = "local"
    dependabot_head = ""
    dependabot_scope: list[str] = []
    if require_dependabot_head and verification_mode == "local":
        # Issue #1076: local mode has no hosted eligibility workflow; the
        # signed commit's own update scope replaces it.
        dependabot_head, dependabot_scope = require_local_dependabot_head(
            github, repo, pull, str(head_sha), str(lease["base_sha"])
        )
    elif require_dependabot_head:
        dependabot_head = require_trusted_dependabot_head(
            github, repo, pull, str(head_sha), str(lease["base_sha"])
        )
    if pull.get("draft") is not False:
        raise RuntimeError("Pull request: Draft at merge time. Mark it ready.")
    if UNCHECKED.search(str(pull.get("body") or "")):
        raise RuntimeError(
            "Pull request: unchecked checklist item. Complete it."
        )
    level_decision = resolve_release_level(github, repo, pull)
    label_names = {
        str(label.get("name") or "").casefold()
        for label in pull.get("labels", [])
        if isinstance(label, dict)
    }
    # Issue #1069: the trusted base selects the merge route and path tier;
    # the candidate's own policy only runs as a non-authoritative self-test.
    policy = base_policy_decision(lease, pull, label_names)
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
            "Merge blocked by an unresolved comment: "
            + str(blocker.get("html_url") or "unknown URL")
            + ". Resolve it."
        )
    review_states = current_reviews(reviews)
    blockers = sorted(
        login
        for login, review in review_states.items()
        if review.get("state") == "CHANGES_REQUESTED"
    )
    if blockers:
        raise RuntimeError(
            "Changes requested: by " + ", ".join(blockers) + ". Resolve them."
        )
    actor = github.viewer(explicit_actor).casefold()
    if actor != str(lease["actor"]).casefold():
        raise RuntimeError(
            "GitHub actor: changed after the lease. Reacquire the lease."
        )
    # Issue #1082: the `review` check, `status`, and merge share one
    # decision. A bot-authored Dependabot body cannot carry the marker, so
    # the authenticated local Dependabot route is its own opt-in (#1076).
    review_input = review_gate.review_inputs(
        github,
        repo,
        pr_number,
        pull,
        review_settings(),
        level_decision,
        actor=actor,
        default_branch=str(lease["default_branch"]),
        admin_bypass="valid" if dependabot_scope else None,
    )
    review_decision = review_gate.decide(review_input)
    if not review_decision["passed"]:
        raise RuntimeError(review_decision["reason"])
    admin_bypass = review_decision["admin_bypass"] == "valid"
    copilot_mode = review_decision["mode"] == "copilot"
    source = review_decision["source"]
    bypass_route = (
        level_decision.level
        if admin_bypass
        else "hotfix"
        if "hotfix" in label_names
        else None
    )
    hotfix_evidence: dict[str, object] | None = None
    if source in {"maintainer", "copilot"}:
        reviewed = (
            review_input["approval"]
            if source == "maintainer"
            else review_input["copilot"].review
        )
        auth = {**reviewed, "created_at": reviewed.get("submitted_at")}
        authorization_source = "review" if source == "maintainer" else source
        authorization_url = str(reviewed.get("html_url") or "")
    elif source == "admin-bypass":
        if not authorization_url:
            raise RuntimeError(
                "Admin bypass: no exact maintainer authorization comment. "
                "Post one."
            )
        auth = authorization(
            github, repo, pr_number, head_sha, authorization_url
        )
        if parse_time(
            auth.get("created_at"), "Authorization"
        ) < authorization_anchor(github, lease):
            raise RuntimeError(
                "Authorization: predates the active lease. Renew a live lease "
                "with 'acquire --renew' to keep it."
            )
        auth_actor = str((auth.get("user") or {}).get("login") or "")
        if auth_actor.casefold() != actor:
            raise RuntimeError(
                "Admin bypass: authorizer is not the merge actor. Merge as the "
                "authorizer."
            )
        if live_repository_role(github, repo, actor) != "admin":
            raise RuntimeError(
                "Admin bypass: no live admin permission. Ask an admin."
            )
        authorization_source = "comment"
    else:
        if not authorization_url:
            raise RuntimeError(
                "Emergency hotfix: no exact-head authorization comment. "
                "Post one."
            )
        auth = authorization(
            github, repo, pr_number, head_sha, authorization_url
        )
        if parse_time(
            auth.get("created_at"), "Authorization"
        ) < authorization_anchor(github, lease):
            raise RuntimeError(
                "Hotfix authorization: predates the lease. Reauthorize."
            )
        auth_actor = str((auth.get("user") or {}).get("login") or "")
        if auth_actor.casefold() != actor:
            raise RuntimeError(
                "Emergency hotfix authorization: not the merge actor. Merge as "
                "the authorizer."
            )
        hotfix_evidence = hotfix_emergency_evidence(github, repo, pull, auth)
        authorization_source = "hotfix-emergency"
    authorized_at = parse_time(auth.get("created_at"), "Authorization")
    timeline = github.pages(repo, f"issues/{pr_number}/timeline?per_page=100")
    if any(
        item.get("event") in DRAFT_EVENTS
        and parse_time(item.get("created_at"), "Draft event") >= authorized_at
        for item in timeline
    ):
        raise RuntimeError(
            "Merge authorization: a newer Draft event voids it. Reauthorize."
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
                f"Closing reference #{issue_number}: not an Issue. Edit the PR "
                "body."
            )
        if UNCHECKED.search(str(issue.get("body") or "")):
            raise RuntimeError(
                f"Issue #{issue_number}: unchecked checklist item. Complete it."
            )

    base = pull.get("base") or {}
    base_ref = base.get("ref")
    if not isinstance(base_ref, str):
        raise RuntimeError(
            f"Pull request: base branch unavailable. {GH_RETRY}."
        )
    title = pull.get("title")
    if not isinstance(title, str) or not title.strip():
        raise RuntimeError(f"Pull request: title unavailable. {GH_RETRY}.")
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
        # Copilot is never required: only Copilot evidence needs its rules.
        authorization_source == "copilot",
        verification_mode == "local",
        verification_mode == "local"
        and configured_admin_bypass() in {"beta-only", "always"},
        dependabot_route=bool(dependabot_head),
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
            if live_repository_role(github, repo, actor) != "admin":
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
    server_enforcement = "ruleset"
    merger = ""
    observed_writers: dict[str, list[str]] = {}
    if protection == "none":
        server_enforcement = "none"
        merger = configured_single_writer_merger()
        writer_state, reason = single_writer_eligibility(
            github, repo, actor, observed_writers
        )
        # #1211: an independent exact-head approval lets a multi-writer
        # repository merge; an incomplete readback stays manual-only.
        approved = (
            writer_state == "multiple-writers"
            and authorization_source == "review"
        )
        if approved:
            writer_state = "eligible"
            reason = f"{authorization_actor} approved the exact head; {reason}"
        elif merger:
            writer_state, reason = single_writer_opt_in(
                github, repo, actor, merger, writer_state, reason
            )
        if writer_state != "eligible":
            protection = writer_state
        elif mergeable_state != "clean":
            # Nothing on the server blocks an `unstable` or unknown state,
            # so lifecycle never treats it as mergeable.
            protection = "blocked"
            reason = (
                f"GitHub reports mergeable_state={mergeable_state!r}; "
                "without a Ruleset only a clean pull request can merge"
            )
        else:
            protection = "independent-approval" if approved else "single-writer"
            if verification_mode != "local":
                required_contexts = declared_required_contexts()
    identity, identity_refusal = merge_identity(
        github,
        repo,
        actor,
        protection,
        authorization_source,
        authorization_actor,
    )
    if identity_refusal:
        protection = "blocked"
        reason = identity_refusal
    elif protection == "single-writer" and merger:
        identity = "configured-merger"
    quota_run_urls = (
        require_routine_quota_fallback(
            github, lease, pull, auth, quota_fallback_note_url
        )
        if quota_fallback_note_url
        else set()
    )
    if quota_run_urls and policy["route"] != "ordinary":
        raise RuntimeError(
            "Governance switch: quota fallback cannot replace its required "
            "checks. Run them."
        )
    # The release-channel floor and the trusted path tier both bind local
    # evidence; the stronger one wins (Issue #1069).
    required_tier = trusted_executor_module().stronger_suite(
        level_decision.suite, policy["path_tier"]
    )
    check_evidence = "not-enforced"
    local_evidence: dict[str, Any] | None = None
    # Local and hosted evidence share one normalized record; only its trust
    # label differs.
    verification_record: dict[str, Any] | None = None
    hosted_evidence: dict[str, Any] = {}
    vm_evidence: dict[str, Any] | None = None
    config_path = repository_root() / ".csarc/config.yml"
    exit_reason = (
        self_hosted_evidence.exit_reason(
            subject_repository_root(), config_path, lease
        )
        if self_hosted
        else ""
    )
    if self_hosted and not exit_reason and not quota_run_urls:
        vm_evidence = self_hosted_evidence.require(
            github, repo, lease, pull, config_path, required_tier
        )
        check_evidence = "self-hosted-registered"
        verification_record = evidence_freshness.normalized_record(
            vm_evidence, evidence_freshness.TRUST_SELF_HOSTED
        )
    elif verification_mode == "local":
        if quota_run_urls:
            raise RuntimeError(
                "Quota fallback: not for local verification. Run it."
            )
        local_evidence = local_verification.require(
            head_sha=str(head_sha),
            tree_sha=str(lease["head_tree"]),
            base_ref=str(lease["base_ref"]),
            base_sha=str(lease["base_sha"]),
            required_tier=required_tier,
        )
        check_evidence = "local-self-attested"
        verification_record = evidence_freshness.normalized_record(
            local_evidence, evidence_freshness.TRUST_LOCAL
        )
    elif protection in AGENT_PROTECTIONS or quota_run_urls:
        check_evidence = require_successful_checks(
            github,
            repo,
            head_sha,
            required_contexts,
            quota_run_urls,
            hosted_evidence,
        )
        if hosted_evidence:
            verification_record = evidence_freshness.normalized_record(
                hosted_evidence, evidence_freshness.TRUST_HOSTED
            )
    trace = requirement_trace(
        github, repo, pull, str(head_sha), verification_mode == "local"
    )
    require_lease(github, lease, repo, pr_number, head_sha)
    head_ref = str((pull.get("head") or {}).get("ref") or "")
    return {
        "requirement_trace": trace,
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
        "merge_mode": (
            "agent" if protection in AGENT_PROTECTIONS else "human-only"
        ),
        "merge_permission": merge_route(protection),
        "server_enforcement": server_enforcement,
        "merge_identity": identity,
        "single_writer_merger": merger,
        "observed_writers": observed_writers,
        "protection_reason": reason,
        "required_check_evidence": check_evidence,
        "local_verification": local_evidence,
        "verification_record": verification_record,
        "hosted_verification": hosted_evidence or None,
        "self_hosted_verification": vm_evidence,
        "self_hosted_exit": exit_reason,
        "trailer_route": trailer_route(
            str(lease["base_ref"]),
            head_ref,
            label_names,
            bool(dependabot_head),
        ),
        "merge_route": policy["route"],
        "merge_route_reasons": policy["reasons"],
        "schema_source": policy.get("schema_source", "base"),
        "required_tier": required_tier,
        "policy_self_test": policy["self_test"],
        "admin_bypass": admin_bypass,
        "dependabot_head": dependabot_head,
        "dependabot_update_scope": dependabot_scope,
        "hotfix_evidence": hotfix_evidence,
        "review_decision": review_decision,
    }


def args_snapshot(
    github: GitHub, lease: dict[str, Any], args: argparse.Namespace
) -> dict[str, object]:
    """Take the merge snapshot with this command's own inputs."""
    return merge_snapshot(
        github,
        lease,
        args.authorization_url,
        getattr(args, "actor", ""),
        getattr(args, "quota_fallback_note_url", ""),
        getattr(args, "require_dependabot_head", False),
    )


def review_settings() -> str:
    """Return this checkout's normalized Copilot review setting."""
    return review_gate.review_settings(
        Path(__file__).resolve().parents[2] / ".csarc/config.yml"
    )


def resolve_release_level(
    github: GitHub, repo: str, pull: dict[str, Any]
) -> release_level.Decision:
    """Resolve the live pull request's review requirement."""
    config = Path(__file__).resolve().parents[2] / ".csarc/config.yml"
    return release_level.resolve_pull(
        github, repo, pull, release_level.load_settings(config)
    )


def mutate_state(args: argparse.Namespace, github: GitHub) -> None:
    """Change Draft state only while the exact lease remains live."""
    lease = caller_lease(args, github)
    require_lease(github, lease, args.repo, args.pr_number, args.head_sha)
    pull = live_pull(github, args.repo, args.pr_number, args.head_sha)
    current = bool(pull.get("draft"))
    desired = args.state == "draft"
    if current == desired:
        raise RuntimeError(
            f"Pull request: already {args.state}. No change needed."
        )
    if not desired:
        requirement_trace(github, args.repo, pull, args.head_sha, None)
    command = ["gh", "pr", "ready", str(args.pr_number), "--repo", args.repo]
    if desired:
        command.append("--undo")
    run(command)
    require_lease(github, lease, args.repo, args.pr_number, args.head_sha)
    updated = live_pull(github, args.repo, args.pr_number, args.head_sha)
    if bool(updated.get("draft")) != desired:
        raise RuntimeError(
            "Pull request: Draft state did not change. Run 'gh pr view'."
        )


def read_body_file(body_file: Path | None) -> str | None:
    """Read an optional UTF-8 pull-request body."""
    if body_file is None:
        return None
    try:
        return body_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise RuntimeError(
            "Pull request body file: not UTF-8. Save it as UTF-8."
        ) from error


def promotion_milestone(
    github: GitHub, repo: str, head: str, body: str
) -> list[str]:
    """Return the tracker Milestone option of a `promote/m<N>-*` PR."""
    route = re.fullmatch(r"promote/m([0-9]+)-[a-z0-9][a-z0-9-]*", head)
    if route is None:
        return []
    tracker = re.search(r"[Rr][Ee][Ff][Ss]\s+#([0-9]+)", body)
    issue = github.get(repo, f"issues/{tracker[1]}") if tracker else {}
    if not isinstance(issue, dict):
        issue = {}
    milestone = issue.get("milestone") or {}
    if (
        "pull_request" in issue
        or not str(issue.get("title")).startswith(f"Milestone {route[1]}: ")
        or str(milestone.get("number")) != route[1]
    ):
        raise RuntimeError(
            f"Milestone {route[1]} promotion: no tracker reference. Add 'Refs "
            "#N' for its tracker Issue."
        )
    return ["--milestone", str(milestone.get("title"))]


def create_draft_pull(  # noqa: C901
    args: argparse.Namespace, github: GitHub
) -> None:
    """Create one clean, pushed pull request directly in Draft state."""
    if REPOSITORY.fullmatch(args.repo) is None:
        raise RuntimeError(
            "Repository: invalid identity. Pass --repo owner/name."
        )
    if not args.title.strip() or "\n" in args.title:
        raise RuntimeError(
            "Pull request title: not one non-empty line. Pass one line."
        )
    body = read_body_file(args.body_file)
    if body is None or not body.strip():
        raise RuntimeError("Pull request body: empty. Write it.")
    require_origin(args.repo)
    milestone = promotion_milestone(github, args.repo, args.head, body)
    for branch in (args.base, args.head):
        run(["git", "check-ref-format", "--branch", branch])
    current_branch = run(["git", "branch", "--show-current"])
    if current_branch != args.head:
        raise RuntimeError("Current branch: differs from --head. Check it out.")
    if run(["git", "status", "--porcelain"]):
        raise RuntimeError("Worktree: not clean. Commit or stash changes.")
    head_sha = run(["git", "rev-parse", "HEAD"])
    if SHA.fullmatch(head_sha) is None:
        raise RuntimeError("Current head commit: invalid. Run 'git log -1'.")
    if branch_sha(github, args.repo, args.head) != head_sha:
        raise RuntimeError("Remote branch: not at current HEAD. Push it.")
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
            *milestone,
        ],
        input_text=body,
    )
    url = output.splitlines()[-1].strip() if output else ""
    match = re.fullmatch(
        rf"https://github\.com/{re.escape(args.repo)}/pull/([1-9][0-9]*)",
        url,
    )
    if match is None:
        raise RuntimeError(
            "GitHub: no pull request URL returned. Run 'gh pr list --head "
            "<branch>'."
        )
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
        raise RuntimeError(
            "Created pull request: not Draft. Convert it to Draft."
        )
    # message-pattern: allow X1 URL output for callers
    sys.stdout.write(url + "\n")


def admin_bypass_marker_body(body: str, present: bool) -> str:
    """Insert or remove the one exact admin-bypass marker line."""
    lines = [
        line
        for line in body.replace("\r\n", "\n").split("\n")
        if line.strip().lstrip("-*+").strip() != ADMIN_BYPASS_MARKER
    ]
    if present:
        anchor = next(
            (
                index + 1
                for index, line in enumerate(lines)
                if line.lstrip().startswith("<!--")
                and ADMIN_BYPASS_MARKER in line
            ),
            None,
        )
        if anchor is None:
            while lines and not lines[-1].strip():
                lines.pop()
            lines.extend(("", ADMIN_BYPASS_MARKER))
        else:
            lines.insert(anchor, ADMIN_BYPASS_MARKER)
    return "\n".join(lines).rstrip("\n") + "\n"


def requested_edit_body(
    body_file: Path | None, marker: str | None, pull: dict[str, Any]
) -> str | None:
    """Return the body an edit writes from a file or the marker action."""
    if marker is None:
        return read_body_file(body_file)
    if body_file is not None:
        raise RuntimeError(
            "Options: --body-file and --admin-bypass-marker conflict. Use one."
        )
    return admin_bypass_marker_body(
        str(pull.get("body") or ""), marker == "add"
    )


def edit_metadata(args: argparse.Namespace, github: GitHub) -> None:
    """Edit the body, labels, or milestone while the lease remains live."""
    lease = caller_lease(args, github)
    require_lease(github, lease, args.repo, args.pr_number, args.head_sha)
    pull = live_pull(github, args.repo, args.pr_number, args.head_sha)
    labels = {
        item.get("name")
        for item in pull.get("labels", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    body_file = getattr(args, "body_file", None)
    marker = getattr(args, "admin_bypass_marker", None)
    requested_body = requested_edit_body(body_file, marker, pull)
    if not any(
        (
            body_file is not None,
            marker is not None,
            args.add_label,
            args.remove_label,
            args.milestone is not None,
            args.remove_milestone,
        )
    ):
        raise RuntimeError(
            "Edit: nothing requested. Give a body, label, or milestone."
        )
    if any(
        "\n" in label or not label
        for label in args.add_label + args.remove_label
    ):
        raise RuntimeError(
            "Label names: empty or multi-line. Pass one-line names."
        )
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
        raise RuntimeError(
            "Pull request metadata: did not change. Run 'gh pr view'."
        )


def check(args: argparse.Namespace, github: GitHub) -> None:
    """Print the live merge snapshot without mutating GitHub."""
    lease = caller_lease(args, github)
    snapshot = args_snapshot(github, lease, args)
    # message-pattern: allow X1 JSON output
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
    root = Path(__file__).resolve().parents[2]
    config = csarc_config.load_config(root / ".csarc/config.yml")
    try:
        # One shared resolver decides the Release writer (#1068).
        csarc_owned = csarc_config.renders_release_workflow(config)
    except ValueError as error:
        raise RuntimeError(str(error)) from error
    if not csarc_owned:
        return ""
    repo = str(lease["repository"])
    pr_number = int(lease["pull_request"])
    head_sha = str(lease["head_sha"])
    require_lease(github, lease, repo, pr_number, head_sha)
    if head_ref.startswith("sync/main-to-"):
        pull = live_pull(github, repo, pr_number, head_sha)
        if require_routine_route(github, repo, lease, pull) != "sync":
            raise RuntimeError(
                "Release bypass: needs a formal sync route. Use one."
            )
        return ""
    if promotion is not None:
        source_sha = run(["git", "-C", str(root), "rev-parse", f"{head_sha}^1"])
        return run(
            [
                sys.executable,
                str(root / ".csarc" / "scripts" / "release_policy.py"),
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
                str(root / ".csarc" / "scripts" / "release_policy.py"),
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
                "--pr-title",
                str(pull.get("title") or ""),
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
                str(root / ".csarc" / "scripts" / "verify-release-candidate"),
                str(candidate),
            ],
            env=env,
        )


def trailer_route(
    base_ref: str, head_ref: str, labels: set[str], dependabot: bool
) -> str:
    """Name the legal lifecycle route recorded in `CSARC-Route`."""
    if dependabot or head_ref.startswith("dependabot/"):
        return "dependabot"
    if head_ref.startswith("sync/main-to-"):
        return "sync"
    kind = main_route_kind(base_ref, head_ref, set(labels))
    if kind in {
        "hotfix",
        "isolated",
        "milestone",
        "release-follow-up",
        "release-recovery",
    }:
        return kind
    if "hotfix" in labels:
        return "hotfix"
    return "issue"


def require_head_contains_base(
    github: GitHub, repo: str, lease: dict[str, Any]
) -> None:
    """Refuse a head that does not contain the lease-bound base commit."""
    comparison = github.get(
        repo, f"compare/{lease['base_sha']}...{lease['head_sha']}"
    )
    status = comparison.get("status") if isinstance(comparison, dict) else None
    if status not in {"ahead", "identical"}:
        raise RuntimeError(
            "Pull request head: lacks the base "
            f"{lease['base_sha']} (compare status {status!r}). Merge the "
            "base and rerun 'verify' or 'verify-fast'."
        )


def merge_evidence(
    snapshot: dict[str, object], lease: dict[str, Any]
) -> tuple[bytes, str]:
    """Return canonical evidence bytes and trust bound to the lease tree."""
    local = snapshot.get("local_verification")
    hosted = snapshot.get("hosted_verification")
    if isinstance(local, dict):
        payload, trust = local, "self-attested-local"
    elif isinstance(hosted, dict):
        payload, trust = hosted, "github-hosted"
    elif isinstance(vm := snapshot.get("self_hosted_verification"), dict):
        payload, trust = vm, "self-hosted-registered"
    else:
        raise RuntimeError(
            "evidence-missing: no exact-head verification evidence. "
            "Rerun verification."
        )
    if (
        payload.get("head_sha") != lease["head_sha"]
        or payload.get("tree_sha") != lease["head_tree"]
    ):
        raise RuntimeError(
            "Verification evidence: not bound to the leased tree. Rerun "
            "'verify' on the exact head."
        )
    trace = snapshot.get("requirement_trace")
    if isinstance(trace, dict):
        payload = {**payload, "requirement_trace": trace}
    try:
        return merge_trace.canonical_bytes(payload), trust
    except merge_trace.EvidenceError as error:
        raise RuntimeError(
            f"Verification evidence: {error}. Rerun verification."
        ) from error


def comment_id(url: str) -> int:
    """Return the numeric ID of one PR-comment locator."""
    match = merge_trace.COMMENT_LOCATOR.fullmatch(url)
    if match is None:
        raise RuntimeError(
            "Merge evidence summary: invalid URL. Delete the marker comment."
        )
    return int(match.group("comment"))


def ensure_summary(
    github: GitHub,
    repo: str,
    pr_number: int,
    record: dict[str, object],
    data: bytes,
) -> str:
    """Create, or replace in place, the PR's single evidence summary."""
    summaries = [
        comment
        for comment in github.pages(
            repo, f"issues/{pr_number}/comments?per_page=100"
        )
        if merge_trace.is_summary(str(comment.get("body") or ""))
    ]
    if len(summaries) > 1:
        raise RuntimeError(
            "Merge evidence summary: more than one. Remove the extra "
            "marker comments."
        )
    body = merge_trace.summary_comment(record, data)
    if not summaries:
        created = github.comment(repo, pr_number, body)
        url = str(created.get("html_url") or "")
        comment_id(url)
        return url
    existing = summaries[0]
    url = str(existing.get("html_url") or "")
    comment_id(url)
    try:
        current = merge_trace.parse_summary(str(existing.get("body") or ""))
    except merge_trace.EvidenceError:
        current = None
    if current is not None and current.status != "attempt":
        raise RuntimeError(
            "Merge evidence summary: records a completed merge "
            f"({current.status}). Do not change it."
        )
    if current is None or current.record != record or current.data != data:
        github.edit_comment(repo, comment_id(url), body)
    return url


def merge_trailers(
    contract: dict[str, Any],
    snapshot: dict[str, object],
    lease: dict[str, Any],
    locator: str,
    record: dict[str, object],
) -> list[tuple[str, str]]:
    """Build the fixed squash trailers for one lifecycle merge."""
    values: dict[str, str | list[str]] = {
        "CSARC-Evidence": locator,
        "CSARC-Evidence-SHA256": str(record["digest"]),
        "CSARC-Evidence-Tree": str(lease["head_tree"]),
        "CSARC-Trust": str(record["trust"]),
        "CSARC-Route": str(record["route"]),
        "CSARC-Approval": str(snapshot.get("authorization_source") or ""),
        "CSARC-Authorization": str(snapshot.get("authorization_url") or ""),
    }
    try:
        return merge_trace.build_trailers(contract, values)
    except merge_trace.EvidenceError as error:
        raise RuntimeError(str(error)) from error


def pull_commit_messages(
    github: GitHub, repo: str, pr_number: int
) -> list[str]:
    """Read every commit message of the pull request being squashed."""
    return [
        str((item.get("commit") or {}).get("message") or "")
        for item in github.pages(
            repo, f"pulls/{pr_number}/commits?per_page=100"
        )
    ]


def trace_lines(
    snapshot: dict[str, object], lease: dict[str, Any], suffix: str
) -> list[str]:
    """Return the audit trace lines recorded in the summary status."""
    lines: list[str] = []
    # Issue #1239: new settings judged by a release schema stay visible.
    if str(snapshot.get("schema_source") or "base") != "base":
        lines.append(
            f"schema-trace: schema_source={snapshot['schema_source']} {suffix}"
        )
    if snapshot.get("reviewed_bypass") is True:
        reason = (
            "exact-head-copilot-review"
            if snapshot.get("authorization_source") == "copilot"
            else "emergency-hotfix"
            if snapshot.get("authorization_source") == "hotfix-emergency"
            else "exact-head-review"
        )
        lines.append(
            "bypass-trace: "
            f"release_level={snapshot['release_level']} "
            f"route={snapshot['bypass_route']} "
            f"actor={lease['actor']} reason={reason} {suffix}"
        )
    if snapshot.get("authorization_source") == "copilot":
        lines.append(
            "copilot-review-trace: "
            f"review={snapshot['authorization_url']} "
            f"head={lease['head_sha']} actor={lease['actor']} {suffix}"
        )
    if snapshot.get("protection") == "independent-approval":
        lines.append(
            "independent-approval-trace: "
            f"approver={snapshot.get('authorization_actor')} "
            f"merger={lease['actor']} server_enforcement=none "
            f"head={lease['head_sha']} {suffix}; no Ruleset enforced this "
            "merge, lifecycle revalidated every control"
        )
    elif snapshot.get("server_enforcement") == "none":
        observed = snapshot.get("observed_writers")
        opt_in = ""
        if snapshot.get("single_writer_merger") and isinstance(observed, dict):
            # #1233: name the config opt-in and every writer at merge time.
            opt_in = (
                "enabled_by=config:single_writer_merger "
                f"writers={','.join(observed['accounts']) or '-'} "
                f"write_deploy_keys={','.join(observed['deploy_keys']) or '-'} "
            )
        lines.append(
            "single-writer-trace: "
            f"writer={lease['actor']} server_enforcement=none {opt_in}"
            f"head={lease['head_sha']} {suffix}; no Ruleset enforced this "
            "merge, lifecycle revalidated every control"
        )
    scope = snapshot.get("dependabot_update_scope")
    if isinstance(scope, list) and scope:
        lines.append(
            "dependabot-trace: "
            f"kind={snapshot['dependabot_head']} "
            f"update_types={','.join(str(item) for item in scope)} "
            f"route=dependabot release_level={snapshot['release_level']} "
            f"{suffix}"
        )
    local_evidence = snapshot.get("local_verification")
    if isinstance(local_evidence, dict):
        lines.append(
            "local-verification-trace: "
            f"head={lease['head_sha']} tree={local_evidence['tree_sha']} "
            f"base={lease['base_sha']} tier={local_evidence['tier']} "
            f"scopes={','.join(local_evidence['scopes'])} {suffix} "
            "trust=self-attested-local; this is not trusted hosted evidence"
        )
    if snapshot.get("self_hosted_verification") or snapshot.get(
        "self_hosted_exit"
    ):
        lines += self_hosted_evidence.trace_lines(snapshot, suffix)
    return lines


def merge(args: argparse.Namespace, github: GitHub) -> None:  # noqa: C901
    """Merge only when the lease and exact-head controls are enforced."""
    lease = caller_lease(args, github)
    try:
        contract = merge_trace.load_contract()
    except merge_trace.EvidenceError as error:
        raise RuntimeError(str(error)) from error
    snapshot = args_snapshot(github, lease, args)
    if snapshot["merge_mode"] != "agent":
        permission = str(snapshot.get("merge_permission") or "blocked")
        step = (
            "A human maintainer must merge it manually, untraced"
            if permission == "manual-only"
            else "Fix the condition before a merge"
        )
        raise RuntimeError(
            f"Agent merge is {permission}: "
            f"{snapshot.get('protection_reason') or 'protection is unproven'}"
            f". {step}."
        )
    print_policy_self_test(snapshot)
    candidate_evidence = revalidate_release_candidate(
        github,
        lease,
        str(snapshot.get("head_ref") or ""),
        str(snapshot.get("release_level") or ""),
    )
    if candidate_evidence:
        # message-pattern: allow X2 release_policy output without change
        sys.stdout.write(candidate_evidence.rstrip() + "\n")
    snapshot = args_snapshot(github, lease, args)
    title = str(snapshot["title"])
    require_head_contains_base(github, args.repo, lease)
    # Because the head contains the base, the squash tree is the head tree;
    # read it back before merging and bind it to the evidence.
    if commit_tree_sha(github, args.repo, args.head_sha) != lease["head_tree"]:
        raise RuntimeError(
            "tree-mismatch: the head tree differs from the verified "
            "tree. Rerun verification."
        )
    data, trust = merge_evidence(snapshot, lease)
    route = str(snapshot.get("trailer_route") or "issue")
    try:
        record = merge_trace.envelope(data, trust=trust, route=route)
    except merge_trace.EvidenceError as error:
        raise RuntimeError(str(error)) from error
    # The only pre-merge write is the durable evidence summary; every trace
    # waits until the merge is read back (Issue #1073).
    locator = ensure_summary(github, args.repo, args.pr_number, record, data)
    trailers = merge_trailers(contract, snapshot, lease, locator, record)
    message = merge_trace.squash_message(
        merge_trace.breaking_footers(
            pull_commit_messages(github, args.repo, args.pr_number)
        ),
        trailers,
    )
    confirm_refs(lease)
    if branch_sha(github, args.repo, lease["base_ref"]) != lease["base_sha"]:
        raise RuntimeError(
            "Destination branch: advanced before merge. Update the branch."
        )
    result = github.merge(
        args.repo, args.pr_number, args.head_sha, title, message
    )
    merge_sha = result.get("sha")
    if result.get("merged") is not True or not isinstance(merge_sha, str):
        raise RuntimeError(
            "Merge: GitHub did not merge it synchronously. Check the PR."
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
            "Merged pull request: state differs from the response. Run 'gh pr "
            "view'."
        )
    commit = merge_commit if isinstance(merge_commit, dict) else {}
    merged_tree = (commit.get("tree") or {}).get("sha")
    merged_trailers = merge_trace.parse_trailers(
        str(commit.get("message") or "")
    )
    suffix = f"merge={merge_sha} evidence={locator}"
    status = (
        "tree-mismatch"
        if merged_tree != lease["head_tree"]
        else "trailer-mismatch"
        if merged_trailers != trailers
        else "merged"
    )
    result_name = "traced" if status == "merged" else status
    lines = [
        f"merge-trace: result={result_name} {suffix} tree={merged_tree} "
        f"expected_tree={lease['head_tree']} route={route} trust={trust} "
        f"actor={lease['actor']} server_enforcement="
        f"{snapshot.get('server_enforcement') or 'ruleset'} "
        f"identity={snapshot.get('merge_identity') or 'unknown'}"
    ]
    if status == "merged":
        lines.extend(trace_lines(snapshot, lease, suffix))
    github.edit_comment(
        args.repo,
        comment_id(locator),
        merge_trace.summary_comment(record, data, status, lines),
    )
    if status != "merged":
        raise RuntimeError(
            f"{status}: merge commit {merge_sha} lacks the verified tree "
            "or trailers. Run 'git show --stat' on it."
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
    lease = caller_lease(args, github)
    if (
        lease["repository"].casefold() != args.repo.casefold()
        or lease["pull_request"] != args.pr_number
    ):
        raise RuntimeError("Lease: not for this pull request. Use its lease.")
    require_origin(args.repo)
    require_committed_lease(github, lease)
    release_refs(lease)


def authorization_template(args: argparse.Namespace, github: GitHub) -> None:
    """Print the exact statement a human maintainer may post."""
    lease = caller_lease(args, github)
    require_lease(github, lease, args.repo, args.pr_number, args.head_sha)
    sys.stdout.write(
        authorization_statement(args.repo, args.pr_number, args.head_sha)
    )


def issue_body_arguments(body_file: Path | None) -> list[str]:
    """Validate and return the optional GitHub CLI body arguments."""
    if body_file is None:
        return []
    if not body_file.is_file():
        raise RuntimeError("Issue body file: missing. Create it.")
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
        raise RuntimeError(
            "Issue: invalid identity. Pass a positive Issue number."
        )
    if (not values and not args.remove_type and args.body_file is None) or any(
        not value or "\n" in value for value in values
    ):
        raise RuntimeError(
            "Issue metadata: empty or multi-line. Pass one-line values."
        )
    issue = github.get(args.repo, f"issues/{args.issue_number}")
    if (
        not isinstance(issue, dict)
        or issue.get("number") != args.issue_number
        or issue.get("pull_request") is not None
    ):
        raise RuntimeError("Target: not a standalone Issue. Choose one.")
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
    known_methods = write_methods | {"get", "head", "options"}
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
        first_url = node.args[0] if node.args else keywords.get("url")
        if urllib_request:
            url_node = first_url
            method_node = keywords.get("method")
            if method_node is not None:
                resolved = ast_text(method_node, values)
                method = resolved.casefold() if resolved is not None else None
            elif "data" in keywords or len(node.args) > 1:
                method = "post"
            else:
                method = "get"
        elif urllib_urlopen:
            url_node = first_url
            method = (
                "post" if "data" in keywords or len(node.args) > 1 else "get"
            )
        elif leaf in known_methods:
            method = leaf
            url_node = first_url
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
        exposed = (
            lifecycle_target
            or root in {"httpx", "requests"}
            or unresolved_urllib
        )
        if method in write_methods and exposed:
            violations.append("Python HTTP client lifecycle mutation")
        elif method not in known_methods and exposed:
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
                ".csarc/scripts/pr_lifecycle.py",
                "template/.csarc/scripts/pr_lifecycle.py",
            }
        ),
    )


def dependabot_auto_merge_exemption(root: Path, path: Path) -> bool:
    """Trust the two exact dependabot-auto-merge.yml paths (see #602)."""
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
        *root.joinpath(".csarc/scripts").rglob("*"),
        *root.glob("template/.github/workflows/*.yml"),
        *root.glob("template/.github/workflows/*.yaml"),
        *root.joinpath("template/.csarc/scripts").rglob("*"),
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
                f"Automation file {relative}: not UTF-8. Save it as UTF-8."
            ) from error
        found = writer_violations(text)
        violations.extend(f"{relative}: {item}" for item in found)
    if violations:
        raise RuntimeError(
            "Unleased PR lifecycle writer: found.\n"
            + "\n".join(violations)
            + "\nRoute each write through 'pr_lifecycle.py'."
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
    trace = commands.add_parser("trace")
    trace.add_argument("--repo", required=True)
    trace.add_argument("--pr-number", required=True, type=int)
    trace.add_argument("--head-sha", required=True)
    trace.set_defaults(handler=trace_command)

    for name in (
        "state",
        "edit",
        "check",
        "merge",
        "authorization-template",
        "release",
        "recover",
    ):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        command.add_argument("--pr-number", required=True, type=int)
        if name == "recover":
            command.add_argument("--apply", action="store_true")
            command.set_defaults(handler=recover)
        else:
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
            command.add_argument(
                "--admin-bypass-marker",
                choices=("add", "remove"),
                help="insert or remove the one exact admin-bypass marker",
            )
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
        bootstrap_trusted_base(args)
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
        sys.stderr.write(f"ERROR: {error}\n")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
