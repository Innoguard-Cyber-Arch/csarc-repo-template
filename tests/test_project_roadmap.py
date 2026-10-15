"""GitHub Project Roadmap projection with a stubbed GitHub API (#1080, K2).

No test talks to GitHub: `FakeGitHub` serves the REST and GraphQL calls the
module makes and records every call, so each test can prove which Project
API calls happened, which writes landed, and that nothing was duplicated.
The live ProjectV2 pilot is a separate owner-run step (#1058 Pilot).
"""

from __future__ import annotations

import io
import json
import re
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import settings_support

from csarc_cli import cli, project_roadmap, risk_tools, settings_schema
from csarc_cli.project_roadmap import ProjectSyncError

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/orgs/acme/projects/7"
MINIMAL_SETTINGS: dict[str, object] = dict(settings_support.DEFAULTS)
BODY = (
    "### 問題\n\nWhy.\n\n### 完成條件\n\n- [ ] AC1: One\n\n### 補充\n\n"
    "#### 風險與控制\n\n"
    "| ID | 類別 | 等級 | 風險 | 控制 | 預計證據 | Owner |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
    "| R1 | data | high | Loses files | Dry-run test | Regression | @a |\n"
)


def field(name: str, data_type: str = "DATE", ident: str = "") -> dict:
    """Return one ProjectV2 field node."""
    return {"id": ident or f"F-{name}", "name": name, "dataType": data_type}


class FakeGitHub:
    """A stateful stand-in for the `gh` calls project_roadmap makes."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.scopes: str | None = "repo, project, read:org"
        self.owner_login = "acme"
        self.project: dict[str, Any] | None = {
            "id": "PVT_1",
            "url": URL,
            "title": "Roadmap",
            "closed": False,
            "viewerCanUpdate": True,
            "fields": {
                "nodes": [
                    field("Title", "TITLE"),
                    field("Project start"),
                    field("Project target"),
                ]
            },
        }
        self.milestones: dict[int, dict[str, Any]] = {
            3: {"number": 3, "title": "Beta", "due_on": "2026-10-31T07:00:00Z"}
        }
        self.issues: dict[int, dict[str, Any]] = {}
        self.items: dict[str, dict[str, Any]] = {}
        self.fail_on: dict[str, int] = {}
        self.add_calls = 0
        self.set_calls = 0
        self.fail_set_at: int | None = None

    def add_issue(
        self, number: int, created: str, milestone: int | None
    ) -> None:
        """Add one Issue fixture."""
        self.issues[number] = {
            "number": number,
            "node_id": f"I_{number}",
            "created_at": created,
            "milestone": self.milestones.get(milestone) if milestone else None,
        }

    def project_api_calls(self) -> list[list[str]]:
        """Return every call that reached a GitHub API."""
        return [call for call in self.calls if call[:1] == ["api"]]

    def maybe_fail(self, operation: str) -> None:
        """Fail the next ``operation`` while its counter is positive."""
        if self.fail_on.get(operation, 0) > 0:
            self.fail_on[operation] -= 1
            raise ProjectSyncError(f"gh api failed: HTTP 502 on {operation}")

    def __call__(self, command: list[str]) -> str:
        self.calls.append(command)
        if command[:2] == ["repo", "view"]:
            return "o/r\n"
        if command[:2] == ["issue", "create"]:
            number = max(self.issues, default=40) + 1
            title = command[command.index("--title") + 1]
            wanted = project_roadmap.option_value(command, "--milestone", "-m")
            milestone = next(
                (
                    m["number"]
                    for m in self.milestones.values()
                    if m["title"] == wanted
                ),
                None,
            )
            self.add_issue(number, "2026-10-15T23:30:00Z", milestone)
            self.issues[number]["title"] = title
            return f"https://github.com/o/r/issues/{number}\n"
        if command[:3] == ["api", "--include", "rate_limit"]:
            if self.scopes is None:
                return "HTTP/2.0 200 OK\nContent-Type: json\n\n{}"
            return f"HTTP/2.0 200 OK\nX-Oauth-Scopes: {self.scopes}\n\n{{}}"
        if command[:2] == ["api", "graphql"]:
            return json.dumps(self.graphql(command))
        if command[:3] == ["api", "--paginate", "--slurp"]:
            endpoint = command[3]
            if "/milestones?" in endpoint:
                return json.dumps([list(self.milestones.values())])
            found = re.search(r"milestone=([0-9]+)", endpoint)
            assert found is not None
            number = int(found[1])
            return json.dumps(
                [
                    [
                        issue
                        for issue in self.issues.values()
                        if (issue["milestone"] or {}).get("number") == number
                    ]
                    + [{"number": 99, "pull_request": {}}]
                ]
            )
        if command[0] == "api" and "/issues/" in command[1]:
            return json.dumps(self.issues[int(command[1].rsplit("/", 1)[1])])
        raise AssertionError(command)

    def graphql(self, command: list[str]) -> dict[str, Any]:
        """Serve one GraphQL document from the fake state."""
        query = command[3]
        values = dict(
            item.split("=", 1) for item in command[5::2] if "=" in item
        )
        if self.fail_on.get("rate_limited"):
            self.fail_on["rate_limited"] -= 1
            return {
                "errors": [
                    {"type": "RATE_LIMITED", "message": "API rate limit"}
                ]
            }
        if "projectV2(number" in query:
            assert values["number"] == "7"
            return {
                "data": {
                    "owner": {
                        "login": self.owner_login,
                        "projectV2": self.project,
                    }
                }
            }
        if "projectItems" in query:
            item = self.items.get(values["id"])
            nodes = []
            if item:
                nodes.append(
                    {
                        "id": item["id"],
                        "project": {"id": "PVT_1"},
                        "start": {"date": item["start"]}
                        if item["start"]
                        else None,
                        "target": {"date": item["target"]}
                        if item["target"]
                        else None,
                    }
                )
            nodes.append({"id": "OTHER", "project": {"id": "PVT_other"}})
            return {"data": {"node": {"projectItems": {"nodes": nodes}}}}
        if "addProjectV2ItemById" in query:
            self.maybe_fail("add")
            self.add_calls += 1
            item = self.items.setdefault(
                values["content"],
                {
                    "id": f"ITEM_{values['content']}",
                    "start": None,
                    "target": None,
                },
            )
            return {
                "data": {"addProjectV2ItemById": {"item": {"id": item["id"]}}}
            }
        if "updateProjectV2ItemFieldValue" in query:
            self.maybe_fail("set")
            if self.fail_set_at == self.set_calls:
                self.fail_set_at = None
                raise ProjectSyncError("gh api failed: HTTP 502 on set")
            self.set_calls += 1
            item = next(
                i for i in self.items.values() if i["id"] == values["item"]
            )
            key = "start" if values["field"] == "F-Project start" else "target"
            item[key] = values["date"]
            return {"data": {"updateProjectV2ItemFieldValue": {}}}
        raise AssertionError(query)


def sync(
    fake: FakeGitHub,
    *,
    issue: int | None = None,
    **options: Any,  # noqa: ANN401
) -> tuple[int, str]:
    """Run `sync-project` against the fake with a configured URL."""
    out = io.StringIO()
    config = options.pop("config", None)
    if config is None:
        config = Path(options.pop("tmp")) / "config.yml"
        config.write_text(f"github_project_url: {URL}\n", encoding="utf-8")
    status = project_roadmap.command_sync(
        "o/r",
        issue=issue,
        milestone=options.pop("milestone", None),
        run=fake,
        out=out,
        config=config,
        **options,
    )
    return status, out.getvalue()


# ---------------------------------------------------------------- AC1 / AC2


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("", True),
        (URL, True),
        ("https://github.com/users/alice/projects/12", True),
        ("https://github.com/acme/repo/projects/1", False),
        (URL + "/", False),
        (URL + "/views/1", False),
        ("https://github.com/orgs/acme/projects/0", False),
        ("PVT_kwDOAbc", False),
    ],
)
def test_setting_stores_only_a_full_project_url(
    value: str, valid: bool
) -> None:
    """AC1: '' or a full org/user ProjectV2 URL; never an ID.

    The CLI owns the format (it writes and reads the setting); the shipped
    runtime parser only types it as text and never uses it.
    """
    if valid:
        settings_schema._validate_value("github_project_url", value)
        assert settings_schema.config_text(
            {**MINIMAL_SETTINGS, "github_project_url": value}
        )
        return
    with pytest.raises(settings_schema.SettingsSchemaError):
        settings_schema._validate_value("github_project_url", value)
    with pytest.raises(ProjectSyncError):
        project_roadmap.parse_project_url(value)


def test_setting_is_one_unasked_key_defaulting_to_empty() -> None:
    """AC1: one Project key, empty by default, never asked (no new question)."""
    import yaml

    copier = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    question = copier["github_project_url"]
    assert question["default"] == "" and question["when"] is False
    project_keys = [key for key in copier if "project_url" in key]
    assert project_keys == ["github_project_url"]
    assert settings_schema.migrated_intent({})["github_project_url"] == ""
    # The root file omits the optional key so older trusted-base readers,
    # which reject unknown keys, still accept it; absent means ''.
    root = yaml.safe_load(
        (ROOT / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    assert "github_project_url" not in root
    assert (
        project_roadmap.configured_project_url(ROOT / ".csarc/config.yml") == ""
    )


def test_missing_optional_key_is_valid_and_defaults_to_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1/AC2: schema 2 without the key is valid in every reader."""
    values = dict(settings_support.DEFAULTS)
    values.pop("github_project_url", None)
    settings_schema.validate_current(values)
    text = settings_schema.config_text(values)
    assert "github_project_url" not in text
    config = tmp_path / ".csarc/config.yml"
    config.parent.mkdir()
    config.write_text(text, encoding="utf-8")
    runtime = runpy.run_path(str(ROOT / "scripts/csarc_config.py"))
    runtime["validate_config"](runtime["load_config"](config), config)
    monkeypatch.chdir(tmp_path)
    assert runtime["main"](["github_project_url"]) == 0


def test_empty_setting_never_calls_a_project_api(tmp_path: Path) -> None:
    """AC2: an empty URL disables sync with zero GitHub calls."""
    fake = FakeGitHub()
    config = tmp_path / "config.yml"
    config.write_text("github_project_url: ''\n", encoding="utf-8")
    status, output = sync(fake, issue=41, config=config)
    assert status == 0
    assert "disabled" in output
    assert fake.calls == []
    missing = tmp_path / "missing.yml"
    assert sync(fake, issue=41, config=missing)[0] == 0
    assert fake.calls == []


def test_empty_setting_keeps_issue_create_free_of_project_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: `csarc issue create` with '' creates without hooks."""
    (tmp_path / ".csarc").mkdir()
    (tmp_path / ".csarc/config.yml").write_text(
        "github_project_url: ''\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    seen: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        risk_tools,
        "issue_create",
        lambda *args, **kwargs: seen.append((args, kwargs)) or 0,
    )
    assert cli.main(["issue", "create", "--", "--title", "Add report"]) == 0
    assert seen == [((["--title", "Add report"], None), {})]


def test_repository_projects_stay_disabled_without_new_workflows() -> None:
    """AC2: has_projects stays false; no workflow or check runs the sync."""
    for path in (
        ROOT / "policies/repository.json",
        ROOT / "template/.csarc/policies/repository.json",
    ):
        assert json.loads(path.read_text())["has_projects"] is False
    workflows = [
        *ROOT.glob(".github/workflows/*"),
        *ROOT.glob("template/.github/workflows/*"),
    ]
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        assert "sync-project" not in text and "ProjectV2" not in text, path


# ---------------------------------------------------------------- AC3 (R1)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda f: setattr(f, "owner_login", "evil"), "resolved owner"),
        (lambda f: setattr(f, "project", None), "does not exist"),
        (
            lambda f: f.project.update(
                url="https://github.com/orgs/acme/projects/8"
            ),
            "resolved",
        ),
        (lambda f: f.project.update(closed=True), "closed"),
        (
            lambda f: f.project.update(viewerCanUpdate=False),
            "viewerCanUpdate is false",
        ),
        (
            lambda f: setattr(f, "scopes", "repo, read:project"),
            "gh auth refresh -s project",
        ),
        (
            lambda f: f.project["fields"]["nodes"].append(
                field("project start", ident="F-dup")
            ),
            "exactly one field named 'Project start' (found 2)",
        ),
        (
            lambda f: f.project["fields"]["nodes"].pop(),
            "exactly one field named 'Project target' (found 0)",
        ),
        (
            lambda f: f.project["fields"]["nodes"].__setitem__(
                1, field("Project start", "TEXT")
            ),
            "must be a DATE field",
        ),
    ],
)
def test_project_is_verified_before_any_write(
    tmp_path: Path, change: Callable[[FakeGitHub], object], message: str
) -> None:
    """AC3/R1: wrong owner/project/permission/scope/field writes nothing."""
    fake = FakeGitHub()
    fake.add_issue(41, "2026-10-15T10:00:00Z", 3)
    change(fake)
    status, output = sync(fake, issue=41, tmp=tmp_path)
    assert status == 1
    assert message in output
    assert "Repair (idempotent): csarc issue sync-project --issue 41" in output
    assert fake.add_calls == fake.set_calls == 0


def test_unknown_token_scopes_are_reported_not_guessed(
    tmp_path: Path,
) -> None:
    """AC3: without a scopes header the transcript says unknown."""
    fake = FakeGitHub()
    fake.scopes = None
    fake.add_issue(41, "2026-10-15T10:00:00Z", 3)
    status, output = sync(fake, issue=41, tmp=tmp_path)
    assert status == 0
    assert "token scope unknown" in output
    fake.scopes = "repo, project"
    assert "token scope project" in sync(fake, issue=41, tmp=tmp_path)[1]


# ---------------------------------------------------------------- AC4


def test_utc_dates_follow_creation_and_milestone_due() -> None:
    """AC4: start/target are UTC calendar dates."""
    assert project_roadmap.utc_date("2026-10-15T23:59:59Z") == "2026-10-15"
    assert project_roadmap.utc_date("2026-10-16T07:30:00+08:00") == "2026-10-15"
    assert project_roadmap.utc_date("2026-10-31T07:00:00Z") == "2026-10-31"


def test_issue_create_checks_first_then_adds_and_dates_the_issue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC3/AC4: verify before create, then add once with UTC dates."""
    fake = FakeGitHub()
    out = io.StringIO()
    before, after = project_roadmap.create_hooks(URL, "", run=fake, out=out)
    status = risk_tools.issue_create(
        ["--title", "Add report checks", "--body", BODY, "--milestone", "Beta"],
        run=fake,
        interactive=False,
        before=before,
        after=after,
    )
    assert status == 0, out.getvalue()
    first_create = next(
        i
        for i, call in enumerate(fake.calls)
        if call[:2] == ["issue", "create"]
    )
    assert any(
        "projectV2(number" in " ".join(c) for c in fake.calls[:first_create]
    )
    assert fake.items["I_41"] == {
        "id": "ITEM_I_41",
        "start": "2026-10-15",
        "target": "2026-10-31",
    }
    assert fake.add_calls == 1
    assert "https://github.com/o/r/issues/41" in capsys.readouterr().out


def test_issue_without_due_date_needs_an_explicit_target() -> None:
    """AC4: no due date and no --target-date stops before creating."""
    fake = FakeGitHub()
    before, after = project_roadmap.create_hooks(URL, "", run=fake)
    with pytest.raises(ProjectSyncError, match="no Issue was created"):
        risk_tools.issue_create(
            ["--title", "Add report checks", "--body", BODY],
            run=fake,
            interactive=False,
            before=before,
            after=after,
        )
    assert not any(call[:2] == ["issue", "create"] for call in fake.calls)
    before, after = project_roadmap.create_hooks(URL, "2026-12-01", run=fake)
    assert (
        risk_tools.issue_create(
            ["--title", "Add report checks", "--body", BODY],
            run=fake,
            interactive=False,
            before=before,
            after=after,
        )
        == 0
    )
    assert fake.items["I_41"]["target"] == "2026-12-01"


def test_explicit_target_cannot_contradict_a_due_date(tmp_path: Path) -> None:
    """AC4: the Milestone due date is authoritative when it exists."""
    fake = FakeGitHub()
    fake.add_issue(41, "2026-10-15T10:00:00Z", 3)
    status, output = sync(
        fake, issue=41, tmp=tmp_path, target_date="2026-11-30"
    )
    assert status == 1 and "drop --target-date" in output
    assert fake.add_calls == 0


def test_pull_requests_are_never_projected(tmp_path: Path) -> None:
    """Scope: only Issues are synced."""
    fake = FakeGitHub()
    fake.issues[50] = {"number": 50, "pull_request": {}}
    status, output = sync(fake, issue=50, tmp=tmp_path)
    assert status == 1 and "is a pull request" in output


# ---------------------------------------------------------------- AC5 (R2)


def test_resync_is_idempotent(tmp_path: Path) -> None:
    """AC5: a second sync writes nothing and adds no item."""
    fake = FakeGitHub()
    fake.add_issue(41, "2026-10-15T10:00:00Z", 3)
    assert sync(fake, issue=41, tmp=tmp_path)[0] == 0
    writes = (fake.add_calls, fake.set_calls)
    status, output = sync(fake, issue=41, tmp=tmp_path)
    assert status == 0
    assert "(unchanged)" in output and "existing item" in output
    assert (fake.add_calls, fake.set_calls) == writes
    assert len(fake.items) == 1


def test_due_date_change_lists_a_diff_and_needs_confirmation(
    tmp_path: Path,
) -> None:
    """AC5/R2: a different existing date is shown, not silently replaced."""
    fake = FakeGitHub()
    fake.add_issue(41, "2026-10-15T10:00:00Z", 3)
    assert sync(fake, issue=41, tmp=tmp_path)[0] == 0
    fake.milestones[3]["due_on"] = "2026-11-14T00:00:00Z"
    status, output = sync(fake, issue=41, tmp=tmp_path)
    assert status == 1
    assert (
        "Project target 2026-10-31 -> 2026-11-14 (overwrite needs "
        "confirmation)" in output
    )
    assert "nothing was written" in output
    assert fake.items["I_41"]["target"] == "2026-10-31"
    status, output = sync(fake, issue=41, tmp=tmp_path, ask=lambda _prompt: "n")
    assert status == 1 and fake.items["I_41"]["target"] == "2026-10-31"
    status, output = sync(fake, issue=41, tmp=tmp_path, ask=lambda _prompt: "y")
    assert status == 0 and fake.items["I_41"]["target"] == "2026-11-14"


def test_milestone_reassignment_resyncs_the_whole_milestone(
    tmp_path: Path,
) -> None:
    """AC5: --milestone follows the current Milestone; PRs are skipped."""
    fake = FakeGitHub()
    fake.milestones[4] = {"number": 4, "title": "GA", "due_on": None}
    fake.add_issue(41, "2026-10-15T10:00:00Z", 3)
    fake.add_issue(42, "2026-10-16T00:10:00Z", 3)
    assert sync(fake, milestone=3, tmp=tmp_path)[0] == 0
    assert fake.items["I_42"] == {
        "id": "ITEM_I_42",
        "start": "2026-10-16",
        "target": "2026-10-31",
    }
    fake.milestones[4]["due_on"] = "2026-12-15T00:00:00Z"
    fake.issues[42]["milestone"] = fake.milestones[4]
    status, output = sync(fake, milestone=4, tmp=tmp_path)
    assert status == 1 and "2026-10-31 -> 2026-12-15" in output
    assert "#41" not in output
    status, _output = sync(fake, milestone=4, tmp=tmp_path, confirm=True)
    assert status == 0 and fake.items["I_42"]["target"] == "2026-12-15"
    assert fake.items["I_41"]["target"] == "2026-10-31"


# ---------------------------------------------------------- AC6 (R3) / AC7


def test_partial_write_keeps_the_issue_and_retry_is_idempotent(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """AC6/R3: a failed write prints one repair; rerun adds no duplicate."""
    fake = FakeGitHub()
    fake.fail_set_at = 1  # the second date write (target) fails once
    out = io.StringIO()
    before, after = project_roadmap.create_hooks(URL, "", run=fake, out=out)
    status = risk_tools.issue_create(
        ["--title", "Add report checks", "--body", BODY, "-m", "Beta"],
        run=fake,
        interactive=False,
        before=before,
        after=after,
    )
    capsys.readouterr()
    transcript = out.getvalue()
    assert status == 1
    assert 41 in fake.issues
    assert not any(
        "deleteIssue" in " ".join(call) or "delete" in call
        for call in fake.calls
    )
    repairs = re.findall(r"Repair \(idempotent\): (.*)", transcript)
    assert repairs == ["csarc issue sync-project --issue 41 --repo o/r"]
    assert fake.items["I_41"]["start"] == "2026-10-15"
    assert fake.items["I_41"]["target"] is None
    status, _output = sync(fake, issue=41, tmp=tmp_path)
    assert status == 0
    assert fake.items["I_41"]["target"] == "2026-10-31"
    assert len(fake.items) == 1
    assert fake.add_calls == 1


def test_add_failure_after_create_is_repairable(tmp_path: Path) -> None:
    """AC6: an add failure keeps the Issue; the repair adds it once."""
    fake = FakeGitHub()
    fake.fail_on["add"] = 1
    out = io.StringIO()
    before, after = project_roadmap.create_hooks(URL, "", run=fake, out=out)
    status = risk_tools.issue_create(
        ["--title", "Add report checks", "--body", BODY, "--milestone=Beta"],
        run=fake,
        interactive=False,
        before=before,
        after=after,
    )
    assert status == 1 and 41 in fake.issues and not fake.items
    assert "Issue #41 was created and kept" in out.getvalue()
    assert sync(fake, issue=41, tmp=tmp_path)[0] == 0
    assert len(fake.items) == 1


def test_rate_limit_stops_with_a_repair_command(tmp_path: Path) -> None:
    """AC7: a rate-limited GraphQL call writes nothing further."""
    fake = FakeGitHub()
    fake.add_issue(41, "2026-10-15T10:00:00Z", 3)
    fake.fail_on["rate_limited"] = 1
    status, output = sync(fake, issue=41, tmp=tmp_path)
    assert status == 1
    assert "rate limit" in output
    assert "csarc issue sync-project --issue 41 --repo o/r" in output
    assert fake.add_calls == fake.set_calls == 0


def test_gh_runner_marks_rate_limit_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC7: a REST rate-limit error is named, not hidden."""

    class Result:
        returncode = 1
        stdout = ""
        stderr = "HTTP 403: API rate limit exceeded for user"

    monkeypatch.setattr(
        project_roadmap.subprocess, "run", lambda *_a, **_k: Result()
    )
    with pytest.raises(ProjectSyncError, match="rate limit reached"):
        project_roadmap.gh_runner(["api", "rate_limit"])


def test_cli_routes_sync_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI forwards sync-project options unchanged."""
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        project_roadmap,
        "command_sync",
        lambda repo, **kwargs: seen.append({"repo": repo, **kwargs}) or 0,
    )
    assert (
        cli.main(
            [
                "issue",
                "sync-project",
                "--milestone",
                "3",
                "--target-date",
                "2026-12-01",
                "--yes",
            ]
        )
        == 0
    )
    assert seen[0]["milestone"] == 3 and seen[0]["confirm"] is True
    assert seen[0]["issue"] is None
    with pytest.raises(SystemExit):
        cli.main(["issue", "sync-project"])
