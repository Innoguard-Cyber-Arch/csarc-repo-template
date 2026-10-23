"""Read-only writing-guide review prompt in lifecycle reports (#1224)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import csarc_cli.cli as cli
from csarc_cli import lifecycle_report, writing_guide_review
from csarc_cli.lifecycle_report import LifecycleReportError

GENERATED_AT = "2026-10-23T00:00:00+00:00"
ENGLISH = ".csarc/docs/writing-guide.en.md"
CHINESE = ".csarc/docs/writing-guide.md"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def project(tmp_path: Path) -> Path:
    """Return a project with guides and project-owned documents."""
    root = tmp_path / "product"
    write(root / ENGLISH, "# English writing guide\n")
    write(root / CHINESE, "# 中文寫作指引\n")
    write(root / "README.md", "# Product\n")
    write(root / "README.en.md", "# Product (English)\n")
    write(root / "docs/guide.md", "Guide.\n")
    write(root / "docs/adr/0001-choice.md", "Decision.\n")
    write(root / "docs/diagram.png", "not markdown")
    write(root / "src/notes.md", "Not a document under docs/.\n")
    return root


def answers(mode: str = "content-only", languages: str = "zh-tw+en") -> dict:
    return {
        "documentation_mode": mode,
        "documentation_languages": languages,
    }


def recorded_answers(tmp_path: Path, mode: str = "content-only") -> dict:
    """Return answers complete enough for write_provenance."""
    return {
        **cli.resolve_release_answers(
            tmp_path, {"language": "ci", "project_mode": "existing"}
        ),
        **answers(mode=mode),
    }


def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def revision() -> cli.Revision:
    return cli.Revision("v1.0.0", "b" * 40, "https://example.invalid/t.git")


def report_with(tmp_path: Path, prompt: dict | None) -> dict[str, object]:
    plan = cli.ResolvedPlan(
        mode="update",
        target=tmp_path / "product",
        revision=revision(),
        repository=cli.RepositoryContext(
            "owner/product", "owner", "User", "private", "github", True
        ),
        answers=cli.resolve_release_answers(
            tmp_path, {"language": "ci", "project_mode": "existing"}
        ),
        capabilities={},
        files=cli.Plan((), (), (), ("README.md",), (), (), ()),
        update={"update_available": True},
        writing_guide=prompt,
    )
    return cli.lifecycle_report_model(
        plan,
        operation="update",
        plan_name=cli.UPDATE_PLAN_BASENAME,
        plan_sha256="a" * 64,
        generated_at=GENERATED_AT,
        previous=revision(),
        target_head="c" * 40,
        target_changes=(),
    )


def test_first_prompt_lists_project_documents(tmp_path: Path) -> None:
    root = project(tmp_path)
    before = snapshot(root)

    prompt = cli.writing_guide_prompt(root, root, answers(), recorded_from=root)

    assert prompt == {
        "files": [
            "README.en.md",
            "README.md",
            "docs/adr/0001-choice.md",
            "docs/guide.md",
        ],
        "guides": [ENGLISH, CHINESE],
        "instruction": writing_guide_review.INSTRUCTION,
        "reason": "first",
    }
    report = report_with(tmp_path, prompt)
    markdown = lifecycle_report.render_markdown(
        json.loads(lifecycle_report.report_json(report))
    )
    section = markdown.split("## Writing guide\n", 1)[1]
    assert "for the first time" in section
    assert "CSARC did not change any project-owned document" in section
    assert "- `docs/guide.md`" in section
    assert f"Agent instruction: {writing_guide_review.INSTRUCTION}" in section
    assert report["status"] == "ready"
    assert report["required_actions"] == []
    assert snapshot(root) == before


def test_same_version_is_not_prompted_again(tmp_path: Path) -> None:
    root = project(tmp_path)

    cli.write_provenance(root, revision(), answers=recorded_answers(tmp_path))
    recorded = json.loads((root / cli.PROVENANCE_FILE).read_text())

    assert recorded[writing_guide_review.PROVENANCE_KEY] == (
        writing_guide_review.guide_version(root)
    )
    assert (
        cli.writing_guide_prompt(root, root, answers(), recorded_from=root)
        is None
    )
    report = report_with(tmp_path, None)
    markdown = lifecycle_report.render_markdown(report)
    assert report["writing_guide"] is None
    assert "## Writing guide" not in markdown


def test_changed_version_prompts_again(tmp_path: Path) -> None:
    root = project(tmp_path)
    cli.write_provenance(root, revision(), answers=recorded_answers(tmp_path))
    received = tmp_path / "received"
    write(received / ENGLISH, "# English writing guide\n\nE12. New rule.\n")
    before = snapshot(root)

    prompt = cli.writing_guide_prompt(
        received, root, answers(), recorded_from=root
    )

    assert prompt is not None
    assert prompt["reason"] == "changed"
    assert prompt["guides"] == [ENGLISH]
    markdown = lifecycle_report.render_markdown(report_with(tmp_path, prompt))
    assert "changed since the last review prompt" in markdown
    assert snapshot(root) == before


def test_documentation_mode_off_is_silent_and_records_nothing(
    tmp_path: Path,
) -> None:
    root = project(tmp_path)
    off = answers(mode="off")
    before = snapshot(root)

    assert cli.writing_guide_prompt(root, root, off, recorded_from=root) is None
    assert snapshot(root) == before
    cli.write_provenance(
        root, revision(), answers=recorded_answers(tmp_path, mode="off")
    )
    recorded = json.loads((root / cli.PROVENANCE_FILE).read_text())
    assert writing_guide_review.PROVENANCE_KEY not in recorded


def test_languages_select_the_readme_files(tmp_path: Path) -> None:
    root = project(tmp_path)
    write(root / "README.zh-tw.md", "# 產品\n")

    english_first = writing_guide_review.project_documents(root, "en+zh-tw")
    chinese_only = writing_guide_review.project_documents(root, "zh-tw")

    assert "README.zh-tw.md" in english_first
    assert "README.en.md" not in english_first
    assert "README.en.md" not in chinese_only
    assert "README.zh-tw.md" not in chinese_only


def test_a_project_without_guides_is_not_prompted(tmp_path: Path) -> None:
    root = tmp_path / "bare"
    write(root / "README.md", "# Bare\n")

    assert writing_guide_review.guide_version(root) is None
    assert cli.writing_guide_prompt(root, root, answers()) is None


def test_terminal_plan_prints_the_prompt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path)
    prompt = cli.writing_guide_prompt(root, root, answers())

    cli.print_writing_guide(prompt)
    output = capsys.readouterr().out

    assert output.startswith("Writing guide: review 4 project-owned")
    assert "  docs/guide.md\n" in output
    assert "no file is changed" in output
    cli.print_writing_guide(None)
    assert capsys.readouterr().out == ""


def test_long_file_lists_stay_in_the_report_json(tmp_path: Path) -> None:
    files = [f"docs/page-{index:02}.md" for index in range(25)]
    prompt = {
        "files": files,
        "guides": [ENGLISH],
        "instruction": writing_guide_review.INSTRUCTION,
        "reason": "first",
    }

    markdown = lifecycle_report.render_markdown(report_with(tmp_path, prompt))

    assert "- `docs/page-19.md`" in markdown
    assert "docs/page-20.md" not in markdown
    assert "5 more file(s) are listed only in the report JSON." in markdown


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("reason", "again", "unknown value"),
        ("guides", [], "at least one guide"),
        ("files", "README.md", "list of paths"),
        ("instruction", None, "must be a string"),
        ("extra", True, "unknown keys"),
    ],
)
def test_invalid_prompts_fail_closed(
    tmp_path: Path, key: str, value: object, message: str
) -> None:
    prompt: dict[str, object] = {
        "files": [],
        "guides": [ENGLISH],
        "instruction": writing_guide_review.INSTRUCTION,
        "reason": "first",
    }
    report = report_with(tmp_path, prompt)
    broken = copy.deepcopy(report)
    broken["writing_guide"] = {**prompt, key: value}

    with pytest.raises(LifecycleReportError, match=message):
        lifecycle_report.validate_report(broken)


def test_earlier_report_versions_have_no_prompt(tmp_path: Path) -> None:
    report = report_with(tmp_path, None)
    earlier = dict(report)
    earlier.pop("writing_guide")
    earlier["report_format_version"] = (
        lifecycle_report.REPORT_FORMAT_VERSION_2_2
    )

    assert lifecycle_report.validate_report(earlier) is earlier
    earlier["writing_guide"] = None
    with pytest.raises(LifecycleReportError, match="unknown keys"):
        lifecycle_report.validate_report(earlier)


def test_spec_documents_the_prompt() -> None:
    spec = (
        Path(__file__).resolve().parents[1]
        / "docs/specs/SPEC-008-lifecycle-report-format.md"
    ).read_text(encoding="utf-8")

    assert f"`## {lifecycle_report.WRITING_GUIDE_HEADING}`" in spec
    assert f"`{writing_guide_review.PROVENANCE_KEY}`" in spec
    for value in lifecycle_report.WRITING_GUIDE_REASONS:
        assert f"`{value}`" in spec
