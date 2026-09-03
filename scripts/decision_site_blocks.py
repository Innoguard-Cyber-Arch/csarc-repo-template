"""Shared `{{< name attr="value" >}}...{{< /name >}}` block parsing.

Both `scripts/check-decision-site-translations` (structural shape
comparison of the two language sources) and `scripts/build_decision_site.py`
(the rendering engine) need to recognize the same Hugo-shortcode-style block
syntax still used, unchanged, by `site/content/_index.{zh-tw,en}.md`. This
module is the single parser for that syntax so neither caller reimplements
it; `check-decision-site-translations` keeps its own shape-comparison logic
and only imports the regexes below.

The syntax has three shapes, all used by the content files:
- a *container* block: `{{< name attr="value" >}}...{{< /name >}}`; only
  `slide`, `legacy`, `basic`, `detail`, and `disclosure` are containers, and
  none of them nest inside another block of the same name;
- a *self-closing* call with attributes: `{{< config-guidance track="x" >}}`;
- a bare self-closing call: `{{< similar-tools >}}`, `{{< testing >}}`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

# Reused verbatim by scripts/check-decision-site-translations for its own
# flat, order-preserving shape comparison of both language sources.
BLOCK: Final = re.compile(
    r"(?={{<\s*(slide|detail|disclosure)\b([^>]*)>}}"
    r"(.*?){{<\s*/\1\s*>}})",
    re.DOTALL,
)
ATTRIBUTE: Final = re.compile(r'(\w+)="([^"]*)"')
NESTED_BLOCK: Final = re.compile(
    r"{{<\s*(detail|disclosure)\b[^>]*>}}.*?{{<\s*/\1\s*>}}",
    re.DOTALL,
)

# Shortcodes that can appear inside a slide body without a matching
# `{{< /name >}}` close tag; site/content/*.md never nests one inside
# another (verified by the content-fidelity ports in
# tests/test_build_decision_site.py).
SELF_CLOSING_NAMES: Final = ("config-guidance", "similar-tools", "testing")
# Shortcodes that always pair with a close tag and never nest inside their
# own name, but may nest inside a `basic` or non-legacy slide body.
CONTAINER_NAMES: Final = ("detail", "disclosure")

_MIXED_TOKEN: Final = re.compile(
    r"{{<\s*(?P<self_name>" + "|".join(SELF_CLOSING_NAMES) + r")\b"
    r"(?P<self_attrs>[^>]*)>}}"
    r"|"
    r"{{<\s*(?P<container_name>" + "|".join(CONTAINER_NAMES) + r")\b"
    r"(?P<attrs>[^>]*)>}}(?P<body>.*?){{<\s*/(?P=container_name)\s*>}}",
    re.DOTALL,
)


def parse_attributes(raw: str) -> dict[str, str]:
    """Parse one shortcode's `key="value"` attribute list."""
    return dict(ATTRIBUTE.findall(raw))


def _container_pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"{{{{<\s*{re.escape(name)}\b(?P<attrs>[^>]*)>}}}}"
        rf"(?P<body>.*?){{{{<\s*/{re.escape(name)}\s*>}}}}",
        re.DOTALL,
    )


def iter_containers(
    text: str, name: str
) -> list[tuple[dict[str, str], str, re.Match[str]]]:
    """Return every non-nested `{{< name ... >}}...{{< /name >}}` block."""
    return [
        (parse_attributes(match.group("attrs")), match.group("body"), match)
        for match in _container_pattern(name).finditer(text)
    ]


def find_container(
    text: str, name: str
) -> tuple[dict[str, str], str, re.Match[str]] | None:
    """Return the first `{{< name ... >}}...{{< /name >}}` block, if any."""
    match = _container_pattern(name).search(text)
    if match is None:
        return None
    return parse_attributes(match.group("attrs")), match.group("body"), match


@dataclass(frozen=True)
class MixedNode:
    """One segment of a slide/basic/detail/disclosure body, in source order.

    `kind` is `"text"` for prose (including raw HTML lines), one of
    `SELF_CLOSING_NAMES`, or one of `CONTAINER_NAMES`. `attrs` and `body`
    are empty for `"text"` nodes.
    """

    kind: str
    text: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    body: str = ""


def iter_mixed(text: str) -> list[MixedNode]:
    """Tokenize a body into ordered prose/shortcode segments.

    Splits `text` on every top-level `config-guidance` / `similar-tools` /
    `testing` self-closing call and `detail` / `disclosure` container block,
    preserving document order and treating everything else as one prose
    segment per gap (including raw HTML lines Hugo's `unsafe = true`
    goldmark setting let authors write directly).
    """
    nodes: list[MixedNode] = []
    position = 0
    for match in _MIXED_TOKEN.finditer(text):
        if match.start() > position:
            nodes.append(MixedNode("text", text=text[position : match.start()]))
        if match.group("self_name"):
            nodes.append(
                MixedNode(
                    match.group("self_name"),
                    attrs=parse_attributes(match.group("self_attrs")),
                )
            )
        else:
            nodes.append(
                MixedNode(
                    match.group("container_name"),
                    attrs=parse_attributes(match.group("attrs")),
                    body=match.group("body"),
                )
            )
        position = match.end()
    if position < len(text):
        nodes.append(MixedNode("text", text=text[position:]))
    return nodes
