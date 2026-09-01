"""Tests for the minimal immutable release bundle."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def clean_environment() -> dict[str, str]:
    """Keep fixture subprocesses out of the parent coverage session."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_")
        and key not in {"COVERAGE_FILE", "COVERAGE_PROCESS_START"}
    }


def run(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one fixture command."""
    return subprocess.run(  # noqa: S603
        arguments,
        cwd=cwd,
        check=True,
        capture_output=True,
        env=clean_environment(),
        text=True,
    )


def repository(tmp_path: Path) -> Path:
    """Create one tagged release fixture without language build tools."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/release_bundle.py", root / "scripts")
    shutil.copy2(ROOT / "scripts/release_policy.py", root / "scripts")
    (root / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "simple",
                "packages": {".": {"component": "fixture"}},
            }
        ),
        encoding="utf-8",
    )
    (root / ".release-please-manifest.json").write_text(
        '{".": "1.2.3"}\n', encoding="utf-8"
    )
    (root / "version.txt").write_text("1.2.3\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.2.3 (2026-09-01)\n", encoding="utf-8"
    )
    run("git", "init", "-b", "main", cwd=root)
    run("git", "config", "user.email", "test@example.invalid", cwd=root)
    run("git", "config", "user.name", "Test", cwd=root)
    run("git", "add", ".", cwd=root)
    run("git", "commit", "-m", "chore: release 1.2.3", cwd=root)
    run("git", "tag", "v1.2.3", cwd=root)
    return root


def invoke(root: Path, output: Path, action: str, tag: str = "v1.2.3") -> None:
    """Run the fixture's release bundle entry point."""
    run(
        "python3",
        "scripts/release_bundle.py",
        action,
        "--tag",
        tag,
        "--output",
        str(output),
        cwd=root,
    )


def complete_bundle(root: Path, output: Path) -> None:
    """Prepare and finalize one fixture bundle."""
    invoke(root, output, "prepare")
    (output / "sbom.spdx.json").write_text(
        '{"spdxVersion":"SPDX-2.3","SPDXID":"SPDXRef-DOCUMENT"}\n',
        encoding="utf-8",
    )
    invoke(root, output, "finalize")


def test_bundle_is_repeatable_and_verifiable(tmp_path: Path) -> None:
    """Allow a release run to rebuild and verify the exact same tag."""
    root = repository(tmp_path)
    output = tmp_path / "bundle"
    complete_bundle(root, output)
    invoke(root, output, "verify")

    run(
        "python3",
        "scripts/release_bundle.py",
        "candidate",
        "--output",
        str(output),
        cwd=root,
    )

    complete_bundle(root, output)
    invoke(root, output, "verify")


@pytest.mark.parametrize("failure", ["missing", "tampered", "wrong-tag"])
def test_bundle_fails_closed(tmp_path: Path, failure: str) -> None:
    """Reject missing files, changed bytes, and a tag for another commit."""
    root = repository(tmp_path)
    output = tmp_path / "bundle"
    complete_bundle(root, output)

    if failure == "missing":
        (output / "sbom.spdx.json").unlink()
    elif failure == "tampered":
        (output / "sbom.spdx.json").write_text("{}\n", encoding="utf-8")
    else:
        (root / "after.txt").write_text("later\n", encoding="utf-8")
        run("git", "add", ".", cwd=root)
        run("git", "commit", "-m", "fix: later", cwd=root)

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/release_bundle.py",
            "verify",
            "--tag",
            "v1.2.3",
            "--output",
            str(output),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        env=clean_environment(),
        text=True,
    )
    assert result.returncode != 0
