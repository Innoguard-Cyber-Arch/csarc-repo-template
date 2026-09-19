"""Tests for change-aware CI routing."""

from __future__ import annotations

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


def test_workflow_rename_keeps_old_and_new_paths(tmp_path: Path) -> None:
    """A workflow moved into docs must retain its workflow scope."""
    command = 'git diff --no-renames --name-only -z "$BASE_SHA" "$HEAD_SHA"'
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
