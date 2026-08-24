#!/usr/bin/env python3
"""Select and execute a release path from observable GitHub capabilities."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATES = {"allowed", "blocked", "unknown"}
SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
DIRECT_CAPABILITIES = ("contents", "release", "dispatch")
INTENT_RANK = {"no-release": 0, "patch": 1, "minor": 2, "major": 3}
RENOVATE_INSTALL_URL = "https://github.com/apps/renovate/installations/new"
DEPENDABOT_FALLBACK = (
    "Keep GitHub Dependabot via .github/dependabot.yml and the existing "
    "required CI/CD checks."
)


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


def select_release_mode(capabilities: dict[str, Capability]) -> tuple[str, str]:
    """Choose Release Please, direct release, or verification-only."""
    pull_requests = capabilities["actions_pull_requests"]
    unavailable = [
        name
        for name in DIRECT_CAPABILITIES
        if capabilities[name].state != "allowed"
    ]
    if pull_requests.state == "allowed" and not unavailable:
        return (
            "release-pr",
            "Actions pull requests and the artifact handoff are allowed",
        )
    if not unavailable:
        return (
            "direct",
            f"Actions pull requests are {pull_requests.state}; "
            "direct release is allowed",
        )
    return (
        "verification-only",
        f"Actions pull requests are {pull_requests.state}; "
        f"artifact handoff unavailable: {', '.join(unavailable)}",
    )


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


def aggregate_release_boundaries(  # noqa: C901
    boundaries: list[dict[str, Any]], main_sha: str, source_kind: str
) -> dict[str, object]:
    """Combine verified promotions into one deterministic release boundary."""
    if not boundaries:
        raise ValueError("release boundary contains no promotion evidence")
    summaries: list[dict[str, object]] = []
    pull_requests: dict[int, dict[str, object]] = {}
    highest = "no-release"
    valid_routes = {"milestone", "standalone-batch", "dev-promotion", "hotfix"}
    for evidence in boundaries:
        route = evidence.get("route")
        post_merge = evidence.get("post_merge")
        release = evidence.get("release")
        if (
            evidence.get("gate") != "passed"
            or not isinstance(route, dict)
            or route.get("kind") not in valid_routes
            or not isinstance(post_merge, dict)
            or post_merge.get("tree_identity") != "verified"
            or not isinstance(release, dict)
        ):
            raise ValueError("release boundary has invalid promotion evidence")
        intent = release.get("intent")
        if not isinstance(intent, str) or intent not in INTENT_RANK:
            raise ValueError("release boundary has invalid SemVer intent")
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
        summaries.append(
            {
                "kind": route["kind"],
                "milestone": route.get("milestone"),
                "delivery_branch": evidence.get("head_ref"),
                "promotion_pr": evidence.get("pull_request"),
                "promotion_main_sha": post_merge.get("main_sha"),
                "promotion_run": evidence.get("workflow_run"),
                "included_issues": evidence.get("included_issues", []),
                "canary": evidence.get("canary"),
                "full_check": evidence.get("full_check"),
            }
        )
    summaries.sort(key=lambda item: str(item["promotion_main_sha"]))
    return {
        "schema_version": 1,
        "kind": source_kind,
        "main_sha": main_sha,
        "eligible": highest != "no-release",
        "reason": (
            f"verified promotion batch declares {highest} release intent"
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
        "release": {"intent": intent},
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
            "release",
            "dispatch",
        )
    }


def detect_runtime_capabilities(
    api: GitHubAPI, repo: str, sha: str, branch: str, workflow: str
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

    encoded_workflow = urllib.parse.quote(workflow, safe="")
    status, _ = api.request(
        "POST",
        f"repos/{repo}/actions/workflows/{encoded_workflow}/dispatches",
        {"ref": f"__csarc_capability_probe_{sha[:12]}__"},
    )
    capabilities["dispatch"] = classify_probe(
        status, validation_proves_access=True
    )
    return capabilities


def preflight_capabilities(repo: str) -> dict[str, Capability]:
    """Read the repository PR policy; defer token-write checks to runtime."""
    capabilities = unknown_capabilities("requires the runtime workflow token")
    executable = shutil.which("gh")
    if executable is None:
        capabilities["actions_pull_requests"] = Capability(
            "unknown", "GitHub CLI is unavailable"
        )
        return capabilities
    result = subprocess.run(  # noqa: S603
        [executable, "api", f"repos/{repo}/actions/permissions/workflow"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        capabilities["actions_pull_requests"] = Capability(
            "unknown",
            "Actions policy is not readable with the current identity",
        )
        return capabilities
    try:
        response = json.loads(result.stdout)
        allowed = (
            response.get("can_approve_pull_request_reviews")
            if isinstance(response, dict)
            else None
        )
    except json.JSONDecodeError:
        allowed = None
    if isinstance(allowed, bool):
        capabilities["actions_pull_requests"] = Capability(
            "allowed" if allowed else "blocked",
            "repository Actions policy allows pull requests"
            if allowed
            else "repository Actions policy blocks pull requests",
        )
    return capabilities


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
    capabilities: dict[str, Capability], source: str, **extra: object
) -> dict[str, object]:
    """Build the machine-readable decision record."""
    mode, reason = select_release_mode(capabilities)
    return {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "source": source,
        "mode": mode,
        "reason": reason,
        "capabilities": {
            name: asdict(capability)
            for name, capability in sorted(capabilities.items())
        },
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
    raw = git_output(["log", "--format=%s%x1f%b%x1e", revision_range], root)
    messages = [
        message.replace("\x1f", "\n")
        for message in raw.split("\x1e")
        if message
    ]
    version = bump_version(base, messages)
    return None if version is None else (f"v{version}", version)


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

    for path in [
        root / "README.md",
        root / "docs" / "index.html",
        *root.glob("src/*/__init__.py"),
    ]:
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
        if (
            path in {root / "README.md", root / "docs" / "index.html"}
            and not marker_found
        ):
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


def direct_release(  # noqa: C901
    api: GitHubAPI,
    repo: str,
    sha: str,
    branch: str,
    workflow: str,
    root: Path,
    source_run_id: str = "",
) -> tuple[dict[str, object], bool]:
    """Allocate one release from the current remote default-branch head."""
    capabilities = detect_runtime_capabilities(api, repo, sha, branch, workflow)
    payload = report(capabilities, "runtime-recheck")
    if payload["mode"] != "direct":
        return payload, False

    encoded_branch = urllib.parse.quote(branch, safe="")
    status, remote_ref = api.request(
        "GET", f"repos/{repo}/git/ref/heads/{encoded_branch}"
    )
    remote_sha = (
        remote_ref.get("object", {}).get("sha")
        if isinstance(remote_ref, dict)
        else None
    )
    if status != 200 or remote_sha != sha:
        payload.update(
            mode="verification-only",
            reason="workflow commit is no longer the default-branch head",
            status="superseded",
        )
        return payload, False

    planned = release_plan(root, sha)
    if planned is None:
        payload.update(status="no-release", reason="no release-worthy commits")
        return payload, False
    tag, version = planned
    version_errors = release_version_errors(root, version)
    if version_errors:
        payload.update(
            mode="verification-only",
            reason="release commit is not materialized: "
            + "; ".join(version_errors),
            status="version-not-materialized",
            tag=tag,
            version=version,
        )
        return payload, False
    status, existing_ref = api.request(
        "GET", f"repos/{repo}/git/ref/tags/{tag}"
    )
    if status == 200:
        existing_sha = (
            existing_ref.get("object", {}).get("sha")
            if isinstance(existing_ref, dict)
            else None
        )
        if existing_sha != sha:
            payload.update(
                mode="verification-only",
                reason=f"tag {tag} already identifies another commit",
                status="tag-conflict",
                tag=tag,
            )
            return payload, True
    elif status == 404:
        create_status, _ = api.request(
            "POST",
            f"repos/{repo}/git/refs",
            {"ref": f"refs/tags/{tag}", "sha": sha},
        )
        if create_status != 201:
            payload.update(
                mode="verification-only",
                reason=f"tag creation failed with HTTP {create_status}",
                status="tag-create-failed",
                tag=tag,
            )
            return payload, True
    else:
        payload.update(
            mode="verification-only",
            reason=f"tag state is unknown (HTTP {status or 'unavailable'})",
            status="tag-unknown",
            tag=tag,
        )
        return payload, True

    encoded_tag = urllib.parse.quote(tag, safe="")
    status, release = api.request(
        "GET", f"repos/{repo}/releases/tags/{encoded_tag}"
    )
    if status == 404:
        status, release = api.request(
            "POST",
            f"repos/{repo}/releases",
            {
                "tag_name": tag,
                "target_commitish": sha,
                "name": tag,
                "draft": True,
                "generate_release_notes": True,
            },
        )
    if status not in {200, 201} or not isinstance(release, dict):
        payload.update(
            mode="verification-only",
            reason=f"draft release creation failed with HTTP {status}",
            status="release-create-failed",
            tag=tag,
        )
        return payload, True
    if release.get("draft") is not True:
        payload.update(status="already-released", tag=tag, version=version)
        return payload, False

    encoded_workflow = urllib.parse.quote(workflow, safe="")
    status, runs = api.request(
        "GET",
        f"repos/{repo}/actions/workflows/{encoded_workflow}/runs?event=workflow_dispatch&branch={encoded_tag}&per_page=20",
    )
    active_or_successful = False
    if status == 200 and isinstance(runs, dict):
        active_or_successful = any(
            item.get("head_sha") == sha
            and (
                item.get("status") != "completed"
                or item.get("conclusion") == "success"
            )
            for item in runs.get("workflow_runs", [])
            if isinstance(item, dict)
        )
    if not active_or_successful:
        dispatch: dict[str, object] = {"ref": tag}
        if source_run_id:
            dispatch["inputs"] = {"source_run_id": source_run_id}
        status, _ = api.request(
            "POST",
            f"repos/{repo}/actions/workflows/{encoded_workflow}/dispatches",
            dispatch,
        )
        if status != 204:
            payload.update(
                mode="verification-only",
                reason=f"artifact dispatch failed with HTTP {status}",
                status="dispatch-failed",
                tag=tag,
            )
            return payload, True
    payload.update(status="dispatched", tag=tag, version=version)
    return payload, False


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
    detect.add_argument("--workflow", required=True)
    detect.add_argument("--output", type=Path)
    detect.add_argument("--github-output", type=Path)

    release = subparsers.add_parser("release")
    release.add_argument("--repo", required=True)
    release.add_argument("--sha", required=True)
    release.add_argument("--branch", required=True)
    release.add_argument("--workflow", required=True)
    release.add_argument("--root", type=Path, default=Path.cwd())
    release.add_argument("--output", type=Path)
    release.add_argument("--github-output", type=Path)
    release.add_argument("--source-run-id", default="")

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
    verify = subparsers.add_parser("verify-version")
    verify.add_argument("--tag")
    verify.add_argument("--root", type=Path, default=Path.cwd())
    return result


def main(arguments: list[str] | None = None) -> int:  # noqa: C901
    """Run capability detection, direct release, or build preparation."""
    args = parser().parse_args(arguments)
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
        write_report(
            report(
                preflight_capabilities(args.repo),
                "cli-preflight",
                integrations=optional_integration_preflight(args.repo),
            ),
            None,
            None,
        )
        return 0

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    capabilities = (
        unknown_capabilities("GitHub token is unavailable")
        if not token
        else detect_runtime_capabilities(
            GitHubAPI(
                token,
                os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            ),
            args.repo,
            args.sha,
            args.branch,
            args.workflow,
        )
    )
    if args.command == "detect":
        write_report(
            report(capabilities, "runtime"), args.output, args.github_output
        )
        return 0
    if not token:
        write_report(
            report(capabilities, "runtime-recheck"),
            args.output,
            args.github_output,
        )
        return 0
    payload, failed = direct_release(
        GitHubAPI(
            token, os.environ.get("GITHUB_API_URL", "https://api.github.com")
        ),
        args.repo,
        args.sha,
        args.branch,
        args.workflow,
        args.root.resolve(),
        args.source_run_id,
    )
    write_report(payload, args.output, args.github_output)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
