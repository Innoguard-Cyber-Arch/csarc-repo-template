"""Template-owned files stay in `.csarc/` or an ADR fixed location (#1070).

`docs/adr/generated-repository-layout.md` owns the allowlist of paths a
fresh render may create outside `.csarc/`. Generated-render coverage of the
same list lives in tests/test_generated_self_tests.py.
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

from csarc_cli.cli import option_retirements

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template"
ADR = ROOT / "docs/adr/generated-repository-layout.md"


def allowlist() -> list[str]:
    """Return the ADR's fixed-location patterns, without comments."""
    text = ADR.read_text(encoding="utf-8")
    section = text.split("## 固定位置 allowlist", 1)[1]
    block = re.search(r"```text\n(.*?)\n```", section, re.DOTALL)
    assert block is not None
    return [
        line.strip()
        for line in block.group(1).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def outside_control_layer(path: str, patterns: list[str]) -> bool:
    """Return whether one rendered path is outside every ADR pattern."""
    return not any(fnmatchcase(path, pattern) for pattern in patterns)


def rendered_names(relative: Path) -> list[str]:
    """Approximate the rendered path for one template source file."""
    text = relative.as_posix().removesuffix(".jinja")
    text = text.replace("{{project_slug}}", "project").replace(
        "{{package_name}}", "package"
    )
    if text.startswith("{% if") and "README" in text:
        return ["README.md", "README.en.md", "README.zh-tw.md"]
    return [text]


def test_allowlist_names_fixed_and_product_locations() -> None:
    """The ADR lists the platform, scanner, and agent fixed locations."""
    patterns = allowlist()
    for required in (
        ".github/workflows/*.yml",
        "SECURITY.md",
        ".github/SECURITY.md",
        "AGENTS.md",
        ".claude/CLAUDE.md",
        "pyproject.toml",
        "tests/test_smoke.py",
    ):
        assert required in patterns
    assert not any(pattern.startswith(".csarc") for pattern in patterns)
    assert not any(pattern.startswith("scripts/") for pattern in patterns)


def test_template_sources_outside_csarc_match_the_allowlist() -> None:
    """Every template source outside `.csarc/` renders to an allowed path."""
    patterns = allowlist()
    violations: list[str] = []
    for path in sorted(TEMPLATE.rglob("*")):
        relative = path.relative_to(TEMPLATE)
        if (
            not path.is_file()
            or relative.parts[0] == ".csarc"
            or "__pycache__" in relative.parts
            # Copier writes the answers file to .csarc/config.yml.
            or relative.name.startswith("{{ _copier_conf.answers_file }}")
        ):
            continue
        violations.extend(
            name
            for name in rendered_names(relative)
            if outside_control_layer(name, patterns)
        )
    assert violations == []


def adr_payload_rules() -> dict[str, str]:
    """Return the ADR's option-rendered `.csarc/` and `.github/` paths."""
    text = ADR.read_text(encoding="utf-8")
    section = text.split("## 依選項 render 的 payload", 1)[1]
    block = re.search(r"```text\n(.*?)\n```", section, re.DOTALL)
    assert block is not None
    rules: dict[str, str] = {}
    for line in block.group(1).splitlines():
        if line.strip() and not line.startswith("#"):
            path, _, condition = line.partition(" | ")
            rules[path.strip()] = condition.strip()
    return rules


def copier_payload_rules() -> dict[str, str]:
    """Return copier.yml's option-rendered `.csarc/` and `.github/` paths."""
    config = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    rules: dict[str, str] = {}
    for rule in config["_exclude"]:
        match = re.fullmatch(
            r"\{% if (.*?) %\}(.*?)\{% else %\}(.*?)\{% endif %\}", rule
        )
        if match is None:
            continue
        condition, kept, excluded = match.groups()
        if not kept.startswith("__keep"):
            condition, excluded = f"not ({condition})", kept
        if excluded.startswith((".csarc/", ".github/")):
            rules[excluded] = condition
    return rules


def test_adr_payload_table_matches_copier_exclusions() -> None:
    """AC7 (#1077): the ADR and Copier list the same payload rules."""
    assert adr_payload_rules() == copier_payload_rules()


def test_template_ships_no_self_test_or_dead_module() -> None:
    """AC1 (#1077): self-tests and caller-less modules never render."""
    scripts = TEMPLATE / ".csarc/scripts"
    assert not list(scripts.glob("test-*"))
    for name in ("security-smoke", "release_phase_rulesets.py"):
        assert not (scripts / name).exists(), name
    assert not (TEMPLATE / ".csarc/tests").exists()


def test_update_retires_only_csarc_files_the_new_options_drop() -> None:
    """AC7 (#1077): the CLI retires by the same render difference."""
    old = {
        ".csarc/scripts/request-reviewer": "a",
        ".csarc/scripts/verify": "b",
        ".github/workflows/release.yml": "c",
        "src/product/__init__.py": "d",
        "README.md": "e",
    }
    new = {".csarc/scripts/verify": "b", "README.md": "e"}
    assert option_retirements(old, new) == (
        ".csarc/scripts/request-reviewer",
        ".github/workflows/release.yml",
    )
