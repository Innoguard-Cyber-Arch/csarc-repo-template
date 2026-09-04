#!/usr/bin/env python3
"""Plan and verify one release path from observable GitHub capabilities."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

STATES = {"allowed", "blocked", "unknown"}
SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
PUBLISH_CAPABILITIES = ("contents", "release", "immutable_releases")
INTENT_RANK = {"no-release": 0, "patch": 1, "minor": 2, "major": 3}
RENOVATE_INSTALL_URL = "https://github.com/apps/renovate/installations/new"
DEPENDABOT_FALLBACK = (
    "Keep GitHub Dependabot via .github/dependabot.yml and the existing "
    "required CI/CD checks."
)
RELEASE_PLEASE_ACTOR = "github-actions[bot]"
RELEASE_PLEASE_COMMITTER = "web-flow"


@dataclass(frozen=True)
class Capability:
    """One observed permission state and its evidence."""

    state: str
    reason: str

    def __post_init__(self) -> None:
        """Reject states outside the public tri-state contract."""
        if self.state not in STATES:
            raise ValueError(f"invalid capability state: {self.state}")


class GitHubAPI:
    """Small GitHub REST client that preserves response status codes."""

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


def classify_probe(
    status: int, *, validation_proves_access: bool = False
) -> Capability:
    """Map an HTTP probe to a conservative tri-state capability."""
    if 200 <= status < 300 or (status == 422 and validation_proves_access):
        return Capability("allowed", f"GitHub API returned HTTP {status}")
    if status in {401, 403, 409}:
        return Capability("blocked", f"GitHub API returned HTTP {status}")
    return Capability(
        "unknown", f"GitHub API returned HTTP {status or 'unavailable'}"
    )


def select_release_mode(
    capabilities: dict[str, Capability], *, operator_reason: str | None = None
) -> tuple[str, str]:
    """Choose Automatic, Guided, or Blocked without a second publisher.

    Guided mode has one automatically-detected trigger (Actions pull
    requests are blocked or unknown per observed capabilities) and one
    operator-asserted trigger: `operator_reason` is a non-empty, human- or
    agent-authored justification recording a live decision that Actions or
    its webhook delivery is currently unhealthy (see Issue #589 and #587,
    and docs/ci-policy.md's "Release 發版不依賴 Actions 健康度的 fallback"
    section). There is no capability probe for "Actions/webhooks are
    unhealthy": an idle hosted runner or a dropped `pull_request` webhook
    delivery looks identical to "nothing to release right now" from the
    GitHub REST API this module probes, so this trigger is deliberately
    manual rather than auto-detected. An operator override can only steer
    an otherwise-automatic release toward the same reviewed Guided path
    (prepare-candidate -> ordinary pull request -> ordinary review); it
    never turns a genuinely blocked publish capability into a usable one,
    and it never skips review.
    """
    pull_requests = capabilities["actions_pull_requests"]
    blocked = [
        name
        for name in PUBLISH_CAPABILITIES
        if capabilities[name].state == "blocked"
    ]
    unknown = [
        name
        for name in PUBLISH_CAPABILITIES
        if capabilities[name].state == "unknown"
    ]
    if blocked or unknown:
        return (
            "blocked",
            "GitHub tag or Release publication is unavailable or unproven: "
            + ", ".join([*blocked, *unknown]),
        )
    if operator_reason:
        return (
            "guided",
            "Operator judged Actions or webhook delivery unhealthy: "
            + operator_reason,
        )
    if pull_requests.state == "allowed":
        return (
            "automatic",
            "Actions pull requests and the artifact handoff are allowed",
        )
    if pull_requests.state != "allowed":
        return (
            "guided",
            f"Actions pull requests are {pull_requests.state}; prepare a "
            "reviewed version candidate locally",
        )
    raise AssertionError("release mode selection is incomplete")


def release_intent(title: str) -> str:
    """Return the semantic bump intent without allocating a version."""
    match = re.match(
        r"^(feat|fix|docs|refactor|test|build|ci|chore|revert)"
        r"(?:\([a-z0-9._/-]+\))?(!)?: ",
        title,
    )
    if match is None:
        return "no-release"
    if match.group(2):
        return "major"
    if match.group(1) == "feat":
        return "minor"
    if match.group(1) in {"fix", "revert"}:
        return "patch"
    return "no-release"


def release_follow_up_errors(  # noqa: C901
    root: Path,
    repo: str,
    head: str,
    head_repo: str,
    head_sha: str,
    actor: str,
    changed_files: list[str],
    commits: list[dict[str, Any]],
    actor_permission: str = "",
) -> list[str]:
    """Reject release follow-ups outside the automation-owned boundary."""
    errors: list[str] = []
    if head_repo != repo:
        errors.append("release follow-up must come from this repository")
    automation_actor = actor == RELEASE_PLEASE_ACTOR
    maintainer_actor = bool(actor) and actor_permission in {"admin", "maintain"}
    if not automation_actor and not maintainer_actor:
        errors.append(
            "release follow-up must be authored by github-actions[bot] "
            "or a live repository maintainer"
        )
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        errors.append("release follow-up head is not a full commit SHA")
    elif not commits or commits[-1].get("sha") != head_sha:
        errors.append("release follow-up commits do not end at the PR head")
    for commit in commits:
        author = commit.get("author")
        committer = commit.get("committer")
        commit_data = commit.get("commit")
        verification = (
            commit_data.get("verification")
            if isinstance(commit_data, dict)
            else None
        )
        author_login = author.get("login") if isinstance(author, dict) else None
        committer_login = (
            committer.get("login") if isinstance(committer, dict) else None
        )
        automation_commit = (
            author_login == RELEASE_PLEASE_ACTOR
            and committer_login == RELEASE_PLEASE_COMMITTER
            and isinstance(verification, dict)
            and verification.get("verified") is True
            and verification.get("reason") == "valid"
        )
        maintainer_commit = (
            maintainer_actor
            and actor in {author_login, committer_login}
            and committer_login in {actor, RELEASE_PLEASE_COMMITTER}
        )
        if not (
            (automation_actor and automation_commit)
            or (not automation_actor and maintainer_commit)
        ):
            errors.append(
                "release follow-up commits must be owned by the trusted "
                "release actor; automation commits must also be GitHub-verified"
            )
            break

    try:
        config = json.loads(
            (root / "release-please-config.json").read_text(encoding="utf-8")
        )
        packages = config["packages"]
        package = packages["."]
        component = package["component"]
        release_type = package.get("release-type", config.get("release-type"))
        if not isinstance(component, str) or not component:
            raise ValueError("release component is missing")
        if release_type not in {"simple", "python", "node", "rust"}:
            raise ValueError("release type is unsupported")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"release-please configuration is invalid: {error}")
        return errors

    expected_head = f"release-please--branches--main--components--{component}"
    guided_head = re.fullmatch(r"release/v\d+\.\d+\.\d+", head)
    if automation_actor and head != expected_head:
        errors.append(f"release follow-up branch must be {expected_head}")
    elif maintainer_actor and guided_head is None:
        errors.append(
            "guided release branch must use release/v<major>.<minor>.<patch>"
        )

    allowed = {".release-please-manifest.json", "CHANGELOG.md"}
    release_file = {
        "simple": "version.txt",
        "python": "pyproject.toml",
        "node": "package.json",
        "rust": "Cargo.toml",
    }[release_type]
    allowed.add(release_file)
    for item in package.get("extra-files", []):
        value = (
            item
            if isinstance(item, str)
            else item.get("path")
            if isinstance(item, dict)
            else None
        )
        if not isinstance(value, str):
            errors.append("release-please extra-files entry is invalid")
            continue
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"release-please extra-files path is unsafe: {value}")
            continue
        allowed.add(path.as_posix())
    for lockfile in ("uv.lock", "pnpm-lock.yaml", "Cargo.lock"):
        if (root / lockfile).is_file():
            allowed.add(lockfile)

    changed = {path for path in changed_files if path}
    if not changed:
        errors.append("release follow-up has no changed files")
    unexpected = sorted(changed - allowed)
    if unexpected:
        errors.append(
            "release follow-up changes non-release files: "
            + ", ".join(unexpected)
        )
    return errors


def bump_version(version: str, messages: list[str]) -> str | None:
    """Calculate the next version from merged Conventional Commits."""
    match = SEMVER.fullmatch(version)
    if match is None:
        raise ValueError(f"invalid semantic version: {version}")
    bump = "no-release"
    for message in messages:
        subject, _, body = message.partition("\n")
        intent = release_intent(subject)
        if "BREAKING CHANGE:" in body or "BREAKING-CHANGE:" in body:
            intent = "major"
        if INTENT_RANK[intent] > INTENT_RANK[bump]:
            bump = intent
    if bump == "no-release":
        return None
    major, minor, patch = (int(value) for value in match.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def milestone_boundary(  # noqa: C901
    evidence: dict[str, Any],
    included_pull_requests: list[dict[str, Any]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Validate one milestone promotion's canonical Issue scope."""
    promotion = evidence.get("milestone_promotion")
    issues = evidence.get("included_issues")
    if (
        not isinstance(promotion, dict)
        or set(promotion) != {"mode", "declared_issues"}
        or not isinstance(issues, list)
    ):
        raise ValueError("milestone release boundary schema is invalid")
    issue_numbers: list[int] = []
    normalized_issues: list[dict[str, object]] = []
    for issue in issues:
        if (
            not isinstance(issue, dict)
            or set(issue) != {"number", "title"}
            or type(issue.get("number")) is not int
            or int(issue["number"]) < 1
            or not isinstance(issue.get("title"), str)
        ):
            raise ValueError("milestone included Issue is invalid")
        issue_numbers.append(int(issue["number"]))
        normalized_issues.append(
            {"number": int(issue["number"]), "title": issue["title"]}
        )
    if issue_numbers != sorted(set(issue_numbers)):
        raise ValueError("milestone included Issues are not canonical")
    pull_request_issues: set[int] = set()
    for pull_request in included_pull_requests:
        if "issue" not in pull_request:
            raise ValueError("milestone pull request has no Issue binding")
        number = pull_request["issue"]
        if number is not None and (type(number) is not int or number < 1):
            raise ValueError("milestone pull-request Issue binding is invalid")
        if isinstance(number, int):
            pull_request_issues.add(number)
    if issue_numbers != sorted(pull_request_issues):
        raise ValueError("milestone Issue evidence does not match its PRs")
    mode = promotion.get("mode")
    declared = promotion.get("declared_issues")
    if mode == "final":
        if declared is not None:
            raise ValueError("final milestone promotion declares Issues")
    elif mode == "checkpoint":
        if (
            not isinstance(declared, list)
            or not declared
            or any(type(number) is not int or number < 1 for number in declared)
            or declared != sorted(set(declared))
            or declared != issue_numbers
        ):
            raise ValueError("checkpoint Issue evidence is invalid")
    else:
        raise ValueError("milestone promotion mode is invalid")
    return promotion, normalized_issues


def aggregate_release_boundaries(  # noqa: C901
    boundaries: list[dict[str, Any]], main_sha: str, source_kind: str
) -> dict[str, object]:
    """Combine verified main boundaries into one deterministic release batch."""
    if not boundaries:
        raise ValueError("release boundary contains no source evidence")
    summaries: list[dict[str, object]] = []
    pull_requests: dict[int, dict[str, object]] = {}
    highest = "no-release"
    valid_routes = {
        "milestone",
        "isolated",
        "hotfix",
        "release-recovery",
    }
    for evidence in boundaries:
        route = evidence.get("route")
        post_merge = evidence.get("post_merge")
        release = evidence.get("release")
        if evidence.get("kind") == "main-strategy":
            direct_pr = evidence.get("pull_request")
            direct_main = evidence.get("main_sha")
            if (
                not isinstance(direct_pr, int)
                or not isinstance(direct_main, str)
                or not isinstance(release, dict)
            ):
                raise ValueError(
                    "release boundary has invalid direct-main evidence"
                )
            route_kind = "main-strategy"
            milestone = None
            delivery_branch = None
            promotion_run = None
            included_issues: object = []
            boundary_main = direct_main
        else:
            if (
                evidence.get("gate") != "passed"
                or evidence.get("release_eligible") is False
                or not isinstance(route, dict)
                or route.get("kind") not in valid_routes
                or not isinstance(post_merge, dict)
                or post_merge.get("tree_identity") != "verified"
                or not isinstance(post_merge.get("main_sha"), str)
                or not isinstance(release, dict)
            ):
                raise ValueError(
                    "release boundary has invalid promotion evidence"
                )
            route_kind = str(route["kind"])
            milestone = route.get("milestone")
            delivery_branch = evidence.get("head_ref")
            direct_pr = evidence.get("pull_request")
            promotion_run = evidence.get("workflow_run")
            included_issues = evidence.get("included_issues", [])
            boundary_main = str(post_merge["main_sha"])
        intent = release.get("intent")
        if not isinstance(intent, str) or intent not in INTENT_RANK:
            raise ValueError("release boundary has invalid SemVer intent")
        if evidence.get("kind") == "main-strategy" and evidence.get(
            "eligible"
        ) is not (intent != "no-release"):
            raise ValueError(
                "release boundary has invalid direct-main evidence"
            )
        if INTENT_RANK[intent] > INTENT_RANK[highest]:
            highest = intent
        included = release.get("included_pull_requests")
        if not isinstance(included, list) or not included:
            raise ValueError("release boundary has no included pull requests")
        boundary_highest = "no-release"
        for pull_request in included:
            if not isinstance(pull_request, dict):
                raise ValueError("release boundary has an invalid pull request")
            number = pull_request.get("number")
            title = pull_request.get("title")
            recorded_intent = pull_request.get("intent")
            if not isinstance(number, int) or not isinstance(title, str):
                raise ValueError("release boundary pull request is incomplete")
            actual_intent = release_intent(title)
            if recorded_intent != actual_intent:
                raise ValueError(
                    "release boundary pull-request intent is invalid"
                )
            if INTENT_RANK[actual_intent] > INTENT_RANK[boundary_highest]:
                boundary_highest = actual_intent
            pull_requests[number] = pull_request
        if intent != boundary_highest:
            raise ValueError("release boundary batch intent is invalid")
        if route_kind == "milestone":
            if type(milestone) is not int or milestone < 1:
                raise ValueError("milestone release boundary is incomplete")
            promotion, included_issues = milestone_boundary(evidence, included)
        else:
            if "milestone_promotion" in evidence:
                raise ValueError(
                    "non-milestone boundary has milestone promotion data"
                )
            promotion = None
        summary: dict[str, object] = {
            "kind": route_kind,
            "milestone": milestone,
            "delivery_branch": delivery_branch,
            "promotion_pr": direct_pr,
            "promotion_main_sha": boundary_main,
            "promotion_run": promotion_run,
            "included_issues": included_issues,
            "canary": evidence.get("canary"),
            "full_check": evidence.get("full_check"),
        }
        if promotion is not None:
            summary["milestone_promotion"] = promotion
        summaries.append(summary)
    summaries.sort(key=lambda item: str(item["promotion_main_sha"]))
    return {
        "schema_version": 1,
        "kind": source_kind,
        "main_sha": main_sha,
        "eligible": highest != "no-release",
        "reason": (
            f"verified release batch declares {highest} release intent"
            if highest != "no-release"
            else "all included pull requests are no-release changes"
        ),
        "release": {
            "intent": highest,
            "included_pull_requests": [
                pull_requests[number] for number in sorted(pull_requests)
            ],
        },
        "boundaries": summaries,
    }


def simple_release_boundary(
    kind: str,
    main_sha: str,
    *,
    title: str = "",
    pull_request: int | None = None,
    reason: str = "",
) -> dict[str, object]:
    """Represent main-strategy or fail-closed commits without promotion data."""
    if kind == "unexpected":
        return {
            "schema_version": 1,
            "kind": kind,
            "main_sha": main_sha,
            "eligible": False,
            "reason": reason or "main commit has no eligible release source",
        }
    if kind == "main-release-follow-up":
        eligible = True
        intent = "release-follow-up"
        explanation = "release pull request completed an existing boundary"
    elif kind == "main-strategy":
        intent = release_intent(title)
        eligible = intent != "no-release"
        explanation = (
            f"main-strategy pull request declares {intent} release intent"
            if eligible
            else "main-strategy pull request is a no-release change"
        )
    else:
        raise ValueError(f"invalid simple release boundary: {kind}")
    return {
        "schema_version": 1,
        "kind": kind,
        "main_sha": main_sha,
        "pull_request": pull_request,
        "eligible": eligible,
        "reason": explanation,
        "release": {
            "intent": intent,
            "included_pull_requests": (
                [
                    {
                        "number": pull_request,
                        "title": title,
                        "intent": intent,
                    }
                ]
                if kind == "main-strategy" and pull_request is not None
                else []
            ),
        },
    }


def release_boundary_errors(
    evidence: dict[str, Any], expected_sha: str
) -> list[str]:
    """Return reasons an artifact workflow must reject release-source data."""
    errors: list[str] = []
    if evidence.get("main_sha") != expected_sha:
        errors.append("release source does not match the tag commit")
    if evidence.get("eligible") is not True:
        errors.append(
            str(evidence.get("reason") or "release source is ineligible")
        )
    kind = evidence.get("kind")
    if kind in {"promotion", "release-follow-up"}:
        boundaries = evidence.get("boundaries")
        if not isinstance(boundaries, list) or not boundaries:
            errors.append("release source has no verified promotion boundaries")
    elif kind not in {"main-strategy", "main-release-follow-up"}:
        errors.append(f"release source kind is not eligible: {kind}")
    return errors


def write_boundary(
    payload: dict[str, object], output: Path, github_output: Path | None
) -> None:
    """Write release eligibility evidence and stable workflow outputs."""
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if github_output is not None:
        with github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"eligible={str(payload['eligible']).lower()}\n")
            handle.write(f"reason={payload['reason']}\n")
            release = payload.get("release")
            intent = (
                release.get("intent") if isinstance(release, dict) else "none"
            )
            handle.write(f"intent={intent}\n")


def unknown_capabilities(reason: str) -> dict[str, Capability]:
    """Return a complete unknown result for unavailable observation."""
    return {
        name: Capability("unknown", reason)
        for name in (
            "actions_pull_requests",
            "contents",
            "immutable_releases",
            "release",
        )
    }


def detect_runtime_capabilities(
    api: GitHubAPI, repo: str, sha: str, branch: str
) -> dict[str, Capability]:
    """Probe current workflow-token behavior without creating resources."""
    capabilities = unknown_capabilities("probe did not run")
    status, _ = api.request(
        "POST",
        f"repos/{repo}/pulls",
        {
            "title": "csarc capability probe",
            "head": f"__csarc_capability_probe_{sha[:12]}__",
            "base": branch,
            "body": "This invalid head must never create a pull request.",
        },
    )
    capabilities["actions_pull_requests"] = classify_probe(
        status, validation_proves_access=True
    )
    if capabilities["actions_pull_requests"].state == "allowed":
        capabilities["actions_pull_requests"] = Capability(
            "allowed", "invalid-head validation proved pull-request access"
        )

    status, _ = api.request(
        "POST",
        f"repos/{repo}/git/refs",
        {"ref": "invalid-csarc-capability-probe", "sha": sha},
    )
    capabilities["contents"] = classify_probe(
        status, validation_proves_access=True
    )

    status, _ = api.request("POST", f"repos/{repo}/releases", {})
    capabilities["release"] = classify_probe(
        status, validation_proves_access=True
    )

    status, immutable = api.request("GET", f"repos/{repo}/immutable-releases")
    if 200 <= status < 300 and isinstance(immutable, dict):
        enabled = immutable.get("enabled")
        capabilities["immutable_releases"] = Capability(
            "allowed" if enabled is True else "blocked",
            "immutable Releases are enabled"
            if enabled is True
            else "immutable Releases must be enabled before publication",
        )
    else:
        capabilities["immutable_releases"] = classify_probe(status)

    return capabilities


def workflow_policy_observations(
    api: GitHubAPI, repo: str
) -> dict[str, Capability]:
    """Read organization and repository PR policy without inferring access."""

    def observe(path: str, scope: str) -> Capability:
        status, payload = api.request("GET", path)
        allowed = (
            payload.get("can_approve_pull_request_reviews")
            if isinstance(payload, dict)
            else None
        )
        if 200 <= status < 300 and isinstance(allowed, bool):
            return Capability(
                "allowed" if allowed else "blocked",
                f"{scope} Actions policy "
                + ("allows" if allowed else "blocks")
                + " pull requests",
            )
        return Capability(
            "unknown",
            f"{scope} Actions policy could not be read (HTTP "
            f"{status or 'unavailable'})",
        )

    owner = repo.split("/", 1)[0]
    return {
        "organization_policy": observe(
            f"orgs/{owner}/actions/permissions/workflow", "organization"
        ),
        "repository_setting": observe(
            f"repos/{repo}/actions/permissions/workflow", "repository"
        ),
    }


def preflight_capabilities(repo: str) -> dict[str, Capability]:
    """Leave token permissions unknown until the workflow runs."""
    del repo
    return unknown_capabilities("requires the runtime workflow token")


def preflight_policy_observations(repo: str) -> dict[str, Capability]:
    """Read org/repository settings without treating them as token access."""
    unknown = {
        name: Capability("unknown", "GitHub CLI is unavailable")
        for name in ("organization_policy", "repository_setting")
    }
    executable = shutil.which("gh")
    if executable is None:
        return unknown

    def observe(endpoint: str, scope: str) -> Capability:
        result = subprocess.run(  # noqa: S603
            [executable, "api", endpoint],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return Capability(
                "unknown",
                f"{scope} Actions policy is not readable with the current "
                "identity",
            )
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError:
            response = None
        allowed = (
            response.get("can_approve_pull_request_reviews")
            if isinstance(response, dict)
            else None
        )
        if not isinstance(allowed, bool):
            return Capability(
                "unknown", f"{scope} Actions policy response is incomplete"
            )
        return Capability(
            "allowed" if allowed else "blocked",
            f"{scope} Actions policy "
            + ("allows" if allowed else "blocks")
            + " pull requests",
        )

    owner = repo.split("/", 1)[0]
    return {
        "organization_policy": observe(
            f"orgs/{owner}/actions/permissions/workflow", "organization"
        ),
        "repository_setting": observe(
            f"repos/{repo}/actions/permissions/workflow", "repository"
        ),
    }


def gh_json(executable: str, endpoint: str) -> dict[str, object] | None:
    """Read one GitHub API object without treating failure as permission."""
    result = subprocess.run(  # noqa: S603
        [executable, "api", endpoint],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def renovate_result(
    state: str,
    reason: str,
    *,
    observed: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the optional Renovate integration decision."""
    if state == "available":
        next_step = (
            "Open the installation page, choose only this repository, and "
            "review the App permissions before approving."
        )
    elif state == "request-owner":
        next_step = (
            "Ask the account or organization owner to review the installation "
            "page and grant access only to this repository. Until approved, "
            "keep GitHub Dependabot and the existing required CI/CD checks."
        )
    else:
        next_step = DEPENDABOT_FALLBACK
    return {
        "state": state,
        "reason": reason,
        "next_step": next_step,
        "install_url": RENOVATE_INSTALL_URL,
        "fallback": DEPENDABOT_FALLBACK,
        "requested_access": (
            "The App installation screen is authoritative; Renovate currently "
            "requests organization members read access and repository "
            "administration read plus workflow/content/PR write access."
        ),
        "observed": observed
        or {
            "owner": None,
            "owner_type": None,
            "actor": None,
            "repository_admin": None,
            "organization_owner": None,
        },
    }


def optional_integration_preflight(repo: str) -> dict[str, dict[str, object]]:
    """Classify optional App setup from read-only repository observations."""
    executable = shutil.which("gh")
    if executable is None:
        return {
            "renovate": renovate_result("fallback", "GitHub CLI is unavailable")
        }

    repository = gh_json(executable, f"repos/{repo}")
    if repository is None:
        return {
            "renovate": renovate_result(
                "fallback",
                "Repository permissions are unavailable; installation was "
                "not assumed",
            )
        }
    owner_payload = repository.get("owner")
    permissions = repository.get("permissions")
    owner = (
        owner_payload.get("login")
        if isinstance(owner_payload, dict)
        and isinstance(owner_payload.get("login"), str)
        else None
    )
    owner_type = (
        owner_payload.get("type")
        if isinstance(owner_payload, dict)
        and isinstance(owner_payload.get("type"), str)
        else None
    )
    repository_admin = (
        permissions.get("admin")
        if isinstance(permissions, dict)
        and isinstance(permissions.get("admin"), bool)
        else None
    )
    actor_payload = gh_json(executable, "user")
    actor = (
        actor_payload.get("login")
        if isinstance(actor_payload, dict)
        and isinstance(actor_payload.get("login"), str)
        else None
    )
    observed: dict[str, object] = {
        "owner": owner,
        "owner_type": owner_type,
        "actor": actor,
        "repository_admin": repository_admin,
        "organization_owner": None,
    }
    if owner is None or owner_type not in {"User", "Organization"}:
        return {
            "renovate": renovate_result(
                "fallback",
                "Repository owner type is unknown; installation was not "
                "assumed",
                observed=observed,
            )
        }
    if actor is None or repository_admin is None:
        return {
            "renovate": renovate_result(
                "fallback",
                "Actor or repository permission is unknown; installation was "
                "not assumed",
                observed=observed,
            )
        }
    if not repository_admin:
        return {
            "renovate": renovate_result(
                "fallback",
                "The current actor is not a repository administrator",
                observed=observed,
            )
        }

    if owner_type == "User":
        if actor == owner:
            return {
                "renovate": renovate_result(
                    "available",
                    "The personal repository owner can review an App "
                    "installation",
                    observed=observed,
                )
            }
        return {
            "renovate": renovate_result(
                "request-owner",
                "A repository collaborator cannot install an App for another "
                "personal account",
                observed=observed,
            )
        }

    membership = gh_json(executable, f"orgs/{owner}/memberships/{actor}")
    if membership is None:
        return {
            "renovate": renovate_result(
                "fallback",
                "Organization ownership is unknown; installation was not "
                "assumed",
                observed=observed,
            )
        }
    organization_owner = (
        membership.get("state") == "active"
        and membership.get("role") == "admin"
    )
    if organization_owner:
        return {
            "renovate": renovate_result(
                "available",
                "The current actor is an organization owner and repository "
                "administrator",
                observed={**observed, "organization_owner": True},
            )
        }
    return {
        "renovate": renovate_result(
            "request-owner",
            "Renovate requests organization permissions, so a repository "
            "admin who is only a member must ask an organization owner",
            observed={**observed, "organization_owner": False},
        )
    }


def report(
    capabilities: dict[str, Capability],
    source: str,
    *,
    policies: dict[str, Capability] | None = None,
    operator_reason: str | None = None,
    **extra: object,
) -> dict[str, object]:
    """Build the machine-readable decision record."""
    policy = policies or {
        "organization_policy": Capability("unknown", "not observed"),
        "repository_setting": Capability("unknown", "not observed"),
    }
    effective_capabilities = dict(capabilities)
    policy_blocks = [
        name
        for name in ("organization_policy", "repository_setting")
        if policy[name].state == "blocked"
    ]
    if policy_blocks:
        effective_capabilities["actions_pull_requests"] = Capability(
            "blocked",
            "Actions pull requests are blocked by " + ", ".join(policy_blocks),
        )
    mode, reason = select_release_mode(
        effective_capabilities, operator_reason=operator_reason
    )
    token_permissions = {
        name: asdict(capability)
        for name, capability in sorted(capabilities.items())
    }
    return {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "source": source,
        "mode": mode,
        "reason": reason,
        "operator_override": operator_reason,
        "organization_policy": asdict(policy["organization_policy"]),
        "repository_setting": asdict(policy["repository_setting"]),
        "token_permissions": token_permissions,
        "effective": {
            "mode": mode,
            "reason": reason,
            "actions_pull_requests": asdict(
                effective_capabilities["actions_pull_requests"]
            ),
        },
        # Compatibility alias for callers that predate the split evidence.
        "capabilities": token_permissions,
        **extra,
    }


def write_report(
    payload: dict[str, object], output: Path | None, github_output: Path | None
) -> None:
    """Write JSON plus stable GitHub Actions outputs."""
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    if github_output is not None:
        with github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"mode={payload['mode']}\n")
            handle.write(f"reason={payload['reason']}\n")
            if payload.get("tag"):
                handle.write(f"tag={payload['tag']}\n")
    print(rendered, end="")  # noqa: T201


def write_plan_report(
    payload: dict[str, object], output: Path | None, github_output: Path | None
) -> None:
    """Write the local version decision and stable workflow outputs."""
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    if github_output is not None:
        with github_output.open("a", encoding="utf-8") as handle:
            for name in ("status", "tag", "version", "materialized"):
                value = payload.get(name, "")
                if isinstance(value, bool):
                    value = str(value).lower()
                handle.write(f"{name}={value}\n")
    print(rendered, end="")  # noqa: T201


def git_output(arguments: list[str], root: Path) -> str:
    """Run a read-only Git query."""
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git is required for release planning")
    result = subprocess.run(  # noqa: S603
        [executable, *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def semver_key(tag: str) -> tuple[int, int, int]:
    """Return a sortable key for a previously validated tag."""
    match = SEMVER.fullmatch(tag)
    if match is None:
        raise ValueError(f"invalid semantic version tag: {tag}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def release_plan(root: Path, sha: str) -> tuple[str, str] | None:
    """Return the next tag/version, or None when HEAD needs no release."""
    pointed_tags = git_output(["tag", "--points-at", sha], root).splitlines()
    released = sorted(
        (tag for tag in pointed_tags if SEMVER.fullmatch(tag)),
        key=semver_key,
    )
    if released:
        return released[-1], released[-1].removeprefix("v")

    tags = git_output(["tag", "--merged", sha], root).splitlines()
    versions = [
        (tuple(int(value) for value in match.groups()), tag)
        for tag in tags
        if (match := SEMVER.fullmatch(tag)) is not None
    ]
    if versions:
        _, latest_tag = max(versions)
        base = latest_tag.removeprefix("v")
        revision_range = f"{latest_tag}..{sha}"
    else:
        manifest = json.loads(
            (root / ".release-please-manifest.json").read_text(encoding="utf-8")
        )
        base = str(manifest["."])
        revision_range = sha
        try:
            parent = git_output(["rev-parse", f"{sha}^"], root)
            parent_manifest = json.loads(
                git_output(
                    ["show", f"{parent}:.release-please-manifest.json"], root
                )
            )
            parent_version = str(parent_manifest["."])
        except (  # fmt: skip -- ruff 0.16.5 strips these required parens
            subprocess.CalledProcessError,
            json.JSONDecodeError,
            KeyError,
        ):
            parent = ""
            parent_version = base
        if (
            parent
            and parent_version != base
            and not release_version_errors(root, base)
        ):
            parent_log = git_output(
                ["log", "--format=%s%x1f%b%x1e", parent], root
            )
            parent_messages = [
                message.strip("\n").replace("\x1f", "\n")
                for message in parent_log.split("\x1e")
                if message.strip("\n")
            ]
            if bump_version(parent_version, parent_messages) == base:
                return f"v{base}", base
    raw = git_output(["log", "--format=%s%x1f%b%x1e", revision_range], root)
    messages = [
        message.strip("\n").replace("\x1f", "\n")
        for message in raw.split("\x1e")
        if message.strip("\n")
    ]
    version = bump_version(base, messages)
    return None if version is None else (f"v{version}", version)


def release_plan_report(root: Path, sha: str) -> dict[str, object]:
    """Describe the one local release decision without changing the repo."""
    planned = release_plan(root, sha)
    if planned is None:
        return {
            "status": "no-release",
            "materialized": False,
            "reason": "no release-worthy Conventional Commits",
        }
    tag, version = planned
    pointed = set(git_output(["tag", "--points-at", sha], root).splitlines())
    if tag in pointed:
        status = "released"
        materialized = True
        reason = f"{tag} already identifies this commit"
    else:
        materialized = not release_version_errors(root, version)
        status = "candidate" if materialized else "pending"
        reason = (
            "reviewed version candidate is ready"
            if materialized
            else "version and CHANGELOG candidate must be prepared"
        )
    return {
        "status": status,
        "tag": tag,
        "version": version,
        "materialized": materialized,
        "reason": reason,
    }


def verify_candidate_version(root: Path, base_sha: str) -> str:
    """Recompute the candidate version from its base commit."""
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git is required for release planning")
    with tempfile.TemporaryDirectory(prefix="csarc-release-base-") as path:
        worktree = Path(path) / "worktree"
        subprocess.run(  # noqa: S603
            [
                executable,
                "worktree",
                "add",
                "--detach",
                "--force",
                str(worktree),
                base_sha,
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        try:
            planned = release_plan(worktree, base_sha)
        finally:
            subprocess.run(  # noqa: S603
                [
                    executable,
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree),
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
    if planned is None:
        raise ValueError("candidate base has no release-worthy commits")
    _, expected = planned
    verify_release_version(root, expected)
    return expected


def _replace_toml_version(
    path: Path, table: str, version: str, *, package_name: str = ""
) -> None:
    """Replace one simple TOML version owned by Release Please."""
    source = path.read_text(encoding="utf-8")
    if package_name:
        block = re.compile(
            rf"(?ms)(^\[\[{re.escape(table)}\]\]\s*\n"
            rf"(?:(?!^\[\[).)*?^name\s*=\s*\"{re.escape(package_name)}\"\s*$"
            rf"(?:(?!^\[\[).)*?^version\s*=\s*\")[^\"]+(\")"
        )
    else:
        block = re.compile(
            rf"(?ms)(^\[{re.escape(table)}\]\s*\n"
            rf"(?:(?!^\[).)*?^version\s*=\s*\")[^\"]+(\")"
        )
    updated, count = block.subn(rf"\g<1>{version}\g<2>", source, count=1)
    if count != 1:
        raise ValueError(f"cannot locate governed version in {path.name}")
    path.write_text(updated, encoding="utf-8")


def _write_release_version(root: Path, version: str) -> None:  # noqa: C901
    """Materialize only version surfaces declared by release configuration."""
    config = json.loads(
        (root / "release-please-config.json").read_text(encoding="utf-8")
    )
    package = config["packages"]["."]
    release_type = package.get("release-type", config.get("release-type"))
    manifest = root / ".release-please-manifest.json"
    manifest.write_text(
        json.dumps({".": version}, indent=2) + "\n", encoding="utf-8"
    )
    if release_type == "simple":
        (root / "version.txt").write_text(f"{version}\n", encoding="utf-8")
    elif release_type == "python":
        _replace_toml_version(root / "pyproject.toml", "project", version)
    elif release_type == "node":
        path = root / "package.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["version"] = version
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    elif release_type == "rust":
        _replace_toml_version(root / "Cargo.toml", "package", version)
    else:
        raise ValueError(f"unsupported release type: {release_type}")

    for item in package.get("extra-files", []):
        if isinstance(item, str):
            kind, value, jsonpath = "generic", item, ""
        elif isinstance(item, dict):
            kind = str(item.get("type", "generic"))
            value = item.get("path")
            jsonpath = str(item.get("jsonpath", ""))
        else:
            raise ValueError("release extra-file entry is invalid")
        if not isinstance(value, str):
            raise ValueError("release extra-file path is invalid")
        path = root / value
        if kind == "generic":
            source = path.read_text(encoding="utf-8")
            lines = []
            changed = False
            for line in source.splitlines(keepends=True):
                if "x-release-please-version" in line:
                    line, count = re.subn(
                        r"(?P<prefix>v?)\d+\.\d+\.\d+",
                        rf"\g<prefix>{version}",
                        line,
                        count=1,
                    )
                    changed = changed or count == 1
                lines.append(line)
            if not changed:
                raise ValueError(f"{value} has no release version marker")
            path.write_text("".join(lines), encoding="utf-8")
        elif kind == "toml" and jsonpath == "$.project.version":
            _replace_toml_version(path, "project", version)
        elif kind == "toml" and jsonpath == "$.package.version":
            _replace_toml_version(path, "package", version)
        elif kind == "toml" and jsonpath.startswith("$.package["):
            match = re.search(r'name\.value=="([^"]+)"', jsonpath)
            if match is None:
                raise ValueError(f"unsupported release jsonpath: {jsonpath}")
            _replace_toml_version(
                path, "package", version, package_name=match.group(1)
            )
        else:
            raise ValueError(f"unsupported release extra-file: {value}")

    cargo_manifest = root / "Cargo.toml"
    cargo_lock = root / "Cargo.lock"
    if cargo_manifest.is_file() and cargo_lock.is_file():
        with cargo_manifest.open("rb") as source:
            cargo_package = tomllib.load(source).get("package", {})
        cargo_name = cargo_package.get("name")
        if not isinstance(cargo_name, str) or not cargo_name:
            raise ValueError("Cargo.toml has no package name")
        _replace_toml_version(
            cargo_lock, "package", version, package_name=cargo_name
        )


def _write_changelog(root: Path, sha: str, version: str) -> None:
    """Prepend deterministic notes for the same commits used by planning."""
    changelog = root / "CHANGELOG.md"
    source = changelog.read_text(encoding="utf-8")
    if re.search(rf"(?m)^## (?:\[)?v?{re.escape(version)}(?:\]|\s|\()", source):
        return
    tags = git_output(["tag", "--merged", sha], root).splitlines()
    versions = [tag for tag in tags if SEMVER.fullmatch(tag)]
    latest = max(versions, key=semver_key) if versions else ""
    revision = f"{latest}..{sha}" if latest else sha
    raw = git_output(
        ["log", "--reverse", "--format=%h%x1f%s%x1e", revision], root
    )
    notes: dict[str, list[str]] = {
        "Breaking Changes": [],
        "Features": [],
        "Bug Fixes": [],
    }
    for record in raw.split("\x1e"):
        if not record.strip():
            continue
        short_sha, subject = record.strip().split("\x1f", 1)
        intent = release_intent(subject)
        heading = {
            "major": "Breaking Changes",
            "minor": "Features",
            "patch": "Bug Fixes",
        }.get(intent)
        if heading:
            notes[heading].append(f"* {subject} ({short_sha})")
    date = git_output(["show", "-s", "--format=%cs", sha], root)
    sections = [f"## [{version}] - {date}"]
    for heading, entries in notes.items():
        if entries:
            sections.extend(["", f"### {heading}", "", *entries])
    entry = "\n".join(sections) + "\n\n"
    marker = source.find("\n## ")
    if marker == -1:
        updated = source.rstrip() + "\n\n" + entry
    else:
        updated = source[: marker + 1] + entry + source[marker + 1 :]
    changelog.write_text(updated, encoding="utf-8")


def prepare_release_candidate(root: Path, sha: str) -> dict[str, object]:
    """Write a local candidate; never create a PR, tag, or GitHub Release."""
    planned = release_plan(root, sha)
    if planned is None:
        raise ValueError("no release-worthy Conventional Commits")
    tag, version = planned
    if tag in git_output(["tag", "--points-at", sha], root).splitlines():
        raise ValueError(f"{tag} already identifies this commit")
    _write_release_version(root, version)
    _write_changelog(root, sha, version)
    errors = release_version_errors(root, version)
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "status": "candidate",
        "tag": tag,
        "version": version,
        "branch": f"release/v{version}",
        "title": f"chore(main): release {version}",
    }


def release_version_errors(  # noqa: C901
    root: Path, expected: str | None = None, *, require_changelog: bool = True
) -> list[str]:
    """Return every release surface that disagrees with the source version."""
    versions: dict[str, str] = {}
    errors: list[str] = []
    version_file = root / "version.txt"
    if version_file.is_file():
        versions["version.txt"] = version_file.read_text(
            encoding="utf-8"
        ).strip()

    manifest_path = root / ".release-please-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        versions[".release-please-manifest.json"] = str(manifest.get(".", ""))
    else:
        errors.append(".release-please-manifest.json is missing")

    pyproject = root / "pyproject.toml"
    project_name = None
    if pyproject.is_file():
        with pyproject.open("rb") as source:
            project = tomllib.load(source).get("project", {})
        project_name = project.get("name")
        if isinstance(project.get("version"), str):
            versions["pyproject.toml"] = project["version"]

    lock = root / "uv.lock"
    if lock.is_file() and isinstance(project_name, str):
        with lock.open("rb") as source:
            packages = tomllib.load(source).get("package", [])
        locked = next(
            (
                package.get("version")
                for package in packages
                if package.get("name") == project_name
            ),
            None,
        )
        if isinstance(locked, str):
            versions["uv.lock"] = locked

    package_json = root / "package.json"
    if package_json.is_file():
        package = json.loads(package_json.read_text(encoding="utf-8"))
        if isinstance(package.get("version"), str):
            versions["package.json"] = package["version"]

    cargo_manifest = root / "Cargo.toml"
    if cargo_manifest.is_file():
        with cargo_manifest.open("rb") as source:
            cargo_package = tomllib.load(source).get("package", {})
        cargo_name = cargo_package.get("name")
        cargo_version = cargo_package.get("version")
        if not isinstance(cargo_name, str) or not cargo_name:
            errors.append("Cargo.toml has no package name")
        if isinstance(cargo_version, str):
            versions["Cargo.toml"] = cargo_version
        else:
            errors.append("Cargo.toml has no package version")

        cargo_lock = root / "Cargo.lock"
        if not cargo_lock.is_file():
            errors.append("Cargo.lock is missing")
        elif isinstance(cargo_name, str) and cargo_name:
            with cargo_lock.open("rb") as source:
                cargo_packages = tomllib.load(source).get("package", [])
            locked_version = next(
                (
                    package.get("version")
                    for package in cargo_packages
                    if package.get("name") == cargo_name
                    and package.get("source") is None
                ),
                None,
            )
            if isinstance(locked_version, str):
                versions["Cargo.lock"] = locked_version
            else:
                errors.append(f"Cargo.lock has no package {cargo_name}")

    marker_paths = [*root.glob("src/*/__init__.py")]
    required_markers: set[Path] = set()
    release_config = root / "release-please-config.json"
    if release_config.is_file():
        config = json.loads(release_config.read_text(encoding="utf-8"))
        extra_files = (
            config.get("packages", {}).get(".", {}).get("extra-files", [])
        )
        extra_paths = {
            item if isinstance(item, str) else item.get("path")
            for item in extra_files
            if isinstance(item, str)
            or (
                isinstance(item, dict) and item.get("type") in {None, "generic"}
            )
        }
        required_markers = {
            root / path
            for path in extra_paths
            if isinstance(path, str) and path and (root / path).is_file()
        }
        marker_paths.extend(required_markers)
    else:
        required_markers = {
            path
            for path in (
                root / "README.md",
                root / "docs" / "index.html",
                root / "site" / "index.html",
            )
            if path.is_file()
        }
        marker_paths.extend(required_markers)
    for path in marker_paths:
        if not path.is_file():
            continue
        marker_found = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if "x-release-please-version" not in line:
                continue
            marker_found = True
            match = re.search(r"v?(\d+\.\d+\.\d+)", line)
            versions[str(path.relative_to(root))] = (
                match.group(1) if match else ""
            )
        if path in required_markers and not marker_found:
            errors.append(
                f"{path.relative_to(root)} has no "
                "x-release-please-version marker"
            )

    if not versions:
        errors.append("no release version source exists")
        return errors
    source_version = expected or next(iter(versions.values()))
    if SEMVER.fullmatch(source_version) is None:
        errors.append(f"invalid release version: {source_version}")
    errors.extend(
        f"{path} is {version}, expected {source_version}"
        for path, version in versions.items()
        if version != source_version
    )

    if require_changelog:
        changelog = root / "CHANGELOG.md"
        heading = re.compile(
            rf"(?m)^## (?:\[)?v?{re.escape(source_version)}(?:\]|\s|\()"
        )
        if not changelog.is_file() or not heading.search(
            changelog.read_text(encoding="utf-8")
        ):
            errors.append(f"CHANGELOG.md has no {source_version} release entry")
    return errors


def verify_release_version(
    root: Path, expected: str | None = None, *, require_changelog: bool = True
) -> str:
    """Require every governed source surface to identify one release."""
    errors = release_version_errors(
        root, expected, require_changelog=require_changelog
    )
    if errors:
        raise ValueError("; ".join(errors))
    if expected is not None:
        return expected
    version_file = root / "version.txt"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    manifest = json.loads(
        (root / ".release-please-manifest.json").read_text(encoding="utf-8")
    )
    return str(manifest["."])


def parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    result = argparse.ArgumentParser()
    subparsers = result.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--repo", required=True)

    detect = subparsers.add_parser("detect")
    detect.add_argument("--repo", required=True)
    detect.add_argument("--sha", required=True)
    detect.add_argument("--branch", required=True)
    detect.add_argument("--output", type=Path)
    detect.add_argument("--github-output", type=Path)
    detect.add_argument(
        "--operator-reason",
        default=None,
        help=(
            "Non-empty justification for forcing Guided mode because an "
            "operator or agent judged Actions or webhook delivery "
            "currently unhealthy, rather than because Actions pull "
            "requests are blocked by policy. Never forces Automatic or "
            "overrides a genuinely blocked publish capability; see "
            "select_release_mode()."
        ),
    )

    boundary = subparsers.add_parser("boundary")
    boundary.add_argument(
        "--kind",
        choices=("main-strategy", "main-release-follow-up", "unexpected"),
        required=True,
    )
    boundary.add_argument("--main-sha", required=True)
    boundary.add_argument("--title", default="")
    boundary.add_argument("--pull-request", type=int)
    boundary.add_argument("--reason", default="")
    boundary.add_argument("--output", type=Path, required=True)
    boundary.add_argument("--github-output", type=Path)

    aggregate = subparsers.add_parser("aggregate-boundary")
    aggregate.add_argument("--evidence-dir", type=Path, required=True)
    aggregate.add_argument("--main-sha", required=True)
    aggregate.add_argument(
        "--source-kind",
        choices=("promotion", "release-follow-up"),
        required=True,
    )
    aggregate.add_argument("--output", type=Path, required=True)
    aggregate.add_argument("--github-output", type=Path)

    verify_boundary = subparsers.add_parser("verify-boundary")
    verify_boundary.add_argument("--evidence", type=Path, required=True)
    verify_boundary.add_argument("--sha", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--tag", required=True)
    prepare.add_argument("--root", type=Path, default=Path.cwd())
    plan = subparsers.add_parser("plan")
    plan.add_argument("--sha", default="HEAD")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--output", type=Path)
    plan.add_argument("--github-output", type=Path)
    candidate = subparsers.add_parser("prepare-candidate")
    candidate.add_argument("--sha", default="HEAD")
    candidate.add_argument("--root", type=Path, default=Path.cwd())
    verify = subparsers.add_parser("verify-version")
    verify.add_argument("--tag")
    verify.add_argument("--root", type=Path, default=Path.cwd())
    verify_candidate = subparsers.add_parser("verify-candidate-version")
    verify_candidate.add_argument("--base-sha", required=True)
    verify_candidate.add_argument("--root", type=Path, default=Path.cwd())
    verify_follow_up = subparsers.add_parser("verify-release-follow-up")
    verify_follow_up.add_argument("--repo", required=True)
    verify_follow_up.add_argument("--head", required=True)
    verify_follow_up.add_argument("--head-repo", required=True)
    verify_follow_up.add_argument("--head-sha", required=True)
    verify_follow_up.add_argument("--actor", required=True)
    verify_follow_up.add_argument("--actor-permission", default="")
    verify_follow_up.add_argument("--changed-files", type=Path, required=True)
    verify_follow_up.add_argument("--commits", type=Path, required=True)
    verify_follow_up.add_argument("--root", type=Path, default=Path.cwd())
    return result


def main(arguments: list[str] | None = None) -> int:  # noqa: C901
    """Run capability detection, local planning, or verification."""
    args = parser().parse_args(arguments)
    if args.command == "verify-release-follow-up":
        commit_pages = json.loads(args.commits.read_text(encoding="utf-8"))
        if not isinstance(commit_pages, list) or any(
            not isinstance(page, list)
            or any(not isinstance(commit, dict) for commit in page)
            for page in commit_pages
        ):
            raise SystemExit("release follow-up commit response is invalid")
        commits = [commit for page in commit_pages for commit in page]
        errors = release_follow_up_errors(
            args.root.resolve(),
            args.repo,
            args.head,
            args.head_repo,
            args.head_sha,
            args.actor,
            args.changed_files.read_text(encoding="utf-8").splitlines(),
            commits,
            args.actor_permission,
        )
        if errors:
            raise SystemExit("; ".join(errors))
        print("Release follow-up source is verified.")  # noqa: T201
        return 0
    if args.command == "boundary":
        write_boundary(
            simple_release_boundary(
                args.kind,
                args.main_sha,
                title=args.title,
                pull_request=args.pull_request,
                reason=args.reason,
            ),
            args.output,
            args.github_output,
        )
        return 0
    if args.command == "aggregate-boundary":
        evidence = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(args.evidence_dir.glob("*.json"))
        ]
        write_boundary(
            aggregate_release_boundaries(
                evidence, args.main_sha, args.source_kind
            ),
            args.output,
            args.github_output,
        )
        return 0
    if args.command == "verify-boundary":
        evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
        errors = release_boundary_errors(evidence, args.sha)
        if errors:
            raise SystemExit("; ".join(errors))
        print("Release source boundary is verified.")  # noqa: T201
        return 0
    if args.command == "plan":
        try:
            payload = release_plan_report(args.root.resolve(), args.sha)
        except (ValueError, json.JSONDecodeError) as error:
            raise SystemExit(str(error)) from error
        write_plan_report(payload, args.output, args.github_output)
        return 0
    if args.command == "prepare-candidate":
        try:
            payload = prepare_release_candidate(args.root.resolve(), args.sha)
        except (ValueError, json.JSONDecodeError) as error:
            raise SystemExit(str(error)) from error
        write_plan_report(payload, None, None)
        return 0
    if args.command == "verify-candidate-version":
        try:
            version = verify_candidate_version(
                args.root.resolve(), args.base_sha
            )
        except (
            ValueError,
            json.JSONDecodeError,
            subprocess.CalledProcessError,
            tomllib.TOMLDecodeError,
        ) as error:
            raise SystemExit(str(error)) from error
        print(  # noqa: T201
            f"Release candidate matches base decision {version}."
        )
        return 0
    if args.command in {"prepare", "verify-version"}:
        tag = args.tag
        expected = None
        if tag is not None:
            match = SEMVER.fullmatch(tag)
            if match is None:
                raise SystemExit(f"invalid release tag: {tag}")
            expected = tag.removeprefix("v")
        try:
            version = verify_release_version(args.root.resolve(), expected)
        except (
            ValueError,
            json.JSONDecodeError,
            tomllib.TOMLDecodeError,
        ) as error:
            raise SystemExit(str(error)) from error
        print(f"Release version {version} is consistent.")  # noqa: T201
        return 0
    if args.command == "preflight":
        policies = preflight_policy_observations(args.repo)
        write_report(
            report(
                preflight_capabilities(args.repo),
                "cli-preflight",
                policies=policies,
                integrations=optional_integration_preflight(args.repo),
            ),
            None,
            None,
        )
        return 0

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    policies = None
    if not token:
        capabilities = unknown_capabilities("GitHub token is unavailable")
    else:
        api = GitHubAPI(
            token,
            os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        )
        capabilities = detect_runtime_capabilities(
            api, args.repo, args.sha, args.branch
        )
        policies = workflow_policy_observations(api, args.repo)
    if args.command == "detect":
        write_report(
            report(
                capabilities,
                "runtime",
                policies=policies,
                operator_reason=args.operator_reason,
            ),
            args.output,
            args.github_output,
        )
        return 0
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
