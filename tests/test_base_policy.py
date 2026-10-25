"""Contract tests for the base-commit merge and verification policy (#1069).

The same `trusted_executor.py` ships in this repository (`scripts/`) and in
generated projects (`.csarc/scripts/`), so every contract runs against both
copies. The cases cover a normal pull request, a malicious candidate that
rewrites its own gate, an unknown configuration schema, and the
governance-switch route, for the hosted PR policy reader and the local
lifecycle alike.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COPIES = {
    "root": REPO_ROOT / "scripts" / "trusted_executor.py",
    "template": REPO_ROOT
    / "template"
    / ".csarc"
    / "scripts"
    / "trusted_executor.py",
}
GIT = shutil.which("git") or "git"
LOCAL_ESCALATION = (
    '{% if verification_mode != "hosted" -%}\n'
    '  if [[ -z "${CSARC_CI_TIER:-}" ]]'
)
MERGE_DOCSTRING = (
    '    """Merge only when the lease and exact-head controls are '
    'enforced."""\n'
)
REQUIRE_ROUTE = (
    "def require_route(decision: RouteDecision, labels: set[str]) -> None:\n"
)
ROUTE_SELECTION = (
    "    route = ROUTE_GOVERNANCE_SWITCH if reasons else ROUTE_ORDINARY\n"
)


@pytest.fixture(params=sorted(COPIES), name="executor")
def executor_fixture(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Load one shipped copy of the base-policy module."""
    return runpy.run_path(str(COPIES[request.param]))


def git(root: Path, *args: str) -> str:
    """Run one quiet git command in a fixture repository."""
    return subprocess.run(  # noqa: S603 - fixed git arguments in a temp repo
        [GIT, "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit_all(root: Path, message: str) -> str:
    """Commit every fixture change and return the commit SHA."""
    git(root, "add", "-A")
    git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        message,
    )
    return git(root, "rev-parse", "HEAD")


def config_text(**overrides: object) -> str:
    """Return a schema 2 configuration (SPEC-009) with overrides.

    An override of ``None`` removes the key.
    """
    values: dict[str, object] = {
        "schema_version": 2,
        "admin_bypass": "off",
        "code_owner": "",
        "container": False,
        "copilot_review": "off",
        "coverage_mode": "global",
        "coverage_threshold": 80,
        "documentation_languages": "zh-tw",
        "documentation_mode": "content-only",
        "enable_codeql": True,
        "governance_mode": "managed",
        "languages": ["python"],
        "lifecycle": ["issues", "milestones"],
        "project_maturity": "early",
        "github_project_url": "",
        "project_verification_hook": "",
        "python_floor": "latest",
        "release_ownership": "csarc-owned",
        "release_trigger": "main",
        "scheduled_checks": ["governance-drift"],
        "security_reporting_channel": "security@example.com",
        "verification_mode": "hosted",
    }
    values.update(overrides)
    lines: list[str] = []
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, list):
            lines.append(f"{key}:" if value else f"{key}: []")
            lines.extend(f"- {item}" for item in value)
        elif isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif value == "" or value == "off":
            lines.append(f"{key}: '{value}'")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def write_config(path: Path, text: str) -> Path:
    """Write one configuration fixture and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_both_shipped_copies_are_identical() -> None:
    """Root and generated projects evaluate exactly the same policy."""
    assert COPIES["root"].read_bytes() == COPIES["template"].read_bytes()


@pytest.mark.parametrize("python_floor", ["latest", "3.12"])
def test_generated_formatter_keeps_trusted_scripts_on_py312_grammar(
    tmp_path: Path, python_floor: str
) -> None:
    """A generated project's own `ruff format` keeps 3.12-parseable excepts.

    The product formatter never collects `.csarc/` (#1070), so it cannot
    rewrite trusted scripts to a newer grammar whatever its target is.
    """
    from jinja2 import Environment, StrictUndefined

    template = Environment(
        autoescape=False,  # noqa: S701 - trusted local TOML template
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    ).from_string(
        (REPO_ROOT / "template" / "pyproject.toml.jinja").read_text(
            encoding="utf-8"
        )
    )
    (tmp_path / "pyproject.toml").write_text(
        template.render(
            python_floor=python_floor,
            project_slug="gen-smoke",
            project_description="Generated smoke.",
            documentation_mode="content-only",
            project_license="MIT",
            repository_url="https://github.com/example/gen-smoke",
            package_name="gen_smoke",
        ),
        encoding="utf-8",
    )
    shutil.copytree(
        REPO_ROOT / "template" / ".csarc" / "scripts",
        tmp_path / ".csarc" / "scripts",
        ignore=shutil.ignore_patterns("*.jinja", "__pycache__"),
    )
    shutil.copy2(
        REPO_ROOT / "template" / ".csarc" / ".ignore.jinja",
        tmp_path / ".csarc" / ".ignore",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            ".",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_trusted_policy_parses_before_python_setup() -> None:
    """Hosted CI stages the policy with the runner's system Python."""
    for path in (*COPIES.values(), REPO_ROOT / "scripts" / "csarc_config.py"):
        ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 12))


def test_layout_selects_the_matching_control_set(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """The control set follows the repository layout it is staged from."""
    root = tmp_path / "root"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "verify-template.sh").write_text("", encoding="utf-8")
    generated = tmp_path / "generated"
    (generated / ".csarc" / "scripts").mkdir(parents=True)
    assert executor["scripts_prefix"](root) == "scripts"
    assert executor["scripts_prefix"](generated) == ".csarc/scripts"
    assert ".csarc/scripts/verify" in executor["control_paths"](generated)
    assert ".csarc/scripts/trusted_executor.py" in executor["control_paths"](
        generated
    )
    assert executor["is_control_path"](".csarc/scripts/ci_tier.py")
    assert executor["is_control_path"]("scripts/trusted_executor.py")


# Unknown or next schema


def test_current_schema_reads_without_writing(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """The reader is read-only and never normalizes (SPEC-009)."""
    path = write_config(tmp_path / "config.yml", config_text())
    before = path.read_bytes()
    values = executor["read_config"](path)
    assert values["schema_version"] == 2
    assert values["admin_bypass"] == "off"
    assert path.read_bytes() == before


def test_next_schema_is_read_strictly(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """Schema 2 is accepted only in its intent-only shape."""
    path = write_config(
        tmp_path / "config.yml",
        "_src_path: gh:owner/template\n" + config_text(),
    )
    before = path.read_bytes()
    assert executor["read_config"](path)["schema_version"] == 2
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"schema_version": 9}, "reads schema 2 only"),
        ({"schema_version": "two"}, "reads schema 2 only"),
        ({"schema_version": None}, "legacy settings schema"),
        ({"pr_review_mode": "human"}, "retired settings pr_review_mode"),
        ({"policy_labels": True}, "retired settings policy_labels"),
        ({"review": "solo"}, "retired settings review"),
        ({"_secret": "x"}, "retired settings _secret"),
    ],
)
def test_unknown_or_invalid_schema_fails_closed(
    executor: dict[str, Any],
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    """The trusted base never guesses at a schema it cannot read."""
    path = write_config(tmp_path / "config.yml", config_text(**overrides))
    with pytest.raises(ValueError, match=message):
        executor["read_config"](path)


def test_next_schema_requires_explicit_governance_values(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """Schema 2 never fills a governance value from a legacy default."""
    path = write_config(
        tmp_path / "config.yml", config_text(verification_mode=None)
    )
    with pytest.raises(
        ValueError, match="missing persistent settings verification_mode"
    ):
        executor["read_config"](path)


def test_root_schema_two_settings_pass_the_trusted_base_reader(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """The exact schema 2 root settings Q1 writes are readable here."""
    path = write_config(
        tmp_path / "config.yml",
        "schema_version: 2\n"
        "admin_bypass: always\n"
        "code_owner: '@Innoguard-Cyber-Arch/arch'\n"
        "container: false\n"
        "copilot_review: allowed\n"
        "coverage_mode: global\n"
        "coverage_threshold: 80\n"
        "documentation_languages: zh-tw+en\n"
        "documentation_mode: template-and-content\n"
        "enable_codeql: false\n"
        "governance_mode: managed\n"
        "languages:\n- python\n"
        "lifecycle:\n- issues\n- milestones\n"
        "package_name: csarc_cli\n"
        "project_maturity: early\n"
        "project_run_command: uv run csarc --help\n"
        "github_project_url: ''\n"
        "project_verification_hook: ''\n"
        "python_floor: latest\n"
        "release_ownership: csarc-owned\n"
        "release_trigger: manual\n"
        "scheduled_checks: []\n"
        "security_reporting_channel: security@example.com\n"
        "verification_mode: hosted\n",
    )
    values = executor["read_config"](path)
    # SPEC-011: the legacy key reads as the same mode for both visibilities.
    assert values["verification_mode_private"] == "hosted"
    assert values["verification_mode_public"] == "hosted"
    assert values["admin_bypass"] == "always"


# Governance switch


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"admin_bypass": "always"}, "admin_bypass: off -> always"),
        (
            {
                "verification_mode": None,
                "verification_mode_private": "hosted",
                "verification_mode_public": "local",
            },
            "verification_mode_public: hosted -> local",
        ),
        ({"governance_mode": "observe"}, "governance_mode: managed -> observe"),
        (
            {"scheduled_checks": []},
            "scheduled_checks: removes governance-drift",
        ),
        ({"copilot_review": "allowed"}, "copilot_review: off -> allowed"),
        ({"enable_codeql": False}, "enable_codeql: true -> False"),
        ({"lifecycle": ["issues"]}, "lifecycle: removes milestones"),
        ({"coverage_threshold": 60}, "coverage_threshold: 80 -> 60"),
    ],
)
def test_relaxed_governance_value_needs_the_switch(
    executor: dict[str, Any],
    tmp_path: Path,
    override: dict[str, object],
    reason: str,
) -> None:
    """Each relaxed governance value selects the governance-switch route."""
    base = executor["read_config"](
        write_config(tmp_path / "base.yml", config_text())
    )
    candidate = executor["read_config"](
        write_config(tmp_path / "candidate.yml", config_text(**override))
    )
    decision = executor["classify_route"]([], base, candidate)
    assert decision.route == "governance-switch"
    assert decision.reasons == (f"relaxes {reason}",)
    with pytest.raises(RuntimeError, match="'governance-switch' label"):
        executor["require_route"](decision, {"enhancement"})
    executor["require_route"](decision, {"enhancement", "governance-switch"})


def test_tightened_governance_stays_ordinary(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """Making governance stricter needs no special route."""
    base = executor["read_config"](
        write_config(tmp_path / "base.yml", config_text(admin_bypass="always"))
    )
    candidate = executor["read_config"](
        write_config(
            tmp_path / "candidate.yml", config_text(coverage_threshold=90)
        )
    )
    decision = executor["classify_route"](
        ["src/app.py", "scripts/helper.py"], base, candidate
    )
    assert decision.route == "ordinary"
    executor["require_route"](decision, set())


def test_generated_script_and_schema_changes_need_the_switch(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """`.csarc/scripts`, a schema change, or unknown paths are switches."""
    base = executor["read_config"](
        write_config(tmp_path / "base.yml", config_text())
    )
    # A later schema is readable only after a trusted base adds it; the
    # route still names the change.
    next_schema = {**base, "schema_version": 3}
    scripts = executor["classify_route"](
        [".csarc/scripts/verify-fast"], base, base
    )
    schema = executor["classify_route"]([], base, next_schema)
    unknown = executor["classify_route"](None, base, base)
    assert scripts.reasons == (
        "changes .csarc/scripts/: .csarc/scripts/verify-fast",
    )
    assert schema.reasons == ("changes schema_version: 2 -> 3",)
    assert unknown.reasons == ("changed paths are unavailable",)


def test_route_cli_enforces_the_label_and_caps_pull_files(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """The hosted PR policy entry point fails closed on every gap."""
    script = COPIES["root"]
    base = write_config(tmp_path / "base.yml", config_text())
    candidate = write_config(tmp_path / "candidate.yml", config_text())
    files = tmp_path / "files.json"

    def route(*extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - repository-owned entry point
            [
                sys.executable,
                str(script),
                "route",
                "--base-config",
                str(base),
                "--candidate-config",
                str(candidate),
                "--pull-files",
                str(files),
                "--enforce",
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    files.write_text(json.dumps([[{"filename": "src/app.py"}]]), "utf-8")
    assert route().returncode == 0
    files.write_text(
        json.dumps(
            [[{"filename": f"src/{index}.py"} for index in range(3000)]]
        ),
        "utf-8",
    )
    capped = route()
    assert capped.returncode == 1
    assert "changed paths are unavailable" in capped.stderr
    assert route("--labels", "governance-switch").returncode == 0
    del executor


# Release channel floor


@pytest.mark.parametrize(
    ("base", "labels", "path_tier", "expected"),
    [
        ("dev/m18-downstream-upgrade-readiness", set(), "fast", "fast"),
        ("dev/m18-downstream-upgrade-readiness", set(), "full", "full"),
        ("dev/i42-canary", set(), "docs", "fast"),
        ("main", set(), "fast", "full"),
        ("main", {"hotfix"}, "fast", "full"),
        ("main", {"release-recovery"}, "fast", "full"),
        ("dev/m18-downstream-upgrade-readiness", {"hotfix"}, "fast", "full"),
    ],
)
def test_channel_floor_takes_the_stronger_suite(
    executor: dict[str, Any],
    base: str,
    labels: set[str],
    path_tier: str,
    expected: str,
) -> None:
    """Standalone, hotfix, and recovery routes always require full."""
    _level, floor = executor["channel_floor"](base, labels)
    assert executor["stronger_suite"](floor, path_tier) == expected


def test_local_verify_fast_escalates_only_in_local_mode() -> None:
    """Root and generated verify-fast both apply the channel floor."""
    root = (REPO_ROOT / "scripts" / "verify-fast").read_text(encoding="utf-8")
    template = (
        REPO_ROOT / "template" / ".csarc" / "scripts" / "verify-fast.jinja"
    ).read_text(encoding="utf-8")
    for source in (root, template):
        assert "trusted_executor.py" in source and "channel-floor" in source
        assert (
            'if [[ "$channel_floor" == "full" && "$suite" != "full" ]]'
            in source
        )
    assert LOCAL_ESCALATION in template


# Local lifecycle: trusted base re-execution


def lifecycle_repository(tmp_path: Path) -> tuple[Path, str, str]:
    """Build a repository whose candidate tampers with its own gate."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    shutil.copytree(REPO_ROOT / "scripts", repo / "scripts")
    shutil.copytree(REPO_ROOT / ".csarc", repo / ".csarc")
    base_sha = commit_all(repo, "base")
    git(repo, "switch", "-q", "-c", "fix/1069-tamper")
    lifecycle = repo / "scripts" / "pr_lifecycle.py"
    source = lifecycle.read_text(encoding="utf-8")
    lifecycle.write_text(
        source.replace(
            MERGE_DOCSTRING,
            MERGE_DOCSTRING + '    print("CANDIDATE-MERGE-GATE")\n',
            1,
        ),
        encoding="utf-8",
    )
    executor = repo / "scripts" / "trusted_executor.py"
    executor.write_text(
        executor.read_text(encoding="utf-8").replace(
            REQUIRE_ROUTE,
            REQUIRE_ROUTE + "    return None\n",
            1,
        ),
        encoding="utf-8",
    )
    head_sha = commit_all(repo, "candidate tampers with its gate")
    return repo, base_sha, head_sha


def lease_file(path: Path, base_sha: str, head_sha: str, tree: str) -> Path:
    """Write one structurally valid lease for the fixture repository."""
    lifecycle = runpy.run_path(str(REPO_ROOT / "scripts" / "pr_lifecycle.py"))
    capability = "f" * 64
    payload = {
        "schema_version": 2,
        "repository": "owner/repo",
        "pull_request": 42,
        "head_sha": head_sha,
        "head_tree": tree,
        "base_ref": "main",
        "base_sha": base_sha,
        "default_branch": "main",
        "owner": "task/merge",
        "actor": "agent",
        "capability": capability,
        "capability_digest": hashlib.sha256(capability.encode()).hexdigest(),
        "acquired_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "expires_at": (datetime.now(UTC) + timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z"),
        "lease_commit": "c" * 40,
        "refs": [
            "refs/heads/csarc/leases/pr-42",
            lifecycle["base_lane_ref"]("main"),
        ],
        "reclaimed_commits": [],
        "audit_url": "https://github.com/owner/repo/pull/42#issuecomment-1",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_local_merge_runs_the_trusted_base_not_the_candidate_gate(
    tmp_path: Path,
) -> None:
    """A malicious candidate cannot decide its own merge locally."""
    repo, base_sha, head_sha = lifecycle_repository(tmp_path)
    lease = lease_file(
        tmp_path / "lease.json",
        base_sha,
        head_sha,
        git(repo, "rev-parse", "HEAD^{tree}"),
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "gh").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (fake_bin / "gh").chmod(0o755)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "CSARC_TRUSTED_BASE_SHA"
    }
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    result = subprocess.run(  # noqa: S603 - fixture lifecycle entry point
        [
            sys.executable,
            str(repo / "scripts" / "pr_lifecycle.py"),
            "merge",
            "--repo",
            "owner/repo",
            "--pr-number",
            "42",
            "--lease",
            str(lease),
            "--owner",
            "task/merge",
            "--head-sha",
            head_sha,
        ],
        cwd=repo,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert f"runs from trusted base {base_sha}" in result.stdout
    assert "CANDIDATE-MERGE-GATE" not in result.stdout
    assert result.returncode == 1
    assert "ERROR: " in result.stderr
    worktrees = git(repo, "worktree", "list", "--porcelain")
    assert worktrees.count("worktree ") == 1


def generated_repository(
    tmp_path: Path, *, candidate: str
) -> tuple[Path, str, str]:
    """Build a generated-layout repository with one candidate change."""
    repo = tmp_path / "generated"
    scripts = repo / ".csarc" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("trusted_executor.py", "csarc_config.py"):
        shutil.copy2(
            REPO_ROOT / "template/.csarc/scripts" / name, scripts / name
        )
    (scripts / "verify-fast").write_text("#!/bin/sh\nexit 0\n", "utf-8")
    write_config(repo / ".csarc" / "config.yml", config_text())
    git(repo, "init", "-q", "-b", "main")
    base_sha = commit_all(repo, "base")
    git(repo, "switch", "-q", "-c", "fix/1069-candidate")
    if candidate == "scripts":
        (scripts / "verify-fast").write_text(
            "#!/bin/sh\nexit 0 # ok\n", "utf-8"
        )
    elif candidate == "relax":
        write_config(
            repo / ".csarc" / "config.yml", config_text(admin_bypass="always")
        )
    elif candidate == "schema":
        write_config(
            repo / ".csarc" / "config.yml", config_text(schema_version=9)
        )
    else:
        (repo / "README.md").write_text("normal change\n", "utf-8")
    head_sha = commit_all(repo, f"candidate {candidate}")
    return repo, base_sha, head_sha


@pytest.fixture(name="lifecycle_module")
def lifecycle_module_fixture() -> dict[str, Any]:
    """Load the root lifecycle so its base-policy hook can be exercised."""
    return runpy.run_path(str(REPO_ROOT / "scripts" / "pr_lifecycle.py"))


@pytest.mark.parametrize(
    ("candidate", "labels", "route", "error"),
    [
        ("normal", set(), "ordinary", None),
        ("scripts", set(), None, "'governance-switch' label"),
        ("scripts", {"governance-switch"}, "governance-switch", None),
        ("relax", set(), None, "relaxes admin_bypass"),
        ("relax", {"governance-switch"}, "governance-switch", None),
        ("schema", {"governance-switch"}, None, "reads schema 2 only"),
    ],
)
def test_local_lifecycle_routes_from_the_trusted_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lifecycle_module: dict[str, Any],
    candidate: str,
    labels: set[str],
    route: str | None,
    error: str | None,
) -> None:
    """The local merge snapshot applies the base route to the exact head."""
    repo, base_sha, head_sha = generated_repository(
        tmp_path, candidate=candidate
    )
    trusted = tmp_path / "trusted"
    shutil.copytree(repo / ".csarc", trusted / ".csarc")
    git(repo, "show", f"{base_sha}:.csarc/config.yml")
    (trusted / ".csarc" / "config.yml").write_text(
        git(repo, "show", f"{base_sha}:.csarc/config.yml") + "\n", "utf-8"
    )
    decide = lifecycle_module["base_policy_decision"]
    monkeypatch.setitem(decide.__globals__, "repository_root", lambda: trusted)
    monkeypatch.chdir(repo)
    lease = {"base_sha": base_sha, "head_sha": head_sha, "base_ref": "main"}
    pull = {"head": {"ref": "fix/1069-candidate"}}
    if error is not None:
        with pytest.raises(RuntimeError, match=error):
            decide(lease, pull, labels)
        return
    decision = decide(lease, pull, labels)
    assert decision["route"] == route
    assert decision["path_tier"] in {"fast", "full"}
    assert decision["self_test"][0].startswith(
        "Candidate policy self-test (non-authoritative)"
    )


def test_candidate_self_test_reports_but_never_decides(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """A candidate policy that disagrees is reported as a difference only."""
    repo, base_sha, _head_sha = generated_repository(
        tmp_path, candidate="scripts"
    )
    tampered = repo / ".csarc" / "scripts" / "trusted_executor.py"
    tampered.write_text(
        tampered.read_text(encoding="utf-8").replace(
            ROUTE_SELECTION,
            "    route = ROUTE_ORDINARY\n",
            1,
        ),
        encoding="utf-8",
    )
    base_config = write_config(tmp_path / "base.yml", config_text())
    changed = tmp_path / "changed"
    changed.write_bytes(b".csarc/scripts/verify-fast\0")
    trusted = executor["classify_route"](
        [".csarc/scripts/verify-fast"],
        executor["read_config"](base_config),
        executor["read_config"](base_config),
    )
    lines = executor["policy_self_test"](
        repo,
        base_config=base_config,
        candidate_config=base_config,
        changed_files=changed,
        labels="",
        trusted=trusted,
    )
    assert trusted.route == "governance-switch"
    assert lines[0].startswith("Candidate policy self-test (non-authoritative)")
    assert lines[1].startswith("Route difference:")
    del base_sha


def test_trusted_base_checkout_ignores_candidate_worktree_edits(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """The trusted copy comes from the base commit, not the working tree."""
    repo, base_sha, _head_sha = generated_repository(
        tmp_path, candidate="normal"
    )
    (repo / ".csarc" / "config.yml").write_text(
        "admin_bypass: always\n", "utf-8"
    )
    with executor["trusted_base_checkout"](repo, base_sha) as base:
        assert (base / ".csarc" / "config.yml").read_text(
            encoding="utf-8"
        ) == config_text()
        assert git(base, "rev-parse", "HEAD") == base_sha
    assert git(repo, "worktree", "list", "--porcelain").count("worktree ") == 1
    with (
        pytest.raises(RuntimeError, match="malformed"),
        executor["trusted_base_checkout"](repo, "not-a-sha"),
    ):
        pass


# Hosted workflow contract (root and generated)

WORKFLOWS = {
    "root": (REPO_ROOT / ".github/workflows/ci.yml", "scripts"),
    "template": (
        REPO_ROOT / "template/.github/workflows/ci.yml.jinja",
        ".csarc/scripts",
    ),
}


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_hosted_workflow_runs_the_trusted_base_executor(name: str) -> None:
    """Root and generated CI stage the gate from the base before checkout."""
    path, scripts = WORKFLOWS[name]
    source = path.read_text(encoding="utf-8")
    prepare = source.index(f"python3 {scripts}/trusted_executor.py prepare")
    candidate = source.index("- name: Check out the exact candidate")
    assert prepare < candidate
    assert "executor=trusted-base" in source
    assert 'verify --destination "$entry_root"' in source
    assert 'export CSARC_VERIFICATION_SUBJECT_ROOT="$GITHUB_WORKSPACE"' in (
        source
    )
    assert f'"$entry_root/{scripts}/verify-fast"' in source
    self_test = source.index(
        "- name: Candidate gate self-test (non-authoritative)"
    )
    assert source.index("- name: Execute trusted verification") < self_test
    assert "continue-on-error: true" in source[self_test : self_test + 800]
    assert 'ownership="$(python3' in source


def test_template_workflow_no_longer_declares_root_only_executor() -> None:
    """The drift check compares the ported executor line by line."""
    drift = runpy.run_path(
        str(REPO_ROOT / "scripts" / "check_jinja_workflow_drift.py")
    )
    assert drift["ROOT_ONLY_BLOCKS"] == {}


def test_generated_entry_points_run_against_the_subject_root() -> None:
    """Generated verify entry points keep control and subject trees apart."""
    for name in ("verify-fast.jinja", "verify.jinja"):
        source = (REPO_ROOT / "template/.csarc/scripts" / name).read_text(
            encoding="utf-8"
        )
        assert 'repo_root="$(verification_subject_root "$control_root")"' in (
            source
        )
        assert "unset CSARC_VERIFICATION_SUBJECT_ROOT" in source


def test_generated_prepare_ignores_a_tampered_candidate_gate(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """A malicious generated candidate cannot replace the staged gate."""
    base = tmp_path / "base"
    scripts = base / ".csarc" / "scripts"
    scripts.mkdir(parents=True)
    for relative in executor["GENERATED_CONTROL_FILES"]:
        (base / relative).write_text(f"trusted {relative}\n", "utf-8")
    staged = tmp_path / "staged"
    files = executor["prepare"](base, staged)
    assert sorted(files) == sorted(executor["GENERATED_CONTROL_FILES"])
    (scripts / "verify-fast").write_text("exit 0  # tampered\n", "utf-8")
    executor["verify_manifest"](staged)
    assert (staged / ".csarc/scripts/verify-fast").read_text(
        encoding="utf-8"
    ) == "trusted .csarc/scripts/verify-fast\n"
