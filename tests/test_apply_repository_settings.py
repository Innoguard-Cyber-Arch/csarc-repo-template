"""Regression tests for the GitHub Pages policy logic embedded in
scripts/apply-repository-settings.sh (Issue #571).

GitHub Pages is a separate REST resource (`/repos/{owner}/{repo}/pages`),
not a field on the repository object, so it gets its own
`policies/pages.json` declaration plus dedicated apply/check handling in
the shell script. That handling has two independently testable pieces:

1. A pure bash decision (`pages_enforcement_available`) that mirrors the
   plan-aware DEGRADED detection already used for Rulesets
   (`ruleset_enforcement_available`): GitHub Pages is free for public
   repositories on every plan, but a private repository requires GitHub
   Enterprise Cloud. This is derived from the already-computed
   `repo_visibility` and `plan_label` variables, not recomputed from a
   live API probe.
2. A Python drift-check heredoc (mirrors the pattern used for
   `policies/repository.json`/`policies/releases.json`/
   `policies/rulesets.json`) that compares `policies/pages.json`'s
   `source` object against the live `GET /repos/{owner}/{repo}/pages`
   response body.

Both pieces are extracted verbatim from the shipped script (not
reimplemented) and executed via subprocess against crafted fixtures, so a
regression in either the script's guard clauses or its heredoc/conditional
boundaries is caught here without mocking the full `gh` CLI surface that
`apply-repository-settings.sh check` otherwise requires. This follows the
same extraction pattern established for the Ruleset drift-check heredoc in
this same file (Issue #570).
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


PAGES_AVAILABILITY_SOURCE = _extract(
    "pages_enforcement_available=true\n",
    "\n\ncodeowners_validation=",
)

PAGES_DRIFT_SOURCE = _extract(
    'elif ! pages_drift="$(python3 - "$pages_policy" "$pages_state" '
    "2>&1 <<'PY'\n",
    "\nPY\n",
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
