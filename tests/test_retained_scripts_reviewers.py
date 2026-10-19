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
from test_cli import commit, git, make_template, write_executable
from test_operator_run_regressions import (
    legacy_consumer,
    main,
    read_json,
    update,
    write,
)

from csarc_cli import (
    cli,
    file_transition,
    final_plan,
    governance_migration,
    lifecycle_report,
)

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


def test_a_path_under_a_shell_root_variable_is_a_use() -> None:
    """AC1: ``$repo_root/scripts/x`` runs ``scripts/x`` like ``./scripts/x``."""
    for line in (
        b'validator="$repo_root/scripts/validate-pr-policy"\n',
        b'"${ROOT}/scripts/validate-pr-policy" --check\n',
    ):
        assert file_transition.content_uses(
            "scripts/test-pr-policy", line, ["scripts/validate-pr-policy"]
        ) == ("scripts/validate-pr-policy",)
    for line in (
        b'"$repo_root/.csarc/scripts/validate-pr-policy"\n',
        b'"$repo_root/scripts/validate-pr-policy-v2"\n',
    ):
        assert (
            file_transition.content_uses(
                "scripts/test-pr-policy", line, ["scripts/validate-pr-policy"]
            )
            == ()
        )


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
def test_kept_legacy_verify_blocks_until_retired_by_decision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC1/R1: a kept ``scripts/verify`` never loses ``test-pr-policy``.

    The old template rendered both scripts; the product changed
    ``scripts/verify`` so it is kept as ``retire-modified``, while the new
    template drops ``scripts/test-pr-policy`` and verifies from
    ``.csarc/scripts/verify``. ``--check`` blocks on the kept script and
    ``--finalize-plan`` without a decision writes no plan. A
    ``--decision scripts/verify=take-new`` retires it as the new release
    does, so the update applies with no product commit.
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
    write_executable(template / ".csarc/scripts/verify", verify)
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
    # keep-current is not a retirement; only take-new clears the block.
    assert (
        update(
            project,
            new_sha,
            "--finalize-plan",
            "--report-dir",
            str(reports),
            "--decision",
            "scripts/verify=keep-current",
        )
        != 0
    )
    assert not (reports / final_plan.FINAL_PLAN_BASENAME).exists()
    capsys.readouterr()

    assert (
        update(
            project,
            new_sha,
            "--finalize-plan",
            "--report-dir",
            str(reports),
            "--decision",
            "scripts/verify=take-new",
        )
        == 0
    ), capsys.readouterr().err
    # The terminal summary follows the decision (Issue #1164).
    summary = capsys.readouterr().out
    assert "Retained modified files (0):" in summary
    assert re.search(
        r"^Remove \(\d+\):\n(?:  .*\n)*  scripts/verify$", summary, re.M
    )
    final = read_json(reports / "csarc-update-report.json")
    assert final["status"] != "blocked"
    [row] = [r for r in final["files"] if r["path"] == "scripts/verify"]
    assert (row["reason"], row["decision"]) == ("retire-modified", "take-new")
    assert not [
        r for r in final["required_actions"] if r["kind"] == "retire-modified"
    ]
    head = git_head(project)
    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(reports / final_plan.FINAL_PLAN_BASENAME),
                "--yes",
            ]
        )
        == 0
    ), capsys.readouterr().err
    assert git_head(project) == head
    assert not (project / "scripts/verify").exists()
    assert not (project / "scripts/test-pr-policy").exists()
    assert (project / ".csarc/scripts/verify").is_file()


def git_head(project: Path) -> str:
    """Return the target's HEAD: the update writes no product commit."""
    return git(project, "rev-parse", "HEAD")


def test_finalize_refuses_to_retire_a_file_something_kept_uses(
    tmp_path: Path,
) -> None:
    """AC1/R1: retiring the kept script must not break another kept file."""
    write_executable(tmp_path / "scripts/verify", LEGACY_VERIFY)
    write(
        tmp_path / ".github/workflows/product-ci.yml",
        "jobs:\n  ci:\n    steps:\n      - run: ./scripts/verify\n",
    )
    files = cli.Plan(
        (),
        (),
        (),
        (".github/workflows/product-ci.yml",),
        (),
        (),
        (),
        retained=("scripts/verify",),
    )
    with pytest.raises(cli.CliError) as error:
        cli.reject_retired_uses(tmp_path, files, ("scripts/verify",), {})
    assert ".github/workflows/product-ci.yml uses scripts/verify" in str(
        error.value
    )
    # Decided content that no longer calls it, or nothing retired, passes.
    cli.reject_retired_uses(
        tmp_path,
        files,
        (),
        {},
    )
    with pytest.raises(cli.CliError):
        cli.reject_retired_uses(
            tmp_path,
            cli.Plan((), (), (), (), (), (), (), retained=("scripts/verify",)),
            ("scripts/verify",),
            {"ci.yml": b"run: ./scripts/verify\n"},
        )


def test_only_take_new_retires_a_kept_file() -> None:
    """AC1: a retire-modified path takes take-new; conflicts stay apart."""
    choices = {
        "scripts/verify": ("take-new", None),
        "docs/README.md": ("keep-current", None),
    }
    conflicts, retired = cli.split_retirement_decisions(
        choices, ("scripts/verify",)
    )
    assert retired == ("scripts/verify",)
    assert conflicts == {"docs/README.md": ("keep-current", None)}
    with pytest.raises(cli.CliError) as error:
        cli.split_retirement_decisions(
            {"scripts/verify": ("keep-current", None)}, ("scripts/verify",)
        )
    assert "take-new" in str(error.value)


def test_finalize_summary_lists_a_take_new_retirement_as_removed(
    tmp_path: Path,
) -> None:
    """Issue #1164 AC1/R1: the summary follows the retirement decision."""
    files = cli.Plan(
        (),
        (),
        ("scripts/old",),
        (),
        (),
        ("docs/README.md",),
        (),
        retained=("scripts/test", "scripts/verify"),
    )
    plan = cli.ResolvedPlan(
        mode="update",
        target=tmp_path,
        revision=cli.Revision("v1.0.0", "b" * 40, "https://example.invalid"),
        repository=cli.RepositoryContext(
            None, None, None, "private", "none", False
        ),
        answers={},
        capabilities={},
        files=files,
    )
    decided = cli.decided_summary_plan(
        plan,
        ["scripts/verify=take-new", "docs/README.md=take-new"],
    )
    assert decided.files is not None
    assert decided.files.retained == ("scripts/test",)
    assert decided.files.remove == ("scripts/old", "scripts/verify")
    # A conflict decision does not move the manual merge entry.
    assert decided.files.manual == ("docs/README.md",)
    # No decision, keep-current, or an invalid value leaves it unchanged.
    for values in ([], ["scripts/verify=keep-current"], ["bad"]):
        assert cli.decided_summary_plan(plan, values) is plan


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
