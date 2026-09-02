"""Regression coverage for Issue #472: config_examples.json + the
config-guidance Hugo shortcode replace the old hardcoded, zh-tw-only
`configExamples` JS objects in site/static/{app,legacy-components}.js.

Covers:
- the merged data file drops the orphaned tracks that had no matching
  decision-slide (`template`, `knowledge`) instead of migrating dead data;
- every migrated item carries real, distinct zh-tw and en text (not a
  machine-translation placeholder or a copy of the zh-tw string);
- the config-guidance shortcode actually renders the right number of
  config-trigger / inline-detail items per track in both languages. This is
  an end-to-end Hugo-build check, not just a source read: the shortcode's
  first implementation silently dropped items whenever a `code` sample
  contained a blank line, once it was embedded in the markdownify-processed
  English page (a Go template pipe-argument-order bug, then a CommonMark
  raw-HTML-block/blank-line interaction) — a source-only check would not
  have caught it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]

# Tracks with a live `{{< slide ... track="..." decision-slide ... >}}` in
# both site/content/_index.zh-tw.md and site/content/_index.en.md. Anything
# in config_examples.json outside this set is orphaned data that should have
# been dropped instead of migrated (see the module docstring and Issue #472's
# own "orphan" completion criterion).
LIVE_DECISION_TRACKS = {
    "method",
    "agents",
    "contract",
    "languages",
    "pr",
    "supply",
    "deploy",
    "governance",
    "template-release",
}

DIRECT_TRACKS = {"method", "agents", "contract"}


def _load_config_examples() -> dict:
    return json.loads(
        (ROOT / "site/data/config_examples.json").read_text(encoding="utf-8")
    )


def test_config_examples_matches_live_tracks_and_drops_orphans() -> None:
    data = _load_config_examples()
    assert set(data["tracks"]) == LIVE_DECISION_TRACKS
    # The pre-migration app.js/legacy-components.js data carried extra keys
    # ('template', 'knowledge' in legacy-components.js; also 'ci', 'rollout'
    # in app.js) with no matching decision-slide anywhere in
    # site/content/*.md. None of that dead data should have been migrated.
    for orphan in ("template", "knowledge", "ci", "rollout"):
        assert orphan not in data["tracks"]

    chinese = (ROOT / "site/content/_index.zh-tw.md").read_text(
        encoding="utf-8"
    )
    english = (ROOT / "site/content/_index.en.md").read_text(encoding="utf-8")
    for track, spec in data["tracks"].items():
        assert spec["direct"] == (track in DIRECT_TRACKS)
        assert spec["items"], f"{track} has no items"
        for source in (chinese, english):
            assert f'{{{{< config-guidance track="{track}" >}}}}' in source


def test_config_examples_is_genuinely_bilingual() -> None:
    """Every item carries real, distinct English text, not a placeholder."""
    data = _load_config_examples()
    for label in data["labels"]["zh-tw"]:
        zh = data["labels"]["zh-tw"][label]
        en = data["labels"]["en"][label]
        assert zh and en and zh != en

    for track, spec in data["tracks"].items():
        for index, item in enumerate(spec["items"]):
            for field in ("title", "goal", "file", "code"):
                zh = item[field]["zh-tw"]
                en = item[field]["en"]
                assert zh, f"{track}[{index}].{field} missing zh-tw text"
                assert en, f"{track}[{index}].{field} missing en text"
            # `title` and `goal` are always prose and must be translated.
            # `file` (a path) and `code` (mostly language-neutral shell/YAML)
            # are legitimately identical across languages unless they embed
            # descriptive prose in the original zh-tw text.
            for field in ("title", "goal"):
                assert item[field]["zh-tw"] != item[field]["en"], (
                    f"{track}[{index}].{field} en text is identical to "
                    "zh-tw (looks unmigrated or copy-pasted)"
                )
            if "summary" in item:
                assert item["summary"]["zh-tw"] != item["summary"]["en"]


def test_governance_single_source_item_translation_is_accurate() -> None:
    """Manually cross-checked pair (Issue #472's own acceptance criterion):
    the zh-tw and en text for governance[0] describe the same fixed/adjustable
    policy, not a re-worded or drifted substitute.
    """
    data = _load_config_examples()
    item = data["tracks"]["governance"]["items"][0]
    assert item["title"]["zh-tw"] == "單一來源｜治理只保存高價值選項"  # noqa: RUF001
    assert item["title"]["en"] == (
        "Single source | Governance keeps only high-value options"
    )
    assert ".csarc/config.yml" in item["summary"]["en"]
    assert "policies/" in item["summary"]["en"]
    assert "branch_strategy" in item["code"]["en"]
    # The code sample is deliberately shared (language-neutral YAML), unlike
    # prose fields.
    assert item["code"]["zh-tw"] == item["code"]["en"]


def test_app_js_rollout_orphan_is_intentionally_untouched() -> None:
    """app.js only backs the frozen site/legacy/index.html parity fixture
    (Issue #472 explicitly excludes site/legacy/index.html), and that fixture
    still has a `data-track="rollout"` slide. So app.js's `rollout` entry is
    not dead code in the context it actually runs in, and is out of scope for
    this migration; this test locks in that decision so a future change
    cannot silently orphan the fixture instead.
    """
    app_js = (ROOT / "site/static/app.js").read_text(encoding="utf-8")
    legacy_fixture = (ROOT / "site/legacy/index.html").read_text(
        encoding="utf-8"
    )
    assert "rollout:" in app_js
    assert 'data-track="rollout"' in legacy_fixture
    assert '<script src="app.js"></script>' in legacy_fixture
    # The live, Markdown-driven decision slides never use this track.
    for content in (
        (ROOT / "site/content/_index.zh-tw.md").read_text(encoding="utf-8"),
        (ROOT / "site/content/_index.en.md").read_text(encoding="utf-8"),
    ):
        assert 'track="rollout"' not in content


def _hugo_binary() -> str | None:
    try:
        # repository-owned installer script, no untrusted input
        result = subprocess.run(  # noqa: S603
            [str(ROOT / "scripts/install-hugo")],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError, OSError:
        return None
    stripped = result.stdout.strip()
    path = stripped.splitlines()[-1] if stripped else ""
    return path or None


@pytest.mark.skipif(
    shutil.which("hugo") is None and _hugo_binary() is None,
    reason="Hugo is not installable in this environment",
)
def test_config_guidance_shortcode_renders_expected_counts_in_both_languages(
    tmp_path: Path,
) -> None:
    hugo_bin = _hugo_binary() or shutil.which("hugo")
    assert hugo_bin
    destination = tmp_path / "hugo-site"
    # locally installed/cached Hugo binary resolved above, no untrusted input
    subprocess.run(  # noqa: S603
        [
            hugo_bin,
            "--source",
            str(ROOT),
            "--config",
            "site/hugo.toml",
            "--destination",
            str(destination),
            "--cleanDestinationDir",
            "--noBuildLock",
            "--environment",
            "production",
            "--quiet",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )

    data = _load_config_examples()
    zh_html = (destination / "index.html").read_text(encoding="utf-8")
    en_html = (destination / "en/index.html").read_text(encoding="utf-8")

    for lang, html in (("zh-tw", zh_html), ("en", en_html)):
        direct_items = sum(
            len(spec["items"])
            for spec in data["tracks"].values()
            if spec["direct"]
        )
        assert html.count('class="config-inline-detail"') == direct_items

        for track, spec in data["tracks"].items():
            if spec["direct"]:
                continue
            expected = len(spec["items"])
            actual = len(
                re.findall(f'aria-controls="config-overlay-{track}"', html)
            )
            assert actual == expected, (
                f"{lang}: track {track!r} rendered {actual} config-trigger "
                f"buttons, expected {expected} (see site/data/"
                "config_examples.json)"
            )

        # No leftover markdownify corruption from a raw-HTML block ending at
        # a blank line partway through a multi-line `code` sample.
        assert "&lt;button" not in html
        assert "&ldquo;" not in html and "&rdquo;" not in html

    # The same governance item's rendered trigger carries distinct,
    # correctly localized text in each language.
    item = data["tracks"]["governance"]["items"][0]
    assert f'data-config-title="{item["title"]["zh-tw"]}"' in zh_html
    assert f'data-config-title="{item["title"]["en"]}"' in en_html

    # Content-level check, not just a trigger count: the multi-line `code`
    # sample (with an embedded blank line) must survive server rendering
    # byte-for-byte in the data-config-code attribute, decoded from its
    # "&#10;" HTML-entity encoding back to real newlines. A wrong Go
    # template pipe argument order previously collapsed this to a single
    # "\n" character without changing the trigger count at all.
    for lang, html in (("zh-tw", zh_html), ("en", en_html)):
        match = re.search(
            r'aria-controls="config-overlay-governance"[^>]*'
            r'data-config-code="([^"]*)"',
            html,
        )
        assert match, f"{lang}: governance[0] trigger not found"
        rendered_code = (
            match.group(1)
            .replace("&#10;", "\n")
            .replace("&#34;", '"')
            .replace("&amp;", "&")
        )
        assert rendered_code == item["code"][lang], (
            f"{lang}: governance[0] data-config-code does not match the "
            "source code sample once decoded"
        )
        assert "\n" in rendered_code, (
            f"{lang}: governance[0] data-config-code lost its embedded newlines"
        )

    # Same check for a "direct" track's inline <pre>, whose zh-tw source code
    # contains a blank line (site/data/config_examples.json: agents[0]).
    agents_item = data["tracks"]["agents"]["items"][0]
    for lang, html in (("zh-tw", zh_html), ("en", en_html)):
        match = re.search(
            r'<pre class="code">([^<]*)</pre>\s*</div>\s*</details>',
            html[html.find(agents_item["title"][lang]) :],
        )
        assert match, f"{lang}: agents[0] inline <pre> not found"
        rendered_code = match.group(1).replace("&#10;", "\n")
        assert rendered_code == agents_item["code"][lang]
        assert "\n\n" in rendered_code, (
            f"{lang}: agents[0] <pre> lost its embedded blank line"
        )
