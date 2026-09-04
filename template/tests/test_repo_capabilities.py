"""Regression tests for scripts/repo_capabilities.py (Issue #531).

Exercises the pure evaluator (`load_matrix`, `load_facts`, `evaluate`,
`summarize`, `gaps`, `render_report`) directly, and the CLI entry point via
subprocess, against crafted fixture facts representing different
permission/plan combinations -- no `gh` CLI, no network -- proving the
"repo capability gap list" auto-detection is actually checkable per Issue
#531 completion checklist item 5, not just documented.

Several tests load the real, shipped `policies/capability-matrix.json`
directly (not a synthetic fixture) so a structural regression in that data
file -- a missing bilingual field, a duplicate id, or drift between the
matrix and this module's expectations -- is caught here immediately.
"""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
# `ty` only resolves static imports and does not search `scripts/`, so a
# plain `sys.path.insert` + `import repo_capabilities` passes at runtime but
# fails `ty check` on a generated project (Issue #665). `runpy.run_path`
# loads the module by executing it directly, which `ty` never tries to
# statically resolve -- the same convention `test_promotion_gate.py` already
# uses. Wrapped in a `SimpleNamespace` so every existing `rc.xxx` call below
# keeps working unchanged.
rc = SimpleNamespace(
    **runpy.run_path(str(ROOT / "scripts" / "repo_capabilities.py"))
)

REAL_MATRIX_PATH = ROOT / "policies" / "capability-matrix.json"
REAL_CAPABILITY_IDS = (
    "repository_admin",
    "ruleset_enforcement",
    "codeowners_enforcement",
    "actions_pr_approval",
    "security_and_analysis",
    "github_pages",
    "repository_settings_inspection",
    "immutable_releases",
)


def _minimal_matrix(*ids: str) -> list[dict]:
    """Build a tiny synthetic matrix with the given capability ids."""
    bilingual = {"en": "text", "zh-tw": "文字"}
    return [
        {
            "id": capability_id,
            "title": bilingual,
            "behavior": bilingual,
            "requirement": bilingual,
            "detection": bilingual,
            "workaround": bilingual,
            "related_degraded_marker": None,
        }
        for capability_id in ids
    ]


def _facts(**statuses: str) -> dict[str, dict]:
    return {
        capability_id: {
            "status": status,
            "detail": f"detail for {capability_id}",
        }
        for capability_id, status in statuses.items()
    }


def _real_facts(**overrides: str) -> dict[str, dict]:
    """All eight real capability ids defaulting to 'allowed', with overrides."""
    statuses = dict.fromkeys(REAL_CAPABILITY_IDS, "allowed")
    statuses.update(overrides)
    return {
        capability_id: {"status": status, "detail": f"fixture: {capability_id}"}
        for capability_id, status in statuses.items()
    }


# --- load_matrix -----------------------------------------------------------


def test_load_matrix_loads_the_real_shipped_matrix() -> None:
    matrix = rc.load_matrix(REAL_MATRIX_PATH)

    ids = [entry["id"] for entry in matrix]
    assert ids == list(REAL_CAPABILITY_IDS)


def test_load_matrix_rejects_a_missing_bilingual_field(tmp_path: Path) -> None:
    payload = {
        "capabilities": [
            {
                "id": "example",
                "title": {"en": "Example", "zh-tw": "範例"},
                "behavior": {"en": "does something", "zh-tw": "做某事"},
                "requirement": {
                    "en": "",
                    "zh-tw": "需求",
                },  # empty English text
                "detection": {"en": "probe", "zh-tw": "探測"},
                "workaround": {"en": "fix it", "zh-tw": "修正"},
            }
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(rc.CapabilityDataError, match="requirement"):
        rc.load_matrix(matrix_path)


def test_load_matrix_rejects_duplicate_ids(tmp_path: Path) -> None:
    payload = {"capabilities": _minimal_matrix("dup", "dup")}
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(rc.CapabilityDataError, match="duplicate"):
        rc.load_matrix(matrix_path)


# --- load_facts --------------------------------------------------------


def test_load_facts_rejects_an_invalid_status() -> None:
    with pytest.raises(rc.CapabilityDataError, match="must be one of"):
        rc.load_facts(json.dumps({"repository_admin": {"status": "maybe"}}))


def test_load_facts_defaults_detail_to_empty_string() -> None:
    facts = rc.load_facts(
        json.dumps({"repository_admin": {"status": "allowed"}})
    )

    assert facts["repository_admin"] == {"status": "allowed", "detail": ""}


# --- evaluate: structural guarantees ----------------------------------


def test_evaluate_merges_matrix_and_facts_preserving_matrix_order() -> None:
    matrix = _minimal_matrix("second", "first")
    facts = _facts(second="allowed", first="blocked")

    results = rc.evaluate(matrix, facts)

    assert [result["id"] for result in results] == ["second", "first"]
    assert results[1]["status"] == "blocked"


def test_evaluate_raises_when_a_declared_capability_has_no_fact() -> None:
    matrix = _minimal_matrix("alpha", "beta")
    facts = _facts(alpha="allowed")

    with pytest.raises(rc.CapabilityDataError, match="beta"):
        rc.evaluate(matrix, facts)


def test_evaluate_raises_when_facts_reference_an_unknown_capability() -> None:
    matrix = _minimal_matrix("alpha")
    facts = _facts(alpha="allowed", ghost="blocked")

    with pytest.raises(rc.CapabilityDataError, match="ghost"):
        rc.evaluate(matrix, facts)


def test_summarize_counts_every_status_including_zero() -> None:
    matrix = _minimal_matrix("alpha", "beta")
    facts = _facts(alpha="allowed", beta="allowed")

    summary = rc.summarize(rc.evaluate(matrix, facts))

    assert summary == {"allowed": 2, "blocked": 0, "unknown": 0}


def test_gaps_excludes_only_allowed_capabilities() -> None:
    matrix = _minimal_matrix("alpha", "beta", "gamma")
    facts = _facts(alpha="allowed", beta="blocked", gamma="unknown")

    gap_ids = [result["id"] for result in rc.gaps(rc.evaluate(matrix, facts))]

    assert gap_ids == ["beta", "gamma"]


# --- permission-combination scenarios (checklist item 5) ---------------
#
# Each scenario below evaluates the REAL shipped matrix against a distinct,
# named permission/plan combination and asserts the resulting gap list --
# proving different real-world repository configurations produce different,
# correct capability/gap reports.


def test_admin_public_repo_full_org_support_has_no_actionable_gaps() -> None:
    """Best case: repo admin, public repo, org allows Actions PR approval."""
    matrix = rc.load_matrix(REAL_MATRIX_PATH)
    facts = _real_facts(
        actions_pr_approval="allowed",
        immutable_releases="unknown",  # never detectable, see matrix entry
    )

    results = rc.evaluate(matrix, facts)
    gap_ids = {result["id"] for result in rc.gaps(results)}

    assert gap_ids == {"immutable_releases"}


def test_free_plan_private_repo_degrades_plan_gated_capabilities() -> None:
    """Free-plan private repo: admin present, but plan-gated rows degrade."""
    matrix = rc.load_matrix(REAL_MATRIX_PATH)
    facts = _real_facts(
        ruleset_enforcement="blocked",
        security_and_analysis="blocked",
        github_pages="blocked",
        actions_pr_approval="unknown",
        immutable_releases="unknown",
    )

    results = rc.evaluate(matrix, facts)
    gap_ids = {result["id"] for result in rc.gaps(results)}

    assert gap_ids == {
        "ruleset_enforcement",
        "security_and_analysis",
        "github_pages",
        "actions_pr_approval",
        "immutable_releases",
    }
    # repository_admin and codeowners_enforcement stay allowed: plan
    # limitations are independent of whether the acting token has admin.
    by_id = {result["id"]: result for result in results}
    assert by_id["repository_admin"]["status"] == "allowed"
    assert by_id["codeowners_enforcement"]["status"] == "allowed"


def test_non_admin_token_blocks_admin_gated_rows_only() -> None:
    """Read-only token: admin-gated rows blocked, plan-gated rows unaffected."""
    matrix = rc.load_matrix(REAL_MATRIX_PATH)
    facts = _real_facts(
        repository_admin="blocked",
        repository_settings_inspection="blocked",
        codeowners_enforcement="unknown",
        actions_pr_approval="unknown",
        immutable_releases="unknown",
    )

    results = rc.evaluate(matrix, facts)
    gap_ids = {result["id"] for result in rc.gaps(results)}

    assert gap_ids == {
        "repository_admin",
        "repository_settings_inspection",
        "codeowners_enforcement",
        "actions_pr_approval",
        "immutable_releases",
    }
    # ruleset_enforcement, security_and_analysis, and github_pages are all
    # plan/visibility-derived and stay allowed regardless of admin.
    by_id = {result["id"]: result for result in results}
    assert by_id["ruleset_enforcement"]["status"] == "allowed"
    assert by_id["security_and_analysis"]["status"] == "allowed"
    assert by_id["github_pages"]["status"] == "allowed"


def test_missing_codeowners_team_reports_a_targeted_workaround() -> None:
    """A malformed/missing CODEOWNERS team is its own, narrow gap."""
    matrix = rc.load_matrix(REAL_MATRIX_PATH)
    facts = _real_facts(
        codeowners_enforcement="blocked",
        actions_pr_approval="unknown",
        immutable_releases="unknown",
    )

    results = rc.evaluate(matrix, facts)
    by_id = {result["id"]: result for result in results}

    assert by_id["codeowners_enforcement"]["status"] == "blocked"
    assert (
        "request-reviewer"
        in by_id["codeowners_enforcement"]["workaround"]["en"]
    )
    # Every other capability -- including the closely related
    # ruleset_enforcement -- is unaffected by this one narrow gap.
    assert by_id["ruleset_enforcement"]["status"] == "allowed"


# --- render_report -------------------------------------------------------


def test_render_report_omits_requirement_and_workaround_for_allowed_rows() -> (
    None
):
    matrix = _minimal_matrix("alpha", "beta")
    facts = _facts(alpha="allowed", beta="blocked")
    results = rc.evaluate(matrix, facts)

    report = rc.render_report(results, language="en")

    alpha_section, beta_section = report.split("[BLOCKED]")
    assert "requirement:" not in alpha_section
    assert "workaround:" not in alpha_section
    assert "requirement:" in beta_section
    assert "workaround:" in beta_section


def test_render_report_zh_tw_uses_chinese_summary_line() -> None:
    matrix = _minimal_matrix("alpha")
    facts = _facts(alpha="allowed")
    results = rc.evaluate(matrix, facts)

    report = rc.render_report(results, language="zh-tw")

    assert "共 1 項能力" in report


def test_render_report_rejects_an_unsupported_language() -> None:
    matrix = _minimal_matrix("alpha")
    results = rc.evaluate(matrix, _facts(alpha="allowed"))

    with pytest.raises(rc.CapabilityDataError):
        rc.render_report(results, language="fr")


# --- CLI ------------------------------------------------------------


def _run_cli(
    *args: str, input_facts: dict | None = None
) -> subprocess.CompletedProcess[str]:
    facts_arg = list(args)
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(ROOT / "scripts" / "repo_capabilities.py"),
            *facts_arg,
        ],
        input=json.dumps(input_facts) if input_facts is not None else None,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_reads_facts_from_stdin_and_prints_json() -> None:
    result = _run_cli(
        "check", "--facts", "-", "--json", input_facts=_real_facts()
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["allowed"] == len(REAL_CAPABILITY_IDS)
    assert {c["id"] for c in payload["capabilities"]} == set(
        REAL_CAPABILITY_IDS
    )


def test_cli_exits_2_with_a_clear_message_on_malformed_facts(
    tmp_path: Path,
) -> None:
    facts_path = tmp_path / "facts.json"
    facts_path.write_text("not json", encoding="utf-8")

    result = _run_cli("check", "--facts", str(facts_path))

    assert result.returncode == 2
    assert "repo_capabilities" in result.stderr


def test_cli_default_matrix_path_is_the_real_shipped_file(
    tmp_path: Path,
) -> None:
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(_real_facts()), encoding="utf-8")

    result = _run_cli("check", "--facts", str(facts_path))

    assert result.returncode == 0
    assert "out of 8 capabilities" in result.stdout
