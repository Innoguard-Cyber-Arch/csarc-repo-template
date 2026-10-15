#!/usr/bin/env python3
"""Measure generated-project payload against the #1058 Targets (#1077).

Renders the fixed Targets fixtures from the working-tree template and
reports file counts, `.csarc/scripts` counts and lines, bytes, workflows,
and `.csarc/docs` sizes. `tests/test_generated_payload.py` asserts each
measure stays within its recorded ceiling, so payload can only shrink; the
ceiling never relaxes a Target, it only records where this head stands.

Usage:
  scripts/generated_payload.py [--json] [FIXTURE ...]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BASE_DATA: dict[str, object] = {
    "project_name": "Payload Fixture",
    "project_slug": "payload-fixture",
    "project_description": "Measures the generated payload.",
    "repository_url": "https://github.com/example/payload-fixture",
    "security_reporting_channel": "Use the private security contact.",
}
# `solo-local` as #1058 decision 14 expands it for an empty folder.
SOLO_LOCAL: dict[str, object] = {
    "verification_mode": "local",
    "documentation_mode": "content-only",
    "documentation_languages": "zh-tw",
    "lifecycle": [],
    "scheduled_checks": [],
    "languages": [],
}
ADOPTED_HOSTED: dict[str, object] = {
    "project_mode": "existing",
    "release_ownership": "product-owned",
    "verification_mode": "hosted",
    "documentation_mode": "content-only",
    "documentation_languages": "zh-tw",
    "languages": ["python"],
}
FIXTURES: dict[str, dict[str, object]] = {
    "solo-default": dict(SOLO_LOCAL),
    "solo-python": {**SOLO_LOCAL, "languages": ["python"]},
    "hosted-csarc-owned-python": {
        "verification_mode": "hosted",
        "release_ownership": "csarc-owned",
        "documentation_mode": "content-only",
        "documentation_languages": "zh-tw",
        "languages": ["python"],
    },
    "consumer-a": {
        **ADOPTED_HOSTED,
        "scheduled_checks": ["governance-drift", "template-update"],
    },
    "consumer-b": {**ADOPTED_HOSTED, "scheduled_checks": []},
}
# #1058 Targets; `None` means the tracker sets no budget for that measure.
TARGETS: dict[str, dict[str, int | None]] = {
    "solo-default": {
        "files": 80,
        "scripts": 42,
        "script_lines": 16_500,
        "bytes": 700_000,
        "workflows": 0,
    },
    "solo-python": {
        "files": 85,
        "scripts": 43,
        "script_lines": 17_000,
        "bytes": 760_000,
        "workflows": 0,
    },
    "hosted-csarc-owned-python": {
        "files": 137,
        "scripts": None,
        "script_lines": 28_600,
        "bytes": None,
        "workflows": None,
    },
    "consumer-a": {
        "files": 121,
        "scripts": 57,
        "script_lines": 23_900,
        "bytes": None,
        "workflows": 13,
    },
    "consumer-b": {
        "files": 117,
        "scripts": 55,
        "script_lines": 23_700,
        "bytes": None,
        "workflows": 11,
    },
}
# Measured at the #1077 head (bytes rounded up to 10 KB), plus K1's
# (#1079) exact allowance per fixture: +1 file, +1 `.csarc/scripts`,
# +400 script lines (`risk_controls.py` and its wiring). P2 left no room
# to offset it, so the cut is a follow-up Issue; any other change may only
# lower these. The gap to TARGETS stays open until the remaining cuts land
# (#1058 kill criterion 4). K2 (#1080) adds exactly +1 measured script line per
# fixture: the optional `github_project_url` entry and its default in the
# shared settings parser; its Project sync stays CLI-only.
CEILINGS: dict[str, dict[str, int]] = {
    "solo-default": {
        "files": 96,
        "scripts": 57,
        "script_lines": 28_818,
        "bytes": 1_370_000,
        "workflows": 0,
    },
    "solo-python": {
        "files": 99,
        "scripts": 57,
        "script_lines": 28_835,
        "bytes": 1_370_000,
        "workflows": 0,
    },
    "hosted-csarc-owned-python": {
        "files": 120,
        "scripts": 63,
        "script_lines": 30_181,
        "bytes": 1_520_000,
        "workflows": 13,
    },
    "consumer-a": {
        "files": 106,
        "scripts": 56,
        "script_lines": 27_839,
        "bytes": 1_420_000,
        "workflows": 12,
    },
    "consumer-b": {
        "files": 102,
        "scripts": 54,
        "script_lines": 27_656,
        "bytes": 1_410_000,
        "workflows": 10,
    },
}
DOC_TARGETS: dict[str, int] = {
    "solo_docs_lines": 600,
    "solo_docs_bytes": 60_000,
    "solo_ci_policy_lines": 300,
    "hosted_ci_policy_lines": 360,
    "agent_workflow_lines": 90,
    "agent_workflow_bytes": 12_000,
    "milestone_description_lines": 90,
}


def line_count(path: Path) -> int:
    """Return the number of lines in one file."""
    return len(path.read_bytes().splitlines())


def measure(project: Path) -> dict[str, int]:
    """Return the payload measures of one rendered project."""
    files = [path for path in project.rglob("*") if path.is_file()]
    scripts = [
        path
        for path in (project / ".csarc/scripts").glob("*")
        if path.is_file()
    ]
    docs = [
        path for path in (project / ".csarc/docs").glob("*") if path.is_file()
    ]
    workflows = list((project / ".github/workflows").glob("*.yml"))

    def doc_lines(name: str) -> int:
        path = project / ".csarc/docs" / name
        return line_count(path) if path.is_file() else 0

    agent = project / ".csarc/docs/agent-workflow.md"
    return {
        "files": len(files),
        "scripts": len(scripts),
        "script_lines": sum(line_count(path) for path in scripts),
        "bytes": sum(path.stat().st_size for path in files),
        "workflows": len(workflows),
        "docs_lines": sum(line_count(path) for path in docs),
        "docs_bytes": sum(path.stat().st_size for path in docs),
        "ci_policy_lines": doc_lines("ci-policy.md"),
        "agent_workflow_lines": doc_lines("agent-workflow.md"),
        "agent_workflow_bytes": agent.stat().st_size if agent.is_file() else 0,
        "milestone_description_lines": doc_lines("milestone-description.md"),
    }


def template_copy(destination: Path) -> Path:
    """Copy the working-tree template so uncommitted edits are measured."""
    shutil.copy2(ROOT / "copier.yml", destination / "copier.yml")
    shutil.copytree(
        ROOT / "template",
        destination / "template",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return destination


def render(source: Path, target: Path, data: dict[str, object]) -> Path:
    """Render one fixture without Copier tasks (no network, no lockfile)."""
    from copier import run_copy

    run_copy(
        str(source),
        target,
        data={**BASE_DATA, **data},
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        quiet=True,
    )
    return target


def measure_fixtures(names: list[str]) -> dict[str, dict[str, int]]:
    """Render and measure each named fixture in a temporary directory."""
    with tempfile.TemporaryDirectory(prefix="csarc-payload-") as temporary:
        workdir = Path(temporary)
        source = workdir / "source"
        source.mkdir()
        template_copy(source)
        return {
            name: measure(render(source, workdir / name, FIXTURES[name]))
            for name in names
        }


def main(argv: list[str] | None = None) -> int:
    """Print the payload table for the requested fixtures."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fixtures", nargs="*", metavar="FIXTURE")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    unknown = sorted(set(args.fixtures) - set(FIXTURES))
    if unknown:
        parser.error(f"unknown fixtures: {', '.join(unknown)}")
    names = args.fixtures or list(FIXTURES)
    results = measure_fixtures(names)
    write = sys.stdout.write
    if args.json:
        write(json.dumps(results, indent=2, sort_keys=True) + "\n")
        return 0
    columns = ("files", "scripts", "script_lines", "bytes", "workflows")
    write("| Fixture | " + " | ".join(columns) + " | docs lines/bytes |\n")
    write("| --- |" + " ---: |" * (len(columns) + 1) + "\n")
    for name, values in results.items():
        cells = []
        for column in columns:
            target = TARGETS[name][column]
            cells.append(
                f"{values[column]:,}"
                + (f" (≤ {target:,})" if target is not None else "")
            )
        docs = f"{values['docs_lines']:,} / {values['docs_bytes']:,}"
        write(f"| {name} | " + " | ".join(cells) + f" | {docs} |\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
