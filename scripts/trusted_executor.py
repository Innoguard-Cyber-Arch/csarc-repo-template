#!/usr/bin/env python3
"""Stage the trusted-base verification executor and compare candidate gates.

Hosted `verify` runs from `pull_request_target`, so its workflow YAML always
comes from the default branch. Issue #1086: the files that decide what the
required result means -- the entry points, the stage gate, the path router,
and the configuration reader -- must also come from the trusted pull request
base instead of the candidate. `prepare` copies exactly that control set out
of the trusted base checkout before the candidate is checked out; the hosted
job then runs the staged entry point with `CSARC_VERIFICATION_SUBJECT_ROOT`
pointing at the exact candidate tree, so the checks themselves (tests, lint,
scans) still exercise the candidate's code.

`self-test` runs only after the authoritative result exists. It compares the
candidate's own router and configuration reader with the trusted decision and
labels every difference as non-authoritative; it always exits 0 so candidate
code can never decide the required result through it.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

EXECUTOR_TRUSTED = "trusted-base"
EXECUTOR_LEGACY = "candidate-legacy"
CONTROL_FILES = (
    "scripts/ci_tier.py",
    "scripts/csarc_config.py",
    "scripts/resolve-cache-root",
    "scripts/verification-step",
    "scripts/verify-fast",
    "scripts/verify-template.sh",
)
CONTROL_GLOBS = ("scripts/verify-stage-*",)
MANIFEST = "trusted-executor.json"


def control_paths(root: Path) -> list[str]:
    """Return the sorted relative control-set paths present under `root`."""
    paths = set(CONTROL_FILES)
    for pattern in CONTROL_GLOBS:
        paths.update(
            path.relative_to(root).as_posix()
            for path in root.glob(pattern)
            if path.is_file()
        )
    return sorted(paths)


def is_control_path(path: str) -> bool:
    """Return whether one repository path belongs to the control set."""
    return path in CONTROL_FILES or (
        path.startswith("scripts/verify-stage-") and "/" not in path[8:]
    )


def digest(path: Path) -> str:
    """Return the SHA-256 digest of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source: Path, destination: Path) -> dict[str, str]:
    """Copy the trusted control set and record its manifest.

    The copy fails closed: a missing control file, a symbolic link, or an
    existing destination never produces a partially trusted executor.
    """
    source = source.resolve()
    if destination.exists():
        raise RuntimeError(f"Trusted executor already exists: {destination}")
    files: dict[str, str] = {}
    for relative in control_paths(source):
        origin = source / relative
        if origin.is_symlink() or not origin.is_file():
            raise RuntimeError(
                f"Trusted control file is missing or not a regular file: "
                f"{relative}"
            )
        files[relative] = digest(origin)
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
        # Keep the trusted copy read-only so an accidental candidate write
        # fails loudly; this is not a sandbox against hostile test code.
        target.chmod(
            stat.S_IMODE(target.stat().st_mode)
            & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        )
    manifest = {"executor": EXECUTOR_TRUSTED, "files": files}
    (destination / MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return files


def verify_manifest(destination: Path) -> None:
    """Fail closed when the staged control set no longer matches its digest."""
    manifest = json.loads((destination / MANIFEST).read_text(encoding="utf-8"))
    files = manifest.get("files")
    if manifest.get("executor") != EXECUTOR_TRUSTED or not isinstance(
        files, dict
    ):
        raise RuntimeError("Trusted executor manifest is malformed")
    for relative, expected in files.items():
        if digest(destination / relative) != expected:
            raise RuntimeError(f"Trusted control file changed: {relative}")


def load_plan(path: Path) -> dict[str, object] | None:
    """Read one router plan, or None when the candidate produced none."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def self_test_report(
    *,
    trusted_plan: dict[str, object] | None,
    candidate_plan: dict[str, object] | None,
    trusted_ownership: str,
    candidate_ownership: str,
    changed_files: list[str],
) -> list[str]:
    """Describe candidate-versus-trusted differences as non-authoritative."""
    lines = [
        "Candidate gate self-test (non-authoritative): the trusted-base "
        "executor already decided the required result; nothing below can "
        "change it.",
    ]
    changed_gate = sorted(
        path for path in changed_files if is_control_path(path)
    )
    if changed_gate:
        lines.append(
            "Candidate changes trusted control files (effective only after "
            "merge): " + ", ".join(changed_gate)
        )
    if trusted_plan is None:
        lines.append("Trusted plan is unavailable; no comparison was made.")
        return lines
    if candidate_plan is None:
        lines.append("Candidate router produced no readable plan.")
    else:
        for key in ("tier", "scopes", "run_project"):
            trusted_value = trusted_plan.get(key)
            candidate_value = candidate_plan.get(key)
            if trusted_value != candidate_value:
                lines.append(
                    f"Router difference {key}: trusted={trusted_value!r} "
                    f"candidate={candidate_value!r}"
                )
    if trusted_ownership != candidate_ownership:
        lines.append(
            "Config reader difference release_ownership: "
            f"trusted={trusted_ownership!r} candidate={candidate_ownership!r}"
        )
    if len(lines) == 1 + bool(changed_gate):
        lines.append("Candidate router and config reader agree with trusted.")
    return lines


# File-command and credential variables never reach candidate self-test code,
# so it cannot set environment, PATH, or outputs for later steps.
SCRUBBED_ENVIRONMENT = (
    "GH_TOKEN",
    "GITHUB_ENV",
    "GITHUB_OUTPUT",
    "GITHUB_PATH",
    "GITHUB_STATE",
    "GITHUB_STEP_SUMMARY",
    "GITHUB_TOKEN",
)


def candidate_environment() -> dict[str, str]:
    """Return the environment handed to candidate self-test code."""
    return {
        key: value
        for key, value in os.environ.items()
        if key not in SCRUBBED_ENVIRONMENT
        and not key.startswith(("ACTIONS_", "CSARC_VERIFICATION_"))
    }


def run_candidate_gate(
    candidate_root: Path, router_args: list[str], *, timeout: float = 120.0
) -> tuple[dict[str, object] | None, str]:
    """Run the candidate's router and config reader without authority."""
    environment = candidate_environment()
    with tempfile.TemporaryDirectory(prefix="candidate-gate-") as scratch:
        output = Path(scratch) / "plan.json"
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(  # noqa: S603 - candidate self-test, no authority
                [
                    sys.executable,
                    str(candidate_root / "scripts" / "ci_tier.py"),
                    *router_args,
                    "--output-json",
                    str(output),
                ],
                cwd=candidate_root,
                env=environment,
                check=False,
                capture_output=True,
                timeout=timeout,
            )
        plan = load_plan(output)
    try:
        reader = subprocess.run(  # noqa: S603 - candidate self-test
            [
                sys.executable,
                str(candidate_root / "scripts" / "csarc_config.py"),
                "release_ownership",
            ],
            cwd=candidate_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except OSError, subprocess.SubprocessError:
        return plan, "unavailable"
    ownership = reader.stdout.strip() if reader.returncode == 0 else ""
    return plan, ownership or "unavailable"


def read_router_args(path: Path) -> list[str]:
    """Read the NUL-terminated trusted router arguments to replay.

    Empty arguments (for example `--labels ""`) are kept; only the final
    terminator is dropped.
    """
    raw = path.read_bytes()
    if not raw.endswith(b"\0"):
        raise ValueError("Router arguments must be NUL-terminated")
    return [item.decode("utf-8") for item in raw[:-1].split(b"\0")]


def read_changed_files(path: Path | None) -> list[str]:
    """Read a NUL-separated changed-file list when one is available."""
    if path is None:
        return []
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    return [
        item.decode("utf-8", "replace") for item in raw.split(b"\0") if item
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("prepare", help="stage the trusted executor")
    stage.add_argument("--source", type=Path, required=True)
    stage.add_argument("--destination", type=Path, required=True)
    check = commands.add_parser("verify", help="check the staged digests")
    check.add_argument("--destination", type=Path, required=True)
    compare = commands.add_parser(
        "self-test", help="report candidate gate differences"
    )
    compare.add_argument("--candidate-root", type=Path, required=True)
    compare.add_argument("--router-args", type=Path, required=True)
    compare.add_argument("--trusted-plan", type=Path, required=True)
    compare.add_argument("--trusted-ownership", default="")
    compare.add_argument("--changed-files", type=Path)
    compare.add_argument("--summary", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run one trusted-executor command."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "prepare":
        try:
            files = prepare(args.source, args.destination)
        except (OSError, RuntimeError) as error:
            sys.stderr.write(f"{error}\n")
            return 1
        count = len(files)
        sys.stdout.write(
            f"Staged {count} trusted control files in {args.destination}\n"
        )
        return 0
    if args.command == "verify":
        try:
            verify_manifest(args.destination)
        except (OSError, RuntimeError, ValueError) as error:
            sys.stderr.write(f"{error}\n")
            return 1
        return 0
    try:
        router_args = read_router_args(args.router_args)
    except OSError, ValueError:
        router_args = None
    if router_args is None:
        candidate_plan, candidate_ownership = None, "unavailable"
    else:
        candidate_plan, candidate_ownership = run_candidate_gate(
            args.candidate_root.resolve(), router_args
        )
    lines = self_test_report(
        trusted_plan=load_plan(args.trusted_plan),
        candidate_plan=candidate_plan,
        trusted_ownership=args.trusted_ownership,
        candidate_ownership=candidate_ownership,
        changed_files=read_changed_files(args.changed_files),
    )
    for line in lines:
        sys.stdout.write(f"::notice title=Candidate gate self-test::{line}\n")
    if args.summary is not None:
        with args.summary.open("a", encoding="utf-8") as summary:
            summary.write(
                "### Candidate gate self-test (non-authoritative)\n\n"
            )
            summary.writelines(f"- {line}\n" for line in lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
