"""Hosted-only half of `sync_milestone_state.py` (#1177); local renders omit it.

The shared helpers come from `sync_milestone_state.py` when it loads this file.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sync_milestone_state import (
        _CLOSING_KEYWORD,
        _ISSUE_VOCABULARY,
        CHECK_NAME,
        Decision,
        _admin_self_approval_allowed,
        _approval_records,
        _gate_decision,
        _pages,
        _SnapshotGitHub,
        _vocabulary_approval_records,
        approval_decision,
        closure_decision,
        has_scope_sentinel,
        load_issue_snapshot,
        load_snapshot,
        run_gh,
        tracker,
        tracker_errors,
    )

# Work Issue actions that can change a closed Milestone's delivery facts.
# Every other work Issue event (labels, edits, comments) leaves it alone.
_CLOSED_MILESTONE_ACTIONS = {"milestoned", "demilestoned", "reopened"}
_AUTOMATED_PULL_REQUEST_HEAD_PREFIXES = (
    "dependabot/",
    "automation/",
    "release-please--",
    "sync/main-to-",
)


def scope_decision(
    snapshot: dict[str, Any], *, allow_admin_self_approval: bool | None = None
) -> Decision:
    """Require independent approval only for a self-declared scope expansion.

    A work Issue inherits its tracker's approval by default -- no sentinel
    means no extra gate, exactly like today, keeping the common in-scope
    case exactly as cheap as it already is. Only when the Issue's own body
    contains the literal `Tracker scope: expanded` marker line does it need
    its own non-proposer approval (or admin self-approval), evaluated with
    the exact same `/milestone` comment vocabulary as the tracker's gate.
    That approval is bound to this Issue's body as of the approval
    comment's own timestamp: editing the body afterward invalidates it
    (#632; see `_approval_is_stale()`).
    """
    issue = snapshot.get("issue")
    if not isinstance(issue, dict):
        return Decision(False, "GitHub returned invalid Issue data")
    body = issue.get("body")
    if not isinstance(body, str) or not has_scope_sentinel(body):
        return Decision(True, "In scope; inherits the tracker's approval")
    proposer = issue.get("user", {}).get("login")
    approvals, objections, resolved, admin_approvals, stale = _approval_records(
        snapshot, proposer, item_updated_at=issue.get("updated_at")
    )
    if allow_admin_self_approval is None and admin_approvals and not approvals:
        allow_admin_self_approval = _admin_self_approval_allowed(
            _SnapshotGitHub(snapshot), str(snapshot.get("repo") or ""), issue
        )
    if allow_admin_self_approval is None:
        allow_admin_self_approval = False
    return _gate_decision(
        approvals,
        objections,
        resolved,
        admin_approvals,
        stale,
        missing_message=(
            "Scope expansion declared: a person other than the proposer "
            "must approve"
        ),
        approved_prefix="Scope expansion approved by",
        admin_prefix="Scope expansion admin self-approved by",
        allow_admin_self_approval=allow_admin_self_approval,
    )


def check_scope(repo: str, number: int) -> Decision:
    """Validate the scope-expansion gate for one work Issue."""
    snapshot = load_issue_snapshot(repo, number)
    return scope_decision(snapshot)


def _issue_approval_records(
    snapshot: dict[str, Any],
    proposer: str | None,
    *,
    item_updated_at: str | None = None,
) -> tuple[set[str], dict[str, str], set[str], dict[str, str], set[str]]:
    """Collect standalone/hotfix Issue approvals, objections, self-approvals.

    Uses `_ISSUE_VOCABULARY`: the plain, case-insensitive `Approve` /
    `Admin-approve: <reason>` / `Object: <reason>` / `Resolve: <target>`
    grammar the maintainer decided on 2026-09-18 (Issue #743's own
    comments) -- deliberately independent of `_approval_records()`'s
    tracker vocabulary, per that decision, though both now share the same
    underlying algorithm via `_vocabulary_approval_records()`.
    """
    return _vocabulary_approval_records(
        _ISSUE_VOCABULARY, snapshot, proposer, item_updated_at=item_updated_at
    )


def standalone_issue_approval_decision(
    snapshot: dict[str, Any],
    issue_number: int,
    *,
    require_open: bool = True,
    allow_admin_self_approval: bool | None = None,
) -> Decision:
    """Require independent approval for one Issue with no Milestone (#743).

    Covers standalone, hotfix, and release-recovery Issues alike -- the
    common trait this function gates on is simply having no Milestone of
    its own. A Milestone-scoped Issue keeps inheriting its tracker's approval
    unchanged (see `check_issue_approval()`, which routes there before ever
    calling this function): this function only runs for the other half of
    the maintainer's two-point approval model -- an Issue with no Milestone
    needs its own approval, because nothing else ever gates it.

    Uses the plain, case-insensitive `Approve` / `Admin-approve: <reason>` /
    `Object: <reason>` / `Resolve: <target>` vocabulary the maintainer
    decided on 2026-09-18 (Issue #743's own comments) -- a deliberate,
    independent counterpart to the tracker's and scope-expansion gate's
    `/milestone approve` family, not a reuse of it: a slash command reads
    oddly on an Issue that has no Milestone to invoke it against, and a
    plain keyword needs no prior familiarity with the tracker's own syntax.
    The two vocabularies are data (`_ISSUE_VOCABULARY` here vs.
    `_TRACKER_VOCABULARY`), not separate algorithms: `_issue_approval_
    records()` and `_approval_records()` are both thin wrappers around the
    shared `_vocabulary_approval_records()`, so neither can accidentally
    match the other's comments (each is only ever compared against its own
    vocabulary's `normalize()`), and there is exactly one implementation of
    the underlying algorithm to keep correct. This is what "no second
    parallel system" means here: one shared decision engine and one shared
    comment-matching algorithm, parameterized by two independent
    vocabularies.

    `require_open` mirrors `approval_decision()`'s own gate exactly: an
    Issue closed out from under an already-posted `Approve` comment (mis-
    triaged, marked duplicate, closed by an unrelated PR, etc.) must not
    keep counting as approved. Without this check, a since-closed Issue's
    stale-but-syntactically-valid approval would still satisfy the gate the
    next time `check-pr` or `check-merge-group` re-evaluates it -- a
    fail-open hole the tracker path has never had, since `approval_decision()`
    has required `item.get("state") == "open"` since #400. There is no
    standalone equivalent of the tracker's completed-closure path (which is
    the only caller that ever passes `require_open=False`), so every real
    caller keeps the default.
    """
    issue = snapshot.get("issue")
    if not isinstance(issue, dict):
        return Decision(False, "GitHub returned invalid Issue data")
    if require_open and issue.get("state") != "open":
        return Decision(
            False, f"Issue #{issue_number} must remain open while work runs"
        )
    proposer = issue.get("user", {}).get("login")
    approvals, objections, resolved, admin_approvals, stale = (
        _issue_approval_records(
            snapshot, proposer, item_updated_at=issue.get("updated_at")
        )
    )
    if allow_admin_self_approval is None and admin_approvals and not approvals:
        allow_admin_self_approval = _admin_self_approval_allowed(
            _SnapshotGitHub(snapshot), str(snapshot.get("repo") or ""), issue
        )
    if allow_admin_self_approval is None:
        allow_admin_self_approval = False
    return _gate_decision(
        approvals,
        objections,
        resolved,
        admin_approvals,
        stale,
        missing_message=(
            f"Issue #{issue_number} has no Milestone: a person other than "
            "the proposer must comment `Approve` on it, or an admin "
            "collaborator who is also the proposer may comment "
            "`Admin-approve: <reason>`, before this pull request can merge"
        ),
        approved_prefix="Issue approved by",
        admin_prefix="Issue admin self-approved by",
        allow_admin_self_approval=allow_admin_self_approval,
    )


def check_issue_approval(
    repo: str, number: int, *, require_open: bool = True
) -> Decision:
    """Validate the standalone/hotfix/release-recovery Issue-approval gate.

    A Milestone-scoped Issue defers to that Milestone's own tracker
    approval (`approval_decision()`) -- unaffected by this Issue, exactly
    as before #743. This is normally unreachable through `_pull_decision()`
    itself (a pull request with a Milestone never reaches this function;
    `.csarc/scripts/validate-pr-policy` also requires a pull request's own
    Milestone to match its closing Issue's Milestone), but `check-issue-
    approval` is also a standalone CLI entry point, so it re-derives the
    right answer directly from the Issue's own Milestone field rather than
    trusting a caller's assumption.

    `require_open` is threaded straight through to
    `standalone_issue_approval_decision()`; every real caller (the CLI, and
    `_standalone_pull_decision()`) keeps the default `True`.
    """
    snapshot = load_issue_snapshot(repo, number)
    issue = snapshot.get("issue")
    if not isinstance(issue, dict):
        return Decision(False, "GitHub returned invalid Issue data")
    milestone = issue.get("milestone")
    if isinstance(milestone, dict) and isinstance(milestone.get("number"), int):
        return approval_decision(load_snapshot(repo, milestone["number"]))
    return standalone_issue_approval_decision(
        snapshot,
        number,
        require_open=require_open,
    )


def refresh_issue_pr_checks(repo: str, issue_number: int) -> Decision:
    """Refresh the Milestone-approval check for one standalone Issue (#743).

    The no-Milestone counterpart to `refresh_pr_checks()`'s tracker-wide
    refresh: wired into `work-item-lifecycle.yml` so a fresh `Approve` /
    `Admin-approve:` / `Object:` / `Resolve:` comment on the Issue actually
    re-triggers "Validate Milestone approval" on its linked pull request,
    instead of leaving a stale check-run in place until some unrelated PR
    event happens to re-run it. Without this, the standalone/hotfix path
    would fail *closed* (correct, never silently open) but *stuck* --
    breaking the parity the tracker path already has via `reconcile()`'s
    own `refresh_pr_checks()` call.

    Scans every open pull request repo-wide for one whose body's closing
    keyword(s) include this Issue number. Deliberately does not itself
    decide "exactly one closing Issue" here -- `_standalone_pull_
    decision()` already owns that fail-closed check when the refreshed
    `check-pr` actually runs, so a PR referencing this Issue among several
    still gets refreshed and correctly reported as blocked, rather than
    silently skipped by a duplicate check here. Always returns an allowed
    Decision: this is a best-effort refresh, not a gate in its own right.
    """
    pulls = _pages(
        run_gh(
            [
                "api",
                "--paginate",
                "--slurp",
                f"repos/{repo}/pulls?state=open&per_page=100",
            ]
        )
    )
    count = 0
    for pull in pulls:
        if pull.get("milestone") is not None:
            continue
        body = pull.get("body")
        if not isinstance(body, str):
            continue
        issue_numbers = {
            int(match.group(1)) for match in _CLOSING_KEYWORD.finditer(body)
        }
        if issue_number not in issue_numbers:
            continue
        number = pull.get("number")
        if not isinstance(number, int):
            continue
        check_pr(repo, number)
        count += 1
    return Decision(
        True,
        f"Refreshed the Milestone-approval check on {count} pull "
        f"request(s) closing #{issue_number}",
    )


def _set_milestone_state(repo: str, number: int, state: str) -> None:
    """Set one Milestone state."""
    run_gh(
        [
            "api",
            "--method",
            "PATCH",
            f"repos/{repo}/milestones/{number}",
            "--raw-field",
            f"state={state}",
        ]
    )


def _set_issue_state(repo: str, number: int, state: str) -> None:
    """Set one Issue state."""
    run_gh(
        [
            "api",
            "--method",
            "PATCH",
            f"repos/{repo}/issues/{number}",
            "--raw-field",
            f"state={state}",
        ]
    )


def _record_check(repo: str, head_sha: str, decision: Decision) -> None:
    """Publish the latest approval decision on one pull-request head."""
    status = "queued" if decision.pending else "completed"
    arguments = [
        "api",
        "--method",
        "POST",
        f"repos/{repo}/check-runs",
        "--raw-field",
        f"name={CHECK_NAME}",
        "--raw-field",
        f"head_sha={head_sha}",
        "--raw-field",
        f"status={status}",
        "--raw-field",
        f"output[title]={CHECK_NAME}",
        "--raw-field",
        f"output[summary]={decision.summary}",
    ]
    if not decision.pending:
        conclusion = "success" if decision.allowed else "failure"
        arguments.extend(["--raw-field", f"conclusion={conclusion}"])
    run_gh(arguments)


def refresh_pr_checks(snapshot: dict[str, Any]) -> int:
    """Refresh the approval check for every open PR in this Milestone."""
    decision = approval_decision(snapshot)
    count = 0
    repo = snapshot["repo"]
    for issue in snapshot["issues"]:
        if issue.get("state") != "open" or "pull_request" not in issue:
            continue
        pull = json.loads(
            run_gh(["api", f"repos/{repo}/pulls/{issue['number']}"])
        )
        head_sha = pull.get("head", {}).get("sha")
        if not isinstance(head_sha, str) or not head_sha:
            raise RuntimeError("GitHub returned an invalid pull-request head")
        _record_check(repo, head_sha, decision)
        count += 1
    return count


def check_pr(repo: str, number: int, *, record_check: bool = True) -> Decision:
    """Validate lifecycle approval and optionally record its check."""
    pull = json.loads(run_gh(["api", f"repos/{repo}/pulls/{number}"]))
    head_sha = pull.get("head", {}).get("sha")
    if not isinstance(head_sha, str) or not head_sha:
        raise RuntimeError("GitHub returned an invalid pull-request head")
    decision = _pull_decision(repo, pull)
    if record_check:
        _record_check(repo, head_sha, decision)
    return decision


def _standalone_pull_decision(repo: str, pull: dict[str, Any]) -> Decision:
    """Read the approval decision for a pull request with no Milestone."""
    head_ref = pull.get("head", {}).get("ref")
    if isinstance(head_ref, str) and head_ref.startswith(
        _AUTOMATED_PULL_REQUEST_HEAD_PREFIXES
    ):
        return Decision(True, "This pull request is not part of a Milestone")
    body = pull.get("body")
    if not isinstance(body, str):
        return Decision(True, "This pull request is not part of a Milestone")
    issue_numbers = {
        int(match.group(1)) for match in _CLOSING_KEYWORD.finditer(body)
    }
    if not issue_numbers:
        return Decision(True, "This pull request is not part of a Milestone")
    if len(issue_numbers) > 1:
        numbers = ", ".join(f"#{number}" for number in sorted(issue_numbers))
        return Decision(
            False,
            "This pull request closes more than one Issue "
            f"({numbers}); the standalone Issue-approval gate requires "
            "exactly one closing Issue reference",
        )
    return check_issue_approval(repo, next(iter(issue_numbers)))


def _pull_decision(repo: str, pull: dict[str, Any]) -> Decision:
    """Read the lifecycle decision for one pull-request payload."""
    milestone = pull.get("milestone")
    if milestone is None:
        return _standalone_pull_decision(repo, pull)
    milestone_number = milestone.get("number")
    if not isinstance(milestone_number, int):
        raise RuntimeError(
            "GitHub returned invalid pull-request lifecycle data"
        )
    return approval_decision(load_snapshot(repo, milestone_number))


def check_merge_group(
    repo: str, head_sha: str, *, record_check: bool = True
) -> Decision:
    """Recheck every pull request represented by one merge-group commit."""
    pulls = _pages(run_gh(["api", f"repos/{repo}/commits/{head_sha}/pulls"]))
    if not pulls:
        decision = Decision(
            False, "No pull request belongs to this merge group"
        )
    else:
        decisions = [_pull_decision(repo, pull) for pull in pulls]
        blocked = [
            decision.summary for decision in decisions if not decision.allowed
        ]
        decision = Decision(
            not blocked,
            "; ".join(blocked)
            if blocked
            else "Every queued Milestone is approved",
            pending=bool(blocked)
            and all(item.pending for item in decisions if not item.allowed),
        )
    if record_check:
        _record_check(repo, head_sha, decision)
    return decision


def _unchanged_lifecycle(
    snapshot: dict[str, Any],
    item: dict[str, Any] | None,
    errors: list[str],
    event_issue: int | None,
    event_action: str | None,
) -> Decision | None:
    """Return a no-op decision when an event cannot change the lifecycle."""
    closed = snapshot["milestone"].get("state") == "closed"
    work_event = event_issue not in {None, 0} and (
        item is None or item.get("number") != event_issue
    )
    if work_event and (
        (closed and event_action not in _CLOSED_MILESTONE_ACTIONS)
        or (
            event_action not in {"milestoned", "demilestoned"}
            and not errors
            and item is not None
        )
    ):
        return Decision(
            True,
            f"Work Issue #{event_issue} does not change Milestone lifecycle",
        )
    open_work = any(
        issue.get("state") == "open"
        and "pull_request" not in issue
        and (item is None or issue.get("number") != item.get("number"))
        for issue in snapshot["issues"]
    )
    if (
        not closed
        or not errors
        or open_work
        or (item is not None and item.get("state") != "closed")
    ):
        return None
    # A finished Milestone that only fails rules adopted after it closed
    # keeps its closure; report the gaps instead of reopening history.
    summary = "; ".join(errors)
    notice = summary.replace("%", "%25").replace("\n", "%0A")
    print(f"::notice title=Closed Milestone governance gaps::{notice}")  # noqa: T201
    return Decision(True, f"Closed Milestone keeps its closure: {summary}")


def reconcile(
    repo: str,
    number: int,
    *,
    event_issue: int | None = None,
    event_action: str | None = None,
) -> Decision:
    """Synchronize one relevant Milestone event and refresh its PR checks."""
    snapshot = load_snapshot(repo, number)
    milestone = snapshot["milestone"]
    item = tracker(snapshot)
    errors = tracker_errors(snapshot)
    skipped = _unchanged_lifecycle(
        snapshot, item, errors, event_issue, event_action
    )
    if skipped is not None:
        return skipped
    if item is None:
        if milestone.get("state") == "closed":
            _set_milestone_state(repo, number, "open")
        decision = Decision(False, "; ".join(errors))
        refresh_pr_checks(snapshot)
        return decision
    if item.get("state") == "open":
        if milestone.get("state") == "closed":
            _set_milestone_state(repo, number, "open")
        decision = approval_decision(snapshot)
        refresh_pr_checks(snapshot)
        if not decision.allowed and not errors:
            notice = (
                decision.summary.replace("%", "%25")
                .replace("\r", "%0D")
                .replace("\n", "%0A")
            )
            print(  # noqa: T201
                f"::notice title=Milestone governance status::{notice}"
            )
            return Decision(
                True, f"Milestone governance status: {decision.summary}"
            )
        return decision
    decision = closure_decision(snapshot)
    if decision.allowed:
        if milestone.get("state") == "open":
            _set_milestone_state(repo, number, "closed")
    else:
        _set_issue_state(repo, item["number"], "open")
        if milestone.get("state") == "closed":
            _set_milestone_state(repo, number, "open")
    refresh_pr_checks(snapshot)
    return decision
