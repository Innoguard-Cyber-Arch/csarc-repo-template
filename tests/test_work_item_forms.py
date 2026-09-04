"""Tests for native GitHub work-item forms and PR templates."""

import runpy
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).parents[1]
FORM_POLICY = {
    "feature.yml": ("Feature", "enhancement"),
    "task.yml": ("Task", "enhancement"),
    "bug.yml": ("Bug", "bug"),
    "documentation.yml": ("Task", "documentation"),
}
TRACKER_FORM_NAME = "milestone-tracker.yml"


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one mapping-only YAML document."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


@pytest.mark.parametrize(("filename", "expected"), FORM_POLICY.items())
def test_forms_set_native_type_and_one_classification(
    filename: str, expected: tuple[str, str]
) -> None:
    """Keep native metadata fixed at the entry point without an Action."""
    root_path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / filename
    template_path = REPO_ROOT / "template" / root_path.relative_to(REPO_ROOT)
    root_form = load_yaml(root_path)

    assert root_form == load_yaml(template_path)
    assert (root_form["type"], root_form["labels"][0]) == expected
    assert len(root_form["labels"]) == 1
    assert "assignees" not in root_form

    fields = [item for item in root_form["body"] if item["type"] != "markdown"]
    assert [field["id"] for field in fields] == [
        "problem",
        "acceptance",
        "supplement",
    ]
    assert [field["validations"]["required"] for field in fields] == [
        True,
        True,
        False,
    ]
    assert "--assignee @me" in root_form["body"][0]["attributes"]["value"]


def test_no_generic_or_duplicate_issue_entrypoint() -> None:
    """Duplicate is a close reason, not a work-item form or native Type."""
    for base in [REPO_ROOT, REPO_ROOT / "template"]:
        form_dir = base / ".github" / "ISSUE_TEMPLATE"
        assert not (form_dir / "work-item.yml").exists()
        assert {path.name for path in form_dir.glob("*.yml")} == {
            "config.yml",
            TRACKER_FORM_NAME,
            *FORM_POLICY,
        }
        form_text = "\n".join(
            (form_dir / filename).read_text(encoding="utf-8")
            for filename in [*FORM_POLICY, TRACKER_FORM_NAME]
        )
        assert 'type: "Duplicate"' not in form_text
        assert 'type: "Hotfix"' not in form_text


def test_milestone_tracker_form_matches_the_lifecycle_contract() -> None:
    """The tracker form's skeleton must stay in lockstep with tracker_errors().

    Issue #555: a dedicated Issue form pre-fills the four H2 sections
    `scripts/sync_milestone_state.py`'s `tracker_errors()` requires, so a
    missing or misspelled section is caught by the form itself instead of
    only after the Issue already exists. This test ties the form's field
    labels directly to `TRACKER_SECTIONS` (rather than re-hardcoding the
    same four strings) so the two cannot silently drift apart.
    """
    root_path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / TRACKER_FORM_NAME
    template_path = REPO_ROOT / "template" / root_path.relative_to(REPO_ROOT)
    root_form = load_yaml(root_path)

    assert root_form == load_yaml(template_path)
    assert root_form["type"] == "Feature"
    assert root_form["labels"] == ["enhancement"]
    assert "assignees" not in root_form
    assert "--assignee @me" in root_form["body"][0]["attributes"]["value"]

    module = runpy.run_path(
        str(REPO_ROOT / "scripts" / "sync_milestone_state.py")
    )
    tracker_sections = module["TRACKER_SECTIONS"]

    fields = [item for item in root_form["body"] if item["type"] != "markdown"]
    assert [field["id"] for field in fields] == [
        "proposal",
        "completion_evidence",
        "early_termination",
        "promotion",
        "references",
    ]
    # The first four field labels are the literal H2 headings tracker_errors()
    # searches for; they must match TRACKER_SECTIONS verbatim, in order.
    assert (
        tuple(field["attributes"]["label"] for field in fields[:4])
        == tracker_sections
    )
    assert fields[4]["attributes"]["label"] == "References"
    assert [field["validations"]["required"] for field in fields] == [
        True,
        True,
        True,
        True,
        False,
    ]


def test_milestone_tracker_form_skeleton_round_trips_through_parser() -> None:
    """Render the form's default output the way GitHub would, then parse it.

    Builds the Issue body exactly as GitHub Issue Forms renders it (each
    non-markdown field becomes `## <label>\\n\\n<value>\\n\\n`, in field
    order) from the form's own pre-filled `value` defaults, with nothing
    edited by a user yet. Confirms every required section is found by
    `_section()`, and that a still-untouched Proposal placeholder is
    correctly rejected by `_meaningful()` -- the form reduces hand-copy
    error but the fail-closed check downstream still catches a submission
    nobody actually filled in.
    """
    root_form = load_yaml(
        REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / TRACKER_FORM_NAME
    )
    module = runpy.run_path(
        str(REPO_ROOT / "scripts" / "sync_milestone_state.py")
    )
    section = module["_section"]
    meaningful = module["_meaningful"]
    tracker_sections = module["TRACKER_SECTIONS"]

    fields = [item for item in root_form["body"] if item["type"] != "markdown"]
    rendered = "".join(
        f"## {field['attributes']['label']}\n\n"
        f"{field['attributes'].get('value', '')}\n\n"
        for field in fields
    )

    for heading in tracker_sections:
        assert section(rendered, heading) is not None
    assert not meaningful(section(rendered, "Proposal"))

    filled = rendered.replace(
        fields[0]["attributes"]["value"],
        "Describe the real scope covered by this Milestone.\n",
    )
    assert meaningful(section(filled, "Proposal"))


def test_pr_templates_keep_repository_specific_checks_separate() -> None:
    """Generated projects must not inherit template-engine verification."""
    root_template = (
        REPO_ROOT / ".github" / "pull_request_template.md"
    ).read_text(encoding="utf-8")
    generated_template = (
        REPO_ROOT / "template" / ".github" / "pull_request_template.md"
    ).read_text(encoding="utf-8")

    assert "./scripts/verify-template.sh" in root_template
    assert "已測試新專案產生" in root_template
    assert "./scripts/verify`" in generated_template
    assert "verify-template.sh" not in generated_template
    assert "已測試新專案產生" not in generated_template


def test_paired_files_check_accepts_selected_actions() -> None:
    """Only the selected active workflows may remain template pairs."""
    completed = subprocess.run(  # noqa: S603
        [REPO_ROOT / "scripts" / "sync-paired-files.sh", "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
