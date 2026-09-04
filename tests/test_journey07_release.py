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
    assert "./scripts/publish-release stage" in source
    assert "./scripts/publish-release resolve" in source
    assert "./scripts/publish-release publish" in source
    assert "./scripts/publish-release rerun-verify" in source
    assert "secrets.GITHUB_TOKEN" in source
    assert "PAT" not in source
    assert "create-github-app-token" not in source
    assert "release_policy.py release" not in source
    assert "/actions/workflows/" not in source
    assert "source_run_id" not in source

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

    # The publish stage (Issue #589) is a single implementation: release.yml
    # calls scripts/publish-release for staging, state resolution,
    # publishing, and rerun verification instead of keeping its own copy of
    # this bash. See tests/test_release_publish.py for behavioral proof
    # (mocked `gh`) that the extracted script does what these strings say.
    publish = (ROOT / "scripts/publish-release").read_text(encoding="utf-8")
    assert 'release_bundle.py" prepare' in publish
    assert 'release_bundle.py" finalize' in publish
    assert 'release_bundle.py" verify' in publish
    assert "gh release upload" in publish
    assert "--clobber" in publish
    assert "gh release edit" in publish
    assert "for attempt in $(seq 1 12)" in publish
    assert "gh release verify" in publish
    assert '"$repo_root/scripts/converge-release-tag"' in publish
    assert '"$repo_root/scripts/verify-release-candidate"' in publish
    assert "scripts/install-syft" in publish
    # A shell double-quoted --jq argument must escape its own literal quotes,
    # so the merged-commit comparison reads as \"$sha\" in the script.
    assert r".merge_commit_sha == \"$sha\"" in publish
    assert 'jq -r .merge_commit_sha <<<"$pr"' in publish
    # A failed publish reverts a still-mutable Release back to draft instead
    # of leaving a half-public Release; extracted from the old separate
    # "Keep a failed mutable release in draft" step into this same script.
    assert "revert_to_draft_on_failure" in publish
    assert "trap revert_to_draft_on_failure EXIT" in publish


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
    converge = (ROOT / "scripts/converge-release-tag").read_text(
        encoding="utf-8"
    )
    publish = (ROOT / "scripts/publish-release").read_text(encoding="utf-8")

    # A same-repo concurrency group with cancel-in-progress disabled queues
    # concurrent or resent runs instead of racing them.
    assert workflow["concurrency"] == {
        "group": "release-${{ github.repository }}",
        "cancel-in-progress": False,
    }
    # release.yml calls the extracted publish stage, which in turn calls
    # converge-release-tag; it does not keep its own copy of that call.
    assert "$repo_root/scripts/converge-release-tag" in publish
    # A rerun that finds the tag already pointing at this commit reuses it;
    # a tag at any other commit fails closed instead of moving or ignoring it.
    assert 'test "$tag_sha" = "$sha"' in converge
    # A Release is only created when none exists yet for the tag.
    assert 'if ! gh release view "$tag" >/dev/null 2>&1; then' in converge
    # The exact release state is always re-derived from GitHub after any
    # candidate or rerun path, not assumed from a prior step's local output.
    assert (
        'release="$(gh release view "$tag" --json isDraft,isImmutable,tagName)"'
        in publish
    )
    assert 'test "$(jq -r .tagName <<<"$release")" = "$tag"' in publish
    assert (
        'test "$(git -C "$repo_root" rev-parse "$tag^{commit}")" = "$sha"'
        in publish
    )


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
    assert "./scripts/publish-release stage" in source
    publish = (ROOT / "scripts/publish-release").read_text(encoding="utf-8")
    assert "$repo_root/scripts/converge-release-tag" in publish
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


def test_release_drift_check_is_independent_of_release_yml() -> None:
    """Issue #605: a stuck release.yml must not gate its own drift alert.

    Mirrors the .github/workflows/governance-drift.yml pattern (schedule +
    workflow_dispatch, least-privilege permissions, logic in a repo-local
    check-* script) but is a genuinely separate workflow file so a hung or
    failing release.yml cannot suppress it.
    """
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/release-drift.yml").read_text(
            encoding="utf-8"
        )
    )
    source = (ROOT / ".github/workflows/release-drift.yml").read_text(
        encoding="utf-8"
    )
    triggers = workflow.get("on", workflow.get(True))

    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers
    assert workflow["permissions"] == {
        "actions": "read",
        "contents": "read",
        "issues": "write",
    }
    assert workflow["jobs"]["check"]["timeout-minutes"] == 5
    assert "run: ./scripts/check-release-drift" in source
    # Not a step inside release.yml itself, and does not share its trigger.
    release_source = (ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )
    assert "check-release-drift" not in release_source
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_release_drift_script_documents_its_threshold_and_record_format() -> (
    None
):
    """The 24h default and the local-record convention must be self-documented.

    Issue #605 pins N=24h (release.yml normally finishes within minutes of
    a push to main, and 24h both tolerates a release-free day and still
    catches a same-day stall) and defines the Release-publish-record
    marker line #589 only described in prose; both need to live in the
    script's own header, not only in an Issue body.
    """
    script = (ROOT / "scripts/check-release-drift").read_text(encoding="utf-8")

    assert "RELEASE_DRIFT_HOURS" in script
    assert "24" in script
    assert "Release-publish-record:" in script
    assert "operator=" in script
    assert "commit=" in script
    assert 'gh api "repos/$repo/actions/workflows/release.yml/runs' in script
    assert "gh issue create" in script
    assert "gh issue edit" in script
    assert "exit 1" in script


def test_release_drift_check_ships_with_release_ownership() -> None:
    """Only a repository that owns release.yml needs its drift check.

    Reuses release.yml's own project_mode == 'new' exclude condition
    instead of adding a second Copier option -- consistent with the
    release-security-and-dependencies ADR's "本節也不新增 Copier 選項"
    principle for this same capability pairing.
    """
    copier = (ROOT / "copier.yml").read_text(encoding="utf-8")
    paired = (ROOT / "scripts/sync-paired-files.sh").read_text(encoding="utf-8")

    assert (
        "{% if project_mode == 'new' %}__keep_release_drift_workflow__"
        "{% else %}.github/workflows/release-drift.yml{% endif %}" in copier
    )
    assert (
        "{% if project_mode == 'new' %}__keep_release_drift_script__"
        "{% else %}scripts/check-release-drift{% endif %}" in copier
    )
    assert ".github/workflows/release-drift.yml" in paired
    assert "scripts/check-release-drift" in paired

    template_workflow = (
        ROOT / "template/.github/workflows/release-drift.yml"
    ).read_bytes()
    template_script = (
        ROOT / "template/scripts/check-release-drift"
    ).read_bytes()
    assert (
        template_workflow
        == (ROOT / ".github/workflows/release-drift.yml").read_bytes()
    )
    assert (
        template_script == (ROOT / "scripts/check-release-drift").read_bytes()
    )
