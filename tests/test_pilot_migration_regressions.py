"""Pilot-proven migration regressions (Issue #1083).

The beta.2 pilot updated two existing consumers: one legacy-answers
consumer whose only Release writer was rendered by the old template, and
one `.csarc` consumer with customized generated scripts. Each test below
models one shape the pilot hit; no consumer identity is recorded here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import settings_support
import yaml
from test_action_pin_preflight import commit_all, drift_fixture, git_runner
from test_cli import commit, git, make_template, write_executable

from csarc_cli import action_pin_preflight as pins
from csarc_cli import cli, final_plan
from csarc_cli.cli import main as cli_main

OLD_PIN = "1" * 40
NEW_PIN = "2" * 40
RELEASE_PIN = "3" * 40
RELEASE_WORKFLOW = ".github/workflows/release-please.yml"
LEGACY_WORKFLOW = ".github/workflows/legacy-tool.yml"


def main(arguments: list[str]) -> int:
    """Run the CLI with the explicit setup seeds a script passes (#1078)."""
    return cli_main(settings_support.seeded_setup(arguments))


def write(path: Path, content: str) -> None:
    """Write one fixture file, creating its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def setup_workflow(pin: str) -> str:
    """Return a workflow that pins astral-sh/setup-uv at ``pin``."""
    return (
        "on: push\njobs:\n  job:\n    runs-on: ubuntu-latest\n    steps:\n"
        f"      - uses: astral-sh/setup-uv@{pin} # v1\n"
    )


# --- Small contracts --------------------------------------------------------


def test_retained_legacy_sources_never_move() -> None:
    """R1: a kept, customized legacy file is not a layout move source."""
    moves = (
        ("scripts/verify", ".csarc/scripts/verify"),
        ("scripts/scan-secrets", ".csarc/scripts/scan-secrets"),
    )
    assert cli.effective_layout_moves(moves, {"scripts/verify"}) == (
        ("scripts/scan-secrets", ".csarc/scripts/scan-secrets"),
    )
    assert cli.effective_layout_moves(moves, ()) == moves


def test_only_a_product_owned_release_workflow_is_protected() -> None:
    """R3: the selected writer is protected only under product ownership."""
    selected = {
        "release_ownership": "product-owned",
        "release_workflow": RELEASE_WORKFLOW,
    }
    assert cli.product_release_workflow(selected) == (RELEASE_WORKFLOW,)
    for ownership in ("csarc-owned", "verification-only"):
        assert (
            cli.product_release_workflow(
                {**selected, "release_ownership": ownership}
            )
            == ()
        )
    assert (
        cli.product_release_workflow({**selected, "release_workflow": ""}) == ()
    )


def test_preflight_ignores_workflows_the_update_retires() -> None:
    """R2: a retired legacy workflow never asks for a product pin commit."""
    retired = pins.PinDrift(
        LEGACY_WORKFLOW, 6, "astral-sh/setup-uv", OLD_PIN, NEW_PIN, "x"
    )
    product = pins.PinDrift(
        ".github/workflows/product.yml",
        6,
        "astral-sh/setup-uv",
        OLD_PIN,
        NEW_PIN,
        "x",
    )
    preflight = pins.PinPreflight(
        "a" * 40,
        (LEGACY_WORKFLOW, ".github/workflows/product.yml"),
        (retired, product),
    )
    remaining = pins.excluding(preflight, (LEGACY_WORKFLOW, "zizmor.yml"))
    assert remaining.items == (product,)
    assert remaining.product_workflows == (".github/workflows/product.yml",)
    assert pins.excluding(remaining, ()) == remaining


def test_pin_commit_may_refresh_the_release_tag_comment(
    tmp_path: Path,
) -> None:
    """R4: the readable tag after a pin moves with its SHA (#1065 AC4)."""
    target, items = drift_fixture(tmp_path)
    path = target / ".github/workflows/product.yml"
    text = path.read_text(encoding="utf-8")
    for item in items:
        text = text.replace(
            f"{item['action']}@{item['old_sha']} # v1",
            f"{item['action']}@{item['new_sha']} # v9",
        )
    path.write_text(text, encoding="utf-8")
    commit = commit_all(target, "fix: pins with refreshed release tags")

    assert pins.unlisted_pin_changes(items, git_runner, target, commit) == []


def test_ignored_rendered_files_stop_the_update(tmp_path: Path) -> None:
    """R5: a product ignore rule never silently drops a rendered file.

    The legacy consumer ignored every ``data/`` directory, which hid the
    rendered ``.csarc/site/data/glossary.toml``: the candidate verified
    with it, the target never received it, and the next update failed.
    """
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    git(candidate, "init", "-b", "main")
    write(candidate / ".gitignore", "data/\n")
    write(candidate / "data/tracked.txt", "product\n")
    git(candidate, "add", "--force", ".gitignore", "data/tracked.txt")
    glossary = ".csarc/site/data/glossary.toml"
    write(candidate / glossary, 'title = "Glossary"\n')
    payload = (glossary, "data/tracked.txt", "missing.txt")

    with pytest.raises(cli.CliError) as error:
        cli.reject_ignored_payload(candidate, payload)
    assert f"{glossary} (.gitignore:1: data/)" in str(error.value)
    assert "data/tracked.txt" not in str(error.value)
    assert "target was not changed" in str(error.value)

    # The plan still lists the hidden file while a .gitignore conflict is
    # undecided, so the decided apply is compared with the same additions.
    cli.stage_payload(candidate, payload)
    staged = git(candidate, "diff", "--cached", "--name-only")
    assert glossary in staged.splitlines()
    git(candidate, "rm", "--cached", "--quiet", glossary)

    write(candidate / ".gitignore", "data/\n!/.csarc/site/data/\n")
    cli.reject_ignored_payload(candidate, payload)
    cli.reject_ignored_payload(candidate, ())


# --- One consumer-shaped check -> decide -> apply ---------------------------


def legacy_consumer(tmp_path: Path) -> tuple[Path, Path, str]:
    """Return a legacy existing-mode consumer and the next template SHA.

    The first template renders a legacy root ``scripts/verify``, a CSARC
    workflow pinning setup-uv, and a release-please workflow. The consumer
    keeps legacy answers without a release owner, customizes
    ``scripts/verify`` and ``managed.txt``, and its only Release writer is
    the generated release-please workflow. The next template moves the
    verifier under ``.csarc/``, drops both workflows, and bumps the pin.
    """
    source, _first = make_template(tmp_path)
    template = source / "template"
    write(template / LEGACY_WORKFLOW, setup_workflow(OLD_PIN))
    write(template / ".github/workflows/ci.yml", setup_workflow(OLD_PIN))
    write(
        template / RELEASE_WORKFLOW,
        "on: push\njobs:\n  release:\n    runs-on: ubuntu-latest\n"
        "    steps:\n"
        f"      - uses: googleapis/release-please-action@{RELEASE_PIN}"
        " # v5\n",
    )
    old_sha = commit(source, "test: legacy generated layout")
    project = tmp_path / "consumer"
    assert (
        main(
            [
                "init",
                "--data",
                "repository_url=https://github.com/example-org/consumer",
                str(project),
                "--source",
                str(source),
                "--to",
                old_sha,
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
                "--data",
                "language=ci",
            ]
        )
        == 0
    )
    answers_path = project / ".copier-answers.yml"
    answers = yaml.safe_load(answers_path.read_text(encoding="utf-8"))
    answers = {
        key: value
        for key, value in answers.items()
        if not key.startswith("release_")
    }
    answers["project_mode"] = "existing"
    answers_path.write_text(
        yaml.safe_dump(answers, sort_keys=True), encoding="utf-8"
    )
    verify = project / "scripts/verify"
    verify.write_text(
        verify.read_text(encoding="utf-8") + "# product check\n",
        encoding="utf-8",
    )
    write(project / "managed.txt", "product version one\n")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: legacy consumer")

    generated = template / ".csarc/scripts"
    generated.mkdir(parents=True)
    (template / "scripts/verify").replace(generated / "verify")
    (template / LEGACY_WORKFLOW).unlink()
    (template / RELEASE_WORKFLOW).unlink()
    write(template / ".github/workflows/ci.yml", setup_workflow(NEW_PIN))
    write(template / "managed.txt", "template version two\n")
    write_executable(
        generated / "verify",
        (generated / "verify").read_text(encoding="utf-8"),
    )
    new_sha = commit(source, "test: consolidated layout")
    return project, source, new_sha


def update(project: Path, revision: str, *extra: str) -> int:
    """Run one ``csarc update`` against the fixture revision."""
    return main(
        ["update", str(project), "--to", revision, "--allow-unreleased", *extra]
    )


def changed_paths(project: Path) -> dict[str, set[str]]:
    """Return the working-tree effects of the apply against HEAD."""
    git(project, "add", "-A")
    output = git(project, "diff", "--cached", "--no-renames", "--name-status")
    git(project, "reset", "-q")
    effects: dict[str, set[str]] = {"A": set(), "M": set(), "D": set()}
    for line in output.splitlines():
        status, _tab, path = line.partition("\t")
        effects[status[0]].add(path)
    return effects


@pytest.mark.large
def test_legacy_consumer_update_applies_its_final_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """R1-R3 through one real update shaped like the pilot consumers.

    Before #1083 the plan retired the selected product Release writer,
    asked for a product pin commit in workflows it was about to retire,
    and the apply stopped on a layout collision for the customized
    verifier the same plan promised to keep.
    """
    project, _source, new_sha = legacy_consumer(tmp_path)
    report_dir = project.parent / f"{project.name}-csarc-update-report"
    release_before = (project / RELEASE_WORKFLOW).read_bytes()
    verify_before = (project / "scripts/verify").read_bytes()
    capsys.readouterr()

    assert update(project, new_sha, "--check") == 1
    stage1: dict[str, Any] = json.loads(
        (report_dir / "csarc-update-plan.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (report_dir / "csarc-update-report.json").read_text(encoding="utf-8")
    )
    release = report["product"]["release_ownership"]
    assert release["ownership"] == "product-owned"
    assert release["selected_workflow"] == RELEASE_WORKFLOW
    preflight = stage1["action_pin_preflight"]
    assert preflight["items"] == []
    assert LEGACY_WORKFLOW not in preflight["product_workflows"]
    planning = stage1["planning"]
    assert planning["conflicts"] == ["managed.txt"]
    assert "scripts/verify" in planning["retained"]
    assert RELEASE_WORKFLOW in planning["product_owned"]
    assert RELEASE_WORKFLOW not in planning["retained"]
    files = stage1["files"]
    assert LEGACY_WORKFLOW in files["remove"]
    assert RELEASE_WORKFLOW not in files["remove"]
    assert "scripts/verify -> .csarc/scripts/verify" not in files["move"]
    assert ".csarc/scripts/verify" in files["add"]
    rows = {
        (row["path"], row["action"], row["reason"]) for row in report["files"]
    }
    assert (RELEASE_WORKFLOW, "preserve", "product-owned") in rows
    assert ("scripts/verify", "conflict", "retire-modified") in rows
    assert not any(
        action["kind"] == "action-pin" for action in report["required_actions"]
    )

    assert (
        update(
            project,
            new_sha,
            "--finalize-plan",
            "--decision",
            "managed.txt=keep-current",
        )
        == 0
    )
    plan_path = report_dir / final_plan.FINAL_PLAN_BASENAME
    sealed: dict[str, Any] = final_plan.load(plan_path)
    approved = sealed["derived"]["transitions"]
    capsys.readouterr()

    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    ), capsys.readouterr().err
    assert (project / RELEASE_WORKFLOW).read_bytes() == release_before
    assert (project / "scripts/verify").read_bytes() == verify_before
    assert (project / ".csarc/scripts/verify").is_file()
    assert not (project / LEGACY_WORKFLOW).exists()
    assert (project / "managed.txt").read_text(encoding="utf-8") == (
        "product version one\n"
    )
    effects = changed_paths(project)
    metadata = set(approved["optional"])
    assert effects["D"] - metadata == set(approved["delete"])
    assert effects["A"] - metadata == set(approved["create"])
    assert effects["M"] - metadata == set(approved["modify"])

    # R6: the kept legacy verifier beside its migrated destination is not a
    # second layout move, so the next check of the same release plans
    # without a collision, conflict, or move.
    commit(project, "chore: apply the reviewed update")
    capsys.readouterr()
    assert update(project, new_sha, "--check") in {0, 1}, (
        capsys.readouterr().err
    )
    again: dict[str, Any] = json.loads(
        (report_dir / "csarc-update-plan.json").read_text(encoding="utf-8")
    )
    assert again["files"]["move"] == []
    assert again["planning"]["conflicts"] == []
    assert "scripts/verify" in again["files"]["preserve"]
    assert (project / "scripts/verify").read_bytes() == verify_before
