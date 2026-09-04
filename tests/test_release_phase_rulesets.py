"""Regression tests for scripts/release_phase_rulesets.py (Issue #607).

These exercise the pure `assemble_rulesets` and `check_release_phase_bypass`
functions directly (no `gh` CLI, no network) plus the module's CLI, proving
the core acceptance criteria from Issue #607:

* alpha:   both the review rule and required_status_checks are
           bypass-exempt for the repository-admin role.
* beta:    only the review rule stays bypass-exempt; required_status_checks
           moves to its own Ruleset with an always-empty bypass_actors.
* release: a non-empty bypass_actors anywhere in the checked-in Ruleset
           payloads fails closed.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "release_phase_rulesets.py"

sys.path.insert(0, str(ROOT / "scripts"))
import release_phase_rulesets as rpr  # noqa: E402

ADMIN_BYPASS = [
    {
        "actor_type": "RepositoryRole",
        "actor_id": 5,
        "bypass_mode": "pull_request",
    }
]

REVIEW_RULESET = {
    "name": "CSARC protected branches",
    "target": "branch",
    "enforcement": "active",
    "bypass_actors": ADMIN_BYPASS,
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [
        {"type": "non_fast_forward"},
        {
            "type": "pull_request",
            "parameters": {
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": True,
                "require_last_push_approval": True,
                "required_approving_review_count": 1,
                "required_review_thread_resolution": True,
            },
        },
    ],
}

REQUIRED_CHECKS_RULESET = {
    "name": "CSARC required checks",
    "target": "branch",
    "enforcement": "active",
    "bypass_actors": [],
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": False,
                "required_status_checks": [
                    {"context": "title"},
                    {"context": "promotion"},
                    {"context": "verify"},
                ],
            },
        }
    ],
}


def _rule_types(ruleset: dict) -> set[str]:
    return {rule["type"] for rule in ruleset["rules"]}


def test_alpha_folds_required_checks_into_the_bypassable_ruleset() -> None:
    """Alpha: both required_status_checks and review are bypass-exempt."""
    review, required_checks = rpr.assemble_rulesets(
        "alpha", REVIEW_RULESET, REQUIRED_CHECKS_RULESET
    )

    assert _rule_types(review) == {
        "non_fast_forward",
        "pull_request",
        "required_status_checks",
    }
    assert review["bypass_actors"] == ADMIN_BYPASS
    # required_status_checks now lives in the bypassable Ruleset, so the
    # standalone required-checks Ruleset carries no rules of its own.
    assert required_checks["rules"] == []


def test_beta_keeps_required_checks_in_its_own_never_bypassed_ruleset() -> None:
    """Beta: only the review rule stays bypass-exempt."""
    review, required_checks = rpr.assemble_rulesets(
        "beta", REVIEW_RULESET, REQUIRED_CHECKS_RULESET
    )

    assert _rule_types(review) == {"non_fast_forward", "pull_request"}
    assert review["bypass_actors"] == ADMIN_BYPASS

    assert _rule_types(required_checks) == {"required_status_checks"}
    assert required_checks["bypass_actors"] == []


def test_release_keeps_the_same_split_as_beta() -> None:
    """Release uses the identical two-Ruleset split as beta.

    Whether the review Ruleset's own bypass_actors is empty at "release"
    is a property of the checked-in files, enforced by
    check_release_phase_bypass/scripts/check-bypass-lifecycle -- not
    something assemble_rulesets rewrites on the fly.
    """
    review, required_checks = rpr.assemble_rulesets(
        "release", REVIEW_RULESET, REQUIRED_CHECKS_RULESET
    )

    assert _rule_types(review) == {"non_fast_forward", "pull_request"}
    assert _rule_types(required_checks) == {"required_status_checks"}
    assert required_checks["bypass_actors"] == []


def test_assemble_rulesets_does_not_mutate_its_inputs() -> None:
    review_before = copy.deepcopy(REVIEW_RULESET)
    required_checks_before = copy.deepcopy(REQUIRED_CHECKS_RULESET)

    rpr.assemble_rulesets("alpha", REVIEW_RULESET, REQUIRED_CHECKS_RULESET)

    assert review_before == REVIEW_RULESET
    assert required_checks_before == REQUIRED_CHECKS_RULESET


def test_assemble_rulesets_rejects_an_unknown_phase() -> None:
    with pytest.raises(ValueError, match="unknown release_phase"):
        rpr.assemble_rulesets("stable", REVIEW_RULESET, REQUIRED_CHECKS_RULESET)


@pytest.mark.parametrize("phase", ["alpha", "beta"])
def test_check_release_phase_bypass_passes_before_release(phase: str) -> None:
    """A non-empty bypass_actors is legitimate at alpha and beta."""
    offenders = rpr.check_release_phase_bypass(
        phase, [REVIEW_RULESET, REQUIRED_CHECKS_RULESET]
    )

    assert offenders == []


def test_check_release_phase_bypass_fails_closed_at_release() -> None:
    """Issue #607 acceptance criterion 3: release_phase "release" plus a
    non-empty bypass_actors anywhere must be rejected."""
    offenders = rpr.check_release_phase_bypass(
        "release", [REVIEW_RULESET, REQUIRED_CHECKS_RULESET]
    )

    assert offenders == ["CSARC protected branches"]


def test_check_release_phase_bypass_passes_at_release_once_cleared() -> None:
    """The fail-closed check passes once bypass_actors is actually empty."""
    cleared_review = {**REVIEW_RULESET, "bypass_actors": []}

    offenders = rpr.check_release_phase_bypass(
        "release", [cleared_review, REQUIRED_CHECKS_RULESET]
    )

    assert offenders == []


def test_load_release_phase_rejects_an_invalid_value(tmp_path: Path) -> None:
    project_stage = tmp_path / "project-stage.json"
    project_stage.write_text(
        json.dumps({"release_phase": "ga"}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="release_phase must be one of"):
        rpr.load_release_phase(project_stage)


def _write_fixtures(
    tmp_path: Path, release_phase: str, review: dict, required_checks: dict
) -> tuple[Path, Path, Path]:
    project_stage = tmp_path / "project-stage.json"
    project_stage.write_text(
        json.dumps({"release_phase": release_phase}), encoding="utf-8"
    )
    review_path = tmp_path / "rulesets.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    required_checks_path = tmp_path / "rulesets-required-checks.json"
    required_checks_path.write_text(
        json.dumps(required_checks), encoding="utf-8"
    )
    return project_stage, review_path, required_checks_path


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, str(MODULE), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def test_cli_assemble_prints_the_effective_rulesets(tmp_path: Path) -> None:
    project_stage, review_path, required_checks_path = _write_fixtures(
        tmp_path, "alpha", REVIEW_RULESET, REQUIRED_CHECKS_RULESET
    )

    result = _run_cli(
        "assemble",
        "--project-stage",
        str(project_stage),
        "--review-ruleset",
        str(review_path),
        "--required-checks-ruleset",
        str(required_checks_path),
    )

    assert result.returncode == 0, result.stdout
    rulesets = json.loads(result.stdout)
    assert len(rulesets) == 2
    assert _rule_types(rulesets[0]) == {
        "non_fast_forward",
        "pull_request",
        "required_status_checks",
    }


def test_cli_check_exits_nonzero_when_release_phase_release_still_has_bypass(
    tmp_path: Path,
) -> None:
    """Issue #607 acceptance criterion 3, exercised through the actual CLI
    entry point `scripts/check-bypass-lifecycle` runs."""
    project_stage, review_path, required_checks_path = _write_fixtures(
        tmp_path, "release", REVIEW_RULESET, REQUIRED_CHECKS_RULESET
    )

    result = _run_cli(
        "check",
        "--project-stage",
        str(project_stage),
        "--review-ruleset",
        str(review_path),
        "--required-checks-ruleset",
        str(required_checks_path),
    )

    assert result.returncode == 1
    assert "CSARC protected branches" in result.stdout
    assert "Issue #607" in result.stdout


def test_cli_check_passes_when_release_phase_release_has_no_bypass(
    tmp_path: Path,
) -> None:
    cleared_review = {**REVIEW_RULESET, "bypass_actors": []}
    project_stage, review_path, required_checks_path = _write_fixtures(
        tmp_path, "release", cleared_review, REQUIRED_CHECKS_RULESET
    )

    result = _run_cli(
        "check",
        "--project-stage",
        str(project_stage),
        "--review-ruleset",
        str(review_path),
        "--required-checks-ruleset",
        str(required_checks_path),
    )

    assert result.returncode == 0, result.stdout


def test_cli_check_passes_at_alpha_despite_bypass_actors(
    tmp_path: Path,
) -> None:
    project_stage, review_path, required_checks_path = _write_fixtures(
        tmp_path, "alpha", REVIEW_RULESET, REQUIRED_CHECKS_RULESET
    )

    result = _run_cli(
        "check",
        "--project-stage",
        str(project_stage),
        "--review-ruleset",
        str(review_path),
        "--required-checks-ruleset",
        str(required_checks_path),
    )

    assert result.returncode == 0, result.stdout


def test_repo_checked_in_fixtures_are_consistent_with_the_module() -> None:
    """The actual checked-in policy files load and assemble cleanly, and
    scripts/check-bypass-lifecycle currently passes (release_phase is
    "alpha" today, see policies/project-stage.json)."""
    project_stage = ROOT / "policies" / "project-stage.json"
    review_path = ROOT / "policies" / "rulesets.json"
    required_checks_path = ROOT / "policies" / "rulesets-required-checks.json"

    release_phase = rpr.load_release_phase(project_stage)
    assert release_phase == "alpha"

    review = json.loads(review_path.read_text(encoding="utf-8"))
    required_checks = json.loads(
        required_checks_path.read_text(encoding="utf-8")
    )
    assert required_checks["bypass_actors"] == []

    offenders = rpr.check_release_phase_bypass(
        release_phase, [review, required_checks]
    )
    assert offenders == []
