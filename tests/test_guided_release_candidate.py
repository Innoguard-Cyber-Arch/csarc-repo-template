"""Guided release candidate validation runs from the trusted base (#1106).

`release/v*` pull requests into `main` run "Validate the guided release
candidate" in hosted `verify`. These tests stage the release control set the
way the workflow does, then drive the real `scripts/verify-release-candidate`
and `scripts/release_bundle.py` against a real Git fixture and a fake `gh`
(shared with tests/test_release_publish.py): a candidate that rewrites its own
validation scripts cannot change the result, a normal candidate still passes,
and the workflow keeps the token away from every step that runs candidate
code.
"""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from test_release_publish import (
    build_repo,
    clean_environment,
    fixture_bin,
    git,
    write_pull_request_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = runpy.run_path(str(ROOT / "scripts" / "trusted_executor.py"))
prepare = EXECUTOR["prepare"]
verify_manifest = EXECUTOR["verify_manifest"]
control_paths = EXECUTOR["control_paths"]
REPO = "acme/fixture"
MAINTAINER = "fixture-maintainer"
# A guided `release/v*` candidate is opened by a live maintainer; the shared
# fake `gh` has no collaborator endpoint, so this shim answers that one call.
PERMISSION_SHIM = """#!/usr/bin/env bash
if [[ "$*" == *"/collaborators/"*"/permission"* ]]; then
  echo admin
  exit 0
fi
exec "$(dirname "$0")/gh-fixture" "$@"
"""
VERSION_FILES = (".release-please-manifest.json", "CHANGELOG.md", "version.txt")
GUIDED_IF = (
    "github.event.pull_request.base.ref == 'main' && "
    "startsWith(github.event.pull_request.head.ref, 'release/v') && "
    "steps.release.outputs.ownership == 'csarc-owned'"
)
# A tampered candidate copy records that it ran and whether it saw a token.
TAMPERED_ENTRY = """#!/usr/bin/env bash
printf 'candidate-entry token=%s\\n' "${GH_TOKEN:-unset}" >>"$CANDIDATE_LOG"
exit 0
"""
TAMPERED_MODULE = """import os, sys
with open(os.environ["CANDIDATE_LOG"], "a") as log:
    log.write("candidate-module token=" + os.environ.get("GH_TOKEN", "unset"))
sys.exit(0)
"""


def stage_trusted(source: Path, destination: Path) -> Path:
    """Stage the release control set exactly as the Preserve step does."""
    prepare(source, destination, "release")
    verify_manifest(destination)
    return destination


def tamper(root: Path) -> str:
    """Commit a candidate that rewrites its validation to always pass."""
    entry = root / "scripts" / "verify-release-candidate"
    entry.write_text(TAMPERED_ENTRY, encoding="utf-8")
    entry.chmod(0o755)
    for name in ("release_policy.py", "release_bundle.py"):
        (root / "scripts" / name).write_text(TAMPERED_MODULE, encoding="utf-8")
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "chore(main): release 0.2.0", cwd=root)
    return git("rev-parse", "HEAD", cwd=root)


def serve_pull_request(
    tmp_path: Path,
    fixture: dict[str, str],
    candidate_sha: str,
    files: tuple[str, ...],
) -> None:
    """Serve one guided release pull request from the fake GitHub API."""
    write_pull_request_fixture(
        tmp_path / "state",
        number=7,
        repo=REPO,
        base_sha=fixture["base_sha"],
        candidate_sha=candidate_sha,
        head_ref="release/v0.2.0",
        actor=MAINTAINER,
        committer="web-flow",
        changed_files=files,
    )


def run_validation(
    entry: Path,
    *,
    root: Path,
    tmp_path: Path,
    candidate_sha: str,
    subject: bool = True,
) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run one validation entry point the way the workflow step does."""
    bindir = fixture_bin(tmp_path)
    (bindir / "gh").replace(bindir / "gh-fixture")
    (bindir / "gh").write_text(PERMISSION_SHIM, encoding="utf-8")
    (bindir / "gh").chmod(0o755)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir(exist_ok=True)
    log = tmp_path / "candidate.log"
    log.write_text("", encoding="utf-8")
    pull = runner_temp / "release-pr.json"
    pull.write_text(
        json.dumps(
            {
                "number": 7,
                "sha": candidate_sha,
                "headBranchName": "release/v0.2.0",
                "baseBranchName": "main",
            }
        ),
        encoding="utf-8",
    )
    env = clean_environment()
    env.update(
        {
            "CANDIDATE_LOG": str(log),
            "CSARC_PUBLISH_CANDIDATE_STATUS": "false",
            "CSARC_RELEASE_CANDIDATE_BUNDLE": "false",
            "FIXTURE_REPO": str(root),
            "FIXTURE_STATE": str(tmp_path / "state"),
            "GH_TOKEN": "fixture-token",
            "GITHUB_REPOSITORY": REPO,
            "GITHUB_RUN_ID": "1",
            "GITHUB_SERVER_URL": "https://github.com",
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_TEMP": str(runner_temp),
        }
    )
    if subject:
        env["CSARC_RELEASE_SUBJECT_ROOT"] = str(root)
    result = subprocess.run(  # noqa: S603 - fixture entry point
        [str(entry), str(pull)],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, log.read_text(encoding="utf-8")


def test_release_control_set_covers_entry_and_every_module() -> None:
    """Both layouts stage the entry point and every module beside it."""
    root = control_paths(ROOT, "release")
    assert "scripts/verify-release-candidate" in root
    assert {
        "scripts/release_policy.py",
        "scripts/release_bundle.py",
        "scripts/release_phase.py",
        "scripts/csarc_config.py",
        "scripts/repository_facts.py",
    } <= set(root)
    assert "scripts/verify-fast" not in root
    generated = control_paths(ROOT / "template", "release")
    assert ".csarc/scripts/verify-release-candidate" in generated
    assert ".csarc/scripts/release_candidate.py" in generated
    assert all(path.startswith(".csarc/scripts/") for path in generated)


def test_normal_guided_candidate_passes_from_the_trusted_copy(
    tmp_path: Path,
) -> None:
    """A valid candidate passes, then packages, through trusted copies only."""
    fixture = build_repo(tmp_path)
    root = Path(fixture["root"])
    trusted = stage_trusted(root, tmp_path / "trusted-release")
    serve_pull_request(
        tmp_path, fixture, fixture["candidate_sha"], VERSION_FILES
    )

    result, log = run_validation(
        trusted / "scripts" / "verify-release-candidate",
        root=root,
        tmp_path=tmp_path,
        candidate_sha=fixture["candidate_sha"],
    )

    assert result.returncode == 0, result.stderr
    assert "Release follow-up source is verified." in result.stdout
    assert "matches current base" in result.stdout
    assert log == ""
    # Packaging is deferred to the tokenless step.
    assert not (tmp_path / "runner-temp" / "release-candidate-assets").exists()

    worktree = tmp_path / "package"
    git(
        "worktree",
        "add",
        "--detach",
        str(worktree),
        fixture["candidate_sha"],
        cwd=root,
    )
    output = tmp_path / "assets"
    env = clean_environment()
    env.pop("GH_TOKEN", None)
    package = subprocess.run(  # noqa: S603 - trusted bundler fixture
        [
            sys.executable,
            str(trusted / "scripts" / "release_bundle.py"),
            "candidate",
            "--root",
            str(worktree),
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert package.returncode == 0, package.stderr
    assert (output / "fixture-0.2.0.tar").is_file()


def test_tampered_candidate_validation_cannot_decide_the_result(
    tmp_path: Path,
) -> None:
    """Rewriting verify-release-candidate in the candidate changes nothing."""
    fixture = build_repo(tmp_path)
    root = Path(fixture["root"])
    # The Preserve step stages from the trusted base before checkout.
    trusted = stage_trusted(root, tmp_path / "trusted-release")
    candidate_sha = tamper(root)
    files = (
        *VERSION_FILES,
        "scripts/release_bundle.py",
        "scripts/release_policy.py",
        "scripts/verify-release-candidate",
    )
    serve_pull_request(tmp_path, fixture, candidate_sha, files)

    # The pre-#1106 step ran the candidate copy, which passed itself with
    # the token in reach.
    legacy, legacy_log = run_validation(
        root / "scripts" / "verify-release-candidate",
        root=root,
        tmp_path=tmp_path,
        candidate_sha=candidate_sha,
        subject=False,
    )
    assert legacy.returncode == 0
    assert "candidate-entry token=fixture-token" in legacy_log

    result, log = run_validation(
        trusted / "scripts" / "verify-release-candidate",
        root=root,
        tmp_path=tmp_path,
        candidate_sha=candidate_sha,
    )

    assert result.returncode != 0
    assert log == ""
    assert "release follow-up" in result.stderr


def verify_steps(source: str) -> list[dict[str, Any]]:
    """Return the verify-job steps of one workflow source."""
    return yaml.safe_load(source)["jobs"]["verify"]["steps"]


def test_workflow_keeps_the_token_away_from_candidate_code() -> None:
    """Only the trusted step holds the token, and it runs before candidates."""
    source = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    data = yaml.safe_load(source)
    assert set(data["permissions"].values()) == {"read"}
    assert "permissions" not in data["jobs"]["verify"]
    assert "secrets." not in source
    steps = verify_steps(source)
    names = [str(step["name"]) for step in steps]
    preserve = steps[names.index("Preserve the trusted verification policy")]
    assert "--control-set release" in preserve["run"]
    assert '--destination "$RUNNER_TEMP/trusted-release"' in preserve["run"]
    assert "release/v" in preserve["env"]["GUIDED_RELEASE"]

    checkout = names.index("Check out the exact candidate")
    validate_index = names.index("Validate the guided release candidate")
    package_index = names.index("Package the guided release candidate")
    execute = next(
        index
        for index, name in enumerate(names)
        if name.startswith("Execute trusted verification")
    )
    # The token step runs after checkout but before any candidate code.
    assert checkout < validate_index < execute < package_index
    validate = steps[validate_index]
    package = steps[package_index]
    for step in (validate, package):
        assert GUIDED_IF in step["if"]
    assert validate["env"]["GH_TOKEN"] == "${{ github.token }}"  # noqa: S105
    assert validate["env"]["CSARC_RELEASE_CANDIDATE_BUNDLE"] == "false"
    assert 'verify --destination "$trusted"' in validate["run"]
    assert 'CSARC_RELEASE_SUBJECT_ROOT="$GITHUB_WORKSPACE"' in validate["run"]
    assert (
        '"$trusted/scripts/verify-release-candidate" '
        '"$RUNNER_TEMP/release-pr.json"'
    ) in validate["run"]
    assert "./scripts/verify-release-candidate" not in source
    assert '"$trusted/scripts/release_bundle.py" candidate' in package["run"]
    # No step that can run candidate code receives a token.
    for index in range(execute, len(steps)):
        env = steps[index].get("env", {})
        assert "GH_TOKEN" not in env, names[index]
        assert "GITHUB_TOKEN" not in env, names[index]


def test_template_workflow_matches_the_trusted_release_route() -> None:
    """Generated projects get the same trusted release candidate route."""
    source = (
        ROOT / "template" / ".github" / "workflows" / "ci.yml.jinja"
    ).read_text(encoding="utf-8")
    assert "--control-set release" in source
    assert "-f .csarc/scripts/verify-release-candidate" in source
    assert (
        '"$trusted/.csarc/scripts/verify-release-candidate" '
        '"$RUNNER_TEMP/release-pr.json"'
    ) in source
    assert '"$trusted/.csarc/scripts/release_bundle.py" candidate' in source
    assert "./.csarc/scripts/verify-release-candidate" not in source
    validate = source.index("- name: Validate the guided release candidate")
    execute = source.index("- name: Execute trusted verification")
    package = source.index("- name: Package the guided release candidate")
    assert validate < execute < package
