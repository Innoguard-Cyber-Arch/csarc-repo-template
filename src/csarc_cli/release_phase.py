#!/usr/bin/env python3
"""Shared beta/stable release format and early/formal maturity (Issue #918).

Release channel and project maturity are independent axes:

    beta    X.Y.Z-beta.N   (GitHub pre-release)
    stable  X.Y.Z          (GitHub latest candidate)
    early   stable major == 0
    formal  stable major >= 1

Historical alpha tags are migrated out-of-band. They are intentionally not
part of this public parser, so unknown or retired versions fail closed.

Shared verbatim between the root repository, `template/.csarc/scripts/` (see
AGENTS.md's "Keep shared policy changes synchronized between root and
template/" rule), and `src/csarc_cli/release_phase.py`. The third copy
exists only because the distributed `csarc` wheel ships `src/csarc_cli`
alone (see `[tool.hatch.build.targets.wheel]` in pyproject.toml) -- the
CLI cannot import a sibling repository adapter module that will not be present
once installed. Keep all three copies byte-identical.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

PHASES = ("beta", "stable")
MATURITIES = ("early", "formal")
PRERELEASE_PHASES = ("beta",)

# Canonical SemVer form used everywhere except PEP 440 (Python) surfaces.
_VERSION_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<phase>beta)\.(?P<n>[1-9]\d*))?$"
)


class ReleasePhaseError(ValueError):
    """A version string or requested channel is not legal under Issue #918."""


@dataclass(frozen=True)
class ParsedVersion:
    """One parsed ``X.Y.Z`` or ``X.Y.Z-beta.N`` version."""

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
        """Return whether this version carries a beta suffix."""
        return self.phase is not None

    @property
    def release_kind(self) -> str:
        """Return the canonical public channel for this version."""
        return "beta" if self.phase is not None else "stable"

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
        core version; beta sequence numbers compare numerically.
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
    ``X.Y.Z`` or ``X.Y.Z-beta.N`` shape -- this is the one
    fail-closed gate every other check in this module builds on.
    """
    stripped = text[1:] if text[:1] in {"v", "V"} else text
    match = _VERSION_RE.fullmatch(stripped)
    if match is None:
        raise ReleasePhaseError(
            f"invalid release version {text!r}; expected X.Y.Z or X.Y.Z-beta.N"
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
    """Return the canonical ``X.Y.Z`` or ``X.Y.Z-beta.N`` string."""
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

    PEP 440 has no hyphenated ``-beta.N`` pre-release segment; its
    normalized form is a bare letter and number instead (``0.16.0b1``).
    Only a "python" release-please package's
    `pyproject.toml`/`uv.lock` need this form; every other surface (Git
    tag, GitHub Release name, CHANGELOG heading, `package.json`,
    `Cargo.toml`) uses the canonical SemVer string from `format_version`
    unchanged (both Node and Rust's own SemVer implementations accept a
    hyphenated pre-release segment natively).
    """
    if phase is None:
        return format_version(major, minor, patch, None, None)
    letter = {"beta": "b"}.get(phase)
    if letter is None or not isinstance(n, int) or n < 1:
        raise ReleasePhaseError(
            f"cannot render a PEP 440 version for phase {phase!r}"
        )
    return f"{major}.{minor}.{patch}{letter}{n}"


# The mirror image of `_VERSION_RE`'s hyphenated `-beta.N` shape: the compact
# form `format_pep440` produces (`0.16.0b1`).
_PEP440_COMPACT_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:(?P<letter>b)(?P<n>[1-9]\d*))?$"
)
_PEP440_LETTER_TO_PHASE = {"b": "beta"}


def parse_pep440(text: str) -> ParsedVersion:
    """Parse a PEP 440-normalized version string (Issue #744).

    `parse_version` only accepts the canonical hyphenated form; this is
    its mirror image for the compact form `format_pep440` produces.
    Needed wherever a Python packaging surface's on-disk value
    (`pyproject.toml`, `uv.lock`, `src/<package>/__init__.py`) must be
    compared against a canonical-form surface (see `normalize` below).
    """
    stripped = text[1:] if text[:1] in {"v", "V"} else text
    match = _PEP440_COMPACT_RE.fullmatch(stripped)
    if match is None:
        raise ReleasePhaseError(
            f"invalid PEP 440 version {text!r}; expected X.Y.Z or X.Y.Zb1"
        )
    letter = match.group("letter")
    n = match.group("n")
    return ParsedVersion(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        phase=_PEP440_LETTER_TO_PHASE[letter] if letter else None,
        n=int(n) if n is not None else None,
    )


def normalize(text: str) -> str:
    """Return `text`'s canonical SemVer form, accepting either shape.

    Every release surface must ultimately agree on one version regardless
    of whether it is written in the canonical form (``0.16.0-beta.1``,
    used everywhere) or the PEP 440-normalized form (``0.16.0b1``, used only
    by a Python packaging surface per `format_pep440`). This tries
    `parse_version` first and falls back to `parse_pep440`, so a caller
    that needs to compare surfaces written in either shape (e.g. a
    generated project's own release-consistency check across
    the release-please manifest, `pyproject.toml`, `package.json`,
    and `Cargo.toml`) has one common key to compare.
    """
    try:
        parsed = parse_version(text)
    except ReleasePhaseError:
        parsed = parse_pep440(text)
    return parsed.format()


def validate_declared_phase(
    version: str, declared_phase: str, maturity: str | None = None
) -> ParsedVersion:
    """Fail closed unless ``version`` matches its channel and maturity."""
    if declared_phase not in PHASES:
        raise ReleasePhaseError(
            f"unknown release phase {declared_phase!r}; expected one of "
            + ", ".join(PHASES)
        )
    parsed = parse_version(version)
    if maturity is not None and maturity not in MATURITIES:
        raise ReleasePhaseError(
            f"unknown project maturity {maturity!r}; expected one of "
            + ", ".join(MATURITIES)
        )
    if declared_phase == "beta":
        if parsed.phase != "beta":
            raise ReleasePhaseError(
                f"{version} does not carry the declared beta suffix"
            )
    elif parsed.phase is not None:
        raise ReleasePhaseError(
            f"{version} carries a {parsed.phase} suffix but {declared_phase} "
            "releases must be unsuffixed"
        )
    if maturity == "early" and parsed.major != 0:
        raise ReleasePhaseError(
            f"{version} has major version {parsed.major}; an early release "
            "requires major version 0"
        )
    if maturity == "formal" and parsed.major == 0:
        raise ReleasePhaseError(
            f"{version} has major version 0; a formal release requires "
            "major version >= 1"
        )
    return parsed


def next_prerelease_n(
    existing: Iterable[str], major: int, minor: int, patch: int, phase: str
) -> int:
    """Return the next `.N` for `major.minor.patch` + `phase`, starting at 1.

    Residual race, accepted rather than fixed here: `existing` is a
    snapshot of local git tags taken before the caller (typically
    the sibling `converge-release-tag` adapter) actually pushes the new tag,
    so two
    concurrent callers could compute the same "next" N. This is mitigated,
    not eliminated: `converge-release-tag` creates the tag via `gh api
    POST .../git/refs`, which fails outright on a name collision rather
    than silently overwriting one, and the one caller that currently
    passes a declared `--phase` at all is a local/guided invocation (see
    `release_policy.py`'s `plan`/`prepare-candidate`), not the automated
    push-triggered path -- concurrent guided publishes of the same
    major.minor.patch+phase are an unlikely, human-driven race, not a
    routine one. A full distributed-lock fix (e.g. re-checking the
    remote's tag list immediately before push and retrying once on a
    collision) would be disproportionate to that residual risk; revisit
    if `--phase` ever gets wired into the automated path.
    """
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
    core_version: str,
    phase: str,
    existing: Iterable[str] = (),
    *,
    maturity: str | None = None,
) -> str:
    """Return the version string for `core_version` (plain X.Y.Z) at `phase`.

    For beta this appends the next `.N` for that exact X.Y.Z channel
    combination (existing published versions are consulted so a tag name
    is never reused). For stable the core version is returned unchanged.
    The result is always re-validated through `validate_declared_phase`.
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
    validate_declared_phase(candidate, phase, maturity)
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


def select_latest(
    versions: Iterable[str], channel: str | None = None
) -> str | None:
    """Return the latest readable version, optionally within one channel."""
    if channel not in {None, *PHASES}:
        raise ReleasePhaseError(f"unknown release channel: {channel!r}")
    readable = []
    for raw in versions:
        try:
            parsed = parse_version(raw)
        except ReleasePhaseError:
            continue
        if channel is None or parsed.release_kind == channel:
            readable.append(raw)
    ordered = sort_by_precedence(readable)
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

    Keep every unsuffixed stable version, unconditionally. For
    pre-releases, only the single highest-precedence pre-release within
    the *newest* major.minor group that has one is kept ("the latest
    pre-release string"); every other pre-release -- older pre-releases in
    that same newest group, and every pre-release belonging to an older
    major.minor group ("a string", per the Issue's own wording) -- is
    marked for deletion. Malformed version strings are ignored rather than
    raising, since a retention listing must survive one bad tag among many.

    Deliberate single-active-line assumption: the maintainer decision this
    mirrors keeps exactly the *one* latest pre-release string (singular),
    not the latest pre-release of every major.minor group that still has
    recent activity. If two major.minor lines are both genuinely being
    pre-released concurrently (e.g. a maintenance line and a next line),
    the numerically older line's pre-releases are still marked for
    deletion here even though it may still be in active use -- this
    function has no way to distinguish "abandoned" from "still
    maintained" beyond the version number itself. This is a dry-run
    lister only (see `RetentionDecision`'s own docstring): nothing is ever
    deleted automatically, so a maintainer reviewing the listing before
    acting is exactly the point at which a genuinely active older line
    gets a chance to be kept anyway. See
    docs/adr/release-security-and-dependencies.md's dated section on this
    Issue for the decision this mirrors.
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
