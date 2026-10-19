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

Issue #1069 (G2) extends the same boundary to merges and to generated
projects. This file is byte-identical in the template repository
(`scripts/`) and in generated projects (`.csarc/scripts/`), and it also owns
the base-commit policy: a read-only, fail-closed reader for the current
configuration schema (SPEC-009 schema 2, Issue #1071, through the shared
current-only `csarc_config` parser), the governance-switch route for changes to
`.csarc/scripts` or relaxed governance values, the release-channel
verification floor, and the materialized trusted base the local lifecycle
re-executes from. Candidate copies of these rules only ever run as a
non-authoritative self-test.

Issue #1106: the guided release candidate check (`release/v*` into the
default branch) also decides a required result, so `prepare --control-set
release` stages its entry point and every Python module beside it from the
same trusted base. The hosted job then validates the exact candidate tree
with that copy, and candidate code never runs in the step that holds a token.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    csarc_config = importlib.import_module("csarc_config")
else:
    csarc_config = importlib.import_module(f"{__package__}.csarc_config")

EXECUTOR_TRUSTED = "trusted-base"
EXECUTOR_LEGACY = "candidate-legacy"
CONTROL_FILES = (
    "scripts/ci_tier.py",
    "scripts/csarc_config.py",
    "scripts/resolve-cache-root",
    "scripts/trusted_executor.py",
    "scripts/verification-step",
    "scripts/verify-fast",
    "scripts/verify-template.sh",
)
CONTROL_GLOBS = ("scripts/verify-stage-*",)
# Generated projects keep the same control set under .csarc/scripts, with
# `verify` as their full entry point (Issue #1069).
GENERATED_SCRIPTS = ".csarc/scripts"
GENERATED_CONTROL_FILES = (
    ".csarc/scripts/ci_tier.py",
    ".csarc/scripts/csarc_config.py",
    ".csarc/scripts/resolve-cache-root",
    ".csarc/scripts/trusted_executor.py",
    ".csarc/scripts/verification-step",
    ".csarc/scripts/verify",
    ".csarc/scripts/verify-fast",
)
MANIFEST = "trusted-executor.json"
# Issue #1106: the release control set is the guided candidate entry point
# plus every Python module in the same directory, so a module it loads
# indirectly can never fall back to a candidate copy.
RELEASE_ENTRY = "verify-release-candidate"
CONTROL_SET_VERIFICATION = "verification"
CONTROL_SET_RELEASE = "release"
CONTROL_SETS = (CONTROL_SET_VERIFICATION, CONTROL_SET_RELEASE)


def scripts_prefix(root: Path) -> str:
    """Return the control-script directory for the repository layout."""
    return (
        GENERATED_SCRIPTS
        if (root / GENERATED_SCRIPTS).is_dir()
        and not (root / "scripts" / "verify-template.sh").is_file()
        else "scripts"
    )


def release_control_paths(root: Path) -> list[str]:
    """Return the guided release candidate control set under `root`."""
    prefix = scripts_prefix(root)
    paths = {f"{prefix}/{RELEASE_ENTRY}"}
    paths.update(
        path.relative_to(root).as_posix()
        for path in (root / prefix).glob("*.py")
    )
    return sorted(paths)


def control_paths(
    root: Path, control_set: str = CONTROL_SET_VERIFICATION
) -> list[str]:
    """Return the sorted relative control-set paths present under `root`."""
    if control_set == CONTROL_SET_RELEASE:
        return release_control_paths(root)
    if control_set != CONTROL_SET_VERIFICATION:
        raise RuntimeError(f"Unknown trusted control set: {control_set}")
    if scripts_prefix(root) == GENERATED_SCRIPTS:
        return sorted(GENERATED_CONTROL_FILES)
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
    return (
        path in CONTROL_FILES
        or path in GENERATED_CONTROL_FILES
        or (path.startswith("scripts/verify-stage-") and "/" not in path[8:])
    )


def digest(path: Path) -> str:
    """Return the SHA-256 digest of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(
    source: Path,
    destination: Path,
    control_set: str = CONTROL_SET_VERIFICATION,
) -> dict[str, str]:
    """Copy the trusted control set and record its manifest.

    The copy fails closed: a missing control file, a symbolic link, or an
    existing destination never produces a partially trusted executor.
    """
    source = source.resolve()
    if destination.exists():
        raise RuntimeError(f"Trusted executor already exists: {destination}")
    files: dict[str, str] = {}
    for relative in control_paths(source, control_set):
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
    except (OSError, json.JSONDecodeError):
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
    prefix = scripts_prefix(candidate_root)
    with tempfile.TemporaryDirectory(prefix="candidate-gate-") as scratch:
        output = Path(scratch) / "plan.json"
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(  # noqa: S603 - candidate self-test, no authority
                [
                    sys.executable,
                    str(candidate_root / prefix / "ci_tier.py"),
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
                str(candidate_root / prefix / "csarc_config.py"),
                "release_ownership",
            ],
            cwd=candidate_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
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


# ---------------------------------------------------------------------------
# Issue #1069 (G2): base-commit policy shared by hosted and local gates.
# ---------------------------------------------------------------------------

SCHEMA_KEY = csarc_config.SCHEMA_KEY
# Issue #1071 (Q1) switched the writer to schema 2 only after this reader
# could validate it. The reader is current-only: legacy schemas are read by
# the pinned CLI's migration registry, never by repository scripts, and a
# later schema must first be added here in a trusted base before any writer
# emits it (#1058 decision 8).
CURRENT_SCHEMA = csarc_config.SCHEMA_VERSION
SUPPORTED_SCHEMAS = (CURRENT_SCHEMA,)

ROUTE_ORDINARY = "ordinary"
ROUTE_GOVERNANCE_SWITCH = "governance-switch"
GOVERNANCE_SWITCH_LABEL = "governance-switch"
GOVERNED_SCRIPTS = GENERATED_SCRIPTS + "/"
# Each tuple runs from the strictest to the most relaxed value.
GOVERNANCE_ORDER: dict[str, tuple[str, ...]] = {
    "admin_bypass": ("off", "beta-only", "always"),
    "copilot_review": ("off", "allowed"),
    "governance_mode": ("managed", "observe"),
    "verification_mode": ("hosted", "local"),
}
GOVERNANCE_FLAGS = ("enable_codeql",)
GOVERNANCE_LISTS = ("lifecycle", "scheduled_checks")
GOVERNANCE_MINIMUMS = ("coverage_threshold",)

SUITE_RANK = {"fast": 0, "full": 1}
FULL_FLOOR_LABELS = frozenset({"hotfix", "promotion", "release-recovery"})
DELIVERY_BASE = re.compile(r"dev/[mi][1-9][0-9]*-[a-z0-9][a-z0-9-]*")
TRUSTED_BASE_ENV = "CSARC_TRUSTED_BASE_SHA"
SHA = re.compile(r"[0-9a-f]{40}")
PULL_FILES_LIMIT = 3000


def config_schema(path: Path) -> int:
    """Return the declared configuration schema, failing closed if unknown."""
    values = csarc_config.parse_settings_text(
        path.read_text(encoding="utf-8"), path
    )
    try:
        return csarc_config.declared_schema(values, path)
    except csarc_config.SettingsError as error:
        raise ValueError(
            f"{error} This trusted base reads schema {CURRENT_SCHEMA} only; "
            "merge a base that reads a new schema before changing the writer."
        ) from error


def read_config(path: Path) -> dict[str, object]:
    """Read the current configuration schema without writing.

    Retired keys, unknown keys or metadata, missing intent, and any other
    schema fail closed; nothing is normalized from legacy defaults.
    """
    config_schema(path)
    return csarc_config.load_config(path)


def governance_relaxations(  # noqa: C901
    base: dict[str, object], candidate: dict[str, object]
) -> list[str]:
    """List every governance value the candidate relaxes from its base."""
    relaxed: list[str] = []
    for key, order in GOVERNANCE_ORDER.items():
        before, after = base.get(key), candidate.get(key)
        if before == after:
            continue
        if before in order and after in order:
            if order.index(str(after)) > order.index(str(before)):
                relaxed.append(f"{key}: {before} -> {after}")
        else:
            # An unordered change (added, removed, or unknown) counts as a
            # relaxation so it can only land through the reviewed route.
            relaxed.append(f"{key}: {before} -> {after}")
    for key in GOVERNANCE_FLAGS:
        if base.get(key) is True and candidate.get(key) is not True:
            relaxed.append(f"{key}: true -> {candidate.get(key)}")
    for key in GOVERNANCE_LISTS:
        before_items = base.get(key)
        after_items = candidate.get(key)
        removed = sorted(
            {str(item) for item in before_items}
            if isinstance(before_items, list)
            else set()
        )
        if isinstance(after_items, list):
            removed = [item for item in removed if item not in after_items]
        if removed:
            relaxed.append(f"{key}: removes {', '.join(removed)}")
    for key in GOVERNANCE_MINIMUMS:
        before, after = base.get(key), candidate.get(key)
        if type(before) is int and (type(after) is not int or after < before):
            relaxed.append(f"{key}: {before} -> {after}")
    return relaxed


@dataclass(frozen=True)
class RouteDecision:
    """One base-policy merge route and the reasons that selected it."""

    route: str
    reasons: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        """Return the stable machine-readable form."""
        return {"route": self.route, "reasons": list(self.reasons)}


def classify_route(
    changed_files: list[str] | None,
    base_config: dict[str, object],
    candidate_config: dict[str, object],
) -> RouteDecision:
    """Select the merge route from base-owned rules only."""
    reasons: list[str] = []
    if changed_files is None:
        reasons.append("changed paths are unavailable")
    else:
        governed = sorted(
            path for path in changed_files if path.startswith(GOVERNED_SCRIPTS)
        )
        if governed:
            shown = ", ".join(governed[:5])
            extra = (
                f" and {len(governed) - 5} more" if len(governed) > 5 else ""
            )
            reasons.append(f"changes {GOVERNED_SCRIPTS}: {shown}{extra}")
    base_schema = base_config.get(SCHEMA_KEY, CURRENT_SCHEMA)
    candidate_schema = candidate_config.get(SCHEMA_KEY, CURRENT_SCHEMA)
    if base_schema != candidate_schema:
        reasons.append(
            f"changes {SCHEMA_KEY}: {base_schema} -> {candidate_schema}"
        )
    reasons.extend(
        f"relaxes {item}"
        for item in governance_relaxations(base_config, candidate_config)
    )
    route = ROUTE_GOVERNANCE_SWITCH if reasons else ROUTE_ORDINARY
    return RouteDecision(route, tuple(reasons))


def require_route(decision: RouteDecision, labels: set[str]) -> None:
    """Fail closed when a governance switch is not declared on the PR."""
    if (
        decision.route == ROUTE_GOVERNANCE_SWITCH
        and GOVERNANCE_SWITCH_LABEL not in labels
    ):
        raise RuntimeError(
            "This pull request needs the governance-switch route ("
            + "; ".join(decision.reasons)
            + f"); add the {GOVERNANCE_SWITCH_LABEL} label. The route keeps "
            "required checks, the exact head, and the remote lease."
        )


def stronger_suite(first: str, second: str) -> str:
    """Return the stronger of two verification suites."""
    aliases = {"baseline": "fast", "docs": "fast"}
    first, second = aliases.get(first, first), aliases.get(second, second)
    if first not in SUITE_RANK or second not in SUITE_RANK:
        raise ValueError("unknown verification suite")
    return max((first, second), key=SUITE_RANK.__getitem__)


def channel_floor(base_ref: str, labels: set[str]) -> tuple[str, str]:
    """Return the release channel and verification floor for one base.

    Delivery branches carry beta work (fast floor). Every other base, which
    covers standalone work, hotfixes, and release recovery on `main`, is a
    stable route that needs full evidence; so do the tier labels.
    """
    base = base_ref.removeprefix("refs/heads/").removeprefix("origin/")
    if labels & FULL_FLOOR_LABELS:
        return "stable", "full"
    if DELIVERY_BASE.fullmatch(base) is not None:
        return "beta", "fast"
    return "stable", "full"


def _git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    """Run one Git command in `root`, failing closed with its error."""
    result = subprocess.run(  # noqa: S603 - fixed git arguments
        ["git", "-C", str(root), *args],  # noqa: S607
        input=data,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {args[0]} failed: {detail}")
    return result.stdout


def ensure_commit(root: Path, sha: str) -> None:
    """Make one exact commit available locally, fetching it if needed."""
    if SHA.fullmatch(sha) is None:
        raise RuntimeError("Trusted base commit identity is malformed")
    try:
        _git(root, "cat-file", "-e", f"{sha}^{{commit}}")
    except RuntimeError:
        _git(root, "fetch", "--no-tags", "--quiet", "origin", sha)
        _git(root, "cat-file", "-e", f"{sha}^{{commit}}")


@contextlib.contextmanager
def trusted_base_checkout(root: Path, base_sha: str) -> Generator[Path]:
    """Check out one exact trusted base commit beside the candidate.

    The detached checkout shares the object store, so base scripts that read
    history (release and promotion revalidation) keep working, while every
    decision file comes from the base commit instead of the candidate tree.
    """
    ensure_commit(root, base_sha)
    with tempfile.TemporaryDirectory(prefix="csarc-trusted-base-") as scratch:
        checkout = Path(scratch) / "base"
        _git(
            root,
            "worktree",
            "add",
            "--detach",
            "--quiet",
            str(checkout),
            base_sha,
        )
        try:
            actual = _git(checkout, "rev-parse", "HEAD").decode().strip()
            if actual != base_sha:
                raise RuntimeError(
                    "Trusted base checkout is not the lease base"
                )
            yield checkout
        finally:
            with contextlib.suppress(RuntimeError):
                _git(root, "worktree", "remove", "--force", str(checkout))


def read_pull_files(path: Path) -> list[str] | None:
    """Read a GitHub pull-request file listing, or None if incomplete.

    The REST listing stops at 3,000 files, so a listing that reaches the cap
    is treated as unavailable instead of as complete.
    """
    try:
        pages = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(pages, list):
        return None
    items = (
        [item for page in pages for item in page]
        if all(isinstance(page, list) for page in pages)
        else pages
    )
    files: list[str] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(
            item.get("filename"), str
        ):
            return None
        files.append(item["filename"])
        previous = item.get("previous_filename")
        if isinstance(previous, str):
            files.append(previous)
    return None if len(items) >= PULL_FILES_LIMIT else files


def read_changed_files_strict(path: Path) -> list[str]:
    """Read a NUL-separated changed-file list, raising when unreadable."""
    return [
        item.decode("utf-8", "replace")
        for item in path.read_bytes().split(b"\0")
        if item
    ]


def policy_self_test(
    candidate_root: Path,
    *,
    base_config: Path,
    candidate_config: Path,
    changed_files: Path | None,
    labels: str,
    trusted: RouteDecision,
    timeout: float = 120.0,
) -> list[str]:
    """Replay the candidate's own route rules without any authority."""
    lines = [
        "Candidate policy self-test (non-authoritative): the trusted base "
        f"already selected route {trusted.route}; nothing below changes it.",
    ]
    script = (
        candidate_root / scripts_prefix(candidate_root) / "trusted_executor.py"
    )
    if not script.is_file():
        lines.append("Candidate has no base-policy reader to compare.")
        return lines
    command = [
        sys.executable,
        str(script),
        "route",
        "--base-config",
        str(base_config),
        "--candidate-config",
        str(candidate_config),
        "--labels",
        labels,
        "--json",
    ]
    if changed_files is not None:
        command.extend(["--changed-files", str(changed_files)])
    try:
        result = subprocess.run(  # noqa: S603 - candidate self-test only
            command,
            cwd=candidate_root,
            env=candidate_environment(),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        candidate = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        candidate = None
    if not isinstance(candidate, dict):
        lines.append("Candidate policy produced no readable route.")
    elif candidate != trusted.as_json():
        lines.append(
            f"Route difference: trusted={trusted.as_json()!r} "
            f"candidate={candidate!r}"
        )
    else:
        lines.append("Candidate policy agrees with the trusted route.")
    return lines


def _route_command(args: argparse.Namespace) -> int:
    """Print or enforce one base-policy route."""
    try:
        base = read_config(args.base_config)
        candidate = read_config(args.candidate_config)
    except (OSError, ValueError) as error:
        sys.stderr.write(
            f"Trusted base cannot read the configuration: {error}\n"
        )
        return 1
    changed: list[str] | None = []
    if args.pull_files is not None:
        changed = read_pull_files(args.pull_files)
    elif args.changed_files is not None:
        try:
            changed = read_changed_files_strict(args.changed_files)
        except OSError:
            changed = None
    decision = classify_route(changed, base, candidate)
    if args.json:
        sys.stdout.write(json.dumps(decision.as_json(), sort_keys=True) + "\n")
    else:
        sys.stdout.write(f"Merge route: {decision.route}\n")
        sys.stdout.writelines(f"- {reason}\n" for reason in decision.reasons)
    if args.enforce:
        try:
            require_route(
                decision, {label for label in args.labels.split(",") if label}
            )
        except RuntimeError as error:
            sys.stderr.write(f"{error}\n")
            return 1
    return 0


def policy_main(args: argparse.Namespace) -> int:
    """Run one base-policy command (Issue #1069)."""
    if args.command == "route":
        return _route_command(args)
    if args.command == "read-config":
        try:
            values = read_config(args.config)
            value = values if args.key is None else values[args.key]
        except (OSError, KeyError, ValueError) as error:
            sys.stderr.write(f"{error}\n")
            return 1
        if isinstance(value, dict):
            sys.stdout.write(json.dumps(value, sort_keys=True) + "\n")
        elif isinstance(value, list):
            sys.stdout.write(",".join(str(item) for item in value) + "\n")
        elif isinstance(value, bool):
            sys.stdout.write(f"{str(value).lower()}\n")
        elif value is not None:
            sys.stdout.write(f"{value}\n")
        return 0
    if args.command == "channel-floor":
        labels = {label for label in args.labels.split(",") if label}
        level, floor = channel_floor(args.base, labels)
        try:
            suite = stronger_suite(floor, args.path_tier)
        except ValueError as error:
            sys.stderr.write(f"{error}\n")
            return 2
        sys.stdout.write(f"level={level} floor={floor} suite={suite}\n")
        return 0
    return 2


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("prepare", help="stage the trusted executor")
    stage.add_argument("--source", type=Path, required=True)
    stage.add_argument("--destination", type=Path, required=True)
    stage.add_argument(
        "--control-set", choices=CONTROL_SETS, default=CONTROL_SET_VERIFICATION
    )
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
    reader = commands.add_parser(
        "read-config", help="read any supported schema, failing closed"
    )
    reader.add_argument("--config", type=Path, required=True)
    reader.add_argument("--key")
    route = commands.add_parser("route", help="select the base-policy route")
    route.add_argument("--base-config", type=Path, required=True)
    route.add_argument("--candidate-config", type=Path, required=True)
    changed = route.add_mutually_exclusive_group()
    changed.add_argument("--changed-files", type=Path)
    changed.add_argument("--pull-files", type=Path)
    route.add_argument("--labels", default="")
    route.add_argument("--json", action="store_true")
    route.add_argument("--enforce", action="store_true")
    floor = commands.add_parser(
        "channel-floor", help="print the release-channel verification floor"
    )
    floor.add_argument("--base", required=True)
    floor.add_argument("--labels", default="")
    floor.add_argument("--path-tier", default="fast")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run one trusted-executor command."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "prepare":
        try:
            files = prepare(args.source, args.destination, args.control_set)
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
    if args.command in {"read-config", "route", "channel-floor"}:
        return policy_main(args)
    try:
        router_args = read_router_args(args.router_args)
    except (OSError, ValueError):
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
