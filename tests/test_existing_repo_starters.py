"""An update never adds starter files to an existing repository (#1166).

Handbook 5.1 and appendix B.9: an existing repository owns its README and
LICENSE. The operator run updated two existing consumers and the update
added a proprietary LICENSE (holder inferred from the project name) and a
secondary README starter; no consumer identity is recorded here.
"""

from __future__ import annotations

import json
from pathlib import Path

import jinja2
import pytest
import yaml
from test_cli import commit
from test_operator_run_regressions import legacy_consumer, main, update, write

from csarc_cli import cli, final_plan

ROOT = Path(__file__).resolve().parents[1]


def excluded_paths(data: dict[str, object]) -> set[str]:
    """Render the real ``copier.yml`` exclusions for one answer set."""
    config = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    environment = jinja2.Environment(autoescape=False)  # noqa: S701
    return {
        environment.from_string(pattern).render(**data)
        for pattern in config["_exclude"]
        if "README" in pattern
    }


@pytest.mark.parametrize("languages", ["zh-tw+en", "en+zh-tw"])
def test_existing_repository_renders_no_readme_starter(languages: str) -> None:
    """AC1: neither language's README starter reaches an existing repo."""
    secondary = (
        "/README.en.md" if languages == "zh-tw+en" else "/README.zh-tw.md"
    )
    common = {
        "documentation_mode": "content-only",
        "documentation_languages": languages,
    }
    existing = excluded_paths({**common, "project_mode": "existing"})
    assert {"/README.md", secondary} <= existing
    new = excluded_paths({**common, "project_mode": "new"})
    assert "/README.md" not in new
    assert secondary not in new


def test_update_keeps_an_absent_license_product_owned(tmp_path: Path) -> None:
    """AC1: no LICENSE means ``custom`` and no inferred copyright holder."""
    existing = {"project_mode": "existing", "project_name": "Product"}
    assert cli.existing_license_seed(tmp_path, existing, {}) == {
        "project_license": "custom",
        "copyright_holder": "",
    }
    # A new project keeps its co-maintained starter; an existing LICENSE
    # is the product's own file and is never re-derived here.
    assert (
        cli.existing_license_seed(tmp_path, {"project_mode": "new"}, {}) == {}
    )
    (tmp_path / "LICENSE").write_text("Product terms.\n", encoding="utf-8")
    assert cli.existing_license_seed(tmp_path, existing, {}) == {}


def test_adding_a_license_on_update_needs_an_explicit_holder(
    tmp_path: Path,
) -> None:
    """AC1: only an explicit choice with a stated holder adds the starter."""
    existing = {"project_mode": "existing"}
    with pytest.raises(cli.CliError, match="copyright_holder"):
        cli.existing_license_seed(
            tmp_path, existing, {"project_license": "MIT"}
        )
    chosen = {"project_license": "MIT", "copyright_holder": "Example Owner"}
    assert cli.existing_license_seed(tmp_path, existing, chosen) == {}
    custom = {"project_license": "custom"}
    assert cli.existing_license_seed(tmp_path, existing, custom) == {}


@pytest.mark.large
def test_update_adds_no_license_to_an_existing_repository(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1 through check -> finalize -> apply on a legacy existing consumer.

    The new template renders a LICENSE starter unless the license is
    ``custom``, like the real ``copier.yml``. The consumer has no LICENSE,
    so the update adds none, and verification already sees the provenance
    the update lands (the recorded ``custom`` accepts an absent LICENSE).
    """
    project, source = legacy_consumer(tmp_path, {"notes.txt": "v1\n"})
    config_path = source / "copier.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["project_license"] = {"type": "str", "default": "proprietary"}
    config["_exclude"] = [
        ".git",
        "{% if project_license == 'custom' %}/LICENSE"
        "{% else %}__keep_license__{% endif %}",
    ]
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    write(
        source / "template/LICENSE.jinja",
        "Copyright (c) {{ copyright_holder }}. All rights reserved.\n",
    )
    new_sha = commit(source, "test: LICENSE starter")
    verified: list[str] = []
    original = cli.verify_project

    def recording(candidate: Path) -> object:
        provenance = candidate / ".csarc/provenance.json"
        record = json.loads(provenance.read_text(encoding="utf-8"))
        verified.append(record["commit_sha"])
        return original(candidate)

    monkeypatch.setattr(cli, "verify_project", recording)
    reports = tmp_path / "reports"
    capsys.readouterr()

    assert update(
        project, new_sha, "--check", "--report-dir", str(reports)
    ) in {0, 1}, capsys.readouterr().err
    files = json.loads(
        (reports / "csarc-update-plan.json").read_text(encoding="utf-8")
    )["files"]
    assert "LICENSE" not in files["add"]
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
    assert not (project / "LICENSE").exists()
    assert verified == [new_sha]


@pytest.mark.parametrize(
    ("name", "heading"),
    [
        ("install.md", "### 既有 repo 的 README 與 LICENSE"),
        ("install.en.md", "### README and LICENSE in an existing repo"),
    ],
)
def test_install_guide_describes_the_existing_starter_rule(
    name: str, heading: str
) -> None:
    """AC2: both install guides state the rule and the explicit opt-in."""
    text = (ROOT / "docs" / name).read_text(encoding="utf-8")
    section = text.split(heading, 1)[1].split("\n### ", 1)[0]
    for phrase in (
        "README.en.md",
        "`custom`",
        "--data project_license=<proprietary|MIT|Apache-2.0>",
        "--data copyright_holder=",
    ):
        assert phrase in section, phrase
