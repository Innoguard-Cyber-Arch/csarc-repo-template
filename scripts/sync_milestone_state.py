#!/usr/bin/env python3
"""Validate one Milestone lifecycle Issue and synchronize GitHub state."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    stale_branch_detection = importlib.import_module("stale_branch_detection")
    release_level = importlib.import_module("release_level")
else:
    stale_branch_detection = importlib.import_module(
        f"{__package__}.stale_branch_detection"
    )
    release_level = importlib.import_module(f"{__package__}.release_level")

CHECK_NAME = "Milestone approval"
TRACKER_SECTIONS = (
    "Proposal",
    "Completion evidence",
    "Early termination",
    "Promotion",
)
WORK_KIND_LABELS = {"bug", "documentation", "enhancement"}
# A work Issue self-declares scope expansion with this literal body line.
# Its own presence (not its wording) is the whole signal -- see
# `has_scope_sentinel()`.
SCOPE_SENTINEL = "Tracker scope: expanded"
# The tracker's auto-regenerated closure-verification section. Deliberately
# not part of TRACKER_SECTIONS: it cannot exist before the first
# `regenerate-reconciliation` run, so requiring it at tracker-creation time
# would make a tracker permanently uncreatable.
RECONCILIATION_HEADING = "Reconciliation"
# A work Issue closed as not planned was cancelled or superseded, not
# delivered; it is shown as such and does not block a completed closure.
NOT_PLANNED_STATUS = "Not planned"
# Strict per-Issue delivery evidence took effect with #816 (merge commit
# 057b83e35a). Work Issues closed before then are historical records: they
# are labelled as such instead of being judged retroactively (#1012).
STRICT_DELIVERY_CUTOFF = "2026-09-19T19:06:52Z"
HISTORICAL_STATUS = "Closed before #816"
SETTLED_STATUSES = {"Delivered", NOT_PLANNED_STATUS, HISTORICAL_STATUS}
# Work Issue actions that can change a closed Milestone's delivery facts.
# Every other work Issue event (labels, edits, comments) leaves it alone.
_CLOSED_MILESTONE_ACTIONS = {"milestoned", "demilestoned", "reopened"}
_FINGERPRINT_COMMENT = re.compile(
    r"<!--\s*reconciliation-fingerprint:\s*([0-9a-f]+)\s*-->"
)
_CLOSING_KEYWORD = re.compile(
    r"(?<!\w)(?:Closes|Fixes|Resolves)[ \t]+#(\d+)(?!\w)", re.IGNORECASE
)
_TRACKING_KEYWORD = re.compile(r"(?<!\w)Refs[ \t]+#(\d+)(?!\w)", re.IGNORECASE)
_PROMOTION_BRANCH = re.compile(r"^promote/m([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class Decision:
    """One fail-closed lifecycle decision."""

    allowed: bool
    summary: str
    pending: bool = False


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


class _SnapshotGitHub:
    """Expose an already-loaded Milestone snapshot to the level resolver."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot

    def get(self, repo: str, path: str) -> object:
        """Read snapshot data or delegate collaborator permission lookup."""
        if path.startswith("collaborators/") and path.endswith("/permission"):
            login = urllib.parse.unquote(path.split("/", 2)[1])
            permission = _collaborator_permission(repo, login)
            if permission is None:
                raise RuntimeError("collaborator permission is unavailable")
            return {"permission": permission}
        if path.startswith("milestones/"):
            number = int(path.split("/", 1)[1])
            milestone = self.snapshot.get("milestone")
            if (
                isinstance(milestone, dict)
                and milestone.get("number") == number
            ):
                return milestone
            return load_snapshot(repo, number)["milestone"]
        if path.startswith("issues/"):
            number = int(path.split("/", 1)[1])
            issue = self.snapshot.get("issue")
            if isinstance(issue, dict) and issue.get("number") == number:
                return issue
            for issue in self.snapshot.get("issues", []):
                if issue.get("number") == number:
                    return issue
        raise RuntimeError(f"snapshot has no {path}")

    def pages(self, repo: str, path: str) -> list[dict[str, Any]]:
        """Return the snapshot's Milestone Issue collection."""
        if path.startswith("issues?milestone="):
            issues = self.snapshot.get("issues")
            if isinstance(issues, list):
                return list(issues)
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
            milestone_number = int(query["milestone"][0])
            return list(load_snapshot(repo, milestone_number)["issues"])
        raise RuntimeError(f"snapshot has no {path}")


def _admin_self_approval_allowed(
    github: release_level.GitHubReader,
    repo: str,
    issue: dict[str, Any],
) -> bool:
    """Return whether this work's configured review policy permits self-use."""
    labels = {
        str(label.get("name") or "").casefold()
        for label in issue.get("labels", [])
        if isinstance(label, dict)
    }
    if issue.get("milestone") is None and "hotfix" in labels:
        return True
    decision = release_level.resolve_issue(
        github, repo, issue, release_level.load_settings()
    )
    return decision.review == "self"


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
    item_updated_at: object,
    comment_created_at: object,
    comment_updated_at: object = None,
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

    `comment_updated_at` closes a gap in the item-vs-`created_at` check
    above (#778): GitHub does not expose a comment's own body-edit history
    any more than it does an Issue's, so a comment last edited long after
    it was first posted could have had the approval vocabulary this script
    currently reads back written in at any point up to that edit --
    including well after whatever it originally said. `created_at` alone
    cannot see that: an old, unrelated comment edited into
    `/milestone approve` today still carries its original, untouched
    `created_at`, so if the item itself has not been touched since around
    then, the item-vs-`created_at` gap alone looks small and the edit goes
    undetected. This is therefore a second, independent staleness check --
    the comment's own edit gap -- OR'd with the first: an approval is
    stale if either the item was updated long after the comment was
    created, OR the comment was itself edited long after it was created.
    Only the first check uses `item_updated_at`, so a comment edited
    *after* a later item update does not get to look fresh purely because
    the edit is recent -- the first check already caught that case from
    the item side and this addition never overrides it back to fresh.
    A comment that was never edited reports `comment_updated_at` equal to
    `comment_created_at` (or omits it), so the second check is always
    false there and behavior for that -- the common -- case is unchanged.
    """
    updated = _parse_github_timestamp(item_updated_at)
    created = _parse_github_timestamp(comment_created_at)
    item_side_stale = (
        updated is not None
        and created is not None
        and updated - created > _STALE_GRACE_SECONDS
    )
    edited = _parse_github_timestamp(comment_updated_at)
    edit_gap_stale = (
        edited is not None
        and created is not None
        and edited - created > _STALE_GRACE_SECONDS
    )
    return item_side_stale or edit_gap_stale


def acceptance_complete(description: str) -> bool:
    """Return whether every checkbox in the acceptance section is checked."""
    section = _section(description, "Acceptance criteria")
    if section is None:
        return False
    return checklist_complete(section)


def checklist_complete(body: str) -> bool:
    """Return whether a body contains checkboxes and all are checked."""
    checkboxes = re.findall(r"(?m)^- \[([ xX])\] ", body)
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


def _parent_membership_errors(
    issues: list[dict[str, Any]], milestone_number: int
) -> list[str]:
    """Require native Feature parents to share their sub-issue Milestone."""
    members = {
        issue.get("number")
        for issue in issues
        if "pull_request" not in issue and isinstance(issue.get("number"), int)
    }
    missing: dict[int, list[int]] = {}
    for issue in issues:
        if "pull_request" in issue or issue.get("parent_issue_url") is None:
            continue
        parent_url = issue.get("parent_issue_url")
        match = (
            re.search(r"/issues/([1-9][0-9]*)$", parent_url)
            if isinstance(parent_url, str)
            else None
        )
        if match is None:
            return ["GitHub returned invalid parent Issue data"]
        parent = int(match.group(1))
        child = issue.get("number")
        if parent not in members and isinstance(child, int):
            missing.setdefault(parent, []).append(child)
    return [
        f"Feature parent #{parent} must share Milestone {milestone_number} "
        f"with sub-issue(s) {', '.join(f'#{child}' for child in children)}"
        for parent, children in sorted(missing.items())
    ]


def _tracker_classification_errors(item: dict[str, Any]) -> list[str]:
    """Validate native Feature type or the portable label fallback."""
    labels = {
        str(label.get("name") or "").casefold()
        for label in item.get("labels", [])
        if isinstance(label, dict)
    }
    issue_type = item.get("type")
    if issue_type is None:
        if "enhancement" in labels:
            return []
        return [
            "The lifecycle Issue must use the enhancement label when "
            "native Issue Types are unavailable"
        ]
    if not isinstance(issue_type, dict) or not isinstance(
        issue_type.get("name"), str
    ):
        return ["GitHub returned invalid lifecycle Issue type data"]

    errors = []
    if issue_type["name"] != "Feature":
        errors.append("The lifecycle Issue must use the Feature type")
    if labels & WORK_KIND_LABELS:
        errors.append(
            "The lifecycle Issue must not repeat its native Type with a "
            "work-kind label"
        )
    return errors


def _checkpoint_errors(
    body: str, issues: list[dict[str, Any]], milestone_number: int
) -> list[str]:
    """Validate optional beta checkpoints declared in the tracker Proposal."""
    try:
        roles = release_level.declared_checkpoints(body)
    except ValueError as error:
        return [str(error)]
    if roles is None:
        return []
    members = {
        item.get("number")
        for item in issues
        if item.get("pull_request") is None
        and (item.get("milestone") or {}).get("number") == milestone_number
    }
    return [
        f"Checkpoint Issue #{number} is not a work Issue in this Milestone"
        for number in sorted(roles)
        if number not in members
    ]


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
    errors.extend(_parent_membership_errors(snapshot["issues"], number))
    item = tracker(snapshot)
    if item is None:
        errors.append(
            f"Create exactly one Issue titled: Milestone {number}: {title}"
        )
        return errors
    errors.extend(_tracker_classification_errors(item))
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
        errors.extend(_checkpoint_errors(body, snapshot["issues"], number))
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


@dataclass(frozen=True)
class _ApprovalVocabulary:
    """One comment grammar an approval gate reads (#743's shared algorithm).

    `approve`/`admin_prefix`/`object_prefix`/`resolve_prefix` must already
    be cased correctly for `case_sensitive`: lowercase throughout for a
    case-insensitive vocabulary (matched against `command.lower()`), or
    the exact literal case for the tracker's case-sensitive `/milestone`
    family (matched against `command` unchanged). Two vocabularies never
    cross-match each other's comments, because each is only ever compared
    against its own `normalize()` rule -- this is what lets the tracker's
    `/milestone approve` family and the standalone/hotfix Issue's plain
    `Approve` family (#743) share one decision algorithm without merging
    into one comparison.
    """

    approve: str
    admin_prefix: str
    object_prefix: str
    resolve_prefix: str
    case_sensitive: bool

    def normalize(self, command: str) -> str:
        """Return `command` as this vocabulary compares it."""
        return command if self.case_sensitive else command.lower()


_TRACKER_VOCABULARY = _ApprovalVocabulary(
    approve="/milestone approve",
    admin_prefix="/milestone admin-approve:",
    object_prefix="/milestone object:",
    resolve_prefix="/milestone resolve:",
    case_sensitive=True,
)

# The standalone/hotfix/release-recovery Issue-approval vocabulary the
# maintainer decided on 2026-09-18 (Issue #743's own comments): plain,
# case-insensitive text, deliberately independent of the tracker's slash
# commands above -- see `standalone_issue_approval_decision()`.
_ISSUE_VOCABULARY = _ApprovalVocabulary(
    approve="approve",
    admin_prefix="admin-approve:",
    object_prefix="object:",
    resolve_prefix="resolve:",
    case_sensitive=False,
)


def _vocabulary_admin_self_approval(
    vocabulary: _ApprovalVocabulary,
    command: str,
    author: str,
    author_type: str | None,
    permission: str | None,
    proposer: str | None,
) -> str | None:
    """Return the reason for one valid admin self-approval, if any."""
    if not vocabulary.normalize(command).startswith(vocabulary.admin_prefix):
        return None
    reason = command[len(vocabulary.admin_prefix) :].strip()
    if not reason or author != proposer or author_type == "Bot":
        return None
    return reason if permission == "admin" else None


def _vocabulary_record_objection(
    vocabulary: _ApprovalVocabulary,
    normalized: str,
    command: str,
    author: str,
    url: object,
    objections: dict[str, str],
) -> None:
    """Record one objection comment, keyed by its own permalink."""
    if not normalized.startswith(vocabulary.object_prefix) or not isinstance(
        url, str
    ):
        return
    if command[len(vocabulary.object_prefix) :].strip():
        objections[url] = author


def _vocabulary_record_resolution(
    vocabulary: _ApprovalVocabulary,
    normalized: str,
    command: str,
    author: str,
    objections: dict[str, str],
    resolved: set[str],
) -> None:
    """Record one objection withdrawal by its original author."""
    if not normalized.startswith(vocabulary.resolve_prefix):
        return
    target = command[len(vocabulary.resolve_prefix) :].strip()
    if objections.get(target) == author:
        resolved.add(target)


def _vocabulary_approval_records(
    vocabulary: _ApprovalVocabulary,
    snapshot: dict[str, Any],
    proposer: str | None,
    *,
    item_updated_at: str | None = None,
) -> tuple[set[str], dict[str, str], set[str], dict[str, str], set[str]]:
    """Collect approvals, objections, withdrawals, and admin self-approvals.

    Shared algorithm behind both `_approval_records()` (tracker) and
    `_issue_approval_records()` (#743's standalone/hotfix Issue gate),
    parameterized by `vocabulary`.

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
        normalized = vocabulary.normalize(command)
        is_stale = _approval_is_stale(
            item_updated_at,
            comment.get("created_at"),
            comment.get("updated_at"),
        )
        if normalized == vocabulary.approve:
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
            and normalized.startswith(vocabulary.admin_prefix)
            else None
        )
        reason = _vocabulary_admin_self_approval(
            vocabulary, command, author, author_type, permission, proposer
        )
        if reason is not None:
            if is_stale:
                stale.add(author)
            else:
                admin_approvals[author] = reason
            continue
        _vocabulary_record_objection(
            vocabulary, normalized, command, author, url, objections
        )
        _vocabulary_record_resolution(
            vocabulary, normalized, command, author, objections, resolved
        )
    return approvals, objections, resolved, admin_approvals, stale


def _admin_self_approval(
    command: str,
    author: str,
    author_type: str | None,
    permission: str | None,
    proposer: str | None,
) -> str | None:
    """Return the reason for one valid tracker admin self-approval, if any."""
    return _vocabulary_admin_self_approval(
        _TRACKER_VOCABULARY, command, author, author_type, permission, proposer
    )


def _record_objection(
    command: str, author: str, url: object, objections: dict[str, str]
) -> None:
    """Record one tracker objection comment, keyed by its own permalink."""
    _vocabulary_record_objection(
        _TRACKER_VOCABULARY, command, command, author, url, objections
    )


def _record_resolution(
    command: str, author: str, objections: dict[str, str], resolved: set[str]
) -> None:
    """Record one tracker objection withdrawal by its original author."""
    _vocabulary_record_resolution(
        _TRACKER_VOCABULARY, command, command, author, objections, resolved
    )


def _approval_records(
    snapshot: dict[str, Any],
    proposer: str | None,
    *,
    item_updated_at: str | None = None,
) -> tuple[set[str], dict[str, str], set[str], dict[str, str], set[str]]:
    """Collect tracker approvals, objections, and admin self-approvals.

    See `_vocabulary_approval_records()` for the shared algorithm.
    """
    return _vocabulary_approval_records(
        _TRACKER_VOCABULARY,
        snapshot,
        proposer,
        item_updated_at=item_updated_at,
    )


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
    allow_admin_self_approval: bool = True,
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
    if not approvals and admin_approvals and not allow_admin_self_approval:
        return Decision(
            False,
            "This release level requires approval from another person; "
            "admin self-approval is only valid when self-review is configured",
            pending=True,
        )
    if not approvals and not admin_approvals:
        if stale:
            return Decision(
                False,
                f"{missing_message} (a later edit invalidated the approval "
                f"from {', '.join(sorted(stale))} -- re-approve)",
                pending=True,
            )
        return Decision(False, missing_message, pending=True)
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
    snapshot: dict[str, Any],
    *,
    require_open: bool = True,
    allow_admin_self_approval: bool | None = None,
    bind_to_item_update: bool = True,
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
    item_updated_at = item.get("updated_at") if bind_to_item_update else None
    approvals, objections, resolved, admin_approvals, stale = _approval_records(
        snapshot, proposer, item_updated_at=item_updated_at
    )
    if allow_admin_self_approval is None and admin_approvals and not approvals:
        allow_admin_self_approval = _admin_self_approval_allowed(
            _SnapshotGitHub(snapshot), str(snapshot.get("repo") or ""), item
        )
    if allow_admin_self_approval is None:
        allow_admin_self_approval = False
    return _gate_decision(
        approvals,
        objections,
        resolved,
        admin_approvals,
        stale,
        missing_message="A person other than the proposer must approve",
        allow_admin_self_approval=allow_admin_self_approval,
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


@dataclass(frozen=True)
class ApprovalEditInvalidation:
    """One currently valid approval that a body edit would invalidate."""

    author: str
    url: str
    reapproval_command: str


def _body_edit_vocabulary(
    issue: dict[str, Any],
) -> _ApprovalVocabulary | None:
    """Return the approval vocabulary bound to this Issue's own body."""
    milestone = issue.get("milestone")
    if milestone is None:
        return _ISSUE_VOCABULARY
    if not isinstance(milestone, dict):
        return None
    expected_tracker_title = (
        f"Milestone {milestone.get('number')}: {milestone.get('title')}"
    )
    if issue.get("title") == expected_tracker_title:
        return _TRACKER_VOCABULARY
    body = issue.get("body")
    if isinstance(body, str) and has_scope_sentinel(body):
        return _TRACKER_VOCABULARY
    return None


def approval_invalidations_for_body_edit(
    snapshot: dict[str, Any], proposed_updated_at: str
) -> list[ApprovalEditInvalidation]:
    """Predict approvals the proposed body edit would make stale (#799).

    Both the current and proposed states use `_approval_is_stale()`; this
    is an early warning around the existing gate, not another approval
    decision mechanism.
    """
    issue = snapshot.get("issue")
    if not isinstance(issue, dict):
        return []
    vocabulary = _body_edit_vocabulary(issue)
    if vocabulary is None:
        return []
    proposer = issue.get("user", {}).get("login")
    records = _vocabulary_approval_records(
        vocabulary,
        snapshot,
        proposer,
        item_updated_at=issue.get("updated_at"),
    )
    approvals, _, _, admin_approvals, _ = records
    if not approvals and not admin_approvals:
        return []

    invalidations: list[ApprovalEditInvalidation] = []
    fresh_after_edit = False
    for comment in snapshot.get("comments", []):
        body = comment.get("body")
        author = comment.get("user", {}).get("login")
        if not isinstance(body, str) or not isinstance(author, str):
            continue
        command = next(
            (line.strip() for line in body.splitlines() if line.strip()), ""
        )
        normalized = vocabulary.normalize(command)
        if normalized == vocabulary.approve and author in approvals:
            reapproval = (
                "/milestone approve"
                if vocabulary is _TRACKER_VOCABULARY
                else "Approve"
            )
        elif (
            normalized.startswith(vocabulary.admin_prefix)
            and command[len(vocabulary.admin_prefix) :].strip()
            and author in admin_approvals
        ):
            reapproval = (
                "/milestone admin-approve: <reason>"
                if vocabulary is _TRACKER_VOCABULARY
                else "Admin-approve: <reason>"
            )
        else:
            continue
        if _approval_is_stale(
            issue.get("updated_at"),
            comment.get("created_at"),
            comment.get("updated_at"),
        ):
            continue
        if not _approval_is_stale(
            proposed_updated_at,
            comment.get("created_at"),
            comment.get("updated_at"),
        ):
            fresh_after_edit = True
            continue
        url = comment.get("html_url")
        invalidations.append(
            ApprovalEditInvalidation(
                author=author,
                url=url if isinstance(url, str) else "(URL unavailable)",
                reapproval_command=reapproval,
            )
        )
    return [] if fresh_after_edit else invalidations


def body_edit_warning(
    snapshot: dict[str, Any], proposed_updated_at: str
) -> str | None:
    """Format a non-blocking warning for one approval-invalidating edit."""
    invalidations = approval_invalidations_for_body_edit(
        snapshot, proposed_updated_at
    )
    if not invalidations:
        return None
    issue = snapshot["issue"]
    lines = [
        f"WARNING: editing Issue #{issue.get('number')}'s body now will "
        "invalidate these approval comments:"
    ]
    lines.extend(f"- @{item.author}: {item.url}" for item in invalidations)
    lines.append("After the edit, re-approval is required:")
    lines.extend(
        f"- @{item.author} should comment `{item.reapproval_command}` again."
        for item in invalidations
    )
    return "\n".join(lines)


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
    `scripts/validate-pr-policy` also requires a pull request's own
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
    issue: dict[str, Any],
    pulls: list[dict[str, Any]],
    status: str,
    children: list[int],
) -> tuple[str, str]:
    """Return one reconciliation table row and its delivery status."""
    number = issue.get("number")
    title = str(issue.get("title", "")).replace("|", "\\|")
    state = issue.get("state", "unknown")
    merged_pulls = [pull for pull in pulls if _merged_at(pull)]
    chosen = merged_pulls[0] if merged_pulls else (pulls[0] if pulls else None)
    pr_cell = f"#{chosen['number']}" if chosen else "(none found)"
    merged = chosen is not None and _merged_at(chosen) is not None
    if children and not pulls:
        pr_cell = "sub-issues " + ", ".join(f"#{child}" for child in children)
    row = (
        f"| #{number} {title} | {state} | {pr_cell} | "
        f"{'yes' if merged else 'no'} | {status} |"
    )
    return row, status


def _parent_number(issue: dict[str, Any]) -> int | None:
    match = re.search(
        r"/issues/([0-9]+)$", str(issue.get("parent_issue_url") or "")
    )
    return int(match.group(1)) if match else None


def _parent_status(issue: dict[str, Any], sub_statuses: list[str]) -> str:
    """Return a Feature parent's status from its sub-issues and checklist."""
    if issue.get("state") != "closed":
        return "Pending"
    if issue.get("state_reason") == "not_planned":
        return NOT_PLANNED_STATUS
    if any(status not in SETTLED_STATUSES for status in sub_statuses):
        return "Sub-issues not settled"
    if not checklist_complete(str(issue.get("body") or "")):
        return "Acceptance incomplete or missing"
    return "Delivered"


def _delivery_statuses(
    snapshot: dict[str, Any], tracker_number: int
) -> tuple[dict[int, str], dict[int, list[int]]]:
    """Return every linked Issue's delivery status and its sub-issues.

    A Feature parent never has its own delivering pull request (#962 keeps
    it in the Milestone; a promotion may not close it). It is delivered once
    every sub-issue in this Milestone is settled and its own acceptance
    checklist is complete (#1026). Leaf work keeps the strict per-Issue
    closing pull request evidence required since #816.
    """
    items = {
        int(issue["number"]): issue
        for issue in _linked_work_items(snapshot, tracker_number)
        if type(issue.get("number")) is int
    }
    children: dict[int, list[int]] = {}
    for number, issue in items.items():
        parent = _parent_number(issue)
        if parent in items:
            children.setdefault(parent, []).append(number)
    closing = _closing_pull_requests(snapshot)
    statuses: dict[int, str] = {}

    def status_of(number: int, seen: frozenset[int]) -> str:
        if number in statuses:
            return statuses[number]
        issue = items[number]
        pulls = closing.get(number, [])
        kids = sorted(children.get(number, []))
        if not kids or pulls or number in seen:
            result = _delivery_status(issue, pulls)
        else:
            result = _parent_status(
                issue, [status_of(kid, seen | {number}) for kid in kids]
            )
        statuses[number] = result
        return result

    for number in items:
        status_of(number, frozenset())
    return statuses, {parent: sorted(kids) for parent, kids in children.items()}


def _delivery_status(issue: dict[str, Any], pulls: list[dict[str, Any]]) -> str:
    """Return the shared delivery decision for one Milestone work Issue."""
    if issue.get("state") != "closed":
        return "Pending"
    if issue.get("state_reason") == "not_planned":
        return NOT_PLANNED_STATUS
    body = issue.get("body")
    if not any(_merged_at(pull) for pull in pulls):
        status = "Closed without a merged PR"
    elif not isinstance(body, str) or not checklist_complete(body):
        status = "Acceptance incomplete or missing"
    else:
        return "Delivered"
    closed_at = issue.get("closed_at")
    if isinstance(closed_at, str) and closed_at < STRICT_DELIVERY_CUTOFF:
        return HISTORICAL_STATUS
    return status


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
    GitHub state: closed or not, whether a pull request that declares closing
    it has actually merged, and whether its checklist is complete. This is a
    genuine per-line delivery table for a human to sign off against the
    Milestone's own Acceptance criteria, not a second evidence database.
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
    statuses, children = _delivery_statuses(snapshot, item["number"])
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
        number = int(issue["number"])
        row, status = _delivery_row(
            issue,
            closing.get(number, []),
            statuses[number],
            children.get(number, []),
        )
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


def _completed_closure(
    snapshot: dict[str, Any], tracker_number: int, body: str
) -> Decision:
    """Validate the completed-closure evidence chain for one tracker."""
    statuses, _ = _delivery_statuses(snapshot, tracker_number)
    undelivered = []
    for issue in _linked_work_items(snapshot, tracker_number):
        status = statuses.get(int(issue["number"]), "Pending")
        if status not in SETTLED_STATUSES:
            undelivered.append(f"#{issue['number']} ({status})")
    if undelivered:
        return Decision(
            False, f"Non-delivered work Issues: {', '.join(undelivered)}"
        )
    description = snapshot["milestone"].get("description", "")
    if not acceptance_complete(description):
        return Decision(False, "Complete every Milestone acceptance criterion")
    if not promotion_complete(body):
        return Decision(False, "Complete every Promotion readiness checkbox")
    # Closing the Issue and writing machine-owned evidence both advance its
    # `updated_at`. The release completer already revalidated the approval
    # before either write, while the reconciliation fingerprint binds the
    # current body here. Keep detecting edits to the approval comment itself.
    approval = approval_decision(
        snapshot, require_open=False, bind_to_item_update=False
    )
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
    body = item.get("body", "")
    reason = item.get("state_reason")
    if reason == "completed":
        return _completed_closure(snapshot, item["number"], body)
    if reason == "not_planned":
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


_AUTOMATED_PULL_REQUEST_HEAD_PREFIXES = (
    "dependabot/",
    "automation/",
    "release-please--",
    "sync/main-to-",
)


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


def complete_release(  # noqa: C901
    repo: str,
    main_sha: str,
    evidence_url: str,
    *,
    outcome: str,
) -> Decision:
    """Close one Milestone only after its promotion release has succeeded."""
    if outcome == "published":
        expected_prefix = f"https://github.com/{repo}/releases/tag/"
    elif outcome == "no-release":
        expected_prefix = f"https://github.com/{repo}/actions/runs/"
    else:
        return Decision(False, f"Unknown release outcome: {outcome}")
    if not evidence_url.startswith(expected_prefix):
        return Decision(False, "Release completion evidence URL is invalid")

    pulls = _pages(
        run_gh(
            [
                "api",
                "--paginate",
                "--slurp",
                f"repos/{repo}/commits/{main_sha}/pulls?per_page=100",
            ]
        )
    )
    promotions = []
    for pull in pulls:
        base = pull.get("base")
        head = pull.get("head")
        head_ref = head.get("ref") if isinstance(head, dict) else None
        if (
            isinstance(base, dict)
            and base.get("ref") == "main"
            and isinstance(head_ref, str)
            and _PROMOTION_BRANCH.fullmatch(head_ref)
            and pull.get("merge_commit_sha") == main_sha
            and isinstance(pull.get("merged_at"), str)
        ):
            promotions.append(pull)
    if not promotions:
        return Decision(True, "This main commit is not a Milestone promotion")
    if len(promotions) != 1:
        return Decision(False, "Main commit has no unique Milestone promotion")

    pull = promotions[0]
    head_ref = str(pull["head"]["ref"])
    branch_match = _PROMOTION_BRANCH.fullmatch(head_ref)
    milestone = pull.get("milestone")
    milestone_number = (
        milestone.get("number") if isinstance(milestone, dict) else None
    )
    if (
        branch_match is None
        or not isinstance(milestone_number, int)
        or milestone_number != int(branch_match.group(1))
    ):
        return Decision(False, "Promotion branch and Milestone differ")
    body = pull.get("body")
    if not isinstance(body, str) or _CLOSING_KEYWORD.search(body):
        return Decision(
            False,
            "Milestone promotion must keep its tracker open until release",
        )
    trackers = {
        int(match.group(1)) for match in _TRACKING_KEYWORD.finditer(body)
    }
    if len(trackers) != 1:
        return Decision(False, "Milestone promotion needs exactly one Refs #N")
    tracker_number = next(iter(trackers))
    snapshot = load_snapshot(repo, milestone_number)
    issue = tracker(snapshot)
    if issue is None or issue.get("number") != tracker_number:
        return Decision(
            False, "Promotion does not reference its Milestone tracker"
        )
    issue_milestone = issue.get("milestone")
    if (
        not str(issue.get("title") or "").startswith(
            f"Milestone {milestone_number}: "
        )
        or not isinstance(issue_milestone, dict)
        or issue_milestone.get("number") != milestone_number
    ):
        return Decision(
            False, "Promotion does not reference its Milestone tracker"
        )

    promotion_url = f"https://github.com/{repo}/commit/{main_sha}"
    issue_body = issue.get("body")
    if not isinstance(issue_body, str):
        return Decision(False, "The lifecycle Issue body is missing")
    approval = approval_decision(snapshot)
    retry_ready = (
        promotion_url in issue_body
        and evidence_url in issue_body
        and reconciliation_status(issue_body).allowed
    )
    if not approval.allowed and retry_ready:
        approval = approval_decision(
            snapshot, require_open=False, bind_to_item_update=False
        )
    if not approval.allowed:
        return approval

    updated_body = issue_body
    try:
        for url in (promotion_url, evidence_url):
            updated_body = append_completion_evidence(updated_body, url)
        issue["body"] = updated_body
        updated_body = regenerate_reconciliation(snapshot)
    except RuntimeError as error:
        return Decision(False, str(error))
    issue["body"] = updated_body
    issue["state"] = "closed"
    issue["state_reason"] = "completed"
    closure = closure_decision(snapshot)
    if not closure.allowed:
        return closure
    if updated_body != issue_body:
        run_gh(
            [
                "issue",
                "edit",
                str(tracker_number),
                "--repo",
                repo,
                "--body",
                updated_body,
            ]
        )
    run_gh(
        [
            "api",
            "--method",
            "PATCH",
            f"repos/{repo}/issues/{tracker_number}",
            "--raw-field",
            "state=closed",
            "--raw-field",
            "state_reason=completed",
        ]
    )
    closed = reconcile(repo, milestone_number)
    if not closed.allowed:
        return closed
    return Decision(
        True,
        f"Completed tracker #{tracker_number} and Milestone {milestone_number}",
    )


def preflight(repo: str, number: int) -> Decision:
    """Validate a Milestone's own metadata before any work is dispatched.

    Runs the exact due-date and tracker contract `tracker_errors()` already
    enforces on every work-Issue pull request through `approval_decision()`,
    but directly against a bare Milestone number -- so a missing due date or
    a mistyped tracker title surfaces immediately after `gh api ... POST
    milestones` / `gh issue create`, instead of waiting for the first PR to
    fail "Validate Milestone approval" (Issue #572, landed on `main` as
    #655; ported here directly rather than waiting for a full `main` sync
    of this Milestone delivery branch, since #667 below depends on this
    exact subcommand existing).

    Also surfaces a repo-wide stale-delivery-branch review list (Issue
    #667: detection only, see `stale_branch_detection`). That check is
    unrelated to this Milestone's own metadata, so a stale-branch finding
    never flips `allowed` to False -- it is appended to the summary purely
    for visibility, on both the pass and fail path.
    """
    snapshot = load_snapshot(repo, number)
    errors = tracker_errors(snapshot)
    hygiene = stale_branch_detection.stale_branch_report(repo)["summary"]
    base = (
        "; ".join(errors) if errors else "Milestone metadata is ready for work"
    )
    return Decision(not errors, f"{base} | {hygiene}")


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


def main() -> None:
    """Run the PR gate or synchronize one event-selected Milestone."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check-pr")
    check.add_argument("--repo", required=True)
    check.add_argument("--pr", required=True, type=int)
    check_mode = check.add_mutually_exclusive_group()
    check_mode.add_argument("--read-only", action="store_true")
    check_mode.add_argument("--publish-only", action="store_true")
    queue = subparsers.add_parser("check-merge-group")
    queue.add_argument("--repo", required=True)
    queue.add_argument("--head-sha", required=True)
    queue_mode = queue.add_mutually_exclusive_group()
    queue_mode.add_argument("--read-only", action="store_true")
    queue_mode.add_argument("--publish-only", action="store_true")
    subparsers.add_parser("check-promotion")
    record = subparsers.add_parser("record-promotion-evidence")
    record.add_argument("--repo", required=True)
    record.add_argument("--tracker", required=True, type=int)
    record.add_argument("--evidence-url", required=True)
    complete = subparsers.add_parser("complete-release")
    complete.add_argument("--repo", required=True)
    complete.add_argument("--main-sha", required=True)
    complete.add_argument("--evidence-url", required=True)
    complete.add_argument(
        "--outcome", choices=("published", "no-release"), required=True
    )
    scope = subparsers.add_parser("check-scope")
    scope.add_argument("--repo", required=True)
    scope.add_argument("--issue", required=True, type=int)
    issue_approval = subparsers.add_parser("check-issue-approval")
    issue_approval.add_argument("--repo", required=True)
    issue_approval.add_argument("--issue", required=True, type=int)
    refresh_issue = subparsers.add_parser("refresh-issue-pr-checks")
    refresh_issue.add_argument("--repo", required=True)
    refresh_issue.add_argument("--issue", required=True, type=int)
    reconciliation = subparsers.add_parser("regenerate-reconciliation")
    reconciliation.add_argument("--repo", required=True)
    reconciliation.add_argument("--milestone", required=True, type=int)
    sync = subparsers.add_parser("reconcile")
    sync.add_argument("--repo", required=True)
    sync.add_argument("--milestone", required=True, type=int)
    sync.add_argument("--event-issue", type=int)
    sync.add_argument("--event-action")
    pre = subparsers.add_parser("preflight")
    pre.add_argument("--repo", required=True)
    pre.add_argument("--milestone", required=True, type=int)
    args = parser.parse_args()
    decision = _dispatch(args)
    print(decision.summary)  # noqa: T201
    if not decision.allowed:
        raise SystemExit(1)


def _dispatch(args: argparse.Namespace) -> Decision:  # noqa: C901
    """Route one parsed subcommand to its handler function."""
    if args.command == "check-pr":
        decision = check_pr(args.repo, args.pr, record_check=not args.read_only)
        return (
            Decision(True, f"Published {CHECK_NAME}: {decision.summary}")
            if args.publish_only
            else decision
        )
    if args.command == "check-merge-group":
        decision = check_merge_group(
            args.repo, args.head_sha, record_check=not args.read_only
        )
        return (
            Decision(True, f"Published {CHECK_NAME}: {decision.summary}")
            if args.publish_only
            else decision
        )
    if args.command == "check-promotion":
        return promotion_decision(sys.stdin.read())
    if args.command == "record-promotion-evidence":
        return record_promotion_evidence(
            args.repo, args.tracker, args.evidence_url
        )
    if args.command == "complete-release":
        return complete_release(
            args.repo,
            args.main_sha,
            args.evidence_url,
            outcome=args.outcome,
        )
    if args.command == "check-scope":
        return check_scope(args.repo, args.issue)
    if args.command == "check-issue-approval":
        return check_issue_approval(args.repo, args.issue)
    if args.command == "refresh-issue-pr-checks":
        return refresh_issue_pr_checks(args.repo, args.issue)
    if args.command == "regenerate-reconciliation":
        return record_reconciliation(args.repo, args.milestone)
    if args.command == "preflight":
        return preflight(args.repo, args.milestone)
    return reconcile(
        args.repo,
        args.milestone,
        event_issue=args.event_issue,
        event_action=args.event_action,
    )


if __name__ == "__main__":
    main()
