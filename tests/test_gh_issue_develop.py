"""Regression tests for Issue number parsing in gh-issue-develop (Issue #1178).

The argument parser used the bash `case` glob `[1-9][0-9]*)`, whose `[0-9]`
demands one character, so Issue #1 through #9 were treated as missing. These
tests run the shipped root and template copies against a fake `gh` that only
records the forwarded arguments.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    ROOT / "scripts" / "gh-issue-develop",
    ROOT / "template" / ".csarc" / "scripts" / "gh-issue-develop",
]
URL = "https://github.com/example/repo/issues/{n}"


def _run(
    script: Path, tmp_path: Path, *args: str
) -> subprocess.CompletedProcess[str]:
    fake_gh = tmp_path / "gh"
    log = tmp_path / "gh.log"
    fake_gh.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" > {log}\n')
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "GH_BINARY": str(fake_gh)}
    return subprocess.run(  # noqa: S603
        ["bash", str(script), *args],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=["root", "template"])
@pytest.mark.parametrize(
    "issue", ["1", "9", "10", URL.format(n=1), URL.format(n=10)]
)
def test_accepts_positive_issue_numbers(
    script: Path, tmp_path: Path, issue: str
) -> None:
    number = issue.rsplit("/", 1)[-1]
    branch = f"feat/{number}-short-slug"
    result = _run(script, tmp_path, issue, "--base", "main", "--name", branch)
    assert result.returncode == 0, result.stderr
    forwarded = (tmp_path / "gh.log").read_text().strip()
    assert forwarded == f"issue develop {issue} --base main --name {branch}"


@pytest.mark.parametrize("script", SCRIPTS, ids=["root", "template"])
@pytest.mark.parametrize("issue", ["0", "01", "1a", "abc"])
def test_rejects_zero_leading_zero_and_non_numeric(
    script: Path, tmp_path: Path, issue: str
) -> None:
    result = _run(
        script, tmp_path, issue, "--base", "main", "--name", "feat/1-short-slug"
    )
    assert result.returncode == 1
    assert "Pass an Issue number or URL" in result.stderr
    assert not (tmp_path / "gh.log").exists()


def test_no_shell_case_glob_requires_two_digits() -> None:
    # A `[1-9][0-9]*)` case pattern without a lone `[1-9]` skips 1-9.
    offenders = []
    for directory in (
        ROOT / "scripts",
        ROOT / "template" / ".csarc" / "scripts",
    ):
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix == ".py":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if not stripped.endswith(")") or "[[" in stripped:
                    continue
                alternatives = stripped[:-1].split("|")
                if (
                    "[1-9][0-9]*" in alternatives
                    and "[1-9]" not in alternatives
                ):
                    offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert offenders == []
