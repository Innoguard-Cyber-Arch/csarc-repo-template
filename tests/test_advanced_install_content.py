"""Guard against policies/capability-matrix.json drifting from the hand-
authored "Advanced install" repo-site content (Issue #531).

Issue #531 gave this content its own "advanced-install" slide; a later
UX review (#681/#682) folded it into the "install" slide's own Ops-mode
pane as three `{{< disclosure >}}` blocks instead (see the ADR), since
the standalone page read as an install variant but lived in a different
nav group. The capability table itself, in `site/content/_index.en.md` /
`_index.zh-tw.md`, is still hand-written prose, not generated from
`policies/capability-matrix.json` -- see AGENTS.md's repo-site editing
rule ("pick the existing block that fits rather than inventing a one-off
layout"), which favors a plain Markdown table over a new data-driven
shortcode for content this simple. That means nothing forces the two to
stay in sync automatically; this test is the mechanical tripwire instead:
every capability id declared in the matrix must still be mentioned (as an
inline-code token) in both language files' content.
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
            f"{content_path} is missing the advanced-install content"
        )
        missing = [
            capability_id
            for capability_id in capability_ids
            if f"`{capability_id}`" not in text
        ]
        assert not missing, (
            f"{content_path} is missing capability ids: {missing}"
        )


def test_advanced_install_has_no_separate_navigation_entry() -> None:
    import json

    navigation = json.loads(
        (ROOT / "site" / "data" / "navigation.json").read_text(encoding="utf-8")
    )
    # Issue #681 folded the former appendix bookend links into the "support"
    # group as ordinary numbered items; a later UX review (#681/#682) then
    # moved advanced-install/testing/bridge into their own unnumbered
    # "notes" group. A still later review (#681/#682) merged advanced-install
    # into the "install" slide's own Ops-mode pane as three disclosures
    # instead -- the standalone "進階安裝"/"Advanced" label read as an
    # install variant but lived in a different nav group and page, so it no
    # longer gets its own top-level entry.
    all_keys = {item["key"] for item in navigation["items"]}

    assert "advanced-install" not in all_keys
    assert "install" in all_keys
