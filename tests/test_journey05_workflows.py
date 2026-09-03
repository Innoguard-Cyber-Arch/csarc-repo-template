"""Regression tests for the active Journey 05 pull-request workflow."""

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parents[1]
WORKFLOW = "pr-policy.yml"


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one mapping-only YAML document."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_pr_policy_is_paired_and_bounded() -> None:
    """Ship one bounded PR policy to root and generated repositories."""
    root_path = REPO_ROOT / ".github" / "workflows" / WORKFLOW
    template_path = REPO_ROOT / "template" / root_path.relative_to(REPO_ROOT)

    assert root_path.read_bytes() == template_path.read_bytes()

    workflow = load_yaml(root_path)
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"pull_request", "merge_group"}
    assert "schedule" not in triggers
    for job in workflow["jobs"].values():
        assert job["timeout-minutes"] == 10
        assert "matrix" not in job.get("strategy", {})


def test_pr_policy_delegates_to_repository_scripts() -> None:
    """Keep PR routing and metadata logic outside workflow YAML."""
    source = (REPO_ROOT / ".github" / "workflows" / WORKFLOW).read_text(
        encoding="utf-8"
    )

    assert "./scripts/validate-pr-policy" in source
    assert "scripts/sync_work_item_metadata.py" in source
    assert "scripts/delivery_sync.py" in source
