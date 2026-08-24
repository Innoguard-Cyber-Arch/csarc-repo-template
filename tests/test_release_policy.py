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
bump_version = MODULE["bump_version"]
classify_probe = MODULE["classify_probe"]
direct_release = MODULE["direct_release"]
release_intent = MODULE["release_intent"]
release_plan = MODULE["release_plan"]
select_release_mode = MODULE["select_release_mode"]
optional_integration_preflight = MODULE["optional_integration_preflight"]
update_release_version = MODULE["update_release_version"]


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


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", *arguments],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


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
    (tmp_path / ".release-please-manifest.json").write_text(
        '{".": "0.1.0"}\n', encoding="utf-8"
    )
    (tmp_path / "file").write_text("content\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feat: direct release")
    sha = git(tmp_path, "rev-parse", "HEAD")
    api = DirectReleaseAPI(sha)

    payload, failed = direct_release(
        api, "owner/repo", sha, "main", "release.yml", tmp_path
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


def test_prepare_materializes_tag_version(tmp_path: Path) -> None:
    (tmp_path / ".release-please-manifest.json").write_text(
        '{".": "0.1.0"}\n', encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        "v0.1.0 <!-- x-release-please-version -->\n", encoding="utf-8"
    )
    update_release_version(tmp_path, "0.2.0")
    assert json.loads(
        (tmp_path / ".release-please-manifest.json").read_text()
    ) == {".": "0.2.0"}
    assert 'version = "0.2.0"' in (tmp_path / "pyproject.toml").read_text()
    assert 'version = "0.2.0"' in (tmp_path / "uv.lock").read_text()
    assert "v0.2.0" in (tmp_path / "README.md").read_text()
