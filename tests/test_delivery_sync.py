"""Tests for delivery branch synchronization decisions."""

from __future__ import annotations

import re
import runpy
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "delivery_sync.py")
)
capability_state = MODULE["capability_state"]
create_sync_pr = MODULE["create_sync_pr"]
gate = MODULE["gate"]
includes_main = MODULE["includes_main"]
label_sync_pr = MODULE["label_sync_pr"]
manual_commands = MODULE["manual_commands"]
merge_group_gate = MODULE["merge_group_gate"]
promotion_source = MODULE["promotion_source"]
read_delivery_state = MODULE["read_delivery_state"]
reconcile = MODULE["reconcile"]
require_sync_request = MODULE["require_sync_request"]
select_auto_mode = MODULE["select_auto_mode"]
sync_branch_name = MODULE["sync_branch_name"]

HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40


def promotion(head_ref: str = "dev/m7-ci") -> dict[str, Any]:
    """Return one exact same-repository main candidate."""
    return {
        "number": 42,
        "merged": False,
        "state": "open",
        "merge_commit_sha": None,
        "body": "Closes #42",
        "labels": [{"name": "promotion"}],
        "user": {"login": "owner"},
        "base": {"ref": "main", "sha": BASE_SHA},
        "head": {
            "ref": head_ref,
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


def sync_pull(
    main_sha: str,
    *,
    base: str = "dev/m7-ci",
    merged_at: str | None = "2026-08-25T05:49:23Z",
) -> dict[str, Any]:
    """Return REST evidence for one deterministic reviewed sync PR."""
    return {
        "number": 283,
        "state": "closed",
        "merged_at": merged_at,
        "merge_commit_sha": "squash-sha",
        "base": {"ref": base},
        "head": {
            "ref": sync_branch_name(base, main_sha),
            "sha": "sync-head-sha",
        },
    }


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


def test_gate_skips_ordinary_work_and_checks_final_promotion() -> None:
    """Ordinary Milestone work waits until the final promotion to sync."""
    api = FakeAPI([])
    assert (
        gate(
            api,
            "acme/repo",
            "dev/m7-ci",
            "head",
            head_ref="feat/42-change",
        )
        == "not-applicable"
    )
    assert not api.calls

    api = FakeAPI(
        [(200, {"object": {"sha": "main-sha"}}), (200, {"status": "ahead"})]
    )
    assert (
        gate(
            api,
            "acme/repo",
            "main",
            "head-sha",
            head_ref="dev/m7-ci",
        )
        == "ahead"
    )


def test_promotion_source_maps_direct_and_bridge_routes() -> None:
    """Only main-bound Milestone candidates select a delivery source."""
    assert promotion_source("main", "dev/m7-ci") == "dev/m7-ci"
    assert promotion_source("main", "promote/m7-ci") == "dev/m7-ci"
    assert promotion_source("main", "dev/i42-soak") == "dev/i42-soak"
    assert promotion_source("dev/m7-ci", "feat/42-change") is None
    assert promotion_source("main", "feat/42-change") is None


def test_gate_accepts_verified_squash_sync_for_a_stacked_head() -> None:
    """Accept a reviewed sync squash only when its content is in the head."""
    main_sha = "a" * 40
    api = FakeAPI(
        [
            (200, {"object": {"sha": main_sha}}),
            (200, {"status": "diverged"}),
            (200, [sync_pull(main_sha)]),
            (200, {"status": "ahead"}),
            (200, {"status": "ahead"}),
        ]
    )

    assert (
        gate(
            api,
            "acme/repo",
            "main",
            "proposed-head",
            head_ref="dev/m7-ci",
        )
        == "squash-sync-pr-283"
    )
    assert "state=closed" in api.calls[2][1]
    assert "head=acme%3Async%2Fmain-to-m7-ci-aaaaaaaaaaaa" in api.calls[2][1]
    assert "base=dev%2Fm7-ci" in api.calls[2][1]


@pytest.mark.parametrize(
    "pull",
    [
        sync_pull("a" * 40, merged_at=None),
        sync_pull("a" * 40, base="dev/m8-other"),
        sync_pull("b" * 40),
    ],
    ids=("unmerged", "wrong-base", "previous-main"),
)
def test_gate_rejects_unrelated_sync_pull_evidence(
    pull: dict[str, Any],
) -> None:
    """Reject unmerged, wrong-base, and previous-main sync pull requests."""
    api = FakeAPI(
        [
            (200, {"object": {"sha": "a" * 40}}),
            (200, {"status": "diverged"}),
            (200, [pull]),
        ]
    )
    with pytest.raises(RuntimeError, match="verified reviewed sync squash"):
        gate(
            api,
            "acme/repo",
            "main",
            "proposed-head",
            head_ref="dev/m7-ci",
        )


def test_gate_rejects_sync_branch_without_current_main() -> None:
    """A deterministic branch name cannot replace commit ancestry proof."""
    main_sha = "a" * 40
    api = FakeAPI(
        [
            (200, {"object": {"sha": main_sha}}),
            (200, {"status": "diverged"}),
            (200, [sync_pull(main_sha)]),
            (200, {"status": "diverged"}),
        ]
    )
    with pytest.raises(RuntimeError, match="verified reviewed sync squash"):
        gate(
            api,
            "acme/repo",
            "main",
            "proposed-head",
            head_ref="dev/m7-ci",
        )


def test_gate_rejects_head_without_sync_squash_commit() -> None:
    """A reviewed sync does not cover a head missing its squash commit."""
    main_sha = "a" * 40
    api = FakeAPI(
        [
            (200, {"object": {"sha": main_sha}}),
            (200, {"status": "diverged"}),
            (200, [sync_pull(main_sha)]),
            (200, {"status": "ahead"}),
            (200, {"status": "diverged"}),
        ]
    )
    with pytest.raises(RuntimeError, match="verified reviewed sync squash"):
        gate(
            api,
            "acme/repo",
            "main",
            "proposed-head",
            head_ref="dev/m7-ci",
        )


def test_gate_does_not_block_stale_ordinary_or_stacked_work() -> None:
    """Main movement never churns an in-flight ordinary Milestone PR."""
    for base in ("dev/m7-ci", "feat/41-parent"):
        api = FakeAPI([])
        assert (
            gate(
                api,
                "acme/repo",
                base,
                "head-sha",
                head_ref="feat/42-change",
            )
            == "not-applicable"
        )
        assert not api.calls


def test_second_main_advance_invalidates_previous_success() -> None:
    """A new main SHA requires a fresh ancestry result."""
    first = FakeAPI(
        [(200, {"object": {"sha": "main-one"}}), (200, {"status": "ahead"})]
    )
    assert (
        gate(
            first,
            "acme/repo",
            "main",
            "head-sha",
            head_ref="dev/m7-ci",
        )
        == "ahead"
    )
    second = FakeAPI(
        [
            (200, {"object": {"sha": "main-two"}}),
            (200, {"status": "diverged"}),
            (200, []),
        ]
    )
    with pytest.raises(RuntimeError, match="exactly one reviewed sync PR"):
        gate(
            second,
            "acme/repo",
            "main",
            "head-sha",
            head_ref="dev/m7-ci",
            pr_number=42,
        )


def test_stale_bridge_points_to_its_single_delivery_sync() -> None:
    """A stale bridge must sync its matching source before being rebuilt."""
    api = FakeAPI(
        [
            (200, {"object": {"sha": "main-two"}}),
            (200, {"status": "diverged"}),
        ]
    )
    with pytest.raises(RuntimeError, match="gh pr create --base dev/m7-ci"):
        gate(
            api,
            "acme/repo",
            "main",
            "bridge-head",
            head_ref="promote/m7-ci",
            pr_number=42,
        )
    assert not any("pulls?" in path for _method, path, _payload in api.calls)


def test_manual_sync_is_deterministic_and_reviewed() -> None:
    """The fallback never pushes directly to an active delivery branch."""
    assert sync_branch_name("dev/m7-staged-ci", "abcdef0123456789") == (
        "sync/main-to-m7-staged-ci-abcdef012345"
    )
    commands = manual_commands("dev/m7-staged-ci", "abcdef0123456789")
    assert "git merge --no-ff origin/main" in commands
    assert "gh pr create --base dev/m7-staged-ci" in commands
    assert "git push origin dev/m7-staged-ci" not in commands


def test_explicit_dependency_sync_requires_the_requesting_pr_owner() -> None:
    """Early sync is limited to an owner PR with a declared dependency."""
    request = promotion("feat/42-change")
    request.update(
        {
            "base": {"ref": "dev/m7-ci", "sha": BASE_SHA},
            "labels": [{"name": "enhancement"}],
            "body": (
                "Refs #42\n\n"
                "- Dependencies / non-parallel work: Needs main PR #40"
            ),
        }
    )
    require_sync_request(
        FakeAPI([(200, request)]),
        "acme/repo",
        "dev/m7-ci",
        "explicit-dependency",
        42,
        "owner",
    )
    with pytest.raises(RuntimeError, match="owned by"):
        require_sync_request(
            FakeAPI([(200, request)]),
            "acme/repo",
            "dev/m7-ci",
            "explicit-dependency",
            42,
            "another-owner",
        )
    request["body"] = "Refs #42\n\n- Dependencies / non-parallel work: None"
    with pytest.raises(RuntimeError, match="explicit dependency"):
        require_sync_request(
            FakeAPI([(200, request)]),
            "acme/repo",
            "dev/m7-ci",
            "explicit-dependency",
            42,
            "owner",
        )


def test_archived_delivery_maintenance_uses_reviewed_manual_fallback() -> None:
    """An unavailable workflow is replaced by exact reviewed PR commands."""
    root = Path(__file__).parents[1]
    workflow = root / ".github/workflows/delivery-maintenance.yml"
    assert not workflow.exists()

    main_sha = "a" * 40
    api = FakeAPI(
        [
            (200, {"object": {"sha": main_sha}}),
            (200, {"status": "diverged"}),
            (200, []),
        ]
    )
    with pytest.raises(RuntimeError) as error:
        gate(
            api,
            "acme/repo",
            "main",
            "proposed-head",
            head_ref="dev/m7-ci",
            pr_number=42,
        )
    message = str(error.value)
    assert manual_commands("dev/m7-ci", main_sha) in message
    assert "delivery-maintenance.yml" not in message


def test_merge_group_revalidates_one_exact_pull_request() -> None:
    """A queue candidate is rebound to one live same-repository PR."""
    queue_sha = "f" * 40
    queue_ref = "refs/heads/gh-readonly-queue/main/pr-42-deadbeef"
    queue_branch = "gh-readonly-queue%2Fmain%2Fpr-42-deadbeef"
    api = FakeAPI(
        [
            (200, {"object": {"sha": queue_sha}}),
            (200, [{"number": 42}]),
            (200, promotion()),
            (200, {"object": {"sha": BASE_SHA}}),
            (200, {"object": {"sha": HEAD_SHA}}),
            (200, {"status": "ahead"}),
            (200, {"status": "ahead"}),
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
        == "exact queue candidate for dev/m7-ci"
    )
    assert api.calls[0][1].endswith(queue_branch)


@pytest.mark.parametrize(
    "head_ref", ["dev/m7-ci", "promote/m7-ci", "dev/i42-soak"]
)
def test_merge_group_revalidates_other_exact_promotion_heads(
    head_ref: str,
) -> None:
    """Milestone promotion heads keep exact queue and live-ref validation."""
    queue_sha = "f" * 40
    queued = promotion()
    queued["head"]["ref"] = head_ref
    api = FakeAPI(
        [
            (200, {"object": {"sha": queue_sha}}),
            (200, [{"number": 42}]),
            (200, queued),
            (200, {"object": {"sha": BASE_SHA}}),
            (200, {"object": {"sha": HEAD_SHA}}),
            (200, {"status": "ahead"}),
            (200, {"status": "ahead"}),
        ]
    )

    assert (
        merge_group_gate(
            api,
            "acme/repo",
            "refs/heads/gh-readonly-queue/main/pr-42-deadbeef",
            queue_sha,
            "refs/heads/main",
            BASE_SHA,
        )
        == f"exact queue candidate for {head_ref}"
    )
    encoded = urllib.parse.quote(head_ref, safe="")
    assert any(path.endswith(encoded) for _method, path, _payload in api.calls)


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


def untrusted_admin_secret_references(source: str) -> set[str]:
    """Return admin secret references exposed by untrusted workflow events."""
    lines = source.splitlines()
    on_index = next(
        (index for index, line in enumerate(lines) if line.startswith("on:")),
        None,
    )
    if on_index is None:
        return set()
    declaration = lines[on_index].removeprefix("on:")
    untrusted = bool(
        re.search(r"\b(?:pull_request|merge_group)\b", declaration)
    )
    if not declaration.strip():
        for line in lines[on_index + 1 :]:
            if line and not line[0].isspace():
                break
            untrusted |= bool(
                re.match(r"^  (?:pull_request|merge_group):", line)
            )
    if not untrusted:
        return set()
    names = {
        "CSARC_SYNC_TOKEN",
        "CSARC_ADMIN_TOKEN",
        "GH_ADMIN_TOKEN",
        "ADMIN_TOKEN",
    }
    return {name for name in names if f"secrets.{name}" in source}


def test_untrusted_workflows_cannot_reference_admin_secrets() -> None:
    """PR-controlled workflows never receive administration tokens."""
    root = Path(__file__).parents[1]
    for trigger in ("pull_request", "merge_group"):
        unsafe = f"""
on: [{trigger}]
jobs:
  leak:
    env:
      TOKEN: ${{{{ secrets.CSARC_SYNC_TOKEN }}}}
"""
        assert untrusted_admin_secret_references(unsafe) == {"CSARC_SYNC_TOKEN"}
    workflows = (root / ".github/workflows").glob("*.y*ml")
    for workflow in workflows:
        assert not untrusted_admin_secret_references(workflow.read_text()), (
            workflow
        )

    for name in ("pr-policy.yml", "ci.yml"):
        source = (root / ".github/workflows" / name).read_text()
        assert "secrets.CSARC_SYNC_TOKEN" not in source


def test_pr_policy_uses_supported_delivery_gate_arguments() -> None:
    """Keep the thin workflow aligned with the repo-local command."""
    root = Path(__file__).parents[1]
    script = root / "scripts/delivery_sync.py"
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script), "gate", "--help"],
        capture_output=True,
        check=True,
        text=True,
    )
    supported = set(re.findall(r"--[a-z][a-z-]*", result.stdout))
    root_workflow = (root / ".github/workflows/pr-policy.yml").read_text()
    command = re.search(
        r"python3 scripts/delivery_sync\.py gate"
        r"(?P<arguments>(?:\n\s+--[^\n]+)+)",
        root_workflow,
    )
    assert command is not None
    used = set(re.findall(r"--[a-z][a-z-]*", command["arguments"]))
    assert used <= supported


def test_legacy_persistent_delivery_assets_are_removed() -> None:
    """Keep removed catch-all routes out of active delivery policy."""
    root = Path(__file__).parents[1]
    for relative in (
        "policies/dev-next-ruleset.json",
        "template/policies/dev-next-ruleset.json",
    ):
        assert not (root / relative).exists()
    for relative in (
        "scripts/delivery_sync.py",
        "scripts/promotion_gate.py",
        ".github/dependabot.yml",
    ):
        policy = (root / relative).read_text(encoding="utf-8")
        assert "dev/next" not in policy
        assert "promote/next" not in policy


def test_milestone_promotion_check_and_cleanup_cover_delivery_refs() -> None:
    """Required checks conclude and exact promoted delivery refs retire."""
    root = Path(__file__).parents[1]
    promotion_path = root / ".github/workflows/promotion.yml"
    if not promotion_path.is_file():
        pytest.skip("Trusted promotion workflows remain archived")
    promotion = promotion_path.read_text()
    post_merge = (
        root / ".github/workflows/promotion-post-merge.yml"
    ).read_text()
    assert 'branches: [main, "dev/m*"]' in promotion
    assert "Report non-applicable route" in promotion
    assert "source_tree" in post_merge
    assert (
        '--force-with-lease="refs/heads/$source_ref:$source_sha"' in post_merge
    )
    assert "moved after promotion; refusing to delete it" in post_merge


def test_isolated_delivery_state_requires_its_open_promotion_issue() -> None:
    """An isolated canary sync stays bound to one live promotion Issue."""
    api = FakeAPI(
        [
            (200, {"object": {"sha": "isolated"}}),
            (
                200,
                {
                    "number": 42,
                    "state": "open",
                    "labels": [{"name": "promotion"}],
                },
            ),
            (200, {"status": "ahead"}),
        ]
    )
    state = read_delivery_state(api, "acme/repo", "main-sha", "dev/i42-soak")
    assert state.branch == "dev/i42-soak"
    assert state.current is True


def test_existing_sync_pr_deduplicates_same_main_sha() -> None:
    """Return the existing deterministic PR without another write."""
    api = FakeAPI([(200, [{"html_url": "https://example.test/pull/1"}])])
    assert (
        create_sync_pr(
            api,
            "acme/repo",
            "dev/m7-ci",
            "delivery",
            "abcdef0123456789",
            "promotion",
            42,
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
            api,
            "acme/repo",
            "dev/m7-ci",
            "delivery",
            "abcdef0123456789",
            "promotion",
            42,
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
            api,
            "acme/repo",
            "dev/m7-ci",
            "delivery",
            "abcdef0123456789",
            "promotion",
            42,
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


def test_reconcile_handles_only_the_requested_delivery() -> None:
    """One authorized request cannot fan out to other Milestones."""
    api = FakeAPI(
        [
            (
                200,
                promotion(),
            ),
            (200, {"object": {"sha": "seven"}}),
            (200, {"number": 7, "state": "open"}),
            (200, {"status": "diverged"}),
        ]
    )
    results = reconcile(
        api,
        "acme/repo",
        "main-two",
        auto_requested=True,
        external_token=False,
        delivery_branch="dev/m7-ci",
        reason="promotion",
        request_pr=42,
        requester="owner",
    )
    assert results[0].startswith("Sync mode: manual")
    assert any("dev/m7-ci is diverged" in result for result in results)
    assert not any("m8" in path for _method, path, _payload in api.calls)


def test_reconcile_skips_current_delivery_without_writes() -> None:
    """A requested branch already containing main needs no sync PR."""
    api = FakeAPI(
        [
            (200, promotion()),
            (200, {"object": {"sha": "next"}}),
            (200, {"number": 7, "state": "open"}),
            (200, {"status": "ahead"}),
        ]
    )

    assert reconcile(
        api,
        "acme/repo",
        "main-two",
        auto_requested=False,
        external_token=False,
        delivery_branch="dev/m7-ci",
        reason="promotion",
        request_pr=42,
        requester="owner",
    ) == ["dev/m7-ci already contains current main."]
    assert not any(method == "POST" for method, _path, _payload in api.calls)
