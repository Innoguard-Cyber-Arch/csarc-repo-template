"""Regression tests for the minimal Journey 03 verification workflow."""

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parents[1]


def direct_regression_commands(path: str) -> set[str]:
    """Return standalone regressions invoked by one stage entry point."""
    source = (REPO_ROOT / path).read_text(encoding="utf-8")
    return {
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith("./scripts/test-")
    }


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one mapping-only YAML document."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_root_ci_is_one_bounded_verification_job() -> None:
    """Spend at most one runner on each template-repository change."""
    path = REPO_ROOT / ".github/workflows/ci.yml"
    workflow = load_yaml(path)
    triggers = workflow.get("on", workflow.get(True))

    assert set(triggers) == {
        "pull_request",
        "merge_group",
        "workflow_dispatch",
    }
    assert set(workflow["permissions"]) == {"contents"}
    assert set(workflow["jobs"]) == {"verify"}
    assert workflow["jobs"]["verify"]["timeout-minutes"] == 30

    source = path.read_text(encoding="utf-8")
    assert "python3 scripts/ci_tier.py" in source
    assert "run: ./scripts/verify-fast" in source
    assert "run: ./scripts/verify-template.sh" in source
    assert all(
        name not in source
        for name in ("osv", "zizmor", "matrix:", "schedule:", "push:")
    )


def test_generated_ci_uses_the_same_one_job_contract() -> None:
    """Give generated repositories the same local-first wrapper."""
    path = REPO_ROOT / "template/.github/workflows/ci.yml.jinja"
    source = path.read_text(encoding="utf-8")

    assert "jobs:\n  verify:" in source
    assert "timeout-minutes: 30" in source
    assert "python3 scripts/ci_tier.py" in source
    assert "run: ./scripts/verify-fast" in source
    assert "run: ./scripts/verify" in source
    assert all(
        name not in source
        for name in ("osv", "zizmor", "matrix:", "schedule:", "push:")
    )


def test_documentation_tier_validates_the_generated_site() -> None:
    """Documentation-only changes still verify their built artifact."""
    root_fast = (REPO_ROOT / "scripts/verify-fast").read_text(encoding="utf-8")
    template_fast = (
        REPO_ROOT / "template/scripts/verify-fast.jinja"
    ).read_text(encoding="utf-8")

    assert "./scripts/build-decision-site --check" in root_fast
    assert "python3 scripts/render_site.py --check" in template_fast


def test_release_verification_contains_issue_pr_regressions() -> None:
    """Keep each release set a provable superset of its Issue PR set."""
    root_issue = direct_regression_commands("scripts/verify-fast")
    root_release = direct_regression_commands("scripts/verify-template.sh")
    generated_issue = direct_regression_commands(
        "template/scripts/verify-fast.jinja"
    )
    generated_release = direct_regression_commands(
        "template/scripts/verify.jinja"
    )

    assert root_issue == generated_issue
    assert root_issue <= root_release
    assert generated_issue <= generated_release


def test_full_pytest_includes_the_issue_pr_ai_contract() -> None:
    """Run the unmarked AI-guidance tests in both repo-template stages."""
    issue_entry = (REPO_ROOT / "scripts/verify-fast").read_text(
        encoding="utf-8"
    )
    release_entry = (REPO_ROOT / "scripts/verify-template.sh").read_text(
        encoding="utf-8"
    )
    ai_contract = (REPO_ROOT / "tests/test_ai_guidelines.py").read_text(
        encoding="utf-8"
    )

    assert 'uv run pytest -m "not large"' in issue_entry
    assert "uv run pytest --cov=csarc_cli" in release_entry
    assert "pytest.mark.large" not in ai_contract
