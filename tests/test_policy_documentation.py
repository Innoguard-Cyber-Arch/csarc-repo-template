"""Regression tests for deterministic policy-documentation review."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import cast

import pytest

import csarc_cli.cli as cli
from csarc_cli import lifecycle_report, policy_documentation, settings_schema


def setting(value: object) -> list[dict[str, object]]:
    """Return one changed admin-bypass report row."""
    return [
        {
            "after": value,
            "before": "off",
            "class": "widened",
            "key": "admin_bypass",
            "note": None,
            "source": "explicit",
        }
    ]


def test_every_managed_policy_has_scan_keywords() -> None:
    """Keep future persistent policy settings inside the review boundary."""
    assert policy_documentation.POLICY_KEYWORDS.keys() == (
        settings_schema.INTENT_SETTINGS.keys()
    )


def test_contradictory_admin_bypass_runbook_blocks(tmp_path: Path) -> None:
    """Find the reported Chinese runbook contradiction with its location."""
    (tmp_path / "README.md").write_text("# Product\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "deploy.md").write_text(
        "# 部署\n\n部署操作人不得核准自己的變更。\n", encoding="utf-8"
    )

    rows = policy_documentation.review(tmp_path, setting("always"), "zh-tw")

    assert rows == [
        {
            "key": "admin_bypass",
            "locations": ["docs/deploy.md:3"],
            "reason": (
                "At least one candidate line states another policy value."
            ),
            "status": "drift",
            "value": "always",
        }
    ]
    assert policy_documentation.blocking(rows)


def test_consistent_admin_bypass_runbook_does_not_false_positive(
    tmp_path: Path,
) -> None:
    """Accept a runbook that agrees with the configured self-approval route."""
    (tmp_path / "README.md").write_text(
        "admin_bypass: always; the operator can approve their own change.\n",
        encoding="utf-8",
    )

    rows = policy_documentation.review(tmp_path, setting("always"), "en")

    assert rows[0]["status"] == "aligned"
    assert rows[0]["locations"] == ["README.md:1"]
    assert not policy_documentation.blocking(rows)


def test_scan_is_offline_bounded_and_excludes_csarc_docs(
    tmp_path: Path,
) -> None:
    """Scan only project-owned README/docs and record no-match explicitly."""
    (tmp_path / "README.md").write_text("# Product\n", encoding="utf-8")
    managed = tmp_path / ".csarc/docs"
    managed.mkdir(parents=True)
    (managed / "ci-policy.md").write_text(
        "The operator cannot approve their own change.\n", encoding="utf-8"
    )

    rows = policy_documentation.review(tmp_path, setting("always"), "en")

    assert rows[0]["status"] == "not-applicable"
    assert rows[0]["locations"] == []


def test_unreadable_project_document_fails_closed(tmp_path: Path) -> None:
    """Treat undecodable project documentation as inconclusive offline."""
    (tmp_path / "README.md").write_bytes(b"\xff")

    rows = policy_documentation.review(tmp_path, setting("always"), "en")

    assert rows[0]["status"] == "inconclusive"
    assert rows[0]["locations"] == ["README.md:1"]
    assert policy_documentation.blocking(rows)


def test_drift_blocks_the_lifecycle_report_and_apply(tmp_path: Path) -> None:
    """Carry one contradiction into the report's blocking action and gate."""
    target = tmp_path / "product"
    target.mkdir()
    (target / "README.md").write_text(
        "The operator cannot approve their own change.\n", encoding="utf-8"
    )
    after = cli.resolve_release_answers(
        target,
        {
            "admin_bypass": "always",
            "documentation_languages": "en",
            "documentation_mode": "content-only",
            "language": "ci",
            "project_mode": "existing",
        },
    )
    before = {**after, "admin_bypass": "off"}
    assert cli.policy_documentation_blocks(target, after)
    plan = cli.ResolvedPlan(
        mode="update",
        target=target,
        revision=cli.Revision(
            "v1.1.0", "d" * 40, "https://example.invalid/template.git"
        ),
        repository=cli.RepositoryContext(
            "owner/product", "owner", "User", "private", "github", True
        ),
        answers=after,
        capabilities={},
        files=cli.Plan((), (), (), (), (), (), ()),
        update={"update_available": True},
    )

    report = cli.lifecycle_report_model(
        plan,
        operation="update",
        plan_name=cli.UPDATE_PLAN_BASENAME,
        plan_sha256="a" * 64,
        generated_at="2026-10-27T00:00:00+00:00",
        plan_path=tmp_path / "report" / cli.UPDATE_PLAN_BASENAME,
        before=before,
        target_head="c" * 40,
        target_changes=(),
    )

    assert report["status"] == "blocked"
    assert report["applicable"] is False
    assert any(
        row["kind"] == "documentation-review" and row["blocking"] is True
        for row in cast(list[dict[str, object]], report["required_actions"])
    )
    with pytest.raises(cli.CliError, match="target was not changed"):
        cli.reject_policy_documentation(report)

    tampered = copy.deepcopy(report)
    actions = [
        row
        for row in cast(list[dict[str, object]], tampered["required_actions"])
        if row["kind"] != "documentation-review"
    ]
    tampered["required_actions"] = actions
    tampered["summary"] = lifecycle_report.summary_counts(
        cast(list[dict[str, object]], tampered["settings"]),
        cast(list[dict[str, object]], tampered["files"]),
        actions,
    )
    tampered["status"] = "review-required"
    tampered["applicable"] = True
    with pytest.raises(
        lifecycle_report.LifecycleReportError,
        match="must match blocking policy rows",
    ):
        lifecycle_report.validate_report(tampered)
