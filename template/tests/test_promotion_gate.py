"""Tests for delivery promotion and canary evidence."""

from __future__ import annotations

import json
import runpy
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "promotion_gate.py")
)
classify_canary = MODULE["classify_canary"]
finalize = MODULE["finalize"]
finalize_quota_fallback = MODULE["finalize_quota_fallback"]
github_get = MODULE["github_get"]
highest_release_intent = MODULE["highest_release_intent"]
included_pull_requests = MODULE["included_pull_requests"]
main_is_current = MODULE["main_is_current"]
prepare = MODULE["prepare"]
require_zero_step_run = MODULE["require_zero_step_run"]
route_for = MODULE["route_for"]
same_repository = MODULE["same_repository"]
unfinished_milestone_issues = MODULE["unfinished_milestone_issues"]
verify_main = MODULE["verify_main"]
verify_quota_main = MODULE["verify_quota_main"]
_GIT = shutil.which("git")
if _GIT is None:
    raise RuntimeError("Git is required for promotion tests")
GIT: str = _GIT


@pytest.mark.parametrize(
    ("base", "head", "labels", "strategy", "kind", "milestone"),
    [
        ("main", "dev/m7-staged-ci", {"promotion"}, "delivery", "milestone", 7),
        (
            "main",
            "dev/next",
            {"promotion"},
            "delivery",
            "standalone-batch",
            None,
        ),
        ("main", "fix/42-outage", {"hotfix"}, "delivery", "hotfix", None),
        (
            "dev/m7-staged-ci",
            "feat/42-work",
            set(),
            "delivery",
            "not-applicable",
            None,
        ),
        (
            "main",
            "release-please--branches--main",
            set(),
            "delivery",
            "release-follow-up",
            None,
        ),
        ("main", "feat/42-work", set(), "delivery", "invalid-main-route", None),
        ("main", "dev", set(), "dev", "dev-promotion", None),
        ("main", "feat/42-work", set(), "main", "not-applicable", None),
    ],
)
def test_route_for(
    base: str,
    head: str,
    labels: set[str],
    strategy: str,
    kind: str,
    milestone: int | None,
) -> None:
    """Distinguish promotions, hotfixes, and unrelated pull requests."""
    route = route_for(base, head, labels, strategy)
    assert route.kind == kind
    assert route.milestone == milestone


def test_isolated_issue_route_binds_the_issue_number() -> None:
    """A temporary isolated delivery branch belongs to exactly one Issue."""
    route = route_for("main", "dev/i42-payment-soak", {"promotion"}, "delivery")
    assert route.kind == "isolated"
    assert route.issue == 42
    assert route.relevant


@pytest.mark.parametrize(
    ("command", "environment", "state"),
    [
        ("./scripts/canary-smoke", "canary", "allowed"),
        ("", "", "blocked"),
        ("./scripts/canary-smoke", "", "unknown"),
        ("", "canary", "unknown"),
    ],
)
def test_canary_capability_is_explicit(
    command: str, environment: str, state: str
) -> None:
    """Never infer that an external canary exists from partial configuration."""
    assert classify_canary(command, environment).state == state


def test_batch_uses_highest_included_pull_request_intent() -> None:
    """A delivery batch exposes one auditable SemVer decision."""
    assert highest_release_intent(["docs: guide", "fix: timeout"]) == "patch"
    assert highest_release_intent(["fix: timeout", "feat: reports"]) == "minor"
    assert (
        highest_release_intent(["feat!: protocol", "feat: reports"]) == "major"
    )
    assert highest_release_intent(["docs: guide", "ci: tune"]) == "no-release"


def test_included_pull_requests_are_deduplicated_and_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only pull requests merged into the promoted delivery range count."""

    def fake_get(_repo: str, path: str, _token: str) -> object:
        if path.startswith("compare/"):
            return {"commits": [{"sha": "one"}, {"sha": "two"}]}
        if path == "commits/one/pulls":
            return [
                {
                    "number": 10,
                    "title": "fix: timeout",
                    "merged_at": "2026-01-01T00:00:00Z",
                    "base": {"ref": "dev/m7-staged-ci"},
                }
            ]
        return [
            {
                "number": 10,
                "title": "fix: timeout",
                "merged_at": "2026-01-01T00:00:00Z",
                "base": {"ref": "dev/m7-staged-ci"},
            },
            {
                "number": 11,
                "title": "feat: unrelated",
                "merged_at": "2026-01-01T00:00:00Z",
                "base": {"ref": "dev/next"},
            },
        ]

    monkeypatch.setitem(
        included_pull_requests.__globals__, "github_get", fake_get
    )
    assert included_pull_requests(
        "owner/repo", "base", "head", "dev/m7-staged-ci", "token"
    ) == [{"number": 10, "title": "fix: timeout", "intent": "patch"}]


def test_milestone_requires_closed_checked_non_promotion_work() -> None:
    """Block open and unchecked work while ignoring PRs and promotion Issues."""
    issues = [
        {"number": 1, "state": "closed", "body": "- [x] Done", "labels": []},
        {"number": 2, "state": "open", "body": "- [x] Done", "labels": []},
        {"number": 3, "state": "closed", "body": "- [ ] Verify", "labels": []},
        {
            "number": 4,
            "state": "open",
            "body": "",
            "labels": [{"name": "promotion"}],
        },
        {
            "number": 5,
            "state": "open",
            "body": "",
            "labels": [],
            "pull_request": {},
        },
    ]
    assert unfinished_milestone_issues(issues, 4) == [2, 3]


def test_latest_main_requires_matching_base_and_ancestry() -> None:
    """Fail closed when main advanced or the delivery branch omitted it."""
    assert main_is_current("abc", "abc", True)
    assert not main_is_current("new", "old", True)
    assert not main_is_current("abc", "abc", False)


def test_promotion_source_must_be_the_same_repository() -> None:
    """A same-named fork branch cannot enter a protected canary environment."""
    pull_request = {"head": {"repo": {"full_name": "owner/repo"}}}
    assert same_repository(pull_request, "owner/repo")
    assert not same_repository(pull_request, "fork/repo")
    assert not same_repository({"head": {"repo": None}}, "owner/repo")


def test_github_get_uses_authenticated_cli_without_environment_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local promotion preflight must not persist an extracted token."""
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(arguments)
        return SimpleNamespace(stdout='{"state": "open"}')

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert github_get("owner/repo", "issues/42", "") == {"state": "open"}
    assert calls == [["/usr/bin/gh", "api", "repos/owner/repo/issues/42"]]


def test_blocked_run_must_match_head_and_have_no_started_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real hosted test failure cannot be relabeled as quota exhaustion."""

    def zero_step_get(_repo: str, path: str, _token: str) -> object:
        if path.endswith("/jobs"):
            return {"jobs": [{"runner_id": 0, "steps": []}]}
        return {"head_sha": "head", "conclusion": "failure"}

    monkeypatch.setitem(
        require_zero_step_run.__globals__, "github_get", zero_step_get
    )
    run_url = "https://github.com/owner/repo/actions/runs/200"
    require_zero_step_run(run_url, "owner/repo", "head", "")

    def started_get(_repo: str, path: str, _token: str) -> object:
        if path.endswith("/jobs"):
            return {"jobs": [{"runner_id": 7, "steps": [{"name": "tests"}]}]}
        return {"head_sha": "head", "conclusion": "failure"}

    monkeypatch.setitem(
        require_zero_step_run.__globals__, "github_get", started_get
    )
    with pytest.raises(RuntimeError, match="zero-step"):
        require_zero_step_run(run_url, "owner/repo", "head", "")


def test_prepare_builds_milestone_candidate_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bind a completed Milestone promotion to its exact candidate tree."""

    def run_git(*arguments: str) -> str:
        result = subprocess.run(  # noqa: S603
            [GIT, *arguments],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return str(result.stdout).strip()

    run_git("init", "-b", "main")
    run_git("config", "user.email", "test@example.com")
    run_git("config", "user.name", "Test")
    (tmp_path / "tracked.txt").write_text("base\n", encoding="utf-8")
    run_git("add", ".")
    run_git("commit", "-m", "base")
    base_sha = run_git("rev-parse", "HEAD")
    run_git("checkout", "-b", "dev/m7-staged-ci")
    (tmp_path / "tracked.txt").write_text("candidate\n", encoding="utf-8")
    run_git("commit", "-am", "candidate")
    head_sha = run_git("rev-parse", "HEAD")
    event = {
        "number": 99,
        "pull_request": {
            "number": 99,
            "title": "feat: promote staged CI",
            "body": "Closes #99",
            "labels": [{"name": "promotion"}],
            "base": {"ref": "main", "sha": base_sha},
            "head": {
                "ref": "dev/m7-staged-ci",
                "sha": head_sha,
                "repo": {"full_name": "owner/repo"},
            },
        },
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")

    def fake_get(_repo: str, path: str, _token: str) -> object:
        if path == "issues/99":
            return {
                "number": 99,
                "state": "open",
                "body": "- [x] Ready",
                "labels": [{"name": "promotion"}],
                "milestone": {"number": 7},
            }
        return {"object": {"sha": base_sha}}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setitem(prepare.__globals__, "github_get", fake_get)
    monkeypatch.setitem(
        prepare.__globals__,
        "milestone_issues",
        lambda *_: [
            {
                "number": 1,
                "title": "Completed work",
                "state": "closed",
                "body": "- [x] Done",
                "labels": [],
            },
            {
                "number": 99,
                "title": "Promotion",
                "state": "open",
                "body": "- [x] Ready",
                "labels": [{"name": "promotion"}],
            },
        ],
    )
    monkeypatch.setitem(
        prepare.__globals__,
        "included_pull_requests",
        lambda *_: [
            {"number": 1, "title": "feat: completed work", "intent": "minor"}
        ],
    )
    output = tmp_path / "promotion.json"
    prepare(
        SimpleNamespace(
            event="pull_request",
            event_path=event_path,
            repo="owner/repo",
            branch_strategy="delivery",
            candidate_sha=head_sha,
            workflow_run="https://example.test/run/1",
            canary_command="",
            canary_environment="",
            archive=tmp_path / "candidate.tar.gz",
            output=output,
            github_output=None,
            summary=None,
        )
    )
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["route"]["kind"] == "milestone"
    assert evidence["candidate_tree"]
    assert evidence["included_issues"] == [
        {"number": 1, "title": "Completed work"}
    ]
    assert evidence["release"] == {
        "intent": "minor",
        "promotion_title": "feat: promote staged CI",
        "included_pull_requests": [
            {
                "number": 1,
                "title": "feat: completed work",
                "intent": "minor",
            }
        ],
    }


def test_finalize_accepts_artifact_only_blocked_canary(tmp_path: Path) -> None:
    """Blocked capability remains evidence without faking a canary pass."""
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text(
        json.dumps({"canary": {"state": "blocked"}}), encoding="utf-8"
    )
    finalize(
        SimpleNamespace(input=source, output=target, canary_result="skipped")
    )
    evidence = json.loads(target.read_text(encoding="utf-8"))
    assert evidence["canary"]["result"] == "artifact-only"
    assert evidence["full_check"]["context"] == "verify"
    assert evidence["gate"] == "passed"


def test_finalize_rejects_failed_configured_canary(tmp_path: Path) -> None:
    """An allowed external canary becomes a real merge gate."""
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps({"canary": {"state": "allowed"}}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="did not succeed"):
        finalize(
            SimpleNamespace(
                input=source,
                output=tmp_path / "target.json",
                canary_result="failure",
            )
        )


def test_finalize_quota_fallback_is_non_release_and_sha_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local promotion evidence stays tied to one clean pull-request head."""
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text(
        json.dumps(
            {
                "repository": "owner/repo",
                "pull_request": 42,
                "route": {"kind": "standalone-batch", "relevant": True},
                "base_sha": "base",
                "head_sha": "head",
                "candidate_sha": "head",
                "candidate_tree": "tree",
                "candidate_archive": {"sha256": "digest"},
                "canary": {"state": "blocked"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "git_output",
        lambda *arguments: "" if arguments[0] == "status" else "head",
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "contains_commit",
        lambda *_: True,
    )

    def fallback_get(_repo: str, path: str, _token: str) -> object:
        if path == "git/ref/heads/main":
            return {"object": {"sha": "base"}}
        if path.endswith("/jobs"):
            return {"jobs": [{"runner_id": 0, "steps": []}]}
        return {"head_sha": "head", "conclusion": "failure"}

    monkeypatch.setitem(
        finalize_quota_fallback.__globals__, "github_get", fallback_get
    )
    finalize_quota_fallback(
        SimpleNamespace(
            input=source,
            output=target,
            attestation_url=(
                "https://github.com/owner/repo/pull/42#issuecomment-100"
            ),
            authorization_url=(
                "https://github.com/owner/repo/pull/42#issuecomment-101"
            ),
            blocked_run_url=["https://github.com/owner/repo/actions/runs/200"],
            verification_command=["./scripts/verify-template.sh"],
        )
    )
    evidence = json.loads(target.read_text(encoding="utf-8"))
    assert evidence["gate"] == "quota-fallback"
    assert evidence["release_eligible"] is False
    assert evidence["full_check"] == {
        "context": "verify",
        "status": "local-quota-attested",
        "commands": ["./scripts/verify-template.sh"],
    }


@pytest.mark.parametrize(
    (
        "route_kind",
        "candidate_sha",
        "canary_state",
        "authorization_url",
        "message",
    ),
    [
        ("standalone-batch", "merge", "blocked", "valid", "must equal"),
        ("standalone-batch", "head", "allowed", "valid", "configured canary"),
        (
            "standalone-batch",
            "head",
            "blocked",
            "wrong",
            "comments on the promotion PR",
        ),
        ("hotfix", "head", "blocked", "valid", "promotion gate"),
    ],
)
def test_finalize_quota_fallback_rejects_unsafe_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    route_kind: str,
    candidate_sha: str,
    canary_state: str,
    authorization_url: str,
    message: str,
) -> None:
    """A fallback cannot drift from the head or replace external controls."""
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "repository": "owner/repo",
                "pull_request": 42,
                "route": {"kind": route_kind, "relevant": True},
                "base_sha": "base",
                "head_sha": "head",
                "candidate_sha": candidate_sha,
                "candidate_tree": "tree",
                "candidate_archive": {"sha256": "digest"},
                "canary": {"state": canary_state},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "git_output",
        lambda *arguments: "" if arguments[0] == "status" else "head",
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "contains_commit",
        lambda *_: True,
    )

    def fallback_get(_repo: str, path: str, _token: str) -> object:
        if path == "git/ref/heads/main":
            return {"object": {"sha": "base"}}
        if path.endswith("/jobs"):
            return {"jobs": [{"runner_id": 0, "steps": []}]}
        return {"head_sha": "head", "conclusion": "failure"}

    monkeypatch.setitem(
        finalize_quota_fallback.__globals__, "github_get", fallback_get
    )
    authorization = (
        "https://github.com/owner/repo/pull/42#issuecomment-101"
        if authorization_url == "valid"
        else "https://github.com/owner/repo/pull/41#issuecomment-101"
    )
    with pytest.raises(RuntimeError, match=message):
        finalize_quota_fallback(
            SimpleNamespace(
                input=source,
                output=tmp_path / "target.json",
                attestation_url=(
                    "https://github.com/owner/repo/pull/42#issuecomment-100"
                ),
                authorization_url=authorization,
                blocked_run_url=[
                    "https://github.com/owner/repo/actions/runs/200"
                ],
                verification_command=["./scripts/verify-template.sh"],
            )
        )


def test_verify_main_rejects_a_different_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A squash result must preserve the exact verified candidate tree."""
    evidence = tmp_path / "evidence.json"
    checks = tmp_path / "checks.json"
    evidence.write_text(
        json.dumps(
            {
                "gate": "passed",
                "repository": "owner/repo",
                "pull_request": 42,
                "head_sha": "head",
                "candidate_tree": "expected",
            }
        ),
        encoding="utf-8",
    )
    checks.write_text(
        json.dumps(
            {"check_runs": [{"name": "verify", "conclusion": "success"}]}
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(
        verify_main.__globals__, "git_output", lambda *_: "different"
    )
    with pytest.raises(RuntimeError, match="tree differs"):
        verify_main(
            SimpleNamespace(
                evidence=evidence,
                checks=checks,
                repo="owner/repo",
                pr_number=42,
                head_sha="head",
                main_sha="main",
                output=tmp_path / "verified.json",
            )
        )


def test_verify_main_requires_successful_full_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Promotion evidence cannot substitute for the full CI result."""
    evidence = tmp_path / "evidence.json"
    checks = tmp_path / "checks.json"
    evidence.write_text(
        json.dumps(
            {
                "gate": "passed",
                "repository": "owner/repo",
                "pull_request": 42,
                "head_sha": "head",
                "candidate_tree": "same",
            }
        ),
        encoding="utf-8",
    )
    checks.write_text(json.dumps({"check_runs": []}), encoding="utf-8")
    monkeypatch.setitem(
        verify_main.__globals__, "git_output", lambda *_: "same"
    )
    with pytest.raises(RuntimeError, match="successful verify"):
        verify_main(
            SimpleNamespace(
                evidence=evidence,
                checks=checks,
                repo="owner/repo",
                pr_number=42,
                head_sha="head",
                main_sha="main",
                output=tmp_path / "verified.json",
            )
        )


def test_verify_quota_main_preserves_non_release_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A locally verified main tree must remain ineligible for release."""
    source = tmp_path / "fallback.json"
    target = tmp_path / "verified.json"
    source.write_text(
        json.dumps(
            {
                "gate": "quota-fallback",
                "release_eligible": False,
                "repository": "owner/repo",
                "pull_request": 42,
                "head_sha": "head",
                "candidate_tree": "tree",
                "full_check": {"status": "local-quota-attested"},
            }
        ),
        encoding="utf-8",
    )

    def fake_git(*arguments: str) -> str:
        if arguments[0] == "status":
            return ""
        if arguments[-1] == "HEAD":
            return "main"
        return "tree"

    monkeypatch.setitem(verify_quota_main.__globals__, "git_output", fake_git)
    verify_quota_main(
        SimpleNamespace(
            evidence=source,
            repo="owner/repo",
            pr_number=42,
            head_sha="head",
            main_sha="main",
            output=target,
        )
    )
    evidence = json.loads(target.read_text(encoding="utf-8"))
    assert evidence["post_merge"]["tree_identity"] == (
        "verified-local-quota-fallback"
    )
    assert evidence["release_eligible"] is False
