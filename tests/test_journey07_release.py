"""Regression tests for the automatic version and release workflow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).parents[1]


def test_release_workflow_only_publishes_premerged_candidates() -> None:
    """Candidate creation belongs to the reviewed delivery pull request."""
    path = ROOT / ".github/workflows/release.yml"
    source = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    triggers = workflow.get("on", workflow.get(True))

    assert triggers == {"workflow_dispatch": None}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert workflow["jobs"]["release"]["if"] == (
        "${{ github.ref == 'refs/heads/main' || "
        "startsWith(github.ref, 'refs/heads/dev/m') }}"
    )
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]["release"]["permissions"]) == {
        "actions",
        "checks",
        "contents",
        "issues",
        "pull-requests",
        "statuses",
    }
    assert workflow["jobs"]["release"]["permissions"]["pull-requests"] == (
        "read"
    )
    assert workflow["jobs"]["release"]["timeout-minutes"] == 60
    assert "googleapis/release-please-action@" not in source

    assert "release_policy.py plan" in source
    assert "release_level.py release-batch" in source
    assert "RELEASE_LEVEL: ${{ steps.route.outputs.channel }}" in source
    assert '--phase "$RELEASE_LEVEL"' in source
    assert "release_level.py annotate-pr" not in source
    assert "release_level.py annotate-release" in source
    assert "release_policy.py detect" in source
    assert "mode == 'blocked'" in source
    assert "release_policy.py prepare-candidate" not in source
    assert "./scripts/verify-release-candidate" not in source
    assert "Reject an unmaterialized merged delivery" in source
    assert './scripts/check-trusted-verification "$GITHUB_SHA"' in source
    assert "./scripts/verify-template.sh" in source
    assert "./scripts/verify-fast" in source
    assert "run: ./scripts/verify full" not in source
    assert "--resolve-merge-source" in source
    assert "REQUIRED_TIER: ${{ steps.route.outputs.required_tier }}" in source
    assert '--required-tier "$REQUIRED_TIER"' in source
    assert '--github-repo "$GITHUB_REPOSITORY"' in source
    assert "steps.verification.outputs.reused != 'true'" in source
    assert "scripts/release_bundle.py prepare" in source
    assert "./scripts/publish-release stage" in source
    assert "./scripts/publish-release resolve" in source
    assert "./scripts/publish-release publish" in source
    assert "./scripts/publish-release rerun-verify" in source
    assert "sync_milestone_state.py complete-release" in source
    assert "steps.plan.outputs.status == 'no-release'" in source
    assert "secrets.GITHUB_TOKEN" not in source
    assert "PAT" not in source
    assert "create-github-app-token" not in source
    assert "release_policy.py release" not in source
    assert "/actions/workflows/" not in source
    assert "source_run_id" not in source

    steps = workflow["jobs"]["release"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Resolve included work and release level") < names.index(
        "Plan the next version from repository history"
    )
    assert names.index(
        "Reject an unmaterialized merged delivery"
    ) < names.index("Detect the available release path")
    assert names.index(
        "Record included work in the draft Release"
    ) < names.index("Bind, upload, and publish the release")

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
    assert (
        "# shellcheck disable=SC2329 # Invoked indirectly by the EXIT trap.\n"
        "  cleanup_candidate_worktree() {"
    ) in candidate

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


@pytest.mark.parametrize(
    ("release_trigger", "push_enabled"),
    [("main", True), ("manual", False)],
)
def test_release_trigger_omits_unwanted_push_runs(
    release_trigger: str, push_enabled: bool
) -> None:
    """Manual releases create no push-triggered workflow run at all."""
    source = (ROOT / "template/.github/workflows/release.yml.jinja").read_text(
        encoding="utf-8"
    )
    environment = Environment(
        autoescape=False,  # noqa: S701 - trusted local YAML template
        undefined=StrictUndefined,
    )
    rendered = environment.from_string(source).render(
        languages=[], release_trigger=release_trigger
    )
    workflow = yaml.safe_load(rendered)

    triggers = workflow.get("on", workflow.get(True))
    assert triggers["workflow_dispatch"] is None
    assert ("push" in triggers) is push_enabled
    if push_enabled:
        assert triggers["push"]["branches"] == ["main", "dev/m*"]
    condition = workflow["jobs"]["release"]["if"]
    assert "github.event_name != 'push'" not in condition


def test_release_preflight_short_circuits_before_toolchain_setup() -> None:
    """Issue #707: cheap gates must run before any expensive setup."""
    root_source = (ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )
    template_source = (
        ROOT / "template/.github/workflows/release.yml.jinja"
    ).read_text(encoding="utf-8")
    environment = Environment(
        autoescape=False,  # noqa: S701 - trusted local YAML template
        undefined=StrictUndefined,
    )
    rendered_template = environment.from_string(template_source).render(
        languages=["python", "typescript", "rust"], release_trigger="main"
    )
    no_release_guard = (
        '${{ !contains(fromJSON(\'["no-release","deferred"]\'), '
        "steps.plan.outputs.status) }}"
    )

    for source in (root_source, rendered_template):
        steps = yaml.safe_load(source)["jobs"]["release"]["steps"]
        by_name = {
            step["name"]: (index, step)
            for index, step in enumerate(steps)
            if "name" in step
        }
        toolchain_steps = [
            (index, step)
            for index, step in enumerate(steps)
            if any(
                str(step.get("uses", "")).startswith(action)
                for action in (
                    "actions/setup-python@",
                    "astral-sh/setup-uv@",
                    "pnpm/action-setup@",
                    "actions/setup-node@",
                )
            )
            or step.get("name") == "Install the pinned Rust toolchain"
        ]

        plan_index, _ = by_name["Plan the next version from repository history"]
        capability_index, capability = by_name[
            "Detect the available release path"
        ]
        blocked_index, _ = by_name["Stop when GitHub publication is blocked"]
        attestation_index, attestation = by_name[
            "Reuse the source PR's trusted verification evidence"
        ]
        _, fallback = by_name[
            "Re-verify the exact release tree when reuse is unavailable"
        ]
        _, resolve = by_name["Resolve the exact release state"]

        route_index, _ = by_name["Resolve release route"]
        level_index, _ = by_name["Resolve included work and release level"]
        checkpoint_index, checkpoint = by_name[
            "Resolve the checkpoint role of the merged work"
        ]
        deferred_index, deferred = by_name["Record deferred checkpoint work"]
        _, plan = by_name["Plan the next version from repository history"]
        assert route_index == 1
        assert level_index == route_index + 1
        assert checkpoint_index == level_index + 1
        assert plan_index == checkpoint_index + 1
        assert deferred_index == plan_index + 1
        # Only delivery branches resolve a checkpoint; main keeps role none.
        assert checkpoint["if"] == (
            "${{ steps.route.outputs.channel == 'beta' }}"
        )
        assert plan["env"]["CHECKPOINT_ROLE"] == (
            "${{ steps.checkpoint.outputs.role || 'none' }}"
        )
        assert '--checkpoint-role "$CHECKPOINT_ROLE"' in plan["run"]
        assert deferred["if"] == (
            "${{ steps.plan.outputs.status == 'deferred' }}"
        )
        assert plan_index < capability_index < blocked_index
        assert blocked_index < attestation_index
        assert attestation_index < min(index for index, _ in toolchain_steps)
        assert capability["if"] == no_release_guard
        assert attestation["if"] == no_release_guard
        # Fallback verifies against the real pre-merge base, never the
        # accumulated default branch of a dispatched delivery release.
        assert fallback["env"]["CSARC_CI_BASE"] == "${{ github.event.before }}"
        assert (
            'CSARC_CI_BASE="${CSARC_CI_BASE:-$(git rev-parse "$GITHUB_SHA^1")}"'
            in fallback["run"]
        )
        assert '--merge-branch "$GITHUB_REF_NAME"' in attestation["run"]
        assert resolve["if"] == no_release_guard
        assert all(
            step["if"] == no_release_guard for _, step in toolchain_steps
        )


def test_release_reuse_resolves_the_exact_merged_pr_head() -> None:
    """Reuse trusted PR evidence only for the exact merged-main tree."""
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["release"]["steps"]
    step = next(
        candidate
        for candidate in steps
        if candidate.get("name")
        == "Reuse the source PR's trusted verification evidence"
    )
    assert step["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "REQUIRED_TIER": "${{ steps.route.outputs.required_tier }}",
    }
    assert "--resolve-merge-source" in step["run"]
    assert '--github-repo "$GITHUB_REPOSITORY"' in step["run"]


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
        ROOT / "template/.csarc/release-please-config.json.jinja"
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
    """Only new hosted repositories receive the release workflow."""
    copier = (ROOT / "copier.yml").read_text(encoding="utf-8")
    template = (
        ROOT / "template/.github/workflows/release.yml.jinja"
    ).read_text(encoding="utf-8")

    assert "project_mode == 'new'" in copier
    assert "verification_mode == 'hosted'" in copier
    assert ".github/workflows/release.yml" in copier
    assert (
        './.csarc/scripts/check-trusted-verification "$GITHUB_SHA"' in template
    )
    assert "--resolve-merge-source" in template
    assert '--github-repo "$GITHUB_REPOSITORY"' in template
    assert "REQUIRED_TIER: ${{ steps.route.outputs.required_tier }}" in template
    assert '--required-tier "$REQUIRED_TIER"' in template
    assert "googleapis/release-please-action@" not in template
    assert "Reject an unmaterialized merged delivery" in template
    assert '{% if "typescript" in languages %}' in template
    assert '{% if "rust" in languages %}' in template
    assert '"path": "Cargo.lock"' in (
        ROOT / "template/.csarc/release-please-config.json.jinja"
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


def test_csarc_owned_promotion_materializes_the_release_in_one_pr() -> None:
    """The delivery PR itself carries the exact version and changelog."""
    root = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    template = (ROOT / "template/.github/workflows/ci.yml.jinja").read_text(
        encoding="utf-8"
    )

    for source in (root, template):
        assert "Validate Milestone promotion version materialization" in source
        assert "verify-promotion-version" in source
        assert "steps.release.outputs.ownership == 'csarc-owned'" in source


def test_csarc_owned_ordinary_work_materializes_the_release_in_one_pr() -> None:
    """Standalone and Milestone work use the same exact final-commit gate."""
    root = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    template = (ROOT / "template/.github/workflows/ci.yml.jinja").read_text(
        encoding="utf-8"
    )

    for source in (root, template):
        assert "Validate same-PR release materialization" in source
        assert "verify-delivery-version" in source
        assert '--base-sha "$BASE_SHA"' in source
        assert "steps.release.outputs.ownership == 'csarc-owned'" in source
        assert "steps.sync.outputs.route == 'ordinary'" in source


def test_one_issue_milestone_uses_only_work_and_promotion_prs() -> None:
    """No post-promotion version PR is needed for a CSARC-owned Milestone."""
    release = (ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )
    lifecycle = (ROOT / ".github/workflows/work-item-lifecycle.yml").read_text(
        encoding="utf-8"
    )
    policy = (ROOT / "scripts/validate-pr-policy").read_text(encoding="utf-8")
    publish = (ROOT / "scripts/publish-release").read_text(encoding="utf-8")

    assert "steps.plan.outputs.status == 'pending'" in release
    assert "googleapis/release-please-action@" not in release
    assert "sync_milestone_state.py complete-release" in release
    assert "record-promotion-evidence" not in lifecycle
    assert "Refs #N" in policy
    assert "must not close its tracker before release succeeds" in policy
    assert "verify-promotion-version" in publish
    assert 'sync_milestone_state.py" complete-release' in publish


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


def test_guided_path_has_no_repo_local_publisher() -> None:
    """Only release.yml may create tags or GitHub Releases.

    Issue #744's dry-run retention lister legitimately *reads* an existing
    Release's `tag_name` (there is no other way to list what already
    exists), so the narrower invariant this guards is "never construct a
    create-Release request body" -- a real `gh api ... -f tag_name=...` or
    JSON payload literal `"tag_name": ` -- not "never mention the field
    name while reading one back."
    """
    source = (ROOT / "scripts/release_policy.py").read_text(encoding="utf-8")

    assert "def direct_release" not in source
    assert 'add_parser("release")' not in source
    assert '"tag_name": ' not in source
    assert '"/dispatches"' not in source


def test_release_phase_module_is_synced_across_all_three_copies() -> None:
    """scripts/release_phase.py has no single canonical source, by CI.

    Its own docstring says three copies (scripts/, template/.csarc/scripts/, and
    src/csarc_cli/ -- the last only because the distributed `csarc` wheel
    ships src/csarc_cli alone and cannot import a sibling scripts/ module)
    are kept byte-identical, but only the first two are enforced by
    scripts/sync-paired-files.sh (a root-to-template/ tool, not a 3-way
    one). Without this test, an edit to one copy without the others would
    only ever be caught by someone's word, not CI.
    """
    root_text = (ROOT / "scripts/release_phase.py").read_text(encoding="utf-8")
    template_text = (
        ROOT / "template/.csarc/scripts/release_phase.py"
    ).read_text(encoding="utf-8")
    cli_text = (ROOT / "src/csarc_cli/release_phase.py").read_text(
        encoding="utf-8"
    )
    assert root_text == template_text, (
        "scripts/release_phase.py and template/.csarc/scripts/release_phase.py "
        "have drifted; run scripts/sync-paired-files.sh"
    )
    assert root_text == cli_text, (
        "scripts/release_phase.py and src/csarc_cli/release_phase.py have "
        "drifted; copy one over the other so all three stay identical"
    )


def test_release_status_stays_candidate_until_default_branch_evidence() -> None:
    """Keep root, generated README, and both site languages honest."""
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # Issue #681: template/README.md.jinja's destination name now depends
    # on the primary_language answer, so its source filename is a
    # Jinja expression; "zh-tw" always appears in the zh-tw content file's
    # name and never in the English one, so it is a reliable glob.
    zh_tw_readme_matches = list((ROOT / "template").glob("*zh-tw*.md.jinja"))
    assert len(zh_tw_readme_matches) == 1, (
        f"expected exactly one zh-tw README template, found "
        f"{zh_tw_readme_matches}"
    )
    template_readme = zh_tw_readme_matches[0].read_text(encoding="utf-8")
    chinese = (ROOT / "site/content/_index.zh-tw.md").read_text(
        encoding="utf-8"
    )
    english = (ROOT / "site/content/_index.en.md").read_text(encoding="utf-8")
    rendered_chinese = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    rendered_english = (ROOT / "docs/index.en.html").read_text(encoding="utf-8")
    fullwidth_slash = "\N{FULLWIDTH SOLIDUS}"

    assert f"Candidate{fullwidth_slash}Blocked" in root_readme
    assert "Tag / GitHub Release" not in template_readme
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

    assert "（生成 repo 是 `.csarc/scripts/verify`）" in policy  # noqa: RUF001
    assert (
        "入口是 `.csarc/scripts/verify`（不帶參數即預設 full）" in policy  # noqa: RUF001
    )


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
        "pull-requests": "read",
    }
    assert workflow["jobs"]["check"]["timeout-minutes"] == 5
    assert "run: ./scripts/check-release-drift" in source
    # Not a step inside release.yml itself, and does not share its trigger.
    release_source = (ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )
    assert "check-release-drift" not in release_source
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_release_drift_script_documents_its_authoritative_sources() -> None:
    """The threshold and authoritative release-state sources stay explicit.

    Issue #605 pins N=24h (release.yml normally finishes within minutes of
    a push to main, and 24h both tolerates a release-free day and still
    catches a same-day stall). Issue #708 keeps audit text from becoming
    release authority and requires immutable GitHub Release evidence. Issue
    #802 limits successful workflow evidence to an explicit no-release plan.
    """
    script = (ROOT / "scripts/check-release-drift").read_text(encoding="utf-8")

    assert "RELEASE_DRIFT_HOURS" in script
    assert "24" in script
    assert "Release-publish-record" in script
    assert 'latest_release.get("immutable") is not True' in script
    assert 'gh api "repos/$repo/actions/workflows/release.yml/runs' in script
    assert 'gh api "repos/$repo/actions/runs/$last_run_id/jobs' in script
    assert "Local publish record (audit only)" in script
    assert "last_success_no_release = bool(" in script
    assert "if last_success_no_release and last_success_sha" in script
    assert "guided instructions only (not publication evidence)" in script
    assert "recent_activity = success_recent or release_recent" in script
    assert "record_sha" not in script
    assert "record_recent" not in script
    assert 'len(fields["command"]) <= 512' in script
    assert "audit evidence is unavailable" in script
    assert "gh issue create" in script
    assert 'scripts/pr_lifecycle.py" issue-edit' in script
    assert (
        "Release publish drift detected; publishing the tracking Issue."
        in script
    )
    assert script.rstrip().endswith("exit 0")


def test_release_drift_check_ships_with_release_ownership() -> None:
    """Only a hosted repository that owns release.yml needs its drift check.

    Reuses release.yml's project and verification mode conditions instead
    of adding a second Copier option -- consistent with the
    release-security-and-dependencies ADR's "本節也不新增 Copier 選項"
    principle for this same capability pairing.
    """
    copier = (ROOT / "copier.yml").read_text(encoding="utf-8")
    assert (
        "{% if project_mode == 'new' and verification_mode == 'hosted' %}"
        "__keep_release_drift_workflow__"
        "{% else %}.github/workflows/release-drift.yml{% endif %}" in copier
    )
    assert (
        "{% if project_mode == 'new' and verification_mode == 'hosted' %}"
        "__keep_release_drift_script__"
        "{% else %}.csarc/scripts/check-release-drift{% endif %}" in copier
    )

    template_workflow = (
        ROOT / "template/.github/workflows/release-drift.yml"
    ).read_text(encoding="utf-8")
    template_script = (
        ROOT / "template/.csarc/scripts/check-release-drift"
    ).read_text(encoding="utf-8")
    root_script = (ROOT / "scripts/check-release-drift").read_text(
        encoding="utf-8"
    )
    assert "run: ./.csarc/scripts/check-release-drift" in template_workflow
    assert ".csarc/scripts/check-release-drift" in template_workflow
    for marker in (
        "RELEASE_DRIFT_HOURS",
        "Release-publish-record",
        "gh issue create",
        'pr_lifecycle.py" issue-edit',
    ):
        assert marker in template_script
        assert marker in root_script
    assert 'dirname "${BASH_SOURCE[0]}")/../..' in template_script
