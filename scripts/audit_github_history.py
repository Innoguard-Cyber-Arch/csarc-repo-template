#!/usr/bin/env python3
"""Audit bounded GitHub work-item history without persisting raw content."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]
Fetcher = Callable[[str], list[JsonObject]]

GRAPHQL_QUERY = """
query($owner: String!, $name: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      first: 100
      after: $endCursor
      orderBy: {field: CREATED_AT, direction: ASC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        state
        reviewThreads { totalCount }
        closingIssuesReferences { totalCount }
      }
    }
  }
}
""".strip()


class AuditError(RuntimeError):
    """Raised when audit input cannot be retrieved or parsed."""


def _objects(value: object, label: str) -> list[JsonObject]:
    """Flatten gh --slurp pages into validated JSON objects."""
    if not isinstance(value, list):
        raise AuditError(f"{label}: expected a JSON page list")
    objects: list[JsonObject] = []
    for page in value:
        if not isinstance(page, list):
            raise AuditError(f"{label}: expected each page to be a list")
        for item in page:
            if not isinstance(item, dict):
                raise AuditError(f"{label}: expected each item to be an object")
            objects.append(item)
    return objects


def _graphql_objects(value: object) -> list[JsonObject]:
    """Flatten pull-request nodes from paginated GraphQL output."""
    if not isinstance(value, list):
        raise AuditError("graphql: expected a JSON page list")
    nodes: list[JsonObject] = []
    for page in value:
        try:
            current = page["data"]["repository"]["pullRequests"]["nodes"]
        except (KeyError, TypeError) as error:
            raise AuditError("graphql: missing pullRequests nodes") from error
        nodes.extend(_objects([current], "graphql"))
    return nodes


def _run_gh(arguments: list[str], retries: int) -> object:
    """Run one GitHub API request, retrying without writing responses."""
    failure = ""
    for _attempt in range(retries):
        completed = subprocess.run(  # noqa: S603
            ["gh", "api", *arguments],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            try:
                return json.loads(completed.stdout)
            except json.JSONDecodeError as error:
                raise AuditError("gh api returned invalid JSON") from error
        failure = completed.stderr.strip()
    raise AuditError(failure or "gh api failed")


def _count(connection: object) -> int:
    """Read a GraphQL connection totalCount."""
    if not isinstance(connection, dict):
        raise AuditError("graphql: missing connection")
    value = connection.get("totalCount")
    if not isinstance(value, int):
        raise AuditError("graphql: missing totalCount")
    return value


def audit(  # noqa: C901
    repo: str,
    cutoff: str,
    max_number: int,
    fetch: Fetcher,
    graph_nodes: list[JsonObject],
    retries: int,
) -> JsonObject:
    """Return coverage and aggregate counts for one bounded audit."""
    prefix = f"repos/{repo}"
    items = [
        item
        for item in fetch(
            f"{prefix}/issues?state=all&per_page=100&direction=asc"
        )
        if isinstance(item.get("number"), int)
        and item["number"] <= max_number
        and isinstance(item.get("created_at"), str)
        and item["created_at"] <= cutoff
    ]
    issues = [item for item in items if "pull_request" not in item]
    pulls = [item for item in items if "pull_request" in item]
    coverage: dict[str, JsonObject] = {
        "body": {"ok": 0, "expected": len(items)},
        "comments": {"ok": 0, "expected": len(items)},
        "timeline": {"ok": 0, "expected": len(items)},
        "reviews": {"ok": 0, "expected": len(pulls)},
        "commits": {"ok": 0, "expected": len(pulls)},
        "files": {"ok": 0, "expected": len(pulls)},
        "graphql": {"ok": 0, "expected": len(pulls)},
    }
    gaps: list[str] = []
    counts = {
        "issues": len(issues),
        "issues_closed": sum(item.get("state") == "closed" for item in issues),
        "issues_open": sum(item.get("state") == "open" for item in issues),
        "issues_with_comments": 0,
        "pull_requests": len(pulls),
        "pull_requests_closed_unmerged": 0,
        "issue_comments": 0,
        "pull_request_comments": 0,
        "pull_requests_merged": 0,
        "pull_requests_open": 0,
        "timeline_entries": 0,
        "reviews": 0,
        "commits": 0,
        "files": 0,
        "review_threads": 0,
        "pull_requests_with_closing_issues": 0,
    }

    for item in items:
        number = item["number"]
        if "body" in item:
            coverage["body"]["ok"] += 1
        else:
            gaps.append(f"issues/{number}/body")
        for endpoint, key in (
            ("comments", "comments"),
            ("timeline", "timeline"),
        ):
            try:
                entries = fetch(
                    f"{prefix}/issues/{number}/{endpoint}?per_page=100"
                )
            except AuditError:
                gaps.append(f"issues/{number}/{endpoint}")
                continue
            coverage[key]["ok"] += 1
            if endpoint == "comments":
                count_key = (
                    "pull_request_comments"
                    if "pull_request" in item
                    else "issue_comments"
                )
                counts[count_key] += len(entries)
                if count_key == "issue_comments" and entries:
                    counts["issues_with_comments"] += 1
            else:
                counts["timeline_entries"] += len(entries)

    for pull in pulls:
        number = pull["number"]
        for endpoint in ("reviews", "commits", "files"):
            try:
                entries = fetch(
                    f"{prefix}/pulls/{number}/{endpoint}?per_page=100"
                )
            except AuditError:
                gaps.append(f"pulls/{number}/{endpoint}")
                continue
            coverage[endpoint]["ok"] += 1
            counts[endpoint] += len(entries)

    graph_by_number = {
        node["number"]: node
        for node in graph_nodes
        if isinstance(node.get("number"), int)
    }
    for pull in pulls:
        number = pull["number"]
        node = graph_by_number.get(number)
        if node is None:
            gaps.append(f"pulls/{number}/graphql")
            continue
        try:
            counts["review_threads"] += _count(node.get("reviewThreads"))
            closing = _count(node.get("closingIssuesReferences"))
        except AuditError:
            gaps.append(f"pulls/{number}/graphql")
            continue
        coverage["graphql"]["ok"] += 1
        counts["pull_requests_with_closing_issues"] += closing > 0
        state = node.get("state")
        if state == "MERGED":
            counts["pull_requests_merged"] += 1
        elif state == "OPEN":
            counts["pull_requests_open"] += 1
        elif state == "CLOSED":
            counts["pull_requests_closed_unmerged"] += 1
        else:
            gaps.append(f"pulls/{number}/graphql-state")

    return {
        "repository": repo,
        "retrieved_at": dt.datetime.now(dt.UTC).isoformat(),
        "cutoff": cutoff,
        "max_number": max_number,
        "retries_per_request": retries,
        "counts": counts,
        "coverage": coverage,
        "gaps": gaps,
    }


def main(argv: list[str] | None = None) -> int:
    """Run a live or fixture-backed audit and print only its summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--max-number", required=True, type=int)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args(argv)
    if args.retries < 1:
        parser.error("--retries must be positive")

    if args.fixture:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        rest = fixture.get("rest", {})

        def fetch(endpoint: str) -> list[JsonObject]:
            if endpoint not in rest:
                raise AuditError("fixture endpoint missing")
            return _objects(rest[endpoint], endpoint)

        try:
            graph_nodes = _graphql_objects(fixture.get("graphql"))
        except AuditError:
            graph_nodes = []
    else:

        def fetch(endpoint: str) -> list[JsonObject]:
            return _objects(
                _run_gh(["--paginate", "--slurp", endpoint], args.retries),
                endpoint,
            )

        owner, name = args.repo.split("/", 1)
        try:
            graph_nodes = _graphql_objects(
                _run_gh(
                    [
                        "graphql",
                        "--paginate",
                        "--slurp",
                        "-f",
                        f"query={GRAPHQL_QUERY}",
                        "-F",
                        f"owner={owner}",
                        "-F",
                        f"name={name}",
                    ],
                    args.retries,
                )
            )
        except AuditError:
            graph_nodes = []

    result = audit(
        args.repo,
        args.cutoff,
        args.max_number,
        fetch,
        graph_nodes,
        args.retries,
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return int(bool(result["gaps"]))


if __name__ == "__main__":
    sys.exit(main())
