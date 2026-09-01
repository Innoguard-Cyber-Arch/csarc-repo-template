"""Regression tests for dependency update and vulnerability automation."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]


def test_dependabot_uses_three_day_cooldown() -> None:
    """Keep routine updates observable without delaying security updates."""
    config = (REPO_ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    ecosystems = set(
        re.findall(r"^\s*- package-ecosystem:\s*(\S+)\s*$", config, re.M)
    )

    config_path = REPO_ROOT / ".csarc/config.yml"
    expected = {"github-actions", "uv"}
    if config_path.exists():
        languages = set(
            subprocess.run(
                [sys.executable, "scripts/csarc_config.py", "languages"],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            .stdout.strip()
            .split(",")
        )
        expected = {"github-actions"}
        if "python" in languages:
            expected.add("uv")
        if "typescript" in languages:
            expected.add("npm")
        if "rust" in languages:
            expected.add("cargo")
        container_match = re.search(
            r"^container_mode:\s*(\S+)\s*$",
            config_path.read_text(encoding="utf-8"),
            re.M,
        )
        container_mode = container_match.group(1) if container_match else "none"
        if container_mode != "none":
            expected.add("docker")
    assert ecosystems == expected
    assert len(re.findall(r"^\s+default-days:\s*3\s*$", config, re.M)) == len(
        ecosystems
    )
    assert len(re.findall(r"^\s+interval:\s*weekly\s*$", config, re.M)) == len(
        ecosystems
    )


def test_scheduled_scan_is_a_thin_local_wrapper() -> None:
    """Keep schedules and permissions in YAML while scan logic stays local."""
    workflow = (REPO_ROOT / ".github/workflows/osv.yml").read_text(
        encoding="utf-8"
    )

    assert "on:\n  workflow_dispatch:\n  schedule:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "    runs-on: ubuntu-latest" in workflow
    assert "    timeout-minutes: 10" in workflow
    assert workflow.rstrip().endswith("- run: ./scripts/verify-dependencies")


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
    removed_delivery_workflows = {
        "delivery-maintenance.yml",
        "dev-next-close.yml",
        "live-integration.yml",
        "promotion-post-merge.yml",
        "promotion.yml",
        "python-version-policy.yml",
        "release-consumption.yml",
        "release-follow-up-policy.yml",
        "release-please.yml",
        "release-template.yml",
    }
    assert not removed_delivery_workflows.intersection(
        path.name for path in (archive / "root-workflows").glob("*")
    )
    assert not (
        archive / "template-workflows/delivery-maintenance.yml"
    ).exists()
    assert not (archive / "template-workflows/dev-next-close.yml").exists()
    assert not (archive / "template-workflows/promotion.yml").exists()
    assert not (archive / "template-workflows/release-please.yml").exists()
    assert not (
        archive / "template-workflows/template-update.yml.jinja"
    ).exists()
