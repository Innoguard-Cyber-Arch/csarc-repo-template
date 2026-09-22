"""Tests for composable language-profile generation."""

from __future__ import annotations

import json
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
    assert catalog["template_version_policy"]["materialization"] == (
        "release_please_reviewed_pull_request"
    )
    assert catalog["template_version_policy"]["release_automation"] == (
        "verified_immutable_github_release"
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

    (tmp_path / "pyproject.toml").touch()
    assert cli.detect_languages(tmp_path) == ["python", "rust"]

    (tmp_path / "package.json").touch()
    assert cli.detect_languages(tmp_path) == ["python", "rust", "typescript"]


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
        {
            "languages": ["python"],
            "project_mode": "new",
            "project_visibility": "private",
        },
        {"languages": '["typescript", "rust"]'},
        repository,
    )

    assert answers["languages"] == ["typescript", "rust"]
    assert update_data["languages"] == ["typescript", "rust"]


def test_config_supports_ci_only_and_extension_settings(tmp_path: Path) -> None:
    """Keep an empty language list and derived-template settings readable."""
    config_dir = tmp_path / ".csarc"
    scripts_dir = tmp_path / ".csarc/scripts"
    config_dir.mkdir()
    scripts_dir.mkdir()
    shutil.copy2(ROOT / "scripts/csarc_config.py", scripts_dir)
    detector = scripts_dir / "detect-language-profile"
    shutil.copy2(
        ROOT / "template/.csarc/scripts/detect-language-profile", detector
    )
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


def test_generated_detector_uses_copier_language_order(tmp_path: Path) -> None:
    """Compare generated language profiles in the Copier choice order."""
    config_dir = tmp_path / ".csarc"
    scripts_dir = tmp_path / ".csarc/scripts"
    config_dir.mkdir()
    scripts_dir.mkdir()
    shutil.copy2(ROOT / "scripts/csarc_config.py", scripts_dir)
    detector = scripts_dir / "detect-language-profile"
    shutil.copy2(
        ROOT / "template/.csarc/scripts/detect-language-profile", detector
    )
    detector.chmod(detector.stat().st_mode | 0o100)
    (config_dir / "config.yml").write_text(
        "languages:\n- rust\n- typescript\n", encoding="utf-8"
    )
    (tmp_path / "Cargo.toml").touch()
    (tmp_path / "package.json").touch()

    detected = subprocess.run(  # noqa: S603
        [detector], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    assert detected == "language modules: rust,typescript"


@pytest.mark.large
def test_representative_generated_project_runs_full_verifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run one mixed generated project through the complete verifier once."""
    required_tools = ("uv", "node", "pnpm", "cargo", "rustc")
    missing = [tool for tool in required_tools if shutil.which(tool) is None]
    if missing:
        pytest.skip(
            f"Required language tools are unavailable: {', '.join(missing)}"
        )

    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    cli.run(["git", "init", "-b", "main"], cwd=source)
    cli.run(["git", "config", "user.name", "Language Test"], cwd=source)
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
        ["git", "rev-parse", "HEAD"], cwd=source, capture=True
    ).stdout.strip()
    project = tmp_path / "representative-project"
    arguments = [
        "init",
        str(project),
        "--source",
        str(source),
        "--to",
        revision,
        "--allow-unreleased",
        "--data",
        "languages=python,typescript,rust",
        "--data",
        "project_name=Representative Fixture",
        "--data",
        "project_slug=representative-fixture",
        "--data",
        "project_description=Exercises the representative toolchains.",
        "--data",
        "repository_url=https://github.com/example/representative-fixture",
        "--data",
        "security_reporting_channel=Use the private security contact.",
    ]
    verified_projects: list[Path] = []
    original_verify_project = cli.verify_project

    def record_verification(target: Path) -> dict[str, object]:
        verified_projects.append(target)
        return original_verify_project(target)

    monkeypatch.setattr(cli, "verify_project", record_verification)
    assert cli.main([*arguments, "--dry-run"]) == 0
    assert not project.exists()
    assert cli.main([*arguments, "--yes", "--non-interactive"]) == 0
    assert verified_projects == [project]
    assert (
        json.loads((project / cli.PROVENANCE_FILE).read_text(encoding="utf-8"))[
            "commit_sha"
        ]
        == revision
    )
    config = yaml.safe_load(
        (project / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    assert config["languages"] == ["python", "rust", "typescript"]
    assert not (project / ".copier-answers.yml").exists()
    assert not (project / ".csarc/profile.json").exists()
    assert not (project / ".csarc/gitleaks.toml").exists()
    assert not (project / ".csarc/pre-commit-config.yaml").exists()
    assert not (project / ".csarc/zizmor.yml").exists()
    assert not (project / ".csarc/scripts/pre-commit").exists()
    secret_adapter = (project / ".csarc/scripts/scan-secrets").read_text(
        encoding="utf-8"
    )
    assert "mktemp" in secret_adapter
    assert "trap 'rm -f" in secret_adapter
    assert all(
        (project / manifest).is_file()
        for manifest in ("pyproject.toml", "package.json", "Cargo.toml")
    )
    assert {path.name for path in project.iterdir()} == {
        ".coverage",
        ".claude",
        ".csarc",
        ".github",
        ".gitignore",
        ".node-version",
        ".pytest_cache",
        ".python-version",
        ".ruff_cache",
        ".venv",
        "AGENTS.md",
        "CHANGELOG.md",
        "Cargo.lock",
        "Cargo.toml",
        "README.en.md",
        "README.md",
        "SECURITY.md",
        "biome.json",
        "coverage",
        "dist",
        "docs",
        "node_modules",
        "package.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "pyproject.toml",
        "rust-toolchain.toml",
        "src",
        "target",
        "tests",
        "tsconfig.build.json",
        "tsconfig.json",
        "typescript",
        "uv.lock",
        "vitest.config.ts",
    }
    cli.run(["git", "init", "-b", "main"], cwd=project)
    cli.run(["git", "config", "user.name", "Verification Test"], cwd=project)
    cli.run(
        ["git", "config", "user.email", "verification@example.invalid"],
        cwd=project,
    )
    cli.run(["git", "add", "."], cwd=project)
    cli.run(
        ["git", "commit", "-m", "test: generated project"],
        cwd=project,
        capture=True,
    )

    subprocess.run(  # noqa: S603
        [project / ".csarc/scripts/scan-secrets"], cwd=project, check=True
    )


@pytest.mark.large
def test_precommit_adapter_materializes_ephemeral_config(
    tmp_path: Path,
) -> None:
    """Keep tool syntax behind the opt-in stable adapter."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "precommit-fixture"
    run_copy(
        str(source),
        project,
        data={
            "languages": ["python", "typescript"],
            "project_name": "Precommit Fixture",
            "project_slug": "precommit-fixture",
            "project_description": "Exercises the pre-commit adapter.",
            "repository_url": "https://github.com/example/precommit-fixture",
            "security_reporting_channel": "Use the private security contact.",
            "enable_precommit": True,
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    adapter = project / ".csarc/scripts/pre-commit"
    source_text = adapter.read_text(encoding="utf-8")
    assert adapter.is_file()
    assert adapter.stat().st_mode & 0o111
    assert "mktemp" in source_text
    assert "trap 'rm -f" in source_text
    assert "uv run ruff check" in source_text
    assert "pnpm exec tsc --noEmit" in source_text
    assert not (project / ".pre-commit-config.yaml").exists()
    assert not (project / ".csarc/pre-commit-config.yaml").exists()


@pytest.mark.large
def test_enable_codeql_generates_a_working_workflow(tmp_path: Path) -> None:
    """Prove enable_codeql=true actually renders a usable CodeQL workflow.

    Regression for #494: the generator source used to be missing entirely,
    so `enable_codeql: true` silently produced no workflow at all despite
    copier.yml and the README both describing it as active.

    Copies copier.yml/template/ into a plain (non-git) source directory
    first, like test_generated_language_module_runs_its_own_verifier does:
    running run_copy() straight against ROOT would let Copier default to
    ROOT's latest release git tag instead of the working tree, silently
    testing stale, already-released template content.
    """
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "codeql-fixture"
    run_copy(
        str(source),
        project,
        data={
            "languages": ["python", "typescript"],
            "project_name": "CodeQL Fixture",
            "project_slug": "codeql-fixture",
            "project_description": "Exercises the CodeQL workflow generator.",
            "repository_url": "https://github.com/example/codeql-fixture",
            "security_reporting_channel": "Use the private security contact.",
            "project_visibility": "public",
            "enable_codeql": True,
        },
        defaults=True,
        unsafe=True,
        # Only the rendered files are under test here; skip the pnpm/uv
        # post-generation tasks so this stays runnable without a Node
        # toolchain (e.g. on the docs/fast CI tier).
        skip_tasks=True,
    )

    workflow_path = project / ".github/workflows/codeql.yml"
    assert workflow_path.is_file()
    raw = workflow_path.read_text(encoding="utf-8")
    # Guards the exact escaping bug found in the archived generator, where
    # `${{ "${{ matrix.language }}" }}` rendered as a broken `$${{ ... }}`.
    assert "$$" not in raw
    # No unrendered Jinja block/statement syntax should survive rendering.
    assert "{%" not in raw

    workflow = yaml.safe_load(raw)
    # PyYAML parses the bare `on:` key as boolean True (YAML 1.1).
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["pull_request"]["types"] == [
        "opened",
        "reopened",
        "synchronize",
    ]
    assert "workflow_dispatch" in triggers
    assert "push" not in triggers

    assert workflow["permissions"] == {}

    job = workflow["jobs"]["analyze"]
    assert job["timeout-minutes"] == 20
    assert job["permissions"] == {
        "contents": "read",
        "security-events": "write",
    }
    assert job["strategy"]["matrix"]["language"] == [
        "python",
        "javascript-typescript",
    ]

    steps = job["steps"]
    uses = [step["uses"] for step in steps]
    assert uses == [
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "github/codeql-action/init@cdf488f595d80d6e07e03d4674febd5ab45fa938",
        "github/codeql-action/analyze@cdf488f595d80d6e07e03d4674febd5ab45fa938",
    ]
    # Every third-party Action is pinned to a full commit SHA with a
    # readable version-tag comment, matching this session's house style.
    for line in raw.splitlines():
        if "uses:" in line and "actions/checkout" in line:
            assert "# v7.0.1" in line
        if "uses:" in line and "codeql-action" in line:
            assert "# v4.37.9" in line

    init_step = steps[1]
    assert init_step["with"]["languages"] == "${{ matrix.language }}"
    assert init_step["with"]["build-mode"] == "none"


@pytest.mark.large
def test_disabling_codeql_omits_the_workflow(tmp_path: Path) -> None:
    """Keep the exclude-list branch honest when CodeQL stays off."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "no-codeql-fixture"
    run_copy(
        str(source),
        project,
        data={
            "languages": ["python"],
            "project_name": "No CodeQL Fixture",
            "project_slug": "no-codeql-fixture",
            "project_description": "Exercises the disabled CodeQL path.",
            "repository_url": "https://github.com/example/no-codeql-fixture",
            "security_reporting_channel": "Use the private security contact.",
            "project_visibility": "private",
            "enable_codeql": False,
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    assert not (project / ".github/workflows/codeql.yml").exists()


@pytest.mark.large
def test_docker_feature_generates_container_starter_files(
    tmp_path: Path,
) -> None:
    """Prove the docker feature renders a usable Dockerfile, compose file,
    and an opt-in, registry-free build-and-scan CI workflow (#554).

    Direction 1 (opt-in Dockerfile/docker-compose template) and direction 2
    (opt-in CI build-and-scan job) were both selected for downstream
    projects that are or want to be containerized, without reopening the
    "no pre-provisioned container job for every repo" boundary recorded in
    docs/adr/selective-ci-automation-adoption.md: the workflow only exists
    when a project opts in, and it never authenticates to or pushes to any
    registry.
    """
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "docker-fixture"
    run_copy(
        str(source),
        project,
        data={
            "languages": ["python"],
            "project_name": "Docker Fixture",
            "project_slug": "docker-fixture",
            "project_description": "Exercises the Docker option generator.",
            "repository_url": "https://github.com/example/docker-fixture",
            "security_reporting_channel": "Use the private security contact.",
            "project_visibility": "private",
            "features": ["docker"],
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    dockerfile = project / "Dockerfile"
    compose = project / "docker-compose.yml"
    workflow_path = project / ".github/workflows/docker-build-scan.yml"
    assert dockerfile.is_file()
    assert compose.is_file()
    assert workflow_path.is_file()

    dockerfile_text = dockerfile.read_text(encoding="utf-8")
    assert "{%" not in dockerfile_text
    assert "FROM python:3.14-slim AS python-build" in dockerfile_text
    assert "FROM python:3.14-slim AS runtime" in dockerfile_text
    # Only the selected language's build stage is present.
    assert "typescript-build" not in dockerfile_text
    assert "rust-build" not in dockerfile_text

    compose_text = compose.read_text(encoding="utf-8")
    assert "{%" not in compose_text
    compose_doc = yaml.safe_load(compose_text)
    assert compose_doc["services"]["docker-fixture"]["build"] == "."
    assert compose_doc["services"]["docker-fixture"]["image"] == (
        "docker-fixture:local"
    )

    raw = workflow_path.read_text(encoding="utf-8")
    assert "{%" not in raw
    workflow = yaml.safe_load(raw)
    assert workflow["permissions"] == {"contents": "read"}
    triggers = workflow.get("on", workflow.get(True))
    assert "Dockerfile" in triggers["pull_request"]["paths"]
    assert "workflow_dispatch" in triggers

    job = workflow["jobs"]["build-and-scan"]
    assert "permissions" not in job  # no job-level permission escalation
    steps = job["steps"]
    uses = [step.get("uses") for step in steps]
    # No registry login step and no push of the built image: the job only
    # builds locally on the runner and scans that local image.
    assert not any(str(u).startswith("docker/login-action") for u in uses)
    assert any(u and u.startswith("docker/build-push-action") for u in uses)
    assert any(u and u.startswith("aquasecurity/trivy-action") for u in uses)
    build_step = next(
        step
        for step in steps
        if str(step.get("uses", "")).startswith("docker/build-push-action")
    )
    assert build_step["with"]["push"] is False


@pytest.mark.large
def test_disabling_docker_omits_container_files(tmp_path: Path) -> None:
    """Keep the exclude-list branch honest when the Docker option stays off:
    a non-container project must gain no Dockerfile, no compose file, and no
    triggered CI job (#554)."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "no-docker-fixture"
    run_copy(
        str(source),
        project,
        data={
            "languages": ["python"],
            "project_name": "No Docker Fixture",
            "project_slug": "no-docker-fixture",
            "project_description": "Exercises the disabled Docker path.",
            "repository_url": "https://github.com/example/no-docker-fixture",
            "security_reporting_channel": "Use the private security contact.",
            "project_visibility": "private",
            "features": [],
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    assert not (project / "Dockerfile").exists()
    assert not (project / "docker-compose.yml").exists()
    assert not (project / ".github/workflows/docker-build-scan.yml").exists()


@pytest.mark.parametrize(
    "features",
    [[], ["repo-site"], ["docker"], ["repo-site", "docker"]],
)
def test_optional_features_render_independently(
    tmp_path: Path, features: list[str]
) -> None:
    """Cover every repo-site and Docker selection without coupled behavior."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "feature-fixture"
    run_copy(
        str(source),
        project,
        data={
            "languages": [],
            "project_name": "Feature Fixture",
            "project_slug": "feature-fixture",
            "project_description": "Exercises independent optional features.",
            "repository_url": "https://github.com/example/feature-fixture",
            "security_reporting_channel": "Use the private security contact.",
            "project_visibility": "private",
            "features": features,
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    site_enabled = "repo-site" in features
    docker_enabled = "docker" in features
    assert (project / ".csarc/site").exists() is site_enabled
    assert (project / "docs/site").exists() is site_enabled
    assert (project / ".csarc/scripts/build-repo-site").exists() is site_enabled
    verify = (project / ".csarc/scripts/verify").read_text(encoding="utf-8")
    assert (
        "./.csarc/scripts/build-repo-site --check" in verify
    ) is site_enabled
    pages = json.loads(
        (project / ".csarc/policies/pages.json").read_text(encoding="utf-8")
    )
    assert pages["enabled"] is site_enabled

    assert (project / "Dockerfile").exists() is docker_enabled
    assert (project / "docker-compose.yml").exists() is docker_enabled
    assert (
        project / ".github/workflows/docker-build-scan.yml"
    ).exists() is docker_enabled
