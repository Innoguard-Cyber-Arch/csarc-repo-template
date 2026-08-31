"""Regression tests for the active Journey 06 delivery workflow."""

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parents[1]
WORKFLOW = "milestone-lifecycle.yml"


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one mapping-only YAML document."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_milestone_lifecycle_is_paired_and_bounded() -> None:
    """Ship one bounded Milestone closure workflow to both repository forms."""
    root_path = REPO_ROOT / ".github" / "workflows" / WORKFLOW
    template_path = REPO_ROOT / "template" / root_path.relative_to(REPO_ROOT)

    assert root_path.read_bytes() == template_path.read_bytes()

    workflow = load_yaml(root_path)
    triggers = workflow.get("on", workflow.get(True))
    assert triggers == {
        "issues": {"types": ["closed", "reopened", "milestoned"]}
    }
    assert "schedule" not in triggers
    for job in workflow["jobs"].values():
        assert job["timeout-minutes"] == 5
        assert "matrix" not in job.get("strategy", {})


def test_milestone_lifecycle_delegates_to_repository_script() -> None:
    """Keep Milestone closure logic outside workflow YAML."""
    source = (REPO_ROOT / ".github" / "workflows" / WORKFLOW).read_text(
        encoding="utf-8"
    )

    assert "scripts/sync_milestone_state.py" in source
