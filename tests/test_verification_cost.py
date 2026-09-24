"""Tests for the verification-cost report and large-test policy (#999)."""

from __future__ import annotations

import io
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts" / "verification_cost.py"))
parse_junit = MODULE["parse_junit"]
growth_warning = MODULE["growth_warning"]
large_marker_delta = MODULE["large_marker_delta"]
justification = MODULE["justification"]
count_large_markers = MODULE["count_large_markers"]
main = MODULE["main"]

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
  <testsuite name="pytest" errors="0" failures="1" skipped="1" tests="4"
    time="12.500">
    <testcase classname="tests.test_cli" name="test_real_update" time="9.000">
      <properties><property name="csarc_marker" value="large" /></properties>
    </testcase>
    <testcase classname="tests.test_cli" name="test_fast[1]" time="0.250" />
    <testcase classname="tests.test_cli" name="test_slow" time="2.000">
      <failure message="boom" />
    </testcase>
    <testcase classname="tests.test_cli" name="test_skip" time="0.000">
      <skipped message="skip" />
    </testcase>
  </testsuite>
</testsuites>
"""


def test_parse_junit_reports_total_slowest_and_large_from_one_run() -> None:
    """Totals, slowest cases, and large count come from one JUnit file."""
    summary = parse_junit(JUNIT)

    assert summary.total_seconds == pytest.approx(12.5)
    assert summary.tests == 4
    assert summary.failures == 1
    assert summary.skipped == 1
    assert summary.large_executed == 1
    assert [case.name for case in summary.slowest(2)] == [
        "tests.test_cli::test_real_update",
        "tests.test_cli::test_slow",
    ]


def test_conftest_tags_large_cases_in_junit(tmp_path: Path) -> None:
    """The root conftest hook records the marker in the same run's XML."""
    (tmp_path / "conftest.py").write_text(
        (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\nmarkers =\n  large: slow\n", encoding="utf-8"
    )
    (tmp_path / "test_sample.py").write_text(
        "import pytest\n\n\n@pytest.mark.large\ndef test_big():\n    pass\n\n\n"
        "def test_small():\n    pass\n",
        encoding="utf-8",
    )
    junit = tmp_path / "out.xml"
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
            str(tmp_path),
        ],
        check=True,
        cwd=tmp_path,
        capture_output=True,
    )

    summary = parse_junit(junit.read_text(encoding="utf-8"))
    assert summary.tests == 2
    assert summary.large_executed == 1


@pytest.mark.parametrize(
    ("total", "baseline", "warns"),
    [
        (115.0, 100.0, False),
        (115.1, 100.0, True),
        (80.0, 100.0, False),
        (500.0, None, False),
        (500.0, 0.0, False),
    ],
)
def test_growth_warning_only_above_fifteen_percent(
    total: float, baseline: float | None, warns: bool
) -> None:
    """Warn strictly above 15% growth and never without a baseline."""
    assert (growth_warning(total, baseline) is not None) is warns


def test_count_large_markers_ignores_strings_and_other_markers() -> None:
    """Only real decorators or module markers count as large tests."""
    source = (
        "@pytest.mark.large\n"
        "def test_a(): ...\n"
        "  @pytest.mark.large\n"
        "pytestmark = [pytest.mark.large]\n"
        '    assert "pytest.mark.large" not in text\n'
        "@pytest.mark.runtime\n"
    )
    assert count_large_markers(source) == 3


def test_large_marker_delta_counts_net_added_markers() -> None:
    """Added minus removed markers across Python patches."""
    files = [
        {
            "filename": "tests/test_a.py",
            "status": "modified",
            "patch": "@@\n+@pytest.mark.large\n+@pytest.mark.large\n"
            "-@pytest.mark.large\n+++ not a marker",
        },
        {"filename": "README.md", "patch": "+@pytest.mark.large"},
        {"filename": "tests/test_gone.py", "status": "removed"},
    ]
    assert large_marker_delta(files) == (1, [])
    assert large_marker_delta([{"filename": "tests/test_big.py"}]) == (
        0,
        ["tests/test_big.py"],
    )


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "Large test justification: replaces test_old_e2e",
            "replaces test_old_e2e",
        ),
        (
            "- **Large test justification**\uff1a"
            "真實 Copier update 無法以單元測試取代",
            "真實 Copier update 無法以單元測試取代",
        ),
        ("Large test justification: N/A", None),
        ("Large test justification:", None),
        ("No justification here", None),
    ],
)
def test_justification_requires_concrete_text(
    body: str, expected: str | None
) -> None:
    """Placeholders and missing lines do not satisfy the policy."""
    assert justification(body) == expected


def _check(monkeypatch: pytest.MonkeyPatch, files: object, body: str) -> int:
    monkeypatch.setenv("PR_BODY", body)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(files)))
    return main(["check-large-justification", "--files-json", "-"])


def test_check_large_justification_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Net new large tests need a justification; removals do not."""
    added = [[{"filename": "tests/t.py", "patch": "+@pytest.mark.large"}]]
    removed = [[{"filename": "tests/t.py", "patch": "-@pytest.mark.large"}]]

    assert _check(monkeypatch, added, "Closes #1") == 1
    assert (
        _check(
            monkeypatch,
            added,
            "Closes #1\nLarge test justification: replaces test_old",
        )
        == 0
    )
    assert _check(monkeypatch, removed, "Closes #1") == 0


def test_report_local_prints_only_this_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Local output shows total and slowest cases with no baseline."""
    junit = tmp_path / "pytest.xml"
    junit.write_text(JUNIT, encoding="utf-8")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    assert (
        main(
            [
                "report",
                "--junit",
                str(junit),
                "--label",
                "local",
                "--suite",
                "full",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "pytest total 12.5s" in output
    assert "tests.test_cli::test_real_update  [large]" in output
    assert "baseline" not in output
    assert "::warning" not in output


def test_report_hosted_writes_summary_and_warns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Hosted output compares with the baseline and only warns."""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)

    def git(*args: str) -> None:
        subprocess.run(  # noqa: S603
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],  # noqa: S607
            cwd=repo,
            check=True,
            capture_output=True,
        )

    git("init", "-q", "-b", "main")
    (repo / "tests/test_a.py").write_text(
        "@pytest.mark.large\ndef test_a(): ...\n", encoding="utf-8"
    )
    (repo / "tests/verification-cost-baseline.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suites": {"full": {"pytest_seconds": 10.0, "source": "run 1"}},
            }
        ),
        encoding="utf-8",
    )
    git("add", ".")
    git("commit", "-q", "-m", "base")
    git("checkout", "-q", "-b", "feature")
    (repo / "tests/test_b.py").write_text(
        "@pytest.mark.large\ndef test_b(): ...\n", encoding="utf-8"
    )
    git("add", ".")
    git("commit", "-q", "-m", "head")

    junit = tmp_path / "pytest.xml"
    junit.write_text(JUNIT, encoding="utf-8")
    step_summary = tmp_path / "summary.md"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))
    monkeypatch.setenv("CSARC_CI_BASE", "main")

    args = ["report", "--junit", str(junit), "--label", "full", "--suite"]
    assert main([*args, "full"]) == 0
    output = capsys.readouterr().out
    summary = step_summary.read_text(encoding="utf-8")
    assert "::warning title=Verification cost growth::" in output
    assert "markers vs PR base: 1 → 2 (+1)" in summary
    assert "10.0s from run 1 via base commit" in summary
    assert "| 9.00 | `tests.test_cli::test_real_update` (large) |" in summary

    step_summary.unlink()
    assert main([*args, "fast"]) == 0
    assert "::warning" not in capsys.readouterr().out
    assert "no same-kind baseline" in step_summary.read_text(encoding="utf-8")
