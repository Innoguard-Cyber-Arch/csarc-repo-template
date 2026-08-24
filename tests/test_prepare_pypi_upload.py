"""Tests for idempotent PyPI upload planning."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "prepare_pypi_upload.py")
)
PlanError = MODULE["PlanError"]
prepare_upload = MODULE["prepare_upload"]
sha256 = MODULE["sha256"]


def distributions(root: Path) -> list[Path]:
    """Create one wheel and source distribution fixture."""
    root.mkdir()
    wheel = root / "package-1.0-py3-none-any.whl"
    source = root / "package-1.0.tar.gz"
    wheel.write_bytes(b"wheel")
    source.write_bytes(b"source")
    return [wheel, source]


def metadata(paths: list[Path]) -> dict[str, object]:
    """Represent published PyPI files with their trusted digests."""
    return {
        "urls": [
            {"filename": path.name, "digests": {"sha256": sha256(path)}}
            for path in paths
        ]
    }


def test_new_release_uploads_both_distributions(tmp_path: Path) -> None:
    """A missing PyPI version requires both verified files."""
    artifacts = distributions(tmp_path / "verified")

    pending = prepare_upload(tmp_path / "verified", tmp_path / "upload", None)

    assert [path.name for path in pending] == sorted(
        path.name for path in artifacts
    )


def test_complete_rerun_uploads_nothing(tmp_path: Path) -> None:
    """A complete same-digest release is an idempotent no-op."""
    artifacts = distributions(tmp_path / "verified")

    pending = prepare_upload(
        tmp_path / "verified", tmp_path / "upload", metadata(artifacts)
    )

    assert pending == []


def test_partial_rerun_uploads_only_missing_distribution(
    tmp_path: Path,
) -> None:
    """A partial same-digest release resumes with only the missing file."""
    artifacts = distributions(tmp_path / "verified")

    pending = prepare_upload(
        tmp_path / "verified", tmp_path / "upload", metadata(artifacts[:1])
    )

    assert [path.name for path in pending] == [artifacts[1].name]


def test_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    """Never overwrite a filename whose published bytes differ."""
    artifacts = distributions(tmp_path / "verified")
    payload = metadata(artifacts)
    first = payload["urls"][0]
    assert isinstance(first, dict)
    first["digests"] = {"sha256": "0" * 64}

    with pytest.raises(PlanError, match="digest mismatch"):
        prepare_upload(tmp_path / "verified", tmp_path / "upload", payload)


def test_unexpected_published_distribution_fails_closed(
    tmp_path: Path,
) -> None:
    """Reject a PyPI version containing bytes absent from the release."""
    artifacts = distributions(tmp_path / "verified")
    payload = metadata(artifacts)
    urls = payload["urls"]
    assert isinstance(urls, list)
    urls.append(
        {
            "filename": "package-1.0-py2-none-any.whl",
            "digests": {"sha256": "0" * 64},
        }
    )

    with pytest.raises(PlanError, match="unexpected distributions"):
        prepare_upload(tmp_path / "verified", tmp_path / "upload", payload)
