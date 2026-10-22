"""Project an Issue's Roadmap dates onto a configured ProjectV2 (#1080, K2).

`.csarc/config.yml` keeps one optional setting, `github_project_url`: the
full organization or user ProjectV2 URL (#1058 decision 23, SPEC-009 §10).
An empty value disables everything here, so no Project API is ever called.
Repository Projects stay disabled; the external ProjectV2 is only a
projection of Issue facts, with fixed board rules (#1186):

* only Milestone trackers and standalone Issues (no parent, not in a
  Milestone that has a tracker) are added; work Issues and sub-issues are
  skipped with a reason and never written;
* ``Project start`` is the Asia/Taipei date the Issue was created;
* ``Project target`` is the UTC date of the current Milestone ``due_on``,
  else an explicit ``--target-date``, else the start date plus 14 calendar
  days; once the Issue is complete it is the Asia/Taipei completion date
  instead (#1179): the date its Project ``Status`` became ``Done``, else
  its ``closed_at``.

Every project, field, and item ID is resolved live and never saved. The
sync is idempotent: an item is added by Issue/Project identity (GitHub's
``addProjectV2ItemById`` returns the existing item), empty dates are
written directly, and a different existing date is shown as a diff and
overwritten only after confirmation. A failed write never deletes the
Issue; it prints one rerunnable repair command instead.

This module is CLI-only and never ships to a generated project.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TextIO

import yaml  # type: ignore[import-untyped]

from csarc_cli.settings_schema import PROJECT_URL

Runner = Callable[[list[str]], str]
Prompt = Callable[[str], str]

CONFIG_FILE = Path(".csarc/config.yml")
SETTING = "github_project_url"
START_FIELD = "Project start"
TARGET_FIELD = "Project target"
STATUS_FIELD = "Status"
DONE = "Done"
REQUIRED_SCOPE = "project"
# The board's day boundary (#1186): Taiwan has no DST, so a fixed +08:00
# offset equals Asia/Taipei without depending on a tz database.
TAIPEI = timezone(timedelta(hours=8), "Asia/Taipei")
DEFAULT_TARGET_DAYS = 14
TRACKER_LINK = re.compile(r"(?mi)^Lifecycle Issue:\s*#([0-9]+)\s*$")

PROJECT_QUERY = """
query($login: String!, $number: Int!) {
  owner: %s(login: $login) {
    login
    projectV2(number: $number) {
      id url title closed viewerCanUpdate
      fields(first: 100) {
        nodes { ... on ProjectV2FieldCommon { id name dataType } }
      }
    }
  }
}
"""
ITEM_QUERY = """
query($id: ID!) {
  node(id: $id) {
    ... on Issue {
      projectItems(first: 100) {
        nodes {
          id
          project { id }
          start: fieldValueByName(name: "Project start") {
            ... on ProjectV2ItemFieldDateValue { date }
          }
          target: fieldValueByName(name: "Project target") {
            ... on ProjectV2ItemFieldDateValue { date }
          }
          status: fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name updatedAt }
          }
        }
      }
    }
  }
}
"""
ADD_ITEM = """
mutation($project: ID!, $content: ID!) {
  addProjectV2ItemById(input: {projectId: $project, contentId: $content}) {
    item { id }
  }
}
"""
SET_DATE = """
mutation($project: ID!, $item: ID!, $field: ID!, $date: Date!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $project, itemId: $item, fieldId: $field,
    value: {date: $date}
  }) { projectV2Item { id } }
}
"""


class ProjectSyncError(RuntimeError):
    """A Project check or write failed; the message says what to do."""


def gh_runner(command: list[str]) -> str:
    """Run one `gh` command and return stdout, failing closed."""
    result = subprocess.run(  # noqa: S603
        ["gh", *command],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        if "rate limit" in detail.casefold():
            detail = f"GitHub API rate limit reached ({detail})"
        raise ProjectSyncError(f"gh {command[0]} failed: {detail}")
    return result.stdout


@dataclass(frozen=True)
class ProjectRef:
    """The owner and number one configured URL names."""

    url: str
    owner_kind: str
    login: str
    number: int


def parse_project_url(url: str) -> ProjectRef:
    """Accept only a full organization or user ProjectV2 URL."""
    match = PROJECT_URL.fullmatch(url)
    if match is None:
        raise ProjectSyncError(
            f"{SETTING} {url!r} is not a full ProjectV2 URL; use "
            "https://github.com/orgs/<org>/projects/<n> or "
            "https://github.com/users/<user>/projects/<n>"
        )
    return ProjectRef(
        url,
        "organization" if match["kind"] == "orgs" else "user",
        match["login"],
        int(match["number"]),
    )


def configured_project_url(path: Path = CONFIG_FILE) -> str:
    """Return the saved URL, or '' when the setting disables Projects."""
    if not path.is_file():
        return ""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    value = raw.get(SETTING, "") if isinstance(raw, dict) else ""
    if value in {None, ""}:
        return ""
    if not isinstance(value, str):
        raise ProjectSyncError(f"{SETTING} in {path} must be a string")
    parse_project_url(value)
    return value


def graphql(run: Runner, query: str, **variables: object) -> dict[str, Any]:
    """Run one GraphQL document through `gh api graphql`."""
    command = ["api", "graphql", "-f", f"query={query}"]
    for name, value in variables.items():
        flag = "-F" if isinstance(value, int) else "-f"
        command += [flag, f"{name}={value}"]
    payload = json.loads(run(command) or "{}")
    errors = payload.get("errors") or []
    if errors:
        message = "; ".join(str(error.get("message")) for error in errors)
        if any(error.get("type") == "RATE_LIMITED" for error in errors):
            message = f"GitHub API rate limit reached ({message})"
        raise ProjectSyncError(f"GitHub GraphQL failed: {message}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ProjectSyncError("GitHub GraphQL returned no data")
    return data


def token_scopes(run: Runner) -> set[str] | None:
    """Return the token's OAuth scopes, or None when GitHub does not say."""
    try:
        output = run(["api", "--include", "rate_limit"])
    except ProjectSyncError:
        return None
    for line in output.splitlines():
        if not line.strip():
            break
        name, _, value = line.partition(":")
        if name.strip().casefold() == "x-oauth-scopes":
            return {scope.strip() for scope in value.split(",") if scope}
    return None


@dataclass(frozen=True)
class Project:
    """One live-resolved, writable ProjectV2 with its two date fields."""

    id: str
    url: str
    title: str
    start_field: str
    target_field: str
    scope: str


def date_field(nodes: list[Any], name: str) -> str:
    """Return the ID of the one DATE field called ``name``."""
    found = [
        node
        for node in nodes
        if isinstance(node, dict)
        and str(node.get("name", "")).casefold() == name.casefold()
    ]
    if len(found) != 1:
        raise ProjectSyncError(
            f"the Project needs exactly one field named {name!r} "
            f"(found {len(found)}); fix the Project fields first"
        )
    if found[0].get("dataType") != "DATE":
        raise ProjectSyncError(
            f"Project field {name!r} is {found[0].get('dataType')}; it "
            "must be a DATE field"
        )
    return str(found[0]["id"])


def resolve_project(run: Runner, url: str) -> Project:
    """Read back owner, project, permission, and fields before any write."""
    ref = parse_project_url(url)
    scopes = token_scopes(run)
    if scopes is not None and REQUIRED_SCOPE not in scopes:
        listed = ", ".join(sorted(scopes)) or "none"
        raise ProjectSyncError(
            f"the GitHub token lacks the `{REQUIRED_SCOPE}` scope (has: "
            f"{listed}); run `gh auth refresh -s {REQUIRED_SCOPE}`"
        )
    data = graphql(
        run, PROJECT_QUERY % ref.owner_kind, login=ref.login, number=ref.number
    )
    owner = data.get("owner")
    if not isinstance(owner, dict):
        raise ProjectSyncError(
            f"{ref.owner_kind} {ref.login!r} is not visible to this token"
        )
    if str(owner.get("login", "")).casefold() != ref.login.casefold():
        raise ProjectSyncError(
            f"GitHub resolved owner {owner.get('login')!r}, not {ref.login!r}"
        )
    project = owner.get("projectV2")
    if not isinstance(project, dict):
        raise ProjectSyncError(f"{url} does not exist or is not visible")
    if str(project.get("url", "")).casefold() != url.casefold():
        raise ProjectSyncError(
            f"GitHub resolved {project.get('url')!r}, not {url}"
        )
    if project.get("closed"):
        raise ProjectSyncError(f"{url} is closed")
    if project.get("viewerCanUpdate") is not True:
        raise ProjectSyncError(
            f"this token cannot update {url} (viewerCanUpdate is false)"
        )
    nodes = (project.get("fields") or {}).get("nodes") or []
    return Project(
        str(project["id"]),
        url,
        str(project.get("title", "")),
        date_field(nodes, START_FIELD),
        date_field(nodes, TARGET_FIELD),
        REQUIRED_SCOPE if scopes is not None else "unknown",
    )


def utc_date(timestamp: str) -> str:
    """Return the UTC calendar date of one GitHub ISO-8601 timestamp."""
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).date().isoformat()


def taipei_date(timestamp: str) -> str:
    """Return the Asia/Taipei calendar date of one GitHub timestamp."""
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(TAIPEI).date().isoformat()


def default_target(start: str) -> str:
    """Return the fixed fallback target: start plus 14 calendar days."""
    return (
        date.fromisoformat(start) + timedelta(days=DEFAULT_TARGET_DAYS)
    ).isoformat()


def milestone_tracker(milestone: Mapping[str, Any]) -> int | None:
    """Return the tracker number a Milestone description links, if any."""
    found = TRACKER_LINK.search(str(milestone.get("description") or ""))
    return int(found[1]) if found else None


def checked_date(value: str) -> str:
    """Validate one explicit ``--target-date``."""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ProjectSyncError(
            f"--target-date {value!r} must be YYYY-MM-DD"
        ) from error


@dataclass(frozen=True)
class IssueFacts:
    """The live Issue facts the Roadmap dates are projected from."""

    repo: str
    number: int
    node_id: str
    start: str
    milestone: str
    due: str
    closed: str = ""
    skip: str = ""


def issue_facts(item: Mapping[str, Any], repo: str) -> IssueFacts:
    """Return projection facts for one REST Issue; refuse pull requests."""
    if "pull_request" in item:
        raise ProjectSyncError(
            f"#{item.get('number')} is a pull request; only Issues are "
            "projected"
        )
    milestone = item.get("milestone") or {}
    due = milestone.get("due_on")
    number = int(item["number"])
    return IssueFacts(
        repo,
        number,
        str(item["node_id"]),
        taipei_date(str(item["created_at"])),
        str(milestone.get("title", "")),
        utc_date(str(due)) if due else "",
        taipei_date(str(item["closed_at"]))
        if item.get("state") == "closed" and item.get("closed_at")
        else "",
        board_skip(item, milestone, number),
    )


def board_skip(
    item: Mapping[str, Any], milestone: Mapping[str, Any], number: int
) -> str:
    """Return why an Issue stays off the board, or '' when it belongs.

    The board holds only Milestone trackers and standalone Issues (#1186).
    """
    tracker = milestone_tracker(milestone)
    if tracker == number:
        return ""
    if item.get("parent_issue_url"):
        return "it is a sub-issue (it has a parent Issue)"
    if tracker is not None:
        return (
            f"it is a work Issue of Milestone {milestone.get('title')!r} "
            f"(tracker #{tracker})"
        )
    return ""


def read_issue(run: Runner, repo: str, number: int) -> IssueFacts:
    """Read one Issue's current facts."""
    return issue_facts(
        json.loads(run(["api", f"repos/{repo}/issues/{number}"])), repo
    )


def milestone_issues(
    run: Runner, repo: str, milestone: int
) -> list[IssueFacts]:
    """Read every Issue (open or closed, no PRs) in one Milestone."""
    pages = json.loads(
        run(
            [
                "api",
                "--paginate",
                "--slurp",
                f"repos/{repo}/issues?milestone={milestone}&state=all"
                "&per_page=100",
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


def target_for(issue: IssueFacts, target_date: str, done: str = "") -> str:
    """Return the target date for one Issue (SPEC-009 §10).

    A complete Issue targets its completion date: the day its Project
    ``Status`` became ``Done`` (``done``), else the day it was closed. The
    Done date wins when both exist, because the owner's acceptance is the
    later, deliberate completion. An open Issue targets its Milestone due
    date, else the explicit ``--target-date``, else its start date plus 14
    calendar days; a complete Issue ignores ``--target-date`` so one
    Milestone-wide value cannot misdate it.
    """
    if done or issue.closed:
        return done or issue.closed
    if issue.due:
        if target_date and target_date != issue.due:
            raise ProjectSyncError(
                f"#{issue.number}'s Milestone {issue.milestone!r} is due "
                f"{issue.due}; that is the target, so drop --target-date"
            )
        return issue.due
    return target_date or default_target(issue.start)


@dataclass(frozen=True)
class Change:
    """One date field: what the Project holds and what it should hold."""

    name: str
    field_id: str
    current: str | None
    desired: str

    @property
    def overwrite(self) -> bool:
        """True when a different existing value would be replaced."""
        return self.current is not None and self.current != self.desired


@dataclass
class Plan:
    """The idempotent sync plan for one Issue."""

    issue: IssueFacts
    item_id: str | None
    changes: list[Change] = field(default_factory=list)

    @property
    def pending(self) -> list[Change]:
        """The fields that still differ from their desired value."""
        return [c for c in self.changes if c.current != c.desired]


@dataclass(frozen=True)
class Item:
    """The Issue's item in this Project: dates and the Done date, if any."""

    id: str | None = None
    start: str | None = None
    target: str | None = None
    done: str = ""


def read_item(run: Runner, project: Project, issue: IssueFacts) -> Item:
    """Return the Issue's item in this Project and its dates."""
    data = graphql(run, ITEM_QUERY, id=issue.node_id)
    nodes = ((data.get("node") or {}).get("projectItems") or {}).get(
        "nodes"
    ) or []
    found = [
        node
        for node in nodes
        if isinstance(node, dict)
        and (node.get("project") or {}).get("id") == project.id
    ]
    if not found:
        return Item()
    item = found[0]
    status = item.get("status") or {}
    done = (
        taipei_date(str(status["updatedAt"]))
        if str(status.get("name", "")).casefold() == DONE.casefold()
        and status.get("updatedAt")
        else ""
    )
    return Item(
        str(item["id"]),
        (item.get("start") or {}).get("date"),
        (item.get("target") or {}).get("date"),
        done,
    )


def plan_issue(
    run: Runner, project: Project, issue: IssueFacts, target_date: str = ""
) -> Plan:
    """Compare the Issue's projected dates with what the Project holds."""
    item = read_item(run, project, issue)
    target = target_for(issue, target_date, item.done)
    return Plan(
        issue,
        item.id,
        [
            Change(START_FIELD, project.start_field, item.start, issue.start),
            Change(TARGET_FIELD, project.target_field, item.target, target),
        ],
    )


def apply_plan(run: Runner, project: Project, plan: Plan) -> None:
    """Add the item if needed, write each differing date, then read back."""
    item_id = plan.item_id
    if item_id is None:
        data = graphql(
            run, ADD_ITEM, project=project.id, content=plan.issue.node_id
        )
        item_id = str(data["addProjectV2ItemById"]["item"]["id"])
    for change in plan.pending:
        graphql(
            run,
            SET_DATE,
            project=project.id,
            item=item_id,
            field=change.field_id,
            date=change.desired,
        )
    item = read_item(run, project, plan.issue)
    if (item.start, item.target) != tuple(c.desired for c in plan.changes):
        raise ProjectSyncError(
            f"#{plan.issue.number} read back start {item.start} and target "
            f"{item.target} after the write"
        )


def describe(plan: Plan) -> list[str]:
    """Return one transcript line per Issue: unchanged, set, or diff."""
    parts: list[str] = []
    for change in plan.changes:
        if change.current == change.desired:
            parts.append(f"{change.name} {change.desired} (unchanged)")
        elif change.current is None:
            parts.append(f"{change.name} {change.desired} (set)")
        else:
            parts.append(
                f"{change.name} {change.current} -> {change.desired} "
                "(overwrite needs confirmation)"
            )
    item = "existing item" if plan.item_id else "new item"
    return [f"#{plan.issue.number} [{item}]: " + "; ".join(parts)]


def repair_command(
    repo: str,
    *,
    issue: int | None = None,
    milestone: int | None = None,
    target_date: str = "",
) -> str:
    """Return the one rerunnable, idempotent repair command."""
    command = "csarc issue sync-project"
    command += (
        f" --issue {issue}"
        if issue is not None
        else (f" --milestone {milestone}")
    )
    if target_date:
        command += f" --target-date {target_date}"
    return command + f" --repo {repo}"


def on_board(issues: list[IssueFacts], out: TextIO) -> list[IssueFacts]:
    """Return the Issues the board holds; explain each one it skips."""
    for issue in issues:
        if issue.skip:
            out.write(
                f"#{issue.number} skipped: {issue.skip}; only Milestone "
                "trackers and standalone Issues go to the Project, so no "
                "Project write was made.\n"
            )
    return [issue for issue in issues if not issue.skip]


def sync(
    run: Runner,
    project: Project,
    issues: list[IssueFacts],
    *,
    target_date: str = "",
    confirm: bool = False,
    ask: Prompt | None = None,
    out: TextIO,
) -> int:
    """Plan every Issue first, confirm overwrites, then write idempotently.

    Returns 0 when the Project matches, 1 when an overwrite was not
    confirmed (nothing was written). Raises :class:`ProjectSyncError` on a
    failed check or write.
    """
    out.write(
        f"Project: {project.url} ({project.title}); viewerCanUpdate true; "
        f"token scope {project.scope}\n"
    )
    plans = [plan_issue(run, project, issue, target_date) for issue in issues]
    for plan in plans:
        out.writelines(line + "\n" for line in describe(plan))
    overwrites = [c for plan in plans for c in plan.changes if c.overwrite]
    if overwrites and not confirm:
        answer = (
            ask("Overwrite the listed Project dates? [y/N] ") if ask else ""
        )
        if answer.strip().casefold() != "y":
            out.write(
                "Not confirmed; nothing was written. Rerun with --yes to "
                "overwrite the listed dates.\n"
            )
            return 1
    for plan in plans:
        if plan.item_id is None or plan.pending:
            apply_plan(run, project, plan)
    out.write(f"Synced {len(plans)} Issue(s); Project dates read back.\n")
    return 0


ISSUE_URL = re.compile(
    r"https://github\.com/(?P<repo>[^/\s]+/[^/\s]+)/issues/(?P<number>[0-9]+)"
)


def precheck_create(
    run: Runner, url: str, repo: str, milestone: str, target_date: str
) -> Project | None:
    """Verify the Project and the target before `gh issue create` runs.

    Returns None when the new Issue cannot belong on the board: a Milestone
    that already has a tracker makes it a work Issue (#1186), so no Project
    API is called at all.
    """
    due = ""
    if milestone:
        pages = json.loads(
            run(
                [
                    "api",
                    "--paginate",
                    "--slurp",
                    f"repos/{repo}/milestones?state=open&per_page=100",
                ]
            )
            or "[]"
        )
        found = [
            item
            for page in pages
            for item in page
            if isinstance(item, dict) and item.get("title") == milestone
        ]
        if len(found) != 1:
            raise ProjectSyncError(
                f"Milestone {milestone!r} is not one open Milestone of {repo}"
            )
        if milestone_tracker(found[0]) is not None:
            return None
        due = (
            utc_date(str(found[0]["due_on"])) if found[0].get("due_on") else ""
        )
    if due and target_date and due != target_date:
        raise ProjectSyncError(
            f"Milestone {milestone!r} is due {due}; that is the target, so "
            "drop --target-date"
        )
    return resolve_project(run, url)


def issue_reference(output: str) -> tuple[str, int]:
    """Return the repository and number `gh issue create` printed."""
    match = ISSUE_URL.search(output)
    if match is None:
        raise ProjectSyncError(
            "could not read the created Issue URL from `gh issue create`"
        )
    return match["repo"], int(match["number"])


def option_value(arguments: list[str], *flags: str) -> str:
    """Return the last value of one `gh` option, or ''."""
    value = ""
    for index, argument in enumerate(arguments):
        flag, equals, inline = argument.partition("=")
        if flag in flags and equals:
            value = inline
        elif argument in flags and index + 1 < len(arguments):
            value = arguments[index + 1]
    return value


def current_repo(run: Runner) -> str:
    """Return the checkout's `owner/name`."""
    return run(
        ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]
    ).strip()


def create_hooks(
    url: str,
    target_date: str,
    run: Runner = gh_runner,
    out: TextIO | None = None,
) -> tuple[Callable[[list[str]], None], Callable[[str], int]]:
    """Return the before/after hooks `csarc issue create` runs (AC3/AC4/AC6).

    ``before`` verifies the Project, permission, scope, fields, and target
    before the Issue exists; ``after`` adds the new Issue and writes its
    dates. A failure after creation keeps the Issue and prints one repair
    command; nothing is ever deleted.
    """
    state: dict[str, Project | None] = {}

    def before(arguments: list[str]) -> None:
        repo = option_value(arguments, "--repo", "-R") or current_repo(run)
        try:
            state["project"] = precheck_create(
                run,
                url,
                repo,
                option_value(arguments, "--milestone", "-m"),
                target_date,
            )
        except ProjectSyncError as error:
            raise ProjectSyncError(
                f"Project check failed; no Issue was created: {error}"
            ) from error

    def after(output: str) -> int:
        stream = out or sys.stdout
        repo, number = issue_reference(output)
        try:
            issues = on_board([read_issue(run, repo, number)], stream)
            project = state.get("project")
            if issues and project is None:
                project = resolve_project(run, url)
            status = (
                sync(
                    run,
                    project,
                    issues,
                    target_date=target_date,
                    out=stream,
                )
                if issues and project is not None
                else 0
            )
        except ProjectSyncError as error:
            stream.write(f"Project sync failed: {error}\n")
            status = 1
        if status:
            stream.write(
                f"Issue #{number} was created and kept. Repair (idempotent): "
                + repair_command(repo, issue=number, target_date=target_date)
                + "\n"
            )
        return status

    return before, after


def command_sync(
    repo: str,
    *,
    issue: int | None,
    milestone: int | None,
    target_date: str = "",
    confirm: bool = False,
    run: Runner = gh_runner,
    ask: Prompt | None = None,
    out: TextIO | None = None,
    config: Path = CONFIG_FILE,
) -> int:
    """Run `csarc issue sync-project` for one Issue or one Milestone (AC5)."""
    stream = out or sys.stdout
    url = configured_project_url(config)
    if not url:
        stream.write(
            f"{SETTING} is empty; Project sync is disabled and no Project "
            "API was called.\n"
        )
        return 0
    target = checked_date(target_date) if target_date else ""
    repo = repo or current_repo(run)
    try:
        issues = on_board(
            [read_issue(run, repo, issue)]
            if issue is not None
            else milestone_issues(run, repo, int(milestone or 0)),
            stream,
        )
        if not issues:
            stream.write(
                "No selected Issue belongs on the Project; no Project API "
                "was called.\n"
            )
            return 0
        project = resolve_project(run, url)
        return sync(
            run,
            project,
            issues,
            target_date=target,
            confirm=confirm,
            ask=ask,
            out=stream,
        )
    except ProjectSyncError as error:
        stream.write(
            f"Project sync failed: {error}\nRepair (idempotent): "
            + repair_command(
                repo, issue=issue, milestone=milestone, target_date=target
            )
            + "\n"
        )
        return 1
