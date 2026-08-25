"""Tests for delivery branch synchronization decisions."""

from __future__ import annotations

import json
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
abort_dev_next = MODULE["abort_dev_next"]
append_preservation_record = MODULE["append_preservation_record"]
merge_group_gate = MODULE["merge_group_gate"]
prepare_dev_next = MODULE["prepare_dev_next"]
preservation_operation = MODULE["preservation_operation"]
read_active_states = MODULE["read_active_states"]
reconcile = MODULE["reconcile"]
select_auto_mode = MODULE["select_auto_mode"]
sync_branch_name = MODULE["sync_branch_name"]

HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40
MAIN_SHA = "c" * 40
LEDGER_SHA = "d" * 40


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


class PromotionAPI:
    """Model mutable promotion refs and repository cleanup settings."""

    def __init__(
        self,
        *,
        merged: bool = False,
        setting: bool = True,
        rules_status: int = 200,
        rules: list[dict[str, object]] | None = None,
        missing_dev_next: bool = False,
        drift_after_patch: bool = False,
    ) -> None:
        self.merged = merged
        self.setting = setting
        self.rules_status = rules_status
        self.rules = rules if rules is not None else []
        self.missing_dev_next = missing_dev_next
        self.drift_after_patch = drift_after_patch
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, Any]:
        self.calls.append((method, path, payload))
        if method == "GET" and path == "repos/acme/repo/pulls/42":
            return 200, promotion(merged=self.merged)
        if method == "GET" and path == "repos/acme/repo/git/ref/heads/main":
            main = (
                "e" * 40
                if self.drift_after_patch and self.setting is False
                else MAIN_SHA
                if self.merged
                else BASE_SHA
            )
            return 200, {"object": {"sha": main}}
        if (
            method == "GET"
            and path == "repos/acme/repo/git/ref/heads/dev%2Fnext"
        ):
            if self.missing_dev_next:
                return 404, {"message": "Not Found"}
            return 200, {"object": {"sha": HEAD_SHA}}
        if method == "GET" and path == "repos/acme/repo":
            return 200, {"delete_branch_on_merge": self.setting}
        if method == "GET" and path.endswith("/rules/branches/dev%2Fnext"):
            return self.rules_status, self.rules
        if method == "GET" and path in {
            f"repos/acme/repo/git/commits/{HEAD_SHA}",
            f"repos/acme/repo/git/commits/{MAIN_SHA}",
        }:
            return 200, {"tree": {"sha": "tree"}}
        if method == "PATCH" and path == "repos/acme/repo":
            assert payload is not None
            self.setting = bool(payload["delete_branch_on_merge"])
            return 200, {"delete_branch_on_merge": self.setting}
        raise AssertionError((method, path, payload))


class MemoryLedger:
    """Provide an in-memory append-only ledger for transaction tests."""

    def __init__(
        self, checkpoint: tuple[str, dict[str, Any]] | None = None
    ) -> None:
        self.checkpoint = checkpoint
        self.counter = 13

    def read(
        self, _api: object, _repo: str
    ) -> tuple[str, dict[str, Any]] | None:
        return self.checkpoint

    def append(
        self,
        _api: object,
        _repo: str,
        previous: str | None,
        record: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        assert previous == (self.checkpoint[0] if self.checkpoint else None)
        commit = f"{self.counter:040x}"
        self.counter += 1
        self.checkpoint = commit, record
        return self.checkpoint


def preservation_record(
    *, state: str = "prepared", mode: str = "temporary-auto-delete"
) -> dict[str, Any]:
    """Return one exact ledger record for the promotion fixture."""
    return {
        "schema_version": 1,
        "repository": "acme/repo",
        "pull_request": 42,
        "base_ref": "main",
        "base_sha": BASE_SHA,
        "head_ref": "dev/next",
        "head_sha": HEAD_SHA,
        "operation_id": preservation_operation(
            "acme/repo", 42, BASE_SHA, HEAD_SHA
        ),
        "mode": mode,
        "prior_auto_delete": True,
        "state": state,
    }


def install_memory_ledger(
    monkeypatch: pytest.MonkeyPatch, ledger: MemoryLedger
) -> None:
    """Route transaction helpers through one deterministic ledger."""
    monkeypatch.setitem(
        prepare_dev_next.__globals__, "read_preservation_record", ledger.read
    )
    monkeypatch.setitem(
        prepare_dev_next.__globals__,
        "append_preservation_record",
        ledger.append,
    )


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


def test_promotion_gate_requires_owned_disabled_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repository-wide false setting is insufficient without its ledger."""
    api = PromotionAPI(setting=False)
    monkeypatch.setitem(
        gate.__globals__, "read_preservation_record", lambda *_: None
    )
    with pytest.raises(
        RuntimeError, match="without a preservation transaction"
    ):
        gate(
            api,
            "acme/repo",
            "main",
            HEAD_SHA,
            head_ref="dev/next",
            pr_number=42,
        )


def test_promotion_gate_accepts_only_the_exact_prepared_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The temporary setting is accepted only for its current remote owner."""
    record = preservation_record()
    monkeypatch.setitem(
        gate.__globals__,
        "read_preservation_record",
        lambda *_: (LEDGER_SHA, record),
    )
    api = PromotionAPI(setting=False)
    result = gate(
        api,
        "acme/repo",
        "main",
        HEAD_SHA,
        head_ref="dev/next",
        pr_number=42,
    )
    assert str(record["operation_id"]) in result
    assert LEDGER_SHA in result


def test_merge_group_revalidates_one_exact_promotion() -> None:
    """A queue candidate is rebound to one live same-repository promotion."""
    queue_sha = "f" * 40
    queue_ref = "refs/heads/gh-readonly-queue/main/pr-42-deadbeef"
    queue_branch = "gh-readonly-queue%2Fmain%2Fpr-42-deadbeef"
    api = FakeAPI(
        [
            (200, {"object": {"sha": queue_sha}}),
            (200, [{"number": 42}]),
            (200, promotion()),
            (200, promotion()),
            (200, {"object": {"sha": BASE_SHA}}),
            (200, {"object": {"sha": HEAD_SHA}}),
            (200, {"status": "ahead"}),
            (200, {"status": "ahead"}),
            (200, {"delete_branch_on_merge": True}),
            (200, [{"type": "deletion"}]),
        ]
    )
    assert (
        merge_group_gate(
            api,
            "acme/repo",
            queue_ref,
            queue_sha,
            "refs/heads/main",
            BASE_SHA,
        )
        == "deletion-protected"
    )
    assert api.calls[0][1].endswith(queue_branch)


def test_merge_group_rejects_ambiguous_associated_pulls() -> None:
    """Never guess which associated pull request supplied a queue commit."""
    queue_sha = "f" * 40
    api = FakeAPI(
        [
            (200, {"object": {"sha": queue_sha}}),
            (200, [{"number": 42}, {"number": 43}]),
        ]
    )
    with pytest.raises(RuntimeError, match="no unique pull request"):
        merge_group_gate(
            api,
            "acme/repo",
            "refs/heads/gh-readonly-queue/main/pr-42-deadbeef",
            queue_sha,
            "refs/heads/main",
            BASE_SHA,
        )


def test_merge_group_rejects_an_associated_pull_on_page_two() -> None:
    """Pagination cannot hide a second PR associated with the queue commit."""
    queue_sha = "f" * 40
    first_page = [{"number": 42}] + [
        {"number": number} for number in range(100, 199)
    ]
    api = FakeAPI(
        [
            (200, {"object": {"sha": queue_sha}}),
            (200, first_page),
            (200, [{"number": 43}]),
        ]
    )
    with pytest.raises(RuntimeError, match="no unique pull request"):
        merge_group_gate(
            api,
            "acme/repo",
            "refs/heads/gh-readonly-queue/main/pr-42-deadbeef",
            queue_sha,
            "refs/heads/main",
            BASE_SHA,
        )
    assert any("page=2" in path for _method, path, _payload in api.calls)


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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blocked rule checks create one durable transaction before mutation."""
    api = PromotionAPI(rules_status=rules_status)
    ledger = MemoryLedger()
    install_memory_ledger(monkeypatch, ledger)
    evidence = json.loads(prepare_dev_next(api, "acme/repo", 42, HEAD_SHA))
    assert evidence["transaction"]["state"] == "prepared"
    assert evidence["transaction"]["prior_auto_delete"] is True
    assert evidence["transaction"]["mode"] == "temporary-auto-delete"
    assert api.setting is False
    assert (
        "PATCH",
        "repos/acme/repo",
        {"delete_branch_on_merge": False},
    ) in api.calls

    api.calls.clear()
    assert (
        json.loads(prepare_dev_next(api, "acme/repo", 42, HEAD_SHA)) == evidence
    )
    assert not any(method == "PATCH" for method, _path, _body in api.calls)


def test_prepare_rejects_external_disabled_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never adopt a repository-wide setting changed outside a transaction."""
    ledger = MemoryLedger()
    install_memory_ledger(monkeypatch, ledger)
    api = PromotionAPI(setting=False, rules_status=403)
    with pytest.raises(RuntimeError, match="outside this transaction"):
        prepare_dev_next(api, "acme/repo", 42, HEAD_SHA)
    assert ledger.checkpoint is None


def test_prepare_rolls_back_if_main_drifts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A changed promotion context cannot leave repository cleanup disabled."""
    ledger = MemoryLedger()
    install_memory_ledger(monkeypatch, ledger)
    api = PromotionAPI(drift_after_patch=True)
    with pytest.raises(RuntimeError, match="changed while enabling"):
        prepare_dev_next(api, "acme/repo", 42, HEAD_SHA)
    assert api.setting is True


def test_complete_restores_cleanup_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bind cleanup restoration to the merged PR, main, tree, and live ref."""
    prepared = preservation_record()
    ledger = MemoryLedger((LEDGER_SHA, prepared))
    install_memory_ledger(monkeypatch, ledger)
    api = PromotionAPI(merged=True, setting=False)
    operation = str(prepared["operation_id"])
    evidence = json.loads(
        complete_dev_next(
            api,
            "acme/repo",
            42,
            HEAD_SHA,
            MAIN_SHA,
            operation,
            LEDGER_SHA,
        )
    )
    assert evidence["transaction"]["state"] == "completed"
    assert evidence["transaction"]["prepared_ledger_commit"] == LEDGER_SHA
    assert api.setting is True

    api.calls.clear()
    assert (
        json.loads(
            complete_dev_next(
                api,
                "acme/repo",
                42,
                HEAD_SHA,
                MAIN_SHA,
                operation,
                LEDGER_SHA,
            )
        )
        == evidence
    )
    assert not any(method == "PATCH" for method, _path, _body in api.calls)


def test_complete_rejects_another_operation_without_restoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller cannot use another transaction to restore repository policy."""
    prepared = preservation_record()
    ledger = MemoryLedger((LEDGER_SHA, prepared))
    install_memory_ledger(monkeypatch, ledger)
    api = PromotionAPI(merged=True, setting=False)
    with pytest.raises(RuntimeError, match="another promotion"):
        complete_dev_next(
            api,
            "acme/repo",
            42,
            HEAD_SHA,
            MAIN_SHA,
            "f" * 64,
            LEDGER_SHA,
        )
    assert api.setting is False
    assert not any(method == "PATCH" for method, _path, _body in api.calls)


def test_complete_rejects_an_auto_deleted_dev_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing long-lived branch can never pass post-merge evidence."""
    prepared = preservation_record()
    ledger = MemoryLedger((LEDGER_SHA, prepared))
    install_memory_ledger(monkeypatch, ledger)
    api = PromotionAPI(merged=True, setting=False, missing_dev_next=True)
    with pytest.raises(RuntimeError, match="read dev/next failed"):
        complete_dev_next(
            api,
            "acme/repo",
            42,
            HEAD_SHA,
            MAIN_SHA,
            str(prepared["operation_id"]),
            LEDGER_SHA,
        )


def test_abort_only_restores_the_owned_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A closed unmerged PR can recover an interrupted owned mutation."""
    prepared = preservation_record(state="preparing")
    ledger = MemoryLedger((LEDGER_SHA, prepared))
    install_memory_ledger(monkeypatch, ledger)
    api = PromotionAPI(setting=False)
    closed = promotion()
    closed["state"] = "closed"
    api.request = lambda method, path, payload=None: (
        (200, closed)
        if method == "GET" and path.endswith("/pulls/42")
        else PromotionAPI.request(api, method, path, payload)
    )
    result = json.loads(
        abort_dev_next(
            api,
            "acme/repo",
            42,
            HEAD_SHA,
            str(prepared["operation_id"]),
        )
    )
    assert result["transaction"]["state"] == "aborted"
    assert api.setting is True


def test_ledger_create_collision_fails_closed() -> None:
    """A create-ref conflict never pretends to own the transaction."""
    api = FakeAPI(
        [
            (201, {"sha": "blob"}),
            (201, {"sha": "tree"}),
            (201, {"sha": "commit"}),
            (422, {"message": "Reference already exists"}),
        ]
    )
    with pytest.raises(RuntimeError, match="changed concurrently"):
        append_preservation_record(
            api, "acme/repo", None, preservation_record(state="preparing")
        )


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
