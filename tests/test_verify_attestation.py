"""Regression tests for scripts/verify_attestation.py (Issue #661).

Covers the pure `parse_trailer`, `render_trailer`, and `check_attestation`
functions directly (no git, no subprocess) plus the module's `render` and
`check` CLI subcommands against a real, disposable git repository. The
git-plumbing side of the design -- scripts/write-verify-attestation's
amend-in-place, working-tree-cleanliness guard, and idempotent replace --
is covered separately by scripts/test-verify-attestation, which exercises
real git operations end to end; this file is the fast, no-subprocess-git
counterpart for the validation logic itself.
"""

from __future__ import annotations

import datetime as dt
import runpy
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "verify_attestation.py"

# runpy.run_path(), not `sys.path.insert` + `import verify_attestation`
# (mirrors tests/test_ci_tier.py, the other paired test that exercises a
# bare scripts/*.py module): a sys.path mutation only takes effect once
# pytest actually executes this file, which a static type checker like
# `ty` never does -- it has no way to know the import will resolve at
# runtime. That distinction is invisible when `ty check` runs against the
# central template repo (empirically, it still passes there), but it is
# not invisible inside a freshly generated or adopted downstream project,
# where `ty check` genuinely fails to resolve `import verify_attestation`
# and takes scripts/verify's own regression coverage down with it.
# runpy.run_path() sidesteps the whole question: it is a real,
# runtime-only file execution ty is not expected to model at all, exactly
# like every other paired test in this position.
va = types.SimpleNamespace(**runpy.run_path(str(MODULE)))

UTC = dt.UTC


def utc(*args: int) -> dt.datetime:
    return dt.datetime(*args, tzinfo=UTC)


TREE = "a" * 40
OTHER_TREE = "b" * 40


# --- parse_trailer -----------------------------------------------------


def test_parse_trailer_extracts_a_well_formed_line() -> None:
    message = (
        "feat: add a thing\n\n"
        "Some body text.\n\n"
        f"Verified-locally: sha256={TREE} tier=fast at=2026-09-01T00:00:00Z\n"
    )
    result = va.parse_trailer(message)
    assert result == va.Attestation(
        sha256=TREE, tier="fast", at=utc(2026, 9, 1)
    )


def test_parse_trailer_is_case_insensitive_on_the_hash() -> None:
    message = (
        f"x\n\nVerified-locally: sha256={TREE.upper()} "
        "tier=full at=2026-09-01T00:00:00Z\n"
    )
    result = va.parse_trailer(message)
    assert result is not None
    assert result.sha256 == TREE  # normalized to lowercase


def test_parse_trailer_returns_none_when_absent() -> None:
    assert va.parse_trailer("just a normal commit message\n") is None


@pytest.mark.parametrize(
    "line",
    [
        "Verified-locally: sha256=nothex tier=fast at=2026-09-01T00:00:00Z",
        f"Verified-locally: sha256={TREE} tier=medium at=2026-09-01T00:00:00Z",
        f"Verified-locally: sha256={TREE} tier=fast at=not-a-date",
        f"Verified-locally: sha256={TREE} tier=fast",
        f"verified-locally: sha256={TREE} tier=fast at=2026-09-01T00:00:00Z",
    ],
)
def test_parse_trailer_rejects_malformed_lines(line: str) -> None:
    assert va.parse_trailer(f"subject\n\n{line}\n") is None


def test_parse_trailer_keeps_other_trailers_and_takes_the_last_match() -> None:
    message = (
        "subject\n\n"
        "Co-authored-by: Someone <someone@example.com>\n"
        f"Verified-locally: sha256={TREE} tier=fast at=2026-09-01T00:00:00Z\n"
        f"Verified-locally: sha256={OTHER_TREE} "
        "tier=full at=2026-09-02T00:00:00Z\n"
    )
    result = va.parse_trailer(message)
    assert result == va.Attestation(
        sha256=OTHER_TREE, tier="full", at=utc(2026, 9, 2)
    )


# --- render_trailer ------------------------------------------------------


def test_render_trailer_round_trips_through_parse_trailer() -> None:
    at = utc(2026, 9, 1, 12, 30, 45)
    line = va.render_trailer(TREE, "full", at)
    assert (
        line
        == f"Verified-locally: sha256={TREE} tier=full at=2026-09-01T12:30:45Z"
    )
    parsed = va.parse_trailer(f"subject\n\n{line}\n")
    assert parsed == va.Attestation(sha256=TREE, tier="full", at=at)


def test_render_trailer_rejects_an_invalid_tier() -> None:
    with pytest.raises(ValueError, match="tier must be one of"):
        va.render_trailer(TREE, "docs")


def test_render_trailer_rejects_a_non_hex_hash() -> None:
    with pytest.raises(ValueError, match="does not look like a git tree hash"):
        va.render_trailer("not-hex!", "fast")


# --- check_attestation ---------------------------------------------------


def _message(sha256: str, tier: str, at: dt.datetime) -> str:
    return f"subject\n\n{va.render_trailer(sha256, tier, at)}\n"


def test_check_attestation_passes_for_a_fresh_matching_trailer() -> None:
    at = utc(2026, 9, 1, 12, 0, 0)
    now = at + dt.timedelta(hours=1)
    result = va.check_attestation(
        _message(TREE, "fast", at), TREE, now=now, max_age_hours=24
    )
    assert result.ok
    assert "tier=fast" in result.reason


def test_check_attestation_fails_when_the_trailer_is_missing() -> None:
    result = va.check_attestation("no trailer here\n", TREE)
    assert not result.ok
    assert "no 'Verified-locally:' trailer" in result.reason


def test_check_attestation_fails_on_hash_mismatch() -> None:
    at = utc(2026, 9, 1)
    result = va.check_attestation(
        _message(TREE, "fast", at), OTHER_TREE, now=at
    )
    assert not result.ok
    assert "does not match this commit's actual tree hash" in result.reason


def test_check_attestation_rejects_a_blank_actual_tree_hash() -> None:
    at = utc(2026, 9, 1)
    result = va.check_attestation(_message(TREE, "fast", at), "   ", now=at)
    assert not result.ok
    assert "plumbing problem" in result.reason


@pytest.mark.parametrize(
    ("age_hours", "expected_ok"),
    [(23.999, True), (24.0, True), (24.001, False), (48, False)],
)
def test_check_attestation_freshness_boundary(
    age_hours: float, expected_ok: bool
) -> None:
    at = utc(2026, 9, 1)
    now = at + dt.timedelta(hours=age_hours)
    result = va.check_attestation(
        _message(TREE, "fast", at), TREE, now=now, max_age_hours=24
    )
    assert result.ok is expected_ok
    if not expected_ok:
        assert "stale" in result.reason


@pytest.mark.parametrize(
    ("ahead_seconds", "expected_ok"),
    # The trailer format only stores second-level precision (render_trailer
    # truncates to %Y-%m-%dT%H:%M:%SZ), so boundary cases are expressed in
    # whole seconds around the 5-minute (300s) default skew threshold, not
    # fractional minutes that would round away before check_attestation
    # ever sees them.
    [(0, True), (299, True), (300, True), (301, False), (3600, False)],
)
def test_check_attestation_rejects_a_future_timestamp_beyond_clock_skew(
    ahead_seconds: int, expected_ok: bool
) -> None:
    now = utc(2026, 9, 1, 12, 0, 0)
    at = now + dt.timedelta(seconds=ahead_seconds)
    result = va.check_attestation(
        _message(TREE, "fast", at),
        TREE,
        now=now,
        max_clock_skew_minutes=5.0,
    )
    assert result.ok is expected_ok
    if not expected_ok:
        assert "future" in result.reason


def test_far_future_timestamp_is_rejected_as_future_not_stale() -> None:
    """A fabricated far-future 'at=' must fail as future, not pass as fresh.

    Adversarial case from Issue #661's own review request: without an
    explicit "not in the future" check, staleness alone would never catch
    a timestamp stamped decades ahead, since it is never "too old".
    """
    now = utc(2026, 9, 1)
    at = utc(2099, 1, 1)
    result = va.check_attestation(_message(TREE, "fast", at), TREE, now=now)
    assert not result.ok
    assert "future" in result.reason


@pytest.mark.parametrize(
    ("attested_tier", "required_tier", "expected_ok"),
    [
        ("fast", "docs", True),
        ("fast", "fast", True),
        ("fast", "full", False),
        ("full", "docs", True),
        ("full", "fast", True),
        ("full", "full", True),
    ],
)
def test_check_attestation_tier_sufficiency_matrix(
    attested_tier: str, required_tier: str, expected_ok: bool
) -> None:
    """A cheap tier=fast attestation must never satisfy a full requirement.

    Adversarial case from Issue #661's own review request: scripts/ci_tier.py
    independently decides a PR needs "full" verification (e.g. it touches
    .github/workflows/); without this check, running the far cheaper
    scripts/verify-fast locally -- which always attests tier=fast -- would
    still make the hosted, no-longer-test-executing job pass.
    """
    at = utc(2026, 9, 1)
    result = va.check_attestation(
        _message(TREE, attested_tier, at),
        TREE,
        now=at,
        required_tier=required_tier,
    )
    assert result.ok is expected_ok
    if not expected_ok:
        assert f"needs '{required_tier}' verification" in result.reason


def test_check_attestation_rejects_an_unknown_required_tier() -> None:
    at = utc(2026, 9, 1)
    with pytest.raises(ValueError, match="unexpected required_tier"):
        va.check_attestation(
            _message(TREE, "fast", at), TREE, now=at, required_tier="post-merge"
        )


# --- CLI -------------------------------------------------------------
#
# Both helpers below hardcode their own executable ("git" / sys.executable)
# once, so only these two definitions need an S603/S607 exemption -- every
# call site stays free of the noqa comments a repeated inline
# subprocess.run([...]) pattern would otherwise need on every line.


def _git(
    *args: str,
    cwd: Path,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed executable, test-owned fixture
        ["git", "-C", str(cwd), *args],  # noqa: S607 - fixed executable
        capture_output=True,
        text=True,
        check=True,
        input=input,
    )


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed executable, repository-owned script
        [sys.executable, str(MODULE), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_render_prints_the_trailer_line() -> None:
    result = _cli(
        "render",
        "--sha256",
        TREE,
        "--tier",
        "full",
        "--at",
        "2026-09-01T00:00:00Z",
    )
    assert result.returncode == 0
    assert (
        result.stdout.strip()
        == f"Verified-locally: sha256={TREE} tier=full at=2026-09-01T00:00:00Z"
    )


def test_cli_check_against_a_real_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _git("add", "a.txt", cwd=repo)
    _git("commit", "-q", "-m", "Initial commit", cwd=repo)

    tree_hash = _git("rev-parse", "HEAD^{tree}", cwd=repo).stdout.strip()
    real_trailer = va.render_trailer(tree_hash, "fast")
    new_message = _git(
        "interpret-trailers",
        "--trailer",
        real_trailer,
        cwd=repo,
        input="Initial commit\n",
    ).stdout
    _git("commit", "--amend", "-q", "-F", "-", cwd=repo, input=new_message)
    head = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()

    passing = _cli("check", head, "--repo", str(repo))
    assert passing.returncode == 0
    assert "verified: tier=fast" in passing.stdout

    failing = _cli(
        "check", head, "--repo", str(repo), "--required-tier", "full"
    )
    assert failing.returncode == 1
    assert "needs 'full' verification" in failing.stderr


def test_cli_check_reports_a_bad_git_invocation_as_exit_2(
    tmp_path: Path,
) -> None:
    result = _cli("check", "not-a-real-sha", "--repo", str(tmp_path))
    assert result.returncode == 2
    assert "git" in result.stderr
