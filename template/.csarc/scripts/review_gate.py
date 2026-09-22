#!/usr/bin/env python3
"""Decide whether a pull request's exact head has earned review.

The configured human fallback is either solo or peer. When explicitly allowed,
a clean Copilot review of the exact head can satisfy either mode; otherwise the
human rule applies. The audited admin-bypass authorization remains limited
to its existing route. The Ruleset keeps native approval count at zero and
makes this ``review`` check required for every pull request.

Copilot never submits ``APPROVED``; a clean review is a ``COMMENTED``
review whose body states that it generated no comments. The gate fails
closed on anything else: a review of an older head, a review still being
prepared, inline comments, findings Copilot moved into the body as
suppressed low-confidence comments, or wording this module does not
recognize. Unresolved review threads are enforced natively by the
Ruleset's ``required_review_thread_resolution``; ``status`` still lists
them so the local agent loop knows what is left to answer.

Commands:

* ``check``: the hosted ``review`` required check; exits non-zero with the
  reason when the head has not earned review.
* ``status``: JSON for the local fix loop -- the Copilot findings on the
  current head and the unresolved threads to answer before merging.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    csarc_config = importlib.import_module("csarc_config")
    release_level = importlib.import_module("release_level")
else:
    csarc_config = importlib.import_module(f"{__package__}.csarc_config")
    release_level = importlib.import_module(f"{__package__}.release_level")

COPILOT_LOGINS = {"copilot-pull-request-reviewer[bot]", "copilot"}
CLEAN_BODY = re.compile(r"(?i)\bgenerated (?:no|0) (?:new )?comments\b")
SUPPRESSED_BODY = re.compile(r"(?i)\bsuppressed\b")
UNLIMITED = "unlimited"

CommentLoader = Callable[[object], list[dict[str, Any]]]


class GitHubReader(Protocol):
    """The read-only subset of ``pr_lifecycle.GitHub`` this gate uses."""

    def get(self, repo: str, path: str) -> object:
        """Read one REST resource."""
        ...

    def pages(self, repo: str, path: str) -> list[dict[str, Any]]:
        """Read every page of one REST collection."""
        ...


@dataclass(frozen=True)
class CopilotReview:
    """Copilot's verdict on one exact head."""

    state: str
    reason: str
    review: dict[str, Any] | None = None
    findings: list[dict[str, Any]] = field(default_factory=list)


def review_settings(path: Path | None = None) -> tuple[str, str]:
    """Return the normalized Copilot mode and compatibility level cap.

    The new schema deliberately has no release-level cap: an explicitly
    allowed clean exact-head Copilot review can satisfy either human mode.
    """
    config_path = path or csarc_config.CONFIG_FILE
    if not config_path.exists():
        return "human", UNLIMITED
    config = csarc_config.load_config(config_path)
    configured = config.get("copilot_review")
    if configured is None:
        configured = (
            "allowed" if config.get("pr_review_mode") == "copilot" else "off"
        )
    mode = "copilot" if configured == "allowed" else "human"
    level = UNLIMITED
    return str(mode), str(level)


def is_copilot(review: dict[str, Any]) -> bool:
    """Return whether GitHub's Copilot code review App wrote this review."""
    user = review.get("user")
    return (
        isinstance(user, dict)
        and user.get("type") == "Bot"
        and str(user.get("login", "")).casefold() in COPILOT_LOGINS
    )


def latest_copilot_review(
    reviews: list[dict[str, Any]], head_sha: str
) -> dict[str, Any] | None:
    """Return Copilot's newest submitted review of the exact head."""
    candidates = [
        review
        for review in reviews
        if is_copilot(review)
        and review.get("commit_id") == head_sha
        and review.get("submitted_at")
        and review.get("state") != "PENDING"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: str(item["submitted_at"]))


def copilot_verdict(
    reviews: list[dict[str, Any]],
    head_sha: str,
    comments_for: CommentLoader,
) -> CopilotReview:
    """Classify Copilot's review of ``head_sha``.

    ``comments_for`` maps a review ID to that review's inline comments; it
    is only called for the one review that decides the verdict.
    """
    review = latest_copilot_review(reviews, head_sha)
    if review is None:
        older = any(is_copilot(item) for item in reviews)
        return CopilotReview(
            "pending",
            (
                "Copilot has not reviewed the current head yet"
                if older
                else "Copilot has not reviewed this pull request yet"
            ),
        )
    comments = comments_for(review["id"])
    findings = [
        {
            "path": comment.get("path"),
            "line": comment.get("line") or comment.get("original_line"),
            "body": comment.get("body"),
            "url": comment.get("html_url"),
        }
        for comment in comments
    ]
    body = str(review.get("body") or "")
    if findings:
        return CopilotReview(
            "changes",
            f"Copilot left {len(findings)} comment(s) on the current head",
            review,
            findings,
        )
    if SUPPRESSED_BODY.search(body):
        return CopilotReview(
            "changes",
            "Copilot reported suppressed low-confidence comments in its "
            "review body",
            review,
            [{"path": None, "line": None, "body": body, "url": None}],
        )
    if not CLEAN_BODY.search(body):
        return CopilotReview(
            "unrecognized",
            "Copilot's review does not state that it generated no comments",
            review,
        )
    return CopilotReview("clean", "Copilot found no issues", review)


def level_allows_copilot(max_level: str, level: str) -> tuple[bool, str]:
    """Return whether the configured cap lets Copilot approve this level."""
    if release_level.level_allows_copilot(max_level, level):
        return True, ""
    return (
        False,
        f"copilot_review_max_level={max_level} does not allow Copilot to "
        f"approve a {level} pull request; a maintainer approval is required",
    )


def _pr_context(
    github: GitHubReader, repo: str, pr_number: int
) -> dict[str, Any]:
    pull = github.get(repo, f"pulls/{pr_number}")
    if not isinstance(pull, dict):
        raise RuntimeError("Pull request is unavailable")
    return pull


def _comments_for(
    github: GitHubReader, repo: str, pr_number: int
) -> CommentLoader:
    def load(review_id: object) -> list[dict[str, Any]]:
        return github.pages(
            repo, f"pulls/{pr_number}/reviews/{review_id}/comments?per_page=100"
        )

    return load


def evaluate(  # noqa: C901
    github: GitHubReader,
    repo: str,
    pr_number: int,
    config: Path | None = None,
) -> dict[str, Any]:
    """Return the review decision for the pull request's current head."""
    lifecycle = importlib.import_module(
        "pr_lifecycle"
        if __package__ in {None, ""}
        else f"{__package__}.pr_lifecycle"
    )
    mode, max_level = review_settings(config)
    pull = _pr_context(github, repo, pr_number)
    level_decision = release_level.resolve_pull(
        github, repo, pull, release_level.load_settings(config)
    )
    head_sha = str((pull.get("head") or {}).get("sha") or "")
    author = str((pull.get("user") or {}).get("login") or "").casefold()
    result: dict[str, Any] = {
        "mode": mode,
        "release_level": level_decision.level,
        "required_review": level_decision.review,
        "head_sha": head_sha,
        "passed": False,
        "source": None,
        "reason": "",
    }
    reviews = github.pages(repo, f"pulls/{pr_number}/reviews?per_page=100")
    approval = lifecycle.exact_head_approval(
        github,
        repo,
        lifecycle.current_reviews(reviews),
        head_sha,
        author,
    )
    if approval is not None:
        result.update(
            passed=True,
            source="maintainer",
            reason="An independent maintainer approved the exact head: "
            + str(approval.get("html_url") or ""),
        )
        return result
    if pull.get("draft") is not False:
        result["reason"] = (
            "Draft pull requests are not reviewed; mark it ready for review"
        )
        return result
    verdict = None
    if mode == "copilot":
        verdict = copilot_verdict(
            reviews, head_sha, _comments_for(github, repo, pr_number)
        )
        result["copilot"] = {
            "state": verdict.state,
            "reason": verdict.reason,
            "review_url": (verdict.review or {}).get("html_url"),
            "findings": verdict.findings,
        }
        allowed, cap_reason = level_allows_copilot(
            max_level, level_decision.level
        )
        if allowed and verdict.state == "clean":
            result.update(
                passed=True,
                source="copilot",
                reason="Copilot reviewed the exact head and found no issues: "
                + str((verdict.review or {}).get("html_url") or ""),
            )
            return result
        if not allowed:
            result["reason"] = cap_reason
    if level_decision.review == "peer":
        labels = {
            str(label.get("name") or "").casefold()
            for label in pull.get("labels", [])
            if isinstance(label, dict)
        }
        if "hotfix" in labels:
            authorization = lifecycle.find_exact_head_authorization(
                github, repo, pr_number, head_sha
            )
            if authorization is not None:
                try:
                    evidence = lifecycle.hotfix_emergency_evidence(
                        github, repo, pull, authorization
                    )
                except RuntimeError as error:
                    result["reason"] = str(error)
                else:
                    result.update(
                        passed=True,
                        source="hotfix-emergency",
                        reason=(
                            "Admin emergency authorization covers the exact "
                            "head; post-review is required: "
                            f"{evidence['reason']}"
                        ),
                    )
                    return result
        result["reason"] = (
            result["reason"]
            or f"The {level_decision.level} release level requires an "
            "independent maintainer approval of the exact head"
        )
        return result
    bypass_authorization, bypass_reason = (
        _admin_bypass_authorization(github, repo, pr_number, head_sha, pull)
        if level_decision.review == "self"
        else (None, "")
    )
    if bypass_authorization is not None:
        result.update(
            passed=True,
            source="admin-bypass",
            reason="Admin bypass exact-head authorization: "
            + str(bypass_authorization.get("html_url") or ""),
        )
        return result
    if not result["reason"]:
        reason = (
            verdict.reason
            if verdict is not None
            else "No self-review authorization exists for the exact head"
        )
        result["reason"] = (
            f"{reason}. Get an independent maintainer approval, or use the "
            "configured audited admin-bypass path when it applies."
            + (f" {bypass_reason}" if bypass_reason else "")
        )
    return result


def _admin_bypass_authorization(
    github: GitHubReader,
    repo: str,
    pr_number: int,
    head_sha: str,
    pull: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    """Return the configured admin-bypass authorization for this head.

    Mirrors `pr_lifecycle.merge_snapshot`'s admin-bypass path (marker,
    route, exact-head authorization) without needing a lease: this gate
    runs on every push, well before any lease is acquired. Any rejection
    inside `admin_bypass_opt_in` (malformed marker, wrong route, or invalid
    Issue) means this path simply does not apply here, not
    that the check should error.

    The second return value explains *why* there is no authorization, so
    `evaluate()` can surface it instead of always falling back to the same
    Copilot-shaped message (Issue #781): a PR that never opted in (no
    marker) gets an empty reason, since the generic message already fits;
    a PR that opted in but was rejected -- a closed or Milestoned Issue, a
    malformed marker, an unauthorized comment author, or simply no
    matching exact-head comment at all -- gets the specific reason instead
    of looking identical to "Copilot has not reviewed this pull request
    yet."
    """
    lifecycle = importlib.import_module(
        "pr_lifecycle"
        if __package__ in {None, ""}
        else f"{__package__}.pr_lifecycle"
    )
    marker_count = (
        str(pull.get("body") or "")
        .splitlines()
        .count(lifecycle.ADMIN_BYPASS_MARKER)
    )
    if marker_count == 0:
        # Cheap check first: skip every further API call (default branch,
        # route validation) for the overwhelming majority of pull requests,
        # which never opt into admin bypass at all. No separate
        # release-channel gate here: `admin_bypass_opt_in` itself does not
        # check it either (its safety comes from the marker,
        # route, and live Ruleset shape), so adding one only here would let
        # this check and `pr_lifecycle.py merge` disagree about which heads
        # are actually mergeable.
        return None, ""
    try:
        repository = github.get(repo, "")
        default_branch = (
            repository.get("default_branch")
            if isinstance(repository, dict)
            else None
        )
        if not isinstance(default_branch, str):
            return None, "The repository default branch is unavailable"
        opted_in = lifecycle.admin_bypass_opt_in(
            github, repo, {"default_branch": default_branch}, pull
        )
    except RuntimeError as error:
        return None, f"Admin bypass does not apply here: {error}"
    if not opted_in:
        return None, ""
    authorization = lifecycle.find_exact_head_authorization(
        github, repo, pr_number, head_sha
    )
    if authorization is None:
        return None, (
            "Admin bypass applies but no exact-head maintainer "
            "authorization comment was found"
        )
    return authorization, ""


def unresolved_threads(repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Return unresolved review threads through GraphQL."""
    lifecycle = importlib.import_module(
        "pr_lifecycle"
        if __package__ in {None, ""}
        else f"{__package__}.pr_lifecycle"
    )
    owner, name = repo.split("/", 1)
    query = (
        "query($owner:String!,$name:String!,$number:Int!){repository("
        "owner:$owner,name:$name){pullRequest(number:$number){reviewThreads("
        "first:100){nodes{id isResolved isOutdated comments(first:1){nodes{"
        "author{login} path body url}}}}}}}"
    )
    payload = json.loads(
        lifecycle.run(
            [
                "gh",
                "api",
                "graphql",
                "-f",
                f"query={query}",
                "-F",
                f"owner={owner}",
                "-F",
                f"name={name}",
                "-F",
                f"number={pr_number}",
            ]
        )
    )
    nodes = payload["data"]["repository"]["pullRequest"]["reviewThreads"][
        "nodes"
    ]
    threads = []
    for node in nodes:
        if node.get("isResolved"):
            continue
        first = (node.get("comments", {}).get("nodes") or [{}])[0]
        threads.append(
            {
                "id": node.get("id"),
                "outdated": node.get("isOutdated"),
                "author": (first.get("author") or {}).get("login"),
                "path": first.get("path"),
                "body": first.get("body"),
                "url": first.get("url"),
            }
        )
    return threads


def parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("check", "status"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        command.add_argument("--pr", type=int, required=True)
        command.add_argument("--config", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    """Run one review-gate command."""
    args = parser().parse_args(argv)
    lifecycle = importlib.import_module(
        "pr_lifecycle"
        if __package__ in {None, ""}
        else f"{__package__}.pr_lifecycle"
    )
    github = lifecycle.GitHub()
    try:
        decision = evaluate(github, args.repo, args.pr, args.config)
        if args.command == "status":
            decision["unresolved_threads"] = unresolved_threads(
                args.repo, args.pr
            )
            sys.stdout.write(json.dumps(decision, indent=2) + "\n")
            return 0
    except (RuntimeError, ValueError, KeyError) as error:
        sys.stderr.write(f"review gate failed closed: {error}\n")
        return 1
    if decision["passed"]:
        sys.stdout.write(f"PASS ({decision['source']}): {decision['reason']}\n")
        return 0
    sys.stderr.write(f"FAIL: {decision['reason']}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
