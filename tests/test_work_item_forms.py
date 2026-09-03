"""Tests for native GitHub work-item forms and PR templates."""

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
            *FORM_POLICY,
        }
        form_text = "\n".join(
            (form_dir / filename).read_text(encoding="utf-8")
            for filename in FORM_POLICY
        )
        assert 'type: "Duplicate"' not in form_text
        assert 'type: "Hotfix"' not in form_text


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
