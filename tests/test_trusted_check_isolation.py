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
import yaml

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


def workflow_step(workflow: Path, name: str) -> str:
    """Return the `run` script of the step named exactly so."""
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    scripts = [
        item["run"]
        for job in document["jobs"].values()
        for item in job.get("steps", [])
        if item.get("name") == name
    ]
    assert len(scripts) == 1, (workflow, name)
    return scripts[0]


def run_bash(
    script: str, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess:
    """Run one workflow step the way GitHub Actions runs `bash`."""
    return subprocess.run(  # noqa: S603
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],  # noqa: S607
        cwd=cwd,
        env={**os.environ, **env},
        check=False,
        capture_output=True,
        text=True,
    )


def test_hosted_release_ownership_comes_from_the_trusted_base(
    tmp_path: Path, render: Path
) -> None:
    """A candidate cannot skip the release checks by changing ownership."""
    base = tmp_path / "base"
    shutil.copytree(render, base)
    candidate = tmp_path / "candidate"
    shutil.copytree(render, candidate)
    config = candidate / ".csarc/config.yml"
    text = config.read_text(encoding="utf-8")
    owned = re.search(r"^release_ownership: (\S+)$", text, re.M)
    assert owned is not None
    other = (
        "verification-only"
        if owned[1] != "verification-only"
        else "csarc-owned"
    )
    config.write_text(
        text.replace(owned[0], f"release_ownership: {other}"), "utf-8"
    )
    runner = tmp_path / "runner"
    runner.mkdir()
    output = tmp_path / "output"
    common = {"RUNNER_TEMP": str(runner), "GITHUB_OUTPUT": str(output)}
    workflow = base / ".github/workflows/ci.yml"
    preserved = run_bash(
        workflow_step(workflow, "Preserve the trusted verification policy"),
        base,
        {**common, "GITHUB_WORKSPACE": str(base), "GUIDED_RELEASE": "false"},
    )
    assert preserved.returncode == 0, preserved.stderr
    output.write_text("", encoding="utf-8")
    read = run_bash(
        workflow_step(workflow, "Read release ownership"),
        candidate,
        {**common, "GITHUB_WORKSPACE": str(candidate)},
    )
    assert read.returncode == 0, read.stderr
    assert output.read_text(encoding="utf-8") == f"ownership={owned[1]}\n"


def test_root_ci_reads_release_ownership_from_the_base() -> None:
    """The root workflow stages and reads the same base settings."""
    workflow = ROOT / ".github/workflows/ci.yml"
    preserve = workflow_step(
        workflow, "Preserve the trusted verification policy"
    )
    read = workflow_step(workflow, "Read release ownership")
    staged = "$RUNNER_TEMP/trusted-verification/base-config.yml"
    assert f'cp .csarc/config.yml "{staged}"' in preserve
    assert f'--config "{staged}" release_ownership' in read


def test_lower_bound_tests_ignore_a_candidate_pytest(tmp_path: Path) -> None:
    """A candidate pytest.py never replaces the runner under -P."""
    (tmp_path / "pytest.py").write_text(
        "raise SystemExit('ERROR: candidate pytest ran')\n", encoding="utf-8"
    )
    plain = subprocess.run(
        [sys.executable, "-m", "pytest", "--version"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert "candidate pytest ran" in plain.stderr
    isolated = subprocess.run(
        [sys.executable, "-P", "-m", "pytest", "--version"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert isolated.returncode == 0, isolated.stderr
    text = (TEMPLATE_SCRIPTS / "verify.jinja").read_text(encoding="utf-8")
    assert text.count('/.venv/bin/python" -P -m pytest') == 2
    assert '/.venv/bin/python" -m pytest' not in text


@pytest.mark.parametrize(("version_ok", "status"), [(True, 0), (False, 2)])
def test_entry_points_require_a_recent_python(
    tmp_path: Path, version_ok: bool, status: int
) -> None:
    """An old python3 stops verification with a clear error."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "python3"
    fake.write_text(f"#!/bin/sh\nexit {0 if version_ok else 1}\n", "utf-8")
    fake.chmod(0o755)
    step_file = TEMPLATE_SCRIPTS / "verification-step"
    result = subprocess.run(  # noqa: S603
        ["bash", "-c", f'source "{step_file}"; verification_require_python'],  # noqa: S607
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == status
    assert ("ERROR: Python is too old" in result.stderr) is (not version_ok)
    for name in ("verify-fast.jinja", "verify.jinja"):
        entry = (TEMPLATE_SCRIPTS / name).read_text(encoding="utf-8")
        assert "\nverification_require_python\n" in entry, name


@pytest.mark.parametrize(
    "script",
    ["scripts/pr_lifecycle.py", "template/.csarc/scripts/pr_lifecycle.py"],
)
def test_lifecycle_route_reads_base_settings_from_the_base_commit(
    script: str,
) -> None:
    """The route never compares the candidate's settings with themselves."""
    text = (ROOT / script).read_text(encoding="utf-8")
    assert 'f"{base_sha}:.csarc/config.yml"' in text
    assert 'base_config = repository_root() / ".csarc/config.yml"' not in text
