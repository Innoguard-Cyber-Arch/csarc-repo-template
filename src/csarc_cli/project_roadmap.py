"""Project an Issue's Roadmap dates onto a configured ProjectV2 (#1080, K2).

`.csarc/config.yml` keeps one optional setting, `github_project_url`: the
full organization or user ProjectV2 URL (#1058 decision 23, SPEC-009 §9).
An empty value disables everything here, so no Project API is ever called.
Repository Projects stay disabled; the external ProjectV2 is only a
projection of Issue facts:

* ``Project start`` is the UTC date the Issue was created;
* ``Project target`` is the UTC date of the current Milestone ``due_on``,
  or an explicit ``--target-date`` when the Issue has no due date.

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
from datetime import UTC, date, datetime
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
REQUIRED_SCOPE = "project"

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


def issue_facts(item: Mapping[str, Any], repo: str) -> IssueFacts:
    """Return projection facts for one REST Issue; refuse pull requests."""
    if "pull_request" in item:
        raise ProjectSyncError(
            f"#{item.get('number')} is a pull request; only Issues are "
            "projected"
        )
    milestone = item.get("milestone") or {}
    due = milestone.get("due_on")
    return IssueFacts(
        repo,
        int(item["number"]),
        str(item["node_id"]),
        utc_date(str(item["created_at"])),
        str(milestone.get("title", "")),
        utc_date(str(due)) if due else "",
    )


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


def target_for(issue: IssueFacts, target_date: str) -> str:
    """Return the target: the Milestone due date, else an explicit date."""
    if issue.due:
        if target_date and target_date != issue.due:
            raise ProjectSyncError(
                f"#{issue.number}'s Milestone {issue.milestone!r} is due "
                f"{issue.due}; that is the target, so drop --target-date"
            )
        return issue.due
    if not target_date:
        raise ProjectSyncError(
            f"#{issue.number} has no Milestone due date; pass "
            "--target-date YYYY-MM-DD"
        )
    return target_date


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


def read_item(
    run: Runner, project: Project, issue: IssueFacts
) -> tuple[str | None, str | None, str | None]:
    """Return the Issue's item in this Project and its two dates."""
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
        return None, None, None
    item = found[0]
    start = (item.get("start") or {}).get("date")
    target = (item.get("target") or {}).get("date")
    return str(item["id"]), start, target


def plan_issue(
    run: Runner, project: Project, issue: IssueFacts, target_date: str = ""
) -> Plan:
    """Compare the Issue's projected dates with what the Project holds."""
    target = target_for(issue, target_date)
    item_id, start, current_target = read_item(run, project, issue)
    return Plan(
        issue,
        item_id,
        [
            Change(START_FIELD, project.start_field, start, issue.start),
            Change(TARGET_FIELD, project.target_field, current_target, target),
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
    _item, start, target = read_item(run, project, plan.issue)
    if (start, target) != tuple(c.desired for c in plan.changes):
        raise ProjectSyncError(
            f"#{plan.issue.number} read back start {start} and target "
            f"{target} after the write"
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
) -> Project:
    """Verify the Project and the target before `gh issue create` runs."""
    project = resolve_project(run, url)
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
        due = (
            utc_date(str(found[0]["due_on"])) if found[0].get("due_on") else ""
        )
    if due and target_date and due != target_date:
        raise ProjectSyncError(
            f"Milestone {milestone!r} is due {due}; that is the target, so "
            "drop --target-date"
        )
    if not due and not target_date:
        raise ProjectSyncError(
            "the new Issue has no Milestone due date; pass --target-date "
            "YYYY-MM-DD before `--`"
        )
    return project


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
    state: dict[str, Project] = {}

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
            issue = read_issue(run, repo, number)
            status = sync(
                run,
                state["project"],
                [issue],
                target_date=target_date,
                out=stream,
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
        project = resolve_project(run, url)
        issues = (
            [read_issue(run, repo, issue)]
            if issue is not None
            else milestone_issues(run, repo, int(milestone or 0))
        )
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
