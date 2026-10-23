#!/usr/bin/env python3
"""Decide whether one verification result is still fresh enough to reuse.

Issue #1075: every local, hosted, merge, release, promotion, and fallback
consumer of verification evidence calls `require_fresh` so they share one
window, one clock-skew allowance, and one UTC comparison. The threat model
and the reason for the 24-hour default live in
`docs/adr/verification-evidence-freshness.md`.

The window is a trusted policy parameter. It is never read from an evidence
payload, and a caller may only tighten it, so a candidate cannot widen the
window to accept its own old evidence. Freshness is one necessary condition;
callers keep every identity binding (repository, head, tree, base, tier,
scopes, command, toolchain, runner, and result) and check those separately.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

DEFAULT_MAX_AGE_HOURS = 24.0
MAX_CLOCK_SKEW = timedelta(minutes=5)


def policy_max_age_hours(requested: object = None) -> float:
    """Return the trusted window in hours; a caller may only tighten it."""
    if requested is None:
        return DEFAULT_MAX_AGE_HOURS
    if (
        isinstance(requested, bool)
        or not isinstance(requested, int | float)
        or not math.isfinite(requested)
        or requested <= 0
    ):
        raise RuntimeError(
            "Verification freshness window is invalid: not > 0. Pass hours > 0."
        )
    if requested > DEFAULT_MAX_AGE_HOURS:
        raise RuntimeError(
            "Verification freshness window is too wide: the limit is "
            f"{DEFAULT_MAX_AGE_HOURS:g} hours. Pass fewer hours."
        )
    return float(requested)


def reference_time(now: datetime | None = None) -> datetime:
    """Return the aware UTC instant that freshness is measured against."""
    if now is None:
        return datetime.now(UTC)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise RuntimeError(
            "Reference time has no timezone: unsafe. Pass an aware datetime."
        )
    return now.astimezone(UTC)


def completion_time(value: object, subject: str) -> datetime:
    """Parse one required, timezone-aware completion time into UTC."""
    what = f"{subject} completion time"
    if value is None or value == "":
        raise RuntimeError(
            f"{what} is missing: empty. Verify the exact head again."
        )
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise RuntimeError(
                f"{what} is malformed: no ISO. Verify the exact head again."
            ) from error
    else:
        raise RuntimeError(
            f"{what} is malformed: no text. Verify the exact head again."
        )
    if parsed.tzinfo is None:
        raise RuntimeError(
            f"{what} has no timezone: unsafe. Verify the exact head again."
        )
    return parsed.astimezone(UTC)


def require_fresh(
    completed_at: object,
    *,
    subject: str,
    now: datetime | None = None,
    max_age_hours: object = None,
) -> datetime:
    """Return the UTC completion time, or fail when evidence is not fresh.

    Evidence exactly `max_age_hours` old is still fresh; one instant later
    it is stale. A completion time more than `MAX_CLOCK_SKEW` ahead of the
    reference time is rejected rather than treated as fresh, so a future
    timestamp cannot extend the window.
    """
    window = timedelta(hours=policy_max_age_hours(max_age_hours))
    current = reference_time(now)
    completed = completion_time(completed_at, subject)
    if completed - current > MAX_CLOCK_SKEW:
        raise RuntimeError(
            f"{subject} completion time is in the future: skew. "
            "Check the clock."
        )
    if current - completed > window:
        raise RuntimeError(
            f"{subject} evidence is stale: too old. Re-verify the exact head."
        )
    return completed
