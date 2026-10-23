#!/usr/bin/env python3
"""Record and validate self-attested local verification evidence."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    csarc_config = importlib.import_module("csarc_config")
    evidence_freshness = importlib.import_module("evidence_freshness")
else:
    csarc_config = importlib.import_module(f"{__package__}.csarc_config")
    evidence_freshness = importlib.import_module(
        f"{__package__}.evidence_freshness"
    )

SCHEMA_VERSION = 1
SHA = re.compile(r"[0-9a-f]{40}")
VALID_TIERS = {"fast", "full"}
# One normalized verification record serves both trust modes. Only the trust
# label differs, so a reader can compare candidates without ever treating
# self-attested local evidence as trusted hosted evidence.
TRUST_LOCAL = "self-attested-local"
TRUST_HOSTED = "github-hosted"
RECORD_KEYS = frozenset(
    {
        "schema_version",
        "trust",
        "success",
        "head_sha",
        "tree_sha",
        "base_ref",
        "base_sha",
        "tier",
        "scopes",
        "command",
        "completed_at",
    }
)
RECORD_TIERS = {"docs", "fast", "full"}
TIER_RANK = {"fast": 0, "full": 1}
VALID_SCOPES = {
    "all",
    "dependency",
    "docs",
    "governance",
    "shell",
    "source",
    "template",
    "unknown",
    "workflow",
}


def normalized_record(evidence: dict[str, Any], trust: str) -> dict[str, Any]:
    """Project local or hosted evidence onto the shared record contract.

    Local evidence names its base `base_ref`; hosted evidence names it `base`
    and may omit it for legacy execution claims. Every other field and its
    validation are identical, and the trust label is kept as given.
    """
    if trust not in {TRUST_LOCAL, TRUST_HOSTED}:
        raise RuntimeError(f"Bad trust label: '{trust}' is unknown. Fix it.")
    declared = evidence.get("trust")
    if declared is not None and declared != trust:
        raise RuntimeError("Bad trust label: evidence differs. Rerun.")
    base_ref = evidence.get("base_ref", evidence.get("base"))
    base_sha = evidence.get("base_sha")
    scopes = evidence.get("scopes")
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "trust": trust,
        "success": True,
        "head_sha": evidence.get("head_sha"),
        "tree_sha": evidence.get("tree_sha"),
        "base_ref": base_ref,
        "base_sha": base_sha,
        "tier": evidence.get("tier"),
        "scopes": sorted(set(scopes)) if isinstance(scopes, list) else scopes,
        "command": evidence.get("command"),
        "completed_at": evidence.get("completed_at"),
    }
    legacy_hosted_base = trust == TRUST_HOSTED and not base_ref and not base_sha
    exact_base = (
        isinstance(base_ref, str)
        and bool(base_ref)
        and isinstance(base_sha, str)
        and SHA.fullmatch(base_sha) is not None
    )
    if (
        evidence.get("success", True) is not True
        or not isinstance(record["head_sha"], str)
        or SHA.fullmatch(record["head_sha"]) is None
        or not isinstance(record["tree_sha"], str)
        or SHA.fullmatch(record["tree_sha"]) is None
        or not (legacy_hosted_base or exact_base)
        or record["tier"] not in RECORD_TIERS
        or not isinstance(record["scopes"], list)
        or not record["scopes"]
        or not all(isinstance(scope, str) for scope in record["scopes"])
        or not isinstance(record["command"], str)
        or not record["command"]
        or not isinstance(record["completed_at"], str)
    ):
        raise RuntimeError("Bad evidence: a record field is invalid. Rerun.")
    try:
        completed_at = datetime.fromisoformat(record["completed_at"])
    except ValueError as error:
        raise RuntimeError(
            "Record completion time is malformed: not ISO 8601. Rerun it."
        ) from error
    if completed_at.tzinfo is None:
        raise RuntimeError("Bad completion time: it has no zone. Rerun.")
    return record


def git(*args: str) -> str:
    """Return one stripped Git result from the current repository."""
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def repository_root() -> Path:
    """Return the current repository root."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    parent = Path(__file__).resolve().parents[1]
    return parent.parent if parent.name == ".csarc" else parent


def is_git_repository() -> bool:
    """Return whether the current directory has commit metadata."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def config_path(root: Path) -> Path:
    """Return the single project configuration path."""
    return root / ".csarc" / "config.yml"


def evidence_path(head_sha: str) -> Path:
    """Keep per-commit evidence in Git metadata, outside the worktree."""
    if SHA.fullmatch(head_sha) is None:
        raise RuntimeError("Bad commit identity: it is not a SHA. Fix it.")
    common = Path(git("rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = repository_root() / common
    return (
        common.resolve() / "csarc" / "local-verification" / f"{head_sha}.json"
    )


def verification_mode(root: Path | None = None) -> str:
    """Return the configured verification trust mode."""
    target = root or repository_root()
    return str(
        csarc_config.load_config(config_path(target))["verification_mode"]
    )


def resolve_base(base: str = "") -> tuple[str, str]:
    """Resolve the configured pull-request base to one exact local commit."""
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD")
    selected = base.strip()
    if not selected:
        configured = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "git",
                "config",
                "--get",
                f"branch.{branch}.gh-merge-base",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        selected = configured.stdout.strip()
    if not selected:
        remote_head = subprocess.run(
            [  # noqa: S607
                "git",
                "symbolic-ref",
                "--quiet",
                "--short",
                "refs/remotes/origin/HEAD",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        selected = remote_head.stdout.strip()
    selected = selected.removeprefix("refs/heads/")
    selected = selected.removeprefix("refs/remotes/origin/")
    selected = selected.removeprefix("origin/")
    if not selected:
        raise RuntimeError("Base is unavailable: none is set. Pass '--base'.")
    for candidate in (
        f"refs/remotes/origin/{selected}",
        f"refs/heads/{selected}",
    ):
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "git",
                "rev-parse",
                "--verify",
                f"{candidate}^{{commit}}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return selected, result.stdout.strip()
    raise RuntimeError(f"Unknown base: '{selected}'. Run 'git fetch'.")


def record(
    tier: str,
    scopes: list[str],
    base: str = "",
    expected_head_sha: str = "",
    expected_base_sha: str = "",
) -> dict[str, Any] | None:
    """Write evidence only after a canonical local suite has succeeded."""
    root = repository_root()
    if verification_mode(root) != "local":
        return None
    if tier not in VALID_TIERS:
        raise RuntimeError(f"Tier is invalid: '{tier}'. Use 'fast' or 'full'.")
    normalized_scopes = sorted(set(scopes))
    if not normalized_scopes or any(
        scope not in VALID_SCOPES for scope in normalized_scopes
    ):
        raise RuntimeError("Bad scopes: one is unknown. Fix '--scopes'.")
    if (tier == "full" and normalized_scopes != ["all"]) or (
        tier == "fast" and "all" in normalized_scopes
    ):
        raise RuntimeError(
            "Local tier and scopes disagree: 'full' needs 'all'. Fix them."
        )
    if not is_git_repository():
        sys.stdout.write(
            "Local verification passed; evidence was not recorded because "
            "the candidate has no Git commit.\n"
        )
        return None
    if git("status", "--porcelain"):
        sys.stdout.write(
            "Local verification passed; evidence was not recorded because "
            "the worktree is not clean. Commit the exact candidate and run "
            "the suite once more.\n"
        )
        return None
    head_sha = git("rev-parse", "HEAD")
    if expected_head_sha and head_sha != expected_head_sha:
        raise RuntimeError("HEAD changed during verification: stale. Rerun.")
    tree_sha = git("rev-parse", "HEAD^{tree}")
    base_ref, base_sha = resolve_base(base)
    if expected_base_sha and base_sha != expected_base_sha:
        raise RuntimeError("Base changed during verification: stale. Rerun.")
    command_root = (
        ".csarc/scripts"
        if (root / ".csarc/scripts/verify").is_file()
        else "scripts"
    )
    command = (
        f"./{command_root}/verify"
        if tier == "full"
        else f"./{command_root}/verify-fast"
    )
    payload = normalized_record(
        {
            "head_sha": head_sha,
            "tree_sha": tree_sha,
            "base_ref": base_ref,
            "base_sha": base_sha,
            "tier": tier,
            "scopes": normalized_scopes,
            "command": command,
            # The canonical evidence contract (#1073) allows only
            # whole-second UTC times, so the merge can hash this payload
            # unchanged.
            "completed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        TRUST_LOCAL,
    )
    path = evidence_path(head_sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    sys.stdout.write(
        "Recorded self-attested local verification for "
        f"{head_sha} ({tier}; {','.join(normalized_scopes)}).\n"
    )
    return payload


def require(
    *,
    head_sha: str,
    tree_sha: str,
    base_ref: str,
    base_sha: str,
    required_tier: str,
    now: datetime | None = None,
    max_age_hours: float | None = None,
) -> dict[str, Any]:
    """Validate one exact local result without claiming trusted provenance."""
    # Issue #1075: reject a widened window before reading candidate evidence.
    max_age_hours = evidence_freshness.policy_max_age_hours(max_age_hours)
    if required_tier not in VALID_TIERS:
        raise RuntimeError("Bad required tier: it is unknown. Fix it.")
    if any(
        SHA.fullmatch(value) is None for value in (head_sha, tree_sha, base_sha)
    ):
        raise RuntimeError("Bad commit identity: it is not a SHA. Fix it.")
    path = evidence_path(head_sha)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Local evidence is unavailable: unreadable. Rerun verify."
        ) from error
    if not isinstance(payload, dict) or set(payload) != RECORD_KEYS:
        raise RuntimeError("Local evidence is malformed: bad keys. Rerun.")
    tier = payload.get("tier")
    scopes = payload.get("scopes")
    command = payload.get("command")
    expected_commands = {
        "fast": {
            "./scripts/verify-fast",
            "./.csarc/scripts/verify-fast",
        },
        "full": {"./scripts/verify", "./.csarc/scripts/verify"},
    }
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("trust") != TRUST_LOCAL
        or payload.get("success") is not True
        or payload.get("head_sha") != head_sha
        or payload.get("tree_sha") != tree_sha
        or payload.get("base_ref") != base_ref
        or payload.get("base_sha") != base_sha
        or tier not in VALID_TIERS
        or TIER_RANK[str(tier)] < TIER_RANK[required_tier]
        or not isinstance(scopes, list)
        or not scopes
        or scopes != sorted(set(scopes))
        or any(scope not in VALID_SCOPES for scope in scopes)
        or (tier == "full" and scopes != ["all"])
        or (tier == "fast" and "all" in scopes)
        or command not in expected_commands.get(str(tier), set())
    ):
        raise RuntimeError(
            "Local evidence does not match: wrong candidate. Rerun verify."
        )
    evidence_freshness.require_fresh(
        payload["completed_at"],
        subject="Local verification",
        now=now,
        max_age_hours=max_age_hours,
    )
    if (
        git("rev-parse", "HEAD") != head_sha
        or git("rev-parse", "HEAD^{tree}") != tree_sha
    ):
        raise RuntimeError("Bad current worktree: HEAD moved. Rerun.")
    if git("status", "--porcelain"):
        raise RuntimeError("Worktree is dirty: needs a clean worktree. Commit.")
    return payload


def main() -> None:
    """Record one successful canonical local suite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("record",))
    parser.add_argument("--tier", choices=sorted(VALID_TIERS), required=True)
    parser.add_argument("--scopes", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--base-sha", default="")
    args = parser.parse_args()
    try:
        record(
            args.tier,
            [scope for scope in args.scopes.split(",") if scope],
            args.base,
            args.head_sha,
            args.base_sha,
        )
    except (RuntimeError, subprocess.CalledProcessError) as error:
        sys.stderr.write(f"Local verification evidence blocked: {error}\n")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
