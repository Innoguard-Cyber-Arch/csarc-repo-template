"""Tests for the template repository's own CSARC configuration."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROOT_CONFIG = ROOT / ".csarc/config.yml"


def test_root_uses_public_copier_setting_names() -> None:
    """Keep root dogfood values on the same public schema 2 settings."""
    copier = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    config = yaml.safe_load(ROOT_CONFIG.read_text(encoding="utf-8"))
    question_names = {key for key in copier if not key.startswith("_")}

    assert config["schema_version"] == 2
    assert set(config) - {"schema_version"} <= question_names
    assert "_src_path" not in config
    assert "_commit" not in config
    # Seeds and live facts are read from native sources, never saved
    # (SPEC-009, Issue #1071).
    for seed in (
        "project_name",
        "project_slug",
        "project_description",
        "project_license",
        "copyright_holder",
        "project_visibility",
        "repository_url",
        "project_mode",
    ):
        assert seed not in config
    assert config["languages"] == ["python"]
    # The import package differs from the distribution name, so it is a
    # saved one-time decision.
    assert config["package_name"] == "csarc_cli"
    assert config["governance_mode"] == "managed"
    assert config["lifecycle"] == ["issues", "milestones"]
    assert config["verification_mode"] == "hosted"
    assert config["admin_bypass"] == "always"
    assert config["project_maturity"] == "early"
    assert config["copilot_review"] == "allowed"
    assert config["release_ownership"] == "csarc-owned"
    assert config["release_trigger"] == "manual"
    assert config["documentation_mode"] == "template-and-content"
    assert config["documentation_languages"] == "zh-tw+en"
    assert config["container"] is False
    assert config["scheduled_checks"] == []
    assert config["python_floor"] == "latest"
    assert not any(key.startswith("release_level_") for key in config)


def test_root_public_identity_claims_are_consistent() -> None:
    """Keep root configuration and public-facing sources aligned."""
    config = yaml.safe_load(ROOT_CONFIG.read_text(encoding="utf-8"))
    pages = json.loads(
        (ROOT / "policies/pages.json").read_text(encoding="utf-8")
    )
    readmes = [
        (ROOT / "README.md").read_text(encoding="utf-8"),
        (ROOT / "README.en.md").read_text(encoding="utf-8"),
    ]
    site_sources = [
        (ROOT / "site/content/_index.zh-tw.md").read_text(encoding="utf-8"),
        (ROOT / "site/content/_index.en.md").read_text(encoding="utf-8"),
    ]
    robots = (ROOT / "docs/robots.txt").read_text(encoding="utf-8")

    # Issue #1084 / #1058 decision 20: a public repository reports privately
    # through the maintainer-approved channel outside GitHub. Visibility is
    # a live fact, not a saved setting (SPEC-009).
    assert config["security_reporting_channel"] == "justyn.jt.chen@tw.ey.com"
    assert pages == {"enabled": True, "build_type": "workflow"}

    for text in readmes + site_sources:
        assert "issues/79" in text
        assert "issues/425" in text
        assert "internal audience only" not in text
        assert "內部限閱" not in text
        assert "This organization is private" not in text
        assert "這個組織對外是私密的" not in text

    assert "publicly readable" in robots
    assert "does not restrict access or sharing" in robots


def run_reader(
    tmp_path: Path, source: str, key: str
) -> subprocess.CompletedProcess[str]:
    """Run the root current-only reader against one settings file."""
    path = tmp_path / ".csarc/config.yml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(source, encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "scripts/csarc_config.py", scripts)
    return subprocess.run(  # noqa: S603
        [sys.executable, scripts / "csarc_config.py", key],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )


def with_setting(key: str, value: str) -> str:
    """Return the root settings with one top-level value replaced."""
    lines = ROOT_CONFIG.read_text(encoding="utf-8").splitlines()
    result: list[str] = []
    skipping = False
    for line in lines:
        if skipping and line.startswith("- "):
            continue
        skipping = False
        if line.startswith(f"{key}:"):
            result.append(f"{key}: {value}" if value else f"{key}:")
            skipping = True
            continue
        result.append(line)
    return "\n".join(result) + "\n"


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("governance_mode", "partial", "governance_mode is 'partial'"),
        ("verification_mode", "automatic", "verification_mode is"),
        ("copilot_review", "required", "copilot_review is"),
        ("release_trigger", "tag", "release_trigger is"),
        ("lifecycle", "\n- projects", "lifecycle must be a list"),
        ("documentation_mode", "website", "documentation_mode is"),
        ("documentation_languages", "fr", "documentation_languages is"),
        ("languages", "\n- java", "languages must be a list"),
        ("languages", "\n- python\n- python", "languages repeats a value"),
        ("coverage_threshold", "0", "coverage_threshold must be an integer"),
        ("release_ownership", "somebody", "release_ownership is"),
        ("admin_bypass", "sometimes", "admin_bypass is"),
        ("project_maturity", "mature", "project_maturity is"),
        ("python_floor", "'3.11'", "python_floor is"),
        ("container", "maybe", "container must be true or false"),
        ("code_owner", "nobody", "code_owner must be"),
        ("schema_version", "3", "accepts only schema 2"),
    ],
)
def test_managed_setting_errors_are_diagnostic(
    tmp_path: Path, key: str, value: str, message: str
) -> None:
    """Reject invalid schema 2 values with one stable diagnostic."""
    result = run_reader(tmp_path, with_setting(key, value), "languages")

    assert result.returncode == 1
    assert "CSARC settings error" in result.stderr
    assert message in result.stderr


@pytest.mark.parametrize(
    "extra",
    [
        "actions_fallback: admin\n",
        "primary_language: zh-tw\n",
        "features: []\n",
        "project_name: Example\n",
        "acme_policy_mode: strict\n",
    ],
)
def test_retired_seed_and_unknown_keys_fail_closed(
    tmp_path: Path, extra: str
) -> None:
    """Schema 2 is closed: retired, seed, and unknown keys are refused."""
    result = run_reader(
        tmp_path, ROOT_CONFIG.read_text(encoding="utf-8") + extra, "languages"
    )

    assert result.returncode == 1
    assert "unknown or retired settings" in result.stderr


def test_missing_intent_fails_closed(tmp_path: Path) -> None:
    """A schema 2 file must state every persistent intent."""
    source = "".join(
        line
        for line in ROOT_CONFIG.read_text(encoding="utf-8").splitlines(
            keepends=True
        )
        if not line.startswith("release_ownership:")
    )
    result = run_reader(tmp_path, source, "release_ownership")

    assert result.returncode == 1
    assert "missing persistent settings release_ownership" in result.stderr


def test_seed_keys_are_not_readable_settings(tmp_path: Path) -> None:
    """A seed is read from its native source, never from the settings."""
    result = run_reader(
        tmp_path, ROOT_CONFIG.read_text(encoding="utf-8"), "project_name"
    )

    assert result.returncode == 1
    assert "not a schema 2 setting" in result.stderr


@pytest.mark.parametrize(
    "source",
    [
        "languages: []\n",
        "languages: []\npolicy_repository_settings: false\n",
        "release_ownership: csarc-owned\nrelease_trigger: main\n",
    ],
)
def test_legacy_settings_never_get_runtime_defaults(
    tmp_path: Path, source: str
) -> None:
    """Pre-schema-2 answers fail closed and point to the pinned CLI."""
    result = run_reader(tmp_path, source, "governance_mode")

    assert result.returncode == 1
    assert "legacy settings schema" in result.stderr
    assert "csarc update" in result.stderr


def test_list_and_bool_settings_print_for_shell_callers(tmp_path: Path) -> None:
    """Shell adapters keep reading lists and booleans in one stable form."""
    source = ROOT_CONFIG.read_text(encoding="utf-8")

    assert run_reader(tmp_path, source, "lifecycle").stdout.strip() == (
        "issues,milestones"
    )
    assert run_reader(tmp_path, source, "container").stdout.strip() == "false"
    assert (
        run_reader(tmp_path, source, "release_ownership").stdout.strip()
        == "csarc-owned"
    )
