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
import json
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
CONFIG = ".csarc/config.yml"
PROVENANCE = ".csarc/provenance.json"
# Q12 (#1317): a registration may change only the settings, the
# provenance record the CLI rewrites, and the verify workflow render.
REGISTRATION_PATHS = {CONFIG, PROVENANCE, WORKFLOW}
UNREGISTERED_LABEL = "'csarc-vm-unregistered'"
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
    """Return the newest VM run that binds to the leased exact head."""
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
    error: RuntimeError | None = None
    for run in sorted(runs, key=lambda item: int(item.get("id") or 0))[::-1]:
        if str(lease["head_sha"]) not in str(run.get("display_title") or ""):
            continue
        jobs = github.collection(
            repo,
            f"actions/runs/{int(run['id'])}/jobs?filter=latest&per_page=100",
            "jobs",
        )
        try:
            return validate_run(
                run,
                jobs,
                repo=repo,
                lease=lease,
                config=config,
                required_tier=required_tier,
                now=now,
            )
        except RuntimeError as rejected:
            error = error or rejected
    raise error or RuntimeError(
        f"Self-hosted verification: no VM run on the exact head. {RERUN}."
    )


def git_reader(
    subject: Path, git: Callable[[list[str]], str] | None
) -> Callable[[list[str]], str]:
    """Return the Git reader that serves one candidate's objects."""
    return git or (
        lambda args: (
            subprocess.run(  # noqa: S603 - fixed git arguments
                ["git", "-C", str(subject), *args],  # noqa: S607
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
    )


def changed_paths(
    show: Callable[[list[str]], str], lease: dict[str, Any]
) -> list[str]:
    """Return every path the pull request touches.

    Rename detection would list only the new side of a move, so a file
    moved from product code into an allowed directory would look allowed;
    --no-renames lists both sides (#1317 review).
    """
    head, base_sha = lease["head_sha"], lease["base_sha"]
    return show(
        ["diff", "--no-renames", "--name-only", f"{base_sha}...{head}"]
    ).splitlines()


def candidate_config(
    show: Callable[[list[str]], str], head: str
) -> dict[str, object]:
    """Read the candidate settings with the trusted base reader."""
    with tempfile.TemporaryDirectory(prefix="csarc-exit-") as scratch:
        path = Path(scratch) / "config.yml"
        path.write_text(show(["show", f"{head}:{CONFIG}"]), encoding="utf-8")
        return csarc_config.load_config(path)


def differing_keys(
    base: dict[str, object], candidate: dict[str, object]
) -> set[str]:
    """Return the settings whose values differ."""
    return {
        key
        for key in {*base, *candidate}
        if base.get(key) != candidate.get(key)
    }


def settings_change(
    subject: Path,
    base_config: Path,
    lease: dict[str, Any],
    git: Callable[[list[str]], str] | None = None,
) -> tuple[dict[str, object], dict[str, object], set[str]] | None:
    """Return the base and candidate settings and the keys that differ.

    None means the pull request also changed a path outside the settings
    and their render directories, or the settings could not be read.
    """
    show = git_reader(subject, git)
    try:
        base = csarc_config.load_config(base_config)
        candidate = candidate_config(show, str(lease["head_sha"]))
        changed = changed_paths(show, lease)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None
    if not all(path.startswith(EXIT_PATHS) for path in changed):
        return None
    return base, candidate, differing_keys(base, candidate)


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
    change = settings_change(subject, base_config, lease, git)
    if change is None:
        return ""
    base, candidate, differing = change
    after = candidate.get("verification_mode_private")
    if (
        base.get("verification_mode_private") != "self-hosted"
        or after == "self-hosted"
        or not differing <= EXIT_KEYS
    ):
        return ""
    return (
        f"the pull request only switches verification_mode_private from "
        f"self-hosted to {after} (ADR Q1)"
    )


def options_block(environments: object) -> str:
    """Return the rendered environment choices of the verify workflow."""
    if not isinstance(environments, list) or not environments:
        raise ValueError(
            "Self-hosted registration: no environments are listed. "
            "Register dev, uat, or both."
        )
    return "        options:\n" + "".join(
        f"          - {env}\n" for env in environments
    )


def registered_workflow(
    before: str,
    runner_id: str,
    base: dict[str, object],
    candidate: dict[str, object],
) -> str:
    """Return the verify workflow a registration render produces.

    The render differs from the unregistered one only in the runner label
    and the environment choices (csarc-verify.yml.jinja); every other byte
    must stay as the trusted base has it.
    """
    old_options = options_block(base.get("self_hosted_environments"))
    if before.count(UNREGISTERED_LABEL) != 1 or before.count(old_options) != 1:
        raise ValueError(
            "Self-hosted registration: the base workflow is not an "
            "unregistered render. Restore csarc-verify.yml first."
        )
    return before.replace(
        UNREGISTERED_LABEL, f"'csarc-vm-{runner_id}'"
    ).replace(
        old_options,
        options_block(candidate.get("self_hosted_environments")),
    )


def same_provenance(before: str, after: str) -> bool:
    """Return whether provenance changed only as a settings rewrite does.

    The CLI rewrites the time, the previous record, the plan digest, and
    the settings record; the settings context may differ only in the
    self-hosted settings. The file is data the CLI reads, never code.
    """
    old, new = json.loads(before), json.loads(after)
    if not isinstance(old, dict) or not isinstance(new, dict):
        return False
    volatile = {"applied_at", "previous", "final_plan_sha256", "settings"}
    if any(old.get(key) != new.get(key) for key in {*old, *new} - volatile):
        return False
    old_settings, new_settings = old.get("settings"), new.get("settings")
    if old_settings is None and new_settings is None:
        return True
    if not isinstance(old_settings, dict) or not isinstance(new_settings, dict):
        return False
    digests = {"config_sha256", "context_sha256", "record_sha256", "context"}
    old_context, new_context = (
        old_settings.get("context"),
        new_settings.get("context"),
    )
    return (
        isinstance(old_context, dict)
        and isinstance(new_context, dict)
        and differing_keys(old_context, new_context)
        <= set(csarc_config.SELF_HOSTED_KEYS)
        and all(
            old_settings.get(key) == new_settings.get(key)
            for key in {*old_settings, *new_settings} - digests
        )
    )


def registration_reason(
    subject: Path,
    base_config: Path,
    lease: dict[str, Any],
    git: Callable[[list[str]], str] | None = None,
) -> str:
    """Return why a first registration may merge on local evidence.

    ADR D2/Q12 (#1317): a new project starts self-hosted with an empty
    self_hosted_runner, so no VM evidence can exist yet. Only a pull
    request that keeps self-hosted, fills the empty runner, changes no
    other setting, and changes no file beyond what that settings change
    renders qualifies. A pull request that is not a registration returns
    ''; a registration that carries anything more raises, so it fails
    closed with the reason.
    """
    show = git_reader(subject, git)
    head, base_sha = str(lease["head_sha"]), str(lease["base_sha"])
    try:
        base = csarc_config.load_config(base_config)
        candidate = candidate_config(show, head)
        changed = changed_paths(show, lease)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return ""
    runner = candidate.get("self_hosted_runner")
    differing = differing_keys(base, candidate)
    if (
        base.get("verification_mode_private") != "self-hosted"
        or candidate.get("verification_mode_private") != "self-hosted"
        or base.get("self_hosted_runner")
        or not isinstance(runner, dict)
        or not runner
        or "self_hosted_runner" not in differing
        or not differing <= set(csarc_config.SELF_HOSTED_KEYS)
    ):
        return ""
    rejected = [path for path in changed if path not in REGISTRATION_PATHS]
    for path in sorted(set(changed) & {WORKFLOW, PROVENANCE}):
        try:
            before = show(["show", f"{base_sha}:{path}"])
            after = show(["show", f"{head}:{path}"])
            same = (
                after
                == registered_workflow(
                    before, str(runner["id"]), base, candidate
                )
                if path == WORKFLOW
                else same_provenance(before, after)
            )
        except (ValueError, subprocess.CalledProcessError):
            same = False
        if not same:
            rejected.append(path)
    if rejected:
        raise RuntimeError(
            "Self-hosted registration: "
            + ", ".join(rejected)
            + " changes more than registering self_hosted_runner renders "
            "(ADR Q12). Keep only the settings and their render in this "
            "pull request; verify the rest on the VM afterwards."
        )
    return (
        f"the pull request only registers self_hosted_runner {runner['id']} "
        f"({runner['registration']}) on an unregistered self-hosted base "
        "(ADR Q12)"
    )


def trace_lines(snapshot: dict[str, object], suffix: str) -> list[str]:
    """Return the merge-trace lines for VM evidence, Q1 exit, or Q12."""
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
    reason = snapshot.get("self_hosted_registration")
    if reason:
        return [
            f"self-hosted-registration-trace: {suffix} trust="
            f"{evidence_freshness.TRUST_LOCAL} because {reason}"
        ]
    return []
