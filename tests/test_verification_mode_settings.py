"""Verification mode per repository visibility (SPEC-011, Issue #1268).

The two mode settings replace `verification_mode`; `self-hosted` is valid
only for a private repository; an empty runner is the valid "not yet
registered" state; the legacy key migrates to both settings unchanged; and
the render, the governance route, and the merge decision all use the mode
for the live visibility. Root and generated readers are checked alike.
"""

from __future__ import annotations

import json
import runpy
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import jinja2
import pytest
import yaml
from settings_support import settings_text

from csarc_cli import cli, governance_migration, settings_schema, setup_plan

ROOT = Path(__file__).resolve().parents[1]
READERS = {
    "root": ROOT / "scripts/csarc_config.py",
    "template": ROOT / "template/.csarc/scripts/csarc_config.py",
}
EXECUTORS = {
    "root": ROOT / "scripts/trusted_executor.py",
    "template": ROOT / "template/.csarc/scripts/trusted_executor.py",
}
LIFECYCLES = {
    "root": ROOT / "scripts/pr_lifecycle.py",
    "template": ROOT / "template/.csarc/scripts/pr_lifecycle.py",
}
REGISTRATION = "https://github.com/Innoguard-Cyber-Arch/csarc-devops/issues/7"
RUNNER_TEXT = (
    f"self_hosted_runner:\n  id: vm-01\n  registration: {REGISTRATION}\n"
)
MODES = [
    (private, public)
    for private in ("self-hosted", "hosted", "local")
    for public in ("hosted", "local")
]
COPIER = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))


def reader(name: str) -> dict[str, Any]:
    """Load one csarc_config.py namespace."""
    return runpy.run_path(str(READERS[name]))


def config(
    private: str = "self-hosted",
    public: str = "hosted",
    extra: str = "",
    **overrides: object,
) -> str:
    """Return a schema 2 file in the new form, with self-hosted keys."""
    values: dict[str, object] = {
        "verification_mode": None,
        "verification_mode_private": private,
        "verification_mode_public": public,
        **overrides,
    }
    text = settings_text("", **values)
    if private == "self-hosted" and "self_hosted_runner" not in extra:
        extra = "self_hosted_runner: {}\n" + extra
    if private == "self-hosted" and "self_hosted_environments" not in extra:
        extra += "self_hosted_environments:\n- dev\n- uat\n"
    return text + extra


def load(name: str, text: str, tmp_path: Path) -> dict[str, object]:
    """Write and load one settings file with one reader."""
    path = tmp_path / "config.yml"
    path.write_text(text, encoding="utf-8")
    return reader(name)["load_config"](path)


@pytest.mark.parametrize("name", READERS)
@pytest.mark.parametrize(("private", "public"), MODES)
def test_every_mode_pair_is_valid_in_both_readers(
    name: str, private: str, public: str, tmp_path: Path
) -> None:
    """AC1/AC6: three private modes and two public modes load as written."""
    loaded = load(name, config(private, public), tmp_path)

    assert loaded["verification_mode_private"] == private
    assert loaded["verification_mode_public"] == public
    assert ("self_hosted_runner" in loaded) is (private == "self-hosted")
    settings_schema.validate_current(yaml.safe_load(config(private, public)))


@pytest.mark.parametrize("name", READERS)
def test_public_self_hosted_is_rejected(name: str, tmp_path: Path) -> None:
    """AC1/R2: a public repository can never be set to self-hosted."""
    text = config("hosted", "self-hosted")
    with pytest.raises(ValueError, match="verification_mode_public"):
        load(name, text, tmp_path)
    with pytest.raises(settings_schema.SettingsSchemaError):
        settings_schema.validate_current(yaml.safe_load(text))
    assert "self-hosted" not in str(
        COPIER["verification_mode_public"]["choices"]
    )


@pytest.mark.parametrize("name", READERS)
def test_registered_runner_parses_as_a_mapping(
    name: str, tmp_path: Path
) -> None:
    """AC1: a registered runner is one nested mapping with both keys."""
    loaded = load(name, config(extra=RUNNER_TEXT), tmp_path)

    assert loaded["self_hosted_runner"] == {
        "id": "vm-01",
        "registration": REGISTRATION,
    }
    settings_schema.validate_current(yaml.safe_load(config(extra=RUNNER_TEXT)))


INVALID = {
    "id-only": "self_hosted_runner:\n  id: vm-01\n",
    "other-repository": (
        "self_hosted_runner:\n  id: vm-01\n  registration: "
        "https://github.com/acme/other/issues/7\n"
    ),
    "extra-key": RUNNER_TEXT + "  host: vm.internal\n",
    "bad-id": RUNNER_TEXT.replace("vm-01", "VM_01"),
    "empty-environments": "self_hosted_environments: []\n",
    "unknown-environment": "self_hosted_environments:\n- prd\n",
}


@pytest.mark.parametrize("name", READERS)
@pytest.mark.parametrize("case", INVALID)
def test_incomplete_or_invalid_registration_fails_closed(
    name: str, case: str, tmp_path: Path
) -> None:
    """AC2: an incomplete or malformed registration fails closed."""
    text = config(extra=INVALID[case])
    with pytest.raises(ValueError, match="settings error"):
        load(name, text, tmp_path)
    with pytest.raises(settings_schema.SettingsSchemaError):
        settings_schema.validate_current(yaml.safe_load(text))


PRESENCE = {
    "runner-missing": "self_hosted_environments:\n- dev\n",
    "environments-missing": "self_hosted_runner: {}\n",
}


@pytest.mark.parametrize("name", READERS)
@pytest.mark.parametrize("case", [*PRESENCE, "local-with-runner"])
def test_self_hosted_keys_exist_exactly_for_self_hosted(
    name: str, case: str, tmp_path: Path
) -> None:
    """AC2: both keys exist for self-hosted, and neither otherwise."""
    if case == "local-with-runner":
        text = config("local", "hosted") + "self_hosted_runner: {}\n"
    else:
        text = (
            settings_text(
                verification_mode=None,
                verification_mode_private="self-hosted",
                verification_mode_public="hosted",
            )
            + PRESENCE[case]
        )
    with pytest.raises(ValueError, match="self_hosted"):
        load(name, text, tmp_path)
    with pytest.raises(settings_schema.SettingsSchemaError):
        settings_schema.validate_current(yaml.safe_load(text))


@pytest.mark.parametrize("name", READERS)
@pytest.mark.parametrize("legacy", ["local", "hosted"])
def test_legacy_mode_reads_as_both_visibilities(
    name: str, legacy: str, tmp_path: Path
) -> None:
    """AC2/R1: the legacy key keeps its value for both visibilities."""
    loaded = load(name, settings_text(verification_mode=legacy), tmp_path)

    assert loaded["verification_mode_private"] == legacy
    assert loaded["verification_mode_public"] == legacy
    assert settings_schema.verification_modes(
        yaml.safe_load(settings_text(verification_mode=legacy))
    ) == dict.fromkeys(settings_schema.MODE_KEYS, legacy)


@pytest.mark.parametrize("name", READERS)
def test_legacy_and_new_mode_together_fail_closed(
    name: str, tmp_path: Path
) -> None:
    """AC2: one file never mixes the legacy key with the new settings."""
    text = settings_text(verification_mode="hosted") + (
        "verification_mode_public: local\n"
    )
    with pytest.raises(ValueError, match="verification_mode"):
        load(name, text, tmp_path)
    with pytest.raises(settings_schema.SettingsSchemaError):
        settings_schema.validate_current(yaml.safe_load(text))


def test_config_text_round_trips_both_forms() -> None:
    """AC2: the CLI writer emits the new form or the transitional one."""
    for text in (config(extra=RUNNER_TEXT), settings_text()):
        values = yaml.safe_load(text)
        written = settings_schema.config_text(values)
        assert yaml.safe_load(written) == values


def test_legacy_data_key_is_refused() -> None:
    """AC2: `--data verification_mode=...` names the two new settings."""
    with pytest.raises(
        settings_schema.SettingsSchemaError, match="verification_mode_private"
    ):
        settings_schema.reject_retired_data({"verification_mode": "local"})


# ---------------------------------------------------------------------------
# Render (copier.yml) and the settings file template.
# ---------------------------------------------------------------------------

ENV = jinja2.Environment(undefined=jinja2.StrictUndefined)  # noqa: S701


def effective(context: Mapping[str, object]) -> str:
    """Render copier.yml's computed verification_mode default."""
    return ENV.from_string(COPIER["verification_mode"]["default"]).render(
        context
    )


def question_default(key: str, context: Mapping[str, object]) -> str:
    """Render one copier.yml default in a context."""
    return ENV.from_string(str(COPIER[key]["default"])).render(context)


@pytest.mark.parametrize(("private", "public"), MODES)
@pytest.mark.parametrize("visibility", ["private", "internal", "public"])
def test_render_uses_the_mode_for_its_visibility(
    private: str, public: str, visibility: str
) -> None:
    """AC3: the render reads the mode for the render's visibility."""
    context = {
        "verification_mode_private": private,
        "verification_mode_public": public,
        "project_visibility": visibility,
    }
    mode = effective(context)
    assert mode == (public if visibility == "public" else private)
    hosted_only = [
        item
        for item in COPIER["_exclude"]
        if "__keep_pr_policy_workflow__" in item
    ]
    local_only = [
        item
        for item in COPIER["_exclude"]
        if "__keep_local_verification__" in item
    ]
    render = {**context, "verification_mode": mode}
    excluded = {
        ENV.from_string(item).render(render)
        for item in hosted_only + local_only
    }
    if mode == "hosted":
        assert excluded == {
            "__keep_pr_policy_workflow__",
            ".csarc/scripts/local_verification.py",
        }
    else:
        assert excluded == {
            ".github/workflows/pr-policy.yml",
            "__keep_local_verification__",
        }


def test_new_project_defaults_and_legacy_answers() -> None:
    """AC1/AC2: defaults stay local/hosted; a legacy mode fills both."""
    assert question_default("verification_mode_private", {}) == "local"
    assert question_default("verification_mode_public", {}) == "hosted"
    for legacy in ("local", "hosted"):
        saved = {"verification_mode": legacy}
        assert question_default("verification_mode_private", saved) == legacy
        assert question_default("verification_mode_public", saved) == legacy


def test_self_hosted_is_not_offered_but_accepted_when_given() -> None:
    """AC1: self-hosted is disabled as a new choice, valid from data."""
    choices = COPIER["verification_mode_private"]["choices"]
    entry = next(
        value
        for value in choices.values()
        if isinstance(value, dict) and value["value"] == "self-hosted"
    )
    disabled = ENV.from_string(entry["validator"])
    assert disabled.render({}) == "Self-hosted verification is not offered yet."
    assert disabled.render({"verification_mode_private": "self-hosted"}) == ""
    assert "self-hosted" not in setup_plan.CHOICES["verification_mode_private"]
    for values in setup_plan.PRESET_VALUES.values():
        assert values.get("verification_mode_private") != "self-hosted"
    assert setup_plan.DEFAULT_WORK_MODE == "solo-local"


def render_settings(**answers: object) -> dict[str, object]:
    """Render the settings file template and load it with the reader."""
    env = jinja2.Environment(  # noqa: S701
        undefined=jinja2.StrictUndefined, extensions=["jinja2.ext.do"]
    )
    env.filters["to_nice_yaml"] = lambda value: yaml.safe_dump(
        value, default_flow_style=False, sort_keys=True, width=1_000_000
    )
    template = ROOT / "template/{{ _copier_conf.answers_file }}.jinja"
    values: dict[str, object] = {
        **dict.fromkeys(settings_schema.INTENT_SETTINGS, ""),
        **yaml.safe_load(settings_text()),
        "lifecycle": [],
        "_copier_answers": {},
        "self_hosted_runner": {},
        "self_hosted_environments": ["dev", "uat"],
        **answers,
    }
    return yaml.safe_load(
        env.from_string(template.read_text("utf-8")).render(values)
    )


def test_settings_template_writes_registration_only_for_self_hosted() -> None:
    """AC1: the registration keys appear only for a self-hosted mode."""
    saved = render_settings(
        verification_mode_private="self-hosted",
        verification_mode_public="hosted",
    )
    assert saved["self_hosted_runner"] == {}
    assert saved["self_hosted_environments"] == ["dev", "uat"]
    assert "verification_mode" not in saved
    hosted = render_settings(
        verification_mode_private="hosted", verification_mode_public="hosted"
    )
    assert "self_hosted_runner" not in hosted
    legacy = render_settings(
        verification_mode_private="local",
        verification_mode_public="local",
        csarc_legacy_verification_mode=True,
    )
    assert legacy["verification_mode"] == "local"
    assert not set(settings_schema.MODE_KEYS) & set(legacy)


# ---------------------------------------------------------------------------
# Migration and CLI.
# ---------------------------------------------------------------------------

REPOSITORY = cli.RepositoryContext(
    "acme/product", "acme", "Organization", "private", "github", True
)


@pytest.mark.parametrize("legacy", ["local", "hosted", None])
def test_update_migrates_the_legacy_mode_unchanged(legacy: str | None) -> None:
    """AC2/R1: an update writes the saved mode to both settings."""
    answers: dict[str, object] = {
        "project_mode": "existing",
        "project_visibility": "private",
        "code_owner": "",
        "admin_bypass": "always",
        "copilot_review": "allowed",
        "governance_mode": "managed",
        "lifecycle": [],
        "project_maturity": "early",
        "release_trigger": "main",
    }
    if legacy is not None:
        answers["verification_mode"] = legacy
    result, update_data = cli.update_plan_answers(answers, {}, REPOSITORY)
    expected = legacy or "hosted"
    for key in settings_schema.MODE_KEYS:
        assert result[key] == expected
        assert update_data[key] == expected
    classes = governance_migration.setting_classes(answers, result)
    for key in settings_schema.MODE_KEYS:
        assert classes[key] == ("exact", None)


def test_update_passes_the_effective_mode_to_both_render_sides() -> None:
    """AC3/R1: an update supplies the derived mode the old side needs.

    Copier evaluates the new `_exclude` rules on the old side too, where
    `verification_mode` is never computed; without the data every hosted
    workflow of a legacy hosted consumer would look removed (#1277 parity).
    """
    hosted = dict.fromkeys(settings_schema.MODE_KEYS, "hosted")
    for visibility, private, expected in (
        ("private", "local", "local"),
        ("public", "local", "hosted"),
        ("internal", "hosted", "hosted"),
    ):
        answers = {
            **hosted,
            "verification_mode_private": private,
            "project_visibility": visibility,
        }
        assert cli.effective_mode_data(answers) == {
            "verification_mode": expected
        }
    assert cli.effective_mode_data({}) == {}


def test_writer_keeps_the_legacy_key_until_the_reader_reads_both(
    tmp_path: Path,
) -> None:
    """AC2 (#1069 decision 8): the reader switches before the writer."""
    scripts = tmp_path / ".csarc/scripts"
    scripts.mkdir(parents=True)
    reader_path = scripts / "csarc_config.py"
    reader_path.write_text('"verification_mode": (KIND_CHOICE, ())\n', "utf-8")
    same = dict.fromkeys(settings_schema.MODE_KEYS, "hosted")
    assert cli.legacy_mode_writer(tmp_path, same) == {
        cli.LEGACY_MODE_FLAG: True
    }
    for changed in (
        {**same, "verification_mode_public": "local"},
        {**same, "verification_mode_private": "self-hosted"},
    ):
        with pytest.raises(cli.CliError, match="Merge this update"):
            cli.legacy_mode_writer(tmp_path, changed)
    reader_path.write_text(READERS["template"].read_text("utf-8"), "utf-8")
    assert cli.legacy_mode_writer(tmp_path, changed) == {}


# ---------------------------------------------------------------------------
# Governance route and merge decision.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", EXECUTORS)
def test_self_hosted_changes_take_the_governance_route(name: str) -> None:
    """AC4: a self-hosted switch or registration change is governed."""
    executor = runpy.run_path(str(EXECUTORS[name]))
    relaxations = executor["governance_relaxations"]
    hosted = dict.fromkeys(settings_schema.MODE_KEYS, "hosted")
    self_hosted = {
        **hosted,
        "verification_mode_private": "self-hosted",
        "self_hosted_runner": {},
        "self_hosted_environments": ["dev", "uat"],
    }
    assert relaxations(hosted, self_hosted)
    assert relaxations(self_hosted, hosted)
    registered = {
        **self_hosted,
        "self_hosted_runner": {"id": "vm-01", "registration": REGISTRATION},
    }
    assert relaxations(self_hosted, registered)
    assert relaxations(
        registered, {**registered, "self_hosted_environments": ["uat"]}
    )
    # Rewriting the legacy key into the same two values is not a relaxation.
    assert relaxations(hosted, dict(hosted)) == []
    local = dict.fromkeys(settings_schema.MODE_KEYS, "local")
    assert relaxations(local, hosted) == []
    assert relaxations(hosted, local)


class Visibility:
    """A GitHub stub that reports one repository visibility."""

    def __init__(self, private: object) -> None:
        self.private = private

    def get(self, repo: str, path: str) -> object:
        """Return the repository object."""
        assert (repo, path) == ("acme/product", "")
        return {"private": self.private}


RENDERED = {"hosted": "pr-policy.yml", "self-hosted": "csarc-verify.yml"}
OTHER_RENDER = {"hosted": "local", "local": "hosted", "self-hosted": "local"}


def lifecycle(
    name: str, root: Path, text: str, render: str
) -> Callable[..., str]:
    """Load one lifecycle module against a root rendered in one mode."""
    module = runpy.run_path(str(LIFECYCLES[name]))
    (root / ".csarc").mkdir(parents=True, exist_ok=True)
    (root / ".csarc/config.yml").write_text(text, encoding="utf-8")
    if render in RENDERED:
        (root / ".github/workflows").mkdir(parents=True, exist_ok=True)
        (root / ".github/workflows" / RENDERED[render]).write_text("", "utf-8")
    function = module["configured_verification_mode"]
    function.__globals__["repository_root"] = lambda: root
    return function


@pytest.mark.parametrize("name", LIFECYCLES)
@pytest.mark.parametrize(("private", "public"), MODES)
@pytest.mark.parametrize("is_private", [True, False])
def test_merge_uses_the_live_visibility_and_fails_closed(
    name: str, private: str, public: str, is_private: bool, tmp_path: Path
) -> None:
    """AC3/R2: merge reads live visibility; a render mismatch stops.

    #1269 replaced the blanket self-hosted refusal: the mode is returned and
    the merge then requires bound VM evidence (test_self_hosted_verification).
    """
    mode = private if is_private else public
    function = lifecycle(name, tmp_path, config(private, public), mode)
    github = Visibility(is_private)
    assert function(github, "acme/product") == mode
    # The same settings against the other render family must re-render.
    other = tmp_path / "other"
    function = lifecycle(
        name, other, config(private, public), OTHER_RENDER[mode]
    )
    with pytest.raises(RuntimeError, match="csarc update"):
        function(github, "acme/product")


@pytest.mark.parametrize("name", LIFECYCLES)
def test_merge_fails_closed_without_visibility(
    name: str, tmp_path: Path
) -> None:
    """AC3 (ADR Q7): an unreadable visibility never picks a mode."""
    function = lifecycle(name, tmp_path, config("hosted", "hosted"), "hosted")
    with pytest.raises(RuntimeError, match="visibility"):
        function(Visibility(None), "acme/product")


@pytest.mark.parametrize("name", LIFECYCLES)
def test_registered_self_hosted_still_waits_for_vm_evidence(
    name: str, tmp_path: Path
) -> None:
    """AC3: a registered runner never makes a merge pretend VM evidence.

    #1269: the mode is self-hosted, and without a bound VM run the evidence
    reader refuses the merge instead of using local or hosted evidence.
    """
    text = config(extra=RUNNER_TEXT)
    function = lifecycle(name, tmp_path, text, "self-hosted")
    assert function(Visibility(True), "acme/product") == "self-hosted"
    reader_path = LIFECYCLES[name].with_name("self_hosted_evidence.py")
    require = runpy.run_path(str(reader_path))["require"]

    class NoRuns:
        def collection(self, *_args: object) -> list[dict[str, Any]]:
            return []

    lease = {
        "head_sha": "a" * 40,
        "head_tree": "e" * 40,
        "base_ref": "main",
        "base_sha": "b" * 40,
    }
    pull = {"head": {"repo": {"full_name": "acme/product"}}}
    with pytest.raises(RuntimeError, match="no VM run"):
        require(
            NoRuns(),
            "acme/product",
            lease,
            pull,
            tmp_path / ".csarc/config.yml",
            "fast",
        )


def test_payload_fixtures_keep_the_default_and_add_self_hosted() -> None:
    """AC6 (ADR Q2): solo-default stays local; solo-self-hosted shares it."""
    payload = runpy.run_path(str(ROOT / "scripts/generated_payload.py"))
    fixtures = payload["FIXTURES"]
    assert fixtures["solo-default"]["verification_mode_private"] == "local"
    assert (
        fixtures["solo-self-hosted"]["verification_mode_private"]
        == "self-hosted"
    )
    for table in ("TARGETS", "RAW_TARGETS", "CONVERSION_OFFSETS"):
        assert (
            payload[table]["solo-self-hosted"] == payload[table]["solo-default"]
        )
    assert json.dumps(
        fixtures["solo-self-hosted"], sort_keys=True
    ) == json.dumps(
        {
            **fixtures["solo-default"],
            "verification_mode_private": "self-hosted",
            "verification_mode_public": "hosted",
        },
        sort_keys=True,
    )
