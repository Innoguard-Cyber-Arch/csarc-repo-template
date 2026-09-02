"""Regression tests for the minimal Journey 03 verification workflow."""

import os
import shlex
import subprocess
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


def test_shared_cache_root_is_explicit_and_worktree_independent(
    tmp_path: Path,
) -> None:
    """Reuse downloads only when the caller names one absolute location."""
    resolver = REPO_ROOT / "scripts/resolve-cache-root"
    shared_cache = tmp_path / "shared-cache"
    environment = os.environ.copy()
    environment["CSARC_CACHE_ROOT"] = str(shared_cache)

    first = subprocess.run(  # noqa: S603 - repository-owned helper
        [resolver],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    second = subprocess.run(  # noqa: S603 - repository-owned helper
        [resolver],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert first.stdout.strip() == str(shared_cache)
    assert second.stdout == first.stdout
    assert shared_cache.is_dir()

    environment["CSARC_CACHE_ROOT"] = "relative-cache"
    rejected = subprocess.run(  # noqa: S603 - repository-owned helper
        [resolver],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert rejected.returncode == 2
    assert "must be an absolute path" in rejected.stderr


def test_verification_reuses_downloads_without_sharing_environments() -> None:
    """Share package stores and pinned tools, not installed environments."""
    root_fast = (REPO_ROOT / "scripts/verify-fast").read_text(encoding="utf-8")
    root_full = (REPO_ROOT / "scripts/verify-template.sh").read_text(
        encoding="utf-8"
    )
    generated_fast = (
        REPO_ROOT / "template/scripts/verify-fast.jinja"
    ).read_text(encoding="utf-8")
    generated_full = (REPO_ROOT / "template/scripts/verify.jinja").read_text(
        encoding="utf-8"
    )

    assert all(
        "scripts/resolve-cache-root" in source
        for source in (root_fast, root_full, generated_fast, generated_full)
    )
    assert all(
        'export UV_CACHE_DIR="$cache_root/uv"' in source
        and 'UV_CACHE_DIR="${UV_CACHE_DIR:-$cache_root/uv}"' in source
        for source in (root_fast, root_full, generated_fast, generated_full)
    )
    assert all(
        '--store-dir "$pnpm_store_dir"' in source
        for source in (generated_fast, generated_full)
    )
    assert all(
        "$cache_root/.venv" not in source
        and "$cache_root/node_modules" not in source
        for source in (root_fast, root_full, generated_fast, generated_full)
    )


def test_pinned_tool_caches_are_platform_scoped_and_revalidated() -> None:
    """Avoid cross-platform binaries and repair a corrupt cached download."""
    installers = (
        "install-actionlint",
        "install-gitleaks",
        "install-hugo",
        "install-osv-scanner",
        "install-shellcheck",
    )
    for name in installers:
        source = (REPO_ROOT / f"scripts/{name}").read_text(encoding="utf-8")
        assert "scripts/resolve-cache-root" in source
        assert "$(shasum -a 256 " in source
        assert ".tmp.$$" in source
        assert "$version/" in source

    assert "$version/$asset" in (
        REPO_ROOT / "scripts/install-actionlint"
    ).read_text(encoding="utf-8")
    assert "$version/$platform" in (
        REPO_ROOT / "scripts/install-shellcheck"
    ).read_text(encoding="utf-8")


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
    assert "CSARC_RUN_OSV: ${{ steps.plan.outputs.run_osv }}" in source
    assert all(
        name not in source
        for name in ("zizmor", "matrix:", "schedule:", "push:")
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
    assert "CSARC_RUN_OSV:" in source
    assert "steps.plan.outputs.run_osv" in source
    assert all(
        name not in source
        for name in ("zizmor", "matrix:", "schedule:", "push:")
    )


def test_documentation_tier_validates_the_generated_site() -> None:
    """Documentation-only changes still verify their built artifact."""
    root_fast = (REPO_ROOT / "scripts/verify-fast").read_text(encoding="utf-8")
    template_fast = (
        REPO_ROOT / "template/scripts/verify-fast.jinja"
    ).read_text(encoding="utf-8")

    assert "./scripts/build-decision-site --check" in root_fast
    assert "python3 scripts/render_site.py --check" in template_fast


def test_template_smoke_reads_config_from_the_generated_repository() -> None:
    """Resolve the generated config relative to the generated repository."""
    source = (REPO_ROOT / "scripts/verify-fast").read_text(encoding="utf-8")

    assert (
        '(cd "$smoke_root/project" '
        "&& python3 scripts/csarc_config.py languages >/dev/null)" in source
    )


def test_template_verification_reports_stage_timings() -> None:
    """Keep the full entry point readable in local and Actions logs."""
    entry = REPO_ROOT / "scripts/verify-template.sh"
    source = entry.read_text(encoding="utf-8")
    quoted_entry = shlex.quote(str(entry))
    stage_names = (
        "Repository contracts",
        "Static assets and paired files",
        "Python environment",
        "Python quality",
        "Regression tests",
        "Package smoke test",
        "GitHub Actions audit",
    )
    assert all(f'run_stage "{name}"' in source for name in stage_names)
    success = subprocess.run(  # noqa: S603 - sources this repository's script
        [
            "/bin/bash",
            "-c",
            f"""
source {quoted_entry}
verification_started=$SECONDS
sample_stage() {{ :; }}
run_stage "Sample stage" sample_stage
print_timing_summary
""",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "[verify-template] START Sample stage" in success.stdout
    assert "[verify-template] PASSED Sample stage (" in success.stdout
    assert "[verify-template] Timing summary" in success.stdout
    assert "TOTAL" in success.stdout

    failure = subprocess.run(  # noqa: S603 - sources this repository's script
        [
            "/bin/bash",
            "-c",
            f"""
source {quoted_entry}
verification_started=$SECONDS
trap report_failure ERR
sample_failure() {{ return 7; }}
run_stage "Broken stage" sample_failure
""",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert failure.returncode == 7
    assert "[verify-template] FAILED Broken stage (" in failure.stderr
    assert "FAILED" in failure.stderr
    assert "TOTAL" in failure.stderr


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


def test_issue_pr_policy_regressions_run_only_for_relevant_scopes() -> None:
    """Avoid rerunning policy fixtures for unrelated source changes."""
    expected = {
        "./scripts/test-issue-triage",
        "./scripts/test-pr-policy",
        "./scripts/test-worktree-cleanup",
    }
    for path in (
        "scripts/verify-fast",
        "template/scripts/verify-fast.jinja",
    ):
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
        gate_start = source.index('if [[ "$scopes" == *,governance,*')
        gate_end = source.index("\nfi", gate_start)
        gate = source[gate_start:gate_end]

        assert expected <= {
            line.strip()
            for line in gate.splitlines()
            if line.strip().startswith("./scripts/test-")
        }
        assert all(
            scope in gate
            for scope in ("governance", "template", "workflow", "shell")
        )
        assert "source" not in gate
        assert "dependency" not in gate


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
