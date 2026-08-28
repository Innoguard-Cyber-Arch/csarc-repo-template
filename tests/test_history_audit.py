import json
import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "audit_github_history.py")
)
main = MODULE["main"]
FIXTURE = Path(__file__).parent / "fixtures" / "history-audit-sample.json"


def test_sample_audit_is_paginated_and_omits_raw_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "--repo",
                "owner/repo",
                "--cutoff",
                "2026-08-24T13:08:45Z",
                "--max-number",
                "8",
                "--fixture",
                str(FIXTURE),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    result = json.loads(output)

    assert result["counts"] == {
        "commits": 2,
        "files": 3,
        "issue_comments": 1,
        "issues": 1,
        "issues_closed": 1,
        "issues_open": 0,
        "issues_with_comments": 1,
        "pull_request_comments": 1,
        "pull_requests": 1,
        "pull_requests_closed_unmerged": 0,
        "pull_requests_merged": 1,
        "pull_requests_open": 0,
        "pull_requests_with_closing_issues": 1,
        "review_threads": 0,
        "reviews": 0,
        "timeline_entries": 2,
    }
    assert all(
        item["ok"] == item["expected"] for item in result["coverage"].values()
    )
    assert result["gaps"] == []
    assert "private issue text" not in output
    assert "private PR text" not in output


def test_sample_audit_reports_endpoint_gaps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    del fixture["rest"]["repos/owner/repo/pulls/8/files?per_page=100"]
    broken = tmp_path / "audit.json"
    broken.write_text(json.dumps(fixture), encoding="utf-8")

    assert (
        main(
            [
                "--repo",
                "owner/repo",
                "--cutoff",
                "2026-08-24T13:08:45Z",
                "--max-number",
                "8",
                "--fixture",
                str(broken),
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["coverage"]["files"] == {"ok": 0, "expected": 1}
    assert result["gaps"] == ["pulls/8/files"]
