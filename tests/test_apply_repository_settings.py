"""Regression tests for policy-drift logic embedded in
scripts/apply-repository-settings.sh.

This file covers three independently added pieces of the script, each
extracted verbatim from the shipped script (not reimplemented) and
executed via subprocess against crafted fixtures, so a regression in
either the script's guard clauses or its heredoc/conditional boundaries is
caught here without mocking the full `gh` CLI surface that
`apply-repository-settings.sh check` otherwise requires:

1. The Ruleset drift-check (Issue #570). The `check` mode compares
   policies/rulesets.json ("desired") against the live GitHub effective
   rules ("effective", the response body of
   `gh api repos/{repo}/rules/branches/{branch}`) using a Python block
   embedded in the script as a `python3 - <<'PY' ... PY` heredoc. That
   block used to assume unconditionally that both the desired *and* the
   effective rule sets already contained a `required_status_checks` entry
   (`desired_by_type["required_status_checks"]`); when policies/rulesets.json
   was missing that rule, the drift-check crashed with an unhandled
   `KeyError` instead of reporting a clear policy error. From release_phase
   "beta" onward (Issue #607), that same rule instead lives in a second
   file, policies/rulesets-required-checks.json, passed as a third
   positional argument (`extra_desired` in the test harness below); the
   drift-check must treat the union of both files' rules as "desired".

2. The GitHub Pages policy logic (Issue #571). GitHub Pages is a separate
   REST resource (`/repos/{owner}/{repo}/pages`), not a field on the
   repository object, so it gets its own `policies/pages.json` declaration
   plus dedicated apply/check handling in the shell script. That handling
   has two independently testable pieces:

   a. A pure bash decision (`pages_enforcement_available`) that mirrors the
      plan-aware DEGRADED detection already used for Rulesets
      (`ruleset_enforcement_available`): GitHub Pages is free for public
      repositories on every plan, but a private repository requires GitHub
      Enterprise Cloud. This is derived from the already-computed
      `repo_visibility` and `plan_label` variables, not recomputed from a
      live API probe.
   b. A Python drift-check heredoc (mirrors the pattern used for
      `policies/repository.json`/`policies/releases.json`/
      `policies/rulesets.json`) that compares `policies/pages.json`'s
      `source` object against the live `GET /repos/{owner}/{repo}/pages`
      response body.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply-repository-settings.sh"
SCRIPT_SOURCE = SCRIPT.read_text(encoding="utf-8")
_BASH = shutil.which("bash")
if _BASH is None:
    raise RuntimeError("bash is required for apply-repository-settings tests")
BASH: str = _BASH


def _extract(start_marker: str, end_marker: str) -> str:
    """Pull one literal snippet out of the shipped script by markers.

    Extracting the literal text (rather than duplicating the logic in the
    test) guarantees this test exercises the same code the script ships,
    and fails loudly if the markers ever move.
    """
    start = SCRIPT_SOURCE.index(start_marker) + len(start_marker)
    end = SCRIPT_SOURCE.index(end_marker, start)
    return SCRIPT_SOURCE[start:end]


DRIFT_CHECK_SOURCE = _extract(
    'elif ! ruleset_drift="$(python3 - "$ruleset_payload" "$branch_rules" '
    "\"$check_desired_rules_payload_extra\" 2>&1 <<'PY'\n",
    "\nPY\n",
)

PAGES_AVAILABILITY_SOURCE = _extract(
    "pages_enforcement_available=true\n",
    "\n\ncodeowners_validation=",
)

PAGES_DRIFT_SOURCE = _extract(
    'elif ! pages_drift="$(python3 - "$pages_policy" "$pages_state" '
    "2>&1 <<'PY'\n",
    "\nPY\n",
)


def run_drift_check(
    desired: dict[str, object],
    effective: list[dict[str, object]],
    tmp_path: Path,
    extra_desired: dict[str, object] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute the extracted ruleset drift-check heredoc against fixture JSON.

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


def run_pages_availability(
    repo_visibility: str, plan_label: str
) -> subprocess.CompletedProcess[str]:
    """Execute the extracted availability decision with fixture inputs.

    The real script computes this once near the top from repo_visibility
    and plan_label (both already derived from live `gh api` calls); this
    harness only supplies those two inputs and echoes the result, so the
    exact same bash guard clause is under test.
    """
    script = (
        "repo_visibility=$1\n"
        "plan_label=$2\n"
        "pages_enforcement_available=true\n"
        f"{PAGES_AVAILABILITY_SOURCE}\n"
        'echo "$pages_enforcement_available"\n'
    )
    return subprocess.run(  # noqa: S603
        [BASH, "-c", script, "bash", repo_visibility, plan_label],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def run_pages_drift(
    desired: Mapping[str, object],
    actual: Mapping[str, object],
    tmp_path: Path,
) -> subprocess.CompletedProcess[str]:
    """Execute the extracted Pages drift-check heredoc against fixtures.

    The real invocation captures the heredoc with `2>&1`, merging stdout
    and stderr into one string before deciding what to print. Mirror that
    here so `result.stdout` reflects exactly what an operator would see
    from `apply-repository-settings.sh check`.
    """
    payload_path = tmp_path / "pages.json"
    payload_path.write_text(json.dumps(desired), encoding="utf-8")
    return subprocess.run(  # noqa: S603
        [sys.executable, "-", str(payload_path), json.dumps(actual)],
        input=PAGES_DRIFT_SOURCE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


# ---------------------------------------------------------------------------
# Ruleset drift-check (Issue #570)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# GitHub Pages policy (Issue #571)
# ---------------------------------------------------------------------------

# -- pages_enforcement_available: positive and negative DEGRADED cases --


@pytest.mark.parametrize(
    ("repo_visibility", "plan_label"),
    [
        ("public", "GitHub Free"),
        ("public", "GitHub Pro"),
        ("public", "GitHub Team"),
        ("public", "Unknown (unknown)"),
        ("private", "GitHub Enterprise"),
    ],
)
def test_pages_available_when_public_or_enterprise(
    repo_visibility: str, plan_label: str
) -> None:
    """Public repos, and Enterprise-plan private ones, are not degraded."""
    result = run_pages_availability(repo_visibility, plan_label)

    assert result.returncode == 0, result.stdout
    assert result.stdout.strip() == "true"


@pytest.mark.parametrize(
    ("repo_visibility", "plan_label"),
    [
        ("private", "GitHub Free"),
        ("private", "GitHub Pro"),
        ("private", "GitHub Team"),
        ("private", "Unknown (unknown)"),
    ],
)
def test_pages_degraded_when_private_without_enterprise(
    repo_visibility: str, plan_label: str
) -> None:
    """A private repository without GitHub Enterprise Cloud is degraded.

    GitHub Pages cannot be enabled on a private repository on Free, Pro,
    or Team; only GitHub Enterprise Cloud supports it. This must report
    unavailable rather than attempt (and fail) the live API call.
    """
    result = run_pages_availability(repo_visibility, plan_label)

    assert result.returncode == 0, result.stdout
    assert result.stdout.strip() == "false"


# -- Pages drift-check heredoc: matching and drifted live state --

DESIRED_SOURCE = {"branch": "main", "path": "/docs"}


def test_matching_pages_source_passes_cleanly(tmp_path: Path) -> None:
    """Live Pages state matching policies/pages.json reports no drift."""
    actual = {"source": dict(DESIRED_SOURCE), "status": "built"}

    result = run_pages_drift(
        {"enabled": True, "source": DESIRED_SOURCE}, actual, tmp_path
    )

    assert result.returncode == 0, result.stdout
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("live_source", "expected_message"),
    [
        (
            {"branch": "gh-pages", "path": "/docs"},
            "source.branch: desired 'main', live 'gh-pages'",
        ),
        (
            {"branch": "main", "path": "/"},
            "source.path: desired '/docs', live '/'",
        ),
    ],
)
def test_drifted_pages_source_is_reported(
    live_source: dict[str, str], expected_message: str, tmp_path: Path
) -> None:
    """A live source that differs from policy is reported field-by-field."""
    actual = {"source": live_source, "status": "built"}

    result = run_pages_drift(
        {"enabled": True, "source": DESIRED_SOURCE}, actual, tmp_path
    )

    assert result.returncode != 0
    assert expected_message in result.stdout


def test_missing_live_source_is_reported(tmp_path: Path) -> None:
    """A live response with no source object at all is treated as drift."""
    actual = {"status": "built"}

    result = run_pages_drift(
        {"enabled": True, "source": DESIRED_SOURCE}, actual, tmp_path
    )

    assert result.returncode != 0
    assert "source.branch: desired 'main', live None" in result.stdout
    assert "source.path: desired '/docs', live None" in result.stdout
