"""Tests for the one-time historical Release migration."""

from __future__ import annotations

import runpy
from pathlib import Path

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "migrate_retired_releases.py")
)
RETIRED_RELEASES = MODULE["RETIRED_RELEASES"]
deletion_errors = MODULE["deletion_errors"]
plan_identity_errors = MODULE["plan_identity_errors"]
release_identity_errors = MODULE["release_identity_errors"]


def release(index: int, *, immutable: bool = True) -> dict[str, object]:
    """Return one verified replacement fixture."""
    item = RETIRED_RELEASES[index]
    return {
        "tagName": item.replacement_tag,
        "targetCommitish": item.commit,
        "tagCommit": item.commit,
        "isDraft": False,
        "isPrerelease": True,
        "isImmutable": immutable,
        "attestationVerified": True,
        "assets": [{"name": "release-evidence.json"}],
    }


def plan() -> dict[str, object]:
    """Return the exact checked-in migration identity set."""
    return {
        "schemaVersion": 1,
        "repository": "Innoguard-Cyber-Arch/csarc-repo-template",
        "releases": [
            {
                "sourceTag": item.source_tag,
                "replacementTag": item.replacement_tag,
                "commit": item.commit,
            }
            for item in RETIRED_RELEASES
        ],
    }


def test_exact_retired_release_mapping_is_stable() -> None:
    """Never infer or broaden the four-item historical migration."""
    mapping = [
        (item.source_tag, item.replacement_tag) for item in RETIRED_RELEASES
    ]
    assert mapping == [
        ("v0.18.0-alpha.1", "v0.18.0-beta.1"),
        ("v0.19.0-alpha.1", "v0.19.0-beta.1"),
        ("v0.20.0-alpha.1", "v0.20.0-beta.1"),
        ("v0.21.0-alpha.1", "v0.21.0-beta.1"),
    ]


def test_verified_replacements_unlock_the_exact_deletion_plan() -> None:
    """Allow deletion only after all four replacements verify."""
    replacements = {
        item.replacement_tag: release(index)
        for index, item in enumerate(RETIRED_RELEASES)
    }
    assert deletion_errors(plan(), replacements) == []


def test_plan_rejects_any_unplanned_history() -> None:
    """The migration is an exact one-time map, never a legacy parser."""
    payload = plan()
    payload["releases"][0]["commit"] = "0" * 40
    assert plan_identity_errors(payload) == [
        "v0.18.0-alpha.1: commit changed since plan"
    ]


def test_missing_or_mutable_replacement_fails_closed() -> None:
    """Preserve source history if any replacement is absent or mutable."""
    replacements = {
        item.replacement_tag: release(index)
        for index, item in enumerate(RETIRED_RELEASES)
    }
    replacements.pop(RETIRED_RELEASES[0].replacement_tag)
    replacements[RETIRED_RELEASES[1].replacement_tag] = release(
        1, immutable=False
    )
    errors = deletion_errors(plan(), replacements)
    assert any("Release is missing" in error for error in errors)
    assert any("isImmutable=False" in error for error in errors)


def test_release_identity_rejects_wrong_commit_or_attestation() -> None:
    """A matching label never substitutes for exact provenance."""
    candidate = release(0)
    candidate["tagCommit"] = "0" * 40
    candidate["attestationVerified"] = False
    errors = release_identity_errors(
        candidate, RETIRED_RELEASES[0], replacement=True
    )
    assert any("tag does not resolve" in error for error in errors)
    assert any("lack verified attestation" in error for error in errors)
