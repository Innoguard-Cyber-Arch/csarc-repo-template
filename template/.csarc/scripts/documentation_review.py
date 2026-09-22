#!/usr/bin/env python3
"""Validate an AI-assisted documentation review recorded on a pull request."""

from __future__ import annotations

import argparse
import os
import re
import sys

FIELD = re.compile(
    r"(?im)^\s*-?\s*(Status|Reviewed head|Reason):\s*`?([^`\n]+?)`?\s*$"
)
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
PASSING = {"aligned", "not-applicable"}
BLOCKING = {"drift", "inconclusive"}


def parse_review(body: str) -> dict[str, str]:
    """Return normalized documentation-review fields from a PR body."""
    return {
        name.casefold().replace(" ", "_"): value.strip()
        for name, value in FIELD.findall(body)
    }


def validate_review(body: str, head_sha: str, mode: str) -> str:
    """Validate a review state against the exact pull-request head."""
    if mode == "off":
        return "Documentation review skipped because documentation_mode is off."
    fields = parse_review(body)
    status = fields.get("status", "")
    if status not in PASSING | BLOCKING:
        raise ValueError(
            "Documentation review status must be aligned, drift, "
            "not-applicable, or inconclusive."
        )
    reviewed_head = fields.get("reviewed_head", "").casefold()
    if (
        not FULL_SHA.fullmatch(reviewed_head)
        or reviewed_head != head_sha.casefold()
    ):
        raise ValueError(
            "Documentation review must name the exact 40-character PR head."
        )
    reason = fields.get("reason", "")
    if status == "not-applicable" and (
        not reason or reason.casefold().startswith(("replace", "todo", "tbd"))
    ):
        raise ValueError(
            "A not-applicable documentation review needs a concrete reason."
        )
    if status in BLOCKING:
        raise ValueError(
            f"Documentation review is {status}; update the project content "
            "or resolve the uncertainty before release."
        )
    return f"Documentation review is {status} for {reviewed_head}."


def main(argv: list[str] | None = None) -> int:
    """Read review inputs from arguments or pull-request policy variables."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        default=os.environ.get("DOCUMENTATION_MODE", "template-and-content"),
        choices=("template-and-content", "content-only", "off"),
    )
    parser.add_argument("--head", default=os.environ.get("PR_HEAD_SHA", ""))
    parser.add_argument("--body", default=os.environ.get("PR_BODY", ""))
    args = parser.parse_args(argv)
    try:
        message = validate_review(args.body, args.head, args.mode)
        sys.stdout.write(message + "\n")
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
