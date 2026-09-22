"""Regression tests for the Dependabot auto-merge workflow."""

from __future__ import annotations

import ast
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/dependabot-auto-merge.yml"
MERGE_WORKFLOW_PATH = REPO_ROOT / ".github/workflows/dependabot-merge.yml"
GENERATED_WORKFLOW_PATH = (
    REPO_ROOT / "template/.github/workflows/dependabot-auto-merge.yml"
)


def test_copier_is_never_imported_at_module_level() -> None:
    """Issue #771: keep the `copier` import lazy, not a regression waiting.

    `copier` is a template-authoring-only dependency (root `pyproject.toml`).
    A top-level `import copier` /
    `from copier import ...` here previously broke a generated project's own
    `ty check` (static "unresolved-import" -- `ty` has no way to know the
    import is conditional at runtime) and, without `copier` installed,
    pytest's collection of the whole module. Walk this file's own top-level
    statements (deliberately not `ast.walk`, which would also match the
    intentional, guarded import inside `_render_dependabot_config`) to prove
    the import stays confined to that lazy `pytest.importorskip("copier")`
    guard instead of trusting a future edit to notice by re-running
    `ty check` in a copier-less environment.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_names = {alias.name.split(".")[0] for alias in node.names}
            assert "copier" not in top_level_names
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "copier"


def test_generated_workflow_uses_only_its_csarc_adapter() -> None:
    """Do not ship the template-authoring paired-file sync downstream."""
    source = GENERATED_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)

    assert "sync-template" not in workflow["jobs"]
    assert "sync_eligible" not in source
    assert "sync_complete" not in source
    assert "scripts/sync-paired-files.sh" not in source
    assert ".csarc/scripts/authenticate_dependabot_head.py" in source
    assert workflow["jobs"]["classify-update"]["needs"] == "authenticate"


def _load_workflow() -> tuple[str, dict]:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    return source, workflow


def _steps_by_name(workflow: dict) -> dict[str, dict]:
    steps = workflow["jobs"]["classify-update"]["steps"]
    return {step["name"]: step for step in steps}


def _load_merge_workflow() -> tuple[str, dict]:
    source = MERGE_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    return source, workflow


def _auth_steps_by_name(workflow: dict) -> dict[str, dict]:
    steps = workflow["jobs"]["authenticate"]["steps"]
    return {step["name"]: step for step in steps}


def _sync_steps_by_name(workflow: dict) -> dict[str, dict]:
    steps = workflow["jobs"]["sync-template"]["steps"]
    return {step["name"]: step for step in steps}


def test_workflow_only_triggers_on_dependabot_pull_requests() -> None:
    """Use the trusted base workflow and skip non-Dependabot pull requests."""
    _, workflow = _load_workflow()
    triggers = workflow.get("on", workflow.get(True))

    assert triggers == {
        "pull_request_target": {
            "branches": ["main"],
            "types": ["opened", "synchronize", "reopened"],
        }
    }
    job = workflow["jobs"]["authenticate"]
    assert (
        " ".join(job["if"].split())
        == "${{ github.event.pull_request.user.login == 'dependabot[bot]' && "
        "github.event.pull_request.base.ref == 'main' }}"
    )


def test_concurrency_serializes_head_state_without_cancelling_sync() -> None:
    """Each PR authenticates head changes in event order."""
    _, workflow = _load_workflow()

    assert workflow["concurrency"] == {
        "group": (
            "${{ github.workflow }}-${{ github.event.pull_request.number }}"
        ),
        "cancel-in-progress": False,
    }


def test_workflow_permissions_are_minimal() -> None:
    """Grant only what authentication, syncing, and labeling need."""
    _, workflow = _load_workflow()

    assert workflow["permissions"] == {}
    assert workflow["jobs"]["authenticate"]["permissions"] == {
        "contents": "read",
        "pull-requests": "read",
    }
    assert workflow["jobs"]["classify-update"]["permissions"] == {
        "contents": "read",
        "pull-requests": "write",
    }
    assert workflow["jobs"]["merge-eligible"]["permissions"] == {}
    assert workflow["jobs"]["classify-update"]["timeout-minutes"] == 10


def test_workflow_never_leaves_persistent_native_auto_merge_state() -> None:
    """Every merge decision is exact-head and lifecycle-owned."""
    source, workflow = _load_workflow()

    assert "reset-auto-merge" not in workflow["jobs"]
    assert "auto-merge" not in workflow["jobs"]
    assert "gh pr merge --auto" not in source
    assert "--disable-auto" not in source


def test_writer_jobs_revalidate_the_exact_live_pull_request() -> None:
    """Close, retarget, repo, ref, base, or head races all fail closed."""
    _, workflow = _load_workflow()
    classify_steps = _steps_by_name(workflow)
    sync_steps = _sync_steps_by_name(workflow)

    for step in (
        classify_steps["Flag major updates for manual review"],
        sync_steps[
            "Sync paired template files and push if this bump drifted them"
        ],
    ):
        assert step["env"]["BASE_SHA"] == (
            "${{ needs.authenticate.outputs.base_sha }}"
        )
        assert step["env"]["HEAD_REF"] == (
            "${{ needs.authenticate.outputs.head_ref }}"
        )
        run = step["run"]
        for predicate in (
            '.state == "open"',
            '.base.ref == "main"',
            ".base.repo.full_name == $repo",
            ".base.sha == $base_sha",
            ".head.ref == $head_ref",
            ".head.repo.full_name == $repo",
            ".head.sha == $head_sha",
        ):
            assert predicate in run


def test_fetch_metadata_action_is_pinned_to_a_full_commit_sha() -> None:
    """Match this repository's convention for every third-party Action."""
    source, _ = _load_workflow()

    match = re.search(
        r"dependabot/fetch-metadata@([0-9a-f]{40})\s+#\s+(v\S+)", source
    )
    assert match is not None, (
        "fetch-metadata must be pinned to a full commit SHA"
    )
    assert match.group(2).startswith("v")


def test_minor_and_patch_updates_publish_exact_head_eligibility() -> None:
    """Only authenticated minor and patch heads get merge eligibility."""
    _, workflow = _load_workflow()
    job = workflow["jobs"]["merge-eligible"]

    assert job["name"] == "dependabot-merge-eligible"
    condition = job["if"]
    assert "version-update:semver-patch" in condition
    assert "version-update:semver-minor" in condition
    assert "version-update:semver-major" not in condition
    assert job["needs"] == "classify-update"


def test_major_updates_are_flagged_instead_of_merged() -> None:
    """Keep breaking-change-risk updates out of the auto-merge path."""
    _, workflow = _load_workflow()
    steps = _steps_by_name(workflow)
    step = steps["Flag major updates for manual review"]

    condition = step["if"]
    assert "version-update:semver-major" in condition
    assert "semver-minor" not in condition
    assert "semver-patch" not in condition
    run = step["run"]
    assert "gh pr merge" not in run
    assert 'gh pr edit "$PR_URL" --add-label needs-manual-review' in run
    assert "gh pr comment" in run


def test_needs_manual_review_label_is_defined_in_policy() -> None:
    """Keep the label the workflow applies provisionable from policy."""
    labels = json.loads(
        (REPO_ROOT / "policies/labels.json").read_text(encoding="utf-8")
    )
    names = {label["name"] for label in labels}

    assert "needs-manual-review" in names


def test_dependabot_cooldown_already_covers_the_supply_chain_delay() -> None:
    """Confirm the pre-merge safeguard the maintainer asked for is in place.

    The auto-merge workflow deliberately does not add its own waiting
    period: .github/dependabot.yml already delays every pull request by
    cooldown.default-days: 3 after a release, before Dependabot opens it.
    """
    config = (REPO_ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")

    assert len(re.findall(r"^\s+default-days:\s*3\s*$", config, re.M)) >= 1


def test_sync_template_job_only_triggers_on_dependabot_pull_requests() -> None:
    """Issue #830: writes require an authenticated Actions update head."""
    _, workflow = _load_workflow()
    job = workflow["jobs"]["sync-template"]

    assert (
        job["if"] == "${{ needs.authenticate.outputs.sync_eligible == 'true' }}"
    )
    assert job["permissions"] == {
        "contents": "write",
        "pull-requests": "read",
    }


def test_authentication_uses_only_the_trusted_base_revision() -> None:
    """Issue #830: authentication code comes from the immutable base SHA."""
    _, workflow = _load_workflow()
    steps = _auth_steps_by_name(workflow)
    checkout = steps["Check out the trusted base revision"]
    authenticate = steps["Classify the current Dependabot head"]

    assert checkout["with"] == {
        "ref": "${{ github.event.pull_request.base.sha }}",
        "persist-credentials": False,
    }
    assert "scripts/authenticate_dependabot_head.py" in authenticate["run"]
    assert authenticate["env"]["EXPECTED_BASE_SHA"] == (
        "${{ github.event.pull_request.base.sha }}"
    )
    assert '--expected-base-sha "$EXPECTED_BASE_SHA"' in authenticate["run"]
    assert "pull-request.json" in authenticate["run"]
    assert "head-commit.json" in authenticate["run"]
    assert "comparison.json" in authenticate["run"]


def test_authentication_reconstructs_a_trusted_sync_child() -> None:
    """A reopened generated head is accepted only after exact tree replay."""
    _, workflow = _load_workflow()
    job = workflow["jobs"]["authenticate"]
    steps = _auth_steps_by_name(workflow)
    reconstruct = steps["Reconstruct the candidate sync child"]["run"]

    assert job["outputs"]["sync_complete"] == (
        "${{ steps.authenticate.outputs.sync_complete }}"
    )
    assert (
        steps["Check out the trusted synchronizer for a sync child"]["with"][
            "ref"
        ]
        == "${{ steps.classify.outputs.source_base_sha }}"
    )
    assert (
        steps["Check out the authenticated Dependabot parent"]["with"]["ref"]
        == "${{ steps.classify.outputs.parent_sha }}"
    )
    assert steps["Check out the candidate sync child"]["with"]["ref"] == (
        "${{ steps.classify.outputs.head_sha }}"
    )
    assert "auth-sync-base/scripts/sync-paired-files.sh" in reconstruct
    assert "git write-tree" in reconstruct
    assert '[[ "$expected_tree" == "$child_tree" ]]' in reconstruct
    publish = steps["Publish authenticated head"]["run"]
    assert "sync_complete=true" in publish


def test_sync_template_checks_out_only_the_authenticated_head() -> None:
    """The writable checkout is pinned to the authenticated immutable SHA."""
    _, workflow = _load_workflow()
    steps = _sync_steps_by_name(workflow)
    step = steps["Check out the authenticated pull request head"]

    assert step["with"]["ref"] == "${{ needs.authenticate.outputs.head_sha }}"
    assert step["with"]["path"] == "pull-request"
    assert step["with"]["fetch-depth"] == 0


def test_sync_template_job_runs_only_the_base_synchronizer() -> None:
    """Never execute the synchronizer selected by the pull request head."""
    _, workflow = _load_workflow()
    steps = _sync_steps_by_name(workflow)
    run = steps[
        "Sync paired template files and push if this bump drifted them"
    ]["run"]

    assert (
        'cp "$GITHUB_WORKSPACE/trusted-base/scripts/sync-paired-files.sh"'
        in run
    )
    assert r"^template/\.github/workflows/[^/]+\.ya?ml$" in run
    assert 'git cat-file -e "$BASE_SHA^{commit}"' in run
    assert "if [[ $diff_status -ne 1 ]]" in run
    assert 'git add -- "${synced_paths[@]}"' in run


def test_sync_template_push_is_bound_to_the_authenticated_bot_ref() -> None:
    """The write fails if the authenticated head moved before the push."""
    _, workflow = _load_workflow()
    steps = _sync_steps_by_name(workflow)
    run = steps[
        "Sync paired template files and push if this bump drifted them"
    ]["run"]

    assert '--force-with-lease="refs/heads/$HEAD_REF:$HEAD_SHA"' in run
    assert 'origin "HEAD:refs/heads/$HEAD_REF"' in run


def test_eligibility_waits_for_the_final_authenticated_sync_head() -> None:
    """A paired-file sync cannot authorize the superseded parent head."""
    _, workflow = _load_workflow()
    classify = workflow["jobs"]["classify-update"]
    sync_template = workflow["jobs"]["sync-template"]
    sync = _sync_steps_by_name(workflow)[
        "Sync paired template files and push if this bump drifted them"
    ]

    assert classify["needs"] == ["authenticate", "sync-template"]
    assert sync_template["needs"] == "authenticate"
    assert "always()" in classify["if"]
    assert "needs.authenticate.result == 'success'" in classify["if"]
    assert "needs.sync-template.result == 'success'" in classify["if"]
    assert "needs.sync-template.result == 'skipped'" in classify["if"]
    assert (
        "needs.sync-template.outputs.head_sha == "
        "needs.authenticate.outputs.head_sha"
    ) in " ".join(classify["if"].split())
    assert sync_template["outputs"]["head_sha"] == (
        "${{ steps.sync.outputs.head_sha }}"
    )
    assert sync["id"] == "sync"
    assert 'echo "head_sha=$HEAD_SHA"' in sync["run"]
    assert 'echo "head_sha=$synced_head_sha"' in sync["run"]


def test_sync_template_job_is_a_no_op_without_drift() -> None:
    """A bump that never touches a paired file must not push an empty commit."""
    _, workflow = _load_workflow()
    steps = _sync_steps_by_name(workflow)
    run = steps[
        "Sync paired template files and push if this bump drifted them"
    ]["run"]

    assert "git status --porcelain" in run
    assert "exit 0" in run


def test_sync_template_commit_is_a_release_triggering_fix() -> None:
    """Issue #755, condition 5: template drift must reach a release.

    release-please (release-type: simple) only bumps a version for a
    `fix`/`feat` commit, never `chore`. Using `fix(deps)` here -- and
    only here, since this step only commits when sync-paired-files.sh
    found real drift -- is what stops a template-affecting bump from
    sitting on `main` unreleased forever without also release-triggering
    every unrelated Dependabot commit that never touched template/.
    """
    _, workflow = _load_workflow()
    steps = _sync_steps_by_name(workflow)
    run = steps[
        "Sync paired template files and push if this bump drifted them"
    ]["run"]

    assert re.search(r"git commit -m \"fix(\(deps\))?:", run) is not None


def test_exact_merge_wakes_only_from_trusted_completed_workflows() -> None:
    """A default-branch workflow_run resolves one exact open PR."""
    source, workflow = _load_merge_workflow()
    triggers = workflow.get("on", workflow.get(True))

    assert triggers == {
        "workflow_run": {
            "workflows": [
                "CI",
                "PR policy",
                "PR review",
                "Dependabot auto-merge",
            ],
            "branches": ["dependabot/**"],
            "types": ["completed"],
        }
    }
    assert workflow["permissions"] == {}
    resolve = workflow["jobs"]["resolve-pr"]
    assert "pull_request_target" in resolve["if"]
    assert "pull_request_review" in resolve["if"]
    assert "--resolve-head-sha" in source
    assert "ref: ${{ github.sha }}" in source
    assert "ref: ${{ github.event.workflow_run.head_sha }}" not in source


def test_exact_merge_rechecks_live_bot_coordinates_before_readiness() -> None:
    """A completed old run cannot select a moved, forked, or human PR head."""
    _, workflow = _load_merge_workflow()
    step = next(
        step
        for step in workflow["jobs"]["resolve-pr"]["steps"]
        if step["name"] == "Bind the exact live Dependabot identity"
    )

    for predicate in (
        '.state == "open"',
        '.user.login == "dependabot[bot]"',
        '.user.type == "Bot"',
        '.base.ref == "main"',
        ".base.repo.full_name == $repo",
        ".head.ref == $head_ref",
        ".head.repo.full_name == $head_repo",
        ".head.repo.full_name == $repo",
        ".head.sha == $head_sha",
    ):
        assert predicate in step["run"]


def test_exact_merge_uses_readiness_only_before_lifecycle_proof() -> None:
    """Read-only hints avoid lease churn; lifecycle proves every invariant."""
    source, workflow = _load_merge_workflow()
    merge = workflow["jobs"]["merge"]
    steps = {step["name"]: step for step in merge["steps"]}

    assert merge["permissions"] == {
        "actions": "write",
        "checks": "read",
        "contents": "write",
        "issues": "write",
        "pull-requests": "write",
        "statuses": "read",
    }
    assert "gh pr checks" in steps["Check read-only merge readiness"]["run"]
    assert "--required" in steps["Check read-only merge readiness"]["run"]
    assert (
        "dependabot-merge-eligible"
        in steps["Check read-only merge readiness"]["run"]
    )
    assert source.index("Check read-only merge readiness") < source.index(
        "Acquire the PR and destination lease"
    )
    for name in (
        "Revalidate lifecycle merge eligibility",
        "Merge the exact authenticated head",
    ):
        run = steps[name]["run"]
        assert "scripts/pr_lifecycle.py" in run
        assert "--require-dependabot-head" in run
        assert "--actor 'github-actions[bot]'" in run
    assert (
        "scripts/pr_lifecycle.py acquire"
        in steps["Acquire the PR and destination lease"]["run"]
    )
    assert (
        "--ttl-seconds 900"
        in steps["Acquire the PR and destination lease"]["run"]
    )
    assert "--auto" not in source
    assert "expectedHeadOid" not in source


def test_exact_merge_preserves_ambiguous_failures_and_dispatches_release() -> (
    None
):
    """Rejected preflights release; successful CSARC merges wake release."""
    _, workflow = _load_merge_workflow()
    steps = {step["name"]: step for step in workflow["jobs"]["merge"]["steps"]}
    release = steps["Release a pre-merge rejected lease"]
    dispatch = steps["Dispatch the repository-owned release flow"]

    assert "steps.check.outcome == 'failure'" in release["if"]
    assert "steps.merge.outcome" not in release["if"]
    assert "scripts/pr_lifecycle.py release" in release["run"]
    assert "steps.merge.outcome == 'success'" in dispatch["if"]
    assert "release_ownership" in dispatch["run"]
    assert "gh workflow run release.yml" in dispatch["run"]


def _render_dependabot_config(tmp_path: Path, release_ownership: str) -> str:
    """Render `template/.github/dependabot.yml.jinja` for one ownership.

    This only makes sense in the template-authoring repository itself:
    `copier.yml` and `template/` exist only here, never in a downstream
    generated project (`_subdirectory: template` in copier.yml deliberately
    excludes both from the rendered output), and `copier` is likewise only a
    template-authoring dependency (root `pyproject.toml`), never a generated
    project's own runtime/test dependency.
    """
    copier = pytest.importorskip("copier")
    if (
        not (REPO_ROOT / "copier.yml").is_file()
        or not (REPO_ROOT / "template").is_dir()
    ):
        pytest.skip(
            "requires the template-authoring repository's own copier.yml "
            "and template/ tree, absent in a generated project (Issue #771)"
        )
    source = tmp_path / "source"
    if not source.exists():
        source.mkdir()
        shutil.copy2(REPO_ROOT / "copier.yml", source / "copier.yml")
        shutil.copytree(REPO_ROOT / "template", source / "template")
    project = tmp_path / f"project-{release_ownership}"
    copier.run_copy(
        str(source),
        project,
        data={
            "languages": ["python"],
            "project_description": "Dependabot prefix fixture.",
            "project_name": "Dependabot Prefix Fixture",
            "project_slug": "dependabot-prefix-fixture",
            "release_ownership": release_ownership,
            "repository_url": "https://github.com/example/dependabot-prefix-fixture",
            "security_reporting_channel": "Use the private security contact.",
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )
    return (project / ".github/dependabot.yml").read_text(encoding="utf-8")


@pytest.mark.large
def test_csarc_owned_projects_split_release_and_dev_dependency_prefixes(
    tmp_path: Path,
) -> None:
    """Issue #755: only a project whose release CSARC owns needs this."""
    config = _render_dependabot_config(tmp_path, "csarc-owned")
    parsed = yaml.safe_load(config)
    uv_update = next(
        update
        for update in parsed["updates"]
        if update["package-ecosystem"] == "uv"
    )

    assert uv_update["commit-message"] == {
        "prefix": "fix",
        "prefix-development": "build",
    }


@pytest.mark.large
def test_non_csarc_owned_projects_keep_the_dependabot_default(
    tmp_path: Path,
) -> None:
    """A product with its own release process is not forced into this."""
    config = _render_dependabot_config(tmp_path, "verification-only")
    parsed = yaml.safe_load(config)
    uv_update = next(
        update
        for update in parsed["updates"]
        if update["package-ecosystem"] == "uv"
    )

    assert "commit-message" not in uv_update


@pytest.mark.large
def test_github_actions_ecosystem_never_gets_a_release_prefix(
    tmp_path: Path,
) -> None:
    """Actions bumps only affect root CI; they must never trigger a release."""
    config = _render_dependabot_config(tmp_path, "csarc-owned")
    parsed = yaml.safe_load(config)
    actions_update = next(
        update
        for update in parsed["updates"]
        if update["package-ecosystem"] == "github-actions"
    )

    assert "commit-message" not in actions_update
