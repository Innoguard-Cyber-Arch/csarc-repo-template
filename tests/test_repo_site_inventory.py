"""Regression coverage for the repo-site slide inventory (Issue #1088)."""

from __future__ import annotations

import json
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "check-repo-site-inventory"
INVENTORY = ROOT / "site" / "data" / "slide_inventory.json"
MODULE = runpy.run_path(str(SCRIPT))
check = MODULE["check"]
load_inventory = MODULE["load_inventory"]
BUILD = runpy.run_path(str(ROOT / "scripts" / "build_repo_site.py"))["build"]

# Slides the retired site/legacy/index.html snapshot required (its
# keys-only parity set, with `capability` already renamed to `index`), so
# the inventory provably keeps everything the snapshot used to protect.
LEGACY_REQUIRED_KEYS = {
    "access-control",
    "agents",
    "benchmark",
    "index",
    "deploy",
    "docs-site",
    "fleet-governance-thresholds",
    "fleet-inventory",
    "flow",
    "governance",
    "method",
    "pr",
    "principles",
    "rollout",
    "spec-format",
    "supply",
}


def _copy_content(tmp_path: Path) -> Path:
    content = tmp_path / "content"
    shutil.copytree(ROOT / "site" / "content", content)
    return content


def test_real_sources_and_rendered_pages_match_inventory(
    tmp_path: Path,
) -> None:
    outputs = BUILD(ROOT, tmp_path / "dist/repo-site")
    candidates = [outputs["zh-tw"], outputs["en"]]
    assert check(INVENTORY, ROOT / "site" / "content", candidates) == []


def test_inventory_keeps_every_slide_the_legacy_snapshot_required() -> None:
    keys = {entry[0] for entry in load_inventory(INVENTORY)}
    assert keys >= LEGACY_REQUIRED_KEYS


def test_reordered_slide_in_one_language_fails(tmp_path: Path) -> None:
    content = _copy_content(tmp_path)
    english = content / "_index.en.md"
    text = english.read_text(encoding="utf-8")
    first = text.index('{{< slide key="method"')
    second = text.index('{{< slide key="agents"')
    end = text.index('{{< slide key="contract"')
    swapped = text[:first] + text[second:end] + text[first:second] + text[end:]
    english.write_text(swapped, encoding="utf-8")

    problems = check(INVENTORY, content, [])
    assert len(problems) == 1
    assert "_index.en.md: order differs" in problems[0]


def test_changed_track_in_one_language_fails(tmp_path: Path) -> None:
    content = _copy_content(tmp_path)
    chinese = content / "_index.zh-tw.md"
    text = chinese.read_text(encoding="utf-8")
    chinese.write_text(
        text.replace('key="supply" track="supply"', 'key="supply" track="x"'),
        encoding="utf-8",
    )

    problems = check(INVENTORY, content, [])
    assert problems == [
        f"{chinese}: slide 'supply' has track/audience ('x', None), "
        "inventory says ('supply', None)"
    ]


def test_missing_rendered_section_fails(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text(
        '<section class="slide markdown-slide" id="index" '
        'data-content-key="index" data-track="index">\n',
        encoding="utf-8",
    )

    problems = check(INVENTORY, ROOT / "site" / "content", [page])
    assert len(problems) == 1
    assert problems[0].startswith(f"{page}: missing=['install', 'about'")


def test_inventory_rejects_duplicate_and_unknown_fields(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        json.dumps({"slides": [{"key": "a"}, {"key": "a"}]}), encoding="utf-8"
    )
    unknown = tmp_path / "unknown.json"
    unknown.write_text(
        json.dumps({"slides": [{"key": "a", "title": "A"}]}), encoding="utf-8"
    )
    for path in (duplicate, unknown):
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(SCRIPT), "--inventory", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        assert result.stderr.startswith("ERROR: ")
        assert "is invalid" in result.stderr


def test_cli_passes_on_real_sources() -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "slides match in 2 sources and 0 pages" in result.stdout
