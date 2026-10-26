"""Legacy answer reconstruction and update render parity (Issue #1063)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import settings_support
import yaml

from csarc_cli import settings_schema, update_plan
from csarc_cli.cli import main as cli_main


def main(arguments: list[str] | None = None) -> int:
    """Run the CLI with the explicit setup seeds a script passes (#1078)."""
    return cli_main(settings_support.seeded_setup(arguments))


ROOT = Path(__file__).resolve().parents[1]
CODE_OWNER = "@Innoguard-Cyber-Arch/platform"
REPOSITORY_URL = "https://github.com/example-owner/parity-fixture"


def run(command: list[str], cwd: Path) -> str:
    """Run one successful fixture command and return its stdout."""
    return subprocess.run(  # noqa: S603
        command, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def git(repository: Path, *arguments: str) -> str:
    """Run Git in one fixture repository."""
    return run(["git", *arguments], repository)


def commit_all(repository: Path, message: str) -> str:
    """Commit every fixture change and return the full SHA."""
    git(repository, "add", "-A")
    git(repository, "commit", "--quiet", "--no-gpg-sign", "-m", message)
    return git(repository, "rev-parse", "HEAD")


def init_repository(path: Path) -> None:
    """Create one fixture repository with a local identity."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "--quiet", "-b", "main")
    git(path, "config", "user.name", "Parity Test")
    git(path, "config", "user.email", "parity-test@example.invalid")
    git(path, "config", "commit.gpgsign", "false")


# --- Pure planning contract -------------------------------------------------


def test_old_side_keeps_only_asked_answers_and_never_injects_defaults() -> None:
    """AC1: unused saved keys are dropped and missing keys stay old defaults."""
    saved = {
        "code_owner": CODE_OWNER,
        "language": "ci",
        "verification_mode": "hosted",
        "documentation_mode": "template-and-content",
    }
    old = update_plan.reconstruct_old_inputs(
        saved, {"code_owner", "language", "project_name"}, {}
    )

    assert dict(old.answers) == {"code_owner": CODE_OWNER, "language": "ci"}
    assert old.dropped == ("documentation_mode", "verification_mode")
    assert old.sources["project_name"] == update_plan.OLD_SOURCE_DEFAULT
    assert "project_name" not in old.answers
    summary = old.as_dict()
    assert summary["defaulted"] == ["project_name"]
    assert summary["keys"] == ["code_owner", "language"]
    # Values never appear in the auditable summary, only their digest.
    assert CODE_OWNER not in json.dumps(summary)


def test_trusted_snapshot_requires_verified_provenance() -> None:
    """AC1: only verified provenance may fill an unanswered old question."""
    release = {
        "immutable_releases": "required",
        "ownership": "csarc-owned",
        "reason": "CSARC owns the release.",
        "required_inputs": [],
        "selected_workflow": None,
        "settings_owner": "csarc-admin",
    }
    assert update_plan.trusted_snapshot(None) == {}
    assert (
        update_plan.trusted_snapshot(
            {"release": release, "verification": "legacy-unverified"}
        )
        == {}
    )
    snapshot = update_plan.trusted_snapshot(
        {"release": release, "verification": "verified"}
    )
    assert snapshot["release_ownership"] == "csarc-owned"
    assert snapshot["release_workflow"] == ""

    old = update_plan.reconstruct_old_inputs(
        {"release_ownership": "product-owned"},
        {"release_ownership", "release_settings_owner"},
        snapshot,
    )
    # Saved answers win; the snapshot only fills a real gap.
    assert old.answers == {
        "release_ownership": "product-owned",
        "release_settings_owner": "csarc-admin",
    }
    assert old.sources["release_settings_owner"] == (
        update_plan.OLD_SOURCE_SNAPSHOT
    )


def test_new_side_keeps_dropped_intent_and_reviewed_data_wins() -> None:
    """Dropped old-side answers still reach the new side as saved intent."""
    saved = {"language": "ci", "verification_mode": "local"}
    old = update_plan.reconstruct_old_inputs(saved, {"language"}, {})
    assert update_plan.new_side_data(saved, old, {}) == {
        "verification_mode": "local"
    }
    assert update_plan.new_side_data(
        saved, old, {"verification_mode": "hosted", "lifecycle": []}
    ) == {"lifecycle": [], "verification_mode": "hosted"}


def test_self_hosted_settings_are_forwarded_when_copier_hides_them() -> None:
    """#1304 AC2: a stable-to-beta update keeps the VM registration."""
    assert {"self_hosted_runner", "self_hosted_environments"} <= set(
        settings_schema.HIDDEN_SETTINGS
    )


def test_unstable_old_question_set_fails_closed() -> None:
    """AC3: an old baseline that changes once inputs are filtered fails."""
    update_plan.require_stable_old_inputs({"a", "b"}, {"b", "a"})
    with pytest.raises(update_plan.UpdatePlanningError, match="not changed"):
        update_plan.require_stable_old_inputs({"a", "b"}, {"a"})


def test_normalized_diff_and_realized_divergence() -> None:
    """AC2: one normalized diff; apply may not drop changes or add conflicts."""
    add, overwrite, merge, delete = update_plan.classify_changes(
        {
            "added.txt": "A",
            "custom.txt": "M",
            "gone.txt": "D",
            "managed.txt": "M",
            "moved.txt": "A",
            "conflict.txt": "M",
        },
        conflicts={"conflict.txt"},
        excluded={"moved.txt"},
        customized={"custom.txt"},
    )
    assert (add, overwrite, merge, delete) == (
        ("added.txt",),
        ("managed.txt",),
        ("custom.txt",),
        ("gone.txt",),
    )
    old = update_plan.reconstruct_old_inputs({}, set(), {})
    planning = update_plan.UpdatePlanning(
        old_side=old,
        new_data={},
        add=add,
        overwrite=overwrite,
        merge=merge,
        delete=delete,
        conflicts=(),
        render_parity=update_plan.RENDER_PARITY_EQUAL,
    )
    same = update_plan.UpdatePlanning(
        old_side=old,
        new_data={},
        add=add,
        overwrite=overwrite,
        merge=merge,
        delete=delete,
        conflicts=(),
        render_parity=update_plan.RENDER_PARITY_EQUAL,
    )
    assert planning.digest() == same.digest()
    assert (
        update_plan.realized_divergence(
            planning, {*planning.changed_paths(), "task-output.html"}, ()
        )
        == []
    )
    problems = update_plan.realized_divergence(
        planning, {"added.txt"}, {"managed.txt"}
    )
    assert problems == [
        "unplanned conflicts: managed.txt",
        "planned changes not applied: custom.txt, gone.txt, managed.txt",
    ]


# --- Real legacy and current templates --------------------------------------

LEGACY_TAGS = ("v0.3.1", "v0.16.0")


@pytest.fixture(scope="module")
def template_source(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """Build a small template repository with real legacy and current trees.

    The legacy trees are the repository's own immutable release tags; the
    current trees are this checkout's ``copier.yml`` and ``template/``. A
    shallow local fetch keeps every Copier clone fast and offline.
    """
    for tag in LEGACY_TAGS:
        command = [
            "git",
            "rev-parse",
            "--verify",
            "--quiet",
            f"{tag}^{{commit}}",
        ]
        found = subprocess.run(  # noqa: S603
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if found.returncode != 0:
            pytest.skip(f"release tag {tag} is not available in this clone")
    root = tmp_path_factory.mktemp("parity")
    source = root / "template-source"
    init_repository(source)
    git(
        source,
        "fetch",
        "--quiet",
        "--depth",
        "1",
        ROOT.as_uri(),
        *(f"refs/tags/{tag}:refs/tags/{tag}" for tag in LEGACY_TAGS),
    )
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(
        ROOT / "template",
        source / "template",
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    current = commit_all(source, "test: current template")
    # Copier refuses downgrades, so the current trees carry versions above
    # every legacy tag.
    git(source, "tag", "v0.99.0", current)
    policy = source / "template/.csarc/docs/ci-policy.md.jinja"
    policy.write_text(
        policy.read_text(encoding="utf-8")
        + "\nParity fixture: one template change.\n",
        encoding="utf-8",
    )
    following = commit_all(source, "test: following template change")
    git(source, "tag", "v0.99.1", following)
    shas = {
        tag: git(source, "rev-parse", f"{tag}^{{commit}}")
        for tag in LEGACY_TAGS
    }
    return {
        "source": str(source),
        "current": current,
        "following": following,
        **shas,
    }


def render_legacy_fixture(source: str, tag: str, sha: str, path: Path) -> None:
    """Render one untouched legacy consumer the way Copier created it."""
    run(
        [
            sys.executable,
            "-m",
            "copier",
            "copy",
            "--trust",
            "--defaults",
            "--skip-tasks",
            "--vcs-ref",
            tag,
            "--data",
            "language=ci",
            "--data",
            f"code_owner={CODE_OWNER}",
            source,
            str(path),
        ],
        ROOT,
    )
    answers = next(
        candidate
        for candidate in (
            path / ".csarc/config.yml",
            path / ".copier-answers.yml",
        )
        if candidate.is_file()
    )
    lines = [
        f"_commit: {sha}" if line.startswith("_commit:") else line
        for line in answers.read_text(encoding="utf-8").splitlines()
    ]
    answers.write_text("\n".join(lines) + "\n", encoding="utf-8")
    init_repository(path)
    commit_all(path, f"test: untouched {tag} consumer")


def check_update(
    project: Path,
    target_sha: str,
    report_dir: Path,
    capsys: pytest.CaptureFixture[str],
    data: tuple[str, ...] = (),
) -> tuple[dict[str, object], dict[str, object]]:
    """Run one read-only update check and return its plan and report."""
    exit_code = main(
        [
            "update",
            str(project),
            "--check",
            "--json",
            "--to",
            target_sha,
            "--allow-unreleased",
            "--report-dir",
            str(report_dir),
            *(argument for item in data for argument in ("--data", item)),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1, captured.out + captured.err
    plan = json.loads(captured.out.strip().splitlines()[-1])
    report = json.loads(
        (report_dir / "csarc-update-report.json").read_text(encoding="utf-8")
    )
    return plan, report


def saved_answer_keys(project: Path) -> set[str]:
    """Return the fixture's persisted answer keys without Copier metadata."""
    for name in (".csarc/config.yml", ".copier-answers.yml"):
        path = project / name
        if path.is_file():
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            return {key for key in payload if not key.startswith("_")}
    raise AssertionError("fixture has no answers file")


def assert_parity(
    project: Path,
    target_sha: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    data: tuple[str, ...] = (),
    *,
    current_schema: bool = False,
) -> dict[str, object]:
    """AC4: equal render, zero false conflicts, and a deterministic check."""
    before = git(project, "status", "--porcelain")
    head = git(project, "rev-parse", "HEAD")
    first, first_report = check_update(
        project, target_sha, tmp_path / "first", capsys, data
    )
    second, second_report = check_update(
        project, target_sha, tmp_path / "second", capsys, data
    )
    planning = first["planning"]
    assert planning == second["planning"]
    assert first["files"] == second["files"]
    assert first_report["files"] == second_report["files"]
    assert planning["render_parity"] == "equal", planning
    assert planning["render_parity_paths"] == [], planning
    assert planning["conflicts"] == []
    assert first["files"]["manual_merge"] == []
    assert first["files"]["unknown"] == []
    assert first_report["verification"]["render_parity"] == {"state": "equal"}
    assert not [
        row for row in first_report["files"] if row["action"] == "conflict"
    ]
    old_side = planning["old_side"]
    assert old_side["defaulted"] == []
    if current_schema:
        # SPEC-009 (#1071): a schema 2 target replays its verified
        # provenance context plus the saved intent; nothing is dropped.
        saved = saved_answer_keys(project) - {"schema_version"}
        assert saved <= set(old_side["keys"])
        assert set(old_side["snapshot"]) == set(old_side["keys"])
        assert old_side["dropped"] == []
    else:
        assert old_side["snapshot"] == []
        # Every saved answer is either old-side input or explicitly dropped
        # as a question the old template never asked.
        assert set(old_side["keys"]) | set(old_side["dropped"]) == (
            saved_answer_keys(project)
        )
        assert not set(old_side["keys"]) & set(old_side["dropped"])
    # The check never writes to the target.
    assert git(project, "status", "--porcelain") == before
    assert git(project, "rev-parse", "HEAD") == head
    return planning


@pytest.mark.large
@pytest.mark.parametrize("tag", LEGACY_TAGS)
def test_legacy_consumer_update_has_render_parity(
    tag: str,
    template_source: dict[str, str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC1/AC4: v0.3.1 answers and v0.16.0 .csarc rebuild the old render."""
    project = tmp_path / f"consumer-{tag}"
    render_legacy_fixture(
        template_source["source"], tag, template_source[tag], project
    )
    # v0.3.1 rendered two release writers; until one writer is selected
    # (#1074) the update needs an explicit ownership choice to plan.
    # The legacy placeholder description no longer passes the current
    # validator; the new side receives a reviewed value instead.
    # A fixture without a GitHub origin names its repository explicitly.
    data: tuple[str, ...] = (
        "project_description=Parity fixture product",
        f"repository_url={REPOSITORY_URL}",
    )
    if tag == "v0.3.1":
        data += ("release_ownership=verification-only",)
    planning = assert_parity(
        project, template_source["current"], tmp_path, capsys, data
    )
    assert planning["old_side"]["dropped"] == []
    keys = set(planning["old_side"]["keys"])
    # Current-schema questions and defaults never reach the old side.
    for current_only in (
        "verification_mode",
        "documentation_mode",
        "primary_language",
        "admin_bypass",
    ):
        assert current_only not in keys


@pytest.mark.large
def test_current_schema_update_has_render_parity(
    template_source: dict[str, str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC4: a project created by the current schema updates without drift."""
    project = tmp_path / "current-consumer"
    assert (
        main(
            [
                "init",
                str(project),
                "--source",
                template_source["source"],
                "--to",
                template_source["current"],
                "--allow-unreleased",
                "--yes",
                "--non-interactive",
                "--data",
                "languages=[]",
                "--data",
                f"repository_url={REPOSITORY_URL}",
            ]
        )
        == 0
    )
    init_repository(project)
    commit_all(project, "test: current consumer")
    capsys.readouterr()
    planning = assert_parity(
        project,
        template_source["following"],
        tmp_path,
        capsys,
        current_schema=True,
    )
    # The verified render context reaches the old side (SPEC-009).
    keys = set(planning["old_side"]["keys"])
    assert {"project_mode", "project_name", "repository_url"} <= keys
    assert "release_ownership" in keys
