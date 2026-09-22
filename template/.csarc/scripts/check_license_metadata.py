#!/usr/bin/env python3
"""Check that project license declarations agree across package ecosystems."""

from __future__ import annotations

import json
import runpy
import sys
import tomllib
from pathlib import Path


def expected_identifiers(project_license: str) -> tuple[str, str]:
    """Return the SPDX/Python and npm identifiers for one project license."""
    if project_license == "proprietary":
        return "LicenseRef-Proprietary", "UNLICENSED"
    return project_license, project_license


def validate_license_file(
    path: Path, project_license: str, holder: str
) -> None:
    """Validate the human-readable license file."""
    if not path.is_file():
        raise ValueError("LICENSE is missing")
    license_text = path.read_text(encoding="utf-8")
    if holder not in license_text:
        raise ValueError("LICENSE does not name copyright_holder")
    if project_license == "proprietary":
        if "All rights reserved" not in license_text:
            raise ValueError("proprietary LICENSE must reserve all rights")
        return
    license_name = f"{project_license.split('-')[0]} License"
    if not license_text.startswith(license_name):
        raise ValueError(f"LICENSE does not contain {project_license}")


def validate_python(path: Path, expected: str) -> None:
    """Validate Python package metadata when present."""
    if not path.is_file():
        return
    project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    if project.get("license") != expected:
        raise ValueError("pyproject.toml license does not match config")
    if "LICENSE" not in project.get("license-files", []):
        raise ValueError("pyproject.toml must package LICENSE")


def validate_node(path: Path, expected: str, proprietary: bool) -> None:
    """Validate npm package metadata when present."""
    if not path.is_file():
        return
    package = json.loads(path.read_text(encoding="utf-8"))
    if package.get("license") != expected:
        raise ValueError("package.json license does not match config")
    if proprietary and package.get("private") is not True:
        raise ValueError("proprietary npm packages must set private=true")


def validate_cargo(path: Path, project_license: str) -> None:
    """Validate Cargo package metadata when present."""
    if not path.is_file():
        return
    package = tomllib.loads(path.read_text(encoding="utf-8"))["package"]
    if project_license == "proprietary":
        if package.get("license-file") != "LICENSE" or "license" in package:
            raise ValueError("Cargo.toml proprietary license is inconsistent")
    elif package.get("license") != project_license:
        raise ValueError("Cargo.toml license does not match config")


def validate(root: Path) -> None:
    """Reject a missing or contradictory project license declaration."""
    script_dir = Path(__file__).resolve().parent
    load_config = runpy.run_path(str(script_dir / "csarc_config.py"))[
        "load_config"
    ]
    config = load_config(root / ".csarc/config.yml")
    project_license = str(config["project_license"])
    holder = config.get("copyright_holder")
    if not isinstance(holder, str) or not holder.strip():
        raise ValueError("copyright_holder must be declared")
    license_path = root / "LICENSE"
    validate_license_file(license_path, project_license, holder)
    spdx_license, npm_license = expected_identifiers(project_license)
    validate_python(root / "pyproject.toml", spdx_license)
    validate_node(
        root / "package.json",
        npm_license,
        project_license == "proprietary",
    )
    validate_cargo(root / "Cargo.toml", project_license)


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
