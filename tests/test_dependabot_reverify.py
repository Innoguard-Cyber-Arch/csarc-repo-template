"""Reverify behind Dependabot updates on the latest main (Issue #1264).

Template repository only: a conflict-free Dependabot head that falls behind
main is verified again on GitHub's test merge into the current main, and
lifecycle accepts that result instead of a rebase only on the Dependabot
path. Nothing here ships to `template/`.
"""

from __future__ import annotations

import runpy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from test_pr_lifecycle import (
    MODULE,
    DependabotGitHub,
    DependabotSyncChildGitHub,
    FakeGitHub,
    bind_canonical_remote,
    bind_remote_lease,
    human_review_mode,
    lease_fixture,
    merge_snapshot,
    patch_merge_boundary,
    require_lease,
    run_merge,
    traced_snapshot,
)

# Re-export the autouse fixture so this module pins the same review mode.
__all__ = ["human_review_mode"]

ROOT = Path(__file__).resolve().parents[1]
REVERIFY = runpy.run_path(str(ROOT / "scripts/dependabot_reverify.py"))
WORKFLOW = ROOT / ".github/workflows/dependabot-reverify.yml"
MERGE_WORKFLOW = ROOT / ".github/workflows/dependabot-merge.yml"
HEAD = "a" * 40
OLD_BASE = "b" * 40
MAIN = "1" * 40
MERGE = "2" * 40
TREE = "3" * 40
NUMBER = 42
REPO = "owner/repo"


def step_name(**overrides: object) -> str:
    """Return the execution claim the workflow step name renders."""
    values: dict[str, object] = {
        "pr": NUMBER,
        "head": HEAD,
        "main": MAIN,
        "merge": MERGE,
        "tree": TREE,
        "scopes": "dependency,source",
    }
    values.update(overrides)
    return (
        f"Execute Dependabot reverification pr={values['pr']} "
        f"head={values['head']} main={values['main']} "
        f"merge={values['merge']} tree={values['tree']} "
        f"scopes={values['scopes']} tier=full "
        "command=./scripts/verify-template.sh executor=trusted-base"
    )


class ReverifyGitHub:
    """Serve one trusted reverification run on the current main."""

    def __init__(self) -> None:
        self.main = MAIN
        self.conclusion = "success"
        self.path = ".github/workflows/dependabot-reverify.yml"
        self.event = "push"
        self.labels = ["ubuntu-latest"]
        self.completed_at = (
            datetime.now(UTC).replace(microsecond=0).isoformat()
        ).replace("+00:00", "Z")
        self.steps = [step_name()]
        self.comments: list[dict[str, Any]] = []
        self.posted: list[tuple[int, str]] = []
        self.pulls: dict[int, dict[str, Any]] = {}
        self.reviews: dict[int, list[dict[str, Any]]] = {}
        self.eligible: set[str] = set()

    def check(self) -> dict[str, Any]:
        return {
            "id": 77,
            "name": f"dependabot-reverify (#{NUMBER})",
            "head_sha": MAIN,
            "status": "completed",
            "conclusion": self.conclusion,
            "details_url": f"https://github.com/{REPO}/actions/runs/500/job/77",
            "app": {"id": 15368},
            "check_suite": {"id": 9500},
        }

    def collection(
        self, _repo: str, path: str, key: str
    ) -> list[dict[str, Any]]:
        if key == "check_runs" and path.startswith(f"commits/{self.main}/"):
            return [self.check()] if self.main == MAIN else []
        if key == "check_runs" and "dependabot-merge-eligible" in path:
            head = path.split("/")[1]
            return (
                [{"conclusion": "success", "app": {"id": 15368}}]
                if head in self.eligible
                else []
            )
        if key == "check_runs":
            return []
        if key == "jobs" and path.startswith("actions/runs/500/jobs"):
            return [
                {
                    "id": 77,
                    "name": f"dependabot-reverify (#{NUMBER})",
                    "head_sha": MAIN,
                    "html_url": self.check()["details_url"],
                    "conclusion": self.conclusion,
                    "labels": self.labels,
                    "runner_group_name": "GitHub Actions",
                    "completed_at": self.completed_at,
                    "steps": [
                        {"name": name, "conclusion": "success"}
                        for name in self.steps
                    ],
                }
            ]
        raise AssertionError(path)

    def get(self, _repo: str, path: str) -> object:
        if path == "actions/runs/500":
            return {
                "id": 500,
                "path": self.path,
                "event": self.event,
                "head_sha": MAIN,
                "head_branch": "main",
                "run_attempt": 1,
                "check_suite_id": 9500,
                "repository": {"full_name": REPO},
            }
        if path.startswith("pulls/"):
            return self.pulls[int(path.split("/")[1])]
        raise AssertionError(path)

    def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
        if path.startswith("pulls?state=open"):
            return list(self.pulls.values())
        if path.startswith("pulls/") and "/reviews" in path:
            return self.reviews.get(int(path.split("/")[1]), [])
        if path.startswith("pulls/") and "/commits" in path:
            title = self.pulls[int(path.split("/")[1])]["title"]
            return [{"commit": {"message": title}}]
        if path.startswith("issues/"):
            return self.comments
        raise AssertionError(path)

    def comment(self, _repo: str, number: int, body: str) -> dict[str, Any]:
        self.posted.append((number, body))
        self.comments.append({"body": body})
        return {"body": body}


def pull_fixture(
    number: int = NUMBER,
    head: str = HEAD,
    base: str = OLD_BASE,
    mergeable: object = True,
) -> dict[str, Any]:
    """Return one open same-repository Dependabot pull request."""
    return {
        "number": number,
        "title": "build(deps-dev): bump ty from 0.0.88 to 0.0.90",
        "state": "open",
        "commits": 1,
        "mergeable": mergeable,
        "user": {"login": "dependabot[bot]", "type": "Bot"},
        "base": {"ref": "main", "sha": base},
        "head": {
            "sha": head,
            "ref": f"dependabot/uv/main/routine-{number}",
            "repo": {"full_name": REPO},
        },
    }


# --- trusted reverification evidence (AC1, AC2, R1) -------------------------


def test_reverification_binds_head_main_and_merge_tree() -> None:
    """AC1: the run on the current main names the exact head and tree."""
    evidence = REVERIFY["require"](ReverifyGitHub(), REPO, NUMBER, HEAD, MAIN)

    assert evidence["main_sha"] == MAIN
    assert evidence["merge_sha"] == MERGE
    assert evidence["tree_sha"] == TREE
    assert evidence["scopes"] == ["dependency", "source"]


def test_reverification_expires_when_main_advances_again() -> None:
    """R1: a result on an older main never satisfies the newer main."""
    with pytest.raises(RuntimeError, match="none on main"):
        REVERIFY["require"](ReverifyGitHub(), REPO, NUMBER, HEAD, "9" * 40)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("conclusion", "failure", "did not pass"),
        ("path", ".github/workflows/ci.yml", "untrusted producer"),
        ("event", "pull_request", "untrusted producer"),
        ("labels", ["self-hosted", "ubuntu-latest"], "GitHub-hosted"),
        ("steps", [step_name(head="c" * 40)], "another head or main"),
        ("steps", [step_name(main="9" * 40)], "another head or main"),
        ("steps", [step_name(scopes="bogus")], "invalid scopes"),
        ("steps", [], "no single execution claim"),
        ("completed_at", "2026-01-01T00:00:00Z", "stale"),
    ],
)
def test_reverification_fails_closed(
    field: str, value: object, message: str
) -> None:
    """R1: a failed, foreign, self-hosted, stale, or other-head run blocks."""
    github = ReverifyGitHub()
    setattr(github, field, value)

    with pytest.raises(RuntimeError, match=message):
        REVERIFY["require"](github, REPO, NUMBER, HEAD, MAIN)


def test_payload_is_a_valid_hosted_record_for_the_merged_tree() -> None:
    """The durable evidence names the merged tree and the verified main."""
    evidence = REVERIFY["require"](ReverifyGitHub(), REPO, NUMBER, HEAD, MAIN)
    payload = REVERIFY["payload"](evidence, REPO, "e" * 40, OLD_BASE)
    record = MODULE["evidence_freshness"].normalized_record(
        payload, "github-hosted"
    )

    assert record["tree_sha"] == TREE
    assert record["base_sha"] == MAIN
    assert payload["dependabot_reverification"]["head_tree"] == "e" * 40
    assert payload["dependabot_reverification"]["pull_base_sha"] == OLD_BASE


# --- inventory, dedupe, and the conflict notice (AC1, AC3, R2) --------------


@pytest.mark.parametrize(
    ("pull", "approved", "eligible", "reverified", "state"),
    [
        (pull_fixture(base=MAIN), True, True, False, "current"),
        (pull_fixture(mergeable=False), True, True, False, "conflict"),
        (pull_fixture(mergeable=None), True, True, False, "pending"),
        (pull_fixture(), False, True, False, "waiting"),
        (pull_fixture(), True, False, False, "waiting"),
        ({**pull_fixture(), "commits": 2}, True, True, False, "waiting"),
        (pull_fixture(), True, True, True, "reverified"),
        (pull_fixture(), True, True, False, "reverify"),
    ],
)
def test_only_approved_eligible_conflict_free_heads_reverify(
    pull: dict[str, Any],
    approved: bool,
    eligible: bool,
    reverified: bool,
    state: str,
) -> None:
    """R2: reverification spends Actions only on ready, new candidates."""
    assert (
        REVERIFY["classify"](
            pull,
            MAIN,
            approved=approved,
            eligible=eligible,
            reverified=reverified,
        )
        == state
    )


def test_approval_must_be_the_latest_review_on_the_exact_head() -> None:
    """A stale-head or superseded approval does not select a candidate."""
    approve = {"user": {"login": "m"}, "state": "APPROVED", "commit_id": HEAD}
    assert REVERIFY["approved_head"]([approve], HEAD)
    assert not REVERIFY["approved_head"]([approve], "c" * 40)
    changes = {"user": {"login": "m"}, "state": "CHANGES_REQUESTED"}
    assert not REVERIFY["approved_head"]([approve, changes], HEAD)


def test_inventory_lists_every_pull_request_before_acting() -> None:
    """AC1/AC3: the read-only inventory selects one candidate per state."""
    github = ReverifyGitHub()
    github.main = "5" * 40
    approve = {"user": {"login": "m"}, "state": "APPROVED", "commit_id": HEAD}
    github.pulls = {
        NUMBER: pull_fixture(),
        43: pull_fixture(43, "c" * 40, mergeable=False),
        44: pull_fixture(44, "d" * 40, base="5" * 40),
        45: {**pull_fixture(45, "f" * 40), "title": "fix(deps): bump copier"},
    }
    approve_45 = {**approve, "commit_id": "f" * 40}
    github.reviews = {NUMBER: [approve], 45: [approve_45]}
    github.eligible = {HEAD, "f" * 40}

    rows = REVERIFY["inventory"](github, REPO, "5" * 40)
    states = {row["number"]: row["state"] for row in rows}

    assert states == {
        NUMBER: "reverify",
        43: "conflict",
        44: "current",
        45: "rebase",
    }
    table = REVERIFY["inventory_markdown"](rows, "5" * 40)
    assert "| #43 |" in table
    assert "conflict" in table


def test_conflict_notice_is_posted_once() -> None:
    """AC3: a conflicting pull request gets one notice, never a repeat."""
    github = ReverifyGitHub()

    assert REVERIFY["post_notices"](github, REPO, [NUMBER]) == [NUMBER]
    assert REVERIFY["post_notices"](github, REPO, [NUMBER]) == []
    assert len(github.posted) == 1
    assert REVERIFY["NOTICE_MARKER"] in github.posted[0][1]
    assert "@dependabot rebase" in github.posted[0][1]


@pytest.mark.parametrize(
    ("mutation", "parents"),
    [
        ({}, [MAIN, HEAD]),
        ({}, [OLD_BASE, HEAD]),
        ({"head": {"sha": "c" * 40}}, [MAIN, HEAD]),
        ({"mergeable": False}, [MAIN, HEAD]),
    ],
)
def test_bind_requires_the_test_merge_of_this_head_on_main(
    mutation: dict[str, Any], parents: list[str]
) -> None:
    """AC1: only GitHub's merge of the unchanged head into main is verified."""
    pull = {**pull_fixture(), **mutation}
    bind = REVERIFY["bind"]
    if not mutation and parents == [MAIN, HEAD]:
        bind(
            pull,
            NUMBER,
            HEAD,
            MAIN,
            MERGE,
            parents,
            ["build(deps-dev): bump ty from 0.0.88 to 0.0.90"],
        )
        return
    with pytest.raises(RuntimeError):
        bind(
            pull,
            NUMBER,
            HEAD,
            MAIN,
            MERGE,
            parents,
            ["build(deps-dev): bump ty from 0.0.88 to 0.0.90"],
        )


@pytest.mark.parametrize(
    ("title", "message"),
    [
        ("fix(deps): bump copier", "fix(deps): bump copier"),
        (
            "build(deps-dev): bump ty from 0.0.88 to 0.0.90",
            "fix(deps): bump copier",
        ),
        (
            "build(deps-dev): bump ty from 0.0.88 to 0.0.90",
            "build(deps): bump ty\n\nBREAKING CHANGE: drop 3.12",
        ),
        (
            "build(deps)!: bump ty",
            "build(deps-dev): bump ty from 0.0.88 to 0.0.90",
        ),
    ],
)
def test_only_no_release_heads_take_the_reverified_route(
    title: str, message: str
) -> None:
    """Review: a head with release intent waits for a Dependabot rebase."""
    pull = {**pull_fixture(), "title": title}
    with pytest.raises(RuntimeError, match="Wait for a Dependabot rebase"):
        REVERIFY["bind"](
            pull, NUMBER, HEAD, MAIN, MERGE, [MAIN, HEAD], [message]
        )
    assert (
        REVERIFY["classify"](
            pull,
            MAIN[:-1] + "9",
            approved=True,
            eligible=True,
            reverified=False,
            no_release=False,
        )
        == "rebase"
    )
    no_release = {
        **pull_fixture(),
        "title": "build(deps-dev): bump ty from 0.0.88 to 0.0.90",
    }
    REVERIFY["require_no_release"](
        no_release, ["build(deps-dev): bump ty from 0.0.88 to 0.0.90"]
    )


# --- lifecycle on the Dependabot path (AC2, AC5) -----------------------------


def reverification(main: str = MAIN) -> dict[str, Any]:
    """Return accepted reverification evidence on `main`."""
    return {
        "pull_request": NUMBER,
        "head_sha": HEAD,
        "main_sha": main,
        "merge_sha": MERGE,
        "tree_sha": TREE,
        "tier": "full",
        "scopes": ["dependency"],
        "command": "./scripts/verify-template.sh",
        "event": "push",
        "run_id": 500,
        "run_attempt": 1,
        "job_id": 77,
        "check_run_id": 77,
        "runner_labels": ["ubuntu-latest"],
        "completed_at": "2026-10-26T00:00:00Z",
    }


CALLS: dict[int, list[tuple[int, str, str]]] = {}


def no_release_title(
    monkeypatch: pytest.MonkeyPatch, github: DependabotGitHub
) -> None:
    """Give the fixture a no-release Dependabot title and commit."""
    original = github.pull

    def pull(number: int = NUMBER) -> dict[str, Any]:
        return {
            **original(number),
            "title": "build(deps-dev): bump ty from 0.0.88 to 0.0.90",
        }

    monkeypatch.setattr(github, "pull", pull)
    github.pull_commits = [
        {
            "commit": {
                "message": "build(deps-dev): bump ty from 0.0.88 to 0.0.90"
            }
        }
    ]


def behind_dependabot(
    monkeypatch: pytest.MonkeyPatch,
    require: object = None,
    github: DependabotGitHub | None = None,
) -> DependabotGitHub:
    """Return a Dependabot PR whose main advanced past its base."""
    bind_remote_lease(monkeypatch)
    github = github or DependabotGitHub()
    github.ruleset_response = {
        "enforcement": "active",
        "current_user_can_bypass": "never",
    }
    github.required_status_checks = [
        {"context": "verify", "integration_id": 15368}
    ]
    github.destination_sha = MAIN
    calls: list[tuple[int, str, str]] = []

    def accept(
        _github: object, _repo: str, number: int, head: str, main: str
    ) -> dict[str, Any]:
        calls.append((number, head, main))
        if main != MAIN:
            raise RuntimeError("Dependabot reverification: none on main.")
        return reverification(main)

    module = SimpleNamespace(
        require=require or accept,
        payload=REVERIFY["payload"],
        require_no_release=REVERIFY["require_no_release"],
    )
    no_release_title(monkeypatch, github)
    monkeypatch.setitem(
        merge_snapshot.__globals__, "dependabot_reverify", module
    )
    CALLS[id(github)] = calls
    return github


def test_behind_head_merges_with_reverification_on_current_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5: behind, conflict-free, and reverified on main is allowed."""
    github = behind_dependabot(monkeypatch)

    snapshot = merge_snapshot(
        github, lease_fixture(), require_dependabot_head=True
    )

    assert snapshot["merge_mode"] == "agent"
    assert snapshot["destination_sha"] == MAIN
    assert CALLS[id(github)] == [(NUMBER, HEAD, MAIN)]
    hosted = snapshot["hosted_verification"]
    assert isinstance(hosted, dict)
    assert hosted["tree_sha"] == TREE
    assert hosted["base_sha"] == MAIN
    target = MODULE["merge_target"](snapshot, lease_fixture())
    assert target == (MAIN, TREE)
    data, trust = MODULE["merge_evidence"](snapshot, lease_fixture())
    assert trust == "github-hosted"
    assert TREE.encode() in data


def test_behind_head_without_current_reverification_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5: no passing reverification on the current main blocks."""

    def missing(*_args: object) -> dict[str, Any]:
        raise RuntimeError("Dependabot reverification: none on main.")

    github = behind_dependabot(monkeypatch, missing)

    with pytest.raises(RuntimeError, match="none on main"):
        merge_snapshot(github, lease_fixture(), require_dependabot_head=True)


def test_behind_head_without_exact_approval_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5: a missing or stale-head approval still fails closed."""
    github = behind_dependabot(monkeypatch)
    github.reviews[0]["commit_id"] = "c" * 40

    with pytest.raises(RuntimeError, match="approval of the exact head"):
        merge_snapshot(github, lease_fixture(), require_dependabot_head=True)


def test_moved_head_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC5: a head that changed after the lease never merges."""
    github = behind_dependabot(monkeypatch)
    github.head = "c" * 40

    with pytest.raises(RuntimeError, match="head drifted"):
        merge_snapshot(github, lease_fixture(), require_dependabot_head=True)


def test_sync_child_heads_still_need_a_rebase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A materialized stable sync child is bound to its own base."""
    github = behind_dependabot(monkeypatch, github=DependabotSyncChildGitHub())
    lease = lease_fixture()
    lease["head_sha"] = github.head

    with pytest.raises(RuntimeError, match="only a direct"):
        merge_snapshot(github, lease, require_dependabot_head=True)


def test_reverification_is_hosted_mode_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Self-hosted and local projects keep the operator-driven route."""
    github = DependabotGitHub()
    monkeypatch.setitem(
        MODULE["reverified_destination"].__globals__,
        "configured_verification_mode",
        lambda *_: "local",
    )

    with pytest.raises(RuntimeError, match="hosted mode only"):
        MODULE["reverified_destination"](
            github, REPO, github.pull(), github.head, MAIN
        )


def test_ordinary_path_still_requires_the_current_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2/AC5: without the Dependabot path a newer main still blocks."""
    bind_canonical_remote(monkeypatch)
    canonical = lease_fixture()
    github = FakeGitHub(HEAD)
    github.canonical_lease = canonical
    github.destination_sha = MAIN

    with pytest.raises(RuntimeError, match="Destination branch: advanced"):
        require_lease(github, canonical, REPO, NUMBER, HEAD)
    require_lease(github, canonical, REPO, NUMBER, HEAD, MAIN)
    with pytest.raises(RuntimeError, match="Destination branch: advanced"):
        require_lease(github, canonical, REPO, NUMBER, HEAD, "9" * 40)


def test_ordinary_snapshot_ignores_a_reverification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5: a non-Dependabot snapshot never consults reverification."""
    github = behind_dependabot(monkeypatch)
    github.destination_sha = OLD_BASE

    snapshot = merge_snapshot(
        github, lease_fixture(), require_dependabot_head=True
    )

    assert snapshot["dependabot_reverification"] is None
    assert snapshot["destination_sha"] == OLD_BASE
    assert CALLS[id(github)] == []
    assert MODULE["merge_target"](snapshot, lease_fixture()) == (
        OLD_BASE,
        "e" * 40,
    )


class AcquireGitHub(DependabotGitHub):
    """Stop acquire right after its base check."""

    def get(self, _repo: str, path: str) -> object:
        if path == "":
            return {"default_branch": "main", "private": True}
        return super().get(_repo, path)


def acquire_args(**overrides: object) -> SimpleNamespace:
    """Return the acquire arguments used by the merge workflow."""
    values: dict[str, object] = {
        "repo": REPO,
        "pr_number": NUMBER,
        "head_sha": HEAD,
        "owner": "task/merge",
        "actor": "github-actions[bot]",
        "ttl_seconds": 900,
        "renew": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_acquire_refuses_a_behind_base_off_the_dependabot_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2: acquire keeps the base-equals-main rule for other callers."""
    acquire = MODULE["acquire"]
    monkeypatch.setitem(acquire.__globals__, "require_origin", lambda _r: None)
    github = AcquireGitHub()
    github.destination_sha = MAIN

    with pytest.raises(RuntimeError, match="base differs"):
        acquire(acquire_args(), github)

    def missing(*_args: object) -> dict[str, Any]:
        raise RuntimeError("Dependabot reverification: none on main.")

    monkeypatch.setitem(
        acquire.__globals__,
        "dependabot_reverify",
        SimpleNamespace(
            require=missing,
            require_no_release=REVERIFY["require_no_release"],
        ),
    )
    monkeypatch.setitem(
        MODULE["reverified_destination"].__globals__,
        "configured_verification_mode",
        lambda *_: "hosted",
    )
    with pytest.raises(RuntimeError, match="Wait for a Dependabot rebase"):
        acquire(acquire_args(require_dependabot_head=True), github)
    no_release_title(monkeypatch, github)
    with pytest.raises(RuntimeError, match="none on main"):
        acquire(acquire_args(require_dependabot_head=True), github)


def test_release_intent_head_is_refused_by_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review: a fix(deps) head never merges on the reverified route."""
    github = behind_dependabot(monkeypatch)
    github.pull_commits = [{"commit": {"message": "fix(deps): bump copier"}}]

    with pytest.raises(RuntimeError, match="release intent patch"):
        merge_snapshot(github, lease_fixture(), require_dependabot_head=True)
    assert CALLS[id(github)] == []


def reverified_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, parent: str, tree: str
) -> FakeGitHub:
    """Merge through the lifecycle with a reverified snapshot."""
    patch_merge_boundary(
        monkeypatch,
        traced_snapshot(
            dependabot_reverification=reverification(),
            hosted_verification=REVERIFY["payload"](
                reverification(), REPO, "e" * 40, OLD_BASE
            ),
            trailer_route="dependabot",
        ),
    )
    github = FakeGitHub(HEAD)
    github.destination_sha = MAIN
    github.merge_parent = parent
    github.merged_tree = tree
    github.commit_payloads[f"compare/{OLD_BASE}...{HEAD}"] = {"status": "ahead"}
    run_merge(tmp_path, github)
    return github


def test_reverified_merge_reads_back_the_verified_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The squash lands on the verified main with the verified tree."""
    github = reverified_merge(tmp_path, monkeypatch, MAIN, TREE)

    assert github.merged
    assert f"CSARC-Evidence-Tree: {TREE}" in github.merge_message


@pytest.mark.parametrize(
    ("parent", "tree"), [("9" * 40, TREE), (MAIN, "8" * 40)]
)
def test_unverified_reverified_merge_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, parent: str, tree: str
) -> None:
    """Review: main moving under the squash is detected, named, and loud."""
    with pytest.raises(RuntimeError) as error:
        reverified_merge(tmp_path, monkeypatch, parent, tree)

    message = str(error.value)
    assert message.startswith(f"Reverified Dependabot merge {'d' * 40}:")
    assert f"Verify {'d' * 40} on main, or revert it." in message


# --- workflows (AC1, AC3, R2) ------------------------------------------------


def load(path: Path) -> dict[str, Any]:
    """Load one workflow, keeping the `on` key."""
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    workflow["on"] = workflow.pop(True, workflow.get("on"))
    return workflow


def test_reverify_workflow_runs_when_main_or_checks_change() -> None:
    """AC1: main advancing or a Dependabot check completing wakes it."""
    workflow = load(WORKFLOW)

    assert workflow["on"]["push"] == {"branches": ["main"]}
    assert workflow["on"]["workflow_run"]["branches"] == ["dependabot/**"]
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert workflow["permissions"] == {}


def test_reverify_workflow_keeps_writes_minimal_and_serialized() -> None:
    """R2: one candidate at a time; only notice and dispatch can write."""
    jobs = load(WORKFLOW)["jobs"]

    assert jobs["inventory"]["permissions"] == {
        "actions": "read",
        "checks": "read",
        "contents": "read",
        "pull-requests": "read",
    }
    assert jobs["reverify"]["permissions"] == {
        "contents": "read",
        "pull-requests": "read",
    }
    assert jobs["reverify"]["strategy"]["max-parallel"] == 1
    assert jobs["notice"]["permissions"] == {
        "contents": "read",
        "pull-requests": "write",
    }
    assert jobs["dispatch"]["permissions"] == {
        "actions": "write",
        "checks": "read",
        "contents": "read",
    }
    assert "conflicts != '[]'" in jobs["notice"]["if"]


def test_reverify_job_checks_out_trusted_main_then_the_test_merge() -> None:
    """AC1: trusted main code verifies GitHub's merge; no branch is edited."""
    job = load(WORKFLOW)["jobs"]["reverify"]
    steps = job["steps"]
    refs = [
        step["with"]["ref"]
        for step in steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]

    assert job["name"] == "dependabot-reverify (#${{ matrix.number }})"
    assert refs == [
        "${{ needs.inventory.outputs.main_sha }}",
        "refs/pull/${{ matrix.number }}/merge",
    ]
    for step in steps:
        if str(step.get("uses", "")).startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] is False
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "git push" not in source
    assert "update-branch" not in source
    execute = next(
        step for step in steps if step["name"].startswith("Execute ")
    )
    rendered = (
        execute["name"]
        .replace("${{ matrix.number }}", str(NUMBER))
        .replace("${{ matrix.head_sha }}", HEAD)
        .replace("${{ needs.inventory.outputs.main_sha }}", MAIN)
        .replace("${{ steps.bind.outputs.merge }}", MERGE)
        .replace("${{ steps.bind.outputs.tree }}", TREE)
        .replace("${{ steps.bind.outputs.scopes }}", "dependency")
    )
    assert REVERIFY["STEP"].fullmatch(rendered)
    assert "trusted_executor.py" in execute["run"]


def test_merge_workflow_accepts_the_reverify_dispatch() -> None:
    """AC2: the dispatched merge proves the same identity through lifecycle."""
    workflow = load(MERGE_WORKFLOW)
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    steps = {step["name"]: step for step in workflow["jobs"]["merge"]["steps"]}

    assert set(inputs) == {"pr_number", "head_sha"}
    assert "workflow_dispatch" in workflow["jobs"]["resolve-pr"]["if"]
    assert (
        "--require-dependabot-head"
        in steps["Acquire the PR and destination lease"]["run"]
    )
    release = steps["Dispatch the repository-owned release flow"]["run"]
    # A reverified merge squashes another tree; release resolution would
    # refuse it, and its direct build(deps) head plans no release anyway.
    assert 'if [[ "$merged_tree" != "$head_tree" ]]; then' in release
    assert release.rstrip().endswith("--ref main")
    # A failed merge step (including an unverified reverified merge)
    # dispatches nothing further.
    dispatch = steps["Dispatch the repository-owned release flow"]
    assert dispatch["if"] == "${{ steps.merge.outcome == 'success' }}"


def test_reverify_job_never_saves_a_cache() -> None:
    """Review: candidate code on a main-ref event cannot poison a cache."""
    for step in load(WORKFLOW)["jobs"]["reverify"]["steps"]:
        uses = str(step.get("uses", ""))
        options = step.get("with") or {}
        assert not uses.startswith("actions/cache")
        assert options.get("cache") in (None, False), uses
        if uses.startswith("astral-sh/setup-uv@"):
            assert options["enable-cache"] is False
        if uses.startswith("actions/setup-node@"):
            assert options["package-manager-cache"] is False
        if uses.startswith("actions/setup-go@"):
            assert options["cache"] is False
