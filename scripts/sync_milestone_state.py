#!/usr/bin/env python3
"""Close or reopen a Milestone from its latest GitHub Issue counts."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess


def run_gh(arguments: list[str]) -> str:
    """Run GitHub CLI without a shell."""
    executable = shutil.which("gh")
    if executable is None:
        raise RuntimeError("GitHub CLI (gh) is required")
    result = subprocess.run(  # noqa: S603
        [executable, *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def acceptance_complete(description: str) -> bool:
    """Return whether every checkbox in the acceptance section is checked."""
    section = re.search(
        r"(?ms)^## Acceptance criteria\s*$\n(.*?)(?=^## |\Z)", description
    )
    if section is None:
        return False
    checkboxes = re.findall(r"(?m)^- \[([ xX])\] ", section.group(1))
    return bool(checkboxes) and all(mark.lower() == "x" for mark in checkboxes)


def desired_state(
    state: str, open_issues: int, criteria_complete: bool
) -> str | None:
    """Return the state transition required by the latest remote snapshot."""
    if open_issues == 0 and criteria_complete and state == "open":
        return "closed"
    if (open_issues > 0 or not criteria_complete) and state == "closed":
        return "open"
    return None


def sync(repo: str, number: int) -> str:
    """Read fresh Milestone state and apply only the required transition."""
    endpoint = f"repos/{repo}/milestones/{number}"
    milestone = json.loads(run_gh(["api", endpoint]))
    state = milestone.get("state")
    open_issues = milestone.get("open_issues")
    description = milestone.get("description")
    if (
        not isinstance(state, str)
        or state not in {"open", "closed"}
        or not isinstance(open_issues, int)
        or not isinstance(description, str)
    ):
        raise RuntimeError("GitHub returned invalid Milestone state")
    target = desired_state(state, open_issues, acceptance_complete(description))
    if target is None:
        return state
    run_gh(
        [
            "api",
            "--method",
            "PATCH",
            endpoint,
            "--raw-field",
            f"state={target}",
        ]
    )
    return target


def main() -> None:
    """Synchronize one Milestone selected by the workflow event."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--milestone", required=True, type=int)
    args = parser.parse_args()
    sync(args.repo, args.milestone)


if __name__ == "__main__":
    main()
