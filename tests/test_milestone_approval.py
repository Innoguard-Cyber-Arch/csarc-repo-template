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
_approval_is_stale = MODULE["_approval_is_stale"]


@pytest.fixture(autouse=True)
def _no_network_permission_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default collaborator-permission lookups to unknown, never the network."""
    monkeypatch.setitem(
        approval_decision.__globals__,
        "_collaborator_permission",
        lambda repo, username: None,
    )


def _stub_permission(
    monkeypatch: pytest.MonkeyPatch, permission: str | None
) -> None:
    """Make every collaborator-permission lookup return one fixed value."""
    monkeypatch.setitem(
        approval_decision.__globals__,
        "_collaborator_permission",
        lambda repo, username: permission,
    )


def snapshot(
    *comments: dict[str, Any], tracker_updated_at: str | None = None
) -> dict[str, Any]:
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
        "updated_at": tracker_updated_at,
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
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build one auditable lifecycle comment."""
    return {
        "body": body,
        "html_url": f"https://github.com/acme/project/issues/80#issuecomment-{number}",
        "user": {"login": author, "type": author_type},
        "created_at": created_at,
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


def test_admin_self_approval_opens_the_gate_with_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A proposer with `admin` repo permission may self-approve.

    This does not key off a comment's `author_association`: that field's
    visibility depends on whether the commenter's organization membership
    is public, which the workflow's own token may not be able to see.
    Repository collaborator permission is unaffected by that setting.
    """
    _stub_permission(monkeypatch, "admin")
    result = approval_decision(
        snapshot(
            comment(
                1,
                "proposer",
                "/milestone admin-approve: no reviewer before the deadline",
            )
        )
    )

    assert result.allowed
    assert result.summary == (
        "Admin self-approved by proposer "
        "(reason: no reviewer before the deadline)"
    )


def test_admin_self_approval_rejects_non_admin_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A proposer without `admin` repo permission may not self-approve."""
    _stub_permission(monkeypatch, "write")
    result = approval_decision(
        snapshot(
            comment(
                1,
                "proposer",
                "/milestone admin-approve: outside collaborator",
            )
        )
    )

    assert not result.allowed


@pytest.mark.parametrize(
    "admin_comment",
    [
        comment(
            1,
            "proposer",
            "/milestone admin-approve:",
        ),
        comment(
            1,
            "reviewer",
            "/milestone admin-approve: pretending to be the proposer",
        ),
    ],
)
def test_admin_self_approval_rejects_impostors_and_empty_reasons(
    admin_comment: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty reason or wrong author bypasses review despite admin permission."""
    _stub_permission(monkeypatch, "admin")
    assert not approval_decision(snapshot(admin_comment)).allowed


def test_ordinary_approval_still_works_alongside_admin_approve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real reviewer approval is reported normally, distinct from a bypass."""
    _stub_permission(monkeypatch, "admin")
    result = approval_decision(
        snapshot(
            comment(
                1,
                "proposer",
                "/milestone admin-approve: backup path",
            ),
            comment(2, "reviewer", "/milestone approve"),
        )
    )

    assert result.allowed
    assert result.summary == "Approved by reviewer"


def test_unresolved_objection_blocks_admin_self_approval_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An admin bypass never overrides an outstanding objection."""
    _stub_permission(monkeypatch, "admin")
    objection = comment(
        2, "skeptic", "/milestone object: Missing rollback plan"
    )
    result = approval_decision(
        snapshot(
            comment(
                1,
                "proposer",
                "/milestone admin-approve: ship now",
            ),
            objection,
        )
    )

    assert not result.allowed


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


@pytest.mark.parametrize(
    ("item_updated_at", "comment_created_at", "expected"),
    [
        (None, "2026-01-01T00:00:00Z", False),
        ("2026-01-01T00:00:00Z", None, False),
        (None, None, False),
        # Same instant, or within the recording-lag grace window: fresh.
        ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", False),
        ("2026-01-01T00:00:30Z", "2026-01-01T00:00:00Z", False),
        # Comfortably beyond the grace window: stale.
        ("2026-01-01T00:05:00Z", "2026-01-01T00:00:00Z", True),
        # The comment is itself the later event: never stale.
        ("2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z", False),
    ],
)
def test_approval_is_stale_uses_a_grace_window_around_recording_lag(
    item_updated_at: str | None, comment_created_at: str | None, expected: bool
) -> None:
    """The staleness signal is `updated_at` vs. the comment's own timestamp.

    A short grace window absorbs GitHub's own second-or-two lag between a
    comment's `created_at` and the resulting bump to its parent Issue's
    `updated_at` (see the module's own `_STALE_GRACE_SECONDS` docstring),
    without weakening detection of a genuine later edit or comment.
    """
    assert _approval_is_stale(item_updated_at, comment_created_at) is expected


def test_stale_approval_no_longer_opens_the_gate() -> None:
    """An approval predating a later tracker update needs redoing (#632)."""
    result = approval_decision(
        snapshot(
            comment(
                1,
                "reviewer",
                "/milestone approve",
                created_at="2026-01-01T00:00:00Z",
            ),
            tracker_updated_at="2026-01-01T01:00:00Z",
        )
    )

    assert not result.allowed
    assert "invalidated" in result.summary
    assert "reviewer" in result.summary


def test_approval_posted_after_the_last_update_is_not_stale() -> None:
    """An approval posted after the tracker's own last update still counts."""
    result = approval_decision(
        snapshot(
            comment(
                1,
                "reviewer",
                "/milestone approve",
                created_at="2026-01-02T00:00:00Z",
            ),
            tracker_updated_at="2026-01-01T00:00:00Z",
        )
    )

    assert result.allowed
    assert result.summary == "Approved by reviewer"


def test_missing_timestamps_never_invent_staleness() -> None:
    """No `created_at`/`updated_at` data reads as "cannot tell", not stale.

    Locks in backward compatibility: every pre-#632 caller and test that
    never supplied these fields keeps behaving exactly as before.
    """
    result = approval_decision(
        snapshot(
            comment(1, "reviewer", "/milestone approve"),
            tracker_updated_at="2026-01-01T00:00:00Z",
        )
    )

    assert result.allowed


def test_stale_admin_self_approval_no_longer_opens_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later tracker edit invalidates an admin self-approval too."""
    _stub_permission(monkeypatch, "admin")
    result = approval_decision(
        snapshot(
            comment(
                1,
                "proposer",
                "/milestone admin-approve: no reviewer before the deadline",
                created_at="2026-01-01T00:00:00Z",
            ),
            tracker_updated_at="2026-01-01T01:00:00Z",
        )
    )

    assert not result.allowed
    assert "invalidated" in result.summary


def test_fresh_approval_after_a_stale_one_still_opens_the_gate() -> None:
    """A later re-approval past the edit satisfies the gate normally."""
    result = approval_decision(
        snapshot(
            comment(
                1,
                "reviewer",
                "/milestone approve",
                created_at="2026-01-01T00:00:00Z",
            ),
            comment(
                2,
                "reviewer",
                "/milestone approve",
                created_at="2026-01-02T00:00:00Z",
            ),
            tracker_updated_at="2026-01-01T12:00:00Z",
        )
    )

    assert result.allowed
    assert result.summary == "Approved by reviewer"
