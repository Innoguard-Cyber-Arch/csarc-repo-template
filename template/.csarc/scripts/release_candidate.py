#!/usr/bin/env python3
"""Plan, materialize, and verify CSARC-owned release versions.

Split from `release_policy.py` in generated projects (#1129): only
`release_ownership: csarc-owned` renders this module, while every project
keeps the capability preflight in `release_policy.py`, whose command line
dispatches here for every other subcommand.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    csarc_config = importlib.import_module("csarc_config")
    release_policy = importlib.import_module("release_policy")
    release_phase = importlib.import_module("release_phase")
else:
    csarc_config = importlib.import_module(f"{__package__}.csarc_config")
    release_policy = importlib.import_module(f"{__package__}.release_policy")
    release_phase = importlib.import_module(f"{__package__}.release_phase")

Capability = release_policy.Capability
report = release_policy.report
unknown_capabilities = release_policy.unknown_capabilities
write_report = release_policy.write_report


# Version parsing/formatting/precedence all go through release_phase (Issue
# #918: beta/stable channels with no legacy prerelease parser) instead of a
# local plain-triplet pattern.
PEP440_SURFACES = {"pyproject.toml", "uv.lock"}


def _is_pep440_surface(relative_path: str) -> bool:
    """Return whether a version surface requires PEP 440 normalization."""
    return relative_path in PEP440_SURFACES or (
        relative_path.startswith("src/")
        and relative_path.endswith("/__init__.py")
    )


INTENT_RANK = {"no-release": 0, "patch": 1, "minor": 2, "major": 3}


RELEASE_PLEASE_ACTOR = "github-actions[bot]"


RELEASE_PLEASE_COMMITTER = "web-flow"


class GitHubAPI:
    """Small GitHub REST client that preserves response status codes."""

    def __init__(
        self, token: str, base_url: str = "https://api.github.com"
    ) -> None:
        """Create a client restricted to an HTTPS API origin."""
        if urllib.parse.urlparse(base_url).scheme != "https":
            raise ValueError("GitHub API URL: not HTTPS. Use HTTPS.")
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
            (root / ".csarc/release-please-config.json").read_text(
                encoding="utf-8"
            )
        )
        packages = config["packages"]
        package = packages["."]
        component = package["component"]
        release_type = package.get("release-type", config.get("release-type"))
        if not isinstance(component, str) or not component:
            raise ValueError("Release component: missing. Add it.")
        if release_type not in {"simple", "python", "node", "rust"}:
            raise ValueError("Release type: unsupported. Fix it.")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"release-please configuration is invalid: {error}")
        return errors

    expected_head = f"release-please--branches--main--components--{component}"
    guided_version = head.removeprefix("release/v")
    guided_head = guided_version != head and release_phase.is_valid_version(
        guided_version
    )
    if automation_actor and head != expected_head:
        errors.append(f"release follow-up branch must be {expected_head}")
    elif maintainer_actor and not guided_head:
        errors.append(
            "guided release branch must use release/v<version>, where "
            "<version> is X.Y.Z or X.Y.Z-beta.N"
        )

    allowed = {".csarc/release-please-manifest.json", "CHANGELOG.md"}
    release_file = {
        "simple": ".csarc/version.txt",
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


def _is_breaking(subject: str, body: str) -> bool:
    """Return whether one commit declares a breaking change."""
    return (
        release_intent(subject) == "major"
        or "BREAKING CHANGE:" in body
        or "BREAKING-CHANGE:" in body
    )


BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:[ \t]*(.*)$")
FOOTER_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9-]*(?:: | #)")


def _breaking_notes(body: str) -> list[str]:
    """Return the migration text of each BREAKING CHANGE footer in a body."""
    notes: list[str] = []
    current: list[str] | None = None
    for line in [*body.splitlines(), ""]:
        stripped = line.strip()
        match = BREAKING_FOOTER.match(stripped)
        if current is not None and (
            not stripped or match or FOOTER_TOKEN.match(stripped)
        ):
            text = " ".join(" ".join(current).split())
            if text:
                notes.append(text)
            current = None
        if match:
            current = [match.group(1)]
        elif current is not None:
            current.append(stripped)
    return notes


MAIN_REFS = ("refs/remotes/origin/main", "refs/heads/main")


def _main_ref(root: Path) -> str:
    """Return the authoritative main ref, or "" when none is available."""
    refs = set(
        git_output(
            ["for-each-ref", "--format=%(refname)", *MAIN_REFS], root
        ).splitlines()
    )
    return next((ref for ref in MAIN_REFS if ref in refs), "")


def project_maturity(root: Path) -> str | None:
    """Return the ``project_maturity`` declared by current main."""
    main_ref = _main_ref(root)
    if not main_ref:
        if (root / ".csarc/config.yml").is_file():
            raise ValueError(
                "project_maturity: origin/main and main are unavailable. "
                "Run 'git fetch origin main'."
            )
        return None
    listed = git_output(
        ["ls-tree", "--name-only", main_ref, "--", ".csarc/config.yml"], root
    )
    if not listed:
        return None
    try:
        text = git_output(["show", f"{main_ref}:.csarc/config.yml"], root)
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.yml"
            config_path.write_text(text + "\n", encoding="utf-8")
            declared = csarc_config.parse_settings_text(text, config_path)
            if csarc_config.SCHEMA_KEY in declared:
                value = csarc_config.load_config(config_path).get(
                    "project_maturity"
                )
            else:
                # A main that predates schema 2 (the update that migrates it
                # is the candidate) still declares its maturity under the
                # same key; nothing is defaulted from a legacy key, so a
                # main without one fails closed (Issue #1071).
                value = declared.get("project_maturity")
                if value not in {"early", "formal"}:
                    raise ValueError(
                        "Legacy main: no project_maturity. Declare it."
                    )
    except (subprocess.CalledProcessError, ValueError) as error:
        raise ValueError(
            "project_maturity: unreadable in "
            f"{main_ref}:.csarc/config.yml. Fix the file."
        ) from error
    return None if value is None else str(value)


def bump_version(
    version: str, messages: list[str], *, maturity: str | None = None
) -> str | None:
    """Calculate the next CORE version from merged Conventional Commits."""
    try:
        parsed = release_phase.parse_version(version)
    except release_phase.ReleasePhaseError as error:
        raise ValueError(
            f"Semantic version {version}: invalid. Fix it."
        ) from error
    bump = "no-release"
    for message in messages:
        subject, _, body = message.partition("\n")
        intent = release_intent(subject)
        if _is_breaking(subject, body):
            intent = "major"
        if INTENT_RANK[intent] > INTENT_RANK[bump]:
            bump = intent
    if bump == "no-release":
        return None
    major, minor, patch = parsed.core
    if maturity == "formal" and major == 0:
        return "1.0.0"
    if bump == "major" and maturity == "early" and major == 0:
        bump = "minor"
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


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


def fetch_all_releases(api: GitHubAPI, repo: str) -> list[dict[str, object]]:
    """Return every GitHub Release for `repo` via paginated GET (Issue #744)."""
    releases: list[dict[str, object]] = []
    page = 1
    while True:
        status, payload = api.request(
            "GET", f"repos/{repo}/releases?per_page=100&page={page}"
        )
        if not (200 <= status < 300) or not isinstance(payload, list):
            detail = status or "unavailable"
            raise RuntimeError(
                f"Releases of {repo}: cannot list them (HTTP {detail}). Retry."
            )
        if not payload:
            break
        releases.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            break
        page += 1
    return releases


def retention_report(api: GitHubAPI, repo: str) -> dict[str, object]:
    """Build the dry-run keep/delete listing for Issue #744 decision 5."""
    releases = [
        release
        for release in fetch_all_releases(api, repo)
        if release.get("draft") is False
    ]
    by_tag = {
        str(release["tag_name"]): release
        for release in releases
        if isinstance(release.get("tag_name"), str)
    }
    decisions = release_phase.retention_plan(by_tag.keys())
    considered = {decision.version for decision in decisions}
    ignored = sorted(tag for tag in by_tag if tag not in considered)

    def entry(decision: release_phase.RetentionDecision) -> dict[str, object]:
        release = by_tag[decision.version]
        return {
            "tag": decision.version,
            "reason": decision.reason,
            "id": release.get("id"),
            "html_url": release.get("html_url"),
        }

    return {
        "schema_version": 1,
        "repo": repo,
        "dry_run": True,
        "keep": [entry(decision) for decision in decisions if decision.keep],
        "delete": [
            entry(decision) for decision in decisions if not decision.keep
        ],
        "ignored": ignored,
    }


def write_retention_report(
    payload: dict[str, object], output: Path | None, github_output: Path | None
) -> None:
    """Write the retention dry-run listing and stable workflow outputs."""
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    if github_output is not None:
        keep = payload["keep"]
        delete = payload["delete"]
        keep_count = len(keep) if isinstance(keep, list) else 0
        delete_count = len(delete) if isinstance(delete, list) else 0
        with github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"keep_count={keep_count}\n")
            handle.write(f"delete_count={delete_count}\n")
    print(rendered, end="")  # noqa: T201


def git_output(arguments: list[str], root: Path) -> str:
    """Run a read-only Git query."""
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git: not found. Install Git for release planning.")
    result = subprocess.run(  # noqa: S603
        [executable, *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def release_plan(  # noqa: C901
    root: Path, sha: str, *, phase: str | None = None
) -> tuple[str, str] | None:
    """Return the next tag/version, or None when HEAD needs no release."""
    pointed_tags = git_output(["tag", "--points-at", sha], root).splitlines()
    released = release_phase.sort_by_precedence(
        tag for tag in pointed_tags if release_phase.is_valid_version(tag)
    )
    if released:
        return released[-1], released[-1].removeprefix("v")

    tags = git_output(["tag", "--merged", sha], root).splitlines()
    all_tags = git_output(["tag", "--list"], root).splitlines()
    # Beta and stable apply one core-version policy for the same line,
    # and that policy comes from current main rather than the candidate.
    maturity = project_maturity(root)
    valid_tags = [tag for tag in tags if release_phase.is_valid_version(tag)]
    if valid_tags:
        latest_tag = release_phase.sort_by_precedence(valid_tags)[-1]
        base = latest_tag.removeprefix("v")
        revision_range = f"{latest_tag}..{sha}"
    else:
        manifest = json.loads(
            (root / ".csarc/release-please-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        base = str(manifest["."])
        revision_range = sha
        try:
            parent = git_output(["rev-parse", f"{sha}^"], root)
            parent_manifest = json.loads(
                git_output(
                    ["show", f"{parent}:.csarc/release-please-manifest.json"],
                    root,
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
            parent_core = release_phase.parse_version(
                parent_version
            ).core_string()
            base_core = release_phase.parse_version(base).core_string()
            if (
                bump_version(parent_core, parent_messages, maturity=maturity)
                == base_core
            ):
                return f"v{base}", base
    base_core = release_phase.parse_version(base).core_string()
    raw = git_output(["log", "--format=%s%x1f%b%x1e", revision_range], root)
    messages = [
        message.strip("\n").replace("\x1f", "\n")
        for message in raw.split("\x1e")
        if message.strip("\n")
    ]
    version = bump_version(base_core, messages, maturity=maturity)
    if version is None:
        return None

    # A formal sync is squash-merged, so main's stable tag may not be an
    # ancestor. Use the stable version recorded by authoritative main only
    # when its matching tag is reachable there; the delivery tag above still
    # bounds the changelog and release-intent range.
    if phase == "beta":
        main_ref = _main_ref(root)
        if not main_ref:
            higher_stable_tags = [
                tag
                for tag in all_tags
                if release_phase.is_valid_version(tag)
                and not release_phase.parse_version(tag).is_prerelease
                and release_phase.parse_version(tag).core
                > release_phase.parse_version(base_core).core
            ]
            if higher_stable_tags:
                raise ValueError(
                    "Stable version: origin/main and main are unavailable. "
                    "Run 'git fetch origin main'."
                )
        if main_ref:
            try:
                main_version = str(
                    json.loads(
                        git_output(
                            [
                                "show",
                                f"{main_ref}:.csarc/release-please-manifest.json",
                            ],
                            root,
                        )
                    )["."]
                )
                stable = release_phase.parse_version(main_version)
            except (
                subprocess.CalledProcessError,
                json.JSONDecodeError,
                KeyError,
                release_phase.ReleasePhaseError,
            ) as error:
                raise ValueError(
                    "Stable version: unreadable from main. Fix main."
                ) from error
            main_tag = f"v{main_version}"
            main_tags = git_output(
                ["tag", "--merged", main_ref], root
            ).splitlines()
            tag_version = ""
            if main_tag in main_tags:
                try:
                    tag_version = str(
                        json.loads(
                            git_output(
                                [
                                    "show",
                                    f"{main_tag}:.csarc/release-please-manifest.json",
                                ],
                                root,
                            )
                        )["."]
                    )
                except (
                    subprocess.CalledProcessError,
                    json.JSONDecodeError,
                    KeyError,
                ):
                    tag_version = ""
            if stable.is_prerelease or tag_version != main_version:
                if stable.core > release_phase.parse_version(base_core).core:
                    raise ValueError(
                        "Main version: no reachable stable tag. Fetch tags."
                    )
            elif stable.core > release_phase.parse_version(base_core).core:
                base_core = stable.core_string()
                version = (
                    bump_version(base_core, messages, maturity=maturity)
                    or version
                )
    if phase is not None:
        version = release_phase.phase_version(
            version, phase, existing=all_tags, maturity=maturity
        )
    return f"v{version}", version


def release_plan_report(
    root: Path,
    sha: str,
    *,
    phase: str | None = None,
    checkpoint_role: str = "none",
    source_sha: str | None = None,
) -> dict[str, object]:
    """Describe the one local release decision without changing the repo."""
    if source_sha:
        trees = {
            git_output(["rev-parse", f"{revision}^{{tree}}"], root)
            for revision in (sha, source_sha)
        }
        if len(trees) != 1:
            raise ValueError(
                "Release source tree: differs from merge. Inspect it."
            )
    planned = release_plan(root, source_sha or sha, phase=phase)
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
        if checkpoint_role == "deferred":
            if materialized:
                raise ValueError(
                    "Deferred checkpoint work: has a version. Remove it."
                )
            status = "deferred"
            reason = "checkpoint work defers its release to the terminal Issue"
    return {
        "status": status,
        "tag": tag,
        "version": version,
        "materialized": materialized,
        "reason": reason,
    }


def verify_candidate_version(root: Path, base_sha: str) -> tuple[str, str, str]:
    """Recompute the candidate version from its current base commit."""
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git: not found. Install Git for release planning.")
    candidate_sha = git_output(["rev-parse", "HEAD"], root)
    source_sha = git_output(["merge-base", candidate_sha, base_sha], root)
    new_base_log = git_output(
        ["log", "--format=%H%x1f%s%x1f%b%x1e", f"{source_sha}..{base_sha}"],
        root,
    )
    new_base_commits = []
    for entry in new_base_log.split("\x1e"):
        fields = entry.strip("\n").split("\x1f", 2)
        if len(fields) == 2:
            fields.append("")
        if len(fields) == 3:
            new_base_commits.append(fields)
    release_worthy = [
        (sha, subject)
        for sha, subject, body in new_base_commits
        if bump_version("0.0.0", [f"{subject}\n{body}"]) is not None
    ]
    if release_worthy:
        commits = ", ".join(
            f"{sha[:12]} {subject}" for sha, subject in release_worthy
        )
        raise ValueError(
            f"Release candidate {candidate_sha}: built from {source_sha}, "
            f"but base {base_sha} adds release-worthy commits: "
            f"{commits}. Update the same Release PR and revalidate."
        )
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
        raise ValueError(
            "Candidate base: no release-worthy commits. Do not release."
        )
    _, expected = planned
    verify_release_version(root, expected)
    return expected, candidate_sha, source_sha


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
        raise ValueError(f"Governed version: not found in {path.name}. Add it.")
    path.write_text(updated, encoding="utf-8")


def _pep440_equivalent(version: str) -> str:
    """Return `version`'s PEP 440-normalized form (Issue #744)."""
    parsed = release_phase.parse_version(version)
    return release_phase.format_pep440(
        parsed.major, parsed.minor, parsed.patch, parsed.phase, parsed.n
    )


def _target_version(version: str, relative_path: str) -> str:
    """Return the version string to write into one governed surface."""
    return (
        _pep440_equivalent(version)
        if _is_pep440_surface(relative_path)
        else version
    )


def _write_release_version(root: Path, version: str) -> None:  # noqa: C901
    """Materialize only version surfaces declared by release configuration."""
    config = json.loads(
        (root / ".csarc/release-please-config.json").read_text(encoding="utf-8")
    )
    package = config["packages"]["."]
    release_type = package.get("release-type", config.get("release-type"))
    manifest = root / ".csarc/release-please-manifest.json"
    manifest.write_text(
        json.dumps({".": version}, indent=2) + "\n", encoding="utf-8"
    )
    if release_type == "simple":
        (root / ".csarc/version.txt").write_text(
            f"{version}\n", encoding="utf-8"
        )
    elif release_type == "python":
        _replace_toml_version(
            root / "pyproject.toml",
            "project",
            _target_version(version, "pyproject.toml"),
        )
    elif release_type == "node":
        path = root / "package.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["version"] = version
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    elif release_type == "rust":
        _replace_toml_version(root / "Cargo.toml", "package", version)
    else:
        raise ValueError(f"Release type {release_type}: unsupported. Fix it.")

    for item in package.get("extra-files", []):
        if isinstance(item, str):
            kind, value, jsonpath = "generic", item, ""
        elif isinstance(item, dict):
            kind = str(item.get("type", "generic"))
            value = item.get("path")
            jsonpath = str(item.get("jsonpath", ""))
        else:
            raise ValueError("Release extra-file: invalid entry. Fix it.")
        if not isinstance(value, str):
            raise ValueError("Release extra-file: invalid path. Fix it.")
        path = root / value
        target_version = _target_version(version, value)
        if kind == "generic":
            source = path.read_text(encoding="utf-8")
            lines = []
            changed = False
            for line in source.splitlines(keepends=True):
                if "x-release-please-version" in line:
                    line, count = re.subn(
                        r"(?P<prefix>v?)\d+\.\d+\.\d+"
                        r"(?:-[0-9A-Za-z.-]+)?",
                        rf"\g<prefix>{target_version}",
                        line,
                        count=1,
                    )
                    changed = changed or count == 1
                lines.append(line)
            if not changed:
                raise ValueError(f"{value}: no release version marker. Add it.")
            path.write_text("".join(lines), encoding="utf-8")
        elif kind == "toml" and jsonpath == "$.project.version":
            _replace_toml_version(path, "project", target_version)
        elif kind == "toml" and jsonpath == "$.package.version":
            _replace_toml_version(path, "package", target_version)
        elif kind == "toml" and jsonpath.startswith("$.package["):
            match = re.search(r'name\.value=="([^"]+)"', jsonpath)
            if match is None:
                raise ValueError(
                    f"Release jsonpath {jsonpath}: unsupported. Fix it."
                )
            _replace_toml_version(
                path, "package", target_version, package_name=match.group(1)
            )
        else:
            raise ValueError(
                f"Release extra-file {value}: unsupported. Fix it."
            )

    cargo_manifest = root / "Cargo.toml"
    cargo_lock = root / "Cargo.lock"
    if cargo_manifest.is_file() and cargo_lock.is_file():
        with cargo_manifest.open("rb") as source:
            cargo_package = tomllib.load(source).get("package", {})
        cargo_name = cargo_package.get("name")
        if not isinstance(cargo_name, str) or not cargo_name:
            raise ValueError("Cargo.toml: no package name. Add it.")
        _replace_toml_version(
            cargo_lock, "package", version, package_name=cargo_name
        )


def _changelog_boundary(
    root: Path, tags: list[str], version: str
) -> tuple[str, list[str]]:
    """Return the notes' starting tag and any prereleases a stable covers."""
    valid = [tag for tag in tags if release_phase.is_valid_version(tag)]
    if release_phase.parse_version(version).is_prerelease:
        ordered = release_phase.sort_by_precedence(valid)
        return (ordered[-1] if ordered else ""), []
    stables = release_phase.sort_by_precedence(
        tag
        for tag in valid
        if not release_phase.parse_version(tag).is_prerelease
    )
    latest = stables[-1] if stables else ""
    covered = (
        set(git_output(["tag", "--merged", latest], root).splitlines())
        if latest
        else set()
    )
    included = release_phase.sort_by_precedence(
        tag
        for tag in valid
        if tag not in covered and release_phase.parse_version(tag).is_prerelease
    )
    return latest, included


def _changelog_heads(root: Path, sha: str) -> list[str]:
    """Return the commits whose history the notes for ``sha`` describe."""
    parents = git_output(
        ["rev-list", "--parents", "-n", "1", sha], root
    ).split()[1:]
    return parents if len(parents) > 1 else [sha]


def _changelog_records(raw: str) -> list[tuple[str, str, str]]:
    """Split ``%h%x1f%s%x1f%b%x1e`` log output into (sha, subject, body)."""
    records: list[tuple[str, str, str]] = []
    for record in raw.split("\x1e"):
        if not record.strip():
            continue
        # Output stripping can drop an empty body's separator (\x1f is
        # whitespace to str.strip), so pad the missing field.
        fields = [*record.strip("\n").split("\x1f", 2), ""]
        records.append((fields[0], fields[1], fields[2]))
    return records


def _migration_note(short_sha: str, body: str) -> str:
    """Return one breaking commit's migration bullets, one per footer."""
    notes = _breaking_notes(body) or [
        "no BREAKING CHANGE footer was recorded; read the linked pull "
        "request before upgrading"
    ]
    return "\n".join(f"* {short_sha}: {note}" for note in notes)


def _migration_section(
    version: str, latest: str, migrations: list[str]
) -> list[str]:
    """Return the notes section that tells consumers how to cross a break."""
    if not migrations:
        return []
    recovery = f"stay on or reinstall {latest}" if latest else "do not upgrade"
    return [
        "",
        "### Migration notes",
        "",
        f"* Minimum version for the changed behavior: {version}; "
        f"to recover, {recovery}.",
        *migrations,
    ]


def _write_changelog(root: Path, sha: str, version: str) -> None:
    """Prepend deterministic notes for the same commits used by planning."""
    changelog = root / "CHANGELOG.md"
    source = changelog.read_text(encoding="utf-8")
    if re.search(rf"(?m)^## (?:\[)?v?{re.escape(version)}(?:\]|\s|\()", source):
        return
    tags = git_output(["tag", "--merged", sha], root).splitlines()
    latest, included = _changelog_boundary(root, tags, version)
    heads = _changelog_heads(root, sha)
    revision = [*heads, f"^{latest}"] if latest else heads
    raw = git_output(
        ["log", "--reverse", "--format=%h%x1f%s%x1f%b%x1e", *revision], root
    )
    notes: dict[str, list[str]] = {
        "Breaking Changes": [],
        "Features": [],
        "Bug Fixes": [],
    }
    migrations: list[str] = []
    for short_sha, subject, body in _changelog_records(raw):
        intent = release_intent(subject)
        if _is_breaking(subject, body):
            intent = "major"
            migrations.append(_migration_note(short_sha, body))
        heading = {
            "major": "Breaking Changes",
            "minor": "Features",
            "patch": "Bug Fixes",
        }.get(intent)
        if heading:
            notes[heading].append(f"* {subject} ({short_sha})")
    date = git_output(["show", "-s", "--format=%cs", heads[0]], root)
    sections = [f"## [{version}] - {date}"]
    if included:
        sections.extend(
            ["", "### Included prereleases", "", *(f"* {t}" for t in included)]
        )
    for heading, entries in notes.items():
        if entries:
            sections.extend(["", f"### {heading}", "", *entries])
    sections.extend(_migration_section(version, latest, migrations))
    entry = "\n".join(sections) + "\n\n"
    marker = source.find("\n## ")
    if marker == -1:
        updated = source.rstrip() + "\n\n" + entry
    else:
        updated = source[: marker + 1] + entry + source[marker + 1 :]
    changelog.write_text(updated, encoding="utf-8")


def prepare_release_candidate(
    root: Path,
    sha: str,
    *,
    phase: str | None = None,
    changelog_sha: str | None = None,
) -> dict[str, object]:
    """Write a local candidate; never create a PR, tag, or GitHub Release."""
    planned = release_plan(root, sha, phase=phase)
    if planned is None:
        raise ValueError(
            "Release: no release-worthy Conventional Commits. Do not release."
        )
    tag, version = planned
    if tag in git_output(["tag", "--points-at", sha], root).splitlines():
        raise ValueError(
            f"Tag {tag}: already on this commit. Do not release again."
        )
    _write_release_version(root, version)
    _write_changelog(root, changelog_sha or sha, version)
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


def _promotion_baseline_tree(root: Path, source_sha: str, head_sha: str) -> str:
    """Return the deterministic pre-release tree for a promotion head."""
    source_tree = git_output(["rev-parse", f"{source_sha}^{{tree}}"], root)
    parents = git_output(
        ["rev-list", "--parents", "-n", "1", head_sha], root
    ).split()
    if parents == [head_sha, source_sha]:
        return source_tree
    if len(parents) != 3 or parents[1] != source_sha:
        raise ValueError(
            "Promotion head: first parent is not the delivery source. Fix it."
        )

    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git: not found. Install Git for release planning.")
    merged = subprocess.run(  # noqa: S603
        [executable, "merge-tree", "--write-tree", source_sha, parents[2]],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    first_line = merged.stdout.splitlines()[0] if merged.stdout else ""
    if merged.returncode == 0:
        return git_output(["rev-parse", f"{first_line}^{{tree}}"], root)
    if re.fullmatch(r"[0-9a-f]{40,64}", first_line):
        return source_tree
    raise RuntimeError(
        "Promotion baseline: Git cannot rebuild it. Fetch full history."
    )


def verify_promotion_version(
    root: Path,
    source_sha: str,
    head_sha: str,
    *,
    phase: str,
    context: str = "promotion",
) -> dict[str, object]:
    """Require a release tree to equal its deterministic candidate."""
    baseline_tree = _promotion_baseline_tree(root, source_sha, head_sha)
    head_tree = git_output(["rev-parse", f"{head_sha}^{{tree}}"], root)
    # A release-only commit was prepared on its parent (the source). A
    # promotion bridge was prepared on the bridge itself, whose second parent
    # brings main's previous stable tag into reach (Issue #1018).
    head_parents = git_output(
        ["rev-list", "--parents", "-n", "1", head_sha], root
    ).split()
    changelog_sha = head_sha if len(head_parents) > 2 else source_sha
    planned = release_plan(root, head_sha, phase=phase)
    if planned is None:
        if head_tree != baseline_tree:
            raise ValueError(
                f"No-release {context}: baseline tree changed. Restore it."
            )
        return {
            "status": "no-release",
            "materialized": False,
            "source_sha": source_sha,
            "head_sha": head_sha,
        }

    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git: not found. Install Git for release planning.")
    with tempfile.TemporaryDirectory(prefix="csarc-promotion-version-") as path:
        worktree = Path(path) / "worktree"
        subprocess.run(  # noqa: S603
            [
                executable,
                "worktree",
                "add",
                "--detach",
                "--force",
                str(worktree),
                source_sha,
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        try:
            subprocess.run(  # noqa: S603
                [executable, "read-tree", "--reset", "-u", baseline_tree],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = prepare_release_candidate(
                worktree,
                head_sha,
                phase=phase,
                changelog_sha=changelog_sha,
            )
            subprocess.run(  # noqa: S603
                [executable, "add", "--all"],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
            )
            expected_tree = git_output(["write-tree"], worktree)
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
    if head_tree != expected_tree:
        expected_paths = git_output(
            ["diff", "--name-only", baseline_tree, expected_tree], root
        ).splitlines()
        actual_paths = git_output(
            ["diff", "--name-only", baseline_tree, head_sha], root
        ).splitlines()
        raise ValueError(
            f"{context} release materialization: not exact: expected "
            f"{expected_paths or ['no changed files']}, got "
            f"{actual_paths or ['no changed files']}. Rerun it."
        )
    return {
        **payload,
        "materialized": True,
        "source_sha": source_sha,
        "head_sha": head_sha,
        "tree": head_tree,
    }


def _manifest_version(root: Path, revision: str) -> object:
    manifest = json.loads(
        git_output(["show", f"{revision}:.release-please-manifest.json"], root)
    )
    return manifest.get(".") if isinstance(manifest, dict) else None


def branch_release_intent(root: Path, base_sha: str, head_sha: str) -> str:
    """Return the highest release intent among the branch-only commits."""
    raw = git_output(
        ["log", "--format=%s%x1f%b%x1e", f"{base_sha}..{head_sha}"], root
    )
    highest = "no-release"
    for message in raw.split("\x1e"):
        subject, _, body = message.strip("\n").partition("\x1f")
        if not subject:
            continue
        intent = release_intent(subject)
        if "BREAKING CHANGE:" in body or "BREAKING-CHANGE:" in body:
            intent = "major"
        if INTENT_RANK[intent] > INTENT_RANK[highest]:
            highest = intent
    return highest


def pull_request_title_errors(
    root: Path, base_sha: str, head_sha: str, title: str
) -> list[str]:
    """Reject a PR title whose release intent differs from its commits."""
    title_intent = release_intent(title)
    commit_intent = branch_release_intent(root, base_sha, head_sha)
    if title_intent == commit_intent:
        return []
    return [
        f"PR title release intent is {title_intent}, but the highest "
        f"branch commit intent is {commit_intent}; the squash merge keeps "
        "only the title, so the version materialized on this branch would "
        "not hold after merge. Change the PR title type to match the "
        "highest branch commit type, or move the higher-type commits to a "
        "separate pull request."
    ]


def breaking_migration_errors(
    root: Path, base_sha: str, head_sha: str, title: str
) -> list[str]:
    """Reject a breaking pull request that records no migration text."""
    raw = git_output(
        ["log", "--format=%s%x1f%b%x1e", f"{base_sha}..{head_sha}"], root
    )
    breaking = release_intent(title) == "major"
    documented = False
    for message in raw.split("\x1e"):
        subject, _, body = message.strip("\n").partition("\x1f")
        if not subject:
            continue
        breaking = breaking or _is_breaking(subject, body)
        documented = documented or bool(_breaking_notes(body))
    if not breaking or documented:
        return []
    return [
        "the pull request declares a breaking change, but no branch commit "
        "records migration text in a `BREAKING CHANGE:` footer; the squash "
        "merge keeps only those footers, so the CHANGELOG Migration notes "
        "would be empty. Add a commit whose body ends with `BREAKING "
        "CHANGE: <how to migrate>`, or remove the breaking marker."
    ]


def verify_delivery_version(
    root: Path,
    base_sha: str,
    head_sha: str,
    *,
    phase: str,
    checkpoint_role: str = "none",
    pr_title: str | None = None,
) -> dict[str, object]:
    """Require release-worthy work to end in one exact release-only commit."""
    if pr_title is not None:
        migration_errors = breaking_migration_errors(
            root, base_sha, head_sha, pr_title
        )
        if migration_errors:
            raise ValueError(migration_errors[0])
    if pr_title is not None and checkpoint_role != "deferred":
        title_errors = pull_request_title_errors(
            root, base_sha, head_sha, pr_title
        )
        if title_errors:
            raise ValueError(title_errors[0])
    planned = release_plan(root, head_sha, phase=phase)
    if planned is None:
        return {
            "status": "no-release",
            "materialized": False,
            "base_sha": base_sha,
            "head_sha": head_sha,
        }
    if checkpoint_role == "deferred":
        if _manifest_version(root, head_sha) != _manifest_version(
            root, base_sha
        ):
            raise ValueError(
                "Deferred checkpoint work: materializes a version. Only the "
                "terminal Issue releases the beta."
            )
        return {
            "status": "deferred",
            "materialized": False,
            "base_sha": base_sha,
            "head_sha": head_sha,
        }
    if git_output(["merge-base", base_sha, head_sha], root) != base_sha:
        raise ValueError(
            "Release-worthy delivery: lacks the destination base. Merge "
            "it before materialization."
        )
    parents = git_output(
        ["rev-list", "--parents", "-n", "1", head_sha], root
    ).split()
    if len(parents) != 2:
        raise ValueError(
            "Release-worthy delivery: no final release-only commit. Add it."
        )
    payload = verify_promotion_version(
        root,
        parents[1],
        head_sha,
        phase=phase,
        context="delivery",
    )
    return {**payload, "base_sha": base_sha}


def release_version_errors(  # noqa: C901
    root: Path, expected: str | None = None, *, require_changelog: bool = True
) -> list[str]:
    """Return every release surface that disagrees with the source version."""
    versions: dict[str, str] = {}
    errors: list[str] = []
    version_file = root / ".csarc/version.txt"
    if version_file.is_file():
        versions[".csarc/version.txt"] = version_file.read_text(
            encoding="utf-8"
        ).strip()

    manifest_path = root / ".csarc/release-please-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        versions[".csarc/release-please-manifest.json"] = str(
            manifest.get(".", "")
        )
    else:
        errors.append(".csarc/release-please-manifest.json is missing")

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
    release_config = root / ".csarc/release-please-config.json"
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
            # A PEP 440 surface's marker (Issue #744's `_is_pep440_surface`,
            # e.g. `src/<package>/__init__.py`) holds the compact
            # `b1` form instead of the canonical `-beta.1`
            # segment; match either so its phase suffix is not silently
            # dropped from `versions` below.
            match = re.search(r"v?(\d+\.\d+\.\d+(?:-beta\.\d+|b\d+)?)", line)
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
    try:
        parsed_source = release_phase.parse_version(source_version)
        expected_pep440 = release_phase.format_pep440(
            parsed_source.major,
            parsed_source.minor,
            parsed_source.patch,
            parsed_source.phase,
            parsed_source.n,
        )
    except release_phase.ReleasePhaseError:
        errors.append(f"invalid release version: {source_version}")
        expected_pep440 = source_version
    errors.extend(
        f"{path} is {version}, expected "
        f"{expected_pep440 if _is_pep440_surface(path) else source_version}"
        for path, version in versions.items()
        if version
        != (expected_pep440 if _is_pep440_surface(path) else source_version)
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
    version_file = root / ".csarc/version.txt"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    manifest = json.loads(
        (root / ".csarc/release-please-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return str(manifest["."])


def dispatch(args: argparse.Namespace) -> int:  # noqa: C901
    """Run one parsed CSARC release command (all but `preflight`)."""
    if args.command == "verify-release-follow-up":
        commit_pages = json.loads(args.commits.read_text(encoding="utf-8"))
        if not isinstance(commit_pages, list) or any(
            not isinstance(page, list)
            or any(not isinstance(commit, dict) for commit in page)
            for page in commit_pages
        ):
            raise SystemExit(
                "ERROR: Release follow-up commit: invalid response. Retry."
            )
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
        print("OK: Release follow-up source is verified.")  # noqa: T201
        return 0
    if args.command == "plan":
        try:
            payload = release_plan_report(
                args.root.resolve(),
                args.sha,
                phase=args.phase,
                checkpoint_role=args.checkpoint_role,
                source_sha=args.source_sha,
            )
        except (ValueError, json.JSONDecodeError) as error:
            raise SystemExit(str(error)) from error
        write_plan_report(payload, args.output, args.github_output)
        return 0
    if args.command == "prepare-candidate":
        try:
            payload = prepare_release_candidate(
                args.root.resolve(), args.sha, phase=args.phase
            )
        except (ValueError, json.JSONDecodeError) as error:
            raise SystemExit(str(error)) from error
        write_plan_report(payload, None, None)
        return 0
    if args.command == "retention-plan":
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit(
                "ERROR: retention-plan: no token to list Releases. Set "
                "GH_TOKEN or GITHUB_TOKEN."
            )
        api = GitHubAPI(
            token, os.environ.get("GITHUB_API_URL", "https://api.github.com")
        )
        payload = retention_report(api, args.repo)
        write_retention_report(payload, args.output, args.github_output)
        return 0
    if args.command == "verify-candidate-version":
        try:
            version, candidate_sha, source_sha = verify_candidate_version(
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
            f"OK: Release candidate {candidate_sha} from source {source_sha} "
            f"matches current base {args.base_sha} decision {version}."
        )
        return 0
    if args.command in {"verify-delivery-version", "verify-promotion-version"}:
        try:
            phase = args.phase
            if args.tag is not None:
                version = args.tag.removeprefix("v")
                if not release_phase.is_valid_version(version):
                    raise ValueError(
                        f"Release tag {args.tag}: invalid. Fix it."
                    )
                phase = release_phase.parse_version(version).release_kind
            if phase is None:
                raise ValueError("Release phase: missing. Pass --phase.")
            if args.command == "verify-delivery-version":
                payload = verify_delivery_version(
                    args.root.resolve(),
                    args.base_sha,
                    args.head_sha,
                    phase=phase,
                    checkpoint_role=args.checkpoint_role,
                    pr_title=args.pr_title,
                )
            else:
                payload = verify_promotion_version(
                    args.root.resolve(),
                    args.source_sha,
                    args.head_sha,
                    phase=phase,
                )
            if args.tag is not None and payload.get("tag") != args.tag:
                raise ValueError(
                    f"{args.command}: planned {payload.get('tag')}, "
                    f"expected {args.tag}. Fix the tag."
                )
        except (
            ValueError,
            json.JSONDecodeError,
            subprocess.CalledProcessError,
            tomllib.TOMLDecodeError,
        ) as error:
            raise SystemExit(str(error)) from error
        print(json.dumps(payload, sort_keys=True))  # noqa: T201
        return 0
    if args.command == "verify-version":
        tag = args.tag
        expected = None
        if tag is not None:
            candidate_version = tag.removeprefix("v")
            if not release_phase.is_valid_version(candidate_version):
                raise SystemExit(f"ERROR: Release tag {tag}: invalid. Fix it.")
            expected = candidate_version
        try:
            version = verify_release_version(args.root.resolve(), expected)
        except (
            ValueError,
            json.JSONDecodeError,
            tomllib.TOMLDecodeError,
        ) as error:
            raise SystemExit(str(error)) from error
        print(f"OK: Release version {version} is consistent.")  # noqa: T201
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
    raise SystemExit(
        f"ERROR: Command {args.command}: unsupported. Run with --help."
    )
