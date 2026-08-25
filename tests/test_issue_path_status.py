"""Behavior contracts for the read-only Issue path status entrypoint."""

from __future__ import annotations

import base64
import hashlib
import runpy
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from promotion_gate import quota_fallback_note  # noqa: E402

MODULE = runpy.run_path(str(SCRIPTS / "issue_path_status.py"))
GitHub = MODULE["GitHub"]
check_state = MODULE["check_state"]
derive_status = MODULE["derive_status"]
has_exact_quota_note = MODULE["has_exact_quota_note"]
has_human_approval = MODULE["has_human_approval"]
inspect_issue = MODULE["inspect_issue"]
inspect_capability = MODULE["inspect_capability"]
native_links = MODULE["_native_links"]
route_for = MODULE["route_for"]
unresolved_blocker = MODULE["unresolved_blocker"]


def lifecycle_content(
    content: bytes | None = None,
    path: str = "scripts/pr_lifecycle.py",
) -> dict[str, str]:
    """Return one exact GitHub Contents response for a policy helper."""
    payload = content or (SCRIPTS / Path(path).name).read_bytes()
    git_blob = b"blob " + str(len(payload)).encode() + b"\0" + payload
    return {
        "type": "file",
        "path": path,
        "sha": hashlib.sha1(git_blob, usedforsecurity=False).hexdigest(),
        "encoding": "base64",
        "content": base64.b64encode(payload).decode(),
    }


def observation(
    *,
    milestone: int | None = 9,
    issue_labels: list[str] | None = None,
    branches: dict[str, str] | None = None,
    pulls: list[dict[str, Any]] | None = None,
    work_branches: list[str] | None = None,
    files: list[str] | None = None,
    checks: str = "missing",
    capability: str = "unknown",
    blocker: str | None = None,
    base_current: bool = True,
    blocked_run_urls: list[str] | None = None,
    quota_note: bool = False,
    human_approval: bool = False,
) -> dict[str, Any]:
    """Build one normalized live-state fixture."""
    branch_map = (
        {"main": "main", "dev/next": "next", "dev/m9-sdlc": "base"}
        if branches is None
        else branches
    )
    pull_items = pulls or []
    return {
        "repository": "owner/repo",
        "issue": {
            "number": 266,
            "state": "open",
            "labels": [{"name": name} for name in issue_labels or []],
            "milestone": {"number": milestone} if milestone else None,
        },
        "branches": branch_map,
        "pulls": pull_items,
        "native_links": {("owner/repo", pull["number"]) for pull in pull_items},
        "work_branches": work_branches or [],
        "files": files or [],
        "checks": checks,
        "capability": {
            "state": capability,
            "reason": "fixture",
            "required": ["verify"],
        },
        "blocker": blocker,
        "base_current": base_current,
        "chain_ancestry": {
            f"{item['base']['sha']}...{item['head']['sha']}": True
            for item in pull_items
        },
        "blocked_run_urls": blocked_run_urls or [],
        "quota_note": quota_note,
        "human_approval": human_approval,
    }


def pull(
    number: int = 300,
    *,
    draft: bool = True,
    base: str = "dev/m9-sdlc",
    base_sha: str = "base",
    head: str = "feat/266-path-status",
    head_sha: str = "head",
    body: str | None = None,
    state: str = "open",
    merged_at: str | None = None,
    merge_commit_sha: str | None = None,
) -> dict[str, Any]:
    """Build one live pull-request fixture."""
    link = "Refs #266" if draft else "Closes #266"
    contract = (
        f"{link}\n\n"
        "- Scope: Add Issue path status\n"
        "- Completed verification: Targeted tests pass\n"
        "- Pending verification: None\n"
        "- Known risks: None\n"
        "- Dependencies / non-parallel work: None"
    )
    if not draft:
        contract += "\n\nAlpha 自行合併 / self-merged"
    return {
        "number": number,
        "state": state,
        "draft": draft,
        "html_url": f"https://github.com/owner/repo/pull/{number}",
        "body": contract if body is None else body,
        "merged_at": merged_at,
        "merge_commit_sha": merge_commit_sha,
        "base": {"ref": base, "sha": base_sha},
        "head": {
            "ref": head,
            "sha": head_sha,
            "repo": {"full_name": "owner/repo"},
        },
    }


def test_milestone_issue_selects_one_live_delivery_branch() -> None:
    """A Milestone Issue needs no manual branch choice."""
    decision = derive_status(observation())
    assert decision.state == "Open"
    assert decision.guard == "clear"
    assert decision.route["kind"] == "milestone"
    assert decision.route["base"] == "dev/m9-sdlc"
    assert decision.allowed_actions == ("create-branch", "open-draft")


def test_live_read_model_drives_the_milestone_scenario_end_to_end() -> None:
    """The public entrypoint derives its answer from GitHub resources."""

    class FakeGitHub:
        def __init__(self) -> None:
            self.reads: list[str] = []

        def get(self, _repo: str, path: str = "") -> object:
            self.reads.append(path or "repository")
            if not path:
                return {"permissions": {"push": True}}
            if path == "issues/266":
                return {
                    "number": 266,
                    "state": "open",
                    "labels": [],
                    "milestone": {"number": 9},
                }
            raise AssertionError(path)

        def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
            self.reads.append(path)
            if path.startswith("branches?"):
                return [
                    {"name": "main", "commit": {"sha": "main"}},
                    {"name": "dev/m9-sdlc", "commit": {"sha": "base"}},
                ]
            return []

    github = FakeGitHub()
    decision = inspect_issue(github, "owner/repo", 266, "delivery")
    assert decision.state == "Open"
    assert decision.route["base"] == "dev/m9-sdlc"
    assert github.reads == [
        "repository",
        "issues/266",
        "branches?per_page=100",
        "pulls?state=all&per_page=100",
        "issues/266/timeline?per_page=100",
    ]


def test_standalone_issue_selects_dev_next() -> None:
    """A standalone Issue uses the durable shared delivery branch."""
    decision = derive_status(observation(milestone=None))
    assert decision.route["kind"] == "standalone"
    assert decision.route["base"] == "dev/next"
    assert "dev/next" in decision.next_step


def test_repository_profile_selects_main_or_dev_without_user_choice() -> None:
    """Generated repositories keep their declared non-delivery route."""
    issue = {"number": 266, "labels": [], "milestone": None}
    assert route_for(issue, {"main": "sha"}, "main")["base"] == "main"
    assert (
        route_for(issue, {"main": "one", "dev": "two"}, "dev")["base"] == "dev"
    )
    issue["labels"] = [{"name": "promotion"}]
    dev_promotion = route_for(issue, {"main": "one", "dev": "two"}, "dev")
    assert dev_promotion["base"] == "main"
    assert dev_promotion["head"] == "dev"


def test_standalone_batch_promotion_selects_dev_next() -> None:
    """A non-Milestone promotion can deliver the shared dev/next batch."""
    current = pull(
        draft=False,
        base="main",
        base_sha="main",
        head="dev/next",
        head_sha="next",
    )
    data = observation(
        milestone=None,
        issue_labels=["promotion"],
        pulls=[current],
        branches={"main": "main", "dev/next": "next"},
        files=["src/release.py"],
        checks="passing",
        capability="allowed",
        human_approval=True,
    )
    decision = derive_status(data)
    assert decision.state == "Candidate"
    assert decision.guard == "clear"
    assert decision.route["kind"] == "standalone-batch-promotion"
    assert decision.route["head"] == "dev/next"
    assert decision.allowed_actions == ("acquire-lease",)


def test_hotfix_is_always_a_full_main_route() -> None:
    """An explicit standalone hotfix never takes the routine path."""
    current = pull(
        draft=False,
        base="main",
        base_sha="main",
        head="fix/266-outage",
    )
    data = observation(
        milestone=None,
        issue_labels=["hotfix"],
        pulls=[current],
        branches={"main": "main", "fix/266-outage": "head"},
        files=["src/fix.py"],
        checks="passing",
        capability="allowed",
        human_approval=True,
    )
    decision = derive_status(data)
    assert decision.state == "Candidate"
    assert decision.risk["class"] == "promotion"
    assert decision.risk["ci_tier"] == "full"
    assert decision.risk["verification"] == [
        "full",
        "promotion",
        "tree-identity",
    ]
    assert decision.allowed_actions == ("acquire-lease",)


def test_hotfix_rejects_a_non_fix_issue_branch() -> None:
    """A hotfix label cannot route an ordinary feature branch to main."""
    current = pull(
        draft=False,
        base="main",
        base_sha="main",
        head="feat/266-normal",
    )
    data = observation(
        milestone=None,
        issue_labels=["hotfix"],
        pulls=[current],
        branches={"main": "main", "feat/266-normal": "head"},
        files=["src/fix.py"],
        checks="passing",
        human_approval=True,
    )
    decision = derive_status(data)
    assert decision.state == "Ready"
    assert decision.guard == "blocked"
    assert "does not match the hotfix route" in decision.reason
    assert "merge-once" not in decision.allowed_actions


def test_draft_rejects_a_branch_for_another_issue() -> None:
    """Native linkage cannot make another Issue's head a valid owner."""
    current = pull(head="feat/999-wrong")
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/999-wrong": "head",
        },
    )
    decision = derive_status(data)
    assert decision.state == "Draft"
    assert decision.guard == "blocked"
    assert "does not match the milestone route" in decision.reason
    assert "type/266-*" in decision.next_step


def test_draft_rejects_a_closed_linked_issue() -> None:
    """Visible Draft ownership cannot silently reopen a closed Issue."""
    data = observation(
        pulls=[pull()],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
    )
    data["issue"]["state"] = "closed"
    decision = derive_status(data)
    assert decision.state == "Draft"
    assert decision.guard == "blocked"
    assert "Issue is closed" in decision.reason
    assert "Reopen Issue #266" in decision.next_step


def test_parallel_claims_fail_closed() -> None:
    """Two agents cannot both own an Issue through open PRs."""
    data = observation(pulls=[pull(300), pull(301, head="fix/266-other")])
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "More than one open pull request" in decision.reason
    assert "close or unlink" in decision.next_step


def test_external_links_cannot_claim_local_issue_ownership() -> None:
    """Cross-repository references and PR-number collisions are not owners."""
    current = pull(head="feat/999-foreign", body="Refs other/repo#266")
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/m9-sdlc": "base",
            "feat/999-foreign": "head",
        },
    )
    data["native_links"] = {("other/repo", current["number"])}
    decision = derive_status(data)
    assert decision.state == "Open"
    assert decision.pull_request is None

    timeline = [
        {
            "source": {
                "issue": {
                    "number": current["number"],
                    "pull_request": {},
                    "repository_url": "https://api.github.com/repos/other/repo",
                }
            }
        }
    ]
    assert native_links(timeline, "owner/repo") == set()


def test_open_pr_does_not_hide_a_second_issue_branch() -> None:
    """One visible owner cannot mask another live same-Issue branch."""
    data = observation(
        pulls=[pull()],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
            "fix/266-parallel": "other",
        },
        work_branches=["feat/266-path-status", "fix/266-parallel"],
    )
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "More than one remote work branch" in decision.reason


def test_valid_stacked_pr_chain_reaches_the_delivery_branch() -> None:
    """A unique immediate-parent chain is a valid Issue route."""
    child = pull(draft=True, base="enhancement/254-parent", base_sha="parent")
    parent = pull(
        281,
        draft=False,
        base="dev/m9-sdlc",
        base_sha="base",
        head="enhancement/254-parent",
        head_sha="parent",
    )
    data = observation(
        pulls=[child],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "enhancement/254-parent": "parent",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
    )
    data["all_pulls"] = [child, parent]
    data["chain_ancestry"]["base...parent"] = True
    decision = derive_status(data)
    assert decision.state == "Draft"
    assert decision.guard == "clear"
    assert decision.observed_evidence["base_chain"] == [
        "feat/266-path-status",
        "enhancement/254-parent",
        "dev/m9-sdlc",
    ]
    assert decision.observed_evidence["delivery_sha"] == "base"
    assert decision.observed_evidence["immediate_base_sha"] == "parent"
    assert decision.pull_request is not None
    assert decision.pull_request["base_sha"] == "parent"


def test_ready_stacked_pr_waits_for_parent_then_retargets() -> None:
    """A stack is visible in Draft but an Issue merges only to its route."""
    child = pull(draft=False, base="enhancement/254-parent", base_sha="parent")
    parent = pull(
        281,
        draft=False,
        base="dev/m9-sdlc",
        base_sha="base",
        head="enhancement/254-parent",
        head_sha="parent",
    )
    data = observation(
        pulls=[child],
        branches={
            "main": "main",
            "dev/m9-sdlc": "base",
            "enhancement/254-parent": "parent",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
        checks="passing",
    )
    data["all_pulls"] = [child, parent]
    data["chain_ancestry"]["base...parent"] = True
    decision = derive_status(data)
    assert decision.state == "Ready"
    assert decision.guard == "blocked"
    assert "open stack parent" in decision.reason
    assert "retarget" in decision.next_step


@pytest.mark.parametrize(
    ("parent_base_sha", "parent_ancestry", "reason"),
    [
        ("stale-base", True, "drifted from its live ref"),
        ("base", False, "is not an ancestor"),
    ],
)
def test_stacked_parent_must_be_current_and_contain_its_base(
    parent_base_sha: str, parent_ancestry: bool, reason: str
) -> None:
    """Every parent edge is live and ancestral, not only the top PR edge."""
    child = pull(draft=True, base="enhancement/254-parent", base_sha="parent")
    parent = pull(
        281,
        draft=False,
        base="dev/m9-sdlc",
        base_sha=parent_base_sha,
        head="enhancement/254-parent",
        head_sha="parent",
    )
    data = observation(
        pulls=[child],
        branches={
            "main": "main",
            "dev/m9-sdlc": "base",
            "enhancement/254-parent": "parent",
            "feat/266-path-status": "head",
        },
    )
    data["all_pulls"] = [child, parent]
    data["chain_ancestry"][f"{parent_base_sha}...parent"] = parent_ancestry
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert reason in decision.reason
    assert decision.allowed_actions == ("inspect",)


def test_draft_contract_keeps_incomplete_work_visible_without_closing() -> None:
    """A complete ownership body may retain unchecked Draft work with Refs."""
    current = pull()
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
    )
    data["issue"]["body"] = "- [ ] Finish acceptance"
    decision = derive_status(data)
    assert decision.state == "Draft"
    assert decision.guard == "clear"


def test_draft_contract_requires_every_nonblank_ownership_field() -> None:
    """A Draft without every required handoff field cannot claim ownership."""
    current = pull(body="Refs #266\n\n- Scope: Add status")
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
    )
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "missing or blank" in decision.reason


@pytest.mark.parametrize(
    "link",
    [
        "No Issue link",
        "Refs #999",
        "Refs other/repo#266",
        "Refs #266\nRefs #266",
    ],
)
def test_draft_requires_one_primary_local_issue_reference(link: str) -> None:
    """A valid branch name cannot replace the Draft ownership link."""
    current = pull(body=str(pull()["body"]).replace("Refs #266", link))
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
    )
    decision = derive_status(data)
    assert decision.state == "Draft"
    assert decision.guard == "blocked"
    assert "exactly one primary Issue" in decision.reason


def test_incomplete_draft_must_reference_instead_of_close_the_issue() -> None:
    """A closing keyword cannot hide incomplete Draft or Issue work."""
    current = pull()
    current["body"] = str(current["body"]).replace("Refs #266", "Closes #266")
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
    )
    data["issue"]["body"] = "- [ ] Finish acceptance"
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "incomplete Draft" in decision.reason
    assert "Refs" in decision.next_step


def test_ready_pr_requires_one_primary_closing_reference() -> None:
    """Ready cannot retain the Draft-only Refs linkage."""
    current = pull(draft=False)
    current["body"] = str(current["body"]).replace("Closes #266", "Refs #266")
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
        checks="passing",
    )
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "one closing reference" in decision.reason


def test_ready_quota_path_requires_the_self_merge_marker() -> None:
    """Status cannot offer merge-quota when its writer would reject it."""
    current = pull(draft=False)
    current["body"] = str(current["body"]).replace(
        "\n\nAlpha 自行合併 / self-merged", ""
    )
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
        checks="quota-blocked",
        blocked_run_urls=["https://github.com/owner/repo/actions/runs/42"],
        quota_note=True,
        capability="allowed",
    )
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "self-merge note" in decision.reason
    assert "merge-quota" not in decision.next_step


@pytest.mark.parametrize("checks", ["passing", "quota-blocked"])
def test_ready_and_quota_paths_reject_a_foreign_repository_closer(
    checks: str,
) -> None:
    """A same-number cross-repository closer cannot satisfy this Issue."""
    current = pull(draft=False)
    current["body"] = str(current["body"]).replace(
        "Closes #266", "Closes other/repo#266"
    )
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
        checks=checks,
        capability="allowed",
        blocked_run_urls=["https://github.com/owner/repo/actions/runs/42"],
        quota_note=True,
    )
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "mismatched closing references" in decision.reason


@pytest.mark.parametrize(
    "secondary",
    [
        "Close #999",
        "Closed #999",
        "Fix #999",
        "Fixed #999",
        "Resolve #999",
        "Resolved #999",
        "Fixes https://github.com/owner/repo/issues/999",
    ],
)
def test_every_github_closing_form_rejects_a_secondary_issue(
    secondary: str,
) -> None:
    """GitHub closing syntax cannot bypass the one-Issue ownership rule."""
    current = pull(draft=False)
    current["body"] += f"\n\n{secondary}"
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
        checks="passing",
    )
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "multiple or mismatched" in decision.reason


@pytest.mark.parametrize("cycle", [False, True])
def test_broken_or_cyclic_stacked_pr_chain_fails_closed(cycle: bool) -> None:
    """A stack cannot stop early, fan out, or loop around the target."""
    child = pull(draft=True, base="stack/parent", base_sha="parent")
    parents = []
    if cycle:
        parents = [
            pull(
                281,
                base="feat/266-path-status",
                head="stack/parent",
                head_sha="parent",
            )
        ]
    data = observation(
        pulls=[child],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "stack/parent": "parent",
            "feat/266-path-status": "head",
        },
    )
    data["all_pulls"] = [child, *parents]
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "chain" in decision.reason or "parent PRs" in decision.reason
    assert decision.allowed_actions == ("inspect",)


def test_routine_quota_block_points_to_existing_exact_note_command() -> None:
    """Routine zero-step blocks reuse #254 without a new approval ceremony."""
    run = "https://github.com/owner/repo/actions/runs/42"
    data = observation(
        pulls=[pull(draft=False)],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
        checks="quota-blocked",
        blocked_run_urls=[run],
    )
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert decision.risk["class"] == "routine"
    assert decision.observed_evidence["blocked_run_urls"] == [run]
    assert "note-quota-fallback" in decision.next_step
    assert run in decision.next_step
    assert "authorization" not in decision.next_step


def test_exact_quota_note_allows_only_the_guarded_merge_path() -> None:
    """One exact #254 note removes repetition but not the #240 lease."""
    run = "https://github.com/owner/repo/actions/runs/42"
    data = observation(
        pulls=[pull(draft=False)],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
        checks="quota-blocked",
        blocked_run_urls=[run],
        quota_note=True,
        capability="allowed",
        human_approval=True,
    )
    decision = derive_status(data)
    assert decision.guard == "clear"
    assert decision.allowed_actions == ("acquire-lease",)
    assert "note-quota-fallback" not in decision.next_step
    assert "merge-quota" in decision.next_step

    data["capability"]["state"] = "unknown"
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert decision.allowed_actions == ("inspect",)

    data["capability"]["lease_status"] = {"state": "available"}
    data["capability"]["quota_fallback"] = True
    decision = derive_status(data)
    assert decision.guard == "clear"
    assert "merge-quota" in decision.next_step

    data["capability"]["state"] = "blocked"
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "merge-quota" not in decision.next_step


def test_quota_note_must_match_repo_pr_head_runs_and_verification() -> None:
    """A stale or partial note cannot authorize the routine fallback."""
    run = "https://github.com/owner/repo/actions/runs/42"
    comment = {
        "user": {"login": "author", "type": "User"},
        "body": quota_fallback_note(
            "owner/repo",
            300,
            "head",
            [run],
            "./scripts/verify-template.sh",
            ["hosted runner identity"],
        ),
    }
    assert has_exact_quota_note(
        [comment], "owner/repo", 300, "head", [run], "author"
    )
    assert not has_exact_quota_note(
        [comment, comment], "owner/repo", 300, "head", [run], "author"
    )
    assert not has_exact_quota_note(
        [comment], "owner/repo", 300, "new-head", [run], "author"
    )
    assert not has_exact_quota_note(
        [comment], "owner/repo", 300, "head", [run], "attacker"
    )
    stale = {
        **comment,
        "body": quota_fallback_note(
            "owner/repo",
            300,
            "old-head",
            [run],
            "./scripts/verify-template.sh",
            ["hosted runner identity"],
        ),
    }
    untrusted = {
        **comment,
        "user": {"login": "attacker", "type": "User"},
    }
    assert has_exact_quota_note(
        [stale, untrusted, comment],
        "owner/repo",
        300,
        "head",
        [run],
        "author",
    )
    wrong_runs = {
        **comment,
        "body": quota_fallback_note(
            "owner/repo",
            300,
            "head",
            ["https://github.com/owner/repo/actions/runs/99"],
            "./scripts/verify-template.sh",
            ["hosted runner identity"],
        ),
    }
    assert not has_exact_quota_note(
        [comment, wrong_runs], "owner/repo", 300, "head", [run], "author"
    )
    old = {**comment, "created_at": "2026-08-25T01:00:00Z"}
    current = {**comment, "created_at": "2026-08-25T03:00:00Z"}
    boundary = datetime(2026, 8, 25, 2, 0, tzinfo=UTC)
    assert not has_exact_quota_note(
        [old], "owner/repo", 300, "head", [run], "author", boundary
    )
    assert has_exact_quota_note(
        [old, current],
        "owner/repo",
        300,
        "head",
        [run],
        "author",
        boundary,
    )


def test_elevated_and_main_routes_require_human_approval() -> None:
    """Automation cannot authorize its own elevated or main-bound merge."""
    elevated = observation(
        pulls=[pull(draft=False)],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
        files=[".github/workflows/ci.yml"],
        checks="passing",
    )
    decision = derive_status(elevated)
    assert decision.guard == "blocked"
    assert "independent human approval" in decision.reason
    assert "merge-once" not in decision.allowed_actions

    hotfix = pull(
        draft=False,
        base="main",
        base_sha="main",
        head="fix/266-outage",
    )
    promoted = observation(
        milestone=None,
        issue_labels=["hotfix"],
        pulls=[hotfix],
        branches={"main": "main", "fix/266-outage": "head"},
        files=["src/fix.py"],
        checks="passing",
    )
    decision = derive_status(promoted)
    assert decision.guard == "blocked"
    assert "human approval" in decision.reason


def test_promotion_quota_keeps_the_two_party_fallback() -> None:
    """A main-bound zero-step block never becomes a routine-note merge."""
    current = pull(
        draft=False,
        base="main",
        base_sha="main",
        head="fix/266-outage",
    )
    data = observation(
        milestone=None,
        issue_labels=["hotfix"],
        pulls=[current],
        branches={"main": "main", "fix/266-outage": "head"},
        files=["src/fix.py"],
        checks="quota-blocked",
        blocked_run_urls=["https://github.com/owner/repo/actions/runs/42"],
        human_approval=True,
    )
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "routine quota note" in decision.reason
    assert "attestation" in decision.next_step
    assert "human authorization" in decision.next_step
    assert "merge-once" not in decision.allowed_actions


def test_only_current_independent_maintainer_review_is_authority() -> None:
    """Bot, author, outsider, and superseded approvals are not authority."""
    reviews = [
        {
            "state": "APPROVED",
            "submitted_at": "2026-08-25T01:00:00Z",
            "author_association": "OWNER",
            "user": {"login": "author", "type": "User"},
        },
        {
            "state": "APPROVED",
            "submitted_at": "2026-08-25T02:00:00Z",
            "author_association": "MEMBER",
            "user": {"login": "review-bot", "type": "Bot"},
        },
        {
            "state": "APPROVED",
            "submitted_at": "2026-08-25T03:00:00Z",
            "author_association": "NONE",
            "user": {"login": "visitor", "type": "User"},
        },
    ]
    assert not has_human_approval(reviews, "author", "head")
    reviews.append(
        {
            "state": "APPROVED",
            "submitted_at": "2026-08-25T04:00:00Z",
            "author_association": "MEMBER",
            "user": {"login": "maintainer", "type": "User"},
            "commit_id": "stale",
        }
    )
    assert not has_human_approval(reviews, "author", "head")
    reviews[-1]["commit_id"] = "head"
    assert has_human_approval(reviews, "author", "head")
    reviews.append(
        {
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2026-08-25T05:00:00Z",
            "author_association": "MEMBER",
            "user": {"login": "maintainer", "type": "User"},
            "commit_id": "head",
        }
    )
    assert not has_human_approval(reviews, "author", "head")


def test_missing_delivery_branch_has_one_repair_step() -> None:
    """Missing policy refs are not guessed or treated as completed."""
    decision = derive_status(observation(branches={"main": "main"}))
    assert decision.guard == "blocked"
    assert "found 0" in decision.reason
    assert "exactly one" in decision.next_step


def test_merged_pr_on_the_wrong_route_never_claims_integration() -> None:
    """A merged timestamp alone is not delivery evidence."""
    merged = pull(
        draft=False,
        base="dev/next",
        state="closed",
        merged_at="2026-08-25T02:00:00Z",
        merge_commit_sha="merge",
    )
    data = observation(pulls=[merged])
    data["merged_routes"] = {
        "300": {
            "valid": False,
            "reason": "Merged PR base dev/next has 0 merged parent PRs",
            "chain": ["feat/266-path-status"],
        }
    }
    decision = derive_status(data)
    assert decision.state == "Candidate"
    assert decision.guard == "blocked"
    assert "0 merged parent PRs" in decision.reason


def test_integrated_issue_has_one_auditable_close_action() -> None:
    """A non-default merge retains its lease until the Issue is closed."""
    merged = pull(
        draft=False,
        state="closed",
        merged_at="2026-08-25T02:00:00Z",
        merge_commit_sha="merge",
    )
    data = observation(pulls=[merged])
    data["issue"]["state"] = "open"
    data["merged_routes"] = {
        "300": {
            "valid": True,
            "reason": "Merged PR chain reaches the expected integration branch",
            "chain": ["feat/266-path-status", "dev/m9-sdlc"],
            "terminal_merge_sha": "merge",
            "containment": [],
        }
    }
    data["merged_lease_status"] = {
        "state": "held",
        "holder": {"owner": "task/merge"},
    }
    decision = derive_status(data)
    assert decision.state == "Integrated"
    assert decision.guard == "blocked"
    assert decision.allowed_actions == ("close-issue",)
    assert "pr_lifecycle.py close-issue" in decision.next_step
    assert "retained merge lease" in decision.next_step


@pytest.mark.parametrize("issue_state", ["open", "closed"])
def test_integrated_issue_does_not_offer_an_unusable_close_action(
    issue_state: str,
) -> None:
    """Only the current retained lease holder can run close-issue."""
    merged = pull(
        draft=False,
        state="closed",
        merged_at="2026-08-25T02:00:00Z",
        merge_commit_sha="merge",
    )
    data = observation(pulls=[merged])
    data["issue"]["state"] = issue_state
    data["merged_routes"] = {
        "300": {
            "valid": True,
            "reason": "Merged PR chain reaches the expected integration branch",
            "chain": ["feat/266-path-status", "dev/m9-sdlc"],
            "terminal_merge_sha": "merge",
            "containment": [],
        }
    }
    data["merged_lease_status"] = {
        "state": "blocked",
        "reason": "retained merge lease is expired",
    }
    decision = derive_status(data)
    assert decision.allowed_actions == ("inspect",)
    assert "close-issue" not in decision.next_step
    assert decision.guard == "blocked"
    assert "cannot be used safely" in decision.reason


def test_live_promotion_collects_containment_and_post_merge_evidence(  # noqa: C901
) -> None:
    """Delivered needs route containment and exact-merge verification."""
    merged = pull(
        draft=False,
        base="main",
        base_sha="old-main",
        head="dev/m9-sdlc",
        head_sha="delivery-head",
        state="closed",
        merged_at="2026-08-25T02:00:00Z",
        merge_commit_sha="merge",
    )

    class FakeGitHub:
        def __init__(
            self,
            app_id: int = 15368,
            workflow_path: str = ".github/workflows/promotion-post-merge.yml",
        ) -> None:
            self.app_id = app_id
            self.workflow_path = workflow_path

        def get(self, _repo: str, path: str = "") -> object:
            if not path:
                return {"permissions": {"push": True}}
            if path == "issues/266":
                return {
                    "number": 266,
                    "state": "closed",
                    "body": "All acceptance tasks are complete.",
                    "labels": [{"name": "promotion"}],
                    "milestone": {"number": 9},
                }
            if path == "compare/merge...main-head":
                return {"status": "ahead"}
            if path == "actions/runs/77":
                return {
                    "id": 77,
                    "name": "Promotion post-merge",
                    "path": self.workflow_path,
                    "event": "push",
                    "head_branch": "main",
                    "head_sha": "merge",
                    "status": "completed",
                    "conclusion": "success",
                    "check_suite_id": 88,
                    "html_url": "https://github.com/owner/repo/actions/runs/77",
                    "repository": {"full_name": "owner/repo"},
                    "head_repository": {"full_name": "owner/repo"},
                }
            raise AssertionError(path)

        def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
            if path.startswith("branches?"):
                return [
                    {"name": "main", "commit": {"sha": "main-head"}},
                    {
                        "name": "dev/m9-sdlc",
                        "commit": {"sha": "delivery-head"},
                    },
                ]
            if path.startswith("pulls?state=all"):
                return [merged]
            if path.startswith("issues/266/timeline"):
                return []
            raise AssertionError(path)

        def keyed(
            self, _repo: str, path: str, key: str
        ) -> list[dict[str, Any]]:
            assert path.startswith("commits/merge/check-runs")
            assert key == "check_runs"
            return [
                {
                    "name": "verify promoted main",
                    "head_sha": "merge",
                    "status": "completed",
                    "conclusion": "success",
                    "app": {
                        "id": self.app_id,
                        "slug": "github-actions",
                    },
                    "check_suite": {"id": 88},
                    "details_url": (
                        "https://github.com/owner/repo/actions/runs/77/job/99"
                    ),
                }
            ]

    decision = inspect_issue(FakeGitHub(), "owner/repo", 266, "delivery")
    assert decision.state == "Delivered"
    assert decision.guard == "clear"
    assert decision.observed_evidence["post_merge_verified"] is True
    assert decision.observed_evidence["base_chain"] == [
        "dev/m9-sdlc",
        "main",
    ]
    assert decision.observed_evidence["merged_route"] == {
        "valid": True,
        "chain": ["dev/m9-sdlc", "main"],
        "reason": "Merged PR chain reaches the expected integration branch",
        "terminal_merge_sha": "merge",
        "containment": [],
    }

    for spoofed_source in (
        FakeGitHub(999),
        FakeGitHub(workflow_path=".github/workflows/rogue.yml"),
    ):
        spoofed = inspect_issue(spoofed_source, "owner/repo", 266, "delivery")
        assert spoofed.state == "Candidate"
        assert spoofed.guard == "blocked"
        assert "post-merge tree evidence" in spoofed.reason


def test_live_merged_stack_proves_child_and_terminal_containment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stacked child is integrated only when each merge is contained."""
    child = pull(
        draft=False,
        base="stack/parent",
        base_sha="parent-old",
        state="closed",
        merged_at="2026-08-25T01:00:00Z",
        merge_commit_sha="child-merge",
    )
    parent = pull(
        281,
        draft=False,
        base="dev/m9-sdlc",
        base_sha="delivery-old",
        head="stack/parent",
        head_sha="parent-head",
        body="Refs #254",
        state="closed",
        merged_at="2026-08-25T02:00:00Z",
        merge_commit_sha="parent-merge",
    )
    monkeypatch.setitem(
        inspect_issue.__globals__,
        "require_base_lifecycle_interface",
        lambda *_: None,
    )
    monkeypatch.setitem(
        inspect_issue.__globals__,
        "merged_lease_status_snapshot",
        lambda *_: {"state": "available", "reason": "no retained lease"},
    )

    class FakeGitHub:
        def __init__(self, failed: str | None = None) -> None:
            self.comparisons: list[str] = []
            self.failed = failed

        def get(self, _repo: str, path: str = "") -> object:
            if not path:
                return {"permissions": {"push": True}}
            if path == "issues/266":
                return {
                    "number": 266,
                    "state": "closed",
                    "body": "All acceptance tasks are complete.",
                    "labels": [],
                    "milestone": {"number": 9},
                }
            if path.startswith("compare/"):
                self.comparisons.append(path)
                return {
                    "status": "diverged" if path == self.failed else "ahead"
                }
            raise AssertionError(path)

        def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
            if path.startswith("branches?"):
                return [
                    {"name": "main", "commit": {"sha": "main"}},
                    {
                        "name": "dev/m9-sdlc",
                        "commit": {"sha": "delivery-head"},
                    },
                ]
            if path.startswith("pulls?state=all"):
                return [child, parent]
            if path.startswith("issues/266/timeline"):
                return []
            raise AssertionError(path)

    github = FakeGitHub()
    decision = inspect_issue(github, "owner/repo", 266, "delivery")
    assert decision.state == "Integrated"
    assert decision.guard == "clear"
    assert github.comparisons == [
        "compare/child-merge...parent-head",
        "compare/parent-merge...delivery-head",
    ]

    failed = inspect_issue(
        FakeGitHub("compare/child-merge...parent-head"),
        "owner/repo",
        266,
        "delivery",
    )
    assert failed.state == "Candidate"
    assert failed.guard == "blocked"
    assert "child-merge is not contained" in failed.reason


def test_base_or_head_drift_invalidates_ready_state() -> None:
    """A current check result cannot authorize a stale candidate."""
    current = pull(draft=False)
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
        checks="passing",
        base_current=False,
    )
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "base snapshot drifted" in decision.reason
    assert "Sync dev/m9-sdlc" in decision.next_step

    current["head"]["sha"] = "stale"
    data["base_current"] = True
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "head differs" in decision.reason


@pytest.mark.parametrize("location", ["issue", "pull"])
def test_unchecked_acceptance_blocks_ready_without_policy_check(
    location: str,
) -> None:
    """Live unchecked work blocks merge even if every check says success."""
    current = pull(draft=False)
    data = observation(
        pulls=[current],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
        checks="passing",
    )
    if location == "issue":
        data["issue"]["body"] = "- [ ] still required"
    else:
        current["body"] += "\n\n- [ ] still required"
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "unchecked work" in decision.reason
    assert "merge-once" not in decision.allowed_actions


def test_newer_blocker_survives_older_resolution() -> None:
    """Only a resolution newer than the latest blocker clears the guard."""
    comments = [
        {
            "body": "Merge blocker resolved: old",
            "created_at": "2026-08-25T01:00:00Z",
            "author_association": "MEMBER",
        },
        {
            "body": "[merge-blocker] new",
            "created_at": "2026-08-25T02:00:00Z",
            "author_association": "OWNER",
            "html_url": "https://github.com/owner/repo/pull/300#issuecomment-1",
        },
    ]
    blocker = unresolved_blocker(comments, [])
    data = observation(
        pulls=[pull(draft=False)],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
        checks="passing",
        blocker=blocker,
    )
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert "issuecomment-1" in decision.reason


def test_unknown_single_writer_capability_never_allows_merge() -> None:
    """Missing #240 capability evidence keeps the merge human-only."""
    data = observation(
        pulls=[pull(draft=False)],
        branches={
            "main": "main",
            "dev/next": "next",
            "dev/m9-sdlc": "base",
            "feat/266-path-status": "head",
        },
        files=["src/status.py"],
        checks="passing",
        capability="unknown",
        human_approval=True,
    )
    decision = derive_status(data)
    assert decision.guard == "blocked"
    assert decision.allowed_actions == ("inspect",)
    assert "human-only" in decision.next_step


def test_required_check_keeps_its_github_app_identity() -> None:
    """A same-named check from another App cannot satisfy a protected rule."""
    runs = [
        {
            "name": "verify",
            "status": "completed",
            "conclusion": "success",
            "app": {"id": 2},
        }
    ]
    assert check_state(runs, [], {("verify", 1)}) == "failed"
    assert check_state(runs, [], {("verify", 2)}) == "passing"


def test_capability_composes_canonical_protection_and_available_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the canonical interface and enforceable controls allow acquire."""

    class FakeGitHub:
        def get(self, _repo: str, path: str = "") -> object:
            if path.startswith("contents/scripts/"):
                source = path.split("?", 1)[0].removeprefix("contents/")
                return lifecycle_content(path=source)
            raise AssertionError(path)

    monkeypatch.setitem(
        inspect_capability.__globals__,
        "effective_protection",
        lambda *_: ("enforced", "protected", {("verify", 7)}),
    )
    monkeypatch.setitem(
        inspect_capability.__globals__,
        "lease_status_snapshot",
        lambda *_: {"state": "available", "reason": "atomic acquire"},
    )
    capability = inspect_capability(
        FakeGitHub(),
        "owner/repo",
        {"permissions": {"push": True}},
        pull(draft=False, head_sha="a" * 40),
        "b" * 40,
    )
    assert capability["state"] == "allowed"
    assert capability["required"] == [
        {"context": "verify", "integration_id": 7}
    ]


def test_capability_blocks_when_canonical_lease_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live lease keeps another status caller read-only."""

    class FakeGitHub:
        def get(self, _repo: str, _path: str = "") -> object:
            source = _path.split("?", 1)[0].removeprefix("contents/")
            return lifecycle_content(path=source)

    monkeypatch.setitem(
        inspect_capability.__globals__,
        "effective_protection",
        lambda *_: ("enforced", "protected", {("verify", None)}),
    )
    monkeypatch.setitem(
        inspect_capability.__globals__,
        "lease_status_snapshot",
        lambda *_: {"state": "held", "reason": "another owner holds it"},
    )
    capability = inspect_capability(
        FakeGitHub(),
        "owner/repo",
        {"permissions": {"push": True}},
        pull(draft=False, head_sha="a" * 40),
        "b" * 40,
    )
    assert capability["state"] == "blocked"
    assert capability["lease_status"] == {
        "state": "held",
        "reason": "another owner holds it",
    }


def test_capability_still_reports_lease_when_protection_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routine quota can use its lease while ordinary merge stays unknown."""

    class FakeGitHub:
        def get(self, _repo: str, _path: str = "") -> object:
            source = _path.split("?", 1)[0].removeprefix("contents/")
            return lifecycle_content(path=source)

    monkeypatch.setitem(
        inspect_capability.__globals__,
        "effective_protection",
        lambda *_: ("unknown", "GitHub rules API returned 403", set()),
    )
    monkeypatch.setitem(
        inspect_capability.__globals__,
        "lease_status_snapshot",
        lambda *_: {"state": "available", "reason": "atomic acquire"},
    )
    capability = inspect_capability(
        FakeGitHub(),
        "owner/repo",
        {"permissions": {"push": True}},
        pull(draft=False, head_sha="a" * 40),
        "b" * 40,
    )
    assert capability["state"] == "unknown"
    assert capability["lease_status"] == {
        "state": "available",
        "reason": "atomic acquire",
    }
    assert capability["quota_fallback"] is True


def test_unrelated_unknown_protection_cannot_use_the_quota_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the documented private-plan 403 can use quota-only capability."""

    class FakeGitHub:
        def get(self, _repo: str, path: str = "") -> object:
            source = path.split("?", 1)[0].removeprefix("contents/")
            return lifecycle_content(path=source)

    monkeypatch.setitem(
        inspect_capability.__globals__,
        "effective_protection",
        lambda *_: ("unknown", "malformed rules response", set()),
    )
    monkeypatch.setitem(
        inspect_capability.__globals__,
        "lease_status_snapshot",
        lambda *_: {"state": "available", "reason": "atomic acquire"},
    )
    capability = inspect_capability(
        FakeGitHub(),
        "owner/repo",
        {"permissions": {"push": True}},
        pull(draft=False, head_sha="a" * 40),
        "b" * 40,
    )
    assert capability["state"] == "unknown"
    assert capability["quota_fallback"] is False


@pytest.mark.parametrize(
    "tampered_name",
    [
        "pr_lifecycle.py",
        "ci_tier.py",
        "promotion_gate.py",
        "issue_path_status.py",
    ],
)
def test_capability_rejects_a_modified_policy_helper(
    tampered_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A work branch cannot replace any dependency used by the writer."""

    class FakeGitHub:
        def get(self, _repo: str, path: str = "") -> object:
            source = path.split("?", 1)[0].removeprefix("contents/")
            content = (SCRIPTS / Path(source).name).read_bytes()
            if Path(source).name == tampered_name:
                content += b"\n# changed\n"
            return lifecycle_content(content, source)

    called = False

    def unexpected(*_args: object) -> object:
        nonlocal called
        called = True
        return None

    monkeypatch.setitem(
        inspect_capability.__globals__, "effective_protection", unexpected
    )
    monkeypatch.setitem(
        inspect_capability.__globals__, "lease_status_snapshot", unexpected
    )
    capability = inspect_capability(
        FakeGitHub(),
        "owner/repo",
        {"permissions": {"push": True}},
        pull(draft=False, head_sha="a" * 40),
        "b" * 40,
    )
    assert capability["state"] == "unknown"
    assert "base blob" in str(capability["reason"])
    assert not called


def test_capability_trusts_terminal_policy_base_not_a_stack_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mutable parent cannot replace the terminal branch's lifecycle code."""

    class FakeGitHub:
        def get(self, _repo: str, path: str = "") -> object:
            source = path.split("?", 1)[0].removeprefix("contents/")
            local = (SCRIPTS / Path(source).name).read_bytes()
            if path.endswith("ref=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"):
                return lifecycle_content(
                    local + b"\n# stale terminal\n", source
                )
            if path.endswith("ref=cccccccccccccccccccccccccccccccccccccccc"):
                return lifecycle_content(local, source)
            raise AssertionError(path)

    called = False

    def unexpected(*_args: object) -> object:
        nonlocal called
        called = True
        return None

    monkeypatch.setitem(
        inspect_capability.__globals__, "effective_protection", unexpected
    )
    monkeypatch.setitem(
        inspect_capability.__globals__, "lease_status_snapshot", unexpected
    )
    capability = inspect_capability(
        FakeGitHub(),
        "owner/repo",
        {"permissions": {"push": True}},
        pull(draft=False, base_sha="c" * 40, head_sha="a" * 40),
        "b" * 40,
    )
    assert capability["state"] == "unknown"
    assert "base blob" in str(capability["reason"])
    assert not called


def test_missing_push_permission_is_unknown() -> None:
    """An omitted permission field cannot be treated as capability."""
    capability = inspect_capability(
        SimpleNamespace(), "owner/repo", {}, pull(draft=False), "b" * 40
    )
    assert capability["state"] == "unknown"


def test_github_adapter_uses_only_explicit_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The status entrypoint cannot write GitHub state."""
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setitem(
        GitHub._read.__globals__["shutil"].__dict__,
        "which",
        lambda _name: "/usr/bin/gh",
    )
    monkeypatch.setitem(
        GitHub._read.__globals__["subprocess"].__dict__, "run", fake_run
    )
    assert GitHub().get("owner/repo") == {}
    assert calls == [
        ["/usr/bin/gh", "api", "--method", "GET", "repos/owner/repo"]
    ]
