#!/usr/bin/env python3
"""Create and verify delivery-promotion evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

UNCHECKED = re.compile(r"(?m)^\s*-\s+\[\s*\]")
CLOSING_ISSUE = re.compile(r"(?:Closes|Fixes|Resolves)\s+#(\d+)(?:\D|$)", re.I)
MILESTONE_BRANCH = re.compile(r"^dev/m(\d+)-[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class Route:
    """Promotion route selected from pull request metadata."""

    kind: str
    relevant: bool
    milestone: int | None = None


@dataclass(frozen=True)
class Canary:
    """External canary capability configured by repository variables."""

    state: str
    reason: str
    environment: str | None


def route_for(
    base: str, head: str, labels: set[str], branch_strategy: str = "delivery"
) -> Route:
    """Classify a pull request without accepting arbitrary main PRs."""
    if base != "main":
        return Route("not-applicable", False)
    if head.startswith("release-please--"):
        return Route("release-follow-up", False)
    if branch_strategy == "main":
        return Route("not-applicable", False)
    if branch_strategy == "dev":
        return (
            Route("dev-promotion", True)
            if head == "dev"
            else Route("invalid-main-route", True)
        )
    match = MILESTONE_BRANCH.fullmatch(head)
    if match and "promotion" in labels:
        return Route("milestone", True, int(match.group(1)))
    if head == "dev/next" and "promotion" in labels:
        return Route("standalone-batch", True)
    if head.startswith("fix/") and "hotfix" in labels:
        return Route("hotfix", True)
    return Route("invalid-main-route", True)


def classify_canary(command: str, environment: str) -> Canary:
    """Use an explicit tri-state instead of assuming an external environment."""
    if command and environment:
        return Canary(
            "allowed", "canary command and environment configured", environment
        )
    if not command and not environment:
        return Canary("blocked", "no external canary is configured", None)
    return Canary(
        "unknown",
        "canary command and environment must be configured together",
        environment or None,
    )


def issue_number(body: str) -> int | None:
    """Return the first Issue closed by a promotion pull request."""
    match = CLOSING_ISSUE.search(body)
    return int(match.group(1)) if match else None


def issue_labels(issue: dict[str, Any]) -> set[str]:
    """Normalize REST Issue labels."""
    labels = issue.get("labels", [])
    return {
        label["name"]
        for label in labels
        if isinstance(label, dict) and isinstance(label.get("name"), str)
    }


def same_repository(pull_request: dict[str, Any], repo: str) -> bool:
    """Reject same-named delivery branches supplied by a fork."""
    head = pull_request.get("head")
    head_repo = head.get("repo") if isinstance(head, dict) else None
    return isinstance(head_repo, dict) and head_repo.get("full_name") == repo


def unfinished_milestone_issues(
    issues: list[dict[str, Any]], promotion_number: int
) -> list[int]:
    """Return non-promotion work that is open or has unchecked acceptance."""
    unfinished: list[int] = []
    for issue in issues:
        if "pull_request" in issue or issue.get("number") == promotion_number:
            continue
        if "promotion" in issue_labels(issue):
            continue
        body = issue.get("body") or ""
        if issue.get("state") != "closed" or UNCHECKED.search(body):
            number = issue.get("number")
            if isinstance(number, int):
                unfinished.append(number)
    return sorted(unfinished)


def main_is_current(
    current_main: str, base_sha: str, contains_main: bool
) -> bool:
    """Require the reviewed base and delivery ancestry to match current main."""
    return current_main == base_sha and contains_main


def github_get(repo: str, path: str, token: str) -> object:
    """Read one GitHub REST endpoint with the workflow token."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{path.lstrip('/')}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
        return json.load(response)


def milestone_issues(
    repo: str, milestone: int, token: str
) -> list[dict[str, Any]]:
    """Read every Issue in a Milestone across REST pages."""
    issues: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "milestone": milestone,
                "state": "all",
                "per_page": 100,
                "page": page,
            }
        )
        payload = github_get(repo, f"issues?{query}", token)
        if not isinstance(payload, list):
            raise RuntimeError(
                "GitHub returned an invalid Milestone Issue list"
            )
        page_items = [item for item in payload if isinstance(item, dict)]
        issues.extend(page_items)
        if len(payload) < 100:
            return issues
        page += 1


def git_output(*arguments: str) -> str:
    """Run a read-only Git command and return one line."""
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git is required")
    return subprocess.run(  # noqa: S603
        [executable, *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def contains_commit(ancestor: str, descendant: str) -> bool:
    """Return whether the delivery head contains the current main commit."""
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git is required")
    return (
        subprocess.run(  # noqa: S603
            [executable, "merge-base", "--is-ancestor", ancestor, descendant],
            check=False,
        ).returncode
        == 0
    )


def sha256(path: Path) -> str:
    """Hash a candidate archive without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_outputs(path: Path | None, values: dict[str, object]) -> None:
    """Append scalar outputs for later workflow jobs."""
    if path is None:
        return
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            rendered = (
                str(value).lower() if isinstance(value, bool) else str(value)
            )
            output.write(f"{key}={rendered}\n")


def write_summary(path: Path | None, lines: list[str]) -> None:
    """Append concise human-readable evidence to the run summary."""
    if path is None:
        return
    with path.open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")


def prepare(args: argparse.Namespace) -> None:  # noqa: C901
    """Validate promotion prerequisites and create the candidate bundle."""
    event = json.loads(args.event_path.read_text(encoding="utf-8"))
    if args.event != "pull_request":
        route = Route("merge-queue", False)
        canary = classify_canary("", "")
        evidence = {"schema_version": 1, "route": asdict(route)}
    else:
        pull_request = event["pull_request"]
        labels = {
            item["name"]
            for item in pull_request.get("labels", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        base = pull_request["base"]["ref"]
        head = pull_request["head"]["ref"]
        route = route_for(base, head, labels, args.branch_strategy)
        canary = classify_canary(args.canary_command, args.canary_environment)
        evidence = {"schema_version": 1, "route": asdict(route)}
        if route.kind == "invalid-main-route":
            raise RuntimeError(
                "Only a promotion, hotfix, or release follow-up may target main"
            )
        if route.relevant:
            if not same_repository(pull_request, args.repo):
                raise RuntimeError(
                    "Promotion and hotfix branches must come from "
                    "this repository"
                )
            number = issue_number(pull_request.get("body") or "")
            if number is None and route.kind != "dev-promotion":
                raise RuntimeError(
                    "Promotion pull request must close its tracking Issue"
                )
            token = os.environ.get("GH_TOKEN", "")
            if not token:
                raise RuntimeError(
                    "GH_TOKEN is required for promotion preflight"
                )
            if number is not None:
                issue = github_get(args.repo, f"issues/{number}", token)
                if not isinstance(issue, dict) or issue.get("state") != "open":
                    raise RuntimeError(
                        "Promotion tracking Issue must exist and remain open"
                    )
                if UNCHECKED.search(issue.get("body") or ""):
                    raise RuntimeError(
                        "Promotion Issue has unchecked acceptance criteria"
                    )
                tracking_labels = issue_labels(issue)
                if (
                    route.kind in {"milestone", "standalone-batch"}
                    and "promotion" not in tracking_labels
                ):
                    raise RuntimeError(
                        "Promotion tracking Issue must use the promotion label"
                    )
                issue_milestone = (issue.get("milestone") or {}).get("number")
                if (
                    route.kind == "milestone"
                    and issue_milestone != route.milestone
                ):
                    raise RuntimeError(
                        "Promotion Issue and delivery branch Milestones differ"
                    )
                if route.kind != "milestone" and issue_milestone is not None:
                    raise RuntimeError(
                        "Standalone promotion or hotfix cannot use a Milestone"
                    )
            included: list[dict[str, object]] = []
            if route.milestone is not None:
                if number is None:
                    raise RuntimeError(
                        "Milestone promotion requires a tracking Issue"
                    )
                issues = milestone_issues(args.repo, route.milestone, token)
                unfinished = unfinished_milestone_issues(issues, number)
                if unfinished:
                    rendered = ", ".join(f"#{item}" for item in unfinished)
                    raise RuntimeError(
                        f"Milestone work is not complete: {rendered}"
                    )
                included = [
                    {"number": item["number"], "title": item.get("title", "")}
                    for item in issues
                    if "pull_request" not in item
                    and item.get("number") != number
                ]
            current_main = github_get(args.repo, "git/ref/heads/main", token)
            if not isinstance(current_main, dict):
                raise RuntimeError("GitHub returned an invalid main reference")
            main_object = current_main.get("object")
            current_main_sha = (
                main_object.get("sha")
                if isinstance(main_object, dict)
                else None
            )
            base_sha = pull_request["base"]["sha"]
            head_sha = pull_request["head"]["sha"]
            if not main_is_current(
                str(current_main_sha),
                base_sha,
                contains_commit(base_sha, head_sha),
            ):
                raise RuntimeError(
                    "Delivery branch must contain current main before promotion"
                )
            candidate_sha = args.candidate_sha
            candidate_tree = git_output(
                "rev-parse", f"{candidate_sha}^{{tree}}"
            )
            subprocess.run(  # noqa: S603
                [
                    shutil.which("git") or "git",
                    "archive",
                    "--format=tar.gz",
                    f"--output={args.archive}",
                    candidate_sha,
                ],
                check=True,
            )
            evidence = {
                "schema_version": 1,
                "repository": args.repo,
                "route": asdict(route),
                "pull_request": pull_request["number"],
                "tracking_issue": number,
                "base_ref": base,
                "base_sha": base_sha,
                "head_ref": head,
                "head_sha": head_sha,
                "candidate_sha": candidate_sha,
                "candidate_tree": candidate_tree,
                "candidate_archive": {
                    "name": args.archive.name,
                    "sha256": sha256(args.archive),
                },
                "included_issues": included,
                "canary": asdict(canary),
                "workflow_run": args.workflow_run,
                "created_at": datetime.now(UTC).isoformat(),
            }
    args.output.write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    write_outputs(
        args.github_output,
        {
            "relevant": route.relevant,
            "kind": route.kind,
            "canary_state": canary.state,
            "canary_environment": canary.environment or "",
            "pr_number": event.get("number", "none"),
            "candidate_sha": args.candidate_sha,
            "head_sha": (event.get("pull_request") or {})
            .get("head", {})
            .get("sha", "none"),
        },
    )
    write_summary(
        args.summary,
        [
            "## Promotion preflight",
            "",
            f"- Route: `{route.kind}`",
            f"- Canary capability: `{canary.state}` — {canary.reason}",
        ],
    )


def finalize(args: argparse.Namespace) -> None:
    """Record canary outcome and the peer full-CI gate."""
    evidence = json.loads(args.input.read_text(encoding="utf-8"))
    canary = evidence.get("canary", {})
    state = canary.get("state")
    if state == "allowed" and args.canary_result != "success":
        raise RuntimeError("Configured canary did not succeed")
    if state not in {"allowed", "blocked", "unknown"}:
        raise RuntimeError("Promotion evidence has an invalid canary state")
    canary["result"] = "passed" if state == "allowed" else "artifact-only"
    evidence["full_check"] = {
        "context": "verify",
        "status": "required-peer-check",
    }
    evidence["gate"] = "passed"
    args.output.write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


def verify_main(args: argparse.Namespace) -> None:
    """Prove the merged main tree is the candidate that passed both gates."""
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    checks = json.loads(args.checks.read_text(encoding="utf-8"))
    if evidence.get("gate") != "passed":
        raise RuntimeError("Promotion gate evidence is incomplete")
    expected = {
        "repository": args.repo,
        "pull_request": args.pr_number,
        "head_sha": args.head_sha,
    }
    for field, value in expected.items():
        if evidence.get(field) != value:
            raise RuntimeError(
                f"Promotion evidence {field} does not match main"
            )
    current_tree = git_output("rev-parse", f"{args.main_sha}^{{tree}}")
    if current_tree != evidence.get("candidate_tree"):
        raise RuntimeError(
            "Merged main tree differs from the verified candidate tree"
        )
    check_runs = (
        checks.get("check_runs", []) if isinstance(checks, dict) else []
    )
    if not any(
        item.get("name") == "verify" and item.get("conclusion") == "success"
        for item in check_runs
        if isinstance(item, dict)
    ):
        raise RuntimeError("Candidate has no successful verify check")
    evidence["post_merge"] = {
        "main_sha": args.main_sha,
        "main_tree": current_tree,
        "tree_identity": "verified",
        "verified_at": datetime.now(UTC).isoformat(),
    }
    args.output.write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


def parser() -> argparse.ArgumentParser:
    """Build the command line interface."""
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    prepare_command = commands.add_parser("prepare")
    prepare_command.add_argument("--event", required=True)
    prepare_command.add_argument("--event-path", type=Path, required=True)
    prepare_command.add_argument("--repo", required=True)
    prepare_command.add_argument(
        "--branch-strategy", choices=("main", "dev", "delivery"), required=True
    )
    prepare_command.add_argument("--candidate-sha", required=True)
    prepare_command.add_argument("--workflow-run", required=True)
    prepare_command.add_argument("--canary-command", default="")
    prepare_command.add_argument("--canary-environment", default="")
    prepare_command.add_argument("--archive", type=Path, required=True)
    prepare_command.add_argument("--output", type=Path, required=True)
    prepare_command.add_argument("--github-output", type=Path)
    prepare_command.add_argument("--summary", type=Path)
    prepare_command.set_defaults(handler=prepare)

    finalize_command = commands.add_parser("finalize")
    finalize_command.add_argument("--input", type=Path, required=True)
    finalize_command.add_argument("--output", type=Path, required=True)
    finalize_command.add_argument("--canary-result", required=True)
    finalize_command.set_defaults(handler=finalize)

    verify_command = commands.add_parser("verify-main")
    verify_command.add_argument("--repo", required=True)
    verify_command.add_argument("--pr-number", type=int, required=True)
    verify_command.add_argument("--head-sha", required=True)
    verify_command.add_argument("--main-sha", required=True)
    verify_command.add_argument("--evidence", type=Path, required=True)
    verify_command.add_argument("--checks", type=Path, required=True)
    verify_command.add_argument("--output", type=Path, required=True)
    verify_command.set_defaults(handler=verify_main)
    return root


def main() -> None:
    """Run the selected promotion evidence operation."""
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
