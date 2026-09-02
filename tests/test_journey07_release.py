"""Regression tests for the automatic version and release workflow."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_release_workflow_is_one_capability_aware_pipeline() -> None:
    """Keep candidate creation and publication in one workflow owner."""
    path = ROOT / ".github/workflows/release.yml"
    source = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    triggers = workflow.get("on", workflow.get(True))

    assert triggers == {
        "push": {"branches": ["main"]},
        "workflow_dispatch": None,
    }
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert workflow["jobs"]["release"]["if"] == (
        "${{ github.ref == 'refs/heads/main' }}"
    )
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]["release"]["permissions"]) == {
        "contents",
        "issues",
        "pull-requests",
        "statuses",
    }
    assert workflow["jobs"]["release"]["timeout-minutes"] == 30
    assert "googleapis/release-please-action@45996ed1" in source
    assert "release_policy.py plan" in source
    assert "release_policy.py detect" in source
    assert "mode == 'automatic'" in source
    assert "mode == 'guided'" in source
    assert "mode == 'blocked'" in source
    assert "release_policy.py prepare-candidate" in source
    assert "./scripts/verify-release-candidate" in source
    assert "scripts/release_bundle.py prepare" in source
    assert "scripts/release_bundle.py verify" in source
    assert "releases/assets/$asset_id" in source
    assert "gh release edit" in source
    assert "for attempt in $(seq 1 12)" in source
    assert "gh release verify" in source
    assert "secrets.GITHUB_TOKEN" in source
    assert "PAT" not in source
    assert "create-github-app-token" not in source
    assert "release_policy.py release" not in source
    assert "/actions/workflows/" not in source
    assert "source_run_id" not in source
    # A shell double-quoted --jq argument must escape its own literal quotes,
    # so the merged-commit comparison reads as \"$GITHUB_SHA\" in source.
    assert r".merge_commit_sha == \"$GITHUB_SHA\"" in source
    assert 'jq -r .merge_commit_sha <<<"$pr"' in source

    settings = (ROOT / "scripts/apply-repository-settings.sh").read_text(
        encoding="utf-8"
    )
    assert 'gh api "repos/$repo/immutable-releases"' in settings
    assert '--method PUT "repos/$repo/immutable-releases"' in settings
    assert json.loads(
        (ROOT / "policies/releases.json").read_text(encoding="utf-8")
    ) == {"enabled": True}

    candidate = (ROOT / "scripts/verify-release-candidate").read_text(
        encoding="utf-8"
    )
    assert "release_bundle.py candidate" in candidate
    assert "verify-candidate-version" in candidate
    assert 'base_sha="$(jq -r' in candidate
    assert "./scripts/verify-template.sh" not in candidate
    assert "status=failure\nif (" in candidate
    assert 'publish_status "$status"' in candidate


def test_release_converges_a_repeated_or_concurrent_run_to_one_release() -> (
    None
):
    """Never trust a blind already-exists shortcut for tag or Release state.

    The tag/Release creation guard clauses this test names live in
    scripts/converge-release-tag (extracted from this workflow so they can
    be driven directly, not just read as source text) — see
    tests/test_release_convergence.py for behavioral proof that a resent
    event and a genuine concurrent race actually converge to one tag and
    one Release, not merely that these strings are present.
    """
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    )
    source = (ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )
    converge = (ROOT / "scripts/converge-release-tag").read_text(
        encoding="utf-8"
    )

    # A same-repo concurrency group with cancel-in-progress disabled queues
    # concurrent or resent runs instead of racing them.
    assert workflow["concurrency"] == {
        "group": "release-${{ github.repository }}",
        "cancel-in-progress": False,
    }
    assert "./scripts/converge-release-tag" in source
    # A rerun that finds the tag already pointing at this commit reuses it;
    # a tag at any other commit fails closed instead of moving or ignoring it.
    assert 'test "$tag_sha" = "$sha"' in converge
    # A Release is only created when none exists yet for the tag.
    assert 'if ! gh release view "$tag" >/dev/null 2>&1; then' in converge
    # The exact release state is always re-derived from GitHub after any
    # candidate or rerun path, not assumed from a prior step's local output.
    assert (
        'release="$(gh release view "$tag" --json isDraft,isImmutable,tagName)"'
        in source
    )
    assert 'test "$(jq -r .tagName <<<"$release")" = "$tag"' in source
    assert 'test "$(git rev-parse "$tag^{commit}")" = "$GITHUB_SHA"' in source


def test_release_please_always_stages_a_draft() -> None:
    """Never expose a GitHub Release before its assets are verified."""
    config = json.loads(
        (ROOT / "release-please-config.json").read_text(encoding="utf-8")
    )
    assert config["packages"]["."]["draft"] is True
    assert '"draft": true' in (
        ROOT / "template/release-please-config.json.jinja"
    ).read_text(encoding="utf-8")


def test_release_rerun_recovers_a_tag_without_a_release() -> None:
    """Revalidate and restage when a prior run stopped after tag creation."""
    source = (ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )

    assert "steps.plan.outputs.status == 'released'" in source
    assert "./scripts/converge-release-tag" in source
    converge = (ROOT / "scripts/converge-release-tag").read_text(
        encoding="utf-8"
    )
    assert "gh release create" in converge


def test_template_only_adds_release_workflow_to_new_repositories() -> None:
    """Leave an existing repository's product-owned release workflow alone."""
    copier = (ROOT / "copier.yml").read_text(encoding="utf-8")
    template = (
        ROOT / "template/.github/workflows/release.yml.jinja"
    ).read_text(encoding="utf-8")

    assert "project_mode == 'new'" in copier
    assert ".github/workflows/release.yml" in copier
    assert "./scripts/verify full" in template
    assert "./scripts/verify-release-candidate" in template
    assert '{% if "typescript" in languages %}' in template
    assert '{% if "rust" in languages %}' in template
    assert '"path": "Cargo.lock"' in (
        ROOT / "template/release-please-config.json.jinja"
    ).read_text(encoding="utf-8")

    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "CSARC_PUBLISH_CANDIDATE_STATUS" in ci
    assert (
        './scripts/verify-release-candidate "$RUNNER_TEMP/release-pr.json"'
        in ci
    )


def test_guided_candidate_validation_is_csarc_owned_only() -> None:
    """Do not apply the CSARC release contract to product release branches."""
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["verify"]["steps"]
    candidate = next(
        step
        for step in steps
        if step.get("name") == "Validate the guided release candidate"
    )

    assert "steps.release.outputs.ownership == 'csarc-owned'" in candidate["if"]
    template = (ROOT / "template/.github/workflows/ci.yml.jinja").read_text(
        encoding="utf-8"
    )
    assert "steps.release.outputs.ownership == 'csarc-owned'" in template


def test_template_only_offers_working_delivery_options() -> None:
    """Do not expose settings that cannot change generated behavior."""
    config = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))

    unsupported = {
        "container_mode",
        "containerfile_path",
        "container_smoke_command",
        "enable_release_attestations",
        "enable_pypi_publishing",
        "pypi_environment",
        "enable_npm_publishing",
        "npm_environment",
    }
    assert unsupported.isdisjoint(config)


def test_retired_archive_has_no_release_workflow_copy() -> None:
    """Use Git history instead of keeping replaced release workflows."""
    archive = ROOT / "archive/ci-cd/2026-08-27"
    assert not list((archive / "root-workflows").glob("*release*"))
    assert not list((archive / "template-workflows").glob("*release*"))


def test_guided_path_has_no_repo_local_publisher() -> None:
    """Only release.yml may create tags or GitHub Releases."""
    source = (ROOT / "scripts/release_policy.py").read_text(encoding="utf-8")

    assert "def direct_release" not in source
    assert 'add_parser("release")' not in source
    assert '"tag_name"' not in source
    assert '"/dispatches"' not in source


def test_release_status_stays_candidate_until_default_branch_evidence() -> None:
    """Keep root, generated README, and both site languages honest."""
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    template_readme = (ROOT / "template/README.md.jinja").read_text(
        encoding="utf-8"
    )
    chinese = (ROOT / "site/content/_index.zh-tw.md").read_text(
        encoding="utf-8"
    )
    english = (ROOT / "site/content/_index.en.md").read_text(encoding="utf-8")
    rendered_chinese = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    rendered_english = (ROOT / "docs/index.en.html").read_text(encoding="utf-8")
    fullwidth_slash = "\N{FULLWIDTH SOLIDUS}"

    assert f"Candidate{fullwidth_slash}Blocked" in root_readme
    assert "Configured" in template_readme
    assert f"Candidate{fullwidth_slash}Blocked" in chinese
    assert "Candidate / Blocked" in english
    assert f"Candidate{fullwidth_slash}Blocked" in rendered_chinese
    assert "Candidate / Blocked" in rendered_english
    assert f"| tag{fullwidth_slash}GitHub Release | Active |" not in chinese
    assert "| Tag and GitHub Release | Active |" not in english
    assert "release workflow are active" not in english
    assert "Action 尚未啟用" not in chinese


def test_shared_ci_policy_names_the_generated_verifier() -> None:
    """Do not send generated repositories to a root-only command."""
    policy = (ROOT / "docs/ci-policy.md").read_text(encoding="utf-8")

    assert "生成 repo 呼叫 `scripts/verify`" in policy
    assert "生成 repo 用 `scripts/verify full`" in policy
