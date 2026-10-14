"""Generated runtime boundary: product tools and lazy imports (Issue #1070).

Generated projects keep repository-template code under `.csarc/`. Product
lint, format, type check, test discovery, and coverage must not collect it,
and every rendered entry point must load without siblings that an allowed
render can omit (#1058 decisions 13 and 25).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template"
SCRIPTS = TEMPLATE / ".csarc" / "scripts"
TOOL_BIN = Path(sys.executable).parent
PROBE = """
import json
import os
import runpy
import sys

script, mode, *arguments = sys.argv[1:]
sys.argv = [script, *arguments]
# Mirror `python <script>`: the script's own directory leads sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(script)))
code = 0
try:
    runpy.run_path(script, run_name=mode)
except SystemExit as stop:
    code = stop.code or 0
sys.stdout.write("\\nCSARC-PROBE " + json.dumps(
    {"code": code, "modules": sorted(sys.modules)}
) + "\\n")
"""


def sibling_modules() -> set[str]:
    """Return every importable Python module shipped in `.csarc/scripts`."""
    return {path.stem for path in SCRIPTS.glob("*.py")}


def optional_script_paths() -> set[str]:
    """Return `.csarc/scripts` files that some allowed render omits."""
    config = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    optional: set[str] = set()
    for rule in config["_exclude"]:
        match = re.search(
            r"\{% else %\}(\.csarc/scripts/[^{]+)\{% endif %\}", rule
        )
        if match is not None:
            optional.add(match.group(1).removeprefix(".csarc/scripts/"))
    return optional


def minimal_render(tmp_path: Path) -> Path:
    """Copy the script set left when every optional script is not rendered."""
    project = tmp_path / "minimal"
    scripts = project / ".csarc" / "scripts"
    optional = optional_script_paths()
    shutil.copytree(
        SCRIPTS,
        scripts,
        ignore=shutil.ignore_patterns("*.jinja", "__pycache__"),
    )
    for name in optional:
        (scripts / name).unlink(missing_ok=True)
    (project / ".csarc" / "config.yml").write_text(
        "languages: []\nverification_mode: local\n", encoding="utf-8"
    )
    return project


def python_entries(scripts: Path) -> list[Path]:
    """Return every Python file or Python-shebang script in one script set."""
    entries: list[Path] = []
    for path in sorted(scripts.iterdir()):
        if not path.is_file():
            continue
        if path.suffix == ".py":
            entries.append(path)
            continue
        if path.suffix:
            continue
        first_line = path.read_text(encoding="utf-8").partition("\n")[0]
        if first_line.startswith("#!") and "python" in first_line:
            entries.append(path)
    return entries


def probe(
    project: Path, script: Path, mode: str, *arguments: str
) -> tuple[object, set[str]]:
    """Run or load one script and return its exit code and loaded siblings."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", PROBE, str(script), mode, *arguments],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    marker = result.stdout.rpartition("CSARC-PROBE ")[2]
    payload = json.loads(marker)
    return payload["code"], set(payload["modules"]) & sibling_modules()


def test_minimal_render_omits_the_optional_script_modules() -> None:
    """The matrix below really removes the conditional site modules."""
    assert {
        "build_repo_site.py",
        "render_site.py",
        "repo_site_blocks.py",
    } <= optional_script_paths()


def test_every_entry_loads_without_optional_siblings(tmp_path: Path) -> None:
    """Each rendered Python entry loads on the smallest allowed script set."""
    project = minimal_render(tmp_path)
    scripts = project / ".csarc" / "scripts"
    entries = python_entries(scripts)
    assert len(entries) > 20
    for entry in entries:
        code, _loaded = probe(project, entry, "csarc_import_probe")
        assert code == 0, entry.name


def test_scan_writers_loads_only_the_lifecycle_and_configuration(
    tmp_path: Path,
) -> None:
    """`pr_lifecycle.py scan-writers` needs no other sibling module."""
    project = minimal_render(tmp_path)
    code, loaded = probe(
        project,
        project / ".csarc/scripts/pr_lifecycle.py",
        "__main__",
        "scan-writers",
        "--root",
        str(project),
    )
    assert code == 0
    assert loaded == {"csarc_config"}


def test_issue_edit_loads_only_the_issue_approval_module(
    tmp_path: Path,
) -> None:
    """`gh-issue-edit` loads its approval helper and nothing else."""
    project = minimal_render(tmp_path)
    code, loaded = probe(
        project, project / ".csarc/scripts/gh-issue-edit", "csarc_import_probe"
    )
    assert code == 0
    assert "sync_milestone_state" in loaded
    assert loaded <= {"sync_milestone_state", "csarc_config"}


def test_trusted_verification_help_skips_the_lifecycle(tmp_path: Path) -> None:
    """`check-trusted-verification --help` never loads `pr_lifecycle`."""
    project = minimal_render(tmp_path)
    code, loaded = probe(
        project,
        project / ".csarc/scripts/check-trusted-verification",
        "__main__",
        "--help",
    )
    assert code == 0
    assert "pr_lifecycle" not in loaded
    assert loaded == set()


def render_text(relative: str, **context: object) -> str:
    """Render one product manifest template with Jinja only."""
    return (
        Environment(
            autoescape=False,  # noqa: S701 - trusted local TOML template
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        .from_string((TEMPLATE / relative).read_text(encoding="utf-8"))
        .render(**context)
    )


def rendered_pyproject() -> str:
    """Render the generated Python manifest for one representative project."""
    return render_text(
        "pyproject.toml.jinja",
        python_floor="latest",
        project_slug="gen-smoke",
        project_description="Generated smoke.",
        documentation_mode="content-only",
        project_license="MIT",
        repository_url="https://github.com/example/gen-smoke",
        package_name="gen_smoke",
        coverage_threshold=80,
    )


def test_product_manifests_never_name_the_control_layer() -> None:
    """Product manifests and tool configs neither include nor name `.csarc`."""
    pyproject = rendered_pyproject()
    assert ".csarc" not in pyproject
    manifest = tomllib.loads(pyproject)
    assert manifest["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert manifest["tool"]["coverage"]["run"]["source"] == ["src"]
    assert ".csarc" not in manifest["tool"]["ty"]["src"]["include"]
    for relative in (
        "Cargo.toml.jinja",
        "biome.json",
        "go.mod.jinja",
        "package.json.jinja",
        "pnpm-workspace.yaml",
        "tsconfig.build.json",
        "tsconfig.json",
        "vitest.config.ts.jinja",
    ):
        assert ".csarc" not in (TEMPLATE / relative).read_text(
            encoding="utf-8"
        ), relative


def product_tree(tmp_path: Path, manifest: str) -> Path:
    """Build a product tree whose `.csarc` code violates product rules."""
    project = tmp_path / "product"
    (project / "src/gen_smoke").mkdir(parents=True)
    (project / "tests").mkdir()
    (project / ".csarc/scripts").mkdir(parents=True)
    (project / ".csarc/tests").mkdir()
    (project / "pyproject.toml").write_text(manifest, encoding="utf-8")
    shutil.copy2(TEMPLATE / ".csarc/.ignore.jinja", project / ".csarc/.ignore")
    (project / "src/gen_smoke/__init__.py").write_text(
        '"""Product package."""\n\n__version__ = "0.1.0"\n', encoding="utf-8"
    )
    (project / "tests/test_product.py").write_text(
        '"""Product test."""\n\n\ndef test_product() -> None:\n'
        '    """Pass."""\n    assert True  # noqa: S101\n',
        encoding="utf-8",
    )
    # Unformatted, unlinted, ill-typed control-layer code and a test module.
    (project / ".csarc/scripts/control.py").write_text(
        "import os\nvalue: int = 'text'\n", encoding="utf-8"
    )
    (project / ".csarc/tests/test_control.py").write_text(
        "def test_control():\n  assert False\n", encoding="utf-8"
    )
    return project


@pytest.mark.parametrize(
    "shape",
    ["generated-manifest", "existing-product-manifest"],
)
def test_product_tools_do_not_collect_the_control_layer(
    tmp_path: Path, shape: str
) -> None:
    """Ruff, ty, and pytest skip `.csarc` even when the manifest is bare."""
    manifest = (
        rendered_pyproject()
        if shape == "generated-manifest"
        else '[project]\nname = "product"\nversion = "0.1.0"\n'
    )
    project = product_tree(tmp_path, manifest)
    ruff = [sys.executable, "-m", "ruff"]
    ty = TOOL_BIN / "ty"
    if not ty.is_file():
        pytest.skip("ty is unavailable in this environment")

    files = subprocess.run(  # noqa: S603
        [*ruff, "check", "--show-files", "."],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert ".csarc" not in files
    assert "src/gen_smoke/__init__.py" in files
    for command in (
        [*ruff, "check", "--select", "F,E", "."],
        [*ruff, "format", "--check", "."],
        [str(ty), "check", "--python", sys.executable],
    ):
        result = subprocess.run(  # noqa: S603
            command, cwd=project, check=False, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert ".csarc" not in result.stdout + result.stderr

    collected = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "tests/test_product.py" in collected
    assert ".csarc" not in collected
