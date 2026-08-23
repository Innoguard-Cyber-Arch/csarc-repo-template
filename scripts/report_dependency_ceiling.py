#!/usr/bin/env python3
"""Report whether each direct dev dependency can reach its PyPI latest.

Scope boundary: this script only answers "does the uv resolver accept the
latest published version given the rest of the dependency graph" (a resolver
lower/upper-bound question). It intentionally does not implement, and must
not grow into, a new-version observation window or known-vulnerability gate:
those are Dependabot's cooldown, pnpm's minimumReleaseAge/trustPolicy, OSV-
Scanner's job today, or a future single Renovate configuration per the
dependency-risk decision recorded in docs/index.html (the "supply" track).
Keep this module free of that overlap even after that mechanism changes.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

DEPENDENCY_NAME = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?(.*)$")


def dev_dependencies(repo_root: Path) -> list[tuple[str, str]]:
    """Read direct development dependency names and declared ranges."""
    with (repo_root / "pyproject.toml").open("rb") as pyproject:
        data = tomllib.load(pyproject)
    groups = data.get("dependency-groups")
    if not isinstance(groups, dict):
        raise RuntimeError("dependency-groups is missing from pyproject.toml")
    dependencies = groups.get("dev")
    if not isinstance(dependencies, list):
        raise RuntimeError(
            "dependency-groups.dev is missing from pyproject.toml"
        )

    parsed: list[tuple[str, str]] = []
    for dependency in dependencies:
        if not isinstance(dependency, str):
            raise RuntimeError("Every dev dependency must be a string")
        match = DEPENDENCY_NAME.fullmatch(dependency)
        if match is None:
            raise RuntimeError(f"Cannot parse dev dependency: {dependency}")
        parsed.append((match.group(1), match.group(2)))
    return parsed


def pypi_latest(package: str) -> str:
    """Read the latest published version reported by PyPI."""
    encoded = urllib.parse.quote(package, safe="")
    request = urllib.request.Request(
        f"https://pypi.org/pypi/{encoded}/json",
        headers={"User-Agent": "csarc-repo-template-ceiling-report"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.load(response)
    version = payload.get("info", {}).get("version")
    if not isinstance(version, str):
        raise RuntimeError(f"PyPI did not return a version for {package}")
    return version


def resolve_latest(
    repo_root: Path,
    package: str,
    version: str,
    python_version: str,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    """Ask uv whether the requested package version fits the whole graph."""
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required")
    return subprocess.run(  # noqa: S603
        [
            uv,
            "pip",
            "compile",
            "pyproject.toml",
            "--group",
            "dev",
            "--python-version",
            python_version,
            "--upgrade-package",
            f"{package}=={version}",
            "--output-file",
            str(output),
        ],
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=True,
    )


def main() -> None:
    """Write a Markdown dependency ceiling report to standard output."""
    repo_root = Path(__file__).resolve().parents[1]
    python_version = (
        (repo_root / ".python-version").read_text(encoding="utf-8").strip()
    )
    rows: list[str] = []
    conflicts: list[str] = []

    with tempfile.TemporaryDirectory() as temporary_directory:
        output_root = Path(temporary_directory)
        for package, declared_range in dev_dependencies(repo_root):
            latest = pypi_latest(package)
            result = resolve_latest(
                repo_root,
                package,
                latest,
                python_version,
                output_root / f"{package}.txt",
            )
            status = "可解析" if result.returncode == 0 else "被相依條件阻擋"
            rows.append(
                f"| `{package}` | `{declared_range}` | `{latest}` | {status} |"
            )
            if result.returncode != 0:
                diagnostic = html.escape(result.stderr.strip())
                conflicts.append(
                    f"<details><summary>{package} {latest} 衝突鏈</summary>"
                    f"<pre>{diagnostic}</pre></details>"
                )

    report = [
        "## Dev dependency ceiling report",
        "",
        f"Python `{python_version}`: 由 uv resolver 實際解析。這不是漏洞掃描。",
        "",
        "| Direct dependency | Declared range | PyPI latest | Result |",
        "| --- | --- | --- | --- |",
        *rows,
    ]
    if conflicts:
        report.extend(["", "### Resolver conflict chains", "", *conflicts])
    sys.stdout.write("\n".join(report) + "\n")


if __name__ == "__main__":
    main()
