"""Keep rulesets, site tokens, and CLI hints on the current schema (#1090).

SPEC-009 (#1071) removed or reclassified settings; #1077 renders only the
payload each option uses. These checks prove the generated Rulesets cite
only checks a rendered workflow owns and never derive from a removed
setting, that repo-site tokens and config guidance name only current keys
in both languages, and that CLI repair hints suggest only `--data` keys and
flags the current CLI accepts.
"""

from __future__ import annotations

import itertools
import json
import re
import runpy
from pathlib import Path
from typing import Any

import jinja2
import pytest
import yaml

from csarc_cli import cli, governance_migration, settings_schema

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ROOT / "template/.csarc/policies"
WORKFLOWS = ROOT / "template/.github/workflows"
ENGINES = {
    "root": ROOT / "scripts",
    "template": ROOT / "template/.csarc/scripts",
}
# Each required context and the rendered workflow whose job publishes it.
REQUIRED_CHECK_OWNERS = {
    "title": "pr-policy.yml",
    "verify": "ci.yml",
    "review": "pr-review.yml",
}
# Keys a hint may suggest with `--data`: every current key plus the
# one-time inputs and live facts a plan accepts for a single run.
DATA_KEYS = (
    set(settings_schema.INTENT_SETTINGS)
    | set(settings_schema.DECISION_SETTINGS)
    | set(settings_schema.SEED_KEYS)
    | set(settings_schema.LIVE_KEYS)
    | set(settings_schema.ONE_TIME_INPUTS)
)
RETIRED = set(settings_schema.RETIRED_SETTINGS) - set(
    settings_schema.ONE_TIME_INPUTS
)


def current_context(**overrides: object) -> dict[str, object]:
    """Return a render context holding only current SPEC-009 keys."""
    context: dict[str, object] = {
        key: spec[1][0] if spec[1] else ""
        for key, spec in settings_schema.INTENT_SETTINGS.items()
    }
    context.update(
        lifecycle=["issues", "milestones"],
        languages=[],
        scheduled_checks=[],
        container=False,
        enable_codeql=False,
        coverage_threshold=80,
        code_owner="",
        project_verification_hook="",
        security_reporting_channel="Use the private security contact.",
        package_name="example",
        project_run_command="./.csarc/scripts/verify",
        project_name="Example",
        project_slug="example",
        project_description="Example project.",
        project_license="proprietary",
        copyright_holder="Example",
        repository_url="https://github.com/example/example",
        project_visibility="private",
        project_mode="new",
    )
    context.update(overrides)
    return context


def render_policy(name: str, context: dict[str, object]) -> dict[str, Any]:
    """Render one Ruleset template; an undefined (removed) key fails."""
    environment = jinja2.Environment(  # noqa: S701 - JSON, not HTML
        undefined=jinja2.StrictUndefined
    )
    template = environment.from_string(
        (POLICIES / f"{name}.json.jinja").read_text(encoding="utf-8")
    )
    return json.loads(template.render(**context))


def excluded(path: str, context: dict[str, object]) -> bool:
    """Evaluate copier.yml's `_exclude` rules for one rendered path."""
    rules = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    environment = jinja2.Environment()  # noqa: S701 - path rules
    for rule in rules["_exclude"]:
        if environment.from_string(rule).render(**context) == path:
            return True
    return False


MATRIX = list(
    itertools.product(
        ("local", "hosted"),
        ([], ["issues"], ["issues", "milestones"]),
        ("csarc-owned", "product-owned", "verification-only"),
    )
)


@pytest.mark.parametrize(
    ("verification_mode", "lifecycle", "release_ownership"), MATRIX
)
def test_required_checks_cite_only_rendered_workflow_checks(
    verification_mode: str, lifecycle: list[str], release_ownership: str
) -> None:
    """AC1/AC4: required checks follow the workflows each render ships."""
    context = current_context(
        verification_mode=verification_mode,
        lifecycle=lifecycle,
        release_ownership=release_ownership,
        project_mode=(
            "existing" if release_ownership == "product-owned" else "new"
        ),
    )
    required = render_policy("rulesets-required-checks", context)
    protected = render_policy("rulesets", context)

    # dev/m* delivery branches get the same required checks as the default
    # branch, matching the protected-branch Ruleset (no removed setting).
    assert required["conditions"] == protected["conditions"]
    assert required["conditions"]["ref_name"]["include"] == [
        "~DEFAULT_BRANCH",
        "refs/heads/dev/m*",
    ]
    assert required["bypass_actors"] == []
    contexts = {
        check["context"]
        for rule in required["rules"]
        for check in rule["parameters"]["required_status_checks"]
    }
    if verification_mode == "local":
        assert required["enforcement"] == "disabled"
        assert contexts == set()
        return
    assert required["enforcement"] == "active"
    assert contexts == set(REQUIRED_CHECK_OWNERS)
    for check, workflow in REQUIRED_CHECK_OWNERS.items():
        assert not excluded(f".github/workflows/{workflow}", context)
        source = WORKFLOWS / workflow
        if not source.exists():
            source = WORKFLOWS / f"{workflow}.jinja"
        text = source.read_text(encoding="utf-8")
        assert re.search(rf"(?m)^    name: {check}$", text), (check, workflow)


def test_root_rulesets_match_the_template_render_of_root_settings() -> None:
    """AC4: root policies equal the template render of root's own config."""
    config = yaml.safe_load(
        (ROOT / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    context = current_context(
        **{
            key: value
            for key, value in config.items()
            if key in settings_schema.INTENT_SETTINGS
        }
    )
    for name in ("rulesets", "rulesets-required-checks"):
        root = json.loads(
            (ROOT / f"policies/{name}.json").read_text(encoding="utf-8")
        )
        assert render_policy(name, context) == root, name


def test_ruleset_templates_name_no_retired_setting() -> None:
    """AC1/AC5: neither Ruleset template reads a removed setting."""
    for path in POLICIES.glob("rulesets*.json.jinja"):
        text = path.read_text(encoding="utf-8")
        expressions = " ".join(re.findall(r"{[{%](.*?)[%}]}", text))
        used = set(re.findall(r"\b([a-z][a-z0-9_]*)\b", expressions))
        assert used >= {"verification_mode"}, path.name
        assert not used & RETIRED, (path.name, sorted(used & RETIRED))


@pytest.mark.parametrize("engine", sorted(ENGINES))
def test_site_tokens_are_current_settings(engine: str) -> None:
    """AC2: tokens are current keys; retired ones map to current tokens."""
    build = runpy.run_path(str(ENGINES[engine] / "build_repo_site.py"))
    render = runpy.run_path(str(ENGINES[engine] / "render_site.py"))
    tokens = set(build["_CONFIG_TOKENS"])
    classes = settings_schema.classification()
    assert not tokens & RETIRED
    assert {classes[token] for token in tokens} <= {
        settings_schema.CLASS_INTENT,
        settings_schema.CLASS_SEED,
        settings_schema.CLASS_LIVE,
    }
    # The only live fact a token may show is the local-origin repository
    # URL; visibility is read from GitHub and is never a site token.
    assert {
        token
        for token in tokens
        if classes[token] == settings_schema.CLASS_LIVE
    } == {"repository_url"}
    retired_tokens: dict[str, str | None] = render["RETIRED_CONFIG_TOKENS"]
    for key, successor in retired_tokens.items():
        assert key not in tokens
        if key in settings_schema.RETIRED_SETTINGS:
            assert successor == settings_schema.RETIRED_SETTINGS[key]
        else:
            assert classes[key] == settings_schema.CLASS_LIVE
        assert successor is None or successor in tokens


@pytest.mark.parametrize("engine", sorted(ENGINES))
@pytest.mark.parametrize(
    ("token", "hint"),
    [
        ("features", "replace it with [[container]]"),
        ("i18n", "replace it with [[documentation_languages]]"),
        ("primary_language", "replace it with [[documentation_languages]]"),
        ("review", "replace it with [[admin_bypass]]"),
        ("project_visibility", "remove it"),
        ("branch_strategy", "remove it"),
    ],
)
def test_retired_site_token_names_its_replacement(
    engine: str, token: str, hint: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC2: an older consumer page is reported with its migration.

    Before #1090 the repo-site engine left an unknown `[[features]]` in the
    page verbatim without a word. Project-owned content from an older
    starter must not stop a `csarc update` (its Copier task builds the
    site), so the repo-site build warns with the replacement token; the
    handbook bundle keeps failing closed, now with the same hint.
    """
    build = runpy.run_path(str(ENGINES[engine] / "build_repo_site.py"))
    render = runpy.run_path(str(ENGINES[engine] / "render_site.py"))
    config = {"container": False, "admin_bypass": "off"}
    for lang in ("zh-tw", "en"):
        build["_substitute_config_tokens"](
            f"Value: [[{token}]]\n", config, lang=lang
        )
        warning = capsys.readouterr().err
        assert f"WARNING: Retired site content setting [[{token}]]: {hint}" in (
            warning
        )
    with pytest.raises(render["BundleError"]) as bundle_error:
        render["_substitute_config"](f"Value: [[{token}]]\n", config)
    assert f"[[{token}]]: {hint}" in str(bundle_error.value)


def test_template_site_content_uses_the_same_current_tokens() -> None:
    """AC2: both starter languages show the same current settings."""
    build = runpy.run_path(str(ENGINES["template"] / "build_repo_site.py"))
    tokens = set(build["_CONFIG_TOKENS"])
    content = ROOT / "template/docs/site/content"
    used = {
        lang: set(
            re.findall(
                r"\[\[([a-z_]+)\]\]",
                (content / f"_index.{lang}.md").read_text(encoding="utf-8"),
            )
        )
        for lang in ("zh-tw", "en")
    }
    assert used["zh-tw"] == used["en"]
    assert used["en"] <= tokens
    # Prose must not describe a removed setting as a saved choice either.
    for lang, stale in (("en", "branch strategy"), ("zh-tw", "分支策略")):
        text = (content / f"_index.{lang}.md").read_text(encoding="utf-8")
        assert stale not in text, lang
    readme = (ROOT / "template/.csarc/site/README.md").read_text(
        encoding="utf-8"
    )
    assert set(re.findall(r"\[\[([a-z_]+)\]\]", readme)) <= tokens


def _guidance_examples(node: object) -> list[dict[str, Any]]:
    """Return every config-guidance example with a file and code sample."""
    if isinstance(node, dict):
        found = [node] if "code" in node and "file" in node else []
        for value in node.values():
            found.extend(_guidance_examples(value))
        return found
    if isinstance(node, list):
        return [item for value in node for item in _guidance_examples(value)]
    return []


def test_config_guidance_samples_show_only_saved_settings() -> None:
    """AC2: config samples state only keys schema 2 saves, in both languages."""
    examples = _guidance_examples(
        json.loads(
            (ROOT / "site/data/config_examples.json").read_text(
                encoding="utf-8"
            )
        )
    )
    classes = settings_schema.classification()
    saved = {
        settings_schema.CLASS_INTENT,
        settings_schema.CLASS_DECISION,
        settings_schema.CLASS_METADATA,
    }
    keys: dict[str, set[str]] = {"zh-tw": set(), "en": set()}
    for example in examples:
        for lang, found in keys.items():
            for line in example["code"][lang].splitlines():
                match = re.match(r"^([a-z_]+):", line)
                if match and match.group(1) in classes:
                    assert classes[match.group(1)] in saved, (lang, line)
                    found.add(match.group(1))
    assert keys["zh-tw"] == keys["en"]


def _cli_flags() -> set[str]:
    """Return every option string the current CLI parser accepts."""
    flags: set[str] = set()
    parsers = [cli.parser()]
    while parsers:
        current = parsers.pop()
        for action in current._actions:
            flags.update(
                option for option in action.option_strings if option[:2] == "--"
            )
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                parsers.extend(choices.values())
    return flags


HINT_SOURCES = (
    *sorted((ROOT / "src/csarc_cli").glob("*.py")),
    *sorted(
        path
        for path in (ROOT / "template/.csarc/scripts").iterdir()
        if path.is_file()
    ),
)


def test_cli_hints_suggest_only_current_keys_and_flags() -> None:
    """AC3: every literal hint names a current key and an existing flag."""
    flags = _cli_flags()
    for path in HINT_SOURCES:
        text = path.read_text(encoding="utf-8")
        for key in re.findall(r"--data[ =]`?([a-z_]+)=", text):
            assert key in DATA_KEYS, (path.name, key)
        for hint in re.findall(
            r"csarc (?:init|adopt|update|status)\b[^\"'`\n]*", text
        ):
            for flag in re.findall(r"(--[a-z][a-z-]*)", hint):
                assert flag in flags, (path.name, hint)


def test_release_owner_hint_names_only_current_settings() -> None:
    """AC3: the incomplete-owner error suggests release_ownership only."""
    with pytest.raises(cli.CliError) as error:
        cli.release_contract(
            {"project_mode": "new", "release_ownership": "csarc-owned"}
        )
    message = str(error.value)
    keys = re.findall(r"--data ([a-z_]+)=", message)
    assert keys == ["release_ownership"]
    assert "release_ownership_reason" not in message
    settings_schema.reject_retired_data(dict.fromkeys(keys, "csarc-owned"))


def test_update_report_names_the_replacement_site_token() -> None:
    """AC2: the migration report tells a consumer how to fix its site page.

    The engines and the CLI keep one list: every retired site token the
    engines stop on has a report note, and live facts are not settings.
    """
    render = runpy.run_path(str(ENGINES["root"] / "render_site.py"))
    assert (
        set(render["RETIRED_CONFIG_TOKENS"]) - set(settings_schema.LIVE_KEYS)
        == settings_schema.RETIRED_SITE_TOKENS
    )
    classes = governance_migration.setting_classes(
        {"features": ["docker"], "i18n": "en-zh-tw", "reviewers": []},
        {"container": True, "documentation_languages": "zh-tw+en"},
    )
    assert classes["features"] == (
        "retired",
        "Retired; `container` carries this intent. Replace `[[features]]` "
        "in project-owned site content with `[[container]]`.",
    )
    assert "`[[documentation_languages]]`" in str(classes["i18n"][1])
    assert classes["reviewers"][1] == (
        "Retired; the current schema has no equivalent setting. Remove "
        "`[[reviewers]]` from project-owned site content."
    )
