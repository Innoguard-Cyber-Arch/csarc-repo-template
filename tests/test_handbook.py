"""Handbook source, generated page and print layout (Issue #1081).

AC1: the owner-approved r2 baseline is kept byte-for-byte and its digest is
pinned. AC2: the Markdown source renders to a page whose visible content and
structure equal the baseline, carries the planned status and names no
consumer. AC6: the generated page still prints as 10 A4 sheets with no
overflow.

An approved handbook edit replaces the baseline copy under
docs/handbook/approved/ (with a new owner approval and digest) in the same
change, so the DOM parity check below always compares against the version
the owner approved.
"""

from __future__ import annotations

import json
import re
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
    baseline, generated = _events(BASELINE), _events(GENERATED)
    for index, (want, got) in enumerate(zip(baseline, generated, strict=False)):
        assert got == want, f"first DOM difference at event {index}"
    assert len(generated) == len(baseline)


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
    assert measured["sheets"] == SHEETS
    assert len(measured["overflow"]) == 2 * SHEETS
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
    assert pages == SHEETS
