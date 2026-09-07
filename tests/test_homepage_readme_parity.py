"""Regression checks for Issue #526: homepage / README.md content parity.

The repo-site's "index" slide (key renamed from "capability", now
labeled "首頁"/"Home") must show the same core content as the repository
`README.md` hero -- the
same capability table, the same required version/language facts -- and
that shared content must stay within an explicit, enforced length limit
(the "首頁" slide is one screen; `README.md`'s hero is the part GitHub
shows above the fold). These tests make both properties fail closed
instead of relying on manual review to notice drift or bloat.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]

# Length limits for the always-visible (non-collapsible) hero/home content.
# Each limit carries meaningful headroom over the content drafted for
# Issue #526 (README hero: 1141 chars/18 lines; zh home: 791 chars/14
# lines; en home: 1834 chars/14 lines) so ordinary wording tweaks do not
# immediately trip it, while still catching an accidental paste of the
# full README or an unrelated slide's content into this section.
README_HERO_MAX_CHARS = 1600
README_HERO_MAX_LINES = 28
ZH_HOME_MAX_CHARS = 1200
ZH_HOME_MAX_LINES = 22
EN_HOME_MAX_CHARS = 2400
EN_HOME_MAX_LINES = 22

# The exact capability table shared, byte-for-byte, between README.md and
# the zh-tw home slide's default ("basic") view -- the clearest possible
# proof that the two stay aligned instead of drifting into two separate
# descriptions of the same capability.
SHARED_CAPABILITY_TABLE = "\n".join(
    [
        "| 可以直接選擇 | 目前提供的正式能力 |",
        "| --- | --- |",
        (
            "| 程式語言 | Python、Rust、TypeScript "
            "可獨立複選；都不選時只使用共通工作流程 |"
        ),
        (
            "| 分支做法 | 每個交付批次有自己的開發分支、"
            "所有修改直接進 `main`，或先集中到 `dev` |"
        ),
        (
            "| 公版設定 | 建立／導入時把選項寫入 "
            "`.csarc/config.yml`；之後由公版更新，"
            "不必到不同檔案重複設定 |"
        ),
        (
            "| 共用能力 | 工作單（Issue）與變更提案（PR）"
            "表單、AI 工作規範、自動驗證、依賴安全、"
            "版本記錄與公版更新 |"
        ),
    ]
)


def _non_blank_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def _readme_hero() -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    hero, _, _rest = readme.partition("## 目錄")
    assert hero != readme, "README.md must still have a '## 目錄' heading"
    return hero


def _before_first_collapsible_boundary(basic: str) -> str:
    # `{{< detail` (always-visible aside) and `{{< disclosure` (collapsed
    # `<details>`) both mark the start of collapsible/secondary content,
    # not part of the always-visible home content this limit governs --
    # whichever one appears first ends the visible body.
    boundaries = [
        index
        for index in (basic.find("{{< detail"), basic.find("{{< disclosure"))
        if index != -1
    ]
    return basic[: min(boundaries)] if boundaries else basic


def _zh_home_visible_body() -> str:
    zh = (ROOT / "site/content/_index.zh-tw.md").read_text(encoding="utf-8")
    basic = zh.split("{{< basic >}}", 1)[1].split("{{< /basic >}}", 1)[0]
    return _before_first_collapsible_boundary(basic)


def _en_home_visible_body() -> str:
    # Issue #681/#682 UX review, P1: the en home slide now carries the
    # same legacy (standard-mode interactive hero) / basic (ops-mode plain
    # body, mirroring README) split as zh-tw's, instead of one flat body
    # -- see _zh_home_visible_body. This length limit governs only the
    # always-visible basic/README-mirroring content, not the interactive
    # hero, whose HTML markup is not comparable to README prose length.
    en = (ROOT / "site/content/_index.en.md").read_text(encoding="utf-8")
    basic = en.split("{{< basic >}}", 1)[1].split("{{< /basic >}}", 1)[0]
    return _before_first_collapsible_boundary(basic)


def test_readme_hero_exists_before_toc() -> None:
    hero = _readme_hero()
    assert "# CSARC Repo Template" in hero
    assert "## 目錄" not in hero


def test_readme_hero_length_is_bounded() -> None:
    hero = _readme_hero()
    assert len(hero) <= README_HERO_MAX_CHARS, (
        f"README.md hero grew to {len(hero)} chars "
        f"(limit {README_HERO_MAX_CHARS}); trim it or raise the limit "
        "deliberately alongside the site home slide's own limit"
    )
    assert len(_non_blank_lines(hero)) <= README_HERO_MAX_LINES


def test_zh_home_length_is_bounded() -> None:
    visible = _zh_home_visible_body()
    assert len(visible) <= ZH_HOME_MAX_CHARS, (
        f"zh-tw home slide grew to {len(visible)} chars "
        f"(limit {ZH_HOME_MAX_CHARS})"
    )
    assert len(_non_blank_lines(visible)) <= ZH_HOME_MAX_LINES


def test_en_home_length_is_bounded() -> None:
    visible = _en_home_visible_body()
    assert len(visible) <= EN_HOME_MAX_CHARS, (
        f"en home slide grew to {len(visible)} chars "
        f"(limit {EN_HOME_MAX_CHARS})"
    )
    assert len(_non_blank_lines(visible)) <= EN_HOME_MAX_LINES


def test_capability_table_is_identical_in_readme_and_zh_home() -> None:
    """The exact GFM table must be byte-identical in both places.

    This is the literal, machine-checkable core of Issue #526: the
    homepage and README.md must show "the same thing", not two
    independently-worded descriptions of the same capability.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    zh = (ROOT / "site/content/_index.zh-tw.md").read_text(encoding="utf-8")
    assert SHARED_CAPABILITY_TABLE in readme
    assert SHARED_CAPABILITY_TABLE in zh


def test_home_slide_renamed_in_navigation() -> None:
    navigation = json.loads(
        (ROOT / "site/data/navigation.json").read_text(encoding="utf-8")
    )
    entry = next(item for item in navigation["items"] if item["key"] == "index")
    assert entry["labels"]["zh-tw"] == "首頁"
    assert entry["labels"]["en"] == "Home"
    assert entry["labels"]["zh-tw"] != "能力／導入"
    assert entry["labels"]["en"] != "Capability"


def test_required_facts_appear_in_readme_and_both_home_slides() -> None:
    """Issue #526: supported languages, repo/CLI, template, and engine
    versions must all be clearly visible on the homepage (and, since
    README.md is meant to mirror it, in the README hero too)."""
    readme = _readme_hero()
    zh = _zh_home_visible_body()
    en = _en_home_visible_body()

    for text, label in ((readme, "README"), (zh, "zh home")):
        assert "Python、Rust、TypeScript" in text, (
            f"{label} is missing the supported-languages line"
        )
        assert "v0.14.0" in text, f"{label} is missing the repo/CLI version"

    assert "Python, Rust, and TypeScript" in en
    assert "v0.14.0" in en

    # Site template / render engine versions: README states them as plain
    # text (it is never run through the site's `[[...]]` token
    # substitution), while both home slides use the live
    # `[[site_template_version]]` / `[[site_engine_version]]` tokens
    # (scripts/build_repo_site.py, Issue #524) instead of a literal
    # number, so a template/engine bump can never leave this page stale.
    version_data = json.loads(
        (ROOT / "site/version.json").read_text(encoding="utf-8")
    )
    assert f"| repo-site 排版模板版本 | {version_data['template']} |" in readme
    assert f"| repo-site 渲染引擎版本 | {version_data['engine']} |" in readme
    assert "[[site_template_version]]" in zh
    assert "[[site_engine_version]]" in zh
    assert "[[site_template_version]]" in en
    assert "[[site_engine_version]]" in en


def test_zh_home_repo_version_mentions_stay_in_sync() -> None:
    """Issue #694: the zh-tw file mentions the repo/CLI version twice,
    both carrying a live `x-release-please-version` marker -- once in
    the legacy/technical badge, once in the always-visible basic-mode
    paragraph (`<p class="template-version">`, mirroring en's own
    structure -- see test_en_home_repo_version_mentions_stay_in_sync).
    The version used to sit as unmarked plain text in a table cell
    instead (the site's own minimal Markdown renderer -- unlike
    GitHub's -- HTML-escapes a raw comment placed inside a table cell,
    so a marker could not go there safely), which meant a release bump
    only updated the badge and silently drifted the table cell on every
    release (v0.14.0 and v0.15.0 both needed a manual fix). Moving it to
    its own raw-HTML line lets the marker live there safely, so both
    mentions now update automatically together; this test just guards
    against the two ever drifting again."""
    zh = (ROOT / "site/content/_index.zh-tw.md").read_text(encoding="utf-8")
    badge_match = re.search(
        r'<span class="package-badge muted">(v[\d.]+)</span>'
        r"<!-- x-release-please-version -->",
        zh,
    )
    paragraph_match = re.search(
        r"公版版本：</strong>(v[\d.]+)<!-- x-release-please-version -->",
        zh,
    )
    assert badge_match, "legacy badge's marked version mention is missing"
    assert paragraph_match, "basic-mode paragraph's marked version is missing"
    assert badge_match.group(1) == paragraph_match.group(1), (
        "zh-tw home content's two repo-version mentions drifted: "
        f"badge={badge_match.group(1)!r} paragraph={paragraph_match.group(1)!r}"
    )


def test_zh_home_release_markers_are_each_on_their_own_raw_html_line() -> None:
    """Issue #694: mirrors
    test_en_home_release_markers_are_each_on_their_own_raw_html_line now
    that zh-tw's basic-mode version mention is also a raw-HTML line
    instead of a table cell. Each marker must sit on its own line
    starting with `<` -- the only form the renderer passes through
    unescaped -- or the literal comment text leaks into the rendered
    page (see test_zh_home_repo_version_mentions_stay_in_sync's
    docstring for why a table cell cannot carry the marker safely)."""
    zh = (ROOT / "site/content/_index.zh-tw.md").read_text(encoding="utf-8")
    lines = zh.splitlines()
    marker_lines = [
        line for line in lines if "x-release-please-version" in line
    ]
    assert len(marker_lines) == 2
    for marker_line in marker_lines:
        assert marker_line.strip().startswith("<"), (
            "each release marker must sit on its own raw-HTML line so "
            "the engine's Markdown-table escaping (see test_"
            "zh_home_repo_version_mentions_stay_in_sync's docstring) "
            "cannot turn it into visible text"
        )


def test_readme_and_manifest_versions_match() -> None:
    """README's repo/CLI version marker must match the release-please
    manifest -- both are meant to describe the same released version."""
    manifest = json.loads(
        (ROOT / ".release-please-manifest.json").read_text(encoding="utf-8")
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"\| 公版版本 \| (v[\d.]+)<!--", readme)
    assert match, "README.md is missing its marked repo/CLI version cell"
    assert match.group(1) == f"v{manifest['.']}"


def test_en_home_release_markers_are_each_on_their_own_raw_html_line() -> None:
    """Issue #681/#682 UX review, P1: since the en home slide gained the
    same legacy (badge)/basic (paragraph) split as zh-tw, it now marks
    the repo/CLI version in two places, matching zh-tw's own count (see
    test_zh_home_repo_version_mentions_stay_in_sync and its sibling
    test_zh_home_release_markers_are_each_on_their_own_raw_html_line,
    which now mirrors this test since Issue #694 gave zh-tw's own
    basic-mode mention the same raw-HTML-line structure). Each must
    still sit on its own raw-HTML line (the renderer only passes a full
    line through unescaped when it starts with `<`; anywhere else the
    literal comment text would leak into the rendered page)."""
    en = (ROOT / "site/content/_index.en.md").read_text(encoding="utf-8")
    lines = en.splitlines()
    marker_lines = [
        line for line in lines if "x-release-please-version" in line
    ]
    assert len(marker_lines) == 2
    for marker_line in marker_lines:
        assert marker_line.strip().startswith("<"), (
            "each release marker must sit on its own raw-HTML line so "
            "the engine's Markdown-table escaping (see test_"
            "zh_home_repo_version_mentions_stay_in_sync's docstring) "
            "cannot turn it into visible text"
        )


def test_en_home_repo_version_mentions_stay_in_sync() -> None:
    """Issue #681/#682 UX review, P1: mirrors
    test_zh_home_repo_version_mentions_stay_in_sync now that the en home
    slide also mentions the repo/CLI version twice -- once in the legacy
    hero's badge, once in the always-visible basic-mode paragraph."""
    en = (ROOT / "site/content/_index.en.md").read_text(encoding="utf-8")
    badge_match = re.search(
        r'<span class="package-badge muted">(v[\d.]+)</span>'
        r"<!-- x-release-please-version -->",
        en,
    )
    paragraph_match = re.search(
        r"Template release:</strong> (v[\d.]+)"
        r"<!-- x-release-please-version -->",
        en,
    )
    assert badge_match, "legacy badge's marked version mention is missing"
    assert paragraph_match, "basic-mode paragraph's marked version is missing"
    assert badge_match.group(1) == paragraph_match.group(1), (
        "en home content's two repo-version mentions drifted: "
        f"badge={badge_match.group(1)!r} paragraph={paragraph_match.group(1)!r}"
    )


def test_release_please_tracks_both_language_home_files() -> None:
    """Both `_index.zh-tw.md` and `_index.en.md` carry a repo-version
    marker (Issue #526's "雙語皆同步" requirement), so both must be
    registered as release-please extra-files or only one language would
    stay current after a real release."""
    config = json.loads(
        (ROOT / "release-please-config.json").read_text(encoding="utf-8")
    )
    extra_files = {
        entry["path"]
        for entry in config["packages"]["."]["extra-files"]
        if entry.get("type") == "generic"
    }
    assert "site/content/_index.zh-tw.md" in extra_files
    assert "site/content/_index.en.md" in extra_files
