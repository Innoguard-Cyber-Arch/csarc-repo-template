"""Tests for serialized pull-request lifecycle writes."""

from __future__ import annotations

import json
import runpy
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "pr_lifecycle.py")
)
acquire = MODULE["acquire"]
merge = MODULE["merge"]
merge_snapshot = MODULE["merge_snapshot"]
read_lease = MODULE["read_lease"]
release_refs = MODULE["release_refs"]
remote_repository = MODULE["remote_repository"]
_GIT = shutil.which("git")
if _GIT is None:
    raise RuntimeError("Git is required for PR lifecycle tests")
GIT: str = _GIT


class FakeGitHub:
    """Serve the mutable GitHub state needed by lifecycle tests."""

    def __init__(self, head: str) -> None:
        self.head = head
        self.draft = False
        self.authorization_created_at = "2026-08-25T01:01:00Z"
        self.authorization_actor = "maintainer"
        self.timeline: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self.reviews: list[dict[str, Any]] = [
            {
                "user": {"login": "reviewer"},
                "state": "APPROVED",
                "submitted_at": "2026-08-25T01:00:30Z",
            }
        ]
        self.audit_comments: list[str] = []
        self.protected = True

    def viewer(self) -> str:
        """Return the task's authenticated actor."""
        return "agent"

    def pull(self) -> dict[str, Any]:
        """Return one live PR fixture."""
        return {
            "number": 42,
            "state": "open",
            "merged": False,
            "draft": self.draft,
            "body": "Ready for review.",
            "base": {"ref": "main", "sha": "b" * 40},
            "head": {
                "ref": "dev/next",
                "sha": self.head,
                "repo": {"full_name": "owner/repo"},
            },
        }

    def get(self, _repo: str, path: str) -> object:
        """Return one REST fixture."""
        if path == "":
            return {"default_branch": "main"}
        if path == "pulls/42":
            return self.pull()
        if path == "issues/comments/99":
            binding = {
                "repository": "owner/repo",
                "pull_request": 42,
                "head_sha": self.head,
            }
            return {
                "html_url": (
                    "https://github.com/owner/repo/pull/42#issuecomment-99"
                ),
                "issue_url": "https://api.github.com/repos/owner/repo/issues/42",
                "author_association": "OWNER",
                "user": {"login": self.authorization_actor},
                "created_at": self.authorization_created_at,
                "body": (
                    "PR lifecycle merge authorization\n\n"
                    "`"
                    + json.dumps(binding, sort_keys=True, separators=(",", ":"))
                    + "`"
                ),
            }
        if path == "rules/branches/main":
            if not self.protected:
                raise RuntimeError("Upgrade to GitHub Pro")
            return [
                {
                    "type": "pull_request",
                    "ruleset_id": 7,
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
                    "ruleset_id": 7,
                    "parameters": {
                        "required_status_checks": [{"context": "verify"}]
                    },
                },
            ]
        if path == "rulesets/7":
            return {"enforcement": "active", "bypass_actors": []}
        raise AssertionError(path)

    def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
        """Return one paginated fixture."""
        if path.startswith("issues/42/timeline"):
            return self.timeline
        if path.startswith("issues/42/comments"):
            return self.comments
        if path.startswith("pulls/42/reviews"):
            return self.reviews
        raise AssertionError(path)

    def comment(self, _repo: str, _number: int, body: str) -> dict[str, Any]:
        """Record a lease audit comment."""
        self.audit_comments.append(body)
        return {
            "html_url": "https://github.com/owner/repo/pull/42#issuecomment-1"
        }


def git(path: Path, *arguments: str) -> str:
    """Run Git in one fixture repository."""
    return subprocess.run(  # noqa: S603
        [GIT, *arguments],
        cwd=path,
        text=True,
        check=True,
        capture_output=True,
    ).stdout.strip()


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
        "git@github.com:owner/repo.git",
    ],
)
def test_origin_must_resolve_to_the_exact_github_repository(url: str) -> None:
    """Common authenticated GitHub origin forms resolve safely."""
    assert remote_repository(url) == "owner/repo"


def test_236_concurrent_lifecycle_writer_cannot_acquire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A merge owner and concurrent Draft owner cannot hold the same PR."""
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
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "origin", f"{head}:refs/heads/main")
    monkeypatch.chdir(work)
    monkeypatch.setitem(
        acquire.__globals__, "remote_repository", lambda _url: "owner/repo"
    )
    github = FakeGitHub(head)
    first = SimpleNamespace(
        repo="owner/repo",
        pr_number=42,
        head_sha=head,
        owner="task/merge",
        ttl_seconds=600,
        output=tmp_path / "first.json",
    )
    acquire(first, github)
    lease = read_lease(first.output)
    assert len(lease["refs"]) == 2
    assert github.audit_comments

    second = SimpleNamespace(
        **{
            **vars(first),
            "owner": "task/draft",
            "output": tmp_path / "second.json",
        }
    )
    with pytest.raises(RuntimeError, match="already holds"):
        acquire(second, github)
    assert not second.output.exists()
    release_refs(lease)


def lease_fixture() -> dict[str, object]:
    """Return an unexpired in-memory lease."""
    acquired = datetime(2026, 8, 25, 1, 0, tzinfo=UTC)
    return {
        "schema_version": 1,
        "repository": "owner/repo",
        "pull_request": 42,
        "head_sha": "a" * 40,
        "owner": "task/merge",
        "actor": "agent",
        "acquired_at": acquired.isoformat().replace("+00:00", "Z"),
        "expires_at": (datetime.now(UTC) + timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z"),
        "lease_commit": "c" * 40,
        "refs": [
            "refs/heads/csarc/leases/pr-42",
            "refs/heads/csarc/leases/promotion",
        ],
    }


def bind_remote_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make remote ref checks observe the fixture lease."""
    monkeypatch.setitem(
        merge_snapshot.__globals__, "remote_ref", lambda _ref: "c" * 40
    )
    monkeypatch.setitem(
        merge_snapshot.__globals__, "require_origin", lambda _repo: None
    )


def test_236_newer_draft_event_invalidates_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Ready state cannot hide a concurrent post-authorization Draft event."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.timeline = [
        {"event": "convert_to_draft", "created_at": "2026-08-25T01:02:00Z"},
        {"event": "ready_for_review", "created_at": "2026-08-25T01:03:00Z"},
    ]
    with pytest.raises(RuntimeError, match="newer Draft event"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_237_unresolved_blocker_survives_ready_and_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later Ready or authorization does not erase a blocking comment."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.authorization_created_at = "2026-08-25T01:03:00Z"
    github.comments = [
        {
            "created_at": "2026-08-25T01:02:00Z",
            "body": (
                "Blocked: keep this PR Draft until the regression is fixed."
            ),
            "html_url": "https://github.com/owner/repo/pull/42#issuecomment-98",
            "author_association": "MEMBER",
        }
    ]
    github.timeline = [
        {"event": "ready_for_review", "created_at": "2026-08-25T01:04:00Z"}
    ]
    with pytest.raises(RuntimeError, match="unresolved blocking comment"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_merge_snapshot_allows_agent_only_with_enforced_no_bypass_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only enforced no-bypass protection permits an agent merge."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    snapshot = merge_snapshot(
        github,
        lease_fixture(),
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["merge_mode"] == "agent"
    github.protected = False
    snapshot = merge_snapshot(
        github,
        lease_fixture(),
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["merge_mode"] == "human-only"


def test_commented_review_does_not_clear_requested_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only approval or dismissal clears a review blocker."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews = [
        {
            "user": {"login": "Reviewer"},
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2026-08-25T01:01:30Z",
        },
        {
            "user": {"login": "independent"},
            "state": "APPROVED",
            "submitted_at": "2026-08-25T01:00:30Z",
        },
        {
            "user": {"login": "Reviewer"},
            "state": "COMMENTED",
            "submitted_at": "2026-08-25T01:02:00Z",
        },
    ]
    with pytest.raises(RuntimeError, match="reviewer"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_executing_actor_cannot_approve_its_own_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shared execution identity cannot also supply independent review."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews = [
        {
            "user": {"login": "agent"},
            "state": "APPROVED",
            "submitted_at": "2026-08-25T01:00:30Z",
        }
    ]
    with pytest.raises(RuntimeError, match="independent approving review"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_executing_actor_cannot_authorize_its_own_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared authorization and execution identity forces human-only mode."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.authorization_actor = "agent"
    snapshot = merge_snapshot(
        github,
        lease_fixture(),
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["merge_mode"] == "human-only"
    assert "executing GitHub actor" in snapshot["protection_reason"]


def test_untrusted_comment_cannot_resolve_a_maintainer_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a maintainer lifecycle marker can resolve a merge blocker."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.comments = [
        {
            "created_at": "2026-08-25T01:02:00Z",
            "body": "Blocked: a regression remains.",
            "html_url": "https://github.com/owner/repo/pull/42#issuecomment-97",
            "author_association": "MEMBER",
        },
        {
            "created_at": "2026-08-25T01:03:00Z",
            "body": "Merge blocker resolved: looks fine.",
            "html_url": "https://github.com/owner/repo/pull/42#issuecomment-98",
            "author_association": "NONE",
        },
    ]
    with pytest.raises(RuntimeError, match="unresolved blocking comment"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_tampered_lease_cannot_delete_an_arbitrary_ref(tmp_path: Path) -> None:
    """Edited evidence cannot turn release into an arbitrary ref delete."""
    payload = lease_fixture()
    payload["refs"] = ["refs/heads/main"]
    path = tmp_path / "lease.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="refs are invalid"):
        read_lease(path)


def test_merge_never_calls_gh_when_protection_is_degraded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Private Free or unknown protection fails before any merge mutation."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    monkeypatch.setitem(
        merge.__globals__,
        "merge_snapshot",
        lambda *_: {"merge_mode": "human-only"},
    )
    called = False

    def unexpected_run(_command: list[str], **_kwargs: object) -> str:
        nonlocal called
        called = True
        return ""

    monkeypatch.setitem(merge.__globals__, "run", unexpected_run)
    with pytest.raises(RuntimeError, match="human maintainer"):
        merge(
            SimpleNamespace(
                repo="owner/repo",
                pr_number=42,
                head_sha="a" * 40,
                owner="task/merge",
                lease=lease_path,
                authorization_url=(
                    "https://github.com/owner/repo/pull/42#issuecomment-99"
                ),
            ),
            FakeGitHub("a" * 40),
        )
    assert not called
