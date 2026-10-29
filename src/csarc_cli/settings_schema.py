"""SPEC-009 settings classification, migration registry, and provenance.

Issue #1071 (Q1). `.csarc/config.yml` keeps only persistent intent: values
that change later behavior and cannot be safely reconstructed. Everything
else a render consumed is classified here once, closed over every key any
release ever asked:

* one-time seeds and live repository facts are never saved as settings;
* derived context is recomputed, and saved only as an explicit one-time
  decision when no native source resolves it;
* the immutable ``project_mode`` and the resolved render context live in
  `.csarc/provenance.json`, bound to the settings file by digests so a hand
  edit, a missing record, or a contradiction fails closed before any write;
* every retired key is read only by this pinned CLI's migration registry,
  never by repository scripts, and the migration writes only schema 2.

The repository's own current-only parser (`csarc_config.py`) enforces the
same persistent-intent table; a conformance test keeps both equal to the
SPEC-009 tables.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore[import-untyped]

SCHEMA_KEY = "schema_version"
SCHEMA_VERSION = 2
LEGACY_SCHEMA = 1
COPIER_METADATA_KEYS = ("_commit", "_src_path")
CONFIG_HEADER = (
    "# CSARC repository settings (SPEC-009 schema 2). Change them only "
    "through csarc update --data KEY=VALUE.\n"
)
# The pinned CLI asks the template to render its resolved context here so
# provenance records the exact seeds and facts the render consumed. The
# file never reaches a target: the CLI reads and removes it right away.
RENDER_CONTEXT_FLAG = "csarc_render_context"
RENDER_CONTEXT_FILE = Path(".csarc/render-context.json")
SETTINGS_ERROR_PREFIX = "CSARC settings error"

CLASS_INTENT = "persistent-intent"
CLASS_DECISION = "derived-decision"
CLASS_SEED = "one-time-seed"
CLASS_LIVE = "live-fact"
CLASS_DERIVED = "derived-context"
CLASS_METADATA = "machine-metadata"
CLASS_RENDER = "render-derived"
CLASS_RETIRED = "retired"

CHOICE = "choice"
MULTI = "multi"
BOOL = "bool"
INT = "int"
TEXT = "text"
MAP = "map"

# Persistent intent: kind and allowed values (SPEC-009 settings table).
INTENT_SETTINGS: dict[str, tuple[str, tuple[str, ...]]] = {
    "languages": (MULTI, ("go", "python", "rust", "typescript")),
    "python_floor": (CHOICE, ("latest", "3.12", "3.13", "3.14")),
    "documentation_mode": (
        CHOICE,
        ("template-and-content", "content-only", "off"),
    ),
    "documentation_languages": (
        CHOICE,
        ("zh-tw", "en", "zh-tw+en", "en+zh-tw"),
    ),
    "verification_mode_private": (CHOICE, ("self-hosted", "hosted", "local")),
    "verification_mode_public": (CHOICE, ("hosted", "local")),
    "admin_bypass": (CHOICE, ("off", "beta-only", "always")),
    "copilot_review": (CHOICE, ("allowed", "off")),
    "governance_mode": (CHOICE, ("managed", "observe")),
    "release_ownership": (
        CHOICE,
        ("csarc-owned", "product-owned", "verification-only"),
    ),
    "release_trigger": (CHOICE, ("main", "manual")),
    "project_maturity": (CHOICE, ("early", "formal")),
    "code_owner": (TEXT, ()),
    "enable_codeql": (BOOL, ()),
    "scheduled_checks": (MULTI, ("governance-drift", "template-update")),
    "lifecycle": (MULTI, ("issues", "milestones")),
    "coverage_mode": (CHOICE, ("global", "diff")),
    "coverage_threshold": (INT, ()),
    "security_reporting_channel": (TEXT, ()),
    "container": (BOOL, ()),
    "project_verification_hook": (TEXT, ()),
    "github_project_url": (TEXT, ()),
    "single_writer_merger": (TEXT, ()),
    "self_hosted_runner": (MAP, ("id", "registration")),
    "self_hosted_environments": (MULTI, ("dev", "uat")),
}
# SPEC-011: the registration keys exist exactly when the private mode is
# self-hosted; ``{}`` is the valid "not yet registered" runner.
SELF_HOSTED_KEYS = ("self_hosted_runner", "self_hosted_environments")
# Until csarc-devops confirms an isolated Docker daemon inside each job
# container (ADR D8, C11), container cannot verify in self-hosted mode.
CONTAINER_SELF_HOSTED = (
    "container needs Docker, which self-hosted verification lacks (ADR "
    "self-hosted-verification D8); set verification_mode_private to local "
    "or hosted, or container to false"
)
# SPEC-011 transition (#1069 decision 8): the one legacy mode key stays
# valid, alone, until the target's trusted base reads both visibility
# settings; it means the same mode for both visibilities.
LEGACY_MODE = "verification_mode"
MODE_KEYS = ("verification_mode_private", "verification_mode_public")
RUNNER = re.compile(
    r"[a-z0-9][a-z0-9-]{0,31} "
    r"https://github\.com/[A-Za-z0-9-]+/csarc-devops/issues/[1-9][0-9]*"
)
# Optional intent and its default when absent: #1080 added it after older
# readers, which reject unknown keys, so a schema 2 file may omit it.
OPTIONAL_DEFAULTS: dict[str, object] = {
    "github_project_url": "",
    "single_writer_merger": "",
}
# Issue #1298: saved intent whose Copier question is `when: false`. Copier
# drops the last answer of such a question on update and renders its
# default, so `csarc update` forwards each saved value as update data.
# M21 registration keys must also survive stable-to-beta updates (#1304).
# The only other `when: false` questions are RENDER_KEYS, recomputed from
# documentation_languages on every render and never saved.
HIDDEN_SETTINGS = (
    *SELF_HOSTED_KEYS,
    "github_project_url",
    "release_ownership",
    "single_writer_merger",
)
# K2 (#1080): only the full organization or user ProjectV2 URL is saved;
# project, field, and item IDs are always resolved live.
PROJECT_URL = re.compile(
    r"^https://github\.com/(?P<kind>orgs|users)/(?P<login>[A-Za-z0-9-]+)"
    r"/projects/(?P<number>[1-9][0-9]*)$"
)
# Issue #1233: the opted-in single-writer merger is one GitHub user login.
GITHUB_LOGIN = re.compile(r"^(?=.{1,39}$)[A-Za-z0-9](?:-?[A-Za-z0-9])*$")
DECISION_SETTINGS: dict[str, tuple[str, tuple[str, ...]]] = {
    "package_name": (TEXT, ()),
    "project_run_command": (TEXT, ()),
}
SEED_KEYS = (
    "copyright_holder",
    "project_description",
    "project_license",
    "project_name",
)
LIVE_KEYS = ("project_visibility", "repository_url")
DERIVED_KEYS = ("package_name", "project_run_command", "project_slug")
METADATA_KEYS = (SCHEMA_KEY, *COPIER_METADATA_KEYS, "project_mode")
RENDER_KEYS = (
    "documentation_primary_language",
    "documentation_secondary_language",
    # SPEC-011: the effective mode for the render's visibility.
    "verification_mode",
)
# The resolved render context recorded in provenance: what a render
# consumed beyond the saved intent.
CONTEXT_KEYS = tuple(
    sorted({*SEED_KEYS, *LIVE_KEYS, *DERIVED_KEYS, "project_mode"})
)

# Every key a release ever asked that schema 2 no longer stores, with the
# current key that carries its intent (None when nothing does).
RETIRED_SETTINGS: dict[str, str | None] = {
    "actions_fallback": None,
    "branch_strategy": None,
    "container_mode": "container",
    "container_smoke_command": None,
    "containerfile_path": None,
    "copilot_review_max_level": "copilot_review",
    "default_release_level": "project_maturity",
    "enable_attestations": None,
    "enable_docker": "container",
    "enable_governance_drift_check": "scheduled_checks",
    "enable_npm_publishing": None,
    "enable_precommit": None,
    "enable_pypi_publishing": None,
    "enable_release_attestations": None,
    "enable_template_update_notifications": "scheduled_checks",
    "features": "container",
    "i18n": "documentation_languages",
    "language": "languages",
    "npm_environment": None,
    "policy_actions_permissions": "governance_mode",
    "policy_branch_ruleset": "governance_mode",
    "policy_labels": "governance_mode",
    "policy_repository_settings": "governance_mode",
    "pr_review_mode": "copilot_review",
    "primary_language": "documentation_languages",
    "pypi_environment": None,
    "python_min_version": "python_floor",
    "python_support_mode": "python_floor",
    "readme_primary_language": "documentation_languages",
    "release_immutable_releases": None,
    "release_level_alpha_review": "admin_bypass",
    "release_level_alpha_verification": None,
    "release_level_beta_review": "admin_bypass",
    "release_level_beta_verification": None,
    "release_level_early_review": "admin_bypass",
    "release_level_early_verification": None,
    "release_level_formal_review": "admin_bypass",
    "release_level_formal_verification": None,
    "release_levels_enabled": None,
    "release_ownership_reason": None,
    "release_required_inputs": None,
    "release_settings_owner": None,
    "release_workflow": None,
    "review": "admin_bypass",
    "reviewers": None,
    "use_reusable_workflow": None,
    "work_item_mapping_review": None,
    "workflow_ref": None,
}


# Release observations older releases saved; the CLI recomputes them in
# memory from the release owner, so reports never list them as answers.
RELEASE_OBSERVATIONS = frozenset(
    {
        "release_immutable_releases",
        "release_ownership_reason",
        "release_required_inputs",
        "release_settings_owner",
        "release_workflow",
    }
)
# Retired from the settings file but still accepted once as `--data`.
ONE_TIME_INPUTS = frozenset({"work_item_mapping_review"})
# Retired keys older repo-site content could show as `[[key]]` tokens. The
# site engines (`render_site.py` RETIRED_CONFIG_TOKENS) stop on them, and an
# update's retired row names the replacement token (Issue #1090).
RETIRED_SITE_TOKENS = frozenset(
    {
        "branch_strategy",
        "features",
        "i18n",
        "primary_language",
        "review",
        "reviewers",
    }
)


def classification() -> dict[str, str]:
    """Return the closed SPEC-009 class of every known key."""
    classes: dict[str, str] = {}
    classes.update(dict.fromkeys(INTENT_SETTINGS, CLASS_INTENT))
    classes.update(dict.fromkeys(SEED_KEYS, CLASS_SEED))
    classes.update(dict.fromkeys(LIVE_KEYS, CLASS_LIVE))
    classes.update(dict.fromkeys(DERIVED_KEYS, CLASS_DERIVED))
    classes.update(dict.fromkeys(DECISION_SETTINGS, CLASS_DECISION))
    classes.update(dict.fromkeys(METADATA_KEYS, CLASS_METADATA))
    classes.update(dict.fromkeys(RENDER_KEYS, CLASS_RENDER))
    classes.update(dict.fromkeys(RETIRED_SETTINGS, CLASS_RETIRED))
    return classes


class SettingsSchemaError(ValueError):
    """Saved settings or their provenance cannot be trusted; nothing ran."""


def canonical_digest(value: object) -> str:
    """Return a stable SHA-256 digest of one JSON-compatible value."""
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def settings_error(detail: str) -> SettingsSchemaError:
    """Return one stable fail-closed error with the recovery path."""
    return SettingsSchemaError(
        f"{SETTINGS_ERROR_PREFIX}: {detail}. No file was changed. Run 'git "
        "checkout -- .csarc/config.yml .csarc/provenance.json', then change "
        "settings only with 'csarc update --data KEY=VALUE'."
    )


def declared_schema(raw: Mapping[str, object]) -> int:
    """Return 1 for a legacy answers file, 2 for current, else fail closed.

    An unknown or malformed ``schema_version`` (for example one written by
    a newer CLI) stops before any write instead of being normalized.
    """
    if SCHEMA_KEY not in raw:
        return LEGACY_SCHEMA
    value = raw[SCHEMA_KEY]
    if type(value) is int and value == SCHEMA_VERSION:
        return SCHEMA_VERSION
    raise SettingsSchemaError(
        f"{SETTINGS_ERROR_PREFIX}: .csarc/config.yml declares "
        f"{SCHEMA_KEY} {value!r}: this CLI reads only legacy answers and "
        f"schema {SCHEMA_VERSION}. No file was changed. Install the CLI "
        "release that wrote this schema."
    )


def _validate_value(key: str, value: object) -> None:
    """Validate one schema 2 value against its kind and allowed values."""
    kind, allowed = {**INTENT_SETTINGS, **DECISION_SETTINGS}[key]
    valid = True
    if kind == CHOICE:
        valid = isinstance(value, str) and value in allowed
    elif kind == MULTI:
        valid = (
            isinstance(value, list)
            and all(isinstance(item, str) and item in allowed for item in value)
            and len(value) == len(set(value))
        )
    elif kind == BOOL:
        valid = isinstance(value, bool)
    elif kind == INT:
        valid = type(value) is int and 1 <= value <= 100
    elif kind == MAP:
        valid = value == {} or (
            isinstance(value, Mapping)
            and len(value) == 2
            and RUNNER.fullmatch(
                f"{value.get('id')} {value.get('registration')}"
            )
            is not None
        )
    else:
        pattern = {
            "github_project_url": PROJECT_URL,
            "single_writer_merger": GITHUB_LOGIN,
        }.get(key)
        valid = isinstance(value, str) and (
            pattern is None or not value or pattern.fullmatch(value) is not None
        )
    if not valid:
        expected = ", ".join(allowed) if allowed else kind
        raise settings_error(
            f"{key} is {value!r} in .csarc/config.yml; expected {expected}"
        )


def verification_modes(raw: Mapping[str, object]) -> dict[str, object]:
    """Return both visibility modes, reading the legacy key (SPEC-011)."""
    if LEGACY_MODE not in raw:
        return {key: raw[key] for key in MODE_KEYS if key in raw}
    legacy = raw[LEGACY_MODE]
    if legacy not in ("local", "hosted") or set(MODE_KEYS) & set(raw):
        raise settings_error(
            f"{LEGACY_MODE} is {legacy!r} in .csarc/config.yml; expected "
            "local or hosted, without verification_mode_private or "
            "verification_mode_public"
        )
    return dict.fromkeys(MODE_KEYS, legacy)


def _validate_self_hosted(raw: Mapping[str, object]) -> None:
    """Require the registration keys exactly for a self-hosted mode."""
    modes = verification_modes(raw)
    self_hosted = modes.get("verification_mode_private") == "self-hosted"
    present = [key for key in SELF_HOSTED_KEYS if key in raw]
    if present != (list(SELF_HOSTED_KEYS) if self_hosted else []) or (
        self_hosted and raw["self_hosted_environments"] == []
    ):
        raise settings_error(
            "self_hosted_runner and a non-empty self_hosted_environments "
            "are required exactly when verification_mode_private is "
            "self-hosted in .csarc/config.yml"
        )
    if self_hosted and raw.get("container") is True:
        # The VM gives jobs no Docker daemon yet (ADR D8, #1281).
        raise settings_error(CONTAINER_SELF_HOSTED)


def validate_current(raw: Mapping[str, object]) -> None:
    """Fail closed unless ``raw`` is exactly a valid schema 2 file."""
    allowed = {
        SCHEMA_KEY,
        LEGACY_MODE,
        *COPIER_METADATA_KEYS,
        *INTENT_SETTINGS,
        *DECISION_SETTINGS,
    }
    unknown = sorted(str(key) for key in raw if key not in allowed)
    if unknown:
        raise settings_error(
            "unknown or retired settings in .csarc/config.yml: "
            + ", ".join(unknown)
        )
    _validate_self_hosted(raw)
    present = {*raw, *verification_modes(raw)}
    missing = sorted(
        key
        for key in INTENT_SETTINGS
        if key not in present
        and key not in OPTIONAL_DEFAULTS
        and key not in SELF_HOSTED_KEYS
    )
    if missing:
        raise settings_error(
            "missing persistent settings in .csarc/config.yml: "
            + ", ".join(missing)
        )
    for key in (*INTENT_SETTINGS, *DECISION_SETTINGS):
        if key in raw:
            _validate_value(key, raw[key])


def config_text(values: Mapping[str, object]) -> str:
    """Return the one canonical schema 2 settings file for ``values``.

    Only schema 2 keys are written; the dump never folds long values so
    the repository's flat-scalar reader sees each setting on one line.
    """
    allowed = (
        SCHEMA_KEY,
        LEGACY_MODE,
        *COPIER_METADATA_KEYS,
        *INTENT_SETTINGS,
        *DECISION_SETTINGS,
    )
    payload = {key: values[key] for key in sorted(allowed) if key in values}
    payload[SCHEMA_KEY] = SCHEMA_VERSION
    validate_current(payload)
    return CONFIG_HEADER + yaml.safe_dump(
        dict(sorted(payload.items())),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
        width=1_000_000,
    )


def context_from(answers: Mapping[str, object]) -> dict[str, object]:
    """Return the resolved render context recorded in provenance."""
    return {key: answers[key] for key in CONTEXT_KEYS if key in answers}


def settings_record(
    context: Mapping[str, object], config_bytes: bytes
) -> dict[str, object]:
    """Bind the saved settings and the render context in provenance."""
    record: dict[str, object] = {
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "context": dict(sorted(context.items())),
        "context_sha256": canonical_digest(dict(context)),
        "project_mode": context.get("project_mode"),
        SCHEMA_KEY: SCHEMA_VERSION,
    }
    record["record_sha256"] = canonical_digest(record)
    return record


def verified_context(
    provenance: Mapping[str, object] | None, config_bytes: bytes
) -> dict[str, object]:
    """Return the trusted render context or fail closed (AC4).

    The settings record must exist, carry schema 2, match its own digest,
    match the context digest, name the immutable project mode, and match
    the exact settings bytes; any hand edit or contradiction stops here.
    """
    if provenance is None:
        raise settings_error(
            ".csarc/provenance.json is missing; schema 2 settings need the "
            "CLI-written render context"
        )
    record = provenance.get("settings")
    if not isinstance(record, Mapping):
        raise settings_error(
            ".csarc/provenance.json has no settings record for schema 2"
        )
    body = {
        key: value for key, value in record.items() if key != "record_sha256"
    }
    if record.get(SCHEMA_KEY) != SCHEMA_VERSION:
        raise settings_error("the provenance settings record is not schema 2")
    if record.get("record_sha256") != canonical_digest(body):
        raise settings_error(
            "the provenance settings record was edited by hand"
        )
    context = record.get("context")
    if not isinstance(context, Mapping) or record.get(
        "context_sha256"
    ) != canonical_digest(dict(context)):
        raise settings_error("the provenance render context digest is wrong")
    unknown = sorted(key for key in context if key not in CONTEXT_KEYS)
    if unknown:
        raise settings_error(
            "the provenance render context has unknown keys: "
            + ", ".join(unknown)
        )
    mode = context.get("project_mode")
    if mode not in {"new", "existing"} or record.get("project_mode") != mode:
        raise settings_error(
            "the provenance project_mode is missing or contradictory"
        )
    if record.get("config_sha256") != hashlib.sha256(config_bytes).hexdigest():
        raise settings_error(
            ".csarc/config.yml does not match its provenance digest (hand "
            "edit or partial write)"
        )
    return dict(context)


@dataclass(frozen=True)
class SavedSettings:
    """One trusted reading of a target's saved settings."""

    schema: int
    raw: Mapping[str, object]
    answers: Mapping[str, object]
    context: Mapping[str, object] = field(default_factory=dict)
    decisions: Mapping[str, object] = field(default_factory=dict)


def read_saved_settings(
    config_path: Path, provenance: Mapping[str, object] | None
) -> SavedSettings:
    """Read legacy answers for migration, or verify current settings.

    Legacy answers are returned unchanged for the migration registry; they
    are never normalized here. Schema 2 settings are validated and joined
    with the verified provenance context into the full answers view the
    old side of an update needs.
    """
    try:
        config_bytes = config_path.read_bytes()
        raw = yaml.safe_load(config_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise settings_error(
            f"cannot read {config_path.name}: {error}"
        ) from error
    if not isinstance(raw, dict):
        raise settings_error(f"{config_path.name} must be a mapping")
    raw = {str(key): value for key, value in raw.items()}
    schema = declared_schema(raw)
    if schema == LEGACY_SCHEMA:
        answers = {
            key: value for key, value in raw.items() if not key.startswith("_")
        }
        return SavedSettings(schema, raw, answers)
    validate_current(raw)
    context = verified_context(provenance, config_bytes)
    decisions = {key: raw[key] for key in DECISION_SETTINGS if key in raw}
    answers: dict[str, object] = dict(context)
    answers.update(
        (key, value)
        for key, value in raw.items()
        if not key.startswith("_") and key != SCHEMA_KEY
    )
    return SavedSettings(schema, raw, answers, context, decisions)


# ---------------------------------------------------------------------------
# Migration registry for the non-governance keys (#1058 decision 3).
# Governance keys follow governance_migration's approved mapping.
# ---------------------------------------------------------------------------

LEGACY_DOCUMENTATION_LANGUAGES = {
    ("zh-tw", "en-zh-tw"): "zh-tw+en",
    ("en", "en-zh-tw"): "en+zh-tw",
    ("zh-tw", "off"): "zh-tw",
    ("en", "off"): "en",
}
CODEQL_LANGUAGES = frozenset({"go", "python", "typescript"})
PYTHON_FLOORS = ("3.12", "3.13", "3.14")


class MigrationDecisionError(SettingsSchemaError):
    """A legacy value has no exact current equivalent; decide explicitly."""


def legacy_languages(answers: Mapping[str, object]) -> list[str]:
    """Map ``languages`` or the single legacy ``language`` value."""
    languages = answers.get("languages")
    if isinstance(languages, list):
        return [str(item) for item in languages]
    language = answers.get("language", "python")
    if language == "ci":
        return []
    return [part for part in str(language).split("-") if part]


def legacy_python_floor(answers: Mapping[str, object]) -> str:
    """Map ``python_support_mode`` and ``python_min_version`` exactly."""
    mode = answers.get("python_support_mode", "latest")
    if mode == "latest":
        return "latest"
    version = str(answers.get("python_min_version", "3.12"))
    if mode == "minimum" and version in PYTHON_FLOORS:
        return version
    raise MigrationDecisionError(
        f"{SETTINGS_ERROR_PREFIX}: python_support_mode {mode!r} with "
        f"python_min_version {version!r} has no exact python_floor. Pass "
        "'--data python_floor=<latest|3.12|3.13|3.14>'."
    )


def legacy_documentation_languages(answers: Mapping[str, object]) -> str:
    """Join ``primary_language`` and ``i18n`` into one current value."""
    primary = answers.get(
        "primary_language", answers.get("readme_primary_language", "zh-tw")
    )
    i18n = answers.get("i18n", "en-zh-tw")
    value = LEGACY_DOCUMENTATION_LANGUAGES.get((str(primary), str(i18n)))
    if value is None:
        raise MigrationDecisionError(
            f"{SETTINGS_ERROR_PREFIX}: primary_language {primary!r} with "
            f"i18n {i18n!r} has no exact documentation_languages. Pass "
            "'--data documentation_languages=<zh-tw|en|zh-tw+en|en+zh-tw>'."
        )
    return value


def legacy_documentation_mode(answers: Mapping[str, object]) -> str:
    """Map the legacy ``features: repo-site`` toggle (#919)."""
    features = answers.get("features")
    if isinstance(features, list):
        return (
            "template-and-content"
            if "repo-site" in features
            else "content-only"
        )
    return "template-and-content"


def legacy_container(answers: Mapping[str, object]) -> bool:
    """Map ``features: docker``, ``enable_docker``, or ``container_mode``."""
    features = answers.get("features")
    if isinstance(features, list):
        return "docker" in features
    if "enable_docker" in answers:
        return answers.get("enable_docker") is True
    return answers.get("container_mode", "none") not in {None, "none"}


def legacy_scheduled_checks(answers: Mapping[str, object]) -> list[str]:
    """Map the two legacy schedule toggles with their old defaults."""
    checks: list[str] = []
    if answers.get("enable_governance_drift_check", True) is True:
        checks.append("governance-drift")
    if answers.get("enable_template_update_notifications", False) is True:
        checks.append("template-update")
    return checks


def legacy_enable_codeql(answers: Mapping[str, object]) -> bool:
    """Derive a missing CodeQL choice with the old template's own rule."""
    languages = set(legacy_languages(answers))
    return answers.get("project_visibility") == "public" and bool(
        languages & CODEQL_LANGUAGES
    )


def migrated_intent(answers: Mapping[str, object]) -> dict[str, object]:
    """Return schema 2 values a legacy answers file implies.

    Only keys the legacy file does not already state are returned; a saved
    current-named value always wins. A value without an exact equivalent
    raises :class:`MigrationDecisionError` so the update stops before any
    write and asks for an explicit ``--data`` decision.
    """
    derived: dict[str, object] = {
        "languages": legacy_languages(answers),
        "python_floor": legacy_python_floor(answers),
        "documentation_languages": legacy_documentation_languages(answers),
        "documentation_mode": legacy_documentation_mode(answers),
        "container": legacy_container(answers),
        "scheduled_checks": legacy_scheduled_checks(answers),
        "enable_codeql": legacy_enable_codeql(answers),
        "project_verification_hook": "",
        "github_project_url": "",
    }
    return {key: value for key, value in derived.items() if key not in answers}


def retired_keys(answers: Mapping[str, object]) -> list[str]:
    """Return the saved keys schema 2 no longer stores."""
    return sorted(key for key in answers if key in RETIRED_SETTINGS)


def reject_retired_data(explicit: Mapping[str, object]) -> None:
    """Refuse ``--data`` for a retired key before any write.

    One-time inputs that were once saved, such as adopt's work-item mapping
    review, remain valid ``--data`` but never reach the settings file.
    """
    if LEGACY_MODE in explicit:
        raise SettingsSchemaError(
            f"{SETTINGS_ERROR_PREFIX}: --data names {LEGACY_MODE}, which "
            "now has one setting per visibility. No file was changed. Pass "
            "'--data verification_mode_private=<self-hosted|hosted|local>' "
            "or '--data verification_mode_public=<hosted|local>'."
        )
    retired = sorted(
        key
        for key in explicit
        if key in RETIRED_SETTINGS and key not in ONE_TIME_INPUTS
    )
    if retired:
        hints = [
            f"{key} (use {RETIRED_SETTINGS[key]})"
            if RETIRED_SETTINGS[key]
            else f"{key} (retired without a successor)"
            for key in retired
        ]
        raise SettingsSchemaError(
            f"{SETTINGS_ERROR_PREFIX}: --data names retired settings: "
            + ", ".join(hints)
            + ". No file was changed. Remove them, or pass the listed "
            "successor with '--data'."
        )
