"""SPEC-008 lifecycle report contract shared by adopt and update."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

import csarc_cli.cli as cli
from csarc_cli import lifecycle_report
from csarc_cli.lifecycle_report import LifecycleReportError

ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = "2026-10-13T00:00:00+00:00"
PLAN_SHA = "a" * 64
TOKEN = "ghp_" + "A" * 36


def revision(label: str = "v1.0.0", sha: str = "b" * 40) -> cli.Revision:
    return cli.Revision(label, sha, "https://example.invalid/template.git")


def repository() -> cli.RepositoryContext:
    return cli.RepositoryContext(
        "owner/product", "owner", "User", "private", "github", True
    )


def files() -> cli.Plan:
    return cli.Plan(
        add=("new.txt",),
        overwrite=("changed.txt",),
        remove=(),
        preserve=("kept.txt",),
        merge=("AGENTS.md",),
        manual=(),
        unknown=(),
    )


def adoption(**overrides: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "applicable": True,
        "clean": True,
        "code_owner": {
            "reason": "User exists.",
            "state": "verified",
            "value": "@owner",
        },
        "generated_at": GENERATED_AT,
        "mapping_reviewed": True,
        "project_verification_hook": {
            "configured": False,
            "path": None,
            "reason": "No project verification hook configured.",
            "result": "not-run",
            "source": "none",
        },
        "target_changes": [],
        "target_files": {"kept.txt": "digest-not-content"},
        "target_head": "c" * 40,
        "verification": "pending-authorization",
        "work_item_mapping": {},
    }
    evidence.update(overrides)
    return evidence


def answers(tmp_path: Path, **extra: object) -> dict[str, object]:
    return {
        **cli.resolve_release_answers(
            tmp_path, {"language": "ci", "project_mode": "existing"}
        ),
        **extra,
    }


def adopt_report(tmp_path: Path, **overrides: object) -> dict[str, object]:
    plan = cli.ResolvedPlan(
        mode="adopt",
        target=tmp_path / "product",
        revision=revision(),
        repository=repository(),
        answers=answers(tmp_path),
        capabilities={},
        files=files(),
        adoption=adoption(**overrides),
    )
    return cli.lifecycle_report_model(
        plan,
        operation="adopt",
        plan_name=cli.ADOPTION_PLAN_BASENAME,
        plan_sha256=PLAN_SHA,
        generated_at=GENERATED_AT,
        plan_path=tmp_path / "reports" / cli.ADOPTION_PLAN_BASENAME,
    )


def update_report(
    tmp_path: Path,
    *,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
    explicit: tuple[str, ...] = (),
    update_available: bool = True,
    plan_files: cli.Plan | None = None,
) -> dict[str, object]:
    resolved = answers(tmp_path)
    plan = cli.ResolvedPlan(
        mode="update",
        target=tmp_path / "product",
        revision=revision("v1.1.0", "d" * 40),
        repository=repository(),
        answers=resolved if after is None else after,
        capabilities={},
        files=files() if plan_files is None else plan_files,
        update={
            "project_verification_hook": {
                "configured": False,
                "path": None,
                "reason": "Configuration validated.",
                "result": "not-run",
            },
            "update_available": update_available,
        },
    )
    return cli.lifecycle_report_model(
        plan,
        operation="update",
        plan_name=cli.UPDATE_PLAN_BASENAME,
        plan_sha256=PLAN_SHA,
        generated_at=GENERATED_AT,
        plan_path=tmp_path / "reports" / cli.UPDATE_PLAN_BASENAME,
        before=resolved if before is None else before,
        explicit=explicit,
        previous=revision(),
        target_head="c" * 40,
        target_changes=(),
    )


def headings(markdown: str, level: str) -> list[str]:
    return re.findall(rf"^{level} (.+)$", markdown, flags=re.MULTILINE)


def test_adopt_and_update_share_one_closed_schema(tmp_path: Path) -> None:
    adopt = adopt_report(tmp_path)
    update = update_report(tmp_path)

    assert set(adopt) == set(update) == lifecycle_report.REPORT_KEYS_2_1
    for key in ("plan", "target", "release", "product", "verification"):
        assert set(adopt[key]) == set(update[key])  # type: ignore[arg-type]
    assert adopt["report_format_version"] == update["report_format_version"]
    assert adopt["report_format_version"] == "2.1.0"
    assert update["setup"] is None
    assert adopt["operation"] == "adopt"
    assert update["operation"] == "update"
    assert update["final_plan"] is None
    assert update["plan"]["replayable"] is False  # type: ignore[index]
    assert adopt["plan"]["replayable"] is True  # type: ignore[index]


@pytest.mark.parametrize("operation", ["adopt", "update"])
def test_markdown_round_trips_from_report_json_only(
    tmp_path: Path, operation: str
) -> None:
    report = (
        adopt_report(tmp_path)
        if operation == "adopt"
        else update_report(tmp_path)
    )
    text = lifecycle_report.report_json(report)
    markdown = lifecycle_report.render_markdown(json.loads(text))

    assert json.loads(text) == report
    assert markdown == lifecycle_report.render_markdown(report)
    assert headings(markdown, "##") == list(lifecycle_report.SECTION_HEADINGS)
    title = "adoption" if operation == "adopt" else "update"
    assert markdown.startswith(f"# CSARC {title} report\n")
    assert "Report format version: `2.1.0`" in markdown
    summary_rows = re.findall(r"^\| `([a-z]+)` \| (\d+) \|$", markdown, re.M)
    assert [name for name, _count in summary_rows] == list(
        lifecycle_report.FILE_ACTIONS
    )
    counts = report["summary"]["files"]  # type: ignore[index]
    assert {name: int(count) for name, count in summary_rows} == counts


def test_report_output_is_deterministic(tmp_path: Path) -> None:
    first = adopt_report(tmp_path)
    second = adopt_report(tmp_path)

    assert lifecycle_report.report_json(first) == (
        lifecycle_report.report_json(second)
    )
    assert lifecycle_report.render_markdown(first) == (
        lifecycle_report.render_markdown(second)
    )
    assert [row["path"] for row in first["files"]] == [  # type: ignore[union-attr]
        "new.txt",
        "AGENTS.md",
        "changed.txt",
        "kept.txt",
    ]


def test_report_excludes_file_snapshots_and_secret_values(
    tmp_path: Path,
) -> None:
    plan = cli.ResolvedPlan(
        mode="adopt",
        target=tmp_path / "product",
        revision=cli.Revision(
            "v1.0.0",
            "b" * 40,
            f"https://x-access-token:{TOKEN}@github.com/owner/template.git",
        ),
        repository=repository(),
        answers=answers(
            tmp_path,
            api_token=TOKEN,
            project_description=f"Uses {TOKEN} for {'AKIA' + 'B' * 16}",
        ),
        capabilities={},
        files=files(),
        adoption=adoption(),
    )
    report = cli.lifecycle_report_model(
        plan,
        operation="adopt",
        plan_name=cli.ADOPTION_PLAN_BASENAME,
        plan_sha256=PLAN_SHA,
        generated_at=GENERATED_AT,
    )
    text = lifecycle_report.report_json(report)
    markdown = lifecycle_report.render_markdown(report)

    for output in (text, markdown):
        assert TOKEN not in output
        assert "AKIA" not in output
        assert "x-access-token" not in output
        assert "api_token" not in output
        assert "digest-not-content" not in output
    assert "https://[redacted]@github.com/owner/template.git" in text
    rows = {row["key"]: row for row in report["settings"]}  # type: ignore[union-attr]
    assert rows["project_description"]["after"] == (
        "Uses [redacted] for [redacted]"
    )


def test_unredacted_secret_fails_closed(tmp_path: Path) -> None:
    report = adopt_report(tmp_path)
    report["status_reason"] = f"leaked {TOKEN}"

    with pytest.raises(LifecycleReportError, match="unredacted credential"):
        lifecycle_report.report_json(report)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("status",), "approved", "unknown value"),
        (("files", 0, "action"), "rewrite", "unknown value"),
        (("files", 0, "reason"), "lockfile-v2", "unknown value"),
        (("settings", 0, "class"), "broadened", "unknown value"),
        (("settings", 0, "source"), "guessed", "unknown value"),
        (("target", "working_tree"), "dirty", "unknown value"),
        (("report_format_version",), "2.2.0", "unsupported version"),
        (("report_format_version",), "1.1.0", "unsupported version"),
        (("operation",), "init", "unknown value"),
    ],
)
def test_unknown_vocabulary_fails_closed(
    tmp_path: Path, path: tuple[object, ...], value: str, message: str
) -> None:
    report: dict[str, object] = copy.deepcopy(adopt_report(tmp_path))
    container: object = report
    for part in path[:-1]:
        container = container[part]  # type: ignore[index]
    container[path[-1]] = value  # type: ignore[index]

    with pytest.raises(LifecycleReportError, match=message):
        lifecycle_report.render_markdown(report)


def test_missing_or_extra_keys_and_count_drift_fail_closed(
    tmp_path: Path,
) -> None:
    missing = adopt_report(tmp_path)
    del missing["next_steps"]
    extra = adopt_report(tmp_path)
    extra["unexpected"] = True
    drift = adopt_report(tmp_path)
    drift["files"] = drift["files"][1:]  # type: ignore[index]

    with pytest.raises(LifecycleReportError, match="missing keys"):
        lifecycle_report.validate_report(missing)
    with pytest.raises(LifecycleReportError, match="unknown keys"):
        lifecycle_report.validate_report(extra)
    with pytest.raises(LifecycleReportError, match="counts do not match"):
        lifecycle_report.validate_report(drift)


def with_setting_decision(report: dict[str, object]) -> dict[str, object]:
    report["required_actions"] = [
        {
            "blocking": False,
            "command": None,
            "kind": "setting-decision",
            "message": "Choose a value.",
            "subject": "admin_bypass",
        }
    ]
    report["status"] = "review-required"
    report["summary"] = lifecycle_report.summary_counts(
        report["settings"],  # type: ignore[arg-type]
        report["files"],  # type: ignore[arg-type]
        report["required_actions"],  # type: ignore[arg-type]
    )
    return report


def as_2_0_0(report: dict[str, object]) -> dict[str, object]:
    """Return the report as a 2.0.0 writer produced it (no setup field)."""
    previous = dict(report)
    previous.pop("setup")
    previous["report_format_version"] = "2.0.0"
    return previous


def test_2_1_0_opens_setting_decision_to_adopt(tmp_path: Path) -> None:
    """AC6: 2.1.0 adds only the adopt setting-decision and setup record."""
    report = with_setting_decision(adopt_report(tmp_path))

    assert lifecycle_report.validate_report(report) is report
    assert {
        "setup"
    } == lifecycle_report.REPORT_KEYS_2_1 - lifecycle_report.REPORT_KEYS_2_0


def test_2_0_0_reports_stay_readable_by_their_own_rules(tmp_path: Path) -> None:
    """AC6: a 2.0.0 report validates as 2.0.0; nothing else is widened."""
    for report in (adopt_report(tmp_path), update_report(tmp_path)):
        previous = as_2_0_0(report)
        assert lifecycle_report.validate_report(previous) is previous
        markdown = lifecycle_report.render_markdown(previous)
        assert "Report format version: `2.0.0`" in markdown
        assert "### Warnings" not in markdown
    old_adopt = as_2_0_0(with_setting_decision(adopt_report(tmp_path)))
    with pytest.raises(LifecycleReportError, match="unknown value"):
        lifecycle_report.validate_report(old_adopt)
    mixed = as_2_0_0(adopt_report(tmp_path))
    mixed["setup"] = None
    with pytest.raises(LifecycleReportError, match="unknown keys"):
        lifecycle_report.validate_report(mixed)
    missing = adopt_report(tmp_path)
    del missing["setup"]
    with pytest.raises(LifecycleReportError, match="missing keys"):
        lifecycle_report.validate_report(missing)


SETUP = {
    "approval_route": {
        "confirmation": "second-approver",
        "reason": "the collaborator read is incomplete: HTTP 403",
        "state": "inconclusive",
    },
    "questions": ["detected", "governance_mode", "work_mode"],
    "warnings": [
        {
            "code": "W03-second-approver-confirmed",
            "command": "csarc update --data admin_bypass=always",
            "message": "You confirmed another maintainer can approve.",
            "subject": "admin_bypass",
        }
    ],
    "work_mode": "team",
}


def test_setup_record_renders_and_fails_closed(tmp_path: Path) -> None:
    report = adopt_report(tmp_path)
    report["setup"] = copy.deepcopy(SETUP)
    markdown = lifecycle_report.render_markdown(report)

    assert headings(markdown, "##") == list(lifecycle_report.SECTION_HEADINGS)
    assert "### Warnings" in markdown
    assert "W03-second-approver-confirmed" in markdown
    assert "setup questions asked: 3" in markdown
    assert "(confirmed `second-approver`)" in markdown
    for path, value, message in (
        (("work_mode",), "solo", "unknown value"),
        (("approval_route", "state"), "eligible", "unknown value"),
        (("approval_route", "confirmation"), "yes", "unknown value"),
        (("warnings", 0, "code"), "W3", "unknown value"),
        (("questions",), "work_mode", "must be a list"),
    ):
        broken: dict[str, object] = copy.deepcopy(SETUP)
        container: object = broken
        for part in path[:-1]:
            container = container[part]  # type: ignore[index]
        container[path[-1]] = value  # type: ignore[index]
        report["setup"] = broken
        with pytest.raises(LifecycleReportError, match=message):
            lifecycle_report.validate_report(report)
    update = update_report(tmp_path)
    update["setup"] = copy.deepcopy(SETUP)
    with pytest.raises(LifecycleReportError, match="only adopt"):
        lifecycle_report.validate_report(update)


@pytest.mark.parametrize(
    ("overrides", "status", "applicable", "kinds"),
    [
        ({}, "ready", True, []),
        (
            {"mapping_reviewed": False, "applicable": False},
            "review-required",
            False,
            ["mapping-review"],
        ),
        (
            {
                "applicable": False,
                "code_owner": {
                    "reason": "Team is missing.",
                    "state": "blocked",
                    "value": "@owner/team",
                },
            },
            "blocked",
            False,
            ["code-owner"],
        ),
        (
            {"applicable": False, "verification": "failed: verify exited 1"},
            "blocked",
            False,
            ["verification"],
        ),
        (
            {
                "applicable": False,
                "clean": False,
                "verification": "not-run-dirty",
            },
            "blocked",
            False,
            ["working-tree"],
        ),
        (
            {
                "applicable": False,
                "mapping_reviewed": False,
                "verification": "failed: boom",
            },
            "blocked",
            False,
            ["mapping-review", "verification"],
        ),
    ],
)
def test_adoption_conclusions_map_to_lifecycle_status(
    tmp_path: Path,
    overrides: dict[str, object],
    status: str,
    applicable: bool,
    kinds: list[str],
) -> None:
    report = adopt_report(tmp_path, **overrides)

    assert report["status"] == status
    assert report["applicable"] is applicable
    assert [
        action["kind"]
        for action in report["required_actions"]  # type: ignore[union-attr]
    ] == kinds


def test_manual_merges_need_review_but_stay_applicable(tmp_path: Path) -> None:
    plan = cli.ResolvedPlan(
        mode="adopt",
        target=tmp_path / "product",
        revision=revision(),
        repository=repository(),
        answers=answers(tmp_path),
        capabilities={},
        files=cli.Plan((), (), (), (), (), ("LICENSE",), ("bin",)),
        adoption=adoption(verification="deferred-manual-merge"),
    )
    report = cli.lifecycle_report_model(
        plan,
        operation="adopt",
        plan_name=cli.ADOPTION_PLAN_BASENAME,
        plan_sha256=PLAN_SHA,
        generated_at=GENERATED_AT,
    )
    markdown = lifecycle_report.render_markdown(report)

    assert report["status"] == "review-required"
    assert report["applicable"] is True
    assert "> **Status: Review required.**" in markdown
    assert (
        "| `LICENSE` | `conflict` | `manual-merge` | `(none)` | `pending` |"
        in (markdown)
    )
    assert "| `bin` | `conflict` | `undetermined` |" in markdown


def test_update_statuses_and_setting_classes(tmp_path: Path) -> None:
    resolved = answers(tmp_path)
    current = update_report(
        tmp_path,
        update_available=False,
        plan_files=cli.Plan((), (), (), ("kept.txt",), (), (), ()),
    )
    before = {**resolved, "admin_bypass": "off", "actions_fallback": "on"}
    after = {
        key: value
        for key, value in {**resolved, "admin_bypass": "always"}.items()
        if key != "actions_fallback"
    }
    after["enable_codeql"] = True
    before.pop("enable_codeql", None)
    changed = update_report(tmp_path, before=before, after=after)
    explicit = update_report(
        tmp_path, before=before, after=after, explicit=("admin_bypass",)
    )

    assert current["status"] == "current"
    assert current["required_actions"] == []
    assert "> **Status: Current.**" in lifecycle_report.render_markdown(current)
    rows = {row["key"]: row for row in changed["settings"]}  # type: ignore[union-attr]
    assert rows["admin_bypass"]["class"] == "decision"
    assert rows["actions_fallback"]["class"] == "retired"
    assert rows["actions_fallback"]["after"] is None
    assert rows["enable_codeql"]["class"] == "new"
    # SPEC-009 retired the single legacy `language` key (Issue #1071).
    assert rows["language"]["class"] == "retired"
    assert rows["language"]["after"] is None
    assert changed["status"] == "review-required"
    assert [
        action["kind"]
        for action in changed["required_actions"]  # type: ignore[union-attr]
    ] == ["setting-decision"]
    assert explicit["status"] == "ready"
    explicit_rows = {
        row["key"]: row
        for row in explicit["settings"]  # type: ignore[union-attr]
    }
    assert explicit_rows["admin_bypass"]["source"] == "explicit"
    markdown = lifecycle_report.render_markdown(changed)
    assert "| `admin_bypass` | `off` | `always` | `decision` |" in markdown
    assert "False" not in markdown
    assert "True" not in markdown


def test_widened_settings_lead_the_impact_analysis(tmp_path: Path) -> None:
    report = update_report(tmp_path)
    rows = report["settings"]  # type: ignore[assignment]
    for row in rows:  # type: ignore[attr-defined]
        if row["key"] == "language":
            row["class"] = "widened"
    report["summary"] = lifecycle_report.summary_counts(
        rows,  # type: ignore[arg-type]
        report["files"],  # type: ignore[arg-type]
        report["required_actions"],  # type: ignore[arg-type]
    )
    markdown = lifecycle_report.render_markdown(report)
    impact = markdown.split("## Impact analysis\n\n", 1)[1]

    assert impact.startswith("- Widened settings: `language`. See Settings.\n")


def test_applied_report_is_bound_to_the_replayed_plan(tmp_path: Path) -> None:
    report = adopt_report(tmp_path)
    applied = cli.applied_lifecycle_report(
        report, PLAN_SHA, "2026-10-13T01:00:00+00:00"
    )
    markdown = lifecycle_report.render_markdown(applied)

    assert applied["status"] == "applied"
    assert applied["applied_at"] == "2026-10-13T01:00:00+00:00"
    assert applied["plan"]["sha256"] == PLAN_SHA  # type: ignore[index]
    assert applied["applicable"] is False
    assert "> **Status: Adopted.**" in markdown
    with pytest.raises(cli.CliError, match="different plan digest"):
        cli.applied_lifecycle_report(report, "e" * 64, GENERATED_AT)
    with pytest.raises(cli.CliError, match="cannot be marked applied"):
        cli.applied_lifecycle_report(applied, PLAN_SHA, GENERATED_AT)
    blocked = adopt_report(
        tmp_path, applicable=False, verification="failed: verify exited 1"
    )
    with pytest.raises(cli.CliError, match="cannot be marked applied"):
        cli.applied_lifecycle_report(blocked, PLAN_SHA, GENERATED_AT)
    update_applied = cli.applied_lifecycle_report(
        update_report(tmp_path), PLAN_SHA, GENERATED_AT
    )
    assert "> **Status: Updated.**" in lifecycle_report.render_markdown(
        update_applied
    )


def test_writer_emits_three_files_outside_target(tmp_path: Path) -> None:
    target = (tmp_path / "product").resolve()
    target.mkdir()
    directory = cli.lifecycle_report_directory(target, None, "update")
    report = update_report(tmp_path)
    payload = {"mode": "update", "plan_sha256": PLAN_SHA}

    paths = cli.write_lifecycle_reports(
        directory,
        operation="update",
        plan_name=cli.UPDATE_PLAN_BASENAME,
        plan_payload=payload,
        report=report,
        emit=False,
    )

    assert directory == tmp_path.resolve() / "product-csarc-update-report"
    assert [path.name for path in paths] == [
        "csarc-update-report.md",
        "csarc-update-report.json",
        "csarc-update-plan.json",
    ]
    markdown_path, json_path, plan_path = paths
    assert json.loads(json_path.read_text(encoding="utf-8")) == report
    assert markdown_path.read_text(encoding="utf-8") == (
        lifecycle_report.render_markdown(
            json.loads(json_path.read_text(encoding="utf-8"))
        )
    )
    assert json.loads(plan_path.read_text(encoding="utf-8")) == payload
    assert list(target.iterdir()) == []
    with pytest.raises(cli.CliError, match="outside the target repo"):
        cli.lifecycle_report_directory(target, target / "reports", "update")


def test_invalid_report_writes_nothing(tmp_path: Path) -> None:
    directory = tmp_path / "reports"
    report = update_report(tmp_path)
    report["status"] = "approved"

    with pytest.raises(cli.CliError, match="Lifecycle report is invalid"):
        cli.write_lifecycle_reports(
            directory,
            operation="update",
            plan_name=cli.UPDATE_PLAN_BASENAME,
            plan_payload={"plan_sha256": PLAN_SHA},
            report=report,
            emit=False,
        )
    assert not directory.exists()


def test_writer_replaces_regular_legacy_report_and_keeps_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = adopt_report(tmp_path)
    regular = tmp_path / "regular"
    regular.mkdir()
    (regular / cli.LEGACY_ADOPTION_REPORT_NAME).write_text(
        "old\n", encoding="utf-8"
    )
    linked = tmp_path / "linked"
    linked.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("keep\n", encoding="utf-8")
    (linked / cli.LEGACY_ADOPTION_REPORT_NAME).symlink_to(outside)

    for directory in (regular, linked):
        cli.write_lifecycle_reports(
            directory,
            operation="adopt",
            plan_name=cli.ADOPTION_PLAN_BASENAME,
            plan_payload={"plan_sha256": PLAN_SHA},
            report=report,
            emit=False,
        )

    assert not (regular / cli.LEGACY_ADOPTION_REPORT_NAME).exists()
    assert (linked / cli.LEGACY_ADOPTION_REPORT_NAME).is_symlink()
    assert outside.read_text(encoding="utf-8") == "keep\n"
    assert "kept non-regular legacy report" in capsys.readouterr().err


def test_spec_documents_the_closed_contract() -> None:
    spec = (ROOT / "docs/specs/SPEC-008-lifecycle-report-format.md").read_text(
        encoding="utf-8"
    )

    assert f"`{lifecycle_report.LIFECYCLE_REPORT_FORMAT_VERSION}`" in spec
    for heading in lifecycle_report.SECTION_HEADINGS:
        assert f"`## {heading}`" in spec
    for value in (
        *lifecycle_report.STATUSES,
        *lifecycle_report.SETTING_CLASSES,
        *lifecycle_report.SETTING_SOURCES,
        *lifecycle_report.FILE_ACTIONS,
        *(
            reason
            for reasons in lifecycle_report.FILE_ACTIONS.values()
            for reason in reasons
        ),
        *lifecycle_report.REQUIRED_ACTION_KINDS,
        *lifecycle_report.WORKING_TREE_STATES,
        *lifecycle_report.CANDIDATE_STATES,
        *lifecycle_report.APPROVAL_ROUTE_STATES,
        *lifecycle_report.APPROVAL_CONFIRMATIONS,
        *lifecycle_report.WORK_MODES,
        *lifecycle_report.READABLE_REPORT_FORMAT_VERSIONS,
    ):
        assert f"`{value}`" in spec, value
