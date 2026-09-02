"""Tests for reviewer assignment and optional governance drift automation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from copier import run_copy

ROOT = Path(__file__).resolve().parents[1]


def run_reviewer_assignment(
    tmp_path: Path, reviewers: str, author: str = "alice", number: int = 1
) -> subprocess.CompletedProcess[str]:
    """Run the repository-local reviewer logic with a fake GitHub CLI."""
    fixture = tmp_path / "fixture"
    (fixture / "scripts").mkdir(parents=True)
    (fixture / ".github").mkdir()
    script = fixture / "scripts/request-reviewer"
    shutil.copy2(ROOT / "scripts/request-reviewer", script)
    (fixture / ".github/REVIEWERS").write_text(reviewers, encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$GH_CAPTURE"\n',
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    capture = tmp_path / "gh-arguments"
    env = os.environ | {
        "GITHUB_REPOSITORY": "example/project",
        "GH_CAPTURE": str(capture),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "PR_AUTHOR": author,
        "PR_NUMBER": str(number),
    }
    return subprocess.run(  # noqa: S603
        [script],
        cwd=fixture,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_reviewer_assignment_excludes_author(tmp_path: Path) -> None:
    """Request exactly one configured reviewer who is not the PR author."""
    result = run_reviewer_assignment(tmp_path, "@alice\n@bob\n", number=8)

    assert result.returncode == 0, result.stderr
    assert "Requested review from @bob" in result.stdout
    arguments = (tmp_path / "gh-arguments").read_text(encoding="utf-8")
    assert "reviewers[]=bob" in arguments
    assert "reviewers[]=alice" not in arguments


def test_reviewer_assignment_skips_when_only_author_remains(
    tmp_path: Path,
) -> None:
    """Do not turn an impossible request into a misleading merge gate."""
    result = run_reviewer_assignment(tmp_path, "# owner\n@Alice\n")

    assert result.returncode == 0, result.stderr
    assert "Reviewer assignment skipped" in result.stdout
    assert not (tmp_path / "gh-arguments").exists()


def test_reviewer_assignment_rejects_invalid_configuration(
    tmp_path: Path,
) -> None:
    """Reject malformed reviewer names before making a GitHub API call."""
    result = run_reviewer_assignment(tmp_path, "alice\n")

    assert result.returncode == 1
    assert "Invalid reviewer" in result.stderr
    assert not (tmp_path / "gh-arguments").exists()


@pytest.mark.parametrize("enabled", [False, True])
def test_copier_governance_drift_option_is_complete(
    tmp_path: Path, enabled: bool
) -> None:
    """Generate both sides of the optional drift-automation contract."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / f"project-{enabled}"

    run_copy(
        str(source),
        project,
        data={
            "enable_governance_drift_check": enabled,
            "languages": [],
            "project_description": "Governance automation fixture.",
            "project_name": "Governance Fixture",
            "project_slug": "governance-fixture",
            "repository_url": "https://github.com/example/governance-fixture",
            "reviewers": "@alice,@bob",
            "security_reporting_channel": "Use the private security contact.",
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    assert (project / ".github/workflows/governance-comment.yml").is_file()
    assert (project / "scripts/request-reviewer").is_file()
    assert (
        (project / ".github/REVIEWERS")
        .read_text(encoding="utf-8")
        .endswith("@alice\n@bob\n")
    )
    assert (
        project / ".github/workflows/governance-drift.yml"
    ).exists() is enabled
    assert (project / "scripts/check-governance-drift").exists() is enabled


def test_governance_workflows_are_thin_and_least_privilege() -> None:
    """Keep events and permissions in YAML while logic stays local."""
    reviewer = (ROOT / ".github/workflows/governance-comment.yml").read_text(
        encoding="utf-8"
    )
    generated_reviewer = (
        ROOT / "template/.github/workflows/governance-comment.yml"
    ).read_text(encoding="utf-8")
    drift = (
        ROOT / "template/.github/workflows/governance-drift.yml"
    ).read_text(encoding="utf-8")

    assert reviewer == generated_reviewer
    assert (ROOT / "scripts/request-reviewer").read_bytes() == (
        ROOT / "template/scripts/request-reviewer"
    ).read_bytes()
    assert not (ROOT / ".github/workflows/governance-drift.yml").exists()
    assert not list(
        (ROOT / "archive/ci-cd/2026-08-27").rglob("*governance*.yml")
    )
    assert "pull_request_target:" in reviewer
    assert "ref: ${{ github.event.pull_request.base.sha }}" in reviewer
    assert "pull-requests: write" in reviewer
    assert "issues: write" not in reviewer
    assert "run: ./scripts/request-reviewer" in reviewer
    assert "timeout-minutes: 5" in reviewer

    assert "schedule:" in drift and "workflow_dispatch:" in drift
    assert "issues: write" in drift
    assert "pull-requests: write" not in drift
    assert "run: ./scripts/check-governance-drift" in drift
    assert "timeout-minutes: 5" in drift


def test_docs_reflect_restored_governance_actions() -> None:
    """Docs must not claim restored governance Actions are still archived."""
    stale_archived_list = "Zizmor、remote governance、deployment"
    for relative in (
        "README.md",
        "docs/ci-policy.md",
        "template/README.md.jinja",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert stale_archived_list not in text, relative
        assert "governance-comment.yml" in text, relative

    widget = (ROOT / "site/static/legacy-components.js").read_text(
        encoding="utf-8"
    )
    assert "The scheduled workflow is archived and does not run" not in widget
    # Issue #472 moved this code sample out of legacy-components.js into
    # site/data/config_examples.json (governance track, drift-schedule item),
    # server-rendered by the config-guidance shortcode; the underlying claim
    # this test protects (no stale "archived" wording) still applies there.
    config_examples = json.loads(
        (ROOT / "site/data/config_examples.json").read_text(encoding="utf-8")
    )
    drift_codes = " ".join(
        item["code"]["zh-tw"] + item["code"]["en"]
        for item in config_examples["tracks"]["governance"]["items"]
    )
    assert "The scheduled workflow is archived and does not run" not in (
        drift_codes
    )
    assert (
        "enable_governance_drift_check=true generates the daily workflow"
        in drift_codes
    )
