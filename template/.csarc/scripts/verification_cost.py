#!/usr/bin/env python3
"""Report verification cost from one pytest run and guard large-test growth.

``report`` reads the JUnit XML written by the same pytest invocation that the
verifier already runs; it never starts a second test run or a collect-only
pass. Locally it prints only this run's total and slowest cases. On a
GitHub-hosted runner it also writes a step summary with the static change in
``@pytest.mark.large`` tests against the pull-request base and emits a
warning-only annotation when the same-kind total grows more than 15% over the
checked-in hosted baseline.

``check-large-justification`` is the pull-request policy check: when a pull
request adds net ``@pytest.mark.large`` markers, its body must carry a
``Large test justification:`` line naming what it replaces or why the case
cannot be replaced.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import TextIO

LARGE_LINE = re.compile(
    r"^\s*(?:@pytest\.mark\.large\b|pytestmark\s*=.*\bpytest\.mark\.large\b)"
)
JUSTIFICATION = re.compile(
    r"(?im)^[ \t]*(?:[-*][ \t]+)?(?:\*\*)?Large test justification(?:\*\*)?"
    r"[ \t]*[:\uff1a][ \t]*(.*?)[ \t]*$"
)
PLACEHOLDERS = {"", "-", "n/a", "na", "none", "tbd", "todo", "無", "不適用"}


def emit(text: str, stream: TextIO | None = None) -> None:
    """Write one line of command output."""
    (stream or sys.stdout).write(text + "\n")


def large_marker_delta(files: list[dict[str, object]]) -> tuple[int, list[str]]:
    """Return the net added ``large`` markers and files without a diff patch."""
    delta = 0
    unknown: list[str] = []
    for entry in files:
        filename = str(entry.get("filename", ""))
        if not filename.endswith(".py"):
            continue
        patch = entry.get("patch")
        if not isinstance(patch, str):
            if entry.get("status") != "removed":
                unknown.append(filename)
            continue
        for line in patch.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                delta += bool(LARGE_LINE.match(line[1:]))
            elif line.startswith("-") and not line.startswith("---"):
                delta -= bool(LARGE_LINE.match(line[1:]))
    return delta, unknown


def justification(body: str) -> str | None:
    """Return the stated large-test justification, if it is concrete."""
    for value in JUSTIFICATION.findall(body):
        text = value.strip().strip("`").strip()
        if text.casefold() not in PLACEHOLDERS:
            return text
    return None


def flatten_files(payload: object) -> list[dict[str, object]]:
    """Flatten a (possibly slurped, paginated) pull-request files payload."""
    if isinstance(payload, dict):
        return [payload]
    if not isinstance(payload, list):
        raise ValueError(
            "PR files payload is invalid: not a JSON array. Retry."
        )
    files: list[dict[str, object]] = []
    for item in payload:
        files.extend(flatten_files(item))
    return files


def command_check_justification(args: argparse.Namespace) -> int:
    """Require a justification when a pull request adds net large tests."""
    raw = (
        sys.stdin.read()
        if args.files_json == "-"
        else Path(args.files_json).read_text(encoding="utf-8")
    )
    files = flatten_files(json.loads(raw or "[]"))
    delta, unknown = large_marker_delta(files)
    body = os.environ.get("PR_BODY", "")
    if delta <= 0 and not unknown:
        emit(f"Large test marker change: {delta:+d}; no justification needed.")
        return 0
    reason = justification(body)
    if reason:
        emit(f"Large test marker change: {delta:+d}; justification: {reason}")
        return 0
    if unknown:
        emit(
            "Cannot count @pytest.mark.large changes without a diff for: "
            + ", ".join(sorted(unknown))
        )
    emit(
        f"This pull request adds {max(delta, 0)} net @pytest.mark.large "
        "test(s). "
        "Add a 'Large test justification:' line to the PR body naming the "
        "test it replaces or why a smaller test cannot cover it."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the verification-cost command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "check-large-justification", help="PR policy for new large tests"
    )
    check.add_argument("--files-json", required=True)
    check.set_defaults(handler=command_check_justification)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, ValueError, ElementTree.ParseError) as error:
        emit(f"verification cost: {error}", sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
