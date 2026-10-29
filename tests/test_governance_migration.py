"""Legacy governance migration mapping and report rows (Issue #1064)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
import yaml

import csarc_cli.cli as cli
from csarc_cli import governance_migration, lifecycle_report, settings_schema
from csarc_cli.cli import CliError

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = cli.RepositoryContext(
    "owner/product", "owner", "User", "private", "github", True
)
CURRENT_QUESTIONS = frozenset(
    key
    for key in yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    if not key.startswith("_")
)
COMMON = {
    "_commit": "v0.0.0",
    "_src_path": "https://github.com/example/template.git",
    "code_owner": "@owner",
    "coverage_mode": "off",
    "coverage_threshold": 80,
    "enable_codeql": False,
    "enable_governance_drift_check": True,
    "enable_precommit": True,
    "enable_template_update_notifications": True,
    "language": "python",
    "languages": "",
    "package_name": "product",
    "project_description": "Product service",
    "project_mode": "new",
    "project_name": "Product",
    "project_run_command": "",
    "project_slug": "product",
    "project_verification_hook": "",
    "project_visibility": "private",
    "python_min_version": "3.14",
    "python_support_mode": "latest",
    "release_ownership": "csarc-owned",
    "repository_url": "https://github.com/owner/product",
    "security_reporting_channel": "Use the private security contact.",
}
# Saved answers shaped like each release's question set (copier.yml at the
# tag), with that release's defaults.
V0_16_0 = {
    **COMMON,
    "branch_strategy": "delivery",
    "copilot_review_max_level": "unlimited",
    "enable_docker": False,
    "policy_actions_permissions": True,
    "policy_branch_ruleset": True,
    "policy_labels": True,
    "policy_repository_settings": True,
    "pr_review_mode": "human",
    "readme_primary_language": "zh-tw",
    "reviewers": "@reviewer",
}
V0_22_0 = {
    **COMMON,
    "actions_fallback": "off",
    "admin_bypass": "off",
    "copilot_review": "allowed",
    "features": [],
    "governance_mode": "managed",
    "lifecycle": ["issues", "milestones"],
    "project_maturity": "early",
    "readme_primary_language": "zh-tw",
    "release_trigger": "main",
    "verification_mode": "hosted",
}
V0_30_3 = {
    **{
        key: value
        for key, value in V0_22_0.items()
        if key != "readme_primary_language"
    },
    "admin_bypass": "beta-only",
    "copyright_holder": "Product",
    "documentation_mode": "content-only",
    "primary_language": "zh-tw",
    "project_license": "proprietary",
    "verification_mode": "local",
    "work_item_mapping_review": "confirmed",
}
MISSING_ADMIN_BYPASS = {
    key: value for key, value in V0_30_3.items() if key != "admin_bypass"
}


MODE_KEYS = settings_schema.MODE_KEYS


def migrate(
    saved: Mapping[str, object], explicit: Mapping[str, str] | None = None
) -> tuple[dict[str, object], dict[str, object], dict[str, dict[str, object]]]:
    """Resolve one update and return its answers, data, and setting rows."""
    data = dict(explicit or {})
    answers, update_data = cli.update_plan_answers(
        dict(saved), data, REPOSITORY
    )
    rows = cli.report_setting_rows(answers, saved, tuple(data))
    assert governance_migration.governance_row_violations(rows) == []
    return answers, update_data, {str(row["key"]): row for row in rows}


def persisted(answers: Mapping[str, object]) -> dict[str, object]:
    """Return what Copier writes: answers to current questions only."""
    return {
        key: value
        for key, value in answers.items()
        if key in CURRENT_QUESTIONS or key.startswith("_")
    }


def assert_rows_cover_changes(
    saved: Mapping[str, object],
    answers: Mapping[str, object],
    rows: Mapping[str, Mapping[str, object]],
) -> None:
    """AC2: a governance or retired value never changes without a row."""
    after = persisted(answers)
    for key in governance_migration.GOVERNANCE_KEYS | set(
        governance_migration.RETIRED_SETTINGS
    ):
        if saved.get(key) != after.get(key):
            assert key in rows, key
            assert rows[key]["class"] != "unchanged", key
    for row in rows.values():
        assert row["class"] in lifecycle_report.SETTING_CLASSES


def test_report_vocabulary_has_no_parallel_terms() -> None:
    """AC3: no `mapped` or `decision-required` setting class exists."""
    assert "mapped" not in lifecycle_report.SETTING_CLASSES
    assert "decision-required" not in lifecycle_report.SETTING_CLASSES
    assert governance_migration.GOVERNANCE_CLASSES.issubset(
        lifecycle_report.SETTING_CLASSES
    )
    assert set(governance_migration.RETIRED_SETTINGS).isdisjoint(
        CURRENT_QUESTIONS
    )
    for successor in governance_migration.RETIRED_SETTINGS.values():
        assert successor is None or successor in CURRENT_QUESTIONS
    assert governance_migration.GOVERNANCE_KEYS <= CURRENT_QUESTIONS


def test_v0_16_0_maps_governance_and_retires_legacy_keys() -> None:
    """AC1/AC2/AC3/AC6: the v0.16.0 answer set migrates with full rows."""
    answers, update_data, rows = migrate(V0_16_0)

    assert answers["admin_bypass"] == "always"
    assert update_data["admin_bypass"] == "always"
    admin = rows["admin_bypass"]
    assert (admin["class"], admin["before"], admin["after"]) == (
        "widened",
        None,
        "always",
    )
    assert admin["source"] == "derived"
    note = str(admin["note"])
    assert "equivalent to `beta-only`" in note
    assert "beta and stable work" in note
    assert "csarc update --data admin_bypass=beta-only" in note
    expected = {
        "copilot_review": "off",
        "governance_mode": "managed",
        "lifecycle": ["issues", "milestones"],
        "project_maturity": "early",
        "release_trigger": "main",
        "verification_mode_private": "hosted",
        "verification_mode_public": "hosted",
    }
    for key, value in expected.items():
        assert answers[key] == value, key
        assert rows[key]["class"] == "exact", key
    for key in (
        "branch_strategy",
        "copilot_review_max_level",
        "enable_docker",
        "policy_actions_permissions",
        "policy_branch_ruleset",
        "policy_labels",
        "policy_repository_settings",
        "pr_review_mode",
        "readme_primary_language",
        "reviewers",
    ):
        assert rows[key]["class"] == "retired", key
        assert rows[key]["after"] is None, key
        assert rows[key]["before"] == V0_16_0[key], key
        assert rows[key]["note"], key
    # SPEC-009 successors of the retired keys (Issue #1071).
    assert rows["container"]["class"] == "exact"
    assert rows["documentation_languages"]["class"] == "exact"
    assert answers["documentation_languages"] == "zh-tw+en"
    assert_rows_cover_changes(V0_16_0, answers, rows)


@pytest.mark.parametrize(
    "saved", [V0_22_0, V0_30_3], ids=["v0.22.0", "v0.30.3"]
)
def test_saved_governance_values_are_unchanged(
    saved: dict[str, object],
) -> None:
    """AC1/AC2/AC6: saved values (including `off`) are never rewritten."""
    answers, update_data, rows = migrate(saved)

    for key in governance_migration.GOVERNANCE_KEYS - set(MODE_KEYS):
        assert answers[key] == saved[key], key
        assert key not in update_data, key
        assert rows[key]["class"] == "unchanged", key
        assert rows[key]["source"] == "saved", key
    # SPEC-011: the saved legacy mode moves unchanged to both settings.
    for key in MODE_KEYS:
        assert answers[key] == saved["verification_mode"], key
        assert rows[key]["class"] == "exact", key
    assert_rows_cover_changes(saved, answers, rows)


def test_missing_admin_bypass_is_widened_to_always() -> None:
    """AC1/AC6: a current-schema config without the key is reported."""
    answers, _update_data, rows = migrate(MISSING_ADMIN_BYPASS)

    assert answers["admin_bypass"] == "always"
    assert rows["admin_bypass"]["class"] == "widened"
    for key in governance_migration.GOVERNANCE_KEYS - {
        "admin_bypass",
        *MODE_KEYS,
    }:
        assert rows[key]["class"] == "unchanged", key
    for key in MODE_KEYS:
        assert rows[key]["class"] == "exact", key
    assert_rows_cover_changes(MISSING_ADMIN_BYPASS, answers, rows)


@pytest.mark.parametrize(
    ("legacy", "scope"),
    [
        ({"review": "peer"}, "off"),
        ({"review": "solo"}, "always"),
        ({"release_level_alpha_review": "peer"}, "off"),
        ({"release_level_beta_review": "self"}, "beta-only"),
        ({"release_level_formal_review": "self"}, "always"),
    ],
)
def test_legacy_review_scope_is_explained_but_always_widened(
    legacy: dict[str, object], scope: str
) -> None:
    """AC1: the note names the earlier scope and how to restore it."""
    saved = {**V0_16_0, **legacy}
    answers, _update_data, rows = migrate(saved)

    assert answers["admin_bypass"] == "always"
    assert rows["admin_bypass"]["class"] == "widened"
    assert f"csarc update --data admin_bypass={scope}" in str(
        rows["admin_bypass"]["note"]
    )
    for key in legacy:
        assert rows[key]["class"] == "retired"


@pytest.mark.parametrize(
    ("value", "setting_class"),
    [("beta-only", "exact"), ("off", "narrowed"), ("always", "decision")],
)
def test_explicit_admin_bypass_is_kept(value: str, setting_class: str) -> None:
    """AC1: an explicit value is preserved and never reported widened."""
    answers, update_data, rows = migrate(V0_16_0, {"admin_bypass": value})

    assert answers["admin_bypass"] == value
    assert update_data["admin_bypass"] == value
    assert rows["admin_bypass"]["class"] == setting_class
    assert rows["admin_bypass"]["source"] == "explicit"


def test_explicit_saved_admin_bypass_change_is_a_decision() -> None:
    """AC1/AC2: changing a saved value is an explicit decision row."""
    answers, _update_data, rows = migrate(V0_22_0, {"admin_bypass": "always"})

    assert answers["admin_bypass"] == "always"
    assert rows["admin_bypass"]["class"] == "decision"
    assert rows["admin_bypass"]["source"] == "explicit"


@pytest.mark.parametrize(
    ("legacy", "value", "setting_class"),
    [
        ({"pr_review_mode": "human"}, "off", "exact"),
        ({"pr_review_mode": "copilot"}, "allowed", "exact"),
        (
            {"pr_review_mode": "copilot", "copilot_review_max_level": "beta"},
            "off",
            "narrowed",
        ),
    ],
)
def test_copilot_review_is_exact_or_narrowed(
    legacy: dict[str, object], value: str, setting_class: str
) -> None:
    """AC2: a level-capped Copilot review never widens to every level."""
    answers, _update_data, rows = migrate({**V0_16_0, **legacy})

    assert answers["copilot_review"] == value
    assert rows["copilot_review"]["class"] == setting_class
    if setting_class == "narrowed":
        assert "copilot_review=allowed" in str(rows["copilot_review"]["note"])


def test_mixed_policy_toggles_require_a_decision() -> None:
    """AC2: no equivalent governance mode means a decision before writing."""
    saved = {**V0_16_0, "policy_labels": False}
    with pytest.raises(CliError, match="mixed"):
        migrate(saved)
    answers, _update_data, rows = migrate(saved, {"governance_mode": "observe"})
    assert answers["governance_mode"] == "observe"
    assert rows["governance_mode"]["class"] == "decision"
    assert rows["governance_mode"]["source"] == "explicit"


@pytest.mark.parametrize(
    "saved",
    [V0_16_0, V0_22_0, V0_30_3, MISSING_ADMIN_BYPASS],
    ids=["v0.16.0", "v0.22.0", "v0.30.3", "missing-admin-bypass"],
)
def test_repeated_migration_is_idempotent(saved: dict[str, object]) -> None:
    """AC6: a second update of the migrated answers changes nothing."""
    first, _update_data, _rows = migrate(saved)
    stored = persisted(first)
    second, update_data, rows = migrate(stored)

    for key in governance_migration.GOVERNANCE_KEYS:
        assert second[key] == first[key], key
        assert key not in update_data, key
        assert rows[key]["class"] == "unchanged", key
    assert not set(governance_migration.RETIRED_SETTINGS) & set(rows)
    assert persisted(second) == stored | {
        key: second[key] for key in update_data if key in CURRENT_QUESTIONS
    }


def test_update_report_validates_the_migration_rows(tmp_path: Path) -> None:
    """AC1/AC3: the full SPEC-008 report carries and renders the rows."""
    answers, _update_data, _rows = migrate(V0_16_0)
    answers = cli.resolve_release_answers(tmp_path, answers)
    plan = cli.ResolvedPlan(
        mode="update",
        target=tmp_path / "product",
        revision=cli.Revision("v1.1.0", "d" * 40, "https://example.invalid"),
        repository=REPOSITORY,
        answers=answers,
        capabilities={},
        files=cli.Plan((), (), (), ("kept.txt",), (), (), ()),
        update={
            "project_verification_hook": {
                "configured": False,
                "path": None,
                "reason": "Configuration validated.",
                "result": "not-run",
            },
            "update_available": True,
        },
    )
    report = cli.lifecycle_report_model(
        plan,
        operation="update",
        plan_name=cli.UPDATE_PLAN_BASENAME,
        plan_sha256="a" * 64,
        generated_at="2026-10-14T00:00:00+00:00",
        plan_path=tmp_path / "reports" / cli.UPDATE_PLAN_BASENAME,
        before=V0_16_0,
        previous=cli.Revision("v0.16.0", "b" * 40, "https://example.invalid"),
        target_head="c" * 40,
        target_changes=(),
    )
    settings = cast(list[dict[str, object]], report["settings"])
    rows = {row["key"]: row for row in settings}
    assert rows["admin_bypass"]["class"] == "widened"
    assert rows["pr_review_mode"]["class"] == "retired"
    markdown = lifecycle_report.render_markdown(report)
    assert "Widened settings: `admin_bypass`" in markdown
    assert "admin_bypass=beta-only" in markdown


@pytest.mark.parametrize(
    "row",
    [
        {
            "key": "verification_mode_private",
            "class": "widened",
            "before": "hosted",
            "after": "local",
            "source": "derived",
        },
        {
            "key": "governance_mode",
            "class": "new",
            "before": None,
            "after": "managed",
            "source": "derived",
        },
        {
            "key": "admin_bypass",
            "class": "widened",
            "before": "off",
            "after": "always",
            "source": "derived",
        },
        {
            "key": "admin_bypass",
            "class": "widened",
            "before": None,
            "after": "always",
            "source": "explicit",
        },
    ],
)
def test_unapproved_governance_rows_are_violations(
    row: dict[str, object],
) -> None:
    """AC2: only the approved admin_bypass migration may be widened."""
    assert governance_migration.governance_row_violations([row]) == [
        f"{row['key']}={row['class']}"
    ]


def test_update_report_refuses_an_unapproved_governance_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: a widened non-admin governance row stops the plan."""
    monkeypatch.setattr(
        governance_migration,
        "setting_classes",
        lambda before, after, explicit: {
            "verification_mode_private": ("widened", None)
        },
    )
    with pytest.raises(CliError, match="approved migration mapping"):
        cli.lifecycle_report_model(
            cli.ResolvedPlan(
                mode="update",
                target=tmp_path,
                revision=cli.Revision("v1", "d" * 40, "https://x.invalid"),
                repository=REPOSITORY,
                answers={**V0_30_3, "verification_mode_private": "hosted"},
                capabilities={},
                files=cli.Plan((), (), (), (), (), (), ()),
                update={"update_available": True},
            ),
            operation="update",
            plan_name=cli.UPDATE_PLAN_BASENAME,
            plan_sha256="a" * 64,
            generated_at="2026-10-14T00:00:00+00:00",
            before=V0_30_3,
        )
