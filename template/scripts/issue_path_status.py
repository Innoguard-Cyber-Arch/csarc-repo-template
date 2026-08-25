#!/usr/bin/env python3
"""Report the single safe next step for one live GitHub Issue."""

from __future__ import annotations

import argparse
import importlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from ci_tier import classify as classify_ci
from promotion_gate import (
    failed_pull_request_run_urls,
    quota_fallback_note,
    require_zero_step_run,
)

ISSUE_BRANCH = r"[a-z][a-z0-9-]*"
SUCCESSFUL_CONCLUSIONS = {"neutral", "skipped", "success"}
MAINTAINER_ASSOCIATIONS = {"MEMBER", "OWNER"}
BLOCKER = re.compile(
    r"(?i)^(?:blocked|blocker)\s*:|^\[merge-blocker\]|^\[P[01]\]"
)
BLOCKER_RESOLVED = re.compile(
    r"(?i)^merge blocker resolved\s*:|^\[merge-blocker-resolved\]"
)
UNCHECKED = re.compile(r"(?m)^\s*[-*+]\s+\[\s*\]")
QUOTA_NOTE = re.compile(r"\AActions quota fallback note\n\n`([^`\n]+)`\n\n")
DRAFT_FIELDS = (
    "Scope",
    "Completed verification",
    "Pending verification",
    "Known risks",
    "Dependencies / non-parallel work",
)
CLOSING_REFERENCE = re.compile(
    r"(?i)\b(?:close(?:s|d)?|fix(?:es|ed)?|resolve(?:s|d)?)\s+"
    r"(?:(?:https://github\.com/[\w.-]+/[\w.-]+/issues/)|"
    r"(?:[\w.-]+/[\w.-]+)?#)(\d+)(?!\d)"
)


@dataclass(frozen=True)
class Decision:
    """One reproducible issue-path decision."""

    schema_version: int
    repository: str
    issue: int
    state: str
    guard: str
    reason: str
    route: dict[str, object]
    risk: dict[str, object]
    capability: dict[str, object]
    pull_request: dict[str, object] | None
    observed_evidence: dict[str, object]
    allowed_actions: tuple[str, ...]
    required_evidence: tuple[str, ...]
    next_step: str


class GitHub:
    """Minimal GitHub CLI adapter restricted to explicit GET requests."""

    def _read(self, arguments: list[str]) -> object:
        executable = shutil.which("gh")
        if executable is None:
            raise RuntimeError("GitHub CLI is unavailable")
        result = subprocess.run(  # noqa: S603
            [executable, "api", "--method", "GET", *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"GitHub read failed: {detail}")
        return json.loads(result.stdout)

    def get(self, repo: str, path: str = "") -> object:
        """Read one repository REST resource."""
        endpoint = f"repos/{repo}"
        if path:
            endpoint = f"{endpoint}/{path.lstrip('/')}"
        return self._read([endpoint])

    def viewer(self, explicit_actor: str = "") -> str:
        """Read the authenticated user for the canonical lifecycle guard."""
        if explicit_actor:
            return explicit_actor
        payload = self._read(["user"])
        login = payload.get("login") if isinstance(payload, dict) else None
        if not isinstance(login, str) or not login:
            raise RuntimeError("Authenticated GitHub actor is unavailable")
        return login

    def pages(self, repo: str, path: str) -> list[dict[str, Any]]:
        """Read and flatten every page of one list resource."""
        payload = self._read(
            [
                "--paginate",
                "--slurp",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{repo}/{path.lstrip('/')}",
            ]
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"GitHub collection {path} is invalid")
        pages = (
            payload if payload and isinstance(payload[0], list) else [payload]
        )
        items = [item for page in pages for item in page]
        if not all(isinstance(item, dict) for item in items):
            raise RuntimeError(f"GitHub collection {path} is invalid")
        return items

    def keyed(self, repo: str, path: str, key: str) -> list[dict[str, Any]]:
        """Read a paginated object collection such as check runs."""
        return self.collection(repo, path, key)

    def collection(
        self,
        repo: str,
        path: str,
        key: str,
        response_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read a keyed collection for the canonical lifecycle guard."""
        payload = self._read(
            [
                "--paginate",
                "--slurp",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{repo}/{path.lstrip('/')}",
            ]
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"GitHub collection {path} is invalid")
        items: list[dict[str, Any]] = []
        for page in payload:
            entries = page.get(key) if isinstance(page, dict) else None
            if (
                response_sha is not None
                and isinstance(page, dict)
                and page.get("sha") != response_sha
            ):
                raise RuntimeError(
                    f"GitHub collection {path} is for another SHA"
                )
            if not isinstance(entries, list) or not all(
                isinstance(item, dict) for item in entries
            ):
                raise RuntimeError(f"GitHub collection {path} has no {key}")
            items.extend(entries)
        return items


class _Lifecycle(Protocol):
    """Read-only surface exported by the canonical #240 helper."""

    def effective_protection(
        self, github: GitHub, repo: str, branch: str
    ) -> tuple[str, str, set[tuple[str, int | None]]]: ...

    def read_lease(self, path: Path) -> dict[str, Any]: ...

    def require_caller(
        self,
        lease: dict[str, Any],
        owner: str,
        actor: str,
        github: GitHub,
    ) -> None: ...

    def merge_snapshot(
        self,
        github: GitHub,
        lease: dict[str, Any],
        authorization_url: str,
    ) -> dict[str, object]: ...


def labels(payload: dict[str, Any]) -> set[str]:
    """Normalize REST labels."""
    return {
        str(label["name"])
        for label in payload.get("labels", [])
        if isinstance(label, dict) and isinstance(label.get("name"), str)
    }


def route_for(  # noqa: C901
    issue: dict[str, Any],
    branches: dict[str, str],
    branch_strategy: str = "delivery",
) -> dict[str, object]:
    """Select the only route allowed by Issue metadata and live refs."""
    issue_number = issue.get("number")
    if not isinstance(issue_number, int):
        return {
            "kind": "unknown",
            "valid": False,
            "reason": "Issue number is missing",
        }
    issue_labels = labels(issue)
    milestone = issue.get("milestone")
    milestone_number = (
        milestone.get("number") if isinstance(milestone, dict) else None
    )
    if milestone is not None and not isinstance(milestone_number, int):
        return {
            "kind": "unknown",
            "valid": False,
            "reason": "Issue Milestone identity is malformed",
        }

    if "hotfix" in issue_labels:
        if milestone_number is not None:
            return {
                "kind": "hotfix",
                "valid": False,
                "reason": "A hotfix Issue must be standalone",
            }
        return {
            "kind": "hotfix",
            "valid": "main" in branches,
            "base": "main",
            "head_pattern": f"fix/{issue_number}-*",
            "reason": "explicit hotfix label",
        }

    if branch_strategy == "main":
        return {
            "kind": "main",
            "valid": "main" in branches,
            "base": "main",
            "head_pattern": f"type/{issue_number}-*",
            "reason": "repository profile selects main",
        }

    if branch_strategy == "dev":
        promotion = "promotion" in issue_labels
        return {
            "kind": "dev-promotion" if promotion else "dev",
            "valid": "main" in branches and "dev" in branches,
            "base": "main" if promotion else "dev",
            "head": "dev" if promotion else None,
            "head_pattern": None if promotion else f"type/{issue_number}-*",
            "reason": "repository profile selects dev",
        }

    if branch_strategy != "delivery":
        return {
            "kind": "unknown",
            "valid": False,
            "reason": f"unknown branch strategy: {branch_strategy}",
        }

    if "promotion" in issue_labels:
        if isinstance(milestone_number, int):
            candidates = sorted(
                branch
                for branch in branches
                if re.fullmatch(
                    rf"dev/m{milestone_number}-[a-z0-9][a-z0-9-]*", branch
                )
            )
            kind = "milestone-promotion"
        else:
            candidates = sorted(
                branch
                for branch in branches
                if re.fullmatch(
                    rf"dev/i{issue_number}-[a-z0-9][a-z0-9-]*", branch
                )
            )
            kind = "isolated-promotion"
        return _unique_route(kind, "main", candidates, branches)

    if isinstance(milestone_number, int):
        candidates = sorted(
            branch
            for branch in branches
            if re.fullmatch(
                rf"dev/m{milestone_number}-[a-z0-9][a-z0-9-]*", branch
            )
        )
        return _unique_route("milestone", "", candidates, branches)

    return {
        "kind": "standalone",
        "valid": "dev/next" in branches,
        "base": "dev/next",
        "head_pattern": f"type/{issue_number}-*",
        "reason": (
            "standalone Issues use dev/next"
            if "dev/next" in branches
            else "required branch dev/next is missing"
        ),
    }


def _unique_route(
    kind: str,
    fixed_base: str,
    candidates: list[str],
    branches: dict[str, str],
) -> dict[str, object]:
    """Build a route only when its delivery branch is unambiguous."""
    if len(candidates) != 1:
        return {
            "kind": kind,
            "valid": False,
            "reason": (
                f"expected one live delivery branch, found {len(candidates)}"
            ),
            "candidates": candidates,
        }
    delivery = candidates[0]
    promotion = bool(fixed_base)
    return {
        "kind": kind,
        "valid": fixed_base in branches if promotion else True,
        "base": fixed_base or delivery,
        "head": delivery if promotion else None,
        "head_pattern": None if promotion else "type/<issue>-*",
        "delivery": delivery,
        "reason": "route derived from the live Issue and delivery ref",
    }


def linked_pull(
    pull: dict[str, Any],
    issue_number: int,
    native_links: set[int],
    route: dict[str, object],
) -> bool:
    """Use native cross-references, explicit body links, or the issue branch."""
    body = str(pull.get("body") or "")
    reference = re.compile(
        rf"(?i)(?:closes|fixes|resolves|refs?)\s+(?:[\w.-]+/[\w.-]+)?#{issue_number}(?!\d)"
    )
    number = pull.get("number")
    related = (
        isinstance(number, int) and number in native_links
    ) or reference.search(body) is not None
    head = pull.get("head") or {}
    head_ref = str(head.get("ref") or "")
    branch_related = (
        re.fullmatch(
            rf"{ISSUE_BRANCH}/{issue_number}-[a-z0-9][a-z0-9-]*",
            head_ref,
        )
        is not None
    )
    return related or branch_related


def base_chain(
    pull: dict[str, Any],
    pulls: list[dict[str, Any]],
    expected_base: str,
    repo: str,
) -> tuple[bool, list[str], str]:
    """Follow one unique open PR chain to the expected integration ref."""
    current = pull
    chain: list[str] = []
    visited: set[str] = set()
    while True:
        head = current.get("head") or {}
        base = current.get("base") or {}
        head_ref = head.get("ref")
        base_ref = base.get("ref")
        head_repo = head.get("repo") or {}
        if (
            not isinstance(head_ref, str)
            or not isinstance(base_ref, str)
            or head_repo.get("full_name") != repo
        ):
            return False, chain, "PR chain identity is incomplete or external"
        if head_ref in visited:
            return False, chain, "PR base chain contains a cycle"
        visited.add(head_ref)
        chain.append(head_ref)
        if base_ref == expected_base:
            chain.append(base_ref)
            return (
                True,
                chain,
                "PR chain reaches the expected integration branch",
            )
        parents = [
            candidate
            for candidate in pulls
            if candidate.get("state") == "open"
            and (candidate.get("head") or {}).get("ref") == base_ref
            and (candidate.get("head") or {}).get("repo", {}).get("full_name")
            == repo
        ]
        if len(parents) != 1:
            return (
                False,
                chain,
                f"PR base {base_ref} has {len(parents)} open parent PRs",
            )
        current = parents[0]
        if len(chain) > len(pulls) + 1:
            return False, chain, "PR base chain exceeded its safe depth"


def merged_base_chain(
    pull: dict[str, Any],
    pulls: list[dict[str, Any]],
    expected_base: str,
    repo: str,
) -> tuple[
    bool,
    list[str],
    str,
    dict[str, Any],
    list[tuple[str, str]],
]:
    """Follow merged stacked parents to the expected integration ref."""
    current = pull
    chain: list[str] = []
    visited: set[str] = set()
    containment: list[tuple[str, str]] = []
    while True:
        head = current.get("head") or {}
        base = current.get("base") or {}
        head_ref = head.get("ref")
        base_ref = base.get("ref")
        head_repo = head.get("repo") or {}
        if (
            not isinstance(head_ref, str)
            or not isinstance(base_ref, str)
            or head_repo.get("full_name") != repo
            or not current.get("merged_at")
        ):
            return (
                False,
                chain,
                "Merged PR chain identity is incomplete or external",
                current,
                containment,
            )
        if head_ref in visited:
            return (
                False,
                chain,
                "Merged PR base chain contains a cycle",
                current,
                containment,
            )
        visited.add(head_ref)
        chain.append(head_ref)
        if base_ref == expected_base:
            chain.append(base_ref)
            return (
                True,
                chain,
                "Merged PR chain reaches the expected integration branch",
                current,
                containment,
            )
        parents = [
            candidate
            for candidate in pulls
            if candidate.get("merged_at")
            and (candidate.get("head") or {}).get("ref") == base_ref
            and (candidate.get("head") or {}).get("repo", {}).get("full_name")
            == repo
        ]
        if len(parents) != 1:
            return (
                False,
                chain,
                f"Merged PR base {base_ref} has {len(parents)} merged parent "
                "PRs",
                current,
                containment,
            )
        parent = parents[0]
        if str(parent.get("merged_at")) < str(current.get("merged_at")):
            return (
                False,
                chain,
                "Stacked parent merged before its child",
                current,
                containment,
            )
        child_merge_sha = current.get("merge_commit_sha")
        parent_head_sha = (parent.get("head") or {}).get("sha")
        if not isinstance(child_merge_sha, str) or not isinstance(
            parent_head_sha, str
        ):
            return (
                False,
                chain,
                "Merged stack lacks immutable child containment identities",
                current,
                containment,
            )
        containment.append((child_merge_sha, parent_head_sha))
        current = parent
        if len(chain) > len(pulls) + 1:
            return (
                False,
                chain,
                "Merged PR base chain exceeded its safe depth",
                current,
                containment,
            )


def risk_for(route: dict[str, object], files: list[str]) -> dict[str, object]:
    """Map the canonical CI plan to the #264 risk classes."""
    promotion = route.get("kind") in {
        "hotfix",
        "milestone-promotion",
        "isolated-promotion",
        "dev-promotion",
    }
    issue_labels = {"promotion"} if promotion else set()
    if route.get("kind") == "hotfix":
        issue_labels = {"hotfix"}
    plan = classify_ci(
        "pull_request",
        str(route.get("base") or ""),
        str(route.get("head") or "issue-branch"),
        issue_labels,
        files,
    )
    scopes = list(plan.scopes)
    if promotion:
        return {
            "class": "promotion",
            "ci_tier": plan.tier,
            "scopes": scopes,
            "verification": ["full", "promotion", "tree-identity"],
        }
    elevated_scopes = {
        "workflow",
        "governance",
        "dependency",
        "template",
        "unknown",
    }
    elevated = (
        not files
        or bool(set(scopes) & elevated_scopes)
        or any(
            any(
                word in path.casefold()
                for word in ("security", "release", "promotion")
            )
            for path in files
        )
    )
    verification = [plan.tier]
    if plan.run_zizmor:
        verification.append("zizmor")
    if plan.run_osv:
        verification.append("osv")
    if plan.run_governance:
        verification.append("remote-governance")
    return {
        "class": "unknown"
        if not files
        else ("elevated" if elevated else "routine"),
        "ci_tier": plan.tier,
        "scopes": scopes,
        "verification": verification,
    }


def unresolved_blocker(
    comments: list[dict[str, Any]], reviews: list[dict[str, Any]]
) -> str | None:
    """Return the newest unresolved maintainer blocker URL."""
    blocker: tuple[str, str] | None = None
    resolved = ""
    for comment in comments:
        if comment.get("author_association") not in MAINTAINER_ASSOCIATIONS:
            continue
        created = str(comment.get("created_at") or "")
        body = str(comment.get("body") or "").lstrip()
        if BLOCKER_RESOLVED.search(body) and created > resolved:
            resolved = created
        elif BLOCKER.search(body) and (
            blocker is None or created >= blocker[0]
        ):
            blocker = (created, str(comment.get("html_url") or "unknown URL"))
    if blocker is not None and blocker[0] >= resolved:
        return blocker[1]
    current: dict[str, tuple[str, str, str]] = {}
    for review in sorted(
        reviews, key=lambda item: str(item.get("submitted_at") or "")
    ):
        user = review.get("user") or {}
        login = user.get("login")
        state = review.get("state")
        if isinstance(login, str) and state in {
            "APPROVED",
            "CHANGES_REQUESTED",
            "DISMISSED",
        }:
            current[login.casefold()] = (
                str(state),
                str(review.get("submitted_at") or ""),
                str(review.get("html_url") or "unknown URL"),
            )
    requested = [
        value for value in current.values() if value[0] == "CHANGES_REQUESTED"
    ]
    return max(requested, key=lambda value: value[1])[2] if requested else None


def has_human_approval(
    reviews: list[dict[str, Any]], author: str, head_sha: str
) -> bool:
    """Require a current independent human maintainer approval."""
    current: dict[str, tuple[str, str, str, str, str]] = {}
    for review in sorted(
        reviews, key=lambda item: str(item.get("submitted_at") or "")
    ):
        user = review.get("user") or {}
        login = user.get("login")
        state = review.get("state")
        if isinstance(login, str) and state in {
            "APPROVED",
            "CHANGES_REQUESTED",
            "DISMISSED",
        }:
            current[login.casefold()] = (
                str(state),
                str(user.get("type") or ""),
                str(review.get("author_association") or ""),
                login,
                str(review.get("commit_id") or ""),
            )
    return any(
        state == "APPROVED"
        and user_type == "User"
        and association in MAINTAINER_ASSOCIATIONS
        and login.casefold() != author.casefold()
        and commit_id == head_sha
        for state, user_type, association, login, commit_id in current.values()
    )


def has_exact_quota_note(
    comments: list[dict[str, Any]],
    repo: str,
    pull_number: int,
    head_sha: str,
    run_urls: list[str],
) -> bool:
    """Accept one canonical #254 note bound to all live failed runs."""
    matching = 0
    for comment in comments:
        match = QUOTA_NOTE.match(str(comment.get("body") or ""))
        if match is None:
            continue
        try:
            binding = json.loads(match.group(1))
        except json.JSONDecodeError:
            return False
        verification = (
            binding.get("verification") if isinstance(binding, dict) else None
        )
        if (
            isinstance(binding, dict)
            and set(binding)
            == {
                "repository",
                "pull_request",
                "head_sha",
                "runs",
                "verification",
            }
            and binding.get("repository") == repo
            and binding.get("pull_request") == pull_number
            and binding.get("head_sha") == head_sha
            and binding.get("runs") == sorted(run_urls)
            and isinstance(verification, dict)
            and verification.get("command")
            in {"./scripts/verify", "./scripts/verify-template.sh"}
            and verification.get("result") == "passed"
            and isinstance(verification.get("unreproduced_checks"), list)
            and all(
                isinstance(item, str)
                for item in verification["unreproduced_checks"]
            )
            and set(verification)
            == {"command", "result", "unreproduced_checks"}
            and str(comment.get("body"))
            == quota_fallback_note(
                repo,
                pull_number,
                head_sha,
                run_urls,
                str(verification["command"]),
                verification["unreproduced_checks"],
            )
        ):
            matching += 1
    return matching == 1


def pull_contract_problem(
    issue: dict[str, Any], pull: dict[str, Any]
) -> tuple[str, str] | None:
    """Return the first #261 Draft/Ready contract violation."""
    issue_number = int(issue["number"])
    issue_body = str(issue.get("body") or "")
    body = str(pull.get("body") or "")
    closing = [int(number) for number in CLOSING_REFERENCE.findall(body)]
    if len(closing) > 1 or any(number != issue_number for number in closing):
        return (
            "The pull request has multiple or mismatched closing references",
            f"Keep only the primary Issue #{issue_number} reference, then "
            "rerun status.",
        )
    incomplete = UNCHECKED.search(issue_body) or UNCHECKED.search(body)
    if pull.get("draft"):
        missing = [
            field
            for field in DRAFT_FIELDS
            if re.search(rf"(?m)^\s*-\s+{re.escape(field)}:\s+\S", body) is None
        ]
        if missing:
            return (
                "Draft ownership fields are missing or blank: "
                + ", ".join(missing),
                "Fill every Draft ownership field, then rerun status.",
            )
        if closing and incomplete:
            return (
                "An incomplete Draft uses a closing keyword",
                f"Change the Issue #{issue_number} link to Refs, then rerun "
                "status.",
            )
        return None
    if closing != [issue_number]:
        return (
            "A Ready pull request needs one closing reference to its Issue",
            f"Use exactly one Closes #{issue_number} reference, then rerun "
            "status.",
        )
    if incomplete:
        return (
            "The Issue or Ready pull request still has unchecked work",
            "Complete the unchecked acceptance item or return the PR to "
            "Draft, then rerun status.",
        )
    return None


def check_state(
    runs: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
    required: set[tuple[str, int | None]],
) -> str:
    """Classify exact-head checks without inventing a passing result."""
    if not runs and not statuses:
        return "missing"
    if any(status.get("state") != "success" for status in statuses):
        return "failed"
    passing_runs = {
        (str(run.get("name")), (run.get("app") or {}).get("id"))
        for run in runs
        if run.get("status") == "completed"
        and run.get("conclusion") in SUCCESSFUL_CONCLUSIONS
    }
    passing_statuses = {
        str(status.get("context"))
        for status in statuses
        if status.get("state") == "success"
    }
    missing = {
        (context, integration_id)
        for context, integration_id in required
        if (context, integration_id) not in passing_runs
        and not (integration_id is None and context in passing_statuses)
    }
    if missing:
        return "failed"
    if any(run.get("status") != "completed" for run in runs):
        return "pending"
    if any(run.get("conclusion") not in SUCCESSFUL_CONCLUSIONS for run in runs):
        return "failed"
    return "passing"


def derive_status(observation: dict[str, Any]) -> Decision:  # noqa: C901
    """Derive a durable state and exactly one safe next step."""
    repo = str(observation["repository"])
    issue = observation["issue"]
    issue_number = int(issue["number"])
    branches = observation["branches"]
    branch_strategy = str(observation.get("branch_strategy", "delivery"))
    route = route_for(issue, branches, branch_strategy)
    capability = observation.get(
        "capability",
        {"state": "unknown", "reason": "not inspected", "required": []},
    )
    risk = risk_for(route, observation.get("files", []))
    required = (
        "Issue acceptance and exact-head targeted results",
        "exact-head full local verification before Ready",
        "live source and destination refs",
        "review, required checks, and blocker state",
    )

    def decision(
        state: str,
        guard: str,
        reason: str,
        next_step: str,
        pull: dict[str, Any] | None = None,
        actions: tuple[str, ...] = ("inspect",),
    ) -> Decision:
        public_pull = None
        if pull is not None:
            public_pull = {
                "number": pull.get("number"),
                "url": pull.get("html_url"),
                "draft": pull.get("draft"),
                "base": (pull.get("base") or {}).get("ref"),
                "base_sha": (pull.get("base") or {}).get("sha"),
                "head": (pull.get("head") or {}).get("ref"),
                "head_sha": (pull.get("head") or {}).get("sha"),
            }
        evidence = {
            "delivery_sha": branches.get(str(route.get("base") or "")),
            "immediate_base_sha": (
                branches.get(str((pull.get("base") or {}).get("ref") or ""))
                if pull is not None
                else None
            ),
            "head_sha": (
                (pull.get("head") or {}).get("sha")
                if pull is not None
                else None
            ),
            "checks": observation.get("checks", "not-applicable"),
            "blocked_run_urls": observation.get("blocked_run_urls", []),
            "blocker": observation.get("blocker"),
            "post_merge_verified": bool(observation.get("post_merge_verified")),
            "human_approval": bool(observation.get("human_approval")),
            "quota_note": bool(observation.get("quota_note")),
            "base_chain": observation.get("base_chain", []),
            "merged_route": observation.get("merged_route"),
        }
        return Decision(
            1,
            repo,
            issue_number,
            state,
            guard,
            reason,
            route,
            risk,
            capability,
            public_pull,
            evidence,
            actions,
            required,
            next_step,
        )

    if not route.get("valid"):
        return decision(
            "Open",
            "blocked",
            str(route.get("reason")),
            "Create or restore exactly one policy-named delivery branch, "
            "then rerun status.",
        )

    pulls = [
        pull
        for pull in observation.get("pulls", [])
        if linked_pull(
            pull, issue_number, observation.get("native_links", set()), route
        )
    ]
    open_pulls = [pull for pull in pulls if pull.get("state") == "open"]
    if len(open_pulls) > 1:
        return decision(
            "Open",
            "blocked",
            "More than one open pull request claims this Issue",
            "Coordinate ownership and close or unlink every duplicate PR, "
            "then rerun status.",
        )
    work_branches = observation.get("work_branches", [])
    if len(work_branches) > 1:
        return decision(
            "Open",
            "blocked",
            "More than one remote work branch claims this Issue",
            "Coordinate ownership and retain exactly one work branch, then "
            "rerun status.",
        )

    if not open_pulls:
        merged = [pull for pull in pulls if pull.get("merged_at")]
        if merged:
            latest = max(merged, key=lambda item: str(item.get("merged_at")))
            merged_routes = observation.get("merged_routes", {})
            merged_route = merged_routes.get(str(latest.get("number")))
            if not isinstance(merged_route, dict) or not merged_route.get(
                "valid"
            ):
                reason = (
                    merged_route.get("reason")
                    if isinstance(merged_route, dict)
                    else "Merged route evidence was not collected"
                )
                return decision(
                    "Candidate",
                    "blocked",
                    str(reason),
                    "Confirm the merged PR chain and commit are contained in "
                    f"{route['base']}, then rerun status.",
                    latest,
                )
            observation["base_chain"] = merged_route.get("chain", [])
            observation["merged_route"] = merged_route
            promotion = route.get("base") == "main"
            if promotion and not observation.get("post_merge_verified"):
                return decision(
                    "Candidate",
                    "blocked",
                    "A main merge exists without successful post-merge tree "
                    "evidence",
                    "Run or repair the exact-merge post-merge promotion check, "
                    "then rerun status.",
                    latest,
                )
            return decision(
                "Delivered" if promotion else "Integrated",
                "clear",
                "The linked pull request is merged into the policy route",
                (
                    "Verify the post-merge main evidence and release boundary."
                    if promotion
                    else (
                        "Wait for the delivery owner to create or advance "
                        "the promotion candidate."
                    )
                ),
                latest,
                ("inspect", "verify-post-merge") if promotion else ("inspect",),
            )
        if issue.get("state") != "open":
            return decision(
                "Open",
                "blocked",
                "The Issue is closed without a linked merged pull request",
                "Reopen the Issue or link its actual merged PR, then rerun "
                "status.",
            )
        branch = work_branches[0] if work_branches else None
        if branch:
            return decision(
                "Open",
                "blocked",
                "A remote work branch exists without visible Draft ownership",
                f"Open one Draft PR from {branch} to {route['base']} and "
                f"reference Issue #{issue_number}.",
            )
        return decision(
            "Open",
            "clear",
            "No live PR or work branch claims this Issue",
            f"Create one issue branch from {route['base']}, run a targeted "
            "check, and open a Draft PR.",
            actions=("create-branch", "open-draft"),
        )

    pull = open_pulls[0]
    base = pull.get("base") or {}
    head = pull.get("head") or {}
    head_repo = head.get("repo") or {}
    if head_repo.get("full_name") != repo:
        return decision(
            "Draft" if pull.get("draft") else "Ready",
            "blocked",
            "The pull request head is not owned by this repository",
            "Move the work to a repository-owned issue branch, then rerun "
            "status.",
            pull,
        )
    head_ref = str(head.get("ref") or "")
    expected_head = route.get("head")
    if (
        isinstance(expected_head, str)
        and expected_head
        and head_ref != expected_head
    ) or (
        route.get("kind") == "hotfix"
        and re.fullmatch(rf"fix/{issue_number}-[a-z0-9][a-z0-9-]*", head_ref)
        is None
    ):
        expected = expected_head or f"fix/{issue_number}-*"
        return decision(
            "Draft" if pull.get("draft") else "Ready",
            "blocked",
            f"The pull request head does not match the {route['kind']} route",
            f"Move the work to {expected}, then rerun status.",
            pull,
        )
    all_pulls = observation.get("all_pulls", observation.get("pulls", []))
    chain_valid, chain, chain_reason = base_chain(
        pull, all_pulls, str(route["base"]), repo
    )
    observation["base_chain"] = chain
    if not chain_valid:
        return decision(
            "Draft" if pull.get("draft") else "Ready",
            "blocked",
            chain_reason,
            f"Repair the unique open PR chain so it ends at {route['base']}, "
            "then rerun status.",
            pull,
        )
    if (
        base.get("sha") != branches.get(str(base.get("ref") or ""))
        or observation.get("base_current") is False
    ):
        return decision(
            "Draft" if pull.get("draft") else "Ready",
            "blocked",
            "The pull request base snapshot drifted from its live parent",
            f"Sync {base.get('ref')} into the work branch through the reviewed "
            "path, then rerun checks.",
            pull,
        )
    if head.get("sha") != branches.get(head_ref):
        return decision(
            "Draft" if pull.get("draft") else "Ready",
            "blocked",
            "The pull request head differs from the live branch ref",
            f"Refresh PR #{pull['number']} at the live head and rerun status.",
            pull,
        )
    blocker = observation.get("blocker")
    if blocker:
        return decision(
            "Draft" if pull.get("draft") else "Ready",
            "blocked",
            f"A newer unresolved blocker exists: {blocker}",
            "Ask the blocker owner to resolve it explicitly, then rerun "
            "status.",
            pull,
        )
    contract_problem = pull_contract_problem(issue, pull)
    if contract_problem is not None:
        reason, next_step = contract_problem
        return decision(
            "Draft" if pull.get("draft") else "Ready",
            "blocked",
            reason,
            next_step,
            pull,
        )
    if pull.get("draft"):
        return decision(
            "Draft",
            "clear",
            "Visible Draft ownership is active",
            "Complete acceptance, targeted checks, and exact-head full local "
            "verification, then mark Ready.",
            pull,
            ("update-draft", "run-targeted", "run-full-local"),
        )

    checks = str(observation.get("checks", "missing"))
    if checks == "quota-blocked" and risk["class"] == "routine":
        run_arguments = " ".join(
            f"--blocked-run-url {url}"
            for url in observation.get("blocked_run_urls", [])
        )
        if not observation.get("quota_note"):
            return decision(
                "Ready",
                "blocked",
                "Every failed exact-head Actions run is a confirmed zero-step "
                "billing block, but its one fallback note is missing",
                (
                    "On the exact PR head run ./scripts/promotion_gate.py "
                    f"note-quota-fallback --repo {repo} --pr "
                    f"{pull['number']} --branch-strategy {branch_strategy} "
                    f"{run_arguments}; publish its single SHA-bound note, "
                    "then rerun status."
                ),
                pull,
                ("run-local-quota-fallback",),
            )
        checks = "accepted-routine-quota-fallback"
    elif checks == "quota-blocked":
        fallback = (
            "Use the existing promotion quota attestation and independent "
            "human authorization flow, then rerun status."
            if risk["class"] == "promotion"
            else (
                "Ask an independent human maintainer to evaluate the "
                "exact-head elevated quota fallback, then rerun status."
            )
        )
        return decision(
            "Ready",
            "blocked",
            f"{risk['class']} work cannot use the routine quota note",
            fallback,
            pull,
        )
    if checks not in {"passing", "accepted-routine-quota-fallback"}:
        return decision(
            "Ready",
            "blocked",
            f"Exact-head required checks are {checks}",
            "Run or repair the required checks on the exact head, then "
            "rerun status.",
            pull,
            ("run-checks",),
        )
    if risk["class"] in {"elevated", "promotion"} and not observation.get(
        "human_approval"
    ):
        return decision(
            "Ready",
            "blocked",
            f"{risk['class']} work has no current independent human approval",
            "Obtain an approving review from an independent human maintainer, "
            "then rerun status.",
            pull,
        )
    if capability.get("state") == "available":
        return decision(
            "Ready",
            "blocked",
            "The canonical lifecycle guard is available but no lease is held",
            "Run ./scripts/pr_lifecycle.py acquire "
            f"--repo {repo} --pr-number {pull['number']} --head-sha "
            f"{head.get('sha')} --owner <task-owner> --output <lease.json>; "
            "obtain its exact authorization comment, then rerun status with "
            "--lease, --owner, and --authorization-url.",
            pull,
            ("acquire-lease",),
        )
    if capability.get("state") != "allowed":
        return decision(
            "Ready",
            "blocked",
            "Single-writer repository capability is "
            f"{capability.get('state', 'unknown')}",
            "Ask a maintainer to restore or confirm the lifecycle guard; use "
            "human-only merge if policy permits.",
            pull,
        )
    return decision(
        "Candidate" if route.get("base") == "main" else "Ready",
        "clear",
        "Route, refs, blockers, required checks, and single-writer capability "
        "are current",
        "Acquire the lifecycle lease for this exact head and perform the one "
        "authorized merge attempt.",
        pull,
        ("acquire-lease", "merge-once"),
    )


def _branch_map(items: list[dict[str, Any]]) -> dict[str, str]:
    """Normalize branch names and commit SHAs."""
    result: dict[str, str] = {}
    for item in items:
        name = item.get("name")
        sha = (item.get("commit") or {}).get("sha")
        if isinstance(name, str) and isinstance(sha, str):
            result[name] = sha
    return result


def _native_links(timeline: list[dict[str, Any]]) -> set[int]:
    """Extract PR numbers from native Issue cross-reference events."""
    result: set[int] = set()
    for item in timeline:
        source = item.get("source") or {}
        linked = source.get("issue") or {}
        if isinstance(linked.get("pull_request"), dict) and isinstance(
            linked.get("number"), int
        ):
            result.add(linked["number"])
    return result


def local_branch_strategy() -> str:
    """Read the checked-in repository profile, defaulting only for this root."""
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


def local_repository() -> str:
    """Resolve the repository identity from the read-only origin URL."""
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git is unavailable; pass --repo")
    result = subprocess.run(  # noqa: S603
        [executable, "remote", "get-url", "origin"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Git origin is unavailable; pass --repo")
    url = result.stdout.strip()
    match = re.fullmatch(
        r"(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)"
        r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?",
        url,
    )
    if match is None:
        raise RuntimeError(
            "Git origin is not a github.com repository; pass --repo"
        )
    return match.group(1)


def inspect_capability(  # noqa: C901
    github: GitHub,
    repo: str,
    repository: dict[str, Any],
    pull: dict[str, Any],
    lease: Path | None = None,
    owner: str | None = None,
    authorization_url: str | None = None,
    lifecycle_module: _Lifecycle | None = None,
) -> dict[str, object]:
    """Delegate read-only capability proof to the canonical #240 guard."""
    permissions = repository.get("permissions") or {}
    if permissions.get("push") is not True:
        return {
            "state": (
                "blocked" if permissions.get("push") is False else "unknown"
            ),
            "reason": "caller push capability is unavailable",
            "required": [],
        }
    base = pull.get("base") or {}
    head = pull.get("head") or {}
    base_ref = base.get("ref")
    base_sha = base.get("sha")
    head_sha = head.get("sha")
    pull_number = pull.get("number")
    if not all(
        (
            isinstance(base_ref, str),
            isinstance(base_sha, str),
            isinstance(head_sha, str),
            isinstance(pull_number, int),
        )
    ):
        return {
            "state": "unknown",
            "reason": "pull request identity is incomplete",
            "required": [],
        }
    base_name = cast(str, base_ref)
    base_commit = cast(str, base_sha)
    head_commit = cast(str, head_sha)
    number = cast(int, pull_number)
    try:
        lifecycle_file = github.get(
            repo, f"contents/scripts/pr_lifecycle.py?ref={base_commit}"
        )
    except RuntimeError as error:
        return {"state": "unknown", "reason": str(error), "required": []}
    if (
        not isinstance(lifecycle_file, dict)
        or lifecycle_file.get("type") != "file"
        or lifecycle_file.get("path") != "scripts/pr_lifecycle.py"
        or not isinstance(lifecycle_file.get("sha"), str)
    ):
        return {
            "state": "unknown",
            "reason": "canonical lifecycle script is unavailable on the base",
            "required": [],
        }
    if lifecycle_module is None:
        path = Path(__file__).with_name("pr_lifecycle.py")
        if not path.is_file():
            return {
                "state": "unknown",
                "reason": "canonical local lifecycle interface is unavailable",
                "required": [],
            }
        executable = shutil.which("git")
        if executable is None:
            return {
                "state": "unknown",
                "reason": "Git is unavailable for lifecycle identity proof",
                "required": [],
            }
        blob = subprocess.run(  # noqa: S603
            [executable, "hash-object", str(path)],
            text=True,
            capture_output=True,
            check=False,
        )
        if blob.returncode or blob.stdout.strip() != lifecycle_file.get("sha"):
            return {
                "state": "unknown",
                "reason": "local lifecycle helper differs from the base",
                "required": [],
            }
        try:
            imported = importlib.import_module("pr_lifecycle")
        except ImportError as error:
            return {"state": "unknown", "reason": str(error), "required": []}
        module_file = getattr(imported, "__file__", None)
        if not isinstance(module_file, str) or Path(module_file).resolve() != (
            path.resolve()
        ):
            return {
                "state": "unknown",
                "reason": "canonical local lifecycle interface is ambiguous",
                "required": [],
            }
        lifecycle_module = cast(_Lifecycle, imported)
    functions = (
        "effective_protection",
        "read_lease",
        "require_caller",
        "merge_snapshot",
    )
    if any(
        not callable(getattr(lifecycle_module, name, None))
        for name in functions
    ):
        return {
            "state": "unknown",
            "reason": "canonical lifecycle read-only interface is incomplete",
            "required": [],
        }
    try:
        protection, reason, required = lifecycle_module.effective_protection(
            github, repo, base_name
        )
    except RuntimeError as error:
        return {"state": "unknown", "reason": str(error), "required": []}
    required_output = [
        {"context": context, "integration_id": integration_id}
        for context, integration_id in sorted(
            required, key=lambda item: (item[0], item[1] or -1)
        )
    ]
    if protection != "enforced":
        return {
            "state": "blocked" if protection == "blocked" else "unknown",
            "reason": str(reason),
            "required": required_output,
        }
    supplied = (lease is not None, bool(owner), bool(authorization_url))
    if not any(supplied):
        return {
            "state": "available",
            "reason": (
                "canonical #240 lease guard is available but not acquired"
            ),
            "required": required_output,
        }
    if not all(supplied):
        return {
            "state": "blocked",
            "reason": (
                "lease, owner, and authorization URL must be supplied together"
            ),
            "required": required_output,
        }
    lease_path = cast(Path, lease)
    owner_name = cast(str, owner)
    authorization = cast(str, authorization_url)
    try:
        lease_payload = lifecycle_module.read_lease(lease_path)
        lifecycle_module.require_caller(lease_payload, owner_name, "", github)
        snapshot = lifecycle_module.merge_snapshot(
            github, lease_payload, authorization
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        return {
            "state": "blocked",
            "reason": f"canonical lifecycle check failed: {error}",
            "required": required_output,
        }
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("repository") != repo
        or snapshot.get("pull_request") != number
        or snapshot.get("head_sha") != head_commit
        or snapshot.get("base_ref") != base_name
        or snapshot.get("base_sha") != base_commit
        or snapshot.get("authorization_url") != authorization
        or snapshot.get("merge_mode") != "agent"
    ):
        return {
            "state": "blocked",
            "reason": "canonical lifecycle snapshot does not authorize this PR",
            "required": required_output,
        }
    return {
        "state": "allowed",
        "reason": "canonical lease and exact merge authorization are current",
        "required": required_output,
        "authorization_url": authorization_url,
    }


def inspect_issue(  # noqa: C901
    github: GitHub,
    repo: str,
    issue_number: int,
    branch_strategy: str,
    lease: Path | None = None,
    owner: str | None = None,
    authorization_url: str | None = None,
) -> Decision:
    """Read live GitHub state once and derive one safe next step."""
    repository = github.get(repo)
    issue = github.get(repo, f"issues/{issue_number}")
    if (
        not isinstance(repository, dict)
        or not isinstance(issue, dict)
        or "pull_request" in issue
    ):
        raise RuntimeError(
            "Requested Issue is unavailable or is a pull request"
        )
    branches = _branch_map(github.pages(repo, "branches?per_page=100"))
    pulls = github.pages(repo, "pulls?state=all&per_page=100")
    timeline = github.pages(
        repo, f"issues/{issue_number}/timeline?per_page=100"
    )
    route = route_for(issue, branches, branch_strategy)
    native_links = _native_links(timeline)
    related = [
        pull
        for pull in pulls
        if linked_pull(pull, issue_number, native_links, route)
    ]
    open_pulls = [pull for pull in related if pull.get("state") == "open"]
    work_pattern = re.compile(
        rf"{ISSUE_BRANCH}/{issue_number}-[a-z0-9][a-z0-9-]*"
    )
    observation: dict[str, Any] = {
        "repository": repo,
        "branch_strategy": branch_strategy,
        "issue": issue,
        "branches": branches,
        "pulls": related,
        "all_pulls": pulls,
        "native_links": native_links,
        "work_branches": sorted(
            branch for branch in branches if work_pattern.fullmatch(branch)
        ),
        "files": [],
        "checks": "missing",
        "capability": {
            "state": "unknown",
            "reason": "no active PR",
            "required": [],
        },
    }
    if not open_pulls and route.get("valid"):
        merged = [pull for pull in related if pull.get("merged_at")]
        merged_routes: dict[str, dict[str, object]] = {}
        for candidate in merged:
            valid, chain, reason, terminal, containment = merged_base_chain(
                candidate, pulls, str(route["base"]), repo
            )
            merge_sha = terminal.get("merge_commit_sha")
            if valid and isinstance(merge_sha, str):
                try:
                    proofs = [
                        *containment,
                        (merge_sha, branches[str(route["base"])]),
                    ]
                    for ancestor, descendant in proofs:
                        comparison = github.get(
                            repo, f"compare/{ancestor}...{descendant}"
                        )
                        if not isinstance(comparison, dict) or comparison.get(
                            "status"
                        ) not in {
                            "ahead",
                            "identical",
                        }:
                            valid = False
                            reason = (
                                f"Merged commit {ancestor} is not contained "
                                f"in {descendant}"
                            )
                            break
                except RuntimeError:
                    valid = False
                    reason = "Merged PR containment could not be verified"
            elif valid:
                valid = False
                reason = "Merged PR has no merge commit identity"
            merged_routes[str(candidate.get("number"))] = {
                "valid": valid,
                "chain": chain,
                "reason": reason,
                "terminal_merge_sha": merge_sha,
                "containment": [
                    {"ancestor": ancestor, "descendant": descendant}
                    for ancestor, descendant in containment
                ],
            }
        observation["merged_routes"] = merged_routes
        if merged and route.get("base") == "main":
            latest = max(merged, key=lambda item: str(item.get("merged_at")))
            latest_route = merged_routes.get(str(latest.get("number")), {})
            merge_sha = latest_route.get("terminal_merge_sha")
            if latest_route.get("valid") and isinstance(merge_sha, str):
                try:
                    post_merge_runs = github.keyed(
                        repo,
                        f"commits/{merge_sha}/check-runs?filter=latest"
                        "&per_page=100",
                        "check_runs",
                    )
                    observation["post_merge_verified"] = any(
                        run.get("name") == "verify promoted main"
                        and run.get("head_sha") == merge_sha
                        and run.get("status") == "completed"
                        and run.get("conclusion") == "success"
                        for run in post_merge_runs
                    )
                except RuntimeError:
                    observation["post_merge_verified"] = False
    if len(open_pulls) != 1 or not route.get("valid"):
        return derive_status(observation)

    pull = github.get(repo, f"pulls/{open_pulls[0]['number']}")
    if not isinstance(pull, dict):
        raise RuntimeError("Live pull request is malformed")
    observation["pulls"] = [
        pull,
        *[item for item in related if item.get("number") != pull.get("number")],
    ]
    observation["files"] = [
        str(item["filename"])
        for item in github.pages(
            repo, f"pulls/{pull['number']}/files?per_page=100"
        )
        if isinstance(item.get("filename"), str)
    ]
    base = pull.get("base") or {}
    base_ref = str(base.get("ref") or "")
    base_sha = branches.get(base_ref, "")
    head = pull.get("head") or {}
    capability = inspect_capability(
        github,
        repo,
        repository,
        pull,
        lease,
        owner,
        authorization_url,
    )
    observation["capability"] = capability
    head_repo = head.get("repo") or {}
    if head_repo.get("full_name") != repo:
        observation["base_current"] = False
    head_sha = str(head.get("sha") or "")
    runs = github.keyed(
        repo,
        f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
        "check_runs",
    )
    status = github.get(repo, f"commits/{head_sha}/status")
    statuses = status.get("statuses") if isinstance(status, dict) else None
    if not isinstance(statuses, list) or not all(
        isinstance(item, dict) for item in statuses
    ):
        raise RuntimeError("Commit statuses are malformed")
    required_value = capability.get("required")
    required_contexts = (
        {
            (str(item["context"]), item.get("integration_id"))
            for item in required_value
            if isinstance(item, dict) and isinstance(item.get("context"), str)
        }
        if isinstance(required_value, list)
        else set()
    )
    observed_checks = check_state(runs, statuses, required_contexts)
    try:
        comparison = github.get(repo, f"compare/{base_sha}...{head_sha}")
        observation["base_current"] = (
            observation.get("base_current") is not False
            and isinstance(comparison, dict)
            and comparison.get("status") in {"ahead", "identical"}
        )
    except RuntimeError:
        observation["base_current"] = False
    if observed_checks == "failed":
        try:
            urls = failed_pull_request_run_urls(repo, head_sha, "")
            for url in urls:
                require_zero_step_run(
                    url,
                    repo,
                    int(pull["number"]),
                    str(head.get("ref") or ""),
                    head_sha,
                    "",
                )
            observed_checks = "quota-blocked"
            observation["blocked_run_urls"] = urls
        except RuntimeError:
            pass
    observation["checks"] = observed_checks
    issue_comments = github.pages(
        repo, f"issues/{pull['number']}/comments?per_page=100"
    )
    comments = [
        *issue_comments,
        *github.pages(repo, f"pulls/{pull['number']}/comments?per_page=100"),
    ]
    reviews = github.pages(repo, f"pulls/{pull['number']}/reviews?per_page=100")
    comments.extend(
        {**review, "created_at": review.get("submitted_at")}
        for review in reviews
        if review.get("state") == "COMMENTED" and review.get("body")
    )
    observation["blocker"] = unresolved_blocker(comments, reviews)
    observation["human_approval"] = has_human_approval(
        reviews,
        str((pull.get("user") or {}).get("login") or ""),
        head_sha,
    )
    observation["quota_note"] = has_exact_quota_note(
        issue_comments,
        repo,
        int(pull["number"]),
        head_sha,
        list(observation.get("blocked_run_urls", [])),
    )
    return derive_status(observation)


def main() -> None:
    """Print a machine-readable, read-only Issue path decision."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--lease", type=Path)
    parser.add_argument("--owner")
    parser.add_argument("--authorization-url")
    args = parser.parse_args()
    try:
        supplied = (
            args.lease is not None,
            bool(args.owner),
            bool(args.authorization_url),
        )
        if any(supplied) and not all(supplied):
            raise RuntimeError(
                "--lease, --owner, and --authorization-url are required "
                "together"
            )
        repo = args.repo or local_repository()
        decision = inspect_issue(
            GitHub(),
            repo,
            args.issue,
            local_branch_strategy(),
            args.lease,
            args.owner,
            args.authorization_url,
        )
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(  # noqa: T201
            f"issue path status failed closed: {error}", file=sys.stderr
        )
        raise SystemExit(2) from error
    print(json.dumps(asdict(decision), indent=2, sort_keys=True))  # noqa: T201
    if decision.guard == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
