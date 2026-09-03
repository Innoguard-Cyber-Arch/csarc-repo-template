"""Regression tests for the retry cleanup in scripts/test-check-branch-fresh
(Issue #591).

Hosted CI has twice failed this fixture's teardown with `rm: cannot remove
'.../work/.git': Directory not empty` right after the last git operation
against it -- a TOCTOU race never reproduced locally, so the fix is a
retrying `cleanup()` trap rather than a targeted root-cause change. These
tests extract that `cleanup()` function verbatim (not a reimplementation)
and exercise its retry-then-surface-failure contract deterministically, by
substituting a fake `rm` on PATH that fails a controlled number of times,
instead of trying to force the real, non-deterministic kernel race.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "test-check-branch-fresh"

FUNCTION_START = "cleanup() {\n"
FUNCTION_END = "\ntrap cleanup EXIT"


def _extract_cleanup_source() -> str:
    """Pull the `cleanup()` function verbatim out of the shell script.

    Extracting the literal text guarantees this test exercises the same
    code the script ships, and fails loudly if the function or its trap
    ever move.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index(FUNCTION_START)
    end = source.index(FUNCTION_END, start)
    return source[start:end]


CLEANUP_SOURCE = _extract_cleanup_source()


def _write_fake_rm(bin_dir: Path, fail_count: int, log_path: Path) -> None:
    """Write an `rm` shim that fails `fail_count` calls, then delegates.

    Each call appends to `log_path` so a test can assert how many times
    `cleanup()` actually retried. A "failing" call never touches the
    filesystem (modeling an `rm -rf` that aborted without deleting
    anything, the worst case for a retry loop); once past `fail_count`,
    the shim runs the real `/bin/rm` so a genuinely succeeding retry still
    leaves the target actually removed.
    """
    fake_rm = bin_dir / "rm"
    fake_rm.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
count_file={log_path}
count=0
[[ -f "$count_file" ]] && count="$(cat "$count_file")"
count=$((count + 1))
printf '%s' "$count" >"$count_file"
if (( count <= {fail_count} )); then
  exit 1
fi
exec /bin/rm "$@"
""",
        encoding="utf-8",
    )
    fake_rm.chmod(fake_rm.stat().st_mode | stat.S_IEXEC)


def _run_cleanup(
    tmp_path: Path, fixture_root: Path, fail_count: int
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "rm-calls"
    _write_fake_rm(bin_dir, fail_count, log_path)

    script = (
        f"fixture_root={fixture_root}\n{CLEANUP_SOURCE}\n"
        "cleanup; rc=$?; echo DONE; exit $rc\n"
    )
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return subprocess.run(  # noqa: S603
        ["bash", "-c", script],  # noqa: S607
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cleanup_survives_a_transient_failure_within_the_retry_budget(
    tmp_path: Path,
) -> None:
    """A race that clears within 5 attempts must not fail the test run."""
    fixture_root = tmp_path / "fixture"
    (fixture_root / "work" / ".git").mkdir(parents=True)

    result = _run_cleanup(tmp_path, fixture_root, fail_count=2)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "DONE" in result.stdout
    assert not fixture_root.exists()


def test_cleanup_still_surfaces_a_genuinely_persistent_failure(
    tmp_path: Path,
) -> None:
    """The retry must not silently hide a real, non-transient failure."""
    fixture_root = tmp_path / "fixture"
    (fixture_root / "work" / ".git").mkdir(parents=True)

    result = _run_cleanup(tmp_path, fixture_root, fail_count=100)

    assert result.returncode != 0
    assert fixture_root.exists()
