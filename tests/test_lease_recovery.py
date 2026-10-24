"""Tests for own-lease recovery and promotion Milestones (Issue #1252)."""

from __future__ import annotations

import hashlib
import runpy
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
# The live globals, so monkeypatching reaches the functions under test.
MODULES = {
    name: runpy.run_path(str(ROOT / path))["parser"].__globals__
    for name, path in (
        ("root", "scripts/pr_lifecycle.py"),
        ("template", "template/.csarc/scripts/pr_lifecycle.py"),
    )
}
GIT = shutil.which("git") or "git"
REPO = "owner/repo"


def git(path: Path, *arguments: str, stdin: str | None = None) -> str:
    """Run Git in one fixture repository."""
    return subprocess.run(  # noqa: S603
        [GIT, *arguments],
        cwd=path,
        input=stdin,
        text=True,
        check=True,
        capture_output=True,
    ).stdout.strip()


class FakeGitHub:
    """Serve the commits, pull request, Issue, and viewer a test needs."""

    def __init__(self) -> None:
        self.payloads: dict[str, object] = {}
        self.actor = "agent"

    def get(self, _repo: str, path: str) -> object:
        """Return one stored API payload."""
        return self.payloads.get(path)

    def viewer(self, explicit_actor: str = "") -> str:
        """Return the live authenticated actor."""
        return explicit_actor or self.actor


@pytest.fixture(params=sorted(MODULES))
def module(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Run each test against the root and the template copy."""
    return MODULES[request.param]


def leased_origin(
    module: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    owner: str = "task/merge",
) -> tuple[FakeGitHub, SimpleNamespace, dict[str, Any]]:
    """Push one canonical live lease to a real bare origin."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "init", str(work))
    git(work, "config", "user.name", "Lease Test")
    git(work, "config", "user.email", "lease@example.invalid")
    (work / "README.md").write_text("fixture\n", encoding="utf-8")
    git(work, "add", "README.md")
    git(work, "commit", "-m", "test: create fixture")
    head = git(work, "rev-parse", "HEAD")
    tree = git(work, "rev-parse", "HEAD^{tree}")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "origin", f"{head}:refs/heads/main")
    monkeypatch.chdir(work)
    monkeypatch.setitem(module, "remote_repository", lambda _url: REPO)
    acquired = datetime.now(UTC) - timedelta(minutes=1)
    core: dict[str, Any] = {
        "schema_version": module["LEASE_SCHEMA"],
        "repository": REPO,
        "pull_request": 42,
        "head_sha": head,
        "head_tree": tree,
        "base_ref": "main",
        "base_sha": head,
        "default_branch": "main",
        "owner": owner,
        "actor": "agent",
        "capability_digest": hashlib.sha256(b"secret").hexdigest(),
        "acquired_at": acquired.isoformat().replace("+00:00", "Z"),
        "expires_at": (acquired + timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z"),
        "refs": [module["pr_ref"](42), module["base_lane_ref"]("main")],
        "reclaimed_commits": [],
    }
    message = module["lease_message"](core)
    commit = git(work, "commit-tree", tree, "-p", head, stdin=f"{message}\n")
    for ref in core["refs"]:
        git(work, "push", "origin", f"{commit}:{ref}")
    github = FakeGitHub()
    github.payloads = {
        f"git/commits/{commit}": {
            "sha": commit,
            "message": message,
            "parents": [{"sha": head}],
            "tree": {"sha": tree},
        },
        f"git/commits/{head}": {"sha": head, "tree": {"sha": tree}},
        "pulls/42": {
            "number": 42,
            "state": "open",
            "merged": False,
            "head": {"sha": head},
        },
    }
    arguments = SimpleNamespace(
        repo=REPO,
        pr_number=42,
        head_sha=head,
        owner="task/merge",
        actor="",
        apply=False,
    )
    return github, arguments, {**core, "lease_commit": commit}


def test_recovery_inventories_then_releases_the_same_owner_lease(
    module: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC2: a dry run changes nothing; '--apply' frees both lease refs."""
    github, arguments, lease = leased_origin(module, tmp_path, monkeypatch)
    module["recover"](arguments, github)
    output = capsys.readouterr().out
    assert lease["lease_commit"] in output
    assert "Dry run only" in output
    assert all(
        module["remote_ref"](ref) == lease["lease_commit"]
        for ref in lease["refs"]
    )
    arguments.apply = True
    module["recover"](arguments, github)
    assert "OK: Lease released" in capsys.readouterr().out
    assert all(module["remote_ref"](ref) is None for ref in lease["refs"])


@pytest.mark.parametrize(
    "drift", ["owner", "actor", "head", "live_head", "not_canonical"]
)
def test_recovery_refuses_any_identity_or_canonical_mismatch(
    module: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    """R1: recovery fails closed unless every bound field matches."""
    github, arguments, lease = leased_origin(module, tmp_path, monkeypatch)
    arguments.apply = True
    if drift == "owner":
        arguments.owner = "task/other"
    elif drift == "actor":
        github.actor = "someone-else"
    elif drift == "head":
        arguments.head_sha = "f" * 40
    elif drift == "live_head":
        github.payloads["pulls/42"]["head"] = {"sha": "f" * 40}  # ty: ignore[invalid-assignment]
    else:
        commit = github.payloads[f"git/commits/{lease['lease_commit']}"]
        commit["message"] = "chore: lease PR #42\n\n{}"  # ty: ignore[invalid-assignment]
    with pytest.raises(RuntimeError):
        module["recover"](arguments, github)
    assert all(
        module["remote_ref"](ref) == lease["lease_commit"]
        for ref in lease["refs"]
    )


@pytest.mark.parametrize("owner", ["task/merge", "task/other"])
def test_acquire_names_the_same_owner_and_its_recovery_command(
    module: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    owner: str,
) -> None:
    """AC3: only the same owner learns its remaining time and the command."""
    github, _arguments, lease = leased_origin(
        module, tmp_path, monkeypatch, owner
    )
    with pytest.raises(RuntimeError) as error:
        module["expired_remote_lease"](
            github, REPO, lease["lease_commit"], lease["refs"][0], "task/merge"
        )
    if owner == "task/merge":
        assert "owner 'task/merge' holds it for" in str(error.value)
        assert "more seconds" in str(error.value)
        assert (
            f"run 'pr_lifecycle.py recover --repo {REPO} --pr-number 42 "
            f"--head-sha {lease['head_sha']} --owner task/merge'."
        ) in str(error.value)
    else:
        assert str(error.value) == (
            "PR lifecycle lease: held by another owner. Wait for its release."
        )


def promotion_github(title: str, milestone: int) -> FakeGitHub:
    """Serve one tracker Issue with its Milestone."""
    github = FakeGitHub()
    github.payloads["issues/1217"] = {
        "title": title,
        "milestone": {"number": milestone, "title": "Writing guides"},
    }
    return github


def test_promotion_routes_carry_the_validated_tracker_milestone(
    module: dict[str, Any],
) -> None:
    """AC1/R2: only a matching tracker supplies the promotion Milestone."""
    find = module["promotion_milestone"]
    body = "Refs #1217\n"
    github = promotion_github("Milestone 20: Writing guides", 20)
    assert find(github, REPO, "promote/m20-writing", body) == [
        "--milestone",
        "Writing guides",
    ]
    assert find(github, REPO, "fix/1252-lease", body) == []
    pull_request = promotion_github("Milestone 20: Writing guides", 20)
    pull_request.payloads["issues/1217"]["pull_request"] = {}  # ty: ignore[invalid-assignment]
    for wrong in (
        promotion_github("Milestone 19: Old", 20),
        promotion_github("Milestone 20: Writing guides", 19),
        pull_request,
    ):
        with pytest.raises(RuntimeError, match="no tracker reference"):
            find(wrong, REPO, "promote/m20-writing", body)
    with pytest.raises(RuntimeError, match="no tracker reference"):
        find(github, REPO, "promote/m20-writing", "Closes #1217\n")


def test_create_attaches_only_a_validated_promotion_milestone(
    module: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1: 'create' attaches the tracker Milestone or creates nothing."""
    head, head_ref = "a" * 40, "promote/m20-writing"
    body = tmp_path / "body.md"
    body.write_text("Refs #1217\n", encoding="utf-8")
    github = promotion_github("Milestone 20: Writing guides", 20)
    pull: dict[str, Any] = {
        "state": "open",
        "draft": True,
        "title": "feat: promote Milestone 20 delivery",
        "body": "Refs #1217\n",
        "head": {"ref": head_ref, "sha": head},
        "base": {"ref": "main"},
    }
    github.payloads["pulls/7"] = pull
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> str:
        calls.append(command)
        outputs = {
            "branch": head_ref,
            "rev-parse": head,
            "create": f"https://github.com/{REPO}/pull/7",
        }
        return outputs.get(
            command[1] if command[0] == "git" else command[2], ""
        )

    monkeypatch.setitem(module, "require_origin", lambda *_: None)
    monkeypatch.setitem(
        module,
        "branch_sha",
        lambda _github, _repo, branch: head if branch == head_ref else "b" * 40,
    )
    monkeypatch.setitem(module, "run", fake_run)
    arguments = SimpleNamespace(
        repo=REPO,
        base="main",
        head=head_ref,
        title=pull["title"],
        body_file=body,
    )
    module["create_draft_pull"](arguments, github)
    create = next(call for call in calls if call[:3] == ["gh", "pr", "create"])
    assert create[-2:] == ["--milestone", "Writing guides"]
    calls.clear()
    github.payloads["issues/1217"] = {"title": "Milestone 19: Old"}
    with pytest.raises(RuntimeError, match="no tracker reference"):
        module["create_draft_pull"](arguments, github)
    assert not [call for call in calls if call[:2] == ["gh", "pr"]]
