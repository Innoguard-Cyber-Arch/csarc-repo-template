"""Deterministic repository lifecycle commands backed by Copier."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, NoReturn, Protocol, cast
from urllib.parse import quote

import yaml  # type: ignore[import-untyped]
from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfbase.pdfmetrics import (  # type: ignore[import-untyped]
    stringWidth,
)
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

CANONICAL_SOURCE = (
    "https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git"
)
CANONICAL_REPOSITORY = "Innoguard-Cyber-Arch/csarc-repo-template"
CANONICAL_REPOSITORY_ID = 1_340_899_393
DEFAULT_OWNER = "@Innoguard-Cyber-Arch/arch"
CONFIG_FILE = Path(".csarc/config.yml")
LEGACY_ANSWERS_FILE = Path(".copier-answers.yml")
PROVENANCE_FILE = Path(".csarc/provenance.json")
PENDING_ADOPTION_FILE = Path(".csarc/adoption-pending.json")
ADOPTION_REPORT_BASENAME = "csarc-adoption-dry-run"
ADOPTION_PLAN_BASENAME = "csarc-adoption-plan.json"
AGENTS_BLOCK_START = "<!-- BEGIN CSARC MANAGED BLOCK -->"
AGENTS_BLOCK_END = "<!-- END CSARC MANAGED BLOCK -->"
FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
REPOSITORY_VISIBILITIES = {"public", "private", "internal"}
RELEASE_OWNERSHIPS = {"csarc-owned", "product-owned", "verification-only"}
RELEASE_WRITER_MARKERS = (
    "gh release create",
    "gh release edit",
    "gh release upload",
    "googleapis/release-please-action@",
    "ncipollo/release-action@",
    "softprops/action-gh-release@",
)
INSTALL_STATE_CREATE = "create"
INSTALL_STATE_ADOPT = "adopt"
INSTALL_STATE_UPDATE = "update"
INSTALL_STATE_CURRENT = "current"
INSTALL_STATE_POLICY_ONLY = "policy-only-update"
INSTALL_STATE_NEXT_COMMAND = {
    INSTALL_STATE_CREATE: (
        "csarc init <path> --dry-run to preview, then --yes --non-interactive"
    ),
    INSTALL_STATE_ADOPT: (
        "csarc adopt <path> to write a dry-run plan, review it, then "
        "csarc adopt <path> --apply-plan <plan>"
    ),
    INSTALL_STATE_UPDATE: (
        "csarc update <path> --check to preview, then csarc update <path>"
    ),
    INSTALL_STATE_CURRENT: "no action needed",
    INSTALL_STATE_POLICY_ONLY: (
        "scripts/apply-repository-settings.sh plan to preview, then "
        "scripts/apply-repository-settings.sh apply"
    ),
}
POLICY_CHECK_COMPLETED_MARKER = "Repository settings check failed with"
LEGACY_MILESTONE_HEADINGS = (
    "problem",
    "outcome",
    "acceptance criteria",
    "out of scope",
    "verification",
    "source",
)
CURRENT_MILESTONE_HEADINGS = (
    "problem",
    "outcome",
    "acceptance criteria",
    "plan",
    "out of scope",
    "verification",
    "references",
)


class CliError(RuntimeError):
    """An expected command error with an actionable message."""


class ProjectVerificationError(CliError):
    """A verification failure with precise project-hook evidence."""

    def __init__(self, message: str, hook: dict[str, object]) -> None:
        """Preserve the failure message and structured hook result."""
        super().__init__(message)
        self.hook = hook


@dataclass(frozen=True)
class Revision:
    """A reviewed template revision resolved to an immutable commit."""

    label: str
    sha: str
    source: str
    repository: str | None = None
    repository_id: int | None = None
    release_id: int | None = None
    tag_object_sha: str | None = None
    immutable: bool = False
    attestation_verified: bool = False
    signature_verified: bool = False

    @property
    def verified(self) -> bool:
        """Return whether the full production trust chain passed."""
        return all(
            (
                self.repository == CANONICAL_REPOSITORY,
                self.repository_id == CANONICAL_REPOSITORY_ID,
                self.release_id is not None,
                self.immutable,
                self.attestation_verified,
                self.signature_verified,
            )
        )

    @property
    def guide_url(self) -> str:
        """Return the installer guide pinned to this exact commit."""
        if not self.verified:
            return "unavailable-for-unverified-development-source"
        return (
            "https://raw.githubusercontent.com/"
            f"{CANONICAL_REPOSITORY}/{self.sha}/docs/agent-install.md"
        )


@dataclass(frozen=True)
class TagResolution:
    """A tag reference and its recursively dereferenced commit."""

    object_sha: str
    commit_sha: str


class ReleaseClient(Protocol):
    """Injectable boundary for GitHub release verification."""

    def repository(self) -> dict[str, object]:
        """Return canonical repository metadata."""

    def release(self, tag: str | None) -> dict[str, object]:
        """Return the latest or named release metadata."""

    def resolve_tag(self, tag: str) -> TagResolution:
        """Resolve a tag to its current commit."""

    def verify_release(self, tag: str) -> None:
        """Verify the GitHub release attestation."""

    def verify_commit(self, sha: str) -> None:
        """Verify the commit signature through GitHub."""


@dataclass(frozen=True)
class Plan:
    """File effects for an init or adoption operation."""

    add: tuple[str, ...]
    overwrite: tuple[str, ...]
    preserve: tuple[str, ...]
    merge: tuple[str, ...]
    manual: tuple[str, ...]
    unknown: tuple[str, ...]


@dataclass(frozen=True)
class RepositoryContext:
    """Resolved GitHub identity used to choose repository-safe defaults."""

    repository: str | None
    owner: str | None
    owner_type: str | None
    visibility: str
    source: str
    verified: bool
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-safe repository context."""
        return {
            "owner": self.owner,
            "owner_type": self.owner_type,
            "reason": self.reason,
            "repository": self.repository,
            "source": self.source,
            "verified": self.verified,
            "visibility": self.visibility,
        }


@dataclass(frozen=True)
class ResolvedPlan:
    """Single plan model shared by terminal and JSON output."""

    mode: str
    target: Path
    revision: Revision
    repository: RepositoryContext
    answers: dict[str, object]
    capabilities: dict[str, object]
    files: Plan | None = None
    update: dict[str, object] | None = None
    adoption: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        """Return the stable machine-readable plan representation."""
        result: dict[str, object] = {
            "answers": dict(sorted(self.answers.items())),
            "mode": self.mode,
            "release": release_contract(self.answers),
            "release_capabilities": self.capabilities,
            "release_ownership": release_ownership(self.answers),
            "repository": self.repository.as_dict(),
            "schema_version": 1,
            "target": str(self.target),
            "template": {
                "guide_url": self.revision.guide_url,
                "release": self.revision.label,
                "sha": self.revision.sha,
                "source": self.revision.source,
                "verification": (
                    "verified" if self.revision.verified else "unverified"
                ),
            },
        }
        if self.files is not None:
            result["files"] = {
                "add": list(self.files.add),
                "automatic_merge": list(self.files.merge),
                "manual_merge": list(self.files.manual),
                "overwrite": list(self.files.overwrite),
                "preserve": list(self.files.preserve),
                "unknown": list(self.files.unknown),
            }
        if self.update is not None:
            result.update(self.update)
        if self.adoption is not None:
            result["adoption"] = self.adoption
        return result


@dataclass(frozen=True)
class PolicyCheckResult:
    """Outcome of comparing live repository settings with checked-in policy."""

    available: bool
    drifted: bool | None
    detail: str


@dataclass(frozen=True)
class MilestoneDescriptionChange:
    """One legacy Milestone description that can be upgraded safely."""

    number: int
    title: str
    before: str
    after: str


@dataclass(frozen=True)
class MilestoneDescriptionPlan:
    """Read-only classification of a repository's Milestone descriptions."""

    repository: str
    changes: tuple[MilestoneDescriptionChange, ...]
    current: tuple[tuple[int, str], ...]
    review: tuple[tuple[int, str], ...]


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess without invoking a shell."""
    return subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture,
    )


def github_repository(source: str) -> str | None:
    """Extract owner/repository from a GitHub template source."""
    match = re.search(
        r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/|gh:)"
        r"([^/]+)/([^/#]+?)(?:\.git)?/?$",
        source,
    )
    if match is None:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def git_commit(source: Path, reference: str) -> str:
    """Resolve a local Git reference to a full commit SHA."""
    result = run(
        ["git", "-C", str(source), "rev-parse", f"{reference}^{{commit}}"],
        capture=True,
        check=False,
    )
    sha = result.stdout.strip()
    if result.returncode != 0 or FULL_SHA.fullmatch(sha) is None:
        raise CliError(f"Cannot resolve template revision {reference!r}.")
    return sha.lower()


def gh_json(endpoint: str) -> dict[str, object]:
    """Read one GitHub API object through the authenticated gh CLI."""
    try:
        result = run(
            ["gh", "api", "--method", "GET", endpoint],
            capture=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise CliError(
            "GitHub CLI is required to resolve template releases."
        ) from error
    if result.returncode != 0:
        detail = result.stderr.strip() or "GitHub API request failed"
        raise CliError(f"Cannot resolve an approved GitHub Release: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CliError(
            "GitHub returned invalid JSON for the release."
        ) from error
    if not isinstance(payload, dict):
        raise CliError("GitHub returned an unexpected release response.")
    return payload


class GhReleaseClient:
    """GitHub CLI implementation of the release trust boundary."""

    def repository(self) -> dict[str, object]:
        """Return canonical repository metadata."""
        return gh_json(f"repos/{CANONICAL_REPOSITORY}")

    def release(self, tag: str | None) -> dict[str, object]:
        """Return the latest or named canonical release."""
        if tag is None or tag == "latest":
            endpoint = f"repos/{CANONICAL_REPOSITORY}/releases/latest"
        else:
            endpoint = (
                f"repos/{CANONICAL_REPOSITORY}/releases/tags/"
                f"{quote(tag, safe='')}"
            )
        return gh_json(endpoint)

    def resolve_tag(self, tag: str) -> TagResolution:
        """Resolve lightweight or nested annotated tags."""
        payload = gh_json(
            f"repos/{CANONICAL_REPOSITORY}/git/ref/tags/{quote(tag, safe='')}"
        )
        target = payload.get("object")
        if not isinstance(target, dict):
            raise CliError(f"GitHub tag {tag!r} has no target object.")
        object_sha = target.get("sha")
        target_type = target.get("type")
        target_sha = object_sha
        visited: set[str] = set()
        while target_type == "tag" and isinstance(target_sha, str):
            if target_sha in visited:
                raise CliError(f"GitHub tag {tag!r} contains a cycle.")
            visited.add(target_sha)
            tag_payload = gh_json(
                f"repos/{CANONICAL_REPOSITORY}/git/tags/{target_sha}"
            )
            target = tag_payload.get("object")
            if not isinstance(target, dict):
                raise CliError(f"GitHub tag {tag!r} has an invalid object.")
            target_type = target.get("type")
            target_sha = target.get("sha")
        if (
            target_type != "commit"
            or not isinstance(target_sha, str)
            or FULL_SHA.fullmatch(target_sha) is None
            or not isinstance(object_sha, str)
            or FULL_SHA.fullmatch(object_sha) is None
        ):
            raise CliError(f"GitHub tag {tag!r} does not resolve to a commit.")
        return TagResolution(object_sha.lower(), target_sha.lower())

    def verify_release(self, tag: str) -> None:
        """Require a valid GitHub release attestation."""
        result = run(
            [
                "gh",
                "release",
                "verify",
                tag,
                "-R",
                CANONICAL_REPOSITORY,
                "--format",
                "json",
            ],
            capture=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or "attestation is unavailable"
            raise CliError(f"Release attestation verification failed: {detail}")
        try:
            attestation = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise CliError(
                "Release attestation returned invalid JSON."
            ) from error
        if not attestation:
            raise CliError("Release attestation response is empty.")

    def verify_commit(self, sha: str) -> None:
        """Require GitHub to report a valid commit signature."""
        payload = gh_json(f"repos/{CANONICAL_REPOSITORY}/commits/{sha}")
        commit = payload.get("commit")
        verification = (
            commit.get("verification") if isinstance(commit, dict) else None
        )
        if (
            not isinstance(verification, dict)
            or verification.get("verified") is not True
        ):
            reason = (
                verification.get("reason", "unknown")
                if isinstance(verification, dict)
                else "missing"
            )
            raise CliError(f"Commit signature verification failed ({reason}).")


def resolve_unreleased_revision(source: str, requested: str | None) -> Revision:
    """Resolve an explicitly allowed development-only revision."""
    source_path = Path(source).expanduser()
    if not source_path.is_dir():
        raise CliError(
            "--allow-unreleased template source is unavailable; use a local "
            "Git repository."
        )
    if requested is not None and FULL_SHA.fullmatch(requested):
        return Revision(
            requested.lower(), git_commit(source_path, requested), source
        )
    label = requested or "latest-local-tag"
    reference = requested
    if reference is None:
        tags = run(
            ["git", "-C", str(source_path), "tag", "--sort=-version:refname"],
            capture=True,
        ).stdout.splitlines()
        if not tags:
            raise CliError("Local template repository has no release tags.")
        reference = tags[0]
    return Revision(label, git_commit(source_path, reference), source)


def release_identity(release: dict[str, object]) -> tuple[str, int]:
    """Validate stable immutable release metadata."""
    tag = release.get("tag_name")
    release_id = release.get("id")
    if not isinstance(tag, str) or not tag or not isinstance(release_id, int):
        raise CliError("GitHub returned incomplete release metadata.")
    if (
        release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise CliError("Only published, stable GitHub Releases are approved.")
    if not isinstance(release.get("published_at"), str):
        raise CliError("The selected GitHub Release is not published.")
    if release.get("immutable") is not True:
        raise CliError("The selected GitHub Release is not immutable.")
    return tag, release_id


def resolve_revision(
    source: str,
    requested: str | None,
    *,
    expected_sha: str | None = None,
    allow_unreleased: bool = False,
    client: ReleaseClient | None = None,
) -> Revision:
    """Resolve and verify an immutable canonical GitHub Release."""
    if allow_unreleased:
        revision = resolve_unreleased_revision(source, requested)
        if expected_sha is not None and (
            FULL_SHA.fullmatch(expected_sha) is None
            or revision.sha != expected_sha.lower()
        ):
            raise CliError(
                "Expected commit SHA does not match the unreleased revision."
            )
        return revision
    canonical_sources = {
        CANONICAL_SOURCE,
        CANONICAL_SOURCE.removesuffix(".git"),
    }
    if source.rstrip("/") not in canonical_sources:
        raise CliError(
            f"Production source must be {CANONICAL_SOURCE}; use "
            "--allow-unreleased only for local development."
        )
    if expected_sha is not None and FULL_SHA.fullmatch(expected_sha) is None:
        raise CliError("--expected-sha must be a full 40-character commit SHA.")

    github = client or GhReleaseClient()
    repository = github.repository()
    if (
        repository.get("id") != CANONICAL_REPOSITORY_ID
        or repository.get("full_name") != CANONICAL_REPOSITORY
    ):
        raise CliError("Canonical GitHub repository identity mismatch.")
    release = github.release(requested)
    tag, release_id = release_identity(release)

    before = github.resolve_tag(tag)
    github.verify_release(tag)
    after = github.resolve_tag(tag)
    if before != after:
        raise CliError("Release tag moved during verification.")
    if expected_sha is not None and after.commit_sha != expected_sha.lower():
        raise CliError(
            "Expected commit SHA does not match the verified release."
        )
    github.verify_commit(after.commit_sha)
    return Revision(
        tag,
        after.commit_sha,
        CANONICAL_SOURCE,
        CANONICAL_REPOSITORY,
        CANONICAL_REPOSITORY_ID,
        release_id,
        after.object_sha,
        True,
        True,
        True,
    )


def parse_data(values: list[str]) -> dict[str, str]:
    """Parse repeatable Copier KEY=VALUE arguments."""
    result: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key:
            raise CliError(f"Invalid --data value {value!r}; use KEY=VALUE.")
        result[key] = item
    return result


def slugify(value: str) -> str:
    """Create a safe default slug from a directory name."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")
    return slug or "csarc-project"


def detect_languages(target: Path) -> list[str]:
    """Return enabled language modules in their canonical order."""
    manifests = (
        ("python", "pyproject.toml"),
        ("typescript", "package.json"),
        ("rust", "Cargo.toml"),
    )
    return [
        name for name, manifest in manifests if (target / manifest).is_file()
    ]


def detect_language(target: Path) -> str:
    """Return the legacy profile label for compatibility."""
    return "-".join(detect_languages(target)) or "ci"


def selected_languages(answers: dict[str, object]) -> set[str]:
    """Read new module answers with a legacy profile fallback."""
    selected = answers.get("languages")
    if isinstance(selected, list):
        return {str(item) for item in selected}
    legacy = answers.get("language")
    if isinstance(legacy, str) and legacy != "ci":
        return set(legacy.split("-"))
    return set()


def is_text(content: bytes) -> bool:
    """Return whether file content can be reviewed as UTF-8 text."""
    if b"\0" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def project_files(root: Path) -> dict[str, Path]:
    """Index regular project files while ignoring transient directories."""
    ignored = {
        ".git",
        ".cache",
        ".eggs",
        ".mypy_cache",
        ".pnpm-store",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
    }
    ignored_files = {".coverage", "coverage.xml"}
    files: dict[str, Path] = {}
    if not root.exists():
        return files
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(
            part in ignored or part.startswith(".venv")
            for part in relative.parts
        ):
            continue
        if (
            path.name in ignored_files
            or path.name.startswith(".coverage.")
            or path.suffix in {".pyc", ".pyo", ".tsbuildinfo"}
        ):
            continue
        if path.is_file() or path.is_symlink():
            files[relative.as_posix()] = path
    return files


def copier_copy(
    source: str,
    revision: Revision,
    stage: Path,
    data: Mapping[str, object],
    *,
    skip_tasks: bool = False,
) -> None:
    """Render one immutable template revision into a staging directory."""
    command = [
        sys.executable,
        "-m",
        "copier",
        "copy",
        "--trust",
        "--defaults",
        "--overwrite",
        "--vcs-ref",
        revision.sha,
    ]
    if skip_tasks:
        command.append("--skip-tasks")
    data_file = stage.parent / f".{stage.name}-copier-data.yml"
    data_file.write_text(
        yaml.safe_dump(dict(data), sort_keys=True), encoding="utf-8"
    )
    command.extend(["--data-file", str(data_file)])
    command.extend([source, str(stage)])
    try:
        result = run(command, capture=True, check=False)
    finally:
        data_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise CliError(
            result.stderr.strip() or result.stdout.strip() or "Copier failed."
        )
    pin_answer_commit(stage, revision.sha)
    persist_release_answers(stage, data)


def pin_answer_commit(target: Path, commit: str) -> None:
    """Replace Copier's abbreviated revision with the reviewed full SHA."""
    answers = config_path(target)
    if not answers.is_file():
        raise CliError(f"Template did not create {CONFIG_FILE}.")
    lines = answers.read_text(encoding="utf-8").splitlines()
    matches = sum(line.startswith("_commit:") for line in lines)
    if matches != 1:
        raise CliError("Copier answers must contain exactly one _commit value.")
    pinned = [
        f"_commit: {commit}" if line.startswith("_commit:") else line
        for line in lines
    ]
    answers.write_text("\n".join(pinned) + "\n", encoding="utf-8")


def config_path(target: Path) -> Path:
    """Return the current config, falling back to pre-migration answers."""
    current = target / CONFIG_FILE
    if current.is_file():
        return current
    return target / LEGACY_ANSWERS_FILE


def read_copier_answers(path: Path) -> dict[str, object]:
    """Read every non-secret answer persisted by Copier."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CliError(f"Cannot read Copier answers from {path}.") from error
    if not isinstance(payload, dict):
        raise CliError(f"Copier answers in {path} must be a mapping.")
    return {
        str(key): value
        for key, value in payload.items()
        if isinstance(key, str) and not key.startswith("_")
    }


def persist_release_answers(
    target: Path, answers: Mapping[str, object]
) -> None:
    """Persist the CLI-resolved release contract in Copier's answer file."""
    path = config_path(target)
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CliError(f"Cannot read Copier answers from {path}.") from error
    if not isinstance(payload, dict):
        raise CliError(f"Copier answers in {path} must be a mapping.")
    contract = release_contract(answers)
    payload.update(
        release_immutable_releases=contract["immutable_releases"],
        release_ownership=contract["ownership"],
        release_ownership_reason=contract["reason"],
        release_required_inputs=contract["required_inputs"],
        release_settings_owner=contract["settings_owner"],
        release_workflow=contract["selected_workflow"] or "",
    )
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def project_verification_configuration(
    target: Path, answers: Mapping[str, object] | None = None
) -> dict[str, object]:
    """Describe the explicit project hook or the legacy fallback."""
    if answers is None:
        answers_path = config_path(target)
        answers = (
            read_copier_answers(answers_path) if answers_path.is_file() else {}
        )
    configured = answers.get("project_verification_hook", "")
    if configured is not None and configured != "":
        return {
            "configured": True,
            "path": configured,
            "source": "explicit",
        }
    fallback = target / "scripts" / "verify-product"
    if fallback.is_file() and os.access(fallback, os.X_OK):
        return {
            "configured": True,
            "path": "scripts/verify-product",
            "source": "fallback",
        }
    return {"configured": False, "path": None, "source": "none"}


def project_verification_evidence(
    configuration: Mapping[str, object], result: str, reason: str
) -> dict[str, object]:
    """Return stable, precise evidence for one configured project hook."""
    if result not in {"passed", "failed", "not-run"}:
        raise ValueError(f"Unsupported project verification result: {result}")
    return {**configuration, "reason": reason, "result": result}


def validated_project_verification_hook(
    target: Path, configuration: Mapping[str, object]
) -> Path | None:
    """Resolve one executable hook without allowing repository escape."""
    raw_path = configuration.get("path")
    if raw_path is None:
        return None
    if not isinstance(raw_path, str):
        raise CliError("Project verification hook must be a path string.")
    relative = Path(raw_path)
    if (
        not raw_path
        or raw_path != raw_path.strip()
        or relative.is_absolute()
        or ".." in relative.parts
        or re.fullmatch(r"[A-Za-z0-9._/-]+", raw_path) is None
    ):
        raise CliError(
            "Project verification hook must be a safe repository-relative "
            "executable path without shell syntax or parent traversal."
        )
    try:
        root = target.resolve(strict=True)
        hook = (target / relative).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise CliError(
            f"Project verification hook does not exist: {raw_path}"
        ) from error
    if hook != root and root not in hook.parents:
        raise CliError(
            f"Project verification hook escapes the repository: {raw_path}"
        )
    if not hook.is_file():
        raise CliError(
            f"Project verification hook is not a regular file: {raw_path}"
        )
    if not os.access(hook, os.X_OK):
        raise CliError(
            f"Project verification hook is not executable: {raw_path}"
        )
    canonical = target / "scripts" / "verify"
    try:
        if canonical.exists() and os.path.samefile(hook, canonical):
            raise CliError(
                "Project verification hook must not resolve to the canonical "
                f"scripts/verify command: {raw_path}"
            )
    except OSError as error:
        raise CliError(
            f"Cannot compare project verification hook identity: {raw_path}"
        ) from error
    return hook


def file_fingerprint(path: Path) -> str:
    """Hash managed content and the file traits Copier can reproduce."""
    digest = hashlib.sha256()
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as error:
        raise CliError(f"Managed adoption file is missing: {path}") from error
    if stat.S_ISLNK(mode):
        digest.update(b"symlink\0")
        digest.update(os.readlink(path).encode())
    elif stat.S_ISREG(mode):
        digest.update(b"file\0")
        digest.update(b"executable" if mode & 0o111 else b"regular")
        digest.update(b"\0")
        digest.update(path.read_bytes())
    else:
        raise CliError(f"Managed adoption file is missing: {path}")
    return digest.hexdigest()


def pending_adoption_data(
    target: Path,
    revision: Revision,
    repository: RepositoryContext,
    answers_path: Path,
    managed_files: tuple[str, ...],
    manual_files: tuple[str, ...],
) -> dict[str, object]:
    """Build the checkpoint needed to resume one exact adoption."""
    return {
        "answers_sha256": hashlib.sha256(answers_path.read_bytes()).hexdigest(),
        "managed_files": [
            {"fingerprint": file_fingerprint(target / name), "path": name}
            for name in managed_files
            if name
            not in {CONFIG_FILE.as_posix(), LEGACY_ANSWERS_FILE.as_posix()}
        ],
        "manual_files": list(manual_files),
        "repository": repository.as_dict(),
        "schema_version": 1,
        "template": {
            "release": revision.label,
            "sha": revision.sha,
            "source": revision.source,
            "verification": (
                "verified" if revision.verified else "development-unreleased"
            ),
        },
    }


def write_pending_adoption(target: Path, payload: dict[str, object]) -> None:
    """Atomically persist an incomplete adoption checkpoint."""
    destination = target / PENDING_ADOPTION_FILE
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def read_pending_adoption(target: Path) -> dict[str, object]:
    """Read and minimally validate an adoption checkpoint."""
    path = checked_destination(target, PENDING_ADOPTION_FILE.as_posix())
    if path.is_symlink() or not path.is_file():
        raise CliError(
            "No pending adoption exists; run csarc adopt first or use "
            "csarc update for a completed adoption."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CliError(
            "Pending adoption state is unreadable; restore it from the "
            "original adoption or restart from a clean commit."
        ) from error
    template = payload.get("template") if isinstance(payload, dict) else None
    repository = (
        payload.get("repository") if isinstance(payload, dict) else None
    )
    managed = (
        payload.get("managed_files") if isinstance(payload, dict) else None
    )
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("answers_sha256"), str)
        or not isinstance(template, dict)
        or not isinstance(repository, dict)
        or not isinstance(managed, list)
        or not all(
            isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and isinstance(item.get("fingerprint"), str)
            for item in managed
        )
    ):
        raise CliError(
            "Pending adoption state has an unsupported shape; restore it "
            "from the original adoption or restart from a clean commit."
        )
    return payload


def provenance_data(
    revision: Revision,
    previous: dict[str, object] | None = None,
    *,
    applied_at: str | None = None,
    answers: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the auditable state recorded after a successful operation."""
    result: dict[str, object] = {
        "applied_at": applied_at
        or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "commit_sha": revision.sha,
        "guide_url": revision.guide_url,
        "release_attestation_verified": revision.attestation_verified,
        "release_id": revision.release_id,
        "release_immutable": revision.immutable,
        "release_tag": revision.label,
        "repository": revision.repository or revision.source,
        "repository_id": revision.repository_id,
        "schema_version": 1,
        "signature_verified": revision.signature_verified,
        "verification": "verified"
        if revision.verified
        else "development-unreleased",
    }
    if previous is not None:
        result["previous"] = previous
    if answers is not None:
        result["release"] = release_contract(answers)
    return result


def write_provenance(
    target: Path,
    revision: Revision,
    previous: dict[str, object] | None = None,
    *,
    applied_at: str | None = None,
    answers: Mapping[str, object] | None = None,
) -> None:
    """Atomically persist verified release provenance."""
    destination = target / PROVENANCE_FILE
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            provenance_data(
                revision,
                previous,
                applied_at=applied_at,
                answers=answers,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def read_provenance(target: Path) -> dict[str, object] | None:
    """Read saved provenance without trusting its fields yet."""
    path = target / PROVENANCE_FILE
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CliError("Saved provenance is invalid JSON.") from error
    if not isinstance(payload, dict):
        raise CliError("Saved provenance must be a JSON object.")
    return payload


def managed_agents_block(content: str) -> str:
    """Extract one complete CSARC-managed AGENTS block."""
    if (
        content.count(AGENTS_BLOCK_START) != 1
        or content.count(AGENTS_BLOCK_END) != 1
    ):
        raise CliError("Generated AGENTS.md must contain one managed block.")
    start = content.index(AGENTS_BLOCK_START)
    end = content.index(AGENTS_BLOCK_END, start) + len(AGENTS_BLOCK_END)
    return content[start:end]


def merge_agents_file(existing: str, generated: str) -> str:
    """Replace or append only the CSARC-managed AGENTS block."""
    block = managed_agents_block(generated)
    newline = "\r\n" if "\r\n" in existing else "\n"
    block = block.replace("\r\n", "\n").replace("\n", newline)
    starts = existing.count(AGENTS_BLOCK_START)
    ends = existing.count(AGENTS_BLOCK_END)
    if starts == 0 and ends == 0:
        return existing.rstrip("\r\n") + newline * 2 + block + newline
    if starts != 1 or ends != 1:
        raise CliError("Existing AGENTS.md has invalid CSARC block markers.")
    start = existing.index(AGENTS_BLOCK_START)
    end = existing.index(AGENTS_BLOCK_END, start) + len(AGENTS_BLOCK_END)
    return existing[:start] + block + existing[end:]


def merge_gitignore(existing: str, generated: str) -> str:
    """Append missing template entries while preserving project order."""
    newline = "\r\n" if "\r\n" in existing else "\n"
    lines = existing.splitlines()
    known = set(lines)
    additions = [line for line in generated.splitlines() if line not in known]
    if not additions:
        return (
            existing if existing.endswith(("\n", "\r")) else existing + newline
        )
    separator = [] if not lines or not lines[-1] else [""]
    return newline.join([*lines, *separator, *additions]) + newline


def is_regular_file(path: Path) -> bool:
    """Return whether a path is a regular file without following links."""
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except (FileNotFoundError, NotADirectoryError):  # fmt: skip
        return False


def apply_adoption_policies(stage: Path, target: Path) -> tuple[str, ...]:
    """Apply the small fixed set of safe existing-repository merges."""
    merged: list[str] = []
    agents = target / "AGENTS.md"
    staged_agents = stage / "AGENTS.md"
    if is_regular_file(agents) and is_regular_file(staged_agents):
        staged_agents.write_text(
            merge_agents_file(
                agents.read_text(encoding="utf-8"),
                staged_agents.read_text(encoding="utf-8"),
            ),
            encoding="utf-8",
        )
        merged.append("AGENTS.md")
    gitignore = target / ".gitignore"
    staged_gitignore = stage / ".gitignore"
    if is_regular_file(gitignore) and is_regular_file(staged_gitignore):
        staged_gitignore.write_text(
            merge_gitignore(
                gitignore.read_text(encoding="utf-8"),
                staged_gitignore.read_text(encoding="utf-8"),
            ),
            encoding="utf-8",
        )
        merged.append(".gitignore")
    return tuple(sorted(merged))


def comparison_destination(target: Path, relative_name: str) -> Path | None:
    """Return a safe destination; reject symlink ancestors."""
    try:
        return checked_destination(target, relative_name)
    except CliError:
        current = target
        for part in Path(relative_name).parts[:-1]:
            current /= part
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(mode):
                raise
            if not stat.S_ISDIR(mode):
                return None
        return None


def compare_stage(
    stage: Path,
    target: Path,
    *,
    adopt: bool,
    merged_paths: tuple[str, ...] = (),
) -> Plan:
    """Compare staged output with the destination without changing it."""
    staged = project_files(stage)
    existing = project_files(target)
    add: list[str] = []
    preserve: list[str] = []
    merge: list[str] = []
    manual: list[str] = []
    unknown: list[str] = []
    for relative_name, staged_path in staged.items():
        existing_path = comparison_destination(target, relative_name)
        if existing_path is None:
            unknown.append(relative_name)
            continue
        try:
            existing_mode = existing_path.lstat().st_mode
        except FileNotFoundError:
            add.append(relative_name)
            continue
        if not (stat.S_ISREG(existing_mode) or stat.S_ISLNK(existing_mode)):
            unknown.append(relative_name)
            continue
        if file_fingerprint(staged_path) == file_fingerprint(existing_path):
            preserve.append(relative_name)
        elif relative_name in merged_paths:
            merge.append(relative_name)
        elif adopt:
            regular_files = stat.S_ISREG(
                staged_path.lstat().st_mode
            ) and stat.S_ISREG(existing_mode)
            destination = unknown
            if regular_files:
                staged_content = staged_path.read_bytes()
                existing_content = existing_path.read_bytes()
                if is_text(staged_content) and is_text(existing_content):
                    destination = manual
            destination.append(relative_name)
        else:
            manual.append(relative_name)
    preserve.extend(name for name in existing if name not in staged)
    return Plan(
        tuple(sorted(add)),
        (),
        tuple(sorted(set(preserve))),
        tuple(sorted(merge)),
        tuple(sorted(manual)),
        tuple(sorted(unknown)),
    )


def plan_status(
    plan: Plan, adoption: Mapping[str, object] | None = None
) -> tuple[str, str]:
    """Return the strongest adoption decision and its limitation."""
    if adoption is not None and adoption.get("applied") is True:
        return (
            "Adopted",
            "Formal adoption completed; this report now records the "
            "post-adoption state.",
        )
    if adoption is not None and adoption.get("applicable") is not True:
        return (
            "Not ready to adopt",
            "The machine plan is not applicable; candidate verification is "
            f"{adoption.get('verification', 'unknown')}.",
        )
    if plan.unknown:
        return (
            "Unable to determine",
            "Directory, ancestor, special-file, or non-text path collisions "
            "need human inspection.",
        )
    if plan.manual:
        return (
            "Review required",
            "Different text content needs a manual merge decision.",
        )
    return (
        "Ready to adopt",
        "No known file conflicts; semantic and runtime conflicts remain "
        "possible.",
    )


def printable(value: object) -> str:
    """Escape control characters without exposing file content."""
    return str(value).replace("\n", r"\n").replace("\r", r"\r")


def markdown_code(value: object) -> str:
    """Return a safe inline Markdown code value."""
    return printable(value).replace("`", r"\`")


def report_settings(data: dict[str, object]) -> str:
    """Return known non-secret settings used for rendering."""
    allowed = {
        "branch_strategy",
        "code_owner",
        "coverage_mode",
        "coverage_threshold",
        "enable_codeql",
        "enable_docker",
        "enable_governance_drift_check",
        "enable_precommit",
        "enable_template_update_notifications",
        "language",
        "languages",
        "package_name",
        "project_description",
        "project_mode",
        "project_name",
        "project_slug",
        "project_verification_hook",
        "project_visibility",
        "python_min_version",
        "python_support_mode",
        "reviewers",
    }
    return ", ".join(
        f"`{key}={markdown_code(value)}`"
        for key, value in sorted(data.items())
        if key in allowed
    )


def adoption_report_markdown(
    target: Path,
    revision: Revision,
    repository: RepositoryContext,
    data: dict[str, object],
    plan: Plan,
    generated_at: str,
    adoption: dict[str, object] | None = None,
) -> str:
    """Render the complete, shareable adoption decision report."""
    status, reason = plan_status(plan, adoption)
    release = release_contract(data)
    workflow = release["selected_workflow"] or "(none)"
    inputs = ", ".join(cast(list[str], release["required_inputs"])) or "(none)"
    counts = (
        ("Add", len(plan.add)),
        ("Overwrite", len(plan.overwrite)),
        ("Preserve", len(plan.preserve)),
        ("Automatic merge", len(plan.merge)),
        ("Manual merge", len(plan.manual)),
        ("Unable to determine", len(plan.unknown)),
    )
    lines = [
        "# CSARC adoption dry-run",
        "",
        f"> **Decision: {status}.** {reason}",
        "",
        "## Snapshot",
        "",
        f"- Target: `{markdown_code(target)}`",
        f"- Repository: `{markdown_code(repository.repository or '(none)')}`",
        "- Repository visibility: `"
        f"{markdown_code(repository.visibility)}` "
        f"(`{markdown_code(repository.source)}`)",
        f"- Template source: `{markdown_code(revision.source)}`",
        f"- Template: `{markdown_code(revision.label)}` / `{revision.sha}`",
        "- Release verification: "
        + ("verified immutable release" if revision.verified else "UNVERIFIED"),
        f"- Release ownership: `{release['ownership']}`",
        f"- Selected release workflow: `{workflow}`",
        f"- Required release inputs: `{inputs}`",
        f"- Release ownership reason: {release['reason']}",
        "- Release repository settings: "
        f"`{release['settings_owner']}` / immutable Releases "
        f"`{release['immutable_releases']}`",
        f"- Settings: {report_settings(data)}",
        f"- Generated: `{generated_at}`",
        "",
        "## Expected file effects",
        "",
        "| Effect | Files |",
        "| --- | ---: |",
        *(f"| {label} | {count} |" for label, count in counts),
        "",
        "## Files needing attention",
        "",
    ]
    if adoption is not None:
        owner = adoption.get("code_owner")
        owner_state = (
            owner.get("state", "unknown")
            if isinstance(owner, dict)
            else "unknown"
        )
        raw_hook = adoption.get("project_verification_hook")
        hook = raw_hook if isinstance(raw_hook, dict) else {}
        hook_path = hook.get("path") or "(none)"
        working_tree = (
            "clean"
            if adoption.get("clean")
            else (
                "dirty; exact preserved state"
                if adoption.get("applicable") is True
                else "dirty; review only"
            )
        )
        applied = adoption.get("applied") is True
        lines[12:12] = [
            f"- Target HEAD: `{markdown_code(adoption.get('target_head'))}`",
            f"- Working tree: {working_tree}",
            f"- CODEOWNER verification: `{markdown_code(owner_state)}`",
            f"- Project verification hook: `{markdown_code(hook_path)}`",
            "- Project verification hook configured: `"
            f"{str(hook.get('configured') is True).lower()}`",
            "- Project verification result: `"
            f"{markdown_code(hook.get('result'))}`",
            "- Project verification reason: `"
            f"{markdown_code(hook.get('reason'))}`",
            "- Candidate verification: `"
            f"{markdown_code(adoption.get('verification'))}`",
            f"- Adoption applied: `{str(applied).lower()}`",
            *(
                [f"- Adopted at: `{markdown_code(adoption.get('applied_at'))}`"]
                if applied
                else []
            ),
        ]
        changes = adoption.get("target_changes")
        if isinstance(changes, list) and changes:
            lines[14:14] = [
                "- Working-tree entries: "
                + ", ".join(f"`{markdown_code(value)}`" for value in changes)
            ]
    attention = (
        (path, "template and repository contain different UTF-8 text")
        for path in plan.manual
    )
    unknown = (
        (
            path,
            "file type, executable bit, link target, or non-text content "
            "differs; a directory, ancestor, or special-file collision is "
            "also possible",
        )
        for path in plan.unknown
    )
    items = (*attention, *unknown)
    if items:
        lines.extend(
            f"- `{markdown_code(path)}` - {item_reason}."
            for path, item_reason in items
        )
    else:
        lines.append(
            "- No known file conflicts. This does not guarantee semantic or "
            "runtime compatibility."
        )
    if plan.merge:
        lines.extend(
            (
                "",
                "## Automatic merges",
                "",
                *(
                    f"- `{markdown_code(path)}` - fixed CSARC adoption policy."
                    for path in plan.merge
                ),
            )
        )
    if adoption is not None and adoption.get("applied") is True:
        lines.extend(
            (
                "",
                "## Adoption applied",
                "",
                "Formal adoption completed at `"
                f"{markdown_code(adoption.get('applied_at'))}`. This report "
                "was updated in place to record the post-adoption state; no "
                "plan remains to apply.",
                "",
            )
        )
    elif adoption is not None and adoption.get("applicable") is not True:
        lines.extend(
            (
                "",
                "## Next step",
                "",
                "Do not apply this plan. Resolve the reported gate and create "
                "a new dry-run plan.",
                "",
            )
        )
    else:
        lines.extend(
            (
                "",
                "## If you approve",
                "",
                "Apply only this machine plan with `csarc adopt --apply-plan`. "
                "The CLI rebuilds and verifies the candidate before changing "
                "the target. It does not apply settings, push, or open a pull "
                "request.",
                "",
                "Review this report and the terminal plan before applying it.",
                "",
            )
        )
    return "\n".join(lines)


def pdf_text(
    value: object, limit: int = 92, max_width: float | None = None
) -> str:
    """Return printable ASCII text supported by the bundled PDF font."""
    escaped = printable(value).encode("ascii", "backslashreplace").decode()
    text = escaped if len(escaped) <= limit else escaped[: limit - 3] + "..."
    while (
        max_width is not None
        and len(text) > 3
        and stringWidth(text, "Helvetica", 8) > max_width
    ):
        text = text[:-4] + "..."
    return text


def draw_adoption_pdf(
    output: BinaryIO,
    target: Path,
    revision: Revision,
    repository: RepositoryContext,
    data: dict[str, object],
    plan: Plan,
    generated_at: str,
    adoption: Mapping[str, object] | None = None,
) -> None:
    """Draw a concise, selectable-text adoption decision PDF."""
    page_width, page_height = A4
    document = Canvas(output, pagesize=A4, pageCompression=1)
    status, reason = plan_status(plan, adoption)
    status_color = {
        "Adopted": colors.HexColor("#DDEFE2"),
        "Ready to adopt": colors.HexColor("#DDEFE2"),
        "Review required": colors.HexColor("#F7E9B5"),
        "Unable to determine": colors.HexColor("#F4D7D5"),
        "Not ready to adopt": colors.HexColor("#F4D7D5"),
    }[status]

    document.setTitle("CSARC adoption dry-run")
    document.setAuthor("CSARC Repo Template")
    document.setFillColor(colors.HexColor("#17324D"))
    document.setFont("Helvetica-Bold", 8)
    document.drawString(48, page_height - 44, "CSARC REPO TEMPLATE")
    document.setFont("Helvetica-Bold", 22)
    document.drawString(48, page_height - 72, "Adoption dry-run")
    document.setFillColor(colors.HexColor("#52606D"))
    document.setFont("Helvetica", 8)
    document.drawRightString(
        page_width - 48, page_height - 44, pdf_text(generated_at)
    )

    document.setFillColor(status_color)
    document.roundRect(
        48, page_height - 150, page_width - 96, 54, 7, fill=1, stroke=0
    )
    document.setFillColor(colors.HexColor("#17212B"))
    document.setFont("Helvetica-Bold", 14)
    document.drawString(62, page_height - 118, status)
    document.setFont("Helvetica", 8)
    document.drawString(62, page_height - 135, pdf_text(reason))

    raw_hook = (
        adoption.get("project_verification_hook")
        if adoption is not None
        else None
    )
    hook = raw_hook if isinstance(raw_hook, dict) else {}
    hook_path = hook.get("path") or "(none)"
    hook_result = hook.get("result") or "not-run"
    release = release_contract(data)
    release_inputs = cast(list[str], release["required_inputs"])
    metadata = (
        ("Target", target),
        ("Repository", repository.repository or "(none)"),
        (
            "Visibility",
            f"{repository.visibility} ({repository.source})",
        ),
        ("Template source", revision.source),
        ("Template", f"{revision.label} / {revision.sha}"),
        (
            "Verification",
            "verified immutable release" if revision.verified else "UNVERIFIED",
        ),
        ("Release ownership", release["ownership"]),
        ("Release workflow", release["selected_workflow"] or "(none)"),
        ("Release inputs", ", ".join(release_inputs) or "(none)"),
        ("Release reason", release["reason"]),
        ("Release settings owner", release["settings_owner"]),
        ("Immutable Releases", release["immutable_releases"]),
        ("Languages", data.get("languages", "unknown")),
        ("Project hook", hook_path),
        ("Hook configured", str(hook.get("configured") is True).lower()),
        ("Hook result", hook_result),
        ("Hook reason", hook.get("reason") or "(none)"),
    )
    value_x = 56 + max(
        stringWidth(label, "Helvetica-Bold", 8) for label, _ in metadata
    )
    value_width = page_width - 48 - value_x
    y = page_height - 178
    for label, value in metadata:
        document.setFont("Helvetica-Bold", 8)
        document.drawString(48, y, label)
        document.setFont("Helvetica", 8)
        document.drawString(value_x, y, pdf_text(value, 105, value_width))
        y -= 15

    counts = (
        ("Add", len(plan.add), "#2F6B8A"),
        ("Overwrite", len(plan.overwrite), "#477E94"),
        ("Preserve", len(plan.preserve), "#7298A8"),
        ("Automatic merge", len(plan.merge), "#4D7C5B"),
        ("Manual merge", len(plan.manual), "#A7833B"),
        ("Unknown", len(plan.unknown), "#9A5550"),
    )
    document.setFillColor(colors.HexColor("#17212B"))
    document.setFont("Helvetica-Bold", 11)
    document.drawString(48, y - 10, "Expected file effects")
    maximum = max((count for _, count, _ in counts), default=1) or 1
    y -= 34
    for label, count, color in counts:
        document.setFillColor(colors.HexColor("#52606D"))
        document.setFont("Helvetica", 8)
        document.drawString(48, y, label)
        document.setFillColor(colors.HexColor("#E8EDF1"))
        document.roundRect(128, y - 2, 330, 8, 4, fill=1, stroke=0)
        document.setFillColor(colors.HexColor(color))
        width = 0 if count == 0 else max(4, 330 * count / maximum)
        if width:
            document.roundRect(128, y - 2, width, 8, 4, fill=1, stroke=0)
        document.setFillColor(colors.HexColor("#17212B"))
        document.setFont("Helvetica-Bold", 8)
        document.drawRightString(page_width - 48, y, str(count))
        y -= 20

    document.setFont("Helvetica-Bold", 11)
    document.drawString(48, y - 4, "Files needing attention")
    y -= 25
    attention = [
        (path, "different text - manual merge") for path in plan.manual
    ] + [
        (path, "different file traits or non-text content - inspect")
        for path in plan.unknown
    ]
    if not attention:
        document.setFont("Helvetica", 8)
        document.drawString(
            48,
            y,
            "No known file conflicts. Semantic and runtime conflicts remain "
            "possible.",
        )
    else:
        document.setFont("Helvetica", 8)
        for path, item_reason in attention[:7]:
            document.drawString(48, y, f"- {pdf_text(path, 68)}")
            document.setFillColor(colors.HexColor("#52606D"))
            document.drawRightString(page_width - 48, y, item_reason)
            document.setFillColor(colors.HexColor("#17212B"))
            y -= 15
        if len(attention) > 7:
            document.drawString(
                48,
                y,
                f"- {len(attention) - 7} more item(s); see the Markdown "
                "report.",
            )

    document.setFillColor(colors.HexColor("#F1F4F6"))
    document.roundRect(48, 84, page_width - 96, 68, 7, fill=1, stroke=0)
    document.setFillColor(colors.HexColor("#17212B"))
    document.setFont("Helvetica-Bold", 10)
    applied = adoption is not None and adoption.get("applied") is True
    applicable = adoption is None or adoption.get("applicable") is True
    heading = (
        "Applied" if applied else ("If approved" if applicable else "Next step")
    )
    document.drawString(62, 132, heading)
    document.setFont("Helvetica", 8)
    if applied:
        document.drawString(
            62,
            116,
            "Formal adoption completed at "
            f"{pdf_text(adoption.get('applied_at') if adoption else None)}.",
        )
        document.drawString(
            62, 101, "This report now reflects the post-adoption state."
        )
    elif applicable:
        document.drawString(
            62,
            116,
            "Adoption adds planned files, runs ./scripts/verify, and previews "
            "settings.",
        )
        document.drawString(
            62, 101, "It does not apply settings, push, or open a pull request."
        )
    else:
        document.drawString(
            62, 116, "Do not apply this plan. Resolve the reported gate and"
        )
        document.drawString(62, 101, "create a new dry-run plan.")
    document.setStrokeColor(colors.HexColor("#D5DCE1"))
    document.line(48, 65, page_width - 48, 65)
    document.setFillColor(colors.HexColor("#52606D"))
    document.setFont("Helvetica", 7)
    document.drawString(48, 50, "Generated by csarc adopt --dry-run")
    document.drawRightString(page_width - 48, 50, "Page 1 of 1")
    document.showPage()
    document.save()


def adoption_report_directory(target: Path, requested: Path | None) -> Path:
    """Resolve a report directory that cannot dirty the target repository."""
    directory = (
        requested.expanduser().resolve()
        if requested is not None
        else target.parent / f"{target.name}-csarc-adoption-report"
    )
    if directory == target or target in directory.parents:
        raise CliError(
            "Adoption reports must be written outside the target repo."
        )
    return directory


def adoption_plan_payload(plan: ResolvedPlan) -> dict[str, object]:
    """Return a tamper-evident plan ready for persistence."""
    payload = plan.as_dict()
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode()
    payload["plan_sha256"] = hashlib.sha256(encoded).hexdigest()
    return payload


def atomic_replace_text(destination: Path, content: str) -> None:
    """Replace text through a random regular file in the same directory."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_adoption_plan(path: Path) -> dict[str, object]:
    """Read a machine plan and reject accidental or malicious edits."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CliError(f"Cannot read adoption plan from {path}.") from error
    if not isinstance(payload, dict):
        raise CliError("Adoption plan must be a JSON object.")
    expected = payload.pop("plan_sha256", None)
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode()
    actual = hashlib.sha256(encoded).hexdigest()
    if not isinstance(expected, str) or expected != actual:
        raise CliError("Adoption plan digest does not match its contents.")
    payload["plan_sha256"] = expected
    return payload


def adoption_binding(payload: dict[str, object]) -> dict[str, object]:
    """Return only fields that must remain identical before apply."""
    adoption = payload.get("adoption")
    if not isinstance(adoption, dict):
        raise CliError("Adoption plan has no target state.")
    return {
        "answers": payload.get("answers"),
        "adoption": adoption,
        "files": payload.get("files"),
        "mode": payload.get("mode"),
        "release": payload.get("release"),
        "release_ownership": payload.get("release_ownership"),
        "repository": payload.get("repository"),
        "target": payload.get("target"),
        "template": payload.get("template"),
    }


def json_differences(
    saved: object, rebuilt: object, path: str = "$"
) -> tuple[str, ...]:
    """Describe differing JSON leaves without hiding the fail-closed reason."""
    if type(saved) is not type(rebuilt):
        return (f"{path}: saved={saved!r}, rebuilt={rebuilt!r}",)
    if isinstance(saved, dict) and isinstance(rebuilt, dict):
        differences: list[str] = []
        for key in sorted(set(saved) | set(rebuilt)):
            child = f"{path}.{key}"
            if key not in saved:
                differences.append(
                    f"{child}: saved=<missing>, rebuilt={rebuilt[key]!r}"
                )
            elif key not in rebuilt:
                differences.append(
                    f"{child}: saved={saved[key]!r}, rebuilt=<missing>"
                )
            else:
                differences.extend(
                    json_differences(saved[key], rebuilt[key], child)
                )
        return tuple(differences)
    if isinstance(saved, list) and isinstance(rebuilt, list):
        differences = []
        if len(saved) != len(rebuilt):
            differences.append(
                f"{path}.length: saved={len(saved)}, rebuilt={len(rebuilt)}"
            )
        for index, (saved_item, rebuilt_item) in enumerate(
            zip(saved, rebuilt, strict=False)
        ):
            differences.extend(
                json_differences(saved_item, rebuilt_item, f"{path}[{index}]")
            )
        return tuple(differences)
    if saved != rebuilt:
        return (f"{path}: saved={saved!r}, rebuilt={rebuilt!r}",)
    return ()


def target_state(target: Path) -> tuple[str, tuple[str, ...], str]:
    """Return HEAD, status entries, and a stable status digest."""
    head, changes = git_target_state(target)
    digest = hashlib.sha256("\0".join(changes).encode()).hexdigest()
    return head, changes, digest


def code_owner_verification(
    repository: RepositoryContext, code_owner: object
) -> dict[str, str]:
    """Verify a team CODEOWNER when the GitHub API can enumerate access."""
    value = str(code_owner)
    match = re.fullmatch(r"@([^/]+)/([^/]+)", value)
    if repository.repository is None or match is None:
        return {
            "reason": "Repository or team owner is unavailable.",
            "state": "unknown",
            "value": value,
        }
    organization, team = match.groups()
    if (
        repository.owner is None
        or organization.casefold() != repository.owner.casefold()
    ):
        return {
            "reason": "CODEOWNER organization does not match the repository.",
            "state": "blocked",
            "value": value,
        }
    try:
        result = run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{repository.repository}/teams",
                "--jq",
                ".[].slug",
            ],
            capture=True,
            check=False,
        )
    except FileNotFoundError:
        return {
            "reason": "GitHub CLI is unavailable.",
            "state": "unknown",
            "value": value,
        }
    if result.returncode != 0:
        return {
            "reason": result.stderr.strip() or "Team access is unreadable.",
            "state": "unknown",
            "value": value,
        }
    teams = {line.strip().casefold() for line in result.stdout.splitlines()}
    if team.casefold() not in teams:
        return {
            "reason": "Team is not attached to the target repository.",
            "state": "blocked",
            "value": value,
        }
    return {
        "reason": "Team has repository access.",
        "state": "verified",
        "value": value,
    }


def mark_adoption_applied(plan: ResolvedPlan, applied_at: str) -> ResolvedPlan:
    """Return a copy of one adoption plan tagged with its applied state.

    Formal adoption must update the same adoption report in place once it
    completes, recording both the pre-adoption (dry-run) and post-adoption
    state (#529). The report's detailed format is out of this scope (#530);
    this only tags the existing plan so the existing renderers can record
    that the plan was actually applied, and when.
    """
    if plan.adoption is None:
        raise CliError("Adoption report requires target state.")
    adoption = dict(plan.adoption)
    adoption["applied"] = True
    adoption["applied_at"] = applied_at
    return replace(plan, adoption=adoption)


def write_adoption_reports(
    plan: ResolvedPlan,
    requested_directory: Path | None,
    *,
    emit: bool = True,
) -> tuple[Path, Path, Path]:
    """Atomically replace the latest adoption reports outside the repo."""
    if plan.files is None or plan.adoption is None:
        raise CliError("Adoption report requires file and target state.")
    directory = adoption_report_directory(plan.target, requested_directory)
    markdown_path = directory / f"{ADOPTION_REPORT_BASENAME}.md"
    pdf_path = directory / f"{ADOPTION_REPORT_BASENAME}.pdf"
    plan_path = directory / ADOPTION_PLAN_BASENAME
    directory.mkdir(parents=True, exist_ok=True)
    generated_at = str(plan.adoption["generated_at"])
    atomic_replace_text(
        markdown_path,
        adoption_report_markdown(
            plan.target,
            plan.revision,
            plan.repository,
            plan.answers,
            plan.files,
            generated_at,
            plan.adoption,
        ),
    )
    atomic_replace_text(
        plan_path,
        json.dumps(adoption_plan_payload(plan), indent=2, sort_keys=True)
        + "\n",
    )
    pdf_path.unlink(missing_ok=True)
    pdf_temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=directory,
            prefix=f".{pdf_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as pdf:
            pdf_temporary = Path(pdf.name)
            draw_adoption_pdf(
                cast(BinaryIO, pdf),
                plan.target,
                plan.revision,
                plan.repository,
                plan.answers,
                plan.files,
                generated_at,
                plan.adoption,
            )
            pdf.flush()
        pdf_temporary.replace(pdf_path)
    except Exception as error:
        if pdf_temporary is not None:
            pdf_temporary.unlink(missing_ok=True)
        print(
            "WARNING: PDF report generation failed; Markdown and the machine "
            f"plan remain usable at {directory}: {error}",
            file=sys.stderr,
        )
    if emit:
        print(f"Markdown report: {markdown_path}")
        if pdf_path.is_file() and not pdf_path.is_symlink():
            print(f"PDF report: {pdf_path}")
        print(f"Machine plan: {plan_path}")
    return markdown_path, pdf_path, plan_path


def print_group(title: str, paths: tuple[str, ...]) -> None:
    """Print one stable plan group."""
    print(f"{title} ({len(paths)}):")
    if paths:
        for path in paths:
            print(f"  {path}")
    else:
        print("  (none)")


def print_capabilities(payload: dict[str, object]) -> None:
    """Print capability results from a resolved plan."""
    for name in ("organization_policy", "repository_setting"):
        value = payload.get(name)
        state = (
            value.get("state", "unknown")
            if isinstance(value, dict)
            else "unknown"
        )
        print(f"GitHub release planning {name}={state}")
    raw_states = payload.get("token_permissions", payload.get("capabilities"))
    states = raw_states if isinstance(raw_states, dict) else {}
    token_summary = ", ".join(
        f"token {name}={value.get('state', 'unknown')}"
        for name, value in states.items()
        if isinstance(value, dict)
    )
    print(f"GitHub release planning permissions: {token_summary or 'unknown'}")
    effective = payload.get("effective")
    mode = (
        effective.get("mode", payload.get("mode", "blocked"))
        if isinstance(effective, dict)
        else payload.get("mode", "blocked")
    )
    print(f"GitHub release planning effective={mode}")
    print("Planning only: this check neither enables nor publishes a release.")
    raw_integrations = payload.get("integrations")
    integrations = (
        raw_integrations if isinstance(raw_integrations, dict) else {}
    )
    for name, value in integrations.items():
        if not isinstance(value, dict):
            continue
        state = value.get("state", "fallback")
        next_step = value.get("next_step", "No automatic action.")
        print(f"Optional integration {name}: {state}")
        print(f"Next: {next_step}")


def print_plan(plan: ResolvedPlan) -> None:
    """Print the human-readable form of the shared plan model."""
    print(f"Mode: {plan.mode}")
    print(f"Target: {plan.target}")
    if plan.update is not None:
        print(
            f"Template: {plan.update['current_version']} / "
            f"{plan.update['current_sha']} -> "
            f"{plan.update['target_version']} / "
            f"{plan.update['target_sha']}"
        )
    else:
        print(f"Template version: {plan.revision.label}")
        print(f"Template commit: {plan.revision.sha}")
    print(f"Template source: {plan.revision.source}")
    print(f"Pinned guide: {plan.revision.guide_url}")
    print(
        "Release verification: "
        + (
            "verified immutable release"
            if plan.revision.verified
            else "UNVERIFIED"
        )
    )
    release = release_contract(plan.answers)
    release_inputs = cast(list[str], release["required_inputs"])
    print(f"Release ownership: {release['ownership']}")
    print(
        f"Selected release workflow: {release['selected_workflow'] or '(none)'}"
    )
    print(f"Required release inputs: {', '.join(release_inputs) or '(none)'}")
    print(f"Release ownership reason: {release['reason']}")
    print(f"Release settings owner: {release['settings_owner']}")
    print(f"Immutable Releases: {release['immutable_releases']}")
    print(f"Repository: {plan.repository.repository or '(none)'}")
    print(f"Repository owner: {plan.repository.owner or '(unknown)'}")
    print(f"Repository owner type: {plan.repository.owner_type or 'unknown'}")
    print(
        f"Repository visibility: {plan.repository.visibility} "
        f"({plan.repository.source})"
    )
    if plan.repository.reason is not None:
        print(f"Repository context: {plan.repository.reason}")
    print("Settings:")
    for key, value in sorted(plan.answers.items()):
        print(f"  {key}={value}")
    if plan.adoption is not None:
        owner = plan.adoption.get("code_owner")
        if isinstance(owner, dict):
            print(
                "CODEOWNER verification: "
                f"{owner.get('state', 'unknown')} - "
                f"{owner.get('reason', 'No details available.')}"
            )
        raw_hook = plan.adoption.get("project_verification_hook")
        if isinstance(raw_hook, dict):
            print(
                "Project verification hook: "
                f"{raw_hook.get('path') or '(none)'} "
                f"({raw_hook.get('source', 'none')})"
            )
            print(
                "Project verification result: "
                f"{raw_hook.get('result', 'not-run')}"
            )
            print(
                "Project verification reason: "
                f"{raw_hook.get('reason', 'No details available.')}"
            )
    print_capabilities(plan.capabilities)
    if plan.files is not None:
        print_group("Add", plan.files.add)
        print_group("Overwrite", plan.files.overwrite)
        print_group("Preserve", plan.files.preserve)
        print_group("Automatic merge", plan.files.merge)
        print_group("Manual merge", plan.files.manual)
        print_group("Unable to determine", plan.files.unknown)
        status, reason = plan_status(plan.files)
        print(f"Conflict risk: {status} - {reason}")
    elif plan.update is not None:
        print(
            "Conflict risk: Copier smart diff; conflicts fail closed and "
            "remain in place."
        )


def confirm(args: argparse.Namespace) -> bool:
    """Require explicit approval before writing files."""
    if args.yes:
        return True
    if args.non_interactive:
        raise CliError(
            "--non-interactive requires --yes before files may change."
        )
    return input("Apply this plan? [y/N] ").strip().lower() in {"y", "yes"}


def checked_destination(root: Path, relative_name: str) -> Path:
    """Reject paths whose existing ancestors could escape the destination."""
    relative = Path(relative_name)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise CliError(f"Unsafe adoption path: {relative_name}")
    try:
        root_mode = root.lstat().st_mode
    except FileNotFoundError as error:
        raise CliError(f"Adoption destination is missing: {root}") from error
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        raise CliError(f"Adoption destination is not a real directory: {root}")
    current = root
    for part in relative.parts[:-1]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise CliError(
                f"Adoption path has a symlink or non-directory ancestor: "
                f"{relative_name}"
            )
    return root / relative


def copy_additions(stage: Path, target: Path, paths: tuple[str, ...]) -> None:
    """Copy only files that the plan classified as additions."""
    target.mkdir(parents=True, exist_ok=True)
    for relative_name in paths:
        source = stage / relative_name
        destination = target / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination, follow_symlinks=False)


def copy_candidate_files(
    stage: Path, target: Path, paths: tuple[str, ...]
) -> None:
    """Copy planned additions and fixed merges into an isolated candidate."""
    copies = [
        (stage / relative_name, checked_destination(target, relative_name))
        for relative_name in paths
    ]
    for source, destination in copies:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            destination.unlink()
        if source.is_symlink():
            destination.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, destination)


def git_target_state(target: Path) -> tuple[str, tuple[str, ...]]:
    """Return the exact committed base and reviewable working-tree state."""
    head = run(
        ["git", "-C", str(target), "rev-parse", "HEAD"], capture=True
    ).stdout.strip()
    status = run(
        [
            "git",
            "-C",
            str(target),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        capture=True,
    ).stdout.splitlines()
    return head, tuple(status)


def target_file_snapshot(target: Path) -> dict[str, str]:
    """Fingerprint every relevant path in one allowed working-tree state."""
    return {
        name: file_fingerprint(path)
        for name, path in sorted(project_files(target).items())
    }


def git_changed_paths(target: Path) -> set[str]:
    """Return tracked and untracked paths without parsing display quoting."""
    tracked = run(
        [
            "git",
            "-C",
            str(target),
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            "HEAD",
            "--",
        ],
        capture=True,
    ).stdout.split("\0")
    untracked = run(
        [
            "git",
            "-C",
            str(target),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        capture=True,
    ).stdout.split("\0")
    return {name for name in (*tracked, *untracked) if name}


def validate_target_snapshot(
    target: Path, expected: Mapping[str, object]
) -> None:
    """Reject any target change after a plan was built or confirmed."""
    expected_head = expected.get("target_head")
    expected_changes = expected.get("target_changes")
    expected_files = expected.get("target_files")
    head, changes = git_target_state(target)
    if (
        not isinstance(expected_head, str)
        or not isinstance(expected_changes, list)
        or not all(isinstance(value, str) for value in expected_changes)
        or not isinstance(expected_files, dict)
        or not all(
            isinstance(name, str) and isinstance(value, str)
            for name, value in expected_files.items()
        )
        or head != expected_head
        or list(changes) != expected_changes
        or target_file_snapshot(target) != expected_files
    ):
        raise CliError(
            "Repository changed after the plan was created or confirmed; "
            "create a new plan."
        )


def pending_managed_paths(stage: Path, planned: Plan) -> tuple[str, ...]:
    """Return every rendered path protected by a pending checkpoint."""
    return tuple(
        sorted(
            (set(planned.add) | set(planned.merge))
            | (set(planned.preserve) & set(project_files(stage)))
        )
    )


def validate_pending_file_sets(
    target: Path,
    pending: Mapping[str, object],
    stage: Path,
    planned: Plan,
) -> None:
    """Derive pending paths from the template and reject unrelated changes."""
    expected_managed = set(pending_managed_paths(stage, planned)) - {
        CONFIG_FILE.as_posix(),
        LEGACY_ANSWERS_FILE.as_posix(),
    }
    raw_managed = pending.get("managed_files")
    managed = (
        {
            item.get("path")
            for item in raw_managed
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        if isinstance(raw_managed, list)
        else set()
    )
    expected_manual = set(planned.manual) | set(planned.unknown)
    raw_manual = pending.get("manual_files")
    manual = (
        {value for value in raw_manual if isinstance(value, str)}
        if isinstance(raw_manual, list)
        else set()
    )
    if managed != expected_managed or manual != expected_manual:
        raise CliError(
            "Pending file classifications do not match the verified template; "
            "restart adoption from a clean commit."
        )
    rendered = project_files(stage)
    for name in sorted(expected_managed):
        current = checked_destination(target, name)
        expected = rendered.get(name)
        if expected is None or file_fingerprint(current) != file_fingerprint(
            expected
        ):
            raise CliError(
                f"Managed adoption file differs from the verified template: "
                f"{name}. Restart adoption from a clean commit."
            )
    allowed = (
        managed
        | manual
        | {
            CONFIG_FILE.as_posix(),
            LEGACY_ANSWERS_FILE.as_posix(),
            PENDING_ADOPTION_FILE.as_posix(),
        }
    )
    unexpected = sorted(git_changed_paths(target) - allowed)
    if unexpected:
        raise CliError(
            "Pending adoption contains unexpected working-tree changes: "
            + ", ".join(unexpected)
        )


def candidate_effects(
    candidate: Path,
    target: Path,
    planned: Plan,
) -> tuple[Plan, dict[str, str]]:
    """Describe candidate changes, excluding ignored verification output."""
    candidate_files = project_files(candidate)
    target_files = project_files(target)
    changed_paths = git_changed_paths(candidate)
    additions: list[str] = []
    overwrites: list[str] = []
    merges: list[str] = []
    artifacts: dict[str, str] = {}
    for name in sorted(changed_paths):
        path = candidate_files.get(name)
        if path is None:
            continue
        existing = target_files.get(name)
        if existing is not None and file_fingerprint(path) == file_fingerprint(
            existing
        ):
            continue
        artifacts[name] = file_fingerprint(path)
        if existing is None:
            additions.append(name)
        elif name in planned.merge:
            merges.append(name)
        else:
            overwrites.append(name)
    return (
        Plan(
            tuple(sorted(additions)),
            tuple(sorted(overwrites)),
            planned.preserve,
            tuple(sorted(merges)),
            planned.manual,
            planned.unknown,
        ),
        dict(sorted(artifacts.items())),
    )


def candidate_patch_effects(
    candidate: Path, *, include_paths: tuple[str, ...] = ()
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Return exact staged artifacts and deletions for transactional apply."""
    candidate_files = project_files(candidate)
    missing = sorted(set(include_paths) - set(candidate_files))
    if missing:
        raise CliError(
            "Candidate includes missing explicit paths: " + ", ".join(missing)
        )
    changed = git_changed_paths(candidate) | set(include_paths)
    artifacts = {
        name: file_fingerprint(candidate_files[name])
        for name in sorted(changed)
        if name in candidate_files
    }
    deletions = tuple(
        sorted(
            name
            for name in changed
            if name not in candidate_files
            and not (candidate / name).exists()
            and not (candidate / name).is_symlink()
        )
    )
    return artifacts, deletions


def clone_target(target: Path, candidate: Path) -> None:
    """Clone the committed target without mutating its Git metadata."""
    result = run(
        [
            "git",
            "clone",
            "--quiet",
            "--no-hardlinks",
            str(target),
            str(candidate),
        ],
        capture=True,
        check=False,
    )
    if result.returncode != 0:
        raise CliError(
            result.stderr.strip() or "Cannot stage repository clone."
        )


def clone_working_tree(target: Path, candidate: Path) -> None:
    """Clone HEAD and overlay the current tracked and untracked worktree."""
    clone_target(target, candidate)
    patch = candidate.parent / "working-tree.patch"
    difference = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "git",
            "-C",
            str(target),
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "HEAD",
            "--",
        ],
        capture_output=True,
        check=False,
    )
    if difference.returncode != 0:
        detail = difference.stderr.decode(errors="replace").strip()
        raise CliError(detail or "Cannot stage tracked adoption work.")
    patch.write_bytes(difference.stdout)
    if difference.stdout:
        result = run(
            ["git", "-C", str(candidate), "apply", str(patch)],
            capture=True,
            check=False,
        )
        if result.returncode != 0:
            raise CliError(
                result.stderr.strip() or "Cannot stage tracked adoption work."
            )
    untracked = run(
        [
            "git",
            "-C",
            str(target),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        capture=True,
    ).stdout.split("\0")
    copy_candidate_files(
        target, candidate, tuple(path for path in untracked if path)
    )
    run(["git", "-C", str(candidate), "add", "--all"])
    run(
        [
            "git",
            "-C",
            str(candidate),
            "-c",
            "user.name=CSARC",
            "-c",
            "user.email=csarc@example.invalid",
            "commit",
            "--quiet",
            "--no-gpg-sign",
            "-m",
            "chore: stage pending adoption",
        ]
    )


def prepare_adoption_candidate(
    stage: Path,
    target: Path,
    revision: Revision,
    repository: RepositoryContext,
    answers: dict[str, object],
    planned: Plan,
    generated_at: str,
    candidate: Path,
    preserved_dirty_paths: tuple[str, ...] = (),
) -> tuple[Plan, dict[str, str], str, dict[str, object]]:
    """Build and verify the exact adoption result outside the target repo."""
    if preserved_dirty_paths:
        clone_working_tree(target, candidate)
    else:
        clone_target(target, candidate)
    copy_candidate_files(stage, candidate, (*planned.add, *planned.merge))
    hook_configuration = project_verification_configuration(candidate, answers)
    try:
        validated_project_verification_hook(candidate, hook_configuration)
    except CliError as error:
        verification = f"failed: {error}"
        hook = project_verification_evidence(
            hook_configuration, "failed", str(error)
        )
    else:
        if planned.manual or planned.unknown:
            write_pending_adoption(
                candidate,
                pending_adoption_data(
                    candidate,
                    revision,
                    repository,
                    config_path(candidate),
                    pending_managed_paths(stage, planned),
                    (*planned.manual, *planned.unknown),
                ),
            )
            verification = "deferred-manual-merge"
            hook = project_verification_evidence(
                hook_configuration,
                "not-run",
                "Manual file decisions must be completed first.",
            )
        else:
            create_adoption_lockfiles(candidate, answers)
            write_provenance(
                candidate,
                revision,
                applied_at=generated_at,
                answers=answers,
            )
            try:
                hook = verify_project(candidate)
            except ProjectVerificationError as error:
                verification = f"failed: {error}"
                hook = error.hook
            except CliError as error:
                verification = f"failed: {error}"
                hook = project_verification_evidence(
                    hook_configuration,
                    "not-run",
                    "Candidate preparation failed before the hook ran.",
                )
            else:
                verification = "passed"
    candidate_files = project_files(candidate)
    target_files = project_files(target)
    dirty_drift = tuple(
        name
        for name in preserved_dirty_paths
        if name not in candidate_files
        or name not in target_files
        or file_fingerprint(candidate_files[name])
        != file_fingerprint(target_files[name])
    )
    if dirty_drift:
        verification = (
            "failed: Candidate verification changed preserved dirty files: "
            + ", ".join(dirty_drift)
        )
    effects, artifacts = candidate_effects(candidate, target, planned)
    return effects, artifacts, verification, hook


def write_candidate_patch(
    candidate: Path,
    target: Path,
    patch: Path,
    *,
    artifacts: Mapping[str, object],
    target_snapshot: Mapping[str, object],
    delete_paths: tuple[str, ...] = (),
    include_paths: tuple[str, ...] = (),
) -> None:
    """Apply an already verified candidate as one checked byte-level patch."""
    before = patch.parent / "before"
    after = patch.parent / "after"
    before.mkdir()
    after.mkdir()
    target_files = project_files(target)
    expected_artifacts = {
        name: value
        for name, value in artifacts.items()
        if isinstance(name, str) and isinstance(value, str)
    }
    if len(expected_artifacts) != len(artifacts):
        raise CliError("Adoption plan contains invalid artifact fingerprints.")
    actual_artifacts, actual_deletions = candidate_patch_effects(
        candidate, include_paths=include_paths
    )
    canonical_deletions = tuple(sorted(set(delete_paths)))
    if (
        tuple(delete_paths) != canonical_deletions
        or actual_artifacts != expected_artifacts
        or actual_deletions != canonical_deletions
    ):
        raise CliError(
            "Candidate effects differ from the verified plan; create a new "
            "plan."
        )
    changed = tuple(sorted(expected_artifacts))
    for relative_name in (*changed, *canonical_deletions):
        checked_destination(target, relative_name)
    validate_target_snapshot(target, target_snapshot)
    existing = tuple(name for name in changed if name in target_files)
    copy_candidate_files(target, before, existing)
    copy_candidate_files(candidate, after, changed)
    copy_candidate_files(
        target,
        before,
        tuple(name for name in canonical_deletions if name in target_files),
    )
    patch_result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "git",
            "diff",
            "--no-index",
            "--binary",
            "--no-renames",
            "--",
            before.name,
            after.name,
        ],
        cwd=patch.parent,
        capture_output=True,
        check=False,
    )
    if patch_result.returncode not in {0, 1}:
        detail = patch_result.stderr.decode(errors="replace").strip()
        raise CliError(detail or "Cannot build candidate patch.")
    patch.write_bytes(patch_result.stdout)
    for check_only in (True, False):
        validate_target_snapshot(target, target_snapshot)
        command = ["git", "-C", str(target), "apply", "-p2"]
        if check_only:
            command.append("--check")
        command.append(str(patch))
        apply_result = run(command, capture=True, check=False)
        if apply_result.returncode != 0:
            detail = (
                apply_result.stderr.strip()
                or "Git rejected the candidate patch."
            )
            raise CliError(detail)


def create_adoption_lockfiles(  # noqa: C901
    target: Path, answers: dict[str, object]
) -> None:
    """Create language lockfiles after an adoption is ready to finalize."""
    languages = selected_languages(answers)
    if "python" in languages:
        python_version = target / ".python-version"
        if not python_version.is_file():
            raise CliError(
                "Cannot create uv.lock because .python-version is missing; "
                "restore the managed file, then rerun csarc adopt --finalize."
            )
        try:
            result = run(
                [
                    "uv",
                    "lock",
                    "--python",
                    python_version.read_text(encoding="utf-8").strip(),
                ],
                cwd=target,
                capture=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise CliError(
                "uv is required to create uv.lock; install uv, then rerun "
                "csarc adopt --finalize."
            ) from error
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise CliError(
                "Cannot create uv.lock after the manifest merge; fix "
                f"pyproject.toml, then rerun csarc adopt --finalize. {detail}"
            )
    if "typescript" in languages:
        try:
            result = run(
                ["pnpm", "install", "--lockfile-only", "--ignore-scripts"],
                cwd=target,
                capture=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise CliError(
                "pnpm is required to create pnpm-lock.yaml; install pnpm, "
                "then rerun csarc adopt --finalize."
            ) from error
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise CliError(
                "Cannot create pnpm-lock.yaml after the manifest merge; fix "
                f"package.json, then rerun csarc adopt --finalize. {detail}"
            )
    if "rust" in languages:
        try:
            result = run(
                ["cargo", "generate-lockfile"],
                cwd=target,
                capture=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise CliError(
                "Cargo is required to create Cargo.lock; install the Rust "
                "toolchain, then rerun csarc adopt --finalize."
            ) from error
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise CliError(
                "Cannot create Cargo.lock after the manifest merge; fix "
                f"Cargo.toml, then rerun csarc adopt --finalize. {detail}"
            )


def verify_project(target: Path) -> dict[str, object]:
    """Run canonical verification and one validated project hook."""
    configuration = project_verification_configuration(target)
    verify = target / "scripts" / "verify"
    if not verify.is_file():
        hook = project_verification_evidence(
            configuration,
            "not-run",
            "Canonical project verification is unavailable.",
        )
        raise ProjectVerificationError(
            "Generated project is missing ./scripts/verify.", hook
        )
    try:
        project_hook = validated_project_verification_hook(
            target, configuration
        )
    except CliError as error:
        hook = project_verification_evidence(
            configuration, "failed", str(error)
        )
        raise ProjectVerificationError(str(error), hook) from error
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as status_file:
        environment = dict(os.environ)
        environment.pop("_CSARC_PROJECT_VERIFICATION_STATUS_FILE", None)
        status_fd = status_file.fileno()
        environment["_CSARC_PROJECT_VERIFICATION_STATUS_FD"] = str(status_fd)
        result = subprocess.run(  # noqa: S603
            [str(verify)],
            cwd=target,
            check=False,
            env=environment,
            pass_fds=(status_fd,),
        )
        status_file.seek(0)
        hook_statuses = tuple(status_file.read().splitlines())
    expected_statuses = (
        ("not-run", "started", "passed")
        if project_hook is not None and result.returncode == 0
        else (
            ("not-run",)
            if project_hook is None or hook_statuses == ("not-run",)
            else ("not-run", "started", "failed")
        )
    )
    if hook_statuses != expected_statuses:
        hook = project_verification_evidence(
            configuration,
            "failed" if project_hook is not None else "not-run",
            "Canonical verification returned an invalid hook status.",
        )
        raise ProjectVerificationError(
            "Project verification hook status is invalid.", hook
        )
    if result.returncode != 0:
        if hook_statuses == ("not-run", "started", "failed"):
            hook = project_verification_evidence(
                configuration,
                "failed",
                "Project verification hook exited non-zero: "
                f"{configuration['path']}",
            )
            raise ProjectVerificationError(
                f"Project verification hook failed: {configuration['path']}",
                hook,
            )
        hook = project_verification_evidence(
            configuration,
            "not-run",
            "Canonical project verification failed before the hook ran.",
        )
        raise ProjectVerificationError(
            "Project verification failed; generated differences were "
            "preserved for review.",
            hook,
        )
    if project_hook is not None:
        return project_verification_evidence(
            configuration,
            "passed",
            "Project verification hook completed successfully.",
        )
    return project_verification_evidence(
        configuration,
        "not-run",
        "No project verification hook is configured.",
    )


def settings_plan(target: Path) -> None:
    """Run only the read-only repository settings plan."""
    settings = target / "scripts" / "apply-repository-settings.sh"
    if not settings.is_file():
        print("Repository settings plan unavailable: script is missing.")
        return
    result = run([str(settings), "plan"], cwd=target, check=False)
    if result.returncode != 0:
        print(
            "Repository settings plan needs a GitHub remote; "
            "no settings were applied."
        )


def target_repository(target: Path) -> str | None:
    """Return the GitHub origin of an existing target, when discoverable."""
    root = run(
        ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
        capture=True,
        check=False,
    )
    is_repository_root = (
        root.returncode == 0
        and Path(root.stdout.strip()).resolve() == target.resolve()
    )
    if is_repository_root:
        result = run(
            ["git", "-C", str(target), "remote", "get-url", "origin"],
            capture=True,
            check=False,
        )
        if result.returncode == 0:
            repository = github_repository(result.stdout.strip())
            if repository is not None:
                return repository
    explicit_repository = os.environ.get("GH_REPO", "").strip()
    if explicit_repository:
        return github_repository(f"gh:{explicit_repository}")
    return None


def repository_context(  # noqa: C901
    target: Path,
    explicit_visibility: str | None,
    *,
    saved_visibility: str | None = None,
) -> RepositoryContext:
    """Resolve repository owner and visibility before template rendering."""
    if (
        explicit_visibility is not None
        and explicit_visibility not in REPOSITORY_VISIBILITIES
    ):
        raise CliError(
            "project_visibility must be public, private, or internal."
        )
    repository = target_repository(target)
    if repository is None:
        visibility = explicit_visibility or saved_visibility or "private"
        if visibility not in REPOSITORY_VISIBILITIES:
            raise CliError(
                "Saved project_visibility must be public, private, or internal."
            )
        return RepositoryContext(
            repository=None,
            owner=None,
            owner_type=None,
            visibility=visibility,
            source=(
                "explicit"
                if explicit_visibility is not None
                else "saved"
                if saved_visibility is not None
                else "safe-default"
            ),
            verified=False,
            reason="No GitHub origin or GH_REPO was found.",
        )

    try:
        result = run(
            ["gh", "api", "--method", "GET", f"repos/{repository}"],
            capture=True,
            check=False,
        )
    except FileNotFoundError:
        result = subprocess.CompletedProcess(
            ["gh"], 1, stdout="", stderr="GitHub CLI is unavailable"
        )
    failure = result.stderr.strip() or "GitHub API request failed"
    payload: object = None
    if result.returncode == 0:
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            failure = "GitHub returned invalid repository JSON"
    if isinstance(payload, dict):
        owner = payload.get("owner")
        payload_visibility = payload.get("visibility")
        full_name = payload.get("full_name")
        if (
            isinstance(owner, dict)
            and isinstance(owner.get("login"), str)
            and isinstance(owner.get("type"), str)
            and isinstance(full_name, str)
            and full_name.casefold() == repository.casefold()
            and payload_visibility in REPOSITORY_VISIBILITIES
        ):
            actual_visibility = str(payload_visibility)
            if (
                explicit_visibility is not None
                and explicit_visibility != actual_visibility
            ):
                raise CliError(
                    "Explicit project_visibility does not match GitHub "
                    f"({explicit_visibility} != {actual_visibility})."
                )
            return RepositoryContext(
                repository=full_name,
                owner=str(owner["login"]),
                owner_type=str(owner["type"]).lower(),
                visibility=actual_visibility,
                source="github",
                verified=True,
            )
        failure = "GitHub returned incomplete repository metadata"

    if explicit_visibility is None:
        raise CliError(
            f"Cannot confirm visibility for {repository}: {failure}. Pass "
            "--data project_visibility=public|private|internal after "
            "verifying the repository setting."
        )
    return RepositoryContext(
        repository=repository,
        owner=repository.partition("/")[0],
        owner_type=None,
        visibility=explicit_visibility,
        source="explicit",
        verified=False,
        reason=failure,
    )


def validate_repository_context(
    target: Path,
    expected: RepositoryContext,
    explicit_visibility: str | None,
    *,
    saved_visibility: str | None = None,
) -> None:
    """Reject repository context drift after a plan was confirmed."""
    current = repository_context(
        target,
        explicit_visibility,
        saved_visibility=saved_visibility,
    )
    if current.as_dict() != expected.as_dict():
        raise CliError(
            "Repository context changed after the plan was created or "
            "confirmed; create a new plan."
        )


def gh_milestone_payload(arguments: list[str]) -> object:
    """Run one GitHub Milestone API request and validate its JSON shape."""
    try:
        result = run(["gh", "api", *arguments], capture=True, check=False)
    except FileNotFoundError as error:
        raise CliError(
            "GitHub CLI is required to inspect Milestone descriptions."
        ) from error
    if result.returncode != 0:
        detail = result.stderr.strip() or "GitHub API request failed"
        raise CliError(f"Cannot inspect Milestone descriptions: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CliError("GitHub returned invalid Milestone JSON.") from error
    return payload


def gh_pages(endpoint: str) -> list[dict[str, object]]:
    """Read all pages from one GitHub REST collection."""
    payload = gh_milestone_payload(["--paginate", "--slurp", endpoint])
    if not isinstance(payload, list):
        raise CliError("GitHub returned an unexpected Milestone response.")
    items: list[dict[str, object]] = []
    for page in payload:
        if not isinstance(page, list):
            raise CliError("GitHub returned an unexpected Milestone page.")
        for item in page:
            if not isinstance(item, dict):
                raise CliError("GitHub returned invalid Milestone metadata.")
            items.append(item)
    return items


def milestone_headings(description: str) -> tuple[str, ...]:
    """Return normalized H2 headings from one Milestone description."""
    return tuple(
        match.group(1).strip().casefold()
        for match in re.finditer(r"^##[ \t]+(.+?)[ \t]*$", description, re.M)
    )


def upgraded_milestone_description(
    description: str, issues: list[dict[str, object]]
) -> str | None:
    """Upgrade the exact legacy CSARC layout without rewriting prose."""
    if milestone_headings(description) != LEGACY_MILESTONE_HEADINGS:
        return None
    work: list[tuple[int, str]] = []
    for issue in issues:
        number = issue.get("number")
        if "pull_request" in issue or not isinstance(number, int):
            continue
        work.append(
            (
                number,
                str(issue.get("title", "")).strip(),
            )
        )
    work.sort()
    if not work:
        return None
    issue_plan = "\n".join(f"- #{number} — {title}" for number, title in work)
    upgraded = re.sub(
        r"^##[ \t]+Out of scope[ \t]*$",
        lambda _: f"## Plan\n\n{issue_plan}\n\n## Out of scope",
        description,
        count=1,
        flags=re.I | re.M,
    )
    return re.sub(
        r"^##[ \t]+Source[ \t]*$",
        "## References",
        upgraded,
        count=1,
        flags=re.I | re.M,
    )


def milestone_description_plan(  # noqa: C901
    target: Path,
    *,
    emit: bool = True,
) -> MilestoneDescriptionPlan | None:
    """Classify all target Milestones and print the proposed migration."""
    repository = target_repository(target)
    if repository is None:
        if emit:
            print(
                "Milestone descriptions: unavailable (no GitHub origin; "
                "review them manually)."
            )
        return None
    changes: list[MilestoneDescriptionChange] = []
    current: list[tuple[int, str]] = []
    review: list[tuple[int, str]] = []
    try:
        milestones = gh_pages(
            f"repos/{repository}/milestones?state=all&per_page=100"
        )
        for milestone in milestones:
            number = milestone.get("number")
            title = milestone.get("title")
            description = milestone.get("description")
            if not isinstance(number, int) or not isinstance(title, str):
                raise CliError("GitHub returned invalid Milestone metadata.")
            if not isinstance(description, str):
                review.append((number, title))
                continue
            headings = milestone_headings(description)
            if headings == CURRENT_MILESTONE_HEADINGS:
                current.append((number, title))
                continue
            if headings != LEGACY_MILESTONE_HEADINGS:
                review.append((number, title))
                continue
            issues = gh_pages(
                f"repos/{repository}/issues?state=all&milestone={number}"
                "&per_page=100"
            )
            upgraded = upgraded_milestone_description(description, issues)
            if upgraded is None:
                review.append((number, title))
                continue
            changes.append(
                MilestoneDescriptionChange(
                    number=number,
                    title=title,
                    before=description,
                    after=upgraded,
                )
            )
    except CliError as error:
        if emit:
            print(
                f"Milestone descriptions: unavailable ({error}; "
                "review them manually)."
            )
        return None
    plan = MilestoneDescriptionPlan(
        repository=repository,
        changes=tuple(changes),
        current=tuple(current),
        review=tuple(review),
    )
    if emit:
        print("Milestone description migration:")
        print_group(
            "  Upgrade",
            tuple(f"#{item.number} {item.title}" for item in plan.changes),
        )
        print_group(
            "  Current",
            tuple(f"#{number} {title}" for number, title in plan.current),
        )
        print_group(
            "  Manual review",
            tuple(f"#{number} {title}" for number, title in plan.review),
        )
    return plan


def apply_milestone_description_plan(
    plan: MilestoneDescriptionPlan | None,
) -> None:
    """Apply a confirmed migration without changing Milestone metadata."""
    if plan is None or not plan.changes:
        return
    for change in plan.changes:
        payload = gh_milestone_payload(
            [f"repos/{plan.repository}/milestones/{change.number}"]
        )
        if not isinstance(payload, dict):
            raise CliError("GitHub returned invalid Milestone metadata.")
        if payload.get("description") != change.before:
            raise CliError(
                f"Milestone #{change.number} changed after the dry-run plan; "
                "run the command again."
            )
    for change in plan.changes:
        result = run(
            [
                "gh",
                "api",
                "--method",
                "PATCH",
                f"repos/{plan.repository}/milestones/{change.number}",
                "--raw-field",
                f"description={change.after}",
            ],
            capture=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or "GitHub API request failed"
            raise CliError(
                f"Cannot upgrade Milestone #{change.number}: {detail}"
            )
    print(f"Milestone descriptions upgraded: {len(plan.changes)}")


def capability_preflight(
    script: Path, target: Path, *, emit: bool = True
) -> dict[str, object]:
    """Inspect release-related capabilities for planning only."""
    repository = target_repository(target)
    if repository is None or not script.is_file():
        unknown = {"state": "unknown", "reason": "runtime check required"}
        token_permissions = {
            name: dict(unknown)
            for name in ("actions_pull_requests", "contents", "release")
        }
        payload: dict[str, object] = {
            "mode": "blocked",
            "reason": "GitHub origin or capability script is unavailable",
            "organization_policy": dict(unknown),
            "repository_setting": dict(unknown),
            "token_permissions": token_permissions,
            "effective": {
                "mode": "blocked",
                "reason": "GitHub origin or capability script is unavailable",
            },
            "capabilities": token_permissions,
            "integrations": {
                "renovate": {
                    "state": "fallback",
                    "reason": (
                        "GitHub origin or capability script is unavailable"
                    ),
                    "next_step": (
                        "Keep GitHub Dependabot via .github/dependabot.yml "
                        "and the existing required CI/CD checks."
                    ),
                }
            },
        }
    else:
        result = run(
            [
                sys.executable,
                str(script),
                "preflight",
                "--repo",
                repository,
            ],
            capture=True,
            check=False,
        )
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = None
        payload = (
            cast(dict[str, object], parsed)
            if result.returncode == 0 and isinstance(parsed, dict)
            else {
                "mode": "blocked",
                "reason": "GitHub capability preflight was unavailable",
                "organization_policy": {},
                "repository_setting": {},
                "token_permissions": {},
                "effective": {
                    "mode": "blocked",
                    "reason": "GitHub capability preflight was unavailable",
                },
                "capabilities": {},
            }
        )
    if emit:
        print_capabilities(payload)
    return payload


def parse_languages(value: str) -> list[str]:
    """Parse a CLI language selection without defining combinations."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(parsed, list) or not all(
        isinstance(item, str) for item in parsed
    ):
        raise CliError("languages must be a JSON list or comma-separated list.")
    unknown = sorted(set(parsed) - {"python", "typescript", "rust"})
    if unknown:
        raise CliError(f"Unsupported language modules: {', '.join(unknown)}")
    return list(dict.fromkeys(parsed))


def required_release_inputs(value: object) -> list[str]:
    """Normalize the required workflow input names stored in flat config."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise CliError(
                "release_required_inputs must be a JSON list."
            ) from error
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise CliError(
            "release_required_inputs must be a list of non-empty strings."
        )
    return sorted(set(value))


def release_workflow_metadata(
    target: Path, relative_name: str
) -> dict[str, object]:
    """Inspect one repository-local workflow for its release contract."""
    relative = Path(relative_name)
    if (
        relative.is_absolute()
        or relative.parts[:2] != (".github", "workflows")
        or relative.suffix not in {".yml", ".yaml"}
    ):
        raise CliError(
            "release_workflow must be a YAML file under .github/workflows."
        )
    path = checked_destination(target, relative_name)
    if path.is_symlink() or not path.is_file():
        raise CliError(
            f"Selected release workflow does not exist: {relative_name}"
        )
    source = path.read_text(encoding="utf-8")
    try:
        workflow = yaml.safe_load(source)
    except yaml.YAMLError as error:
        raise CliError(
            f"Selected release workflow is invalid YAML: {relative_name}"
        ) from error
    if not isinstance(workflow, dict):
        raise CliError(
            f"Selected release workflow is not a mapping: {relative_name}"
        )
    events = workflow.get("on", workflow.get(True))
    dispatch = (
        events.get("workflow_dispatch") if isinstance(events, dict) else None
    )
    inputs = dispatch.get("inputs", {}) if isinstance(dispatch, dict) else {}
    if not isinstance(inputs, dict):
        raise CliError(
            f"Selected release workflow has invalid inputs: {relative_name}"
        )
    required = []
    for name, settings in inputs.items():
        if not isinstance(name, str) or not isinstance(settings, dict):
            raise CliError(
                f"Selected release workflow has invalid inputs: {relative_name}"
            )
        is_required = settings.get("required", False)
        if not isinstance(is_required, bool):
            raise CliError(
                f"Selected release workflow has invalid inputs: {relative_name}"
            )
        if is_required:
            required.append(name)
    return {
        "path": relative.as_posix(),
        "required_inputs": sorted(required),
        "writes_release": any(
            marker in source for marker in RELEASE_WRITER_MARKERS
        ),
    }


def release_writer_workflows(target: Path) -> list[dict[str, object]]:
    """Return every parseable workflow that explicitly writes a Release."""
    root = target / ".github" / "workflows"
    if not root.is_dir() or root.is_symlink():
        return []
    result = []
    for path in sorted((*root.glob("*.yml"), *root.glob("*.yaml"))):
        metadata = release_workflow_metadata(
            target, path.relative_to(target).as_posix()
        )
        if metadata["writes_release"]:
            result.append(metadata)
    return result


def release_ownership(answers: Mapping[str, object]) -> str:
    """Return an explicit owner, with project_mode as a legacy fallback."""
    ownership = answers.get("release_ownership")
    if ownership is None:
        project_mode = answers.get("project_mode")
        if project_mode == "new":
            return "csarc-owned"
        if project_mode == "existing":
            return "product-owned"
        raise CliError("project_mode must be new or existing.")
    if ownership not in RELEASE_OWNERSHIPS:
        raise CliError(
            "release_ownership must be csarc-owned, product-owned, or "
            "verification-only."
        )
    return str(ownership)


def release_contract(answers: Mapping[str, object]) -> dict[str, object]:
    """Return the normalized release contract used by every plan artifact."""
    ownership = release_ownership(answers)
    workflow = answers.get("release_workflow", "")
    reason = answers.get("release_ownership_reason", "")
    if (
        not isinstance(workflow, str)
        or not isinstance(reason, str)
        or not reason
    ):
        raise CliError("Release workflow ownership is incomplete.")
    inputs = required_release_inputs(answers.get("release_required_inputs"))
    if ownership == "verification-only" and (workflow or inputs):
        raise CliError(
            "verification-only release ownership cannot select a workflow."
        )
    if ownership != "verification-only" and not workflow:
        raise CliError(f"{ownership} release ownership requires a workflow.")
    expected_settings = {
        "csarc-owned": ("csarc-admin", "required"),
        "product-owned": ("product-admin", "product-defined"),
        "verification-only": ("none", "not-required"),
    }[ownership]
    settings_owner = answers.get("release_settings_owner", expected_settings[0])
    immutable = answers.get("release_immutable_releases", expected_settings[1])
    if (settings_owner, immutable) != expected_settings:
        raise CliError("Release repository settings do not match ownership.")
    return {
        "immutable_releases": immutable,
        "ownership": ownership,
        "reason": reason,
        "required_inputs": inputs,
        "selected_workflow": workflow or None,
        "settings_owner": settings_owner,
    }


def resolve_release_answers(  # noqa: C901
    target: Path, answers: Mapping[str, object]
) -> dict[str, object]:
    """Resolve one fail-closed release owner from repository evidence."""
    result = dict(answers)
    project_mode = result.get("project_mode")
    if project_mode not in {"new", "existing"}:
        raise CliError("project_mode must be new or existing.")
    explicit_owner = result.get("release_ownership")
    writers = release_writer_workflows(target)
    if explicit_owner is None:
        ownership = (
            "csarc-owned"
            if project_mode == "new"
            else "product-owned"
            if len(writers) == 1
            else "verification-only"
        )
    else:
        ownership = release_ownership(result)

    if ownership == "verification-only":
        selected = result.get("release_workflow", "")
        configured_inputs = required_release_inputs(
            result.get("release_required_inputs")
        )
        if selected or configured_inputs:
            raise CliError(
                "verification-only release ownership cannot select a workflow."
            )
        reason = result.get("release_ownership_reason")
        if not isinstance(reason, str) or not reason:
            reason = (
                "No product release writer was detected; CSARC verifies only."
                if not writers
                else "Multiple product release writers were detected; "
                "CSARC verifies only until one owner is selected."
            )
        result.update(
            release_immutable_releases="not-required",
            release_ownership=ownership,
            release_ownership_reason=reason,
            release_required_inputs=[],
            release_settings_owner="none",
            release_workflow="",
        )
        return result

    if ownership == "csarc-owned":
        selected = result.get("release_workflow", "")
        if not isinstance(selected, str):
            raise CliError("release_workflow must be a string.")
        expected = (
            ".github/workflows/release.yml"
            if project_mode == "new"
            else selected
        )
        if not expected:
            raise CliError(
                "Existing CSARC-owned release requires an explicit workflow."
            )
        if writers and (
            len(writers) != 1 or str(writers[0]["path"]) != expected
        ):
            raise CliError(
                "CSARC-owned release would duplicate a product release writer."
            )
        if project_mode == "existing" and not writers:
            raise CliError(
                "Existing CSARC-owned release workflow does not exist."
            )
        observed_inputs = (
            cast(list[str], writers[0]["required_inputs"]) if writers else []
        )
        saved_inputs = result.get("release_required_inputs")
        if (
            saved_inputs is not None
            and required_release_inputs(saved_inputs) != observed_inputs
        ):
            raise CliError("Selected release workflow input contract drifted.")
        result.update(
            release_immutable_releases="required",
            release_ownership=ownership,
            release_ownership_reason=(
                "CSARC owns the only version and GitHub Release workflow."
            ),
            release_required_inputs=observed_inputs,
            release_settings_owner="csarc-admin",
            release_workflow=expected,
        )
        return result

    if project_mode != "existing":
        raise CliError("product-owned release requires an existing repository.")
    if len(writers) != 1:
        raise CliError(
            "Product-owned release requires exactly one release-writing "
            "workflow."
        )
    workflow = writers[0]
    selected = result.get("release_workflow", "")
    if selected and selected != workflow["path"]:
        raise CliError(
            f"Selected release workflow {selected} is not the sole release "
            "writer."
        )
    observed_inputs = cast(list[str], workflow["required_inputs"])
    saved_inputs = result.get("release_required_inputs")
    if (
        saved_inputs is not None
        and required_release_inputs(saved_inputs) != observed_inputs
    ):
        raise CliError("Selected release workflow input contract drifted.")
    result.update(
        release_immutable_releases="product-defined",
        release_ownership=ownership,
        release_ownership_reason=(
            "The existing product workflow remains the only Release writer; "
            "CSARC never dispatches it."
        ),
        release_required_inputs=observed_inputs,
        release_settings_owner="product-admin",
        release_workflow=workflow["path"],
    )
    return result


def base_data(
    target: Path, mode: str, values: dict[str, str]
) -> dict[str, object]:
    """Build stable defaults while allowing explicit Copier answers."""
    slug = slugify(target.name)
    detected_languages = (
        detect_languages(target) if mode == "adopt" else ["python"]
    )
    data: dict[str, object] = {
        "project_mode": "existing" if mode == "adopt" else "new",
        "project_name": target.name.replace("-", " ").replace("_", " ").title(),
        "project_slug": slug,
        "package_name": slug.replace("-", "_").replace(".", "_"),
        "language": "-".join(detected_languages) or "ci",
        "languages": detected_languages,
        "code_owner": DEFAULT_OWNER,
    }
    if mode == "adopt":
        data["coverage_mode"] = "diff"
    data.update(values)
    if "languages" in values:
        data["languages"] = parse_languages(values["languages"])
    if "language" in values and "languages" not in values:
        legacy = values["language"]
        data["languages"] = [] if legacy == "ci" else legacy.split("-")
    if "package_name" not in values:
        data["package_name"] = (
            str(data["project_slug"]).replace("-", "_").replace(".", "_")
        )
    return resolve_release_answers(target, data)


def default_security_reporting_channel(repository_url: str) -> str:
    """Return the template's repository-derived public reporting channel."""
    return (
        f"Open a GitHub Issue at {repository_url}/issues/new; "
        "maintainers receive notifications for new Issues."
    )


def require_clean_repository(target: Path) -> None:
    """Require an existing repository with no tracked or untracked changes."""
    inside = run(
        ["git", "-C", str(target), "rev-parse", "--is-inside-work-tree"],
        capture=True,
        check=False,
    )
    if inside.returncode != 0:
        raise CliError(f"{target} must be an existing Git repository.")
    status = run(
        ["git", "-C", str(target), "status", "--porcelain"], capture=True
    )
    if status.stdout.strip():
        raise CliError("Git working tree must be clean before adopt or update.")


def resolve_repository_target(path: Path) -> Path:
    """Resolve any path inside one Git worktree to its root."""
    candidate = path.expanduser().resolve()
    result = run(
        ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
        capture=True,
        check=False,
    )
    if result.returncode != 0:
        raise CliError(
            f"{candidate} must be inside an existing Git repository."
        )
    return Path(result.stdout.strip()).resolve()


def validate_copy_target(
    target: Path, mode: str, *, require_clean: bool = True
) -> None:
    """Validate an init or adopt destination before release resolution."""
    if mode == "init" and target.exists() and any(target.iterdir()):
        raise CliError("init target must not exist or must be empty.")
    if mode != "adopt":
        return
    if not target.is_dir():
        raise CliError("adopt target must be an existing directory.")
    if (target / PENDING_ADOPTION_FILE).is_file():
        raise CliError(
            "Adoption is pending; complete the manual merge, then run "
            "csarc adopt --finalize."
        )
    if config_path(target).exists():
        raise CliError(
            "Repository already has CSARC configuration; use csarc update."
        )
    if require_clean:
        require_clean_repository(target)


def command_finalize_adoption(args: argparse.Namespace) -> int:  # noqa: C901
    """Plan or apply a verified second-stage adoption transaction."""
    target = resolve_repository_target(args.path or Path.cwd())
    if not target.is_dir():
        raise CliError("adopt target must be an existing directory.")
    if args.apply_plan is not None and args.dry_run:
        raise CliError(
            "adopt --finalize cannot combine --apply-plan and --dry-run."
        )
    if args.json and not args.dry_run:
        raise CliError("--json requires --dry-run for adopt --finalize.")
    if args.json and args.report_dir is not None:
        raise CliError("--report-dir cannot be combined with --json.")
    if not args.dry_run and args.apply_plan is None:
        raise CliError(
            "Run adopt --finalize --dry-run first, then apply its machine "
            "plan with --finalize --apply-plan."
        )
    if any((args.source, args.to, args.expected_sha, args.allow_unreleased)):
        raise CliError(
            "adopt --finalize uses the source and release saved by the "
            "pending adoption; do not pass release-selection options."
        )

    explicit_data = parse_data(args.data)
    if args.apply_plan is not None and explicit_data:
        raise CliError(
            "--apply-plan uses the repository state saved by dry-run."
        )
    unsupported = sorted(set(explicit_data) - {"project_visibility"})
    if unsupported:
        raise CliError(
            "adopt --finalize only accepts project_visibility; saved Copier "
            f"answers cannot change ({', '.join(unsupported)})."
        )
    saved: dict[str, object] | None = None
    if args.apply_plan is not None:
        plan_path = args.apply_plan.expanduser().resolve()
        if plan_path == target or target in plan_path.parents:
            raise CliError(
                "Adoption plans must remain outside the target repo."
            )
        saved = read_adoption_plan(plan_path)
        if saved.get("mode") != "adopt-finalize" or saved.get("target") != str(
            target
        ):
            raise CliError(
                "Finalize plan does not match this target repository."
            )

    pending = read_pending_adoption(target)
    raw_template = pending["template"]
    raw_repository = pending["repository"]
    raw_managed = pending["managed_files"]
    if (
        not isinstance(raw_template, dict)
        or not isinstance(raw_repository, dict)
        or not isinstance(raw_managed, list)
    ):
        raise CliError("Pending adoption state is invalid.")
    source = raw_template.get("source")
    release = raw_template.get("release")
    sha = raw_template.get("sha")
    verification = raw_template.get("verification")
    if (
        not isinstance(source, str)
        or not source
        or not isinstance(release, str)
        or not release
        or not isinstance(sha, str)
        or FULL_SHA.fullmatch(sha) is None
        or verification not in {"verified", "development-unreleased"}
    ):
        raise CliError(
            "Pending template identity is invalid; restore the checkpoint or "
            "restart adoption from a clean commit."
        )

    answers_path = checked_destination(
        target, config_path(target).relative_to(target).as_posix()
    )
    if answers_path.is_symlink() or not answers_path.is_file():
        raise CliError(
            "Pending adoption is missing the CSARC configuration; restore the "
            "managed file, then rerun csarc adopt --finalize."
        )
    actual_answers_hash = hashlib.sha256(answers_path.read_bytes()).hexdigest()
    if actual_answers_hash != pending["answers_sha256"]:
        raise CliError(
            "Copier answers changed after adoption started; restore "
            "configuration or restart adoption from a clean commit."
        )
    if read_answer(answers_path, "_src_path") != source:
        raise CliError(
            "Copier source drifted after adoption started; restore the saved "
            "answers or restart adoption from a clean commit."
        )
    if read_answer(answers_path, "_commit").lower() != sha.lower():
        raise CliError(
            "Copier commit drifted after adoption started; restore the saved "
            "answers or restart adoption from a clean commit."
        )
    allow_unreleased = verification == "development-unreleased"
    revision = resolve_revision(
        source,
        release,
        expected_sha=sha,
        allow_unreleased=allow_unreleased,
    )
    source_path = Path(source).expanduser()
    if allow_unreleased:
        if not source_path.exists():
            raise CliError(
                "Pending unreleased template source is unavailable; restore "
                "the same local source, then rerun csarc adopt --finalize."
            )
        git_commit(source_path, sha)

    for item in raw_managed:
        if not isinstance(item, dict):
            raise CliError("Pending managed-file state is invalid.")
        name = item.get("path")
        expected = item.get("fingerprint")
        if not isinstance(name, str) or not isinstance(expected, str):
            raise CliError("Pending managed-file state is invalid.")
        relative_path = Path(name)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise CliError("Pending managed-file path is invalid.")
        path = target / relative_path
        if file_fingerprint(path) != expected:
            raise CliError(
                f"Managed adoption file drifted: {name}. Restore it from the "
                "pending template revision, then rerun csarc adopt --finalize."
            )

    answers = read_copier_answers(answers_path)
    saved_visibility = answers.get("project_visibility")
    if not isinstance(saved_visibility, str):
        raise CliError("Copier answers are missing project_visibility.")
    explicit_visibility = explicit_data.get("project_visibility")
    if (
        explicit_visibility is None
        and raw_repository.get("source") == "explicit"
    ):
        explicit_visibility = saved_visibility
    repository = repository_context(
        target,
        explicit_visibility,
        saved_visibility=saved_visibility,
    )
    saved_repository = raw_repository.get("repository")
    if saved_repository is not None and not isinstance(saved_repository, str):
        raise CliError("Pending repository identity is invalid.")
    repository_matches = (
        repository.repository is None and saved_repository is None
    ) or (
        isinstance(saved_repository, str)
        and repository.repository is not None
        and repository.repository.casefold() == saved_repository.casefold()
    )
    if not repository_matches or repository.visibility != raw_repository.get(
        "visibility"
    ):
        raise CliError(
            "Repository origin or visibility changed after adoption started; "
            "restore it or restart adoption from a clean commit."
        )

    capabilities = capability_preflight(
        target / "scripts" / "release_policy.py", target, emit=False
    )
    raw_manual = pending.get("manual_files", [])
    manual_files = (
        tuple(value for value in raw_manual if isinstance(value, str))
        if isinstance(raw_manual, list)
        else ()
    )
    with tempfile.TemporaryDirectory(prefix="csarc-finalize-") as temporary:
        temporary_root = Path(temporary)
        stage = temporary_root / "rendered"
        stage.mkdir()
        copier_copy(source, revision, stage, answers)
        baseline = temporary_root / "baseline"
        clone_target(target, baseline)
        merged = apply_adoption_policies(stage, baseline)
        planned = compare_stage(
            stage, baseline, adopt=True, merged_paths=merged
        )
        validate_pending_file_sets(target, pending, stage, planned)

        if saved is None:
            generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        else:
            saved_adoption = saved.get("adoption")
            if not isinstance(saved_adoption, dict) or not isinstance(
                saved_adoption.get("generated_at"), str
            ):
                raise CliError("Finalize plan has invalid target state.")
            generated_at = str(saved_adoption["generated_at"])
        candidate = temporary_root / "candidate"
        clone_working_tree(target, candidate)
        create_adoption_lockfiles(candidate, answers)
        write_provenance(
            candidate,
            revision,
            applied_at=generated_at,
            answers=answers,
        )
        checked_destination(
            candidate, PENDING_ADOPTION_FILE.as_posix()
        ).unlink()
        try:
            hook = verify_project(candidate)
        except CliError as error:
            raise CliError(
                "Project verification failed; fix the reported failures, "
                "then rerun csarc adopt --finalize."
            ) from error
        effects, artifacts = candidate_effects(
            candidate,
            target,
            Plan((), (), (), (), (), ()),
        )
        head, changes, status_sha256 = target_state(target)
        target_files = target_file_snapshot(target)
        manual_results = {
            name: target_files.get(name, "missing") for name in manual_files
        }
        adoption: dict[str, object] = {
            "applicable": True,
            "artifacts": artifacts,
            "checkpoint_sha256": file_fingerprint(
                target / PENDING_ADOPTION_FILE
            ),
            "clean": not changes,
            "code_owner": code_owner_verification(
                repository, answers.get("code_owner")
            ),
            "delete_paths": [PENDING_ADOPTION_FILE.as_posix()],
            "generated_at": generated_at,
            "manual_results": manual_results,
            "phase": "complete",
            "project_verification_hook": hook,
            "target_changes": list(changes),
            "target_files": target_files,
            "target_head": head,
            "target_status_sha256": status_sha256,
            "verification": "passed",
        }
        plan = ResolvedPlan(
            mode="adopt-finalize",
            target=target,
            revision=revision,
            repository=repository,
            answers=answers,
            capabilities=capabilities,
            files=effects,
            adoption=adoption,
        )
        fresh_payload = adoption_plan_payload(plan)
        if saved is not None and adoption_binding(
            fresh_payload
        ) != adoption_binding(saved):
            raise CliError(
                "Repository or manual merge results drifted after finalize "
                "dry-run; create a new finalize plan."
            )
        if args.json:
            print(
                json.dumps(
                    plan.as_dict(), sort_keys=True, separators=(",", ":")
                )
            )
        else:
            print_plan(plan)
            print("Pending state: verified; ready to finalize.")
        milestone_plan = milestone_description_plan(target, emit=not args.json)
        if args.dry_run:
            write_adoption_reports(plan, args.report_dir, emit=not args.json)
            return 0
        if not confirm(args):
            return 0
        validate_repository_context(
            target,
            repository,
            explicit_visibility,
            saved_visibility=saved_visibility,
        )
        validate_target_snapshot(target, adoption)
        write_candidate_patch(
            candidate,
            target,
            temporary_root / "finalize.patch",
            artifacts=artifacts,
            target_snapshot=adoption,
            delete_paths=(PENDING_ADOPTION_FILE.as_posix(),),
        )
    settings_plan(target)
    apply_milestone_description_plan(milestone_plan)
    write_adoption_reports(
        mark_adoption_applied(
            plan, datetime.now(UTC).replace(microsecond=0).isoformat()
        ),
        args.report_dir,
        emit=not args.json,
    )
    print("Adoption complete.")
    return 0


def predicted_adoption_effects(target: Path, planned: Plan) -> Plan:
    """Include the checkpoint or provenance file in a review-only forecast."""
    runtime = (
        PENDING_ADOPTION_FILE
        if planned.manual or planned.unknown
        else PROVENANCE_FILE
    )
    additions = set(planned.add)
    if not (target / runtime).exists():
        additions.add(runtime.as_posix())
    return Plan(
        tuple(sorted(additions)),
        planned.overwrite,
        planned.preserve,
        planned.merge,
        planned.manual,
        planned.unknown,
    )


def build_adoption_plan(
    stage: Path,
    candidate: Path,
    target: Path,
    revision: Revision,
    repository: RepositoryContext,
    answers: dict[str, object],
    capabilities: dict[str, object],
    generated_at: str,
) -> ResolvedPlan:
    """Build one locked adoption plan and its isolated candidate."""
    head, changes, status_sha256 = target_state(target)
    target_files = target_file_snapshot(target)
    dirty_paths = tuple(sorted(git_changed_paths(target))) if changes else ()
    merged = apply_adoption_policies(stage, target)
    planned = compare_stage(stage, target, adopt=True, merged_paths=merged)
    preserved_dirty_paths = (
        dirty_paths
        if dirty_paths
        and all(change[:2] == " M" for change in changes)
        and set(dirty_paths).issubset(planned.preserve)
        else ()
    )
    candidate_allowed = not changes or bool(preserved_dirty_paths)
    artifacts: dict[str, str] = {}
    if not candidate_allowed:
        files = predicted_adoption_effects(target, planned)
        verification = "not-run-dirty"
    else:
        files, artifacts, verification, hook = prepare_adoption_candidate(
            stage,
            target,
            revision,
            repository,
            answers,
            planned,
            generated_at,
            candidate,
            preserved_dirty_paths,
        )
    owner = code_owner_verification(repository, answers.get("code_owner"))
    if not candidate_allowed:
        hook = project_verification_configuration(target, answers)
        hook = project_verification_evidence(
            hook,
            "not-run",
            "Dirty paths must be unstaged tracked modifications preserved by "
            "the adoption plan.",
        )
    adoption: dict[str, object] = {
        "applicable": candidate_allowed
        and verification in {"passed", "deferred-manual-merge"}
        and owner["state"] != "blocked",
        "artifacts": artifacts,
        "clean": not changes,
        "code_owner": owner,
        "generated_at": generated_at,
        "phase": (
            "pending" if planned.manual or planned.unknown else "complete"
        ),
        "preserved_dirty_paths": list(preserved_dirty_paths),
        "project_verification_hook": hook,
        "target_changes": list(changes),
        "target_files": target_files,
        "target_head": head,
        "target_status_sha256": status_sha256,
        "verification": verification,
    }
    validate_target_snapshot(target, adoption)
    return ResolvedPlan(
        mode="adopt",
        target=target,
        revision=revision,
        repository=repository,
        answers=answers,
        capabilities=capabilities,
        files=files,
        adoption=adoption,
    )


def command_apply_adoption_plan(  # noqa: C901
    args: argparse.Namespace, target: Path
) -> int:
    """Rebuild, verify, and apply exactly one saved adoption plan."""
    if args.dry_run or args.json:
        raise CliError(
            "--apply-plan cannot be combined with --dry-run or --json."
        )
    if any((args.source, args.to, args.expected_sha, args.allow_unreleased)):
        raise CliError(
            "--apply-plan uses the source and SHA saved by dry-run; do not "
            "pass release-selection options."
        )
    if args.data:
        raise CliError("--apply-plan uses the answers saved by dry-run.")
    plan_path = args.apply_plan.expanduser().resolve()
    if plan_path == target or target in plan_path.parents:
        raise CliError("Adoption plans must remain outside the target repo.")
    saved = read_adoption_plan(plan_path)
    if saved.get("mode") != "adopt" or saved.get("target") != str(target):
        raise CliError("Adoption plan does not match this target repository.")
    raw_adoption = saved.get("adoption")
    raw_template = saved.get("template")
    raw_answers = saved.get("answers")
    raw_repository = saved.get("repository")
    raw_capabilities = saved.get("release_capabilities")
    if not all(
        isinstance(value, dict)
        for value in (
            raw_adoption,
            raw_template,
            raw_answers,
            raw_repository,
            raw_capabilities,
        )
    ):
        raise CliError("Adoption plan has an unsupported shape.")
    raw_adoption = cast(dict[str, object], raw_adoption)
    raw_template = cast(dict[str, object], raw_template)
    raw_answers = cast(dict[str, object], raw_answers)
    raw_repository = cast(dict[str, object], raw_repository)
    raw_capabilities = cast(dict[str, object], raw_capabilities)
    if raw_adoption.get("applicable") is not True:
        raise CliError(
            "Adoption plan is review-only; clean the repository or resolve "
            "the reported failure, then rerun --dry-run."
        )
    source = raw_template.get("source")
    release = raw_template.get("release")
    sha = raw_template.get("sha")
    verification = raw_template.get("verification")
    generated_at = raw_adoption.get("generated_at")
    if (
        not isinstance(source, str)
        or not isinstance(release, str)
        or not isinstance(sha, str)
        or not isinstance(generated_at, str)
        or verification not in {"verified", "unverified"}
    ):
        raise CliError("Adoption plan has invalid template identity.")
    if raw_adoption.get("clean") is True:
        require_clean_repository(target)
    else:
        validate_target_snapshot(target, raw_adoption)
    revision = resolve_revision(
        source,
        release,
        expected_sha=sha,
        allow_unreleased=verification == "unverified",
    )
    answers = {str(key): value for key, value in raw_answers.items()}
    visibility = answers.get("project_visibility")
    if not isinstance(visibility, str):
        raise CliError("Adoption plan has no project_visibility answer.")
    explicit_visibility = (
        visibility if raw_repository.get("source") == "explicit" else None
    )
    repository = repository_context(target, explicit_visibility)
    with tempfile.TemporaryDirectory(prefix="csarc-apply-") as temporary:
        temporary_root = Path(temporary)
        stage = temporary_root / "rendered"
        stage.mkdir()
        copier_copy(source, revision, stage, answers)
        candidate = temporary_root / "candidate"
        fresh = build_adoption_plan(
            stage,
            candidate,
            target,
            revision,
            repository,
            answers,
            raw_capabilities,
            generated_at,
        )
        fresh_payload = adoption_plan_payload(fresh)
        saved_binding = adoption_binding(saved)
        fresh_binding = adoption_binding(fresh_payload)
        if fresh_binding != saved_binding:
            differences = json_differences(saved_binding, fresh_binding)
            detail = "; ".join(differences[:10])
            if len(differences) > 10:
                detail += f"; ... and {len(differences) - 10} more"
            raise CliError(
                "Repository or rendered output drifted after dry-run; create "
                f"a new adoption plan. Differing fields: {detail}"
            )
        if (
            fresh.adoption is None
            or fresh.adoption.get("applicable") is not True
        ):
            raise CliError("Rebuilt adoption candidate is not applicable.")
        artifacts = fresh.adoption.get("artifacts")
        if not isinstance(artifacts, dict):
            raise CliError("Rebuilt adoption candidate has no artifact plan.")
        print_plan(fresh)
        milestone_plan = milestone_description_plan(target)
        if not confirm(args):
            return 0
        validate_repository_context(
            target,
            fresh.repository,
            explicit_visibility,
        )
        validate_target_snapshot(target, fresh.adoption)
        write_candidate_patch(
            candidate,
            target,
            temporary_root / "adopt.patch",
            artifacts=artifacts,
            target_snapshot=fresh.adoption,
        )

    phase = fresh.adoption.get("phase")
    if phase == "pending":
        print(
            "Adoption pending: complete the listed manual merges, then run "
            "csarc adopt --finalize."
        )
        return 1
    settings_plan(target)
    apply_milestone_description_plan(milestone_plan)
    write_adoption_reports(
        mark_adoption_applied(
            fresh, datetime.now(UTC).replace(microsecond=0).isoformat()
        ),
        args.report_dir,
        emit=not args.json,
    )
    print("Adoption complete.")
    return 0


def command_copy(args: argparse.Namespace, mode: str) -> int:  # noqa: C901
    """Plan and apply init or adopt."""
    target = (
        resolve_repository_target(args.path or Path.cwd())
        if mode == "adopt"
        else args.path.expanduser().resolve()
    )
    if mode == "adopt" and args.apply_plan is None:
        args.dry_run = True
    if mode == "adopt" and args.finalize:
        return command_finalize_adoption(args)
    if mode == "adopt" and args.apply_plan is not None:
        return command_apply_adoption_plan(args, target)
    validate_copy_target(
        target, mode, require_clean=mode != "adopt" or not args.dry_run
    )
    if mode == "adopt" and args.report_dir is not None and not args.dry_run:
        raise CliError("--report-dir requires adopt --dry-run.")
    if args.json and not args.dry_run:
        raise CliError("--json requires --dry-run for init or adopt.")
    if args.json and mode == "adopt" and args.report_dir is not None:
        raise CliError("--report-dir cannot be combined with --json.")
    source = args.source or CANONICAL_SOURCE
    revision = resolve_revision(
        source,
        args.to,
        expected_sha=args.expected_sha,
        allow_unreleased=args.allow_unreleased,
    )
    if not revision.verified:
        print(
            "WARNING: --allow-unreleased bypasses release identity, "
            "immutability, attestation, and signature verification.",
            file=sys.stderr,
        )
    explicit_data = parse_data(args.data)
    repository = repository_context(
        target, explicit_data.get("project_visibility")
    )
    data = base_data(target, mode, explicit_data)
    data["project_visibility"] = repository.visibility
    if repository.repository is not None:
        data["repository_url"] = f"https://github.com/{repository.repository}"
    with tempfile.TemporaryDirectory(prefix="csarc-plan-") as temporary:
        stage = Path(temporary) / "project"
        stage.mkdir()
        copier_copy(revision.source, revision, stage, data)
        answers: dict[str, object] = dict(data)
        answers.update(read_copier_answers(config_path(stage)))
        capabilities = capability_preflight(
            stage / "scripts" / "release_policy.py", target, emit=False
        )
        if mode == "adopt":
            generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
            plan = build_adoption_plan(
                stage,
                Path(temporary) / "candidate",
                target,
                revision,
                repository,
                answers,
                capabilities,
                generated_at,
            )
        else:
            plan = ResolvedPlan(
                mode=mode,
                target=target,
                revision=revision,
                repository=repository,
                answers=answers,
                capabilities=capabilities,
                files=compare_stage(stage, target, adopt=False),
            )
        if args.json:
            print(
                json.dumps(
                    plan.as_dict(), sort_keys=True, separators=(",", ":")
                )
            )
        else:
            print_plan(plan)
        if mode == "adopt" and args.dry_run:
            write_adoption_reports(plan, args.report_dir, emit=not args.json)
        if mode == "adopt":
            milestone_description_plan(target, emit=not args.json)
        if args.dry_run or not confirm(args):
            return 0
        if mode == "init":
            if target.exists():
                target.rmdir()
            shutil.copytree(stage, target, symlinks=True)
        else:
            raise CliError("Adoption requires a saved machine plan.")

    verify_project(target)
    write_provenance(target, revision, answers=answers)
    settings_plan(target)
    return 0


def read_answer(path: Path, key: str) -> str:
    """Read a scalar from Copier answers without adding a YAML dependency."""
    prefix = f"{key}:"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip().strip("'\"")
    raise CliError(f"Copier answers are missing {key}.")


def find_conflicts(target: Path) -> tuple[str, ...]:
    """Find Copier rejection files and unresolved conflict markers."""
    conflicts: list[str] = []
    marker = re.compile(r"^(<{7}|={7}|>{7})( |$)")
    for relative_name, path in project_files(target).items():
        if relative_name.endswith(".rej"):
            conflicts.append(relative_name)
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        if any(marker.match(line) for line in lines):
            conflicts.append(relative_name)
    return tuple(sorted(conflicts))


def current_revision(
    target: Path,
    source: str,
    commit: str,
    *,
    allow_unreleased: bool,
    accept_legacy: bool,
    from_release: str | None,
    client: ReleaseClient | None = None,
) -> tuple[Revision, dict[str, object] | None]:
    """Verify saved provenance or explicitly migrate a legacy installation."""
    if FULL_SHA.fullmatch(commit) is None:
        raise CliError("Copier answers do not contain a full commit SHA.")
    saved = read_provenance(target)
    if allow_unreleased:
        revision = resolve_revision(
            source,
            commit,
            allow_unreleased=True,
            client=client,
        )
        if saved is not None and saved.get("commit_sha") != revision.sha:
            raise CliError("Saved provenance does not match Copier answers.")
        return revision, saved

    if saved is None:
        if not accept_legacy or from_release is None:
            raise CliError(
                "Legacy repository has no verifiable provenance; review the "
                "Copier source/SHA, then pass --accept-legacy and "
                "--from-release <tag>."
            )
        revision = resolve_revision(
            source,
            from_release,
            expected_sha=commit,
            client=client,
        )
        return revision, {
            "commit_sha": commit.lower(),
            "release_tag": from_release,
            "repository": source,
            "verification": "legacy-unverified",
        }

    required = {
        "commit_sha": commit.lower(),
        "repository": CANONICAL_REPOSITORY,
        "repository_id": CANONICAL_REPOSITORY_ID,
        "schema_version": 1,
        "verification": "verified",
    }
    for key, expected in required.items():
        if saved.get(key) != expected:
            raise CliError(f"Saved provenance field {key!r} is not trusted.")
    tag = saved.get("release_tag")
    if not isinstance(tag, str) or not tag:
        raise CliError("Saved provenance has no release tag.")
    revision = resolve_revision(source, tag, expected_sha=commit, client=client)
    if (
        saved.get("release_id") != revision.release_id
        or saved.get("release_immutable") is not True
        or saved.get("release_attestation_verified") is not True
        or saved.get("signature_verified") is not True
    ):
        raise CliError("Saved release provenance does not match GitHub.")
    return revision, saved


def update_status(
    target: Path,
    requested: str | None,
    *,
    expected_sha: str | None = None,
    allow_unreleased: bool = False,
    accept_legacy: bool = False,
    from_release: str | None = None,
    client: ReleaseClient | None = None,
) -> tuple[dict[str, object], Revision, dict[str, object] | None]:
    """Return stable status plus verified current and target state."""
    answers = config_path(target)
    if not answers.is_file():
        raise CliError(f"Missing {CONFIG_FILE}; use csarc adopt first.")
    source = read_answer(answers, "_src_path")
    current = read_answer(answers, "_commit")
    previous_revision, previous = current_revision(
        target,
        source,
        current,
        allow_unreleased=allow_unreleased,
        accept_legacy=accept_legacy,
        from_release=from_release,
        client=client,
    )
    target_revision = resolve_revision(
        source,
        requested,
        expected_sha=expected_sha,
        allow_unreleased=allow_unreleased,
        client=client,
    )
    status: dict[str, object] = {
        "current_version": previous_revision.label,
        "current_sha": previous_revision.sha,
        "current_verification": (
            "verified" if previous_revision.verified else "unverified"
        ),
        "source": source,
        "status": (
            "current"
            if previous_revision.sha == target_revision.sha
            else "outdated"
        ),
        "target_sha": target_revision.sha,
        "target_version": target_revision.label,
        "target_verification": (
            "verified" if target_revision.verified else "unverified"
        ),
        "update_available": previous_revision.sha != target_revision.sha,
    }
    return status, target_revision, previous


def repository_target_is_new(target: Path) -> bool:
    """Return whether a target is unwritten: missing or an empty directory.

    Mirrors the `init` scope check in `validate_copy_target` so the two
    functions never disagree about what counts as a brand-new project.
    """
    return not target.exists() or not any(target.iterdir())


def run_policy_settings_check(
    target: Path,
) -> subprocess.CompletedProcess[str]:
    """Run one target's own read-only repository policy-drift check."""
    script = target / "scripts" / "apply-repository-settings.sh"
    if not script.is_file():
        return subprocess.CompletedProcess(
            [str(script), "check"],
            127,
            "",
            "scripts/apply-repository-settings.sh is missing.",
        )
    return run([str(script), "check"], cwd=target, capture=True, check=False)


def classify_policy_check(
    result: subprocess.CompletedProcess[str],
) -> PolicyCheckResult:
    """Classify one policy-drift check without guessing at ambiguous output.

    `scripts/apply-repository-settings.sh check` either runs its full
    comparison to completion -- exit 0 for a clean match, or exit 1 with its
    own `POLICY_CHECK_COMPLETED_MARKER` summary line once it has counted at
    least one actionable difference -- or it hard-stops early on something
    it cannot recover from: missing/unauthenticated `gh`, an unidentifiable
    repository, unreadable repository metadata, a transient or
    rate-limited `gh api` call (for example its own "Cannot determine
    Ruleset capability" guard), an unusable invocation, or a missing script.
    Keying off the script's own completion marker -- rather than
    enumerating every hard-stop message the script can print -- means any
    hard-stop path the script has today or gains later is treated as
    unavailable by default instead of silently being misread as confirmed
    drift.
    """
    output = "\n".join(
        part for part in (result.stdout, result.stderr) if part
    ).strip()
    if result.returncode == 0:
        return PolicyCheckResult(True, False, output or "no drift detected")
    if POLICY_CHECK_COMPLETED_MARKER in output:
        return PolicyCheckResult(True, True, output or "policy drift detected")
    return PolicyCheckResult(False, None, output or "policy check unavailable")


def detect_install_state(
    target: Path,
    *,
    requested: str | None = None,
    expected_sha: str | None = None,
    allow_unreleased: bool = False,
    accept_legacy: bool = False,
    from_release: str | None = None,
    client: ReleaseClient | None = None,
    policy_check: (
        Callable[[Path], subprocess.CompletedProcess[str]] | None
    ) = None,
) -> dict[str, object]:
    """Deterministically classify a target into one of five install states.

    Reads only `.csarc/config.yml` (or legacy Copier answers), the pinned
    Copier revision, and `policies/` drift; it never infers a state from
    free-form judgment, so repeated runs against unchanged repository state
    always return the same classification. The five states are: `create`
    (no target yet, or an empty directory), `adopt` (an existing repository
    without CSARC configuration), `update` (a pinned Copier revision behind
    the resolved target release), `current` (revision and policy settings
    both match), and `policy-only-update` (revision matches but the live
    repository policy settings have drifted from `policies/`).
    """
    if repository_target_is_new(target):
        return {
            "next_command": INSTALL_STATE_NEXT_COMMAND[INSTALL_STATE_CREATE],
            "reason": f"{target} does not exist or is an empty directory.",
            "state": INSTALL_STATE_CREATE,
        }
    answers_path = config_path(target)
    if not answers_path.is_file():
        return {
            "next_command": INSTALL_STATE_NEXT_COMMAND[INSTALL_STATE_ADOPT],
            "reason": (
                f"{target} has no {CONFIG_FILE}; it is not yet CSARC-managed."
            ),
            "state": INSTALL_STATE_ADOPT,
        }
    status, _target_revision, _previous = update_status(
        target,
        requested,
        expected_sha=expected_sha,
        allow_unreleased=allow_unreleased,
        accept_legacy=accept_legacy,
        from_release=from_release,
        client=client,
    )
    if status["update_available"]:
        return {
            "next_command": INSTALL_STATE_NEXT_COMMAND[INSTALL_STATE_UPDATE],
            "reason": (
                f"Copier revision {status['current_sha']} is behind "
                f"target {status['target_sha']}."
            ),
            "state": INSTALL_STATE_UPDATE,
            "update_status": status,
        }
    check_result = (policy_check or run_policy_settings_check)(target)
    policy = classify_policy_check(check_result)
    policy_report = {
        "available": policy.available,
        "detail": policy.detail,
        "drifted": policy.drifted,
    }
    if not policy.available:
        return {
            "next_command": INSTALL_STATE_NEXT_COMMAND[INSTALL_STATE_CURRENT],
            "policy_check": policy_report,
            "reason": (
                "Copier revision is current; repository policy drift could "
                f"not be checked: {policy.detail}"
            ),
            "state": INSTALL_STATE_CURRENT,
            "update_status": status,
        }
    if policy.drifted:
        return {
            "next_command": (
                INSTALL_STATE_NEXT_COMMAND[INSTALL_STATE_POLICY_ONLY]
            ),
            "policy_check": policy_report,
            "reason": (
                "Copier revision is current; repository policy settings "
                "have drifted from policies/."
            ),
            "state": INSTALL_STATE_POLICY_ONLY,
            "update_status": status,
        }
    return {
        "next_command": INSTALL_STATE_NEXT_COMMAND[INSTALL_STATE_CURRENT],
        "policy_check": policy_report,
        "reason": (
            "Copier revision and repository policy settings are both current."
        ),
        "state": INSTALL_STATE_CURRENT,
        "update_status": status,
    }


def command_status(args: argparse.Namespace) -> int:
    """Report the deterministic install state without changing anything."""
    raw_target = args.path.expanduser()
    target = (
        raw_target.resolve()
        if repository_target_is_new(raw_target)
        else resolve_repository_target(raw_target)
    )
    result = detect_install_state(
        target,
        requested=args.to,
        expected_sha=args.expected_sha,
        allow_unreleased=args.allow_unreleased,
        accept_legacy=args.accept_legacy,
        from_release=args.from_release,
    )
    result["target"] = str(target)
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(f"Target: {result['target']}")
        print(f"Install state: {result['state']}")
        print(f"Reason: {result['reason']}")
        print(f"Next: {result['next_command']}")
    return 0


def update_plan_answers(  # noqa: C901
    answers: dict[str, object],
    explicit_data: dict[str, str],
    repository: RepositoryContext,
) -> tuple[dict[str, object], dict[str, object]]:
    """Resolve update answers and Copier overrides from repository facts."""
    result = dict(answers)
    update_data: dict[str, object] = dict(explicit_data)
    release_ownership(answers)
    release_keys = {
        "release_ownership",
        "release_ownership_reason",
        "release_immutable_releases",
        "release_required_inputs",
        "release_settings_owner",
        "release_workflow",
    }
    if release_keys.intersection(explicit_data):
        raise CliError(
            "Release ownership contract is discovered during adoption and "
            "cannot be changed with --data."
        )
    requested_mode = explicit_data.get("project_mode")
    if requested_mode is not None and requested_mode != answers["project_mode"]:
        raise CliError(
            "project_mode cannot change during update because it owns the "
            "release boundary."
        )
    saved_visibility = answers.get("project_visibility")
    update_data["project_visibility"] = repository.visibility
    if repository.repository is not None:
        repository_url = f"https://github.com/{repository.repository}"
        previous_url = answers.get("repository_url")
        previous_channel = answers.get("security_reporting_channel")
        update_data["repository_url"] = repository_url
        if (
            "security_reporting_channel" not in explicit_data
            and isinstance(previous_url, str)
            and previous_channel
            == default_security_reporting_channel(previous_url)
        ):
            update_data["security_reporting_channel"] = (
                default_security_reporting_channel(repository_url)
            )
    if saved_visibility != repository.visibility:
        enabled = repository.visibility == "public" and bool(
            selected_languages(answers)
        )
        if "enable_codeql" in answers and "enable_codeql" not in explicit_data:
            update_data["enable_codeql"] = str(enabled).lower()
    for key, value in update_data.items():
        previous_value = answers.get(key)
        if key == "languages":
            result[key] = parse_languages(str(value))
            update_data[key] = result[key]
        elif isinstance(previous_value, bool):
            normalized = str(value).casefold()
            if normalized in {"1", "true", "yes", "on"}:
                result[key] = True
            elif normalized in {"0", "false", "no", "off"}:
                result[key] = False
            else:
                raise CliError(f"{key} must be a boolean value.")
        elif isinstance(previous_value, int):
            try:
                result[key] = int(str(value))
            except ValueError as error:
                raise CliError(f"{key} must be an integer value.") from error
        else:
            result[key] = value
    return result, update_data


def command_update(args: argparse.Namespace) -> int:  # noqa: C901
    """Check or apply a Copier smart update."""
    target = resolve_repository_target(args.path)
    if (target / PENDING_ADOPTION_FILE).is_file():
        raise CliError(
            "Adoption is pending; complete the manual merge and run "
            "csarc adopt --finalize before update."
        )
    answers_path = config_path(target)
    if not answers_path.is_file():
        raise CliError(f"Missing {CONFIG_FILE}; use csarc adopt first.")
    saved_answers = read_copier_answers(answers_path)
    explicit_data = parse_data(args.data)
    saved_visibility = saved_answers.get("project_visibility")
    repository = repository_context(
        target,
        explicit_data.get("project_visibility"),
        saved_visibility=(
            saved_visibility if isinstance(saved_visibility, str) else None
        ),
    )
    candidate_answers, update_data = update_plan_answers(
        saved_answers, explicit_data, repository
    )
    candidate_answers = resolve_release_answers(target, candidate_answers)
    status, target_revision, previous = update_status(
        target,
        args.to,
        expected_sha=args.expected_sha,
        allow_unreleased=args.allow_unreleased,
        accept_legacy=args.accept_legacy,
        from_release=args.from_release,
    )
    current_capabilities = capability_preflight(
        target / "scripts" / "release_policy.py",
        target,
        emit=False,
    )
    source = status.get("source")
    if not isinstance(source, str):
        raise CliError("Update source must be a string.")
    with tempfile.TemporaryDirectory(prefix="csarc-update-plan-") as temporary:
        stage = Path(temporary) / "project"
        stage.mkdir()
        copier_copy(
            source,
            target_revision,
            stage,
            candidate_answers,
            skip_tasks=True,
        )
        target_uses_current_config = (stage / CONFIG_FILE).is_file()
        answers = read_copier_answers(config_path(stage))
        preflight = capability_preflight(
            stage / "scripts" / "release_policy.py",
            target,
            emit=False,
        )
    hook_configuration = project_verification_configuration(target, answers)
    validated_project_verification_hook(target, hook_configuration)
    hook = project_verification_evidence(
        hook_configuration,
        "not-run",
        "Configuration validated; the hook runs before an update is applied.",
    )
    current_capabilities = dict(current_capabilities)
    target_capabilities = dict(preflight)
    current_capabilities.pop("observed_at", None)
    target_capabilities.pop("observed_at", None)
    answers_changed = answers != saved_answers
    capabilities_changed = target_capabilities != current_capabilities
    update_available = bool(status["update_available"]) or any(
        (answers_changed, capabilities_changed)
    )
    status.update(
        {
            "answers_changed": answers_changed,
            "capabilities_changed": capabilities_changed,
            "status": "outdated" if update_available else "current",
            "update_available": update_available,
            "project_verification_hook": hook,
        }
    )
    target_snapshot: dict[str, object] = {}
    if not args.check:
        require_clean_repository(target)
        head, changes, status_sha256 = target_state(target)
        target_snapshot = {
            "target_changes": list(changes),
            "target_files": target_file_snapshot(target),
            "target_head": head,
            "target_status_sha256": status_sha256,
        }
    plan = ResolvedPlan(
        mode="update",
        target=target,
        revision=target_revision,
        repository=repository,
        answers=answers,
        capabilities=preflight,
        update=status,
    )
    if args.check:
        if args.json:
            print(
                json.dumps(
                    plan.as_dict(), sort_keys=True, separators=(",", ":")
                )
            )
        else:
            print_plan(plan)
        return 1 if status["update_available"] else 0

    with tempfile.TemporaryDirectory(
        prefix="csarc-update-preview-"
    ) as temporary:
        data_file = Path(temporary) / "data.yml"
        data_file.write_text(
            yaml.safe_dump(update_data, sort_keys=True), encoding="utf-8"
        )
        preview = run(
            [
                sys.executable,
                "-m",
                "copier",
                "update",
                "--trust",
                "--defaults",
                "--pretend",
                "--vcs-ref",
                str(status["target_sha"]),
                "--answers-file",
                answers_path.relative_to(target).as_posix(),
                "--data-file",
                str(data_file),
                str(target),
            ],
            capture=True,
            check=False,
        )
    if preview.returncode != 0:
        raise CliError(preview.stderr.strip() or preview.stdout.strip())
    print_plan(plan)
    print("Copier smart-update preview:")
    print(
        preview.stdout.strip()
        or "  (Copier returned no preview details; files may still change.)"
    )
    milestone_plan = milestone_description_plan(target)
    if args.dry_run or not confirm(args):
        return 0

    validate_repository_context(
        target,
        plan.repository,
        explicit_data.get("project_visibility"),
        saved_visibility=(
            saved_visibility if isinstance(saved_visibility, str) else None
        ),
    )
    validate_target_snapshot(target, target_snapshot)
    with tempfile.TemporaryDirectory(prefix="csarc-update-") as temporary:
        temporary_root = Path(temporary).resolve()
        candidate = temporary_root / "candidate"
        clone_target(target, candidate)
        candidate_config_path = config_path(candidate)
        data_file = temporary_root / "data.yml"
        data_file.write_text(
            yaml.safe_dump(update_data, sort_keys=True), encoding="utf-8"
        )
        result = run(
            [
                sys.executable,
                "-m",
                "copier",
                "update",
                "--trust",
                "--defaults",
                "--conflict",
                "inline",
                "--vcs-ref",
                str(status["target_sha"]),
                "--answers-file",
                candidate_config_path.relative_to(candidate).as_posix(),
                "--data-file",
                str(data_file),
                str(candidate),
            ],
            check=False,
        )
        conflicts = find_conflicts(candidate)
        if result.returncode != 0 or conflicts:
            detail = (
                ", ".join(conflicts) if conflicts else "Copier exited non-zero"
            )
            raise CliError(
                f"Update needs manual conflict resolution ({detail}); "
                "the target was not changed. Resolve the listed files in "
                "the target or template, then rerun the update."
            )
        if (
            target_uses_current_config
            and candidate_config_path == candidate / LEGACY_ANSWERS_FILE
        ):
            migrated = candidate / CONFIG_FILE
            migrated.parent.mkdir(parents=True, exist_ok=True)
            candidate_config_path.replace(migrated)
        pin_answer_commit(candidate, str(status["target_sha"]))
        persist_release_answers(candidate, answers)
        verify_project(candidate)
        write_provenance(candidate, target_revision, previous, answers=answers)
        artifacts, delete_paths = candidate_patch_effects(candidate)
        write_candidate_patch(
            candidate,
            target,
            temporary_root / "update.patch",
            artifacts=artifacts,
            target_snapshot=target_snapshot,
            delete_paths=delete_paths,
        )
    settings_plan(target)
    apply_milestone_description_plan(milestone_plan)
    return 0


def add_write_options(parser: argparse.ArgumentParser) -> None:
    """Add shared confirmation and dry-run switches."""
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="plan without writing (the default for adopt)",
    )
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")


def parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    result = argparse.ArgumentParser(prog="csarc")
    subparsers = result.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("init", "create a new repository from an immutable template release"),
        ("adopt", "add the baseline to an existing clean repository"),
    ):
        subparser = subparsers.add_parser(name, help=help_text)
        if name == "adopt":
            subparser.add_argument(
                "path", nargs="?", type=Path, default=Path.cwd()
            )
        else:
            subparser.add_argument("path", type=Path)
        subparser.add_argument("--to", metavar="RELEASE_OR_SHA")
        subparser.add_argument("--source")
        subparser.add_argument("--expected-sha", metavar="FULL_SHA")
        subparser.add_argument("--allow-unreleased", action="store_true")
        subparser.add_argument(
            "--data", action="append", default=[], metavar="KEY=VALUE"
        )
        subparser.add_argument("--json", action="store_true")
        if name == "adopt":
            subparser.add_argument(
                "--apply-plan",
                type=Path,
                metavar="PATH",
                help="apply one unchanged machine plan from dry-run",
            )
            subparser.add_argument(
                "--finalize",
                action="store_true",
                help="finish the exact saved pending adoption",
            )
            subparser.add_argument(
                "--report-dir",
                type=Path,
                metavar="PATH",
                help=(
                    "write or update the adoption Markdown and PDF reports "
                    "outside the repo (dry-run, then applied)"
                ),
            )
        add_write_options(subparser)

    update = subparsers.add_parser(
        "update", help="check or apply a smart update"
    )
    update.add_argument("path", nargs="?", type=Path, default=Path.cwd())
    update.add_argument("--to", metavar="RELEASE_OR_SHA")
    update.add_argument("--expected-sha", metavar="FULL_SHA")
    update.add_argument("--from-release", metavar="RELEASE")
    update.add_argument("--accept-legacy", action="store_true")
    update.add_argument("--allow-unreleased", action="store_true")
    update.add_argument("--check", action="store_true")
    update.add_argument("--json", action="store_true")
    update.add_argument(
        "--data", action="append", default=[], metavar="KEY=VALUE"
    )
    add_write_options(update)

    status = subparsers.add_parser(
        "status",
        help=(
            "the one-prompt entry point: deterministically classify a "
            "repository as create/adopt/update/current/policy-only-update"
        ),
    )
    status.add_argument("path", nargs="?", type=Path, default=Path.cwd())
    status.add_argument("--to", metavar="RELEASE_OR_SHA")
    status.add_argument("--expected-sha", metavar="FULL_SHA")
    status.add_argument("--from-release", metavar="RELEASE")
    status.add_argument("--accept-legacy", action="store_true")
    status.add_argument("--allow-unreleased", action="store_true")
    status.add_argument("--json", action="store_true")
    return result


def main(arguments: list[str] | None = None) -> int:
    """Run the CSARC command-line interface."""
    args = parser().parse_args(arguments)
    try:
        if sys.platform == "win32":
            raise CliError("Native Windows is unsupported; run csarc in WSL2.")
        if args.command in {"init", "adopt"}:
            return command_copy(args, args.command)
        if args.command == "status":
            return command_status(args)
        if args.json and not args.check:
            raise CliError("--json is only valid with update --check.")
        return command_update(args)
    except (CliError, OSError, subprocess.SubprocessError) as error:
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {"error": str(error), "status": "error"},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        else:
            print(f"csarc: {error}", file=sys.stderr)
        return 2


def entrypoint() -> NoReturn:
    """Exit with the command result for the installed console script."""
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
