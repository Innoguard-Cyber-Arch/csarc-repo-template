#!/usr/bin/env python3
"""Every `uses: owner/repo@sha` pin must agree across the repo (#755).

Dependabot only scans real `.yml`/`.yaml` files, never the `.jinja`
workflow templates under `template/.github/workflows/` -- it cannot
parse Jinja syntax, so those never get a bump PR at all.
`.github/workflows/dependabot-auto-merge.yml`'s `sync-template` job keeps
root and template's byte-identical *paired* workflow copies in sync
automatically (Issue #755), but a `.jinja` file is never byte-identical
to anything (it renders differently per language selection), so it needs
its own check: every pin of the same action anywhere in the repository
must agree, or this fails closed and names exactly which file fell
behind and what the majority pin already is.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

USES = re.compile(
    r"^\s*(?:-\s+)?uses:\s*([\w.-]+/[\w.-]+(?:/[\w./-]+)?)@([0-9a-f]{40})",
    re.MULTILINE,
)


def find_pins(paths: list[Path]) -> dict[str, list[tuple[Path, str]]]:
    """Map each action name to every (file, sha) pin found for it."""
    pins: dict[str, list[tuple[Path, str]]] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in USES.finditer(text):
            action, sha = match.group(1), match.group(2)
            pins.setdefault(action, []).append((path, sha))
    return pins


def check(paths: list[Path], root: Path) -> list[str]:
    """Return one message per action whose pins disagree across the repo."""
    errors = []
    for action, occurrences in sorted(find_pins(paths).items()):
        shas = {sha for _, sha in occurrences}
        if len(shas) <= 1:
            continue
        majority_sha, _ = Counter(sha for _, sha in occurrences).most_common(1)[
            0
        ]
        stale = sorted(
            str(path.relative_to(root))
            for path, sha in occurrences
            if sha != majority_sha
        )
        errors.append(
            f"{action}: {', '.join(stale)} pin a different commit than "
            f"the rest of the repo (majority: {majority_sha})"
        )
    return errors


def workflow_files(root: Path) -> list[Path]:
    """Return every workflow-shaped file this check should compare."""
    patterns = (
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
        "template/.github/workflows/*.yml",
        "template/.github/workflows/*.yaml",
        "template/.github/workflows/*.jinja",
    )
    return sorted(
        path
        for pattern in patterns
        for path in root.glob(pattern)
        if path.is_file()
    )


def main(argv: list[str] | None = None) -> int:
    """Fail closed and list every action whose pins disagree."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    args = parser.parse_args(argv)
    errors = check(workflow_files(args.root), args.root)
    if errors:
        for error in errors:
            sys.stderr.write(f"action pin drift: {error}\n")
        return 1
    sys.stdout.write("Action pins agree across the repository.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
