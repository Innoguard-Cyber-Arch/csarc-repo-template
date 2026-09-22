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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    csarc_config = importlib.import_module("csarc_config")
else:
    csarc_config = importlib.import_module(f"{__package__}.csarc_config")

SCHEMA_VERSION = 1
SHA = re.compile(r"[0-9a-f]{40}")
VALID_TIERS = {"fast", "full"}
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
        raise RuntimeError("Local verification commit identity is malformed")
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
        raise RuntimeError("Local verification base is unavailable")
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
    raise RuntimeError(f"Local verification base '{selected}' is unavailable")


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
        raise RuntimeError(f"Invalid local verification tier: {tier}")
    normalized_scopes = sorted(set(scopes))
    if not normalized_scopes or any(
        scope not in VALID_SCOPES for scope in normalized_scopes
    ):
        raise RuntimeError("Invalid local verification scopes")
    if (tier == "full" and normalized_scopes != ["all"]) or (
        tier == "fast" and "all" in normalized_scopes
    ):
        raise RuntimeError("Local verification tier and scopes disagree")
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
        raise RuntimeError("HEAD changed while local verification was running")
    tree_sha = git("rev-parse", "HEAD^{tree}")
    base_ref, base_sha = resolve_base(base)
    if expected_base_sha and base_sha != expected_base_sha:
        raise RuntimeError("Base changed while local verification was running")
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
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "trust": "self-attested-local",
        "success": True,
        "head_sha": head_sha,
        "tree_sha": tree_sha,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "tier": tier,
        "scopes": normalized_scopes,
        "command": command,
        "completed_at": datetime.now(UTC).isoformat(),
    }
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


def require(  # noqa: C901
    *,
    head_sha: str,
    tree_sha: str,
    base_ref: str,
    base_sha: str,
    required_tier: str,
    now: datetime | None = None,
    max_age_hours: float = 24.0,
) -> dict[str, Any]:
    """Validate one exact local result without claiming trusted provenance."""
    if required_tier not in VALID_TIERS:
        raise RuntimeError("Required local verification tier is invalid")
    if any(
        SHA.fullmatch(value) is None for value in (head_sha, tree_sha, base_sha)
    ):
        raise RuntimeError("Local verification commit identity is malformed")
    path = evidence_path(head_sha)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Self-attested local verification evidence is unavailable"
        ) from error
    expected_keys = {
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
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise RuntimeError("Local verification evidence is malformed")
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
        or payload.get("trust") != "self-attested-local"
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
            "Local verification evidence does not match the candidate"
        )
    try:
        completed_at = datetime.fromisoformat(str(payload["completed_at"]))
    except ValueError as error:
        raise RuntimeError(
            "Local verification completion time is malformed"
        ) from error
    if completed_at.tzinfo is None:
        raise RuntimeError("Local verification completion time has no timezone")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    completed_at = completed_at.astimezone(UTC)
    if completed_at > current + timedelta(minutes=5):
        raise RuntimeError(
            "Local verification completion time is in the future"
        )
    if completed_at < current - timedelta(hours=max_age_hours):
        raise RuntimeError("Local verification evidence is stale")
    if (
        git("rev-parse", "HEAD") != head_sha
        or git("rev-parse", "HEAD^{tree}") != tree_sha
    ):
        raise RuntimeError("The current worktree is not the verified candidate")
    if git("status", "--porcelain"):
        raise RuntimeError("Local verification requires a clean worktree")
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
