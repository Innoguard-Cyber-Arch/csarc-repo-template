"""Build the portable documentation site as one self-contained HTML file."""

from __future__ import annotations

import argparse
import base64
import html as html_module
import re
import runpy
import sys
from pathlib import Path
from typing import Final
from urllib.parse import unquote, urlsplit

SUPPORTED_CONTENT_SCHEMA: Final = 1
MEDIA_TYPES: Final = {
    ".avif": "image/avif",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".otf": "font/otf",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ttf": "font/ttf",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}

_STYLESHEET = re.compile(
    r"<link\b(?=[^>]*\brel=[\"']stylesheet[\"'])"
    r"(?=[^>]*\bhref=[\"'](?P<url>[^\"']+)[\"'])[^>]*>",
    re.IGNORECASE,
)
_SCRIPT = re.compile(
    r"<script\b(?=[^>]*\bsrc=[\"'](?P<url>[^\"']+)[\"'])"
    r"[^>]*>\s*</script>",
    re.IGNORECASE,
)
_STYLE = re.compile(
    r"(<style\b[^>]*>)(.*?)(</style>)", re.DOTALL | re.IGNORECASE
)
_MEDIA_ATTRIBUTE = re.compile(
    r"(?P<prefix><(?:audio|img|input|source|video)\b[^>]*"
    r"\b(?:poster|src)=[\"'])(?P<url>[^\"']+)(?P<suffix>[\"'][^>]*>)",
    re.IGNORECASE,
)
_ICON = re.compile(
    r"(?P<prefix><link\b(?=[^>]*\brel=[\"'](?:icon|apple-touch-icon)"
    r"[\"'])[^>]*\bhref=[\"'])(?P<url>[^\"']+)(?P<suffix>[\"'][^>]*>)",
    re.IGNORECASE,
)
_CSS_URL = re.compile(
    r"url\(\s*(?P<quote>[\"']?)(?P<url>[^\"')]+)(?P=quote)\s*\)",
    re.IGNORECASE,
)
_CSS_IMPORT = re.compile(r"@import\b", re.IGNORECASE)
_SCHEMA_VERSION = re.compile(r"\bschemaVersion\s*:\s*(?P<version>\d+)\b")
_CONFIG_TOKEN = re.compile(r"\[\[(?P<key>[a-z][a-z0-9_]*)\]\]")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_MARKDOWN_NAV = "<!-- CSARC_SITE_NAV -->"
_MARKDOWN_CONTENT = "<!-- CSARC_SITE_CONTENT -->"
_MARKDOWN_TITLE = "<!-- CSARC_SITE_TITLE -->"


class BundleError(ValueError):
    """Report a source that cannot satisfy the portable bundle contract."""


def _load_config(root: Path) -> dict[str, object]:
    """Read the repository's existing CSARC configuration."""
    config_reader = root / "scripts/csarc_config.py"
    config_path = root / ".csarc/config.yml"
    try:
        load_config = runpy.run_path(str(config_reader))["load_config"]
        config = load_config(config_path)
    except (KeyError, OSError, SyntaxError, ValueError) as error:
        raise BundleError(f"Cannot read {config_path}: {error}") from error
    if not isinstance(config, dict):
        raise BundleError(f"Invalid configuration in {config_path}")
    return config


def _config_text(value: object) -> str:
    """Format one flat CSARC setting for human-readable content."""
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    if isinstance(value, bool):
        return "是" if value else "否"
    return "" if value is None else str(value)


def _substitute_config(markdown: str, config: dict[str, object]) -> str:
    """Resolve explicit Markdown tokens from the single config source."""

    def replace(match: re.Match[str]) -> str:
        key = match.group("key")
        if key not in config:
            raise BundleError(f"Unknown site content setting: {key}")
        return _config_text(config[key])

    return _CONFIG_TOKEN.sub(replace, markdown)


def _slug(text: str, used: set[str]) -> str:
    """Create a stable local anchor for a Markdown heading."""
    value = re.sub(r"[^\w\u3400-\u9fff-]+", "-", text.lower()).strip("-")
    value = value or "section"
    candidate = value
    suffix = 2
    while candidate in used:
        candidate = f"{value}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _inline_markdown(text: str) -> str:
    """Render the small inline subset used by project-owned content."""
    escaped = html_module.escape(text, quote=True)

    def link(match: re.Match[str]) -> str:
        label, target = match.groups()
        decoded_target = html_module.unescape(target).strip()
        parsed = urlsplit(decoded_target)
        if parsed.scheme and parsed.scheme not in {"http", "https", "mailto"}:
            raise BundleError(f"Unsupported Markdown link: {decoded_target}")
        attributes = ""
        if parsed.scheme in {"http", "https"}:
            attributes = ' target="_blank" rel="noreferrer"'
        target_html = html_module.escape(decoded_target, quote=True)
        return f'<a href="{target_html}"{attributes}>{label}</a>'

    escaped = _LINK.sub(link, escaped)
    escaped = _INLINE_CODE.sub(r"<code>\1</code>", escaped)
    return _BOLD.sub(r"<strong>\1</strong>", escaped)


def _render_markdown(markdown: str) -> tuple[str, str]:  # noqa: C901
    """Render a deliberately small, dependency-free Markdown subset."""
    output: list[str] = []
    navigation: list[str] = []
    paragraph: list[str] = []
    used_ids: set[str] = set()
    list_tag: str | None = None
    in_code = False
    code_lines: list[str] = []
    section_open = False
    details_open = False

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{_inline_markdown(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            output.append(f"</{list_tag}>")
            list_tag = None

    def close_details() -> None:
        nonlocal details_open
        flush_paragraph()
        close_list()
        if details_open:
            output.append("</div></details>")
            details_open = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                code = html_module.escape(chr(10).join(code_lines))
                output.append(f'<pre class="command"><code>{code}</code></pre>')
                code_lines.clear()
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        heading = re.fullmatch(r"(#{1,3})\s+(.+)", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if level == 1:
                heading_html = _inline_markdown(title)
                output.append(
                    f'<header class="hero"><h1>{heading_html}</h1></header>'
                )
            elif level == 2:
                close_details()
                if section_open:
                    output.append("</section>")
                anchor = _slug(title, used_ids)
                navigation.append(
                    f'<a href="#{anchor}">{_inline_markdown(title)}</a>'
                )
                heading_html = _inline_markdown(title)
                output.append(
                    f'<section id="{anchor}"><h2><span>'
                    f"{heading_html}</span></h2>"
                )
                section_open = True
            else:
                close_details()
                label = title.removeprefix("進階:").strip()
                output.append(
                    '<details class="advanced"><summary>'
                    f"進階: {_inline_markdown(label)}</summary><div>"
                )
                details_open = True
            continue
        item = re.fullmatch(r"\s*([-*]|\d+\.)\s+(.+)", line)
        if item:
            flush_paragraph()
            tag = "ul" if item.group(1) in {"-", "*"} else "ol"
            if list_tag != tag:
                close_list()
                output.append(f"<{tag}>")
                list_tag = tag
            output.append(f"<li>{_inline_markdown(item.group(2))}</li>")
            continue
        if not line.strip():
            flush_paragraph()
            close_list()
            continue
        paragraph.append(line.strip())

    if in_code:
        raise BundleError("Unclosed Markdown code fence")
    close_details()
    if section_open:
        output.append("</section>")
    return "\n".join(output), "\n".join(navigation)


def _inject_markdown(html: str, *, root: Path) -> str:
    """Insert project-owned Markdown when the managed shell requests it."""
    markers = (_MARKDOWN_NAV, _MARKDOWN_CONTENT, _MARKDOWN_TITLE)
    present = tuple(marker in html for marker in markers)
    if not any(present):
        return html
    if not all(present):
        raise BundleError("Site shell has an incomplete Markdown marker set")

    content_path = root / "docs/site-content.md"
    try:
        markdown = content_path.read_text(encoding="utf-8")
    except OSError as error:
        raise BundleError(f"Cannot read {content_path}: {error}") from error
    config = _load_config(root)
    content, navigation = _render_markdown(_substitute_config(markdown, config))
    if (root / "docs/site-content.js").is_file():
        content = (
            '<aside class="notice"><strong>需要遷移舊網站內容：</strong>'  # noqa: RUF001
            "既有 <code>docs/site-content.js</code> 仍保留但不再顯示；"  # noqa: RUF001
            "請把要保留的文字移到 <code>docs/site-content.md</code>，"  # noqa: RUF001
            "確認後再刪除舊檔。</aside>\n"
            f"{content}"
        )
    title = html_module.escape(
        f"{_config_text(config.get('project_name'))} — 內部專案網站"
    )
    return (
        html.replace(_MARKDOWN_NAV, navigation)
        .replace(_MARKDOWN_CONTENT, content)
        .replace(_MARKDOWN_TITLE, title)
    )


def _asset_path(root: Path, parent: Path, url: str) -> Path | None:
    """Resolve one local asset and reject runtime network dependencies."""
    if url.startswith("data:") or url.startswith("#"):
        return None

    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc:
        raise BundleError(f"External runtime asset is not allowed: {url}")

    asset = (parent / unquote(parsed.path)).resolve()
    try:
        asset.relative_to(root.resolve())
    except ValueError as error:
        raise BundleError(
            f"Asset escapes the repository root: {url}"
        ) from error
    if not asset.is_file():
        raise BundleError(f"Asset does not exist: {url}")
    return asset


def _data_uri(asset: Path) -> str:
    """Encode an asset as a deterministic data URI."""
    media_type = MEDIA_TYPES.get(
        asset.suffix.lower(), "application/octet-stream"
    )
    payload = base64.b64encode(asset.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{payload}"


def _inline_css(css: str, stylesheet: Path, root: Path) -> str:
    """Inline every local CSS asset and reject imports."""
    if _CSS_IMPORT.search(css):
        raise BundleError(f"CSS @import is not allowed: {stylesheet}")

    def replace(match: re.Match[str]) -> str:
        url = match.group("url").strip()
        asset = _asset_path(root, stylesheet.parent, url)
        return match.group(0) if asset is None else f'url("{_data_uri(asset)}")'

    return _CSS_URL.sub(replace, css)


def _validate_content_schema(script: Path, content: str) -> None:
    """Fail closed for unsupported project content schemas."""
    if script.name != "site-content.js":
        return
    match = _SCHEMA_VERSION.search(content)
    version = int(match.group("version")) if match else 1
    if version != SUPPORTED_CONTENT_SCHEMA:
        raise BundleError(
            "Unsupported docs/site-content.js schemaVersion: "
            f"{version}; expected {SUPPORTED_CONTENT_SCHEMA}"
        )


def _inline_stylesheets(html: str, source: Path, root: Path) -> str:
    def replace_stylesheet(match: re.Match[str]) -> str:
        url = match.group("url")
        asset = _asset_path(root, source.parent, url)
        if asset is None:
            raise BundleError(f"Stylesheet must be a local file: {url}")
        css = _inline_css(asset.read_text(encoding="utf-8"), asset, root)
        if "</style>" in css.lower():
            raise BundleError(
                f"Stylesheet contains a closing style tag: {asset}"
            )
        return f'<style data-bundled-from="{url}">\n{css.rstrip()}\n</style>'

    return _STYLESHEET.sub(replace_stylesheet, html)


def _inline_scripts(html: str, source: Path, root: Path) -> str:
    def replace_script(match: re.Match[str]) -> str:
        url = match.group("url")
        asset = _asset_path(root, source.parent, url)
        if asset is None:
            raise BundleError(f"Script must be a local file: {url}")
        content = asset.read_text(encoding="utf-8")
        _validate_content_schema(asset, content)
        if "</script>" in content.lower():
            raise BundleError(f"Script contains a closing script tag: {asset}")
        return (
            f'<script data-bundled-from="{url}">\n{content.rstrip()}\n</script>'
        )

    return _SCRIPT.sub(replace_script, html)


def _inline_styles(html: str, source: Path, root: Path) -> str:
    def replace_style(match: re.Match[str]) -> str:
        css = _inline_css(match.group(2), source, root)
        return f"{match.group(1)}{css}{match.group(3)}"

    return _STYLE.sub(replace_style, html)


def _inline_assets(html: str, source: Path, root: Path) -> str:
    def replace_asset(match: re.Match[str]) -> str:
        url = match.group("url")
        asset = _asset_path(root, source.parent, url)
        if asset is None:
            return match.group(0)
        return (
            f"{match.group('prefix')}{_data_uri(asset)}{match.group('suffix')}"
        )

    html = _MEDIA_ATTRIBUTE.sub(replace_asset, html)
    return _ICON.sub(replace_asset, html)


def render(source: Path, *, root: Path) -> str:
    """Render one HTML source file into a self-contained document."""
    root = root.resolve()
    source = source.resolve()
    try:
        source.relative_to(root)
    except ValueError as error:
        raise BundleError(
            "Site source must be inside the repository root"
        ) from error

    html = source.read_text(encoding="utf-8")
    html = _inject_markdown(html, root=root)
    html = _inline_stylesheets(html, source, root)
    html = _inline_scripts(html, source, root)
    html = _inline_styles(html, source, root)
    html = _inline_assets(html, source, root)

    if _STYLESHEET.search(html) or _SCRIPT.search(html):
        raise BundleError(
            "Bundle still contains a runtime stylesheet or script"
        )
    return f"{html.rstrip()}\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, default=Path("site/index.html"))
    parser.add_argument("--output", type=Path, default=Path("docs/index.html"))
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed bundle does not match the source.",
    )
    return parser


def main() -> int:
    """Write the bundle, or verify that the committed output is current."""
    args = _parser().parse_args()
    root = args.root.resolve()
    source = root / args.source
    output = root / args.output
    try:
        bundled = render(source, root=root)
    except (BundleError, OSError, UnicodeError) as error:
        sys.stderr.write(f"site bundle failed: {error}\n")
        return 1

    if args.check:
        try:
            current = output.read_text(encoding="utf-8")
        except OSError as error:
            sys.stderr.write(f"site bundle is missing: {error}\n")
            return 1
        if current != bundled:
            sys.stderr.write(
                "docs/index.html is stale; run "
                "`uv run --no-project python scripts/render_site.py`.\n"
            )
            return 1
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(bundled, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
