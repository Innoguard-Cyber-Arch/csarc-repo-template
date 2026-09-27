"""Tests for carrying Dependabot Actions pins into templates (#1052)."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

pins = importlib.import_module("sync_template_action_pins")

OLD = "d0cc045d04ccac9017b7ba5a3fd1e2cd4e4d5a0d"
NEW = "c18668ad3cf93ea998bef934396af7bb5c839dc7"
OTHER = "3d3c42e5aac5ba805825da76410c181273ba90b1"


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", *arguments],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _workflow(sha: str, tag: str) -> str:
    return (
        "jobs:\n  build:\n    steps:\n"
        f"      - uses: actions/checkout@{OTHER} # v7.0.1\n"
        f"      - uses: astral-sh/setup-uv@{sha} # {tag}\n"
    )


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")
    _write(root, ".github/workflows/ci.yml", _workflow(OLD, "v10.1.0"))
    _write(
        root,
        "template/.github/workflows/ci.yml.jinja",
        "{% if python %}\n"
        + _workflow(OLD, "v10.1.0")
        + "        with:\n          version: {{ uv }}\n{% endif %}\n",
    )
    _write(
        root,
        "template/.github/workflows/release.yml.jinja",
        f"      - uses: astral-sh/setup-uv@{OTHER} # v9.0.0\n",
    )
    _git(root, "add", "--all")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    _write(root, ".github/workflows/ci.yml", _workflow(NEW, "v10.2.0"))
    _git(root, "commit", "-q", "-am", "build(deps): bump setup-uv")
    return root, base, _git(root, "rev-parse", "HEAD")


def test_jinja_workflows_receive_the_exact_root_pin(tmp_path: Path) -> None:
    """Only lines using the exact old pin move; Jinja stays intact."""
    root, base, head = _repository(tmp_path)

    edited = pins.sync(root, base, head)

    jinja = (root / "template/.github/workflows/ci.yml.jinja").read_text(
        encoding="utf-8"
    )
    assert [path.name for path in edited] == ["ci.yml.jinja"]
    assert f"astral-sh/setup-uv@{NEW} # v10.2.0" in jinja
    assert OLD not in jinja
    assert f"actions/checkout@{OTHER} # v7.0.1" in jinja
    assert "{% if python %}" in jinja
    assert "{{ uv }}" in jinja
    # A different, already-stale pin is not guessed into the new one.
    release = (root / "template/.github/workflows/release.yml.jinja").read_text(
        encoding="utf-8"
    )
    assert release == f"      - uses: astral-sh/setup-uv@{OTHER} # v9.0.0\n"


def test_no_pin_change_leaves_templates_untouched(tmp_path: Path) -> None:
    root, base, _ = _repository(tmp_path)

    assert pins.sync(root, base, base) == []


def test_an_ambiguous_root_bump_fails_closed() -> None:
    """Two different new pins for one action cannot choose a template pin."""
    before = [_workflow(OLD, "v10.1.0")]
    after = [_workflow(NEW, "v10.2.0"), _workflow(OTHER, "v10.3.0")]

    with pytest.raises(pins.AmbiguousPinError, match="astral-sh/setup-uv"):
        pins.pin_changes(before, after)


def test_rewrite_preserves_list_markers_and_line_endings() -> None:
    changes = {"astral-sh/setup-uv": ((OLD, "v10.1.0"), (NEW, "v10.2.0"))}
    text = f"  - uses: astral-sh/setup-uv@{OLD}   # v10.1.0\r\n"

    assert pins.rewrite(text, changes) == (
        f"  - uses: astral-sh/setup-uv@{NEW}   # v10.2.0\r\n"
    )


def test_cli_reports_edited_paths(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    root, base, head = _repository(tmp_path)

    exit_code = pins.main(
        ["--root", str(root), "--base-rev", base, "--head-rev", head]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "template/.github/workflows/ci.yml.jinja\n"
    )
