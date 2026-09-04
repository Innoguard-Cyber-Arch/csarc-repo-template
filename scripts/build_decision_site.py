"""Render the bilingual decision-site presentation from Markdown sources.

Pure-Python, stdlib-only replacement for the retired Hugo build (Issue
#524). `site/content/_index.{zh-tw,en}.md` keep their existing
`{{< slide key="..." >}}...{{< /slide >}}`-style block syntax unchanged;
this module parses that syntax (via `scripts/decision_site_blocks.py`) and
ports each Hugo shortcode/partial/home layout under `site/layouts/` to a
plain Python function reading the same `site/data/*.json`/`*.toml` files.

This module only produces the two languages' *pre-bundle* HTML sources
(under `dist/decision-site/`) plus the shared `llms.txt` index.
`scripts/render_site.py`'s `render()` -- completely unmodified -- then
inlines local CSS/JS/images and rejects any external runtime asset, exactly
as it already does for the generated-project handbook. That inlining step,
and the portable-bundle contract it enforces, are out of this module's
scope by design; see `docs/adr/portable-decision-site.md`.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import runpy
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol

_ROOT: Final = Path(__file__).resolve().parents[1]
_BLOCKS: Final = runpy.run_path(str(_ROOT / "scripts/decision_site_blocks.py"))
_RENDER_SITE: Final = runpy.run_path(str(_ROOT / "scripts/render_site.py"))
# Reused verbatim rather than reimplemented: the same small inline-Markdown
# subset (bold/code/links) already used for the generated-project handbook
# in scripts/render_site.py.
_inline_markdown: Final = _RENDER_SITE["_inline_markdown"]
_slug: Final = _RENDER_SITE["_slug"]

# Root content is not driven by `.csarc/config.yml`, and already documents
# scripts/render_site.py's generic, fail-closed `[[key]]` mechanism in prose
# using a literal `` `[[key]]` `` example (see the "docs-site"/governance
# slides). Reusing that generic `_substitute_config` here would treat "key"
# itself as an unresolved token and fail the build. So this engine only
# resolves the two known version-token names below and leaves every other
# `[[...]]` occurrence untouched, rather than erroring on it -- narrower
# than `_substitute_config`, but the same `[[key]]` substitution syntax, so
# a later homepage change (Issue #526) can still just write
# `[[site_engine_version]]` / `[[site_template_version]]`.
_VERSION_TOKENS: Final = {
    "site_engine_version": "engine",
    "site_template_version": "template",
}
_VERSION_TOKEN: Final = re.compile(
    r"\[\[(?P<key>" + "|".join(_VERSION_TOKENS) + r")\]\]"
)


def _substitute_version_tokens(markdown: str, data: SiteData) -> str:
    """Resolve `[[site_engine_version]]` / `[[site_template_version]]`."""

    def replace(match: re.Match[str]) -> str:
        return str(data.version[_VERSION_TOKENS[match.group("key")]])

    return _VERSION_TOKEN.sub(replace, markdown)


# Both outputs are written as siblings under dist/decision-site/, two
# directories below the repository root, so they share one relative asset
# path -- no more Hugo `en/` subdirectory or per-language `../` prefix.
_ASSET_PREFIX: Final = "../../"

_LANGUAGES: Final = {
    "zh-tw": {"code": "zh-Hant-TW", "name": "繁體中文", "output": "index.html"},
    "en": {"code": "en", "name": "English", "output": "index.en.html"},
}
# Matches site/hugo.toml's retired [languages] weight ordering.
_LANGUAGE_ORDER: Final = ("zh-tw", "en")

_FENCE: Final = re.compile(r"^```(?P<lang>\S*)\s*$")
_HEADING: Final = re.compile(r"^(?P<hashes>#{2,3})\s+(?P<text>.+)$")
_LIST_ITEM: Final = re.compile(
    r"^(?P<indent>\s*)(?P<marker>[-*]|\d+\.)\s+(?P<text>.+)$"
)
_BARE_SELF_CLOSING: Final = re.compile(
    r"^{{<\s*(?P<name>similar-tools|testing|audit-trail)\s*>}}$"
)


class BuildError(ValueError):
    """Report a source the engine cannot render."""


@dataclass
class SiteData:
    """The `site/data/*` sources every render function reads from."""

    navigation: dict[str, Any]
    glossary: dict[str, Any]
    config_examples: dict[str, Any]
    similar_tools: dict[str, Any]
    file_map: dict[str, Any]
    audit_trail: dict[str, Any]
    version: dict[str, Any]


@dataclass
class RenderState:
    """Mutable state threaded through one page's render, in reading order."""

    used_ids: set[str] = field(default_factory=set)
    mermaid_used: bool = False


def _esc(value: str) -> str:
    """Escape text for safe use as HTML element content or an attribute."""
    return html.escape(value, quote=True)


def _code_html(code: str) -> str:
    """Encode one config-guidance code sample the way Hugo's `$codeHTML` did.

    A literal newline surviving into a rendered `<pre>` or `data-*`
    attribute is harmless for this engine -- unlike the retired Hugo build,
    it never re-parses rendered shortcode output as Markdown, so the
    blank-line/raw-HTML-block interaction the "&#10;" encoding originally
    guarded against (see the historical comment this replaced in
    site/layouts/shortcodes/config-guidance.html) cannot recur here. The
    encoding is kept anyway so rendered output, and this port's structural
    diff against the previously committed docs/index.html, stay close to
    the prior renderer's.
    """
    return html.escape(code, quote=True).replace("\n", "&#10;")


# The CI/CD settings appendix (`{{< testing >}}`) used to keep all nine
# steps' check tables inline under `similar_tools.json`'s "testing.groups"
# array, which made a single-step edit touch one large, hard-to-review
# file (Issue #533). Each step now lives in its own
# `site/data/testing/<key>.json`; this tuple is the single source of the
# tab order the appendix renders in (steps 01-09, matching the "workflow"
# and "support" rows of `navigation.json`), since a directory listing is
# not guaranteed to sort that way and nothing else records the order.
_TESTING_STEP_ORDER: Final = (
    "work",
    "agents",
    "contract",
    "languages",
    "supply",
    "pr",
    "delivery",
    "governance",
    "template-upgrade",
)


def load_site_data(root: Path) -> SiteData:
    """Load every `site/data/*` source the render functions consume."""
    data_dir = root / "site/data"
    with (data_dir / "glossary.toml").open("rb") as stream:
        glossary = tomllib.load(stream)
    similar_tools = _load_json_file(data_dir / "similar_tools.json")
    similar_tools["testing"]["groups"] = _load_testing_groups(
        data_dir / "testing"
    )
    return SiteData(
        navigation=_load_json_file(data_dir / "navigation.json"),
        glossary=glossary,
        config_examples=_load_json_file(data_dir / "config_examples.json"),
        similar_tools=similar_tools,
        file_map=_load_json_file(data_dir / "file_map.json"),
        audit_trail=_load_json_file(data_dir / "audit_trail.json"),
        version=_load_json_file(root / "site/version.json"),
    )


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_testing_groups(testing_dir: Path) -> list[dict[str, Any]]:
    """Load the CI/CD settings appendix's per-step files, in tab order."""
    on_disk = {path.stem for path in testing_dir.glob("*.json")}
    expected = set(_TESTING_STEP_ORDER)
    if on_disk != expected:
        raise BuildError(
            "site/data/testing/*.json does not match _TESTING_STEP_ORDER: "
            f"missing {sorted(expected - on_disk)}, "
            f"unexpected {sorted(on_disk - expected)}"
        )
    groups = [
        _load_json_file(testing_dir / f"{key}.json")
        for key in _TESTING_STEP_ORDER
    ]
    found = {group["key"] for group in groups}
    if found != expected:
        raise BuildError(
            "site/data/testing/*.json 'key' fields do not match "
            f"_TESTING_STEP_ORDER: missing {sorted(expected - found)}, "
            f"unexpected {sorted(found - expected)}"
        )
    return groups


def _parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Split one content source into its TOML front matter and body."""
    parts = text.split("+++", 2)
    if len(parts) != 3 or parts[0].strip():
        raise BuildError("expected TOML front matter")
    return tomllib.loads(parts[1]), parts[2]


# --- Inline prose (the `{{< basic >}}` / non-legacy Markdown subset) -----


def _render_table(lines: list[str]) -> str:
    """Render a GFM-style pipe table (alignment markers are ignored)."""
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in lines
    ]
    header, *body_rows = [row for index, row in enumerate(rows) if index != 1]
    parts = ["<table>", "<thead>", "<tr>"]
    parts.extend(f"<th>{_inline_markdown(cell)}</th>" for cell in header)
    parts.append("</tr></thead><tbody>")
    for row in body_rows:
        parts.append("<tr>")
        parts.extend(f"<td>{_inline_markdown(cell)}</td>" for cell in row)
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


@dataclass
class _ListItem:
    tag: str
    html_text: str
    children: list[_ListItem]


def _parse_list(lines: list[str]) -> list[_ListItem]:
    """Parse indentation-nested `-`/`*`/`1.` list lines into a tree."""
    root: list[_ListItem] = []
    stack: list[tuple[int, list[_ListItem]]] = [(-1, root)]
    for line in lines:
        match = _LIST_ITEM.match(line)
        if match is None:  # pragma: no cover - guarded by the caller
            continue
        indent = len(match.group("indent"))
        tag = "ol" if match.group("marker")[0].isdigit() else "ul"
        while indent <= stack[-1][0]:
            stack.pop()
        item = _ListItem(tag, _inline_markdown(match.group("text").strip()), [])
        stack[-1][1].append(item)
        stack.append((indent, item.children))
    return root


def _render_list_items(items: list[_ListItem]) -> str:
    if not items:
        return ""
    tag = items[0].tag
    parts = [f"<{tag}>"]
    for item in items:
        parts.append(
            f"<li>{item.html_text}{_render_list_items(item.children)}</li>"
        )
    parts.append(f"</{tag}>")
    return "".join(parts)


def render_prose(text: str, *, state: RenderState) -> str:  # noqa: C901
    """Render the small Markdown subset used by prose content bodies.

    Supports paragraphs, `##`/`###` headings, nested `-`/`*`/`1.` lists,
    pipe tables, fenced code (including ` ```mermaid ` blocks), bold/code/
    link inline spans (via `_inline_markdown`), and raw HTML lines --
    Hugo's `unsafe = true` goldmark setting let authors write an `<aside>`
    directly in the Markdown, so a handful of content lines already rely on
    that passthrough.
    """
    lines = text.strip("\n").splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{_inline_markdown(' '.join(paragraph))}</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        if stripped.startswith("<"):
            flush_paragraph()
            blocks.append(stripped)
            index += 1
            continue
        heading = _HEADING.match(stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group("hashes"))
            title = heading.group("text").strip()
            anchor = _slug(title, state.used_ids)
            blocks.append(
                f'<h{level} id="{anchor}">{_inline_markdown(title)}</h{level}>'
            )
            index += 1
            continue
        fence = _FENCE.match(stripped)
        if fence:
            flush_paragraph()
            language = fence.group("lang")
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and lines[index].strip() != "```":
                code_lines.append(lines[index])
                index += 1
            index += 1  # skip the closing fence
            code = "\n".join(code_lines)
            if language == "mermaid":
                state.mermaid_used = True
                blocks.append(f'<pre class="mermaid">{html.escape(code)}</pre>')
            else:
                escaped = html.escape(code)
                blocks.append(
                    f'<pre class="command"><code>{escaped}</code></pre>'
                )
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            blocks.append(_render_table(table_lines))
            continue
        if _LIST_ITEM.match(line):
            flush_paragraph()
            list_lines: list[str] = []
            while index < len(lines) and _LIST_ITEM.match(lines[index]):
                list_lines.append(lines[index])
                index += 1
            blocks.append(_render_list_items(_parse_list(list_lines)))
            continue
        paragraph.append(stripped)
        index += 1

    flush_paragraph()
    return "\n".join(blocks)


# --- Mixed bodies (prose interleaved with detail/disclosure/config calls) -


def render_mixed(
    body: str, *, lang: str, data: SiteData, state: RenderState
) -> str:
    """Render a body that mixes prose with nested shortcode calls."""
    pieces: list[str] = []
    for node in _BLOCKS["iter_mixed"](body):
        if node.kind == "text":
            rendered = render_prose(node.text, state=state)
            if rendered:
                pieces.append(rendered)
        else:
            pieces.append(
                _render_shortcode(node, lang=lang, data=data, state=state)
            )
    return "\n".join(pieces)


def render_raw(
    body: str, *, lang: str, data: SiteData, state: RenderState
) -> str:
    """Render a `{{< legacy >}}` body: raw HTML, only shortcodes expanded."""
    pieces: list[str] = []
    for node in _BLOCKS["iter_mixed"](body):
        if node.kind == "text":
            stripped = node.text.strip()
            if stripped:
                pieces.append(stripped)
        else:
            pieces.append(
                _render_shortcode(node, lang=lang, data=data, state=state)
            )
    return "\n".join(pieces)


class _MixedNode(Protocol):
    """Structural shape of `decision_site_blocks.MixedNode`.

    That dataclass is loaded dynamically via `runpy` (see `_BLOCKS` above),
    so it has no static type this module can import directly; a Protocol
    lets `ty` still check attribute access against its known shape.
    """

    kind: str
    attrs: dict[str, str]
    body: str


def _render_shortcode(
    node: _MixedNode, *, lang: str, data: SiteData, state: RenderState
) -> str:
    if node.kind == "detail":
        return render_detail(
            node.attrs, node.body, lang=lang, data=data, state=state
        )
    if node.kind == "disclosure":
        return render_disclosure(
            node.attrs,
            node.body,
            lang=lang,
            data=data,
            state=state,
        )
    return _render_self_closing(node.kind, node.attrs, lang=lang, data=data)


def _render_self_closing(
    name: str, attrs: dict[str, str], *, lang: str, data: SiteData
) -> str:
    if name == "config-guidance":
        return render_config_guidance(attrs["track"], lang=lang, data=data)
    if name == "file-map":
        return render_file_map(lang=lang, data=data)
    if name == "similar-tools":
        return render_similar_tools(lang=lang, data=data)
    if name == "testing":
        return render_testing(lang=lang, data=data)
    if name == "audit-trail":
        return render_audit_trail(lang=lang, data=data)
    raise BuildError(
        f"unknown self-closing shortcode: {name}"
    )  # pragma: no cover


def render_detail(
    attrs: dict[str, str],
    body: str,
    *,
    lang: str,
    data: SiteData,
    state: RenderState,
) -> str:
    """Port `site/layouts/shortcodes/detail.html`."""
    title = attrs.get("title", "")
    heading = f"<h3>{_esc(title)}</h3>\n" if title else ""
    inner = render_mixed(body, lang=lang, data=data, state=state)
    key = _esc(attrs["key"])
    return (
        f'<aside class="technical-detail" data-content-key="{key}">'
        f"{heading}{inner}</aside>"
    )


def render_disclosure(
    attrs: dict[str, str],
    body: str,
    *,
    lang: str,
    data: SiteData,
    state: RenderState,
) -> str:
    """Port `site/layouts/shortcodes/disclosure.html`."""
    inner = render_mixed(body, lang=lang, data=data, state=state)
    key = _esc(attrs["key"])
    title = _esc(attrs.get("title", ""))
    return (
        f'<details class="package-disclosure" data-content-key="{key}">'
        f'<summary><span class="tech-name">{title}</span></summary>'
        f'<div class="package-health">{inner}</div></details>'
    )


# --- Config guidance -------------------------------------------------------


def render_config_guidance(track: str, *, lang: str, data: SiteData) -> str:
    """Port `site/layouts/shortcodes/config-guidance.html`.

    Issue #525 retired the old two-mode disclosure -- a fold-open
    `<details>` for "direct" tracks, a button plus modal-overlay-with-
    pager for the rest -- in favor of one static block. The
    simple/technical toggle (see detail-toggle.css's `.config-guidance`
    rule) already shows or hides this whole element directly in the
    content page; once it is visible, every item is already in view, so
    no further click-to-reveal layer is needed inside it. The `direct`
    field in site/data/config_examples.json is no longer read here (both
    prior styles collapsed into this one), but is left in the data file
    since it still documents which tracks were considered "fixed
    baseline" content when that distinction was authored.
    """
    tracks = data.config_examples["tracks"]
    if track not in tracks:
        raise BuildError(
            f"config-guidance shortcode: unknown track {track!r} "
            "(no entry in site/data/config_examples.json)"
        )
    spec = tracks[track]
    labels = data.config_examples["labels"][lang]
    items = spec["items"]

    entries = []
    for item in items:
        title = item["title"][lang]
        goal = item["goal"][lang]
        file_ = item["file"][lang]
        code = item["code"][lang]
        entries.append(
            '<article class="config-item">'
            f"<h4>{_esc(title)}</h4>"
            f"<p>{_esc(goal)}</p>"
            f'<p class="config-item-path">{_esc(labels["configFile"])}'
            f"<code>{_esc(file_)}</code></p>"
            f'<pre class="code">{_code_html(code)}</pre>'
            "</article>"
        )
    return (
        '<aside class="config-guidance" '
        f'data-content-key="config-{_esc(track)}">'
        f"<strong>{_esc(labels['heading'])}</strong>"
        f"<p>{_esc(labels['intro'])}</p>"
        f'<div class="config-items">{"".join(entries)}</div></aside>'
    )


# --- File map (Issue #534) -------------------------------------------


@dataclass
class _FileMapNode:
    """One segment of the file-map tree, keyed by its path segment.

    `children` keeps Python dict insertion order, so the tree renders in
    the same top-to-bottom order `site/data/file_map.json` lists its
    entries and each entry lists its `paths` -- no separate sort step.
    `entry` is the owning `site/data/file_map.json` entry (purpose,
    responsibility, optional `note`) when this exact node is one of that
    entry's literal paths; intermediate directories implied only by a
    longer sibling path (e.g. `.github/` itself) carry no entry.
    """

    name: str
    is_dir: bool = False
    children: dict[str, _FileMapNode] = field(default_factory=dict)
    entry: dict[str, Any] | None = None


def _insert_file_map_path(
    children: dict[str, _FileMapNode], path: str, entry: dict[str, Any]
) -> None:
    """Insert one entry's literal path into the tree being built, in place.

    A trailing "/" marks the whole path as a directory; any segment the
    path continues through is a directory regardless, so two entries that
    share a directory prefix (e.g. `.github/workflows/` and
    `.github/REVIEWERS`) merge into one shared branch instead of two.
    """
    ends_with_slash = path.endswith("/")
    segments = [segment for segment in path.split("/") if segment]
    cursor = children
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        node = cursor.setdefault(segment, _FileMapNode(name=segment))
        if not is_last or ends_with_slash:
            node.is_dir = True
        if is_last:
            node.entry = entry
        cursor = node.children


def _build_file_map_tree(
    entries: list[dict[str, Any]],
) -> dict[str, _FileMapNode]:
    root: dict[str, _FileMapNode] = {}
    for entry in entries:
        for path in entry["paths"]:
            _insert_file_map_path(root, path, entry)
    return root


def _render_file_map_annotation(
    entry: dict[str, Any], *, lang: str, responsibility_labels: dict[str, Any]
) -> tuple[str, str]:
    """Render one entry's note/tag (header line) and purpose (body line)."""
    note = entry.get("note")
    note_html = (
        f'<span class="file-map-note">{_esc(note[lang])}</span>' if note else ""
    )
    kind = entry["responsibility"]
    tag_label = _esc(responsibility_labels[kind][lang])
    tag_html = (
        f'<span class="file-map-tag file-map-tag-{_esc(kind)}">'
        f"{tag_label}</span>"
    )
    purpose_html = (
        f'<p class="file-map-purpose">{_esc(entry["purpose"][lang])}</p>'
    )
    return f"{note_html}{tag_html}", purpose_html


def _render_file_map_node(
    node: _FileMapNode, *, lang: str, responsibility_labels: dict[str, Any]
) -> str:
    """Port one `_FileMapNode` (and its subtree) to a `<li>` tree row."""
    icon_class = "is-dir" if node.is_dir else "is-file"
    display_name = _esc(node.name + ("/" if node.is_dir else ""))
    header = (
        f'<span class="file-map-icon {icon_class}" aria-hidden="true">'
        f"</span>"
        f'<code class="file-map-name">{display_name}</code>'
    )
    purpose_html = ""
    if node.entry is not None:
        annotation, purpose_html = _render_file_map_annotation(
            node.entry, lang=lang, responsibility_labels=responsibility_labels
        )
        header += annotation
    if node.children:
        children_html = "".join(
            _render_file_map_node(
                child, lang=lang, responsibility_labels=responsibility_labels
            )
            for child in node.children.values()
        )
        return (
            '<li class="file-map-node">'
            '<details class="file-map-branch" open>'
            f'<summary class="file-map-summary">'
            f'<span class="file-map-row">{header}</span></summary>'
            f"{purpose_html}"
            f"<ul>{children_html}</ul>"
            "</details></li>"
        )
    return (
        '<li class="file-map-node">'
        f'<div class="file-map-row">{header}</div>'
        f"{purpose_html}</li>"
    )


def render_file_map(*, lang: str, data: SiteData) -> str:
    """Render `{{< file-map >}}`: a file-explorer tree of the file map.

    Replaces the flat three-column path/purpose/responsibility table (see
    Issue #534) with a real nested tree built from each entry's literal
    `paths` in `site/data/file_map.json`; content (paths, purpose,
    responsibility) is unchanged from that table, only the presentation.
    """
    file_map = data.file_map
    labels = file_map["labels"][lang]
    responsibility_labels = file_map["responsibilityLabels"]
    tree = _build_file_map_tree(file_map["entries"])
    items = "".join(
        _render_file_map_node(
            node, lang=lang, responsibility_labels=responsibility_labels
        )
        for node in tree.values()
    )
    return (
        '<div class="file-map-window">'
        '<div class="file-map-toolbar">'
        '<span class="file-map-dots" aria-hidden="true">'
        "<i></i><i></i><i></i></span>"
        f'<code class="file-map-address">{_esc(labels["address"])}</code>'
        "</div>"
        f'<ul class="file-map-tree">{items}</ul>'
        "</div>"
    )


# --- Similar tools -----------------------------------------------------


def _break_before_paren(text: str) -> str:
    """Match Hugo's header-cell `<br>` insertion before a "(" / "（"."""
    return text.replace("（", "<br>（").replace(" (", "<br>(")


def _rank_tools(data: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = []
    for tool in data["tools"]:
        full = tool["coverage"]["full"]
        partial = tool["coverage"]["partial"]
        coverage_count = len(full) + len(partial)
        released = tool["released"]
        has_release_date = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", released))
        is_recent = has_release_date and released >= data["releaseCutoff"]
        is_primary = is_recent and coverage_count >= data["threshold"]
        stars = int(tool["stars"].replace(",", ""))
        is_ecosystem = (
            is_recent and not is_primary and stars >= data["starThreshold"]
        )
        if not (is_primary or is_ecosystem):
            continue
        rank = f"{99 - len(full):02d}-{99 - len(partial):02d}"
        sort_key = f"{rank}-{tool['name'].lower()}"
        ranked.append(
            {"tool": tool, "sort_key": sort_key, "primary": is_primary}
        )
    ranked.sort(key=lambda entry: entry["sort_key"])
    return ranked


def render_similar_tools(*, lang: str, data: SiteData) -> str:  # noqa: C901
    """Port `site/layouts/shortcodes/similar-tools.html`."""
    tools_data = data.similar_tools
    labels = tools_data["labels"][lang]
    ranked = _rank_tools(tools_data)

    tabs = [
        '<button id="similar-tools-tab-primary" type="button" role="tab" '
        'aria-selected="true" aria-controls="similar-tools-panel-primary" '
        f'data-similar-tools-tab="0"><small>{_esc(labels["primaryTabOverline"])}'
        f"</small>{_esc(labels['primaryTab'])}</button>"
    ]
    for group_index, group in enumerate(tools_data["featureGroups"]):
        group_labels = group["labels"][lang]
        tabs.append(
            f'<button id="similar-tools-tab-{group["key"]}" type="button" '
            'role="tab" aria-selected="false" '
            f'aria-controls="similar-tools-panel-{group["key"]}" '
            f'data-similar-tools-tab="{group_index + 1}">'
            f"<small>{_esc(group_labels['overline'])}</small>"
            f"{_esc(group_labels['title'])}</button>"
        )

    rows = []
    for entry in ranked:
        if not entry["primary"]:
            continue
        tool = entry["tool"]
        difference = "".join(
            f"<li>{_esc(item)}</li>" for item in tool["difference"][lang]
        )
        full_tags = "".join(
            f'<span class="coverage-tag full" title="{_esc(code)}: '
            f'{_esc(labels["full"])}">{_esc(code)}</span>'
            for code in sorted(tool["coverage"]["full"])
        )
        partial_tags = "".join(
            f'<span class="coverage-tag partial" title="{_esc(code)}: '
            f'{_esc(labels["partial"])}">{_esc(code)}</span>'
            for code in sorted(tool["coverage"]["partial"])
        )
        rows.append(
            "<tr>"
            f'<th scope="row"><a href="{_esc(tool["url"])}" target="_blank" '
            f'rel="noreferrer">{_esc(tool["name"])}</a></th>'
            f"<td>{_esc(tool['version'])}<br>({_esc(tool['released'])})</td>"
            f"<td>{_esc(tool['stars'])}</td>"
            f"<td>{_esc(tool['position'][lang])}</td>"
            f"<td><ul>{difference}</ul></td>"
            f'<td><div class="coverage-tags">{full_tags}'
            f"{partial_tags}</div></td>"
            "</tr>"
        )

    features_by_key = {
        feature["key"]: feature for feature in tools_data["features"]
    }
    group_panels = []
    for group in tools_data["featureGroups"]:
        group_labels = group["labels"][lang]
        body_rows = []
        for feature_key in group["features"]:
            feature = features_by_key.get(feature_key)
            if feature is None:
                continue
            columns = []
            for want_primary in (True, False):
                items = []
                for entry in ranked:
                    if entry["primary"] != want_primary:
                        continue
                    tool = entry["tool"]
                    for comparison in tool["comparisons"]:
                        if comparison["key"] != feature_key:
                            continue
                        meta = (
                            ""
                            if want_primary
                            else '<span class="tool-meta">'
                            f"<span>{_esc(tool['version'])} "
                            f"({_esc(tool['released'])})</span>"
                            f"<span>★ {_esc(tool['stars'])}</span></span>"
                        )
                        items.append(
                            f"<li><strong>{_esc(tool['name'])}{meta}</strong>"
                            '<span class="tool-comparison-detail">'
                            f'<a href="{_esc(comparison["docs"])}" '
                            f'target="_blank" rel="noreferrer">'
                            f"{_esc(comparison['feature'])}</a>："
                            f"{_esc(comparison['description'][lang])}</span></li>"
                        )
                columns.append(f"<td><ul>{''.join(items)}</ul></td>")
            body_rows.append(
                '<tr><th scope="row">'
                f"<strong>{_esc(feature['title'][lang])}</strong>"
                f"<span>{_esc(feature['description'][lang])}<br><br>"
                f"<b>{_esc(labels['csarc'])}</b>{_esc(feature['csarc'][lang])}"
                f"</span></th>{''.join(columns)}</tr>"
            )
        group_panels.append(
            f'<div id="similar-tools-panel-{group["key"]}" '
            'class="similar-tools-panel" role="tabpanel" '
            f'aria-labelledby="similar-tools-tab-{group["key"]}" '
            "data-similar-tools-panel hidden>"
            '<div class="similar-tools-legend">'
            f'<span class="reference">{_esc(group_labels["legend"])}</span>'
            f'<span class="capture-date">{_esc(labels["captureDate"])}｜'
            f"{_esc(tools_data['comparisonDate'])}</span></div>"
            '<div class="similar-tools-table-wrap" tabindex="0" role="region" '
            f'aria-label="{_esc(group_labels["title"])}">'
            '<table class="similar-tools-matrix '
            'similar-tools-philosophy-matrix">'
            f'<thead><tr><th scope="col">{_esc(labels["feature"])}</th>'
            f'<th scope="col">{_esc(labels["primaryTools"])}</th>'
            f'<th scope="col">{_esc(labels["otherTools"])}</th></tr></thead>'
            f"<tbody>{''.join(body_rows)}</tbody></table></div></div>"
        )

    return (
        '<div class="legacy-content similar-tools-content">'
        '<div class="similar-tools-tabs" role="tablist" '
        f'aria-label="{_esc(labels["title"])}" data-audience="maintainer">'
        f"{''.join(tabs)}</div>"
        '<div id="similar-tools-panel-primary" class="similar-tools-panel" '
        'role="tabpanel" aria-labelledby="similar-tools-tab-primary" '
        "data-similar-tools-panel>"
        '<div class="similar-tools-legend">'
        f'<span class="competitor">{_esc(labels["primaryLegend"])}</span>'
        '<span class="coverage-key">'
        f'<i class="coverage-tag full">{_esc(labels["full"])}</i>　'
        f'<i class="coverage-tag partial">{_esc(labels["partial"])}</i></span>'
        f'<span class="capture-date">{_esc(labels["captureDate"])}｜'
        f"{_esc(tools_data['comparisonDate'])}</span></div>"
        '<div class="similar-tools-table-wrap" tabindex="0" role="region" '
        f'aria-label="{_esc(labels["primaryTab"])}">'
        '<table class="similar-tools-matrix similar-tools-primary-matrix">'
        f'<thead><tr><th scope="col">{_esc(labels["package"])}</th>'
        f'<th scope="col">{_break_before_paren(labels["version"])}</th>'
        f'<th scope="col">{_break_before_paren(labels["stars"])}</th>'
        f'<th scope="col">{_esc(labels["position"])}</th>'
        f'<th scope="col">{_esc(labels["difference"])}</th>'
        f'<th scope="col">{_esc(labels["coverage"])}</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        '<p class="similar-tools-note">'
        f"<strong>{_esc(labels['criterionLabel'])}</strong>"
        f"{_esc(labels['criterion'])}</p></div>"
        f"{''.join(group_panels)}</div>"
    )


# --- CI/CD settings appendix ---------------------------------------------


def render_testing(*, lang: str, data: SiteData) -> str:  # noqa: C901
    """Port `site/layouts/shortcodes/testing.html`."""
    testing = data.similar_tools["testing"]
    labels = testing["labels"][lang]
    duration = testing["duration"]
    duration_labels = duration["labels"][lang]

    tabs = [
        '<button id="testing-tab-duration" type="button" role="tab" '
        'aria-selected="true" aria-controls="testing-panel-duration" '
        f'data-similar-tools-tab="0"><small>{_esc(duration_labels["overline"])}'
        f"</small>{_esc(duration_labels['title'])}</button>"
    ]
    for group_index, group in enumerate(testing["groups"]):
        group_labels = group["labels"][lang]
        tabs.append(
            f'<button id="testing-tab-{group["key"]}" type="button" '
            'role="tab" aria-selected="false" '
            f'aria-controls="testing-panel-{group["key"]}" '
            f'data-similar-tools-tab="{group_index + 1}">'
            f"<small>{_esc(labels['step'])} {_esc(group['code'])}</small>"
            f"{_esc(group_labels['title'])}</button>"
        )

    duration_rows = []
    for row in duration["rows"]:
        cells = []
        for scope in (row["shared"], row["templateOnly"]):
            items = "".join(
                f"<li><strong>{_esc(item['label'][lang])}：</strong>"
                f"{_esc(item['value'][lang])}</li>"
                for item in scope["items"]
            )
            cells.append(
                f'<td><ul class="testing-duration-list">{items}</ul>'
                f'<p class="testing-duration-total">'
                f"<strong>{_esc(duration_labels['total'])}</strong>"
                f"{_esc(scope['total'][lang])}</p></td>"
            )
        duration_rows.append(
            f'<tr><th scope="row"><strong>{_esc(row["stage"][lang])}</strong>'
            f"</th>{''.join(cells)}</tr>"
        )

    def pending_tag(entry: dict[str, Any], default_issue: int) -> str:
        if not entry.get("pending"):
            return ""
        issue = entry.get("issue", default_issue)
        pending_label = _esc(labels["pending"])
        return (
            ' <a class="testing-pending-tag" '
            'href="https://github.com/Innoguard-Cyber-Arch/'
            f'csarc-repo-template/issues/{issue}" target="_blank" '
            f'rel="noreferrer">{pending_label} #{issue}</a>'
        )

    def render_files(files: list[dict[str, Any]]) -> str:
        entries = "".join(
            f"<li><code>{_esc(entry['path'])}</code>"
            f"{pending_tag(entry, 382)}</li>"
            for entry in files
        )
        tests_label = _esc(labels["tests"])
        return (
            f'<div class="testing-kind"><b>{tests_label}</b>'
            f"<ul>{entries}</ul></div>"
        )

    def render_automation(entries_data: list[dict[str, Any]]) -> str:
        entries = []
        for entry in entries_data:
            trigger = _esc(entry["trigger"][lang])
            timeout_label = _esc(labels["timeout"])
            entries.append(
                f"<li><code>{_esc(entry['path'])}</code>／"
                f"<code>{_esc(entry['job'])}</code>{pending_tag(entry, 385)}"
                f"<span>{_esc(labels['trigger'])}："
                f"{trigger} · {timeout_label}："
                f"{_esc(entry['timeout'])}</span></li>"
            )
        automation_label = _esc(labels["automation"])
        return (
            f'<div class="testing-kind"><b>{automation_label}</b>'
            f"<ul>{''.join(entries)}</ul></div>"
        )

    def render_stage(scope: dict[str, Any], stage_key: str, group: dict) -> str:
        stage = scope.get(stage_key)
        if not stage:
            return ""
        if "stageLabels" in group:
            stage_label = group["stageLabels"][lang][stage_key]
        else:
            stage_label = labels[
                "milestone" if stage_key == "milestone" else "release"
            ]
        parts = [f"<li><strong>{_esc(stage_label)}</strong>"]
        files = stage.get("files")
        if files:
            parts.append(render_files(files))
        automation = stage.get("automation")
        if automation:
            parts.append(render_automation(automation))
        automation_note = stage.get("automationNote")
        if automation_note:
            parts.append(
                f'<div class="testing-kind"><b>{_esc(labels["automation"])}</b>'
                f"<span>{_esc(automation_note[lang])}</span></div>"
            )
        note = stage.get("note")
        if note:
            parts.append(f"<span>{_esc(note[lang])}</span>")
        parts.append("</li>")
        return "".join(parts)

    group_panels = []
    for group in testing["groups"]:
        group_labels = group["labels"][lang]
        body_rows = []
        for row in group["rows"]:
            purpose = row["purpose"][lang]
            cells = []
            # Not every row has both scopes (e.g. a repo-template-only PR
            # check with no shared counterpart); Hugo's `where`/index on a
            # missing map key is a silent no-op, so default to {}.
            for scope in (row.get("shared", {}), row.get("templateOnly", {})):
                stages = "".join(
                    render_stage(scope, key, group)
                    for key in ("milestone", "release")
                )
                cells.append(
                    f'<td><ul class="testing-stage-list">{stages}</ul></td>'
                )
            body_rows.append(
                '<tr><th scope="row">'
                f"<strong>{_esc(purpose['title'])}</strong>"
                f"<span>{_esc(purpose['description'])}</span>"
                f"</th>{''.join(cells)}</tr>"
            )
        group_panels.append(
            f'<div id="testing-panel-{group["key"]}" '
            'class="similar-tools-panel" role="tabpanel" '
            f'aria-labelledby="testing-tab-{group["key"]}" '
            "data-similar-tools-panel hidden>"
            '<div class="similar-tools-testing-intro">'
            f"<strong>{_esc(group_labels['heading'])}</strong>"
            f"<span>{_esc(group_labels['scope'])}</span></div>"
            '<div class="similar-tools-table-wrap" tabindex="0" role="region" '
            f'aria-label="{_esc(group_labels["heading"])}">'
            '<table class="similar-tools-matrix similar-tools-testing-matrix">'
            f'<thead><tr><th scope="col">{_esc(labels["purpose"])}</th>'
            f'<th scope="col">{_esc(labels["shared"])}</th>'
            f'<th scope="col">{_esc(labels["templateOnly"])}</th></tr></thead>'
            f"<tbody>{''.join(body_rows)}</tbody></table></div></div>"
        )

    return (
        '<div class="legacy-content similar-tools-content testing-content">'
        '<div class="similar-tools-tabs" role="tablist" '
        f'aria-label="{_esc(labels["title"])}">{"".join(tabs)}</div>'
        '<div id="testing-panel-duration" class="similar-tools-panel" '
        'role="tabpanel" aria-labelledby="testing-tab-duration" '
        "data-similar-tools-panel>"
        '<div class="similar-tools-testing-intro">'
        f"<strong>{_esc(duration_labels['heading'])}</strong>"
        f"<span>{_esc(duration_labels['scope'])}</span>"
        f"<p>{_esc(duration_labels['runnerNote'])}</p>"
        f"<p>{_esc(duration_labels['archiveNote'])}</p></div>"
        '<div class="similar-tools-table-wrap" tabindex="0" role="region" '
        f'aria-label="{_esc(duration_labels["heading"])}">'
        '<table class="similar-tools-matrix similar-tools-testing-matrix '
        'testing-duration-matrix">'
        f'<thead><tr><th scope="col">{_esc(duration_labels["stage"])}</th>'
        f'<th scope="col">{_esc(duration_labels["shared"])}</th>'
        f'<th scope="col">{_esc(duration_labels["templateOnly"])}</th>'
        "</tr></thead>"
        f"<tbody>{''.join(duration_rows)}</tbody></table></div></div>"
        f"{''.join(group_panels)}</div>"
    )


# --- Governance audit trail (Issue #559) ----------------------------------

_AUDIT_TRAIL_ISSUES: Final = (("535", "535"), ("559", "559"))


def render_audit_trail(*, lang: str, data: SiteData) -> str:
    """Render `{{< audit-trail >}}`: present the governance audit trail.

    `scripts/generate_audit_trail.py` (Issue #535) queries live GitHub
    state and writes two Markdown tables. This decision site is the
    byte-reproducible, `file://`-openable static bundle
    `docs/adr/portable-decision-site.md` requires, so it can never embed
    that live query's result as if it were current -- Issue #559 decided
    this shortcode instead documents each output file's *structure*
    (paths and columns, sourced once here so both languages stay in sync
    with the generator's real header text) plus the exact regeneration
    command, and explicitly states that -- mirroring the
    `scripts/check-governance-drift` precedent -- no schedule or
    on-merge job generates and commits a snapshot either. The content
    itself is hand-curated, not live-fetched, the same way
    `site/data/config_examples.json` backs `render_config_guidance`.
    """
    audit = data.audit_trail
    labels = audit["labels"][lang]
    rows = "".join(
        "<tr><td><code>{path}</code></td><td>{description}</td>"
        "<td>{columns}</td></tr>".format(
            path=_esc(entry["path"]),
            description=_inline_markdown(entry["description"][lang]),
            columns=" ".join(
                f"<code>{_esc(column)}</code>" for column in entry["columns"]
            ),
        )
        for entry in audit["files"]
    )
    evidence_links = " ".join(
        f'<a href="https://github.com/Innoguard-Cyber-Arch/'
        f'csarc-repo-template/issues/{number}" target="_blank" '
        f'rel="noreferrer">#{label}</a>'
        for number, label in _AUDIT_TRAIL_ISSUES
    )
    return (
        '<div class="legacy-content audit-trail-content">'
        f"<p>{_inline_markdown(labels['intro'])}</p>"
        f'<table class="decision-register" '
        f'aria-label="{_esc(labels["tableAriaLabel"])}">'
        f"<thead><tr><th>{_esc(labels['fileColumn'])}</th>"
        f"<th>{_esc(labels['descriptionColumn'])}</th>"
        f"<th>{_esc(labels['columnsColumn'])}</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        '<aside class="selection-note">'
        f"<strong>{_esc(labels['freshnessLabel'])}</strong>"
        f"<span>{_inline_markdown(labels['freshnessNote'])}</span></aside>"
        f'<p class="bridge-reference reference">'
        f"{_esc(labels['commandIntro'])} "
        f"<code>{_esc(audit['command'])}</code> "
        f"{_inline_markdown(labels['commandOutro'])}</p>"
        f'<p class="bridge-reference reference">'
        f"{_esc(labels['evidenceIntro'])} {evidence_links}</p>"
        "</div>"
    )


# --- Journey rail and slide shell -----------------------------------------


def render_journey_rail(
    nav: dict[str, Any], *, lang: str, active_key: str
) -> str:
    """Port `site/layouts/partials/journey-rail.html`."""
    labels = nav["labels"][lang]

    def group_items(name: str) -> list[dict[str, Any]]:
        return [item for item in nav["items"] if item["group"] == name]

    def render_items(items: list[dict[str, Any]], *, with_code: bool) -> str:
        parts = []
        for item in items:
            classes = f"journey-item {item['participation']}"
            is_active = item["key"] == active_key
            if is_active:
                classes += " active"
            aria = ' aria-current="step"' if is_active else ""
            audience = item.get("audience")
            audience_attr = (
                f' data-audience="{_esc(audience)}"' if audience else ""
            )
            item_code = _esc(item.get("code", ""))
            code = (
                f'<span class="journey-code">{item_code}</span>'
                if with_code
                else ""
            )
            label = _esc(item["labels"][lang])
            link = f'<a href="#{item["key"]}">{code}<span>{label}</span></a>'
            parts.append(
                f'    <li class="{classes}"{audience_attr}{aria}>\n'
                f"      {link}\n    </li>"
            )
        return "\n".join(parts)

    appendices = []
    for item in nav["appendices"]:
        classes = f"journey-bookend appendix {item['participation']}"
        if item["key"] == active_key:
            classes += " active-selection"
        audience = item.get("audience")
        audience_attr = f' data-audience="{_esc(audience)}"' if audience else ""
        current = ' aria-current="page"' if item["key"] == active_key else ""
        label = _esc(item["labels"][lang])
        appendices.append(
            f'  <a class="{classes}"{audience_attr} href="#{item["key"]}"'
            f"{current}>{label}</a>"
        )

    aria_label = _esc(labels["ariaLabel"])
    return (
        f'<aside class="journey-rail" aria-label="{aria_label}">\n'
        f"  <h3>{_esc(labels['use'])}</h3>\n"
        '  <ol class="journey-use">\n'
        f"{render_items(group_items('use'), with_code=False)}\n  </ol>\n"
        f"  <h3>{_esc(labels['workflow'])}</h3>\n"
        '  <ol class="journey-main">\n'
        f"{render_items(group_items('workflow'), with_code=True)}\n  </ol>\n"
        f"  <h3>{_esc(labels['support'])}</h3>\n"
        '  <ol class="journey-support">\n'
        f"{render_items(group_items('support'), with_code=True)}\n  </ol>\n"
        f"{chr(10).join(appendices)}\n"
        f'  <div class="journey-legend" aria-label="{_esc(labels["legend"])}">'
        "\n"
        f'    <span><i class="human" aria-hidden="true"></i>'
        f"{_esc(labels['human'])}</span>\n"
        f'    <span><i class="automated" aria-hidden="true"></i>'
        f"{_esc(labels['automated'])}</span>\n"
        '    <span data-audience="maintainer">'
        f'<i class="maintainer" aria-hidden="true"></i>'
        f"{_esc(labels['maintainer'])}</span>\n"
        "  </div>\n</aside>"
    )


def _render_header(attrs: dict[str, str], *, legacy: bool) -> str:
    class_attr = ' class="basic-header"' if legacy else ""
    lines = [f"<header{class_attr}>"]
    eyebrow = attrs.get("eyebrow")
    if eyebrow:
        lines.append(
            f'  <span class="selection-sequence">{_esc(eyebrow)}</span>'
        )
    lines.append(f"  <h2>{_esc(attrs['title'])}</h2>")
    subtitle = attrs.get("subtitle")
    if subtitle:
        lines.append(f'  <p class="subtitle">{_esc(subtitle)}</p>')
    lines.append("</header>")
    return "\n".join(lines)


def _render_legacy_body(
    body: str, *, lang: str, data: SiteData, state: RenderState
) -> str:
    """Render a `legacy="true"` slide's Inner (raw HTML, safeHTML in Hugo)."""
    bare = _BARE_SELF_CLOSING.match(body.strip())
    if bare:
        return _render_self_closing(
            bare.group("name"), {}, lang=lang, data=data
        )

    legacy = _BLOCKS["find_container"](body, "legacy")
    basic = _BLOCKS["find_container"](body, "basic")
    if legacy is None or basic is None:
        raise BuildError(
            "legacy slide body is missing its {{< legacy >}}/{{< basic >}} pair"
        )
    _, legacy_inner, legacy_match = legacy
    _, basic_inner, _basic_match = basic
    prefix = body[: legacy_match.start()].strip()

    pieces = []
    if prefix:
        pieces.append(prefix)
    pieces.append(
        '<div class="legacy-content">'
        f"{render_raw(legacy_inner, lang=lang, data=data, state=state)}</div>"
    )
    pieces.append(
        '<div class="markdown-body basic-summary">'
        f"{render_mixed(basic_inner, lang=lang, data=data, state=state)}</div>"
    )
    return "\n".join(pieces)


def render_slide(
    attrs: dict[str, str],
    body: str,
    *,
    lang: str,
    data: SiteData,
    state: RenderState,
    ordinal: int,
) -> str:
    """Port `site/layouts/shortcodes/slide.html`."""
    key = attrs["key"]
    legacy = attrs.get("legacy") == "true"

    classes = ["slide", "markdown-slide"]
    if ordinal == 0:
        classes.append("active")
    extra_class = attrs.get("class")
    if extra_class:
        classes.append(extra_class)

    optional_attrs = ""
    for attr_name in ("track", "audience", "parity"):
        value = attrs.get(attr_name)
        if value:
            optional_attrs += f' data-{attr_name}="{_esc(value)}"'

    rail = render_journey_rail(data.navigation, lang=lang, active_key=key)
    header = _render_header(attrs, legacy=legacy)
    if legacy:
        content = _render_legacy_body(body, lang=lang, data=data, state=state)
        body_html = f"{header}\n{content}"
    else:
        content = render_mixed(body, lang=lang, data=data, state=state)
        body_html = f'{header}\n<div class="markdown-body">{content}</div>'

    return (
        f'<section class="{" ".join(classes)}" id="{key}" '
        f'data-content-key="{key}"{optional_attrs} '
        f'aria-label="{_esc(attrs["title"])}">\n'
        f"  {rail}\n\n{body_html}\n</section>"
    )


# --- Page shell (site/layouts/home.presentation.html) --------------------

_DETAIL_LEVEL_SCRIPT: Final = """\
  <script>
    try {
      const savedDetailLevel = localStorage.getItem("csarc-detail-level");
      if (savedDetailLevel === "technical")
        document.documentElement.dataset.detailLevel = savedDetailLevel;
    } catch {}
  </script>"""

_REORDER_SCRIPT: Final = """\
  <script>
    (() => {
      const pr = document.querySelector('[data-track="pr"]');
      const supply = document.querySelector('[data-track="supply"]');
      const testing = document.querySelector("#testing");
      const bridge = document.querySelector("#bridge");
      if (pr && supply) supply.before(pr);
      if (testing && bridge) testing.after(bridge);
    })();
  </script>"""


def render_page(
    markdown_text: str,
    *,
    lang: str,
    data: SiteData,
    root: Path | None = None,
) -> str:
    """Render one language's complete pre-bundle HTML source.

    When `root` is given, a slide whose `key` is in `_EXTERNAL_SLIDE_SOURCES`
    has its inline body replaced with Markdown read from a docs/ file, so
    that page's single source of truth lives in one plain Markdown file
    instead of being duplicated into this shortcode source. `root` is
    optional (and the lookup only fires for a key that is actually present)
    so callers that render a synthetic fixture with no docs/ directory,
    such as unit tests, are unaffected.
    """
    substituted = _substitute_version_tokens(markdown_text, data)
    metadata, body = _parse_front_matter(substituted)
    title = metadata["title"]
    controls = metadata["controls"]

    state = RenderState()
    slides = [
        render_slide(
            attrs,
            (
                _external_slide_body(
                    root, _EXTERNAL_SLIDE_SOURCES[attrs["key"]], lang
                )
                if root is not None and attrs["key"] in _EXTERNAL_SLIDE_SOURCES
                else slide_body
            ),
            lang=lang,
            data=data,
            state=state,
            ordinal=ordinal,
        )
        for ordinal, (attrs, slide_body, _match) in enumerate(
            _BLOCKS["iter_containers"](body, "slide")
        )
    ]
    content = "\n".join(slides)

    language_links = "\n".join(
        f'      <a href="{_LANGUAGES[code]["output"]}" '
        f'lang="{_LANGUAGES[code]["code"]}"'
        + (' aria-current="page"' if code == lang else "")
        + f">{_esc(_LANGUAGES[code]['name'])}</a>"
        for code in _LANGUAGE_ORDER
    )

    mermaid_block = ""
    if state.mermaid_used:
        mermaid_src = f"{_ASSET_PREFIX}site/static/vendor/mermaid.min.js"
        mermaid_block = (
            f'\n  <script src="{mermaid_src}"></script>\n'
            "  <script>\n"
            "    mermaid.initialize({ startOnLoad: true, "
            'securityLevel: "strict" });\n'
            "  </script>"
        )

    language_code = _LANGUAGES[lang]["code"]
    return f"""<!doctype html>
<html lang="{language_code}" data-detail-level="simple">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <link rel="icon" href="data:,">
  <title>{_esc(title)}</title>
{_DETAIL_LEVEL_SCRIPT}
  <link rel="stylesheet" href="{_ASSET_PREFIX}site/static/styles.css">
  <link rel="stylesheet" href="{_ASSET_PREFIX}site/static/detail-toggle.css">
  <link rel="stylesheet" href="{_ASSET_PREFIX}site/theme.css">
</head>
<body>
  <div class="reading-controls">
    <nav class="language-control" aria-label="{_esc(controls["language"])}">
{language_links}
    </nav>
    <div class="detail-level-control" role="group" \
aria-label="{_esc(controls["detail"])}" hidden>
      <button type="button" data-detail-level="simple" \
aria-pressed="true">{_esc(controls["simple"])}</button>
      <button type="button" data-detail-level="technical" \
aria-pressed="false">{_esc(controls["technical"])}</button>
    </div>
  </div>
  <main class="deck" aria-live="polite">{content}</main>
  <nav class="controls" aria-label="{_esc(controls["slides"])}" hidden>
    <button id="previous" type="button" \
aria-label="{_esc(controls["previous"])}">←</button>
    <span class="counter" id="counter">1 / 1</span>
    <button id="next" type="button" \
aria-label="{_esc(controls["next"])}">→</button>
  </nav>
  <nav class="view-controls" aria-label="{_esc(controls["zoom"])}" hidden>
    <button id="zoom-out" type="button" \
aria-label="{_esc(controls["zoom_out"])}">−</button>
    <button id="zoom-reset" type="button" \
aria-label="{_esc(controls["zoom_reset"])}">{_esc(controls["fit"])}</button>
    <span class="zoom-level" id="zoom-level" aria-live="polite">100%</span>
    <button id="zoom-in" type="button" \
aria-label="{_esc(controls["zoom_in"])}">＋</button>
  </nav>
  <div class="progress" aria-hidden="true" hidden><span id="bar"></span></div>
{_REORDER_SCRIPT}
  <script src="{_ASSET_PREFIX}site/static/deck.js"></script>
  <script src="{_ASSET_PREFIX}site/static/legacy-components.js"></script>
  <script src="{_ASSET_PREFIX}site/static/detail-toggle.js"></script>\
{mermaid_block}
</body>
</html>
"""


# --- llms.txt (site/layouts/home.llms.txt) --------------------------------


def render_llms_txt(data: SiteData) -> str:
    """Port `site/layouts/home.llms.txt`.

    Built by direct string concatenation, mirroring the Go template's own
    token-by-token output, rather than a line list -- each group's blank
    line before its heading and the blank line after its last term are two
    separate newline contributions in the source template that only merge
    into one blank line once concatenated, which a naive one-blank-per-
    boundary line list would double up on.
    """
    glossary = data.glossary
    text = (
        f"# {glossary['title']}\n\n"
        f"> {glossary['summary_en']} / {glossary['summary_zh_tw']}\n"
    )
    for group in glossary.get("groups", []):
        text += f"\n## {group['title_en']} / {group['title_zh_tw']}\n"
        for term in group["terms"]:
            text += (
                f"\n- [{term['term_en']} / {term['term_zh_tw']}]"
                f"({glossary['source_base']}{term['path']}): "
                f"{term['summary_en']} / {term['summary_zh_tw']}"
            )
        text += "\n"
    return text


# --- CLI --------------------------------------------------------------


# Slide keys whose body is authored once in docs/<stem>{.<lang>}.md instead
# of being duplicated into site/content/_index.{lang}.md; the primary
# language (_LANGUAGE_ORDER[0]) reads the bare stem, other languages read
# the stem with their language code appended, matching how a downstream
# repo's own README.md / README.<lang>.md pairs will resolve.
_EXTERNAL_SLIDE_SOURCES: Final = {"about": "about"}


def _external_slide_body(root: Path, stem: str, lang: str) -> str:
    suffix = "" if lang == _LANGUAGE_ORDER[0] else f".{lang}"
    path = root / "docs" / f"{stem}{suffix}.md"
    text = path.read_text(encoding="utf-8")
    # The slide shell already renders attrs["title"] as an <h2>; drop the
    # docs/ file's own leading "# Title" line (plus the blank line after
    # it) so the title is not shown twice.
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        if lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines)


def build(root: Path, output_dir: Path) -> dict[str, Path]:
    """Render both languages and the shared llms.txt into `output_dir`."""
    data = load_site_data(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    for lang in _LANGUAGE_ORDER:
        source = root / "site/content" / f"_index.{lang}.md"
        html_text = render_page(
            source.read_text(encoding="utf-8"),
            lang=lang,
            data=data,
            root=root,
        )
        output_path = output_dir / _LANGUAGES[lang]["output"]
        output_path.write_text(html_text, encoding="utf-8")
        outputs[lang] = output_path
    llms_path = output_dir / "llms.txt"
    llms_path.write_text(render_llms_txt(data), encoding="utf-8")
    outputs["llms"] = llms_path
    return outputs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir", type=Path, default=Path("dist/decision-site")
    )
    return parser


def main() -> int:
    """Write the two pre-bundle HTML sources and the shared llms.txt."""
    args = _parser().parse_args()
    root = args.root.resolve()
    try:
        outputs = build(root, root / args.output_dir)
    except (
        BuildError,
        OSError,
        UnicodeError,
        tomllib.TOMLDecodeError,
    ) as error:
        sys.stderr.write(f"decision site build failed: {error}\n")
        return 1
    for name, path in outputs.items():
        sys.stdout.write(f"{name}: {path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
