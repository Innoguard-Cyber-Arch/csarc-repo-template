"""Replayable update final plan (Issue #1067)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from test_cli import commit, git, make_template

from csarc_cli import cli, file_transition, final_plan
from csarc_cli.cli import main

ROOT = Path(__file__).resolve().parents[1]
OLD_PIN = "1" * 40
NEW_PIN = "2" * 40


def write(path: Path, content: str) -> None:
    """Write one fixture file, creating its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def workflow(pin: str) -> str:
    """Return a workflow that pins actions/checkout at ``pin``."""
    return (
        "on: push\njobs:\n  job:\n    runs-on: ubuntu-latest\n    steps:\n"
        f"      - uses: actions/checkout@{pin} # v1\n"
    )


def sealed_fixture() -> dict[str, object]:
    """Return one minimal sealed final plan."""
    return final_plan.seal(
        {
            "created_at": "2026-10-14T00:00:00+00:00",
            "decisions": {"files": []},
            "derived": {"planning": {}},
            "inputs": {"answers": {"language": "ci"}},
            "kind": final_plan.FINAL_PLAN_KIND,
            "live_facts": {"origin": None},
            "replayable": True,
            "report": {},
            "schema_version": final_plan.SCHEMA_VERSION,
            "stage1_plan": {"path": "csarc-update-plan.json", "sha256": "0"},
            "target": "/srv/product",
            "toolchain": dict(final_plan.PINNED_TOOLS),
        }
    )


# --- Pure contract -----------------------------------------------------------


def test_sealed_plan_detects_any_tampering(tmp_path: Path) -> None:
    """AC1/R1: every section and the whole plan are bound to digests."""
    sealed = sealed_fixture()
    path = tmp_path / final_plan.FINAL_PLAN_BASENAME
    path.write_text(final_plan.plan_text(sealed), encoding="utf-8")
    assert final_plan.load(path) == sealed

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["inputs"]["answers"]["language"] = "python"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(final_plan.FinalPlanError, match="inputs"):
        final_plan.load(path)

    resealed = json.loads(final_plan.plan_text(sealed))
    resealed["target"] = "/srv/other"
    with pytest.raises(final_plan.FinalPlanError, match="digest"):
        final_plan.verify(resealed)

    not_replayable = dict(sealed, replayable=False)
    with pytest.raises(final_plan.FinalPlanError, match="replayable"):
        final_plan.verify(not_replayable)
    with pytest.raises(final_plan.FinalPlanError, match="shape"):
        final_plan.verify(dict(sealed, extra=True))


def test_stage1_plan_must_be_marked_not_replayable(tmp_path: Path) -> None:
    """AC1: only a digest-bound, non-replayable stage-1 plan is accepted."""
    body: dict[str, object] = {"mode": "update", "replayable": False}
    body["plan_sha256"] = final_plan.stage1_digest(body)
    path = tmp_path / "csarc-update-plan.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    assert final_plan.load_stage1(path) == body

    body["replayable"] = True
    body["plan_sha256"] = final_plan.stage1_digest(body)
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(final_plan.FinalPlanError, match="non-replayable"):
        final_plan.load_stage1(path)


def test_file_decisions_must_cover_each_conflict_exactly() -> None:
    """AC1: one decision per conflict; unknown choices fail closed."""
    parsed = final_plan.parse_file_decisions(
        ["a.txt=keep-current", "b.txt=take-new", "c.txt=custom:/srv/c"]
    )
    assert parsed["a.txt"] == ("keep-current", None)
    assert parsed["c.txt"] == ("custom", Path("/srv/c"))
    final_plan.require_complete_decisions(("a.txt", "b.txt", "c.txt"), parsed)
    with pytest.raises(final_plan.FinalPlanError, match=r"missing.*d\.txt"):
        final_plan.require_complete_decisions(("a.txt", "d.txt"), parsed)
    for invalid in (["a.txt=merge"], ["a.txt"], ["a.txt=custom:"]):
        with pytest.raises(final_plan.FinalPlanError):
            final_plan.parse_file_decisions(invalid)
    with pytest.raises(final_plan.FinalPlanError, match="Duplicate"):
        final_plan.parse_file_decisions(["a.txt=take-new", "a.txt=take-new"])


def test_recorded_content_and_values_replay_exactly() -> None:
    """R1: decision bytes are digest-bound; values must be plain JSON."""
    entry = final_plan.resolution("a.txt", "custom", b"resolved\n")
    assert final_plan.resolution_content(entry) == b"resolved\n"
    assert (
        final_plan.resolution_content(
            final_plan.resolution("a.txt", "take-new", None)
        )
        is None
    )
    entry["content_sha256"] = "0" * 64
    with pytest.raises(final_plan.FinalPlanError, match="digest"):
        final_plan.resolution_content(entry)
    with pytest.raises(final_plan.FinalPlanError, match="round-trip"):
        final_plan.exact_json({"moves": ("a", "b")}, "Inputs")
    assert final_plan.live_fact_differences(
        {"origin": None, "repository": {"visibility": "private"}},
        {"origin": None, "repository": {"visibility": "public"}},
    ) == ["repository"]


def test_copier_and_jinja_use_one_exact_pin_everywhere() -> None:
    """AC5/R4: pyproject, uv.lock, runtime, and template workflow agree."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    for name, version in final_plan.PINNED_TOOLS.items():
        assert f"{name}=={version}" in dependencies
    lock = tomllib.loads((ROOT / "uv.lock").read_text("utf-8"))
    locked = {item["name"]: item["version"] for item in lock["package"]}
    toolchain = final_plan.observe_toolchain(lambda: "git version test")
    for name, version in final_plan.PINNED_TOOLS.items():
        assert locked[name] == version
        assert toolchain[name] == version
    final_plan.require_pinned_toolchain(toolchain)
    assert {"csarc", "git", "python"} <= set(toolchain)
    workflow_text = (
        ROOT / "template/.github/workflows/template-update.yml.jinja"
    ).read_text("utf-8")
    assert (
        f"uv tool install copier=={final_plan.PINNED_TOOLS['copier']} "
        f"--with jinja2=={final_plan.PINNED_TOOLS['jinja2']}"
    ) in workflow_text
    with pytest.raises(final_plan.FinalPlanError, match="Unsupported"):
        final_plan.require_pinned_toolchain(dict(toolchain, copier="9.17.2"))


# --- One real check -> decision -> apply ------------------------------------


def target_state(project: Path) -> tuple[str, str, str]:
    """Return the tree digest, HEAD, and status of one fixture target."""
    return (
        file_transition.tree_digest(project),
        git(project, "rev-parse", "HEAD"),
        git(project, "status", "--porcelain", "--untracked-files=all"),
    )


def updated_fixture(tmp_path: Path) -> tuple[Path, str, Path]:
    """Create a product whose update has conflicts, a delete, and pin drift."""
    source, _first = make_template(tmp_path)
    template = source / "template"
    for name in ("keep.txt", "take.txt", "custom.txt"):
        write(template / name, "line one\nline two\n")
    write(template / "obsolete.txt", "csarc generated\n")
    write(template / ".github/workflows/ci.yml", workflow(OLD_PIN))
    old_sha = commit(source, "test: conflict fixture one")
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
    for name in ("keep.txt", "take.txt", "custom.txt"):
        write(project / name, "line one product\nline two\n")
    write(project / ".github/workflows/product.yml", workflow(OLD_PIN))
    git(project, "init", "-b", "main")
    git(project, "config", "user.name", "CLI Test")
    git(project, "config", "user.email", "cli-test@example.invalid")
    commit(project, "test: product changes")

    for name in ("keep.txt", "take.txt", "custom.txt"):
        write(template / name, "line one template\nline two\n")
    (template / "obsolete.txt").unlink()
    write(template / ".github/workflows/ci.yml", workflow(NEW_PIN))
    new_sha = commit(source, "test: conflict fixture two")
    return project, new_sha, project.parent / "product-csarc-update-report"


def update(project: Path, revision: str, *extra: str) -> int:
    """Run one ``csarc update`` command against the fixture revision."""
    return main(
        [
            "update",
            str(project),
            "--to",
            revision,
            "--allow-unreleased",
            "--data",
            "copilot_review=allowed",
            *extra,
        ]
    )


def apply(project: Path, plan: Path) -> int:
    """Apply one final plan non-interactively."""
    return main(
        [
            "update",
            str(project),
            "--apply-plan",
            str(plan),
            "--yes",
            "--non-interactive",
        ]
    )


@pytest.mark.large
def test_check_decide_apply_replays_one_final_plan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1-AC4/AC6 through one real three-way update.

    The update has three conflicts (kept, taken from the template, and
    resolved by hand), a template deletion, product action pin drift, and an
    explicit governance setting change. Tampering, live-fact drift, a
    toolchain change, and an injected write failure all leave the target
    byte-identical; the successful apply binds provenance and the report to
    the final plan, and replaying it is an explicit no-op.
    """
    project, new_sha, report_dir = updated_fixture(tmp_path)
    capsys.readouterr()

    # Stage 1: a reviewable, non-replayable plan.
    assert update(project, new_sha, "--check") == 1
    stage1_path = report_dir / "csarc-update-plan.json"
    stage1 = json.loads(stage1_path.read_text(encoding="utf-8"))
    assert stage1["replayable"] is False
    conflicts = stage1["planning"]["conflicts"]
    assert conflicts == ["custom.txt", "keep.txt", "take.txt"]
    assert stage1["files"]["delete"] == ["obsolete.txt"]
    assert [
        item["file"] for item in stage1["action_pin_preflight"]["items"]
    ] == [".github/workflows/product.yml"]
    stage1_bytes = stage1_path.read_bytes()
    capsys.readouterr()

    # Decisions: the pin drift is fixed by a product commit first.
    write(project / ".github/workflows/product.yml", workflow(NEW_PIN))
    pin_commit = commit(project, "fix: pin checkout like the template")
    resolved = tmp_path / "custom-resolution.txt"
    write(resolved, "line one product and template\nline two\n")
    decisions = [
        "--decision",
        "keep.txt=keep-current",
        "--decision",
        "take.txt=take-new",
        "--decision",
        f"custom.txt=custom:{resolved}",
    ]
    assert update(project, new_sha, "--finalize-plan", *decisions[:4]) == 2
    assert "missing a decision: custom.txt" in capsys.readouterr().err
    assert update(project, new_sha, "--finalize-plan", *decisions) == 2
    assert "--pin-commit" in capsys.readouterr().err
    before = target_state(project)
    assert (
        update(
            project,
            new_sha,
            "--finalize-plan",
            *decisions,
            "--pin-commit",
            pin_commit,
        )
        == 0
    )
    capsys.readouterr()
    assert target_state(project) == before
    assert stage1_path.read_bytes() == stage1_bytes
    plan_path = report_dir / final_plan.FINAL_PLAN_BASENAME
    sealed: dict[str, Any] = final_plan.load(plan_path)
    digest = sealed["final_plan_sha256"]
    recorded = sealed["decisions"]
    assert {
        entry["path"]: entry["decision"] for entry in recorded["files"]
    } == {
        "custom.txt": "custom",
        "keep.txt": "keep-current",
        "take.txt": "take-new",
    }
    assert recorded["action_pins"]["commit"] == pin_commit
    assert any(
        row["key"] == "copilot_review" and row["after"] == "allowed"
        for row in recorded["settings"]
    )
    assert set(sealed["toolchain"]) == {
        "copier",
        "csarc",
        "git",
        "jinja2",
        "python",
    }
    assert sealed["inputs"]["arguments"]["to"] == new_sha
    assert sealed["live_facts"]["target"]["target_head"] == pin_commit
    report = json.loads(
        (report_dir / "csarc-update-report.json").read_text(encoding="utf-8")
    )
    assert report["final_plan"]["sha256"] == digest
    assert report["final_plan"]["replayable"] is True
    assert report["plan"]["sha256"] == stage1["plan_sha256"]
    assert not any(
        action["kind"] == "file-conflict"
        for action in report["required_actions"]
    )
    # A final plan is immutable: deciding again needs an explicit removal.
    assert (
        update(
            project,
            new_sha,
            "--finalize-plan",
            *decisions,
            "--pin-commit",
            pin_commit,
        )
        == 2
    )
    assert "immutable" in capsys.readouterr().err

    # AC2: apply takes no new inputs.
    assert (
        main(
            [
                "update",
                str(project),
                "--apply-plan",
                str(plan_path),
                "--data",
                "copilot_review=off",
                "--yes",
            ]
        )
        == 2
    )
    assert "remove --data" in capsys.readouterr().err

    # R1: a tampered plan never reaches the target.
    original = plan_path.read_bytes()
    tampered = json.loads(original)
    tampered["inputs"]["new_data"]["copilot_review"] = "off"
    plan_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert apply(project, plan_path) == 2
    assert "inputs" in capsys.readouterr().err
    assert target_state(project) == before
    plan_path.write_bytes(original)

    # AC3/R2: live facts and the toolchain are re-observed before apply.
    real_context = cli.repository_context

    def public_context(
        target: Path,
        explicit_visibility: str | None,
        *,
        saved_visibility: str | None = None,
    ) -> cli.RepositoryContext:
        context = real_context(
            target, explicit_visibility, saved_visibility=saved_visibility
        )
        return cli.RepositoryContext(
            context.repository,
            context.owner,
            context.owner_type,
            "public",
            context.source,
            context.verified,
            context.reason,
        )

    monkeypatch.setattr(cli, "repository_context", public_context)
    assert apply(project, plan_path) == 2
    assert "Live facts differ from the final plan (repository)" in (
        capsys.readouterr().err
    )
    monkeypatch.setattr(cli, "repository_context", real_context)
    assert target_state(project) == before

    monkeypatch.setattr(
        cli, "repository_permissions", lambda _repository: {"push": False}
    )
    assert apply(project, plan_path) == 2
    assert "(permissions)" in capsys.readouterr().err
    monkeypatch.undo()
    assert target_state(project) == before

    git(project, "remote", "add", "origin", "https://example.invalid/x.git")
    assert apply(project, plan_path) == 2
    assert "origin" in capsys.readouterr().err
    git(project, "remote", "remove", "origin")
    assert target_state(project) == before

    real_toolchain = final_plan.observe_toolchain
    monkeypatch.setattr(
        final_plan,
        "observe_toolchain",
        lambda git_version: dict(real_toolchain(git_version), git="git 0.0"),
    )
    assert apply(project, plan_path) == 2
    assert "toolchain differs from the final plan (git)" in (
        capsys.readouterr().err
    )
    monkeypatch.undo()
    assert target_state(project) == before

    # R3: a failure in the middle of the write restores the base.
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
    assert apply(project, plan_path) == 2
    assert "target was restored" in capsys.readouterr().err
    monkeypatch.undo()
    assert target_state(project) == before

    # AC2/AC4: the apply realizes exactly the recorded decisions.
    assert apply(project, plan_path) == 0
    assert f"Applied final plan {digest}" in capsys.readouterr().out
    assert (project / "keep.txt").read_text(encoding="utf-8") == (
        "line one product\nline two\n"
    )
    assert (project / "take.txt").read_text(encoding="utf-8") == (
        "line one template\nline two\n"
    )
    assert (project / "custom.txt").read_bytes() == resolved.read_bytes()
    assert not (project / "obsolete.txt").exists()
    provenance = json.loads(
        (project / ".csarc/provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["final_plan_sha256"] == digest
    assert provenance["commit_sha"] == new_sha
    answers = yaml.safe_load(
        (project / ".copier-answers.yml").read_text(encoding="utf-8")
    )
    assert answers["copilot_review"] == "allowed"
    assert answers["_commit"] == new_sha
    applied = json.loads(
        (report_dir / "csarc-update-report.json").read_text(encoding="utf-8")
    )
    assert applied["status"] == "applied"
    assert applied["final_plan"]["sha256"] == digest
    assert plan_path.read_bytes() == original

    # AC4: replaying the same plan is a readable no-op.
    after = target_state(project)
    assert apply(project, plan_path) == 0
    assert "already applied" in capsys.readouterr().out
    assert target_state(project) == after
