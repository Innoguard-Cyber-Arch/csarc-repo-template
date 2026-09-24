"""Regression tests for beta/stable release governance (Issue #918)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "release_level_under_test", ROOT / "scripts" / "release_level.py"
)
assert SPEC is not None and SPEC.loader is not None
levels = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = levels
SPEC.loader.exec_module(levels)


class FakeGitHub:
    """Serve Issues, Milestones, PRs, and collaborator permissions."""

    def __init__(self) -> None:
        self.objects: dict[str, object] = {}
        self.collections: dict[str, list[dict[str, Any]]] = {}
        self.writes: list[tuple[str, str, str]] = []
        self.fields: list[dict[str, object] | None] = []

    def get(self, repo: str, path: str) -> object:
        del repo
        value = self.objects.get(path)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise AssertionError(path)
        return value

    def pages(self, repo: str, path: str) -> list[dict[str, Any]]:
        del repo
        return self.collections[path]

    def write(
        self,
        repo: str,
        method: str,
        path: str,
        body: str,
        fields: dict[str, object] | None = None,
    ) -> object:
        del repo
        self.writes.append((method, path, body))
        self.fields.append(fields)
        return {"html_url": "https://github.com/o/r/pull/9#issuecomment-1"}


def body(level: str | None) -> str:
    """Render the Issue-form section used by GitHub."""
    if level is None:
        return "### Problem\n\nSomething happened.\n"
    return f"### {levels.DECLARATION_HEADING}\n\n{level}\n"


def issue(
    number: int,
    level: str | None,
    *,
    author: str = "worker",
    milestone: int | None = None,
) -> dict[str, Any]:
    """Build one Issue fixture."""
    return {
        "number": number,
        "title": "Work",
        "body": body(level),
        "user": {"login": author, "type": "User"},
        "milestone": {"number": milestone} if milestone else None,
    }


def settings(**overrides: object) -> levels.Settings:
    """Build settings with repository defaults plus explicit overrides."""
    config: dict[str, object] = {
        "default_release_level": "stable",
        "admin_bypass": "always",
    }
    config.update(overrides)
    return levels.settings_from_mapping(config)


def trust(github: FakeGitHub, *logins: str) -> None:
    """Mark users as repository collaborators."""
    for login in logins:
        github.objects[f"collaborators/{login}/permission"] = {
            "permission": "write"
        }


def test_release_level_defaults_match_the_two_channel_decision() -> None:
    configured = settings()

    assert configured.default_level == "stable"
    assert configured.reviews == {
        "beta": "self",
        "stable": "self",
    }
    assert configured.suites == {
        "beta": "fast",
        "stable": "full",
    }


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("off", {"beta": "peer", "stable": "peer"}),
        ("beta-only", {"beta": "self", "stable": "peer"}),
        ("always", {"beta": "self", "stable": "self"}),
    ],
)
def test_admin_bypass_mode_controls_only_human_approval(
    mode: str, expected: dict[str, str]
) -> None:
    configured = settings(admin_bypass=mode)

    assert configured.reviews == expected
    assert configured.suites == {"beta": "fast", "stable": "full"}


def test_declaration_accepts_legacy_h2_and_issue_form_h3() -> None:
    assert (
        levels.declared_level(
            f"### {levels.DECLARATION_HEADING}\n\nearly\n\n### Details\n\nText"
        )
        == "stable"
    )
    assert (
        levels.declared_level(f"## {levels.DECLARATION_HEADING}\n\nbeta\n")
        == "beta"
    )


def test_non_collaborator_declaration_uses_default() -> None:
    github = FakeGitHub()
    github.objects["collaborators/outsider/permission"] = RuntimeError("404")

    result = levels.resolve_issue(
        github, "o/r", issue(7, "formal", author="outsider"), settings()
    )

    assert result.level == "stable"
    assert result.source == "standalone work item"


def test_none_permission_is_not_a_trusted_collaborator() -> None:
    github = FakeGitHub()
    github.objects["collaborators/outsider/permission"] = {"permission": "none"}

    result = levels.resolve_issue(
        github, "o/r", issue(7, "formal", author="outsider"), settings()
    )

    assert result.level == "stable"


def test_collaborator_declaration_is_trusted() -> None:
    github = FakeGitHub()
    trust(github, "worker")

    result = levels.resolve_issue(github, "o/r", issue(7, "early"), settings())

    assert (result.level, result.review, result.suite) == (
        "stable",
        "self",
        "full",
    )


def test_milestone_work_issue_is_always_beta() -> None:
    github = FakeGitHub()
    trust(github, "worker", "tracker-owner")
    tracker = issue(80, "alpha", author="tracker-owner", milestone=8)
    tracker["title"] = "Milestone 8: Delivery"
    github.objects["milestones/8"] = {"title": "Delivery"}
    github.collections["issues?milestone=8&state=all&per_page=100"] = [tracker]

    result = levels.resolve_issue(
        github, "o/r", issue(7, None, milestone=8), settings()
    )

    assert result.level == "beta"
    assert result.source == "Milestone 8 work item"


def test_milestone_tracker_is_always_stable() -> None:
    github = FakeGitHub()
    trust(github, "worker", "tracker-owner")
    tracker = issue(80, "beta", author="tracker-owner", milestone=8)
    tracker["title"] = "Milestone 8: Delivery"
    github.objects["milestones/8"] = {"title": "Delivery"}
    github.collections["issues?milestone=8&state=all&per_page=100"] = [tracker]

    result = levels.resolve_issue(github, "o/r", tracker, settings())

    assert result.level == "stable"


def test_legacy_disable_flag_cannot_turn_off_release_classification() -> None:
    configured = settings(release_levels_enabled=False)

    assert configured.enabled is True


def test_dependabot_is_always_beta() -> None:
    pull = {
        "user": {"login": "dependabot[bot]"},
        "head": {"ref": "dependabot/pip/foo-2", "repo": {"full_name": "o/r"}},
        "body": "",
    }

    result = levels.resolve_pull(FakeGitHub(), "o/r", pull, settings())

    assert result.level == "beta"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("chore(main): release 0.16.0-beta.1", "beta"),
        ("chore(main): release 0.16.0", "stable"),
        ("chore(main): release 1.0.0", "stable"),
    ],
)
def test_release_pull_uses_its_version_level(title: str, expected: str) -> None:
    pull = {
        "title": title,
        "user": {"login": "github-actions[bot]"},
        "head": {
            "ref": "release-please--branches--main",
            "repo": {"full_name": "o/r"},
        },
        "body": "",
    }

    assert (
        levels.resolve_pull(FakeGitHub(), "o/r", pull, settings()).level
        == expected
    )


def test_milestone_promotion_pull_uses_tracker_level() -> None:
    github = FakeGitHub()
    trust(github, "tracker-owner")
    tracker = issue(140, "early", author="tracker-owner", milestone=14)
    tracker["title"] = "Milestone 14: Delivery"
    github.objects["milestones/14"] = {"number": 14, "title": "Delivery"}
    github.collections["issues?milestone=14&state=all&per_page=100"] = [tracker]
    pull = {
        "number": 7,
        "body": "Promotes the completed delivery branch.",
        "milestone": {"number": 14},
        "user": {"login": "maintainer"},
        "head": {"ref": "dev/m14-delivery", "repo": {"full_name": "o/r"}},
    }

    decision = levels.resolve_pull(github, "o/r", pull, settings())

    assert decision.level == "stable"
    assert decision.source == "Milestone 14 promotion"


def test_level_floor_and_path_tier_use_the_stronger_suite() -> None:
    configured = settings()

    assert levels.required_suite("beta", "fast", configured) == "fast"
    assert levels.required_suite("stable", "docs", configured) == "full"


@pytest.mark.parametrize(
    ("level", "path_tier", "expected"),
    [
        ("beta", "docs", "fast"),
        ("beta", "fast", "fast"),
        ("beta", "full", "full"),
        ("stable", "docs", "full"),
        ("stable", "fast", "full"),
        ("stable", "full", "full"),
    ],
)
def test_release_level_and_path_tier_matrix(
    level: str, path_tier: str, expected: str
) -> None:
    assert levels.required_suite(level, path_tier, settings()) == expected


def test_highest_level_uses_channel_order() -> None:
    assert levels.highest_level(["beta", "stable", "beta"]) == "stable"


def test_release_batch_lists_each_work_item_and_uses_highest_level() -> None:
    github = FakeGitHub()
    trust(github, "worker")
    alpha = issue(7, "alpha")
    alpha["html_url"] = "https://github.com/o/r/issues/7"
    formal = issue(8, "formal")
    formal["html_url"] = "https://github.com/o/r/issues/8"
    github.objects["issues/7"] = alpha
    github.objects["issues/8"] = formal
    pulls = [
        {
            "number": 17,
            "title": "Alpha work",
            "html_url": "https://github.com/o/r/pull/17",
            "body": "Fixes #7",
            "user": {"login": "worker"},
            "head": {"ref": "fix/7-alpha", "repo": {"full_name": "o/r"}},
        },
        {
            "number": 18,
            "title": "Formal work",
            "html_url": "https://github.com/o/r/pull/18",
            "body": "Fixes #8",
            "user": {"login": "worker"},
            "head": {"ref": "feat/8-formal", "repo": {"full_name": "o/r"}},
        },
    ]

    batch = levels.release_batch(github, "o/r", pulls, settings())
    markdown = levels.release_batch_markdown(batch)

    assert batch["level"] == "stable"
    assert [item["level"] for item in batch["items"]] == ["stable", "stable"]
    assert "Issue #7: Work" in markdown
    assert "Issue #8: Work" in markdown
    assert "Highest included level: `stable`" in markdown


def test_release_batch_expands_a_milestone_to_its_child_work() -> None:
    github = FakeGitHub()
    trust(github, "tracker-owner", "worker")
    tracker = issue(140, "beta", author="tracker-owner", milestone=14)
    tracker["title"] = "Milestone 14: Delivery"
    child = issue(145, None, milestone=14)
    child["html_url"] = "https://github.com/o/r/issues/145"
    github.objects["milestones/14"] = {"number": 14, "title": "Delivery"}
    github.collections["issues?milestone=14&state=all&per_page=100"] = [
        tracker,
        child,
    ]
    pull = {
        "number": 19,
        "title": "Promote delivery",
        "html_url": "https://github.com/o/r/pull/19",
        "body": "",
        "milestone": {"number": 14},
        "user": {"login": "worker"},
        "head": {"ref": "promote/m14", "repo": {"full_name": "o/r"}},
    }

    batch = levels.release_batch(github, "o/r", [pull], settings())

    assert batch["level"] == "beta"
    assert [(item["kind"], item["number"]) for item in batch["items"]] == [
        ("Issue", 145)
    ]


def test_unreleased_pulls_uses_only_exact_main_merge_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github = FakeGitHub()
    github.objects["commits/a/pulls"] = [
        {
            "number": 7,
            "merged_at": "2026-09-19T00:00:00Z",
            "merge_commit_sha": "a",
            "base": {"ref": "main"},
        },
        {
            "number": 8,
            "merged_at": "2026-09-19T00:00:00Z",
            "merge_commit_sha": "other",
            "base": {"ref": "main"},
        },
    ]
    github.objects["commits/b/pulls"] = [
        {
            "number": 7,
            "merged_at": "2026-09-19T00:00:00Z",
            "merge_commit_sha": "b",
            "base": {"ref": "release"},
        }
    ]

    def fake_git_lines(root: Path, arguments: list[str]) -> list[str]:
        del root
        if arguments == ["tag", "--merged", "head"]:
            return ["not-a-version", "v0.1.0"]
        assert arguments == ["rev-list", "--reverse", "v0.1.0..head"]
        return ["a", "b"]

    monkeypatch.setattr(levels, "_git_lines", fake_git_lines)

    assert [
        pull["number"]
        for pull in levels.unreleased_pulls(github, "o/r", ROOT, "head")
    ] == [7]


def test_release_batch_without_prior_tag_or_work_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(levels, "_git_lines", lambda root, arguments: [])

    batch = levels.release_batch_from_git(
        FakeGitHub(),
        "o/r",
        ROOT,
        "head",
        settings(default_release_level="stable"),
    )

    assert batch == {"level": "stable", "items": []}


def test_release_pull_annotation_is_idempotent_for_the_same_actor() -> None:
    github = FakeGitHub()
    note = (
        "<!-- release-level-work-items:start -->\n"
        "details\n"
        "<!-- release-level-work-items:end -->\n"
    )
    github.collections["issues/9/comments?per_page=100"] = []

    levels.annotate_pull_request(github, "o/r", 9, "github-actions[bot]", note)

    assert github.writes == [("POST", "issues/9/comments", note)]
    github.writes.clear()
    github.collections["issues/9/comments?per_page=100"] = [
        {
            "id": 44,
            "body": note,
            "user": {"login": "github-actions[bot]"},
        }
    ]
    levels.annotate_pull_request(github, "o/r", 9, "github-actions[bot]", note)
    assert github.writes == [("PATCH", "issues/comments/44", note)]


def test_release_annotation_preserves_notes_and_replaces_evidence() -> None:
    github = FakeGitHub()
    github.collections["releases?per_page=100"] = [
        {"id": 54, "tag_name": "v1.2.2", "draft": False, "immutable": True},
        {
            "id": 55,
            "tag_name": "v1.2.3",
            "draft": True,
            "immutable": False,
            "body": (
                "Existing notes\n\n"
                "<!-- release-level-work-items:start -->\nold\n"
                "<!-- release-level-work-items:end -->\n"
            ),
        },
    ]
    # The by-tag endpoint returns 404 for drafts; it must not be consulted.
    github.objects["releases/tags/v1.2.3"] = RuntimeError("HTTP 404")
    details = (
        "<!-- release-level-work-items:start -->\nnew\n"
        "<!-- release-level-work-items:end -->\n"
    )

    levels.annotate_release(github, "o/r", "v1.2.3", details)

    assert github.writes == [
        (
            "PATCH",
            "releases/55",
            "Existing notes\n\n" + details,
        )
    ]
    # Omitting tag_name makes GitHub detach the draft from its tag.
    assert github.fields == [{"tag_name": "v1.2.3", "draft": True}]


@pytest.mark.parametrize(
    "releases",
    [
        [],
        [{"id": 55, "tag_name": "v1.2.3", "draft": False, "immutable": True}],
        [{"id": 55, "tag_name": "v1.2.3", "draft": True, "immutable": True}],
        [
            {"id": 55, "tag_name": "v1.2.3", "draft": True, "immutable": False},
            {"id": 56, "tag_name": "v1.2.3", "draft": True, "immutable": False},
        ],
    ],
    ids=["missing", "published", "immutable", "ambiguous"],
)
def test_release_annotation_fails_closed_without_one_mutable_draft(
    releases: list[dict[str, Any]],
) -> None:
    github = FakeGitHub()
    github.collections["releases?per_page=100"] = releases

    with pytest.raises(RuntimeError, match="one mutable draft Release"):
        levels.annotate_release(github, "o/r", "v1.2.3", "details")

    assert github.writes == []


def test_root_and_template_release_level_modules_match() -> None:
    assert (ROOT / "scripts/release_level.py").read_bytes() == (
        ROOT / "template/.csarc/scripts/release_level.py"
    ).read_bytes()
