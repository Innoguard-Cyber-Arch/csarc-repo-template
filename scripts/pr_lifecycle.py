#!/usr/bin/env python3
"""Serialize pull-request lifecycle writes across local tasks."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

LEASE_SCHEMA = 1
MAX_TTL_SECONDS = 7200
MIN_OPERATION_SECONDS = 30
MAINTAINER_ASSOCIATIONS = {"MEMBER", "OWNER"}
SHA = re.compile(r"[0-9a-f]{40}")
OWNER = re.compile(r"[A-Za-z0-9._/@:-]{1,200}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
UNCHECKED = re.compile(r"(?m)^\s*-\s+\[\s*\]")
CLOSING_ISSUE = re.compile(r"(?:Closes|Fixes|Resolves)\s+#(\d+)(?:\D|$)", re.I)
BLOCKER = re.compile(r"(?i)^(?:blocked|blocker)\s*:|^\[merge-blocker\]")
BLOCKER_RESOLVED = re.compile(
    r"(?i)^merge blocker resolved\s*:|^\[merge-blocker-resolved\]"
)
DRAFT_EVENTS = {"convert_to_draft", "converted_to_draft"}


def canonical_json(value: object) -> str:
    """Return stable compact JSON for comments and commit messages."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def parse_time(value: object, label: str) -> datetime:
    """Parse an aware GitHub timestamp or fail closed."""
    if not isinstance(value, str):
        raise RuntimeError(f"{label} has no timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError(f"{label} has an invalid timestamp") from error
    if parsed.tzinfo is None:
        raise RuntimeError(f"{label} timestamp has no timezone")
    return parsed.astimezone(UTC)


def run(
    command: list[str],
    *,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Run one local command and return stdout."""
    result = subprocess.run(  # noqa: S603
        command,
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed: {' '.join(command)}: {detail}")
    return result.stdout.strip()


class GitHub:
    """Small GitHub CLI adapter that never handles a token directly."""

    def get(self, repo: str, path: str) -> object:
        """Read one REST resource."""
        return json.loads(run(["gh", "api", f"repos/{repo}/{path}"]))

    def viewer(self) -> str:
        """Return the authenticated GitHub actor."""
        payload = json.loads(run(["gh", "api", "user"]))
        login = payload.get("login") if isinstance(payload, dict) else None
        if not isinstance(login, str) or not login:
            raise RuntimeError("Authenticated GitHub actor is unavailable")
        return login

    def pages(self, repo: str, path: str) -> list[dict[str, Any]]:
        """Read and flatten every page of a REST collection."""
        payload = json.loads(
            run(
                [
                    "gh",
                    "api",
                    "--paginate",
                    "--slurp",
                    "-H",
                    "Accept: application/vnd.github+json",
                    f"repos/{repo}/{path}",
                ]
            )
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"GitHub collection {path} is not a list")
        pages = (
            payload if payload and isinstance(payload[0], list) else [payload]
        )
        items = [item for page in pages for item in page]
        if not all(isinstance(item, dict) for item in items):
            raise RuntimeError(f"GitHub collection {path} has invalid entries")
        return items

    def comment(self, repo: str, pr_number: int, body: str) -> dict[str, Any]:
        """Create one audit comment."""
        payload = run(
            [
                "gh",
                "api",
                "--method",
                "POST",
                f"repos/{repo}/issues/{pr_number}/comments",
                "--input",
                "-",
            ],
            input_text=json.dumps({"body": body}),
        )
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise RuntimeError("GitHub comment response is invalid")
        return result


def remote_repository(url: str) -> str:
    """Resolve an origin URL to its GitHub owner/name identity."""
    patterns = (
        r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?$",
        r"ssh://git@github\.com/([^/]+/[^/]+?)(?:\.git)?$",
        r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, url)
        if match:
            return match.group(1)
    raise RuntimeError("origin must be the requested github.com repository")


def require_origin(repo: str) -> None:
    """Require local origin to be the requested GitHub repository."""
    origin = remote_repository(run(["git", "remote", "get-url", "origin"]))
    if origin.casefold() != repo.casefold():
        raise RuntimeError("origin does not match the requested repository")


def pr_ref(pr_number: int) -> str:
    """Return the repository-wide lock ref for one pull request."""
    return f"refs/heads/csarc/leases/pr-{pr_number}"


def lease_refs(pull: dict[str, Any], default_branch: str) -> list[str]:
    """Lock the PR and the shared promotion lane when it targets default."""
    refs = [pr_ref(int(pull["number"]))]
    base = pull.get("base") or {}
    if base.get("ref") == default_branch:
        refs.append("refs/heads/csarc/leases/promotion")
    return refs


def live_pull(
    github: GitHub, repo: str, pr_number: int, head_sha: str
) -> dict[str, Any]:
    """Require one open pull request at the exact expected head."""
    payload = github.get(repo, f"pulls/{pr_number}")
    if not isinstance(payload, dict):
        raise RuntimeError("Live pull request response is invalid")
    head = payload.get("head") or {}
    if (
        payload.get("number") != pr_number
        or payload.get("state") != "open"
        or payload.get("merged") is not False
        or head.get("sha") != head_sha
    ):
        raise RuntimeError("Live pull request state or head has drifted")
    return payload


def remote_ref(ref: str) -> str | None:
    """Return the exact origin ref SHA, rejecting ambiguous output."""
    output = run(["git", "ls-remote", "--refs", "origin", ref])
    if not output:
        return None
    lines = output.splitlines()
    if len(lines) != 1:
        raise RuntimeError(f"Remote lease ref is ambiguous: {ref}")
    try:
        sha, observed_ref = lines[0].split("\t", 1)
    except ValueError as error:
        raise RuntimeError(f"Remote lease ref is invalid: {ref}") from error
    if observed_ref != ref or SHA.fullmatch(sha) is None:
        raise RuntimeError(f"Remote lease ref is invalid: {ref}")
    return sha


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Atomically write evidence without following an output symlink."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise RuntimeError(f"Output must be a regular file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}."
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_lease(path: Path) -> dict[str, Any]:
    """Load structurally valid lease evidence."""
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Lease evidence must be a regular file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != LEASE_SCHEMA
    ):
        raise RuntimeError("Lease evidence schema is invalid")
    required = {
        "repository": str,
        "pull_request": int,
        "head_sha": str,
        "owner": str,
        "actor": str,
        "acquired_at": str,
        "expires_at": str,
        "lease_commit": str,
        "refs": list,
    }
    if any(
        not isinstance(payload.get(key), kind) for key, kind in required.items()
    ):
        raise RuntimeError("Lease evidence is incomplete")
    if (
        SHA.fullmatch(payload["head_sha"]) is None
        or SHA.fullmatch(payload["lease_commit"]) is None
    ):
        raise RuntimeError("Lease evidence has an invalid SHA")
    if (
        REPOSITORY.fullmatch(payload["repository"]) is None
        or OWNER.fullmatch(payload["owner"]) is None
        or not payload["actor"]
        or payload["pull_request"] < 1
    ):
        raise RuntimeError("Lease evidence has invalid identity fields")
    validate_refs(payload)
    return payload


def validate_refs(lease: dict[str, Any]) -> None:
    """Limit evidence to the PR ref and optional promotion-lane ref."""
    refs = lease.get("refs")
    required = pr_ref(int(lease["pull_request"]))
    allowed = {required, "refs/heads/csarc/leases/promotion"}
    if (
        not isinstance(refs, list)
        or len(refs) not in {1, 2}
        or not all(isinstance(ref, str) for ref in refs)
        or len(set(refs)) != len(refs)
        or refs[0] != required
        or any(ref not in allowed for ref in refs)
    ):
        raise RuntimeError("Lease refs are invalid")


def require_lease(
    lease: dict[str, Any], repo: str, pr_number: int, head_sha: str
) -> None:
    """Revalidate an unexpired lease against every remote ref."""
    require_origin(repo)
    if (
        lease["repository"].casefold() != repo.casefold()
        or lease["pull_request"] != pr_number
        or lease["head_sha"] != head_sha
    ):
        raise RuntimeError("Lease does not match the requested pull request")
    validate_refs(lease)
    if parse_time(lease["expires_at"], "Lease") <= datetime.now(
        UTC
    ) + timedelta(seconds=MIN_OPERATION_SECONDS):
        raise RuntimeError(
            "Lease expired; fail closed and inspect it before release"
        )
    refs = lease["refs"]
    if not refs or not all(isinstance(ref, str) for ref in refs):
        raise RuntimeError("Lease refs are invalid")
    for ref in refs:
        if remote_ref(ref) != lease["lease_commit"]:
            raise RuntimeError(f"Lease ownership changed or is missing: {ref}")


def require_caller(lease: dict[str, Any], owner: str, github: GitHub) -> None:
    """Require the task owner and actor that acquired the lease."""
    if lease["owner"] != owner:
        raise RuntimeError("Task owner does not hold this lifecycle lease")
    if str(lease["actor"]).casefold() != github.viewer().casefold():
        raise RuntimeError(
            "Authenticated GitHub actor changed after lease acquisition"
        )


def release_refs(lease: dict[str, Any]) -> None:
    """Delete only refs that still point at this exact lease commit."""
    validate_refs(lease)
    commit = lease["lease_commit"]
    refs = lease["refs"]
    command = ["git", "push", "--atomic", "--porcelain"]
    command.extend(f"--force-with-lease={ref}:{commit}" for ref in refs)
    command.append("origin")
    command.extend(f":{ref}" for ref in refs)
    run(command)


def acquire(args: argparse.Namespace, github: GitHub) -> None:
    """Atomically acquire the PR and optional promotion-lane refs."""
    if SHA.fullmatch(args.head_sha) is None:
        raise RuntimeError(
            "Head SHA must be 40 lowercase hexadecimal characters"
        )
    if OWNER.fullmatch(args.owner) is None:
        raise RuntimeError("Owner must be a stable task or human identifier")
    if not 60 <= args.ttl_seconds <= MAX_TTL_SECONDS:
        raise RuntimeError(
            f"Lease TTL must be between 60 and {MAX_TTL_SECONDS} seconds"
        )
    require_origin(args.repo)
    pull = live_pull(github, args.repo, args.pr_number, args.head_sha)
    repository = github.get(args.repo, "")
    if not isinstance(repository, dict) or not isinstance(
        repository.get("default_branch"), str
    ):
        raise RuntimeError("Repository default branch is unavailable")
    refs = lease_refs(pull, repository["default_branch"])
    if any(remote_ref(ref) is not None for ref in refs):
        raise RuntimeError("Another owner already holds the PR lifecycle lease")

    acquired = datetime.now(UTC).replace(microsecond=0)
    core: dict[str, object] = {
        "schema_version": LEASE_SCHEMA,
        "repository": args.repo,
        "pull_request": args.pr_number,
        "head_sha": args.head_sha,
        "owner": args.owner,
        "actor": github.viewer(),
        "acquired_at": acquired.isoformat().replace("+00:00", "Z"),
        "expires_at": (acquired + timedelta(seconds=args.ttl_seconds))
        .isoformat()
        .replace("+00:00", "Z"),
        "refs": refs,
    }
    tree = run(["git", "rev-parse", f"{args.head_sha}^{{tree}}"])
    commit_env = os.environ.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "CSARC PR lifecycle lease",
            "GIT_AUTHOR_EMAIL": "pr-lifecycle@invalid.example",
            "GIT_COMMITTER_NAME": "CSARC PR lifecycle lease",
            "GIT_COMMITTER_EMAIL": "pr-lifecycle@invalid.example",
        }
    )
    commit = run(
        ["git", "commit-tree", tree, "-p", args.head_sha],
        input_text=(
            f"chore: lease PR #{args.pr_number}\n\n{canonical_json(core)}\n"
        ),
        env=commit_env,
    )
    if SHA.fullmatch(commit) is None:
        raise RuntimeError("Git did not create a valid lease commit")
    push = ["git", "push", "--atomic", "--porcelain", "origin"]
    push.extend(f"{commit}:{ref}" for ref in refs)
    run(push)
    evidence = {**core, "lease_commit": commit}
    try:
        comment = github.comment(
            args.repo,
            args.pr_number,
            "PR lifecycle lease acquired\n\n"
            f"`{canonical_json(evidence)}`\n\n"
            "All automated Ready, Draft, authorization, and merge writes for "
            "this PR are serialized by the refs above.",
        )
        audit_url = comment.get("html_url")
        if not isinstance(audit_url, str):
            raise RuntimeError("Lease audit comment has no URL")
        evidence["audit_url"] = audit_url
        write_json(args.output, evidence)
    except Exception:
        release_refs(evidence)
        raise


def authorization(
    github: GitHub, repo: str, pr_number: int, head_sha: str, url: str
) -> dict[str, Any]:
    """Require a maintainer authorization bound to the exact PR head."""
    parsed = urllib.parse.urlparse(url)
    expected_path = f"/{repo}/pull/{pr_number}"
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() != "github.com"
        or parsed.path.casefold() != expected_path.casefold()
        or re.fullmatch(r"issuecomment-(\d+)", parsed.fragment) is None
    ):
        raise RuntimeError(
            "Authorization URL must be a comment on this pull request"
        )
    comment_id = parsed.fragment.removeprefix("issuecomment-")
    payload = github.get(repo, f"issues/comments/{comment_id}")
    if not isinstance(payload, dict):
        raise RuntimeError("Authorization comment response is invalid")
    body = payload.get("body")
    user = payload.get("user") or {}
    first_line = body.splitlines()[0] if isinstance(body, str) and body else ""
    if (
        payload.get("html_url") != url
        or not str(payload.get("issue_url", "")).endswith(
            f"/issues/{pr_number}"
        )
        or payload.get("author_association") not in MAINTAINER_ASSOCIATIONS
        or not isinstance(user.get("login"), str)
        or not isinstance(body, str)
        or "authorization" not in first_line.casefold()
    ):
        raise RuntimeError("Authorization is not an exact maintainer statement")
    bindings: list[dict[str, Any]] = []
    for candidate in re.findall(r"`([^`\n]+)`", body):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            bindings.append(value)
    matching = [
        item
        for item in bindings
        if str(item.get("repository", "")).casefold() == repo.casefold()
        and item.get("pull_request") == pr_number
        and item.get("head_sha") == head_sha
    ]
    if len(matching) != 1:
        raise RuntimeError(
            "Authorization is not bound to the exact repository, PR, and head"
        )
    parse_time(payload.get("created_at"), "Authorization")
    return payload


def unresolved_blocker(comments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the latest unresolved merge-blocker marker."""
    latest_blocker: tuple[datetime, dict[str, Any]] | None = None
    latest_resolution: datetime | None = None
    for comment in comments:
        created = parse_time(comment.get("created_at"), "Comment")
        body = str(comment.get("body") or "").lstrip()
        if comment.get("author_association") not in MAINTAINER_ASSOCIATIONS:
            continue
        if BLOCKER_RESOLVED.search(body) and (
            latest_resolution is None or created > latest_resolution
        ):
            latest_resolution = created
        elif BLOCKER.search(body) and (
            latest_blocker is None or created >= latest_blocker[0]
        ):
            latest_blocker = (created, comment)
    if latest_blocker is None:
        return None
    if latest_resolution is not None and latest_resolution > latest_blocker[0]:
        return None
    return latest_blocker[1]


def current_reviews(reviews: list[dict[str, Any]]) -> dict[str, str]:
    """Return each reviewer's current decisive state."""
    current: dict[str, str] = {}
    ordered = sorted(
        reviews,
        key=lambda item: (
            parse_time(item.get("submitted_at"), "Review")
            if item.get("submitted_at")
            else datetime.min.replace(tzinfo=UTC)
        ),
    )
    for review in ordered:
        user = review.get("user") or {}
        login = user.get("login")
        if not isinstance(login, str) or not review.get("submitted_at"):
            continue
        reviewer = login.casefold()
        state = str(review.get("state") or "")
        if state in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            current[reviewer] = state
    return current


def effective_protection(
    github: GitHub, repo: str, branch: str
) -> tuple[str, str]:
    """Prove review, last-push, thread, checks, and no-bypass enforcement."""
    try:
        rules = github.get(
            repo, f"rules/branches/{urllib.parse.quote(branch, safe='')}"
        )
    except RuntimeError as error:
        return "unknown", str(error)
    if not isinstance(rules, list):
        return "unknown", "effective branch rules are unavailable"
    pull_rules = [item for item in rules if item.get("type") == "pull_request"]
    check_rules = [
        item for item in rules if item.get("type") == "required_status_checks"
    ]
    pull = [item.get("parameters") or {} for item in pull_rules]
    checks = [item.get("parameters") or {} for item in check_rules]
    protected = (
        any(
            item.get("required_approving_review_count", 0) >= 1 for item in pull
        )
        and any(
            item.get("dismiss_stale_reviews_on_push") is True for item in pull
        )
        and any(item.get("require_code_owner_review") is True for item in pull)
        and any(item.get("require_last_push_approval") is True for item in pull)
        and any(
            item.get("required_review_thread_resolution") is True
            for item in pull
        )
        and any(item.get("required_status_checks") for item in checks)
    )
    if not protected:
        return (
            "blocked",
            "required approval, stale-review dismissal, CODEOWNER, last-push, "
            "thread, or check rules are missing",
        )
    ruleset_ids = {
        item.get("ruleset_id")
        for item in pull_rules + check_rules
        if item.get("ruleset_id")
    }
    if not ruleset_ids:
        return "unknown", "effective rules do not expose their Ruleset identity"
    for ruleset_id in ruleset_ids:
        try:
            ruleset = github.get(repo, f"rulesets/{ruleset_id}")
        except RuntimeError as error:
            return "unknown", str(error)
        if (
            not isinstance(ruleset, dict)
            or ruleset.get("enforcement") != "active"
            or ruleset.get("bypass_actors") != []
        ):
            return (
                "blocked",
                "an effective Ruleset is inactive or permits bypass",
            )
    return "enforced", "server-side merge controls are active without bypass"


def merge_snapshot(  # noqa: C901
    github: GitHub,
    lease: dict[str, Any],
    authorization_url: str,
) -> dict[str, object]:
    """Re-read every mutable merge input while the lease is held."""
    repo = lease["repository"]
    pr_number = lease["pull_request"]
    head_sha = lease["head_sha"]
    require_lease(lease, repo, pr_number, head_sha)
    pull = live_pull(github, repo, pr_number, head_sha)
    if pull.get("draft") is not False:
        raise RuntimeError("Pull request is Draft at merge time")
    if UNCHECKED.search(str(pull.get("body") or "")):
        raise RuntimeError("Pull request has an unchecked checklist item")
    auth = authorization(github, repo, pr_number, head_sha, authorization_url)
    acquired_at = parse_time(lease["acquired_at"], "Lease")
    authorized_at = parse_time(auth.get("created_at"), "Authorization")
    if authorized_at < acquired_at:
        raise RuntimeError("Authorization predates the active lifecycle lease")

    timeline = github.pages(repo, f"issues/{pr_number}/timeline?per_page=100")
    if any(
        item.get("event") in DRAFT_EVENTS
        and parse_time(item.get("created_at"), "Draft event") >= authorized_at
        for item in timeline
    ):
        raise RuntimeError(
            "A newer Draft event invalidated merge authorization"
        )
    comments = github.pages(repo, f"issues/{pr_number}/comments?per_page=100")
    blocker = unresolved_blocker(comments)
    if blocker is not None:
        raise RuntimeError(
            "An unresolved blocking comment prevents merge: "
            + str(blocker.get("html_url") or "unknown URL")
        )
    reviews = github.pages(repo, f"pulls/{pr_number}/reviews?per_page=100")
    review_states = current_reviews(reviews)
    blockers = sorted(
        login
        for login, state in review_states.items()
        if state == "CHANGES_REQUESTED"
    )
    if blockers:
        raise RuntimeError(
            "Changes are still requested by: " + ", ".join(blockers)
        )
    actor = github.viewer().casefold()
    approvers = sorted(
        login
        for login, state in review_states.items()
        if state == "APPROVED" and login != actor
    )
    if not approvers:
        raise RuntimeError("An independent approving review is required")
    if actor != str(lease["actor"]).casefold():
        raise RuntimeError(
            "Authenticated GitHub actor changed after lease acquisition"
        )
    for issue_number in sorted(
        {
            int(value)
            for value in CLOSING_ISSUE.findall(str(pull.get("body") or ""))
        }
    ):
        issue = github.get(repo, f"issues/{issue_number}")
        if not isinstance(issue, dict) or issue.get("pull_request") is not None:
            raise RuntimeError(
                f"Closing reference #{issue_number} is not an Issue"
            )
        if UNCHECKED.search(str(issue.get("body") or "")):
            raise RuntimeError(
                f"Issue #{issue_number} has an unchecked checklist item"
            )

    base = pull.get("base") or {}
    base_ref = base.get("ref")
    if not isinstance(base_ref, str):
        raise RuntimeError("Pull request base branch is unavailable")
    protection, reason = effective_protection(github, repo, base_ref)
    authorization_actor = str((auth.get("user") or {}).get("login", ""))
    independently_authorized = authorization_actor.casefold() != actor
    if protection == "enforced" and not independently_authorized:
        protection = "blocked"
        reason = "merge authorization uses the executing GitHub actor"
    require_lease(lease, repo, pr_number, head_sha)
    return {
        "repository": repo,
        "pull_request": pr_number,
        "head_sha": head_sha,
        "authorization_url": authorization_url,
        "authorization_created_at": auth["created_at"],
        "authorization_actor": authorization_actor,
        "protection": protection,
        "merge_mode": "agent" if protection == "enforced" else "human-only",
        "protection_reason": reason,
    }


def mutate_state(args: argparse.Namespace, github: GitHub) -> None:
    """Change Draft state only while the exact lease remains live."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, github)
    require_lease(lease, args.repo, args.pr_number, args.head_sha)
    pull = live_pull(github, args.repo, args.pr_number, args.head_sha)
    current = bool(pull.get("draft"))
    desired = args.state == "draft"
    if current == desired:
        raise RuntimeError(f"Pull request is already {args.state}")
    command = ["gh", "pr", "ready", str(args.pr_number), "--repo", args.repo]
    if desired:
        command.append("--undo")
    run(command)
    require_lease(lease, args.repo, args.pr_number, args.head_sha)
    updated = live_pull(github, args.repo, args.pr_number, args.head_sha)
    if bool(updated.get("draft")) != desired:
        raise RuntimeError(
            "Pull request Draft state did not change as requested"
        )


def check(args: argparse.Namespace, github: GitHub) -> None:
    """Print the live merge snapshot without mutating GitHub."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, github)
    snapshot = merge_snapshot(github, lease, args.authorization_url)
    sys.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")


def merge(args: argparse.Namespace, github: GitHub) -> None:
    """Merge only when both the lease and server-side controls are enforced."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, github)
    snapshot = merge_snapshot(github, lease, args.authorization_url)
    if snapshot["merge_mode"] != "agent":
        raise RuntimeError(
            "Agent merge is blocked: server-side protection is unavailable or "
            "incomplete; a human maintainer must merge manually"
        )
    require_lease(lease, args.repo, args.pr_number, args.head_sha)
    run(
        [
            "gh",
            "pr",
            "merge",
            str(args.pr_number),
            "--repo",
            args.repo,
            "--squash",
            "--match-head-commit",
            args.head_sha,
        ]
    )
    release_refs(lease)


def release(args: argparse.Namespace, github: GitHub) -> None:
    """Release only the exact lease held by this evidence file."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, github)
    if (
        lease["repository"].casefold() != args.repo.casefold()
        or lease["pull_request"] != args.pr_number
    ):
        raise RuntimeError("Lease does not match the requested pull request")
    require_origin(args.repo)
    release_refs(lease)


def authorization_template(args: argparse.Namespace, github: GitHub) -> None:
    """Print the exact statement a human maintainer may post."""
    lease = read_lease(args.lease)
    require_caller(lease, args.owner, github)
    require_lease(lease, args.repo, args.pr_number, args.head_sha)
    binding = {
        "repository": args.repo,
        "pull_request": args.pr_number,
        "head_sha": args.head_sha,
    }
    sys.stdout.write(
        "PR lifecycle merge authorization\n\n"
        f"`{canonical_json(binding)}`\n\n"
        "I authorize this exact pull request head for one merge attempt.\n"
    )


def parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(required=True)
    acquire_command = commands.add_parser("acquire")
    acquire_command.add_argument("--repo", required=True)
    acquire_command.add_argument("--pr-number", required=True, type=int)
    acquire_command.add_argument("--head-sha", required=True)
    acquire_command.add_argument("--owner", required=True)
    acquire_command.add_argument("--ttl-seconds", type=int, default=3600)
    acquire_command.add_argument("--output", type=Path, required=True)
    acquire_command.set_defaults(handler=acquire)

    for name in (
        "state",
        "check",
        "merge",
        "authorization-template",
        "release",
    ):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        command.add_argument("--pr-number", required=True, type=int)
        command.add_argument("--lease", type=Path, required=True)
        command.add_argument("--owner", required=True)
        if name != "release":
            command.add_argument("--head-sha", required=True)
        if name in {"check", "merge"}:
            command.add_argument("--authorization-url", required=True)
        if name == "state":
            command.add_argument(
                "--state", choices=("ready", "draft"), required=True
            )
        command.set_defaults(handler_name=name)
    return result


def main() -> None:
    """Run one fail-closed lifecycle operation."""
    args = parser().parse_args()
    github = GitHub()
    try:
        if hasattr(args, "handler"):
            args.handler(args, github)
        elif args.handler_name == "state":
            mutate_state(args, github)
        elif args.handler_name == "check":
            check(args, github)
        elif args.handler_name == "merge":
            merge(args, github)
        elif args.handler_name == "authorization-template":
            authorization_template(args, github)
        else:
            release(args, github)
    except (RuntimeError, json.JSONDecodeError) as error:
        sys.stderr.write(f"PR lifecycle blocked: {error}\n")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
