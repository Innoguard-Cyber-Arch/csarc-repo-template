#!/usr/bin/env python3
"""Decide whether a pull request's exact head has earned review.

``check``, ``status``, and ``pr_lifecycle.py merge`` share `decide` and its
reason codes (Issue #1082). A clean exact-head Copilot review satisfies self
or peer review only when allowed, the Ruleset shape can run it, and no valid
admin-bypass marker exists; otherwise the result equals ``off``.

Copilot never submits ``APPROVED``; a clean review is a ``COMMENTED``
review whose body states that it generated no comments. The gate remains
pending while the current head has not been reviewed, and fails closed on
conclusive problems: inline comments, findings Copilot moved into the body
as suppressed low-confidence comments, or wording this module does not
recognize. Unresolved review threads are enforced natively by the
Ruleset's ``required_review_thread_resolution``; ``status`` still lists
them so the local agent loop knows what is left to answer.

Commands:

* ``check``: a local fail-closed evaluation of the ``review`` decision.
* ``publish``: the hosted publisher for the required check. Waiting states
  stay in progress, while conclusive decisions complete as success or failure.
* ``status``: JSON for the local fix loop -- the Copilot findings on the
  current head and the unresolved threads to answer before merging.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
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

CommentLoader = Callable[[object], list[dict[str, Any]]]


class GitHubReader(Protocol):
    """The read-only subset of ``pr_lifecycle.GitHub`` this gate uses."""

    def get(self, repo: str, path: str) -> object:
        """Read one REST resource."""
        ...

    def pages(self, repo: str, path: str) -> list[dict[str, Any]]:
        """Read every page of one REST collection."""
        ...


class LevelDecision(Protocol):
    """The resolved release level and its human review mode."""

    level: str
    review: str


@dataclass(frozen=True)
class CopilotReview:
    """Copilot's verdict on one exact head."""

    state: str
    reason: str
    review: dict[str, Any] | None = None
    findings: list[dict[str, Any]] = field(default_factory=list)


def review_settings(path: Path | None = None) -> str:
    """Return ``copilot`` when Copilot evidence is allowed, else ``human``."""
    config_path = path or csarc_config.CONFIG_FILE
    if not config_path.exists():
        return "human"
    # Schema 2 always states copilot_review; legacy review keys are read
    # only by the pinned CLI's migration registry (SPEC-009, Issue #1071).
    config = csarc_config.load_config(config_path)
    return "copilot" if config["copilot_review"] == "allowed" else "human"


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
    if review.get("state") == "DISMISSED":
        return CopilotReview(
            "pending", "Copilot's review of the current head was dismissed"
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


def _lifecycle() -> ModuleType:
    return importlib.import_module(
        "pr_lifecycle"
        if __package__ in {None, ""}
        else f"{__package__}.pr_lifecycle"
    )


def _comments_for(
    github: GitHubReader, repo: str, pr_number: int
) -> CommentLoader:
    def load(review_id: object) -> list[dict[str, Any]]:
        return github.pages(
            repo, f"pulls/{pr_number}/reviews/{review_id}/comments?per_page=100"
        )

    return load


def copilot_route(github: GitHubReader, repo: str, branch: str) -> str:
    """Return whether the Ruleset shape can run the Copilot route.

    Only shapes A and E1 (#1058 decision 4) need zero native approvals with
    stale-review dismissal and thread resolution. Shape C, other shapes, or
    an unreadable Ruleset degrade to ``off``; entitlement is never probed.
    """
    try:
        rules = github.get(
            repo, f"rules/branches/{urllib.parse.quote(branch, safe='')}"
        )
    except RuntimeError:
        return "unavailable"
    pull = [
        item.get("parameters")
        for item in (rules if isinstance(rules, list) else [])
        if isinstance(item, dict) and item.get("type") == "pull_request"
    ]
    shaped = (
        bool(pull)
        and all(
            isinstance(item, dict)
            and type(item.get("required_approving_review_count")) is int
            and item["required_approving_review_count"] == 0
            for item in pull
        )
        and any(item.get("dismiss_stale_reviews_on_push") for item in pull)
        and any(item.get("required_review_thread_resolution") for item in pull)
    )
    return "available" if shaped else "unavailable"


def _admin_bypass_state(
    github: GitHubReader,
    repo: str,
    pull: dict[str, Any],
    default_branch: str | None,
) -> tuple[str, str]:
    """Return ``absent``, ``valid``, or ``invalid`` (with why, #781)."""
    lifecycle = _lifecycle()
    if (
        lifecycle.ADMIN_BYPASS_MARKER
        not in str(pull.get("body") or "").splitlines()
    ):
        # Cheap check first: most pull requests never opt in.
        return "absent", ""
    try:
        if default_branch is None:
            repository = github.get(repo, "")
            default_branch = (
                repository.get("default_branch")
                if isinstance(repository, dict)
                else None
            )
            if not isinstance(default_branch, str):
                return "invalid", "The repository default branch is unavailable"
        opted_in = lifecycle.admin_bypass_opt_in(
            github, repo, {"default_branch": default_branch}, pull
        )
    except RuntimeError as error:
        return "invalid", str(error)
    return ("valid", "") if opted_in else ("absent", "")


def head_pushers(
    github: GitHubReader, repo: str, pull: dict[str, Any]
) -> tuple[set[str], str]:
    """Return the accounts that last pushed or committed the exact head.

    Issue #1211 (revising #1058 decision 27): an approval is independent
    unless its reviewer authored the pull request or last pushed the
    approved head. The merge actor is no longer excluded; an agent that
    pushes under a maintainer's account still makes that maintainer's
    approval non-independent. The head commit's GitHub committer and the
    actor of the newest branch activity whose ``after`` is the head are
    excluded. When no such push is readable the pusher is unknown and the
    second element names why: no approval counts as independent then.
    """
    head = pull.get("head") or {}
    sha = str(head.get("sha") or "")
    ref = str(head.get("ref") or "")
    head_repo = str((head.get("repo") or {}).get("full_name") or "")
    if not sha or not ref or not head_repo:
        return set(), "the pull request head repository or branch is unknown"
    branch = urllib.parse.quote(f"refs/heads/{ref}", safe="")
    try:
        commit = github.get(repo, f"commits/{sha}")
        activity = github.get(head_repo, f"activity?ref={branch}&per_page=100")
    except RuntimeError as error:
        return set(), f"the head pusher could not be read: {error}"
    pushers: set[str] = set()
    committer = commit.get("committer") if isinstance(commit, dict) else None
    if isinstance(committer, dict) and isinstance(committer.get("login"), str):
        pushers.add(committer["login"].casefold())
    pushes = [
        item
        for item in (activity if isinstance(activity, list) else [])
        if isinstance(item, dict)
        and item.get("after") == sha
        and item.get("activity_type") != "branch_deletion"
        and isinstance(item.get("timestamp"), str)
    ]
    if not pushes:
        return set(), "no push of the exact head was found on its branch"
    lifecycle = _lifecycle()
    newest = max(
        pushes,
        key=lambda item: lifecycle.parse_time(item["timestamp"], "Push"),
    )
    actor = newest.get("actor")
    login = actor.get("login") if isinstance(actor, dict) else None
    if not isinstance(login, str) or not login:
        return set(), "the last push of the exact head has no actor"
    pushers.add(login.casefold())
    return pushers, ""


def review_inputs(
    github: GitHubReader,
    repo: str,
    pr_number: int,
    pull: dict[str, Any],
    mode: str,
    level: LevelDecision,
    *,
    actor: str = "",
    default_branch: str | None = None,
    admin_bypass: str | None = None,
) -> dict[str, Any]:
    """Read every live input of `decide`; merge adds its actor and route.

    The merge ``actor`` no longer limits who may approve (#1211): only the
    pull request author and the head's last pusher are excluded.
    """
    lifecycle = _lifecycle()
    head_sha = str((pull.get("head") or {}).get("sha") or "")
    author = str((pull.get("user") or {}).get("login") or "").casefold()
    reviews = github.pages(repo, f"pulls/{pr_number}/reviews?per_page=100")
    states = lifecycle.current_reviews(reviews)
    pushers: set[str] = set()
    unknown_pusher = ""
    if any(
        login != author
        and review.get("state") == "APPROVED"
        and review.get("commit_id") == head_sha
        for login, review in states.items()
    ):
        # Read the pusher only when an approval could count.
        pushers, unknown_pusher = head_pushers(github, repo, pull)
    labels = {
        str(label.get("name") or "").casefold()
        for label in pull.get("labels", [])
        if isinstance(label, dict)
    }
    inputs: dict[str, Any] = {
        "repository": repo,
        "pull_request": pr_number,
        "head_sha": head_sha,
        "draft": pull.get("draft") is not False,
        "mode": mode,
        "release_level": level.level,
        "required_review": level.review,
        "approval": None
        if unknown_pusher
        else lifecycle.exact_head_approval(
            github,
            repo,
            states,
            head_sha,
            ({author} | pushers) - {""},
        ),
        "approval_independence": unknown_pusher,
        "admin_bypass": "absent",
        "admin_bypass_reason": "",
        "admin_authorization": None,
        "hotfix": level.review == "peer" and "hotfix" in labels,
        "hotfix_authorization": None,
        "hotfix_reason": "",
        "copilot_route": "unavailable",
        "copilot": None,
    }
    if level.review == "self":
        state, reason = (
            (admin_bypass, "")
            if admin_bypass is not None
            else _admin_bypass_state(github, repo, pull, default_branch)
        )
        inputs.update(admin_bypass=state, admin_bypass_reason=reason)
        if state == "valid":
            # Only a live `role_name` of `admin` may replace peer approval.
            inputs["admin_authorization"] = (
                lifecycle.find_exact_head_authorization(
                    github, repo, pr_number, head_sha, require_admin=True
                )
            )
    if inputs["hotfix"]:
        authorization = lifecycle.find_exact_head_authorization(
            github, repo, pr_number, head_sha
        )
        if authorization is not None:
            try:
                evidence = lifecycle.hotfix_emergency_evidence(
                    github, repo, pull, authorization
                )
            except RuntimeError as error:
                inputs["hotfix_reason"] = str(error)
            else:
                inputs["hotfix_authorization"] = authorization
                inputs["hotfix_reason"] = str(evidence["reason"])
    if mode == "copilot":
        inputs["copilot_route"] = copilot_route(
            github, repo, str((pull.get("base") or {}).get("ref") or "")
        )
        inputs["copilot"] = copilot_verdict(
            reviews, head_sha, _comments_for(github, repo, pr_number)
        )
    return inputs


def _binding(inputs: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    """Bind accepted evidence to its exact repository, head, and author."""
    return {
        "repository": inputs["repository"],
        "pull_request": inputs["pull_request"],
        "head_sha": inputs["head_sha"],
        "id": item.get("id"),
        "author": (item.get("user") or {}).get("login"),
        "state": item.get("state"),
        "commit_id": item.get("commit_id"),
        "at": item.get("submitted_at") or item.get("created_at"),
        "url": item.get("html_url"),
        "admin_bypass": inputs["admin_bypass"],
    }


def decide(inputs: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    """Return the one review decision shared by every entry point."""
    result = {
        key: inputs[key]
        for key in (
            "repository",
            "head_sha",
            "mode",
            "release_level",
            "required_review",
            "admin_bypass",
        )
    }
    verdict = inputs["copilot"]
    if verdict is not None:
        result["copilot"] = {
            "state": verdict.state,
            "reason": verdict.reason,
            "route": inputs["copilot_route"],
            "review_url": (verdict.review or {}).get("html_url"),
            "findings": verdict.findings,
        }

    def done(
        state: str,
        code: str,
        reason: str,
        source: str | None = None,
        item: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result.update(
            state=state,
            passed=state == "success",
            source=source,
            code=code,
            reason=reason,
            evidence=_binding(inputs, item) if item is not None else None,
        )
        return result

    approval = inputs["approval"]
    if approval is not None:
        return done(
            "success",
            "maintainer-approval",
            "An independent maintainer approved the exact head: "
            + str(approval.get("html_url") or ""),
            "maintainer",
            approval,
        )
    if inputs["draft"]:
        return done(
            "pending",
            "draft",
            "Draft pull requests are not reviewed; mark it ready for review",
        )
    bypass = inputs["admin_bypass"]
    if bypass == "invalid":
        return done(
            "failure",
            "admin-bypass-invalid",
            "Admin bypass does not apply here: "
            + inputs["admin_bypass_reason"],
        )
    if bypass == "valid":
        authorization = inputs["admin_authorization"]
        if authorization is None:
            return done(
                "pending",
                "admin-bypass-unauthorized",
                "Admin bypass applies but no exact-head maintainer "
                "authorization comment from a live admin was found",
            )
        return done(
            "success",
            "admin-bypass-authorized",
            "Admin bypass exact-head authorization: "
            + str(authorization.get("html_url") or ""),
            "admin-bypass",
            authorization,
        )
    copilot_code = ""
    if verdict is not None and inputs["copilot_route"] == "available":
        if verdict.state == "clean" and verdict.review is not None:
            return done(
                "success",
                "copilot-clean",
                "Copilot reviewed the exact head and found no issues: "
                + str(verdict.review.get("html_url") or ""),
                "copilot",
                verdict.review,
            )
        if verdict.state in {"changes", "unrecognized"}:
            copilot_code = f"copilot-{verdict.state}"
    if inputs["hotfix"] and inputs["hotfix_reason"]:
        authorization = inputs["hotfix_authorization"]
        if authorization is None:
            return done("failure", "hotfix-invalid", inputs["hotfix_reason"])
        return done(
            "success",
            "hotfix-emergency-authorized",
            "Admin emergency authorization covers the exact head; "
            "post-review is required: " + inputs["hotfix_reason"],
            "hotfix-emergency",
            authorization,
        )
    required = (
        f"The {inputs['release_level']} release level requires an "
        "independent maintainer approval of the exact head"
        if inputs["required_review"] == "peer"
        else "No self-review authorization exists for the exact head. Get "
        "an independent maintainer approval, or use the configured audited "
        "admin-bypass path when it applies"
    )
    if inputs.get("approval_independence"):
        # #1211: an unknown last pusher makes every approval non-independent.
        required += (
            "; an approval does not count while its independence is "
            "unknown: " + inputs["approval_independence"]
        )
    if copilot_code:
        return done("failure", copilot_code, f"{verdict.reason}. {required}")
    return done("pending", "approval-required", required)


def evaluate(
    github: GitHubReader,
    repo: str,
    pr_number: int,
    config: Path | None = None,
) -> dict[str, Any]:
    """Return the review decision for the pull request's current head."""
    pull = github.get(repo, f"pulls/{pr_number}")
    if not isinstance(pull, dict):
        raise RuntimeError("Pull request is unavailable")
    level = release_level.resolve_pull(
        github, repo, pull, release_level.load_settings(config)
    )
    return decide(
        review_inputs(
            github, repo, pr_number, pull, review_settings(config), level
        )
    )


def unresolved_threads(repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Return unresolved review threads through GraphQL."""
    lifecycle = _lifecycle()
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
    for name in ("check", "status", "publish"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        command.add_argument("--pr", type=int, required=True)
        command.add_argument("--config", type=Path)
        if name == "publish":
            command.add_argument("--details-url", required=True)
            command.add_argument("--run-id", type=int, required=True)
    return result


def publish_check(
    repo: str,
    decision: dict[str, Any],
    details_url: str,
    run_id: int,
) -> None:
    """Publish one three-state review check from the trusted workflow."""
    lifecycle = _lifecycle()
    state = decision.get("state")
    head_sha = decision.get("head_sha")
    run_url = lifecycle.actions_run_url(details_url, repo)
    if (
        state not in {"pending", "success", "failure"}
        or not isinstance(head_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", head_sha) is None
        or run_id < 1
        or run_url != details_url.rstrip("/")
        or not run_url.endswith(f"/{run_id}")
    ):
        raise RuntimeError("Review check publication identity is invalid")
    payload: dict[str, Any] = {
        "name": "review",
        "head_sha": head_sha,
        "status": "queued" if state == "pending" else "completed",
        "details_url": run_url,
        "external_id": f"csarc-review:{run_id}:{head_sha}",
        "output": {
            "title": "Review pending"
            if state == "pending"
            else "Review decision",
            "summary": str(
                decision.get("reason") or "Review decision unavailable"
            ),
        },
    }
    if state != "pending":
        payload["conclusion"] = state
    response = json.loads(
        lifecycle.run(
            [
                "gh",
                "api",
                "--method",
                "POST",
                f"repos/{repo}/check-runs",
                "--input",
                "-",
            ],
            input_text=json.dumps(payload),
        )
    )
    if (
        not isinstance(response, dict)
        or response.get("name") != "review"
        or response.get("head_sha") != head_sha
        or response.get("status") != payload["status"]
        or response.get("external_id") != payload["external_id"]
        or response.get("conclusion") != payload.get("conclusion")
    ):
        raise RuntimeError("GitHub returned an invalid review check")


def main(argv: list[str] | None = None) -> int:
    """Run one review-gate command."""
    args = parser().parse_args(argv)
    lifecycle = _lifecycle()
    github = lifecycle.GitHub()
    try:
        decision = evaluate(github, args.repo, args.pr, args.config)
        if args.command == "status":
            decision["unresolved_threads"] = unresolved_threads(
                args.repo, args.pr
            )
            sys.stdout.write(json.dumps(decision, indent=2) + "\n")
            return 0
        if args.command == "publish":
            publish_check(args.repo, decision, args.details_url, args.run_id)
            sys.stdout.write(
                f"Published review {decision['state']}: {decision['reason']}\n"
            )
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
