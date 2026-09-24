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
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

GROWTH_WARNING_RATIO = 0.15
BASELINE_PATH = "tests/verification-cost-baseline.json"
LARGE_PROPERTY = ("csarc_marker", "large")
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


@dataclass(frozen=True)
class Case:
    """One executed test case and its wall time in seconds."""

    name: str
    seconds: float
    large: bool


@dataclass
class RunSummary:
    """Cost facts derived from one pytest JUnit XML report."""

    total_seconds: float = 0.0
    tests: int = 0
    failures: int = 0
    skipped: int = 0
    cases: list[Case] = field(default_factory=list)

    @property
    def large_executed(self) -> int:
        """Return how many executed cases carried the ``large`` marker."""
        return sum(1 for case in self.cases if case.large)

    def slowest(self, limit: int) -> list[Case]:
        """Return the slowest cases, longest first."""
        return sorted(self.cases, key=lambda case: case.seconds, reverse=True)[
            :limit
        ]


def parse_junit(text: str) -> RunSummary:
    """Parse pytest JUnit XML into totals and per-case durations."""
    root = ElementTree.fromstring(text)  # noqa: S314 - local pytest output
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    summary = RunSummary()
    for suite in suites:
        summary.total_seconds += float(suite.get("time", "0") or 0)
        summary.tests += int(suite.get("tests", "0") or 0)
        summary.failures += int(suite.get("failures", "0") or 0) + int(
            suite.get("errors", "0") or 0
        )
        summary.skipped += int(suite.get("skipped", "0") or 0)
        for case in suite.iter("testcase"):
            classname = case.get("classname", "")
            name = case.get("name", "")
            large = any(
                (prop.get("name"), prop.get("value")) == LARGE_PROPERTY
                for prop in case.iter("property")
            )
            summary.cases.append(
                Case(
                    name=f"{classname}::{name}" if classname else name,
                    seconds=float(case.get("time", "0") or 0),
                    large=large,
                )
            )
    return summary


def growth_warning(
    total_seconds: float, baseline_seconds: float | None
) -> str | None:
    """Return a warning message when the total grows past the threshold."""
    if not baseline_seconds or baseline_seconds <= 0:
        return None
    ratio = total_seconds / baseline_seconds - 1
    if ratio <= GROWTH_WARNING_RATIO:
        return None
    return (
        f"pytest total {total_seconds:.1f}s is {ratio:.0%} above the hosted "
        f"baseline {baseline_seconds:.1f}s (warning threshold "
        f"{GROWTH_WARNING_RATIO:.0%}); explain or offset the added cost."
    )


def count_large_markers(text: str) -> int:
    """Count ``large`` marker declarations in Python source text."""
    return sum(1 for line in text.splitlines() if LARGE_LINE.match(line))


def _git(*args: str) -> str | None:
    """Run a read-only git command, returning stdout or None on failure."""
    # Keep syntax runnable by the runner's system python3 (the PR policy job
    # has no setup-python step), so avoid Python 3.14-only constructs here.
    try:
        result = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def static_large_count(ref: str | None) -> int | None:
    """Count ``large`` markers under tests/ at a git ref or the work tree."""
    args = ["grep", "-h", "-E", "pytest\\.mark\\.large"]
    if ref:
        args.append(ref)
    output = _git(*args, "--", "tests/*.py")
    if output is None:
        # git grep exits 1 when nothing matches; confirm the ref exists.
        if ref and _git(
            "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"
        ):
            return 0
        return None if ref else 0
    return count_large_markers(output)


def resolve_merge_base(base: str) -> str | None:
    """Resolve the merge base between HEAD and a pull-request base branch."""
    base = base.removeprefix("refs/heads/").removeprefix("origin/")
    if not base:
        return None
    for candidate in (
        f"refs/remotes/origin/{base}",
        f"refs/heads/{base}",
        base,
    ):
        if _git("rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"):
            merge_base = _git("merge-base", candidate, "HEAD")
            return merge_base.strip() if merge_base else None
    return None


def load_baseline(
    suite: str, merge_base: str | None, path: Path
) -> tuple[dict[str, object] | None, str]:
    """Load the same-kind baseline, preferring the trusted base commit copy."""
    text = None
    source = "none"
    if merge_base:
        text = _git("show", f"{merge_base}:{BASELINE_PATH}")
        if text is not None:
            source = f"base commit {merge_base[:12]}"
    if text is None and path.is_file():
        text = path.read_text(encoding="utf-8")
        source = "candidate (not yet on base)"
    if text is None:
        return None, source
    entry = json.loads(text).get("suites", {}).get(suite)
    return (entry if isinstance(entry, dict) else None), source


def render_local(summary: RunSummary, label: str, top: int) -> str:
    """Render the local terminal summary: this run only, no comparison."""
    lines = [
        f"[verification-cost] {label}: pytest total "
        f"{summary.total_seconds:.1f}s, {summary.tests} tests, "
        f"{summary.large_executed} large executed",
        f"[verification-cost] slowest {min(top, len(summary.cases))} cases:",
    ]
    lines.extend(
        f"  {case.seconds:8.2f}s  {case.name}"
        + ("  [large]" if case.large else "")
        for case in summary.slowest(top)
    )
    return "\n".join(lines)


def render_hosted(
    summary: RunSummary,
    label: str,
    top: int,
    base_large: int | None,
    head_large: int | None,
    baseline: dict[str, object] | None,
    baseline_source: str,
    warning: str | None,
) -> str:
    """Render the GitHub step-summary Markdown section."""
    if base_large is None or head_large is None:
        large_change = "n/a (base not resolvable)"
    else:
        large_change = (
            f"{base_large} → {head_large} ({head_large - base_large:+d})"
        )
    if baseline is None:
        comparison = "no same-kind baseline; bounded subsets vary by scope"
    else:
        baseline_seconds = float(str(baseline.get("pytest_seconds", 0)))
        change = summary.total_seconds / baseline_seconds - 1
        comparison = (
            f"{baseline_seconds:.1f}s from {baseline.get('source', 'unknown')} "
            f"via {baseline_source}; change {change:+.0%}"
        )
    lines = [
        f"### Verification cost — {label}",
        "",
        f"- pytest total: {summary.total_seconds:.1f}s "
        f"({summary.tests} tests, {summary.skipped} skipped)",
        f"- `large` tests executed in this run: {summary.large_executed}",
        f"- `@pytest.mark.large` markers vs PR base: {large_change}",
        f"- Hosted baseline: {comparison}",
    ]
    if warning:
        lines.append(f"- ⚠️ {warning}")
    lines.extend(["", "| Seconds | Test |", "| ---: | --- |"])
    lines.extend(
        f"| {case.seconds:.2f} | `{case.name}`"
        + (" (large)" if case.large else "")
        + " |"
        for case in summary.slowest(top)
    )
    return "\n".join(lines) + "\n\n"


def command_report(args: argparse.Namespace) -> int:
    """Summarize one pytest JUnit report for local or hosted output."""
    summary = parse_junit(Path(args.junit).read_text(encoding="utf-8"))
    emit(render_local(summary, args.label, args.top))
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if os.environ.get("GITHUB_ACTIONS") != "true" or not step_summary:
        return 0
    merge_base = resolve_merge_base(os.environ.get("CSARC_CI_BASE", ""))
    base_large = static_large_count(merge_base) if merge_base else None
    head_large = static_large_count(None)
    baseline, baseline_source = load_baseline(
        args.suite, merge_base, Path(BASELINE_PATH)
    )
    warning = None
    if baseline is not None:
        warning = growth_warning(
            summary.total_seconds, float(str(baseline.get("pytest_seconds", 0)))
        )
    if warning:
        emit(f"::warning title=Verification cost growth::{warning}")
    with Path(step_summary).open("a", encoding="utf-8") as handle:
        handle.write(
            render_hosted(
                summary,
                args.label,
                args.top,
                base_large,
                head_large,
                baseline,
                baseline_source,
                warning,
            )
        )
    return 0


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
        raise ValueError("Pull request files payload must be a JSON array.")
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
    report = commands.add_parser("report", help="summarize one pytest run")
    report.add_argument("--junit", required=True)
    report.add_argument("--label", required=True)
    report.add_argument("--suite", required=True, choices=("fast", "full"))
    report.add_argument("--top", type=int, default=10)
    report.set_defaults(handler=command_report)
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
