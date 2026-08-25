"""Tests for serialized pull-request lifecycle writes."""

from __future__ import annotations

import json
import runpy
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "pr_lifecycle.py")
)
acquire = MODULE["acquire"]
authorization = MODULE["authorization"]
authorization_statement = MODULE["authorization_statement"]
create_refs = MODULE["create_refs"]
GitHub = MODULE["GitHub"]
lease_message = MODULE["lease_message"]
merge = MODULE["merge"]
merge_snapshot = MODULE["merge_snapshot"]
read_lease = MODULE["read_lease"]
require_lease = MODULE["require_lease"]
require_successful_checks = MODULE["require_successful_checks"]
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
        self.authorization_type = "User"
        self.authorization_body: str | None = None
        self.permission = "maintain"
        self.merged = False
        self.base_ref = "main"
        self.base_sha = "b" * 40
        self.default_branch = "main"
        self.canonical_lease: dict[str, object] | None = None

    def viewer(self) -> str:
        """Return the task's authenticated actor."""
        return "agent"

    def pull(self) -> dict[str, Any]:
        """Return one live PR fixture."""
        return {
            "number": 42,
            "state": "closed" if self.merged else "open",
            "merged": self.merged,
            "merge_commit_sha": "d" * 40 if self.merged else None,
            "draft": self.draft,
            "title": "fix(ci): serialize lifecycle writes",
            "body": "Ready for review.",
            "base": {"ref": self.base_ref, "sha": self.base_sha},
            "head": {
                "ref": "dev/next",
                "sha": self.head,
                "repo": {"full_name": "owner/repo"},
            },
        }

    def get(self, _repo: str, path: str) -> object:
        """Return one REST fixture."""
        if path == "":
            return {"default_branch": self.default_branch}
        if path == "pulls/42":
            return self.pull()
        if path == "issues/comments/99":
            return {
                "html_url": (
                    "https://github.com/owner/repo/pull/42#issuecomment-99"
                ),
                "issue_url": "https://api.github.com/repos/owner/repo/issues/42",
                "author_association": "OWNER",
                "user": {
                    "login": self.authorization_actor,
                    "type": self.authorization_type,
                },
                "created_at": self.authorization_created_at,
                "body": self.authorization_body
                or authorization_statement("owner/repo", 42, self.head),
            }
        if path == f"collaborators/{self.authorization_actor}/permission":
            return {
                "permission": self.permission,
                "user": {"login": self.authorization_actor},
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
        if path == f"git/commits/{'a' * 40}":
            return {"sha": "a" * 40, "tree": {"sha": "e" * 40}}
        if path == f"git/commits/{'c' * 40}" and self.canonical_lease:
            return {
                "sha": "c" * 40,
                "message": lease_message(self.canonical_lease),
                "parents": [{"sha": "a" * 40}],
                "tree": {"sha": "e" * 40},
            }
        raise AssertionError(path)

    def collection(
        self,
        _repo: str,
        path: str,
        key: str,
        response_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return successful exact-head check fixtures."""
        assert response_sha in {None, self.head}
        if key == "check_runs" and path.startswith(f"commits/{self.head}/"):
            return [
                {
                    "name": "verify",
                    "head_sha": self.head,
                    "status": "completed",
                    "conclusion": "success",
                }
            ]
        if key == "statuses" and path.startswith(f"commits/{self.head}/"):
            return []
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

    def merge(
        self, _repo: str, _number: int, head_sha: str, _title: str
    ) -> dict[str, Any]:
        """Record one synchronous exact-head merge."""
        assert head_sha == self.head
        self.merged = True
        return {"merged": True, "sha": "d" * 40}


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
    second = SimpleNamespace(
        **{
            **vars(first),
            "owner": "task/draft",
            "output": tmp_path / "second.json",
        }
    )
    barrier = Barrier(2)
    original_create = create_refs

    def simultaneous_create(commit: str, refs: list[str]) -> None:
        barrier.wait(timeout=5)
        original_create(commit, refs)

    monkeypatch.setitem(acquire.__globals__, "create_refs", simultaneous_create)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(acquire, arguments, github)
            for arguments in (first, second)
        ]
    errors = [future.exception() for future in futures]
    assert sum(error is None for error in errors) == 1
    assert sum(isinstance(error, RuntimeError) for error in errors) == 1
    outputs = [path for path in (first.output, second.output) if path.exists()]
    assert len(outputs) == 1
    lease = read_lease(outputs[0])
    assert len(lease["refs"]) == 2
    assert github.audit_comments
    release_refs(lease)


def lease_fixture() -> dict[str, object]:
    """Return an unexpired in-memory lease."""
    acquired = datetime(2026, 8, 25, 1, 0, tzinfo=UTC)
    return {
        "schema_version": 1,
        "repository": "owner/repo",
        "pull_request": 42,
        "head_sha": "a" * 40,
        "head_tree": "e" * 40,
        "base_ref": "main",
        "base_sha": "b" * 40,
        "default_branch": "main",
        "owner": "task/merge",
        "actor": "agent",
        "nonce": "f" * 32,
        "acquired_at": acquired.isoformat().replace("+00:00", "Z"),
        "expires_at": (datetime.now(UTC) + timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z"),
        "lease_commit": "c" * 40,
        "refs": [
            "refs/heads/csarc/leases/pr-42",
            "refs/heads/csarc/leases/promotion",
        ],
        "audit_url": "https://github.com/owner/repo/pull/42#issuecomment-1",
    }


def bind_remote_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make remote ref checks observe the fixture lease."""
    monkeypatch.setitem(
        merge_snapshot.__globals__, "require_lease", lambda *_: None
    )


def bind_canonical_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make remote refs point to the canonical fixture commit."""
    monkeypatch.setitem(
        require_lease.__globals__, "require_origin", lambda _repo: None
    )
    monkeypatch.setitem(
        require_lease.__globals__, "remote_ref", lambda _ref: "c" * 40
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("owner", "task/attacker"),
        ("expires_at", "2099-01-01T00:00:00Z"),
    ],
)
def test_lease_evidence_must_match_the_remote_commit(
    field: str, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Editing owner or expiry cannot forge remote lease ownership."""
    bind_canonical_remote(monkeypatch)
    canonical = lease_fixture()
    github = FakeGitHub("a" * 40)
    github.canonical_lease = canonical
    tampered = {**canonical, field: value}
    with pytest.raises(RuntimeError, match="canonical evidence"):
        require_lease(github, tampered, "owner/repo", 42, "a" * 40)


@pytest.mark.parametrize("part", ["parent", "tree"])
def test_remote_lease_must_reuse_the_exact_head_commit(
    part: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A same-message commit cannot substitute another parent or tree."""
    bind_canonical_remote(monkeypatch)
    canonical = lease_fixture()
    github = FakeGitHub("a" * 40)
    github.canonical_lease = canonical
    original_get = github.get

    def tampered_get(repo: str, path: str) -> object:
        payload = original_get(repo, path)
        if path == f"git/commits/{'c' * 40}" and isinstance(payload, dict):
            payload = dict(payload)
            if part == "parent":
                payload["parents"] = [{"sha": "9" * 40}]
            else:
                payload["tree"] = {"sha": "9" * 40}
        return payload

    github.get = tampered_get  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="canonical evidence"):
        require_lease(github, canonical, "owner/repo", 42, "a" * 40)


def test_retargeting_to_default_requires_the_promotion_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A base retarget cannot change the lane covered by an active lease."""
    bind_canonical_remote(monkeypatch)
    canonical = lease_fixture()
    canonical["base_ref"] = "dev/next"
    canonical["refs"] = ["refs/heads/csarc/leases/pr-42"]
    github = FakeGitHub("a" * 40)
    github.canonical_lease = canonical
    with pytest.raises(RuntimeError, match="promotion lease scope drifted"):
        require_lease(github, canonical, "owner/repo", 42, "a" * 40)


@pytest.mark.parametrize(
    ("actor_type", "body"),
    [
        ("Bot", None),
        ("User", "Authorization revoked"),
    ],
)
def test_authorization_requires_an_exact_affirmative_human_statement(
    actor_type: str, body: str | None
) -> None:
    """Bot identities and non-affirmative text cannot authorize a merge."""
    github = FakeGitHub("a" * 40)
    github.authorization_type = actor_type
    github.authorization_body = body
    with pytest.raises(RuntimeError, match="exact maintainer statement"):
        authorization(
            github,
            "owner/repo",
            42,
            "a" * 40,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_authorization_requires_live_maintainer_permission() -> None:
    """A stale MEMBER association cannot replace live repository permission."""
    github = FakeGitHub("a" * 40)
    github.permission = "read"
    with pytest.raises(RuntimeError, match="lacks maintainer permission"):
        authorization(
            github,
            "owner/repo",
            42,
            "a" * 40,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_keyed_github_collections_flatten_every_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Required-check discovery cannot silently ignore later pages."""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> str:
        commands.append(command)
        return json.dumps(
            [
                {"check_runs": [{"name": "first"}]},
                {"check_runs": [{"name": "second"}]},
            ]
        )

    monkeypatch.setitem(GitHub.collection.__globals__, "run", fake_run)
    assert [
        item["name"]
        for item in GitHub().collection(
            "owner/repo", "commits/abc/check-runs?per_page=100", "check_runs"
        )
    ] == ["first", "second"]
    assert "--paginate" in commands[0]


def test_required_check_must_succeed_on_the_exact_head() -> None:
    """A successful check attached to another SHA cannot satisfy protection."""
    github = FakeGitHub("a" * 40)

    def stale_collection(
        _repo: str,
        _path: str,
        key: str,
        _response_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        if key == "check_runs":
            return [
                {
                    "name": "verify",
                    "head_sha": "f" * 40,
                    "status": "completed",
                    "conclusion": "success",
                }
            ]
        return []

    github.collection = stale_collection  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", "a" * 40, {("verify", None)}
        )


def test_required_check_must_match_its_pinned_github_app() -> None:
    """A same-name check from another integration cannot satisfy protection."""
    github = FakeGitHub("a" * 40)
    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", "a" * 40, {("verify", 1234)}
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


@pytest.mark.parametrize("marker", ["-", "*", "+"])
def test_all_markdown_list_markers_block_unchecked_items(
    marker: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every CommonMark bullet form preserves the checklist merge gate."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    original_pull = github.pull

    def unchecked_pull() -> dict[str, Any]:
        pull = original_pull()
        pull["body"] = f"{marker} [ ] unresolved"
        return pull

    github.pull = unchecked_pull  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="unchecked checklist"):
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


def test_merge_uses_synchronous_sha_bound_rest_and_confirms_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A merge cannot become queued auto-merge or target a later head."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    monkeypatch.setitem(
        merge.__globals__, "merge_snapshot", lambda *_: {"merge_mode": "agent"}
    )
    monkeypatch.setitem(merge.__globals__, "require_lease", lambda *_: None)
    released = False

    def record_release(_lease: dict[str, Any]) -> None:
        nonlocal released
        released = True

    monkeypatch.setitem(merge.__globals__, "release_refs", record_release)
    github = FakeGitHub("a" * 40)
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
        github,
    )
    assert github.merged
    assert released


def test_merge_does_not_release_a_lease_for_an_unconfirmed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ambiguous REST result remains locked for manual inspection."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    monkeypatch.setitem(
        merge.__globals__, "merge_snapshot", lambda *_: {"merge_mode": "agent"}
    )
    monkeypatch.setitem(merge.__globals__, "require_lease", lambda *_: None)
    monkeypatch.setitem(
        merge.__globals__,
        "release_refs",
        lambda _lease: pytest.fail("lease was released"),
    )
    github = FakeGitHub("a" * 40)
    github.merge = lambda *_: {"merged": False, "sha": None}  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="synchronously merge"):
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
            github,
        )
