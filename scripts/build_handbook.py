#!/usr/bin/env python3
"""Render the repo-template handbook from its Markdown source (Issue #1081).

`docs/handbook/handbook.md` is the authoritative, editable source. This
single-page renderer turns it into `docs/handbook/index.html`, inlining the
stylesheet kept in `docs/handbook/handbook.css`, and records input and output
digests in `docs/handbook/manifest.json`. The owner-approved baseline under
`docs/handbook/approved/` is never rewritten; its SHA-256 must equal the
front matter `baseline_sha256`, otherwise the build fails closed.

Source syntax: TOML front matter between `+++` lines, then one Markdown
block per line group:

- `::: sheet <id> | <footer label>` opens an A4 sheet; `:::` closes it. The
  renderer adds the footer with the label, `footer_version` and `N / total`.
- `#`, `##`, `###` headings; any other plain line is one paragraph (one
  paragraph per line, so CJK text is never joined with spaces).
- A trailing ` {: spec}` on a heading or paragraph sets its element and
  classes, e.g. `{: div.eyebrow}` or `{: .compact .mt-3}`.
- A line holding only `{: spec}` applies to the next table, list or
  definition list, e.g. `{: table.stage-table.dense stage}`,
  `{: ul.checklist}`, `{: dl.terms.dense}`.
- Table flags: `stage` marks the first column `class="stage"` on th and td,
  `stage-td` only on td, `headless` renders every row into `<tbody>` (no
  `|---|` separator line).
- Definition list: a term line followed by a `: definition` line.
- Fenced code renders as a bare `<pre>`; `<!-- ... -->` blocks are
  source-only notes and are dropped; any other line starting with `<` is raw
  HTML passed through unchanged.
- Inline `code`, **bold** and [links](...) come from `_inline_markdown` in
  `scripts/render_site.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import runpy
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

_ROOT: Final = Path(__file__).resolve().parents[1]
_inline: Final = runpy.run_path(str(_ROOT / "scripts/render_site.py"))[
    "_inline_markdown"
]

SOURCE: Final = "docs/handbook/handbook.md"
STYLESHEET: Final = "docs/handbook/handbook.css"
OUTPUT: Final = "docs/handbook/index.html"
MANIFEST: Final = "docs/handbook/manifest.json"
ICON: Final = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "viewBox='0 0 1 1'%3E%3C/svg%3E"
)
_SPEC_SUFFIX: Final = re.compile(r"\s+\{:\s*([^}]*)\}$")
_SPEC_LINE: Final = re.compile(r"^\{:\s*([^}]*)\}$")
_SHEET: Final = re.compile(r"^::: sheet ([\w-]+) \| (.+)$")
_HEADING: Final = re.compile(r"^(#{1,3}) (.+)$")
_TABLE_FLAGS: Final = frozenset({"stage", "stage-td", "headless"})
_INDENT: Final = "      "


class HandbookError(ValueError):
    """Raised when the handbook source or baseline is invalid."""


def sha256(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_front_matter(text: str) -> tuple[dict[str, Any], list[str]]:
    """Split TOML front matter from the Markdown body lines."""
    if not text.startswith("+++\n"):
        raise HandbookError(f"{SOURCE} must start with +++ front matter")
    end = text.find("\n+++\n", 4)
    if end < 0:
        raise HandbookError(f"{SOURCE} front matter is not closed")
    meta = tomllib.loads(text[4 : end + 1])
    return meta, text[end + 5 :].splitlines()


def parse_spec(spec: str) -> tuple[str | None, list[str], set[str]]:
    """Parse `tag.class .class flag` into element, classes and flags."""
    tag: str | None = None
    classes: list[str] = []
    flags: set[str] = set()
    for token in spec.split():
        if token.startswith("."):
            classes.append(token[1:])
        elif "." in token:
            tag, *names = token.split(".")
            classes.extend(names)
        else:
            flags.add(token)
    return tag, classes, flags


def open_tag(tag: str, classes: list[str]) -> str:
    """Return an opening tag with an optional class attribute."""
    attr = f' class="{html.escape(" ".join(classes))}"' if classes else ""
    return f"<{tag}{attr}>"


def cells(line: str) -> list[str]:
    """Split one pipe-table row into stripped cell texts."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_table(
    rows: list[str], classes: list[str], flags: set[str]
) -> list[str]:
    """Render a pipe table with the documented first-column flags."""
    if unknown := flags - _TABLE_FLAGS:
        raise HandbookError(f"unknown table flags: {sorted(unknown)}")
    stage = ' class="stage"'
    out = [_INDENT + open_tag("table", classes)]
    body = rows
    if "headless" not in flags:
        if len(rows) < 2 or not re.fullmatch(r"\|(\s*-+\s*\|)+", rows[1]):
            raise HandbookError(f"table needs a |---| separator: {rows[0]}")
        th = [
            f"<th{stage if i == 0 and 'stage' in flags else ''}>"
            f"{_inline(cell)}</th>"
            for i, cell in enumerate(cells(rows[0]))
        ]
        out.append(f"{_INDENT}  <thead><tr>{''.join(th)}</tr></thead>")
        body = rows[2:]
    out.append(f"{_INDENT}  <tbody>")
    td_stage = flags & {"stage", "stage-td"}
    for row in body:
        td = [
            f"<td{stage if i == 0 and td_stage else ''}>{_inline(cell)}</td>"
            for i, cell in enumerate(cells(row))
        ]
        out.append(f"{_INDENT}    <tr>{''.join(td)}</tr>")
    out += [f"{_INDENT}  </tbody>", f"{_INDENT}</table>"]
    return out


def render_body(lines: list[str], meta: dict[str, Any]) -> tuple[str, int]:  # noqa: C901
    """Render the Markdown body into sheets; return HTML and sheet count."""
    total = sum(1 for line in lines if _SHEET.match(line))
    out: list[str] = []
    pending: tuple[str | None, list[str], set[str]] | None = None
    sheet = 0
    footer = ""
    index = 0

    def take(predicate: Callable[[str], bool]) -> list[str]:
        nonlocal index
        block: list[str] = []
        while index < len(lines) and predicate(lines[index]):
            block.append(lines[index])
            index += 1
        return block

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        index += 1
        if pending is not None and (stripped.startswith(("<", "#", ":::"))):
            raise HandbookError(f"block spec not followed by a block: {line}")
        if not stripped:
            continue
        if stripped.startswith("<!--"):
            while "-->" not in line and index < len(lines):
                line = lines[index]
                index += 1
        elif match := _SHEET.match(line):
            sheet += 1
            footer = match.group(2)
            out += [
                f'  <section class="sheet" id="{match.group(1)}">',
                '    <div class="page-content">',
            ]
        elif stripped == ":::":
            spans = (footer, meta["footer_version"], f"{sheet} / {total}")
            inner = "".join(f"<span>{html.escape(s)}</span>" for s in spans)
            out += [
                "    </div>",
                f'    <footer class="page-footer">{inner}</footer>',
                "  </section>",
            ]
        elif match := _SPEC_LINE.match(stripped):
            pending = parse_spec(match.group(1))
        elif stripped.startswith("```"):
            code = take(lambda text: not text.startswith("```"))
            index += 1
            escaped = html.escape("\n".join(code), quote=False)
            out.append(f"{_INDENT}<pre>{escaped}</pre>")
        elif stripped.startswith("<"):
            out.append(_INDENT + line.rstrip())
        elif stripped.startswith("|"):
            tag, classes, flags = pending or (None, [], set())
            pending = None
            rows = [line, *take(lambda text: text.startswith("|"))]
            out += render_table(rows, classes, flags)
        elif stripped.startswith("- "):
            _, classes, _ = pending or (None, [], set())
            pending = None
            items = [line, *take(lambda text: text.startswith("- "))]
            out.append(_INDENT + open_tag("ul", classes))
            out += [f"{_INDENT}  <li>{_inline(i[2:])}</li>" for i in items]
            out.append(f"{_INDENT}</ul>")
        elif pending is not None and pending[0] == "dl":
            classes = pending[1]
            pending = None
            pairs = [line, *take(lambda text: text.strip() != "")]
            out.append(_INDENT + open_tag("dl", classes))
            for term, definition in zip(pairs[::2], pairs[1::2], strict=True):
                if not definition.startswith(": "):
                    raise HandbookError(
                        f"definition must start with ': ' {term}"
                    )
                out.append(
                    f"{_INDENT}  <dt>{_inline(term)}</dt>"
                    f"<dd>{_inline(definition[2:])}</dd>"
                )
            out.append(f"{_INDENT}</dl>")
        else:
            if pending is not None:
                raise HandbookError(f"block spec before a paragraph: {line}")
            tag, classes = "p", []
            if heading := _HEADING.match(stripped):
                tag, stripped = f"h{len(heading.group(1))}", heading.group(2)
            if suffix := _SPEC_SUFFIX.search(stripped):
                element, classes, _ = parse_spec(suffix.group(1))
                tag = element or tag
                stripped = stripped[: suffix.start()]
            out.append(
                f"{_INDENT}{open_tag(tag, classes)}{_inline(stripped)}</{tag}>"
            )
    if pending is not None:
        raise HandbookError("block spec at end of source")
    return "\n".join(out), total


def render(root: Path) -> tuple[str, dict[str, Any]]:
    """Render the handbook page and its manifest without writing files."""
    meta, lines = split_front_matter((root / SOURCE).read_text("utf-8"))
    baseline = root / "docs/handbook" / meta["baseline"]
    digest = sha256(baseline)
    if digest != meta["baseline_sha256"]:
        raise HandbookError(
            f"{baseline.relative_to(root)} sha256 {digest} is not the "
            f"approved {meta['baseline_sha256']}"
        )
    body, total = render_body(lines, meta)
    css = (root / STYLESHEET).read_text("utf-8")
    page = (
        "<!doctype html>\n"
        f'<html lang="{html.escape(meta["lang"])}">\n<head>\n'
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, '
        'initial-scale=1">\n'
        f'  <link rel="icon" href="{ICON}">\n'
        f"  <title>{html.escape(meta['title'])}</title>\n"
        f"  <style>\n{css}  </style>\n</head>\n<body>\n<main>\n"
        f"{body}\n</main>\n</body>\n</html>\n"
    )
    manifest = {
        "baseline": {
            "path": str(baseline.relative_to(root)),
            "sha256": digest,
        },
        "source": {"path": SOURCE, "sha256": sha256(root / SOURCE)},
        "stylesheet": {"path": STYLESHEET, "sha256": sha256(root / STYLESHEET)},
        "html": {
            "path": OUTPUT,
            "sha256": hashlib.sha256(page.encode("utf-8")).hexdigest(),
        },
        "status": meta["status"],
        "sheets": total,
    }
    return page, manifest


def main(argv: list[str] | None = None) -> int:
    """Write or check the generated handbook page and manifest."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=_ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        page, manifest = render(root)
    except (HandbookError, KeyError, OSError, tomllib.TOMLDecodeError) as exc:
        sys.stderr.write(f"build-handbook: {exc}\n")
        return 1
    outputs = {
        OUTPUT: page,
        MANIFEST: json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    }
    if args.check:
        stale = [
            path
            for path, text in outputs.items()
            if not (root / path).is_file()
            or (root / path).read_text("utf-8") != text
        ]
        if stale:
            sys.stderr.write(
                f"build-handbook: stale {', '.join(stale)}; "
                "run scripts/build-handbook\n"
            )
            return 1
        sys.stdout.write("build-handbook: outputs are fresh\n")
        return 0
    for path, text in outputs.items():
        (root / path).write_text(text, "utf-8")
    sys.stdout.write(f"build-handbook: wrote {OUTPUT} and {MANIFEST}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
