"""`csarc self-hosted` window commands (Issue #1271, SPEC-011 §8).

Every command prints a read-only inventory first and changes nothing
without `--apply`; `open` refuses public or unregistered repositories,
keeps the registration token in memory, and removes every runner when an
unexpected one appears; `extend` never registers a second runner and
never accumulates; `verify` dispatches only inside a usable window;
`retire` deletes nothing without `--apply`. GitHub and the csarc-devops
delivery channel are stubs here.
"""

from __future__ import annotations

import base64
import json
import re
import stat
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from settings_support import settings_text

from csarc_cli import cli, self_hosted

ROOT = Path(__file__).resolve().parents[1]
REPO = "acme/widget"
VM = "vm-01"
TOKEN = "AAAREGISTRATIONTOKEN0123456789"  # noqa: S105 - stub token
NOW = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
REGISTRATION = "https://github.com/acme/csarc-devops/issues/7"
HEAD = "a" * 40


def config(
    private: str = "self-hosted",
    runner: bool = True,
    environments: tuple[str, ...] = ("dev", "uat"),
) -> str:
    """Return one schema 2 settings file."""
    text = settings_text(
        "",
        verification_mode=None,
        verification_mode_private=private,
        verification_mode_public="hosted",
    )
    if private == "self-hosted":
        text += (
            f"self_hosted_runner:\n  id: {VM}\n  registration: {REGISTRATION}\n"
            if runner
            else "self_hosted_runner: {}\n"
        )
        text += "self_hosted_environments:\n" + "".join(
            f"- {env}\n" for env in environments
        )
    return text


def runner(env: str, number: int = 1, status: str = "online") -> dict:
    """Return one registered window runner as the API lists it."""
    name, labels = self_hosted.runner_identity(VM, env)
    return {
        "id": number,
        "name": name,
        "status": status,
        "labels": [{"name": label} for label in labels],
    }


class FakeGitHub:
    """In-memory GitHub REST API that records every call."""

    def __init__(self, text: str | None = None, **repo: object) -> None:
        self.repo = {
            "private": True,
            "default_branch": "main",
            "permissions": {"admin": True},
            **repo,
        }
        self.configs = {"main": text if text is not None else config()}
        self.runners: list[dict[str, Any]] = []
        self.pulls: dict[int, dict[str, Any]] = {}
        self.runs: list[dict[str, Any]] = []
        self.artifacts: dict[int, list[dict[str, Any]]] = {}
        self.caches: list[dict[str, Any]] = []
        self.calls: list[tuple[str, str]] = []
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.fail_delete: set[str] = set()

    def get(self, endpoint: str) -> dict[str, Any]:
        self.calls.append(("GET", endpoint))
        if endpoint == f"repos/{REPO}":
            return dict(self.repo)
        if endpoint.startswith(f"repos/{REPO}/contents/.csarc/config.yml"):
            ref = endpoint.split("ref=", 1)[1]
            content = base64.b64encode(self.configs[ref].encode()).decode()
            return {"content": content}
        if endpoint.startswith(f"repos/{REPO}/pulls/"):
            return self.pulls[int(endpoint.rsplit("/", 1)[1])]
        # The shared public-log check (#1287) reads one workflow's runs.
        verify = [
            r for r in self.runs if r["path"] == self_hosted.WORKFLOW_PATH
        ]
        if endpoint == f"repos/{REPO}/actions/workflows?per_page=100":
            flow = {"id": 9, "path": self_hosted.WORKFLOW_PATH}
            return {"workflows": [flow] if verify else []}
        if endpoint == f"repos/{REPO}/actions/workflows/9/runs?per_page=1":
            return {"total_count": len(verify)}
        raise AssertionError(endpoint)

    def collection(self, endpoint: str, key: str) -> list[dict[str, Any]]:
        self.calls.append(("LIST", endpoint))
        if endpoint.endswith("/actions/runners"):
            return [dict(item) for item in self.runners]
        if endpoint.endswith("/actions/runs"):
            return list(self.runs)
        if endpoint.endswith("/artifacts"):
            return self.artifacts.get(int(endpoint.split("/")[-2]), [])
        if endpoint.endswith("/actions/caches"):
            return list(self.caches)
        raise AssertionError(endpoint)

    def post(self, endpoint: str, body: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append(("POST", endpoint))
        self.posts.append((endpoint, dict(body)))
        if endpoint.endswith("/registration-token"):
            return {"token": TOKEN, "expires_at": "2026-10-25T02:00:00Z"}
        return {}

    def delete(self, endpoint: str) -> None:
        self.calls.append(("DELETE", endpoint))
        if endpoint in self.fail_delete:
            raise self_hosted.SelfHostedError(
                "GitHub request failed: HTTP 500. Run it again."
            )
        if "/actions/runners/" in endpoint:
            number = int(endpoint.rsplit("/", 1)[1])
            self.runners = [r for r in self.runners if r["id"] != number]

    def deletes(self) -> list[str]:
        return [
            endpoint for method, endpoint in self.calls if method == "DELETE"
        ]

    def token_requested(self) -> bool:
        return any(e.endswith("/registration-token") for e, _ in self.posts)


class FakeChannel:
    """The csarc-devops VM: registers runners and keeps the window."""

    def __init__(
        self, github: FakeGitHub, ends: datetime | None = None
    ) -> None:
        self.github = github
        self.requests: list[dict[str, Any]] = []
        self.ends = ends
        self.rogue = False
        self.extend_to: datetime | None = None

    def window(self, env: str, ends: datetime) -> dict[str, Any]:
        return {
            "runner_name": self_hosted.runner_identity(VM, env)[0],
            "started_at": "2026-10-24T09:00Z",
            "ends_at": ends.strftime("%Y-%m-%dT%H:%MZ"),
            "registration": "active",
        }

    def request(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.requests.append(dict(payload))
        env = payload.get("environment", "dev")
        reply: dict[str, Any] = {"protocol": self_hosted.PROTOCOL}
        if payload["action"] == "open":
            self.github.runners.append(runner(env, 7))
            if self.rogue:
                self.github.runners.append(
                    {
                        "id": 8,
                        "name": "attacker",
                        "status": "online",
                        "labels": [{"name": "self-hosted"}],
                    }
                )
            self.ends = self_hosted.utc(payload["ends_at"], "end")
            return {
                **reply,
                "result": "ok",
                "window": self.window(env, self.ends),
            }
        if payload["action"] == "extend":
            self.ends = self.extend_to or self_hosted.utc(
                payload["ends_at"], "end"
            )
            return {
                **reply,
                "result": "ok",
                "window": self.window(env, self.ends),
            }
        if payload["action"] == "status":
            window = self.window(env, self.ends) if self.ends else None
            return {**reply, "result": "ok", "window": window}
        return {**reply, "result": "ok", "window": None}


def session(
    github: FakeGitHub,
    channel: self_hosted.Channel | None = None,
    switch: self_hosted.Switch | None = None,
) -> self_hosted.Session:
    return self_hosted.Session(
        github=github,
        channel=channel if channel is not None else FakeChannel(github),
        now=lambda: NOW,
        sleep=lambda _seconds: None,
        switch=switch,
    )


def run(
    monkeypatch: pytest.MonkeyPatch, current: self_hosted.Session, *argv: str
) -> int:
    """Run `csarc self-hosted ...` through the real CLI entry point."""
    monkeypatch.setattr(
        self_hosted, "default_session", lambda _checkout=None: current
    )
    return cli.main(["self-hosted", *argv, "--repo", REPO])


# AC1 open


def test_open_without_apply_prints_inventory_and_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    channel = FakeChannel(github)
    assert (
        run(monkeypatch, session(github, channel), "open", "--env", "dev") == 0
    )
    out = capsys.readouterr().out
    assert "Inventory: open a dev window (read-only)" in out
    assert "acme/widget (private)" in out
    assert "csarc-vm-01-dev" in out
    assert "2026-10-26T01:00Z (24h, fixed)" in out
    assert "only .github/workflows/csarc-verify.yml" in out
    assert "--apply' to continue" in out
    assert not github.token_requested()
    assert channel.requests == []
    assert github.deletes() == []


@pytest.mark.parametrize(
    ("text", "repo", "expected"),
    [
        (config(), {"private": False}, "the repository is public"),
        (config(runner=False), {}, "not registered. Register with"),
        (config(private="local"), {}, "verification_mode_private is 'local'"),
        (config(environments=("uat",)), {}, "'dev' is not in"),
        (config(), {"permissions": {"admin": False}}, "not a repository admin"),
    ],
)
def test_open_refuses_before_any_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    text: str,
    repo: dict[str, Any],
    expected: str,
) -> None:
    github = FakeGitHub(text, **repo)
    channel = FakeChannel(github)
    code = run(
        monkeypatch, session(github, channel), "open", "--env", "dev", "--apply"
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "Inventory: open a dev window" in captured.out
    assert expected in captured.err
    assert captured.err.startswith("ERROR: ")
    assert not github.token_requested()
    assert channel.requests == []


def test_open_fails_closed_without_a_delivery_channel(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    channel = self_hosted.configured_channel({})
    assert isinstance(channel, self_hosted.MissingChannel)
    code = run(
        monkeypatch, session(github, channel), "open", "--env", "dev", "--apply"
    )
    err = capsys.readouterr().err
    assert code == 2
    assert "none is configured" in err
    assert self_hosted.CHANNEL_ENV in err
    assert not github.token_requested()


def test_open_hands_the_token_only_to_the_channel_and_reads_back(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    channel = FakeChannel(github)
    code = run(
        monkeypatch, session(github, channel), "open", "--env", "dev", "--apply"
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "OK: Opened the dev window" in captured.out
    assert "2026-10-26T01:00Z" in captured.out
    assert TOKEN not in captured.out + captured.err
    (opened,) = channel.requests
    assert opened["action"] == "open"
    assert opened["protocol"] == self_hosted.PROTOCOL
    assert opened["registration_token"] == TOKEN
    assert opened["runner_name"] == "csarc-vm-01-dev"
    assert opened["labels"] == [
        "csarc-env-dev",
        "csarc-vm-vm-01",
        "self-hosted",
    ]
    assert [r["name"] for r in github.runners] == ["csarc-vm-01-dev"]


def test_open_removes_every_runner_when_an_unexpected_one_appears(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    channel = FakeChannel(github)
    channel.rogue = True
    code = run(
        monkeypatch, session(github, channel), "open", "--env", "dev", "--apply"
    )
    err = capsys.readouterr().err
    assert code == 2
    assert "every runner was removed" in err
    assert github.runners == []
    assert sorted(github.deletes()) == [
        f"repos/{REPO}/actions/runners/7",
        f"repos/{REPO}/actions/runners/8",
    ]


def test_open_refuses_when_an_unexpected_runner_is_already_registered(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.runners = [{"id": 3, "name": "other", "status": "online"}]
    code = run(monkeypatch, session(github), "open", "--env", "dev", "--apply")
    assert code == 2
    assert "unexpected runners are registered" in capsys.readouterr().err
    assert not github.token_requested()


def test_open_reports_a_vm_refusal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()

    class Refusing(FakeChannel):
        def request(self, payload: Mapping[str, Any]) -> dict[str, Any]:
            return {
                "protocol": self_hosted.PROTOCOL,
                "result": "refused",
                "reason": "registration expired",
            }

    code = run(
        monkeypatch,
        session(github, Refusing(github)),
        "open",
        "--env",
        "uat",
        "--apply",
    )
    assert code == 2
    assert "The VM refused 'open': registration expired." in (
        capsys.readouterr().err
    )


# AC2 extend, close, status


def test_open_on_a_live_window_extends_without_a_second_runner(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.runners = [runner("dev", 5)]
    channel = FakeChannel(github, ends=NOW + timedelta(hours=3))
    code = run(
        monkeypatch, session(github, channel), "open", "--env", "dev", "--apply"
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "extends that window instead of registering a second runner" in out
    assert not github.token_requested()
    assert [r["action"] for r in channel.requests] == ["status", "extend"]
    assert [r["id"] for r in github.runners] == [5]


def test_extend_moves_the_end_to_now_plus_24h_and_never_accumulates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.runners = [runner("dev", 5)]
    channel = FakeChannel(github, ends=NOW + timedelta(hours=20))
    code = run(
        monkeypatch,
        session(github, channel),
        "extend",
        "--env",
        "dev",
        "--apply",
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "current end  2026-10-25T21:00Z" in out
    assert "2026-10-26T01:00Z (now + 24h, not cumulative)" in out
    extend = channel.requests[-1]
    assert extend["action"] == "extend"
    assert extend["ends_at"] == "2026-10-26T01:00Z"
    assert "registration_token" not in extend
    assert not github.token_requested()
    assert [r["id"] for r in github.runners] == [5]
    assert "OK: Extended the dev window" in out


def test_extend_rejects_a_vm_that_accumulates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.runners = [runner("dev", 5)]
    channel = FakeChannel(github, ends=NOW + timedelta(hours=20))
    channel.extend_to = NOW + timedelta(hours=44)
    code = run(
        monkeypatch,
        session(github, channel),
        "extend",
        "--env",
        "dev",
        "--apply",
    )
    assert code == 2
    assert "windows never accumulate" in capsys.readouterr().err


def test_extend_without_apply_or_window_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.runners = [runner("dev", 5)]
    channel = FakeChannel(github, ends=NOW + timedelta(hours=3))
    assert (
        run(monkeypatch, session(github, channel), "extend", "--env", "dev")
        == 0
    )
    assert [r["action"] for r in channel.requests] == ["status"]
    channel = FakeChannel(github, ends=None)
    code = run(
        monkeypatch,
        session(github, channel),
        "extend",
        "--env",
        "dev",
        "--apply",
    )
    assert code == 2
    assert "Run 'csarc self-hosted open --env dev'." in capsys.readouterr().err
    assert [r["action"] for r in channel.requests] == ["status"]


def test_close_removes_only_the_window_runner_with_apply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.runners = [runner("dev", 5), runner("uat", 6)]
    channel = FakeChannel(github)
    assert (
        run(monkeypatch, session(github, channel), "close", "--env", "dev") == 0
    )
    assert github.deletes() == []
    code = run(
        monkeypatch,
        session(github, channel),
        "close",
        "--env",
        "dev",
        "--apply",
    )
    assert code == 0
    assert github.deletes() == [f"repos/{REPO}/actions/runners/5"]
    assert [r["id"] for r in github.runners] == [6]
    assert channel.requests[-1]["action"] == "close"
    assert "OK: Closed the dev window" in capsys.readouterr().out


def test_close_without_a_channel_still_removes_the_runner(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.runners = [runner("dev", 5)]
    current = session(github, self_hosted.MissingChannel())
    assert run(monkeypatch, current, "close", "--env", "dev", "--apply") == 0
    out = capsys.readouterr().out
    assert "the VM stops its runner" in out
    assert github.runners == []


@pytest.mark.parametrize(
    ("left", "expected"),
    [
        (timedelta(hours=5), None),
        (
            timedelta(hours=1, minutes=40),
            "(1h40m left). Run 'csarc self-hosted",
        ),
        (timedelta(minutes=20), "accepts no new jobs"),
    ],
)
def test_status_shows_time_left_and_warns(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    left: timedelta,
    expected: str | None,
) -> None:
    github = FakeGitHub()
    github.runners = [runner("dev", 5)]
    channel = FakeChannel(github, ends=NOW + left)
    assert (
        run(monkeypatch, session(github, channel), "status", "--env", "dev")
        == 0
    )
    captured = capsys.readouterr()
    assert "dev window: runner csarc-vm-01-dev" in captured.out
    if expected is None:
        assert "WARNING" not in captured.err
    else:
        assert captured.err.startswith("WARNING: ")
        assert expected in captured.err
    assert {r["action"] for r in channel.requests} == {"status"}
    assert [m for m, _ in github.calls if m in {"POST", "DELETE"}] == []


def test_status_warns_when_public_and_guides_registration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub(private=False)
    github.runs = [{"id": 11, "path": self_hosted.WORKFLOW_PATH}]
    assert run(monkeypatch, session(github), "status") == 0
    assert "Run 'csarc self-hosted retire'" in capsys.readouterr().err
    github = FakeGitHub(config(runner=False))
    assert run(monkeypatch, session(github), "status") == 0
    assert "not registered. Register with csarc-devops" in (
        capsys.readouterr().out
    )


def test_status_fails_closed_without_a_channel(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    current = session(github, self_hosted.MissingChannel())
    assert run(monkeypatch, current, "status") == 2
    assert "none is configured" in capsys.readouterr().err


def test_window_record_never_writes_a_repository_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github = FakeGitHub()
    channel = FakeChannel(github)
    run(
        monkeypatch, session(github, channel), "open", "--env", "dev", "--apply"
    )
    run(
        monkeypatch,
        session(github, channel),
        "extend",
        "--env",
        "dev",
        "--apply",
    )
    run(monkeypatch, session(github, channel), "status")
    assert not [e for _, e in github.calls if "/actions/variables" in e]


# AC3 verify


def pull(
    base: str = "main", head_repo: str = REPO, state: str = "open"
) -> dict[str, Any]:
    return {
        "state": state,
        "base": {"ref": base},
        "head": {"sha": HEAD, "repo": {"full_name": head_repo}},
    }


def test_verify_dispatches_the_target_branch_workflow(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.pulls[9] = pull("dev/m21-x")
    github.configs["dev/m21-x"] = config()
    channel = FakeChannel(github, ends=NOW + timedelta(hours=5))
    assert (
        run(monkeypatch, session(github, channel), "verify", "--pr", "9") == 0
    )
    assert github.posts == []
    code = run(
        monkeypatch, session(github, channel), "verify", "--pr", "9", "--apply"
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "Inventory: dispatch csarc-verify.yml for pull request #9" in (
        captured.out
    )
    assert "WARNING" not in captured.err
    ((endpoint, body),) = github.posts
    assert (
        endpoint
        == f"repos/{REPO}/actions/workflows/csarc-verify.yml/dispatches"
    )
    assert body == {
        "ref": "dev/m21-x",
        "inputs": {
            "pull_request": "9",
            "head_sha": HEAD,
            "environment": "dev",
            "window_end": "2026-10-25T06:00Z",
        },
    }
    assert (
        "GET",
        f"repos/{REPO}/contents/.csarc/config.yml?ref=dev/m21-x",
    ) in (github.calls)


def test_verify_warns_in_the_last_two_hours(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.pulls[9] = pull()
    channel = FakeChannel(github, ends=NOW + timedelta(hours=1, minutes=40))
    code = run(
        monkeypatch, session(github, channel), "verify", "--pr", "9", "--apply"
    )
    err = capsys.readouterr().err
    assert code == 0
    assert err == (
        "WARNING: Self-hosted uat verification: the window ends at "
        "2026-10-25T02:40Z (1h40m left). Run 'csarc self-hosted extend "
        "--env uat' before it closes.\n"
    )
    assert len(github.posts) == 1


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"repo": {"private": False}}, "the repository is public"),
        ({"pull": pull(head_repo="fork/widget")}, "the head is a fork"),
        ({"pull": pull(state="closed")}, "the pull request is not open"),
        ({"pull": pull(base="feature/x")}, "has no self-hosted environment"),
        ({"text": config(runner=False)}, "the repository is not registered"),
        ({"text": config(environments=("dev",))}, "'uat' is not registered"),
        ({"text": config(private="hosted")}, "effective mode on 'main'"),
        ({"ends": None}, "no uat window is open"),
        ({"ends": NOW + timedelta(minutes=29)}, "less than 30m left"),
    ],
)
def test_verify_refuses_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    change: dict[str, Any],
    expected: str,
) -> None:
    github = FakeGitHub(change.get("text"), **change.get("repo", {}))
    github.pulls[9] = change.get("pull", pull())
    github.configs.setdefault("feature/x", config())
    ends = change.get("ends", NOW + timedelta(hours=5))
    channel = FakeChannel(github, ends=ends)
    code = run(
        monkeypatch, session(github, channel), "verify", "--pr", "9", "--apply"
    )
    err = capsys.readouterr().err
    assert code == 2
    assert expected in err
    assert github.posts == []


def test_verify_fails_closed_without_a_channel(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.pulls[9] = pull()
    current = session(github, self_hosted.MissingChannel())
    assert run(monkeypatch, current, "verify", "--pr", "9", "--apply") == 2
    assert "none is configured" in capsys.readouterr().err
    assert github.posts == []


# AC4 retire


class FakeSwitch:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.fail = fail

    def open_pull_request(self, repo: str, base: str, private_mode: str) -> str:
        self.calls.append((repo, base, private_mode))
        if self.fail:
            raise self_hosted.SelfHostedError(
                "Update failed: conflicts. Resolve them."
            )
        return f"https://github.com/{repo}/pull/42"


def retire_github() -> FakeGitHub:
    github = FakeGitHub()
    github.runs = [
        {"id": 11, "path": self_hosted.WORKFLOW_PATH},
        {"id": 12, "path": ".github/workflows/other.yml"},
    ]
    github.artifacts = {11: [{"id": 21}]}
    github.caches = [{"id": 31}]
    github.runners = [runner("dev", 5)]
    return github


def test_retire_without_apply_deletes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = retire_github()
    switch = FakeSwitch()
    assert run(monkeypatch, session(github, switch=switch), "retire") == 0
    out = capsys.readouterr().out
    assert "csarc-verify.yml runs  11" in out
    assert "artifacts              21" in out
    assert "self-hosted -> hosted" in out
    assert github.deletes() == []
    assert switch.calls == []


def test_retire_apply_deletes_data_and_opens_a_pull_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github = retire_github()
    switch = FakeSwitch()
    code = run(
        monkeypatch,
        session(github, switch=switch),
        "retire",
        "--apply",
        "--private-mode",
        "local",
    )
    out = capsys.readouterr().out
    assert code == 0
    assert github.deletes() == [
        f"repos/{REPO}/actions/artifacts/21",
        f"repos/{REPO}/actions/runs/11",
        f"repos/{REPO}/actions/caches/31",
        f"repos/{REPO}/actions/runners/5",
    ]
    assert switch.calls == [(REPO, "main", "local")]
    assert "Exit notice for csarc-devops:" in out
    assert "https://github.com/acme/widget/pull/42" in out
    # Q4: retire never changes repository settings itself.
    assert [m for m, e in github.calls if m in {"POST", "PATCH", "PUT"}] == []


def test_retire_retry_with_no_data_still_opens_the_pull_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Finish a prior partial cleanup by retrying only the missing PR."""
    github = FakeGitHub()
    switch = FakeSwitch()

    assert (
        run(monkeypatch, session(github, switch=switch), "retire", "--apply")
        == 0
    )

    assert github.deletes() == []
    assert switch.calls == [(REPO, "main", "hosted")]
    assert "deleted 0 items" in capsys.readouterr().out


@pytest.mark.parametrize("failure", ["delete", "switch"])
def test_retire_exits_non_zero_when_any_step_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    github = retire_github()
    if failure == "delete":
        github.fail_delete = {f"repos/{REPO}/actions/runs/11"}
    switch = FakeSwitch(fail=failure == "switch")
    code = run(monkeypatch, session(github, switch=switch), "retire", "--apply")
    err = capsys.readouterr().err
    assert code == 2
    assert "'retire' did not finish" in err
    assert "stay visible once the repository is public" in err


# R1: the channel command never sees a credential outside standard input


def test_command_channel_gets_the_token_only_on_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = tmp_path / "record.json"
    script = tmp_path / "channel.py"
    script.write_text(
        "import json, os, sys\n"
        "payload = json.load(sys.stdin)\n"
        f"open({str(record)!r}, 'w').write(json.dumps({{\n"
        "    'argv': sys.argv,\n"
        "    'env': sorted(k for k in os.environ if 'TOKEN' in k),\n"
        "    'got_token': bool(payload.get('registration_token')),\n"
        "}))\n"
        "print(json.dumps({'protocol': payload['protocol'], 'result': 'ok',\n"
        "    'window': {'runner_name': payload['runner_name'],\n"
        "    'started_at': '2026-10-25T01:00Z',\n"
        "    'ends_at': payload['ends_at'],\n"
        "    'registration': 'active'}}))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("GH_TOKEN", "admin-credential")
    monkeypatch.setenv("GITHUB_TOKEN", "admin-credential")
    channel = self_hosted.configured_channel(
        {self_hosted.CHANNEL_ENV: f"{sys.executable} {script}"}
    )
    github = FakeGitHub()

    class Registering:
        def request(self, payload: Mapping[str, Any]) -> dict[str, Any]:
            github.runners.append(runner("dev", 7))
            return channel.request(payload)

    monkeypatch.chdir(tmp_path)
    code = run(
        monkeypatch,
        session(github, Registering()),
        "open",
        "--env",
        "dev",
        "--apply",
    )
    assert code == 0
    seen = json.loads(record.read_text())
    assert seen["got_token"] is True
    assert TOKEN not in " ".join(seen["argv"])
    assert not set(seen["env"]) & set(self_hosted.CREDENTIAL_ENV)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert TOKEN not in path.read_text(errors="ignore")


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ("not json", "answered without JSON"),
        ('{"protocol": "other/9", "result": "ok"}', "spoke another protocol"),
        (
            '{"protocol": "csarc-self-hosted-channel/1", "result": "maybe"}',
            "did not confirm the result",
        ),
    ],
)
def test_command_channel_fails_closed_on_a_bad_answer(
    tmp_path: Path, stdout: str, expected: str
) -> None:
    script = tmp_path / "channel.py"
    script.write_text(f"import sys\nsys.stdin.read()\nprint({stdout!r})\n")
    channel = self_hosted.CommandChannel([sys.executable, str(script)])
    with pytest.raises(self_hosted.SelfHostedError, match=expected):
        self_hosted.channel_call(channel, {"action": "status"})


def test_live_gh_calls_never_read_the_admin_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        seen.append(list(argv))
        payload = {"token": TOKEN} if "registration-token" in argv[-3] else {}
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    monkeypatch.setattr(self_hosted.subprocess, "run", fake_run)
    api = self_hosted.GhApi()
    assert api.post(f"repos/{REPO}/actions/runners/registration-token", {}) == {
        "token": TOKEN
    }
    assert all(argv[:3] != ["gh", "auth", "token"] for argv in seen)
    assert all(TOKEN not in " ".join(argv) for argv in seen)


# AC6: the commands live in the csarc CLI, not in the generated payload


def test_window_commands_ship_only_in_the_cli_package() -> None:
    module = ROOT / "src/csarc_cli/self_hosted.py"
    assert module.is_file()
    rendered = [
        path
        for path in (ROOT / "template").rglob("*")
        if path.is_file() and "self_hosted.py" in path.name
    ]
    assert rendered == []
    for path in (ROOT / "template").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".jinja", ""}:
            text = path.read_text(errors="ignore")
            assert "csarc_cli.self_hosted" not in text, path


# AC5: the toolchain image contract follows the language profiles


def test_toolchain_contract_matches_the_language_profiles() -> None:
    contract = json.loads(
        (ROOT / "profiles/self-hosted-toolchain.json").read_text()
    )
    catalog = yaml.safe_load((ROOT / "profiles/catalog.yaml").read_text())
    profiles = catalog["profiles"]
    assert set(contract["profiles"]) == set(profiles)
    python = profiles["python"]
    latest = python["latest_reviewed_stable"]
    assert contract["profiles"]["python"]["tools"]["python"] == latest
    assert sorted(
        {*contract["profiles"]["python"]["additional_runtimes"], latest}
    ) == sorted(python["support_modes"]["minimum"]["selectable_minimums"])
    typescript = contract["profiles"]["typescript"]["tools"]
    node = profiles["typescript"]["latest_reviewed_active_lts"]
    assert typescript["node"] == node
    pnpm = profiles["typescript"]["package_manager_version"]
    assert typescript["pnpm"] == pnpm
    for name in ("go", "rust"):
        tools = contract["profiles"][name]["tools"]
        assert tools[name] == profiles[name]["latest_reviewed_stable"]
    workflow = (ROOT / "template/.github/workflows/ci.yml.jinja").read_text()
    uv = contract["base"]["uv"]
    assert f"Set up uv {uv}\n" in workflow
    assert contract["profiles"]["python"]["tools"]["uv"] == uv
    install = (ROOT / "template/.csarc/scripts/install-tool").read_text()
    listed = re.search(r"install-tool ([a-z|-]+)\.", install)
    assert listed is not None
    assert (
        sorted(listed.group(1).split("|"))
        == (contract["base"]["downloaded_by_install_tool"])
    )
    assert "docker-socket" in contract["image"]["forbidden"]
    assert "container" in contract["unsupported_modules"]


# AC4: the retire pull request comes from a branch, never the operator tree


def git(cwd: Path, *arguments: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", *arguments],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a clone whose github.com origin resolves to a local bare repo."""
    for key in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{key}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{key}_EMAIL", "test@example.invalid")
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    work = tmp_path / "work"
    git(tmp_path, "init", "-b", "main", str(work))
    (work / ".csarc").mkdir()
    (work / ".csarc/config.yml").write_text(config() + "_commit: v1.2.3\n")
    (work / ".github").mkdir()
    (work / ".github/pull_request_template.md").write_text("## Summary\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "init")
    url = f"https://github.com/{REPO}"
    git(work, "remote", "add", "origin", url)
    git(work, "config", f"url.{bare}.insteadOf", url)
    git(work, "push", "origin", "main")
    return work


def test_git_switch_opens_a_draft_governance_switch_pull_request(
    clone: Path,
) -> None:
    updates: list[list[str]] = []
    created: list[list[str]] = []

    def update(tree: Path, arguments: list[str]) -> None:
        updates.append(arguments)
        path = tree / ".csarc/config.yml"
        path.write_text(
            path.read_text()
            .replace("self-hosted", "hosted")
            .split("self_hosted_runner")[0]
        )

    def create(arguments: list[str]) -> str:
        created.append(arguments)
        return f"https://github.com/{REPO}/pull/42\n"

    switch = self_hosted.GitSwitch(clone, update=update, create=create)
    url = switch.open_pull_request(REPO, "main", "hosted")
    assert url == f"https://github.com/{REPO}/pull/42"
    assert updates == [
        [
            "--data",
            "verification_mode_private=hosted",
            "--data",
            "project_visibility=public",
            "--retire-public-transition",
            "--to",
            "v1.2.3",
            "--yes",
            "--non-interactive",
        ]
    ]
    (arguments,) = created
    assert arguments[4:7] == ["--draft", "--base", "main"]
    assert arguments[arguments.index("--label") + 1] == "governance-switch"
    assert arguments[-1] == "## Summary\n"
    branch = self_hosted.RETIRE_BRANCH
    pushed = git(clone, "ls-remote", "origin", f"refs/heads/{branch}")
    assert pushed
    changed = git(clone, "show", "--name-only", "--format=", pushed.split()[0])
    assert changed == ".csarc/config.yml"
    # The operator's own tree and branch never change.
    assert git(clone, "status", "--porcelain") == ""
    assert git(clone, "branch", "--show-current") == "main"
    assert "self-hosted" in (clone / ".csarc/config.yml").read_text()
    assert len(git(clone, "worktree", "list").splitlines()) == 1


def test_git_switch_refuses_a_clone_of_another_repository(
    clone: Path,
) -> None:
    switch = self_hosted.GitSwitch(
        clone, update=lambda *_: None, create=lambda _: ""
    )
    with pytest.raises(self_hosted.SelfHostedError, match="is not a clone"):
        switch.open_pull_request("acme/other", "main", "hosted")
