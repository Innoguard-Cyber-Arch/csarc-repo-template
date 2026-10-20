"""Immutable, replayable final plan for ``csarc update`` (Issue #1067).

``csarc update --check`` writes a stage-1 plan (``csarc-update-plan.json``)
that is never replayable: it is a preview whose conflicts still need human
decisions. ``csarc update --finalize-plan`` records those decisions in the
same report directory as ``csarc-update-final-plan.json``, together with
every value the apply needs: the tool versions, the exact Copier inputs,
the live facts observed at decision time, the derived planning context,
and a digest per section plus one digest over the whole plan.

``csarc update --apply-plan`` renders and applies only from those recorded
values. It never asks again, never takes a current default, and never
recomputes mutable context; it re-observes the live facts and the
toolchain first and fails closed, with the target byte-identical, when any
of them differ from the plan.

This module holds the pure, Copier-free part of that contract.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import json
import platform
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

FINAL_PLAN_BASENAME = "csarc-update-final-plan.json"
FINAL_PLAN_KIND = "csarc-update-final-plan"
SCHEMA_VERSION = 1

# Copier and Jinja2 decide what a render produces, so a plan replays only
# with the exact versions that created it. ``pyproject.toml`` pins both to
# these versions and the generated template-update workflow installs the
# same Copier pin (#1058 decision 19); tests read all three back.
PINNED_TOOLS = {"copier": "9.19.1", "jinja2": "3.1.6"}
CSARC_DISTRIBUTION = "csarc-repo-template"

DECISION_KEEP = "keep-current"
DECISION_TAKE = "take-new"
DECISION_CUSTOM = "custom"
FILE_DECISIONS = (DECISION_KEEP, DECISION_TAKE, DECISION_CUSTOM)

SECTIONS = (
    "decisions",
    "derived",
    "inputs",
    "live_facts",
    "report",
    "toolchain",
)
TOP_LEVEL_KEYS = frozenset(
    {
        *SECTIONS,
        "created_at",
        "digests",
        "final_plan_sha256",
        "kind",
        "replayable",
        "schema_version",
        "stage1_plan",
        "target",
    }
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")

GitVersion = Callable[[], str]


class FinalPlanError(ValueError):
    """Raised when a final plan cannot be created, trusted, or replayed."""


def canonical_bytes(value: object) -> bytes:
    """Serialize one JSON value canonically; non-JSON values fail closed."""
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as error:
        raise FinalPlanError(
            f"Final plan values must be plain JSON ({error})."
        ) from error


def digest(value: object) -> str:
    """Return the SHA-256 digest of one canonical JSON value."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def exact_json(value: object, label: str) -> object:
    """Return ``value`` only when it survives a JSON round trip unchanged.

    A value that changes type or content when written and read back (a
    tuple, a date, a non-string key) could replay differently, so it is
    rejected before the plan is written.
    """
    restored = json.loads(canonical_bytes(value))
    if restored != value or canonical_bytes(restored) != canonical_bytes(value):
        raise FinalPlanError(
            f"{label} does not round-trip through JSON exactly; the final "
            "plan cannot replay it."
        )
    return restored


def observe_toolchain(git_version: GitVersion) -> dict[str, str]:
    """Return the versions of every tool that shapes the render."""
    versions = {
        name: importlib.metadata.version(name) for name in sorted(PINNED_TOOLS)
    }
    try:
        csarc_version = importlib.metadata.version(CSARC_DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError:
        csarc_version = "unknown"
    versions.update(
        {
            "csarc": csarc_version,
            "git": git_version(),
            "python": platform.python_version(),
        }
    )
    return dict(sorted(versions.items()))


def require_pinned_toolchain(toolchain: Mapping[str, str]) -> None:
    """Fail closed when Copier or Jinja2 is not the exact pinned version."""
    drift = [
        f"{name} {toolchain.get(name)} != {pinned}"
        for name, pinned in sorted(PINNED_TOOLS.items())
        if toolchain.get(name) != pinned
    ]
    if drift:
        raise FinalPlanError(
            "Unsupported toolchain (" + "; ".join(drift) + "). Install the "
            "csarc release that pins these exact versions; a version range "
            "is never accepted for a replayable plan."
        )


def parse_file_decisions(
    values: Sequence[str],
) -> dict[str, tuple[str, Path | None]]:
    """Parse ``PATH=keep-current|take-new|custom:FILE`` decisions."""
    decisions: dict[str, tuple[str, Path | None]] = {}
    for value in values:
        path, separator, choice = value.partition("=")
        if not separator or not path or not choice:
            raise FinalPlanError(
                f"Invalid --decision {value!r}; use PATH=keep-current, "
                "PATH=take-new, or PATH=custom:FILE."
            )
        if path in decisions:
            raise FinalPlanError(f"Duplicate --decision for {path}.")
        custom: Path | None = None
        if choice.startswith(f"{DECISION_CUSTOM}:"):
            custom_name = choice.partition(":")[2]
            if not custom_name:
                raise FinalPlanError(
                    f"--decision {path}=custom needs a FILE with the "
                    "resolved content."
                )
            custom = Path(custom_name)
            choice = DECISION_CUSTOM
        elif choice not in (DECISION_KEEP, DECISION_TAKE):
            raise FinalPlanError(
                f"Unknown decision {choice!r} for {path}; use "
                + ", ".join(FILE_DECISIONS)
                + "."
            )
        decisions[path] = (choice, custom)
    return decisions


def require_complete_decisions(
    conflicts: Sequence[str], decisions: Mapping[str, object]
) -> None:
    """Require exactly one decision for every planned conflict."""
    missing = sorted(set(conflicts) - set(decisions))
    extra = sorted(set(decisions) - set(conflicts))
    problems: list[str] = []
    if missing:
        problems.append("missing a decision: " + ", ".join(missing))
    if extra:
        problems.append("not a planned conflict: " + ", ".join(extra))
    if problems:
        raise FinalPlanError(
            "Every stage-1 conflict needs exactly one --decision ("
            + "; ".join(problems)
            + ")."
        )


def resolution(
    path: str, choice: str, content: bytes | None
) -> dict[str, object]:
    """Record one file decision with its exact resolved bytes.

    ``content`` is ``None`` when the decision resolves to an absent file.
    """
    return {
        "content_base64": None
        if content is None
        else base64.b64encode(content).decode("ascii"),
        "content_sha256": None
        if content is None
        else hashlib.sha256(content).hexdigest(),
        "decision": choice,
        "path": path,
    }


def resolution_content(entry: Mapping[str, object]) -> bytes | None:
    """Return the recorded bytes of one decision, verifying their digest."""
    encoded = entry.get("content_base64")
    expected = entry.get("content_sha256")
    if encoded is None and expected is None:
        return None
    if not isinstance(encoded, str) or not isinstance(expected, str):
        raise FinalPlanError(
            f"Decision for {entry.get('path')} has malformed content."
        )
    try:
        content = base64.b64decode(encoded.encode("ascii"), validate=True)
    except ValueError as error:
        raise FinalPlanError(
            f"Decision for {entry.get('path')} has malformed content."
        ) from error
    if hashlib.sha256(content).hexdigest() != expected:
        raise FinalPlanError(
            f"Decision content for {entry.get('path')} does not match its "
            "recorded digest."
        )
    return content


def seal(payload: Mapping[str, object]) -> dict[str, object]:
    """Add per-section digests and the whole-plan digest."""
    plan = {
        key: value
        for key, value in payload.items()
        if key not in {"digests", "final_plan_sha256"}
    }
    plan["digests"] = {name: digest(plan[name]) for name in SECTIONS}
    plan["final_plan_sha256"] = digest(plan)
    return plan


def plan_text(plan: Mapping[str, object]) -> str:
    """Return the exact bytes written for one sealed final plan."""
    return json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False) + (
        "\n"
    )


def _require_shape(plan: Mapping[str, object]) -> None:
    """Validate the closed top-level shape of one final plan."""
    keys = set(plan)
    if keys != TOP_LEVEL_KEYS:
        unexpected = sorted(keys - TOP_LEVEL_KEYS)
        missing = sorted(TOP_LEVEL_KEYS - keys)
        raise FinalPlanError(
            "Final plan has an invalid shape (missing: "
            + (", ".join(missing) or "none")
            + "; unexpected: "
            + (", ".join(unexpected) or "none")
            + ")."
        )
    if plan["kind"] != FINAL_PLAN_KIND:
        raise FinalPlanError("The file is not a csarc update final plan.")
    if plan["schema_version"] != SCHEMA_VERSION:
        raise FinalPlanError(
            f"Unsupported final plan schema_version {plan['schema_version']!r}."
        )
    if plan["replayable"] is not True:
        raise FinalPlanError("Only a replayable final plan can be applied.")
    for name in SECTIONS:
        if not isinstance(plan[name], dict):
            raise FinalPlanError(
                f"Final plan section {name} must be an object."
            )


def verify(plan: Mapping[str, object]) -> dict[str, object]:
    """Validate the shape and every digest of one final plan."""
    _require_shape(plan)
    digests = plan["digests"]
    if not isinstance(digests, dict) or set(digests) != set(SECTIONS):
        raise FinalPlanError("Final plan digests are incomplete.")
    tampered = sorted(
        name for name in SECTIONS if digests[name] != digest(plan[name])
    )
    if tampered:
        raise FinalPlanError(
            "Final plan sections do not match their digests ("
            + ", ".join(tampered)
            + "); the plan was modified after it was created."
        )
    body = {
        key: value for key, value in plan.items() if key != "final_plan_sha256"
    }
    recorded = plan["final_plan_sha256"]
    if not isinstance(recorded, str) or SHA256.fullmatch(recorded) is None:
        raise FinalPlanError("Final plan digest is missing or malformed.")
    if digest(body) != recorded:
        raise FinalPlanError(
            "Final plan digest does not match its content; the plan was "
            "modified after it was created."
        )
    return dict(plan)


def load(path: Path) -> dict[str, object]:
    """Read and verify one final plan file."""
    if path.is_symlink() or not path.is_file():
        raise FinalPlanError(f"Final plan {path} must be a regular file.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalPlanError(f"Cannot read final plan {path}.") from error
    if not isinstance(payload, dict):
        raise FinalPlanError(f"Final plan {path} must be a JSON object.")
    return verify(payload)


def stage1_digest(payload: Mapping[str, object]) -> str:
    """Return the digest a stage-1 plan records for its own content."""
    body = {
        key: value for key, value in payload.items() if key != "plan_sha256"
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_stage1(path: Path) -> dict[str, object]:
    """Read one stage-1 plan, requiring its digest and non-replayable flag."""
    if path.is_symlink() or not path.is_file():
        raise FinalPlanError(
            f"Stage-1 plan {path} is missing; run csarc update --check first."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalPlanError(f"Cannot read stage-1 plan {path}.") from error
    if not isinstance(payload, dict) or payload.get("mode") != "update":
        raise FinalPlanError(f"{path} is not a csarc update stage-1 plan.")
    if payload.get("replayable") is not False:
        raise FinalPlanError(
            f"{path} is not marked as a non-replayable stage-1 plan."
        )
    if payload.get("plan_sha256") != stage1_digest(payload):
        raise FinalPlanError(
            f"Stage-1 plan {path} does not match its digest; run csarc "
            "update --check again."
        )
    return payload


def live_fact_differences(
    recorded: Mapping[str, object], observed: Mapping[str, object]
) -> list[str]:
    """Name every live fact whose current value differs from the plan."""
    return sorted(
        key
        for key in set(recorded) | set(observed)
        if canonical_bytes(recorded.get(key))
        != canonical_bytes(observed.get(key))
    )
