"""Deterministic repository lifecycle commands backed by Copier."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn, Protocol
from urllib.parse import quote

CANONICAL_SOURCE = (
    "https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git"
)
CANONICAL_REPOSITORY = "Innoguard-Cyber-Arch/csarc-repo-template"
CANONICAL_REPOSITORY_ID = 1_340_899_393
DEFAULT_OWNER = "@Innoguard-Cyber-Arch/repository-maintainers"
PROVENANCE_FILE = Path(".csarc/provenance.json")
FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


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


def needs_manual_merge(relative: Path) -> bool:
    """Return whether a preserved file also needs template settings merged."""
    return relative.as_posix() in {"pyproject.toml", "package.json"}


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
    data: dict[str, str],
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
    for key, value in sorted(data.items()):
        command.extend(["--data", f"{key}={value}"])
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
    for relative_name, staged_path in staged.items():
        existing_path = existing.get(relative_name)
        if existing_path is None:
            add.append(relative_name)
            continue
        relative = Path(relative_name)
        if staged_path.read_bytes() == existing_path.read_bytes():
            preserve.append(relative_name)
        elif adopt and needs_manual_merge(relative):
            manual.append(relative_name)
        elif adopt:
            preserve.append(relative_name)
        else:
            manual.append(relative_name)
    preserve.extend(name for name in existing if name not in staged)
    return Plan(
        tuple(sorted(add)),
        (),
        tuple(sorted(set(preserve))),
        tuple(sorted(manual)),
    )


def print_group(title: str, paths: tuple[str, ...]) -> None:
    """Print one stable plan group."""
    print(f"{title} ({len(paths)}):")
    if paths:
        for path in paths:
            print(f"  {path}")
    else:
        print("  (none)")


def print_plan(
    mode: str,
    target: Path,
    revision: Revision,
    data: dict[str, str],
    plan: Plan,
) -> None:
    """Print the immutable revision, settings, risks, and file effects."""
    print(f"Mode: {mode}")
    print(f"Target: {target}")
    print(f"Template version: {revision.label}")
    print(f"Template commit: {revision.sha}")
    print(f"Pinned guide: {revision.guide_url}")
    print(
        "Release verification: "
        + ("verified immutable release" if revision.verified else "UNVERIFIED")
    )
    print("Settings:")
    for key, value in sorted(data.items()):
        print(f"  {key}={value}")
    print_group("Add", plan.add)
    print_group("Overwrite", plan.overwrite)
    print_group("Preserve", plan.preserve)
    print_group("Manual merge", plan.manual)
    risk = "manual merge required" if plan.manual else "no known file conflicts"
    print(f"Conflict risk: {risk}")


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
    result = run(
        ["git", "-C", str(target), "remote", "get-url", "origin"],
        capture=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return github_repository(result.stdout.strip())


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
        raw_states = payload.get("capabilities")
        states = raw_states if isinstance(raw_states, dict) else {}
        summary = ", ".join(
            f"{name}={value.get('state', 'unknown')}"
            for name, value in states.items()
            if isinstance(value, dict)
        )
        print(f"GitHub release preflight: {summary or 'unknown'}")
        print("Runtime workflows recheck capabilities before every release.")
    return payload


def base_data(target: Path, mode: str, values: list[str]) -> dict[str, str]:
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
    data.update(parse_data(values))
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

    revision = resolve_revision(
        args.source,
        args.to,
        expected_sha=args.expected_sha,
        allow_unreleased=args.allow_unreleased,
    )
    if not revision.verified:
        print(
            "WARNING: --allow-unreleased bypasses release identity, "
            "immutability, attestation, and signature verification."
        )
    data = base_data(target, mode, args.data)
    with tempfile.TemporaryDirectory(prefix="csarc-plan-") as temporary:
        stage = Path(temporary) / "project"
        stage.mkdir()
        copier_copy(args.source, revision, stage, data)
        plan = compare_stage(stage, target, adopt=mode == "adopt")
        print_plan(mode, target, revision, data, plan)
        capability_preflight(stage / "scripts" / "release_policy.py", target)
        if args.dry_run or not confirm(args):
            return 0
        if mode == "init":
            if target.exists():
                target.rmdir()
            shutil.copytree(stage, target, symlinks=True)
        else:
            copy_additions(stage, target, plan.add)

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


def command_update(args: argparse.Namespace) -> int:
    """Check or apply a Copier smart update."""
    target = args.path.expanduser().resolve()
    status, target_revision, previous = update_status(
        target,
        args.to,
        expected_sha=args.expected_sha,
        allow_unreleased=args.allow_unreleased,
        accept_legacy=args.accept_legacy,
        from_release=args.from_release,
    )
    preflight = capability_preflight(
        target / "scripts" / "release_policy.py",
        target,
        emit=not args.json,
    )
    if args.json:
        status["release_capabilities"] = preflight
    if args.check:
        if args.json:
            print(json.dumps(status, sort_keys=True, separators=(",", ":")))
        else:
            print(
                f"Template {status['status']}: {status['current_sha']} -> "
                f"{status['target_sha']} ({status['target_version']})"
            )
        return 1 if status["update_available"] else 0

    require_clean_repository(target)
    print("Mode: update")
    print(f"Target: {target}")
    print(
        f"Template: {status['current_version']} / {status['current_sha']} -> "
        f"{status['target_version']} / {status['target_sha']}"
    )
    print(f"Release verification: {status['target_verification']}")
    print("Settings: existing .copier-answers.yml")
    print(
        "Conflict risk: Copier smart diff; conflicts fail closed and remain "
        "in place."
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
            str(target),
        ],
        capture=True,
        check=False,
    )
    if preview.returncode != 0:
        raise CliError(preview.stderr.strip() or preview.stdout.strip())
    print("Copier smart-update preview:")
    print(preview.stdout.strip() or "  (no file changes)")
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
