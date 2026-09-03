"""Regression coverage for Issue #472: config_examples.json + the
config-guidance shortcode (now `render_config_guidance` in
scripts/build_decision_site.py; see Issue #524's Hugo-to-Python port)
replace the old hardcoded, zh-tw-only `configExamples` JS objects in
site/static/{app,legacy-components}.js.

Covers:
- the merged data file drops the orphaned tracks that had no matching
  decision-slide (`template`, `knowledge`) instead of migrating dead data;
- every migrated item carries real, distinct zh-tw and en text (not a
  machine-translation placeholder or a copy of the zh-tw string).

End-to-end rendering coverage (the right number of config-trigger /
inline-detail items per track, and multi-line `code` samples surviving
rendering byte-for-byte in both languages) now lives in
tests/test_build_decision_site.py, exercising `render_config_guidance`
directly -- no Hugo build required.
"""

from __future__ import annotations

import json
from pathlib import Path

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
