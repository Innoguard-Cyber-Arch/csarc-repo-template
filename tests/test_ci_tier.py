"""Tests for change-aware CI routing."""

from __future__ import annotations

import os
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
MODULE = runpy.run_path(str(REPO_ROOT / "scripts" / "ci_tier.py"))
classify = MODULE["classify"]
scope_for = MODULE["scope_for"]


def run_git(repo: Path, *args: str) -> bytes:
    """Run Git in one test repository and return stdout."""
    executable = shutil.which("git")
    assert executable is not None
    return subprocess.run(  # noqa: S603 - fixed executable and test inputs
        [executable, "-C", str(repo), *args],
        check=True,
        capture_output=True,
    ).stdout


@pytest.mark.parametrize(
    ("path", "scope"),
    [
        ("docs/guide.md", "docs"),
        ("site/app.js", "docs"),
        ("template/site/static/styles.css", "docs"),
        (".github/ISSUE_TEMPLATE/feature.yml", "docs"),
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
        ("scripts/request-reviewer", "governance"),
        (".csarc/config.yml", "governance"),
        ("template/scripts/verify.jinja", "shell"),
        ("Cargo.lock", "dependency"),
        ("Cargo.toml", "dependency"),
        ("package-lock.json", "dependency"),
        ("uv.lock", "dependency"),
        ("yarn.lock", "dependency"),
        ("template/pyproject.toml.jinja", "dependency"),
        ("template/.github/dependabot.yml.jinja", "dependency"),
        ("template/pnpm-workspace.yaml", "dependency"),
        ("policies/rulesets.json", "governance"),
        ("policies/releases.json", "governance"),
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
        "docs/site-content.md",
        "scripts/render_site.py",
        "template/site/content/_index.zh-tw.md",
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
        [".github/ISSUE_TEMPLATE/feature.yml"],
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
    plan = classify("pull_request", "main", "chore/9-change", set(), [path])
    assert plan.tier == "fast"
    assert getattr(plan, flag)


@pytest.mark.parametrize(
    "path",
    [
        "copier.yml",
        "profiles/catalog.yaml",
        "src/csarc_cli/cli.py",
        "template/README.md.jinja",
        "scripts/ci_tier.py",
        "scripts/verify-fast",
        "scripts/verify-stage-regression-tests",
        "scripts/verify_attestation.py",
        "template/scripts/verify-fast.jinja",
    ],
)
def test_standalone_generator_and_verifier_changes_require_full(
    path: str,
) -> None:
    """A direct-to-main change has no later promotion boundary."""
    plan = classify("pull_request", "main", "feat/9-change", set(), [path])
    assert plan.tier == "full"
    assert plan.reason == "standalone generator or verifier change"


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        "template/.github/workflows/ci.yml.jinja",
        "scripts/pr_lifecycle.py",
        "template/scripts/pr_lifecycle.py",
    ],
)
def test_standalone_workflows_and_other_scripts_stay_fast(path: str) -> None:
    """Scope-selected checks cover ordinary workflow and script changes."""
    assert (
        classify("pull_request", "main", "chore/9-change", set(), [path]).tier
        == "fast"
    )


def _run_stubbed_verify_fast(
    tmp_path: Path, changed_path: str, *, extra_scopes: str = "source"
) -> tuple[str, str]:
    """Run the real local planner while replacing expensive check bodies."""
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    for name in ("ci_tier.py", "verify-fast"):
        shutil.copy2(REPO_ROOT / "scripts" / name, scripts / name)
    (scripts / "resolve-cache-root").write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$PWD/.cache"\n',
        encoding="utf-8",
    )
    (scripts / "verification-step").write_text(
        'verification_step() { printf "%s\\n" "$*" >> "$CSARC_TEST_LOG"; }\n',
        encoding="utf-8",
    )
    for name in (
        "resolve-cache-root",
        "verify-fast",
    ):
        (scripts / name).chmod(0o755)

    run_git(repo, "init", "-q", "-b", "main")
    run_git(repo, "add", ".")
    run_git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "base",
    )
    run_git(repo, "switch", "-q", "-c", "feat/test-plan")
    run_git(repo, "config", "branch.feat/test-plan.gh-merge-base", "main")
    changed = repo / changed_path
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text("changed\n", encoding="utf-8")
    run_git(repo, "add", changed_path)
    run_git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "change",
    )

    log = tmp_path / "verification.log"
    environment = os.environ.copy()
    for name in (
        "CSARC_CI_BASE",
        "CSARC_CI_DRAFT",
        "CSARC_CI_LABELS",
        "CSARC_CI_TIER",
        "CSARC_RUN_OSV",
        "CSARC_VERIFICATION_SUITE",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "CSARC_CI_SCOPES": extra_scopes,
            "CSARC_CI_TIER": "baseline",
            "CSARC_TEST_LOG": str(log),
            "CSARC_VERIFICATION_SUITE": "baseline",
        }
    )
    result = subprocess.run(  # noqa: S603 - repository-owned entry point
        [scripts / "verify-fast"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return result.stdout, log.read_text(encoding="utf-8")


def test_local_verify_fast_computes_workflow_scope(tmp_path: Path) -> None:
    """A weaker explicit scope cannot suppress workflow-specific checks."""
    output, log = _run_stubbed_verify_fast(tmp_path, ".github/workflows/ci.yml")
    assert "suite=fast scopes=source,workflow" in output
    assert "Workflow and shell lint ./scripts/lint-workflows-shell" in log
    assert (
        "GitHub Actions audit ./scripts/verify-stage-github-actions-audit"
        in log
    )


@pytest.mark.parametrize("lockfile", ["uv.lock", "Cargo.lock"])
def test_local_verify_fast_computes_dependency_scope(
    tmp_path: Path, lockfile: str
) -> None:
    """A dependency lockfile change cannot silently skip the scan."""
    output, log = _run_stubbed_verify_fast(tmp_path, lockfile)
    assert "suite=fast scopes=dependency,source" in output
    assert "Dependency scan ./scripts/verify-dependencies" in log


@pytest.mark.parametrize(
    ("path", "runs_python"),
    [
        ("README.md", False),
        ("uv.lock", False),
        (".github/workflows/ci.yml", True),
        ("src/pkg/core.py", True),
    ],
)
def test_fast_gate_runs_python_only_for_its_risk_owners(
    tmp_path: Path, path: str, runs_python: bool
) -> None:
    """Docs and dependencies skip unrelated Python regression work."""
    _output, log = _run_stubbed_verify_fast(tmp_path, path, extra_scopes="")
    assert ("Bounded Python regression suite" in log) is runs_python


@pytest.mark.parametrize(
    ("path", "extra_scopes", "included", "excluded"),
    [
        (
            ".github/workflows/ci.yml",
            "",
            "tests/test_ci_tier.py",
            "tests/test_cli.py",
        ),
        (
            "scripts/apply-repository-settings.sh",
            "",
            "tests/test_apply_repository_settings.py",
            "tests/test_cli.py",
        ),
        (
            "src/pkg/core.py",
            "",
            "tests/test_cli.py",
            "tests/test_ci_tier.py",
        ),
        (
            "tests/test_pr_lifecycle.py",
            "",
            "tests/test_pr_lifecycle.py",
            "tests/test_ci_tier.py",
        ),
        (
            "README.md",
            "template",
            "tests/test_language_profiles.py",
            "tests/test_release_publish.py",
        ),
    ],
)
def test_fast_gate_selects_only_scope_owner_tests(
    tmp_path: Path,
    path: str,
    extra_scopes: str,
    included: str,
    excluded: str,
) -> None:
    """Execute owner files without falling back to the whole test tree."""
    _output, log = _run_stubbed_verify_fast(
        tmp_path, path, extra_scopes=extra_scopes
    )
    command = next(
        line
        for line in log.splitlines()
        if line.startswith("Bounded Python regression suite ")
    )
    assert included in command
    assert excluded not in command
    assert not command.endswith(" tests")


def test_workflow_rename_keeps_old_and_new_paths(tmp_path: Path) -> None:
    """A workflow moved into docs must retain its workflow scope."""
    command = 'git diff --no-renames --name-only -z "$merge_base" "$HEAD_SHA"'
    workflow = REPO_ROOT / ".github/workflows/ci.yml"
    if not workflow.exists():
        workflow = workflow.with_name("ci.yml.jinja")
    assert command in workflow.read_text(encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init")
    workflow = repo / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\n" + "# padding\n" * 20, encoding="utf-8")
    run_git(repo, "add", ".")
    run_git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-m",
        "base",
    )
    base = run_git(repo, "rev-parse", "HEAD").decode().strip()
    destination = repo / "docs/ci.md"
    destination.parent.mkdir()
    workflow.rename(destination)
    run_git(repo, "add", "-A")
    run_git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-m",
        "rename",
    )

    output = run_git(
        repo,
        "diff",
        "--no-renames",
        "--name-only",
        "-z",
        base,
        "HEAD",
    )
    changed_files = [path.decode() for path in output.split(b"\0") if path]
    plan = classify(
        "pull_request",
        "dev/m14-generated-project-fixes",
        "fix/747-renamed-paths",
        set(),
        changed_files,
    )

    assert set(changed_files) == {".github/workflows/ci.yml", "docs/ci.md"}
    assert plan.scopes == ("docs", "workflow")
    assert plan.tier == "fast"
    assert plan.run_zizmor


@pytest.mark.parametrize(
    "path",
    [
        "scripts/apply-repository-settings.sh",
        "scripts/check-governance-drift",
        "scripts/request-reviewer",
    ],
)
def test_governance_checkers_run_only_remote_governance(path: str) -> None:
    """Route governance checkers without unrelated security scans."""
    plan = classify("pull_request", "main", "fix/276-route", set(), [path])
    assert plan.tier == "fast"
    assert plan.scopes == ("governance",)
    assert plan.run_governance
    assert not plan.run_osv
    assert not plan.run_zizmor


@pytest.mark.parametrize(
    "path",
    ["scripts/verify-dependencies", "scripts/install-osv-scanner"],
)
def test_osv_scripts_trigger_their_own_check_and_shell_validation(
    path: str,
) -> None:
    """Scan and lint changes to the local vulnerability entrypoint."""
    plan = classify("pull_request", "main", "fix/407-osv", set(), [path])
    assert plan.scopes == ("shell",)
    assert plan.run_osv


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


def test_manual_and_merge_queue_runs_are_full() -> None:
    """Explicit and queued candidates retain the complete gate."""
    manual = classify(
        "workflow_dispatch", "", "", set(), ["README.md"], force_full=True
    )
    queued = classify("merge_group", "main", "queue", set(), ["README.md"])
    assert manual.tier == queued.tier == "full"
    assert manual.upload_site


def test_draft_caps_full_work_until_ready() -> None:
    """Draft pushes stay fast and the same ready head returns to full."""
    draft = classify(
        "pull_request",
        "main",
        "dev/m14-ci",
        set(),
        ["src/pkg/core.py"],
        draft=True,
    )
    ready = classify(
        "pull_request",
        "main",
        "dev/m14-ci",
        set(),
        ["src/pkg/core.py"],
    )
    assert draft.tier == "fast"
    assert ready.tier == "full"


def test_clean_sync_requires_explicit_structural_proof() -> None:
    """A sync-like branch name cannot select the cheap route by itself."""
    ordinary = classify(
        "pull_request",
        "dev/m14-ci",
        "sync/main-to-m14-ci-aaaaaaaaaaaa",
        set(),
        [],
    )
    verified = classify(
        "pull_request",
        "dev/m14-ci",
        "sync/main-to-m14-ci-aaaaaaaaaaaa",
        set(),
        [],
        verified_sync=True,
    )
    assert ordinary.tier == "full"
    assert verified.tier == "fast"
