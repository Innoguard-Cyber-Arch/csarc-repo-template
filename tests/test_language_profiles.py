"""Tests for composable language-profile generation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml
from copier import run_copy, run_update

from csarc_cli import cli

ROOT = Path(__file__).resolve().parents[1]


def _resolve_pytest_evidence(
    root: Path, node_ids: list[str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *node_ids],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def test_languages_are_independent_modules() -> None:
    """Offer language modules instead of enumerating combinations."""
    config = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    question = config["languages"]

    assert question["multiselect"] is True
    assert list(question["choices"].values()) == [
        "go",
        "python",
        "rust",
        "typescript",
    ]
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
    promotion_evidence = catalog["promotion_evidence"]
    lifecycle = promotion_evidence["language_module_lifecycle"]
    assert lifecycle == {
        "status": "satisfied",
        "method": "shared_representative_canaries",
        "evidence": [
            "tests/test_cli.py::test_real_existing_adoption_uses_fixed_ownership_policies",
            "tests/test_cli.py::test_previous_release_to_current_managed_file_migration",
        ],
    }
    for language in ("python", "rust", "typescript"):
        assert catalog["profiles"][language]["stage"] == "beta"
        evidence = promotion_evidence[language]
        assert evidence["status"] == "satisfied"
        assert evidence["method"] == "generated_native_verification"
        assert evidence["evidence"] == [
            "tests/test_language_profiles.py::test_representative_generated_project_runs_full_verifier",
            "scripts/verify-template.sh",
        ]

    assert catalog["profiles"]["go"]["stage"] == "future"
    assert "go" not in promotion_evidence

    repository_evidence = {
        reference
        for item in promotion_evidence.values()
        if isinstance(item, dict)
        for reference in item.get("evidence", [])
        if isinstance(reference, str) and "://" not in reference
    }
    for reference in repository_evidence:
        assert (ROOT / reference.partition("::")[0]).is_file()
    pytest_nodes = sorted(
        reference for reference in repository_evidence if "::" in reference
    )
    resolved = _resolve_pytest_evidence(ROOT, pytest_nodes)
    assert resolved.returncode == 0, resolved.stdout + resolved.stderr


def test_go_profile_contract_uses_native_toolchain_only() -> None:
    """Pin the reviewed Go contract while the profile is a candidate."""
    catalog = yaml.safe_load(
        (ROOT / "profiles/catalog.yaml").read_text(encoding="utf-8")
    )
    go = catalog["profiles"]["go"]

    assert go["stage"] == "future"
    assert go["candidate"].endswith("/issues/941")
    assert "reason" not in go
    assert go["latest_reviewed_stable"] == "1.27.1"
    assert go["minimum"] == "1.27"
    assert go["go_directive"] == f"{go['minimum']}.0"
    assert go["latest_reviewed_stable"].startswith(f"{go['minimum']}.")
    assert go["toolchain_directive"] == "none"
    assert go["toolchain_download"] == "disabled"
    assert go["package_manager"] == "go_modules"
    assert go["lockfile_policy"] == "only_when_dependencies_exist"
    assert go["tools"] == {
        "format": "gofmt",
        "lint": "go_vet",
        "test": "go_test",
        "build": "go_build",
    }
    assert go["release_type"] == "simple"
    assert go["version_in_go_mod"] is False
    assert go["distribution"] == "github_release_source_archive"
    modules = catalog["compositions"]["language_modules"]
    assert "go" in modules["selectable_profiles"]


def test_selectable_languages_are_beta_or_milestone_candidates() -> None:
    """Offer a future profile only while its Milestone delivers it."""
    catalog = yaml.safe_load(
        (ROOT / "profiles/catalog.yaml").read_text(encoding="utf-8")
    )
    config = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    selectable = catalog["compositions"]["language_modules"][
        "selectable_profiles"
    ]

    assert selectable == list(config["languages"]["choices"].values())
    for language in selectable:
        profile = catalog["profiles"][language]
        assert profile["stage"] == "beta" or "candidate" in profile


def test_promotion_evidence_resolver_rejects_stale_pytest_nodes(
    tmp_path: Path,
) -> None:
    """Fail when catalog evidence names a missing pytest node."""
    (tmp_path / "test_evidence.py").write_text(
        "def test_current():\n    pass\n", encoding="utf-8"
    )

    current = _resolve_pytest_evidence(
        tmp_path, ["test_evidence.py::test_current"]
    )
    stale = _resolve_pytest_evidence(
        tmp_path, ["test_evidence.py::test_removed"]
    )

    assert current.returncode == 0, current.stdout + current.stderr
    assert stale.returncode != 0


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

    (tmp_path / "go.mod").touch()
    assert cli.detect_languages(tmp_path) == [
        "go",
        "python",
        "rust",
        "typescript",
    ]


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


@pytest.mark.parametrize(
    ("languages", "enabled"),
    [(["go"], True), (["rust"], False), (["python", "rust"], True)],
)
def test_public_visibility_enables_codeql_only_for_analyzed_modules(
    languages: list[str], enabled: bool
) -> None:
    """Match copier.yml so a Rust-only project never gets an empty matrix."""
    repository = cli.RepositoryContext(
        "owner/repository",
        "owner",
        "Organization",
        "public",
        "github",
        True,
    )

    _answers, update_data = cli.update_plan_answers(
        {
            "languages": languages,
            "project_mode": "new",
            "project_visibility": "private",
            "enable_codeql": False,
        },
        {},
        repository,
    )

    assert update_data["enable_codeql"] == str(enabled).lower()


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
        "languages:\n- go\n- rust\n- typescript\n", encoding="utf-8"
    )
    (tmp_path / "go.mod").touch()
    (tmp_path / "Cargo.toml").touch()
    (tmp_path / "package.json").touch()

    detected = subprocess.run(  # noqa: S603
        [detector], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    assert detected == "language modules: go,rust,typescript"


@pytest.mark.large
def test_representative_generated_project_runs_full_verifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run one mixed generated project through the complete verifier once."""
    required_tools = ("uv", "node", "pnpm", "cargo", "rustc", "go")
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
        "languages=go,python,typescript,rust",
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
    assert config["languages"] == ["go", "python", "rust", "typescript"]
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
        for manifest in (
            "go.mod",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
        )
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
        "LICENSE",
        "README.en.md",
        "README.md",
        "SECURITY.md",
        "biome.json",
        "cmd",
        "coverage",
        "dist",
        "docs",
        "go.mod",
        "internal",
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


def _git_template_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    for command in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.name", "Go Test"],
        ["git", "config", "user.email", "go@example.invalid"],
        ["git", "add", "."],
        ["git", "commit", "-m", "test: template"],
    ):
        cli.run(command, cwd=source, capture=True)
    return source


GO_DATA = {
    "project_name": "Go Fixture",
    "project_slug": "go-fixture",
    "project_description": "Exercises the Go module.",
    "repository_url": "https://github.com/example/go-fixture",
    "security_reporting_channel": "Use the private security contact.",
}


@pytest.mark.large
def test_go_selection_controls_generated_go_files(tmp_path: Path) -> None:
    """Create Go files only for Go and keep mixed run commands composable."""
    source = _git_template_source(tmp_path)
    rendered: dict[str, Path] = {}
    for name, languages in (
        ("go-only", ["go"]),
        ("go-python", ["go", "python"]),
        ("no-go", ["python"]),
    ):
        target = tmp_path / name
        run_copy(
            str(source),
            target,
            data={**GO_DATA, "languages": languages},
            defaults=True,
            unsafe=True,
            skip_tasks=True,
            vcs_ref="HEAD",
        )
        rendered[name] = target

    go_only = rendered["go-only"]
    assert (go_only / "go.mod").read_text(encoding="utf-8") == (
        "module github.com/example/go-fixture\n\ngo 1.27.0\n"
    )
    assert (go_only / "cmd/go-fixture/main.go").is_file()
    assert (go_only / "internal/go_fixture/go_fixture_test.go").is_file()
    assert not (go_only / "go.sum").exists()
    assert "toolchain" not in (go_only / "go.mod").read_text(encoding="utf-8")
    release_config = json.loads(
        (go_only / ".csarc/release-please-config.json").read_text(
            encoding="utf-8"
        )
    )
    assert release_config["release-type"] == "simple"
    assert (go_only / ".csarc/version.txt").is_file()
    assert not (rendered["go-python"] / ".csarc/version.txt").exists()
    go_only_answers = yaml.safe_load(
        (go_only / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    assert go_only_answers["project_run_command"] == "go build ./..."
    mixed_answers = yaml.safe_load(
        (rendered["go-python"] / ".csarc/config.yml").read_text(
            encoding="utf-8"
        )
    )
    assert mixed_answers["project_run_command"] == (
        "uv run python -c 'import go_fixture' && go build ./..."
    )
    no_go = rendered["no-go"]
    assert not any(
        (no_go / path).exists()
        for path in ("go.mod", "go.sum", "cmd", "internal")
    )
    assert "verify_go=false" in (no_go / ".csarc/scripts/verify").read_text(
        encoding="utf-8"
    )


@pytest.mark.large
def test_existing_go_adoption_and_update_preserve_product_module(
    tmp_path: Path,
) -> None:
    """Keep product go.mod, source, and no go.sum through adopt and update."""
    source = _git_template_source(tmp_path)
    project = tmp_path / "existing-go"
    (project / "app").mkdir(parents=True)
    product_mod = "module example.com/product\n\ngo 1.27.0\n"
    product_main = 'package main\n\nfunc main() { println("product") }\n'
    (project / "go.mod").write_text(product_mod, encoding="utf-8")
    (project / "app/main.go").write_text(product_main, encoding="utf-8")
    for command in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.name", "Go Test"],
        ["git", "config", "user.email", "go@example.invalid"],
        ["git", "add", "."],
        ["git", "commit", "-m", "test: product"],
    ):
        cli.run(command, cwd=project, capture=True)
    assert cli.detect_languages(project) == ["go"]

    run_copy(
        str(source),
        project,
        data={**GO_DATA, "languages": ["go"], "project_mode": "existing"},
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        overwrite=True,
        vcs_ref="HEAD",
    )

    assert (project / "go.mod").read_text(encoding="utf-8") == product_mod
    assert (project / "app/main.go").read_text(encoding="utf-8") == product_main
    assert not (project / "go.sum").exists()
    assert not (project / "cmd").exists()
    assert not (project / "internal").exists()

    cli.run(["git", "add", "."], cwd=project, capture=True)
    cli.run(["git", "commit", "-m", "test: adopt"], cwd=project, capture=True)
    notice = source / "template/.csarc/go-update-probe.txt"
    notice.write_text("template-owned\n", encoding="utf-8")
    cli.run(["git", "add", "."], cwd=source, capture=True)
    cli.run(["git", "commit", "-m", "test: update"], cwd=source, capture=True)
    run_update(
        project,
        answers_file=".csarc/config.yml",
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        overwrite=True,
        vcs_ref="HEAD",
    )

    assert (project / ".csarc/go-update-probe.txt").is_file()
    assert (project / "go.mod").read_text(encoding="utf-8") == product_mod
    assert (project / "app/main.go").read_text(encoding="utf-8") == product_main
    assert not (project / "go.sum").exists()


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
            "verification_mode": "hosted",
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
            "verification_mode": "hosted",
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
def test_local_docker_feature_reuses_full_verification(tmp_path: Path) -> None:
    """Local mode replaces the hosted container job without a second suite."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "local-docker-fixture"
    run_copy(
        str(source),
        project,
        data={
            "languages": ["python"],
            "project_description": "Local container fixture.",
            "project_name": "Local Container Fixture",
            "project_slug": "local-container-fixture",
            "repository_url": (
                "https://github.com/example/local-container-fixture"
            ),
            "security_reporting_channel": "Use the private contact.",
            "features": ["docker"],
            "verification_mode": "local",
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    assert not (project / ".github/workflows/docker-build-scan.yml").exists()
    for workflow in (
        "ci.yml",
        "pr-policy.yml",
        "pr-policy-writes.yml",
        "pr-review.yml",
        "governance-comment.yml",
        "spec-to-issue.yml",
        "work-item-lifecycle.yml",
        "pages.yml",
    ):
        assert not (project / ".github/workflows" / workflow).exists()
    pages = json.loads(
        (project / ".csarc/policies/pages.json").read_text(encoding="utf-8")
    )
    assert pages == {"enabled": False, "build_type": "workflow"}
    verifier = (project / ".csarc/scripts/verify").read_text(encoding="utf-8")
    assert verifier.count("verify_container") == 2
    assert (
        'docker build --tag "local-container-fixture:csarc-verification"'
        in verifier
    )
    assert "trivy image --exit-code 1 --severity HIGH,CRITICAL" in verifier


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
    "documentation_mode", ["template-and-content", "content-only", "off"]
)
@pytest.mark.parametrize("features", [[], ["docker"]])
def test_optional_features_render_independently(
    tmp_path: Path, documentation_mode: str, features: list[str]
) -> None:
    """Keep documentation modes and Docker selection independent."""
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
            "verification_mode": "hosted",
            "documentation_mode": documentation_mode,
            "features": features,
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    site_enabled = documentation_mode == "template-and-content"
    content_enabled = documentation_mode != "off"
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
    assert pages["build_type"] == "workflow"
    assert (project / ".github/workflows/pages.yml").exists() is site_enabled
    if site_enabled:
        pages_workflow = yaml.safe_load(
            (project / ".github/workflows/pages.yml").read_text(
                encoding="utf-8"
            )
        )
        triggers = pages_workflow.get("on", pages_workflow.get(True))
        assert triggers["push"]["paths"] == ["docs/**"]
        assert triggers["workflow_dispatch"] is None
    assert (project / "README.md").exists() is content_enabled
    assert (project / "docs/README.md").exists() is content_enabled

    assert (project / "Dockerfile").exists() is docker_enabled
    assert (project / "docker-compose.yml").exists() is docker_enabled
    assert (
        project / ".github/workflows/docker-build-scan.yml"
    ).exists() is docker_enabled


@pytest.mark.parametrize(
    ("project_mode", "documentation_mode", "content_enabled"),
    [
        ("new", "off", False),
        ("existing", "off", False),
        ("new", "content-only", True),
    ],
)
def test_documentation_guidance_matches_rendered_content(
    tmp_path: Path,
    project_mode: str,
    documentation_mode: str,
    content_enabled: bool,
) -> None:
    """Point operational guidance only at documentation that exists."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "documentation-guidance"
    if project_mode == "existing":
        project.mkdir()
        (project / "package.json").write_text(
            '{"name": "documentation-guidance", "private": true}\n',
            encoding="utf-8",
        )

    run_copy(
        str(source),
        project,
        data={
            "project_mode": project_mode,
            "languages": ["typescript"],
            "project_name": "Documentation Guidance",
            "project_slug": "documentation-guidance",
            "project_description": "Exercises mode-specific guidance.",
            "repository_url": "https://github.com/example/documentation-guidance",
            "security_reporting_channel": "Use the private security contact.",
            "project_visibility": "private",
            "documentation_mode": documentation_mode,
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    assert (project / "README.md").exists() is content_enabled
    assert (project / "docs/README.md").exists() is content_enabled

    security = (project / "SECURITY.md").read_text(encoding="utf-8")
    workflow = (project / ".csarc/docs/agent-workflow.md").read_text(
        encoding="utf-8"
    )
    lifecycle = (project / ".csarc/docs/csarc.md").read_text(encoding="utf-8")
    assert "Read `README.md` when present." in security

    if content_enabled:
        assert "`docs/README.md` maps durable project memory" in workflow
        assert "專案自己的 `README.md` 為準" in lifecycle
    else:
        assert "`docs/README.md` maps durable project memory" not in workflow
        assert "`docs/specs/` SDD contract" not in workflow
        assert (
            "`.csarc/docs/csarc.md` is the stable operations entry point"
            in workflow
        )
        assert "專案自己的 `README.md` 為準" not in lifecycle
        assert "既有專案導入 CSARC" not in lifecycle
        assert "root `AGENTS.md`" in lifecycle
        assert "`.csarc/config.yml`" in lifecycle


@pytest.mark.parametrize(
    ("primary_language", "i18n", "project_license"),
    [
        ("zh-tw", "en-zh-tw", "proprietary"),
        ("en", "off", "MIT"),
        ("zh-tw", "off", "Apache-2.0"),
    ],
)
def test_readme_i18n_and_license_metadata_are_synchronized(
    tmp_path: Path,
    primary_language: str,
    i18n: str,
    project_license: str,
) -> None:
    """Render README language and ecosystem license metadata from one source."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "documentation-fixture"
    run_copy(
        str(source),
        project,
        data={
            "languages": ["python", "typescript", "rust"],
            "project_name": "Documentation Fixture",
            "project_slug": "documentation-fixture",
            "project_description": "Exercises documentation and licensing.",
            "repository_url": "https://github.com/example/documentation-fixture",
            "security_reporting_channel": "Use the private security contact.",
            "project_visibility": "private",
            "documentation_mode": "content-only",
            "primary_language": primary_language,
            "i18n": i18n,
            "project_license": project_license,
            "copyright_holder": "Example Owner",
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    readme = (project / "README.md").read_text(encoding="utf-8")
    assert ("## 特色" in readme) is (primary_language == "zh-tw")
    assert "## 目錄" not in readme
    assert "## Table of contents" not in readme
    assert len(readme.splitlines()) < 80
    secondary = project / (
        "README.en.md" if primary_language == "zh-tw" else "README.zh-tw.md"
    )
    assert secondary.exists() is (i18n == "en-zh-tw")

    license_text = (project / "LICENSE").read_text(encoding="utf-8")
    assert "Example Owner" in license_text
    python = tomllib.loads((project / "pyproject.toml").read_text())
    node = json.loads((project / "package.json").read_text())
    rust = tomllib.loads((project / "Cargo.toml").read_text())
    expected = (
        "LicenseRef-Proprietary"
        if project_license == "proprietary"
        else project_license
    )
    assert python["project"]["license"] == expected
    assert python["project"]["license-files"] == ["LICENSE"]
    assert node["license"] == (
        "UNLICENSED" if project_license == "proprietary" else project_license
    )
    assert node["private"] is (project_license == "proprietary")
    if project_license == "proprietary":
        assert rust["package"]["license-file"] == "LICENSE"
        assert "license" not in rust["package"]
    else:
        assert rust["package"]["license"] == project_license
        assert "license-file" not in rust["package"]
    subprocess.run(
        [sys.executable, ".csarc/scripts/check_license_metadata.py"],
        cwd=project,
        check=True,
    )


def test_single_language_site_uses_primary_language_at_index(
    tmp_path: Path,
) -> None:
    """Do not emit a second README or site page when i18n is disabled."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "english-site"
    run_copy(
        str(source),
        project,
        data={
            "languages": [],
            "project_name": "English Site",
            "project_slug": "english-site",
            "project_description": "Exercises a single-language site.",
            "repository_url": "https://github.com/example/english-site",
            "security_reporting_channel": "Use the private security contact.",
            "project_visibility": "private",
            "documentation_mode": "template-and-content",
            "primary_language": "en",
            "i18n": "off",
        },
        defaults=True,
        unsafe=True,
    )

    assert "## Highlights" in (project / "README.md").read_text()
    assert not (project / "README.zh-tw.md").exists()
    assert not (project / "docs/site/content/_index.zh-tw.md").exists()
    assert (project / "docs/index.html").is_file()
    assert not (project / "docs/index.en.html").exists()
    assert not (project / "docs/index.zh-tw.html").exists()
    index = (project / "docs/index.html").read_text(encoding="utf-8")
    assert "[Project documentation](docs/index.html)" in (
        project / "README.md"
    ).read_text(encoding="utf-8")
    assert '<html lang="en"' in index
    assert 'class="language-control"' in index
    assert "繁體中文" not in index

    stale_translation = project / "docs/index.en.html"
    stale_translation.write_text("stale\n", encoding="utf-8")
    site_builder = project / ".csarc/scripts/build-repo-site"
    stale_check = subprocess.run(  # noqa: S603
        [site_builder, "--check"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert stale_check.returncode == 1
    assert "stale for the selected i18n mode" in stale_check.stderr
    subprocess.run(  # noqa: S603
        [site_builder],
        cwd=project,
        check=True,
    )
    assert not stale_translation.exists()


def test_documentation_off_omits_readme_manifest_references(
    tmp_path: Path,
) -> None:
    """Keep package manifests valid when README management is disabled."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "documentation-off"
    run_copy(
        str(source),
        project,
        data={
            "languages": ["python", "typescript", "rust"],
            "project_name": "Documentation Off",
            "project_slug": "documentation-off",
            "project_description": "Exercises disabled documentation.",
            "repository_url": "https://github.com/example/documentation-off",
            "security_reporting_channel": "Use the private security contact.",
            "project_visibility": "private",
            "documentation_mode": "off",
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    assert not (project / "README.md").exists()
    python = tomllib.loads((project / "pyproject.toml").read_text())
    rust = tomllib.loads((project / "Cargo.toml").read_text())
    assert "readme" not in python["project"]
    assert (
        "README.md"
        not in python["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    )
    assert "readme" not in rust["package"]
