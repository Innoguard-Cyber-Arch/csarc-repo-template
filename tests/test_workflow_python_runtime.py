"""Workflow-executed scripts must run on an interpreter that parses them.

Issue #1111: the hosted `verify` job ran `python3 scripts/trusted_executor.py`
on the runner's system Python before `actions/setup-python`, and the script
used Python 3.14-only PEP 758 `except A, B:` syntax, so every pull request
failed with a SyntaxError. Issue #483 hit the same class of bug earlier.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

# Workflow steps run these directories with whatever `python3` the runner
# provides (some workflows never call setup-python), so keep them parseable
# on the oldest supported runner interpreter.
SYSTEM_PYTHON_SCRIPT_DIRS = ("scripts", "template/.csarc/scripts")
SYSTEM_PYTHON_GRAMMAR = (3, 12)


def _python_sources() -> list[Path]:
    sources: list[Path] = []
    for directory in SYSTEM_PYTHON_SCRIPT_DIRS:
        for path in sorted((ROOT / directory).iterdir()):
            if not path.is_file():
                continue
            if path.suffix == ".py":
                sources.append(path)
                continue
            with path.open("rb") as handle:
                first_line = handle.readline()
            if first_line.startswith(b"#!") and b"python" in first_line:
                sources.append(path)
    return sources


@pytest.mark.parametrize(
    "path",
    _python_sources(),
    ids=lambda path: str(path.relative_to(ROOT)),
)
def test_workflow_executed_script_parses_on_system_python(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path), feature_version=SYSTEM_PYTHON_GRAMMAR)


def test_system_python_grammar_check_rejects_pep_758_except() -> None:
    with pytest.raises(SyntaxError):
        ast.parse(
            "try:\n    pass\nexcept OSError, ValueError:\n    pass\n",
            feature_version=SYSTEM_PYTHON_GRAMMAR,
        )


def test_ruff_targets_system_python_for_workflow_scripts() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    per_file = pyproject["tool"]["ruff"]["per-file-target-version"]
    for directory in SYSTEM_PYTHON_SCRIPT_DIRS:
        assert per_file[f"{directory}/**"] == "py312"


def _steps(workflow: str, job: str) -> list[dict[str, Any]]:
    path = ROOT / ".github" / "workflows" / workflow
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document["jobs"][job]["steps"]


def test_verify_sets_up_python_before_any_trusted_python_step() -> None:
    steps = _steps("ci.yml", "verify")
    first_python = next(
        index
        for index, step in enumerate(steps)
        if "python3 " in str(step.get("run", ""))
    )
    setups = [
        index
        for index, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("actions/setup-python@")
    ]
    assert setups, "verify must set up Python"
    early = steps[setups[0]]
    assert setups[0] < first_python, (
        "actions/setup-python must run before the first python3 step "
        f"({steps[first_python]['name']!r})"
    )
    assert "if" not in early, "the early Python setup must be unconditional"
    assert early["with"]["python-version"] == "3.14"
