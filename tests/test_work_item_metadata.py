"""Tests for GitHub work-item metadata synchronization."""

import importlib.util
from pathlib import Path
from typing import Any

MODULE_PATH = (
    Path(__file__).parents[1] / "scripts" / "sync_work_item_metadata.py"
)
SPEC = importlib.util.spec_from_file_location("work_item_metadata", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

MetadataError = MODULE.MetadataError
desired_pull_request_metadata = MODULE.desired_pull_request_metadata
issue_classification = MODULE.issue_classification
linked_issue_number = MODULE.linked_issue_number
sync_pull_request = MODULE.sync_pull_request


def test_linked_issue_prefers_branch_and_accepts_promotion_body() -> None:
    assert (
        linked_issue_number("feat/301-native-hierarchy", "Closes #999") == 301
    )
    assert linked_issue_number("enhancement/266-status-path", "") == 266
    assert linked_issue_number("dev/m11-native-hierarchy", "Closes #303") == 303
    assert linked_issue_number("dependabot/pip/pytest", "") is None


def test_metadata_preserves_facets_and_mirrors_issue() -> None:
    pull = {
        "user": {"login": "author", "type": "User"},
        "assignees": [{"login": "owner"}],
        "labels": [{"name": "hotfix"}, {"name": "documentation"}],
    }
    issue = {
        "labels": [{"name": "bug"}],
        "type": {"name": "Bug"},
        "milestone": {"number": 11},
    }
    assert desired_pull_request_metadata(pull, issue) == {
        "assignees": ["author", "owner"],
        "labels": ["bug", "hotfix"],
        "milestone": 11,
    }


def test_task_without_label_uses_enhancement_fallback() -> None:
    assert issue_classification({"labels": [], "type": {"name": "Task"}}) == (
        "enhancement"
    )


def test_sync_patches_pr_issue_metadata() -> None:
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(arguments: list[str], stdin: str | None) -> dict[str, Any]:
        calls.append((arguments, stdin))
        endpoint = arguments[-1]
        if endpoint.endswith("/pulls/44"):
            return {
                "head": {"ref": "fix/42-timeout"},
                "body": "Fixes #42",
            }
        if endpoint.endswith("/issues/42"):
            return {
                "labels": [{"name": "bug"}],
                "type": {"name": "Bug"},
                "milestone": {"number": 7},
            }
        if arguments[:3] == ["api", "--method", "PATCH"]:
            return {}
        return {
            "user": {"login": "author", "type": "User"},
            "assignees": [],
            "labels": [],
        }

    assert sync_pull_request("owner/repo", 44, fake_run).endswith("Issue #42")
    patch = calls[-1]
    assert patch[0][-1] == "-"
    assert '"assignees": ["author"]' in (patch[1] or "")
    assert '"milestone": 7' in (patch[1] or "")


def test_sync_skips_an_identical_patch() -> None:
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(arguments: list[str], stdin: str | None) -> dict[str, Any]:
        calls.append((arguments, stdin))
        endpoint = arguments[-1]
        if endpoint.endswith("/pulls/44"):
            return {
                "head": {"ref": "fix/42-timeout"},
                "body": "Fixes #42",
            }
        if endpoint.endswith("/issues/42"):
            return {
                "labels": [{"name": "bug"}],
                "type": {"name": "Bug"},
                "milestone": {"number": 7},
            }
        return {
            "user": {"login": "author", "type": "User"},
            "assignees": [{"login": "author"}],
            "labels": [{"name": "bug"}],
            "milestone": {"number": 7},
        }

    result = sync_pull_request("owner/repo", 44, fake_run)
    assert "already matches" in result
    assert not any("PATCH" in arguments for arguments, _ in calls)
