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
complete_release = MODULE["complete_release"]
Decision = MODULE["Decision"]
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
            {
                "number": 99,
                "title": "Deliver #42",
                "state": "closed",
                "body": "Closes #42\n",
                "pull_request": {"merged_at": "2026-09-01T00:00:00Z"},
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
    """Closed work with merged PR and complete acceptance is delivered."""
    state = _base_snapshot()
    body = regenerate_reconciliation(state)
    state["issues"][1]["body"] = body

    assert "#42" in body
    assert "Delivered" in body
    assert "1 linked work Issue(s); 1 delivered." in body
    assert reconciliation_status(body).allowed
    assert closure_decision(state).allowed


@pytest.mark.parametrize(
    ("gap", "status"),
    [
        ("unchecked", "Acceptance incomplete or missing"),
        ("missing", "Acceptance incomplete or missing"),
        ("unmerged", "Closed without a merged PR"),
        ("open", "Pending"),
    ],
)
def test_reconciliation_and_completed_closure_reject_undelivered_work(
    gap: str, status: str
) -> None:
    """Every non-delivered reconciliation state blocks completed closure."""
    state = _base_snapshot()
    work_issue = state["issues"][0]
    if gap == "unchecked":
        work_issue["body"] = "## Acceptance criteria\n\n- [ ] Done\n"
    elif gap == "missing":
        work_issue["body"] = "No acceptance checklist\n"
    elif gap == "unmerged":
        state["issues"][2]["pull_request"]["merged_at"] = None
    else:
        work_issue["state"] = "open"

    body = regenerate_reconciliation(state)
    state["issues"][1]["body"] = body
    result = closure_decision(state)

    assert status in body
    assert "0 delivered" in body
    assert not result.allowed
    assert f"#42 ({status})" in result.summary


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


def test_successful_release_completes_tracker_and_milestone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publication owns the idempotent tracker and Milestone close."""
    sha = "a" * 40
    pull = {
        "number": 91,
        "body": "Refs #80\n",
        "merged_at": "2026-09-22T00:00:00Z",
        "merge_commit_sha": sha,
        "base": {"ref": "main"},
        "head": {"ref": "promote/m8-delivery"},
        "milestone": {"number": 8},
    }
    writes: list[list[str]] = []
    state = _base_snapshot()
    tracker_issue = state["issues"][1]
    tracker_issue["state"] = "open"
    tracker_issue["state_reason"] = None
    tracker_issue["milestone"] = {"number": 8}
    tracker_issue["body"] = tracker_issue["body"].replace(
        "https://github.com/acme/project/releases/tag/v1.0.0",
        "<!-- Filled after publication. -->",
    )

    def fake_run_gh(arguments: list[str]) -> str:
        if "commits/" in " ".join(arguments):
            return json.dumps([pull])
        writes.append(arguments)
        return ""

    globals_ = complete_release.__globals__
    monkeypatch.setitem(globals_, "run_gh", fake_run_gh)
    monkeypatch.setitem(globals_, "load_snapshot", lambda *_: state)
    monkeypatch.setitem(
        globals_, "reconcile", lambda *_: Decision(True, "closed")
    )

    result = complete_release(
        "acme/project",
        sha,
        "https://github.com/acme/project/releases/tag/v1.0.0",
        outcome="published",
    )

    assert result.allowed
    body_write = next(call for call in writes if call[:2] == ["issue", "edit"])
    written_body = body_write[body_write.index("--body") + 1]
    assert f"https://github.com/acme/project/commit/{sha}" in written_body
    assert "https://github.com/acme/project/releases/tag/v1.0.0" in written_body
    assert "## Reconciliation" in written_body
    assert any("state_reason=completed" in call for call in writes)


def test_release_completion_retries_after_its_evidence_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An interrupted close resumes from exact, reconciled release evidence."""
    sha = "a" * 40
    release_url = "https://github.com/acme/project/releases/tag/v1.0.0"
    state = snapshot()
    tracker_issue = state["issues"][1]
    tracker_issue["milestone"] = {"number": 8}
    tracker_issue["body"] = append_completion_evidence(
        tracker_issue["body"],
        f"https://github.com/acme/project/commit/{sha}",
    )
    tracker_issue["body"] = regenerate_reconciliation(state)
    tracker_issue["updated_at"] = "2026-09-22T03:00:00Z"
    state["comments"][0].update(
        {
            "created_at": "2026-09-21T00:00:00Z",
            "updated_at": "2026-09-21T00:00:00Z",
        }
    )
    pull = {
        "number": 91,
        "body": "Refs #80\n",
        "merged_at": "2026-09-22T00:00:00Z",
        "merge_commit_sha": sha,
        "base": {"ref": "main"},
        "head": {"ref": "promote/m8-delivery"},
        "milestone": {"number": 8},
    }
    writes: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        if "commits/" in " ".join(arguments):
            return json.dumps([pull])
        writes.append(arguments)
        return ""

    globals_ = complete_release.__globals__
    monkeypatch.setitem(globals_, "run_gh", fake_run_gh)
    monkeypatch.setitem(globals_, "load_snapshot", lambda *_: state)
    monkeypatch.setitem(
        globals_, "reconcile", lambda *_: Decision(True, "closed")
    )

    result = complete_release(
        "acme/project", sha, release_url, outcome="published"
    )

    assert result.allowed
    assert all(call[:2] != ["issue", "edit"] for call in writes)
    assert any("state_reason=completed" in call for call in writes)


def test_completed_closure_uses_the_pre_write_approval_boundary() -> None:
    """Machine evidence and closing writes cannot stale their own approval."""
    state = snapshot()
    tracker_issue = state["issues"][1]
    tracker_issue["updated_at"] = "2026-09-22T03:00:00Z"
    state["comments"][0].update(
        {
            "created_at": "2026-09-21T00:00:00Z",
            "updated_at": "2026-09-21T00:00:00Z",
        }
    )

    assert closure_decision(state).allowed


def test_completed_closure_still_rejects_an_edited_approval() -> None:
    """Ignoring tracker writes must not permit edited approval comments."""
    state = snapshot()
    tracker_issue = state["issues"][1]
    tracker_issue["updated_at"] = "2026-09-22T03:00:00Z"
    state["comments"][0].update(
        {
            "created_at": "2026-09-21T00:00:00Z",
            "updated_at": "2026-09-21T01:00:01Z",
        }
    )

    result = closure_decision(state)

    assert not result.allowed
    assert "invalidated" in result.summary


def test_release_completion_ignores_non_promotion_main_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standalone releases never close an unrelated Milestone tracker."""
    monkeypatch.setitem(
        complete_release.__globals__,
        "run_gh",
        lambda *_: json.dumps(
            [
                {
                    "number": 91,
                    "merged_at": "2026-09-22T00:00:00Z",
                    "merge_commit_sha": "a" * 40,
                    "base": {"ref": "main"},
                    "head": {"ref": "feat/42-standalone"},
                }
            ]
        ),
    )

    result = complete_release(
        "acme/project",
        "a" * 40,
        "https://github.com/acme/project/releases/tag/v1.0.0",
        outcome="published",
    )

    assert result.allowed
    assert "not a Milestone promotion" in result.summary


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


@pytest.mark.parametrize(
    ("governance_state", "expected_summary"),
    [
        ("unapproved", "must approve"),
        ("stale", "invalidated"),
        ("objected", "Resolve 1 objection"),
    ],
)
def test_pending_governance_is_a_notice_while_pr_checks_stay_failed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    governance_state: str,
    expected_summary: str,
) -> None:
    """Pending governance is visible without making reconciliation fail."""
    state = _base_snapshot()
    tracker_issue = state["issues"][1]
    tracker_issue["state"] = "open"
    tracker_issue["state_reason"] = None
    if governance_state == "unapproved":
        state["comments"] = []
    elif governance_state == "stale":
        tracker_issue["updated_at"] = "2026-09-02T00:00:00Z"
        state["comments"][0].update(
            {
                "created_at": "2026-09-01T00:00:00Z",
                "updated_at": "2026-09-01T00:00:00Z",
            }
        )
    else:
        state["comments"].append(
            {
                "body": "/milestone object: unresolved risk",
                "html_url": (
                    "https://github.com/acme/project/issues/80#issuecomment-2"
                ),
                "user": {"login": "critic", "type": "User"},
            }
        )
    _with_pull_request(state, number=99, closes=42, merged=False)
    recorded: list[bool] = []

    monkeypatch.setitem(
        reconcile.__globals__, "load_snapshot", lambda *_: state
    )
    monkeypatch.setitem(
        reconcile.__globals__,
        "run_gh",
        lambda _arguments: json.dumps({"head": {"sha": "pr-head"}}),
    )
    monkeypatch.setitem(
        reconcile.__globals__,
        "_record_check",
        lambda _repo, _sha, decision: recorded.append(decision.allowed),
    )

    result = reconcile(
        "acme/project", 8, event_issue=80, event_action="created"
    )

    assert result.allowed
    assert expected_summary in result.summary
    assert recorded == [False]
    output = capsys.readouterr().out
    assert "::notice title=Milestone governance status::" in output


@pytest.mark.parametrize(
    ("event_issue", "event_action", "should_refresh"),
    [(42, "edited", False), (42, "milestoned", True), (0, "edited", True)],
)
def test_only_relevant_milestone_events_reconcile(
    monkeypatch: pytest.MonkeyPatch,
    event_issue: int,
    event_action: str,
    should_refresh: bool,
) -> None:
    """Skip work activity, but run Milestone and membership changes."""
    state = _base_snapshot()
    state["issues"][1]["state"] = "open"
    if not should_refresh:
        state["milestone"]["state"] = "closed"
    refreshed: list[dict[str, Any]] = []
    writes: list[tuple[int, str]] = []

    monkeypatch.setitem(
        reconcile.__globals__, "load_snapshot", lambda *_: state
    )
    monkeypatch.setitem(
        reconcile.__globals__,
        "refresh_pr_checks",
        lambda current: refreshed.append(current),
    )
    monkeypatch.setitem(
        reconcile.__globals__,
        "_set_milestone_state",
        lambda _repo, number, value: writes.append((number, value)),
    )

    result = reconcile(
        "acme/project",
        8,
        event_issue=event_issue,
        event_action=event_action,
    )

    assert result.allowed
    assert refreshed == ([state] if should_refresh else [])
    assert writes == []
    if not should_refresh:
        assert "does not change Milestone lifecycle" in result.summary


def test_invalid_tracker_is_not_hidden_by_a_work_issue_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configuration errors stay red even when a work Issue caused the run."""
    state = _base_snapshot()
    state["issues"][1]["state"] = "open"
    state["issues"][1]["labels"] = []

    monkeypatch.setitem(
        reconcile.__globals__, "load_snapshot", lambda *_: state
    )
    monkeypatch.setitem(reconcile.__globals__, "refresh_pr_checks", lambda _: 0)

    result = reconcile("acme/project", 8, event_issue=42, event_action="edited")

    assert not result.allowed
    assert "enhancement label" in result.summary


def test_reconcile_api_and_write_errors_remain_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub API and state-write failures are not governance status."""

    def fail_load(*_args: object) -> dict[str, Any]:
        raise RuntimeError("GitHub API failed")

    monkeypatch.setitem(reconcile.__globals__, "load_snapshot", fail_load)

    with pytest.raises(RuntimeError, match="GitHub API failed"):
        reconcile("acme/project", 8, event_issue=80, event_action="edited")

    state = _base_snapshot()
    state["issues"][1]["state"] = "open"
    state["milestone"]["state"] = "closed"

    monkeypatch.setitem(
        reconcile.__globals__, "load_snapshot", lambda *_: state
    )

    def fail_write(*_args: object) -> None:
        raise RuntimeError("state write failed")

    monkeypatch.setitem(
        reconcile.__globals__, "_set_milestone_state", fail_write
    )

    with pytest.raises(RuntimeError, match="state write failed"):
        reconcile("acme/project", 8, event_issue=80, event_action="edited")
