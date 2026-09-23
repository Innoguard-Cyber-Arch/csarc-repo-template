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


def test_root_uses_public_copier_setting_names() -> None:
    """Keep root dogfood values on the same public setting schema."""
    copier = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    config = yaml.safe_load(
        (ROOT / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    question_names = {key for key in copier if not key.startswith("_")}

    assert set(config) <= question_names
    assert "_src_path" not in config
    assert "_commit" not in config
    assert config["project_slug"] == "csarc-repo-template"
    repository_url = config["repository_url"]
    assert isinstance(repository_url, str)
    assert repository_url.endswith("/csarc-repo-template")
    assert config["languages"] == ["python"]
    assert config["package_name"] == "csarc_cli"
    assert config["governance_mode"] == "managed"
    assert config["lifecycle"] == ["issues", "milestones"]
    assert config["actions_fallback"] == "admin"
    assert config["verification_mode"] == "hosted"
    assert config["admin_bypass"] == "always"
    assert config["project_maturity"] == "early"
    assert config["copilot_review"] == "allowed"
    assert config["release_ownership"] == "csarc-owned"
    assert config["release_trigger"] == "main"
    assert config["documentation_mode"] == "template-and-content"
    assert config["primary_language"] == "zh-tw"
    assert config["i18n"] == "en-zh-tw"
    assert config["project_license"] == "proprietary"
    assert config["copyright_holder"] == "Innoguard Cyber Arch"
    assert config["features"] == []
    assert not any(key.startswith("release_level_") for key in config)


def test_root_public_identity_claims_are_consistent() -> None:
    """Keep root configuration and public-facing sources aligned."""
    config = yaml.safe_load(
        (ROOT / ".csarc/config.yml").read_text(encoding="utf-8")
    )
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

    assert config["project_visibility"] == "public"
    assert (
        "public repository's GitHub Issues"
        in config["security_reporting_channel"]
    )
    assert pages == {
        "enabled": True,
        "source": {"branch": "main", "path": "/docs"},
    }

    for text in readmes + site_sources:
        assert "issues/79" in text
        assert "issues/425" in text
        assert "internal audience only" not in text
        assert "內部限閱" not in text
        assert "This organization is private" not in text
        assert "這個組織對外是私密的" not in text

    assert "publicly readable" in robots
    assert "does not restrict access or sharing" in robots


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("branch_strategy: trunk\n", "Invalid branch_strategy"),
        ("governance_mode: partial\n", "Invalid governance_mode"),
        ("actions_fallback: automatic\n", "Invalid actions_fallback"),
        ("verification_mode: automatic\n", "Invalid verification_mode"),
        ("review: anyone\n", "Invalid review"),
        ("copilot_review: required\n", "Invalid copilot_review"),
        ("release_trigger: tag\n", "Invalid release_trigger"),
        ("lifecycle:\n- projects\n", "Invalid lifecycle"),
        ("features:\n- website\n", "Invalid features"),
        ("documentation_mode: website\n", "Invalid documentation_mode"),
        ("primary_language: fr\n", "Invalid primary_language"),
        ("i18n: all\n", "Invalid i18n"),
        ("project_license: unknown\n", "Invalid project_license"),
        ("copyright_holder: ''\n", "Invalid copyright_holder"),
        ("languages:\n- go\n", "Invalid languages"),
        ("languages:\n- python\n- python\n", "Duplicate languages"),
        ("coverage_threshold: 0\n", "Invalid coverage_threshold"),
        ("release_ownership: somebody\n", "Invalid release_ownership"),
        (
            "release_ownership: verification-only\n"
            "release_workflow: .github/workflows/release.yml\n",
            "cannot select a workflow",
        ),
        (
            "release_ownership: csarc-owned\n"
            "release_workflow: .github/workflows/release.yml\n"
            "release_required_inputs: []\n"
            "release_ownership_reason: CSARC owns release.\n"
            "release_settings_owner: product-admin\n"
            "release_immutable_releases: product-defined\n",
            "settings do not match ownership",
        ),
        (
            "policy_repository_settings: maybe\n",
            "Invalid policy_repository_settings",
        ),
        (
            "policy_branch_ruleset: 1\n",
            "Invalid policy_branch_ruleset",
        ),
        (
            "release_levels_enabled: maybe\n",
            "Invalid release_levels_enabled",
        ),
        ("admin_bypass: sometimes\n", "Invalid admin_bypass"),
        ("project_maturity: mature\n", "Invalid project_maturity"),
        (
            "release_level_beta_review: optional\n",
            "Invalid release_level_beta_review",
        ),
        (
            "release_level_stable_verification: smoke\n",
            "Invalid release_level_stable_verification",
        ),
    ],
)
def test_managed_setting_errors_are_diagnostic(
    tmp_path: Path, source: str, message: str
) -> None:
    """Reject invalid managed values while leaving extension keys available."""
    path = tmp_path / ".csarc/config.yml"
    path.parent.mkdir()
    path.write_text(source, encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts/csarc_config.py", scripts)

    result = subprocess.run(  # noqa: S603
        [sys.executable, scripts / "csarc_config.py", "languages"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert message in result.stderr


def test_derived_templates_can_add_namespaced_settings(tmp_path: Path) -> None:
    """Allow downstream policy extensions without creating another config."""
    path = tmp_path / ".csarc/config.yml"
    path.parent.mkdir()
    path.write_text(
        "languages: []\nacme_policy_mode: strict\n", encoding="utf-8"
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts/csarc_config.py", scripts)

    result = subprocess.run(  # noqa: S603
        [sys.executable, scripts / "csarc_config.py", "acme_policy_mode"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "strict"


def test_compact_release_ownership_needs_no_derived_settings(
    tmp_path: Path,
) -> None:
    """Accept the compact release contract before all tooling is upgraded."""
    path = tmp_path / ".csarc/config.yml"
    path.parent.mkdir()
    path.write_text(
        "release_ownership: csarc-owned\nrelease_trigger: main\n",
        encoding="utf-8",
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts/csarc_config.py", scripts)

    result = subprocess.run(  # noqa: S603
        [sys.executable, scripts / "csarc_config.py", "release_ownership"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "csarc-owned"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("governance_mode", "managed"),
        ("actions_fallback", "off"),
        ("verification_mode", "hosted"),
        ("review", "peer"),
        ("copilot_review", "off"),
        ("release_trigger", "main"),
    ],
)
def test_legacy_config_gets_safe_simplified_defaults(
    tmp_path: Path, key: str, expected: str
) -> None:
    """Pre-#900 answers remain readable through deterministic defaults."""
    path = tmp_path / ".csarc/config.yml"
    path.parent.mkdir()
    path.write_text("languages: []\n", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts/csarc_config.py", scripts)

    result = subprocess.run(  # noqa: S603
        [sys.executable, scripts / "csarc_config.py", key],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == expected


def test_mixed_legacy_policy_toggles_require_an_explicit_choice(
    tmp_path: Path,
) -> None:
    """Do not guess while collapsing an old mixed policy configuration."""
    path = tmp_path / ".csarc/config.yml"
    path.parent.mkdir()
    path.write_text(
        "languages: []\n"
        "policy_repository_settings: false\n"
        "policy_actions_permissions: true\n",
        encoding="utf-8",
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts/csarc_config.py", scripts)

    result = subprocess.run(  # noqa: S603
        [sys.executable, scripts / "csarc_config.py", "governance_mode"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "mixed" in result.stderr
