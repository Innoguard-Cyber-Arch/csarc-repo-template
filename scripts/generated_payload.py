#!/usr/bin/env python3
"""Measure generated-project payload against its budgets (#1077, #1231).

Renders the fixed fixtures from the working-tree template, or from a
committed template with `--ref`, and reports each budgeted measure: file
count, canonical bytes (the backstop), workflows with write permissions or
`pull_request_target`, agent document tokens, and canonical runtime bytes
per capability group. Raw bytes, script counts, and script lines are
printed for reference only. `tests/test_generated_payload.py` asserts each
measure stays within its budget; a budget may only shrink.

`churn --since TAG` renders each fixture from TAG and from the working tree
and prints the changed files and lines. It is advisory and never fails.

Usage:
  scripts/generated_payload.py [--json] [--ref REF] [FIXTURE ...]
  scripts/generated_payload.py churn --since TAG [FIXTURE ...]
"""

from __future__ import annotations

import argparse
import ast
import difflib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
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
HOSTED: dict[str, object] = {
    "verification_mode_private": "hosted",
    "verification_mode_public": "hosted",
}
# The `solo-local` preset as #1058 decision 14 expands it for an empty folder.
SOLO_LOCAL: dict[str, object] = {
    "verification_mode_private": "local",
    "verification_mode_public": "local",
    "documentation_mode": "content-only",
    "documentation_languages": "zh-tw",
    "lifecycle": [],
    "scheduled_checks": [],
    "languages": [],
}
# SPEC-011 (ADR self-hosted-verification Q2): `solo-default` measures the
# `solo-self-hosted` default preset (#1272); `solo-local` keeps the former
# local default on the same budgets.
SOLO_SELF_HOSTED: dict[str, object] = {
    **SOLO_LOCAL,
    "verification_mode_private": "self-hosted",
    "verification_mode_public": "hosted",
}
ADOPTED_HOSTED: dict[str, object] = {
    "project_mode": "existing",
    "release_ownership": "product-owned",
    **HOSTED,
    "documentation_mode": "content-only",
    "documentation_languages": "zh-tw",
    "languages": ["python"],
}
FIXTURES: dict[str, dict[str, object]] = {
    "solo-default": dict(SOLO_SELF_HOSTED),
    "solo-local": dict(SOLO_LOCAL),
    "solo-python": {**SOLO_LOCAL, "languages": ["python"]},
    "hosted-csarc-owned-python": {
        **HOSTED,
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

# #1231 backstop: the #1058 raw-bytes Targets converted to canonical bytes
# at one fixed point. At CONVERSION_REF each offset is the measured raw
# bytes minus canonical bytes; the backstop is the raw Target minus that
# offset, rounded down to 1,000 B, so the headroom at the conversion point
# matches the old rule and no raw Target was raised.
CONVERSION_REF = "cd0b69d"
RAW_TARGETS: dict[str, int] = {
    "solo-default": 1_000_000,
    "solo-local": 1_000_000,
    "solo-python": 1_010_000,
    "hosted-csarc-owned-python": 1_200_000,
    "consumer-a": 1_050_000,
    "consumer-b": 1_050_000,
}
CONVERSION_OFFSETS: dict[str, int] = {
    "solo-default": 215_456,
    "solo-local": 215_456,
    "solo-python": 215_476,
    "hosted-csarc-owned-python": 278_881,
    "consumer-a": 229_124,
    "consumer-b": 228_687,
}
# Every per-fixture budget (#1231). A later change may only lower these;
# raising one needs an ADR revision and owner approval, as #1267 did for the
# solo agent_doc_tokens (2026-10-25).
TARGETS: dict[str, dict[str, int]] = {
    "solo-default": {
        "files": 92,
        "canonical_bytes": 784_000,
        "write_workflows": 0,
        "pull_request_target_workflows": 0,
        "agent_doc_tokens": 14_000,
    },
    "solo-local": {
        "files": 92,
        "canonical_bytes": 784_000,
        "write_workflows": 0,
        "pull_request_target_workflows": 0,
        "agent_doc_tokens": 14_000,
    },
    "solo-python": {
        "files": 95,
        "canonical_bytes": 794_000,
        "write_workflows": 0,
        "pull_request_target_workflows": 0,
        "agent_doc_tokens": 14_000,
    },
    "hosted-csarc-owned-python": {
        "files": 126,
        "canonical_bytes": 921_000,
        "write_workflows": 10,
        "pull_request_target_workflows": 5,
        "agent_doc_tokens": 15_500,
    },
    "consumer-a": {
        "files": 112,
        "canonical_bytes": 820_000,
        "write_workflows": 9,
        "pull_request_target_workflows": 5,
        "agent_doc_tokens": 15_000,
    },
    "consumer-b": {
        "files": 108,
        "canonical_bytes": 821_000,
        "write_workflows": 7,
        "pull_request_target_workflows": 5,
        "agent_doc_tokens": 15_000,
    },
}
# #1231 runtime accounts: each `.csarc/scripts` file belongs to exactly one
# capability group. A script missing here is counted as unassigned and fails
# the payload test, so new runtime code must be booked to a group.
RUNTIME_GROUPS: dict[str, frozenset[str]] = {
    "pr-lifecycle": frozenset(
        {
            "check-scope-gate",
            "finalization-queue",
            "merge_trace.py",
            "pr_lifecycle.py",
            "pr_lifecycle_hosted.py",
            "request-reviewer",
            "review_gate.py",
            "risk_controls.py",
            "trusted_executor.py",
            "validate-pr-policy",
        }
    ),
    "release": frozenset(
        {
            "check-release-drift",
            "converge-release-tag",
            "publish-release",
            "release_bundle.py",
            "release_candidate.py",
            "release_level.py",
            "release_phase.py",
            "release_policy.py",
            "release_writer.py",
            "verify-release-candidate",
            "verify_release_consumption.py",
        }
    ),
    "milestone-issue": frozenset(
        {
            "delivery_sync.py",
            "detect-open-milestone",
            "gh-issue-develop",
            "gh-issue-edit",
            "promotion_gate.py",
            "spec_to_issue.py",
            "sync_milestone_state.py",
            "sync_milestone_state_hosted.py",
            "sync_work_item_metadata.py",
            "validate-issue-policy",
            "validate-issue-title",
        }
    ),
    "verification": frozenset(
        {
            "check-message-style",
            "check-project-metadata",
            "check-trusted-verification",
            "check_action_pins.py",
            "check_license_metadata.py",
            "ci_tier.py",
            "detect-language-profile",
            "documentation_review.py",
            "evidence_freshness.py",
            "install-tool",
            "lint-workflows-shell",
            "local_verification.py",
            "resolve-cache-root",
            "scan-secrets",
            "self_hosted_evidence.py",
            "verification-step",
            "verification_cost.py",
            "verification_evidence.py",
            "verify",
            "verify-dependencies",
            "verify-fast",
        }
    ),
    "settings-drift": frozenset(
        {
            "__init__.py",
            "apply-repository-settings.sh",
            "check-governance-drift",
            "check-template-update",
            "check-update-conflicts",
            "cleanup-worktrees",
            "csarc_config.py",
            "repository_facts.py",
            "stale_branch_detection.py",
        }
    ),
    "dependabot": frozenset(
        {"authenticate_dependabot_head.py", "authenticate_dependabot_hosted.py"}
    ),
    # Rendered only with `documentation_mode: site`, which no budget
    # fixture selects, so this group is measured but has no budget.
    "docs-site": frozenset(
        {
            "build-repo-site",
            "build_repo_site.py",
            "check-repo-site-navigation",
            "check-repo-site-translations",
            "check-repo-site-versions",
            "render_site.py",
            "repo_site_blocks.py",
        }
    ),
}
# Canonical runtime bytes per budgeted group, checked against every fixture.
RUNTIME_GROUP_BUDGETS: dict[str, int] = {
    "pr-lifecycle": 266_000,
    "release": 166_000,
    "milestone-issue": 130_000,
    "verification": 101_000,
    "settings-drift": 87_000,
    "dependabot": 18_000,
}
# Issue #1177, re-based by #1231: a render whose remaining room under its
# backstop drops below one file or 20 KB is flagged. The warning never
# changes a budget or the exit status; it asks the change to free room.
HEADROOM_WARNING: dict[str, int] = {"files": 1, "canonical_bytes": 20_000}
# #1058 Targets, documentation line budget: solo `.csarc/docs` in total,
# `ci-policy.md` for solo and hosted csarc-owned python, `agent-workflow.md`
# in a local render, and `milestone-description.md` wherever it renders.
# #1231 replaced the two bytes budgets with `agent_doc_tokens`.
DOC_TARGETS: dict[str, int] = {
    "solo_docs_lines": 600,
    "solo_ci_policy_lines": 300,
    "hosted_ci_policy_lines": 360,
    "agent_workflow_lines": 90,
    "milestone_description_lines": 90,
}
# CJK ideographs, kana, hangul, and full-width forms count one token each.
CJK = re.compile(r"[　-鿿가-힯＀-￯]")
# Provenance Copier rewrites on every render; churn ignores it.
CHURN_IGNORED = frozenset({".copier-answers.yml"})


def line_count(path: Path) -> int:
    """Return the number of lines in one file."""
    return len(path.read_bytes().splitlines())


def is_python(path: Path) -> bool:
    """Return whether one runtime file is Python by suffix or shebang."""
    if path.suffix == ".py":
        return True
    first = path.read_bytes().split(b"\n", 1)[0]
    return first.startswith(b"#!") and b"python" in first


def _drop_docstrings(tree: ast.AST) -> None:
    """Remove module, class, and function docstrings in place."""
    scopes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, scopes):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]


def canonical_bytes(path: Path) -> int:
    """Return the canonical code bytes of one runtime file (#1231).

    Python is parsed, stripped of docstrings, and unparsed, so comments,
    blank lines, wrapping, and quoting do not count. Other runtime files
    count their non-blank lines that are not `#` comments. Each kept line
    counts its stripped UTF-8 bytes plus one newline.
    """
    text = path.read_text(encoding="utf-8")
    if is_python(path):
        tree = ast.parse(text)
        _drop_docstrings(tree)
        lines = ast.unparse(tree).splitlines()
    else:
        lines = [
            line
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    return sum(len(line.strip().encode()) + 1 for line in lines)


def estimated_tokens(text: str) -> int:
    """Estimate tokens: one per CJK character, one per four other characters."""
    cjk = len(CJK.findall(text))
    rest = len(text) - cjk
    return cjk + -(-rest // 4)


def workflow_permissions(project: Path) -> dict[str, int]:
    """Count workflows that grant a write scope or run `pull_request_target`."""
    import yaml

    write = target = 0
    for workflow in sorted((project / ".github/workflows").glob("*.y*ml")):
        data = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        # YAML 1.1 reads the bare `on` key as boolean true.
        triggers = data.get(True, data.get("on")) or {}
        if isinstance(triggers, str):
            triggers = [triggers]
        grants = [data.get("permissions")] + [
            (job or {}).get("permissions")
            for job in (data.get("jobs") or {}).values()
        ]
        write += any(
            grant == "write-all"
            or (isinstance(grant, dict) and "write" in grant.values())
            for grant in grants
        )
        target += "pull_request_target" in triggers
    return {"write_workflows": write, "pull_request_target_workflows": target}


def runtime_group(name: str) -> str | None:
    """Return the capability group of one runtime file, or None."""
    return next(
        (group for group, names in RUNTIME_GROUPS.items() if name in names),
        None,
    )


def measure(project: Path) -> dict[str, int]:
    """Return the payload measures of one rendered project."""
    files = [path for path in project.rglob("*") if path.is_file()]
    scripts = sorted(
        path
        for path in (project / ".csarc/scripts").glob("*")
        if path.is_file()
    )
    docs = [
        path for path in (project / ".csarc/docs").glob("*") if path.is_file()
    ]
    agent_docs = [project / "AGENTS.md", *sorted(docs)]
    workflows = list((project / ".github/workflows").glob("*.yml"))

    def doc_lines(name: str) -> int:
        path = project / ".csarc/docs" / name
        return line_count(path) if path.is_file() else 0

    raw = sum(path.stat().st_size for path in files)
    groups = dict.fromkeys(RUNTIME_GROUPS, 0)
    unassigned = 0
    script_raw = script_canonical = 0
    for path in scripts:
        size = canonical_bytes(path)
        script_raw += path.stat().st_size
        script_canonical += size
        group = runtime_group(path.name)
        if group is None:
            unassigned += 1
        else:
            groups[group] += size
    agent = project / ".csarc/docs/agent-workflow.md"
    return {
        "files": len(files),
        "scripts": len(scripts),
        "script_lines": sum(line_count(path) for path in scripts),
        "bytes": raw,
        "canonical_bytes": raw - script_raw + script_canonical,
        "workflows": len(workflows),
        **workflow_permissions(project),
        "agent_doc_tokens": sum(
            estimated_tokens(path.read_text(encoding="utf-8"))
            for path in agent_docs
            if path.suffix == ".md" and path.is_file()
        ),
        **{f"runtime:{group}": size for group, size in groups.items()},
        "runtime_unassigned": unassigned,
        "docs_lines": sum(line_count(path) for path in docs),
        "docs_bytes": sum(path.stat().st_size for path in docs),
        "ci_policy_lines": doc_lines("ci-policy.md"),
        "agent_workflow_lines": doc_lines("agent-workflow.md"),
        "agent_workflow_bytes": agent.stat().st_size if agent.is_file() else 0,
        "milestone_description_lines": doc_lines("milestone-description.md"),
    }


def budget_failures(name: str, values: dict[str, int]) -> list[str]:
    """Return one line per budget the fixture exceeds (#1231)."""
    limits = {
        **TARGETS[name],
        **{f"runtime:{g}": size for g, size in RUNTIME_GROUP_BUDGETS.items()},
        "runtime_unassigned": 0,
    }
    return [
        f"{name} {measure} {values[measure]:,} > {limit:,}"
        for measure, limit in limits.items()
        if values[measure] > limit
    ]


def low_headroom(results: dict[str, dict[str, int]]) -> dict[str, str]:
    """Return each fixture whose backstop headroom is low, with details."""
    found = {}
    for name, values in results.items():
        low = [
            f"{measure} {TARGETS[name][measure] - values[measure]:,} "
            f"(< {minimum:,})"
            for measure, minimum in HEADROOM_WARNING.items()
            if TARGETS[name][measure] - values[measure] < minimum
        ]
        if low:
            found[name] = ", ".join(low)
    return found


def headroom_warnings(results: dict[str, dict[str, int]]) -> list[str]:
    """Return one warning per fixture whose backstop headroom is low."""
    return [
        f"WARNING: {name} payload headroom is low: {low}. "
        "Free room before adding generated payload."
        for name, low in low_headroom(results).items()
    ]


def template_copy(destination: Path) -> Path:
    """Copy the working-tree template so uncommitted edits are measured."""
    shutil.copy2(ROOT / "copier.yml", destination / "copier.yml")
    shutil.copytree(
        ROOT / "template",
        destination / "template",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return destination


def template_at_ref(ref: str, destination: Path, root: Path = ROOT) -> Path:
    """Extract `copier.yml` and `template/` of one commit into destination."""
    done = subprocess.run(  # noqa: S603
        ["git", "archive", "--format=tar", ref, "copier.yml", "template"],  # noqa: S607
        cwd=root,
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        detail = done.stderr.decode(errors="replace").strip()
        raise ValueError(
            f"Template ref {ref}: git archive failed ({detail}). "
            "Pass a commit or tag that exists in this clone."
        )
    with tarfile.open(fileobj=io.BytesIO(done.stdout)) as archive:
        archive.extractall(destination, filter="data")
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


def measure_fixtures(
    names: list[str], ref: str | None = None
) -> dict[str, dict[str, int]]:
    """Render and measure each named fixture in a temporary directory."""
    with tempfile.TemporaryDirectory(prefix="csarc-payload-") as temporary:
        workdir = Path(temporary)
        source = workdir / "source"
        source.mkdir()
        if ref is None:
            template_copy(source)
        else:
            template_at_ref(ref, source)
        return {
            name: measure(render(source, workdir / name, FIXTURES[name]))
            for name in names
        }


def _tree(project: Path) -> dict[str, bytes]:
    """Return every rendered file keyed by its relative path."""
    return {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
        and path.relative_to(project).as_posix() not in CHURN_IGNORED
    }


def tree_churn(old: dict[str, bytes], new: dict[str, bytes]) -> dict[str, int]:
    """Return changed file counts and changed line counts between two trees."""
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    modified = sorted(
        path for path in set(old) & set(new) if old[path] != new[path]
    )
    lines_added = sum(len(new[path].splitlines()) for path in added)
    lines_removed = sum(len(old[path].splitlines()) for path in removed)
    for path in modified:
        before = old[path].decode(errors="replace").splitlines()
        after = new[path].decode(errors="replace").splitlines()
        matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "equal":
                lines_removed += i2 - i1
                lines_added += j2 - j1
    return {
        "files_added": len(added),
        "files_removed": len(removed),
        "files_modified": len(modified),
        "lines_added": lines_added,
        "lines_removed": lines_removed,
    }


def churn(
    since: str, names: list[str] | None = None, root: Path = ROOT
) -> dict[str, object]:
    """Return the advisory generated-project churn since one ref (#1231)."""
    names = names or list(FIXTURES)
    with tempfile.TemporaryDirectory(prefix="csarc-churn-") as temporary:
        workdir = Path(temporary)
        old_source, new_source = workdir / "old", workdir / "new"
        old_source.mkdir()
        new_source.mkdir()
        template_at_ref(since, old_source, root)
        template_copy(new_source)
        fixtures = {
            name: tree_churn(
                _tree(render(old_source, workdir / f"old-{name}", data)),
                _tree(render(new_source, workdir / f"new-{name}", data)),
            )
            for name, data in FIXTURES.items()
            if name in names
        }
    return {"available": True, "since": since, "fixtures": fixtures}


def _write_table(results: dict[str, dict[str, int]]) -> None:
    """Print the budget table and the reference measures."""
    write = sys.stdout.write
    columns = (
        "files",
        "canonical_bytes",
        "write_workflows",
        "pull_request_target_workflows",
        "agent_doc_tokens",
    )
    write("| Fixture | " + " | ".join(columns) + " | bytes (reference) |\n")
    write("| --- |" + " ---: |" * (len(columns) + 1) + "\n")
    for name, values in results.items():
        cells = [
            f"{values[column]:,} (≤ {TARGETS[name][column]:,})"
            for column in columns
        ]
        write(
            f"| {name} | " + " | ".join(cells) + f" | {values['bytes']:,} |\n"
        )
    write("\n| Runtime group | " + " | ".join(results) + " |\n")
    write("| --- |" + " ---: |" * len(results) + "\n")
    for group, budget in RUNTIME_GROUP_BUDGETS.items():
        cells = [
            f"{values[f'runtime:{group}']:,}" for values in results.values()
        ]
        write(f"| {group} (≤ {budget:,}) | " + " | ".join(cells) + " |\n")


def main(argv: list[str] | None = None) -> int:
    """Print the payload table, or the churn report, for the fixtures."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["churn"]:
        parser = argparse.ArgumentParser(prog="generated_payload.py churn")
        parser.add_argument("--since", required=True, metavar="TAG")
        parser.add_argument("fixtures", nargs="*", metavar="FIXTURE")
        args = parser.parse_args(arguments[1:])
    else:
        parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
        parser.add_argument("fixtures", nargs="*", metavar="FIXTURE")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--ref", default=None)
        args = parser.parse_args(arguments)
    unknown = sorted(set(args.fixtures) - set(FIXTURES))
    if unknown:
        parser.error(f"unknown fixtures: {', '.join(unknown)}")
    names = args.fixtures or list(FIXTURES)
    try:
        if arguments[:1] == ["churn"]:
            report = churn(args.since, names)
            # message-pattern: allow X1 JSON output
            sys.stdout.write(
                json.dumps(report, indent=2, sort_keys=True) + "\n"
            )
            return 0
        results = measure_fixtures(names, args.ref)
    except ValueError as error:
        sys.stderr.write(f"ERROR: {error}\n")
        return 2
    if args.json:
        # message-pattern: allow X1 JSON output
        sys.stdout.write(json.dumps(results, indent=2, sort_keys=True) + "\n")
        return 0
    _write_table(results)
    for name, low in low_headroom(results).items():
        sys.stderr.write(
            f"WARNING: {name} payload headroom is low: {low}. "
            "Free room before adding generated payload.\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
