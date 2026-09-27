#!/usr/bin/env python3
"""Carry one Dependabot Actions bump into template workflows (#1052).

Dependabot only edits root `.github/workflows/*.yml`. Byte-identical paired
copies are handled by `scripts/sync-paired-files.sh`, but templated
workflows (`template/.github/workflows/*.jinja`) and unpaired template
copies keep the previous pin, so `scripts/check_action_pins.py` fails.

This script reads only the root workflow change between two trusted Git
revisions, derives exactly one `old pin -> new pin` mapping per action, and
rewrites template workflow lines that use that exact old pin. An action whose
old or new pin is not unique fails closed instead of guessing.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT_WORKFLOWS = ".github/workflows"
TEMPLATE_WORKFLOW_PATTERNS = (
    "template/.github/workflows/*.yml",
    "template/.github/workflows/*.yaml",
    "template/.github/workflows/*.jinja",
)
USES = re.compile(
    r"^(?P<prefix>\s*(?:-\s+)?uses:\s*)"
    r"(?P<action>[\w.-]+/[\w.-]+(?:/[\w./-]+)?)@(?P<sha>[0-9a-f]{40})"
    r"(?P<space>\s*)(?:#\s*(?P<tag>\S+))?(?P<rest>.*)$"
)

Pin = tuple[str, str]


class AmbiguousPinError(ValueError):
    """Raised when one action has no single old or new pin."""


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", *arguments],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def pins(text: str) -> dict[str, set[Pin]]:
    """Map each pinned action to its distinct (sha, tag comment) pairs."""
    found: dict[str, set[Pin]] = {}
    for line in text.splitlines():
        match = USES.match(line)
        if match is not None:
            found.setdefault(match["action"], set()).add(
                (match["sha"], match["tag"] or "")
            )
    return found


def pin_changes(
    before: list[str], after: list[str]
) -> dict[str, tuple[Pin, Pin]]:
    """Return one exact old->new pin per action changed by the bump."""
    old: dict[str, set[Pin]] = {}
    new: dict[str, set[Pin]] = {}
    for text in before:
        for action, values in pins(text).items():
            old.setdefault(action, set()).update(values)
    for text in after:
        for action, values in pins(text).items():
            new.setdefault(action, set()).update(values)
    changes: dict[str, tuple[Pin, Pin]] = {}
    for action in sorted(set(old) | set(new)):
        if old.get(action, set()) == new.get(action, set()):
            continue
        if len(old.get(action, set())) != 1 or len(new.get(action, set())) != 1:
            raise AmbiguousPinError(
                f"{action}: the root bump has no single old and new pin"
            )
        (old_pin,) = old[action]
        (new_pin,) = new[action]
        changes[action] = (old_pin, new_pin)
    return changes


def rewrite(text: str, changes: dict[str, tuple[Pin, Pin]]) -> str:
    """Replace only lines that use an action's exact old pin."""
    lines = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        match = USES.match(body)
        change = changes.get(match["action"]) if match is not None else None
        if (
            match is not None
            and change is not None
            and (match["sha"], match["tag"] or "") == change[0]
        ):
            new_sha, new_tag = change[1]
            comment = f"# {new_tag}" if new_tag else ""
            body = (
                f"{match['prefix']}{match['action']}@{new_sha}"
                f"{match['space'] if comment else ''}{comment}{match['rest']}"
            )
        lines.append(body + ending)
    return "".join(lines)


def template_workflows(root: Path) -> list[Path]:
    """Return every template workflow file the pin check compares."""
    return sorted(
        path
        for pattern in TEMPLATE_WORKFLOW_PATTERNS
        for path in root.glob(pattern)
        if path.is_file()
    )


def root_workflow_texts(
    root: Path, base_rev: str, head_rev: str
) -> tuple[list[str], list[str]]:
    """Read the changed root workflows at both trusted revisions."""
    changed = _git(
        root, "diff", "--name-only", base_rev, head_rev, "--", ROOT_WORKFLOWS
    ).splitlines()
    before: list[str] = []
    after: list[str] = []
    for path in changed:
        if not re.fullmatch(r"\.github/workflows/[^/]+\.ya?ml", path):
            continue
        before.append(_git(root, "show", f"{base_rev}:{path}"))
        after.append(_git(root, "show", f"{head_rev}:{path}"))
    return before, after


def sync(root: Path, base_rev: str, head_rev: str) -> list[Path]:
    """Apply the bump's pin changes to template workflows; return edits."""
    before, after = root_workflow_texts(root, base_rev, head_rev)
    changes = pin_changes(before, after)
    edited = []
    for path in template_workflows(root):
        text = path.read_text(encoding="utf-8")
        updated = rewrite(text, changes)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            edited.append(path)
    return edited


def main(argv: list[str] | None = None) -> int:
    """Rewrite template workflow pins from one root workflow change."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-rev", required=True)
    parser.add_argument("--head-rev", required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        edited = sync(root, args.base_rev, args.head_rev)
    except (AmbiguousPinError, subprocess.CalledProcessError) as error:
        sys.stderr.write(f"template action pin sync failed: {error}\n")
        return 1
    for path in edited:
        sys.stdout.write(f"{path.relative_to(root)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
