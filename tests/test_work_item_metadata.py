"""Tests for GitHub work-item metadata synchronization."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

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
linked_issue_numbers = MODULE.linked_issue_numbers
remind_missing_milestone = MODULE.remind_missing_milestone
resolve_workflow_run_pr = MODULE.resolve_workflow_run_pr
sync_issue_pull_requests = MODULE.sync_issue_pull_requests
sync_pull_request = MODULE.sync_pull_request


def test_linked_issue_prefers_branch_and_accepts_promotion_body() -> None:
    assert (
        linked_issue_number("feat/301-native-hierarchy", "Closes #999") == 301
    )
    assert linked_issue_number("enhancement/266-status-path", "") == 266
    assert linked_issue_number("dev/m11-native-hierarchy", "Closes #303") == 303
    assert linked_issue_number("dependabot/pip/pytest", "") is None


def test_linked_issue_numbers_deduplicate_and_expose_conflicts() -> None:
    assert linked_issue_numbers(
        "fix/42-timeout", "Fixes #42\n\nResolves #99"
    ) == (42, 99)
    assert linked_issue_numbers("fix/42-timeout", "Fixes #42") == (42,)


def test_workflow_run_resolves_one_exact_open_pr() -> None:
    def fake_run(
        _arguments: list[str], _stdin: str | None
    ) -> list[dict[str, Any]]:
        return [
            {
                "number": 44,
                "state": "open",
                "head": {
                    "sha": "abc123",
                    "ref": "fix/42-timeout",
                    "repo": {"full_name": "fork/repo"},
                },
                "base": {"repo": {"full_name": "owner/repo"}},
            },
            {
                "number": 45,
                "state": "closed",
                "head": {
                    "sha": "abc123",
                    "ref": "fix/42-timeout",
                    "repo": {"full_name": "fork/repo"},
                },
                "base": {"repo": {"full_name": "owner/repo"}},
            },
        ]

    assert (
        resolve_workflow_run_pr(
            "owner/repo",
            "abc123",
            "fork/repo",
            "fix/42-timeout",
            fake_run,
        )
        == 44
    )


def test_workflow_run_rejects_zero_or_multiple_exact_prs() -> None:
    exact = {
        "number": 44,
        "state": "open",
        "head": {
            "sha": "abc123",
            "ref": "fix/42-timeout",
            "repo": {"full_name": "fork/repo"},
        },
        "base": {"repo": {"full_name": "owner/repo"}},
    }

    for pulls in ([], [exact, {**exact, "number": 45}]):

        def fake_run(
            _arguments: list[str],
            _stdin: str | None,
            result: list[dict[str, Any]] = pulls,
        ) -> list[dict[str, Any]]:
            return result

        try:
            resolve_workflow_run_pr(
                "owner/repo",
                "abc123",
                "fork/repo",
                "fix/42-timeout",
                fake_run,
            )
        except MetadataError as error:
            assert "exactly one" in str(error)
        else:
            raise AssertionError("ambiguous workflow run should fail closed")


def test_workflow_run_checks_every_page_for_ambiguity() -> None:
    def exact(number: int) -> dict[str, Any]:
        return {
            "number": number,
            "state": "open",
            "head": {
                "sha": "abc123",
                "ref": "fix/42-timeout",
                "repo": {"full_name": "fork/repo"},
            },
            "base": {"repo": {"full_name": "owner/repo"}},
        }

    def fake_run(
        arguments: list[str], _stdin: str | None
    ) -> list[list[dict[str, Any]]]:
        assert "--paginate" in arguments
        assert "--slurp" in arguments
        return [[exact(44)], [exact(45)]]

    try:
        resolve_workflow_run_pr(
            "owner/repo",
            "abc123",
            "fork/repo",
            "fix/42-timeout",
            fake_run,
        )
    except MetadataError as error:
        assert "found 2" in str(error)
    else:
        raise AssertionError("cross-page ambiguity should fail closed")


def test_metadata_preserves_facets_and_mirrors_issue() -> None:
    pull = {
        "user": {"login": "author", "type": "User"},
        "assignees": [{"login": "owner"}],
        "labels": [{"name": "hotfix"}, {"name": "documentation"}],
    }
    issue = {
        "labels": [],
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


def test_label_is_used_only_without_a_native_type() -> None:
    assert issue_classification({"labels": [{"name": "bug"}]}) == "bug"

    try:
        issue_classification(
            {"labels": [{"name": "bug"}], "type": {"name": "Bug"}}
        )
    except MetadataError as error:
        assert "redundant" in str(error)
    else:
        raise AssertionError("native Issue Type and work-kind label overlapped")


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
                "labels": [],
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
                "labels": [],
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


def test_sync_rejects_multiple_linked_issues() -> None:
    def fake_run(arguments: list[str], _stdin: str | None) -> dict[str, Any]:
        assert arguments[-1].endswith("/pulls/44")
        return {
            "head": {"ref": "fix/42-timeout"},
            "body": "Fixes #42\n\nResolves #99",
        }

    try:
        sync_pull_request("owner/repo", 44, fake_run)
    except MetadataError as error:
        assert "multiple work Issues" in str(error)
    else:
        raise AssertionError("conflicting Issue relationships should fail")


def test_issue_milestone_change_resynchronizes_matching_open_prs() -> None:
    patches: list[int] = []

    def fake_run(
        arguments: list[str], stdin: str | None
    ) -> dict[str, Any] | list[Any]:
        endpoint = arguments[-1]
        if endpoint.endswith("pulls?state=open&per_page=100"):
            return [
                [
                    {
                        "number": 44,
                        "head": {"ref": "fix/42-timeout"},
                        "body": "Fixes #42",
                    },
                    {
                        "number": 45,
                        "head": {"ref": "fix/41-other"},
                        "body": "Fixes #41",
                    },
                ]
            ]
        if endpoint.endswith("/pulls/44"):
            return {
                "head": {"ref": "fix/42-timeout"},
                "body": "Fixes #42",
            }
        if endpoint.endswith("/issues/42"):
            return {
                "labels": [],
                "type": {"name": "Bug"},
                "milestone": {"number": 7},
            }
        if arguments[:3] == ["api", "--method", "PATCH"]:
            patches.append(int(arguments[-3].rsplit("/", 1)[1]))
            return {}
        if endpoint.endswith("/issues/44"):
            return {
                "user": {"login": "author", "type": "User"},
                "assignees": [],
                "labels": [],
                "milestone": None,
            }
        raise AssertionError(arguments)

    result = sync_issue_pull_requests("owner/repo", 42, fake_run)

    assert result == "Issue #42: synchronized 1 open pull request(s)"
    assert patches == [44]


def test_issue_dispatch_uses_the_issue_resynchronizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    def fake_sync(repo: str, issue: int) -> str:
        calls.append((repo, issue))
        return "done"

    monkeypatch.setattr(MODULE, "sync_issue_pull_requests", fake_sync)
    monkeypatch.setattr(
        MODULE.sys,
        "argv",
        ["sync_work_item_metadata.py", "--repo", "owner/repo", "--issue", "42"],
    )

    assert MODULE.main() == 0
    assert calls == [("owner/repo", 42)]


def test_missing_milestone_reminder_is_posted_once() -> None:
    calls: list[tuple[list[str], str | None]] = []
    reminder_bodies: list[str] = []

    def fake_run(
        arguments: list[str], stdin: str | None
    ) -> dict[str, Any] | list[Any]:
        calls.append((arguments, stdin))
        joined = " ".join(arguments)
        if "POST" in arguments:
            reminder_bodies.extend(
                value.removeprefix("body=")
                for value in arguments
                if value.startswith("body=")
            )
            return {}
        if joined == "api repos/owner/repo/pulls/44":
            return {"head": {"ref": "fix/42-timeout"}, "body": "Fixes #42"}
        if joined == "api repos/owner/repo/issues/42":
            return {"milestone": None}
        if joined == "api repos/owner/repo/issues/44":
            return {"milestone": None}
        if "repos/owner/repo/issues/44/comments" in arguments:
            return [[{"body": body} for body in reminder_bodies]]
        raise AssertionError(arguments)

    def fake_detect(_repo: str) -> tuple[int, str]:
        return (7, "Delivery")

    result = remind_missing_milestone("owner/repo", 44, fake_run, fake_detect)
    repeated = remind_missing_milestone("owner/repo", 44, fake_run, fake_detect)

    assert "posted" in result
    assert "already present" in repeated
    post = next(arguments for arguments, _ in calls if "POST" in arguments)
    body = next(value for value in post if value.startswith("body="))
    assert "<!-- csarc-milestone-safeguard:551 -->" in body
    assert "#7 Delivery" in body
    assert len(reminder_bodies) == 1
