"""Tests for the root/rendered jinja workflow drift check (Issue #739)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

check_jinja_workflow_drift = importlib.import_module(
    "check_jinja_workflow_drift"
)


def test_identical_content_has_no_drift() -> None:
    """Two files with the same relevant content never disagree."""
    text = "name: CI\njobs:\n  verify:\n    steps:\n      - run: echo hi\n"

    assert check_jinja_workflow_drift.find_drift(text, text) == []


def test_comment_and_blank_line_differences_are_ignored() -> None:
    """Comment wording and blank-line placement never change CI behavior."""
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      # root-only explanation\n      - run: echo hi\n"
    )
    rendered = (
        "jobs:\n  verify:\n    steps:\n\n"
        "      # a differently worded, template-only explanation\n"
        "      - run: echo hi\n"
    )

    assert check_jinja_workflow_drift.find_drift(root, rendered) == []


def test_declared_allowed_difference_does_not_false_positive() -> None:
    """An explicitly declared line-level difference is not reported."""
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: ./scripts/verify-template.sh\n"
    )
    rendered = "jobs:\n  verify:\n    steps:\n      - run: ./scripts/verify\n"
    allowed = {
        (
            ("- run: ./scripts/verify-template.sh",),
            ("- run: ./scripts/verify",),
        )
    }

    assert check_jinja_workflow_drift.find_drift(root, rendered, allowed) == []


def test_undeclared_difference_is_reported() -> None:
    """An artificially introduced, undeclared difference fails the check."""
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      - uses: actions/setup-node@abc\n"
        '        with:\n          node-version: "24"\n'
    )
    rendered = (
        "jobs:\n  verify:\n    steps:\n      - uses: actions/setup-node@abc\n"
        '        with:\n          node-version: "24"\n          cache: pnpm\n'
    )

    errors = check_jinja_workflow_drift.find_drift(root, rendered)

    assert len(errors) == 1
    assert "cache: pnpm" in errors[0]


def test_declared_difference_elsewhere_does_not_mask_a_real_one() -> None:
    """An allowlist entry only covers its own exact hunk, not every hunk."""
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: ./scripts/verify-template.sh\n"
        "      - uses: actions/setup-node@abc\n"
        "        with:\n"
        '          node-version: "24"\n'
    )
    rendered = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: ./scripts/verify\n"
        "      - uses: actions/setup-node@abc\n"
        "        with:\n"
        '          node-version: "24"\n'
        "          cache: pnpm\n"
    )
    allowed = {
        (
            ("- run: ./scripts/verify-template.sh",),
            ("- run: ./scripts/verify",),
        )
    }

    errors = check_jinja_workflow_drift.find_drift(root, rendered, allowed)

    assert len(errors) == 1
    assert "cache: pnpm" in errors[0]
    assert "verify-template.sh" not in errors[0]


def test_paired_workflow_files_skips_jinja_without_a_root_counterpart(
    tmp_path: Path,
) -> None:
    """A downstream-only jinja workflow (no root file) is out of scope."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "template" / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n")
    (
        tmp_path / "template" / ".github" / "workflows" / "ci.yml.jinja"
    ).write_text("name: CI\n")
    (
        tmp_path / "template" / ".github" / "workflows" / "codeql.yml.jinja"
    ).write_text("name: CodeQL\n")

    pairs = check_jinja_workflow_drift.paired_workflow_files(tmp_path)

    assert [jinja.name for _root, jinja in pairs] == ["ci.yml.jinja"]


def test_real_repository_workflows_have_no_undeclared_drift() -> None:
    """Sanity check: this repo's own known allowlist entries actually apply.

    This does not render template/ (that is scripts/check_jinja_workflow_drift's
    own `check()`, exercised end to end by ./scripts/verify-fast); it only
    confirms the declared allowlist lines are still present verbatim in the
    real root workflow, so a future rewording does not silently orphan the
    allowlist entry without anyone noticing.
    """
    root_ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    allowed = check_jinja_workflow_drift.ALLOWED_LINE_DIFFERENCES[
        "ci.yml.jinja"
    ]

    for removed, _added in allowed:
        for line in removed:
            assert line in root_ci, (
                f"allowlisted root line {line!r} no longer appears in "
                ".github/workflows/ci.yml -- update or remove the "
                "ALLOWED_LINE_DIFFERENCES entry in "
                "scripts/check_jinja_workflow_drift.py"
            )
