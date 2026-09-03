"""Regression tests for the intentionally active Journey 01 workflows."""

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parents[1]
WORKFLOWS = {
    "issue-triage.yml": 5,
    "spec-to-issue.yml": 10,
}


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one mapping-only YAML document."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_journey01_workflows_are_paired() -> None:
    """Ship the same Journey 01 workflows at root and in the template."""
    for filename in WORKFLOWS:
        root_path = REPO_ROOT / ".github" / "workflows" / filename
        template_path = (
            REPO_ROOT / "template" / root_path.relative_to(REPO_ROOT)
        )
        assert root_path.read_bytes() == template_path.read_bytes()


def test_workflows_have_bounded_jobs_without_schedules_or_matrices() -> None:
    """Keep the restored policy workflows event-driven and bounded."""
    for filename, timeout in WORKFLOWS.items():
        workflow = load_yaml(REPO_ROOT / ".github" / "workflows" / filename)
        triggers = workflow.get("on", workflow.get(True))
        assert isinstance(triggers, dict)
        assert "schedule" not in triggers
        for job in workflow["jobs"].values():
            assert job["timeout-minutes"] == timeout
            assert "matrix" not in job.get("strategy", {})


def test_workflows_keep_the_approved_event_scope() -> None:
    """Run only for Journey 01 work-item events or an explicit sync."""
    triggers = {}
    for filename in WORKFLOWS:
        workflow = load_yaml(REPO_ROOT / ".github" / "workflows" / filename)
        triggers[filename] = workflow.get("on", workflow.get(True))

    assert triggers["issue-triage.yml"] == {
        "issues": {"types": ["opened", "edited", "reopened", "closed"]}
    }
    assert set(triggers["spec-to-issue.yml"]) == {"push", "workflow_dispatch"}


def test_workflows_delegate_to_the_existing_policy_scripts() -> None:
    """Reuse policy scripts instead of adding another implementation."""
    contents = {
        filename: (REPO_ROOT / ".github" / "workflows" / filename).read_text(
            encoding="utf-8"
        )
        for filename in WORKFLOWS
    }
    issue_validator = (REPO_ROOT / "scripts/validate-issue-policy").read_text(
        encoding="utf-8"
    )
    assert "./scripts/validate-issue-policy" in contents["issue-triage.yml"]
    assert "scripts/pr_lifecycle.py issue-edit" in issue_validator
    assert "scripts/spec_to_issue.py" in contents["spec-to-issue.yml"]
