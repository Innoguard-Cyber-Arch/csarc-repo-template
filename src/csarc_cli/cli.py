"""Deterministic repository lifecycle commands backed by Copier."""

from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import itertools
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import (
    Callable,
    Collection,
    Generator,
    Mapping,
    Sequence,
)
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, replace
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal, NoReturn, Protocol, cast, overload
from urllib.parse import quote

import yaml  # type: ignore[import-untyped]

from csarc_cli import (
    action_pin_preflight,
    file_transition,
    final_plan,
    governance_migration,
    lifecycle_report,
    merge_trace,
    project_roadmap,
    release_phase,
    repository_facts,
    risk_tools,
    settings_schema,
    setup_plan,
    update_plan,
)
from csarc_cli.lifecycle_report import (
    LIFECYCLE_REPORT_FORMAT_VERSION,
    redact,
)

CANONICAL_SOURCE = (
    "https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git"
)
CANONICAL_REPOSITORY = "Innoguard-Cyber-Arch/csarc-repo-template"
CANONICAL_REPOSITORY_ID = 1_340_899_393
MINIMUM_GH_VERSION = "2.93.0"
GH_INSTALL_URL = "https://github.com/cli/cli#installation"
# CODEOWNERS is opt-in: create and adopt never assume an organization or team
# (#1061). LEGACY_DEFAULT_OWNER is the value earlier releases applied when no
# owner was given; it is only used to preserve what an existing repository
# already rendered when its saved answers predate the code_owner question.
DEFAULT_OWNER = ""
LEGACY_DEFAULT_OWNER = "@Innoguard-Cyber-Arch/arch"
CONFIG_FILE = Path(".csarc/config.yml")
LEGACY_ANSWERS_FILE = Path(".copier-answers.yml")
# Pre-dates CONFIG_FILE: a derived projection of a subset of Copier's own
# answers (branch strategy, language modules, a since-removed container
# feature). Every field it held is already part of the unified answers file,
# so a migration only needs to retire it, never read it.
LEGACY_PROFILE_FILE = Path(".csarc/profile.json")
PROVENANCE_FILE = Path(".csarc/provenance.json")
PENDING_ADOPTION_FILE = Path(".csarc/adoption-pending.json")
# SPEC-008 report files. Each name below carries ``.json`` (the only
# source) and ``.md`` (rendered from that JSON) beside the machine plan.
ADOPTION_REPORT_BASENAME = "csarc-adoption-report"
ADOPTION_PLAN_BASENAME = "csarc-adoption-plan.json"
UPDATE_REPORT_BASENAME = "csarc-update-report"
# The default update report folder as docs/install.md names it: commands run
# from inside the target (``.``), and ``lifecycle_report_directory`` writes
# the folder next to it as ``<repo>-csarc-update-report`` (Issue #1153).
UPDATE_FINAL_PLAN_HINT = (
    f"../<repo>-{UPDATE_REPORT_BASENAME}/{final_plan.FINAL_PLAN_BASENAME}"
)
UPDATE_PLAN_BASENAME = "csarc-update-plan.json"
# The 1.1.0 Markdown-only report name, removed after the new set is written.
LEGACY_ADOPTION_REPORT_NAME = "csarc-adoption-dry-run.md"
AGENTS_BLOCK_START = "<!-- BEGIN CSARC MANAGED BLOCK -->"
AGENTS_BLOCK_END = "<!-- END CSARC MANAGED BLOCK -->"
FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
GIT_OBJECT_ID = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
CODE_OWNER_USER = re.compile(
    r"^@(?![A-Za-z0-9-]*--)([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}"
    r"[A-Za-z0-9])?)$"
)
CODE_OWNER_TEAM = re.compile(r"^@([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$")
GITHUB_REPOSITORY_URL = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
)
REPOSITORY_VISIBILITIES = {"public", "private", "internal"}
RELEASE_OWNERSHIPS = {"csarc-owned", "product-owned", "verification-only"}
# SPEC-009 (Issue #1071): every resolved schema 2 intent plus the seeds,
# live facts, derived context, and immutable project_mode a render consumed.
# Retired keys are reported through governance_migration.RETIRED_SETTINGS.
REPORT_SETTING_KEYS = frozenset(
    {
        *settings_schema.INTENT_SETTINGS,
        *settings_schema.DECISION_SETTINGS,
        *settings_schema.CONTEXT_KEYS,
    }
)
WORK_ITEM_DEFAULTS = (
    {
        "kind": "Bug",
        "issue_type": "Bug",
        "issue_label": None,
        "pr_label": "bug",
    },
    {
        "kind": "Feature",
        "issue_type": "Feature",
        "issue_label": None,
        "pr_label": "enhancement",
    },
    {
        "kind": "Task",
        "issue_type": "Task",
        "issue_label": None,
        "pr_label": "enhancement",
    },
    {
        "kind": "Documentation",
        "issue_type": "Task",
        "issue_label": "documentation",
        "pr_label": "documentation",
    },
)
WORK_ITEM_LABEL_ALIASES = {
    "bug": ("Bug", "bug"),
    "bugs": ("Bug", "bug"),
    "bugfix": ("Bug", "bug"),
    "defect": ("Bug", "bug"),
    "defects": ("Bug", "bug"),
    "enhancement": (None, "enhancement"),
    "enhancements": (None, "enhancement"),
    "feature": ("Feature", "enhancement"),
    "features": ("Feature", "enhancement"),
    "task": ("Task", "enhancement"),
    "tasks": ("Task", "enhancement"),
    "doc": ("Task", "documentation"),
    "docs": ("Task", "documentation"),
    "documentation": ("Task", "documentation"),
}
WORK_ITEM_ORTHOGONAL_LABELS = {
    "duplicate",
    "hotfix",
    "needs-manual-review",
    "promotion",
    "release-recovery",
}
RELEASE_WRITER_MARKERS = (
    "gh release create",
    "gh release edit",
    "gh release upload",
    "scripts/publish-release publish",
    "googleapis/release-please-action@",
    "ncipollo/release-action@",
    "softprops/action-gh-release@",
)
INSTALL_STATE_CREATE = "create"
INSTALL_STATE_ADOPT = "adopt"
INSTALL_STATE_ADOPTION_PENDING = "adoption-pending"
INSTALL_STATE_MIGRATE = "migrate"
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
    INSTALL_STATE_ADOPTION_PENDING: "csarc adopt <path> --finalize",
    INSTALL_STATE_UPDATE: (
        "csarc update . --to <release> --expected-sha <full SHA> "
        "--check --json to preview; then the same command with "
        "--finalize-plan --decision PATH=keep-current|take-new|custom:FILE "
        "(one per listed conflict) instead of --check --json; then csarc "
        f"update . --apply-plan {UPDATE_FINAL_PLAN_HINT} --yes"
    ),
    INSTALL_STATE_CURRENT: "no action needed",
    INSTALL_STATE_POLICY_ONLY: (
        ".csarc/scripts/apply-repository-settings.sh plan to preview, then "
        ".csarc/scripts/apply-repository-settings.sh apply"
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


class ReleaseRecoveryError(CliError):
    """A release identity is unusable but safe reinstall remains possible."""


class ReleaseNotFoundError(ReleaseRecoveryError):
    """The canonical repository confirmed a named release tag is gone.

    Raised only when GitHub itself reports the tag not found (Issue #744
    retention deleted it) -- every other verification failure (bad
    attestation, a moved tag, an invalid signature, a repository identity
    mismatch) stays a plain ``CliError`` and must keep failing closed, not
    fall back to reinstall.
    """


class UnsupportedReleaseVersionError(ReleaseRecoveryError):
    """A saved or selected Release uses an unsupported version shape."""


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

    def release(
        self, tag: str | None, *, channel: str = "stable"
    ) -> dict[str, object]:
        """Return the latest or named release metadata."""

    def resolve_tag(self, tag: str) -> TagResolution:
        """Resolve a tag to its current commit."""

    def verify_release(self, tag: str) -> None:
        """Verify the GitHub release attestation."""

    def verify_commit(self, sha: str) -> None:
        """Verify the commit signature through GitHub."""


@dataclass(frozen=True)
class Plan:
    """Explicit file effects for an init, adoption, or update operation.

    Init and adoption do not remove files. Update may explicitly move legacy
    generated assets into ``.csarc`` or retire obsolete generated state; each
    effect remains independently countable and auditable (#530, #742).
    """

    add: tuple[str, ...]
    overwrite: tuple[str, ...]
    remove: tuple[str, ...]
    preserve: tuple[str, ...]
    merge: tuple[str, ...]
    manual: tuple[str, ...]
    unknown: tuple[str, ...]
    move: tuple[str, ...] = ()
    delete: tuple[str, ...] = ()
    # Update only (#1066): modified files the new render no longer produces
    # stay in place, and product release state is never rewritten.
    retained: tuple[str, ...] = ()
    product_owned: tuple[str, ...] = ()
    # Update only (#1083): CSARC forwarding wrappers at moved scripts' old
    # paths that product files still call.
    shims: tuple[str, ...] = ()


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
    # The shared detector's facts (Issue #1072). They stay out of the plan
    # identity below so an adoption plan's repository binding is unchanged.
    facts: Mapping[str, Mapping[str, object]] = dataclass_field(
        default_factory=dict, compare=False
    )

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
    # Setup questions, work mode, warnings, and approval route (#1078);
    # only init and adopt plans carry one.
    setup: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        """Return the stable machine-readable plan representation."""
        result: dict[str, object] = {
            "answers": dict(sorted(self.answers.items())),
            "mode": self.mode,
            "release": release_contract(self.answers),
            "release_capabilities": self.capabilities,
            "release_ownership": release_ownership(self.answers),
            "repository": self.repository.as_dict(),
            # Shared detector output (Issue #1072): every live fact with its
            # known or unknown state. Informational; apply binds `repository`.
            "repository_facts": {
                name: dict(fact)
                for name, fact in sorted(self.repository.facts.items())
            },
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
                "move": list(self.files.move),
                "overwrite": list(self.files.overwrite),
                "preserve": list(self.files.preserve),
                "remove": list(self.files.remove),
                "unknown": list(self.files.unknown),
            }
            if self.mode == "update":
                # Template-deleted paths are an update-only effect; adopt
                # plan bytes and digests stay unchanged.
                files_payload = cast(dict[str, object], result["files"])
                files_payload["delete"] = list(self.files.delete)
                files_payload["product_owned"] = list(self.files.product_owned)
                files_payload["retained"] = list(self.files.retained)
        if self.update is not None:
            result.update(self.update)
        if self.adoption is not None:
            result["adoption"] = self.adoption
        if self.setup is not None:
            result["setup"] = self.setup
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
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess without invoking a shell."""
    return subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture,
        env=dict(env) if env is not None else None,
    )


GIT_FILTER_CONFIG = re.compile(
    r"^filter\.(?P<driver>.+)\.(?:clean|smudge|process|required)$",
    re.IGNORECASE,
)


def git_environment(
    extra_config: tuple[tuple[str, str], ...] = (),
) -> dict[str, str]:
    """Build a Git environment without caller-injected execution config."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    config = (
        ("core.fsmonitor", "false"),
        ("core.hooksPath", os.devnull),
        *extra_config,
    )
    environment["GIT_CONFIG_COUNT"] = str(len(config))
    for index, (key, value) in enumerate(config):
        environment[f"GIT_CONFIG_KEY_{index}"] = key
        environment[f"GIT_CONFIG_VALUE_{index}"] = value
    return environment


def git_filter_config(repository: Path) -> tuple[tuple[str, str], ...]:
    """Return inert overrides for configured filters, including submodules."""
    if not repository.is_dir():
        return ()
    root = repository.resolve()
    pending = [root]
    visited: set[Path] = set()
    drivers: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        config = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "git",
                "-C",
                str(current),
                "config",
                "--includes",
                "--name-only",
                "--null",
                "--get-regexp",
                r"^filter\..*\.(clean|smudge|process|required)$",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=git_environment(),
        )
        if config.returncode not in {0, 1}:
            detail = (
                config.stderr.strip() or "Cannot inspect Git filter config."
            )
            raise CliError(detail)
        drivers.update(
            match.group("driver")
            for key in config.stdout.split("\0")
            if (match := GIT_FILTER_CONFIG.fullmatch(key)) is not None
        )
        index = subprocess.run(  # noqa: S603
            ["git", "-C", str(current), "ls-files", "--stage", "-z"],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
            env=git_environment(),
        )
        if index.returncode != 0:
            detail = index.stderr.strip() or "Cannot inspect Git submodules."
            raise CliError(detail)
        for entry in index.stdout.split("\0"):
            metadata, separator, relative_name = entry.partition("\t")
            if not separator or not metadata.startswith("160000 "):
                continue
            candidate = (current / relative_name).resolve()
            try:
                candidate.relative_to(root)
            except ValueError as error:
                raise CliError(
                    "Git submodule path escapes the repository."
                ) from error
            if candidate.is_dir():
                pending.append(candidate)
    return tuple(
        (f"filter.{driver}.{setting}", value)
        for driver in sorted(drivers)
        for setting, value in (
            ("clean", ""),
            ("smudge", ""),
            ("process", ""),
            ("required", "false"),
        )
    )


@overload
def run_git(
    command: list[str],
    *,
    repository: Path | None = None,
    cwd: Path | None = None,
    capture: bool = False,
    check: bool = True,
    text: Literal[True] = True,
    neutralize_filters: bool = False,
) -> subprocess.CompletedProcess[str]: ...


@overload
def run_git(
    command: list[str],
    *,
    repository: Path | None = None,
    cwd: Path | None = None,
    capture: bool = False,
    check: bool = True,
    text: Literal[False],
    neutralize_filters: bool = False,
) -> subprocess.CompletedProcess[bytes]: ...


def run_git(
    command: list[str],
    *,
    repository: Path | None = None,
    cwd: Path | None = None,
    capture: bool = False,
    check: bool = True,
    text: bool = True,
    neutralize_filters: bool = False,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    """Run Git without repository-local or ambient executable helpers."""
    if not command or command[0] != "git":
        raise ValueError("run_git requires a Git command")
    filter_config = (
        git_filter_config(repository)
        if repository is not None and neutralize_filters
        else ()
    )
    return subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        check=check,
        text=text,
        capture_output=capture,
        env=git_environment(filter_config),
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
    result = run_git(
        ["git", "-C", str(source), "rev-parse", f"{reference}^{{commit}}"],
        repository=source,
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


def require_supported_gh() -> None:
    """Fail closed unless GitHub CLI supports safe release verification."""
    requirement = (
        f"Release verification requires gh {MINIMUM_GH_VERSION} or newer. "
        f"Install or upgrade it using {GH_INSTALL_URL}."
    )
    try:
        result = run(["gh", "--version"], capture=True, check=False)
    except FileNotFoundError as error:
        raise CliError(f"GitHub CLI was not found. {requirement}") from error

    match = re.match(r"^gh version (\d+)\.(\d+)\.(\d+)(?:\s|$)", result.stdout)
    if result.returncode != 0 or match is None:
        output = result.stdout.strip() or result.stderr.strip() or "no output"
        raise CliError(
            f"Cannot determine the GitHub CLI version from {output!r}. "
            f"{requirement}"
        )
    current = tuple(int(part) for part in match.groups())
    minimum = tuple(int(part) for part in MINIMUM_GH_VERSION.split("."))
    if current < minimum:
        raise CliError(
            f"GitHub CLI {'.'.join(match.groups())} is too old. {requirement}"
        )


_NOT_FOUND_SUFFIX = re.compile(r"\(HTTP 404\)\s*$")


def gh_json_or_missing(endpoint: str) -> dict[str, object] | None:
    """Read one GitHub API object, or None when GitHub reports HTTP 404.

    Distinguishes "this exact resource is confirmed gone" from every other
    failure (auth, network, malformed JSON), which still raises through
    the same actionable ``CliError`` as ``gh_json``. Used only for a named
    release-tag lookup: a confirmed 404 there is the one condition Issue
    #744 allows to fall into the downstream reinstall flow instead of
    failing closed.

    `gh api` has no structured (e.g. JSON) error output to key off of, so
    this still parses stderr text -- but `_NOT_FOUND_SUFFIX` anchors on
    the literal `(HTTP 404)` suffix `gh`'s own REST client always appends
    to a failed request's message, rather than a bare substring search for
    "HTTP 404" anywhere in the text, which could also match an unrelated
    404 quoted inside a longer diagnostic (e.g. a nested-resource error
    embedded in a verbose message). This endpoint
    (`repos/{repo}/releases/tags/{tag}`) has no nested sub-resource of its
    own to be confused with, which limits the residual risk further.
    """
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
        if _NOT_FOUND_SUFFIX.search(detail):
            return None
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


def gh_json_list(endpoint: str) -> list[object]:
    """Read one GitHub API array response through the authenticated gh CLI."""
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
    if not isinstance(payload, list):
        raise CliError("GitHub returned an unexpected release response.")
    return payload


class GhReleaseClient:
    """GitHub CLI implementation of the release trust boundary."""

    def __init__(self) -> None:
        """Check the GitHub CLI before making any release-related call."""
        require_supported_gh()

    def repository(self) -> dict[str, object]:
        """Return canonical repository metadata."""
        return gh_json(f"repos/{CANONICAL_REPOSITORY}")

    def release(
        self, tag: str | None, *, channel: str = "stable"
    ) -> dict[str, object]:
        """Return the highest-precedence or named canonical release.

        A named lookup raises ``ReleaseNotFoundError`` on a confirmed
        HTTP 404 (Issue #744) so callers can distinguish "this tag is
        gone" from every other failure. "Latest" is selected by SemVer
        precedence across every published, non-draft release instead of
        GitHub's own `releases/latest` API, which never returns a
        `prerelease: true` Release and therefore cannot see an
        beta-suffixed tag. Stable is the default; beta is explicit opt-in.
        """
        if tag is None or tag == "latest":
            return self._latest(channel)
        endpoint = (
            f"repos/{CANONICAL_REPOSITORY}/releases/tags/{quote(tag, safe='')}"
        )
        release = gh_json_or_missing(endpoint)
        if release is None:
            raise ReleaseNotFoundError(
                f"GitHub Release {tag!r} was not found on the canonical "
                "repository."
            )
        return release

    def _latest(self, channel: str = "stable") -> dict[str, object]:
        """Return the highest-SemVer-precedence eligible, consistent release.

        A release whose GitHub `prerelease` flag disagrees with its own
        tag shape (the same check `release_identity()` applies afterward)
        is skipped here rather than selected -- selecting it and letting
        `release_identity()` hard-fail on it later would surface a
        confusing error for a release that was never going to be usable,
        when a perfectly good next-best candidate may exist.
        """
        eligible: dict[str, dict[str, object]] = {}
        page = 1
        while True:
            endpoint = (
                f"repos/{CANONICAL_REPOSITORY}/releases?per_page=100"
                f"&page={page}"
            )
            batch = gh_json_list(endpoint)
            if not batch:
                break
            for item in batch:
                if not isinstance(item, dict):
                    continue
                tag_name = item.get("tag_name")
                if (
                    not isinstance(tag_name, str)
                    or item.get("draft") is not False
                ):
                    continue
                try:
                    parsed = release_phase.parse_version(tag_name)
                except release_phase.ReleasePhaseError:
                    continue
                if (
                    item.get("prerelease") is not parsed.is_prerelease
                    or parsed.release_kind != channel
                ):
                    continue
                eligible[tag_name] = item
            if len(batch) < 100:
                break
            page += 1
        latest_tag = release_phase.select_latest(eligible)
        if latest_tag is None:
            raise CliError(
                "No published, well-formed, self-consistent GitHub Release "
                f"was found for the {channel} channel on the canonical "
                "repository."
            )
        return eligible[latest_tag]

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
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_dir():
        raise CliError(
            "--allow-unreleased template source is unavailable; use a local "
            "Git repository."
        )
    if requested is not None and FULL_SHA.fullmatch(requested):
        return Revision(
            requested.lower(),
            git_commit(source_path, requested),
            str(source_path),
        )
    label = requested or "latest-local-tag"
    reference = requested
    if reference is None:
        tags = run_git(
            ["git", "-C", str(source_path), "tag", "--sort=-version:refname"],
            repository=source_path,
            capture=True,
        ).stdout.splitlines()
        if not tags:
            raise CliError("Local template repository has no release tags.")
        reference = tags[0]
    return Revision(label, git_commit(source_path, reference), str(source_path))


def release_identity(release: dict[str, object]) -> tuple[str, int]:
    """Validate immutable beta/stable Release metadata (Issue #918).

    Every existing verification (immutable, draft, published) is kept
    unchanged; a `prerelease: true` Release is now approved as long as its
    tag is a legal beta/stable version and GitHub's own `prerelease` flag
    agrees with that shape, so this stays fail-closed for a malformed or
    self-contradictory tag rather than silently trusting either signal
    alone.
    """
    tag = release.get("tag_name")
    release_id = release.get("id")
    if not isinstance(tag, str) or not tag or not isinstance(release_id, int):
        raise CliError("GitHub returned incomplete release metadata.")
    if release.get("draft") is not False:
        raise CliError("Only published GitHub Releases are approved.")
    try:
        parsed = release_phase.parse_version(tag)
    except release_phase.ReleasePhaseError as error:
        raise UnsupportedReleaseVersionError(
            f"GitHub Release tag {tag!r} is not a supported beta/stable "
            "version; reinstall from the latest stable release is required."
        ) from error
    if release.get("prerelease") is not parsed.is_prerelease:
        raise CliError(
            f"GitHub Release {tag!r} prerelease flag does not match its "
            "version format."
        )
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
    channel: str = "stable",
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

    if channel not in release_phase.PHASES:
        raise CliError("--channel must be stable or beta.")
    github = client or GhReleaseClient()
    repository = github.repository()
    if (
        repository.get("id") != CANONICAL_REPOSITORY_ID
        or repository.get("full_name") != CANONICAL_REPOSITORY
    ):
        raise CliError("Canonical GitHub repository identity mismatch.")
    release = github.release(requested, channel=channel)
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


# Namespaces whose files only CSARC renders. copier.yml `_exclude` decides
# which of them a given set of options renders (#1077); an update retires a
# byte-identical file the new options no longer render.
CSARC_OWNED_PREFIXES = (
    ".csarc/docs/",
    ".csarc/policies/",
    ".csarc/scripts/",
    ".csarc/site/",
    ".csarc/tests/",
    ".github/ISSUE_TEMPLATE/",
    ".github/workflows/",
)


def product_release_workflow(answers: Mapping[str, object]) -> tuple[str, ...]:
    """Return the selected product-owned release workflow, if any (#1083)."""
    workflow = answers.get("release_workflow")
    if answers.get("release_ownership") != "product-owned" or not (
        isinstance(workflow, str) and workflow
    ):
        return ()
    return (workflow,)


def option_retirements(
    old_render: Mapping[str, object], new_render: Mapping[str, object]
) -> tuple[str, ...]:
    """Return CSARC-owned old-render files the new options no longer render."""
    return tuple(
        sorted(
            name
            for name in old_render
            if name.startswith(CSARC_OWNED_PREFIXES) and name not in new_render
        )
    )


# CodeQL-analyzed modules; copier.yml's enable_codeql uses the same set.
CODEQL_LANGUAGES = frozenset({"go", "python", "typescript"})


def detect_languages(target: Path) -> list[str]:
    """Return enabled language modules in their canonical order."""
    manifests = (
        ("go", "go.mod"),
        ("python", "pyproject.toml"),
        ("rust", "Cargo.toml"),
        ("typescript", "package.json"),
    )
    return [
        name for name, manifest in manifests if (target / manifest).is_file()
    ]


def selected_languages(answers: dict[str, object]) -> set[str]:
    """Read new module answers with a legacy profile fallback."""
    selected = answers.get("languages")
    if isinstance(selected, list):
        return {str(item) for item in selected}
    legacy = answers.get("language")
    if isinstance(legacy, str) and legacy != "ci":
        return set(legacy.split("-"))
    return set()


def adoption_lockfiles(answers: dict[str, object]) -> tuple[str, ...]:
    """Return lockfiles produced by the selected language tooling."""
    languages = selected_languages(answers)
    names = {
        "python": "uv.lock",
        "rust": "Cargo.lock",
        "typescript": "pnpm-lock.yaml",
    }
    return tuple(names[name] for name in sorted(languages & names.keys()))


def predicted_lockfile_effects(
    target: Path, planned: Plan, answers: dict[str, object]
) -> Plan:
    """Represent deferred lock generation without running package tooling."""
    additions = set(planned.add)
    overwrites = set(planned.overwrite)
    preserved = set(planned.preserve)
    fixed = (
        additions
        | overwrites
        | {
            *planned.merge,
            *planned.manual,
            *planned.unknown,
        }
    )
    existing = project_files(target)
    for name in adoption_lockfiles(answers):
        if name in fixed:
            continue
        preserved.discard(name)
        (overwrites if name in existing else additions).add(name)
    return Plan(
        tuple(sorted(additions)),
        tuple(sorted(overwrites)),
        planned.remove,
        tuple(sorted(preserved)),
        planned.merge,
        planned.manual,
        planned.unknown,
        planned.move,
    )


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
    skip_tasks: bool,
    persist_answers: bool = True,
    decisions: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Render one immutable template revision into a staging directory.

    ``persist_answers=False`` keeps Copier's rendered answers file exactly
    as the template recorded it, so the caller can read which questions the
    template actually asked. Otherwise the template's resolved render
    context (SPEC-009 seeds, live facts, derived context, and project_mode)
    is returned for provenance, and the settings file is rewritten in its
    canonical schema with only explicit one-time ``decisions`` added.
    """
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
    render_data = dict(data)
    if persist_answers:
        render_data[settings_schema.RENDER_CONTEXT_FLAG] = True
    data_file.write_text(
        yaml.safe_dump(render_data, sort_keys=True), encoding="utf-8"
    )
    command.extend(["--data-file", str(data_file)])
    command.extend([source, str(stage)])
    try:
        result = run(command, capture=True, check=False)
    finally:
        data_file.unlink(missing_ok=True)
    phase = "preview render" if skip_tasks else "task-bearing render"
    if result.returncode != 0:
        raise CliError(
            f"Copier {phase} failed: "
            + (
                result.stderr.strip()
                or result.stdout.strip()
                or "unknown Copier error"
            )
        )
    if not persist_answers:
        return {}
    try:
        context = take_render_context(stage)
        pin_answer_commit(stage, revision.sha)
        persist_release_answers(stage, data, decisions)
    except CliError as error:
        raise CliError(f"Copier {phase} failed: {error}") from error
    return context


def take_render_context(stage: Path) -> dict[str, object]:
    """Read and remove the render context a schema 2 template wrote.

    A template that predates SPEC-009 writes none, which returns ``{}``.
    """
    path = stage / settings_schema.RENDER_CONTEXT_FILE
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CliError("The template render context is unreadable.") from error
    finally:
        path.unlink(missing_ok=True)
    if not isinstance(payload, dict) or set(payload) - set(
        settings_schema.CONTEXT_KEYS
    ):
        raise CliError("The template render context has an unknown shape.")
    return {str(key): value for key, value in payload.items()}


def pin_answer_commit(target: Path, commit: str) -> None:
    """Replace Copier's abbreviated revision with the reviewed full SHA."""
    answers = safe_copier_config_path(target)
    lines = answers.read_text(encoding="utf-8").splitlines()
    matches = sum(line.startswith("_commit:") for line in lines)
    if matches != 1:
        raise CliError("Copier answers must contain exactly one _commit value.")
    pinned = [
        f"_commit: {commit}" if line.startswith("_commit:") else line
        for line in lines
    ]
    atomic_replace_text(
        target,
        answers.relative_to(target).as_posix(),
        "\n".join(pinned) + "\n",
        mode=stat.S_IMODE(answers.lstat().st_mode),
    )


def config_path(target: Path) -> Path:
    """Return the current config, falling back to pre-migration answers."""
    current = target / CONFIG_FILE
    if current.is_file():
        return current
    return target / LEGACY_ANSWERS_FILE


def safe_copier_config_path(target: Path) -> Path:
    """Reject a missing or link-routed Copier configuration."""
    path = config_path(target)
    relative = path.relative_to(target).as_posix()
    path = checked_destination(target, relative)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as error:
        raise CliError(f"Template did not create {CONFIG_FILE}.") from error
    if not stat.S_ISREG(mode):
        raise CliError("Copier configuration must be a regular file.")
    return path


def copier_config_binding(target: Path) -> tuple[str, str]:
    """Bind both the persisted Copier configuration path and its bytes."""
    path = safe_copier_config_path(target)
    return path.relative_to(target).as_posix(), file_fingerprint(path)


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
        if isinstance(key, str)
        and not key.startswith("_")
        and key != settings_schema.SCHEMA_KEY
    }


def explicit_decisions(
    explicit_data: Mapping[str, object],
) -> dict[str, object]:
    """Return the one-time derived decisions passed with ``--data``."""
    return {
        key: value
        for key, value in explicit_data.items()
        if key in settings_schema.DECISION_SETTINGS
    }


def parse_settings_data(values: list[str]) -> dict[str, str]:
    """Parse ``--data``; retired keys are checked against the render."""
    return parse_data(values)


def reject_retired_data_for(
    stage: Path, explicit_data: Mapping[str, object]
) -> None:
    """Refuse retired ``--data`` once a schema 2 render is known.

    Runs right after the side-effect-free preview render and before any
    target write; an older target template still asks legacy questions.
    """
    path = config_path(stage)
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError, yaml.YAMLError:
        return
    if (
        not isinstance(payload, dict)
        or settings_schema.SCHEMA_KEY not in payload
    ):
        return
    try:
        settings_schema.reject_retired_data(explicit_data)
    except settings_schema.SettingsSchemaError as error:
        raise CliError(str(error)) from error


def persist_release_answers(
    target: Path,
    answers: Mapping[str, object],
    decisions: Mapping[str, object] | None = None,
) -> None:
    """Persist release answers in the rendered template's schema.

    A schema 2 render (SPEC-009) is rewritten canonically: its persistent
    intent, the resolved release owner (#1068), and only the explicit
    one-time ``decisions`` for derived values; seeds and facts never land
    in the settings file.
    """
    path = safe_copier_config_path(target)
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CliError(f"Cannot read Copier answers from {path}.") from error
    if not isinstance(payload, dict):
        raise CliError(f"Copier answers in {path} must be a mapping.")
    if settings_schema.SCHEMA_KEY in payload:
        values = {str(key): value for key, value in payload.items()}
        values["release_ownership"] = release_ownership(answers)
        for key, value in (decisions or {}).items():
            if key in settings_schema.DECISION_SETTINGS:
                values[key] = value
        try:
            text = settings_schema.config_text(values)
        except settings_schema.SettingsSchemaError as error:
            raise CliError(str(error)) from error
        atomic_replace_text(
            target,
            path.relative_to(target).as_posix(),
            text,
            mode=stat.S_IMODE(path.lstat().st_mode),
        )
        return
    config_reader = managed_script(target, "csarc_config.py")
    simplified_schema = config_reader.is_file() and (
        "ACTIONS_FALLBACK_MODES" in config_reader.read_text(encoding="utf-8")
    )
    if not simplified_schema:
        contract = release_contract(answers)
        payload.update(
            release_immutable_releases=contract["immutable_releases"],
            release_ownership=contract["ownership"],
            release_ownership_reason=contract["reason"],
            release_required_inputs=contract["required_inputs"],
            release_settings_owner=contract["settings_owner"],
            release_workflow=contract["selected_workflow"] or "",
        )
    else:
        payload["release_ownership"] = release_ownership(answers)
        legacy_keys = {
            "branch_strategy",
            "copilot_review_max_level",
            "enable_docker",
            "policy_actions_permissions",
            "policy_branch_ruleset",
            "policy_labels",
            "policy_repository_settings",
            "pr_review_mode",
            "release_levels_enabled",
            "release_immutable_releases",
            "release_ownership_reason",
            "release_required_inputs",
            "release_settings_owner",
            "release_workflow",
            "reviewers",
        }
        legacy_keys.update(
            f"release_level_{level}_{field}"
            for level in ("alpha", "beta", "early", "formal")
            for field in ("review", "verification")
        )
        for key in legacy_keys:
            payload.pop(key, None)
    atomic_replace_text(
        target,
        path.relative_to(target).as_posix(),
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        mode=stat.S_IMODE(path.lstat().st_mode),
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


def reject_canonical_verification_hook(
    target: Path, hook: Path, raw_path: str
) -> None:
    """Reject both current and legacy canonical verifier identities."""
    for canonical in (
        target / ".csarc" / "scripts" / "verify",
        target / "scripts" / "verify",
    ):
        try:
            if canonical.exists() and os.path.samefile(hook, canonical):
                raise CliError(
                    "Project verification hook must not resolve to the "
                    f"canonical verifier: {raw_path}"
                )
        except OSError as error:
            raise CliError(
                f"Cannot compare project verification hook identity: {raw_path}"
            ) from error


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
    reject_canonical_verification_hook(target, hook, raw_path)
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


def git_blob_oid(target: Path, revision: str, relative_name: str) -> str:
    """Return one file's blob identity at a trusted revision."""
    checked_destination(target, relative_name)
    result = run_git(
        [
            "git",
            "-C",
            str(target),
            "rev-parse",
            "--verify",
            f"{revision}:{relative_name}",
        ],
        repository=target,
        capture=True,
        check=False,
        neutralize_filters=True,
    )
    oid = result.stdout.strip()
    if result.returncode != 0 or GIT_OBJECT_ID.fullmatch(oid) is None:
        detail = result.stderr.strip()
        raise CliError(
            f"Cannot recover the original manual file {relative_name} from "
            f"Git history. {detail}"
        )
    kind = run_git(
        ["git", "-C", str(target), "cat-file", "-t", oid],
        repository=target,
        capture=True,
        check=False,
        neutralize_filters=True,
    )
    if kind.returncode != 0 or kind.stdout.strip() != "blob":
        raise CliError(f"Original manual path is not a file: {relative_name}.")
    return oid.lower()


def git_worktree_file_oid(
    attributes_repo: Path, target: Path, relative_name: str
) -> str:
    """Hash working-tree bytes through trusted Git path attributes."""
    path = checked_destination(target, relative_name)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as error:
        raise CliError(f"Manual adoption file is missing: {path}") from error
    if not stat.S_ISREG(mode):
        raise CliError(f"Manual adoption file is not a regular file: {path}")
    result = run_git(
        [
            "git",
            "-C",
            str(attributes_repo),
            "hash-object",
            f"--path={relative_name}",
            str(path),
        ],
        repository=attributes_repo,
        capture=True,
        check=False,
        neutralize_filters=True,
    )
    oid = result.stdout.strip()
    if result.returncode != 0 or GIT_OBJECT_ID.fullmatch(oid) is None:
        detail = result.stderr.strip()
        raise CliError(
            f"Cannot hash manual adoption file {relative_name} with Git path "
            f"attributes. {detail}"
        )
    return oid.lower()


def pending_adoption_data(
    target: Path,
    revision: Revision,
    repository: RepositoryContext,
    answers_path: Path,
    managed_files: tuple[str, ...],
    manual_files: tuple[str, ...],
    unknown_files: tuple[str, ...],
    target_head: str,
    work_item_mapping: dict[str, object],
    render_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the checkpoint needed to resume one exact adoption.

    Schema 2 settings omit seeds and live facts (SPEC-009), so the
    checkpoint carries the resolved render context finalize replays.
    """
    payload: dict[str, object] = {
        "answers_sha256": hashlib.sha256(answers_path.read_bytes()).hexdigest(),
        "managed_files": [
            {"fingerprint": file_fingerprint(target / name), "path": name}
            for name in managed_files
            if name
            not in {CONFIG_FILE.as_posix(), LEGACY_ANSWERS_FILE.as_posix()}
        ],
        "manual_file_git_oid": {
            name: git_blob_oid(target, target_head, name)
            for name in manual_files
        },
        "manual_files": list((*manual_files, *unknown_files)),
        "manual_merge_files": list(manual_files),
        "repository": repository.as_dict(),
        "schema_version": 2,
        "target_head": target_head,
        "template": {
            "release": revision.label,
            "sha": revision.sha,
            "source": revision.source,
            "verification": (
                "verified" if revision.verified else "development-unreleased"
            ),
        },
        "work_item_mapping": work_item_mapping,
    }
    if render_context:
        payload["render_context"] = dict(sorted(render_context.items()))
    return payload


def write_pending_adoption(target: Path, payload: dict[str, object]) -> None:
    """Atomically persist an incomplete adoption checkpoint."""
    atomic_replace_text(
        target,
        PENDING_ADOPTION_FILE.as_posix(),
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        mode=0o666,
    )


def read_pending_adoption(target: Path) -> dict[str, object]:
    """Read and minimally validate an adoption checkpoint."""
    path = checked_destination(target, PENDING_ADOPTION_FILE.as_posix())
    try:
        mode = path.lstat().st_mode
    except (FileNotFoundError, NotADirectoryError) as error:
        raise CliError(
            "No pending adoption exists; run csarc adopt first or use "
            "csarc update for a completed adoption."
        ) from error
    if not stat.S_ISREG(mode):
        raise CliError(
            "Pending adoption state is not a regular file; restore the "
            "checkpoint or restart adoption from a clean commit."
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
    work_item_mapping = (
        payload.get("work_item_mapping") if isinstance(payload, dict) else None
    )
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") not in {1, 2}
        or not isinstance(payload.get("answers_sha256"), str)
        or not isinstance(template, dict)
        or not isinstance(repository, dict)
        or not isinstance(managed, list)
        or (
            work_item_mapping is not None
            and not isinstance(work_item_mapping, dict)
        )
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


def validate_pending_manual_merges(
    target: Path,
    pending: Mapping[str, object],
    answers: dict[str, object],
    planned: Plan,
    target_head: str,
    baseline: Path,
) -> tuple[str, ...]:
    """Verify pending merge identities and require changed manual bytes."""
    if pending.get("schema_version") != 2:
        raise CliError(
            "Pending adoption state predates manual-file fingerprints, so "
            "CSARC cannot determine whether its manual merges were completed; "
            "restore the original files and restart adoption from a clean "
            "commit."
        )
    raw_files = pending.get("manual_files")
    raw_merges = pending.get("manual_merge_files")
    raw_fingerprints = pending.get("manual_file_git_oid")
    if (
        not isinstance(raw_files, list)
        or not all(isinstance(value, str) for value in raw_files)
        or not isinstance(raw_merges, list)
        or not all(isinstance(value, str) for value in raw_merges)
        or not isinstance(raw_fingerprints, dict)
        or not all(
            isinstance(name, str)
            and isinstance(value, str)
            and GIT_OBJECT_ID.fullmatch(value) is not None
            for name, value in raw_fingerprints.items()
        )
        or tuple(raw_merges) != planned.manual
        or tuple(raw_files) != (*planned.manual, *planned.unknown)
        or set(raw_merges) != set(raw_fingerprints)
    ):
        raise CliError(
            "Pending manual-file fingerprints are invalid; restore the "
            "checkpoint or restart adoption from a clean commit."
        )
    fingerprints = cast(dict[str, str], raw_fingerprints)
    forged = [
        name
        for name in cast(list[str], raw_merges)
        if git_blob_oid(target, target_head, name) != fingerprints[name]
    ]
    if forged:
        raise CliError(
            "Pending manual-file fingerprints do not match the original "
            "Git revision for: "
            + ", ".join(sorted(forged))
            + ". Restore the checkpoint or restart adoption from a clean "
            "commit."
        )
    unchanged = [
        name
        for name in cast(list[str], raw_merges)
        if git_worktree_file_oid(baseline, target, name) == fingerprints[name]
    ]
    if unchanged:
        raise CliError(
            "Manual merge is unfinished; these files have unchanged content "
            "after Git normalization: "
            + ", ".join(sorted(unchanged))
            + ". Complete each listed merge, then rerun csarc adopt "
            "--finalize."
        )
    if "typescript" in selected_languages(answers):
        package_path = checked_destination(target, "package.json")
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CliError(
                "Manual package.json is invalid JSON; fix it, then rerun "
                "csarc adopt --finalize."
            ) from error
        expected_name = answers.get("project_slug")
        actual_name = package.get("name") if isinstance(package, dict) else None
        if not isinstance(expected_name, str) or actual_name != expected_name:
            raise CliError(
                "Manual package.json name must match project_slug "
                f"({expected_name!r}); found {actual_name!r}. Fix "
                "package.json, "
                "then rerun csarc adopt --finalize."
            )
    return tuple(cast(list[str], raw_files))


def pending_adoption_target_head(
    target: Path, pending: Mapping[str, object]
) -> str:
    """Recover and authenticate the pre-adoption commit from Git history."""
    if pending.get("schema_version") != 2:
        raise CliError(
            "Pending adoption state predates manual-file fingerprints, so "
            "CSARC cannot determine whether its manual merges were completed; "
            "restore the original files and restart adoption from a clean "
            "commit."
        )
    saved_head = pending.get("target_head")
    if (
        not isinstance(saved_head, str)
        or FULL_SHA.fullmatch(saved_head) is None
    ):
        raise CliError(
            "Pending adoption has no valid original Git revision; restore the "
            "checkpoint or restart adoption from a clean commit."
        )
    committed = run_git(
        [
            "git",
            "-C",
            str(target),
            "ls-tree",
            "-z",
            "--name-only",
            "HEAD",
            "--",
            PENDING_ADOPTION_FILE.as_posix(),
        ],
        repository=target,
        capture=True,
        check=False,
        neutralize_filters=True,
    )
    if committed.returncode != 0:
        detail = committed.stderr.strip()
        raise CliError("Cannot inspect pending adoption Git history. " + detail)
    if committed.stdout.rstrip("\0") == PENDING_ADOPTION_FILE.as_posix():
        introduced = run_git(
            [
                "git",
                "-C",
                str(target),
                "log",
                "--diff-filter=A",
                "--format=%H",
                "-1",
                "--",
                PENDING_ADOPTION_FILE.as_posix(),
            ],
            repository=target,
            capture=True,
            check=False,
            neutralize_filters=True,
        )
        introduction = introduced.stdout.strip()
        if (
            introduced.returncode != 0
            or FULL_SHA.fullmatch(introduction) is None
        ):
            raise CliError(
                "Cannot locate the pending adoption checkpoint in Git "
                "history; restore it or restart adoption from a clean commit."
            )
        parent = run_git(
            [
                "git",
                "-C",
                str(target),
                "rev-parse",
                f"{introduction}^",
            ],
            repository=target,
            capture=True,
            check=False,
            neutralize_filters=True,
        )
        observed_head = parent.stdout.strip()
        if parent.returncode != 0 or FULL_SHA.fullmatch(observed_head) is None:
            raise CliError(
                "Cannot recover the repository revision before pending "
                "adoption; restart adoption from a clean commit."
            )
    elif not committed.stdout:
        observed_head, _ = git_target_state(target)
    else:
        raise CliError(
            "Pending adoption path has an unexpected Git tree entry; restore "
            "the checkpoint or restart adoption from a clean commit."
        )
    if observed_head.lower() != saved_head.lower():
        raise CliError(
            "Pending adoption does not match its original Git revision; "
            "restore the checkpoint or restart adoption from a clean commit."
        )
    return saved_head


def validate_pending_adoption_identity(  # noqa: C901
    target: Path,
) -> tuple[dict[str, object], Path, str]:
    """Validate only the local identity of one pending adoption."""
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
    saved_repository = raw_repository.get("repository")
    saved_visibility = raw_repository.get("visibility")
    current_repository = target_repository(target)
    repository_matches = (
        saved_repository is None and current_repository is None
    ) or (
        isinstance(saved_repository, str)
        and current_repository is not None
        and current_repository.casefold() == saved_repository.casefold()
    )
    if (
        not repository_matches
        or saved_visibility not in REPOSITORY_VISIBILITIES
        or read_answer(answers_path, "project_visibility") != saved_visibility
    ):
        raise CliError(
            "Repository origin or visibility changed after adoption started; "
            "restore it or restart adoption from a clean commit."
        )

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
        path = checked_destination(target, name)
        if file_fingerprint(path) != expected:
            raise CliError(
                f"Managed adoption file drifted: {name}. Restore it from the "
                "pending template revision, then rerun csarc adopt --finalize."
            )

    return pending, answers_path, pending_adoption_target_head(target, pending)


def provenance_data(
    revision: Revision,
    previous: dict[str, object] | None = None,
    *,
    applied_at: str | None = None,
    answers: Mapping[str, object] | None = None,
    final_plan_sha256: str | None = None,
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
    if final_plan_sha256 is not None:
        # The replayed update final plan this state came from (#1067).
        result["final_plan_sha256"] = final_plan_sha256
    return result


def write_provenance(
    target: Path,
    revision: Revision,
    previous: dict[str, object] | None = None,
    *,
    applied_at: str | None = None,
    answers: Mapping[str, object] | None = None,
    final_plan_sha256: str | None = None,
) -> None:
    """Atomically persist verified release provenance.

    When the target holds schema 2 settings (SPEC-009), the record also
    binds the immutable project_mode, the resolved render context taken
    from ``answers``, and digests of both, so status and update detect a
    hand edit or a missing record before any write (Issue #1071).
    """
    payload = provenance_data(
        revision,
        previous,
        applied_at=applied_at,
        answers=answers,
        final_plan_sha256=final_plan_sha256,
    )
    config = target / CONFIG_FILE
    if answers is not None and config.is_file():
        config_bytes = config.read_bytes()
        try:
            raw = yaml.safe_load(config_bytes.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as error:
            raise CliError(f"Cannot read {CONFIG_FILE}.") from error
        if isinstance(raw, dict) and settings_schema.SCHEMA_KEY in raw:
            payload["settings"] = settings_schema.settings_record(
                settings_schema.context_from(answers), config_bytes
            )
    atomic_replace_text(
        target,
        PROVENANCE_FILE.as_posix(),
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        mode=0o666,
    )


def load_saved_settings(target: Path) -> settings_schema.SavedSettings:
    """Read legacy answers or verified schema 2 settings before any write.

    An unknown schema, a hand-edited settings file or provenance record, a
    missing record, or a contradictory project_mode fails closed here
    (Issue #1071 AC4/AC6) with one stable error.
    """
    path = config_path(target)
    try:
        return settings_schema.read_saved_settings(
            path, read_provenance(target)
        )
    except settings_schema.SettingsSchemaError as error:
        raise CliError(str(error)) from error


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


def preserve_existing_security_policy(stage: Path, target: Path) -> None:
    """Leave an existing product-owned root security policy unchanged."""
    security = target / "SECURITY.md"
    staged_security = stage / "SECURITY.md"
    if is_regular_file(security) and is_regular_file(staged_security):
        staged_security.unlink()


def apply_adoption_policies(stage: Path, target: Path) -> tuple[str, ...]:
    """Apply the fixed merges and preservation for an existing repository."""
    preserve_existing_security_policy(stage, target)
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
        (),
        tuple(sorted(set(preserve))),
        tuple(sorted(merge)),
        tuple(sorted(manual)),
        tuple(sorted(unknown)),
    )


def legacy_layout_pairs(
    stage: Path,
    target: Path,
) -> tuple[tuple[str, str], ...]:
    """Return only known generated paths that need the one-time layout move.

    A destination the target already has means the move happened in an
    earlier update; a legacy file left beside it is the customized copy
    that update kept, never a second move onto that destination (#1083).
    """
    pairs: set[tuple[str, str]] = set()
    staged = project_files(stage)
    existing = project_files(target)
    prefixes = (
        ("scripts/", ".csarc/scripts/"),
        ("policies/", ".csarc/policies/"),
        ("tests/", ".csarc/tests/"),
        ("site/static/", ".csarc/site/static/"),
    )
    for old_prefix, new_prefix in prefixes:
        for new in staged:
            if new.startswith(new_prefix):
                old = old_prefix + new.removeprefix(new_prefix)
                if old in existing and new not in existing:
                    pairs.add((old, new))
    exact = {
        ".copier-answers.yml": ".csarc/config.yml",
        ".release-please-manifest.json": (
            ".csarc/release-please-manifest.json"
        ),
        ".github/REVIEWERS": ".csarc/REVIEWERS",
        "CLAUDE.md": ".claude/CLAUDE.md",
        "docs/ci-policy.md": ".csarc/docs/ci-policy.md",
        "docs/csarc.md": ".csarc/docs/csarc.md",
        "docs/milestone-description.md": (
            ".csarc/docs/milestone-description.md"
        ),
        "docs/site-theme.css": "docs/site/theme.css",
        "release-please-config.json": ".csarc/release-please-config.json",
        "site/README.md": ".csarc/site/README.md",
        "site/data/glossary.toml": ".csarc/site/data/glossary.toml",
        "site/data/navigation.json": "docs/site/data/navigation.json",
        "site/version.json": ".csarc/site/version.json",
        "version.txt": ".csarc/version.txt",
    }
    for old, new in exact.items():
        if old in existing and new in staged and new not in existing:
            pairs.add((old, new))
    for old in existing:
        if old.startswith("site/content/"):
            destination = "docs/site/content/" + old.removeprefix(
                "site/content/"
            )
            if destination not in existing:
                pairs.add((old, destination))
    return tuple(sorted(pairs))


def update_file_plan(
    staged: Plan,
    moves: tuple[tuple[str, str], ...],
    removals: tuple[str, ...] = (),
) -> Plan:
    """Make Copier's update effects explicit without changing the target."""
    old = {source for source, _destination in moves}
    new = {destination for _source, destination in moves}
    return Plan(
        tuple(sorted(set(staged.add) - new)),
        tuple(sorted(set(staged.overwrite) | (set(staged.manual) - new))),
        tuple(sorted(removals)),
        tuple(sorted(set(staged.preserve) - old - new - set(removals))),
        staged.merge,
        (),
        staged.unknown,
        tuple(f"{source} -> {destination}" for source, destination in moves),
    )


def apply_layout_moves(
    target: Path, moves: tuple[tuple[str, str], ...]
) -> None:
    """Apply the approved generated-layout moves with collision protection."""
    for source_name, destination_name in moves:
        source = checked_destination(target, source_name)
        destination = checked_destination(target, destination_name)
        if not source.exists() and not source.is_symlink():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            if file_fingerprint(source) != file_fingerprint(destination):
                raise CliError(
                    "Generated layout migration collision: "
                    f"{source_name} -> {destination_name}."
                )
            source.unlink()
        else:
            source.replace(destination)
    legacy_directories = (
        "scripts",
        "policies",
        "site/content",
        "site/data",
        "site",
    )
    for relative in legacy_directories:
        directory = target / relative
        with suppress(OSError):
            directory.rmdir()


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
    if adoption is not None and adoption.get("mapping_reviewed") is False:
        return (
            "Review required",
            "Confirm the work-item mapping suggestions before applying this "
            "plan.",
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


def observed_setting_note(key: str, value: object) -> str:
    """Return the report note for one observed difference (#1068, #1072)."""
    if key in settings_schema.DECISION_SETTINGS:
        shown = (
            ", ".join(f"`{redact(item)}`" for item in value)
            if isinstance(value, list)
            else f"`{redact(value)}`"
        )
        return (
            f"The native manifests resolve {shown}; the recorded value is "
            f"kept. Pass `--data {key}=<value>` once to decide."
        )
    if key in settings_schema.INTENT_SETTINGS:
        return (
            f"Live GitHub facts suggest `{redact(value)}`; the saved intent "
            "stays unchanged. Pass `--data "
            f"{key}=<value>` only to change it."
        )
    return (
        f"Live GitHub facts suggest `{redact(value)}`; the saved value is "
        f"kept. Pass `--data {key}=<value>` to change it."
    )


def report_setting_rows(
    after: Mapping[str, object],
    before: Mapping[str, object] | None,
    explicit: Collection[str] = (),
    observed: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Return allowlisted SPEC-008 setting rows with JSON-typed values.

    ``before`` is ``None`` for adoption: every resolved setting is new.
    Keys outside ``REPORT_SETTING_KEYS`` and the retired legacy keys never
    appear (#950). An update classifies migrated governance keys and
    retired legacy keys with the approved mapping (#1064). A live fact in
    ``observed`` that differs from the kept saved value is noted on its row
    (#1068).
    """
    previous = {} if before is None else before
    live = {} if observed is None else observed
    migrated = (
        {}
        if before is None
        else governance_migration.setting_classes(before, after, explicit)
    )
    # A retired key is reported only when the saved file still has it.
    retired = (
        set(governance_migration.RETIRED_SETTINGS)
        - settings_schema.RELEASE_OBSERVATIONS
    ) & set(previous)
    reportable = REPORT_SETTING_KEYS | retired
    keys = sorted(
        key for key in set(previous) | set(after) if key in reportable
    )
    rows: list[dict[str, object]] = []
    for key in keys:
        old = previous.get(key)
        new = after.get(key)
        source = "explicit" if key in explicit else "derived"
        note: str | None = None
        if key in migrated:
            setting_class, note = migrated[key]
            if setting_class == "retired":
                new = None
        elif before is None or key not in previous:
            setting_class = "new"
        elif key not in after:
            setting_class = "retired"
        elif old == new:
            setting_class = "unchanged"
            source = "explicit" if key in explicit else "saved"
        else:
            setting_class = "decision"
        if key in live and note is None:
            note = observed_setting_note(key, live[key])
        rows.append(
            {
                "after": redact(new),
                "before": redact(old),
                "class": setting_class,
                "key": key,
                "note": note,
                "source": source,
            }
        )
    return rows


def setup_setting_rows(
    rows: Sequence[dict[str, object]], setup: Mapping[str, object]
) -> list[dict[str, object]]:
    """Give adopt rows the source and note the setup planner recorded.

    A TTY answer or an explicit ``--data`` value is ``explicit``; a
    detection, a work-mode expansion, or a suggested default stays
    ``derived`` with a note naming where the value came from (#1078).
    """
    raw = setup.get("sources")
    sources = raw if isinstance(raw, dict) else {}
    result: list[dict[str, object]] = []
    for row in rows:
        entry = sources.get(row["key"])
        updated = dict(row)
        if isinstance(entry, dict) and entry.get("source") in {
            "explicit",
            "derived",
        }:
            updated["source"] = entry["source"]
            note = entry.get("note")
            if isinstance(note, str) and updated.get("note") is None:
                updated["note"] = note
        result.append(updated)
    return result


def setup_decision_actions(
    setup: Mapping[str, object] | None, answers: Mapping[str, object]
) -> list[dict[str, object]]:
    """Return adopt's non-blocking decisions for suggested intent (#1078).

    A non-interactive adopt takes the suggested value of an intent no
    unique source decides; the report asks the reviewer to confirm it.
    """
    if setup is None:
        return []
    raw = setup.get("suggested")
    suggested = raw if isinstance(raw, list) else []
    actions: list[dict[str, object]] = []
    for key in sorted(str(item) for item in suggested):
        if key not in REPORT_SETTING_KEYS:
            continue
        value = answers.get(key)
        shown = ", ".join(map(str, value)) if isinstance(value, list) else value
        actions.append(
            {
                "blocking": False,
                "command": f"csarc adopt --data {key}=<value>",
                "kind": "setting-decision",
                "message": (
                    f"No unique source decides {key}; this plan uses the "
                    f"suggested `{redact(shown)}`. Confirm it, or plan again "
                    "with an explicit value."
                ),
                "subject": key,
            }
        )
    return actions


def report_file_rows(
    files: Plan,
    preserved_dirty: Collection[str] = (),
    *,
    update: bool = False,
) -> list[dict[str, object]]:
    """Map one file plan onto the closed SPEC-008 action vocabulary.

    An update's three-way conflicts are ``update-conflict`` rows; adopt and
    reinstall keep their two-way ``manual-merge`` rows.
    """
    rows: list[tuple[str, str, str, str | None, str | None]] = []
    rows.extend((path, "add", "template", None, None) for path in files.add)
    rows.extend(
        (
            path,
            "overwrite",
            lifecycle_report.COMPATIBILITY_SHIM
            if path in files.shims
            else "template",
            None,
            None,
        )
        for path in files.overwrite
    )
    rows.extend(
        (path, "overwrite", "automatic-merge", None, None)
        for path in files.merge
    )
    for move in files.move:
        source, _separator, destination = move.partition(" -> ")
        rows.append((destination, "move", "layout-migration", source, None))
    rows.extend(
        (path, "retire", "obsolete-generated", None, None)
        for path in files.remove
    )
    rows.extend(
        (path, "remove", "template-deleted", None, None)
        for path in files.delete
    )
    rows.extend(
        (
            path,
            "preserve",
            "dirty-preserved"
            if path in preserved_dirty
            else (
                "product-owned" if path in files.product_owned else "untouched"
            ),
            None,
            None,
        )
        for path in files.preserve
    )
    rows.extend(
        (path, "conflict", "retire-modified", None, "keep-current")
        for path in files.retained
    )
    rows.extend(
        (
            path,
            "conflict",
            "update-conflict" if update else "manual-merge",
            None,
            "pending",
        )
        for path in files.manual
    )
    rows.extend(
        (path, "conflict", "undetermined", None, "pending")
        for path in files.unknown
    )
    order = list(lifecycle_report.FILE_ACTIONS)
    return [
        {
            "action": action,
            "decision": decision,
            "from": source,
            "path": path,
            "reason": reason,
        }
        for path, action, reason, source, decision in sorted(
            rows, key=lambda row: (order.index(row[1]), row[0])
        )
    ]


def candidate_verification_state(value: object) -> dict[str, object]:
    """Split the legacy candidate verification string into state and reason."""
    text = str(value)
    if text in {"passed", "pending-authorization", "deferred-manual-merge"}:
        return {"reason": None, "state": text}
    if text == "not-run-dirty":
        return {
            "reason": "The dirty working tree can only be reviewed.",
            "state": "not-run",
        }
    if text.startswith("failed"):
        reason = text.removeprefix("failed").removeprefix(":").strip()
        return {"reason": reason or None, "state": "failed"}
    return {
        "reason": f"Unrecognized verification result: {text}",
        "state": "failed",
    }


def adoption_required_actions(  # noqa: C901
    plan: ResolvedPlan,
) -> list[dict[str, object]]:
    """Derive adopt required actions from the plan's target evidence."""
    actions: list[dict[str, object]] = []
    adoption = plan.adoption or {}

    def add(
        kind: str,
        subject: str,
        message: str,
        *,
        blocking: bool,
        command: str | None = None,
    ) -> None:
        actions.append(
            {
                "blocking": blocking,
                "command": command,
                "kind": kind,
                "message": message,
                "subject": subject,
            }
        )

    if adoption.get("mapping_reviewed") is False:
        add(
            "mapping-review",
            "work_item_mapping_review",
            "Work-item mapping suggestions are pending review; plan again "
            "with an explicit review choice (or review-individually).",
            blocking=False,
            command="csarc adopt --data work_item_mapping_review=accept-safe",
        )
    raw_mapping = adoption.get("work_item_mapping")
    mapping = raw_mapping if isinstance(raw_mapping, dict) else {}
    for group, item_kind in (
        (mapping.get("issue_types"), "Issue Type"),
        (mapping.get("labels"), "label"),
    ):
        if not isinstance(group, list):
            continue
        for item in group:
            if isinstance(item, dict) and (
                item.get("action") == "decision-required"
            ):
                add(
                    "mapping-decision",
                    str(item.get("source")),
                    f"Existing {item_kind} has no safe automatic mapping; "
                    "preserve it unless you explicitly choose a target.",
                    blocking=False,
                )
    raw_owner = adoption.get("code_owner")
    owner = raw_owner if isinstance(raw_owner, dict) else {}
    # An unverifiable (unknown) CODEOWNER is shown in Product state but is
    # not a required action: no answer can resolve it before the push.
    if owner.get("state") == "blocked":
        add(
            "code-owner",
            str(owner.get("value") or "(none)"),
            f"CODEOWNER verification is {owner.get('state')}: "
            f"{owner.get('reason', 'No details available.')}",
            blocking=True,
            command="csarc adopt --data code_owner=<@user-or-@org/team>",
        )
    raw_hook = adoption.get("project_verification_hook")
    hook = raw_hook if isinstance(raw_hook, dict) else {}
    if hook.get("result") == "failed":
        add(
            "verification",
            str(hook.get("path") or "project verification hook"),
            f"Project verification hook failed: {hook.get('reason')}",
            blocking=True,
        )
    candidate = candidate_verification_state(adoption.get("verification"))
    if plan.adoption is not None and candidate["state"] == "failed":
        add(
            "verification",
            "candidate",
            f"Candidate verification failed: {candidate['reason']}",
            blocking=True,
        )
    if plan.adoption is not None and adoption.get("verification") == (
        "not-run-dirty"
    ):
        add(
            "working-tree",
            str(plan.target),
            "Only unstaged tracked modifications that the plan preserves can "
            "be applied; commit, stash, or remove the other changes.",
            blocking=True,
        )
    if (
        plan.adoption is not None
        and adoption.get("applicable") is not True
        and adoption.get("mapping_reviewed") is not False
        and not any(action["blocking"] for action in actions)
    ):
        add(
            "verification",
            "candidate",
            "The machine plan is not applicable; candidate verification is "
            f"{adoption.get('verification', 'unknown')}.",
            blocking=True,
        )
    files = plan.files or Plan((), (), (), (), (), (), ())
    for path in files.manual:
        add(
            "file-conflict",
            path,
            "Template and repository contain different UTF-8 text; merge "
            "it manually.",
            blocking=False,
        )
    for path in files.unknown:
        add(
            "file-conflict",
            path,
            "File type, executable bit, link target, or non-text content "
            "differs; a directory, ancestor, or special-file collision is "
            "also possible.",
            blocking=False,
        )
    return actions


def update_pin_items(
    update: Mapping[str, object] | None,
) -> list[dict[str, object]] | None:
    """Return the preflight drift items recorded in an update plan."""
    preflight = (update or {}).get("action_pin_preflight")
    if not isinstance(preflight, dict):
        return None
    items = preflight.get("items")
    if not isinstance(items, list):
        return None
    return [dict(item) for item in items if isinstance(item, dict)]


CONFLICT_SIDES_DIRECTORY = "conflicts"
CONFLICT_SIDES = ("base", "current", "new")


def update_conflict_message(
    path: str, missing_ignore_rules: Sequence[str] = ()
) -> str:
    """Point one update conflict at its sides and its decision (#1147).

    An ignore-file conflict also names the template rules the current file
    lacks, so keeping it does not silently drop them (#1154 AC3).
    """
    sides = ", ".join(
        f"{CONFLICT_SIDES_DIRECTORY}/{side}/{path}" for side in CONFLICT_SIDES
    )
    message = (
        "Template and repository changes overlap in the three-way update. "
        f"Compare {sides} in this report folder (base: the recorded "
        "release's render; current: this repository; new: the target "
        "release's render; a missing file means that side has none), then "
        f"decide it with csarc update --finalize-plan --decision {path}="
        "keep-current|take-new|custom:FILE."
    )
    if missing_ignore_rules:
        message += (
            " The current file lacks these template ignore rules; "
            "keep-current leaves them out, so add the ones the project "
            "needs to a custom:FILE decision: "
            + ", ".join(missing_ignore_rules)
            + "."
        )
    return message


IGNORE_FILE_NAMES = frozenset({".gitignore"})


def ignore_rules(content: bytes | None) -> list[str]:
    """Return the non-comment, non-blank rules of one ignore file."""
    if content is None:
        return []
    rules: list[str] = []
    for line in content.decode("utf-8", errors="replace").splitlines():
        rule = line.strip()
        if rule and not rule.startswith("#"):
            rules.append(rule)
    return rules


def missing_ignore_rules(
    sides: Mapping[str, Mapping[str, bytes | None]],
) -> dict[str, list[str]]:
    """Return, per ignore-file conflict, new-side rules current lacks.

    ``keep-current`` records the current side, so these are exactly the
    template rules that decision would leave out (#1154 AC3).
    """
    result: dict[str, list[str]] = {}
    for path, contents in sides.items():
        if PurePosixPath(path).name not in IGNORE_FILE_NAMES:
            continue
        current = set(ignore_rules(contents.get("current")))
        missing = list(
            dict.fromkeys(
                rule
                for rule in ignore_rules(contents.get("new"))
                if rule not in current
            )
        )
        if missing:
            result[path] = missing
    return result


def update_ignored_payload(
    update: Mapping[str, object] | None,
) -> list[dict[str, str]]:
    """Return the hidden rendered files recorded in an update plan."""
    rows = (update or {}).get("ignored_payload")
    if not isinstance(rows, list):
        return []
    return [
        {str(key): str(value) for key, value in row.items()}
        for row in rows
        if isinstance(row, dict)
    ]


def ignored_payload_actions(
    hidden: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    """Return one blocking row per ignore file that hides rendered files."""
    by_source: dict[str, list[Mapping[str, str]]] = {}
    for row in hidden:
        by_source.setdefault(row["source"], []).append(row)
    return [
        {
            "blocking": True,
            "command": None,
            "kind": "file-conflict",
            "message": "Ignore rules hide rendered CSARC files, so the "
            f"update cannot deliver them: {ignored_text(rows)}. Except "
            "those paths in this file (in its --decision when it is a "
            "conflict), then create a new plan.",
            "subject": source,
        }
        for source, rows in sorted(by_source.items())
    ]


def update_required_actions(
    files: Plan,
    settings: Sequence[Mapping[str, object]],
    pin_items: Sequence[Mapping[str, object]] = (),
    observed: Mapping[str, object] | None = None,
    ignored: Sequence[Mapping[str, str]] = (),
    pin_versions: Mapping[
        tuple[str, int], tuple[str | None, str | None]
    ] = MappingProxyType({}),
    ignore_gaps: Mapping[str, Sequence[str]] = MappingProxyType({}),
    writer_moves: Sequence[Mapping[str, str]] = (),
    retained_uses: Sequence[Mapping[str, str]] = (),
) -> list[dict[str, object]]:
    """Derive the update required actions this release can evaluate."""
    live = {} if observed is None else observed
    actions: list[dict[str, object]] = [
        {
            "blocking": False,
            "command": f"csarc update --data {row['key']}=<value>",
            "kind": "setting-decision",
            "message": "The saved value changes without an explicit choice; "
            "confirm the new value or pass the one to keep.",
            "subject": str(row["key"]),
        }
        for row in settings
        if row["class"] == "decision" and row["source"] != "explicit"
    ]
    # A saved intent the live facts no longer suggest is only a row note
    # (#1058 decision 15, Issue #1072 AC4); live facts and contradicted
    # derived context ask for one explicit decision.
    actions.extend(
        {
            "blocking": False,
            "command": f"csarc update --data {key}=<value>",
            "kind": "setting-decision",
            "message": (
                "The native manifests do not confirm the recorded value; "
                "it is kept until you pass one explicitly."
                if key in settings_schema.DECISION_SETTINGS
                else "Live GitHub facts suggest a value that differs from "
                "the saved setting; the saved value is kept until you pass "
                "one explicitly."
            ),
            "subject": key,
        }
        for key in sorted(live)
        if key not in settings_schema.INTENT_SETTINGS
    )
    actions.extend(
        {
            "blocking": True,
            "command": None,
            "kind": "file-conflict",
            "message": update_conflict_message(path, ignore_gaps.get(path, ())),
            "subject": path,
        }
        for path in files.manual
    )
    actions.extend(ignored_payload_actions(ignored))
    actions.extend(release_writer_actions(writer_moves))
    actions.extend(
        {
            "blocking": False,
            "command": None,
            "kind": "file-conflict",
            "message": "File type, link target, or a directory collision "
            "differs from the new release; inspect it before updating.",
            "subject": path,
        }
        for path in files.unknown
    )
    actions.extend(
        {
            "blocking": True,
            "command": None,
            "kind": "action-pin",
            "message": f"Product workflow pins {item['action']}@"
            f"{item['old_sha']}; the new template pins {item['new_sha']} "
            f"({item['reason']}; "
            + action_pin_preflight.version_note(
                *pin_versions.get(
                    (str(item["file"]), cast(int, item["line"])),
                    (None, None),
                )
            )
            + "). Commit that pin change, then create a new plan.",
            "subject": f"{item['file']}:{item['line']}",
        }
        for item in pin_items
        if item.get("reason") != action_pin_preflight.REASON_PRODUCT_PIN_NEWER
    )
    actions.extend(
        {
            "blocking": False,
            "command": None,
            "kind": "action-pin",
            "message": f"Product workflow keeps {item['action']}@"
            f"{item['old_sha']}, newer than the template pin "
            f"{item['new_sha']} in the same major release "
            f"({item['reason']}); the update aligns the template workflows "
            "to the product pin.",
            "subject": f"{item['file']}:{item['line']}",
        }
        for item in pin_items
        if item.get("reason") == action_pin_preflight.REASON_PRODUCT_PIN_NEWER
    )
    actions.extend(reviewer_assignment_actions(files, settings))
    uses = retained_uses_by_script(retained_uses)
    actions.extend(
        retained_use_action(path, uses[path])
        if path in uses
        else {
            "blocking": False,
            "command": None,
            "kind": "retire-modified",
            "message": "The new release no longer renders this file, but it "
            "differs from the trusted old render; it is kept. Delete it "
            "yourself once its changes are no longer needed.",
            "subject": path,
        }
        for path in files.retained
    )
    return actions


def reviewer_assignment_actions(
    files: Plan, settings: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    """Ask the owner to confirm the reviewer assignment change (#1157).

    Retiring ``reviewers`` or ``.github/REVIEWERS`` changes who reviews
    pull requests. The setting row stays ``retired`` and its note explains
    the new behavior; this row asks the owner to confirm it, the way a
    ``widened`` row needs an explicit owner decision.
    """
    key = governance_migration.REVIEWERS_KEY
    path = governance_migration.REVIEWERS_FILE
    retired = [
        row
        for row in settings
        if row["key"] == key and row["class"] == "retired"
    ]
    if not retired and path not in {
        *files.remove,
        *files.delete,
        *files.retained,
    }:
        return []
    before = retired[0]["before"] if retired else None
    return [
        {
            "blocking": False,
            "command": None,
            "kind": "setting-decision",
            "message": "Reviewer assignment changes and the owner must "
            "confirm it before --finalize-plan: "
            + governance_migration.reviewers_note(before).removeprefix(
                "Retired; "
            ),
            "subject": key,
        }
    ]


def retained_uses_by_script(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, list[Mapping[str, str]]]:
    """Group the recorded retained-script uses by the retained script."""
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["script"], []).append(row)
    return grouped


def retained_use_action(
    path: str, uses: Sequence[Mapping[str, str]]
) -> dict[str, object]:
    """Return the blocking row for a kept script the plan would break."""
    used = ", ".join(
        f"{row['path']} -> {row['destination']}"
        if row["destination"]
        else f"{row['path']} (removed)"
        for row in uses
    )
    return {
        "blocking": True,
        "command": None,
        "kind": "retire-modified",
        "message": "The new release no longer renders this script, but it "
        "differs from the trusted old render, so it is kept. It still runs "
        f"or reads files this update removes or moves: {used}, so it would "
        "fail after the update. Delete it, or change it in a product commit "
        "so it no longer uses these paths (for example, call the "
        ".csarc/scripts/ version), then run csarc update --check again; "
        "the target was not changed.",
        "subject": path,
    }


APPLIED_NEXT_STEPS = (
    {
        "command": None,
        "text": "No plan remains to apply. Review the repository changes, "
        "then open a pull request.",
    },
)


def decidable_conflicts_only(
    actions: Sequence[Mapping[str, object]], files: Plan
) -> bool:
    """Return whether every blocking row is a planned, decidable conflict.

    Only these are resolved by ``--finalize-plan --decision`` (Issue #1147);
    any other blocking row, such as ignore rules hiding rendered files
    outside the conflicts, needs a product change and a new plan first.
    """
    blocking = [action for action in actions if action["blocking"]]
    return bool(blocking) and all(
        action["kind"] == "file-conflict" and action["subject"] in files.manual
        for action in blocking
    )


def lifecycle_next_steps(
    operation: str,
    status: str,
    *,
    applicable: bool,
    plan: ResolvedPlan,
    plan_path: Path | None,
    conflicts_only: bool = False,
) -> list[dict[str, object]]:
    """Return the next steps for one unapplied report status."""
    if status == "current":
        return [{"command": None, "text": "No update is available."}]
    steps: list[dict[str, object]] = []
    if (
        status == "blocked"
        and operation == "update"
        and plan_path is not None
        and conflicts_only
    ):
        # Only file conflicts block: they are decided in one final plan,
        # not by editing the target (Issue #1147).
        release = (
            f"--to {plan.revision.label} --expected-sha {plan.revision.sha}"
        )
        final = plan_path.parent / final_plan.FINAL_PLAN_BASENAME
        return [
            {
                "command": f"csarc update {plan.target} {release} "
                "--finalize-plan --decision "
                "PATH=keep-current|take-new|custom:FILE",
                "text": "Decide every blocking file conflict in one final "
                "plan, with one --decision per conflict and any --data "
                "options used for this plan:",
            },
            {
                "command": f"csarc update {plan.target} --apply-plan {final}",
                "text": "Review the final plan, then apply it exactly as "
                "recorded:",
            },
        ]
    if status == "blocked":
        return [
            {
                "command": None,
                "text": "Do not apply this plan. Resolve the blocking items, "
                "then create a new plan.",
            }
        ]
    if status == "review-required":
        steps.append(
            {
                "command": None,
                "text": "Resolve each item under Items requiring your "
                "decision; an answer given with --data needs a new plan.",
            }
        )
    if operation == "adopt" and applicable and plan_path is not None:
        finalize = " --finalize" if plan.mode == "adopt-finalize" else ""
        steps.append(
            {
                "command": f"csarc adopt{finalize} --apply-plan {plan_path}",
                "text": "Apply exactly this reviewed machine plan:",
            }
        )
    elif operation == "update":
        steps.append(
            {
                "command": f"csarc update {plan.target} --to "
                f"{plan.revision.label} --expected-sha {plan.revision.sha}",
                "text": "Apply the same reviewed release, repeating any "
                "--data options used for this plan:",
            }
        )
    return steps


RISK_CONTROLS_PATH = ".csarc/scripts/risk_controls.py"


def risk_behavior_changes(files: Plan) -> list[dict[str, object]] | None:
    """Report the SPEC-010 gate an update starts enforcing (#1079)."""
    if RISK_CONTROLS_PATH not in files.add:
        return None
    return [
        {
            "subject": "risk-controls",
            "before": "Ready pull requests are not checked for risk controls",
            "after": (
                "Ready pull requests require the linked Issue to carry a "
                "valid risk-controls block and every acceptance criterion "
                "and risk to map to exact-head evidence (SPEC-010)"
            ),
            "note": (
                "Run csarc risk suggest --open to list open Issues without "
                "one; there is no grace period."
            ),
        }
    ]


def lifecycle_report_model(  # noqa: C901
    plan: ResolvedPlan,
    *,
    operation: str,
    plan_name: str,
    plan_sha256: str,
    generated_at: str,
    plan_path: Path | None = None,
    before: Mapping[str, object] | None = None,
    explicit: Collection[str] = (),
    previous: Revision | None = None,
    target_head: str | None = None,
    target_changes: Sequence[str] | None = None,
    observed: Mapping[str, object] | None = None,
    pin_versions: Mapping[
        tuple[str, int], tuple[str | None, str | None]
    ] = MappingProxyType({}),
    ignore_gaps: Mapping[str, Sequence[str]] = MappingProxyType({}),
) -> dict[str, object]:
    """Build the single SPEC-008 report object for one adopt or update plan.

    Every other report output (Markdown, terminal summaries) derives from
    this object; it is validated before it is returned.
    """
    files = plan.files or Plan((), (), (), (), (), (), ())
    adoption = plan.adoption
    preserved_dirty: Collection[str] = ()
    if adoption is not None:
        raw_preserved = adoption.get("preserved_dirty_paths")
        if isinstance(raw_preserved, list):
            preserved_dirty = {str(path) for path in raw_preserved}
    settings = report_setting_rows(
        plan.answers,
        before if operation == "update" else None,
        explicit,
        observed if operation == "update" else None,
    )
    setup = plan.setup if operation == "adopt" else None
    if setup is not None:
        settings = setup_setting_rows(settings, setup)
    if operation == "update":
        violations = governance_migration.governance_row_violations(settings)
        if violations:
            raise CliError(
                "Governance settings changed outside the approved migration "
                "mapping (" + ", ".join(violations) + "); pass an explicit "
                "--data value for each key and create a new plan."
            )
    file_rows = report_file_rows(
        files,
        preserved_dirty,
        update=operation == "update" and adoption is None,
    )
    if operation == "adopt" or adoption is not None:
        actions = adoption_required_actions(plan)
        actions.extend(setup_decision_actions(setup, plan.answers))
    else:
        actions = update_required_actions(
            files,
            settings,
            update_pin_items(plan.update) or (),
            observed=observed,
            ignored=update_ignored_payload(plan.update),
            pin_versions=pin_versions,
            ignore_gaps=ignore_gaps,
            writer_moves=update_release_writer_moves(plan.update),
            retained_uses=update_retained_uses(plan.update),
        )
    if adoption is not None:
        applicable = adoption.get("applicable") is True
    else:
        applicable = not any(action["blocking"] for action in actions)
    has_changes = any(
        row["action"] not in {"preserve"} for row in file_rows
    ) or any(row["class"] != "unchanged" for row in settings)
    if plan.update is not None:
        has_changes = plan.update.get("update_available") is True
    status = lifecycle_report.derive_status(
        operation, actions, has_changes=has_changes
    )
    if status == "blocked":
        applicable = False
    reasons = {
        "blocked": "At least one blocking item must be resolved before a "
        "new plan can be applied.",
        "current": "The repository already matches the selected release.",
        "ready": "No known file conflicts; semantic and runtime conflicts "
        "remain possible.",
        "review-required": "Answer the listed decisions before relying on "
        "this plan.",
    }
    head = target_head
    changes: object = None if target_changes is None else list(target_changes)
    working_tree: str | None = None
    if adoption is not None:
        head = cast(str | None, adoption.get("target_head"))
        raw_changes = adoption.get("target_changes")
        changes = list(raw_changes) if isinstance(raw_changes, list) else None
        working_tree = (
            "clean"
            if adoption.get("clean")
            else (
                "dirty-preserved"
                if adoption.get("applicable") is True
                else "dirty-review-only"
            )
        )
    elif target_changes is not None:
        working_tree = "clean" if not target_changes else "dirty-review-only"
    owner: dict[str, object] | None = None
    mapping: dict[str, object] | None = None
    hook: dict[str, object] | None = None
    candidate: dict[str, object] | None = None
    if adoption is not None:
        raw_owner = adoption.get("code_owner")
        if isinstance(raw_owner, dict):
            owner = {
                key: raw_owner.get(key) for key in ("reason", "state", "value")
            }
        raw_mapping = adoption.get("work_item_mapping")
        if isinstance(raw_mapping, dict) and raw_mapping:
            mapping = dict(raw_mapping)
        candidate = candidate_verification_state(adoption.get("verification"))
        raw_hook = adoption.get("project_verification_hook")
    else:
        raw_hook = (plan.update or {}).get("project_verification_hook")
    if isinstance(raw_hook, dict):
        hook = {
            key: raw_hook.get(key)
            for key in ("configured", "path", "reason", "result")
        }
    render_parity: dict[str, object] | None = None
    planning = (plan.update or {}).get("planning")
    if isinstance(planning, dict):
        render_parity = {"state": planning.get("render_parity")}
    report: dict[str, object] = {
        "applicable": applicable,
        "applied_at": None,
        "files": file_rows,
        "final_plan": None,
        "generated_at": generated_at,
        "next_steps": lifecycle_next_steps(
            operation,
            status,
            applicable=applicable,
            plan=plan,
            plan_path=plan_path,
            conflicts_only=decidable_conflicts_only(actions, files),
        ),
        "operation": operation,
        "plan": {
            "mode": plan.mode,
            "path": plan_name,
            "replayable": operation == "adopt",
            "schema_version": plan.as_dict()["schema_version"],
            "sha256": plan_sha256,
        },
        "product": {
            "action_pins": update_pin_items(plan.update)
            if operation == "update" and adoption is None
            else None,
            "behavior_changes": risk_behavior_changes(files)
            if operation == "update" and adoption is None
            else None,
            "code_owner": owner,
            "release_ownership": release_contract(plan.answers),
            "release_writers": None,
            "reviewer_rotation": None,
            "version_surfaces": None,
            "work_item_mapping": mapping,
        },
        "release": {
            "from": None
            if previous is None
            else {
                "sha": previous.sha,
                "tag": previous.label,
                "verification": "verified"
                if previous.verified
                else "unverified",
            },
            "source": plan.revision.source,
            "to": {
                "guide_url": plan.revision.guide_url,
                "sha": plan.revision.sha,
                "tag": plan.revision.label,
                "verification": "verified"
                if plan.revision.verified
                else "unverified",
            },
        },
        "report_format_version": LIFECYCLE_REPORT_FORMAT_VERSION,
        "required_actions": actions,
        "settings": settings,
        "setup": None
        if setup is None
        else {
            "approval_route": setup.get("approval_route"),
            "questions": setup.get("questions", []),
            "warnings": setup.get("warnings", []),
            "work_mode": setup.get("work_mode"),
        },
        "status": status,
        "status_reason": reasons[status],
        "summary": lifecycle_report.summary_counts(
            settings, file_rows, actions
        ),
        "target": {
            "changes": changes,
            "head": head,
            "path": str(plan.target),
            "repository": plan.repository.repository,
            "visibility": plan.repository.visibility,
            "visibility_source": plan.repository.source,
            "working_tree": working_tree,
        },
        "verification": {
            "candidate": candidate,
            "hook": hook,
            "render_parity": render_parity,
        },
    }
    redacted = cast(dict[str, object], redact(report))
    try:
        lifecycle_report.validate_report(redacted)
    except lifecycle_report.LifecycleReportError as error:
        raise CliError(f"Lifecycle report is invalid: {error}") from error
    return redacted


def lifecycle_report_directory(
    target: Path, requested: Path | None, operation: str
) -> Path:
    """Resolve a report directory that cannot dirty the target repository."""
    label = "adoption" if operation == "adopt" else "update"
    directory = (
        Path(os.path.abspath(requested.expanduser()))
        if requested is not None
        else target.parent / f"{target.name}-csarc-{label}-report"
    )
    if directory == target or target in directory.parents:
        raise CliError(
            f"{label.capitalize()} reports must be written outside the "
            "target repo."
        )
    return directory


def adoption_report_directory(target: Path, requested: Path | None) -> Path:
    """Resolve the adoption report directory outside the target."""
    return lifecycle_report_directory(target, requested, "adopt")


def applied_report_directory(
    target: Path, plan_path: Path, requested: Path | None
) -> Path:
    """Return the replayed plan's directory for the applied report rewrite.

    The applied report must replace the report the user reviewed beside the
    plan, never a report in another directory.
    """
    directory = plan_path.parent
    if (
        requested is not None
        and adoption_report_directory(target, requested).resolve() != directory
    ):
        raise CliError(
            "--report-dir must match the directory of the applied plan; the "
            "applied report is written beside that plan."
        )
    return directory


def remove_legacy_adoption_report(root: Path, relative_directory: Path) -> None:
    """Delete a 1.1.0 Markdown report so one directory holds one report.

    Only a regular file is removed, through a no-follow directory
    descriptor; a symlink or special file is kept and reported (#529, #716).
    """
    relative_name = (
        relative_directory / LEGACY_ADOPTION_REPORT_NAME
    ).as_posix()
    with atomic_parent_directory(root, relative_name) as (directory_fd, name):
        try:
            mode = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(mode.st_mode):
            print(
                "Warning: kept non-regular legacy report "
                f"{root / relative_name}.",
                file=sys.stderr,
            )
            return
        os.unlink(name, dir_fd=directory_fd)


def write_lifecycle_reports(
    directory: Path,
    *,
    operation: str,
    plan_name: str,
    plan_payload: Mapping[str, object] | None,
    report: Mapping[str, object],
    emit: bool,
) -> tuple[Path, Path, Path]:
    """Write the machine plan, report JSON, and Markdown outside the target.

    The Markdown is rendered only from the serialized report JSON, after
    both have been validated, so no partial or divergent set is written.
    """
    basename = (
        ADOPTION_REPORT_BASENAME
        if operation == "adopt"
        else UPDATE_REPORT_BASENAME
    )
    try:
        report_text = lifecycle_report.report_json(report)
        markdown = lifecycle_report.render_markdown(json.loads(report_text))
    except lifecycle_report.LifecycleReportError as error:
        raise CliError(f"Lifecycle report is invalid: {error}") from error
    filesystem_root = Path(directory.anchor)
    relative_directory = directory.relative_to(filesystem_root)
    plan_path = directory / plan_name
    json_path = directory / f"{basename}.json"
    markdown_path = directory / f"{basename}.md"
    if plan_payload is not None:
        atomic_replace_text(
            filesystem_root,
            (relative_directory / plan_name).as_posix(),
            json.dumps(plan_payload, indent=2, sort_keys=True) + "\n",
        )
    atomic_replace_text(
        filesystem_root,
        (relative_directory / json_path.name).as_posix(),
        report_text,
    )
    atomic_replace_text(
        filesystem_root,
        (relative_directory / markdown_path.name).as_posix(),
        markdown,
    )
    if operation == "adopt":
        remove_legacy_adoption_report(filesystem_root, relative_directory)
    if emit:
        print(f"Markdown report: {markdown_path}")
        print(f"Report JSON: {json_path}")
        print(f"Machine plan: {plan_path}")
    return markdown_path, json_path, plan_path


def applied_lifecycle_report(
    report: Mapping[str, object],
    plan_sha256: str,
    applied_at: str,
    *,
    final_plan_sha256: str | None = None,
) -> dict[str, object]:
    """Mark a report applied while keeping it bound to the replayed plan."""
    try:
        return lifecycle_report.mark_applied(
            report,
            applied_at=applied_at,
            plan_sha256=plan_sha256,
            next_steps=APPLIED_NEXT_STEPS,
            final_plan_sha256=final_plan_sha256,
        )
    except lifecycle_report.LifecycleReportError as error:
        raise CliError(f"Cannot mark the report applied: {error}") from error


def adoption_plan_payload(plan: ResolvedPlan) -> dict[str, object]:
    """Return a tamper-evident plan ready for persistence."""
    payload = plan.as_dict()
    if plan.mode == "update":
        # The update stage-1 plan is a preview whose conflicts still need
        # decisions; only the final plan replays (#1067).
        payload["replayable"] = False
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode()
    payload["plan_sha256"] = hashlib.sha256(encoded).hexdigest()
    return payload


@contextmanager
def atomic_parent_directory(
    root: Path, relative_name: str
) -> Generator[tuple[int, str]]:
    """Open a relative destination's parent without following symlinks."""
    destination = checked_destination(root, relative_name)
    relative = destination.relative_to(root)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory_only = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or directory_only is None:
        raise CliError("Atomic writes require no-follow directory support.")
    directory_flags = os.O_RDONLY | directory_only | no_follow
    descriptors: list[int] = []
    try:
        directory_fd = os.open(root, directory_flags)
        descriptors.append(directory_fd)
        for part in relative.parts[:-1]:
            with suppress(FileExistsError):
                os.mkdir(part, dir_fd=directory_fd)
            child_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            descriptors.append(child_fd)
            directory_fd = child_fd
        yield directory_fd, relative.name
    except OSError as error:
        raise CliError(
            f"Cannot safely access {relative_name}: {error}"
        ) from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def check_atomic_destination(
    directory_fd: int, destination_name: str, relative_name: str
) -> None:
    """Reject a final destination that cannot be safely replaced."""
    try:
        destination_mode = os.stat(
            destination_name,
            dir_fd=directory_fd,
            follow_symlinks=False,
        ).st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISREG(destination_mode):
        raise CliError(
            "Atomic destination is a symlink or non-regular file: "
            f"{relative_name}"
        )


def create_atomic_temporary(
    directory_fd: int, destination_name: str, mode: int
) -> tuple[int, str]:
    """Create one unpredictable exclusive temporary without symlink follow."""
    file_flags = (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    for _ in range(128):
        temporary_name = f".{destination_name}.{secrets.token_hex(16)}.tmp"

        try:
            descriptor = os.open(
                temporary_name,
                file_flags,
                mode,
                dir_fd=directory_fd,
            )
        except FileExistsError:
            continue
        return descriptor, temporary_name
    raise CliError("Cannot allocate a unique atomic temporary file.")


def atomic_replace_text(
    root: Path,
    relative_name: str,
    content: str | bytes,
    *,
    mode: int = 0o600,
) -> None:
    """Replace text or bytes through no-follow descriptors."""
    temporary_name: str | None = None
    with atomic_parent_directory(root, relative_name) as (
        directory_fd,
        destination_name,
    ):
        check_atomic_destination(directory_fd, destination_name, relative_name)
        try:
            descriptor, temporary_name = create_atomic_temporary(
                directory_fd, destination_name, mode
            )

            data = (
                content
                if isinstance(content, bytes)
                else content.encode("utf-8")
            )
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(
                temporary_name,
                destination_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            temporary_name = None
            os.fsync(directory_fd)
        except OSError as error:
            raise CliError(
                f"Cannot safely replace {relative_name}: {error}"
            ) from error
        finally:
            if temporary_name is not None:
                with suppress(FileNotFoundError):
                    os.unlink(temporary_name, dir_fd=directory_fd)


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


def require_replay_authorization(
    args: argparse.Namespace,
    *,
    source: str,
    sha: str,
    verification: str,
) -> bool:
    """Require fresh authority before replaying an unreleased source."""
    unreleased = verification in {"unverified", "development-unreleased"}
    supplied = any((args.source, args.expected_sha, args.allow_unreleased))
    if not unreleased:
        if supplied:
            raise CliError(
                "Verified replay uses its saved immutable Release; do not "
                "pass --source, --expected-sha, or --allow-unreleased."
            )
        return False
    if not all((args.source, args.expected_sha, args.allow_unreleased)):
        raise CliError(
            "Unreleased replay requires this invocation to pass the saved "
            "--source, full --expected-sha, and --allow-unreleased."
        )
    if FULL_SHA.fullmatch(args.expected_sha) is None:
        raise CliError("--expected-sha must be a full 40-character commit SHA.")
    try:
        supplied_source = Path(args.source).expanduser().resolve()
        saved_source = Path(source).expanduser().resolve()
    except OSError as error:
        raise CliError(
            "Cannot resolve the unreleased template source."
        ) from error
    if (
        supplied_source != saved_source
        or args.expected_sha.lower() != sha.lower()
    ):
        raise CliError(
            "Unreleased replay source or expected SHA does not match the "
            "saved plan."
        )
    return True


def print_saved_adoption_plan(payload: dict[str, object]) -> None:
    """Display every saved field before repository-controlled code runs."""
    print("Saved adoption plan:")
    print(json.dumps(payload, indent=2, sort_keys=True))


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


def pre_verification_binding(payload: dict[str, object]) -> dict[str, object]:
    """Bind every static plan field while excluding runtime evidence."""
    binding = adoption_binding(payload)
    adoption = binding["adoption"]
    if not isinstance(adoption, dict):
        raise CliError("Adoption plan has no target state.")
    static_adoption = dict(adoption)
    static_adoption.pop("verification", None)
    hook = static_adoption.get("project_verification_hook")
    if isinstance(hook, dict):
        static_hook = dict(hook)
        static_hook.pop("reason", None)
        static_hook.pop("result", None)
        static_adoption["project_verification_hook"] = static_hook
    return {**binding, "adoption": static_adoption}


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


def code_owner_verification(  # noqa: C901
    repository: RepositoryContext, code_owner: object
) -> dict[str, str]:
    """Verify one optional user or team CODEOWNER against its repository."""
    value = "" if code_owner is None else str(code_owner)
    if not value:
        return {
            "reason": "No CODEOWNER is configured.",
            "state": "not-configured",
            "value": value,
        }
    user_match = CODE_OWNER_USER.fullmatch(value)
    team_match = CODE_OWNER_TEAM.fullmatch(value)
    if user_match is None and team_match is None:
        return {
            "reason": "Use an @user or @organization/team CODEOWNER.",
            "state": "blocked",
            "value": value,
        }
    if repository.repository is None:
        return {
            "reason": (
                "No GitHub origin or GH_REPO is available; verify the "
                "CODEOWNER after the repository is pushed."
            ),
            "state": "unknown",
            "value": value,
        }
    if user_match is not None:
        user = user_match.group(1)
        try:
            result = run(
                [
                    "gh",
                    "api",
                    f"repos/{repository.repository}/collaborators/"
                    f"{user}/permission",
                    "--jq",
                    ".permission",
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
                "reason": result.stderr.strip() or "User access is unreadable.",
                "state": "unknown",
                "value": value,
            }
        if result.stdout.strip() not in {
            "write",
            "push",
            "maintain",
            "admin",
        }:
            return {
                "reason": "User lacks repository write access.",
                "state": "blocked",
                "value": value,
            }
        return {
            "reason": "User has repository write access.",
            "state": "verified",
            "value": value,
        }

    organization, team = cast(re.Match[str], team_match).groups()
    if (
        repository.owner is None
        or organization.casefold() != repository.owner.casefold()
    ):
        return {
            "reason": (
                f"CODEOWNER organization @{organization} does not match "
                f"repository owner @{repository.owner or '(unknown)'}."
            ),
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
                ".[] | select((.slug | ascii_downcase) == "
                f'"{team.casefold()}") | .permission',
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
    permissions = {line.strip() for line in result.stdout.splitlines()}
    if not permissions:
        return {
            "reason": "Team is not attached to the target repository.",
            "state": "blocked",
            "value": value,
        }
    if not permissions.intersection({"push", "maintain", "admin"}):
        return {
            "reason": "Team lacks repository write access.",
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

    The rewritten machine plan keeps its existing ``adoption.applied``
    contract (#529); the SPEC-008 report records the applied state itself,
    bound to the approved plan digest (#1062).
    """
    if plan.adoption is None:
        raise CliError("Adoption report requires target state.")
    adoption = dict(plan.adoption)
    adoption["applied"] = True
    adoption["applied_at"] = applied_at
    return replace(plan, adoption=adoption)


def write_adoption_reports(
    plan: ResolvedPlan,
    directory: Path,
    *,
    emit: bool = True,
    approved_sha256: str | None = None,
    applied_at: str | None = None,
) -> tuple[Path, Path, Path]:
    """Write the adoption plan and its SPEC-008 report set.

    Dry-run writes the plan and an unapplied report. A successful
    ``--apply-plan`` rewrites the same set in the replayed plan's directory,
    marking the report applied and binding it to the approved plan digest.
    """
    if plan.files is None or plan.adoption is None:
        raise CliError("Adoption report requires file and target state.")
    payload = adoption_plan_payload(plan)
    plan_sha256 = approved_sha256 or str(payload["plan_sha256"])
    report = lifecycle_report_model(
        plan,
        operation="adopt",
        plan_name=ADOPTION_PLAN_BASENAME,
        plan_sha256=plan_sha256,
        generated_at=str(plan.adoption["generated_at"]),
        plan_path=directory / ADOPTION_PLAN_BASENAME,
    )
    if applied_at is not None:
        report = applied_lifecycle_report(report, plan_sha256, applied_at)
    return write_lifecycle_reports(
        directory,
        operation="adopt",
        plan_name=ADOPTION_PLAN_BASENAME,
        plan_payload=payload,
        report=report,
        emit=emit,
    )


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


def print_update_recommendation(update: dict[str, object] | None) -> None:
    """Print an optional update recommendation."""
    if update is None:
        return
    recommendation = update.get("governance_drift_recommendation")
    if isinstance(recommendation, str):
        print(f"Recommendation: {recommendation}")


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
    print_setup(plan.setup)
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
        print_group("Remove", plan.files.remove)
        print_group("Move", plan.files.move)
        print_group("Preserve", plan.files.preserve)
        print_group("Product release state (kept)", plan.files.product_owned)
        print_group("Retained modified files", plan.files.retained)
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
    print_update_recommendation(plan.update)


def print_setup(setup: Mapping[str, object] | None) -> None:
    """Print the work mode, question count, approval route, and warnings."""
    if setup is None:
        return
    questions = setup.get("questions")
    asked = questions if isinstance(questions, list) else []
    print(
        f"Work mode: {setup.get('work_mode')} (expanded into the settings "
        "above; the name is not saved)"
    )
    print(f"Setup questions asked: {len(asked)}")
    suggested = setup.get("suggested")
    if isinstance(suggested, list) and suggested:
        print("Suggested defaults used: " + ", ".join(map(str, suggested)))
    route = setup.get("approval_route")
    if isinstance(route, dict):
        confirmation = route.get("confirmation")
        print(
            f"Approval route: {route.get('state')} - {route.get('reason')}"
            + (f" (confirmed: {confirmation})" if confirmation else "")
        )
    warnings = setup.get("warnings")
    for row in warnings if isinstance(warnings, list) else []:
        if isinstance(row, dict):
            command = row.get("command")
            print(
                f"WARNING {row.get('code')} ({row.get('subject')}): "
                f"{row.get('message')}"
                + (f" Fix: {command}" if command else "")
            )


def setup_interactive(args: argparse.Namespace) -> bool:
    """Ask setup questions only on a TTY without --non-interactive/--json."""
    return (
        sys.stdin.isatty()
        and not getattr(args, "non_interactive", False)
        and not getattr(args, "json", False)
    )


def manifest_description(target: Path) -> tuple[str, str] | None:
    """Return the first product manifest description and its file."""
    readers: tuple[tuple[str, Callable[[str], object]], ...] = (
        (
            "pyproject.toml",
            lambda text: (
                tomllib.loads(text).get("project", {}).get("description")
            ),
        ),
        ("package.json", lambda text: json.loads(text).get("description")),
        (
            "Cargo.toml",
            lambda text: (
                tomllib.loads(text).get("package", {}).get("description")
            ),
        ),
    )
    for name, read in readers:
        path = target / name
        if not is_regular_file(path):
            continue
        try:
            value = read(path.read_text(encoding="utf-8"))
        except (
            OSError,
            UnicodeDecodeError,
            ValueError,
            AttributeError,
        ):
            continue
        if isinstance(value, str) and value.strip():
            return value.strip(), name
    return None


LICENSE_HOLDER = re.compile(
    r"^\s*Copyright\s+\(c\)\s+(?:\d{4}(?:-\d{4})?\s+)?(?P<holder>.+?)"
    r"(?:\.\s*All rights reserved\.)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
DISCLOSURE_POLICIES = (".github/SECURITY.md", "SECURITY.md", "docs/SECURITY.md")


def license_holder(target: Path) -> str | None:
    """Return the `Copyright (c)` holder named by an existing LICENSE."""
    path = target / "LICENSE"
    if not is_regular_file(path):
        return None
    try:
        match = LICENSE_HOLDER.search(path.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError:
        return None
    return match.group("holder").strip() if match else None


def detected_disclosure_channel(target: Path) -> str | None:
    """Return the one private channel the product's policy names, if any."""
    texts: list[str] = []
    for name in DISCLOSURE_POLICIES:
        path = target / name
        if is_regular_file(path):
            with suppress(OSError, UnicodeDecodeError):
                texts.append(path.read_text(encoding="utf-8"))
    channels = setup_plan.disclosure_channels(texts)
    return channels[0] if len(channels) == 1 else None


LANGUAGE_MANIFESTS = repository_facts.LANGUAGE_MANIFESTS


def adoption_detections(
    target: Path, explicit: Mapping[str, str]
) -> list[setup_plan.Detection]:
    """Return what adopt can detect before asking (Issue #1072 rules).

    Only values without a unique native source become questions: a missing
    manifest description, a LICENSE the plan would create, and ambiguous
    package or run-command derivations.
    """
    detections: list[setup_plan.Detection] = []
    languages = detect_languages(target)
    if "languages" in explicit:
        languages = parse_languages(explicit["languages"])
    elif "language" in explicit:
        # The legacy single key an older template still asks (SPEC-009).
        legacy = explicit["language"]
        languages = [] if legacy == "ci" else legacy.split("-")
    else:
        detections.append(
            setup_plan.Detection(
                "languages",
                languages,
                "manifests: "
                + (
                    ", ".join(
                        manifest
                        for name, manifest in LANGUAGE_MANIFESTS
                        if name in languages
                    )
                    or "none"
                ),
            )
        )
    description = manifest_description(target)
    detections.append(
        setup_plan.Detection(
            "project_description", description[0], description[1]
        )
        if description is not None
        else setup_plan.Detection(
            "project_description", None, "no manifest description", "unknown"
        )
    )
    if is_regular_file(target / "LICENSE"):
        holder = license_holder(target)
        if holder is not None:
            detections.append(
                setup_plan.Detection("copyright_holder", holder, "LICENSE")
            )
    else:
        detections.append(
            setup_plan.Detection(
                "copyright_holder",
                None,
                "no LICENSE; the plan would create one",
                "unknown",
            )
        )
    selected = languages
    # An ambiguous run command only follows an ambiguous package, so the
    # package is the one question; the command derives from the answer.
    entry = repository_facts.derive_context(target, selected).get(
        "package_name"
    )
    if entry is not None and entry["state"] == repository_facts.AMBIGUOUS:
        candidates = entry.get("candidates")
        detections.append(
            setup_plan.Detection(
                "package_name",
                None,
                "native manifests",
                "ambiguous",
                tuple(map(str, candidates))
                if isinstance(candidates, list)
                else (),
            )
        )
    return detections


def plan_setup(
    session: setup_plan.Session,
    mode: str,
    target: Path,
    explicit: Mapping[str, str],
    preset: str | None,
) -> setup_plan.SetupResult:
    """Ask the local setup questions, or fail on missing script input."""
    try:
        if mode == "init":
            result = setup_plan.plan_init(session, explicit, preset)
        else:
            result = setup_plan.plan_adopt(
                session,
                explicit,
                preset,
                adoption_detections(target, explicit),
                release_ownership=str(
                    explicit.get("release_ownership", "product-owned")
                ),
                dockerfile=is_regular_file(target / "Dockerfile"),
            )
        session.require_complete(mode)
    except setup_plan.SetupError as error:
        raise CliError(str(error)) from error
    return result


def plan_repository_setup(
    session: setup_plan.Session,
    setup: setup_plan.SetupResult,
    target: Path,
    explicit: Mapping[str, str],
    repository: RepositoryContext,
    mode: str,
) -> RepositoryContext:
    """Ask for an unresolvable repository and a public reporting channel."""
    try:
        if session.interactive and repository.repository is None:
            setup_plan.plan_repository(
                session,
                setup,
                explicit,
                resolved=False,
                visibility_known=repository.source == "explicit",
            )
            asked = setup.values.get("project_visibility")
            if isinstance(asked, str):
                repository = repository_context(target, asked)
        setup_plan.plan_security_channel(
            session,
            setup,
            explicit,
            visibility=repository.visibility,
            detected=(
                detected_disclosure_channel(target) if mode == "adopt" else None
            ),
        )
        session.require_complete(mode)
    except setup_plan.SetupError as error:
        raise CliError(str(error)) from error
    return repository


def setup_inputs(
    setup: setup_plan.SetupResult, explicit: Mapping[str, str]
) -> dict[str, object]:
    """Merge setup answers under explicit --data, in base_data's types."""
    inputs: dict[str, object] = {
        key: ",".join(map(str, value))
        if key == "languages" and isinstance(value, list)
        else value
        for key, value in setup.values.items()
    }
    inputs.update(explicit)
    return inputs


def finish_setup(
    session: setup_plan.Session,
    setup: setup_plan.SetupResult,
    data: Mapping[str, object],
    explicit: Mapping[str, str],
    repository: RepositoryContext,
    mode: str,
    args: argparse.Namespace,
) -> dict[str, object]:
    """Reject invalid combinations, run the approval preflight, and warn."""
    errors = setup_plan.invalid_combinations(data, explicit, mode=mode)
    if errors:
        raise CliError(" ".join(errors) + " Nothing was rendered or written.")
    approval: dict[str, object] | None = None
    try:
        if setup_plan.preflight_applies(data):
            state, reason = setup_plan.approval_route(
                detector_api, repository.repository, repository.owner_type
            )
            approval = setup_plan.resolve_approval(
                session,
                data,
                state,
                reason,
                confirm_second=bool(
                    getattr(args, "confirm_second_approver", False)
                ),
                confirm_copilot=bool(
                    getattr(args, "confirm_copilot_entitlement", False)
                ),
            )
    except setup_plan.SetupError as error:
        raise CliError(str(error)) from error
    facts = repository.facts
    role_fact = facts.get("permissions", {})
    plan_fact = facts.get("plan", {})
    runner_role = (
        str(role_fact.get("value"))
        if role_fact.get("state") == repository_facts.KNOWN
        else None
    )
    plan_name = (
        str(plan_fact.get("value"))
        if plan_fact.get("state") == repository_facts.KNOWN
        else None
    )
    single_writer: bool | None = None
    if (
        data.get("project_visibility") == "private"
        and plan_name == "free"
        and data.get("release_ownership") == "csarc-owned"
    ):
        single_writer = setup_plan.single_writer_observed(
            detector_api, repository.repository, repository.owner_type
        )
    warnings = setup_plan.setup_warnings(
        data,
        approval=approval,
        runner_role=runner_role,
        plan_name=plan_name,
        single_writer=single_writer,
    )
    return setup_plan.setup_record(
        setup,
        session,
        warnings=warnings,
        approval=approval,
        explicit=explicit,
    )


def confirm(args: argparse.Namespace) -> bool:
    """Require explicit approval before writing files."""
    if args.yes:
        return True
    if args.non_interactive:
        raise CliError(
            "--non-interactive requires --yes before files may change."
        )
    try:
        answer = input("Apply this plan? [y/N] ")
    except EOFError as error:
        raise CliError(
            "No confirmation could be read; pass --yes to apply without a "
            "prompt. Nothing was changed."
        ) from error
    return answer.strip().lower() in {"y", "yes"}


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
    head = run_git(
        ["git", "-C", str(target), "rev-parse", "HEAD"],
        repository=target,
        capture=True,
    ).stdout.strip()
    status = run_git(
        [
            "git",
            "-C",
            str(target),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--no-renames",
        ],
        repository=target,
        capture=True,
        neutralize_filters=True,
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
    tracked = run_git(
        [
            "git",
            "-C",
            str(target),
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--name-only",
            "--no-renames",
            "-z",
            "HEAD",
            "--",
        ],
        repository=target,
        capture=True,
        neutralize_filters=True,
    ).stdout.split("\0")
    untracked = run_git(
        [
            "git",
            "-C",
            str(target),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        repository=target,
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
    answers: dict[str, object],
    *,
    task_outputs_available: bool,
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
    if task_outputs_available and (
        managed != expected_managed or manual != expected_manual
    ):
        raise CliError(
            "Pending file classifications do not match the verified template; "
            "restart adoption from a clean commit."
        )
    if task_outputs_available:
        rendered = project_files(stage)
        for name in sorted(expected_managed):
            current = checked_destination(target, name)
            expected = rendered.get(name)
            if expected is None or file_fingerprint(
                current
            ) != file_fingerprint(expected):
                raise CliError(
                    "Managed adoption file differs from the verified "
                    f"template: {name}. Restart adoption from a clean commit."
                )
    allowed = (
        managed
        | manual
        | set(adoption_lockfiles(answers))
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
            planned.remove,
            planned.preserve,
            tuple(sorted(merges)),
            planned.manual,
            planned.unknown,
            planned.move,
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
    result = run_git(
        [
            "git",
            "clone",
            "--quiet",
            "--no-hardlinks",
            str(target),
            str(candidate),
        ],
        repository=target,
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
    difference = run_git(
        [
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
        repository=target,
        capture=True,
        check=False,
        text=False,
        neutralize_filters=True,
    )
    if difference.returncode != 0:
        detail = difference.stderr.decode(errors="replace").strip()
        raise CliError(detail or "Cannot stage tracked adoption work.")
    patch.write_bytes(difference.stdout)
    if difference.stdout:
        result = run_git(
            ["git", "-C", str(candidate), "apply", str(patch)],
            repository=candidate,
            capture=True,
            check=False,
            neutralize_filters=True,
        )
        if result.returncode != 0:
            raise CliError(
                result.stderr.strip() or "Cannot stage tracked adoption work."
            )
    untracked = run_git(
        [
            "git",
            "-C",
            str(target),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        repository=target,
        capture=True,
    ).stdout.split("\0")
    copy_candidate_files(
        target, candidate, tuple(path for path in untracked if path)
    )
    run_git(
        ["git", "-C", str(candidate), "add", "--all"],
        repository=candidate,
        neutralize_filters=True,
    )
    staged = run_git(
        ["git", "-C", str(candidate), "diff", "--cached", "--quiet"],
        repository=candidate,
        capture=True,
        check=False,
        neutralize_filters=True,
    )
    if staged.returncode == 0:
        return
    if staged.returncode != 1:
        raise CliError(
            staged.stderr.strip() or "Cannot inspect staged adoption work."
        )
    run_git(
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
        ],
        repository=candidate,
        neutralize_filters=True,
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
    target_head: str,
    work_item_mapping: dict[str, object],
    preserved_dirty_paths: tuple[str, ...] = (),
) -> tuple[Plan, dict[str, str], str, dict[str, object]]:
    """Build an exact preview candidate without executing package tooling."""
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
                    planned.manual,
                    planned.unknown,
                    target_head,
                    work_item_mapping,
                    {
                        **settings_schema.context_from(answers),
                        **(
                            {
                                "work_item_mapping_review": answers[
                                    "work_item_mapping_review"
                                ]
                            }
                            if "work_item_mapping_review" in answers
                            else {}
                        ),
                    },
                ),
            )
            verification = "deferred-manual-merge"
            hook = project_verification_evidence(
                hook_configuration,
                "not-run",
                "Manual file decisions must be completed first.",
            )
        else:
            write_provenance(
                candidate,
                revision,
                applied_at=generated_at,
                answers=answers,
            )
            verification = "pending-authorization"
            hook = project_verification_evidence(
                hook_configuration,
                "not-run",
                "Candidate verification runs only after plan approval.",
            )
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
    if not (planned.manual or planned.unknown):
        effects = predicted_lockfile_effects(target, effects, answers)
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
    patch_result = run_git(
        [
            "git",
            "diff",
            "--no-index",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "--",
            before.name,
            after.name,
        ],
        cwd=patch.parent,
        capture=True,
        check=False,
        text=False,
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
        apply_result = run_git(
            command,
            repository=target,
            capture=True,
            check=False,
            neutralize_filters=True,
        )
        if apply_result.returncode != 0:
            detail = (
                apply_result.stderr.strip()
                or "Git rejected the candidate patch."
            )
            raise CliError(detail)


def dependency_tool_environment(root: Path) -> dict[str, str]:
    """Build an isolated resolver environment without ambient credentials."""
    inherited = (
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "PATH",
        "PATHEXT",
        "RUSTUP_HOME",
        "RUSTUP_TOOLCHAIN",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
    )
    environment = {
        name: os.environ[name] for name in inherited if name in os.environ
    }
    directories = {
        "CARGO_HOME": root / "cargo",
        "COREPACK_HOME": root / "corepack",
        "HOME": root / "home",
        "PNPM_HOME": root / "pnpm",
        "UV_CACHE_DIR": root / "uv-cache",
        "XDG_CACHE_HOME": root / "xdg-cache",
        "XDG_CONFIG_HOME": root / "xdg-config",
        "XDG_DATA_HOME": root / "xdg-data",
        "XDG_STATE_HOME": root / "xdg-state",
    }
    for path in directories.values():
        path.mkdir(parents=True)
    npm_config = root / "npmrc"
    npm_config.touch()
    environment.update({name: str(path) for name, path in directories.items()})
    rustup_home = Path(
        os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup"))
    )
    if rustup_home.is_dir():
        environment["RUSTUP_HOME"] = str(rustup_home)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "NPM_CONFIG_USERCONFIG": str(npm_config),
        }
    )
    return environment


def validate_authorized_candidate_effects(
    planned: Plan, actual: Plan, answers: dict[str, object]
) -> None:
    """Reject resolver effects beyond the symbolic lockfile forecast."""
    lockfiles = set(adoption_lockfiles(answers))
    fields = (
        "add",
        "overwrite",
        "remove",
        "preserve",
        "merge",
        "manual",
        "unknown",
    )
    for field in fields:
        expected = set(getattr(planned, field)) - lockfiles
        observed = set(getattr(actual, field)) - lockfiles
        if observed != expected:
            raise CliError(
                "Authorized dependency tooling changed files outside the "
                "approved lockfile forecast; create a new adoption plan."
            )
    for name in lockfiles:
        expected = next(
            (field for field in fields if name in getattr(planned, field)),
            None,
        )
        observed = next(
            (field for field in fields if name in getattr(actual, field)),
            None,
        )
        if observed != expected and not (
            expected == "overwrite" and observed is None
        ):
            raise CliError(
                "Authorized dependency tooling did not match the approved "
                f"lockfile forecast for {name}; create a new adoption plan."
            )


def create_adoption_lockfiles(  # noqa: C901
    target: Path, answers: dict[str, object]
) -> None:
    """Create language lockfiles only after adoption is authorized."""
    languages = selected_languages(answers)
    with tempfile.TemporaryDirectory(
        prefix="csarc-dependency-tools-"
    ) as temporary:
        environment = dependency_tool_environment(Path(temporary))
        if "python" in languages:
            python_version = target / ".python-version"
            if not python_version.is_file():
                raise CliError(
                    "Cannot create uv.lock because .python-version is "
                    "missing; restore the managed file, then rerun csarc "
                    "adopt --finalize."
                )
            base_command = [
                "uv",
                "lock",
                "--python",
                python_version.read_text(encoding="utf-8").strip(),
                "--no-python-downloads",
            ]
            try:
                result = None
                if (target / "uv.lock").is_file():
                    result = run(
                        [*base_command, "--check", "--offline"],
                        cwd=target,
                        capture=True,
                        check=False,
                        env=environment,
                    )
                if result is None or result.returncode != 0:
                    result = run(
                        base_command,
                        cwd=target,
                        capture=True,
                        check=False,
                        env=environment,
                    )
            except FileNotFoundError as error:
                raise CliError(
                    "uv is required to create uv.lock; install uv, then "
                    "rerun csarc adopt --finalize."
                ) from error
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip()
                raise CliError(
                    "Cannot create uv.lock after the manifest merge; fix "
                    "pyproject.toml, then rerun csarc adopt --finalize. "
                    f"{detail}"
                )
        if "typescript" in languages:
            base_command = [
                "pnpm",
                "install",
                "--lockfile-only",
                "--ignore-scripts",
            ]
            try:
                result = None
                if (target / "pnpm-lock.yaml").is_file():
                    result = run(
                        [*base_command, "--frozen-lockfile", "--offline"],
                        cwd=target,
                        capture=True,
                        check=False,
                        env=environment,
                    )
                if result is None or result.returncode != 0:
                    result = run(
                        [*base_command, "--prefer-offline"],
                        cwd=target,
                        capture=True,
                        check=False,
                        env=environment,
                    )
            except FileNotFoundError as error:
                raise CliError(
                    "pnpm is required to create pnpm-lock.yaml; install "
                    "pnpm, then rerun csarc adopt --finalize."
                ) from error
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip()
                raise CliError(
                    "Cannot create pnpm-lock.yaml after the manifest merge; "
                    "fix package.json, then rerun csarc adopt --finalize. "
                    f"{detail}"
                )
        if "rust" in languages:
            base_command = ["cargo", "generate-lockfile"]
            try:
                result = None
                if (target / "Cargo.lock").is_file():
                    result = run(
                        [*base_command, "--locked", "--offline"],
                        cwd=target,
                        capture=True,
                        check=False,
                        env=environment,
                    )
                if result is None or result.returncode != 0:
                    result = run(
                        base_command,
                        cwd=target,
                        capture=True,
                        check=False,
                        env=environment,
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
                    "Cargo.toml, then rerun csarc adopt --finalize. "
                    f"{detail}"
                )


def authorize_adoption_candidate(
    plan: ResolvedPlan, candidate: Path
) -> ResolvedPlan:
    """Generate dependencies and verify one already-approved candidate."""
    adoption = plan.adoption
    planned = plan.files
    if adoption is None or planned is None:
        raise CliError("Adoption candidate is incomplete.")
    if adoption.get("phase") != "complete":
        return plan
    create_adoption_lockfiles(candidate, plan.answers)
    hook_configuration = project_verification_configuration(
        candidate, plan.answers
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
    raw_preserved_dirty_paths = adoption.get("preserved_dirty_paths")
    preserved_dirty_paths = tuple(
        value
        for value in (
            raw_preserved_dirty_paths
            if isinstance(raw_preserved_dirty_paths, list)
            else []
        )
        if isinstance(value, str)
    )
    candidate_files = project_files(candidate)
    target_files = project_files(plan.target)
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
    effects, artifacts = candidate_effects(candidate, plan.target, planned)
    validate_authorized_candidate_effects(planned, effects, plan.answers)
    owner = adoption.get("code_owner")
    owner_blocked = isinstance(owner, dict) and owner.get("state") == "blocked"
    updated = {
        **adoption,
        "applicable": verification == "passed"
        and not owner_blocked
        and adoption.get("mapping_reviewed") is not False,
        "artifacts": artifacts,
        "project_verification_hook": hook,
        "verification": verification,
    }
    return replace(plan, files=effects, adoption=updated)


def managed_script(root: Path, name: str) -> Path:
    """Resolve a current CSARC script or its legacy update-time location."""
    current = root / ".csarc" / "scripts" / name
    return current if current.is_file() else root / "scripts" / name


VERIFY_STEP_FAILED = "[verify-step] FAILED "


def verification_failure(lines: Sequence[str]) -> str:
    """Name the failed verify step from its output (Issue #1146 AC5).

    ``verification_step`` and the canonical verifier's error trap print a
    ``[verify-step] FAILED`` line; the first one names the step that
    stopped the run. Without one, the last output line is the best reason.
    """
    for line in lines:
        if line.startswith(VERIFY_STEP_FAILED):
            return line.removeprefix(VERIFY_STEP_FAILED).strip()
    for line in reversed(lines):
        if line.strip():
            return f"no step reported a failure; last output: {line.strip()}"
    return "no step reported a failure and the verifier printed nothing"


def run_verification_streaming(
    command: list[str],
    cwd: Path,
    environment: Mapping[str, str],
    status_fd: int,
) -> tuple[int, str]:
    """Run the verifier, echo its output, and name a failed step."""
    tail: collections.deque[str] = collections.deque(maxlen=200)
    failed: list[str] = []
    with subprocess.Popen(  # noqa: S603
        command,
        cwd=cwd,
        env=dict(environment),
        pass_fds=(status_fd,),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    ) as process:
        assert process.stdout is not None  # noqa: S101
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            text = line.rstrip("\n")
            tail.append(text)
            if text.startswith(VERIFY_STEP_FAILED) and not failed:
                failed.append(text)
        returncode = process.wait()
    return returncode, verification_failure([*failed, *tail])


def verify_project(target: Path) -> dict[str, object]:
    """Run canonical verification and one validated project hook."""
    configuration = project_verification_configuration(target)
    verify = managed_script(target, "verify")
    if not verify.is_file():
        hook = project_verification_evidence(
            configuration,
            "not-run",
            "Canonical project verification is unavailable.",
        )
        raise ProjectVerificationError(
            "Generated project is missing ./.csarc/scripts/verify "
            "(or legacy ./scripts/verify).",
            hook,
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
        returncode, failure = run_verification_streaming(
            [str(verify)], target, environment, status_fd
        )
        status_file.seek(0)
        hook_statuses = tuple(status_file.read().splitlines())
    expected_statuses = (
        ("not-run", "started", "passed")
        if project_hook is not None and returncode == 0
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
    if returncode != 0:
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
            "Canonical project verification failed before the hook ran: "
            f"{failure}",
        )
        raise ProjectVerificationError(
            f"Project verification failed: {failure}. Rerun "
            f"{verify.relative_to(target).as_posix()} in the candidate "
            "layout to see the full output.",
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
    settings = managed_script(target, "apply-repository-settings.sh")
    if not settings.is_file():
        print("Repository settings plan unavailable: script is missing.")
        return
    result = run([str(settings), "plan"], cwd=target, capture=True, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode == 0:
        return
    # Only an unidentified origin is a missing remote; any other failure
    # names its own reason (Issue #1146 AC6).
    if target_repository(target) is None:
        print(
            "Repository settings plan needs a GitHub origin remote; "
            "no settings were applied."
        )
        return
    lines = [
        line.strip()
        for line in (result.stderr or result.stdout or "").splitlines()
        if line.strip()
    ]
    reason = lines[-1].rstrip(".") if lines else "no output"
    print(
        f"Repository settings plan failed (exit {result.returncode}): "
        f"{reason}; no settings were applied."
    )


def detector_git(target: Path) -> repository_facts.Runner:
    """Return the shared detector's Git reader for one target."""

    def read(arguments: Sequence[str]) -> tuple[int, str, str]:
        result = run_git(
            ["git", "-C", str(target), *arguments],
            repository=target,
            capture=True,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr

    return read


def detector_api(arguments: Sequence[str]) -> tuple[int, str, str]:
    """Serve the shared detector's read-only GitHub requests."""
    try:
        result = run(
            ["gh", "api", "--method", "GET", *arguments],
            capture=True,
            check=False,
        )
    except FileNotFoundError:
        return 1, "", "GitHub CLI is unavailable"
    return result.returncode, result.stdout, result.stderr


def target_origin(target: Path) -> dict[str, object]:
    """Return the shared detector's origin fact for one target (#1072)."""
    return repository_facts.observe_origin(target, detector_git(target))


def target_repository(target: Path) -> str | None:
    """Return the GitHub origin of an existing target, when discoverable.

    Only a ``known`` origin identifies the target; an unknown or ambiguous
    one (no origin, several other remotes) is never guessed (#1072).
    """
    origin = target_origin(target)
    if origin["state"] != repository_facts.KNOWN:
        return None
    return repository_facts.github_slug(str(origin["value"]))


def repository_context(
    target: Path,
    explicit_visibility: str | None,
    *,
    saved_visibility: str | None = None,
) -> RepositoryContext:
    """Resolve repository owner and visibility before template rendering.

    The live facts come from the shared detector (Issue #1072) and ride on
    the context; an unobservable fact stays ``unknown`` there even when the
    render falls back to a saved, explicit, or safe default value.
    """
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
        facts = {
            "origin": target_origin(target),
            **{
                name: repository_facts.unknown(
                    "the repository identity is unknown"
                )
                for name in repository_facts.REMOTE_FACTS
            },
        }
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
            facts=facts,
        )

    observed = repository_facts.observe_repository(repository, detector_api)
    identity = observed["identity"]
    if identity["state"] == repository_facts.KNOWN:
        observed["plan"] = repository_facts.observe_plan(
            cast(Mapping[str, object], identity["value"]), detector_api
        )
    facts = {
        "origin": repository_facts.known(
            repository_facts.repository_url(repository), "origin"
        ),
        **observed,
    }
    visibility_fact = observed["visibility"]
    if (
        identity["state"] == repository_facts.KNOWN
        and visibility_fact["state"] == repository_facts.KNOWN
    ):
        value = cast(Mapping[str, object], identity["value"])
        actual_visibility = str(visibility_fact["value"])
        if (
            explicit_visibility is not None
            and explicit_visibility != actual_visibility
        ):
            raise CliError(
                "Explicit project_visibility does not match GitHub "
                f"({explicit_visibility} != {actual_visibility})."
            )
        return RepositoryContext(
            repository=str(value["repository"]),
            owner=str(value["owner"]),
            owner_type=str(value["owner_type"]),
            visibility=actual_visibility,
            source="github",
            verified=True,
            facts=facts,
        )
    failure = (
        str(identity["reason"])
        if identity["state"] != repository_facts.KNOWN
        else "GitHub returned incomplete repository metadata"
    )
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
        facts=facts,
    )


def inspect_work_item_mapping(  # noqa: C901
    repository: RepositoryContext,
    review: str = "accept-safe",
) -> dict[str, object]:
    """Suggest a conservative mapping from existing GitHub metadata."""
    if review not in {"accept-safe", "pending", "review-individually"}:
        raise CliError(
            "work_item_mapping_review must be accept-safe, pending, or "
            "review-individually."
        )
    result: dict[str, object] = {
        "defaults": [dict(item) for item in WORK_ITEM_DEFAULTS],
        "issue_type_state": "unknown",
        "issue_types": [],
        "label_state": "unknown",
        "labels": [],
        "mutation": "none",
        "review": review,
    }
    if not repository.verified or repository.repository is None:
        result.update(
            state="unknown",
            reason=(
                repository.reason
                or "GitHub repository context was not verified."
            ),
        )
        return result

    labels: list[object] = []
    label_problem = ""
    try:
        label_response = run(
            [
                "gh",
                "label",
                "list",
                "--repo",
                repository.repository,
                "--limit",
                "1000",
                "--json",
                "name,color,description",
            ],
            capture=True,
            check=False,
        )
    except FileNotFoundError:
        label_response = subprocess.CompletedProcess(
            [], 1, "", "GitHub CLI is unavailable"
        )
    if label_response.returncode != 0:
        label_state = "unavailable"
        label_problem = (
            "GitHub permissions or connectivity prevented live label "
            "inspection."
        )
    else:
        try:
            raw_labels = json.loads(label_response.stdout)
        except json.JSONDecodeError:
            raw_labels = None
        if isinstance(raw_labels, list):
            labels = raw_labels
            label_state = "available" if labels else "empty"
        else:
            label_state = "unavailable"
            label_problem = "GitHub returned invalid label metadata."
    result["label_state"] = label_state

    issue_type_nodes: list[object] = []
    owner_type = (repository.owner_type or "").casefold()
    if owner_type != "organization" or repository.owner is None:
        issue_type_state = "unsupported"
        issue_type_problem = (
            "Native Issue Types are unsupported for non-organization "
            "repositories; defaults remain fallback."
        )
    else:
        query = (
            "query($owner:String!){organization(login:$owner){"
            "issueTypes(first:100){nodes{color description isEnabled name}}}}"
        )
        try:
            response = run(
                [
                    "gh",
                    "api",
                    "graphql",
                    "-f",
                    f"query={query}",
                    "-F",
                    f"owner={repository.owner}",
                ],
                capture=True,
                check=False,
            )
        except FileNotFoundError:
            response = subprocess.CompletedProcess([], 1, "", "gh missing")
        try:
            payload = json.loads(response.stdout)
        except json.JSONDecodeError:
            payload = None
        organization = (
            payload.get("data", {}).get("organization")
            if isinstance(payload, dict)
            and isinstance(payload.get("data"), dict)
            else None
        )
        issue_types = (
            organization.get("issueTypes")
            if isinstance(organization, dict)
            else None
        )
        nodes = (
            issue_types.get("nodes") if isinstance(issue_types, dict) else None
        )
        valid_nodes = isinstance(nodes, list) and all(
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("isEnabled"), bool)
            and (
                item.get("color") is None or isinstance(item.get("color"), str)
            )
            and (
                item.get("description") is None
                or isinstance(item.get("description"), str)
            )
            for item in nodes or []
        )
        if response.returncode != 0:
            issue_type_state = "unavailable"
            issue_type_problem = (
                "GitHub permissions or connectivity prevented Issue Type "
                "inspection; defaults remain fallback."
            )
        elif not valid_nodes:
            issue_type_state = "unavailable"
            issue_type_problem = (
                "GitHub returned invalid Issue Type metadata; defaults "
                "remain fallback."
            )
        elif not nodes:
            issue_type_state = "empty"
            issue_type_problem = (
                "The organization defines no Issue Types; defaults remain "
                "fallback."
            )
        else:
            issue_type_nodes = nodes
            issue_type_state = "available"
            issue_type_problem = ""

    if label_state != "unavailable" and issue_type_state == "available":
        state = "available"
        reason = (
            "Read-only GitHub inspection completed; suggestions do not "
            "rename or delete labels."
        )
    elif label_state != "unavailable":
        state = "degraded"
        reason = f"Labels were inspected, but {issue_type_problem}"
    elif issue_type_state in {"available", "empty"}:
        state = "degraded"
        reason = f"Issue Types were inspected, but {label_problem}"
    else:
        state = "unknown"
        reason = f"{label_problem} {issue_type_problem}".strip()

    observed_types = sorted(
        (
            {
                "color": item.get("color"),
                "description": item.get("description"),
                "enabled": item.get("isEnabled"),
                "source": str(item["name"]),
            }
            for item in issue_type_nodes
            if isinstance(item, dict)
        ),
        key=lambda item: str(item["source"]).casefold(),
    )
    type_suggestions = []
    canonical_types = {"bug": "Bug", "feature": "Feature", "task": "Task"}
    for observed in observed_types:
        name = str(observed["source"])
        enabled = observed.get("enabled") is True
        target = canonical_types.get(name.casefold()) if enabled else None
        type_suggestions.append(
            {
                **observed,
                "action": (
                    "decision-required"
                    if not enabled
                    else "preserve"
                    if name in canonical_types.values()
                    else "map"
                    if target is not None
                    else "decision-required"
                ),
                "target": target,
            }
        )

    observed_labels = sorted(
        (
            {
                "color": (
                    item.get("color")
                    if isinstance(item.get("color"), str)
                    else None
                ),
                "description": (
                    item.get("description")
                    if isinstance(item.get("description"), str)
                    else None
                ),
                "source": str(item["name"]),
            }
            for item in labels
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ),
        key=lambda item: str(item["source"]).casefold(),
    )
    label_suggestions = []
    for observed in observed_labels:
        name = str(observed["source"])
        normalized = re.sub(r"[ _-]+", " ", name.strip().casefold())
        alias = WORK_ITEM_LABEL_ALIASES.get(normalized)
        canonical = name.casefold()
        if canonical in WORK_ITEM_ORTHOGONAL_LABELS:
            suggestion = {
                **observed,
                "action": "preserve" if name == canonical else "map",
                "issue_type": None,
                "pr_label": canonical,
                "target": canonical,
            }
        elif alias is not None:
            issue_type, pr_label = alias
            canonical_name = pr_label
            suggestion = {
                **observed,
                "action": ("preserve" if name == canonical_name else "map"),
                "issue_type": issue_type,
                "pr_label": pr_label,
                "target": canonical_name,
            }
        else:
            suggestion = {
                **observed,
                "action": "decision-required",
                "issue_type": None,
                "pr_label": None,
                "target": None,
            }
        label_suggestions.append(suggestion)

    result.update(
        state=state,
        reason=reason,
        issue_type_state=issue_type_state,
        issue_types=type_suggestions,
        labels=label_suggestions,
    )
    return result


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


def unavailable_capabilities(reason: str) -> dict[str, object]:
    """Return a complete fail-closed capability result."""
    unknown = {"state": "unknown", "reason": reason}
    token_permissions = {
        name: dict(unknown)
        for name in ("actions_pull_requests", "contents", "release")
    }
    return {
        "mode": "blocked",
        "reason": reason,
        "organization_policy": dict(unknown),
        "repository_setting": dict(unknown),
        "token_permissions": token_permissions,
        "effective": {"mode": "blocked", "reason": reason},
        "capabilities": token_permissions,
        "integrations": {
            "renovate": {
                "state": "fallback",
                "reason": reason,
                "next_step": (
                    "Keep GitHub Dependabot via .github/dependabot.yml "
                    "and the existing required CI/CD checks."
                ),
            }
        },
    }


def capability_preflight(
    script: Path,
    target: Path,
    revision: Revision,
    *,
    emit: bool = True,
) -> dict[str, object]:
    """Inspect capabilities with code from a verified template Release."""
    repository = target_repository(target)
    if not revision.verified:
        payload = unavailable_capabilities(
            "Capability helper is not from a verified template Release"
        )
    elif repository is None or not script.is_file():
        payload = unavailable_capabilities(
            "GitHub origin or trusted capability helper is unavailable"
        )
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


MULTI_SETTINGS = frozenset(
    key
    for key, (kind, _allowed) in settings_schema.INTENT_SETTINGS.items()
    if kind == settings_schema.MULTI and key != "languages"
)


def parse_multi_setting(key: str, value: object) -> list[str]:
    """Parse one multi-select schema 2 setting from saved or --data input."""
    if isinstance(value, list):
        parsed: object = value
    else:
        text = str(value).strip()
        try:
            parsed = json.loads(text) if text.startswith("[") else None
        except json.JSONDecodeError:
            parsed = None
        if parsed is None:
            parsed = [part.strip() for part in text.split(",") if part.strip()]
    allowed = settings_schema.INTENT_SETTINGS[key][1]
    if not isinstance(parsed, list) or any(
        not isinstance(item, str) or item not in allowed for item in parsed
    ):
        raise CliError(
            f"{key} must list only "
            + ", ".join(allowed)
            + " (comma-separated)."
        )
    return list(dict.fromkeys(parsed))


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
    unknown = sorted(set(parsed) - {"go", "python", "typescript", "rust"})
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
        # The reason is recomputed from release_ownership (SPEC-009), so the
        # hint names only the current setting, never the retired reason key.
        raise CliError(
            "Release workflow ownership is incomplete. This is a "
            "release_ownership gap, not a provenance problem; "
            "--accept-legacy does not resolve it. Pass "
            "--data release_ownership=csarc-owned|product-owned|"
            "verification-only to choose the one release owner."
        )
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


CSARC_RELEASE_WORKFLOW = ".github/workflows/release.yml"
CSARC_RELEASE_MIGRATION: dict[str, object] = {
    "release_immutable_releases": "required",
    "release_ownership": "csarc-owned",
    "release_ownership_reason": (
        "CSARC owns the only version policy and GitHub Release workflow."
    ),
    "release_required_inputs": [],
    "release_settings_owner": "csarc-admin",
    "release_workflow": CSARC_RELEASE_WORKFLOW,
}


def legacy_release_writer(
    target: Path,
    source: str,
    old_sha: str,
    answers: Mapping[str, object],
) -> str | None:
    """Return the sole Release writer when the old template generated it.

    A legacy existing-mode repository without a saved release owner is
    derived as product-owned when it has one release-writing workflow. If
    that workflow is byte-identical to the old template's own (non-Jinja)
    workflow, CSARC wrote it, so it is not product release machinery
    (Issue #1083). Anything else, or an unreadable source, returns None and
    keeps the product-owned derivation.
    """
    workflow = answers.get("release_workflow")
    if (
        answers.get("project_mode") != "existing"
        or answers.get("release_ownership") != "product-owned"
        or not isinstance(workflow, str)
        or not workflow.startswith(".github/workflows/")
    ):
        return None
    path = target / workflow
    if path.is_symlink() or not path.is_file():
        return None
    try:
        _config, files = action_pin_preflight.read_template_source(
            lambda command: run_git(command, capture=True, check=False),
            source,
            old_sha,
        )
    except action_pin_preflight.PinPreflightError:
        return None
    legacy = files.get(PurePosixPath(workflow).name)
    try:
        current = path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None
    return workflow if legacy is not None and legacy == current else None


def implicit_release_owner(
    target: Path,
    candidate: Mapping[str, object],
    saved: Mapping[str, object],
    explicit: Mapping[str, str],
) -> dict[str, object] | None:
    """Return the release answers derived without an explicit owner.

    A legacy repository that never saved ``release_ownership`` derives its
    owner from repository evidence, and the legacy-writer migration reads
    that derivation. An explicit ``--data release_ownership`` must not
    hide it: confirming the derived ``csarc-owned`` value otherwise
    selected the legacy writer itself and retired both release workflows
    (Issue #1146 AC1). ``None`` means the evidence derives no owner.
    """
    implicit = dict(candidate)
    if "release_ownership" not in saved and "release_ownership" in explicit:
        implicit.pop("release_ownership", None)
    try:
        return resolve_release_answers(target, implicit)
    except CliError:
        return None


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
            or (str(writers[0]["path"]) if len(writers) == 1 else "")
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
                "CSARC owns the only version policy and GitHub Release "
                "workflow."
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
    target: Path, mode: str, values: Mapping[str, object]
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
        # Older templates still ask the single legacy `language`; a schema 2
        # template ignores it and never saves it (SPEC-009).
        "language": "-".join(detected_languages) or "ci",
        "languages": detected_languages,
        "code_owner": DEFAULT_OWNER,
    }
    if mode == "adopt":
        data["coverage_mode"] = "diff"
    data.update(values)
    code_owner = data.get("code_owner")
    if not isinstance(code_owner, str) or (
        code_owner
        and CODE_OWNER_USER.fullmatch(code_owner) is None
        and CODE_OWNER_TEAM.fullmatch(code_owner) is None
    ):
        raise CliError(
            "code_owner must use an @user or @organization/team value, "
            "or be empty."
        )
    if "languages" in values:
        data["languages"] = parse_languages(str(values["languages"]))
    if "language" in values and "languages" not in values:
        legacy = str(values["language"])
        data["languages"] = [] if legacy == "ci" else legacy.split("-")
    if "package_name" not in values:
        data["package_name"] = (
            str(data["project_slug"]).replace("-", "_").replace(".", "_")
        )
    if mode == "adopt":
        data.update(adoption_derived_context(target, data, values))
    return resolve_release_answers(target, data)


def adoption_derived_context(
    target: Path, data: Mapping[str, object], values: Mapping[str, object]
) -> dict[str, object]:
    """Return the derived context an adoption renders (Issue #1072).

    Only an explicit ``--data`` value counts as recorded; the slug default
    is a fallback the native manifests replace when they resolve one value
    and several candidates fail closed until one is passed.
    """
    context = {
        key: value
        for key, value in data.items()
        if key not in settings_schema.DECISION_SETTINGS or key in values
    }
    derived, _differences = resolve_derived_context(
        target, context, explicit_decisions(values)
    )
    return derived


def adoption_decisions(
    target: Path, answers: Mapping[str, object]
) -> dict[str, object]:
    """Return the one-time decisions an adoption saves (SPEC-009, #1072).

    A derived value is saved only when the native manifests cannot choose
    it alone: several candidates, or an explicit value the manifests
    contradict. The rule reads only the target and the plan answers, so a
    dry run, its apply, and the finalize step save the same decisions.
    """
    languages = sorted(selected_languages(dict(answers)))
    decisions: dict[str, object] = {}
    package = repository_facts.derive_context(target, languages).get(
        "package_name"
    )
    for key in ("package_name", "project_run_command"):
        entry = (
            package
            if key == "package_name"
            else repository_facts.derive_context(target, languages, decisions)[
                "project_run_command"
            ]
        )
        value = answers.get(key)
        if entry is None or not isinstance(value, str):
            continue
        if entry["state"] == repository_facts.AMBIGUOUS or (
            entry["state"] == repository_facts.KNOWN and entry["value"] != value
        ):
            decisions[key] = value
    return decisions


def default_security_reporting_channel(repository_url: str) -> str:
    """Return the template's repository-derived public reporting channel."""
    return (
        f"Open a GitHub Issue at {repository_url}/issues/new; "
        "maintainers receive notifications for new Issues."
    )


def require_clean_repository(target: Path) -> None:
    """Require an existing repository with no tracked or untracked changes."""
    inside = run_git(
        ["git", "-C", str(target), "rev-parse", "--is-inside-work-tree"],
        repository=target,
        capture=True,
        check=False,
    )
    if inside.returncode != 0:
        raise CliError(f"{target} must be an existing Git repository.")
    status = run_git(
        [
            "git",
            "-C",
            str(target),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--no-renames",
        ],
        repository=target,
        capture=True,
        neutralize_filters=True,
    )
    if status.stdout.strip():
        raise CliError("Git working tree must be clean before adopt or update.")


def resolve_repository_target(path: Path) -> Path:
    """Resolve any path inside one Git worktree to its root."""
    candidate = path.expanduser().resolve()
    result = run_git(
        ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
        repository=candidate,
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
    if mode == "init" and not repository_target_is_new(target):
        raise CliError(
            "init target must not exist, must be empty, or must be an empty "
            "Git repository (only .git, no commit or tracked file)."
        )
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
    if args.to is not None:
        raise CliError(
            "adopt --finalize uses the release label saved by the pending "
            "adoption; do not pass --to."
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
        report_directory = applied_report_directory(
            target, plan_path, args.report_dir
        )
    else:
        report_directory = adoption_report_directory(target, args.report_dir)

    pending, answers_path, pending_target_head = (
        validate_pending_adoption_identity(target)
    )
    raw_template = cast(dict[str, object], pending["template"])
    raw_repository = cast(dict[str, object], pending["repository"])
    source = cast(str, raw_template.get("source"))
    release = cast(str, raw_template.get("release"))
    sha = cast(str, raw_template.get("sha"))
    verification = cast(str, raw_template.get("verification"))
    allow_unreleased = require_replay_authorization(
        args,
        source=source,
        sha=sha,
        verification=verification,
    )

    pending_context = pending.get("render_context")
    finalize_answers = read_copier_answers(answers_path)
    if isinstance(pending_context, dict):
        # Schema 2 saves no seed or live fact; replay the checkpoint's
        # resolved render context (SPEC-009, Issue #1071).
        finalize_answers = {**pending_context, **finalize_answers}
    answers = resolve_release_answers(target, finalize_answers)
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

    raw_work_item_mapping = pending.get("work_item_mapping")
    review = answers.get(
        "work_item_mapping_review",
        "accept-safe" if raw_work_item_mapping is None else "pending",
    )
    if not isinstance(review, str):
        raise CliError("work_item_mapping_review must be a string.")
    current_mapping = inspect_work_item_mapping(repository, review)
    if isinstance(raw_work_item_mapping, dict):
        if current_mapping != raw_work_item_mapping:
            raise CliError(
                "GitHub work-item metadata drifted after adoption started; "
                "restart adoption with a new dry-run plan."
            )
        work_item_mapping = raw_work_item_mapping
    else:
        work_item_mapping = current_mapping

    milestone_plan: MilestoneDescriptionPlan | None = None
    if saved is not None:
        raw_saved_adoption = saved.get("adoption")
        if not isinstance(raw_saved_adoption, dict) or not isinstance(
            raw_saved_adoption.get("generated_at"), str
        ):
            raise CliError("Finalize plan has invalid target state.")
        saved_adoption = cast(dict[str, object], raw_saved_adoption)
        validate_target_snapshot(target, saved_adoption)
        print_saved_adoption_plan(saved)
        milestone_plan = milestone_description_plan(target)
        if not confirm(args):
            return 0
        validate_target_snapshot(target, saved_adoption)
        validate_repository_context(
            target,
            repository,
            explicit_visibility,
            saved_visibility=saved_visibility,
        )

    revision = resolve_revision(
        args.source if allow_unreleased else source,
        release,
        expected_sha=sha,
        allow_unreleased=allow_unreleased,
        channel=args.channel,
    )
    source_path = Path(revision.source)
    if allow_unreleased:
        if not source_path.exists():
            raise CliError(
                "Pending unreleased template source is unavailable; restore "
                "the same local source, then rerun csarc adopt --finalize."
            )
        git_commit(source_path, sha)

    with tempfile.TemporaryDirectory(prefix="csarc-finalize-") as temporary:
        temporary_root = Path(temporary)
        stage = temporary_root / "rendered"
        stage.mkdir()
        copier_copy(
            revision.source,
            revision,
            stage,
            answers,
            skip_tasks=True,
            decisions=adoption_decisions(target, answers),
        )
        preview_config_binding = copier_config_binding(stage)
        capabilities = capability_preflight(
            managed_script(stage, "release_policy.py"),
            target,
            revision,
            emit=False,
        )
        baseline = temporary_root / "baseline"
        clone_target(target, baseline)
        checkout = run_git(
            [
                "git",
                "-C",
                str(baseline),
                "checkout",
                "--quiet",
                "--detach",
                pending_target_head,
            ],
            repository=baseline,
            capture=True,
            check=False,
            neutralize_filters=True,
        )
        if checkout.returncode != 0:
            raise CliError(
                checkout.stderr.strip()
                or "Cannot reconstruct the pre-adoption repository state."
            )
        merged = apply_adoption_policies(stage, baseline)
        planned = compare_stage(
            stage, baseline, adopt=True, merged_paths=merged
        )
        manual_files = validate_pending_manual_merges(
            target,
            pending,
            answers,
            planned,
            pending_target_head,
            baseline,
        )
        validate_pending_file_sets(
            target,
            pending,
            stage,
            planned,
            answers,
            task_outputs_available=False,
        )

        if saved is None:
            generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        else:
            generated_at = str(saved_adoption["generated_at"])
        candidate = temporary_root / "candidate"
        clone_working_tree(target, candidate)
        write_provenance(
            candidate,
            revision,
            applied_at=generated_at,
            answers=answers,
        )
        checked_destination(
            candidate, PENDING_ADOPTION_FILE.as_posix()
        ).unlink()
        hook_configuration = project_verification_configuration(
            candidate, answers
        )
        validated_project_verification_hook(candidate, hook_configuration)
        hook = project_verification_evidence(
            hook_configuration,
            "not-run",
            "Candidate verification runs only after plan approval.",
        )
        candidate_verification = "pending-authorization"
        effects, artifacts = candidate_effects(
            candidate,
            target,
            Plan((), (), (), (), (), (), ()),
        )
        effects = predicted_lockfile_effects(target, effects, answers)
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
            "mapping_reviewed": review != "pending",
            "phase": "complete",
            "project_verification_hook": hook,
            "target_changes": list(changes),
            "target_files": target_files,
            "target_head": head,
            "target_status_sha256": status_sha256,
            "verification": candidate_verification,
            "work_item_mapping": work_item_mapping,
        }
        adoption["applicable"] = bool(
            adoption["applicable"] and adoption["mapping_reviewed"]
        )
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
        if saved is not None and pre_verification_binding(
            fresh_payload
        ) != pre_verification_binding(saved):
            raise CliError(
                "Repository or manual merge results drifted after finalize "
                "dry-run; create a new finalize plan."
            )
        if saved is not None:
            plan = authorize_adoption_candidate(plan, candidate)
            adoption = cast(dict[str, object], plan.adoption)
            candidate_verification = str(adoption.get("verification"))
            if candidate_verification != "passed":
                verify_path = managed_script(candidate, "verify").relative_to(
                    candidate
                )
                raw_hook = adoption.get("project_verification_hook")
                hook_reason = (
                    raw_hook.get("reason")
                    if isinstance(raw_hook, dict)
                    else None
                )
                structured_detail = (
                    f" Structured result: {hook_reason}."
                    if isinstance(hook_reason, str)
                    else ""
                )
                raise CliError(
                    "Project verification failed at "
                    f"./{verify_path.as_posix()}: {candidate_verification}."
                    + structured_detail
                    + " Review the failed step or tool output above. Pending "
                    "manual files: "
                    + ", ".join(manual_files)
                    + ". Fix the related merge or verification failure, then "
                    "rerun csarc adopt --finalize."
                )
            effects = cast(Plan, plan.files)
            raw_artifacts = adoption.get("artifacts")
            if not isinstance(raw_artifacts, dict):
                raise CliError(
                    "Verified finalize candidate has no artifact plan."
                )
            artifacts = raw_artifacts
        if args.json:
            print(
                json.dumps(
                    plan.as_dict(), sort_keys=True, separators=(",", ":")
                )
            )
        else:
            print_plan(plan)
            print(
                "Pending state: "
                + (
                    "verified; ready to finalize."
                    if saved is not None
                    else "verification awaits plan approval."
                )
            )
        if saved is None:
            milestone_plan = milestone_description_plan(
                target, emit=not args.json
            )
        if args.dry_run:
            write_adoption_reports(plan, report_directory, emit=not args.json)
            return 0
        if saved is None and not confirm(args):
            return 0
        validate_repository_context(
            target,
            repository,
            explicit_visibility,
            saved_visibility=saved_visibility,
        )
        validate_target_snapshot(target, adoption)
        shutil.rmtree(stage)
        stage.mkdir()
        copier_copy(
            revision.source,
            revision,
            stage,
            answers,
            skip_tasks=False,
            decisions=adoption_decisions(target, answers),
        )
        if copier_config_binding(stage) != preview_config_binding:
            raise CliError(
                "Copier configuration changed during the approved "
                "task-bearing render."
            )
        task_merged = apply_adoption_policies(stage, baseline)
        task_planned = compare_stage(
            stage, baseline, adopt=True, merged_paths=task_merged
        )
        validate_pending_file_sets(
            target,
            pending,
            stage,
            task_planned,
            answers,
            task_outputs_available=True,
        )
        latest_mapping = inspect_work_item_mapping(repository, review)
        if latest_mapping != work_item_mapping:
            raise CliError(
                "GitHub work-item metadata drifted during finalize; restart "
                "adoption with a new dry-run plan."
            )
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
    applied_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    write_adoption_reports(
        mark_adoption_applied(plan, applied_at),
        report_directory,
        emit=not args.json,
        approved_sha256=cast(
            str, cast(dict[str, object], saved)["plan_sha256"]
        ),
        applied_at=applied_at,
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
        planned.remove,
        planned.preserve,
        planned.merge,
        planned.manual,
        planned.unknown,
        planned.move,
    )


def preservable_dirty_paths(
    changes: Sequence[str],
    dirty_paths: Sequence[str],
    preserve: Sequence[str],
) -> tuple[str, ...]:
    """Return dirty paths an adoption may carry through unchanged.

    Only tracked, unstaged content modifications (porcelain " M") of files
    the plan already preserves qualify. Any staged, untracked, deleted, or
    type-changed entry, or a dirty path outside the preserve set, disables
    the exception for the whole working tree.
    """
    if (
        dirty_paths
        and all(change[:2] == " M" for change in changes)
        and set(dirty_paths).issubset(preserve)
    ):
        return tuple(dirty_paths)
    return ()


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
    if answers.get("documentation_mode") != "off" and not is_regular_file(
        target / "README.md"
    ):
        raise CliError(
            "Existing repositories with documentation enabled require a "
            "product-owned regular README.md before adoption. Create and "
            "commit README.md, then rerun csarc adopt, or explicitly choose "
            "--data documentation_mode=off."
        )
    review = answers.get("work_item_mapping_review", "pending")
    if not isinstance(review, str):
        raise CliError("work_item_mapping_review must be a string.")
    work_item_mapping = inspect_work_item_mapping(repository, review)
    head, changes, status_sha256 = target_state(target)
    target_files = target_file_snapshot(target)
    dirty_paths = tuple(sorted(git_changed_paths(target))) if changes else ()
    merged = apply_adoption_policies(stage, target)
    planned = compare_stage(stage, target, adopt=True, merged_paths=merged)
    preserved_dirty_paths = preservable_dirty_paths(
        changes, dirty_paths, planned.preserve
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
            head,
            work_item_mapping,
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
        and verification
        in {"passed", "deferred-manual-merge", "pending-authorization"}
        and owner["state"] != "blocked",
        "mapping_reviewed": review != "pending",
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
        "work_item_mapping": work_item_mapping,
    }
    adoption["applicable"] = bool(
        adoption["applicable"] and adoption["mapping_reviewed"]
    )
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
    if args.to is not None:
        raise CliError(
            "--apply-plan uses the release label saved by dry-run; do not "
            "pass --to."
        )
    if args.data:
        raise CliError("--apply-plan uses the answers saved by dry-run.")
    plan_path = args.apply_plan.expanduser().resolve()
    if plan_path == target or target in plan_path.parents:
        raise CliError("Adoption plans must remain outside the target repo.")
    saved = read_adoption_plan(plan_path)
    if saved.get("mode") != "adopt" or saved.get("target") != str(target):
        raise CliError("Adoption plan does not match this target repository.")
    report_directory = applied_report_directory(
        target, plan_path, args.report_dir
    )
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
        or FULL_SHA.fullmatch(sha) is None
        or not isinstance(generated_at, str)
        or verification not in {"verified", "unverified"}
    ):
        raise CliError("Adoption plan has invalid template identity.")
    verification = cast(str, verification)
    allow_unreleased = require_replay_authorization(
        args,
        source=source,
        sha=sha,
        verification=verification,
    )
    answers = {str(key): value for key, value in raw_answers.items()}
    visibility = answers.get("project_visibility")
    if not isinstance(visibility, str):
        raise CliError("Adoption plan has no project_visibility answer.")
    explicit_visibility = (
        visibility if raw_repository.get("source") == "explicit" else None
    )
    repository = repository_context(target, explicit_visibility)
    if repository.as_dict() != raw_repository:
        raise CliError(
            "Repository context changed after the plan was created or "
            "confirmed; create a new plan."
        )
    validate_target_snapshot(target, raw_adoption)
    print_saved_adoption_plan(saved)
    milestone_plan = milestone_description_plan(target)
    if not confirm(args):
        return 0
    validate_target_snapshot(target, raw_adoption)
    validate_repository_context(target, repository, explicit_visibility)
    revision = resolve_revision(
        args.source if allow_unreleased else source,
        release,
        expected_sha=sha,
        allow_unreleased=allow_unreleased,
    )
    with tempfile.TemporaryDirectory(prefix="csarc-apply-") as temporary:
        temporary_root = Path(temporary)
        preview_stage = temporary_root / "preview"
        preview_stage.mkdir()
        copier_copy(
            revision.source,
            revision,
            preview_stage,
            answers,
            skip_tasks=True,
            decisions=adoption_decisions(target, answers),
        )
        preview_config_binding = copier_config_binding(preview_stage)
        preview_candidate = temporary_root / "preview-candidate"
        rebuilt_preview = build_adoption_plan(
            preview_stage,
            preview_candidate,
            target,
            revision,
            repository,
            answers,
            raw_capabilities,
            generated_at,
        )
        saved_binding = pre_verification_binding(saved)
        preview_binding = pre_verification_binding(
            adoption_plan_payload(rebuilt_preview)
        )
        if preview_binding != saved_binding:
            differences = json_differences(saved_binding, preview_binding)
            detail = "; ".join(differences[:10])
            if len(differences) > 10:
                detail += f"; ... and {len(differences) - 10} more"
            raise CliError(
                "Repository or rendered output drifted after dry-run; create "
                f"a new adoption plan. Differing fields: {detail}"
            )
        shutil.rmtree(preview_stage)
        preview_stage.mkdir()
        stage = preview_stage
        copier_copy(
            revision.source,
            revision,
            stage,
            answers,
            skip_tasks=False,
            decisions=adoption_decisions(target, answers),
        )
        if copier_config_binding(stage) != preview_config_binding:
            raise CliError(
                "Copier configuration changed during the approved "
                "task-bearing render."
            )
        validate_target_snapshot(target, raw_adoption)
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
        fresh_adoption = fresh.adoption
        fresh_mapping = (
            fresh_adoption.get("work_item_mapping")
            if fresh_adoption is not None
            else None
        )
        saved_mapping = raw_adoption.get("work_item_mapping")
        if fresh_mapping != saved_mapping:
            differences = json_differences(
                saved_mapping,
                fresh_mapping,
                "$.adoption.work_item_mapping",
            )
            detail = "; ".join(differences[:10])
            if len(differences) > 10:
                detail += f"; ... and {len(differences) - 10} more"
            raise CliError(
                "GitHub work-item metadata drifted during the approved "
                f"task-bearing render. Differing fields: {detail}"
            )
        fresh = authorize_adoption_candidate(fresh, candidate)
        # The reviewed setup record (questions, work mode, warnings, and
        # approval route) is replayed as saved; nothing is asked again.
        saved_setup = saved.get("setup")
        fresh = replace(
            fresh,
            setup=cast(dict[str, object], saved_setup)
            if isinstance(saved_setup, dict)
            else None,
        )
        fresh_adoption = fresh.adoption
        if fresh_adoption is None or fresh_adoption.get("verification") not in {
            "passed",
            "deferred-manual-merge",
        }:
            detail = (
                fresh_adoption.get("verification", "unknown")
                if fresh_adoption is not None
                else "unknown"
            )
            raise CliError(
                f"Project verification failed after plan approval: {detail}"
            )
        if fresh_adoption.get("applicable") is not True:
            raise CliError("Rebuilt adoption candidate is not applicable.")
        artifacts = fresh_adoption.get("artifacts")
        if not isinstance(artifacts, dict):
            raise CliError("Rebuilt adoption candidate has no artifact plan.")
        print_plan(fresh)
        validate_repository_context(
            target,
            fresh.repository,
            explicit_visibility,
        )
        validate_target_snapshot(target, fresh_adoption)
        write_candidate_patch(
            candidate,
            target,
            temporary_root / "adopt.patch",
            artifacts=artifacts,
            target_snapshot=fresh_adoption,
        )

    phase = fresh_adoption.get("phase")
    if phase == "pending":
        print(
            "Adoption pending: complete the listed manual merges, then run "
            "csarc adopt --finalize."
        )
        return 1
    settings_plan(target)
    apply_milestone_description_plan(milestone_plan)
    applied_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    write_adoption_reports(
        mark_adoption_applied(fresh, applied_at),
        report_directory,
        emit=not args.json,
        approved_sha256=str(saved["plan_sha256"]),
        applied_at=applied_at,
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
    explicit_data = parse_settings_data(args.data)
    # Issue #1078: every question and every missing required input is
    # settled before the release lookup, GitHub, or Copier runs.
    session = setup_plan.Session(
        interactive=setup_interactive(args), ask=input, emit=print
    )
    setup = plan_setup(session, mode, target, explicit_data, args.preset)
    source = args.source or CANONICAL_SOURCE
    revision = resolve_revision(
        source,
        args.to,
        expected_sha=args.expected_sha,
        allow_unreleased=args.allow_unreleased,
        channel=args.channel,
    )
    if not revision.verified:
        print(
            "WARNING: --allow-unreleased bypasses release identity, "
            "immutability, attestation, and signature verification.",
            file=sys.stderr,
        )
    repository = repository_context(
        target, explicit_data.get("project_visibility")
    )
    repository = plan_repository_setup(
        session, setup, target, explicit_data, repository, mode
    )
    inputs = setup_inputs(setup, explicit_data)
    data = base_data(target, mode, inputs)
    # Init records every explicit one-time decision (SPEC-009); adoption
    # saves one only where the native manifests cannot decide (#1072), by
    # the same rule its apply and finalize steps replay.
    decisions = (
        explicit_decisions(inputs)
        if mode == "init"
        else adoption_decisions(target, data)
    )
    # The repository URL comes only from the live repository identity or an
    # explicit answer; it is never derived from code_owner (#1061).
    if (
        repository.repository is None
        and GITHUB_REPOSITORY_URL.fullmatch(
            str(inputs.get("repository_url", ""))
        )
        is None
    ):
        raise CliError(
            "No GitHub origin or GH_REPO identifies this repository; pass "
            "--data repository_url=https://github.com/owner/repository."
        )
    data["project_visibility"] = repository.visibility
    if repository.repository is not None:
        data["repository_url"] = f"https://github.com/{repository.repository}"
    setup_record = finish_setup(
        session, setup, data, explicit_data, repository, mode, args
    )
    with tempfile.TemporaryDirectory(prefix="csarc-plan-") as temporary:
        temporary_root = Path(temporary)
        stage = temporary_root / "preview"
        stage.mkdir()
        context = copier_copy(
            revision.source,
            revision,
            stage,
            data,
            skip_tasks=True,
            decisions=decisions,
        )
        reject_retired_data_for(stage, explicit_data)
        preview_files = {
            name: file_fingerprint(path)
            for name, path in project_files(stage).items()
        }
        answers: dict[str, object] = dict(data)
        answers.update(read_copier_answers(config_path(stage)))
        answers.update(context)
        capabilities = capability_preflight(
            managed_script(stage, "release_policy.py"),
            target,
            revision,
            emit=False,
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
            plan = replace(plan, setup=setup_record)
        else:
            plan = ResolvedPlan(
                mode=mode,
                target=target,
                revision=revision,
                repository=repository,
                answers=answers,
                capabilities=capabilities,
                files=compare_stage(stage, target, adopt=False),
                setup=setup_record,
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
                plan,
                adoption_report_directory(target, args.report_dir),
                emit=not args.json,
            )
        if mode == "adopt":
            milestone_description_plan(target, emit=not args.json)
        if args.dry_run or not confirm(args):
            return 0
        if mode == "init":
            approved_revision = resolve_revision(
                source,
                args.to,
                expected_sha=revision.sha,
                allow_unreleased=args.allow_unreleased,
                channel=args.channel,
            )
            if approved_revision != revision:
                raise CliError(
                    "Template revision changed after approval; review a new "
                    "plan."
                )
            validate_copy_target(target, mode, require_clean=True)
            shutil.rmtree(stage)
            stage.mkdir()
            rebound_context = copier_copy(
                approved_revision.source,
                approved_revision,
                stage,
                data,
                skip_tasks=True,
                decisions=decisions,
            )
            rebound_answers: dict[str, object] = dict(data)
            rebound_answers.update(read_copier_answers(config_path(stage)))
            rebound_answers.update(rebound_context)
            rebound_plan = ResolvedPlan(
                mode=mode,
                target=target,
                revision=approved_revision,
                repository=repository,
                answers=rebound_answers,
                capabilities=capabilities,
                files=compare_stage(stage, target, adopt=False),
                setup=setup_record,
            )
            rebound_files = {
                name: file_fingerprint(path)
                for name, path in project_files(stage).items()
            }
            if (
                rebound_plan.as_dict() != plan.as_dict()
                or rebound_files != preview_files
            ):
                raise CliError(
                    "Repository or preview render drifted after approval; "
                    "review a new plan."
                )
            preview_config_binding = copier_config_binding(stage)
            shutil.rmtree(stage)
            stage.mkdir()
            copier_copy(
                approved_revision.source,
                approved_revision,
                stage,
                data,
                skip_tasks=False,
                decisions=decisions,
            )
            if copier_config_binding(stage) != preview_config_binding:
                raise CliError(
                    "Copier configuration changed during the approved "
                    "task-bearing render."
                )
            validate_copy_target(target, mode, require_clean=True)
            # An empty directory or an empty Git repository (only `.git`,
            # no commit or tracked file) keeps its `.git` (Issue #1078).
            shutil.copytree(stage, target, symlinks=True, dirs_exist_ok=True)
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


def require_legacy_migration_flags(saved: dict[str, object] | None) -> NoReturn:
    """Raise an actionable error for a provenance record needing migration.

    Distinguishes "no provenance was ever recorded" from "a provenance
    record exists but is in an old, unverified format", since only the
    latter has a Copier source/SHA and a `verification` label worth
    naming in the error.
    """
    if saved is None:
        raise CliError(
            "Legacy repository has no verifiable provenance; review "
            "the Copier source/SHA, then pass --accept-legacy and "
            "--from-release <tag>."
        )
    raise CliError(
        "Saved provenance uses an unverified legacy format "
        f"({saved.get('verification')!r}); review the Copier "
        "source/SHA, then pass --accept-legacy and --from-release "
        "<tag> to migrate it."
    )


def legacy_commit_kind(commit: str) -> str:
    """Classify a non-full Copier revision for actionable diagnostics."""
    if release_phase.is_valid_version(commit):
        return "release tag"
    if re.fullmatch(r"[0-9a-fA-F]{7,39}", commit):
        return "short commit SHA"
    return "unsupported revision"


def legacy_commit_migration_command(commit: str) -> str:
    """Return the explicit verified-release migration command."""
    if legacy_commit_kind(commit) == "unsupported revision":
        return (
            "restore _commit to the full SHA from an immutable release, "
            "then run csarc status <path> --json"
        )
    release = commit if release_phase.is_valid_version(commit) else "<tag>"
    return (
        f"csarc update <path> --check --accept-legacy --from-release {release}"
    )


def legacy_commit_error(commit: str) -> str:
    """Explain a malformed Copier revision and its safe migration path."""
    kind = legacy_commit_kind(commit)
    if kind == "unsupported revision":
        command = legacy_commit_migration_command(commit)
        return (
            f"Copier answer _commit is {commit!r} ({kind}); expected a full "
            f"40-character commit SHA. {command}."
        )
    command = legacy_commit_migration_command(commit)
    return (
        f"Copier answer _commit is {commit!r} ({kind}); expected a full "
        "40-character commit SHA. Review the recorded template source and "
        f"revision, then run `{command}` to verify and migrate it."
    )


def legacy_commit_matches_release(commit: str, revision: Revision) -> bool:
    """Bind a legacy tag or abbreviated SHA to one verified release."""
    if release_phase.is_valid_version(commit):
        return release_phase.normalize(commit) == release_phase.normalize(
            revision.label
        )
    return bool(
        re.fullmatch(r"[0-9a-fA-F]{7,39}", commit)
        and revision.sha.startswith(commit.lower())
    )


def legacy_migration_source(
    source: str, accept_legacy: bool, from_release: str | None
) -> str:
    """Normalize a canonical GitHub alias only for explicit migration."""
    if (
        accept_legacy
        and from_release is not None
        and github_repository(source) == CANONICAL_REPOSITORY
    ):
        return CANONICAL_SOURCE
    return source


def migrate_legacy_commit(
    source: str,
    commit: str,
    saved: dict[str, object] | None,
    accept_legacy: bool,
    from_release: str | None,
    client: ReleaseClient | None,
) -> tuple[Revision, dict[str, object]]:
    """Verify and replace one legacy tag or abbreviated commit answer."""
    if saved is not None and saved.get("verification") == "verified":
        raise CliError(
            f"{legacy_commit_error(commit)} Saved verified provenance "
            "prevents legacy migration; restore _commit to its recorded "
            "commit_sha instead."
        )
    if (
        not accept_legacy
        or from_release is None
        or legacy_commit_kind(commit) == "unsupported revision"
    ):
        raise CliError(legacy_commit_error(commit))
    revision = resolve_revision(source, from_release, client=client)
    if not legacy_commit_matches_release(commit, revision):
        raise CliError(
            f"Copier answer _commit {commit!r} does not match verified "
            f"release {from_release!r} at {revision.sha}."
        )
    return revision, {
        "commit_sha": revision.sha,
        "release_tag": from_release,
        "repository": revision.source,
        "verification": "legacy-unverified",
    }


RAW_COPIER_UPDATE_NEXT_COMMAND = (
    "restore the files the raw copier update changed (for example "
    "git restore --source=HEAD --staged --worktree -- .), then run "
    "csarc update <path> --check"
)


def raw_copier_update_detail(
    target: Path, commit: str, saved: Mapping[str, object] | None
) -> str | None:
    """Detect a state only a raw `copier update` produces (#1058 d19).

    Raw `copier update` is unsupported: it moves the Copier answers
    ``_commit`` past the release CSARC recorded and can leave rejection
    files. Detection is never reported as a successful migration; the only
    supported entry point is ``csarc update``.
    """
    recorded = None if saved is None else saved.get("commit_sha")
    if (
        isinstance(recorded, str)
        and FULL_SHA.fullmatch(recorded) is not None
        and FULL_SHA.fullmatch(commit) is not None
        and recorded.lower() != commit.lower()
    ):
        return (
            "Detected an unsupported raw `copier update`: the Copier answers "
            f"record _commit {commit}, but CSARC provenance records "
            f"{recorded}. CSARC did not migrate or verify this state. "
            f"Next: {RAW_COPIER_UPDATE_NEXT_COMMAND}."
        )
    rejections = sorted(
        name for name in project_files(target) if name.endswith(".rej")
    )
    if rejections:
        return (
            "Detected Copier rejection files from an unsupported raw "
            "`copier update` (" + ", ".join(rejections[:5]) + "). CSARC did "
            "not migrate or verify this state. Next: "
            f"{RAW_COPIER_UPDATE_NEXT_COMMAND}."
        )
    return None


def current_revision(  # noqa: C901
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
    saved = read_provenance(target)
    raw_update = raw_copier_update_detail(target, commit, saved)
    if raw_update is not None:
        raise CliError(raw_update)
    source = legacy_migration_source(source, accept_legacy, from_release)
    if FULL_SHA.fullmatch(commit) is None:
        return migrate_legacy_commit(
            source,
            commit,
            saved,
            accept_legacy,
            from_release,
            client,
        )
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

    # Saved provenance predating the current schema (for example the
    # "development-unreleased" shape an unverified adopt/update used to
    # write) is present but was never fully verified, so it must not be
    # graded against the strict `required` fields below; that check is
    # reserved for a record that already claims to be "verified" but has
    # drifted (a corruption/tampering signal, not a format migration). Both
    # "absent" and "present but legacy format" require the same explicit
    # human-authorized escape hatch, and are re-verified identically against
    # the requested release once accepted.
    if saved is None or saved.get("verification") != "verified":
        if not accept_legacy or from_release is None:
            require_legacy_migration_flags(saved)
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
    channel: str = "stable",
) -> tuple[dict[str, object], Revision, Revision, dict[str, object] | None]:
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
    source = previous_revision.source
    target_revision = resolve_revision(
        source,
        requested,
        expected_sha=expected_sha,
        allow_unreleased=allow_unreleased,
        client=client,
        channel=channel,
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
    return status, previous_revision, target_revision, previous


def repository_target_is_new(target: Path) -> bool:
    """Return whether a target is unwritten (Issue #1078 AC4).

    A missing path, an empty directory, or a directory holding only an
    empty Git repository (``.git`` with no commit and no tracked file) is
    new. Mirrors the `init` scope check in `validate_copy_target` so the two
    functions never disagree about what counts as a brand-new project.
    """
    if not target.exists():
        return True
    if not target.is_dir():
        return False
    entries = [entry.name for entry in target.iterdir()]
    if not entries:
        return True
    if entries != [".git"] or not (target / ".git").is_dir():
        return False
    head = run_git(
        ["git", "-C", str(target), "rev-parse", "--verify", "--quiet", "HEAD"],
        repository=target,
        capture=True,
        check=False,
    )
    if head.returncode == 0:
        return False
    tracked = run_git(
        ["git", "-C", str(target), "ls-files", "-z"],
        repository=target,
        capture=True,
        check=False,
    )
    return tracked.returncode == 0 and not tracked.stdout


def run_policy_settings_check(
    script: Path, target: Path
) -> subprocess.CompletedProcess[str]:
    """Run a trusted policy inspector against one target repository."""
    if not script.is_file():
        return subprocess.CompletedProcess(
            [str(script), "check"],
            127,
            "",
            ".csarc/scripts/apply-repository-settings.sh is missing.",
        )
    return run([str(script), "check"], cwd=target, capture=True, check=False)


def trusted_policy_settings_check(
    target: Path,
    revision: Revision,
    answers: Mapping[str, object],
) -> subprocess.CompletedProcess[str]:
    """Run only a verified Release's complete policy helper closure."""
    command = ["trusted-release-policy", "check"]
    if not revision.verified:
        return subprocess.CompletedProcess(
            command,
            126,
            "",
            "Policy inspection requires a verified template Release.",
        )
    try:
        with tempfile.TemporaryDirectory(
            prefix="csarc-policy-inspection-"
        ) as temporary:
            stage = Path(temporary) / "project"
            stage.mkdir()
            copier_copy(
                revision.source,
                revision,
                stage,
                answers,
                skip_tasks=True,
            )
            # Copier never records the hidden release_ownership answer, so
            # carry the saved owner into the inspected render; a missing
            # owner stays missing and the helper fails closed (#1068).
            if "release_ownership" in answers:
                persist_release_answers(stage, answers)
            return run_policy_settings_check(
                managed_script(stage, "apply-repository-settings.sh"), target
            )
    except CliError as error:
        return subprocess.CompletedProcess(command, 126, "", str(error))


def classify_policy_check(
    result: subprocess.CompletedProcess[str],
) -> PolicyCheckResult:
    """Classify one policy-drift check without guessing at ambiguous output.

    `.csarc/scripts/apply-repository-settings.sh check` either runs its full
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


def update_next_command(
    status: Mapping[str, object],
    *,
    allow_unreleased: bool = False,
    accept_legacy: bool = False,
    from_release: str | None = None,
) -> str:
    """Return the full check -> finalize -> apply sequence (Issue #1147).

    Every stage names the resolved release and its full SHA, so a beta or a
    pinned release is never silently replaced by the latest stable one and
    `--finalize-plan` re-plans the exact release the check reviewed. The
    commands, their flags, and the default report folder follow
    docs/install.md: run from inside the target, the report sits next to it
    (Issue #1153), and check and apply carry the same ``--json`` and
    ``--yes`` as the documented sequence (Issue #1157).
    """
    flags = [
        "--to",
        str(status["target_version"]),
        "--expected-sha",
        str(status["target_sha"]),
    ]
    if from_release is not None:
        flags += ["--from-release", from_release]
    if accept_legacy:
        flags.append("--accept-legacy")
    if allow_unreleased:
        flags.append("--allow-unreleased")
    release = " ".join(flags)
    return (
        f"csarc update . {release} --check --json to preview; then "
        f"csarc update . {release} --finalize-plan "
        "--decision PATH=keep-current|take-new|custom:FILE (one per listed "
        "conflict, repeating every --data used for the check); then "
        f"csarc update . --apply-plan {UPDATE_FINAL_PLAN_HINT} --yes"
    )


def detect_install_state(
    target: Path,
    *,
    requested: str | None = None,
    expected_sha: str | None = None,
    allow_unreleased: bool = False,
    accept_legacy: bool = False,
    from_release: str | None = None,
    client: ReleaseClient | None = None,
    channel: str = "stable",
    policy_check: (
        Callable[[Path], subprocess.CompletedProcess[str]] | None
    ) = None,
) -> dict[str, object]:
    """Deterministically classify a target into one of seven install states.

    Reads the local adoption checkpoint first, then `.csarc/config.yml` (or
    legacy Copier answers), the pinned Copier revision, and `.csarc/policies/`
    drift; it never infers a state from free-form judgment, so repeated runs
    against unchanged repository state always return the same classification.
    The seven states are: `create`
    (no target yet, or an empty directory), `adopt` (an existing repository
    without CSARC configuration), `adoption-pending` (a locally authenticated
    checkpoint still needs finalize), `migrate` (legacy Copier answers need
    an explicit verified-release migration), `update` (a pinned Copier
    revision behind the resolved target release), `current` (revision and
    policy settings both match), and `policy-only-update` (revision matches
    but the live repository policy settings have drifted from
    `.csarc/policies/`).
    """
    if repository_target_is_new(target):
        return {
            "next_command": INSTALL_STATE_NEXT_COMMAND[INSTALL_STATE_CREATE],
            "reason": (
                f"{target} does not exist, is an empty directory, or is an "
                "empty Git repository."
            ),
            "state": INSTALL_STATE_CREATE,
        }
    pending_path = checked_destination(target, PENDING_ADOPTION_FILE.as_posix())
    try:
        pending_path.lstat()
    except FileNotFoundError, NotADirectoryError:
        pass
    else:
        validate_pending_adoption_identity(target)
        return {
            "next_command": INSTALL_STATE_NEXT_COMMAND[
                INSTALL_STATE_ADOPTION_PENDING
            ],
            "reason": (
                "A valid adoption checkpoint is present; adoption is not "
                "complete."
            ),
            "state": INSTALL_STATE_ADOPTION_PENDING,
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
    current = read_answer(answers_path, "_commit")
    saved = read_provenance(target)
    raw_update = raw_copier_update_detail(target, current, saved)
    if raw_update is not None:
        return {
            "next_command": RAW_COPIER_UPDATE_NEXT_COMMAND,
            "reason": raw_update,
            "state": INSTALL_STATE_MIGRATE,
        }
    if FULL_SHA.fullmatch(current) is None and (
        saved is None or saved.get("verification") != "verified"
    ):
        return {
            "next_command": legacy_commit_migration_command(current),
            "reason": legacy_commit_error(current),
            "state": INSTALL_STATE_MIGRATE,
        }
    # Schema 2 settings must match their provenance digests; an unknown
    # schema or a hand edit stops status here (Issue #1071 AC4).
    saved_settings = load_saved_settings(target)
    status, current_revision, _target_revision, _previous = update_status(
        target,
        requested,
        expected_sha=expected_sha,
        allow_unreleased=allow_unreleased,
        accept_legacy=accept_legacy,
        from_release=from_release,
        client=client,
        channel=channel,
    )
    if status["update_available"]:
        return {
            "next_command": update_next_command(
                status,
                allow_unreleased=allow_unreleased,
                accept_legacy=accept_legacy,
                from_release=from_release,
            ),
            "reason": (
                f"Copier revision {status['current_sha']} is behind "
                f"target {status['target_sha']}."
            ),
            "state": INSTALL_STATE_UPDATE,
            "update_status": status,
        }
    check_result = (
        policy_check(target)
        if policy_check is not None
        else trusted_policy_settings_check(
            target,
            current_revision,
            dict(saved_settings.answers),
        )
    )
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
                "have drifted from .csarc/policies/."
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
        channel=args.channel,
    )
    result["target"] = str(target)
    governance = governance_audit(
        target, getattr(args, "confirm_governance_baseline", None)
    )
    result["governance_baseline"] = governance["baseline"]
    result["merge_audit"] = governance["merges"]
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(f"Target: {result['target']}")
        print(f"Install state: {result['state']}")
        print(f"Reason: {result['reason']}")
        print(f"Next: {result['next_command']}")
        print_governance_audit(governance)
    return 1 if governance["blocking"] else 0


def governance_audit(  # noqa: C901
    target: Path, confirm: str | None
) -> dict[str, object]:
    """Audit default-branch merges after the governance baseline (#1073)."""
    head = run_git(
        ["git", "-C", str(target), "rev-parse", "--verify", "HEAD^{commit}"],
        repository=target,
        capture=True,
        check=False,
    )
    if head.returncode != 0:
        if confirm:
            raise CliError("No Git history exists to confirm a baseline in.")
        return {
            "baseline": {
                "result": "not-installed",
                "baseline": None,
                "reason": "the target has no Git history",
                "unresolved": [],
                "candidates": [],
            },
            "merges": {"merges": [], "blocking": [], "untraced": []},
            "blocking": False,
        }

    def git(arguments: list[str]) -> tuple[int, str]:
        completed = run_git(
            ["git", "-C", str(target), *arguments],
            repository=target,
            capture=True,
            check=False,
        )
        return completed.returncode, completed.stdout

    def api(endpoint: str) -> tuple[int, str]:
        try:
            completed = run(
                ["gh", "api", "--method", "GET", endpoint],
                capture=True,
                check=False,
            )
        except FileNotFoundError:
            return 1, "GitHub CLI is unavailable"
        if completed.returncode != 0:
            return completed.returncode, completed.stderr.strip()
        return 0, completed.stdout

    def identity() -> merge_trace.Identity | None:
        code, remote = git(["remote", "get-url", "origin"])
        name = github_repository(remote.strip()) if code == 0 else None
        if name is None:
            return None
        code, text = api(f"repos/{name}")
        try:
            payload = json.loads(text) if code == 0 else None
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        full_name, repository_id = payload.get("full_name"), payload.get("id")
        if not isinstance(full_name, str) or type(repository_id) is not int:
            return None
        return merge_trace.Identity(full_name, repository_id)

    code, remote_head = git(
        ["rev-parse", "--verify", "refs/remotes/origin/HEAD"]
    )
    ref = remote_head.strip() if code == 0 and remote_head.strip() else "HEAD"
    context = merge_trace.AuditContext(
        git,
        api,
        identity,
    )
    try:
        return merge_trace.audit(context, ref, confirm)
    except merge_trace.EvidenceError as error:
        raise CliError(str(error)) from error


def print_governance_audit(governance: Mapping[str, object]) -> None:
    """Print the baseline and every merge finding that needs attention."""
    baseline = cast(dict[str, object], governance["baseline"])
    merges = cast(dict[str, object], governance["merges"])
    print(
        f"Governance baseline: {baseline['result']} "
        f"{baseline.get('baseline') or '-'} ({baseline['reason']})"
    )
    for item in cast(list[dict[str, str]], baseline.get("unresolved") or []):
        print(f"  unresolved {item['sha']}: {item['reason']}")
    if baseline["result"] == "inconclusive":
        print(
            "  Notice: confirm one candidate with "
            "--confirm-governance-baseline <SHA>: "
            + ", ".join(cast(list[str], baseline["candidates"]))
        )
    for item in cast(list[dict[str, str]], merges["merges"]):
        if item["finding"] != "traced":
            kind = "Notice" if item["finding"] == "untraced" else "Blocking"
            print(
                f"  {kind}: merge {item['sha']} is {item['finding']} "
                f"({item['detail']})"
            )


def governance_drift_update_recommendation(
    saved_answers: Mapping[str, object], explicit_data: Mapping[str, str]
) -> str | None:
    """Explain the new default without changing an existing saved choice."""
    saved = saved_answers.get("scheduled_checks")
    legacy_off = saved_answers.get("enable_governance_drift_check") is False
    if "scheduled_checks" in explicit_data:
        return None
    if legacy_off or (
        isinstance(saved, list) and "governance-drift" not in saved
    ):
        return (
            "new projects enable the daily governance drift check by "
            "default; this update preserves the saved choice. Add "
            "governance-drift with --data scheduled_checks=... to add the "
            "scheduled workflow and its read-only checker."
        )
    return None


def migrate_simplified_settings(
    answers: Mapping[str, object], explicit_data: Mapping[str, str]
) -> dict[str, object]:
    """Map the former overlapping settings to the compact public schema."""
    migrated: dict[str, object] = {}

    # Governance keys follow the approved mapping (#1058 decision 1): saved
    # or explicit values are kept, a missing admin_bypass becomes `always`
    # (reported as widened), and every other key is equivalent or narrower.
    governance: dict[str, object] = {}
    if any(
        key not in answers and key not in explicit_data
        for key in governance_migration.GOVERNANCE_KEYS
    ):
        try:
            governance = governance_migration.legacy_governance_values(answers)
        except governance_migration.GovernanceMigrationError as error:
            if (
                "governance_mode" not in explicit_data
                and "governance_mode" not in answers
            ):
                raise CliError(str(error)) from error
            governance = governance_migration.legacy_governance_values(
                {
                    key: value
                    for key, value in answers.items()
                    if key not in governance_migration.POLICY_TOGGLES
                }
            )
    saved_features = answers.get("features")
    if isinstance(saved_features, list):
        legacy_features = [
            feature for feature in saved_features if feature != "repo-site"
        ]
        documentation_mode = (
            "template-and-content"
            if "repo-site" in saved_features
            else "content-only"
        )
    else:
        legacy_features = (
            ["docker"] if answers.get("enable_docker") is True else []
        )
        documentation_mode = "template-and-content"

    if isinstance(saved_features, list) and "repo-site" in saved_features:
        migrated["features"] = legacy_features

    defaults: dict[str, object] = {
        **governance,
        "features": legacy_features,
        "documentation_mode": documentation_mode,
        "project_license": "proprietary",
        "copyright_holder": answers.get(
            "copyright_holder", answers.get("project_name", "")
        ),
    }
    # SPEC-009 schema 2 successors of the retired keys (Issue #1071); a
    # value without an exact equivalent stops before any write.
    try:
        defaults.update(settings_schema.migrated_intent(answers))
    except settings_schema.MigrationDecisionError as error:
        successors = {"python_floor", "documentation_languages"}
        if not successors & set(explicit_data):
            raise CliError(str(error)) from error
        partial = {
            key: value
            for key, value in answers.items()
            if key
            not in {
                "python_support_mode",
                "python_min_version",
                "primary_language",
                "i18n",
                "readme_primary_language",
            }
        }
        defaults.update(settings_schema.migrated_intent(partial))
    for key, value in defaults.items():
        if key not in answers and key not in explicit_data:
            migrated[key] = value
    return migrated


def update_plan_answers(  # noqa: C901
    answers: dict[str, object],
    explicit_data: dict[str, str],
    repository: RepositoryContext,
) -> tuple[dict[str, object], dict[str, object]]:
    """Resolve update answers and Copier overrides from repository facts."""
    result = dict(answers)
    update_data: dict[str, object] = dict(explicit_data)
    migrated_settings = migrate_simplified_settings(answers, explicit_data)
    result.update(migrated_settings)
    update_data.update(migrated_settings)
    release_ownership(answers)
    release_keys = {
        "release_ownership_reason",
        "release_immutable_releases",
        "release_required_inputs",
        "release_settings_owner",
        "release_workflow",
    }
    if release_keys.intersection(explicit_data):
        raise CliError(
            "Derived release observations cannot be changed with --data; "
            "set only release_ownership and release_trigger."
        )
    requested_mode = explicit_data.get("project_mode")
    if requested_mode is not None and requested_mode != answers["project_mode"]:
        raise CliError(
            "project_mode cannot change during update because it owns the "
            "release boundary."
        )
    if "code_owner" not in answers and "code_owner" not in explicit_data:
        # Saved answers that predate code_owner were rendered with the old
        # organization default. Keep that rendered owner instead of letting
        # the new empty default silently drop CODEOWNERS (#1061); a saved or
        # explicit owner is always authoritative and never rewritten here.
        update_data["code_owner"] = LEGACY_DEFAULT_OWNER
    # Saved visibility and origin-derived settings are authoritative (#1068):
    # live GitHub facts only fill a value the answers file never recorded.
    # A differing live fact is reported by observed_setting_differences and
    # changes the saved value only through an explicit --data choice.
    if "project_visibility" not in answers:
        update_data.setdefault("project_visibility", repository.visibility)
    previous_url = answers.get("repository_url")
    if (
        repository.repository is not None
        and not previous_url
        and "repository_url" not in explicit_data
    ):
        update_data["repository_url"] = (
            f"https://github.com/{repository.repository}"
        )
    new_url = update_data.get("repository_url")
    previous_channel = answers.get("security_reporting_channel")
    if (
        isinstance(new_url, str)
        and isinstance(previous_url, str)
        and previous_url
        and new_url != previous_url
        and "security_reporting_channel" not in explicit_data
        and previous_channel == default_security_reporting_channel(previous_url)
    ):
        # The explicit URL change carries the repository-derived reporting
        # channel with it; a custom channel is never rewritten.
        update_data["security_reporting_channel"] = (
            default_security_reporting_channel(new_url)
        )
    for key, value in update_data.items():
        previous_value = answers.get(key)
        if key == "languages":
            result[key] = (
                list(value)
                if isinstance(value, list)
                else parse_languages(str(value))
            )
            update_data[key] = result[key]
        elif key in MULTI_SETTINGS:
            result[key] = parse_multi_setting(key, value)
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
    # Schema 2 stores no retired key; the old side still reads them from
    # the saved answers (Issue #1071).
    # One-time inputs such as the work-item mapping review stay available
    # to a reinstall plan but are never saved.
    for key in settings_schema.retired_keys(result):
        if key in settings_schema.ONE_TIME_INPUTS:
            continue
        result.pop(key, None)
        update_data.pop(key, None)
    return result, update_data


def codeql_entitled(repository: RepositoryContext) -> bool | None:
    """Return whether the live facts show a CodeQL entitlement, if known.

    Public repositories are entitled. Otherwise only an observed security
    capability decides; ``None`` means the detector could not observe it.
    """
    if repository.visibility == "public":
        return True
    security = repository.facts.get("security", {})
    if security.get("state") != repository_facts.KNOWN:
        return None
    features = security.get("value")
    if not isinstance(features, Mapping):
        return None
    return any(
        features.get(name) == "enabled"
        for name in ("advanced_security", "code_security")
    )


def observed_setting_differences(
    answers: Mapping[str, object],
    explicit_data: Mapping[str, str],
    repository: RepositoryContext,
) -> dict[str, object]:
    """Return live facts that differ from saved settings (#1068, #1072).

    None is written. A differing live fact is reported as a setting
    decision; a saved intent the facts no longer suggest (CodeQL after a
    visibility or entitlement change) is only a report note and stays
    ``unchanged``. Only a verified GitHub observation counts, and an
    explicit --data value for the key is the approved writer, so it is
    never reported again. A repository URL that differs is not reported
    here: it fails closed in ``require_repository_identity``.
    """
    observed: dict[str, object] = {}
    if not repository.verified or repository.source != "github":
        return observed
    saved_visibility = answers.get("project_visibility")
    visibility_changed = (
        "project_visibility" not in explicit_data
        and isinstance(saved_visibility, str)
        and saved_visibility != repository.visibility
    )
    if visibility_changed:
        observed["project_visibility"] = repository.visibility
    # The CodeQL choice is noted, never flipped, when visibility or the
    # observed entitlement changes (#1058 decision 15).
    saved_codeql = answers.get("enable_codeql")
    analyzable = bool(selected_languages(dict(answers)) & CODEQL_LANGUAGES)
    entitled = codeql_entitled(repository)
    if visibility_changed:
        suggested: bool | None = repository.visibility == "public" and (
            analyzable
        )
    elif saved_codeql is True and entitled is False:
        suggested = False
    else:
        suggested = None
    if (
        suggested is not None
        and "enable_codeql" not in explicit_data
        and isinstance(saved_codeql, bool)
        and saved_codeql != suggested
    ):
        observed["enable_codeql"] = suggested
    return observed


def require_repository_identity(
    answers: Mapping[str, object],
    explicit_data: Mapping[str, str],
    repository: RepositoryContext,
) -> None:
    """Fail closed before any write when the target is another repository.

    The URL the saved settings and provenance recorded must name the
    repository the live origin identifies (Issue #1072). A one-time
    ``--data repository_url=...`` override approves a different recorded
    URL for this plan only; it must still name the live repository. An
    unknown origin (offline, no remote) cannot contradict anything.
    """
    if repository.repository is None:
        return
    live_url = repository_facts.repository_url(repository.repository)
    override = explicit_data.get("repository_url")
    if override is not None:
        if not repository_facts.same_repository(override, live_url):
            raise CliError(
                f"--data repository_url={override} does not name the "
                f"repository the origin identifies ({live_url}); the target "
                "was not changed."
            )
        return
    recorded = answers.get("repository_url")
    if (
        isinstance(recorded, str)
        and recorded
        and not repository_facts.same_repository(recorded, live_url)
    ):
        raise CliError(
            f"The origin identifies {live_url}, but the saved settings and "
            f"provenance record {recorded}; the target was not changed. "
            "Check the origin remote, or approve the new identity for this "
            f"plan only with --data repository_url={live_url}."
        )


def resolve_derived_context(
    target: Path,
    answers: Mapping[str, object],
    decisions: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    """Resolve the derived package and run command (Issue #1072).

    Returns the values to render and the differences to report. A saved
    or explicit decision always wins. Otherwise a value the native
    manifests resolve uniquely fills a key nothing recorded; a recorded
    value the manifests contradict, or several candidates, keeps the
    recorded value and is reported until one explicit decision is passed.
    Several candidates with nothing recorded fail closed before any write,
    and an unobservable value keeps what the last render recorded.
    """
    languages = sorted(selected_languages(dict(answers)))
    derived = repository_facts.derive_context(target, languages, decisions)
    values: dict[str, object] = {}
    differences: dict[str, object] = {}
    for key, entry in derived.items():
        if key in decisions:
            continue
        recorded = answers.get(key)
        state = entry["state"]
        if state == repository_facts.KNOWN:
            if not isinstance(recorded, str) or not recorded:
                values[key] = entry["value"]
            elif recorded != entry["value"]:
                differences[key] = entry["value"]
        elif state == repository_facts.AMBIGUOUS:
            candidates = cast(list[str], entry["candidates"])
            if not isinstance(recorded, str) or not recorded:
                raise CliError(
                    f"{key} has several candidates in the native manifests "
                    f"({', '.join(candidates)}); pass --data {key}=<value> "
                    "once to decide. The target was not changed."
                )
            differences[key] = candidates
    return values, differences


def _render_reinstall_plan(
    args: argparse.Namespace,
    target: Path,
    source: str,
    candidate_answers: dict[str, object],
    repository: RepositoryContext,
    generated_at: str,
    *,
    label: str,
) -> tuple[Path, ResolvedPlan, Path, str]:
    """Render the requested revision fresh and build one adoption plan.

    Never reuses a previous render: called once for the pre-confirmation
    preview and again after confirmation, closing the plan-to-apply TOCTOU
    window. The preview skips Copier tasks, while the post-confirmation
    render runs them. Real verification is run explicitly by the caller,
    against candidate, after overwriting its answers file with the fresh
    content this function returns (see `command_update_reinstall`). Always
    resolves `args.to` -- the caller's actual requested target, not a
    hardcoded "latest" -- so an explicit `--to <tag>` is never silently
    substituted; if that same explicit target is also unavailable,
    resolving it here raises the same `ReleaseRecoveryError` again,
    uncaught, with its own specific message naming that tag.

    Returns `(temporary_root, plan, answers_relative, fresh_answers)`; the
    caller owns `temporary_root` and must remove it once done (the
    candidate lives at `temporary_root / "candidate"`).
    """
    revision = resolve_revision(
        source,
        args.to,
        expected_sha=args.expected_sha,
        allow_unreleased=args.allow_unreleased,
        channel=args.channel,
    )
    # The reinstall fallback is reachable from csarc update, so the same
    # product pin preflight runs before each of its renders (#1065).
    pins = update_action_pin_preflight(
        target, revision.source, revision.sha, candidate_answers
    )
    if pins.blocking:
        if not (args.check or args.dry_run):
            raise CliError(action_pin_preflight.drift_error(pins))
        print(action_pin_preflight.drift_error(pins), file=sys.stderr)
    temporary_root = Path(tempfile.mkdtemp(prefix=f"csarc-reinstall-{label}-"))
    stage = temporary_root / "rendered"
    stage.mkdir()
    # The resolved render context joins the answers that provenance records
    # after the reinstall applies (SPEC-009, Issue #1071).
    candidate_answers.update(
        copier_copy(
            revision.source,
            revision,
            stage,
            candidate_answers,
            skip_tasks=label == "preview",
        )
    )
    # The freshly rendered answers file legitimately differs from the
    # target's (new _commit/_src_path, possibly new answers) on every
    # ordinary reinstall -- that is expected evolution, not a conflict, so
    # it is excluded from the adopt-style diff entirely and written to
    # target directly once the rest of the patch has applied, exactly
    # like the normal (non-reinstall) update path leaves answer-file
    # merging to Copier rather than compare_stage.
    staged_answers_path = config_path(stage)
    answers_relative = staged_answers_path.relative_to(stage)
    fresh_answers = staged_answers_path.read_text(encoding="utf-8")
    staged_answers_path.unlink()
    capabilities = capability_preflight(
        stage / ".csarc" / "scripts" / "release_policy.py",
        target,
        revision,
        emit=False,
    )
    plan = build_adoption_plan(
        stage,
        temporary_root / "candidate",
        target,
        revision,
        repository,
        candidate_answers,
        capabilities,
        generated_at,
    )
    if plan.adoption is None:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise CliError("Reinstall plan has no adoption evidence.")
    return temporary_root, plan, answers_relative, fresh_answers


def command_update_reinstall(  # noqa: C901
    args: argparse.Namespace,
    target: Path,
    source: str,
    candidate_answers: dict[str, object],
    repository: RepositoryContext,
    missing: ReleaseRecoveryError,
) -> int:
    """Fall into a from-scratch reinstall plan for an unusable release.

    Triggered by a confirmed-missing release or an unsupported version
    shape. ``missing`` identifies the exact recovery reason.
    Every other verification failure keeps raising through `update_status`
    unchanged (see the `except ReleaseRecoveryError` in `command_update`).
    Reuses `csarc adopt`'s exact transactional-plan machinery (Issue #219,
    `build_adoption_plan`/`compare_stage`) so additions, overwrites,
    preserved files, and manual-merge items are categorized identically,
    and a project-owned or diverged file is never silently overwritten.

    Mirrors `command_apply_adoption_plan`/`command_finalize_adoption`'s own
    preview-then-reverify shape: a cheap, side-effect-free preview build is
    shown and gates on `--check` and on needing manual merges; only after
    the caller confirms does a second, independent render run, closing the
    plan-to-apply TOCTOU window. That second build still uses
    based on the approved preview. The fresh answers file is written into
    candidate directly and `verify_project` -- the same canonical
    `./.csarc/scripts/verify` plus validated project hook every other
    apply-to-target path in this module runs -- is invoked explicitly
    against it. A `ProjectVerificationError` there fails reinstall closed
    before anything is written to target, exactly like `adopt
    --apply-plan`/`--finalize`/`update`'s own unconditional
    `verify_project` calls already require; the generic `applicable`
    field is never trusted on its own here. A plan that needs manual merges
    is reported and left for `csarc adopt` to resolve against this same
    directory, rather than reimplementing adopt's separate
    pending/finalize replay flow a second time for this narrower recovery
    path.

    Known limitation: unlike the ordinary (non-reinstall) update path,
    which renders both the old and new revisions to tell "the template
    changed this file" apart from "the project customized this file",
    `compare_stage`'s adopt-mode categorization here is a plain two-way
    diff against the target's current content -- there is no verified old
    revision to render a three-way baseline from (the whole point of this
    path is that the old release is confirmed gone). Every file that
    differs from the newest release's render is therefore routed to
    `manual`, even one the project never touched itself. This stays safe
    (never silently overwrites anything) but can make an ordinary
    reinstall need more manual review than an equivalent up-to-date
    `csarc update` would; a future revision could add a best-effort
    three-way diff when the old commit SHA happens to still be fetchable.
    """
    target_label = args.to if args.to else "the newest available release"
    print(
        f"{missing} Attempting a reinstall targeting {target_label} "
        "instead of failing outright (Issue #918).",
        file=sys.stderr,
    )
    if not args.check:
        require_clean_repository(target)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    preview_root, preview, _preview_answers_relative, _preview_answers = (
        _render_reinstall_plan(
            args,
            target,
            source,
            candidate_answers,
            repository,
            generated_at,
            label="preview",
        )
    )
    try:
        if args.json:
            print(
                json.dumps(
                    preview.as_dict(), sort_keys=True, separators=(",", ":")
                )
            )
        else:
            print_plan(preview)
        adoption = preview.adoption
    finally:
        shutil.rmtree(preview_root, ignore_errors=True)
    if adoption is None:
        raise CliError("Reinstall plan has no adoption evidence.")
    report_directory = lifecycle_report_directory(
        target, args.report_dir, "update"
    )
    plan_payload = adoption_plan_payload(preview)
    reinstall_report = lifecycle_report_model(
        preview,
        operation="update",
        plan_name=UPDATE_PLAN_BASENAME,
        plan_sha256=str(plan_payload["plan_sha256"]),
        generated_at=generated_at,
        plan_path=report_directory / UPDATE_PLAN_BASENAME,
        before=candidate_answers,
        observed=observed_setting_differences(
            candidate_answers, {}, repository
        ),
    )
    write_lifecycle_reports(
        report_directory,
        operation="update",
        plan_name=UPDATE_PLAN_BASENAME,
        plan_payload=plan_payload,
        report=reinstall_report,
        emit=not args.json,
    )

    if args.check:
        return 1
    if adoption.get("phase") == "pending":
        print(
            "Reinstall needs manual merges before it can be applied "
            "automatically. Resolve the listed manual-merge files "
            "against this directory with csarc adopt, then rerun "
            "csarc update.",
            file=sys.stderr,
        )
        return 1
    if adoption.get("applicable") is not True:
        raise CliError("Reinstall plan is not applicable.")
    if not confirm(args):
        return 0

    # Re-render from scratch now that the caller has approved: this closes
    # the plan-to-apply TOCTOU window (matching
    # command_apply_adoption_plan/command_finalize_adoption). The fresh
    # answers file is written into candidate below and verify_project is
    # invoked explicitly against it, exactly like command_update's own
    # unconditional verify_project(candidate) call for its non-reinstall
    # path (see _render_reinstall_plan's docstring for why).
    require_clean_repository(target)
    apply_root, fresh, answers_relative, fresh_answers = _render_reinstall_plan(
        args,
        target,
        source,
        candidate_answers,
        repository,
        generated_at,
        label="apply",
    )
    try:
        fresh_adoption = fresh.adoption
        planned = fresh.files
        if fresh_adoption is None or planned is None:
            raise CliError("Reinstall plan has no adoption evidence.")
        if fresh_adoption.get("phase") == "pending":
            print(
                "Reinstall needs manual merges before it can be applied "
                "automatically (the target changed since the preview "
                "plan). Resolve the listed manual-merge files against "
                "this directory with csarc adopt, then rerun csarc "
                "update.",
                file=sys.stderr,
            )
            return 1
        owner_state = fresh_adoption.get("code_owner")
        if (
            isinstance(owner_state, dict)
            and owner_state.get("state") == "blocked"
        ):
            raise CliError(
                "Reinstall plan is not applicable: "
                f"{owner_state.get('reason', 'CODEOWNER is blocked')}"
            )
        candidate = apply_root / "candidate"
        (candidate / answers_relative).write_text(
            fresh_answers, encoding="utf-8"
        )
        try:
            verify_project(candidate)
        except ProjectVerificationError as error:
            raise CliError(
                f"Reinstall verification failed after plan approval: {error}"
            ) from error
        _effects, artifacts = candidate_effects(candidate, target, planned)
        write_candidate_patch(
            candidate,
            target,
            apply_root / "reinstall.patch",
            artifacts=artifacts,
            target_snapshot=fresh_adoption,
        )
        (target / answers_relative).write_text(fresh_answers, encoding="utf-8")
    finally:
        shutil.rmtree(apply_root, ignore_errors=True)
    write_provenance(target, fresh.revision, answers=candidate_answers)
    settings_plan(target)
    write_lifecycle_reports(
        report_directory,
        operation="update",
        plan_name=UPDATE_PLAN_BASENAME,
        plan_payload=None,
        report=applied_lifecycle_report(
            reinstall_report,
            str(plan_payload["plan_sha256"]),
            datetime.now(UTC).replace(microsecond=0).isoformat(),
        ),
        emit=True,
    )
    print("Reinstall complete.")
    return 0


OLD_SIDE_ANSWERS_HEADER = (
    "# Changes here will be overwritten by Copier; NEVER EDIT MANUALLY\n"
)


def read_raw_answers(path: Path) -> dict[str, object]:
    """Read a Copier answers file including its ``_`` metadata keys."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CliError(f"Cannot read Copier answers from {path}.") from error
    if not isinstance(payload, dict):
        raise CliError(f"Copier answers in {path} must be a mapping.")
    return {str(key): value for key, value in payload.items()}


def render_old_side(
    source: str,
    revision: Revision,
    workdir: Path,
    saved: Mapping[str, object],
    provenance: Mapping[str, object] | None,
    update_data: Mapping[str, object],
    *,
    complete: bool = False,
) -> tuple[update_plan.OldSideInputs, dict[str, object], Path]:
    """Rebuild the old template render from trusted inputs only (#1063).

    The first render records which questions the old template actually
    asks. The second render, the baseline the plan compares against, uses
    exactly the reconstructed answers plus the new-side values Copier needs
    to evaluate the new template's exclusions for keys the old template
    never asks; no current default reaches an old question. A render
    failure, or a question set that changes between the two renders, means
    a required old input is missing or untrusted; it fails closed before
    the target is touched. Returns the old-side inputs, the new-side data,
    and the baseline render.
    """

    def render(stage: Path, data: Mapping[str, object]) -> frozenset[str]:
        stage.mkdir()
        try:
            copier_copy(
                source,
                revision,
                stage,
                data,
                skip_tasks=True,
                persist_answers=False,
            )
        except CliError as error:
            raise CliError(
                f"The old template {revision.label} cannot be rebuilt from "
                f"the saved answers and trusted provenance ({error}). The "
                "target was not changed."
            ) from error
        return update_plan.asked_keys(read_copier_answers(config_path(stage)))

    if complete:
        # A schema 2 target's verified provenance context plus its saved
        # intent are exactly the answers the old render consumed (#1071);
        # its intent-only settings file cannot list the asked seeds.
        reconstructed = update_plan.OldSideInputs(
            answers=dict(sorted(saved.items())),
            sources=dict.fromkeys(saved, update_plan.OLD_SOURCE_SNAPSHOT),
            dropped=(),
        )
        new_data = update_plan.new_side_data(saved, reconstructed, update_data)
        old = reconstructed.with_context(new_data)
        baseline = workdir / "old-baseline"
        render(baseline, old.copier_answers())
        return old, new_data, baseline
    asked = render(workdir / "old-asked", saved)
    reconstructed = update_plan.reconstruct_old_inputs(
        saved, asked, update_plan.trusted_snapshot(provenance)
    )
    new_data = update_plan.new_side_data(saved, reconstructed, update_data)
    old = reconstructed.with_context(new_data)
    baseline = workdir / "old-baseline"
    try:
        update_plan.require_stable_old_inputs(
            asked, render(baseline, old.copier_answers())
        )
    except update_plan.UpdatePlanningError as error:
        raise CliError(str(error)) from error
    return old, new_data, baseline


def write_old_side_answers(
    path: Path,
    raw: Mapping[str, object],
    old: update_plan.OldSideInputs,
    *,
    commit: str,
    source: str,
) -> None:
    """Write the answers file Copier reads to rebuild the old side."""
    payload: dict[str, object] = {
        key: value for key, value in raw.items() if key.startswith("_")
    }
    payload["_commit"] = commit
    payload["_src_path"] = source
    payload.update(old.copier_answers())
    path.write_text(
        OLD_SIDE_ANSWERS_HEADER
        + yaml.safe_dump(payload, allow_unicode=True, sort_keys=True),
        encoding="utf-8",
    )


def commit_candidate(candidate: Path, message: str) -> None:
    """Commit every candidate change so Copier sees a clean destination."""
    run_git(
        ["git", "-C", str(candidate), "add", "-A"],
        repository=candidate,
        neutralize_filters=True,
    )
    run_git(
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
            "--allow-empty",
            "-m",
            message,
        ],
        repository=candidate,
        neutralize_filters=True,
    )


def staged_name_status(candidate: Path, baseline: str) -> dict[str, str]:
    """Stage the candidate and return each changed path's Git status."""
    run_git(
        ["git", "-C", str(candidate), "add", "-A"],
        repository=candidate,
        neutralize_filters=True,
    )
    output = run_git(
        [
            "git",
            "-C",
            str(candidate),
            "diff",
            "--cached",
            "--no-ext-diff",
            "--no-textconv",
            "--name-status",
            "--no-renames",
            "-z",
            baseline,
            "--",
        ],
        repository=candidate,
        capture=True,
        neutralize_filters=True,
    ).stdout
    tokens = [token for token in output.split("\0") if token]
    pairs = zip(tokens[::2], tokens[1::2], strict=True)
    return {path: status[:1] for status, path in pairs}


@dataclass(frozen=True)
class UpdateRun:
    """One Copier three-way update executed in a disposable candidate."""

    candidate: Path
    baseline_head: str
    returncode: int
    conflicts: tuple[str, ...]
    changes: dict[str, str]
    output: str
    retained: tuple[str, ...] = ()
    product_owned: tuple[str, ...] = ()
    shims: tuple[str, ...] = ()
    restored: tuple[str, ...] = ()


@dataclass(frozen=True)
class UpdateRunInputs:
    """Inputs shared verbatim by the planning run and the apply run."""

    raw_answers: Mapping[str, object]
    old_side: update_plan.OldSideInputs
    new_data: Mapping[str, object]
    old_commit: str
    source: str
    target_sha: str
    layout_moves: tuple[tuple[str, str], ...]
    retiring: tuple[str, ...]
    target_uses_current_config: bool
    # Fingerprints of the trusted old render, keyed by path (#1066).
    old_render: Mapping[str, str] = dataclass_field(default_factory=dict)
    # Every path the new release renders; none may hide behind the
    # repository's ignore rules (#1083).
    payload: tuple[str, ...] = ()
    # Kept newer product pins the template workflows adopt (#1083).
    pin_alignment: tuple[tuple[str, ...], ...] = ()
    # Rendered files Copier's update deleted although the reviewed new
    # render keeps them, as {path: [base64 content, executable]} (#1083).
    restored: Mapping[str, Sequence[object]] = dataclass_field(
        default_factory=dict
    )


def baseline_paths(candidate: Path, baseline: str) -> tuple[str, ...]:
    """Return every path the candidate's baseline commit tracks."""
    output = run_git(
        [
            "git",
            "-C",
            str(candidate),
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            baseline,
        ],
        repository=candidate,
        capture=True,
    ).stdout
    return tuple(sorted(name for name in output.split("\0") if name))


def protect_candidate_transitions(
    candidate: Path,
    baseline: str,
    inputs: UpdateRunInputs,
    early_layout_moves: tuple[tuple[str, str], ...],
    *,
    rebuild_site: bool = False,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Keep Copier inside the transitions an update may approve (#1066).

    Product release state and project-owned site content return to their
    baseline content (relocated when the layout migration moves them), and
    every Copier deletion the trusted old render cannot justify is undone.
    Both the check and the apply run call this with the same inputs. With
    ``rebuild_site`` (a run whose Copier tasks built the site from the new
    seed) the derived site is rebuilt from restored content. Returns the
    protected product paths, the retained modified paths, and the layout
    moves already completed.
    """
    tracked = baseline_paths(candidate, baseline)
    site_before = project_site_fingerprints(candidate)

    def restore(names: Sequence[str]) -> None:
        run_git(
            [
                "git",
                "-C",
                str(candidate),
                "checkout",
                baseline,
                "--",
                *names,
            ],
            repository=candidate,
            neutralize_filters=True,
        )

    product, completed = file_transition.protect_product_state(
        candidate, tracked, inputs.layout_moves, restore
    )
    if rebuild_site and project_site_fingerprints(candidate) != site_before:
        rebuild_project_site(candidate)
    skip = {
        CONFIG_FILE.as_posix(),
        LEGACY_ANSWERS_FILE.as_posix(),
        *inputs.retiring,
        *(source for source, _destination in early_layout_moves),
        *(source for source, _destination in completed),
    }
    retained = file_transition.protect_deletions(
        candidate, tracked, inputs.old_render, skip, restore
    )
    return product, retained, completed


def project_site_fingerprints(candidate: Path) -> dict[str, str | None]:
    """Fingerprint the project-owned repo-site sources in a candidate."""
    names = file_transition.project_owned_state(project_files(candidate), ())
    return {
        name: file_transition.fingerprint(candidate / name)
        for name in names
        if name.startswith(file_transition.PROJECT_SITE_CONTENT_PREFIX)
        or name in file_transition.PROJECT_SITE_FILES
    }


def rebuild_project_site(candidate: Path) -> None:
    """Rebuild the derived site after project content was put back.

    Copier's site build task ran on the new seed before the update restored
    the project's own repo-site content (Issue #1146 AC3), so the derived
    pages are built again from the content the plan keeps.
    """
    script = candidate / ".csarc/scripts/build-repo-site"
    if script.is_symlink() or not script.is_file():
        return
    result = run(
        ["bash", str(script)], cwd=candidate, capture=True, check=False
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip() or (result.stdout or "").strip()
        raise CliError(
            "Rebuilding the repo-site from the project's own site content "
            f"failed: {detail or 'unknown error'}. The target was not changed."
        )


def run_update_candidate(
    target: Path,
    workdir: Path,
    inputs: UpdateRunInputs,
    *,
    working_tree: bool,
    skip_tasks: bool,
    resolutions: Mapping[str, bytes | None] | None = None,
    stage: Path | None = None,
) -> UpdateRun:
    """Run the one shared three-way update in a disposable candidate.

    ``resolutions`` are the conflict decisions a final plan recorded
    (#1067): Copier must report exactly those conflicts, and each one is
    replaced by its recorded bytes (or removed) before anything else runs.

    Both ``update --check`` (``skip_tasks=True`` on a working-tree clone)
    and the apply path (``skip_tasks=False`` on the committed target) run
    this same function with the same :class:`UpdateRunInputs`. The old side
    Copier rebuilds comes only from the reconstructed answers file this
    function writes; current defaults and migrations reach the new side
    through the data file.
    """
    candidate = workdir / "candidate"
    if working_tree:
        clone_working_tree(target, candidate)
        if git_changed_paths(candidate):
            commit_candidate(candidate, "chore: snapshot the working tree")
    else:
        clone_target(target, candidate)
    baseline_head = run_git(
        ["git", "-C", str(candidate), "rev-parse", "HEAD"],
        repository=candidate,
        capture=True,
    ).stdout.strip()
    candidate_config_path = config_path(candidate)
    migrating_legacy_config = (
        inputs.target_uses_current_config
        and candidate_config_path == candidate / LEGACY_ANSWERS_FILE
    )
    early_layout_moves = tuple(
        move
        for move in inputs.layout_moves
        if move[0] == LEGACY_ANSWERS_FILE.as_posix()
    )
    deferred_layout_moves = tuple(
        move for move in inputs.layout_moves if move not in early_layout_moves
    )
    # Copier must see the legacy generated paths in their original
    # locations so its old-to-new comparison can remove and add them
    # cleanly. Only the answers file moves early because Copier and the
    # target template's finalize tasks need the canonical config path.
    apply_layout_moves(candidate, early_layout_moves)
    if migrating_legacy_config:
        candidate_config_path = candidate / CONFIG_FILE
    write_old_side_answers(
        candidate_config_path,
        inputs.raw_answers,
        inputs.old_side,
        commit=inputs.old_commit,
        source=inputs.source,
    )
    for name in inputs.retiring:
        # The legacy profile is superseded by CONFIG_FILE. Tool-specific
        # configs are now materialized by stable adapters at runtime.
        (candidate / name).unlink()
    if git_changed_paths(candidate):
        # Copier's own `update` refuses to run against a dirty destination,
        # so commit this filesystem-only migration first; HEAD moves back
        # to the baseline afterward so the migration and Copier's changes
        # form one diff against the repository's real prior state.
        commit_candidate(
            candidate, "chore: migrate legacy repository configuration"
        )
    data_file = workdir / "update-data.yml"
    data_file.write_text(
        yaml.safe_dump(dict(inputs.new_data), sort_keys=True),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "copier",
        "update",
        "--trust",
        "--defaults",
        "--conflict",
        "inline",
        "--vcs-ref",
        inputs.target_sha,
        "--answers-file",
        candidate_config_path.relative_to(candidate).as_posix(),
        "--data-file",
        str(data_file),
    ]
    if skip_tasks:
        command.append("--skip-tasks")
    command.append(str(candidate))
    result = run(command, capture=True, check=False)
    output = (result.stderr or "").strip() or (result.stdout or "").strip()
    restored = restore_rendered_payload(target, candidate, inputs, stage)
    product_owned, retained, completed_moves = protect_candidate_transitions(
        candidate,
        baseline_head,
        inputs,
        early_layout_moves,
        rebuild_site=not skip_tasks,
    )
    # A retained legacy source is a modified generated file the plan keeps
    # in place as a retire-modified conflict (#1066); it never moves onto
    # the destination the new release renders (#1083).
    deferred_layout_moves = effective_layout_moves(
        tuple(
            move
            for move in deferred_layout_moves
            if move not in completed_moves
        ),
        retained,
    )
    conflicts = find_conflicts(candidate)
    copier_succeeded = result.returncode == 0
    if resolutions is not None:
        # Copier reports the inline conflicts it left; once each one is
        # resolved from the plan, the run continues as a clean update.
        copier_succeeded = copier_succeeded or bool(conflicts)
        conflicts = resolve_recorded_conflicts(
            candidate, conflicts, resolutions
        )
    if copier_succeeded and not conflicts:
        # Copier normally performs clean legacy deletions and additions
        # itself. Any legacy source left behind is user-modified or
        # otherwise outside that clean update, so finish the move only when
        # it is safe and fail closed on a different destination.
        apply_layout_moves(candidate, deferred_layout_moves)
        reject_ignored_payload(candidate, inputs.payload)
    head = run_git(
        ["git", "-C", str(candidate), "rev-parse", "HEAD"],
        repository=candidate,
        capture=True,
    ).stdout.strip()
    if head != baseline_head or conflicts:
        # Move HEAD (and an index Copier may have left with unmerged
        # stages) back to the baseline without touching the working tree:
        # the migration and Copier's changes form one diff against the
        # repository's real prior state.
        run_git(
            [
                "git",
                "-C",
                str(candidate),
                "reset",
                "--quiet",
                "--mixed",
                baseline_head,
            ],
            repository=candidate,
        )
    # A rendered file stays visible to the plan even while an undecided
    # .gitignore conflict would hide it; the final candidate above already
    # failed closed if the decided ignore rules still hide it (#1083).
    action_pin_preflight.align_pins(candidate, inputs.pin_alignment)
    shims = write_compatibility_shims(
        candidate, inputs.layout_moves, retained, inputs.payload
    )
    stage_payload(candidate, inputs.payload)
    return UpdateRun(
        candidate,
        baseline_head,
        0 if copier_succeeded else result.returncode,
        conflicts,
        staged_name_status(candidate, baseline_head),
        output,
        retained,
        product_owned,
        shims,
        restored,
    )


def restore_rendered_payload(
    target: Path,
    candidate: Path,
    inputs: UpdateRunInputs,
    stage: Path | None,
) -> tuple[str, ...]:
    """Put back rendered files Copier's update deleted (Issue #1083).

    Copier lists the files an update removes before it loads every answer,
    so a file whose ``_exclude`` rule reads CLI-provided data (the migrated
    CSARC release workflow) can be deleted although the reviewed new render
    keeps it. The planning run takes such a file from that render when the
    target still holds the unmodified old render; the plan records the
    bytes and the apply run writes the same bytes.
    """
    contents: dict[str, tuple[bytes, bool]] = {}
    for name, (encoded, executable) in inputs.restored.items():
        contents[name] = (base64.b64decode(str(encoded)), bool(executable))
    if stage is not None:
        for name in inputs.payload:
            rendered = stage / name
            if (
                name in contents
                or (candidate / name).exists()
                or (candidate / name).is_symlink()
                or not rendered.is_file()
                or rendered.is_symlink()
                or inputs.old_render.get(name) is None
                or file_transition.fingerprint(target / name)
                != inputs.old_render.get(name)
            ):
                continue
            contents[name] = (
                rendered.read_bytes(),
                bool(rendered.stat().st_mode & 0o111),
            )
    for name, (content, executable) in sorted(contents.items()):
        path = checked_destination(candidate, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o755 if executable else 0o644)
    return tuple(sorted(contents))


def restored_record(
    stage: Path, names: Sequence[str]
) -> dict[str, list[object]]:
    """Return the recorded bytes of the files a planning run restored."""
    return {
        name: [
            base64.b64encode((stage / name).read_bytes()).decode("ascii"),
            bool((stage / name).stat().st_mode & 0o111),
        ]
        for name in sorted(names)
    }


SHIM_MARKER = "# CSARC compatibility shim (Issue #1083)"


def shim_text(source: str, destination: str) -> str:
    """Return the forwarding wrapper kept at one moved script's old path."""
    relative = os.path.relpath(destination, os.path.dirname(source) or ".")
    header = (
        f"{SHIM_MARKER}: {source} moved to {destination}.\n"
        "# csarc update removes this file once no product file calls it.\n"
    )
    if source.endswith(".py"):
        # A Python caller may run the module or import it from this path.
        return (
            "#!/usr/bin/env python3\n" + header + "import os\n"
            "import runpy\n"
            "import sys\n\n"
            "_TARGET = os.path.join(\n"
            "    os.path.dirname(os.path.abspath(__file__)), "
            f"{relative!r}\n"
            ")\n"
            'if __name__ == "__main__":\n'
            "    sys.argv[0] = _TARGET\n"
            '    runpy.run_path(_TARGET, run_name="__main__")\n'
            "else:\n"
            "    globals().update(runpy.run_path(_TARGET))\n"
        )
    return (
        "#!/usr/bin/env bash\n"
        + header
        + 'exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/'
        f'{relative}" "$@"\n'
    )


def product_references(
    candidate: Path, source: str, payload: Collection[str]
) -> bool:
    """Return whether a non-CSARC file still calls one legacy path.

    A file names the path itself, or it sits in the same directory and
    names the script by its file name (for example a sibling lookup).
    """
    directory, _slash, name = source.rpartition("/")
    pattern = rf"(?<![\w.-]){re.escape(name)}(?![\w.-])"
    if name.endswith(".py"):
        # A sibling Python file may import the moved module by name.
        module = re.escape(name.removesuffix(".py"))
        pattern += rf"|^\s*(?:import|from)\s+{module}\b"
    sibling = re.compile(pattern, re.MULTILINE)
    rendered = set(payload)
    for relative, path in project_files(candidate).items():
        if (
            relative == source
            or relative in rendered
            or relative.startswith((".csarc/", ".git/"))
            or not path.is_file()
            or path.is_symlink()
            or path.stat().st_size > 1_000_000
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if source in text or (
            relative.rpartition("/")[0] == directory and sibling.search(text)
        ):
            return True
    return False


def write_compatibility_shims(
    candidate: Path,
    layout_moves: Sequence[tuple[str, str]],
    retained: Collection[str],
    payload: Collection[str],
) -> tuple[str, ...]:
    """Keep moved scripts callable at their old paths for product files.

    A moved executable whose legacy path a product file still calls gets a
    CSARC-owned forwarding wrapper there; an earlier wrapper nothing calls
    any longer is removed (Issue #1083). Returns the wrappers written.
    """
    shims: list[str] = []
    for source, destination in layout_moves:
        target = candidate / source
        moved = candidate / destination
        if (
            source in retained
            or target.exists()
            or target.is_symlink()
            or not moved.is_file()
            or not os.access(moved, os.X_OK)
            or not product_references(candidate, source, payload)
        ):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(shim_text(source, destination), encoding="utf-8")
        target.chmod(0o755)
        shims.append(source)
    for relative, path in sorted(project_files(candidate).items()):
        if (
            relative in shims
            or relative.startswith(".csarc/")
            or not path.is_file()
            or path.is_symlink()
            or path.stat().st_size > 4096
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SHIM_MARKER in text and not product_references(
            candidate, relative, payload
        ):
            path.unlink()
    return tuple(sorted(shims))


def present_payload(candidate: Path, payload: Sequence[str]) -> list[str]:
    """Return the rendered payload files the candidate holds."""
    return [
        name
        for name in payload
        if (candidate / name).is_file() and not (candidate / name).is_symlink()
    ]


def stage_payload(candidate: Path, payload: Sequence[str]) -> None:
    """Stage every rendered file, including one ignore rules would hide."""
    present = present_payload(candidate, payload)
    if present:
        run_git(
            ["git", "-C", str(candidate), "add", "--force", "--", *present],
            repository=candidate,
            neutralize_filters=True,
        )


def ignored_paths(
    repository: Path, paths: Sequence[str]
) -> list[dict[str, str]]:
    """Return each path the repository's ignore rules hide, with its rule."""
    if not paths:
        return []
    result = run_git(
        [
            "git",
            "-C",
            str(repository),
            "check-ignore",
            "--verbose",
            "--",
            *paths,
        ],
        repository=repository,
        capture=True,
        check=False,
        neutralize_filters=True,
    )
    if result.returncode not in {0, 1}:
        raise CliError(
            "Cannot evaluate the repository ignore rules for the rendered "
            "files; the target was not changed."
        )
    # Each line is `<source>:<line>:<pattern>\t<path>`; rendered paths are
    # plain template names, so Git never quotes them.
    hidden = []
    for line in result.stdout.splitlines():
        rule, _tab, path = line.partition("\t")
        source, _colon, rest = rule.partition(":")
        number, _colon, pattern = rest.partition(":")
        if path:
            hidden.append(
                {
                    "line": number,
                    "path": path,
                    "pattern": pattern,
                    "source": source,
                }
            )
    return hidden


def ignored_text(hidden: Sequence[Mapping[str, str]]) -> str:
    """Render hidden payload rows as ``path (source:line: pattern)``."""
    return "; ".join(
        f"{row['path']} ({row['source']}:{row['line']}: {row['pattern']})"
        for row in hidden
    )


def reject_ignored_payload(candidate: Path, payload: Sequence[str]) -> None:
    """Fail closed when ignore rules would hide a rendered file (#1083).

    The candidate is verified with every rendered file, but Git never
    stages an untracked ignored one, so the target would silently miss it
    and the verified tree would differ from the written one.
    """
    hidden = ignored_paths(candidate, present_payload(candidate, payload))
    if hidden:
        raise CliError(
            "Repository ignore rules hide rendered CSARC files, so the "
            "update would not deliver them: "
            + ignored_text(hidden)
            + ". Narrow or except those rules (for a conflicted .gitignore, "
            "in its decision), then create a new plan. The target was not "
            "changed."
        )


def planned_ignored_payload(
    target: Path,
    payload: Sequence[str],
    overrides: Mapping[str, bytes | None] | None = None,
) -> list[dict[str, str]]:
    """Return rendered files the target's ignore rules would hide.

    The apply stops on such a file (``reject_ignored_payload``); this
    evaluates the same rules before any candidate exists, so ``--check``
    lists them and ``--finalize-plan`` rejects a decided ``.gitignore``
    that still hides one (Issue #1146 AC4). ``overrides`` replaces the
    content of conflicted ignore files with their recorded decisions. A
    payload path the target already tracks is delivered regardless.
    """
    tracked = set(
        run_git(
            ["git", "-C", str(target), "ls-files", "-z"],
            repository=target,
            capture=True,
            neutralize_filters=True,
        ).stdout.split("\0")
    )
    candidates = sorted(name for name in payload if name not in tracked)
    if not candidates:
        return []
    decided = dict(overrides or {})
    with tempfile.TemporaryDirectory(prefix="csarc-ignore-") as temporary:
        root = Path(temporary).resolve()
        run_git(["git", "init", "--quiet", str(root)])
        sources = {
            name: path.read_bytes()
            for name, path in project_files(target).items()
            if PurePosixPath(name).name == ".gitignore"
            and not path.is_symlink()
        }
        for name, content in decided.items():
            if PurePosixPath(name).name == ".gitignore":
                if content is None:
                    sources.pop(name, None)
                else:
                    sources[name] = content
        for name, content in sources.items():
            destination = checked_destination(root, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        return ignored_paths(root, candidates)


def resolve_recorded_conflicts(
    candidate: Path,
    conflicts: Sequence[str],
    resolutions: Mapping[str, bytes | None],
) -> tuple[str, ...]:
    """Resolve exactly the planned conflicts; return any that remain."""
    if set(conflicts) != set(resolutions):
        raise CliError(
            "Update conflicts differ from the final plan (planned: "
            + (", ".join(sorted(resolutions)) or "none")
            + "; realized: "
            + (", ".join(conflicts) or "none")
            + "); the target was not changed. Create a new plan."
        )
    apply_conflict_resolutions(candidate, resolutions)
    return find_conflicts(candidate)


def apply_conflict_resolutions(
    candidate: Path, resolutions: Mapping[str, bytes | None]
) -> None:
    """Replace each conflicted candidate path with its recorded content."""
    for name, content in sorted(resolutions.items()):
        path = checked_destination(candidate, name)
        if content is None:
            if path.is_symlink() or path.exists():
                path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            path.unlink()
        path.write_bytes(content)


def update_action_pin_preflight(
    target: Path,
    source: str,
    sha: str,
    answers: Mapping[str, object],
) -> action_pin_preflight.PinPreflight:
    """Run the read-only product pin preflight, failing closed (#1065)."""
    try:
        return action_pin_preflight.run_preflight(
            target,
            source,
            sha,
            answers,
            lambda command: run_git(command, capture=True, check=False),
        )
    except action_pin_preflight.PinPreflightError as error:
        raise CliError(
            "Action pin preflight failed closed; the target was not "
            f"changed. {error} Repair: make the template source reachable "
            "at the reviewed commit (or pass a verified --to release) and "
            "keep each .github/workflows file a regular UTF-8 file, then "
            "rerun csarc update --check."
        ) from error


def update_conflict_sides(
    target: Path,
    old_stage: Path,
    new_side: Mapping[str, bytes | None],
    layout_moves: Sequence[tuple[str, str]],
) -> dict[str, dict[str, bytes | None]]:
    """Return the base, current, and new bytes of each conflict (#1147).

    ``current`` and ``new`` are exactly what ``keep-current`` and
    ``take-new`` would record; ``base`` is the recorded release's render,
    read at its old path when the update moves the file.
    """
    old_names = {new: old for old, new in layout_moves}

    def regular(path: Path) -> bytes | None:
        if path.is_symlink() or not path.is_file():
            return None
        return path.read_bytes()

    return {
        name: {
            "base": regular(old_stage / name)
            if (old_stage / name).exists()
            else regular(old_stage / old_names.get(name, name)),
            "current": regular(target / name),
            "new": new_content,
        }
        for name, new_content in sorted(new_side.items())
    }


def write_conflict_sides(
    report_directory: Path,
    sides: Mapping[str, Mapping[str, bytes | None]],
) -> None:
    """Write each conflict's sides under the report folder (#1147).

    The ``conflicts`` folder is tool output: it is replaced on every plan so
    no file from an earlier plan can be mistaken for the current one.
    """
    folder = report_directory / CONFLICT_SIDES_DIRECTORY
    if folder.is_symlink():
        raise CliError(
            f"{folder} is a symlink; remove it so conflict sides can be "
            "written."
        )
    if folder.is_dir():
        shutil.rmtree(folder)
    filesystem_root = Path(report_directory.anchor)
    relative_directory = report_directory.relative_to(filesystem_root)
    for name, contents in sides.items():
        for side in CONFLICT_SIDES:
            content = contents.get(side)
            if content is None:
                continue
            atomic_replace_text(
                filesystem_root,
                (
                    relative_directory / CONFLICT_SIDES_DIRECTORY / side / name
                ).as_posix(),
                content,
            )


def update_conflict_error(conflicts: Sequence[str], detail: str = "") -> str:
    """Return the one fail-closed message for an update conflict."""
    summary = (
        ", ".join(conflicts)
        if conflicts
        else detail or ("Copier exited non-zero")
    )
    return (
        f"Update needs manual conflict resolution ({summary}); the target "
        "was not changed. Run csarc update --check, compare each file's "
        "base, current, and new sides in the report folder, decide every "
        "listed file with csarc update --finalize-plan --decision "
        "PATH=keep-current|take-new|custom:FILE, then apply the final plan "
        "with csarc update --apply-plan."
    )


def plan_update(
    target: Path,
    workdir: Path,
    inputs: UpdateRunInputs,
    old_stage: Path,
    retained: Collection[str] = (),
    product_paths: Collection[str] = (),
    stage: Path | None = None,
) -> update_plan.UpdatePlanning:
    """Build the immutable planning result both check and apply review.

    ``retained`` lists retirement candidates kept because they differ from
    the trusted old render (#1066). ``product_paths`` lists generated
    paths the product now owns (the selected product-owned release
    workflow, #1083): Copier's deletion of one is undone and the plan
    reports it as product-owned, not as a retirement.
    """
    run_result = run_update_candidate(
        target,
        workdir,
        inputs,
        working_tree=True,
        skip_tasks=True,
        stage=stage,
    )
    if run_result.returncode != 0 and not run_result.conflicts:
        raise CliError(
            "Copier could not plan the update ("
            + (run_result.output or "unknown Copier error")
            + "). The target was not changed."
        )
    answers_files = {CONFIG_FILE.as_posix(), LEGACY_ANSWERS_FILE.as_posix()}
    old_files = project_files(old_stage)
    target_files = project_files(target)
    parity_paths = tuple(
        sorted(
            name
            for name, path in old_files.items()
            if name not in answers_files
            and (
                name not in target_files
                or file_fingerprint(path)
                != file_fingerprint(target_files[name])
            )
        )
    )
    customized = {
        name
        for name in parity_paths
        if name in target_files and name not in answers_files
    }
    kept = {*retained, *run_result.retained}
    owned = kept & set(product_paths)
    kept -= owned
    excluded = set(inputs.retiring)
    for source_name, destination_name in effective_layout_moves(
        inputs.layout_moves, {*kept, *run_result.shims}
    ):
        excluded.update((source_name, destination_name))
    add, overwrite, merge, delete = update_plan.classify_changes(
        run_result.changes,
        conflicts=run_result.conflicts,
        excluded=excluded,
        customized=customized,
    )
    return update_plan.UpdatePlanning(
        old_side=inputs.old_side,
        new_data=dict(inputs.new_data),
        add=add,
        overwrite=overwrite,
        merge=merge,
        delete=delete,
        conflicts=run_result.conflicts,
        render_parity=(
            update_plan.RENDER_PARITY_DIVERGED
            if parity_paths
            else update_plan.RENDER_PARITY_EQUAL
        ),
        parity_paths=parity_paths,
        retained=tuple(sorted(kept)),
        shims=run_result.shims,
        restored=run_result.restored,
        product_owned=tuple(
            sorted(
                name
                for name in {*run_result.product_owned, *owned}
                if name in target_files
            )
        ),
    )


def effective_layout_moves(
    layout_moves: tuple[tuple[str, str], ...], retained: Collection[str]
) -> tuple[tuple[str, str], ...]:
    """Drop the layout moves whose legacy source the plan keeps (#1083).

    A retained source is a modified generated file reported as a
    retire-modified conflict: it stays where it is, and the destination the
    new release renders is an ordinary addition, never a move target.
    """
    kept = set(retained)
    return tuple(move for move in layout_moves if move[0] not in kept)


def referenced_removals(
    target: Path,
    planning: update_plan.UpdatePlanning,
    layout_moves: tuple[tuple[str, str], ...],
    retiring: tuple[str, ...],
) -> tuple[str, ...]:
    """Return the planned removals a file the plan keeps still uses.

    A kept file is one the plan leaves with its product content: untouched,
    product-owned, or merged. A conflict is not kept until its decision;
    ``--finalize-plan`` rejects a decision that keeps a use of a removal
    (``reject_decided_uses``). A retained ``retire-modified`` file is the
    superseded legacy layout kept only for review, so its calls into that
    layout keep nothing alive; a retained script that still uses them blocks
    the plan instead (``retained_script_uses``, Issue #1157). A move source
    is excluded; its callers keep
    working through a compatibility shim (#1083). See
    ``file_transition.content_uses`` for what counts as a use (#1146 AC2).
    """
    files = planned_update_files(target, planning, layout_moves, retiring)
    kept = {*files.preserve, *files.merge, *files.product_owned}
    kept -= {*files.retained, *files.manual}
    return file_transition.referenced_retirements(
        target, (*retiring, *planning.delete), kept
    )


def release_writer_moves(
    target: Path,
    writers: Sequence[str],
    moves: Sequence[tuple[str, str]],
) -> list[dict[str, str]]:
    """Return the moved files a kept product Release writer still uses.

    A product-owned Release writer stays where it is (#1083), but the
    layout migration moves the legacy release config, manifest, and version
    file into ``.csarc/``; a writer that still names them, or a
    release-please config that implies the moved version file, would stop
    releasing the product (Issue #1153). Each row names the writer, the
    used path, and its destination; the report blocks on them.
    """
    destinations = dict(moves)
    rows: list[dict[str, str]] = []
    for writer in writers:
        path = target / writer
        if path.is_symlink() or not path.is_file():
            continue
        used = set(
            file_transition.content_uses(
                writer, path.read_bytes(), destinations
            )
        )
        for config in sorted(used):
            source = target / config
            if source.is_symlink() or not source.is_file():
                continue
            used.update(
                name
                for name in file_transition.release_please_version_files(
                    source.read_bytes()
                )
                if name in destinations
            )
        rows.extend(
            {
                "destination": destinations[name],
                "path": name,
                "writer": writer,
            }
            for name in sorted(used)
        )
    return rows


def retained_script_uses(
    target: Path,
    retained: Sequence[str],
    removals: Sequence[str],
    moves: Sequence[tuple[str, str]],
) -> list[dict[str, str]]:
    """Return the removed or moved files a kept legacy script still uses.

    A ``retire-modified`` script stays in place, but the same plan removes
    or moves the files it runs or reads; after the apply it fails, as a kept
    ``scripts/verify`` that called a removed ``scripts/test-pr-policy`` and
    read the moved ``policies/*.json`` did (Issue #1157). Each row names the
    script, the used path, and its destination (empty when removed); the
    report blocks on them. A move source with a compatibility shim keeps
    working and is not in ``moves``.
    """
    destinations = dict(moves)
    gone = {*removals, *destinations}
    rows: list[dict[str, str]] = []
    for script in sorted(set(retained)):
        path = target / script
        if path.is_symlink() or not path.is_file():
            continue
        content = path.read_bytes()
        if not (path.stat().st_mode & 0o111 or content.startswith(b"#!")):
            continue
        rows.extend(
            {
                "destination": destinations.get(used, ""),
                "path": used,
                "script": script,
            }
            for used in file_transition.content_uses(script, content, gone)
        )
    return rows


def update_retained_uses(
    update: Mapping[str, object] | None,
) -> list[dict[str, str]]:
    """Return the recorded retained-script uses from one plan."""
    rows = (update or {}).get("retained_uses")
    if not isinstance(rows, list):
        return []
    return [
        {str(key): str(value) for key, value in row.items()}
        for row in rows
        if isinstance(row, dict)
    ]


def reject_retained_uses(report: Mapping[str, object]) -> None:
    """Stop a final plan while a kept legacy script loses its files.

    No file decision resolves it (Issue #1157): the script has to be
    deleted or changed in a product commit, and a new ``--check`` plans
    again.
    """
    actions = cast(list[Mapping[str, object]], report["required_actions"])
    blocked = [
        str(row["message"])
        for row in actions
        if row["kind"] == "retire-modified" and row["blocking"] is True
    ]
    if blocked:
        raise CliError(" ".join(blocked))


def update_release_writer_moves(
    update: Mapping[str, object] | None,
) -> list[dict[str, str]]:
    """Return the recorded writer uses of moved files from one plan."""
    rows = (update or {}).get("release_writer_moves")
    if not isinstance(rows, list):
        return []
    return [
        {str(key): str(value) for key, value in row.items()}
        for row in rows
        if isinstance(row, dict)
    ]


def release_writer_actions(
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    """Return one blocking row per product writer that moves would break."""
    by_writer: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        by_writer.setdefault(row["writer"], []).append(row)
    return [
        {
            "blocking": True,
            "command": "csarc update --data release_ownership=csarc-owned",
            "kind": "release-writer",
            "message": "The product-owned Release writer is kept, but this "
            "update moves files it uses: "
            + ", ".join(
                f"{row['path']} -> {row['destination']}" for row in uses
            )
            + ", so product releases would break. Plan again with "
            "--data release_ownership=csarc-owned to let CSARC own the "
            "release, or change the writer in a product commit so it no "
            "longer uses these paths, then run csarc update --check again; "
            "the target was not changed.",
            "subject": writer,
        }
        for writer, uses in sorted(by_writer.items())
    ]


def reject_release_writer_moves(report: Mapping[str, object]) -> None:
    """Stop a final plan while a kept Release writer loses moved files.

    No file decision resolves it (Issue #1153): the release owner or the
    writer itself has to change, and a new ``--check`` then plans again.
    """
    actions = cast(list[Mapping[str, object]], report["required_actions"])
    blocked = [
        str(row["message"])
        for row in actions
        if row["kind"] == "release-writer" and row["blocking"] is True
    ]
    if blocked:
        raise CliError(" ".join(blocked))


def reject_decided_ignore_rules(
    target: Path,
    payload: Sequence[str],
    resolutions: Mapping[str, bytes | None],
) -> None:
    """Stop a final plan whose decided ignore rules hide rendered files.

    The apply would fail closed on the same files (#1083); finalize knows
    every decision, so it refuses before the plan exists (#1146 AC4).
    """
    hidden = planned_ignored_payload(target, payload, resolutions)
    if hidden:
        raise CliError(
            "With the recorded decisions, ignore rules still hide rendered "
            "CSARC files, so the apply would stop: "
            + ignored_text(hidden)
            + ". Except those paths (for a conflicted .gitignore, in its "
            "--decision), then run csarc update --check again; the target "
            "was not changed."
        )


def reject_decided_uses(
    resolutions: Mapping[str, bytes | None],
    removals: Sequence[str],
    moved: Sequence[str] = (),
) -> None:
    """Stop a final plan whose decided content uses a file it removes.

    keep-current or custom content for a conflict is kept by the plan, so
    it must not call or configure a file the same plan retires or deletes
    (Issue #1146 AC2). A kept script also must not run or read a file the
    plan moves without a compatibility shim (Issue #1157). The operator
    chooses take-new, a custom file without that use, or moves the product
    use into a product file and plans again, which keeps the used file as
    product-owned.
    """
    planned = tuple(removals)
    findings = [
        f"{name} uses {', '.join(used)}"
        for name, content in sorted(resolutions.items())
        if content is not None
        and (
            used := file_transition.content_uses(
                name,
                content,
                (*planned, *moved) if content.startswith(b"#!") else planned,
            )
        )
    ]
    if findings:
        raise CliError(
            "The decided content keeps a use of a file this plan removes: "
            + "; ".join(findings)
            + ". Choose take-new or a custom file without that use, or move "
            "the use into a product file and run csarc update --check "
            "again; the target was not changed."
        )


def planned_update_files(
    target: Path,
    planning: update_plan.UpdatePlanning,
    layout_moves: tuple[tuple[str, str], ...],
    retiring: tuple[str, ...],
) -> Plan:
    """Project one planning result onto the shared file plan model."""
    layout_moves = effective_layout_moves(
        layout_moves, {*planning.retained, *planning.shims}
    )
    acted = set(planning.changed_paths()) | set(planning.conflicts)
    acted.update(retiring)
    acted.update(planning.retained)
    for source_name, destination_name in layout_moves:
        acted.update((source_name, destination_name))
    return Plan(
        planning.add,
        planning.overwrite,
        tuple(sorted(retiring)),
        tuple(sorted(set(project_files(target)) - acted)),
        planning.merge,
        planning.conflicts,
        (),
        tuple(f"{old} -> {new}" for old, new in layout_moves),
        planning.delete,
        planning.retained,
        planning.product_owned,
        planning.shims,
    )


def update_transitions(
    target: Path,
    planning: update_plan.UpdatePlanning,
    layout_moves: tuple[tuple[str, str], ...],
    retiring: tuple[str, ...],
) -> file_transition.ApprovedTransitions:
    """Return the exact file transitions one reviewed plan approves."""
    return file_transition.approved_transitions(
        add=planning.add,
        overwrite=planning.overwrite,
        merge=planning.merge,
        delete=planning.delete,
        retire=retiring,
        moves=effective_layout_moves(
            layout_moves, {*planning.retained, *planning.shims}
        ),
        target_files=project_files(target),
        metadata=(
            CONFIG_FILE.as_posix(),
            LEGACY_ANSWERS_FILE.as_posix(),
            PROVENANCE_FILE.as_posix(),
        ),
        protected=planning.product_owned,
    )


def apply_update_transitions(
    target: Path,
    candidate: Path,
    transitions: file_transition.ApprovedTransitions,
    artifacts: Mapping[str, str],
    delete_paths: tuple[str, ...],
    target_snapshot: Mapping[str, object],
) -> None:
    """Apply exactly the approved update transitions as one transaction.

    The realized candidate effects must equal the approved create, modify,
    and delete sets before anything is written (#1066); the write then
    restores the byte-identical base on any failure.
    """
    problems = file_transition.transition_divergence(
        transitions,
        artifacts,
        delete_paths,
        cast(Mapping[str, str], target_snapshot["target_files"]),
    )
    if problems:
        raise CliError(
            "Update apply diverged from the approved file transitions ("
            + "; ".join(problems)
            + "); the target was not changed. Create a new plan."
        )
    for relative_name in (*artifacts, *delete_paths):
        checked_destination(target, relative_name)
    validate_target_snapshot(target, target_snapshot)
    try:
        file_transition.apply_transaction(
            target, candidate, artifacts, delete_paths
        )
    except (OSError, file_transition.TransitionError) as error:
        raise CliError(
            f"Update apply failed ({error}); the target was restored to "
            "its base. Create a new plan."
        ) from error


FINAL_PLAN_ARGUMENTS = (
    "accept_legacy",
    "allow_unreleased",
    "channel",
    "expected_sha",
    "from_release",
    "to",
)
CONFLICT_MARKER = re.compile(rb"^(<{7}|={7}|>{7})( |$)", re.MULTILINE)


def git_version() -> str:
    """Return the Git version string that shapes clones and diffs."""
    return run_git(["git", "--version"], capture=True).stdout.strip()


def update_toolchain() -> dict[str, str]:
    """Observe the exact-pinned toolchain, failing closed on drift."""
    toolchain = final_plan.observe_toolchain(git_version)
    try:
        final_plan.require_pinned_toolchain(toolchain)
    except final_plan.FinalPlanError as error:
        raise CliError(f"{error} The target was not changed.") from error
    return toolchain


def repository_permissions(repository: RepositoryContext) -> object:
    """Return the caller's live permissions on the GitHub repository."""
    if not repository.verified or repository.repository is None:
        return None
    try:
        result = run(
            ["gh", "api", "--method", "GET", f"repos/{repository.repository}"],
            capture=True,
            check=False,
        )
    except FileNotFoundError:
        return "unavailable"
    if result.returncode != 0:
        return "unavailable"
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return "unavailable"
    permissions = (
        payload.get("permissions") if isinstance(payload, dict) else None
    )
    if not isinstance(permissions, dict):
        return "unavailable"
    return {
        str(key): value
        for key, value in sorted(permissions.items())
        if isinstance(value, bool)
    }


def update_live_facts(
    target: Path,
    repository: RepositoryContext,
    *,
    target_snapshot: Mapping[str, object],
    current: Revision,
    resolved: Revision,
    previous: Mapping[str, object] | None,
) -> dict[str, object]:
    """Return every live fact a final plan binds and apply re-observes."""
    origin = run_git(
        ["git", "-C", str(target), "remote", "get-url", "origin"],
        repository=target,
        capture=True,
        check=False,
    )
    return {
        "origin": origin.stdout.strip() if origin.returncode == 0 else None,
        "permissions": repository_permissions(repository),
        "release": {
            "current": asdict(current),
            "previous": None if previous is None else dict(previous),
            "target": asdict(resolved),
        },
        "repository": repository.as_dict(),
        "target": dict(sorted(target_snapshot.items())),
    }


def current_target_snapshot(target: Path) -> dict[str, object]:
    """Return the target state an update plan binds."""
    head, changes, status_sha256 = target_state(target)
    return {
        "target_changes": list(changes),
        "target_files": target_file_snapshot(target),
        "target_head": head,
        "target_status_sha256": status_sha256,
    }


def decision_content(
    target: Path,
    name: str,
    choice: str,
    custom: Path | None,
    new_side: Mapping[str, bytes | None],
) -> bytes | None:
    """Return the exact bytes one conflict decision resolves to."""
    if choice == final_plan.DECISION_KEEP:
        path = target / name
        if path.is_symlink():
            raise CliError(f"Cannot keep {name}: it is a symlink.")
        content = path.read_bytes() if path.is_file() else None
    elif choice == final_plan.DECISION_TAKE:
        content = new_side.get(name)
    else:
        if custom is None:
            raise CliError(f"The custom decision for {name} needs a FILE.")
        resolved = Path(os.path.abspath(custom.expanduser()))
        if resolved == target or target in resolved.parents:
            raise CliError(
                f"The custom resolution for {name} must live outside the "
                "target repository."
            )
        if resolved.is_symlink() or not resolved.is_file():
            raise CliError(
                f"The custom resolution for {name} must be a regular file."
            )
        content = resolved.read_bytes()
    if content is not None and CONFLICT_MARKER.search(content):
        raise CliError(
            f"The {choice} resolution for {name} still has conflict markers."
        )
    return content


def resolution_transitions(
    target: Path,
    transitions: file_transition.ApprovedTransitions,
    resolutions: Mapping[str, bytes | None],
) -> file_transition.ApprovedTransitions:
    """Add the file effects of the recorded decisions to the approval."""
    create = set(transitions.create)
    modify = set(transitions.modify)
    delete = set(transitions.delete)
    for name, content in resolutions.items():
        path = target / name
        exists = path.is_file() and not path.is_symlink()
        if content is None:
            if exists:
                delete.add(name)
        elif not exists:
            create.add(name)
        elif path.read_bytes() != content:
            modify.add(name)
    return file_transition.ApprovedTransitions(
        frozenset(create),
        frozenset(modify),
        frozenset(delete),
        transitions.optional,
        transitions.protected,
    )


def replay_pin_decisions(
    target: Path,
    items: Sequence[Mapping[str, object]],
    decisions: Sequence[Mapping[str, object]],
    pin_commit: str,
) -> list[dict[str, object]]:
    """Read pin decisions back from the commit and reject extra changes."""

    def git(command: list[str]) -> subprocess.CompletedProcess[str]:
        return run_git(command, capture=True, check=False)

    try:
        accepted = action_pin_preflight.validate_pin_decisions(
            items, decisions, git, target
        )
        unlisted = action_pin_preflight.unlisted_pin_changes(
            items, git, target, pin_commit
        )
    except action_pin_preflight.PinPreflightError as error:
        raise CliError(
            f"Action pin decisions failed closed ({error}); the target was "
            "not changed."
        ) from error
    if unlisted:
        raise CliError(
            "Pin commit changes more than the listed action pins ("
            + ", ".join(unlisted)
            + "); the target was not changed."
        )
    return accepted


def final_pin_decisions(
    target: Path,
    stage1: Mapping[str, object],
    pin_commit: str | None,
) -> dict[str, object]:
    """Accept the committed product pin decisions for the stage-1 items."""
    items = [
        item
        for item in update_pin_items(stage1) or []
        if item.get("reason") != action_pin_preflight.REASON_PRODUCT_PIN_NEWER
    ]
    if not items:
        if pin_commit is not None:
            raise CliError(
                "--pin-commit was given, but the stage-1 plan lists no "
                "action pin drift."
            )
        return {"commit": None, "decisions": [], "items": []}
    if pin_commit is None:
        raise CliError(
            "The stage-1 plan lists action pin drift; commit the product "
            "pin changes, then pass --pin-commit <full SHA>."
        )
    decisions = [dict(item, commit_sha=pin_commit) for item in items]
    accepted = replay_pin_decisions(target, items, decisions, pin_commit)
    return {"commit": pin_commit, "decisions": accepted, "items": items}


def planning_record(planning: update_plan.UpdatePlanning) -> dict[str, object]:
    """Return every field needed to rebuild one planning result exactly."""
    return {
        "add": list(planning.add),
        "conflicts": list(planning.conflicts),
        "delete": list(planning.delete),
        "digest": planning.digest(),
        "merge": list(planning.merge),
        "overwrite": list(planning.overwrite),
        "parity_paths": list(planning.parity_paths),
        "product_owned": list(planning.product_owned),
        "render_parity": planning.render_parity,
        "retained": list(planning.retained),
        "shims": list(planning.shims),
        "restored": list(planning.restored),
    }


def final_report(
    report: Mapping[str, object], digest: str
) -> dict[str, object]:
    """Return a finalized report that names its sealed final plan."""
    try:
        return lifecycle_report.with_final_plan(
            report,
            {
                "mode": "update",
                "path": final_plan.FINAL_PLAN_BASENAME,
                "replayable": True,
                "schema_version": final_plan.SCHEMA_VERSION,
                "sha256": digest,
            },
        )
    except lifecycle_report.LifecycleReportError as error:
        raise CliError(f"Lifecycle report is invalid: {error}") from error


@dataclass(frozen=True)
class FinalPlanContext:
    """Everything one ``update --finalize-plan`` run records."""

    target: Path
    report_directory: Path
    plan: ResolvedPlan
    planning: update_plan.UpdatePlanning
    run_inputs: UpdateRunInputs
    transitions: file_transition.ApprovedTransitions
    update_report: Mapping[str, object]
    target_snapshot: Mapping[str, object]
    current: Revision
    previous: Mapping[str, object] | None
    explicit_data: Mapping[str, object]
    new_side: Mapping[str, bytes | None]


def final_plan_payload(
    args: argparse.Namespace,
    context: FinalPlanContext,
    *,
    toolchain: Mapping[str, str],
    stage1_sha256: str,
    file_choices: Mapping[str, tuple[str, Path | None]],
    resolutions: Mapping[str, bytes | None],
    approved: file_transition.ApprovedTransitions,
    pins: Mapping[str, object],
    report: Mapping[str, object],
) -> dict[str, object]:
    """Return the unsealed final plan body; every value is plain JSON."""
    run_inputs = context.run_inputs
    plan = context.plan
    arguments = {name: getattr(args, name) for name in FINAL_PLAN_ARGUMENTS}
    return {
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "decisions": final_plan.exact_json(
            {
                "action_pins": dict(pins),
                "files": [
                    final_plan.resolution(name, file_choices[name][0], content)
                    for name, content in sorted(resolutions.items())
                ],
                "settings": [
                    dict(row)
                    for row in cast(
                        list[Mapping[str, object]], report["settings"]
                    )
                    if row["class"] != "unchanged"
                ],
            },
            "Decisions",
        ),
        "derived": final_plan.exact_json(
            {
                "capabilities": plan.capabilities,
                "layout_moves": [
                    list(move) for move in run_inputs.layout_moves
                ],
                "old_render": dict(run_inputs.old_render),
                "payload": list(run_inputs.payload),
                "pin_alignment": [
                    list(entry) for entry in run_inputs.pin_alignment
                ],
                "restored": {
                    name: list(value)
                    for name, value in run_inputs.restored.items()
                },
                "planning": planning_record(context.planning),
                "retiring": list(run_inputs.retiring),
                "transitions": approved.as_dict(),
                "update": plan.update,
            },
            "Derived update context",
        ),
        "inputs": final_plan.exact_json(
            {
                "answers": plan.answers,
                "arguments": arguments,
                "explicit_data": dict(context.explicit_data),
                "new_data": dict(run_inputs.new_data),
                "old_commit": run_inputs.old_commit,
                "old_side": {
                    "answers": dict(run_inputs.old_side.answers),
                    "context": dict(run_inputs.old_side.context),
                    "dropped": list(run_inputs.old_side.dropped),
                    "sources": dict(run_inputs.old_side.sources),
                },
                "raw_answers": dict(run_inputs.raw_answers),
                "source": run_inputs.source,
                "target_sha": run_inputs.target_sha,
                "target_uses_current_config": (
                    run_inputs.target_uses_current_config
                ),
            },
            "Update inputs",
        ),
        "kind": final_plan.FINAL_PLAN_KIND,
        "live_facts": final_plan.exact_json(
            update_live_facts(
                context.target,
                plan.repository,
                target_snapshot=context.target_snapshot,
                current=context.current,
                resolved=plan.revision,
                previous=context.previous,
            ),
            "Live facts",
        ),
        "replayable": True,
        "report": dict(report),
        "schema_version": final_plan.SCHEMA_VERSION,
        "stage1_plan": {
            "path": UPDATE_PLAN_BASENAME,
            "sha256": stage1_sha256,
        },
        "target": str(context.target),
        "toolchain": dict(toolchain),
    }


def write_update_final_plan(
    args: argparse.Namespace, context: FinalPlanContext
) -> int:
    """Record the human decisions as one immutable final plan (#1067)."""
    target = context.target
    report_directory = context.report_directory
    planning = context.planning
    stage1_path = report_directory / UPDATE_PLAN_BASENAME
    final_path = report_directory / final_plan.FINAL_PLAN_BASENAME
    if final_path.exists() or final_path.is_symlink():
        raise CliError(
            f"Final plan {final_path} already exists and is immutable; apply "
            "it with csarc update --apply-plan, or keep it and decide again "
            "in a new report folder: run csarc update --check with a new "
            "--report-dir, then --finalize-plan with that same --report-dir."
        )
    toolchain = update_toolchain()
    try:
        stage1 = final_plan.load_stage1(stage1_path)
        file_choices = final_plan.parse_file_decisions(args.decision)
        final_plan.require_complete_decisions(planning.conflicts, file_choices)
    except final_plan.FinalPlanError as error:
        raise CliError(str(error)) from error
    stage1_planning = stage1.get("planning")
    template = stage1.get("template")
    if (
        not isinstance(stage1_planning, dict)
        or stage1_planning.get("digest") != planning.digest()
        or not isinstance(template, dict)
        or template.get("sha") != context.plan.revision.sha
    ):
        raise CliError(
            "The stage-1 plan no longer matches the update planning (the "
            "template, inputs, or conflicts changed); run csarc update "
            "--check again and review it before deciding."
        )
    pins = final_pin_decisions(target, stage1, args.pin_commit)
    resolutions = {
        name: decision_content(target, name, choice, custom, context.new_side)
        for name, (choice, custom) in sorted(file_choices.items())
    }
    reject_decided_uses(
        resolutions,
        (*context.run_inputs.retiring, *planning.delete),
        tuple(
            source
            for source, _destination in effective_layout_moves(
                context.run_inputs.layout_moves,
                {*planning.retained, *planning.shims},
            )
        ),
    )
    reject_decided_ignore_rules(target, context.run_inputs.payload, resolutions)
    reject_release_writer_moves(context.update_report)
    reject_retained_uses(context.update_report)
    approved = resolution_transitions(target, context.transitions, resolutions)
    stage1_sha256 = str(stage1["plan_sha256"])
    try:
        report = lifecycle_report.finalize_update_report(
            context.update_report,
            decisions={
                name: choice for name, (choice, _) in file_choices.items()
            },
            stage1_sha256=stage1_sha256,
            next_steps=[
                {
                    "command": (
                        f"csarc update {target} --apply-plan {final_path}"
                    ),
                    "text": "Apply the final plan exactly as recorded.",
                }
            ],
        )
        sealed = final_plan.seal(
            final_plan_payload(
                args,
                context,
                toolchain=toolchain,
                stage1_sha256=stage1_sha256,
                file_choices=file_choices,
                resolutions=resolutions,
                approved=approved,
                pins=pins,
                report=report,
            )
        )
    except (
        final_plan.FinalPlanError,
        lifecycle_report.LifecycleReportError,
    ) as error:
        raise CliError(f"Cannot create the final plan: {error}") from error
    digest = str(sealed["final_plan_sha256"])
    filesystem_root = Path(report_directory.anchor)
    atomic_replace_text(
        filesystem_root,
        final_path.relative_to(filesystem_root).as_posix(),
        final_plan.plan_text(sealed),
    )
    write_lifecycle_reports(
        report_directory,
        operation="update",
        plan_name=UPDATE_PLAN_BASENAME,
        plan_payload=None,
        report=final_report(report, digest),
        emit=True,
    )
    print(f"Final plan: {final_path} (sha256 {digest}).")
    return 0


def reject_apply_plan_arguments(args: argparse.Namespace) -> None:
    """Reject options that would change a recorded final plan."""
    conflicting = [
        flag
        for flag, active in (
            ("--check", args.check),
            ("--dry-run", args.dry_run),
            ("--json", args.json),
            ("--finalize-plan", args.finalize_plan),
            ("--data", bool(args.data)),
            ("--decision", bool(args.decision)),
            ("--pin-commit", args.pin_commit is not None),
            ("--to", args.to is not None),
            ("--expected-sha", args.expected_sha is not None),
            ("--from-release", args.from_release is not None),
            ("--accept-legacy", args.accept_legacy),
            ("--allow-unreleased", args.allow_unreleased),
            ("--channel", args.channel != "stable"),
        )
        if active
    ]
    if conflicting:
        raise CliError(
            "--apply-plan uses only the values recorded in the final plan; "
            "remove " + ", ".join(conflicting) + "."
        )


def recorded_run(
    sealed: Mapping[str, object],
) -> tuple[
    UpdateRunInputs,
    update_plan.UpdatePlanning,
    file_transition.ApprovedTransitions,
]:
    """Rebuild the exact update inputs a final plan recorded."""
    inputs = cast(dict[str, Any], sealed["inputs"])
    derived = cast(dict[str, Any], sealed["derived"])
    old = inputs["old_side"]
    old_side = update_plan.OldSideInputs(
        dict(old["answers"]),
        dict(old["sources"]),
        tuple(old["dropped"]),
        dict(old["context"]),
    )
    run_inputs = UpdateRunInputs(
        raw_answers=dict(inputs["raw_answers"]),
        old_side=old_side,
        new_data=dict(inputs["new_data"]),
        old_commit=str(inputs["old_commit"]),
        source=str(inputs["source"]),
        target_sha=str(inputs["target_sha"]),
        layout_moves=tuple(
            (str(source), str(destination))
            for source, destination in derived["layout_moves"]
        ),
        retiring=tuple(derived["retiring"]),
        target_uses_current_config=bool(inputs["target_uses_current_config"]),
        old_render=dict(derived["old_render"]),
        payload=tuple(derived.get("payload", ())),
        pin_alignment=tuple(
            tuple(str(part) for part in entry)
            for entry in derived.get("pin_alignment", ())
        ),
        restored={
            str(name): list(value)
            for name, value in derived.get("restored", {}).items()
        },
    )
    recorded = derived["planning"]
    planning = update_plan.UpdatePlanning(
        old_side=old_side,
        new_data=dict(inputs["new_data"]),
        add=tuple(recorded["add"]),
        overwrite=tuple(recorded["overwrite"]),
        merge=tuple(recorded["merge"]),
        delete=tuple(recorded["delete"]),
        conflicts=tuple(recorded["conflicts"]),
        render_parity=str(recorded["render_parity"]),
        parity_paths=tuple(recorded["parity_paths"]),
        retained=tuple(recorded["retained"]),
        shims=tuple(recorded.get("shims", ())),
        restored=tuple(recorded.get("restored", ())),
        product_owned=tuple(recorded["product_owned"]),
    )
    if planning.digest() != recorded["digest"]:
        raise CliError(
            "The final plan's planning record does not match its digest; "
            "the target was not changed."
        )
    approved = derived["transitions"]
    transitions = file_transition.ApprovedTransitions(
        frozenset(approved["create"]),
        frozenset(approved["modify"]),
        frozenset(approved["delete"]),
        frozenset(approved["optional"]),
        frozenset(approved["protected"]),
    )
    return run_inputs, planning, transitions


def load_final_plan(
    args: argparse.Namespace, target: Path
) -> tuple[dict[str, object], Path]:
    """Read and bind one final plan to this target and report directory."""
    plan_path = Path(os.path.abspath(args.apply_plan.expanduser()))
    try:
        sealed = final_plan.load(plan_path)
    except final_plan.FinalPlanError as error:
        raise CliError(f"{error} The target was not changed.") from error
    if sealed["target"] != str(target):
        raise CliError(
            f"The final plan was created for {sealed['target']}, not "
            f"{target}; the target was not changed."
        )
    report_directory = lifecycle_report_directory(
        target, plan_path.parent, "update"
    )
    if (
        args.report_dir is not None
        and lifecycle_report_directory(target, args.report_dir, "update")
        != report_directory
    ):
        raise CliError(
            "--report-dir must match the directory of the applied final "
            "plan; the applied report is written beside that plan."
        )
    return sealed, report_directory


def require_recorded_live_facts(
    target: Path, sealed: Mapping[str, object]
) -> tuple[Revision, dict[str, object] | None]:
    """Re-observe the toolchain and live facts; any difference fails."""
    toolchain = update_toolchain()
    drift = final_plan.live_fact_differences(
        cast(Mapping[str, object], sealed["toolchain"]), toolchain
    )
    if drift:
        raise CliError(
            "The toolchain differs from the final plan ("
            + ", ".join(drift)
            + "); the target was not changed. Use the recorded versions or "
            "create a new plan."
        )
    inputs = cast(dict[str, Any], sealed["inputs"])
    arguments = inputs["arguments"]
    saved_visibility = inputs["raw_answers"].get("project_visibility")
    repository = repository_context(
        target,
        inputs["explicit_data"].get("project_visibility"),
        saved_visibility=(
            saved_visibility if isinstance(saved_visibility, str) else None
        ),
    )
    _status, current, resolved, previous = update_status(
        target,
        arguments["to"],
        expected_sha=arguments["expected_sha"],
        allow_unreleased=arguments["allow_unreleased"],
        accept_legacy=arguments["accept_legacy"],
        from_release=arguments["from_release"],
        channel=arguments["channel"],
    )
    observed = update_live_facts(
        target,
        repository,
        target_snapshot=current_target_snapshot(target),
        current=current,
        resolved=resolved,
        previous=previous,
    )
    changed = final_plan.live_fact_differences(
        cast(Mapping[str, object], sealed["live_facts"]), observed
    )
    if changed:
        raise CliError(
            "Live facts differ from the final plan ("
            + ", ".join(changed)
            + "); the target was not changed. Keep this final plan and "
            "create a new one: run csarc update --check with a new "
            "--report-dir, then --finalize-plan with that same --report-dir."
        )
    return resolved, previous


def command_update_apply_plan(args: argparse.Namespace) -> int:
    """Apply one sealed final plan using only its recorded values."""
    reject_apply_plan_arguments(args)
    target = resolve_repository_target(args.path)
    sealed, report_directory = load_final_plan(args, target)
    digest = str(sealed["final_plan_sha256"])
    provenance = read_provenance(target)
    if provenance is not None and provenance.get("final_plan_sha256") == digest:
        print(
            f"Final plan {digest} is already applied to {target}; nothing "
            "was changed."
        )
        return 0
    if (target / PENDING_ADOPTION_FILE).is_file():
        raise CliError(
            "Adoption is pending; complete the manual merge and run "
            "csarc adopt --finalize before update."
        )
    # Hand-edited or contradictory schema 2 settings stop before any write
    # (SPEC-009, Issue #1071 AC4).
    load_saved_settings(target)
    resolved, previous = require_recorded_live_facts(target, sealed)
    decisions = cast(dict[str, Any], sealed["decisions"])
    pins = decisions["action_pins"]
    if pins["items"]:
        replay_pin_decisions(
            target, pins["items"], pins["decisions"], pins["commit"]
        )
    inputs = cast(dict[str, Any], sealed["inputs"])
    answers = dict(inputs["answers"])
    validated_project_verification_hook(
        target, project_verification_configuration(target, answers)
    )
    run_inputs, planning, transitions = recorded_run(sealed)
    try:
        resolutions = {
            str(entry["path"]): final_plan.resolution_content(entry)
            for entry in decisions["files"]
        }
    except final_plan.FinalPlanError as error:
        raise CliError(f"{error} The target was not changed.") from error
    target_snapshot = cast(
        dict[str, object], cast(dict[str, Any], sealed["live_facts"])["target"]
    )
    if not confirm(args):
        return 0
    with tempfile.TemporaryDirectory(prefix="csarc-update-") as temporary:
        applied = run_update_candidate(
            target,
            Path(temporary).resolve(),
            run_inputs,
            working_tree=False,
            skip_tasks=False,
            resolutions=resolutions,
        )
        if applied.returncode != 0 or applied.conflicts:
            raise CliError(
                update_conflict_error(applied.conflicts, applied.output)
            )
        divergence = update_plan.realized_divergence(
            planning, applied.changes, applied.conflicts
        )
        if divergence:
            raise CliError(
                "Update apply diverged from the final plan ("
                + "; ".join(divergence)
                + "); the target was not changed. Create a new plan."
            )
        candidate = applied.candidate
        pin_answer_commit(candidate, run_inputs.target_sha)
        # One-time derived decisions come only from the saved schema 2 file
        # and the plan's explicit --data, exactly as the check recorded them
        # (SPEC-009, Issue #1071).
        raw_answers = cast(dict[str, object], inputs["raw_answers"])
        saved_decisions = (
            {
                key: raw_answers[key]
                for key in settings_schema.DECISION_SETTINGS
                if key in raw_answers
            }
            if settings_schema.SCHEMA_KEY in raw_answers
            else {}
        )
        persist_release_answers(
            candidate,
            answers,
            {
                **saved_decisions,
                **explicit_decisions(
                    cast(dict[str, object], inputs["explicit_data"])
                ),
            },
        )
        verify_project(candidate)
        write_provenance(
            candidate,
            resolved,
            previous,
            answers=answers,
            final_plan_sha256=digest,
        )
        artifacts, delete_paths = candidate_patch_effects(candidate)
        apply_update_transitions(
            target,
            candidate,
            transitions,
            artifacts,
            delete_paths,
            target_snapshot,
        )
    settings_plan(target)
    apply_milestone_description_plan(milestone_description_plan(target))
    stage1 = cast(dict[str, Any], sealed["stage1_plan"])
    write_lifecycle_reports(
        report_directory,
        operation="update",
        plan_name=UPDATE_PLAN_BASENAME,
        plan_payload=None,
        report=applied_lifecycle_report(
            final_report(cast(Mapping[str, object], sealed["report"]), digest),
            str(stage1["sha256"]),
            datetime.now(UTC).replace(microsecond=0).isoformat(),
            final_plan_sha256=digest,
        ),
        emit=True,
    )
    print(f"Applied final plan {digest}.")
    return 0


def command_update(args: argparse.Namespace) -> int:  # noqa: C901
    """Check, finalize, or apply a Copier smart update."""
    if args.apply_plan is not None:
        return command_update_apply_plan(args)
    if (args.decision or args.pin_commit is not None) and not (
        args.finalize_plan
    ):
        raise CliError("--decision and --pin-commit need --finalize-plan.")
    if args.finalize_plan and (args.check or args.dry_run or args.json):
        raise CliError(
            "--finalize-plan cannot be combined with --check, --dry-run, "
            "or --json."
        )
    target = resolve_repository_target(args.path)
    if (target / PENDING_ADOPTION_FILE).is_file():
        raise CliError(
            "Adoption is pending; complete the manual merge and run "
            "csarc adopt --finalize before update."
        )
    answers_path = config_path(target)
    if not answers_path.is_file():
        raise CliError(f"Missing {CONFIG_FILE}; use csarc adopt first.")
    # Unknown schemas and hand-edited or contradictory schema 2 settings
    # stop here, before any render or write (Issue #1071 AC4/AC6).
    saved_settings = load_saved_settings(target)
    saved_answers = dict(saved_settings.answers)
    explicit_data = parse_settings_data(args.data)
    decisions = {
        **saved_settings.decisions,
        **explicit_decisions(explicit_data),
    }
    saved_visibility = saved_answers.get("project_visibility")
    repository = repository_context(
        target,
        explicit_data.get("project_visibility"),
        saved_visibility=(
            saved_visibility if isinstance(saved_visibility, str) else None
        ),
    )
    # A target whose origin names another repository stops before any
    # render or write (Issue #1072 AC5).
    require_repository_identity(saved_answers, explicit_data, repository)
    candidate_answers, update_data = update_plan_answers(
        saved_answers, explicit_data, repository
    )
    observed = observed_setting_differences(
        saved_answers, explicit_data, repository
    )
    derived_values, derived_differences = resolve_derived_context(
        target, candidate_answers, decisions
    )
    candidate_answers.update(derived_values)
    update_data.update(derived_values)
    observed.update(derived_differences)
    # The release owner the repository evidence derives without any
    # explicit choice; confirming that value with --data must plan exactly
    # like leaving it out (Issue #1146 AC1).
    implicit_release_answers = implicit_release_owner(
        target, candidate_answers, saved_answers, explicit_data
    )
    candidate_answers = resolve_release_answers(target, candidate_answers)
    try:
        status, current_revision, target_revision, previous = update_status(
            target,
            args.to,
            expected_sha=args.expected_sha,
            allow_unreleased=args.allow_unreleased,
            accept_legacy=args.accept_legacy,
            from_release=args.from_release,
            channel=args.channel,
        )
    except ReleaseRecoveryError as missing:
        # A retired or malformed version cannot be interpreted safely.
        # Preserve user-owned content and rebuild the managed baseline.
        # Every other trust failure remains fail-closed.
        return command_update_reinstall(
            args,
            target,
            read_answer(answers_path, "_src_path"),
            candidate_answers,
            repository,
            missing,
        )
    source = status.get("source")
    if not isinstance(source, str):
        raise CliError("Update source must be a string.")
    release_migrated = bool(
        "release_ownership" not in saved_answers
        and explicit_data.get("release_ownership") in {None, "csarc-owned"}
        and implicit_release_answers is not None
        and legacy_release_writer(
            target, source, current_revision.sha, implicit_release_answers
        )
    )
    if release_migrated:
        # The only Release writer is the legacy template's own workflow, so
        # the release moves to the current CSARC writer (Issue #1083); the
        # plan retires the legacy workflow and keeps the version state.
        candidate_answers.update(CSARC_RELEASE_MIGRATION)
        update_data["release_ownership"] = "csarc-owned"
    if (
        candidate_answers.get("release_ownership") == "csarc-owned"
        and candidate_answers.get("project_mode") == "existing"
        and candidate_answers.get("release_workflow") == CSARC_RELEASE_WORKFLOW
    ):
        # copier.yml renders the hosted release workflow for an existing
        # project only when it is the selected CSARC writer.
        candidate_answers["csarc_release_workflow"] = True
        update_data["csarc_release_workflow"] = True
    # Product action pin drift is known before any render, plan, or write.
    # A one-shot apply stops here; a reviewed plan first drops the
    # workflows it retires, which are not product workflows (#1083).
    pins = update_action_pin_preflight(
        target, source, target_revision.sha, candidate_answers
    )
    if pins.blocking and not (args.check or args.dry_run or args.finalize_plan):
        raise CliError(action_pin_preflight.drift_error(pins))
    raw_answers = read_raw_answers(answers_path)
    with tempfile.TemporaryDirectory(prefix="csarc-update-plan-") as temporary:
        workdir = Path(temporary).resolve()
        stage = workdir / "project"
        stage.mkdir()
        render_context = copier_copy(
            source,
            target_revision,
            stage,
            candidate_answers,
            skip_tasks=True,
            decisions=decisions,
        )
        reject_retired_data_for(stage, explicit_data)
        if release_migrated and not (stage / CSARC_RELEASE_WORKFLOW).is_file():
            raise CliError(
                "This template release cannot render the CSARC release "
                "workflow that replaces the legacy release writer; update to "
                "a release that supports the migration. The target was not "
                "changed."
            )
        target_uses_current_config = (stage / CONFIG_FILE).is_file()
        # The persisted file intentionally keeps only user-owned release
        # choices. Preserve the repository-derived release contract in the
        # in-memory plan that still needs it for evidence and reporting.
        answers = dict(candidate_answers)
        answers.update(read_copier_answers(config_path(stage)))
        answers.update(render_context)
        # The release workflow render flag is derived each run, never a
        # setting, so it cannot make a current repository look outdated.
        answers.pop("csarc_release_workflow", None)
        preflight = capability_preflight(
            managed_script(stage, "release_policy.py"),
            target,
            target_revision,
            emit=False,
        )
        # The old side is rebuilt only from answers the old template asked
        # for plus a verified provenance snapshot (#1063); the derived
        # release contract below is used for settings comparison only.
        try:
            current_answers = resolve_release_answers(target, saved_answers)
        except CliError:
            # A legacy repository whose saved answers cannot resolve one
            # release owner (for example two legacy release writers) is
            # compared from its saved values; the candidate side still
            # fails closed unless an explicit owner was chosen.
            current_answers = dict(saved_answers)
        old_side, new_data, old_stage = render_old_side(
            source,
            current_revision,
            workdir,
            saved_answers,
            previous,
            update_data,
            complete=saved_settings.schema == settings_schema.SCHEMA_VERSION,
        )
        current_capabilities = capability_preflight(
            managed_script(old_stage, "release_policy.py"),
            target,
            current_revision,
            emit=False,
        )
        if saved_answers.get("project_mode") == "existing":
            preserve_existing_security_policy(stage, target)
        layout_moves = legacy_layout_pairs(
            stage,
            target,
        )
        candidates: tuple[str, ...] = (
            LEGACY_PROFILE_FILE.as_posix(),
            ".gitleaks.toml",
            ".pre-commit-config.yaml",
            "zizmor.yml",
        )
        rendered = file_transition.render_fingerprints(project_files(old_stage))
        stage_files = project_files(stage)
        # The selected product-owned release workflow is the product's only
        # Release writer even when a legacy render generated it, so the
        # update never retires or deletes it (#1083). A generated file the
        # new render drops while a file the plan keeps still uses it is
        # product-owned in the same way (#1146 AC2): each pass plans with
        # the referenced removals kept, until no kept file uses a removal.
        product_paths: tuple[str, ...] = product_release_workflow(answers)
        for attempt in itertools.count(1):
            old_render = {
                name: value
                for name, value in rendered.items()
                if name not in product_paths
            }
            # Copier never deletes a file that a newly selected option
            # excludes (for example the Release writer once ownership leaves
            # csarc-owned, #1068), so retire every CSARC-owned file the
            # trusted old render produced that the new render no longer
            # contains (#1077). A product-owned workflow the old render
            # never wrote is not a candidate, and a customized copy stays a
            # conflict below.
            retirement_candidates = (
                *candidates,
                *option_retirements(old_render, stage_files),
            )
            # A legacy file retires only when it is byte-identical to the
            # trusted old render; a modified one stays as a conflict (#1066).
            retiring, retained = file_transition.split_retirements(
                (
                    name
                    for name in retirement_candidates
                    if (target / name).is_file()
                    and not (target / name).is_symlink()
                ),
                target,
                old_render,
            )
            run_inputs = UpdateRunInputs(
                raw_answers=raw_answers,
                old_side=old_side,
                new_data=new_data,
                old_commit=current_revision.sha,
                source=source,
                target_sha=str(status["target_sha"]),
                layout_moves=layout_moves,
                retiring=retiring,
                target_uses_current_config=target_uses_current_config,
                old_render=old_render,
                payload=tuple(sorted(stage_files)),
                pin_alignment=action_pin_preflight.excluding(
                    pins, retiring
                ).aligned,
            )
            planning_root = workdir / f"planning-{attempt}"
            planning_root.mkdir()
            planning = plan_update(
                target,
                planning_root,
                run_inputs,
                old_stage,
                retained,
                product_paths,
                stage,
            )
            referenced = referenced_removals(
                target, planning, layout_moves, retiring
            )
            if set(referenced) <= set(product_paths):
                break
            product_paths = tuple(sorted({*product_paths, *referenced}))
        if planning.restored:
            run_inputs = replace(
                run_inputs, restored=restored_record(stage, planning.restored)
            )
        # A workflow this update retires is not a product workflow, so its
        # pins never ask for a product commit (#1083).
        pins = action_pin_preflight.excluding(pins, retiring)
        if pins.blocking and not (args.check or args.dry_run):
            raise CliError(action_pin_preflight.drift_error(pins))
        files = planned_update_files(target, planning, layout_moves, retiring)
        transitions = update_transitions(
            target, planning, layout_moves, retiring
        )
        # Rendered files the target's ignore rules would hide stop the
        # apply; list them now (Issue #1146 AC4).
        ignored_payload = planned_ignored_payload(target, run_inputs.payload)
        # A kept product Release writer must not lose the files the layout
        # migration moves (Issue #1153).
        writer_moves = release_writer_moves(
            target,
            product_release_workflow(answers),
            effective_layout_moves(
                layout_moves, {*planning.retained, *planning.shims}
            ),
        )
        # A kept legacy script must not lose the files the same plan
        # removes or moves without a shim (Issue #1157).
        retained_uses = retained_script_uses(
            target,
            planning.retained,
            (*retiring, *planning.delete),
            effective_layout_moves(
                layout_moves, {*planning.retained, *planning.shims}
            ),
        )
        # take-new decisions resolve to the reviewed new-side render, with
        # the template pins the apply aligns to kept newer product pins
        # already raised, so conflicts/new is what take-new writes (#1153).
        new_side = {
            name: action_pin_preflight.align_content(
                name,
                (stage / name).read_bytes()
                if (stage / name).is_file() and not (stage / name).is_symlink()
                else None,
                run_inputs.pin_alignment,
            )
            for name in planning.conflicts
        }
        conflict_sides = update_conflict_sides(
            target, old_stage, new_side, layout_moves
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
    answers_changed = answers != current_answers
    capabilities_changed = target_capabilities != current_capabilities
    update_available = bool(status["update_available"]) or any(
        (answers_changed, capabilities_changed)
    )
    status.update(
        {
            "action_pin_preflight": pins.as_dict(),
            "ignored_payload": ignored_payload,
            "release_writer_moves": writer_moves,
            "retained_uses": retained_uses,
            "answers_changed": answers_changed,
            "capabilities_changed": capabilities_changed,
            "planning": planning.as_dict(),
            "status": "outdated" if update_available else "current",
            "update_available": update_available,
            "project_verification_hook": hook,
        }
    )
    governance_drift_recommendation = governance_drift_update_recommendation(
        saved_answers, explicit_data
    )
    if governance_drift_recommendation is not None:
        status["governance_drift_recommendation"] = (
            governance_drift_recommendation
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
        files=files,
        update=status,
    )
    if target_snapshot:
        report_head = cast(str, target_snapshot["target_head"])
        report_changes = cast(list[str], target_snapshot["target_changes"])
    else:
        report_head, report_changes_tuple, _digest = target_state(target)
        report_changes = list(report_changes_tuple)
    report_directory = lifecycle_report_directory(
        target, args.report_dir, "update"
    )
    plan_payload = adoption_plan_payload(plan)
    update_report = lifecycle_report_model(
        plan,
        operation="update",
        plan_name=UPDATE_PLAN_BASENAME,
        plan_sha256=str(plan_payload["plan_sha256"]),
        generated_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
        plan_path=report_directory / UPDATE_PLAN_BASENAME,
        before=current_answers,
        explicit=tuple(explicit_data),
        previous=current_revision,
        target_head=report_head,
        target_changes=report_changes,
        observed=observed,
        pin_versions=pins.versions,
        ignore_gaps=missing_ignore_rules(conflict_sides),
    )
    if args.finalize_plan:
        print_plan(plan)
        return write_update_final_plan(
            args,
            FinalPlanContext(
                target=target,
                report_directory=report_directory,
                plan=plan,
                planning=planning,
                run_inputs=run_inputs,
                transitions=transitions,
                update_report=update_report,
                target_snapshot=target_snapshot,
                current=current_revision,
                previous=previous,
                explicit_data=explicit_data,
                new_side=new_side,
            ),
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
        write_conflict_sides(report_directory, conflict_sides)
        write_lifecycle_reports(
            report_directory,
            operation="update",
            plan_name=UPDATE_PLAN_BASENAME,
            plan_payload=plan_payload,
            report=update_report,
            emit=not args.json,
        )
        return 1 if status["update_available"] else 0
    write_conflict_sides(report_directory, conflict_sides)
    write_lifecycle_reports(
        report_directory,
        operation="update",
        plan_name=UPDATE_PLAN_BASENAME,
        plan_payload=plan_payload,
        report=update_report,
        emit=True,
    )

    print_plan(plan)
    print(
        "Update planning digest: "
        f"{planning.digest()} (old side "
        f"{old_side.as_dict()['answers_sha256']}, render parity "
        f"{planning.render_parity})."
    )
    milestone_plan = milestone_description_plan(target)
    if args.dry_run:
        return 0
    if planning.conflicts:
        raise CliError(update_conflict_error(planning.conflicts))
    if not confirm(args):
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
        # The apply run reuses the reviewed planning inputs verbatim; only
        # template tasks, which the side-effect-free plan skips, differ.
        applied = run_update_candidate(
            target,
            temporary_root,
            run_inputs,
            working_tree=False,
            skip_tasks=False,
        )
        if applied.returncode != 0 or applied.conflicts:
            raise CliError(
                update_conflict_error(applied.conflicts, applied.output)
            )
        divergence = update_plan.realized_divergence(
            planning, applied.changes, applied.conflicts
        )
        if divergence:
            raise CliError(
                "Update apply diverged from the reviewed plan ("
                + "; ".join(divergence)
                + "); the target was not changed. Create a new plan."
            )
        candidate = applied.candidate
        pin_answer_commit(candidate, str(status["target_sha"]))
        persist_release_answers(candidate, answers, decisions)
        verify_project(candidate)
        write_provenance(candidate, target_revision, previous, answers=answers)
        artifacts, delete_paths = candidate_patch_effects(candidate)
        apply_update_transitions(
            target,
            candidate,
            transitions,
            artifacts,
            delete_paths,
            target_snapshot,
        )
    settings_plan(target)
    apply_milestone_description_plan(milestone_plan)
    write_lifecycle_reports(
        report_directory,
        operation="update",
        plan_name=UPDATE_PLAN_BASENAME,
        plan_payload=None,
        report=applied_lifecycle_report(
            update_report,
            str(plan_payload["plan_sha256"]),
            datetime.now(UTC).replace(microsecond=0).isoformat(),
        ),
        emit=True,
    )
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
        subparser.add_argument(
            "--channel",
            choices=release_phase.PHASES,
            default="stable",
            help="select latest stable (default) or opt in to latest beta",
        )
        subparser.add_argument("--source")
        subparser.add_argument("--expected-sha", metavar="FULL_SHA")
        subparser.add_argument("--allow-unreleased", action="store_true")
        subparser.add_argument(
            "--data", action="append", default=[], metavar="KEY=VALUE"
        )
        subparser.add_argument("--json", action="store_true")
        # Issue #1078: one-time setup inputs; none of them is saved.
        subparser.add_argument(
            "--preset",
            choices=setup_plan.WORK_MODES,
            help=(
                "work mode to expand into saved settings (default "
                f"{setup_plan.DEFAULT_WORK_MODE}); explicit --data wins"
            ),
        )
        subparser.add_argument(
            "--confirm-second-approver",
            action="store_true",
            help=(
                "one-time: another maintainer can approve when the approval "
                "route read is inconclusive"
            ),
        )
        subparser.add_argument(
            "--confirm-copilot-entitlement",
            action="store_true",
            help=(
                "one-time: the repository has Copilot code review "
                "entitlement for a Copilot-only approval route"
            ),
        )
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
                    "write or update the adoption Markdown report "
                    "outside the repo (dry-run, then applied)"
                ),
            )
        add_write_options(subparser)

    update = subparsers.add_parser(
        "update", help="check or apply a smart update"
    )
    update.add_argument("path", nargs="?", type=Path, default=Path.cwd())
    update.add_argument("--to", metavar="RELEASE_OR_SHA")
    update.add_argument(
        "--channel",
        choices=release_phase.PHASES,
        default="stable",
        help="select latest stable (default) or opt in to latest beta",
    )
    update.add_argument("--expected-sha", metavar="FULL_SHA")
    update.add_argument("--from-release", metavar="RELEASE")
    update.add_argument("--accept-legacy", action="store_true")
    update.add_argument("--allow-unreleased", action="store_true")
    update.add_argument("--check", action="store_true")
    update.add_argument("--json", action="store_true")
    update.add_argument(
        "--report-dir",
        type=Path,
        metavar="PATH",
        help=(
            "write the update plan and report outside the repo "
            "(planned, then applied)"
        ),
    )
    update.add_argument(
        "--data", action="append", default=[], metavar="KEY=VALUE"
    )
    update.add_argument(
        "--finalize-plan",
        action="store_true",
        help=(
            "record conflict and pin decisions as the immutable final plan "
            "beside the stage-1 plan"
        ),
    )
    update.add_argument(
        "--decision",
        action="append",
        default=[],
        metavar="PATH=keep-current|take-new|custom:FILE",
        help="decide one stage-1 conflict (with --finalize-plan)",
    )
    update.add_argument(
        "--pin-commit",
        metavar="FULL_SHA",
        help="product commit that resolves the listed action pin drift",
    )
    update.add_argument(
        "--apply-plan",
        type=Path,
        metavar="PATH",
        help="apply one unchanged final plan from --finalize-plan",
    )
    add_write_options(update)

    status = subparsers.add_parser(
        "status",
        help=(
            "classify repository state as adoption-pending, create, adopt, "
            "migrate, update, current, or policy-only-update"
        ),
    )
    status.add_argument("path", nargs="?", type=Path, default=Path.cwd())
    status.add_argument("--to", metavar="RELEASE_OR_SHA")
    status.add_argument(
        "--channel",
        choices=release_phase.PHASES,
        default="stable",
        help="select latest stable (default) or opt in to latest beta",
    )
    status.add_argument("--expected-sha", metavar="FULL_SHA")
    status.add_argument("--from-release", metavar="RELEASE")
    status.add_argument("--accept-legacy", action="store_true")
    status.add_argument("--allow-unreleased", action="store_true")
    status.add_argument("--json", action="store_true")
    status.add_argument(
        "--confirm-governance-baseline",
        metavar="FULL_SHA",
        help=(
            "one-time: accept one listed candidate when the governance "
            "baseline is inconclusive"
        ),
    )
    issue = subparsers.add_parser(
        "issue", help="create a governed Issue (SPEC-010 risk block)"
    )
    issue_commands = issue.add_subparsers(dest="issue_command", required=True)
    issue_create = issue_commands.add_parser(
        "create",
        help="check or guide the risk block, then run gh issue create",
    )
    issue_create.add_argument("--body-out", type=Path, metavar="FILE")
    issue_create.add_argument(
        "--target-date",
        default="",
        metavar="YYYY-MM-DD",
        help="Project target when the Issue has no Milestone due date",
    )
    issue_create.add_argument(
        "gh_arguments", nargs=argparse.REMAINDER, metavar="-- GH_ARGS"
    )
    sync_project = issue_commands.add_parser(
        "sync-project",
        help="sync Roadmap dates to the configured github_project_url",
    )
    selection = sync_project.add_mutually_exclusive_group(required=True)
    selection.add_argument("--issue", type=int)
    selection.add_argument("--milestone", type=int)
    sync_project.add_argument("--target-date", default="", metavar="YYYY-MM-DD")
    sync_project.add_argument("--repo", default="", metavar="OWNER/NAME")
    sync_project.add_argument(
        "--yes", action="store_true", help="confirm listed date overwrites"
    )
    risk = subparsers.add_parser(
        "risk", help="read-only risk suggestions, register, and backfill"
    )
    risk_commands = risk.add_subparsers(dest="risk_command", required=True)
    risk_suggest = risk_commands.add_parser("suggest")
    target = risk_suggest.add_mutually_exclusive_group(required=True)
    target.add_argument("--issue", type=int)
    target.add_argument("--open", action="store_true")
    risk_register = risk_commands.add_parser("register")
    risk_register.add_argument("--milestone", type=int)
    risk_register.add_argument(
        "--state", choices=("open", "closed", "all"), default="open"
    )
    risk_backfill = risk_commands.add_parser("backfill")
    risk_backfill.add_argument("--milestone", type=int)
    risk_backfill.add_argument("--out", type=Path, metavar="FILE")
    risk_backfill.add_argument("--verify", type=Path, metavar="FILE")
    risk_backfill.add_argument("--digest", metavar="SHA256")
    for command in (risk_suggest, risk_register, risk_backfill):
        command.add_argument("--repo", default="", metavar="OWNER/NAME")
        command.add_argument("--json", action="store_true")
    return result


def command_risk(args: argparse.Namespace) -> int:  # noqa: C901
    """Run `csarc issue create` or one read-only `csarc risk` command."""
    if args.command == "issue" and args.issue_command == "sync-project":
        return project_roadmap.command_sync(
            args.repo,
            issue=args.issue,
            milestone=args.milestone,
            target_date=args.target_date,
            confirm=args.yes,
            ask=input if sys.stdin.isatty() else None,
        )
    if args.command == "issue":
        gh_arguments = list(args.gh_arguments)
        if gh_arguments[:1] == ["--"]:
            gh_arguments = gh_arguments[1:]
        url = project_roadmap.configured_project_url()
        if not url or args.body_out is not None:
            # An empty github_project_url never calls a Project API (#1080).
            return risk_tools.issue_create(gh_arguments, args.body_out)
        target = (
            project_roadmap.checked_date(args.target_date)
            if args.target_date
            else ""
        )
        before, after = project_roadmap.create_hooks(url, target)
        return risk_tools.issue_create(
            gh_arguments, None, before=before, after=after
        )
    if args.risk_command == "suggest":
        found = risk_tools.suggest(args.repo, issue=args.issue)
        if args.json:
            print(json.dumps(found, ensure_ascii=False, indent=2))
        for item in [] if args.json else found:
            print(
                f"#{item['issue']}: "
                + (
                    f"exempt ({item['exempt_reason']})"
                    if item["exempt_reason"]
                    else "; ".join(item["problems"]) or "valid"
                )
            )
            if item["suggestion"]:
                print(item["suggestion"])
        return 0
    if args.risk_command == "register":
        data = risk_tools.register(
            args.repo, milestone=args.milestone, state=args.state
        )
        print(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
            if args.json
            else risk_tools.render_register(data),
            end="\n" if args.json else "",
        )
        return 0
    if args.verify is not None:
        if not args.digest:
            raise CliError("--verify needs the saved --digest")
        problems = risk_tools.verify_backfill(args.verify, args.digest)
        for line in problems:
            print(f"risk backfill: {line}", file=sys.stderr)
        return 1 if problems else 0
    if args.milestone is None:
        raise CliError("risk backfill needs --milestone or --verify")
    manifest = risk_tools.backfill(args.repo, args.milestone)
    data = risk_tools.canonical(manifest)
    if args.out is not None:
        args.out.write_bytes(data)
    elif args.json:
        print(data.decode("utf-8"))
    print(f"digest: {risk_tools.manifest_digest(manifest)}")
    return 0


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
        if args.command in {"issue", "risk"}:
            return command_risk(args)
        if args.json and not args.check:
            raise CliError("--json is only valid with update --check.")
        return command_update(args)
    except (
        CliError,
        risk_tools.RiskToolError,
        project_roadmap.ProjectSyncError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
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
