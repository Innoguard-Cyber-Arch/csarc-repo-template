"""Tests for synchronized repository license declarations."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
validate = runpy.run_path(str(ROOT / "scripts" / "check_license_metadata.py"))[
    "validate"
]


def test_root_license_metadata_is_synchronized() -> None:
    """Keep the template repository's own closed license explicit."""
    validate(ROOT)


def test_existing_license_conflict_fails_closed(tmp_path: Path) -> None:
    """Never accept a preserved license that contradicts the declaration."""
    (tmp_path / ".csarc").mkdir()
    (tmp_path / ".csarc/config.yml").write_text(
        "project_license: proprietary\ncopyright_holder: Example Owner\n",
        encoding="utf-8",
    )
    (tmp_path / "LICENSE").write_text(
        "MIT License\n\nCopyright (c) Example Owner\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="reserve all rights"):
        validate(tmp_path)
