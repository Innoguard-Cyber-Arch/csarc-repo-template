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
    ("base", "head", "labels", "reason"),
    [
        ("main", "dev/m7-ci", set(), "delivery promotion"),
        ("main", "fix/9-outage", {"hotfix"}, "hotfix to main"),
        (
            "main",
            "fix/321-recover-v012-release",
            {"release-recovery"},
            "release recovery to main",
        ),
    ],
)
def test_promotion_and_hotfix_use_full_tier(
    base: str, head: str, labels: set[str], reason: str
) -> None:
    """Run the complete matrix at every delivery route that can change main."""
    plan = classify("pull_request", base, head, labels, ["src/pkg/core.py"])
    assert plan.tier == "full"
    assert plan.reason == reason
    assert plan.run_governance and plan.run_osv and plan.run_zizmor
    assert plan.upload_site == (reason == "delivery promotion")


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
    assert (issue.stage, issue.tier) == ("issue", "fast")
    assert (integrated.stage, integrated.tier) == ("integrated", "full")
    assert integrated.reason.startswith("direct-to-main risk:")


@pytest.mark.parametrize(
    "path",
    [
        "scripts/ci_tier.py",
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
    assert scheduled.run_deep and release.run_deep


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
            "${{ needs.fast.outputs.run_deep == 'true' }}"
        )


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
