"""Regression tests for scripts/check_bypass_trace.py (Issue #607).

Exercises `parse_trace` and `find_bypass_trace` directly against fixture
comment data -- no `gh` CLI, no network -- proving the usage-trace
requirement from Issue #607 acceptance criterion 4 is actually checkable,
not just documented.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_bypass_trace as cbt  # noqa: E402


def _comment(body: str, created_at: str, login: str = "matheme-justyn") -> dict:
    return {"body": body, "createdAt": created_at, "author": {"login": login}}


def test_parse_trace_extracts_a_well_formed_line() -> None:
    body = (
        "Merging via the alpha self-approval bypass (#580).\n"
        "bypass-trace: release_phase=alpha actor=matheme-justyn "
        "reason=only collaborator, content independently verified\n"
    )

    parsed = cbt.parse_trace(body)

    assert parsed == {
        "release_phase": "alpha",
        "actor": "matheme-justyn",
        "reason": "only collaborator, content independently verified",
    }


def test_parse_trace_returns_none_for_an_unrelated_comment() -> None:
    assert cbt.parse_trace("LGTM, thanks!") is None


def test_parse_trace_rejects_an_invalid_release_phase() -> None:
    # "release" must never appear here -- the bypass does not exist in
    # that phase (Issue #607 acceptance criterion 3), so a trace claiming
    # it is malformed, not merely unusual.
    body = "bypass-trace: release_phase=release actor=x reason=y"

    assert cbt.parse_trace(body) is None


def test_find_bypass_trace_locates_a_qualifying_comment() -> None:
    comments = [
        _comment("just a normal review comment", "2026-09-01T10:00:00Z"),
        _comment(
            "bypass-trace: release_phase=beta actor=matheme-justyn "
            "reason=structural single-account gap, verified locally",
            "2026-09-01T11:00:00Z",
        ),
    ]

    trace = cbt.find_bypass_trace(comments, merged_at="2026-09-01T12:00:00Z")

    assert trace is not None
    assert trace["release_phase"] == "beta"
    assert trace["actor"] == "matheme-justyn"
    assert trace["commenter"] == "matheme-justyn"


def test_find_bypass_trace_ignores_a_trace_left_after_the_merge() -> None:
    """A trace backfilled after merging does not satisfy the requirement:
    it must predate the bypass merge it documents."""
    comments = [
        _comment(
            "bypass-trace: release_phase=alpha actor=matheme-justyn "
            "reason=backfilled after the fact",
            "2026-09-01T13:00:00Z",
        ),
    ]

    trace = cbt.find_bypass_trace(comments, merged_at="2026-09-01T12:00:00Z")

    assert trace is None


def test_find_bypass_trace_returns_none_when_absent() -> None:
    comments = [_comment("approved", "2026-09-01T10:00:00Z")]

    assert (
        cbt.find_bypass_trace(comments, merged_at="2026-09-01T12:00:00Z")
        is None
    )


def test_find_bypass_trace_accepts_any_trace_when_not_yet_merged() -> None:
    comments = [
        _comment(
            "bypass-trace: release_phase=alpha actor=x reason=early note",
            "2026-09-01T09:00:00Z",
        ),
    ]

    trace = cbt.find_bypass_trace(comments, merged_at=None)

    assert trace is not None
    assert trace["release_phase"] == "alpha"


def test_find_bypass_trace_picks_the_latest_qualifying_trace() -> None:
    comments = [
        _comment(
            "bypass-trace: release_phase=alpha actor=x reason=first",
            "2026-09-01T09:00:00Z",
        ),
        _comment(
            "bypass-trace: release_phase=alpha actor=x reason=second",
            "2026-09-01T10:00:00Z",
        ),
    ]

    trace = cbt.find_bypass_trace(comments, merged_at="2026-09-01T12:00:00Z")

    assert trace is not None
    assert trace["reason"] == "second"
