"""Tests for composable language-profile generation."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from copier import run_copy

from csarc_cli import cli

ROOT = Path(__file__).resolve().parents[1]


def test_languages_are_independent_modules() -> None:
    """Offer language modules instead of enumerating combinations."""
    config = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    question = config["languages"]

    assert question["multiselect"] is True
    assert set(question["choices"].values()) == {"python", "typescript", "rust"}
    assert config["language"]["when"] is False


def test_detect_languages_composes_selected_modules(
    tmp_path: Path,
) -> None:
    """Detect modules without defining combination-specific branches."""
    (tmp_path / "Cargo.toml").touch()
    assert cli.detect_languages(tmp_path) == ["rust"]
    assert cli.detect_language(tmp_path) == "rust"

    (tmp_path / "pyproject.toml").touch()
    assert cli.detect_languages(tmp_path) == ["python", "rust"]
    assert cli.detect_language(tmp_path) == "python-rust"


def test_copier_uses_one_yaml_config_for_language_modules(
    tmp_path: Path,
) -> None:
    """Keep Copier tracking and repository settings in the same file."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    cli.run(["git", "init", "-b", "main"], cwd=source)
    cli.run(
        ["git", "config", "user.name", "Language Test"],
        cwd=source,
    )
    cli.run(
        ["git", "config", "user.email", "language@example.invalid"],
        cwd=source,
    )
    cli.run(["git", "add", "."], cwd=source)
    cli.run(
        ["git", "commit", "-m", "test: language template"],
        cwd=source,
        capture=True,
    )
    revision = cli.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        capture=True,
    ).stdout.strip()
    project = tmp_path / "project"
    data = cli.base_data(
        project,
        "init",
        {
            "languages": "python,rust",
            "project_description": "Exercises one CSARC configuration.",
        },
    )

    cli.copier_copy(
        str(source),
        cli.Revision(revision, revision, str(source)),
        project,
        data,
        skip_tasks=True,
    )

    config_path = project / ".csarc/config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["_commit"] == revision
    assert config["languages"] == ["python", "rust"]
    assert not (project / ".copier-answers.yml").exists()
    assert not (project / ".csarc/profile.json").exists()
    assert (project / "pyproject.toml").is_file()
    assert (project / "Cargo.toml").is_file()
    assert not (project / "package.json").exists()
    assert not (project / "version.txt").exists()
    configured = cli.run(
        [sys.executable, "scripts/csarc_config.py", "languages"],
        cwd=project,
        capture=True,
    ).stdout.strip()
    assert configured == "python,rust"


def test_update_language_selection_stays_a_list() -> None:
    """Do not flatten Copier multiselect answers during an update."""
    repository = cli.RepositoryContext(
        "owner/repository",
        "owner",
        "Organization",
        "private",
        "github",
        True,
    )

    answers, update_data = cli.update_plan_answers(
        {"languages": ["python"], "project_visibility": "private"},
        {"languages": '["typescript", "rust"]'},
        repository,
    )

    assert answers["languages"] == ["typescript", "rust"]
    assert update_data["languages"] == ["typescript", "rust"]


def test_config_supports_ci_only_and_extension_settings(tmp_path: Path) -> None:
    """Keep an empty language list and derived-template settings readable."""
    config_dir = tmp_path / ".csarc"
    scripts_dir = tmp_path / "scripts"
    config_dir.mkdir()
    scripts_dir.mkdir()
    shutil.copy2(ROOT / "scripts/csarc_config.py", scripts_dir)
    detector = scripts_dir / "detect-language-profile"
    shutil.copy2(ROOT / "template/scripts/detect-language-profile", detector)
    detector.chmod(detector.stat().st_mode | 0o100)
    (config_dir / "config.yml").write_text(
        "languages: []\nacme_policy_mode: strict\n",
        encoding="utf-8",
    )

    detected = subprocess.run(  # noqa: S603
        [detector], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    extension = subprocess.run(  # noqa: S603
        [sys.executable, scripts_dir / "csarc_config.py", "acme_policy_mode"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert detected == "language modules: ci"
    assert extension == "strict"


@pytest.mark.large
def test_generated_rust_profile_runs_its_own_verifier(tmp_path: Path) -> None:
    """Render and execute the standalone Rust module."""
    if shutil.which("cargo") is None:
        pytest.skip("Cargo is required for the Rust profile integration test")

    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "rust-project"
    run_copy(
        str(source),
        project,
        data={
            "languages": ["rust"],
            "project_name": "Rust Fixture",
            "project_slug": "rust-fixture",
            "project_description": "A generated Rust fixture.",
            "repository_url": "https://github.com/example/rust-fixture",
            "security_reporting_channel": "Use the private security contact.",
        },
        defaults=True,
        unsafe=True,
    )

    profile = yaml.safe_load(
        (project / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    assert profile["languages"] == ["rust"]
    assert not (project / ".copier-answers.yml").exists()
    assert not (project / ".csarc/profile.json").exists()
    assert (project / "Cargo.lock").is_file()
    assert not (project / "pyproject.toml").exists()
    assert not (project / "package.json").exists()
    subprocess.run(  # noqa: S603
        [project / "scripts/verify", "rust"], cwd=project, check=True
    )
