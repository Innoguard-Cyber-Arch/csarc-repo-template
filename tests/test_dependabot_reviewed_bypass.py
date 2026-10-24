"""Reviewed Dependabot merges under the admin bypass Ruleset (Issue #1262).

GitHub hides a Ruleset's `bypass_actors` from a token that cannot edit it,
such as the `GITHUB_TOKEN` of the Dependabot merge workflow. Lifecycle
accepts that only on the Dependabot route, only for a reviewed merge, and
only when GitHub reports that the token can never bypass the Ruleset.
"""

from __future__ import annotations

import os
import runpy
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from test_pr_lifecycle import (
    DependabotGitHub,
    FakeGitHub,
    bind_remote_lease,
    human_review_mode,
    lease_fixture,
    merge_snapshot,
)

# Re-export the autouse fixture so this module pins the same review mode.
__all__ = ["human_review_mode"]

ROOT = Path(__file__).resolve().parents[1]
MODULES = {
    name: runpy.run_path(str(ROOT / path))["parser"].__globals__
    for name, path in (
        ("root", "scripts/pr_lifecycle.py"),
        ("template", "template/.csarc/scripts/pr_lifecycle.py"),
    )
}
WORKFLOWS = {
    "root": ROOT / ".github/workflows/dependabot-merge.yml",
    "template": ROOT / "template/.github/workflows/dependabot-merge.yml",
}
ADMIN_ROLE = {
    "actor_type": "RepositoryRole",
    "actor_id": 5,
    "bypass_mode": "pull_request",
}
# The live shape of main: the review Ruleset as GITHUB_TOKEN reads it.
HIDDEN: dict[str, object] = {
    "enforcement": "active",
    "current_user_can_bypass": "never",
}


class RulesGitHub:
    """Serve the live main-branch rules and one Ruleset readback."""

    def __init__(self, ruleset: dict[str, object]) -> None:
        self.ruleset = ruleset

    def get(self, _repo: str, path: str) -> object:
        """Return the effective rules or the one Ruleset."""
        if path.startswith("rulesets/"):
            return self.ruleset
        return [
            {
                "type": "pull_request",
                "ruleset_id": 1,
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": True,
                },
            },
            {
                "type": "required_status_checks",
                "ruleset_id": 1,
                "parameters": {
                    "required_status_checks": [
                        {"context": "review", "integration_id": 15368}
                    ]
                },
            },
        ]


@pytest.fixture(params=sorted(MODULES))
def module(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Run each test against the root and the template copy."""
    return MODULES[request.param]


def decide(
    module: dict[str, Any],
    ruleset: dict[str, object],
    reviewed: bool = True,
    dependabot: bool = True,
) -> tuple[str, str, set[tuple[str, int]], bool, bool]:
    """Classify one Ruleset readback on the hosted route."""
    return module["effective_protection"](
        RulesGitHub(ruleset),
        "owner/repo",
        "main",
        False,
        reviewed,
        dependabot_route=dependabot,
    )


def test_reviewed_dependabot_merge_accepts_hidden_bypass_actors(
    module: dict[str, Any],
) -> None:
    """AC2: a reviewed Dependabot merge that cannot bypass is enforced."""
    protection, reason, contexts, reviewed_bypass, _ = decide(module, HIDDEN)

    assert protection == "enforced"
    assert reviewed_bypass is True
    assert contexts == {("review", 15368)}
    # The decision names the hidden readback it accepted.
    assert "hides the bypass actors" in reason


@pytest.mark.parametrize(
    ("ruleset", "reviewed", "dependabot", "reason"),
    [
        (HIDDEN, False, True, "unverified bypass"),
        (HIDDEN, True, False, "hides its bypass actors"),
        (
            {**HIDDEN, "current_user_can_bypass": "pull_requests_only"},
            True,
            True,
            "hides its bypass actors",
        ),
        ({"enforcement": "active"}, True, True, "hides its bypass actors"),
        (
            {
                "enforcement": "active",
                "bypass_actors": [{**ADMIN_ROLE, "actor_id": 4}],
            },
            True,
            True,
            "unverified bypass",
        ),
        (
            {"enforcement": "active", "bypass_actors": None},
            True,
            True,
            "unverified bypass",
        ),
    ],
    ids=[
        "no-approval",
        "not-dependabot",
        "token-can-bypass",
        "bypass-unreported",
        "unknown-actor",
        "null-actors",
    ],
)
def test_unproven_bypass_shapes_stay_blocked(
    module: dict[str, Any],
    ruleset: dict[str, object],
    reviewed: bool,
    dependabot: bool,
    reason: str,
) -> None:
    """AC2: no approval or an unexpected bypass shape fails closed."""
    protection, actual, _, reviewed_bypass, _ = decide(
        module, ruleset, reviewed, dependabot
    )

    assert protection == "blocked"
    assert reason in actual
    assert reviewed_bypass is False


def test_readable_admin_bypass_keeps_its_reason(
    module: dict[str, Any],
) -> None:
    """The admin readback of the known shape is unchanged."""
    protection, reason, _, reviewed_bypass, _ = decide(
        module,
        {"enforcement": "active", "bypass_actors": [ADMIN_ROLE]},
        dependabot=False,
    )

    assert protection == "enforced"
    assert reviewed_bypass is True
    assert reason == "exact-head review and checks are revalidated by lifecycle"


def test_dependabot_snapshot_merges_with_exact_head_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2: approval, eligibility, and checks let the Dependabot route merge."""
    bind_remote_lease(monkeypatch)
    github = DependabotGitHub()
    github.ruleset_response = dict(HIDDEN)
    # The fixture's run 201 carries eligibility, so `verify` is the one
    # required check; the fixture's native review rule needs no `review`.
    github.required_status_checks = [
        {"context": "verify", "integration_id": 15368}
    ]

    snapshot = merge_snapshot(
        github, lease_fixture(), require_dependabot_head=True
    )

    assert snapshot["authorization_source"] == "review"
    assert snapshot["dependabot_head"] == "direct"
    assert snapshot["merge_mode"] == "agent"


def test_ordinary_snapshot_keeps_hidden_bypass_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scope: a hidden bypass never relaxes the ordinary route."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.ruleset_response = dict(HIDDEN)

    snapshot = merge_snapshot(github, lease_fixture())

    assert snapshot["merge_mode"] == "human-only"
    assert "hides its bypass actors" in str(snapshot["protection_reason"])


def run_check_step(
    name: str, tmp_path: Path, merge_mode: str, status: int = 0
) -> subprocess.CompletedProcess[str]:
    """Run the workflow's check step against a stub lifecycle snapshot."""
    workflow = yaml.safe_load(WORKFLOWS[name].read_text(encoding="utf-8"))
    steps = {step["name"]: step for step in workflow["jobs"]["merge"]["steps"]}
    stub = tmp_path / "bin"
    stub.mkdir(parents=True)
    python = stub / "python3"
    python.write_text(
        "#!/bin/sh\n"
        "echo 'NOTICE: PR lifecycle check runs from trusted base abc.'\n"
        'printf \'{\\n  "merge_mode": "%s",\\n  "protection": "x"\\n}\\n\''
        f" '{merge_mode}'\n"
        f"exit {status}\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    return subprocess.run(  # noqa: S603 - fixed shell over the step text
        [
            "/bin/bash",
            "-e",
            "-c",
            steps["Revalidate lifecycle merge eligibility"]["run"],
        ],
        env={
            **os.environ,
            "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_refused_snapshot_fails_so_the_run_releases_its_lease(
    name: str, tmp_path: Path
) -> None:
    """AC3: a refused snapshot fails the check, which releases the lease."""
    workflow = yaml.safe_load(WORKFLOWS[name].read_text(encoding="utf-8"))
    steps = {step["name"]: step for step in workflow["jobs"]["merge"]["steps"]}
    release = steps["Release a pre-merge rejected lease"]

    refused = run_check_step(name, tmp_path / "refused", "human-only")
    assert refused.returncode == 1
    assert "ERROR: Dependabot merge: lifecycle refused" in refused.stderr
    assert '"merge_mode": "human-only"' in refused.stdout
    # A failed check is exactly the condition that runs the release step,
    # which releases only this run's own lease file and owner.
    assert "steps.check.outcome == 'failure'" in release["if"]
    assert "pr_lifecycle.py release" in release["run"]
    assert '--owner "$OWNER"' in release["run"]
    assert "dependabot-lease.json" in release["run"]

    errored = run_check_step(name, tmp_path / "errored", "agent", status=3)
    assert errored.returncode == 3
    assert run_check_step(name, tmp_path / "agent", "agent").returncode == 0
