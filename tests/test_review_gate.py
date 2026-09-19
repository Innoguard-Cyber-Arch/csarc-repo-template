"""Tests for the Copilot-or-maintainer `review` required check (#752)."""

from __future__ import annotations

import importlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
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


class FakeGitHub:
    """Serve one pull request, its reviews, and Copilot's comments."""

    def __init__(self, reviews: list[dict[str, Any]]) -> None:
        self.reviews = reviews
        self.inline: list[dict[str, Any]] = []
        self.draft = False
        self.body = ""
        self.base_ref = "main"
        self.default_branch = "main"
        self.head_ref = "fix/42-lifecycle"
        self.head_repo: str | None = "o/r"
        self.issue_state = "open"
        self.issue_milestone: int | None = None
        self.issue_comments: list[dict[str, Any]] = []
        self.hotfix_comments: list[dict[str, Any]] = []
        self.labels: set[str] = set()
        self.permission = "maintain"

    def get(self, repo: str, path: str) -> object:
        """Return one REST fixture."""
        if path == "pulls/7":
            return {
                "draft": self.draft,
                "body": self.body,
                "base": {"ref": self.base_ref},
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
        match = re.fullmatch(r"collaborators/([^/]+)/permission", path)
        if match:
            return {
                "permission": self.permission,
                "user": {"login": match.group(1)},
            }
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
    """Write one answers file and return its path."""
    path = tmp_path / "config.yml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def copilot_config(tmp_path: Path) -> Path:
    """Return a Copilot-mode answers file."""
    return config(
        tmp_path,
        "pr_review_mode: copilot\n"
        "copilot_review_max_level: unlimited\n"
        "default_release_level: alpha\n",
    )


def test_missing_setting_means_human_mode(tmp_path: Path) -> None:
    """An answers file predating #752 keeps maintainer-only review."""
    assert review_gate.review_settings(config(tmp_path, "languages: []\n")) == (
        "human",
        "unlimited",
    )


def test_invalid_review_mode_is_rejected(tmp_path: Path) -> None:
    """The flat config validator owns the allowed values."""
    with pytest.raises(ValueError, match="pr_review_mode"):
        review_gate.review_settings(config(tmp_path, "pr_review_mode: bot\n"))


def test_human_mode_requires_exact_head_approval(tmp_path: Path) -> None:
    """The level-aware check enforces peer review in human mode too."""
    result = review_gate.evaluate(
        FakeGitHub([]), "o/r", 7, config(tmp_path, "pr_review_mode: human\n")
    )
    assert not result["passed"]
    assert result["release_level"] == "beta"
    assert "independent maintainer" in result["reason"]

    approved = review_gate.evaluate(
        FakeGitHub([approval("maintainer")]),
        "o/r",
        7,
        config(tmp_path, "pr_review_mode: human\n"),
    )
    assert approved["passed"]
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
            tmp_path, "pr_review_mode: human\ndefault_release_level: beta\n"
        ),
    )

    assert result["passed"]
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
        github, "o/r", 7, config(tmp_path, "default_release_level: beta\n")
    )

    assert not result["passed"]
    assert "independent maintainer" in result["reason"]


def test_clean_copilot_review_of_head_passes(copilot_config: Path) -> None:
    """A clean exact-head Copilot review passes the check."""
    result = review_gate.evaluate(
        FakeGitHub([copilot()]), "o/r", 7, copilot_config
    )
    assert result["passed"]
    assert result["source"] == "copilot"


@pytest.mark.parametrize(
    ("reviews", "inline", "reason"),
    [
        ([], [], "not reviewed this pull request"),
        ([copilot("b" * 40)], [], "not reviewed the current head"),
        (
            [copilot()],
            [{"path": "x.py", "line": 1, "body": "Bug"}],
            "1 comment",
        ),
        ([copilot(body="Comments suppressed (2)")], [], "suppressed"),
        ([copilot(body="Copilot encountered an error.")], [], "does not state"),
    ],
)
def test_copilot_review_that_is_not_clean_fails(
    copilot_config: Path,
    reviews: list[dict[str, Any]],
    inline: list[dict[str, Any]],
    reason: str,
) -> None:
    """Pending, stale, commented, or unrecognized reviews fail closed."""
    github = FakeGitHub(reviews)
    github.inline = inline
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert reason in result["reason"]
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


def test_draft_fails_even_with_clean_copilot_review(
    copilot_config: Path,
) -> None:
    """Draft pull requests are not ready to merge."""
    github = FakeGitHub([copilot()])
    github.draft = True
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert "Draft" in result["reason"]


def test_level_cap_requires_a_maintainer_above_the_configured_level(
    tmp_path: Path,
) -> None:
    """Copilot cannot satisfy a self-review level above its configured cap."""
    capped = config(
        tmp_path,
        "pr_review_mode: copilot\n"
        "copilot_review_max_level: beta\n"
        "default_release_level: formal\n"
        "release_level_formal_review: self\n",
    )
    result = review_gate.evaluate(FakeGitHub([copilot()]), "o/r", 7, capped)
    assert not result["passed"]
    assert "does not allow Copilot" in result["reason"]


def test_beta_level_requires_peer_even_with_clean_copilot(
    tmp_path: Path,
) -> None:
    """The default Beta policy cannot be weakened by Copilot mode."""
    beta = config(
        tmp_path,
        "pr_review_mode: copilot\n"
        "copilot_review_max_level: unlimited\n"
        "default_release_level: beta\n",
    )
    result = review_gate.evaluate(FakeGitHub([copilot()]), "o/r", 7, beta)
    assert not result["passed"]
    assert result["required_review"] == "peer"


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
    github.body = f"Closes #42\n\n{pr_lifecycle.ALPHA_SELF_MERGE_MARKER}"
    return github


def test_alpha_self_merge_authorization_passes(copilot_config: Path) -> None:
    """Issue #775: a valid exact-head Alpha self-merge comment passes review."""
    github = alpha_github()
    github.issue_comments = [alpha_authorization_comment()]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["passed"]
    assert result["source"] == "alpha-self-merge"


def test_alpha_self_merge_ignores_author_association(
    copilot_config: Path,
) -> None:
    """Issue #785: a downgraded association must not block self-merge.

    Confirmed live on PR #782: a restricted `GITHUB_TOKEN` reports a real
    maintainer's comment as `COLLABORATOR` instead of `MEMBER`. The
    `collaborators/{login}/permission` lookup `FakeGitHub.get` always
    returns `"maintain"` for any login, so this only passes once
    `find_exact_head_authorization` stops filtering on the association.
    """
    github = alpha_github()
    github.issue_comments = [
        alpha_authorization_comment(association="COLLABORATOR")
    ]
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert result["passed"]
    assert result["source"] == "alpha-self-merge"


def test_alpha_self_merge_without_authorization_still_fails(
    copilot_config: Path,
) -> None:
    """The marker and route alone are not authorization -- a comment is."""
    github = alpha_github()
    result = review_gate.evaluate(github, "o/r", 7, copilot_config)
    assert not result["passed"]
    assert "Alpha self-merge" in result["reason"]
    assert "#775" in result["reason"]
    assert "no exact-head maintainer authorization comment" in result["reason"]


def test_alpha_self_merge_milestone_issue_does_not_apply(
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


def test_alpha_self_merge_closed_issue_does_not_apply(
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


def test_alpha_self_merge_ignores_a_non_maintainer_comment(
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


def test_alpha_self_merge_collaborator_permission_under_restricted_token(
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
    assert result["source"] == "alpha-self-merge"


def test_alpha_self_merge_does_not_apply_without_the_marker(
    copilot_config: Path,
) -> None:
    """A plain Issue-linked PR body never triggers the Alpha lookup at all.

    `FakeGitHub` raises `AssertionError` on any unstubbed path, so this
    would fail loudly if the marker-absent short-circuit in
    `_alpha_self_merge_authorization` ever regressed into making the
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
        (project / f"policies/{filename}").read_text(encoding="utf-8")
    )
    return {
        rule["type"]: rule.get("parameters", {}) for rule in payload["rules"]
    }


def test_new_project_defaults_to_copilot_review(tmp_path: Path) -> None:
    """A new project gets the Copilot Ruleset, check, and gate script."""
    project = generate(tmp_path, {})
    config = (project / ".csarc/config.yml").read_text(encoding="utf-8")
    assert "pr_review_mode: copilot" in config
    assert "copilot_review_max_level: unlimited" in config
    generated = rules(project)
    assert generated["copilot_code_review"]["review_on_push"] is True
    assert generated["pull_request"]["required_approving_review_count"] == 0
    assert generated["pull_request"]["required_review_thread_resolution"]
    required = rules(project, "rulesets-required-checks.json")
    contexts = {
        item["context"]
        for item in required["required_status_checks"]["required_status_checks"]
    }
    assert "review" in contexts
    assert (project / ".github/workflows/pr-review.yml").is_file()
    assert (project / "scripts/review_gate.py").is_file()


def test_issue_comment_review_gate_can_read_release_level_issues() -> None:
    """Issue #814: the default-branch trigger can run a newer base gate."""
    for path in (
        ROOT / ".github/workflows/pr-review.yml",
        ROOT / "template/.github/workflows/pr-review.yml",
    ):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert workflow["jobs"]["review"]["permissions"] == {
            "contents": "read",
            "issues": "read",
            "pull-requests": "read",
        }


def test_human_review_uses_the_level_aware_review_check(tmp_path: Path) -> None:
    """Human mode also delegates the variable approval count to the check."""
    project = generate(tmp_path, {"pr_review_mode": "human"})
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
        item["context"]
        for item in required["required_status_checks"]["required_status_checks"]
    }
    assert contexts == {"title", "promotion", "verify", "review"}
    config = (project / ".csarc/config.yml").read_text(encoding="utf-8")
    assert "copilot_review_max_level" not in config
