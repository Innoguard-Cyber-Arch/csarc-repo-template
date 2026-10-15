"""SPEC-009 end to end: zero-question init, tamper stop, legacy migration.

Issue #1071 AC2/AC3/AC4/AC5/AC8 need a real Copier render: the template
must write intent-only settings, the pinned CLI must bind the render
context in provenance, and a legacy v0.30.3 consumer must migrate to schema
2 in one approved update without seeding product files.
"""

from __future__ import annotations

import builtins
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import settings_support
import yaml

from csarc_cli import settings_schema
from csarc_cli.cli import main as cli_main


def main(arguments: list[str] | None = None) -> int:
    """Run the CLI with the explicit setup seeds a script passes (#1078)."""
    return cli_main(settings_support.seeded_setup(arguments))


pytestmark = pytest.mark.large

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_URL = "https://github.com/example/settings-fixture"
LEGACY_TAG = "v0.30.3"
PROJECT_URL = "https://github.com/orgs/example/projects/7"


def git(cwd: Path, *args: str) -> str:
    """Run one git command and return stripped stdout."""
    return subprocess.run(  # noqa: S603
        [shutil.which("git") or "git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit_all(path: Path, message: str) -> str:
    """Commit every file in a fixture repository."""
    git(path, "add", "-A")
    git(
        path,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        message,
    )
    return git(path, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def template_source(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """Build a local template source with the legacy tag and this tree."""
    found = subprocess.run(  # noqa: S603
        [
            shutil.which("git") or "git",
            "-C",
            str(ROOT),
            "rev-parse",
            "--verify",
            "--quiet",
            f"{LEGACY_TAG}^{{commit}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if found.returncode != 0:
        pytest.skip(f"release tag {LEGACY_TAG} is not available in this clone")
    source = tmp_path_factory.mktemp("settings") / "template-source"
    source.mkdir()
    git(source, "init", "-q", "-b", "main")
    git(
        source,
        "fetch",
        "--quiet",
        "--depth",
        "1",
        ROOT.as_uri(),
        f"refs/tags/{LEGACY_TAG}:refs/tags/{LEGACY_TAG}",
    )
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(
        ROOT / "template",
        source / "template",
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    current = commit_all(source, "test: current template")
    git(source, "tag", "v0.99.0", current)
    return {
        "source": str(source),
        "current": current,
        "legacy": git(source, "rev-parse", f"{LEGACY_TAG}^{{commit}}"),
    }


def saved_keys(project: Path) -> set[str]:
    """Return the keys in the project's settings file."""
    payload = yaml.safe_load(
        (project / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    return set(payload)


def assert_schema_2(project: Path) -> dict[str, object]:
    """Assert intent-only settings bound to a verified provenance record."""
    keys = saved_keys(project)
    allowed = {
        settings_schema.SCHEMA_KEY,
        *settings_schema.COPIER_METADATA_KEYS,
        *settings_schema.INTENT_SETTINGS,
        *settings_schema.DECISION_SETTINGS,
    }
    assert keys <= allowed, keys - allowed
    assert set(settings_schema.INTENT_SETTINGS) <= keys
    provenance = json.loads(
        (project / ".csarc/provenance.json").read_text(encoding="utf-8")
    )
    saved = settings_schema.read_saved_settings(
        project / ".csarc/config.yml", provenance
    )
    assert saved.schema == settings_schema.SCHEMA_VERSION
    assert not (project / settings_schema.RENDER_CONTEXT_FILE).exists()
    return dict(saved.context)


def test_non_interactive_init_asks_nothing_and_saves_only_intent(
    tmp_path: Path,
    template_source: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC2/AC4/AC5: seeds reach provenance, never the settings file."""

    def no_questions(*_args: object) -> str:
        raise AssertionError("non-interactive init must not ask questions")

    monkeypatch.setattr(builtins, "input", no_questions)
    project = tmp_path / "settings-fixture"
    assert (
        main(
            [
                "init",
                str(project),
                "--source",
                template_source["source"],
                "--to",
                template_source["current"],
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
                "--data",
                "languages=[]",
                "--data",
                f"repository_url={REPOSITORY_URL}",
                "--data",
                "project_description=Settings fixture product.",
                "--data",
                "copyright_holder=Example Owner",
                "--data",
                f"github_project_url={PROJECT_URL}",
            ]
        )
        == 0
    )
    capsys.readouterr()
    context = assert_schema_2(project)
    # #1080 AC1: the one Project setting is saved as the full URL only.
    saved = yaml.safe_load(
        (project / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    assert saved["github_project_url"] == PROJECT_URL
    for seed in settings_schema.SEED_KEYS + settings_schema.LIVE_KEYS:
        assert seed not in saved_keys(project)
    assert context["project_mode"] == "new"
    assert context["project_description"] == "Settings fixture product."
    assert context["copyright_holder"] == "Example Owner"
    assert context["repository_url"] == REPOSITORY_URL

    git(project, "init", "-q", "-b", "main")
    commit_all(project, "test: initial project")
    config = project / ".csarc/config.yml"
    original = config.read_text(encoding="utf-8")
    config.write_text(
        original.replace("coverage_threshold: 80", "coverage_threshold: 50"),
        encoding="utf-8",
    )
    status = main(
        [
            "status",
            str(project),
            "--json",
            "--allow-unreleased",
            "--to",
            template_source["current"],
        ]
    )
    output = capsys.readouterr()
    assert status == 2
    assert "does not match its provenance digest" in output.out + output.err
    config.write_text(original, encoding="utf-8")


def test_legacy_consumer_migrates_to_schema_2_in_one_update(
    tmp_path: Path,
    template_source: dict[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC3/AC8: legacy answers are read only by the registry; one approved
    update writes schema 2, reports retired and successor rows, and never
    seeds product files."""
    project = tmp_path / "legacy-consumer"
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "copier",
            "copy",
            "--trust",
            "--defaults",
            "--skip-tasks",
            "--vcs-ref",
            LEGACY_TAG,
            "--data",
            "languages=[]",
            "--data",
            "project_name=Settings Fixture",
            "--data",
            f"repository_url={REPOSITORY_URL}",
            "--data",
            "primary_language=en",
            "--data",
            "i18n=off",
            template_source["source"],
            str(project),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    answers = project / ".csarc/config.yml"
    lines = [
        f"_commit: {template_source['legacy']}"
        if line.startswith("_commit:")
        else line
        for line in answers.read_text(encoding="utf-8").splitlines()
    ]
    answers.write_text("\n".join(lines) + "\n", encoding="utf-8")
    product = project / "src/product.py"
    product.parent.mkdir(parents=True, exist_ok=True)
    product.write_text("VALUE = 1\n", encoding="utf-8")
    git(project, "init", "-q", "-b", "main")
    commit_all(project, f"test: untouched {LEGACY_TAG} consumer")
    legacy_keys = saved_keys(project)
    assert "schema_version" not in legacy_keys
    assert {"primary_language", "i18n", "actions_fallback"} <= legacy_keys

    report_dir = tmp_path / "report"
    code = main(
        [
            "update",
            str(project),
            "--yes",
            "--to",
            template_source["current"],
            "--allow-unreleased",
            "--report-dir",
            str(report_dir),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    context = assert_schema_2(project)
    assert context["project_name"] == "Settings Fixture"
    config = yaml.safe_load(
        (project / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    assert config["documentation_languages"] == "en"
    assert config["python_floor"] == "latest"
    assert "actions_fallback" not in config
    assert product.read_text(encoding="utf-8") == "VALUE = 1\n"
    for seeded in ("pyproject.toml", "package.json", "Cargo.toml", "uv.lock"):
        assert not (project / seeded).exists(), seeded
    report = json.loads(
        (report_dir / "csarc-update-report.json").read_text(encoding="utf-8")
    )
    rows = {row["key"]: row for row in report["settings"]}
    for retired in ("primary_language", "i18n", "actions_fallback"):
        assert rows[retired]["class"] == "retired", retired
    assert rows["documentation_languages"]["class"] == "exact"
    assert rows["container"]["class"] == "exact"
