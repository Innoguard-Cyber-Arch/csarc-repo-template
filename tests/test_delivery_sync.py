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
label_sync_pr = MODULE["label_sync_pr"]
manual_commands = MODULE["manual_commands"]
reconcile = MODULE["reconcile"]
select_auto_mode = MODULE["select_auto_mode"]
sync_branch_name = MODULE["sync_branch_name"]


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


def test_new_sync_pr_labels_only_through_the_lifecycle_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Creating a PR never writes its label outside the common lease tool."""
    api = FakeAPI(
        [
            (200, []),
            (404, {"message": "missing"}),
            (201, {"ref": "created"}),
            (201, {"sha": "merge"}),
            (
                201,
                {
                    "number": 17,
                    "html_url": "https://github.com/acme/repo/pull/17",
                    "head": {"sha": "a" * 40},
                },
            ),
        ]
    )
    labelled: list[tuple[str, int, str]] = []
    monkeypatch.setitem(
        create_sync_pr.__globals__,
        "label_sync_pr",
        lambda repo, number, sha: labelled.append((repo, number, sha)),
    )
    assert (
        create_sync_pr(
            api, "acme/repo", "dev/m7-ci", "delivery", "abcdef0123456789"
        )
        == "https://github.com/acme/repo/pull/17"
    )
    assert labelled == [("acme/repo", 17, "a" * 40)]
    assert not any("/labels" in path for _, path, _ in api.calls)


def test_lifecycle_label_always_releases_its_exact_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed metadata edit does not strand the workflow lease."""
    commands: list[list[str]] = []

    def command(arguments: list[str]) -> None:
        commands.append(arguments)
        if arguments[0] == "edit":
            raise RuntimeError("edit failed")

    monkeypatch.setitem(label_sync_pr.__globals__, "lifecycle_command", command)
    with pytest.raises(RuntimeError, match="edit failed"):
        label_sync_pr("acme/repo", 17, "a" * 40)
    assert [arguments[0] for arguments in commands] == [
        "acquire",
        "edit",
        "release",
    ]


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
