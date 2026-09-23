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

    root_source = root_path.read_text(encoding="utf-8")
    template_source = template_path.read_text(encoding="utf-8")
    assert root_source == template_source.replace(
        ".csarc/scripts/", "scripts/"
    ).replace(".csarc/policies/", "policies/")

    workflow = load_yaml(root_path)
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"pull_request_target", "merge_group"}
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


def test_required_check_names_only_run_from_trusted_workflows() -> None:
    """A PR-controlled workflow cannot impersonate a required check name."""

    def reports_required_name(raw_name: object, required_name: str) -> bool:
        if not isinstance(raw_name, str):
            return False
        return raw_name == required_name or any(
            quoted in raw_name
            for quoted in (f"'{required_name}'", f'"{required_name}"')
        )

    producers = {
        "pr-policy.yml": {"title"},
        "ci.yml": {"verify"},
        "pr-review.yml": {"review"},
    }
    required_names = set().union(*producers.values())

    for name, expected_names in producers.items():
        workflow = load_yaml(REPO_ROOT / ".github" / "workflows" / name)
        triggers = workflow.get("on", workflow.get(True))
        assert "pull_request_target" in triggers
        assert "pull_request" not in triggers
        job_names = [job.get("name") for job in workflow["jobs"].values()]
        assert all(
            any(
                reports_required_name(job_name, expected_name)
                for job_name in job_names
            )
            for expected_name in expected_names
        )

    for path in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
        workflow = load_yaml(path)
        triggers = workflow.get("on", workflow.get(True))
        if "pull_request" not in triggers:
            continue
        names = [job.get("name") for job in workflow["jobs"].values()]
        assert not any(
            reports_required_name(name, required_name)
            for name in names
            for required_name in required_names
        ), path

    generated_ci = (
        REPO_ROOT / "template/.github/workflows/ci.yml.jinja"
    ).read_text(encoding="utf-8")
    assert "  pull_request_target:\n" in generated_ci
    assert "  pull_request:\n" not in generated_ci

    policy = load_yaml(REPO_ROOT / ".github/workflows/pr-policy.yml")
    assert set(policy["jobs"]) == {"title"}
    assert (
        "github.event.pull_request.draft == false"
        in policy["jobs"]["title"]["if"]
    )
    assert any(
        step.get("name") == "Classify the delivery-promotion route"
        for step in policy["jobs"]["title"]["steps"]
    )


def test_pr_policy_writes_run_only_from_the_trusted_revision() -> None:
    """Keep governance writes outside every PR-controlled workflow."""
    root_path = REPO_ROOT / ".github" / "workflows" / WRITE_WORKFLOW
    template_path = REPO_ROOT / "template" / root_path.relative_to(REPO_ROOT)

    root_source = root_path.read_text(encoding="utf-8")
    template_source = template_path.read_text(encoding="utf-8")
    assert root_source == template_source.replace(".csarc/scripts/", "scripts/")

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
        "cancel-in-progress": True,
    }
    assert set(workflow["jobs"]) == {"process"}
    process = workflow["jobs"]["process"]
    assert process["permissions"] == {
        "checks": "write",
        "contents": "read",
        "issues": "write",
        "pull-requests": "write",
    }
    assert 'fromJSON(\'["success","failure"]\')' in process["if"]
    assert "workflow_run.conclusion" in process["if"]
    assert "!= 'cancelled'" not in process["if"]
    steps = {step["name"]: step for step in process["steps"]}
    checkout_count = sum(
        "actions/checkout@" in str(step) for step in process["steps"]
    )
    assert checkout_count == 1
    assert "!cancelled()" in steps["Synchronize pull request metadata"]["if"]
    assert (
        "!cancelled()"
        in steps["Publish the pull request approval decision"]["if"]
    )

    source = root_path.read_text(encoding="utf-8")
    assert "ref: ${{ github.sha }}" in source
    assert "ref: ${{ github.event.workflow_run.head_sha }}" not in source
    assert "pull_requests[0]" not in source
    assert "actions/download-artifact" not in source
    assert "--resolve-head-sha" in source
    assert "github.event.workflow_run.head_repository.full_name" in source
    assert "github.event.workflow_run.head_branch" in source
    assert "github.event.workflow_run.event == 'pull_request_target'" in source
    assert "scripts/sync_work_item_metadata.py" in source
    assert "scripts/sync_milestone_state.py check-pr" in source
    assert "scripts/sync_milestone_state.py check-merge-group" in source
    assert source.count("--publish-only") == 2


def test_pr_review_skips_draft_and_conversion_churn() -> None:
    """Defer draft review churn while retaining merge authorization."""
    root_path = REPO_ROOT / ".github/workflows/pr-review.yml"
    template_path = REPO_ROOT / "template/.github/workflows/pr-review.yml"
    root_source = root_path.read_text(encoding="utf-8")
    template_source = template_path.read_text(encoding="utf-8")
    assert root_source == template_source.replace(".csarc/scripts/", "scripts/")

    workflow = load_yaml(root_path)
    triggers = workflow.get("on", workflow.get(True))
    assert "converted_to_draft" not in triggers["pull_request_target"]["types"]
    assert workflow["jobs"]["merge-group-review"]["name"] == "review"
    condition = workflow["jobs"]["publish"]["if"]
    assert "github.event.pull_request.draft == false" in condition
    assert "PR lifecycle merge authorization" in condition
    assert "github.event_name != 'merge_group'" in condition
    assert workflow["jobs"]["publish"]["permissions"]["checks"] == "write"
    assert "review_gate.py publish" in root_source
    assert "--details-url" in root_source
    assert "--run-id" in root_source
