"""The payload tool flags low backstop headroom (#1177, re-based by #1231)."""

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
        "canonical_bytes": TARGET["canonical_bytes"] - bytes_left,
    }


def test_enough_headroom_prints_no_warning() -> None:
    """One spare file and 20 KB of canonical room are enough."""
    assert generated_payload.HEADROOM_WARNING == {
        "files": 1,
        "canonical_bytes": 20_000,
    }
    results = {"solo-default": values(1, 20_000)}
    assert generated_payload.headroom_warnings(results) == []


@pytest.mark.parametrize(
    ("files_left", "bytes_left", "expected"),
    [
        (0, 60_000, "files 0 (< 1)"),
        (5, 19_999, "canonical_bytes 19,999 (< 20,000)"),
        (0, 0, "files 0 (< 1), canonical_bytes 0 (< 20,000)"),
    ],
)
def test_low_headroom_is_named(
    files_left: int, bytes_left: int, expected: str
) -> None:
    """Below one file or 20 KB of room, the fixture and measure are named."""
    results = {"solo-default": values(files_left, bytes_left)}
    (warning,) = generated_payload.headroom_warnings(results)
    assert warning.startswith("WARNING: solo-default payload headroom")
    assert expected in warning
    assert warning.endswith(". Free room before adding generated payload.")


def test_table_output_carries_the_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The table goes to stdout, the warning to stderr; exit status is 0."""
    measures = {
        **dict.fromkeys(
            (
                "write_workflows",
                "pull_request_target_workflows",
                "agent_doc_tokens",
                "bytes",
            ),
            0,
        ),
        **{f"runtime:{group}": 0 for group in generated_payload.RUNTIME_GROUPS},
        **values(0, 1),
    }
    monkeypatch.setattr(
        generated_payload,
        "measure_fixtures",
        lambda names, ref=None: {name: dict(measures) for name in names},
    )
    assert generated_payload.main(["solo-default"]) == 0
    captured = capsys.readouterr()
    assert "| solo-default |" in captured.out
    assert "| pr-lifecycle (≤ 266,000) |" in captured.out
    assert "WARNING" not in captured.out
    assert captured.err.startswith("WARNING: solo-default payload headroom")


def test_raw_targets_do_not_move() -> None:
    """The #1058 raw-bytes Targets stay frozen as the conversion source."""
    assert generated_payload.RAW_TARGETS == {
        "solo-default": 1_000_000,
        "solo-python": 1_010_000,
        "hosted-csarc-owned-python": 1_200_000,
        "consumer-a": 1_050_000,
        "consumer-b": 1_050_000,
    }
