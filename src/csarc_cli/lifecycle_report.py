"""SPEC-008 lifecycle report model shared by adopt and update.

The report JSON object is the only source of truth. The Markdown report is
rendered exclusively from that object, after it has been validated against
the closed vocabularies below, so a reviewer and a program always read the
same decision. Unknown vocabulary, missing keys, or secret-looking values
fail closed instead of being rendered.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import cast

LIFECYCLE_REPORT_FORMAT_VERSION = "2.1.0"
# The 2.1.0 reader still validates a 2.0.0 report (for example one embedded
# in an earlier final plan) by the 2.0.0 rules; the writer emits only 2.1.0.
PREVIOUS_REPORT_FORMAT_VERSION = "2.0.0"
READABLE_REPORT_FORMAT_VERSIONS = (
    PREVIOUS_REPORT_FORMAT_VERSION,
    LIFECYCLE_REPORT_FORMAT_VERSION,
)
OPERATIONS = ("adopt", "update")
STATUSES = ("applied", "blocked", "review-required", "ready", "current")
OPERATION_STATUSES = {
    "adopt": frozenset({"applied", "blocked", "review-required", "ready"}),
    "update": frozenset(STATUSES),
}
BANNERS = {
    "adopt": {
        "applied": "Adopted",
        "blocked": "Blocked",
        "review-required": "Review required",
        "ready": "Ready to adopt",
    },
    "update": {
        "applied": "Updated",
        "blocked": "Blocked",
        "current": "Current",
        "review-required": "Review required",
        "ready": "Ready to update",
    },
}
SETTING_CLASSES = (
    "unchanged",
    "exact",
    "narrowed",
    "widened",
    "decision",
    "new",
    "retired",
)
SETTING_SOURCES = ("explicit", "saved", "derived")
FILE_ACTIONS = {
    "add": ("template", "lockfile"),
    "overwrite": ("template", "automatic-merge"),
    "move": ("layout-migration",),
    "remove": ("template-deleted",),
    "retire": ("obsolete-generated", "excluded-orphan"),
    "preserve": ("untouched", "product-owned", "dirty-preserved"),
    "conflict": (
        "manual-merge",
        "undetermined",
        "move-collision",
        "update-conflict",
        "retire-modified",
    ),
}
FILE_DECISIONS = ("pending", "keep-current", "take-new", "custom")
REQUIRED_ACTION_KINDS = (
    "action-pin",
    "code-owner",
    "committed-resolution",
    "file-conflict",
    "mapping-decision",
    "mapping-review",
    "release-writer",
    "render-parity",
    "retire-modified",
    "runtime-mismatch",
    "setting-decision",
    "verification",
    "version-surface",
    "working-tree",
)
# 2.0.0 kept setting decisions update-only; the 2.1.0 MINOR bump opens them
# to adopt for intent no unique source decides (Issue #1078).
UPDATE_ONLY_ACTION_KINDS_2_0 = frozenset({"setting-decision"})
WORKING_TREE_STATES = ("clean", "dirty-preserved", "dirty-review-only")
CANDIDATE_STATES = (
    "pending-authorization",
    "deferred-manual-merge",
    "passed",
    "failed",
    "not-run",
)
RENDER_PARITY_STATES = ("equal", "diverged")
SECTION_HEADINGS = (
    "Items requiring your decision",
    "Snapshot",
    "Summary of file changes",
    "Impact analysis",
    "File changes",
    "Settings",
    "Product state",
    "Verification",
    "Next steps",
)
PRODUCT_SUBSECTIONS = (
    ("release_writers", "Release writers"),
    ("version_surfaces", "Version surfaces"),
    ("action_pins", "Action pins"),
    ("reviewer_rotation", "Reviewer rotation"),
    ("behavior_changes", "Behavior changes"),
    ("work_item_mapping", "Work-item mapping"),
)
REPORT_KEYS = frozenset(
    {
        "applicable",
        "applied_at",
        "files",
        "final_plan",
        "generated_at",
        "next_steps",
        "operation",
        "plan",
        "product",
        "release",
        "report_format_version",
        "required_actions",
        "settings",
        "status",
        "status_reason",
        "summary",
        "target",
        "verification",
    }
)
# 2.1.0 adds the init/adopt setup record (Issue #1078).
REPORT_KEYS_2_0 = REPORT_KEYS
REPORT_KEYS_2_1 = REPORT_KEYS | {"setup"}
SETUP_KEYS = frozenset({"approval_route", "questions", "warnings", "work_mode"})
WARNING_KEYS = frozenset({"code", "command", "message", "subject"})
WARNING_CODE = re.compile(r"^W[0-9]{2}-[a-z][a-z-]*$")
APPROVAL_ROUTE_KEYS = frozenset({"confirmation", "reason", "state"})
APPROVAL_ROUTE_STATES = ("route-observed", "none-observed", "inconclusive")
APPROVAL_CONFIRMATIONS = ("second-approver", "copilot-entitlement")
WORK_MODES = ("solo-local", "solo-hosted", "team", "custom")
PLAN_KEYS = frozenset(
    {"mode", "path", "replayable", "schema_version", "sha256"}
)
TARGET_KEYS = frozenset(
    {
        "changes",
        "head",
        "path",
        "repository",
        "visibility",
        "visibility_source",
        "working_tree",
    }
)
RELEASE_KEYS = frozenset({"from", "source", "to"})
SETTING_KEYS = frozenset({"after", "before", "class", "key", "note", "source"})
FILE_KEYS = frozenset({"action", "decision", "from", "path", "reason"})
ACTION_KEYS = frozenset({"blocking", "command", "kind", "message", "subject"})
PRODUCT_KEYS = frozenset(
    {
        "action_pins",
        "behavior_changes",
        "code_owner",
        "release_ownership",
        "release_writers",
        "reviewer_rotation",
        "version_surfaces",
        "work_item_mapping",
    }
)
VERIFICATION_KEYS = frozenset({"candidate", "hook", "render_parity"})
NEXT_STEP_KEYS = frozenset({"command", "text"})
REDACTED = "[redacted]"
# Credential shapes that must never reach a report written outside the
# target. Values are replaced before validation; validation then rejects
# any leaf that still matches, so a missed redaction fails closed.
SECRET_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)"),
)


class LifecycleReportError(ValueError):
    """Raised when a report violates the closed SPEC-008 contract."""


def redact_text(value: str) -> str:
    """Replace every credential-shaped fragment with a fixed marker."""
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def redact(value: object) -> object:
    """Return a JSON-safe copy whose string leaves carry no credentials."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(key): redact(item)
            for key, item in cast(Mapping[object, object], value).items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in cast(Sequence[object], value)]
    return value


def _fail(path: str, message: str) -> LifecycleReportError:
    return LifecycleReportError(f"{path}: {message}")


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _fail(path, "must be an object")
    return cast(Mapping[str, object], value)


def _rows(value: object, path: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise _fail(path, "must be a list")
    return [
        _mapping(item, f"{path}[{index}]")
        for index, item in enumerate(cast(list[object], value))
    ]


def _exact_keys(
    value: Mapping[str, object], keys: frozenset[str], path: str
) -> None:
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing:
        raise _fail(path, f"missing keys {missing}")
    if unknown:
        raise _fail(path, f"unknown keys {unknown}")


def _member(value: object, allowed: Sequence[str], path: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _fail(path, f"unknown value {value!r}")
    return value


def _optional_text(value: object, path: str) -> None:
    if value is not None and not isinstance(value, str):
        raise _fail(path, "must be a string or null")


def _check_secrets(value: object, path: str) -> None:
    if isinstance(value, str):
        if any(pattern.search(value) for pattern in SECRET_PATTERNS):
            raise _fail(path, "contains an unredacted credential")
    elif isinstance(value, Mapping):
        for key, item in cast(Mapping[str, object], value).items():
            _check_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(cast(list[object], value)):
            _check_secrets(item, f"{path}[{index}]")


def _validate_plan_reference(value: object, path: str) -> None:
    plan = _mapping(value, path)
    _exact_keys(plan, PLAN_KEYS, path)
    for key in ("mode", "path"):
        if not isinstance(plan[key], str):
            raise _fail(f"{path}.{key}", "must be a string")
    sha256 = plan["sha256"]
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise _fail(f"{path}.sha256", "must be a SHA-256 digest")
    if not isinstance(plan["schema_version"], int):
        raise _fail(f"{path}.schema_version", "must be an integer")
    if not isinstance(plan["replayable"], bool):
        raise _fail(f"{path}.replayable", "must be a boolean")


def _validate_settings(
    report: Mapping[str, object],
) -> list[Mapping[str, object]]:
    rows = _rows(report["settings"], "$.settings")
    keys: list[str] = []
    for index, row in enumerate(rows):
        path = f"$.settings[{index}]"
        _exact_keys(row, SETTING_KEYS, path)
        if not isinstance(row["key"], str):
            raise _fail(f"{path}.key", "must be a string")
        keys.append(row["key"])
        setting_class = _member(row["class"], SETTING_CLASSES, f"{path}.class")
        _member(row["source"], SETTING_SOURCES, f"{path}.source")
        _optional_text(row["note"], f"{path}.note")
        if setting_class == "retired" and row["after"] is not None:
            raise _fail(f"{path}.after", "must be null for a retired key")
        if setting_class == "unchanged" and row["before"] != row["after"]:
            raise _fail(path, "unchanged setting has different values")
    if keys != sorted(set(keys)):
        raise _fail("$.settings", "keys must be unique and sorted")
    return rows


def _validate_files(report: Mapping[str, object]) -> list[Mapping[str, object]]:
    rows = _rows(report["files"], "$.files")
    order = list(FILE_ACTIONS)
    sort_keys: list[tuple[int, str]] = []
    for index, row in enumerate(rows):
        path = f"$.files[{index}]"
        _exact_keys(row, FILE_KEYS, path)
        action = _member(row["action"], order, f"{path}.action")
        _member(row["reason"], FILE_ACTIONS[action], f"{path}.reason")
        if not isinstance(row["path"], str):
            raise _fail(f"{path}.path", "must be a string")
        if action == "move":
            if not isinstance(row["from"], str):
                raise _fail(f"{path}.from", "move requires a source path")
        elif row["from"] is not None:
            raise _fail(f"{path}.from", "only move rows have a source path")
        if row["decision"] is not None:
            _member(row["decision"], FILE_DECISIONS, f"{path}.decision")
        sort_keys.append((order.index(action), row["path"]))
    if sort_keys != sorted(sort_keys):
        raise _fail("$.files", "rows must be ordered by action, then path")
    return rows


def _validate_actions(
    report: Mapping[str, object], operation: str
) -> list[Mapping[str, object]]:
    rows = _rows(report["required_actions"], "$.required_actions")
    previous = report["report_format_version"] == PREVIOUS_REPORT_FORMAT_VERSION
    allowed = [
        kind
        for kind in REQUIRED_ACTION_KINDS
        if operation == "update"
        or not previous
        or kind not in UPDATE_ONLY_ACTION_KINDS_2_0
    ]
    for index, row in enumerate(rows):
        path = f"$.required_actions[{index}]"
        _exact_keys(row, ACTION_KEYS, path)
        _member(row["kind"], allowed, f"{path}.kind")
        if not isinstance(row["blocking"], bool):
            raise _fail(f"{path}.blocking", "must be a boolean")
        for key in ("subject", "message"):
            if not isinstance(row[key], str):
                raise _fail(f"{path}.{key}", "must be a string")
        _optional_text(row["command"], f"{path}.command")
    return rows


def _validate_summary(
    report: Mapping[str, object],
    settings: list[Mapping[str, object]],
    files: list[Mapping[str, object]],
    actions: list[Mapping[str, object]],
) -> None:
    summary = _mapping(report["summary"], "$.summary")
    _exact_keys(
        summary,
        frozenset({"files", "required_actions", "settings"}),
        "$.summary",
    )
    expected = summary_counts(settings, files, actions)
    if dict(summary) != expected:
        raise _fail("$.summary", "counts do not match the report rows")


def _validate_status(
    report: Mapping[str, object],
    operation: str,
    actions: list[Mapping[str, object]],
) -> str:
    status = _member(
        report["status"], sorted(OPERATION_STATUSES[operation]), "$.status"
    )
    if not isinstance(report["status_reason"], str):
        raise _fail("$.status_reason", "must be a string")
    applicable = report["applicable"]
    if not isinstance(applicable, bool):
        raise _fail("$.applicable", "must be a boolean")
    blocking = any(row["blocking"] is True for row in actions)
    if status == "blocked" and (applicable or not blocking):
        raise _fail("$.status", "blocked needs a blocking action")
    if status in {"ready", "review-required", "current"} and blocking:
        raise _fail("$.status", f"{status} cannot carry a blocking action")
    if status == "ready" and (not applicable or actions):
        raise _fail("$.status", "ready must be applicable without actions")
    if status == "current" and actions:
        raise _fail("$.status", "current cannot carry a required action")
    if status == "review-required" and not actions:
        raise _fail("$.status", "review-required needs a required action")
    applied_at = report["applied_at"]
    if (status == "applied") != isinstance(applied_at, str):
        raise _fail("$.applied_at", "is set exactly when status is applied")
    return status


def _validate_sections(report: Mapping[str, object]) -> None:
    _validate_plan_reference(report["plan"], "$.plan")
    if report["final_plan"] is not None:
        if report["operation"] != "update":
            raise _fail("$.final_plan", "only update has a final plan")
        _validate_plan_reference(report["final_plan"], "$.final_plan")
    target = _mapping(report["target"], "$.target")
    _exact_keys(target, TARGET_KEYS, "$.target")
    if target["working_tree"] is not None:
        _member(
            target["working_tree"], WORKING_TREE_STATES, "$.target.working_tree"
        )
    release = _mapping(report["release"], "$.release")
    _exact_keys(release, RELEASE_KEYS, "$.release")
    product = _mapping(report["product"], "$.product")
    _exact_keys(product, PRODUCT_KEYS, "$.product")
    verification = _mapping(report["verification"], "$.verification")
    _exact_keys(verification, VERIFICATION_KEYS, "$.verification")
    candidate = verification["candidate"]
    if candidate is not None:
        candidate = _mapping(candidate, "$.verification.candidate")
        _member(
            candidate.get("state"),
            CANDIDATE_STATES,
            "$.verification.candidate.state",
        )
    parity = verification["render_parity"]
    if parity is not None:
        parity = _mapping(parity, "$.verification.render_parity")
        _member(
            parity.get("state"),
            RENDER_PARITY_STATES,
            "$.verification.render_parity.state",
        )
    for index, row in enumerate(_rows(report["next_steps"], "$.next_steps")):
        _exact_keys(row, NEXT_STEP_KEYS, f"$.next_steps[{index}]")
        if not isinstance(row["text"], str):
            raise _fail(f"$.next_steps[{index}].text", "must be a string")
        _optional_text(row["command"], f"$.next_steps[{index}].command")


def _validate_setup(report: Mapping[str, object], operation: str) -> None:  # noqa: C901
    """Validate the 2.1.0 setup record: adopt only, closed vocabulary."""
    if report["setup"] is None:
        return
    if operation != "adopt":
        raise _fail("$.setup", "only adopt carries a setup record")
    setup = _mapping(report["setup"], "$.setup")
    _exact_keys(setup, SETUP_KEYS, "$.setup")
    _member(setup["work_mode"], WORK_MODES, "$.setup.work_mode")
    questions = setup["questions"]
    if not isinstance(questions, list) or not all(
        isinstance(item, str) for item in cast(list[object], questions)
    ):
        raise _fail("$.setup.questions", "must be a list of keys")
    for index, row in enumerate(_rows(setup["warnings"], "$.setup.warnings")):
        path = f"$.setup.warnings[{index}]"
        _exact_keys(row, WARNING_KEYS, path)
        code = row["code"]
        if not isinstance(code, str) or WARNING_CODE.fullmatch(code) is None:
            raise _fail(f"{path}.code", f"unknown value {code!r}")
        for key in ("subject", "message"):
            if not isinstance(row[key], str):
                raise _fail(f"{path}.{key}", "must be a string")
        _optional_text(row["command"], f"{path}.command")
    route = setup["approval_route"]
    if route is not None:
        route = _mapping(route, "$.setup.approval_route")
        _exact_keys(route, APPROVAL_ROUTE_KEYS, "$.setup.approval_route")
        _member(
            route["state"],
            APPROVAL_ROUTE_STATES,
            "$.setup.approval_route.state",
        )
        if not isinstance(route["reason"], str):
            raise _fail("$.setup.approval_route.reason", "must be a string")
        if route["confirmation"] is not None:
            _member(
                route["confirmation"],
                APPROVAL_CONFIRMATIONS,
                "$.setup.approval_route.confirmation",
            )


def validate_report(report: object) -> Mapping[str, object]:
    """Validate one report object and return it, failing closed.

    A 2.1.0 reader reads 2.0.0 reports by the 2.0.0 rules (no ``setup``,
    update-only ``setting-decision``); any other version fails closed.
    """
    value = _mapping(report, "$")
    version = value.get("report_format_version")
    if version not in READABLE_REPORT_FORMAT_VERSIONS:
        raise _fail(
            "$.report_format_version",
            f"unsupported version {version!r}",
        )
    _exact_keys(
        value,
        REPORT_KEYS_2_0
        if version == PREVIOUS_REPORT_FORMAT_VERSION
        else REPORT_KEYS_2_1,
        "$",
    )
    operation = _member(value["operation"], OPERATIONS, "$.operation")
    if version == LIFECYCLE_REPORT_FORMAT_VERSION:
        _validate_setup(value, operation)
    settings = _validate_settings(value)
    files = _validate_files(value)
    actions = _validate_actions(value, operation)
    _validate_summary(value, settings, files, actions)
    _validate_status(value, operation, actions)
    _validate_sections(value)
    if not isinstance(value["generated_at"], str):
        raise _fail("$.generated_at", "must be a string")
    _check_secrets(value, "$")
    return value


def summary_counts(
    settings: Sequence[Mapping[str, object]],
    files: Sequence[Mapping[str, object]],
    actions: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Return the closed summary counts, listing every zero explicitly."""
    return {
        "files": {
            action: sum(1 for row in files if row["action"] == action)
            for action in FILE_ACTIONS
        },
        "required_actions": {
            "blocking": sum(1 for row in actions if row["blocking"] is True),
            "non_blocking": sum(
                1 for row in actions if row["blocking"] is not True
            ),
        },
        "settings": {
            setting_class: sum(
                1 for row in settings if row["class"] == setting_class
            )
            for setting_class in SETTING_CLASSES
        },
    }


def derive_status(
    operation: str,
    actions: Sequence[Mapping[str, object]],
    *,
    has_changes: bool,
) -> str:
    """Return the strongest unapplied status for the given required actions."""
    if any(row["blocking"] is True for row in actions):
        return "blocked"
    if actions:
        return "review-required"
    if operation == "update" and not has_changes:
        return "current"
    return "ready"


def report_json(report: Mapping[str, object]) -> str:
    """Serialize a validated report deterministically."""
    validate_report(report)
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def finalize_update_report(
    report: Mapping[str, object],
    *,
    decisions: Mapping[str, str],
    stage1_sha256: str,
    next_steps: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Record final-plan file decisions on one validated update report.

    Each decided ``update-conflict`` row carries its decision and its
    blocking ``file-conflict`` action is resolved; the report stays bound to
    the reviewed stage-1 plan digest (#1067). The ``final_plan`` reference
    is added separately, once the final plan digest exists.
    """
    current = validate_report(report)
    if current["operation"] != "update":
        raise LifecycleReportError("Only an update has a final plan.")
    files = [dict(row) for row in _rows(current["files"], "$.files")]
    conflicts = {
        str(row["path"])
        for row in files
        if row["action"] == "conflict" and row["reason"] == "update-conflict"
    }
    if set(decisions) != conflicts:
        raise LifecycleReportError(
            "Final plan decisions must name every update conflict exactly."
        )
    for row in files:
        if row["path"] in decisions and row["reason"] == "update-conflict":
            row["decision"] = _member(
                decisions[str(row["path"])], FILE_DECISIONS, "$.files.decision"
            )
    actions = [
        dict(row)
        for row in _rows(current["required_actions"], "$.required_actions")
        if not (row["kind"] == "file-conflict" and row["subject"] in decisions)
    ]
    result = dict(current)
    plan = dict(_mapping(current["plan"], "$.plan"))
    plan["sha256"] = stage1_sha256
    status = derive_status("update", actions, has_changes=True)
    result.update(
        {
            "applicable": status not in {"blocked", "current"},
            "files": files,
            "next_steps": [dict(step) for step in next_steps],
            "plan": plan,
            "required_actions": actions,
            "status": status,
            "status_reason": (
                "The final plan records every decision; apply it with csarc "
                "update --apply-plan."
                if status != "blocked"
                else "A blocking item remains outside the recorded decisions."
            ),
        }
    )
    result["summary"] = summary_counts(
        cast(list[Mapping[str, object]], result["settings"]), files, actions
    )
    validate_report(result)
    return result


def with_final_plan(
    report: Mapping[str, object], reference: Mapping[str, object]
) -> dict[str, object]:
    """Return an update report that names its sealed final plan."""
    result = dict(validate_report(report))
    result["final_plan"] = dict(reference)
    validate_report(result)
    return result


def mark_applied(
    report: Mapping[str, object],
    *,
    applied_at: str,
    plan_sha256: str,
    next_steps: Sequence[Mapping[str, object]],
    final_plan_sha256: str | None = None,
) -> dict[str, object]:
    """Turn a validated unapplied report into its applied state.

    The applied report stays bound to the digest of the plan that was
    replayed; a report for a different plan cannot be marked applied. An
    update applied from a final plan is also bound to that final plan.
    """
    current = validate_report(report)
    plan = _mapping(current["plan"], "$.plan")
    if plan["sha256"] != plan_sha256:
        raise LifecycleReportError(
            "Report is bound to a different plan digest; refusing to mark "
            "it applied."
        )
    if final_plan_sha256 is not None:
        final = current["final_plan"]
        if not isinstance(final, Mapping) or (
            final.get("sha256") != final_plan_sha256
        ):
            raise LifecycleReportError(
                "Report is bound to a different final plan digest; refusing "
                "to mark it applied."
            )
    if current["status"] in {"applied", "blocked"}:
        raise LifecycleReportError(
            f"A {current['status']} report cannot be marked applied."
        )
    operation = str(current["operation"])
    result = dict(current)
    result.update(
        {
            "applicable": False,
            "applied_at": applied_at,
            "next_steps": [dict(step) for step in next_steps],
            "required_actions": [],
            "status": "applied",
            "status_reason": (
                "The approved plan was applied; this report records the "
                "post-apply state."
                if operation == "adopt"
                else "The approved update was applied; this report records "
                "the post-apply state."
            ),
        }
    )
    result["summary"] = summary_counts(
        cast(list[Mapping[str, object]], result["settings"]),
        cast(list[Mapping[str, object]], result["files"]),
        [],
    )
    validate_report(result)
    return result


def printable(value: object) -> str:
    """Escape control characters without exposing file content."""
    return str(value).replace("\n", r"\n").replace("\r", r"\r")


def markdown_code(value: object) -> str:
    """Return a CommonMark code span using a non-conflicting delimiter."""
    rendered = printable(value)
    longest = max(
        (len(match.group()) for match in re.finditer(r"`+", rendered)),
        default=0,
    )
    delimiter = "`" * (longest + 1)
    padding = (
        " "
        if rendered.startswith("`")
        or rendered.endswith("`")
        or (rendered.strip() and rendered != rendered.strip())
        else ""
    )
    return f"{delimiter}{padding}{rendered}{padding}{delimiter}"


def markdown_text(value: object) -> str:
    """Escape backticks that appear in plain Markdown text."""
    return printable(value).replace("`", r"\`")


def markdown_table_code(value: object) -> str:
    """Return a safe CommonMark code span for a table cell."""
    return markdown_code(printable(value).replace("|", r"\|"))


def display(value: object) -> str:
    """Format one JSON value for Markdown without Python repr artifacts."""
    if value is None:
        return "(none)"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(display(item) for item in cast(list[object], value))
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def code(value: object) -> str:
    """Render one JSON value as an inline code span."""
    return markdown_code(display(value))


def cell(value: object) -> str:
    """Render one JSON value as a table-safe code span."""
    return markdown_table_code(display(value))


def _field(value: Mapping[str, object] | None, key: str) -> object:
    return None if value is None else value.get(key)


def _optional_mapping(value: object) -> Mapping[str, object] | None:
    return (
        cast(Mapping[str, object], value)
        if isinstance(value, Mapping)
        else None
    )


def _decision_lines(report: Mapping[str, object]) -> list[str]:
    actions = cast(list[Mapping[str, object]], report["required_actions"])
    ordered = sorted(actions, key=lambda row: row["blocking"] is not True)
    lines = []
    for row in ordered:
        marker = "Blocking" if row["blocking"] is True else "Decision"
        line = (
            f"- **{marker}** {code(row['kind'])} {code(row['subject'])} - "
            f"{markdown_text(row['message'])}"
        )
        if row["command"] is not None:
            line += f" Run {code(row['command'])}."
        lines.append(line)
    if not lines:
        lines.append(
            "No known file conflicts. This does not guarantee semantic or "
            "runtime compatibility."
        )
    return lines


def _snapshot_lines(report: Mapping[str, object]) -> list[str]:
    target = cast(Mapping[str, object], report["target"])
    release = cast(Mapping[str, object], report["release"])
    plan = cast(Mapping[str, object], report["plan"])
    to = _optional_mapping(release["to"])
    previous = _optional_mapping(release["from"])
    final_plan = _optional_mapping(report["final_plan"])
    lines = [
        f"- Operation: {code(report['operation'])}",
        f"- Target: {code(target['path'])}",
        f"- Target HEAD: {code(target['head'])}",
        f"- Working tree: {code(target['working_tree'])}",
        f"- Working-tree entries: {code(target['changes'])}",
        f"- Repository: {code(target['repository'])}",
        f"- Repository visibility: {code(target['visibility'])} "
        f"({code(target['visibility_source'])})",
        f"- Template source: {code(release['source'])}",
        f"- Previous release: {code(_field(previous, 'tag'))} / "
        f"{code(_field(previous, 'sha'))}",
        f"- Template: {code(_field(to, 'tag'))} / {code(_field(to, 'sha'))}",
        f"- Release verification: {code(_field(to, 'verification'))}",
        f"- Machine plan: {code(plan['path'])} ({code(plan['mode'])}, "
        f"replayable {code(plan['replayable'])})",
        f"- Plan SHA-256: {code(plan['sha256'])}",
        f"- Final plan: {code(_field(final_plan, 'path'))}",
        f"- Applicable: {code(report['applicable'])}",
        f"- Generated: {code(report['generated_at'])}",
        f"- Applied: {code(report['applied_at'])}",
    ]
    return lines


def _summary_lines(report: Mapping[str, object]) -> list[str]:
    summary = cast(Mapping[str, Mapping[str, object]], report["summary"])
    lines = ["| Action | Files |", "| --- | ---: |"]
    lines.extend(
        f"| `{action}` | {summary['files'][action]} |"
        for action in FILE_ACTIONS
    )
    return lines


def _impact_lines(report: Mapping[str, object]) -> list[str]:
    summary = cast(Mapping[str, Mapping[str, object]], report["summary"])
    settings = cast(list[Mapping[str, object]], report["settings"])
    product = cast(Mapping[str, object], report["product"])
    verification = cast(Mapping[str, object], report["verification"])
    files = summary["files"]
    widened = [row["key"] for row in settings if row["class"] == "widened"]
    lines = []
    if widened:
        lines.append(
            "- Widened settings: "
            + ", ".join(code(key) for key in widened)
            + ". See Settings."
        )
    changed = sum(
        cast(int, files[action])
        for action in ("add", "overwrite", "move", "remove", "retire")
    )
    lines.extend(
        [
            f"- Files changed by this plan: {changed}; conflicts: "
            f"{files['conflict']}; preserved: {files['preserve']}.",
            "- Settings by class: "
            + ", ".join(
                f"{name} {summary['settings'][name]}"
                for name in SETTING_CLASSES
            )
            + ".",
            "- Required actions: "
            f"{summary['required_actions']['blocking']} blocking, "
            f"{summary['required_actions']['non_blocking']} non-blocking.",
        ]
    )
    ownership = _optional_mapping(product["release_ownership"])
    lines.append(
        f"- Release ownership: {code(_field(ownership, 'ownership'))} using "
        f"workflow {code(_field(ownership, 'selected_workflow'))}."
    )
    candidate = _optional_mapping(verification["candidate"])
    lines.append(
        f"- Candidate verification: {code(_field(candidate, 'state'))}."
    )
    setup = _optional_mapping(report.get("setup"))
    if setup is not None:
        questions = cast(list[object], setup["questions"])
        route = _optional_mapping(setup["approval_route"])
        lines.extend(
            [
                f"- Work mode: {code(setup['work_mode'])} (expanded into "
                f"settings; not saved); setup questions asked: "
                f"{len(questions)}.",
                f"- Approval route: {code(_field(route, 'state'))}"
                + (
                    f" - {markdown_text(_field(route, 'reason'))}"
                    if route is not None
                    else ""
                )
                + (
                    f" (confirmed {code(_field(route, 'confirmation'))})"
                    if route is not None and route["confirmation"] is not None
                    else ""
                )
                + ".",
                "",
                "### Warnings",
                "",
                *_table(setup["warnings"]),
            ]
        )
    return lines


def _file_lines(report: Mapping[str, object]) -> list[str]:
    files = cast(list[Mapping[str, object]], report["files"])
    listed = [row for row in files if row["action"] != "preserve"]
    preserved = len(files) - len(listed)
    lines = []
    if listed:
        lines.extend(
            [
                "| Path | Action | Reason | From | Decision |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            f"| {cell(row['path'])} | {cell(row['action'])} | "
            f"{cell(row['reason'])} | {cell(row['from'])} | "
            f"{cell(row['decision'])} |"
            for row in listed
        )
    else:
        lines.append("None.")
    lines.extend(
        [
            "",
            f"{preserved} preserved path(s) are listed only in the report "
            "JSON.",
        ]
    )
    return lines


def _setting_lines(report: Mapping[str, object]) -> list[str]:
    settings = cast(list[Mapping[str, object]], report["settings"])
    if not settings:
        return ["None."]
    lines = [
        "| Setting | Before | After | Class | Source | Note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {cell(row['key'])} | {cell(row['before'])} | "
        f"{cell(row['after'])} | {cell(row['class'])} | "
        f"{cell(row['source'])} | {cell(row['note'])} |"
        for row in settings
    )
    return lines


def _table(rows: object) -> list[str]:
    """Render a list of flat objects as a table with sorted columns."""
    if not isinstance(rows, list) or not rows:
        return ["None."]
    items = [
        cast(Mapping[str, object], row)
        for row in cast(list[object], rows)
        if isinstance(row, Mapping)
    ]
    columns = sorted({key for row in items for key in row})
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    lines.extend(
        "| " + " | ".join(cell(row.get(column)) for column in columns) + " |"
        for row in items
    )
    return lines


def _mapping_lines(mapping: Mapping[str, object]) -> list[str]:
    lines = [
        "Read-only guidance; adoption never renames or deletes GitHub labels.",
        "",
        f"- Inspection: {code(mapping.get('state'))} - "
        f"{markdown_text(mapping.get('reason'))}",
        f"- Issue Types: {code(mapping.get('issue_type_state'))}; labels: "
        f"{code(mapping.get('label_state'))}.",
        f"- Review choice: {code(mapping.get('review'))}.",
        "",
        "Defaults:",
        "",
        *_table(mapping.get("defaults")),
        "",
        "Existing Issue Types:",
        "",
        *_table(mapping.get("issue_types")),
        "",
        "Existing labels:",
        "",
        *_table(mapping.get("labels")),
    ]
    return lines


def _product_lines(report: Mapping[str, object]) -> list[str]:
    product = cast(Mapping[str, object], report["product"])
    ownership = _optional_mapping(product["release_ownership"])
    owner = _optional_mapping(product["code_owner"])
    lines = [
        f"- Release ownership: {code(_field(ownership, 'ownership'))}",
        "- Selected release workflow: "
        f"{code(_field(ownership, 'selected_workflow'))}",
        "- Required release inputs: "
        f"{code(_field(ownership, 'required_inputs'))}",
        "- Release ownership reason: "
        f"{markdown_text(display(_field(ownership, 'reason')))}",
        f"- CODEOWNER: {code(_field(owner, 'value'))} "
        f"({code(_field(owner, 'state'))})",
    ]
    for key, title in PRODUCT_SUBSECTIONS:
        value = product[key]
        if value is None:
            continue
        lines.extend(["", f"### {title}", ""])
        if key == "work_item_mapping" and isinstance(value, Mapping):
            lines.extend(_mapping_lines(cast(Mapping[str, object], value)))
        elif isinstance(value, Mapping):
            lines.extend(
                f"- {markdown_text(name)}: {code(item)}"
                for name, item in sorted(
                    cast(Mapping[str, object], value).items()
                )
            )
        else:
            lines.extend(_table(value))
    return lines


def _verification_lines(report: Mapping[str, object]) -> list[str]:
    verification = cast(Mapping[str, object], report["verification"])
    candidate = _optional_mapping(verification["candidate"])
    hook = _optional_mapping(verification["hook"])
    parity = _optional_mapping(verification["render_parity"])
    return [
        f"- Candidate: {code(_field(candidate, 'state'))} - "
        f"{markdown_text(display(_field(candidate, 'reason')))}",
        f"- Project verification hook: {code(_field(hook, 'path'))} "
        f"(configured {code(_field(hook, 'configured'))}, result "
        f"{code(_field(hook, 'result'))}) - "
        f"{markdown_text(display(_field(hook, 'reason')))}",
        f"- Render parity: {code(_field(parity, 'state'))}",
    ]


def _next_step_lines(report: Mapping[str, object]) -> list[str]:
    steps = cast(list[Mapping[str, object]], report["next_steps"])
    if not steps:
        return ["None."]
    lines = []
    for index, step in enumerate(steps, start=1):
        line = f"{index}. {markdown_text(step['text'])}"
        if step["command"] is not None:
            line += f" {code(step['command'])}"
        lines.append(line)
    return lines


def render_markdown(report: object) -> str:
    """Render the human report from one validated report JSON object."""
    value = validate_report(report)
    operation = str(value["operation"])
    status = str(value["status"])
    title = "adoption" if operation == "adopt" else "update"
    sections = (
        _decision_lines(value),
        _snapshot_lines(value),
        _summary_lines(value),
        _impact_lines(value),
        _file_lines(value),
        _setting_lines(value),
        _product_lines(value),
        _verification_lines(value),
        _next_step_lines(value),
    )
    lines = [
        f"# CSARC {title} report",
        "",
        f"> **Status: {BANNERS[operation][status]}.** "
        f"{markdown_text(value['status_reason'])}",
        "",
        f"Report format version: `{value['report_format_version']}`",
    ]
    for heading, body in zip(SECTION_HEADINGS, sections, strict=True):
        lines.extend(["", f"## {heading}", "", *body])
    return "\n".join(lines) + "\n"
