"""Existing projects see the #1208 Milestone-script removals in the plan.

A local project without `lifecycle: milestones` stops receiving the three
Milestone-only scripts. Updating it must list each removal in the
reviewable plan, keep a script its own product files still run
(#1146), and leave a project with Milestones untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import settings_support
import yaml
from test_cli import commit, git, make_template

from csarc_cli.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
MILESTONE_SCRIPTS = (
    ".csarc/scripts/sync_milestone_state.py",
    ".csarc/scripts/promotion_gate.py",
    ".csarc/scripts/delivery_sync.py",
)
USED = ".csarc/scripts/sync_milestone_state.py"
PRODUCT_WORKFLOW = ".github/workflows/product-milestones.yml"


def main(arguments: list[str]) -> int:
    """Run the CLI with the explicit setup seeds a script passes (#1078)."""
    return cli_main(settings_support.seeded_setup(arguments))


def write(path: Path, content: str) -> None:
    """Write one fixture file, creating its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def real_rules() -> list[str]:
    """Return the shipped Copier exclusion rules for the three scripts."""
    config = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    rules = [
        rule
        for rule in config["_exclude"]
        if any(
            rule.endswith(f"{path}{{% endif %}}") for path in MILESTONE_SCRIPTS
        )
    ]
    assert len(rules) == len(MILESTONE_SCRIPTS)
    return rules


def init_project(
    tmp_path: Path, source: Path, sha: str, name: str, lifecycle: str
) -> Path:
    """Render one committed project from the fixture template."""
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
                f"lifecycle={lifecycle}",
            ]
        )
        == 0
    )
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
def test_update_plan_lists_each_milestone_script_removal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """R2: removals are planned; a product use keeps that script."""
    source, _first = make_template(tmp_path)
    config_path = source / "copier.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["verification_mode"] = {"type": "str", "default": "local"}
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    template = source / "template"
    for path in MILESTONE_SCRIPTS:
        write(template / path, "print('milestone script')\n")
    old_sha = commit(source, "test: Milestone scripts on every render")

    solo = init_project(tmp_path, source, old_sha, "solo", "[]")
    # The product runs one Milestone script itself, so that one must stay.
    write(
        solo / PRODUCT_WORKFLOW,
        "on: push\njobs:\n  check:\n    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: python3 .csarc/scripts/sync_milestone_state.py\n",
    )
    team = init_project(
        tmp_path, source, old_sha, "team", "[issues, milestones]"
    )
    for project in (solo, team):
        git(project, "init", "-b", "main")
        git(project, "config", "user.name", "CLI Test")
        git(project, "config", "user.email", "cli-test@example.invalid")
        commit(project, "test: rendered project")
    assert all((solo / path).is_file() for path in MILESTONE_SCRIPTS)

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["_exclude"] = [*config.get("_exclude", []), *real_rules()]
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    new_sha = commit(source, "test: Milestone scripts only with Milestones")

    files = update_plan(tmp_path, solo, new_sha, capsys)
    removed = {*files["remove"], *files["delete"]}
    assert removed == set(MILESTONE_SCRIPTS) - {USED}
    # Like the product-owned Release workflow (#1083), an option-driven
    # removal a product file still uses stays in the plan's kept files.
    assert USED in files["preserve"]

    files = update_plan(tmp_path, team, new_sha, capsys)
    removed = {*files["remove"], *files["delete"]}
    assert not removed & set(MILESTONE_SCRIPTS)
    assert set(MILESTONE_SCRIPTS) <= set(files["preserve"])
