"""Deterministic repository lifecycle commands backed by Copier."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, NoReturn, Protocol, cast
from urllib.parse import quote

import yaml  # type: ignore[import-untyped]
from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

CANONICAL_SOURCE = (
    "https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git"
)
CANONICAL_REPOSITORY = "Innoguard-Cyber-Arch/csarc-repo-template"
CANONICAL_REPOSITORY_ID = 1_340_899_393
DEFAULT_OWNER = "@Innoguard-Cyber-Arch/arch"
PROVENANCE_FILE = Path(".csarc/provenance.json")
PENDING_ADOPTION_FILE = Path(".csarc/adoption-pending.json")
ADOPTION_REPORT_BASENAME = "csarc-adoption-dry-run"
ADOPTION_PLAN_BASENAME = "csarc-adoption-plan.json"
AGENTS_BLOCK_START = "<!-- BEGIN CSARC MANAGED BLOCK -->"
AGENTS_BLOCK_END = "<!-- END CSARC MANAGED BLOCK -->"
FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
REPOSITORY_VISIBILITIES = {"public", "private", "internal"}
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
            "release_capabilities": self.capabilities,
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
    if requested is not None and FULL_SHA.fullmatch(requested):
        return Revision(requested.lower(), requested.lower(), source)
    source_path = Path(source).expanduser()
    if not source_path.exists():
        raise CliError(
            "--allow-unreleased requires a full commit SHA or local Git source."
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


def detect_language(target: Path) -> str:
    """Infer the narrowest supported language profile."""
    has_python = (target / "pyproject.toml").is_file()
    has_typescript = (target / "package.json").is_file()
    if has_python and has_typescript:
        return "python-typescript"
    if has_python:
        return "python"
    if has_typescript:
        return "typescript"
    return "ci"


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
    for key, value in sorted(data.items()):
        serialized = str(value).lower() if isinstance(value, bool) else value
        command.extend(["--data", f"{key}={serialized}"])
    command.extend([source, str(stage)])
    result = run(command, capture=True, check=False)
    if result.returncode != 0:
        raise CliError(
            result.stderr.strip() or result.stdout.strip() or "Copier failed."
        )
    pin_answer_commit(stage, revision.sha)


def pin_answer_commit(target: Path, commit: str) -> None:
    """Replace Copier's abbreviated revision with the reviewed full SHA."""
    answers = target / ".copier-answers.yml"
    if not answers.is_file():
        raise CliError("Template did not create .copier-answers.yml.")
    lines = answers.read_text(encoding="utf-8").splitlines()
    matches = sum(line.startswith("_commit:") for line in lines)
    if matches != 1:
        raise CliError("Copier answers must contain exactly one _commit value.")
    pinned = [
        f"_commit: {commit}" if line.startswith("_commit:") else line
        for line in lines
    ]
    answers.write_text("\n".join(pinned) + "\n", encoding="utf-8")


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
            if name != ".copier-answers.yml"
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
    destination = checked_destination(target, PENDING_ADOPTION_FILE.as_posix())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = checked_destination(target, PENDING_ADOPTION_FILE.as_posix())
    atomic_replace_text(
        destination,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )


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
    return result


def write_provenance(
    target: Path,
    revision: Revision,
    previous: dict[str, object] | None = None,
    *,
    applied_at: str | None = None,
) -> None:
    """Atomically persist verified release provenance."""
    destination = checked_destination(target, PROVENANCE_FILE.as_posix())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = checked_destination(target, PROVENANCE_FILE.as_posix())
    atomic_replace_text(
        destination,
        json.dumps(
            provenance_data(revision, previous, applied_at=applied_at),
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def read_provenance(target: Path) -> dict[str, object] | None:
    """Read saved provenance without trusting its fields yet."""
    path = checked_destination(target, PROVENANCE_FILE.as_posix())
    if path.is_symlink():
        raise CliError("Saved provenance must not be a symlink.")
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
    except FileNotFoundError, NotADirectoryError:
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


def plan_status(plan: Plan) -> tuple[str, str]:
    """Return the strongest adoption decision and its limitation."""
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
        "container_mode",
        "container_smoke_command",
        "containerfile_path",
        "coverage_mode",
        "coverage_threshold",
        "enable_codeql",
        "enable_governance_drift_check",
        "enable_npm_publishing",
        "enable_precommit",
        "enable_pypi_publishing",
        "enable_release_attestations",
        "enable_template_update_notifications",
        "language",
        "npm_environment",
        "package_name",
        "project_description",
        "project_mode",
        "project_name",
        "project_slug",
        "project_visibility",
        "pypi_environment",
        "python_min_version",
        "python_support_mode",
        "reviewers",
        "use_reusable_workflow",
        "workflow_ref",
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
    status, reason = plan_status(plan)
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
        lines[12:12] = [
            f"- Target HEAD: `{markdown_code(adoption.get('target_head'))}`",
            "- Working tree: "
            + ("clean" if adoption.get("clean") else "dirty; review only"),
            f"- CODEOWNER verification: `{markdown_code(owner_state)}`",
            "- Project verification hook: `"
            f"{markdown_code(adoption.get('project_verification_hook'))}`",
            "- Candidate verification: `"
            f"{markdown_code(adoption.get('verification'))}`",
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
    lines.extend(
        (
            "",
            "## If you approve",
            "",
            "Apply only this machine plan with `csarc adopt --apply-plan`. "
            "The CLI rebuilds and verifies the candidate before changing the "
            "target. It does not apply settings, push, or open a pull request.",
            "",
            "Review this report and the terminal plan before applying it.",
            "",
        )
    )
    return "\n".join(lines)


def pdf_text(value: object, limit: int = 92) -> str:
    """Return printable ASCII text supported by the bundled PDF font."""
    escaped = printable(value).encode("ascii", "backslashreplace").decode()
    return escaped if len(escaped) <= limit else escaped[: limit - 3] + "..."


def draw_adoption_pdf(
    output: BinaryIO,
    target: Path,
    revision: Revision,
    repository: RepositoryContext,
    data: dict[str, object],
    plan: Plan,
    generated_at: str,
) -> None:
    """Draw a concise, selectable-text adoption decision PDF."""
    page_width, page_height = A4
    document = Canvas(output, pagesize=A4, pageCompression=1)
    status, reason = plan_status(plan)
    status_color = {
        "Ready to adopt": colors.HexColor("#DDEFE2"),
        "Review required": colors.HexColor("#F7E9B5"),
        "Unable to determine": colors.HexColor("#F4D7D5"),
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
        ("Profile", data.get("language", "unknown")),
    )
    y = page_height - 178
    for label, value in metadata:
        document.setFont("Helvetica-Bold", 8)
        document.drawString(48, y, label)
        document.setFont("Helvetica", 8)
        document.drawString(110, y, pdf_text(value, 105))
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
    document.drawString(62, 132, "If approved")
    document.setFont("Helvetica", 8)
    document.drawString(
        62,
        116,
        "Adoption adds planned files, runs ./scripts/verify, and previews "
        "settings.",
    )
    document.drawString(
        62, 101, "It does not apply settings, push, or open a pull request."
    )
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


def directory_fd_matches_path(directory_fd: int, path: Path) -> bool:
    """Return whether a path still names the directory held by an open fd."""
    try:
        opened = os.fstat(directory_fd)
        current = os.stat(path, follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISDIR(current.st_mode)
        and opened.st_dev == current.st_dev
        and opened.st_ino == current.st_ino
    )


def atomic_replace_text(destination: Path, content: str) -> None:
    """Replace text through a pinned, non-symlink parent directory."""
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        parent_fd = os.open(destination.parent, directory_flags)
    except OSError as error:
        raise CliError(
            f"Cannot safely open destination directory: {destination.parent}"
        ) from error
    temporary_name = f".{destination.name}.{secrets.token_hex(16)}.tmp"
    backup_name = f".{destination.name}.{secrets.token_hex(16)}.bak"
    backup_created = False
    try:
        if not directory_fd_matches_path(parent_fd, destination.parent):
            raise CliError("Destination directory changed while writing.")
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        temporary_stat = os.fstat(temporary_fd)
        with os.fdopen(temporary_fd, mode="w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
        if not directory_fd_matches_path(parent_fd, destination.parent):
            raise CliError("Destination directory changed while writing.")
        try:
            existing_fd = os.open(
                destination.name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            pass
        else:
            with os.fdopen(existing_fd, mode="rb") as existing:
                existing_mode = os.fstat(existing.fileno()).st_mode
                if not stat.S_ISREG(existing_mode):
                    raise CliError(
                        f"Destination is not a regular file: {destination}"
                    )
                backup_fd = os.open(
                    backup_name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    stat.S_IMODE(existing_mode),
                    dir_fd=parent_fd,
                )
                with os.fdopen(backup_fd, mode="wb") as backup:
                    os.fchmod(backup.fileno(), stat.S_IMODE(existing_mode))
                    shutil.copyfileobj(existing, backup)
                    backup.flush()
            backup_created = True
        os.replace(
            temporary_name,
            destination.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        if not directory_fd_matches_path(parent_fd, destination.parent):
            current = os.stat(
                destination.name, dir_fd=parent_fd, follow_symlinks=False
            )
            if (
                current.st_dev == temporary_stat.st_dev
                and current.st_ino == temporary_stat.st_ino
            ):
                if backup_created:
                    os.replace(
                        backup_name,
                        destination.name,
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                    )
                    backup_created = False
                else:
                    os.unlink(destination.name, dir_fd=parent_fd)
            raise CliError("Destination directory changed while writing.")
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name, dir_fd=parent_fd)
        with suppress(FileNotFoundError):
            os.unlink(backup_name, dir_fd=parent_fd)
        os.close(parent_fd)


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
    raw_states = payload.get("capabilities")
    states = raw_states if isinstance(raw_states, dict) else {}
    summary = ", ".join(
        f"{name}={value.get('state', 'unknown')}"
        for name, value in states.items()
        if isinstance(value, dict)
    )
    print(f"GitHub release preflight: {summary or 'unknown'}")
    print("Runtime workflows recheck capabilities before every release.")
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


def require_unreleased_plan_opt_in(
    verification: object, allow_unreleased: bool
) -> None:
    """Require a fresh explicit trust bypass when applying an unsafe plan."""
    if verification not in {"unverified", "development-unreleased"}:
        return
    if not allow_unreleased:
        raise CliError(
            "Applying an unreleased template plan requires "
            "--allow-unreleased again."
        )
    print(
        "WARNING: --allow-unreleased bypasses release identity, "
        "immutability, attestation, and signature verification.",
        file=sys.stderr,
    )


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
        ".copier-answers.yml"
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
            ".copier-answers.yml",
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
    difference = run(
        ["git", "-C", str(target), "diff", "--binary", "HEAD"],
        capture=True,
    )
    patch.write_text(difference.stdout, encoding="utf-8")
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
) -> tuple[Plan, dict[str, str], str]:
    """Build and verify the exact adoption result outside the target repo."""
    clone_target(target, candidate)
    copy_candidate_files(stage, candidate, (*planned.add, *planned.merge))
    if planned.manual or planned.unknown:
        write_pending_adoption(
            candidate,
            pending_adoption_data(
                candidate,
                revision,
                repository,
                candidate / ".copier-answers.yml",
                pending_managed_paths(stage, planned),
                (*planned.manual, *planned.unknown),
            ),
        )
        verification = "deferred-manual-merge"
    else:
        create_adoption_lockfiles(candidate, answers)
        write_provenance(candidate, revision, applied_at=generated_at)
        try:
            verify_project(candidate)
        except CliError as error:
            verification = f"failed: {error}"
        else:
            verification = "passed"
    effects, artifacts = candidate_effects(candidate, target, planned)
    return effects, artifacts, verification


def write_candidate_patch(
    candidate: Path,
    target: Path,
    patch: Path,
    *,
    artifacts: Mapping[str, object],
    target_snapshot: Mapping[str, object],
    delete_paths: tuple[str, ...] = (),
) -> None:
    """Apply an already verified candidate as one checked byte-level patch."""
    before = patch.parent / "before"
    after = patch.parent / "after"
    before.mkdir()
    after.mkdir()
    candidate_files = project_files(candidate)
    target_files = project_files(target)
    expected_artifacts = {
        name: value
        for name, value in artifacts.items()
        if isinstance(name, str) and isinstance(value, str)
    }
    if len(expected_artifacts) != len(artifacts):
        raise CliError("Adoption plan contains invalid artifact fingerprints.")
    actual_artifacts = {
        name: file_fingerprint(candidate_files[name])
        for name in sorted(git_changed_paths(candidate))
        if name in candidate_files
    }
    if actual_artifacts != expected_artifacts:
        raise CliError(
            "Candidate effects differ from the verified plan; create a new "
            "plan."
        )
    changed = tuple(sorted(expected_artifacts))
    for relative_name in (*changed, *delete_paths):
        checked_destination(target, relative_name)
    validate_target_snapshot(target, target_snapshot)
    existing = tuple(name for name in changed if name in target_files)
    copy_candidate_files(target, before, existing)
    copy_candidate_files(candidate, after, changed)
    copy_candidate_files(
        target,
        before,
        tuple(name for name in delete_paths if name in target_files),
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


def create_adoption_lockfiles(target: Path, answers: dict[str, object]) -> None:
    """Create language lockfiles after an adoption is ready to finalize."""
    language = answers.get("language")
    if language in {"python", "python-typescript"}:
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
    if language in {"typescript", "python-typescript"}:
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


def verify_project(target: Path) -> None:
    """Run the generated project's canonical verification command."""
    verify = target / "scripts" / "verify"
    if not verify.is_file():
        raise CliError("Generated project is missing ./scripts/verify.")
    result = run([str(verify)], cwd=target, check=False)
    if result.returncode != 0:
        raise CliError(
            "Project verification failed; generated differences were preserved "
            "for review."
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
    """Run the read-only release preflight without making it a prerequisite."""
    repository = target_repository(target)
    if repository is None or not script.is_file():
        payload: dict[str, object] = {
            "mode": "verification-only",
            "reason": "GitHub origin or capability script is unavailable",
            "capabilities": {
                name: {"state": "unknown", "reason": "runtime check required"}
                for name in (
                    "actions_pull_requests",
                    "contents",
                    "release",
                    "dispatch",
                )
            },
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
            parsed
            if result.returncode == 0 and isinstance(parsed, dict)
            else {
                "mode": "verification-only",
                "reason": "GitHub capability preflight was unavailable",
                "capabilities": {},
            }
        )
    if emit:
        print_capabilities(payload)
    return payload


def base_data(
    target: Path, mode: str, values: dict[str, str]
) -> dict[str, str]:
    """Build stable defaults while allowing explicit Copier answers."""
    slug = slugify(target.name)
    data = {
        "project_mode": "existing" if mode == "adopt" else "new",
        "project_name": target.name.replace("-", " ").replace("_", " ").title(),
        "project_slug": slug,
        "package_name": slug.replace("-", "_").replace(".", "_"),
        "language": detect_language(target) if mode == "adopt" else "python",
        "code_owner": DEFAULT_OWNER,
    }
    if mode == "adopt":
        data["coverage_mode"] = "diff"
    data.update(values)
    if "package_name" not in values:
        data["package_name"] = (
            str(data["project_slug"]).replace("-", "_").replace(".", "_")
        )
    return data


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
    if (target / ".copier-answers.yml").exists():
        raise CliError(
            "Repository already has Copier answers; use csarc update."
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
    if args.report_dir is not None and not args.dry_run:
        raise CliError("--report-dir requires adopt --finalize --dry-run.")
    if args.json and not args.dry_run:
        raise CliError("--json requires --dry-run for adopt --finalize.")
    if args.json and args.report_dir is not None:
        raise CliError("--report-dir cannot be combined with --json.")
    if not args.dry_run and args.apply_plan is None:
        raise CliError(
            "Run adopt --finalize --dry-run first, then apply its machine "
            "plan with --finalize --apply-plan."
        )
    if any((args.source, args.to, args.expected_sha)):
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

    answers_path = checked_destination(target, ".copier-answers.yml")
    if answers_path.is_symlink() or not answers_path.is_file():
        raise CliError(
            "Pending adoption is missing .copier-answers.yml; restore the "
            "managed file, then rerun csarc adopt --finalize."
        )
    actual_answers_hash = hashlib.sha256(answers_path.read_bytes()).hexdigest()
    if actual_answers_hash != pending["answers_sha256"]:
        raise CliError(
            "Copier answers changed after adoption started; restore "
            ".copier-answers.yml or restart adoption from a clean commit."
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
    if args.apply_plan is not None:
        require_unreleased_plan_opt_in(verification, args.allow_unreleased)
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
        write_provenance(candidate, revision, applied_at=generated_at)
        checked_destination(
            candidate, PENDING_ADOPTION_FILE.as_posix()
        ).unlink()
        try:
            verify_project(candidate)
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
            "project_verification_hook": (
                "configured"
                if os.access(target / "scripts" / "verify-product", os.X_OK)
                else "not-configured"
            ),
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
    merged = apply_adoption_policies(stage, target)
    planned = compare_stage(stage, target, adopt=True, merged_paths=merged)
    head, changes, status_sha256 = target_state(target)
    target_files = target_file_snapshot(target)
    artifacts: dict[str, str] = {}
    if changes:
        files = predicted_adoption_effects(target, planned)
        verification = "not-run-dirty"
    else:
        files, artifacts, verification = prepare_adoption_candidate(
            stage,
            target,
            revision,
            repository,
            answers,
            planned,
            generated_at,
            candidate,
        )
    owner = code_owner_verification(repository, answers.get("code_owner"))
    adoption: dict[str, object] = {
        "applicable": not changes
        and verification in {"passed", "deferred-manual-merge"}
        and owner["state"] != "blocked",
        "artifacts": artifacts,
        "clean": not changes,
        "code_owner": owner,
        "generated_at": generated_at,
        "phase": (
            "pending" if planned.manual or planned.unknown else "complete"
        ),
        "project_verification_hook": (
            "configured"
            if os.access(target / "scripts" / "verify-product", os.X_OK)
            else "not-configured"
        ),
        "target_changes": list(changes),
        "target_files": target_files,
        "target_head": head,
        "target_status_sha256": status_sha256,
        "verification": verification,
    }
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
    if args.dry_run or args.report_dir is not None or args.json:
        raise CliError(
            "--apply-plan cannot be combined with --dry-run, --report-dir, "
            "or --json."
        )
    if any((args.source, args.to, args.expected_sha)):
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
    require_unreleased_plan_opt_in(verification, args.allow_unreleased)
    require_clean_repository(target)
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
        answers.update(read_copier_answers(stage / ".copier-answers.yml"))
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
    write_provenance(target, revision)
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
    answers = target / ".copier-answers.yml"
    if not answers.is_file():
        raise CliError("Missing .copier-answers.yml; use csarc adopt first.")
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


def update_plan_answers(  # noqa: C901
    answers: dict[str, object],
    explicit_data: dict[str, str],
    repository: RepositoryContext,
) -> tuple[dict[str, object], dict[str, str]]:
    """Resolve update answers and Copier overrides from repository facts."""
    result = dict(answers)
    update_data = dict(explicit_data)
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
        enabled = (
            repository.visibility == "public"
            and answers.get("language") != "ci"
        )
        for key in ("enable_codeql", "enable_release_attestations"):
            if key in answers and key not in explicit_data:
                update_data[key] = str(enabled).lower()
    for key, value in update_data.items():
        previous_value = answers.get(key)
        if isinstance(previous_value, bool):
            normalized = value.casefold()
            if normalized in {"1", "true", "yes", "on"}:
                result[key] = True
            elif normalized in {"0", "false", "no", "off"}:
                result[key] = False
            else:
                raise CliError(f"{key} must be a boolean value.")
        elif isinstance(previous_value, int):
            try:
                result[key] = int(value)
            except ValueError as error:
                raise CliError(f"{key} must be an integer value.") from error
        else:
            result[key] = value
    return result, update_data


def command_update(args: argparse.Namespace) -> int:
    """Check or apply a Copier smart update."""
    target = resolve_repository_target(args.path)
    if (target / PENDING_ADOPTION_FILE).is_file():
        raise CliError(
            "Adoption is pending; complete the manual merge and run "
            "csarc adopt --finalize before update."
        )
    answers_path = target / ".copier-answers.yml"
    if not answers_path.is_file():
        raise CliError("Missing .copier-answers.yml; use csarc adopt first.")
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
        answers = read_copier_answers(stage / ".copier-answers.yml")
        preflight = capability_preflight(
            stage / "scripts" / "release_policy.py",
            target,
            emit=False,
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

    copier_data = [
        part
        for key, value in sorted(update_data.items())
        for part in ("--data", f"{key}={value}")
    ]
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
            *copier_data,
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
            *copier_data,
            str(target),
        ],
        check=False,
    )
    conflicts = find_conflicts(target)
    if result.returncode != 0 or conflicts:
        detail = ", ".join(conflicts) if conflicts else "Copier exited non-zero"
        raise CliError(
            f"Update needs manual conflict resolution ({detail}); "
            "differences were preserved."
        )
    pin_answer_commit(target, str(status["target_sha"]))
    verify_project(target)
    write_provenance(target, target_revision, previous)
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
                help="write dry-run Markdown and PDF reports outside the repo",
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
    return result


def main(arguments: list[str] | None = None) -> int:
    """Run the CSARC command-line interface."""
    args = parser().parse_args(arguments)
    try:
        if sys.platform == "win32":
            raise CliError("Native Windows is unsupported; run csarc in WSL2.")
        if args.command in {"init", "adopt"}:
            return command_copy(args, args.command)
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
