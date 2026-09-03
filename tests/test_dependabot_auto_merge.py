"""Regression tests for the Dependabot auto-merge workflow."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/dependabot-auto-merge.yml"


def _load_workflow() -> tuple[str, dict]:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    return source, workflow


def _steps_by_name(workflow: dict) -> dict[str, dict]:
    steps = workflow["jobs"]["auto-merge"]["steps"]
    return {step["name"]: step for step in steps}


def test_workflow_only_triggers_on_dependabot_pull_requests() -> None:
    """Never run for a human-authored pull request, even on the right event."""
    _, workflow = _load_workflow()
    triggers = workflow.get("on", workflow.get(True))

    assert triggers == {
        "pull_request": {"types": ["opened", "synchronize", "reopened"]}
    }
    job = workflow["jobs"]["auto-merge"]
    # The actor gate lives on the job itself, not on individual steps, so a
    # pull_request run from any other actor skips the entire job -- fetching
    # metadata, enabling auto-merge, and labeling all stay unreachable. It
    # reads pull_request.user.login rather than the spoofable github.actor
    # context (zizmor bot-conditions audit).
    assert (
        job["if"]
        == "${{ github.event.pull_request.user.login == 'dependabot[bot]' }}"
    )


def test_workflow_permissions_are_minimal() -> None:
    """Grant only what gh pr merge --auto and labeling actually need."""
    _, workflow = _load_workflow()

    assert workflow["permissions"] == {}
    assert workflow["jobs"]["auto-merge"]["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }
    assert workflow["jobs"]["auto-merge"]["timeout-minutes"] == 10


def test_fetch_metadata_action_is_pinned_to_a_full_commit_sha() -> None:
    """Match this repository's convention for every third-party Action."""
    source, _ = _load_workflow()

    match = re.search(
        r"dependabot/fetch-metadata@([0-9a-f]{40})\s+#\s+(v\S+)", source
    )
    assert match is not None, (
        "fetch-metadata must be pinned to a full commit SHA"
    )
    assert match.group(2).startswith("v")


def test_minor_and_patch_updates_enable_auto_merge() -> None:
    """Queue GitHub's native auto-merge instead of merging directly."""
    _, workflow = _load_workflow()
    steps = _steps_by_name(workflow)
    step = steps["Enable auto-merge for minor and patch updates"]

    condition = step["if"]
    assert "version-update:semver-patch" in condition
    assert "version-update:semver-minor" in condition
    assert "version-update:semver-major" not in condition
    assert step["run"].strip() == 'gh pr merge --auto --squash "$PR_URL"'


def test_major_updates_are_flagged_instead_of_merged() -> None:
    """Keep breaking-change-risk updates out of the auto-merge path."""
    _, workflow = _load_workflow()
    steps = _steps_by_name(workflow)
    step = steps["Flag major updates for manual review"]

    condition = step["if"]
    assert "version-update:semver-major" in condition
    assert "semver-minor" not in condition
    assert "semver-patch" not in condition
    run = step["run"]
    assert "gh pr merge" not in run
    assert 'gh pr edit "$PR_URL" --add-label needs-manual-review' in run
    assert "gh pr comment" in run


def test_needs_manual_review_label_is_defined_in_policy() -> None:
    """Keep the label the workflow applies provisionable from policy."""
    labels = json.loads(
        (REPO_ROOT / "policies/labels.json").read_text(encoding="utf-8")
    )
    names = {label["name"] for label in labels}

    assert "needs-manual-review" in names


def test_dependabot_cooldown_already_covers_the_supply_chain_delay() -> None:
    """Confirm the pre-merge safeguard the maintainer asked for is in place.

    The auto-merge workflow deliberately does not add its own waiting
    period: .github/dependabot.yml already delays every pull request by
    cooldown.default-days: 3 after a release, before Dependabot opens it.
    """
    config = (REPO_ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")

    assert len(re.findall(r"^\s+default-days:\s*3\s*$", config, re.M)) >= 1
