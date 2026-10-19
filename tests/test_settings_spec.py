"""SPEC-009 conformance: one settings classification everywhere (#1071 AC7).

The SPEC-009 tables, `copier.yml`, the answers and render-context
templates, the pinned CLI registry, and the root and generated current-only
parsers must agree key by key. Any one of them changing alone fails here.
No Copier render runs; the tables are parsed directly.
"""

from __future__ import annotations

import re
import runpy
import subprocess
from pathlib import Path

import pytest
import yaml

from csarc_cli import governance_migration, settings_schema

ROOT = Path(__file__).parents[1]
SPEC = ROOT / "docs/specs/SPEC-009-project-settings.md"
ANSWERS_TEMPLATE = ROOT / "template/{{ _copier_conf.answers_file }}.jinja"
CONTEXT_TEMPLATE = (
    ROOT
    / "template/.csarc"
    / "{% if csarc_render_context | default(false) %}render-context.json"
    "{% endif %}.jinja"
)
RUNTIME_PARSERS = (
    ROOT / "scripts/csarc_config.py",
    ROOT / "template/.csarc/scripts/csarc_config.py",
)
COPIER_METADATA = {"schema_version", "_src_path", "_commit"}


def table(marker: str) -> list[list[str]]:
    """Return the cells of one marker-delimited SPEC-009 table."""
    text = SPEC.read_text(encoding="utf-8")
    match = re.search(
        rf"<!-- {marker}:start -->(.*?)<!-- {marker}:end -->", text, re.S
    )
    assert match is not None, marker
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in match.group(1).splitlines()
        if line.startswith("|")
    ]
    return rows[2:]


def ticked(cell: str) -> list[str]:
    """Return every backticked value in one table cell."""
    return re.findall(r"`([^`]*)`", cell)


def spec_settings() -> dict[str, tuple[str, str, list[str]]]:
    """Return key -> (class, kind, values) from the settings table."""
    result: dict[str, tuple[str, str, list[str]]] = {}
    for key_cell, class_cell, kind_cell, values_cell, _source in table(
        "csarc-settings-table"
    ):
        (key,) = ticked(key_cell)
        assert key not in result, f"duplicate SPEC-009 row {key}"
        (class_name,) = ticked(class_cell)
        (kind,) = ticked(kind_cell)
        result[key] = (class_name, kind, ticked(values_cell))
    return result


def spec_retired() -> dict[str, str | None]:
    """Return retired key -> successor from the retired-keys table."""
    result: dict[str, str | None] = {}
    for key_cell, successor_cell, _mapping in table("csarc-retired-keys"):
        (key,) = ticked(key_cell)
        successor = ticked(successor_cell)
        result[key] = successor[0] if successor else None
    return result


def copier_questions() -> dict[str, dict[str, object]]:
    """Return every Copier question (non-underscore key)."""
    payload = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    return {
        key: value
        for key, value in payload.items()
        if not key.startswith("_") and isinstance(value, dict)
    }


def choice_values(question: dict[str, object]) -> set[str]:
    """Return a Copier question's choice values as strings."""
    choices = question["choices"]
    if isinstance(choices, dict):
        return {str(value) for value in choices.values()}
    assert isinstance(choices, list)
    return {str(value) for value in choices}


def test_classification_is_closed_and_matches_the_cli_registry() -> None:
    """AC1: one closed class per key, equal in SPEC-009 and the CLI."""
    settings = spec_settings()
    classes = settings_schema.classification()
    current = {
        key: value
        for key, value in classes.items()
        if value != settings_schema.CLASS_RETIRED
    }
    assert {key: row[0] for key, row in settings.items()} == current
    assert spec_retired() == settings_schema.RETIRED_SETTINGS
    assert governance_migration.RETIRED_SETTINGS is (
        settings_schema.RETIRED_SETTINGS
    )
    # The class set is closed and every class the AC names is used.
    assert {row[0] for row in settings.values()} == {
        settings_schema.CLASS_INTENT,
        settings_schema.CLASS_DECISION,
        settings_schema.CLASS_DERIVED,
        settings_schema.CLASS_SEED,
        settings_schema.CLASS_LIVE,
        settings_schema.CLASS_METADATA,
        settings_schema.CLASS_RENDER,
    }
    assert not set(settings) & set(settings_schema.RETIRED_SETTINGS)
    for successor in settings_schema.RETIRED_SETTINGS.values():
        assert successor is None or successor in settings


def test_persistent_settings_agree_across_spec_cli_and_runtime() -> None:
    """AC7: SPEC kinds/values == CLI == root and generated parsers."""
    settings = spec_settings()
    persisted = {
        **settings_schema.INTENT_SETTINGS,
        **settings_schema.DECISION_SETTINGS,
    }
    for key, (kind, allowed) in persisted.items():
        _class, spec_kind, values = settings[key]
        assert spec_kind == kind, key
        if kind in {settings_schema.CHOICE, settings_schema.MULTI}:
            assert values == list(allowed), key
    texts = {path.read_bytes() for path in RUNTIME_PARSERS}
    assert len(texts) == 1, "root and generated parsers must be identical"
    runtime = runpy.run_path(str(RUNTIME_PARSERS[0]))
    assert runtime["INTENT_SETTINGS"] == settings_schema.INTENT_SETTINGS
    assert runtime["DECISION_SETTINGS"] == settings_schema.DECISION_SETTINGS
    assert runtime["SCHEMA_VERSION"] == settings_schema.SCHEMA_VERSION
    assert runtime["COPIER_METADATA_KEYS"] == frozenset(
        settings_schema.COPIER_METADATA_KEYS
    )


def test_copier_questions_match_the_classification() -> None:
    """AC7: every question is classified, none retired, choices agree."""
    settings = spec_settings()
    questions = copier_questions()
    assert set(questions) == set(settings) - COPIER_METADATA
    for key, question in questions.items():
        _class, kind, values = settings[key]
        if "choices" in question:
            assert choice_values(question) == set(values), key
            assert bool(question.get("multiselect")) == (kind == "multi"), key
        elif kind == "bool":
            assert question["type"] == "bool", key
        elif kind == "int":
            assert question["type"] == "int", key
    for key in settings_schema.RENDER_KEYS:
        assert questions[key]["when"] is False


def test_copier_renders_with_strict_undefined() -> None:
    """A template reference to a removed key fails the render loudly."""
    payload = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    assert payload["_envops"]["undefined"] == "jinja2.StrictUndefined"


def jinja_dict_keys(path: Path) -> set[str]:
    """Return the string keys of the dict literal one template renders."""
    return set(
        re.findall(r'^\s*"([a-z_]+)":', path.read_text(encoding="utf-8"), re.M)
    )


def test_answers_template_saves_only_persistent_intent() -> None:
    """AC2: the settings file holds intent plus the schema marker only."""
    assert jinja_dict_keys(ANSWERS_TEMPLATE) == {
        settings_schema.SCHEMA_KEY,
        *settings_schema.INTENT_SETTINGS,
    }
    assert '["_commit", "_src_path"]' in ANSWERS_TEMPLATE.read_text(
        encoding="utf-8"
    )


def test_render_context_template_records_the_closed_context() -> None:
    """AC2: provenance context keys are exactly SPEC-009's context."""
    assert jinja_dict_keys(CONTEXT_TEMPLATE) == set(
        settings_schema.CONTEXT_KEYS
    )


def test_every_released_question_is_classified() -> None:
    """AC1: every key any release tag ever asked has one class."""
    tags = subprocess.run(  # noqa: S603
        ["git", "-C", str(ROOT), "tag", "-l", "v*"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    if not tags:
        pytest.skip("release tags are not available in this clone")
    classes = settings_schema.classification()
    unknown: set[str] = set()
    for tag in tags:
        result = subprocess.run(  # noqa: S603
            ["git", "-C", str(ROOT), "show", f"{tag}:copier.yml"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            continue
        payload = yaml.safe_load(result.stdout) or {}
        unknown.update(
            key
            for key in payload
            if not str(key).startswith("_") and key not in classes
        )
    assert not unknown, sorted(unknown)
