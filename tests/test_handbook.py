"""Handbook source, generated page and print layout (Issue #1081).

AC1: the owner-approved r2 baseline is kept byte-for-byte and its digest is
pinned. AC2: the Markdown source renders to a page whose visible content and
structure equal the baseline, carries the planned status and names no
consumer. AC6: the generated main body still prints as 10 A4 sheets with no
overflow.

An approved handbook edit replaces the baseline copy under
docs/handbook/approved/ (with a new owner approval and digest) in the same
change, so the DOM parity check below always compares against the version
the owner approved.

Issue #1138 AC6 (owner decision 2026-10-16): template appendix sheets
(`class="sheet annex"`) are appended after the approved main body and are
not part of the baseline or its 10-sheet limit. Parity compares the main
body only; the annex sheets are checked separately for placement, links and
print overflow.
"""

from __future__ import annotations

import json
import re
import runpy
import shutil
import subprocess
import sys
import tomllib
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HANDBOOK = ROOT / "docs/handbook"
APPROVED_SHA256 = (
    "a69d2124a549dceb9478f40055675dd4495455d34d979ca02861171dbfb3292d"
)
BASELINE = HANDBOOK / "approved/261013r2_repo-template-handbook.html"
GENERATED = HANDBOOK / "index.html"
SHEETS = 10


def _front_matter() -> dict:
    text = (HANDBOOK / "handbook.md").read_text("utf-8")
    return tomllib.loads(text.split("+++\n")[1])


class _Events(HTMLParser):
    """Flatten a document into start, text and end events."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self.events.append(("start", tag, tuple(sorted(attrs))))

    def handle_endtag(self, tag: str) -> None:
        self.events.append(("end", tag))

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.events.append(("text", text))


def _events(path: Path) -> list[tuple]:
    parser = _Events()
    parser.feed(path.read_text("utf-8"))
    parser.close()
    return parser.events


def _is_annex(event: tuple) -> bool:
    return (
        event[:2] == ("start", "section")
        and "annex" in dict(event[2]).get("class", "").split()
    )


def _split_annexes(events: list[tuple]) -> tuple[list[tuple], list[list]]:
    """Return the main-body events and each appended annex sheet's events."""
    main: list[tuple] = []
    annexes: list[list] = []
    depth = 0
    for event in events:
        if depth == 0 and _is_annex(event):
            annexes.append([])
        if depth or _is_annex(event):
            if event[:2] == ("start", "section"):
                depth += 1
            elif event[:2] == ("end", "section"):
                depth -= 1
            annexes[-1].append(event)
        else:
            main.append(event)
    return main, annexes


def test_baseline_digest_is_the_approved_one() -> None:
    digest = sha256(BASELINE.read_bytes()).hexdigest()
    assert digest == APPROVED_SHA256
    assert _front_matter()["baseline_sha256"] == APPROVED_SHA256
    manifest = json.loads((HANDBOOK / "manifest.json").read_text("utf-8"))
    assert manifest["baseline"]["sha256"] == APPROVED_SHA256


def test_generated_outputs_are_fresh() -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts/build_handbook.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((HANDBOOK / "manifest.json").read_text("utf-8"))
    html_digest = sha256(GENERATED.read_bytes()).hexdigest()
    assert manifest["html"]["sha256"] == html_digest
    assert manifest["sheets"] == SHEETS


def test_generated_dom_matches_approved_baseline() -> None:
    baseline = _events(BASELINE)
    generated, _ = _split_annexes(_events(GENERATED))
    for index, (want, got) in enumerate(zip(baseline, generated, strict=False)):
        assert got == want, f"first DOM difference at event {index}"
    assert len(generated) == len(baseline)


def test_annex_sheets_follow_the_main_body() -> None:
    """#1138 AC6: appendix sheets come after the approved main body."""
    events = _events(GENERATED)
    main, annexes = _split_annexes(events)
    manifest = json.loads((HANDBOOK / "manifest.json").read_text("utf-8"))
    assert len(annexes) == manifest["annex_sheets"] >= 1
    first_annex = next(i for i, e in enumerate(events) if _is_annex(e))
    later = [e for e in events[first_annex:] if e[:2] == ("start", "section")]
    assert all(_is_annex(e) for e in later)
    assert sum(e[:2] == ("start", "section") for e in main) == SHEETS
    texts = [e[1] for annex in annexes for e in annex if e[0] == "text"]
    assert "附錄 B\N{FULLWIDTH COLON}範本格式" in texts
    for template in (
        "ADR",
        "Pilot 紀錄",
        "Operator-independence run",
        "合併授權留言",
        "ProjectV2 設定",
    ):
        assert template in texts, template


# Issue #1139 AC5 (owner decisions 2026-10-16): appendix B shows the
# concrete format of the key templates in execution-flow order, generated
# at build time from the authoritative sources, then a compact index.
FLOW = (
    "B.1 建立／導入",  # noqa: RUF001
    "B.2 規劃",
    "B.3 開發",
    "B.4 驗證與合併",
    "B.5 發版",
    "B.6 升級",
    "B.7 例外與事後",
    "B.8 整合",
    "B.9 索引",
)
FORMATS = (
    ("issue-form", ".github/ISSUE_TEMPLATE/task.yml"),
    ("fence", "docs/specs/SPEC-010-issue-risk-controls.md #### 風險與控制"),
    ("issue-form", ".github/ISSUE_TEMPLATE/bug.yml"),
    ("issue-form", ".github/ISSUE_TEMPLATE/feature.yml"),
    ("issue-form", ".github/ISSUE_TEMPLATE/documentation.yml"),
    ("fence", "docs/milestone-description.md ## Problem"),
    ("tracker", ""),
    ("fence", "docs/milestone-description.md ### Checkpoints"),
    ("conventions", ""),
    ("file", ".github/pull_request_template.md"),
    (
        "fence",
        "docs/specs/SPEC-010-issue-risk-controls.md ## Requirement evidence",
    ),
    ("fence", "docs/adr/README.md # Choose a durable option"),
    ("file", "template/docs/specs/SPEC-001-example.md.jinja"),
    ("authorization", ""),
    ("trailers", ""),
    ("changelog", ""),
    ("report", ""),
    ("record", "docs/ci-policy.md Hotfix 事後紀錄（#1139）"),  # noqa: RUF001
    ("record", "docs/security-response.md 私密紀錄格式"),
    ("record", "docs/pilot-adoption.md Pilot 紀錄格式"),
    ("record", "docs/pilot-adoption.md Operator-independence run"),
    ("checklist", "docs/milestone-description.md Promotion checklist"),
    (
        "section",
        "template/.csarc/docs/csarc.md.jinja Project Roadmap 設定",
    ),
)
BUILDER = runpy.run_path(str(ROOT / "scripts/build_handbook.py"))


def test_annex_shows_template_formats_in_flow_order() -> None:
    """#1139 AC5: stage headings and format blocks follow the flow."""
    source = (HANDBOOK / "handbook.md").read_text("utf-8")
    directives = re.findall(r"(?m)^::: format ([\w-]+)(?: (.+))?$", source)
    assert tuple(directives) == FORMATS

    _, annexes = _split_annexes(_events(GENERATED))
    events = [e for annex in annexes for e in annex]
    stages = [
        events[i + 1][1]
        for i, e in enumerate(events)
        if e[:2] == ("start", "h3")
    ]
    assert tuple(stages) == FLOW
    blocks = [
        events[i + 1][1]
        for i, e in enumerate(events)
        if e[:2] == ("start", "pre") and dict(e[2]).get("class") == "format"
    ]
    assert len(blocks) == len(FORMATS)
    for (kind, argument), block in zip(FORMATS, blocks, strict=True):
        expected = BUILDER["render_format"](ROOT, kind, argument)
        # The event parser collapses whitespace; compare the same way.
        assert block == " ".join(expected.split())
    # The compact index still names every template once.
    names = [
        events[i + 2][1]
        for i, e in enumerate(events)
        if e[:2] == ("start", "tr") and events[i + 1][:2] == ("start", "td")
    ]
    assert len(names) == len(set(names)) >= 39


def test_annex_formats_follow_their_sources() -> None:
    """#1139 AC5: each generated format carries its source's exact shape."""
    render = BUILDER["render_format"]
    task = render(ROOT, "issue-form", ".github/ISSUE_TEMPLATE/task.yml")
    for heading in ("### 問題", "### 完成條件", "### 補充"):
        assert heading in task
    assert "- [ ] ..." in task
    assert "#### 風險與控制" in task
    docs = render(
        ROOT, "issue-form", ".github/ISSUE_TEMPLATE/documentation.yml"
    )
    assert "| R0 | none |" in docs

    lifecycle = runpy.run_path(str(ROOT / "scripts/pr_lifecycle.py"))
    expected = lifecycle["authorization_statement"](
        "<owner>/<repository>", 987654321, "f" * 40
    )
    assert render(ROOT, "authorization", "") == expected.replace(
        "987654321", "<PR>"
    ).replace("f" * 40, "<head SHA>")

    changelog = render(ROOT, "changelog", "")
    assert changelog.startswith("## [1.1.0] - 2026-01-02")
    assert "### Features\n\n* feat(report): add a summary table (" in changelog
    assert "### Bug Fixes\n\n* fix(cli): reject an empty answer (" in changelog
    assert "docs: explain the setup" not in changelog

    trailers = render(ROOT, "trailers", "")
    policy = json.loads((ROOT / "policies/merge-trailers.json").read_text())
    keys = [line.split(":")[0] for line in trailers.splitlines()[4:]]
    assert keys == policy["order"]

    hotfix = render(
        ROOT,
        "record",
        "docs/ci-policy.md Hotfix 事後紀錄（#1139）",  # noqa: RUF001
    )
    assert [row.split(" | ")[0][2:] for row in hotfix.splitlines()[2:]] == [
        "原因",
        "影響範圍",
        "Exact base／head",  # noqa: RUF001
        "為何不能等 Milestone",
        "授權來源",
        "驗證證據",
        "後續 Issue",
    ]
    tracker = render(ROOT, "tracker", "")
    for section in ("Proposal", "Completion evidence", "Early termination"):
        assert f"## {section}" in tracker
    spec = render(ROOT, "file", "template/docs/specs/SPEC-001-example.md.jinja")
    assert "owner: <code_owner>" in spec
    assert "{{" not in spec


def test_annex_format_drift_fails_the_build(tmp_path: Path) -> None:
    """#1139 AC5: a changed source changes the generated appendix."""
    form = tmp_path / ".github/ISSUE_TEMPLATE/task.yml"
    form.parent.mkdir(parents=True)
    source = (ROOT / ".github/ISSUE_TEMPLATE/task.yml").read_text("utf-8")
    form.write_text(source.replace("label: 完成條件", "label: 驗收"), "utf-8")
    changed = BUILDER["render_format"](
        tmp_path, "issue-form", ".github/ISSUE_TEMPLATE/task.yml"
    )
    assert "### 驗收" in changed
    with pytest.raises(BUILDER["HandbookError"], match="heading not found"):
        BUILDER["render_format"](
            ROOT, "record", "docs/ci-policy.md No such heading"
        )


def test_annex_links_resolve() -> None:
    """#1138 AC6: every relative link in an annex names a real file and
    heading."""
    _, annexes = _split_annexes(_events(GENERATED))
    links = [
        dict(e[2])["href"]
        for annex in annexes
        for e in annex
        if e[:2] == ("start", "a")
    ]
    assert links
    for href in links:
        if href.startswith("https://"):
            continue
        path, _, fragment = href.partition("#")
        target = (HANDBOOK / path).resolve()
        assert target.is_file(), href
        if fragment:
            headings = re.findall(
                r"(?m)^#{1,6} +(.+?) *$", target.read_text("utf-8")
            )
            slugs = {
                re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-")
                for h in headings
            }
            assert fragment in slugs, href


def test_planned_status_and_no_consumer_identity() -> None:
    text = " ".join(e[1] for e in _events(GENERATED) if e[0] == "text")
    if _front_matter()["status"] == "planned":
        assert re.search(r"目前狀態.*M18 stable.*規劃內容", text)
    assert not re.search(r"consumer [A-Z]\b|兩個 consumer", text)


def _chrome() -> str | None:
    for name in ("google-chrome", "chromium", "chromium-browser"):
        if found := shutil.which(name):
            return found
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return str(mac) if mac.is_file() else None


_MEASURE = """<pre id="measure"></pre><script>
const boxes = [...document.querySelectorAll('.sheet, .page-content')];
document.getElementById('measure').textContent = JSON.stringify({
  sheets: document.querySelectorAll('.sheet').length,
  main: document.querySelectorAll('.sheet:not(.annex)').length,
  overflow: boxes.map((el) => Math.max(el.scrollHeight - el.clientHeight,
    el.scrollWidth - el.clientWidth)),
});
</script></body>"""


@pytest.mark.large
def test_headless_print_layout(tmp_path: Path) -> None:
    chrome = _chrome()
    if chrome is None:
        pytest.skip("no Chrome or Chromium binary found for the print check")
    flags = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox"]
    page = tmp_path / "index.html"
    page.write_text(
        GENERATED.read_text("utf-8").replace("</body>", _MEASURE), "utf-8"
    )
    dom = subprocess.run(  # noqa: S603
        [
            *flags,
            "--window-size=1400,1000",
            "--virtual-time-budget=5000",
            "--dump-dom",
            page.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout
    found = re.search(r'<pre id="measure">(.*?)</pre>', dom, re.S)
    assert found, "measurement script did not run"
    measured = json.loads(found.group(1))
    manifest = json.loads((HANDBOOK / "manifest.json").read_text("utf-8"))
    total = SHEETS + manifest["annex_sheets"]
    assert measured["main"] == SHEETS
    assert measured["sheets"] == total
    assert len(measured["overflow"]) == 2 * total
    assert max(measured["overflow"]) <= 0, measured["overflow"]

    pdf = tmp_path / "h.pdf"
    subprocess.run(  # noqa: S603
        [
            *flags,
            f"--print-to-pdf={pdf}",
            "--no-pdf-header-footer",
            GENERATED.as_uri(),
        ],
        capture_output=True,
        timeout=120,
        check=True,
    )
    pages = len(re.findall(rb"/Type\s*/Page(?!s)", pdf.read_bytes()))
    assert pages == total


def test_annex_must_follow_every_main_sheet() -> None:
    """#1138 AC6: an annex placed before a main sheet fails the build."""
    builder = runpy.run_path(str(ROOT / "scripts/build_handbook.py"))
    meta = {"footer_version": "v"}
    ordered = ["::: sheet a | A", ":::", "::: annex b | B", ":::"]
    html, main, annexes = builder["render_body"](ordered, meta)
    assert (main, annexes) == (1, 1)
    assert '<section class="sheet annex" id="b">' in html
    assert "<span>1 / 1</span>" in html
    assert "<span>附錄 1 / 1</span>" in html
    with pytest.raises(builder["HandbookError"], match="annex sheets"):
        builder["render_body"](ordered[2:] + ordered[:2], meta)
