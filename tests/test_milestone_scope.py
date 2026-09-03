"""Tests for the work-Issue scope-expansion sentinel and approval gate."""

from __future__ import annotations

import json
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "sync_milestone_state.py")
)
has_scope_sentinel = MODULE["has_scope_sentinel"]
scope_decision = MODULE["scope_decision"]
check_scope = MODULE["check_scope"]


@pytest.fixture(autouse=True)
def _no_network_permission_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default collaborator-permission lookups to unknown, never the network."""
    monkeypatch.setitem(
        scope_decision.__globals__,
        "_collaborator_permission",
        lambda repo, username: None,
    )


def _stub_permission(
    monkeypatch: pytest.MonkeyPatch, permission: str | None
) -> None:
    """Make every collaborator-permission lookup return one fixed value."""
    monkeypatch.setitem(
        scope_decision.__globals__,
        "_collaborator_permission",
        lambda repo, username: permission,
    )


def comment(
    number: int,
    author: str,
    body: str,
    *,
    author_type: str = "User",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build one auditable work-Issue comment."""
    return {
        "body": body,
        "html_url": (
            f"https://github.com/acme/project/issues/101#issuecomment-{number}"
        ),
        "user": {"login": author, "type": author_type},
        "created_at": created_at,
    }


def issue_snapshot(
    body: str,
    *comments: dict[str, Any],
    proposer: str = "worker",
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Build one work-Issue snapshot as `load_issue_snapshot()` returns it."""
    return {
        "repo": "acme/project",
        "issue": {
            "number": 101,
            "title": "Add retry queue",
            "body": body,
            "user": {"login": proposer, "type": "User"},
            "updated_at": updated_at,
        },
        "comments": list(comments),
    }


IN_SCOPE_BODY = "## Acceptance criteria\n\n- [ ] Ship the retry queue.\n"
EXPANDED_BODY = (
    "## Acceptance criteria\n\n- [ ] Ship the retry queue.\n\n"
    "Tracker scope: expanded\n\n"
    "Also touches the dead-letter queue, which the tracker never mentioned.\n"
)


def test_has_scope_sentinel_detects_the_literal_marker_line() -> None:
    """Detection is a literal, whole-line match -- not a substring search."""
    assert has_scope_sentinel(EXPANDED_BODY)
    assert not has_scope_sentinel(IN_SCOPE_BODY)
    assert not has_scope_sentinel(
        "This mentions Tracker scope: expanded mid-sentence, not on its own "
        "line."
    )


def test_no_sentinel_inherits_the_tracker_approval_with_no_extra_gate() -> None:
    """A work Issue with no sentinel needs no independent approval at all."""
    result = scope_decision(issue_snapshot(IN_SCOPE_BODY))

    assert result.allowed
    assert "inherits" in result.summary.lower()


def test_sentinel_present_requires_independent_non_proposer_approval() -> None:
    """Declaring scope expansion, with no reviewer yet, blocks the gate."""
    result = scope_decision(issue_snapshot(EXPANDED_BODY))

    assert not result.allowed
    assert "Scope expansion" in result.summary


def test_sentinel_present_and_reviewer_approved_opens_the_gate() -> None:
    """One non-proposer `/milestone approve` satisfies the scope gate."""
    result = scope_decision(
        issue_snapshot(
            EXPANDED_BODY, comment(1, "reviewer", "/milestone approve")
        )
    )

    assert result.allowed
    assert result.summary == "Scope expansion approved by reviewer"


def test_proposer_self_approval_without_the_sentinel_is_a_non_issue() -> None:
    """A self-approve comment on an in-scope Issue changes nothing.

    Only the sentinel activates this gate; a stray `/milestone approve`
    from the proposer on an ordinary in-scope Issue is simply irrelevant.
    """
    result = scope_decision(
        issue_snapshot(
            IN_SCOPE_BODY, comment(1, "worker", "/milestone approve")
        )
    )

    assert result.allowed
    assert "inherits" in result.summary.lower()


def test_proposer_self_approval_with_the_sentinel_does_not_count() -> None:
    """A proposer cannot approve their own declared scope expansion."""
    result = scope_decision(
        issue_snapshot(
            EXPANDED_BODY, comment(1, "worker", "/milestone approve")
        )
    )

    assert not result.allowed


def test_admin_self_approval_opens_the_scope_gate_with_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proposer may self-approve a scope expansion with `admin` permission.

    Reuses the exact same admin-self-approval mechanism the tracker's own
    `/milestone approve` gate uses (#518/#549/#550) -- required on a
    single-human-account repository where no second approver exists.
    """
    _stub_permission(monkeypatch, "admin")
    result = scope_decision(
        issue_snapshot(
            EXPANDED_BODY,
            comment(
                1,
                "worker",
                "/milestone admin-approve: no reviewer before the deadline",
            ),
        )
    )

    assert result.allowed
    assert result.summary == (
        "Scope expansion admin self-approved by worker "
        "(reason: no reviewer before the deadline)"
    )


def test_unresolved_objection_blocks_the_scope_gate_too() -> None:
    """An outstanding objection blocks a scope expansion like it blocks work."""
    result = scope_decision(
        issue_snapshot(
            EXPANDED_BODY,
            comment(1, "reviewer", "/milestone approve"),
            comment(2, "skeptic", "/milestone object: Needs a rollback plan"),
        )
    )

    assert not result.allowed


def test_check_scope_loads_live_issue_and_comment_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI entry point fetches one Issue and its own comments only."""
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        if arguments[:2] == ["api", "repos/acme/project/issues/101"]:
            return json.dumps(
                {
                    "number": 101,
                    "body": EXPANDED_BODY,
                    "user": {"login": "worker", "type": "User"},
                }
            )
        return "[]"

    monkeypatch.setitem(check_scope.__globals__, "run_gh", fake_run_gh)

    result = check_scope("acme/project", 101)

    assert not result.allowed
    assert any("issues/101/comments" in "/".join(call) for call in calls)


def _fake_run_gh(
    body: str, comments: list[dict[str, Any]], updated_at: str
) -> Callable[[list[str]], str]:
    """Build a `run_gh()` stand-in for one live Issue + comments pair.

    Used to prove `check-scope` -- the CLI Issue #632 wires into
    `pr-policy.yml` -- reads live Issue state correctly end to end,
    covering the same three outcomes the new workflow step depends on:
    no sentinel (allowed), sentinel with no approval (blocked), and
    sentinel with a non-proposer approval (allowed).
    """

    def fake_run_gh(arguments: list[str]) -> str:
        if arguments[:2] == ["api", "repos/acme/project/issues/101"]:
            return json.dumps(
                {
                    "number": 101,
                    "body": body,
                    "user": {"login": "worker", "type": "User"},
                    "updated_at": updated_at,
                }
            )
        return json.dumps(comments)

    return fake_run_gh


def test_check_scope_allows_a_pull_request_with_no_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No sentinel: the CI gate never blocks an ordinary in-scope PR."""
    monkeypatch.setitem(
        check_scope.__globals__,
        "run_gh",
        _fake_run_gh(IN_SCOPE_BODY, [], "2026-01-01T00:00:00Z"),
    )

    result = check_scope("acme/project", 101)

    assert result.allowed


def test_check_scope_blocks_an_unapproved_scope_expanded_pull_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sentinel present, no independent approval: the CI gate blocks it."""
    monkeypatch.setitem(
        check_scope.__globals__,
        "run_gh",
        _fake_run_gh(EXPANDED_BODY, [], "2026-01-01T00:00:00Z"),
    )

    result = check_scope("acme/project", 101)

    assert not result.allowed


def test_check_scope_allows_an_approved_scope_expanded_pull_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sentinel present with a fresh non-proposer approval: allowed."""
    monkeypatch.setitem(
        check_scope.__globals__,
        "run_gh",
        _fake_run_gh(
            EXPANDED_BODY,
            [comment(1, "reviewer", "/milestone approve", created_at=None)],
            "2026-01-01T00:00:00Z",
        ),
    )

    result = check_scope("acme/project", 101)

    assert result.allowed


def test_no_sentinel_inherits_even_after_a_later_edit() -> None:
    """Fingerprint-binding only applies once a sentinel activates the gate."""
    result = scope_decision(
        issue_snapshot(IN_SCOPE_BODY, updated_at="2026-01-01T00:00:00Z")
    )

    assert result.allowed
    assert "inherits" in result.summary.lower()


def test_scope_approval_becomes_stale_after_a_later_body_edit() -> None:
    """Editing the work Issue body after approval invalidates it (#632)."""
    result = scope_decision(
        issue_snapshot(
            EXPANDED_BODY,
            comment(
                1,
                "reviewer",
                "/milestone approve",
                created_at="2026-01-01T00:00:00Z",
            ),
            updated_at="2026-01-01T01:00:00Z",
        )
    )

    assert not result.allowed
    assert "invalidated" in result.summary
    assert "reviewer" in result.summary


def test_scope_approval_posted_after_the_last_edit_is_not_stale() -> None:
    """An approval posted after the Issue's own last update still counts."""
    result = scope_decision(
        issue_snapshot(
            EXPANDED_BODY,
            comment(
                1,
                "reviewer",
                "/milestone approve",
                created_at="2026-01-02T00:00:00Z",
            ),
            updated_at="2026-01-01T00:00:00Z",
        )
    )

    assert result.allowed
    assert result.summary == "Scope expansion approved by reviewer"
