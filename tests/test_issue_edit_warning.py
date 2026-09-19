"""Regression tests for the approval-invalidating edit warning (#799)."""

from __future__ import annotations

import io
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts" / "sync_milestone_state.py"))
WRAPPER = runpy.run_path(str(ROOT / "scripts" / "gh-issue-edit"))
approval_invalidations_for_body_edit = MODULE[
    "approval_invalidations_for_body_edit"
]
body_edit_warning = MODULE["body_edit_warning"]
edit_context = WRAPPER["_edit_context"]
edit_main = WRAPPER["main"]


def _comment(
    author: str, body: str, created_at: str, number: int = 1
) -> dict[str, Any]:
    return {
        "body": body,
        "html_url": (
            f"https://github.com/acme/project/issues/42#issuecomment-{number}"
        ),
        "user": {"login": author, "type": "User"},
        "created_at": created_at,
        "updated_at": created_at,
    }


def _snapshot(
    *comments: dict[str, Any],
    updated_at: str = "2026-01-01T00:00:00Z",
    standalone: bool = False,
    body: str = "## Proposal\n\nShip it.\n",
) -> dict[str, Any]:
    milestone = None if standalone else {"number": 14, "title": "Delivery"}
    title = "Standalone fix" if standalone else "Milestone 14: Delivery"
    return {
        "repo": "acme/project",
        "issue": {
            "number": 42,
            "title": title,
            "body": body,
            "updated_at": updated_at,
            "milestone": milestone,
            "user": {"login": "proposer", "type": "User"},
        },
        "comments": list(comments),
    }


def test_body_edit_warns_for_the_exact_tracker_approval_it_invalidates() -> (
    None
):
    snapshot = _snapshot(
        _comment("reviewer", "/milestone approve", "2026-01-01T01:00:00Z")
    )

    warning = body_edit_warning(snapshot, "2026-01-01T02:00:01Z")

    assert warning is not None
    assert "@reviewer" in warning
    assert "issuecomment-1" in warning
    assert "`/milestone approve`" in warning


@pytest.mark.parametrize(
    ("snapshot", "proposed_updated_at"),
    [
        (
            _snapshot(
                _comment(
                    "reviewer",
                    "/milestone approve",
                    "2026-01-01T00:00:00Z",
                ),
                updated_at="2026-01-01T01:00:01Z",
            ),
            "2026-01-01T02:00:00Z",
        ),
        (
            _snapshot(
                _comment(
                    "reviewer",
                    "/milestone approve",
                    "2026-01-01T01:00:00Z",
                )
            ),
            "2026-01-01T01:00:30Z",
        ),
    ],
)
def test_body_edit_does_not_warn_when_it_will_not_invalidate_approval(
    snapshot: dict[str, Any], proposed_updated_at: str
) -> None:
    assert body_edit_warning(snapshot, proposed_updated_at) is None


def test_fresh_reapproval_suppresses_warning_for_an_older_approval() -> None:
    snapshot = _snapshot(
        _comment("reviewer", "/milestone approve", "2026-01-01T00:00:00Z"),
        _comment(
            "second-reviewer",
            "/milestone approve",
            "2026-01-01T02:00:00Z",
            number=2,
        ),
    )

    invalidations = approval_invalidations_for_body_edit(
        snapshot, "2026-01-01T02:00:30Z"
    )

    assert invalidations == []


def test_standalone_issue_uses_its_plain_approval_vocabulary() -> None:
    snapshot = _snapshot(
        _comment("reviewer", "Approve", "2026-01-01T01:00:00Z"),
        standalone=True,
    )

    warning = body_edit_warning(snapshot, "2026-01-01T02:00:01Z")

    assert warning is not None
    assert "@reviewer" in warning
    assert "`Approve`" in warning


def test_regular_milestone_issue_has_no_body_bound_approval() -> None:
    snapshot = _snapshot(
        _comment("reviewer", "/milestone approve", "2026-01-01T01:00:00Z")
    )
    snapshot["issue"]["title"] = "One delivery leaf"

    assert body_edit_warning(snapshot, "2026-01-01T02:00:01Z") is None


def test_admin_warning_requires_a_valid_admin_self_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        body_edit_warning.__globals__,
        "_collaborator_permission",
        lambda repo, username: "admin",
    )
    snapshot = _snapshot(
        _comment(
            "proposer",
            "/milestone admin-approve: urgent delivery",
            "2026-01-01T01:00:00Z",
        )
    )

    warning = body_edit_warning(snapshot, "2026-01-01T02:00:01Z")

    assert warning is not None
    assert "@proposer" in warning
    assert "`/milestone admin-approve: <reason>`" in warning


def test_wrapper_only_preflights_body_edits() -> None:
    assert edit_context(["42", "--add-label", "bug"]) == (
        False,
        None,
        ["42"],
    )
    assert edit_context(
        ["42", "43", "--body-file", "body.md", "--repo=acme/project"]
    ) == (True, "acme/project", ["42", "43"])
    assert edit_context(
        ["https://github.com/acme/project/issues/42", "-bupdated"]
    ) == (True, None, ["https://github.com/acme/project/issues/42"])


def test_noninteractive_warning_preserves_original_gh_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setitem(
        edit_main.__globals__,
        "_warning_for_target",
        lambda target, repo: "WARNING: approval by @reviewer becomes stale",
    )
    monkeypatch.setitem(
        edit_main.__globals__["shutil"].__dict__,
        "which",
        lambda executable: "/usr/bin/gh",
    )
    monkeypatch.setitem(
        edit_main.__globals__["subprocess"].__dict__,
        "run",
        lambda arguments, check: (
            calls.append(arguments) or subprocess.CompletedProcess(arguments, 0)
        ),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    arguments = ["42", "--body", "updated", "--repo", "acme/project"]

    assert edit_main(arguments) == 0

    assert calls == [["/usr/bin/gh", "issue", "edit", *arguments]]
    output = capsys.readouterr().err
    assert "@reviewer" in output
    assert "Non-interactive session: continuing" in output


class _InteractiveInput(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_interactive_warning_can_cancel_before_gh_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        edit_main.__globals__,
        "_warning_for_target",
        lambda target, repo: "WARNING: approval becomes stale",
    )
    monkeypatch.setitem(
        edit_main.__globals__["subprocess"].__dict__,
        "run",
        lambda arguments, check: pytest.fail("gh should not run"),
    )
    monkeypatch.setattr(sys, "stdin", _InteractiveInput("n\n"))

    with pytest.raises(SystemExit, match="1"):
        edit_main(["42", "--body", "updated"])


def test_preflight_failure_is_advisory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []

    def fail_preflight(target: str, repo: str | None) -> None:
        raise subprocess.CalledProcessError(1, ["gh", "api"])

    monkeypatch.setitem(
        edit_main.__globals__, "_warning_for_target", fail_preflight
    )
    monkeypatch.setitem(
        edit_main.__globals__["shutil"].__dict__,
        "which",
        lambda executable: "/usr/bin/gh",
    )
    monkeypatch.setitem(
        edit_main.__globals__["subprocess"].__dict__,
        "run",
        lambda arguments, check: (
            calls.append(arguments) or subprocess.CompletedProcess(arguments, 0)
        ),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    assert edit_main(["42", "--body", "updated"]) == 0

    assert calls == [
        ["/usr/bin/gh", "issue", "edit", "42", "--body", "updated"]
    ]
    assert "could not check approval" in capsys.readouterr().err
