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
- `::: annex <id> | <footer label>` opens an appended appendix sheet (Issue
  #1138). Annex sheets come after every main sheet, render as
  `class="sheet annex"`, number themselves `附錄 N / total`, and never count
  toward the main body's sheet total, so the approved main body is unchanged.
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
- `::: format <kind> <argument>` (one line) renders a `<pre class="format">`
  generated from the authoritative source at build time (Issue #1139):
  `file <path>`, `fence <path> <first line>`, `issue-form <path>`,
  `record <path> <heading>` (field table to fill-in skeleton),
  `checklist <path> <heading>`, `section <path> <heading>`, `tracker`,
  `conventions`, `authorization`, `changelog`, `trailers` and `report`.
  A missing source fails the build.
- Inline `code`, **bold** and [links](...) come from `_inline_markdown` in
  `scripts/render_site.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
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
_SHEET: Final = re.compile(r"^::: (sheet|annex) ([\w-]+) \| (.+)$")
_HEADING: Final = re.compile(r"^(#{1,3}) (.+)$")
_FORMAT: Final = re.compile(r"^::: format ([\w-]+)(?: (.+))?$")
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


def _section_lines(path: Path, heading: str) -> list[str]:
    """Return the lines under one exact heading, up to the next heading."""
    lines = path.read_text("utf-8").splitlines()
    for start, line in enumerate(lines):
        if re.fullmatch(rf"#{{1,6}} {re.escape(heading)}", line):
            level = len(line) - len(line.lstrip("#"))
            end = next(
                (
                    i
                    for i in range(start + 1, len(lines))
                    if re.match(rf"#{{1,{level}}} ", lines[i])
                ),
                len(lines),
            )
            return lines[start + 1 : end]
    raise HandbookError(f"{path.name}: heading not found: {heading}")


def _fence(path: Path, first: str) -> str:
    """Return the fenced block of a file whose first line is `first`."""
    lines = path.read_text("utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("```") and lines[index + 1 : index + 2] == [first]:
            end = lines.index(line[:3], index + 1)
            return "\n".join(lines[index + 1 : end])
    raise HandbookError(f"{path.name}: no fenced block starts with {first}")


def _issue_form(path: Path) -> str:
    """Return the body a submitted Issue form produces, with placeholders."""
    import yaml

    form = yaml.safe_load(path.read_text("utf-8"))
    parts = []
    for item in form["body"]:
        if item["type"] == "markdown":
            continue
        attrs = item["attributes"]
        if item["type"] == "dropdown":
            value = "<" + " / ".join(attrs["options"]) + ">"
        else:
            value = (
                attrs.get("value")
                or attrs.get("placeholder")
                or (f"<{attrs['description'].strip()}>")
            )
        parts.append(f"### {attrs['label']}\n\n{value.rstrip()}")
    return "\n\n".join(parts)


def _record(path: Path, heading: str) -> str:
    """Turn a section's field table into a fill-in record skeleton."""
    rows = [
        cells(line)
        for line in _section_lines(path, heading)
        if line.startswith("|")
    ]
    if len(rows) < 3 or rows[0][0] != "欄位":
        raise HandbookError(f"{path.name}: {heading} has no field table")
    end = next(
        (i for i, row in enumerate(rows[2:], 2) if row[0] == "欄位"), len(rows)
    )
    body = [f"| {name} | <{hint}> |" for name, hint, *_ in rows[2:end]]
    return "\n".join(["| 欄位 | 內容 |", "| --- | --- |", *body])


def _checklist(path: Path, heading: str) -> str:
    """Turn numbered `N. **Step**` lines into checkbox lines."""
    steps = [
        match.group(1)
        for line in _section_lines(path, heading)
        if (match := re.match(r"\d+\. \*\*(.+?)\*\*", line))
    ]
    if not steps:
        raise HandbookError(f"{path.name}: {heading} has no numbered steps")
    return "\n".join(f"- [ ] {step}" for step in steps)


def _conventions(root: Path) -> str:
    """Show branch and PR title rules from the checks that enforce them."""
    branch = re.search(
        r"work_branch_pattern='\^\(([a-z|]+)\)/",
        (root / "scripts/gh-issue-develop").read_text("utf-8"),
    )
    title = re.search(
        r'"\$PR_TITLE" =~ \^\(([a-z|]+)\)',
        (root / "scripts/validate-pr-policy").read_text("utf-8"),
    )
    if branch is None or title is None:
        raise HandbookError("branch or PR title rule not found")
    return "\n".join(
        [
            "Branch:   <type>/<Issue>-<slug>",
            "          feat/123-summary-table",
            f"          type = {branch.group(1).replace('|', ' | ')}",
            "",
            "PR title: <type>(<scope>)!: <summary>",
            "          (ASCII; scope and ! are optional)",
            "          feat(report): add a summary table",
            "          fix(cli)!: reject an empty answer",
            f"          type = {title.group(1).replace('|', ' | ')}",
            "",
            "Squash commit = PR title; feat → minor, fix/revert → patch,",
            "! → major, other types → no release.",
        ]
    )


def _authorization(root: Path) -> str:
    """Return the exact merge authorization comment with placeholders."""
    statement = runpy.run_path(str(root / "scripts/pr_lifecycle.py"))[
        "authorization_statement"
    ]
    pr, head = 987654321, "f" * 40
    text = statement("<owner>/<repository>", pr, head)
    return text.replace(str(pr), "<PR>").replace(head, "<head SHA>")


def _changelog(root: Path) -> str:
    """Generate one CHANGELOG entry with the real writer on fictional work."""
    writer = runpy.run_path(str(root / "scripts/release_policy.py"))[
        "_write_changelog"
    ]
    fixed = {
        "GIT_AUTHOR_NAME": "Example",
        "GIT_AUTHOR_EMAIL": "example@example.invalid",
        "GIT_COMMITTER_NAME": "Example",
        "GIT_COMMITTER_EMAIL": "example@example.invalid",
        "GIT_AUTHOR_DATE": "2026-01-02T00:00:00Z",
        "GIT_COMMITTER_DATE": "2026-01-02T00:00:00Z",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    saved = {key: os.environ.get(key) for key in fixed}
    os.environ.update(fixed)
    try:
        with tempfile.TemporaryDirectory(prefix="handbook-") as temporary:
            repo = Path(temporary)

            def git(*args: str) -> str:
                return subprocess.run(  # noqa: S603
                    ["git", *args],  # noqa: S607
                    cwd=repo,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

            git("init", "-q", "-b", "main")
            (repo / "CHANGELOG.md").write_text("# Changelog\n", "utf-8")
            for subject in (
                "chore: start the project",
                "feat(report): add a summary table",
                "fix(cli): reject an empty answer",
                "docs: explain the setup",
            ):
                (repo / "work.txt").write_text(subject, "utf-8")
                git("add", "-A")
                git("commit", "-q", "-m", subject)
            writer(repo, git("rev-parse", "HEAD"), "1.1.0")
            text = (repo / "CHANGELOG.md").read_text("utf-8")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return text.split("\n", 2)[2].strip()


def _section_text(path: Path, heading: str) -> str:
    """Return a section's text, with Jinja tags shown as placeholders."""
    text = "\n".join(_section_lines(path, heading)).strip()
    text = re.sub(r"\{%-?.*?-?%\}", "", text)
    return re.sub(r"\{\{\s*(\w+)[^}]*\}\}", r"<\1>", text).strip()


def _trailers(root: Path) -> str:
    """Show the squash commit trailers in their fixed order."""
    policy = json.loads((root / "policies/merge-trailers.json").read_text())
    lines = ["<PR title>", "", "<squash body>", ""]
    for key in policy["order"]:
        spec = policy["keys"][key]
        value = (
            " | ".join(spec["values"]) if "values" in spec else spec["value"]
        )
        optional = "" if spec.get("required") else "   (optional)"
        lines.append(f"{key}: <{value}>{optional}")
    return "\n".join(lines)


def _report(root: Path) -> str:
    """Show the lifecycle report's fixed Markdown sections (SPEC-008)."""
    import ast

    tree = ast.parse((root / "src/csarc_cli/lifecycle_report.py").read_text())
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "SECTION_HEADINGS"
        ):
            headings = ast.literal_eval(node.value)
            return "\n\n".join(f"## {name}\n\n<…>" for name in headings)
    raise HandbookError("lifecycle report SECTION_HEADINGS not found")


def render_format(root: Path, kind: str, argument: str) -> str:
    """Render one `::: format` directive from its authoritative source."""
    if kind == "file":
        text = (root / argument).read_text("utf-8").rstrip()
        if argument.endswith(".jinja"):
            text = re.sub(r"\{\{\s*(\w+)[^}]*\}\}", r"<\1>", text)
        return text
    if kind in {"fence", "record", "checklist", "section"}:
        path, _, rest = argument.partition(" ")
        handler = {
            "fence": _fence,
            "record": _record,
            "checklist": _checklist,
            "section": _section_text,
        }
        return handler[kind](root / path, rest)
    if kind == "issue-form":
        return _issue_form(root / argument)
    if kind == "tracker":
        script = (root / "scripts/create-milestone").read_text("utf-8")
        found = re.search(r"printf '(## Proposal[^']*)'", script)
        if found is None:
            raise HandbookError("create-milestone tracker body not found")
        body = found.group(1).replace("\\n", "\n").rstrip()
        return body.replace(
            "%s",
            "<Proposal：範圍、所屬 Issue，可含 ### Checkpoints>",  # noqa: RUF001
        )
    generators = {
        "conventions": _conventions,
        "authorization": _authorization,
        "changelog": _changelog,
        "trailers": _trailers,
        "report": _report,
    }
    if kind not in generators:
        raise HandbookError(f"unknown format kind: {kind}")
    return generators[kind](root)


def render_body(  # noqa: C901
    lines: list[str], meta: dict[str, Any], root: Path | None = None
) -> tuple[str, int, int]:
    """Render the Markdown body; return HTML, main and annex sheet counts."""
    kinds = [m.group(1) for line in lines if (m := _SHEET.match(line))]
    total, annexes = kinds.count("sheet"), kinds.count("annex")
    if kinds != sorted(kinds, key=lambda kind: kind == "annex"):
        raise HandbookError("annex sheets must follow every main sheet")
    out: list[str] = []
    pending: tuple[str | None, list[str], set[str]] | None = None
    sheet = annex = 0
    footer = page = ""
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
        elif match := _FORMAT.match(stripped):
            if root is None:
                raise HandbookError("format directives need a source root")
            text = render_format(root, match.group(1), match.group(2) or "")
            escaped = html.escape(text, quote=False)
            out.append(f'{_INDENT}<pre class="format">{escaped}</pre>')
        elif match := _SHEET.match(line):
            kind, footer = match.group(1), match.group(3)
            if kind == "sheet":
                sheet += 1
                page, classes = f"{sheet} / {total}", "sheet"
            else:
                annex += 1
                page, classes = f"附錄 {annex} / {annexes}", "sheet annex"
            out += [
                f'  <section class="{classes}" id="{match.group(2)}">',
                '    <div class="page-content">',
            ]
        elif stripped == ":::":
            spans = (footer, meta["footer_version"], page)
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
    return "\n".join(out), total, annexes


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
    body, total, annexes = render_body(lines, meta, root)
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
        "annex_sheets": annexes,
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
