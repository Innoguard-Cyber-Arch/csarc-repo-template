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


def test_supported_language_modules_have_executable_beta_evidence() -> None:
    """Require repeatable evidence instead of disposable pilot repos."""
    catalog = yaml.safe_load(
        (ROOT / "profiles/catalog.yaml").read_text(encoding="utf-8")
    )
    assert catalog["version_policy"]["update_method"] == (
        "manual_reviewed_pull_request"
    )
    assert (
        catalog["version_policy"]["merge_after_full_verification"] == "manual"
    )
    assert catalog["template_version_policy"]["release_automation"] == (
        "blocked_pending_issue_369"
    )
    requirements = catalog["promotion_requirements"]

    assert catalog["compositions"]["language_modules"]["stage"] == "beta"
    assert "real_consuming_repository" in requirements["shared_lifecycle"]
    assert "real_consuming_repository" not in requirements["language_module"]
    for language in ("python", "rust", "typescript"):
        assert catalog["profiles"][language]["stage"] == "beta"
        evidence = catalog["promotion_evidence"][language]
        assert evidence["status"] == "satisfied"
        assert evidence["method"] == "executable_template_lifecycle"
        assert evidence["evidence"]


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
    python_config = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert '"ty==0.0.76"' in python_config
    assert "[tool.ty.src]" in python_config
    assert "mypy" not in python_config
    verifier = (project / "scripts/verify").read_text(encoding="utf-8")
    assert "uv run ty check" in verifier
    assert "mypy" not in verifier
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


@pytest.mark.parametrize(
    ("language", "required_tools", "verify_mode", "manifest", "lockfile"),
    [
        ("python", ("uv",), "python", "pyproject.toml", "uv.lock"),
        (
            "typescript",
            ("node", "pnpm"),
            "typescript",
            "package.json",
            "pnpm-lock.yaml",
        ),
        (
            "rust",
            ("cargo", "rustc"),
            "rust",
            "Cargo.toml",
            "Cargo.lock",
        ),
    ],
)
@pytest.mark.large
def test_generated_language_module_runs_its_own_verifier(
    tmp_path: Path,
    language: str,
    required_tools: tuple[str, ...],
    verify_mode: str,
    manifest: str,
    lockfile: str,
) -> None:
    """Render and execute each standalone language module."""
    missing = [tool for tool in required_tools if shutil.which(tool) is None]
    if missing:
        pytest.skip(
            f"Required language tools are unavailable: {', '.join(missing)}"
        )

    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / f"{language}-project"
    run_copy(
        str(source),
        project,
        data={
            "languages": [language],
            "project_name": f"{language.title()} Fixture",
            "project_slug": f"{language}-fixture",
            "project_description": f"A generated {language} fixture.",
            "repository_url": f"https://github.com/example/{language}-fixture",
            "security_reporting_channel": "Use the private security contact.",
        },
        defaults=True,
        unsafe=True,
    )

    profile = yaml.safe_load(
        (project / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    assert profile["languages"] == [language]
    assert not (project / ".copier-answers.yml").exists()
    assert not (project / ".csarc/profile.json").exists()
    assert (project / manifest).is_file()
    assert (project / lockfile).is_file()
    subprocess.run(  # noqa: S603
        [project / "scripts/verify", verify_mode], cwd=project, check=True
    )
