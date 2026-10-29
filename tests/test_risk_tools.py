"""CLI risk tools: guided Issue creation, register, and backfill (#1079)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from csarc_cli import cli, risk_controls, risk_tools

BLOCK = (
    "#### 風險與控制\n\n"
    "| ID | 類別 | 等級 | 風險 | 控制 | 預計證據 | Owner |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
    "| R1 | data | high | Loses files | Dry-run test | Regression | @alice |\n"
)
R0_BLOCK = (
    "#### 風險與控制\n\n"
    "| ID | 類別 | 等級 | 風險 | 控制 | 預計證據 | Owner |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
    "| R0 | none | — | Typo | Docs only | scope:docs | @alice |\n"
)
BARE = "### 問題\n\nWhy.\n\n### 完成條件\n\n- [ ] AC1: One\n"
VALID = BARE + "\n### 補充\n\n" + BLOCK


class Stub:
    """Record `gh` calls and serve read-only API fixtures."""

    def __init__(self, responses: dict[str, object] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.responses = responses or {}
        self.bodies: list[str] = []

    def __call__(self, command: list[str]) -> str:
        self.calls.append(command)
        if command[:2] == ["issue", "create"]:
            self.bodies.append(
                Path(command[command.index("--body-file") + 1]).read_text(
                    encoding="utf-8"
                )
                if "--body-file" in command
                else ""
            )
            return "https://github.com/o/r/issues/1\n"
        if command[:2] == ["repo", "view"]:
            return "o/r\n"
        return json.dumps(self.responses[command[-1]])


def test_a_valid_body_creates_the_issue_with_arguments_unchanged() -> None:
    stub = Stub()
    status = risk_tools.issue_create(
        ["--title", "Add report checks", "--body", VALID, "--label", "bug"],
        run=stub,
        interactive=False,
    )
    assert status == 0
    command = stub.calls[0]
    assert command[:6] == [
        "issue",
        "create",
        "--title",
        "Add report checks",
        "--label",
        "bug",
    ]
    assert stub.bodies == [VALID]


def test_missing_block_fails_before_gh_without_a_tty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stub = Stub()
    status = risk_tools.issue_create(
        ["--title", "Delete stale tokens", "--body", BARE],
        run=stub,
        interactive=False,
    )
    assert status == 1
    assert stub.calls == []
    err = capsys.readouterr().err
    assert "requirement-trace: RK01" in err
    assert "| R1 | data | TODO" in err


def test_tty_suggests_rows_the_author_confirms() -> None:
    stub = Stub()
    answers = iter(
        [
            "k",
            "high",
            "Leaked token stays valid",
            "Rotation test",
            "Regression",
            "",
            "d",
            "y",
        ]
    )
    status = risk_tools.issue_create(
        [
            "--title",
            "Rotate leaked token on delete",
            "--assignee",
            "alice",
            "--body",
            BARE,
        ],
        run=stub,
        ask=lambda _prompt: next(answers),
        interactive=True,
    )
    assert status == 0
    body = stub.bodies[0]
    assert body.startswith(BARE.rstrip("\n"))
    assert "| R1 | security | high | Leaked token stays valid" in body
    assert "| @alice |" in body
    assert risk_tools.create_problems(body) == []


def test_tty_cancel_creates_nothing() -> None:
    stub = Stub()
    answers = iter(["k", "low", "Risk text", "Control", "Evidence", "", "n"])
    with pytest.raises(risk_tools.RiskToolError, match="cancelled"):
        risk_tools.issue_create(
            ["--title", "Fix report bug", "--assignee", "bob", "-b", BARE],
            run=stub,
            ask=lambda _prompt: next(answers),
            interactive=True,
        )
    assert stub.calls == []


def test_exempt_trackers_pass_through_and_body_is_required(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stub = Stub()
    arguments = ["--title", "Milestone 9: Tracker", "--body", "x"]
    assert risk_tools.issue_create(arguments, run=stub) == 0
    assert stub.calls == [["issue", "create", *arguments]]
    with pytest.raises(risk_tools.RiskToolError, match="exactly one"):
        risk_tools.issue_create(["--title", "Add report"], run=stub)
    out = tmp_path / "body.md"
    status = risk_tools.issue_create(
        ["--title", "Add report checks", f"--body={VALID}"],
        out,
        run=stub,
        interactive=False,
    )
    assert status == 0
    assert out.read_text(encoding="utf-8") == VALID
    assert "--body-file" in capsys.readouterr().out
    assert len(stub.calls) == 1
    stdin = io.StringIO(VALID)
    assert (
        risk_tools.issue_create(
            ["--title", "Add report", "-F", "-"], run=stub, stdin=stdin
        )
        == 0
    )
    assert stub.bodies[-1] == VALID


def issue(number: int, body: str, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    """Return one REST Issue fixture."""
    return {
        "number": number,
        "title": extra.pop("title", f"Work item {number}"),
        "state": extra.pop("state", "open"),
        "body": body,
        "labels": [{"name": name} for name in extra.pop("labels", [])],
        "assignees": [{"login": "alice"}],
        "milestone": {"number": 18},
        **extra,
    }


def evidence(number: int, body: str, mapping: dict[str, str]) -> str:
    """Return a PR body mapping one Issue to evidence."""
    out: list[str] = []
    digest = risk_controls.coverage_digest(
        risk_controls.parse_acs(body, out), risk_controls.parse_risks(body, out)
    )
    rows = "".join(f"| {key} | {value} |\n" for key, value in mapping.items())
    return (
        f"Closes #{number}\n\n## Requirement evidence\n\nIssue: #{number}\n"
        f"Coverage: {digest}\n\n| ID | 證據 |\n| --- | --- |\n{rows}"
    )


def register_stub() -> Stub:
    """Serve one repository with every coverage and trace state."""
    r0 = BARE + "\n### 補充\n\n" + R0_BLOCK
    issues = [
        issue(1, VALID),
        issue(2, r0, state="closed"),
        issue(3, BARE),
        issue(4, "x", title="Milestone 18: Tracker"),
        issue(5, VALID),
        issue(6, VALID),
    ]
    stale_body = VALID.replace("AC1: One", "AC1: Changed")
    pulls = [
        {
            "number": 11,
            "merged_at": "2026-10-01T00:00:00Z",
            "body": evidence(
                1,
                VALID,
                {
                    "AC1": "tests/test_x.py::test_one",
                    "R1": "accepted: Solo maintainer accepts this risk",
                },
            ),
        },
        {
            "number": 12,
            "merged_at": "2026-10-01T00:00:00Z",
            "body": evidence(
                2, r0, {"AC1": "check:verify", "R0": "scope:docs"}
            ),
        },
        {
            "number": 15,
            "merged_at": None,
            "body": evidence(5, stale_body, {"AC1": "check:verify"}),
        },
        {
            "number": 16,
            "merged_at": None,
            "body": evidence(
                6, VALID, {"AC1": "tests/gone.py", "R1": "check:verify"}
            ),
        },
    ]
    return Stub(
        {
            "repos/o/r/issues?state=all&per_page=100&milestone=18": [issues],
            "repos/o/r/pulls?state=all&per_page=100": [pulls],
            "repos/o/r": {"default_branch": "main"},
        }
    )


def test_register_is_read_only_deterministic_and_lists_exceptions() -> None:
    stub = register_stub()
    exists = {"tests/test_x.py": True, "tests/gone.py": False}.get
    first = risk_tools.register(
        "", milestone=18, state="all", run=stub, exists=exists
    )
    second = risk_tools.register(
        "", milestone=18, state="all", run=register_stub(), exists=exists
    )
    assert first == second
    assert all(
        call[0] in {"api", "repo"} and "--method" not in call
        for call in stub.calls
    )
    coverage = {row["number"]: row["coverage"] for row in first["issues"]}
    assert coverage == {
        1: "valid",
        2: "no-material-risk",
        3: "missing",
        4: "exempt",
        5: "valid",
        6: "valid",
    }
    traces = {row["number"]: row["trace"] for row in first["issues"]}
    assert traces[1] == "current"
    assert traces[5] == "stale"
    assert first["no_material_risk"] == [
        {"issue": 2, "state": "closed", "closed_by": 12}
    ]
    assert first["accepted_risks"][0]["id"] == "R1"
    assert {"evidence": "tests/gone.py", "refs": ["#6/AC1"]} in first["stale"]
    markdown = risk_tools.render_register(first)
    for heading in (
        "## Coverage",
        "## No material risk",
        "## Accepted risks",
        "## Evidence index",
        "## Stale",
    ):
        assert heading in markdown


def backfill_stub(body: str = VALID) -> Stub:
    """Serve merged pre-K1 Milestone pull requests."""
    pulls = [
        {
            "number": 21,
            "merged_at": "2026-10-01T00:00:00Z",
            "milestone": {"number": 18},
            "merge_commit_sha": "d" * 40,
            "head": {"sha": "a" * 40},
            "body": "Closes #1",
        },
        {
            "number": 22,
            "merged_at": "2026-10-02T00:00:00Z",
            "milestone": {"number": 18},
            "body": evidence(1, VALID, {"AC1": "check:verify"}),
        },
        {"number": 23, "merged_at": None, "milestone": {"number": 18}},
    ]
    return Stub(
        {
            "repos/o/r/pulls?state=closed&per_page=100": [pulls],
            "repos/o/r/issues/1": issue(1, body),
        }
    )


def test_backfill_manifest_reads_back_and_detects_drift(tmp_path: Path) -> None:
    manifest = risk_tools.backfill("", 18, run=backfill_stub())
    assert [entry["pull_request"] for entry in manifest["entries"]] == [21]
    assert manifest["entries"][0]["acceptance"] == ["AC1"]
    assert manifest == risk_tools.backfill("", 18, run=backfill_stub())
    path = tmp_path / "backfill.json"
    path.write_bytes(risk_tools.canonical(manifest))
    digest = risk_tools.manifest_digest(manifest)
    assert risk_tools.verify_backfill(path, digest, run=backfill_stub()) == []
    assert risk_tools.verify_backfill(path, "sha256:" + "0" * 64, live=False)
    drifted = backfill_stub(VALID.replace("AC1: One", "AC1: Two"))
    assert risk_tools.verify_backfill(path, digest, run=drifted) == [
        "live readback differs from the saved manifest"
    ]


def test_suggest_lists_open_issues_without_a_valid_block() -> None:
    stub = Stub(
        {
            "repos/o/r/issues?state=open&per_page=100": [
                [
                    issue(1, VALID),
                    issue(3, BARE, title="Rotate leaked token"),
                    issue(4, "x", labels=["promotion"]),
                    issue(7, "x", pull_request={}),
                ]
            ],
            "repos/o/r/issues/4": issue(4, "x", labels=["promotion"]),
        }
    )
    found = risk_tools.suggest("", issue=None, run=stub)
    assert [item["issue"] for item in found] == [3]
    assert "| R1 | security |" in found[0]["suggestion"]
    exempt = risk_tools.suggest("", issue=4, run=stub)
    assert exempt[0]["exempt_reason"] == "promotion"


def test_cli_routes_issue_and_risk_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[object] = []
    monkeypatch.setattr(
        risk_tools, "work_item_arguments", lambda arguments: [*arguments, "+"]
    )
    monkeypatch.setattr(
        risk_tools,
        "issue_create",
        lambda arguments, body_out: seen.append((arguments, body_out)) or 0,
    )
    assert cli.main(["issue", "create", "--", "--title", "Add report"]) == 0
    assert seen == [(["--title", "Add report", "+"], None)]
    monkeypatch.setattr(
        risk_tools,
        "register",
        lambda repo, **kwargs: {"repository": repo, **kwargs},
    )
    assert cli.main(["risk", "register", "--repo", "o/r", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["repository"] == "o/r"
    assert cli.main(["risk", "backfill"]) == 2


def test_update_reports_the_new_gate_as_a_behavior_change() -> None:
    added = cli.Plan((cli.RISK_CONTROLS_PATH,), (), (), (), (), (), ())
    rows = cli.risk_behavior_changes(added)
    assert rows is not None
    assert rows[0]["subject"] == "risk-controls"
    assert "csarc risk suggest --open" in str(rows[0]["note"])
    present = cli.Plan((), (cli.RISK_CONTROLS_PATH,), (), (), (), (), ())
    assert cli.risk_behavior_changes(present) is None


# Issue #1081 AC7: the K1 backfill manifest saved before beta.2 for the
# Milestone 18 work pull requests merged before the Requirement evidence
# gate. The live readback (`csarc risk backfill --verify`) runs at
# promotion; this offline check keeps the saved bytes and digest bound.
M18_BACKFILL = Path(__file__).resolve().parents[1] / (
    "docs/evidence/m18-risk-backfill.json"
)
M18_BACKFILL_DIGEST = (
    "sha256:32d064261642befebb51ca272ea264a6cb32a3b4942ecc72dc5bc1180cd0f7f6"
)


def test_saved_m18_backfill_manifest_is_canonical_and_bound() -> None:
    assert (
        risk_tools.verify_backfill(
            M18_BACKFILL, M18_BACKFILL_DIGEST, live=False
        )
        == []
    )
    manifest = json.loads(M18_BACKFILL.read_bytes())
    assert manifest["format"] == risk_tools.BACKFILL_FORMAT
    assert manifest["milestone"] == 18
    pulls = [entry["pull_request"] for entry in manifest["entries"]]
    assert pulls == sorted(set(pulls))
    for entry in manifest["entries"]:
        assert len(entry["merge_commit_sha"]) == 40
        assert entry["acceptance"]
        assert entry["risks"]
        assert entry["problems"] == []


class TypesStub:
    """A `gh` runner whose repository has `count` Issue Types."""

    def __init__(self, count: str) -> None:
        self.count = count
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str]) -> str:
        self.calls.append(command)
        if command[:2] == ["repo", "view"]:
            return "o/r\n"
        assert command[:2] == ["api", "graphql"], command
        if self.count == "error":
            raise risk_tools.RiskToolError("gh api failed")
        return self.count + "\n"


def test_work_item_arguments_set_native_type_and_assignee() -> None:
    """#1344 AC2: the fallback label becomes a Type; @me is assigned."""
    run = TypesStub("3")
    assert risk_tools.work_item_arguments(
        ["--title", "Fix report", "--label", "bug,security", "-b", "x"], run
    ) == [
        "--title",
        "Fix report",
        "-b",
        "x",
        "--assignee",
        "@me",
        "--label",
        "security",
        "--type",
        "Bug",
    ]
    assert 'owner:"o",name:"r"' in run.calls[1][3]
    assert risk_tools.work_item_arguments(
        ["-a", "bob", "--type", "Task", "--label=enhancement,documentation"],
        TypesStub("3"),
    ) == ["-a", "bob", "--type", "Task", "--label", "documentation"]
    assert risk_tools.work_item_arguments(
        ["--repo", "x/y", "-l", "enhancement"], TypesStub("1")
    )[-2:] == ["--type", "Feature"]


def test_work_item_arguments_keep_fallback_labels_without_types() -> None:
    """#1344 AC3: a repository without Issue Types keeps its label."""
    for count in ("0", "null", "", "error"):
        assert risk_tools.work_item_arguments(
            ["--title", "Fix report", "--label", "bug"], TypesStub(count)
        ) == ["--title", "Fix report", "--label", "bug", "--assignee", "@me"]


def test_work_item_arguments_require_a_type_where_types_exist() -> None:
    """#1344 AC2: no Type and no fallback label fails with the fix."""
    with pytest.raises(risk_tools.RiskToolError, match="--type Bug"):
        risk_tools.work_item_arguments(
            ["--title", "Fix report"], TypesStub("3")
        )
    tracker = ["--title", "Milestone 9: Tracker"]
    assert risk_tools.work_item_arguments(tracker, TypesStub("3")) == [
        *tracker,
        "--assignee",
        "@me",
    ]
