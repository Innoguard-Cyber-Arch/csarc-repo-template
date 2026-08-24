"""Tests for GitHub Milestone state reconciliation."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "sync_milestone_state.py")
)
acceptance_complete = MODULE["acceptance_complete"]
desired_state = MODULE["desired_state"]
sync = MODULE["sync"]


@pytest.mark.parametrize(
    ("state", "open_issues", "criteria_complete", "expected"),
    [
        ("open", 0, True, "closed"),
        ("open", 0, False, None),
        ("open", 2, True, None),
        ("closed", 1, True, "open"),
        ("closed", 0, False, "open"),
        ("closed", 0, True, None),
    ],
)
def test_desired_state(
    state: str,
    open_issues: int,
    criteria_complete: bool,
    expected: str | None,
) -> None:
    """Cover close, reopen, standalone, and completed-story decisions."""
    assert desired_state(state, open_issues, criteria_complete) == expected


def test_acceptance_requires_a_complete_section() -> None:
    """Do not infer completion from Issue counts alone."""
    assert acceptance_complete(
        "## Acceptance criteria\n\n"
        "- [x] First\n"
        "- [X] Second\n\n"
        "## Verification\n"
    )
    assert not acceptance_complete("## Acceptance criteria\n\n- [ ] Pending\n")
    assert not acceptance_complete("No acceptance criteria")


def test_sync_rereads_remote_state_before_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the newest open count, then apply one idempotent transition."""
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        if "PATCH" in arguments:
            return "{}"
        return json.dumps(
            {
                "state": "open",
                "open_issues": 0,
                "description": "## Acceptance criteria\n\n- [x] Done\n",
            }
        )

    monkeypatch.setitem(sync.__globals__, "run_gh", fake_run_gh)
    assert sync("owner/repo", 9) == "closed"
    assert calls[0] == ["api", "repos/owner/repo/milestones/9"]
    assert calls[1][-1] == "state=closed"


def test_sync_noops_when_remote_state_already_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid duplicate writes when concurrent events already converged."""
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        return json.dumps(
            {
                "state": "closed",
                "open_issues": 0,
                "description": "## Acceptance criteria\n\n- [x] Done\n",
            }
        )

    monkeypatch.setitem(sync.__globals__, "run_gh", fake_run_gh)
    assert sync("owner/repo", 9) == "closed"
    assert len(calls) == 1
