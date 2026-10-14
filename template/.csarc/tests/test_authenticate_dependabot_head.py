"""Tests for privileged Dependabot head authentication (Issue #830)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".csarc" / "scripts"))

dependabot_auth = importlib.import_module("authenticate_dependabot_head")

REPO = "Innoguard-Cyber-Arch/csarc-repo-template"
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
SYNC_SHA = "c" * 40
RELEASE_SHA = "d" * 40


def _pull_request() -> dict:
    return {
        "state": "open",
        "user": {"login": "dependabot[bot]", "type": "Bot"},
        "base": {
            "ref": "main",
            "repo": {"full_name": REPO},
            "sha": BASE_SHA,
        },
        "head": {
            "ref": "dependabot/github_actions/main/actions-checkout-7",
            "repo": {"full_name": REPO},
            "sha": HEAD_SHA,
        },
    }


def _commit(author: str = "dependabot[bot]") -> dict:
    return {
        "sha": HEAD_SHA,
        "author": {
            "login": author,
            "type": "Bot" if author == "dependabot[bot]" else "User",
        },
        "committer": {"login": "web-flow"},
        "commit": {"verification": {"verified": True, "reason": "valid"}},
        "parents": [{"sha": BASE_SHA}],
    }


def _comparison(path: str = ".github/workflows/ci.yml") -> dict:
    return {
        "ahead_by": 1,
        "files": [{"filename": path, "status": "modified"}],
    }


def _actions_commit(sha: str, message: str, parent: str) -> dict:
    return {
        "sha": sha,
        "commit": {
            "message": message,
            "author": dependabot_auth.DEPENDABOT_SYNC_COMMIT_IDENTITY,
            "committer": dependabot_auth.DEPENDABOT_SYNC_COMMIT_IDENTITY,
            "verification": {"verified": False, "reason": "unsigned"},
        },
        "parents": [{"sha": parent}],
    }


def _sync_child() -> dict:
    return _actions_commit(
        SYNC_SHA, dependabot_auth.DEPENDABOT_SYNC_COMMIT_MESSAGE, HEAD_SHA
    )


def _release_child() -> dict:
    return _actions_commit(RELEASE_SHA, "chore(main): release 0.30.3", SYNC_SHA)


def _sync_child_pull_request() -> dict:
    pull_request = _pull_request()
    pull_request["head"]["sha"] = RELEASE_SHA
    return pull_request


def test_dependabot_on_its_own_branch_in_this_repo_is_eligible() -> None:
    """Dependabot, on its own branch prefix, from this repository, passes."""
    eligible, reason = dependabot_auth.dependabot_coordinates_eligible(
        "dependabot[bot]", "dependabot/uv/copier-9.18.2", REPO, REPO
    )
    assert eligible
    assert "valid coordinates" in reason


def test_non_dependabot_author_is_not_eligible() -> None:
    """A different opener cannot borrow Dependabot's branch namespace."""
    eligible, reason = dependabot_auth.dependabot_coordinates_eligible(
        "some-contributor", "some-contributor/patch-1", REPO, REPO
    )
    assert not eligible
    assert "is not 'dependabot[bot]'" in reason


def test_dependabot_with_wrong_branch_prefix_is_not_eligible() -> None:
    """Dependabot's login on a branch outside its namespace fails closed."""
    eligible, reason = dependabot_auth.dependabot_coordinates_eligible(
        "dependabot[bot]", "not-dependabot/patch-1", REPO, REPO
    )
    assert not eligible
    assert "does not match" in reason


def test_dependabot_from_a_fork_is_not_eligible() -> None:
    """A fork's head repository never qualifies, even with a matching branch."""
    eligible, reason = dependabot_auth.dependabot_coordinates_eligible(
        "dependabot[bot]",
        "dependabot/uv/copier-9.18.2",
        "someone-else/csarc-repo-template",
        REPO,
    )
    assert not eligible
    assert "fork" in reason


def test_missing_head_repository_is_not_eligible() -> None:
    """An empty head repository (unset event field) fails closed."""
    eligible, reason = dependabot_auth.dependabot_coordinates_eligible(
        "dependabot[bot]", "dependabot/uv/copier-9.18.2", "", REPO
    )
    assert not eligible
    assert "fork" in reason


def test_authenticated_dependabot_head_requires_current_bot_commit() -> None:
    """Issue #830: a human commit on a bot-opened PR fails closed."""
    eligible, reason = dependabot_auth.authenticated_dependabot_head(
        _pull_request(), _commit(author="some-contributor"), REPO, BASE_SHA
    )

    assert not eligible
    assert "current head author" in reason


def test_authenticated_dependabot_head_requires_bot_account_types() -> None:
    """Matching login text cannot impersonate GitHub's Bot account type."""
    pull_request = _pull_request()
    pull_request["user"]["type"] = "User"

    eligible, reason = dependabot_auth.authenticated_dependabot_head(
        pull_request, _commit(), REPO, BASE_SHA
    )

    assert not eligible
    assert "GitHub Bot" in reason

    pull_request["user"]["type"] = "Bot"
    commit = _commit()
    commit["author"]["type"] = "User"
    eligible, reason = dependabot_auth.authenticated_dependabot_head(
        pull_request, commit, REPO, BASE_SHA
    )

    assert not eligible
    assert "current head author" in reason


def test_authenticated_dependabot_head_binds_the_event_base() -> None:
    """A stale target run cannot authenticate metadata from a newer base."""
    pull_request = _pull_request()
    pull_request["base"]["sha"] = "d" * 40

    eligible, reason = dependabot_auth.authenticated_dependabot_head(
        pull_request, _commit(), REPO, BASE_SHA
    )

    assert not eligible
    assert "does not match the workflow event" in reason


def test_authenticated_dependabot_head_requires_main() -> None:
    """No privileged action may follow a Dependabot PR retargeted off main."""
    pull_request = _pull_request()
    pull_request["base"]["ref"] = "release/old"

    eligible, reason = dependabot_auth.authenticated_dependabot_head(
        pull_request, _commit(), REPO, BASE_SHA
    )

    assert not eligible
    assert "base is not" in reason


def test_dependabot_sync_accepts_only_modified_root_workflows() -> None:
    """A signed one-commit Actions bump is the complete sync input."""
    eligible, reason = dependabot_auth.dependabot_sync_eligibility(
        _pull_request(), _commit(), _comparison(), REPO, BASE_SHA
    )

    assert eligible
    assert "eligible for sync" in reason


def test_dependabot_sync_rejects_paths_outside_the_allowlist() -> None:
    """A signed bot commit still cannot smuggle arbitrary repository edits."""
    eligible, reason = dependabot_auth.dependabot_sync_eligibility(
        _pull_request(),
        _commit(),
        _comparison(".csarc/scripts/run-me"),
        REPO,
        BASE_SHA,
    )

    assert not eligible
    assert "outside the sync allowlist" in reason


def test_dependabot_sync_rejects_a_possibly_truncated_file_list() -> None:
    """The GitHub compare API's 300-file cap must fail closed."""
    comparison = {
        "ahead_by": 1,
        "files": [
            {
                "filename": f".github/workflows/update-{index}.yml",
                "status": "modified",
            }
            for index in range(300)
        ],
    }

    eligible, reason = dependabot_auth.dependabot_sync_eligibility(
        _pull_request(), _commit(), comparison, REPO, BASE_SHA
    )

    assert not eligible
    assert "truncation limit" in reason


def test_dependabot_sync_rejects_unsigned_or_non_github_commits() -> None:
    """Matching author text is insufficient without GitHub provenance."""
    commit = _commit()
    commit["commit"]["verification"]["verified"] = False

    eligible, reason = dependabot_auth.dependabot_sync_eligibility(
        _pull_request(), commit, _comparison(), REPO, BASE_SHA
    )

    assert not eligible
    assert "valid GitHub signature" in reason


def test_trusted_sync_child_requires_an_authenticated_parent() -> None:
    """A release -> sync -> Dependabot chain is selected for reconstruction."""
    eligible, reason, sync_sha, dependabot_sha = (
        dependabot_auth.trusted_sync_child_candidate(
            _sync_child_pull_request(),
            _release_child(),
            _sync_child(),
            _commit(),
            _comparison(),
            REPO,
            BASE_SHA,
        )
    )

    assert eligible
    assert "candidate trusted sync child" in reason
    assert sync_sha == SYNC_SHA
    assert dependabot_sha == HEAD_SHA


def test_trusted_sync_child_candidate_rejects_a_human_parent() -> None:
    """Spoofed sync metadata cannot replace the signed Dependabot parent."""
    eligible, reason, _, _ = dependabot_auth.trusted_sync_child_candidate(
        _sync_child_pull_request(),
        _release_child(),
        _sync_child(),
        _commit(author="some-contributor"),
        _comparison(),
        REPO,
        BASE_SHA,
    )

    assert not eligible
    assert "parent is not trusted" in reason


def test_trusted_sync_child_requires_a_stable_release_head() -> None:
    """A sync without its release commit, or a beta release, is rejected."""
    legacy = _sync_child_pull_request()
    legacy["head"]["sha"] = SYNC_SHA
    eligible, reason, _, _ = dependabot_auth.trusted_sync_child_candidate(
        legacy,
        _sync_child(),
        _commit(),
        _commit(),
        _comparison(),
        REPO,
        BASE_SHA,
    )
    assert not eligible
    assert "release commit message" in reason

    beta = _release_child()
    beta["commit"]["message"] = "chore(main): release 0.30.3-beta.1"
    eligible, reason, _, _ = dependabot_auth.trusted_sync_child_candidate(
        _sync_child_pull_request(),
        beta,
        _sync_child(),
        _commit(),
        _comparison(),
        REPO,
        BASE_SHA,
    )
    assert not eligible
    assert "release commit message" in reason


def test_trusted_sync_child_rejects_a_mismatched_sync_parent() -> None:
    """The sync commit metadata must be the release commit's real parent."""
    other = _sync_child()
    other["sha"] = "e" * 40
    eligible, reason, _, _ = dependabot_auth.trusted_sync_child_candidate(
        _sync_child_pull_request(),
        _release_child(),
        other,
        _commit(),
        _comparison(),
        REPO,
        BASE_SHA,
    )

    assert not eligible
    assert "does not match the chain" in reason


def test_trusted_sync_child_requires_the_bump_on_the_trusted_base() -> None:
    """A Dependabot commit built on an older base cannot be materialized."""
    stale = _commit()
    stale["parents"] = [{"sha": "f" * 40}]
    eligible, reason, _, _ = dependabot_auth.trusted_sync_child_candidate(
        _sync_child_pull_request(),
        _release_child(),
        _sync_child(),
        stale,
        _comparison(),
        REPO,
        BASE_SHA,
    )

    assert not eligible
    assert "directly on the trusted base" in reason


def test_authenticated_cli_writes_only_validated_push_coordinates(
    tmp_path: Path,
) -> None:
    """The privileged workflow receives the exact authenticated ref and SHA."""
    pull_request_path = tmp_path / "pull-request.json"
    commit_path = tmp_path / "commit.json"
    comparison_path = tmp_path / "comparison.json"
    parent_commit_path = tmp_path / "parent-commit.json"
    grandparent_commit_path = tmp_path / "grandparent-commit.json"
    grandparent_comparison_path = tmp_path / "grandparent-comparison.json"
    output = tmp_path / "github-output"
    pull_request_path.write_text(json.dumps(_pull_request()), encoding="utf-8")
    commit_path.write_text(json.dumps(_commit()), encoding="utf-8")
    comparison_path.write_text(json.dumps(_comparison()), encoding="utf-8")
    parent_commit_path.write_text("{}", encoding="utf-8")
    grandparent_commit_path.write_text("{}", encoding="utf-8")
    grandparent_comparison_path.write_text("{}", encoding="utf-8")

    exit_code = dependabot_auth.main(
        [
            "--base-repo",
            REPO,
            "--expected-base-sha",
            BASE_SHA,
            "--pull-request-json",
            str(pull_request_path),
            "--commit-json",
            str(commit_path),
            "--comparison-json",
            str(comparison_path),
            "--parent-commit-json",
            str(parent_commit_path),
            "--grandparent-commit-json",
            str(grandparent_commit_path),
            "--grandparent-comparison-json",
            str(grandparent_comparison_path),
            "--github-output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.read_text(encoding="utf-8") == (
        "snapshot_valid=true\n"
        "eligible=true\n"
        "sync_eligible=true\n"
        f"base_sha={BASE_SHA}\n"
        "head_ref=dependabot/github_actions/main/actions-checkout-7\n"
        f"head_sha={HEAD_SHA}\n"
        "sync_child_candidate=false\n"
        "sync_sha=\n"
        "dependabot_sha=\n"
    )


def test_cli_classifies_a_sync_child_for_trusted_reconstruction(
    tmp_path: Path,
) -> None:
    """A reopened sync child is not trusted until its tree is reconstructed."""
    inputs = {
        "pull-request": _sync_child_pull_request(),
        "commit": _release_child(),
        "comparison": _comparison(),
        "parent-commit": _sync_child(),
        "grandparent-commit": _commit(),
        "grandparent-comparison": _comparison(),
    }
    paths = {}
    for name, value in inputs.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    output = tmp_path / "github-output"

    exit_code = dependabot_auth.main(
        [
            "--base-repo",
            REPO,
            "--expected-base-sha",
            BASE_SHA,
            "--pull-request-json",
            str(paths["pull-request"]),
            "--commit-json",
            str(paths["commit"]),
            "--comparison-json",
            str(paths["comparison"]),
            "--parent-commit-json",
            str(paths["parent-commit"]),
            "--grandparent-commit-json",
            str(paths["grandparent-commit"]),
            "--grandparent-comparison-json",
            str(paths["grandparent-comparison"]),
            "--github-output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.read_text(encoding="utf-8") == (
        "snapshot_valid=true\n"
        "eligible=false\n"
        "sync_eligible=false\n"
        f"base_sha={BASE_SHA}\n"
        "head_ref=dependabot/github_actions/main/actions-checkout-7\n"
        f"head_sha={RELEASE_SHA}\n"
        "sync_child_candidate=true\n"
        f"sync_sha={SYNC_SHA}\n"
        f"dependabot_sha={HEAD_SHA}\n"
    )


def test_cli_exports_exact_snapshot_for_an_unauthenticated_head(
    tmp_path: Path,
) -> None:
    """Revocation can target a human replacement without authorizing it."""
    inputs = {
        "pull-request": _pull_request(),
        "commit": _commit(author="some-contributor"),
        "comparison": _comparison(),
        "parent-commit": {},
        "grandparent-commit": {},
        "grandparent-comparison": {},
    }
    paths = {}
    for name, value in inputs.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    output = tmp_path / "github-output"

    exit_code = dependabot_auth.main(
        [
            "--base-repo",
            REPO,
            "--expected-base-sha",
            BASE_SHA,
            "--pull-request-json",
            str(paths["pull-request"]),
            "--commit-json",
            str(paths["commit"]),
            "--comparison-json",
            str(paths["comparison"]),
            "--parent-commit-json",
            str(paths["parent-commit"]),
            "--grandparent-commit-json",
            str(paths["grandparent-commit"]),
            "--grandparent-comparison-json",
            str(paths["grandparent-comparison"]),
            "--github-output",
            str(output),
        ]
    )

    assert exit_code == 0
    written = output.read_text(encoding="utf-8")
    assert "snapshot_valid=true\n" in written
    assert "eligible=false\n" in written
    assert f"base_sha={BASE_SHA}\n" in written
    assert f"head_sha={HEAD_SHA}\n" in written


# Issue #1087: exact-merge candidate lookup (zero / one / many).
MERGE_BRANCH = "dependabot/github_actions/main/actions-checkout-7"
MOVED_SHA = "e" * 40


def _associated(number: object = 7, **overrides: object) -> dict:
    record: dict = {
        "number": number,
        "state": "open",
        "merged_at": None,
        "closed_at": None,
        **_pull_request(),
    }
    record.update(overrides)
    return record


def _resolve(pulls: object, **event: str) -> tuple[str, int | None, str]:
    return dependabot_auth.resolve_merge_candidate(
        pulls,
        event.get("base_repo", REPO),
        event.get("head_sha", HEAD_SHA),
        event.get("head_repository", REPO),
        event.get("head_branch", MERGE_BRANCH),
    )


def test_merge_candidate_with_zero_pull_requests_is_a_stable_no_op() -> None:
    """No associated pull request at all is ordinary "no work"."""
    assert _resolve([[]]) == (
        "no-op",
        None,
        "no-open-exact-dependabot-pull-request",
    )


def test_merge_candidate_never_substitutes_a_closed_or_merged_record() -> None:
    """Closed-only history is a no-op, never a stale replacement."""
    closed = _associated(state="closed", closed_at="2026-10-01T00:00:00Z")
    merged = _associated(
        number=8,
        state="closed",
        merged_at="2026-10-01T00:00:00Z",
        head=None,
    )
    assert _resolve([[closed, merged]])[:2] == ("no-op", None)


def test_merge_candidate_resolves_exactly_one_open_identity() -> None:
    """One exact open Dependabot record keeps the exact-merge path."""
    assert _resolve([[_associated()]]) == (
        "merge",
        7,
        "exact open pull request #7",
    )


def test_merge_candidate_moved_head_is_a_no_op() -> None:
    """A run for an old head never selects the PR's newer head."""
    moved = _associated()
    moved["head"] = {**moved["head"], "sha": MOVED_SHA}
    assert _resolve([[moved]])[:2] == ("no-op", None)


def test_merge_candidate_wrong_actor_or_repository_is_a_no_op() -> None:
    """Records outside the Dependabot identity are never matches."""
    human = _associated(user={"login": "someone", "type": "User"})
    fork = _associated(number=9)
    fork["head"] = {
        **fork["head"],
        "repo": {"full_name": "someone/csarc-repo-template"},
    }
    other_base = _associated(number=10)
    other_base["base"] = {**other_base["base"], "ref": "dev/m1-x"}
    assert _resolve([[human, fork, other_base]])[:2] == ("no-op", None)


def test_merge_candidate_event_outside_identity_is_a_no_op() -> None:
    """A fork-triggered or non-Dependabot-branch event has no work."""
    assert _resolve(
        [[_associated()]], head_repository="someone/csarc-repo-template"
    ) == ("no-op", None, "event-outside-dependabot-identity")
    assert _resolve([[_associated()]], head_branch="feature/x")[:2] == (
        "no-op",
        None,
    )


def test_merge_candidate_many_matches_fail_closed() -> None:
    """Never pick one of several exact open matches."""
    with pytest.raises(dependabot_auth.MergeCandidateError, match="#7, #8"):
        _resolve([[_associated(7)], [_associated(8)]])


def test_merge_candidate_incomplete_open_identity_fails_closed() -> None:
    """An open record that cannot be ruled out must not be skipped."""
    incomplete = _associated()
    del incomplete["user"]
    with pytest.raises(dependabot_auth.MergeCandidateError, match="incomplete"):
        _resolve([[incomplete]])
    with pytest.raises(dependabot_auth.MergeCandidateError, match="incomplete"):
        _resolve([[_associated(number="7")]])
    with pytest.raises(dependabot_auth.MergeCandidateError, match="state"):
        _resolve([[{"number": 7}]])
    with pytest.raises(dependabot_auth.MergeCandidateError, match="SHA"):
        _resolve([[_associated()]], head_sha="not-a-sha")


def test_merge_candidate_contradictory_state_fails_closed() -> None:
    """Open records that also claim closure, or diverge, fail closed."""
    merged_open = _associated(merged_at="2026-10-01T00:00:00Z")
    with pytest.raises(dependabot_auth.MergeCandidateError, match="closed"):
        _resolve([[merged_open]])
    renamed = _associated(title="other snapshot")
    with pytest.raises(
        dependabot_auth.MergeCandidateError, match="conflicting"
    ):
        _resolve([[_associated()], [renamed]])


def test_merge_candidate_reads_every_paginated_page() -> None:
    """A match on a later page is found; a duplicate across pages is one."""
    filler = [
        _associated(number=100 + index, state="closed") for index in range(30)
    ]
    assert _resolve([filler, [_associated()]])[:2] == ("merge", 7)
    assert _resolve([[_associated()], [_associated()]])[:2] == ("merge", 7)
    assert _resolve([_associated()])[:2] == ("merge", 7)
    with pytest.raises(dependabot_auth.MergeCandidateError, match="malformed"):
        _resolve([[_associated()], _associated()])
    with pytest.raises(dependabot_auth.MergeCandidateError, match="not a list"):
        _resolve({"pulls": []})


def _resolve_cli(tmp_path: Path, pulls: object) -> tuple[int, str]:
    pulls_path = tmp_path / "pulls.json"
    pulls_path.write_text(json.dumps(pulls), encoding="utf-8")
    output = tmp_path / "github-output"
    exit_code = dependabot_auth.main(
        [
            "resolve-merge-candidate",
            "--base-repo",
            REPO,
            "--head-sha",
            HEAD_SHA,
            "--head-repository",
            REPO,
            "--head-branch",
            MERGE_BRANCH,
            "--pulls-json",
            str(pulls_path),
            "--github-output",
            str(output),
        ]
    )
    return exit_code, output.read_text(encoding="utf-8")


def test_resolve_cli_no_op_succeeds_without_a_merge_target(
    tmp_path: Path,
) -> None:
    """AC1: zero matches exit 0 with a stable reason and no PR number."""
    exit_code, written = _resolve_cli(tmp_path, [[]])
    assert exit_code == 0
    assert written == (
        "outcome=no-op\n"
        "reason=no-open-exact-dependabot-pull-request\n"
        "number=\n"
        "head_sha=\n"
    )


def test_resolve_cli_exports_the_single_exact_candidate(
    tmp_path: Path,
) -> None:
    """AC2: one match exports the exact number and head for revalidation."""
    exit_code, written = _resolve_cli(tmp_path, [[_associated()]])
    assert exit_code == 0
    assert written == (
        "outcome=merge\n"
        "reason=exact open pull request #7\n"
        "number=7\n"
        f"head_sha={HEAD_SHA}\n"
    )


def test_resolve_cli_fails_closed_on_many_candidates(tmp_path: Path) -> None:
    """AC3: several matches exit nonzero and export no merge target."""
    exit_code, written = _resolve_cli(
        tmp_path, [[_associated(7), _associated(8)]]
    )
    assert exit_code == 1
    assert written.startswith("outcome=fail-closed\n")
    assert "number=\n" in written
    assert "head_sha=\n" in written
