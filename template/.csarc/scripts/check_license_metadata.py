#!/usr/bin/env python3
"""Check that project license declarations agree across package ecosystems.

LICENSE is the native source of the license and copyright holder (SPEC-009,
Issue #1071): they are one-time seeds, never saved settings. A LICENSE that
is not one of the CSARC starter texts is product-owned (``custom``), and only
the starter licenses are compared with package manifests.
"""

from __future__ import annotations

import json
import runpy
import sys
import tomllib
from pathlib import Path

Manifests = dict[str, dict]
LICENSE_KEYS = ("license", "license-file", "license-files")
READERS = (
    ("pyproject.toml", lambda text: tomllib.loads(text)["project"]),
    ("Cargo.toml", lambda text: tomllib.loads(text)["package"]),
    ("package.json", json.loads),
)


def validate_license_file(path: Path, kind: str, holder: str) -> None:
    """Validate the human-readable license file."""
    license_text = path.read_text(encoding="utf-8")
    if holder not in license_text:
        raise ValueError(
            "Bad LICENSE: it lacks copyright_holder. Add the holder to LICENSE."
        )
    if kind == "proprietary":
        if "All rights reserved" not in license_text:
            raise ValueError(
                "Bad LICENSE: it must reserve all rights. "
                "Add 'All rights reserved'."
            )
        return
    if not license_text.startswith(f"{kind.split('-')[0]} License"):
        raise ValueError(
            f"Bad LICENSE: it lacks {kind}. Run 'csarc update' to rewrite it."
        )


def manifests(root: Path) -> Manifests:
    """Return the license-bearing table of each present product manifest."""
    return {
        name: read((root / name).read_text(encoding="utf-8"))
        for name, read in READERS
        if (root / name).is_file()
    }


def require_custom(root: Path, found: Manifests) -> None:
    """Accept a missing LICENSE only for a recorded `custom` choice (#1078)."""
    try:
        text = (root / ".csarc/provenance.json").read_text(encoding="utf-8")
        context = json.loads(text)["settings"]["context"]
        custom = context["project_license"] == "custom"
    except (OSError, ValueError, KeyError, TypeError):
        # A raw Copier render: `custom` manifests declare no license.
        found_keys = (k for m in found.values() for k in LICENSE_KEYS if k in m)
        custom = bool(found) and next(found_keys, None) is None
    if not custom:
        raise ValueError(
            "LICENSE is missing: no custom license. "
            "Run 'csarc update' to add it."
        )


def validate_manifests(found: Manifests, project_license: str) -> None:
    """Validate Python, npm, and Cargo metadata against LICENSE."""
    proprietary = project_license == "proprietary"
    spdx = "LicenseRef-Proprietary" if proprietary else project_license
    npm = "UNLICENSED" if proprietary else project_license
    python = found.get("pyproject.toml")
    if python is not None and python.get("license") != spdx:
        raise ValueError(
            "Bad pyproject.toml: does not match LICENSE. "
            "Set 'license' to match."
        )
    if python is not None and "LICENSE" not in python.get("license-files", []):
        raise ValueError(
            "Bad pyproject.toml: LICENSE unpackaged. Add it to 'license-files'."
        )
    node = found.get("package.json")
    if node is not None and node.get("license") != npm:
        raise ValueError(
            "Bad package.json: does not match LICENSE. Set 'license' to match."
        )
    if node is not None and proprietary and node.get("private") is not True:
        raise ValueError(
            "Bad package.json: private is not true. Set 'private' to true."
        )
    cargo = found.get("Cargo.toml")
    if cargo is not None and proprietary:
        if cargo.get("license-file") != "LICENSE" or "license" in cargo:
            raise ValueError(
                "Bad Cargo.toml: proprietary mismatch. Use only 'license-file'."
            )
    elif cargo is not None and cargo.get("license") != project_license:
        raise ValueError(
            "Bad Cargo.toml: does not match LICENSE. Set 'license' to match."
        )


def validate(root: Path) -> None:
    """Reject a missing or contradictory project license declaration."""
    script_dir = Path(__file__).resolve().parent
    license_facts = runpy.run_path(str(script_dir / "csarc_config.py"))[
        "license_facts"
    ]
    if not (root / "LICENSE").is_file():
        return require_custom(root, manifests(root))
    project_license, holder = license_facts(root)
    if project_license == "custom":
        return  # A product-owned license text: CSARC does not interpret it.
    if not isinstance(holder, str) or not holder.strip():
        raise ValueError(
            "Bad LICENSE: it names no copyright holder. Add one to LICENSE."
        )
    validate_license_file(root / "LICENSE", project_license, holder)
    validate_manifests(manifests(root), project_license)


def main() -> int:
    """Validate the current repository."""
    try:
        validate(Path.cwd())
    except (KeyError, OSError, ValueError, tomllib.TOMLDecodeError) as error:
        sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write("OK: License metadata is synchronized.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
