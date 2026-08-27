"""Shared pytest policy hooks."""

from __future__ import annotations

import runpy
from pathlib import Path

pytest_collection_modifyitems = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "pytest_policy.py")
)["pytest_collection_modifyitems"]
