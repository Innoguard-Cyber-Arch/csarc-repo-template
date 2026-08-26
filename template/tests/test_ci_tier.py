"""Tests for change-aware CI routing."""

from __future__ import annotations

import runpy
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts" / "ci_tier.py"))
classify = MODULE["classify"]
scope_for = MODULE["scope_for"]
risks_for = MODULE["risks_for"]


def git(root: Path, *arguments: str, capture: bool = False) -> str:
    """Run Git in a disposable test repository."""
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(root), *arguments],  # noqa: S607
        check=True,
        capture_output=capture,
        text=True,
    ).stdout


def run_required_aggregate(
    **overrides: str,
) -> subprocess.CompletedProcess[str]:
    """Execute the rendered aggregate gate with controlled routing outputs."""
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    )
    environment = {
        "FAST_RESULT": "success",
        "TIER": "fast",
        "RUN_DEEP": "false",
        "RUN_ADOPTION_MACOS": "false",
        "RUN_GOVERNANCE": "false",
        "RUN_OSV": "false",
        "RUN_ZIZMOR": "false",
        "REVIEW_STATE": "ready",
        "CANONICAL_RESULT": "skipped",
        "FULL_RESULT": "skipped",
        "ADOPTION_MACOS_RESULT": "skipped",
        "GOVERNANCE_RESULT": "skipped",
        "OSV_RESULT": "skipped",
        "PYTHON_COMPATIBILITY_RESULT": "skipped",
        "TYPESCRIPT_RESULT": "skipped",
        "ZIZMOR_RESULT": "skipped",
        "RUN_CONTAINER": "false",
        "CONTAINER_RESULT": "skipped",
    }
    environment.update(overrides)
    return subprocess.run(  # noqa: S603
        [
            "/bin/bash",
            "-eu",
            "-o",
            "pipefail",
            "-c",
            workflow["jobs"]["verify"]["steps"][0]["run"],
        ],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )


@pytest.mark.parametrize(
    ("path", "scope"),
    [
        ("docs/guide.md", "docs"),
        ("site/app.js", "docs"),
        ("template/site/styles.css", "docs"),
        (".github/ISSUE_TEMPLATE/work-item.yml", "docs"),
        (".gitignore", "source"),
        ("README.md", "docs"),
        ("src/pkg/core.py", "source"),
        ("template/README.md.jinja", "template"),
        (".github/workflows/ci.yml", "workflow"),
        ("template/.github/workflows/ci.yml.jinja", "workflow"),
        (".github/actions/setup/action.yml", "workflow"),
        ("scripts/verify-fast", "shell"),
        ("scripts/apply-repository-settings.sh", "governance"),
        ("scripts/check-governance-drift", "governance"),
        ("template/scripts/verify.jinja", "shell"),
        ("uv.lock", "dependency"),
        ("template/pyproject.toml.jinja", "dependency"),
        ("template/.github/dependabot.yml.jinja", "dependency"),
        ("policies/rulesets.json", "governance"),
        ("template/policies/rulesets.json.jinja", "governance"),
        ("unexpected.bin", "unknown"),
    ],
)
def test_scope_for(path: str, scope: str) -> None:
    """Classify every governed change family."""
    assert scope_for(path) == scope


def test_docs_only_uses_docs_tier() -> None:
    """Documentation does not start language or generator matrices."""
    plan = classify(
        "pull_request", "main", "docs/9-guide", set(), ["README.md"]
    )
    assert plan.tier == "docs"
    assert not plan.run_osv
    assert not plan.run_zizmor


@pytest.mark.parametrize(
    "path",
    [
        "site/app.js",
        "docs/site-content.js",
        "scripts/render_site.py",
        "template/site/index.html.jinja",
        "template/docs/site-theme.css.jinja",
    ],
)
def test_site_changes_publish_the_decision_artifact(path: str) -> None:
    """Publish the bundle only when its source or project content changes."""
    plan = classify("pull_request", "main", "docs/9-site", set(), [path])
    assert plan.upload_site


def test_unrelated_documentation_does_not_publish_the_site() -> None:
    """Ordinary documentation keeps the fast runner artifact-free."""
    plan = classify(
        "pull_request", "main", "docs/9-guide", set(), ["README.md"]
    )
    assert not plan.upload_site


def test_issue_form_and_gitignore_do_not_fall_through_to_full() -> None:
    """Known low-risk repository metadata receives an explicit cheap tier."""
    issue_form = classify(
        "pull_request",
        "main",
        "docs/9-form",
        set(),
        [".github/ISSUE_TEMPLATE/work-item.yml"],
    )
    gitignore = classify(
        "pull_request",
        "main",
        "chore/9-ignore",
        set(),
        [".gitignore"],
    )
    assert issue_form.tier == "docs"
    assert gitignore.tier == "fast"


def test_source_uses_fast_canonical_runtime() -> None:
    """Ordinary code receives the non-trivial fast verification tier."""
    plan = classify(
        "pull_request", "dev/m7-ci", "feat/9-code", set(), ["src/pkg/core.py"]
    )
    assert plan.tier == "fast"
    assert plan.scopes == ("source",)
    assert plan.review_state == "ready"


@pytest.mark.parametrize(
    ("changed_files", "risk_flags"),
    [
        (["uv.lock"], (False, True, False)),
        (["policies/rulesets.json"], (True, False, False)),
        (
            ["policies/rulesets.json", "uv.lock", ".github/workflows/ci.yml"],
            (True, True, True),
        ),
    ],
)
def test_draft_defers_full_but_keeps_targeted_risk_checks(
    changed_files: list[str], risk_flags: tuple[bool, bool, bool]
) -> None:
    """Draft WIP records pending full verification without hiding its scope."""
    plan = classify(
        "pull_request",
        "main",
        "dev/m7-ci",
        {"promotion"},
        changed_files,
        draft=True,
    )
    assert plan.tier == "fast"
    assert plan.review_state == "draft"
    assert plan.reason == (
        "draft work in progress; full verification deferred until ready"
    )
    assert (plan.run_governance, plan.run_osv, plan.run_zizmor) == risk_flags


@pytest.mark.parametrize(
    ("path", "flag"),
    [
        (".github/workflows/ci.yml", "run_zizmor"),
        ("uv.lock", "run_osv"),
        ("policies/rulesets.json", "run_governance"),
    ],
)
def test_risk_scopes_enable_only_their_expensive_check(
    path: str, flag: str
) -> None:
    """Keep unrelated security and remote checks out of ordinary PRs."""
    plan = classify(
        "pull_request", "dev/m9-staged-ci", "chore/9-change", set(), [path]
    )
    assert plan.tier == "fast"
    assert getattr(plan, flag)


@pytest.mark.parametrize(
    "path",
    [
        "scripts/apply-repository-settings.sh",
        "scripts/check-governance-drift",
    ],
)
def test_governance_checkers_run_only_remote_governance(path: str) -> None:
    """Route governance checkers without unrelated security scans."""
    plan = classify(
        "pull_request", "dev/m9-staged-ci", "fix/276-route", set(), [path]
    )
    assert plan.tier == "fast"
    assert plan.scopes == ("governance",)
    assert plan.run_governance
    assert not plan.run_osv
    assert not plan.run_zizmor


@pytest.mark.parametrize(
    ("head", "labels", "reason"),
    [
        ("dev/m7-ci", set(), "delivery promotion"),
        ("fix/9-outage", {"hotfix"}, "hotfix to main"),
        (
            "fix/321-recover-v012-release",
            {"release-recovery"},
            "release recovery to main",
        ),
    ],
)
def test_promotion_and_hotfix_use_full_tier(
    head: str, labels: set[str], reason: str
) -> None:
    """Run canonical verification without unrelated auxiliary matrices."""
    plan = classify("pull_request", "main", head, labels, ["src/pkg/core.py"])
    assert plan.tier == "full"
    assert plan.reason == reason
    assert not any((plan.run_governance, plan.run_osv, plan.run_zizmor))
    assert not plan.run_deep
    assert plan.upload_site == (reason == "delivery promotion")


@pytest.mark.parametrize(
    ("path", "flag"),
    [
        ("policies/rulesets.json", "run_governance"),
        ("uv.lock", "run_osv"),
        (".github/workflows/ci.yml", "run_zizmor"),
    ],
)
def test_hotfix_routes_only_the_relevant_auxiliary_check(
    path: str, flag: str
) -> None:
    """Keep high-risk hotfix checks fail closed without broad fan-out."""
    plan = classify("pull_request", "main", "fix/9-outage", {"hotfix"}, [path])
    flags = {
        "run_governance": plan.run_governance,
        "run_osv": plan.run_osv,
        "run_zizmor": plan.run_zizmor,
    }
    assert plan.tier == "full"
    assert flags[flag]
    assert sum(flags.values()) == 1


def test_unknown_and_missing_paths_fail_safe_to_full() -> None:
    """Do not treat an unclassified non-trivial change as cheap."""
    assert (
        classify(
            "pull_request", "main", "feat/9-change", set(), ["unknown.bin"]
        ).tier
        == "full"
    )
    assert (
        classify("pull_request", "main", "feat/9-change", set(), []).tier
        == "full"
    )


@pytest.mark.parametrize(
    "path",
    [
        ".release-please-manifest.json",
        "release-please-config.json",
        "version.txt",
        "template/.release-please-manifest.json",
        "template/release-please-config.json.jinja",
        "template/version.txt",
    ],
)
def test_release_version_metadata_stays_fail_closed(path: str) -> None:
    """Do not downgrade unclassified release state to a routine tier."""
    plan = classify("pull_request", "main", "chore/9-release", set(), [path])
    assert plan.tier == "full"
    assert not plan.upload_site


def test_push_does_not_repeat_the_verified_source_tree() -> None:
    """A merged tree records post-merge evidence without another full suite."""
    plan = classify("push", "", "", set(), ["src/pkg/core.py"])
    assert plan.tier == "post-merge"
    assert plan.stage == "post-merge"
    assert not plan.run_deep


def test_manual_and_merge_queue_runs_are_full() -> None:
    """Explicit and queued candidates retain the complete gate."""
    manual = classify(
        "workflow_dispatch", "", "", set(), ["README.md"], force_full=True
    )
    queued = classify("merge_group", "main", "queue", set(), ["README.md"])
    assert manual.tier == queued.tier == "full"
    assert manual.upload_site


@pytest.mark.parametrize(
    ("path", "risk"),
    [
        ("scripts/ci_tier.py", "ci-router"),
        (".github/workflows/governance-comment.yml", "workflow"),
        (".github/actions/setup/action.yml", "workflow"),
        (".github/CODEOWNERS", "governance"),
        ("policies/rulesets.json", "governance"),
        ("pyproject.toml", "test-harness"),
        ("copier.yml", "generator"),
        ("src/csarc_cli/cli.py", "cli-adoption-update"),
        (".github/workflows/release-template.yml", "release"),
        (".github/dependabot.yml", "security"),
        ("uv.lock", "security"),
        ("scripts/promotion_gate.py", "promotion"),
        ("scripts/verify_release_consumption.py", "provenance"),
        ("unexpected.bin", "unknown"),
    ],
)
def test_high_risk_families_are_explicit(path: str, risk: str) -> None:
    """Keep costly or security-sensitive families out of cheap docs routing."""
    assert risk in risks_for(path)


def test_issue_and_integrated_stages_apply_risk_differently() -> None:
    """Issue work stays scoped while the exact main candidate fails closed."""
    issue = classify(
        "pull_request",
        "dev/m9-low-friction-ai-sdlc",
        "enhancement/317-staged-verification",
        set(),
        ["src/csarc_cli/cli.py"],
    )
    integrated = classify(
        "pull_request",
        "main",
        "enhancement/317-staged-verification",
        set(),
        ["src/csarc_cli/cli.py"],
    )
    sync = classify(
        "pull_request",
        "dev/m9-low-friction-ai-sdlc",
        "sync/main-to-m9-low-friction-ai-sdlc-abcdef012345",
        set(),
        ["README.md"],
    )
    mismatched_sync = classify(
        "pull_request",
        "dev/m9-low-friction-ai-sdlc",
        "sync/main-to-m8-other-abcdef012345",
        set(),
        ["README.md"],
    )
    assert (issue.stage, issue.tier) == ("issue", "fast")
    assert (sync.stage, sync.tier, sync.reason) == (
        "sync",
        "fast",
        "reviewed main sync",
    )
    assert (mismatched_sync.stage, mismatched_sync.tier) == ("issue", "docs")
    assert (integrated.stage, integrated.tier) == ("integrated", "full")
    assert integrated.reason.startswith("direct-to-main risk:")


@pytest.mark.parametrize(
    ("path", "runtime", "adoption"),
    [
        ("src/csarc_cli/cli.py", True, True),
        ("copier.yml", True, True),
        (".github/workflows/release-template.yml", True, False),
        ("uv.lock", False, False),
        ("scripts/ci_tier.py", True, False),
        ("scripts/promotion_gate.py", True, False),
    ],
)
@pytest.mark.parametrize("base", ["dev/m9-staged-ci", "main"])
def test_ready_high_risk_work_runs_related_deep_checks(
    path: str, runtime: bool, adoption: bool, base: str
) -> None:
    """Route only the runtime or adoption lane that can expose each risk."""
    plan = classify(
        "pull_request", base, "type/317-staged-verification", set(), [path]
    )
    assert plan.run_deep is runtime
    assert plan.run_adoption_macos is adoption


def test_unrelated_issue_risks_do_not_start_the_deep_matrix() -> None:
    """Keep workflow and governance checks in their dedicated lanes."""
    for path in (".github/workflows/ci.yml", "policies/rulesets.json"):
        plan = classify(
            "pull_request",
            "dev/m9-staged-ci",
            "type/317-staged-verification",
            set(),
            [path],
        )
        assert not plan.run_deep
        assert not plan.run_adoption_macos


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        ".github/dependabot.yml",
        "SECURITY.md",
        "scripts/promotion_gate.py",
    ],
)
def test_router_security_and_promotion_do_not_start_macos(path: str) -> None:
    """Keep adoption E2E exclusive to generator and CLI adoption risks."""
    plan = classify(
        "pull_request",
        "dev/m9-staged-ci",
        "type/317-staged-verification",
        set(),
        [path],
    )
    assert not plan.run_adoption_macos


@pytest.mark.parametrize(
    "path",
    [
        "scripts/ci_tier.py",
        ".github/workflows/governance-comment.yml",
        ".github/actions/setup/action.yml",
        ".github/CODEOWNERS",
        "policies/rulesets.json",
        "pyproject.toml",
        "copier.yml",
        "src/csarc_cli/cli.py",
        ".github/workflows/release-template.yml",
        "uv.lock",
        "scripts/promotion_gate.py",
        "scripts/verify_release_consumption.py",
    ],
)
def test_direct_main_risk_families_fail_closed(path: str) -> None:
    """Escalate bot and standalone main routes when their risk is elevated."""
    plan = classify(
        "pull_request", "main", "dependabot/or-standalone", set(), [path]
    )
    assert plan.tier == "full"
    assert plan.stage == "integrated"


def test_schedule_and_release_run_the_deep_matrix() -> None:
    """Reserve long cross-platform checks for scheduled and release stages."""
    scheduled = classify("schedule", "", "", set(), ["README.md"])
    release = classify(
        "pull_request",
        "main",
        "release-please--branches--main",
        set(),
        [".release-please-manifest.json"],
    )
    assert scheduled.tier == release.tier == "full"
    assert scheduled.run_deep and scheduled.run_adoption_macos
    assert release.run_deep and not release.run_adoption_macos
    assert all(
        (
            scheduled.run_governance,
            scheduled.run_osv,
            scheduled.run_zizmor,
        )
    )


def test_draft_release_defers_the_deep_matrix() -> None:
    """Draft release work must not start long-running platform coverage."""
    plan = classify(
        "pull_request",
        "main",
        "release-please--branches--main",
        set(),
        [".release-please-manifest.json"],
        draft=True,
    )
    assert plan.tier == "fast"
    assert not plan.run_deep


def test_pytest_profiles_are_declared_strictly() -> None:
    """Reject unknown test profiles instead of silently broadening a gate."""
    pytest_config = tomllib.loads((ROOT / "pyproject.toml").read_text())[
        "tool"
    ]["pytest"]["ini_options"]
    assert "--strict-markers" in pytest_config["addopts"]
    assert {item.split(":", 1)[0] for item in pytest_config["markers"]} == {
        "large",
        "runtime",
        "quarantine",
    }


def test_required_aggregate_is_unconditional_and_routing_is_job_level() -> None:
    """Conclude the stable check while expensive jobs remain conditional."""
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    )
    workflow_source = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "git diff --no-renames --name-only -z" in workflow_source
    jobs = workflow["jobs"]
    assert jobs["verify"]["if"] == "${{ always() }}"
    assert "fast" in jobs["verify"]["needs"]
    full_job = next(
        name for name in ("canonical-full", "canonical", "full") if name in jobs
    )
    assert jobs[full_job]["if"] == ("${{ needs.fast.outputs.tier == 'full' }}")
    aggregate = jobs["verify"]["steps"][0]
    assert aggregate["env"]["RUN_GOVERNANCE"] == (
        "${{ needs.fast.outputs.run_governance }}"
    )
    assert aggregate["env"]["RUN_OSV"] == "${{ needs.fast.outputs.run_osv }}"
    assert aggregate["env"]["RUN_ZIZMOR"] == (
        "${{ needs.fast.outputs.run_zizmor }}"
    )
    assert aggregate["run"].count("require_routed") >= 4
    if "adoption-macos" in jobs:
        assert jobs["adoption-macos"]["if"] == (
            "${{ needs.fast.outputs.run_adoption_macos == 'true' }}"
        )
        assert aggregate["env"]["RUN_ADOPTION_MACOS"] == (
            "${{ needs.fast.outputs.run_adoption_macos }}"
        )
        assert (
            'require_routed "$RUN_ADOPTION_MACOS" '
            '"$ADOPTION_MACOS_RESULT"' in aggregate["run"]
        )
    if "python-compatibility" in jobs:
        assert jobs["python-compatibility"]["if"] == (
            "${{ needs.fast.outputs.run_deep == 'true' }}"
        )
        assert aggregate["env"]["RUN_DEEP"] == (
            "${{ needs.fast.outputs.run_deep }}"
        )
        assert (
            'require_routed "$RUN_DEEP" "$PYTHON_COMPATIBILITY_RESULT"'
            in aggregate["run"]
        )


def test_required_aggregate_accepts_explicit_routing() -> None:
    """Accept only a complete, explicit fast-route result."""
    assert run_required_aggregate().returncode == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("TIER", ""),
        ("TIER", "fas"),
        ("REVIEW_STATE", ""),
        ("REVIEW_STATE", "unknown"),
        ("RUN_DEEP", ""),
        ("RUN_DEEP", "tru"),
        ("RUN_ADOPTION_MACOS", ""),
        ("RUN_ADOPTION_MACOS", "tru"),
        ("RUN_GOVERNANCE", ""),
        ("RUN_OSV", "tru"),
        ("RUN_ZIZMOR", "0"),
    ],
)
def test_required_aggregate_rejects_unknown_routing_outputs(
    field: str, value: str
) -> None:
    """Fail closed when a routing output is empty or malformed."""
    result = run_required_aggregate(**{field: value})
    assert result.returncode != 0
    assert (
        "invalid" in result.stderr or "must be true or false" in result.stderr
    )


def test_pr_metadata_edits_validate_without_restarting_product_ci() -> None:
    """Keep metadata validation separate from exact-tree verification."""
    ci_workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    )
    policy_workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "pr-policy.yml").read_text()
    )
    ci_triggers = ci_workflow.get("on", ci_workflow.get(True))
    policy_triggers = policy_workflow.get("on", policy_workflow.get(True))
    assert "edited" not in ci_triggers["pull_request"]["types"]
    assert "edited" in policy_triggers["pull_request"]["types"]


def test_governance_checks_the_candidate_revision() -> None:
    """Never validate governance policy from the pull request base revision."""
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    )
    checkout = workflow["jobs"]["governance"]["steps"][0]
    assert checkout["with"]["ref"] == (
        "${{ github.event.pull_request.head.sha || "
        "github.event.merge_group.head_sha || github.sha }}"
    )


def test_reusable_ci_routes_the_runtime_matrix_explicitly() -> None:
    """Let callers request compatibility without duplicating canonical full."""
    path = ROOT / ".github" / "workflows" / "reusable-ci.yml"
    if not path.exists():
        pytest.skip("generated projects consume the repository workflow")
    workflow = yaml.safe_load(path.read_text())
    jobs = workflow["jobs"]
    assert jobs["python-compatibility"]["if"] == (
        "contains(inputs.language-profile, 'python') && "
        "inputs.run-runtime-matrix"
    )
    aggregate = jobs["verify"]["steps"][0]
    assert aggregate["env"]["RUN_RUNTIME_MATRIX"] == (
        "${{ inputs.run-runtime-matrix }}"
    )
    assert '"$RUN_RUNTIME_MATRIX" == true' in aggregate["run"]


def test_runtime_lane_installs_and_imports_the_built_package() -> None:
    """Catch runtime packaging failures without repeating the full suite."""
    generated_verifier = ROOT / "scripts" / "verify"
    if generated_verifier.exists():
        command = generated_verifier.read_text(encoding="utf-8")
    else:
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        )
        command = next(
            step["run"]
            for step in workflow["jobs"]["python-compatibility"]["steps"]
            if step.get("name") == "Run runtime-sensitive tests"
        )
    assert "uv build --clear" in command
    assert "--with ./dist/*.whl" in command
    assert 'python -c "import ' in command
    if generated_verifier.exists():
        assert "twine check dist/*" in command
    else:
        assert "csarc --help" in command


def test_changed_path_discovery_exposes_both_sides_of_a_rename(
    tmp_path: Path,
) -> None:
    """A sensitive file renamed under docs must retain its original risk."""
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "CI Test")
    git(tmp_path, "config", "user.email", "ci@example.invalid")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "docs").mkdir()
    git(tmp_path, "mv", ".github/workflows/ci.yml", "docs/ci.yml")
    changed = git(
        tmp_path, "diff", "--no-renames", "--name-only", "HEAD", capture=True
    ).splitlines()
    assert set(changed) == {".github/workflows/ci.yml", "docs/ci.yml"}
    assert "ci-router" in risks_for(changed[0])


def test_generated_fast_gate_excludes_large_tests() -> None:
    """Generated Issue gates must share the root large-test boundary."""
    command = (ROOT / "scripts" / "verify-fast").read_text()
    assert 'uv run pytest -m "not large"' in command


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("CSARC_CI_TIER", "quick"),
        ("CSARC_CI_SCOPES", "source,unknown"),
        ("CSARC_CI_RISKS", "generator,mystery"),
    ],
)
def test_fast_gate_rejects_unknown_plan_values(
    variable: str, value: str
) -> None:
    """Do not broaden malformed CI plans into an all-tests fallback."""
    environment = {
        "CSARC_CI_TIER": "fast",
        "CSARC_CI_SCOPES": "source",
        "CSARC_CI_RISKS": "",
        variable: value,
    }
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(ROOT / "scripts" / "verify-fast")],
        check=False,
        capture_output=True,
        cwd=ROOT,
        env=environment,
        text=True,
    )
    assert result.returncode == 2
    assert "Unsupported CI" in result.stderr


def test_fast_gate_selects_tests_from_scopes_and_risks() -> None:
    """Keep the routine gate bounded while unioning every affected group."""
    source = (ROOT / "scripts" / "verify-fast").read_text(encoding="utf-8")
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    )
    fast_step = next(
        step
        for step in workflow["jobs"]["fast"]["steps"]
        if step.get("name") == "Run change-aware checks"
    )
    assert fast_step["env"]["CSARC_CI_RISKS"] == (
        "${{ steps.plan.outputs.risks }}"
    )
    assert 'uv run pytest -m "not large" "${test_paths[@]}"' in source
    assert "source) add_tests tests ;;" in source
    for scope in ("docs", "template", "workflow", "governance", "dependency"):
        assert f"    {scope})" in source


@pytest.mark.parametrize(
    "path",
    [
        "scripts/check-update-conflicts",
        "scripts/check-project-metadata.py",
        "scripts/delivery_sync.py",
        "scripts/pr_lifecycle.py",
        "template/scripts/verify.jinja",
    ],
)
def test_verifier_changes_are_explicit_risks(path: str) -> None:
    """Prevent verifier changes from silently bypassing escalation rules."""
    assert "verifier" in risks_for(path)


def test_post_merge_checks_identity_without_repeating_matrix() -> None:
    """Keep post-merge verification focused on tree and provenance identity."""
    workflow = yaml.safe_load(
        (
            ROOT / ".github" / "workflows" / "promotion-post-merge.yml"
        ).read_text()
    )
    commands = "\n".join(
        step.get("run", "") for step in workflow["jobs"]["verify"]["steps"]
    )
    assert "promotion_gate.py verify-main" in commands
    assert "verify-template.sh" not in commands
    assert "pytest" not in commands
