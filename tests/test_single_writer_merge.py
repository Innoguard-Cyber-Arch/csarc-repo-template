"""Tests for the audited single-maintainer merge route (Issue #1076)."""

from __future__ import annotations

import json
import runpy
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_pr_lifecycle import (
    ADMIN_BYPASS_MARKER,
    MODULE,
    DependabotGitHub,
    FakeGitHub,
    bind_remote_lease,
    edit_metadata,
    human_review_mode,
    lease_fixture,
    merge,
    merge_snapshot,
    traced_snapshot,
)

# Re-export the autouse fixture so this module pins the same review mode.
__all__ = ["human_review_mode"]

AUTHORIZATION_URL = "https://github.com/owner/repo/pull/42#issuecomment-99"
single_writer_eligibility = MODULE["single_writer_eligibility"]
declared_required_contexts = MODULE["declared_required_contexts"]
dependabot_update_scope = MODULE["dependabot_update_scope"]
require_local_dependabot_head = MODULE["require_local_dependabot_head"]
admin_bypass_marker_body = MODULE["admin_bypass_marker_body"]
merge_route = MODULE["merge_route"]
MERGE_ROUTES = MODULE["MERGE_ROUTES"]
merge_trace = MODULE["merge_trace"]


class WriterGitHub:
    """Serve only the collaborator, team, and deploy-key readback."""

    def __init__(self) -> None:
        self.owner_type: object = "User"
        self.collaborators: list[dict[str, Any]] = [
            {"login": "agent", "role_name": "admin"}
        ]
        self.keys: list[dict[str, Any]] = []
        self.teams: list[dict[str, Any]] = []
        self.team_members: dict[str, list[dict[str, Any]]] = {}
        self.failures: dict[str, Exception] = {}

    def get(self, _repo: str, path: str) -> object:
        """Return the repository payload."""
        assert path == ""
        if "repository" in self.failures:
            raise self.failures["repository"]
        return {"default_branch": "main", "owner": {"type": self.owner_type}}

    def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
        """Return one fully paginated repository collection."""
        name = path.split("?", 1)[0]
        if name in self.failures:
            raise self.failures[name]
        return {
            "collaborators": self.collaborators,
            "keys": self.keys,
            "teams": self.teams,
        }[name]

    def api_pages(self, endpoint: str) -> list[dict[str, Any]]:
        """Return one organization team's members."""
        slug = endpoint.split("/teams/", 1)[1].split("/", 1)[0]
        if slug not in self.team_members:
            raise RuntimeError("gh: Not Found (HTTP 404)")
        return self.team_members[slug]


def writer_stub(**changes: object) -> WriterGitHub:
    """Return a writer readback stub with selected fields replaced."""
    github = WriterGitHub()
    for name, value in changes.items():
        setattr(github, name, value)
    return github


@pytest.mark.parametrize(
    ("github", "expected"),
    [
        (writer_stub(), "eligible"),
        # A read-only collaborator is not a writer.
        (
            writer_stub(
                collaborators=[
                    {"login": "Agent", "role_name": "admin"},
                    {"login": "auditor", "role_name": "read"},
                    {"login": "triager", "role_name": "triage"},
                ],
                keys=[{"read_only": True}],
            ),
            "eligible",
        ),
        (
            writer_stub(
                collaborators=[
                    {"login": "agent", "role_name": "admin"},
                    {"login": "peer", "role_name": "write"},
                ]
            ),
            "multiple-writers",
        ),
        (writer_stub(keys=[{"read_only": False}]), "multiple-writers"),
        # Organization teams: visible read teams are fine.
        (
            writer_stub(
                owner_type="Organization",
                teams=[{"slug": "readers", "permission": "pull"}],
            ),
            "eligible",
        ),
        (
            writer_stub(
                owner_type="Organization",
                teams=[{"slug": "core", "permission": "push"}],
                team_members={"core": [{"login": "agent"}]},
            ),
            "eligible",
        ),
        # A hidden team: listed, but its members cannot be read.
        (
            writer_stub(
                owner_type="Organization",
                teams=[{"slug": "secret", "permission": "maintain"}],
            ),
            "inconclusive",
        ),
        # A team grants write to someone the collaborator list missed.
        (
            writer_stub(
                owner_type="Organization",
                teams=[{"slug": "core", "permission": "admin"}],
                team_members={"core": [{"login": "ghost"}]},
            ),
            "inconclusive",
        ),
        (
            writer_stub(
                owner_type="Organization",
                teams=[{"slug": "odd", "permission": "custom"}],
            ),
            "inconclusive",
        ),
        # Insufficient permission and incomplete pagination fail closed.
        (
            writer_stub(failures={"collaborators": RuntimeError("HTTP 403")}),
            "inconclusive",
        ),
        (
            writer_stub(
                failures={
                    "collaborators": RuntimeError(
                        "GitHub collection collaborators has invalid entries"
                    )
                }
            ),
            "inconclusive",
        ),
        (
            writer_stub(failures={"keys": RuntimeError("HTTP 403")}),
            "inconclusive",
        ),
        (
            writer_stub(
                owner_type="Organization",
                failures={"teams": json.JSONDecodeError("truncated", "", 0)},
            ),
            "inconclusive",
        ),
        (writer_stub(owner_type=None), "inconclusive"),
        # #1058 decision 6: no role_name or a custom role is never guessed.
        (
            writer_stub(
                collaborators=[{"login": "agent", "permission": "admin"}]
            ),
            "inconclusive",
        ),
        (
            writer_stub(
                collaborators=[{"login": "agent", "role_name": "release-bot"}]
            ),
            "inconclusive",
        ),
        (writer_stub(keys=[{"id": 1}]), "inconclusive"),
        # The only writer must be the merge actor itself.
        (
            writer_stub(
                collaborators=[{"login": "owner", "role_name": "admin"}]
            ),
            "inconclusive",
        ),
        (writer_stub(collaborators=[]), "inconclusive"),
    ],
)
def test_single_writer_eligibility_is_tri_state(
    github: WriterGitHub, expected: str
) -> None:
    """AC1/AC6: only a complete readback of one writer is eligible."""
    state, reason = single_writer_eligibility(github, "owner/repo", "agent")
    assert state == expected, reason
    assert reason


def test_incomplete_pagination_surfaces_as_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC6: a malformed paginated page never reads as a complete list."""
    github = MODULE["GitHub"]()
    monkeypatch.setitem(
        github.api_pages.__globals__,
        "run",
        lambda *_args, **_kwargs: json.dumps([[{"login": "agent"}], ["x"]]),
    )
    with pytest.raises(RuntimeError, match="invalid entries"):
        github.pages("owner/repo", "collaborators?affiliation=all")


def test_declared_required_contexts_come_from_the_base_policy() -> None:
    """AC3: hosted single-writer merges keep every declared required check."""
    assert declared_required_contexts() == {
        ("title", 15368),
        ("verify", 15368),
        ("review", 15368),
    }


class SingleWriterGitHub(FakeGitHub):
    """Serve a branch without any Ruleset and one observed writer."""

    def __init__(self) -> None:
        super().__init__("a" * 40)
        self.reviews = []
        self.head_ref = "fix/42-lifecycle"
        self.body = f"Closes #42\n\n{ADMIN_BYPASS_MARKER}"
        self.authorization_actor = "agent"
        self.permission = "admin"
        self.writers = writer_stub()

    def get(self, _repo: str, path: str) -> object:
        """Return no effective rules and the repository owner."""
        if path == "":
            return self.writers.get(_repo, path)
        if path == "rules/branches/main":
            return []
        return super().get(_repo, path)

    def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
        """Serve the writer readback beside the PR collections."""
        if path.split("?", 1)[0] in {"collaborators", "keys", "teams"}:
            return self.writers.pages(_repo, path)
        return super().pages(_repo, path)

    def api_pages(self, endpoint: str) -> list[dict[str, Any]]:
        """Serve organization team members."""
        return self.writers.api_pages(endpoint)


def use_local_mode(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Select local verification with exact-head local evidence."""
    for name, value in (
        ("configured_verification_mode", lambda: "local"),
        ("configured_admin_bypass", lambda: "always"),
        ("require_local_pull_policy", lambda *_: None),
    ):
        monkeypatch.setitem(merge_snapshot.__globals__, name, value)
    evidence: dict[str, object] = {
        "schema_version": 1,
        "trust": "self-attested-local",
        "success": True,
        "head_sha": "a" * 40,
        "tree_sha": "e" * 40,
        "base_ref": "main",
        "base_sha": "b" * 40,
        "tier": "fast",
        "scopes": ["source"],
        "command": "./scripts/verify-fast",
        "completed_at": "2026-10-14T00:00:00Z",
    }
    monkeypatch.setattr(
        MODULE["local_verification"], "require", lambda **_kwargs: evidence
    )
    return evidence


def test_local_single_writer_needs_no_extra_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1/AC2: the sole maintainer merges with server_enforcement=none."""
    bind_remote_lease(monkeypatch)
    evidence = use_local_mode(monkeypatch)
    github = SingleWriterGitHub()

    snapshot = merge_snapshot(github, lease_fixture(), AUTHORIZATION_URL)

    assert snapshot["protection"] == "single-writer"
    assert snapshot["server_enforcement"] == "none"
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["merge_permission"] == "allowed"
    assert snapshot["authorization_source"] == "comment"
    assert snapshot["authorization_actor"] == "agent"
    assert snapshot["local_verification"] == evidence
    assert snapshot["required_check_evidence"] == "local-self-attested"


@pytest.mark.parametrize(
    ("writers", "protection", "permission"),
    [
        (
            writer_stub(
                collaborators=[
                    {"login": "agent", "role_name": "admin"},
                    {"login": "peer", "role_name": "maintain"},
                ]
            ),
            "multiple-writers",
            "manual-only",
        ),
        (
            writer_stub(failures={"collaborators": RuntimeError("HTTP 403")}),
            "inconclusive",
            "manual-only",
        ),
    ],
)
def test_other_or_unobserved_writers_leave_a_manual_merge(
    monkeypatch: pytest.MonkeyPatch,
    writers: WriterGitHub,
    protection: str,
    permission: str,
) -> None:
    """AC1: another writer or an incomplete read never merges by agent."""
    bind_remote_lease(monkeypatch)
    use_local_mode(monkeypatch)
    github = SingleWriterGitHub()
    github.writers = writers

    snapshot = merge_snapshot(github, lease_fixture(), AUTHORIZATION_URL)

    assert snapshot["protection"] == protection
    assert snapshot["merge_mode"] == "human-only"
    assert snapshot["merge_permission"] == permission


@pytest.mark.parametrize("state", ["unstable", "blocked", "unknown", ""])
def test_single_writer_never_merges_an_unclean_pull_request(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    """AC5: without a Ruleset an `unstable` state is never mergeable."""
    bind_remote_lease(monkeypatch)
    use_local_mode(monkeypatch)
    github = SingleWriterGitHub()
    github.mergeable_state = state

    snapshot = merge_snapshot(github, lease_fixture(), AUTHORIZATION_URL)

    assert snapshot["protection"] == "blocked"
    assert snapshot["merge_permission"] == "blocked"
    assert snapshot["merge_mode"] == "human-only"


def test_hosted_single_writer_still_requires_declared_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3: no Ruleset never skips the hosted required checks."""
    bind_remote_lease(monkeypatch)
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "configured_verification_mode",
        lambda: "hosted",
    )
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "declared_required_contexts",
        lambda: {("verify", 15368), ("review", 15368)},
    )
    github = SingleWriterGitHub()

    snapshot = merge_snapshot(github, lease_fixture(), AUTHORIZATION_URL)

    assert snapshot["merge_mode"] == "agent"
    assert snapshot["hosted_verification"]

    github.check_conclusion = "failure"
    with pytest.raises(RuntimeError, match="verify"):
        merge_snapshot(github, lease_fixture(), AUTHORIZATION_URL)


@pytest.mark.parametrize(
    ("role", "identity", "mode"),
    [
        ("write", "agent-write", "agent"),
        ("maintain", "agent-maintain", "human-only"),
        ("admin", "agent-admin", "human-only"),
        ("release-bot", "agent-release-bot", "human-only"),
        (None, "agent-unknown", "human-only"),
    ],
)
def test_ruleset_agent_route_actor_must_hold_only_write(
    monkeypatch: pytest.MonkeyPatch,
    role: str | None,
    identity: str,
    mode: str,
) -> None:
    """AC2: the agent-route actor is write-only; unknown fails closed."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    original = github.get

    def role_get(repo: str, path: str) -> object:
        if path == "collaborators/agent/permission":
            # A missing role_name is unknown; the legacy field is ignored.
            payload: dict[str, object] = {
                "permission": "write",
                "user": {"login": "agent"},
            }
            if role is not None:
                payload["role_name"] = role
            return payload
        return original(repo, path)

    monkeypatch.setattr(github, "get", role_get)

    snapshot = merge_snapshot(github, lease_fixture())

    assert snapshot["server_enforcement"] == "ruleset"
    assert snapshot["authorization_source"] == "review"
    assert snapshot["authorization_actor"] == "reviewer"
    assert snapshot["merge_identity"] == identity
    assert snapshot["merge_mode"] == mode
    if mode != "agent":
        assert snapshot["merge_permission"] == "blocked"
        assert "independent write identity" in str(
            snapshot["protection_reason"]
        )


@pytest.mark.parametrize(
    ("role", "approver", "identity", "mode"),
    [
        ("maintain", "agent", "approver", "agent"),
        ("admin", "agent", "approver", "agent"),
        ("write", "agent", "agent-write", "agent"),
        # Only the approving account itself may merge with maintain/admin.
        ("maintain", "reviewer", "agent-maintain", "human-only"),
        ("triage", "agent", "agent-triage", "human-only"),
    ],
)
def test_1211_ruleset_route_accepts_the_independent_approver(
    role: str, approver: str, identity: str, mode: str
) -> None:
    """#1211 AC5: the approver may merge with maintain or admin."""

    class Role:
        def get(self, _repo: str, path: str) -> object:
            assert path == "collaborators/agent/permission"
            return {"role_name": role, "user": {"login": "agent"}}

    merge_identity = MODULE["merge_identity"]
    result = merge_identity(
        Role(), "o/r", "agent", "enforced", "review", approver
    )
    assert result[0] == identity
    assert bool(result[1]) is (mode != "agent")
    # Any other authorization source keeps the write-only agent route.
    if role != "write":
        assert merge_identity(
            Role(), "o/r", "agent", "enforced", "copilot", "agent"
        )[1]


def test_admin_bypass_route_runs_as_the_live_admin_authorizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2: admin bypass stays allowed and records its admin authorizer."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews = []
    github.required_review_count = 0
    github.head_ref = "fix/42-lifecycle"
    github.body = f"Closes #42\n\n{ADMIN_BYPASS_MARKER}"
    github.authorization_actor = "agent"
    github.permission = "admin"
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": MODULE["REVIEWED_MERGE_BYPASS_ACTORS"],
    }

    snapshot = merge_snapshot(github, lease_fixture(), AUTHORIZATION_URL)

    assert snapshot["merge_mode"] == "agent"
    assert snapshot["authorization_source"] == "comment"
    assert snapshot["authorization_actor"] == "agent"
    assert snapshot["merge_identity"] == "admin-authorizer"


def test_app_actor_and_non_agent_routes_skip_the_role_read() -> None:
    """AC2: an App has no repository role; refused states add no read."""

    class NoReads:
        def get(self, _repo: str, path: str) -> object:
            raise AssertionError(path)

    merge_identity = MODULE["merge_identity"]
    assert merge_identity(
        NoReads(), "o/r", "github-actions[bot]", "enforced", "review"
    ) == ("app", "")
    assert merge_identity(
        NoReads(), "o/r", "owner", "enforced", "hotfix-emergency"
    ) == ("admin-authorizer", "")
    assert merge_identity(
        NoReads(), "o/r", "owner", "single-writer", "comment"
    ) == ("sole-maintainer", "")
    assert merge_identity(
        NoReads(), "o/r", "owner", "independent-approval", "review"
    ) == ("independent-approval", "")
    assert merge_identity(NoReads(), "o/r", "a", "inconclusive", "review") == (
        "none",
        "",
    )


def test_every_protection_state_has_one_explicit_route() -> None:
    """AC3: each plan shape is allowed, manual-only, or blocked."""
    assert MERGE_ROUTES == {
        "enforced": "allowed",
        "single-writer": "allowed",
        "independent-approval": "allowed",
        "inconclusive": "manual-only",
        "multiple-writers": "manual-only",
        "unknown": "manual-only",
        "blocked": "blocked",
    }
    # A state nobody classified, including the raw `none`, never merges.
    assert merge_route("none") == "blocked"
    assert merge_route("surprise") == "blocked"


def run_traced_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    snapshot: dict[str, object],
) -> FakeGitHub:
    """Merge one fixture PR through the lifecycle with a fixed snapshot."""
    monkeypatch.setitem(
        merge.__globals__, "merge_snapshot", lambda *_: dict(snapshot)
    )
    for name in ("require_lease", "release_refs", "confirm_refs"):
        monkeypatch.setitem(merge.__globals__, name, lambda *_: None)
    monkeypatch.setitem(
        merge.__globals__, "revalidate_release_candidate", lambda *_: ""
    )
    github = FakeGitHub("a" * 40)
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    merge(
        SimpleNamespace(
            repo="owner/repo",
            pr_number=42,
            head_sha=github.head,
            owner="task/merge",
            lease=lease_path,
            authorization_url=AUTHORIZATION_URL,
        ),
        github,
    )
    return github


def test_single_writer_merge_keeps_the_g4_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3/R2: the trace states server_enforcement=none, never a Ruleset."""
    github = run_traced_merge(
        tmp_path,
        monkeypatch,
        traced_snapshot(
            server_enforcement="none",
            merge_permission="allowed",
            merge_identity="sole-maintainer",
        ),
    )
    summary = merge_trace.parse_summary(github.comment_edits[-1][1])
    assert summary.status == "merged"
    assert summary.lines[0].endswith(
        "actor=agent server_enforcement=none identity=sole-maintainer"
    )
    assert any(
        line.startswith(
            "single-writer-trace: writer=agent server_enforcement=none"
        )
        and "no Ruleset enforced this merge" in line
        for line in summary.lines
    )
    pairs = merge_trace.parse_trailers(github.merge_message)
    assert dict(pairs)["CSARC-Evidence-Tree"] == "e" * 40


@pytest.mark.parametrize(
    ("permission", "message"),
    [
        ("manual-only", "merge it manually, untraced"),
        ("blocked", "Fix the condition"),
    ],
)
def test_refused_routes_never_reach_the_merge_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    permission: str,
    message: str,
) -> None:
    """AC1/AC5: manual-only and blocked routes stop before any write."""
    with pytest.raises(RuntimeError, match=message):
        run_traced_merge(
            tmp_path,
            monkeypatch,
            traced_snapshot(
                merge_mode="human-only",
                merge_permission=permission,
                protection_reason="the writer readback is incomplete",
            ),
        )


GUIDANCE = (
    f"<!-- For admin bypass add one exact line: {ADMIN_BYPASS_MARKER} -->"
)
DEPENDABOT_MESSAGE = (
    "build(deps): bump copier from 9.18.1 to 9.18.2\n\n"
    "---\n"
    "updated-dependencies:\n"
    "- dependency-name: copier\n"
    "  dependency-version: 9.18.2\n"
    "  dependency-type: direct:development\n"
    "  update-type: {update_type}\n"
    "...\n\n"
    "Signed-off-by: dependabot[bot] <support@github.com>\n"
)


class LocalDependabotGitHub(DependabotGitHub):
    """Serve a signed Dependabot head without hosted eligibility checks."""

    def __init__(self) -> None:
        super().__init__()
        self.writers = writer_stub()
        self.reviews = []
        self.body = "Bumps copier."
        self.authorization_actor = "agent"
        self.additional_check_runs = []
        self.message = DEPENDABOT_MESSAGE.format(
            update_type="version-update:semver-patch"
        )

    def get(self, _repo: str, path: str) -> object:
        """Attach the signed message; serve no Ruleset and one writer."""
        if path == "":
            return self.writers.get(_repo, path)
        if path == "rules/branches/main":
            return []
        payload = super().get(_repo, path)
        if path == f"commits/{self.head}" and isinstance(payload, dict):
            payload["commit"]["message"] = self.message
        return payload

    def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
        """Serve the writer readback beside the PR collections."""
        if path.split("?", 1)[0] in {"collaborators", "keys", "teams"}:
            return self.writers.pages(_repo, path)
        return super().pages(_repo, path)


def test_local_dependabot_route_keeps_source_scope_and_release_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC4: the signed head, its update scope, and route are preserved."""
    bind_remote_lease(monkeypatch)
    use_local_mode(monkeypatch)
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "resolve_release_level",
        lambda *_: MODULE["release_level"].Decision(
            "beta", "self", "fast", "test"
        ),
    )
    github = LocalDependabotGitHub()

    snapshot = merge_snapshot(
        github,
        lease_fixture(),
        AUTHORIZATION_URL,
        require_dependabot_head=True,
    )

    assert snapshot["dependabot_head"] == "direct"
    assert snapshot["dependabot_update_scope"] == [
        "version-update:semver-patch"
    ]
    assert snapshot["trailer_route"] == "dependabot"
    assert snapshot["release_level"] == "beta"
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["server_enforcement"] == "none"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda github: setattr(github, "dependabot_author", "contributor"),
            "not authenticated",
        ),
        (
            lambda github: setattr(
                github,
                "message",
                DEPENDABOT_MESSAGE.format(
                    update_type="version-update:semver-major"
                ),
            ),
            "Review and merge it manually",
        ),
        (
            lambda github: setattr(github, "message", "bump copier"),
            "scope: missing",
        ),
        (
            lambda github: setattr(github, "head_ref", "fix/42-not-dependabot"),
            "identity: invalid",
        ),
    ],
)
def test_local_dependabot_route_refuses_a_mismatch(
    mutate: Callable[[LocalDependabotGitHub], None], message: str
) -> None:
    """AC4: an unknown, major, or impersonated head is never merged."""
    github = LocalDependabotGitHub()
    mutate(github)
    with pytest.raises(RuntimeError, match=message):
        require_local_dependabot_head(
            github, "owner/repo", github.pull(), github.head, github.base_sha
        )


def test_dependabot_update_scope_reads_every_dependency() -> None:
    """AC4: one major dependency in a group blocks the whole update."""
    grouped = DEPENDABOT_MESSAGE.format(
        update_type="version-update:semver-minor"
    ).replace(
        "...\n",
        "- dependency-name: ruff\n"
        "  update-type: version-update:semver-major\n...\n",
    )
    with pytest.raises(RuntimeError, match="semver-major"):
        dependabot_update_scope(grouped)


@pytest.mark.parametrize(
    ("body", "present", "expected"),
    [
        (
            f"Closes #1\n\n## 補充\n\n{GUIDANCE}\n",
            True,
            f"Closes #1\n\n## 補充\n\n{GUIDANCE}\n{ADMIN_BYPASS_MARKER}\n",
        ),
        ("Closes #1\n\n", True, f"Closes #1\n\n{ADMIN_BYPASS_MARKER}\n"),
        (
            f"Closes #1\n- {ADMIN_BYPASS_MARKER}\n{ADMIN_BYPASS_MARKER}  \n",
            True,
            f"Closes #1\n\n{ADMIN_BYPASS_MARKER}\n",
        ),
        (f"Closes #1\r\n{ADMIN_BYPASS_MARKER}\r\n", False, "Closes #1\n"),
    ],
)
def test_marker_body_holds_the_exact_marker_once(
    body: str, present: bool, expected: str
) -> None:
    """AC5: the managed edit inserts or updates exactly one marker line."""
    updated = admin_bypass_marker_body(body, present)
    assert updated == expected
    assert updated.splitlines().count(ADMIN_BYPASS_MARKER) == int(present)
    assert admin_bypass_marker_body(updated, present) == updated


def test_marker_edit_uses_the_leased_writer_and_reads_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC5: the marker is written only inside the lease and verified."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    github = FakeGitHub("a" * 40)
    github.body = "Closes #42\n"
    # The marker edit reads back the exact stored body.
    github.trace_evidence = False
    checks = 0

    def check_lease(*_arguments: object) -> None:
        nonlocal checks
        checks += 1

    def edit(
        command: list[str], *, input_text: str | None = None, **_kwargs: object
    ) -> str:
        assert command[-2:] == ["--body-file", "-"]
        github.body = input_text or ""
        return ""

    monkeypatch.setitem(edit_metadata.__globals__, "require_lease", check_lease)
    monkeypatch.setitem(edit_metadata.__globals__, "run", edit)
    arguments = SimpleNamespace(
        repo="owner/repo",
        pr_number=42,
        head_sha="a" * 40,
        owner="task/merge",
        lease=lease_path,
        body_file=None,
        admin_bypass_marker="add",
        add_label=[],
        remove_label=[],
        milestone=None,
        remove_milestone=False,
    )
    edit_metadata(arguments, github)
    assert checks == 2
    assert github.body.splitlines().count(ADMIN_BYPASS_MARKER) == 1

    # A readback that dropped the marker is never reported as success.
    def lossy(
        command: list[str], *, input_text: str | None = None, **_kwargs: object
    ) -> str:
        del command, input_text
        github.body = "Closes #42\n"
        return ""

    monkeypatch.setitem(edit_metadata.__globals__, "run", lossy)
    with pytest.raises(RuntimeError, match="did not change"):
        edit_metadata(arguments, github)

    arguments.body_file = tmp_path / "body.md"
    with pytest.raises(RuntimeError, match="conflict"):
        edit_metadata(arguments, github)


# Issue #1210: a private repository on GitHub Free cannot hold a Ruleset.
PLAN_UNSUPPORTED = (
    "Command failed: gh api repos/owner/repo/rules/branches/main: gh: "
    "Upgrade to GitHub Pro or make this repository public to enable this "
    "feature. (HTTP 403)"
)
TEMPLATE_MODULE = runpy.run_path(
    str(
        Path(__file__).resolve().parents[1]
        / "template/.csarc/scripts/pr_lifecycle.py"
    )
)


class RulesFailureGitHub:
    """Fail the effective-rules read with one exact error message."""

    def __init__(self, message: str) -> None:
        self.message = message

    def get(self, _repo: str, path: str) -> object:
        """Raise the configured error for the rules read."""
        assert path == "rules/branches/main"
        raise RuntimeError(self.message)


@pytest.mark.parametrize(
    "module", [MODULE, TEMPLATE_MODULE], ids=["root", "template"]
)
@pytest.mark.parametrize("local_mode", [False, True])
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (PLAN_UNSUPPORTED, "none"),
        # AC2: every other rules failure stays unknown, judged by content.
        (
            "Command failed: gh api repos/owner/repo/rules/branches/main: "
            "gh: Resource not accessible by integration (HTTP 403)",
            "unknown",
        ),
        (
            "Command failed: gh api repos/owner/repo/rules/branches/main: "
            "gh: Not Found (HTTP 404)",
            "unknown",
        ),
        (
            "Command failed: gh api repos/owner/repo/rules/branches/main: "
            "gh: Upgrade to GitHub Pro or make this repository public to "
            "enable this feature. (HTTP 404)",
            "unknown",
        ),
        (
            "Command failed: gh api repos/owner/repo/rules/branches/main: "
            "gh: Server Error (HTTP 502)",
            "unknown",
        ),
        (PLAN_UNSUPPORTED + "\nunexpected trailing output", "unknown"),
        ("HTTP 403", "unknown"),
    ],
)
def test_only_the_plan_unsupported_rules_answer_means_no_ruleset(
    module: dict[str, Any], local_mode: bool, message: str, expected: str
) -> None:
    """AC1/AC2/AC3: root and template classify rules failures alike."""
    protection, reason, contexts, *_flags = module["effective_protection"](
        RulesFailureGitHub(message), "owner/repo", "main", local_mode=local_mode
    )

    if expected == "unknown" and local_mode:
        expected = "inconclusive"
    assert protection == expected
    assert contexts == set()
    if expected == "none":
        assert "does not support Rulesets" in reason


class FreePrivateGitHub(SingleWriterGitHub):
    """Answer the rules read the way a private Free repository does."""

    def get(self, _repo: str, path: str) -> object:
        """Fail the rules read with GitHub's plan-unsupported 403."""
        if path == "rules/branches/main":
            raise RuntimeError(PLAN_UNSUPPORTED)
        return super().get(_repo, path)


def test_free_private_sole_writer_reaches_the_single_writer_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1: the plan-unsupported 403 still reaches the writer readback."""
    bind_remote_lease(monkeypatch)
    use_local_mode(monkeypatch)

    snapshot = merge_snapshot(
        FreePrivateGitHub(), lease_fixture(), AUTHORIZATION_URL
    )

    assert snapshot["protection"] == "single-writer"
    assert snapshot["server_enforcement"] == "none"
    assert snapshot["merge_identity"] == "sole-maintainer"
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["merge_permission"] == "allowed"


def test_free_private_with_two_writers_stays_manual_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1/R1: the plan answer never skips the exactly-one-writer rule."""
    bind_remote_lease(monkeypatch)
    use_local_mode(monkeypatch)
    github = FreePrivateGitHub()
    github.writers = writer_stub(
        collaborators=[
            {"login": "agent", "role_name": "admin"},
            {"login": "peer", "role_name": "write"},
        ]
    )

    snapshot = merge_snapshot(github, lease_fixture(), AUTHORIZATION_URL)

    assert snapshot["protection"] == "multiple-writers"
    assert snapshot["merge_mode"] == "human-only"
    assert snapshot["merge_permission"] == "manual-only"


MULTIPLE_WRITERS = {
    "collaborators": [
        {"login": "agent", "role_name": "write"},
        {"login": "reviewer", "role_name": "maintain"},
        {"login": "collaborator", "role_name": "write"},
    ]
}


def approved_multi_writer(github: SingleWriterGitHub) -> SingleWriterGitHub:
    """Serve a multi-writer branch whose head a maintainer approved."""
    github.reviews = FakeGitHub("a" * 40).reviews
    github.body = "Closes #42"
    github.head_committer = "collaborator"
    github.head_pusher = "collaborator"
    github.writers = writer_stub(**MULTIPLE_WRITERS)
    return github


def test_1211_multi_writer_merges_on_an_independent_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#1211 AC6: an exact-head approval replaces the sole-writer proof."""
    bind_remote_lease(monkeypatch)
    use_local_mode(monkeypatch)
    github = approved_multi_writer(SingleWriterGitHub())

    snapshot = merge_snapshot(github, lease_fixture())

    assert snapshot["protection"] == "independent-approval"
    assert snapshot["server_enforcement"] == "none"
    assert snapshot["merge_permission"] == "allowed"
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["merge_identity"] == "independent-approval"
    assert snapshot["authorization_source"] == "review"
    assert snapshot["authorization_actor"] == "reviewer"


@pytest.mark.parametrize(
    "case", ["no-approval", "pusher-approved", "incomplete", "unclean"]
)
def test_1211_multi_writer_without_independent_approval_stays_manual(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """#1211 AC6: without an independent approval nothing else changes."""
    bind_remote_lease(monkeypatch)
    use_local_mode(monkeypatch)
    github = approved_multi_writer(SingleWriterGitHub())
    if case == "no-approval":
        # Admin bypass authorization alone keeps the manual-only route.
        github.reviews = []
        github.body = f"Closes #42\n\n{ADMIN_BYPASS_MARKER}"
        github.authorization_actor = "agent"
        snapshot = merge_snapshot(github, lease_fixture(), AUTHORIZATION_URL)
        assert snapshot["protection"] == "multiple-writers"
        assert snapshot["merge_permission"] == "manual-only"
        return
    if case == "pusher-approved":
        github.head_pusher = "reviewer"
        with pytest.raises(RuntimeError, match="independent maintainer"):
            merge_snapshot(github, lease_fixture())
        return
    if case == "incomplete":
        github.writers = writer_stub(
            failures={"collaborators": RuntimeError("HTTP 403")}
        )
        expected = ("inconclusive", "manual-only")
    else:
        github.mergeable_state = "unstable"
        expected = ("blocked", "blocked")
    snapshot = merge_snapshot(github, lease_fixture())
    assert (snapshot["protection"], snapshot["merge_permission"]) == expected
    assert snapshot["merge_mode"] == "human-only"


def test_1211_private_free_multi_writer_merges_by_the_approver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#1211 AC6 with #1210: a Free private 403 means no Ruleset.

    The protection result is stubbed so this does not depend on #1210's
    detection code; the approver runs the lifecycle as the merge actor.
    """
    bind_remote_lease(monkeypatch)
    use_local_mode(monkeypatch)
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "effective_protection",
        lambda *_args, **_kwargs: (
            "none",
            "the Free private rules API returned 403 (no Ruleset, #1210)",
            set(),
            False,
            False,
        ),
    )
    github = approved_multi_writer(SingleWriterGitHub())
    github.authenticated_actor = "reviewer"
    github.actor_role = "maintain"
    lease = {**lease_fixture(), "actor": "reviewer"}

    snapshot = merge_snapshot(github, lease)

    assert snapshot["protection"] == "independent-approval"
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["merge_identity"] == "independent-approval"
    assert snapshot["authorization_actor"] == "reviewer"


def test_1211_independent_approval_merge_keeps_the_g4_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#1211 AC3/AC6: the trace names both the approver and the merger."""
    github = run_traced_merge(
        tmp_path,
        monkeypatch,
        traced_snapshot(
            protection="independent-approval",
            server_enforcement="none",
            merge_permission="allowed",
            merge_identity="independent-approval",
            authorization_actor="reviewer",
        ),
    )
    summary = merge_trace.parse_summary(github.comment_edits[-1][1])
    assert summary.status == "merged"
    assert summary.lines[0].endswith(
        "actor=agent server_enforcement=none identity=independent-approval"
    )
    assert any(
        line.startswith(
            "independent-approval-trace: approver=reviewer merger=agent "
            "server_enforcement=none"
        )
        for line in summary.lines
    )
    assert not any(
        line.startswith("single-writer-trace:") for line in summary.lines
    )
