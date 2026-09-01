"""End-to-end tests for the CSARC lifecycle CLI."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import stat
import subprocess
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

import csarc_cli.cli as cli
from csarc_cli.cli import CliError, main

ROOT = Path(__file__).resolve().parents[1]


def test_copier_migration_preserves_project_owned_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not replace a project-owned test symlink during migration."""
    migration = yaml.safe_load((ROOT / "copier.yml").read_text())[
        "_migrations"
    ][0]["command"]
    assert migration[:2] == ["python3", "-c"]

    tests = tmp_path / "tests"
    tests.mkdir()
    target = tmp_path / "project-owned.py"
    target.write_text("project owned\n", encoding="utf-8")
    legacy_test = tests / "test_delivery_sync.py"
    legacy_test.symlink_to(target)
    (tmp_path / ".copier-answers.yml").write_text(
        "branch_strategy: dev\n", encoding="utf-8"
    )

    class LegacyDigest:
        def hexdigest(self) -> str:
            return (
                "50fc918666723264272a9268ebaf5c0b120341e58"
                "8e1e1f5841686f8448abc99"
            )

    monkeypatch.setattr(hashlib, "sha256", lambda _content: LegacyDigest())
    monkeypatch.chdir(tmp_path)
    exec(compile(migration[2], "copier.yml migration", "exec"), {})  # noqa: S102

    assert legacy_test.is_symlink()
    assert legacy_test.read_text(encoding="utf-8") == "project owned\n"
    assert "branch_strategy: main" in (
        tmp_path / ".copier-answers.yml"
    ).read_text(encoding="utf-8")


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
project_verification_hook:
  type: str
  default: ''
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
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'test -z "${_CSARC_PROJECT_VERIFICATION_ACTIVE:-}"\n'
        'record() { local fd="${_CSARC_PROJECT_VERIFICATION_STATUS_FD:-}"; '
        'if [[ -n "$fd" ]]; then printf \'%s\\n\' "$1" >&"$fd"; fi; }\n'
        "record not-run\n"
        "test -f managed.txt\n"
        "hook=$(sed -n 's/^project_verification_hook: *//p' "
        '.copier-answers.yml | tr -d "\'\\"")\n'
        'if [[ -z "$hook" && -x scripts/verify-product ]]; then '
        "hook=scripts/verify-product; fi\n"
        'if [[ -n "$hook" ]]; then\n'
        "  record started\n"
        '  status_fd="${_CSARC_PROJECT_VERIFICATION_STATUS_FD:-}"\n'
        '  if ( eval "exec ${status_fd}>&-"; '
        "unset _CSARC_PROJECT_VERIFICATION_STATUS_FD; "
        '_CSARC_PROJECT_VERIFICATION_ACTIVE=direct "$hook" ); then\n'
        "    record passed\n"
        "  else\n"
        '    status=$?; record failed; exit "$status"\n'
        "  fi\n"
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


def initialize_project(tmp_path: Path) -> tuple[Path, Path, str]:
    """Create a generated project pinned to the first template commit."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "new-project"
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
                "--yes",
                "--non-interactive",
                "--data",
                "language=ci",
            ]
        )
        == 0
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


@pytest.mark.large
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
    assert main([*arguments, "--yes", "--non-interactive"]) == 0
    answers = (project / ".copier-answers.yml").read_text(encoding="utf-8")
    assert f"_commit: {first_sha}" in answers
    assert (project / "managed.txt").read_text() == "template version one\n"
    provenance = json.loads(
        (project / cli.PROVENANCE_FILE).read_text(encoding="utf-8")
    )
    assert provenance["commit_sha"] == first_sha
    assert provenance["verification"] == "development-unreleased"


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


@pytest.mark.large
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


@pytest.mark.large
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


@pytest.mark.large
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


@pytest.mark.large
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


@pytest.mark.large
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
            ]
        )
        == 2
    )
    assert "Repository context changed" in capsys.readouterr().err
    assert (project / cli.PENDING_ADOPTION_FILE).is_file()
    assert not (project / cli.PROVENANCE_FILE).exists()


@pytest.mark.large
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


@pytest.mark.large
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


@pytest.mark.large
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


@pytest.mark.large
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
        ("rust", "Cargo.toml", "Cargo.lock"),
    ],
)
@pytest.mark.large
def test_real_template_adoption_resumes_after_manifest_merge(
    tmp_path: Path,
    language: str,
    manifest_name: str,
    lock_name: str,
) -> None:
    """Finalize each language adoption without a pre-existing lockfile."""
    revision_sha = git(ROOT, "rev-parse", "HEAD")
    project = tmp_path / f"existing-{language}"
    reference = tmp_path / f"reference-{language}"
    data = cli.base_data(
        project,
        "adopt",
        {
            "coverage_mode": "global",
            "language": language,
            "security_reporting_channel": (
                "Use the synthetic fixture's private reporting channel."
            ),
        },
    )
    data["project_visibility"] = "private"
    cli.copier_copy(
        str(ROOT),
        cli.Revision(revision_sha, revision_sha, str(ROOT)),
        reference,
        data,
    )
    project.mkdir()
    if language == "python":
        initial_manifest = (
            '[project]\nname = "existing-python"\nversion = "0.1.0"\n'
            'requires-python = ">=3.14,<3.15"\n'
        )
    elif language == "typescript":
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
    else:
        initial_manifest = (
            '[package]\nname = "existing-rust"\nversion = "0.1.0"\n'
            'edition = "2024"\n\n[lib]\npath = "src/lib.rs"\n'
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
        str(ROOT),
        "--to",
        revision_sha,
        "--allow-unreleased",
        "--data",
        f"language={language}",
        "--data",
        "coverage_mode=global",
        "--data",
        "security_reporting_channel=Use the synthetic fixture's "
        "private reporting channel.",
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
    elif language == "typescript":
        merged = json.loads(
            (reference / manifest_name).read_text(encoding="utf-8")
        )
        merged["productSetting"] = True
        manifest.write_text(
            json.dumps(merged, indent=2) + "\n", encoding="utf-8"
        )
    else:
        manifest.write_text(
            (reference / manifest_name).read_text(encoding="utf-8")
            + "\n[package.metadata.product]\npreserved = true\n",
            encoding="utf-8",
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
                "--non-interactive",
                "--yes",
            ]
        )
        == 0
    )
    assert (project / lock_name).is_file()
    assert (project / cli.PROVENANCE_FILE).is_file()
    assert not (project / cli.PENDING_ADOPTION_FILE).exists()


@pytest.mark.large
def test_real_existing_adoption_uses_fixed_ownership_policies(
    tmp_path: Path,
) -> None:
    """Adopt the pilot collision shape without replacing product-owned files."""
    revision = git(ROOT, "rev-parse", "HEAD")
    project = tmp_path / "existing CSARC-測試"
    (project / ".github" / "workflows").mkdir(parents=True)
    (project / "README.md").write_text("# Product README\n", encoding="utf-8")
    (project / "CHANGELOG.md").write_text(
        "# Product changes\n", encoding="utf-8"
    )
    (project / "AGENTS.md").write_text(
        "# Product agent rules\r\n\r\nKeep this rule.\r\n",
        encoding="utf-8",
    )
    (project / ".gitignore").write_bytes(b"product-cache/\r\n.env\r\n")
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
    write_executable(
        project / "scripts" / "verify-product",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "grep -q '^# Product README$' README.md\n"
        "grep -q '^name: Product release$' .github/workflows/release.yml\n",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: product collision fixture")
    arguments = [
        "adopt",
        str(project),
        "--source",
        str(ROOT),
        "--to",
        revision,
        "--allow-unreleased",
        "--data",
        "language=ci",
        "--data",
        "security_reporting_channel=Use the synthetic fixture's "
        "private reporting channel.",
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
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["files"]["manual_merge"] == []
    assert payload["files"]["unknown"] == []
    assert payload["files"]["automatic_merge"] == [".gitignore", "AGENTS.md"]
    assert "README.md" in payload["files"]["preserve"]
    assert "CHANGELOG.md" in payload["files"]["preserve"]
    assert ".github/workflows/release.yml" in payload["files"]["preserve"]
    assert ".github/workflows/csarc-release.yml" not in payload["files"]["add"]
    assert cli.PROVENANCE_FILE.as_posix() in payload["files"]["add"]
    assert payload["adoption"]["project_verification_hook"] == {
        "configured": True,
        "path": "scripts/verify-product",
        "reason": "Project verification hook completed successfully.",
        "result": "passed",
        "source": "fallback",
    }
    assert payload["adoption"]["verification"] == "passed"
    assert payload["answers"]["package_name"] == "product_identity"

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
        == 0
    )
    assert (project / "README.md").read_text(encoding="utf-8") == (
        "# Product README\n"
    )
    assert (project / "CHANGELOG.md").read_text(encoding="utf-8") == (
        "# Product changes\n"
    )
    assert product_release.read_text(encoding="utf-8").startswith(
        "name: Product release"
    )
    assert not (
        project / ".github" / "workflows" / "csarc-release.yml"
    ).is_file()
    assert "Keep this rule." in (project / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    assert cli.AGENTS_BLOCK_START in (project / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    ignore_lines = (
        (project / ".gitignore").read_text(encoding="utf-8").splitlines()
    )
    assert ignore_lines[:2] == ["product-cache/", ".env"]
    assert ignore_lines.count(".env") == 1


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
    placements: list[tuple[str, float, float]] = []

    def record_pdf_text(
        text: str,
        _cm: list[float],
        tm: list[float],
        _font: dict[str, object] | None,
        _size: float,
    ) -> None:
        if clean := text.strip():
            placements.append((clean, tm[4], tm[5]))

    PdfReader(report_dir / "csarc-adoption-dry-run.pdf").pages[0].extract_text(
        visitor_text=record_pdf_text
    )
    labels = {
        "Target",
        "Repository",
        "Visibility",
        "Template source",
        "Template",
        "Verification",
        "Profile",
        "Project hook",
        "Hook configured",
        "Hook result",
        "Hook reason",
    }
    for label, label_x, label_y in (
        item for item in placements if item[0] in labels
    ):
        value, value_x, _ = next(
            item
            for item in placements
            if item[2] == label_y and item[1] > label_x
        )
        assert (
            value_x - label_x - cli.stringWidth(label, "Helvetica-Bold", 8)
            >= 7.9
        )
        assert (
            value_x + cli.stringWidth(value, "Helvetica", 8) <= cli.A4[0] - 48
        )
    assert git(project, "status", "--porcelain") == before


@pytest.mark.large
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
    assert "plan without writing (the default for adopt)" in help_text


@pytest.mark.large
def test_adopt_applies_exact_plan_over_preserved_dirty_file(
    tmp_path: Path,
) -> None:
    """Verify and apply while preserving one authorized dirty product file."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "dirty-product"
    project.mkdir()
    hook_runs = tmp_path / "hook-runs.txt"
    (project / "components.yaml").write_text("clean: true\n", encoding="utf-8")
    write_executable(
        project / "scripts" / "verify-skills",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "grep -q '^authorized: dirty$' components.yaml\n"
        f"printf 'run\\n' >> {shlex.quote(str(hook_runs))}\n",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: baseline")
    components = project / "components.yaml"
    components.write_text("authorized: dirty\n", encoding="utf-8")

    before = cli.git_target_state(project)[1]
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
                "--data",
                "project_verification_hook=scripts/verify-skills",
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
    assert payload["adoption"]["applicable"] is True
    assert payload["adoption"]["clean"] is False
    assert payload["adoption"]["target_changes"] == [" M components.yaml"]
    assert payload["adoption"]["preserved_dirty_paths"] == ["components.yaml"]
    assert payload["adoption"]["verification"] == "passed"
    assert payload["adoption"]["project_verification_hook"]["result"] == (
        "passed"
    )
    assert "components.yaml" in payload["files"]["preserve"]
    assert hook_runs.read_text(encoding="utf-8").splitlines() == ["run"]
    markdown = plan.with_name("csarc-adoption-dry-run.md").read_text(
        encoding="utf-8"
    )
    assert "Decision: Ready to adopt" in markdown
    assert "Working tree: dirty; exact preserved state" in markdown
    assert (
        main(
            [
                "adopt",
                str(project),
                "--apply-plan",
                str(plan),
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    )
    assert components.read_text(encoding="utf-8") == "authorized: dirty\n"
    assert before == (" M components.yaml",)
    assert " M components.yaml" in cli.git_target_state(project)[1]
    assert hook_runs.read_text(encoding="utf-8").splitlines() == [
        "run",
        "run",
    ]
    assert (project / ".copier-answers.yml").is_file()


def test_adopt_rejects_dirty_path_not_classified_as_preserve(
    tmp_path: Path,
) -> None:
    """Keep collisions and other unapproved dirty paths review-only."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "dirty-collision"
    project.mkdir()
    (project / "managed.txt").write_text(
        "template version one\n", encoding="utf-8"
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: baseline")
    (project / "managed.txt").write_text("dirty collision\n", encoding="utf-8")

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
    report_dir = tmp_path / "dirty-collision-csarc-adoption-report"
    plan = report_dir / cli.ADOPTION_PLAN_BASENAME
    payload = json.loads(plan.read_text(encoding="utf-8"))
    assert payload["adoption"]["applicable"] is False
    assert payload["adoption"]["verification"] == "not-run-dirty"
    assert payload["adoption"]["preserved_dirty_paths"] == []
    assert "managed.txt" in payload["files"]["manual_merge"]
    markdown = (report_dir / "csarc-adoption-dry-run.md").read_text(
        encoding="utf-8"
    )
    assert "Decision: Not ready to adopt" in markdown
    assert "Do not apply this plan" in markdown
    pdf = PdfReader(report_dir / "csarc-adoption-dry-run.pdf")
    assert "Not ready to adopt" in pdf.pages[0].extract_text()
    assert main(["adopt", str(project), "--apply-plan", str(plan)]) == 2
    assert not (project / ".copier-answers.yml").exists()


def test_adopt_blocks_hook_mutation_of_preserved_dirty_file(
    tmp_path: Path,
) -> None:
    """Keep preserved dirty bytes out of the candidate artifact set."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "dirty-hook-mutation"
    project.mkdir()
    components = project / "components.yaml"
    components.write_text("clean: true\n", encoding="utf-8")
    write_executable(
        project / "scripts" / "verify-skills",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "printf 'hook mutation\\n' > components.yaml\n",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: baseline")
    components.write_text("authorized: dirty\n", encoding="utf-8")

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
                "--data",
                "project_verification_hook=scripts/verify-skills",
            ]
        )
        == 0
    )
    plan = (
        tmp_path
        / "dirty-hook-mutation-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    payload = json.loads(plan.read_text(encoding="utf-8"))
    assert payload["adoption"]["applicable"] is False
    assert payload["adoption"]["project_verification_hook"]["result"] == (
        "passed"
    )
    assert str(payload["adoption"]["verification"]).startswith(
        "failed: Candidate verification changed preserved dirty files:"
    )
    assert components.read_text(encoding="utf-8") == "authorized: dirty\n"


def test_adopt_rejects_staged_preserved_file(tmp_path: Path) -> None:
    """Do not authorize staged state through the dirty-preserve exception."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "staged-product"
    project.mkdir()
    product = project / "product.txt"
    product.write_text("clean\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: baseline")
    product.write_text("staged\n", encoding="utf-8")
    git(project, "add", "product.txt")

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
        / "staged-product-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    payload = json.loads(plan.read_text(encoding="utf-8"))
    assert payload["adoption"]["applicable"] is False
    assert payload["adoption"]["verification"] == "not-run-dirty"
    assert payload["adoption"]["preserved_dirty_paths"] == []
    assert "product.txt" in payload["files"]["preserve"]


@pytest.mark.parametrize(
    ("dirty_state", "expected_status"),
    [
        ("untracked", "?? extra.txt"),
        ("deleted", " D product.txt"),
        ("type", " T product.txt"),
    ],
)
def test_adopt_rejects_non_modified_dirty_states_without_running_hook(
    tmp_path: Path, dirty_state: str, expected_status: str
) -> None:
    """Only tracked unstaged modifications may use the preserve exception."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / f"dirty-{dirty_state}"
    project.mkdir()
    product = project / "product.txt"
    product.write_text("product\n", encoding="utf-8")
    hook_runs = tmp_path / f"{dirty_state}-hook-runs"
    write_executable(
        project / "scripts" / "verify-skills",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        f"printf 'run\\n' >> {shlex.quote(str(hook_runs))}\n",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: baseline")
    if dirty_state == "untracked":
        (project / "extra.txt").write_text("extra\n", encoding="utf-8")
    else:
        product.unlink()
        if dirty_state == "type":
            product.symlink_to("other.txt")

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
                "--data",
                "project_verification_hook=scripts/verify-skills",
            ]
        )
        == 0
    )
    plan = (
        tmp_path
        / f"dirty-{dirty_state}-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    payload = json.loads(plan.read_text(encoding="utf-8"))
    assert payload["adoption"]["target_changes"] == [expected_status]
    assert payload["adoption"]["applicable"] is False
    assert payload["adoption"]["verification"] == "not-run-dirty"
    assert payload["adoption"]["project_verification_hook"]["result"] == (
        "not-run"
    )
    assert not hook_runs.exists()


@pytest.mark.parametrize("drift", ["content", "mode", "path"])
def test_adopt_rejects_preserved_dirty_file_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], drift: str
) -> None:
    """Bind authorized dirty content, mode, and path state to the plan."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / f"dirty-{drift}-drift"
    project.mkdir()
    product = project / "product.txt"
    product.write_text("clean\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: baseline")
    product.write_text("reviewed dirty bytes\n", encoding="utf-8")

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
        / f"dirty-{drift}-drift-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    if drift == "content":
        product.write_text("drifted after review\n", encoding="utf-8")
    elif drift == "mode":
        product.chmod(product.stat().st_mode | stat.S_IXUSR)
    else:
        (project / "extra.txt").write_text("unexpected\n", encoding="utf-8")

    assert main(["adopt", str(project), "--apply-plan", str(plan)]) == 2
    assert "changed after the plan was created" in capsys.readouterr().err
    assert not (project / ".copier-answers.yml").exists()


def test_adopt_rejects_race_between_comparison_and_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Do not legitimize target changes made after file classification."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "comparison-race"
    project.mkdir()
    managed = project / "managed.txt"
    managed.write_text("template version one\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: baseline")
    compare_stage = cli.compare_stage

    def race_after_comparison(
        stage: Path,
        target: Path,
        *,
        adopt: bool,
        merged_paths: tuple[str, ...] = (),
    ) -> cli.Plan:
        planned = compare_stage(
            stage, target, adopt=adopt, merged_paths=merged_paths
        )
        managed.write_text("raced dirty bytes\n", encoding="utf-8")
        return planned

    monkeypatch.setattr(cli, "compare_stage", race_after_comparison)

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
        == 2
    )
    assert "changed after the plan was created" in capsys.readouterr().err
    assert not (
        tmp_path
        / "comparison-race-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    ).exists()


@pytest.mark.large
def test_adopt_infers_unicode_repository_and_applies_exact_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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

    assert (
        main(
            [
                "adopt",
                "--apply-plan",
                str(plan_path),
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    )
    assert (project / cli.PROVENANCE_FILE).is_file()


@pytest.mark.large
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
    assert main(["adopt", str(project), "--apply-plan", str(plan_path)]) == 2
    assert "digest does not match" in capsys.readouterr().err
    assert not (project / "managed.txt").exists()

    plan_path.write_text(original, encoding="utf-8")
    (project / "product.txt").write_text("new product\n", encoding="utf-8")
    commit(project, "test: move target head")
    assert main(["adopt", str(project), "--apply-plan", str(plan_path)]) == 2
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


@pytest.mark.large
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


@pytest.mark.large
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


def test_candidate_patch_ignores_present_transient_paths(
    tmp_path: Path,
) -> None:
    """Do not misclassify verifier caches as planned deletions."""
    project = tmp_path / "transient-patch-target"
    project.mkdir()
    (project / "product.txt").write_text("product\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: transient patch baseline")
    candidate = tmp_path / "transient-patch-candidate"
    cli.clone_target(project, candidate)
    planned = candidate / "planned.txt"
    planned.write_text("planned\n", encoding="utf-8")
    transient = candidate / "scripts" / "__pycache__" / "helper.pyc"
    transient.parent.mkdir(parents=True)
    transient.write_bytes(b"transient")
    assert transient.relative_to(candidate).as_posix() in cli.git_changed_paths(
        candidate
    )
    artifacts, deletions = cli.candidate_patch_effects(candidate)
    head, changes, _ = cli.target_state(project)

    assert artifacts == {"planned.txt": cli.file_fingerprint(planned)}
    assert deletions == ()
    cli.write_candidate_patch(
        candidate,
        project,
        tmp_path / "transient.patch",
        artifacts=artifacts,
        target_snapshot={
            "target_head": head,
            "target_changes": list(changes),
            "target_files": cli.target_file_snapshot(project),
        },
    )

    assert (project / "planned.txt").read_text(encoding="utf-8") == "planned\n"
    assert not (project / "scripts" / "__pycache__").exists()


def test_candidate_patch_preserves_ignored_rejection_file(
    tmp_path: Path,
) -> None:
    """Include an ignored Copier rejection in the explicit conflict patch."""
    project = tmp_path / "ignored-conflict-target"
    project.mkdir()
    (project / ".gitignore").write_text("*.rej\n", encoding="utf-8")
    (project / "managed.txt").write_text("current\n", encoding="utf-8")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: ignored conflict baseline")
    candidate = tmp_path / "ignored-conflict-candidate"
    cli.clone_target(project, candidate)
    rejection = candidate / "managed.txt.rej"
    rejection.write_text("rejected update\n", encoding="utf-8")
    conflicts = cli.find_conflicts(candidate)
    assert conflicts == ("managed.txt.rej",)
    assert "managed.txt.rej" not in cli.git_changed_paths(candidate)
    artifacts, deletions = cli.candidate_patch_effects(
        candidate, include_paths=conflicts
    )
    head, changes, _ = cli.target_state(project)

    cli.write_candidate_patch(
        candidate,
        project,
        tmp_path / "ignored-conflict.patch",
        artifacts=artifacts,
        target_snapshot={
            "target_head": head,
            "target_changes": list(changes),
            "target_files": cli.target_file_snapshot(project),
        },
        delete_paths=deletions,
        include_paths=conflicts,
    )

    assert (project / "managed.txt.rej").read_text(encoding="utf-8") == (
        "rejected update\n"
    )


def test_candidate_patch_rejects_stale_or_unplanned_deletions(
    tmp_path: Path,
) -> None:
    """Bind the exact deletion set before applying a candidate patch."""
    project = tmp_path / "deletion-target"
    project.mkdir()
    (project / "obsolete.txt").write_text(
        "keep until verified\n", encoding="utf-8"
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: deletion baseline")
    head, changes, _ = cli.target_state(project)
    snapshot = {
        "target_head": head,
        "target_changes": list(changes),
        "target_files": cli.target_file_snapshot(project),
    }

    deleted = tmp_path / "unplanned-deletion-candidate"
    cli.clone_target(project, deleted)
    (deleted / "obsolete.txt").unlink()
    unplanned_root = tmp_path / "unplanned-deletion"
    unplanned_root.mkdir()
    with pytest.raises(CliError, match="effects differ"):
        cli.write_candidate_patch(
            deleted,
            project,
            unplanned_root / "candidate.patch",
            artifacts={},
            target_snapshot=snapshot,
        )

    stale = tmp_path / "stale-deletion-candidate"
    cli.clone_target(project, stale)
    stale_root = tmp_path / "stale-deletion"
    stale_root.mkdir()
    with pytest.raises(CliError, match="effects differ"):
        cli.write_candidate_patch(
            stale,
            project,
            stale_root / "candidate.patch",
            artifacts={},
            target_snapshot=snapshot,
            delete_paths=("obsolete.txt",),
        )

    assert (project / "obsolete.txt").read_text(encoding="utf-8") == (
        "keep until verified\n"
    )


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
                "--data",
                "project_verification_hook=scripts/verify-product",
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
    assert payload["adoption"]["project_verification_hook"] == {
        "configured": True,
        "path": "scripts/verify-product",
        "reason": "Project verification hook exited non-zero: "
        "scripts/verify-product",
        "result": "failed",
        "source": "explicit",
    }
    assert str(payload["adoption"]["verification"]).startswith("failed:")
    markdown = plan_path.with_name("csarc-adoption-dry-run.md").read_text(
        encoding="utf-8"
    )
    assert "Decision: Not ready to adopt" in markdown
    pdf = PdfReader(plan_path.with_name("csarc-adoption-dry-run.pdf"))
    assert "Not ready to adopt" in pdf.pages[0].extract_text()
    assert main(["adopt", str(project), "--apply-plan", str(plan_path)]) == 2
    assert git(project, "status", "--porcelain") == before
    assert not (project / "managed.txt").exists()


@pytest.mark.large
def test_invalid_project_hook_blocks_pending_adoption_without_writes(
    tmp_path: Path,
) -> None:
    """Reject a known bad hook before creating a resumable checkpoint."""
    source, revision = make_template(tmp_path)
    project = tmp_path / "invalid-pending-hook"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "existing"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: invalid pending hook")
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
                "--data",
                "language=python",
                "--data",
                "project_verification_hook=scripts/missing",
            ]
        )
        == 0
    )
    plan_path = (
        tmp_path
        / "invalid-pending-hook-csarc-adoption-report"
        / cli.ADOPTION_PLAN_BASENAME
    )
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["adoption"]["applicable"] is False
    assert payload["adoption"]["project_verification_hook"] == {
        "configured": True,
        "path": "scripts/missing",
        "reason": "Project verification hook does not exist: scripts/missing",
        "result": "failed",
        "source": "explicit",
    }
    assert main(["adopt", str(project), "--apply-plan", str(plan_path)]) == 2
    assert git(project, "status", "--porcelain") == before
    assert not (project / cli.PENDING_ADOPTION_FILE).exists()
    assert not (project / "managed.txt").exists()


@pytest.mark.large
def test_adoption_records_and_replays_explicit_project_hook(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bind the explicit hook path and result into every adoption report."""
    source, revision = make_template(tmp_path)
    project = tmp_path / "explicit-hook-product"
    project.mkdir()
    (project / "product.txt").write_text("product\n", encoding="utf-8")
    write_executable(
        project / "scripts" / "verify-skills",
        "#!/usr/bin/env bash\nset -euo pipefail\ntest -f product.txt\n",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: explicit project hook")
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
        "--data",
        "project_verification_hook=scripts/verify-skills",
    ]

    assert main(arguments) == 0
    report_dir = tmp_path / "explicit-hook-product-csarc-adoption-report"
    plan_path = report_dir / cli.ADOPTION_PLAN_BASENAME
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["adoption"]["project_verification_hook"] == {
        "configured": True,
        "path": "scripts/verify-skills",
        "reason": "Project verification hook completed successfully.",
        "result": "passed",
        "source": "explicit",
    }
    markdown = (report_dir / "csarc-adoption-dry-run.md").read_text(
        encoding="utf-8"
    )
    assert "Project verification hook: `scripts/verify-skills`" in markdown
    assert "Project verification hook configured: `true`" in markdown
    assert "Project verification result: `passed`" in markdown
    assert (
        "Project verification reason: `Project verification hook completed "
        "successfully.`" in markdown
    )
    pdf = "\n".join(
        page.extract_text()
        for page in PdfReader(report_dir / "csarc-adoption-dry-run.pdf").pages
    )
    assert "Project hook" in pdf and "scripts/verify-skills" in pdf
    assert "Hook configured" in pdf and "true" in pdf
    assert "Hook result" in pdf and "passed" in pdf
    assert "Hook reason" in pdf
    assert "Project verification hook completed successfully." in pdf

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
        == 0
    )
    assert (project / cli.PROVENANCE_FILE).is_file()

    capsys.readouterr()
    write_executable(
        project / "scripts" / "verify-other",
        "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n",
    )
    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                revision,
                "--allow-unreleased",
                "--check",
                "--json",
                "--data",
                "project_verification_hook=scripts/verify-other",
            ]
        )
        == 1
    )
    update = json.loads(capsys.readouterr().out)
    assert update["answers_changed"] is True
    assert update["answers"]["project_verification_hook"] == (
        "scripts/verify-other"
    )


def test_explicit_project_hook_runs_once_without_using_run_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run one checked executable path without treating product launch as it."""
    project = tmp_path / "hook-project"
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        "project_run_command: scripts/run-product\n"
        "project_verification_hook: scripts/verify-product\n",
        encoding="utf-8",
    )
    write_executable(
        project / "scripts" / "verify",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'test -z "${_CSARC_PROJECT_VERIFICATION_ACTIVE:-}"\n'
        'status_fd="${_CSARC_PROJECT_VERIFICATION_STATUS_FD:-}"\n'
        'test -n "$status_fd"\n'
        "printf 'not-run\\n' >&\"$status_fd\"\n"
        "printf 'started\\n' >&\"$status_fd\"\n"
        "printf '%s\\n' \"$status_fd\" > .known-status-fd\n"
        'if ( eval "exec ${status_fd}>&-"; '
        "unset _CSARC_PROJECT_VERIFICATION_STATUS_FD; "
        "_CSARC_PROJECT_VERIFICATION_ACTIVE=direct "
        "./scripts/verify-product ); then\n"
        "  printf 'passed\\n' >&\"$status_fd\"\n"
        "else\n"
        "  status=$?; printf 'failed\\n' >&\"$status_fd\"; "
        'exit "$status"\n'
        "fi\n",
    )
    write_executable(
        project / "scripts" / "verify-product",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'test -z "${_CSARC_PROJECT_VERIFICATION_STATUS_FD:-}"\n'
        "try_fd() {\n"
        '  local candidate_fd="$1"\n'
        '  [[ "$candidate_fd" =~ ^[0-9]+$ ]] || return 0\n'
        "  (( candidate_fd > 2 )) || return 0\n"
        "  eval \"printf 'forged\\n' >&${candidate_fd}\" 2>/dev/null || true\n"
        "}\n"
        'try_fd "$(cat .known-status-fd)"\n'
        'for candidate_fd in {3..32}; do try_fd "$candidate_fd"; done\n'
        "for descriptor_root in /dev/fd /proc/self/fd; do\n"
        '  [[ -d "$descriptor_root" ]] || continue\n'
        '  for descriptor in "$descriptor_root"/*; do\n'
        '    candidate_fd="${descriptor##*/}"\n'
        '    [[ "$candidate_fd" =~ ^[0-9]+$ ]] || continue\n'
        "    (( candidate_fd <= 32 )) || continue\n"
        '    try_fd "$candidate_fd"\n'
        "  done\n"
        "done\n"
        "test ! -e .project-hook-ran\n"
        "printf 'once\\n' > .project-hook-ran\n",
    )
    write_executable(
        project / "scripts" / "run-product",
        "#!/usr/bin/env bash\nexit 99\n",
    )
    monkeypatch.setenv("CSARC_SKIP_PROJECT_VERIFICATION_HOOK", "true")
    old_status = project / "preserve-me"
    old_status.write_text("preserve me\n", encoding="utf-8")
    monkeypatch.setenv(
        "_CSARC_PROJECT_VERIFICATION_STATUS_FILE", str(old_status)
    )

    assert cli.verify_project(project) == {
        "configured": True,
        "path": "scripts/verify-product",
        "reason": "Project verification hook completed successfully.",
        "result": "passed",
        "source": "explicit",
    }
    assert (project / ".project-hook-ran").read_text(encoding="utf-8") == (
        "once\n"
    )
    assert old_status.read_text(encoding="utf-8") == "preserve me\n"


def test_configured_hook_requires_canonical_status(tmp_path: Path) -> None:
    """Fail closed when canonical verification omits hook completion status."""
    project = tmp_path / "missing-hook-status"
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        "project_verification_hook: scripts/verify-product\n",
        encoding="utf-8",
    )
    write_executable(
        project / "scripts" / "verify",
        "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n",
    )
    write_executable(
        project / "scripts" / "verify-product",
        "#!/usr/bin/env bash\nset -euo pipefail\ntouch should-not-run\n",
    )

    with pytest.raises(cli.ProjectVerificationError) as raised:
        cli.verify_project(project)
    assert raised.value.hook == {
        "configured": True,
        "path": "scripts/verify-product",
        "reason": "Canonical verification returned an invalid hook status.",
        "result": "failed",
        "source": "explicit",
    }
    assert not (project / "should-not-run").exists()


@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_project_hook_rejects_canonical_verify_identity(
    tmp_path: Path, alias: str
) -> None:
    """Reject direct and aliased recursion into canonical verification."""
    project = tmp_path / f"canonical-hook-{alias}"
    project.mkdir()
    verify = project / "scripts" / "verify"
    write_executable(verify, "#!/usr/bin/env bash\nexit 0\n")
    hook = project / "scripts" / "hook"
    if alias == "direct":
        hook_path = "scripts/verify"
    elif alias == "symlink":
        hook.symlink_to("verify")
        hook_path = "scripts/hook"
    else:
        hook.hardlink_to(verify)
        hook_path = "scripts/hook"
    (project / ".copier-answers.yml").write_text(
        f"project_verification_hook: {hook_path}\n", encoding="utf-8"
    )

    with pytest.raises(cli.ProjectVerificationError, match="must not resolve"):
        cli.verify_project(project)


def test_project_hook_cannot_reenter_canonical_verify(tmp_path: Path) -> None:
    """Fail an indirect hook recursion before canonical work runs twice."""
    project = tmp_path / "recursive-hook"
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        "project_verification_hook: scripts/verify-product\n",
        encoding="utf-8",
    )
    write_executable(
        project / "scripts" / "verify",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'if [[ -n "${_CSARC_PROJECT_VERIFICATION_ACTIVE:-}" ]]; then\n'
        "  exit 42\n"
        "fi\n"
        'status_fd="${_CSARC_PROJECT_VERIFICATION_STATUS_FD:-}"\n'
        "printf 'not-run\\n' >&\"$status_fd\"\n"
        "printf 'started\\n' >&\"$status_fd\"\n"
        'if ( eval "exec ${status_fd}>&-"; '
        "unset _CSARC_PROJECT_VERIFICATION_STATUS_FD; "
        "_CSARC_PROJECT_VERIFICATION_ACTIVE=direct "
        "./scripts/verify-product ); then\n"
        "  printf 'passed\\n' >&\"$status_fd\"\n"
        "else\n"
        "  status=$?; printf 'failed\\n' >&\"$status_fd\"; "
        'exit "$status"\n'
        "fi\n",
    )
    write_executable(
        project / "scripts" / "verify-product",
        "#!/usr/bin/env bash\nset -euo pipefail\n./scripts/verify\n",
    )

    with pytest.raises(cli.ProjectVerificationError) as raised:
        cli.verify_project(project)
    assert raised.value.hook["result"] == "failed"
    assert raised.value.hook["reason"] == (
        "Project verification hook exited non-zero: scripts/verify-product"
    )


def test_generated_verifier_has_private_hook_handoff() -> None:
    """Keep generated hook status separate from execution control."""
    verifier = (ROOT / "template/scripts/verify.jinja").read_text(
        encoding="utf-8"
    )
    assert "CSARC_SKIP_PROJECT_VERIFICATION_HOOK" not in verifier
    assert "skip_project_verification_hook" not in verifier
    assert "_CSARC_PROJECT_VERIFICATION_NONCE" not in verifier
    assert "_CSARC_PROJECT_VERIFICATION_STATUS_FILE" not in verifier
    assert "_CSARC_PROJECT_VERIFICATION_STATUS_FD" in verifier
    assert "_CSARC_PROJECT_VERIFICATION_ACTIVE" in verifier
    assert "os.path.samefile(hook, canonical)" in verifier


def test_generated_verifier_status_descriptor_cannot_open_caller_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ignore the retired path variable and fail closed on an invalid FD."""
    preserved = tmp_path / "preserve-me"
    preserved.write_text("preserve me\n", encoding="utf-8")
    monkeypatch.setenv(
        "_CSARC_PROJECT_VERIFICATION_STATUS_FILE", str(preserved)
    )
    verifier = ROOT / "template/scripts/verify.jinja"

    old_path = subprocess.run(  # noqa: S603
        ["/bin/bash", str(verifier), "invalid"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert old_path.returncode == 2
    assert preserved.read_text(encoding="utf-8") == "preserve me\n"

    monkeypatch.setenv("_CSARC_PROJECT_VERIFICATION_STATUS_FD", "not-a-fd")
    invalid_fd = subprocess.run(  # noqa: S603
        ["/bin/bash", str(verifier), "invalid"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid_fd.returncode == 1
    assert "status descriptor is invalid" in invalid_fd.stderr
    assert preserved.read_text(encoding="utf-8") == "preserve me\n"


@pytest.mark.parametrize(
    ("path", "error"),
    [
        ("../verify", "safe repository-relative"),
        ("scripts/verify && true", "safe repository-relative"),
        ("scripts/missing", "does not exist"),
        ("scripts", "not a regular file"),
        ("scripts/not-executable", "not executable"),
    ],
)
@pytest.mark.large
def test_project_hook_rejects_unsafe_or_unusable_paths(
    tmp_path: Path, path: str, error: str
) -> None:
    """Fail closed before canonical verification for an unsafe hook."""
    project = tmp_path / "unsafe-hook-project"
    project.mkdir()
    (project / "scripts").mkdir()
    (project / "scripts" / "not-executable").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
    )
    (project / ".copier-answers.yml").write_text(
        f"project_verification_hook: {path!r}\n", encoding="utf-8"
    )
    write_executable(
        project / "scripts" / "verify",
        "#!/usr/bin/env bash\nexit 0\n",
    )

    with pytest.raises(CliError, match=error):
        cli.verify_project(project)


def test_project_hook_rejects_symlink_escape(tmp_path: Path) -> None:
    """Do not execute a configured path that resolves outside the repo."""
    project = tmp_path / "symlink-hook-project"
    project.mkdir()
    (project / "scripts").mkdir()
    outside = tmp_path / "outside-hook"
    write_executable(outside, "#!/usr/bin/env bash\nexit 0\n")
    (project / "scripts" / "verify-outside").symlink_to(outside)
    (project / ".copier-answers.yml").write_text(
        "project_verification_hook: scripts/verify-outside\n",
        encoding="utf-8",
    )
    write_executable(
        project / "scripts" / "verify",
        "#!/usr/bin/env bash\nexit 0\n",
    )

    with pytest.raises(CliError, match="escapes the repository"):
        cli.verify_project(project)


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


@pytest.mark.large
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


@pytest.mark.large
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
    assert "files may still change" in capsys.readouterr().out

    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                second_sha,
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
    expected_head, expected_changes, _ = cli.target_state(project)
    expected_files = cli.target_file_snapshot(project)

    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                third_sha,
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 2
    )
    actual_head, actual_changes, _ = cli.target_state(project)
    assert (actual_head, actual_changes) == (expected_head, expected_changes)
    assert cli.target_file_snapshot(project) == expected_files


@pytest.mark.large
def test_legacy_update_conflict_leaves_target_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep a legacy target byte-identical when Copier finds a conflict."""
    source, project, _ = initialize_project(tmp_path)
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: generated project")

    (project / cli.PROVENANCE_FILE).unlink()
    (project / "managed.txt").write_text(
        "legacy customization\n", encoding="utf-8"
    )
    commit(project, "test: legacy customized project")
    (source / "template" / "managed.txt").write_text(
        "template version two\n", encoding="utf-8"
    )
    target_sha = commit(source, "test: conflicting template update")
    expected_head, expected_changes, _ = cli.target_state(project)
    expected_files = cli.target_file_snapshot(project)

    assert (
        main(
            [
                "update",
                str(project),
                "--from-release",
                "v0.2.4",
                "--accept-legacy",
                "--to",
                target_sha,
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 2
    )

    error = capsys.readouterr().err
    assert "managed.txt" in error
    assert "the target was not changed" in error
    actual_head, actual_changes, _ = cli.target_state(project)
    assert (actual_head, actual_changes) == (expected_head, expected_changes)
    assert cli.target_file_snapshot(project) == expected_files


@pytest.mark.large
def test_update_migrates_legacy_copier_answers_to_single_config(
    tmp_path: Path,
) -> None:
    """Move legacy Copier tracking into the canonical repository config."""
    source, project, _ = initialize_project(tmp_path)
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: generated legacy project")

    copier_config = source / "copier.yml"
    copier_config.write_text(
        copier_config.read_text(encoding="utf-8").replace(
            "_answers_file: .copier-answers.yml",
            "_answers_file: .csarc/config.yml",
        ),
        encoding="utf-8",
    )
    verify = source / "template/scripts/verify"
    verify.write_text(
        verify.read_text(encoding="utf-8").replace(
            ".copier-answers.yml", ".csarc/config.yml"
        ),
        encoding="utf-8",
    )
    second_sha = commit(source, "test: use one repository config")

    assert (
        main(
            [
                "update",
                str(project),
                "--to",
                second_sha,
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
    )
    config = project / ".csarc/config.yml"
    assert config.is_file()
    assert f"_commit: {second_sha}" in config.read_text(encoding="utf-8")
    assert not (project / ".copier-answers.yml").exists()


def test_update_check_validates_hook_without_running_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Validate the configured update hook while keeping check read-only."""
    source, project, _ = initialize_project(tmp_path)
    capsys.readouterr()
    answers = project / ".copier-answers.yml"
    answers.write_text(
        re.sub(
            r"^project_verification_hook:.*$",
            "project_verification_hook: scripts/verify-product",
            answers.read_text(encoding="utf-8"),
            flags=re.M,
        ),
        encoding="utf-8",
    )
    write_executable(
        project / "scripts" / "verify-product",
        "#!/usr/bin/env bash\nset -euo pipefail\ntouch hook-ran\n",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: configured update hook")
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
                "--check",
                "--json",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["project_verification_hook"] == {
        "configured": True,
        "path": "scripts/verify-product",
        "reason": (
            "Configuration validated; the hook runs before an update is "
            "applied."
        ),
        "result": "not-run",
        "source": "explicit",
    }
    assert not (project / "hook-ran").exists()
    assert git(project, "status", "--porcelain") == ""


@pytest.mark.parametrize(
    ("hook_path", "error"),
    [
        ("scripts/missing", "does not exist"),
        ("../verify", "safe repository-relative"),
    ],
)
@pytest.mark.large
def test_update_check_rejects_invalid_hook_without_writes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    hook_path: str,
    error: str,
) -> None:
    """Reject missing or unsafe hooks during the read-only update check."""
    source, project, _ = initialize_project(tmp_path)
    capsys.readouterr()
    answers = project / ".copier-answers.yml"
    answers.write_text(
        re.sub(
            r"^project_verification_hook:.*$",
            f"project_verification_hook: {hook_path}",
            answers.read_text(encoding="utf-8"),
            flags=re.M,
        ),
        encoding="utf-8",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    base = commit(project, "test: invalid update hook")
    before_files = cli.target_file_snapshot(project)
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
                "--check",
                "--json",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert error in captured.out + captured.err
    assert git(project, "rev-parse", "HEAD") == base
    assert git(project, "status", "--porcelain") == ""
    assert cli.target_file_snapshot(project) == before_files


@pytest.mark.large
def test_update_hook_failure_leaves_target_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify a staged update before applying any candidate bytes."""
    source, project, _ = initialize_project(tmp_path)
    capsys.readouterr()
    answers = project / ".copier-answers.yml"
    answers.write_text(
        re.sub(
            r"^project_verification_hook:.*$",
            "project_verification_hook: scripts/verify-product",
            answers.read_text(encoding="utf-8"),
            flags=re.M,
        ),
        encoding="utf-8",
    )
    write_executable(
        project / "scripts" / "verify-product",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "printf staged > hook-ran\nexit 23\n",
    )
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    base = commit(project, "test: failing update hook")
    before_files = cli.target_file_snapshot(project)
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
                "--yes",
                "--non-interactive",
            ]
        )
        == 2
    )
    assert "Project verification hook failed" in capsys.readouterr().err
    assert git(project, "rev-parse", "HEAD") == base
    assert git(project, "status", "--porcelain") == ""
    assert cli.target_file_snapshot(project) == before_files
    assert not (project / "hook-ran").exists()


@pytest.mark.large
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
                "--to",
                revision,
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert "Repository changed" in capsys.readouterr().err
    assert (project / "managed.txt").read_text(encoding="utf-8") == (
        "template version one\n"
    )


@pytest.mark.large
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
                "--to",
                revision,
                "--allow-unreleased",
            ]
        )
        == 2
    )
    assert "Repository context changed" in capsys.readouterr().err
    assert (project / "managed.txt").read_text(encoding="utf-8") == (
        "template version one\n"
    )


@pytest.mark.parametrize(
    ("saved_channel", "explicit_channel", "expected_channel"),
    [
        (
            "Open a GitHub Issue at https://github.com/old/repository/"
            "issues/new; maintainers receive notifications for new Issues.",
            None,
            "Open a GitHub Issue at https://github.com/new/repository/"
            "issues/new; maintainers receive notifications for new Issues.",
        ),
        (
            "Use the approved private reporting channel.",
            None,
            "Use the approved private reporting channel.",
        ),
        (
            "Open a GitHub Issue at https://github.com/old/repository/"
            "issues/new; maintainers receive notifications for new Issues.",
            "Use the newly approved reporting channel.",
            "Use the newly approved reporting channel.",
        ),
    ],
)
def test_update_repository_rename_preserves_custom_security_channel(
    saved_channel: str,
    explicit_channel: str | None,
    expected_channel: str,
) -> None:
    """Only move a repository-derived reporting channel to the new URL."""
    answers: dict[str, object] = {
        "language": "python",
        "project_visibility": "private",
        "repository_url": "https://github.com/old/repository",
        "security_reporting_channel": saved_channel,
    }
    explicit_data = (
        {"security_reporting_channel": explicit_channel}
        if explicit_channel is not None
        else {}
    )
    repository = cli.RepositoryContext(
        "new/repository",
        "new",
        "Organization",
        "private",
        "github",
        True,
    )

    result, update_data = cli.update_plan_answers(
        answers, explicit_data, repository
    )

    assert result["repository_url"] == "https://github.com/new/repository"
    assert result["security_reporting_channel"] == expected_channel
    if saved_channel == expected_channel and explicit_channel is None:
        assert "security_reporting_channel" not in update_data


@pytest.mark.large
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
                "--to",
                revision,
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


@pytest.mark.large
def test_update_recomputes_visibility_defaults_from_github(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Migrate stale private defaults when GitHub reports a public repo."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "public-project"
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
                "--data",
                "language=python",
                "--yes",
                "--non-interactive",
            ]
        )
        == 0
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


@pytest.mark.large
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


@pytest.mark.large
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


def test_large_adoption_tests_are_excluded_from_bounded_gates() -> None:
    """Keep fast and compatibility gates narrow without weakening full gates."""

    def pytest_commands(path: Path) -> list[list[str]]:
        source = path.read_text(encoding="utf-8").replace("\\\n", " ")
        return [
            shlex.split(line.strip())
            for line in source.splitlines()
            if line.strip().startswith("uv run pytest")
        ]

    def excludes_large(command: list[str]) -> bool:
        return any(
            command[index : index + 2] == ["-m", "not large"]
            for index in range(len(command) - 1)
        )

    for config in (
        ROOT / "pyproject.toml",
        ROOT / "template/pyproject.toml.jinja",
    ):
        pytest_section = (
            config.read_text(encoding="utf-8")
            .split("[tool.pytest.ini_options]", 1)[1]
            .split("\n[", 1)[0]
        )
        assert any(
            line.strip().startswith('"large:')
            for line in pytest_section.splitlines()
        )

    for bounded_gate in (
        ROOT / "scripts/verify-fast",
        ROOT / "template/scripts/verify-fast.jinja",
    ):
        commands = pytest_commands(bounded_gate)
        assert commands
        assert all(excludes_large(command) for command in commands)

    root_full_commands = pytest_commands(ROOT / "scripts/verify-template.sh")
    assert root_full_commands
    assert not any(excludes_large(command) for command in root_full_commands)

    template_commands = pytest_commands(ROOT / "template/scripts/verify.jinja")
    assert len(template_commands) > 1
    assert any(excludes_large(command) for command in template_commands)
    assert any(not excludes_large(command) for command in template_commands)

    marked_large = {
        name
        for name, value in globals().items()
        if name.startswith("test_")
        and any(
            marker.name == "large"
            for marker in getattr(value, "pytestmark", ())
        )
    }
    assert marked_large == {
        "test_adopt_applies_exact_plan_over_preserved_dirty_file",
        "test_adopt_defaults_to_dry_run_and_preserves_product_files",
        "test_adopt_finalize_does_not_trust_edited_checkpoint_fingerprints",
        "test_adopt_finalize_failure_keeps_actionable_pending_state",
        "test_adopt_finalize_rechecks_repository_context_after_confirmation",
        "test_adopt_finalize_rejects_preserved_managed_file_drift",
        "test_adopt_finalize_rejects_repository_drift",
        "test_adopt_finalize_rejects_source_and_managed_file_drift",
        "test_adopt_finalize_rejects_unexpected_worktree_state",
        "test_adopt_finalize_requires_matching_second_stage_plan",
        "test_adopt_infers_unicode_repository_and_applies_exact_plan",
        "test_adopt_rechecks_repository_context_after_confirmation",
        "test_adopt_rechecks_target_after_confirmation",
        "test_adopt_rejects_plan_tampering_and_target_drift",
        "test_adoption_preserves_executable_and_checked_patch_symlink",
        "test_adoption_records_and_replays_explicit_project_hook",
        "test_adoption_report_failure_keeps_markdown",
        "test_init_dry_run_and_apply_pin_full_sha",
        "test_invalid_project_hook_blocks_pending_adoption_without_writes",
        "test_legacy_update_conflict_leaves_target_unchanged",
        "test_project_hook_rejects_unsafe_or_unusable_paths",
        "test_real_existing_adoption_uses_fixed_ownership_policies",
        "test_real_template_adoption_resumes_after_manifest_merge",
        "test_update_check_dry_run_apply_and_conflict",
        "test_update_check_rejects_invalid_hook_without_writes",
        "test_update_check_reports_capability_drift_at_same_revision",
        "test_update_hook_failure_leaves_target_unchanged",
        "test_update_migrates_legacy_copier_answers_to_single_config",
        "test_update_plan_resolves_target_answers_and_capabilities",
        "test_update_rechecks_committed_head_after_confirmation",
        "test_update_rechecks_repository_context_after_confirmation",
        "test_update_rechecks_snapshot_after_repository_context",
        "test_update_recomputes_visibility_defaults_from_github",
    }
