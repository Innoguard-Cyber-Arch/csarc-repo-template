"""Regression tests for dependency update and vulnerability automation."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parents[1]


def test_dependabot_uses_three_day_cooldown() -> None:
    """Keep routine updates observable without delaying security updates."""
    config = yaml.safe_load(
        (REPO_ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    )
    updates = config["updates"]

    profile_path = REPO_ROOT / ".csarc/profile.json"
    expected = {"github-actions", "uv"}
    if profile_path.exists():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        language = profile["language"]
        expected = {"github-actions"}
        if language in {"python", "python-typescript"}:
            expected.add("uv")
        if language in {"typescript", "python-typescript"}:
            expected.add("npm")
        if profile.get("container", {}).get("mode") != "none":
            expected.add("docker")

    assert {update["package-ecosystem"] for update in updates} == expected
    assert all(update["cooldown"]["default-days"] == 3 for update in updates)
    assert all(update["schedule"]["interval"] == "weekly" for update in updates)


def test_scheduled_scan_is_a_thin_local_wrapper() -> None:
    """Keep schedules and permissions in YAML while scan logic stays local."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/osv.yml").read_text(encoding="utf-8")
    )
    triggers = workflow.get("on", workflow.get(True))
    scan = workflow["jobs"]["scan"]

    assert set(triggers) == {"workflow_dispatch", "schedule"}
    assert workflow["permissions"] == {"contents": "read"}
    assert scan["timeout-minutes"] == 10
    assert set(scan) >= {"runs-on", "steps"}
    assert scan["steps"][-1]["run"] == "./scripts/verify-dependencies"


def test_local_scan_calls_the_pinned_tool_contract(tmp_path: Path) -> None:
    """Use one local command from both PR and scheduled workflows."""
    log = tmp_path / "arguments"
    scanner = tmp_path / "osv-scanner"
    scanner.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > {log!s}\n",
        encoding="utf-8",
    )
    scanner.chmod(scanner.stat().st_mode | stat.S_IXUSR)

    subprocess.run(  # noqa: S603
        [REPO_ROOT / "scripts/verify-dependencies"],
        check=True,
        env=os.environ | {"CSARC_OSV_SCANNER": str(scanner)},
    )

    assert log.read_text(encoding="utf-8").splitlines() == [
        "scan",
        "source",
        "--lockfile",
        "uv.lock",
    ]


def test_local_scan_propagates_vulnerability_failure(tmp_path: Path) -> None:
    """Block the caller when OSV reports a disclosed vulnerability."""
    scanner = tmp_path / "osv-scanner"
    scanner.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    scanner.chmod(scanner.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(  # noqa: S603
        [REPO_ROOT / "scripts/verify-dependencies"],
        check=False,
        env=os.environ | {"CSARC_OSV_SCANNER": str(scanner)},
    )

    assert result.returncode == 1


def test_restored_files_have_no_archive_copy() -> None:
    """Keep one authoritative copy after a workflow is restored."""
    archive = REPO_ROOT / "archive/ci-cd/2026-08-27"
    if not archive.exists():
        return
    assert not (archive / "root-dependabot.yml").exists()
    assert not (archive / "root-workflows/osv.yml").exists()
