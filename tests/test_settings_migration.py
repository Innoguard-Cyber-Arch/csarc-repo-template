"""SPEC-009 schema reader/writer matrix and migration fixtures (#1071).

Real answers files rendered from release tags v0.3.1, v0.16.0, v0.22.0,
v0.30.3 and the beta.1 base (Python latest and 3.12) are read only by the
pinned CLI's migration registry. The migrated schema 2 file, the root
settings, and a current-next schema 2 file must then pass the CLI, the root
and generated current-only parsers, and the G2 trusted-base reader; legacy
and unknown schemas fail closed in every repository reader.
"""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest
import yaml

from csarc_cli import governance_migration, settings_schema

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests/fixtures/settings"
LEGACY_FIXTURES = (
    "v0.3.1",
    "v0.16.0",
    "v0.22.0",
    "v0.30.3",
    "beta.1",
    "beta.1-python-3.12",
)
RUNTIME = {
    "root": runpy.run_path(str(ROOT / "scripts/csarc_config.py")),
    "generated": runpy.run_path(
        str(ROOT / "template/.csarc/scripts/csarc_config.py")
    ),
}
EXECUTOR = runpy.run_path(str(ROOT / "scripts/trusted_executor.py"))
# Values the update resolves from the repository or the new template rather
# than from the legacy answers: the single release writer (#1068) and the
# template's own reporting-channel default (#1084).
NEW_SIDE = {
    "release_ownership": "csarc-owned",
    "security_reporting_channel": (
        "Open a GitHub Issue at https://github.com/example/fixture-product"
        "/issues/new; maintainers receive notifications for new Issues."
    ),
}


def legacy(name: str) -> dict[str, Any]:
    """Load one legacy answers fixture as Copier wrote it."""
    payload = yaml.safe_load((FIXTURES / f"{name}.yml").read_text())
    assert isinstance(payload, dict)
    return payload


def migrate(answers: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """Compose the registry exactly as `csarc update` does.

    Saved current-named intent wins; missing governance keys follow the
    approved mapping; every other successor comes from the SPEC-009
    registry. Returns the schema 2 intent and the keys the new side fills.
    """
    saved = {
        key: value for key, value in answers.items() if not key.startswith("_")
    }
    intent = {
        key: value
        for key, value in saved.items()
        if key in settings_schema.INTENT_SETTINGS
    }
    for key, value in governance_migration.legacy_governance_values(
        saved
    ).items():
        intent.setdefault(key, value)
    for key, value in settings_schema.migrated_intent(saved).items():
        intent.setdefault(key, value)
    filled = {key for key in NEW_SIDE if key not in intent}
    for key in filled:
        intent[key] = NEW_SIDE[key]
    return intent, filled


def write(path: Path, values: dict[str, Any]) -> Path:
    """Write one canonical schema 2 settings file."""
    path.write_text(settings_schema.config_text(values), encoding="utf-8")
    return path


@pytest.mark.parametrize("name", LEGACY_FIXTURES)
def test_repository_readers_reject_legacy_settings(
    name: str, tmp_path: Path
) -> None:
    """AC3: only the CLI registry reads legacy answers; scripts fail closed."""
    path = tmp_path / "config.yml"
    path.write_text((FIXTURES / f"{name}.yml").read_text(), encoding="utf-8")
    for runtime in RUNTIME.values():
        with pytest.raises(ValueError, match="legacy settings schema"):
            runtime["load_config"](path)
    with pytest.raises(ValueError, match="reads schema 2 only"):
        EXECUTOR["read_config"](path)
    saved = settings_schema.read_saved_settings(path, None)
    assert saved.schema == settings_schema.LEGACY_SCHEMA
    assert dict(saved.answers) == {
        key: value
        for key, value in legacy(name).items()
        if not key.startswith("_")
    }


EXPECTED = {
    "v0.3.1": {
        "admin_bypass": "always",
        "container": False,
        "documentation_languages": "zh-tw+en",
        "documentation_mode": "template-and-content",
        "governance_mode": "managed",
        "languages": ["python"],
        "python_floor": "latest",
        "scheduled_checks": [],
        "verification_mode_private": "hosted",
        "verification_mode_public": "hosted",
    },
    "v0.16.0": {
        "admin_bypass": "always",
        "container": False,
        "copilot_review": "allowed",
        "documentation_languages": "zh-tw+en",
        "governance_mode": "managed",
        "languages": ["python"],
        "scheduled_checks": [],
    },
    "v0.22.0": {
        "admin_bypass": "off",
        "container": False,
        "documentation_languages": "zh-tw+en",
        "documentation_mode": "template-and-content",
        "scheduled_checks": ["governance-drift"],
        "verification_mode_private": "local",
        "verification_mode_public": "local",
    },
    "v0.30.3": {
        "admin_bypass": "off",
        "container": False,
        "documentation_languages": "zh-tw+en",
        "documentation_mode": "template-and-content",
        "python_floor": "latest",
        "scheduled_checks": ["governance-drift"],
    },
    "beta.1": {
        "admin_bypass": "always",
        "python_floor": "latest",
        "scheduled_checks": ["governance-drift"],
    },
    "beta.1-python-3.12": {"python_floor": "3.12"},
}


@pytest.mark.parametrize("name", LEGACY_FIXTURES)
def test_registry_writes_only_schema_2(name: str, tmp_path: Path) -> None:
    """AC3/AC7: each legacy shape migrates to one schema 2 file every
    current reader accepts, with retired and successor report rows."""
    answers = legacy(name)
    intent, filled = migrate(answers)
    assert filled <= set(NEW_SIDE)
    for key, value in EXPECTED[name].items():
        assert intent[key] == value, key
    values = {
        "_commit": "0" * 40,
        "_src_path": "https://github.com/Innoguard-Cyber-Arch/csarc-repo-template",
        **intent,
    }
    path = write(tmp_path / "config.yml", values)
    text = path.read_text(encoding="utf-8")
    for retired in settings_schema.RETIRED_SETTINGS:
        assert f"\n{retired}:" not in text
    for runtime in RUNTIME.values():
        assert runtime["load_config"](path)["schema_version"] == 2
    assert EXECUTOR["read_config"](path)["languages"] == intent["languages"]
    settings_schema.validate_current(yaml.safe_load(text))
    saved = {
        key: value for key, value in answers.items() if not key.startswith("_")
    }
    classes = governance_migration.setting_classes(saved, intent)
    for key in settings_schema.retired_keys(saved):
        assert classes[key][0] == "retired", key
    for key, (setting_class, _note) in classes.items():
        if key in intent and key not in saved:
            assert setting_class in {"exact", "narrowed", "widened"}, key


def test_python_and_language_mappings_without_equivalent_need_a_decision() -> (
    None
):
    """AC3: a value without an exact successor stops before any write."""
    with pytest.raises(
        settings_schema.MigrationDecisionError, match="python_floor"
    ):
        settings_schema.migrated_intent(
            {"python_support_mode": "minimum", "python_min_version": "3.11"}
        )
    with pytest.raises(
        settings_schema.MigrationDecisionError, match="documentation_languages"
    ):
        settings_schema.migrated_intent({"primary_language": "fr"})


def test_retired_data_is_refused_before_any_write() -> None:
    """A retired --data key names its successor and changes nothing."""
    with pytest.raises(
        settings_schema.SettingsSchemaError, match=r"primary_language \(use"
    ):
        settings_schema.reject_retired_data({"primary_language": "en"})
    settings_schema.reject_retired_data({"documentation_languages": "en"})


def test_root_settings_are_schema_2() -> None:
    """AC7: the template repository's own settings use the current schema."""
    path = ROOT / ".csarc/config.yml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    settings_schema.validate_current(raw)
    for runtime in RUNTIME.values():
        assert runtime["load_config"](path)["release_trigger"] == "manual"
    assert EXECUTOR["read_config"](path)["verification_mode_public"] == "hosted"
    facts = RUNTIME["root"]["project_facts"](ROOT)
    assert facts["project_license"] == "proprietary"
    assert facts["copyright_holder"] == "Innoguard Cyber Arch"
    # The README seed names the product; the manifest names the slug.
    assert facts["project_name"] == "CSARC Repo Template"
    assert facts["project_slug"] == "csarc-repo-template"


CURRENT_NEXT = {
    "_commit": "1" * 40,
    "_src_path": "https://github.com/Innoguard-Cyber-Arch/csarc-repo-template",
    "admin_bypass": "always",
    "code_owner": "",
    "container": False,
    "copilot_review": "allowed",
    "coverage_mode": "global",
    "coverage_threshold": 80,
    "documentation_languages": "zh-tw",
    "documentation_mode": "content-only",
    "enable_codeql": False,
    "governance_mode": "managed",
    "languages": ["python"],
    "lifecycle": [],
    "project_maturity": "early",
    "github_project_url": "",
    "project_verification_hook": "",
    "python_floor": "3.12",
    "release_ownership": "csarc-owned",
    "release_trigger": "main",
    "scheduled_checks": [],
    "security_reporting_channel": "security@example.com",
    "verification_mode": "local",
}
CONTEXT = {
    "copyright_holder": "Example Owner",
    "package_name": "fixture_product",
    "project_description": "Fixture product.",
    "project_license": "MIT",
    "project_mode": "new",
    "project_name": "Fixture Product",
    "project_run_command": "uv run python -c 'import fixture_product'",
    "project_slug": "fixture-product",
    "project_visibility": "private",
    "repository_url": "https://github.com/example/fixture-product",
}


def current_target(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    """Write a current-next settings file and its provenance record."""
    path = write(tmp_path / "config.yml", CURRENT_NEXT)
    provenance = {
        "schema_version": 1,
        "settings": settings_schema.settings_record(CONTEXT, path.read_bytes()),
    }
    return path, provenance


def test_current_next_settings_round_trip(tmp_path: Path) -> None:
    """AC2/AC7: intent in the file, context only in provenance, one view."""
    path, provenance = current_target(tmp_path)
    text = path.read_text(encoding="utf-8")
    for key in settings_schema.CONTEXT_KEYS:
        assert f"\n{key}:" not in text
    saved = settings_schema.read_saved_settings(path, provenance)
    assert saved.schema == 2
    assert dict(saved.context) == CONTEXT
    assert saved.answers["project_mode"] == "new"
    assert saved.answers["python_floor"] == "3.12"
    for runtime in RUNTIME.values():
        assert runtime["load_config"](path)["python_floor"] == "3.12"
    assert EXECUTOR["read_config"](path)["lifecycle"] == []


def edited(record: dict[str, Any], **changes: object) -> dict[str, Any]:
    """Return a provenance with a hand-edited settings record."""
    settings = {**record["settings"], **changes}
    return {**record, "settings": settings}


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("hand-edited config", "does not match its provenance digest"),
        ("missing provenance", "provenance.json is missing"),
        ("missing record", "no settings record"),
        ("edited record", "edited by hand"),
        ("edited context", "edited by hand"),
        ("contradictory mode", "edited by hand"),
        ("unknown schema", r"declares schema_version 3"),
        ("retired key", "unknown or retired settings"),
        ("missing intent", "missing persistent settings"),
    ],
)
def test_status_and_update_fail_closed_before_writes(
    case: str, message: str, tmp_path: Path
) -> None:
    """AC4/AC6: tampering, gaps, unknown schemas, or contradictions stop."""
    path, provenance = current_target(tmp_path)
    if case == "hand-edited config":
        path.write_text(
            path.read_text().replace(
                "admin_bypass: always", "admin_bypass: 'off'"
            )
        )
    elif case == "missing record":
        provenance = {"schema_version": 1}
    elif case == "edited record":
        provenance = edited(provenance, config_sha256="0" * 64)
    elif case == "edited context":
        provenance = edited(
            provenance, context={**CONTEXT, "project_mode": "existing"}
        )
    elif case == "contradictory mode":
        provenance = edited(provenance, project_mode="existing")
    elif case == "unknown schema":
        path.write_text(
            path.read_text().replace("schema_version: 2", "schema_version: 3")
        )
    elif case == "retired key":
        path.write_text(path.read_text() + "actions_fallback: 'off'\n")
    elif case == "missing intent":
        path.write_text(path.read_text().replace("container: false\n", ""))
    with pytest.raises(settings_schema.SettingsSchemaError, match=message):
        settings_schema.read_saved_settings(
            path, None if case == "missing provenance" else provenance
        )


def test_unknown_schema_fails_closed_in_every_reader(tmp_path: Path) -> None:
    """AC6: a newer schema stops the runtime, G2, and CLI readers."""
    path, _provenance = current_target(tmp_path)
    path.write_text(
        path.read_text().replace("schema_version: 2", "schema_version: 3")
    )
    for runtime in RUNTIME.values():
        with pytest.raises(ValueError, match="accepts only schema 2"):
            runtime["load_config"](path)
    with pytest.raises(ValueError, match="reads schema 2 only"):
        EXECUTOR["read_config"](path)
    with pytest.raises(
        settings_schema.SettingsSchemaError, match="No file was changed"
    ):
        settings_schema.declared_schema(yaml.safe_load(path.read_text()))


def test_runtime_reads_seeds_from_native_sources(tmp_path: Path) -> None:
    """AC2: LICENSE and the manifest, never saved settings, hold seeds."""
    (tmp_path / "LICENSE").write_text(
        "MIT License\n\nCopyright (c) Example Owner\n\nPermission is granted.\n"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fixture-product"\ndescription = "Fixture."\n'
    )
    facts = RUNTIME["generated"]["project_facts"](tmp_path)
    assert facts["project_license"] == "MIT"
    assert facts["copyright_holder"] == "Example Owner"
    assert facts["project_name"] == "fixture-product"
    assert facts["project_description"] == "Fixture."
    (tmp_path / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE\n")
    assert RUNTIME["generated"]["license_facts"](tmp_path) == ("custom", "")


def test_settings_file_never_records_context(tmp_path: Path) -> None:
    """AC2: the canonical writer refuses seeds and live facts."""
    with pytest.raises(
        settings_schema.SettingsSchemaError, match="project_name"
    ):
        settings_schema.validate_current(
            {**CURRENT_NEXT, "schema_version": 2, "project_name": "x"}
        )
    text = settings_schema.config_text(
        {**CURRENT_NEXT, "project_name": "dropped"}
    )
    assert "project_name" not in text
    assert json.dumps(CONTEXT)  # the context is JSON-serializable provenance
