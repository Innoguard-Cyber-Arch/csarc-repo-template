#!/usr/bin/env python3
"""Validate one Milestone lifecycle Issue and synchronize GitHub state."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

CHECK_NAME = "Milestone approval"
TRACKER_SECTIONS = (
    "Proposal",
    "Completion evidence",
    "Early termination",
    "Promotion",
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


def acceptance_complete(description: str) -> bool:
    """Return whether every checkbox in the acceptance section is checked."""
    section = _section(description, "Acceptance criteria")
    if section is None:
        return False
    checkboxes = re.findall(r"(?m)^- \[([ xX])\] ", section)
    return bool(checkboxes) and all(mark.lower() == "x" for mark in checkboxes)


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
    snapshot: dict[str, Any], proposer: str | None
) -> tuple[set[str], dict[str, str], set[str], dict[str, str]]:
    """Collect approvals, objections, withdrawals, and admin self-approvals."""
    approvals: set[str] = set()
    objections: dict[str, str] = {}
    resolved: set[str] = set()
    admin_approvals: dict[str, str] = {}
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
        if command == "/milestone approve":
            if author != proposer and author_type != "Bot":
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
            admin_approvals[author] = reason
            continue
        _record_objection(command, author, url, objections)
        _record_resolution(command, author, objections, resolved)
    return approvals, objections, resolved, admin_approvals


def approval_decision(
    snapshot: dict[str, Any], *, require_open: bool = True
) -> Decision:
    """Require one non-proposer approval, or an owner self-approval.

    Also requires no unresolved objection.
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
    approvals, objections, resolved, admin_approvals = _approval_records(
        snapshot, proposer
    )
    if not approvals and not admin_approvals:
        return Decision(False, "A person other than the proposer must approve")
    unresolved = sorted(set(objections) - resolved)
    if unresolved:
        return Decision(
            False,
            f"Resolve {len(unresolved)} objection(s) before work continues",
        )
    if approvals:
        return Decision(True, f"Approved by {', '.join(sorted(approvals))}")
    admins = ", ".join(
        f"{author} (reason: {reason})"
        for author, reason in sorted(admin_approvals.items())
    )
    return Decision(True, f"Admin self-approved by {admins}")


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
    else:
        decision = reconcile(args.repo, args.milestone)
    print(decision.summary)  # noqa: T201
    if not decision.allowed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
