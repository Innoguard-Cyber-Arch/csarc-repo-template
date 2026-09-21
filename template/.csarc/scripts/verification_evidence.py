#!/usr/bin/env python3
"""Validate one trusted GitHub-hosted verification job's execution evidence."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

VALID_TIERS = {"docs", "fast", "full"}
TIER_RANK = {"docs": 0, "fast": 1, "full": 2}
VALID_SCOPES = {
    "dependency",
    "docs",
    "governance",
    "shell",
    "source",
    "template",
    "unknown",
    "workflow",
}
REQUIRED_STEPS = (
    "Select trusted verification plan",
    "Bind trusted verification identity",
)
EXECUTION_STEP = re.compile(
    r"^Execute trusted verification tier=(docs|fast|full) "
    r"scopes=([a-z,-]+) tree=([0-9a-f]{40}) "
    r"command=(\./.csarc/scripts/(?:verify-fast|verify-template\.sh|verify))"
    r"(?: base=([A-Za-z0-9._/-]+) base-sha=([0-9a-f]{40}) "
    r"labels=([0-9a-f]{64}) "
    r"release=(alpha|beta|early|formal|none))?$"
)
REUSE_STEP = re.compile(
    r"^Reuse trusted verification tier=(docs|fast|full) "
    r"scopes=([a-z,-]+) tree=([0-9a-f]{40}) "
    r"command=(\./.csarc/scripts/(?:verify-fast|verify-template\.sh|verify)) "
    r"base=([A-Za-z0-9._/-]+) base-sha=([0-9a-f]{40}) "
    r"labels=([0-9a-f]{64}) "
    r"release=(alpha|beta|early|formal|none) source-run=([1-9][0-9]*) "
    r"source-job=([1-9][0-9]*) source-check=([1-9][0-9]*)$"
)
SYNC_STEP = re.compile(
    r"^Validate trusted clean sync tier=(fast) "
    r"scopes=([a-z,-]+) tree=([0-9a-f]{40}) "
    r"command=(\./.csarc/scripts/verify-fast) "
    r"base=([A-Za-z0-9._/-]+) base-sha=([0-9a-f]{40}) "
    r"labels=([0-9a-f]{64}) "
    r"release=(alpha|beta|early|formal|none) main=([0-9a-f]{40}) "
    r"source-run=([1-9][0-9]*) source-job=([1-9][0-9]*) "
    r"source-check=([1-9][0-9]*)$"
)
TOOLCHAIN_STEP = re.compile(
    r"^Set up (Python 3\.[0-9]+|uv 0\.12\.15|pnpm 11\.22\.0|"
    r"Node\.js 24|Rust 1\.98\.0)$"
)


def parse_github_time(value: object, field: str) -> datetime:
    """Parse one required GitHub UTC timestamp."""
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Trusted verification {field} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError(
            f"Trusted verification {field} is malformed"
        ) from error
    if parsed.tzinfo is None:
        raise RuntimeError(f"Trusted verification {field} has no timezone")
    return parsed.astimezone(UTC)


def successful_steps(job: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return uniquely named successful steps from one completed job."""
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RuntimeError("Trusted verification job has no step evidence")
    result: dict[str, dict[str, Any]] = {}
    for item in steps:
        if not isinstance(item, dict):
            raise RuntimeError("Trusted verification job has a malformed step")
        name = item.get("name")
        if not isinstance(name, str) or not name or name in result:
            raise RuntimeError(
                "Trusted verification job has duplicate or malformed step names"
            )
        if (
            item.get("status") == "completed"
            and item.get("conclusion") == "success"
        ):
            result[name] = item
    return result


def toolchain_token(step_name: str) -> str | None:
    """Return the canonical token for one pinned setup step."""
    match = TOOLCHAIN_STEP.fullmatch(step_name)
    if match is None:
        return None
    return (
        match.group(1).casefold().replace("node.js", "node").replace(" ", "-")
    )


def evidence_source_ids(
    job: dict[str, Any],
) -> tuple[str, int, int, int] | None:
    """Return one direct execution source claimed by a reuse or sync job."""
    steps = job.get("steps")
    if not isinstance(steps, list):
        return None
    matches: list[tuple[str, re.Match[str]]] = []
    for step in steps:
        if (
            isinstance(step, dict)
            and step.get("status") == "completed"
            and step.get("conclusion") == "success"
            and isinstance(step.get("name"), str)
        ):
            for kind, pattern in (("reuse", REUSE_STEP), ("sync", SYNC_STEP)):
                if (match := pattern.fullmatch(step["name"])) is not None:
                    matches.append((kind, match))
    if len(matches) != 1:
        return None
    kind, match = matches[0]
    offset = 8 if kind == "reuse" else 9
    source_run, source_job, source_check = map(
        int, match.groups()[offset : offset + 3]
    )
    return kind, source_run, source_job, source_check


def validate_verification_job(  # noqa: C901
    check_run: dict[str, Any],
    workflow_run: dict[str, Any],
    job: dict[str, Any],
    *,
    repo: str,
    head_sha: str,
    tree_sha: str,
    now: datetime | None = None,
    max_age_hours: float = 24.0,
    max_clock_skew_minutes: float = 5.0,
    full_command: str = "./.csarc/scripts/verify",
    required_tier: str | None = None,
    expected_toolchain: set[str] | None = None,
    source_evidence: tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]
    | None = None,
) -> dict[str, object]:
    """Validate exact-tree, toolchain, result, runner, and freshness claims."""
    if max_age_hours <= 0 or max_clock_skew_minutes < 0:
        raise RuntimeError("Trusted verification freshness bounds are invalid")
    if (
        re.fullmatch(r"[0-9a-f]{40}", head_sha) is None
        or re.fullmatch(r"[0-9a-f]{40}", tree_sha) is None
    ):
        raise RuntimeError("Trusted verification commit identity is malformed")
    repository = workflow_run.get("repository")
    if (
        check_run.get("head_sha") != head_sha
        or workflow_run.get("head_sha") != head_sha
        or job.get("head_sha") != head_sha
        or not isinstance(repository, dict)
        or repository.get("full_name") != repo
    ):
        raise RuntimeError(
            "Trusted verification repository or exact head does not match"
        )
    run_id = workflow_run.get("id")
    check_id = check_run.get("id")
    if (
        type(run_id) is not int
        or run_id <= 0
        or job.get("run_id") != run_id
        or type(check_id) is not int
        or check_id <= 0
        or job.get("id") != check_id
        or job.get("run_attempt") != workflow_run.get("run_attempt")
    ):
        raise RuntimeError("Trusted verification run identity does not match")
    if (
        check_run.get("status") != "completed"
        or check_run.get("conclusion") != "success"
        or workflow_run.get("status") != "completed"
        or workflow_run.get("conclusion") != "success"
        or job.get("status") != "completed"
        or job.get("conclusion") != "success"
    ):
        raise RuntimeError("Trusted verification did not complete successfully")
    if job.get("name") != "verify" or job.get("html_url") != check_run.get(
        "details_url"
    ):
        raise RuntimeError("Trusted verification job identity does not match")
    labels = job.get("labels")
    if (
        not isinstance(labels, list)
        or "ubuntu-latest" not in labels
        or type(job.get("runner_id")) is not int
        or job["runner_id"] <= 0
        or job.get("runner_group_name") != "GitHub Actions"
    ):
        raise RuntimeError("Trusted verification did not use ubuntu-latest")
    if "self-hosted" in labels:
        raise RuntimeError("Trusted verification used an untrusted runner")

    completed_at = parse_github_time(job.get("completed_at"), "completion time")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if completed_at - current > timedelta(minutes=max_clock_skew_minutes):
        raise RuntimeError(
            "Trusted verification completion time is in the future"
        )
    if current - completed_at > timedelta(hours=max_age_hours):
        raise RuntimeError("Trusted verification evidence is stale")

    steps = successful_steps(job)
    missing_steps = [name for name in REQUIRED_STEPS if name not in steps]
    if missing_steps:
        raise RuntimeError(
            "Trusted verification toolchain or routing steps did not succeed: "
            + ", ".join(missing_steps)
        )
    execution_names = [
        name for name in steps if name.startswith("Execute trusted")
    ]
    reuse_names = [name for name in steps if name.startswith("Reuse trusted")]
    sync_names = [
        name for name in steps if name.startswith("Validate trusted clean sync")
    ]
    if len(execution_names) + len(reuse_names) + len(sync_names) != 1:
        raise RuntimeError(
            "Trusted verification must have one execution, reuse, or sync step"
        )
    name = (
        execution_names[0]
        if execution_names
        else reuse_names[0]
        if reuse_names
        else sync_names[0]
    )
    pattern = (
        EXECUTION_STEP
        if execution_names
        else REUSE_STEP
        if reuse_names
        else SYNC_STEP
    )
    match = pattern.fullmatch(name)
    if match is None:
        raise RuntimeError("Trusted verification evidence is malformed")
    tier, raw_scopes, claimed_tree, command, base, base_sha, labels, release = (
        match.groups()[:8]
    )
    scopes = raw_scopes.split(",")
    if required_tier is not None and required_tier not in VALID_TIERS:
        raise RuntimeError("Trusted verification required tier is invalid")
    if (
        tier not in VALID_TIERS
        or scopes != sorted(set(scopes))
        or any(scope not in VALID_SCOPES for scope in scopes)
        or (full_command if tier == "full" else "./.csarc/scripts/verify-fast")
        != command
    ):
        raise RuntimeError(
            "Trusted verification tier, scopes, or command is invalid"
        )
    if required_tier is not None and TIER_RANK[tier] < TIER_RANK[required_tier]:
        raise RuntimeError("Trusted verification tier is insufficient")
    if claimed_tree != tree_sha:
        raise RuntimeError(
            "Trusted verification tree does not match the commit"
        )
    common: dict[str, object] = {
        "check_run_id": check_run.get("id"),
        "run_id": run_id,
        "job_id": job.get("id"),
        "repository": repo,
        "head_sha": head_sha,
        "tree_sha": tree_sha,
        "tier": tier,
        "scopes": scopes,
        "command": command,
        "base": base,
        "base_sha": base_sha,
        "labels": labels,
        "release_level": release,
    }
    if reuse_names or sync_names:
        if source_evidence is None:
            raise RuntimeError(
                "Trusted verification reuse has no direct execution source"
            )
        offset = 8 if reuse_names else 9
        source_run_id, source_job_id, source_check_id = map(
            int, match.groups()[offset : offset + 3]
        )
        source_check, source_run, source_job, source_tree = source_evidence
        if (
            source_run.get("id") != source_run_id
            or source_job.get("id") != source_job_id
            or source_check.get("id") != source_check_id
        ):
            raise RuntimeError(
                "Trusted verification reuse source identity does not match"
            )
        if evidence_source_ids(source_job) is not None:
            raise RuntimeError(
                "Trusted verification reuse has no direct execution source"
            )
        source = validate_verification_job(
            source_check,
            source_run,
            source_job,
            repo=repo,
            head_sha=str(source_check.get("head_sha") or ""),
            tree_sha=source_tree,
            now=now,
            max_age_hours=max_age_hours,
            max_clock_skew_minutes=max_clock_skew_minutes,
            full_command=full_command,
            required_tier="full" if sync_names else required_tier,
            expected_toolchain=expected_toolchain,
        )
        if reuse_names and any(
            source[key] != common[key]
            for key in (
                "repository",
                "head_sha",
                "tree_sha",
                "tier",
                "scopes",
                "command",
                "base",
                "base_sha",
                "labels",
                "release_level",
            )
        ):
            raise RuntimeError(
                "Trusted verification reuse route does not match its source"
            )
        return {
            **common,
            "toolchain": source["toolchain"],
            "completed_at": source["completed_at"],
            "reused": True,
            "source_run_id": source_run_id,
            "source_job_id": source_job_id,
            "source_check_run_id": source_check_id,
            "sync_main_sha": match.group(9) if sync_names else None,
        }

    successful_toolchain = [
        token
        for step_name in steps
        if (token := toolchain_token(step_name)) is not None
    ]
    if (
        "uv-0.12.15" not in successful_toolchain
        or len(successful_toolchain) != len(set(successful_toolchain))
        or (
            expected_toolchain is not None
            and set(successful_toolchain) != expected_toolchain
        )
    ):
        raise RuntimeError("Trusted verification toolchain evidence is invalid")
    return {
        **common,
        "toolchain": successful_toolchain,
        "completed_at": completed_at.isoformat(),
        "reused": False,
    }
