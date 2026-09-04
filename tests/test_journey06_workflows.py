"""Regression tests for the active Journey 06 delivery workflow.

#574 merged three formerly independent workflows (Issue triage, Milestone
lifecycle, Work Issue closure) into one job with sequential steps inside
`work-item-lifecycle.yml`. GitHub Actions bills and queues per job (rounded
up to the nearest minute, each its own concurrency slot); folding lightweight,
same-permission governance checks into one job cuts that fan-out without
changing any step's own logic, permissions, or the scripts it calls.
"""

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parents[1]
WORKFLOW = "work-item-lifecycle.yml"

EXPECTED_TRIGGERS = {
    "issues": {
        "types": [
            "opened",
            "edited",
            "closed",
            "reopened",
            "labeled",
            "unlabeled",
            "milestoned",
            "demilestoned",
        ]
    },
    "issue_comment": {"types": ["created", "edited", "deleted"]},
    "milestone": {"types": ["created", "edited", "opened", "closed"]},
    "pull_request": {"types": ["closed"]},
}

# Step names in file order, distinguishing which formerly independent
# workflow each one carries forward.
EXPECTED_STEP_NAMES = [
    "Checkout",
    "Issue triage: assign author and apply issue classification",
    "Milestone lifecycle: reconcile lifecycle and refresh PR checks",
    "Milestone lifecycle: reconcile the previous Milestone",
    "Milestone lifecycle: resolve the tracker Issue this promotion closes",
    "Milestone lifecycle: record the merge commit as delivery evidence",
    "Work Issue closure: checkout the merge commit",
    "Work Issue closure: close the completed work Issue",
]


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one mapping-only YAML document."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_work_item_lifecycle_is_paired_and_bounded() -> None:
    """Ship one bounded, merged lifecycle workflow to both repository forms."""
    root_path = REPO_ROOT / ".github" / "workflows" / WORKFLOW
    template_path = REPO_ROOT / "template" / root_path.relative_to(REPO_ROOT)

    assert root_path.read_bytes() == template_path.read_bytes()

    workflow = load_yaml(root_path)
    triggers = workflow.get("on", workflow.get(True))
    assert triggers == EXPECTED_TRIGGERS
    assert "schedule" not in triggers
    # Never merge in Reviewer assignment's trusted-token trigger (see the
    # security-boundary comment at the top of the workflow file itself).
    assert "pull_request_target" not in workflow

    assert workflow["permissions"] == {
        "checks": "write",
        "contents": "read",
        "issues": "write",
        "pull-requests": "read",
    }
    # No write access to pull requests: that stays Reviewer assignment's
    # exclusive, separately-triggered privilege.
    assert workflow["permissions"]["pull-requests"] == "read"

    assert set(workflow["jobs"]) == {"process"}
    job = workflow["jobs"]["process"]
    assert job["timeout-minutes"] == 5
    assert "matrix" not in job.get("strategy", {})

    step_names = [step["name"] for step in job["steps"]]
    assert step_names == EXPECTED_STEP_NAMES


def test_work_item_lifecycle_concurrency_prefers_the_narrowest_entity() -> None:
    """Key concurrency by issue/PR number, falling back to Milestone number.

    Issue triage used to serialize per-issue (cancelling superseded runs);
    Milestone lifecycle serialized per-Milestone (never cancelling, since a
    reconcile must not be dropped mid-flight). One shared job can only use
    one concurrency group, so it prefers the Milestone number when the event
    carries one (preserving the cross-issue serialization Milestone sync
    needs) and otherwise falls back to the issue or PR number (preserving
    the original per-issue parallelism for the common non-Milestoned case).
    cancel-in-progress mirrors that split: only true when no Milestone
    number is present anywhere in the event.
    """
    workflow = load_yaml(REPO_ROOT / ".github" / "workflows" / WORKFLOW)
    concurrency = workflow["concurrency"]

    group = concurrency["group"]
    assert "github.event.issue.milestone.number" in group
    assert "github.event.milestone.number" in group
    assert "github.event.issue.number" in group
    assert "github.event.pull_request.number" in group
    assert "'misc'" in group

    cancel = concurrency["cancel-in-progress"]
    assert "github.event.issue.milestone.number == null" in cancel
    assert "github.event.milestone.number == null" in cancel


def test_work_item_lifecycle_steps_survive_independent_failures() -> None:
    """One step failing must not silently skip or mask a later, unrelated one.

    Each step after the initial checkout carries its original job-level
    `if:` condition (the three source workflows ran these as fully
    independent jobs). GitHub Actions skips later steps by default once one
    step fails, so every gated step must opt back in with `!cancelled()` —
    otherwise, e.g., a Milestone-sync failure would silently skip Work Issue
    closure on the same pull_request-closed event, without either failure
    being independently visible.
    """
    workflow = load_yaml(REPO_ROOT / ".github" / "workflows" / WORKFLOW)
    steps = workflow["jobs"]["process"]["steps"]

    assert steps[0]["name"] == "Checkout"
    for step in steps[1:]:
        condition = step.get("if", "")
        assert condition.strip().startswith("!cancelled()"), (
            f"step {step['name']!r} must run even if an earlier step in "
            "this job already failed"
        )


def test_work_item_lifecycle_delegates_to_repository_scripts() -> None:
    """Keep triage, Milestone sync, and closure logic outside workflow YAML."""
    source = (REPO_ROOT / ".github" / "workflows" / WORKFLOW).read_text(
        encoding="utf-8"
    )

    assert "run: ./scripts/validate-issue-policy" in source
    assert "scripts/sync_milestone_state.py" in source
    assert " reconcile" in source
    assert "scripts/sync_milestone_state.py record-promotion-evidence" in source
    assert "scripts/pr_lifecycle.py close-work" in source


def test_pr_policy_uses_the_same_milestone_validator() -> None:
    """Keep the PR gate and comment refresh on one implementation."""
    source = (REPO_ROOT / ".github/workflows/pr-policy.yml").read_text(
        encoding="utf-8"
    )

    assert "scripts/sync_milestone_state.py check-pr" in source
    assert "scripts/sync_milestone_state.py check-merge-group" in source
    assert "starts after the rollout PR reaches its base branch" in source


def test_ci_and_reviewer_assignment_stay_out_of_the_merge() -> None:
    """#574 forbids folding CI or Reviewer assignment into this workflow.

    CI (ci.yml) grows independently with rust/node/python toolchain checks
    at a different pace than these lightweight governance checks. Reviewer
    assignment (governance-comment.yml) runs on pull_request_target with the
    base repo's write-privileged token; mixing that with a workflow that can
    also run PR-branch-influenced steps would be a privilege-escalation
    anti-pattern. Both must stay separate files with their own triggers.
    """
    ci_workflow = load_yaml(REPO_ROOT / ".github/workflows/ci.yml")
    ci_triggers = ci_workflow.get("on", ci_workflow.get(True))
    assert set(ci_triggers) == {
        "pull_request",
        "merge_group",
        "workflow_dispatch",
    }

    reviewer_workflow = load_yaml(
        REPO_ROOT / ".github/workflows/governance-comment.yml"
    )
    reviewer_triggers = reviewer_workflow.get("on", reviewer_workflow.get(True))
    assert "pull_request_target" in reviewer_triggers
    assert reviewer_workflow["permissions"]["pull-requests"] == "write"
    # Reviewer assignment never listens for Issue/Milestone events; folding
    # it in would be exactly the merge #574 forbids.
    assert "issues" not in reviewer_triggers
    assert "issue_comment" not in reviewer_triggers
