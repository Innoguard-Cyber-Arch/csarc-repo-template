"""Deterministic repository lifecycle commands backed by Copier."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, NoReturn, Protocol
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
ADOPTION_REPORT_BASENAME = "csarc-adoption-dry-run"
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
                "manual_merge": list(self.files.manual),
                "overwrite": list(self.files.overwrite),
                "preserve": list(self.files.preserve),
                "unknown": list(self.files.unknown),
            }
        if self.update is not None:
            result.update(self.update)
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
    ignored = {".git", ".cache", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
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
        if "node_modules" in relative.parts or "dist" in relative.parts:
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


def provenance_data(
    revision: Revision, previous: dict[str, object] | None = None
) -> dict[str, object]:
    """Build the auditable state recorded after a successful operation."""
    result: dict[str, object] = {
        "applied_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
) -> None:
    """Atomically persist verified release provenance."""
    destination = target / PROVENANCE_FILE
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            provenance_data(revision, previous), indent=2, sort_keys=True
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


def compare_stage(stage: Path, target: Path, *, adopt: bool) -> Plan:
    """Compare staged output with the destination without changing it."""
    staged = project_files(stage)
    existing = project_files(target)
    add: list[str] = []
    preserve: list[str] = []
    manual: list[str] = []
    unknown: list[str] = []
    for relative_name, staged_path in staged.items():
        existing_path = existing.get(relative_name)
        if existing_path is None:
            add.append(relative_name)
            continue
        staged_content = staged_path.read_bytes()
        existing_content = existing_path.read_bytes()
        if staged_content == existing_content:
            preserve.append(relative_name)
        elif adopt:
            destination = (
                manual
                if is_text(staged_content) and is_text(existing_content)
                else unknown
            )
            destination.append(relative_name)
        else:
            manual.append(relative_name)
    preserve.extend(name for name in existing if name not in staged)
    return Plan(
        tuple(sorted(add)),
        (),
        tuple(sorted(set(preserve))),
        tuple(sorted(manual)),
        tuple(sorted(unknown)),
    )


def plan_status(plan: Plan) -> tuple[str, str]:
    """Return the strongest adoption decision and its limitation."""
    if plan.unknown:
        return (
            "Unable to determine",
            "Non-text path collisions need human inspection.",
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
    """Return only the non-sensitive settings needed for adoption review."""
    allowed = ("project_mode", "language", "coverage_mode")
    return ", ".join(
        f"`{key}={markdown_code(data[key])}`" for key in allowed if key in data
    )


def adoption_report_markdown(
    target: Path,
    revision: Revision,
    data: dict[str, object],
    plan: Plan,
    generated_at: str,
) -> str:
    """Render the complete, shareable adoption decision report."""
    status, reason = plan_status(plan)
    counts = (
        ("Add", len(plan.add)),
        ("Overwrite", len(plan.overwrite)),
        ("Preserve", len(plan.preserve)),
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
    attention = (
        (path, "template and repository contain different UTF-8 text")
        for path in plan.manual
    )
    unknown = (
        (
            path,
            "template and repository contain different non-text content",
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
    lines.extend(
        (
            "",
            "## If you approve",
            "",
            "A real adoption adds only planned new files, runs "
            "`./scripts/verify`, and previews repository settings with `plan`. "
            "It does not apply settings, push, or open a pull request.",
            "",
            "Review this report and the terminal plan before running the "
            "command again without `--dry-run`.",
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
        (path, "different non-text content - inspect") for path in plan.unknown
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


def write_adoption_reports(
    target: Path,
    revision: Revision,
    data: dict[str, object],
    plan: Plan,
    requested_directory: Path | None,
) -> tuple[Path, Path]:
    """Write Markdown first, then a PDF, without replacing prior reports."""
    directory = adoption_report_directory(target, requested_directory)
    markdown_path = directory / f"{ADOPTION_REPORT_BASENAME}.md"
    pdf_path = directory / f"{ADOPTION_REPORT_BASENAME}.pdf"
    collisions = [path for path in (markdown_path, pdf_path) if path.exists()]
    if collisions:
        names = ", ".join(path.name for path in collisions)
        raise CliError(f"Adoption report already exists ({names}).")
    directory.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    with markdown_path.open("x", encoding="utf-8") as markdown:
        markdown.write(
            adoption_report_markdown(target, revision, data, plan, generated_at)
        )
    created_pdf = False
    try:
        with pdf_path.open("xb") as pdf:
            created_pdf = True
            draw_adoption_pdf(pdf, target, revision, data, plan, generated_at)
    except Exception as error:
        if created_pdf:
            pdf_path.unlink(missing_ok=True)
        raise CliError(
            "PDF report generation failed; Markdown remains at "
            f"{markdown_path}."
        ) from error
    print(f"Markdown report: {markdown_path}")
    print(f"PDF report: {pdf_path}")
    return markdown_path, pdf_path


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
    print_capabilities(plan.capabilities)
    if plan.files is not None:
        print_group("Add", plan.files.add)
        print_group("Overwrite", plan.files.overwrite)
        print_group("Preserve", plan.files.preserve)
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


def copy_additions(stage: Path, target: Path, paths: tuple[str, ...]) -> None:
    """Copy only files that the plan classified as additions."""
    target.mkdir(parents=True, exist_ok=True)
    for relative_name in paths:
        source = stage / relative_name
        destination = target / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination, follow_symlinks=False)


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
    return data


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


def validate_copy_target(target: Path, mode: str) -> None:
    """Validate an init or adopt destination before release resolution."""
    if mode == "init" and target.exists() and any(target.iterdir()):
        raise CliError("init target must not exist or must be empty.")
    if mode != "adopt":
        return
    if not target.is_dir():
        raise CliError("adopt target must be an existing directory.")
    if (target / ".copier-answers.yml").exists():
        raise CliError(
            "Repository already has Copier answers; use csarc update."
        )
    require_clean_repository(target)


def command_copy(args: argparse.Namespace, mode: str) -> int:
    """Plan and apply init or adopt."""
    target = args.path.expanduser().resolve()
    validate_copy_target(target, mode)
    if mode == "adopt" and args.report_dir is not None and not args.dry_run:
        raise CliError("--report-dir requires adopt --dry-run.")
    if args.json and not args.dry_run:
        raise CliError("--json requires --dry-run for init or adopt.")
    if args.json and mode == "adopt" and args.report_dir is not None:
        raise CliError("--report-dir cannot be combined with --json.")

    revision = resolve_revision(
        args.source,
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
    with tempfile.TemporaryDirectory(prefix="csarc-plan-") as temporary:
        stage = Path(temporary) / "project"
        stage.mkdir()
        copier_copy(args.source, revision, stage, data)
        answers = read_copier_answers(stage / ".copier-answers.yml")
        file_plan = compare_stage(stage, target, adopt=mode == "adopt")
        capabilities = capability_preflight(
            stage / "scripts" / "release_policy.py", target, emit=False
        )
        plan = ResolvedPlan(
            mode=mode,
            target=target,
            revision=revision,
            repository=repository,
            answers=answers,
            capabilities=capabilities,
            files=file_plan,
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
            write_adoption_reports(
                target, revision, answers, file_plan, args.report_dir
            )
        milestone_plan = (
            milestone_description_plan(target, emit=not args.json)
            if mode == "adopt"
            else None
        )
        if args.dry_run or not confirm(args):
            return 0
        if mode == "init":
            if target.exists():
                target.rmdir()
            shutil.copytree(stage, target, symlinks=True)
        else:
            copy_additions(stage, target, file_plan.add)

    verify_project(target)
    write_provenance(target, revision)
    settings_plan(target)
    apply_milestone_description_plan(milestone_plan)
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


def update_plan_answers(
    answers: dict[str, object],
    explicit_data: dict[str, str],
    repository: RepositoryContext,
) -> tuple[dict[str, object], dict[str, str]]:
    """Resolve update answers and Copier overrides from repository facts."""
    result = dict(answers)
    update_data = dict(explicit_data)
    saved_visibility = answers.get("project_visibility")
    update_data["project_visibility"] = repository.visibility
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
    target = args.path.expanduser().resolve()
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

    require_clean_repository(target)
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
    parser.add_argument("--dry-run", action="store_true")
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
        subparser.add_argument("path", type=Path)
        subparser.add_argument("--to", metavar="RELEASE_OR_SHA")
        subparser.add_argument("--source", default=CANONICAL_SOURCE)
        subparser.add_argument("--expected-sha", metavar="FULL_SHA")
        subparser.add_argument("--allow-unreleased", action="store_true")
        subparser.add_argument(
            "--data", action="append", default=[], metavar="KEY=VALUE"
        )
        subparser.add_argument("--json", action="store_true")
        if name == "adopt":
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
