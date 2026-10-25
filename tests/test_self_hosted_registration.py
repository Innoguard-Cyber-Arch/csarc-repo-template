"""Linked registration for self-hosted mode (Issue #1270, ADR D7, Q5).

A pull request that switches to self-hosted or changes the registration
needs the governance-switch label and a `registration` URL that points at a
csarc-devops Issue. Only the URL format is checked: the template never reads
csarc-devops, because the VM enforces the registration itself. The check
prints its read-only inventory first (ADR D11) and runs in the trusted base,
for the local lifecycle and the hosted PR policy alike.
"""

from __future__ import annotations

import json
import runpy
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from test_base_policy import commit_all, config_text, git, write_config

ROOT = Path(__file__).resolve().parents[1]
COPIES = {
    "root": ROOT / "scripts/trusted_executor.py",
    "template": ROOT / "template/.csarc/scripts/trusted_executor.py",
}
LIFECYCLES = {
    "root": ROOT / "scripts/pr_lifecycle.py",
    "template": ROOT / "template/.csarc/scripts/pr_lifecycle.py",
}
DEVOPS = "https://github.com/acme/csarc-devops/issues/7"
OTHER = "https://github.com/acme/other-repo/issues/7"
LOCAL = {"verification_mode_private": "local"}
UNREGISTERED: dict[str, object] = {
    "verification_mode_private": "self-hosted",
    "self_hosted_runner": {},
    "self_hosted_environments": ["dev", "uat"],
}


def registered(url: str = DEVOPS, **extra: object) -> dict[str, object]:
    """Return self-hosted settings registered with one URL."""
    runner = {"id": "vm-01", "registration": url}
    return {**UNREGISTERED, "self_hosted_runner": runner, **extra}


def block_reads(monkeypatch: pytest.MonkeyPatch, namespace: dict) -> None:
    """Make every network or GitHub read fail the test."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"unexpected read: {args!r}")

    monkeypatch.setitem(namespace, "gh_api", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(subprocess, "run", refuse)


@pytest.mark.parametrize("name", COPIES)
@pytest.mark.parametrize(
    ("base", "candidate", "error"),
    [
        (LOCAL, registered(), None),
        (UNREGISTERED, registered(), None),
        (registered(), registered(self_hosted_environments=["uat"]), None),
        # Leaving self-hosted needs only the repository-side approval.
        (registered(), LOCAL, None),
        (LOCAL, UNREGISTERED, "registration: missing"),
        (registered(), UNREGISTERED, "registration: missing"),
        (LOCAL, registered(OTHER), "is not a csarc-devops Issue"),
        (LOCAL, registered("csarc-devops#7"), "is not a csarc-devops Issue"),
    ],
)
def test_registration_link_is_checked_by_format_only(
    name: str,
    base: dict[str, object],
    candidate: dict[str, object],
    error: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC1, AC2, AC4: the URL format decides, and nothing is read."""
    executor = runpy.run_path(str(COPIES[name]))
    check = executor["require_registration"]
    block_reads(monkeypatch, check.__globals__)
    if error is None:
        check(base, candidate, "#12")
    else:
        with pytest.raises(RuntimeError, match=error) as raised:
            check(base, candidate, "#12")
        assert "csarc-devops/issues/<n>" in str(raised.value)
    # AC3: the inventory comes first, with the Issue, the URL, and each
    # changed setting as old -> new.
    out = capsys.readouterr().out
    assert out.startswith("NOTICE: Self-hosted registration inventory")
    assert "- Issue: #12\n" in out
    runner = candidate.get("self_hosted_runner")
    url = runner.get("registration") if isinstance(runner, dict) else None
    assert f"- registration: {url or '-'}\n" in out
    assert "csarc-devops is not read" in out
    for key in ("verification_mode_private", *executor["GOVERNANCE_EXACT"]):
        if base.get(key) != candidate.get(key):
            assert f"- {key}: {base.get(key, '-')} -> " in out


@pytest.mark.parametrize("name", COPIES)
def test_unchanged_registration_prints_nothing(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ordinary pull requests keep their output unchanged."""
    check = runpy.run_path(str(COPIES[name]))["require_registration"]
    check(registered(), registered())
    check(LOCAL, {**LOCAL, "verification_mode_public": "local"})
    assert capsys.readouterr().out == ""


def self_hosted_text(runner: str) -> str:
    """Return a schema 2 file in self-hosted mode with one runner block."""
    return (
        config_text(
            verification_mode=None,
            verification_mode_private="self-hosted",
            verification_mode_public="hosted",
        )
        + runner
        + "self_hosted_environments:\n- dev\n- uat\n"
    )


def runner_text(url: str) -> str:
    """Return one registered runner block."""
    return f"self_hosted_runner:\n  id: vm-01\n  registration: {url}\n"


@pytest.mark.parametrize(
    ("runner", "labels", "error"),
    [
        (runner_text(DEVOPS), "governance-switch", None),
        (runner_text(DEVOPS), "", "'governance-switch' label"),
        ("self_hosted_runner: {}\n", "governance-switch", "missing"),
        (runner_text(OTHER), "governance-switch", "csarc-devops Issue URL"),
    ],
)
def test_hosted_route_enforces_the_registration(
    tmp_path: Path, runner: str, labels: str, error: str | None
) -> None:
    """AC1, AC4: the PR policy entry point fails closed on each gap."""
    base = write_config(tmp_path / "base.yml", config_text())
    candidate = write_config(tmp_path / "c.yml", self_hosted_text(runner))
    files = tmp_path / "files.json"
    files.write_text(json.dumps([[{"filename": ".csarc/config.yml"}]]))
    result = subprocess.run(  # noqa: S603 - repository-owned entry point
        [
            sys.executable,
            str(COPIES["root"]),
            "route",
            "--base-config",
            str(base),
            "--candidate-config",
            str(candidate),
            "--pull-files",
            str(files),
            "--labels",
            labels,
            "--enforce",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if error is None:
        assert result.returncode == 0, result.stderr
        assert f"- registration: {DEVOPS}" in result.stdout
    else:
        assert result.returncode == 1
        assert error in result.stderr


def switch_repository(tmp_path: Path, runner: str) -> tuple[Path, str, str]:
    """Build a generated-layout repository that switches to self-hosted."""
    repo = tmp_path / "generated"
    scripts = repo / ".csarc/scripts"
    scripts.mkdir(parents=True)
    for name in ("trusted_executor.py", "csarc_config.py", "ci_tier.py"):
        shutil.copy2(ROOT / "template/.csarc/scripts" / name, scripts / name)
    write_config(repo / ".csarc/config.yml", config_text())
    git(repo, "init", "-q", "-b", "main")
    base_sha = commit_all(repo, "base")
    git(repo, "switch", "-q", "-c", "feat/1270-switch")
    write_config(repo / ".csarc/config.yml", self_hosted_text(runner))
    return repo, base_sha, commit_all(repo, "switch")


@pytest.mark.parametrize("name", LIFECYCLES)
@pytest.mark.parametrize(
    ("runner", "error"),
    [
        (runner_text(DEVOPS), None),
        ("self_hosted_runner: {}\n", "registration: missing"),
    ],
)
def test_local_lifecycle_requires_the_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
    runner: str,
    error: str | None,
) -> None:
    """AC1-AC4: the merge decision prints the inventory, reads no GitHub."""
    repo, base_sha, head_sha = switch_repository(tmp_path, runner)
    trusted = tmp_path / "trusted"
    shutil.copytree(repo / ".csarc", trusted / ".csarc")
    (trusted / ".csarc/config.yml").write_text(config_text(), "utf-8")
    lifecycle: dict[str, Any] = runpy.run_path(str(LIFECYCLES[name]))
    decide = lifecycle["base_policy_decision"]
    monkeypatch.setitem(decide.__globals__, "repository_root", lambda: trusted)
    commands: list[list[str]] = []
    real_run = subprocess.run

    def recording_run(command: list[str], **kwargs: Any) -> Any:  # noqa: ANN401
        commands.append([str(part) for part in command])
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    monkeypatch.chdir(repo)
    lease = {"base_sha": base_sha, "head_sha": head_sha, "base_ref": "main"}
    pull = {"head": {"ref": "feat/1270-switch"}, "body": "Closes #12\n"}
    labels = {"governance-switch"}
    if error is None:
        assert decide(lease, pull, labels)["route"] == "governance-switch"
    else:
        with pytest.raises(RuntimeError, match=error):
            decide(lease, pull, labels)
    out = capsys.readouterr().out
    assert "- Issue: #12\n" in out
    assert "- verification_mode_private: hosted -> self-hosted\n" in out
    assert commands
    assert all(
        "csarc-devops" not in part and Path(command[0]).name != "gh"
        for command in commands
        for part in command
    )
