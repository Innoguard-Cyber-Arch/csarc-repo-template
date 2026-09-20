"""Tests for privileged Dependabot head authentication (Issue #830)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

dependabot_auth = importlib.import_module("authenticate_dependabot_head")

REPO = "Innoguard-Cyber-Arch/csarc-repo-template"
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
SYNC_SHA = "c" * 40


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


def _sync_child() -> dict:
    return {
        "sha": SYNC_SHA,
        "commit": {
            "message": dependabot_auth.DEPENDABOT_SYNC_COMMIT_MESSAGE,
            "author": dependabot_auth.DEPENDABOT_SYNC_COMMIT_IDENTITY,
            "committer": dependabot_auth.DEPENDABOT_SYNC_COMMIT_IDENTITY,
            "verification": {"verified": False, "reason": "unsigned"},
        },
        "parents": [{"sha": HEAD_SHA}],
    }


def _sync_child_pull_request() -> dict:
    pull_request = _pull_request()
    pull_request["head"]["sha"] = SYNC_SHA
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
        _comparison("scripts/run-me"),
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
    """A deterministic sync child may be reconstructed from its bot parent."""
    eligible, reason, parent_sha, source_base_sha = (
        dependabot_auth.trusted_sync_child_candidate(
            _sync_child_pull_request(),
            _sync_child(),
            _commit(),
            _comparison(),
            REPO,
            BASE_SHA,
        )
    )

    assert eligible
    assert "candidate trusted sync child" in reason
    assert parent_sha == HEAD_SHA
    assert source_base_sha == BASE_SHA


def test_trusted_sync_child_candidate_rejects_a_human_parent() -> None:
    """Spoofed sync metadata cannot replace the signed Dependabot parent."""
    eligible, reason, _, _ = dependabot_auth.trusted_sync_child_candidate(
        _sync_child_pull_request(),
        _sync_child(),
        _commit(author="some-contributor"),
        _comparison(),
        REPO,
        BASE_SHA,
    )

    assert not eligible
    assert "parent is not trusted" in reason


def test_authenticated_cli_writes_only_validated_push_coordinates(
    tmp_path: Path,
) -> None:
    """The privileged workflow receives the exact authenticated ref and SHA."""
    pull_request_path = tmp_path / "pull-request.json"
    commit_path = tmp_path / "commit.json"
    comparison_path = tmp_path / "comparison.json"
    parent_commit_path = tmp_path / "parent-commit.json"
    parent_comparison_path = tmp_path / "parent-comparison.json"
    output = tmp_path / "github-output"
    pull_request_path.write_text(json.dumps(_pull_request()), encoding="utf-8")
    commit_path.write_text(json.dumps(_commit()), encoding="utf-8")
    comparison_path.write_text(json.dumps(_comparison()), encoding="utf-8")
    parent_commit_path.write_text("{}", encoding="utf-8")
    parent_comparison_path.write_text("{}", encoding="utf-8")

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
            "--parent-comparison-json",
            str(parent_comparison_path),
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
        "parent_sha=\n"
        "source_base_sha=\n"
    )


def test_cli_classifies_a_sync_child_for_trusted_reconstruction(
    tmp_path: Path,
) -> None:
    """A reopened sync child is not trusted until its tree is reconstructed."""
    inputs = {
        "pull-request": _sync_child_pull_request(),
        "commit": _sync_child(),
        "comparison": _comparison(),
        "parent-commit": _commit(),
        "parent-comparison": _comparison(),
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
            "--parent-comparison-json",
            str(paths["parent-comparison"]),
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
        f"head_sha={SYNC_SHA}\n"
        "sync_child_candidate=true\n"
        f"parent_sha={HEAD_SHA}\n"
        f"source_base_sha={BASE_SHA}\n"
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
        "parent-comparison": {},
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
            "--parent-comparison-json",
            str(paths["parent-comparison"]),
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
