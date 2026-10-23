"""Tests for the owner opt-in single-writer merge route (Issue #1233)."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from test_pr_lifecycle import (
    ADMIN_BYPASS_MARKER,
    MODULE,
    bind_remote_lease,
    lease_fixture,
    merge_snapshot,
    traced_snapshot,
)
from test_single_writer_merge import (
    AUTHORIZATION_URL,
    TEMPLATE_MODULE,
    SingleWriterGitHub,
    human_review_mode,
    merge_trace,
    run_traced_merge,
    use_local_mode,
    writer_stub,
)

from csarc_cli import settings_schema

# Re-export the autouse fixture so this module pins the same review mode.
__all__ = ["human_review_mode"]

ROOT = Path(__file__).resolve().parents[1]
MODULES = pytest.mark.parametrize(
    "module", [MODULE, TEMPLATE_MODULE], ids=["root", "template"]
)
THREE_ADMINS = writer_stub(
    owner_type="Organization",
    collaborators=[
        {"login": "agent", "role_name": "admin"},
        {"login": "org-owner", "role_name": "admin"},
        {"login": "org-second", "role_name": "admin"},
    ],
    keys=[{"id": 7, "read_only": False}, {"id": 8, "read_only": True}],
)


class Role:
    """Serve one live repository role for the merge actor."""

    def __init__(self, role: str) -> None:
        self.role = role

    def get(self, _repo: str, path: str) -> object:
        """Return the collaborator permission payload."""
        assert path == "collaborators/agent/permission"
        return {"role_name": self.role, "user": {"login": "agent"}}


def opted_in(monkeypatch: pytest.MonkeyPatch, merger: str) -> None:
    """Configure `single_writer_merger` for the root lifecycle."""
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "configured_single_writer_merger",
        lambda: merger,
    )


@pytest.mark.parametrize(
    ("merger", "protection", "permission", "identity"),
    [
        # AC2: opted in, three admins, the designated merger merges.
        ("Agent", "single-writer", "allowed", "configured-merger"),
        # AC2: another designated login leaves this actor manual-only.
        ("org-owner", "multiple-writers", "manual-only", "none"),
        # AC1: unset keeps auto-detection, so three admins stay manual.
        ("", "multiple-writers", "manual-only", "none"),
    ],
)
def test_opt_in_route_for_three_admins(
    monkeypatch: pytest.MonkeyPatch,
    merger: str,
    protection: str,
    permission: str,
    identity: str,
) -> None:
    """AC1/AC2/AC4: only the configured merger leaves manual-only."""
    bind_remote_lease(monkeypatch)
    use_local_mode(monkeypatch)
    opted_in(monkeypatch, merger)
    github = SingleWriterGitHub()
    github.writers = THREE_ADMINS

    snapshot = merge_snapshot(github, lease_fixture(), AUTHORIZATION_URL)

    assert snapshot["protection"] == protection
    assert snapshot["merge_permission"] == permission
    assert snapshot["merge_identity"] == identity
    assert snapshot["server_enforcement"] == "none"
    assert snapshot["single_writer_merger"] == merger
    assert snapshot["observed_writers"] == {
        "accounts": ["agent", "org-owner", "org-second"],
        "deploy_keys": ["7"],
    }
    if permission == "allowed":
        # AC3: the exact-head local evidence is still required.
        assert snapshot["required_check_evidence"] == "local-self-attested"
        assert "opted in" in str(snapshot["protection_reason"])


def test_opt_in_keeps_exact_head_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3: the opt-in never replaces the exact-head authorization."""
    bind_remote_lease(monkeypatch)
    use_local_mode(monkeypatch)
    opted_in(monkeypatch, "agent")
    github = SingleWriterGitHub()
    github.writers = THREE_ADMINS
    github.body = "Closes #42"
    github.reviews = []

    with pytest.raises(RuntimeError, match="approval of the exact head"):
        merge_snapshot(github, lease_fixture(), AUTHORIZATION_URL)
    github.body = f"Closes #42\n\n{ADMIN_BYPASS_MARKER}"
    github.mergeable_state = "unstable"
    snapshot = merge_snapshot(github, lease_fixture(), AUTHORIZATION_URL)
    assert snapshot["protection"] == "blocked"


@MODULES
@pytest.mark.parametrize(
    ("actor", "role", "state", "expected"),
    [
        ("agent", "admin", "multiple-writers", "eligible"),
        ("agent", "write", "multiple-writers", "eligible"),
        ("agent", "maintain", "eligible", "eligible"),
        # AC4: the designated login below write stays manual-only.
        ("agent", "read", "multiple-writers", "multiple-writers"),
        ("agent", "triage", "eligible", "inconclusive"),
        ("agent", "unknown", "multiple-writers", "multiple-writers"),
        # AC4: an account other than the designated one.
        ("other", "admin", "multiple-writers", "multiple-writers"),
        ("other", "admin", "eligible", "inconclusive"),
        # An incomplete readback cannot list every writer.
        ("agent", "admin", "inconclusive", "inconclusive"),
    ],
)
def test_opt_in_needs_the_designated_live_writer(
    module: dict[str, Any], actor: str, role: str, state: str, expected: str
) -> None:
    """AC2/AC4: root and template judge the opt-in alike."""
    result, reason = module["single_writer_opt_in"](
        Role(role), "o/r", actor, "agent", state, "readback"
    )
    assert result == expected
    assert reason.startswith(
        "single_writer_merger" if expected == "eligible" else "readback"
    )


@MODULES
@pytest.mark.parametrize(
    "value", ["agent", "", "-agent", "two words", "a--b", "x" * 40, "[bot]"]
)
def test_malformed_setting_fails_closed(
    module: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    """AC1/AC4: a malformed merger blocks the merge before any route."""
    base = (ROOT / ".csarc/config.yml").read_text(encoding="utf-8")
    config = tmp_path / ".csarc/config.yml"
    config.parent.mkdir()
    config.write_text(
        f"{base}single_writer_merger: '{value}'\n", encoding="utf-8"
    )
    reader = module["configured_single_writer_merger"]
    monkeypatch.setitem(reader.__globals__, "repository_root", lambda: tmp_path)
    if value in {"agent", ""}:
        assert reader() == value
        settings_schema._validate_value("single_writer_merger", value)
        return
    with pytest.raises(RuntimeError, match="single_writer_merger must be"):
        reader()
    # The CLI writer refuses the same value before any file is written.
    with pytest.raises(settings_schema.SettingsSchemaError):
        settings_schema._validate_value("single_writer_merger", value)


@MODULES
def test_unset_setting_keeps_auto_detection(
    module: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1: a schema 2 file without the key means no opt-in."""
    config = tmp_path / ".csarc/config.yml"
    config.parent.mkdir()
    config.write_text(
        (ROOT / ".csarc/config.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    reader = module["configured_single_writer_merger"]
    monkeypatch.setitem(reader.__globals__, "repository_root", lambda: tmp_path)
    assert reader() == ""


def test_adding_a_merger_is_a_governance_switch() -> None:
    """R2: naming or changing the merger needs the reviewed route."""
    executor = runpy.run_path(str(ROOT / "scripts/trusted_executor.py"))
    relax = executor["governance_relaxations"]
    assert relax({}, {"single_writer_merger": "agent"}) == [
        "single_writer_merger: - -> agent"
    ]
    assert relax(
        {"single_writer_merger": "agent"}, {"single_writer_merger": "peer"}
    ) == ["single_writer_merger: agent -> peer"]
    assert relax({"single_writer_merger": "agent"}, {}) == []


def test_opt_in_trace_names_config_and_every_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3: the trace records the config opt-in and all writers."""
    github = run_traced_merge(
        tmp_path,
        monkeypatch,
        traced_snapshot(
            protection="single-writer",
            server_enforcement="none",
            merge_permission="allowed",
            merge_identity="configured-merger",
            single_writer_merger="agent",
            observed_writers={
                "accounts": ["agent", "org-owner", "org-second"],
                "deploy_keys": ["7"],
            },
        ),
    )
    summary = merge_trace.parse_summary(github.comment_edits[-1][1])
    assert summary.status == "merged"
    assert summary.lines[0].endswith(
        "server_enforcement=none identity=configured-merger"
    )
    assert any(
        line.startswith(
            "single-writer-trace: writer=agent server_enforcement=none "
            "enabled_by=config:single_writer_merger "
            "writers=agent,org-owner,org-second write_deploy_keys=7 head="
        )
        for line in summary.lines
    )


@MODULES
@pytest.mark.parametrize("merger", ["agent", ""])
def test_both_copies_record_the_writer_list(
    module: dict[str, Any], merger: str
) -> None:
    """AC3/AC4: root and template read and trace every writer alike."""
    observed: dict[str, list[str]] = {}
    state, _reason = module["single_writer_eligibility"](
        THREE_ADMINS, "o/r", "agent", observed
    )
    assert state == "multiple-writers"
    lines = module["trace_lines"](
        {
            "server_enforcement": "none",
            "single_writer_merger": merger,
            "observed_writers": observed,
        },
        {"actor": "agent", "head_sha": "a" * 40},
        "suffix",
    )
    opt_in = (
        "enabled_by=config:single_writer_merger "
        "writers=agent,org-owner,org-second write_deploy_keys=7 "
    )
    assert lines == [
        "single-writer-trace: writer=agent server_enforcement=none "
        f"{opt_in if merger else ''}head={'a' * 40} suffix; no Ruleset "
        "enforced this merge, lifecycle revalidated every control"
    ]
