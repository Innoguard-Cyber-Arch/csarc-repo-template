"""Regression tests for path-scoped GitHub Pages deployment."""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one mapping-only workflow."""
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    return workflow


def test_pages_deploys_committed_docs_only() -> None:
    """Avoid a Pages runner for unrelated main-branch changes."""
    root_path = ROOT / ".github/workflows/pages.yml"
    template_path = ROOT / "template/.github/workflows/pages.yml"
    source = root_path.read_text(encoding="utf-8")

    assert source == template_path.read_text(encoding="utf-8")
    workflow = load_yaml(root_path)
    triggers = workflow.get("on", workflow.get(True))
    assert triggers == {
        "push": {"branches": ["main"], "paths": ["docs/**"]},
        "workflow_dispatch": None,
    }
    assert workflow["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    steps = workflow["jobs"]["deploy"]["steps"]
    assert any(step.get("with", {}).get("path") == "docs" for step in steps)
    assert all("run" not in step for step in steps)
