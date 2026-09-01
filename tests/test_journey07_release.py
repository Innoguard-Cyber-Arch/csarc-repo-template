"""Regression tests for the automatic version and release workflow."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_release_workflow_is_one_bounded_pipeline() -> None:
    """Keep version PR validation and publication in one thin workflow."""
    path = ROOT / ".github/workflows/release.yml"
    source = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    triggers = workflow.get("on", workflow.get(True))

    assert triggers == {
        "push": {"branches": ["main"]},
        "workflow_dispatch": None,
    }
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert set(workflow["permissions"]) == {
        "contents",
        "issues",
        "pull-requests",
        "statuses",
    }
    assert workflow["jobs"]["release"]["timeout-minutes"] == 30
    assert "googleapis/release-please-action@45996ed1" in source
    assert "./scripts/verify-release-candidate" in source
    assert "scripts/release_bundle.py prepare" in source
    assert "scripts/release_bundle.py verify" in source
    assert "releases/assets/$asset_id" in source
    assert "gh release edit" in source
    assert "for attempt in $(seq 1 12)" in source
    assert "gh release verify" in source
    assert "secrets.GITHUB_TOKEN" in source
    assert "/actions/workflows/" not in source
    assert "source_run_id" not in source
    assert "PAT" not in source
    assert "create-github-app-token" not in source

    candidate = (ROOT / "scripts/verify-release-candidate").read_text(
        encoding="utf-8"
    )
    assert "release_bundle.py candidate" in candidate
    assert "./scripts/verify-template.sh" not in candidate
    assert "status=failure\nif (" in candidate
    assert 'publish_status "$status"' in candidate


def test_release_please_always_stages_a_draft() -> None:
    """Never expose a GitHub Release before its assets are verified."""
    config = json.loads(
        (ROOT / "release-please-config.json").read_text(encoding="utf-8")
    )
    assert config["packages"]["."]["draft"] is True
    assert '"draft": true' in (
        ROOT / "template/release-please-config.json.jinja"
    ).read_text(encoding="utf-8")


def test_template_only_adds_release_workflow_to_new_repositories() -> None:
    """Leave an existing repository's product-owned release workflow alone."""
    copier = (ROOT / "copier.yml").read_text(encoding="utf-8")
    template = (
        ROOT / "template/.github/workflows/release.yml.jinja"
    ).read_text(encoding="utf-8")

    assert "project_mode == 'new'" in copier
    assert ".github/workflows/release.yml" in copier
    assert "./scripts/verify full" in template
    assert "./scripts/verify-release-candidate" in template
    assert '{% if "typescript" in languages %}' in template
    assert '{% if "rust" in languages %}' in template


def test_guided_candidate_validation_is_csarc_owned_only() -> None:
    """Do not apply the CSARC release contract to product release branches."""
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["verify"]["steps"]
    candidate = next(
        step
        for step in steps
        if step.get("name") == "Validate the guided release candidate"
    )

    assert "steps.release.outputs.ownership == 'csarc-owned'" in candidate["if"]
    template = (ROOT / "template/.github/workflows/ci.yml.jinja").read_text(
        encoding="utf-8"
    )
    assert "steps.release.outputs.ownership == 'csarc-owned'" in template


def test_retired_archive_has_no_release_workflow_copy() -> None:
    """Use Git history instead of keeping replaced release workflows."""
    archive = ROOT / "archive/ci-cd/2026-08-27"
    assert not list((archive / "root-workflows").glob("*release*"))
    assert not list((archive / "template-workflows").glob("*release*"))
