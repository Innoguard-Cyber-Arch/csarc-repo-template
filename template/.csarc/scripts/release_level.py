#!/usr/bin/env python3
"""Resolve per-work release levels and their review/test requirements."""

from __future__ import annotations

import argparse
import importlib
import json
import re
import subprocess
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    csarc_config = importlib.import_module("csarc_config")
    release_phase = importlib.import_module("release_phase")
else:
    csarc_config = importlib.import_module(f"{__package__}.csarc_config")
    release_phase = importlib.import_module(f"{__package__}.release_phase")

LEVELS = ("alpha", "beta", "early", "formal")
LEVEL_RANK = {level: rank for rank, level in enumerate(LEVELS)}
SUITES = ("fast", "full")
SUITE_RANK = {suite: rank for rank, suite in enumerate(SUITES)}
LEGACY_SUITE_ALIASES = {"baseline": "fast", "docs": "fast"}
REVIEWS = ("self", "peer")
COLLABORATOR_PERMISSIONS = {
    "pull",
    "triage",
    "push",
    "maintain",
    "admin",
    "read",
    "write",
}
DECLARATION_HEADING = "Release level / 發布層級"
DEFAULT_REVIEW = {
    "alpha": "self",
    "beta": "peer",
    "early": "peer",
    "formal": "peer",
}
DEFAULT_SUITE = {
    "alpha": "fast",
    "beta": "fast",
    "early": "fast",
    "formal": "full",
}
_CLOSING_ISSUE = re.compile(
    r"(?<!\w)(?:Closes|Fixes|Resolves)[ \t]+#([1-9][0-9]*)(?!\w)",
    re.IGNORECASE,
)
_RELEASE_VERSION = re.compile(
    r"\brelease\s+v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(alpha|beta)\.([1-9]\d*))?\b",
    re.IGNORECASE,
)
_BATCH_MARKER = "release-level-work-items"


class GitHubReader(Protocol):
    """The read-only GitHub API surface used by the resolver."""

    def get(self, repo: str, path: str) -> object:
        """Read one REST resource."""
        ...

    def pages(self, repo: str, path: str) -> list[dict[str, Any]]:
        """Read every page of one REST collection."""
        ...


class GitHubWriter(GitHubReader, Protocol):
    """The narrow authenticated write surface used by release annotations."""

    def write(self, repo: str, method: str, path: str, body: str) -> object:
        """Write one GitHub resource body."""
        ...


@dataclass(frozen=True)
class Settings:
    """Configured defaults and per-level requirements."""

    enabled: bool
    default_level: str
    reviews: dict[str, str]
    suites: dict[str, str]


@dataclass(frozen=True)
class Decision:
    """One resolved work level and the controls it requires."""

    level: str
    review: str
    suite: str
    source: str
    issue: int | None = None


def settings_from_mapping(config: dict[str, object]) -> Settings:
    """Build the fixed verification floor and configured human review mode."""
    enabled = True
    default_level = config.get("default_release_level", "beta")
    if default_level not in LEVELS:
        raise ValueError(
            "default_release_level must be one of " + ", ".join(LEVELS)
        )
    review = config.get("review")
    if review is None:
        legacy = [
            config.get(f"release_level_{level}_review", DEFAULT_REVIEW[level])
            for level in LEVELS
        ]
        review = "peer" if "peer" in legacy else "solo"
    if review not in {"solo", "peer"}:
        raise ValueError("review must be solo or peer")
    resolved_review = "self" if review == "solo" else "peer"
    return Settings(
        enabled,
        str(default_level),
        {level: resolved_review for level in LEVELS},
        dict(DEFAULT_SUITE),
    )


def load_settings(path: Path | None = None) -> Settings:
    """Load the release-level module from the single CSARC config file."""
    config_path = path or csarc_config.CONFIG_FILE
    if not config_path.exists():
        return settings_from_mapping({})
    return settings_from_mapping(csarc_config.load_config(config_path))


def _section(body: str, heading: str) -> str | None:
    match = re.search(
        rf"(?ms)^#{{2,3}} {re.escape(heading)}\s*$\n"
        rf"(.*?)(?=^#{{2,3}} |\Z)",
        body,
    )
    return None if match is None else match.group(1).strip()


def declared_level(body: object) -> str | None:
    """Return the exact Issue-form release-level declaration, if present."""
    if not isinstance(body, str):
        return None
    value = _section(body, DECLARATION_HEADING)
    if value is None or value in {"", "_No response_"}:
        return None
    if value not in LEVELS:
        raise ValueError(
            f"{DECLARATION_HEADING} must be one of {', '.join(LEVELS)}"
        )
    return value


def stronger_suite(first: str, second: str) -> str:
    """Return the stronger of two verification suites."""
    first = LEGACY_SUITE_ALIASES.get(first, first)
    second = LEGACY_SUITE_ALIASES.get(second, second)
    if first not in SUITE_RANK or second not in SUITE_RANK:
        raise ValueError("unknown verification suite")
    return max((first, second), key=SUITE_RANK.__getitem__)


def required_suite(level: str, path_tier: str, settings: Settings) -> str:
    """Combine the work-level floor with the path-selected test tier."""
    if level not in LEVELS:
        raise ValueError(f"unknown release level: {level}")
    if path_tier not in {*SUITES, *LEGACY_SUITE_ALIASES}:
        raise ValueError(f"unknown path verification tier: {path_tier}")
    return stronger_suite(settings.suites[level], path_tier)


def highest_level(levels: list[str]) -> str:
    """Return the highest declared level, failing on an empty batch."""
    if not levels or any(level not in LEVEL_RANK for level in levels):
        raise ValueError("release batch has invalid or missing levels")
    return max(levels, key=LEVEL_RANK.__getitem__)


def _work_item(
    kind: str,
    item: dict[str, Any],
    decision: Decision,
) -> tuple[tuple[str, int], dict[str, object]]:
    """Return one stable release-note row for an Issue or pull request."""
    number = item.get("number")
    title = item.get("title")
    url = item.get("html_url")
    if type(number) is not int or not isinstance(title, str):
        raise RuntimeError(f"GitHub returned invalid {kind} data")
    if not isinstance(url, str):
        url = ""
    row: dict[str, object] = {
        "kind": kind,
        "number": number,
        "title": title,
        "url": url,
        "level": decision.level,
        "source": decision.source,
    }
    return (kind, number), row


def release_batch(
    github: GitHubReader,
    repo: str,
    pulls: list[dict[str, Any]],
    settings: Settings,
) -> dict[str, object]:
    """Resolve and list every work item represented by unreleased pulls."""
    items: dict[tuple[str, int], dict[str, object]] = {}
    for pull in pulls:
        if _release_pull_level(pull) is not None:
            continue
        milestone = pull.get("milestone")
        if isinstance(milestone, dict) and type(milestone.get("number")) is int:
            milestone_number = int(milestone["number"])
            tracker = _tracker_for(github, repo, milestone_number)
            for issue in github.pages(
                repo,
                f"issues?milestone={milestone_number}&state=all&per_page=100",
            ):
                if issue.get("pull_request") is not None or issue.get(
                    "number"
                ) == tracker.get("number"):
                    continue
                decision = resolve_issue(github, repo, issue, settings)
                key, row = _work_item("Issue", issue, decision)
                items[key] = row
            continue
        numbers = sorted(
            {
                int(match.group(1))
                for match in _CLOSING_ISSUE.finditer(
                    str(pull.get("body") or "")
                )
            }
        )
        if len(numbers) == 1:
            issue = github.get(repo, f"issues/{numbers[0]}")
            if (
                not isinstance(issue, dict)
                or issue.get("pull_request") is not None
            ):
                raise RuntimeError(
                    f"Closing reference #{numbers[0]} is not an Issue"
                )
            decision = resolve_issue(github, repo, issue, settings)
            key, row = _work_item("Issue", issue, decision)
        else:
            decision = resolve_pull(github, repo, pull, settings)
            key, row = _work_item("PR", pull, decision)
        items[key] = row

    ordered = [items[key] for key in sorted(items)]
    if not ordered:
        raise RuntimeError("No unreleased work items were found")
    return {
        "level": highest_level([str(item["level"]) for item in ordered]),
        "items": ordered,
    }


def release_batch_markdown(batch: dict[str, object]) -> str:
    """Render release-level evidence for a version PR and Release notes."""
    items = batch.get("items")
    if not isinstance(items, list):
        raise ValueError("release batch has invalid work items")
    lines = [
        f"<!-- {_BATCH_MARKER}:start -->",
        "## Included work and release levels",
        "",
        "| Work | Declared level |",
        "| --- | --- |",
    ]
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("release batch has an invalid work item")
        label = f"{item['kind']} #{item['number']}: {item['title']}"
        url = str(item.get("url") or "")
        if url:
            label = f"[{label}]({url})"
        lines.append(f"| {label} | `{item['level']}` |")
    if not items:
        lines.append(f"| Existing release rerun | `{batch['level']}` |")
    lines.extend(
        [
            "",
            f"Highest included level: `{batch['level']}`.",
            f"<!-- {_BATCH_MARKER}:end -->",
            "",
        ]
    )
    return "\n".join(lines)


def level_allows_copilot(max_level: str, level: str) -> bool:
    """Apply the optional Copilot ceiling to one resolved level."""
    if max_level == "unlimited":
        return True
    normalized = "formal" if max_level == "release" else max_level
    if normalized not in LEVEL_RANK or level not in LEVEL_RANK:
        raise ValueError("invalid Copilot release-level limit")
    return LEVEL_RANK[level] <= LEVEL_RANK[normalized]


def _permission(github: GitHubReader, repo: str, login: object) -> str | None:
    if not isinstance(login, str) or not login:
        return None
    try:
        payload = github.get(
            repo,
            f"collaborators/{urllib.parse.quote(login, safe='')}/permission",
        )
    except RuntimeError:
        return None
    permission = (
        payload.get("permission") if isinstance(payload, dict) else None
    )
    return (
        permission
        if isinstance(permission, str)
        and permission in COLLABORATOR_PERMISSIONS
        else None
    )


def _trusted_declaration(
    github: GitHubReader,
    repo: str,
    issue: dict[str, Any],
) -> str | None:
    """Trust a declaration only when the Issue creator is a collaborator."""
    user = issue.get("user")
    login = user.get("login") if isinstance(user, dict) else None
    if _permission(github, repo, login) is None:
        return None
    return declared_level(issue.get("body"))


def _tracker_for(
    github: GitHubReader, repo: str, milestone_number: int
) -> dict[str, Any]:
    milestone = github.get(repo, f"milestones/{milestone_number}")
    if not isinstance(milestone, dict) or not isinstance(
        milestone.get("title"), str
    ):
        raise RuntimeError("GitHub returned invalid Milestone data")
    title = f"Milestone {milestone_number}: {milestone['title']}"
    candidates = [
        item
        for item in github.pages(
            repo, f"issues?milestone={milestone_number}&state=all&per_page=100"
        )
        if item.get("title") == title and "pull_request" not in item
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"Milestone {milestone_number} needs one tracker")
    return candidates[0]


def resolve_issue(
    github: GitHubReader,
    repo: str,
    issue: dict[str, Any],
    settings: Settings,
) -> Decision:
    """Resolve one Issue, including Milestone inheritance and trust."""
    number = issue.get("number")
    if type(number) is not int or number < 1:
        raise RuntimeError("GitHub returned invalid Issue data")
    if not settings.enabled:
        level = settings.default_level
        return Decision(
            level,
            settings.reviews[level],
            settings.suites[level],
            "configured default (release-level declarations disabled)",
            number,
        )

    own_level = _trusted_declaration(github, repo, issue)
    milestone = issue.get("milestone")
    if isinstance(milestone, dict) and type(milestone.get("number")) is int:
        tracker = _tracker_for(github, repo, int(milestone["number"]))
        tracker_level = _trusted_declaration(github, repo, tracker)
        level = tracker_level or settings.default_level
        if (
            own_level is not None
            and issue.get("number") != tracker.get("number")
            and own_level != level
        ):
            raise RuntimeError(
                f"Issue #{number} declares {own_level}, but Milestone "
                f"{milestone['number']} requires {level} from its tracker"
            )
        source = (
            f"Milestone {milestone['number']} tracker"
            if tracker_level is not None
            else "configured default (tracker has no trusted declaration)"
        )
    else:
        level = own_level or settings.default_level
        source = (
            f"Issue #{number}"
            if own_level is not None
            else "configured default (Issue has no trusted declaration)"
        )
    return Decision(
        level,
        settings.reviews[level],
        settings.suites[level],
        source,
        number,
    )


def _release_pull_level(pull: dict[str, Any]) -> str | None:
    head = pull.get("head")
    head_ref = head.get("ref") if isinstance(head, dict) else None
    if not isinstance(head_ref, str) or not head_ref.startswith(
        ("release-please--", "release/v")
    ):
        return None
    match = _RELEASE_VERSION.search(str(pull.get("title") or ""))
    if match is None:
        raise RuntimeError("Release pull request title has no release version")
    version = ".".join(match.group(index) for index in (1, 2, 3))
    if match.group(4):
        version += f"-{match.group(4).lower()}.{match.group(5)}"
    return release_phase.parse_version(version).release_kind


def resolve_pull(
    github: GitHubReader,
    repo: str,
    pull: dict[str, Any],
    settings: Settings,
) -> Decision:
    """Resolve one pull request to its trusted release level."""
    author = pull.get("user")
    login = str(author.get("login") or "") if isinstance(author, dict) else ""
    head = pull.get("head")
    head_ref = str(head.get("ref") or "") if isinstance(head, dict) else ""
    head_repo = head.get("repo") if isinstance(head, dict) else None
    head_repo_name = (
        head_repo.get("full_name") if isinstance(head_repo, dict) else None
    )
    if (
        login.casefold() == "dependabot[bot]"
        and head_ref.startswith("dependabot/")
        and isinstance(head_repo_name, str)
        and head_repo_name.casefold() == repo.casefold()
    ):
        level = "beta"
        return Decision(
            level,
            settings.reviews[level],
            settings.suites[level],
            "allowlisted dependency bot",
        )
    release_level = _release_pull_level(pull)
    if release_level is not None:
        return Decision(
            release_level,
            settings.reviews[release_level],
            settings.suites[release_level],
            "release pull request version",
        )
    numbers = sorted(
        {
            int(match.group(1))
            for match in _CLOSING_ISSUE.finditer(str(pull.get("body") or ""))
        }
    )
    if len(numbers) > 1:
        raise RuntimeError("Pull request closes more than one Issue")
    if not numbers:
        milestone = pull.get("milestone")
        if isinstance(milestone, dict) and type(milestone.get("number")) is int:
            tracker = _tracker_for(github, repo, int(milestone["number"]))
            return resolve_issue(github, repo, tracker, settings)
        level = settings.default_level
        return Decision(
            level,
            settings.reviews[level],
            settings.suites[level],
            "configured default (pull request has no declared Issue)",
        )
    issue = github.get(repo, f"issues/{numbers[0]}")
    if not isinstance(issue, dict) or issue.get("pull_request") is not None:
        raise RuntimeError(f"Closing reference #{numbers[0]} is not an Issue")
    return resolve_issue(github, repo, issue, settings)


def resolve_pr(
    github: GitHubReader,
    repo: str,
    pr_number: int,
    settings: Settings,
) -> Decision:
    """Load and resolve one pull request."""
    pull = github.get(repo, f"pulls/{pr_number}")
    if not isinstance(pull, dict):
        raise RuntimeError("GitHub returned invalid pull-request data")
    return resolve_pull(github, repo, pull, settings)


class GitHubCLI:
    """Small read-only adapter around the authenticated GitHub CLI."""

    @staticmethod
    def _run(arguments: list[str]) -> object:
        result = subprocess.run(  # noqa: S603
            ["gh", "api", *arguments],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return json.loads(result.stdout)

    def get(self, repo: str, path: str) -> object:
        """Read one GitHub REST resource."""
        endpoint = f"repos/{repo}" + (f"/{path}" if path else "")
        return self._run([endpoint])

    def pages(self, repo: str, path: str) -> list[dict[str, Any]]:
        """Read and flatten a paginated GitHub REST collection."""
        payload = self._run(["--paginate", "--slurp", f"repos/{repo}/{path}"])
        if not isinstance(payload, list):
            raise RuntimeError("GitHub returned an invalid collection")
        pages = (
            payload if payload and isinstance(payload[0], list) else [payload]
        )
        items = [item for page in pages for item in page]
        if not all(isinstance(item, dict) for item in items):
            raise RuntimeError("GitHub returned an invalid collection item")
        return items

    def write(self, repo: str, method: str, path: str, body: str) -> object:
        """Write one JSON body through the authenticated GitHub CLI."""
        endpoint = f"repos/{repo}/{path}"
        result = subprocess.run(  # noqa: S603
            ["gh", "api", "--method", method, endpoint, "--input", "-"],  # noqa: S607
            input=json.dumps({"body": body}),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return json.loads(result.stdout)


def _git_lines(root: Path, arguments: list[str]) -> list[str]:
    result = subprocess.run(  # noqa: S603
        ["git", *arguments],  # noqa: S607
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return [line for line in result.stdout.splitlines() if line]


def unreleased_pulls(
    github: GitHubReader,
    repo: str,
    root: Path,
    sha: str,
) -> list[dict[str, Any]]:
    """Return unique merged pull requests since the prior release tag."""
    valid_tags = [
        tag
        for tag in _git_lines(root, ["tag", "--merged", sha])
        if release_phase.is_valid_version(tag)
    ]
    ordered_tags = release_phase.sort_by_precedence(valid_tags)
    latest = ordered_tags[-1] if ordered_tags else ""
    revision = f"{latest}..{sha}" if latest else sha
    pulls: dict[int, dict[str, Any]] = {}
    for commit in _git_lines(root, ["rev-list", "--reverse", revision]):
        payload = github.get(repo, f"commits/{commit}/pulls")
        if not isinstance(payload, list):
            raise RuntimeError("GitHub returned invalid commit pull requests")
        for pull in payload:
            if (
                not isinstance(pull, dict)
                or type(pull.get("number")) is not int
                or pull.get("merged_at") is None
                or pull.get("merge_commit_sha") != commit
            ):
                continue
            base = pull.get("base")
            if not isinstance(base, dict) or base.get("ref") != "main":
                continue
            pulls[int(pull["number"])] = pull
    return list(pulls.values())


def release_batch_from_git(
    github: GitHubReader,
    repo: str,
    root: Path,
    sha: str,
    settings: Settings,
) -> dict[str, object]:
    """Resolve the unreleased batch represented by one main commit."""
    pulls = unreleased_pulls(github, repo, root, sha)
    if pulls:
        return release_batch(github, repo, pulls, settings)
    pointed = [
        tag
        for tag in _git_lines(root, ["tag", "--points-at", sha])
        if release_phase.is_valid_version(tag)
    ]
    if not pointed:
        return {"level": settings.default_level, "items": []}
    if len(pointed) != 1:
        raise RuntimeError("Release commit points at multiple version tags")
    level = release_phase.parse_version(pointed[0]).release_kind
    return {"level": level, "items": []}


def annotate_pull_request(
    github: GitHubWriter,
    repo: str,
    pr_number: int,
    actor: str,
    body: str,
) -> str:
    """Create or update this actor's one release-level evidence comment."""
    matches = [
        comment
        for comment in github.pages(
            repo, f"issues/{pr_number}/comments?per_page=100"
        )
        if f"<!-- {_BATCH_MARKER}:start -->" in str(comment.get("body") or "")
        and str((comment.get("user") or {}).get("login") or "").casefold()
        == actor.casefold()
    ]
    if len(matches) > 1:
        raise RuntimeError("Release pull request has duplicate level notes")
    if matches:
        comment_id = matches[0].get("id")
        if type(comment_id) is not int:
            raise RuntimeError("Release-level comment has no numeric ID")
        payload = github.write(
            repo, "PATCH", f"issues/comments/{comment_id}", body
        )
    else:
        payload = github.write(
            repo, "POST", f"issues/{pr_number}/comments", body
        )
    if not isinstance(payload, dict) or not isinstance(
        payload.get("html_url"), str
    ):
        raise RuntimeError("Release-level comment response is invalid")
    return str(payload["html_url"])


def annotate_release(
    github: GitHubWriter,
    repo: str,
    tag: str,
    details: str,
) -> None:
    """Append deterministic work-level evidence to one mutable draft Release."""
    encoded_tag = urllib.parse.quote(tag, safe="")
    payload = github.get(repo, f"releases/tags/{encoded_tag}")
    if (
        not isinstance(payload, dict)
        or payload.get("draft") is not True
        or payload.get("immutable") is True
        or type(payload.get("id")) is not int
    ):
        raise RuntimeError(
            "Release-level notes require one mutable draft Release"
        )
    body = str(payload.get("body") or "")
    pattern = re.compile(
        rf"(?ms)^<!-- {re.escape(_BATCH_MARKER)}:start -->.*?"
        rf"^<!-- {re.escape(_BATCH_MARKER)}:end -->\s*"
    )
    cleaned = pattern.sub("", body).rstrip()
    updated = f"{cleaned}\n\n{details}" if cleaned else details
    github.write(repo, "PATCH", f"releases/{payload['id']}", updated)


def _write_outputs(
    decision: Decision,
    path_tier: str | None,
    settings: Settings,
    github_output: Path | None,
) -> dict[str, object]:
    payload = asdict(decision)
    if path_tier is not None:
        payload["suite"] = required_suite(decision.level, path_tier, settings)
    if github_output is not None:
        with github_output.open("a", encoding="utf-8") as handle:
            for key in ("level", "review", "suite", "source"):
                handle.write(f"{key}={payload[key]}\n")
    return payload


def _write_batch_outputs(
    batch: dict[str, object],
    markdown_output: Path | None,
    github_output: Path | None,
) -> None:
    details = release_batch_markdown(batch)
    if markdown_output is not None:
        markdown_output.write_text(details, encoding="utf-8")
    if github_output is not None:
        with github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"level={batch['level']}\n")
            handle.write("details<<CSARC_RELEASE_LEVELS_EOF\n")
            handle.write(details)
            handle.write("CSARC_RELEASE_LEVELS_EOF\n")


def main(argv: list[str] | None = None) -> int:
    """Resolve a work item for local tools and GitHub Actions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    issue_parser = subparsers.add_parser("resolve-issue")
    issue_parser.add_argument("--repo", required=True)
    issue_parser.add_argument("--issue", required=True, type=int)
    issue_parser.add_argument("--github-output", type=Path)
    pr_parser = subparsers.add_parser("resolve-pr")
    pr_parser.add_argument("--repo", required=True)
    pr_parser.add_argument("--pr", required=True, type=int)
    pr_parser.add_argument("--path-tier", choices=("docs", "fast", "full"))
    pr_parser.add_argument("--github-output", type=Path)
    batch_parser = subparsers.add_parser("release-batch")
    batch_parser.add_argument("--repo", required=True)
    batch_parser.add_argument("--sha", default="HEAD")
    batch_parser.add_argument("--root", type=Path, default=Path.cwd())
    batch_parser.add_argument("--markdown-output", type=Path)
    batch_parser.add_argument("--github-output", type=Path)
    annotate_pr = subparsers.add_parser("annotate-pr")
    annotate_pr.add_argument("--repo", required=True)
    annotate_pr.add_argument("--pr", required=True, type=int)
    annotate_pr.add_argument("--actor", required=True)
    annotate_pr.add_argument("--body-file", required=True, type=Path)
    annotate_release_parser = subparsers.add_parser("annotate-release")
    annotate_release_parser.add_argument("--repo", required=True)
    annotate_release_parser.add_argument("--tag", required=True)
    annotate_release_parser.add_argument(
        "--body-file", required=True, type=Path
    )
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    github = GitHubCLI()
    try:
        if args.command == "release-batch":
            batch = release_batch_from_git(
                github,
                args.repo,
                args.root.resolve(),
                args.sha,
                settings,
            )
            _write_batch_outputs(
                batch, args.markdown_output, args.github_output
            )
            sys.stdout.write(json.dumps(batch, sort_keys=True) + "\n")
            return 0
        if args.command == "annotate-pr":
            url = annotate_pull_request(
                github,
                args.repo,
                args.pr,
                args.actor,
                args.body_file.read_text(encoding="utf-8"),
            )
            sys.stdout.write(url + "\n")
            return 0
        if args.command == "annotate-release":
            annotate_release(
                github,
                args.repo,
                args.tag,
                args.body_file.read_text(encoding="utf-8"),
            )
            return 0
        if args.command == "resolve-issue":
            issue = github.get(args.repo, f"issues/{args.issue}")
            if not isinstance(issue, dict):
                raise RuntimeError("GitHub returned invalid Issue data")
            decision = resolve_issue(github, args.repo, issue, settings)
            path_tier = None
        else:
            decision = resolve_pr(github, args.repo, args.pr, settings)
            path_tier = args.path_tier
        payload = _write_outputs(
            decision, path_tier, settings, args.github_output
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        sys.stderr.write(f"release-level resolution failed closed: {error}\n")
        return 1
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
