"""Guard against policies/capability-matrix.json drifting from the hand-
authored "Advanced install" decision-site slide (Issue #531).

The slide's capability table in `site/content/_index.en.md` /
`_index.zh-tw.md` is hand-written prose, not generated from
`policies/capability-matrix.json` -- see AGENTS.md's decision-site editing
rule ("pick the existing block that fits rather than inventing a one-off
layout"), which favors a plain Markdown table over a new data-driven
shortcode for content this simple. That means nothing forces the two to
stay in sync automatically; this test is the mechanical tripwire instead:
every capability id declared in the matrix must still be mentioned (as an
inline-code token) in both language files' slide content.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import repo_capabilities as rc  # noqa: E402

MATRIX_PATH = ROOT / "policies" / "capability-matrix.json"
CONTENT_PATHS = (
    ROOT / "site" / "content" / "_index.en.md",
    ROOT / "site" / "content" / "_index.zh-tw.md",
)


def test_every_matrix_capability_id_is_mentioned_in_both_language_slides() -> (
    None
):
    matrix = rc.load_matrix(MATRIX_PATH)
    capability_ids = [entry["id"] for entry in matrix]

    for content_path in CONTENT_PATHS:
        text = content_path.read_text(encoding="utf-8")
        assert "advanced-install" in text, (
            f"{content_path} is missing the advanced-install slide"
        )
        missing = [
            capability_id
            for capability_id in capability_ids
            if f"`{capability_id}`" not in text
        ]
        assert not missing, (
            f"{content_path} is missing capability ids: {missing}"
        )


def test_navigation_declares_the_advanced_install_appendix() -> None:
    import json

    navigation = json.loads(
        (ROOT / "site" / "data" / "navigation.json").read_text(encoding="utf-8")
    )
    appendix_keys = {item["key"] for item in navigation["appendices"]}

    assert "advanced-install" in appendix_keys
