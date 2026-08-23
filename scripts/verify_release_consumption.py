"""Validate a downloaded artifact against a verified GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

RELEASE_PREDICATE = "https://in-toto.io/attestation/release/v0.2"
RELEASE_SIGNER = "https://dotcom.releases.github.com"


class VerificationError(RuntimeError):
    """A release consumption policy failure."""


def mapping(value: object, label: str) -> Mapping[str, object]:
    """Return a JSON object or fail with its policy location."""
    if not isinstance(value, dict):
        raise VerificationError(f"Missing or invalid {label}.")
    return cast("Mapping[str, object]", value)


def sha256(path: Path) -> str:
    """Calculate one artifact digest without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        while chunk := artifact.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def subject_digest(
    statement: Mapping[str, object], key: str, value: str, algorithm: str
) -> str:
    """Read a digest from the uniquely identified attestation subject."""
    raw_subjects = statement.get("subject")
    if not isinstance(raw_subjects, list):
        raise VerificationError("Release attestation has no subjects.")
    matches = [
        mapping(subject, "release subject")
        for subject in raw_subjects
        if isinstance(subject, dict) and subject.get(key) == value
    ]
    if len(matches) != 1:
        raise VerificationError(
            f"Release attestation must contain exactly one {key}={value!r}."
        )
    digest = mapping(matches[0].get("digest"), "release subject digest").get(
        algorithm
    )
    if not isinstance(digest, str) or not digest:
        raise VerificationError(
            f"Release subject {value!r} has no {algorithm} digest."
        )
    return digest.lower()


def verify_consumption(
    payload: object,
    artifact: Path,
    *,
    repository: str,
    repository_id: str,
    tag: str,
    commit: str,
) -> dict[str, str]:
    """Enforce release signer, repository, tag, commit, and artifact digest."""
    root = mapping(payload, "release verification result")
    result = mapping(root.get("verificationResult"), "verificationResult")
    signature = mapping(result.get("signature"), "signature")
    certificate = mapping(signature.get("certificate"), "certificate")
    signer = certificate.get("subjectAlternativeName")
    if signer != RELEASE_SIGNER:
        raise VerificationError("Release signer identity mismatch.")

    timestamps = result.get("verifiedTimestamps")
    if not isinstance(timestamps, list) or not timestamps:
        raise VerificationError(
            "Release attestation has no verified timestamp."
        )

    statement = mapping(result.get("statement"), "statement")
    if statement.get("predicateType") != RELEASE_PREDICATE:
        raise VerificationError("Release attestation predicate mismatch.")
    predicate = mapping(statement.get("predicate"), "release predicate")
    expected_predicate = {
        "repository": repository,
        "repositoryId": repository_id,
        "tag": tag,
    }
    for key, expected in expected_predicate.items():
        if str(predicate.get(key)) != expected:
            raise VerificationError(f"Release {key} identity mismatch.")

    expected_purl = f"pkg:github/{repository}@{tag}"
    attested_commit = subject_digest(statement, "uri", expected_purl, "sha1")
    if attested_commit != commit.lower():
        raise VerificationError("Release commit identity mismatch.")

    actual_digest = sha256(artifact)
    attested_digest = subject_digest(statement, "name", artifact.name, "sha256")
    if attested_digest != actual_digest:
        raise VerificationError("Downloaded artifact digest mismatch.")

    return {
        "artifact": artifact.name,
        "artifact_sha256": actual_digest,
        "commit_sha": commit.lower(),
        "predicate_type": RELEASE_PREDICATE,
        "repository": repository,
        "repository_id": repository_id,
        "signer": RELEASE_SIGNER,
        "tag": tag,
        "verification": "verified",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the explicit trust boundary inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verification-json", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Validate one downloaded artifact and emit reusable JSON evidence."""
    args = parse_args(argv)
    try:
        payload = json.loads(args.verification_json.read_text(encoding="utf-8"))
        evidence = verify_consumption(
            payload,
            args.artifact,
            repository=args.repository,
            repository_id=args.repository_id,
            tag=args.tag,
            commit=args.commit,
        )
    except (OSError, json.JSONDecodeError, VerificationError) as error:
        sys.stderr.write(f"Release consumption verification failed: {error}\n")
        return 1
    serialized = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(serialized)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
