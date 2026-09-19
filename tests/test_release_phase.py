"""Regression tests for scripts/release_phase.py (Issue #744).

Covers the maintainer-decided version-to-phase mapping directly: parsing,
formatting (canonical SemVer and PEP 440), legality checks, `.N`
increment, SemVer-precedence selection, and the dry-run retention rule.
"""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Load scripts/release_phase.py by path (like tests/test_release_policy.py and
# tests/test_ci_tier.py do for their own scripts/ modules) rather than a static
# `import release_phase`. scripts/*.py are not an installed, importable
# package: they only exist on disk. A real `import` statement is something
# `ty check` tries to statically resolve against the project's own search
# paths -- and this same test file is shipped into every generated/adopted
# downstream project's tests/ directory (Issue #744's paired-file mechanism),
# where scripts/ is never on that path, so a static import fails project
# verification there even though it works fine under pytest's sys.path
# handling in this repository.
rp = SimpleNamespace(
    **runpy.run_path(str(ROOT / "scripts" / "release_phase.py"))
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.2.3", rp.ParsedVersion(1, 2, 3, None, None)),
        ("v1.2.3", rp.ParsedVersion(1, 2, 3, None, None)),
        ("0.16.0-alpha.1", rp.ParsedVersion(0, 16, 0, "alpha", 1)),
        ("v0.16.0-beta.12", rp.ParsedVersion(0, 16, 0, "beta", 12)),
    ],
)
def test_parse_version_accepts_legal_shapes(
    text: str, expected: rp.ParsedVersion
) -> None:
    """Parse both plain and phase-suffixed versions, with or without 'v'."""
    assert rp.parse_version(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "1.2",
        "1.2.3.4",
        "1.2.3-rc.1",
        "1.2.3-alpha",
        "1.2.3-alpha.0",
        "1.2.3-alpha.01",
        "01.2.3",
        "",
        "not-a-version",
    ],
)
def test_parse_version_fails_closed_on_illegal_shapes(text: str) -> None:
    """Reject anything outside X.Y.Z / X.Y.Z-alpha.N / X.Y.Z-beta.N."""
    assert not rp.is_valid_version(text)
    with pytest.raises(rp.ReleasePhaseError):
        rp.parse_version(text)


def test_release_kind_classifies_by_major_version() -> None:
    """early/formal are both unsuffixed, split purely by major version."""
    assert rp.parse_version("0.16.0").release_kind == "early"
    assert rp.parse_version("1.0.0").release_kind == "formal"
    assert rp.parse_version("2.4.1").release_kind == "formal"
    assert rp.parse_version("0.16.0-alpha.1").release_kind == "alpha"
    assert rp.parse_version("1.0.0-beta.2").release_kind == "beta"


def test_format_version_round_trips_with_parse() -> None:
    """format_version is the exact inverse of parse_version's core fields."""
    for text in ("1.2.3", "0.16.0-alpha.1", "1.0.0-beta.9"):
        parsed = rp.parse_version(text)
        assert (
            rp.format_version(
                parsed.major, parsed.minor, parsed.patch, parsed.phase, parsed.n
            )
            == text
        )


def test_format_version_rejects_inconsistent_arguments() -> None:
    """A stable version cannot carry an N; a prerelease needs one >= 1."""
    with pytest.raises(rp.ReleasePhaseError):
        rp.format_version(1, 0, 0, None, 1)
    with pytest.raises(rp.ReleasePhaseError):
        rp.format_version(1, 0, 0, "alpha", None)
    with pytest.raises(rp.ReleasePhaseError):
        rp.format_version(1, 0, 0, "alpha", 0)
    with pytest.raises(rp.ReleasePhaseError):
        rp.format_version(1, 0, 0, "rc", 1)


@pytest.mark.parametrize(
    ("major", "minor", "patch", "phase", "n", "expected"),
    [
        (0, 16, 0, None, None, "0.16.0"),
        (1, 0, 0, None, None, "1.0.0"),
        (0, 16, 0, "alpha", 1, "0.16.0a1"),
        (0, 16, 0, "beta", 12, "0.16.0b12"),
    ],
)
def test_format_pep440_matches_python_normalized_form(
    major: int,
    minor: int,
    patch: int,
    phase: str | None,
    n: int | None,
    expected: str,
) -> None:
    """PEP 440 has no hyphen; alpha/beta compress to a bare letter+number."""
    assert rp.format_pep440(major, minor, patch, phase, n) == expected


@pytest.mark.parametrize(
    ("version", "phase"),
    [
        ("0.16.0-alpha.1", "alpha"),
        ("1.4.0-beta.3", "beta"),
        ("0.16.0", "early"),
        ("1.0.0", "formal"),
        ("2.3.4", "formal"),
    ],
)
def test_validate_declared_phase_accepts_legal_combinations(
    version: str, phase: str
) -> None:
    """Every legal (version, phase) pair from Issue #744 decision 1 passes."""
    rp.validate_declared_phase(version, phase)


@pytest.mark.parametrize(
    ("version", "phase"),
    [
        ("1.0.0", "early"),  # major >= 1 cannot be "early"
        ("0.16.0", "formal"),  # major == 0 cannot be "formal"
        ("0.16.0-alpha.1", "beta"),  # suffix must match the declared phase
        ("0.16.0-beta.1", "alpha"),
        ("0.16.0", "alpha"),  # declared prerelease phase needs a suffix
        ("1.2.3-alpha.1", "early"),  # early/formal must be unsuffixed
        ("1.2.3", "rc"),  # not one of the four legal phases
    ],
)
def test_validate_declared_phase_fails_closed_on_illegal_combinations(
    version: str, phase: str
) -> None:
    """Issue #744's legality rule: suffix only alpha.N/beta.N, else reject."""
    with pytest.raises(rp.ReleasePhaseError):
        rp.validate_declared_phase(version, phase)


def test_next_prerelease_n_increments_within_the_same_core_and_phase() -> None:
    """Same X.Y.Z + phase increments; a different phase or core resets to 1."""
    existing = ["0.16.0-alpha.1", "0.16.0-alpha.2", "0.16.0-beta.1"]
    assert rp.next_prerelease_n(existing, 0, 16, 0, "alpha") == 3
    assert rp.next_prerelease_n(existing, 0, 16, 0, "beta") == 2
    assert rp.next_prerelease_n(existing, 0, 16, 1, "alpha") == 1
    assert rp.next_prerelease_n([], 1, 0, 0, "beta") == 1


def test_phase_version_applies_the_declared_phase_to_a_core_version() -> None:
    """phase_version formats and re-validates in one step (Issue #744)."""
    assert rp.phase_version("0.16.0", "early") == "0.16.0"
    assert rp.phase_version("1.0.0", "formal") == "1.0.0"
    assert (
        rp.phase_version("0.16.0", "beta", existing=["0.16.0-beta.1"])
        == "0.16.0-beta.2"
    )
    assert rp.phase_version("0.16.0", "alpha") == "0.16.0-alpha.1"


def test_phase_version_rejects_a_core_version_that_already_has_a_suffix() -> (
    None
):
    """phase_version's input must be a bare X.Y.Z, not already suffixed."""
    with pytest.raises(rp.ReleasePhaseError):
        rp.phase_version("0.16.0-alpha.1", "beta")


def test_phase_version_fails_closed_when_the_phase_disagrees_with_major() -> (
    None
):
    """A formal declaration for a still-0.x core stays fail-closed."""
    with pytest.raises(rp.ReleasePhaseError):
        rp.phase_version("0.16.0", "formal")
    with pytest.raises(rp.ReleasePhaseError):
        rp.phase_version("1.0.0", "early")


def test_sort_by_precedence_orders_prerelease_before_release() -> None:
    """A release always outranks any pre-release of the same core version."""
    ordered = rp.sort_by_precedence(
        ["1.0.0", "1.0.0-beta.1", "1.0.0-alpha.2", "1.0.0-alpha.1", "0.9.0"]
    )
    assert ordered == [
        "0.9.0",
        "1.0.0-alpha.1",
        "1.0.0-alpha.2",
        "1.0.0-beta.1",
        "1.0.0",
    ]


def test_sort_by_precedence_ignores_malformed_entries() -> None:
    """A single bad tag among many must not crash the whole sort."""
    assert rp.sort_by_precedence(["1.0.0", "not-a-version", "0.9.0"]) == [
        "0.9.0",
        "1.0.0",
    ]


def test_select_latest_prefers_semver_precedence_over_list_order() -> None:
    """select_latest never depends on the caller's ordering."""
    assert (
        rp.select_latest(["0.16.0-alpha.1", "0.16.0-beta.1", "0.15.9"])
        == "0.16.0-beta.1"
    )
    assert rp.select_latest(["0.16.0-beta.1", "0.16.0"]) == "0.16.0"
    assert rp.select_latest([]) is None
    assert rp.select_latest(["not-a-version"]) is None


def test_retention_plan_keeps_every_unsuffixed_version() -> None:
    """Decision 5: every early/formal (unsuffixed) release is always kept."""
    versions = ["0.1.0", "0.2.0", "1.0.0", "2.0.0"]
    decisions = rp.retention_plan(versions)
    assert {decision.version for decision in decisions if decision.keep} == set(
        versions
    )


def test_retention_plan_keeps_only_the_latest_prerelease_string() -> None:
    """Only the newest major.minor group's single latest prerelease survives."""
    versions = [
        "v0.2.2",
        "v0.15.5",
        "v0.15.6",
        "0.16.0-alpha.1",
        "0.16.0-beta.1",
        "0.16.1-beta.1",
        "0.17.0-alpha.1",
    ]
    decisions = {
        decision.version: decision for decision in rp.retention_plan(versions)
    }
    kept = {version for version, decision in decisions.items() if decision.keep}
    assert kept == {"v0.2.2", "v0.15.5", "v0.15.6", "0.17.0-alpha.1"}
    # Older prereleases in the same 0.16 group, and the whole 0.16 group
    # itself once 0.17 has one, are all marked for deletion with a reason.
    assert decisions["0.16.0-alpha.1"].keep is False
    assert decisions["0.16.0-beta.1"].keep is False
    assert decisions["0.16.1-beta.1"].keep is False
    assert all(decision.reason for decision in decisions.values())


def test_retention_plan_ignores_malformed_tags_without_crashing() -> None:
    """A retention listing must survive one bad tag among many real ones."""
    decisions = rp.retention_plan(["1.0.0", "not-a-version", "0.16.0-alpha.1"])
    assert {decision.version for decision in decisions} == {
        "1.0.0",
        "0.16.0-alpha.1",
    }


def test_retention_plan_handles_only_no_suffix_versions() -> None:
    """No pre-releases at all is a legal, empty-prerelease-group input."""
    decisions = rp.retention_plan(["0.1.0", "0.2.0"])
    assert all(decision.keep for decision in decisions)


# --- Issue #744 finding: the alpha/beta suffix regex must not drift ----
#
# scripts/converge-release-tag, scripts/publish-release (two sites:
# cmd_resolve and cmd_publish), and scripts/check-release-drift (three
# sites: release_title_pattern, release_version_pattern, and the
# prerelease-flag consistency check) each re-derive the same
# `-(alpha|beta).N` suffix shape in bash/Python source text rather than
# calling into this module (there is no cheap way to share a compiled
# regex between bash and Python), so nothing but a text-level check
# catches one of them drifting from release_phase.py's own canonical
# `_VERSION_RE`. Sites differ cosmetically between a capturing `(alpha|
# beta)` and a non-capturing `(?:alpha|beta)` group, so the search
# substring below deliberately starts *after* the group-opening
# characters, matching either style.
_BASH_SUFFIX_TAIL = r"alpha|beta)\.[1-9][0-9]*"
_BASH_SUFFIX_SITES = (
    ("scripts/converge-release-tag", 1),
    ("scripts/publish-release", 2),
    ("scripts/check-release-drift", 3),
)
# The exact shape Issue #744's review found two sites still using: `N`
# accepts a leading zero or a literal 0, instead of requiring 1-9 first.
_REGRESSED_SUFFIX_TAIL = r"alpha|beta)\.[0-9]+"


def test_prerelease_suffix_regex_is_consistent_everywhere() -> None:
    """Every bash site's suffix pattern matches the canonical one.

    Also proves the *behavioral* consequence of Issue #744's review
    finding directly: a tag like `v1.2.3-alpha.0` (N=0) must be rejected
    by the canonical pattern -- the exact shape the regressed pattern
    would have wrongly accepted -- so the fixed sites and
    release_phase.py's own parser agree, not just look similar.
    """
    for relative_path, expected_occurrences in _BASH_SUFFIX_SITES:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert source.count(_BASH_SUFFIX_TAIL) == expected_occurrences, (
            f"{relative_path} does not use the canonical suffix pattern "
            f"the expected {expected_occurrences} time(s)"
        )
        assert _REGRESSED_SUFFIX_TAIL not in source, (
            f"{relative_path} still contains the pre-#744-review "
            "regressed pattern (accepts N=0 or a leading zero)"
        )

    import re as _re

    canonical = _re.compile(r"-(alpha|beta)\.[1-9][0-9]*$")
    for tag, expected in (
        ("v1.2.3-alpha.1", True),
        ("v1.2.3-beta.12", True),
        ("v1.2.3-alpha.0", False),
        ("v1.2.3-alpha.01", False),
        ("v1.2.3-alpha", False),
        ("v1.2.3-rc.1", False),
    ):
        suffix_match = canonical.search(tag) is not None
        assert suffix_match == expected, tag
        # release_phase.py's own parser must agree with the same tag as a
        # whole, not just the isolated suffix pattern.
        assert rp.is_valid_version(tag) == expected, tag
