"""Template self-tests run in template CI against real renders (#1070).

Generated `verify` and `verify-fast` no longer run the repository-template
self-tests (#1058 decision 13). This module keeps every one of those cases
in the template's own full tier, proves fresh renders keep template-owned
files inside `.csarc/` or an ADR fixed location, and runs representative
renders through their own generated verifier.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
from copier import run_copy
from test_generated_layout_allowlist import allowlist

pytestmark = pytest.mark.large

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git") or "git"
BASE_DATA = {
    "project_name": "Self Test Fixture",
    "project_slug": "self-test-fixture",
    "project_description": "Exercises the template self-tests.",
    "repository_url": "https://github.com/example/self-test-fixture",
    "security_reporting_channel": "Use the private security contact.",
}
# Case counts each self-test reported when generated verify still ran it.
# A self-test may add cases but never drop below its baseline.
SELF_TEST_BASELINE: dict[str, list[int]] = {
    "test-apply-repository-settings": [11],
    "test-check-scope-gate": [7],
    "test-finalization-queue": [6],
    "test-issue-triage": [10, 12],
    "test-pr-policy": [134],
    "test-worktree-cleanup": [8],
}
CSARC_PYTEST_BASELINE = 46


@pytest.fixture(scope="module")
def template_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy the working-tree template so Copier renders uncommitted edits."""
    source = tmp_path_factory.mktemp("template-source")
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(
        ROOT / "template",
        source / "template",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return source


def git(project: Path, *arguments: str) -> str:
    """Run one Git command in a rendered project."""
    return subprocess.run(  # noqa: S603
        [GIT, *arguments],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def render(
    source: Path, target: Path, *, tasks: bool = False, **data: object
) -> Path:
    """Render one project and commit it as the candidate under test."""
    run_copy(
        str(source),
        target,
        data={**BASE_DATA, **data},
        defaults=True,
        unsafe=True,
        skip_tasks=not tasks,
        quiet=True,
    )
    git(target, "init", "-q", "-b", "main")
    git(target, "add", "-A")
    git(
        target,
        "-c",
        "user.name=Self Test",
        "-c",
        "user.email=self-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "test: rendered project",
    )
    git(target, "config", "branch.main.gh-merge-base", "main")
    return target


SELF_TESTS = ROOT / "tests/generated_self_tests"


def install_self_tests(project: Path) -> list[str]:
    """Copy the template-owned self-tests into one rendered project."""
    for script in (SELF_TESTS / "scripts").iterdir():
        shutil.copy2(script, project / ".csarc/scripts" / script.name)
    shutil.copytree(SELF_TESTS / "csarc_tests", project / ".csarc/tests")
    git(project, "add", "-A")
    git(
        project,
        "-c",
        "user.name=Self Test",
        "-c",
        "user.email=self-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "test: install template self-tests",
    )
    return sorted(path.name for path in (SELF_TESTS / "scripts").iterdir())


def output_tail(result: subprocess.CompletedProcess[str]) -> str:
    """Return the end of one command's combined output for failures."""
    return (result.stdout + result.stderr)[-4000:]


def test_template_self_tests_keep_every_case_in_template_ci(
    template_source: Path, tmp_path: Path
) -> None:
    """Run each self-test against a full render; no case is lost.

    Generated projects never ship these self-tests (#1077); template CI
    installs them into a render whose options enable every script they
    exercise.
    """
    project = render(
        template_source,
        tmp_path / "default",
        verification_mode="hosted",
        lifecycle=["issues", "milestones"],
        release_ownership="csarc-owned",
    )
    assert not list((project / ".csarc/scripts").glob("test-*"))
    assert not (project / ".csarc/tests").exists()
    assert not (project / ".csarc/scripts/security-smoke").exists()
    shipped = install_self_tests(project)
    assert shipped == sorted(SELF_TEST_BASELINE)

    for name, minimums in SELF_TEST_BASELINE.items():
        result = subprocess.run(  # noqa: S603
            [project / ".csarc/scripts" / name],
            cwd=project,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{name}:\n{output_tail(result)}"
        counts = [
            int(count)
            for count in re.findall(
                r"cases passed: (\d+)", result.stdout + result.stderr
            )
        ]
        assert len(counts) == len(minimums), name
        assert all(
            count >= minimum
            for count, minimum in zip(counts, minimums, strict=True)
        ), (name, counts, minimums)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            ".csarc/tests",
        ],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, output_tail(result)
    passed = re.search(r"(\d+) passed", result.stdout)
    assert passed is not None
    assert int(passed.group(1)) >= CSARC_PYTEST_BASELINE


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("default", {}),
        ("documentation-off", {"documentation_mode": "off"}),
        (
            "every-option",
            {
                "languages": ["go", "python", "rust", "typescript"],
                "features": ["docker"],
                "verification_mode": "hosted",
                "enable_codeql": True,
                "enable_precommit": True,
                "enable_template_update_notifications": True,
                "code_owner": "@example",
                "project_visibility": "public",
                "security_reporting_channel": "security@example.com",
            },
        ),
    ],
)
def test_fresh_renders_keep_template_files_in_the_control_layer(
    template_source: Path, tmp_path: Path, name: str, data: dict[str, object]
) -> None:
    """Outside `.csarc/`, a render creates only ADR-allowlisted paths."""
    project = render(template_source, tmp_path / name, **data)
    patterns = allowlist()
    outside = [
        path.relative_to(project).as_posix()
        for path in project.rglob("*")
        if path.is_file()
        and path.relative_to(project).parts[0] not in {".git", ".csarc"}
    ]
    assert outside
    assert [
        path
        for path in outside
        if not any(fnmatchcase(path, pattern) for pattern in patterns)
    ] == []
    assert not (project / "scripts").exists()
    assert sorted(path.name for path in (project / "tests").glob("*")) in (
        [],
        ["test_smoke.py"],
    )


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("documentation-off", {"documentation_mode": "off"}),
        (
            "issues-only-product-release",
            {
                "lifecycle": ["issues"],
                "release_ownership": "product-owned",
                "verification_mode": "hosted",
            },
        ),
        (
            "no-lifecycle-verification-only",
            {"lifecycle": [], "release_ownership": "verification-only"},
        ),
    ],
)
def test_representative_render_passes_its_own_verifier(
    template_source: Path, tmp_path: Path, name: str, data: dict[str, object]
) -> None:
    """Allowed renders verify themselves without template self-tests."""
    if shutil.which("uv") is None:
        pytest.skip("uv is unavailable in this environment")
    # Copier tasks build the documentation site a CI-only render verifies.
    project = render(
        template_source, tmp_path / name, tasks=True, languages=[], **data
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CSARC_", "VIRTUAL_ENV", "PYTEST_"))
    }
    environment["CSARC_CI_BASE"] = git(project, "rev-parse", "HEAD")
    result = subprocess.run(  # noqa: S603
        [project / ".csarc/scripts/verify"],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, output_tail(result)
    assert "cases passed" not in combined
    assert "PR policy regression" not in combined
