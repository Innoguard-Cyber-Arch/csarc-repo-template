"""Regression tests for the trusted-base hosted verifier (#1086)."""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import settings_support
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = runpy.run_path(str(REPO_ROOT / "scripts" / "trusted_executor.py"))
prepare = EXECUTOR["prepare"]
verify_manifest = EXECUTOR["verify_manifest"]
self_test_report = EXECUTOR["self_test_report"]
is_control_path = EXECUTOR["is_control_path"]
control_main = EXECUTOR["main"]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

SUBJECT_CHECKS = (
    "check-update-conflicts",
    "scan-secrets",
    "check-message-style",
    "check-bypass-lifecycle",
    "build-repo-site",
    "build-handbook",
    "sync-paired-files.sh",
    "lint-workflows-shell",
    "test-static-validation",
)


def git(root: Path, *args: str) -> None:
    """Run one quiet git command in a fixture repository."""
    subprocess.run(  # noqa: S603 - fixed git arguments in a temp repository
        ["git", "-C", str(root), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )


def write_script(path: Path, body: str) -> None:
    """Write one executable fixture script."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def recording_check(name: str, *, status: int = 0) -> str:
    """Return a stub check that logs its name and inherited subject override."""
    return (
        "#!/usr/bin/env bash\n"
        f'printf "%s subject=%s\\n" "{name}" '
        '"${CSARC_VERIFICATION_SUBJECT_ROOT-unset}" >>"$CHECK_LOG"\n'
        f"exit {status}\n"
    )


def candidate_repository(
    root: Path, *, tamper_gate: bool, failing_check: str | None
) -> Path:
    """Build a candidate tree whose subject checks are logging stubs."""
    candidate = root / "candidate"
    candidate.mkdir()
    git(candidate, "init", "-q", "-b", "main")
    git(candidate, "config", "user.email", "fixture@example.invalid")
    git(candidate, "config", "user.name", "Fixture")
    for name in SUBJECT_CHECKS:
        status = 1 if name == failing_check else 0
        write_script(
            candidate / "scripts" / name, recording_check(name, status=status)
        )
    write_script(
        candidate / "scripts" / "spec_to_issue.py",
        "import os, sys\n"
        "with open(os.environ['CHECK_LOG'], 'a') as log:\n"
        "    log.write('spec_to_issue.py subject='\n"
        "              + os.environ.get('CSARC_VERIFICATION_SUBJECT_ROOT',"
        " 'unset') + '\\n')\n"
        "sys.exit(0)\n",
    )
    git(candidate, "add", "-A")
    git(candidate, "commit", "-q", "-m", "base")
    git(candidate, "checkout", "-q", "-b", "feature")
    (candidate / "docs").mkdir()
    (candidate / "docs" / "change.md").write_text("change\n", encoding="utf-8")
    if tamper_gate:
        # A malicious candidate rewrites every control file to pass itself.
        for name in (
            "verify-fast",
            "verify-template.sh",
            "verify-stage-static-assets",
        ):
            write_script(
                candidate / "scripts" / name, "#!/usr/bin/env bash\nexit 0\n"
            )
        (candidate / "scripts" / "ci_tier.py").write_text(
            "import json, sys\n"
            "out = sys.argv[sys.argv.index('--output-json') + 1]\n"
            "json.dump({'tier': 'fast', 'scopes': [], 'run_project': False},"
            " open(out, 'w'))\n",
            encoding="utf-8",
        )
    git(candidate, "add", "-A")
    git(candidate, "commit", "-q", "-m", "candidate")
    return candidate


def run_entry(
    entry: Path, candidate: Path, tmp_path: Path, *, subject: bool = True
) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run one entry point against the candidate and return its check log."""
    log = tmp_path / "checks.log"
    log.write_text("", encoding="utf-8")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CSARC_", "GIT_"))
    }
    env.update(
        {
            "CHECK_LOG": str(log),
            "CSARC_CACHE_ROOT": str(tmp_path / "cache"),
            "CSARC_CI_BASE": "main",
        }
    )
    if subject:
        env["CSARC_VERIFICATION_SUBJECT_ROOT"] = str(candidate)
    result = subprocess.run(  # noqa: S603 - fixture entry point
        [str(entry)],
        cwd=candidate if not subject else tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, log.read_text(encoding="utf-8")


@pytest.fixture
def executor(tmp_path: Path) -> Path:
    """Stage this repository's control set as the trusted base."""
    destination = tmp_path / "trusted-executor"
    prepare(REPO_ROOT, destination)
    return destination


def test_prepare_stages_only_the_read_only_control_set(executor: Path) -> None:
    """The staged executor is exactly the digested control set."""
    manifest = json.loads(
        (executor / "trusted-executor.json").read_text(encoding="utf-8")
    )
    files = manifest["files"]
    assert manifest["executor"] == "trusted-base"
    assert {
        "scripts/verify-fast",
        "scripts/verify-template.sh",
        "scripts/verification-step",
        "scripts/ci_tier.py",
        "scripts/csarc_config.py",
        "scripts/resolve-cache-root",
        "scripts/verify-stage-regression-tests",
    } <= set(files)
    assert all(is_control_path(path) for path in files)
    staged = {
        path.relative_to(executor).as_posix()
        for path in executor.rglob("*")
        if path.is_file()
    }
    assert staged == {*files, "trusted-executor.json"}
    for relative in files:
        mode = (executor / relative).stat().st_mode
        assert not mode & 0o222, relative
    verify_manifest(executor)


def test_prepare_fails_closed_without_a_complete_control_set(
    tmp_path: Path,
) -> None:
    """A base missing one control file never yields a partial executor."""
    source = tmp_path / "base"
    (source / "scripts").mkdir(parents=True)
    (source / "scripts" / "verify-fast").write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing or not a regular file"):
        prepare(source, tmp_path / "executor")
    assert not (tmp_path / "executor").exists()


def test_prepare_rejects_symlinked_control_files(tmp_path: Path) -> None:
    """A control file may not point outside the trusted checkout."""
    source = tmp_path / "base"
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    for relative in EXECUTOR["CONTROL_FILES"]:
        (source / relative).write_text("", encoding="utf-8")
    (scripts / "ci_tier.py").unlink()
    (scripts / "ci_tier.py").symlink_to(tmp_path / "elsewhere.py")

    with pytest.raises(RuntimeError, match=r"ci_tier\.py"):
        prepare(source, tmp_path / "executor")


def test_staged_control_set_detects_later_writes(executor: Path) -> None:
    """A changed staged file fails the pre-execution digest check."""
    target = executor / "scripts" / "verify-fast"
    target.chmod(0o755)
    target.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="scripts/verify-fast"):
        verify_manifest(executor)
    assert control_main(["verify", "--destination", str(executor)]) == 1


def test_tampered_candidate_gate_cannot_decide_the_result(
    tmp_path: Path, executor: Path
) -> None:
    """The trusted router and entry point still run the candidate's checks."""
    candidate = candidate_repository(
        tmp_path, tamper_gate=True, failing_check="build-repo-site"
    )

    own, own_log = run_entry(
        candidate / "scripts" / "verify-fast",
        candidate,
        tmp_path,
        subject=False,
    )
    assert own.returncode == 0
    assert own_log == ""

    trusted, log = run_entry(
        executor / "scripts" / "verify-fast", candidate, tmp_path
    )
    assert trusted.returncode != 0, trusted.stdout + trusted.stderr
    # The trusted router sees the rewritten control files and escalates to
    # the trusted full gate, which runs the candidate's own checks.
    assert "suite=full" in trusted.stdout
    assert "[verify-template] START Repository contracts" in trusted.stdout
    assert "check-update-conflicts subject=unset" in log
    assert "scan-secrets subject=unset" in log
    assert "check-message-style subject=unset" in log


def test_failing_message_pattern_check_fails_the_fast_gate(
    tmp_path: Path, executor: Path
) -> None:
    """A nonconforming changed message fails the required verify (#1219)."""
    candidate = candidate_repository(
        tmp_path, tamper_gate=False, failing_check="check-message-style"
    )

    result, log = run_entry(
        executor / "scripts" / "verify-fast", candidate, tmp_path
    )

    assert result.returncode != 0
    assert "check-message-style subject=unset" in log


def test_tampered_candidate_stage_cannot_skip_its_checks(
    tmp_path: Path, executor: Path
) -> None:
    """A trusted stage gate runs the candidate checks it lists."""
    candidate = candidate_repository(
        tmp_path, tamper_gate=True, failing_check="lint-workflows-shell"
    )

    trusted, log = run_entry(
        executor / "scripts" / "verify-stage-static-assets",
        candidate,
        tmp_path,
    )

    assert trusted.returncode != 0
    assert "build-repo-site subject=unset" in log
    assert "lint-workflows-shell subject=unset" in log


def test_normal_candidate_passes_through_the_trusted_executor(
    tmp_path: Path, executor: Path
) -> None:
    """An ordinary candidate runs every routed check and passes."""
    candidate = candidate_repository(
        tmp_path, tamper_gate=False, failing_check=None
    )

    result, log = run_entry(
        executor / "scripts" / "verify-fast", candidate, tmp_path
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for name in (
        "check-update-conflicts",
        "scan-secrets",
        "check-message-style",
        "check-bypass-lifecycle",
        "spec_to_issue.py",
        "build-repo-site",
        "build-handbook",
        "sync-paired-files.sh",
    ):
        # Nested checks never inherit the subject override.
        assert f"{name} subject=unset" in log


def test_relative_subject_root_fails_closed(
    tmp_path: Path, executor: Path
) -> None:
    """An ambiguous subject path never falls back to the control tree."""
    env = {**os.environ, "CSARC_VERIFICATION_SUBJECT_ROOT": "relative/path"}
    result = subprocess.run(  # noqa: S603 - fixture entry point
        [str(executor / "scripts" / "verify-fast")],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "must be an existing absolute directory" in result.stderr


def test_self_test_labels_differences_and_never_fails(tmp_path: Path) -> None:
    """Candidate gate output is reported, never authoritative."""
    trusted = {"tier": "full", "scopes": ["workflow"], "run_project": True}
    candidate = {"tier": "fast", "scopes": [], "run_project": False}

    lines = self_test_report(
        trusted_plan=trusted,
        candidate_plan=candidate,
        trusted_ownership="csarc-owned",
        candidate_ownership="unavailable",
        changed_files=["scripts/ci_tier.py", "README.md"],
    )

    assert lines[0].startswith("Candidate gate self-test (non-authoritative)")
    assert any("scripts/ci_tier.py" in line for line in lines)
    assert not any("README.md" in line for line in lines)
    assert "Router difference tier: trusted='full' candidate='fast'" in lines
    assert any("release_ownership" in line for line in lines)


def self_test_cli(
    tmp_path: Path, candidate: Path, router_args: bytes
) -> tuple[int, str]:
    """Run the self-test command and return its status and summary."""
    trusted_path = tmp_path / "trusted.json"
    trusted_path.write_text(
        json.dumps({"tier": "full", "scopes": ["shell"], "run_project": True}),
        encoding="utf-8",
    )
    args_path = tmp_path / "router-args"
    args_path.write_bytes(router_args)
    summary = tmp_path / "summary.md"
    status = control_main(
        [
            "self-test",
            "--candidate-root",
            str(candidate),
            "--router-args",
            str(args_path),
            "--trusted-plan",
            str(trusted_path),
            "--trusted-ownership",
            "csarc-owned",
            "--summary",
            str(summary),
        ]
    )
    return status, summary.read_text(encoding="utf-8")


def test_self_test_replays_the_candidate_gate_without_file_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Candidate gate code runs with the trusted arguments but no authority."""
    candidate = tmp_path / "candidate"
    (candidate / "scripts").mkdir(parents=True)
    seen = tmp_path / "seen.json"
    (candidate / "scripts" / "ci_tier.py").write_text(
        "import json, os, sys\n"
        f"json.dump({{'argv': sys.argv[1:], 'env': sorted(os.environ)}},"
        f" open({str(seen)!r}, 'w'))\n"
        "out = sys.argv[sys.argv.index('--output-json') + 1]\n"
        "json.dump({'tier': 'fast', 'scopes': [], 'run_project': False},"
        " open(out, 'w'))\n",
        encoding="utf-8",
    )
    (candidate / "scripts" / "csarc_config.py").write_text(
        "print('product-owned')\n", encoding="utf-8"
    )
    for name in ("GITHUB_ENV", "GITHUB_PATH", "GITHUB_OUTPUT", "GH_TOKEN"):
        monkeypatch.setenv(name, str(tmp_path / name))

    status, text = self_test_cli(
        tmp_path, candidate, b"--event\0pull_request\0--labels\0\0"
    )

    assert status == 0
    assert "Router difference tier: trusted='full' candidate='fast'" in text
    assert "trusted='csarc-owned' candidate='product-owned'" in text
    replay = json.loads(seen.read_text(encoding="utf-8"))
    assert replay["argv"][:4] == ["--event", "pull_request", "--labels", ""]
    assert not {"GITHUB_ENV", "GITHUB_PATH", "GITHUB_OUTPUT", "GH_TOKEN"} & set(
        replay["env"]
    )


def test_self_test_survives_a_broken_candidate_gate(tmp_path: Path) -> None:
    """A crashing or missing candidate gate is reported, never fatal."""
    candidate = tmp_path / "candidate"
    (candidate / "scripts").mkdir(parents=True)
    (candidate / "scripts" / "ci_tier.py").write_text(
        "raise SystemExit(3)\n", encoding="utf-8"
    )

    status, text = self_test_cli(tmp_path, candidate, b"--event\0push\0")

    assert status == 0
    assert "Candidate gate self-test (non-authoritative)" in text
    assert "Candidate router produced no readable plan." in text
    assert "candidate='unavailable'" in text

    status, text = self_test_cli(tmp_path, candidate, b"unterminated")
    assert status == 0
    assert "Candidate router produced no readable plan." in text


def test_unknown_candidate_configuration_fails_the_trusted_reader(
    tmp_path: Path,
) -> None:
    """The trusted config reader fails closed on values it does not know."""
    config = tmp_path / ".csarc" / "config.yml"
    config.parent.mkdir()
    config.write_text(
        settings_support.settings_text(release_ownership="future-owned"),
        encoding="utf-8",
    )

    result = subprocess.run(  # noqa: S603 - repository config reader
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "csarc_config.py"),
            "release_ownership",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "release_ownership" in result.stderr
    step = workflow_steps()["Read release ownership"]
    # A command substitution inside `echo` would swallow that failure.
    assert 'echo "ownership=$(' not in step["run"]
    assert (
        'ownership="$(python3 "$RUNNER_TEMP/trusted-verification/'
        in (step["run"])
    )


def workflow() -> dict[Any, Any]:
    """Load the root hosted CI workflow."""
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def workflow_steps() -> dict[str, dict[str, Any]]:
    """Return verify-job steps keyed by their name prefix."""
    steps: dict[str, dict[str, Any]] = {}
    for step in workflow()["jobs"]["verify"]["steps"]:
        name = str(step["name"])
        key = (
            "Execute trusted verification"
            if name.startswith("Execute trusted verification")
            else name
        )
        steps[key] = step
    return steps


def test_workflow_runs_the_trusted_executor_on_the_exact_candidate() -> None:
    """The staged trusted entry point, not the candidate's, runs the suite."""
    steps = workflow()["jobs"]["verify"]["steps"]
    names = [str(step["name"]) for step in steps]
    preserve = names.index("Preserve the trusted verification policy")
    candidate_checkout = names.index("Check out the exact candidate")
    execute = next(
        index
        for index, name in enumerate(names)
        if name.startswith("Execute trusted verification")
    )
    trusted_checkout = steps[0]
    assert trusted_checkout["with"]["ref"].startswith(
        "${{ github.event.pull_request.base.sha"
    )
    assert "head.sha" in steps[candidate_checkout]["with"]["ref"]
    assert preserve < candidate_checkout < execute
    assert "trusted_executor.py prepare" in steps[preserve]["run"]
    run = steps[execute]["run"]
    assert 'entry_root="$RUNNER_TEMP/trusted-executor"' in run
    assert 'trusted_executor.py" \\\n    verify --destination' in run
    assert 'export CSARC_VERIFICATION_SUBJECT_ROOT="$GITHUB_WORKSPACE"' in run
    assert '"$entry_root/scripts/verify-template.sh"' in run
    assert '"$entry_root/scripts/verify-fast"' in run
    assert "\n            ./scripts/verify" not in run
    assert (
        "${{ steps.trusted.outputs.executor == 'trusted-base' && "
        "' executor=trusted-base' || '' }}"
    ) in names[execute]


def test_workflow_and_permissions_come_only_from_the_default_branch() -> None:
    """A candidate cannot supply workflow YAML, write tokens, or secrets."""
    data = workflow()
    source = WORKFLOW.read_text(encoding="utf-8")
    triggers = data[True]
    assert set(triggers) == {
        "pull_request_target",
        "merge_group",
        "workflow_dispatch",
    }
    assert set(data["permissions"].values()) == {"read"}
    assert "permissions" not in data["jobs"]["verify"]
    assert "secrets." not in source
    for step in data["jobs"]["verify"]["steps"]:
        if str(step.get("uses", "")).startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] is False
    steps = workflow_steps()
    for name in (
        "Execute trusted verification",
        "Candidate gate self-test (non-authoritative)",
    ):
        assert "GH_TOKEN" not in steps[name].get("env", {}), name


def test_candidate_self_test_is_labeled_and_non_authoritative() -> None:
    """The candidate gate runs last, never fails the job, never counts."""
    steps = workflow()["jobs"]["verify"]["steps"]
    names = [str(step["name"]) for step in steps]
    self_test = names.index("Candidate gate self-test (non-authoritative)")
    execute = next(
        index
        for index, name in enumerate(names)
        if name.startswith("Execute trusted verification")
    )
    step = steps[self_test]
    assert execute < self_test
    assert names[self_test + 1 :] == ["Record result"]
    assert step["continue-on-error"] is True
    assert "steps.trusted.outputs.executor == 'trusted-base'" in step["if"]
    assert 'trusted_executor.py" self-test' in step["run"]
    assert not names[self_test].startswith(
        ("Execute trusted", "Reuse trusted", "Validate trusted clean sync")
    )


def test_workflow_change_routes_through_the_trusted_router(
    tmp_path: Path,
) -> None:
    """A candidate workflow edit is classified by the base router."""
    files = tmp_path / "files"
    files.write_bytes(b".github/workflows/ci.yml\0")
    output = tmp_path / "plan.json"

    subprocess.run(  # noqa: S603 - repository router
        [  # noqa: S607
            "python3",
            str(REPO_ROOT / "scripts" / "ci_tier.py"),
            "--event",
            "pull_request",
            "--base",
            "main",
            "--head",
            "fix/1-workflow",
            "--labels",
            "",
            "--draft",
            "false",
            "--files-from",
            str(files),
            "--output-json",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    plan = json.loads(output.read_text(encoding="utf-8"))
    assert "workflow" in plan["scopes"]
