"""Contract tests for the shared verification evidence freshness policy."""

from __future__ import annotations

import re
import runpy
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts" / "evidence_freshness.py"))
require_fresh = MODULE["require_fresh"]
policy_max_age_hours = MODULE["policy_max_age_hours"]
DEFAULT_MAX_AGE_HOURS = MODULE["DEFAULT_MAX_AGE_HOURS"]
MAX_CLOCK_SKEW = MODULE["MAX_CLOCK_SKEW"]

NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
SUBJECT = "Trusted verification"

# Every script that decides whether verification evidence may be used, in
# both the template repository and the generated-project copy. Each must
# delegate the age decision to `evidence_freshness.require_fresh` (directly
# or through `validate_verification_job` / `local_verification.require`).
CONSUMERS = (
    "verification_evidence.py",
    "local_verification.py",
    "pr_lifecycle.py",
    "check-trusted-verification",
    "promotion_gate.py",
)
DIRECT_CALLERS = ("verification_evidence.py", "local_verification.py")


def test_default_window_is_the_documented_24_hours() -> None:
    """The ADR's default stays the single trusted constant."""
    assert DEFAULT_MAX_AGE_HOURS == 24.0
    assert policy_max_age_hours() == 24.0
    assert timedelta(minutes=5) == MAX_CLOCK_SKEW
    adr = (ROOT / "docs/adr/verification-evidence-freshness.md").read_text(
        encoding="utf-8"
    )
    assert "24" in adr
    assert "evidence_freshness.py" in adr


@pytest.mark.parametrize(
    ("age", "fresh"),
    [
        (timedelta(0), True),
        (timedelta(hours=23, minutes=59, seconds=59), True),
        (timedelta(hours=24), True),
        (timedelta(hours=24, microseconds=1), False),
        (timedelta(hours=24, seconds=1), False),
        (timedelta(days=30), False),
    ],
)
def test_window_boundary_is_inclusive_at_exactly_24_hours(
    age: timedelta, fresh: bool
) -> None:
    """Exactly 24 hours old is fresh; any instant later is stale."""
    completed = NOW - age
    if fresh:
        assert require_fresh(completed, subject=SUBJECT, now=NOW) == completed
    else:
        with pytest.raises(RuntimeError, match="stale; re-run verification"):
            require_fresh(completed, subject=SUBJECT, now=NOW)


@pytest.mark.parametrize(
    ("ahead", "accepted"),
    [
        (timedelta(minutes=4, seconds=59), True),
        (timedelta(minutes=5), True),
        (timedelta(minutes=5, seconds=1), False),
        (timedelta(days=365), False),
    ],
)
def test_clock_skew_and_future_completion(
    ahead: timedelta, accepted: bool
) -> None:
    """Small clock skew passes; a future time cannot extend the window."""
    completed = NOW + ahead
    if accepted:
        require_fresh(completed, subject=SUBJECT, now=NOW)
    else:
        with pytest.raises(RuntimeError, match="in the future"):
            require_fresh(completed, subject=SUBJECT, now=NOW)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "completion time is missing"),
        ("", "completion time is missing"),
        ("yesterday", "completion time is malformed"),
        (1760443200, "completion time is malformed"),
        ("2026-10-14T11:00:00", "completion time has no timezone"),
        (datetime(2026, 10, 14, 11), "completion time has no timezone"),
    ],
)
def test_missing_or_ambiguous_timestamp_fails_closed(
    value: object, message: str
) -> None:
    """No timestamp, or one without a timezone, is never treated as fresh."""
    with pytest.raises(RuntimeError, match=message):
        require_fresh(value, subject=SUBJECT, now=NOW)


def test_timezone_offsets_are_compared_in_utc() -> None:
    """The same instant written in any offset gets the same verdict."""
    taipei = timezone(timedelta(hours=8))
    boundary = (NOW - timedelta(hours=24)).astimezone(taipei)
    assert require_fresh(boundary.isoformat(), subject=SUBJECT, now=NOW) == (
        NOW - timedelta(hours=24)
    )
    assert require_fresh(
        "2026-10-13T12:00:00Z", subject=SUBJECT, now=NOW.astimezone(taipei)
    ) == NOW - timedelta(hours=24)
    with pytest.raises(RuntimeError, match="stale"):
        require_fresh(
            "2026-10-14T19:59:59+08:00",
            subject=SUBJECT,
            now=NOW + timedelta(hours=24),
        )


def test_naive_reference_time_is_rejected() -> None:
    """A naive `now` would silently mean host-local time, so it fails closed."""
    with pytest.raises(RuntimeError, match="reference time has no timezone"):
        require_fresh(
            NOW,
            subject=SUBJECT,
            now=datetime(2026, 10, 14, 12),
        )


@pytest.mark.parametrize("requested", [24.0001, 48, 1e9, float("inf")])
def test_candidate_cannot_widen_the_window(requested: float) -> None:
    """A caller-supplied window above trusted policy fails closed."""
    with pytest.raises(RuntimeError, match="freshness window"):
        policy_max_age_hours(requested)
    with pytest.raises(RuntimeError, match="freshness window"):
        require_fresh(
            NOW - timedelta(hours=30),
            subject=SUBJECT,
            now=NOW,
            max_age_hours=requested,
        )


@pytest.mark.parametrize("requested", [0, -1, float("nan"), True, "48"])
def test_invalid_window_is_rejected(requested: object) -> None:
    """Zero, negative, non-finite, boolean, and string windows are invalid."""
    with pytest.raises(RuntimeError, match="freshness window is invalid"):
        policy_max_age_hours(requested)


def test_policy_change_tightens_and_revalidation_recovers() -> None:
    """A tighter policy expires old evidence; a new run is fresh again."""
    old = NOW - timedelta(hours=6)
    require_fresh(old, subject=SUBJECT, now=NOW)
    with pytest.raises(RuntimeError, match="stale"):
        require_fresh(old, subject=SUBJECT, now=NOW, max_age_hours=1)
    rerun = NOW - timedelta(minutes=10)
    assert (
        require_fresh(rerun, subject=SUBJECT, now=NOW, max_age_hours=1) == rerun
    )


@pytest.mark.parametrize("layer", ["scripts", "template/.csarc/scripts"])
def test_every_consumer_shares_one_freshness_function(layer: str) -> None:
    """No consumer keeps its own window, skew, or age arithmetic."""
    base = ROOT / layer
    assert (base / "evidence_freshness.py").read_bytes() == (
        ROOT / "scripts/evidence_freshness.py"
    ).read_bytes()
    for name in CONSUMERS:
        source = (base / name).read_text(encoding="utf-8")
        arithmetic = re.search(r"timedelta\(\s*(hours|minutes)=", source)
        assert arithmetic is None, name
        assert "max_age_hours: float = 24" not in source, name
        assert "default=24" not in source, name
        assert "max_clock_skew" not in source, name
    for name in DIRECT_CALLERS:
        source = (base / name).read_text(encoding="utf-8")
        assert "evidence_freshness.require_fresh(" in source, name
        assert "evidence_freshness.policy_max_age_hours(" in source, name


@pytest.mark.parametrize("layer", ["scripts", "template/.csarc/scripts"])
def test_window_is_not_part_of_any_evidence_payload(layer: str) -> None:
    """The window is trusted policy, never a candidate-controlled field."""
    for name in ("merge_trace.py", "local_verification.py"):
        source = (ROOT / layer / name).read_text(encoding="utf-8")
        assert "max_age" not in source.split("def require(")[0], name
    trailers = ROOT / (
        "policies" if layer == "scripts" else "template/.csarc/policies"
    )
    assert "max_age" not in (trailers / "merge-trailers.json").read_text(
        encoding="utf-8"
    )


def test_checker_cli_rejects_a_widened_window_before_any_lookup() -> None:
    """`--max-age-hours` may tighten the policy but never loosen it."""
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(ROOT / "scripts" / "check-trusted-verification"),
            "a" * 40,
            "--github-repo",
            "owner/repo",
            "--max-age-hours",
            "48",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "cannot exceed the trusted 24-hour policy" in result.stderr
