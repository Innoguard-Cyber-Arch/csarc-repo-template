"""Operator-run update defects (Issue #1146).

An operator who never worked on Milestone 18 updated two existing consumers
with only the public documentation. Each test below models one defect that
run hit; no consumer identity is recorded here.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import settings_support
import yaml
from test_cli import commit, git, make_template, write_executable

from csarc_cli import cli, file_transition, final_plan
from csarc_cli.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
RELEASE_PIN = "3" * 40
LEGACY_RELEASE = ".github/workflows/release-please.yml"
CSARC_RELEASE = ".github/workflows/release.yml"
PRODUCT_WORKFLOW = ".github/workflows/product-ci.yml"
ZIZMOR_JOB = (
    "on: pull_request\njobs:\n  audit:\n    runs-on: ubuntu-latest\n"
    "    steps:\n      - run: uvx --from zizmor==1.29.0 zizmor . "
    "--format plain\n"
)


def main(arguments: list[str]) -> int:
    """Run the CLI with the explicit setup seeds a script passes (#1078)."""
    return cli_main(settings_support.seeded_setup(arguments))


def write(path: Path, content: str) -> None:
    """Write one fixture file, creating its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def legacy_consumer(
    tmp_path: Path, old_files: dict[str, str]
) -> tuple[Path, Path]:
    """Return a legacy existing-mode consumer and its template source.

    The old template adds ``old_files``; the consumer keeps legacy answers
    without a release owner, like the operator-run consumers.
    """
    source, _first = make_template(tmp_path)
    template = source / "template"
    for name, content in old_files.items():
        write(template / name, content)
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
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: legacy consumer")
    return project, source


def update(project: Path, revision: str, *extra: str) -> int:
    """Run one ``csarc update`` against the fixture revision."""
    return main(
        ["update", str(project), "--to", revision, "--allow-unreleased", *extra]
    )


def read_json(path: Path) -> dict[str, Any]:
    """Read one JSON report artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


# --- AC1: confirming the derived release owner ------------------------------


@pytest.mark.large
def test_confirming_the_derived_release_owner_plans_identically(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC1: ``--data release_ownership=csarc-owned`` equals leaving it out.

    The legacy consumer's only Release writer is the old template's own
    release-please workflow, so the update derives ``csarc-owned`` and moves
    the release to the CSARC writer. Confirming that value explicitly used
    to select the legacy writer itself and retire both workflows.
    """
    writer = (
        "on: push\njobs:\n  release:\n    runs-on: ubuntu-latest\n"
        "    steps:\n"
        f"      - uses: googleapis/release-please-action@{RELEASE_PIN}\n"
    )
    project, source = legacy_consumer(tmp_path, {LEGACY_RELEASE: writer})
    template = source / "template"
    (template / LEGACY_RELEASE).unlink()
    write(
        template / CSARC_RELEASE,
        "on: workflow_dispatch\njobs:\n  publish:\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: 'true'\n",
    )
    new_sha = commit(source, "test: CSARC release writer")

    def plans(name: str, *extra: str) -> tuple[dict[str, Any], ...]:
        reports = tmp_path / name
        capsys.readouterr()
        assert (
            update(
                project,
                new_sha,
                "--check",
                "--report-dir",
                str(reports),
                *extra,
            )
            == 1
        ), capsys.readouterr().err
        assert (
            update(
                project,
                new_sha,
                "--finalize-plan",
                "--report-dir",
                str(reports),
                *extra,
            )
            == 0
        ), capsys.readouterr().err
        return (
            read_json(reports / "csarc-update-plan.json"),
            read_json(reports / "csarc-update-report.json"),
            final_plan.load(reports / final_plan.FINAL_PLAN_BASENAME),
        )

    implicit = plans("implicit")
    explicit = plans("explicit", "--data", "release_ownership=csarc-owned")

    for stage1, report, _sealed in (implicit, explicit):
        ownership = report["product"]["release_ownership"]
        assert ownership["ownership"] == "csarc-owned"
        assert ownership["selected_workflow"] == CSARC_RELEASE
        assert LEGACY_RELEASE in stage1["files"]["remove"]
        assert CSARC_RELEASE not in stage1["files"]["remove"]
    assert implicit[0]["files"] == explicit[0]["files"]
    assert {
        (row["path"], row["action"], row["reason"])
        for row in implicit[1]["files"]
    } == {
        (row["path"], row["action"], row["reason"])
        for row in explicit[1]["files"]
    }
    for key in ("retiring", "transitions"):
        assert implicit[2]["derived"][key] == explicit[2]["derived"][key]


def test_explicit_owner_never_hides_the_derived_release_owner(
    tmp_path: Path,
) -> None:
    """AC1: the migration reads the owner the evidence derives."""
    target = tmp_path / "consumer"
    write(
        target / LEGACY_RELEASE,
        f"jobs:\n  r:\n    steps:\n      - uses: "
        f"googleapis/release-please-action@{RELEASE_PIN}\n",
    )
    candidate = {"project_mode": "existing", "release_ownership": "csarc-owned"}

    derived = cli.implicit_release_owner(
        target, candidate, {}, {"release_ownership": "csarc-owned"}
    )
    assert derived is not None
    assert derived["release_ownership"] == "product-owned"
    assert derived["release_workflow"] == LEGACY_RELEASE
    # A saved owner is the user's own choice and stays authoritative.
    saved = cli.implicit_release_owner(
        target,
        candidate,
        {"release_ownership": "csarc-owned"},
        {"release_ownership": "csarc-owned"},
    )
    assert saved is not None
    assert saved["release_ownership"] == "csarc-owned"


# --- AC2: a removal a kept file still uses ----------------------------------


def test_a_tool_run_or_a_path_token_uses_a_removed_file() -> None:
    """AC2: discovery-based configuration and named paths both count."""
    assert file_transition.content_uses(
        PRODUCT_WORKFLOW, ZIZMOR_JOB.encode(), ["zizmor.yml"]
    ) == ("zizmor.yml",)
    action = b"steps:\n  - uses: zizmorcore/zizmor-action@abc\n"
    assert file_transition.content_uses("ci.yml", action, ["zizmor.yml"]) == (
        "zizmor.yml",
    )
    named = b"run: ./scripts/check --config scripts/rules.json\n"
    assert file_transition.content_uses(
        "ci.yml", named, ["scripts/check", "scripts/rules.json", "other"]
    ) == ("scripts/check", "scripts/rules.json")
    # Another path that merely ends the same way, a comment, prose, and
    # binary content never keep a file alive.
    moved = b"run: ./.csarc/scripts/check\n"
    assert (
        file_transition.content_uses("ci.yml", moved, ["scripts/check"]) == ()
    )
    comment = b"# zizmor flags this trigger\nrun: echo ok\n"
    assert file_transition.content_uses("ci.yml", comment, ["zizmor.yml"]) == ()
    prose = b"Run zizmor with zizmor.yml.\n"
    assert (
        file_transition.content_uses("README.md", prose, ["zizmor.yml"]) == ()
    )
    assert (
        file_transition.content_uses("x.bin", b"\xff zizmor", ["zizmor.yml"])
        == ()
    )


def test_referenced_retirements_lists_only_present_used_files(
    tmp_path: Path,
) -> None:
    """AC2: only an existing candidate that a kept file uses is returned."""
    write(tmp_path / "zizmor.yml", "rules: {}\n")
    write(tmp_path / ".gitleaks.toml", "title = 'x'\n")
    write(tmp_path / PRODUCT_WORKFLOW, ZIZMOR_JOB)
    candidates = ("zizmor.yml", ".gitleaks.toml", ".pre-commit-config.yaml")

    assert file_transition.referenced_retirements(
        tmp_path, candidates, (PRODUCT_WORKFLOW,)
    ) == ("zizmor.yml",)
    assert (
        file_transition.referenced_retirements(tmp_path, candidates, ()) == ()
    )


def test_finalize_rejects_a_decision_that_keeps_a_use() -> None:
    """AC2: keep-current content may not use a file the plan removes."""
    with pytest.raises(cli.CliError) as error:
        cli.reject_decided_uses(
            {".github/workflows/ci.yml": ZIZMOR_JOB.encode(), "gone": None},
            ("zizmor.yml",),
        )
    assert ".github/workflows/ci.yml uses zizmor.yml" in str(error.value)
    assert "target was not changed" in str(error.value)
    cli.reject_decided_uses(
        {".github/workflows/ci.yml": b"run: echo ok\n"}, ("zizmor.yml",)
    )


@pytest.mark.large
def test_update_keeps_used_config_and_the_project_site(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC2/AC3 through one check -> finalize -> apply.

    The old template rendered ``zizmor.yml`` and the repo-site page at
    ``site/content/``; the new one drops the ignore file and seeds a newer
    page under ``docs/site/content/``. A product workflow runs zizmor, so
    the ignore file stays; the project's page moves byte for byte.
    """
    page_v1 = "# Project page\n\nOur own words.\n"
    project, source = legacy_consumer(
        tmp_path,
        {
            "zizmor.yml": "rules:\n  dangerous-triggers:\n    ignore: []\n",
            "site/content/_index.en.md": page_v1,
        },
    )
    write(project / PRODUCT_WORKFLOW, ZIZMOR_JOB)
    commit(project, "test: product workflow audit")
    template = source / "template"
    (template / "zizmor.yml").unlink()
    (template / "site/content/_index.en.md").unlink()
    write(
        template / "docs/site/content/_index.en.md",
        "# Starter page\n\nA newer seed.\n",
    )
    new_sha = commit(source, "test: new site layout")
    reports = tmp_path / "reports"
    capsys.readouterr()

    assert update(
        project, new_sha, "--check", "--report-dir", str(reports)
    ) in {0, 1}, capsys.readouterr().err
    stage1 = read_json(reports / "csarc-update-plan.json")
    files = stage1["files"]
    assert "zizmor.yml" in files["product_owned"]
    assert "zizmor.yml" not in files["remove"]
    assert "zizmor.yml" not in files["delete"]
    assert (
        "site/content/_index.en.md -> docs/site/content/_index.en.md"
        in files["move"]
    )

    assert (
        update(
            project, new_sha, "--finalize-plan", "--report-dir", str(reports)
        )
        == 0
    ), capsys.readouterr().err
    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(reports / final_plan.FINAL_PLAN_BASENAME),
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    ), capsys.readouterr().err
    assert (project / "zizmor.yml").is_file()
    assert not (project / "site/content/_index.en.md").exists()
    assert (project / "docs/site/content/_index.en.md").read_text(
        encoding="utf-8"
    ) == page_v1


# --- AC3: project-owned site content ----------------------------------------


def test_project_site_content_survives_seed_and_layout_move(
    tmp_path: Path,
) -> None:
    """AC3: site pages, navigation, and theme keep the project's bytes."""
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    write(baseline / "site/content/_index.en.md", "ours\n")
    write(baseline / "docs/site/data/navigation.json", '{"items": ["ours"]}\n')
    # Copier's view: the legacy page is gone and both seeds were written.
    write(candidate / "docs/site/content/_index.en.md", "seed\n")
    write(candidate / "docs/site/data/navigation.json", '{"items": []}\n')

    def restore(names: Sequence[str]) -> None:
        for name in names:
            write(candidate / name, (baseline / name).read_text("utf-8"))

    moves = (("site/content/_index.en.md", "docs/site/content/_index.en.md"),)
    baseline_files = (
        "site/content/_index.en.md",
        "docs/site/data/navigation.json",
    )
    assert file_transition.project_owned_state(baseline_files, moves) == (
        ".csarc/release-please-manifest.json",
        ".csarc/version.txt",
        "CHANGELOG.md",
        "docs/site/content/_index.en.md",
        "docs/site/data/navigation.json",
        "docs/site/theme.css",
    )
    protected, completed = file_transition.protect_product_state(
        candidate, baseline_files, moves, restore
    )

    assert protected == (
        "docs/site/content/_index.en.md",
        "docs/site/data/navigation.json",
    )
    assert completed == moves
    assert (candidate / "docs/site/content/_index.en.md").read_text(
        encoding="utf-8"
    ) == "ours\n"
    assert not (candidate / "site/content/_index.en.md").exists()
    assert (candidate / "docs/site/data/navigation.json").read_text(
        encoding="utf-8"
    ) == '{"items": ["ours"]}\n'


def test_site_documentation_matches_the_update_behavior() -> None:
    """AC3: the root and generated READMEs promise what update does."""
    generated = (ROOT / "template/.csarc/site/README.md").read_text("utf-8")
    assert "a later `csarc update` never overwrites them" in generated
    assert "moves them here unchanged and lists each move" in generated
    zh = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "由 layout migration 原封不動搬到新位置" in zh
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    assert "byte for byte to the new paths" in en
    for text in (generated, zh, en):
        assert "Copier 更新版型時不會覆寫" not in text


# --- AC4: ignore rules that hide rendered files -----------------------------


def ignore_target(tmp_path: Path) -> Path:
    """Return a Git target whose product ignore rule hides ``data/``."""
    target = tmp_path / "target"
    target.mkdir()
    git(target, "init", "-b", "main")
    write(target / ".gitignore", "build/\ndata/\n")
    write(target / "data/tracked.txt", "product\n")
    git(target, "add", "--force", ".gitignore", "data/tracked.txt")
    return target


def test_check_lists_rendered_files_an_ignore_rule_hides(
    tmp_path: Path,
) -> None:
    """AC4: hidden rendered files are a blocking row before any apply."""
    target = ignore_target(tmp_path)
    payload = (
        ".csarc/site/data/glossary.toml",
        "docs/site/data/navigation.json",
        "data/tracked.txt",
        "README.md",
    )

    hidden = cli.planned_ignored_payload(target, payload)
    assert [row["path"] for row in hidden] == [
        ".csarc/site/data/glossary.toml",
        "docs/site/data/navigation.json",
    ]
    assert {row["source"] for row in hidden} == {".gitignore"}
    assert {row["pattern"] for row in hidden} == {"data/"}
    actions = cli.ignored_payload_actions(hidden)
    assert len(actions) == 1
    assert actions[0]["blocking"] is True
    assert actions[0]["kind"] == "file-conflict"
    assert actions[0]["subject"] == ".gitignore"
    assert ".gitignore:2: data/" in str(actions[0]["message"])
    rows = cli.update_required_actions(
        cli.Plan((), (), (), (), (), (), ()), (), ignored=hidden
    )
    assert actions[0] in rows
    assert cli.update_ignored_payload({"ignored_payload": hidden}) == hidden


def test_finalize_rejects_decided_ignore_rules_that_hide_files(
    tmp_path: Path,
) -> None:
    """AC4: keep-current fails at finalize; an excepted decision passes."""
    target = ignore_target(tmp_path)
    payload = (".csarc/site/data/glossary.toml",)

    with pytest.raises(cli.CliError) as error:
        cli.reject_decided_ignore_rules(target, payload, {})
    assert ".csarc/site/data/glossary.toml (.gitignore:2: data/)" in str(
        error.value
    )
    assert "target was not changed" in str(error.value)
    excepted = b"build/\ndata/\n!/.csarc/site/data/\n"
    cli.reject_decided_ignore_rules(target, payload, {".gitignore": excepted})
    cli.reject_decided_ignore_rules(target, payload, {".gitignore": None})


def memory_map_block() -> str:
    """Return the canonical verifier's Durable Project Memory checks."""
    lines = (
        (ROOT / "template/.csarc/scripts/verify.jinja")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    start = lines.index("test -f docs/adr/README.md")
    end = max(i for i, line in enumerate(lines) if '"$memory_map"' in line)
    return "\n".join(lines[start : end + 1]) + "\n"


def test_verify_reads_the_memory_map_from_a_csarc_owned_document(
    tmp_path: Path,
) -> None:
    """AC4 (owner option C): a kept product docs/README.md passes verify.

    The doc map verify checks lives in the CSARC-owned documentation
    policy that every update refreshes; the project-owned docs/README.md
    is never read, so keep-current on it no longer fails the apply.
    """
    block = memory_map_block()
    verify = (ROOT / "template/.csarc/scripts/verify.jinja").read_text(
        encoding="utf-8"
    )
    assert not [
        line
        for line in verify.splitlines()
        if "docs/README.md" in line and not line.lstrip().startswith("#")
    ]
    policy = ROOT / "template/.csarc/docs/documentation-policy.md"
    project = tmp_path / "project"
    write(project / "docs/README.md", "# Product documentation\n")
    write(project / "docs/adr/README.md", "# Decisions\n")
    write(
        project / ".csarc/docs/documentation-policy.md",
        policy.read_text(encoding="utf-8"),
    )
    script = project / "check-memory-map"
    write_executable(script, "#!/usr/bin/env bash\nset -euo pipefail\n" + block)

    assert (
        subprocess.run(  # noqa: S603
            [str(script)], cwd=project, check=False
        ).returncode
        == 0
    )
    # The check is real: a policy without the map fails it.
    write(project / ".csarc/docs/documentation-policy.md", "# Policy\n")
    assert (
        subprocess.run(  # noqa: S603
            [str(script)], cwd=project, check=False
        ).returncode
        != 0
    )


# --- AC5: the failed verify step --------------------------------------------


def test_verify_failure_names_the_failed_step(tmp_path: Path) -> None:
    """AC5: a silent check failure reports the step, not a bare failure."""
    template = (ROOT / "template/.csarc/scripts/verify.jinja").read_text(
        encoding="utf-8"
    )
    trap = next(
        line
        for line in template.splitlines()
        if line.startswith("trap ") and line.endswith(" ERR")
    )
    project = tmp_path / "project"
    write(project / "docs/README.md", "# Docs\n")
    write_executable(
        project / ".csarc/scripts/verify",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        f"{trap}\n"
        'printf "not-run\\n" >&"$_CSARC_PROJECT_VERIFICATION_STATUS_FD"\n'
        "grep -q 'Durable Project Memory' docs/README.md\n",
    )

    with pytest.raises(cli.ProjectVerificationError) as error:
        cli.verify_project(project)
    message = str(error.value)
    assert "grep -q 'Durable Project Memory' docs/README.md" in message
    assert "verify line" in message
    assert "grep -q 'Durable Project Memory'" in str(error.value.hook["reason"])


def test_verification_failure_prefers_the_first_failed_step() -> None:
    """AC5: the first FAILED line names the step; output is the fallback."""
    lines = (
        "[verify-step] START Lint; log=stdout",
        "[verify-step] FAILED Lint (2s); status=1; log=stdout",
        "[verify-step] FAILED verify line 9: verification_step Lint ruff",
    )
    assert cli.verification_failure(lines) == "Lint (2s); status=1; log=stdout"
    assert cli.verification_failure(("ok", "boom", "")) == (
        "no step reported a failure; last output: boom"
    )
    assert "printed nothing" in cli.verification_failure(())


# --- AC6: the repository settings plan message ------------------------------


def settings_target(tmp_path: Path) -> Path:
    """Return a target whose settings plan fails for a non-remote reason."""
    target = tmp_path / "target"
    write_executable(
        target / ".csarc/scripts/apply-repository-settings.sh",
        "#!/usr/bin/env bash\n"
        "echo 'CODEOWNERS validation failed: @org/team lacks access.' >&2\n"
        "exit 1\n",
    )
    return target


def test_settings_plan_names_its_real_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC6: a known GitHub origin never reads as a missing remote."""
    target = settings_target(tmp_path)
    monkeypatch.setattr(
        cli, "target_repository", lambda _target: "example-org/consumer"
    )

    cli.settings_plan(target)
    output = capsys.readouterr()
    assert "needs a GitHub" not in output.out
    assert (
        "Repository settings plan failed (exit 1): CODEOWNERS validation "
        "failed: @org/team lacks access; no settings were applied."
    ) in output.out
    assert "CODEOWNERS validation failed" in output.err


def test_settings_plan_without_origin_says_so(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC6: only an unidentified origin is reported as a missing remote."""
    target = settings_target(tmp_path)
    monkeypatch.setattr(cli, "target_repository", lambda _target: None)

    cli.settings_plan(target)
    assert (
        "Repository settings plan needs a GitHub origin remote; no settings "
        "were applied."
    ) in capsys.readouterr().out
