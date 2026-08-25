"""Tests for delivery branch synchronization decisions."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "delivery_sync.py")
)
active_delivery_branches = MODULE["active_delivery_branches"]
capability_state = MODULE["capability_state"]
create_sync_pr = MODULE["create_sync_pr"]
gate = MODULE["gate"]
includes_main = MODULE["includes_main"]
manual_commands = MODULE["manual_commands"]
complete_dev_next = MODULE["complete_dev_next"]
prepare_dev_next = MODULE["prepare_dev_next"]
read_active_states = MODULE["read_active_states"]
reconcile = MODULE["reconcile"]
select_auto_mode = MODULE["select_auto_mode"]
sync_branch_name = MODULE["sync_branch_name"]

HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40
MAIN_SHA = "c" * 40


def promotion(*, merged: bool = False) -> dict[str, Any]:
    """Return one exact same-repository dev/next promotion."""
    return {
        "number": 42,
        "merged": merged,
        "state": "closed" if merged else "open",
        "merge_commit_sha": MAIN_SHA if merged else None,
        "base": {"ref": "main", "sha": BASE_SHA},
        "head": {
            "ref": "dev/next",
            "sha": HEAD_SHA,
            "repo": {"full_name": "acme/repo"},
        },
    }


class FakeAPI:
    """Return queued REST responses and record the requested paths."""

    def __init__(self, responses: list[tuple[int, Any]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, Any]:
        self.calls.append((method, path, payload))
        return self.responses.pop(0)


def test_active_delivery_branches_follow_open_milestones() -> None:
    """Keep dev/next and only Milestone branches whose Milestone is open."""
    refs = [
        {"ref": "refs/heads/dev/next", "object": {"sha": "next"}},
        {"ref": "refs/heads/dev/m7-ci", "object": {"sha": "seven"}},
        {"ref": "refs/heads/dev/m8-api", "object": {"sha": "eight"}},
        {"ref": "refs/heads/dev/i42-soak", "object": {"sha": "isolated"}},
        {"ref": "refs/heads/dev/not-a-milestone", "object": {"sha": "other"}},
    ]
    assert active_delivery_branches(refs, {7, 8}) == [
        ("dev/i42-soak", "isolated"),
        ("dev/m7-ci", "seven"),
        ("dev/m8-api", "eight"),
        ("dev/next", "next"),
    ]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("ahead", True),
        ("identical", True),
        ("behind", False),
        ("diverged", False),
    ],
)
def test_includes_main(status: str, expected: bool) -> None:
    """Interpret GitHub compare states conservatively."""
    assert includes_main(status) is expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (422, "allowed"),
        (403, "blocked"),
        (409, "blocked"),
        (500, "unknown"),
        (0, "unknown"),
    ],
)
def test_capability_state(status: int, expected: str) -> None:
    """Never infer write capability from an ambiguous response."""
    assert capability_state(status) == expected


@pytest.mark.parametrize(
    ("requested", "external", "pulls", "contents", "expected"),
    [
        (False, False, "unknown", "unknown", "manual"),
        (True, False, "allowed", "allowed", "manual"),
        (True, True, "blocked", "allowed", "manual"),
        (True, True, "unknown", "allowed", "manual"),
        (True, True, "allowed", "allowed", "automatic"),
    ],
)
def test_select_auto_mode(
    requested: bool,
    external: bool,
    pulls: str,
    contents: str,
    expected: str,
) -> None:
    """Require opt-in, event-producing credentials, and proven writes."""
    assert select_auto_mode(requested, external, pulls, contents) == expected


def test_gate_accepts_main_and_current_delivery_heads() -> None:
    """Main PRs are irrelevant; delivery PR heads must contain main."""
    api = FakeAPI([])
    assert gate(api, "acme/repo", "main", "head") == "not-applicable"
    assert not api.calls

    api = FakeAPI(
        [(200, {"object": {"sha": "main-sha"}}), (200, {"status": "ahead"})]
    )
    assert gate(api, "acme/repo", "dev/m7-ci", "head-sha") == "ahead"


def test_gate_rejects_a_stale_stacked_head() -> None:
    """Any non-main PR fails closed after main advances."""
    api = FakeAPI(
        [(200, {"object": {"sha": "main-sha"}}), (200, {"status": "diverged"})]
    )
    with pytest.raises(RuntimeError, match="does not contain current main"):
        gate(api, "acme/repo", "feat/41-parent", "head-sha")


def test_second_main_advance_invalidates_previous_success() -> None:
    """A new main SHA requires a fresh ancestry result."""
    first = FakeAPI(
        [(200, {"object": {"sha": "main-one"}}), (200, {"status": "ahead"})]
    )
    assert gate(first, "acme/repo", "dev/next", "head-sha") == "ahead"
    second = FakeAPI(
        [
            (200, {"object": {"sha": "main-two"}}),
            (200, {"status": "diverged"}),
        ]
    )
    with pytest.raises(RuntimeError, match="main-two"):
        gate(second, "acme/repo", "dev/next", "head-sha")


def test_manual_sync_is_deterministic_and_reviewed() -> None:
    """The fallback never pushes directly to an active delivery branch."""
    assert sync_branch_name("dev/m7-staged-ci", "abcdef0123456789") == (
        "sync/main-to-m7-staged-ci-abcdef012345"
    )
    commands = manual_commands("dev/m7-staged-ci", "abcdef0123456789")
    assert "git merge --no-ff origin/main" in commands
    assert "gh pr create --base dev/m7-staged-ci" in commands
    assert "git push origin dev/m7-staged-ci" not in commands


def test_promotion_gate_requires_verified_deletion_protection() -> None:
    """A direct promotion cannot merge while GitHub may delete dev/next."""
    protected = FakeAPI(
        [
            (200, promotion()),
            (200, {"object": {"sha": BASE_SHA}}),
            (200, {"object": {"sha": HEAD_SHA}}),
            (200, {"delete_branch_on_merge": True}),
            (200, [{"type": "deletion"}]),
        ]
    )
    assert (
        gate(
            protected,
            "acme/repo",
            "main",
            HEAD_SHA,
            head_ref="dev/next",
            pr_number=42,
        )
        == "deletion-protected"
    )

    api = FakeAPI(
        [
            (200, promotion()),
            (200, {"object": {"sha": BASE_SHA}}),
            (200, {"object": {"sha": HEAD_SHA}}),
            (200, {"delete_branch_on_merge": True}),
            (200, [{"type": "non_fast_forward"}]),
        ]
    )
    with pytest.raises(RuntimeError, match="can be auto-deleted"):
        gate(
            api,
            "acme/repo",
            "main",
            HEAD_SHA,
            head_ref="dev/next",
            pr_number=42,
        )


def test_prepare_rejects_a_closed_unmerged_pull_request() -> None:
    """A stale closed pull request cannot change repository cleanup."""
    pull = promotion()
    pull["state"] = "closed"
    api = FakeAPI([(200, pull)])
    with pytest.raises(RuntimeError, match="does not match"):
        prepare_dev_next(api, "acme/repo", 42, HEAD_SHA)
    assert not any(method == "PATCH" for method, _path, _body in api.calls)


@pytest.mark.parametrize("rules_status", [403, 500])
def test_prepare_fallback_is_explicit_and_idempotent(
    rules_status: int,
) -> None:
    """Blocked or unknown rule checks safely disable only the merge window."""
    responses = [
        (200, promotion()),
        (200, {"object": {"sha": BASE_SHA}}),
        (200, {"object": {"sha": HEAD_SHA}}),
        (200, {"delete_branch_on_merge": True}),
        (rules_status, {"message": "unavailable"}),
        (200, {"delete_branch_on_merge": False}),
        (200, {"delete_branch_on_merge": False}),
        (200, {"object": {"sha": BASE_SHA}}),
        (200, {"object": {"sha": HEAD_SHA}}),
    ]
    api = FakeAPI(responses)
    expected = "blocked" if rules_status == 403 else "unknown"
    assert prepare_dev_next(api, "acme/repo", 42, HEAD_SHA) == (
        f"temporary-auto-delete-disabled ({expected})"
    )
    assert (
        "PATCH",
        "repos/acme/repo",
        {"delete_branch_on_merge": False},
    ) in api.calls

    rerun = FakeAPI(
        [
            (200, promotion()),
            (200, {"object": {"sha": BASE_SHA}}),
            (200, {"object": {"sha": HEAD_SHA}}),
            (200, {"delete_branch_on_merge": False}),
        ]
    )
    assert prepare_dev_next(rerun, "acme/repo", 42, HEAD_SHA) == (
        "temporary-auto-delete-disabled"
    )
    assert not any(method == "PATCH" for method, _path, _body in rerun.calls)


def test_prepare_rolls_back_if_main_drifts() -> None:
    """A changed promotion context cannot leave repository cleanup disabled."""
    api = FakeAPI(
        [
            (200, promotion()),
            (200, {"object": {"sha": BASE_SHA}}),
            (200, {"object": {"sha": HEAD_SHA}}),
            (200, {"delete_branch_on_merge": True}),
            (200, []),
            (200, {"delete_branch_on_merge": False}),
            (200, {"delete_branch_on_merge": False}),
            (200, {"object": {"sha": "d" * 40}}),
            (200, {"delete_branch_on_merge": True}),
            (200, {"delete_branch_on_merge": True}),
        ]
    )
    with pytest.raises(RuntimeError, match="changed while enabling"):
        prepare_dev_next(api, "acme/repo", 42, HEAD_SHA)
    assert api.calls[-2] == (
        "PATCH",
        "repos/acme/repo",
        {"delete_branch_on_merge": True},
    )


def test_complete_restores_cleanup_and_is_idempotent() -> None:
    """Bind cleanup restoration to the merged PR, main, tree, and live ref."""
    evidence = [
        (200, promotion(merged=True)),
        (200, {"object": {"sha": MAIN_SHA}}),
        (200, {"object": {"sha": HEAD_SHA}}),
        (200, {"tree": {"sha": "tree"}}),
        (200, {"tree": {"sha": "tree"}}),
    ]
    api = FakeAPI(
        [
            *evidence,
            (200, {"delete_branch_on_merge": False}),
            (200, {"delete_branch_on_merge": True}),
            (200, {"delete_branch_on_merge": True}),
        ]
    )
    assert complete_dev_next(api, "acme/repo", 42, HEAD_SHA, MAIN_SHA) == (
        "auto-delete-restored"
    )

    rerun = FakeAPI([*evidence, (200, {"delete_branch_on_merge": True})])
    assert (
        complete_dev_next(rerun, "acme/repo", 42, HEAD_SHA, MAIN_SHA)
        == "auto-delete-already-enabled"
    )
    assert not any(method == "PATCH" for method, _path, _body in rerun.calls)


def test_complete_rejects_an_auto_deleted_dev_next() -> None:
    """A missing long-lived branch can never pass post-merge evidence."""
    api = FakeAPI(
        [
            (200, promotion(merged=True)),
            (200, {"object": {"sha": MAIN_SHA}}),
            (404, {"message": "Not Found"}),
        ]
    )
    with pytest.raises(RuntimeError, match="read dev/next failed"):
        complete_dev_next(api, "acme/repo", 42, HEAD_SHA, MAIN_SHA)


def test_delivery_reconcile_requires_dev_next() -> None:
    """An empty ref list cannot masquerade as synchronized delivery state."""
    api = FakeAPI([(200, []), (200, [])])
    with pytest.raises(RuntimeError, match="dev/next is missing"):
        read_active_states(api, "acme/repo", "main", require_dev_next=True)


def test_existing_sync_pr_deduplicates_same_main_sha() -> None:
    """Return the existing deterministic PR without another write."""
    api = FakeAPI([(200, [{"html_url": "https://example.test/pull/1"}])])
    assert (
        create_sync_pr(
            api, "acme/repo", "dev/m7-ci", "delivery", "abcdef0123456789"
        )
        == "https://example.test/pull/1"
    )
    assert len(api.calls) == 1


def test_conflict_stops_before_opening_a_pull_request() -> None:
    """Keep conflict resolution on the sync branch and fail closed."""
    api = FakeAPI(
        [
            (200, []),
            (404, {"message": "missing"}),
            (201, {"ref": "created"}),
            (409, {"message": "Merge conflict"}),
        ]
    )
    with pytest.raises(RuntimeError, match="resolve it on sync/main-to-m7-ci"):
        create_sync_pr(
            api, "acme/repo", "dev/m7-ci", "delivery", "abcdef0123456789"
        )
    assert not any(path.endswith("/pulls") for _, path, _ in api.calls[1:])


def test_reconcile_fans_out_with_capability_fallback() -> None:
    """Report every active stale branch when either write probe is blocked."""
    api = FakeAPI(
        [
            (
                200,
                [
                    {"ref": "refs/heads/dev/m7-ci", "object": {"sha": "seven"}},
                    {
                        "ref": "refs/heads/dev/m8-api",
                        "object": {"sha": "eight"},
                    },
                    {"ref": "refs/heads/dev/next", "object": {"sha": "next"}},
                ],
            ),
            (200, [{"number": 7}, {"number": 8}]),
            (200, {"status": "diverged"}),
            (200, {"status": "behind"}),
            (200, {"status": "diverged"}),
            (200, []),
            (422, {"message": "invalid head"}),
            (403, {"message": "blocked"}),
        ]
    )
    results = reconcile(
        api,
        "acme/repo",
        "main-two",
        auto_requested=True,
        external_token=True,
    )
    assert results[0].startswith("Sync mode: manual")
    assert any("dev/m7-ci is diverged" in result for result in results)
    assert any("dev/m8-api is behind" in result for result in results)
    assert any("dev/next is diverged" in result for result in results)
