#!/usr/bin/env python3
"""Advance the reviewed Python feature release after its observation period."""

from __future__ import annotations

import argparse
import json
import logging
import re
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

PYTHON_RELEASES_API = (
    "https://www.python.org/api/v2/downloads/release/?is_published=true"
)
OBSERVATION_DAYS = 30
RELEASE_NAME = re.compile(r"^Python (3)\.(\d+)\.0$")
LOGGER = logging.getLogger(__name__)


def parse_version(value: str) -> tuple[int, int]:
    """Parse a Python feature release such as 3.14."""
    match = re.fullmatch(r"(\d+)\.(\d+)", value)
    if match is None:
        raise ValueError(f"Invalid Python feature release: {value}")
    return int(match.group(1)), int(match.group(2))


def format_version(version: tuple[int, int]) -> str:
    """Format a Python feature release."""
    return f"{version[0]}.{version[1]}"


def current_version(repo_root: Path) -> tuple[int, int]:
    """Read the current reviewed release from the profile catalog."""
    catalog = (repo_root / "profiles/catalog.yaml").read_text(encoding="utf-8")
    match = re.search(r'latest_reviewed_stable: "(3\.\d+)"', catalog)
    if match is None:
        raise RuntimeError("latest_reviewed_stable is missing")
    return parse_version(match.group(1))


def eligible_version(now: datetime) -> tuple[int, int]:
    """Return the newest official release older than the policy delay."""
    request = urllib.request.Request(
        PYTHON_RELEASES_API,
        headers={"User-Agent": "csarc-repo-template-version-policy"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        releases = json.load(response)

    cutoff = now - timedelta(days=OBSERVATION_DAYS)
    eligible: list[tuple[int, int]] = []
    for release in releases:
        match = RELEASE_NAME.fullmatch(release["name"])
        if match is None or release["pre_release"]:
            continue
        released_at = datetime.fromisoformat(
            release["release_date"].replace("Z", "+00:00")
        )
        if released_at <= cutoff:
            eligible.append((int(match.group(1)), int(match.group(2))))

    if not eligible:
        raise RuntimeError("No eligible Python 3 release found")
    return max(eligible)


def replace_once(path: Path, old: str, new: str) -> None:
    """Replace one required text fragment."""
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"Expected one match in {path}: {old!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def replace_all(path: Path, old: str, new: str) -> None:
    """Replace every required occurrence of a text fragment."""
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected a match in {path}: {old!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def add_minimum_choices(
    path: Path,
    current: tuple[int, int],
    target: tuple[int, int],
    indent: str,
    following: str,
) -> None:
    """Keep old compatibility choices and append newly stable releases."""
    current_text = format_version(current)
    additions = "".join(
        f'{indent}- "{current[0]}.{minor}"\n'
        for minor in range(current[1] + 1, target[1] + 1)
    )
    marker = f'{indent}- "{current_text}"\n{following}'
    replace_once(
        path, marker, f'{indent}- "{current_text}"\n{additions}{following}'
    )


def update_files(
    repo_root: Path,
    current: tuple[int, int],
    target: tuple[int, int],
) -> None:
    """Synchronize the runtime policy across the template repository."""
    if current[0] != target[0]:
        raise RuntimeError(
            "Automatic updates cannot cross a Python major version"
        )

    old = format_version(current)
    old_next = format_version((current[0], current[1] + 1))
    new = format_version(target)
    new_next = format_version((target[0], target[1] + 1))
    old_ruff = old.replace(".", "")
    new_ruff = new.replace(".", "")

    (repo_root / ".python-version").write_text(f"{new}\n", encoding="utf-8")
    (repo_root / "template/.python-version.jinja").write_text(
        f"{new}\n", encoding="utf-8"
    )

    pyproject = repo_root / "pyproject.toml"
    replace_once(pyproject, f">={old},<{old_next}", f">={new},<{new_next}")
    replace_once(
        pyproject,
        f'target-version = "py{old_ruff}"',
        f'target-version = "py{new_ruff}"',
    )
    replace_once(
        pyproject, f'python_version = "{old}"', f'python_version = "{new}"'
    )

    template_pyproject = repo_root / "template/pyproject.toml.jinja"
    replace_once(
        template_pyproject,
        f'python_target = "{old}" if',
        f'python_target = "{new}" if',
    )
    replace_once(
        template_pyproject,
        f">={old},<{old_next}",
        f">={new},<{new_next}",
    )

    copier = repo_root / "copier.yml"
    replace_once(copier, f"{{{{ '{old}' if", f"{{{{ '{new}' if")
    replace_once(
        copier,
        f"Latest stable only (Python {old})",
        f"Latest stable only (Python {new})",
    )
    add_minimum_choices(
        copier,
        current,
        target,
        "    ",
        '  default: "3.12"\n',
    )

    catalog = repo_root / "profiles/catalog.yaml"
    replace_once(
        catalog,
        f'latest_reviewed_stable: "{old}"',
        f'latest_reviewed_stable: "{new}"',
    )
    replace_once(
        catalog,
        f'requires_python: ">={old},<{old_next}"',
        f'requires_python: ">={new},<{new_next}"',
    )
    replace_all(
        catalog,
        f'development_runtime: "{old}"',
        f'development_runtime: "{new}"',
    )
    add_minimum_choices(
        catalog,
        current,
        target,
        "          ",
        f'        development_runtime: "{new}"\n',
    )

    replace_all(repo_root / "README.md", old, new)
    replace_all(repo_root / "template/README.md.jinja", old, new)
    for relative_path in (
        ".github/workflows/ci.yml",
        ".github/workflows/reusable-ci.yml",
        "scripts/verify-template.sh",
        "template/.github/workflows/ci.yml.jinja",
        "template/.github/workflows/release.yml.jinja",
        "template/scripts/verify.jinja",
    ):
        replace_all(repo_root / relative_path, old, new)


def main() -> None:
    """Update the repository when a release has cleared the delay."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--candidate",
        help="Use an explicit feature release, or 'next', for a test",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    current = current_version(repo_root)
    if args.candidate == "next":
        target = (current[0], current[1] + 1)
    elif args.candidate:
        target = parse_version(args.candidate)
    else:
        target = eligible_version(datetime.now(UTC))
    if target <= current:
        LOGGER.info("Python %s remains current.", format_version(current))
        return

    update_files(repo_root, current, target)
    LOGGER.info(
        "Updated Python %s to %s.",
        format_version(current),
        format_version(target),
    )


if __name__ == "__main__":
    main()
