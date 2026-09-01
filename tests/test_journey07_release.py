"""Regression tests for the automatic version and release workflow."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_release_workflow_is_one_capability_aware_pipeline() -> None:
    """Keep candidate creation and publication in one workflow owner."""
    path = ROOT / ".github/workflows/release.yml"
    source = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    triggers = workflow.get("on", workflow.get(True))

    assert triggers == {
        "push": {"branches": ["main"]},
        "workflow_dispatch": None,
    }
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]["release"]["permissions"]) == {
        "contents",
        "issues",
        "pull-requests",
        "statuses",
    }
    assert workflow["jobs"]["release"]["timeout-minutes"] == 30
    assert "googleapis/release-please-action@45996ed1" in source
    assert "release_policy.py plan" in source
    assert "release_policy.py detect" in source
    assert "mode == 'automatic'" in source
    assert "mode == 'guided'" in source
    assert "mode == 'blocked'" in source
    assert "release_policy.py prepare-candidate" in source
    assert "./scripts/verify-release-candidate" in source
    assert "scripts/release_bundle.py prepare" in source
    assert "scripts/release_bundle.py verify" in source
    assert "releases/assets/$asset_id" in source
    assert "gh release edit" in source
    assert "for attempt in $(seq 1 12)" in source
    assert "gh release verify" in source
    assert "secrets.GITHUB_TOKEN" in source
    assert "PAT" not in source
    assert "create-github-app-token" not in source
    assert "release_policy.py release" not in source
    assert "/actions/workflows/" not in source

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


def test_retired_archive_has_no_release_workflow_copy() -> None:
    """Use Git history instead of keeping replaced release workflows."""
    archive = ROOT / "archive/ci-cd/2026-08-27"
    assert not list((archive / "root-workflows").glob("*release*"))
    assert not list((archive / "template-workflows").glob("*release*"))


def test_guided_path_has_no_repo_local_publisher() -> None:
    """Only release.yml may create tags or GitHub Releases."""
    source = (ROOT / "scripts/release_policy.py").read_text(encoding="utf-8")

    assert "def direct_release" not in source
    assert 'add_parser("release")' not in source
    assert '"tag_name"' not in source
    assert '"/dispatches"' not in source
