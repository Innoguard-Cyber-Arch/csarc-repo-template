"""Regression tests for the Ruleset drift-check embedded in
scripts/apply-repository-settings.sh (Issue #570).

The `check` mode compares policies/rulesets.json ("desired") against the
live GitHub effective rules ("effective", the response body of
`gh api repos/{repo}/rules/branches/{branch}`) using a Python block embedded
in the script as a `python3 - <<'PY' ... PY` heredoc. That block used to
assume unconditionally that both the desired *and* the effective rule sets
already contained a `required_status_checks` entry
(`desired_by_type["required_status_checks"]`); when policies/rulesets.json
was missing that rule, the drift-check crashed with an unhandled
`KeyError` instead of reporting a clear policy error.

These tests execute the exact Python source embedded in the shipped script
(extracted verbatim from the heredoc, not a reimplementation) against
crafted `desired`/`effective` fixtures, so a regression in either the
script's guard clauses or its heredoc boundaries is caught here without
having to mock the full `gh` CLI surface that `apply-repository-settings.sh
check` otherwise requires.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply-repository-settings.sh"

HEREDOC_START = (
    'elif ! ruleset_drift="$(python3 - "$ruleset_payload" "$branch_rules" '
    "\"$check_desired_rules_payload_extra\" 2>&1 <<'PY'\n"
)
HEREDOC_END = "\nPY\n"


def _extract_ruleset_drift_source() -> str:
    """Pull the ruleset drift-check Python heredoc out of the shell script.

    Extracting the literal text (rather than duplicating the logic in the
    test) guarantees this test exercises the same code the script ships,
    and fails loudly if the heredoc markers ever move.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index(HEREDOC_START) + len(HEREDOC_START)
    end = source.index(HEREDOC_END, start)
    return source[start:end]


DRIFT_CHECK_SOURCE = _extract_ruleset_drift_source()


def run_drift_check(
    desired: dict[str, object],
    effective: list[dict[str, object]],
    tmp_path: Path,
    extra_desired: dict[str, object] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute the extracted drift-check heredoc against fixture JSON.

    The real invocation in apply-repository-settings.sh captures the
    heredoc with `2>&1`, merging its stdout and stderr into one string
    before deciding what to print. Mirror that here by redirecting stderr
    into stdout, so `result.stdout` reflects exactly what an operator
    would see from `apply-repository-settings.sh check`.

    `extra_desired`, when given, mirrors what the script passes as its
    third positional argument once Issue #607 splits
    policies/rulesets-required-checks.json out of policies/rulesets.json:
    a second "desired" file whose `rules` get unioned into `desired`'s
    before the comparison, because the live effective-rules-branches
    endpoint returns rules from every applicable Ruleset, not scoped by
    name (see check_desired_rules_payload_extra in the shipped script).
    """
    payload_path = tmp_path / "rulesets.json"
    payload_path.write_text(json.dumps(desired), encoding="utf-8")
    extra_arg = ""
    if extra_desired is not None:
        extra_payload_path = tmp_path / "rulesets-required-checks.json"
        extra_payload_path.write_text(
            json.dumps(extra_desired), encoding="utf-8"
        )
        extra_arg = str(extra_payload_path)
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-",
            str(payload_path),
            json.dumps(effective),
            extra_arg,
        ],
        input=DRIFT_CHECK_SOURCE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


EFFECTIVE_ALL_RULES = [
    {"type": "non_fast_forward"},
    {
        "type": "pull_request",
        "parameters": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews_on_push": True,
            "require_code_owner_review": True,
            "require_last_push_approval": True,
            "required_review_thread_resolution": True,
        },
    },
    {
        "type": "required_status_checks",
        "parameters": {
            "required_status_checks": [
                {"context": "title"},
                {"context": "promotion"},
                {"context": "verify"},
            ]
        },
    },
]

DESIRED_ALL_RULES = {
    "rules": [
        {"type": "non_fast_forward"},
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 1,
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": True,
                "require_last_push_approval": True,
                "required_review_thread_resolution": True,
            },
        },
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
        },
    ]
}


def test_matching_policy_and_live_state_pass_cleanly(tmp_path: Path) -> None:
    """A rulesets.json with all three rules matching live state is clean."""
    result = run_drift_check(DESIRED_ALL_RULES, EFFECTIVE_ALL_RULES, tmp_path)

    assert result.returncode == 0, result.stdout
    assert result.stdout == ""


def test_policy_missing_required_status_checks_reports_clean_error(
    tmp_path: Path,
) -> None:
    """Issue #570: a policy missing required_status_checks must not crash.

    Before the fix, `desired_by_type["required_status_checks"]` executed
    unconditionally and raised an unhandled KeyError whose traceback was
    surfaced verbatim as "Ruleset settings drift: Traceback ...". The fixed
    block must instead report a clear, actionable error and must not emit a
    Python traceback.
    """
    desired_without_checks = {
        "rules": [
            rule
            for rule in DESIRED_ALL_RULES["rules"]
            if rule["type"] != "required_status_checks"
        ]
    }

    result = run_drift_check(
        desired_without_checks, EFFECTIVE_ALL_RULES, tmp_path
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stdout
    assert "KeyError" not in result.stdout
    assert "policy is missing a required_status_checks rule" in result.stdout


def test_policy_missing_pull_request_reports_clean_error(
    tmp_path: Path,
) -> None:
    """The same latent-KeyError pattern is guarded for pull_request too.

    `desired_by_type["pull_request"]["parameters"]` was reached
    unconditionally right after a loop that only checks
    `effective_by_type`, so a policy missing its `pull_request` rule would
    hit the identical unhandled-KeyError failure mode as #570 did for
    required_status_checks.
    """
    desired_without_pull_request = {
        "rules": [
            rule
            for rule in DESIRED_ALL_RULES["rules"]
            if rule["type"] != "pull_request"
        ]
    }

    result = run_drift_check(
        desired_without_pull_request, EFFECTIVE_ALL_RULES, tmp_path
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stdout
    assert "KeyError" not in result.stdout
    assert "policy is missing a pull_request rule" in result.stdout


@pytest.mark.parametrize("missing_context", ["title", "promotion", "verify"])
def test_missing_effective_check_is_reported_by_context(
    missing_context: str, tmp_path: Path
) -> None:
    """A live branch missing one required context is still reported by name."""
    effective = [
        rule
        if rule["type"] != "required_status_checks"
        else {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [
                    check
                    for check in rule["parameters"]["required_status_checks"]
                    if check["context"] != missing_context
                ]
            },
        }
        for rule in EFFECTIVE_ALL_RULES
    ]

    result = run_drift_check(DESIRED_ALL_RULES, effective, tmp_path)

    assert result.returncode != 0
    assert f"missing required checks: {missing_context}" in result.stdout


def test_required_status_checks_desired_from_a_second_file_passes(
    tmp_path: Path,
) -> None:
    """Issue #607: required_status_checks may live in its own Ruleset file.

    From release_phase "beta" onward, policies/rulesets.json no longer
    carries a required_status_checks rule -- it moves to
    policies/rulesets-required-checks.json so it can keep its own,
    always-empty bypass_actors. The drift check must still treat the
    branch as compliant when the union of both files covers all three
    rule types, even though `desired` (the first file) alone does not.
    """
    desired_review_only = {
        "rules": [
            rule
            for rule in DESIRED_ALL_RULES["rules"]
            if rule["type"] != "required_status_checks"
        ]
    }
    desired_required_checks_only = {
        "rules": [
            rule
            for rule in DESIRED_ALL_RULES["rules"]
            if rule["type"] == "required_status_checks"
        ]
    }

    result = run_drift_check(
        desired_review_only,
        EFFECTIVE_ALL_RULES,
        tmp_path,
        extra_desired=desired_required_checks_only,
    )

    assert result.returncode == 0, result.stdout
    assert result.stdout == ""


def test_required_status_checks_missing_from_both_files_still_reported(
    tmp_path: Path,
) -> None:
    """The Issue #570 clean-error guard still applies when neither file
    supplies required_status_checks (extra_desired present but empty)."""
    desired_review_only = {
        "rules": [
            rule
            for rule in DESIRED_ALL_RULES["rules"]
            if rule["type"] != "required_status_checks"
        ]
    }

    result = run_drift_check(
        desired_review_only,
        EFFECTIVE_ALL_RULES,
        tmp_path,
        extra_desired={"rules": []},
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stdout
    assert "policy is missing a required_status_checks rule" in result.stdout
