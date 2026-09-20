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
EVIDENCE_STEP = re.compile(
    r"^Execute trusted verification tier=(docs|fast|full) "
    r"scopes=([a-z,-]+) tree=([0-9a-f]{40}) "
    r"command=(\./scripts/(?:verify-fast|verify-template\.sh|verify))$"
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
    full_command: str = "./scripts/verify-template.sh",
    required_tier: str | None = None,
    expected_toolchain: set[str] | None = None,
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
    if len(execution_names) != 1:
        raise RuntimeError(
            "Trusted verification must have one successful execution step"
        )
    match = EVIDENCE_STEP.fullmatch(execution_names[0])
    if match is None:
        raise RuntimeError(
            "Trusted verification execution evidence is malformed"
        )
    tier, raw_scopes, claimed_tree, command = match.groups()
    scopes = raw_scopes.split(",")
    if required_tier is not None and required_tier not in VALID_TIERS:
        raise RuntimeError("Trusted verification required tier is invalid")
    if (
        tier not in VALID_TIERS
        or scopes != sorted(set(scopes))
        or any(scope not in VALID_SCOPES for scope in scopes)
        or (full_command if tier == "full" else "./scripts/verify-fast")
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
    successful_toolchain = [
        token for name in steps if (token := toolchain_token(name)) is not None
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
        "check_run_id": check_run.get("id"),
        "run_id": run_id,
        "job_id": job.get("id"),
        "repository": repo,
        "head_sha": head_sha,
        "tree_sha": tree_sha,
        "tier": tier,
        "scopes": scopes,
        "toolchain": successful_toolchain,
        "command": command,
        "completed_at": completed_at.isoformat(),
    }
