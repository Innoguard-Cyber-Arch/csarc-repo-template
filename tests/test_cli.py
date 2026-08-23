"""End-to-end tests for the CSARC lifecycle CLI."""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

import pytest

import csarc_cli.cli as cli
from csarc_cli.cli import CliError, main


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
coverage_mode:
  type: str
  default: global
""",
        encoding="utf-8",
    )
    (source / "template" / "managed.txt").write_text(
        "template version one\n", encoding="utf-8"
    )
    (source / "template" / "pyproject.toml").write_text(
        '[project]\nname = "template-project"\n', encoding="utf-8"
    )
    (source / "template" / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "# Changes here will be overwritten by Copier.\n"
        "{{ _copier_answers|to_nice_yaml -}}\n",
        encoding="utf-8",
    )
    write_executable(
        source / "template" / "scripts" / "verify",
        "#!/usr/bin/env bash\nset -euo pipefail\ntest -f managed.txt\n",
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
    script = tmp_path / "release_policy.py"
    script.touch()
    response = {
        "mode": "direct",
        "capabilities": {
            "actions_pull_requests": {"state": "blocked"},
            "contents": {"state": "unknown"},
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
    assert "actions_pull_requests=blocked" in capsys.readouterr().out


def test_adopt_requires_clean_tree_and_preserves_product_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Adopt detects Python and never changes the existing manifest."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "legacy-product"
    project.mkdir()
    manifest = project / "pyproject.toml"
    manifest.write_text(
        '[project]\nname = "legacy-product"\n', encoding="utf-8"
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
    assert main([*arguments, "--yes", "--non-interactive"]) == 0
    assert manifest.read_text(encoding="utf-8") == (
        '[project]\nname = "legacy-product"\n'
    )
    assert (project / ".copier-answers.yml").is_file()


def test_adopt_rejects_dirty_tree(tmp_path: Path) -> None:
    """Adopt refuses tracked or untracked changes."""
    source, first_sha = make_template(tmp_path)
    project = tmp_path / "dirty-product"
    project.mkdir()
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    (project / "tracked.txt").write_text("clean\n", encoding="utf-8")
    commit(project, "test: baseline")
    (project / "untracked.txt").write_text("dirty\n", encoding="utf-8")

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
    assert not (project / ".copier-answers.yml").exists()


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
    assert "<<<<<<<" in (project / "managed.txt").read_text(encoding="utf-8")


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
