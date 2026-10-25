"""Hosted renders omit the local evidence tool (Issue #1267).

Only local verification records and requires self-attested evidence, so
`local_verification.py` renders only when `verification_mode` is not
`hosted`. The record contract both modes share lives in
`evidence_freshness.py`, which every render receives; `local_verification.py`
keeps the same names as aliases, so local callers see no change.
"""

from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generated_payload  # noqa: E402

LOCAL_TOOL = ".csarc/scripts/local_verification.py"
SHARED = ".csarc/scripts/evidence_freshness.py"
SHARED_NAMES = (
    "normalized_record",
    "TRUST_LOCAL",
    "TRUST_HOSTED",
    "RECORD_KEYS",
    "RECORD_TIERS",
)
HOSTED_FIXTURES = ("hosted-csarc-owned-python", "consumer-a", "consumer-b")
# SPEC-011: a self-hosted render ships the local tool too.
LOCAL_FIXTURES = ("solo-default", "solo-self-hosted", "solo-python")


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Render every payload fixture once from the working-tree template."""
    workdir = tmp_path_factory.mktemp("local-verification-render")
    source = workdir / "source"
    source.mkdir()
    generated_payload.template_copy(source)
    return {
        name: generated_payload.render(source, workdir / name, data)
        for name, data in generated_payload.FIXTURES.items()
    }


def load(project: Path, relative: str) -> ModuleType:
    """Import one rendered script as a module from its own directory."""
    path = project / relative
    scripts = str(path.parent)
    sys.path.insert(0, scripts)
    try:
        spec = importlib.util.spec_from_file_location(
            f"render_{project.name.replace('-', '_')}_{path.stem}", path
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts)
        for name in ("csarc_config", "evidence_freshness"):
            sys.modules.pop(name, None)


def evidence() -> dict[str, object]:
    """Return one valid local evidence payload."""
    return {
        "head_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "base_ref": "main",
        "base_sha": "c" * 40,
        "tier": "full",
        "scopes": ["source"],
        "command": "./.csarc/scripts/verify-fast",
        "completed_at": "2026-10-25T00:00:00Z",
    }


@pytest.mark.parametrize("name", LOCAL_FIXTURES)
def test_local_render_keeps_the_local_evidence_tool(
    rendered: dict[str, Path], name: str
) -> None:
    """R2: a local project still records and requires local evidence."""
    project = rendered[name]
    assert (project / LOCAL_TOOL).is_file()
    for script in ("verify", "verify-fast"):
        text = (project / ".csarc/scripts" / script).read_text(encoding="utf-8")
        assert "local_verification.py record" in text, script
    tool = load(project, LOCAL_TOOL)
    shared = load(project, SHARED)
    for attribute in ("record", "require", "evidence_path", "main"):
        assert callable(getattr(tool, attribute)), attribute
    for attribute in SHARED_NAMES[1:]:
        assert getattr(tool, attribute) == getattr(shared, attribute)
    record = tool.normalized_record(evidence(), tool.TRUST_LOCAL)
    assert record == shared.normalized_record(evidence(), shared.TRUST_LOCAL)
    assert set(record) == tool.RECORD_KEYS


@pytest.mark.parametrize("name", HOSTED_FIXTURES)
def test_hosted_render_omits_the_local_evidence_tool(
    rendered: dict[str, Path], name: str
) -> None:
    """AC3: hosted needs only the shared record, never the local tool."""
    project = rendered[name]
    assert not (project / LOCAL_TOOL).exists()
    scripts = project / ".csarc/scripts"
    for path in sorted(scripts.iterdir()):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "local_verification.py record" not in text, path.name
    shared = load(project, SHARED)
    for attribute in SHARED_NAMES:
        assert hasattr(shared, attribute), attribute
    hosted = shared.normalized_record(evidence(), shared.TRUST_HOSTED)
    assert hosted["trust"] == "github-hosted"
    with pytest.raises(RuntimeError, match="Bad trust label"):
        shared.normalized_record(
            {**evidence(), "trust": shared.TRUST_LOCAL}, shared.TRUST_HOSTED
        )


@pytest.mark.parametrize("name", [*LOCAL_FIXTURES, *HOSTED_FIXTURES])
def test_lifecycle_reads_the_record_from_the_shared_module(
    rendered: dict[str, Path], name: str
) -> None:
    """R2: merge snapshots in both modes resolve the shared record."""
    project = rendered[name]
    path = project / ".csarc/scripts/pr_lifecycle.py"
    source = path.read_text(encoding="utf-8")
    assert "local_verification.normalized_record" not in source
    assert "local_verification.TRUST_" not in source
    assert source.count("evidence_freshness.normalized_record(") == 2
    lifecycle = runpy.run_path(str(path), run_name="render_lifecycle")
    sibling = lifecycle["evidence_freshness"]
    assert sibling.TRUST_HOSTED == "github-hosted"
    assert sibling.TRUST_LOCAL == "self-attested-local"
