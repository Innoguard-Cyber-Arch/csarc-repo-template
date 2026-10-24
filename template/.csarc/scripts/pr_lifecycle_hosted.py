"""Hosted-only half of `pr_lifecycle.py`, which lends it its globals."""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse

    from pr_lifecycle import (
        CLOSING_ISSUE,
        DELIVERY_BRANCH,
        ISSUE_WORK_BRANCH,
        REPOSITORY,
        REVIEW_CHECK_CONTEXT,
        SHA,
        GitHub,
        authenticated_dependabot_commit,
        canonical_json,
        commit_tree_sha,
        parse_time,
        verification_evidence,
    )

DEPENDABOT_ELIGIBILITY_CONTEXT = "dependabot-merge-eligible"
GITHUB_ACTIONS_APP_ID = 15368
SUCCESSFUL_CHECK_CONCLUSIONS = {"neutral", "skipped", "success"}
TRUSTED_CHECK_PRODUCERS: dict[str, tuple[str, frozenset[str]]] = {
    DEPENDABOT_ELIGIBILITY_CONTEXT: (
        ".github/workflows/dependabot-auto-merge.yml",
        frozenset({"pull_request_target"}),
    ),
    "title": (
        ".github/workflows/pr-policy.yml",
        frozenset({"merge_group", "pull_request_target"}),
    ),
    "verify": (
        ".github/workflows/ci.yml",
        frozenset({"merge_group", "pull_request_target"}),
    ),
    "review": (
        ".github/workflows/pr-review.yml",
        frozenset(
            {
                "issue_comment",
                "merge_group",
                "pull_request_review",
                "pull_request_target",
            }
        ),
    ),
}
REQUIRED_CHECKS_POLICY = Path("policies") / "rulesets-required-checks.json"
WORK_CLOSURE_MARKER = "Work Issue closure evidence"


def declared_required_contexts() -> set[tuple[str, int]]:
    """Read the trusted base's declared required checks (Issue #1076)."""
    path = Path(__file__).resolve().parents[1] / REQUIRED_CHECKS_POLICY
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Required checks: unreadable: {error}. Fix the declaration."
        ) from error
    rules = policy.get("rules") if isinstance(policy, dict) else None
    if not isinstance(rules, list):
        raise RuntimeError(
            "Required checks: malformed declaration. Fix '.csarc/config.yml'."
        )
    contexts: set[tuple[str, int]] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise RuntimeError(
                "Required checks: malformed declaration. Fix "
                "'.csarc/config.yml'."
            )
        if rule.get("type") != "required_status_checks":
            continue
        parameters = rule.get("parameters")
        items = (
            parameters.get("required_status_checks")
            if isinstance(parameters, dict)
            else None
        )
        if not isinstance(items, list):
            raise RuntimeError(
                "Required checks: malformed declaration. Fix "
                "'.csarc/config.yml'."
            )
        for item in items:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("context"), str)
                or not item["context"]
                or type(item.get("integration_id")) is not int
                or item["integration_id"] <= 0
            ):
                raise RuntimeError(
                    "Required checks: malformed declaration. Fix "
                    "'.csarc/config.yml'."
                )
            contexts.add((item["context"], item["integration_id"]))
    if not contexts:
        raise RuntimeError(
            "Hosted merge: no declared required checks. Declare them."
        )
    return contexts


def check_run_matches_context(
    item: dict[str, Any], context: str, integration_id: int
) -> bool:
    """Match a check only when its pinned GitHub App identity is exact."""
    if item.get("name") != context:
        return False
    app = item.get("app")
    return (
        isinstance(app, dict)
        and type(app.get("id")) is int
        and app["id"] > 0
        and app["id"] == integration_id
    )


def trusted_check_run_matches_context(
    github: GitHub,
    repo: str,
    head_sha: str,
    item: dict[str, Any],
    context: str,
    integration_id: int,
    run_cache: dict[int, dict[str, Any]],
) -> bool:
    """Match a required check to its trusted workflow and event."""
    if item.get("head_sha") != head_sha or not check_run_matches_context(
        item, context, integration_id
    ):
        return False
    producer = TRUSTED_CHECK_PRODUCERS.get(context)
    if producer is None:
        return False
    try:
        run_url = actions_run_url(str(item.get("details_url") or ""), repo)
    except RuntimeError:
        return False
    run_id = int(run_url.rsplit("/", 1)[1])
    if run_id not in run_cache:
        payload = github.get(repo, f"actions/runs/{run_id}")
        if not isinstance(payload, dict):
            raise RuntimeError(
                "Required check: malformed Actions run. Rerun it in GitHub "
                "Actions."
            )
        run_cache[run_id] = payload
    run = run_cache[run_id]
    repository = run.get("repository")
    check_suite = item.get("check_suite")
    workflow_path, trusted_events = producer
    suite_matches = (
        isinstance(check_suite, dict)
        and type(check_suite.get("id")) is int
        and check_suite["id"] > 0
        and type(run.get("check_suite_id")) is int
        and run["check_suite_id"] == check_suite["id"]
    )
    published_review_matches = (
        context == REVIEW_CHECK_CONTEXT
        and isinstance(check_suite, dict)
        and type(check_suite.get("id")) is int
        and check_suite["id"] > 0
        and item.get("external_id") == f"csarc-review:{run_id}:{head_sha}"
        and item.get("details_url") == run.get("html_url")
    )
    return (
        type(run.get("id")) is int
        and run["id"] == run_id
        and (suite_matches or published_review_matches)
        and run.get("head_sha") == head_sha
        and isinstance(repository, dict)
        and repository.get("full_name") == repo
        and run.get("path") == workflow_path
        and run.get("event") in trusted_events
    )


def trusted_required_check_runs(
    github: GitHub,
    repo: str,
    head_sha: str,
    contexts: set[tuple[str, int]],
    check_runs: list[dict[str, Any]],
) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[int, dict[str, Any]]]:
    """Select each newest check once after validating trusted provenance."""
    run_cache: dict[int, dict[str, Any]] = {}
    required_runs: dict[tuple[str, int], dict[str, Any]] = {}
    for context, integration_id in contexts:
        candidates = [
            item
            for item in check_runs
            if trusted_check_run_matches_context(
                github,
                repo,
                head_sha,
                item,
                context,
                integration_id,
                run_cache,
            )
        ]
        if candidates:
            required_runs[(context, integration_id)] = max(
                candidates, key=lambda item: int(item["id"])
            )
    return required_runs, run_cache


def require_trusted_dependabot_head(
    github: GitHub,
    repo: str,
    pull: dict[str, Any],
    head_sha: str,
    base_sha: str,
) -> str:
    """Reauthenticate one exact Dependabot head and its trusted eligibility."""
    kind, _commit = authenticated_dependabot_commit(
        github, repo, pull, head_sha, base_sha
    )
    check_runs = github.collection(
        repo,
        f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
        "check_runs",
    )
    identity = (DEPENDABOT_ELIGIBILITY_CONTEXT, GITHUB_ACTIONS_APP_ID)
    selected, _ = trusted_required_check_runs(
        github, repo, head_sha, {identity}, check_runs
    )
    check = selected.get(identity)
    if (
        check is None
        or check.get("status") != "completed"
        or check.get("conclusion") != "success"
    ):
        raise RuntimeError(
            "Dependabot head: no trusted merge eligibility. Merge it manually."
        )
    return kind


def require_trusted_verification(  # noqa: C901
    github: GitHub,
    repo: str,
    head_sha: str,
    integration_id: int,
    *,
    max_age_hours: float | None = None,
    required_tier: str | None = None,
    now: datetime | None = None,
    check_runs: list[dict[str, Any]] | None = None,
    durable: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Require fresh hosted execution evidence for one exact commit."""
    available = (
        check_runs
        if check_runs is not None
        else github.collection(
            repo,
            f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
            "check_runs",
        )
    )
    identity = ("verify", integration_id)
    selected, run_cache = trusted_required_check_runs(
        github, repo, head_sha, {identity}, available
    )
    check_run = selected.get(identity)
    if check_run is None:
        raise RuntimeError(
            "Verify check: no trusted producer on the exact head. Rerun "
            "'verify' on the exact head."
        )
    run_url = actions_run_url(str(check_run.get("details_url") or ""), repo)
    run_id = int(run_url.rsplit("/", 1)[1])
    workflow_run = run_cache[run_id]
    commit = github.get(repo, f"git/commits/{head_sha}")
    tree = commit.get("tree") if isinstance(commit, dict) else None
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    if not isinstance(tree_sha, str):
        raise RuntimeError(
            "Exact-head Git tree: unavailable. Run 'gh auth status' and rerun."
        )
    jobs = github.collection(
        repo,
        f"actions/runs/{run_id}/jobs?filter=latest&per_page=100",
        "jobs",
    )
    matching_jobs = [
        job
        for job in jobs
        if job.get("html_url") == check_run.get("details_url")
    ]
    if len(matching_jobs) != 1:
        raise RuntimeError(
            "Trusted verify check: no unique Actions job. Rerun 'verify' on "
            "the exact head."
        )
    job = matching_jobs[0]
    annotations = (
        github.pages(
            repo,
            f"check-runs/{check_run['id']}/annotations?per_page=100",
        )
        if verification_evidence.needs_route_annotations(job)
        else []
    )
    source_evidence = None
    source_ids = verification_evidence.evidence_source_ids(job, annotations)
    if source_ids is not None:
        source_kind, source_run_id, source_job_id, source_check_id = source_ids
        source_check = github.get(repo, f"check-runs/{source_check_id}")
        source_run = github.get(repo, f"actions/runs/{source_run_id}")
        if not isinstance(source_check, dict) or not isinstance(
            source_run, dict
        ):
            raise RuntimeError(
                "Verification reuse source: unavailable. Rerun verify."
            )
        source_head = source_check.get("head_sha")
        if not isinstance(source_head, str) or (
            source_kind == "reuse" and source_head != head_sha
        ):
            raise RuntimeError(
                "Verification reuse source: invalid head. Rerun verify."
            )
        source_cache = {source_run_id: source_run}
        if not trusted_check_run_matches_context(
            github,
            repo,
            source_head,
            source_check,
            "verify",
            integration_id,
            source_cache,
        ):
            raise RuntimeError(
                "Verification reuse source: invalid producer. Rerun verify."
            )
        source_jobs = github.collection(
            repo,
            f"actions/runs/{source_run_id}/jobs?filter=latest&per_page=100",
            "jobs",
        )
        matching_sources = [
            source_job
            for source_job in source_jobs
            if source_job.get("id") == source_job_id
            and source_job.get("html_url") == source_check.get("details_url")
        ]
        if len(matching_sources) != 1:
            raise RuntimeError(
                "Verification reuse source: no unique job. Rerun verify."
            )
        source_job = matching_sources[0]
        source_commit = (
            commit
            if source_head == head_sha
            else github.get(repo, f"git/commits/{source_head}")
        )
        source_tree = (
            source_commit.get("tree")
            if isinstance(source_commit, dict)
            else None
        )
        source_tree_sha = (
            source_tree.get("sha") if isinstance(source_tree, dict) else None
        )
        if not isinstance(source_tree_sha, str):
            raise RuntimeError(
                "Verification reuse source: tree unavailable. Rerun verify."
            )
        source_evidence = (
            source_check,
            source_run,
            source_job,
            source_tree_sha,
        )
    evidence = verification_evidence.validate_verification_job(
        check_run,
        workflow_run,
        job,
        repo=repo,
        head_sha=head_sha,
        tree_sha=tree_sha,
        now=now,
        max_age_hours=max_age_hours,
        required_tier=required_tier,
        source_evidence=source_evidence,
        annotations=annotations,
        commit_tree=lambda sha: commit_tree_sha(github, repo, sha),
        full_command=(
            "./.csarc/scripts/verify-template.sh"
            if Path(".csarc/scripts/verify-template.sh").is_file()
            else "./.csarc/scripts/verify"
        ),
    )
    if durable is not None:
        durable.clear()
        durable.update(
            hosted_payload(
                evidence, workflow_run, job, check_run, integration_id
            )
        )
    return evidence


def evidence_time(value: object, label: str) -> str:
    """Normalize a GitHub timestamp to the evidence `...Z` second form."""
    return parse_time(value, label).strftime("%Y-%m-%dT%H:%M:%SZ")


def hosted_payload(
    evidence: dict[str, object],
    workflow_run: dict[str, Any],
    job: dict[str, Any],
    check_run: dict[str, Any],
    integration_id: int,
) -> dict[str, Any]:
    """Normalize derived hosted facts into one canonical evidence payload."""
    repository = workflow_run.get("repository")
    repository_id = (
        repository.get("id") if isinstance(repository, dict) else None
    )
    labels = job.get("labels")
    toolchain = evidence.get("toolchain")
    scopes = evidence.get("scopes")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "trust": "github-hosted",
        "success": True,
        "conclusion": str(check_run.get("conclusion") or ""),
        "repository": {
            "full_name": str(evidence["repository"]),
            **(
                {"id": repository_id}
                if type(repository_id) is int and repository_id > 0
                else {}
            ),
        },
        "head_sha": str(evidence["head_sha"]),
        "tree_sha": str(evidence["tree_sha"]),
        "base_ref": str(evidence.get("base") or ""),
        "base_sha": str(evidence.get("base_sha") or ""),
        "tier": str(evidence["tier"]),
        "scopes": sorted(str(item) for item in scopes)
        if isinstance(scopes, list)
        else [],
        "command": str(evidence["command"]),
        "toolchain": sorted(str(item) for item in toolchain)
        if isinstance(toolchain, list)
        else [],
        "runner_labels": sorted(str(item) for item in labels)
        if isinstance(labels, list)
        else [],
        "executor": {
            "kind": "github-hosted",
            "id": f"{evidence['run_id']}/{workflow_run.get('run_attempt')}",
            "run_id": evidence["run_id"],
            "run_attempt": workflow_run.get("run_attempt"),
            "job_id": evidence["job_id"],
            "check_run_id": evidence["check_run_id"],
            "app_id": integration_id,
        },
        "started_at": evidence_time(job.get("started_at"), "Verify start"),
        "completed_at": evidence_time(
            evidence.get("completed_at"), "Verify completion"
        ),
    }
    if evidence.get("reused"):
        payload["source"] = {
            "run_id": evidence.get("source_run_id"),
            "job_id": evidence.get("source_job_id"),
            "check_run_id": evidence.get("source_check_run_id"),
            "sync_main_sha": evidence.get("sync_main_sha") or "",
        }
    return payload


def authoritative_check_runs(
    check_runs: list[dict[str, Any]], head_sha: str
) -> list[dict[str, Any]]:
    """Keep the newest check for each strict GitHub App identity."""
    candidate_runs = [
        item for item in check_runs if item.get("head_sha") == head_sha
    ]
    identities: list[tuple[str, int, int]] = []
    latest_ids: dict[tuple[str, int], int] = {}
    for item in candidate_runs:
        name = item.get("name")
        check_id = item.get("id")
        app = item.get("app")
        app_id = app.get("id") if isinstance(app, dict) else None
        if (
            not isinstance(name, str)
            or not name
            or type(check_id) is not int
            or check_id <= 0
            or type(app_id) is not int
            or app_id <= 0
        ):
            raise RuntimeError(
                "Check run: malformed identity. Rerun the check in GitHub "
                "Actions."
            )
        identity = (name, app_id)
        identities.append((name, app_id, check_id))
        latest_ids[identity] = max(latest_ids.get(identity, 0), check_id)
    return [
        item
        for item, (name, app_id, check_id) in zip(
            candidate_runs, identities, strict=True
        )
        if latest_ids[(name, app_id)] == check_id
    ]


def require_successful_checks(  # noqa: C901
    github: GitHub,
    repo: str,
    head_sha: str,
    contexts: set[tuple[str, int]],
    quota_run_urls: set[str] | None = None,
    durable: dict[str, Any] | None = None,
) -> str:
    """Require protected contexts to pass or have exact quota evidence."""
    check_runs = github.collection(
        repo,
        f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
        "check_runs",
    )
    authoritative_runs = authoritative_check_runs(check_runs, head_sha)
    required_runs, _run_cache = trusted_required_check_runs(
        github, repo, head_sha, contexts, check_runs
    )
    statuses = github.collection(
        repo,
        f"commits/{head_sha}/status?per_page=100",
        "statuses",
        head_sha,
    )
    missing = [
        (context, integration_id)
        for context, integration_id in contexts
        if (item := required_runs.get((context, integration_id))) is None
        or item.get("status") != "completed"
        or (
            item.get("conclusion") != "success"
            if context == "verify"
            else item.get("conclusion") not in SUCCESSFUL_CHECK_CONCLUSIONS
        )
    ]
    missing.sort()
    for context, integration_id in contexts:
        item = required_runs.get((context, integration_id))
        if (
            context == "verify"
            and item is not None
            and item.get("status") == "completed"
            and item.get("conclusion") == "success"
        ):
            require_trusted_verification(
                github,
                repo,
                head_sha,
                integration_id,
                check_runs=check_runs,
                durable=durable,
            )
    if quota_run_urls:
        non_quota_failures: set[str] = set()
        for item in authoritative_runs:
            name = str(item.get("name") or "unnamed check")
            if item.get("status") != "completed":
                non_quota_failures.add(name)
                continue
            if item.get("conclusion") in SUCCESSFUL_CHECK_CONCLUSIONS:
                continue
            if item.get("conclusion") != "failure":
                non_quota_failures.add(name)
                continue
            try:
                run_url = actions_run_url(
                    str(item.get("details_url") or ""), repo
                )
            except RuntimeError:
                non_quota_failures.add(name)
                continue
            if run_url not in quota_run_urls:
                non_quota_failures.add(name)
        non_quota_failures.update(
            str(item.get("context") or "unnamed status")
            for item in statuses
            if item.get("state") in {"error", "failure"}
        )
        if non_quota_failures:
            raise RuntimeError(
                "Exact head: non-quota check failures: "
                + ", ".join(sorted(non_quota_failures))
                + ". Fix the failed jobs."
            )
    if not missing:
        return "quota-fallback" if quota_run_urls else "success"
    if quota_run_urls:
        if any(context == "verify" for context, _integration_id in missing):
            raise RuntimeError(
                "Quota fallback: cannot replace trusted verify evidence. "
                "Rerun verify."
            )
        for context, integration_id in missing:
            failed_run = required_runs.get((context, integration_id))
            if (
                failed_run is None
                or failed_run.get("status") != "completed"
                or failed_run.get("conclusion") != "failure"
            ):
                break
            run_url = actions_run_url(
                str(failed_run.get("details_url") or ""), repo
            )
            if run_url not in quota_run_urls:
                break
        else:
            return "quota-fallback"
    raise RuntimeError(
        "Required checks: not passed on the exact head: "
        + ", ".join(context for context, _integration_id in missing)
        + ". Wait for them to pass."
    )


def actions_run_url(details_url: str, repo: str) -> str:
    """Normalize an exact-repository Actions check URL to its run URL."""
    parsed = urllib.parse.urlparse(details_url)
    match = re.fullmatch(
        rf"/{re.escape(repo)}/actions/runs/(\d+)(?:/job/\d+)?",
        parsed.path,
    )
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() != "github.com"
        or match is None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "Failed check: no Actions run URL here. Rerun it in GitHub Actions."
        )
    return f"https://github.com/{repo}/actions/runs/{match.group(1)}"


def work_closure_message(binding: dict[str, object]) -> str:
    """Return exact, replay-safe evidence for one work Issue closure."""
    return f"{WORK_CLOSURE_MARKER}\n\n`{canonical_json(binding)}`"


def close_work_issue(  # noqa: C901
    args: argparse.Namespace, github: GitHub
) -> None:
    """Close one Issue only after its exact work PR reaches its dev branch."""
    if (
        REPOSITORY.fullmatch(args.repo) is None
        or args.pr_number < 1
        or SHA.fullmatch(args.head_sha) is None
    ):
        raise RuntimeError(
            "Work Issue closure: invalid input. Pass --pr-number and "
            "--head-sha."
        )
    repository = github.get(args.repo, "")
    pull = github.get(args.repo, f"pulls/{args.pr_number}")
    if not isinstance(repository, dict) or not isinstance(pull, dict):
        raise RuntimeError(
            "Work Issue closure: state unavailable. Run 'gh auth status' and "
            "rerun."
        )
    head = pull.get("head") or {}
    base = pull.get("base") or {}
    head_repo = head.get("repo") or {} if isinstance(head, dict) else {}
    merge_sha = pull.get("merge_commit_sha")
    if (
        pull.get("number") != args.pr_number
        or pull.get("state") != "closed"
        or pull.get("merged") is not True
        or not isinstance(pull.get("merged_at"), str)
        or not isinstance(head, dict)
        or head.get("sha") != args.head_sha
        or not isinstance(head_repo, dict)
        or str(head_repo.get("full_name", "")).casefold()
        != args.repo.casefold()
        or not isinstance(base, dict)
        or not isinstance(merge_sha, str)
        or SHA.fullmatch(merge_sha) is None
    ):
        raise RuntimeError(
            "Merged pull request: invalid identity or head. Pass the merged PR "
            "number and head SHA."
        )
    parse_time(pull["merged_at"], "Pull request merge")
    default_branch = repository.get("default_branch")
    base_ref = base.get("ref")
    head_ref = head.get("ref")
    if not isinstance(default_branch, str) or not isinstance(base_ref, str):
        raise RuntimeError(
            "Pull request: destination unavailable. Run 'gh auth status' and "
            "rerun."
        )
    if base_ref == default_branch:
        sys.stdout.write(
            f"NOTICE: PR #{args.pr_number}: default-branch closing remains "
            "GitHub-native.\n"
        )
        return
    delivery = DELIVERY_BRANCH.fullmatch(base_ref)
    work = ISSUE_WORK_BRANCH.fullmatch(str(head_ref or ""))
    if delivery is None or work is None:
        raise RuntimeError(
            "Merged pull request: not a Milestone work route. Run close-work "
            "only for dev/m* work."
        )
    issue_number = int(work.group(1))
    closing_issues = [
        int(value)
        for value in CLOSING_ISSUE.findall(str(pull.get("body") or ""))
    ]
    if closing_issues != [issue_number]:
        raise RuntimeError(
            "Work pull request: does not close its Issue. Fix the body."
        )
    issue = github.get(args.repo, f"issues/{issue_number}")
    if (
        not isinstance(issue, dict)
        or issue.get("number") != issue_number
        or issue.get("pull_request") is not None
    ):
        raise RuntimeError(
            "Work Issue: invalid identity. Fix the work branch name."
        )
    expected_milestone = int(delivery.group(1))
    issue_milestone = issue.get("milestone") or {}
    pull_milestone = pull.get("milestone") or {}
    if (
        not isinstance(issue_milestone, dict)
        or not isinstance(pull_milestone, dict)
        or issue_milestone.get("number") != expected_milestone
        or pull_milestone.get("number") != expected_milestone
    ):
        raise RuntimeError(
            "Work Issue: PR or dev branch disagrees. Fix the route."
        )
    binding: dict[str, object] = {
        "base_ref": base_ref,
        "head_sha": args.head_sha,
        "issue": issue_number,
        "merge_commit_sha": merge_sha,
        "pull_request": args.pr_number,
        "repository": args.repo,
        "schema_version": 1,
    }
    message = work_closure_message(binding)
    comments = github.pages(args.repo, f"issues/{issue_number}/comments")
    evidence = [
        str(comment.get("body") or "")
        for comment in comments
        if str(comment.get("body") or "").startswith(WORK_CLOSURE_MARKER)
    ]
    if len(evidence) > 1 or (evidence and evidence != [message]):
        raise RuntimeError(
            "Work Issue: conflicting closure evidence. Run 'gh issue view'."
        )
    state = issue.get("state")
    if state == "closed":
        if issue.get("state_reason") != "completed" or evidence != [message]:
            raise RuntimeError(
                "Work Issue: closed without matching evidence. Reopen it."
            )
        sys.stdout.write(
            f"NOTICE: Issue #{issue_number} is already closed by PR "
            f"#{args.pr_number}.\n"
        )
        return
    if state != "open":
        raise RuntimeError("Work Issue: invalid state. Run 'gh issue view'.")
    if not evidence:
        github.comment(args.repo, issue_number, message)
    result = github.close_issue(args.repo, issue_number)
    if (
        result.get("number") != issue_number
        or result.get("state") != "closed"
        or result.get("state_reason") != "completed"
    ):
        raise RuntimeError(
            "Issue closure: GitHub did not confirm it. Run 'gh issue view'."
        )
    sys.stdout.write(
        f"OK: Issue #{issue_number} closed by merged PR #{args.pr_number}.\n"
    )
