"""Trusted helpers never load code or settings from the candidate (#1325).

The site build and the full verifier run trusted scripts against the
candidate tree. They must load the configuration reader and the settings
from their own checkout, keep tool versions away from the candidate's uv
settings, and import the built wheel rather than a same-named source tree.
"""

from __future__ import annotations

import os
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generated_payload  # noqa: E402

TEMPLATE_SCRIPTS = ROOT / "template/.csarc/scripts"
SITE_SCRIPTS = (
    "build_repo_site.py",
    "csarc_config.py",
    "render_site.py",
    "repo_site_blocks.py",
    "repository_facts.py",
)
FORGED_READER = (
    "from pathlib import Path\n"
    "Path(__file__).with_name('candidate-reader-ran').touch()\n"
    "raise SystemExit('candidate reader ran')\n"
)


@pytest.fixture(scope="module")
def render(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Render one hosted project for its real settings."""
    workdir = tmp_path_factory.mktemp("trusted-site")
    source = workdir / "source"
    source.mkdir()
    generated_payload.template_copy(source)
    return generated_payload.render(
        source,
        workdir / "project",
        {**generated_payload.SOLO_LOCAL, **generated_payload.HOSTED},
    )


def control_and_candidate(tmp_path: Path, render: Path) -> tuple[Path, Path]:
    """Return a control checkout and a candidate whose reader is forged."""
    control = tmp_path / "control"
    (control / ".csarc/scripts").mkdir(parents=True)
    for name in SITE_SCRIPTS:
        shutil.copy2(TEMPLATE_SCRIPTS / name, control / ".csarc/scripts" / name)
    shutil.copy2(render / ".csarc/config.yml", control / ".csarc/config.yml")
    candidate = tmp_path / "candidate"
    shutil.copytree(render, candidate)
    (candidate / ".csarc/scripts/csarc_config.py").write_text(
        FORGED_READER, encoding="utf-8"
    )
    config = candidate / ".csarc/config.yml"
    text = config.read_text(encoding="utf-8")
    assert "documentation_mode: content-only" in text
    config.write_text(
        text.replace(
            "documentation_mode: content-only", "documentation_mode: off"
        ),
        encoding="utf-8",
    )
    return control, candidate


@pytest.mark.parametrize(
    ("script", "loader"),
    [
        ("build_repo_site.py", "_load_downstream_config"),
        ("render_site.py", "_load_config"),
    ],
)
def test_site_scripts_read_settings_from_their_own_checkout(
    tmp_path: Path, render: Path, script: str, loader: str
) -> None:
    """Item 2: the candidate's reader never runs; base settings are used."""
    control, candidate = control_and_candidate(tmp_path, render)
    module = runpy.run_path(str(control / ".csarc/scripts" / script))
    config = module[loader](candidate)
    assert config is not None
    assert config["documentation_mode"] == "content-only"
    assert not (candidate / ".csarc/scripts/candidate-reader-ran").exists()


def wheel_import_check() -> str:
    """Return the rendered wheel import check for a fixture package."""
    text = (TEMPLATE_SCRIPTS / "verify.jinja").read_text(encoding="utf-8")
    match = re.search(r"^wheel_import_check='(.*?)'$", text, re.M | re.S)
    assert match is not None
    return match.group(1).replace("{{ package_name }}", "fixturepkg")


def run_import(
    tmp_path: Path, package_root: Path
) -> subprocess.CompletedProcess:
    """Import the fixture package from `package_root` the way verify does."""
    package = package_root / "fixturepkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    return subprocess.run(  # noqa: S603
        [sys.executable, "-P", "-c", wheel_import_check()],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(package_root)},
        check=False,
        capture_output=True,
        text=True,
    )


def test_wheel_import_check_rejects_a_source_tree(tmp_path: Path) -> None:
    """Item 4: a package outside site-packages fails the import check."""
    result = run_import(tmp_path, tmp_path / "src")
    assert result.returncode != 0
    assert "Package import is not from the wheel" in result.stderr


def test_wheel_import_check_accepts_an_installed_wheel(tmp_path: Path) -> None:
    """Item 4: a package under site-packages passes the import check."""
    result = run_import(tmp_path, tmp_path / "venv/lib/site-packages")
    assert result.returncode == 0, result.stderr


def test_trusted_tools_ignore_the_candidate_uv_settings() -> None:
    """Item 4: wheel and metadata checks pass --no-config and -P."""
    text = (TEMPLATE_SCRIPTS / "verify.jinja").read_text(encoding="utf-8")
    isolated = [line for line in text.splitlines() if "--isolated" in line]
    assert len(isolated) == 4
    assert all("--no-config" in line for line in isolated)
    assert text.count('python -P -c "$wheel_import_check"') == 2
    assert "platform_python=(python3 -I)" in text
