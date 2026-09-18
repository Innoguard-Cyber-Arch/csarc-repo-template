"""Tests for the hosted-verification bot allowlist (Issue #753)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

hosted_verify_bots = importlib.import_module("hosted_verify_bots")

REPO = "Innoguard-Cyber-Arch/csarc-repo-template"


def test_allowlisted_bot_on_its_own_branch_in_this_repo_is_eligible() -> None:
    """Dependabot, on its own branch prefix, from this repository, passes."""
    eligible, reason = hosted_verify_bots.hosted_verify_eligibility(
        "dependabot[bot]", "dependabot/uv/copier-9.18.2", REPO, REPO
    )
    assert eligible
    assert "eligible" in reason


def test_non_allowlisted_author_is_not_eligible() -> None:
    """An author absent from the allowlist keeps the attestation check."""
    eligible, reason = hosted_verify_bots.hosted_verify_eligibility(
        "some-contributor", "some-contributor/patch-1", REPO, REPO
    )
    assert not eligible
    assert "not on the hosted-verification allowlist" in reason


def test_allowlisted_author_with_wrong_branch_prefix_is_not_eligible() -> None:
    """An allowlisted login on a branch it does not own does not count."""
    eligible, reason = hosted_verify_bots.hosted_verify_eligibility(
        "dependabot[bot]", "not-dependabot/patch-1", REPO, REPO
    )
    assert not eligible
    assert "does not match" in reason


def test_allowlisted_author_from_a_fork_is_not_eligible() -> None:
    """A fork's head repository never qualifies, even with a matching branch."""
    eligible, reason = hosted_verify_bots.hosted_verify_eligibility(
        "dependabot[bot]",
        "dependabot/uv/copier-9.18.2",
        "someone-else/csarc-repo-template",
        REPO,
    )
    assert not eligible
    assert "fork" in reason


def test_missing_head_repository_is_not_eligible() -> None:
    """An empty head repository (unset event field) fails closed."""
    eligible, reason = hosted_verify_bots.hosted_verify_eligibility(
        "dependabot[bot]", "dependabot/uv/copier-9.18.2", "", REPO
    )
    assert not eligible
    assert "fork" in reason


def test_cli_writes_github_output(tmp_path: Path) -> None:
    """The command-line entry point appends eligible=true|false for Actions."""
    output = tmp_path / "github-output"
    exit_code = hosted_verify_bots.main(
        [
            "--author",
            "dependabot[bot]",
            "--head-ref",
            "dependabot/uv/copier-9.18.2",
            "--head-repo",
            REPO,
            "--base-repo",
            REPO,
            "--github-output",
            str(output),
        ]
    )
    assert exit_code == 0
    assert output.read_text(encoding="utf-8") == "eligible=true\n"
