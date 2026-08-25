"""Tests for delivery promotion and canary evidence."""

from __future__ import annotations

import hashlib
import json
import runpy
import shutil
import subprocess
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "promotion_gate.py")
)
classify_canary = MODULE["classify_canary"]
finalize = MODULE["finalize"]
finalize_quota_fallback = MODULE["finalize_quota_fallback"]
fallback_statement = MODULE["fallback_statement"]
github_get = MODULE["github_get"]
highest_release_intent = MODULE["highest_release_intent"]
included_pull_requests = MODULE["included_pull_requests"]
local_verification_command = MODULE["local_verification_command"]
main_is_current = MODULE["main_is_current"]
note_quota_fallback = MODULE["note_quota_fallback"]
prepare = MODULE["prepare"]
parser = MODULE["parser"]
quota_fallback_note = MODULE["quota_fallback_note"]
BILLING_GATE_ANNOTATION_MESSAGE = MODULE["BILLING_GATE_ANNOTATION_MESSAGE"]
RejectRedirects = MODULE["RejectRedirects"]
repository_variables = MODULE["repository_variables"]
require_same_preflight = MODULE["require_same_preflight"]
promotion_bridge_source = MODULE["promotion_bridge_source"]
promotion_main_evidence = MODULE["promotion_main_evidence"]
require_zero_step_run = MODULE["require_zero_step_run"]
route_for = MODULE["route_for"]
run_dev_next_preservation = MODULE["run_dev_next_preservation"]
same_repository = MODULE["same_repository"]
unfinished_milestone_issues = MODULE["unfinished_milestone_issues"]
verify_main = MODULE["verify_main"]
verify_quota_main = MODULE["verify_quota_main"]
_GIT = shutil.which("git")
if _GIT is None:
    raise RuntimeError("Git is required for promotion tests")
GIT: str = _GIT


def preservation_evidence() -> dict[str, object]:
    """Return one structured remote checkpoint for quota fallback tests."""
    return {
        "ledger_ref": "refs/heads/csarc/dev-next-preservation-ledger",
        "ledger_commit": "d" * 40,
        "transaction": {
            "schema_version": 1,
            "repository": "owner/repo",
            "pull_request": 42,
            "base_ref": "main",
            "base_sha": "base",
            "head_ref": "dev/next",
            "head_sha": "head",
            "operation_id": "e" * 64,
            "mode": "temporary-auto-delete",
            "prior_auto_delete": True,
            "state": "prepared",
        },
    }


def test_hosted_restoration_is_explicit_and_never_replaces_gh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pass the separate admin secret through the hosted environment."""
    captured: dict[str, object] = {}
    github_value = "github-value"
    admin_value = "admin-value"

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return SimpleNamespace(stdout=json.dumps(preservation_evidence()))

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GH_TOKEN", github_value)
    monkeypatch.setenv("CSARC_SYNC_TOKEN", admin_value)
    monkeypatch.setattr(subprocess, "run", run)
    run_dev_next_preservation(
        "complete-dev-next",
        "owner/repo",
        42,
        "a" * 40,
        "b" * 40,
        "c" * 64,
        "d" * 40,
    )
    command = captured["command"]
    assert isinstance(command, list)
    assert "--hosted" in command
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["GH_TOKEN"] == github_value
    assert environment["CSARC_SYNC_TOKEN"] == admin_value


@pytest.mark.parametrize(
    ("base", "head", "labels", "strategy", "kind", "milestone"),
    [
        ("main", "dev/m7-staged-ci", {"promotion"}, "delivery", "milestone", 7),
        (
            "main",
            "promote/m7-staged-ci",
            {"promotion"},
            "delivery",
            "milestone",
            7,
        ),
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
        (
            "main",
            "promote/next",
            {"promotion"},
            "delivery",
            "standalone-batch",
            None,
        ),
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


@pytest.mark.parametrize(
    ("delivery_branch", "milestone", "expected_number"),
    [
        ("dev/m7-staged-ci", 7, 10),
        ("dev/next", None, 12),
    ],
)
def test_bridge_provenance_accepts_only_eligible_pull_requests(
    monkeypatch: pytest.MonkeyPatch,
    delivery_branch: str,
    milestone: int | None,
    expected_number: int,
) -> None:
    """Accept reviewed sibling work without crossing a delivery boundary."""

    def fake_get(_repo: str, path: str, _token: str) -> object:
        if path.startswith("compare/"):
            return {
                "commits": [
                    {"sha": "work"},
                    {"sha": "bridge"},
                ]
            }
        assert path == "commits/work/pulls"
        return [
            {
                "number": 10,
                "title": "fix: accepted sibling",
                "merged_at": "2026-01-01T00:00:00Z",
                "base": {"ref": "dev/m7-staged-ci"},
            },
            {
                "number": 11,
                "title": "feat: wrong milestone",
                "merged_at": "2026-01-01T00:00:00Z",
                "base": {"ref": "dev/m8-other"},
            },
            {
                "number": 12,
                "title": "feat: standalone",
                "merged_at": "2026-01-01T00:00:00Z",
                "base": {"ref": "dev/next"},
            },
        ]

    monkeypatch.setitem(
        included_pull_requests.__globals__, "github_get", fake_get
    )
    assert included_pull_requests(
        "owner/repo",
        "main",
        "bridge",
        delivery_branch,
        "token",
        milestone=milestone,
        bridge_head_sha="bridge",
    ) == [
        {
            "number": expected_number,
            "title": "fix: accepted sibling"
            if expected_number == 10
            else "feat: standalone",
            "intent": "patch" if expected_number == 10 else "minor",
        }
    ]


def test_bridge_provenance_rejects_an_unreviewed_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every source-side bridge commit must come from a merged Milestone PR."""

    def fake_get(_repo: str, path: str, _token: str) -> object:
        if path.startswith("compare/"):
            return {
                "commits": [
                    {"sha": "unreviewed"},
                    {"sha": "bridge"},
                ]
            }
        return []

    monkeypatch.setitem(
        included_pull_requests.__globals__, "github_get", fake_get
    )
    with pytest.raises(RuntimeError, match="no same-Milestone merged PR"):
        included_pull_requests(
            "owner/repo",
            "main",
            "bridge",
            "promote/m7-staged-ci",
            "token",
            milestone=7,
            bridge_head_sha="bridge",
        )


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


@pytest.mark.parametrize(
    ("bridge_branch", "source_branch", "milestone"),
    [
        ("promote/m7-staged-ci", "dev/m7-staged-ci", 7),
        ("promote/next", "dev/next", None),
    ],
)
def test_promotion_bridge_resolves_conflict_without_changing_source_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bridge_branch: str,
    source_branch: str,
    milestone: int | None,
) -> None:
    """Bridge a real conflict while preserving the source candidate tree."""

    def run_git(
        *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [GIT, *arguments],
            cwd=tmp_path,
            check=check,
            capture_output=True,
            text=True,
        )

    run_git("init", "-b", "main")
    run_git("config", "user.email", "test@example.com")
    run_git("config", "user.name", "Test")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("base\n", encoding="utf-8")
    run_git("add", ".")
    run_git("commit", "-m", "base")

    run_git("checkout", "-b", source_branch)
    tracked.write_text("source\n", encoding="utf-8")
    run_git("commit", "-am", "source")
    source_sha = run_git("rev-parse", "HEAD").stdout.strip()
    source_tree = run_git("rev-parse", "HEAD^{tree}").stdout.strip()

    run_git("checkout", "main")
    tracked.write_text("main\n", encoding="utf-8")
    run_git("commit", "-am", "main")
    base_sha = run_git("rev-parse", "HEAD").stdout.strip()
    assert (
        run_git(
            "merge-tree", "--write-tree", base_sha, source_sha, check=False
        ).returncode
        != 0
    )

    bridge_sha = run_git(
        "commit-tree",
        source_tree,
        "-p",
        source_sha,
        "-p",
        base_sha,
        "-m",
        "promotion bridge",
    ).stdout.strip()

    def fake_get(_repo: str, path: str, _token: str) -> object:
        encoded = urllib.parse.quote(source_branch, safe="")
        assert path == f"git/ref/heads/{encoded}"
        return {"object": {"sha": source_sha}}

    monkeypatch.setitem(
        promotion_bridge_source.__globals__, "github_get", fake_get
    )
    monkeypatch.chdir(tmp_path)
    assert promotion_bridge_source(
        "owner/repo",
        bridge_branch,
        base_sha,
        bridge_sha,
        bridge_sha,
        milestone,
        "token",
    ) == {
        "source_ref": source_branch,
        "source_sha": source_sha,
        "source_tree": source_tree,
    }


@pytest.mark.parametrize(
    ("branch", "milestone", "parents", "candidate_tree", "message"),
    [
        (
            "promote/next",
            7,
            "bridge source main",
            "source-tree",
            "cannot use a Milestone",
        ),
        (
            "promote/m8-other",
            7,
            "bridge source main",
            "source-tree",
            "Milestones differ",
        ),
        (
            "promote/m7-staged-ci",
            7,
            "bridge main source",
            "source-tree",
            "merge current main",
        ),
        (
            "promote/m7-staged-ci",
            7,
            "bridge source main",
            "different-tree",
            "preserve the source tree",
        ),
    ],
)
def test_promotion_bridge_rejects_wrong_scope_graph_or_tree(
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
    milestone: int,
    parents: str,
    candidate_tree: str,
    message: str,
) -> None:
    """Reject cross-Milestone, reversed-parent, or changed-tree bridges."""
    monkeypatch.setitem(
        promotion_bridge_source.__globals__,
        "github_get",
        lambda *_: {"object": {"sha": "source"}},
    )

    def fake_git(*arguments: str) -> str:
        if arguments[0] == "rev-list":
            return parents
        if arguments[-1] == "candidate^{tree}":
            return candidate_tree
        return "source-tree"

    monkeypatch.setitem(
        promotion_bridge_source.__globals__, "git_output", fake_git
    )
    with pytest.raises(RuntimeError, match=message):
        promotion_bridge_source(
            "owner/repo",
            branch,
            "main",
            "bridge",
            "candidate",
            milestone,
            "token",
        )


def test_promotion_accepts_exact_squash_sync_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bind squash evidence to the current main, delivery branch, and head."""
    calls: list[tuple[object, str, str, str, str]] = []

    def merged_sync(
        api: object,
        repo: str,
        delivery_branch: str,
        main_sha: str,
        head_sha: str,
    ) -> int:
        calls.append((api, repo, delivery_branch, main_sha, head_sha))
        return 283

    api = object()
    monkeypatch.setattr(
        MODULE["delivery_sync"], "merged_sync_pr_number", merged_sync
    )
    assert (
        promotion_main_evidence(
            api,
            "owner/repo",
            "main-sha",
            "main-sha",
            "dev/m7-staged-ci",
            "delivery-head",
            False,
        )
        == "squash-sync-pr-283"
    )
    assert calls == [
        (
            api,
            "owner/repo",
            "dev/m7-staged-ci",
            "main-sha",
            "delivery-head",
        )
    ]


def test_promotion_main_evidence_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject main drift, non-delivery routes, absent proof, and API errors."""
    calls = 0

    def no_sync(*_args: object) -> None:
        nonlocal calls
        calls += 1
        return None

    monkeypatch.setattr(
        MODULE["delivery_sync"], "merged_sync_pr_number", no_sync
    )
    api = object()
    assert (
        promotion_main_evidence(
            api, "owner/repo", "main", "main", None, "head", False
        )
        is None
    )
    assert (
        promotion_main_evidence(
            api, "owner/repo", "new", "old", "dev/next", "head", False
        )
        is None
    )
    assert calls == 0
    assert (
        promotion_main_evidence(
            api, "owner/repo", "main", "main", "dev/next", "head", False
        )
        is None
    )
    assert calls == 1

    def failed_sync(*_args: object) -> None:
        raise RuntimeError("find merged sync PR failed with HTTP 500")

    monkeypatch.setattr(
        MODULE["delivery_sync"], "merged_sync_pr_number", failed_sync
    )
    with pytest.raises(RuntimeError, match="HTTP 500"):
        promotion_main_evidence(
            api, "owner/repo", "main", "main", "dev/next", "head", False
        )


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
        if "/jobs?" in path:
            return {
                "total_count": 1,
                "jobs": [
                    {
                        "id": 7,
                        "runner_id": 0,
                        "steps": [],
                        "conclusion": "failure",
                    }
                ],
            }
        if path.startswith("check-runs/7/annotations"):
            return [{"message": BILLING_GATE_ANNOTATION_MESSAGE}]
        return {
            "id": 200,
            "head_sha": "head",
            "head_branch": "dev/next",
            "event": "pull_request",
            "status": "completed",
            "conclusion": "failure",
            "path": ".github/workflows/ci.yml",
            "pull_requests": [{"number": 42}],
            "repository": {"full_name": "owner/repo"},
            "head_repository": {"full_name": "owner/repo"},
        }

    monkeypatch.setitem(
        require_zero_step_run.__globals__, "github_get", zero_step_get
    )
    run_url = "https://github.com/owner/repo/actions/runs/200"
    require_zero_step_run(run_url, "owner/repo", 42, "dev/next", "head", "")

    def started_get(_repo: str, path: str, _token: str) -> object:
        if "/jobs?" in path:
            return {
                "total_count": 1,
                "jobs": [
                    {
                        "runner_id": 7,
                        "steps": [{"name": "tests"}],
                    }
                ],
            }
        return zero_step_get(_repo, path, _token)

    monkeypatch.setitem(
        require_zero_step_run.__globals__, "github_get", started_get
    )
    with pytest.raises(RuntimeError, match="zero-step"):
        require_zero_step_run(run_url, "owner/repo", 42, "dev/next", "head", "")


def _routine_pr_get(
    jobs: list[dict[str, object]],
) -> Callable[[str, str, str], object]:
    def fake_get(_repo: str, path: str, _token: str) -> object:
        if path == "pulls/42":
            return {"head": {"sha": "head", "ref": "dev/next"}}
        if "/jobs?" in path:
            return {"total_count": len(jobs), "jobs": jobs}
        if path.startswith("check-runs/"):
            return [{"message": BILLING_GATE_ANNOTATION_MESSAGE}]
        return {
            "id": 200,
            "head_sha": "head",
            "head_branch": "dev/next",
            "event": "pull_request",
            "status": "completed",
            "conclusion": "failure",
            "path": ".github/workflows/ci.yml",
            "pull_requests": [{"number": 42}],
            "repository": {"full_name": "owner/repo"},
            "head_repository": {"full_name": "owner/repo"},
        }

    return fake_get


def test_note_quota_fallback_prints_note_for_zero_step_block(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A routine PR gets an automatic note once every failure is zero-step."""
    jobs = [{"id": 7, "runner_id": 0, "steps": [], "conclusion": "failure"}]
    monkeypatch.setitem(
        note_quota_fallback.__globals__, "github_get", _routine_pr_get(jobs)
    )
    run_url = "https://github.com/owner/repo/actions/runs/200"
    args = SimpleNamespace(repo="owner/repo", pr=42, blocked_run_url=[run_url])
    note_quota_fallback(args)
    output = capsys.readouterr().out
    assert "Actions quota fallback note" in output
    binding = json.loads(output.split("`")[1])
    assert binding["pull_request"] == 42
    assert binding["head_sha"] == "head"
    assert binding["runs"] == [run_url]


def test_note_quota_fallback_rejects_a_real_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A job that actually ran a step cannot be waved through as quota."""
    jobs = [
        {"runner_id": 7, "steps": [{"name": "tests"}], "conclusion": "failure"}
    ]
    monkeypatch.setitem(
        note_quota_fallback.__globals__, "github_get", _routine_pr_get(jobs)
    )
    run_url = "https://github.com/owner/repo/actions/runs/200"
    args = SimpleNamespace(repo="owner/repo", pr=42, blocked_run_url=[run_url])
    with pytest.raises(RuntimeError, match="zero-step"):
        note_quota_fallback(args)


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
                "title": "Promotion",
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
    arguments = SimpleNamespace(
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
    prepare(arguments)
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["route"]["kind"] == "milestone"
    assert evidence["candidate_tree"]
    assert evidence["promotion_pull_request"] == {
        "number": 99,
        "title": "feat: promote staged CI",
        "body_sha256": hashlib.sha256(b"Closes #99").hexdigest(),
        "closing_issue": 99,
        "labels": ["promotion"],
    }
    assert evidence["tracking_issue_state"] == {
        "number": 99,
        "state": "open",
        "title": "Promotion",
        "body_sha256": hashlib.sha256(b"- [x] Ready").hexdigest(),
        "labels": ["promotion"],
        "milestone": 7,
    }
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
    assert evidence["main_sync"] == "direct-ancestry"
    archive_victim = tmp_path / "archive-victim"
    archive_victim.write_bytes(b"untouched")
    arguments.archive.unlink()
    arguments.archive.symlink_to(archive_victim)
    with pytest.raises(RuntimeError, match="regular file"):
        prepare(arguments)
    assert archive_victim.read_bytes() == b"untouched"
    arguments.archive.unlink()
    prepare(arguments)
    output_victim = tmp_path / "output-victim"
    output_victim.write_bytes(b"untouched")
    output.unlink()
    output.symlink_to(output_victim)
    with pytest.raises(RuntimeError, match="regular file"):
        prepare(arguments)
    assert output_victim.read_bytes() == b"untouched"


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
    archive = tmp_path / "candidate.tar.gz"
    archive.write_bytes(b"archive")
    source.write_text(
        json.dumps(
            {
                "repository": "owner/repo",
                "pull_request": 42,
                "route": {
                    "kind": "standalone-batch",
                    "relevant": True,
                    "milestone": None,
                    "issue": None,
                },
                "base_sha": "base",
                "head_ref": "dev/next",
                "head_sha": "head",
                "candidate_sha": "head",
                "candidate_tree": "tree",
                "candidate_archive": {
                    "name": archive.name,
                    "sha256": "digest",
                },
                "main_sync": "squash-sync-pr-283",
                "canary": {"state": "blocked"},
                "dev_next_preservation": preservation_evidence(),
            }
        ),
        encoding="utf-8",
    )

    def fake_get(_repo: str, path: str, _token: str) -> object:
        if path == "":
            return {
                "full_name": "owner/repo",
                "archived": False,
                "default_branch": "main",
            }
        if path == "pulls/42":
            return {
                "number": 42,
                "state": "open",
                "merged": False,
                "labels": [{"name": "promotion"}],
                "base": {"ref": "main", "sha": "base"},
                "head": {
                    "ref": "dev/next",
                    "sha": "head",
                    "repo": {"full_name": "owner/repo"},
                },
            }
        if path == "git/ref/heads/main":
            return {"object": {"sha": "base"}}
        if path == "git/commits/head":
            return {"tree": {"sha": "tree"}}
        if path.startswith("actions/runs?"):
            return {
                "total_count": 2,
                "workflow_runs": [
                    {"id": 200, "conclusion": "failure", "status": "completed"},
                    {"id": 201, "conclusion": "failure", "status": "completed"},
                ],
            }
        raise AssertionError(path)

    monkeypatch.setitem(
        finalize_quota_fallback.__globals__, "github_get", fake_get
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "git_output",
        lambda *arguments: (
            ""
            if arguments[0] == "status"
            else "tree"
            if "tree" in arguments[-1]
            else "head"
        ),
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__, "contains_commit", lambda *_: True
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__, "sha256", lambda *_: "digest"
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "require_zero_step_run",
        lambda url, *_: (
            ".github/workflows/ci.yml"
            if url.endswith("/200")
            else ".github/workflows/promotion.yml"
        ),
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "contains_commit",
        lambda *_: False,
    )
    monkeypatch.setattr(
        MODULE["delivery_sync"],
        "merged_sync_pr_number",
        lambda *_: 283,
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "require_comment_url",
        lambda _url, _repo, _pr, body, _token: {
            "user": {
                "login": "attestor" if "attestation" in body else "authorizer"
            }
        },
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "rebuild_quota_preflight",
        lambda evidence, *_: evidence,
    )
    preservation_calls: list[tuple[str, str, int, str, str, str, str]] = []

    def fake_preservation(
        action: str,
        repo: str,
        pr_number: int,
        head_sha: str,
        main_sha: str = "",
        operation_id: str = "",
        prepared_ledger_commit: str = "",
    ) -> dict[str, object]:
        preservation_calls.append(
            (
                action,
                repo,
                pr_number,
                head_sha,
                main_sha,
                operation_id,
                prepared_ledger_commit,
            )
        )
        return preservation_evidence()

    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "run_dev_next_preservation",
        fake_preservation,
    )
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: None)
    arguments = SimpleNamespace(
        input=source,
        output=target,
        attestation_url=(
            "https://github.com/owner/repo/pull/42#issuecomment-100"
        ),
        authorization_url=(
            "https://github.com/owner/repo/pull/42#issuecomment-101"
        ),
        blocked_run_url=[
            "https://github.com/owner/repo/actions/runs/200",
            "https://github.com/owner/repo/actions/runs/201",
        ],
        archive=archive,
    )
    finalize_quota_fallback(arguments)
    evidence = json.loads(target.read_text(encoding="utf-8"))
    assert evidence["gate"] == "quota-fallback"
    assert evidence["release_eligible"] is False
    assert evidence["dev_next_preservation"] == preservation_evidence()
    assert preservation_calls == [
        ("inspect-dev-next", "owner/repo", 42, "head", "", "", "")
    ]
    assert evidence["full_check"] == {
        "context": "verify",
        "status": "local-quota-attested",
        "commands": [
            local_verification_command()[0],
            "promotion preflight live refetch",
        ],
    }
    victim = tmp_path / "victim.json"
    victim.write_text("untouched\n", encoding="utf-8")
    target.unlink()
    target.symlink_to(victim)
    with pytest.raises(RuntimeError, match="regular file"):
        finalize_quota_fallback(arguments)
    assert victim.read_text(encoding="utf-8") == "untouched\n"
    arguments.output = archive
    with pytest.raises(RuntimeError, match="must be distinct"):
        finalize_quota_fallback(arguments)


def test_finalize_quota_fallback_rejects_bridge_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-resolve the bridge source instead of trusting preflight evidence."""
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "repository": "owner/repo",
                "pull_request": 42,
                "route": {
                    "kind": "milestone",
                    "relevant": True,
                    "milestone": 7,
                },
                "base_sha": "main",
                "head_ref": "promote/m7-staged-ci",
                "head_sha": "bridge",
                "candidate_sha": "bridge",
                "candidate_tree": "tree",
                "candidate_archive": {"sha256": "digest"},
                "promotion_bridge": {
                    "source_ref": "dev/m7-staged-ci",
                    "source_sha": "old-source",
                    "source_tree": "tree",
                },
                "canary": {"state": "blocked"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "git_output",
        lambda *arguments: "" if arguments[0] == "status" else "bridge",
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "github_get",
        lambda *_: {"object": {"sha": "main"}},
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "promotion_bridge_source",
        lambda *_: {
            "source_ref": "dev/m7-staged-ci",
            "source_sha": "new-source",
            "source_tree": "tree",
        },
    )
    with pytest.raises(RuntimeError, match="changed after preflight"):
        finalize_quota_fallback(
            SimpleNamespace(
                input=source,
                output=tmp_path / "target.json",
                archive=tmp_path / "candidate.tar.gz",
                attestation_url="unused",
                authorization_url="unused",
                blocked_run_url=[],
                verification_command=[],
            )
        )


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
                archive=tmp_path / "candidate.tar.gz",
            )
        )


def test_quota_comment_url_must_reference_the_same_pull_request() -> None:
    """A human statement from a different pull request is never reusable."""
    with pytest.raises(RuntimeError, match="comments on the promotion PR"):
        MODULE["require_comment_url"](
            "https://github.com/owner/repo/pull/41#issuecomment-101",
            "owner/repo",
            42,
            "expected",
            "token",
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


def test_verify_main_completes_standard_dev_next_preservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The standard post-main path closes the exact prepared transaction."""
    source = tmp_path / "evidence.json"
    checks = tmp_path / "checks.json"
    target = tmp_path / "verified.json"
    source.write_text(
        json.dumps(
            {
                "gate": "passed",
                "repository": "owner/repo",
                "pull_request": 42,
                "head_ref": "dev/next",
                "head_sha": "head",
                "candidate_tree": "tree",
                "dev_next_preservation": preservation_evidence(),
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
    calls: list[tuple[object, ...]] = []

    def complete(*arguments: object) -> dict[str, object]:
        calls.append(arguments)
        return {"ledger_commit": "f" * 40, "transaction": {}}

    monkeypatch.setitem(
        verify_main.__globals__, "git_output", lambda *_: "tree"
    )
    monkeypatch.setitem(
        verify_main.__globals__, "run_dev_next_preservation", complete
    )
    verify_main(
        SimpleNamespace(
            evidence=source,
            checks=checks,
            repo="owner/repo",
            pr_number=42,
            head_sha="head",
            main_sha="main",
            output=target,
        )
    )
    assert calls == [
        (
            "complete-dev-next",
            "owner/repo",
            42,
            "head",
            "main",
            "e" * 64,
            "d" * 40,
        )
    ]
    assert (
        json.loads(target.read_text())["dev_next_preservation"]["completion"][
            "ledger_commit"
        ]
        == "f" * 40
    )


def test_verify_quota_main_preserves_non_release_evidence(  # noqa: C901
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
                "base_sha": "base",
                "head_ref": "dev/next",
                "head_sha": "head",
                "route": {"kind": "standalone-batch", "relevant": True},
                "candidate_tree": "tree",
                "full_check": {"status": "local-quota-attested"},
                "quota_fallback": {
                    "attestation_url": (
                        "https://github.com/owner/repo/pull/42#issuecomment-100"
                    ),
                    "authorization_url": (
                        "https://github.com/owner/repo/pull/42#issuecomment-101"
                    ),
                    "blocked_run_urls": [
                        "https://github.com/owner/repo/actions/runs/200"
                    ],
                },
                "dev_next_preservation": preservation_evidence(),
            }
        ),
        encoding="utf-8",
    )

    def fake_git(*arguments: str) -> str:
        if arguments[0] == "status":
            return ""
        if arguments[-1] in {"HEAD", "refs/remotes/origin/main"}:
            return "main"
        return "tree"

    monkeypatch.setitem(verify_quota_main.__globals__, "git_output", fake_git)

    scenario = {"value": "happy"}

    def fake_get(_repo: str, path: str, _token: str) -> object:
        if path == "":
            return {
                "full_name": "owner/repo",
                "archived": False,
                "default_branch": "main",
            }
        if path == "git/ref/heads/main":
            return {"object": {"sha": "main"}}
        if path == "pulls/42":
            return {
                "number": 42,
                "state": "closed",
                "merged": True,
                "merged_at": "2026-08-25T00:00:00Z",
                "merge_commit_sha": "main",
                "base": {"ref": "main", "sha": "base"},
                "head": {
                    "ref": "dev/next",
                    "sha": "head",
                    "repo": {"full_name": "owner/repo"},
                },
            }
        if path == "git/commits/main":
            parent = "other" if scenario["value"] == "rebase" else "base"
            return {"tree": {"sha": "tree"}, "parents": [{"sha": parent}]}
        if path.startswith("commits/main/pulls?"):
            sources = [
                {
                    "number": 42,
                    "merged_at": "2026-08-25T00:00:00Z",
                    "merge_commit_sha": "main",
                    "base": {"ref": "main"},
                }
            ]
            if scenario["value"] == "ambiguous":
                sources.append(
                    {
                        "number": 43,
                        "merged_at": "2026-08-25T00:00:00Z",
                        "merge_commit_sha": "main",
                        "base": {"ref": "main"},
                    }
                )
            return sources
        return {}

    monkeypatch.setitem(verify_quota_main.__globals__, "github_get", fake_get)
    monkeypatch.setitem(
        verify_quota_main.__globals__, "require_comment_url", lambda *_: {}
    )
    preservation_calls: list[tuple[str, str, int, str, str, str, str]] = []

    def fake_preservation(
        action: str,
        repo: str,
        pr_number: int,
        head_sha: str,
        main_sha: str = "",
        operation_id: str = "",
        prepared_ledger_commit: str = "",
    ) -> dict[str, object]:
        preservation_calls.append(
            (
                action,
                repo,
                pr_number,
                head_sha,
                main_sha,
                operation_id,
                prepared_ledger_commit,
            )
        )
        completed = preservation_evidence()
        completed["ledger_commit"] = "f" * 40
        return completed

    monkeypatch.setitem(
        verify_quota_main.__globals__,
        "run_dev_next_preservation",
        fake_preservation,
    )
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: None)
    arguments = SimpleNamespace(
        evidence=source,
        repo="owner/repo",
        pr_number=42,
        head_sha="head",
        main_sha="main",
        output=target,
    )
    verify_quota_main(arguments)
    evidence = json.loads(target.read_text(encoding="utf-8"))
    assert evidence["post_merge"]["tree_identity"] == (
        "verified-local-quota-fallback"
    )
    assert evidence["release_eligible"] is False
    assert (
        evidence["dev_next_preservation"]["completion"]["ledger_commit"]
        == "f" * 40
    )
    assert preservation_calls == [
        (
            "complete-dev-next",
            "owner/repo",
            42,
            "head",
            "main",
            "e" * 64,
            "d" * 40,
        )
    ]
    original = json.loads(source.read_text(encoding="utf-8"))
    del original["dev_next_preservation"]
    source.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(RuntimeError, match="was not prepared"):
        verify_quota_main(arguments)
    original["dev_next_preservation"] = preservation_evidence()
    source.write_text(json.dumps(original), encoding="utf-8")
    scenario["value"] = "ambiguous"
    with pytest.raises(RuntimeError, match="unique promotion source"):
        verify_quota_main(arguments)
    scenario["value"] = "rebase"
    with pytest.raises(RuntimeError, match="squash-merged"):
        verify_quota_main(arguments)
    scenario["value"] = "happy"
    victim = tmp_path / "post-main-victim.json"
    victim.write_text("untouched\n", encoding="utf-8")
    target.unlink()
    target.symlink_to(victim)
    with pytest.raises(RuntimeError, match="regular file"):
        verify_quota_main(arguments)
    assert victim.read_text(encoding="utf-8") == "untouched\n"


def test_quota_finalize_refetches_live_pull_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutable local evidence cannot replace the live promotion identity."""
    source = tmp_path / "source.json"
    archive = tmp_path / "candidate.tar.gz"
    archive.write_bytes(b"archive")
    source.write_text(
        json.dumps(
            {
                "repository": "owner/repo",
                "pull_request": 42,
                "route": {"kind": "standalone-batch", "relevant": True},
                "base_ref": "main",
                "base_sha": "base",
                "head_ref": "dev/next",
                "head_sha": "head",
                "candidate_sha": "head",
                "candidate_tree": "tree",
                "candidate_archive": {
                    "name": archive.name,
                    "sha256": MODULE["sha256"](archive),
                },
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
        finalize_quota_fallback.__globals__, "contains_commit", lambda *_: True
    )

    def fake_get(_repo: str, path: str, _token: str) -> object:
        if path == "":
            return {
                "full_name": "owner/repo",
                "archived": False,
                "default_branch": "main",
            }
        if path == "pulls/42":
            return {
                "number": 42,
                "state": "open",
                "merged": False,
                "labels": [{"name": "promotion"}],
                "base": {"ref": "main", "sha": "base"},
                "head": {
                    "ref": "dev/next",
                    "sha": "changed",
                    "repo": {"full_name": "owner/repo"},
                },
            }
        if path == "git/ref/heads/main":
            return {"object": {"sha": "base"}}
        if path.endswith("/jobs"):
            return {"jobs": [{"runner_id": 0, "steps": []}]}
        return {"head_sha": "head", "conclusion": "failure"}

    monkeypatch.setitem(
        finalize_quota_fallback.__globals__, "github_get", fake_get
    )
    monkeypatch.setitem(
        finalize_quota_fallback.__globals__,
        "run_dev_next_preservation",
        lambda *_args, **_kwargs: preservation_evidence(),
    )
    with pytest.raises(RuntimeError, match="Live promotion"):
        finalize_quota_fallback(
            SimpleNamespace(
                input=source,
                output=tmp_path / "output.json",
                archive=archive,
                attestation_url=(
                    "https://github.com/owner/repo/pull/42#issuecomment-100"
                ),
                authorization_url=(
                    "https://github.com/owner/repo/pull/42#issuecomment-101"
                ),
                blocked_run_url=[
                    "https://github.com/owner/repo/actions/runs/200"
                ],
            )
        )


def test_quota_finalize_rejects_arbitrary_verification_commands() -> None:
    """The fallback runs its fixed checks instead of accepting shell text."""
    with pytest.raises(SystemExit):
        parser().parse_args(
            [
                "finalize-quota-fallback",
                "--input=in.json",
                "--output=out.json",
                "--archive=candidate.tar.gz",
                "--attestation-url=https://example.test/a",
                "--authorization-url=https://example.test/b",
                "--verification-command=false",
            ]
        )


def test_quota_main_refetches_the_unique_squash_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local HEAD cannot stand in for the live merged-main source PR."""
    source = tmp_path / "fallback.json"
    source.write_text(
        json.dumps(
            {
                "gate": "quota-fallback",
                "release_eligible": False,
                "repository": "owner/repo",
                "pull_request": 42,
                "base_sha": "base",
                "head_ref": "dev/next",
                "head_sha": "head",
                "route": {"kind": "standalone-batch", "relevant": True},
                "candidate_tree": "tree",
                "full_check": {"status": "local-quota-attested"},
                "dev_next_preservation": preservation_evidence(),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(
        verify_quota_main.__globals__,
        "git_output",
        lambda *arguments: "" if arguments[0] == "status" else "main",
    )

    def fake_get(_repo: str, path: str, _token: str) -> object:
        if path == "":
            return {
                "full_name": "owner/repo",
                "archived": False,
                "default_branch": "main",
            }
        if path == "git/ref/heads/main":
            return {"object": {"sha": "different-main"}}
        return {}

    monkeypatch.setitem(verify_quota_main.__globals__, "github_get", fake_get)
    with pytest.raises(RuntimeError, match="merged promotion"):
        verify_quota_main(
            SimpleNamespace(
                evidence=source,
                repo="owner/repo",
                pr_number=42,
                head_sha="head",
                main_sha="main",
                output=tmp_path / "verified.json",
            )
        )


def test_zero_step_run_reads_all_jobs_and_rejects_changed_billing_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hidden job or ambiguous billing annotation must fail closed."""
    paths: list[str] = []

    def fake_get(_repo: str, path: str, _token: str) -> object:
        paths.append(path)
        if path == "actions/runs/200":
            return {
                "id": 200,
                "head_sha": "head",
                "head_branch": "dev/next",
                "event": "pull_request",
                "status": "completed",
                "conclusion": "failure",
                "path": ".github/workflows/ci.yml",
                "pull_requests": [{"number": 42}],
                "repository": {"full_name": "owner/repo"},
                "head_repository": {"full_name": "owner/repo"},
            }
        if "jobs?" in path and path.endswith("page=1"):
            return {
                "total_count": 101,
                "jobs": [
                    {
                        "id": number,
                        "runner_id": 0,
                        "steps": [],
                        "conclusion": "skipped",
                    }
                    for number in range(1, 101)
                ],
            }
        if "jobs?" in path and path.endswith("page=2"):
            return {
                "total_count": 101,
                "jobs": [
                    {
                        "id": 101,
                        "runner_id": 0,
                        "steps": [],
                        "conclusion": "failure",
                    }
                ],
            }
        if path.startswith("check-runs/101/annotations"):
            return [
                {
                    "annotation_level": "failure",
                    "message": (
                        "The job was not started because of an unknown "
                        "billing problem."
                    ),
                }
            ]
        return []

    monkeypatch.setitem(
        require_zero_step_run.__globals__, "github_get", fake_get
    )
    with pytest.raises(RuntimeError, match="zero-step billing gate"):
        require_zero_step_run(
            "https://github.com/owner/repo/actions/runs/200",
            "owner/repo",
            42,
            "dev/next",
            "head",
            "",
        )
    assert any(path.endswith("page=2") for path in paths)


@pytest.mark.parametrize(
    "run_identity",
    [
        {"pull_requests": [{"number": 42}]},
        {"id": 200},
        {"id": 200, "pull_requests": []},
        {"id": 200, "pull_requests": [{"number": 41}]},
    ],
)
def test_zero_step_run_requires_exact_run_and_pull_request(
    monkeypatch: pytest.MonkeyPatch, run_identity: dict[str, object]
) -> None:
    """A same-SHA run without exact API identity is not reusable."""

    def fake_get(_repo: str, path: str, _token: str) -> object:
        if path == "actions/runs/200":
            return {
                **run_identity,
                "head_sha": "head",
                "head_branch": "dev/next",
                "event": "pull_request",
                "status": "completed",
                "conclusion": "failure",
                "path": ".github/workflows/ci.yml",
                "repository": {"full_name": "owner/repo"},
                "head_repository": {"full_name": "owner/repo"},
            }
        raise AssertionError(path)

    monkeypatch.setitem(
        require_zero_step_run.__globals__, "github_get", fake_get
    )
    with pytest.raises(
        RuntimeError, match=r"failed PR head|another pull request"
    ):
        require_zero_step_run(
            "https://github.com/owner/repo/actions/runs/200",
            "owner/repo",
            42,
            "dev/next",
            "head",
            "",
        )


def test_preflight_binding_rejects_tampered_canary() -> None:
    """Local JSON cannot hide a configured live canary."""
    evidence = {
        "repository": "owner/repo",
        "canary": {"state": "blocked", "environment": None},
    }
    rebuilt = {
        "repository": "owner/repo",
        "canary": {"state": "allowed", "environment": "canary"},
    }
    with pytest.raises(RuntimeError, match="live reconstruction"):
        require_same_preflight(evidence, rebuilt)


def test_preflight_binding_rejects_changed_pull_request_body() -> None:
    """A changed promotion body invalidates the prepared evidence."""
    evidence = {
        "promotion_pull_request": {"body_sha256": "original"},
        "tracking_issue_state": {"body_sha256": "issue"},
    }
    rebuilt = {
        "promotion_pull_request": {"body_sha256": "changed"},
        "tracking_issue_state": {"body_sha256": "issue"},
    }
    with pytest.raises(RuntimeError, match="live reconstruction"):
        require_same_preflight(evidence, rebuilt)


def test_authorization_statement_binds_full_preflight() -> None:
    """Human authorization covers the route, canary, and evidence schema."""
    evidence = {
        "schema_version": 1,
        "repository": "owner/repo",
        "route": {"kind": "standalone-batch", "relevant": True},
        "canary": {"state": "blocked", "environment": None},
        "dev_next_preservation": preservation_evidence(),
    }
    statement = fallback_statement("authorization", evidence, ["run"])
    binding = json.loads(statement.split("`")[1])
    assert binding["schema_version"] == 1
    assert binding["route"] == evidence["route"]
    assert binding["canary"] == evidence["canary"]
    assert binding["dev_next_preservation"] == preservation_evidence()


def test_repository_variables_reads_every_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canary configuration cannot hide beyond the first API page."""

    def fake_get(_repo: str, path: str, _token: str) -> object:
        if path.endswith("page=1"):
            return {
                "total_count": 101,
                "variables": [
                    {"name": f"VARIABLE_{number}", "value": "value"}
                    for number in range(100)
                ],
            }
        return {
            "total_count": 101,
            "variables": [{"name": "CSARC_CANARY_COMMAND", "value": "./smoke"}],
        }

    monkeypatch.setitem(
        repository_variables.__globals__, "github_get", fake_get
    )
    assert (
        repository_variables("owner/repo", "token")["CSARC_CANARY_COMMAND"]
        == "./smoke"
    )


def test_generated_repository_uses_its_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generated repositories run scripts/verify, not a root-only command."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "verify").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert local_verification_command() == ["./scripts/verify"]


def test_token_request_rejects_cross_origin_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A GitHub bearer token must never follow an attacker redirect."""
    captured: list[object] = []

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true}'

    class Opener:
        def open(
            self, request: urllib.request.Request, *, timeout: int
        ) -> Response:
            assert timeout == 20
            assert request.full_url.startswith("https://api.github.com/")
            assert request.get_header("Authorization") == "Bearer secret"
            return Response()

    def fake_build_opener(*handlers: object) -> Opener:
        captured.extend(handlers)
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    assert github_get("owner/repo", "issues/42", "secret") == {"ok": True}
    handler = captured[0]
    assert isinstance(handler, RejectRedirects)
    assert (
        handler.redirect_request(
            urllib.request.Request("https://api.github.com/repos/owner/repo"),
            None,
            302,
            "Found",
            {},
            "https://attacker.invalid/steal",
        )
        is None
    )
