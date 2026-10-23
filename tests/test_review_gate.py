"""Tests for the Copilot-or-maintainer `review` required check (#752)."""

from __future__ import annotations

import importlib
import io
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import settings_support
import yaml
from copier import run_copy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

review_gate = importlib.import_module("review_gate")
pr_lifecycle = importlib.import_module("pr_lifecycle")

HEAD = "a" * 40
CLEAN = "Copilot reviewed 2 out of 2 changed files and generated no comments."


def copilot(commit: str = HEAD, body: str = CLEAN) -> dict[str, Any]:
    """Return one Copilot review fixture."""
    return {
        "id": 9,
        "user": {"login": "copilot-pull-request-reviewer[bot]", "type": "Bot"},
        "author_association": "NONE",
        "state": "COMMENTED",
        "submitted_at": "2026-09-18T01:00:00Z",
        "commit_id": commit,
        "body": body,
        "html_url": "https://github.com/o/r/pull/7#pullrequestreview-9",
    }


def approval(login: str, commit: str = HEAD) -> dict[str, Any]:
    """Return one maintainer approval fixture."""
    return {
        "id": 10,
        "user": {"login": login, "type": "User"},
        "author_association": "MEMBER",
        "state": "APPROVED",
        "submitted_at": "2026-09-18T02:00:00Z",
        "commit_id": commit,
        "html_url": "https://github.com/o/r/pull/7#pullrequestreview-10",
    }


def push(
    login: str,
    after: str = HEAD,
    at: str = "2026-09-18T01:30:00Z",
    kind: str = "push",
) -> dict[str, Any]:
    """Return one branch activity fixture (#1211)."""
    return {
        "after": after,
        "ref": "refs/heads/fix/42-lifecycle",
        "timestamp": at,
        "activity_type": kind,
        "actor": {"login": login, "type": "User"},
    }


class FakeGitHub:
    """Serve one pull request, its reviews, and Copilot's comments."""

    def __init__(self, reviews: list[dict[str, Any]]) -> None:
        self.reviews = reviews
        self.inline: list[dict[str, Any]] = []
        self.draft = False
        self.body = ""
        self.base_ref = "main"
        self.base_sha = "b" * 40
        self.default_branch = "main"
        self.destination_sha = "f" * 40
        self.head_ref = "fix/42-lifecycle"
        self.title = "fix: lifecycle"
        self.head_repo: str | None = "o/r"
        self.issue_state = "open"
        self.issue_milestone: int | None = None
        self.issue_comments: list[dict[str, Any]] = []
        self.hotfix_comments: list[dict[str, Any]] = []
        self.labels: set[str] = set()
        self.permission = "maintain"
        self.role_name: str | None = None
        # Ruleset shape A/E1 by default; 1 approval models shape C.
        self.required_approvals: object = 0
        # Issue #1211: who committed and last pushed the exact head.
        self.head_committer: str | None = "agent"
        self.head_pushes: list[dict[str, Any]] | None = [push("agent")]

    def get(self, repo: str, path: str) -> object:  # noqa: C901
        """Return one REST fixture."""
        if path.startswith("rules/branches/"):
            if self.required_approvals is None:
                raise RuntimeError("Upgrade to GitHub Pro")
            return [
                {
                    "type": "pull_request",
                    "parameters": {
                        "required_approving_review_count": (
                            self.required_approvals
                        ),
                        "dismiss_stale_reviews_on_push": True,
                        "require_last_push_approval": True,
                        "required_review_thread_resolution": True,
                    },
                }
            ]
        if path == "pulls/7":
            return {
                "draft": self.draft,
                "title": self.title,
                "body": self.body,
                "base": {"ref": self.base_ref, "sha": self.base_sha},
                "head": {
                    "ref": self.head_ref,
                    "sha": HEAD,
                    "repo": (
                        {"full_name": self.head_repo}
                        if self.head_repo is not None
                        else None
                    ),
                },
                "user": {"login": "author"},
                "labels": [{"name": label} for label in sorted(self.labels)],
            }
        if path == "":
            return {"default_branch": self.default_branch}
        if path == "git/ref/heads/main":
            return {"object": {"sha": self.destination_sha}}
        if path == f"compare/{self.destination_sha}...{HEAD}":
            return {"status": "ahead"}
        if path == f"git/commits/{HEAD}":
            return {
                "parents": [
                    {"sha": self.base_sha},
                    {"sha": self.destination_sha},
                ]
            }
        if path == "issues/42":
            return {
                "number": 42,
                "pull_request": None,
                "state": self.issue_state,
                "milestone": (
                    {"number": self.issue_milestone}
                    if self.issue_milestone is not None
                    else None
                ),
                "labels": [{"name": label} for label in sorted(self.labels)],
                "user": {"login": "author", "type": "User"},
            }
        if path == "milestones/7":
            return {"number": 7, "title": "Delivery"}
        if path == f"commits/{HEAD}":
            return {
                "sha": HEAD,
                "committer": (
                    {"login": self.head_committer}
                    if self.head_committer is not None
                    else None
                ),
            }
        if path.startswith("activity?ref="):
            if self.head_pushes is None:
                raise RuntimeError("HTTP 403: Resource not accessible")
            assert repo == self.head_repo
            assert path == (
                "activity?ref=refs%2Fheads%2F"
                + self.head_ref.replace("/", "%2F")
                + "&per_page=100"
            )
            return self.head_pushes
        match = re.fullmatch(r"collaborators/([^/]+)/permission", path)
        if match:
            response: dict[str, object] = {
                "permission": self.permission,
                "role_name": (
                    self.permission
                    if self.role_name is None
                    else self.role_name
                ),
                "user": {"login": match.group(1)},
            }
            if self.role_name == "missing":
                del response["role_name"]
            return response
        raise AssertionError(path)

    def pages(self, repo: str, path: str) -> list[dict[str, Any]]:
        """Return one collection fixture."""
        if path.startswith("pulls/7/reviews/9/comments"):
            return self.inline
        if path.startswith("pulls/7/reviews"):
            return self.reviews
        if path.startswith("issues/7/comments"):
            return self.issue_comments
        if path.startswith("issues/42/comments"):
            return self.hotfix_comments
        if path.startswith("issues?milestone=7"):
            return [
                {
                    "number": 70,
                    "title": "Milestone 7: Delivery",
                    "body": "",
                    "user": {"login": "author", "type": "User"},
                }
            ]
        raise AssertionError(path)


def config(tmp_path: Path, text: str) -> Path:
    """Write one complete schema 2 settings file and return its path."""
    return settings_support.write_settings(tmp_path / "config.yml", text)


@pytest.fixture
def copilot_config(tmp_path: Path) -> Path:
    """Return a Copilot-mode answers file."""
    return config(
        tmp_path,
        "copilot_review: allowed\nadmin_bypass: always\n",
    )


def test_legacy_settings_fail_closed_instead_of_human_mode(
    tmp_path: Path,
) -> None:
    """A legacy answers file is migrated by the CLI, never guessed here."""
    path = tmp_path / "config.yml"
    path.write_text("languages: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="legacy settings schema"):
        review_gate.review_settings(path)
    assert review_gate.review_settings(tmp_path / "absent.yml") == "human"


def test_invalid_review_mode_is_rejected(tmp_path: Path) -> None:
    """The flat config validator owns the allowed values."""
    with pytest.raises(ValueError, match="copilot_review"):
        review_gate.review_settings(config(tmp_path, "copilot_review: bot\n"))


def test_human_mode_requires_exact_head_approval(tmp_path: Path) -> None:
    """The level-aware check enforces peer review in human mode too."""
    result = review_gate.evaluate(
        FakeGitHub([]),
        "o/r",
        7,
        config(tmp_path, "copilot_review: off\nadmin_bypass: off\n"),
    )
    assert not result["passed"]
    assert result["state"] == "pending"
    assert result["release_level"] == "stable"
    assert "independent maintainer" in result["reason"]

    approved = review_gate.evaluate(
        FakeGitHub([approval("maintainer")]),
        "o/r",
        7,
        config(tmp_path, "copilot_review: off\nadmin_bypass: off\n"),
    )
    assert approved["passed"]
    assert approved["state"] == "success"
    assert approved["source"] == "maintainer"


def test_beta_hotfix_admin_authorization_passes_for_exact_head(
    tmp_path: Path,
) -> None:
    """The peer-review gate recognizes only the audited hotfix exception."""
    github = FakeGitHub([])
    github.body = "Fixes #42"
    github.labels = {"bug", "hotfix"}
    github.permission = "admin"
    github.issue_comments = [
        {
            "body": pr_lifecycle.authorization_statement("o/r", 7, HEAD),
            "user": {"login": "author", "type": "User"},
            "author_association": "OWNER",
            "created_at": "2026-09-18T03:00:00Z",
            "html_url": "https://github.com/o/r/pull/7#issuecomment-7",
        }
    ]
    github.hotfix_comments = [
        {
            "body": "Admin-approve: production outage",
            "user": {"login": "author", "type": "User"},
            "created_at": "2026-09-18T02:00:00Z",
            "html_url": "https://github.com/o/r/issues/42#issuecomment-8",
        }
    ]

    result = review_gate.evaluate(
        github,
        "o/r",
        7,
        config(
            tmp_path,
            "copilot_review: off\nadmin_bypass: off\n",
        ),
    )

    assert result["passed"]
    assert result["state"] == "success"
    assert result["source"] == "hotfix-emergency"
    assert "production outage" in result["reason"]


def test_beta_non_hotfix_cannot_use_admin_authorization(tmp_path: Path) -> None:
    """An exact-head admin comment is not a peer-review bypass by itself."""
    github = FakeGitHub([])
    github.issue_comments = [
        {
            "body": pr_lifecycle.authorization_statement("o/r", 7, HEAD),
            "user": {"login": "author", "type": "User"},
            "author_association": "OWNER",
            "created_at": "2026-09-18T03:00:00Z",
            "html_url": "https://github.com/o/r/pull/7#issuecomment-7",
        }
    ]

    result = review_gate.evaluate(
        github, "o/r", 7, config(tmp_path, "admin_bypass: off\n")
    )

    assert not result["passed"]
    assert "independent maintainer" in result["reason"]


def test_clean_copilot_review_of_head_passes(copilot_config: Path) -> None:
    """A clean exact-head Copilot review passes the check."""
    result = review_gate.evaluate(
        FakeGitHub([copilot()]), "o/r", 7, copilot_config
    )
    assert result["passed"]
    assert result["state"] == "success"
    assert result["source"] == "copilot"


@pytest.mark.parametrize(
    ("reviews", "inline", "reason", "state"),
    [
        ([], [], "not reviewed this pull request", "pending"),
        ([copilot("b" * 40)], [], "not reviewed the current head", "pending"),
        (
            [copilot()],
            [{"path": "x.py", "line": 1, "body": "Bug"}],
            "1 comment",
            "failure",
        ),
        (
            [copilot(body="Comments suppressed (2)")],
            [],
            "suppressed",
            "failure",
        ),
        (
            [copilot(body="Copilot encountered an error.")],
            [],
            "does not state",
            "failure",
        ),
    ],
)
def test_copilot_review_that_is_not_clean_fails(
    copilot_config: Path,
    reviews: list[dict[str, Any]],
    inline: list[dict[str, Any]],
    reason: str,
    state: str,
) -> None:
    """Waiting reviews stay pending; conclusive findings fail closed."""
    github = FakeGitHub(reviews)
    github.inline = inline
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert result["state"] == state
    # Waiting Copilot evidence leaves the human decision unchanged (#1082);
    # the status loop still sees why Copilot is not usable yet.
    assert reason in result["copilot"]["reason"]
    assert "maintainer approval" in result["reason"]


def test_maintainer_approval_passes_without_copilot(
    copilot_config: Path,
) -> None:
    """The human path stays available in Copilot mode."""
    result = review_gate.evaluate(
        FakeGitHub([approval("maintainer")]), "o/r", 7, copilot_config
    )
    assert result["passed"]
    assert result["source"] == "maintainer"


def test_author_self_approval_does_not_count(copilot_config: Path) -> None:
    """The author cannot approve their own head."""
    result = review_gate.evaluate(
        FakeGitHub([approval("author")]), "o/r", 7, copilot_config
    )
    assert not result["passed"]


def test_stale_maintainer_approval_does_not_count(copilot_config: Path) -> None:
    """An approval of an older head no longer applies."""
    result = review_gate.evaluate(
        FakeGitHub([approval("maintainer", "c" * 40)]), "o/r", 7, copilot_config
    )
    assert not result["passed"]


def test_draft_stays_pending_even_with_clean_copilot_review(
    copilot_config: Path,
) -> None:
    """Draft pull requests are not ready to merge."""
    github = FakeGitHub([copilot()])
    github.draft = True
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert result["state"] == "pending"
    assert "Draft" in result["reason"]


@pytest.mark.parametrize(
    ("state", "status", "conclusion"),
    [
        ("pending", "queued", None),
        ("success", "completed", "success"),
        ("failure", "completed", "failure"),
    ],
)
def test_publish_check_preserves_three_states(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    status: str,
    conclusion: str | None,
) -> None:
    """The workflow passes after publishing the authoritative check state."""
    payloads: list[dict[str, Any]] = []

    def fake_run(
        command: list[str],
        *,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        del env
        assert command[-3:] == ["repos/o/r/check-runs", "--input", "-"]
        assert input_text is not None
        payload = json.loads(input_text)
        payloads.append(payload)
        return json.dumps({**payload, "conclusion": payload.get("conclusion")})

    monkeypatch.setattr(pr_lifecycle, "run", fake_run)
    review_gate.publish_check(
        "o/r",
        {"head_sha": HEAD, "state": state, "reason": "review evidence"},
        "https://github.com/o/r/actions/runs/123",
        123,
    )

    assert payloads == [
        {
            "name": "review",
            "head_sha": HEAD,
            "status": status,
            "details_url": "https://github.com/o/r/actions/runs/123",
            "external_id": f"csarc-review:123:{HEAD}",
            "output": {
                "title": (
                    "Review pending"
                    if state == "pending"
                    else "Review decision"
                ),
                "summary": "review evidence",
            },
            **({"conclusion": conclusion} if conclusion is not None else {}),
        }
    ]


def test_copilot_can_satisfy_every_release_level(
    tmp_path: Path,
) -> None:
    """The simplified schema has no separate Copilot release-level cap."""
    allowed = config(
        tmp_path, "copilot_review: allowed\nadmin_bypass: always\n"
    )
    result = review_gate.evaluate(FakeGitHub([copilot()]), "o/r", 7, allowed)
    assert result["passed"]
    assert result["source"] == "copilot"


def test_clean_copilot_can_satisfy_peer_review_mode(
    tmp_path: Path,
) -> None:
    """An explicit Copilot allowance is valid in either human review mode."""
    beta = config(
        tmp_path,
        "copilot_review: allowed\nadmin_bypass: off\n",
    )
    result = review_gate.evaluate(FakeGitHub([copilot()]), "o/r", 7, beta)
    assert result["passed"]
    assert result["required_review"] == "peer"
    assert result["source"] == "copilot"


def test_impersonating_user_is_not_copilot(copilot_config: Path) -> None:
    """Only the Copilot App's bot account counts as Copilot."""
    fake = copilot()
    fake["user"] = {"login": "copilot", "type": "User"}
    result = review_gate.evaluate(FakeGitHub([fake]), "o/r", 7, copilot_config)
    assert not result["passed"]


pr_lifecycle = importlib.import_module("pr_lifecycle")


def alpha_authorization_comment(
    login: str = "maintainer", association: str = "MEMBER"
) -> dict[str, Any]:
    """Return one exact-head Alpha self-merge authorization comment."""
    return {
        "id": 99,
        "html_url": "https://github.com/o/r/pull/7#issuecomment-99",
        "created_at": "2026-09-18T03:00:00Z",
        "author_association": association,
        "user": {"login": login, "type": "User"},
        "body": pr_lifecycle.authorization_statement("o/r", 7, HEAD),
    }


def alpha_github() -> FakeGitHub:
    """Return a Milestone-less, Issue-linked Alpha self-merge candidate."""
    github = FakeGitHub([])
    github.body = f"Closes #42\n\n{pr_lifecycle.ADMIN_BYPASS_MARKER}"
    github.role_name = "admin"
    return github


def alpha_sync_github() -> FakeGitHub:
    """Return an exact current-main delivery sync candidate."""
    github = FakeGitHub([])
    github.base_ref = "dev/m10-release-backed-adoption"
    sync_branch_name = (
        pr_lifecycle.promotion_gate.delivery_sync.sync_branch_name
    )
    github.head_ref = sync_branch_name(github.base_ref, github.destination_sha)
    github.body = pr_lifecycle.ADMIN_BYPASS_MARKER
    github.role_name = "admin"
    return github


def alpha_promotion_github() -> FakeGitHub:
    """Return a recognized Milestone promotion candidate."""
    github = FakeGitHub([])
    github.head_ref = "promote/m12-agent-workflow-contract"
    github.labels = {"enhancement", "promotion"}
    github.body = f"Refs #42\n\n{pr_lifecycle.ADMIN_BYPASS_MARKER}"
    github.role_name = "admin"
    return github


def alpha_release_github() -> FakeGitHub:
    """Return a canonical standalone beta release candidate."""
    github = FakeGitHub([])
    github.head_ref = "release/v0.21.0-beta.1"
    github.title = "chore(main): release 0.21.0-beta.1"
    github.body = f"Refs #42\n\n{pr_lifecycle.ADMIN_BYPASS_MARKER}"
    github.role_name = "admin"
    return github


@pytest.mark.parametrize(
    ("permission", "role_name"),
    [
        # A maintainer is never an admin, even if an older or customized
        # response reports a legacy `admin` permission.
        ("admin", "maintain"),
        ("maintain", "maintain"),
        ("write", "write"),
        # A missing role_name is unknown; the legacy field is not read.
        ("admin", ""),
    ],
)
def test_admin_bypass_requires_the_live_admin_role(
    copilot_config: Path, permission: str, role_name: str
) -> None:
    """Issue #1064 AC5: only a live `role_name: admin` may bypass review."""
    github = alpha_github()
    github.permission = permission
    github.role_name = role_name
    github.issue_comments = [alpha_authorization_comment()]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert result["source"] != "admin-bypass"
    assert "from a live admin" in result["reason"]


def test_admin_bypass_authorization_passes(copilot_config: Path) -> None:
    """Issue #775: a valid exact-head Alpha self-merge comment passes review."""
    github = alpha_github()
    github.issue_comments = [alpha_authorization_comment()]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["passed"]
    assert result["source"] == "admin-bypass"


def test_alpha_sync_self_merge_authorization_passes(
    copilot_config: Path,
) -> None:
    """Issue #826: review and lifecycle share the validated sync route."""
    github = alpha_sync_github()
    github.issue_comments = [alpha_authorization_comment()]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["passed"]
    assert result["source"] == "admin-bypass"


def test_alpha_promotion_self_merge_authorization_passes(
    copilot_config: Path,
) -> None:
    """Issue #905: review and lifecycle share the promotion route."""
    github = alpha_promotion_github()
    github.issue_comments = [alpha_authorization_comment()]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["passed"]
    assert result["source"] == "admin-bypass"


def test_alpha_release_self_merge_authorization_passes(
    copilot_config: Path,
) -> None:
    """Issue #913: review and lifecycle share the release route."""
    github = alpha_release_github()
    github.issue_comments = [alpha_authorization_comment()]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["passed"]
    assert result["source"] == "admin-bypass"


def test_peer_alpha_release_still_requires_an_independent_review(
    tmp_path: Path,
) -> None:
    """The release route does not weaken an explicit peer fallback."""
    github = alpha_release_github()
    github.issue_comments = [alpha_authorization_comment()]
    result = review_gate.evaluate(
        github,
        "o/r",
        7,
        config(
            tmp_path,
            "copilot_review: allowed\nadmin_bypass: off\n",
        ),
    )
    assert not result["passed"]
    assert "independent maintainer" in result["reason"]


def test_alpha_sync_requires_exact_head_authorization(
    copilot_config: Path,
) -> None:
    """A valid sync route cannot use an authorization for another head."""
    github = alpha_sync_github()
    comment = alpha_authorization_comment()
    comment["body"] = pr_lifecycle.authorization_statement("o/r", 7, "c" * 40)
    github.issue_comments = [comment]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert "no exact-head maintainer authorization comment" in result["reason"]


def test_admin_bypass_accepts_a_web_ui_crlf_authorization(
    copilot_config: Path,
) -> None:
    """Issue #991: PR #988's CRLF + trailing-newline comment is found."""
    github = alpha_github()
    comment = alpha_authorization_comment()
    comment["body"] = comment["body"].replace("\n", "\r\n") + "\n"
    github.issue_comments = [comment]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["passed"]
    assert result["source"] == "admin-bypass"


def test_admin_bypass_rejects_a_crlf_authorization_for_another_head(
    copilot_config: Path,
) -> None:
    """Issue #991: a CRLF body for a different head is still ignored."""
    github = alpha_github()
    comment = alpha_authorization_comment()
    comment["body"] = pr_lifecycle.authorization_statement(
        "o/r", 7, "c" * 40
    ).replace("\n", "\r\n")
    github.issue_comments = [comment]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert "no exact-head maintainer authorization comment" in result["reason"]


def test_admin_bypass_ignores_author_association(
    copilot_config: Path,
) -> None:
    """Issue #785: a downgraded association must not block self-merge.

    Confirmed live on PR #782: a restricted `GITHUB_TOKEN` reports a real
    maintainer's comment as `COLLABORATOR` instead of `MEMBER`. The
    `collaborators/{login}/permission` lookup `FakeGitHub.get` returns the
    live `role_name` `admin` for any login here, so this only passes once
    `find_exact_head_authorization` stops filtering on the association.
    """
    github = alpha_github()
    github.issue_comments = [
        alpha_authorization_comment(association="COLLABORATOR")
    ]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["passed"]
    assert result["source"] == "admin-bypass"


def test_admin_bypass_without_authorization_still_fails(
    copilot_config: Path,
) -> None:
    """The marker and route alone are not authorization -- a comment is."""
    github = alpha_github()
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert "Admin bypass" in result["reason"]
    assert "no exact-head maintainer authorization comment" in result["reason"]


def test_admin_bypass_milestone_issue_does_not_apply(
    copilot_config: Path,
) -> None:
    """A Milestone Issue must use its dev/mN branch, not this shortcut.

    Issue #781: the final `reason` must say *why* -- not collapse into the
    same generic Copilot message every other Alpha self-merge rejection
    produces, which is what made PR #779's real failure undiagnosable.
    """
    github = alpha_github()
    github.issue_milestone = 7
    github.issue_comments = [alpha_authorization_comment()]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert "Milestone-less Issue" in result["reason"]


def test_admin_bypass_closed_issue_does_not_apply(
    copilot_config: Path,
) -> None:
    """Issue #781 (PR #779): a closed linked Issue fails with a specific
    reason instead of the generic Copilot message.

    This reproduces PR #779's real failure: the review job checks the Issue
    a Default-branch Alpha self-merge PR closes, and once that Issue is no
    longer open the route is rejected. The rejection must say so, not read
    identically to "Copilot has not reviewed this pull request yet" -- that
    ambiguity is what led to chasing an unrelated, disproven GITHUB_TOKEN
    permission theory instead of the real cause.
    """
    github = alpha_github()
    github.issue_state = "closed"
    github.issue_comments = [alpha_authorization_comment()]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert "Issue is not open" in result["reason"]


def test_admin_bypass_ignores_a_non_maintainer_comment(
    copilot_config: Path,
) -> None:
    """An authorization-shaped comment still needs real maintainer perms."""
    github = alpha_github()
    comment = alpha_authorization_comment("outsider")
    github.issue_comments = [comment]
    original_get = github.get

    def get_without_permission(repo: str, path: str) -> object:
        if path == "collaborators/outsider/permission":
            return {"permission": "read", "user": {"login": "outsider"}}
        return original_get(repo, path)

    github.get = get_without_permission  # ty: ignore[invalid-assignment]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert "no exact-head maintainer authorization comment" in result["reason"]


def test_admin_bypass_collaborator_permission_under_restricted_token(
    copilot_config: Path,
) -> None:
    """Issue #781: the collaborators/permission call works fine in CI.

    PR #779's `bypass-trace` audit comment blamed the `review` job's
    restricted `GITHUB_TOKEN` (`contents: read, pull-requests: read`) for
    being unable to resolve `GET .../collaborators/{user}/permission`. That
    theory was disproven experimentally: three live GitHub Actions runs
    under that exact permission set returned this call's real response
    shape successfully. This locks that response shape in as a fixture so
    nobody "fixes" this by widening `pr-review.yml`'s `permissions:` block.
    """
    github = alpha_github()
    github.issue_comments = [alpha_authorization_comment()]
    real_restricted_token_response = {
        "permission": "admin",
        "user": {
            "login": "maintainer",
            "id": 8596186,
            "type": "User",
            "site_admin": False,
            "permissions": {
                "admin": True,
                "maintain": True,
                "push": True,
                "triage": True,
                "pull": True,
            },
        },
        "role_name": "admin",
    }
    original_get = github.get

    def get_with_real_shape(repo: str, path: str) -> object:
        if path == "collaborators/maintainer/permission":
            return real_restricted_token_response
        return original_get(repo, path)

    github.get = get_with_real_shape  # ty: ignore[invalid-assignment]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["passed"]
    assert result["source"] == "admin-bypass"


def test_admin_bypass_does_not_apply_without_the_marker(
    copilot_config: Path,
) -> None:
    """A plain Issue-linked PR body never triggers the Alpha lookup at all.

    `FakeGitHub` raises `AssertionError` on any unstubbed path, so this
    would fail loudly if the marker-absent short-circuit in
    `_admin_bypass_authorization` ever regressed into making the
    default-branch or issue-comments API calls it exists to skip.
    """
    github = FakeGitHub([])
    github.body = "Closes #42"
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]


def generate(tmp_path: Path, answers: dict[str, object]) -> Path:
    """Render the template with the given review answers."""
    source = tmp_path / "source"
    if not source.exists():
        source.mkdir()
        shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
        shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / f"project-{len(list(tmp_path.iterdir()))}"
    run_copy(
        str(source),
        project,
        data={
            "languages": [],
            "project_description": "Review mode fixture.",
            "project_name": "Review Fixture",
            "project_slug": "review-fixture",
            "repository_url": "https://github.com/example/review-fixture",
            "security_reporting_channel": "Use the private security contact.",
            **answers,
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )
    return project


def rules(
    project: Path, filename: str = "rulesets.json"
) -> dict[str, dict[str, Any]]:
    """Return one generated Ruleset's rules by type."""
    payload = json.loads(
        (project / f".csarc/policies/{filename}").read_text(encoding="utf-8")
    )
    return {
        rule["type"]: rule.get("parameters", {}) for rule in payload["rules"]
    }


@pytest.mark.large
def test_new_project_defaults_to_local_verification(tmp_path: Path) -> None:
    """A new project avoids hosted validation and uses the E1 fallback.

    #1058 decisions 1, 4, and 5: the new-project default is
    `admin_bypass: always`, so a local project renders the E1 shape (zero
    native approvals plus the one reviewed bypass actor).
    """
    project = generate(tmp_path, {})
    config = (project / ".csarc/config.yml").read_text(encoding="utf-8")
    assert "copilot_review: allowed" in config
    assert "admin_bypass: always" in config
    assert "verification_mode: local" in config
    generated = rules(project)
    assert generated["copilot_code_review"]["review_on_push"] is True
    assert generated["pull_request"]["required_approving_review_count"] == 0
    assert generated["pull_request"]["require_last_push_approval"] is False
    assert generated["pull_request"]["dismiss_stale_reviews_on_push"]
    assert generated["pull_request"]["required_review_thread_resolution"]
    required = rules(project, "rulesets-required-checks.json")
    assert required == {}
    for workflow in (
        "ci.yml",
        "dependabot-auto-merge.yml",
        "dependabot-merge.yml",
        "osv.yml",
        "pr-policy.yml",
        "pr-review.yml",
        "release-drift.yml",
        "release.yml",
    ):
        assert not (project / ".github/workflows" / workflow).exists()
    assert (project / ".csarc/scripts/review_gate.py").is_file()
    verifier = (project / ".csarc/scripts/verify").read_text(encoding="utf-8")
    assert "verify_container" not in verifier
    guidance = (project / ".csarc/docs/agent-workflow.md").read_text(
        encoding="utf-8"
    )
    assert "self-attested evidence" in guidance
    assert "run `./.csarc/scripts/verify-fast` once" in guidance
    payload = json.loads(
        (project / ".csarc/policies/rulesets.json").read_text(encoding="utf-8")
    )
    assert payload["bypass_actors"] == pr_lifecycle.REVIEWED_MERGE_BYPASS_ACTORS


@pytest.mark.large
@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("off", []),
        (
            "beta-only",
            [
                {
                    "actor_type": "RepositoryRole",
                    "actor_id": 5,
                    "bypass_mode": "pull_request",
                }
            ],
        ),
        (
            "always",
            [
                {
                    "actor_type": "RepositoryRole",
                    "actor_id": 5,
                    "bypass_mode": "pull_request",
                }
            ],
        ),
    ],
)
def test_admin_bypass_materializes_only_after_explicit_selection(
    tmp_path: Path, mode: str, expected: list[dict[str, object]]
) -> None:
    """Keep actions fallback separate from approval bypass policy."""
    project = generate(
        tmp_path,
        {
            "actions_fallback": "admin",
            "admin_bypass": mode,
            "verification_mode": "hosted",
        },
    )
    payload = json.loads(
        (project / ".csarc/policies/rulesets.json").read_text(encoding="utf-8")
    )
    assert payload["bypass_actors"] == expected


def test_issue_comment_review_gate_can_read_release_level_issues() -> None:
    """Issue #814: the default-branch trigger can run a newer base gate."""
    for path in (
        ROOT / ".github/workflows/pr-review.yml",
        ROOT / "template/.github/workflows/pr-review.yml",
    ):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert workflow["jobs"]["publish"]["permissions"] == {
            "checks": "write",
            "contents": "read",
            "issues": "read",
            "pull-requests": "read",
        }


@pytest.mark.large
def test_human_review_uses_the_level_aware_review_check(tmp_path: Path) -> None:
    """Human mode also delegates the variable approval count to the check."""
    project = generate(
        tmp_path,
        {
            "copilot_review": "off",
            "review": "peer",
            "verification_mode": "hosted",
        },
    )
    generated = rules(project)
    assert "copilot_code_review" not in generated
    assert generated["pull_request"] == {
        "dismiss_stale_reviews_on_push": True,
        "require_code_owner_review": False,
        "require_last_push_approval": False,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": True,
    }
    required = rules(project, "rulesets-required-checks.json")
    contexts = {
        (item["context"], item["integration_id"])
        for item in required["required_status_checks"]["required_status_checks"]
    }
    assert contexts == {
        ("title", 15368),
        ("verify", 15368),
        ("review", 15368),
    }
    for workflow in ("ci.yml", "pr-policy.yml", "pr-review.yml", "release.yml"):
        assert (project / ".github/workflows" / workflow).is_file()
    verifier = (project / ".csarc/scripts/verify").read_text(encoding="utf-8")
    assert "verify_container" not in verifier
    config = (project / ".csarc/config.yml").read_text(encoding="utf-8")
    assert "copilot_review: 'off'" in config


# Issue #1082: one review decision for the `review` check, `status`, and merge.
MATRIX_REVIEWS = ("self", "peer")
MATRIX_COPILOT = ("allowed", "off")
MATRIX_EVIDENCE = ("none", "approval", "copilot", "admin", "copilot+admin")
# 0 = shape A/E1, 1 = shape C, None = unreadable Ruleset, False = malformed.
MATRIX_SHAPES = (0, 1, None, False)
MATRIX_ROLES = ("admin", "maintain", "write", "missing")


def matrix_expected(
    review: str, copilot_review: str, evidence: str, shape: object, role: str
) -> tuple[str, str]:
    """Return the expected (state, code) from the approved rule table."""
    if evidence == "approval" and role in {"admin", "maintain"}:
        return "success", "maintainer-approval"
    if review == "self" and "admin" in evidence:
        if role == "admin":
            return "success", "admin-bypass-authorized"
        return "pending", "admin-bypass-unauthorized"
    copilot_runs = copilot_review == "allowed" and type(shape) is int
    copilot_runs = copilot_runs and shape == 0
    if "copilot" in evidence and copilot_runs:
        return "success", "copilot-clean"
    return "pending", "approval-required"


def matrix_github(evidence: str, shape: object, role: str) -> FakeGitHub:
    """Return a ready PR carrying one combination of review evidence."""
    github = FakeGitHub([])
    github.required_approvals = shape
    github.role_name = role
    github.permission = "admin"
    if evidence == "approval":
        github.reviews = [approval("maintainer")]
    if "copilot" in evidence:
        github.reviews = [copilot()]
    if "admin" in evidence:
        github.body = f"Closes #42\n\n{pr_lifecycle.ADMIN_BYPASS_MARKER}"
        github.issue_comments = [alpha_authorization_comment()]
    return github


def matrix_config(tmp_path: Path, review: str, copilot_review: str) -> Path:
    """Return settings whose stable level resolves to the review mode."""
    bypass = "always" if review == "self" else "off"
    return config(
        tmp_path,
        f"copilot_review: {copilot_review}\nadmin_bypass: {bypass}\n",
    )


def entry_point_outputs(
    monkeypatch: pytest.MonkeyPatch, github: FakeGitHub, path: Path
) -> dict[str, Any]:
    """Run the check, status, and merge entry points on the same state."""
    args = ["--repo", "o/r", "--pr", "7", "--config", str(path)]
    check = review_gate.evaluate(github, "o/r", 7, path)
    status_output = io.StringIO()
    with monkeypatch.context() as patch:
        patch.setattr(pr_lifecycle, "GitHub", lambda: github)
        patch.setattr(review_gate, "unresolved_threads", lambda *_: [])
        assert review_gate.main(["check", *args]) == (
            0 if check["passed"] else 1
        )
        patch.setattr(sys, "stdout", status_output)
        assert review_gate.main(["status", *args]) == 0
    status = json.loads(status_output.getvalue())
    assert status.pop("unresolved_threads") == []
    pull = github.get("o/r", "pulls/7")
    assert isinstance(pull, dict)
    level = review_gate.release_level.resolve_pull(
        github, "o/r", pull, review_gate.release_level.load_settings(path)
    )
    # Merge reads the same inputs, adding its own actor (no longer an
    # excluded approver, #1211) and the lease's default branch.
    merge = review_gate.decide(
        review_gate.review_inputs(
            github,
            "o/r",
            7,
            pull,
            review_gate.review_settings(path),
            level,
            actor="merger",
            default_branch="main",
        )
    )
    return {
        "check": json.loads(json.dumps(check)),
        "status": status,
        "merge": json.loads(json.dumps(merge)),
    }


@pytest.mark.parametrize("review", MATRIX_REVIEWS)
@pytest.mark.parametrize("copilot_review", MATRIX_COPILOT)
@pytest.mark.parametrize("evidence", MATRIX_EVIDENCE)
@pytest.mark.parametrize("shape", MATRIX_SHAPES)
@pytest.mark.parametrize("role", MATRIX_ROLES)
def test_review_decision_matrix_is_identical_across_entry_points(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    review: str,
    copilot_review: str,
    evidence: str,
    shape: object,
    role: str,
) -> None:
    """AC1-AC5, AC7: one decision, one reason code, three entry points."""
    path = matrix_config(tmp_path, review, copilot_review)
    outputs = entry_point_outputs(
        monkeypatch, matrix_github(evidence, shape, role), path
    )
    assert outputs["check"] == outputs["status"] == outputs["merge"]
    decision = outputs["check"]
    assert decision["required_review"] == review
    assert (decision["state"], decision["code"]) == matrix_expected(
        review, copilot_review, evidence, shape, role
    )
    assert decision["passed"] == (decision["state"] == "success")


@pytest.mark.parametrize("evidence", ["none", "copilot-pending", "copilot"])
@pytest.mark.parametrize("shape", [0, 1, None])
@pytest.mark.parametrize("review", MATRIX_REVIEWS)
def test_waiting_or_unavailable_copilot_equals_copilot_off(
    tmp_path: Path, evidence: str, shape: object, review: str
) -> None:
    """AC3/AC4: Copilot is never required and never probes entitlement."""
    github = matrix_github("none", shape, "maintain")
    if evidence == "copilot-pending":
        github.reviews = [copilot("b" * 40)]
    elif evidence == "copilot":
        github.reviews = [copilot()]
    allowed = review_gate.evaluate(
        github, "o/r", 7, matrix_config(tmp_path, review, "allowed")
    )
    off = review_gate.evaluate(
        github, "o/r", 7, matrix_config(tmp_path, review, "off")
    )
    if evidence == "copilot" and shape == 0:
        assert allowed["code"] == "copilot-clean"
        return
    keys = ("state", "passed", "source", "code", "reason", "evidence")
    assert {key: allowed[key] for key in keys} == {
        key: off[key] for key in keys
    }


def test_valid_admin_bypass_marker_excludes_copilot_evidence(
    copilot_config: Path,
) -> None:
    """AC2: a clean Copilot review never replaces a pending admin route."""
    github = matrix_github("copilot+admin", 0, "maintain")
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["admin_bypass"] == "valid"
    assert result["copilot"]["state"] == "clean"
    assert result["code"] == "admin-bypass-unauthorized"
    assert not result["passed"]


def test_invalid_admin_bypass_marker_fails_closed_over_copilot(
    copilot_config: Path,
) -> None:
    """A rejected opt-in fails instead of silently falling back to Copilot."""
    github = matrix_github("copilot+admin", 0, "admin")
    github.issue_milestone = 7
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["admin_bypass"] == "invalid"
    assert result["state"] == "failure"
    assert result["code"] == "admin-bypass-invalid"


@pytest.mark.parametrize(
    ("permission", "role_name", "accepted"),
    [
        # The legacy field folds `maintain` into `write`; role_name decides.
        ("write", "maintain", True),
        ("admin", "admin", True),
        # A legacy `admin` permission never widens a missing or write role.
        ("admin", "missing", False),
        ("admin", "write", False),
        ("admin", "custom-reviewer", False),
    ],
)
def test_maintainer_approval_reads_only_the_live_role_name(
    copilot_config: Path, permission: str, role_name: str, accepted: bool
) -> None:
    """AC5: `maintain`/`admin` count by role_name; unknown fails closed."""
    github = FakeGitHub([approval("maintainer")])
    github.permission = permission
    github.role_name = role_name
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["passed"] is accepted
    assert (result["code"] == "maintainer-approval") is accepted


@pytest.mark.parametrize("source", ["maintainer", "copilot"])
def test_evidence_binds_exact_head_and_invalidates_on_change(
    copilot_config: Path, source: str
) -> None:
    """AC6: a push or dismissal invalidates the accepted evidence."""
    review = approval("maintainer") if source == "maintainer" else copilot()
    github = FakeGitHub([review])
    accepted = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert accepted["source"] == source
    assert accepted["evidence"] == {
        "repository": "o/r",
        "pull_request": 7,
        "head_sha": HEAD,
        "id": review["id"],
        "author": review["user"]["login"],
        "state": review["state"],
        "commit_id": HEAD,
        "at": review["submitted_at"],
        "url": review["html_url"],
        "admin_bypass": "absent",
    }
    pushed = {**review, "commit_id": "c" * 40}
    assert not review_gate.evaluate(
        FakeGitHub([pushed]), "o/r", 7, copilot_config
    )["passed"]
    dismissed = {
        **review,
        "state": "DISMISSED",
        "submitted_at": "2026-09-18T04:00:00Z",
    }
    after_dismissal = review_gate.evaluate(
        FakeGitHub([review, dismissed]), "o/r", 7, copilot_config
    )
    assert not after_dismissal["passed"]
    assert after_dismissal["evidence"] is None


def merge_decision(
    github: FakeGitHub, merger: str, tmp_path: Path
) -> dict[str, Any]:
    """Return the merge-time decision with ``merger`` as the lease actor."""
    pull = github.get("o/r", "pulls/7")
    assert isinstance(pull, dict)
    path = config(tmp_path, "copilot_review: off\nadmin_bypass: off\n")
    level = review_gate.release_level.resolve_pull(
        github, "o/r", pull, review_gate.release_level.load_settings(path)
    )
    return review_gate.decide(
        review_gate.review_inputs(
            github,
            "o/r",
            7,
            pull,
            review_gate.review_settings(path),
            level,
            actor=merger,
            default_branch="main",
        )
    )


def test_1211_reviewer_may_merge_a_collaborator_pull_request(
    tmp_path: Path,
) -> None:
    """AC1/AC2: author collaborator, maintainer approves and merges."""
    github = FakeGitHub([approval("maintainer")])
    github.head_committer = "author"
    github.head_pushes = [push("author")]
    result = merge_decision(github, "maintainer", tmp_path)
    assert result["passed"]
    assert result["code"] == "maintainer-approval"
    assert result["evidence"]["author"] == "maintainer"
    assert result["evidence"]["commit_id"] == HEAD


@pytest.mark.parametrize(
    ("committer", "pushes"),
    [
        # The agent pushed the head under the maintainer's account.
        ("author", [push("maintainer")]),
        # The maintainer committed the head someone else pushed.
        ("maintainer", [push("author")]),
        # Only the newest push of the exact head names the last pusher.
        (
            "author",
            [
                push("author", at="2026-09-18T01:00:00Z"),
                push(
                    "Maintainer", at="2026-09-18T01:40:00Z", kind="force_push"
                ),
            ],
        ),
    ],
)
def test_1211_last_pusher_or_committer_cannot_approve(
    tmp_path: Path, committer: str, pushes: list[dict[str, Any]]
) -> None:
    """AC1/AC2: the head's last pusher or committer is not independent."""
    github = FakeGitHub([approval("maintainer")])
    github.head_committer = committer
    github.head_pushes = pushes
    for merger in ("maintainer", "other"):
        result = merge_decision(github, merger, tmp_path)
        assert not result["passed"]
        assert result["code"] == "approval-required"


def test_1211_author_still_cannot_approve(tmp_path: Path) -> None:
    """AC1: the pull request author never approves its own work."""
    github = FakeGitHub([approval("author")])
    github.head_committer = "author"
    github.head_pushes = [push("author")]
    assert not merge_decision(github, "maintainer", tmp_path)["passed"]


def test_1211_head_change_after_approval_needs_reapproval(
    tmp_path: Path,
) -> None:
    """AC1/AC2: an approval of an earlier head never covers a new push."""
    github = FakeGitHub([approval("maintainer", commit="c" * 40)])
    github.head_committer = "author"
    github.head_pushes = [push("author", after="c" * 40), push("author")]
    result = merge_decision(github, "maintainer", tmp_path)
    assert not result["passed"]
    assert result["evidence"] is None


@pytest.mark.parametrize(
    ("pushes", "head_repo", "reason"),
    [
        (None, "o/r", "could not be read"),
        ([], "o/r", "no push of the exact head"),
        ([push("author", after="c" * 40)], "o/r", "no push of the exact head"),
        ([push("author", kind="branch_deletion")], "o/r", "no push"),
        ([{**push("author"), "actor": None}], "o/r", "has no actor"),
        ([push("author")], None, "head repository or branch is unknown"),
    ],
)
def test_1211_unknown_last_pusher_fails_closed(
    tmp_path: Path,
    pushes: list[dict[str, Any]] | None,
    head_repo: str | None,
    reason: str,
) -> None:
    """AC1: an undeterminable last pusher makes the approval non-independent."""
    github = FakeGitHub([approval("maintainer")])
    github.head_committer = "author"
    github.head_pushes = pushes
    github.head_repo = head_repo
    result = merge_decision(github, "maintainer", tmp_path)
    assert not result["passed"]
    assert result["code"] == "approval-required"
    assert reason in result["reason"]


def test_1211_pusher_is_read_only_when_an_approval_could_count(
    tmp_path: Path,
) -> None:
    """No approval candidate means no extra pusher API reads."""
    github = FakeGitHub([])
    github.head_pushes = None
    result = merge_decision(github, "maintainer", tmp_path)
    assert result["code"] == "approval-required"
    assert "independence is unknown" not in result["reason"]
