"""Detect repository facts without changing saved intent (Issue #1072).

One detector contract serves the pinned CLI and every generated runtime.
Live facts report ``known`` or ``unknown`` and are never saved; derived
context resolves only from one native-manifest candidate; saved intent
stays unchanged when the facts move; and a repository URL that contradicts
the recorded identity fails closed before any write.
"""

from __future__ import annotations

import json
import runpy
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from csarc_cli import cli, repository_facts, settings_schema
from csarc_cli.cli import CliError

ROOT = Path(__file__).resolve().parents[1]
COPIES = (
    ROOT / "scripts/repository_facts.py",
    ROOT / "template/.csarc/scripts/repository_facts.py",
    ROOT / "src/csarc_cli/repository_facts.py",
)
OWNER_REPOSITORY = {
    "default_branch": "main",
    "full_name": "owner/product",
    "id": 42,
    "owner": {"login": "owner", "type": "Organization"},
    "role_name": "admin",
    "security_and_analysis": {
        "advanced_security": {"status": "disabled"},
        "secret_scanning": {"status": "enabled"},
    },
    "visibility": "private",
}


@pytest.fixture(autouse=True)
def no_explicit_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ambient GH_REPO must not identify the fixtures."""
    monkeypatch.delenv("GH_REPO", raising=False)


def git(root: Path, *arguments: str) -> None:
    subprocess.run(  # noqa: S603
        ["git", "-C", str(root), *arguments],  # noqa: S607
        check=True,
        capture_output=True,
    )


def repository(root: Path, remotes: Mapping[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    for name, url in remotes.items():
        git(root, "remote", "add", name, url)
    return root


def api(
    responses: Mapping[str, object], calls: list[str] | None = None
) -> repository_facts.Runner:
    """Serve GitHub reads from fixtures; a missing endpoint is a 404."""

    def read(arguments: Sequence[str]) -> tuple[int, str, str]:
        endpoint = arguments[0]
        if calls is not None:
            calls.append(endpoint)
        if endpoint not in responses:
            return 1, "", "gh: Not Found (HTTP 404)"
        return 0, json.dumps(responses[endpoint]), ""

    return read


def offline(arguments: Sequence[str]) -> tuple[int, str, str]:
    del arguments
    return 1, "", "error connecting to api.github.com"


def states(payload: Mapping[str, object]) -> dict[str, str]:
    facts = payload["facts"]
    assert isinstance(facts, dict)
    return {name: fact["state"] for name, fact in facts.items()}


def test_cli_root_and_generated_copies_share_one_contract() -> None:
    """AC1: the CLI and every runtime run byte-identical detector code."""
    contents = {path.read_bytes() for path in COPIES}
    assert len(contents) == 1
    paired = (ROOT / "scripts/sync-paired-files.sh").read_text(encoding="utf-8")
    assert (
        '"scripts/repository_facts.py|'
        'template/.csarc/scripts/repository_facts.py"'
    ) in paired


def test_detector_reports_every_live_fact_as_known(tmp_path: Path) -> None:
    """AC1: identity, origin, visibility, branch, plan, role, security."""
    root = repository(
        tmp_path / "product",
        {"origin": "git@github.com:owner/product.git"},
    )
    payload = repository_facts.detect(
        root,
        api=api(
            {
                "repos/owner/product": OWNER_REPOSITORY,
                "orgs/owner": {"login": "owner", "plan": {"name": "team"}},
            }
        ),
        env={},
    )
    assert payload["contract"] == repository_facts.CONTRACT
    assert states(payload) == dict.fromkeys(
        repository_facts.LIVE_FACTS, repository_facts.KNOWN
    )
    facts = payload["facts"]
    assert isinstance(facts, dict)
    assert facts["origin"]["value"] == "https://github.com/owner/product"
    assert facts["identity"]["value"] == {
        "id": 42,
        "owner": "owner",
        "owner_type": "organization",
        "repository": "owner/product",
    }
    assert facts["visibility"]["value"] == "private"
    assert facts["default_branch"]["value"] == "main"
    assert facts["plan"]["value"] == "team"
    assert facts["permissions"]["value"] == "admin"
    assert facts["security"]["value"] == {
        "advanced_security": "disabled",
        "secret_scanning": "enabled",
    }


def test_offline_detection_reports_unknown_not_a_guess(tmp_path: Path) -> None:
    """AC2/AC6: unobservable facts are unknown with a reason, no value."""
    root = repository(
        tmp_path / "product", {"origin": "https://github.com/owner/product"}
    )
    for payload in (
        repository_facts.detect(root, env={}, offline=True),
        repository_facts.detect(root, api=offline, env={}),
    ):
        facts = payload["facts"]
        assert isinstance(facts, dict)
        assert facts["origin"]["state"] == repository_facts.KNOWN
        for name in repository_facts.REMOTE_FACTS:
            assert facts[name]["state"] == repository_facts.UNKNOWN
            assert facts[name]["value"] is None
            assert facts[name]["reason"]


def test_insufficient_permission_leaves_gated_facts_unknown(
    tmp_path: Path,
) -> None:
    """AC6: a read-only caller observes identity but not gated facts."""
    root = repository(
        tmp_path / "product", {"origin": "https://github.com/owner/product"}
    )
    limited = {
        key: value
        for key, value in OWNER_REPOSITORY.items()
        if key not in {"role_name", "security_and_analysis"}
    }
    payload = repository_facts.detect(
        root,
        api=api({"repos/owner/product": limited, "orgs/owner": {"login": "x"}}),
        env={},
    )
    assert states(payload) == {
        "default_branch": "known",
        "identity": "known",
        "origin": "known",
        "permissions": "unknown",
        "plan": "unknown",
        "security": "unknown",
        "visibility": "known",
    }


def test_multiple_remotes_are_never_guessed(tmp_path: Path) -> None:
    """AC6: origin wins; without origin, other remotes stay unresolved."""
    with_origin = repository(
        tmp_path / "with-origin",
        {
            "origin": "https://github.com/owner/product.git",
            "upstream": "https://github.com/upstream/product.git",
        },
    )
    origin = repository_facts.observe_origin(
        with_origin, repository_facts.git_runner(with_origin), {}
    )
    assert origin["state"] == repository_facts.KNOWN
    assert origin["value"] == "https://github.com/owner/product"

    several = repository(
        tmp_path / "several",
        {
            "fork": "https://github.com/fork/product.git",
            "upstream": "https://github.com/upstream/product.git",
        },
    )
    ambiguous = repository_facts.observe_origin(
        several, repository_facts.git_runner(several), {}
    )
    assert ambiguous["state"] == repository_facts.AMBIGUOUS
    assert ambiguous["candidates"] == [
        "https://github.com/fork/product",
        "https://github.com/upstream/product",
    ]
    assert cli.target_repository(several) is None

    single = repository(
        tmp_path / "single", {"upstream": "https://github.com/up/product"}
    )
    lone = repository_facts.observe_origin(
        single, repository_facts.git_runner(single), {}
    )
    assert lone["state"] == repository_facts.UNKNOWN
    assert lone["value"] is None


def test_cli_and_runtime_read_the_same_origin(tmp_path: Path) -> None:
    """AC1: the generated reader and the CLI resolve one origin rule."""
    reader = runpy.run_path(
        str(ROOT / "template/.csarc/scripts/csarc_config.py")
    )
    root = repository(
        tmp_path / "product", {"origin": "git@github.com:owner/product.git"}
    )
    assert reader["project_facts"](root)["repository_url"] == (
        "https://github.com/owner/product"
    )
    assert cli.target_repository(root) == "owner/product"
    several = repository(
        tmp_path / "several",
        {
            "fork": "https://github.com/fork/product.git",
            "upstream": "https://github.com/upstream/product.git",
        },
    )
    # An ambiguous origin is empty at runtime, never the first remote.
    assert reader["project_facts"](several)["repository_url"] == ""
    assert cli.target_repository(several) is None


def test_cli_context_carries_the_detector_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1/AC2: the CLI context holds the shared facts; failures are unknown."""
    root = repository(
        tmp_path / "product", {"origin": "https://github.com/owner/product"}
    )
    responses = {
        "repos/owner/product": OWNER_REPOSITORY,
        "orgs/owner": {"login": "owner", "plan": {"name": "team"}},
    }
    monkeypatch.setattr(cli, "detector_api", api(responses), raising=True)
    context = cli.repository_context(root, None)
    expected = repository_facts.detect(root, api=api(responses), env={})
    assert context.verified
    assert dict(context.facts) == expected["facts"]

    monkeypatch.setattr(cli, "detector_api", offline)
    fallback = cli.repository_context(root, "private")
    assert not fallback.verified
    # The explicit visibility renders, but the live fact stays unknown.
    assert fallback.visibility == "private"
    assert fallback.facts["visibility"]["state"] == repository_facts.UNKNOWN


def write_package(root: Path, name: str) -> None:
    package = root / "src" / name
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")


def write_pyproject(root: Path, name: str | None) -> None:
    body = f'[project]\nname = "{name}"\n' if name else "[tool.x]\n"
    (root / "pyproject.toml").write_text(body, encoding="utf-8")


def test_package_name_resolves_only_from_one_candidate(tmp_path: Path) -> None:
    """AC3/AC6: several manifests or packages need one decision."""
    single = tmp_path / "single"
    single.mkdir()
    write_pyproject(single, "Product-Kit")
    assert repository_facts.derive_package_name(single) == (
        repository_facts.known("product_kit", "pyproject.toml")
    )
    write_package(single, "product_core")
    # The src layout names the import package, not the distribution.
    assert repository_facts.derive_package_name(single)["value"] == (
        "product_core"
    )

    several = tmp_path / "several"
    write_package(several, "alpha")
    write_package(several, "beta")
    write_pyproject(several, "other")
    ambiguous = repository_facts.derive_package_name(several)
    assert ambiguous["state"] == repository_facts.AMBIGUOUS
    assert ambiguous["candidates"] == ["alpha", "beta"]
    write_pyproject(several, "beta")
    assert repository_facts.derive_package_name(several)["value"] == "beta"

    empty = tmp_path / "empty"
    empty.mkdir()
    assert repository_facts.derive_package_name(empty)["state"] == (
        repository_facts.UNKNOWN
    )


def test_run_command_composes_native_manifests(tmp_path: Path) -> None:
    """AC3: one command per selected language, only with its manifest."""
    root = tmp_path / "product"
    write_package(root, "product")
    write_pyproject(root, "product")
    (root / "package.json").write_text("{}", encoding="utf-8")
    package = repository_facts.derive_package_name(root)
    command = repository_facts.derive_run_command(
        root, ["python", "typescript"], package
    )
    assert command["value"] == (
        "uv run python -c 'import product' && pnpm run build"
    )
    missing = repository_facts.derive_run_command(root, ["go"], package)
    assert missing["state"] == repository_facts.UNKNOWN
    assert "go.mod" in str(missing["reason"])
    assert repository_facts.derive_run_command(root, [], package)["value"] == (
        repository_facts.NO_LANGUAGE_COMMAND
    )
    write_package(root, "other")
    write_pyproject(root, "suite")
    ambiguous = repository_facts.derive_context(root, ["python"])
    assert ambiguous["package_name"]["state"] == repository_facts.AMBIGUOUS
    assert ambiguous["project_run_command"]["candidates"] == [
        "uv run python -c 'import other'",
        "uv run python -c 'import product'",
    ]
    decided = repository_facts.derive_context(
        root, ["python"], {"package_name": "product"}
    )
    assert decided["project_run_command"]["value"] == (
        "uv run python -c 'import product'"
    )


def test_update_derives_context_without_overriding_a_record(
    tmp_path: Path,
) -> None:
    """AC3: unique values fill gaps; contradictions ask for one decision."""
    root = tmp_path / "product"
    write_package(root, "product")
    write_pyproject(root, "product")
    answers: dict[str, object] = {"languages": ["python"]}
    values, differences = cli.resolve_derived_context(root, answers, {})
    assert values == {
        "package_name": "product",
        "project_run_command": "uv run python -c 'import product'",
    }
    assert differences == {}

    # A previous render records both derived values in provenance.
    recorded = {
        **answers,
        "package_name": "legacy",
        "project_run_command": "uv run python -c 'import legacy'",
    }
    values, differences = cli.resolve_derived_context(root, recorded, {})
    # The recorded value is kept and reported, never flipped.
    assert "package_name" not in values
    assert differences["package_name"] == "product"
    values, differences = cli.resolve_derived_context(
        root, recorded, {"package_name": "legacy"}
    )
    assert "package_name" not in differences

    write_package(root, "other")
    write_pyproject(root, "suite")
    with pytest.raises(CliError, match="--data package_name=<value> once"):
        cli.resolve_derived_context(root, answers, {})
    _values, differences = cli.resolve_derived_context(root, recorded, {})
    assert differences["package_name"] == ["other", "product"]
    rows = cli.report_setting_rows(recorded, recorded, (), differences)
    package_row = next(row for row in rows if row["key"] == "package_name")
    assert package_row["class"] == "unchanged"
    assert "Pass `--data package_name=<value>` once" in str(package_row["note"])
    actions = cli.update_required_actions(
        cli.Plan((), (), (), (), (), (), ()), rows, observed=differences
    )
    assert ("setting-decision", "package_name") in {
        (action["kind"], action["subject"]) for action in actions
    }


def test_adoption_saves_only_decisions_the_manifests_cannot_make(
    tmp_path: Path,
) -> None:
    """AC3: adopt saves a decision only for several or contradicted values."""
    root = tmp_path / "product"
    write_package(root, "product")
    write_pyproject(root, "product")
    derived = {
        "languages": ["python"],
        "package_name": "product",
        "project_run_command": "uv run python -c 'import product'",
    }
    assert cli.adoption_decisions(root, derived) == {}
    assert cli.adoption_derived_context(
        root, {"languages": ["python"], "package_name": "slug_default"}, {}
    ) == {
        "package_name": "product",
        "project_run_command": "uv run python -c 'import product'",
    }
    write_package(root, "other")
    write_pyproject(root, "suite")
    with pytest.raises(CliError, match="several candidates"):
        cli.adoption_derived_context(
            root, {"languages": ["python"], "package_name": "slug"}, {}
        )
    chosen = {
        "languages": ["python"],
        "package_name": "other",
        "project_run_command": "uv run python -c 'import other'",
    }
    assert cli.adoption_derived_context(
        root, chosen, {"package_name": "other"}
    ) == {"project_run_command": "uv run python -c 'import other'"}
    assert cli.adoption_decisions(root, chosen) == {"package_name": "other"}


SAVED: Mapping[str, object] = {
    "coverage_mode": "diff",
    "coverage_threshold": 80,
    "enable_codeql": True,
    "languages": ["python"],
    "lifecycle": ["issues"],
    "project_mode": "existing",
    "project_visibility": "public",
    "python_floor": "3.13",
    "release_ownership": "verification-only",
    "repository_url": "https://github.com/owner/product",
    "scheduled_checks": ["governance-drift"],
}
INTENT_KEYS = (
    "coverage_mode",
    "coverage_threshold",
    "enable_codeql",
    "lifecycle",
    "python_floor",
    "scheduled_checks",
)


def private_context(security: str) -> cli.RepositoryContext:
    return cli.RepositoryContext(
        "owner/product",
        "owner",
        "organization",
        "private",
        "github",
        True,
        facts={
            "security": repository_facts.known(
                {"advanced_security": security}, "github"
            )
        },
    )


def test_visibility_and_entitlement_changes_keep_saved_intent(
    tmp_path: Path,
) -> None:
    """AC4/AC6: saved intent stays unchanged; differences are only notes."""
    # An existing Python support intent is never re-derived from the
    # manifest's requires-python (SPEC-009).
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "product"\nrequires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    context = private_context("disabled")
    result, update_data = cli.update_plan_answers(dict(SAVED), {}, context)
    observed = cli.observed_setting_differences(SAVED, {}, context)
    derived, differences = cli.resolve_derived_context(tmp_path, result, {})
    observed.update(differences)
    for key in INTENT_KEYS:
        assert result[key] == SAVED[key]
        assert key not in update_data
        assert key not in derived
    # The CodeQL suggestion follows the visibility change, as a note only.
    assert observed["enable_codeql"] is False
    rows = cli.report_setting_rows(result, SAVED, (), observed)
    by_key = {row["key"]: row for row in rows}
    for key in INTENT_KEYS:
        assert by_key[key]["class"] == "unchanged", key
    assert "saved intent stays unchanged" in str(
        by_key["enable_codeql"]["note"]
    )
    subjects = {
        action["subject"]
        for action in cli.update_required_actions(
            cli.Plan((), (), (), (), (), (), ()), rows, observed=observed
        )
    }
    assert not subjects & set(INTENT_KEYS)

    # Same visibility, but the observed entitlement no longer covers it.
    private = {**SAVED, "project_visibility": "private"}
    assert cli.observed_setting_differences(
        private, {}, private_context("disabled")
    ) == {"enable_codeql": False}
    assert (
        cli.observed_setting_differences(
            private, {}, private_context("enabled")
        )
        == {}
    )


def test_repository_identity_mismatch_fails_closed() -> None:
    """AC5: another repository stops; an override binds one plan only."""
    renamed = cli.RepositoryContext(
        "new-owner/renamed",
        "new-owner",
        "organization",
        "public",
        "github",
        True,
    )
    with pytest.raises(CliError, match="the target was not changed"):
        cli.require_repository_identity(SAVED, {}, renamed)
    live = "https://github.com/new-owner/renamed"
    cli.require_repository_identity(SAVED, {"repository_url": live}, renamed)
    with pytest.raises(CliError, match="does not name the repository"):
        cli.require_repository_identity(
            SAVED, {"repository_url": "https://github.com/x/y"}, renamed
        )
    # The override is a one-time input, never a saved setting.
    assert "repository_url" not in settings_schema.INTENT_SETTINGS
    assert "repository_url" not in settings_schema.DECISION_SETTINGS
    unknown_origin = cli.RepositoryContext(
        None, None, None, "private", "saved", False, "No origin."
    )
    cli.require_repository_identity(SAVED, {}, unknown_origin)


def test_update_identity_check_runs_before_any_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC5: `csarc update` stops on a mismatch before planning or writing."""
    root = repository(
        tmp_path / "product",
        {"origin": "https://github.com/new-owner/renamed.git"},
    )
    config = root / ".csarc/config.yml"
    config.parent.mkdir()
    config.write_text("schema_version: 2\n", encoding="utf-8")
    before = config.read_bytes()
    monkeypatch.setattr(
        cli,
        "load_saved_settings",
        lambda target: settings_schema.SavedSettings(2, {}, dict(SAVED)),
    )
    payload = {**OWNER_REPOSITORY, "full_name": "new-owner/renamed"}
    payload["owner"] = {"login": "new-owner", "type": "Organization"}
    monkeypatch.setattr(
        cli, "detector_api", api({"repos/new-owner/renamed": payload})
    )

    def no_render(*args: object, **kwargs: object) -> None:
        raise AssertionError("update planned past the identity check")

    monkeypatch.setattr(cli, "update_status", no_render)
    assert cli.main(["update", str(root), "--check"]) != 0
    assert config.read_bytes() == before
    assert sorted(path.name for path in root.iterdir()) == [".csarc", ".git"]
