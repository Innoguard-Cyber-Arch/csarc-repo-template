"""Read-only ProjectV2 drift report with a stubbed GitHub API (#1346).

No test talks to GitHub: `FakeBoard` serves the REST and GraphQL reads the
report makes, records every call, and fails on any mutation. The report is
verified only with stubs, not against a live ProjectV2 (SPEC-009 §10).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from csarc_cli import cli, project_drift

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/orgs/acme/projects/7"
TRACKED = {
    "number": 3,
    "title": "Beta",
    "due_on": "2026-10-31T07:00:00Z",
    "description": "Lifecycle Issue: #40",
}


def field(name: str, data_type: str = "DATE") -> dict[str, str]:
    """Return one ProjectV2 field node."""
    return {"id": f"F-{name}", "name": name, "dataType": data_type}


class FakeBoard:
    """A read-only stand-in for the `gh` calls the drift report makes."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.scopes: str | None = "repo, read:project"
        self.fields = [
            field("Title", "TITLE"),
            field("Status", "SINGLE_SELECT"),
            field("Project start"),
            field("Project target"),
        ]
        self.issues: dict[int, dict[str, Any]] = {}
        self.items: list[dict[str, Any]] = []
        self.page_size = 2

    def issue(
        self,
        number: int,
        *,
        milestone: dict[str, Any] | None = None,
        closed: bool = False,
        parent: bool = False,
    ) -> None:
        """Add one Issue fixture."""
        self.issues[number] = {
            "number": number,
            "node_id": f"I_{number}",
            "created_at": "2026-10-15T10:00:00Z",
            "milestone": milestone,
            "state": "closed" if closed else "open",
            "closed_at": "2026-10-20T10:00:00Z" if closed else None,
        }
        if parent:
            self.issues[number]["parent_issue_url"] = "https://x/issues/1"

    def item(
        self,
        number: int,
        *,
        status: str | None = "Todo",
        start: str | None = "2026-10-15",
        target: str | None = "2026-10-29",
        repo: str = "o/r",
    ) -> None:
        """Put one Issue on the fake board."""
        state = (self.issues.get(number) or {}).get("state", "open").upper()
        self.items.append(
            {
                "content": {
                    "number": number,
                    "state": state,
                    "repository": {"nameWithOwner": repo},
                },
                "start": {"date": start} if start else None,
                "target": {"date": target} if target else None,
                "status": {"name": status} if status else None,
            }
        )

    def __call__(self, command: list[str]) -> str:
        self.calls.append(command)
        if command[:2] == ["repo", "view"]:
            return "o/r\n"
        if command[:3] == ["api", "--include", "rate_limit"]:
            header = f"X-Oauth-Scopes: {self.scopes}\n" if self.scopes else ""
            return f"HTTP/2.0 200 OK\n{header}\n{{}}"
        if command[:2] == ["api", "graphql"]:
            return json.dumps(self.graphql(command))
        if command[:3] == ["api", "--paginate", "--slurp"]:
            issues = list(self.issues.values())
            if "milestone=3" in command[3]:
                issues = [i for i in issues if i["milestone"]]
            return json.dumps([[*issues, {"number": 99, "pull_request": {}}]])
        if command[0] == "api" and "/issues/" in command[1]:
            return json.dumps(self.issues[int(command[1].rsplit("/", 1)[1])])
        raise AssertionError(command)

    def graphql(self, command: list[str]) -> dict[str, Any]:
        """Serve one read-only GraphQL document."""
        query = command[3]
        assert "mutation" not in query, "the drift report must never write"
        values = dict(
            item.split("=", 1) for item in command[5::2] if "=" in item
        )
        if "items(first" in query:
            start = int(values.get("cursor", "0"))
            end = start + self.page_size
            return {
                "data": {
                    "owner": {
                        "projectV2": {
                            "items": {
                                "pageInfo": {
                                    "hasNextPage": end < len(self.items),
                                    "endCursor": str(end),
                                },
                                "nodes": self.items[start:end],
                            }
                        }
                    }
                }
            }
        assert "projectV2(number" in query
        project = {
            "id": "PVT_1",
            "url": URL,
            "title": "Roadmap",
            "closed": True,
            "viewerCanUpdate": False,
            "fields": {"nodes": self.fields},
        }
        return {"data": {"owner": {"login": "acme", "projectV2": project}}}


def run_report(
    fake: FakeBoard, tmp_path: Path, **selection: int | None
) -> tuple[int, str]:
    """Run the report against the fake with a configured URL."""
    config = tmp_path / "config.yml"
    config.write_text(f"github_project_url: {URL}\n", encoding="utf-8")
    out = io.StringIO()
    status = project_drift.command_report(
        "o/r",
        issue=selection.get("issue"),
        milestone=selection.get("milestone"),
        run=fake,
        out=out,
        config=config,
    )
    return status, out.getvalue()


def drifted_board() -> FakeBoard:
    """Return a board with one example of each drift kind."""
    fake = FakeBoard()
    fake.issue(40, milestone=TRACKED)  # tracker, dated: clean
    fake.issue(41, milestone=TRACKED, closed=True)  # work Issue, at Review
    fake.issue(42, milestone=TRACKED)  # work Issue, off board: fine
    fake.issue(50, closed=True)  # standalone, closed at Done: clean
    fake.issue(51)  # standalone, missing from the board
    fake.issue(52)  # standalone, no target date
    fake.issue(53, parent=True)  # sub-issue, off board: fine
    fake.item(40)
    fake.item(41, status="Review")
    fake.item(50, status="Done")
    fake.item(52, target=None)
    fake.item(51, repo="other/repo")  # another repository's #51
    return fake


def test_report_lists_each_drift_kind_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """AC1/AC3: closed-not-Done, missing from the board, missing dates."""
    fake = drifted_board()
    status, output = run_report(fake, tmp_path)
    assert status == 1, output
    assert "read-only drift report; token scope read:project" in output
    assert "#41 is closed but its Project Status is 'Review'" in output
    assert "#51 is not on the Project" in output
    assert "csarc issue sync-project --issue 51" in output
    assert "#52 has no Project target" in output
    for clean in ("#40 ", "#42 ", "#50 ", "#53 "):
        assert clean not in output, clean
    assert "Found 3 drift item(s) in 7 Issue(s); nothing was written" in output
    graphql = [c[3] for c in fake.calls if c[:2] == ["api", "graphql"]]
    assert graphql and not any("mutation" in query for query in graphql)
    # Three board pages were read through the cursor.
    assert sum("items(first" in query for query in graphql) == 3


def test_closed_item_without_status_is_drift(tmp_path: Path) -> None:
    """AC1: an empty Status on a closed Issue is not Done."""
    fake = FakeBoard()
    fake.issue(50, closed=True)
    fake.item(50, status=None)
    status, output = run_report(fake, tmp_path, issue=50)
    assert status == 1
    assert "#50 is closed but its Project Status is empty" in output


def test_selection_limits_the_report(tmp_path: Path) -> None:
    """AC1: '--issue' and '--milestone' report only the selected Issues."""
    fake = drifted_board()
    status, output = run_report(fake, tmp_path, issue=40)
    assert status == 0, output
    assert "OK: No Project drift in 1 Issue(s); nothing was written" in output
    status, output = run_report(fake, tmp_path, milestone=3)
    assert status == 1
    assert "#41 is closed" in output and "#51" not in output


def test_missing_fields_are_named_and_their_checks_skipped(
    tmp_path: Path,
) -> None:
    """R1: a missing or mistyped field is reported, never guessed."""
    fake = drifted_board()
    fake.fields = [field("Status", "TEXT"), field("Project start")]
    status, output = run_report(fake, tmp_path)
    assert "Field 'Status' cannot be read: it is TEXT, not SINGLE_SELECT" in (
        output
    )
    assert "closed-but-not-Done check is skipped" in output
    assert "Field 'Project target' cannot be read: the Project has no" in (
        output
    )
    assert "#41 is closed" not in output
    assert "#52 has no" not in output
    assert status == 1 and "#51 is not on the Project" in output


def test_report_needs_a_read_scope_only(tmp_path: Path) -> None:
    """AC1: read access is enough; a closed or read-only Project reports."""
    fake = drifted_board()
    fake.scopes = "repo, project"
    assert run_report(fake, tmp_path)[0] == 1
    fake.scopes = None
    assert "token scope unknown" in run_report(fake, tmp_path)[1]
    fake.scopes = "repo"
    status, output = run_report(fake, tmp_path)
    assert status == 1
    assert "lacks the 'read:project' scope" in output
    assert "Nothing was written" in output


def test_empty_setting_calls_no_api(tmp_path: Path) -> None:
    """AC1: an empty URL reports nothing and calls no GitHub API."""
    fake = FakeBoard()
    config = tmp_path / "config.yml"
    config.write_text("github_project_url: ''\n", encoding="utf-8")
    out = io.StringIO()
    status = project_drift.command_report(
        "o/r", issue=None, milestone=None, run=fake, out=out, config=config
    )
    assert status == 0 and "disabled" in out.getvalue()
    assert fake.calls == []


def test_cli_routes_report_and_rejects_write_options(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC1: '--report' routes to the read-only report; '--all' needs it."""
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        project_drift,
        "command_report",
        lambda repo, **kwargs: seen.append({"repo": repo, **kwargs}) or 0,
    )
    assert cli.main(["issue", "sync-project", "--all", "--report"]) == 0
    assert seen == [{"repo": "", "issue": None, "milestone": None}]
    assert cli.main(["issue", "sync-project", "--issue", "5", "--report"]) == 0
    assert seen[-1]["issue"] == 5
    assert cli.main(["issue", "sync-project", "--all"]) == 2
    assert "--all is only valid with --report" in capsys.readouterr().err
    assert (
        cli.main(["issue", "sync-project", "--all", "--report", "--yes"]) == 2
    )
    assert "drift report never writes" in capsys.readouterr().err
    assert len(seen) == 2


def test_spec_keeps_status_ownership_and_stub_only_note() -> None:
    """AC2/AC3: SPEC-009 says workflows own Status and stubs verify this."""
    text = (ROOT / "docs/specs/SPEC-009-project-settings.md").read_text(
        encoding="utf-8"
    )
    assert "sync-project --report" in text
    assert "Project 自己的 workflow" in text
    assert "未經 live ProjectV2 驗證" in text
