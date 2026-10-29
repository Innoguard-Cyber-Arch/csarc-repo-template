#!/usr/bin/env python3
"""Reverify behind Dependabot pull requests on the latest main (Issue #1264).

Template repository only; nothing here ships to `template/`. When main
advances, a same-repository Dependabot pull request that GitHub still reports
as mergeable is verified again on GitHub's own test merge of its unchanged
head into the current main (`refs/pull/<N>/merge`). The trusted workflow
`.github/workflows/dependabot-reverify.yml` names that exact identity in one
step, and `pr_lifecycle.py` accepts a base behind main only on the Dependabot
path and only with such a result bound to the current main.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TYPE_CHECKING:
    from pr_lifecycle import GitHub

WORKFLOW_PATH = ".github/workflows/dependabot-reverify.yml"
TRUSTED_EVENTS = frozenset({"push", "workflow_dispatch", "workflow_run"})
GITHUB_ACTIONS_APP_ID = 15368
DEPENDABOT_LOGIN = "dependabot[bot]"
ELIGIBILITY_CONTEXT = "dependabot-merge-eligible"
COMMAND = "./scripts/verify-template.sh"
NOTICE_MARKER = "<!-- csarc-dependabot-reverify-conflict -->"
SHA = re.compile(r"[0-9a-f]{40}")
STEP = re.compile(
    r"^Execute Dependabot reverification pr=([1-9][0-9]*) "
    r"head=([0-9a-f]{40}) main=([0-9a-f]{40}) merge=([0-9a-f]{40}) "
    r"tree=([0-9a-f]{40}) scopes=([a-z,-]+) tier=full "
    r"command=(\./scripts/verify-template\.sh) "
    r"executor=trusted-base$"
)
GH_RETRY = "Run 'gh auth status', then rerun it"


def module(name: str) -> ModuleType:
    """Load one sibling module only when a command needs it."""
    return importlib.import_module(name)


def check_name(number: int) -> str:
    """Return the per-pull-request reverification check name."""
    return f"dependabot-reverify (#{number})"


def require(
    github: GitHub,
    repo: str,
    pr_number: int,
    head_sha: str,
    main_sha: str,
    *,
    now: datetime | None = None,
    max_age_hours: float | None = None,
) -> dict[str, Any]:
    """Return trusted reverification evidence bound to this main, or fail.

    The check run must come from the trusted workflow run on exactly
    `main_sha` (so main advancing again invalidates it), on a GitHub-hosted
    runner, and carry one successful step naming this pull request, its
    unchanged head, that main, and the verified merge tree.
    """
    name = check_name(pr_number)
    query = urllib.parse.quote(name)
    runs = github.collection(
        repo,
        f"commits/{main_sha}/check-runs?check_name={query}&filter=latest"
        "&per_page=100",
        "check_runs",
    )
    candidates = [
        item
        for item in runs
        if item.get("name") == name
        and item.get("head_sha") == main_sha
        and (item.get("app") or {}).get("id") == GITHUB_ACTIONS_APP_ID
    ]
    if not candidates:
        raise RuntimeError(
            f"Dependabot reverification: none on main {main_sha}. Wait for "
            "'dependabot-reverify' or dispatch it."
        )
    check = max(candidates, key=lambda item: int(item["id"]))
    if check.get("status") != "completed" or check.get("conclusion") != (
        "success"
    ):
        raise RuntimeError(
            "Dependabot reverification: did not pass on the current main. "
            "Read its run, then fix or merge it manually."
        )
    lifecycle = module("pr_lifecycle")
    run_url = lifecycle.actions_run_url(str(check.get("details_url")), repo)
    run_id = int(run_url.rsplit("/", 1)[1])
    run = github.get(repo, f"actions/runs/{run_id}")
    suite = check.get("check_suite") or {}
    if (
        not isinstance(run, dict)
        or run.get("id") != run_id
        or run.get("path") != WORKFLOW_PATH
        or run.get("event") not in TRUSTED_EVENTS
        or run.get("head_sha") != main_sha
        or run.get("head_branch") != "main"
        or (run.get("repository") or {}).get("full_name") != repo
        or run.get("check_suite_id") != suite.get("id")
    ):
        raise RuntimeError(
            "Dependabot reverification: untrusted producer. Rerun "
            f"'{WORKFLOW_PATH}' on main."
        )
    jobs = github.collection(
        repo,
        f"actions/runs/{run_id}/jobs?filter=latest&per_page=100",
        "jobs",
    )
    matching = [
        job
        for job in jobs
        if job.get("id") == check.get("id")
        and job.get("html_url") == check.get("details_url")
        and job.get("name") == name
    ]
    if len(matching) != 1:
        raise RuntimeError(
            "Dependabot reverification: no unique job. Rerun "
            f"'{WORKFLOW_PATH}' on main."
        )
    job = matching[0]
    labels = job.get("labels")
    if (
        job.get("conclusion") != "success"
        or job.get("head_sha") != main_sha
        or not isinstance(labels, list)
        or "ubuntu-latest" not in labels
        or "self-hosted" in labels
        or job.get("runner_group_name") != "GitHub Actions"
    ):
        raise RuntimeError(
            "Dependabot reverification: not a passing GitHub-hosted job. "
            f"Rerun '{WORKFLOW_PATH}' on main."
        )
    module("evidence_freshness").require_fresh(
        job.get("completed_at"),
        subject="Dependabot reverification",
        now=now,
        max_age_hours=max_age_hours,
    )
    claims = [
        match
        for step in job.get("steps") or []
        if isinstance(step, dict) and step.get("conclusion") == "success"
        for match in [STEP.fullmatch(str(step.get("name") or ""))]
        if match is not None
    ]
    if len(claims) != 1:
        raise RuntimeError(
            "Dependabot reverification: no single execution claim. Rerun "
            f"'{WORKFLOW_PATH}' on main."
        )
    number, head, main, merge, tree, raw_scopes, command = claims[0].groups()
    token = module("verification_evidence").toolchain_token
    toolchain = [
        name
        for step in job.get("steps") or []
        if isinstance(step, dict) and step.get("conclusion") == "success"
        for name in [token(str(step.get("name") or ""))]
        if name is not None
    ]
    scopes = raw_scopes.split(",")
    valid = module("verification_evidence").VALID_SCOPES
    if scopes != sorted(set(scopes)) or not set(scopes) <= valid:
        raise RuntimeError(
            "Dependabot reverification: invalid scopes. Rerun "
            f"'{WORKFLOW_PATH}' on main."
        )
    if int(number) != pr_number or head != head_sha or main != main_sha:
        raise RuntimeError(
            "Dependabot reverification: bound to another head or main. Wait "
            "for the run on the current main."
        )
    return {
        "pull_request": pr_number,
        "head_sha": head_sha,
        "main_sha": main_sha,
        "merge_sha": merge,
        "tree_sha": tree,
        "tier": "full",
        "scopes": scopes,
        "command": command,
        "event": run.get("event"),
        "run_id": run_id,
        "run_attempt": run.get("run_attempt"),
        "job_id": job.get("id"),
        "check_run_id": check.get("id"),
        "runner_labels": sorted(str(item) for item in labels),
        "toolchain": toolchain,
        "completed_at": job.get("completed_at"),
    }


def tree_and_parents(
    github: GitHub, repo: str, sha: str
) -> tuple[object, list[object]]:
    """Return one commit's tree SHA and parent SHAs as GitHub reports them."""
    commit = github.get(repo, f"git/commits/{sha}")
    commit = commit if isinstance(commit, dict) else {}
    return (commit.get("tree") or {}).get("sha"), [
        item.get("sha")
        for item in commit.get("parents") or []
        if isinstance(item, dict)
    ]


def require_eligible(
    github: GitHub, repo: str, pull: dict[str, Any], head_sha: str
) -> None:
    """Require Dependabot coordinates and trusted exact-head eligibility.

    Issue #1284: the same gate the release source applies to an ordinary
    Dependabot squash, so a reverified squash merged without a passing
    `dependabot-merge-eligible` (for example by admin bypass) never
    resolves as a verified source.
    """
    head = pull.get("head") or {}
    user = pull.get("user") or {}
    auth = module("authenticate_dependabot_head")
    coordinates, _ = auth.dependabot_coordinates_eligible(
        str(user.get("login") or ""),
        str(head.get("ref") or ""),
        str((head.get("repo") or {}).get("full_name") or ""),
        repo,
    )
    lifecycle = module("pr_lifecycle")
    identity = (ELIGIBILITY_CONTEXT, GITHUB_ACTIONS_APP_ID)
    checks = github.collection(
        repo,
        f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
        "check_runs",
    )
    selected, _ = lifecycle.trusted_required_check_runs(
        github, repo, head_sha, {identity}, checks
    )
    check = selected.get(identity) or {}
    if (
        not coordinates
        or user.get("type") != "Bot"
        or check.get("status") != "completed"
        or check.get("conclusion") != "success"
    ):
        raise RuntimeError(
            "Dependabot source lacks trusted exact-head eligibility: no "
            "pass. Wait for its 'verify' check."
        )


def merged(
    github: GitHub,
    repo: str,
    commit: str,
    *,
    now: datetime | None = None,
    max_age_hours: float | None = None,
) -> dict[str, Any]:
    """Return the reverification that verified this exact main squash.

    Issue #1284: clean sync and release source resolution may stand on a
    reverified Dependabot merge only when the squash has exactly the
    verified tree on the main it was verified on, and the verified test
    merge's parents are that main and the unchanged head. A squash GitHub
    put on a newer main (the accepted #1264 window) has another parent or
    tree and fails closed here.
    """
    pulls = [
        pull
        for pull in github.pages(repo, f"commits/{commit}/pulls?per_page=100")
        if pull.get("merged_at")
        and pull.get("merge_commit_sha") == commit
        and (pull.get("base") or {}).get("ref") == "main"
        and (pull.get("user") or {}).get("login") == DEPENDABOT_LOGIN
    ]
    tree, parents = tree_and_parents(github, repo, commit)
    if len(pulls) != 1 or len(parents) != 1:
        raise RuntimeError(
            "Merged main tree does not match: source differs and no "
            "Dependabot reverification binds it. Verify the merge."
        )
    head_sha = str((pulls[0].get("head") or {}).get("sha") or "")
    require_eligible(github, repo, pulls[0], head_sha)
    evidence = require(
        github,
        repo,
        int(pulls[0]["number"]),
        head_sha,
        str(parents[0]),
        now=now,
        max_age_hours=max_age_hours,
    )
    if tree != evidence["tree_sha"] or tree_and_parents(
        github, repo, evidence["merge_sha"]
    ) != (tree, [parents[0], head_sha]):
        raise RuntimeError(
            f"Reverified Dependabot merge {commit}: tree {tree} was not "
            "verified. Verify it on main, or revert it."
        )
    return {**evidence, "base": "main", "reused": False}


def payload(
    evidence: dict[str, Any], repo: str, head_tree: str, pull_base_sha: str
) -> dict[str, Any]:
    """Return the durable merge-evidence payload for a reverified merge.

    Its `tree_sha` is the verified test-merge tree, which the squash merge
    must reproduce, and `base_sha` is the main it was verified on; the
    original head tree and stale pull request base stay visible beside them.
    """
    return {
        "schema_version": 1,
        "trust": "github-hosted",
        "success": True,
        "conclusion": "success",
        "repository": {"full_name": repo},
        "head_sha": evidence["head_sha"],
        "tree_sha": evidence["tree_sha"],
        "base_ref": "main",
        "base_sha": evidence["main_sha"],
        "tier": evidence["tier"],
        "scopes": evidence["scopes"],
        "command": evidence["command"],
        "runner_labels": evidence["runner_labels"],
        "executor": {
            "kind": "github-hosted",
            "id": f"{evidence['run_id']}/{evidence['run_attempt']}",
            "run_id": evidence["run_id"],
            "run_attempt": evidence["run_attempt"],
            "job_id": evidence["job_id"],
            "check_run_id": evidence["check_run_id"],
            "app_id": GITHUB_ACTIONS_APP_ID,
        },
        "completed_at": evidence["completed_at"],
        "dependabot_reverification": {
            "pull_request": evidence["pull_request"],
            "merge_sha": evidence["merge_sha"],
            "event": evidence["event"],
            "head_tree": head_tree,
            "pull_base_sha": pull_base_sha,
        },
    }


def approved_head(reviews: list[dict[str, Any]], head_sha: str) -> bool:
    """Return whether someone's latest review approves this exact head."""
    latest: dict[str, dict[str, Any]] = {}
    for review in reviews:
        login = str((review.get("user") or {}).get("login") or "")
        if login and review.get("state") in {
            "APPROVED",
            "CHANGES_REQUESTED",
            "DISMISSED",
        }:
            latest[login] = review
    return any(
        review.get("state") == "APPROVED"
        and review.get("commit_id") == head_sha
        for review in latest.values()
    )


def release_intent(title: str, messages: list[str]) -> str:
    """Return the highest release intent of the title and every commit.

    The squash merge keeps the title, and planning reads the commits; both
    use `release_policy.py`'s own intent rules.
    """
    policy = module("release_policy")
    highest = policy.release_intent(title)
    for message in messages:
        subject, _, body = message.partition("\n")
        intent = (
            "major"
            if policy._is_breaking(subject, body)
            else policy.release_intent(subject)
        )
        if policy.INTENT_RANK[intent] > policy.INTENT_RANK[highest]:
            highest = intent
    return highest


def require_no_release(pull: dict[str, Any], messages: list[str]) -> None:
    """Refuse a head whose merge would plan a release (Issue #1264).

    A reverified merge squashes a tree other than the head's, so no source
    history can own a version and no release is dispatched after it.
    """
    intent = release_intent(str(pull.get("title") or ""), messages)
    if intent != "no-release":
        raise RuntimeError(
            f"Pull request #{pull.get('number')}: release intent {intent} "
            "cannot be reverified on a newer main. Wait for a Dependabot "
            "rebase."
        )


def classify(
    pull: dict[str, Any],
    main_sha: str,
    *,
    approved: bool,
    eligible: bool,
    reverified: bool,
    no_release: bool = True,
) -> str:
    """Return one inventory state; only `reverify` starts a verification.

    `current` already uses the ordinary path, `conflict` needs a Dependabot
    rebase or a human, `pending` waits for GitHub's mergeability, `waiting`
    lacks an exact-head approval, eligibility, or a single direct commit, and
    `reverified` already has a result on this main (deduplication).
    `rebase` plans a release, so only a Dependabot rebase can merge it.
    """
    if (pull.get("base") or {}).get("sha") == main_sha:
        return "current"
    if pull.get("mergeable") is False:
        return "conflict"
    if pull.get("mergeable") is not True:
        return "pending"
    if not (approved and eligible and pull.get("commits") == 1):
        return "waiting"
    if not no_release:
        return "rebase"
    if reverified:
        return "reverified"
    return "reverify"


def dependabot_pulls(github: GitHub, repo: str) -> list[dict[str, Any]]:
    """List open same-repository Dependabot pull requests against main."""
    return [
        pull
        for pull in github.pages(
            repo, "pulls?state=open&base=main&per_page=100"
        )
        if (pull.get("user") or {}).get("login") == DEPENDABOT_LOGIN
        and ((pull.get("head") or {}).get("repo") or {}).get("full_name")
        == repo
        and str((pull.get("head") or {}).get("ref") or "").startswith(
            "dependabot/"
        )
    ]


def live_pull(github: GitHub, repo: str, number: int) -> dict[str, Any]:
    """Read one pull request, waiting briefly for GitHub's mergeability."""
    pull: object = {}
    for attempt in range(4):
        pull = github.get(repo, f"pulls/{number}")
        if not isinstance(pull, dict):
            raise RuntimeError(
                f"Pull request #{number}: unreadable. {GH_RETRY}."
            )
        if pull.get("mergeable") is not None or attempt == 3:
            break
        time.sleep(5)
    return pull if isinstance(pull, dict) else {}


def inventory(github: GitHub, repo: str, main_sha: str) -> list[dict[str, Any]]:
    """Return the read-only state of every open Dependabot pull request."""
    rows = []
    for listed in dependabot_pulls(github, repo):
        number = int(listed["number"])
        pull = live_pull(github, repo, number)
        head_sha = str((pull.get("head") or {}).get("sha") or "")
        checks = github.collection(
            repo,
            f"commits/{head_sha}/check-runs?check_name={ELIGIBILITY_CONTEXT}"
            "&filter=latest&per_page=100",
            "check_runs",
        )
        eligible = any(
            item.get("conclusion") == "success"
            and (item.get("app") or {}).get("id") == GITHUB_ACTIONS_APP_ID
            for item in checks
        )
        reviews = github.pages(repo, f"pulls/{number}/reviews?per_page=100")
        try:
            require_no_release(pull, commit_messages(github, repo, number))
            no_release = True
        except RuntimeError:
            no_release = False
        try:
            require(github, repo, number, head_sha, main_sha)
            reverified = True
        except RuntimeError:
            reverified = False
        rows.append(
            {
                "number": number,
                "head_sha": head_sha,
                "head_ref": str((pull.get("head") or {}).get("ref") or ""),
                "base_sha": str((pull.get("base") or {}).get("sha") or ""),
                "state": classify(
                    pull,
                    main_sha,
                    approved=approved_head(reviews, head_sha),
                    eligible=eligible,
                    reverified=reverified,
                    no_release=no_release,
                ),
            }
        )
    return rows


def inventory_markdown(rows: list[dict[str, Any]], main_sha: str) -> str:
    """Render the inventory printed before any verification or notice."""
    lines = [
        f"### Dependabot reverification inventory (main `{main_sha[:12]}`)",
        "",
        "| PR | Head | Base | State |",
        "| --- | --- | --- | --- |",
    ]
    lines += [
        f"| #{row['number']} | `{row['head_sha'][:12]}` | "
        f"`{row['base_sha'][:12]}` | {row['state']} |"
        for row in rows
    ]
    if not rows:
        lines.append("| - | - | - | no open Dependabot pull request |")
    return "\n".join(lines) + "\n"


def commit_messages(github: GitHub, repo: str, number: int) -> list[str]:
    """Read every commit message of one pull request."""
    return [
        str((item.get("commit") or {}).get("message") or "")
        for item in github.pages(repo, f"pulls/{number}/commits?per_page=100")
    ]


def bind(
    pull: dict[str, Any],
    pr_number: int,
    head_sha: str,
    main_sha: str,
    merge_sha: str,
    parents: list[str],
    messages: list[str],
) -> None:
    """Refuse a candidate that is not the test merge of this head into main."""
    if (
        pull.get("state") != "open"
        or pull.get("number") != pr_number
        or (pull.get("user") or {}).get("login") != DEPENDABOT_LOGIN
        or (pull.get("base") or {}).get("ref") != "main"
        or (pull.get("head") or {}).get("sha") != head_sha
        or pull.get("mergeable") is not True
    ):
        raise RuntimeError(
            f"Pull request #{pr_number}: changed since the inventory. Wait "
            "for the next reverification run."
        )
    if SHA.fullmatch(merge_sha) is None or parents != [main_sha, head_sha]:
        raise RuntimeError(
            f"Test merge of #{pr_number}: not this head on main {main_sha}. "
            "Wait for GitHub to refresh it, then rerun."
        )
    require_no_release(pull, messages)


def post_notices(github: GitHub, repo: str, numbers: list[int]) -> list[int]:
    """Post one conflict notice per pull request; never repeat it."""
    posted = []
    for number in numbers:
        comments = github.pages(repo, f"issues/{number}/comments?per_page=100")
        if any(
            NOTICE_MARKER in str(comment.get("body") or "")
            for comment in comments
        ):
            continue
        github.comment(
            repo,
            number,
            NOTICE_MARKER
            + "\nThis Dependabot update conflicts with `main`, so it was not "
            "reverified and will not merge automatically. Comment "
            "`@dependabot rebase`; if Dependabot does not respond, follow "
            "the manual steps in `docs/ci-policy.md` (Issue #1264).",
        )
        posted.append(number)
    return posted


def write_output(path: Path | None, values: dict[str, str]) -> None:
    """Append single-line values to one GitHub Actions output file."""
    if path is None:
        return
    with path.open("a", encoding="utf-8") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    """Run one read-only inventory, one binding check, or the notices."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("inventory")
    listing.add_argument("--repo", required=True)
    listing.add_argument("--main-sha", required=True)
    listing.add_argument("--github-output", type=Path)
    listing.add_argument("--summary", type=Path)
    binding = commands.add_parser("bind")
    binding.add_argument("--repo", required=True)
    binding.add_argument("--pr-number", type=int, required=True)
    binding.add_argument("--head-sha", required=True)
    binding.add_argument("--main-sha", required=True)
    binding.add_argument("--merge-sha", required=True)
    binding.add_argument("--parents", required=True)
    notice = commands.add_parser("notice")
    notice.add_argument("--repo", required=True)
    notice.add_argument("--pr-numbers", required=True)
    passed = commands.add_parser("passed")
    passed.add_argument("--repo", required=True)
    passed.add_argument("--main-sha", required=True)
    passed.add_argument("--matrix", required=True)
    passed.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    github = module("pr_lifecycle").GitHub()
    try:
        if args.command == "inventory":
            rows = inventory(github, args.repo, args.main_sha)
            text = inventory_markdown(rows, args.main_sha)
            sys.stdout.write(text)
            if args.summary is not None:
                with args.summary.open("a", encoding="utf-8") as stream:
                    stream.write(text)
            keys = ("number", "head_sha", "head_ref")
            pick = [
                {key: row[key] for key in keys}
                for row in rows
                if row["state"] == "reverify"
            ]
            write_output(
                args.github_output,
                {
                    "matrix": json.dumps(pick, separators=(",", ":")),
                    "conflicts": json.dumps(
                        [r["number"] for r in rows if r["state"] == "conflict"]
                    ),
                },
            )
        elif args.command == "bind":
            pull = github.get(args.repo, f"pulls/{args.pr_number}")
            bind(
                pull if isinstance(pull, dict) else {},
                args.pr_number,
                args.head_sha,
                args.main_sha,
                args.merge_sha,
                args.parents.split(),
                commit_messages(github, args.repo, args.pr_number),
            )
        elif args.command == "passed":
            ready = []
            for item in json.loads(args.matrix):
                try:
                    require(
                        github,
                        args.repo,
                        int(item["number"]),
                        str(item["head_sha"]),
                        args.main_sha,
                    )
                except RuntimeError as error:
                    sys.stdout.write(
                        f"NOTICE: Skipped #{item['number']}, which is not "
                        f"ready ({error}).\n"
                    )
                    continue
                ready.append(
                    {"number": item["number"], "head_sha": item["head_sha"]}
                )
            write_output(
                args.github_output,
                {"ready": json.dumps(ready, separators=(",", ":"))},
            )
        else:
            numbers = json.loads(args.pr_numbers)
            for number in post_notices(github, args.repo, numbers):
                sys.stdout.write(
                    f"NOTICE: Posted the conflict notice on #{number}.\n"
                )
    except RuntimeError as error:
        sys.stderr.write(f"ERROR: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
