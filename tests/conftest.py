"""Shared pytest hooks for the root regression suite."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Tag large cases so the run's JUnit XML reports them without a recount.

    scripts/verification_cost.py reads this property from the JUnit XML the
    verifier already writes, so the executed `large` count comes from the same
    pytest run instead of a second collection pass.
    """
    for item in items:
        if item.get_closest_marker("large") is not None:
            item.user_properties.append(("csarc_marker", "large"))
