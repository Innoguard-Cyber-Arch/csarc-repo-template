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
    """Never accept manifests that contradict the LICENSE native source."""
    (tmp_path / "LICENSE").write_text(
        "MIT License\n\nCopyright (c) Example Owner\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nlicense = "LicenseRef-Proprietary"\n'
        'license-files = ["LICENSE"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match LICENSE"):
        validate(tmp_path)


def test_product_owned_license_text_is_not_interpreted(tmp_path: Path) -> None:
    """A LICENSE outside the CSARC starters is custom and product-owned."""
    (tmp_path / "LICENSE").write_text(
        "GNU GENERAL PUBLIC LICENSE\nVersion 3\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nlicense = "GPL-3.0-only"\n', encoding="utf-8"
    )

    validate(tmp_path)


def test_missing_license_fails_closed(tmp_path: Path) -> None:
    """Project metadata verification still requires a LICENSE file."""
    with pytest.raises(ValueError, match="LICENSE is missing"):
        validate(tmp_path)
