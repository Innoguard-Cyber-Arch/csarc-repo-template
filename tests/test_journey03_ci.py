"""Regression tests for the minimal Journey 03 verification workflow."""

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parents[1]


def direct_regression_commands(path: str) -> set[str]:
    """Return standalone regressions invoked by one stage entry point."""
    source = (REPO_ROOT / path).read_text(encoding="utf-8")
    return set(re.findall(r"\./scripts/test-[A-Za-z0-9-]+", source))


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
    """Spend at most one runner on each template-repository change.

    Issue #661: the `verify` required check no longer re-executes
    scripts/verify-fast or scripts/verify-template.sh on the runner --
    those now run locally, and the hosted job only checks the
    Verified-locally attestation they leave behind (see
    scripts/check-verify-attestation / scripts/verify_attestation.py).
    """
    path = REPO_ROOT / ".github/workflows/ci.yml"
    workflow = load_yaml(path)
    triggers = workflow.get("on", workflow.get(True))

    assert set(triggers) == {
        "pull_request",
        "merge_group",
        "workflow_dispatch",
    }
    assert workflow["permissions"] == {
        "contents": "read",
        "issues": "read",
        "pull-requests": "read",
    }
    assert set(workflow["jobs"]) == {"verify"}
    assert workflow["jobs"]["verify"]["timeout-minutes"] == 15

    source = path.read_text(encoding="utf-8")
    assert "python3 scripts/ci_tier.py" in source
    assert "run: ./scripts/check-verify-attestation" in source
    assert "--required-tier" in source
    assert "run: ./scripts/verify-fast" not in source
    assert "run: ./scripts/verify-template.sh" not in source
    assert "CSARC_RUN_OSV" not in source
    assert all(
        name not in source
        for name in ("zizmor", "matrix:", "schedule:", "push:")
    )


def test_generated_ci_uses_the_same_one_job_contract() -> None:
    """Give generated repositories the same local-first wrapper.

    Issue #661: same shift as the central template's own ci.yml above --
    the hosted job checks the attestation scripts/verify-fast.jinja /
    scripts/verify.jinja leave behind rather than re-running either.
    """
    path = REPO_ROOT / "template/.github/workflows/ci.yml.jinja"
    source = path.read_text(encoding="utf-8")

    assert "jobs:\n  verify:" in source
    assert "timeout-minutes: 15" in source
    assert "python3 scripts/ci_tier.py" in source
    assert "run: ./scripts/check-verify-attestation" in source
    assert "--required-tier" in source
    assert "run: ./scripts/verify-fast" not in source
    assert "run: ./scripts/verify" not in source
    assert "CSARC_RUN_OSV" not in source
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

    assert "./scripts/build-repo-site --check" in root_fast
    assert "./scripts/build-repo-site --check" in template_fast


def test_mixed_scope_pull_requests_still_catch_docs_staleness() -> None:
    """A fast-tier PR that also touches docs must not skip docs checks.

    Issue #588: a PR with scopes = {"workflow", "docs", ...} classifies as
    tier "fast", not "docs", so the docs-only early-exit branch never runs.
    Both docs checks it used to bundle -- spec validation and the
    repo-site staleness check -- must also fire from a second gate,
    keyed on scopes rather than tier, that survives past that early exit.
    Issue #598: #593 fixed only the staleness check in that second gate and
    left spec_to_issue.py validate behind, silently skipped for any mixed-
    scope PR that touches docs/specs/ or an ADR.
    """
    root_fast = (REPO_ROOT / "scripts/verify-fast").read_text(encoding="utf-8")
    template_fast = (
        REPO_ROOT / "template/scripts/verify-fast.jinja"
    ).read_text(encoding="utf-8")

    for source, staleness_check in (
        (root_fast, "./scripts/build-repo-site --check"),
        (template_fast, "./scripts/build-repo-site --check"),
    ):
        gate_start = source.index(
            'if [[ "$suite" == "docs" || "$scopes" == *,docs,* ]]; then'
        )
        gate_end = source.index("\nfi", gate_start)
        gate = source[gate_start:gate_end]

        assert "python3 scripts/spec_to_issue.py validate" in gate
        assert staleness_check in gate


def test_template_smoke_reads_config_from_the_generated_repository() -> None:
    """Resolve the generated config relative to the generated repository."""
    source = (REPO_ROOT / "scripts/verify-fast").read_text(encoding="utf-8")

    assert "python3 scripts/csarc_config.py languages" in source
    assert 'read_generated_languages "$smoke_root/project"' in source


def test_verification_steps_report_progress_heartbeat_and_rerun() -> None:
    """Make a silent or failing step actionable from the same log."""
    helper = shlex.quote(str(REPO_ROOT / "scripts/verification-step"))
    success = subprocess.run(  # noqa: S603 - sources this repository's script
        [
            "/bin/bash",
            "-c",
            (
                f"source {helper}; "
                "CSARC_VERIFICATION_HEARTBEAT_SECONDS=1 "
                'verification_step "Silent step" sleep 1.1'
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "[verify-step] START Silent step; log=stdout" in success.stdout
    assert "[verify-step] COMMAND sleep 1.1" in success.stdout
    assert "[verify-step] HEARTBEAT Silent step" in success.stdout
    assert "[verify-step] PASSED Silent step" in success.stdout

    failure = subprocess.run(  # noqa: S603 - sources this repository's script
        [
            "/bin/bash",
            "-c",
            (
                f"source {helper}; "
                'verification_step "Broken step" bash -c "exit 7"'
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert failure.returncode == 7
    assert "[verify-step] FAILED Broken step" in failure.stderr
    assert "[verify-step] RERUN bash -c exit\\ 7" in failure.stderr


def test_verification_entry_points_use_shared_step_reporting() -> None:
    """Keep every long local verification path observable."""
    entries = (
        REPO_ROOT / "scripts/verify-fast",
        REPO_ROOT / "template/scripts/verify-fast.jinja",
        REPO_ROOT / "template/scripts/verify.jinja",
        *sorted((REPO_ROOT / "scripts").glob("verify-stage-*")),
    )
    for entry in entries:
        source = entry.read_text(encoding="utf-8")
        assert "scripts/verification-step" in source
        assert "verification_step " in source


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
    assert "[verify-template] RERUN sample_failure" in failure.stderr
    assert "FAILED" in failure.stderr
    assert "TOTAL" in failure.stderr


def test_full_verification_stages_are_independently_runnable_scripts() -> None:
    """Rerun one full-verification stage without paying for the whole run.

    scripts/verify-template.sh is a thin aggregator (Issue #458): each of its
    seven stages is also a standalone scripts/verify-stage-* script. This
    proves the aggregator still calls the documented scripts, by name, in
    the same order, and that every one of them exists and is executable;
    test_template_verification_reports_stage_timings above already proves
    the shared run_stage/report_failure/print_timing_summary harness itself
    still reports PASSED/FAILED and a non-zero exit, so that mechanism is
    not re-tested here.
    """
    entry = REPO_ROOT / "scripts/verify-template.sh"
    source = entry.read_text(encoding="utf-8")

    expected = (
        ("Repository contracts", "scripts/verify-stage-repository-contracts"),
        (
            "Static assets and paired files",
            "scripts/verify-stage-static-assets",
        ),
        ("Python environment", "scripts/verify-stage-python-environment"),
        ("Python quality", "scripts/verify-stage-python-quality"),
        ("Regression tests", "scripts/verify-stage-regression-tests"),
        ("Package smoke test", "scripts/verify-stage-package-smoke"),
        ("GitHub Actions audit", "scripts/verify-stage-github-actions-audit"),
    )

    calls = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith('run_stage "')
    ]
    assert calls == [
        f'run_stage "{name}" ./{script}' for name, script in expected
    ]

    for _, script in expected:
        path = REPO_ROOT / script
        assert path.is_file(), f"Missing stage script: {script}"
        assert os.access(path, os.X_OK), f"Not executable: {script}"


def test_release_verification_contains_issue_pr_regressions() -> None:
    """Keep each release set a provable superset of its Issue PR set."""
    root_issue = direct_regression_commands("scripts/verify-fast")
    # scripts/verify-template.sh (Issue #458) is a thin aggregator; the
    # Regression tests stage's own ./scripts/test-* invocations moved to
    # scripts/verify-stage-regression-tests.
    root_release = direct_regression_commands(
        "scripts/verify-stage-regression-tests"
    )
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
        source = (
            (REPO_ROOT / path).read_text(encoding="utf-8").replace("\\\n", " ")
        )
        gate_start = source.index('if [[ "$scopes" == *,governance,*')
        gate_end = source.index("\nfi", gate_start)
        gate = source[gate_start:gate_end]

        assert expected <= set(
            re.findall(r"\./scripts/test-[A-Za-z0-9-]+", gate)
        )
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
    # The full-tier pytest invocation lives in the Regression tests stage
    # script since scripts/verify-template.sh became a thin aggregator
    # (Issue #458).
    release_entry = (
        REPO_ROOT / "scripts/verify-stage-regression-tests"
    ).read_text(encoding="utf-8")
    ai_contract = (REPO_ROOT / "tests/test_ai_guidelines.py").read_text(
        encoding="utf-8"
    )

    assert "uv run pytest -vv --durations=20" in issue_entry
    assert '-m "not large"' in issue_entry
    assert "uv run pytest -vv --durations=20" in release_entry
    assert "--cov=csarc_cli" in release_entry
    assert "pytest.mark.large" not in ai_contract
