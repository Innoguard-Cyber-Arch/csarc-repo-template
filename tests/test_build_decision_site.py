import json
import re
import runpy
from pathlib import Path

ROOT = Path(__file__).parents[1]
SITE_MODULE = runpy.run_path(str(ROOT / "scripts" / "build_decision_site.py"))
RENDER_SITE_MODULE = runpy.run_path(str(ROOT / "scripts" / "render_site.py"))

BuildError = SITE_MODULE["BuildError"]
SiteData = SITE_MODULE["SiteData"]
RenderState = SITE_MODULE["RenderState"]
render_prose = SITE_MODULE["render_prose"]
render_mixed = SITE_MODULE["render_mixed"]
render_detail = SITE_MODULE["render_detail"]
render_disclosure = SITE_MODULE["render_disclosure"]
render_config_guidance = SITE_MODULE["render_config_guidance"]
render_similar_tools = SITE_MODULE["render_similar_tools"]
render_testing = SITE_MODULE["render_testing"]
render_journey_rail = SITE_MODULE["render_journey_rail"]
render_slide = SITE_MODULE["render_slide"]
render_page = SITE_MODULE["render_page"]
render_llms_txt = SITE_MODULE["render_llms_txt"]
load_site_data = SITE_MODULE["load_site_data"]
build = SITE_MODULE["build"]
_substitute_version_tokens = SITE_MODULE["_substitute_version_tokens"]
render = RENDER_SITE_MODULE["render"]


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


def test_config_guidance_overlay_mode_preserves_blank_line_in_code() -> None:
    data = _empty_data()
    data.config_examples["tracks"]["pr"] = _CONFIG_TRACK
    html = render_config_guidance("pr", lang="en", data=data)
    assert html.count('class="config-trigger"') == 1
    assert 'aria-controls="config-overlay-pr"' in html
    assert 'data-config-code="line one&#10;&#10;line two"' in html
    assert '<div class="config-actions">' in html
    assert '<aside id="config-overlay-pr" class="config-overlay" hidden' in html


def test_config_guidance_direct_mode_renders_inline_pre() -> None:
    data = _empty_data()
    data.config_examples["tracks"]["method"] = {
        **_CONFIG_TRACK,
        "direct": True,
    }
    html = render_config_guidance("method", lang="en", data=data)
    assert html.count('class="config-inline-detail"') == 1
    assert '<pre class="code">line one&#10;&#10;line two</pre>' in html
    assert "config-overlay" not in html  # only the overlay path needs one


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
        assert f'data-config-code="{expected_code}"' in html
        assert f'data-config-title="{item["title"][lang]}"' in html


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


# --- full-build integration (small fixture site) -------------------------


def _write_fixture_site(root: Path) -> None:
    site = root / "site"
    (site / "content").mkdir(parents=True)
    (site / "data").mkdir(parents=True)
    (site / "static").mkdir(parents=True)
    (site / "static" / "styles.css").write_text("body{}", encoding="utf-8")
    (site / "static" / "detail-toggle.css").write_text("", encoding="utf-8")
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
