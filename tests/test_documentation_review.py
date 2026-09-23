"""Tests for the exact-head documentation review contract."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
validate_review = runpy.run_path(
    str(ROOT / "scripts" / "documentation_review.py")
)["validate_review"]

HEAD = "a" * 40


def review_body(
    status: str, head: str = HEAD, reason: str = "Checked docs."
) -> str:
    """Return one pull-request documentation review section."""
    return (
        "## Documentation review\n\n"
        f"- Status: `{status}`\n"
        f"- Reviewed head: `{head}`\n"
        f"- Reason: {reason}\n"
    )


@pytest.mark.parametrize("status", ["aligned", "not-applicable"])
def test_passing_review_states_bind_the_exact_head(status: str) -> None:
    """Accept only passing states recorded for the current candidate."""
    assert status in validate_review(review_body(status), HEAD, "content-only")


@pytest.mark.parametrize("status", ["drift", "inconclusive"])
def test_blocking_review_states_fail(status: str) -> None:
    """Block known drift and uncertainty before delivery."""
    with pytest.raises(ValueError, match=status):
        validate_review(review_body(status), HEAD, "template-and-content")


def test_review_rejects_a_stale_head() -> None:
    """A push invalidates the previous documentation assessment."""
    with pytest.raises(ValueError, match="exact 40-character PR head"):
        validate_review(review_body("aligned", "b" * 40), HEAD, "content-only")


def test_not_applicable_requires_a_concrete_reason() -> None:
    """Do not allow a no-impact state without reviewable evidence."""
    with pytest.raises(ValueError, match="concrete reason"):
        validate_review(
            review_body("not-applicable", reason="TODO"),
            HEAD,
            "content-only",
        )


def test_off_mode_needs_no_review_record() -> None:
    """Disabled documentation management creates no review requirement."""
    assert "skipped" in validate_review("", "", "off")
