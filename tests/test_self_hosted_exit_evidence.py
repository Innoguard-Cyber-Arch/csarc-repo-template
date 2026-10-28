"""The retire exit pull request can record merge evidence (Issue #1318).

`csarc self-hosted retire` re-renders a private self-hosted project in public
mode with `verification_mode_private` defaulting to the public mode, which is
`hosted`. That render ships no local evidence recorder, so the candidate's own
verifier cannot produce the local evidence the ADR Q1 exit requires. The
trusted base's verifier checks the candidate as its control set instead.
"""

from __future__ import annotations

import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generated_payload  # noqa: E402

BRANCH = "chore/5-leave-self-hosted"
SIBLINGS = ("csarc_config", "evidence_freshness")
PRIVATE = {
    **generated_payload.SOLO_SELF_HOSTED,
    "project_visibility": "private",
    "security_reporting_channel": "security@example.com",
}
# What `retire` passes by default: the private mode becomes the public one.
PUBLIC = {
    **PRIVATE,
    "project_visibility": "public",
    "verification_mode_private": PRIVATE["verification_mode_public"],
}


def git(repo: Path, *args: str) -> str:
    """Run Git in one fixture repository."""
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def verify(script: Path, cwd: Path, **env: str) -> subprocess.CompletedProcess:
    """Run one rendered verifier with the fixture base."""
    return subprocess.run(  # noqa: S603
        [str(script)],
        cwd=cwd,
        env={**os.environ, "CSARC_CI_BASE": "main", **env},
        check=False,
        capture_output=True,
        text=True,
    )


def replace_tree(repo: Path, render: Path) -> None:
    """Make the worktree match one render, keeping only Git metadata."""
    for item in repo.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    shutil.copytree(render, repo, dirs_exist_ok=True)


@pytest.mark.large
def test_default_retire_exit_records_evidence_with_the_base_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: the default hosted exit gets local evidence and qualifies."""
    source = tmp_path / "source"
    source.mkdir()
    generated_payload.template_copy(source)
    private = generated_payload.render(source, tmp_path / "private", PRIVATE)
    public = generated_payload.render(source, tmp_path / "public", PUBLIC)
    recorder = ".csarc/scripts/local_verification.py"
    assert (private / recorder).is_file()
    assert not (public / recorder).exists()

    repo = tmp_path / "repo"
    shutil.copytree(private, repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Exit Test")
    git(repo, "config", "user.email", "exit@example.invalid")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: private self-hosted project")
    git(repo, "switch", "-qc", BRANCH)
    git(repo, "config", f"branch.{BRANCH}.gh-merge-base", "main")
    replace_tree(repo, public)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: leave self-hosted verification")
    head, base_sha = (
        git(repo, "rev-parse", "HEAD"),
        git(repo, "rev-parse", "main"),
    )
    base = tmp_path / "base"
    git(repo, "worktree", "add", "-q", "--detach", str(base), "main")
    evidence = (
        Path(
            git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
        )
        / "csarc/local-verification"
        / f"{head}.json"
    )

    # The candidate's own hosted verifier passes but records nothing.
    own = verify(repo / ".csarc/scripts/verify-fast", repo)
    assert own.returncode == 0, own.stdout + own.stderr
    assert not evidence.exists()

    trusted = verify(
        base / ".csarc/scripts/verify-fast",
        repo,
        CSARC_VERIFICATION_SUBJECT_ROOT=str(repo),
    )
    assert trusted.returncode == 0, trusted.stdout + trusted.stderr
    assert evidence.is_file()

    # The trusted base's own lifecycle modules accept the exit and its proof.
    lease = {"head_sha": head, "base_sha": base_sha}
    scripts = base / ".csarc/scripts"
    # The rendered modules add their own directory to the import path.
    monkeypatch.setattr(sys, "path", list(sys.path))
    saved = {name: sys.modules.pop(name, None) for name in SIBLINGS}
    try:
        check_exit(repo, base, scripts, lease, monkeypatch)
    finally:
        for name, module in saved.items():
            sys.modules.pop(name, None)
            if module is not None:
                sys.modules[name] = module


def check_exit(
    repo: Path,
    base: Path,
    scripts: Path,
    lease: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the trusted base's exit and evidence checks on the candidate."""
    head, base_sha = lease["head_sha"], lease["base_sha"]
    exit_reason = runpy.run_path(str(scripts / "self_hosted_evidence.py"))[
        "exit_reason"
    ]
    reason = exit_reason(repo, base / ".csarc/config.yml", lease)
    assert "from self-hosted to hosted (ADR Q1)" in reason
    monkeypatch.chdir(repo)
    require = runpy.run_path(str(scripts / "local_verification.py"))["require"]
    record = require(
        head_sha=head,
        tree_sha=git(repo, "rev-parse", "HEAD^{tree}"),
        base_ref="main",
        base_sha=base_sha,
        required_tier="fast",
    )
    assert record["trust"] == "self-attested-local"
