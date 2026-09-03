#!/usr/bin/env python3
"""Validate one Milestone lifecycle Issue and synchronize GitHub state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

CHECK_NAME = "Milestone approval"
TRACKER_SECTIONS = (
    "Proposal",
    "Completion evidence",
    "Early termination",
    "Promotion",
)
# A work Issue self-declares scope expansion with this literal body line.
# Its own presence (not its wording) is the whole signal -- see
# `has_scope_sentinel()`.
SCOPE_SENTINEL = "Tracker scope: expanded"
# The tracker's auto-regenerated closure-verification section. Deliberately
# not part of TRACKER_SECTIONS: it cannot exist before the first
# `regenerate-reconciliation` run, so requiring it at tracker-creation time
# would make a tracker permanently uncreatable.
RECONCILIATION_HEADING = "Reconciliation"
_FINGERPRINT_COMMENT = re.compile(
    r"<!--\s*reconciliation-fingerprint:\s*([0-9a-f]+)\s*-->"
)
_CLOSING_KEYWORD = re.compile(
    r"(?<!\w)(?:Closes|Fixes|Resolves)[ \t]+#(\d+)(?!\w)", re.IGNORECASE
)


@dataclass(frozen=True)
class Decision:
    """One fail-closed lifecycle decision."""

    allowed: bool
    summary: str


def run_gh(arguments: list[str]) -> str:
    """Run GitHub CLI without a shell."""
    executable = shutil.which("gh")
    if executable is None:
        raise RuntimeError("GitHub CLI (gh) is required")
    result = subprocess.run(  # noqa: S603
        [executable, *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _pages(raw: str) -> list[dict[str, Any]]:
    """Flatten a paginated GitHub REST response."""
    value = json.loads(raw)
    if not isinstance(value, list):
        raise RuntimeError("GitHub returned an invalid collection")
    if value and isinstance(value[0], list):
        value = [item for page in value for item in page]
    if not all(isinstance(item, dict) for item in value):
        raise RuntimeError("GitHub returned an invalid collection item")
    return value


def _section(body: str, heading: str) -> str | None:
    """Return one canonical H2 section body."""
    match = re.search(
        rf"(?ms)^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", body
    )
    return None if match is None else match.group(1).strip()


def _meaningful(text: str | None) -> bool:
    """Reject an absent, empty, or comment-only section."""
    if text is None:
        return False
    without_comments = re.sub(r"(?s)<!--.*?-->", "", text)
    return bool(without_comments.strip())


def _replace_section(body: str, heading: str, content: str) -> str:
    """Replace one H2 section's content, or append it if not present."""
    pattern = re.compile(
        rf"(?ms)^(## {re.escape(heading)}\s*$\n)(.*?)(?=^## |\Z)"
    )
    block = f"## {heading}\n\n{content.strip()}\n\n"
    match = pattern.search(body)
    if match is not None:
        return body[: match.start()] + block + body[match.end() :]
    return body.rstrip("\n") + "\n\n" + block


def _remove_section(body: str, heading: str) -> str:
    """Return body with one whole H2 section (heading included) removed."""
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\s*$\n.*?(?=^## |\Z)")
    return pattern.sub("", body, count=1).rstrip("\n") + "\n"


def _fingerprint(text: str) -> str:
    """Return one short, stable content fingerprint."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


_GITHUB_TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"
# GitHub's own Issue `updated_at` can trail the `created_at` of the very
# comment that caused it by a second or two while the platform finishes
# recording that comment -- confirmed empirically against this repository's
# own Issue history (a comment's `created_at` one second before its parent
# Issue's `updated_at`). This grace window absorbs that recording lag
# without weakening real staleness detection: a genuine follow-up edit or
# comment happens seconds-to-hours later in practice, never within a few
# seconds of the approval it would invalidate.
_STALE_GRACE_SECONDS = 60


def _parse_github_timestamp(value: object) -> float | None:
    """Parse one GitHub REST UTC timestamp into comparable epoch seconds."""
    if not isinstance(value, str):
        return None
    try:
        return (
            datetime.strptime(value, _GITHUB_TIMESTAMP)
            .replace(tzinfo=UTC)
            .timestamp()
        )
    except ValueError:
        return None


def _approval_is_stale(
    item_updated_at: object, comment_created_at: object
) -> bool:
    """Return whether one approval no longer binds to the current body.

    This is the fingerprint-binding gate #632 adds on top of #552's
    approval mechanism. Reconciliation's own staleness check
    (`reconciliation_status()`) can compare a stored content hash exactly,
    because the bot writes that hash itself right after computing it. An
    approval comment is written by a human, not the bot, and GitHub does
    not expose Issue body-edit history over REST at all (unlike a Git
    diff, there is no per-revision body to hash retroactively) -- so
    `updated_at` is the only queryable edit signal available, and it also
    advances on Issue activity that never touched the body: a new comment,
    a label, Milestone, or state change. This trades a higher
    "needs re-approval" false-positive rate for never silently accepting
    an approval that could be reading a version of the body that no longer
    exists -- the conservative direction for a governance gate.

    Missing data on either side reads as "cannot tell", not "definitely
    stale": a caller that never supplies `item_updated_at` keeps today's
    behavior unchanged.
    """
    updated = _parse_github_timestamp(item_updated_at)
    created = _parse_github_timestamp(comment_created_at)
    if updated is None or created is None:
        return False
    return updated - created > _STALE_GRACE_SECONDS


def acceptance_complete(description: str) -> bool:
    """Return whether every checkbox in the acceptance section is checked."""
    section = _section(description, "Acceptance criteria")
    if section is None:
        return False
    checkboxes = re.findall(r"(?m)^- \[([ xX])\] ", section)
    return bool(checkboxes) and all(mark.lower() == "x" for mark in checkboxes)


def has_scope_sentinel(body: str) -> bool:
    """Return whether one work Issue has self-declared a scope expansion.

    Detection is deliberately dumb: an exact, literal body line, matched
    regardless of surrounding content. No natural-language judgment about
    whether work actually exceeds the tracker's Proposal is attempted --
    that judgment is exactly what the independent approval this triggers
    is for.
    """
    return re.search(rf"(?m)^{re.escape(SCOPE_SENTINEL)}\s*$", body) is not None


def promotion_complete(body: str) -> bool:
    """Return whether every checkbox in the tracker Promotion section is set."""
    section = _section(body, "Promotion")
    if section is None:
        return False
    checkboxes = re.findall(r"(?m)^- \[([ xX])\] ", section)
    return bool(checkboxes) and all(mark.lower() == "x" for mark in checkboxes)


def promotion_decision(body: str) -> Decision:
    """Validate that a tracker's Promotion section is ready to close."""
    if _section(body, "Promotion") is None:
        return Decision(False, "The lifecycle Issue needs a Promotion section")
    if not promotion_complete(body):
        return Decision(
            False, "Complete every Promotion readiness checkbox first"
        )
    return Decision(True, "Promotion checklist complete")


def append_completion_evidence(body: str, evidence_url: str) -> str:
    """Append one delivery evidence URL into the Completion evidence section.

    Preserves any content already present in the section (stripping only the
    placeholder HTML comment) instead of overwriting it, so a promotion
    bridge merge never clobbers evidence recorded by an earlier checkpoint.
    """
    match = re.search(
        r"(?ms)^(## Completion evidence\s*$\n)(.*?)(?=^## |\Z)", body
    )
    if match is None:
        raise RuntimeError(
            "The lifecycle Issue body is missing a Completion evidence section"
        )
    heading = match.group(1)
    kept = re.sub(r"(?s)<!--.*?-->", "", match.group(2)).strip()
    if evidence_url in kept:
        return body
    lines = [line for line in kept.splitlines() if line.strip()]
    lines.append(evidence_url)
    new_section = heading + "\n".join(lines) + "\n\n"
    return body[: match.start()] + new_section + body[match.end() :]


def load_snapshot(repo: str, number: int) -> dict[str, Any]:
    """Read one current Milestone, its items, tracker, and tracker comments."""
    milestone = json.loads(run_gh(["api", f"repos/{repo}/milestones/{number}"]))
    issues = _pages(
        run_gh(
            [
                "api",
                "--paginate",
                "--slurp",
                f"repos/{repo}/issues?milestone={number}&state=all&per_page=100",
            ]
        )
    )
    expected_title = f"Milestone {number}: {milestone.get('title', '')}"
    trackers = [
        issue
        for issue in issues
        if issue.get("title") == expected_title and "pull_request" not in issue
    ]
    comments: list[dict[str, Any]] = []
    if len(trackers) == 1:
        comments = _pages(
            run_gh(
                [
                    "api",
                    "--paginate",
                    "--slurp",
                    f"repos/{repo}/issues/{trackers[0]['number']}/comments?per_page=100",
                ]
            )
        )
    return {
        "repo": repo,
        "milestone": milestone,
        "issues": issues,
        "comments": comments,
    }


def tracker(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Return the unique exact-title lifecycle Issue, if present."""
    milestone = snapshot["milestone"]
    expected = f"Milestone {milestone['number']}: {milestone['title']}"
    matches = [
        issue
        for issue in snapshot["issues"]
        if issue.get("title") == expected and "pull_request" not in issue
    ]
    return matches[0] if len(matches) == 1 else None


def _milestone_errors(milestone: dict[str, Any]) -> list[str]:
    """Validate Milestone fields that are independent of the tracker."""
    if not milestone.get("due_on"):
        return ["The Milestone must have a real due date"]
    return []


def tracker_errors(snapshot: dict[str, Any]) -> list[str]:
    """Validate the lifecycle Issue identity and stable body contract."""
    milestone = snapshot.get("milestone")
    if not isinstance(milestone, dict):
        return ["GitHub returned invalid Milestone data"]
    number = milestone.get("number")
    title = milestone.get("title")
    description = milestone.get("description")
    if not isinstance(number, int) or not isinstance(title, str):
        return ["GitHub returned invalid Milestone identity"]
    errors = _milestone_errors(milestone)
    item = tracker(snapshot)
    if item is None:
        errors.append(
            f"Create exactly one Issue titled: Milestone {number}: {title}"
        )
        return errors
    labels = {
        label.get("name")
        for label in item.get("labels", [])
        if isinstance(label, dict)
    }
    if "enhancement" not in labels:
        errors.append("The lifecycle Issue must use the enhancement label")
    body = item.get("body")
    if not isinstance(body, str):
        errors.append("The lifecycle Issue body is missing")
    else:
        if not _meaningful(_section(body, "Proposal")):
            errors.append(
                "The lifecycle Issue needs a non-empty Proposal section"
            )
        for heading in TRACKER_SECTIONS[1:]:
            if _section(body, heading) is None:
                errors.append(f"The lifecycle Issue needs a {heading} section")
    if (
        not isinstance(description, str)
        or re.search(
            rf"(?mi)^Lifecycle Issue:\s*#{item['number']}\s*$", description
        )
        is None
    ):
        errors.append(
            f"The Milestone description must contain `Lifecycle Issue: "
            f"#{item['number']}`"
        )
    return errors


def _collaborator_permission(repo: str, username: str) -> str | None:
    """Return one collaborator's permission level for this repo, if known.

    Unlike a comment's `author_association`, this is not affected by
    whether the commenter's organization membership is public or private,
    so it stays reliable under the workflow's own `GITHUB_TOKEN`.
    """
    try:
        payload = json.loads(
            run_gh(["api", f"repos/{repo}/collaborators/{username}/permission"])
        )
    except subprocess.CalledProcessError:
        return None
    permission = payload.get("permission")
    return permission if isinstance(permission, str) else None


def _admin_self_approval(
    command: str,
    author: str,
    author_type: str | None,
    permission: str | None,
    proposer: str | None,
) -> str | None:
    """Return the reason for one valid admin self-approval, if any."""
    if not command.startswith("/milestone admin-approve:"):
        return None
    reason = command.removeprefix("/milestone admin-approve:").strip()
    if not reason or author != proposer or author_type == "Bot":
        return None
    return reason if permission == "admin" else None


def _record_objection(
    command: str, author: str, url: object, objections: dict[str, str]
) -> None:
    """Record one objection comment, keyed by its own permalink."""
    if not command.startswith("/milestone object:") or not isinstance(url, str):
        return
    if command.removeprefix("/milestone object:").strip():
        objections[url] = author


def _record_resolution(
    command: str, author: str, objections: dict[str, str], resolved: set[str]
) -> None:
    """Record one objection withdrawal by its original author."""
    if not command.startswith("/milestone resolve:"):
        return
    target = command.removeprefix("/milestone resolve:").strip()
    if objections.get(target) == author:
        resolved.add(target)


def _approval_records(
    snapshot: dict[str, Any],
    proposer: str | None,
    *,
    item_updated_at: str | None = None,
) -> tuple[set[str], dict[str, str], set[str], dict[str, str], set[str]]:
    """Collect approvals, objections, withdrawals, and admin self-approvals.

    Also returns the authors whose approve/admin-approve comment no longer
    binds (#632). `item_updated_at` is the tracker's (or work Issue's) own
    `updated_at` field, read from the same snapshot as
    `snapshot["comments"]`. When supplied, an approve/admin-approve
    comment made stale by a later edit
    (see `_approval_is_stale()`) is excluded from `approvals`/
    `admin_approvals` and its author reported in the returned `stale` set
    instead, so callers can distinguish "never approved" from "was
    approved, then invalidated" in their own Decision message.
    """
    approvals: set[str] = set()
    objections: dict[str, str] = {}
    resolved: set[str] = set()
    admin_approvals: dict[str, str] = {}
    stale: set[str] = set()
    repo = snapshot.get("repo")
    for comment in snapshot.get("comments", []):
        body = comment.get("body")
        author = comment.get("user", {}).get("login")
        author_type = comment.get("user", {}).get("type")
        url = comment.get("html_url")
        if not isinstance(body, str) or not isinstance(author, str):
            continue
        command = next(
            (line.strip() for line in body.splitlines() if line.strip()), ""
        )
        is_stale = _approval_is_stale(
            item_updated_at, comment.get("created_at")
        )
        if command == "/milestone approve":
            if author != proposer and author_type != "Bot":
                if is_stale:
                    stale.add(author)
                else:
                    approvals.add(author)
            continue
        # Only query collaborator permission for a plausible admin-approve
        # comment from the proposer -- avoids one API call per comment.
        permission = (
            _collaborator_permission(repo, author)
            if isinstance(repo, str)
            and author == proposer
            and command.startswith("/milestone admin-approve:")
            else None
        )
        reason = _admin_self_approval(
            command, author, author_type, permission, proposer
        )
        if reason is not None:
            if is_stale:
                stale.add(author)
            else:
                admin_approvals[author] = reason
            continue
        _record_objection(command, author, url, objections)
        _record_resolution(command, author, objections, resolved)
    return approvals, objections, resolved, admin_approvals, stale


def _gate_decision(
    approvals: set[str],
    objections: dict[str, str],
    resolved: set[str],
    admin_approvals: dict[str, str],
    stale: set[str],
    *,
    missing_message: str,
    approved_prefix: str = "Approved by",
    admin_prefix: str = "Admin self-approved by",
) -> Decision:
    """Turn one collected approval-record set into a pass/fail Decision.

    Shared by the tracker's own `/milestone approve` gate and a work
    Issue's scope-expansion gate: both read the identical comment
    vocabulary (`/milestone approve`, `/milestone admin-approve:`,
    `/milestone object:`, `/milestone resolve:`) via `_approval_records()`,
    and only differ in wording. `stale` (#632) names authors whose
    approve/admin-approve comment was invalidated by a later edit -- when
    it is the only reason no approval currently counts, the message says
    so explicitly instead of reading identically to "never approved".
    """
    if not approvals and not admin_approvals:
        if stale:
            return Decision(
                False,
                f"{missing_message} (a later edit invalidated the approval "
                f"from {', '.join(sorted(stale))} -- re-approve)",
            )
        return Decision(False, missing_message)
    unresolved = sorted(set(objections) - resolved)
    if unresolved:
        return Decision(
            False,
            f"Resolve {len(unresolved)} objection(s) before work continues",
        )
    if approvals:
        return Decision(
            True, f"{approved_prefix} {', '.join(sorted(approvals))}"
        )
    admins = ", ".join(
        f"{author} (reason: {reason})"
        for author, reason in sorted(admin_approvals.items())
    )
    return Decision(True, f"{admin_prefix} {admins}")


def approval_decision(
    snapshot: dict[str, Any], *, require_open: bool = True
) -> Decision:
    """Require one non-proposer approval, or an owner self-approval.

    Also requires no unresolved objection. An approval is bound to the
    tracker body as of its own comment's timestamp: editing the body
    afterward invalidates it (#632; see `_approval_is_stale()`).
    """
    errors = tracker_errors(snapshot)
    item = tracker(snapshot)
    if errors or item is None:
        return Decision(False, "; ".join(errors))
    if require_open and item.get("state") != "open":
        return Decision(
            False, "The lifecycle Issue must remain open while work runs"
        )
    proposer = item.get("user", {}).get("login")
    approvals, objections, resolved, admin_approvals, stale = _approval_records(
        snapshot, proposer, item_updated_at=item.get("updated_at")
    )
    return _gate_decision(
        approvals,
        objections,
        resolved,
        admin_approvals,
        stale,
        missing_message="A person other than the proposer must approve",
    )


def load_issue_snapshot(repo: str, number: int) -> dict[str, Any]:
    """Read one work Issue and its own comments for scope-gate evaluation."""
    issue = json.loads(run_gh(["api", f"repos/{repo}/issues/{number}"]))
    comments = _pages(
        run_gh(
            [
                "api",
                "--paginate",
                "--slurp",
                f"repos/{repo}/issues/{number}/comments?per_page=100",
            ]
        )
    )
    return {"repo": repo, "issue": issue, "comments": comments}


def scope_decision(snapshot: dict[str, Any]) -> Decision:
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
    )


def check_scope(repo: str, number: int) -> Decision:
    """Validate the scope-expansion gate for one work Issue."""
    return scope_decision(load_issue_snapshot(repo, number))


def _linked_work_items(
    snapshot: dict[str, Any], tracker_number: int
) -> list[dict[str, Any]]:
    """Return every non-tracker Issue (not a pull request) in this Milestone."""
    return [
        issue
        for issue in snapshot["issues"]
        if issue.get("number") != tracker_number and "pull_request" not in issue
    ]


def _merged_at(pull_issue: dict[str, Any]) -> str | None:
    """Return one pull request's merge timestamp, if it has merged."""
    pull_request = pull_issue.get("pull_request")
    if not isinstance(pull_request, dict):
        return None
    merged_at = pull_request.get("merged_at")
    return merged_at if isinstance(merged_at, str) else None


def _closing_pull_requests(
    snapshot: dict[str, Any],
) -> dict[int, list[dict[str, Any]]]:
    """Map each Issue number to the pull requests that declare closing it."""
    mapping: dict[int, list[dict[str, Any]]] = {}
    for issue in snapshot["issues"]:
        if "pull_request" not in issue:
            continue
        body = issue.get("body")
        if not isinstance(body, str):
            continue
        for match in _CLOSING_KEYWORD.finditer(body):
            mapping.setdefault(int(match.group(1)), []).append(issue)
    return mapping


def _delivery_row(
    issue: dict[str, Any], pulls: list[dict[str, Any]]
) -> tuple[str, str]:
    """Return one reconciliation table row and its delivery status."""
    number = issue.get("number")
    title = str(issue.get("title", "")).replace("|", "\\|")
    state = issue.get("state", "unknown")
    merged_pulls = [pull for pull in pulls if _merged_at(pull)]
    chosen = merged_pulls[0] if merged_pulls else (pulls[0] if pulls else None)
    pr_cell = f"#{chosen['number']}" if chosen else "(none found)"
    merged = chosen is not None and _merged_at(chosen) is not None
    if state == "closed" and merged:
        status = "Delivered"
    elif state == "closed":
        status = "Closed without a merged PR"
    else:
        status = "Pending"
    row = (
        f"| #{number} {title} | {state} | {pr_cell} | "
        f"{'yes' if merged else 'no'} | {status} |"
    )
    return row, status


def reconciliation_status(body: str) -> Decision:
    """Return whether the tracker's Reconciliation section is fresh.

    Fresh means: the section exists, carries its own fingerprint comment,
    and that fingerprint still matches the rest of the tracker body today.
    `regenerate_reconciliation()` only ever rewrites the Reconciliation
    section itself, so this fingerprint changes only when a human or agent
    edits some other part of the tracker body after the last regeneration
    -- exactly the edit this check exists to catch, so a stale table can
    never be relied on to justify closing the Milestone.
    """
    section = _section(body, RECONCILIATION_HEADING)
    if not isinstance(section, str) or not _meaningful(section):
        return Decision(False, "Reconciliation section is missing")
    match = _FINGERPRINT_COMMENT.search(section)
    if match is None:
        return Decision(False, "Reconciliation section has no fingerprint")
    rest = _remove_section(body, RECONCILIATION_HEADING)
    if match.group(1) != _fingerprint(rest):
        return Decision(
            False, "Reconciliation: stale, regenerate before closing"
        )
    return Decision(True, "Reconciliation is fresh")


def regenerate_reconciliation(snapshot: dict[str, Any]) -> str:
    """Return the tracker body with a freshly rebuilt Reconciliation section.

    Walks every Issue actually attached to this Milestone (the same set
    `closure_decision()` already treats as authoritative) against its real
    GitHub state: closed or not, and whether a pull request that declares
    closing it has actually merged. This is a genuine per-line delivery
    table for a human to sign off against the Milestone's own Acceptance
    criteria, not a second checkbox scan.
    """
    item = tracker(snapshot)
    if item is None:
        raise RuntimeError("No unique lifecycle Issue found to reconcile")
    body = item.get("body")
    if not isinstance(body, str):
        raise RuntimeError("The lifecycle Issue body is missing")
    base = _remove_section(body, RECONCILIATION_HEADING)
    fingerprint = _fingerprint(base)
    items = sorted(
        _linked_work_items(snapshot, item["number"]),
        key=lambda issue: issue.get("number", 0),
    )
    closing = _closing_pull_requests(snapshot)
    lines = [
        f"<!-- reconciliation-fingerprint: {fingerprint} -->",
        (
            "Auto-regenerated from live Milestone state. Re-run "
            "`regenerate-reconciliation` after editing this Issue and "
            "before closing it as completed -- editing any other section "
            "marks this one stale."
        ),
        "",
        "| Work Issue | State | Delivering PR | Merged | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    delivered = 0
    for issue in items:
        row, status = _delivery_row(issue, closing.get(issue.get("number"), []))
        lines.append(row)
        if status == "Delivered":
            delivered += 1
    if not items:
        lines.append("| _(no linked work Issues found)_ | | | | |")
    lines.append("")
    lines.append(f"_{len(items)} linked work Issue(s); {delivered} delivered._")
    return _replace_section(base, RECONCILIATION_HEADING, "\n".join(lines))


def record_reconciliation(repo: str, milestone_number: int) -> Decision:
    """Regenerate and persist the tracker's Reconciliation section."""
    snapshot = load_snapshot(repo, milestone_number)
    item = tracker(snapshot)
    if item is None:
        return Decision(False, "; ".join(tracker_errors(snapshot)))
    try:
        new_body = regenerate_reconciliation(snapshot)
    except RuntimeError as error:
        return Decision(False, str(error))
    if new_body != item.get("body"):
        run_gh(
            [
                "issue",
                "edit",
                str(item["number"]),
                "--repo",
                repo,
                "--body",
                new_body,
            ]
        )
    return Decision(True, f"Recorded reconciliation on #{item['number']}")


def _completed_closure(snapshot: dict[str, Any], body: str) -> Decision:
    """Validate the completed-closure evidence chain for one tracker."""
    description = snapshot["milestone"].get("description", "")
    if not acceptance_complete(description):
        return Decision(False, "Complete every Milestone acceptance criterion")
    if not promotion_complete(body):
        return Decision(False, "Complete every Promotion readiness checkbox")
    approval = approval_decision(snapshot, require_open=False)
    if not approval.allowed:
        return approval
    evidence = _section(body, "Completion evidence")
    if (
        not isinstance(evidence, str)
        or not _meaningful(evidence)
        or "https://github.com/" not in evidence
    ):
        return Decision(
            False, "Completed closure needs a GitHub delivery evidence URL"
        )
    reconciliation = reconciliation_status(body)
    if not reconciliation.allowed:
        return reconciliation
    return Decision(True, "Completed with approval and delivery evidence")


def closure_decision(snapshot: dict[str, Any]) -> Decision:
    """Validate completed and not-planned lifecycle closure paths."""
    errors = tracker_errors(snapshot)
    item = tracker(snapshot)
    if errors or item is None:
        return Decision(False, "; ".join(errors))
    if item.get("state") != "closed":
        return Decision(False, "The lifecycle Issue is still open")
    open_items = [
        issue
        for issue in snapshot["issues"]
        if issue.get("number") != item.get("number")
        and issue.get("state") == "open"
    ]
    if open_items:
        numbers = ", ".join(f"#{issue['number']}" for issue in open_items)
        return Decision(
            False, f"Move or close unfinished items first: {numbers}"
        )
    body = item.get("body", "")
    reason = item.get("state_reason")
    if reason == "completed":
        return _completed_closure(snapshot, body)
    if reason == "not_planned":
        if not _meaningful(_section(body, "Early termination")):
            return Decision(False, "Not-planned closure needs an explanation")
        return Decision(True, "Stopped early with all unfinished work disposed")
    return Decision(False, "Use the completed or not planned close reason")


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
    conclusion = "success" if decision.allowed else "failure"
    run_gh(
        [
            "api",
            "--method",
            "POST",
            f"repos/{repo}/check-runs",
            "--raw-field",
            f"name={CHECK_NAME}",
            "--raw-field",
            f"head_sha={head_sha}",
            "--raw-field",
            "status=completed",
            "--raw-field",
            f"conclusion={conclusion}",
            "--raw-field",
            f"output[title]={CHECK_NAME}",
            "--raw-field",
            f"output[summary]={decision.summary}",
        ]
    )


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


def check_pr(repo: str, number: int) -> Decision:
    """Validate and record lifecycle approval for one current pull request."""
    pull = json.loads(run_gh(["api", f"repos/{repo}/pulls/{number}"]))
    head_sha = pull.get("head", {}).get("sha")
    if not isinstance(head_sha, str) or not head_sha:
        raise RuntimeError("GitHub returned an invalid pull-request head")
    decision = _pull_decision(repo, pull)
    _record_check(repo, head_sha, decision)
    return decision


def _pull_decision(repo: str, pull: dict[str, Any]) -> Decision:
    """Read the lifecycle decision for one pull-request payload."""
    milestone = pull.get("milestone")
    if milestone is None:
        return Decision(True, "This pull request is not part of a Milestone")
    milestone_number = milestone.get("number")
    if not isinstance(milestone_number, int):
        raise RuntimeError(
            "GitHub returned invalid pull-request lifecycle data"
        )
    return approval_decision(load_snapshot(repo, milestone_number))


def check_merge_group(repo: str, head_sha: str) -> Decision:
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
        )
    _record_check(repo, head_sha, decision)
    return decision


def record_promotion_evidence(
    repo: str, tracker_number: int, evidence_url: str
) -> Decision:
    """Append one promotion merge evidence URL onto a tracker Issue."""
    issue = json.loads(run_gh(["api", f"repos/{repo}/issues/{tracker_number}"]))
    body = issue.get("body")
    if not isinstance(body, str):
        return Decision(False, "The lifecycle Issue body is missing")
    try:
        new_body = append_completion_evidence(body, evidence_url)
    except RuntimeError as error:
        return Decision(False, str(error))
    if new_body == body:
        return Decision(
            True, f"Promotion evidence already recorded on #{tracker_number}"
        )
    run_gh(
        [
            "issue",
            "edit",
            str(tracker_number),
            "--repo",
            repo,
            "--body",
            new_body,
        ]
    )
    return Decision(True, f"Recorded promotion evidence on #{tracker_number}")


def reconcile(repo: str, number: int) -> Decision:
    """Synchronize one Milestone and refresh its open PR checks."""
    snapshot = load_snapshot(repo, number)
    milestone = snapshot["milestone"]
    item = tracker(snapshot)
    if item is None:
        if milestone.get("state") == "closed":
            _set_milestone_state(repo, number, "open")
        decision = Decision(False, "; ".join(tracker_errors(snapshot)))
        refresh_pr_checks(snapshot)
        return decision
    if item.get("state") == "open":
        if milestone.get("state") == "closed":
            _set_milestone_state(repo, number, "open")
        decision = approval_decision(snapshot)
        refresh_pr_checks(snapshot)
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


def main() -> None:
    """Run the PR gate or synchronize one event-selected Milestone."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check-pr")
    check.add_argument("--repo", required=True)
    check.add_argument("--pr", required=True, type=int)
    queue = subparsers.add_parser("check-merge-group")
    queue.add_argument("--repo", required=True)
    queue.add_argument("--head-sha", required=True)
    subparsers.add_parser("check-promotion")
    record = subparsers.add_parser("record-promotion-evidence")
    record.add_argument("--repo", required=True)
    record.add_argument("--tracker", required=True, type=int)
    record.add_argument("--evidence-url", required=True)
    scope = subparsers.add_parser("check-scope")
    scope.add_argument("--repo", required=True)
    scope.add_argument("--issue", required=True, type=int)
    reconciliation = subparsers.add_parser("regenerate-reconciliation")
    reconciliation.add_argument("--repo", required=True)
    reconciliation.add_argument("--milestone", required=True, type=int)
    sync = subparsers.add_parser("reconcile")
    sync.add_argument("--repo", required=True)
    sync.add_argument("--milestone", required=True, type=int)
    args = parser.parse_args()
    if args.command == "check-pr":
        decision = check_pr(args.repo, args.pr)
    elif args.command == "check-merge-group":
        decision = check_merge_group(args.repo, args.head_sha)
    elif args.command == "check-promotion":
        decision = promotion_decision(sys.stdin.read())
    elif args.command == "record-promotion-evidence":
        decision = record_promotion_evidence(
            args.repo, args.tracker, args.evidence_url
        )
    elif args.command == "check-scope":
        decision = check_scope(args.repo, args.issue)
    elif args.command == "regenerate-reconciliation":
        decision = record_reconciliation(args.repo, args.milestone)
    else:
        decision = reconcile(args.repo, args.milestone)
    print(decision.summary)  # noqa: T201
    if not decision.allowed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
