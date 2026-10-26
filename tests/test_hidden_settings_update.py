"""Issue #1298: `csarc update` keeps saved hidden (`when: false`) settings.

A real Copier render is the only way to prove the template, the CLI's
update data, and the answers-file template together keep a saved value
the template never asks for.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import settings_support
import yaml

from csarc_cli import settings_schema
from csarc_cli.cli import main as cli_main

pytestmark = pytest.mark.large

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_URL = "https://github.com/example/hidden-settings"
OLD_TAG = "v0.41.0"
MERGER = "sole-maintainer"
PROJECT_URL = "https://github.com/orgs/example/projects/7"


def main(arguments: list[str]) -> int:
    """Run the CLI with the explicit setup seeds a script passes (#1078)."""
    return cli_main(settings_support.seeded_setup(arguments))


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
    """Build a local template source with the old tag and this tree."""
    found = subprocess.run(  # noqa: S603
        [
            shutil.which("git") or "git",
            "-C",
            str(ROOT),
            "rev-parse",
            "--verify",
            "--quiet",
            f"{OLD_TAG}^{{commit}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if found.returncode != 0:
        pytest.skip(f"release tag {OLD_TAG} is not available in this clone")
    source = tmp_path_factory.mktemp("hidden") / "template-source"
    source.mkdir()
    git(source, "init", "-q", "-b", "main")
    git(
        source,
        "fetch",
        "--quiet",
        "--depth",
        "1",
        ROOT.as_uri(),
        f"refs/tags/{OLD_TAG}:refs/tags/{OLD_TAG}",
    )
    git(source, "reset", "--quiet", "--hard", OLD_TAG)
    for name in ("copier.yml",):
        shutil.copy2(ROOT / name, source / name)
    shutil.rmtree(source / "template")
    shutil.copytree(
        ROOT / "template",
        source / "template",
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    current = commit_all(source, "test: current template")
    return {
        "source": str(source),
        "current": current,
        "old": git(source, "rev-parse", f"{OLD_TAG}^{{commit}}"),
    }


def saved(project: Path) -> dict[str, object]:
    """Read the project's settings file."""
    payload = yaml.safe_load(
        (project / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    assert isinstance(payload, dict)
    return payload


@pytest.fixture
def old_project(
    tmp_path: Path,
    template_source: dict[str, str],
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Create a project at the old release with hidden settings saved."""
    project = tmp_path / "hidden-settings"
    code = main(
        [
            "init",
            str(project),
            "--source",
            template_source["source"],
            "--to",
            template_source["old"],
            "--allow-unreleased",
            "--yes",
            "--non-interactive",
            "--data",
            "languages=[]",
            "--data",
            f"repository_url={REPOSITORY_URL}",
            "--data",
            "project_description=Hidden settings fixture.",
            "--data",
            "copyright_holder=Example Owner",
            "--data",
            f"github_project_url={PROJECT_URL}",
            "--data",
            f"single_writer_merger={MERGER}",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    before = saved(project)
    assert before["single_writer_merger"] == MERGER
    assert before["github_project_url"] == PROJECT_URL
    git(project, "init", "-q", "-b", "main")
    commit_all(project, f"test: {OLD_TAG} project")
    return project


def test_update_keeps_saved_hidden_settings(
    old_project: Path,
    tmp_path: Path,
    template_source: dict[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC1/AC2: every saved `when: false` setting survives an update."""
    before = saved(old_project)
    report_dir = tmp_path / "report"
    code = main(
        [
            "update",
            str(old_project),
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
    after = saved(old_project)
    for key in ("single_writer_merger", "github_project_url"):
        assert after.get(key) == before[key], key
    assert after["release_ownership"] == before["release_ownership"]


def test_update_check_reports_the_hidden_settings_apply_writes(
    old_project: Path,
    template_source: dict[str, str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3: the check reports the hidden settings the apply really writes.

    With forwarding the saved values stay and nothing changes. With the
    forwarding removed, as before #1298, the check must report the lost
    setting instead of `answers_changed: false` (#1153).
    """

    def check() -> dict[str, object]:
        code = main(
            [
                "update",
                str(old_project),
                "--check",
                "--json",
                "--to",
                template_source["current"],
                "--allow-unreleased",
            ]
        )
        captured = capsys.readouterr()
        # 1 reports an available update; 2 would be an error.
        assert code == 1, captured.out + captured.err
        status = json.loads(captured.out)
        assert isinstance(status, dict)
        return status

    kept = check()
    answers = kept["answers"]
    assert isinstance(answers, dict)
    assert answers["single_writer_merger"] == MERGER
    assert answers["github_project_url"] == PROJECT_URL
    assert kept["answers_changed"] is False

    monkeypatch.setattr(settings_schema, "HIDDEN_SETTINGS", ())
    lost = check()
    answers = lost["answers"]
    assert isinstance(answers, dict)
    assert "single_writer_merger" not in answers
    assert answers["github_project_url"] == ""
    assert lost["answers_changed"] is True
