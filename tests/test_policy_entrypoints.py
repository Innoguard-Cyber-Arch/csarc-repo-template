"""Regression tests for workflow-independent policy validation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_policy_tests_do_not_read_workflow_yaml() -> None:
    """Local tests exercise validators directly instead of parsing YAML."""
    for relative_path in (
        "scripts/test-issue-triage",
        "scripts/test-pr-policy",
    ):
        source = (ROOT / relative_path).read_text()
        assert ".github/workflows/issue-triage.yml" not in source
        assert ".github/workflows/pr-policy.yml" not in source
        assert "Could not extract" not in source


def test_policy_validators_are_shipped_without_forks() -> None:
    """Generated repositories receive the exact validators tested at root."""
    for name in ("validate-issue-policy", "validate-pr-policy"):
        assert (ROOT / "scripts" / name).read_bytes() == (
            ROOT / "template/scripts" / name
        ).read_bytes()
