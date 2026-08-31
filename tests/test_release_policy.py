"""Tests for adaptive release capability and version decisions."""

from __future__ import annotations

import json
import runpy
import subprocess
from pathlib import Path
from typing import cast

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "release_policy.py")
)
Capability = MODULE["Capability"]
aggregate_release_boundaries = MODULE["aggregate_release_boundaries"]
bump_version = MODULE["bump_version"]
classify_probe = MODULE["classify_probe"]
direct_release = MODULE["direct_release"]
release_intent = MODULE["release_intent"]
release_follow_up_errors = MODULE["release_follow_up_errors"]
release_boundary_errors = MODULE["release_boundary_errors"]
release_plan = MODULE["release_plan"]
release_version_errors = MODULE["release_version_errors"]
select_release_mode = MODULE["select_release_mode"]
simple_release_boundary = MODULE["simple_release_boundary"]
verify_release_version = MODULE["verify_release_version"]
optional_integration_preflight = MODULE["optional_integration_preflight"]


def test_root_release_config_updates_site_source_and_rendered_bundle() -> None:
    """Release bumps keep the source site and checked-in bundle aligned."""
    config = json.loads(
        (Path(__file__).parents[1] / "release-please-config.json").read_text(
            encoding="utf-8"
        )
    )
    if config["packages"]["."]["component"] != "csarc-repo-template":
        return
    extra_files = config["packages"]["."]["extra-files"]
    paths = {
        item if isinstance(item, str) else item["path"] for item in extra_files
    }
    assert {"site/content/_index.zh-tw.md", "docs/index.html"} <= paths


def test_release_version_checks_configured_site_source(tmp_path: Path) -> None:
    """A stale source site blocks release even when the bundle was edited."""
    write_release_surfaces(tmp_path, "1.2.3")
    (tmp_path / "site").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "site/index.html").write_text(
        "v1.2.2 <!-- x-release-please-version -->\n", encoding="utf-8"
    )
    (tmp_path / "docs/index.html").write_text(
        "v1.2.3 <!-- x-release-please-version -->\n", encoding="utf-8"
    )
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {"packages": {".": {"extra-files": [{"path": "site/index.html"}]}}}
        ),
        encoding="utf-8",
    )
    assert "site/index.html is 1.2.2, expected 1.2.3" in release_version_errors(
        tmp_path, "1.2.3"
    )


def test_release_follow_up_accepts_only_automation_owned_changes(
    tmp_path: Path,
) -> None:
    """Bind release follow-ups to the canonical bot branch and file set."""
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "python",
                "packages": {
                    ".": {
                        "component": "demo",
                        "extra-files": [
                            {"path": "src/demo/__init__.py"},
                            "README.md",
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").touch()
    valid_head = "release-please--branches--main--components--demo"
    valid_sha = "a" * 40
    valid_commits = [
        {
            "sha": valid_sha,
            "author": {"login": "github-actions[bot]"},
            "committer": {"login": "web-flow"},
            "commit": {"verification": {"verified": True, "reason": "valid"}},
        }
    ]
    valid = {
        "root": tmp_path,
        "repo": "owner/repo",
        "head": valid_head,
        "head_repo": "owner/repo",
        "head_sha": valid_sha,
        "actor": "github-actions[bot]",
        "changed_files": [
            ".release-please-manifest.json",
            "CHANGELOG.md",
            "pyproject.toml",
            "uv.lock",
            "src/demo/__init__.py",
            "README.md",
        ],
        "commits": valid_commits,
    }
    assert release_follow_up_errors(**valid) == []

    maintainer = dict(valid)
    maintainer.update(
        actor="maintainer",
        actor_permission="maintain",
        commits=[
            {
                "sha": valid_sha,
                "author": {"login": "maintainer"},
                "committer": {"login": "web-flow"},
                "commit": {
                    "verification": {"verified": True, "reason": "valid"}
                },
            }
        ],
    )
    assert release_follow_up_errors(**maintainer) == []
    maintainer["actor_permission"] = "write"
    assert release_follow_up_errors(**maintainer)
    wrong_author = dict(maintainer)
    wrong_author.update(
        actor_permission="admin",
        commits=[
            {
                "sha": valid_sha,
                "author": {"login": "attacker"},
                "committer": {"login": "web-flow"},
                "commit": {
                    "verification": {"verified": True, "reason": "valid"}
                },
            }
        ],
    )
    assert release_follow_up_errors(**wrong_author)

    assert release_follow_up_errors(
        tmp_path,
        "owner/repo",
        "release-please--forged",
        "owner/repo",
        valid_sha,
        "github-actions[bot]",
        ["CHANGELOG.md"],
        valid_commits,
    )
    assert release_follow_up_errors(
        tmp_path,
        "owner/repo",
        valid_head,
        "fork/repo",
        valid_sha,
        "github-actions[bot]",
        ["CHANGELOG.md"],
        valid_commits,
    )
    assert release_follow_up_errors(
        tmp_path,
        "owner/repo",
        valid_head,
        "owner/repo",
        valid_sha,
        "attacker",
        ["CHANGELOG.md"],
        valid_commits,
    )
    assert release_follow_up_errors(
        tmp_path,
        "owner/repo",
        valid_head,
        "owner/repo",
        valid_sha,
        "github-actions[bot]",
        ["src/product.py"],
        valid_commits,
    )
    assert release_follow_up_errors(
        tmp_path,
        "owner/repo",
        valid_head,
        "owner/repo",
        valid_sha,
        "github-actions[bot]",
        [".github/workflows/ci.yml"],
        valid_commits,
    )

    human_commit = [
        {
            "sha": valid_sha,
            "author": {"login": "github-actions[bot]"},
            "committer": {"login": "maintainer"},
            "commit": {"verification": {"verified": True, "reason": "valid"}},
        }
    ]
    assert release_follow_up_errors(
        tmp_path,
        "owner/repo",
        valid_head,
        "owner/repo",
        valid_sha,
        "github-actions[bot]",
        ["pyproject.toml"],
        human_commit,
    )
    unsigned_spoof = [
        {
            "sha": valid_sha,
            "author": {"login": "github-actions[bot]"},
            "committer": {"login": "web-flow"},
            "commit": {
                "verification": {"verified": False, "reason": "unsigned"}
            },
        }
    ]
    assert release_follow_up_errors(
        tmp_path,
        "owner/repo",
        valid_head,
        "owner/repo",
        valid_sha,
        "github-actions[bot]",
        ["pyproject.toml"],
        unsigned_spoof,
    )
    assert release_follow_up_errors(
        tmp_path,
        "owner/repo",
        valid_head,
        "owner/repo",
        "b" * 40,
        "github-actions[bot]",
        ["CHANGELOG.md"],
        valid_commits,
    )


def test_release_follow_up_accepts_rust_manifest_and_lockfile(
    tmp_path: Path,
) -> None:
    """Treat Cargo's manifest and lockfile as one supported release surface."""
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "rust",
                "packages": {".": {"component": "demo"}},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "Cargo.lock").touch()
    head_sha = "a" * 40
    commits = [
        {
            "sha": head_sha,
            "author": {"login": "github-actions[bot]"},
            "committer": {"login": "web-flow"},
            "commit": {"verification": {"verified": True, "reason": "valid"}},
        }
    ]

    assert (
        release_follow_up_errors(
            tmp_path,
            "owner/repo",
            "release-please--branches--main--components--demo",
            "owner/repo",
            head_sha,
            "github-actions[bot]",
            [
                ".release-please-manifest.json",
                "CHANGELOG.md",
                "Cargo.toml",
                "Cargo.lock",
            ],
            commits,
        )
        == []
    )


def capabilities(
    pull_requests: str, contents: str, release: str, dispatch: str
) -> dict[str, object]:
    return {
        "actions_pull_requests": Capability(pull_requests, "test"),
        "contents": Capability(contents, "test"),
        "release": Capability(release, "test"),
        "dispatch": Capability(dispatch, "test"),
    }


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (("allowed", "allowed", "allowed", "allowed"), "release-pr"),
        (
            ("allowed", "unknown", "unknown", "unknown"),
            "verification-only",
        ),
        (("blocked", "allowed", "allowed", "allowed"), "direct"),
        (("unknown", "allowed", "allowed", "allowed"), "direct"),
        (("blocked", "blocked", "allowed", "allowed"), "verification-only"),
        (("unknown", "allowed", "unknown", "allowed"), "verification-only"),
    ],
)
def test_release_mode_is_fail_closed(
    states: tuple[str, str, str, str], expected: str
) -> None:
    assert select_release_mode(capabilities(*states))[0] == expected


def test_http_failures_are_never_allowed() -> None:
    assert classify_probe(403).state == "blocked"
    assert classify_probe(409).state == "blocked"
    assert classify_probe(0).state == "unknown"
    assert classify_probe(422).state == "unknown"
    assert classify_probe(422, validation_proves_access=True).state == "allowed"


def integration_preflight(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, dict[str, object] | None],
) -> dict[str, object]:
    """Run the integration preflight with deterministic GitHub responses."""
    monkeypatch.setattr(MODULE["shutil"], "which", lambda _: "/usr/bin/gh")

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        del check, capture_output, text
        payload = responses.get(command[-1])
        return subprocess.CompletedProcess(
            command,
            0 if payload is not None else 1,
            stdout=json.dumps(payload) if payload is not None else "",
            stderr="",
        )

    monkeypatch.setattr(MODULE["subprocess"], "run", fake_run)
    payload = optional_integration_preflight("owner/repo")
    return cast(dict[str, object], payload["renovate"])


def test_personal_repository_owner_can_open_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = integration_preflight(
        monkeypatch,
        {
            "repos/owner/repo": {
                "owner": {"login": "owner", "type": "User"},
                "permissions": {"admin": True},
            },
            "user": {"login": "owner"},
        },
    )
    assert result["state"] == "available"
    observed = cast(dict[str, object], result["observed"])
    assert observed["repository_admin"] is True


def test_organization_owner_can_open_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = integration_preflight(
        monkeypatch,
        {
            "repos/owner/repo": {
                "owner": {"login": "owner", "type": "Organization"},
                "permissions": {"admin": True},
            },
            "user": {"login": "actor"},
            "orgs/owner/memberships/actor": {
                "state": "active",
                "role": "admin",
            },
        },
    )
    assert result["state"] == "available"
    observed = cast(dict[str, object], result["observed"])
    assert observed["organization_owner"] is True


def test_organization_member_requests_owner_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = integration_preflight(
        monkeypatch,
        {
            "repos/owner/repo": {
                "owner": {"login": "owner", "type": "Organization"},
                "permissions": {"admin": True},
            },
            "user": {"login": "actor"},
            "orgs/owner/memberships/actor": {
                "state": "active",
                "role": "member",
            },
        },
    )
    assert result["state"] == "request-owner"
    assert "Dependabot" in str(result["fallback"])


@pytest.mark.parametrize(
    "responses",
    [
        {
            "repos/owner/repo": {
                "owner": {"login": "owner", "type": "Organization"},
                "permissions": {},
            },
            "user": {"login": "actor"},
        },
        {"repos/owner/repo": None},
    ],
)
def test_unknown_or_failed_observation_uses_native_fallback(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, dict[str, object] | None],
) -> None:
    result = integration_preflight(monkeypatch, responses)
    assert result["state"] == "fallback"
    assert "Dependabot" in str(result["next_step"])


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("feat(api): add reports", "minor"),
        ("fix: handle timeout", "patch"),
        ("feat!: replace protocol", "major"),
        ("docs: explain reports", "no-release"),
        ("not conventional", "no-release"),
    ],
)
def test_pr_title_only_reports_bump_intent(title: str, expected: str) -> None:
    assert release_intent(title) == expected


def test_bump_uses_highest_merged_intent() -> None:
    assert bump_version("1.2.3", ["fix: one", "feat(api): two"]) == "1.3.0"
    assert bump_version("1.2.3", ["docs: one"]) is None
    assert (
        bump_version("1.2.3", ["fix: one\n\nBREAKING CHANGE: API"]) == "2.0.0"
    )


def promotion_evidence(
    kind: str, intent: str, number: int
) -> dict[str, object]:
    """Create one compact, verified delivery-boundary fixture."""
    title = {
        "no-release": "docs: work",
        "patch": "fix: work",
        "minor": "feat: work",
        "major": "feat!: work",
    }[intent]
    evidence: dict[str, object] = {
        "gate": "passed",
        "route": {
            "kind": kind,
            "milestone": 7 if kind == "milestone" else None,
        },
        "head_ref": "dev/m7-staged-ci" if kind == "milestone" else "dev/next",
        "pull_request": number + 100,
        "workflow_run": f"https://example.test/runs/{number}",
        "included_issues": [{"number": number, "title": "Work"}],
        "release": {
            "intent": intent,
            "included_pull_requests": [
                {
                    "number": number,
                    "title": title,
                    "intent": intent,
                    **({"issue": number} if kind == "milestone" else {}),
                }
            ],
        },
        "canary": {"state": "blocked", "result": "artifact-only"},
        "full_check": {"context": "verify", "status": "required-peer-check"},
        "post_merge": {
            "main_sha": f"sha-{number}",
            "tree_identity": "verified",
        },
    }
    if kind == "milestone":
        evidence["milestone_promotion"] = {
            "mode": "checkpoint",
            "declared_issues": [number],
        }
    return evidence


@pytest.mark.parametrize(
    "kind",
    ["milestone", "standalone-batch", "isolated", "hotfix", "release-recovery"],
)
def test_release_boundary_traces_each_delivery_route(kind: str) -> None:
    """Milestone, standalone, and hotfix batches retain promotion provenance."""
    result = aggregate_release_boundaries(
        [promotion_evidence(kind, "patch", 10)], "main", "promotion"
    )
    assert result["eligible"] is True
    assert result["release"]["intent"] == "patch"
    assert result["boundaries"][0]["kind"] == kind
    assert result["boundaries"][0]["included_issues"] == [
        {"number": 10, "title": "Work"}
    ]
    if kind == "milestone":
        assert result["boundaries"][0]["milestone_promotion"] == {
            "mode": "checkpoint",
            "declared_issues": [10],
        }
    else:
        assert "milestone_promotion" not in result["boundaries"][0]


@pytest.mark.parametrize(
    "promotion",
    [
        None,
        {"mode": "unknown", "declared_issues": [10]},
        {"mode": "checkpoint", "declared_issues": None},
        {"mode": "checkpoint", "declared_issues": [10, 10]},
        {"mode": "checkpoint", "declared_issues": [11]},
        {"mode": "final", "declared_issues": []},
    ],
)
def test_milestone_release_boundary_rejects_invalid_scope(
    promotion: object,
) -> None:
    """Release eligibility requires canonical milestone Issue evidence."""
    evidence = promotion_evidence("milestone", "patch", 10)
    if promotion is None:
        evidence.pop("milestone_promotion")
    else:
        evidence["milestone_promotion"] = promotion
    with pytest.raises(ValueError, match=r"milestone|checkpoint"):
        aggregate_release_boundaries([evidence], "main", "promotion")


def test_milestone_release_boundary_binds_issues_to_pull_requests() -> None:
    """Included Issue evidence cannot omit or invent reviewed PR scope."""
    evidence = promotion_evidence("milestone", "patch", 10)
    release = evidence["release"]
    assert isinstance(release, dict)
    pull_requests = release["included_pull_requests"]
    assert isinstance(pull_requests, list)
    assert isinstance(pull_requests[0], dict)
    pull_requests[0].pop("issue")
    with pytest.raises(ValueError, match="no Issue binding"):
        aggregate_release_boundaries([evidence], "main", "promotion")
    evidence = promotion_evidence("milestone", "patch", 10)
    evidence["included_issues"] = [{"number": 11, "title": "Invented"}]
    with pytest.raises(ValueError, match="does not match its PRs"):
        aggregate_release_boundaries([evidence], "main", "promotion")


def test_final_milestone_release_boundary_keeps_canonical_scope() -> None:
    """Final mode uses the same PR-to-Issue binding without a declaration."""
    evidence = promotion_evidence("milestone", "patch", 10)
    evidence["milestone_promotion"] = {
        "mode": "final",
        "declared_issues": None,
    }
    result = aggregate_release_boundaries([evidence], "main", "promotion")
    assert result["boundaries"][0]["milestone_promotion"] == {
        "mode": "final",
        "declared_issues": None,
    }


def test_non_milestone_boundary_rejects_milestone_scope() -> None:
    """Standalone evidence cannot smuggle a milestone checkpoint."""
    evidence = promotion_evidence("standalone-batch", "patch", 10)
    evidence["milestone_promotion"] = None
    with pytest.raises(ValueError, match="non-milestone"):
        aggregate_release_boundaries([evidence], "main", "promotion")


def test_release_boundary_uses_highest_intent_and_is_idempotent() -> None:
    """Retries converge on the same audited batch and highest SemVer intent."""
    boundaries = [
        promotion_evidence("milestone", "patch", 10),
        promotion_evidence("standalone-batch", "minor", 11),
    ]
    first = aggregate_release_boundaries(
        boundaries, "main", "release-follow-up"
    )
    second = aggregate_release_boundaries(
        boundaries, "main", "release-follow-up"
    )
    assert first == second
    assert first["release"]["intent"] == "minor"
    assert [
        item["number"] for item in first["release"]["included_pull_requests"]
    ] == [
        10,
        11,
    ]


def test_no_release_boundary_stops_empty_versions() -> None:
    """A docs/governance-only delivery batch is recorded but cannot publish."""
    result = aggregate_release_boundaries(
        [promotion_evidence("milestone", "no-release", 10)],
        "main",
        "promotion",
    )
    assert result["eligible"] is False
    assert result["release"]["intent"] == "no-release"
    assert release_boundary_errors(result, "main")


def test_unexpected_main_commit_is_verification_only() -> None:
    """Unrecognized main history fails closed with an actionable reason."""
    result = simple_release_boundary(
        "unexpected", "main", reason="No reviewed pull request found"
    )
    assert result["eligible"] is False
    assert release_boundary_errors(result, "main") == [
        "No reviewed pull request found",
        "release source kind is not eligible: unexpected",
    ]


def test_release_source_must_match_the_tag_commit() -> None:
    """A valid batch cannot be replayed for a different source tree."""
    result = aggregate_release_boundaries(
        [promotion_evidence("hotfix", "patch", 10)], "main", "promotion"
    )
    assert release_boundary_errors(result, "other") == [
        "release source does not match the tag commit"
    ]


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", *arguments],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_release_surfaces(root: Path, version: str) -> None:
    """Create the minimum governed release surfaces used by direct mode."""
    (root / ".release-please-manifest.json").write_text(
        json.dumps({".": version}) + "\n", encoding="utf-8"
    )
    (root / "version.txt").write_text(f"{version}\n", encoding="utf-8")
    (root / "README.md").write_text(
        f"v{version} <!-- x-release-please-version -->\n", encoding="utf-8"
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## v{version}\n", encoding="utf-8"
    )


def test_release_plan_uses_reachable_tags_and_commit_order(
    tmp_path: Path,
) -> None:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    (tmp_path / ".release-please-manifest.json").write_text(
        '{".": "0.1.0"}\n', encoding="utf-8"
    )
    (tmp_path / "file").write_text("one\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: initial capability")
    first = git(tmp_path, "rev-parse", "HEAD")
    assert release_plan(tmp_path, first) == ("v0.2.0", "0.2.0")
    git(tmp_path, "tag", "v0.2.0")
    assert release_plan(tmp_path, first) == ("v0.2.0", "0.2.0")
    (tmp_path / "file").write_text("two\n", encoding="utf-8")
    git(tmp_path, "commit", "-am", "fix: follow-up")
    second = git(tmp_path, "rev-parse", "HEAD")
    assert release_plan(tmp_path, second) == ("v0.2.1", "0.2.1")


def test_release_plan_parses_every_git_log_record(tmp_path: Path) -> None:
    """A leading newline after a record separator cannot hide older intent."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    (tmp_path / ".release-please-manifest.json").write_text(
        '{".": "0.1.0"}\n', encoding="utf-8"
    )
    (tmp_path / "file").write_text("baseline\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    git(tmp_path, "tag", "v0.1.0")
    (tmp_path / "file").write_text("feature\n", encoding="utf-8")
    git(tmp_path, "commit", "-am", "feat: add release capability")
    (tmp_path / "file").write_text("docs\n", encoding="utf-8")
    git(tmp_path, "commit", "-am", "docs: explain release")

    assert release_plan(tmp_path, git(tmp_path, "rev-parse", "HEAD")) == (
        "v0.2.0",
        "0.2.0",
    )


class FakeAPI:
    def __init__(self, remote_sha: str, pr_status: int = 409) -> None:
        self.remote_sha = remote_sha
        self.pr_status = pr_status
        self.calls: list[tuple[str, str]] = []

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, object]:
        del payload
        self.calls.append((method, path))
        if method == "POST" and path.endswith("/pulls"):
            return self.pr_status, {}
        if method == "POST" and path.endswith("/git/refs"):
            return 422, {}
        if method == "POST" and path.endswith("/releases"):
            return 422, {}
        if method == "POST" and path.endswith("/dispatches"):
            return 422, {}
        if method == "GET" and "/git/ref/heads/" in path:
            return 200, {"object": {"sha": self.remote_sha}}
        raise AssertionError((method, path))


def test_out_of_order_push_is_superseded(tmp_path: Path) -> None:
    expected = "a" * 40
    newer = "b" * 40
    payload, failed = direct_release(
        FakeAPI(newer),
        "owner/repo",
        expected,
        "main",
        "release.yml",
        tmp_path,
    )
    assert not failed
    assert payload["mode"] == "verification-only"
    assert payload["status"] == "superseded"


def test_runtime_policy_drift_changes_the_selected_path(tmp_path: Path) -> None:
    payload, failed = direct_release(
        FakeAPI("a" * 40, pr_status=422),
        "owner/repo",
        "a" * 40,
        "main",
        "release.yml",
        tmp_path,
    )
    assert not failed
    assert payload["mode"] == "release-pr"
    assert "status" not in payload


class DirectReleaseAPI:
    def __init__(self, sha: str) -> None:
        self.sha = sha
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, object]:
        self.calls.append((method, path, payload))
        if method == "POST" and path.endswith("/pulls"):
            return 409, {}
        if method == "POST" and path.endswith("/git/refs"):
            ref = payload.get("ref") if payload else None
            return (
                (201, {})
                if isinstance(ref, str) and ref.startswith("refs/")
                else (422, {})
            )
        if method == "POST" and path.endswith("/releases"):
            return (
                (201, {"draft": True})
                if payload and payload.get("tag_name")
                else (422, {})
            )
        if method == "POST" and path.endswith("/dispatches"):
            return (
                (204, None)
                if payload and str(payload.get("ref", "")).startswith("v")
                else (422, {})
            )
        if method == "GET" and "/git/ref/heads/" in path:
            return 200, {"object": {"sha": self.sha}}
        if method == "GET" and "/git/ref/tags/" in path:
            return 404, {}
        if method == "GET" and "/releases/tags/" in path:
            return 404, {}
        if method == "GET" and "/actions/workflows/" in path:
            return 200, {"workflow_runs": []}
        raise AssertionError((method, path, payload))


def test_direct_release_creates_one_tag_draft_and_dispatch(
    tmp_path: Path,
) -> None:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.1.0")
    (tmp_path / "file").write_text("baseline\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    git(tmp_path, "tag", "v0.1.0")
    write_release_surfaces(tmp_path, "0.2.0")
    (tmp_path / "file").write_text("content\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: direct release")
    sha = git(tmp_path, "rev-parse", "HEAD")
    api = DirectReleaseAPI(sha)

    payload, failed = direct_release(
        api,
        "owner/repo",
        sha,
        "main",
        "release.yml",
        tmp_path,
        "12345",
    )

    assert not failed
    assert payload["status"] == "dispatched"
    assert payload["tag"] == "v0.2.0"
    assert any(
        method == "POST"
        and path.endswith("/git/refs")
        and body == {"ref": "refs/tags/v0.2.0", "sha": sha}
        for method, path, body in api.calls
    )
    assert any(
        method == "POST"
        and path.endswith("/dispatches")
        and body == {"ref": "v0.2.0", "inputs": {"source_run_id": "12345"}}
        for method, path, body in api.calls
    )


def test_direct_release_refuses_an_unmaterialized_version(
    tmp_path: Path,
) -> None:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.1.0")
    (tmp_path / "file").write_text("baseline\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    git(tmp_path, "tag", "v0.1.0")
    (tmp_path / "file").write_text("fix\n", encoding="utf-8")
    git(tmp_path, "commit", "-am", "fix: direct release")
    sha = git(tmp_path, "rev-parse", "HEAD")
    api = DirectReleaseAPI(sha)

    payload, failed = direct_release(
        api, "owner/repo", sha, "main", "release.yml", tmp_path
    )

    assert not failed
    assert payload["mode"] == "verification-only"
    assert payload["status"] == "version-not-materialized"
    assert payload["tag"] == "v0.1.1"
    assert not any("/git/ref/tags/" in path for _, path, _ in api.calls)


def test_prepare_requires_tag_version_without_mutating_files(
    tmp_path: Path,
) -> None:
    write_release_surfaces(tmp_path, "0.2.0")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.2.0"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "demo"\nversion = "0.2.0"\n', encoding="utf-8"
    )

    before = {
        path: path.read_text(encoding="utf-8")
        for path in tmp_path.iterdir()
        if path.is_file()
    }
    assert verify_release_version(tmp_path, "0.2.0") == "0.2.0"
    assert before == {
        path: path.read_text(encoding="utf-8")
        for path in tmp_path.iterdir()
        if path.is_file()
    }

    errors = release_version_errors(tmp_path, "0.2.1")
    assert ".release-please-manifest.json is 0.2.0, expected 0.2.1" in errors
    assert "CHANGELOG.md has no 0.2.1 release entry" in errors

    (tmp_path / "README.md").write_text(
        "No version marker.\n", encoding="utf-8"
    )
    errors = release_version_errors(tmp_path, "0.2.0")
    assert "README.md has no x-release-please-version marker" in errors
