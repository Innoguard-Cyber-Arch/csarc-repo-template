import json
import re
import runpy
import sys
from pathlib import Path

import pytest

SPEC_MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "spec_to_issue.py")
)
SpecError = SPEC_MODULE["SpecError"]
audit_milestone_titles = SPEC_MODULE["audit_milestone_titles"]
build_issue_body = SPEC_MODULE["build_issue_body"]
build_milestone_description = SPEC_MODULE["build_milestone_description"]
discover_adrs = SPEC_MODULE["discover_adrs"]
discover_specs = SPEC_MODULE["discover_specs"]
find_issue = SPEC_MODULE["find_issue"]
find_milestone = SPEC_MODULE["find_milestone"]
load_labels = SPEC_MODULE["load_labels"]
main = SPEC_MODULE["main"]
milestone_title_violations = SPEC_MODULE["milestone_title_violations"]
open_milestone_titles = SPEC_MODULE["open_milestone_titles"]
parse_spec_text = SPEC_MODULE["parse_spec_text"]
sync_spec = SPEC_MODULE["sync_spec"]
sync_milestone = SPEC_MODULE["sync_milestone"]
validate_unique_ids = SPEC_MODULE["validate_unique_ids"]
validate_adr = SPEC_MODULE["validate_adr"]
validate_local_links = SPEC_MODULE["validate_local_links"]
FULLWIDTH_COLON = "\N{FULLWIDTH COLON}"

VALID_SPEC = """---
id: SPEC-001
title: Add a health endpoint
owner: platform-team
priority: P1
estimate: 1-3 days
status: proposed
---

## Problem

Operators cannot distinguish a healthy service from a failed one.

## Outcome

The service exposes a health endpoint.

## Acceptance criteria

- [ ] The endpoint returns HTTP 200 when dependencies are healthy.

## Plan

- #42 — Deliver the endpoint.

## Out of scope

Changing the monitoring platform.

## Verification

Run the endpoint test and observe HTTP 200.

## References

- Preserve the decision in #12.
"""


def test_parse_valid_spec() -> None:
    spec = parse_spec_text(Path("docs/specs/SPEC-001-health.md"), VALID_SPEC)
    assert spec.spec_id == "SPEC-001"
    assert spec.status == "proposed"
    assert spec.tracking == "issue"


def test_story_tracking_is_explicit() -> None:
    story = VALID_SPEC.replace(
        "status: proposed", "status: approved\ntracking: story"
    )
    spec = parse_spec_text(Path("docs/specs/SPEC-001-health.md"), story)
    assert spec.tracking == "story"
    with pytest.raises(SpecError, match="tracking must be"):
        parse_spec_text(
            Path("invalid.md"),
            VALID_SPEC.replace(
                "status: proposed", "status: proposed\ntracking: epic"
            ),
        )


@pytest.mark.parametrize(
    ("title", "reason"),
    [
        ("Milestone 12 delivery", "Milestone prefix"),
        (
            "\uff2d\uff49\uff4c\uff45\uff53\uff54\uff4f\uff4e\uff45 "
            "\uff11\uff12 delivery",
            "Milestone prefix",
        ),
        ("#12", "sequence number"),
        ("12.", "sequence number"),
        ("\uff11\uff12\u3002", "sequence number"),
        ("Draft Better delivery", "status prefix"),
        ("WIP Outcome", "status prefix"),
        ("Done Outcome", "status prefix"),
        ("WIP: Repeatable delivery", "status prefix"),
        ("A" * 81, "3-80 characters"),
    ],
)
def test_milestone_title_rejects_mechanical_anti_patterns(
    title: str, reason: str
) -> None:
    assert any(reason in item for item in milestone_title_violations(title))


@pytest.mark.parametrize(
    "title",
    ["Repeatable release delivery", "降低導入失敗風險"],
)
def test_milestone_title_accepts_outcomes_in_project_language(
    title: str,
) -> None:
    assert milestone_title_violations(title) == ()


def test_story_spec_rejects_invalid_milestone_title() -> None:
    story = VALID_SPEC.replace(
        "title: Add a health endpoint",
        "title: Milestone 12",
    ).replace("status: proposed", "status: approved\ntracking: story")

    with pytest.raises(SpecError, match="Milestone prefix"):
        parse_spec_text(Path("docs/specs/SPEC-001-health.md"), story)


def test_current_spec_can_explicitly_skip_work_item_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = VALID_SPEC.replace(
        "status: proposed", "status: approved\ntracking: none"
    )
    spec = parse_spec_text(Path("docs/specs/SPEC-001-health.md"), current)
    calls: list[list[str]] = []

    monkeypatch.setitem(
        sync_spec.__globals__,
        "run_gh",
        lambda arguments: calls.append(arguments),
    )
    sync_spec(spec, "owner/repo", "main", "https://github.com")

    assert spec.tracking == "none"
    assert calls == []


def test_rejects_duplicate_spec_ids() -> None:
    first = parse_spec_text(Path("docs/specs/first.md"), VALID_SPEC)
    second = parse_spec_text(Path("docs/specs/second.md"), VALID_SPEC)

    with pytest.raises(SpecError, match="duplicate id SPEC-001"):
        validate_unique_ids([first, second])


VALID_DECISION = f"""# Keep the portable baseline

- **狀態{FULLWIDTH_COLON}**Accepted
- **日期{FULLWIDTH_COLON}**2026-08-24
- **來源 Issue{FULLWIDTH_COLON}**[Issue #1](https://github.com/owner/repo/issues/1)
- **實作 PR{FULLWIDTH_COLON}**[PR #2](https://github.com/owner/repo/pull/2)

## 問題與限制

The baseline must remain portable.

## 決定

Use repository files.

## 評估過的替代方案

Do not require an external database.

## 重新評估條件

Revisit when repository files no longer scale.
"""


def test_validates_adr_metadata_and_sources(tmp_path: Path) -> None:
    decision = tmp_path / "portable-baseline.md"
    decision.write_text(VALID_DECISION, encoding="utf-8")
    validate_adr(decision)

    decision.write_text(
        VALID_DECISION.replace(
            f"**狀態{FULLWIDTH_COLON}**Accepted",
            f"**狀態{FULLWIDTH_COLON}**Unknown",
        ),
        encoding="utf-8",
    )
    with pytest.raises(SpecError, match="ADR status"):
        validate_adr(decision)


def test_rejects_adr_without_pull_request_source(tmp_path: Path) -> None:
    decision = tmp_path / "portable-baseline.md"
    decision.write_text(
        VALID_DECISION.replace(
            f"- **實作 PR{FULLWIDTH_COLON}**"
            "[PR #2](https://github.com/owner/repo/pull/2)\n",
            "",
        ),
        encoding="utf-8",
    )
    with pytest.raises(SpecError, match="implementation PR URL"):
        validate_adr(decision)


@pytest.mark.parametrize(
    ("metadata", "url", "message"),
    [
        (
            f"- **來源 Issue{FULLWIDTH_COLON}**"
            "[Issue #1](https://github.com/owner/repo/issues/1)\n",
            "https://github.com/owner/repo/issues/1",
            "source Issue URL",
        ),
        (
            f"- **實作 PR{FULLWIDTH_COLON}**"
            "[PR #2](https://github.com/owner/repo/pull/2)\n",
            "https://github.com/owner/repo/pull/2",
            "implementation PR URL",
        ),
    ],
)
def test_adr_sources_must_be_metadata(
    tmp_path: Path, metadata: str, url: str, message: str
) -> None:
    decision = tmp_path / "portable-baseline.md"
    decision.write_text(
        VALID_DECISION.replace(metadata, "").replace(
            "The baseline must remain portable.",
            f"The baseline must remain portable. See {url}.",
        ),
        encoding="utf-8",
    )

    with pytest.raises(SpecError, match=message):
        validate_adr(decision)


def test_explicit_missing_spec_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="spec file does not exist"):
        discover_specs([str(tmp_path / "missing.md")])


def test_default_validation_requires_specs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["spec_to_issue.py", "validate"])

    with pytest.raises(SpecError, match="no spec files found"):
        main()


def test_discovers_current_and_legacy_adrs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = tmp_path / "docs" / "adr" / "current.md"
    legacy = tmp_path / "docs" / "decisions" / "legacy.md"
    current.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    current.write_text(VALID_DECISION, encoding="utf-8")
    legacy.write_text(VALID_DECISION, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert discover_adrs() == [
        Path("docs/adr/current.md"),
        Path("docs/decisions/legacy.md"),
    ]


def test_rejects_broken_local_memory_link(tmp_path: Path) -> None:
    spec = tmp_path / "docs" / "specs" / "SPEC-001-example.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("See [missing](../adr/missing.md).", encoding="utf-8")

    with pytest.raises(SpecError, match="linked file does not exist"):
        validate_local_links([spec], tmp_path)


def test_rejects_missing_acceptance_criteria() -> None:
    invalid = VALID_SPEC.replace("## Acceptance criteria", "## Checks")
    with pytest.raises(SpecError, match="Acceptance criteria"):
        parse_spec_text(Path("invalid.md"), invalid)


def test_accepts_completed_acceptance_criterion() -> None:
    completed = VALID_SPEC.replace("- [ ] The endpoint", "- [x] The endpoint")
    spec = parse_spec_text(Path("docs/specs/SPEC-001-health.md"), completed)
    assert spec.spec_id == "SPEC-001"


def test_rejects_missing_required_section() -> None:
    invalid = VALID_SPEC.replace("## Verification", "## Test notes")
    with pytest.raises(SpecError, match="Verification"):
        parse_spec_text(Path("invalid.md"), invalid)


def test_issue_body_links_source_and_identity() -> None:
    spec = parse_spec_text(Path("docs/specs/SPEC-001-health.md"), VALID_SPEC)
    body = build_issue_body(spec, "https://github.example/spec")
    assert "csarc-spec-id: SPEC-001" in body
    assert "https://github.example/spec" in body
    assert re.findall(r"^### .+$", body, re.MULTILINE) == [
        "### 類型",
        "### 問題",
        "### 完成條件",
        "### 補充",
    ]
    assert "**Outcome**" in body
    assert "## Outcome" not in body


def test_milestone_description_has_story_contract() -> None:
    story = VALID_SPEC.replace(
        "status: proposed", "status: approved\ntracking: story"
    )
    spec = parse_spec_text(Path("docs/specs/SPEC-001-health.md"), story)
    description = build_milestone_description(
        spec, "https://github.example/spec"
    )
    assert "csarc-story-id: SPEC-001" in description
    assert "## Acceptance criteria" in description
    assert "## Plan" in description
    assert "## Verification" in description
    assert "## References" in description


def test_find_issue_deduplicates_by_spec_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    response = json.dumps(
        [
            {
                "number": 42,
                "body": "<!-- csarc-spec-id: SPEC-001 -->\nDetails",
            }
        ]
    )

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        return response

    monkeypatch.setitem(find_issue.__globals__, "run_gh", fake_run_gh)
    assert find_issue("owner/repo", "SPEC-001") == 42
    assert '"csarc-spec-id: SPEC-001" in:body' in calls[0]
    assert "number,body" in calls[0]


def test_find_milestone_is_paginated_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        return json.dumps(
            [
                [],
                [
                    {
                        "number": 7,
                        "description": "<!-- csarc-story-id: SPEC-001 -->\n",
                    }
                ],
            ]
        )

    monkeypatch.setitem(find_milestone.__globals__, "run_gh", fake_run_gh)
    assert find_milestone("owner/repo", "SPEC-001") == 7
    assert "--paginate" in calls[0]
    assert "--slurp" in calls[0]


def test_milestone_title_audit_is_paginated_and_read_only(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        return json.dumps(
            [
                [{"number": 7, "title": "Repeatable release delivery"}],
                [{"number": 8, "title": "Draft: Better adoption"}],
            ]
        )

    monkeypatch.setitem(
        open_milestone_titles.__globals__, "run_gh", fake_run_gh
    )

    assert not audit_milestone_titles("owner/repo", ["改善交付流程", "42"])
    assert calls == [
        [
            "api",
            "--paginate",
            "--slurp",
            "repos/owner/repo/milestones?state=open&per_page=100",
        ]
    ]
    assert "status prefix" in caplog.text
    assert "sequence number" in caplog.text


def test_sync_keeps_spec_id_out_of_issue_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = parse_spec_text(Path("docs/specs/SPEC-001-health.md"), VALID_SPEC)
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        return "created"

    monkeypatch.setitem(sync_spec.__globals__, "find_issue", lambda *_: None)
    monkeypatch.setitem(sync_spec.__globals__, "run_gh", fake_run_gh)

    sync_spec(spec, "owner/repo", "main", "https://github.com")

    create = next(call for call in calls if call[:2] == ["issue", "create"])
    assert create[create.index("--title") + 1] == "Add a health endpoint"


def test_story_spec_syncs_milestone_without_creating_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = VALID_SPEC.replace(
        "status: proposed", "status: approved\ntracking: story"
    )
    spec = parse_spec_text(Path("docs/specs/SPEC-001-health.md"), story)
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        if "--paginate" in arguments:
            return "[[]]"
        return '{"number":7}'

    monkeypatch.setitem(sync_spec.__globals__, "run_gh", fake_run_gh)
    sync_spec(spec, "owner/repo", "main", "https://github.com")

    create = next(call for call in calls if "POST" in call)
    assert "repos/owner/repo/milestones" in create
    assert not any(call[:2] == ["issue", "create"] for call in calls)


def test_story_sync_updates_existing_milestone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = VALID_SPEC.replace(
        "status: proposed", "status: approved\ntracking: story"
    )
    spec = parse_spec_text(Path("docs/specs/SPEC-001-health.md"), story)
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str]) -> str:
        calls.append(arguments)
        return "{}"

    monkeypatch.setitem(
        sync_milestone.__globals__, "find_milestone", lambda *_: 7
    )
    monkeypatch.setitem(sync_milestone.__globals__, "run_gh", fake_run_gh)
    sync_milestone(spec, "owner/repo", "https://github.example/spec")

    assert calls[0][:5] == [
        "api",
        "--method",
        "PATCH",
        "repos/owner/repo/milestones/7",
        "--raw-field",
    ]


def test_load_labels_uses_policy_file(tmp_path: Path) -> None:
    policy = tmp_path / "labels.json"
    policy.write_text(
        json.dumps(
            [
                {
                    "name": "enhancement",
                    "color": "A2EEEF",
                    "description": "New feature or improvement",
                }
            ]
        ),
        encoding="utf-8",
    )
    assert load_labels(policy) == [
        {
            "name": "enhancement",
            "color": "A2EEEF",
            "description": "New feature or improvement",
        }
    ]
