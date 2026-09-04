"""Policy-toggle regression tests for scripts/apply-repository-settings.sh.

Issue #532 lets a project opt out of one template-owned policy area at a
time via `.csarc/config.yml` (`policy_repository_settings`,
`policy_actions_permissions`, `policy_labels`, `policy_branch_ruleset`, and
the existing `release_immutable_releases` contract for
policies/releases.json). These tests run the real script end to end against
a fake `gh` CLI and assert that different policy combinations produce the
correct generated-repo behavior: disabled areas are skipped (no mutating
`gh` call, a `SKIPPED`/`SKIP` line, no drift accounted in `check`), enabled
areas are still applied and checked exactly as before, and a legacy
`.csarc/config.yml` predating this feature keeps every area on by default.

The branch-Ruleset domain's `check` drift comparison has a preexisting,
unrelated bug (`scripts/apply-repository-settings.sh` computes
`desired_by_type["required_status_checks"]`, a rule type that
`policies/rulesets.json` no longer declares -- see git history for the
commit that removed it) that always raises before this feature's code runs.
`policy_branch_ruleset=false` is used to keep `check`/`apply` scenarios
independent of that unrelated failure; the toggle's "on" path is instead
verified through `plan`, which never reaches that comparison.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_SOURCE = ROOT / "scripts" / "apply-repository-settings.sh"
CONFIG_READER_SOURCE = ROOT / "scripts" / "csarc_config.py"
POLICIES_SOURCE = ROOT / "policies"
REPO_SLUG = "acme/repo-test"

FAKE_GH = r"""#!/usr/bin/env bash
set -euo pipefail
: "${FAKE_GH_LOG:?}"
printf '%s\n' "$*" >>"$FAKE_GH_LOG"

case "$1" in
  api)
    shift
    method="GET"
    jq_filter=""
    path=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --method) method="$2"; shift 2 ;;
        --jq) jq_filter="$2"; shift 2 ;;
        --input) shift 2 ;;
        --paginate|--slurp) shift ;;
        -f) shift 2 ;;
        *)
          if [[ -z "$path" ]]; then path="$1"; fi
          shift
          ;;
      esac
    done
    case "$path" in
      */teams)
        team_json='[[{"slug": "platform", "permission": "admin",'
        team_json+=' "permissions": {"admin": true}}]]'
        echo "$team_json"
        ;;
      */rulesets)
        echo "[]"
        ;;
      */immutable-releases)
        if [[ "$method" == "PUT" ]]; then
          echo "{}"
        else
          echo '{"enabled": true}'
        fi
        ;;
      */actions/permissions/workflow)
        if [[ "$method" == "PUT" ]]; then
          echo "{}"
        else
          cat "$FAKE_GH_ACTIONS_STATE"
        fi
        ;;
      orgs/*|users/*)
        echo "team"
        ;;
      repos/*)
        if [[ "$method" == "PATCH" ]]; then
          echo "{}"
        elif [[ "$jq_filter" == *"@tsv"* ]]; then
          printf 'acme\tOrganization\tprivate\ttrue\tmain\n'
        else
          cat "$FAKE_GH_REPOSITORY_STATE"
        fi
        ;;
      *)
        echo "fake gh: unhandled api path: $path" >&2
        exit 1
        ;;
    esac
    ;;
  label)
    shift
    sub="$1"; shift
    case "$sub" in
      list)
        if [[ "$*" == *"name,color,description"* ]]; then
          cat "$FAKE_GH_LABELS_STATE"
        else
          cat "$FAKE_GH_LABEL_NAMES"
        fi
        ;;
      create) exit 0 ;;
      delete) exit 0 ;;
      *)
        echo "fake gh: unhandled label subcommand: $sub" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "fake gh: unhandled command: $1" >&2
    exit 1
    ;;
esac
"""

CONFIG_CSARC_OWNED = """\
project_mode: existing
release_ownership: csarc-owned
release_workflow: .github/workflows/release.yml
release_required_inputs: []
release_ownership_reason: CSARC owns the only version and GitHub Release
  workflow.
release_settings_owner: csarc-admin
release_immutable_releases: required
policy_repository_settings: true
policy_actions_permissions: true
policy_labels: true
policy_branch_ruleset: false
"""

CONFIG_VERIFICATION_ONLY_ALL_DISABLED = """\
project_mode: existing
release_ownership: verification-only
release_workflow: ''
release_required_inputs: []
release_ownership_reason: No product release writer was detected; CSARC
  verifies only.
release_settings_owner: none
release_immutable_releases: not-required
policy_repository_settings: false
policy_actions_permissions: false
policy_labels: false
policy_branch_ruleset: false
"""

CONFIG_LEGACY_NO_POLICY_KEYS = "languages: []\n"


def _make_repo(tmp_path: Path, config_yaml: str) -> Path:
    """Assemble a minimal repo fixture the real script can run against."""
    repo = tmp_path / "repo"
    scripts_dir = repo / "scripts"
    scripts_dir.mkdir(parents=True)
    script_target = scripts_dir / "apply-repository-settings.sh"
    script_target.write_text(
        SCRIPT_SOURCE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    script_target.chmod(script_target.stat().st_mode | stat.S_IEXEC)
    config_reader_target = scripts_dir / "csarc_config.py"
    config_reader_target.write_text(
        CONFIG_READER_SOURCE.read_text(encoding="utf-8"), encoding="utf-8"
    )

    policies_dir = repo / "policies"
    policies_dir.mkdir()
    for policy_file in POLICIES_SOURCE.glob("*.json"):
        (policies_dir / policy_file.name).write_text(
            policy_file.read_text(encoding="utf-8"), encoding="utf-8"
        )

    github_dir = repo / ".github"
    github_dir.mkdir()
    (github_dir / "CODEOWNERS").write_text(
        "* @acme/platform\n", encoding="utf-8"
    )

    csarc_dir = repo / ".csarc"
    csarc_dir.mkdir()
    (csarc_dir / "config.yml").write_text(config_yaml, encoding="utf-8")

    return repo


def _make_fake_gh(tmp_path: Path) -> Path:
    """Write the fake `gh` binary and return its containing directory."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake_gh = bin_dir / "gh"
    fake_gh.write_text(FAKE_GH, encoding="utf-8")
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IEXEC)
    return bin_dir


def _run(
    repo: Path,
    tmp_path: Path,
    mode: str,
    *,
    log_path: Path,
) -> subprocess.CompletedProcess[str]:
    """Invoke the fixture's own copy of apply-repository-settings.sh."""
    bin_dir = _make_fake_gh(tmp_path)
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["GH_REPO"] = REPO_SLUG
    env["FAKE_GH_LOG"] = str(log_path)
    env["FAKE_GH_REPOSITORY_STATE"] = str(ROOT / "policies" / "repository.json")
    env["FAKE_GH_ACTIONS_STATE"] = str(ROOT / "policies" / "actions.json")
    env["FAKE_GH_LABELS_STATE"] = str(ROOT / "policies" / "labels.json")
    label_names = tmp_path / "label-names.txt"
    labels = json.loads(
        (ROOT / "policies" / "labels.json").read_text(encoding="utf-8")
    )
    label_names.write_text(
        "\n".join(label["name"] for label in labels) + "\n", encoding="utf-8"
    )
    env["FAKE_GH_LABEL_NAMES"] = str(label_names)
    return subprocess.run(  # noqa: S603
        [str(repo / "scripts" / "apply-repository-settings.sh"), mode],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_disabled_policies_are_skipped_in_check_and_apply(
    tmp_path: Path,
) -> None:
    """Every disabled policy area is skipped, not silently failed or run."""
    repo = _make_repo(tmp_path, CONFIG_VERIFICATION_ONLY_ALL_DISABLED)

    check_log = tmp_path / "gh-check.log"
    check_result = _run(repo, tmp_path, "check", log_path=check_log)
    check_output = check_result.stdout + check_result.stderr
    assert check_result.returncode == 0, check_output
    assert (
        "SKIPPED policies/repository.json (policy_repository_settings=false"
        in check_output
    )
    assert (
        "SKIPPED policies/releases.json (release_immutable_releases="
        "not-required" in check_output
    )
    assert (
        "SKIPPED policies/actions.json (policy_actions_permissions=false"
        in check_output
    )
    assert "SKIPPED policies/labels.json (policy_labels=false" in check_output
    assert (
        "SKIPPED policies/rulesets.json (policy_branch_ruleset=false"
        in check_output
    )
    assert "All observable repository settings match policy." in check_output

    apply_log = tmp_path / "gh-apply.log"
    apply_result = _run(repo, tmp_path, "apply", log_path=apply_log)
    apply_output = apply_result.stdout + apply_result.stderr
    assert apply_result.returncode == 0, apply_output
    assert "- SKIP policies/repository.json" in apply_output
    assert "- SKIP policies/releases.json" in apply_output
    assert "- SKIP policies/actions.json" in apply_output
    assert "- SKIP policies/labels.json" in apply_output
    assert "- SKIP policies/rulesets.json" in apply_output
    assert (
        "branch protection Ruleset is disabled by policy_branch_ruleset=false"
        in apply_output
    )

    full_log = check_log.read_text(encoding="utf-8") + apply_log.read_text(
        encoding="utf-8"
    )
    assert "--method PATCH repos/acme/repo-test" not in full_log
    assert "immutable-releases" not in full_log
    assert "actions/permissions/workflow" not in full_log
    assert "label create" not in full_log
    assert "label delete" not in full_log


def test_enabled_policies_are_still_applied_and_checked(
    tmp_path: Path,
) -> None:
    """Enabling an area keeps its exact pre-toggle apply/check behavior."""
    repo = _make_repo(tmp_path, CONFIG_CSARC_OWNED)

    check_log = tmp_path / "gh-check.log"
    check_result = _run(repo, tmp_path, "check", log_path=check_log)
    check_output = check_result.stdout + check_result.stderr
    assert check_result.returncode == 0, check_output
    assert "Repository settings match policies/repository.json." in check_output
    assert "Immutable Releases match policies/releases.json." in check_output
    assert (
        "Actions workflow permissions match policies/actions.json."
        in check_output
    )
    assert (
        "Policy labels match policies/labels.json; extra labels are allowed."
        in check_output
    )
    assert (
        "SKIPPED policies/rulesets.json (policy_branch_ruleset=false"
        in check_output
    )

    apply_log = tmp_path / "gh-apply.log"
    apply_result = _run(repo, tmp_path, "apply", log_path=apply_log)
    apply_output = apply_result.stdout + apply_result.stderr
    assert apply_result.returncode == 0, apply_output
    assert (
        "branch protection Ruleset is disabled by policy_branch_ruleset=false"
        in apply_output
    )

    full_log = apply_log.read_text(encoding="utf-8")
    assert "--method PATCH repos/acme/repo-test" in full_log
    assert "--method PUT repos/acme/repo-test/immutable-releases" in full_log
    assert (
        "--method PUT repos/acme/repo-test/actions/permissions/workflow"
        in full_log
    )
    label_names = json.loads(
        (ROOT / "policies" / "labels.json").read_text(encoding="utf-8")
    )
    for label in label_names:
        assert f"label create {label['name']}" in full_log


def test_legacy_config_without_policy_keys_defaults_every_area_on(
    tmp_path: Path,
) -> None:
    """A pre-#532 .csarc/config.yml keeps applying every policy area."""
    repo = _make_repo(tmp_path, CONFIG_LEGACY_NO_POLICY_KEYS)

    plan_log = tmp_path / "gh-plan.log"
    plan_result = _run(repo, tmp_path, "plan", log_path=plan_log)
    plan_output = plan_result.stdout + plan_result.stderr
    assert plan_result.returncode == 0, plan_output
    assert "- APPLY policies/repository.json" in plan_output
    assert "- APPLY policies/releases.json (immutable Releases)" in plan_output
    assert (
        "- APPLY policies/actions.json when account policy permits it"
        in plan_output
    )
    assert (
        "- APPLY policies/labels.json (create or update policy labels)"
        in plan_output
    )
    assert "- APPLY policies/rulesets.json (enforced by GitHub)" in plan_output
    assert (
        "No changes applied. Re-run with 'apply' after review." in plan_output
    )


@pytest.mark.parametrize(
    "toggle_key",
    [
        "policy_repository_settings",
        "policy_actions_permissions",
        "policy_labels",
        "policy_branch_ruleset",
    ],
)
def test_policy_toggle_value_is_readable_through_csarc_config(
    tmp_path: Path, toggle_key: str
) -> None:
    """Each toggle round-trips through the shared config reader as a bool."""
    repo = _make_repo(tmp_path, f"languages: []\n{toggle_key}: false\n")
    result = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/csarc_config.py", toggle_key],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "false"
