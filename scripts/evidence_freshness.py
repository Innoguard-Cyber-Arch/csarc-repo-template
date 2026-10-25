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
import re
from datetime import UTC, datetime, timedelta
from typing import Any

DEFAULT_MAX_AGE_HOURS = 24.0
MAX_CLOCK_SKEW = timedelta(minutes=5)
# One normalized verification record serves both trust modes. Only the trust
# label differs, so a reader can compare candidates without ever treating
# self-attested local evidence as trusted hosted evidence. It lives here,
# rendered in every verification mode, so a hosted render does not need
# `local_verification.py` (Issue #1267).
RECORD_SCHEMA_VERSION = 1
SHA = re.compile(r"[0-9a-f]{40}")
TRUST_LOCAL = "self-attested-local"
TRUST_HOSTED = "github-hosted"
TRUST_SELF_HOSTED = "self-hosted-registered"
RECORD_KEYS = frozenset(
    {
        "schema_version",
        "trust",
        "success",
        "head_sha",
        "tree_sha",
        "base_ref",
        "base_sha",
        "tier",
        "scopes",
        "command",
        "completed_at",
    }
)
RECORD_TIERS = {"docs", "fast", "full"}


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


def normalized_record(evidence: dict[str, Any], trust: str) -> dict[str, Any]:
    """Project local or hosted evidence onto the shared record contract.

    Local evidence names its base `base_ref`; hosted evidence names it `base`
    and may omit it for legacy execution claims. Every other field and its
    validation are identical, and the trust label is kept as given.
    """
    if trust not in {TRUST_LOCAL, TRUST_HOSTED, TRUST_SELF_HOSTED}:
        raise RuntimeError(
            f"Bad trust label: '{trust}' is unknown. Use a known trust label."
        )
    declared = evidence.get("trust")
    if declared is not None and declared != trust:
        raise RuntimeError(
            "Bad trust label: evidence differs. Run verify again."
        )
    base_ref = evidence.get("base_ref", evidence.get("base"))
    base_sha = evidence.get("base_sha")
    scopes = evidence.get("scopes")
    record: dict[str, Any] = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "trust": trust,
        "success": True,
        "head_sha": evidence.get("head_sha"),
        "tree_sha": evidence.get("tree_sha"),
        "base_ref": base_ref,
        "base_sha": base_sha,
        "tier": evidence.get("tier"),
        "scopes": sorted(set(scopes)) if isinstance(scopes, list) else scopes,
        "command": evidence.get("command"),
        "completed_at": evidence.get("completed_at"),
    }
    legacy_hosted_base = trust == TRUST_HOSTED and not base_ref and not base_sha
    exact_base = (
        isinstance(base_ref, str)
        and bool(base_ref)
        and isinstance(base_sha, str)
        and SHA.fullmatch(base_sha) is not None
    )
    if (
        evidence.get("success", True) is not True
        or not isinstance(record["head_sha"], str)
        or SHA.fullmatch(record["head_sha"]) is None
        or not isinstance(record["tree_sha"], str)
        or SHA.fullmatch(record["tree_sha"]) is None
        or not (legacy_hosted_base or exact_base)
        or record["tier"] not in RECORD_TIERS
        or not isinstance(record["scopes"], list)
        or not record["scopes"]
        or not all(isinstance(scope, str) for scope in record["scopes"])
        or not isinstance(record["command"], str)
        or not record["command"]
        or not isinstance(record["completed_at"], str)
    ):
        raise RuntimeError(
            "Bad evidence: a field is invalid. Run verify again."
        )
    try:
        completed_at = datetime.fromisoformat(record["completed_at"])
    except ValueError as error:
        raise RuntimeError(
            "Record completion time is malformed: not ISO 8601. "
            "Run verify again."
        ) from error
    if completed_at.tzinfo is None:
        raise RuntimeError("Bad completion time: no zone. Run verify again.")
    return record
