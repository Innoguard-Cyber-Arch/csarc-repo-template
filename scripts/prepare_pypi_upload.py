"""Select verified distributions that are not already present on PyPI."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast


class PlanError(RuntimeError):
    """A fail-closed PyPI upload planning error."""


def sha256(path: Path) -> str:
    """Calculate one distribution digest."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def published_digests(payload: object | None) -> dict[str, str]:
    """Extract the published filename-to-SHA-256 mapping."""
    if payload is None:
        return {}
    if not isinstance(payload, dict) or not isinstance(
        payload.get("urls"), list
    ):
        raise PlanError("PyPI metadata must contain a urls list.")

    result: dict[str, str] = {}
    for raw_file in payload["urls"]:
        if not isinstance(raw_file, dict):
            raise PlanError("PyPI metadata contains an invalid file entry.")
        file = cast("Mapping[str, object]", raw_file)
        filename = file.get("filename")
        digests = file.get("digests")
        if not isinstance(filename, str) or not isinstance(digests, dict):
            raise PlanError("PyPI metadata contains an invalid file identity.")
        digest = digests.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise PlanError(f"PyPI has no SHA-256 digest for {filename}.")
        previous = result.setdefault(filename, digest.lower())
        if previous != digest.lower():
            raise PlanError(
                f"PyPI returned conflicting digests for {filename}."
            )
    return result


def prepare_upload(
    verified_dir: Path,
    upload_dir: Path,
    payload: object | None,
) -> list[Path]:
    """Copy missing distributions and reject published digest conflicts."""
    artifacts = sorted(
        path
        for path in verified_dir.iterdir()
        if path.is_file()
        and (path.suffix == ".whl" or path.name.endswith(".tar.gz"))
    )
    if (
        len(artifacts) != 2
        or not any(path.suffix == ".whl" for path in artifacts)
        or not any(path.name.endswith(".tar.gz") for path in artifacts)
    ):
        raise PlanError(
            "Expected exactly one wheel and one source distribution."
        )
    if upload_dir.exists() and any(upload_dir.iterdir()):
        raise PlanError("PyPI upload directory must be empty.")
    upload_dir.mkdir(parents=True, exist_ok=True)

    published = published_digests(payload)
    pending: list[Path] = []
    for artifact in artifacts:
        actual = sha256(artifact)
        expected = published.get(artifact.name)
        if expected is not None:
            if expected != actual:
                raise PlanError(
                    f"Published PyPI digest mismatch for {artifact.name}."
                )
            continue
        destination = upload_dir / artifact.name
        shutil.copy2(artifact, destination)
        pending.append(destination)
    return pending


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse explicit verified input and upload output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verified-dir", required=True, type=Path)
    parser.add_argument("--upload-dir", required=True, type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Prepare the minimal idempotent upload set."""
    args = parse_args(argv)
    try:
        payload = (
            json.loads(args.metadata.read_text(encoding="utf-8"))
            if args.metadata is not None
            else None
        )
        pending = prepare_upload(args.verified_dir, args.upload_dir, payload)
    except (OSError, json.JSONDecodeError, PlanError) as error:
        sys.stderr.write(f"PyPI upload planning failed: {error}\n")
        return 1

    required = "true" if pending else "false"
    output = f"publish_required={required}\n"
    if args.github_output is None:
        sys.stdout.write(output)
    else:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write(output)
    for artifact in pending:
        sys.stdout.write(f"PyPI upload pending: {artifact.name}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
