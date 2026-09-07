#!/usr/bin/env python3
"""Generate the governance audit trail from live GitHub state (Issue #535).

This repository already enforces PR/Issue/Milestone governance through
`scripts/validate-pr-policy` and `scripts/sync_milestone_state.py`, but
proving that past activity actually followed those rules previously meant
reading raw `git log` / GitHub history by hand. This script is the
automatic-generation mechanism the Issue's research called for: the
query logic below is the source of truth, and the two Markdown files it
writes are derived, regenerable artifacts -- never hand-edited.

It produces two files:

* `pr-audit.md` -- one row per pull request merged into the target branch
  (`main` by default): PR open/merge time, source/target branch, the
  linked Issue's open/close time, Milestone, developer(s), reviewer(s),
  and a `governance_stage` marker.
* `rule-changes.md` -- one row per merged pull request that touched a
  rule path (`policies/` by default): change time, `proposed_by` +
  `proposing_pr`, `approved_by` + `approving_review`.

`governance_stage` (alpha/beta/stable) is deliberately a different axis
from `profiles/catalog.yaml`'s repository-scoped `stage` field (see the
Issue body's naming-collision warning). It classifies the *source*
branch pattern a pull request used to reach the target branch, not the
target itself -- every included row targets the same branch, so only the
source pattern carries a signal. The three delivery paths this maps
across are the ones `docs/ci-policy.md` already documents:

* `dev/i<N>-*`            -> "alpha"  (canary: an explicit, Issue-justified
                                        exception path)
* `dev/m<N>-*`, `promote/m<N>-*` -> "beta" (Milestone delivery: a batched,
                                        cross-Issue promotion)
* anything else (ordinary `type/<N>-*`, `fix/<N>-*`, release branches)
                          -> "stable" (the default, most-exercised path
                                        straight to the target branch)

Historical reviewer/approval data is reported as-is, even when empty.
`docs/history-audit-2026-08.md` already found that this repository's
GitHub "reviews" endpoint returned zero entries for every pull request it
audited as of 2026-08-24; this generator surfaces the same reality rather
than inventing retroactive approvals -- an empty reviewer or approval
column is a finding, not a bug in this script.

Live data is fetched with `gh api graphql`, paginating a `search(...)`
query bounded by `--since` and/or `--limit` so an ordinary run does not
have to walk the repository's entire history (a one-time full backfill
already exists in `docs/history-audit-2026-08.md`). `--fixture` replaces
the live call with a pre-fetched JSON array of already-flattened PR
nodes, so the regression test in `tests/test_generate_audit_trail.py`
never needs network access or GitHub auth.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]

DEFAULT_RULE_PREFIXES = ("policies/",)
DEFAULT_OUT_DIR = Path("docs/audit-trail")
DEFAULT_PR_AUDIT_FILE = "pr-audit.md"
DEFAULT_RULE_CHANGE_FILE = "rule-changes.md"
DEFAULT_LIMIT = 200
PAGE_SIZE = 25

# first: {PAGE_SIZE} is substituted below; kept out of an f-string so the
# GraphQL body itself stays a plain, easily-diffed triple-quoted literal.
GRAPHQL_QUERY = """
query($searchQuery: String!, $endCursor: String) {
  search(query: $searchQuery, type: ISSUE, first: PAGE_SIZE,
      after: $endCursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        title
        url
        createdAt
        mergedAt
        baseRefName
        headRefName
        author { login }
        milestone { title }
        reviews(first: 50, states: [APPROVED]) {
          nodes { author { login } url submittedAt }
        }
        commits(first: 100) {
          nodes { commit { authors(first: 5) { nodes { user { login } } } } }
        }
        files(first: 100) { nodes { path } }
        closingIssuesReferences(first: 5) {
          nodes { number createdAt closedAt }
        }
      }
    }
  }
}
""".replace("PAGE_SIZE", str(PAGE_SIZE))


class AuditTrailError(RuntimeError):
    """Raised when audit trail input cannot be retrieved or parsed."""


@dataclass(frozen=True)
class PullRequestRecord:
    """One merged pull request, normalized from a GraphQL PR node."""

    number: int
    title: str
    url: str
    created_at: str
    merged_at: str
    base_ref: str
    head_ref: str
    milestone: str | None
    author: str
    developers: tuple[str, ...]
    reviewers: tuple[str, ...]
    approvals: tuple[tuple[str, str], ...]
    issue_number: int | None
    issue_created_at: str | None
    issue_closed_at: str | None
    changed_paths: tuple[str, ...]


def governance_stage(head_ref: str) -> str:
    """Classify the delivery path a pull request used to reach its target.

    See the module docstring for the alpha/beta/stable mapping and why it
    is deliberately distinct from `profiles/catalog.yaml`'s `stage` field.
    """
    if re.match(r"^dev/i\d+-", head_ref):
        return "alpha"
    if re.match(r"^(dev|promote)/m\d+-", head_ref):
        return "beta"
    return "stable"


def _logins(nodes: list[JsonObject], key: str = "author") -> list[str]:
    """Collect distinct, sorted GitHub logins from a list of nodes."""
    logins: set[str] = set()
    for node in nodes:
        author = node.get(key)
        if isinstance(author, dict):
            login = author.get("login")
            if isinstance(login, str) and login:
                logins.add(login)
    return sorted(logins)


def _pr_author_login(node: JsonObject) -> str:
    """Return the PR opener's login, distinct from `developers`.

    `developers` (see `_developer_logins` below) is an alphabetically
    sorted union used for the general "who touched this" display; it must
    never stand in for "who proposed this", because sort order has no
    relationship to who actually opened the pull request. This field is
    the single, authoritative source for that maker identity.
    """
    author = node.get("author")
    if isinstance(author, dict):
        login = author.get("login")
        if isinstance(login, str) and login:
            return login
    return ""


def _developer_logins(node: JsonObject) -> tuple[str, ...]:
    """Union the PR author with every distinct commit-author login."""
    logins: set[str] = set(_logins([node]))
    for commit_node in node.get("commits", {}).get("nodes", []):
        commit = commit_node.get("commit", {})
        for author_node in commit.get("authors", {}).get("nodes", []):
            user = author_node.get("user")
            if isinstance(user, dict):
                login = user.get("login")
                if isinstance(login, str) and login:
                    logins.add(login)
    return tuple(sorted(logins))


def record_from_node(node: JsonObject) -> PullRequestRecord:
    """Normalize one GraphQL pull request node into a `PullRequestRecord`."""
    milestone = node.get("milestone")
    milestone_title = (
        milestone.get("title") if isinstance(milestone, dict) else None
    )

    review_nodes = node.get("reviews", {}).get("nodes", [])
    approvals = tuple(
        sorted(
            (
                (review["author"]["login"], review.get("url", ""))
                for review in review_nodes
                if isinstance(review.get("author"), dict)
                and review["author"].get("login")
            ),
            key=lambda pair: pair[0],
        )
    )

    closing_issues = node.get("closingIssuesReferences", {}).get("nodes", [])
    issue = closing_issues[0] if closing_issues else None

    changed_paths = tuple(
        sorted(
            entry["path"]
            for entry in node.get("files", {}).get("nodes", [])
            if isinstance(entry.get("path"), str)
        )
    )

    return PullRequestRecord(
        number=node["number"],
        title=node.get("title", ""),
        url=node.get("url", ""),
        created_at=node.get("createdAt", ""),
        merged_at=node.get("mergedAt") or "",
        base_ref=node.get("baseRefName", ""),
        head_ref=node.get("headRefName", ""),
        milestone=milestone_title,
        author=_pr_author_login(node),
        developers=_developer_logins(node),
        reviewers=tuple(_logins(review_nodes)),
        approvals=approvals,
        issue_number=issue.get("number") if issue else None,
        issue_created_at=issue.get("createdAt") if issue else None,
        issue_closed_at=issue.get("closedAt") if issue else None,
        changed_paths=changed_paths,
    )


def _run_gh_graphql(variables: dict[str, str], retries: int) -> JsonObject:
    """Run one paged GraphQL request, retrying without persisting output."""
    executable = shutil.which("gh")
    if executable is None:
        raise AuditTrailError("GitHub CLI (gh) is required")
    arguments = [executable, "api", "graphql", "-f", f"query={GRAPHQL_QUERY}"]
    for name, value in variables.items():
        arguments += ["-F", f"{name}={value}"]

    failure = ""
    for _attempt in range(retries):
        completed = subprocess.run(  # noqa: S603
            arguments,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            try:
                return json.loads(completed.stdout)
            except json.JSONDecodeError as error:
                raise AuditTrailError(
                    "gh api graphql returned invalid JSON"
                ) from error
        failure = completed.stderr.strip()
    raise AuditTrailError(failure or "gh api graphql failed")


def fetch_pull_request_nodes(
    repo: str,
    base: str,
    since: str | None,
    limit: int,
    retries: int,
) -> list[JsonObject]:
    """Page through merged pull requests via GitHub search, live."""
    search_query = f"repo:{repo} is:pr is:merged base:{base}"
    if since:
        search_query += f" merged:>={since}"

    nodes: list[JsonObject] = []
    end_cursor = ""
    while True:
        variables = {"searchQuery": search_query}
        if end_cursor:
            variables["endCursor"] = end_cursor
        payload = _run_gh_graphql(variables, retries)
        search = payload.get("data", {}).get("search")
        if not isinstance(search, dict):
            raise AuditTrailError("graphql: missing search connection")
        nodes.extend(search.get("nodes", []))
        page_info = search.get("pageInfo", {})
        if limit and len(nodes) >= limit:
            return nodes[:limit]
        if not page_info.get("hasNextPage"):
            return nodes
        end_cursor = page_info.get("endCursor", "")
        if not end_cursor:
            return nodes


def load_fixture_nodes(path: Path) -> list[JsonObject]:
    """Load pre-fetched PR nodes for fixture-driven, network-free runs."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise AuditTrailError("fixture must be a JSON array of PR nodes")
    return data


def _md_escape(value: str) -> str:
    """Escape a value for safe placement inside a Markdown table cell."""
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _join_or_placeholder(values: tuple[str, ...]) -> str:
    """Join values for a table cell, or a placeholder when none exist."""
    return ", ".join(values) if values else "(none recorded)"


def _preamble(title: str, repo: str, generated_at: str) -> list[str]:
    """Return the shared, non-hand-edited-warning header lines."""
    return [
        f"# {title}",
        "",
        f"Repository: `{repo}`",
        f"Generated: {generated_at}",
        "",
        "Auto-generated by `scripts/generate_audit_trail.py` from live "
        "GitHub state -- do not hand edit. Re-run the script for a "
        "current table; this file does not replace git as the "
        "authoritative history, it is a derived report for humans.",
        "",
    ]


def render_pr_audit_table(
    records: list[PullRequestRecord], repo: str, generated_at: str
) -> str:
    """Render the PR audit table Markdown, sorted by merge time."""
    lines = _preamble("Pull request audit trail", repo, generated_at)
    lines.append(
        "| PR | Title | Opened | Merged | Source -> Target | Issue | "
        "Issue opened | Issue closed | Milestone | Developers | "
        "Reviewers | governance_stage |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- "
        "| --- | --- | --- |"
    )

    ordered = sorted(
        records, key=lambda record: (record.merged_at, record.number)
    )
    for record in ordered:
        issue_cell = (
            f"#{record.issue_number}"
            if record.issue_number
            else ("(none recorded)")
        )
        lines.append(
            "| [#{number}]({url}) | {title} | {opened} | {merged} | "
            "`{head}` -> `{base}` | {issue} | {issue_opened} | "
            "{issue_closed} | {milestone} | {developers} | {reviewers} | "
            "{stage} |".format(
                number=record.number,
                url=record.url,
                title=_md_escape(record.title),
                opened=record.created_at or "(unknown)",
                merged=record.merged_at or "(unknown)",
                head=record.head_ref,
                base=record.base_ref,
                issue=issue_cell,
                issue_opened=record.issue_created_at or "(none recorded)",
                issue_closed=record.issue_closed_at or "(none recorded)",
                milestone=record.milestone or "(none recorded)",
                developers=_join_or_placeholder(record.developers),
                reviewers=_join_or_placeholder(record.reviewers),
                stage=governance_stage(record.head_ref),
            )
        )
    lines.append("")
    return "\n".join(lines)


def render_rule_change_log(
    records: list[PullRequestRecord],
    rule_prefixes: tuple[str, ...],
    repo: str,
    generated_at: str,
) -> str:
    """Render the rule-change maker/checker log, sorted by change time."""
    lines = _preamble("Governance rule change log", repo, generated_at)
    lines.append(
        f"Rule paths tracked: {', '.join(f'`{p}`' for p in rule_prefixes)}"
    )
    lines.append("")
    lines.append(
        "| Changed | proposed_by | proposing_pr | approved_by | "
        "approving_review |"
    )
    lines.append("| --- | --- | --- | --- | --- |")

    rule_records = [
        record
        for record in records
        if any(
            path.startswith(prefix)
            for path in record.changed_paths
            for prefix in rule_prefixes
        )
    ]
    ordered = sorted(
        rule_records, key=lambda record: (record.merged_at, record.number)
    )
    for record in ordered:
        approved_by = _join_or_placeholder(
            tuple(login for login, _url in record.approvals)
        )
        approving_review = _join_or_placeholder(
            tuple(url for _login, url in record.approvals if url)
        )
        lines.append(
            "| {changed} | {proposed_by} | [#{pr}]({url}) | "
            "{approved_by} | {approving_review} |".format(
                changed=record.merged_at or "(unknown)",
                # The PR's actual opener, not developers[0] -- that tuple
                # is an alphabetically sorted union of the author and every
                # commit author, so its first element is whichever login
                # sorts earliest, not necessarily who proposed the change.
                proposed_by=record.author or "(none recorded)",
                pr=record.number,
                url=record.url,
                approved_by=approved_by,
                approving_review=approving_review,
            )
        )
    lines.append("")
    return "\n".join(lines)


def build_records(
    nodes: list[JsonObject], base: str
) -> list[PullRequestRecord]:
    """Normalize nodes and keep only pull requests merged into `base`."""
    return [
        record_from_node(node)
        for node in nodes
        if node.get("baseRefName") == base and node.get("mergedAt")
    ]


def _default_repo() -> str:
    """Resolve `owner/name` for the current repository's `origin` remote."""
    executable = shutil.which("gh")
    if executable is None:
        raise AuditTrailError("GitHub CLI (gh) is required")
    completed = subprocess.run(  # noqa: S603
        [
            executable,
            "repo",
            "view",
            "--json",
            "nameWithOwner",
            "--jq",
            ".nameWithOwner",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AuditTrailError(completed.stderr.strip() or "gh repo view failed")
    return completed.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    """Generate the two audit-trail Markdown files and write them to disk."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=None)
    parser.add_argument("--base", default="main")
    parser.add_argument("--since", default=None)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--rule-path-prefix",
        dest="rule_path_prefixes",
        action="append",
        default=None,
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--pr-audit-file", default=DEFAULT_PR_AUDIT_FILE)
    parser.add_argument("--rule-change-file", default=DEFAULT_RULE_CHANGE_FILE)
    parser.add_argument("--fixture", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.retries < 1:
        parser.error("--retries must be positive")

    rule_prefixes = tuple(
        args.rule_path_prefixes
        if args.rule_path_prefixes
        else DEFAULT_RULE_PREFIXES
    )

    if args.fixture:
        nodes = load_fixture_nodes(args.fixture)
        repo = args.repo or "owner/repo"
    else:
        repo = args.repo or _default_repo()
        nodes = fetch_pull_request_nodes(
            repo, args.base, args.since, args.limit, args.retries
        )

    records = build_records(nodes, args.base)
    generated_at = dt.datetime.now(dt.UTC).isoformat()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    pr_audit_path = args.out_dir / args.pr_audit_file
    rule_change_path = args.out_dir / args.rule_change_file

    pr_audit_path.write_text(
        render_pr_audit_table(records, repo, generated_at), encoding="utf-8"
    )
    rule_change_path.write_text(
        render_rule_change_log(records, rule_prefixes, repo, generated_at),
        encoding="utf-8",
    )

    sys.stderr.write(
        f"Wrote {len(records)} pull request rows to {pr_audit_path} and "
        f"{rule_change_path}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
