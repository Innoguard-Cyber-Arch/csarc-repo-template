import runpy
from pathlib import Path

import pytest

SITE_MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "render_site.py")
)
BundleError = SITE_MODULE["BundleError"]
render = SITE_MODULE["render"]


def test_render_inlines_local_runtime_assets(tmp_path: Path) -> None:
    site = tmp_path / "site"
    docs = tmp_path / "docs"
    site.mkdir()
    docs.mkdir()
    (site / "pixel.png").write_bytes(b"png")
    (site / "style.css").write_text(
        '.hero { background: url("pixel.png"); }', encoding="utf-8"
    )
    (site / "app.js").write_text(
        'document.body.dataset.ready = "yes";', encoding="utf-8"
    )
    (docs / "site-content.js").write_text(
        "window.CONTENT = { schemaVersion: 1 };", encoding="utf-8"
    )
    source = site / "index.html"
    source.write_text(
        """<!doctype html>
<link rel="stylesheet" href="style.css">
<script src="../docs/site-content.js"></script>
<script src="app.js"></script>
<img src="pixel.png" alt="">
<a href="https://example.com/reference">Reference</a>
""",
        encoding="utf-8",
    )

    bundled = render(source, root=tmp_path)

    assert '<style data-bundled-from="style.css">' in bundled
    assert '<script data-bundled-from="app.js">' in bundled
    assert "data:image/png;base64,cG5n" in bundled
    assert 'href="https://example.com/reference"' in bundled
    assert "stylesheet" not in bundled
    assert "<script src=" not in bundled


@pytest.mark.parametrize(
    "runtime_asset",
    [
        '<link rel="stylesheet" href="https://cdn.example/style.css">',
        '<script src="https://cdn.example/app.js"></script>',
        '<img src="https://cdn.example/image.png" alt="">',
    ],
)
def test_render_rejects_external_runtime_assets(
    tmp_path: Path, runtime_asset: str
) -> None:
    source = tmp_path / "index.html"
    source.write_text(runtime_asset, encoding="utf-8")

    with pytest.raises(BundleError, match="External runtime asset"):
        render(source, root=tmp_path)


def test_render_rejects_unsupported_content_schema(tmp_path: Path) -> None:
    site = tmp_path / "site"
    docs = tmp_path / "docs"
    site.mkdir()
    docs.mkdir()
    (docs / "site-content.js").write_text(
        "window.CONTENT = { schemaVersion: 2 };", encoding="utf-8"
    )
    source = site / "index.html"
    source.write_text(
        '<script src="../docs/site-content.js"></script>', encoding="utf-8"
    )

    with pytest.raises(BundleError, match="schemaVersion"):
        render(source, root=tmp_path)


@pytest.mark.parametrize(
    ("url", "message"),
    [("missing.js", "does not exist"), ("../outside.js", "escapes")],
)
def test_render_rejects_missing_or_outside_assets(
    tmp_path: Path, url: str, message: str
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.js").write_text("", encoding="utf-8")
    source = root / "index.html"
    source.write_text(f'<script src="{url}"></script>', encoding="utf-8")

    with pytest.raises(BundleError, match=message):
        render(source, root=root)


def test_render_accepts_legacy_content_as_schema_one(tmp_path: Path) -> None:
    site = tmp_path / "site"
    docs = tmp_path / "docs"
    site.mkdir()
    docs.mkdir()
    (docs / "site-content.js").write_text(
        "window.CONTENT = {};", encoding="utf-8"
    )
    source = site / "index.html"
    source.write_text(
        '<script src="../docs/site-content.js"></script>', encoding="utf-8"
    )

    assert "window.CONTENT = {};" in render(source, root=tmp_path)


def test_similar_tools_appendix_is_maintainer_only() -> None:
    root = Path(__file__).parents[1]
    source = (root / "site" / "index.html").read_text(encoding="utf-8")
    app = (root / "site" / "app.js").read_text(encoding="utf-8")

    assert 'class="slide similar-tools-slide" data-audience="maintainer"' in source
    assert source.count('data-work-step="') == 10
    assert "get('audience') === 'maintainer'" in app
    assert "element.remove()" in app
    assert "similarToolsSlide ?" in app
