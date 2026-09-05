import json
import re
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SITE_MODULE = runpy.run_path(str(ROOT / "scripts" / "build_decision_site.py"))
RENDER_SITE_MODULE = runpy.run_path(str(ROOT / "scripts" / "render_site.py"))
PARITY_MODULE = runpy.run_path(
    str(ROOT / "scripts" / "check-decision-site-parity")
)
AUDIT_TRAIL_GENERATOR_MODULE = runpy.run_path(
    str(ROOT / "scripts" / "generate_audit_trail.py")
)

BuildError = SITE_MODULE["BuildError"]
SiteData = SITE_MODULE["SiteData"]
RenderState = SITE_MODULE["RenderState"]
render_prose = SITE_MODULE["render_prose"]
render_mixed = SITE_MODULE["render_mixed"]
render_detail = SITE_MODULE["render_detail"]
render_disclosure = SITE_MODULE["render_disclosure"]
render_config_guidance = SITE_MODULE["render_config_guidance"]
render_file_map = SITE_MODULE["render_file_map"]
render_similar_tools = SITE_MODULE["render_similar_tools"]
render_testing = SITE_MODULE["render_testing"]
render_audit_trail = SITE_MODULE["render_audit_trail"]
render_journey_rail = SITE_MODULE["render_journey_rail"]
render_slide = SITE_MODULE["render_slide"]
render_page = SITE_MODULE["render_page"]
render_llms_txt = SITE_MODULE["render_llms_txt"]
load_site_data = SITE_MODULE["load_site_data"]
build = SITE_MODULE["build"]
_substitute_version_tokens = SITE_MODULE["_substitute_version_tokens"]
render = RENDER_SITE_MODULE["render"]
parse_parity = PARITY_MODULE["parse"]
compare_parity = PARITY_MODULE["compare"]


def _empty_data(**overrides: object) -> object:
    """A SiteData fixture with empty-but-valid sources, overridable by key."""
    base = {
        "navigation": {
            "labels": {
                "zh-tw": {
                    "ariaLabel": "簡報目錄",
                    "use": "使用",
                    "workflow": "流程",
                    "support": "管理",
                    "legend": "顏色說明",
                    "human": "需要人決策",
                    "automated": "自動完成",
                    "maintainer": "僅維運可見",
                },
                "en": {
                    "ariaLabel": "Outline",
                    "use": "Use",
                    "workflow": "Workflow",
                    "support": "Maintenance",
                    "legend": "Color key",
                    "human": "Human decision",
                    "automated": "Automated",
                    "maintainer": "Maintainers only",
                },
            },
            "items": [
                {
                    "key": "one",
                    "group": "use",
                    "participation": "human",
                    "labels": {"zh-tw": "第一", "en": "One"},
                },
                {
                    "key": "two",
                    "code": "01",
                    "group": "workflow",
                    "participation": "automated",
                    "labels": {"zh-tw": "第二", "en": "Two"},
                },
            ],
            "appendices": [
                {
                    "key": "appendix",
                    "participation": "maintainer",
                    "audience": "maintainer",
                    "labels": {"zh-tw": "附錄", "en": "Appendix"},
                },
            ],
        },
        "glossary": {
            "title": "Glossary",
            "summary_en": "Summary EN",
            "summary_zh_tw": "Summary ZH",
            "groups": [],
        },
        "config_examples": {
            "labels": {
                "zh-tw": {
                    "heading": "固定與可調政策",
                    "intro": "說明文字",
                    "configFile": "設定檔：",
                    "overlayAriaLabel": "覆蓋卡",
                    "overlayCloseAriaLabel": "關閉",
                },
                "en": {
                    "heading": "Policy",
                    "intro": "Intro",
                    "configFile": "Config file: ",
                    "overlayAriaLabel": "Overlay",
                    "overlayCloseAriaLabel": "Close",
                },
            },
            "tracks": {},
        },
        "similar_tools": {
            "comparisonDate": "2026-09-01",
            "releaseCutoff": "2026-03-01",
            "threshold": 5,
            "starThreshold": 1000,
            "labels": {"zh-tw": {}, "en": {}},
            "featureGroups": [],
            "features": [],
            "tools": [],
            "testing": {
                "labels": {"zh-tw": {}, "en": {}},
                "duration": {
                    "labels": {"zh-tw": {}, "en": {}},
                    "rows": [],
                },
                "groups": [],
            },
        },
        "file_map": {
            "labels": {
                "zh-tw": {"address": "檔案總管｜專案根目錄"},
                "en": {"address": "File Explorer | repository root"},
            },
            "responsibilityLabels": {
                "template": {"zh-tw": "公版主導", "en": "Template-led"},
                "shared": {"zh-tw": "共同維護", "en": "Shared"},
                "project": {"zh-tw": "專案持有", "en": "Project-owned"},
            },
            "entries": [],
        },
        "audit_trail": {
            "command": "python3 scripts/generate_audit_trail.py",
            "labels": {
                "zh-tw": {
                    "intro": "說明文字",
                    "tableAriaLabel": "表格",
                    "fileColumn": "檔案",
                    "descriptionColumn": "內容",
                    "columnsColumn": "欄位",
                    "freshnessLabel": "新鮮度",
                    "freshnessNote": "新鮮度說明",
                    "commandIntro": "重新產生：",
                    "commandOutro": "備註",
                    "evidenceIntro": "延伸閱讀：",
                },
                "en": {
                    "intro": "Intro",
                    "tableAriaLabel": "Table",
                    "fileColumn": "File",
                    "descriptionColumn": "Contents",
                    "columnsColumn": "Columns",
                    "freshnessLabel": "Freshness",
                    "freshnessNote": "Freshness note",
                    "commandIntro": "Regenerate with:",
                    "commandOutro": "note",
                    "evidenceIntro": "Further reading:",
                },
            },
            "files": [],
        },
        "version": {
            "engine": "1.0.0",
            "template": "1.0.0",
            "compatible_template_range": ">=1.0.0 <2.0.0",
        },
    }
    base.update(overrides)
    return SiteData(**base)


# --- render_prose ----------------------------------------------------------


def test_prose_renders_paragraph_with_inline_spans() -> None:
    state = RenderState()
    html = render_prose(
        "Plain **bold** and `code` and [link](https://example.com).",
        state=state,
    )
    assert html == (
        "<p>Plain <strong>bold</strong> and <code>code</code> and "
        '<a href="https://example.com" target="_blank" '
        'rel="noreferrer">link</a>.</p>'
    )


def test_prose_bold_span_survives_an_embedded_asterisk() -> None:
    # Regression for the goldmark/CommonMark flanking-rule edge case found
    # while porting site/content/_index.en.md's "contract" slide: a bold
    # span wrapping an inline code span that itself contains "*" (e.g.
    # `dev/m*`) must still close instead of leaving literal "**" markers.
    state = RenderState()
    html = render_prose("**Work PR (`dev/m*`):** text", state=state)
    assert html == "<p><strong>Work PR (<code>dev/m*</code>):</strong> text</p>"


def test_prose_headings_get_slug_ids_and_levels() -> None:
    state = RenderState()
    html = render_prose("## Our Choice\n\nBody.\n\n### Sub Point", state=state)
    assert '<h2 id="our-choice">Our Choice</h2>' in html
    assert '<h3 id="sub-point">Sub Point</h3>' in html


def test_prose_nested_list_wraps_child_ul_inside_parent_li() -> None:
    state = RenderState()
    markdown = (
        "- **Milestone:** top level\n"
        "  - Nested one\n"
        "  - Nested two\n"
        "- **Issue:** another top item\n"
    )
    html = render_prose(markdown, state=state)
    assert html == (
        "<ul>"
        "<li><strong>Milestone:</strong> top level"
        "<ul><li>Nested one</li><li>Nested two</li></ul>"
        "</li>"
        "<li><strong>Issue:</strong> another top item</li>"
        "</ul>"
    )


def test_prose_renders_pipe_table_ignoring_alignment_row() -> None:
    state = RenderState()
    markdown = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    html = render_prose(markdown, state=state)
    assert html == (
        "<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody>"
        "<tr><td>1</td><td>2</td></tr></tbody></table>"
    )


def test_prose_passes_through_a_raw_html_line() -> None:
    # Hugo's `unsafe = true` goldmark setting let authors write raw HTML
    # (e.g. an <aside> banner) directly among the Markdown paragraphs.
    state = RenderState()
    html = render_prose(
        'Intro.\n\n<aside class="note">Raw</aside>\n\nOutro.', state=state
    )
    assert html == (
        '<p>Intro.</p>\n<aside class="note">Raw</aside>\n<p>Outro.</p>'
    )


def test_prose_fenced_code_renders_as_command_pre() -> None:
    state = RenderState()
    html = render_prose("```\nline one\nline two\n```", state=state)
    assert html == '<pre class="command"><code>line one\nline two</code></pre>'
    assert not state.mermaid_used


def test_prose_mermaid_fence_sets_state_and_renders_pre_mermaid() -> None:
    state = RenderState()
    html = render_prose("```mermaid\ngraph TD;\nA-->B;\n```", state=state)
    assert html == '<pre class="mermaid">graph TD;\nA--&gt;B;</pre>'
    assert state.mermaid_used


# --- detail / disclosure ----------------------------------------------------


def test_render_detail_wraps_title_and_prose() -> None:
    state = RenderState()
    html = render_detail(
        {"key": "k", "title": "Title"},
        "Body text.",
        lang="en",
        data=_empty_data(),
        state=state,
    )
    assert html == (
        '<aside class="technical-detail" data-content-key="k">'
        "<h3>Title</h3>\n"
        "<p>Body text.</p></aside>"
    )


def test_render_disclosure_wraps_summary_and_prose() -> None:
    state = RenderState()
    html = render_disclosure(
        {"key": "k", "title": "Title"},
        "Body text.",
        lang="en",
        data=_empty_data(),
        state=state,
    )
    assert html == (
        '<details class="package-disclosure" data-content-key="k">'
        '<summary><span class="tech-name">Title</span></summary>'
        '<div class="package-health"><p>Body text.</p></div></details>'
    )


# --- config-guidance ---------------------------------------------------


_CONFIG_TRACK = {
    "direct": False,
    "items": [
        {
            "title": {"zh-tw": "標題", "en": "Title"},
            "goal": {"zh-tw": "目標", "en": "Goal"},
            "file": {"zh-tw": "a.yml", "en": "a.yml"},
            "code": {
                "zh-tw": "line one\n\nline two",
                "en": "line one\n\nline two",
            },
        },
    ],
}


def test_config_guidance_unknown_track_raises() -> None:
    try:
        render_config_guidance("nope", lang="en", data=_empty_data())
    except BuildError as error:
        assert "nope" in str(error)
    else:
        raise AssertionError("expected BuildError")


def test_config_guidance_renders_one_static_block_regardless_of_direct() -> (
    None
):
    # Issue #525: the old fold-open/overlay-with-pager split collapsed into
    # one static block -- the simple/technical toggle alone (see
    # detail-toggle.css's `.config-guidance` rule) decides whether readers
    # see it at all, so the `direct` field no longer changes the markup.
    for direct in (False, True):
        data = _empty_data()
        track = {**_CONFIG_TRACK, "direct": direct}
        data.config_examples["tracks"]["pr"] = track
        html = render_config_guidance("pr", lang="en", data=data)
        assert html == (
            '<aside class="config-guidance" data-content-key="config-pr">'
            "<strong>Policy</strong><p>Intro</p>"
            '<div class="config-items">'
            '<article class="config-item">'
            "<h4>Title</h4><p>Goal</p>"
            '<p class="config-item-path">Config file: <code>a.yml</code></p>'
            '<pre class="code">line one&#10;&#10;line two</pre>'
            "</article></div></aside>"
        )
        # No click-to-reveal layer of any kind survives: no trigger button,
        # no fold, no overlay markup.
        assert "config-trigger" not in html
        assert "config-guidance-fold" not in html
        assert "config-overlay" not in html
        assert "<details" not in html


def test_config_guidance_matches_real_governance_item_newlines() -> None:
    # Replaces the retired Hugo end-to-end test in tests/test_config_guidance
    # (Issue #472/#524): the multi-line `code` sample for governance[0] must
    # survive rendering with its embedded newlines intact, without a Hugo
    # build.
    data = load_site_data(ROOT)
    config_examples = json.loads(
        (ROOT / "site/data/config_examples.json").read_text(encoding="utf-8")
    )
    item = config_examples["tracks"]["governance"]["items"][0]
    for lang in ("zh-tw", "en"):
        html = render_config_guidance("governance", lang=lang, data=data)
        expected_code = (
            item["code"][lang]
            .replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "&#10;")
        )
        assert f'<pre class="code">{expected_code}</pre>' in html
        assert f"<h4>{item['title'][lang]}</h4>" in html


# --- file map (Issue #534) ----------------------------------------------


def _file_map_data(entries: list[dict]) -> object:
    return _empty_data(
        file_map={
            "labels": {
                "zh-tw": {"address": "檔案總管"},
                "en": {"address": "Address"},
            },
            "responsibilityLabels": {
                "template": {"zh-tw": "公版主導", "en": "Template-led"},
                "shared": {"zh-tw": "共同維護", "en": "Shared"},
                "project": {"zh-tw": "專案持有", "en": "Project-owned"},
            },
            "entries": entries,
        }
    )


def test_file_map_renders_single_path_leaf_with_icon_tag_and_purpose() -> None:
    data = _file_map_data(
        [
            {
                "paths": ["AGENTS.md"],
                "responsibility": "template",
                "purpose": {"zh-tw": "規範", "en": "Rules"},
            }
        ]
    )
    html = render_file_map(lang="en", data=data)
    assert html == (
        '<div class="file-map-window">'
        '<div class="file-map-toolbar">'
        '<span class="file-map-dots" aria-hidden="true">'
        "<i></i><i></i><i></i></span>"
        '<code class="file-map-address">Address</code></div>'
        '<ul class="file-map-tree"><li class="file-map-node">'
        '<div class="file-map-row">'
        '<span class="file-map-icon is-file" aria-hidden="true"></span>'
        '<code class="file-map-name">AGENTS.md</code>'
        '<span class="file-map-tag file-map-tag-template">Template-led'
        "</span></div>"
        '<p class="file-map-purpose">Rules</p></li></ul></div>'
    )


def test_file_map_merges_shared_directory_prefix_from_separate_entries() -> (
    None
):
    # `.github/workflows/` and `.github/REVIEWERS` are two distinct
    # site/data/file_map.json entries (different purpose/responsibility),
    # but they share a real directory prefix: the tree must merge them
    # under one `.github/` branch instead of listing `.github/` twice.
    data = _file_map_data(
        [
            {
                "paths": [".github/workflows/"],
                "responsibility": "template",
                "purpose": {"zh-tw": "流程", "en": "Flows"},
            },
            {
                "paths": [".github/REVIEWERS"],
                "responsibility": "shared",
                "purpose": {"zh-tw": "審查", "en": "Reviewers"},
            },
        ]
    )
    html = render_file_map(lang="en", data=data)
    assert html == (
        '<div class="file-map-window">'
        '<div class="file-map-toolbar">'
        '<span class="file-map-dots" aria-hidden="true">'
        "<i></i><i></i><i></i></span>"
        '<code class="file-map-address">Address</code></div>'
        '<ul class="file-map-tree"><li class="file-map-node">'
        '<details class="file-map-branch" open>'
        '<summary class="file-map-summary">'
        '<span class="file-map-row">'
        '<span class="file-map-icon is-dir" aria-hidden="true"></span>'
        '<code class="file-map-name">.github/</code></span></summary>'
        "<ul>"
        '<li class="file-map-node"><div class="file-map-row">'
        '<span class="file-map-icon is-dir" aria-hidden="true"></span>'
        '<code class="file-map-name">workflows/</code>'
        '<span class="file-map-tag file-map-tag-template">Template-led'
        "</span></div>"
        '<p class="file-map-purpose">Flows</p></li>'
        '<li class="file-map-node"><div class="file-map-row">'
        '<span class="file-map-icon is-file" aria-hidden="true"></span>'
        '<code class="file-map-name">REVIEWERS</code>'
        '<span class="file-map-tag file-map-tag-shared">Shared</span>'
        "</div>"
        '<p class="file-map-purpose">Reviewers</p></li>'
        "</ul></details></li></ul></div>"
    )


def test_file_map_renders_non_path_note_after_the_name() -> None:
    # site/data/file_map.json's "src/" entry appends a non-path note
    # ("product tests, and product specifications") that was part of the
    # original table's path cell but isn't a real path itself.
    data = _file_map_data(
        [
            {
                "paths": ["src/"],
                "responsibility": "project",
                "note": {"zh-tw": "、額外文字", "en": ", extra text"},
                "purpose": {"zh-tw": "行為", "en": "Behavior"},
            }
        ]
    )
    html = render_file_map(lang="en", data=data)
    assert html == (
        '<div class="file-map-window">'
        '<div class="file-map-toolbar">'
        '<span class="file-map-dots" aria-hidden="true">'
        "<i></i><i></i><i></i></span>"
        '<code class="file-map-address">Address</code></div>'
        '<ul class="file-map-tree"><li class="file-map-node">'
        '<div class="file-map-row">'
        '<span class="file-map-icon is-dir" aria-hidden="true"></span>'
        '<code class="file-map-name">src/</code>'
        '<span class="file-map-note">, extra text</span>'
        '<span class="file-map-tag file-map-tag-project">Project-owned'
        "</span></div>"
        '<p class="file-map-purpose">Behavior</p></li></ul></div>'
    )


def test_file_map_matches_real_workflow_directory_and_paths() -> None:
    # Content-fidelity check against the real site/data/file_map.json (no
    # Hugo, mirrors test_config_guidance_matches_real_governance_item_
    # newlines): every literal path must exist in this repository, and the
    # `.github/workflows/` entry's purpose must still name every active
    # workflow file -- the same invariant
    # tests/test_render_site.py::test_overview_matches_active_workflows_
    # and_uses_plain_language proves from the other side.
    data = load_site_data(ROOT)
    file_map = data.file_map
    for entry in file_map["entries"]:
        for path in entry["paths"]:
            assert (ROOT / path).exists(), f"file-map path missing: {path}"
    html = render_file_map(lang="zh-tw", data=data)
    assert "<code>" not in html  # never fall back to un-styled inline code
    assert html.count('<span class="file-map-icon is-dir"') >= 1
    assert html.count('<span class="file-map-icon is-file"') >= 1
    for kind in ("template", "shared", "project"):
        assert f'file-map-tag-{kind}"' in html


# --- similar tools -----------------------------------------------------


def _tool(
    name: str,
    *,
    released: str,
    stars: str,
    full: list[str],
    partial: list[str],
) -> dict[str, object]:
    return {
        "name": name,
        "url": f"https://example.com/{name}",
        "version": "1.0.0",
        "released": released,
        "stars": stars,
        "coverage": {"full": full, "partial": partial},
        "position": {"zh-tw": "定位", "en": "Position"},
        "difference": {"zh-tw": ["差異"], "en": ["Difference"]},
        "comparisons": [],
    }


_SIMILAR_TOOLS_LABEL_KEYS = (
    "title",
    "primaryTabOverline",
    "primaryTab",
    "primaryLegend",
    "coverageLegend",
    "package",
    "version",
    "stars",
    "captureDate",
    "position",
    "difference",
    "coverage",
    "criterionLabel",
    "criterion",
    "full",
    "partial",
)


def _similar_tools_labels() -> dict[str, dict[str, str]]:
    return {
        "zh-tw": dict.fromkeys(_SIMILAR_TOOLS_LABEL_KEYS, "x"),
        "en": dict.fromkeys(_SIMILAR_TOOLS_LABEL_KEYS, "x"),
    }


def test_similar_tools_sorts_primary_by_coverage_before_ecosystem() -> None:
    data = _empty_data()
    data.similar_tools["tools"] = [
        _tool(
            "Wide",
            released="2026-06-01",
            stars="10",
            full=["01", "02"],
            partial=[],
        ),
        _tool(
            "Narrow", released="2026-06-01", stars="10", full=["01"], partial=[]
        ),
        _tool(
            "BigStars",
            released="2026-06-01",
            stars="5,000",
            full=[],
            partial=[],
        ),
        _tool(
            "TooOld",
            released="2020-01-01",
            stars="9,000",
            full=["01"],
            partial=[],
        ),
    ]
    data.similar_tools["labels"] = _similar_tools_labels()
    data.similar_tools["threshold"] = 1
    html = render_similar_tools(lang="en", data=data)

    wide_index = html.index("Wide")
    narrow_index = html.index("Narrow")
    assert wide_index < narrow_index  # more full-coverage journeys sorts first
    assert (
        "TooOld" not in html
    )  # released before releaseCutoff, excluded entirely
    # BigStars has zero journey coverage, so it ranks ecosystem-only; with no
    # featureGroups fixture to list its comparisons, it never appears in the
    # primary table it would otherwise be excluded from either way.
    assert "BigStars" not in html


def test_similar_tools_unknown_release_date_is_never_primary() -> None:
    data = _empty_data()
    data.similar_tools["tools"] = [
        _tool(
            "NoDate",
            released="unreleased",
            stars="1",
            full=["01", "02"],
            partial=[],
        )
    ]
    data.similar_tools["labels"] = _similar_tools_labels()
    html = render_similar_tools(lang="en", data=data)
    assert "NoDate" not in html


# --- testing appendix ----------------------------------------------------


def test_testing_pending_automation_defaults_issue_number() -> None:
    data = _empty_data()
    data.similar_tools["testing"]["labels"] = {
        "zh-tw": dict.fromkeys(
            (
                "title",
                "purpose",
                "shared",
                "templateOnly",
                "milestone",
                "release",
                "tests",
                "automation",
                "trigger",
                "timeout",
                "pending",
                "step",
            ),
            "x",
        ),
        "en": dict.fromkeys(
            (
                "title",
                "purpose",
                "shared",
                "templateOnly",
                "milestone",
                "release",
                "tests",
                "automation",
                "trigger",
                "timeout",
                "pending",
                "step",
            ),
            "x",
        ),
    }
    data.similar_tools["testing"]["duration"]["labels"] = {
        "zh-tw": dict.fromkeys(
            (
                "overline",
                "title",
                "heading",
                "scope",
                "runnerNote",
                "archiveNote",
                "stage",
                "shared",
                "templateOnly",
                "total",
            ),
            "x",
        ),
        "en": dict.fromkeys(
            (
                "overline",
                "title",
                "heading",
                "scope",
                "runnerNote",
                "archiveNote",
                "stage",
                "shared",
                "templateOnly",
                "total",
            ),
            "x",
        ),
    }
    data.similar_tools["testing"]["groups"] = [
        {
            "key": "work",
            "code": "01",
            "labels": {
                "zh-tw": {"title": "工作", "heading": "h", "scope": "s"},
                "en": {"title": "Work", "heading": "h", "scope": "s"},
            },
            "rows": [
                {
                    "purpose": {
                        "zh-tw": {"title": "t", "description": "d"},
                        "en": {"title": "t", "description": "d"},
                    },
                    "shared": {
                        "milestone": {
                            "automation": [
                                {
                                    "path": ".github/workflows/x.yml",
                                    "job": "job",
                                    "trigger": {"zh-tw": "t", "en": "t"},
                                    "timeout": "5 min",
                                    "pending": True,
                                }
                            ]
                        }
                    },
                }
            ],
        }
    ]
    html = render_testing(lang="en", data=data)
    assert "csarc-repo-template/issues/385" in html  # default automation issue
    assert '<div id="testing-panel-work"' in html


# --- governance audit trail (Issue #559) ----------------------------------


def _header_columns(markdown_table: str) -> list[str]:
    """Extract the header cell text from the first pipe-table row."""
    header_line = markdown_table.splitlines()[0]
    return [cell.strip() for cell in header_line.strip("|").split("|")]


def test_audit_trail_renders_file_rows_with_path_description_and_columns() -> (
    None
):
    data = _empty_data()
    data.audit_trail["files"] = [
        {
            "path": "docs/audit-trail/pr-audit.md",
            "description": {"zh-tw": "說明 `x`", "en": "About `x`"},
            "columns": ["PR", "governance_stage"],
        }
    ]
    html = render_audit_trail(lang="en", data=data)
    assert "<code>docs/audit-trail/pr-audit.md</code>" in html
    assert "About <code>x</code>" in html  # description inline-code renders
    assert "<code>PR</code>" in html
    assert "<code>governance_stage</code>" in html


def test_audit_trail_never_embeds_a_live_or_scheduled_snapshot() -> None:
    # Issue #559's decision: this static, file://-openable bundle can never
    # show live GitHub data, and no schedule/on-merge job generates and
    # commits one either -- see docs/adr/portable-decision-site.md. The
    # rendered copy must say so explicitly rather than implying real-time
    # or automatically refreshed content.
    data = _empty_data()
    data.audit_trail["labels"]["en"]["freshnessNote"] = (
        "never embeds live-fetched GitHub data, and cannot; no schedule "
        "or on-merge job generates and commits a snapshot"
    )
    html = render_audit_trail(lang="en", data=data)
    assert "never embeds live-fetched GitHub data, and cannot" in html
    assert (
        "no schedule or on-merge job generates and commits a snapshot" in html
    )
    assert "python3 scripts/generate_audit_trail.py" in html


def test_audit_trail_columns_match_the_real_generator_headers() -> None:
    # Content-fidelity check (mirrors test_file_map_matches_real_workflow_
    # directory_and_paths): site/data/audit_trail.json hand-curates each
    # output file's column list so both languages describe it identically,
    # but that copy must never silently drift from
    # scripts/generate_audit_trail.py's own Markdown header cells -- the
    # actual source of truth for what the generated files contain.
    data = load_site_data(ROOT)
    files_by_path = {
        entry["path"]: entry for entry in data.audit_trail["files"]
    }
    render_pr_audit_table = AUDIT_TRAIL_GENERATOR_MODULE[
        "render_pr_audit_table"
    ]
    render_rule_change_log = AUDIT_TRAIL_GENERATOR_MODULE[
        "render_rule_change_log"
    ]
    default_out_dir = AUDIT_TRAIL_GENERATOR_MODULE["DEFAULT_OUT_DIR"]
    pr_audit_file = AUDIT_TRAIL_GENERATOR_MODULE["DEFAULT_PR_AUDIT_FILE"]
    rule_change_file = AUDIT_TRAIL_GENERATOR_MODULE["DEFAULT_RULE_CHANGE_FILE"]
    rule_prefixes = AUDIT_TRAIL_GENERATOR_MODULE["DEFAULT_RULE_PREFIXES"]

    pr_audit_path = str(default_out_dir / pr_audit_file)
    rule_change_path = str(default_out_dir / rule_change_file)
    assert pr_audit_path in files_by_path
    assert rule_change_path in files_by_path

    pr_audit_markdown = render_pr_audit_table([], "owner/repo", "now")
    rule_change_markdown = render_rule_change_log(
        [], rule_prefixes, "owner/repo", "now"
    )
    assert files_by_path[pr_audit_path]["columns"] == _header_columns(
        pr_audit_markdown[pr_audit_markdown.index("| PR |") :]
    )
    assert files_by_path[rule_change_path]["columns"] == _header_columns(
        rule_change_markdown[rule_change_markdown.index("| Changed |") :]
    )


# --- journey rail --------------------------------------------------------


def test_journey_rail_marks_active_item_and_omits_code_for_use_group() -> None:
    nav = _empty_data().navigation
    html = render_journey_rail(nav, lang="en", active_key="two")
    assert '<li class="journey-item human">' in html  # "one" not active
    assert (
        '<li class="journey-item automated active" aria-current="step">' in html
    )
    assert '<span class="journey-code">' not in html.split("journey-main")[0]
    assert 'href="#appendix"' in html
    assert 'data-audience="maintainer"' in html


def test_journey_rail_threads_audience_onto_ordinary_items() -> None:
    # Issue #681: a maintainer-only item living directly in "items" (not
    # the separate "appendices" bookend list) must still carry
    # data-audience="maintainer" on its <li>, so the existing
    # detail-toggle.js/[data-audience="maintainer"] show/hide mechanism
    # keeps working after folding appendix links into a regular group.
    nav = _empty_data().navigation
    nav["items"].append(
        {
            "key": "three",
            "code": "02",
            "group": "workflow",
            "participation": "maintainer",
            "audience": "maintainer",
            "labels": {"zh-tw": "第三", "en": "Three"},
        }
    )
    html = render_journey_rail(nav, lang="en", active_key="two")
    assert (
        '<li class="journey-item maintainer" data-audience="maintainer">'
        in html
    )


# --- llms.txt --------------------------------------------------------------


def test_llms_txt_blank_line_placement_matches_two_groups() -> None:
    data = _empty_data()
    data.glossary = {
        "title": "T",
        "summary_en": "SE",
        "summary_zh_tw": "SZ",
        "source_base": "https://example.com/",
        "groups": [
            {
                "title_en": "G1E",
                "title_zh_tw": "G1Z",
                "terms": [
                    {
                        "term_en": "t1e",
                        "term_zh_tw": "t1z",
                        "path": "a.md",
                        "summary_en": "s1e",
                        "summary_zh_tw": "s1z",
                    },
                    {
                        "term_en": "t2e",
                        "term_zh_tw": "t2z",
                        "path": "b.md",
                        "summary_en": "s2e",
                        "summary_zh_tw": "s2z",
                    },
                ],
            },
            {
                "title_en": "G2E",
                "title_zh_tw": "G2Z",
                "terms": [
                    {
                        "term_en": "t3e",
                        "term_zh_tw": "t3z",
                        "path": "c.md",
                        "summary_en": "s3e",
                        "summary_zh_tw": "s3z",
                    },
                ],
            },
        ],
    }
    text = render_llms_txt(data)
    assert text == (
        "# T\n\n"
        "> SE / SZ\n"
        "\n## G1E / G1Z\n"
        "\n- [t1e / t1z](https://example.com/a.md): s1e / s1z"
        "\n- [t2e / t2z](https://example.com/b.md): s2e / s2z\n"
        "\n## G2E / G2Z\n"
        "\n- [t3e / t3z](https://example.com/c.md): s3e / s3z\n"
    )


def test_llms_txt_matches_committed_output() -> None:
    data = load_site_data(ROOT)
    generated = render_llms_txt(data)
    assert generated == (ROOT / "llms.txt").read_text(encoding="utf-8")
    assert generated == (ROOT / "docs/llms.txt").read_text(encoding="utf-8")


# --- version tokens ----------------------------------------------------


def test_substitute_version_tokens_resolves_known_keys_only() -> None:
    data = _empty_data(version={"engine": "1.2.3", "template": "4.5.6"})
    text = _substitute_version_tokens(
        "engine [[site_engine_version]], template [[site_template_version]]",
        data,
    )
    assert text == "engine 1.2.3, template 4.5.6"


def test_substitute_version_tokens_ignores_unrelated_bracket_text() -> None:
    # Root content documents scripts/render_site.py's own generic `[[key]]`
    # mechanism in prose using a literal `` `[[key]]` `` example; that must
    # not be treated as an unresolved version token.
    data = _empty_data()
    text = _substitute_version_tokens("see `[[key]]` for details", data)
    assert text == "see `[[key]]` for details"


# --- slide / page assembly ----------------------------------------------


def test_render_slide_marks_only_the_first_slide_active() -> None:
    data = _empty_data()
    state = RenderState()
    first = render_slide(
        {"key": "a", "title": "A"},
        "Body.",
        lang="en",
        data=data,
        state=state,
        ordinal=0,
    )
    second = render_slide(
        {"key": "b", "title": "B"},
        "Body.",
        lang="en",
        data=data,
        state=state,
        ordinal=1,
    )
    assert 'class="slide markdown-slide active"' in first
    assert 'class="slide markdown-slide"' in second


def test_render_slide_legacy_true_wraps_legacy_and_basic_blocks() -> None:
    data = _empty_data()
    state = RenderState()
    body = (
        '<aside class="selection-note">Note</aside>\n'
        "{{< legacy >}}<p>Raw HTML</p>{{< /legacy >}}\n"
        "{{< basic >}}Prose text.{{< /basic >}}\n"
    )
    html = render_slide(
        {"key": "k", "title": "K", "legacy": "true"},
        body,
        lang="en",
        data=data,
        state=state,
        ordinal=0,
    )
    assert '<header class="basic-header">' in html
    assert '<aside class="selection-note">Note</aside>' in html
    assert '<div class="legacy-content"><p>Raw HTML</p></div>' in html
    assert (
        '<div class="markdown-body basic-summary"><p>Prose text.</p></div>'
        in html
    )


def test_render_page_includes_mermaid_only_when_used() -> None:
    content = (
        "+++\n"
        'title = "T"\n\n'
        "[controls]\n"
        'language = "L"\ndetail = "D"\nsimple = "S"\ntechnical = "T"\n'
        'slides = "SL"\nprevious = "P"\nnext = "N"\nzoom = "Z"\n'
        'zoom_out = "ZO"\nzoom_reset = "ZR"\nzoom_in = "ZI"\nfit = "F"\n'
        "+++\n\n"
        '{{< slide key="a" title="A" legacy="false" >}}\n'
        "no diagram here\n"
        "{{< /slide >}}\n"
    )
    data = _empty_data()
    html = render_page(content, lang="en", data=data)
    assert "vendor/mermaid.min.js" not in html
    assert "mermaid.initialize" not in html

    diagram_content = content.replace(
        "no diagram here", "```mermaid\ngraph TD;\nA-->B;\n```"
    )
    diagram_html = render_page(diagram_content, lang="en", data=data)
    assert "vendor/mermaid.min.js" in diagram_html
    assert "mermaid.initialize" in diagram_html
    assert 'class="pre-mermaid"' not in diagram_html  # sanity: no stray class


def test_render_page_links_theme_css_after_base_stylesheet() -> None:
    # Issue #527: a fork-owned site/theme.css must be linked (and thus later
    # inlined by scripts/render_site.py) after the base stylesheets so CSS
    # cascade lets its overrides win over site/static/styles.css defaults.
    content = (
        "+++\n"
        'title = "T"\n\n'
        "[controls]\n"
        'language = "L"\ndetail = "D"\nsimple = "S"\ntechnical = "T"\n'
        'slides = "SL"\nprevious = "P"\nnext = "N"\nzoom = "Z"\n'
        'zoom_out = "ZO"\nzoom_reset = "ZR"\nzoom_in = "ZI"\nfit = "F"\n'
        "+++\n\n"
        '{{< slide key="a" title="A" legacy="false" >}}\nbody\n{{< /slide >}}\n'
    )
    html = render_page(content, lang="en", data=_empty_data())
    theme_link = '<link rel="stylesheet" href="../../site/theme.css">'
    assert theme_link in html
    assert html.index("site/static/detail-toggle.css") < html.index(
        "../../site/theme.css"
    )


def test_render_page_orders_language_switcher_zh_tw_then_en() -> None:
    content = (
        "+++\n"
        'title = "T"\n\n'
        "[controls]\n"
        'language = "L"\ndetail = "D"\nsimple = "S"\ntechnical = "T"\n'
        'slides = "SL"\nprevious = "P"\nnext = "N"\nzoom = "Z"\n'
        'zoom_out = "ZO"\nzoom_reset = "ZR"\nzoom_in = "ZI"\nfit = "F"\n'
        "+++\n\n"
        '{{< slide key="a" title="A" legacy="false" >}}\nbody\n{{< /slide >}}\n'
    )
    html = render_page(content, lang="zh-tw", data=_empty_data())
    zh_index = html.index("index.html")
    en_index = html.index("index.en.html")
    assert zh_index < en_index
    assert 'lang="zh-Hant-TW" aria-current="page"' in html


def _readme_fixture(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# T\n\n"
        "[English](README.en.md)\n\n"
        "zh-tw tagline paragraph.\n\n"
        "## 目錄\n\ntoc\n\n"
        "## 專案概述\n\nzh-tw overview body.\n\n"
        "## 快速開始\n\nzh-tw quickstart body.\n",
        encoding="utf-8",
    )
    (tmp_path / "README.en.md").write_text(
        "# T\n\n"
        "[繁體中文](README.md)\n\n"
        "en tagline paragraph.\n\n"
        "## Table of contents\n\ntoc\n\n"
        "## Overview\n\nen overview body.\n\n"
        "## Quick start\n\nen quickstart body.\n",
        encoding="utf-8",
    )


def test_render_page_sources_the_about_slide_from_readme_when_root_is_given(
    tmp_path: Path,
) -> None:
    # Issue #681: the "about" slide's body is README's own "## 專案概述"/
    # "## Overview" H2 section, read fresh, instead of a paraphrase hand-
    # copied into site/content/_index.<lang>.md.
    _readme_fixture(tmp_path)
    content = (
        "+++\n"
        'title = "T"\n\n'
        "[controls]\n"
        'language = "L"\ndetail = "D"\nsimple = "S"\ntechnical = "T"\n'
        'slides = "SL"\nprevious = "P"\nnext = "N"\nzoom = "Z"\n'
        'zoom_out = "ZO"\nzoom_reset = "ZR"\nzoom_in = "ZI"\nfit = "F"\n'
        "+++\n\n"
        '{{< slide key="about" title="About" legacy="false" >}}\n'
        "stale inline body, must not appear in the output\n"
        "{{< /slide >}}\n"
    )

    zh_html = render_page(
        content, lang="zh-tw", data=_empty_data(), root=tmp_path
    )
    en_html = render_page(content, lang="en", data=_empty_data(), root=tmp_path)

    assert "zh-tw overview body." in zh_html
    assert "en overview body." in en_html
    assert "stale inline body" not in zh_html
    assert "stale inline body" not in en_html


def test_render_page_raises_when_readme_is_missing_a_mapped_section(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# T\n\nno H2 sections at all here.\n", encoding="utf-8"
    )
    content = (
        "+++\n"
        'title = "T"\n\n'
        "[controls]\n"
        'language = "L"\ndetail = "D"\nsimple = "S"\ntechnical = "T"\n'
        'slides = "SL"\nprevious = "P"\nnext = "N"\nzoom = "Z"\n'
        'zoom_out = "ZO"\nzoom_reset = "ZR"\nzoom_in = "ZI"\nfit = "F"\n'
        "+++\n\n"
        '{{< slide key="about" title="About" legacy="false" >}}\n'
        "body\n"
        "{{< /slide >}}\n"
    )
    with pytest.raises(ValueError, match="專案概述"):
        render_page(content, lang="zh-tw", data=_empty_data(), root=tmp_path)


def test_render_page_ignores_readme_sourcing_without_root() -> None:
    # A caller that renders a synthetic fixture with no README (e.g. the
    # full-build integration tests below) must be unaffected.
    content = (
        "+++\n"
        'title = "T"\n\n'
        "[controls]\n"
        'language = "L"\ndetail = "D"\nsimple = "S"\ntechnical = "T"\n'
        'slides = "SL"\nprevious = "P"\nnext = "N"\nzoom = "Z"\n'
        'zoom_out = "ZO"\nzoom_reset = "ZR"\nzoom_in = "ZI"\nfit = "F"\n'
        "+++\n\n"
        '{{< slide key="about" title="About" legacy="false" >}}\n'
        "inline body stays\n"
        "{{< /slide >}}\n"
    )
    html = render_page(content, lang="zh-tw", data=_empty_data())
    assert "inline body stays" in html


def test_render_page_fills_a_readme_marker_span(tmp_path: Path) -> None:
    # Issue #681: a <!-- csarc-readme-<name>:start/end --> span anywhere in
    # a slide's body is replaced with the matching README fragment, for a
    # narrower injection than replacing the whole slide (e.g. the
    # capability slide's hero tagline, which otherwise keeps bespoke
    # legacy HTML around it).
    _readme_fixture(tmp_path)
    content = (
        "+++\n"
        'title = "T"\n\n'
        "[controls]\n"
        'language = "L"\ndetail = "D"\nsimple = "S"\ntechnical = "T"\n'
        'slides = "SL"\nprevious = "P"\nnext = "N"\nzoom = "Z"\n'
        'zoom_out = "ZO"\nzoom_reset = "ZR"\nzoom_in = "ZI"\nfit = "F"\n'
        "+++\n\n"
        '{{< slide key="capability" title="Cap" legacy="false" >}}\n'
        "<p><!-- csarc-readme-preamble-tagline:start -->stale"
        "<!-- csarc-readme-preamble-tagline:end --></p>\n"
        "{{< /slide >}}\n"
    )

    zh_html = render_page(
        content, lang="zh-tw", data=_empty_data(), root=tmp_path
    )
    en_html = render_page(content, lang="en", data=_empty_data(), root=tmp_path)

    assert "zh-tw tagline paragraph." in zh_html
    assert "en tagline paragraph." in en_html
    assert "stale" not in zh_html
    assert "stale" not in en_html


def test_readme_preamble_first_paragraph_skips_the_language_switcher_link(
    tmp_path: Path,
) -> None:
    _readme_fixture(tmp_path)
    tagline = SITE_MODULE["_readme_preamble_first_paragraph"](tmp_path, "zh-tw")
    assert tagline == "zh-tw tagline paragraph."


# --- full-build integration (small fixture site) -------------------------


def _write_fixture_site(root: Path) -> None:
    site = root / "site"
    (site / "content").mkdir(parents=True)
    (site / "data").mkdir(parents=True)
    (site / "static").mkdir(parents=True)
    (site / "static" / "styles.css").write_text(
        ":root{--yellow:#ffe600;}", encoding="utf-8"
    )
    (site / "static" / "detail-toggle.css").write_text("", encoding="utf-8")
    (site / "theme.css").write_text(":root {\n}\n", encoding="utf-8")
    (site / "static" / "deck.js").write_text("", encoding="utf-8")
    (site / "static" / "legacy-components.js").write_text("", encoding="utf-8")
    (site / "static" / "detail-toggle.js").write_text("", encoding="utf-8")
    (site / "version.json").write_text(
        json.dumps(
            {
                "engine": "1.0.0",
                "template": "1.0.0",
                "compatible_template_range": ">=1.0.0 <2.0.0",
            }
        ),
        encoding="utf-8",
    )
    (site / "data" / "navigation.json").write_text(
        json.dumps(
            {
                "labels": {
                    "zh-tw": {
                        "ariaLabel": "a",
                        "use": "u",
                        "workflow": "w",
                        "support": "s",
                        "legend": "l",
                        "human": "h",
                        "automated": "au",
                        "maintainer": "m",
                    },
                    "en": {
                        "ariaLabel": "a",
                        "use": "u",
                        "workflow": "w",
                        "support": "s",
                        "legend": "l",
                        "human": "h",
                        "automated": "au",
                        "maintainer": "m",
                    },
                },
                "items": [
                    {
                        "key": "capability",
                        "group": "use",
                        "participation": "human",
                        "labels": {"zh-tw": "能力", "en": "Capability"},
                    }
                ],
                "appendices": [],
            }
        ),
        encoding="utf-8",
    )
    (site / "data" / "glossary.toml").write_text(
        'title = "T"\n'
        'title_zh_tw = "T"\n'
        'title_en = "T"\n'
        'intro_zh_tw = "i"\n'
        'intro_en = "i"\n'
        'source_label_zh_tw = "s"\n'
        'source_label_en = "s"\n'
        'summary_zh_tw = "s"\n'
        'summary_en = "s"\n'
        'source_base = "https://example.com/"\n',
        encoding="utf-8",
    )
    (site / "data" / "config_examples.json").write_text(
        json.dumps(
            {
                "labels": {
                    "zh-tw": {
                        "heading": "h",
                        "intro": "i",
                        "configFile": "c",
                        "overlayAriaLabel": "o",
                        "overlayCloseAriaLabel": "x",
                    },
                    "en": {
                        "heading": "h",
                        "intro": "i",
                        "configFile": "c",
                        "overlayAriaLabel": "o",
                        "overlayCloseAriaLabel": "x",
                    },
                },
                "tracks": {},
            }
        ),
        encoding="utf-8",
    )
    (site / "data" / "similar_tools.json").write_text(
        json.dumps(
            {
                "comparisonDate": "2026-09-01",
                "releaseCutoff": "2026-01-01",
                "threshold": 5,
                "starThreshold": 1000,
                "labels": {"zh-tw": {}, "en": {}},
                "featureGroups": [],
                "features": [],
                "tools": [],
                "testing": {
                    "labels": {"zh-tw": {}, "en": {}},
                    "duration": {"labels": {"zh-tw": {}, "en": {}}, "rows": []},
                },
            }
        ),
        encoding="utf-8",
    )
    # The CI/CD settings appendix's per-step groups live under their own
    # site/data/testing/<key>.json files (Issue #533), loaded by
    # `_load_testing_groups` in the same fixed order as `_TESTING_STEP_ORDER`.
    # Nothing in this minimal fixture's content source calls
    # `{{< testing >}}`, so these stubs only need to satisfy that loader's
    # own consistency check, not carry real rows.
    testing_dir = site / "data" / "testing"
    testing_dir.mkdir()
    for key, code in (
        ("work", "01"),
        ("agents", "02"),
        ("contract", "03"),
        ("languages", "04"),
        ("supply", "05"),
        ("pr", "06"),
        ("delivery", "07"),
        ("governance", "08"),
        ("template-upgrade", "09"),
    ):
        (testing_dir / f"{key}.json").write_text(
            json.dumps(
                {
                    "key": key,
                    "code": code,
                    "labels": {
                        "zh-tw": {"title": "t", "heading": "h", "scope": "s"},
                        "en": {"title": "t", "heading": "h", "scope": "s"},
                    },
                    "rows": [],
                }
            ),
            encoding="utf-8",
        )
    (site / "data" / "file_map.json").write_text(
        json.dumps(
            {
                "labels": {
                    "zh-tw": {"address": "a"},
                    "en": {"address": "a"},
                },
                "responsibilityLabels": {
                    "template": {"zh-tw": "t", "en": "t"},
                    "shared": {"zh-tw": "s", "en": "s"},
                    "project": {"zh-tw": "p", "en": "p"},
                },
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    (site / "data" / "audit_trail.json").write_text(
        json.dumps(
            {
                "command": "python3 scripts/generate_audit_trail.py",
                "labels": {
                    "zh-tw": {
                        "intro": "i",
                        "tableAriaLabel": "t",
                        "fileColumn": "f",
                        "descriptionColumn": "d",
                        "columnsColumn": "c",
                        "freshnessLabel": "fl",
                        "freshnessNote": "fn",
                        "commandIntro": "ci",
                        "commandOutro": "co",
                        "evidenceIntro": "ei",
                    },
                    "en": {
                        "intro": "i",
                        "tableAriaLabel": "t",
                        "fileColumn": "f",
                        "descriptionColumn": "d",
                        "columnsColumn": "c",
                        "freshnessLabel": "fl",
                        "freshnessNote": "fn",
                        "commandIntro": "ci",
                        "commandOutro": "co",
                        "evidenceIntro": "ei",
                    },
                },
                "files": [],
            }
        ),
        encoding="utf-8",
    )
    for lang, title in (("zh-tw", "標題"), ("en", "Title")):
        (site / "content" / f"_index.{lang}.md").write_text(
            "+++\n"
            f'title = "{title}"\n\n'
            "[controls]\n"
            'language = "L"\ndetail = "D"\nsimple = "S"\ntechnical = "T"\n'
            'slides = "SL"\nprevious = "P"\nnext = "N"\nzoom = "Z"\n'
            'zoom_out = "ZO"\nzoom_reset = "ZR"\nzoom_in = "ZI"\nfit = "F"\n'
            "+++\n\n"
            '{{< slide key="capability" title="Cap" legacy="false" >}}\n'
            "Body paragraph.\n"
            "{{< /slide >}}\n",
            encoding="utf-8",
        )
    (root / "docs").mkdir()


def test_testing_groups_reject_an_unexpected_extra_file(tmp_path: Path) -> None:
    # `_load_testing_groups` only iterates the 9 known keys from
    # _TESTING_STEP_ORDER, so a stray extra file in site/data/testing/ was
    # previously never inspected at all -- silently ignored instead of
    # failing closed. It must now be rejected.
    _write_fixture_site(tmp_path)
    (tmp_path / "site" / "data" / "testing" / "zzz-extra.json").write_text(
        json.dumps({"key": "zzz-extra"}), encoding="utf-8"
    )
    try:
        build(tmp_path, tmp_path / "dist/decision-site")
    except BuildError as error:
        assert "unexpected" in str(error)
        assert "zzz-extra" in str(error)
    else:
        raise AssertionError("expected BuildError for the extra file")


def test_build_writes_both_languages_and_llms_txt(tmp_path: Path) -> None:
    _write_fixture_site(tmp_path)
    outputs = build(tmp_path, tmp_path / "dist/decision-site")
    assert set(outputs) == {"zh-tw", "en", "llms"}
    for path in outputs.values():
        assert path.is_file()
    assert "Body paragraph." in outputs["zh-tw"].read_text(encoding="utf-8")
    assert "{{<" not in outputs["en"].read_text(encoding="utf-8")


def test_build_output_feeds_render_site_unmodified(tmp_path: Path) -> None:
    # The engine's job stops at the pre-bundle HTML; render() -- completely
    # unmodified -- must still be able to inline it into a portable bundle.
    _write_fixture_site(tmp_path)
    outputs = build(tmp_path, tmp_path / "dist/decision-site")
    bundled = render(outputs["zh-tw"], root=tmp_path)
    assert '<link rel="stylesheet"' not in bundled
    assert "<script src=" not in bundled
    assert "Body paragraph." in bundled


def test_theme_css_default_is_a_no_op_override(tmp_path: Path) -> None:
    # Issue #527: site/theme.css ships empty, so the default build must not
    # change the palette declared in site/static/styles.css.
    _write_fixture_site(tmp_path)
    outputs = build(tmp_path, tmp_path / "dist/decision-site")
    bundled = render(outputs["zh-tw"], root=tmp_path)
    assert bundled.count("--yellow:#ffe600;") == 1


def test_theme_css_override_cascades_after_base_styles(tmp_path: Path) -> None:
    # A fork-owned override in site/theme.css must reach the final bundle,
    # positioned after site/static/styles.css so it wins the CSS cascade.
    _write_fixture_site(tmp_path)
    (tmp_path / "site" / "theme.css").write_text(
        ":root {\n  --yellow: #123456;\n}\n", encoding="utf-8"
    )
    outputs = build(tmp_path, tmp_path / "dist/decision-site")
    bundled = render(outputs["zh-tw"], root=tmp_path)
    assert "--yellow: #123456;" in bundled
    assert bundled.index("--yellow:#ffe600;") < bundled.index(
        "--yellow: #123456;"
    )


# --- real content regression (no Hugo) ------------------------------------


def test_real_content_builds_with_no_leftover_shortcode_markup(
    tmp_path: Path,
) -> None:
    outputs = build(ROOT, tmp_path / "dist/decision-site")
    for lang in ("zh-tw", "en"):
        text = outputs[lang].read_text(encoding="utf-8")
        assert "{{<" not in text
        assert "{{-" not in text


def test_real_content_slide_ids_match_navigation_items(tmp_path: Path) -> None:
    data = load_site_data(ROOT)
    outputs = build(ROOT, tmp_path / "dist/decision-site")
    text = outputs["en"].read_text(encoding="utf-8")
    ids = set(re.findall(r'data-content-key="([^"]*)"', text))
    for item in data.navigation["items"]:
        assert item["key"] in ids


def test_real_content_keeps_decision_site_key_parity(tmp_path: Path) -> None:
    """No slide key silently vanishes or appears unacknowledged (Issue #586).

    Only the key set is checked here (`keys_only=True`), matching what
    `scripts/build-decision-site --check` wires into CI. The exact-text
    comparison is not part of this regression; see Issue #590.
    """
    outputs = build(ROOT, tmp_path / "dist/decision-site")
    legacy = parse_parity(ROOT / "site/legacy/index.html", candidate=False)
    candidate = parse_parity(outputs["zh-tw"], candidate=True)
    assert compare_parity(legacy, candidate, keys_only=True) == []
