"""Hosted and VM verification run the trusted base's checks (Issue #1325).

Hosted CI (`ci.yml`) and the self-hosted VM (`csarc-verify.yml`) stage a
control set from the trusted base before they check out the candidate. The
control set now carries every check script and the base's settings, so a
candidate that turns one of its own checks into `exit 0` still fails. These
tests run the rendered workflow steps themselves, in both renders, against a
fixture repository.
"""

from __future__ import annotations

import os
import re
import runpy
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generated_payload  # noqa: E402

BRANCH = "fix/7-quiet-checks"
SELF_HOSTED = {
    **generated_payload.SOLO_SELF_HOSTED,
    "project_visibility": "private",
    "security_reporting_channel": "security@example.com",
}
HOSTED = {**generated_payload.SOLO_LOCAL, **generated_payload.HOSTED}
# Each route: the render, its workflow, the execute step's name prefix, and
# the execute step's environment as the workflow resolves it. A change under
# .csarc/scripts selects the full tier, so the full entry point runs.
ROUTES = {
    "hosted": (
        HOSTED,
        "ci.yml",
        "Execute trusted verification",
        {
            "CSARC_CI_BASE": "main",
            "CSARC_CI_DRAFT": "false",
            "CSARC_CI_SCOPES": "",
            "CSARC_CI_TIER": "full",
            "CSARC_VERIFICATION_SUITE": "full",
            "EXECUTOR": "trusted-base",
        },
    ),
    "self-hosted": (
        SELF_HOSTED,
        "csarc-verify.yml",
        "Execute self-hosted verification",
        {
            "CSARC_CI_BASE": "main",
            "CSARC_CI_LABELS": "",
            "CSARC_CI_SCOPES": "",
            "CSARC_CI_TIER": "fast",
            "CSARC_SELF_HOSTED_VM": "true",
            "CSARC_VERIFICATION_SUITE": "fast",
        },
    ),
}
PRESERVE = "Preserve the trusted verification policy"
# Checks a candidate silences; only the conflict check sees the planted
# marker, the others are silenced so the fallback run needs no network.
SILENCED = (
    "check-update-conflicts",
    "lint-workflows-shell",
    "scan-secrets",
    "verify-dependencies",
)
CONFLICT = "ERROR: Update conflict"


def git(repo: Path, *args: str) -> str:
    """Run Git in one fixture repository."""
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def step(workflow: Path, prefix: str) -> str:
    """Return the `run` script of the one step whose name starts so."""
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    scripts = [
        item["run"]
        for job in document["jobs"].values()
        for item in job.get("steps", [])
        if str(item.get("name", "")).startswith(prefix)
    ]
    assert len(scripts) == 1, (workflow.name, prefix, len(scripts))
    return scripts[0]


def run_step(
    script: str, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run one workflow step the way GitHub Actions runs `bash`."""
    clean = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CSARC_", "GITHUB_", "RUNNER_"))
    }
    return subprocess.run(  # noqa: S603
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],  # noqa: S607
        cwd=cwd,
        env={**clean, **env},
        check=False,
        capture_output=True,
        text=True,
    )


def silence_checks(repo: Path) -> None:
    """Plant a conflict marker and make the candidate's own checks pass."""
    for name in SILENCED:
        script = repo / ".csarc/scripts" / name
        assert script.is_file(), name
        script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (repo / ".csarc/notes.txt").write_text(
        "<<<<<<< ours\nkept\n=======\ndropped\n>>>>>>> theirs\n",
        encoding="utf-8",
    )


def fall_back_to_candidate(base: Path) -> None:
    """Make the base entry points read checks from the candidate (pre-#1325)."""
    trusted = 'check_root="$control_root"\n'
    for name in ("verify-fast", "verify"):
        script = base / ".csarc/scripts" / name
        text = script.read_text(encoding="utf-8")
        assert text.count(trusted) == 1, name
        script.write_text(
            text.replace(trusted, 'check_root="$repo_root"\n'),
            encoding="utf-8",
        )


TEMPLATE_SCRIPTS = ROOT / "template/.csarc/scripts"
CHECK_REFERENCE = re.compile(r'"\$checks"?/([A-Za-z0-9_.-]+)')


def test_control_set_carries_every_check_the_entry_points_run(
    tmp_path: Path,
) -> None:
    """AC1: each `$checks/<name>` the entry points run is staged from base.

    The entry points take checks only from their control root, so a local
    run, where the control root is the subject, is unchanged.
    """
    executor = runpy.run_path(str(TEMPLATE_SCRIPTS / "trusted_executor.py"))
    base = tmp_path / "base"
    scripts = base / ".csarc/scripts"
    scripts.mkdir(parents=True)
    for source in TEMPLATE_SCRIPTS.iterdir():
        if source.is_file():
            shutil.copy2(source, scripts / source.name.removesuffix(".jinja"))
    (base / ".csarc/config.yml").write_text("schema: base\n", "utf-8")
    staged = tmp_path / "staged"
    files = executor["prepare"](base, staged)

    referenced: set[str] = set()
    for name in ("verify-fast.jinja", "verify.jinja"):
        text = (TEMPLATE_SCRIPTS / name).read_text(encoding="utf-8")
        assert 'check_root="$control_root"\n' in text, name
        assert "verification_check_root" not in text, name
        referenced.update(CHECK_REFERENCE.findall(text))
    assert {"check-update-conflicts", "scan-secrets"} <= referenced
    for name in referenced:
        assert f".csarc/scripts/{name}" in files, name
        assert (staged / ".csarc/scripts" / name).is_file(), name
    assert ".csarc/config.yml" in files
    executor["verify_manifest"](staged)


def test_control_set_rejects_a_symlinked_check(tmp_path: Path) -> None:
    """A base check that is a symbolic link never yields a partial set."""
    executor = runpy.run_path(str(TEMPLATE_SCRIPTS / "trusted_executor.py"))
    base = tmp_path / "base"
    scripts = base / ".csarc/scripts"
    scripts.mkdir(parents=True)
    for relative in executor["GENERATED_CONTROL_FILES"]:
        (base / relative).write_text("trusted\n", "utf-8")
    (base / ".csarc/config.yml").write_text("schema: base\n", "utf-8")
    (tmp_path / "elsewhere").write_text("exit 0\n", "utf-8")
    (scripts / "scan-secrets").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(RuntimeError, match="scan-secrets"):
        executor["prepare"](base, tmp_path / "staged")
    assert not (tmp_path / "staged").exists()


SOURCE_DOCUMENTS = (
    "docs/adr/self-hosted-verification.md",
    "docs/ci-policy.md",
    "docs/specs/SPEC-011-verification-mode-settings.md",
    "template/.csarc/docs/ci-policy.md.jinja",
)


@pytest.mark.parametrize("document", SOURCE_DOCUMENTS)
def test_documents_name_who_supplies_checks_and_tests(document: str) -> None:
    """AC3: each record states the source of checks, settings and tests."""
    text = (ROOT / document).read_text(encoding="utf-8")
    # A generated document never carries a template Issue number (#1329).
    assert ("#1325" in text) is not document.startswith("template/")
    assert ".csarc/config.yml" in text
    assert "測試、lint 設定" in text
    assert "verification hook" in text
    assert "release_ownership" in text
    assert "只搬入幾個入口檔" not in text


@pytest.mark.parametrize(
    "document", ["docs/adr/self-hosted-verification.md", "docs/ci-policy.md"]
)
def test_source_table_covers_the_three_runs(document: str) -> None:
    """AC3: the local, base-verifier, hosted and VM runs each have a row."""
    lines = (ROOT / document).read_text(encoding="utf-8").splitlines()
    header = "| 執行 | 入口與檢查腳本 | 決定要跑哪些步驟的設定 |"
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    runs: dict[str, list[str]] = {}
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        run, *cells = (cell.strip() for cell in line.strip("|").split("|"))
        runs[run] = cells
    local = next(cells for run, cells in runs.items() if "檢查自己" in run)
    assert local == ["candidate"] * 3
    trusted = [cells for run, cells in runs.items() if "檢查自己" not in run]
    assert len(trusted) >= 2
    for cells in trusted:
        assert "candidate" not in cells[0] and "base" in cells[0]
        assert "base" in cells[1]
        assert cells[2] == "candidate"
    assert any("hosted CI" in run for run in runs)
    assert any("VM" in run for run in runs)


@pytest.fixture(scope="module")
def renders(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Render the hosted and the self-hosted project once."""
    workdir = tmp_path_factory.mktemp("trusted-checks")
    source = workdir / "source"
    source.mkdir()
    generated_payload.template_copy(source)
    return {
        name: generated_payload.render(source, workdir / name, data)
        for name, (data, *_rest) in ROUTES.items()
    }


def verify_route(
    tmp_path: Path,
    render: Path,
    route: str,
    change_base: Callable[[Path], None] | None = None,
    change_candidate: Callable[[Path], None] | None = None,
    tier: str = "full",
) -> subprocess.CompletedProcess[str]:
    """Stage the base like the workflow, then verify the changed candidate.

    The candidate silences its checks unless another change is given.
    """
    _data, workflow, execute, execute_env = ROUTES[route]
    repo = tmp_path / "repo"
    shutil.copytree(render, repo)
    if change_base is not None:
        change_base(repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Trusted Checks")
    git(repo, "config", "user.email", "checks@example.invalid")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: trusted base")
    base = tmp_path / "base"
    git(repo, "worktree", "add", "-q", "--detach", str(base), "main")
    git(repo, "switch", "-qc", BRANCH)
    (change_candidate or silence_checks)(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fix: change the candidate tree")

    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    output = tmp_path / "github-output"
    common = {"RUNNER_TEMP": str(runner_temp), "GITHUB_OUTPUT": str(output)}
    workflow_path = repo / ".github/workflows" / workflow
    preserved = run_step(
        step(workflow_path, PRESERVE),
        base,
        {**common, "GITHUB_WORKSPACE": str(base), "GUIDED_RELEASE": "false"},
    )
    assert preserved.returncode == 0, preserved.stdout + preserved.stderr
    return run_step(
        step(workflow_path, execute),
        repo,
        {
            **common,
            "GITHUB_WORKSPACE": str(repo),
            **execute_env,
            "CSARC_CI_TIER": tier,
            "CSARC_VERIFICATION_SUITE": tier,
        },
    )


@pytest.mark.large
@pytest.mark.parametrize("route", sorted(ROUTES))
def test_candidate_cannot_silence_a_trusted_check(
    tmp_path: Path, renders: dict[str, Path], route: str
) -> None:
    """AC2: a candidate check turned into `exit 0` never yields success."""
    result = verify_route(tmp_path, renders[route], route)
    log = result.stdout + result.stderr
    assert result.returncode != 0, log
    assert CONFLICT in log


@pytest.mark.large
@pytest.mark.parametrize("route", sorted(ROUTES))
def test_negative_control_fallback_lets_the_candidate_pass(
    tmp_path: Path, renders: dict[str, Path], route: str
) -> None:
    """The AC2 test fails when the check root falls back to the candidate.

    A base whose entry point reads checks from the candidate, as the staged
    control did before #1325, runs the silenced copies and passes, so the
    assertions above would not hold.
    """
    result = verify_route(
        tmp_path, renders[route], route, change_base=fall_back_to_candidate
    )
    log = result.stdout + result.stderr
    assert result.returncode == 0, log
    assert CONFLICT not in log


SHADOW = "ERROR: shadowed standard library"
SHADOWED = ("json", "pytest", "runpy", "tomllib")


def shadow_modules(as_package: bool) -> Callable[[Path], None]:
    """Return a change that plants stdlib look-alikes in the candidate."""

    def change(repo: Path) -> None:
        for name in SHADOWED:
            target = (
                repo / name / "__init__.py"
                if as_package
                else repo / f"{name}.py"
            )
            target.parent.mkdir(exist_ok=True)
            target.write_text(f"raise SystemExit({SHADOW!r})\n", "utf-8")

    return change


def trust_the_current_directory(base: Path) -> None:
    """Drop the isolation flags from the base entry points (pre-#1325).

    The fixture renders declare no language, so the plan reads two keys.
    """
    replacements = {
        "verify-fast": ("python3 -I -c", "python3 -c", 2),
        "verify": (
            "platform_python=(python3 -I)",
            "platform_python=(python3)",
            1,
        ),
    }
    for name, (old, new, count) in replacements.items():
        script = base / ".csarc/scripts" / name
        text = script.read_text(encoding="utf-8")
        assert text.count(old) == count, name
        script.write_text(text.replace(old, new), encoding="utf-8")


@pytest.mark.large
@pytest.mark.parametrize("as_package", [False, True], ids=["module", "package"])
@pytest.mark.parametrize("route", sorted(ROUTES))
def test_candidate_cannot_shadow_the_trusted_interpreter(
    tmp_path: Path, renders: dict[str, Path], route: str, as_package: bool
) -> None:
    """AC1: a candidate json.py or json/ never reaches trusted Python.

    The fast entry point reads the router plan and the full entry point
    checks JSON and settings with Python in the candidate's directory.
    """
    result = verify_route(
        tmp_path,
        renders[route],
        route,
        change_candidate=shadow_modules(as_package),
        tier="fast",
    )
    log = result.stdout + result.stderr
    assert result.returncode == 0, log
    assert "suite=full" in log
    assert "JSON syntax: .csarc/policies/repository.json" in log
    assert SHADOW not in log


@pytest.mark.large
@pytest.mark.parametrize("route", sorted(ROUTES))
def test_negative_control_shadowing_without_isolation(
    tmp_path: Path, renders: dict[str, Path], route: str
) -> None:
    """The shadowing test fails when trusted Python trusts the cwd."""
    result = verify_route(
        tmp_path,
        renders[route],
        route,
        change_base=trust_the_current_directory,
        change_candidate=shadow_modules(as_package=False),
        tier="fast",
    )
    log = result.stdout + result.stderr
    assert result.returncode != 0, log
    assert SHADOW in log
