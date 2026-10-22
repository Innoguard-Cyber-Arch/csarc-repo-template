"""The payload tool flags low headroom under the #1058 Targets (#1177)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generated_payload  # noqa: E402

TARGET = generated_payload.TARGETS["solo-default"]


def values(files_left: int, bytes_left: int) -> dict[str, int]:
    """Return solo-default measures that leave the given headroom."""
    return {
        "files": TARGET["files"] - files_left,
        "bytes": TARGET["bytes"] - bytes_left,
    }


def test_enough_headroom_prints_no_warning() -> None:
    """One spare file and 20 KB of room are enough."""
    assert generated_payload.HEADROOM_WARNING == {"files": 1, "bytes": 20_000}
    results = {"solo-default": values(1, 20_000)}
    assert generated_payload.headroom_warnings(results) == []


@pytest.mark.parametrize(
    ("files_left", "bytes_left", "expected"),
    [
        (0, 60_000, "files 0 (< 1)"),
        (5, 19_999, "bytes 19,999 (< 20,000)"),
        (0, 0, "files 0 (< 1), bytes 0 (< 20,000)"),
    ],
)
def test_low_headroom_is_named(
    files_left: int, bytes_left: int, expected: str
) -> None:
    """Below one file or 20 KB of room, the fixture and measure are named."""
    results = {"solo-default": values(files_left, bytes_left)}
    (warning,) = generated_payload.headroom_warnings(results)
    assert warning.startswith("WARNING: solo-default headroom")
    assert expected in warning


def test_table_output_carries_the_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The printed table ends with the warning; the exit status stays 0."""
    monkeypatch.setattr(
        generated_payload,
        "measure_fixtures",
        lambda names: {
            name: {
                **dict.fromkeys(
                    ("scripts", "script_lines", "workflows", "docs_lines"), 0
                ),
                "docs_bytes": 0,
                **values(0, 1),
            }
            for name in names
        },
    )
    assert generated_payload.main(["solo-default"]) == 0
    output = capsys.readouterr().out
    assert "| solo-default |" in output
    assert output.rstrip().endswith(
        "free room before adding generated payload."
    )
    assert "WARNING: solo-default headroom" in output


def test_targets_do_not_move() -> None:
    """The warning leaves every Target exactly as #1058 approved it."""
    assert generated_payload.TARGETS["solo-default"] == {
        "files": 92,
        "bytes": 1_000_000,
    }
    assert generated_payload.TARGETS["solo-python"] == {
        "files": 95,
        "bytes": 1_010_000,
    }
