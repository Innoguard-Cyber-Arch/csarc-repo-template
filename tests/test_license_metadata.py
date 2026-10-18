"""Tests for synchronized repository license declarations."""

from __future__ import annotations

import json
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


def provenance(root: Path, project_license: str) -> None:
    """Record the CLI's resolved render context for one license choice."""
    (root / ".csarc").mkdir(parents=True, exist_ok=True)
    (root / ".csarc/provenance.json").write_text(
        json.dumps(
            {"settings": {"context": {"project_license": project_license}}}
        ),
        encoding="utf-8",
    )


def test_custom_license_needs_no_rendered_license(tmp_path: Path) -> None:
    """Issue #1078: `custom` means the product adds its own LICENSE."""
    provenance(tmp_path, "custom")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "product"\n', encoding="utf-8"
    )
    validate(tmp_path)
    (tmp_path / ".csarc/provenance.json").unlink()
    # A raw Copier render: manifests without any license declaration.
    validate(tmp_path)


@pytest.mark.parametrize("recorded", ["proprietary", "MIT", "Apache-2.0"])
def test_other_licenses_still_require_license_file(
    tmp_path: Path, recorded: str
) -> None:
    """A missing LICENSE is never accepted for a starter license."""
    provenance(tmp_path, recorded)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "product"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="LICENSE is missing"):
        validate(tmp_path)


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("pyproject.toml", '[project]\nlicense = "MIT"\n'),
        ("package.json", '{"license": "UNLICENSED"}\n'),
        ("Cargo.toml", '[package]\nlicense-file = "LICENSE"\n'),
    ],
)
def test_raw_render_with_declared_license_requires_license_file(
    tmp_path: Path, name: str, text: str
) -> None:
    """Without provenance, a declared manifest license needs LICENSE."""
    (tmp_path / name).write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="LICENSE is missing"):
        validate(tmp_path)
