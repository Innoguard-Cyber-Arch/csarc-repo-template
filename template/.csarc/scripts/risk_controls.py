#!/usr/bin/env python3
"""Trace Issue requirements to risks and exact-head evidence (SPEC-010).

The one shipped gate module (#1079), loaded from the trusted base. Keep the
scripts, template/.csarc/scripts, and src/csarc_cli copies byte-identical,
stdlib-only, within 300 lines, and on the Python 3.12 grammar.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections.abc import Callable, Iterator

LABEL = "#### 風險與控制"
LABELS = (LABEL, LABEL + chr(0xFF08) + "SPEC-010 規劃格式" + chr(0xFF09))
HEADER = tuple(["ID", "類別", "等級", "風險", "控制", "預計證據", "Owner"])
PLANNING = tuple(["ID", "類別", "風險", "控制", "預計證據", "Owner"])
AC_HEADINGS = ("### 完成條件", "### Acceptance criteria")
EVIDENCE = "## Requirement evidence"
LEVELS, DASH = ("low", "medium", "high"), "—"
# R0 never covers these documents, root or rendered (#1058 decision 22.2).
POLICIES = ("AGENTS.md", "SECURITY.md", "docs/ci-policy.md")
SECURITY_DOCS = {*POLICIES, ".github/SECURITY.md", ".csarc/docs/ci-policy.md"}
MAX_ROWS, MAX_ACS, MAX_CELL, MAX_BLOCK = 10, 50, 300, 8000
FENCE, HEADING = re.compile(r" {0,3}(```|~~~)"), re.compile(r"#{1,6} ")
SEPARATOR, CELL = re.compile(r":?-{3,}:?"), re.compile(r"(?<!\\)\|")
RISK_ID = re.compile(r"R0|R[1-9][0-9]?")
TRACE_ID = re.compile(r"AC[1-9][0-9]?|R0|R[1-9][0-9]?")
CATEGORY = re.compile(r"[a-z][a-z0-9-]{1,31}")
OWNER = re.compile(r"@[A-Za-z0-9][A-Za-z0-9-]{0,38}")
AC_ITEM = re.compile(r"- \[[ xX]\] (.+)")
AC_LABEL = re.compile(r"\**AC([0-9]+)(?![0-9])")
TODO = re.compile(r"(?<![A-Za-z0-9_])TODO(?![A-Za-z0-9_])|^<[^<>|]*>$")
SECRET = re.compile(
    r"(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{8,}|AKIA[A-Z0-9]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[abposr]-[A-Za-z0-9-]{8,}"
    r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
PATH = re.compile(r"(?!/)(?!.*\.\.)([A-Za-z0-9._/-]{1,200})(::[\w.:-]{1,100})?")
FORMS = (
    ("scope", re.compile(r"scope:docs")),
    ("check", re.compile(r"check:[A-Za-z0-9_.()/ -]{1,80}")),
    ("manual", re.compile(r"manual: https://[^\s|]+ \S.{8,}")),
    ("accepted", re.compile(r"accepted: \S.{8,}")),
    ("path", PATH),
)
ISSUE_LINE = re.compile(r"Issue: #([1-9][0-9]*)")
COVERAGE_LINE = re.compile(r"Coverage: (sha256:[0-9a-f]{64})")
UNTRACED = re.compile(
    r"(release-please--|release/v|sync/main-to-|automation/).*"
)
PROMOTION = re.compile(r"(dev/m|promote/m|dev/i)[0-9]+-.+|dependabot/.+")
Risk = dict[str, str]


def lines_of(text: str) -> list[str]:
    """Normalize line endings before any rule runs."""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def unfenced(lines: list[str]) -> Iterator[tuple[int, str]]:
    """Yield the lines outside fenced code blocks."""
    fenced = False
    for index, line in enumerate(lines):
        fenced ^= bool(FENCE.match(line))
        if not fenced and not FENCE.match(line):
            yield index, line


def cells(line: str) -> tuple[str, ...]:
    """Split one table row on unescaped pipes and trim every cell."""
    inner = line.strip().removeprefix("|")
    inner = inner[:-1] if inner.endswith("|") and inner[-2:] != "\\|" else inner
    return tuple(cell.strip() for cell in CELL.split(inner))


def table(
    lines: list[str], label: int, *headers: tuple[str, ...]
) -> tuple[tuple[str, ...], list[tuple[str, ...]], int]:
    """Return the header, rows, and end of the table after one label."""
    at = label + 1
    while at < len(lines) and not lines[at].strip():
        at += 1
    head = cells(lines[at]) if at < len(lines) else ()
    rule = cells(lines[at + 1]) if at + 1 < len(lines) else ()
    valid = head in headers and len(rule) == len(head)
    if not valid or not all(SEPARATOR.fullmatch(cell) for cell in rule):
        return (), [], at
    end = at + 2
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    return head, [cells(line) for line in lines[at + 2 : end]], end


def parse_risks(body: str, out: list[str]) -> list[Risk]:  # noqa: C901
    """Parse the one risk block, appending each problem to `out`."""
    lines = lines_of(body)
    found = [i for i, line in unfenced(lines) if line.rstrip() in LABELS]
    if len(found) != 1:
        code = "RK02 keep exactly one" if found else "RK01 add the"
        out.append(f'{code} "{LABEL}" block in 補充 (SPEC-010)')
        return []
    head, rows, end = table(lines, found[0], HEADER, PLANNING)
    size = len("\n".join(lines[found[0] : end]))
    if not head or not 1 <= len(rows) <= MAX_ROWS or size > MAX_BLOCK:
        out.append(f"RK03 use | {' | '.join(HEADER)} | with 1-{MAX_ROWS} rows")
    risks: list[Risk] = []
    for number, row in enumerate(rows, start=1):
        risk = {"等級": "unrated", **dict(zip(head, row, strict=False))}
        rid, where = risk["ID"], f"row {number}"
        if len(row) != len(head) or not RISK_ID.fullmatch(rid):
            out.append(f"RK05 {where}: use {len(head)} cells and R0-R99")
            continue
        where += f" ({rid})"
        if rid in {r["ID"] for r in risks}:
            out.append(f"RK06 {where}: risk IDs must be unique")
        if rid == "R0" and (
            len(rows) != 1
            or (risk["類別"], risk["預計證據"]) != ("none", "scope:docs")
            or risk["等級"] not in {DASH, "unrated"}
        ):
            out.append(f"RK07 R0 is the only row: none, {DASH}, scope:docs")
        elif rid != "R0" and (
            not CATEGORY.fullmatch(risk["類別"]) or risk["類別"] == "none"
        ):
            out.append(f"RK08 {where}: 類別 must be a lowercase-kebab token")
        elif rid != "R0" and risk["等級"] not in LEVELS and head == HEADER:
            out.append(f"RK09 {where}: 等級 must be low, medium, or high")
        for column in ("風險", "控制", "預計證據"):
            text = risk[column]
            if not text or len(text) > MAX_CELL or TODO.search(text):
                out.append(f"RK10 {where} column {column}: write real text")
        if not OWNER.fullmatch(risk["Owner"]):
            out.append(f"RK11 {where}: Owner must be one @login")
        if any(SECRET.search(cell) for cell in row):
            out.append(f"RK12 {where}: drop secrets or personal data; rotate")
        risks.append(risk)
    return risks


def parse_acs(body: str, out: list[str]) -> list[str]:
    """Return the top-level 完成條件 checkboxes in order as AC1..ACn."""
    items: list[str] = []
    inside = False
    for _, line in unfenced(lines_of(body)):
        if HEADING.match(line):
            inside = line.rstrip() in AC_HEADINGS
        elif inside and (match := AC_ITEM.fullmatch(line.rstrip())):
            items.append(unicodedata.normalize("NFC", match.group(1).strip()))
    if not 1 <= len(items) <= MAX_ACS:
        out.append(f"RK13 list 1-{MAX_ACS} top-level - [ ] items in 完成條件")
    for position, text in enumerate(items, start=1):
        label = AC_LABEL.match(text)
        if label and int(label.group(1)) != position:
            out.append(f"RK14 AC{position}: the item is labeled out of order")
    return items


def evidence_kind(value: str) -> str | None:
    """Classify one evidence cell, or return None for an unknown form."""
    for kind, pattern in FORMS:
        if pattern.fullmatch(value) and not TODO.search(value):
            return kind
    return None


def parse_evidence(body: str, out: list[str]) -> tuple[int, str, Risk]:
    """Return the declared Issue, coverage digest, and evidence by ID."""
    lines = lines_of(body)
    found = [i for i, line in unfenced(lines) if line.rstrip() == EVIDENCE]
    if len(found) != 1:
        out.append(f'RK20 add exactly one "{EVIDENCE}" section')
        return 0, "", {}
    issue, coverage, at = 0, "", found[0]
    while at + 1 < len(lines) and not lines[at + 1].startswith(("## ", "|")):
        at += 1
        if match := ISSUE_LINE.fullmatch(lines[at].strip()):
            issue = int(match.group(1))
        coverage = "".join(COVERAGE_LINE.findall(lines[at].strip())) or coverage
    head, rows, _ = table(lines, at, ("ID", "證據"))
    if not head:
        out.append("RK21 use the header | ID | 證據 |")
    mapping: Risk = {}
    for number, row in enumerate(rows, start=1):
        if len(row) != 2 or not TRACE_ID.fullmatch(row[0]) or row[0] in mapping:
            out.append(f"RK22 evidence row {number}: use one unique AC/R ID")
            continue
        mapping[row[0]] = unicodedata.normalize("NFC", row[1].strip("`"))
        if evidence_kind(mapping[row[0]]) is None:
            out.append(f"RK23 {row[0]}: evidence is not a SPEC-010 form")
    return issue, coverage, mapping


def digest(text: str) -> str:
    """Return the `sha256:` digest of one normalized text."""
    data = "\n".join(lines_of(text)).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def coverage_digest(acs: list[str], risks: list[Risk]) -> str:
    """Digest the ordered criteria and risk controls evidence is bound to."""
    keys = ("ID", "類別", "等級", "控制", "Owner")
    rows = [[risk[key] for key in keys] for risk in risks]
    return digest(json.dumps([acs, rows], ensure_ascii=False))


def traced_route(base: str, head: str) -> bool:
    """Return whether a pull request must carry requirement evidence."""
    promotion = base == "main" and PROMOTION.match(head)
    return not (UNTRACED.fullmatch(head) or promotion)


def found_in(text: str | None, name: str) -> bool:
    """Return whether a file exists and holds every `::` identifier."""
    word = r"(?<![A-Za-z0-9_]){}(?![A-Za-z0-9_])"
    return text is not None and all(
        re.search(word.format(re.escape(part)), text)
        for part in name.split("::")
        if part
    )


def ready(  # noqa: C901
    issue: tuple[int, str, list[str]],
    pr_body: str,
    paths: list[str],
    scope_for: Callable[[str], str],
    read_file: Callable[[str], str | None],
) -> tuple[dict[str, object], list[str], list[str]]:
    """Return the trace, problems, and visible exceptions for Ready/merge."""
    number, body, assignees = issue
    out: list[str] = []
    risks, acs = parse_risks(body, out), parse_acs(body, out)
    declared, coverage, mapping = parse_evidence(pr_body, out)
    if out:
        return {}, out, []
    owners = {f"@{login}".casefold() for login in assignees}
    for risk in risks:
        if risk["Owner"].casefold() not in owners:
            out.append(f"RK15 {risk['ID']}: Owner must be an Issue assignee")
    if declared != number:
        out.append(f"RK24 write the line Issue: #{number}")
    expected = coverage_digest(acs, risks)
    if coverage != expected:
        out.append(
            f"RK25 stale coverage; remap, then write Coverage: {expected}"
        )
    ids = [f"AC{k}" for k in range(1, len(acs) + 1)] + [r["ID"] for r in risks]
    if missing := [tid for tid in ids if tid not in mapping]:
        out.append("RK26 map every requirement; missing " + ", ".join(missing))
    if unknown := sorted(set(mapping) - set(ids)):
        out.append("RK27 remove unknown IDs " + ", ".join(unknown))
    levels = {risk["ID"]: risk["等級"] for risk in risks}
    kinds = {tid: evidence_kind(value) for tid, value in mapping.items()}
    for tid in sorted(set(ids) & set(mapping)):
        path, _, name = mapping[tid].partition("::")
        if (kinds[tid] == "scope") != (tid == "R0") or (
            kinds[tid] == "accepted" and tid not in levels
        ):
            out.append(f"RK28 {tid}: this evidence form is not allowed here")
        elif kinds[tid] == "path" and not found_in(read_file(path), name):
            out.append(f"RK29 {tid}: {mapping[tid]} is not in the head tree")
    notes = []
    if "R0" in levels:
        changed = {scope_for(path) for path in paths} - {"docs"}
        if SECURITY_DOCS.intersection(paths):
            changed.add("security-docs")
        if changed:
            out.append(
                "RK30 R0 covers only docs outside the security-related list; "
                "this pull request also changes " + ", ".join(sorted(changed))
            )
        notes.append(f"#{number} R0 declared; {len(paths)} paths are docs")
    if accepted := [
        tid + ("(high)" if levels[tid] == "high" else "")
        for tid in sorted(set(levels) & set(mapping))
        if kinds[tid] == "accepted"
    ]:
        notes.append(f"#{number} self-accepted: " + ", ".join(accepted))
    evidence = dict(sorted(mapping.items()))
    trace = {"issue": number, "body_digest": digest(body), "evidence": evidence}
    return trace | {"coverage_digest": expected}, out, notes


def main() -> int:
    """Check an Issue body from stdin at the create stage."""
    body, out = sys.stdin.read(), []
    parse_risks(body, out)
    parse_acs(body, out)
    sys.stderr.write("".join(f"requirement-trace: {line}\n" for line in out))
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
