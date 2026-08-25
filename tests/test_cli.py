"""End-to-end tests for the CSARC lifecycle CLI."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest
from pypdf import PdfReader

import csarc_cli.cli as cli
from csarc_cli.cli import CliError, main

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a successful fixture command."""
    return subprocess.run(  # noqa: S603
        command, cwd=cwd, check=True, capture_output=True, text=True
    )


def git(repository: Path, *arguments: str) -> str:
    """Run Git in a fixture repository."""
    return run(["git", *arguments], repository).stdout.strip()


def commit(repository: Path, message: str) -> str:
    """Commit all fixture changes and return the full SHA."""
    git(repository, "add", ".")
    git(repository, "commit", "-m", message)
    return git(repository, "rev-parse", "HEAD")


def write_executable(path: Path, content: str) -> None:
    """Create an executable fixture script."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def make_template(root: Path) -> tuple[Path, str]:
    """Create a minimal versioned Copier template."""
    source = root / "template-source"
    (source / "template").mkdir(parents=True)
    (source / "copier.yml").write_text(
        """\
_subdirectory: template
_answers_file: .copier-answers.yml
project_mode:
  type: str
  default: new
project_name:
  type: str
  default: Test Project
project_slug:
  type: str
  default: test-project
package_name:
  type: str
  default: test_project
language:
  type: str
  default: ci
code_owner:
  type: str
  default: '@Innoguard-Cyber-Arch/repository-maintainers'
reviewers:
  type: str
  default: '@default-reviewer'
coverage_mode:
  type: str
  default: global
project_visibility:
  type: str
  default: private
enable_codeql:
  type: bool
  default: "{{ project_visibility == 'public' and language != 'ci' }}"
enable_release_attestations:
  type: bool
  default: "{{ project_visibility == 'public' and language != 'ci' }}"
""",
        encoding="utf-8",
    )
    (source / "template" / "managed.txt").write_text(
        "template version one\n", encoding="utf-8"
    )
    (source / "template" / ".python-version").write_text(
        "3.14\n", encoding="utf-8"
    )
    (source / "template" / "pyproject.toml").write_text(
        '[project]\nname = "template-project"\nversion = "0.1.0"\n'
        'requires-python = ">=3.14"\n',
        encoding="utf-8",
    )
    (source / "template" / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "# Changes here will be overwritten by Copier.\n"
        "{{ _copier_answers|to_nice_yaml -}}\n",
        encoding="utf-8",
    )
    write_executable(
        source / "template" / "scripts" / "verify",
        "#!/usr/bin/env bash\nset -euo pipefail\ntest -f managed.txt\n"
        "if [[ -x scripts/verify-product ]]; then\n"
        "  ./scripts/verify-product\n"
        "fi\n",
    )
    write_executable(
        source / "template" / "scripts" / "apply-repository-settings.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "test \"${1:-}\" = plan\nprintf 'settings plan only\\n'\n",
    )
    git(source, "init", "-b", "main")
    git(source, "config", "user.name", "CLI Test")
    git(source, "config", "user.email", "cli-test@example.invalid")
    return source, commit(source, "test: template version one")


def lifecycle_plan_path(target: Path, mode: str) -> Path:
    """Return the default external plan path for init or update."""
    return target.parent / f"{target.name}-csarc-{mode}-plan.json"


def copy_real_template(destination: Path) -> None:
    """Create an independent Git source from the repository's tracked tree."""
    shutil.copytree(
        ROOT,
        destination,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"
        ),
    )
    git(destination, "init", "-b", "main")
    git(destination, "config", "user.name", "CLI Test")
    git(destination, "config", "user.email", "cli-test@example.invalid")


def apply_init(arguments: list[str], target: Path) -> None:
    """Plan and apply one init transaction."""
    assert main(arguments) == 0
    assert (
        main(
            [
                "init",
                str(target),
                "--apply-plan",
                str(lifecycle_plan_path(target, "init")),
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    )


def apply_update(arguments: list[str], target: Path) -> int:
    """Plan and apply one update transaction."""
    assert main(arguments) == 0
    return main(
        [
            "update",
            str(target),
            "--apply-plan",
            str(lifecycle_plan_path(target, "update")),
            "--allow-unreleased",
            "--yes",
            "--non-interactive",
        ]
    )


def apply_adopt(arguments: list[str], target: Path) -> None:
    """Plan and apply one adoption transaction."""
    assert main(arguments) == 0
    plan = (
        target.parent
        / f"{target.name}-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    assert (
        main(
            [
                "adopt",
                str(target),
                "--apply-plan",
                str(plan),
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    )


def initialize_project(tmp_path: Path) -> tuple[Path, Path, str]:
    """Create a generated project pinned to the first template commit."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "new-project"
    apply_init(
        [
            "init",
            str(project),
            "--source",
            str(source),
            "--to",
            first_sha,
            "--allow-unreleased",
            "--data",
            "language=ci",
        ],
        project,
    )
    return source, project, first_sha


def initialize_pending_adoption(tmp_path: Path) -> tuple[Path, Path]:
    """Start a minimal adoption that requires a manual manifest merge."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "pending-product"
    project.mkdir()
    write_executable(
        project / "scripts" / "verify",
        (source / "template" / "scripts" / "verify").read_text(
            encoding="utf-8"
        ),
    )
    (project / "pyproject.toml").write_text(
        '[project]\nname = "pending-product"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: pending product")
    arguments = [
        "adopt",
        str(project),
        "--source",
        str(source),
        "--to",
        first_sha,
        "--allow-unreleased",
        "--data",
        "language=ci",
    ]
    assert main(arguments) == 0
    plan = (
        tmp_path
        / "pending-product-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(plan),
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 1
    )
    return source, project


def finalize_plan_path(project: Path) -> Path:
    """Return the default external plan path for one adoption target."""
    return (
        project.parent
        / f"{project.name}-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )


class FakeReleaseClient:
    """Deterministic GitHub boundary used by trust-chain tests."""

    def __init__(self) -> None:
        self.repository_id = cli.CANONICAL_REPOSITORY_ID
        self.release_values: dict[str, object] = {
            "id": 42,
            "tag_name": "v1.2.3",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-08-24T00:00:00Z",
            "immutable": True,
        }
        self.tag_results = [
            cli.TagResolution("a" * 40, "b" * 40),
            cli.TagResolution("a" * 40, "b" * 40),
        ]
        self.release_error: CliError | None = None
        self.commit_error: CliError | None = None

    def repository(self) -> dict[str, object]:
        return {
            "id": self.repository_id,
            "full_name": cli.CANONICAL_REPOSITORY,
        }

    def release(self, tag: str | None) -> dict[str, object]:
        assert tag in {None, "v1.2.3"}
        return self.release_values

    def resolve_tag(self, tag: str) -> cli.TagResolution:
        assert tag == "v1.2.3"
        return self.tag_results.pop(0)

    def verify_release(self, tag: str) -> None:
        assert tag == "v1.2.3"
        if self.release_error is not None:
            raise self.release_error

    def verify_commit(self, sha: str) -> None:
        assert cli.FULL_SHA.fullmatch(sha)
        if self.commit_error is not None:
            raise self.commit_error


def test_init_dry_run_and_apply_pin_full_sha(tmp_path: Path) -> None:
    """Init previews without writes, then creates and verifies the project."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "new-project"
    arguments = [
        "init",
        str(project),
        "--source",
        str(source),
        "--to",
        first_sha,
        "--allow-unreleased",
        "--data",
        "language=ci",
    ]

    assert main([*arguments, "--dry-run"]) == 0
    assert not project.exists()
    plan_path = lifecycle_plan_path(project, "init")
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["transaction"]["applicable"] is True
    assert cli.PROVENANCE_FILE.as_posix() in payload["transaction"]["artifacts"]
    apply_arguments = [
        "init",
        str(project),
        "--apply-plan",
        str(plan_path),
        "--yes",
        "--non-interactive",
    ]
    assert main(apply_arguments) == 2
    assert not project.exists()
    assert main([*apply_arguments, "--allow-unreleased"]) == 0
    answers = (project / ".copier-answers.yml").read_text(encoding="utf-8")
    assert f"_commit: {first_sha}" in answers
    assert (project / "managed.txt").read_text() == "template version one\n"
    provenance = json.loads(
        (project / cli.PROVENANCE_FILE).read_text(encoding="utf-8")
    )
    assert provenance["commit_sha"] == first_sha
    assert provenance["verification"] == "development-unreleased"


@pytest.mark.parametrize("entrypoint", ("init", "adopt"))
def test_lifecycle_plan_replay_updates_v1_to_v2(
    tmp_path: Path, entrypoint: str
) -> None:
    """Replay init or adopt v1, then update the clean target to v2."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / f"{entrypoint}-lifecycle"
    arguments = [
        entrypoint,
        str(project),
        "--source",
        str(source),
        "--to",
        first_sha,
        "--allow-unreleased",
        "--data",
        "language=ci",
    ]
    if entrypoint == "init":
        apply_init(arguments, project)
        git(project, "init", "-b", "main")
        git(project, "config", "user.name", "CLI Test")
        git(project, "config", "user.email", "cli-test@example.invalid")
    else:
        project.mkdir()
        (project / "product.txt").write_text("preserve me\n", encoding="utf-8")
        git(project, "init", "-b", "main")
        git(project, "config", "user.name", "CLI Test")
        git(project, "config", "user.email", "cli-test@example.invalid")
        commit(project, "test: existing product")
        apply_adopt(arguments, project)
    commit(project, f"test: {entrypoint} template v1")

    (source / "template" / "managed.txt").write_text(
        "template version two\n", encoding="utf-8"
    )
    second_sha = commit(source, "test: template version two")
    assert (
        apply_update(
            [
                "update",
                str(project),
                "--to",
                second_sha,
                "--allow-unreleased",
            ],
            project,
        )
        == 0
    )

    update_plan = json.loads(
        lifecycle_plan_path(project, "update").read_text(encoding="utf-8")
    )
    transaction = update_plan["transaction"]
    assert transaction["verification"] == "passed"
    for relative_name, digest in transaction["artifacts"].items():
        assert cli.file_fingerprint(project / relative_name) == digest
    assert (project / "managed.txt").read_text(encoding="utf-8") == (
        "template version two\n"
    )
    if entrypoint == "adopt":
        assert (project / "product.txt").read_text(encoding="utf-8") == (
            "preserve me\n"
        )
    provenance = json.loads(
        (project / cli.PROVENANCE_FILE).read_text(encoding="utf-8")
    )
    assert provenance["commit_sha"] == second_sha
    assert provenance["previous"]["commit_sha"] == first_sha
    assert f"_commit: {second_sha}" in (
        project / ".copier-answers.yml"
    ).read_text(encoding="utf-8")


def test_update_verification_failure_is_zero_write_and_safely_replayable(
    tmp_path: Path,
) -> None:
    """Keep a failed candidate external, then accept a newly verified plan."""
    source, project, _ = initialize_project(tmp_path)
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: generated project")
    (source / "template" / "managed.txt").write_text(
        "unverified version two\n", encoding="utf-8"
    )
    write_executable(
        source / "template" / "scripts" / "verify",
        "#!/usr/bin/env bash\nset -euo pipefail\nexit 23\n",
    )
    failing_sha = commit(source, "test: failing template verification")
    before = cli.target_file_snapshot(project)

    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                failing_sha,
                "--allow-unreleased",
            ]
        )
        == 0
    )
    plan_path = lifecycle_plan_path(project, "update")
    failed_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert failed_plan["transaction"]["applicable"] is False
    assert "verification failed" in failed_plan["transaction"]["verification"]
    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert cli.target_file_snapshot(project) == before

    write_executable(
        source / "template" / "scripts" / "verify",
        "#!/usr/bin/env bash\nset -euo pipefail\ntest -f managed.txt\n",
    )
    verified_sha = commit(source, "test: repair template verification")
    assert (
        apply_update(
            [
                "update",
                str(project),
                "--to",
                verified_sha,
                "--allow-unreleased",
            ],
            project,
        )
        == 0
    )
    assert (project / "managed.txt").read_text(encoding="utf-8") == (
        "unverified version two\n"
    )
    assert (
        json.loads((project / cli.PROVENANCE_FILE).read_text(encoding="utf-8"))[
            "commit_sha"
        ]
        == verified_sha
    )


def test_init_verification_failure_is_zero_write_and_safely_replayable(
    tmp_path: Path,
) -> None:
    """Reject an unverified init candidate without creating the target."""
    source, _ = make_template(tmp_path)
    project = tmp_path / "init-verification"
    write_executable(
        source / "template" / "scripts" / "verify",
        "#!/usr/bin/env bash\nset -euo pipefail\nexit 23\n",
    )
    failing_sha = commit(source, "test: failing init verification")
    arguments = [
        "init",
        str(project),
        "--source",
        str(source),
        "--to",
        failing_sha,
        "--allow-unreleased",
    ]

    assert main(arguments) == 0
    plan_path = lifecycle_plan_path(project, "init")
    failed_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert failed_plan["transaction"]["applicable"] is False
    assert (
        main(
            [
                "init",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert not project.exists()

    write_executable(
        source / "template" / "scripts" / "verify",
        "#!/usr/bin/env bash\nset -euo pipefail\ntest -f managed.txt\n",
    )
    verified_sha = commit(source, "test: repair init verification")
    apply_init(
        [
            "init",
            str(project),
            "--source",
            str(source),
            "--to",
            verified_sha,
            "--allow-unreleased",
        ],
        project,
    )
    assert (project / "managed.txt").is_file()


def test_init_rejects_destination_drift_after_planning(tmp_path: Path) -> None:
    """Do not replace a destination created after an init plan."""
    source, revision = make_template(tmp_path)
    project = tmp_path / "late-destination"
    assert (
        main(
            [
                "init",
                str(project),
                "--source",
                str(source),
                "--to",
                revision,
                "--allow-unreleased",
            ]
        )
        == 0
    )
    project.mkdir()
    sentinel = project / "product.txt"
    sentinel.write_text("do not replace\n", encoding="utf-8")

    assert (
        main(
            [
                "init",
                str(project),
                "--apply-plan",
                str(lifecycle_plan_path(project, "init")),
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 2
    )
    assert sentinel.read_text(encoding="utf-8") == "do not replace\n"
    assert not (project / "managed.txt").exists()


def test_capability_preflight_uses_readable_github_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".git").mkdir()
    script = tmp_path / "release_policy.py"
    script.touch()
    response = {
        "mode": "direct",
        "capabilities": {
            "actions_pull_requests": {"state": "blocked"},
            "contents": {"state": "unknown"},
        },
        "integrations": {
            "renovate": {
                "state": "request-owner",
                "next_step": "Ask the organization owner.",
            }
        },
    }

    def fake_run(
        command: list[str],
        *,
        cwd: Path | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture, check
        if command[0] == "git" and "rev-parse" in command:
            return subprocess.CompletedProcess(
                command, 0, stdout=f"{tmp_path}\n", stderr=""
            )
        if command[0] == "git":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="https://github.com/owner/repo.git\n",
                stderr="",
            )
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(response), stderr=""
        )

    monkeypatch.setattr(cli, "run", fake_run)
    assert cli.capability_preflight(script, tmp_path) == response
    output = capsys.readouterr().out
    assert "actions_pull_requests=blocked" in output
    assert "Optional integration renovate: request-owner" in output
    assert "Next: Ask the organization owner." in output


def test_capability_preflight_without_origin_uses_integration_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = tmp_path / "release_policy.py"
    script.touch()
    monkeypatch.setattr(
        cli,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout="", stderr=""
        ),
    )

    payload = cli.capability_preflight(script, tmp_path)

    integration = payload["integrations"]["renovate"]
    assert integration["state"] == "fallback"
    assert "Dependabot" in integration["next_step"]
    assert "Optional integration renovate: fallback" in capsys.readouterr().out


def test_target_repository_uses_explicit_repo_for_new_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_REPO", "owner/new-repository")
    monkeypatch.setattr(
        cli,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout="", stderr=""
        ),
    )

    assert cli.target_repository(tmp_path) == "owner/new-repository"


def test_target_repository_does_not_inherit_an_enclosing_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Treat an init destination inside another checkout as a new repo."""
    parent = tmp_path / "parent"
    parent.mkdir()
    git(parent, "init", "-b", "main")
    git(
        parent,
        "remote",
        "add",
        "origin",
        "https://github.com/parent-org/parent-repo.git",
    )
    target = parent / "new-project"
    target.mkdir()
    monkeypatch.delenv("GH_REPO", raising=False)

    assert cli.target_repository(target) is None


@pytest.mark.parametrize("visibility", ["public", "private", "internal"])
def test_repository_context_uses_github_owner_and_visibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    visibility: str,
) -> None:
    """Trust validated GitHub metadata instead of the template default."""
    monkeypatch.setattr(cli, "target_repository", lambda _: "owner/repo")
    monkeypatch.setattr(
        cli,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout=json.dumps(
                {
                    "full_name": "owner/repo",
                    "owner": {"login": "owner", "type": "Organization"},
                    "visibility": visibility,
                }
            ),
            stderr="",
        ),
    )

    context = cli.repository_context(tmp_path, None)

    assert context.owner == "owner"
    assert context.owner_type == "organization"
    assert context.visibility == visibility
    assert context.verified


def test_repository_context_requires_visibility_when_api_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed unless an operator supplies the unavailable setting."""
    monkeypatch.setattr(cli, "target_repository", lambda _: "owner/repo")
    monkeypatch.setattr(
        cli,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout="", stderr="permission denied"
        ),
    )

    with pytest.raises(CliError, match="--data project_visibility"):
        cli.repository_context(tmp_path, None)

    context = cli.repository_context(tmp_path, "internal")
    assert context.owner == "owner"
    assert context.visibility == "internal"
    assert context.source == "explicit"
    assert not context.verified


def test_repository_context_without_remote_uses_safe_or_explicit_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep no-remote projects private unless the user says otherwise."""
    monkeypatch.setattr(cli, "target_repository", lambda _: None)

    default = cli.repository_context(tmp_path, None)
    explicit = cli.repository_context(tmp_path, "public")

    assert default.visibility == "private"
    assert default.source == "safe-default"
    assert explicit.visibility == "public"
    assert explicit.source == "explicit"


@pytest.mark.parametrize(
    ("visibility", "enabled"),
    [("public", True), ("private", False), ("internal", False)],
)
def test_init_json_uses_one_complete_resolved_plan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    visibility: str,
    enabled: bool,
) -> None:
    """Emit repository defaults and every persisted answer from one plan."""
    source, revision = make_template(tmp_path)
    target = tmp_path / f"{visibility}-project"

    assert (
        main(
            [
                "init",
                str(target),
                "--source",
                str(source),
                "--to",
                revision,
                "--allow-unreleased",
                "--data",
                "language=python",
                "--data",
                f"project_visibility={visibility}",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema_version"] == 1
    assert payload["template"]["sha"] == revision
    assert payload["repository"]["visibility"] == visibility
    assert payload["answers"]["project_visibility"] == visibility
    assert payload["answers"]["enable_codeql"] is enabled
    assert payload["answers"]["enable_release_attestations"] is enabled
    assert payload["answers"]["reviewers"] == "@default-reviewer"
    assert payload["release_capabilities"]["mode"] == "verification-only"
    assert not target.exists()


def test_milestone_description_plan_is_paginated_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    legacy = """## Problem

使用者看不到完整 story。

## Outcome

使用者可以驗收完整成果。

## Acceptance criteria

- [x] 結果可驗證。

## Out of scope

不改 Issue 關聯。

## Verification

檢查 Milestone。

## Source

Issue #1.
"""
    current = cli.upgraded_milestone_description(
        legacy,
        [{"number": 1, "title": "Deliver the story", "state": "closed"}],
    )
    assert current is not None
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture, check
        calls.append(command)
        endpoint = command[-1]
        payload: object
        if "milestones?" in endpoint:
            payload = [
                [
                    {"number": 1, "title": "Legacy", "description": legacy},
                    {"number": 2, "title": "Current", "description": current},
                ],
                [
                    {
                        "number": 3,
                        "title": "Custom",
                        "description": "Custom notes",
                    },
                    {"number": 4, "title": "Empty", "description": legacy},
                ],
            ]
        elif "milestone=1" in endpoint:
            payload = [
                [
                    {"number": 12, "title": "Second", "state": "open"},
                    {
                        "number": 11,
                        "title": "First",
                        "state": "closed",
                    },
                ],
                [
                    {
                        "number": 13,
                        "title": "Delivery PR",
                        "state": "closed",
                        "pull_request": {},
                    }
                ],
            ]
        elif "milestone=4" in endpoint:
            payload = [[]]
        elif endpoint.endswith("milestones/1"):
            payload = {"description": legacy}
        else:
            payload = {}
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload), stderr=""
        )

    monkeypatch.setattr(cli, "target_repository", lambda _: "owner/repo")
    monkeypatch.setattr(cli, "run", fake_run)

    plan = cli.milestone_description_plan(tmp_path)

    assert plan is not None
    assert [change.number for change in plan.changes] == [1]
    assert plan.current == ((2, "Current"),)
    assert plan.review == ((3, "Custom"), (4, "Empty"))
    assert "使用者看不到完整 story。" in plan.changes[0].after
    assert "- #11 — First" in plan.changes[0].after
    assert "- #12 — Second" in plan.changes[0].after
    assert "## References" in plan.changes[0].after
    assert not any("PATCH" in call for call in calls)
    assert "Upgrade (1)" in capsys.readouterr().out

    cli.apply_milestone_description_plan(plan)

    patches = [call for call in calls if "PATCH" in call]
    assert len(patches) == 1
    assert patches[0][4].endswith("milestones/1")
    assert cli.milestone_headings(plan.changes[0].after) == (
        cli.CURRENT_MILESTONE_HEADINGS
    )
    assert cli.upgraded_milestone_description(plan.changes[0].after, []) is None


def test_milestone_description_plan_degrades_without_api_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unavailable Milestone access does not block repository adoption."""
    monkeypatch.setattr(cli, "target_repository", lambda _: "owner/repo")
    monkeypatch.setattr(
        cli,
        "gh_pages",
        lambda _: (_ for _ in ()).throw(
            cli.CliError("GitHub authentication is unavailable")
        ),
    )

    assert cli.milestone_description_plan(tmp_path) is None
    output = capsys.readouterr().out
    assert "Milestone descriptions: unavailable" in output
    assert "review them manually" in output


def test_adopt_defaults_to_dry_run_and_preserves_product_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Adopt detects Python and never changes the existing manifest."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "legacy-product"
    project.mkdir()
    manifest = project / "pyproject.toml"
    manifest.write_text(
        '[project]\nname = "legacy-product"\nversion = "0.1.0"\n'
        'requires-python = ">=3.14"\n',
        encoding="utf-8",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: legacy product")
    arguments = [
        "adopt",
        str(project),
        "--source",
        str(source),
        "--to",
        first_sha,
        "--allow-unreleased",
    ]

    before = git(project, "status", "--porcelain")
    assert main([*arguments, "--dry-run"]) == 0
    plan = capsys.readouterr().out
    assert "language=python" in plan
    assert "Overwrite (0):" in plan
    assert "Manual merge (1):" in plan
    assert "pyproject.toml" in plan
    assert git(project, "status", "--porcelain") == before
    assert not (project / ".copier-answers.yml").exists()
    report_dir = tmp_path / "legacy-product-csarc-adoption-report"
    markdown = report_dir / "csarc-adoption-dry-run.md"
    pdf = report_dir / "csarc-adoption-dry-run.pdf"
    assert markdown.is_file()
    assert pdf.is_file()
    assert "Decision: Review required" in markdown.read_text(encoding="utf-8")
    reader = PdfReader(pdf)
    assert len(reader.pages) == 1
    pdf_text = reader.pages[0].extract_text()
    assert "Review required" in pdf_text
    assert "Manual merge" in pdf_text
    assert main([*arguments, "--dry-run"]) == 0
    assert git(project, "status", "--porcelain") == before
    plan_path = report_dir / cli.ADOPTION_PLAN_BASENAME
    assert plan_path.is_file()
    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 1
    )
    assert manifest.read_text(encoding="utf-8") == (
        '[project]\nname = "legacy-product"\nversion = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
    )
    assert (project / ".copier-answers.yml").is_file()
    assert (project / cli.PENDING_ADOPTION_FILE).is_file()
    assert not (project / cli.PROVENANCE_FILE).exists()
    pending_status = git(project, "status", "--porcelain")
    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 0
    assert git(project, "status", "--porcelain") == pending_status
    assert (
        main(
            [
                "update",
                str(project),
                "--allow-unreleased",
                "--check",
                "--json",
            ]
        )
        == 2
    )
    assert "Adoption is pending" in capsys.readouterr().out
    assert (
        main(
            [
                "adopt",
                str(project),
                "--finalize",
                "--apply-plan",
                str(finalize_plan_path(project)),
            ]
        )
        == 2
    )
    assert "--allow-unreleased again" in capsys.readouterr().err
    assert git(project, "status", "--porcelain") == pending_status
    assert (
        main(
            [
                "adopt",
                str(project),
                "--finalize",
                "--apply-plan",
                str(finalize_plan_path(project)),
                "--allow-unreleased",
                "--non-interactive",
                "--yes",
            ]
        )
        == 0
    )
    assert (project / "uv.lock").is_file()
    assert (project / cli.PROVENANCE_FILE).is_file()
    assert not (project / cli.PENDING_ADOPTION_FILE).exists()


def test_adopt_finalize_rejects_answer_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Never complete an adoption whose saved Copier answers changed."""
    _, project = initialize_pending_adoption(tmp_path)
    answers = project / ".copier-answers.yml"
    answers.write_text(
        answers.read_text(encoding="utf-8") + "# unexpected edit\n",
        encoding="utf-8",
    )

    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 2
    assert "Copier answers changed" in capsys.readouterr().err
    assert (project / cli.PENDING_ADOPTION_FILE).is_file()
    assert not (project / cli.PROVENANCE_FILE).exists()


def test_adopt_finalize_rejects_source_and_managed_file_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Require the original source and every copied managed file."""
    source, project = initialize_pending_adoption(tmp_path)
    unavailable_source = tmp_path / "template-source-moved"
    source.rename(unavailable_source)

    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 2
    assert "template source is unavailable" in capsys.readouterr().err
    unavailable_source.rename(source)
    (project / "managed.txt").write_text(
        "unexpected managed edit\n", encoding="utf-8"
    )

    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 2
    assert "Managed adoption file drifted" in capsys.readouterr().err
    assert (project / cli.PENDING_ADOPTION_FILE).is_file()
    assert not (project / cli.PROVENANCE_FILE).exists()


def test_adopt_finalize_rejects_preserved_managed_file_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fingerprint template-managed files that adoption preserved."""
    _, project = initialize_pending_adoption(tmp_path)
    write_executable(
        project / "scripts" / "verify",
        "#!/usr/bin/env bash\nexit 0\n",
    )

    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 2
    assert "Managed adoption file drifted: scripts/verify" in (
        capsys.readouterr().err
    )
    assert (project / cli.PENDING_ADOPTION_FILE).is_file()
    assert not (project / cli.PROVENANCE_FILE).exists()


def test_adopt_finalize_rejects_repository_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Do not finalize against a different GitHub repository context."""
    _, project = initialize_pending_adoption(tmp_path)
    monkeypatch.setattr(
        cli,
        "repository_context",
        lambda *args, **kwargs: cli.RepositoryContext(
            "different/repository",
            "different",
            "organization",
            "private",
            "github",
            True,
        ),
    )

    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 2
    assert "origin or visibility changed" in capsys.readouterr().err
    assert (project / cli.PENDING_ADOPTION_FILE).is_file()


def test_adopt_finalize_rechecks_repository_context_after_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject repository context drift while finalize waits for approval."""
    _, project = initialize_pending_adoption(tmp_path)
    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 0
    stable = cli.RepositoryContext(
        None,
        None,
        None,
        "private",
        "saved",
        False,
        "No GitHub origin or GH_REPO was found.",
    )
    current = [stable]
    monkeypatch.setattr(
        cli, "repository_context", lambda *args, **kwargs: current[0]
    )

    def drift_during_confirmation(_: str) -> str:
        current[0] = cli.RepositoryContext(
            "different/repository",
            "different",
            "organization",
            "public",
            "github",
            True,
        )
        return "yes"

    monkeypatch.setattr("builtins.input", drift_during_confirmation)
    assert (
        main(
            [
                "adopt",
                str(project),
                "--finalize",
                "--apply-plan",
                str(finalize_plan_path(project)),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert "Repository context changed" in capsys.readouterr().err
    assert (project / cli.PENDING_ADOPTION_FILE).is_file()
    assert not (project / cli.PROVENANCE_FILE).exists()


def test_adopt_finalize_failure_keeps_actionable_pending_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep the checkpoint and explain how to retry a failed verification."""
    _, project = initialize_pending_adoption(tmp_path)
    monkeypatch.setattr(
        cli,
        "verify_project",
        lambda _: (_ for _ in ()).throw(CliError("fixture failure")),
    )

    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 2
    assert "rerun csarc adopt --finalize" in capsys.readouterr().err
    assert (project / cli.PENDING_ADOPTION_FILE).is_file()
    assert not (project / cli.PROVENANCE_FILE).exists()


def test_adopt_finalize_requires_matching_second_stage_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Bind accepted manual results and recheck them after confirmation."""
    _, project = initialize_pending_adoption(tmp_path)
    assert main(["adopt", str(project), "--finalize", "--yes"]) == 0
    assert finalize_plan_path(project).is_file()
    capsys.readouterr()
    manifest = project / "pyproject.toml"
    reviewed = manifest.read_bytes()
    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 0
    plan_path = finalize_plan_path(project)
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "adopt-finalize"
    assert payload["adoption"]["manual_results"]["pyproject.toml"]
    assert payload["adoption"]["target_files"]["pyproject.toml"]

    def drift_during_confirmation(_: str) -> str:
        manifest.write_text("changed after review\n", encoding="utf-8")
        return "yes"

    monkeypatch.setattr("builtins.input", drift_during_confirmation)
    assert (
        main(
            [
                "adopt",
                str(project),
                "--finalize",
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert "changed after the plan was created or confirmed" in (
        capsys.readouterr().err
    )
    assert manifest.read_bytes() != reviewed
    assert (project / cli.PENDING_ADOPTION_FILE).is_file()
    assert not (project / cli.PROVENANCE_FILE).exists()


def test_adopt_finalize_rejects_unexpected_worktree_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reject files outside the complete pending adoption allowlist."""
    _, project = initialize_pending_adoption(tmp_path)
    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 0
    (project / "unexpected.txt").write_text("not reviewed\n", encoding="utf-8")

    assert (
        main(
            [
                "adopt",
                str(project),
                "--finalize",
                "--apply-plan",
                str(finalize_plan_path(project)),
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 2
    )
    assert "unexpected working-tree changes: unexpected.txt" in (
        capsys.readouterr().err
    )
    assert not (project / cli.PROVENANCE_FILE).exists()


def test_adopt_finalize_does_not_trust_edited_checkpoint_fingerprints(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Re-render managed content instead of trusting mutable checkpoint data."""
    _, project = initialize_pending_adoption(tmp_path)
    managed = project / "managed.txt"
    managed.write_text("tampered managed content\n", encoding="utf-8")
    checkpoint_path = project / cli.PENDING_ADOPTION_FILE
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    for item in checkpoint["managed_files"]:
        if item["path"] == "managed.txt":
            item["fingerprint"] = cli.file_fingerprint(managed)
    checkpoint_path.write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 2
    assert "differs from the verified template: managed.txt" in (
        capsys.readouterr().err
    )
    assert not (project / cli.PROVENANCE_FILE).exists()


@pytest.mark.parametrize(
    ("language", "manifest_name", "lock_name"),
    [
        ("python", "pyproject.toml", "uv.lock"),
        ("typescript", "package.json", "pnpm-lock.yaml"),
    ],
)
def test_real_template_adoption_resumes_after_manifest_merge(
    tmp_path: Path,
    language: str,
    manifest_name: str,
    lock_name: str,
) -> None:
    """Finalize real Python and TypeScript adoptions without prior locks."""
    source = tmp_path / "real-template-source"
    copy_real_template(source)
    revision_sha = commit(source, "test: copy real template")
    project = tmp_path / f"existing-{language}"
    reference = tmp_path / f"reference-{language}"
    data = cli.base_data(
        project,
        "adopt",
        {"coverage_mode": "global", "language": language},
    )
    data["project_visibility"] = "private"
    cli.copier_copy(
        str(source),
        cli.Revision(revision_sha, revision_sha, str(source)),
        reference,
        data,
    )
    project.mkdir()
    if language == "python":
        initial_manifest = (
            '[project]\nname = "existing-python"\nversion = "0.1.0"\n'
            'requires-python = ">=3.14,<3.15"\n'
        )
    else:
        initial_manifest = (
            json.dumps(
                {
                    "name": "existing-typescript",
                    "private": True,
                    "type": "module",
                    "version": "0.1.0",
                },
                indent=2,
            )
            + "\n"
        )
    (project / "README.md").write_text("# Existing product\n", encoding="utf-8")
    (project / manifest_name).write_text(initial_manifest, encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, f"test: existing {language} product")

    arguments = [
        "adopt",
        str(project),
        "--source",
        str(source),
        "--to",
        revision_sha,
        "--allow-unreleased",
        "--data",
        f"language={language}",
        "--data",
        "coverage_mode=global",
    ]
    assert main([*arguments, "--dry-run"]) == 0
    plan_path = (
        tmp_path
        / f"existing-{language}-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 1
    )
    assert not (project / lock_name).exists()
    assert not (project / cli.PROVENANCE_FILE).exists()
    manifest = project / manifest_name
    if language == "python":
        manifest.write_text(
            (reference / manifest_name).read_text(encoding="utf-8")
            + "\n[tool.product]\npreserved = true\n",
            encoding="utf-8",
        )
    else:
        merged = json.loads(
            (reference / manifest_name).read_text(encoding="utf-8")
        )
        merged["productSetting"] = True
        manifest.write_text(
            json.dumps(merged, indent=2) + "\n", encoding="utf-8"
        )

    before = git(project, "status", "--porcelain")
    assert main(["adopt", str(project), "--finalize", "--dry-run"]) == 0
    assert git(project, "status", "--porcelain") == before
    assert not (project / lock_name).exists()
    assert (
        main(
            [
                "adopt",
                str(project),
                "--finalize",
                "--apply-plan",
                str(finalize_plan_path(project)),
                "--allow-unreleased",
                "--non-interactive",
                "--yes",
            ]
        )
        == 0
    )
    assert (project / lock_name).is_file()
    assert (project / cli.PROVENANCE_FILE).is_file()
    assert not (project / cli.PENDING_ADOPTION_FILE).exists()


def test_real_existing_adoption_updates_without_losing_product_decisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adopt and update a realistic product through two verified releases."""
    source = tmp_path / "controlled-release-source"
    copy_real_template(source)
    (source / "template" / "decision.txt").write_text(
        "template decision v1\n", encoding="utf-8"
    )
    lifecycle_version = source / "template" / "lifecycle-version.txt"
    lifecycle_version.write_text("lifecycle v1\n", encoding="utf-8")
    retired = source / "template" / "retired-after-v1.txt"
    retired.write_text("retire in v2\n", encoding="utf-8")
    first_sha = commit(source, "test: controlled release v1")
    releases = {"v1.0.0": first_sha}

    def verified_revision(
        source_value: str,
        requested: str | None,
        *,
        expected_sha: str | None = None,
        allow_unreleased: bool = False,
        client: cli.ReleaseClient | None = None,
    ) -> cli.Revision:
        del client
        assert source_value == str(source)
        assert allow_unreleased is False
        tag = requested or max(releases)
        sha = releases[tag]
        if expected_sha is not None and expected_sha != sha:
            raise CliError(
                "Expected commit SHA does not match the verified release."
            )
        return cli.Revision(
            tag,
            sha,
            str(source),
            cli.CANONICAL_REPOSITORY,
            cli.CANONICAL_REPOSITORY_ID,
            1 if tag == "v1.0.0" else 2,
            sha,
            True,
            True,
            True,
        )

    monkeypatch.setattr(cli, "resolve_revision", verified_revision)
    project = tmp_path / "existing CSARC-測試"
    data = cli.base_data(
        project,
        "adopt",
        {
            "language": "python",
            "project_name": "Product Identity",
            "project_slug": "product-identity",
        },
    )
    data["project_visibility"] = "private"
    reference = tmp_path / "reference-v1"
    reference.mkdir()
    cli.copier_copy(
        str(source),
        verified_revision(str(source), "v1.0.0", expected_sha=first_sha),
        reference,
        data,
    )
    (project / ".github" / "workflows").mkdir(parents=True)
    (project / "README.md").write_text("# Product README\n", encoding="utf-8")
    (project / "CHANGELOG.md").write_text(
        "# Product changes\n", encoding="utf-8"
    )
    (project / "AGENTS.md").write_text(
        "# Product agent rules\n\nKeep this rule.\n",
        encoding="utf-8",
    )
    (project / ".gitignore").write_bytes(b"product-cache/\n.env\n")
    product_release = project / ".github" / "workflows" / "release.yml"
    product_release.write_text(
        "name: Product release\n"
        "on: workflow_dispatch\n"
        "permissions: {}\n"
        "jobs:\n"
        "  release:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        '      - run: "true"\n',
        encoding="utf-8",
    )
    manifest = project / "pyproject.toml"
    manifest.write_text(
        (reference / "pyproject.toml").read_text(encoding="utf-8")
        + '\n[tool.product]\ndecision = "keep"\n',
        encoding="utf-8",
    )
    decision = project / "decision.txt"
    decision.write_text("product decision\n", encoding="utf-8")
    write_executable(
        project / "scripts" / "verify-product",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "grep -q '^# Product README$' README.md\n"
        "grep -q '^# Product changes$' CHANGELOG.md\n"
        "grep -q '^name: Product release$' .github/workflows/release.yml\n"
        "grep -q 'decision = \"keep\"' pyproject.toml\n"
        "grep -q '^version = 1$' uv.lock\n"
        "grep -q '^product decision$' decision.txt\n"
        "grep -q '^template decision v1$' decision.txt\n",
    )
    run(["uv", "lock", "--python", "3.14"], project)
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: product collision fixture")
    arguments = [
        "adopt",
        str(project),
        "--source",
        str(source),
        "--to",
        "v1.0.0",
        "--expected-sha",
        first_sha,
        "--data",
        "language=python",
        "--data",
        "project_name=Product Identity",
        "--data",
        "project_slug=product-identity",
    ]

    assert main(arguments) == 0
    plan_path = (
        tmp_path
        / "existing CSARC-測試-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    payload = cli.read_adoption_plan(plan_path)
    assert payload["template"]["verification"] == "verified"
    assert payload["files"]["manual_merge"] == [
        "decision.txt",
        "pyproject.toml",
    ]
    assert payload["files"]["unknown"] == []
    assert payload["files"]["automatic_merge"] == [".gitignore", "AGENTS.md"]
    assert "README.md" in payload["files"]["preserve"]
    assert "CHANGELOG.md" in payload["files"]["preserve"]
    assert ".github/workflows/release.yml" in payload["files"]["preserve"]
    assert ".github/workflows/csarc-release.yml" in payload["files"]["add"]
    assert payload["adoption"]["project_verification_hook"] == "configured"
    assert payload["adoption"]["verification"] == "deferred-manual-merge"

    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--yes",
                "--non-interactive",
            ]
        )
        == 1
    )
    decision.write_text(
        "product decision\ntemplate decision v1\n", encoding="utf-8"
    )
    assert main(["adopt", str(project), "--finalize"]) == 0
    assert (
        main(
            [
                "adopt",
                str(project),
                "--finalize",
                "--apply-plan",
                str(finalize_plan_path(project)),
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    )
    assert (project / ".github" / "workflows" / "csarc-release.yml").is_file()
    assert "Keep this rule." in (project / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    ignore_lines = (
        (project / ".gitignore").read_text(encoding="utf-8").splitlines()
    )
    assert ignore_lines[:2] == ["product-cache/", ".env"]
    assert ignore_lines.count(".env") == 1
    assert (
        project / "scripts" / "verify-product"
    ).stat().st_mode & stat.S_IXUSR

    finalize_plan = cli.read_adoption_plan(finalize_plan_path(project))
    finalize_artifacts = finalize_plan["adoption"]["artifacts"]
    for relative_name, digest in finalize_artifacts.items():
        assert cli.file_fingerprint(project / relative_name) == digest
    protected = {
        relative_name: (project / relative_name).read_bytes()
        for relative_name in (
            "README.md",
            "CHANGELOG.md",
            "AGENTS.md",
            ".gitignore",
            ".github/workflows/release.yml",
            "pyproject.toml",
            "uv.lock",
            "decision.txt",
            "scripts/verify-product",
        )
    }
    commit(project, "test: adopt controlled release v1")

    lifecycle_version.write_text("lifecycle v2\n", encoding="utf-8")
    retired.unlink()
    second_sha = commit(source, "test: controlled release v2")
    releases["v2.0.0"] = second_sha
    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                "v2.0.0",
                "--expected-sha",
                second_sha,
            ]
        )
        == 0
    )
    update_plan_path = lifecycle_plan_path(project, "update")
    update_plan = cli.read_machine_plan(update_plan_path)
    transaction = update_plan["transaction"]
    assert transaction["verification"] == "passed"
    assert update_plan["template"]["sha"] == second_sha
    assert update_plan["files"]["delete"] == ["retired-after-v1.txt"]
    assert "retired-after-v1.txt" not in update_plan["files"]["preserve"]
    assert set(transaction["artifacts"]) == (
        set(update_plan["files"]["add"])
        | set(update_plan["files"]["overwrite"])
        | set(update_plan["files"]["automatic_merge"])
    )
    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(update_plan_path),
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    )

    for relative_name, content in protected.items():
        assert (project / relative_name).read_bytes() == content
    assert (project / "lifecycle-version.txt").read_text(encoding="utf-8") == (
        "lifecycle v2\n"
    )
    assert not (project / "retired-after-v1.txt").exists()
    for relative_name, digest in transaction["artifacts"].items():
        assert cli.file_fingerprint(project / relative_name) == digest
    provenance = json.loads(
        (project / cli.PROVENANCE_FILE).read_text(encoding="utf-8")
    )
    assert provenance["release_tag"] == "v2.0.0"
    assert provenance["commit_sha"] == second_sha
    assert provenance["previous"]["release_tag"] == "v1.0.0"
    assert provenance["previous"]["commit_sha"] == first_sha


def test_adoption_report_classifies_unknown_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report text collisions separately from unknown binary collisions."""
    source, _ = make_template(tmp_path)
    (source / "template" / "binary.dat").write_bytes(b"template\0binary")
    (source / "template" / "same.txt").write_text(
        "identical\n", encoding="utf-8"
    )
    revision = commit(source, "test: add report classification fixtures")
    project = tmp_path / "collision-product"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "collision-product"\n', encoding="utf-8"
    )
    (project / "managed.txt").write_text("product content\n", encoding="utf-8")
    (project / "binary.dat").write_bytes(b"product\0binary")
    (project / "same.txt").write_text("identical\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: collision product")
    report_dir = tmp_path / "reports"
    arguments = [
        "adopt",
        str(project),
        "--source",
        str(source),
        "--to",
        revision,
        "--allow-unreleased",
        "--dry-run",
        "--report-dir",
        str(report_dir),
    ]

    before = git(project, "status", "--porcelain")
    assert main(arguments) == 0
    output = capsys.readouterr().out
    assert (
        f"Markdown report: {report_dir / 'csarc-adoption-dry-run.md'}" in output
    )
    assert f"PDF report: {report_dir / 'csarc-adoption-dry-run.pdf'}" in output
    report = (report_dir / "csarc-adoption-dry-run.md").read_text(
        encoding="utf-8"
    )
    assert "Decision: Unable to determine" in report
    assert "- Repository: `(none)`" in report
    assert "- Repository visibility: `private` (`safe-default`)" in report
    assert f"- Template source: `{source}`" in report
    assert (
        "`managed.txt` - template and repository contain different UTF-8 text"
        in report
    )
    assert (
        "`binary.dat` - file type, executable bit, link target, or non-text "
        "content differs" in report
    )
    assert "| Preserve | 1 |" in report
    assert "| Manual merge | 2 |" in report
    assert "| Unable to determine | 1 |" in report
    pdf_text = (
        PdfReader(report_dir / "csarc-adoption-dry-run.pdf")
        .pages[0]
        .extract_text()
    )
    assert "Unable to determine" in pdf_text
    assert "binary.dat" in pdf_text
    assert "Repository" in pdf_text and "(none)" in pdf_text
    assert "Visibility" in pdf_text and "private (safe-default)" in pdf_text
    assert "Template source" in pdf_text
    assert git(project, "status", "--porcelain") == before


def test_adoption_report_failure_keeps_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A PDF failure leaves the useful Markdown report and target untouched."""
    source, revision = make_template(tmp_path)
    project = tmp_path / "report-failure-product"
    project.mkdir()
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    (project / "README.md").write_text("product\n", encoding="utf-8")
    commit(project, "test: report failure product")
    report_dir = tmp_path / "failed-report"

    arguments = [
        "adopt",
        str(project),
        "--source",
        str(source),
        "--to",
        revision,
        "--allow-unreleased",
        "--dry-run",
        "--report-dir",
        str(report_dir),
    ]
    assert main(arguments) == 0
    assert (report_dir / "csarc-adoption-dry-run.pdf").is_file()
    capsys.readouterr()

    def fail_pdf(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("fixture PDF failure")

    monkeypatch.setattr(cli, "draw_adoption_pdf", fail_pdf)
    before = git(project, "status", "--porcelain")
    assert main(arguments) == 0
    output = capsys.readouterr()
    assert "machine plan remain usable" in output.err
    assert "PDF report:" not in output.out
    assert (report_dir / "csarc-adoption-dry-run.md").is_file()
    assert not (report_dir / "csarc-adoption-dry-run.pdf").exists()
    assert (report_dir / cli.ADOPTION_PLAN_BASENAME).is_file()
    assert git(project, "status", "--porcelain") == before


@pytest.mark.parametrize(
    "temporary_name",
    [
        f"{cli.ADOPTION_REPORT_BASENAME}.md.tmp",
        f"{cli.ADOPTION_REPORT_BASENAME}.pdf.tmp",
        cli.ADOPTION_PLAN_BASENAME.replace(".json", ".json.tmp"),
    ],
)
def test_adoption_reports_ignore_predictable_temporary_symlinks(
    tmp_path: Path,
    temporary_name: str,
) -> None:
    """Never truncate a victim through a predictable report temporary path."""
    source, revision = make_template(tmp_path)
    project = tmp_path / "report-symlink-product"
    project.mkdir()
    (project / "product.txt").write_text("product\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: report symlink product")
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("do not replace\n", encoding="utf-8")
    planted = report_dir / temporary_name
    planted.symlink_to(victim)

    assert (
        main(
            [
                "adopt",
                str(project),
                "--source",
                str(source),
                "--to",
                revision,
                "--allow-unreleased",
                "--dry-run",
                "--report-dir",
                str(report_dir),
            ]
        )
        == 0
    )

    assert victim.read_text(encoding="utf-8") == "do not replace\n"
    assert planted.is_symlink()
    for name in (
        f"{cli.ADOPTION_REPORT_BASENAME}.md",
        f"{cli.ADOPTION_REPORT_BASENAME}.pdf",
        cli.ADOPTION_PLAN_BASENAME,
    ):
        output = report_dir / name
        assert output.is_file()
        assert not output.is_symlink()


def test_adoption_report_path_and_settings_are_safe(tmp_path: Path) -> None:
    """Keep reports outside the repo and omit arbitrary Copier data values."""
    project = (tmp_path / "product").resolve()
    project.mkdir()
    with pytest.raises(CliError, match="outside the target repo"):
        cli.adoption_report_directory(project, project / "reports")
    settings = cli.report_settings(
        {"language": "python", "coverage_mode": "diff", "api_token": "secret"}
    )
    assert "language=python" in settings
    assert "coverage_mode=diff" in settings
    assert "api_token" not in settings
    assert "secret" not in settings


@pytest.mark.parametrize(
    ("context", "repository_line", "visibility_line"),
    [
        (
            cli.RepositoryContext(
                "owner/repo",
                "owner",
                "Organization",
                "public",
                "github",
                True,
            ),
            "- Repository: `owner/repo`",
            "- Repository visibility: `public` (`github`)",
        ),
        (
            cli.RepositoryContext(
                "owner/repo",
                "owner",
                None,
                "internal",
                "explicit",
                False,
            ),
            "- Repository: `owner/repo`",
            "- Repository visibility: `internal` (`explicit`)",
        ),
        (
            cli.RepositoryContext(
                None,
                None,
                None,
                "private",
                "safe-default",
                False,
            ),
            "- Repository: `(none)`",
            "- Repository visibility: `private` (`safe-default`)",
        ),
    ],
)
def test_adoption_markdown_reports_repository_context(
    tmp_path: Path,
    context: cli.RepositoryContext,
    repository_line: str,
    visibility_line: str,
) -> None:
    """Record GitHub, explicit, and no-origin report context."""
    source = "https://example.invalid/template.git"
    report = cli.adoption_report_markdown(
        tmp_path,
        cli.Revision("v1.0.0", "a" * 40, source),
        context,
        {"language": "ci"},
        cli.Plan((), (), (), (), (), ()),
        "2026-08-24T00:00:00+00:00",
    )

    assert repository_line in report
    assert visibility_line in report
    assert f"- Template source: `{source}`" in report


def test_adopt_help_describes_report_directory(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Expose the report output option in the public CLI help."""
    with pytest.raises(SystemExit) as error:
        cli.parser().parse_args(["adopt", "--help"])
    assert error.value.code == 0
    help_text = capsys.readouterr().out
    assert "--apply-plan PATH" in help_text
    assert "--finalize" in help_text
    assert "--report-dir PATH" in help_text
    assert "plan without writing (the default for lifecycle" in help_text


def test_adopt_reports_dirty_tree_without_mutating_it(tmp_path: Path) -> None:
    """Dirty adoption plans remain useful but cannot be applied."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "dirty-product"
    project.mkdir()
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    (project / "tracked.txt").write_text("clean\n", encoding="utf-8")
    commit(project, "test: baseline")
    (project / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    before = git(project, "status", "--porcelain")
    assert (
        main(
            [
                "adopt",
                str(project),
                "--source",
                str(source),
                "--to",
                first_sha,
                "--allow-unreleased",
                "--dry-run",
            ]
        )
        == 0
    )
    plan = (
        tmp_path
        / "dirty-product-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    payload = json.loads(plan.read_text(encoding="utf-8"))
    assert payload["adoption"]["applicable"] is False
    assert payload["adoption"]["clean"] is False
    assert payload["adoption"]["target_changes"] == ["?? untracked.txt"]
    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(plan),
                "--allow-unreleased",
                "--yes",
            ]
        )
        == 2
    )
    assert git(project, "status", "--porcelain") == before
    assert not (project / ".copier-answers.yml").exists()


def test_adopt_infers_unicode_repository_and_applies_exact_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Infer the Git root and count provenance in a portable exact plan."""
    source, revision = make_template(tmp_path)
    project = tmp_path / "product with space-測試"
    nested = project / "nested folder" / "子目錄"
    nested.mkdir(parents=True)
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    (project / "product.txt").write_text("product\n", encoding="utf-8")
    commit(project, "test: unicode product")
    monkeypatch.chdir(nested)

    arguments = [
        "adopt",
        "--source",
        str(source),
        "--to",
        revision,
        "--allow-unreleased",
        "--dry-run",
    ]
    assert main(arguments) == 0
    plan_path = (
        project.parent
        / f"{project.name}-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["target"] == str(project)
    assert cli.PROVENANCE_FILE.as_posix() in payload["files"]["add"]
    assert payload["adoption"]["artifacts"][cli.PROVENANCE_FILE.as_posix()]

    assert main(["adopt", "--apply-plan", str(plan_path)]) == 2
    assert "requires --allow-unreleased again" in capsys.readouterr().err

    assert (
        main(
            [
                "adopt",
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    )
    assert (project / cli.PROVENANCE_FILE).is_file()


def test_adopt_rejects_plan_tampering_and_target_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse a changed plan or HEAD without writing generated files."""
    source, revision = make_template(tmp_path)
    project = tmp_path / "drift-product"
    project.mkdir()
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    (project / "product.txt").write_text("product\n", encoding="utf-8")
    commit(project, "test: baseline")
    arguments = [
        "adopt",
        str(project),
        "--source",
        str(source),
        "--to",
        revision,
        "--allow-unreleased",
        "--dry-run",
    ]
    assert main(arguments) == 0
    plan_path = (
        tmp_path
        / "drift-product-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    original = plan_path.read_text(encoding="utf-8")
    plan_path.write_text(
        original.replace('"mode": "adopt"', '"mode": "init"'),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert "digest does not match" in capsys.readouterr().err
    assert not (project / "managed.txt").exists()

    plan_path.write_text(original, encoding="utf-8")
    (project / "product.txt").write_text("new product\n", encoding="utf-8")
    commit(project, "test: move target head")
    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    error = capsys.readouterr().err
    assert "drifted after dry-run" in error
    assert "$.adoption.target_head" in error
    assert not (project / "managed.txt").exists()


def test_json_differences_reports_paths_and_values() -> None:
    """Explain plan drift at the exact JSON leaves that changed."""
    assert cli.json_differences(
        {"artifacts": {"managed.txt": "old"}, "files": ["a"]},
        {"artifacts": {"managed.txt": "new"}, "files": ["a", "b"]},
    ) == (
        "$.artifacts.managed.txt: saved='old', rebuilt='new'",
        "$.files.length: saved=1, rebuilt=2",
    )


def test_adopt_rechecks_target_after_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject target drift introduced while confirmation is pending."""
    source, revision = make_template(tmp_path)
    project = tmp_path / "confirmation-drift-product"
    project.mkdir()
    product = project / "product.txt"
    product.write_text("reviewed\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: baseline")
    arguments = [
        "adopt",
        str(project),
        "--source",
        str(source),
        "--to",
        revision,
        "--allow-unreleased",
        "--data",
        "language=ci",
    ]
    assert main([*arguments, "--dry-run"]) == 0

    def drift_during_confirmation(_: str) -> str:
        product.write_text("changed while waiting\n", encoding="utf-8")
        return "yes"

    monkeypatch.setattr("builtins.input", drift_during_confirmation)
    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(finalize_plan_path(project)),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert "changed after the plan was created or confirmed" in (
        capsys.readouterr().err
    )
    assert product.read_bytes() == b"changed while waiting\n"
    assert not (project / "managed.txt").exists()
    assert not (project / cli.PROVENANCE_FILE).exists()


def test_adopt_rechecks_repository_context_after_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject repository context drift while apply waits for approval."""
    source, revision = make_template(tmp_path)
    project = tmp_path / "context-drift-product"
    project.mkdir()
    (project / "product.txt").write_text("product\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: context drift product")
    arguments = [
        "adopt",
        str(project),
        "--source",
        str(source),
        "--to",
        revision,
        "--allow-unreleased",
        "--data",
        "language=ci",
    ]
    assert main([*arguments, "--dry-run"]) == 0
    stable = cli.RepositoryContext(
        None,
        None,
        None,
        "private",
        "safe-default",
        False,
        "No GitHub origin or GH_REPO was found.",
    )
    current = [stable]
    monkeypatch.setattr(
        cli, "repository_context", lambda *args, **kwargs: current[0]
    )

    def drift_during_confirmation(_: str) -> str:
        current[0] = cli.RepositoryContext(
            "different/repository",
            "different",
            "organization",
            "public",
            "github",
            True,
        )
        return "yes"

    monkeypatch.setattr("builtins.input", drift_during_confirmation)
    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(finalize_plan_path(project)),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert "Repository context changed" in capsys.readouterr().err
    assert not (project / "managed.txt").exists()
    assert not (project / cli.PROVENANCE_FILE).exists()


def test_candidate_patch_rejects_unplanned_effects(tmp_path: Path) -> None:
    """Apply only the artifact set recorded by the fresh verified plan."""
    project = tmp_path / "patch-target"
    project.mkdir()
    (project / "product.txt").write_text("product\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: baseline")
    candidate = tmp_path / "patch-candidate"
    cli.clone_target(project, candidate)
    planned = candidate / "planned.txt"
    planned.write_text("planned\n", encoding="utf-8")
    (candidate / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    head, changes, _ = cli.target_state(project)

    with pytest.raises(CliError, match="effects differ"):
        cli.write_candidate_patch(
            candidate,
            project,
            tmp_path / "candidate.patch",
            artifacts={"planned.txt": cli.file_fingerprint(planned)},
            target_snapshot={
                "target_head": head,
                "target_changes": list(changes),
                "target_files": cli.target_file_snapshot(project),
            },
        )

    assert not (project / "planned.txt").exists()
    assert not (project / "unexpected.txt").exists()


def test_candidate_patch_rolls_back_after_late_external_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Undo only CLI writes when an unplanned path races with git apply."""
    project = tmp_path / "race-target"
    project.mkdir()
    managed = project / "managed.txt"
    product = project / "product.txt"
    managed.write_text("managed v1\n", encoding="utf-8")
    product.write_text("product v1\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: baseline")
    candidate = tmp_path / "race-candidate"
    cli.clone_target(project, candidate)
    candidate_managed = candidate / "managed.txt"
    candidate_managed.write_text("managed v2\n", encoding="utf-8")
    patch_path = tmp_path / "race.patch"
    snapshot = cli.repository_snapshot(project)
    original_run = cli.run
    raced = False

    def run_with_late_race(
        command: list[str],
        *,
        cwd: Path | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal raced
        result = original_run(command, cwd=cwd, capture=capture, check=check)
        if (
            not raced
            and command[:5] == ["git", "-C", str(project), "apply", "-p2"]
            and "--check" not in command
            and "-R" not in command
        ):
            product.write_text("external race\n", encoding="utf-8")
            raced = True
        return result

    monkeypatch.setattr(cli, "run", run_with_late_race)
    with pytest.raises(CliError, match="CLI changes were rolled back"):
        cli.write_candidate_patch(
            candidate,
            project,
            patch_path,
            artifacts={"managed.txt": cli.file_fingerprint(candidate_managed)},
            target_snapshot=snapshot,
        )

    assert raced is True
    assert managed.read_text(encoding="utf-8") == "managed v1\n"
    assert product.read_text(encoding="utf-8") == "external race\n"


def test_failed_project_hook_leaves_target_unchanged(tmp_path: Path) -> None:
    """Run the project hook in the candidate and keep target bytes unchanged."""
    source, revision = make_template(tmp_path)
    project = tmp_path / "hook-product"
    project.mkdir()
    write_executable(
        project / "scripts" / "verify-product",
        "#!/usr/bin/env bash\nset -euo pipefail\nexit 23\n",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: failing product hook")
    before = git(project, "status", "--porcelain")

    assert (
        main(
            [
                "adopt",
                str(project),
                "--source",
                str(source),
                "--to",
                revision,
                "--allow-unreleased",
                "--dry-run",
            ]
        )
        == 0
    )
    plan_path = (
        tmp_path
        / "hook-product-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["adoption"]["applicable"] is False
    assert payload["adoption"]["project_verification_hook"] == "configured"
    assert str(payload["adoption"]["verification"]).startswith("failed:")
    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert git(project, "status", "--porcelain") == before
    assert not (project / "managed.txt").exists()


def test_adopt_dry_run_rejects_csarc_symlink_without_external_writes(
    tmp_path: Path,
) -> None:
    """Never follow a repository-controlled .csarc directory symlink."""
    source, revision = make_template(tmp_path)
    external = tmp_path / "external-state"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    project = tmp_path / "symlinked-state-product"
    project.mkdir()
    (project / ".csarc").symlink_to(external, target_is_directory=True)
    (project / "product.txt").write_text("product\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: repository-controlled state symlink")
    before = cli.target_file_snapshot(project)

    assert (
        main(
            [
                "adopt",
                str(project),
                "--source",
                str(source),
                "--to",
                revision,
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert cli.target_file_snapshot(project) == before
    assert sentinel.read_text(encoding="utf-8") == "unchanged\n"
    assert not (external / "provenance.json").exists()
    assert not (external / "adoption-pending.json").exists()
    assert not (
        tmp_path / "symlinked-state-product-csarc-adoption-report"
    ).exists()


def test_fixed_merges_preserve_product_content_and_crlf() -> None:
    """Apply only deterministic AGENTS and gitignore ownership policies."""
    generated = f"{cli.AGENTS_BLOCK_START}\nmanaged\n{cli.AGENTS_BLOCK_END}\n"
    existing = "# Product rules\r\n\r\nKeep this.\r\n"
    merged = cli.merge_agents_file(existing, generated)
    assert merged.startswith(existing.rstrip("\r\n"))
    assert "\n" not in merged.replace("\r\n", "")
    assert "Keep this." in merged
    assert "managed" in merged

    ignored = cli.merge_gitignore("dist/\r\n.env\r\n", ".env\n.venv/\n")
    assert ignored == "dist/\r\n.env\r\n\r\n.venv/\r\n"


@pytest.mark.parametrize("name", ["AGENTS.md", ".gitignore"])
def test_adoption_policies_do_not_follow_final_symlinks(
    tmp_path: Path, name: str
) -> None:
    """Leave final symlinks for unknown-file review without reading them."""
    stage = tmp_path / "stage"
    target = tmp_path / "target"
    stage.mkdir()
    target.mkdir()
    generated = (
        f"{cli.AGENTS_BLOCK_START}\ngenerated\n{cli.AGENTS_BLOCK_END}\n"
        if name == "AGENTS.md"
        else "generated ignore\n"
    )
    (stage / name).write_text(generated, encoding="utf-8")
    external = tmp_path / f"external-{name.lstrip('.')}"
    external.write_text(f"external {name}\n", encoding="utf-8")
    (target / name).symlink_to(external)

    merged = cli.apply_adoption_policies(stage, target)
    plan = cli.compare_stage(stage, target, adopt=True, merged_paths=merged)

    assert merged == ()
    assert plan.unknown == (name,)
    assert (stage / name).read_text(encoding="utf-8") == generated
    assert external.read_text(encoding="utf-8") == f"external {name}\n"


def test_compare_stage_includes_file_traits_without_following_links(
    tmp_path: Path,
) -> None:
    """Classify mode and link drift without dereferencing dangling links."""
    stage = tmp_path / "stage"
    target = tmp_path / "target"
    stage.mkdir()
    target.mkdir()
    write_executable(stage / "mode.txt", "same text\n")
    (target / "mode.txt").write_text("same text\n", encoding="utf-8")
    (stage / "link-target").write_text("template\n", encoding="utf-8")
    (target / "link-target").symlink_to("missing-product-target")
    (stage / "link-drift").symlink_to("template-target")
    (target / "link-drift").symlink_to("product-target")

    plan = cli.compare_stage(stage, target, adopt=True)

    assert plan.manual == ("mode.txt",)
    assert plan.unknown == ("link-drift", "link-target")


@pytest.mark.parametrize(
    ("collision", "unknown_path"),
    [
        ("target-directory", "collision"),
        ("target-file-ancestor", "collision/managed.txt"),
        (
            "target-multilevel-file-ancestor",
            "collision/nested/managed.txt",
        ),
    ],
)
def test_adopt_reports_file_directory_collisions_without_writes(
    tmp_path: Path,
    collision: str,
    unknown_path: str,
) -> None:
    """Classify file-directory collisions before building a candidate."""
    source, _ = make_template(tmp_path)
    project = tmp_path / collision
    project.mkdir()
    if collision == "target-directory":
        (source / "template" / "collision").write_text(
            "template file\n", encoding="utf-8"
        )
        (project / "collision").mkdir()
        (project / "collision" / "owned.txt").write_text(
            "owned\n", encoding="utf-8"
        )
    else:
        managed = source / "template" / unknown_path
        managed.parent.mkdir(parents=True)
        managed.write_text("template file\n", encoding="utf-8")
        (project / "collision").write_text("owned\n", encoding="utf-8")
    revision = commit(source, "test: add file directory collision")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: collision product")
    before = cli.target_file_snapshot(project)
    status = git(project, "status", "--porcelain")
    report_dir = tmp_path / f"{collision}-report"

    assert (
        main(
            [
                "adopt",
                str(project),
                "--source",
                str(source),
                "--to",
                revision,
                "--allow-unreleased",
                "--dry-run",
                "--report-dir",
                str(report_dir),
            ]
        )
        == 0
    )

    report = (report_dir / f"{cli.ADOPTION_REPORT_BASENAME}.md").read_text(
        encoding="utf-8"
    )
    assert f"`{unknown_path}`" in report
    assert "directory, ancestor, or special-file collision" in report
    assert cli.target_file_snapshot(project) == before
    assert git(project, "status", "--porcelain") == status


def test_adopt_dry_run_rejects_symlink_ancestor_without_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Never render a planned child through a repository symlink."""
    source, _ = make_template(tmp_path)
    nested = source / "template" / "linked" / "managed.txt"
    nested.parent.mkdir()
    nested.write_text("template content\n", encoding="utf-8")
    revision = commit(source, "test: add nested managed file")
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / "managed.txt"
    external.write_text("external content\n", encoding="utf-8")
    project = tmp_path / "symlink-ancestor-product"
    project.mkdir()
    (project / "linked").symlink_to(outside)
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: symlink ancestor")
    before = cli.target_file_snapshot(project)

    assert (
        main(
            [
                "adopt",
                str(project),
                "--source",
                str(source),
                "--to",
                revision,
                "--allow-unreleased",
                "--dry-run",
            ]
        )
        == 2
    )

    assert "symlink or non-directory ancestor" in capsys.readouterr().err
    assert cli.target_file_snapshot(project) == before
    assert external.read_bytes() == b"external content\n"


def test_native_windows_stops_with_wsl2_guidance(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail before filesystem work when invoked from native Windows."""
    monkeypatch.setattr(cli.sys, "platform", "win32")
    assert main(["adopt", "--dry-run"]) == 2
    assert "WSL2" in capsys.readouterr().err


def test_code_owner_verification_distinguishes_team_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinguish verified, missing, and unreadable teams."""
    repository = cli.RepositoryContext(
        "Innoguard-Cyber-Arch/product",
        "Innoguard-Cyber-Arch",
        "Organization",
        "private",
        "github",
        True,
    )
    monkeypatch.setattr(
        cli,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout="arch\n", stderr=""
        ),
    )
    assert (
        cli.code_owner_verification(repository, "@Innoguard-Cyber-Arch/arch")[
            "state"
        ]
        == "verified"
    )
    assert (
        cli.code_owner_verification(
            repository, "@Innoguard-Cyber-Arch/missing"
        )["state"]
        == "blocked"
    )

    monkeypatch.setattr(
        cli,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout="", stderr="not authorized"
        ),
    )
    unknown = cli.code_owner_verification(
        repository, "@Innoguard-Cyber-Arch/arch"
    )
    assert unknown["state"] == "unknown"
    assert unknown["reason"] == "not authorized"


def test_adoption_preserves_executable_and_checked_patch_symlink(
    tmp_path: Path,
) -> None:
    """Keep portable filesystem traits through the checked candidate patch."""
    source, _ = make_template(tmp_path)
    write_executable(
        source / "template" / "scripts" / "managed-tool",
        "#!/usr/bin/env bash\nset -euo pipefail\n",
    )
    (source / "template" / "managed-link").symlink_to("managed.txt")
    revision = commit(source, "test: add filesystem traits")
    project = tmp_path / "filesystem-product"
    project.mkdir()
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    (project / "product.txt").write_text("product\n", encoding="utf-8")
    commit(project, "test: filesystem product")

    assert (
        main(
            [
                "adopt",
                str(project),
                "--source",
                str(source),
                "--to",
                revision,
                "--allow-unreleased",
                "--dry-run",
            ]
        )
        == 0
    )
    plan_path = (
        tmp_path
        / "filesystem-product-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    )
    assert (project / "managed-link").read_text(encoding="utf-8") == (
        "template version one\n"
    )
    assert (project / "scripts" / "managed-tool").stat().st_mode & stat.S_IXUSR

    candidate = tmp_path / "symlink-candidate"
    cli.clone_target(project, candidate)
    (candidate / "portable-link").symlink_to("product.txt")
    target_head, target_changes, _ = cli.target_state(project)
    cli.write_candidate_patch(
        candidate,
        project,
        tmp_path / "symlink.patch",
        artifacts={
            "portable-link": cli.file_fingerprint(candidate / "portable-link")
        },
        target_snapshot={
            "target_head": target_head,
            "target_changes": list(target_changes),
            "target_files": cli.target_file_snapshot(project),
        },
    )
    assert (project / "portable-link").is_symlink()
    assert (project / "portable-link").readlink() == Path("product.txt")


def test_update_check_dry_run_apply_and_conflict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercise status, dry-run, smart update, and conflict handling."""
    source, project, _ = initialize_project(tmp_path)
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: generated project")

    managed = source / "template" / "managed.txt"
    managed.write_text("template version two\n", encoding="utf-8")
    second_sha = commit(source, "test: template version two")

    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                second_sha,
                "--allow-unreleased",
                "--check",
                "--json",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out.strip().splitlines()[-1]
    status = json.loads(output)
    assert status["target_sha"] == second_sha
    assert status["status"] == "outdated"

    before = git(project, "status", "--porcelain")
    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                second_sha,
                "--allow-unreleased",
                "--dry-run",
            ]
        )
        == 0
    )
    assert git(project, "status", "--porcelain") == before
    assert managed.read_text(encoding="utf-8") == "template version two\n"
    plan_path = lifecycle_plan_path(project, "update")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["transaction"]["verification"] == "passed"
    capsys.readouterr()

    before_apply = cli.target_file_snapshot(project)
    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(plan_path),
            ]
        )
        == 2
    )
    assert "--allow-unreleased again" in capsys.readouterr().err
    assert cli.target_file_snapshot(project) == before_apply
    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    )
    assert (project / "managed.txt").read_text() == "template version two\n"
    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                second_sha,
                "--allow-unreleased",
                "--check",
            ]
        )
        == 0
    )
    commit(project, "test: update to version two")

    (project / "managed.txt").write_text(
        "project customization\n", encoding="utf-8"
    )
    commit(project, "test: customize managed file")
    managed.write_text("template version three\n", encoding="utf-8")
    third_sha = commit(source, "test: template version three")
    before_content = (project / "managed.txt").read_text(encoding="utf-8")

    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                third_sha,
                "--allow-unreleased",
            ]
        )
        == 0
    )
    failed_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert failed_plan["transaction"]["applicable"] is False
    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert (project / "managed.txt").read_text(
        encoding="utf-8"
    ) == before_content


def test_update_rechecks_committed_head_after_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject a clean committed target change made during confirmation."""
    source, project, _ = initialize_project(tmp_path)
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    (project / "product.txt").write_text("before\n", encoding="utf-8")
    commit(project, "test: generated project")
    (source / "template" / "managed.txt").write_text(
        "template version two\n", encoding="utf-8"
    )
    revision = commit(source, "test: template version two")

    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                revision,
                "--allow-unreleased",
            ]
        )
        == 0
    )

    def drift_during_confirmation(_: str) -> str:
        (project / "product.txt").write_text("after\n", encoding="utf-8")
        commit(project, "test: concurrent product change")
        return "yes"

    monkeypatch.setattr("builtins.input", drift_during_confirmation)
    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(lifecycle_plan_path(project, "update")),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert "Repository changed" in capsys.readouterr().err
    assert (project / "managed.txt").read_text(encoding="utf-8") == (
        "template version one\n"
    )


def test_update_rechecks_repository_context_after_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject repository origin or visibility drift before Copier writes."""
    source, project, _ = initialize_project(tmp_path)
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: generated project")
    (source / "template" / "managed.txt").write_text(
        "template version two\n", encoding="utf-8"
    )
    revision = commit(source, "test: template version two")
    stable = cli.RepositoryContext(
        "owner/repository",
        "owner",
        "organization",
        "private",
        "github",
        True,
    )
    current = [stable]
    monkeypatch.setattr(
        cli, "repository_context", lambda *args, **kwargs: current[0]
    )

    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                revision,
                "--allow-unreleased",
            ]
        )
        == 0
    )

    def drift_during_confirmation(_: str) -> str:
        current[0] = cli.RepositoryContext(
            "different/repository",
            "different",
            "organization",
            "public",
            "github",
            True,
        )
        return "yes"

    monkeypatch.setattr("builtins.input", drift_during_confirmation)
    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(lifecycle_plan_path(project, "update")),
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert "Repository context changed" in capsys.readouterr().err
    assert (project / "managed.txt").read_text(encoding="utf-8") == (
        "template version one\n"
    )


def test_update_rechecks_snapshot_after_repository_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject target drift introduced while repository context is refreshed."""
    source, project, _ = initialize_project(tmp_path)
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    product = project / "product.txt"
    product.write_text("before\n", encoding="utf-8")
    commit(project, "test: generated project")
    (source / "template" / "managed.txt").write_text(
        "template version two\n", encoding="utf-8"
    )
    revision = commit(source, "test: template version two")
    stable = cli.RepositoryContext(
        "owner/repository",
        "owner",
        "organization",
        "private",
        "github",
        True,
    )
    monkeypatch.setattr(
        cli, "repository_context", lambda *args, **kwargs: stable
    )
    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                revision,
                "--allow-unreleased",
            ]
        )
        == 0
    )
    calls = 0

    def context_with_target_drift(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            product.write_text("after\n", encoding="utf-8")
            commit(project, "test: context-query product change")
        return stable

    monkeypatch.setattr(cli, "repository_context", context_with_target_drift)
    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(lifecycle_plan_path(project, "update")),
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 2
    )
    assert calls == 2
    assert "Repository changed" in capsys.readouterr().err
    assert (project / "managed.txt").read_text(encoding="utf-8") == (
        "template version one\n"
    )


def test_update_replay_rejects_source_answers_and_rendered_output_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep every replay input external until the saved plan still matches."""
    source, project, _ = initialize_project(tmp_path)
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: generated project")
    (source / "template" / "managed.txt").write_text(
        "template version two\n", encoding="utf-8"
    )
    revision = commit(source, "test: template version two")
    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                revision,
                "--allow-unreleased",
            ]
        )
        == 0
    )
    plan_path = lifecycle_plan_path(project, "update")
    apply_arguments = [
        "update",
        str(project),
        "--apply-plan",
        str(plan_path),
        "--allow-unreleased",
        "--yes",
        "--non-interactive",
    ]
    baseline = cli.target_file_snapshot(project)

    unavailable = tmp_path / "template-source-unavailable"
    source.rename(unavailable)
    assert main(apply_arguments) == 2
    assert cli.target_file_snapshot(project) == baseline
    unavailable.rename(source)

    answers_path = project / ".copier-answers.yml"
    original_answers = answers_path.read_bytes()
    answers_path.write_bytes(original_answers + b"project_name: Drifted\n")
    drifted = cli.target_file_snapshot(project)
    assert main(apply_arguments) == 2
    assert cli.target_file_snapshot(project) == drifted
    answers_path.write_bytes(original_answers)
    assert git(project, "status", "--porcelain") == ""

    original_prepare = cli.prepare_update_candidate

    def render_drift(
        target: Path,
        candidate: Path,
        target_revision: cli.Revision,
        previous: dict[str, object] | None,
        update_data: Mapping[str, str],
        generated_at: str,
    ) -> tuple[cli.Plan, dict[str, str], tuple[str, ...], str]:
        result = original_prepare(
            target,
            candidate,
            target_revision,
            previous,
            update_data,
            generated_at,
        )
        effects, artifacts, deleted, verification = result
        managed = candidate / "managed.txt"
        managed.write_text("rendered drift\n", encoding="utf-8")
        artifacts = dict(artifacts)
        artifacts["managed.txt"] = cli.file_fingerprint(managed)
        return effects, artifacts, deleted, verification

    capsys.readouterr()
    with monkeypatch.context() as context:
        context.setattr(cli, "prepare_update_candidate", render_drift)
        assert main(apply_arguments) == 2
    assert "rendered output drifted" in capsys.readouterr().err
    assert cli.target_file_snapshot(project) == baseline

    assert main(apply_arguments) == 0
    assert (project / "managed.txt").read_text(encoding="utf-8") == (
        "template version two\n"
    )


def test_update_recomputes_visibility_defaults_from_github(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Migrate stale private defaults when GitHub reports a public repo."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "public-project"
    apply_init(
        [
            "init",
            str(project),
            "--source",
            str(source),
            "--to",
            first_sha,
            "--allow-unreleased",
            "--data",
            "language=python",
        ],
        project,
    )
    capsys.readouterr()
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: generated private defaults")
    monkeypatch.setattr(
        cli,
        "repository_context",
        lambda *args, **kwargs: cli.RepositoryContext(
            "owner/repo",
            "owner",
            "organization",
            "public",
            "github",
            True,
        ),
    )

    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                first_sha,
                "--allow-unreleased",
                "--check",
                "--json",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "outdated"
    assert payload["update_available"] is True
    assert payload["answers_changed"] is True
    assert payload["answers"]["project_visibility"] == "public"
    assert payload["answers"]["enable_codeql"] is True
    assert payload["answers"]["enable_release_attestations"] is True


def test_update_plan_resolves_target_answers_and_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Build update output from the target template, not installed answers."""
    source, project, _ = initialize_project(tmp_path)
    capsys.readouterr()
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    git(
        project,
        "remote",
        "add",
        "origin",
        "https://github.com/owner/repository.git",
    )
    commit(project, "test: generated project")
    copier_config = source / "copier.yml"
    copier_config.write_text(
        copier_config.read_text(encoding="utf-8")
        + "new_target_answer:\n  type: str\n  default: target-default\n",
        encoding="utf-8",
    )
    write_executable(
        source / "template" / "scripts" / "release_policy.py",
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'mode': 'target', 'capabilities': {}}))\n",
    )
    second_sha = commit(source, "test: add target answer and capability")
    monkeypatch.setattr(
        cli,
        "repository_context",
        lambda *args, **kwargs: cli.RepositoryContext(
            "owner/repository",
            "owner",
            "organization",
            "private",
            "github",
            True,
        ),
    )

    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                second_sha,
                "--allow-unreleased",
                "--check",
                "--json",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["answers"]["new_target_answer"] == "target-default"
    assert payload["release_capabilities"]["mode"] == "target"
    assert payload["capabilities_changed"] is True


def test_update_check_reports_capability_drift_at_same_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Treat target-policy drift as an available update without a new SHA."""
    _source, project, first_sha = initialize_project(tmp_path)
    capsys.readouterr()
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    git(
        project,
        "remote",
        "add",
        "origin",
        "https://github.com/owner/repository.git",
    )
    write_executable(
        project / "scripts" / "release_policy.py",
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'mode': 'installed', 'capabilities': {}}))\n",
    )
    commit(project, "test: customize installed capability policy")
    monkeypatch.setattr(
        cli,
        "repository_context",
        lambda *args, **kwargs: cli.RepositoryContext(
            "owner/repository",
            "owner",
            "organization",
            "private",
            "github",
            True,
        ),
    )

    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                first_sha,
                "--allow-unreleased",
                "--check",
                "--json",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["answers_changed"] is False
    assert payload["capabilities_changed"] is True
    assert payload["update_available"] is True


def test_non_interactive_writes_require_yes(tmp_path: Path) -> None:
    """Automation cannot mutate a target without explicit approval."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "unapproved"
    assert (
        main(
            [
                "init",
                str(project),
                "--source",
                str(source),
                "--to",
                first_sha,
                "--allow-unreleased",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "init",
                str(project),
                "--apply-plan",
                str(lifecycle_plan_path(project, "init")),
                "--allow-unreleased",
                "--non-interactive",
            ]
        )
        == 2
    )
    assert not project.exists()


def test_release_resolution_and_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolve an approved annotated release and cover small input helpers."""
    del monkeypatch
    client = FakeReleaseClient()
    tag_object_sha = client.tag_results[0].object_sha
    commit_sha = client.tag_results[0].commit_sha
    revision = cli.resolve_revision(
        cli.CANONICAL_SOURCE,
        None,
        expected_sha=commit_sha,
        client=client,
    )
    assert revision.label == "v1.2.3"
    assert revision.sha == commit_sha
    assert revision.tag_object_sha == tag_object_sha
    assert revision.verified
    assert cli.github_repository("gh:owner/repository") == "owner/repository"
    assert cli.github_repository("not-a-github-source") is None
    assert cli.slugify(" Example Project! ") == "example-project"
    assert cli.slugify("...") == "csarc-project"

    empty_repo = tmp_path / "empty-template"
    empty_repo.mkdir()
    git(empty_repo, "init", "-b", "main")
    with pytest.raises(CliError, match="no release tags"):
        cli.resolve_revision(str(empty_repo), None, allow_unreleased=True)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("immutable", False, "not immutable"),
        ("draft", True, "published, stable"),
        ("prerelease", True, "published, stable"),
        ("published_at", None, "not published"),
    ],
)
def test_release_metadata_fails_closed(
    field: str, value: object, message: str
) -> None:
    """Reject releases that are mutable or not stable and published."""
    client = FakeReleaseClient()
    client.release_values[field] = value
    with pytest.raises(CliError, match=message):
        cli.resolve_revision(cli.CANONICAL_SOURCE, None, client=client)


def test_release_trust_failures_stop_before_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject identity, tag, SHA, attestation, and signature failures."""
    client = FakeReleaseClient()
    client.repository_id = 1
    with pytest.raises(CliError, match="identity mismatch"):
        cli.resolve_revision(cli.CANONICAL_SOURCE, None, client=client)

    client = FakeReleaseClient()
    client.tag_results[1] = cli.TagResolution("c" * 40, "b" * 40)
    with pytest.raises(CliError, match="tag moved"):
        cli.resolve_revision(cli.CANONICAL_SOURCE, None, client=client)

    client = FakeReleaseClient()
    with pytest.raises(CliError, match="Expected commit SHA"):
        cli.resolve_revision(
            cli.CANONICAL_SOURCE,
            None,
            expected_sha=client.tag_results[0].object_sha,
            client=client,
        )

    client = FakeReleaseClient()
    client.release_error = CliError("attestation missing")
    with pytest.raises(CliError, match="attestation missing"):
        cli.resolve_revision(cli.CANONICAL_SOURCE, None, client=client)

    client = FakeReleaseClient()
    client.commit_error = CliError("signature invalid")
    with pytest.raises(CliError, match="signature invalid"):
        cli.resolve_revision(cli.CANONICAL_SOURCE, None, client=client)

    with pytest.raises(CliError, match="Production source"):
        cli.resolve_revision(
            "https://github.com/example/csarc-repo-template",
            None,
            client=FakeReleaseClient(),
        )

    target = tmp_path / "unchanged"
    called = False

    def copied(*args: object, **kwargs: object) -> None:
        del args, kwargs
        nonlocal called
        called = True

    bad_client = FakeReleaseClient()
    bad_client.release_error = CliError("attestation missing")
    monkeypatch.setattr(cli, "GhReleaseClient", lambda: bad_client)
    monkeypatch.setattr(cli, "copier_copy", copied)
    assert main(["init", str(target), "--dry-run"]) == 2
    assert not called
    assert not target.exists()


@pytest.mark.parametrize(
    "source",
    [
        cli.CANONICAL_SOURCE.removesuffix(".git"),
        f"{cli.CANONICAL_SOURCE}/",
    ],
)
def test_copy_uses_resolved_canonical_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    """Give Copier one canonical spelling for every approved source alias."""
    copied_source: str | None = None

    def copied(
        actual_source: str,
        revision: cli.Revision,
        stage: Path,
        data: dict[str, str],
    ) -> None:
        del revision, stage, data
        nonlocal copied_source
        copied_source = actual_source
        raise CliError("fixture stop after source capture")

    monkeypatch.setattr(cli, "GhReleaseClient", FakeReleaseClient)
    monkeypatch.setattr(cli, "copier_copy", copied)

    assert (
        main(
            [
                "init",
                str(tmp_path / "canonical-source"),
                "--source",
                source,
                "--dry-run",
            ]
        )
        == 2
    )
    assert copied_source == cli.CANONICAL_SOURCE


def test_gh_client_dereferences_annotated_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep annotated-tag object SHA distinct from the commit SHA."""
    first_tag = "a" * 40
    nested_tag = "b" * 40
    commit_sha = "c" * 40

    def fake_gh_json(endpoint: str) -> dict[str, object]:
        if "/git/ref/tags/" in endpoint:
            return {"object": {"type": "tag", "sha": first_tag}}
        if endpoint.endswith(first_tag):
            return {"object": {"type": "tag", "sha": nested_tag}}
        if endpoint.endswith(nested_tag):
            return {"object": {"type": "commit", "sha": commit_sha}}
        raise AssertionError(endpoint)

    monkeypatch.setattr(cli, "gh_json", fake_gh_json)
    assert cli.GhReleaseClient().resolve_tag("v1.2.3") == cli.TagResolution(
        first_tag, commit_sha
    )


def test_gh_client_verifies_attestation_and_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate concrete GitHub boundary successes and malformed responses."""
    client = cli.GhReleaseClient()

    def successful_run(
        command: list[str],
        *,
        cwd: Path | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture, check
        return subprocess.CompletedProcess(command, 0, '{"verified":true}', "")

    monkeypatch.setattr(cli, "run", successful_run)
    client.verify_release("v1.2.3")

    def signature(endpoint: str) -> dict[str, object]:
        assert endpoint.endswith("c" * 40)
        return {"commit": {"verification": {"verified": True}}}

    monkeypatch.setattr(cli, "gh_json", signature)
    client.verify_commit("c" * 40)

    monkeypatch.setattr(cli, "gh_json", lambda endpoint: {"commit": {}})
    with pytest.raises(CliError, match="signature verification failed"):
        client.verify_commit("c" * 40)

    def invalid_attestation(
        command: list[str],
        *,
        cwd: Path | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture, check
        return subprocess.CompletedProcess(command, 0, "not-json", "")

    monkeypatch.setattr(cli, "run", invalid_attestation)
    with pytest.raises(CliError, match="invalid JSON"):
        client.verify_release("v1.2.3")


def test_provenance_validation_and_legacy_migration(tmp_path: Path) -> None:
    """Detect provenance drift and require explicit legacy migration."""
    target = tmp_path / "project"
    target.mkdir()
    commit_sha = "b" * 40
    client = FakeReleaseClient()
    revision = cli.resolve_revision(
        cli.CANONICAL_SOURCE,
        "v1.2.3",
        expected_sha=commit_sha,
        client=client,
    )
    cli.write_provenance(target, revision)
    current, saved = cli.current_revision(
        target,
        cli.CANONICAL_SOURCE,
        commit_sha,
        allow_unreleased=False,
        accept_legacy=False,
        from_release=None,
        client=FakeReleaseClient(),
    )
    assert current.verified
    assert saved is not None

    saved_path = target / cli.PROVENANCE_FILE
    changed = json.loads(saved_path.read_text(encoding="utf-8"))
    changed["repository_id"] = 1
    saved_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(CliError, match="repository_id"):
        cli.current_revision(
            target,
            cli.CANONICAL_SOURCE,
            commit_sha,
            allow_unreleased=False,
            accept_legacy=False,
            from_release=None,
            client=FakeReleaseClient(),
        )

    saved_path.unlink()
    with pytest.raises(CliError, match="Legacy repository"):
        cli.current_revision(
            target,
            cli.CANONICAL_SOURCE,
            commit_sha,
            allow_unreleased=False,
            accept_legacy=False,
            from_release=None,
            client=FakeReleaseClient(),
        )
    migrated, prior = cli.current_revision(
        target,
        cli.CANONICAL_SOURCE,
        commit_sha,
        allow_unreleased=False,
        accept_legacy=True,
        from_release="v1.2.3",
        client=FakeReleaseClient(),
    )
    assert migrated.verified
    assert prior is not None and prior["verification"] == "legacy-unverified"


def test_runtime_state_rejects_symlinked_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep adoption checkpoints and provenance inside the target repo."""
    revision = cli.Revision("local", "a" * 40, str(tmp_path))
    writers = (
        lambda target: cli.write_pending_adoption(target, {}),
        lambda target: cli.write_provenance(target, revision),
    )

    for index, writer in enumerate(writers):
        target = tmp_path / f"target-{index}"
        external = tmp_path / f"external-{index}"
        target.mkdir()
        external.mkdir()
        sentinel = external / "sentinel.txt"
        sentinel.write_text("outside\n", encoding="utf-8")
        (target / ".csarc").symlink_to(external, target_is_directory=True)

        with pytest.raises(CliError, match="symlink or non-directory"):
            writer(target)

        assert sentinel.read_text(encoding="utf-8") == "outside\n"
        assert tuple(external.iterdir()) == (sentinel,)

    target = tmp_path / "read-target"
    state = target / ".csarc"
    state.mkdir(parents=True)
    external = tmp_path / "external-provenance.json"
    external.write_text("{}\n", encoding="utf-8")
    (target / cli.PROVENANCE_FILE).symlink_to(external)

    with pytest.raises(CliError, match="must not be a symlink"):
        cli.read_provenance(target)

    fifo = state / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(CliError, match="not a regular file"):
        cli.atomic_replace_text(fifo, "replacement\n")

    target = tmp_path / "race-target"
    state = target / ".csarc"
    moved_state = target / ".csarc-before-race"
    external = tmp_path / "race-external"
    state.mkdir(parents=True)
    external.mkdir()
    real_open = cli.os.open

    def swap_parent_before_open(
        path: str | bytes | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if Path(path) == state and dir_fd is None and state.is_dir():
            state.rename(moved_state)
            state.symlink_to(external, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(cli.os, "open", swap_parent_before_open)
    with pytest.raises(CliError, match="Cannot safely open"):
        cli.write_provenance(target, revision)
    assert tuple(external.iterdir()) == ()

    target = tmp_path / "post-open-race-target"
    state = target / ".csarc"
    moved_state = target / ".csarc-before-race"
    external = tmp_path / "post-open-race-external"
    state.mkdir(parents=True)
    external.mkdir()

    def swap_parent_after_open(
        path: str | bytes | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        opened = real_open(path, flags, mode, dir_fd=dir_fd)
        if Path(path) == state and dir_fd is None and state.is_dir():
            state.rename(moved_state)
            state.symlink_to(external, target_is_directory=True)
        return opened

    monkeypatch.setattr(cli.os, "open", swap_parent_after_open)
    with pytest.raises(CliError, match="changed while writing"):
        cli.write_provenance(target, revision)
    assert tuple(external.iterdir()) == ()
    assert tuple(moved_state.iterdir()) == ()

    monkeypatch.setattr(cli.os, "open", real_open)
    target = tmp_path / "replace-race-target"
    state = target / ".csarc"
    moved_state = target / ".csarc-before-race"
    external = tmp_path / "replace-race-external"
    state.mkdir(parents=True)
    external.mkdir()
    provenance = target / cli.PROVENANCE_FILE
    provenance.write_text("original\n", encoding="utf-8")
    real_replace = cli.os.replace
    swapped = False

    def swap_parent_before_replace(
        source: str | bytes | Path,
        destination: str | bytes | Path,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal swapped
        if destination == provenance.name and not swapped:
            swapped = True
            state.rename(moved_state)
            state.symlink_to(external, target_is_directory=True)
        real_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(cli.os, "replace", swap_parent_before_replace)
    with pytest.raises(CliError, match="changed while writing"):
        cli.write_provenance(target, revision)
    assert (moved_state / provenance.name).read_text(encoding="utf-8") == (
        "original\n"
    )
    assert tuple(external.iterdir()) == ()


def test_github_api_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Translate GitHub CLI and response errors into actionable CLI errors."""

    def denied(
        command: list[str],
        *,
        cwd: Path | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture, check
        return subprocess.CompletedProcess(command, 1, "", "permission denied")

    monkeypatch.setattr(cli, "run", denied)
    with pytest.raises(CliError, match="approved GitHub Release"):
        cli.gh_json("repos/owner/repository/releases/latest")

    def invalid_json(
        command: list[str],
        *,
        cwd: Path | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture, check
        return subprocess.CompletedProcess(command, 0, "not json", "")

    monkeypatch.setattr(cli, "run", invalid_json)
    with pytest.raises(CliError, match="invalid JSON"):
        cli.gh_json("repos/owner/repository/releases/latest")


def test_input_and_conflict_errors(tmp_path: Path) -> None:
    """Reject malformed input and detect both supported conflict formats."""
    with pytest.raises(CliError, match="KEY=VALUE"):
        cli.parse_data(["missing-separator"])

    (tmp_path / "answers.yml").write_text("other: value\n", encoding="utf-8")
    with pytest.raises(CliError, match="missing _commit"):
        cli.read_answer(tmp_path / "answers.yml", "_commit")

    (tmp_path / "change.rej").write_text("rejected\n", encoding="utf-8")
    (tmp_path / "conflict.txt").write_text(
        "<<<<<<< project\nlocal\n=======\ntemplate\n>>>>>>> template\n",
        encoding="utf-8",
    )
    assert cli.find_conflicts(tmp_path) == ("change.rej", "conflict.txt")


def test_guardrails_for_invalid_targets(tmp_path: Path) -> None:
    """Reject targets that cannot safely enter the requested lifecycle."""
    source, first_sha = make_template(tmp_path)
    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "file.txt").write_text("content\n", encoding="utf-8")
    assert (
        main(
            [
                "init",
                str(nonempty),
                "--source",
                str(source),
                "--to",
                first_sha,
                "--allow-unreleased",
                "--dry-run",
            ]
        )
        == 2
    )
    assert main(["adopt", str(tmp_path / "missing"), "--dry-run"]) == 2
    assert main(["update", str(nonempty), "--check", "--json"]) == 2
    assert main(["update", str(nonempty), "--json"]) == 2
