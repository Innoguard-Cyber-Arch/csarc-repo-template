"""Hosted and VM verification run the trusted base's checks (Issue #1325).

Hosted CI (`ci.yml`) and the self-hosted VM (`csarc-verify.yml`) stage a
control set from the trusted base before they check out the candidate. The
control set now carries every check script and the base's settings, so a
candidate that turns one of its own checks into `exit 0` still fails. These
tests run the rendered workflow steps themselves, in both renders, against a
fixture repository.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generated_payload  # noqa: E402

BRANCH = "fix/7-quiet-checks"
SELF_HOSTED = {
    **generated_payload.SOLO_SELF_HOSTED,
    "project_visibility": "private",
    "security_reporting_channel": "security@example.com",
}
HOSTED = {**generated_payload.SOLO_LOCAL, **generated_payload.HOSTED}
# Each route: the render, its workflow, the execute step's name prefix, and
# the execute step's environment as the workflow resolves it. A change under
# .csarc/scripts selects the full tier, so the full entry point runs.
ROUTES = {
    "hosted": (
        HOSTED,
        "ci.yml",
        "Execute trusted verification",
        {
            "CSARC_CI_BASE": "main",
            "CSARC_CI_DRAFT": "false",
            "CSARC_CI_SCOPES": "",
            "CSARC_CI_TIER": "full",
            "CSARC_VERIFICATION_SUITE": "full",
            "EXECUTOR": "trusted-base",
        },
    ),
    "self-hosted": (
        SELF_HOSTED,
        "csarc-verify.yml",
        "Execute self-hosted verification",
        {
            "CSARC_CI_BASE": "main",
            "CSARC_CI_LABELS": "",
            "CSARC_CI_SCOPES": "",
            "CSARC_CI_TIER": "fast",
            "CSARC_SELF_HOSTED_VM": "true",
            "CSARC_VERIFICATION_SUITE": "fast",
        },
    ),
}
PRESERVE = "Preserve the trusted verification policy"
# Checks a candidate silences; only the conflict check sees the planted
# marker, the others are silenced so the fallback run needs no network.
SILENCED = (
    "check-update-conflicts",
    "lint-workflows-shell",
    "scan-secrets",
    "verify-dependencies",
)
CONFLICT = "ERROR: Update conflict"


def git(repo: Path, *args: str) -> str:
    """Run Git in one fixture repository."""
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def step(workflow: Path, prefix: str) -> str:
    """Return the `run` script of the one step whose name starts so."""
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    scripts = [
        item["run"]
        for job in document["jobs"].values()
        for item in job.get("steps", [])
        if str(item.get("name", "")).startswith(prefix)
    ]
    assert len(scripts) == 1, (workflow.name, prefix, len(scripts))
    return scripts[0]


def run_step(
    script: str, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run one workflow step the way GitHub Actions runs `bash`."""
    clean = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CSARC_", "GITHUB_", "RUNNER_"))
    }
    return subprocess.run(  # noqa: S603
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],  # noqa: S607
        cwd=cwd,
        env={**clean, **env},
        check=False,
        capture_output=True,
        text=True,
    )


def silence_checks(repo: Path) -> None:
    """Plant a conflict marker and make the candidate's own checks pass."""
    for name in SILENCED:
        script = repo / ".csarc/scripts" / name
        assert script.is_file(), name
        script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (repo / ".csarc/notes.txt").write_text(
        "<<<<<<< ours\nkept\n=======\ndropped\n>>>>>>> theirs\n",
        encoding="utf-8",
    )


def fall_back_to_candidate(base: Path) -> None:
    """Make the base entry points read checks from the candidate (pre-#1325)."""
    trusted = 'check_root="$control_root"\n'
    for name in ("verify-fast", "verify"):
        script = base / ".csarc/scripts" / name
        text = script.read_text(encoding="utf-8")
        assert text.count(trusted) == 1, name
        script.write_text(
            text.replace(trusted, 'check_root="$repo_root"\n'),
            encoding="utf-8",
        )


@pytest.fixture(scope="module")
def renders(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Render the hosted and the self-hosted project once."""
    workdir = tmp_path_factory.mktemp("trusted-checks")
    source = workdir / "source"
    source.mkdir()
    generated_payload.template_copy(source)
    return {
        name: generated_payload.render(source, workdir / name, data)
        for name, (data, *_rest) in ROUTES.items()
    }


def verify_route(
    tmp_path: Path,
    render: Path,
    route: str,
    change_base: Callable[[Path], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Stage the base like the workflow, then verify the silenced candidate."""
    _data, workflow, execute, execute_env = ROUTES[route]
    repo = tmp_path / "repo"
    shutil.copytree(render, repo)
    if change_base is not None:
        change_base(repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Trusted Checks")
    git(repo, "config", "user.email", "checks@example.invalid")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: trusted base")
    base = tmp_path / "base"
    git(repo, "worktree", "add", "-q", "--detach", str(base), "main")
    git(repo, "switch", "-qc", BRANCH)
    silence_checks(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fix: quiet the update checks")

    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    output = tmp_path / "github-output"
    common = {"RUNNER_TEMP": str(runner_temp), "GITHUB_OUTPUT": str(output)}
    workflow_path = repo / ".github/workflows" / workflow
    preserved = run_step(
        step(workflow_path, PRESERVE),
        base,
        {**common, "GITHUB_WORKSPACE": str(base), "GUIDED_RELEASE": "false"},
    )
    assert preserved.returncode == 0, preserved.stdout + preserved.stderr
    return run_step(
        step(workflow_path, execute),
        repo,
        {**common, "GITHUB_WORKSPACE": str(repo), **execute_env},
    )


@pytest.mark.large
@pytest.mark.parametrize("route", sorted(ROUTES))
def test_candidate_cannot_silence_a_trusted_check(
    tmp_path: Path, renders: dict[str, Path], route: str
) -> None:
    """AC2: a candidate check turned into `exit 0` never yields success."""
    result = verify_route(tmp_path, renders[route], route)
    log = result.stdout + result.stderr
    assert result.returncode != 0, log
    assert CONFLICT in log


@pytest.mark.large
@pytest.mark.parametrize("route", sorted(ROUTES))
def test_negative_control_fallback_lets_the_candidate_pass(
    tmp_path: Path, renders: dict[str, Path], route: str
) -> None:
    """The AC2 test fails when the check root falls back to the candidate.

    A base whose entry point reads checks from the candidate, as the staged
    control did before #1325, runs the silenced copies and passes, so the
    assertions above would not hold.
    """
    result = verify_route(
        tmp_path, renders[route], route, change_base=fall_back_to_candidate
    )
    log = result.stdout + result.stderr
    assert result.returncode == 0, log
    assert CONFLICT not in log
