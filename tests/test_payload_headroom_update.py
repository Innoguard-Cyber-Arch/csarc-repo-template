"""Existing projects see every #1177 payload removal in the update plan.

Issue #1177 replaces the five pinned-tool installers with one
`install-tool`. An existing project that updates must see each removed
installer in the reviewable plan, and an installer its own product files
still run must stay instead of disappearing (#1058 Kill criteria 1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import settings_support
from test_cli import commit, git, make_template

from csarc_cli.cli import main as cli_main

RETIRED_INSTALLERS = tuple(
    f".csarc/scripts/install-{tool}"
    for tool in ("actionlint", "gitleaks", "osv-scanner", "shellcheck", "syft")
)
INSTALL_TOOL = ".csarc/scripts/install-tool"
PRODUCT_WORKFLOW = ".github/workflows/product-secrets.yml"


def main(arguments: list[str]) -> int:
    """Run the CLI with the explicit setup seeds a script passes (#1078)."""
    return cli_main(settings_support.seeded_setup(arguments))


def write(path: Path, content: str) -> None:
    """Write one fixture file, creating its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.mark.large
def test_update_plan_lists_each_retired_installer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """R2: removals are planned; a product use keeps that installer."""
    source, _first = make_template(tmp_path)
    template = source / "template"
    for path in RETIRED_INSTALLERS:
        write(template / path, "#!/usr/bin/env bash\necho old installer\n")
    old_sha = commit(source, "test: per-tool installers")
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
    # The product runs one installer itself, so that one must stay.
    write(
        project / PRODUCT_WORKFLOW,
        "on: push\njobs:\n  scan:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: ./.csarc/scripts/install-gitleaks\n",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: product scans secrets")

    for path in RETIRED_INSTALLERS:
        (template / path).unlink()
    write(template / INSTALL_TOOL, "#!/usr/bin/env bash\necho installer\n")
    new_sha = commit(source, "test: one pinned-tool installer")
    reports = tmp_path / "reports"
    capsys.readouterr()

    assert main(
        [
            "update",
            str(project),
            "--to",
            new_sha,
            "--allow-unreleased",
            "--check",
            "--report-dir",
            str(reports),
        ]
    ) in {0, 1}, capsys.readouterr().err
    plan = json.loads(
        (reports / "csarc-update-plan.json").read_text(encoding="utf-8")
    )
    files = plan["files"]
    used = ".csarc/scripts/install-gitleaks"
    removed = {*files["remove"], *files["delete"]}
    assert removed == set(RETIRED_INSTALLERS) - {used}
    assert used in files["product_owned"]
    assert INSTALL_TOOL in files["add"]
