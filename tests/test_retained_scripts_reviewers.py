"""Operator-run update defects from the beta.6 run (Issue #1157).

A kept legacy script must not lose the files the same plan removes or
moves, a retired reviewer list must ask the owner to confirm the new
reviewer assignment, and ``status`` must hint the documented flags. No
consumer identity is recorded here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_cli import commit, make_template, write_executable
from test_operator_run_regressions import (
    legacy_consumer,
    read_json,
    update,
    write,
)

from csarc_cli import cli, final_plan, governance_migration, lifecycle_report

ROOT = Path(__file__).resolve().parents[1]
LEGACY_VERIFY = (
    "#!/usr/bin/env bash\nset -euo pipefail\n"
    "./scripts/test-pr-policy\n"
    "python3 -m json.tool policies/repository.json >/dev/null\n"
)
EMPTY_PLAN = cli.Plan((), (), (), (), (), (), ())


# --- AC1: a kept legacy script and the files the plan removes -------------


def test_retained_script_uses_lists_removed_and_moved_files(
    tmp_path: Path,
) -> None:
    """AC1/R1: a kept script's removed and moved uses are listed."""
    write_executable(tmp_path / "scripts/verify", LEGACY_VERIFY)
    write(tmp_path / "policies/repository.json", "{}\n")
    # Prose and a non-script file never run anything.
    write(tmp_path / "CLAUDE.md", "Run ./scripts/test-pr-policy first.\n")
    write(tmp_path / "notes.txt", "./scripts/test-pr-policy\n")
    moves = (("policies/repository.json", ".csarc/policies/repository.json"),)

    rows = cli.retained_script_uses(
        tmp_path,
        ("CLAUDE.md", "notes.txt", "scripts/verify"),
        ("scripts/test-pr-policy",),
        moves,
    )
    assert rows == [
        {
            "destination": ".csarc/policies/repository.json",
            "path": "policies/repository.json",
            "script": "scripts/verify",
        },
        {
            "destination": "",
            "path": "scripts/test-pr-policy",
            "script": "scripts/verify",
        },
    ]
    # A move with a compatibility shim is not passed in, so it never counts.
    assert cli.retained_script_uses(tmp_path, ("scripts/verify",), (), ()) == []


def test_kept_script_with_lost_uses_blocks_and_finalize_refuses() -> None:
    """AC1/R1: the retire-modified row blocks; finalize refuses it."""
    files = cli.Plan((), (), (), (), (), (), (), retained=("scripts/verify",))
    uses = [
        {
            "destination": "",
            "path": "scripts/test-pr-policy",
            "script": "scripts/verify",
        }
    ]
    [plain] = cli.update_required_actions(files, ())
    assert plain["kind"] == "retire-modified"
    assert plain["blocking"] is False

    [action] = cli.update_required_actions(files, (), retained_uses=uses)
    assert action["kind"] == "retire-modified"
    assert action["subject"] == "scripts/verify"
    assert action["blocking"] is True
    assert "scripts/test-pr-policy (removed)" in str(action["message"])
    assert "target was not changed" in str(action["message"])
    assert action["kind"] in lifecycle_report.REQUIRED_ACTION_KINDS

    with pytest.raises(cli.CliError) as error:
        cli.reject_retained_uses({"required_actions": [action]})
    assert "scripts/test-pr-policy" in str(error.value)
    cli.reject_retained_uses({"required_actions": [plain]})


def test_finalize_rejects_a_kept_script_that_reads_a_moved_file() -> None:
    """AC1: keep-current script content may not use an unshimmed move."""
    script = LEGACY_VERIFY.replace("./scripts/test-pr-policy\n", "").encode()
    with pytest.raises(cli.CliError) as error:
        cli.reject_decided_uses(
            {"scripts/check": script}, (), ("policies/repository.json",)
        )
    assert "scripts/check uses policies/repository.json" in str(error.value)
    # A workflow or other non-script content is judged by removals only.
    cli.reject_decided_uses(
        {".github/workflows/ci.yml": b"run: cat policies/repository.json\n"},
        (),
        ("policies/repository.json",),
    )


@pytest.mark.large
def test_kept_legacy_verify_calling_a_removed_script_blocks_the_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC1/R1: a kept ``scripts/verify`` never loses ``test-pr-policy``.

    The old template rendered both scripts; the product changed
    ``scripts/verify`` so it is kept as ``retire-modified``, while the new
    template drops ``scripts/test-pr-policy``. ``--check`` blocks on the
    kept script and ``--finalize-plan`` writes no plan.
    """
    probe, _sha = make_template(tmp_path / "probe")
    verify = (probe / "template/scripts/verify").read_text(encoding="utf-8")
    legacy_verify = verify + "bash scripts/test-pr-policy\n"
    project, source = legacy_consumer(
        tmp_path,
        {
            "scripts/verify": legacy_verify,
            "scripts/test-pr-policy": "#!/usr/bin/env bash\ntrue\n",
        },
    )
    write_executable(
        project / "scripts/verify", legacy_verify + "echo product step\n"
    )
    commit(project, "test: product changes verify")
    template = source / "template"
    (template / "scripts/verify").unlink()
    (template / "scripts/test-pr-policy").unlink()
    new_sha = commit(source, "test: drop legacy verify scripts")
    reports = tmp_path / "reports"
    capsys.readouterr()

    assert (
        update(project, new_sha, "--check", "--report-dir", str(reports)) == 1
    ), capsys.readouterr().err
    report = read_json(reports / "csarc-update-report.json")
    [kept] = [
        row
        for row in report["required_actions"]
        if row["kind"] == "retire-modified"
    ]
    assert kept["subject"] == "scripts/verify"
    assert kept["blocking"] is True
    assert "scripts/test-pr-policy (removed)" in kept["message"]
    assert report["status"] == "blocked"
    capsys.readouterr()
    assert (
        update(
            project, new_sha, "--finalize-plan", "--report-dir", str(reports)
        )
        != 0
    )
    assert "scripts/test-pr-policy" in capsys.readouterr().err
    assert not (reports / final_plan.FINAL_PLAN_BASENAME).exists()
    assert (project / "scripts/test-pr-policy").is_file()


# --- AC2: a retired reviewer list asks the owner to confirm ---------------


def test_retired_reviewers_note_explains_new_behavior_and_restore() -> None:
    """AC2/R2: the row stays retired and explains the change."""
    classes = governance_migration.setting_classes(
        {"reviewers": "@reviewer-one"}, {}
    )
    setting_class, note = classes["reviewers"]
    assert setting_class == "retired"
    assert note is not None
    assert "`.github/REVIEWERS` (`@reviewer-one`)" in note
    assert "maintain or admin permission" in note
    assert "csarc update --data code_owner=<owners>" in note
    assert "[[reviewers]]" in note


@pytest.mark.parametrize(
    ("files", "settings"),
    [
        (
            EMPTY_PLAN,
            [
                {
                    "key": "reviewers",
                    "before": "@reviewer-one",
                    "after": None,
                    "class": "retired",
                    "source": "derived",
                    "note": None,
                }
            ],
        ),
        (
            cli.Plan((), (), (), (), (), (), (), delete=(".github/REVIEWERS",)),
            [],
        ),
    ],
)
def test_retired_reviewers_add_an_owner_confirmation_row(
    files: cli.Plan, settings: list[dict[str, object]]
) -> None:
    """AC2/R2: the key or the file retiring adds one confirmation row."""
    [action] = cli.update_required_actions(files, settings)
    assert action["kind"] == "setting-decision"
    assert action["subject"] == "reviewers"
    assert action["blocking"] is False
    message = str(action["message"])
    assert "owner must confirm" in message
    assert "requests one collaborator with maintain or admin" in message
    assert "csarc update --data code_owner=<owners>" in message
    assert action["kind"] in lifecycle_report.REQUIRED_ACTION_KINDS


def test_no_reviewer_change_adds_no_confirmation_row() -> None:
    """AC2: nothing is asked when the reviewer setup does not change."""
    unchanged = [
        {
            "key": "code_owner",
            "before": "@owner",
            "after": "@owner",
            "class": "unchanged",
            "source": "saved",
            "note": None,
        }
    ]
    assert cli.update_required_actions(EMPTY_PLAN, unchanged) == []


# --- AC3: status hints the documented flags -------------------------------


def _flags(text: str) -> list[str]:
    """Return the ``--flag`` tokens of one command, ignoring the prose."""
    command = text.split(" (", 1)[0].split(" to preview", 1)[0]
    return re.findall(r"(?<!\S)--[a-z][a-z-]*", command)


@pytest.mark.parametrize("guide", ["docs/install.md", "docs/install.en.md"])
def test_status_next_command_uses_the_install_guide_flags(guide: str) -> None:
    """AC3: every stage of the hint carries the guide's flags."""
    text = (ROOT / guide).read_text(encoding="utf-8")
    block = next(
        part
        for part in text.split("```")
        if "csarc status . --to <tag>" in part
    )
    documented = {
        stage: _flags(line)
        for line in block.splitlines()
        if line.startswith("csarc update .")
        for stage in ("--check", "--finalize-plan", "--apply-plan")
        if stage in line.split()
    }
    hint = cli.update_next_command(
        {"target_version": "v1.2.3", "target_sha": "a" * 40}
    )
    hinted = {
        stage: _flags(part)
        for part in hint.split("; then ")
        for stage in ("--check", "--finalize-plan", "--apply-plan")
        if stage in part.split()
    }
    assert (
        set(documented)
        == set(hinted)
        == {
            "--check",
            "--finalize-plan",
            "--apply-plan",
        }
    )
    for stage, flags in documented.items():
        assert sorted(hinted[stage]) == sorted(flags), stage
    static = cli.INSTALL_STATE_NEXT_COMMAND[cli.INSTALL_STATE_UPDATE]
    assert "--check --json" in static
    assert static.endswith("--yes")
