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
detect_runtime_capabilities = MODULE["detect_runtime_capabilities"]
prepare_release_candidate = MODULE["prepare_release_candidate"]
preflight_capabilities = MODULE["preflight_capabilities"]
preflight_policy_observations = MODULE["preflight_policy_observations"]
release_intent = MODULE["release_intent"]
release_follow_up_errors = MODULE["release_follow_up_errors"]
release_boundary_errors = MODULE["release_boundary_errors"]
release_plan = MODULE["release_plan"]
release_plan_report = MODULE["release_plan_report"]
release_version_errors = MODULE["release_version_errors"]
report = MODULE["report"]
select_release_mode = MODULE["select_release_mode"]
simple_release_boundary = MODULE["simple_release_boundary"]
verify_release_version = MODULE["verify_release_version"]
verify_candidate_version = MODULE["verify_candidate_version"]
workflow_policy_observations = MODULE["workflow_policy_observations"]
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
        head="release/v1.2.3",
        actor="maintainer",
        actor_permission="maintain",
        commits=[
            {
                "sha": valid_sha,
                "author": {"login": "maintainer"},
                "committer": {"login": "web-flow"},
                "commit": {
                    "verification": {
                        "verified": False,
                        "reason": "unsigned",
                    }
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
    pull_requests: str,
    contents: str,
    release: str,
    dispatch: str,
    immutable_releases: str = "allowed",
) -> dict[str, object]:
    return {
        "actions_pull_requests": Capability(pull_requests, "test"),
        "contents": Capability(contents, "test"),
        "immutable_releases": Capability(immutable_releases, "test"),
        "release": Capability(release, "test"),
        "dispatch": Capability(dispatch, "test"),
    }


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (("allowed", "allowed", "allowed", "allowed"), "automatic"),
        (
            ("allowed", "unknown", "unknown", "unknown"),
            "blocked",
        ),
        (("blocked", "allowed", "allowed", "allowed"), "guided"),
        (("unknown", "allowed", "allowed", "allowed"), "guided"),
        (("blocked", "blocked", "allowed", "allowed"), "blocked"),
        (("unknown", "allowed", "unknown", "allowed"), "blocked"),
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


def test_cli_preflight_separates_policy_from_token_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readable policy settings never masquerade as workflow-token access."""
    monkeypatch.setattr(MODULE["shutil"], "which", lambda _: "/usr/bin/gh")

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        allowed = not command[-1].startswith("orgs/")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"can_approve_pull_request_reviews": allowed}),
            stderr="",
        )

    monkeypatch.setattr(
        MODULE["subprocess"],
        "run",
        fake_run,
    )

    token_permissions = preflight_capabilities("owner/repo")
    policies = preflight_policy_observations("owner/repo")
    payload = report(token_permissions, "cli-preflight", policies=policies)

    assert payload["organization_policy"]["state"] == "blocked"
    assert payload["repository_setting"]["state"] == "allowed"
    assert payload["token_permissions"]["actions_pull_requests"]["state"] == (
        "unknown"
    )
    assert payload["effective"]["mode"] == "blocked"


@pytest.mark.parametrize("status", [403, 409])
def test_pr_policy_block_uses_guided_mode_without_publishing(
    status: int,
) -> None:
    """A blocked bot PR is not permission to create tags or Releases."""

    class ProbeAPI:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict[str, object] | None]] = []

        def request(
            self,
            method: str,
            path: str,
            payload: dict[str, object] | None = None,
        ) -> tuple[int, object]:
            self.calls.append((method, path, payload))
            if path.endswith("/pulls"):
                return status, {}
            if path.endswith("/immutable-releases"):
                return 200, {"enabled": True}
            return 422, {}

    api = ProbeAPI()
    capabilities = detect_runtime_capabilities(
        api, "owner/repo", "a" * 40, "main"
    )

    assert report(capabilities, "test")["mode"] == "guided"
    assert not any(
        path.endswith("/releases") and bool(payload and payload.get("tag_name"))
        for _, path, payload in api.calls
    )
    assert not any("/dispatches" in path for _, path, _ in api.calls)


@pytest.mark.parametrize("status", [0, 403, 409])
@pytest.mark.parametrize("endpoint", ["git/refs", "releases"])
def test_unproven_publication_capability_is_blocked(
    status: int, endpoint: str
) -> None:
    """Guided candidate creation never masks unavailable publication."""

    class ProbeAPI:
        def request(
            self,
            method: str,
            path: str,
            payload: dict[str, object] | None = None,
        ) -> tuple[int, object]:
            del method, payload
            if path.endswith("/pulls"):
                return 403, {}
            if path.endswith("/immutable-releases"):
                return 200, {"enabled": True}
            if endpoint in path:
                return status, {}
            return 422, {}

    observed = detect_runtime_capabilities(
        ProbeAPI(), "owner/repo", "a" * 40, "main"
    )

    assert report(observed, "test")["mode"] == "blocked"


def test_disabled_immutable_releases_block_publication() -> None:
    """Do not publish into a repository that cannot preserve a release."""

    class ProbeAPI:
        def request(
            self,
            method: str,
            path: str,
            payload: dict[str, object] | None = None,
        ) -> tuple[int, object]:
            del method, payload
            if path.endswith("/pulls"):
                return 422, {}
            if path.endswith("/immutable-releases"):
                return 200, {"enabled": False, "enforced_by_owner": False}
            return 422, {}

    observed = detect_runtime_capabilities(
        ProbeAPI(), "owner/repo", "a" * 40, "main"
    )

    assert observed["immutable_releases"].state == "blocked"
    assert report(observed, "test")["mode"] == "blocked"


def test_capability_report_separates_policy_token_and_effective_state() -> None:
    """Do not collapse parent policy, repository setting, and token access."""

    class ProbeAPI:
        def request(
            self,
            method: str,
            path: str,
            payload: dict[str, object] | None = None,
        ) -> tuple[int, object]:
            del method, payload
            if path.startswith("orgs/"):
                return 200, {"can_approve_pull_request_reviews": False}
            return 200, {"can_approve_pull_request_reviews": True}

    policies = workflow_policy_observations(ProbeAPI(), "owner/repo")
    payload = report(
        capabilities("allowed", "allowed", "allowed", "unknown"),
        "test",
        policies=policies,
    )

    assert payload["organization_policy"]["state"] == "blocked"
    assert payload["repository_setting"]["state"] == "allowed"
    assert payload["token_permissions"]["actions_pull_requests"]["state"] == (
        "allowed"
    )
    assert payload["effective"]["actions_pull_requests"]["state"] == "blocked"
    assert payload["effective"]["mode"] == "guided"


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
        "head_ref": (
            "dev/m7-staged-ci" if kind == "milestone" else "fix/42-outage"
        ),
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


@pytest.mark.parametrize("kind", ["milestone", "hotfix"])
def test_release_boundary_traces_each_delivery_route(kind: str) -> None:
    """Milestone and hotfix batches retain promotion provenance."""
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
    evidence = promotion_evidence("isolated", "patch", 10)
    evidence["milestone_promotion"] = None
    with pytest.raises(ValueError, match="non-milestone"):
        aggregate_release_boundaries([evidence], "main", "promotion")


def test_release_boundary_uses_highest_intent_and_is_idempotent() -> None:
    """Retries converge on the same audited batch and highest SemVer intent."""
    boundaries = [
        promotion_evidence("milestone", "patch", 10),
        promotion_evidence("hotfix", "minor", 11),
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


def test_release_boundary_aggregates_direct_main_and_promotion_history() -> (
    None
):
    """Standalone and bot changes retain intent beside promotion evidence."""
    standalone = simple_release_boundary(
        "main-strategy", "sha-20", title="feat: standalone", pull_request=20
    )
    bot = simple_release_boundary(
        "main-strategy", "sha-21", title="fix: dependency", pull_request=21
    )
    result = aggregate_release_boundaries(
        [standalone, bot, promotion_evidence("milestone", "patch", 10)],
        "main",
        "release-follow-up",
    )
    assert result["release"]["intent"] == "minor"
    assert [
        item["number"] for item in result["release"]["included_pull_requests"]
    ] == [10, 20, 21]
    assert {item["kind"] for item in result["boundaries"]} == {
        "main-strategy",
        "milestone",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("release_eligible", False),
        ("post_merge", {"tree_identity": "failed"}),
    ],
)
def test_release_boundary_rejects_ineligible_historical_evidence(
    field: str, value: object
) -> None:
    """A later release follow-up cannot launder a failed promotion."""
    evidence = promotion_evidence("milestone", "patch", 10)
    evidence[field] = value
    with pytest.raises(ValueError, match="invalid promotion evidence"):
        aggregate_release_boundaries([evidence], "main", "release-follow-up")


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


def test_guided_candidate_only_materializes_local_release_files(
    tmp_path: Path,
) -> None:
    """The fallback never calls GitHub or creates a tag itself."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.1.0")
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "simple",
                "packages": {
                    ".": {
                        "component": "demo",
                        "extra-files": [
                            {"type": "generic", "path": "README.md"}
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    git(tmp_path, "tag", "v0.1.0")
    (tmp_path / "feature").write_text("new\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: guided release")
    sha = git(tmp_path, "rev-parse", "HEAD")

    payload = prepare_release_candidate(tmp_path, sha)

    assert payload["tag"] == "v0.2.0"
    assert payload["branch"] == "release/v0.2.0"
    assert json.loads(
        (tmp_path / ".release-please-manifest.json").read_text(encoding="utf-8")
    ) == {".": "0.2.0"}
    assert (tmp_path / "version.txt").read_text(encoding="utf-8") == "0.2.0\n"
    assert "## [0.2.0]" in (tmp_path / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
    assert git(tmp_path, "tag", "--points-at", sha) == ""
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore(main): release 0.2.0")
    report_payload = release_plan_report(tmp_path, "HEAD")
    assert report_payload["version"] == "0.2.0"
    assert report_payload["status"] == "candidate"


def test_candidate_version_is_recomputed_from_base(tmp_path: Path) -> None:
    """A self-consistent v99 candidate cannot override the base decision."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.1.0")
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "simple",
                "packages": {
                    ".": {
                        "component": "demo",
                        "extra-files": [
                            {"type": "generic", "path": "README.md"}
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    git(tmp_path, "tag", "v0.1.0")
    (tmp_path / "feature").write_text("new\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: expected minor")
    base_sha = git(tmp_path, "rev-parse", "HEAD")
    write_release_surfaces(tmp_path, "99.0.0")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore(main): release 99.0.0")

    with pytest.raises(ValueError, match=r"expected 0\.2\.0"):
        verify_candidate_version(tmp_path, base_sha)


def test_guided_rust_candidate_updates_and_checks_cargo_lock(
    tmp_path: Path,
) -> None:
    """Keep the Rust manifest and lockfile aligned for locked CI."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    (tmp_path / ".release-please-manifest.json").write_text(
        '{".": "0.1.0"}\n', encoding="utf-8"
    )
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "rust",
                "packages": {".": {"component": "demo"}},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "Cargo.lock").write_text(
        'version = 4\n\n[[package]]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.1.0]\n", encoding="utf-8"
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    git(tmp_path, "tag", "v0.1.0")
    (tmp_path / "src.rs").write_text("// feature\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: add Rust support")

    payload = prepare_release_candidate(tmp_path, "HEAD")

    assert payload["version"] == "0.2.0"
    assert 'version = "0.2.0"' in (tmp_path / "Cargo.toml").read_text(
        encoding="utf-8"
    )
    assert 'version = "0.2.0"' in (tmp_path / "Cargo.lock").read_text(
        encoding="utf-8"
    )
    assert release_version_errors(tmp_path, "0.2.0") == []

    (tmp_path / "Cargo.lock").write_text(
        'version = 4\n\n[[package]]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    assert "Cargo.lock is 0.1.0, expected 0.2.0" in release_version_errors(
        tmp_path, "0.2.0"
    )


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
