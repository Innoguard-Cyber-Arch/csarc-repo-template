#!/usr/bin/env python3
"""Read registered self-hosted VM verification evidence for one merge.

ADR self-hosted-verification D4 and D6 L6 (Issue #1269): an operator
dispatches `csarc-verify.yml` on the pull request's target branch, and the
registered VM runs it. Before a merge, `pr_lifecycle.py` reads that run back
through the Actions run and Jobs APIs and accepts it only when GitHub
recorded every binding below. Only self-hosted renders ship this file.
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
import tempfile
import urllib.parse
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    csarc_config = importlib.import_module("csarc_config")
    evidence_freshness = importlib.import_module("evidence_freshness")
else:
    csarc_config = importlib.import_module(f"{__package__}.csarc_config")
    evidence_freshness = importlib.import_module(
        f"{__package__}.evidence_freshness"
    )

WORKFLOW = ".github/workflows/csarc-verify.yml"
CHECK_STEP = "Check the dispatch before any candidate code"
EXECUTE = re.compile(
    r"Execute self-hosted verification head=(?P<head>[0-9a-f]{40}) "
    r"tree=(?P<tree>[0-9a-f]{40}) tier=(?P<tier>fast|full) "
    r"scopes=(?P<scopes>[a-z]+(?:,[a-z]+)*) mode=self-hosted "
    r"environment=(?P<environment>dev|uat) "
    r"window=(?P<window>\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?Z)"
)
TIER_RANK = {"fast": 0, "full": 1}
# Q1: a pull request that leaves self-hosted may change only these settings
# and the files that a render in the new mode replaces.
EXIT_KEYS = {"verification_mode_private", *csarc_config.SELF_HOSTED_KEYS}
EXIT_PATHS = (".csarc/", ".github/", "AGENTS.md")
RERUN = "Dispatch csarc-verify.yml for the exact head"


class Reader(Protocol):
    """The one GitHub read that the evidence lookup needs."""

    def collection(
        self, repo: str, path: str, key: str
    ) -> list[dict[str, Any]]:
        """Read one keyed REST collection across every page."""
        ...


def environment(base_ref: str) -> str:
    """Return the environment a target branch needs (ADR D5), or ''."""
    if base_ref == "main":
        return "uat"
    return "dev" if re.fullmatch(r"dev/[mi].+", base_ref) else ""


def runner_identity(vm: str, env: str) -> tuple[str, list[str]]:
    """Return the runner name and labels derived from the registration."""
    return f"csarc-{vm}-{env}", sorted(
        {"self-hosted", f"csarc-vm-{vm}", f"csarc-env-{env}"}
    )


def stamp(value: object) -> str:
    """Normalize one GitHub timestamp to the evidence second form."""
    parsed = evidence_freshness.completion_time(value, "Self-hosted run")
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def unregistered() -> RuntimeError:
    """Return the registration guidance error (SPEC-011)."""
    return RuntimeError(
        "Self-hosted verification: no registered VM evidence. Register with "
        "csarc-devops, then add self_hosted_runner through a "
        "governance-switch pull request."
    )


def validate_run(
    run: dict[str, Any],
    jobs: list[dict[str, Any]],
    *,
    repo: str,
    lease: dict[str, Any],
    config: dict[str, object],
    required_tier: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return canonical evidence for one run, or raise why it does not bind."""
    base_ref = str(lease["base_ref"])
    env = environment(base_ref)
    runner = config.get("self_hosted_runner")
    if not isinstance(runner, dict) or not runner:
        raise unregistered()
    registered = config.get("self_hosted_environments")
    if not env or not isinstance(registered, list) or env not in registered:
        raise RuntimeError(
            f"Self-hosted verification: {base_ref} needs a registered "
            f"'{env or 'dev or uat'}' environment. Register it first."
        )
    name, labels = runner_identity(str(runner["id"]), env)

    def field(item: object, *keys: str) -> object:
        for key in keys:
            item = item.get(key) if isinstance(item, dict) else None
        return item

    checks = (
        (run.get("event") == "workflow_dispatch", "not a workflow_dispatch"),
        (run.get("path") == WORKFLOW, f"not {WORKFLOW}"),
        (
            run.get("head_branch") == base_ref
            and run.get("head_sha") == lease["base_sha"],
            "not the target branch's trusted base definition",
        ),
        (
            field(run, "repository", "full_name") == repo
            and field(run, "head_repository", "full_name") == repo,
            "not this repository",
        ),
        (
            run.get("status") == "completed"
            and run.get("conclusion") == "success",
            "the run did not succeed",
        ),
        (len(jobs) == 1, "not exactly one job"),
    )
    for passed, reason in checks:
        if not passed:
            raise RuntimeError(f"Self-hosted run: {reason}. {RERUN}.")
    job = jobs[0]
    steps = [step for step in job.get("steps") or [] if isinstance(step, dict)]
    names = [str(step.get("name") or "") for step in steps]
    executed = [
        (match, step)
        for step in steps
        if (match := EXECUTE.fullmatch(str(step.get("name") or "")))
    ]
    job_checks = (
        (
            job.get("status") == "completed"
            and job.get("conclusion") == "success",
            "the job did not succeed",
        ),
        (
            sorted(str(label) for label in job.get("labels") or []) == labels,
            f"labels are not {','.join(labels)}",
        ),
        (job.get("runner_name") == name, f"runner is not {name}"),
        (job.get("runner_group_name") == "Default", "runner group not Default"),
        (
            CHECK_STEP in names
            and len(executed) == 1
            and names.index(CHECK_STEP) < steps.index(executed[0][1])
            and all(
                step.get("conclusion") == "success"
                for step in (steps[names.index(CHECK_STEP)], executed[0][1])
            ),
            "no successful dispatch check and execution step",
        ),
    )
    for passed, reason in job_checks:
        if not passed:
            raise RuntimeError(f"Self-hosted job: {reason}. {RERUN}.")
    match = executed[0][0]
    if (
        match["head"] != lease["head_sha"]
        or match["tree"] != lease["head_tree"]
        or match["environment"] != env
        or TIER_RANK[match["tier"]] < TIER_RANK[required_tier]
    ):
        raise RuntimeError(
            "Self-hosted evidence: not the exact head, tree, environment, or "
            f"{required_tier} tier. {RERUN}."
        )
    completed = stamp(job.get("completed_at"))
    evidence_freshness.require_fresh(
        completed, subject="Self-hosted verification", now=now
    )
    return {
        "schema_version": 1,
        "trust": evidence_freshness.TRUST_SELF_HOSTED,
        "success": True,
        "repository": {"full_name": repo},
        "head_sha": match["head"],
        "tree_sha": match["tree"],
        "base_ref": base_ref,
        "base_sha": str(lease["base_sha"]),
        "tier": match["tier"],
        "scopes": sorted(set(match["scopes"].split(","))),
        "command": "./.csarc/scripts/"
        + ("verify" if match["tier"] == "full" else "verify-fast"),
        "mode": "self-hosted",
        "environment": env,
        "window": match["window"],
        "runner_labels": labels,
        "executor": {
            "kind": evidence_freshness.TRUST_SELF_HOSTED,
            "run_url": str(run.get("html_url") or ""),
            "run_id": run.get("id"),
            "run_attempt": run.get("run_attempt"),
            "job_id": job.get("id"),
            "runner_name": name,
            "runner_group": "Default",
            "actor": str(field(run, "actor", "login") or ""),
            "triggering_actor": str(
                field(run, "triggering_actor", "login") or ""
            ),
        },
        "started_at": stamp(job.get("started_at")),
        "completed_at": completed,
    }


def require(
    github: Reader,
    repo: str,
    lease: dict[str, Any],
    pull: dict[str, Any],
    config_path: Path,
    required_tier: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return evidence from the newest VM run on the leased exact head."""
    config = csarc_config.load_config(config_path)
    if not config.get("self_hosted_runner"):
        raise unregistered()
    head_repo = (pull.get("head") or {}).get("repo") or {}
    if head_repo.get("full_name") != repo:
        raise RuntimeError(
            "Self-hosted verification: the head is a fork. Fork pull "
            "requests never run on the VM."
        )
    query = urllib.parse.urlencode(
        {
            "event": "workflow_dispatch",
            "branch": lease["base_ref"],
            "head_sha": lease["base_sha"],
            "per_page": 100,
        }
    )
    runs = github.collection(
        repo,
        f"actions/workflows/csarc-verify.yml/runs?{query}",
        "workflow_runs",
    )
    # Issue #1319: only the newest run for this head and base counts. A
    # newer failed, cancelled, or unfinished run voids any older success.
    bound = [
        run
        for run in runs
        if str(lease["head_sha"]) in str(run.get("display_title") or "")
    ]
    if not bound:
        raise RuntimeError(
            f"Self-hosted verification: no VM run on the exact head. {RERUN}."
        )
    run = max(bound, key=lambda item: int(item.get("id") or 0))
    status, conclusion = run.get("status"), run.get("conclusion")
    if status != "completed" or conclusion != "success":
        raise RuntimeError(
            f"Self-hosted verification: the newest VM run on the exact head "
            f"(run {run.get('id')}) is {status}/{conclusion or 'none'}, so "
            f"older runs do not count. {RERUN} to re-verify."
        )
    jobs = github.collection(
        repo,
        f"actions/runs/{int(run['id'])}/jobs?filter=latest&per_page=100",
        "jobs",
    )
    return validate_run(
        run,
        jobs,
        repo=repo,
        lease=lease,
        config=config,
        required_tier=required_tier,
        now=now,
    )


def exit_reason(
    subject: Path,
    base_config: Path,
    lease: dict[str, Any],
    git: Callable[[list[str]], str] | None = None,
) -> str:
    """Return why a pull request may leave self-hosted on local evidence.

    ADR D10/Q1: only a pull request that switches verification_mode_private
    away from self-hosted, and changes nothing but that setting, its
    registration, and the files a new render replaces, qualifies. Anything
    else returns '' and keeps requiring VM evidence.
    """
    show = git or (
        lambda args: (
            subprocess.run(  # noqa: S603 - fixed git arguments
                ["git", "-C", str(subject), *args],  # noqa: S607
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
    )
    try:
        base = csarc_config.load_config(base_config)
        with tempfile.TemporaryDirectory(prefix="csarc-exit-") as scratch:
            path = Path(scratch) / "config.yml"
            path.write_text(
                show(["show", f"{lease['head_sha']}:.csarc/config.yml"]),
                encoding="utf-8",
            )
            candidate = csarc_config.load_config(path)
        head, base_sha = lease["head_sha"], lease["base_sha"]
        changed = show(["diff", "--name-only", f"{base_sha}...{head}"])
    except (OSError, ValueError, subprocess.CalledProcessError):
        return ""
    after = candidate.get("verification_mode_private")
    differing = {
        key
        for key in {*base, *candidate}
        if base.get(key) != candidate.get(key)
    }
    if (
        base.get("verification_mode_private") != "self-hosted"
        or after == "self-hosted"
        or not differing <= EXIT_KEYS
        or not all(path.startswith(EXIT_PATHS) for path in changed.splitlines())
    ):
        return ""
    return (
        f"the pull request only switches verification_mode_private from "
        f"self-hosted to {after} (ADR Q1)"
    )


def trace_lines(snapshot: dict[str, object], suffix: str) -> list[str]:
    """Return the merge-trace lines for VM evidence or the Q1 exit."""
    evidence = snapshot.get("self_hosted_verification")
    if isinstance(evidence, dict):
        executor = evidence["executor"]
        return [
            "self-hosted-verification-trace: "
            f"run={executor['run_url']} actor={executor['actor']} "
            f"triggering_actor={executor['triggering_actor']} "
            f"runner={executor['runner_name']} "
            f"environment={evidence['environment']} "
            f"window={evidence['window']} mode=self-hosted "
            f"head={evidence['head_sha']} tier={evidence['tier']} {suffix} "
            f"trust={evidence_freshness.TRUST_SELF_HOSTED}"
        ]
    reason = snapshot.get("self_hosted_exit")
    if reason:
        return [
            f"self-hosted-exit-trace: {suffix} trust="
            f"{evidence_freshness.TRUST_LOCAL} because {reason}"
        ]
    return []
