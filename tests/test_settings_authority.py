"""Saved settings are the only authority for every reader (Issue #1068).

One contract table drives the root and template configuration readers, the
shell adapters that consume them, the Copier render conditions, and the CLI
update resolver, so no reader can re-derive a saved value on its own.
"""

from __future__ import annotations

import os
import runpy
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import jinja2
import pytest
import yaml

from csarc_cli import cli
from csarc_cli.cli import CliError

ROOT = Path(__file__).resolve().parents[1]
READERS = {
    "root": ROOT / "scripts" / "csarc_config.py",
    "template": ROOT / "template" / ".csarc" / "scripts" / "csarc_config.py",
}
# Layout of each adapter copy: (scripts directory, policies directory).
LAYOUTS = {
    "root": (Path("scripts"), Path("policies")),
    "template": (Path(".csarc/scripts"), Path(".csarc/policies")),
}
SOURCE_ROOTS = {"root": ROOT, "template": ROOT / "template"}

# (project_mode, saved release_ownership, CSARC writes Releases)
VALID_OWNERSHIP = (
    ("new", "csarc-owned", True),
    ("new", "verification-only", False),
    ("existing", "csarc-owned", True),
    ("existing", "product-owned", False),
    ("existing", "verification-only", False),
)
MISSING_PREFIX = "CSARC settings error: release_ownership is missing"


def load_reader(layout: str) -> dict[str, object]:
    """Load one copy of the shared configuration reader."""
    return runpy.run_path(str(READERS[layout]))


def resolver(
    reader: Mapping[str, object],
) -> Callable[[dict[str, object]], str]:
    """Return one loaded reader's release-ownership resolver."""
    return cast(
        "Callable[[dict[str, object]], str]",
        reader["resolve_release_ownership"],
    )


def test_root_and_template_share_one_reader() -> None:
    """The template ships the exact reader the root uses."""
    assert READERS["root"].read_bytes() == READERS["template"].read_bytes()


@pytest.mark.parametrize("layout", sorted(READERS))
@pytest.mark.parametrize(("mode", "ownership", "writes"), VALID_OWNERSHIP)
def test_saved_ownership_is_returned_unchanged(
    layout: str, mode: str, ownership: str, *, writes: bool
) -> None:
    """A saved owner wins over project_mode; only csarc-owned writes."""
    reader = load_reader(layout)
    config: dict[str, object] = {
        "project_mode": mode,
        "release_ownership": ownership,
    }
    renders = cast(
        "Callable[[dict[str, object]], bool]",
        reader["renders_release_workflow"],
    )
    assert resolver(reader)(config) == ownership
    assert renders(config) is writes


@pytest.mark.parametrize("layout", sorted(READERS))
@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"project_mode": "new"}, MISSING_PREFIX),
        ({"project_mode": "existing"}, MISSING_PREFIX),
        ({}, MISSING_PREFIX),
        (
            {"project_mode": "existing", "release_ownership": "someone"},
            "release_ownership in .csarc/config.yml is 'someone'",
        ),
        (
            {"project_mode": "new", "release_ownership": "product-owned"},
            "product-owned contradicts project_mode new",
        ),
    ],
)
def test_missing_unknown_or_contradictory_owner_fails_closed(
    layout: str, config: dict[str, object], message: str
) -> None:
    """Never fall back to a project_mode or Copier default (#485)."""
    reader = load_reader(layout)
    error_type = cast("type[Exception]", reader["SettingsError"])
    with pytest.raises(error_type, match=r"^CSARC settings error") as caught:
        resolver(reader)(config)
    assert message in str(caught.value)
    assert isinstance(caught.value, ValueError)


@pytest.mark.parametrize("layout", sorted(READERS))
@pytest.mark.parametrize(
    ("config", "returncode", "stdout", "stderr"),
    [
        ("project_mode: new\n", 1, "", MISSING_PREFIX),
        (
            "project_mode: existing\nrelease_ownership: unknown\n",
            1,
            "",
            "Invalid release_ownership in .csarc/config.yml: 'unknown'",
        ),
        (
            "project_mode: existing\nrelease_ownership: product-owned\n",
            0,
            "product-owned\n",
            "",
        ),
    ],
)
def test_reader_command_prints_one_stable_answer(
    tmp_path: Path,
    layout: str,
    config: str,
    returncode: int,
    stdout: str,
    stderr: str,
) -> None:
    """Shell and workflow callers get the value or a stable error only."""
    (tmp_path / ".csarc").mkdir()
    (tmp_path / ".csarc/config.yml").write_text(config, encoding="utf-8")
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(READERS[layout]), "release_ownership"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == returncode
    assert result.stdout == stdout
    assert stderr in result.stderr


def adapter_repository(tmp_path: Path, layout: str, config: str | None) -> Path:
    """Assemble one adapter copy with its own reader and policies."""
    repository = tmp_path / layout
    scripts, policies = LAYOUTS[layout]
    source = SOURCE_ROOTS[layout]
    (repository / scripts).mkdir(parents=True)
    for name in (
        "apply-repository-settings.sh",
        "validate-pr-policy",
        "csarc_config.py",
    ):
        target = repository / scripts / name
        shutil.copy2(source / scripts / name, target)
        target.chmod(target.stat().st_mode | stat.S_IEXEC)
    # Rendered policy payloads are identical in both layouts.
    shutil.copytree(ROOT / "policies", repository / policies)
    (repository / ".csarc").mkdir(exist_ok=True)
    if config is not None:
        (repository / ".csarc/config.yml").write_text(config, encoding="utf-8")
    return repository


def logging_gh(tmp_path: Path) -> tuple[Path, Path]:
    """Return a fake gh directory and the log of every gh invocation."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh.log"
    gh = bin_dir / "gh"
    gh.write_text(
        f'#!/usr/bin/env bash\necho "$*" >> "{log}"\nexit 1\n',
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    return bin_dir, log


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
@pytest.mark.parametrize(
    ("config", "message"),
    [
        ("governance_mode: managed\n", MISSING_PREFIX),
        (
            "governance_mode: managed\nrelease_ownership: someone\n",
            "Invalid release_ownership",
        ),
        (
            "governance_mode: shared\nrelease_ownership: csarc-owned\n",
            "Invalid governance_mode",
        ),
        (None, "CSARC settings error: .csarc/config.yml is missing"),
    ],
)
def test_settings_script_stops_before_any_github_call(
    tmp_path: Path, layout: str, config: str | None, message: str
) -> None:
    """No default replaces an unreadable setting before a settings write."""
    repository = adapter_repository(tmp_path, layout, config)
    bin_dir, log = logging_gh(tmp_path)
    scripts, _policies = LAYOUTS[layout]
    result = subprocess.run(  # noqa: S603
        [str(repository / scripts / "apply-repository-settings.sh"), "apply"],
        cwd=repository,
        env={
            **os.environ,
            "GH_REPO": "acme/product",
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert message in result.stderr
    assert not log.exists()


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
@pytest.mark.parametrize("mode", ["new", "existing"])
def test_pr_policy_does_not_derive_owner_from_project_mode(
    tmp_path: Path, layout: str, mode: str
) -> None:
    """The PR gate fails closed instead of re-deriving a release owner."""
    repository = adapter_repository(tmp_path, layout, f"project_mode: {mode}\n")
    scripts, _policies = LAYOUTS[layout]
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PR_", "GITHUB_"))
    }
    result = subprocess.run(  # noqa: S603
        [str(repository / scripts / "validate-pr-policy")],
        cwd=repository,
        env={
            **environment,
            "PR_DRAFT": "true",
            "PR_LABELS": "bug",
            "PR_NUMBER": "7",
            "PR_POLICY_FIXTURE": "true",
            "PR_TITLE": "fix(settings): keep saved owner",
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert MISSING_PREFIX in result.stderr
    assert "CSARC release follow-up policy" not in result.stdout


def copier_exclusions() -> dict[str, str]:
    """Return the Copier exclusion expression for each release path."""
    copier = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    paths = {
        ".github/workflows/release.yml",
        ".github/workflows/release-drift.yml",
        ".csarc/scripts/check-release-drift",
    }
    result: dict[str, str] = {}
    for expression in copier["_exclude"]:
        for path in paths:
            if expression.endswith(f"{{% else %}}{path}{{% endif %}}"):
                result[path] = expression
    assert set(result) == paths
    return result


@pytest.mark.parametrize("verification", ["hosted", "local"])
@pytest.mark.parametrize(("mode", "ownership", "writes"), VALID_OWNERSHIP)
def test_only_csarc_owned_renders_the_release_writer(
    mode: str, ownership: str, verification: str, *, writes: bool
) -> None:
    """Render the CSARC Release workflow for exactly one owner."""
    environment = jinja2.Environment(autoescape=False)  # noqa: S701
    context = {
        "project_mode": mode,
        "release_ownership": ownership,
        "verification_mode": verification,
    }
    for path, expression in copier_exclusions().items():
        excluded = environment.from_string(expression).render(context) == path
        rendered = writes and mode == "new" and verification == "hosted"
        assert excluded is not rendered, (path, context)


@pytest.mark.parametrize(
    ("mode", "ownership"),
    [
        ("new", "csarc-owned"),
        ("new", "verification-only"),
        ("existing", "verification-only"),
    ],
)
def test_cli_update_resolver_agrees_with_runtime_reader(
    tmp_path: Path, mode: str, ownership: str
) -> None:
    """The CLI keeps the saved owner the runtime reader returns."""
    saved: dict[str, object] = {
        "project_mode": mode,
        "release_ownership": ownership,
    }
    resolved = cli.resolve_release_answers(tmp_path, saved)
    reader = load_reader("root")
    assert resolved["release_ownership"] == resolver(reader)(dict(saved))
    assert cli.release_ownership(resolved) == ownership


def test_cli_and_runtime_reject_the_same_contradiction(tmp_path: Path) -> None:
    """A product-owned new project stops in both the CLI and runtime."""
    saved: dict[str, object] = {
        "project_mode": "new",
        "release_ownership": "product-owned",
    }
    with pytest.raises(CliError, match="requires an existing repository"):
        cli.resolve_release_answers(tmp_path, saved)
    with pytest.raises(ValueError, match="contradicts project_mode new"):
        resolver(load_reader("root"))(dict(saved))


GITHUB_PUBLIC_RENAMED = cli.RepositoryContext(
    "new-owner/renamed",
    "new-owner",
    "organization",
    "public",
    "github",
    True,
)
SAVED_PRIVATE: Mapping[str, object] = {
    "enable_codeql": False,
    "languages": ["python"],
    "project_mode": "existing",
    "project_visibility": "private",
    "release_ownership": "verification-only",
    "repository_url": "https://github.com/old-owner/product",
    "security_reporting_channel": (
        "Open a GitHub Issue at https://github.com/old-owner/product/"
        "issues/new; maintainers receive notifications for new Issues."
    ),
}


def test_update_keeps_saved_visibility_and_origin_settings() -> None:
    """Live visibility and origin never rewrite saved settings."""
    result, update_data = cli.update_plan_answers(
        dict(SAVED_PRIVATE), {}, GITHUB_PUBLIC_RENAMED
    )
    for key in (
        "enable_codeql",
        "project_visibility",
        "repository_url",
        "security_reporting_channel",
    ):
        assert result[key] == SAVED_PRIVATE[key]
        assert key not in update_data
    assert cli.observed_setting_differences(
        SAVED_PRIVATE, {}, GITHUB_PUBLIC_RENAMED
    ) == {
        # CodeQL is listed for confirmation, never flipped (#1058 d15).
        "enable_codeql": True,
        "project_visibility": "public",
        "repository_url": "https://github.com/new-owner/renamed",
    }


def test_explicit_data_is_the_only_writer_for_live_differences() -> None:
    """An explicit choice changes the saved value and clears the report."""
    explicit = {
        "project_visibility": "public",
        "repository_url": "https://github.com/new-owner/renamed",
        "security_reporting_channel": "security@example.com",
    }
    result, update_data = cli.update_plan_answers(
        dict(SAVED_PRIVATE), explicit, GITHUB_PUBLIC_RENAMED
    )
    for key, value in explicit.items():
        assert result[key] == value
        assert update_data[key] == value
    # The visibility choice does not flip CodeQL on its own (#1058 d15).
    assert result["enable_codeql"] is False
    assert "enable_codeql" not in update_data
    assert (
        cli.observed_setting_differences(
            SAVED_PRIVATE, explicit, GITHUB_PUBLIC_RENAMED
        )
        == {}
    )


@pytest.mark.parametrize(
    "repository",
    [
        cli.RepositoryContext(
            None, None, None, "public", "explicit", False, "No origin."
        ),
        cli.RepositoryContext(
            "new-owner/renamed",
            "new-owner",
            None,
            "public",
            "explicit",
            False,
            "GitHub API request failed",
        ),
    ],
)
def test_unverified_observation_reports_no_difference(
    repository: cli.RepositoryContext,
) -> None:
    """Only a verified GitHub observation can be reported as a difference."""
    assert cli.observed_setting_differences(SAVED_PRIVATE, {}, repository) == {}


def test_live_difference_is_a_reported_decision_not_a_write() -> None:
    """The report notes the live fact and asks for an explicit choice."""
    after = dict(SAVED_PRIVATE)
    observed = cli.observed_setting_differences(
        SAVED_PRIVATE, {}, GITHUB_PUBLIC_RENAMED
    )
    rows = cli.report_setting_rows(after, SAVED_PRIVATE, (), observed)
    by_key = {row["key"]: row for row in rows}
    visibility = by_key["project_visibility"]
    assert visibility["class"] == "unchanged"
    assert visibility["after"] == "private"
    assert "Live GitHub facts suggest `public`" in str(visibility["note"])
    actions = cli.update_required_actions(
        cli.Plan((), (), (), (), (), (), ()), rows, observed=observed
    )
    assert [
        (action["kind"], action["subject"], action["blocking"])
        for action in actions
    ] == [
        ("setting-decision", "enable_codeql", False),
        ("setting-decision", "project_visibility", False),
        ("setting-decision", "repository_url", False),
    ]


def test_status_inspection_carries_the_saved_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Status inspects settings with the saved owner, never a default."""
    seen: list[str] = []

    def fake_copy(
        source: str,
        revision: object,
        stage: Path,
        answers: Mapping[str, object],
        **kwargs: object,
    ) -> None:
        del source, revision, answers, kwargs
        (stage / ".csarc/scripts").mkdir(parents=True)
        shutil.copy2(READERS["template"], stage / ".csarc/scripts")
        (stage / ".csarc/scripts/apply-repository-settings.sh").write_text(
            "#!/usr/bin/env bash\n", encoding="utf-8"
        )
        (stage / ".csarc/config.yml").write_text(
            "project_mode: existing\n", encoding="utf-8"
        )

    def fake_check(
        script: Path, target: Path
    ) -> subprocess.CompletedProcess[str]:
        del target
        seen.append(
            (script.parents[2] / ".csarc/config.yml").read_text(
                encoding="utf-8"
            )
        )
        return subprocess.CompletedProcess(["check"], 0, "", "")

    monkeypatch.setattr(cli, "copier_copy", fake_copy)
    monkeypatch.setattr(cli, "run_policy_settings_check", fake_check)
    revision = cli.Revision(
        label="v1.0.0",
        sha="a" * 40,
        source="source",
        repository=cli.CANONICAL_REPOSITORY,
        repository_id=cli.CANONICAL_REPOSITORY_ID,
        release_id=1,
        immutable=True,
        attestation_verified=True,
        signature_verified=True,
    )
    assert revision.verified
    saved = {"project_mode": "existing", "release_ownership": "product-owned"}
    result = cli.trusted_policy_settings_check(tmp_path, revision, saved)
    assert result.returncode == 0
    assert "release_ownership: product-owned" in seen[-1]

    cli.trusted_policy_settings_check(
        tmp_path, revision, {"project_mode": "existing"}
    )
    assert "release_ownership" not in seen[-1]
