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
        raise ValueError("LICENSE does not name copyright_holder")
    if kind == "proprietary":
        if "All rights reserved" not in license_text:
            raise ValueError("proprietary LICENSE must reserve all rights")
        return
    if not license_text.startswith(f"{kind.split('-')[0]} License"):
        raise ValueError(f"LICENSE does not contain {kind}")


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
        raise ValueError("LICENSE is missing")


def validate_manifests(found: Manifests, project_license: str) -> None:
    """Validate Python, npm, and Cargo metadata against LICENSE."""
    proprietary = project_license == "proprietary"
    spdx = "LicenseRef-Proprietary" if proprietary else project_license
    npm = "UNLICENSED" if proprietary else project_license
    python = found.get("pyproject.toml")
    if python is not None and python.get("license") != spdx:
        raise ValueError("pyproject.toml license does not match LICENSE")
    if python is not None and "LICENSE" not in python.get("license-files", []):
        raise ValueError("pyproject.toml must package LICENSE")
    node = found.get("package.json")
    if node is not None and node.get("license") != npm:
        raise ValueError("package.json license does not match LICENSE")
    if node is not None and proprietary and node.get("private") is not True:
        raise ValueError("proprietary npm packages must set private=true")
    cargo = found.get("Cargo.toml")
    if cargo is not None and proprietary:
        if cargo.get("license-file") != "LICENSE" or "license" in cargo:
            raise ValueError("Cargo.toml proprietary license is inconsistent")
    elif cargo is not None and cargo.get("license") != project_license:
        raise ValueError("Cargo.toml license does not match LICENSE")


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
        raise ValueError("LICENSE does not name a copyright holder")
    validate_license_file(root / "LICENSE", project_license, holder)
    validate_manifests(manifests(root), project_license)


def main() -> int:
    """Validate the current repository."""
    try:
        validate(Path.cwd())
    except (KeyError, OSError, ValueError, tomllib.TOMLDecodeError) as error:
        sys.stderr.write(f"License metadata invalid: {error}\n")
        return 1
    sys.stdout.write("License metadata is synchronized.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
