"""Regression tests for scripts/generate_audit_trail.py (Issue #535).

Every case below is driven by the fixture-shaped GraphQL nodes in
tests/fixtures/audit-trail-sample.json -- never a live `gh` call -- so the
suite proves the query/rendering logic is correct without network access
or GitHub auth, the same pattern tests/test_history_audit.py already uses
for scripts/audit_github_history.py.
"""

import json
import runpy
from pathlib import Path

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "generate_audit_trail.py")
)
governance_stage = MODULE["governance_stage"]
build_records = MODULE["build_records"]
render_pr_audit_table = MODULE["render_pr_audit_table"]
render_rule_change_log = MODULE["render_rule_change_log"]
load_fixture_nodes = MODULE["load_fixture_nodes"]
PullRequestRecord = MODULE["PullRequestRecord"]
main = MODULE["main"]

FIXTURE = Path(__file__).parent / "fixtures" / "audit-trail-sample.json"


def _records() -> list[PullRequestRecord]:
    nodes = load_fixture_nodes(FIXTURE)
    return build_records(nodes, base="main")


def test_build_records_filters_by_target_branch() -> None:
    # PR #604 targets dev/m9-decision-site-adoption, not main, so a table
    # scoped to main must never surface it -- it is a topic PR merged into
    # the milestone integration branch, not into the target this audit
    # trail reports on.
    records = _records()
    numbers = sorted(record.number for record in records)
    assert numbers == [601, 602, 603, 605]


def test_governance_stage_maps_source_branch_pattern() -> None:
    assert governance_stage("feat/590-tighten-label-policy") == "stable"
    assert governance_stage("dev/m9-decision-site-adoption") == "beta"
    assert governance_stage("promote/m9-decision-site-adoption") == "beta"
    assert governance_stage("dev/i535-audit-trail-soak") == "alpha"


def test_developer_and_reviewer_aggregation() -> None:
    records = {record.number: record for record in _records()}

    solo = records[601]
    assert solo.developers == ("alice",)
    assert solo.reviewers == ("bob",)

    unreviewed = records[602]
    assert unreviewed.developers == ("carol",)
    assert unreviewed.reviewers == ()

    multi_author = records[603]
    assert multi_author.developers == ("dana", "frank")
    assert multi_author.reviewers == ("erin",)
    assert multi_author.issue_number is None

    # PR #605 is opened by "zack" but "alice" also has a commit on it, and
    # "alice" sorts before "zack" -- this is the exact ordering that used
    # to make render_rule_change_log's proposed_by pick the wrong person.
    multi_author_reordered = records[605]
    assert multi_author_reordered.author == "zack"
    assert multi_author_reordered.developers == ("alice", "zack")


def test_pr_audit_table_reports_reality_including_gaps() -> None:
    table = render_pr_audit_table(
        _records(), "owner/repo", "2026-09-03T00:00:00Z"
    )

    assert "#601" in table
    assert "alice" in table
    assert "bob" in table
    assert "| stable |" in table
    assert "#590" in table

    assert "| beta |" in table
    # PR #602 has no recorded reviews -- the table must say so plainly
    # rather than inventing an approver docs/history-audit-2026-08.md
    # already proved does not exist for this repository's history.
    assert "carol | (none recorded) | beta" in table

    assert "| alpha |" in table
    assert "dana, frank" in table

    # PR #604 targets the milestone branch, not main, and must not leak in.
    assert "#604" not in table


def test_rule_change_log_only_includes_rule_touching_prs() -> None:
    records = _records()
    log = render_rule_change_log(
        records, ("policies/",), "owner/repo", "2026-09-03T00:00:00Z"
    )

    assert "[#601]" in log
    assert "alice" in log
    assert "bob" in log
    assert "pullrequestreview-1" in log

    # PR #602 (README.md only) and #603 (scripts/*.py only) never touch
    # policies/, so neither belongs in a rule-change log.
    assert "[#602]" not in log
    assert "[#603]" not in log

    # PR #605 (policies/rulesets.json) does belong -- see the dedicated
    # proposed_by-attribution test below for the identity assertion.
    assert "[#605]" in log


def test_rule_change_log_proposed_by_uses_actual_author() -> None:
    # Regression for the PR #564 review finding: proposed_by used to be
    # `record.developers[0]`, i.e. whichever login sorts first among the
    # PR author and every commit author -- not necessarily the person who
    # actually opened the pull request. PR #605 is authored by "zack", but
    # co-committer "alice" sorts first alphabetically, so a correct
    # implementation must still report "zack".
    records = _records()
    record_605 = next(record for record in records if record.number == 605)
    assert record_605.author == "zack"
    assert record_605.developers == ("alice", "zack")

    log = render_rule_change_log(
        records, ("policies/",), "owner/repo", "2026-09-03T00:00:00Z"
    )
    row = next(line for line in log.splitlines() if "[#605]" in line)
    assert "zack" in row
    assert "alice" not in row


def test_rendering_is_deterministic() -> None:
    records = _records()
    first = render_pr_audit_table(records, "owner/repo", "2026-09-03T00:00:00Z")
    second = render_pr_audit_table(
        records, "owner/repo", "2026-09-03T00:00:00Z"
    )
    assert first == second


def test_main_writes_both_markdown_files_from_fixture(tmp_path: Path) -> None:
    out_dir = tmp_path / "audit-trail"
    exit_code = main(
        [
            "--repo",
            "owner/repo",
            "--fixture",
            str(FIXTURE),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert exit_code == 0

    pr_audit = (out_dir / "pr-audit.md").read_text(encoding="utf-8")
    rule_changes = (out_dir / "rule-changes.md").read_text(encoding="utf-8")

    assert "Auto-generated by `scripts/generate_audit_trail.py`" in pr_audit
    assert "#601" in pr_audit
    assert "#604" not in pr_audit

    assert "Auto-generated by `scripts/generate_audit_trail.py`" in rule_changes
    assert "[#601]" in rule_changes
    assert "[#602]" not in rule_changes


def test_main_rejects_non_positive_retries(tmp_path: Path) -> None:
    with open(tmp_path / "stderr.log", "w", encoding="utf-8"):
        pass
    try:
        main(
            [
                "--repo",
                "owner/repo",
                "--fixture",
                str(FIXTURE),
                "--out-dir",
                str(tmp_path / "out"),
                "--retries",
                "0",
            ]
        )
    except SystemExit as exit_error:
        assert exit_error.code != 0
    else:
        raise AssertionError("expected argparse to reject --retries 0")


def test_load_fixture_nodes_round_trips_expected_shape() -> None:
    nodes = load_fixture_nodes(FIXTURE)
    assert isinstance(nodes, list)
    assert {node["number"] for node in nodes} == {601, 602, 603, 604, 605}
    # Confirm the fixture itself is valid JSON with no trailing garbage,
    # matching the shape load_fixture_nodes expects from a real search
    # response's flattened `data.search.nodes` pages.
    json.loads(FIXTURE.read_text(encoding="utf-8"))
