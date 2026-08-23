"""Tests for release artifact consumption verification."""

from __future__ import annotations

import hashlib
import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "verify_release_consumption.py")
)
VerificationError = MODULE["VerificationError"]
verify_consumption = MODULE["verify_consumption"]

REPOSITORY = "owner/repository"
REPOSITORY_ID = "1234"
TAG = "v1.2.3"
COMMIT = "a" * 40


def release_verification(artifact: Path) -> dict[str, object]:
    """Build the minimum shape emitted by gh release verify."""
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return {
        "verificationResult": {
            "signature": {
                "certificate": {
                    "subjectAlternativeName": (
                        "https://dotcom.releases.github.com"
                    )
                }
            },
            "verifiedTimestamps": [{"type": "TimestampAuthority"}],
            "statement": {
                "predicateType": (
                    "https://in-toto.io/attestation/release/v0.2"
                ),
                "predicate": {
                    "repository": REPOSITORY,
                    "repositoryId": REPOSITORY_ID,
                    "tag": TAG,
                },
                "subject": [
                    {
                        "uri": f"pkg:github/{REPOSITORY}@{TAG}",
                        "digest": {"sha1": COMMIT},
                    },
                    {
                        "name": artifact.name,
                        "digest": {"sha256": digest},
                    },
                ],
            },
        }
    }


def verify(payload: object, artifact: Path) -> dict[str, str]:
    """Apply the fixed policy used by all tests."""
    return verify_consumption(
        payload,
        artifact,
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        tag=TAG,
        commit=COMMIT,
    )


def test_verifies_downloaded_artifact_identity_and_digest(
    tmp_path: Path,
) -> None:
    """Accept the exact artifact covered by the expected release identity."""
    artifact = tmp_path / "package.whl"
    artifact.write_bytes(b"trusted artifact")

    evidence = verify(release_verification(artifact), artifact)

    assert evidence["artifact"] == artifact.name
    assert evidence["repository"] == REPOSITORY
    assert evidence["verification"] == "verified"


def test_rejects_missing_attestation(tmp_path: Path) -> None:
    """Fail closed when cryptographic release verification is absent."""
    artifact = tmp_path / "package.whl"
    artifact.write_bytes(b"trusted artifact")

    with pytest.raises(VerificationError, match="verificationResult"):
        verify({}, artifact)


def test_rejects_wrong_repository_identity(tmp_path: Path) -> None:
    """Fail closed when the signed repository identity differs."""
    artifact = tmp_path / "package.whl"
    artifact.write_bytes(b"trusted artifact")
    payload = release_verification(artifact)
    result = payload["verificationResult"]
    assert isinstance(result, dict)
    statement = result["statement"]
    assert isinstance(statement, dict)
    predicate = statement["predicate"]
    assert isinstance(predicate, dict)
    predicate["repository"] = "attacker/repository"

    with pytest.raises(VerificationError, match="repository identity"):
        verify(payload, artifact)


def test_rejects_tampered_artifact(tmp_path: Path) -> None:
    """Fail closed when downloaded bytes no longer match the attestation."""
    artifact = tmp_path / "package.whl"
    artifact.write_bytes(b"trusted artifact")
    payload = release_verification(artifact)
    artifact.write_bytes(b"tampered artifact")

    with pytest.raises(VerificationError, match="artifact digest"):
        verify(payload, artifact)
