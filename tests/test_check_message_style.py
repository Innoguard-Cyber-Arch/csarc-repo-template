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
    root: Path, *args: str, checker: Path = CHECKERS[0], ci_base: str = ""
) -> subprocess.CompletedProcess[str]:
    """Run the checker in a fixture repository."""
    env = {k: v for k, v in os.environ.items() if k != "CSARC_CI_BASE"}
    if ci_base:
        env["CSARC_CI_BASE"] = ci_base
    return subprocess.run(  # noqa: S603 - the checker under test
        [str(checker), *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
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
        'raise SystemExit("ERROR: Load failed: bad JSON. Fix the file.")\n'
        'raise ValueError(f"Parse failed: {name} is empty. Fill it.")\n',
    )
    result = run(repo, "--base", "main", checker=checker)
    assert result.returncode == 0, result.stderr
    assert "OK: Message pattern check passed for 7 messages." in result.stdout


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


@pytest.mark.parametrize("checker", CHECKERS, ids=["root", "template"])
def test_missing_base_is_a_notice_and_bad_base_fails(
    tmp_path: Path, checker: Path
) -> None:
    """Without Git there is nothing to diff; an unknown --base stops the run."""
    (tmp_path / ".csarc" / "scripts").mkdir(parents=True)
    result = run(tmp_path, checker=checker, ci_base="dev/m1-x")
    assert result.returncode == 0
    assert result.stdout.startswith("NOTICE: ")
    failed = run(tmp_path, "--base", "missing", checker=checker)
    assert failed.returncode == 1
    assert failed.stderr.startswith("ERROR: Base 'missing' is unknown")


@pytest.mark.parametrize("checker", CHECKERS, ids=["root", "template"])
def test_unresolvable_environment_base_falls_through(
    repo: Path, checker: Path
) -> None:
    """A CSARC_CI_BASE absent from the repository falls back to main."""
    append(repo, "tool", 'echo "not a pattern" >&2\n')
    result = run(repo, checker=checker, ci_base="dev/m20-absent")
    assert result.returncode == 1
    assert ".csarc/scripts/tool:4: missing ERROR" in result.stderr
    fresh = repo / "fresh"
    (fresh / ".csarc" / "scripts").mkdir(parents=True)
    git(fresh, "init", "-q", "-b", "trunk")
    git(
        fresh,
        "-c",
        "user.email=f@example.invalid",
        "-c",
        "user.name=F",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "init",
    )
    single = run(fresh, checker=checker, ci_base="dev/m20-absent")
    assert single.returncode == 0, single.stderr
    assert single.stdout.startswith("NOTICE: ")


def test_checker_messages_follow_the_patterns() -> None:
    """The checker's own messages conform in full mode."""
    result = run(ROOT, "--all", "scripts/check-message-style")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "entry",
    ["scripts/verify-fast", "scripts/verify-stage-repository-contracts"],
)
def test_root_verification_runs_the_check(entry: str) -> None:
    """Root fast and full verification run the check."""
    text = (ROOT / entry).read_text(encoding="utf-8")
    assert 'verification_step "Message pattern check"' in text
    assert "./scripts/check-message-style" in text


@pytest.mark.parametrize("entry", ["verify-fast.jinja", "verify.jinja"])
def test_generated_verification_does_not_run_the_check_yet(entry: str) -> None:
    """Generated verify gets the check in #1221; flip this test there.

    Until #1220/#1221 rewrite every template message, csarc adopt and
    update would fail on the template's own old messages.
    """
    text = (ROOT / "template/.csarc/scripts" / entry).read_text(
        encoding="utf-8"
    )
    assert "check-message-style" not in text


@pytest.mark.parametrize("checker", CHECKERS, ids=["root", "template"])
def test_raised_exception_text_has_no_prefix(repo: Path, checker: Path) -> None:
    """Exception text uses the unprefixed ERROR body; a prefix is flagged."""
    append(
        repo,
        "tool.py",
        'raise RuntimeError("ERROR: Lease failed: no comment. Retry.")\n'
        'raise KeyError("lease is missing")\n',
    )
    result = run(repo, "--base", "main", checker=checker)
    assert result.returncode == 1
    assert "tool.py:3: exception text carries a prefix" in result.stderr
    assert "tool.py:4: sentence does not end with a period (M3)" in (
        result.stderr
    )
    assert "  expected: <what failed>: <why>. <what to do next>." in (
        result.stderr
    )


@pytest.mark.parametrize("checker", CHECKERS, ids=["root", "template"])
def test_block_exception_covers_a_report(repo: Path, checker: Path) -> None:
    """A reasoned X5 block allows its lines; bad blocks are flagged."""
    append(
        repo,
        "tool",
        "# message-pattern: allow-begin X5 rows of one status table\n"
        'echo "  name   state"\n'
        'echo "  main   clean"\n'
        "# message-pattern: allow-end\n"
        'echo "after the block"\n'
        "# message-pattern: allow-begin X5\n"
        'echo "  row"\n'
        "# message-pattern: allow-end\n"
        "# message-pattern: allow-begin X5 never closed block\n"
        'echo "  open row"\n',
    )
    result = run(repo, "--base", "main", checker=checker)
    assert result.returncode == 1
    errors = [x for x in result.stderr.splitlines() if x.startswith(".csarc")]
    assert [x.split(": ")[0:2] for x in errors] == [
        [".csarc/scripts/tool:9", "block exception needs X5 and a reason"],
        [".csarc/scripts/tool:12", "unmatched allow-begin or allow-end"],
        [
            ".csarc/scripts/tool:8",
            "missing ERROR, WARNING, NOTICE, or OK prefix",
        ],
        [
            ".csarc/scripts/tool:13",
            "missing ERROR, WARNING, NOTICE, or OK prefix",
        ],
    ]


@pytest.mark.parametrize("checker", CHECKERS, ids=["root", "template"])
def test_stream_write_messages_are_checked(repo: Path, checker: Path) -> None:
    """Messages written with sys.stderr.write or sys.stdout.write are judged."""
    append(
        repo,
        "tool.py",
        'sys.stderr.write("ERROR: Load failed: bad JSON. Fix the file.\\n")\n'
        'sys.stdout.write(f"OK: Wrote {count} files.\\n")\n'
        'sys.stderr.write("lease is missing\\n")\n'
        'sys.stdout.write("WARNING: Cache: stale. Clear it.\\n")\n'
        'sys.stderr.write(f"NOTICE: Checking {name}.\\n")\n'
        "sys.stdout.write(payload)\n",
    )
    result = run(repo, "--base", "main", checker=checker)
    assert result.returncode == 1
    errors = [x for x in result.stderr.splitlines() if x.startswith(".csarc")]
    assert [x.split(": ")[0:2] for x in errors] == [
        [
            ".csarc/scripts/tool.py:5",
            "missing ERROR, WARNING, NOTICE, or OK prefix",
        ],
        [".csarc/scripts/tool.py:6", "wrong output stream (M4)"],
        [".csarc/scripts/tool.py:7", "wrong output stream (M4)"],
    ]
    assert "failed: 3 of 5 messages" in result.stderr


def test_untouched_stream_write_is_not_checked(repo: Path) -> None:
    """PR mode leaves an old sys.stderr.write message alone."""
    path = repo / ".csarc" / "scripts" / "tool.py"
    path.write_text(
        OLD_PYTHON + 'sys.stderr.write("legacy failure\\n")\n', encoding="utf-8"
    )
    git(repo, "commit", "-q", "-am", "legacy write")
    append(repo, "tool.py", 'sys.stdout.write("OK: Added a step.\\n")\n')
    result = run(repo, "--base", "HEAD")
    assert result.returncode == 0, result.stderr
    assert "passed for 1 messages" in result.stdout
