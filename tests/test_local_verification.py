"""Tests for self-attested local verification evidence."""

from __future__ import annotations

import importlib.util
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "local_verification", ROOT / "scripts/local_verification.py"
)
assert SPEC is not None and SPEC.loader is not None
local_verification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(local_verification)


def git(repo: Path, *args: str) -> str:
    """Run Git in one isolated fixture repository."""
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def repository(tmp_path: Path, mode: str = "local") -> Path:
    """Create one committed branch with a configured pull-request base."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test User")
    config = tmp_path / ".csarc/config.yml"
    config.parent.mkdir()
    config.write_text(
        f"languages: []\nverification_mode: {mode}\n",
        encoding="utf-8",
    )
    (tmp_path / "tracked.txt").write_text("base\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "base")
    git(tmp_path, "switch", "-c", "feat/1-local-proof")
    git(tmp_path, "config", "branch.feat/1-local-proof.gh-merge-base", "main")
    (tmp_path / "tracked.txt").write_text("candidate\n", encoding="utf-8")
    git(tmp_path, "commit", "-am", "candidate")
    return tmp_path


def test_local_evidence_is_bound_to_clean_exact_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Head, tree, base, tier, freshness, and cleanliness all remain bound."""
    repo = repository(tmp_path)
    monkeypatch.chdir(repo)
    payload = local_verification.record("fast", ["source"], "main")
    assert payload is not None

    result = local_verification.require(
        head_sha=git(repo, "rev-parse", "HEAD"),
        tree_sha=git(repo, "rev-parse", "HEAD^{tree}"),
        base_ref="main",
        base_sha=git(repo, "rev-parse", "main"),
        required_tier="fast",
    )
    assert result["trust"] == "self-attested-local"
    assert result["scopes"] == ["source"]

    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="clean worktree"):
        local_verification.require(
            head_sha=str(payload["head_sha"]),
            tree_sha=str(payload["tree_sha"]),
            base_ref="main",
            base_sha=str(payload["base_sha"]),
            required_tier="fast",
        )
    (repo / "tracked.txt").write_text("candidate\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="does not match"):
        local_verification.require(
            head_sha=str(payload["head_sha"]),
            tree_sha=str(payload["tree_sha"]),
            base_ref="main",
            base_sha="0" * 40,
            required_tier="fast",
        )
    with pytest.raises(RuntimeError, match="stale"):
        local_verification.require(
            head_sha=str(payload["head_sha"]),
            tree_sha=str(payload["tree_sha"]),
            base_ref="main",
            base_sha=str(payload["base_sha"]),
            required_tier="fast",
            now=datetime.now(UTC) + timedelta(hours=25),
        )

    (repo / "tracked.txt").write_text("next candidate\n", encoding="utf-8")
    git(repo, "commit", "-am", "next candidate")
    with pytest.raises(RuntimeError, match="current worktree"):
        local_verification.require(
            head_sha=str(payload["head_sha"]),
            tree_sha=str(payload["tree_sha"]),
            base_ref="main",
            base_sha=str(payload["base_sha"]),
            required_tier="fast",
        )


def test_local_evidence_rejects_inconsistent_tier_scope_and_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The attestation cannot relabel a fast run as a full run."""
    repo = repository(tmp_path)
    monkeypatch.chdir(repo)
    with pytest.raises(RuntimeError, match="tier and scopes disagree"):
        local_verification.record("full", ["source"], "main")
    with pytest.raises(RuntimeError, match="HEAD changed"):
        local_verification.record(
            "fast",
            ["source"],
            "main",
            expected_head_sha="0" * 40,
        )
    payload = local_verification.record("fast", ["source"], "main")
    assert payload is not None
    path = local_verification.evidence_path(str(payload["head_sha"]))
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace('"tier": "fast"', '"tier": "full"'),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="does not match"):
        local_verification.require(
            head_sha=str(payload["head_sha"]),
            tree_sha=str(payload["tree_sha"]),
            base_ref="main",
            base_sha=str(payload["base_sha"]),
            required_tier="full",
        )


def test_hosted_mode_does_not_write_local_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hosted projects keep the established trusted evidence path."""
    repo = repository(tmp_path, "hosted")
    monkeypatch.chdir(repo)
    head_sha = git(repo, "rev-parse", "HEAD")

    assert local_verification.record("fast", ["source"], "main") is None
    assert not local_verification.evidence_path(head_sha).exists()


def test_uncommitted_local_project_passes_without_merge_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Initial validation is useful before a repository has a first commit."""
    config = tmp_path / ".csarc/config.yml"
    config.parent.mkdir()
    config.write_text("verification_mode: local\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert local_verification.record("fast", ["source"], "main") is None


def test_dirty_local_project_passes_without_merge_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dirty tree keeps test success while remaining ineligible to merge."""
    repo = repository(tmp_path)
    monkeypatch.chdir(repo)
    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")

    assert local_verification.record("fast", ["source"], "main") is None
