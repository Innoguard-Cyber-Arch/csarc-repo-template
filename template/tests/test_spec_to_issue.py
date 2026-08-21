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
    response = '[{"number": 42, "title": "[SPEC-001] Existing issue"}]'
    monkeypatch.setitem(find_issue.__globals__, "run_gh", lambda _: response)
    assert find_issue("owner/repo", "SPEC-001") == 42


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
