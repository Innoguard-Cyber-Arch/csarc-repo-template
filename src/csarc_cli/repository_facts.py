#!/usr/bin/env python3
"""Detect repository facts without changing saved intent (Issue #1072).

This is the one detector contract shared by the pinned CLI
(`src/csarc_cli/repository_facts.py`), this repository's scripts, and every
generated repository (`.csarc/scripts/repository_facts.py`); the three
copies stay byte-identical. SPEC-009 classifies what it reports:

* live facts (origin, identity, visibility, default branch, plan,
  permissions, and observable security capabilities) are read every time
  and never written to `.csarc/config.yml`;
* derived context (the Python package name and the product run command) is
  produced only when native manifests resolve exactly one value.

Every fact carries one closed state. ``known`` holds a value observed now;
``unknown`` means the fact could not be observed (offline, missing
permission, no GitHub origin) and carries the reason instead of a guess or
a stale value; ``ambiguous`` means several candidates exist and the caller
must ask for one explicit decision instead of picking one.

The detector never writes anything. Git and GitHub reads go through
injected runners, so callers and tests decide how they are executed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

CONTRACT = "csarc-repository-facts/v1"
KNOWN = "known"
UNKNOWN = "unknown"
AMBIGUOUS = "ambiguous"
STATES = (KNOWN, UNKNOWN, AMBIGUOUS)
LIVE_FACTS = (
    "origin",
    "identity",
    "visibility",
    "default_branch",
    "plan",
    "permissions",
    "security",
)
REMOTE_FACTS = LIVE_FACTS[1:]
VISIBILITIES = frozenset({"public", "private", "internal"})
# Security capabilities GitHub reports in `security_and_analysis`; the
# payload only carries them for callers with admin access.
SECURITY_FEATURES = (
    "advanced_security",
    "code_security",
    "dependabot_security_updates",
    "secret_scanning",
    "secret_scanning_push_protection",
)
# Native manifest per language, in the template's run-command order.
LANGUAGE_MANIFESTS = (
    ("python", "pyproject.toml"),
    ("typescript", "package.json"),
    ("rust", "Cargo.toml"),
    ("go", "go.mod"),
)
LANGUAGE_COMMANDS = {
    "typescript": "pnpm run build",
    "rust": "cargo test --locked",
    "go": "go build ./...",
}
PACKAGE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
_GITHUB_REMOTE = re.compile(
    r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/|gh:)"
    r"(?P<slug>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)
_REMOTE_URL = re.compile(r"^remote\.(?P<name>.+)\.url (?P<url>.+)$")

# A runner executes one argument vector and returns (code, stdout, stderr).
Runner = Callable[[Sequence[str]], tuple[int, str, str]]
Fact = dict[str, object]


def fact(
    state: str,
    value: object = None,
    *,
    source: str = "",
    reason: str = "",
    candidates: Sequence[str] = (),
) -> Fact:
    """Return one fact in the closed detector shape."""
    if state not in STATES:
        raise ValueError(f"unknown fact state {state!r}")
    result: Fact = {
        "reason": reason,
        "source": source,
        "state": state,
        "value": value if state == KNOWN else None,
    }
    if state == AMBIGUOUS:
        result["candidates"] = sorted(candidates)
    return result


def known(value: object, source: str) -> Fact:
    """Return a fact observed now."""
    return fact(KNOWN, value, source=source)


def unknown(reason: str, source: str = "") -> Fact:
    """Return a fact that could not be observed, with the reason."""
    return fact(UNKNOWN, source=source, reason=reason)


def github_slug(url: str) -> str | None:
    """Return ``owner/repository`` for a GitHub remote URL, if it is one."""
    match = _GITHUB_REMOTE.fullmatch(url.strip())
    return match.group("slug") if match else None


def repository_url(slug: str) -> str:
    """Return the canonical repository URL for ``owner/repository``."""
    return f"https://github.com/{slug}"


def same_repository(left: str, right: str) -> bool:
    """Return whether two repository URLs or slugs name one repository."""
    left_slug = github_slug(left) or left
    right_slug = github_slug(right) or right
    return left_slug.casefold() == right_slug.casefold()


def _execute(arguments: Sequence[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(  # noqa: S603
            list(arguments), capture_output=True, text=True, check=False
        )
    except OSError as error:
        return 127, "", f"{arguments[0]} is unavailable: {error}"
    return result.returncode, result.stdout, result.stderr


def git_runner(root: Path) -> Runner:
    """Return a runner for read-only Git commands in ``root``."""
    return lambda arguments: _execute(["git", "-C", str(root), *arguments])


def api_runner() -> Runner:
    """Return a runner for read-only GitHub REST requests through `gh`."""
    return lambda arguments: _execute(
        ["gh", "api", "--method", "GET", *arguments]
    )


def observe_origin(
    root: Path, git: Runner, env: Mapping[str, str] | None = None
) -> Fact:
    """Return the GitHub repository URL that identifies ``root``.

    Only the ``origin`` remote of ``root`` itself identifies the
    repository; an enclosing repository's remote never does. Without an
    origin, an explicit ``GH_REPO`` is used. Other remotes are never
    guessed, so several of them leave the origin ambiguous.
    """
    environment = os.environ if env is None else env
    explicit = environment.get("GH_REPO", "").strip()
    explicit_slug = github_slug(f"gh:{explicit}") if explicit else None
    code, top, _error = git(["rev-parse", "--show-toplevel"])
    if code != 0 or Path(top.strip()).resolve() != root.resolve():
        if explicit_slug is not None:
            return known(repository_url(explicit_slug), "GH_REPO")
        return unknown(f"{root} is not the root of a Git repository")
    code, output, _error = git(["config", "--get-regexp", r"^remote\..*\.url$"])
    remotes: dict[str, str] = {}
    for line in output.splitlines() if code == 0 else []:
        match = _REMOTE_URL.fullmatch(line.strip())
        if match is not None:
            remotes[match.group("name")] = match.group("url")
    origin = remotes.get("origin")
    if origin is not None:
        slug = github_slug(origin)
        if slug is None:
            return unknown("the origin remote is not a GitHub URL", "origin")
        return known(repository_url(slug), "origin")
    if explicit_slug is not None:
        return known(repository_url(explicit_slug), "GH_REPO")
    others = sorted(name for name, url in remotes.items() if github_slug(url))
    if len(others) > 1:
        return fact(
            AMBIGUOUS,
            source="remotes",
            reason="no origin remote; several GitHub remotes are not guessed",
            candidates=[
                repository_url(str(github_slug(remotes[name])))
                for name in others
            ],
        )
    if others:
        return unknown(
            f"no origin remote; remote {others[0]!r} is not guessed",
            "remotes",
        )
    return unknown("no origin remote or GH_REPO identifies the repository")


def _unknown_remote_facts(reason: str, source: str = "") -> dict[str, Fact]:
    return {name: unknown(reason, source) for name in REMOTE_FACTS}


def observe_repository(slug: str, api: Runner) -> dict[str, Fact]:
    """Return the facts one read of the GitHub repository can observe."""
    code, output, error = api([f"repos/{slug}"])
    if code != 0:
        return _unknown_remote_facts(
            error.strip() or "GitHub API request failed", "github"
        )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return _unknown_remote_facts(
            "GitHub returned invalid repository JSON", "github"
        )
    owner = payload.get("owner") if isinstance(payload, dict) else None
    full_name = payload.get("full_name") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or not isinstance(owner, dict)
        or not isinstance(owner.get("login"), str)
        or not isinstance(owner.get("type"), str)
        or not isinstance(full_name, str)
        or full_name.casefold() != slug.casefold()
    ):
        return _unknown_remote_facts(
            "GitHub returned incomplete repository metadata", "github"
        )
    repository_id = payload.get("id")
    facts: dict[str, Fact] = {
        "identity": known(
            {
                "id": repository_id if type(repository_id) is int else None,
                "owner": owner["login"],
                "owner_type": str(owner["type"]).lower(),
                "repository": full_name,
            },
            "github",
        ),
        "plan": unknown("not observed yet", "github"),
    }
    visibility = payload.get("visibility")
    facts["visibility"] = (
        known(visibility, "github")
        if visibility in VISIBILITIES
        else unknown("GitHub reported no repository visibility", "github")
    )
    branch = payload.get("default_branch")
    facts["default_branch"] = (
        known(branch, "github")
        if isinstance(branch, str) and branch
        else unknown("GitHub reported no default branch", "github")
    )
    # Maintainer checks use role_name only (#1058 decision 6).
    role = payload.get("role_name")
    facts["permissions"] = (
        known(role, "github")
        if isinstance(role, str) and role
        else unknown("GitHub reported no role_name for this caller", "github")
    )
    analysis = payload.get("security_and_analysis")
    features = {
        name: str(entry["status"])
        for name in SECURITY_FEATURES
        if isinstance(analysis, dict)
        and isinstance(entry := analysis.get(name), dict)
        and isinstance(entry.get("status"), str)
    }
    facts["security"] = (
        known(features, "github")
        if features
        else unknown(
            "security_and_analysis needs admin access to observe", "github"
        )
    )
    return facts


def observe_plan(identity: Mapping[str, object], api: Runner) -> Fact:
    """Return the owner's GitHub plan when this caller may read it."""
    owner = str(identity.get("owner", ""))
    if identity.get("owner_type") == "organization":
        endpoint, reason = (
            f"orgs/{owner}",
            "the organization plan is visible only to its owners",
        )
    else:
        endpoint, reason = (
            "user",
            "a personal plan is visible only to that account",
        )
    code, output, _error = api([endpoint])
    try:
        payload = json.loads(output) if code == 0 else None
    except json.JSONDecodeError:
        payload = None
    plan = payload.get("plan") if isinstance(payload, dict) else None
    login = payload.get("login") if isinstance(payload, dict) else None
    name = plan.get("name") if isinstance(plan, dict) else None
    if (
        isinstance(name, str)
        and name
        and isinstance(login, str)
        and login.casefold() == owner.casefold()
    ):
        return known(name, "github")
    return unknown(reason, "github")


def detect(
    root: Path,
    *,
    git: Runner | None = None,
    api: Runner | None = None,
    env: Mapping[str, str] | None = None,
    offline: bool = False,
) -> dict[str, object]:
    """Return every live repository fact in the shared contract shape."""
    origin = observe_origin(root, git or git_runner(root), env)
    facts: dict[str, Fact] = {"origin": origin}
    slug = (
        github_slug(str(origin["value"])) if origin["state"] == KNOWN else None
    )
    if slug is None:
        facts.update(
            _unknown_remote_facts("the repository identity is unknown")
        )
    elif offline:
        facts.update(_unknown_remote_facts("offline: GitHub was not queried"))
    else:
        reader = api or api_runner()
        facts.update(observe_repository(slug, reader))
        identity = facts["identity"]
        if identity["state"] == KNOWN and isinstance(identity["value"], dict):
            facts["plan"] = observe_plan(identity["value"], reader)
        else:
            facts["plan"] = unknown(str(identity["reason"]), "github")
    return {"contract": CONTRACT, "facts": {k: facts[k] for k in LIVE_FACTS}}


def _python_project_name(root: Path) -> tuple[str | None, str]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return None, "pyproject.toml is missing"
    # One exception type per clause keeps the py312 and py314 formatters of
    # the byte-identical copies in agreement.
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, "pyproject.toml is not readable"
    try:
        project = tomllib.loads(text).get("project", {})
    except ValueError:
        return None, "pyproject.toml is not readable TOML"
    name = project.get("name") if isinstance(project, dict) else None
    if not isinstance(name, str):
        return None, "pyproject.toml has no [project] name"
    package = re.sub(r"[-.]+", "_", name.strip().lower())
    if PACKAGE_NAME.fullmatch(package) is None:
        return None, "pyproject.toml [project] name is not a package name"
    return package, ""


def derive_package_name(root: Path) -> Fact:
    """Return the Python import package the native sources resolve.

    One package under ``src/`` resolves it. Several packages resolve only
    when the ``pyproject.toml`` project name selects one of them; otherwise
    they are ambiguous. Without a ``src/`` package, the project name does.
    """
    source = root / "src"
    packages = (
        sorted(
            path.name
            for path in source.iterdir()
            if path.is_dir()
            and (path / "__init__.py").is_file()
            and PACKAGE_NAME.fullmatch(path.name)
        )
        if source.is_dir()
        else []
    )
    name, reason = _python_project_name(root)
    if len(packages) == 1:
        return known(packages[0], "src")
    if packages:
        if name in packages:
            return known(name, "pyproject.toml")
        return fact(
            AMBIGUOUS,
            source="src",
            reason="several src packages and no project name selects one",
            candidates=packages,
        )
    if name is not None:
        return known(name, "pyproject.toml")
    return unknown(reason or "no Python package was found", "pyproject.toml")


def derive_run_command(
    root: Path, languages: Sequence[str], package: Fact
) -> Fact:
    """Return the product run command the native manifests resolve.

    The command composes the template's per-language command, in template
    order, and resolves only when every selected language has its native
    manifest; a Python package that is ambiguous leaves it ambiguous.
    Without a language there is no native manifest to read, so the command
    is unknown rather than the CSARC verifier (#1165).
    """
    if not languages:
        return unknown(
            "no native manifest declares a product command", "languages"
        )
    selected = [item for item in LANGUAGE_MANIFESTS if item[0] in languages]
    for language, manifest in selected:
        if not (root / manifest).is_file():
            return unknown(f"{manifest} is missing for {language}", manifest)
    if "python" in languages and package["state"] == UNKNOWN:
        return unknown(str(package["reason"]), "pyproject.toml")

    def compose(name: object) -> str:
        return " && ".join(
            f"uv run python -c 'import {name}'"
            if language == "python"
            else LANGUAGE_COMMANDS[language]
            for language, _manifest in selected
        )

    if "python" in languages and package["state"] == AMBIGUOUS:
        raw = package.get("candidates")
        names = [str(item) for item in raw] if isinstance(raw, list) else []
        return fact(
            AMBIGUOUS,
            source="pyproject.toml",
            reason="the Python package is ambiguous",
            candidates=[compose(name) for name in names],
        )
    return known(compose(package["value"]), "manifests")


def derive_context(
    root: Path,
    languages: Sequence[str],
    decisions: Mapping[str, object] | None = None,
) -> dict[str, Fact]:
    """Return derived context; a saved or explicit decision always wins."""
    chosen = {} if decisions is None else decisions
    package_decision = chosen.get("package_name")
    package = (
        known(package_decision, "decision")
        if isinstance(package_decision, str)
        else derive_package_name(root)
    )
    command_decision = chosen.get("project_run_command")
    command = (
        known(command_decision, "decision")
        if isinstance(command_decision, str)
        else derive_run_command(root, languages, package)
    )
    # The package comes first: an ambiguous package is the root cause of
    # an ambiguous run command, so it is the decision to ask for first.
    context: dict[str, Fact] = {}
    if "python" in languages:
        context["package_name"] = package
    context["project_run_command"] = command
    return context


def main(argv: Sequence[str] | None = None) -> int:
    """Print the repository facts of one directory as JSON."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", type=Path, default=Path())
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Read only local Git state; GitHub facts are reported unknown.",
    )
    args = parser.parse_args(argv)
    root = args.path.resolve()
    payload = detect(root, offline=args.offline)
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
