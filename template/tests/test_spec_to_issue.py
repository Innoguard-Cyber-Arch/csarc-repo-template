import json
import runpy
from pathlib import Path

import pytest

SPEC_MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "spec_to_issue.py")
)
SpecError = SPEC_MODULE["SpecError"]
build_issue_body = SPEC_MODULE["build_issue_body"]
find_issue = SPEC_MODULE["find_issue"]
load_labels = SPEC_MODULE["load_labels"]
parse_spec_text = SPEC_MODULE["parse_spec_text"]
sync_spec = SPEC_MODULE["sync_spec"]

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

## Out of scope

Changing the monitoring platform.

## Verification

Run the endpoint test and observe HTTP 200.
"""


def test_parse_valid_spec() -> None:
    spec = parse_spec_text(Path("docs/specs/SPEC-001-health.md"), VALID_SPEC)
    assert spec.spec_id == "SPEC-001"
    assert spec.status == "proposed"


def test_rejects_missing_acceptance_criteria() -> None:
    invalid = VALID_SPEC.replace("## Acceptance criteria", "## Checks")
    with pytest.raises(SpecError, match="Acceptance criteria"):
        parse_spec_text(Path("invalid.md"), invalid)


def test_rejects_missing_required_section() -> None:
    invalid = VALID_SPEC.replace("## Verification", "## Test notes")
    with pytest.raises(SpecError, match="Verification"):
        parse_spec_text(Path("invalid.md"), invalid)


def test_issue_body_links_source_and_identity() -> None:
    spec = parse_spec_text(Path("docs/specs/SPEC-001-health.md"), VALID_SPEC)
    body = build_issue_body(spec, "https://github.example/spec")
    assert "csarc-spec-id: SPEC-001" in body
    assert "https://github.example/spec" in body


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
