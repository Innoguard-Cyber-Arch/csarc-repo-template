"""Tests for change-aware CI routing."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "ci_tier.py")
)
classify = MODULE["classify"]
scope_for = MODULE["scope_for"]


@pytest.mark.parametrize(
    ("path", "scope"),
    [
        ("docs/guide.md", "docs"),
        ("README.md", "docs"),
        ("src/pkg/core.py", "source"),
        ("template/README.md.jinja", "template"),
        (".github/workflows/ci.yml", "workflow"),
        ("template/.github/workflows/ci.yml.jinja", "workflow"),
        (".github/actions/setup/action.yml", "workflow"),
        ("uv.lock", "dependency"),
        ("template/pyproject.toml.jinja", "dependency"),
        ("policies/rulesets.json", "governance"),
        ("policies/dev-next-ruleset.json", "governance"),
        ("template/policies/rulesets.json.jinja", "governance"),
        ("template/policies/dev-next-ruleset.json", "governance"),
        ("unexpected.bin", "unknown"),
    ],
)
def test_scope_for(path: str, scope: str) -> None:
    """Classify every governed change family."""
    assert scope_for(path) == scope


def test_docs_only_uses_docs_tier() -> None:
    """Documentation does not start language or generator matrices."""
    plan = classify(
        "pull_request", "dev/next", "docs/9-guide", set(), ["README.md"]
    )
    assert plan.tier == "docs"
    assert not plan.run_osv
    assert not plan.run_zizmor


def test_source_uses_fast_canonical_runtime() -> None:
    """Ordinary code receives the non-trivial fast verification tier."""
    plan = classify(
        "pull_request", "dev/m7-ci", "feat/9-code", set(), ["src/pkg/core.py"]
    )
    assert plan.tier == "fast"
    assert plan.scopes == ("source",)


@pytest.mark.parametrize(
    ("path", "flag"),
    [
        (".github/workflows/ci.yml", "run_zizmor"),
        ("uv.lock", "run_osv"),
        ("policies/rulesets.json", "run_governance"),
        ("policies/dev-next-ruleset.json", "run_governance"),
    ],
)
def test_risk_scopes_enable_only_their_expensive_check(
    path: str, flag: str
) -> None:
    """Keep unrelated security and remote checks out of ordinary PRs."""
    plan = classify("pull_request", "dev/next", "chore/9-change", set(), [path])
    assert plan.tier == "fast"
    assert getattr(plan, flag)


@pytest.mark.parametrize(
    ("base", "head", "labels", "reason"),
    [
        ("main", "dev/m7-ci", set(), "delivery promotion"),
        ("main", "dev/i42-soak", {"promotion"}, "delivery promotion"),
        ("main", "fix/9-outage", {"hotfix"}, "hotfix to main"),
    ],
)
def test_promotion_and_hotfix_use_full_tier(
    base: str, head: str, labels: set[str], reason: str
) -> None:
    """Run the complete matrix at every delivery route that can change main."""
    plan = classify("pull_request", base, head, labels, ["src/pkg/core.py"])
    assert plan.tier == "full"
    assert plan.reason == reason
    assert plan.run_governance and plan.run_osv and plan.run_zizmor


def test_unknown_and_missing_paths_fail_safe_to_full() -> None:
    """Do not treat an unclassified non-trivial change as cheap."""
    assert (
        classify(
            "pull_request", "dev/next", "feat/9-change", set(), ["unknown.bin"]
        ).tier
        == "full"
    )
    assert (
        classify("pull_request", "dev/next", "feat/9-change", set(), []).tier
        == "full"
    )


def test_push_does_not_repeat_the_verified_source_tree() -> None:
    """A merged tree records post-merge evidence without another full suite."""
    plan = classify("push", "", "", set(), ["src/pkg/core.py"])
    assert plan.tier == "post-merge"


def test_manual_and_merge_queue_runs_are_full() -> None:
    """Explicit and queued candidates retain the complete gate."""
    manual = classify(
        "workflow_dispatch", "", "", set(), ["README.md"], force_full=True
    )
    queued = classify("merge_group", "main", "queue", set(), ["README.md"])
    assert manual.tier == queued.tier == "full"
