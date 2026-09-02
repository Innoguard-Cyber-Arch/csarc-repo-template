"""Generated-repository checks for optional template update notices."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml
from copier import run_copy

ROOT = Path(__file__).parents[1]

# Stands in for the real `copier` binary. `--quiet` reports the outcome via
# exit code (0 up to date, 2 update available, anything else an error); the
# follow-up `--output-format json` call only runs after a 2, so it always
# succeeds with fixed version numbers.
_COPIER_STUB = """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "check-update" ]]; then
  for arg in "$@"; do
    if [[ "$arg" == "--output-format" ]]; then
      echo '{"current_version": "1.0.0", "latest_version": "1.1.0"}'
      exit 0
    fi
  done
  exit "${COPIER_STUB_EXIT:-0}"
fi
echo "unexpected copier invocation: $*" >&2
exit 1
"""

# Stands in for the real `gh` binary. Logs every invocation so a test can
# assert which subcommands ran, and reports at most one open Issue number
# from $GH_STUB_EXISTING_ISSUE so both the create and the edit branch of
# check-template-update are reachable.
_GH_STUB = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$GH_LOG"
if [[ "$1" == "issue" && "$2" == "list" ]]; then
  printf '%s\\n' "${GH_STUB_EXISTING_ISSUE:-}"
fi
"""


def _write_stub(path: Path, content: str) -> None:
    """Write an executable stub script."""
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run_checker(
    tmp_path: Path, *, copier_exit: int, existing_issue: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the real check-template-update script against stubbed tools."""
    project = tmp_path / "project"
    project.mkdir()
    script = project / "check-template-update"
    shutil.copy2(ROOT / "template/scripts/check-template-update", script)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub(bin_dir / "copier", _COPIER_STUB)
    _write_stub(bin_dir / "gh", _GH_STUB)
    gh_log = tmp_path / "gh.log"

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["COPIER_STUB_EXIT"] = str(copier_exit)
    env["GH_STUB_EXISTING_ISSUE"] = existing_issue
    env["GH_LOG"] = str(gh_log)

    result = subprocess.run(  # noqa: S603
        [str(script)],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, gh_log


def test_check_template_update_is_a_noop_when_already_current(
    tmp_path: Path,
) -> None:
    """Exit 0 from `copier check-update --quiet` must skip every gh call."""
    result, gh_log = _run_checker(tmp_path, copier_exit=0, existing_issue="")
    assert result.returncode == 0
    assert "latest" in result.stdout.lower()
    assert not gh_log.exists()


@pytest.mark.parametrize(
    ("existing_issue", "expected", "unexpected"),
    [
        ("", "issue create", "issue edit"),
        ("42", "issue edit 42", "issue create"),
    ],
)
def test_check_template_update_maintains_one_notice_issue(
    tmp_path: Path, existing_issue: str, expected: str, unexpected: str
) -> None:
    """A real update creates one Issue, or refreshes the existing one."""
    result, gh_log = _run_checker(
        tmp_path, copier_exit=2, existing_issue=existing_issue
    )
    assert result.returncode == 0
    log = gh_log.read_text(encoding="utf-8")
    assert expected in log
    assert unexpected not in log


def test_check_template_update_fails_closed_on_check_error(
    tmp_path: Path,
) -> None:
    """An unexpected `check-update` exit code must propagate, not vanish."""
    result, gh_log = _run_checker(tmp_path, copier_exit=1, existing_issue="")
    assert result.returncode == 1
    assert "failed" in result.stderr.lower()
    assert not gh_log.exists()


@pytest.mark.parametrize("enabled", [False, True])
def test_template_update_notification_is_opt_in(
    tmp_path: Path, enabled: bool
) -> None:
    """Generate the updater only when the repository selected it."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "project"
    run_copy(
        str(source),
        project,
        data={
            "enable_template_update_notifications": enabled,
            "languages": [],
            "project_description": "A generated update-notification fixture.",
            "project_name": "Update notification fixture",
            "project_slug": "update-notification-fixture",
            "repository_url": (
                "https://github.com/example/update-notification-fixture"
            ),
            "security_reporting_channel": "Use the private security contact.",
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    workflow_path = project / ".github/workflows/template-update.yml"
    checker_path = project / "scripts/check-template-update"
    assert workflow_path.exists() is enabled
    assert checker_path.exists() is enabled
    assert (
        "每週一或手動執行 template update workflow"
        in (project / "README.md").read_text(encoding="utf-8")
    ) is enabled

    if not enabled:
        return

    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert workflow["permissions"] == {
        "contents": "read",
        "issues": "write",
    }
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert set(workflow["jobs"]) == {"check"}
    assert workflow["jobs"]["check"]["timeout-minutes"] == 10
    source = workflow_path.read_text(encoding="utf-8")
    assert "run: ./scripts/check-template-update" in source
    assert "CSARC_TEMPLATE_READ_TOKEN" in source
    assert "pull_request" not in source


def test_template_repository_does_not_run_generated_update_notices() -> None:
    """Keep Copier provenance checks in generated repositories only."""
    assert not (ROOT / ".github/workflows/template-update.yml").exists()
