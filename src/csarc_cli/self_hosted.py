"""Manage on-demand self-hosted verification windows (Issue #1271).

ADR self-hosted-verification D7, D9, D10, and D11, and SPEC-011 §8: a
repository administrator opens a 24-hour window on the registered
csarc-devops VM, extends or closes it, reads its status, dispatches
`csarc-verify.yml` for one pull request, and retires the self-hosted data
before the repository becomes public.

Every command first prints a read-only inventory. A command that changes
anything does so only with `--apply`. GitHub calls use the operator's own
`gh` login; the registration token stays in memory, reaches the VM only
through the csarc-devops delivery channel on standard input, and is never
written to a file, an argument list, or the output. The channel itself
(ADR C1) belongs to csarc-devops: this module defines only its protocol
and fails closed when no channel is configured.

This module is CLI-only and never ships to a generated project.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import yaml  # type: ignore[import-untyped]

from csarc_cli import settings_schema

WINDOW = timedelta(hours=24)
WARN_BEFORE = timedelta(hours=2)
# The job timeout of csarc-verify.yml: a shorter window cannot finish a job.
DISPATCH_CUTOFF = timedelta(minutes=30)
WORKFLOW_FILE = "csarc-verify.yml"
WORKFLOW_PATH = f".github/workflows/{WORKFLOW_FILE}"
CONFIG_PATH = ".csarc/config.yml"
ENVIRONMENTS = ("dev", "uat")
CHANNEL_ENV = "CSARC_SELF_HOSTED_CHANNEL"
PROTOCOL = "csarc-self-hosted-channel/1"
CHANNEL_ACTIONS = ("open", "extend", "close", "status")
# The channel inherits no GitHub credential from the operator's shell.
CREDENTIAL_ENV = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
)
TIME_FORMAT = "%Y-%m-%dT%H:%MZ"
READBACK_ATTEMPTS = 12
READBACK_INTERVAL = 5.0
RETIRE_BRANCH = "chore/retire-self-hosted-verification"
RETIRE_TITLE = "chore(settings): leave self-hosted verification before public"
REGISTER = (
    "Register with csarc-devops (one Issue in each repository, linked both "
    "ways), then set self_hosted_runner in a governance-switch pull request"
)


class SelfHostedError(RuntimeError):
    """A self-hosted window command stopped; the message says what next."""


class GitHub(Protocol):
    """The GitHub REST calls the window commands make as the operator."""

    def get(self, endpoint: str) -> dict[str, Any]:
        """Read one object."""
        ...

    def collection(self, endpoint: str, key: str) -> list[dict[str, Any]]:
        """Read every page of one keyed collection."""
        ...

    def post(self, endpoint: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """Send one POST and return its JSON object, or {} when empty."""
        ...

    def delete(self, endpoint: str) -> None:
        """Send one DELETE."""
        ...


class Channel(Protocol):
    """The csarc-devops delivery channel to the VM (ADR C1)."""

    def request(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Send one protocol request and return the decoded response."""
        ...


class Switch(Protocol):
    """Prepare the governance-switch pull request that `retire` opens."""

    def open_pull_request(self, repo: str, base: str, private_mode: str) -> str:
        """Return the URL of the draft pull request it opened."""
        ...


def gh(arguments: Sequence[str], stdin: str | None = None) -> str:
    """Run one `gh` command as the operator and return its stdout."""
    try:
        result = subprocess.run(  # noqa: S603
            ["gh", *arguments],  # noqa: S607
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise SelfHostedError(
            "GitHub CLI was not found: the window commands use your own "
            "'gh' login. Install it from https://cli.github.com/."
        ) from error
    if result.returncode:
        detail = (result.stderr.strip() or "no output").rstrip(".")
        raise SelfHostedError(
            f"GitHub request failed: {detail}. Run 'gh auth status', then "
            "run the command again."
        )
    return result.stdout


class GhApi:
    """`gh api` implementation of the GitHub calls."""

    def get(self, endpoint: str) -> dict[str, Any]:
        """Read one object."""
        payload = json.loads(gh(["api", "--method", "GET", endpoint]) or "{}")
        if not isinstance(payload, dict):
            raise SelfHostedError(
                f"GitHub response for '{endpoint}' is not an object: the "
                "API answered unexpectedly. Run the command again."
            )
        return payload

    def collection(self, endpoint: str, key: str) -> list[dict[str, Any]]:
        """Read every page of one keyed collection."""
        separator = "&" if "?" in endpoint else "?"
        pages = json.loads(
            gh(
                [
                    "api",
                    "--method",
                    "GET",
                    "--paginate",
                    "--slurp",
                    f"{endpoint}{separator}per_page=100",
                ]
            )
            or "[]"
        )
        items: list[dict[str, Any]] = []
        for page in pages if isinstance(pages, list) else [None]:
            values = page.get(key) if isinstance(page, dict) else None
            if not isinstance(values, list):
                raise SelfHostedError(
                    f"GitHub response for '{endpoint}' has no '{key}' list: "
                    "the API answered unexpectedly. Run the command again."
                )
            items += [item for item in values if isinstance(item, dict)]
        return items

    def post(self, endpoint: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """Send one POST with a JSON body on standard input."""
        output = gh(
            ["api", "--method", "POST", endpoint, "--input", "-"],
            stdin=json.dumps(dict(body)),
        )
        payload = json.loads(output) if output.strip() else {}
        return payload if isinstance(payload, dict) else {}

    def delete(self, endpoint: str) -> None:
        """Send one DELETE."""
        gh(["api", "--method", "DELETE", endpoint])


class MissingChannel:
    """Fail closed: csarc-devops has not published a delivery channel."""

    def request(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Refuse every request without contacting anything."""
        raise SelfHostedError(
            f"Self-hosted delivery channel for '{payload.get('action')}': "
            f"none is configured, because csarc-devops publishes it (ADR "
            f"C1). Set {CHANNEL_ENV} to the command csarc-devops provides; "
            "nothing was sent to the VM."
        )


class CommandChannel:
    """Run the csarc-devops channel command with JSON on standard input."""

    def __init__(self, argv: Sequence[str], timeout: float = 300) -> None:
        """Keep the command; it runs once per request."""
        self.argv = list(argv)
        self.timeout = timeout

    def request(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Send one request; never put its content on the command line."""
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in CREDENTIAL_ENV
        }
        action = payload.get("action")
        try:
            result = subprocess.run(  # noqa: S603
                self.argv,
                input=json.dumps(dict(payload)),
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SelfHostedError(
                f"Self-hosted delivery channel for '{action}' did not run: "
                f"{type(error).__name__}. Check {CHANNEL_ENV} with "
                "csarc-devops."
            ) from error
        if result.returncode:
            raise SelfHostedError(
                f"Self-hosted delivery channel for '{action}' failed: exit "
                f"status {result.returncode}. Ask csarc-devops to check the "
                "VM, then run the command again."
            )
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise SelfHostedError(
                f"Self-hosted delivery channel for '{action}' answered "
                "without JSON: the protocol was not followed. Ask "
                "csarc-devops to check the channel."
            ) from error
        if not isinstance(response, dict):
            raise SelfHostedError(
                f"Self-hosted delivery channel for '{action}' answered "
                "without an object: the protocol was not followed. Ask "
                "csarc-devops to check the channel."
            )
        return response


def configured_channel(
    environ: Mapping[str, str] | None = None,
) -> Channel:
    """Return the configured channel, or one that always fails closed."""
    value = (os.environ if environ is None else environ).get(CHANNEL_ENV, "")
    argv = shlex.split(value) if value.strip() else []
    return CommandChannel(argv) if argv else MissingChannel()


@dataclass(frozen=True)
class Window:
    """One VM window record, read through the channel."""

    runner_name: str
    started_at: datetime
    ends_at: datetime
    registration: str


def utc(value: object, what: str) -> datetime:
    """Parse one UTC timestamp from the channel."""
    text = str(value or "")
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?Z", text):
        raise SelfHostedError(
            f"Self-hosted window {what} '{text}' is not a UTC time: the "
            "channel broke the protocol. Ask csarc-devops to check it."
        )
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def stamp(value: datetime) -> str:
    """Format a window time the way csarc-verify.yml expects it."""
    return value.astimezone(UTC).strftime(TIME_FORMAT)


def left_text(delta: timedelta) -> str:
    """Format a remaining time such as 1h40m."""
    seconds = max(int(delta.total_seconds()), 0)
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"


def channel_call(channel: Channel, payload: Mapping[str, Any]) -> Window | None:
    """Send one request and return the validated window, if any."""
    action = str(payload["action"])
    response = channel.request({"protocol": PROTOCOL, **payload})
    if response.get("protocol") != PROTOCOL:
        raise SelfHostedError(
            f"Self-hosted delivery channel for '{action}' spoke another "
            f"protocol: expected '{PROTOCOL}'. Ask csarc-devops to update "
            "the channel."
        )
    if response.get("result") == "refused":
        reason = str(response.get("reason") or "no reason given").rstrip(".")
        raise SelfHostedError(
            f"The VM refused '{action}': {reason}. Confirm the registration "
            "is merged, and ask csarc-devops to update the allow list."
        )
    if response.get("result") != "ok":
        raise SelfHostedError(
            f"Self-hosted delivery channel for '{action}' did not confirm "
            "the result: it is neither ok nor refused. Ask csarc-devops to "
            "check the channel."
        )
    window = response.get("window")
    if window is None:
        return None
    if not isinstance(window, dict):
        raise SelfHostedError(
            f"Self-hosted delivery channel for '{action}' sent a bad "
            "window: it is not an object. Ask csarc-devops to check it."
        )
    registration = window.get("registration")
    if registration not in {"active", "expired"}:
        raise SelfHostedError(
            f"Self-hosted window registration '{registration}' is unknown: "
            "expected active or expired. Ask csarc-devops to check it."
        )
    return Window(
        runner_name=str(window.get("runner_name") or ""),
        started_at=utc(window.get("started_at"), "start"),
        ends_at=utc(window.get("ends_at"), "end"),
        registration=str(registration),
    )


def runner_identity(vm: str, env: str) -> tuple[str, list[str]]:
    """Return the SPEC-011 §7 runner name and labels."""
    return f"csarc-{vm}-{env}", sorted(
        {"self-hosted", f"csarc-vm-{vm}", f"csarc-env-{env}"}
    )


def target_environment(base_ref: str) -> str:
    """Return the environment a target branch needs (ADR D5), or ''."""
    if base_ref == "main":
        return "uat"
    return "dev" if re.fullmatch(r"dev/[mi].+", base_ref) else ""


@dataclass(frozen=True)
class Context:
    """The read-only facts every window command starts from."""

    repo: str
    private: bool
    admin: bool
    default_branch: str
    config_ref: str
    mode_private: str
    mode_public: str
    vm: str
    registration: str
    environments: tuple[str, ...]

    @property
    def mode(self) -> str:
        """Return the effective mode for the current visibility."""
        return self.mode_private if self.private else self.mode_public


def read_config(github: GitHub, repo: str, ref: str) -> dict[str, Any]:
    """Read `.csarc/config.yml` from the trusted ref as data."""
    payload = github.get(f"repos/{repo}/contents/{CONFIG_PATH}?ref={ref}")
    try:
        text = base64.b64decode(str(payload.get("content") or "")).decode()
        raw = yaml.safe_load(text)
    except (ValueError, yaml.YAMLError) as error:
        raise SelfHostedError(
            f"{CONFIG_PATH} on '{ref}' cannot be read: it is not valid "
            "YAML. Fix it through a pull request."
        ) from error
    if not isinstance(raw, dict):
        raise SelfHostedError(
            f"{CONFIG_PATH} on '{ref}' cannot be read: it is not a mapping. "
            "Fix it through a pull request."
        )
    try:
        if (
            settings_schema.declared_schema(raw)
            == settings_schema.SCHEMA_VERSION
        ):
            settings_schema.validate_current(raw)
        modes = settings_schema.verification_modes(raw)
    except settings_schema.SettingsSchemaError as error:
        raise SelfHostedError(str(error)) from error
    return {**raw, **modes}


def load_context(github: GitHub, repo: str, ref: str = "") -> Context:
    """Read the repository and its trusted settings."""
    info = github.get(f"repos/{repo}")
    private = info.get("private")
    if not isinstance(private, bool):
        raise SelfHostedError(
            f"Visibility of '{repo}' is unknown: GitHub did not return the "
            "private field. Run 'gh auth status', then run the command again."
        )
    default_branch = str(info.get("default_branch") or "main")
    config_ref = ref or default_branch
    config = read_config(github, repo, config_ref)
    runner = config.get("self_hosted_runner") or {}
    environments = config.get("self_hosted_environments") or []
    return Context(
        repo=repo,
        private=private,
        admin=(info.get("permissions") or {}).get("admin") is True,
        default_branch=default_branch,
        config_ref=config_ref,
        mode_private=str(config.get("verification_mode_private") or "local"),
        mode_public=str(config.get("verification_mode_public") or "hosted"),
        vm=str(runner.get("id") or "") if isinstance(runner, dict) else "",
        registration=(
            str(runner.get("registration") or "")
            if isinstance(runner, dict)
            else ""
        ),
        environments=tuple(
            str(env) for env in environments if env in ENVIRONMENTS
        ),
    )


def report(title: str, rows: Sequence[tuple[str, str]]) -> None:
    """Print one read-only inventory."""
    # message-pattern: allow-begin X5 read-only inventory printed as one unit
    sys.stdout.write(f"Inventory: {title} (read-only)\n")
    width = max(len(name) for name, _ in rows)
    for name, value in rows:
        sys.stdout.write(f"  {name.ljust(width)}  {value}\n")
    # message-pattern: allow-end


def notice(text: str) -> None:
    """Print one NOTICE line."""
    sys.stdout.write(f"NOTICE: {text}\n")


def warning(text: str) -> None:
    """Print one WARNING line to standard error."""
    sys.stderr.write(f"WARNING: {text}\n")


def ok(text: str) -> None:
    """Print one OK line."""
    sys.stdout.write(f"OK: {text}\n")


def inventory_only(command: str) -> int:
    """Close a run without --apply; nothing was changed."""
    notice(
        f"Inventory only, so nothing was changed. Run '{command} --apply' "
        "to continue."
    )
    return 0


def runner_rows(runners: Sequence[Mapping[str, Any]]) -> str:
    """Summarize runners for an inventory row."""
    if not runners:
        return "none"
    return "; ".join(
        f"{item.get('name')} ({item.get('status')}, id {item.get('id')})"
        for item in runners
    )


def labels_of(runner: Mapping[str, Any]) -> list[str]:
    """Return the sorted label names of one runner."""
    return sorted(
        str(label.get("name"))
        for label in runner.get("labels") or []
        if isinstance(label, dict)
    )


def classify_runners(
    context: Context, runners: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Split runners into one expected runner per environment and the rest."""
    expected: dict[str, Mapping[str, Any]] = {}
    unexpected: list[Mapping[str, Any]] = []
    for runner in runners:
        match = None
        for env in context.environments if context.vm else ():
            name, labels = runner_identity(context.vm, env)
            if runner.get("name") == name and labels_of(runner) == labels:
                match = env
        if match is None or match in expected:
            unexpected.append(runner)
        else:
            expected[match] = runner
    return expected, unexpected


def require_window_ready(context: Context, env: str, command: str) -> None:
    """Refuse a window command the repository cannot use."""
    if not context.private:
        raise SelfHostedError(
            f"'{command}' refused for '{context.repo}': the repository is "
            "public and never runs self-hosted jobs. Run 'csarc self-hosted "
            "retire' and use its public mode."
        )
    if not context.admin:
        raise SelfHostedError(
            f"'{command}' refused for '{context.repo}': your 'gh' login is "
            "not a repository administrator. Ask an administrator to run it."
        )
    if context.mode_private != "self-hosted":
        raise SelfHostedError(
            f"'{command}' refused for '{context.repo}': "
            f"verification_mode_private is '{context.mode_private}' on "
            f"'{context.config_ref}'. Switch it in a governance-switch pull "
            "request first."
        )
    if not context.vm:
        raise SelfHostedError(
            f"'{command}' refused for '{context.repo}': the repository is "
            f"not registered. {REGISTER}."
        )
    if env not in context.environments:
        raise SelfHostedError(
            f"'{command}' refused for '{context.repo}': '{env}' is not in "
            "self_hosted_environments. Register it with csarc-devops and "
            "add it in a governance-switch pull request."
        )


def window_rows(
    context: Context, env: str, runners: Sequence[Mapping[str, Any]]
) -> list[tuple[str, str]]:
    """Return the rows every window inventory shares (ADR D11)."""
    name, labels = runner_identity(context.vm or "<unregistered>", env)
    return [
        (
            "repository",
            f"{context.repo} ({'private' if context.private else 'public'})",
        ),
        ("administrator", "yes" if context.admin else "no"),
        ("settings ref", context.config_ref),
        ("private mode", context.mode_private),
        ("VM", context.vm or "not registered"),
        ("registration", context.registration or "none"),
        ("environment", env),
        ("runner", f"{name} labels {','.join(labels)}"),
        (
            "runs",
            f"only {WORKFLOW_PATH}, with a read-only token and no secrets",
        ),
        ("current runners", runner_rows(runners)),
    ]


def remove_all(
    github: GitHub, repo: str, runners: Sequence[Mapping[str, Any]]
) -> None:
    """Remove every listed runner; a leaked token may have added one."""
    for runner in runners:
        github.delete(f"repos/{repo}/actions/runners/{runner.get('id')}")


@dataclass
class Session:
    """Injected collaborators, replaced by stubs in tests."""

    github: GitHub
    channel: Channel
    now: Callable[[], datetime]
    sleep: Callable[[float], None]
    switch: Switch | None = None


def default_session(checkout: Path | None = None) -> Session:
    """Return the live collaborators."""
    return Session(
        github=GhApi(),
        channel=configured_channel(),
        now=lambda: datetime.now(UTC),
        sleep=time.sleep,
        switch=GitSwitch(checkout or Path.cwd()),
    )


def runners_of(session: Session, repo: str) -> list[dict[str, Any]]:
    """Read every repository runner."""
    return session.github.collection(f"repos/{repo}/actions/runners", "runners")


def open_window(session: Session, repo: str, env: str, apply: bool) -> int:
    """`csarc self-hosted open --env ENV` (ADR D7)."""
    context = load_context(session.github, repo)
    runners = runners_of(session, repo) if context.admin else []
    ends = session.now() + WINDOW
    report(
        f"open a {env} window",
        [
            *window_rows(context, env, runners),
            ("window end", f"{stamp(ends)} (24h, fixed)"),
        ],
    )
    require_window_ready(context, env, "open")
    expected, unexpected = classify_runners(context, runners)
    if unexpected:
        raise SelfHostedError(
            f"'open' refused for '{repo}': unexpected runners are registered "
            f"({runner_rows(unexpected)}). Treat it as a leaked registration "
            "token: remove them in the repository settings and tell "
            "csarc-devops."
        )
    if env in expected:
        notice(
            f"A {env} window runner is already registered, so 'open' extends "
            "that window instead of registering a second runner."
        )
        return extend_window(session, repo, env, apply, context=context)
    if not apply:
        return inventory_only(f"csarc self-hosted open --env {env}")
    if isinstance(session.channel, MissingChannel):
        # Fail closed before any token exists.
        session.channel.request({"action": "open"})
    name, labels = runner_identity(context.vm, env)
    token = str(
        session.github.post(
            f"repos/{repo}/actions/runners/registration-token", {}
        ).get("token")
        or ""
    )
    if not token:
        raise SelfHostedError(
            f"Runner registration token for '{repo}' is missing: GitHub "
            "returned none. Run 'gh auth status', then run 'open' again."
        )
    request = {
        "action": "open",
        "repository": repo,
        "vm": context.vm,
        "environment": env,
        "runner_name": name,
        "labels": labels,
        "ends_at": stamp(ends),
        "registration_token": token,
    }
    del token
    try:
        window = channel_call(session.channel, request)
    finally:
        request.pop("registration_token")
    if window is None or window.runner_name != name:
        raise SelfHostedError(
            f"The VM did not confirm the {env} window: no runner '{name}' "
            "was reported. Run 'csarc self-hosted status', then ask "
            "csarc-devops."
        )
    readback(session, context, env)
    ok(
        f"Opened the {env} window on '{repo}': runner '{name}' is online "
        f"until {stamp(window.ends_at)}."
    )
    return 0


def readback(session: Session, context: Context, env: str) -> None:
    """Confirm exactly one expected runner; remove all on any surprise."""
    name, _ = runner_identity(context.vm, env)
    for attempt in range(READBACK_ATTEMPTS):
        runners = runners_of(session, context.repo)
        expected, unexpected = classify_runners(context, runners)
        if unexpected:
            remove_all(session.github, context.repo, runners)
            raise SelfHostedError(
                f"Unexpected runners appeared on '{context.repo}' "
                f"({runner_rows(unexpected)}), so every runner was removed: "
                "the registration token may have leaked. Tell csarc-devops "
                "and review the repository audit log."
            )
        if expected.get(env, {}).get("status") == "online":
            return
        if attempt + 1 < READBACK_ATTEMPTS:
            session.sleep(READBACK_INTERVAL)
    raise SelfHostedError(
        f"Runner '{name}' is not online on '{context.repo}': the VM did "
        "not register it in time. Run 'csarc self-hosted status', or run "
        "'close' and 'open' again."
    )


def current_window(
    session: Session, context: Context, env: str
) -> Window | None:
    """Read the VM window record through the channel."""
    name, labels = runner_identity(context.vm, env)
    return channel_call(
        session.channel,
        {
            "action": "status",
            "repository": context.repo,
            "vm": context.vm,
            "environment": env,
            "runner_name": name,
            "labels": labels,
        },
    )


def extend_window(
    session: Session,
    repo: str,
    env: str,
    apply: bool,
    *,
    context: Context | None = None,
) -> int:
    """`csarc self-hosted extend --env ENV`: now + 24h, never cumulative."""
    first = context is None
    context = context or load_context(session.github, repo)
    runners = runners_of(session, repo) if context.admin else []
    ends = session.now() + WINDOW
    window = None
    if context.vm and env in context.environments:
        window = current_window(session, context, env)
    if first:
        report(f"extend the {env} window", window_rows(context, env, runners))
    report(
        f"extend the {env} window end",
        [
            ("current end", stamp(window.ends_at) if window else "no window"),
            ("new end", f"{stamp(ends)} (now + 24h, not cumulative)"),
        ],
    )
    require_window_ready(context, env, "extend")
    expected, unexpected = classify_runners(context, runners)
    name, _ = runner_identity(context.vm, env)
    if unexpected:
        raise SelfHostedError(
            f"'extend' refused for '{repo}': unexpected runners are "
            f"registered ({runner_rows(unexpected)}). Remove them, tell "
            "csarc-devops, and open a new window."
        )
    if (
        window is None
        or window.ends_at <= session.now()
        or expected.get(env, {}).get("status") != "online"
    ):
        raise SelfHostedError(
            f"'extend' refused for '{repo}': no open {env} window with "
            f"runner '{name}' online. Run 'csarc self-hosted open --env "
            f"{env}'."
        )
    if not apply:
        return inventory_only(f"csarc self-hosted extend --env {env}")
    extended = channel_call(
        session.channel,
        {
            "action": "extend",
            "repository": repo,
            "vm": context.vm,
            "environment": env,
            "runner_name": name,
            "ends_at": stamp(ends),
        },
    )
    if extended is None or extended.runner_name != name:
        raise SelfHostedError(
            f"The VM did not confirm the {env} extension: no runner '{name}' "
            "was reported. Run 'csarc self-hosted status', then ask "
            "csarc-devops."
        )
    if extended.ends_at > ends + timedelta(minutes=5):
        raise SelfHostedError(
            f"The VM extended the {env} window past now + 24h, to "
            f"{stamp(extended.ends_at)}: windows never accumulate. Run "
            f"'csarc self-hosted close --env {env}' and tell csarc-devops."
        )
    readback(session, context, env)
    ok(
        f"Extended the {env} window on '{repo}' to "
        f"{stamp(extended.ends_at)} with the same runner '{name}'."
    )
    return 0


def close_window(session: Session, repo: str, env: str, apply: bool) -> int:
    """`csarc self-hosted close --env ENV`: remove the window runner."""
    context = load_context(session.github, repo)
    runners = runners_of(session, repo) if context.admin else []
    report(f"close the {env} window", window_rows(context, env, runners))
    if not context.admin:
        raise SelfHostedError(
            f"'close' refused for '{repo}': your 'gh' login is not a "
            "repository administrator. Ask an administrator to run it."
        )
    name = runner_identity(context.vm, env)[0] if context.vm else ""
    targets = [item for item in runners if name and item.get("name") == name]
    if not targets:
        notice(f"No runner '{name or 'csarc-<id>-' + env}' is registered.")
    if not apply:
        return inventory_only(f"csarc self-hosted close --env {env}")
    remove_all(session.github, repo, targets)
    if isinstance(session.channel, MissingChannel):
        notice(
            "No delivery channel is configured, so the VM stops its runner "
            "and deletes the runner credentials when the window ends."
        )
    elif context.vm:
        channel_call(
            session.channel,
            {
                "action": "close",
                "repository": repo,
                "vm": context.vm,
                "environment": env,
                "runner_name": name,
            },
        )
    ok(f"Closed the {env} window on '{repo}': removed {len(targets)} runner.")
    return 0


def verify_runs(session: Session, repo: str) -> list[dict[str, Any]]:
    """Read every run of csarc-verify.yml."""
    return [
        run
        for run in session.github.collection(
            f"repos/{repo}/actions/runs", "workflow_runs"
        )
        if run.get("path") == WORKFLOW_PATH
    ]


def status(session: Session, repo: str, env: str | None) -> int:
    """`csarc self-hosted status`: read-only (ADR D7, D9)."""
    context = load_context(session.github, repo)
    runners = runners_of(session, repo) if context.admin else []
    envs = [env] if env else list(context.environments or ENVIRONMENTS)
    report(
        "self-hosted status",
        [
            (
                "repository",
                f"{repo} ({'private' if context.private else 'public'})",
            ),
            ("effective mode", context.mode),
            ("VM", context.vm or "not registered"),
            ("registration", context.registration or "none"),
            ("environments", ",".join(context.environments) or "none"),
            (
                "current runners",
                runner_rows(runners) if context.admin else "needs an admin",
            ),
        ],
    )
    if not context.private and (
        verify_runs(session, repo) or context.mode_private == "self-hosted"
    ):
        warning(
            f"Self-hosted logs on '{repo}' are public: the repository is "
            "public and still has self-hosted runs or settings. Run "
            "'csarc self-hosted retire', then review its inventory."
        )
    if context.mode_private != "self-hosted":
        notice(
            f"verification_mode_private is '{context.mode_private}', so no "
            "self-hosted window applies."
        )
        return 0
    if not context.vm:
        notice(f"The repository is not registered. {REGISTER}.")
        return 0
    now = session.now()
    for item in envs:
        if item not in context.environments:
            notice(f"'{item}' is not in self_hosted_environments.")
            continue
        window = current_window(session, context, item)
        if window is not None and window.registration == "expired":
            warning(
                f"Self-hosted registration on '{repo}' expired: no window "
                "opened for 90 days. Register again with csarc-devops."
            )
        if window is None or window.ends_at <= now:
            notice(
                f"No {item} window is open. Run 'csarc self-hosted open "
                f"--env {item}' to open one."
            )
            continue
        left = window.ends_at - now
        # message-pattern: allow X5 one window row of the status report
        sys.stdout.write(
            f"  {item} window: runner {window.runner_name}, started "
            f"{stamp(window.started_at)}, ends {stamp(window.ends_at)} "
            f"({left_text(left)} left)\n"
        )
        if left < DISPATCH_CUTOFF:
            warning(
                f"Self-hosted {item} window accepts no new jobs: it ends at "
                f"{stamp(window.ends_at)} ({left_text(left)} left). Run "
                f"'csarc self-hosted extend --env {item}'."
            )
        elif left < WARN_BEFORE:
            warning(
                f"Self-hosted {item} verification: the window ends at "
                f"{stamp(window.ends_at)} ({left_text(left)} left). Run "
                f"'csarc self-hosted extend --env {item}' before it closes."
            )
    return 0


def verify(session: Session, repo: str, number: int, apply: bool) -> int:
    """`csarc self-hosted verify --pr N`: dispatch csarc-verify.yml."""
    pull = session.github.get(f"repos/{repo}/pulls/{number}")
    base = str((pull.get("base") or {}).get("ref") or "")
    head = pull.get("head") or {}
    head_repo = str((head.get("repo") or {}).get("full_name") or "")
    head_sha = str(head.get("sha") or "")
    context = load_context(session.github, repo, base)
    env = target_environment(base)
    window = None
    if (
        context.private
        and context.mode_private == "self-hosted"
        and context.vm
        and env in context.environments
    ):
        window = current_window(session, context, env)
    now = session.now()
    left = window.ends_at - now if window else timedelta(0)
    report(
        f"dispatch {WORKFLOW_FILE} for pull request #{number}",
        [
            (
                "repository",
                f"{repo} ({'private' if context.private else 'public'})",
            ),
            ("effective mode", context.mode),
            ("head repository", head_repo or "unknown"),
            ("head SHA", head_sha or "unknown"),
            ("target branch", base or "unknown"),
            ("environment", env or "none"),
            (
                "window",
                f"ends {stamp(window.ends_at)} ({left_text(left)} left)"
                if window
                else "none",
            ),
        ],
    )
    again = f"Run 'csarc self-hosted extend --env {env}' or 'open' first"
    refusals = (
        (
            not context.private,
            "the repository is public",
            "Verify it in its public mode",
        ),
        (
            context.mode != "self-hosted",
            f"the effective mode on '{base}' is '{context.mode}'",
            "Verify it in that mode",
        ),
        (
            pull.get("state") != "open",
            "the pull request is not open",
            "Dispatch an open pull request",
        ),
        (
            head_repo != repo,
            "the head is a fork",
            "Fork pull requests never run on the VM; verify it in another mode",
        ),
        (
            not env,
            f"'{base}' has no self-hosted environment",
            "Target 'main', 'dev/m*', or 'dev/i*'",
        ),
        (not context.vm, "the repository is not registered", REGISTER),
        (
            env not in context.environments,
            f"'{env}' is not registered",
            REGISTER,
        ),
        (
            window is None or left <= timedelta(0),
            f"no {env} window is open",
            again,
        ),
        (
            left < DISPATCH_CUTOFF,
            "the window has less than 30m left, so it accepts no new jobs",
            again,
        ),
    )
    for refused, reason, next_step in refusals:
        if refused:
            raise SelfHostedError(
                f"'verify' refused for pull request #{number}: {reason}. "
                f"{next_step}."
            )
    assert window is not None  # noqa: S101 - narrowed by the refusals above
    if left < WARN_BEFORE:
        warning(
            f"Self-hosted {env} verification: the window ends at "
            f"{stamp(window.ends_at)} ({left_text(left)} left). Run "
            f"'csarc self-hosted extend --env {env}' before it closes."
        )
    if not apply:
        return inventory_only(f"csarc self-hosted verify --pr {number}")
    session.github.post(
        f"repos/{repo}/actions/workflows/{WORKFLOW_FILE}/dispatches",
        {
            "ref": base,
            "inputs": {
                "pull_request": str(number),
                "head_sha": head_sha,
                "environment": env,
                "window_end": stamp(window.ends_at),
            },
        },
    )
    ok(
        f"Dispatched {WORKFLOW_FILE} on '{base}' for pull request #{number} "
        f"at {head_sha} in '{env}'."
    )
    return 0


def retire(
    session: Session, repo: str, private_mode: str | None, apply: bool
) -> int:
    """`csarc self-hosted retire`: clear VM data before going public."""
    context = load_context(session.github, repo)
    if not context.admin:
        raise SelfHostedError(
            f"'retire' refused for '{repo}': your 'gh' login is not a "
            "repository administrator. Ask an administrator to run it."
        )
    runs = verify_runs(session, repo)
    artifacts = {
        int(run["id"]): session.github.collection(
            f"repos/{repo}/actions/runs/{run['id']}/artifacts", "artifacts"
        )
        for run in runs
    }
    caches = session.github.collection(
        f"repos/{repo}/actions/caches", "actions_caches"
    )
    runners = runners_of(session, repo)
    leaving = context.mode_private == "self-hosted"
    new_mode = private_mode or context.mode_public
    report(
        "retire self-hosted data before the repository becomes public",
        [
            (
                "repository",
                f"{repo} ({'private' if context.private else 'public'})",
            ),
            (
                f"{WORKFLOW_FILE} runs",
                ", ".join(str(run["id"]) for run in runs) or "none",
            ),
            (
                "artifacts",
                ", ".join(
                    str(item.get("id"))
                    for items in artifacts.values()
                    for item in items
                )
                or "none",
            ),
            (
                "Actions caches",
                ", ".join(str(item.get("id")) for item in caches) or "none",
            ),
            ("runners", runner_rows(runners)),
            (
                "settings change",
                f"verification_mode_private self-hosted -> {new_mode}, drop "
                "self_hosted_runner and self_hosted_environments, re-render "
                "in public mode (draft governance-switch pull request)"
                if leaving
                else "none",
            ),
        ],
    )
    if not apply:
        return inventory_only("csarc self-hosted retire")
    failed: list[str] = []
    steps: list[tuple[str, str]] = [
        (f"artifact {item.get('id')}", f"actions/artifacts/{item.get('id')}")
        for items in artifacts.values()
        for item in items
    ]
    steps += [(f"run {run['id']}", f"actions/runs/{run['id']}") for run in runs]
    steps += [
        (f"cache {item.get('id')}", f"actions/caches/{item.get('id')}")
        for item in caches
    ]
    steps += [
        (f"runner {item.get('name')}", f"actions/runners/{item.get('id')}")
        for item in runners
    ]
    for label, endpoint in steps:
        try:
            session.github.delete(f"repos/{repo}/{endpoint}")
        except SelfHostedError as error:
            failed.append(label)
            warning(f"Could not delete {label}: {error}")
    url = ""
    if leaving:
        try:
            if session.switch is None:
                raise SelfHostedError(
                    "Governance-switch pull request: no checkout was given. "
                    "Run 'retire --apply' inside a clone of the repository."
                )
            url = session.switch.open_pull_request(
                repo, context.default_branch, new_mode
            )
        except (SelfHostedError, OSError, subprocess.SubprocessError) as error:
            failed.append("governance-switch pull request")
            warning(
                f"Governance-switch pull request was not opened: {error} "
                "Run 'csarc update --data verification_mode_private="
                f"{new_mode} --data project_visibility=public' on a branch."
            )
    # message-pattern: allow-begin X5 exit notice text for csarc-devops
    sys.stdout.write(
        "Exit notice for csarc-devops:\n"
        f"  {repo} leaves self-hosted verification before it becomes "
        "public. Remove it from the allow list and delete its VM data.\n"
    )
    # message-pattern: allow-end
    if failed:
        raise SelfHostedError(
            f"'retire' did not finish: {', '.join(failed)} failed, and "
            "their logs stay visible once the repository is public. Fix "
            "the cause and run 'csarc self-hosted retire --apply' again."
        )
    ok(
        f"Retired self-hosted data on '{repo}': deleted {len(steps)} items"
        + (f" and opened {url}." if url else ".")
    )
    return 0


class GitSwitch:
    """Open the retire pull request from a clean clone (ADR D9, Q4)."""

    def __init__(
        self,
        checkout: Path,
        update: Callable[[Path, list[str]], None] | None = None,
        create: Callable[[list[str]], str] | None = None,
    ) -> None:
        """Keep the operator's clone; its working tree is never changed."""
        self.checkout = checkout
        self.update = update or run_update
        self.create = create or gh

    def git(self, *arguments: str, cwd: Path | None = None) -> str:
        """Run one git command."""
        return subprocess.run(  # noqa: S603
            ["git", *arguments],  # noqa: S607
            cwd=cwd or self.checkout,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def open_pull_request(self, repo: str, base: str, private_mode: str) -> str:
        """Render the new mode on a branch and open a draft pull request."""
        origin = self.git("config", "--get", "remote.origin.url")
        if not re.search(
            rf"github\.com[:/]{re.escape(repo)}(?:\.git)?$", origin
        ):
            raise SelfHostedError(
                f"Governance-switch pull request: '{self.checkout}' is not a "
                f"clone of '{repo}'. Run the command in a clone of it."
            )
        self.git("fetch", "origin", base)
        with tempfile.TemporaryDirectory(prefix="csarc-retire-") as temp:
            tree = Path(temp) / "tree"
            self.git(
                "worktree",
                "add",
                "-B",
                RETIRE_BRANCH,
                str(tree),
                f"origin/{base}",
            )
            try:
                saved = yaml.safe_load(
                    (tree / CONFIG_PATH).read_text(encoding="utf-8")
                )
                release = str((saved or {}).get("_commit") or "")
                # Keep the recorded release: only the mode and render change.
                self.update(
                    tree,
                    [
                        "--data",
                        f"verification_mode_private={private_mode}",
                        "--data",
                        "project_visibility=public",
                        *(["--to", release] if release else []),
                        "--yes",
                        "--non-interactive",
                    ],
                )
                self.git("add", "-A", cwd=tree)
                self.git(
                    "commit",
                    "-m",
                    f"{RETIRE_TITLE}\n\nADR self-hosted-verification D9: "
                    "re-render in public mode after 'csarc self-hosted "
                    "retire'.",
                    cwd=tree,
                )
                self.git("push", "-u", "origin", RETIRE_BRANCH, cwd=tree)
                template = tree / ".github" / "pull_request_template.md"
                body = template.read_text() if template.is_file() else ""
                output = self.create(
                    [
                        "pr",
                        "create",
                        "--repo",
                        repo,
                        "--draft",
                        "--base",
                        base,
                        "--head",
                        RETIRE_BRANCH,
                        "--label",
                        "governance-switch",
                        "--title",
                        RETIRE_TITLE,
                        "--body",
                        body,
                    ]
                )
                return output.strip().splitlines()[-1]
            finally:
                self.git("worktree", "remove", "--force", str(tree))


def run_update(tree: Path, arguments: list[str]) -> None:
    """Run `csarc update` on the retire branch as a separate process."""
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "csarc_cli.cli",
            "update",
            str(tree),
            *arguments,
        ],
        check=True,
    )


def resolve_repo(value: str) -> str:
    """Return OWNER/NAME from the option or the current clone."""
    repo = (
        value
        or gh(
            ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]
        ).strip()
    )
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", repo):
        raise SelfHostedError(
            f"Repository '{repo}' is not OWNER/NAME: it cannot be read. "
            "Pass '--repo OWNER/NAME'."
        )
    return repo


def command(args: argparse.Namespace, session: Session | None = None) -> int:
    """Run one `csarc self-hosted` subcommand."""
    session = session or default_session(getattr(args, "path", None))
    repo = resolve_repo(args.repo)
    action = args.self_hosted_command
    if action == "open":
        return open_window(session, repo, args.env, args.apply)
    if action == "extend":
        return extend_window(session, repo, args.env, args.apply)
    if action == "close":
        return close_window(session, repo, args.env, args.apply)
    if action == "status":
        return status(session, repo, args.env)
    if action == "verify":
        return verify(session, repo, args.pr, args.apply)
    return retire(session, repo, args.private_mode, args.apply)


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Add `csarc self-hosted` and its subcommands."""
    parser = subparsers.add_parser(
        "self-hosted",
        help="open, extend, close, and use a self-hosted verification window",
    )
    commands = parser.add_subparsers(dest="self_hosted_command", required=True)
    helps = {
        "open": "open a 24h window on the registered VM",
        "extend": "move the window end to now + 24h",
        "close": "remove the window runner",
        "status": "show windows, time left, and public warnings",
        "verify": f"dispatch {WORKFLOW_FILE} for one pull request",
        "retire": (
            "required before the repository becomes public: delete "
            "self-hosted runs, artifacts, caches, and runners"
        ),
    }
    for name, text in helps.items():
        sub = commands.add_parser(name, help=text, description=text)
        sub.add_argument("--repo", default="", metavar="OWNER/NAME")
        if name in {"open", "extend", "close"}:
            sub.add_argument("--env", required=True, choices=ENVIRONMENTS)
        if name == "status":
            sub.add_argument("--env", choices=ENVIRONMENTS)
        if name == "verify":
            sub.add_argument("--pr", required=True, type=int)
        if name == "retire":
            sub.add_argument(
                "--private-mode",
                choices=("hosted", "local"),
                help="new verification_mode_private (default: the public mode)",
            )
            sub.add_argument(
                "--path",
                type=Path,
                default=None,
                help="clone that opens the pull request (default: current)",
            )
        if name != "status":
            sub.add_argument(
                "--apply",
                action="store_true",
                help="act after the inventory (default: inventory only)",
            )
