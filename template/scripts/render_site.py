"""Build the portable documentation site as one self-contained HTML file."""

from __future__ import annotations

import argparse
import base64
import re
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


class BundleError(ValueError):
    """Report a source that cannot satisfy the portable bundle contract."""


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
