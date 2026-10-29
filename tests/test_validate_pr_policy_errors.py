"""Every `validate-pr-policy` error branch fails with its own message (#1257).

`scripts/test-pr-policy` runs only in the full tier and mostly checks the
exit status. This module runs both the root and the template copy of the
validator in the not-large tier against a stub `gh`, so every `fail()` call
and every delegated helper error is reached directly and asserts the exit
code and the exact message. It also catches a `fail()` that calls itself,
the #1253 regression the not-large suite once missed.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COPIES = {
    "root": ("scripts", ROOT / "scripts"),
    "template": (".csarc/scripts", ROOT / "template/.csarc/scripts"),
}
HEAD_SHA = "a" * 40
# A subprocess that has not finished by now is treated as a hang, such as a
# `fail()` that recurses instead of exiting.
TIMEOUT_SECONDS = 30
BASE_ENV = {
    "PR_POLICY_FIXTURE": "true",
    "GITHUB_REPOSITORY": "acme/project",
    "PR_NUMBER": "42",
    "PR_TITLE": "feat(api): add report export",
    "PR_LABELS": "enhancement",
    "PR_BASE": "main",
    "PR_HEAD": "feat/42-report-export",
    "PR_BODY": "Closes #42",
    "PR_AUTHOR": "contributor",
    "PR_ASSIGNEES": "contributor",
    "PR_HEAD_SHA": HEAD_SHA,
    "PR_DRAFT": "false",
    "PR_RELEASE_OWNERSHIP": "product-owned",
    "PR_ISSUE_STATE": "open",
    "PR_ISSUE_TITLE": "Add verified report workflow",
    "PR_ISSUE_BODY": "All acceptance tasks are complete.",
    "PR_ISSUE_MILESTONE_NUMBER": "0",
    "PR_ISSUE_LABELS": "enhancement",
    "PR_ISSUE_TYPE": "",
    "PR_DOCUMENTATION_REVIEW_CUTOVER_PR": "999999",
    "PR_REQUIREMENT_TRACE_REQUIRED": "false",
    # Skip the non-blocking Milestone reminder, which would post a comment.
    "PR_POLICY_READ_ONLY": "true",
}
GH_STUB = """#!/usr/bin/env python3
import json, os, sys
call = " ".join(sys.argv[1:])
for rule in json.loads(os.environ.get("GH_STUB_RULES", "[]")):
    if all(part in call for part in rule["match"]):
        sys.stdout.write(rule.get("stdout", ""))
        sys.exit(rule.get("exit", 0))
sys.stderr.write("gh stub: unexpected call: " + call + "\\n")
sys.exit(97)
"""


def metadata(labels: str = "enhancement", milestone: int | None = None) -> dict:
    """Return a stub rule for the live pull-request metadata read."""
    payload = {
        "labels": [{"name": name} for name in labels.split(",")],
        "assignees": [{"login": "contributor"}],
        "milestone": None if milestone is None else {"number": milestone},
        "body": "Closes #42",
    }
    return {
        "match": ["api --method GET repos/acme/project/issues/42"],
        "stdout": json.dumps(payload),
    }


FILES_OK = {"match": ["pulls/42/files"], "stdout": "[[]]"}


@dataclass(frozen=True)
class Case:
    """One failing input and the exact `fail()` message it must print."""

    name: str
    message: str
    env: dict[str, str | None] = field(default_factory=dict)
    gh: tuple[dict, ...] = ()
    minimal: bool = False


FAIL_CASES = (
    Case(
        "title-format",
        "PR title: not 'type(scope): summary'. Use type feat, fix, docs, "
        "refactor, test, build, ci, chore, or revert, and an optional scope "
        "of lowercase letters, numbers, '.', '_', '/', or '-'.",
        {"PR_TITLE": "add report export"},
    ),
    Case(
        "title-ascii",
        "PR title: non-ASCII characters. Use ASCII only; the PR body can use "
        "Chinese.",
        {"PR_TITLE": "feat(api): add réport export"},
    ),
    Case(
        "metadata-unreadable",
        "Pull request metadata: cannot read it. Retry the check.",
        {"PR_POLICY_FIXTURE": "false"},
        ({"match": ["issues/42"], "exit": 1},),
    ),
    Case(
        "metadata-malformed",
        "Pull request metadata: incomplete or malformed. Retry the check.",
        {"PR_POLICY_FIXTURE": "false"},
        ({"match": ["issues/42"], "stdout": "{}"},),
    ),
    Case(
        "label-count",
        "PR label: not exactly one classification label. Select bug, "
        "enhancement, or documentation.",
        {"PR_LABELS": "bug,enhancement"},
    ),
    Case(
        "label-duplicate",
        "PR label: 'duplicate' is an Issue disposition. Remove it.",
        {"PR_LABELS": "enhancement,duplicate"},
    ),
    Case(
        "documentation-cutover-env",
        "PR_DOCUMENTATION_REVIEW_CUTOVER_PR: not a non-negative integer. Fix "
        "the workflow env.",
        {"PR_DOCUMENTATION_REVIEW_CUTOVER_PR": "next"},
    ),
    Case(
        "large-test-files-unreadable",
        "Large-test check: cannot read the file list. Retry the check.",
        {"PR_POLICY_FIXTURE": "false"},
        (metadata(), {"match": ["pulls/42/files"], "exit": 1}),
    ),
    Case(
        "governance-files-unreadable",
        "Governance route: cannot read the file list. Retry the check.",
        {"PR_POLICY_FIXTURE": "false", "PR_DRAFT": "true"},
        (metadata(), {"match": ["pulls/42/files"], "exit": 1}),
    ),
    Case(
        "governance-config-unreadable",
        "Governance route: cannot read the candidate configuration. Retry "
        "the check.",
        {"PR_POLICY_FIXTURE": "false", "PR_DRAFT": "true"},
        (
            metadata(),
            FILES_OK,
            {"match": ["contents/.csarc/config.yml"], "exit": 1},
        ),
    ),
    Case(
        "release-ownership",
        "release_ownership: invalid value. Use csarc-owned, product-owned, or "
        "verification-only.",
        {"PR_RELEASE_OWNERSHIP": "vendor-owned"},
    ),
    Case(
        "delivery-cutover-env",
        "PR_DELIVERY_CUTOVER_ISSUE: not a non-negative integer. Fix the "
        "workflow env.",
        {"PR_DELIVERY_CUTOVER_ISSUE": "-1"},
    ),
    Case(
        "release-recovery-route",
        "Release recovery: invalid route. Use a fix/* branch to main with a "
        "fix title and no hotfix label.",
        {"PR_LABELS": "enhancement,release-recovery"},
    ),
    Case(
        "hotfix-route",
        "Hotfix: invalid route. Use a fix/* branch to main with a fix title.",
        {"PR_LABELS": "enhancement,hotfix"},
    ),
    Case(
        "guided-release-route",
        "Guided release: invalid route. Use release/v<version> and the "
        "matching chore(main) title.",
        {"PR_RELEASE_OWNERSHIP": "csarc-owned", "PR_HEAD": "release/v1.2"},
    ),
    Case(
        "sync-base",
        "Main sync branch: wrong base. Target its matching delivery branch.",
        {"PR_HEAD": "sync/main-to-m7-report-abcdef1"},
    ),
    Case(
        "automation-base",
        "Automated maintenance: wrong base. Target main.",
        {"PR_HEAD": "dependabot/uv/pytest", "PR_BASE": "dev/m7-report"},
    ),
    Case(
        "bridge-label",
        "Promotion bridge: no promotion label. Add it.",
        {"PR_HEAD": "promote/m7-report"},
    ),
    Case(
        "promotion-needs-milestones",
        "Milestone promotion: needs lifecycle: milestones. Set it.",
        {"PR_HEAD": "dev/m7-report"},
        minimal=True,
    ),
    Case(
        "promotion-label",
        "Delivery promotion: no promotion label. Add it.",
        {"PR_HEAD": "dev/i42-report"},
    ),
    Case(
        "csarc-owned-bridge",
        "CSARC-owned Milestone: no promote/m* bridge. Use one so the delivery "
        "PR reviews the version.",
        {
            "PR_HEAD": "dev/m7-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_RELEASE_OWNERSHIP": "csarc-owned",
        },
    ),
    Case(
        "tracker-reference",
        "Milestone promotion: no tracker reference. Add 'Refs #N'.",
        {
            "PR_HEAD": "promote/m7-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_RELEASE_OWNERSHIP": "csarc-owned",
        },
    ),
    Case(
        "tracker-closed-early",
        "Milestone promotion: closes its tracker before release. Use "
        "'Refs #N'.",
        {
            "PR_HEAD": "promote/m7-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_RELEASE_OWNERSHIP": "csarc-owned",
            "PR_BODY": "Refs #42\nCloses #42",
        },
    ),
    Case(
        "promotion-closing-keyword",
        "Delivery promotion: does not close its promotion Issue. Add "
        "'Closes #N'.",
        {
            "PR_HEAD": "dev/i42-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_BODY": "Refs #42",
        },
    ),
    Case(
        "branch-name",
        "Branch: invalid name. Use 'type/<issue-number>-short-slug'.",
        {"PR_HEAD": "report-export"},
    ),
    Case(
        "closing-keyword",
        "PR body: no closing keyword. Add 'Closes #42'.",
        {"PR_BODY": "Refs #42"},
    ),
    Case(
        "pr-checklist",
        "PR checklist: unchecked items. Complete every item.",
        {"PR_BODY": "Closes #42\n\n- [ ] Evidence recorded"},
    ),
    Case(
        "issue-state",
        "Issue #42: missing or closed. Reopen it until merge.",
        {"PR_ISSUE_STATE": "closed"},
    ),
    Case(
        "no-assignee",
        "Pull request: no assignee. Assign its human author.",
        {"PR_ASSIGNEES": "", "PR_AUTHOR": ""},
    ),
    Case(
        "author-not-assignee",
        "Pull request: author is not an assignee. Assign the author.",
        {"PR_ASSIGNEES": "reviewer"},
    ),
    Case(
        "milestone-mismatch",
        "Pull request Milestone: differs from Issue #42. Run 'gh api "
        "repos/acme/project/issues/42 --method PATCH -F milestone=null'.",
        {"PR_MILESTONE_NUMBER": "7"},
    ),
    Case(
        "issue-label-conflict",
        "Issue #42: conflicting classification labels. Keep one.",
        {"PR_ISSUE_LABELS": "bug,enhancement"},
    ),
    Case(
        "issue-type-unsupported",
        "Issue #42: unsupported native Type. Use Bug, Feature, or Task.",
        {"PR_ISSUE_TYPE": "Epic", "PR_ISSUE_LABELS": ""},
    ),
    Case(
        "issue-label-repeats-type",
        "Issue #42: work-kind label repeats its Type. Run 'gh issue edit 42 "
        "--remove-label enhancement'.",
        {"PR_ISSUE_TYPE": "Feature"},
    ),
    # Issue #1344: the local and self-hosted lifecycle (PR_POLICY_LOCAL) asks
    # for a native Type where the repository offers Issue Types.
    Case(
        "local-issue-without-type",
        "Issue #42: no native Type. Run 'gh issue edit 42 --type Feature "
        "--remove-label enhancement'.",
        {"PR_POLICY_LOCAL": "true", "PR_REPO_ISSUE_TYPES": "3"},
    ),
    Case(
        "local-issue-without-assignee",
        "Issue #42: no assignee. Run 'gh issue edit 42 --add-assignee @me'.",
        {
            "PR_POLICY_LOCAL": "true",
            "PR_ISSUE_TYPE": "Feature",
            "PR_ISSUE_LABELS": "",
        },
    ),
    Case(
        "label-differs-from-issue",
        "PR label: differs from Issue #42's Type or label. Match it.",
        {"PR_LABELS": "bug"},
    ),
    Case(
        "development-cutover-env",
        "PR_DEVELOPMENT_CUTOVER_PR or PR_NUMBER: not a non-negative integer. "
        "Fix the workflow env.",
        {"PR_DEVELOPMENT_CUTOVER_PR": "soon"},
    ),
    Case(
        "closing-relationship-unreadable",
        "Closing Issue relationship: cannot read it. Retry the check.",
        {"PR_POLICY_FIXTURE": "false"},
        (
            metadata(),
            FILES_OK,
            {"match": ["contents/.csarc/config.yml"], "stdout": "CONFIG"},
            {"match": ["provenance.json"], "exit": 1},
            {"match": ["api graphql"], "exit": 1},
        ),
    ),
    Case(
        "closing-relationship-mismatch",
        "PR #42: not exactly one closing Issue link to acme/project#42. Fix "
        "the PR body.",
        {"PR_CLOSING_ISSUES_JSON": "{}"},
    ),
    Case(
        "stacked-closing-keywords",
        "PR body: not exactly one closing keyword for Issue #42. Keep one "
        "'Closes #42'.",
        {
            "PR_BASE": "dev/m7-report",
            "PR_MILESTONE_NUMBER": "7",
            "PR_ISSUE_MILESTONE_NUMBER": "7",
            "PR_BODY": "Closes #42\nFixes #42",
        },
    ),
    Case(
        "issue-checklist",
        "Issue #42: unchecked acceptance tasks. Complete them.",
        {"PR_ISSUE_BODY": "- [ ] AC1: report exported"},
    ),
    Case(
        "tracker-title",
        "Milestone 7 promotion: wrong tracker Issue. Reference its own "
        "tracker.",
        {
            "PR_HEAD": "promote/m7-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_RELEASE_OWNERSHIP": "csarc-owned",
            "PR_BODY": "Refs #42",
            "PR_MILESTONE_NUMBER": "7",
            "PR_ISSUE_MILESTONE_NUMBER": "7",
        },
    ),
    Case(
        "tracker-milestone",
        "Tracker Issue Milestone: differs from the delivery branch. Set the "
        "tracker Milestone.",
        {
            "PR_HEAD": "promote/m7-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_RELEASE_OWNERSHIP": "csarc-owned",
            "PR_BODY": "Refs #42",
            "PR_MILESTONE_NUMBER": "8",
            "PR_ISSUE_MILESTONE_NUMBER": "8",
            "PR_ISSUE_TITLE": "Milestone 7: Report export",
        },
    ),
    Case(
        "promotion-issue-label",
        "Delivery promotion: closed Issue has no promotion label. Add it.",
        {"PR_HEAD": "dev/i42-report", "PR_LABELS": "enhancement,promotion"},
    ),
    Case(
        "promotion-issue-milestone",
        "Promotion Issue Milestone: differs from the delivery branch. Set the "
        "Issue Milestone.",
        {
            "PR_HEAD": "dev/m7-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_ISSUE_LABELS": "enhancement,promotion",
            "PR_MILESTONE_NUMBER": "8",
            "PR_ISSUE_MILESTONE_NUMBER": "8",
        },
    ),
    Case(
        "isolated-branch-number",
        "Isolated delivery branch: number differs from its Issue. Use "
        "dev/i<Issue>-<slug>.",
        {
            "PR_HEAD": "dev/i43-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_ISSUE_LABELS": "enhancement,promotion",
        },
    ),
    Case(
        "standalone-promotion-milestone",
        "Standalone promotion Issue: has a Milestone. Remove it.",
        {
            "PR_HEAD": "dev/i42-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_ISSUE_LABELS": "enhancement,promotion",
            "PR_MILESTONE_NUMBER": "7",
            "PR_ISSUE_MILESTONE_NUMBER": "7",
        },
    ),
    Case(
        "promotion-intent-shas",
        "Promotion intent: no exact base and head SHAs. Set PR_BASE_SHA and "
        "PR_HEAD_SHA.",
        {
            "PR_POLICY_FIXTURE": "false",
            "PR_HEAD": "dev/m7-report",
            "PR_HEAD_SHA": None,
            "PR_ISSUE_LABELS": "enhancement,promotion",
            "PR_ISSUE_MILESTONE_NUMBER": "7",
        },
        (metadata("enhancement,promotion", 7),),
    ),
    Case(
        "hotfix-milestone",
        "Direct hotfix: has a Milestone. Remove it.",
        {
            "PR_TITLE": "fix(api): restore report export",
            "PR_HEAD": "fix/42-report-export",
            "PR_LABELS": "enhancement,hotfix",
            "PR_MILESTONE_NUMBER": "7",
            "PR_ISSUE_MILESTONE_NUMBER": "7",
        },
    ),
    Case(
        "milestone-work-base",
        "Milestone work: wrong base. Target its dev/m<Milestone>-* branch.",
        {"PR_MILESTONE_NUMBER": "7", "PR_ISSUE_MILESTONE_NUMBER": "7"},
    ),
    Case(
        "milestone-base-mismatch",
        "Issue #42 Milestone 7: base 'dev/m8-report' is wrong. Use 'dev/m7-'.",
        {
            "PR_BASE": "dev/m8-report",
            "PR_MILESTONE_NUMBER": "7",
            "PR_ISSUE_MILESTONE_NUMBER": "7",
        },
    ),
    Case(
        "legacy-base",
        "PR base: legacy standalone delivery branch. Use a current base.",
        {"PR_BASE": "dev/next"},
    ),
    Case(
        "base-cycle",
        "PR base chain: cycle at feat/41-parent. Fix the bases.",
        {"PR_BASE": "feat/41-parent"},
        (
            {"match": ["head=acme:feat/41-parent"], "stdout": "feat/40-root\n"},
            {"match": ["head=acme:feat/40-root"], "stdout": "feat/41-parent\n"},
        ),
    ),
    Case(
        "base-unreadable",
        "Base branch feat/41-parent: cannot read its open PR. Retry the check.",
        {"PR_BASE": "feat/41-parent"},
        ({"match": ["head=acme:feat/41-parent"], "exit": 1},),
    ),
    Case(
        "base-no-open-pr",
        "Base branch feat/41-parent: not exactly one open PR. Chain it to "
        "'main'.",
        {"PR_BASE": "feat/41-parent"},
        ({"match": ["head=acme:feat/41-parent"], "stdout": ""},),
    ),
)

# Branches that end in `exit 1` after a helper reports its own error.
DELEGATED_CASES = (
    Case(
        "documentation-record",
        "ERROR: Documentation review status is invalid",
        {
            "PR_DOCUMENTATION_REVIEW_REQUIRED": "true",
            "PR_DOCUMENTATION_REVIEW_CUTOVER_PR": "1",
        },
    ),
    Case(
        "large-test-justification",
        "Add a 'Large test justification:' line to the PR body",
        {
            "PR_CHANGED_FILES_JSON": json.dumps(
                [
                    [
                        {
                            "filename": "tests/test_report.py",
                            "status": "added",
                            "patch": "+@pytest.mark.large\n+def test_report():",
                        }
                    ]
                ]
            ),
        },
    ),
    Case(
        "governance-route",
        "Pull request needs the governance-switch route",
        {
            "PR_CANDIDATE_CONFIG": "CONFIG",
            "PR_CHANGED_FILES_JSON": json.dumps(
                [[{"filename": ".csarc/scripts/verify", "status": "modified"}]]
            ),
        },
    ),
    Case(
        "issue-title",
        "ERROR: Issue title is invalid: length must be 12-80 characters.",
        {"PR_ISSUE_TITLE": "fix"},
    ),
    Case(
        "requirement-evidence",
        'requirement-trace: RK20 add exactly one "## Requirement evidence" '
        "section",
        {"PR_REQUIREMENT_TRACE_REQUIRED": "true"},
        (
            {
                "match": ["api repos/acme/project/pulls/42"],
                "stdout": json.dumps(
                    {
                        "number": 42,
                        "state": "open",
                        "merged": False,
                        "head": {
                            "sha": HEAD_SHA,
                            "ref": "feat/42-report-export",
                        },
                        "base": {"ref": "main"},
                        "body": "Closes #42",
                    }
                ),
            },
            {
                "match": ["api repos/acme/project/issues/42"],
                "stdout": json.dumps(
                    {
                        "number": 42,
                        "body": "",
                        "assignees": [{"login": "contributor"}],
                    }
                ),
            },
            FILES_OK,
        ),
    ),
    Case(
        "promotion-intent",
        "Promotion title: wrong SemVer intent.",
        {
            "PR_TITLE": "fix(api): restore report export",
            "PR_HEAD": "dev/m7-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_ISSUE_LABELS": "enhancement,promotion",
            "PR_MILESTONE_NUMBER": "7",
            "PR_ISSUE_MILESTONE_NUMBER": "7",
            "PR_INCLUDED_TITLES_JSON": '["feat(api): add report export"]',
        },
    ),
    Case(
        "tracker-promotion-section",
        "The lifecycle Issue needs a Promotion section",
        {
            "PR_HEAD": "promote/m7-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_RELEASE_OWNERSHIP": "csarc-owned",
            "PR_BODY": "Refs #42\n\n## ADR 與文件對齊\n\n"
            "- Status: aligned\n"
            f"- Reviewed head: `{HEAD_SHA}`\n"
            "- Reason: Tracker decisions match the docs.",
            "PR_MILESTONE_NUMBER": "7",
            "PR_ISSUE_MILESTONE_NUMBER": "7",
            "PR_ISSUE_TITLE": "Milestone 7: Report export",
        },
    ),
    Case(
        "adr-alignment",
        "no '## ADR 與文件對齊' section",
        {
            "PR_HEAD": "promote/m7-report",
            "PR_LABELS": "enhancement,promotion",
            "PR_RELEASE_OWNERSHIP": "csarc-owned",
            "PR_BODY": "Refs #42",
            "PR_MILESTONE_NUMBER": "7",
            "PR_ISSUE_MILESTONE_NUMBER": "7",
            "PR_ISSUE_TITLE": "Milestone 7: Report export",
        },
    ),
)


def fail_messages(source: str) -> list[str]:
    """Return every literal `fail "..."` argument in one validator copy."""
    return re.findall(r'\bfail "((?:[^"\\]|\\.)*)"', source)


def message_pattern(raw: str) -> re.Pattern[str]:
    """Match a raw `fail` argument with each `${...}` as a wildcard."""
    parts = re.split(r"\$\{[^}]*\}", raw)
    return re.compile(".+?".join(re.escape(part) for part in parts))


@pytest.fixture(scope="module")
def layouts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Copy each validator with its helpers into an isolated project."""
    base = tmp_path_factory.mktemp("pr-policy")
    config = (ROOT / ".csarc/config.yml").read_text(encoding="utf-8")
    projects: dict[str, Path] = {}
    for copy, (relative, source) in COPIES.items():
        for minimal in (False, True):
            project = base / f"{copy}-{'minimal' if minimal else 'full'}"
            if minimal:
                (project / relative).mkdir(parents=True)
                shutil.copy2(
                    source / "validate-pr-policy",
                    project / relative / "validate-pr-policy",
                )
            else:
                shutil.copytree(
                    source,
                    project / relative,
                    ignore=shutil.ignore_patterns("__pycache__", "*.jinja"),
                )
            (project / ".csarc").mkdir(exist_ok=True)
            (project / ".csarc/config.yml").write_text(config, encoding="utf-8")
            projects[f"{copy}-{minimal}"] = project
    stub = base / "bin/gh"
    stub.parent.mkdir()
    stub.write_text(GH_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    projects["bin"] = stub.parent
    return projects


def run_validator(
    layouts: dict[str, Path],
    copy: str,
    case: Case,
    *,
    validator: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one validator copy with the base inputs plus the case overrides."""
    project = layouts[f"{copy}-{case.minimal}"]
    config = (project / ".csarc/config.yml").read_text(encoding="utf-8")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PR_", "GITHUB_", "GH_", "RUNNER_"))
    }
    env["PATH"] = f"{layouts['bin']}{os.pathsep}{env.get('PATH', '')}"
    env.update(BASE_ENV)
    for key, value in case.env.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = (
                value.replace("CONFIG", config)
                if key == "PR_CANDIDATE_CONFIG"
                else value
            )
    rules = [dict(rule) for rule in case.gh]
    for rule in rules:
        if rule.get("stdout") == "CONFIG":
            rule["stdout"] = base64.b64encode(config.encode()).decode()
    env["GH_STUB_RULES"] = json.dumps(rules)
    env.update(extra_env or {})
    script = validator or project / COPIES[copy][0] / "validate-pr-policy"
    return subprocess.run(  # noqa: S603
        [str(script)],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )


@pytest.mark.parametrize("copy", COPIES)
def test_baseline_inputs_pass(layouts: dict[str, Path], copy: str) -> None:
    """Prove every failing case differs from a passing input in one way."""
    result = run_validator(layouts, copy, Case("baseline", ""))
    assert result.returncode == 0, result.stderr


LOCAL_TYPE_FIXES = {
    "bug": "--type Bug --remove-label bug",
    "documentation": "--type Task",
    "": "--type <Bug|Feature|Task>",
}
TYPES_ENABLED = {"match": ["api graphql", "issueTypes"], "stdout": "3\n"}


@pytest.mark.parametrize("copy", COPIES)
@pytest.mark.parametrize("label", LOCAL_TYPE_FIXES)
def test_local_missing_type_names_one_fix_command(
    layouts: dict[str, Path], copy: str, label: str
) -> None:
    """#1344 AC1/AC2: the fix turns the fallback label into the Type."""
    env: dict[str, str | None] = {
        "PR_POLICY_LOCAL": "true",
        "PR_ISSUE_LABELS": label,
        "PR_LABELS": label or "enhancement",
    }
    result = run_validator(
        layouts, copy, Case("type", "", env, (TYPES_ENABLED,))
    )
    assert result.returncode == 1, result.stderr
    assert result.stderr.strip() == (
        "ERROR: Issue #42: no native Type. Run 'gh issue edit 42 "
        f"{LOCAL_TYPE_FIXES[label]}'."
    )


@pytest.mark.parametrize("copy", COPIES)
@pytest.mark.parametrize("count", ["0", "", "null", "error"])
def test_local_mode_keeps_fallback_label_without_issue_types(
    layouts: dict[str, Path], copy: str, count: str
) -> None:
    """#1344 AC3: no Issue Types, or an unreadable count, keeps the label."""
    env: dict[str, str | None] = {
        "PR_POLICY_LOCAL": "true",
        "PR_ISSUE_ASSIGNEES": "contributor",
    }
    rule = {"match": ["api graphql", "issueTypes"], "stdout": count}
    if count == "error":
        rule = {"match": ["api graphql"], "exit": 1}
    result = run_validator(layouts, copy, Case("labels", "", env, (rule,)))
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("copy", COPIES)
def test_local_mode_passes_with_type_and_assignee(
    layouts: dict[str, Path], copy: str
) -> None:
    """#1344 AC1: a typed, assigned Issue passes with no Types lookup."""
    env: dict[str, str | None] = {
        "PR_POLICY_LOCAL": "true",
        "PR_ISSUE_TYPE": "Task",
        "PR_ISSUE_LABELS": "",
        "PR_ISSUE_ASSIGNEES": "contributor",
    }
    result = run_validator(layouts, copy, Case("typed", "", env))
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("copy", COPIES)
@pytest.mark.parametrize("case", FAIL_CASES, ids=lambda case: case.name)
def test_fail_branch_reports_its_message(
    layouts: dict[str, Path], copy: str, case: Case
) -> None:
    """Each `fail()` branch exits 1 with exactly its own ERROR line."""
    result = run_validator(layouts, copy, case)
    errors = [
        line for line in result.stderr.splitlines() if line.startswith("ERROR:")
    ]
    assert result.returncode == 1, result.stderr
    assert errors == [f"ERROR: {case.message}"], result.stderr
    assert "gh stub: unexpected call" not in result.stderr


@pytest.mark.parametrize("copy", COPIES)
@pytest.mark.parametrize("case", DELEGATED_CASES, ids=lambda case: case.name)
def test_delegated_error_stops_the_policy(
    layouts: dict[str, Path], copy: str, case: Case
) -> None:
    """A helper's own error stops the policy with exit 1 and its message."""
    result = run_validator(layouts, copy, case)
    assert result.returncode == 1, result.stdout + result.stderr
    assert case.message in result.stdout + result.stderr
    assert "gh stub: unexpected call" not in result.stderr


@pytest.mark.parametrize("copy", COPIES)
def test_every_fail_call_has_a_direct_case(copy: str) -> None:
    """A new `fail()` branch needs a case here before it can land."""
    relative, source = COPIES[copy]
    raw_messages = fail_messages(
        (source / "validate-pr-policy").read_text(encoding="utf-8")
    )
    assert raw_messages
    expected = [case.message for case in FAIL_CASES]
    uncovered = [
        raw
        for raw in raw_messages
        if not any(message_pattern(raw).fullmatch(text) for text in expected)
    ]
    assert not uncovered, f"{relative}/validate-pr-policy: {uncovered}"
    assert len(raw_messages) == len(FAIL_CASES)


def fail_body(source: str) -> str:
    """Return the body of the `fail()` function in one validator copy."""
    match = re.search(r"(?ms)^fail\(\) \{\n(.*?)^\}", source)
    assert match, "validate-pr-policy: no fail() function"
    return match.group(1)


@pytest.mark.parametrize("copy", COPIES)
def test_fail_helper_does_not_call_itself(copy: str) -> None:
    """The #1253 regression: `fail()` must print and exit, never recurse."""
    body = fail_body(
        (COPIES[copy][1] / "validate-pr-policy").read_text(encoding="utf-8")
    )
    assert not re.search(r"(?<![\w-])fail(?![\w-])", body), body
    assert body.rstrip().endswith("exit 1"), body


def fails_cleanly(
    layouts: dict[str, Path], copy: str, validator: Path | None = None
) -> bool:
    """Return whether one failing branch stops once with exit 1."""
    case = FAIL_CASES[0]
    try:
        result = run_validator(
            layouts,
            copy,
            case,
            validator=validator,
            # Bash 4.2+ stops runaway recursion at this depth; older Bash
            # relies on the subprocess timeout instead.
            extra_env={"FUNCNEST": "16"},
        )
    except subprocess.TimeoutExpired:
        return False
    return (
        result.returncode == 1
        and result.stderr.count("ERROR:") == 1
        and "nesting level" not in result.stderr
    )


@pytest.mark.parametrize("copy", COPIES)
def test_failing_branch_is_not_recursive(
    layouts: dict[str, Path], copy: str, tmp_path: Path
) -> None:
    """Run a failing branch bounded, and prove the check sees recursion."""
    assert fails_cleanly(layouts, copy)
    source = layouts[f"{copy}-False"] / COPIES[copy][0] / "validate-pr-policy"
    text = source.read_text(encoding="utf-8")
    mutated = text.replace(
        'fail() {\n  echo "ERROR: $1" >&2', 'fail() {\n  fail "$1"', 1
    )
    assert mutated != text
    recursive = source.with_name("validate-pr-policy-recursive")
    recursive.write_text(mutated, encoding="utf-8")
    recursive.chmod(source.stat().st_mode)
    try:
        assert not fails_cleanly(layouts, copy, recursive)
    finally:
        recursive.unlink()
