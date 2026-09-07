"""Tests for the template repository's own CSARC configuration."""

from __future__ import annotations

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
    assert config["release_ownership"] == "csarc-owned"
    assert config["release_settings_owner"] == "csarc-admin"
    assert config["release_immutable_releases"] == "required"


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("branch_strategy: trunk\n", "Invalid branch_strategy"),
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


@pytest.mark.parametrize(
    "toggle_key",
    [
        "policy_repository_settings",
        "policy_actions_permissions",
        "policy_labels",
        "policy_branch_ruleset",
    ],
)
def test_policy_toggle_absent_key_has_no_forced_value(
    tmp_path: Path, toggle_key: str
) -> None:
    """A policy toggle absent from config.yml is left unset, not defaulted.

    scripts/apply-repository-settings.sh (not this reader) supplies the
    "on" default for a missing key -- see its policy_config_value helper --
    so an older answers file predating Issue #532 keeps every policy area
    on without csarc_config.py needing to know that default.
    """
    path = tmp_path / ".csarc/config.yml"
    path.parent.mkdir()
    path.write_text("languages: []\n", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts/csarc_config.py", scripts)

    result = subprocess.run(  # noqa: S603
        [sys.executable, scripts / "csarc_config.py", toggle_key],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert toggle_key in result.stderr


@pytest.mark.parametrize(
    ("toggle_key", "toggle_value"),
    [
        ("policy_repository_settings", "false"),
        ("policy_actions_permissions", "true"),
        ("policy_labels", "false"),
        ("policy_branch_ruleset", "true"),
    ],
)
def test_policy_toggle_explicit_value_round_trips(
    tmp_path: Path, toggle_key: str, toggle_value: str
) -> None:
    """An explicit true/false policy toggle is validated and echoed back."""
    path = tmp_path / ".csarc/config.yml"
    path.parent.mkdir()
    path.write_text(
        f"languages: []\n{toggle_key}: {toggle_value}\n", encoding="utf-8"
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts/csarc_config.py", scripts)

    result = subprocess.run(  # noqa: S603
        [sys.executable, scripts / "csarc_config.py", toggle_key],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == toggle_value
