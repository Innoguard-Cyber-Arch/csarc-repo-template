import json
import re
import runpy
from pathlib import Path

import pytest

SPEC_MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "spec_to_issue.py")
)
SpecError = SPEC_MODULE["SpecError"]
build_issue_body = SPEC_MODULE["build_issue_body"]
build_milestone_description = SPEC_MODULE["build_milestone_description"]
find_issue = SPEC_MODULE["find_issue"]
find_milestone = SPEC_MODULE["find_milestone"]
load_labels = SPEC_MODULE["load_labels"]
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
