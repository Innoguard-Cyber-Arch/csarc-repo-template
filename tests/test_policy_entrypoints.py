"""Regression tests for workflow-independent policy validation."""

from pathlib import Path
from stat import S_IXUSR

ROOT = Path(__file__).resolve().parents[1]


def test_security_smoke_selects_existing_offline_owners() -> None:
    """Keep the smoke as one thin selector, not a provider-specific suite."""
    root_path = ROOT / "scripts/security-smoke"
    generated_path = ROOT / "template/.csarc/scripts/security-smoke"
    source = root_path.read_text(encoding="utf-8")

    assert source == generated_path.read_text(encoding="utf-8")
    assert root_path.stat().st_mode & S_IXUSR
    assert generated_path.stat().st_mode & S_IXUSR
    for owner in (
        "test-pr-policy",
        "test-apply-repository-settings",
        "test-check-repo-capabilities",
        "test-check-scope-gate",
    ):
        assert source.count(owner) >= 1
    for excluded in (
        "codex-security",
        "claude-security",
        "scan-secrets",
        "verify-dependencies",
    ):
        assert excluded not in source


def test_policy_tests_do_not_read_workflow_yaml() -> None:
    """Local tests exercise validators directly instead of parsing YAML."""
    for relative_path in (
        "scripts/test-issue-triage",
        "scripts/test-pr-policy",
    ):
        source = (ROOT / relative_path).read_text()
        assert ".github/workflows/work-item-lifecycle.yml" not in source
        assert ".github/workflows/pr-policy.yml" not in source
        assert "Could not extract" not in source


def test_policy_validators_use_generated_csarc_entrypoints() -> None:
    """Generated validators call only the generated CSARC entrypoints."""
    for name in ("validate-issue-policy", "validate-pr-policy"):
        generated = (ROOT / "template/.csarc/scripts" / name).read_text(
            encoding="utf-8"
        )
        assert ".csarc/scripts/" in generated
        assert "./scripts/" not in generated


def test_workflows_are_thin_trusted_wrappers() -> None:
    """Actions keep decisions read-only and isolate trusted writes."""
    issue_workflow = (
        ROOT / ".github/workflows/work-item-lifecycle.yml"
    ).read_text()
    pr_workflow = (ROOT / ".github/workflows/pr-policy.yml").read_text()
    write_workflow = (
        ROOT / ".github/workflows/pr-policy-writes.yml"
    ).read_text()

    assert "run: ./scripts/validate-issue-policy" in issue_workflow
    assert "issue_class=" not in issue_workflow
    assert "ref: ${{ github.event.pull_request.base.sha }}" in pr_workflow
    assert "run: ./scripts/validate-pr-policy" in pr_workflow
    assert "branch_pattern=" not in pr_workflow
    assert "checks: write" not in pr_workflow
    assert "issues: write" not in pr_workflow
    assert "pull-requests: write" not in pr_workflow
    assert "ref: ${{ github.sha }}" in write_workflow
    assert "github.event.workflow_run.pull_requests[0]" not in write_workflow
    assert "--resolve-head-sha" in write_workflow
