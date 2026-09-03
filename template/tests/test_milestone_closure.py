"""Tests for completed, cancelled, and reopened Milestone lifecycles."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "sync_milestone_state.py")
)
acceptance_complete = MODULE["acceptance_complete"]
promotion_complete = MODULE["promotion_complete"]
append_completion_evidence = MODULE["append_completion_evidence"]
record_promotion_evidence = MODULE["record_promotion_evidence"]
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
                    "Stopped because the product direction changed.\n\n"
                    "## Promotion\n\n"
                    "- [x] All other Milestone Issues are closed.\n"
                    "- [x] Review ledger resolved and maintainer-confirmed.\n"
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


def test_promotion_requires_a_complete_section() -> None:
    """Do not infer promotion readiness from a partial or missing section."""
    assert promotion_complete("## Promotion\n\n- [x] First\n- [X] Second\n")
    assert not promotion_complete("## Promotion\n\n- [ ] Pending\n")
    assert not promotion_complete("No promotion section")


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


@pytest.mark.parametrize(
    "gap", ["open-item", "criteria", "promotion", "evidence", "reason"]
)
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
    elif gap == "promotion":
        tracker["body"] = tracker["body"].replace(
            "- [x] Review ledger resolved and maintainer-confirmed.",
            "- [ ] Review ledger resolved and maintainer-confirmed.",
        )
    elif gap == "evidence":
        tracker["body"] = tracker["body"].replace(
            "https://github.com/acme/project/releases/tag/v1.0.0", ""
        )
    else:
        tracker["state_reason"] = None

    assert not closure_decision(state).allowed


def test_unchecked_promotion_box_blocks_an_otherwise_ready_closure() -> None:
    """A tracker cannot close as completed with a pending Promotion item."""
    state = snapshot()
    tracker = state["issues"][1]
    assert closure_decision(state).allowed

    tracker["body"] = tracker["body"].replace(
        "- [x] Review ledger resolved and maintainer-confirmed.",
        "- [ ] Review ledger resolved and maintainer-confirmed.",
    )

    result = closure_decision(state)
    assert not result.allowed
    assert "Promotion" in result.summary


def test_append_completion_evidence_preserves_existing_content() -> None:
    """A promotion merge adds evidence without erasing what is already there."""
    body = (
        "## Proposal\n\nShip the reviewed batch.\n\n"
        "## Completion evidence\n\n"
        "https://github.com/acme/project/releases/tag/v0.9.0\n\n"
        "## Early termination\n\n<!-- Fill only when stopped. -->\n\n"
        "## Promotion\n\n- [x] Ready.\n"
    )

    updated = append_completion_evidence(
        body, "https://github.com/acme/project/commit/abc123"
    )

    assert "https://github.com/acme/project/releases/tag/v0.9.0" in updated
    assert "https://github.com/acme/project/commit/abc123" in updated
    assert "## Early termination" in updated
    assert "## Promotion\n\n- [x] Ready." in updated

    # Appending the same evidence again does not duplicate it.
    assert (
        append_completion_evidence(
            updated, "https://github.com/acme/project/commit/abc123"
        )
        == updated
    )


def test_append_completion_evidence_requires_the_section() -> None:
    """A tracker missing its Completion evidence section fails closed."""
    with pytest.raises(RuntimeError):
        append_completion_evidence(
            "## Proposal\n\nShip it.\n", "https://github.com/acme/project/x"
        )


def test_record_promotion_evidence_writes_the_updated_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The workflow helper fetches the tracker and edits it with evidence."""
    body = (
        "## Proposal\n\nShip it.\n\n"
        "## Completion evidence\n\n<!-- Fill after release. -->\n\n"
        "## Early termination\n\n<!-- Fill only when stopped. -->\n\n"
        "## Promotion\n\n- [x] Ready.\n"
    )
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        if arguments[:2] == ["api", "repos/acme/project/issues/80"]:
            return json.dumps({"number": 80, "body": body})
        return ""

    monkeypatch.setitem(
        record_promotion_evidence.__globals__, "run_gh", fake_run_gh
    )

    result = record_promotion_evidence(
        "acme/project", 80, "https://github.com/acme/project/commit/def456"
    )

    assert result.allowed
    assert calls[-1][:3] == ["issue", "edit", "80"]
    written_body = calls[-1][calls[-1].index("--body") + 1]
    assert "https://github.com/acme/project/commit/def456" in written_body
    assert "## Early termination" in written_body
    assert "<!-- Fill only when stopped. -->" in written_body


def test_record_promotion_evidence_is_a_no_op_when_already_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repeat run for the same evidence does not issue a redundant edit."""
    body = (
        "## Proposal\n\nShip it.\n\n"
        "## Completion evidence\n\n"
        "https://github.com/acme/project/commit/def456\n\n"
        "## Early termination\n\n<!-- Fill only when stopped. -->\n\n"
        "## Promotion\n\n- [x] Ready.\n"
    )
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        return json.dumps({"number": 80, "body": body})

    monkeypatch.setitem(
        record_promotion_evidence.__globals__, "run_gh", fake_run_gh
    )

    result = record_promotion_evidence(
        "acme/project", 80, "https://github.com/acme/project/commit/def456"
    )

    assert result.allowed
    assert all(call[:2] != ["issue", "edit"] for call in calls)


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
