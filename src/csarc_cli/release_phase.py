#!/usr/bin/env python3
"""Shared release-phase version format: alpha/beta/early/formal (Issue #744).

Maintainer decision (2026-09-17): the version number itself encodes release
maturity instead of a side channel like `policies/project-stage.json`'s
`release_phase` (that file governs a *different* axis -- Ruleset/review
bypass scope -- and is untouched by this module; see
`scripts/release_phase_rulesets.py`).

    alpha   X.Y.Z-alpha.N   (any major; a later pre-release of the same
    beta    X.Y.Z-beta.N     X.Y.Z increments N -- tag names are never
                              reused once published)
    early   X.Y.Z            (major == 0, no suffix)
    formal  X.Y.Z            (major >= 1, no suffix)

Alpha or beta can be published at any time, including after an early or
formal release has already shipped for a higher X.Y.Z. This module only
maps a *given* declared phase to a version string and validates the
result; deciding which phase a release deserves (the declaration/
computation mechanism) is Issue #745's job.

Shared verbatim between the root repository, `template/scripts/` (see
AGENTS.md's "Keep shared policy changes synchronized between root and
template/" rule), and `src/csarc_cli/release_phase.py`. The third copy
exists only because the distributed `csarc` wheel ships `src/csarc_cli`
alone (see `[tool.hatch.build.targets.wheel]` in pyproject.toml) -- the
CLI cannot import a sibling `scripts/` module that will not be present
once installed. Keep all three copies byte-identical.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

PHASES = ("alpha", "beta", "early", "formal")
PRERELEASE_PHASES = ("alpha", "beta")

# Canonical SemVer form used everywhere except PEP 440 (Python) surfaces.
_VERSION_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<phase>alpha|beta)\.(?P<n>[1-9]\d*))?$"
)


class ReleasePhaseError(ValueError):
    """A version string or requested phase is not legal under Issue #744."""


@dataclass(frozen=True)
class ParsedVersion:
    """One parsed `X.Y.Z` or `X.Y.Z-{alpha,beta}.N` version."""

    major: int
    minor: int
    patch: int
    phase: str | None
    n: int | None

    @property
    def core(self) -> tuple[int, int, int]:
        """Return the (major, minor, patch) tuple, ignoring any suffix."""
        return (self.major, self.minor, self.patch)

    @property
    def is_prerelease(self) -> bool:
        """Return whether this version carries an alpha/beta suffix."""
        return self.phase is not None

    @property
    def release_kind(self) -> str:
        """Classify this version as alpha/beta/early/formal.

        `early` and `formal` are both unsuffixed; the split is purely by
        major version, per Issue #744's legality rule ("主版本號為 0 時
        不帶後綴即視為早期版; 主版本號 >= 1 時不帶後綴即視為正式版").
        """
        if self.phase is not None:
            return self.phase
        return "early" if self.major == 0 else "formal"

    def core_string(self) -> str:
        """Return the unsuffixed `X.Y.Z` form."""
        return f"{self.major}.{self.minor}.{self.patch}"

    def format(self) -> str:
        """Return the canonical SemVer string for this version."""
        return format_version(
            self.major, self.minor, self.patch, self.phase, self.n
        )

    def precedence_key(self) -> tuple[int, int, int, int, str, int]:
        """Return a sortable key implementing SemVer precedence.

        A release (no suffix) always outranks any pre-release of the same
        core version; among pre-releases, the phase name compares
        alphabetically ("alpha" < "beta", matching maturity order) and
        then the numeric `.N` field compares numerically.
        """
        is_release = 1 if self.phase is None else 0
        return (
            self.major,
            self.minor,
            self.patch,
            is_release,
            self.phase or "",
            self.n or 0,
        )


def parse_version(text: str) -> ParsedVersion:
    """Parse a canonical version string (an optional leading 'v' is fine).

    Raises `ReleasePhaseError` for anything that doesn't match the exact
    `X.Y.Z` or `X.Y.Z-alpha.N` / `X.Y.Z-beta.N` shape -- this is the one
    fail-closed gate every other check in this module builds on.
    """
    stripped = text[1:] if text[:1] in {"v", "V"} else text
    match = _VERSION_RE.fullmatch(stripped)
    if match is None:
        raise ReleasePhaseError(
            f"invalid release version {text!r}; expected X.Y.Z or "
            "X.Y.Z-alpha.N / X.Y.Z-beta.N"
        )
    phase = match.group("phase")
    n = match.group("n")
    return ParsedVersion(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        phase=phase,
        n=int(n) if n is not None else None,
    )


def is_valid_version(text: str) -> bool:
    """Return whether `text` is a well-formed version under this module."""
    try:
        parse_version(text)
    except ReleasePhaseError:
        return False
    return True


def format_version(
    major: int, minor: int, patch: int, phase: str | None, n: int | None
) -> str:
    """Return the canonical `X.Y.Z` or `X.Y.Z-{alpha,beta}.N` string."""
    if phase is None:
        if n is not None:
            raise ReleasePhaseError(
                "a stable version cannot carry a pre-release number"
            )
        return f"{major}.{minor}.{patch}"
    if phase not in PRERELEASE_PHASES:
        raise ReleasePhaseError(f"unsupported pre-release phase: {phase!r}")
    if not isinstance(n, int) or n < 1:
        raise ReleasePhaseError(
            "a pre-release version requires a positive integer N"
        )
    return f"{major}.{minor}.{patch}-{phase}.{n}"


def format_pep440(
    major: int, minor: int, patch: int, phase: str | None, n: int | None
) -> str:
    """Return the PEP 440-normalized form for Python package surfaces.

    PEP 440 has no hyphenated `-alpha.N`/`-beta.N` pre-release segment; its
    normalized form is a bare letter and number instead
    (`0.16.0a1` / `0.16.0b1`). Only a "python" release-please package's
    `pyproject.toml`/`uv.lock` need this form; every other surface (Git
    tag, GitHub Release name, CHANGELOG heading, `package.json`,
    `Cargo.toml`) uses the canonical SemVer string from `format_version`
    unchanged (both Node and Rust's own SemVer implementations accept a
    hyphenated pre-release segment natively).
    """
    if phase is None:
        return format_version(major, minor, patch, None, None)
    letter = {"alpha": "a", "beta": "b"}.get(phase)
    if letter is None or not isinstance(n, int) or n < 1:
        raise ReleasePhaseError(
            f"cannot render a PEP 440 version for phase {phase!r}"
        )
    return f"{major}.{minor}.{patch}{letter}{n}"


def validate_declared_phase(version: str, declared_phase: str) -> ParsedVersion:
    """Fail closed unless `version` legally represents `declared_phase`.

    `declared_phase` must be one of `PHASES` ("alpha", "beta", "early",
    "formal"). Implements Issue #744's legality rule: a suffix is only
    ever `alpha.N` or `beta.N`; an unsuffixed version is "early" only when
    its major version is 0, and "formal" only when its major version is
    >= 1.
    """
    if declared_phase not in PHASES:
        raise ReleasePhaseError(
            f"unknown release phase {declared_phase!r}; expected one of "
            + ", ".join(PHASES)
        )
    parsed = parse_version(version)
    if declared_phase in PRERELEASE_PHASES:
        if parsed.phase != declared_phase:
            raise ReleasePhaseError(
                f"{version} does not carry the declared {declared_phase} suffix"
            )
        return parsed
    if parsed.phase is not None:
        raise ReleasePhaseError(
            f"{version} carries a {parsed.phase} suffix but {declared_phase} "
            "releases must be unsuffixed"
        )
    if declared_phase == "early" and parsed.major != 0:
        raise ReleasePhaseError(
            f"{version} has major version {parsed.major}; an early release "
            "requires major version 0 (declare formal instead)"
        )
    if declared_phase == "formal" and parsed.major == 0:
        raise ReleasePhaseError(
            f"{version} has major version 0; a formal release requires "
            "major version >= 1 (declare early instead, or bump a "
            "breaking change first)"
        )
    return parsed


def next_prerelease_n(
    existing: Iterable[str], major: int, minor: int, patch: int, phase: str
) -> int:
    """Return the next `.N` for `major.minor.patch` + `phase`, starting at 1."""
    highest = 0
    for raw in existing:
        try:
            parsed = parse_version(raw)
        except ReleasePhaseError:
            continue
        if parsed.core == (major, minor, patch) and parsed.phase == phase:
            highest = max(highest, parsed.n or 0)
    return highest + 1


def phase_version(
    core_version: str, phase: str, existing: Iterable[str] = ()
) -> str:
    """Return the version string for `core_version` (plain X.Y.Z) at `phase`.

    For alpha/beta this appends the next `.N` for that exact X.Y.Z+phase
    combination (existing published versions are consulted so a tag name
    is never reused, per Issue #744 decision 1). For early/formal the core
    version is returned unchanged. The result is always re-validated
    through `validate_declared_phase` so this function itself fails closed
    on an inconsistent request (e.g. `phase="early"` with a major-1 core).
    """
    parsed_core = parse_version(core_version)
    if parsed_core.phase is not None:
        raise ReleasePhaseError(
            f"{core_version} is not a plain X.Y.Z core version"
        )
    if phase in PRERELEASE_PHASES:
        n = next_prerelease_n(
            existing,
            parsed_core.major,
            parsed_core.minor,
            parsed_core.patch,
            phase,
        )
        candidate = format_version(
            parsed_core.major, parsed_core.minor, parsed_core.patch, phase, n
        )
    else:
        candidate = core_version
    validate_declared_phase(candidate, phase)
    return candidate


def sort_by_precedence(versions: Iterable[str]) -> list[str]:
    """Return only the well-formed versions, ascending by SemVer precedence."""
    parsed = []
    for raw in versions:
        try:
            parsed.append((parse_version(raw), raw))
        except ReleasePhaseError:
            continue
    parsed.sort(key=lambda item: item[0].precedence_key())
    return [raw for _, raw in parsed]


def select_latest(versions: Iterable[str]) -> str | None:
    """Return the highest-precedence version, or None if none are well-formed.

    Used in place of GitHub's `releases/latest` API, which never returns a
    `prerelease: true` Release and therefore cannot see an alpha/beta tag.
    """
    ordered = sort_by_precedence(versions)
    return ordered[-1] if ordered else None


@dataclass(frozen=True)
class RetentionDecision:
    """One Release's retention classification (dry-run only; #744 group 3).

    Nothing in this module deletes anything -- callers decide what, if
    anything, to do with the result, and the actual deletion of any
    existing GitHub Release remains a manual, post-promotion maintainer
    action per Issue #744.
    """

    version: str
    keep: bool
    reason: str


def retention_plan(versions: Iterable[str]) -> list[RetentionDecision]:
    """Classify every version as keep/delete under Issue #744 decision 5.

    Keep every unsuffixed (early or formal) version, unconditionally. For
    pre-releases, only the single highest-precedence pre-release within
    the *newest* major.minor group that has one is kept ("the latest
    pre-release string"); every other pre-release -- older pre-releases in
    that same newest group, and every pre-release belonging to an older
    major.minor group ("a string", per the Issue's own wording) -- is
    marked for deletion. Malformed version strings are ignored rather than
    raising, since a retention listing must survive one bad tag among many.
    """
    parsed: list[tuple[ParsedVersion, str]] = []
    for raw in versions:
        try:
            parsed.append((parse_version(raw), raw))
        except ReleasePhaseError:
            continue

    decisions: dict[str, RetentionDecision] = {}
    stable = [
        (version, raw) for version, raw in parsed if version.phase is None
    ]
    prereleases = [
        (version, raw) for version, raw in parsed if version.phase is not None
    ]

    for version, raw in stable:
        decisions[raw] = RetentionDecision(
            raw,
            True,
            f"unsuffixed {version.release_kind} release is always kept",
        )

    if prereleases:
        newest_group = max(version.core[:2] for version, _ in prereleases)
        group_items = sorted(
            (
                (version, raw)
                for version, raw in prereleases
                if version.core[:2] == newest_group
            ),
            key=lambda item: item[0].precedence_key(),
        )
        _latest_version, latest_raw = group_items[-1]
        decisions[latest_raw] = RetentionDecision(
            latest_raw,
            True,
            "latest pre-release string in the newest major.minor group "
            f"{newest_group[0]}.{newest_group[1]}",
        )
        for version, raw in prereleases:
            if raw == latest_raw:
                continue
            group = version.core[:2]
            if group == newest_group:
                reason = (
                    "superseded by a newer pre-release in the same "
                    f"{group[0]}.{group[1]} major.minor group"
                )
            else:
                reason = (
                    f"pre-release belongs to an older major.minor group "
                    f"({group[0]}.{group[1]}) than the newest "
                    f"({newest_group[0]}.{newest_group[1]})"
                )
            decisions[raw] = RetentionDecision(raw, False, reason)

    return [decisions[raw] for _, raw in parsed]
