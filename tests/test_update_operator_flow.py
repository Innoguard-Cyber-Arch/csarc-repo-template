"""Operator-facing update guidance (Issue #1147).

An operator who reads only the public documentation must be able to follow
``csarc status`` and the update report through check -> finalize -> apply
without guessing a flag or reading template source.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytest
import settings_support
from test_cli import commit, git, initialize_installed_project, make_template

from csarc_cli import cli, final_plan
from csarc_cli.cli import main as cli_main


def main(arguments: list[str] | None = None) -> int:
    """Run the CLI with the explicit setup seeds a script passes (#1078)."""
    return cli_main(settings_support.seeded_setup(arguments))


def git_identity(project: Path) -> None:
    """Make one fixture directory a committed Git repository."""
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: generated project")


def test_status_next_command_names_release_and_three_stages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC1/R1: the update hint pins the release and orders every stage."""
    source, project, _first_sha = initialize_installed_project(tmp_path)
    git_identity(project)
    (source / "template" / "managed.txt").write_text(
        "template version two\n", encoding="utf-8"
    )
    second_sha = commit(source, "test: template version two")
    capsys.readouterr()

    arguments = [
        "status",
        str(project),
        "--to",
        second_sha,
        "--expected-sha",
        second_sha,
        "--allow-unreleased",
    ]
    assert main([*arguments, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == cli.INSTALL_STATE_UPDATE
    hint = payload["next_command"]
    release = f"--to {second_sha} --expected-sha {second_sha}"
    assert hint.count(release) == 2
    assert hint.count("--allow-unreleased") == 2
    check = hint.index("--check")
    finalize = hint.index("--finalize-plan")
    decision = hint.index("--decision PATH=keep-current|take-new|custom:FILE")
    apply = hint.index(
        f"--apply-plan <path>-csarc-update-report/"
        f"{final_plan.FINAL_PLAN_BASENAME}"
    )
    assert check < finalize < decision < apply
    # The apply stage takes only the plan; it rejects --to and friends.
    assert release not in hint[apply:]

    assert main(arguments) == 0
    assert f"Next: {hint}" in capsys.readouterr().out


def test_update_next_command_without_explicit_release_still_pins_it() -> None:
    """AC1: a resolved stable release is pinned the same way."""
    hint = cli.update_next_command(
        {"target_version": "v1.2.3", "target_sha": "a" * 40}
    )
    assert hint.count(f"--to v1.2.3 --expected-sha {'a' * 40}") == 2
    assert "--allow-unreleased" not in hint
    assert hint.index("--check") < hint.index("--finalize-plan")


def test_file_conflict_message_points_to_sides_and_finalize() -> None:
    """AC1/AC2: the report row names the sides and the decision flag."""
    message = cli.update_conflict_message("docs/README.md")
    for side in ("base", "current", "new"):
        assert f"conflicts/{side}/docs/README.md" in message
    assert "--finalize-plan --decision docs/README.md=" in message
    assert "resolve the file in the target" not in message
    error = cli.update_conflict_error(["docs/README.md"])
    assert "--finalize-plan --decision" in error
    assert "the target was not changed" in error


def jinja_conflict_fixture(tmp_path: Path) -> tuple[Path, str]:
    """Return a product whose Jinja-rendered file conflicts on update."""
    source, _first = make_template(tmp_path)
    template = source / "template"
    (template / "rendered.txt.jinja").write_text(
        "name: {{ project_name }}\nline two\n", encoding="utf-8"
    )
    first_sha = commit(source, "test: rendered file")
    project = tmp_path / "product"
    assert (
        main(
            [
                "init",
                "--data",
                "repository_url=https://github.com/example-org/product",
                str(project),
                "--source",
                str(source),
                "--to",
                first_sha,
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
                "--data",
                "language=ci",
            ]
        )
        == 0
    )
    (project / "rendered.txt").write_text(
        "name: product edit\nline two\n", encoding="utf-8"
    )
    git_identity(project)
    (template / "rendered.txt.jinja").write_text(
        "name: {{ project_name }} (template)\nline two\n", encoding="utf-8"
    )
    return project, commit(source, "test: rendered file two")


@pytest.mark.large
def test_check_writes_three_readable_sides_for_each_conflict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC2/R2: base, current, and the Jinja-rendered new side are readable.

    The new side is the render the operator would get with take-new, so it
    never contains template syntax; stale sides from an earlier plan are
    replaced, and the report row and next steps name the decision flow.
    """
    project, target_sha = jinja_conflict_fixture(tmp_path)
    report_dir = tmp_path / "report"
    stale = report_dir / "conflicts" / "new" / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("from an earlier plan\n", encoding="utf-8")
    capsys.readouterr()

    assert (
        main(
            [
                "update",
                str(project),
                "--check",
                "--json",
                "--to",
                target_sha,
                "--allow-unreleased",
                "--report-dir",
                str(report_dir),
            ]
        )
        == 1
    )
    capsys.readouterr()
    sides = report_dir / "conflicts"
    assert (sides / "base/rendered.txt").read_text(encoding="utf-8") == (
        "name: Product\nline two\n"
    )
    assert (sides / "current/rendered.txt").read_text(encoding="utf-8") == (
        "name: product edit\nline two\n"
    )
    new_side = (sides / "new/rendered.txt").read_text(encoding="utf-8")
    assert new_side == "name: Product (template)\nline two\n"
    assert "{{" not in new_side
    assert not stale.exists()

    report = json.loads(
        (report_dir / "csarc-update-report.json").read_text(encoding="utf-8")
    )
    [row] = [
        action
        for action in report["required_actions"]
        if action["kind"] == "file-conflict"
    ]
    assert row["subject"] == "rendered.txt"
    assert "conflicts/new/rendered.txt" in row["message"]
    assert "--finalize-plan --decision rendered.txt=" in row["message"]
    commands = [step["command"] for step in report["next_steps"]]
    assert "--finalize-plan --decision" in commands[0]
    assert f"--to {target_sha}" in commands[0]
    assert commands[1].endswith(
        f"--apply-plan {report_dir / final_plan.FINAL_PLAN_BASENAME}"
    )
    markdown = (report_dir / "csarc-update-report.md").read_text(
        encoding="utf-8"
    )
    assert "conflicts/current/rendered.txt" in markdown


ROOT = Path(__file__).resolve().parents[1]
UPDATE_DOCS = (
    ("docs/install.md", "## 更新已導入的 repo", "## 不確定目前狀態時"),
    ("docs/install.en.md", "## Update an adopted repo", "## Not sure of"),
    ("README.md", "### 更新已導入的 repo", "### Agent prompt"),
    ("README.en.md", "### Update an adopted repo", "### Agent prompt"),
)


def subcommand_options(name: str) -> set[str]:
    """Return every option string one csarc subcommand accepts."""
    subparsers = next(
        action
        for action in cli.parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return {
        option
        for action in subparsers.choices[name]._actions
        for option in action.option_strings
    }


def documented_commands(text: str) -> list[list[str]]:
    """Return each fenced ``csarc`` command as tokens after ``csarc``."""
    commands = []
    for block in text.split("```bash\n")[1:]:
        for line in block.split("```", 1)[0].splitlines():
            padded = f" {line} "
            if " csarc " in padded:
                commands.append(padded.split(" csarc ", 1)[1].split())
    return commands


@pytest.mark.parametrize(("relative", "start", "end"), UPDATE_DOCS)
def test_documented_update_flags_match_the_cli(
    relative: str, start: str, end: str
) -> None:
    """AC3/R3: every documented update command parses as the CLI accepts.

    Each fenced command must parse, apply commands must pass the apply-plan
    flag check, finalize commands must repeat the reviewed release, and
    every flag named in the section must exist on update or status.
    """
    text = (ROOT / relative).read_text(encoding="utf-8")
    section = text.split(start, 1)[1].split(end, 1)[0]
    commands = documented_commands(section)
    stages = [
        stage
        for command in commands
        if command[0] == "update"
        for stage in ("--check", "--finalize-plan", "--apply-plan")
        if stage in command
    ]
    assert stages[:3] == ["--check", "--finalize-plan", "--apply-plan"]
    for command in commands:
        args = cli.parser().parse_args(command)
        if command[0] != "update":
            continue
        if args.apply_plan is not None:
            cli.reject_apply_plan_arguments(args)
            assert args.yes
        if args.finalize_plan:
            assert args.to is not None
            assert args.expected_sha is not None
            assert args.decision
    # uvx's own launcher flags precede ``csarc`` in the documented command.
    known = (
        subcommand_options("update")
        | subcommand_options("status")
        | {"--from", "--python"}
    )
    named = set(re.findall(r"(?<![\w-])--[a-z][a-z-]+", section))
    assert named <= known, sorted(named - known)


@pytest.mark.parametrize(
    ("relative", "headings"),
    [
        (
            "docs/install.md",
            (
                "### 失敗後重試",
                "### Action pin 漂移",
                "### 模板 workflow 的衝突裡有產品 job",
                "### 保留的舊檔與過時連結",
                "### 套用時的附帶訊息",
                "### 平行執行",
            ),
        ),
        (
            "docs/install.en.md",
            (
                "### Retry after a failure",
                "### Action pin drift",
                "### A template workflow conflict that contains product jobs",
                "### Kept legacy files and stale links",
                "### Messages printed by apply",
                "### Parallel runs",
            ),
        ),
    ],
)
def test_update_guide_covers_operator_edge_cases(
    relative: str, headings: tuple[str, ...]
) -> None:
    """AC3/AC4: retries, pins, product jobs, kept files, and parallel runs.

    Both languages keep the same subsections, and the guide names the
    report vocabulary the operator acts on.
    """
    text = (ROOT / relative).read_text(encoding="utf-8")
    for heading in headings:
        assert heading in text
    for term in (
        "retire-modified",
        "`move`",
        "product-ci.yml",
        "--pin-commit",
        "conflicts/new/<path>",
        "custom:<file>",
        "--report-dir ../<repo>-csarc-update-report-2",
    ):
        assert term in text, term


def test_pin_commit_is_required_only_while_the_stage1_plan_lists_drift(
    tmp_path: Path,
) -> None:
    """AC5: the single SPEC-008 rule for --pin-commit.

    A stage-1 plan that lists blocking pin drift needs --pin-commit; one that
    lists none (for example a recheck after the pin commit) rejects it, and
    a non-blocking product-pin-newer row never asks for it.
    """
    drift = {
        "action": "actions/checkout",
        "file": ".github/workflows/product.yml",
        "line": 6,
        "new_sha": "2" * 40,
        "old_sha": "1" * 40,
        "reason": "template-pin-changed",
    }
    listed = {"action_pin_preflight": {"items": [drift]}}
    rechecked: dict[str, object] = {"action_pin_preflight": {"items": []}}
    newer = {
        "action_pin_preflight": {
            "items": [dict(drift, reason="product-pin-newer")]
        }
    }
    with pytest.raises(cli.CliError, match="--pin-commit <full SHA>"):
        cli.final_pin_decisions(tmp_path, listed, None)
    with pytest.raises(cli.CliError, match="lists no action pin drift"):
        cli.final_pin_decisions(tmp_path, rechecked, "3" * 40)
    empty = {"commit": None, "decisions": [], "items": []}
    assert cli.final_pin_decisions(tmp_path, rechecked, None) == empty
    assert cli.final_pin_decisions(tmp_path, newer, None) == empty
    spec = (ROOT / "docs/specs/SPEC-008-lifecycle-report-format.md").read_text(
        encoding="utf-8"
    )
    assert "`--pin-commit` 只在**被 finalize 的那份 stage-1 plan**" in spec
