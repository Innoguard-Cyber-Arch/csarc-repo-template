"""Fail-closed metadata policy for quarantined pytest coverage."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from typing import Any

import pytest

ISSUE_URL = re.compile(r"^https://github\.com/[^/]+/[^/]+/issues/[1-9][0-9]*$")
OWNER = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9/-]*$")
REQUIRED_FIELDS = {"owner", "issue", "expires", "remove_when"}


def validate_quarantine(
    args: tuple[Any, ...],
    values: Mapping[str, Any],
    *,
    today: date | None = None,
) -> None:
    """Reject an unowned, untracked, or expired quarantine marker."""
    if args or set(values) != REQUIRED_FIELDS:
        raise pytest.UsageError(
            "quarantine requires owner, issue, expires, and remove_when"
        )
    if (
        not isinstance(values["owner"], str)
        or OWNER.fullmatch(values["owner"]) is None
    ):
        raise pytest.UsageError("quarantine owner must be an @handle")
    if not isinstance(values["issue"], str) or not ISSUE_URL.fullmatch(
        values["issue"]
    ):
        raise pytest.UsageError(
            "quarantine issue must be a full GitHub Issue URL"
        )
    try:
        expiry = date.fromisoformat(values["expires"])
    except (TypeError, ValueError) as error:
        raise pytest.UsageError(
            "quarantine expires must be an ISO date"
        ) from error
    if expiry <= (today or date.today()):
        raise pytest.UsageError("quarantine has expired")
    if (
        not isinstance(values["remove_when"], str)
        or not values["remove_when"].strip()
    ):
        raise pytest.UsageError("quarantine remove_when must be non-empty")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Validate every quarantine marker during collection."""
    for item in items:
        for marker in item.iter_markers("quarantine"):
            validate_quarantine(marker.args, marker.kwargs)
