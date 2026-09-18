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
refresh_issue_pr_checks = MODULE["refresh_issue_pr_checks"]


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
    state: str = "open",
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
            "state": state,
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


def test_still_open_approved_issue_keeps_passing() -> None:
    """Happy-path regression check: an approved, still-open Issue is
    unaffected by the `require_open` gate (companion to the closed-Issue
    test below, proving the fix does not regress the common case)."""
    result = standalone_issue_approval_decision(
        issue_snapshot(comment(1, "reviewer", "Approve"), state="open"), 210
    )

    assert result.allowed
    assert result.summary == "Issue approved by reviewer"


def test_closed_issue_no_longer_counts_as_approved() -> None:
    """A since-closed Issue must not keep passing on a stale `Approve`.

    Regression test for the fail-open bug found in code review: an Issue
    can be approved while open and then closed independently afterward
    (mis-triaged, marked duplicate, closed by an unrelated PR, etc.) while
    its own closing pull request (`Fixes #N`) is still open. Without this
    `require_open` gate -- mirroring `approval_decision()`'s identical
    check for the tracker path -- `check-pr`/`check-merge-group` would
    keep treating the stale approval as valid every time they re-evaluate
    it, exactly the fail-open hole the tracker path has never had.
    """
    result = standalone_issue_approval_decision(
        issue_snapshot(comment(1, "reviewer", "Approve"), state="closed"), 210
    )

    assert not result.allowed
    assert "#210" in result.summary
    assert "open" in result.summary


def test_require_open_false_allows_a_closed_issue_by_explicit_opt_out() -> None:
    """`require_open=False` is available (mirroring `approval_decision()`'s
    own parameter) even though no current caller passes it -- there is no
    standalone equivalent of the tracker's completed-closure path yet."""
    result = standalone_issue_approval_decision(
        issue_snapshot(comment(1, "reviewer", "Approve"), state="closed"),
        210,
        require_open=False,
    )

    assert result.allowed


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


def test_resolution_by_a_different_author_does_not_count() -> None:
    """Only the objection's own author may withdraw it with `Resolve:` --
    someone else resolving it on their behalf must not reopen the gate
    (mirrors the tracker gate's identical `wrong_resolver` behavior in
    `tests/test_milestone_approval.py::test_unresolved_objection_closes_
    the_gate`, locked in here for the standalone vocabulary too)."""
    objection = comment(2, "skeptic", "Object: Needs a rollback plan")
    result = standalone_issue_approval_decision(
        issue_snapshot(
            comment(1, "reviewer", "Approve"),
            objection,
            comment(3, "worker", f"Resolve: {objection['html_url']}"),
        ),
        210,
    )

    assert not result.allowed


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


def test_standalone_pull_decision_rejects_multiple_closing_issues() -> None:
    """A PR body referencing more than one distinct closing Issue fails
    closed instead of silently evaluating only the first match (code-review
    finding: `.search()` alone would miss every Issue after the first).
    `scripts/validate-pr-policy` already requires exactly one closing Issue
    for a routine work PR, so this is defense-in-depth for `check_issue_
    approval()`'s other use as a standalone CLI entry point."""
    pull = {"milestone": None, "body": "Fixes #210\n\nAlso closes #211"}

    result = _standalone_pull_decision("acme/project", pull)

    assert not result.allowed
    assert "#210" in result.summary
    assert "#211" in result.summary


def test_standalone_pull_decision_allows_a_repeated_reference_to_one_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same Issue number referenced more than once is still just one
    distinct closing Issue, not a multi-Issue rejection."""
    monkeypatch.setitem(
        _standalone_pull_decision.__globals__,
        "load_issue_snapshot",
        lambda repo, number: issue_snapshot(
            comment(1, "reviewer", "Approve"), number=number
        ),
    )
    pull = {
        "milestone": None,
        "body": "Fixes #210.\n\nSee also #210 for the original report.",
    }

    result = _standalone_pull_decision("acme/project", pull)

    assert result.allowed


@pytest.mark.parametrize(
    "head_ref",
    [
        "dependabot/pip/django-5.0.1",
        "automation/bump-lockfiles",
        "release-please--branches--main",
        "sync/main-to-m14-generated-project-fixes-abc1234",
    ],
)
def test_standalone_pull_decision_ignores_automated_prs_with_fake_keyword(
    head_ref: str,
) -> None:
    """An automated PR's own branch-prefix carve-out wins even when its body
    happens to embed a `Fixes #<n>`-shaped string -- for example, an
    upstream changelog Dependabot copies verbatim into its PR description.
    Code-review finding: matching on body text alone, with no bot/automation
    carve-out, could accidentally route such a PR into the approval gate."""
    pull = {
        "milestone": None,
        "head": {"ref": head_ref},
        "body": (
            "Bumps foo from 1.0.0 to 1.0.1.\n\n"
            "## Changelog\n\n### 1.0.1\n\nFixes #210 upstream.\n"
        ),
    }

    result = _standalone_pull_decision("acme/project", pull)

    assert result.allowed
    assert "not part of a Milestone" in result.summary


def test_standalone_pull_decision_still_gates_a_non_automated_head_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pull request with an ordinary `fix/<n>-<slug>` head ref is not
    covered by the automation carve-out and is still gated normally."""
    monkeypatch.setitem(
        _standalone_pull_decision.__globals__,
        "load_issue_snapshot",
        lambda repo, number: issue_snapshot(number=number),
    )
    pull = {
        "milestone": None,
        "head": {"ref": "fix/210-outage"},
        "body": "Fixes #210",
    }

    result = _standalone_pull_decision("acme/project", pull)

    assert not result.allowed
    assert "#210" in result.summary


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


def test_merge_group_revalidation_rejects_a_since_closed_approved_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end regression for the fail-open bug: an Issue approved while
    open, then closed independently while its pull request is still open
    (mis-triaged, marked duplicate, etc.), must fail the merge queue's
    "Revalidate queued Milestone approval" step -- not keep passing on the
    now-stale approval."""
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
        lambda repo, number: issue_snapshot(
            comment(1, "reviewer", "Approve"), number=number, state="closed"
        ),
    )
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "_record_check",
        lambda repo, sha, decision: None,
    )

    result = check_merge_group("acme/project", "queue-sha")

    assert not result.allowed
    assert "#210" in result.summary
    assert "open" in result.summary


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


def test_merge_group_blocks_on_one_unapproved_pr_among_several(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A merge-group commit can represent several queued pull requests at
    once (a batch merge); one unapproved standalone/hotfix Issue among them
    must still block the whole merge-group check, and an automated PR with
    no linked Issue in the same batch must not interfere either way."""
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "run_gh",
        lambda _arguments: json.dumps(
            [
                {"number": 42, "milestone": None, "body": "Fixes #210"},
                {"number": 43, "milestone": None, "body": "Fixes #211"},
                {
                    "number": 44,
                    "milestone": None,
                    "body": "Bumps foo from 1.0.0 to 1.0.1.",
                },
            ]
        ),
    )
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "load_issue_snapshot",
        lambda repo, number: issue_snapshot(
            *([comment(1, "reviewer", "Approve")] if number == 211 else []),
            number=number,
        ),
    )
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "_record_check",
        lambda repo, sha, decision: None,
    )

    result = check_merge_group("acme/project", "queue-sha")

    assert not result.allowed
    assert "#210" in result.summary
    assert "#211" not in result.summary


def test_merge_group_allows_every_pr_when_all_are_approved_or_unaffected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same multi-PR merge group passes once every standalone Issue in
    it is approved, proving the blocking test above is not a false
    positive from some other cause.
    """
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "run_gh",
        lambda _arguments: json.dumps(
            [
                {"number": 42, "milestone": None, "body": "Fixes #210"},
                {"number": 43, "milestone": None, "body": "Fixes #211"},
                {
                    "number": 44,
                    "milestone": None,
                    "body": "Bumps foo from 1.0.0 to 1.0.1.",
                },
            ]
        ),
    )
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "load_issue_snapshot",
        lambda repo, number: issue_snapshot(
            comment(1, "reviewer", "Approve"), number=number
        ),
    )
    monkeypatch.setitem(
        check_merge_group.__globals__,
        "_record_check",
        lambda repo, sha, decision: None,
    )

    result = check_merge_group("acme/project", "queue-sha")

    assert result.allowed


def test_refresh_issue_pr_checks_recheck_only_matching_prs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CI re-trigger wired into work-item-lifecycle.yml (#743): a fresh
    `Approve`/`Admin-approve:`/`Object:`/`Resolve:` comment on a standalone/
    hotfix Issue must re-run `check-pr` on the specific PR(s) that close it
    -- not every open PR, and not one that already has a Milestone (which
    inherits tracker approval and is unaffected by this Issue's comments).
    """
    checked: list[int] = []
    monkeypatch.setitem(
        refresh_issue_pr_checks.__globals__,
        "run_gh",
        lambda _arguments: json.dumps(
            [
                {"number": 42, "milestone": None, "body": "Fixes #210"},
                {"number": 43, "milestone": None, "body": "Fixes #999"},
                {
                    "number": 44,
                    "milestone": {"number": 14},
                    "body": "Fixes #210",
                },
                {
                    "number": 45,
                    "milestone": None,
                    "body": "Bumps foo from 1.0.0 to 1.0.1.",
                },
            ]
        ),
    )
    monkeypatch.setitem(
        refresh_issue_pr_checks.__globals__,
        "check_pr",
        lambda repo, number: checked.append(number),
    )

    result = refresh_issue_pr_checks("acme/project", 210)

    assert result.allowed
    assert checked == [42]
    assert "1" in result.summary
    assert "#210" in result.summary


def test_refresh_issue_pr_checks_rechecks_a_pr_with_multiple_closing_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PR that closes this Issue among several still gets refreshed --
    `_standalone_pull_decision()` owns the "more than one closing Issue"
    fail-closed decision when `check-pr` actually re-runs, so the refresh
    step itself does not need to duplicate that judgment.
    """
    checked: list[int] = []
    monkeypatch.setitem(
        refresh_issue_pr_checks.__globals__,
        "run_gh",
        lambda _arguments: json.dumps(
            [
                {
                    "number": 42,
                    "milestone": None,
                    "body": "Fixes #210\n\nAlso closes #211",
                }
            ]
        ),
    )
    monkeypatch.setitem(
        refresh_issue_pr_checks.__globals__,
        "check_pr",
        lambda repo, number: checked.append(number),
    )

    result = refresh_issue_pr_checks("acme/project", 210)

    assert result.allowed
    assert checked == [42]


def test_refresh_issue_pr_checks_is_a_no_op_with_nothing_to_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No open PR references this Issue: the refresh is a harmless no-op,
    never a failure."""
    checked: list[int] = []
    monkeypatch.setitem(
        refresh_issue_pr_checks.__globals__,
        "run_gh",
        lambda _arguments: json.dumps([]),
    )
    monkeypatch.setitem(
        refresh_issue_pr_checks.__globals__,
        "check_pr",
        lambda repo, number: checked.append(number),
    )

    result = refresh_issue_pr_checks("acme/project", 210)

    assert result.allowed
    assert checked == []
