#!/usr/bin/env python3
"""Select and execute a release path from observable GitHub capabilities."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
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
    rank = {"no-release": 0, "patch": 1, "minor": 2, "major": 3}
    for message in messages:
        subject, _, body = message.partition("\n")
        intent = release_intent(subject)
        if "BREAKING CHANGE:" in body or "BREAKING-CHANGE:" in body:
            intent = "major"
        if rank[intent] > rank[bump]:
            bump = intent
    if bump == "no-release":
        return None
    major, minor, patch = (int(value) for value in match.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


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


def update_release_version(root: Path, version: str) -> None:
    """Materialize a tag-selected version in an ephemeral build checkout."""
    if SEMVER.fullmatch(version) is None:
        raise ValueError(f"invalid semantic version: {version}")
    manifest_path = root / ".release-please-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["."] = version
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    pyproject = root / "pyproject.toml"
    project_name = None
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8")
        project = re.search(r"(?ms)^\[project\]\n(.*?)(?=^\[|\Z)", text)
        if project is not None:
            project_name_match = re.search(
                r'^name = "([^"]+)"$', project.group(1), re.M
            )
            project_name = (
                project_name_match.group(1) if project_name_match else None
            )
            updated = re.sub(
                r'(?m)^version = "\d+\.\d+\.\d+"$',
                f'version = "{version}"',
                project.group(0),
                count=1,
            )
            text = text[: project.start()] + updated + text[project.end() :]
            pyproject.write_text(text, encoding="utf-8")

    lock = root / "uv.lock"
    if lock.is_file() and project_name:
        text = lock.read_text(encoding="utf-8")
        pattern = (
            rf'(?m)(^name = "{re.escape(project_name)}"\nversion = ")'
            r'\d+\.\d+\.\d+("$)'
        )
        lock.write_text(
            re.sub(pattern, rf"\g<1>{version}\2", text, count=1),
            encoding="utf-8",
        )

    package_json = root / "package.json"
    if package_json.is_file():
        package = json.loads(package_json.read_text(encoding="utf-8"))
        package["version"] = version
        package_json.write_text(
            json.dumps(package, indent=2) + "\n", encoding="utf-8"
        )

    for path in [
        root / "README.md",
        root / "docs" / "index.html",
        *root.glob("src/*/__init__.py"),
    ]:
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        changed = [
            re.sub(
                r"v?\d+\.\d+\.\d+",
                lambda match: (
                    ("v" if match.group().startswith("v") else "") + version
                ),
                line,
                count=1,
            )
            if "x-release-please-version" in line
            else line
            for line in lines
        ]
        path.write_text("".join(changed), encoding="utf-8")
    version_file = root / "version.txt"
    if version_file.is_file():
        version_file.write_text(f"{version}\n", encoding="utf-8")


def direct_release(  # noqa: C901
    api: GitHubAPI,
    repo: str,
    sha: str,
    branch: str,
    workflow: str,
    root: Path,
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
        status, _ = api.request(
            "POST",
            f"repos/{repo}/actions/workflows/{encoded_workflow}/dispatches",
            {"ref": tag},
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

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--tag", required=True)
    prepare.add_argument("--root", type=Path, default=Path.cwd())
    return result


def main(arguments: list[str] | None = None) -> int:
    """Run capability detection, direct release, or build preparation."""
    args = parser().parse_args(arguments)
    if args.command == "prepare":
        match = SEMVER.fullmatch(args.tag)
        if match is None:
            raise SystemExit(f"invalid release tag: {args.tag}")
        update_release_version(args.root.resolve(), args.tag.removeprefix("v"))
        return 0
    if args.command == "preflight":
        write_report(
            report(preflight_capabilities(args.repo), "cli-preflight"),
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
    )
    write_report(payload, args.output, args.github_output)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
