"""Tests for fail-closed quarantine metadata."""

from __future__ import annotations

import runpy
from datetime import date
from pathlib import Path

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "pytest_policy.py")
)
validate_quarantine = MODULE["validate_quarantine"]


def test_quarantine_requires_complete_live_metadata() -> None:
    """Accept a future expiry only with an owner, Issue, and removal rule."""
    validate_quarantine(
        (),
        {
            "owner": "@maintainer",
            "issue": "https://github.com/owner/repo/issues/123",
            "expires": "2026-08-26",
            "remove_when": "the race regression is fixed",
        },
        today=date(2026, 8, 25),
    )


@pytest.mark.parametrize(
    "values",
    [
        {},
        {
            "owner": "maintainer",
            "issue": "https://github.com/owner/repo/issues/123",
            "expires": "2026-08-26",
            "remove_when": "fixed",
        },
        {
            "owner": "@maintainer",
            "issue": "#123",
            "expires": "2026-08-26",
            "remove_when": "fixed",
        },
        {
            "owner": "@maintainer",
            "issue": "https://github.com/owner/repo/issues/123",
            "expires": "2026-08-25",
            "remove_when": "fixed",
        },
    ],
)
def test_quarantine_rejects_missing_invalid_or_expired_metadata(
    values: dict[str, str],
) -> None:
    """Reject every quarantine that cannot be audited and removed."""
    with pytest.raises(pytest.UsageError):
        validate_quarantine((), values, today=date(2026, 8, 25))


def test_quarantine_rejects_positional_metadata() -> None:
    """Keep the marker schema explicit and machine-readable."""
    with pytest.raises(pytest.UsageError):
        validate_quarantine(
            ("ambiguous",),
            {
                "owner": "@maintainer",
                "issue": "https://github.com/owner/repo/issues/123",
                "expires": "2026-08-26",
                "remove_when": "fixed",
            },
            today=date(2026, 8, 25),
        )
