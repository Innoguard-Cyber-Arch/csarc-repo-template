"""Contract tests for the English and Chinese writing guides (#1218)."""

import re
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
ENGLISH = ROOT / "docs/writing-guide.en.md"
CHINESE = ROOT / "docs/writing-guide.md"
ENGLISH_TEMPLATE = ROOT / "template/.csarc/docs/writing-guide.en.md.jinja"
CHINESE_TEMPLATE = ROOT / "template/.csarc/docs/writing-guide.md"
AGENTS_TEMPLATE = ROOT / "template/AGENTS.md.jinja"
SKILL_LICENSE_LINES = (
    "Copyright (c) 2026 Raymond Hou (雷蒙三十)",
    "Permission is hereby granted, free of charge, to any person obtaining",
    "The above copyright notice and this permission notice shall be included",
    'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND',
)
# The only lines where the rendered template guide may differ from root:
# the root names its own glossary file, a generated project does not.
ROOT_ONLY_LINES = {
    "- E10. Use the terms of this repository as `site/data/glossary.toml` "
    "and the current specifications define them.",
}
TEMPLATE_ONLY_LINES = {
    "- E10. Use the terms of this project as its glossary and current "
    "specifications define them.",
}


def render(path: Path, **context: object) -> str:
    """Render one template file the way Copier does."""
    environment = Environment(
        autoescape=True, undefined=StrictUndefined, keep_trailing_newline=True
    )
    return environment.from_string(path.read_text(encoding="utf-8")).render(
        **context
    )


def test_english_template_matches_root_guide() -> None:
    """AC1: the shipped English guide carries the same rules as root."""
    root = ENGLISH.read_text(encoding="utf-8").splitlines()
    rendered = render(
        ENGLISH_TEMPLATE, documentation_languages="zh-tw+en"
    ).splitlines()
    assert set(root) - set(rendered) == ROOT_ONLY_LINES
    assert set(rendered) - set(root) == TEMPLATE_ONLY_LINES
    assert [line for line in root if line not in ROOT_ONLY_LINES] == [
        line for line in rendered if line not in TEMPLATE_ONLY_LINES
    ]


@pytest.mark.parametrize(
    ("languages", "chinese"),
    [("zh-tw", True), ("en", False), ("zh-tw+en", True), ("en+zh-tw", True)],
)
def test_chinese_guide_ships_only_for_chinese_projects(
    languages: str, chinese: bool
) -> None:
    """AC6: a project without Chinese text gets no Chinese guide or link."""
    excludes = yaml.safe_load(
        (ROOT / "copier.yml").read_text(encoding="utf-8")
    )["_exclude"]
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    excluded = {
        environment.from_string(rule).render(documentation_languages=languages)
        for rule in excludes
        if "writing-guide" in rule
    }
    assert (".csarc/docs/writing-guide.md" in excluded) is not chinese
    english = render(ENGLISH_TEMPLATE, documentation_languages=languages)
    agents = render(
        AGENTS_TEMPLATE,
        documentation_languages=languages,
        project_name="Fixture",
    )
    assert ("(writing-guide.md)" in english) is chinese
    assert ("(.csarc/docs/writing-guide.md)" in agents) is chinese
    assert "(.csarc/docs/writing-guide.en.md)" in agents
    assert english.endswith(".\n") and not english.endswith("\n\n")


def test_chinese_guide_is_paired_with_template() -> None:
    """AC2: root and generated projects read one Chinese guide."""
    assert CHINESE.read_bytes() == CHINESE_TEMPLATE.read_bytes()
    paired = (ROOT / "scripts/sync-paired-files.sh").read_text(encoding="utf-8")
    assert (
        '"docs/writing-guide.md|template/.csarc/docs/writing-guide.md"'
        in paired
    )


def test_english_guide_cites_ste_without_claiming_it() -> None:
    """AC1/R1: STE is cited as inspiration only."""
    text = ENGLISH.read_text(encoding="utf-8")
    assert "ASD-STE100 Simplified Technical English, Issue 9" in text
    assert "https://www.asd-ste100.org/" in text
    assert "does not contain STE rules or the STE dictionary" in text
    assert "is not STE-compliant" in text
    assert "`site/data/glossary.toml`" in text


def test_english_guide_defines_message_patterns_and_exceptions() -> None:
    """AC3: one pattern per message kind plus recorded exceptions."""
    text = ENGLISH.read_text(encoding="utf-8")
    for pattern in (
        "`ERROR: <what failed>: <why>. <what to do next>.`",
        "`WARNING: <what is at risk>: <why>. <what to do next>.`",
        "`NOTICE: <what happened or what the script does next>.`",
        "`OK: <what the script verified or changed>.`",
    ):
        assert pattern in text
    assert re.findall(r"^- (X\d)\. ", text, re.MULTILINE) == [
        f"X{index}" for index in range(1, 6)
    ]
    assert "`message-pattern: allow X<n> <reason>`" in text


def test_chinese_guide_keeps_source_and_license() -> None:
    """AC2/R2: the speak-human-tw source, version, and MIT notice stay."""
    text = CHINESE.read_text(encoding="utf-8")
    assert "speak-human-tw v1.4.0" in text
    assert "commit `72279f8`" in text
    assert "https://github.com/Raymondhou0917/speak-human-tw" in text
    assert "教育部《重訂標點符號手冊》" in text
    assert "模板不安裝、也不依賴它" in text
    for line in SKILL_LICENSE_LINES:
        assert line in text
    body = text.split("## 授權聲明", 1)[0]
    assert not re.search(r"[一-鿿][,.;:?!]", body)


def test_agents_files_link_guides_without_copying_rules() -> None:
    """AC5: AGENTS.md links the guides and copies none of their rules."""
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "(docs/writing-guide.en.md)" in agents
    assert "(docs/writing-guide.md)" in agents
    for text in (agents, AGENTS_TEMPLATE.read_text(encoding="utf-8")):
        assert "ERROR: <what failed>" not in text
        assert "E1." not in text
    policy = (ROOT / "docs/documentation-policy.md").read_text(encoding="utf-8")
    assert "## 寫作指引" in policy
    assert "[`writing-guide.en.md`](writing-guide.en.md)" in policy
