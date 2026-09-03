"""Tests for Milestone lifecycle approval."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "sync_milestone_state.py")
)
approval_decision = MODULE["approval_decision"]
check_pr = MODULE["check_pr"]
check_merge_group = MODULE["check_merge_group"]
tracker_errors = MODULE["tracker_errors"]


def snapshot(*comments: dict[str, Any]) -> dict[str, Any]:
    """Build one valid open lifecycle snapshot."""
    tracker = {
        "number": 80,
        "title": "Milestone 8: Delivery",
        "state": "open",
        "state_reason": None,
        "body": (
            "## Proposal\n\nShip the reviewed batch.\n\n"
            "## Completion evidence\n\n<!-- Fill after release. -->\n\n"
            "## Early termination\n\n<!-- Fill only when stopped. -->\n\n"
            "## Promotion\n\n<!-- Fill when ready to promote. -->\n"
        ),
        "user": {"login": "proposer", "type": "User"},
        "labels": [{"name": "enhancement"}],
    }
    return {
        "repo": "acme/project",
        "milestone": {
            "number": 8,
            "title": "Delivery",
            "state": "open",
            "due_on": "2026-09-01T00:00:00Z",
            "description": (
                "Lifecycle Issue: #80\n\n"
                "## Acceptance criteria\n\n- [ ] Deliver\n"
            ),
        },
        "issues": [tracker],
        "comments": list(comments),
    }


def comment(
    number: int,
    author: str,
    body: str,
    *,
    author_type: str = "User",
) -> dict[str, Any]:
    """Build one auditable lifecycle comment."""
    return {
        "body": body,
        "html_url": f"https://github.com/acme/project/issues/80#issuecomment-{number}",
        "user": {"login": author, "type": author_type},
    }


def test_non_proposer_approval_opens_the_gate() -> None:
    """One human other than the proposer is sufficient."""
    result = approval_decision(
        snapshot(comment(1, "reviewer", "/milestone approve"))
    )

    assert result.allowed
    assert "reviewer" in result.summary


@pytest.mark.parametrize(
    "comments",
    [
        (),
        (comment(1, "proposer", "/milestone approve"),),
        (
            comment(
                1,
                "automation[bot]",
                "/milestone approve",
                author_type="Bot",
            ),
        ),
    ],
)
def test_missing_independent_approval_fails_closed(
    comments: tuple[dict[str, Any], ...],
) -> None:
    """Silence, self-approval, and bots do not approve a Milestone."""
    assert not approval_decision(snapshot(*comments)).allowed


def test_unresolved_objection_closes_the_gate() -> None:
    """Any valid objection blocks work until its author withdraws it."""
    objection = comment(
        2, "skeptic", "/milestone object: Missing rollback plan"
    )
    blocked = snapshot(
        comment(1, "reviewer", "/milestone approve"),
        objection,
    )
    wrong_resolver = snapshot(
        *blocked["comments"],
        comment(3, "proposer", f"/milestone resolve: {objection['html_url']}"),
    )
    resolved = snapshot(
        *blocked["comments"],
        comment(4, "skeptic", f"/milestone resolve: {objection['html_url']}"),
    )

    assert not approval_decision(blocked).allowed
    assert not approval_decision(wrong_resolver).allowed
    assert approval_decision(resolved).allowed


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("title", "Create exactly one Issue titled"),
        ("label", "enhancement label"),
        ("proposal", "Proposal section"),
        ("link", "Lifecycle Issue"),
        ("due-date", "real due date"),
    ],
)
def test_tracker_contract_is_fail_closed(change: str, message: str) -> None:
    """A tracker must remain uniquely identifiable and auditable."""
    state = snapshot()
    item = state["issues"][0]
    if change == "title":
        item["title"] = "Milestone 8: Wrong title"
    elif change == "label":
        item["labels"] = []
    elif change == "proposal":
        item["body"] = item["body"].replace(
            "Ship the reviewed batch.", "<!-- empty -->"
        )
    elif change == "due-date":
        state["milestone"]["due_on"] = None
    else:
        state["milestone"]["description"] = (
            "## Acceptance criteria\n\n- [ ] Deliver"
        )

    assert message in "; ".join(tracker_errors(state))


def test_pull_request_records_the_live_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PR gate reads current GitHub state and publishes one check."""
    recorded: list[tuple[str, str, object]] = []
    state = snapshot(comment(1, "reviewer", "/milestone approve"))

    monkeypatch.setitem(
        check_pr.__globals__,
        "run_gh",
        lambda _arguments: '{"milestone":{"number":8},"head":{"sha":"abc"}}',
    )
    monkeypatch.setitem(check_pr.__globals__, "load_snapshot", lambda *_: state)
    monkeypatch.setitem(
        check_pr.__globals__,
        "_record_check",
        lambda repo, sha, decision: recorded.append((repo, sha, decision)),
    )

    result = check_pr("acme/project", 42)

    assert result.allowed
    assert recorded == [("acme/project", "abc", result)]


def test_merge_group_rechecks_every_associated_pull_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The required context is also published on the queued commit."""
    recorded: list[tuple[str, str, object]] = []
    state = snapshot(comment(1, "reviewer", "/milestone approve"))

    monkeypatch.setitem(
        check_merge_group.__globals__,
        "run_gh",
        lambda _arguments: '[{"number":42,"milestone":{"number":8}}]',
    )
    monkeypatch.setitem(
        check_merge_group.__globals__, "load_snapshot", lambda *_: state
    )
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "_record_check",
        lambda repo, sha, decision: recorded.append((repo, sha, decision)),
    )

    result = check_merge_group("acme/project", "queue-sha")

    assert result.allowed
    assert recorded == [("acme/project", "queue-sha", result)]
