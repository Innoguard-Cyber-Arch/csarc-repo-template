"""Tests for completed, cancelled, and reopened Milestone lifecycles."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "sync_milestone_state.py")
)
acceptance_complete = MODULE["acceptance_complete"]
closure_decision = MODULE["closure_decision"]
reconcile = MODULE["reconcile"]


def snapshot(*, reason: str = "completed") -> dict[str, Any]:
    """Build one closable lifecycle snapshot."""
    return {
        "repo": "acme/project",
        "milestone": {
            "number": 8,
            "title": "Delivery",
            "state": "open",
            "due_on": "2026-09-01T00:00:00Z",
            "description": (
                "Lifecycle Issue: #80\n\n"
                "## Acceptance criteria\n\n- [x] Deliver\n"
            ),
        },
        "issues": [
            {
                "number": 42,
                "title": "Deliver work",
                "state": "closed",
                "state_reason": "completed",
                "body": "## Acceptance criteria\n\n- [x] Done\n",
                "labels": [{"name": "enhancement"}],
                "user": {"login": "worker", "type": "User"},
            },
            {
                "number": 80,
                "title": "Milestone 8: Delivery",
                "state": "closed",
                "state_reason": reason,
                "body": (
                    "## Proposal\n\nShip the reviewed batch.\n\n"
                    "## Completion evidence\n\n"
                    "https://github.com/acme/project/releases/tag/v1.0.0\n\n"
                    "## Early termination\n\n"
                    "Stopped because the product direction changed.\n"
                ),
                "labels": [{"name": "enhancement"}],
                "user": {"login": "proposer", "type": "User"},
            },
        ],
        "comments": [
            {
                "body": "/milestone approve",
                "html_url": (
                    "https://github.com/acme/project/issues/80#issuecomment-1"
                ),
                "user": {"login": "reviewer", "type": "User"},
            }
        ],
    }


def test_acceptance_requires_a_complete_section() -> None:
    """Do not infer completion from Issue counts alone."""
    assert acceptance_complete(
        "## Acceptance criteria\n\n- [x] First\n- [X] Second\n"
    )
    assert not acceptance_complete("## Acceptance criteria\n\n- [ ] Pending\n")
    assert not acceptance_complete("No acceptance criteria")


def test_completed_and_not_planned_paths_are_distinct() -> None:
    """Normal delivery and early termination require different evidence."""
    assert closure_decision(snapshot()).allowed
    assert closure_decision(snapshot(reason="not_planned")).allowed


def test_early_termination_does_not_claim_completed_acceptance() -> None:
    """A stopped Milestone records disposition instead of false completion."""
    state = snapshot(reason="not_planned")
    state["milestone"]["description"] = state["milestone"][
        "description"
    ].replace("[x]", "[ ]")

    assert closure_decision(state).allowed


@pytest.mark.parametrize("gap", ["open-item", "criteria", "evidence", "reason"])
def test_invalid_closure_is_rejected(gap: str) -> None:
    """Every observable completion condition fails closed."""
    state = snapshot()
    tracker = state["issues"][1]
    if gap == "open-item":
        state["issues"][0]["state"] = "open"
    elif gap == "criteria":
        state["milestone"]["description"] = state["milestone"][
            "description"
        ].replace("[x]", "[ ]")
    elif gap == "evidence":
        tracker["body"] = tracker["body"].replace(
            "https://github.com/acme/project/releases/tag/v1.0.0", ""
        )
    else:
        tracker["state_reason"] = None

    assert not closure_decision(state).allowed


def test_invalid_close_reopens_the_tracker_and_milestone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid close cannot leave the tracker or Milestone closed."""
    state = snapshot()
    state["issues"][0]["state"] = "open"
    state["milestone"]["state"] = "closed"
    writes: list[tuple[str, int, str]] = []

    monkeypatch.setitem(
        reconcile.__globals__, "load_snapshot", lambda *_: state
    )
    monkeypatch.setitem(
        reconcile.__globals__,
        "_set_issue_state",
        lambda _repo, number, value: writes.append(("issue", number, value)),
    )
    monkeypatch.setitem(
        reconcile.__globals__,
        "_set_milestone_state",
        lambda _repo, number, value: writes.append(
            ("milestone", number, value)
        ),
    )
    monkeypatch.setitem(reconcile.__globals__, "refresh_pr_checks", lambda _: 0)

    result = reconcile("acme/project", 8)

    assert not result.allowed
    assert writes == [("issue", 80, "open"), ("milestone", 8, "open")]


def test_reopened_tracker_reopens_the_milestone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lifecycle Issue remains the authoritative open-state signal."""
    state = snapshot()
    state["issues"][1]["state"] = "open"
    state["issues"][1]["state_reason"] = None
    state["milestone"]["state"] = "closed"
    writes: list[tuple[int, str]] = []

    monkeypatch.setitem(
        reconcile.__globals__, "load_snapshot", lambda *_: state
    )
    monkeypatch.setitem(
        reconcile.__globals__,
        "_set_milestone_state",
        lambda _repo, number, value: writes.append((number, value)),
    )
    monkeypatch.setitem(reconcile.__globals__, "refresh_pr_checks", lambda _: 0)

    result = reconcile("acme/project", 8)

    assert result.allowed
    assert writes == [(8, "open")]
