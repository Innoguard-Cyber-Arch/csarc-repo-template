"""Milestone-only scripts render only where a caller needs them (#1208).

`sync_milestone_state.py`, `promotion_gate.py`, and `delivery_sync.py`
serve Milestone approval, promotion, and delivery sync. Hosted PR policy
calls them on every render, so a hosted render keeps them; a local render
without `lifecycle: milestones` omits them, and each caller treats the
missing module as Milestones not enabled.
"""

from __future__ import annotations

import os
import re
import runpy
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import jinja2
import pytest
import settings_support
import yaml
from test_generated_runtime_boundary import minimal_render
from test_settings_authority import adapter_repository

ROOT = Path(__file__).resolve().parents[1]
MILESTONE_SCRIPTS = (
    ".csarc/scripts/sync_milestone_state.py",
    ".csarc/scripts/promotion_gate.py",
    ".csarc/scripts/delivery_sync.py",
)
ROUTE_FOR = cast(
    "Callable[..., Any]",
    runpy.run_path(str(ROOT / "scripts/promotion_gate.py"))["route_for"],
)
# Heads and labels for every route `promotion_gate.route_for` knows.
ROUTE_CASES: tuple[tuple[str, str, frozenset[str]], ...] = tuple(
    (base, head, frozenset(labels))
    for base in ("main", "dev/m3-delivery")
    for head in (
        "release-please--branches--main",
        "release/v1.2.3",
        "fix/12-recover",
        "fix/hotpatch",
        "dev/m3-delivery",
        "promote/m3-delivery",
        "dev/i7-canary",
        "feat/12-change",
        "dependabot/uv/x",
        "automation/sync",
        "random-branch",
    )
    for labels in (
        (),
        ("promotion",),
        ("hotfix",),
        ("release-recovery",),
        ("release-recovery", "hotfix"),
    )
)


# Kinds no lifecycle caller records; without Milestones a Milestone route
# joins them.
UNRECORDED = frozenset({"invalid-main-route", "milestone", "not-applicable"})


def copier_rules() -> dict[str, str]:
    """Return the Copier exclusion expression for each Milestone script."""
    config = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    rules: dict[str, str] = {}
    for rule in config["_exclude"]:
        for path in MILESTONE_SCRIPTS:
            if rule.endswith(f"{{% else %}}{path}{{% endif %}}"):
                rules[path] = rule
    assert set(rules) == set(MILESTONE_SCRIPTS)
    return rules


@pytest.mark.parametrize("verification", ["hosted", "local"])
@pytest.mark.parametrize(
    "lifecycle", [[], ["issues"], ["milestones"], ["issues", "milestones"]]
)
def test_milestone_scripts_render_for_milestones_or_hosted(
    verification: str, lifecycle: list[str]
) -> None:
    """AC1: only a local render without Milestones omits the scripts."""
    environment = jinja2.Environment(autoescape=False)  # noqa: S701
    context = {"verification_mode": verification, "lifecycle": lifecycle}
    rendered = verification == "hosted" or "milestones" in lifecycle
    for path, rule in copier_rules().items():
        excluded = environment.from_string(rule).render(context) == path
        assert excluded is not rendered, (path, context)


@pytest.fixture
def local_lifecycle(tmp_path: Path) -> dict[str, Any]:
    """Load the generated `pr_lifecycle.py` without Milestone scripts."""
    project = minimal_render(tmp_path)
    scripts = project / ".csarc/scripts"
    for path in MILESTONE_SCRIPTS:
        assert not (project / path).exists()
    return runpy.run_path(str(scripts / "pr_lifecycle.py"))


@pytest.mark.parametrize(("base", "head", "labels"), ROUTE_CASES)
def test_routes_without_milestones_match_promotion_gate(
    local_lifecycle: dict[str, Any],
    base: str,
    head: str,
    labels: frozenset[str],
) -> None:
    """AC2: every non-Milestone route keeps its `promotion_gate` kind."""
    expected = ROUTE_FOR(base, head, set(labels)).kind
    actual = local_lifecycle["main_route_kind"](base, head, set(labels))
    if expected in UNRECORDED:
        assert actual in UNRECORDED
    else:
        assert actual == expected


def test_milestone_route_without_milestones_fails_clearly(
    local_lifecycle: dict[str, Any],
) -> None:
    """AC2: a Milestone-only lifecycle step names the missing option."""
    with pytest.raises(RuntimeError, match="lifecycle: milestones"):
        local_lifecycle["require_milestones"]()


def test_trailer_route_without_milestones(
    local_lifecycle: dict[str, Any],
) -> None:
    """The merge trailer route still records non-Milestone routes."""
    trailer_route = local_lifecycle["trailer_route"]
    assert trailer_route("main", "fix/12-recover", {"hotfix"}, False) == (
        "hotfix"
    )
    assert (
        trailer_route("main", "fix/12-recover", {"release-recovery"}, False)
        == "release-recovery"
    )
    assert trailer_route("main", "dev/i7-canary", {"promotion"}, False) == (
        "isolated"
    )
    assert trailer_route("main", "feat/12-change", set(), False) == "issue"


def fake_gh(tmp_path: Path) -> tuple[Path, Path]:
    """Return a PATH directory whose `gh` logs its arguments and succeeds."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh.log"
    gh = bin_dir / "gh"
    gh.write_text(
        f'#!/usr/bin/env bash\necho "$*" >> "{log}"\n', encoding="utf-8"
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    return bin_dir, log


def test_issue_edit_without_milestones_edits_without_approval_check(
    tmp_path: Path,
) -> None:
    """AC2: `gh-issue-edit` still edits; no approval check runs."""
    project = minimal_render(tmp_path)
    bin_dir, log = fake_gh(tmp_path)
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "python3",
            str(project / ".csarc/scripts/gh-issue-edit"),
            "42",
            "--body",
            "new body",
        ],
        cwd=project,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        stdin=subprocess.DEVNULL,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert log.read_text(encoding="utf-8").splitlines() == [
        "issue edit 42 --body new body"
    ]


def test_pr_policy_without_milestones_rejects_a_milestone_promotion(
    tmp_path: Path,
) -> None:
    """AC2: a Milestone promotion names the missing option."""
    repository = adapter_repository(
        tmp_path, "template", settings_support.settings_text()
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PR_", "GITHUB_"))
    }
    result = subprocess.run(  # noqa: S603
        [str(repository / ".csarc/scripts/validate-pr-policy")],
        cwd=repository,
        env={
            **environment,
            "PR_BASE": "main",
            "PR_DRAFT": "true",
            "PR_HEAD": "promote/m3-delivery",
            "PR_LABELS": "enhancement,promotion",
            "PR_NUMBER": "7",
            "PR_POLICY_FIXTURE": "true",
            "PR_RELEASE_OWNERSHIP": "product-owned",
            "PR_TITLE": "feat: promote Milestone 3 delivery",
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Milestone promotion: needs lifecycle: milestones." in (
        result.stderr
    )


def test_publish_release_skips_milestone_completion_without_milestones(
    tmp_path: Path,
) -> None:
    """A release in a render without Milestones skips Milestone closure."""
    source = (ROOT / "template/.csarc/scripts/publish-release").read_text(
        encoding="utf-8"
    )
    function = re.search(
        r"^complete_published_milestone\(\) \{\n.*?^\}\n", source, re.M | re.S
    )
    assert function is not None
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "bash",
            "-c",
            f'set -euo pipefail\n{function.group(0)}repo_root="$1"\n'
            "complete_published_milestone v1.0.0\necho skipped",
            "publish-release",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "skipped\n"


def test_stale_branch_detector_does_not_keep_a_milestone_script() -> None:
    """R2: an unchanged CSARC file must not keep a removal alive (#1146).

    The update plan keeps a removed file that a kept file names as a path;
    the stale-branch detector is often unchanged across releases, so its
    prose must not name a Milestone script path.
    """
    from csarc_cli import file_transition

    name = ".csarc/scripts/stale_branch_detection.py"
    content = (ROOT / "template" / name).read_bytes()
    assert file_transition.content_uses(name, content, MILESTONE_SCRIPTS) == ()
