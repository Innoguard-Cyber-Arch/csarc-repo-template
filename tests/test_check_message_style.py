"""Regression tests for the script message pattern check (Issue #1219)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKERS = (
    ROOT / "scripts" / "check-message-style",
    ROOT / "template" / ".csarc" / "scripts" / "check-message-style",
)
OLD_SHELL = """#!/usr/bin/env bash
echo "old message without a pattern" >&2
echo "NOTICE: Old notice that already conforms."
"""
OLD_PYTHON = """import sys
print("legacy output")
"""


def git(root: Path, *args: str) -> str:
    """Run one git command in a fixture repository."""
    return subprocess.run(  # noqa: S603 - fixed git arguments in a temp repo
        ["git", "-C", str(root), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def run(
    root: Path, *args: str, checker: Path = CHECKERS[0]
) -> subprocess.CompletedProcess[str]:
    """Run the checker in a fixture repository."""
    return subprocess.run(  # noqa: S603 - the checker under test
        [str(checker), *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={k: v for k, v in os.environ.items() if k != "CSARC_CI_BASE"},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Return a generated-layout repository with old messages on main."""
    scripts = tmp_path / ".csarc" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "tool").write_text(OLD_SHELL, encoding="utf-8")
    (scripts / "tool.py").write_text(OLD_PYTHON, encoding="utf-8")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    git(tmp_path, "config", "user.name", "Fixture")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "checkout", "-q", "-b", "feature")
    return tmp_path


def append(repo: Path, name: str, text: str) -> None:
    """Append lines to one fixture script."""
    path = repo / ".csarc" / "scripts" / name
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def test_root_and_template_copies_are_identical() -> None:
    """The generated project receives the same checker as the root."""
    assert CHECKERS[0].read_bytes() == CHECKERS[1].read_bytes()


@pytest.mark.parametrize("checker", CHECKERS, ids=["root", "template"])
def test_conforming_new_messages_pass(repo: Path, checker: Path) -> None:
    """New messages that follow the four patterns pass in PR mode."""
    append(
        repo,
        "tool",
        "echo \"ERROR: Fetch failed: the remote is offline. Run 'git fetch'.\""
        " >&2\n"
        'echo "WARNING: Cache is stale: it is $age days old. Clear it." >&2\n'
        'echo "OK: Wrote $count files."\n'
        "die \"Lease is missing: no comment exists. Run 'lease acquire'.\"\n",
    )
    append(
        repo,
        "tool.py",
        'print(f"NOTICE: Checking {name}.")\n'
        'raise SystemExit("ERROR: Load failed: bad JSON. Fix the file.")\n',
    )
    result = run(repo, "--base", "main", checker=checker)
    assert result.returncode == 0, result.stderr
    assert "OK: Message pattern check passed for 6 messages." in result.stdout


@pytest.mark.parametrize("checker", CHECKERS, ids=["root", "template"])
def test_nonconforming_new_message_fails_with_location(
    repo: Path, checker: Path
) -> None:
    """A new message without a pattern fails and names file, line, pattern."""
    append(repo, "tool", 'echo "ERROR: something broke" >&2\n')
    append(repo, "tool.py", 'print("WARNING: Disk: full. Free space.")\n')
    result = run(repo, "--base", "main", checker=checker)
    assert result.returncode == 1
    assert (
        ".csarc/scripts/tool:4: sentence does not end with a period (M3): "
        "ERROR: something broke" in result.stderr
    )
    assert "expected: ERROR: <what failed>: <why>. <what to do next>." in (
        result.stderr
    )
    assert ".csarc/scripts/tool.py:3: wrong output stream (M4)" in result.stderr
    assert "ERROR: Message pattern check failed: 2 of 2 messages" in (
        result.stderr
    )


def test_untouched_old_messages_are_not_checked(repo: Path) -> None:
    """PR mode ignores old messages on lines the change did not touch."""
    append(repo, "tool", 'echo "NOTICE: Added a step."\n')
    result = run(repo, "--base", "main")
    assert result.returncode == 0, result.stderr
    assert "passed for 1 messages" in result.stdout


def test_modified_old_message_is_checked(repo: Path) -> None:
    """Changing an old message line makes it subject to the patterns."""
    path = repo / ".csarc" / "scripts" / "tool"
    path.write_text(
        OLD_SHELL.replace("old message", "changed message"), encoding="utf-8"
    )
    result = run(repo, "--base", "main")
    assert result.returncode == 1
    assert ".csarc/scripts/tool:2: missing ERROR" in result.stderr


def test_full_mode_inventories_old_messages(repo: Path) -> None:
    """Full mode reports every nonconforming message in the scripts."""
    result = run(repo, "--all")
    assert result.returncode == 1
    assert "failed: 2 of 3 messages" in result.stderr


def test_exception_needs_reason(repo: Path) -> None:
    """An allow marker with a reason passes; one without a reason fails."""
    append(
        repo,
        "tool.py",
        "# message-pattern: allow X1 another program reads this line\n"
        'print(f"status={state}")\n'
        "# message-pattern: allow X1\n"
        'print(f"result={state}")\n',
    )
    result = run(repo, "--base", "main")
    assert result.returncode == 1
    assert "tool.py:5: exception needs X1-X5 and a reason" in result.stderr
    assert "failed: 1 of 2 messages" in result.stderr


def test_data_output_is_not_a_message(repo: Path) -> None:
    """Redirected, piped, and value-only output is not judged."""
    append(
        repo,
        "tool",
        'echo "data" >"$file"\necho "data" | sort\necho "$value"\n'
        'x="$(echo "inner")"\n',
    )
    result = run(repo, "--base", "main")
    assert result.returncode == 0, result.stderr
    assert "passed for 0 messages" in result.stdout


def test_missing_base_is_a_notice_and_bad_base_fails(tmp_path: Path) -> None:
    """Without Git there is nothing to diff; an unknown base stops the run."""
    (tmp_path / ".csarc" / "scripts").mkdir(parents=True)
    result = run(tmp_path)
    assert result.returncode == 0
    assert result.stdout.startswith("NOTICE: ")
    failed = run(tmp_path, "--base", "missing")
    assert failed.returncode == 1
    assert failed.stderr.startswith("ERROR: Message pattern check stopped")


def test_checker_messages_follow_the_patterns() -> None:
    """The checker's own messages conform in full mode."""
    result = run(ROOT, "--all", "scripts/check-message-style")
    assert result.returncode == 0, result.stderr
