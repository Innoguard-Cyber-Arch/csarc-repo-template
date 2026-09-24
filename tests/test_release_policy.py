"""Tests for adaptive release capability and version decisions."""

from __future__ import annotations

import json
import os
import re
import runpy
import subprocess
from pathlib import Path
from typing import cast

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "release_policy.py")
)
Capability = MODULE["Capability"]
PUBLISH_CAPABILITIES = MODULE["PUBLISH_CAPABILITIES"]
GitHubAPI = MODULE["GitHubAPI"]
aggregate_release_boundaries = MODULE["aggregate_release_boundaries"]
bump_version = MODULE["bump_version"]
classify_probe = MODULE["classify_probe"]
detect_runtime_capabilities = MODULE["detect_runtime_capabilities"]
main = MODULE["main"]
prepare_release_candidate = MODULE["prepare_release_candidate"]
preflight_capabilities = MODULE["preflight_capabilities"]
preflight_policy_observations = MODULE["preflight_policy_observations"]
release_intent = MODULE["release_intent"]
release_follow_up_errors = MODULE["release_follow_up_errors"]
release_boundary_errors = MODULE["release_boundary_errors"]
release_phase = MODULE["release_phase"]
release_plan = MODULE["release_plan"]
release_plan_report = MODULE["release_plan_report"]
release_version_errors = MODULE["release_version_errors"]
report = MODULE["report"]
retention_report = MODULE["retention_report"]
select_release_mode = MODULE["select_release_mode"]
simple_release_boundary = MODULE["simple_release_boundary"]
verify_release_version = MODULE["verify_release_version"]
verify_candidate_version = MODULE["verify_candidate_version"]
verify_delivery_version = MODULE["verify_delivery_version"]
verify_promotion_version = MODULE["verify_promotion_version"]
workflow_policy_observations = MODULE["workflow_policy_observations"]
optional_integration_preflight = MODULE["optional_integration_preflight"]
_write_release_version = MODULE["_write_release_version"]


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


def test_operator_override_forces_guided_over_automatic() -> None:
    """An operator can route an otherwise-Automatic release to Guided.

    This is the Issue #589 trigger extension: the operator or an agent has
    judged Actions or its webhook delivery currently unhealthy, which has
    no corresponding capability probe (unlike an organization policy that
    blocks Actions pull requests), so it can only be asserted explicitly.
    """
    mode, reason = select_release_mode(
        capabilities("allowed", "allowed", "allowed", "allowed"),
        operator_reason="hosted runner and pull_request webhook delivery "
        "appear unhealthy (#587)",
    )
    assert mode == "guided"
    assert "#587" in reason
    assert "unhealthy" in reason


def test_operator_override_never_unblocks_a_genuinely_blocked_publish() -> None:
    """An operator override cannot manufacture a publish capability.

    Guided mode still needs a working tag/Release publish capability for
    the identity running it; if that capability is observed blocked or
    unknown, the operator's local-execution judgment about Actions health
    is irrelevant and the release stays blocked, not guided.
    """
    mode, reason = select_release_mode(
        capabilities("allowed", "blocked", "allowed", "allowed"),
        operator_reason="Actions looks unhealthy",
    )
    assert mode == "blocked"
    assert "Actions looks unhealthy" not in reason


def test_operator_override_absent_uses_ordinary_detection() -> None:
    """No override reason falls back to the existing capability-only path."""
    automatic, _ = select_release_mode(
        capabilities("allowed", "allowed", "allowed", "allowed"),
        operator_reason=None,
    )
    assert automatic == "automatic"
    empty_reason, _ = select_release_mode(
        capabilities("allowed", "allowed", "allowed", "allowed"),
        operator_reason="",
    )
    assert empty_reason == "automatic"


def test_report_records_the_operator_override_reason() -> None:
    """The machine-readable report preserves the operator's own wording.

    The release-security-and-dependencies ADR requires recording who made
    this local-execution decision and why; carrying the exact reason string
    through to the JSON report is what lets a merge description or Issue
    comment quote it verbatim as that evidence.
    """
    payload = report(
        capabilities("allowed", "allowed", "allowed", "allowed"),
        "test",
        operator_reason="webhook delivery looked stuck for #587",
    )
    assert payload["mode"] == "guided"
    assert (
        payload["operator_override"] == "webhook delivery looked stuck for #587"
    )

    unset = report(
        capabilities("allowed", "allowed", "allowed", "allowed"), "test"
    )
    assert unset["mode"] == "automatic"
    assert unset["operator_override"] is None


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


def test_cli_preflight_includes_advisory_repo_hygiene_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `preflight` CLI command surfaces Issue #667's stale-branch
    review list as advisory output, reusing the same detection module the
    Milestone preflight subcommand calls, without affecting the existing
    capability `mode`/`reason` decision."""
    monkeypatch.setattr(MODULE["shutil"], "which", lambda _: None)
    canned = {
        "available": True,
        "reason": None,
        "threshold_days": 30,
        "candidates": [
            {
                "name": "fix/441-delivery-manual-contract",
                "last_commit_sha": "a" * 40,
                "last_commit_date": "2026-07-01T00:00:00Z",
                "days_idle": 65,
            }
        ],
        "summary": (
            "1 stale delivery branch candidate(s) for manual review "
            "(no open PR, idle >= 30d): "
            "fix/441-delivery-manual-contract (65d idle). Not deleted "
            "automatically -- confirm each is truly abandoned before "
            "removing it."
        ),
    }
    calls: list[str] = []
    monkeypatch.setattr(
        MODULE["stale_branch_detection"],
        "stale_branch_report",
        lambda repo, **kwargs: (calls.append(repo), canned)[1],
    )

    exit_code = main(["preflight", "--repo", "acme/project"])

    assert exit_code == 0
    assert calls == ["acme/project"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["repo_hygiene"] == canned
    assert payload["mode"] in {"automatic", "guided", "blocked"}


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
            if endpoint in path:
                return status, {}
            return 422, {}

    observed = detect_runtime_capabilities(
        ProbeAPI(), "owner/repo", "a" * 40, "main"
    )

    assert report(observed, "test")["mode"] == "blocked"


def test_immutable_releases_is_no_longer_pre_flight_probed() -> None:
    """Issue #770: publication no longer hinges on an unprovable probe.

    `GET repos/{repo}/immutable-releases` requires repository
    Administration (read), which the Actions `GITHUB_TOKEN` can never
    obtain -- there is no `administration` key in the Actions
    `permissions:` schema (#123/#622/#623/#624/#626). Removing this probe
    is what lets Automatic/Guided stop being permanently `blocked` on it;
    whether Immutable Releases was actually enabled is now proven post-hoc
    by scripts/publish-release verifying GitHub's own signed release
    attestation after publish (see scripts/verify_release_consumption.py),
    not guessed about here beforehand.
    """

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
                return 201, {}
            if path.endswith("/git/refs"):
                return 201, {}
            if path.endswith("/releases"):
                return 201, {}
            if path.endswith("/immutable-releases"):
                raise AssertionError(
                    "detect_runtime_capabilities must not probe "
                    "immutable-releases any more (Issue #770)"
                )
            return 422, {}

    observed = detect_runtime_capabilities(
        ProbeAPI(), "owner/repo", "a" * 40, "main"
    )

    assert "immutable_releases" not in observed
    assert PUBLISH_CAPABILITIES == ("contents", "release")
    payload = report(observed, "test")
    assert payload["mode"] == "automatic"
    assert "immutable_releases" not in payload["token_permissions"]


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


def test_exact_final_alpha_transition_plans_v022_stable(tmp_path: Path) -> None:
    """Retire 0.21 alpha without adding a general legacy version parser."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
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
    write_release_surfaces(tmp_path, "0.17.4")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: prior stable history")
    git(tmp_path, "tag", "v0.17.4")
    write_release_surfaces(tmp_path, "0.21.0-alpha.1")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: final retired prerelease")
    git(tmp_path, "tag", "v0.21.0-alpha.1")
    (tmp_path / "file").write_text("beta stable governance\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: define beta stable governance")

    head = git(tmp_path, "rev-parse", "HEAD")
    assert release_plan(tmp_path, head, phase="stable") == (
        "v0.22.0",
        "0.22.0",
    )
    prepared = prepare_release_candidate(tmp_path, head, phase="stable")
    assert prepared["version"] == "0.22.0"
    assert (tmp_path / "version.txt").read_text(encoding="utf-8") == "0.22.0\n"
    changelog = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "feat: define beta stable governance" in changelog
    assert "feat: prior stable history" not in changelog


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


def test_delivery_version_requires_one_exact_final_release_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ordinary work carries its reviewed release surfaces in the same PR."""
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-09-22T23:59:00Z")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-09-22T23:59:00Z")
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
    base_sha = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "tag", "v0.1.0")
    (tmp_path / "feature").write_text("new\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: same pull request release")
    feature_sha = git(tmp_path, "rev-parse", "HEAD")

    with pytest.raises(ValueError, match="materialization is not exact"):
        verify_delivery_version(tmp_path, base_sha, feature_sha, phase="stable")

    prepare_release_candidate(tmp_path, feature_sha, phase="stable")
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-09-23T00:01:00Z")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-09-23T00:01:00Z")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: materialize stable release")
    head_sha = git(tmp_path, "rev-parse", "HEAD")

    result = verify_delivery_version(
        tmp_path, base_sha, head_sha, phase="stable"
    )
    assert result["status"] == "candidate"
    assert result["version"] == "0.2.0"
    assert result["materialized"] is True
    assert result["base_sha"] == base_sha


def test_delivery_version_rejects_a_stale_release_worthy_branch(
    tmp_path: Path,
) -> None:
    """A materialized delivery must contain the lease-bound destination."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.1.0")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    git(tmp_path, "tag", "v0.1.0")
    git(tmp_path, "branch", "delivery")
    (tmp_path / "main-only").write_text("advance\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "docs: advance main")
    current_base = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "checkout", "delivery")
    (tmp_path / "feature").write_text("new\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "fix: stale delivery")

    with pytest.raises(ValueError, match="current destination base"):
        verify_delivery_version(
            tmp_path,
            current_base,
            git(tmp_path, "rev-parse", "HEAD"),
            phase="stable",
        )


def test_deferred_checkpoint_work_merges_without_a_version(
    tmp_path: Path,
) -> None:
    """Only the checkpoint terminal Issue may materialize the beta."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.1.0")
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {"release-type": "simple", "packages": {".": {"component": "demo"}}}
        ),
        encoding="utf-8",
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    base_sha = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "tag", "v0.1.0")
    git(tmp_path, "checkout", "-b", "dev/m1-demo")
    (tmp_path / "feature").write_text("new\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: deferred checkpoint work")
    feature_sha = git(tmp_path, "rev-parse", "HEAD")

    deferred = verify_delivery_version(
        tmp_path,
        base_sha,
        feature_sha,
        phase="beta",
        checkpoint_role="deferred",
    )
    assert deferred["status"] == "deferred"
    assert deferred["materialized"] is False
    report = release_plan_report(
        tmp_path, feature_sha, phase="beta", checkpoint_role="deferred"
    )
    assert report["status"] == "deferred"
    # Without a checkpoint role the same unmaterialized work stays pending.
    assert (
        release_plan_report(tmp_path, feature_sha, phase="beta")["status"]
        == "pending"
    )

    prepare_release_candidate(tmp_path, feature_sha, phase="beta")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: materialize beta")
    head_sha = git(tmp_path, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="must not materialize a version"):
        verify_delivery_version(
            tmp_path,
            base_sha,
            head_sha,
            phase="beta",
            checkpoint_role="deferred",
        )
    with pytest.raises(ValueError, match="must not materialize a version"):
        release_plan_report(
            tmp_path, head_sha, phase="beta", checkpoint_role="deferred"
        )


def test_squashed_promotion_is_planned_from_its_bridge(
    tmp_path: Path,
) -> None:
    """Issue #1027: main cannot reach delivery betas after a squash merge."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.1.0")
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {"release-type": "simple", "packages": {".": {"component": "demo"}}}
        ),
        encoding="utf-8",
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    git(tmp_path, "tag", "v0.1.0")
    main_sha = git(tmp_path, "rev-parse", "HEAD")

    # A Milestone beta whose core is above main's stable, then more work.
    git(tmp_path, "checkout", "-b", "dev/m1-demo")
    (tmp_path / "feature").write_text("new\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: checkpoint work")
    prepare_release_candidate(tmp_path, "HEAD", phase="beta")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore(main): release 0.2.0-beta.1")
    git(tmp_path, "tag", "v0.2.0-beta.1")
    (tmp_path / "fix").write_text("fixed\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "fix: deferred work")
    delivery = git(tmp_path, "rev-parse", "HEAD")

    # Source-preserving bridge [delivery, main] with the stable candidate.
    bridge = git(
        tmp_path,
        "commit-tree",
        f"{delivery}^{{tree}}",
        "-p",
        delivery,
        "-p",
        main_sha,
        "-m",
        "chore: promote Milestone 1",
    )
    git(tmp_path, "checkout", "--detach", bridge)
    prepared = prepare_release_candidate(tmp_path, "HEAD", phase="stable")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--amend", "--no-edit")
    bridge = git(tmp_path, "rev-parse", "HEAD")

    # The promotion lands on main as a single-parent squash commit.
    squash = git(
        tmp_path,
        "commit-tree",
        f"{bridge}^{{tree}}",
        "-p",
        main_sha,
        "-m",
        "feat: promote Milestone 1",
    )
    git(tmp_path, "checkout", "--detach", squash)

    blind = release_plan_report(tmp_path, squash, phase="stable")
    assert blind["status"] == "pending"
    assert blind["tag"] != prepared["tag"]

    report = release_plan_report(
        tmp_path, squash, phase="stable", source_sha=bridge
    )
    assert report["status"] == "candidate"
    assert report["tag"] == prepared["tag"] == "v0.2.1"
    assert report["materialized"] is True

    with pytest.raises(ValueError, match="source tree does not match"):
        release_plan_report(
            tmp_path, squash, phase="stable", source_sha=delivery
        )


def test_delivery_version_allows_non_release_work_without_materialization(
    tmp_path: Path,
) -> None:
    """Docs-only work does not invent a version commit."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.1.0")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    base_sha = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "tag", "v0.1.0")
    (tmp_path / "docs").write_text("clarify\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "docs: clarify release")

    result = verify_delivery_version(
        tmp_path,
        base_sha,
        git(tmp_path, "rev-parse", "HEAD"),
        phase="stable",
    )
    assert result["status"] == "no-release"
    assert result["materialized"] is False


def test_v022_bridge_cannot_reuse_an_already_published_release(
    tmp_path: Path,
) -> None:
    """Regression for #920: merging tagged v0.22 must plan the next stable."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.21.0-alpha.1")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: retired alpha")
    git(tmp_path, "tag", "v0.21.0-alpha.1")
    git(tmp_path, "checkout", "-b", "delivery")
    (tmp_path / "feature").write_text("new\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: post release work")
    git(tmp_path, "checkout", "main")
    write_release_surfaces(tmp_path, "0.22.0")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore(main): release 0.22.0")
    git(tmp_path, "tag", "v0.22.0")
    git(tmp_path, "checkout", "delivery")
    git(tmp_path, "merge", "--no-ff", "main", "-m", "chore: merge main")

    assert release_plan(
        tmp_path, git(tmp_path, "rev-parse", "HEAD"), phase="stable"
    ) == ("v0.23.0", "0.23.0")


def test_promotion_version_is_materialized_in_the_delivery_pr(
    tmp_path: Path,
) -> None:
    """The promotion head is the exact deterministic version candidate."""
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
    git(tmp_path, "checkout", "-b", "delivery")
    (tmp_path / "feature").write_text("new\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: deliver milestone")
    source_sha = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "checkout", "main")
    (tmp_path / "main-only").write_text("current main\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "docs: advance main")
    git(tmp_path, "checkout", "delivery")
    git(tmp_path, "merge", "--no-ff", "main", "-m", "chore: promotion bridge")
    prepare_release_candidate(tmp_path, "HEAD", phase="beta")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--amend", "--no-edit")
    head_sha = git(tmp_path, "rev-parse", "HEAD")

    result = verify_promotion_version(
        tmp_path, source_sha, head_sha, phase="beta"
    )

    assert result["status"] == "candidate"
    assert result["version"] == "0.2.0-beta.1"
    assert result["materialized"] is True


def init_changelog_repo(root: Path) -> None:
    """Create a repository whose v0.1.0 stable is the previous release."""
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Release Test")
    git(root, "config", "user.email", "release@example.invalid")
    write_release_surfaces(root, "0.1.0")
    (root / "release-please-config.json").write_text(
        json.dumps({"release-type": "simple", "packages": {".": {}}}),
        encoding="utf-8",
    )
    git(root, "add", ".")
    git(root, "commit", "-m", "chore: baseline")
    git(root, "tag", "v0.1.0")


def commit_file(root: Path, name: str, subject: str) -> None:
    (root / name).write_text(f"{subject}\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", subject)


def changelog_section(root: Path, version: str) -> str:
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    return changelog.split(f"## [{version}]")[1].split("\n## ")[0]


def test_promotion_bridge_stable_notes_aggregate_milestone_betas(
    tmp_path: Path,
) -> None:
    """Issue #1018: local bridge prep and hosted verify agree on full notes.

    The delivery source reaches only beta tags, and main published a higher
    stable meanwhile, so a Milestone beta sorts below the previous stable.
    The stable section still starts at that previous stable, lists every
    Milestone fix, and inventories the betas by reachability.
    """
    init_changelog_repo(tmp_path)
    git(tmp_path, "checkout", "-b", "dev/m1-demo")
    commit_file(tmp_path, "a", "fix: repair milestone alpha")
    git(tmp_path, "tag", "v0.1.1-beta.1")
    commit_file(tmp_path, "b", "fix: repair milestone beta")
    git(tmp_path, "tag", "v0.1.1-beta.2")
    source_sha = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "checkout", "main")
    commit_file(tmp_path, "main", "feat: main capability")
    git(tmp_path, "tag", "v0.2.0")
    git(tmp_path, "checkout", "-b", "promote/m1-demo", "dev/m1-demo")
    git(tmp_path, "merge", "--no-ff", "main", "-m", "fix: promote milestone 1")

    payload = prepare_release_candidate(tmp_path, "HEAD", phase="stable")
    version = str(payload["version"])
    section = changelog_section(tmp_path, version)

    assert "fix: repair milestone alpha" in section
    assert "fix: repair milestone beta" in section
    assert "feat: main capability" not in section
    assert "promote milestone 1" not in section
    assert (
        "### Included prereleases\n\n* v0.1.1-beta.1\n* v0.1.1-beta.2\n"
        in section
    )
    # Amend on a later day: the bridge id and committer date change, yet
    # hosted verify must rebuild the same notes from the amended head.
    git(tmp_path, "add", ".")
    subprocess.run(
        ["git", "commit", "--amend", "--no-edit"],  # noqa: S607
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_COMMITTER_DATE": "2099-01-02T00:00:00Z",
        },
    )

    result = verify_promotion_version(
        tmp_path,
        source_sha,
        git(tmp_path, "rev-parse", "HEAD"),
        phase="stable",
    )

    assert result["status"] == "candidate"
    assert result["version"] == version
    assert result["materialized"] is True


def test_stable_notes_start_at_previous_stable_past_newer_beta(
    tmp_path: Path,
) -> None:
    """A higher-precedence beta never truncates a stable section."""
    init_changelog_repo(tmp_path)
    commit_file(tmp_path, "a", "fix: shipped in beta")
    git(tmp_path, "tag", "v0.1.1-beta.1")
    commit_file(tmp_path, "b", "fix: after the beta")

    payload = prepare_release_candidate(tmp_path, "HEAD", phase="stable")
    section = changelog_section(tmp_path, str(payload["version"]))

    assert "fix: shipped in beta" in section
    assert "fix: after the beta" in section
    assert "### Included prereleases\n\n* v0.1.1-beta.1\n" in section


def test_stable_notes_without_betas_omit_included_prereleases(
    tmp_path: Path,
) -> None:
    init_changelog_repo(tmp_path)
    commit_file(tmp_path, "a", "fix: direct stable repair")

    payload = prepare_release_candidate(tmp_path, "HEAD", phase="stable")
    section = changelog_section(tmp_path, str(payload["version"]))

    assert "fix: direct stable repair" in section
    assert "Included prereleases" not in section


def test_beta_notes_start_at_latest_tag_of_any_kind(tmp_path: Path) -> None:
    init_changelog_repo(tmp_path)
    commit_file(tmp_path, "a", "fix: shipped in beta")
    git(tmp_path, "tag", "v0.1.1-beta.1")
    commit_file(tmp_path, "b", "fix: after the beta")

    payload = prepare_release_candidate(tmp_path, "HEAD", phase="beta")
    section = changelog_section(tmp_path, str(payload["version"]))

    assert "fix: after the beta" in section
    assert "fix: shipped in beta" not in section
    assert "Included prereleases" not in section


def test_promotion_version_rejects_non_release_changes(tmp_path: Path) -> None:
    """Version materialization cannot hide unrelated edits in promotion."""
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
    git(tmp_path, "checkout", "-b", "delivery")
    (tmp_path / "feature").write_text("delivery\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "fix: deliver milestone")
    source_sha = git(tmp_path, "rev-parse", "HEAD")
    source_tree = git(tmp_path, "rev-parse", "HEAD^{tree}")
    git(tmp_path, "checkout", "main")
    (tmp_path / "feature").write_text("current main\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "docs: advance main")
    main_sha = git(tmp_path, "rev-parse", "HEAD")
    bridge_sha = git(
        tmp_path,
        "commit-tree",
        source_tree,
        "-p",
        source_sha,
        "-p",
        main_sha,
        "-m",
        "chore: promotion bridge",
    )
    git(tmp_path, "checkout", "delivery")
    git(tmp_path, "reset", "--hard", bridge_sha)
    prepare_release_candidate(tmp_path, "HEAD", phase="beta")
    (tmp_path / "unexpected").write_text("not release metadata\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--amend", "--no-edit")

    with pytest.raises(ValueError, match="materialization is not exact"):
        verify_promotion_version(
            tmp_path,
            source_sha,
            git(tmp_path, "rev-parse", "HEAD"),
            phase="beta",
        )


def test_no_release_promotion_preserves_the_delivery_tree(
    tmp_path: Path,
) -> None:
    """A no-release promotion cannot smuggle any tree change into main."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.1.0")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    source_sha = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "commit", "--allow-empty", "-m", "chore: promotion bridge")
    head_sha = git(tmp_path, "rev-parse", "HEAD")

    result = verify_promotion_version(
        tmp_path, source_sha, head_sha, phase="stable"
    )

    assert result["status"] == "no-release"
    assert result["materialized"] is False

    (tmp_path / "unexpected").write_text("not allowed\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--amend", "--no-edit")
    with pytest.raises(ValueError, match="must preserve"):
        verify_promotion_version(
            tmp_path,
            source_sha,
            git(tmp_path, "rev-parse", "HEAD"),
            phase="stable",
        )


def test_zh_home_version_paragraph_updates_automatically_on_bump(
    tmp_path: Path,
) -> None:
    """Issue #694: prove a real bump keeps a zh-tw home slide's
    basic-mode version mention in sync automatically, not just detect
    drift after the fact (tests/test_homepage_readme_parity.py already
    covers detection). This copies the actual production file -- not a
    synthetic fixture -- so a future regression that moves the version
    back into an unmarked plain-text table cell (the pre-#694 design
    that needed a manual fix on both v0.14.0 and v0.15.0) fails here.
    The baseline version is normalized on marker lines only, not
    hardcoded (Issue #695/#696's own lesson: a literal version string
    goes stale on every release).

    This is intentionally a template-authoring repository test. Generated
    projects keep their own website content under docs/site and do not ship
    this root-specific release marker check."""
    zh_source = (
        Path(__file__).parents[1] / "site/content/_index.zh-tw.md"
    ).read_text(encoding="utf-8")
    marker_lines = [
        line
        for line in zh_source.splitlines()
        if "x-release-please-version" in line
    ]
    if not marker_lines:
        pytest.skip(
            "this project's zh-tw home page has no "
            "x-release-please-version markers to keep in sync"
        )
    assert len(marker_lines) == 2, (
        "expected exactly the legacy badge and basic-mode paragraph "
        "markers; update this test if the zh-tw home slide's version "
        "mentions change"
    )

    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.1.0")
    zh_path = tmp_path / "site/content/_index.zh-tw.md"
    zh_path.parent.mkdir(parents=True)
    baseline_source = "\n".join(
        re.sub(r"v\d+\.\d+\.\d+", "v0.1.0", line)
        if "x-release-please-version" in line
        else line
        for line in zh_source.splitlines()
    )
    zh_path.write_text(baseline_source, encoding="utf-8")
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "simple",
                "packages": {
                    ".": {
                        "component": "demo",
                        "extra-files": [
                            {"type": "generic", "path": "README.md"},
                            {
                                "type": "generic",
                                "path": "site/content/_index.zh-tw.md",
                            },
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

    assert payload["version"] == "0.2.0"
    bumped = zh_path.read_text(encoding="utf-8")
    badge_match = re.search(
        r'<span class="package-badge muted">(v[\d.]+)</span>'
        r"<!-- x-release-please-version -->",
        bumped,
    )
    paragraph_match = re.search(
        r"公版版本[^<]*</strong>(v[\d.]+)<!-- x-release-please-version -->",
        bumped,
    )
    assert badge_match and badge_match.group(1) == "v0.2.0"
    assert paragraph_match and paragraph_match.group(1) == "v0.2.0", (
        "basic-mode version paragraph did not update with the release "
        "bump -- it drifted back to needing a manual fix"
    )


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


@pytest.mark.parametrize(
    ("main_commit", "passes"),
    [(None, True), ("docs: clarify usage", True), ("fix: repair bug", False)],
)
def test_candidate_freshness_follows_current_base_release_intent(
    tmp_path: Path, main_commit: str | None, passes: bool
) -> None:
    """Only release-worthy commits added to main stale a candidate."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    write_release_surfaces(tmp_path, "0.1.0")
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "simple",
                "packages": {".": {"component": "demo"}},
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
    source_sha = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "switch", "-c", "release/v0.2.0")
    write_release_surfaces(tmp_path, "0.2.0")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore(main): release 0.2.0")
    candidate_sha = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "switch", "main")
    if main_commit:
        (tmp_path / "later").write_text(f"{main_commit}\n", encoding="utf-8")
        git(tmp_path, "add", ".")
        git(tmp_path, "commit", "-m", main_commit)
    current_base_sha = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "switch", "release/v0.2.0")

    if passes:
        assert verify_candidate_version(tmp_path, current_base_sha) == (
            "0.2.0",
            candidate_sha,
            source_sha,
        )
    else:
        with pytest.raises(
            ValueError,
            match=(
                rf"candidate {candidate_sha} was built from {source_sha}, "
                rf"but current base {current_base_sha} adds release-worthy"
            ),
        ):
            verify_candidate_version(tmp_path, current_base_sha)


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


# --- Issue #918: release-channel versioning ---------------------------


def test_bump_version_ignores_an_existing_phase_suffix() -> None:
    """bump_version only ever bumps the core; the suffix is applied later."""
    assert bump_version("0.16.0-beta.1", ["fix: one"]) == "0.16.1"
    assert bump_version("0.16.0-beta.3", ["feat: one"]) == "0.17.0"
    assert (
        bump_version("0.16.0-beta.1", ["fix: one\n\nBREAKING CHANGE: x"])
        == "1.0.0"
    )


def test_release_plan_applies_the_declared_phase_to_a_fresh_core_version(
    tmp_path: Path,
) -> None:
    """A --phase input turns the computed core version into X.Y.Z-phase.N."""
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

    assert release_plan(tmp_path, first, phase="beta") == (
        "v0.2.0-beta.1",
        "0.2.0-beta.1",
    )
    # No tag exists yet at this commit, so a repeated call with the same
    # phase recomputes the same first pre-release rather than advancing --
    # advancing to .2 only happens once a .1 tag actually exists.
    assert release_plan(tmp_path, first, phase="beta") == (
        "v0.2.0-beta.1",
        "0.2.0-beta.1",
    )
    git(tmp_path, "tag", "v0.2.0-beta.1")
    assert release_plan(tmp_path, first, phase="beta") == (
        "v0.2.0-beta.1",
        "0.2.0-beta.1",
    )

    (tmp_path / "file").write_text("two\n", encoding="utf-8")
    git(tmp_path, "commit", "-am", "fix: follow-up")
    second = git(tmp_path, "rev-parse", "HEAD")
    # A patch-level change since the last (pre-)release still targets the
    # same next core version by this module's own bump arithmetic; #745
    # owns whether that should instead stay 0.2.0-beta.2.
    assert release_plan(tmp_path, second, phase="beta") == (
        "v0.2.1-beta.1",
        "0.2.1-beta.1",
    )
    assert release_plan(tmp_path, second, phase="stable") == (
        "v0.2.1",
        "0.2.1",
    )


@pytest.mark.parametrize(
    ("existing_beta", "expected"),
    [
        (False, "v0.25.5-beta.1"),
        (True, "v0.25.5-beta.2"),
    ],
)
def test_beta_uses_main_stable_floor_without_expanding_changelog(
    tmp_path: Path, existing_beta: bool, expected: str
) -> None:
    """Trust main's stable floor and preserve off-branch beta numbering."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "simple",
                "packages": {
                    ".": {
                        "component": "demo",
                        "extra-files": ["README.md"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    write_release_surfaces(tmp_path, "0.24.0")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore: baseline")
    git(tmp_path, "tag", "v0.24.0")
    git(tmp_path, "checkout", "-b", "delivery")
    write_release_surfaces(tmp_path, "0.24.1-beta.1")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore(main): release 0.24.1-beta.1")
    git(tmp_path, "tag", "v0.24.1-beta.1")

    git(tmp_path, "checkout", "main")
    write_release_surfaces(tmp_path, "0.25.4")
    (tmp_path / "main-only").write_text("stable work\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: unrelated stable work")
    stable_sha = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "tag", "v0.25.4")
    tree = git(tmp_path, "rev-parse", "HEAD^{tree}")
    orphan_sha = git(
        tmp_path,
        "commit-tree",
        tree,
        "-m",
        "feat: unreviewed future work",
    )
    git(tmp_path, "tag", "v999.0.0", orphan_sha)
    git(tmp_path, "tag", "v998.0.0", stable_sha)
    if existing_beta:
        git(tmp_path, "tag", "v0.25.5-beta.1", stable_sha)

    git(tmp_path, "checkout", "delivery")
    (tmp_path / "main-only").write_text("stable work\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore(sync): merge main into delivery")
    assert (
        subprocess.run(  # noqa: S603
            ["git", "merge-base", "--is-ancestor", stable_sha, "HEAD"],  # noqa: S607
            cwd=tmp_path,
            check=False,
        ).returncode
        == 1
    )
    (tmp_path / "fix").write_text("milestone fix\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "fix: milestone work")

    assert release_plan(tmp_path, "HEAD", phase="beta") == (
        expected,
        expected.removeprefix("v"),
    )
    prepare_release_candidate(tmp_path, "HEAD", phase="beta")
    changelog = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "fix: milestone work" in changelog
    assert "feat: unrelated stable work" not in changelog
    assert "feat: unreviewed future work" not in changelog


def test_beta_rejects_higher_stable_without_a_canonical_main_ref(
    tmp_path: Path,
) -> None:
    """Do not silently trust or ignore a higher tag when main is unknown."""
    git(tmp_path, "init", "-b", "delivery")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "simple",
                "packages": {".": {"component": "demo"}},
            }
        ),
        encoding="utf-8",
    )
    write_release_surfaces(tmp_path, "0.24.1-beta.1")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "chore(main): release 0.24.1-beta.1")
    git(tmp_path, "tag", "v0.24.1-beta.1")
    tree = git(tmp_path, "rev-parse", "HEAD^{tree}")
    orphan_sha = git(
        tmp_path,
        "commit-tree",
        tree,
        "-m",
        "chore(main): release 0.25.4",
    )
    git(tmp_path, "tag", "v0.25.4", orphan_sha)
    (tmp_path / "notes.md").write_text("docs only\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "docs: explain milestone work")
    assert release_plan(tmp_path, "HEAD", phase="beta") is None
    (tmp_path / "fix").write_text("milestone fix\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "fix: milestone work")

    with pytest.raises(
        ValueError,
        match="origin/main and main are unavailable",
    ):
        release_plan(tmp_path, "HEAD", phase="beta")


def test_release_plan_without_phase_still_returns_a_bare_core_version(
    tmp_path: Path,
) -> None:
    """Omitting --phase keeps release_plan's legacy bare-core behavior."""
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


def test_release_plan_reports_an_existing_phase_suffixed_tag_unchanged(
    tmp_path: Path,
) -> None:
    """A tag already at this commit wins regardless of --phase."""
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
    git(tmp_path, "tag", "v0.2.0-beta.1")
    assert release_plan(tmp_path, first, phase="beta") == (
        "v0.2.0-beta.1",
        "0.2.0-beta.1",
    )


def test_write_release_version_normalizes_python_surfaces_to_pep440(
    tmp_path: Path,
) -> None:
    """pyproject.toml gets PEP 440; a non-Python surface stays canonical."""
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {"release-type": "python", "packages": {".": {"component": "demo"}}}
        ),
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    _write_release_version(tmp_path, "0.16.0-beta.1")
    manifest = json.loads(
        (tmp_path / ".release-please-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["."] == "0.16.0-beta.1"
    pyproject = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.16.0b1"' in pyproject


def test_write_release_version_normalizes_init_py_marker_to_pep440(
    tmp_path: Path,
) -> None:
    """The package's own src/<name>/__init__.py marker also needs PEP 440.

    A generated project's own `scripts/verify` compares `__version__`
    against `importlib.metadata.version(...)`, which always reports the
    PEP 440-normalized form -- so this marker must match `pyproject.toml`
    and `uv.lock` (Issue #744), not the canonical SemVer string every
    other extra-file marker (e.g. README.md, docs/index.html) keeps.
    """
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "python",
                "packages": {
                    ".": {
                        "component": "demo",
                        "extra-files": [{"path": "src/demo/__init__.py"}],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    init_py = tmp_path / "src" / "demo" / "__init__.py"
    init_py.parent.mkdir(parents=True)
    init_py.write_text(
        '"""Demo package."""\n\n'
        '__version__ = "0.1.0"  # x-release-please-version\n',
        encoding="utf-8",
    )
    _write_release_version(tmp_path, "0.16.0-beta.1")
    content = init_py.read_text(encoding="utf-8")
    assert '__version__ = "0.16.0b1"  # x-release-please-version' in content


def test_release_version_errors_compares_pep440_for_init_py_marker(
    tmp_path: Path,
) -> None:
    """release_version_errors extracts the compact PEP 440 form correctly.

    Regression for the marker-scan regex, which used to only recognize the
    canonical `-alpha.N`/`-beta.N` shape and silently dropped a compact
    `a1`/`b1` suffix, always reporting the bare core version instead.
    """
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "python",
                "packages": {
                    ".": {
                        "component": "demo",
                        "extra-files": [{"path": "src/demo/__init__.py"}],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".release-please-manifest.json").write_text(
        '{".": "0.16.0-beta.1"}\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## v0.16.0-beta.1\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.16.0b1"\n', encoding="utf-8"
    )
    init_py = tmp_path / "src" / "demo" / "__init__.py"
    init_py.parent.mkdir(parents=True)
    init_py.write_text(
        '"""Demo package."""\n\n'
        '__version__ = "0.16.0b1"  # x-release-please-version\n',
        encoding="utf-8",
    )
    assert release_version_errors(tmp_path, "0.16.0-beta.1") == []

    init_py.write_text(
        '"""Demo package."""\n\n'
        '__version__ = "0.15.0b1"  # x-release-please-version\n',
        encoding="utf-8",
    )
    errors = release_version_errors(tmp_path, "0.16.0-beta.1")
    assert "src/demo/__init__.py is 0.15.0b1, expected 0.16.0b1" in errors


def test_write_release_version_normalizes_uv_lock_extra_file_to_pep440(
    tmp_path: Path,
) -> None:
    """PEP 440 also applies to uv.lock's synced entry, not only pyproject.toml.

    Matches template/.csarc/release-please-config.json.jinja's actual shape:
    uv.lock is a "$.package[...]" extra-file, handled by a different code
    path than pyproject.toml's own primary write.
    """
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "python",
                "packages": {
                    ".": {
                        "component": "demo",
                        "extra-files": [
                            {
                                "type": "toml",
                                "path": "uv.lock",
                                "jsonpath": (
                                    '$.package[?(@.name.value=="demo")].version'
                                ),
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text(
        'version = 4\n\n[[package]]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    _write_release_version(tmp_path, "0.16.0-beta.2")
    pyproject = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    uv_lock = (tmp_path / "uv.lock").read_text(encoding="utf-8")
    assert 'version = "0.16.0b2"' in pyproject
    assert 'version = "0.16.0b2"' in uv_lock


def test_write_release_version_replaces_an_existing_phase_suffix_in_a_marker(
    tmp_path: Path,
) -> None:
    """A generic marker holding an old suffix must not leave it dangling."""
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "simple",
                "packages": {
                    ".": {
                        "component": "demo",
                        "extra-files": ["README.md"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "v0.16.0-alpha.1 <!-- x-release-please-version -->\n",
        encoding="utf-8",
    )
    _write_release_version(tmp_path, "0.16.0-beta.1")
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == (
        "v0.16.0-beta.1 <!-- x-release-please-version -->\n"
    )


def test_release_version_errors_compares_pep440_for_python_surfaces(
    tmp_path: Path,
) -> None:
    """A pyproject.toml holding the canonical (non-PEP440) string is flagged."""
    (tmp_path / "release-please-config.json").write_text(
        json.dumps(
            {"release-type": "python", "packages": {".": {"component": "demo"}}}
        ),
        encoding="utf-8",
    )
    (tmp_path / ".release-please-manifest.json").write_text(
        '{".": "0.16.0-beta.1"}\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## v0.16.0-beta.1\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.16.0b1"\n', encoding="utf-8"
    )
    assert release_version_errors(tmp_path, "0.16.0-beta.1") == []

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.16.0-beta.1"\n',
        encoding="utf-8",
    )
    errors = release_version_errors(tmp_path, "0.16.0-beta.1")
    assert "pyproject.toml is 0.16.0-beta.1, expected 0.16.0b1" in errors


class FakeRetentionAPI:
    """A minimal GitHubAPI stand-in that serves one page of Releases."""

    def __init__(self, releases: list[dict[str, object]]) -> None:
        self.releases = releases

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, object]:
        del payload
        assert method == "GET"
        if "page=1" in path:
            return 200, self.releases
        return 200, []


def test_retention_report_lists_keep_and_delete_without_deleting_anything() -> (
    None
):
    """Issue #744 decision 5: dry-run only, never calls a delete endpoint."""
    api = FakeRetentionAPI(
        [
            {"tag_name": "v0.2.2", "draft": False, "id": 1},
            {"tag_name": "v0.15.6", "draft": False, "id": 2},
            {"tag_name": "0.16.0-beta.1", "draft": False, "id": 3},
            {"tag_name": "0.16.0-beta.2", "draft": False, "id": 4},
            {"tag_name": "0.17.0-beta.1", "draft": False, "id": 5},
            {"tag_name": "still-drafting", "draft": True, "id": 6},
        ]
    )
    payload = retention_report(api, "acme/demo")
    assert payload["dry_run"] is True
    keep = {entry["tag"] for entry in payload["keep"]}
    delete = {entry["tag"] for entry in payload["delete"]}
    assert keep == {"v0.2.2", "v0.15.6", "0.17.0-beta.1"}
    assert delete == {"0.16.0-beta.1", "0.16.0-beta.2"}
    # The draft entry never enters either list -- it is not yet a Release.
    assert "still-drafting" not in keep | delete


def test_main_plan_command_accepts_a_phase_argument(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `plan` CLI subcommand threads --phase through to release_plan."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    (tmp_path / ".release-please-manifest.json").write_text(
        '{".": "0.1.0"}\n', encoding="utf-8"
    )
    (tmp_path / "file").write_text("one\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: initial capability")
    sha = git(tmp_path, "rev-parse", "HEAD")

    assert (
        main(["plan", "--root", str(tmp_path), "--sha", sha, "--phase", "beta"])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == "0.2.0-beta.1"
    assert payload["tag"] == "v0.2.0-beta.1"


def test_main_retention_plan_command_requires_a_token_and_never_deletes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `retention-plan` CLI subcommand fails closed without a token."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="requires GH_TOKEN"):
        main(["retention-plan", "--repo", "acme/demo"])

    monkeypatch.setenv("GH_TOKEN", "test-token")
    releases = [
        {"tag_name": "v1.0.0", "draft": False, "id": 1},
        {"tag_name": "1.1.0-beta.1", "draft": False, "id": 2},
    ]

    def fake_request(
        self: object, method: str, path: str, payload: object = None
    ) -> tuple[int, object]:
        del self, payload
        assert method == "GET"
        return (200, releases) if "page=1" in path else (200, [])

    monkeypatch.setattr(GitHubAPI, "request", fake_request)
    assert main(["retention-plan", "--repo", "acme/demo"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {entry["tag"] for entry in payload["keep"]} == {
        "v1.0.0",
        "1.1.0-beta.1",
    }
    assert payload["delete"] == []
