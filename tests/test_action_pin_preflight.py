"""Read-only product action pin preflight before update planning (#1065)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

import csarc_cli.cli as cli
from csarc_cli import action_pin_preflight as pins
from csarc_cli import lifecycle_report
from csarc_cli.cli import CliError, main

OLD = "1" * 40
NEW = "2" * 40
OTHER = "3" * 40
SETUP_OLD = "4" * 40
SETUP_NEW = "5" * 40

RELEASE_EXCLUDE = (
    "{% if project_mode == 'new' %}__keep_release__"
    "{% else %}.github/workflows/release.yml{% endif %}"
)
COPIER_YML = f"""\
_subdirectory: template
_exclude:
  - "copier.yml"
  - ".git"
  - "{RELEASE_EXCLUDE}"
project_mode:
  type: str
  default: new
"""


def git_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run Git the way the CLI's injected runner does."""
    return subprocess.run(  # noqa: S603
        command, capture_output=True, text=True, check=False
    )


def git(repository: Path, *arguments: str) -> str:
    """Run one successful fixture Git command."""
    command = ["git", "-C", str(repository), *arguments]
    return subprocess.run(  # noqa: S603
        command, capture_output=True, text=True, check=True
    ).stdout.strip()


def init_repository(path: Path) -> None:
    """Create one fixture repository with a local identity."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "--quiet", "-b", "main")
    git(path, "config", "user.name", "Pin Test")
    git(path, "config", "user.email", "pin-test@example.invalid")
    git(path, "config", "commit.gpgsign", "false")


def commit_all(repository: Path, message: str) -> str:
    """Commit every fixture change and return the full SHA."""
    git(repository, "add", "-A")
    git(repository, "commit", "--quiet", "--no-gpg-sign", "-m", message)
    return git(repository, "rev-parse", "HEAD")


def workflow(*uses: str) -> str:
    """Return a workflow-shaped file with one step per ``uses`` value."""
    steps = "".join(f"      - uses: {item} # v1\n" for item in uses)
    header = "on: push\njobs:\n  job:\n    runs-on: ubuntu-latest\n"
    return f"{header}    steps:\n{steps}"


def make_source(root: Path, checkout: str = NEW) -> tuple[Path, str]:
    """Create a template source whose workflows pin ``checkout``."""
    source = root / "source"
    workflows = source / "template/.github/workflows"
    workflows.mkdir(parents=True)
    (source / "copier.yml").write_text(COPIER_YML, encoding="utf-8")
    (workflows / "ci.yml").write_text(
        workflow(
            f"actions/checkout@{checkout}", f"astral-sh/setup-uv@{SETUP_NEW}"
        ),
        encoding="utf-8",
    )
    (workflows / "release.yml.jinja").write_text(
        workflow(f"actions/checkout@{checkout}"), encoding="utf-8"
    )
    init_repository(source)
    return source, commit_all(source, "template")


def make_target(root: Path, files: dict[str, str]) -> Path:
    """Create a committed consumer with the given workflow files."""
    target = root / "target"
    directory = target / ".github/workflows"
    directory.mkdir(parents=True)
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")
    init_repository(target)
    commit_all(target, "consumer")
    return target


def tree_digest(root: Path) -> str:
    """Hash every path, mode, and byte under ``root`` except ``.git``."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts:
            continue
        digest.update(str(path.relative_to(root)).encode())
        digest.update(str(path.lstat().st_mode).encode())
        if path.is_file() and not path.is_symlink():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def run(
    target: Path, source: Path, sha: str, mode: str = "new"
) -> pins.PinPreflight:
    """Run the preflight with the fixture Git runner."""
    return pins.run_preflight(
        target, str(source), sha, {"project_mode": mode}, git_runner
    )


def test_no_drift_reports_an_explicit_empty_set(tmp_path: Path) -> None:
    """AC2/AC5: equal pins produce ``clean`` and an empty item list."""
    source, sha = make_source(tmp_path)
    target = make_target(
        tmp_path,
        {
            "ci.yml": workflow(f"actions/checkout@{OLD}"),
            "product.yml": workflow(f"actions/checkout@{NEW}"),
            # A tag reference is outside the full-SHA pin contract.
            "tagged.yml": workflow("actions/checkout@v4"),
        },
    )
    before = tree_digest(target)

    result = run(target, source, sha)

    payload = result.as_dict()
    assert payload == {
        "items": [],
        "product_workflows": [
            ".github/workflows/product.yml",
            ".github/workflows/tagged.yml",
        ],
        "schema_version": 1,
        "source_sha": sha,
        "state": "clean",
    }
    # The payload is stable JSON for the machine plan.
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload
    assert tree_digest(target) == before


def test_single_drift_item_has_every_stable_field(tmp_path: Path) -> None:
    """AC2/AC5: one stale product pin is listed with file, line, and SHAs."""
    source, sha = make_source(tmp_path)
    target = make_target(
        tmp_path,
        {
            "ci.yml": workflow(f"actions/checkout@{OLD}"),
            "product.yml": workflow(
                "./local-action", f"actions/checkout@{OLD}"
            ),
        },
    )
    before = tree_digest(target)

    result = run(target, source, sha)

    assert result.state == "drift"
    assert result.as_dict()["items"] == [
        {
            "action": "actions/checkout",
            "file": ".github/workflows/product.yml",
            "line": 7,
            "new_sha": NEW,
            "old_sha": OLD,
            "reason": pins.REASON_TEMPLATE_PIN_CHANGED,
        }
    ]
    assert pins.repair_commands(result.items) == [
        f".github/workflows/product.yml:7: change actions/checkout@{OLD} "
        f"to actions/checkout@{NEW}"
    ]
    assert "the target was not changed" in pins.drift_error(result)
    assert tree_digest(target) == before


def test_multiple_drift_items_follow_template_ownership(tmp_path: Path) -> None:
    """AC5: excluded template workflows become product-owned for the answers."""
    source, sha = make_source(tmp_path)
    files = {
        "ci.yml": workflow(f"actions/checkout@{OLD}"),
        "release.yml": workflow(f"actions/checkout@{OLD}"),
        "product.yaml": workflow(
            f"actions/checkout@{OTHER}",
            f"astral-sh/setup-uv@{SETUP_OLD}",
            f"unrelated/action@{OTHER}",
        ),
    }
    target = make_target(tmp_path, files)

    managed = run(target, source, sha, mode="new")
    existing = run(target, source, sha, mode="existing")

    # release.yml is template-managed for new projects only.
    assert [item.file for item in managed.items] == [
        ".github/workflows/product.yaml",
        ".github/workflows/product.yaml",
    ]
    assert [
        (item.file, item.line, item.action, item.reason)
        for item in existing.items
    ] == [
        (
            ".github/workflows/product.yaml",
            6,
            "actions/checkout",
            pins.REASON_PRODUCT_PIN_DIVERGED,
        ),
        (
            ".github/workflows/product.yaml",
            7,
            "astral-sh/setup-uv",
            pins.REASON_PRODUCT_PIN_DIVERGED,
        ),
        (
            ".github/workflows/release.yml",
            6,
            "actions/checkout",
            pins.REASON_TEMPLATE_PIN_CHANGED,
        ),
    ]
    assert {item.new_sha for item in existing.items} == {NEW, SETUP_NEW}


@pytest.mark.parametrize("kind", ["binary", "symlink"])
def test_unparsable_product_workflow_fails_closed(
    tmp_path: Path, kind: str
) -> None:
    """AC3/AC5: a workflow that cannot be parsed stops the update."""
    source, sha = make_source(tmp_path)
    target = make_target(tmp_path, {"ci.yml": workflow()})
    broken = target / ".github/workflows/product.yml"
    if kind == "binary":
        broken.write_bytes(b"\xff\xfe uses: actions/checkout@" + OLD.encode())
    else:
        broken.symlink_to(tmp_path / "elsewhere.yml")
    before = tree_digest(target)

    with pytest.raises(pins.PinPreflightError, match=r"product\.yml"):
        run(target, source, sha)

    assert tree_digest(target) == before


def test_unreachable_source_fails_closed(tmp_path: Path) -> None:
    """AC3/AC5: an unreachable source is never treated as pin-free."""
    target = make_target(tmp_path, {"ci.yml": workflow()})
    before = tree_digest(target)
    missing = (tmp_path / "missing-source.git").as_uri()

    with pytest.raises(pins.PinPreflightError, match="unreachable"):
        pins.run_preflight(target, missing, NEW, {}, git_runner)

    assert tree_digest(target) == before


def test_untrusted_source_shapes_fail_closed(tmp_path: Path) -> None:
    """AC3/AC5: abbreviated, absent, and ambiguous pins are untrusted."""
    source, sha = make_source(tmp_path)
    target = make_target(tmp_path, {"ci.yml": workflow()})

    with pytest.raises(pins.PinPreflightError, match="full commit SHA"):
        run(target, source, sha[:12])
    with pytest.raises(pins.PinPreflightError, match="reviewed commit"):
        run(target, source, "f" * 40)

    (source / "template/.github/workflows/extra.yml").write_text(
        workflow(f"actions/checkout@{OTHER}"), encoding="utf-8"
    )
    ambiguous = commit_all(source, "ambiguous pins")
    with pytest.raises(pins.PinPreflightError, match="disagree"):
        run(target, source, ambiguous)

    (source / "template/.github/workflows/extra.yml").unlink()
    (source / "copier.yml").write_text(
        "_subdirectory: template\n_exclude:\n  - '{{ broken'\n",
        encoding="utf-8",
    )
    unparsable = commit_all(source, "broken exclusion")
    with pytest.raises(pins.PinPreflightError, match="_exclude"):
        run(target, source, unparsable)


def drift_fixture(tmp_path: Path) -> tuple[Path, list[dict[str, object]]]:
    """Return a consumer with two drift items and their preflight rows."""
    source, sha = make_source(tmp_path)
    target = make_target(
        tmp_path,
        {
            "ci.yml": workflow(f"actions/checkout@{OLD}"),
            "product.yml": workflow(
                f"actions/checkout@{OLD}", f"astral-sh/setup-uv@{SETUP_OLD}"
            ),
        },
    )
    items = [item.as_dict() for item in run(target, source, sha).items]
    assert len(items) == 2
    return target, items


def commit_pins(target: Path, items: list[dict[str, object]]) -> str:
    """Apply exactly the listed pin changes as one manual commit."""
    path = target / ".github/workflows/product.yml"
    text = path.read_text(encoding="utf-8")
    for item in items:
        text = text.replace(
            f"{item['action']}@{item['old_sha']}",
            f"{item['action']}@{item['new_sha']}",
        )
    path.write_text(text, encoding="utf-8")
    return commit_all(target, "fix: update product action pins")


def test_pin_decisions_must_be_complete_and_read_back(tmp_path: Path) -> None:
    """AC4: only disposed decisions readable from their commit are accepted."""
    target, items = drift_fixture(tmp_path)
    commit = commit_pins(target, items)
    decisions = [{**item, "commit_sha": commit} for item in items]

    accepted = pins.validate_pin_decisions(
        items, list(reversed(decisions)), git_runner, target
    )
    assert accepted == decisions
    # The pilot proves the manual commit changed nothing beyond the list.
    assert pins.unlisted_pin_changes(items, git_runner, target, commit) == []

    with pytest.raises(pins.PinPreflightError, match="missing"):
        pins.validate_pin_decisions(items, decisions[:1], git_runner, target)
    with pytest.raises(pins.PinPreflightError, match="duplicated"):
        pins.validate_pin_decisions(
            items, [*decisions, decisions[0]], git_runner, target
        )
    with pytest.raises(pins.PinPreflightError, match="not a preflight item"):
        pins.validate_pin_decisions(
            items,
            [{**decisions[0], "line": 99}, decisions[1]],
            git_runner,
            target,
        )
    with pytest.raises(pins.PinPreflightError, match="full lowercase"):
        pins.validate_pin_decisions(
            items,
            [{**decision, "commit_sha": commit[:7]} for decision in decisions],
            git_runner,
            target,
        )
    with pytest.raises(pins.PinPreflightError, match="read back"):
        pins.validate_pin_decisions(
            items,
            [{**decision, "commit_sha": "e" * 40} for decision in decisions],
            git_runner,
            target,
        )
    parent = git(target, "rev-parse", f"{commit}^")
    with pytest.raises(pins.PinPreflightError, match="does not pin"):
        pins.validate_pin_decisions(
            items,
            [{**decision, "commit_sha": parent} for decision in decisions],
            git_runner,
            target,
        )


def test_pin_decision_commit_must_be_in_target_history(tmp_path: Path) -> None:
    """AC4: a pin commit on an unmerged side branch is not accepted."""
    target, items = drift_fixture(tmp_path)
    git(target, "switch", "--quiet", "-c", "side")
    commit = commit_pins(target, items)
    git(target, "switch", "--quiet", "main")

    with pytest.raises(pins.PinPreflightError, match="history"):
        pins.validate_pin_decisions(
            items,
            [{**item, "commit_sha": commit} for item in items],
            git_runner,
            target,
        )


def test_pilot_detects_product_changes_outside_the_list(
    tmp_path: Path,
) -> None:
    """AC4: any other product edit in a pin commit is reported."""
    target, items = drift_fixture(tmp_path)
    path = target / ".github/workflows/product.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            f"actions/checkout@{OLD}", f"actions/checkout@{NEW}"
        )
        + "# unrelated product edit\n",
        encoding="utf-8",
    )
    (target / "src.txt").write_text("product\n", encoding="utf-8")
    commit = commit_all(target, "fix: pins plus extra changes")

    unlisted = pins.unlisted_pin_changes(items, git_runner, target, commit)

    assert ".github/workflows/product.yml: lines added or removed" in unlisted
    assert any(entry.startswith("src.txt: new file mode") for entry in unlisted)


def test_pilot_rejects_a_line_changed_beyond_the_sha(tmp_path: Path) -> None:
    """AC4: a listed line may only swap the old SHA for the new one.

    Its trailing release-tag comment may follow the SHA (#1083); any other
    change to the line is still outside the preflight list.
    """
    target, items = drift_fixture(tmp_path)
    path = target / ".github/workflows/product.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            f"- uses: actions/checkout@{OLD} # v1",
            f"- uses:  actions/checkout@{NEW} # v9",
        ),
        encoding="utf-8",
    )
    commit = commit_all(target, "fix: pin with a changed line")

    assert pins.unlisted_pin_changes(items, git_runner, target, commit) == [
        ".github/workflows/product.yml:6"
    ]


# --- CLI ordering and fail-closed behavior ---------------------------------


def stub_update(
    monkeypatch: pytest.MonkeyPatch, target: Path, source: str, sha: str
) -> list[str]:
    """Stub every live fact before the preflight; record render attempts."""
    (target / ".csarc").mkdir()
    (target / ".csarc/config.yml").write_text(
        f"_commit: {'c' * 40}\n_src_path: {source}\nproject_mode: new\n",
        encoding="utf-8",
    )
    commit_all(target, "answers")
    events: list[str] = []
    current = cli.Revision("v1.0.0", "c" * 40, source)
    reviewed = cli.Revision("development", sha, source)
    monkeypatch.setattr(
        cli,
        "repository_context",
        lambda *args, **kwargs: cli.RepositoryContext(
            "owner/product", "owner", "User", "private", "github", True
        ),
    )
    monkeypatch.setattr(
        cli,
        "update_plan_answers",
        lambda saved, explicit, repository: (dict(saved), {}),
    )
    monkeypatch.setattr(
        cli, "resolve_release_answers", lambda target, answers: answers
    )
    monkeypatch.setattr(
        cli,
        "update_status",
        lambda *args, **kwargs: (
            {
                "source": source,
                "target_sha": sha,
                "update_available": True,
            },
            current,
            reviewed,
            None,
        ),
    )
    original = pins.run_preflight

    def spy(
        target: Path,
        source: str,
        sha: str,
        answers: Mapping[str, object],
        git: pins.GitRunner,
    ) -> pins.PinPreflight:
        events.append("preflight")
        return original(target, source, sha, answers, git)

    def render(*args: object, **kwargs: object) -> None:
        del args, kwargs
        events.append("render")
        raise CliError("stop at the first render")

    monkeypatch.setattr(pins, "run_preflight", spy)
    monkeypatch.setattr(cli, "copier_copy", render)
    return events


def test_update_apply_with_drift_fails_before_any_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC1/AC3: drift stops apply before render, plan, or target write."""
    source, sha = make_source(tmp_path)
    target = make_target(
        tmp_path,
        {
            "ci.yml": workflow(f"actions/checkout@{OLD}"),
            "product.yml": workflow(f"actions/checkout@{OLD}"),
        },
    )
    events = stub_update(monkeypatch, target, str(source), sha)
    before = tree_digest(target)
    head = git(target, "rev-parse", "HEAD")

    exit_code = main(["update", str(target), "--yes", "--non-interactive"])

    error = capsys.readouterr().err
    assert exit_code == 2
    assert events == ["preflight"]
    assert "the target was not changed" in error
    assert (
        f".github/workflows/product.yml:6: change actions/checkout@{OLD} "
        f"to actions/checkout@{NEW}"
    ) in error
    assert tree_digest(target) == before
    assert git(target, "rev-parse", "HEAD") == head
    assert git(target, "status", "--porcelain") == ""


def test_update_check_runs_preflight_before_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC1: a check still plans with drift, but only after the preflight."""
    source, sha = make_source(tmp_path)
    target = make_target(
        tmp_path, {"product.yml": workflow(f"actions/checkout@{OLD}")}
    )
    events = stub_update(monkeypatch, target, str(source), sha)

    assert main(["update", str(target), "--check", "--json"]) == 2

    assert events == ["preflight", "render"]
    # --json reports errors as one JSON object on stdout.
    assert "stop at the first render" in capsys.readouterr().out


@pytest.mark.parametrize("check", [False, True])
def test_update_reinstall_fallback_runs_the_preflight_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    check: bool,
) -> None:
    """AC1/AC3: the reinstall fallback of csarc update is not a bypass."""
    source, sha = make_source(tmp_path)
    target = make_target(
        tmp_path,
        {
            "ci.yml": workflow(f"actions/checkout@{OLD}"),
            "product.yml": workflow(f"actions/checkout@{OLD}"),
        },
    )
    events = stub_update(monkeypatch, target, str(source), sha)

    def unusable_release(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise cli.ReleaseRecoveryError("Recorded release is unusable.")

    monkeypatch.setattr(cli, "update_status", unusable_release)
    monkeypatch.setattr(
        cli,
        "resolve_revision",
        lambda *args, **kwargs: cli.Revision("development", sha, str(source)),
    )
    before = tree_digest(target)
    head = git(target, "rev-parse", "HEAD")
    arguments = ["update", str(target), "--yes", "--non-interactive"]
    if check:
        arguments.append("--check")

    assert main(arguments) == 2

    error = capsys.readouterr().err
    assert "Attempting a reinstall" in error
    assert ".github/workflows/product.yml:6" in error
    # Apply stops before any render; a check reports drift, then renders.
    assert events == (["preflight", "render"] if check else ["preflight"])
    assert tree_digest(target) == before
    assert git(target, "rev-parse", "HEAD") == head
    assert git(target, "status", "--porcelain") == ""


def test_update_with_unreachable_source_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC3: an unreachable pin source stops even a read-only check."""
    target = make_target(tmp_path, {"ci.yml": workflow()})
    missing = (tmp_path / "missing-source.git").as_uri()
    events = stub_update(monkeypatch, target, missing, NEW)
    before = tree_digest(target)

    assert main(["update", str(target), "--check", "--json"]) == 2

    error = capsys.readouterr().out
    assert events == ["preflight"]
    assert "Action pin preflight failed closed" in error
    assert "Repair:" in error
    assert tree_digest(target) == before


# --- Machine plan and SPEC-008 report ---------------------------------------


def pin_report(
    tmp_path: Path, preflight: pins.PinPreflight
) -> dict[str, object]:
    """Build one validated update report carrying a preflight payload."""
    resolved = cli.resolve_release_answers(
        tmp_path, {"language": "ci", "project_mode": "existing"}
    )
    plan = cli.ResolvedPlan(
        mode="update",
        target=tmp_path / "product",
        revision=cli.Revision("v1.1.0", "d" * 40, "https://example.invalid"),
        repository=cli.RepositoryContext(
            "owner/product", "owner", "User", "private", "github", True
        ),
        answers=resolved,
        capabilities={},
        files=cli.Plan((), (), (), (), (), (), ()),
        update={
            "action_pin_preflight": preflight.as_dict(),
            "project_verification_hook": {
                "configured": False,
                "path": None,
                "reason": "Configuration validated.",
                "result": "not-run",
            },
            "update_available": True,
        },
    )
    return cli.lifecycle_report_model(
        plan,
        operation="update",
        plan_name=cli.UPDATE_PLAN_BASENAME,
        plan_sha256="a" * 64,
        generated_at="2026-10-14T00:00:00+00:00",
        before=resolved,
        previous=cli.Revision("v1.0.0", "b" * 40, "https://example.invalid"),
        target_head="c" * 40,
        target_changes=(),
        pin_versions=preflight.versions,
    )


def test_report_lists_pins_and_blocks_on_drift(tmp_path: Path) -> None:
    """AC2: the report carries the same rows plus blocking action-pin items."""
    item = pins.PinDrift(
        ".github/workflows/product.yml",
        6,
        "actions/checkout",
        OLD,
        NEW,
        pins.REASON_TEMPLATE_PIN_CHANGED,
    )
    drift = pins.PinPreflight(NEW, (item.file,), (item,))

    report = pin_report(tmp_path, drift)

    product = report["product"]
    assert isinstance(product, dict)
    assert product["action_pins"] == [item.as_dict()]
    assert report["status"] == "blocked"
    assert report["applicable"] is False
    actions = report["required_actions"]
    assert isinstance(actions, list)
    assert [
        (action["kind"], action["subject"], action["blocking"])
        for action in actions
    ] == [("action-pin", ".github/workflows/product.yml:6", True)]
    markdown = lifecycle_report.render_markdown(report)
    assert "### Action pins" in markdown
    assert OLD in markdown and NEW in markdown


def test_report_shows_an_evaluated_empty_pin_set(tmp_path: Path) -> None:
    """AC2: no drift is an explicit empty list, never ``null``."""
    report = pin_report(tmp_path, pins.PinPreflight(NEW, (), ()))

    product = report["product"]
    assert isinstance(product, dict)
    assert product["action_pins"] == []
    assert report["status"] == "ready"
    markdown = lifecycle_report.render_markdown(report)
    assert "### Action pins\n\nNone." in markdown


# --- Version tags on blocking rows (#1154 AC2) --------------------------------


def tagged_workflow(action: str, sha: str, tag: str | None) -> str:
    """Return a one-step workflow whose pin carries an optional tag comment."""
    comment = f" # {tag}" if tag is not None else ""
    header = "on: push\njobs:\n  job:\n    runs-on: ubuntu-latest\n"
    return f"{header}    steps:\n      - uses: {action}@{sha}{comment}\n"


@pytest.mark.parametrize(
    ("old_tag", "new_tag", "expected"),
    [
        (
            "v6.1.0",
            "v7.0.0",
            "product tag v6.1.0, template tag v7.0.0, major upgrade: yes",
        ),
        (
            "v7.0.0",
            "v7.2.1",
            "product tag v7.0.0, template tag v7.2.1, major upgrade: no",
        ),
        (
            None,
            "v7.0.0",
            "product tag unknown, template tag v7.0.0, major upgrade: unknown",
        ),
        (
            "main",
            None,
            "product tag main, template tag unknown, major upgrade: unknown",
        ),
    ],
)
def test_blocking_pin_row_names_tags_and_major_upgrade(
    tmp_path: Path, old_tag: str | None, new_tag: str | None, expected: str
) -> None:
    """AC2/R2: the blocking row shows both tags and the major judgement.

    Tags come from the ``# vX.Y.Z`` comments of the product line and the
    template pin; a missing or non-semver tag is ``unknown``, never a guess.
    The machine rows keep exactly the SPEC-008 fields.
    """
    product = ".github/workflows/product-ci.yml"
    action = "actions/setup-node"
    template = {
        ".github/workflows/ci.yml": tagged_workflow(action, NEW, new_tag)
    }
    drift = pins.evaluate(
        {product: tagged_workflow(action, OLD, old_tag)},
        set(),
        pins.template_pins(template),
        NEW,
        pins.template_tags(template, pins.template_pins(template)),
    )
    assert drift.versions == {(product, 6): (old_tag, new_tag)}

    report = pin_report(tmp_path, drift)
    product_rows = report["product"]
    assert isinstance(product_rows, dict)
    assert product_rows["action_pins"] == [drift.items[0].as_dict()]
    assert set(drift.as_dict()) == {
        "items",
        "product_workflows",
        "schema_version",
        "source_sha",
        "state",
    }
    actions = report["required_actions"]
    assert isinstance(actions, list)
    [row] = [action for action in actions if action["kind"] == "action-pin"]
    assert row["blocking"] is True
    assert expected in row["message"]
    assert expected in lifecycle_report.render_markdown(report)
