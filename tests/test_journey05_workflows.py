"""Regression tests for the active Journey 05 pull-request workflow."""

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parents[1]
WORKFLOW = "pr-policy.yml"
WRITE_WORKFLOW = "pr-policy-writes.yml"


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
        assert "write" not in job.get("permissions", {}).values()


def test_pr_policy_delegates_to_repository_scripts() -> None:
    """Keep read-only PR routing and decision logic outside workflow YAML."""
    source = (REPO_ROOT / ".github" / "workflows" / WORKFLOW).read_text(
        encoding="utf-8"
    )

    assert "./scripts/validate-pr-policy" in source
    assert "scripts/delivery_sync.py" in source
    assert "scripts/sync_work_item_metadata.py" not in source
    assert source.count("--read-only") == 4
    assert 'PR_POLICY_READ_ONLY: "true"' in source


def test_pr_policy_writes_run_only_from_the_trusted_revision() -> None:
    """Keep governance writes outside every PR-controlled workflow."""
    root_path = REPO_ROOT / ".github" / "workflows" / WRITE_WORKFLOW
    template_path = REPO_ROOT / "template" / root_path.relative_to(REPO_ROOT)

    assert root_path.read_bytes() == template_path.read_bytes()

    workflow = load_yaml(root_path)
    triggers = workflow.get("on", workflow.get(True))
    assert triggers == {
        "workflow_run": {
            "workflows": ["PR policy"],
            "types": ["completed"],
        }
    }
    assert workflow["permissions"] == {}
    assert workflow["concurrency"] == {
        "group": (
            "pr-policy-writes-${{ github.event.workflow_run.event }}-"
            "${{ github.event.workflow_run.head_repository.full_name }}-"
            "${{ github.event.workflow_run.head_branch }}-"
            "${{ github.event.workflow_run.head_sha }}"
        ),
        "cancel-in-progress": False,
    }
    assert workflow["jobs"]["resolve-pr"]["permissions"] == {
        "contents": "read",
        "pull-requests": "read",
    }
    assert workflow["jobs"]["metadata"]["permissions"] == {
        "contents": "read",
        "issues": "write",
        "pull-requests": "write",
    }
    assert workflow["jobs"]["milestone-approval"]["permissions"] == {
        "checks": "write",
        "contents": "read",
        "issues": "read",
        "pull-requests": "read",
    }

    source = root_path.read_text(encoding="utf-8")
    assert "ref: ${{ github.sha }}" in source
    assert "ref: ${{ github.event.workflow_run.head_sha }}" not in source
    assert "pull_requests[0]" not in source
    assert "actions/download-artifact" not in source
    assert "--resolve-head-sha" in source
    assert "github.event.workflow_run.head_repository.full_name" in source
    assert "github.event.workflow_run.head_branch" in source
    assert "scripts/sync_work_item_metadata.py" in source
    assert "scripts/sync_milestone_state.py check-pr" in source
    assert "scripts/sync_milestone_state.py check-merge-group" in source
