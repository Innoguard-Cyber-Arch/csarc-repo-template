"""Regression tests for the minimal Journey 03 verification workflow."""

import os
import re
import runpy
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined

REPO_ROOT = Path(__file__).parents[1]


def direct_regression_commands(path: str) -> set[str]:
    """Return standalone regressions invoked by one stage entry point."""
    source = (REPO_ROOT / path).read_text(encoding="utf-8")
    source = source.replace("./.csarc/scripts/", "./scripts/")
    return set(re.findall(r"\./scripts/test-[A-Za-z0-9-]+", source))


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one mapping-only YAML document."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def ci_steps(source: str) -> list[dict[str, Any]]:
    """Return the one CI job's ordered steps from rendered YAML."""
    document = yaml.safe_load(source)
    assert isinstance(document, dict)
    steps = document["jobs"]["verify"]["steps"]
    assert isinstance(steps, list)
    return steps


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
        REPO_ROOT / "template/.csarc/scripts/verify-fast.jinja"
    ).read_text(encoding="utf-8")
    generated_full = (
        REPO_ROOT / "template/.csarc/scripts/verify.jinja"
    ).read_text(encoding="utf-8")

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
    """Run one trusted, tiered verification job on the exact candidate."""
    path = REPO_ROOT / ".github/workflows/ci.yml"
    workflow = load_yaml(path)
    triggers = workflow.get("on", workflow.get(True))

    assert set(triggers) == {
        "pull_request_target",
        "merge_group",
        "workflow_dispatch",
    }
    assert "edited" in triggers["pull_request_target"]["types"]
    assert set(workflow["permissions"]) == {
        "actions",
        "checks",
        "contents",
        "issues",
        "pull-requests",
    }
    assert all(level == "read" for level in workflow["permissions"].values())
    assert set(workflow["jobs"]) == {"verify"}
    assert workflow["jobs"]["verify"]["timeout-minutes"] == 30

    source = path.read_text(encoding="utf-8")
    assert "Preserve the trusted verification policy" in source
    assert 'python3 "$RUNNER_TEMP/trusted-verification/ci_tier.py"' in source
    assert "Check out the exact candidate" in source
    assert "Execute trusted verification tier=" in source
    assert "- name: Reuse trusted verification" in source
    assert "- name: Validate trusted clean sync" in source
    assert "./scripts/verify-fast" in source
    assert "./scripts/verify-template.sh" in source
    assert "check-verify-attestation" not in source
    assert "hosted_verify_bots" not in source
    assert "CSARC_RUN_OSV" not in source
    assert 'select(. == "promotion" or . == "hotfix" or' in source
    assert '. == "release-recovery")' in source
    assert all(
        name not in source
        for name in ("zizmor", "matrix:", "schedule:", "push:")
    )


def test_generated_ci_uses_the_same_one_job_contract() -> None:
    """Give generated repositories the same trusted hosted execution."""
    path = REPO_ROOT / "template/.github/workflows/ci.yml.jinja"
    source = path.read_text(encoding="utf-8")

    assert "jobs:\n  verify:" in source
    assert (
        "types: [opened, reopened, synchronize, edited, labeled, unlabeled, "
        "ready_for_review, converted_to_draft]" in source
    )
    assert "timeout-minutes: 30" in source
    permissions = source.split("permissions:", 1)[1].split("jobs:", 1)[0]
    assert set(yaml.safe_load(f"permissions:{permissions}")["permissions"]) == {
        "actions",
        "checks",
        "contents",
        "issues",
        "pull-requests",
    }
    assert "Preserve the trusted verification policy" in source
    assert 'python3 "$RUNNER_TEMP/trusted-verification/ci_tier.py"' in source
    assert "Execute trusted verification tier=" in source
    assert "./.csarc/scripts/verify-fast" in source
    assert "./.csarc/scripts/verify" in source
    assert "check-verify-attestation" not in source
    assert "hosted_verify_bots" not in source
    assert "CSARC_RUN_OSV" not in source
    assert 'select(. == "promotion" or . == "hotfix" or' in source
    assert '. == "release-recovery")' in source
    assert all(
        name not in source
        for name in ("zizmor", "matrix:", "schedule:", "push:")
    )


def test_ci_skips_non_actionable_pr_events_before_runner() -> None:
    """Skip Draft churn but keep every ready label event reporting `verify`.

    Issue #1019: a skipped job left the newest CI run on the head without a
    `verify` check, so GitHub reported the required check as expected even
    though an earlier run on the same head had passed. A non-tier label now
    runs the job, which reuses the same-head evidence.
    """
    root_source = (REPO_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    template_source = (
        REPO_ROOT / "template/.github/workflows/ci.yml.jinja"
    ).read_text(encoding="utf-8")
    rendered_template = (
        Environment(
            autoescape=False,  # noqa: S701 - trusted local YAML template
            undefined=StrictUndefined,
        )
        .from_string(template_source)
        .render(
            languages=["python", "typescript", "rust"],
            python_support_mode="latest",
            python_min_version="3.12",
        )
    )
    expected = (
        "${{ github.event_name != 'pull_request_target' || "
        "github.event.action == 'ready_for_review' || "
        "(github.event.action != 'converted_to_draft' && "
        "github.event.pull_request.draft != true) }}"
    )

    for source in (root_source, rendered_template):
        workflow = yaml.safe_load(source)
        triggers = workflow.get("on", workflow.get(True))
        assert {"labeled", "unlabeled"} <= set(
            triggers["pull_request_target"]["types"]
        )
        job = workflow["jobs"]["verify"]
        assert job["name"] == "verify"
        assert " ".join(job["if"].split()) == expected
        assert "label.name" not in job["if"]
        reuse = next(step for step in job["steps"] if step.get("id") == "reuse")
        # Label events take the same-head reuse path instead of rerunning.
        assert "edited|labeled|unlabeled|" in reuse["run"]


def test_hosted_verification_sets_up_each_profile_toolchain_first() -> None:
    """Install each selected language tool before hosted verification."""
    root_source = (REPO_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    template_source = (
        REPO_ROOT / "template/.github/workflows/ci.yml.jinja"
    ).read_text(encoding="utf-8")
    template = Environment(
        autoescape=False,  # noqa: S701 - trusted local YAML template
        undefined=StrictUndefined,
    ).from_string(template_source)
    rendered_templates = (
        template.render(
            languages=["python", "typescript", "rust"],
            python_support_mode="latest",
            python_min_version="3.12",
        ),
        template.render(
            languages=["typescript", "rust"],
            python_support_mode="latest",
            python_min_version="3.12",
        ),
    )

    contracts: list[list[str]] = []
    for source in (root_source, *rendered_templates):
        steps = ci_steps(source)
        hosted_index = next(
            index
            for index, step in enumerate(steps)
            if str(step.get("name", "")).startswith(
                "Execute trusted verification tier="
            )
        )
        toolchain = [
            (index, step)
            for index, step in enumerate(steps)
            if str(step.get("uses", "")).startswith(
                (
                    "actions/setup-python@",
                    "astral-sh/setup-uv@",
                    "pnpm/action-setup@",
                    "actions/setup-node@",
                )
            )
            or "rustup toolchain install" in str(step.get("run", ""))
        ]

        assert all(index < hosted_index for index, _ in toolchain)
        source_contracts = []
        for _, step in toolchain:
            assert "steps.reuse.outputs.reuse != 'true'" in step["if"]
            assert "steps.sync.outputs.clean != 'true'" in step["if"]
            source_contracts.append(str(step.get("uses", "rustup")))
        contracts.append(source_contracts)

    assert contracts[0] == contracts[1]
    assert contracts[2] == [
        item
        for item in contracts[0]
        if not item.startswith("actions/setup-python@")
    ]


def test_hosted_setup_skips_unowned_language_toolchains() -> None:
    """Routine jobs only install product toolchains their plan will use."""
    root = ci_steps(
        (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    root_steps = {str(step.get("name")): step for step in root}
    for name in (
        "Set up pnpm 11.22.0",
        "Set up Node.js 24",
        "Set up Rust 1.98.0",
    ):
        assert (
            "steps.effective.outputs.suite == 'full'" in root_steps[name]["if"]
        )

    template_source = (
        REPO_ROOT / "template/.github/workflows/ci.yml.jinja"
    ).read_text(encoding="utf-8")
    rendered = (
        Environment(
            autoescape=False,  # noqa: S701 - trusted local YAML template
            undefined=StrictUndefined,
        )
        .from_string(template_source)
        .render(
            languages=["python", "typescript", "rust"],
            python_support_mode="latest",
            python_min_version="3.12",
        )
    )
    generated = {str(step.get("name")): step for step in ci_steps(rendered)}
    for name in (
        "Set up Python 3.14",
        "Set up pnpm 11.22.0",
        "Set up Node.js 24",
    ):
        condition = generated[name]["if"]
        assert "steps.plan.outputs.run_project == 'true'" in condition
        assert "steps.plan.outputs.run_osv == 'true'" in condition
    rust_condition = generated["Set up Rust 1.98.0"]["if"]
    assert "steps.plan.outputs.run_project == 'true'" in rust_condition
    assert "steps.plan.outputs.run_osv" not in rust_condition


def test_root_full_tier_prepares_go_without_changing_evidence() -> None:
    """Bootstrap Go on main before a delivery branch can require it."""
    steps = ci_steps(
        (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    names = [str(step.get("name", "")) for step in steps]
    go = steps[names.index("Set up Go 1.27.1")]
    execute = next(
        index
        for index, name in enumerate(names)
        if name.startswith("Execute trusted verification tier=")
    )

    assert names.index("Set up Go 1.27.1") < execute
    assert re.fullmatch(r"actions/setup-go@[0-9a-f]{40}", str(go["uses"])), go[
        "uses"
    ]
    assert go["with"] == {"go-version": "1.27.1", "cache": False}
    assert go["if"] == steps[names.index("Set up Rust 1.98.0")]["if"]
    assert "steps.effective.outputs.suite == 'full'" in go["if"]
    assert steps[execute]["env"]["GOTOOLCHAIN"] == "local"

    for path in (
        "scripts/verification_evidence.py",
        "template/.csarc/scripts/verification_evidence.py",
    ):
        module = runpy.run_path(str(REPO_ROOT / path))
        assert module["toolchain_token"]("Set up Go 1.27.1") is None


def test_reused_release_validation_installs_only_owned_package_tools() -> None:
    """Keep release builds runnable without slowing ordinary evidence reuse."""
    candidate = "startsWith(github.event.pull_request.head.ref, 'release/v')"
    root_steps = {
        str(step.get("name")): step
        for step in ci_steps(
            (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        )
    }
    assert candidate in root_steps["Set up Python 3.14"]["if"]
    assert candidate in root_steps["Set up uv 0.12.15"]["if"]
    for name in (
        "Set up pnpm 11.22.0",
        "Set up Node.js 24",
        "Set up Rust 1.98.0",
    ):
        assert candidate not in root_steps[name]["if"]

    template_source = (
        REPO_ROOT / "template/.github/workflows/ci.yml.jinja"
    ).read_text(encoding="utf-8")
    template = Environment(
        autoescape=False,  # noqa: S701 - trusted local YAML template
        undefined=StrictUndefined,
    ).from_string(template_source)

    for language, expected in (
        ("python", {"Set up Python 3.14", "Set up uv 0.12.15"}),
        ("typescript", {"Set up pnpm 11.22.0", "Set up Node.js 24"}),
        ("rust", {"Set up Rust 1.98.0"}),
    ):
        rendered = template.render(
            languages=[language],
            python_support_mode="latest",
            python_min_version="3.12",
        )
        setup = {
            str(step.get("name")): step
            for step in ci_steps(rendered)
            if str(step.get("name", "")).startswith("Set up ")
        }
        actual = {
            name for name, step in setup.items() if candidate in step["if"]
        }
        assert actual == expected


def test_ci_reuses_only_bound_same_head_evidence_after_sync_preflight() -> None:
    """Keep metadata reuse and clean-sync proof ahead of heavy setup."""
    source = (REPO_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    template_source = (
        REPO_ROOT / "template/.github/workflows/ci.yml.jinja"
    ).read_text(encoding="utf-8")

    preflight = source.index("Validate synchronization structure")
    setup = source.index("Set up Python 3.14")
    execute = source.index("Execute trusted verification tier=")
    assert preflight < setup < execute
    assert "--find-reusable" in source
    assert '--exclude-run-id "$GITHUB_RUN_ID"' in source
    assert "base-sha=${{ steps.identity.outputs.base_sha }}" in source
    assert "- name: Reuse trusted verification" in source
    assert "Trusted verification route evidence" in source
    assert "source_run: $source_run" in source
    assert "steps.reuse.outputs.reuse != 'true'" in source
    assert "steps.sync.outputs.clean != 'true'" in source

    for workflow in (source, template_source):
        reuse_environment = workflow.split(
            "- name: Find reusable trusted verification", 1
        )[1].split("run: |", 1)[0]
        assert "GH_TOKEN:" in reuse_environment
        assert "github.token" in reuse_environment
        reuse_command = workflow.split(
            "- name: Find reusable trusted verification", 1
        )[1].split("- name: Validate trusted clean sync", 1)[0]
        assert (
            'if ! python3 "$RUNNER_TEMP/trusted-verification/' in reuse_command
        )
        assert "running the exact candidate instead" in reuse_command
        reuse_step = workflow.split("- name: Reuse trusted verification", 1)[
            1
        ].split("- name: Set up Python", 1)[0]
        assert (
            "::notice title=Trusted verification route evidence::" in reuse_step
        )
        assert "SOURCE_RUN:" in reuse_step
        assert "SOURCE_JOB:" in reuse_step
        assert "SOURCE_CHECK:" in reuse_step
        sync_step = workflow.split("- name: Validate trusted clean sync", 1)[
            1
        ].split("- name: Reuse trusted verification", 1)[0]
        assert (
            "::notice title=Trusted verification route evidence::" in sync_step
        )
        assert "MAIN_SHA:" in sync_step
        assert 'kind: "sync"' in sync_step


def test_verifiers_do_not_call_removed_attestation_helpers() -> None:
    """Keep generated-project verification free of removed legacy scripts."""
    sources = (
        REPO_ROOT / "scripts/verify-stage-regression-tests",
        REPO_ROOT / "template/.csarc/scripts/verify.jinja",
    )

    for path in sources:
        source = path.read_text(encoding="utf-8")
        assert "test-verify-attestation" not in source
        assert "write-verify-attestation" not in source


def test_documentation_tier_validates_the_generated_site() -> None:
    """Documentation-only changes still verify their built artifact."""
    root_fast = (REPO_ROOT / "scripts/verify-fast").read_text(encoding="utf-8")
    template_fast = (
        REPO_ROOT / "template/.csarc/scripts/verify-fast.jinja"
    ).read_text(encoding="utf-8")

    assert "./scripts/build-repo-site --check" in root_fast
    assert "./.csarc/scripts/build-repo-site --check" in template_fast


def test_local_verification_reuses_the_hosted_path_planner() -> None:
    """Local evidence is appended to the same planner and runner path."""
    for path, planner, recorder in (
        ("scripts/verify-fast", "python3 scripts/ci_tier.py", None),
        (
            "template/.csarc/scripts/verify-fast.jinja",
            "python3 .csarc/scripts/ci_tier.py",
            "python3 .csarc/scripts/local_verification.py record",
        ),
    ):
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert planner in source
        assert 'git merge-base "$base_ref" HEAD' in source
        assert "git diff --no-renames --name-only" in source
        assert '--extra-scopes "$extra_scopes"' in source
        assert "write-verify-attestation" not in source
        if recorder is not None:
            assert recorder in source


def test_workflow_scope_runs_the_actions_security_audit() -> None:
    """A fast workflow change must not wait for a later full boundary."""
    root_fast = (REPO_ROOT / "scripts/verify-fast").read_text(encoding="utf-8")
    generated_fast = (
        REPO_ROOT / "template/.csarc/scripts/verify-fast.jinja"
    ).read_text(encoding="utf-8")
    generated_full = (
        REPO_ROOT / "template/.csarc/scripts/verify.jinja"
    ).read_text(encoding="utf-8")

    assert 'if [[ "$scopes" == *,workflow,* ]]; then' in root_fast
    assert "./scripts/verify-stage-github-actions-audit" in root_fast
    assert (
        "python3 .csarc/scripts/check_action_pins.py --root ." in generated_fast
    )
    assert (
        "python3 .csarc/scripts/check_action_pins.py --root ." in generated_full
    )


def test_full_dispatch_skips_redundant_fast_checks() -> None:
    """A local full request delegates before checks owned by full."""
    for path, full_command in (
        ("scripts/verify-fast", "./scripts/verify-template.sh"),
        (
            "template/.csarc/scripts/verify-fast.jinja",
            "./.csarc/scripts/verify",
        ),
    ):
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert source.index(full_command) < source.index(
            'verification_step "Changed-tree hygiene"'
        )


def test_mixed_scope_pull_requests_still_catch_docs_staleness() -> None:
    """Docs checks follow scope in both docs-only and mixed fast work."""
    root_fast = (REPO_ROOT / "scripts/verify-fast").read_text(encoding="utf-8")
    template_fast = (
        REPO_ROOT / "template/.csarc/scripts/verify-fast.jinja"
    ).read_text(encoding="utf-8")

    for source, specification_check, staleness_check in (
        (
            root_fast,
            "python3 scripts/spec_to_issue.py validate",
            "./scripts/build-repo-site --check",
        ),
        (
            template_fast,
            "python3 .csarc/scripts/spec_to_issue.py validate",
            "./.csarc/scripts/build-repo-site --check",
        ),
    ):
        gate_start = source.index('if [[ "$scopes" == *,docs,* ]]; then')
        gate_end = source.index("\nfi", gate_start)
        gate = source[gate_start:gate_end]

        assert specification_check in gate
        assert staleness_check in gate


def test_routine_verification_does_not_render_a_generated_project() -> None:
    """Keep real Copier create, adopt, and update work in the full suite."""
    source = (REPO_ROOT / "scripts/verify-fast").read_text(encoding="utf-8")

    assert "copier copy" not in source
    assert "read_generated_languages" not in source


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


def test_package_smoke_ignores_stale_dist_wheels(tmp_path: Path) -> None:
    """Run only the wheel produced by this package-smoke invocation."""
    root = tmp_path / "repo"
    scripts = root / "scripts"
    tools = tmp_path / "bin"
    temporary = tmp_path / "tmp"
    scripts.mkdir(parents=True)
    tools.mkdir()
    temporary.mkdir()
    for name in (
        "resolve-cache-root",
        "verification-step",
        "verify-stage-package-smoke",
    ):
        shutil.copy2(REPO_ROOT / "scripts" / name, scripts / name)

    dist = root / "dist"
    dist.mkdir()
    stale = dist / "csarc_repo_template-0.23.0-py3-none-any.whl"
    current = dist / "csarc_repo_template-0.24.2-py3-none-any.whl"
    unrelated = dist / "another_project-1.0.0-py3-none-any.whl"
    for path in (stale, current, unrelated):
        path.write_text(path.name, encoding="utf-8")

    uv = tools / "uv"
    uv.write_text(
        """#!/usr/bin/env bash
set -eu
test "$1" = build
test "${2:-}" = --out-dir
mkdir -p "$3"
touch "$3/csarc_repo_template-0.24.2-py3-none-any.whl"
if [[ "${SMOKE_SECOND_WHEEL:-}" == 1 ]]; then
  touch "$3/another_project-1.0.0-py3-none-any.whl"
fi
""",
        encoding="utf-8",
    )
    uvx = tools / "uvx"
    uvx.write_text(
        """#!/usr/bin/env bash
set -eu
test "$1" = --from
printf '%s\n' "$2" >"$SMOKE_WHEEL_LOG"
test "$(basename "$2")" = csarc_repo_template-0.24.2-py3-none-any.whl
""",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    uvx.chmod(0o755)

    environment = os.environ.copy()
    environment["PATH"] = f"{tools}:{environment['PATH']}"
    environment["TMPDIR"] = str(temporary)
    environment["CSARC_CACHE_ROOT"] = str(tmp_path / "cache")
    wheel_log = tmp_path / "selected-wheel"
    environment["SMOKE_WHEEL_LOG"] = str(wheel_log)
    success = subprocess.run(  # noqa: S603 - isolated test-owned scripts
        [scripts / "verify-stage-package-smoke"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert success.returncode == 0, success.stderr
    selected = Path(wheel_log.read_text(encoding="utf-8").strip())
    assert selected.name == "csarc_repo_template-0.24.2-py3-none-any.whl"
    assert selected.parent != dist
    assert not selected.exists()
    assert all(path.is_file() for path in (stale, current, unrelated))

    wheel_log.unlink()
    environment["SMOKE_SECOND_WHEEL"] = "1"
    ambiguous = subprocess.run(  # noqa: S603 - isolated test-owned scripts
        [scripts / "verify-stage-package-smoke"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert ambiguous.returncode != 0
    assert "FAILED Locate exactly one built wheel" in ambiguous.stderr
    assert not wheel_log.exists()


def test_verification_step_never_runs_the_callers_exit_trap() -> None:
    """Stopping the heartbeat must not delete the caller's artifacts (#1014).

    The forked heartbeat briefly inherits the caller's EXIT trap; bash 5.2
    runs it on SIGTERM, so a fast step followed by `kill` could `rm -rf` the
    wheel the next step needs. The loop reproduces that on bash 5.2, and the
    source assertion keeps the uncatchable signal on newer bash where the
    window does not open.
    """
    for helper in (
        REPO_ROOT / "scripts" / "verification-step",
        REPO_ROOT / "template" / ".csarc" / "scripts" / "verification-step",
    ):
        source = helper.read_text(encoding="utf-8")
        assert 'kill -KILL "$heartbeat_pid"' in source
        assert 'kill "$heartbeat_pid"' not in source

    script = """
source "$1"
gone=0
for _ in $(seq 100); do
  if ! (
    d="$(mktemp -d)"
    trap 'rm -rf "$d"' EXIT
    touch "$d/wheel"
    verification_step "Locate" test -f "$d/wheel" >/dev/null
    test -f "$d/wheel"
  ); then
    gone=$((gone + 1))
  fi
done
echo "gone=$gone"
"""
    bash = shutil.which("bash")
    assert bash is not None
    result = subprocess.run(  # noqa: S603 - test-owned helper and script
        [
            bash,
            "-c",
            script,
            "bash",
            str(REPO_ROOT / "scripts" / "verification-step"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "gone=0"


def test_verification_entry_points_use_shared_step_reporting() -> None:
    """Keep every long local verification path observable."""
    entries = (
        REPO_ROOT / "scripts/verify-fast",
        REPO_ROOT / "template/.csarc/scripts/verify-fast.jinja",
        REPO_ROOT / "template/.csarc/scripts/verify.jinja",
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
        "template/.csarc/scripts/verify-fast.jinja"
    )
    generated_release = direct_regression_commands(
        "template/.csarc/scripts/verify.jinja"
    )

    assert root_issue == generated_issue
    assert root_issue <= root_release
    assert generated_issue <= generated_release


def test_long_policy_regressions_run_only_in_full() -> None:
    """Keep shell lifecycle integration out of the bounded fast path."""
    expected = {
        "./scripts/test-issue-triage",
        "./scripts/test-pr-policy",
        "./scripts/test-worktree-cleanup",
    }
    for path in (
        "scripts/verify-fast",
        "template/.csarc/scripts/verify-fast.jinja",
    ):
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert expected.isdisjoint(
            re.findall(r"\./scripts/test-[A-Za-z0-9-]+", source)
        )

    assert expected <= direct_regression_commands(
        "scripts/verify-stage-regression-tests"
    )
    assert expected <= direct_regression_commands(
        "template/.csarc/scripts/verify.jinja"
    )


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
