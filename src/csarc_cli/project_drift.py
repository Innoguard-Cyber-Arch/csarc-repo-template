"""Report ProjectV2 drift for work items without writing anything (#1346).

`csarc issue sync-project --report` reads the configured
``github_project_url`` and the repository's Issues and lists three kinds of
drift (SPEC-009 §10):

* a board item whose Issue is closed while its Project ``Status`` is not
  ``Done``;
* an Issue the board rules (#1186) put on the board, a Milestone tracker or
  a standalone Issue, that has no item on the Project;
* an item of such an Issue whose ``Project start`` or ``Project target`` is
  empty.

GitHub Project workflows own ``Status``; the template never writes it. This
report sends only GraphQL queries and REST reads, never a mutation. When a
field it needs is missing or has another type, it says so and skips that
check instead of guessing.

This module is CLI-only and never ships to a generated project.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from csarc_cli.project_roadmap import (
    CONFIG_FILE,
    DONE,
    PROJECT_QUERY,
    SETTING,
    START_FIELD,
    STATUS_FIELD,
    TARGET_FIELD,
    IssueFacts,
    ProjectSyncError,
    Runner,
    configured_project_url,
    current_repo,
    gh_runner,
    graphql,
    issue_facts,
    milestone_issues,
    parse_project_url,
    read_issue,
    token_scopes,
)

READ_SCOPES = {"project", "read:project"}
ITEMS_QUERY = """
query($login: String!, $number: Int!, $cursor: String) {
  owner: %s(login: $login) {
    projectV2(number: $number) {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          content {
            ... on Issue { number state repository { nameWithOwner } }
          }
          start: fieldValueByName(name: "Project start") {
            ... on ProjectV2ItemFieldDateValue { date }
          }
          target: fieldValueByName(name: "Project target") {
            ... on ProjectV2ItemFieldDateValue { date }
          }
          status: fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
        }
      }
    }
  }
}
"""
FIELD_TYPES = {
    START_FIELD: "DATE",
    TARGET_FIELD: "DATE",
    STATUS_FIELD: "SINGLE_SELECT",
}


@dataclass(frozen=True)
class BoardItem:
    """One Project item that holds an Issue of the reported repository."""

    number: int
    closed: bool
    start: str | None
    target: str | None
    status: str | None


@dataclass(frozen=True)
class ReadOnlyProject:
    """A live-resolved ProjectV2, checked only for reading."""

    url: str
    title: str
    scope: str
    missing_fields: dict[str, str]


def field_problem(nodes: list[Any], name: str) -> str:
    """Return why field ``name`` cannot be read, or '' when it can."""
    found = [
        node
        for node in nodes
        if isinstance(node, dict)
        and str(node.get("name", "")).casefold() == name.casefold()
    ]
    if not found:
        return "the Project has no such field"
    if len(found) > 1:
        return f"the Project has {len(found)} fields with that name"
    wanted = FIELD_TYPES[name]
    if found[0].get("dataType") != wanted:
        return f"it is {found[0].get('dataType')}, not {wanted}"
    return ""


def resolve_for_report(run: Runner, url: str) -> ReadOnlyProject:
    """Read back owner, Project, and fields; require no write access."""
    ref = parse_project_url(url)
    scopes = token_scopes(run)
    if scopes is not None and not scopes & READ_SCOPES:
        listed = ", ".join(sorted(scopes)) or "none"
        raise ProjectSyncError(
            f"GitHub token lacks the 'read:project' scope: it has {listed}. "
            "Run 'gh auth refresh -s read:project'."
        )
    data = graphql(
        run, PROJECT_QUERY % ref.owner_kind, login=ref.login, number=ref.number
    )
    owner = data.get("owner")
    if not isinstance(owner, dict) or (
        str(owner.get("login", "")).casefold() != ref.login.casefold()
    ):
        raise ProjectSyncError(
            f"{ref.owner_kind} {ref.login!r} is not visible: this token "
            "cannot read it. Check the owner in the Project URL and 'gh auth "
            "status'."
        )
    project = owner.get("projectV2")
    if not isinstance(project, dict) or (
        str(project.get("url", "")).casefold() != url.casefold()
    ):
        raise ProjectSyncError(
            f"{url} is not available: it does not exist, is not visible, or "
            f"resolves to another URL. Check {SETTING} and the token's "
            "Project access."
        )
    nodes = (project.get("fields") or {}).get("nodes") or []
    problems = {name: field_problem(nodes, name) for name in FIELD_TYPES}
    return ReadOnlyProject(
        url,
        str(project.get("title", "")),
        ", ".join(sorted(scopes & READ_SCOPES)) if scopes else "unknown",
        {name: problem for name, problem in problems.items() if problem},
    )


def board_items(run: Runner, url: str, repo: str) -> dict[int, BoardItem]:
    """Read every Project item that holds an Issue of ``repo``."""
    ref = parse_project_url(url)
    found: dict[int, BoardItem] = {}
    cursor = ""
    while True:
        variables: dict[str, object] = {
            "login": ref.login,
            "number": ref.number,
        }
        if cursor:
            variables["cursor"] = cursor
        data = graphql(run, ITEMS_QUERY % ref.owner_kind, **variables)
        items = ((data.get("owner") or {}).get("projectV2") or {}).get(
            "items"
        ) or {}
        for node in items.get("nodes") or []:
            item = board_item(node, repo)
            if item is not None:
                found[item.number] = item
        page = items.get("pageInfo") or {}
        cursor = str(page.get("endCursor") or "")
        if not page.get("hasNextPage") or not cursor:
            return found


def board_item(node: object, repo: str) -> BoardItem | None:
    """Return one item of ``repo``'s Issue, or None for anything else."""
    if not isinstance(node, Mapping):
        return None
    content = node.get("content") or {}
    owner = (content.get("repository") or {}).get("nameWithOwner", "")
    if "number" not in content or str(owner).casefold() != repo.casefold():
        return None
    return BoardItem(
        int(content["number"]),
        str(content.get("state", "")).upper() == "CLOSED",
        (node.get("start") or {}).get("date"),
        (node.get("target") or {}).get("date"),
        (node.get("status") or {}).get("name"),
    )


def repository_issues(run: Runner, repo: str) -> list[IssueFacts]:
    """Read every Issue (open or closed, no PRs) of one repository."""
    pages = json.loads(
        run(
            [
                "api",
                "--paginate",
                "--slurp",
                f"repos/{repo}/issues?state=all&per_page=100",
            ]
        )
        or "[]"
    )
    return [
        issue_facts(item, repo)
        for page in pages
        for item in page
        if isinstance(item, dict) and "pull_request" not in item
    ]


def drift_lines(
    project: ReadOnlyProject,
    issues: list[IssueFacts],
    items: dict[int, BoardItem],
) -> list[str]:
    """Return one WARNING line per drift; never change anything."""
    lines: list[str] = []
    eligible = {issue.number for issue in issues if not issue.skip}
    if STATUS_FIELD not in project.missing_fields:
        for number, item in sorted(items.items()):
            if (
                not item.closed
                or (item.status or "").casefold() == DONE.casefold()
            ):
                continue
            shown = repr(item.status) if item.status else "empty"
            lines.append(
                f"WARNING: #{number} is closed but its Project Status is "
                f"{shown}: the template never moves Status. Set it to "
                f"'{DONE}' in the Project, or let a Project workflow do it."
            )
    lines.extend(
        f"WARNING: #{number} is not on the Project: it is a Milestone "
        "tracker or a standalone Issue, so the board rules include it. "
        f"Run 'csarc issue sync-project --issue {number}'."
        for number in sorted(eligible - set(items))
    )
    dated = [
        name
        for name in (START_FIELD, TARGET_FIELD)
        if name not in project.missing_fields
    ]
    for number in sorted(eligible & set(items)):
        item = items[number]
        values = {START_FIELD: item.start, TARGET_FIELD: item.target}
        empty = [name for name in dated if not values[name]]
        if empty:
            lines.append(
                f"WARNING: #{number} has no {' or '.join(empty)}: the date "
                "is empty on the Project. Run 'csarc issue sync-project "
                f"--issue {number}'."
            )
    return lines


def report(
    run: Runner,
    url: str,
    repo: str,
    issues: list[IssueFacts],
    *,
    whole_repository: bool,
    out: TextIO,
) -> int:
    """Print the drift report; return 1 when drift was found, else 0."""
    project = resolve_for_report(run, url)
    out.write(
        f"Project: {project.url} ({project.title}); read-only drift report; "
        f"token scope {project.scope}\n"
    )
    for name, problem in sorted(project.missing_fields.items()):
        check = "closed-but-not-Done" if name == STATUS_FIELD else "date"
        out.write(
            f"NOTICE: Field {name!r} cannot be read: {problem}; the {check} "
            "check is skipped.\n"
        )
    items = board_items(run, url, repo)
    if not whole_repository:
        selected = {issue.number for issue in issues}
        items = {n: item for n, item in items.items() if n in selected}
    lines = drift_lines(project, issues, items)
    out.writelines(line + "\n" for line in lines)
    if lines:
        out.write(
            f"NOTICE: Found {len(lines)} drift item(s) in {len(issues)} "
            "Issue(s); nothing was written.\n"
        )
        return 1
    out.write(
        f"OK: No Project drift in {len(issues)} Issue(s); nothing was "
        "written.\n"
    )
    return 0


def command_report(
    repo: str,
    *,
    issue: int | None,
    milestone: int | None,
    run: Runner = gh_runner,
    out: TextIO | None = None,
    config: Path = CONFIG_FILE,
) -> int:
    """Run `csarc issue sync-project --report` (read-only, #1346 AC1).

    With neither ``issue`` nor ``milestone`` the report covers every Issue
    of the repository.
    """
    stream = out or sys.stdout
    url = configured_project_url(config)
    if not url:
        stream.write(
            f"NOTICE: {SETTING} is empty; the Project drift report is "
            "disabled and no Project API was called.\n"
        )
        return 0
    repo = repo or current_repo(run)
    try:
        if issue is not None:
            issues = [read_issue(run, repo, issue)]
        elif milestone is not None:
            issues = milestone_issues(run, repo, milestone)
        else:
            issues = repository_issues(run, repo)
        return report(
            run,
            url,
            repo,
            issues,
            whole_repository=issue is None and milestone is None,
            out=stream,
        )
    except ProjectSyncError as error:
        stream.write(
            f"ERROR: Project drift report failed: {error}\nNothing was "
            "written; rerun the same command after the fix.\n"
        )
        return 1
