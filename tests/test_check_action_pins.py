"""Tests for the cross-repo action-pin consistency check (Issue #755)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

check_action_pins = importlib.import_module("check_action_pins")

SHA_A = "a" * 40
SHA_B = "b" * 40


def write(path: Path, *uses_lines: str) -> Path:
    """Write a minimal workflow-shaped file with the given `uses:` lines."""
    body = "\n".join(f"      - uses: {line}" for line in uses_lines)
    path.write_text(f"jobs:\n  job:\n    steps:\n{body}\n", encoding="utf-8")
    return path


def test_matching_pins_pass_cleanly(tmp_path: Path) -> None:
    """The same action pinned to the same commit everywhere is not drift."""
    one = write(tmp_path / "one.yml", f"actions/checkout@{SHA_A} # v1")
    two = write(tmp_path / "two.yml", f"actions/checkout@{SHA_A} # v1")

    assert check_action_pins.check([one, two], tmp_path) == []


def test_disagreeing_pins_are_reported(tmp_path: Path) -> None:
    """A file pinning an older commit than the rest of the repo is drift."""
    write(tmp_path / "current.yml", f"actions/checkout@{SHA_A} # v2")
    write(tmp_path / "also-current.yml", f"actions/checkout@{SHA_A} # v2")
    stale = write(tmp_path / "stale.jinja", f"actions/checkout@{SHA_B} # v1")

    errors = check_action_pins.check(
        [tmp_path / "current.yml", tmp_path / "also-current.yml", stale],
        tmp_path,
    )

    assert len(errors) == 1
    assert "actions/checkout" in errors[0]
    assert "stale.jinja" in errors[0]
    assert SHA_A in errors[0]


def test_unrelated_actions_do_not_interfere(tmp_path: Path) -> None:
    """Two different actions each agreeing internally is not drift."""
    path = write(
        tmp_path / "mixed.yml",
        f"actions/checkout@{SHA_A} # v1",
        f"astral-sh/setup-uv@{SHA_B} # v1",
    )

    assert check_action_pins.check([path], tmp_path) == []


def test_workflow_files_finds_root_and_template_paths(tmp_path: Path) -> None:
    """The default file discovery covers root, template, and .jinja."""
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "template/.github/workflows").mkdir(parents=True)
    write(
        tmp_path / ".github/workflows/ci.yml", f"actions/checkout@{SHA_A} # v1"
    )
    write(
        tmp_path / "template/.github/workflows/ci.yml",
        f"actions/checkout@{SHA_A} # v1",
    )
    write(
        tmp_path / "template/.github/workflows/release.yml.jinja",
        f"actions/checkout@{SHA_A} # v1",
    )

    found = {
        str(path.relative_to(tmp_path))
        for path in check_action_pins.workflow_files(tmp_path)
    }

    assert found == {
        ".github/workflows/ci.yml",
        "template/.github/workflows/ci.yml",
        "template/.github/workflows/release.yml.jinja",
    }


def test_cli_fails_closed_on_real_repo_drift(tmp_path: Path) -> None:
    """The CLI exits non-zero and names the file when pins disagree."""
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "template/.github/workflows").mkdir(parents=True)
    write(
        tmp_path / ".github/workflows/ci.yml", f"actions/checkout@{SHA_A} # v2"
    )
    write(
        tmp_path / "template/.github/workflows/ci.yml.jinja",
        f"actions/checkout@{SHA_B} # v1",
    )

    exit_code = check_action_pins.main(["--root", str(tmp_path)])

    assert exit_code == 1
