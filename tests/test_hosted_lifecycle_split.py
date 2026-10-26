"""Hosted-only lifecycle paths stay out of local renders (Issue #1230).

`actions_run_url` only reads hosted Actions check runs, so its code lives in
`pr_lifecycle_hosted.py`, which only hosted projects render. `close-work`
moved back to the shared module (Issue #1294): local and self-hosted
projects close Milestone work Issues with it too. An existing project that
updates sees the module change as an ordinary template change, and a local
project never gains the hosted file.
"""

from __future__ import annotations

import argparse
import ast
import json
import runpy
from pathlib import Path

import pytest
import settings_support
import yaml
from test_cli import commit, git, make_template
from test_generated_runtime_boundary import minimal_render

from csarc_cli.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "template/.csarc/scripts"
LIFECYCLE = ".csarc/scripts/pr_lifecycle.py"
HOSTED = ".csarc/scripts/pr_lifecycle_hosted.py"
MOVED = ("actions_run_url",)
# Issue #1294: close-work runs in every verification mode.
SHARED = ("WORK_CLOSURE_MARKER", "close_work_issue", "work_closure_message")


def top_level_names(path: Path) -> dict[str, str]:
    """Return each top-level name and the kind of statement defining it."""
    names: dict[str, str] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef):
            names[node.name] = "def"
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names[target.id] = "assign"
    return names


def test_hosted_only_paths_live_in_the_hosted_sibling() -> None:
    """AC1: every moved definition is defined only in the hosted file."""
    shared = top_level_names(SCRIPTS / "pr_lifecycle.py")
    hosted = top_level_names(SCRIPTS / "pr_lifecycle_hosted.py")
    for name in MOVED:
        assert name in hosted, name
        assert name not in shared, name
    for name in SHARED:
        assert name in shared, name
        assert name not in hosted, name
    assert shared["close_work_issue"] == "def"


def test_local_render_runs_close_work_without_the_hosted_paths(
    tmp_path: Path,
) -> None:
    """#1294 AC1: a local render lacks hosted code but runs `close-work`."""
    project = minimal_render(tmp_path)
    assert not (project / HOSTED).exists()
    local = runpy.run_path(str(project / LIFECYCLE))
    for name in MOVED:
        assert name not in local, name
    arguments = argparse.Namespace(
        repo="owner/repo", pr_number=44, head_sha="a" * 40
    )

    class Unavailable:
        def get(self, _repo: str, _path: str) -> None:
            return None

    # It reaches the GitHub checks instead of the hosted-mode refusal.
    with pytest.raises(RuntimeError, match="Work Issue closure: state"):
        local["close_work_issue"](arguments, Unavailable())
    # Read through the module as review_gate does: absent, not a crash.
    with pytest.raises(AttributeError):
        local["__getattr__"]("actions_run_url")


def test_hosted_render_reads_the_moved_paths(tmp_path: Path) -> None:
    """AC1: a hosted render reaches the moved names through the module."""
    project = minimal_render(tmp_path, "pr_lifecycle_hosted.py")
    hosted = runpy.run_path(str(project / LIFECYCLE))
    run_url = hosted["__getattr__"]("actions_run_url")(
        "https://github.com/owner/repo/actions/runs/7/job/9", "owner/repo"
    )
    assert run_url == "https://github.com/owner/repo/actions/runs/7"
    assert hosted["WORK_CLOSURE_MARKER"]


def main(arguments: list[str]) -> int:
    """Run the CLI with the explicit setup seeds a script passes (#1078)."""
    return cli_main(settings_support.seeded_setup(arguments))


def write(path: Path, content: str) -> None:
    """Write one fixture file, creating its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def hosted_rule() -> str:
    """Return the shipped Copier exclusion rule for the hosted sibling."""
    config = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    rules = [
        rule
        for rule in config["_exclude"]
        if rule.endswith(f"{HOSTED}{{% endif %}}")
    ]
    assert len(rules) == 1
    return rules[0]


def init_project(
    tmp_path: Path, source: Path, sha: str, name: str, mode: str
) -> Path:
    """Render and commit one project from the fixture template."""
    project = tmp_path / name
    assert (
        main(
            [
                "init",
                "--data",
                f"repository_url=https://github.com/example-org/{name}",
                str(project),
                "--source",
                str(source),
                "--to",
                sha,
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
                "--data",
                "language=ci",
                "--data",
                f"verification_mode={mode}",
            ]
        )
        == 0
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: rendered project")
    return project


def update_plan(
    tmp_path: Path, project: Path, sha: str, capsys: pytest.CaptureFixture[str]
) -> dict[str, list[str]]:
    """Return the file groups of a checked update plan."""
    reports = tmp_path / f"{project.name}-reports"
    capsys.readouterr()
    assert main(
        [
            "update",
            str(project),
            "--to",
            sha,
            "--allow-unreleased",
            "--check",
            "--report-dir",
            str(reports),
        ]
    ) in {0, 1}, capsys.readouterr().err
    plan = json.loads(
        (reports / "csarc-update-plan.json").read_text(encoding="utf-8")
    )
    return plan["files"]


@pytest.mark.large
def test_update_plan_moves_hosted_paths_without_removing_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC2: local projects get the shrunk module and never the hosted file."""
    source, _first = make_template(tmp_path)
    config_path = source / "copier.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["verification_mode"] = {"type": "str", "default": "local"}
    config["_exclude"] = [*config.get("_exclude", []), hosted_rule()]
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    template = source / "template"
    write(template / LIFECYCLE, "def close_work_issue():\n    pass\n")
    write(template / HOSTED, "HOSTED = True\n")
    old_sha = commit(source, "test: close-work in the shared module")
    local = init_project(tmp_path, source, old_sha, "local", "local")
    hosted = init_project(tmp_path, source, old_sha, "hosted", "hosted")
    assert not (local / HOSTED).exists()
    assert (hosted / HOSTED).is_file()

    write(template / LIFECYCLE, "close_work_issue = forward\n")
    write(template / HOSTED, "HOSTED = True\n\ndef close_work_issue():\n")
    new_sha = commit(source, "test: close-work in the hosted sibling")

    files = update_plan(tmp_path, local, new_sha, capsys)
    planned = {path for group in files.values() for path in group}
    assert HOSTED not in planned
    assert LIFECYCLE in {*files["overwrite"], *files["automatic_merge"]}
    assert not {*files["remove"], *files["delete"]}

    files = update_plan(tmp_path, hosted, new_sha, capsys)
    changed = {*files["overwrite"], *files["automatic_merge"]}
    assert {LIFECYCLE, HOSTED} <= changed
    assert not {*files["remove"], *files["delete"]}
