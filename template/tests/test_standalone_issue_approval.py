"""Tests for the standalone/hotfix/release-recovery Issue-approval gate (#743).

Covers the second half of the maintainer's two-point approval model: a
Milestone-scoped Issue keeps inheriting its tracker's approval (unchanged,
covered by `tests/test_milestone_approval.py` and
`tests/test_milestone_scope.py`); an Issue with no Milestone of its own
must itself carry a valid approval before the pull request that closes it
via `Closes`/`Fixes`/`Resolves #N` can merge.

The approval vocabulary here is `Approve` / `Admin-approve: <reason>` /
`Object: <reason>` / `Resolve: <target>` -- plain text, case-insensitive --
per the maintainer's own decision recorded on Issue #743
(2026-09-18T02:00:35Z, before this implementation started). It is
deliberately a *separate, parallel* vocabulary from the tracker's and
scope-expansion gate's `/milestone approve` family, not a case-insensitive
relaxation of it: several tests below confirm the two never cross-match.
"""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "sync_milestone_state.py")
)
standalone_issue_approval_decision = MODULE[
    "standalone_issue_approval_decision"
]
check_issue_approval = MODULE["check_issue_approval"]
_pull_decision = MODULE["_pull_decision"]
_standalone_pull_decision = MODULE["_standalone_pull_decision"]
check_pr = MODULE["check_pr"]
check_merge_group = MODULE["check_merge_group"]


@pytest.fixture(autouse=True)
def _no_network_permission_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default collaborator-permission lookups to unknown, never the network."""
    monkeypatch.setitem(
        standalone_issue_approval_decision.__globals__,
        "_collaborator_permission",
        lambda repo, username: None,
    )


def _stub_permission(
    monkeypatch: pytest.MonkeyPatch, permission: str | None
) -> None:
    """Make every collaborator-permission lookup return one fixed value."""
    monkeypatch.setitem(
        standalone_issue_approval_decision.__globals__,
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
    """Build one auditable Issue comment."""
    return {
        "body": body,
        "html_url": (
            f"https://github.com/acme/project/issues/210#issuecomment-{number}"
        ),
        "user": {"login": author, "type": author_type},
        "created_at": created_at,
    }


def issue_snapshot(
    *comments: dict[str, Any],
    proposer: str = "worker",
    updated_at: str | None = None,
    milestone: dict[str, Any] | None = None,
    number: int = 210,
) -> dict[str, Any]:
    """Build one work-Issue snapshot as `load_issue_snapshot()` returns it."""
    return {
        "repo": "acme/project",
        "issue": {
            "number": number,
            "title": "Fix the outage",
            "body": "## Acceptance criteria\n\n- [ ] Ship the fix.\n",
            "user": {"login": proposer, "type": "User"},
            "updated_at": updated_at,
            "milestone": milestone,
        },
        "comments": list(comments),
    }


def test_no_approval_blocks_a_standalone_issue() -> None:
    """A standalone Issue with no Milestone and no approval fails closed."""
    result = standalone_issue_approval_decision(issue_snapshot(), 210)

    assert not result.allowed
    assert "#210" in result.summary
    assert "no Milestone" in result.summary


def test_non_proposer_approval_unblocks_a_standalone_issue() -> None:
    """One non-proposer `Approve` comment satisfies the gate."""
    result = standalone_issue_approval_decision(
        issue_snapshot(comment(1, "reviewer", "Approve")), 210
    )

    assert result.allowed
    assert result.summary == "Issue approved by reviewer"


@pytest.mark.parametrize(
    "word", ["approve", "APPROVE", "Approve", "  Approve  "]
)
def test_approval_keyword_is_case_and_whitespace_insensitive(word: str) -> None:
    """The plain-text keyword is deliberately lenient, unlike the slash
    command."""
    result = standalone_issue_approval_decision(
        issue_snapshot(comment(1, "reviewer", word)), 210
    )

    assert result.allowed


def test_proposer_self_approval_does_not_count() -> None:
    """The proposer cannot approve their own standalone/hotfix Issue."""
    result = standalone_issue_approval_decision(
        issue_snapshot(comment(1, "worker", "Approve")), 210
    )

    assert not result.allowed


def test_admin_self_approval_opens_the_gate_with_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proposer may self-approve with `admin` repo permission and a reason.

    Reuses the exact same admin-self-approval mechanism as the tracker's own
    gate and the scope-expansion gate -- required for a genuine hotfix that
    cannot wait for a second reviewer.
    """
    _stub_permission(monkeypatch, "admin")
    result = standalone_issue_approval_decision(
        issue_snapshot(
            comment(
                1,
                "worker",
                "Admin-approve: production outage, no reviewer",
            )
        ),
        210,
    )

    assert result.allowed
    assert result.summary == (
        "Issue admin self-approved by worker "
        "(reason: production outage, no reviewer)"
    )


def test_admin_self_approval_rejects_non_admin_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A proposer without `admin` repo permission may not self-approve."""
    _stub_permission(monkeypatch, "write")
    result = standalone_issue_approval_decision(
        issue_snapshot(
            comment(1, "worker", "Admin-approve: outside collaborator")
        ),
        210,
    )

    assert not result.allowed


def test_admin_self_approval_rejects_empty_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reason is mandatory, not just the `Admin-approve:` prefix."""
    _stub_permission(monkeypatch, "admin")
    result = standalone_issue_approval_decision(
        issue_snapshot(comment(1, "worker", "Admin-approve:")), 210
    )

    assert not result.allowed


def test_unresolved_objection_blocks_the_gate() -> None:
    """An outstanding objection blocks a standalone Issue like anywhere else."""
    result = standalone_issue_approval_decision(
        issue_snapshot(
            comment(1, "reviewer", "Approve"),
            comment(2, "skeptic", "Object: Needs a rollback plan"),
        ),
        210,
    )

    assert not result.allowed


def test_resolved_objection_reopens_the_gate() -> None:
    """The objection's own author withdrawing it with `Resolve:` unblocks
    work."""
    objection = comment(2, "skeptic", "Object: Needs a rollback plan")
    result = standalone_issue_approval_decision(
        issue_snapshot(
            comment(1, "reviewer", "Approve"),
            objection,
            comment(3, "skeptic", f"Resolve: {objection['html_url']}"),
        ),
        210,
    )

    assert result.allowed


def test_approval_becomes_stale_after_a_later_issue_edit() -> None:
    """Editing the Issue body after approval invalidates it (#632's binding)."""
    result = standalone_issue_approval_decision(
        issue_snapshot(
            comment(
                1,
                "reviewer",
                "Approve",
                created_at="2026-01-01T00:00:00Z",
            ),
            updated_at="2026-01-01T01:00:00Z",
        ),
        210,
    )

    assert not result.allowed
    assert "invalidated" in result.summary
    assert "reviewer" in result.summary


def test_approval_posted_after_the_last_edit_is_not_stale() -> None:
    """An approval posted after the Issue's own last update still counts."""
    result = standalone_issue_approval_decision(
        issue_snapshot(
            comment(
                1,
                "reviewer",
                "Approve",
                created_at="2026-01-02T00:00:00Z",
            ),
            updated_at="2026-01-01T00:00:00Z",
        ),
        210,
    )

    assert result.allowed
    assert result.summary == "Issue approved by reviewer"


def test_milestone_slash_vocabulary_does_not_count_on_a_standalone_issue() -> (
    None
):
    """The tracker's `/milestone approve` family is a separate, independent
    vocabulary: it must never satisfy the standalone Issue-approval gate."""
    result = standalone_issue_approval_decision(
        issue_snapshot(
            comment(1, "reviewer", "/milestone approve"),
        ),
        210,
    )

    assert not result.allowed


def test_check_issue_approval_defers_milestone_scoped_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Milestone-scoped Issue needs no per-Issue approval (unchanged)."""
    approval_calls: list[int] = []

    def fake_load_snapshot(repo: str, number: int) -> dict[str, Any]:
        del repo
        return {
            "repo": "acme/project",
            "milestone": {"number": number, "title": "Delivery"},
            "issues": [],
            "comments": [],
        }

    def fake_approval_decision(snapshot: dict[str, Any]) -> object:
        approval_calls.append(snapshot["milestone"]["number"])
        return MODULE["Decision"](True, "Approved by reviewer")

    monkeypatch.setitem(
        check_issue_approval.__globals__, "load_snapshot", fake_load_snapshot
    )
    monkeypatch.setitem(
        check_issue_approval.__globals__,
        "load_issue_snapshot",
        lambda repo, number: issue_snapshot(
            milestone={"number": 14}, number=number
        ),
    )
    monkeypatch.setitem(
        check_issue_approval.__globals__,
        "approval_decision",
        fake_approval_decision,
    )

    result = check_issue_approval("acme/project", 210)

    assert result.allowed
    assert approval_calls == [14]


def test_check_issue_approval_gates_a_standalone_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An Issue with no Milestone runs the standalone approval gate."""
    monkeypatch.setitem(
        check_issue_approval.__globals__,
        "load_issue_snapshot",
        lambda repo, number: issue_snapshot(number=number),
    )

    result = check_issue_approval("acme/project", 210)

    assert not result.allowed
    assert "#210" in result.summary


def test_pull_decision_ignores_a_pull_request_with_no_closing_issue() -> None:
    """Automated PRs (Dependabot, release-please, main-sync bridge, etc.) with
    no `Closes`/`Fixes`/`Resolves` keyword in the body have nothing to gate,
    identical to `scripts/check-scope-gate`'s own carve-out."""
    pull = {"milestone": None, "body": "Bumps foo from 1.0.0 to 1.0.1."}

    result = _pull_decision("acme/project", pull)

    assert result.allowed
    assert "not part of a Milestone" in result.summary


def test_pull_decision_ignores_a_pull_request_with_no_body() -> None:
    """A pull request with an entirely absent body is treated the same way."""
    pull = {"milestone": None, "body": None}

    result = _pull_decision("acme/project", pull)

    assert result.allowed


def test_standalone_pull_decision_blocks_an_unapproved_closing_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A standalone/hotfix PR closing an unapproved Issue is blocked."""
    monkeypatch.setitem(
        _standalone_pull_decision.__globals__,
        "load_issue_snapshot",
        lambda repo, number: issue_snapshot(number=number),
    )
    pull = {"milestone": None, "body": "Fixes production outage.\n\nFixes #210"}

    result = _standalone_pull_decision("acme/project", pull)

    assert not result.allowed
    assert "#210" in result.summary


def test_standalone_pull_decision_allows_an_approved_closing_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A standalone/hotfix PR closing an approved Issue is allowed."""
    monkeypatch.setitem(
        _standalone_pull_decision.__globals__,
        "load_issue_snapshot",
        lambda repo, number: issue_snapshot(
            comment(1, "reviewer", "Approve"), number=number
        ),
    )
    pull = {"milestone": None, "body": "Closes #210"}

    result = _standalone_pull_decision("acme/project", pull)

    assert result.allowed


def test_check_pr_routes_a_milestone_less_pull_request_through_issue_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`check-pr` (the live "Validate Milestone approval" step) wires through
    to the standalone Issue-approval gate for a PR with no Milestone."""
    recorded: list[tuple[str, str, object]] = []

    monkeypatch.setitem(
        check_pr.__globals__,
        "run_gh",
        lambda _arguments: (
            '{"milestone":null,"body":"Fixes #210","head":{"sha":"abc"}}'
        ),
    )
    monkeypatch.setitem(
        check_pr.__globals__,
        "load_issue_snapshot",
        lambda repo, number: issue_snapshot(number=number),
    )
    monkeypatch.setitem(
        check_pr.__globals__,
        "_record_check",
        lambda repo, sha, decision: recorded.append((repo, sha, decision)),
    )

    result = check_pr("acme/project", 42)

    assert not result.allowed
    assert "#210" in result.summary
    assert recorded == [("acme/project", "abc", result)]


def test_check_pr_allows_an_approved_milestone_less_pull_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same wiring allows the pull request once the Issue is approved."""
    monkeypatch.setitem(
        check_pr.__globals__,
        "run_gh",
        lambda _arguments: (
            '{"milestone":null,"body":"Fixes #210","head":{"sha":"abc"}}'
        ),
    )
    monkeypatch.setitem(
        check_pr.__globals__,
        "load_issue_snapshot",
        lambda repo, number: issue_snapshot(
            comment(1, "reviewer", "Approve"), number=number
        ),
    )
    monkeypatch.setitem(
        check_pr.__globals__, "_record_check", lambda repo, sha, decision: None
    )

    result = check_pr("acme/project", 42)

    assert result.allowed


def test_merge_group_revalidates_a_milestone_less_pull_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The merge queue's "Revalidate queued Milestone approval" step also
    blocks an unapproved standalone/hotfix Issue via `check-merge-group`."""
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "run_gh",
        lambda _arguments: json.dumps(
            [{"number": 42, "milestone": None, "body": "Fixes #210"}]
        ),
    )
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "load_issue_snapshot",
        lambda repo, number: issue_snapshot(number=number),
    )
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "_record_check",
        lambda repo, sha, decision: None,
    )

    result = check_merge_group("acme/project", "queue-sha")

    assert not result.allowed
    assert "#210" in result.summary


def test_merge_group_allows_automated_pull_requests_with_no_closing_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dependabot/release-please/main-sync PRs pass merge-queue revalidation
    unaffected, exactly as they did before #743."""
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "run_gh",
        lambda _arguments: json.dumps(
            [
                {
                    "number": 99,
                    "milestone": None,
                    "body": "Bumps foo from 1.0.0 to 1.0.1.",
                }
            ]
        ),
    )
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "_record_check",
        lambda repo, sha, decision: None,
    )

    result = check_merge_group("acme/project", "queue-sha")

    assert result.allowed
