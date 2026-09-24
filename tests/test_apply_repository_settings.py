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
      `policies/rulesets.json`) that compares the selected Pages build type
      and optional source against `GET /repos/{owner}/{repo}/pages`.
   c. The desired/live reconciliation (Issue #985): `enabled` is the
      maintainer's desired-state choice, so `enabled=false` is an explicit
      opt-out that still yields a DISABLE action when a site is live, and an
      unclassifiable live read stays `unknown` instead of passing.

3. The `apply` mode's `issueCreationPolicy` GraphQL mutation (Issue #757).
   GitHub's schema declares this field's input type as `IssueCreationPolicy`
   (confirmed live via `gh api graphql` introspection against
   `UpdateRepositoryInput` on 2026-09-18); the script previously declared
   the mutation variable as the stale `RepositoryIssueCreationPolicy`, which
   GitHub's schema had since renamed. `check` mode's read-only query never
   declares a variable type at all, so it kept passing while every `apply`
   run failed closed on this step and aborted before reaching any later
   step (release policy, Pages, Actions, labels, Rulesets). The tests below
   run the mutation block verbatim (extracted from the shipped script, not
   reimplemented) against a stub `gh` that enforces the real schema's type
   name, so a future schema rename is caught here instead of only surfacing
   the first time someone runs `apply` against a live repository.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import stat
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
    'python3 - "$pages_policy" "$pages_state" 2>&1 <<\'PY\'\n',
    "\nPY\n",
)

PAGES_RECONCILE_SOURCE = _extract(
    '# classified stays "unknown" so it never passes as compliant.\n',
    '\n\nif [[ "$mode" == "check" ]]; then\n',
)

# `_extract` excludes both markers from its result, but this block needs its
# own start line (`repository_node_id=...`) and closing `fi` kept, since the
# mutation depends on the former and is a dangling `if` without the latter.
_ISSUE_CREATION_POLICY_APPLY_START = (
    'repository_node_id="$(gh api "repos/$repo" --jq .node_id)"\n'
)
_issue_creation_policy_apply_start = SCRIPT_SOURCE.index(
    _ISSUE_CREATION_POLICY_APPLY_START
)
_issue_creation_policy_apply_end = SCRIPT_SOURCE.index(
    "\nfi\n", _issue_creation_policy_apply_start
) + len("\nfi\n")
ISSUE_CREATION_POLICY_APPLY_SOURCE = SCRIPT_SOURCE[
    _issue_creation_policy_apply_start:_issue_creation_policy_apply_end
]


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


def run_pages_reconcile(
    enabled: str,
    available: str,
    live: str,
    tmp_path: Path,
    live_settings: Mapping[str, object] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the shipped Pages inspection and decision against a stub `gh`.

    `live` selects the stubbed `GET repos/{repo}/pages` outcome: a published
    site, GitHub's 404 for an unpublished one, a non-404 error, or `forbid`,
    which fails the test if the script inspects Pages at all. The harness
    prints `<live_state> <action>` so each desired/live pair is asserted
    against the same bash the script ships.
    """
    policy = tmp_path / "pages.json"
    policy.write_text(
        json.dumps({"enabled": enabled == "true", "build_type": "workflow"}),
        encoding="utf-8",
    )
    live_path = tmp_path / "live.json"
    live_path.write_text(
        json.dumps(
            live_settings or {"build_type": "workflow", "status": "built"}
        ),
        encoding="utf-8",
    )
    script = (
        'pages_policy="$1"\n'
        'pages_policy_enabled="$2"\n'
        'pages_enforcement_available="$3"\n'
        'repo="Test-Org/test-repo"\n'
        "gh() {\n"
        '  case "$STUB_PAGES" in\n'
        '    published) cat "$STUB_LIVE" ;;\n'
        "    missing)\n"
        '      echo \'{"message":"Not Found","status":"404"}\'\n'
        "      echo 'gh: Not Found (HTTP 404)' >&2\n"
        "      return 1 ;;\n"
        "    error) echo 'gh: Server Error (HTTP 500)' >&2; return 1 ;;\n"
        "    *) echo 'unexpected Pages inspection' >&2; exit 99 ;;\n"
        "  esac\n"
        "}\n"
        f"{PAGES_RECONCILE_SOURCE}\n"
        'echo "$pages_live_state $pages_action"\n'
    )
    return subprocess.run(  # noqa: S603
        [BASH, "-c", script, "bash", str(policy), enabled, available],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env={
            **os.environ,
            "STUB_PAGES": live,
            "STUB_LIVE": str(live_path),
        },
    )


# `gh` stub for the issue-creation-policy `apply` mutation (Issue #757). It
# encodes the real GitHub schema as confirmed by live introspection against
# `UpdateRepositoryInput` on 2026-09-18 (`updateRepository`'s
# `issueCreationPolicy` argument is typed `IssueCreationPolicy`): it accepts
# only that exact variable type, and otherwise fails the way GitHub itself
# failed for the stale `RepositoryIssueCreationPolicy` name, so a future
# schema rename is caught here the same way the live API caught this one.
# The response bodies below only need to signal success/failure: the real
# script never parses the mutation's JSON on the success path, and only
# echoes the failure path's raw text verbatim.
_ISSUE_CREATION_POLICY_GH_STUB = """#!/usr/bin/env bash
set -euo pipefail
args="$*"
case "$args" in
  *"--jq .node_id"*)
    echo "R_test"
    ;;
  *"api graphql"*)
    if [[ "$args" == *'$policy: IssueCreationPolicy!'* ]]; then
      exit 0
    fi
    bad_type="$(grep -oE '\\$policy: [A-Za-z]+' <<<"$args" \\
      | head -1 | cut -d' ' -f2)"
    echo "variableRequiresValidType: $bad_type" \\
      "isn't a defined input type (on \\$policy)" >&2
    exit 1
    ;;
  *)
    echo "unstubbed gh invocation: $args" >&2
    exit 99
    ;;
esac
"""


def run_issue_creation_policy_apply(
    source: str,
    tmp_path: Path,
    repo: str = "Test-Org/test-repo",
    desired_policy: str = "COLLABORATORS_ONLY",
) -> subprocess.CompletedProcess[str]:
    """Execute an issue-creation-policy apply block against a stub `gh`.

    `source` is normally `ISSUE_CREATION_POLICY_APPLY_SOURCE` (the literal
    block shipped in apply-repository-settings.sh), but a test may pass a
    mutated copy to prove the stub actually rejects a stale type name.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh_stub = bin_dir / "gh"
    gh_stub.write_text(_ISSUE_CREATION_POLICY_GH_STUB, encoding="utf-8")
    executable_bits = stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
    gh_stub.chmod(gh_stub.stat().st_mode | executable_bits)

    script = (
        f'repo="{repo}"\n'
        f'desired_issue_creation_policy="{desired_policy}"\n'
        f"{source}"
    )
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    return subprocess.run(  # noqa: S603
        [BASH, "-c", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
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
                {"context": "title", "integration_id": 15368},
                {"context": "verify", "integration_id": 15368},
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
                    {"context": "title", "integration_id": 15368},
                    {"context": "verify", "integration_id": 15368},
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


@pytest.mark.parametrize("missing_context", ["title", "verify"])
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


def test_wrong_required_check_app_is_reported_by_exact_binding(
    tmp_path: Path,
) -> None:
    """A same-name check from another App does not match desired policy."""
    effective = copy.deepcopy(EFFECTIVE_ALL_RULES)
    checks = next(
        rule for rule in effective if rule["type"] == "required_status_checks"
    )["parameters"]["required_status_checks"]
    checks[0]["integration_id"] = 99999

    result = run_drift_check(DESIRED_ALL_RULES, effective, tmp_path)

    assert result.returncode != 0
    assert "missing required checks: title (App 15368)" in result.stdout


@pytest.mark.parametrize("integration_id", [None, True, 0, -1, "15368"])
def test_required_check_app_binding_must_be_a_positive_integer(
    integration_id: object, tmp_path: Path
) -> None:
    """Missing or malformed App identities fail closed during readback."""
    effective = copy.deepcopy(EFFECTIVE_ALL_RULES)
    checks = next(
        rule for rule in effective if rule["type"] == "required_status_checks"
    )["parameters"]["required_status_checks"]
    checks[0]["integration_id"] = integration_id

    result = run_drift_check(DESIRED_ALL_RULES, effective, tmp_path)

    assert result.returncode != 0
    assert (
        "effective Ruleset required check binding is malformed" in result.stdout
    )


def _with_do_not_enforce_on_create(
    rules: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return a rules list with do_not_enforce_on_create set on the
    required_status_checks rule, leaving every other rule untouched."""
    return [
        rule
        if rule["type"] != "required_status_checks"
        else {
            **rule,
            "parameters": {
                **rule["parameters"],
                "do_not_enforce_on_create": True,
            },
        }
        for rule in rules
    ]


def test_do_not_enforce_on_create_matching_passes_cleanly(
    tmp_path: Path,
) -> None:
    """Issue #754: a live Ruleset that already allows ref creation matches."""
    desired = {
        "rules": _with_do_not_enforce_on_create(DESIRED_ALL_RULES["rules"])
    }
    effective = _with_do_not_enforce_on_create(EFFECTIVE_ALL_RULES)

    result = run_drift_check(desired, effective, tmp_path)

    assert result.returncode == 0, result.stdout
    assert result.stdout == ""


def test_missing_do_not_enforce_on_create_is_reported(tmp_path: Path) -> None:
    """Issue #754: a brand-new dev/m* branch cannot exist without this.

    A live Ruleset still requiring every check to exist at ref-creation
    time makes `git push` to create a matching new branch fail closed
    forever -- there is no commit or PR yet to have produced those
    checks. The drift check must report this, not just the required
    check names, so `apply-repository-settings.sh check` actually proves
    branch creation works instead of only proving the check list matches.
    """
    desired = {
        "rules": _with_do_not_enforce_on_create(DESIRED_ALL_RULES["rules"])
    }

    result = run_drift_check(desired, EFFECTIVE_ALL_RULES, tmp_path)

    assert result.returncode != 0
    assert "do_not_enforce_on_create is not enforced" in result.stdout


def test_required_status_checks_desired_from_a_second_file_passes(
    tmp_path: Path,
) -> None:
    """Issue #745: required_status_checks live in their own Ruleset file.

    policies/rulesets.json carries only review and non-fast-forward rules;
    policies/rulesets-required-checks.json keeps required checks behind
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


def test_matching_pages_workflow_build_type_passes_cleanly(
    tmp_path: Path,
) -> None:
    """Actions-owned Pages does not depend on a branch source."""
    result = run_pages_drift(
        {"enabled": True, "build_type": "workflow"},
        {"build_type": "workflow", "status": "built"},
        tmp_path,
    )

    assert result.returncode == 0, result.stdout
    assert result.stdout == ""


def test_pages_build_type_drift_is_reported(tmp_path: Path) -> None:
    """Branch publishing cannot masquerade as path-filtered Actions."""
    result = run_pages_drift(
        {"enabled": True, "build_type": "workflow"},
        {"build_type": "legacy", "source": DESIRED_SOURCE},
        tmp_path,
    )

    assert result.returncode != 0
    assert "build_type: desired 'workflow', live 'legacy'" in result.stdout


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


# -- Desired/live reconciliation (Issue #985) --


@pytest.mark.parametrize(
    ("enabled", "available", "live", "expected"),
    [
        # Public repository on GitHub Free: capability available.
        ("true", "true", "missing", "unpublished enable"),
        ("true", "true", "published", "published noop"),
        ("false", "true", "published", "published disable"),
        ("false", "true", "missing", "unpublished noop"),
        # A non-404 read error never passes as published or compliant.
        ("true", "true", "error", "unknown unknown"),
        ("false", "true", "error", "unknown unknown"),
        # Capability blocked (private without Enterprise): no live probe.
        ("true", "false", "forbid", "not-inspected degraded"),
        ("false", "false", "forbid", "not-inspected noop"),
    ],
)
def test_pages_reconcile_action_matrix(
    enabled: str, available: str, live: str, expected: str, tmp_path: Path
) -> None:
    """Each desired state maps to one reviewable action per live state.

    `enabled=false` is an explicit opt-out, so a published site must yield
    DISABLE rather than being skipped; public/Free capability alone never
    forces `enable`.
    """
    result = run_pages_reconcile(enabled, available, live, tmp_path)

    assert result.returncode == 0, result.stdout
    assert result.stdout.strip() == expected


def test_pages_reconcile_reports_settings_drift_as_update(
    tmp_path: Path,
) -> None:
    """A published site with the wrong build type is an UPDATE, not a no-op."""
    result = run_pages_reconcile(
        "true",
        "true",
        "published",
        tmp_path,
        live_settings={"build_type": "legacy", "status": "built"},
    )

    assert result.returncode == 0, result.stdout
    assert result.stdout.strip() == "published update"


def test_pages_actions_are_wired_into_plan_check_and_apply() -> None:
    """Every reconciliation action has plan, check, and apply handling."""
    plan = SCRIPT_SOURCE[SCRIPT_SOURCE.index('echo "Deployment plan:"') :]
    for label in (
        "NO-OP",
        "ENABLE",
        "UPDATE",
        "DISABLE",
        "DEGRADED",
        "BLOCKED",
    ):
        assert f'echo "- {label} policies/pages.json' in plan
    assert (
        "Pages settings drift: GitHub Pages is published for $repo; "
        "policies/pages.json requests enabled=false (explicit opt-out)."
    ) in SCRIPT_SOURCE
    assert 'gh api --method DELETE "repos/$repo/pages"' in SCRIPT_SOURCE
    unknown_guard = SCRIPT_SOURCE.index(
        'if [[ "$pages_action" == "unknown" ]]; then'
    )
    first_mutation = SCRIPT_SOURCE.index(
        'gh api --method PATCH "repos/$repo" --input'
    )
    assert unknown_guard < first_mutation


COPILOT_RULE = {
    "type": "copilot_code_review",
    "parameters": {"review_draft_pull_requests": False, "review_on_push": True},
}


def test_copilot_policy_requires_live_copilot_rule(tmp_path: Path) -> None:
    """Issue #752: a Copilot-mode policy fails when the live rule is gone."""
    desired = {"rules": [*DESIRED_ALL_RULES["rules"], COPILOT_RULE]}

    result = run_drift_check(desired, EFFECTIVE_ALL_RULES, tmp_path)

    assert result.returncode != 0
    assert "missing copilot_code_review rule" in result.stdout


def test_copilot_policy_matches_live_copilot_rule(tmp_path: Path) -> None:
    """Issue #752: a live Copilot rule reviewing every push is not drift."""
    desired = {"rules": [*DESIRED_ALL_RULES["rules"], COPILOT_RULE]}
    effective = [*EFFECTIVE_ALL_RULES, COPILOT_RULE]

    result = run_drift_check(desired, effective, tmp_path)

    assert result.returncode == 0, result.stdout


def test_copilot_policy_rejects_review_without_push(tmp_path: Path) -> None:
    """Issue #752: Copilot must re-review each push to gate the new head."""
    desired = {"rules": [*DESIRED_ALL_RULES["rules"], COPILOT_RULE]}
    effective = [
        *EFFECTIVE_ALL_RULES,
        {
            "type": "copilot_code_review",
            "parameters": {"review_on_push": False},
        },
    ]

    result = run_drift_check(desired, effective, tmp_path)

    assert result.returncode != 0
    assert "review_on_push is not enforced" in result.stdout


def test_issue_creation_policy_apply_uses_current_graphql_type(
    tmp_path: Path,
) -> None:
    """Issue #757: the shipped mutation matches GitHub's current schema.

    `check` mode's read-only query never declares a variable type, so it
    kept passing while every `apply` run failed closed on this exact step
    (before this fix, the shipped script declared the mutation variable as
    the stale `RepositoryIssueCreationPolicy`, which GitHub's schema had
    renamed to `IssueCreationPolicy`).
    """
    result = run_issue_creation_policy_apply(
        ISSUE_CREATION_POLICY_APPLY_SOURCE, tmp_path
    )

    assert result.returncode == 0, result.stdout
    assert "Cannot apply issue creation policy" not in result.stdout


def test_issue_creation_policy_apply_rejects_stale_type_name(
    tmp_path: Path,
) -> None:
    """Issue #757: a regression to the stale type name fails closed again.

    Mutates the shipped block back to the historical bug
    (`RepositoryIssueCreationPolicy`) to prove the stub above would have
    caught it, rather than only ever exercising the already-fixed path.
    """
    stale_source = ISSUE_CREATION_POLICY_APPLY_SOURCE.replace(
        "IssueCreationPolicy!", "RepositoryIssueCreationPolicy!"
    )
    assert stale_source != ISSUE_CREATION_POLICY_APPLY_SOURCE

    result = run_issue_creation_policy_apply(stale_source, tmp_path)

    assert result.returncode != 0
    assert "Cannot apply issue creation policy for" in result.stdout
    assert "variableRequiresValidType" in result.stdout
