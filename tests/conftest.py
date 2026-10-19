"""Shared pytest hooks for the root regression suite."""

from __future__ import annotations

import pytest

# Generated-project self-tests run only inside a real render
# (tests/test_generated_self_tests.py installs them there, #1077); the root
# suite never collects them in place.
collect_ignore = ["generated_self_tests"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Tag large cases so the run's JUnit XML reports them without a recount.

    scripts/verification_cost.py reads this property from the JUnit XML the
    verifier already writes, so the executed `large` count comes from the same
    pytest run instead of a second collection pass.
    """
    for item in items:
        if item.get_closest_marker("large") is not None:
            item.user_properties.append(("csarc_marker", "large"))
