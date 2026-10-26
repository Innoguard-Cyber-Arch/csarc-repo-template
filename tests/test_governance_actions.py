"""Tests for reviewer assignment and optional governance drift automation."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from copier import run_copy

from csarc_cli import cli

ROOT = Path(__file__).resolve().parents[1]


def run_reviewer_assignment(
    tmp_path: Path, collaborators: str, author: str = "alice", number: int = 1
) -> subprocess.CompletedProcess[str]:
    """Run the repository-local reviewer logic with a fake GitHub CLI."""
    fixture = tmp_path / "fixture"
    (fixture / "scripts").mkdir(parents=True)
    script = fixture / "scripts/request-reviewer"
    shutil.copy2(ROOT / "scripts/request-reviewer", script)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> "$GH_CAPTURE"\n'
        'if [[ "$*" == *"/collaborators?"* ]]; then\n'
        '  printf "%s\\n" "$GH_COLLABORATORS"\n'
        "fi\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    capture = tmp_path / "gh-arguments"
    env = os.environ | {
        "GITHUB_REPOSITORY": "example/project",
        "GH_CAPTURE": str(capture),
        "GH_COLLABORATORS": collaborators,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "PR_AUTHOR": author,
        "PR_NUMBER": str(number),
    }
    return subprocess.run(  # noqa: S603
        [script],
        cwd=fixture,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def run_governance_drift_check(
    tmp_path: Path,
    check_output: str,
    check_exit: int,
    *,
    issue_number: str = "",
    body_store: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the drift wrapper with deterministic checker and GitHub responses."""
    fixture = tmp_path / "drift-fixture"
    scripts = fixture / "scripts"
    shutil.copytree(ROOT / "scripts", scripts, dirs_exist_ok=True)
    drift_script = scripts / "check-governance-drift"
    settings_script = scripts / "apply-repository-settings.sh"
    settings_script.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$CHECK_OUTPUT"\n'
        'exit "$CHECK_EXIT"\n',
        encoding="utf-8",
    )
    settings_script.chmod(0o755)

    fake_bin = tmp_path / "drift-bin"
    fake_bin.mkdir(exist_ok=True)
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        r"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"$GH_CAPTURE"
case "$1 $2" in
  "issue list") printf '%s\n' "$GH_ISSUE_NUMBER" ;;
  "issue view") cat "$GH_BODY_STORE" ;;
  "api repos/example/project/issues/"*)
    printf '{"number":%s}\n' "${2##*/}"
    ;;
  "issue create"|"issue edit")
    action="$2"
    printf 'https://github.com/example/project/issues/6\n'
    shift 2
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--body-file" ]]; then
        cp "$2" "$GH_BODY_STORE"
        break
      fi
      shift
    done
    if [[ "$action" == "edit" ]]; then
      : >"$GH_EDIT_MARKER"
    fi
    ;;
  *) exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    capture = tmp_path / f"gh-{len(list(tmp_path.glob('gh-*')))}.log"
    stored_body = body_store or (tmp_path / "issue-body")
    env = os.environ | {
        "CHECK_EXIT": str(check_exit),
        "CHECK_OUTPUT": check_output,
        "GH_BODY_STORE": str(stored_body),
        "GH_CAPTURE": str(capture),
        "GH_EDIT_MARKER": str(tmp_path / "issue-edited"),
        "GH_ISSUE_NUMBER": issue_number,
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "example/project",
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    result = subprocess.run(  # noqa: S603
        [drift_script],
        cwd=fixture,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, capture


def test_reviewer_assignment_excludes_author(tmp_path: Path) -> None:
    """Request one eligible repository maintainer who is not the author."""
    result = run_reviewer_assignment(tmp_path, "alice\nbob", number=8)

    assert result.returncode == 0, result.stderr
    assert "Requested review from @bob" in result.stdout
    arguments = (tmp_path / "gh-arguments").read_text(encoding="utf-8")
    assert "reviewers[]=bob" in arguments
    assert "reviewers[]=alice" not in arguments


def test_reviewer_assignment_skips_when_only_author_remains(
    tmp_path: Path,
) -> None:
    """Do not turn an impossible request into a misleading merge gate."""
    result = run_reviewer_assignment(tmp_path, "Alice")

    assert result.returncode == 0, result.stderr
    assert "Reviewer assignment skipped" in result.stdout
    assert "requested_reviewers" not in (tmp_path / "gh-arguments").read_text(
        encoding="utf-8"
    )


def test_reviewer_assignment_rejects_invalid_api_data(
    tmp_path: Path,
) -> None:
    """Reject malformed reviewer names before making a GitHub API call."""
    result = run_reviewer_assignment(tmp_path, "not a login")

    assert result.returncode == 1
    assert "Bad login" in result.stderr
    assert "requested_reviewers" not in (tmp_path / "gh-arguments").read_text(
        encoding="utf-8"
    )


def test_reviewer_assignment_accepts_a_bot_author(tmp_path: Path) -> None:
    """A bot login (e.g. dependabot[bot]) is a valid PR author (#753)."""
    result = run_reviewer_assignment(
        tmp_path, "alice\nbob", author="dependabot[bot]", number=8
    )

    assert result.returncode == 0, result.stderr
    assert "Requested review from" in result.stdout


@pytest.mark.parametrize(
    ("option", "enabled"),
    [({}, True), ({"scheduled_checks": []}, False)],
)
@pytest.mark.large
def test_copier_governance_drift_option_is_complete(
    tmp_path: Path, option: dict[str, object], enabled: bool
) -> None:
    """Generate the default-on workflow while preserving an explicit opt-out."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / f"project-{enabled}"

    run_copy(
        str(source),
        project,
        data={
            "languages": [],
            "project_description": "Governance automation fixture.",
            "project_name": "Governance Fixture",
            "project_slug": "governance-fixture",
            "repository_url": "https://github.com/example/governance-fixture",
            "security_reporting_channel": "Use the private security contact.",
        }
        | option,
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    # The default local-first mode omits the event-driven hosted workflow
    # and, with no caller left, its reviewer-assignment script (#1077).
    assert not (project / ".github/workflows/governance-comment.yml").exists()
    assert not (project / ".csarc/scripts/request-reviewer").exists()
    assert not (project / ".csarc/REVIEWERS").exists()
    assert (
        project / ".github/workflows/governance-drift.yml"
    ).exists() is enabled
    assert (
        project / ".csarc/scripts/check-governance-drift"
    ).exists() is enabled
    if enabled:
        # The rendered schedule is weekly on Monday (#1289).
        rendered = (
            project / ".github/workflows/governance-drift.yml"
        ).read_text(encoding="utf-8")
        assert 'cron: "13 4 * * 1"' in rendered
        assert "workflow_dispatch:" in rendered


def schedule_crons(text: str) -> list[str]:
    """Return the cron expressions declared in one workflow file."""
    return [
        line.split("cron:", 1)[1].strip().strip('"')
        for line in text.splitlines()
        if line.strip().startswith("- cron:")
    ]


def test_governance_drift_runs_weekly_without_colliding() -> None:
    """Run drift weekly on Monday, apart from the other Monday jobs (#1289)."""
    workflows = ROOT / "template/.github/workflows"
    drift = schedule_crons(
        (workflows / "governance-drift.yml").read_text(encoding="utf-8")
    )
    others = schedule_crons(
        (workflows / "osv.yml").read_text(encoding="utf-8")
    ) + schedule_crons(
        (workflows / "template-update.yml.jinja").read_text(encoding="utf-8")
    )

    assert drift == ["13 4 * * 1"]
    minute, hour, day, month, weekday = drift[0].split()
    assert (day, month, weekday) == ("*", "*", "1")
    assert all((minute, hour) != tuple(other.split()[:2]) for other in others)
    # release-drift is a different check and stays daily.
    release = schedule_crons(
        (workflows / "release-drift.yml").read_text(encoding="utf-8")
    )
    assert release and release[0].split()[4] == "*"

    recommendation = cli.governance_drift_update_recommendation(
        {"scheduled_checks": []}, {}
    )
    assert recommendation is not None
    assert "weekly governance drift check" in recommendation
    assert "daily" not in recommendation


def test_degraded_drift_check_does_not_create_an_issue(tmp_path: Path) -> None:
    """Keep an unreadable setting distinct from actionable drift."""
    result, capture = run_governance_drift_check(
        tmp_path,
        "DEGRADED immutable Releases inspection: token cannot read setting.",
        0,
    )

    assert result.returncode == 0, result.stderr
    assert "degraded capability differences" in result.stdout
    assert not capture.exists()


def test_governance_drift_issue_is_created_once_and_only_updated_on_change(
    tmp_path: Path,
) -> None:
    """Avoid duplicate Issues and unchanged edit notifications."""
    body_store = tmp_path / "issue-body"
    first, first_capture = run_governance_drift_check(
        tmp_path, "Repository settings drift: first", 1, body_store=body_store
    )
    assert first.returncode == 1
    first_calls = first_capture.read_text(encoding="utf-8")
    assert "issue create" in first_calls
    assert "--assignee" not in first_calls
    assert "--type Bug" in first_calls
    assert "--remove-label bug" in first_calls

    second, second_capture = run_governance_drift_check(
        tmp_path,
        "Repository settings drift: first",
        1,
        issue_number="6",
        body_store=body_store,
    )
    assert second.returncode == 1
    assert "Governance drift is unchanged" in second.stdout
    assert "--body-file" not in second_capture.read_text(encoding="utf-8")

    third, third_capture = run_governance_drift_check(
        tmp_path,
        "Repository settings drift: changed",
        1,
        issue_number="6",
        body_store=body_store,
    )
    assert third.returncode == 1
    third_calls = third_capture.read_text(encoding="utf-8")
    assert "--body-file" in third_calls
    assert "issue create" not in third_calls


def test_update_preserves_governance_drift_opt_out_and_recommends_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep a saved false value while explaining the new-project default."""
    saved: dict[str, object] = {
        "enable_governance_drift_check": False,
        "project_mode": "new",
        "project_visibility": "private",
    }
    repository = cli.RepositoryContext(
        "example/project", "example", "organization", "private", "github", True
    )
    answers, update_data = cli.update_plan_answers(saved, {}, repository)
    recommendation = cli.governance_drift_update_recommendation(saved, {})

    # SPEC-009 migrates the retired toggle to scheduled_checks exactly.
    assert answers["scheduled_checks"] == []
    assert "enable_governance_drift_check" not in answers
    assert "enable_governance_drift_check" not in update_data
    assert recommendation is not None
    plan = cli.ResolvedPlan(
        mode="update",
        target=tmp_path / "example",
        revision=cli.Revision("v1", "a" * 40, "https://example.invalid"),
        repository=repository,
        answers={
            **answers,
            "release_immutable_releases": "required",
            "release_ownership": "csarc-owned",
            "release_ownership_reason": "CSARC owns the release workflow.",
            "release_required_inputs": [],
            "release_settings_owner": "csarc-admin",
            "release_workflow": ".github/workflows/release.yml",
        },
        capabilities={},
        update={
            "current_version": "v1",
            "current_sha": "a" * 40,
            "target_version": "v2",
            "target_sha": "b" * 40,
            "governance_drift_recommendation": recommendation,
        },
    )
    cli.print_plan(plan)
    assert capsys.readouterr().out.count("Recommendation:") == 1
    assert (
        cli.governance_drift_update_recommendation(
            saved, {"scheduled_checks": ""}
        )
        is None
    )


def test_governance_workflows_are_thin_and_least_privilege() -> None:
    """Keep events and permissions in YAML while logic stays local."""
    reviewer = (ROOT / ".github/workflows/governance-comment.yml").read_text(
        encoding="utf-8"
    )
    generated_reviewer = (
        ROOT / "template/.github/workflows/governance-comment.yml"
    ).read_text(encoding="utf-8")
    drift = (
        ROOT / "template/.github/workflows/governance-drift.yml"
    ).read_text(encoding="utf-8")

    assert reviewer == generated_reviewer.replace(".csarc/scripts/", "scripts/")
    root_script = (ROOT / "scripts/request-reviewer").read_text(
        encoding="utf-8"
    )
    generated_script = (
        ROOT / "template/.csarc/scripts/request-reviewer"
    ).read_text(encoding="utf-8")
    assert root_script == generated_script.replace(
        '${BASH_SOURCE[0]}")/../..', '${BASH_SOURCE[0]}")/..'
    ).replace("$repo_root/.csarc/REVIEWERS", "$repo_root/.github/REVIEWERS")
    assert not (ROOT / ".github/workflows/governance-drift.yml").exists()
    assert "pull_request_target:" in reviewer
    assert "ref: ${{ github.event.pull_request.base.sha }}" in reviewer
    assert "pull-requests: write" in reviewer
    assert "issues: write" not in reviewer
    assert "run: ./scripts/request-reviewer" in reviewer
    assert "timeout-minutes: 5" in reviewer

    assert "schedule:" in drift and "workflow_dispatch:" in drift
    assert "issues: write" in drift
    assert "pull-requests: write" not in drift
    assert "run: ./.csarc/scripts/check-governance-drift" in drift
    assert "timeout-minutes: 5" in drift


def test_docs_describe_a_weekly_governance_drift_check() -> None:
    """No doc still calls the governance drift schedule daily (#1289)."""
    stale = re.compile(
        r"(daily|每日|每天)[^。\n]{0,60}(governance[- _]drift|治理漂移|drift)"
        r"|(governance[- _]drift|治理漂移)[^。\n]{0,60}(daily|每日|每天)",
        re.IGNORECASE,
    )
    paths = [
        "README.md",
        "README.en.md",
        "docs/ci-policy.md",
        "site/content/_index.zh-tw.md",
        "site/content/_index.en.md",
        "site/data/config_examples.json",
        "site/data/testing/governance.json",
        "template/.csarc/docs/ci-policy.md.jinja",
        "template/.csarc/docs/csarc.md.jinja",
    ]
    for name in paths:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not stale.search(text), name


def test_docs_reflect_restored_governance_actions() -> None:
    """Docs must not claim restored governance Actions are still archived."""
    stale_archived_list = "Zizmor、remote governance、deployment"
    for path in (
        ROOT / "README.md",
        ROOT / "docs/ci-policy.md",
        ROOT / "template/.csarc/docs/ci-policy.md.jinja",
    ):
        text = path.read_text(encoding="utf-8")
        assert stale_archived_list not in text, path
        assert "governance-comment.yml" in text, path

    widget = (ROOT / "site/static/legacy-components.js").read_text(
        encoding="utf-8"
    )
    assert "The scheduled workflow is archived and does not run" not in widget
    # Issue #472 moved this code sample out of legacy-components.js into
    # site/data/config_examples.json (governance track, drift-schedule item),
    # server-rendered by the config-guidance shortcode; the underlying claim
    # this test protects (no stale "archived" wording) still applies there.
    config_examples = json.loads(
        (ROOT / "site/data/config_examples.json").read_text(encoding="utf-8")
    )
    drift_codes = " ".join(
        item["code"]["zh-tw"] + item["code"]["en"]
        for item in config_examples["tracks"]["governance"]["items"]
    )
    assert "The scheduled workflow is archived and does not run" not in (
        drift_codes
    )
    assert (
        "scheduled_checks: [governance-drift] generates the weekly workflow"
        in drift_codes
    )
