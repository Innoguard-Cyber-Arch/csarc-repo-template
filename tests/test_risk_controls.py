"""Trace Issue requirements to risks and exact-head evidence (Issue #1079)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ci_tier  # noqa: E402
import risk_controls as rc  # noqa: E402

COPIES = (
    "scripts/risk_controls.py",
    "template/.csarc/scripts/risk_controls.py",
    "src/csarc_cli/risk_controls.py",
)
HEADER = (
    "| ID | 類別 | 等級 | 風險 | 控制 | 預計證據 | Owner |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
)
PLANNING = (
    "| ID | 類別 | 風險 | 控制 | 預計證據 | Owner |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
)
ROW = (
    "| R1 | data | high | Loses files | Dry-run test | Regression | @alice |\n"
)


def body(rows: str = ROW, acs: str = "- [ ] AC1: One\n- [x] AC2: Two\n") -> str:
    """Return one Issue body with the given AC items and risk rows."""
    return (
        "### 問題\n\nWhy.\n\n### 完成條件\n\n"
        f"{acs}\n### 補充\n\n#### 風險與控制\n\n{HEADER}{rows}"
    )


def problems(text: str) -> list[str]:
    """Return the create-stage problem codes of one Issue body."""
    out: list[str] = []
    rc.parse_risks(text, out)
    rc.parse_acs(text, out)
    return [line.split()[0] for line in out]


def test_three_copies_are_identical_small_and_stdlib_only() -> None:
    texts = {(ROOT / path).read_bytes() for path in COPIES}
    assert len(texts) == 1
    source = texts.pop()
    assert source.count(b"\n") <= 300
    tree = ast.parse(source)
    modules = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        str(node.module).split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert modules <= set(sys.stdlib_module_names) | {"__future__"}


def test_a_complete_block_and_the_m18_planning_form_parse() -> None:
    assert problems(body()) == []
    planning = body().replace(HEADER + ROW, "")
    planning = planning.replace(
        "#### 風險與控制",
        rc.LABELS[1],
    )
    planning += (
        PLANNING + "| R1 | rollout | Lock | Cutover | Tests | @alice |\n"
    )
    out: list[str] = []
    risks = rc.parse_risks(planning, out)
    assert out == []
    assert risks[0]["等級"] == "unrated"


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("### 完成條件\n\n- [ ] AC1: x\n", "RK01"),
        (body() + "\n#### 風險與控制\n\n" + HEADER + ROW, "RK02"),
        (body().replace("| 等級 |", "| Level |"), "RK03"),
        (body(rows=ROW.replace("| @alice |", "")), "RK05"),
        (body(rows=ROW.replace("R1", "R100")), "RK05"),
        (body(rows=ROW + ROW), "RK06"),
        (body(rows=ROW + ROW.replace("R1", "R0")), "RK07"),
        (body(rows=ROW.replace("data", "Data Loss")), "RK08"),
        (body(rows=ROW.replace("high", "severe")), "RK09"),
        (body(rows=ROW.replace("Dry-run test", "TODO")), "RK10"),
        (body(rows=ROW.replace("@alice", "alice")), "RK11"),
        (body(rows=ROW.replace("Loses files", "ghp_abcdefghijklmn")), "RK12"),
        (body(rows=ROW.replace("Loses files", "a@example.com")), "RK12"),
        (body(acs="Nothing to check\n"), "RK13"),
        (body(acs="- [ ] AC2: Two\n- [ ] AC1: One\n"), "RK14"),
    ],
)
def test_malformed_blocks_fail_closed(text: str, code: str) -> None:
    assert code in problems(text)


def test_a_label_inside_a_fence_does_not_count() -> None:
    fenced = "```\n#### 風險與控制\n```\n"
    assert problems(fenced + "### 完成條件\n\n- [ ] x\n") == ["RK01"]
    assert "RK02" not in problems(body() + "\n~~~\n#### 風險與控制\n~~~\n")


def test_messages_never_echo_free_text() -> None:
    hostile = ROW.replace("Loses files", "::error::pwned TODO")
    out: list[str] = []
    rc.parse_risks(body(rows=hostile), out)
    assert out
    assert all("::error::" not in line for line in out)


def evidence(mapping: dict[str, str], coverage: str, issue: int = 7) -> str:
    """Return one PR body with a Requirement evidence section."""
    rows = "".join(f"| {key} | {value} |\n" for key, value in mapping.items())
    return (
        f"Closes #{issue}\n\n## Requirement evidence\n\nIssue: #{issue}\n"
        f"Coverage: {coverage}\n\n| ID | 證據 |\n| --- | --- |\n{rows}"
    )


def coverage(text: str) -> str:
    """Return the coverage digest of one Issue body."""
    out: list[str] = []
    return rc.coverage_digest(
        rc.parse_acs(text, out), rc.parse_risks(text, out)
    )


GOOD = {
    "AC1": "tests/test_x.py::test_one",
    "AC2": "manual: https://github.com/o/r/pull/1#issuecomment-2 Reviewed log",
    "R1": "accepted: Solo maintainer accepts the residual risk",
}


def run_ready(
    issue_body: str,
    mapping: dict[str, str],
    paths: tuple[str, ...] = ("src/x.py",),
    digest: str | None = None,
    assignees: tuple[str, ...] = ("Alice",),
) -> tuple[dict[str, object], list[str], list[str]]:
    """Run the Ready stage with an in-memory head tree."""
    files = {"tests/test_x.py": "def test_one():\n    pass\n"}
    pr_body = evidence(mapping, digest or coverage(issue_body))
    return rc.ready(
        (7, issue_body, list(assignees)),
        pr_body,
        list(paths),
        ci_tier.scope_for,
        files.get,
    )


def test_ready_records_the_trace_and_lists_self_acceptance() -> None:
    trace, out, notes = run_ready(body(), GOOD)
    assert out == []
    assert trace["coverage_digest"] == coverage(body())
    assert trace["evidence"] == dict(sorted(GOOD.items()))
    assert str(trace["body_digest"]).startswith("sha256:")
    assert notes == ["#7 self-accepted: R1(high)"]


@pytest.mark.parametrize(
    ("mapping", "code"),
    [
        ({k: v for k, v in GOOD.items() if k != "AC2"}, "RK26"),
        ({**GOOD, "AC9": "check:verify"}, "RK27"),
        ({**GOOD, "AC1": "accepted: Accepting a criterion is invalid"}, "RK28"),
        ({**GOOD, "R1": "scope:docs"}, "RK28"),
        ({**GOOD, "AC1": "tests/test_missing.py"}, "RK29"),
        ({**GOOD, "AC1": "tests/test_x.py::test_two"}, "RK29"),
        ({**GOOD, "AC1": "pending soon"}, "RK23"),
        ({**GOOD, "AC1": "accepted: TODO later please"}, "RK23"),
    ],
)
def test_ready_requires_complete_known_evidence(
    mapping: dict[str, str], code: str
) -> None:
    _, out, _ = run_ready(body(), mapping)
    assert code in [line.split()[0] for line in out]


def test_reordering_criteria_after_ready_makes_coverage_stale() -> None:
    before = coverage(body(acs="- [ ] One\n- [ ] Two\n"))
    reordered = body(acs="- [ ] Two\n- [ ] One\n")
    _, out, _ = run_ready(reordered, GOOD, digest=before)
    assert [line.split()[0] for line in out] == ["RK25"]
    checked = body(acs="- [x] One\n- [x] Two\n")
    assert coverage(checked) == before


def test_owner_must_be_an_issue_assignee() -> None:
    _, out, _ = run_ready(body(), GOOD, assignees=("bob",))
    assert [line.split()[0] for line in out] == ["RK15"]


def test_duplicate_evidence_rows_and_missing_section_fail() -> None:
    out: list[str] = []
    rc.parse_evidence("Closes #7", out)
    assert out[0].startswith("RK20")
    out = []
    doubled = evidence(GOOD, "x").replace(
        "| AC1 |", "| AC1 | check:verify |\n| AC1 |"
    )
    rc.parse_evidence(doubled, out)
    assert any(line.startswith("RK22") for line in out)


R0 = "| R0 | none | — | Typo only | Docs-only change | scope:docs | @alice |\n"


@pytest.mark.parametrize(
    ("paths", "ok"),
    [
        (("docs/guide.md",), True),
        (("README.md", ".github/ISSUE_TEMPLATE/task.yml"), True),
        (("SECURITY.md",), False),
        ((".github/SECURITY.md",), False),
        (("docs/ci-policy.md",), False),
        ((".csarc/docs/ci-policy.md",), False),
        (("AGENTS.md",), False),
        (("docs/guide.md", "scripts/x.py"), False),
    ],
)
def test_r0_only_covers_docs_outside_the_security_list(
    paths: tuple[str, ...], ok: bool
) -> None:
    issue_body = body(rows=R0, acs="- [ ] Fix typo\n")
    mapping = {"AC1": "check:verify", "R0": "scope:docs"}
    _, out, notes = run_ready(issue_body, mapping, paths=paths)
    assert (out == []) is ok
    if ok:
        assert notes[0].startswith("#7 R0 declared")
    else:
        assert out[0].startswith("RK30")
        assert all(path not in out[0] for path in paths)


def test_hotfix_and_maintenance_routes_are_untraced() -> None:
    assert rc.traced_route("main", "fix/42-hotfix")
    assert rc.traced_route("dev/m18-x", "feat/1079-trace")
    for head in (
        "release-please--branches--main",
        "release/v1.2.3",
        "sync/main-to-m18-x-abcdef1",
        "dependabot/pip/x",
        "automation/x",
    ):
        assert not rc.traced_route("main", head)
    assert not rc.traced_route("main", "promote/m18-x")
    assert rc.traced_route("dev/m18-x", "dev/m18-x-child")


def test_create_stage_cli_reports_problems(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(body()))
    assert rc.main() == 0
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("no block"))
    assert rc.main() == 1
    assert "requirement-trace: RK01" in capsys.readouterr().err


FILLED_ROW = "| data | high | Loss | Test | Regression | @alice |"
FILLED_R0 = "| none | — | Typo | Docs only | scope:docs | @alice |"


@pytest.mark.parametrize(
    "form", ["task.yml", "bug.yml", "feature.yml", "documentation.yml"]
)
def test_issue_forms_prefill_a_parsable_skeleton(form: str) -> None:
    for root in (ROOT / ".github", ROOT / "template/.github"):
        text = (root / "ISSUE_TEMPLATE" / form).read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        fields = {item.get("id"): item for item in data["body"]}
        assert {"problem", "acceptance", "supplement"} <= set(fields)
        assert fields["supplement"]["validations"]["required"] is False
        value = fields["supplement"]["attributes"]["value"]
        prefix = "### 完成條件\n\n- [ ] Done\n\n### 補充\n\n"
        codes = set(problems(prefix + value))
        assert codes
        assert codes <= {"RK08", "RK09", "RK10", "RK11"}
        concrete = value.replace(
            "| TODO | TODO | TODO | TODO | TODO | TODO |", FILLED_ROW
        ).replace("| none | — | TODO | TODO | scope:docs | TODO |", FILLED_R0)
        assert problems(prefix + concrete) == []
