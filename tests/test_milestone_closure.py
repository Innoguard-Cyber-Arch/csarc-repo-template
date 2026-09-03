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
reconciliation_status = MODULE["reconciliation_status"]
regenerate_reconciliation = MODULE["regenerate_reconciliation"]
record_reconciliation = MODULE["record_reconciliation"]


def _base_snapshot(*, reason: str = "completed") -> dict[str, Any]:
    """Build one closable lifecycle snapshot, without a Reconciliation."""
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


def snapshot(*, reason: str = "completed") -> dict[str, Any]:
    """Build one closable lifecycle snapshot with a fresh Reconciliation.

    Bakes in a Reconciliation section generated from this snapshot's own
    current content, so every existing closure test keeps exercising
    whatever gate it targets instead of tripping the new freshness check
    it knows nothing about.
    """
    state = _base_snapshot(reason=reason)
    tracker_issue = state["issues"][1]
    tracker_issue["body"] = regenerate_reconciliation(state)
    return state


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


def _with_pull_request(
    state: dict[str, Any],
    *,
    number: int,
    closes: int,
    merged: bool,
) -> dict[str, Any]:
    """Add one pull-request Issue entry declaring it closes another Issue."""
    state["issues"].append(
        {
            "number": number,
            "title": f"Deliver #{closes}",
            "state": "closed" if merged else "open",
            "body": f"Closes #{closes}\n",
            "pull_request": {
                "merged_at": "2026-09-01T00:00:00Z" if merged else None,
            },
        }
    )
    return state


def test_reconciliation_marks_delivered_when_pr_merged() -> None:
    """A closed work Issue with a merged closing PR reconciles as delivered."""
    state = _base_snapshot()
    _with_pull_request(state, number=99, closes=42, merged=True)

    body = regenerate_reconciliation(state)

    assert "#42" in body
    assert "Delivered" in body
    assert "1 linked work Issue(s); 1 delivered." in body
    assert reconciliation_status(body).allowed


def test_reconciliation_flags_a_closed_issue_without_a_merged_pr() -> None:
    """A closed work Issue with no merged closing PR is flagged, not hidden."""
    state = _base_snapshot()

    body = regenerate_reconciliation(state)

    assert "Closed without a merged PR" in body
    assert "0 delivered" in body


def test_reconciliation_reports_an_open_issue_as_pending() -> None:
    """A still-open linked work Issue reconciles as pending, not delivered."""
    state = _base_snapshot()
    state["issues"][0]["state"] = "open"

    body = regenerate_reconciliation(state)

    assert "Pending" in body


def test_reconciliation_is_fresh_immediately_after_regeneration() -> None:
    """A just-regenerated section is never considered stale."""
    state = _base_snapshot()

    body = regenerate_reconciliation(state)

    result = reconciliation_status(body)
    assert result.allowed
    assert result.summary == "Reconciliation is fresh"


def test_reconciliation_is_stale_after_an_unrelated_body_edit() -> None:
    """Editing any other tracker section invalidates the reconciliation.

    The regeneration tool only ever rewrites the Reconciliation section
    itself, so a fingerprint mismatch can only mean a human or agent
    touched the rest of the body afterward.
    """
    state = _base_snapshot()
    body = regenerate_reconciliation(state)

    edited = body.replace(
        "Ship the reviewed batch.", "Ship the reviewed batch, plus more."
    )

    result = reconciliation_status(edited)
    assert not result.allowed
    assert result.summary == "Reconciliation: stale, regenerate before closing"


def test_reconciliation_missing_section_is_reported_explicitly() -> None:
    """A tracker that has never been reconciled fails closed, not silently."""
    result = reconciliation_status("## Proposal\n\nShip it.\n")

    assert not result.allowed
    assert "missing" in result.summary.lower()


def test_closure_refuses_a_missing_reconciliation() -> None:
    """`closure_decision()` will not close on checkbox state alone."""
    state = _base_snapshot()

    result = closure_decision(state)
    assert not result.allowed
    assert "Reconciliation" in result.summary


def test_closure_refuses_a_stale_reconciliation() -> None:
    """A reconciliation regenerated before a later tracker edit cannot close."""
    state = snapshot()
    tracker_issue = state["issues"][1]
    assert closure_decision(state).allowed

    tracker_issue["body"] = tracker_issue["body"].replace(
        "Ship the reviewed batch.", "Ship the reviewed batch, expanded."
    )

    result = closure_decision(state)
    assert not result.allowed
    assert result.summary == "Reconciliation: stale, regenerate before closing"


def test_regenerating_reconciliation_clears_staleness() -> None:
    """Re-running regeneration after an edit restores a closable state."""
    state = snapshot()
    tracker_issue = state["issues"][1]
    tracker_issue["body"] = tracker_issue["body"].replace(
        "Ship the reviewed batch.", "Ship the reviewed batch, expanded."
    )
    assert not closure_decision(state).allowed

    tracker_issue["body"] = regenerate_reconciliation(state)

    assert closure_decision(state).allowed


def test_record_reconciliation_writes_the_updated_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The workflow helper fetches live state and persists the section."""
    state = _base_snapshot()
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        return ""

    monkeypatch.setitem(
        record_reconciliation.__globals__, "load_snapshot", lambda *_: state
    )
    monkeypatch.setitem(
        record_reconciliation.__globals__, "run_gh", fake_run_gh
    )

    result = record_reconciliation("acme/project", 8)

    assert result.allowed
    assert calls[-1][:3] == ["issue", "edit", "80"]
    written_body = calls[-1][calls[-1].index("--body") + 1]
    assert "## Reconciliation" in written_body
    assert reconciliation_status(written_body).allowed


def test_record_reconciliation_is_a_no_op_once_already_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repeat run against unchanged state does not issue a redundant edit."""
    state = snapshot()
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        return ""

    monkeypatch.setitem(
        record_reconciliation.__globals__, "load_snapshot", lambda *_: state
    )
    monkeypatch.setitem(
        record_reconciliation.__globals__, "run_gh", fake_run_gh
    )

    result = record_reconciliation("acme/project", 8)

    assert result.allowed
    assert all(call[:2] != ["issue", "edit"] for call in calls)


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
