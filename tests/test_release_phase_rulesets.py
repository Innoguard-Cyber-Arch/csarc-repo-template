"""Regression tests for the fixed review/check Ruleset split."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

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
    "bypass_actors": ADMIN_BYPASS,
    "rules": [{"type": "non_fast_forward"}, {"type": "pull_request"}],
}
REQUIRED_CHECKS_RULESET = {
    "name": "CSARC required checks",
    "bypass_actors": [],
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": False,
                "required_status_checks": [
                    {"context": "title", "integration_id": 15368},
                    {"context": "promotion", "integration_id": 15368},
                    {"context": "verify", "integration_id": 15368},
                ],
            },
        }
    ],
}


def test_assemble_keeps_checks_permanently_separate() -> None:
    review, checks = rpr.assemble_rulesets(
        REVIEW_RULESET, REQUIRED_CHECKS_RULESET
    )

    assert {rule["type"] for rule in review["rules"]} == {
        "non_fast_forward",
        "pull_request",
    }
    assert {rule["type"] for rule in checks["rules"]} == {
        "required_status_checks"
    }
    assert checks["bypass_actors"] == []


def test_assemble_does_not_mutate_inputs() -> None:
    review_before = copy.deepcopy(REVIEW_RULESET)
    checks_before = copy.deepcopy(REQUIRED_CHECKS_RULESET)

    rpr.assemble_rulesets(REVIEW_RULESET, REQUIRED_CHECKS_RULESET)

    assert review_before == REVIEW_RULESET
    assert checks_before == REQUIRED_CHECKS_RULESET


def test_required_checks_bypass_fails_closed() -> None:
    bypassable_checks = {
        **REQUIRED_CHECKS_RULESET,
        "bypass_actors": ADMIN_BYPASS,
    }

    violations = rpr.check_ruleset_bypass([REVIEW_RULESET, bypassable_checks])

    assert violations == [
        "CSARC required checks: required checks must have no bypass"
    ]


def test_unknown_review_bypass_fails_closed() -> None:
    unknown = {
        **REVIEW_RULESET,
        "bypass_actors": [
            {"actor_type": "Team", "actor_id": 9, "bypass_mode": "always"}
        ],
    }

    assert rpr.check_ruleset_bypass([unknown, REQUIRED_CHECKS_RULESET]) == [
        "CSARC protected branches: review bypass is not allowlisted"
    ]


def _write_rulesets(tmp_path: Path, checks: dict) -> tuple[Path, Path]:
    review_path = tmp_path / "rulesets.json"
    review_path.write_text(json.dumps(REVIEW_RULESET), encoding="utf-8")
    checks_path = tmp_path / "rulesets-required-checks.json"
    checks_path.write_text(json.dumps(checks), encoding="utf-8")
    return review_path, checks_path


def _run_cli(
    command: str, review: Path, checks: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(MODULE),
            command,
            "--review-ruleset",
            str(review),
            "--required-checks-ruleset",
            str(checks),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def test_cli_assemble_prints_two_rulesets(tmp_path: Path) -> None:
    review, checks = _write_rulesets(tmp_path, REQUIRED_CHECKS_RULESET)
    result = _run_cli("assemble", review, checks)

    assert result.returncode == 0, result.stdout
    assert len(json.loads(result.stdout)) == 2


def test_cli_check_fails_on_bypassable_required_checks(tmp_path: Path) -> None:
    review, checks = _write_rulesets(
        tmp_path,
        {**REQUIRED_CHECKS_RULESET, "bypass_actors": ADMIN_BYPASS},
    )
    result = _run_cli("check", review, checks)

    assert result.returncode == 1
    assert "required checks must have no bypass" in result.stdout


def test_checked_in_rulesets_have_valid_bypass_boundaries() -> None:
    review, checks = rpr.assemble_rulesets(
        json.loads((ROOT / "policies/rulesets.json").read_text()),
        json.loads(
            (ROOT / "policies/rulesets-required-checks.json").read_text()
        ),
    )

    assert rpr.check_ruleset_bypass([review, checks]) == []
    assert not (ROOT / "policies/project-stage.json").exists()
