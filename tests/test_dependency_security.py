"""Regression tests for dependency update and vulnerability automation."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
SUPPORTED_LOCKFILES = (
    "uv.lock",
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "Cargo.lock",
    "go.mod",
)


def test_dependabot_uses_three_day_cooldown() -> None:
    """Keep routine updates observable without delaying security updates."""
    config = (REPO_ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    ecosystems = set(
        re.findall(r"^\s*- package-ecosystem:\s*(\S+)\s*$", config, re.M)
    )

    expected = {"github-actions", "uv"}
    if (REPO_ROOT / ".csarc/config.yml").exists():
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

    lockfiles = [
        name for name in SUPPORTED_LOCKFILES if (REPO_ROOT / name).is_file()
    ]
    expected = ["scan", "source"]
    for lockfile in lockfiles:
        expected.extend(("--lockfile", lockfile))
    assert log.read_text(encoding="utf-8").splitlines() == expected


@pytest.mark.parametrize("lockfile", ["Cargo.lock", "go.mod"])
def test_local_scan_includes_single_module_lockfile(
    tmp_path: Path, lockfile: str
) -> None:
    """Scan a Rust or Go module even when it has no other lockfile."""
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts/verify-dependencies", scripts)
    (project / lockfile).touch()

    log = tmp_path / "arguments"
    scanner = tmp_path / "osv-scanner"
    scanner.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > {log!s}\n",
        encoding="utf-8",
    )
    scanner.chmod(scanner.stat().st_mode | stat.S_IXUSR)

    subprocess.run(  # noqa: S603
        [scripts / "verify-dependencies"],
        check=True,
        env=os.environ | {"CSARC_OSV_SCANNER": str(scanner)},
    )

    assert log.read_text(encoding="utf-8").splitlines() == [
        "scan",
        "source",
        "--lockfile",
        lockfile,
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
