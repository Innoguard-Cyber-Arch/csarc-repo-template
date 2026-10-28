"""Tests for self-attested local verification evidence."""

from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import settings_support

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
        settings_support.settings_text(verification_mode=mode),
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


def test_trusted_base_records_a_hosted_exit_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#1318 AC2: the control set's settings decide whether to record.

    A self-hosted exit renders hosted, which ships no recorder; the base's
    verifier checks it and records, while a hosted control never does.
    """
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    repo = repository(candidate, "hosted")
    controls = {}
    for mode in ("local", "hosted"):
        control = tmp_path / mode
        (control / ".csarc").mkdir(parents=True)
        (control / ".csarc/config.yml").write_text(
            settings_support.settings_text(verification_mode=mode),
            encoding="utf-8",
        )
        controls[mode] = control
    monkeypatch.chdir(repo)
    head_sha = git(repo, "rev-parse", "HEAD")

    assert local_verification.record("fast", ["source"], "main") is None
    assert (
        local_verification.record(
            "fast", ["source"], "main", control_root=controls["hosted"]
        )
        is None
    )
    assert not local_verification.evidence_path(head_sha).exists()
    payload = local_verification.record(
        "fast", ["source"], "main", control_root=controls["local"]
    )
    assert payload is not None
    assert payload["head_sha"] == head_sha
    assert local_verification.evidence_path(head_sha).is_file()


def test_configured_base_must_be_at_the_planned_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#1318: a commit given as the base must be the configured base tip."""
    repo = repository(tmp_path)
    monkeypatch.chdir(repo)
    head_sha = git(repo, "rev-parse", "HEAD")

    with pytest.raises(RuntimeError, match="Base does not match: 'main' is at"):
        local_verification.record(
            "fast", ["source"], "", expected_base_sha=head_sha
        )
    assert not local_verification.evidence_path(head_sha).exists()


def test_self_hosted_vm_skips_local_evidence_on_detached_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#1301: VM evidence comes from GitHub, not the detached worktree."""
    repo = repository(tmp_path)
    git(repo, "switch", "--detach")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CSARC_SELF_HOSTED_VM", "true")
    head_sha = git(repo, "rev-parse", "HEAD")

    assert local_verification.record("full", ["all"], "main") is None
    assert not local_verification.evidence_path(head_sha).exists()


def test_uncommitted_local_project_passes_without_merge_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Initial validation is useful before a repository has a first commit."""
    config = tmp_path / ".csarc/config.yml"
    config.parent.mkdir()
    config.write_text(
        settings_support.settings_text(verification_mode="local"),
        encoding="utf-8",
    )
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


def test_local_evidence_is_a_canonical_merge_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #1073: the merge hashes recorded local evidence unchanged."""
    repo = repository(tmp_path)
    monkeypatch.chdir(repo)
    payload = local_verification.record("fast", ["source"], "main")
    assert payload is not None
    merge_trace = importlib.import_module("merge_trace")
    data = merge_trace.canonical_bytes(payload)
    assert merge_trace.parse_canonical(data) == payload
    assert merge_trace.payload_schema(payload) == 1
    assert str(payload["completed_at"]).endswith("Z")


def _local_payload(
    repo: Path, **changes: object
) -> tuple[dict[str, object], Path]:
    """Record one local result and rewrite selected payload fields."""
    payload = local_verification.record("fast", ["source"], "main")
    assert payload is not None
    path = local_verification.evidence_path(str(payload["head_sha"]))
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")
    return payload, path


def _require_local(
    payload: dict[str, object], **kwargs: object
) -> dict[str, object]:
    """Validate recorded local evidence for the recorded candidate."""
    return local_verification.require(
        head_sha=str(payload["head_sha"]),
        tree_sha=str(payload["tree_sha"]),
        base_ref="main",
        base_sha=str(payload["base_sha"]),
        required_tier="fast",
        **kwargs,
    )


def test_local_freshness_uses_the_shared_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #1075: local evidence expires on the same inclusive boundary."""
    repo = repository(tmp_path)
    monkeypatch.chdir(repo)
    completed = datetime(2026, 10, 14, 12, tzinfo=UTC)
    payload, _ = _local_payload(repo, completed_at="2026-10-14T12:00:00Z")

    assert _require_local(payload, now=completed + timedelta(hours=24))
    with pytest.raises(RuntimeError, match="is stale: too old"):
        _require_local(payload, now=completed + timedelta(hours=24, seconds=1))
    with pytest.raises(RuntimeError, match="in the future"):
        _require_local(payload, now=completed - timedelta(minutes=5, seconds=1))
    with pytest.raises(RuntimeError, match="freshness window is too wide"):
        _require_local(
            payload, now=completed + timedelta(hours=30), max_age_hours=48
        )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "completion time is missing"),
        ("2026-10-14T12:00:00", "completion time has no timezone"),
        ("not-a-time", "completion time is malformed"),
    ],
)
def test_local_missing_or_naive_completion_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    value: object,
    message: str,
) -> None:
    """Local evidence without an aware completion time never counts."""
    repo = repository(tmp_path)
    monkeypatch.chdir(repo)
    payload, _ = _local_payload(repo, completed_at=value)
    with pytest.raises(RuntimeError, match=message):
        _require_local(payload)


def test_local_evidence_cannot_carry_its_own_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A candidate-written `max_age_hours` field is rejected, not honored."""
    repo = repository(tmp_path)
    monkeypatch.chdir(repo)
    payload, _ = _local_payload(
        repo, completed_at="2000-01-01T00:00:00Z", max_age_hours=1e9
    )
    with pytest.raises(RuntimeError, match="malformed"):
        _require_local(payload)


def test_local_revalidation_replaces_stale_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-running the suite on the same head records fresh evidence again."""
    repo = repository(tmp_path)
    monkeypatch.chdir(repo)
    payload, _ = _local_payload(repo, completed_at="2000-01-01T00:00:00Z")
    with pytest.raises(RuntimeError, match="stale"):
        _require_local(payload)
    rerun = local_verification.record("fast", ["source"], "main")
    assert rerun is not None
    assert _require_local(rerun)["completed_at"] == rerun["completed_at"]
