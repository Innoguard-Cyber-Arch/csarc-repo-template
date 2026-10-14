"""Approved file transitions and product release state (Issue #1066)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
import settings_support
from test_cli import commit, git, make_template

from csarc_cli import cli, file_transition
from csarc_cli.cli import main as cli_main


def main(arguments: list[str] | None = None) -> int:
    """Run the CLI with the explicit setup seeds a script passes (#1078)."""
    return cli_main(settings_support.seeded_setup(arguments))


def write(path: Path, content: str) -> None:
    """Write one fixture file, creating its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def fingerprints(root: Path, names: tuple[str, ...]) -> dict[str, str]:
    """Fingerprint the named fixture files."""
    result: dict[str, str] = {}
    for name in names:
        value = file_transition.fingerprint(root / name)
        assert value is not None
        result[name] = value
    return result


# --- Pure transition rules ---------------------------------------------------


def test_retirement_requires_byte_identical_old_render(tmp_path: Path) -> None:
    """AC2: only unmodified CSARC-rendered files retire."""
    old = tmp_path / "old"
    target = tmp_path / "target"
    for name in ("same.toml", "edited.toml"):
        write(old / name, "csarc\n")
    write(target / "same.toml", "csarc\n")
    write(target / "edited.toml", "csarc\nuser change\n")
    write(target / "unknown.toml", "never rendered\n")
    old_render = fingerprints(old, ("same.toml", "edited.toml"))

    retire, retained = file_transition.split_retirements(
        ("same.toml", "edited.toml", "unknown.toml"), target, old_render
    )

    assert retire == ("same.toml",)
    assert retained == ("edited.toml", "unknown.toml")


def test_protect_deletions_restores_only_modified_files(
    tmp_path: Path,
) -> None:
    """AC2/AC5: a Copier deletion of a user-modified file is undone."""
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    write(baseline / "clean.txt", "csarc\n")
    write(baseline / "custom.txt", "user change\n")
    write(baseline / "answers.yml", "answers\n")
    old_render = {
        "clean.txt": file_transition.fingerprint(baseline / "clean.txt"),
        "custom.txt": "a-different-old-render",
    }
    candidate.mkdir()

    def restore(names: Sequence[str]) -> None:
        for name in names:
            write(
                candidate / name,
                (baseline / name).read_text(encoding="utf-8"),
            )

    retained = file_transition.protect_deletions(
        candidate,
        ("answers.yml", "clean.txt", "custom.txt"),
        {key: value for key, value in old_render.items() if value},
        {"answers.yml"},
        restore,
    )

    assert retained == ("custom.txt",)
    assert not (candidate / "clean.txt").exists()
    assert (candidate / "custom.txt").read_text(encoding="utf-8") == (
        "user change\n"
    )
    assert not (candidate / "answers.yml").exists()


def test_product_state_survives_seed_and_layout_move(tmp_path: Path) -> None:
    """AC3/AC5: release state keeps product content, even when it moves."""
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    write(baseline / "version.txt", "1.4.0\n")
    write(baseline / "CHANGELOG.md", "# Changelog\n\n## 1.4.0\n")
    # Copier's view: the legacy file is gone, the seed reappeared at the
    # canonical path, and the changelog seed changed.
    write(candidate / ".csarc/version.txt", "0.2.0\n")
    write(candidate / "CHANGELOG.md", "# Changelog\n\nseed two\n")

    def restore(names: Sequence[str]) -> None:
        for name in names:
            write(
                candidate / name,
                (baseline / name).read_text(encoding="utf-8"),
            )

    protected, completed = file_transition.protect_product_state(
        candidate,
        ("CHANGELOG.md", "version.txt"),
        (("version.txt", ".csarc/version.txt"),),
        restore,
    )

    assert protected == (".csarc/version.txt", "CHANGELOG.md")
    assert completed == (("version.txt", ".csarc/version.txt"),)
    assert (candidate / ".csarc/version.txt").read_text(encoding="utf-8") == (
        "1.4.0\n"
    )
    assert not (candidate / "version.txt").exists()
    assert (candidate / "CHANGELOG.md").read_text(encoding="utf-8") == (
        "# Changelog\n\n## 1.4.0\n"
    )
    # A repository without release state receives the seed untouched.
    assert file_transition.protect_product_state(
        candidate, (), (), restore
    ) == ((), ())


def test_transition_set_must_equal_the_approved_plan() -> None:
    """AC1/AC5: extra, missing, or product-state effects fail closed."""
    approved = file_transition.approved_transitions(
        add=("new.txt",),
        overwrite=("managed.txt",),
        merge=("merged.txt",),
        delete=("gone.txt",),
        retire=("retired.toml",),
        moves=(("version.txt", ".csarc/version.txt"),),
        target_files=(
            "CHANGELOG.md",
            "gone.txt",
            "managed.txt",
            "merged.txt",
            "preserved.txt",
            "retired.toml",
            "version.txt",
            ".csarc/config.yml",
        ),
        metadata=(".csarc/config.yml", ".csarc/provenance.json"),
        protected=("CHANGELOG.md",),
    )
    target = (
        "CHANGELOG.md",
        "gone.txt",
        "managed.txt",
        "merged.txt",
        "preserved.txt",
        "retired.toml",
        "version.txt",
        ".csarc/config.yml",
    )
    writes = (
        "new.txt",
        "managed.txt",
        "merged.txt",
        ".csarc/version.txt",
        ".csarc/config.yml",
    )
    deletions = ("gone.txt", "retired.toml", "version.txt")
    assert approved.as_dict()["create"] == [".csarc/version.txt", "new.txt"]
    assert (
        file_transition.transition_divergence(
            approved, writes, deletions, target
        )
        == []
    )
    # Deleting a file the plan preserves is never approved.
    assert file_transition.transition_divergence(
        approved, writes, (*deletions, "preserved.txt"), target
    ) == ["unapproved delete: preserved.txt"]
    assert file_transition.transition_divergence(
        approved, (*writes, "CHANGELOG.md", "extra.html"), deletions, target
    ) == [
        "product release state changed: CHANGELOG.md",
        "unapproved create: extra.html",
        "unapproved modify: CHANGELOG.md",
    ]
    assert file_transition.transition_divergence(
        approved, ("new.txt",), (), target
    ) == [
        "approved create not realized: .csarc/version.txt",
        "approved modify not realized: managed.txt, merged.txt",
        "approved delete not realized: gone.txt, retired.toml, version.txt",
    ]


def transaction_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """Build one target and candidate pair for transaction tests."""
    target = tmp_path / "target"
    candidate = tmp_path / "candidate"
    write(target / "keep.txt", "keep\n")
    write(target / "managed.txt", "old\n")
    write(target / "old/gone.txt", "gone\n")
    write(candidate / "managed.txt", "new\n")
    write(candidate / "deep/new/added.txt", "added\n")
    writes = fingerprints(candidate, ("deep/new/added.txt", "managed.txt"))
    return target, candidate, writes


def test_transaction_applies_exact_writes_and_deletions(
    tmp_path: Path,
) -> None:
    """AC4: a successful transaction lands every approved effect."""
    target, candidate, writes = transaction_fixture(tmp_path)

    file_transition.apply_transaction(
        target, candidate, writes, ("old/gone.txt",)
    )

    assert (target / "managed.txt").read_text(encoding="utf-8") == "new\n"
    assert (target / "deep/new/added.txt").is_file()
    assert not (target / "old").exists()
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep\n"


@pytest.mark.parametrize("failing", ["deep/new/added.txt", "managed.txt"])
@pytest.mark.parametrize("deleting", [True, False])
def test_transaction_failure_restores_byte_identical_base(
    tmp_path: Path, failing: str, deleting: bool
) -> None:
    """AC4: a failure at any step leaves the target byte-identical."""
    target, candidate, writes = transaction_fixture(tmp_path)
    before = file_transition.tree_digest(target)
    deletions = ("old/gone.txt",) if deleting else ()

    def inject(name: str) -> None:
        if name == failing:
            raise OSError("injected failure")

    with pytest.raises(OSError, match="injected failure"):
        file_transition.apply_transaction(
            target, candidate, writes, deletions, on_step=inject
        )

    assert file_transition.tree_digest(target) == before
    assert not list(target.rglob("*.rej"))
    assert not list(target.rglob("*.csarc-transaction"))


def test_transaction_rejects_content_that_changed_after_review(
    tmp_path: Path,
) -> None:
    """AC4: a candidate that no longer matches its fingerprint rolls back."""
    target, candidate, writes = transaction_fixture(tmp_path)
    before = file_transition.tree_digest(target)
    write(candidate / "managed.txt", "tampered\n")

    with pytest.raises(file_transition.TransitionError, match=r"managed\.txt"):
        file_transition.apply_transaction(
            target, candidate, writes, ("old/gone.txt",)
        )

    assert file_transition.tree_digest(target) == before


# --- One real Copier update ---------------------------------------------------


def update_arguments(project: Path, revision: str) -> list[str]:
    """Return the non-interactive update command for one fixture."""
    return [
        "update",
        str(project),
        "--to",
        revision,
        "--allow-unreleased",
        "--yes",
        "--non-interactive",
    ]


def target_state(project: Path) -> tuple[str, str, str]:
    """Return the tree digest, HEAD, and status of one fixture target."""
    return (
        file_transition.tree_digest(project),
        git(project, "rev-parse", "HEAD"),
        git(project, "status", "--porcelain", "--untracked-files=all"),
    )


@pytest.mark.large
def test_update_applies_only_approved_transitions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1-AC5 through one real three-way update.

    The old template renders product release state at its legacy path, a
    changelog seed, and two files the new template stops rendering; the
    repository bumps its version, records a release, and edits one of the
    soon-retired files. Injected apply-time failures must leave the target
    byte-identical, and the successful apply must keep product state and
    the edited file while retiring only the untouched one.
    """
    source, _first = make_template(tmp_path)
    template = source / "template"
    write(template / "version.txt", "0.1.0-beta.1\n")
    write(template / "CHANGELOG.md", "# Changelog\n")
    write(template / "obsolete.txt", "csarc generated\n")
    write(template / "customized.txt", "csarc generated\n")
    old_sha = commit(source, "test: legacy release state")
    project = tmp_path / "product"
    assert (
        main(
            [
                "init",
                "--data",
                "repository_url=https://github.com/example-org/product",
                str(project),
                "--source",
                str(source),
                "--to",
                old_sha,
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
                "--data",
                "language=ci",
            ]
        )
        == 0
    )
    write(project / "version.txt", "1.4.0\n")
    write(project / "CHANGELOG.md", "# Changelog\n\n## 1.4.0\n")
    write(project / "customized.txt", "csarc generated\nproduct note\n")
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: released product")

    (template / "version.txt").unlink()
    (template / "obsolete.txt").unlink()
    (template / "customized.txt").unlink()
    write(template / ".csarc/version.txt", "0.2.0\n")
    write(template / "CHANGELOG.md", "# Changelog\n\nseed two\n")
    write(template / "managed.txt", "template version two\n")
    new_sha = commit(source, "test: canonical release state")
    capsys.readouterr()

    assert (
        main(
            [
                "update",
                str(project),
                "--check",
                "--json",
                "--to",
                new_sha,
                "--allow-unreleased",
            ]
        )
        == 1
    )
    plan = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    files = plan["files"]
    assert files["retained"] == ["customized.txt"]
    assert files["product_owned"] == ["CHANGELOG.md"]
    assert files["delete"] == ["obsolete.txt"]
    assert "version.txt -> .csarc/version.txt" in files["move"]
    assert "customized.txt" not in files["preserve"]
    assert plan["planning"]["conflicts"] == []
    report_dir = project.parent / f"{project.name}-csarc-update-report"
    report = json.loads(
        (report_dir / "csarc-update-report.json").read_text(encoding="utf-8")
    )
    rows = {
        row["path"]: (row["action"], row["reason"]) for row in report["files"]
    }
    assert rows["customized.txt"] == ("conflict", "retire-modified")
    assert rows["CHANGELOG.md"] == ("preserve", "product-owned")
    assert rows["obsolete.txt"] == ("remove", "template-deleted")
    assert any(
        action["kind"] == "retire-modified" and not action["blocking"]
        for action in report["required_actions"]
    )

    before = target_state(project)
    # AC1: an apply-time effect the plan never approved fails closed.
    original_verify = cli.verify_project

    def verify_with_extra_output(candidate: Path) -> dict[str, object]:
        write(candidate / "unplanned.txt", "extra\n")
        return original_verify(candidate)

    monkeypatch.setattr(cli, "verify_project", verify_with_extra_output)
    assert main(update_arguments(project, new_sha)) == 2
    error = capsys.readouterr().err
    assert "unapproved create: unplanned.txt" in error
    assert target_state(project) == before
    monkeypatch.setattr(cli, "verify_project", original_verify)

    # AC4: a failure in the middle of the write restores the base.
    original_write = file_transition._Transaction.write
    calls: list[str] = []

    def failing_write(
        self: file_transition._Transaction, name: str, source_path: Path
    ) -> None:
        calls.append(name)
        if len(calls) == 2:
            raise OSError("injected write failure")
        original_write(self, name, source_path)

    monkeypatch.setattr(file_transition._Transaction, "write", failing_write)
    assert main(update_arguments(project, new_sha)) == 2
    assert "target was restored" in capsys.readouterr().err
    assert len(calls) == 2
    assert target_state(project) == before
    monkeypatch.setattr(file_transition._Transaction, "write", original_write)

    assert main(update_arguments(project, new_sha)) == 0
    assert (project / ".csarc/version.txt").read_text(encoding="utf-8") == (
        "1.4.0\n"
    )
    assert not (project / "version.txt").exists()
    assert (project / "CHANGELOG.md").read_text(encoding="utf-8") == (
        "# Changelog\n\n## 1.4.0\n"
    )
    assert (project / "customized.txt").read_text(encoding="utf-8") == (
        "csarc generated\nproduct note\n"
    )
    assert not (project / "obsolete.txt").exists()
    assert (project / "managed.txt").read_text(encoding="utf-8") == (
        "template version two\n"
    )
    assert not list(project.rglob("*.rej"))
    assert "<<<<<<<" not in (project / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
