"""Render only the payload each option uses (Issue #1077).

A render matrix proves every generated script and operations document has
a caller the selected options enable, that nothing outside the ADR
allowlist is created, that an adopted repository receives no product
starter, and that each representative render imports and verifies itself.
`scripts/generated_payload.py` measures the #1058 Targets fixtures.
"""

from __future__ import annotations

import ast
import functools
import os
import re
import shutil
import subprocess
import sys
import warnings
from fnmatch import fnmatchcase
from pathlib import Path
from typing import cast

import pytest
import yaml
from test_generated_layout_allowlist import allowlist
from test_generated_runtime_boundary import probe, python_entries

from csarc_cli import settings_schema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generated_payload  # noqa: E402

pytestmark = pytest.mark.large

GIT = shutil.which("git") or "git"
BASH = shutil.which("bash") or "bash"
NARROW: dict[str, object] = {
    "verification_mode": "local",
    "documentation_mode": "content-only",
    "documentation_languages": "zh-tw",
    "lifecycle": [],
    "scheduled_checks": [],
    "languages": [],
}
# AC6: the representative renders every payload rule is checked against.
MATRIX: dict[str, dict[str, object]] = {
    "minimal": {
        **NARROW,
        "documentation_mode": "off",
        "release_ownership": "verification-only",
    },
    "solo-local": dict(NARROW),
    "hosted": {
        "verification_mode": "hosted",
        "documentation_mode": "template-and-content",
        "lifecycle": ["issues", "milestones"],
        "scheduled_checks": ["governance-drift", "template-update"],
        "languages": [],
        "container": True,
        "code_owner": "@example",
    },
    "documentation-off": {**NARROW, "documentation_mode": "off"},
    "csarc-owned": {
        **NARROW,
        "lifecycle": ["issues", "milestones"],
        "release_ownership": "csarc-owned",
    },
    "product-owned": {
        "project_mode": "existing",
        "release_ownership": "product-owned",
        "verification_mode": "hosted",
        "documentation_mode": "content-only",
        "lifecycle": ["issues"],
        "scheduled_checks": [],
        "languages": ["python", "typescript", "go", "rust"],
        "container": True,
    },
    "verification-only": {
        **NARROW,
        "release_ownership": "verification-only",
        "verification_mode": "hosted",
    },
}
# Read-only operator diagnostics documented for maintainers; they have no
# automated caller, so each one needs a reason here. The capability
# diagnostic (#531) had none and is no longer rendered (#1129 AC5); it stays
# a template-repository tool under root `scripts/`.
OPERATOR_ENTRY_POINTS: dict[str, str] = {}
# Template-repository tools that no generated caller reaches (#1129).
TEMPLATE_REPOSITORY_ONLY = (
    ".csarc/scripts/check-repo-capabilities",
    ".csarc/scripts/repo_capabilities.py",
    ".csarc/policies/capability-matrix.json",
)
# A static reference whose step the workflow gates on the same option at
# runtime, so it never executes when the script is not rendered.
RUNTIME_GATED_REFERENCES = {
    (".github/workflows/ci.yml", "verify-release-candidate"),
    # Issue #1106: the tokenless packaging step shares the same gate.
    (".github/workflows/ci.yml", "release_bundle.py"),
}
# Reference documents would describe the whole template and never make a
# script reachable. Since #1081 every operations document is rendered per
# option, so none remains.
REFERENCE_DOCUMENTS: set[str] = set()
# Operations entry points rendered per option: every script they name must
# exist in that render.
STRICT_FILES = {
    "AGENTS.md",
    ".claude/CLAUDE.md",
    ".csarc/docs/agent-workflow.md",
    ".csarc/docs/ci-policy.md",
    ".csarc/docs/csarc.md",
    ".csarc/docs/milestone-description.md",
    ".csarc/docs/security-scanner-readiness.md",
    ".github/pull_request_template.md",
    "docs/README.md",
}
ENTRY_FILES = (
    "AGENTS.md",
    ".claude/CLAUDE.md",
    ".github/pull_request_template.md",
    "README.md",
)
RELEASE_ONLY = {
    "converge-release-tag",
    "publish-release",
    "release_bundle.py",
    "release_candidate.py",
    "release_writer.py",
    "verify-release-candidate",
    "verify_release_consumption.py",
}
PRODUCT_STARTERS = (
    "src",
    "tests",
    "cmd",
    "internal",
    "typescript",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    ".node-version",
    "biome.json",
    "tsconfig.json",
    "tsconfig.build.json",
    "vitest.config.ts",
    "go.mod",
    "Cargo.toml",
    "Cargo.lock",
    "rust-toolchain.toml",
    "Dockerfile",
    "docker-compose.yml",
)


def git(project: Path, *arguments: str) -> str:
    """Run one Git command in a rendered project."""
    return subprocess.run(  # noqa: S603
        [GIT, *arguments],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture(scope="module")
def renders(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Path]:
    """Render and commit every matrix entry once."""
    workdir = tmp_path_factory.mktemp("payload")
    source = workdir / "source"
    source.mkdir()
    generated_payload.template_copy(source)
    projects: dict[str, Path] = {}
    for name, data in MATRIX.items():
        project = generated_payload.render(source, workdir / name, data)
        if data.get("documentation_mode") == "template-and-content":
            # The Copier task the render skipped builds the site bundle.
            subprocess.run(  # noqa: S603
                [BASH, ".csarc/scripts/build-repo-site"],
                cwd=project,
                check=True,
                capture_output=True,
            )
        git(project, "init", "-q", "-b", "main")
        git(project, "add", "-A")
        git(
            project,
            "-c",
            "user.name=Payload Test",
            "-c",
            "user.email=payload@example.invalid",
            "commit",
            "-q",
            "-m",
            "test: rendered project",
        )
        git(project, "config", "branch.main.gh-merge-base", "main")
        projects[name] = project
    return projects


def files_of(project: Path) -> list[str]:
    """Return every committed rendered path (ignored build output aside)."""
    return sorted(git(project, "ls-files").splitlines())


def cli_script_names() -> set[str]:
    """Return generated script names the pinned CLI runs directly."""
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src/csarc_cli").glob("*.py")
    )
    names = set(re.findall(r"\.csarc/scripts/([A-Za-z0-9_.-]+)", source))
    names |= set(re.findall(r"managed_script\(\s*\w+,\s*\"([^\"]+)\"", source))
    return names


def mentions(text: str, name: str) -> bool:
    """Return whether text calls, imports, or names one script."""
    if re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w-])", text):
        return True
    if name.endswith(".py"):
        stem = re.escape(name.removesuffix(".py"))
        return (
            re.search(rf"(?m)^\s*(?:from|import)\s+{stem}\b", text) is not None
            or re.search(rf"[\"']{stem}[\"']", text) is not None
        )
    return False


def unreachable(project: Path) -> list[str]:
    """Return scripts and docs that no enabled entry point reaches.

    Workflows, the agent entry files, and the CLI are roots; any reached
    script, workflow, or operations document reaches every script or
    document it names. Reference documents never add an edge.
    """
    nodes = {
        path.relative_to(project).as_posix(): path
        for directory in (".csarc/scripts", ".csarc/docs")
        for path in (project / directory).glob("*")
        if path.is_file() and path.name != "__init__.py"
    }
    texts = {
        name: path.read_text(encoding="utf-8", errors="ignore")
        for name, path in nodes.items()
    }
    frontier = [
        path.read_text(encoding="utf-8", errors="ignore")
        for pattern in (".github/workflows/*.yml", ".github/ISSUE_TEMPLATE/*")
        for path in project.glob(pattern)
    ]
    frontier.extend(
        (project / name).read_text(encoding="utf-8")
        for name in ENTRY_FILES
        if (project / name).is_file()
    )
    reached = {
        name
        for name in nodes
        if Path(name).name in cli_script_names()
        or Path(name).name in OPERATOR_ENTRY_POINTS
    }
    frontier.extend(
        texts[name] for name in reached if name not in REFERENCE_DOCUMENTS
    )
    while frontier:
        text = frontier.pop()
        for name in nodes:
            if name not in reached and mentions(text, Path(name).name):
                reached.add(name)
                if name not in REFERENCE_DOCUMENTS:
                    frontier.append(texts[name])
    return sorted(set(nodes) - reached)


@pytest.mark.parametrize("name", list(MATRIX))
def test_every_rendered_script_and_document_has_a_caller(
    renders: dict[str, Path], name: str
) -> None:
    """AC1: nothing is rendered that no enabled entry point reaches."""
    assert unreachable(renders[name]) == []


@pytest.mark.parametrize("name", list(MATRIX))
def test_no_dangling_executable_reference(
    renders: dict[str, Path], name: str
) -> None:
    """AC1/R1: rendered files only invoke scripts the render contains."""
    project = renders[name]
    shipped = {path.name for path in (project / ".csarc/scripts").iterdir()}
    template_scripts = {
        path.name.removesuffix(".jinja")
        for path in (ROOT / "template/.csarc/scripts").iterdir()
    }
    dangling: list[str] = []
    for relative in files_of(project):
        if not relative.endswith((".md", ".yml", ".json")):
            continue
        text = (project / relative).read_text(encoding="utf-8", errors="ignore")
        # Workflows and the option-rendered operations entry points name
        # only scripts this render contains; static documents describe the
        # whole template and may name a script another option renders, but
        # never one no render ships.
        known = (
            shipped
            if relative in STRICT_FILES
            or relative.startswith(".github/workflows/")
            else template_scripts
        )
        for script in re.findall(
            r"\.csarc/scripts/([A-Za-z0-9_*-]+(?:\.[a-z]+)?)", text
        ):
            if (relative, script) in RUNTIME_GATED_REFERENCES:
                continue
            if any(fnmatchcase(candidate, script) for candidate in known):
                continue
            dangling.append(f"{relative}: {script}")
    assert not dangling, "\n".join(sorted(set(dangling)))


@pytest.mark.parametrize("name", list(MATRIX))
def test_options_select_one_verifier_and_at_most_one_publisher(
    renders: dict[str, Path], name: str
) -> None:
    """AC2: options control payload without a second verifier/publisher."""
    data = {**MATRIX[name]}
    project = renders[name]
    scripts = {path.name for path in (project / ".csarc/scripts").iterdir()}
    workflows = {
        path.name for path in (project / ".github/workflows").glob("*.yml")
    }
    config = yaml.safe_load(
        (project / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    ownership = config["release_ownership"]
    hosted = data["verification_mode"] == "hosted"
    lifecycle = cast(list[str], data.get("lifecycle", ["issues", "milestones"]))

    # One verifier pair, no template self-test, no second runner.
    assert {"verify", "verify-fast"} <= scripts
    assert not [script for script in scripts if script.startswith("test-")]
    assert "security-smoke" not in scripts
    assert not (project / ".csarc/tests").exists()
    # The publisher exists only for the CSARC Release owner.
    assert (scripts >= RELEASE_ONLY) is (ownership == "csarc-owned")
    if ownership != "csarc-owned":
        assert not RELEASE_ONLY & scripts
        assert "release.yml" not in workflows
    # Hosted-only automation never reaches a local render.
    for script in ("request-reviewer", "sync_work_item_metadata.py"):
        assert (script in scripts) is hosted, script
    assert ("validate-issue-policy" in scripts) is (
        hosted and "issues" in lifecycle
    )
    assert ("work-item-lifecycle.yml" in workflows) is (
        hosted and bool(lifecycle)
    )
    if not hosted:
        # Only the opted-in scheduled checks run without hosted CI.
        assert workflows <= {"governance-drift.yml", "template-update.yml"}
    # Milestone operations exist only when Milestone automation is on.
    milestones = "milestones" in lifecycle
    assert (
        project / ".csarc/docs/milestone-description.md"
    ).is_file() is milestones
    assert (
        project / ".github/ISSUE_TEMPLATE/milestone-tracker.yml"
    ).is_file() is milestones
    ci_policy = (project / ".csarc/docs/ci-policy.md").read_text(
        encoding="utf-8"
    )
    agent_workflow = (project / ".csarc/docs/agent-workflow.md").read_text(
        encoding="utf-8"
    )
    assert (
        "## Milestone promotion 的 ADR 與文件對齊" in ci_policy
    ) is milestones
    assert ("batch-level ADR and documentation review" in agent_workflow) is (
        milestones
    )
    documentation = data.get("documentation_mode") != "off"
    assert (
        project / ".csarc/docs/documentation-policy.md"
    ).is_file() is documentation


@pytest.mark.parametrize("name", list(MATRIX))
def test_render_stays_inside_the_adr_allowlist(
    renders: dict[str, Path], name: str
) -> None:
    """AC3: outside `.csarc/`, a render creates only ADR fixed locations."""
    patterns = allowlist()
    outside = [
        path
        for path in files_of(renders[name])
        if not path.startswith(".csarc/")
    ]
    assert outside
    assert [
        path
        for path in outside
        if not any(fnmatchcase(path, pattern) for pattern in patterns)
    ] == []


@pytest.mark.parametrize("name", list(MATRIX))
def test_template_repository_tools_are_never_rendered(
    renders: dict[str, Path], name: str
) -> None:
    """#1129 AC5: an uncalled diagnostic stays in the template repository."""
    for relative in TEMPLATE_REPOSITORY_ONLY:
        assert not (renders[name] / relative).exists(), relative
        assert (ROOT / relative.removeprefix(".csarc/")).is_file(), relative


def test_existing_adopt_adds_no_product_starter(
    renders: dict[str, Path],
) -> None:
    """AC4: an adopted repository only receives CSARC and platform files."""
    project = renders["product-owned"]
    for name in PRODUCT_STARTERS:
        assert not (project / name).exists(), name
    for name in ("README.md", "CHANGELOG.md"):
        assert not (project / name).exists(), name


@pytest.mark.parametrize("name", list(MATRIX))
def test_every_python_entry_imports(
    renders: dict[str, Path], name: str
) -> None:
    """AC6: each Python entry of a render loads without missing siblings."""
    project = renders[name]
    entries = python_entries(project / ".csarc/scripts")
    assert entries
    for entry in entries:
        code, _loaded = probe(project, entry, "csarc_import_probe")
        assert code == 0, entry.name


@pytest.mark.parametrize("name", list(MATRIX))
def test_every_rendered_message_follows_the_writing_guide(
    renders: dict[str, Path], name: str
) -> None:
    """#1221 AC5: adopt and update add only conforming messages.

    An adopt or update candidate changes every line the template brings,
    so the generated message check passes only if all of them conform.
    """
    project = renders[name]
    result = subprocess.run(  # noqa: S603
        [project / ".csarc/scripts/check-message-style", "--all"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    assert result.stdout.startswith("OK: Message pattern check passed")


@pytest.mark.parametrize("name", list(MATRIX))
def test_render_passes_its_own_fast_verifier(
    renders: dict[str, Path], name: str
) -> None:
    """AC5/AC6: generated verify-fast runs only the selected checks."""
    project = renders[name]
    if MATRIX[name].get("languages"):
        pytest.skip("product toolchains need the lockfiles Copier tasks write")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CSARC_", "VIRTUAL_ENV", "PYTEST_"))
    }
    environment["CSARC_CI_BASE"] = git(project, "rev-parse", "HEAD")
    result = subprocess.run(  # noqa: S603
        [project / ".csarc/scripts/verify-fast"],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined[-4000:]
    assert "cases passed" not in combined


@pytest.mark.parametrize("name", list(MATRIX))
def test_rulesets_require_only_checks_the_render_ships(
    renders: dict[str, Path], name: str
) -> None:
    """Issue #1090 AC1/AC4: required checks follow rendered workflows.

    Each local/hosted, lifecycle, and release-ownership render requires
    exactly the checks its own workflows publish, on the default branch
    and dev/m* alike, without any removed setting choosing the refs.
    """
    project = renders[name]
    config = yaml.safe_load(
        (project / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    policies = project / ".csarc/policies"
    required = yaml.safe_load(
        (policies / "rulesets-required-checks.json").read_text(encoding="utf-8")
    )
    protected = yaml.safe_load(
        (policies / "rulesets.json").read_text(encoding="utf-8")
    )
    assert required["conditions"] == protected["conditions"]
    assert required["conditions"]["ref_name"]["include"] == [
        "~DEFAULT_BRANCH",
        "refs/heads/dev/m*",
    ]
    contexts = {
        check["context"]
        for rule in required["rules"]
        for check in rule["parameters"]["required_status_checks"]
    }
    published = {
        str(job.get("name", job_id))
        for path in (project / ".github/workflows").glob("*.yml")
        for job_id, job in (
            yaml.safe_load(path.read_text(encoding="utf-8")).get("jobs") or {}
        ).items()
    }
    if config["verification_mode"] == "local":
        assert contexts == set()
    else:
        assert contexts == {"title", "verify", "review"}
        assert contexts <= published


# Ways an active file reads or suggests a setting by name (Issue #1090
# AC5); migration code and historical fixtures are not rendered.
RETIRED_REFERENCE_FORMS = (
    r"\[\[{key}\]\]",
    r"--data[ =]`?{key}=",
    r"csarc_config\.py\"? {key}\b",
)


@pytest.mark.parametrize("name", list(MATRIX))
def test_no_render_reads_or_suggests_a_retired_setting(
    renders: dict[str, Path], name: str
) -> None:
    """Issue #1090 AC5: retired settings never reach active output."""
    retired = sorted(
        set(settings_schema.RETIRED_SETTINGS) - settings_schema.ONE_TIME_INPUTS
    )
    project = renders[name]
    saved = yaml.safe_load(
        (project / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    assert not set(saved) & set(retired)
    pattern = re.compile(
        "|".join(
            form.format(key=re.escape(key))
            for form in RETIRED_REFERENCE_FORMS
            for key in retired
        )
    )
    found = [
        f"{path}: {match.group(0)}"
        for path in files_of(project)
        if (project / path).is_file()
        for match in pattern.finditer(
            (project / path).read_text(encoding="utf-8", errors="ignore")
        )
    ]
    assert found == []


@functools.cache
def measured() -> dict[str, dict[str, int]]:
    """Render and measure every Targets fixture once per test session."""
    return generated_payload.measure_fixtures(list(generated_payload.FIXTURES))


def test_payload_never_grows_past_its_recorded_ceiling() -> None:
    """#1231: every fixture stays within the backstop and each sub-budget.

    Budgets cover file count, canonical bytes, write and
    `pull_request_target` workflows, agent document tokens, and canonical
    runtime bytes per capability group; every runtime file has a group.
    Low headroom (#1177) is reported as a warning, never as a failure.
    """
    values_by_fixture = measured()
    failures = [
        failure
        for name, values in values_by_fixture.items()
        for failure in generated_payload.budget_failures(name, values)
    ]
    assert failures == []
    for warning in generated_payload.headroom_warnings(values_by_fixture):
        warnings.warn(warning, UserWarning, stacklevel=1)


def test_documentation_stays_within_its_budget() -> None:
    """#1081 AC3/AC8: the #1058 documentation line budget holds per fixture.

    #1231 replaced the two bytes budgets with the agent token budget.
    """
    budget = generated_payload.DOC_TARGETS
    values = measured()
    solo = values["solo-default"]
    assert solo["docs_lines"] <= budget["solo_docs_lines"]
    assert solo["ci_policy_lines"] <= budget["solo_ci_policy_lines"]
    hosted = values["hosted-csarc-owned-python"]
    assert hosted["ci_policy_lines"] <= budget["hosted_ci_policy_lines"]
    for name, data in generated_payload.FIXTURES.items():
        if data.get("verification_mode") == "local":
            lines = values[name]["agent_workflow_lines"]
            assert lines <= budget["agent_workflow_lines"], name
        assert (
            values[name]["milestone_description_lines"]
            <= budget["milestone_description_lines"]
        ), name


TEMPLATE_REPOSITORY = (
    "https://github.com/Innoguard-Cyber-Arch/csarc-repo-template"
)
FULL_SHA_LINK = re.compile(
    re.escape(TEMPLATE_REPOSITORY) + r"/(?:blob|tree|raw)/[0-9a-f]{40}/"
)
ISSUE_REFERENCE = re.compile(r"(?<![\w&/#])#\d+\b")
# Documents an operator reads in a render (#1058 Targets, references).
REFERENCE_SCOPE = (
    "AGENTS.md",
    ".claude/CLAUDE.md",
    "SECURITY.md",
    ".github/SECURITY.md",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/*",
    ".csarc/docs/*",
    "README*.md",
    "docs/**/*.md",
)
# Every template `#N` that may reach a render, with the reason it stays.
ISSUE_REFERENCE_ALLOWLIST: dict[tuple[str, str], str] = {
    (".github/ISSUE_TEMPLATE/milestone-tracker.yml", "#100"): (
        "example range in the form's placeholder text, not a template Issue"
    ),
    (".github/ISSUE_TEMPLATE/milestone-tracker.yml", "#110"): (
        "example range in the form's placeholder text, not a template Issue"
    ),
    ("docs/adr/README.md", "#1"): (
        "example ADR header linking a placeholder owner/repo Issue"
    ),
    ("docs/adr/README.md", "#2"): (
        "example ADR header linking a placeholder owner/repo pull request"
    ),
    (".csarc/scripts/authenticate_dependabot_head.py", "#755"): (
        "protocol string: the commit subject existing sync children carry"
    ),
    (".csarc/scripts/release_level.py", "#755"): (
        "protocol string: the same sync-child commit subject it classifies"
    ),
    (".csarc/scripts/sync_milestone_state.py", "#816"): (
        "protocol string: a Reconciliation status existing trackers contain"
    ),
}
# Root paths that exist only in the template repository.
TEMPLATE_ONLY_PATH = re.compile(
    r"(?<![\w./-])(?:scripts/(?!verify-product\b)[\w.-]+"
    r"|docs/index(?:\.en)?\.html|Journey \d+)"
)


def scoped_documents(project: Path) -> list[str]:
    """Return the rendered operator documents the reference rules cover."""
    return sorted(
        path
        for path in files_of(project)
        if any(fnmatchcase(path, pattern) for pattern in REFERENCE_SCOPE)
    )


def visible_script_strings(path: Path) -> list[str]:
    """Return the text a rendered script can print, without its comments.

    Python sources contribute every string literal except docstrings; any
    other script contributes its non-comment lines.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix != ".py" and not text.startswith("#!/usr/bin/env python"):
        return [
            line
            for line in text.splitlines()
            if not line.lstrip().startswith("#")
        ]
    tree = ast.parse(text)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node,
            ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


@pytest.mark.parametrize("name", list(MATRIX))
def test_render_carries_no_template_issue_reference(
    renders: dict[str, Path], name: str
) -> None:
    """#1081 AC4/R3: no template `#N` outside the reasoned allowlist."""
    project = renders[name]
    found: list[str] = []
    for relative in scoped_documents(project):
        text = (project / relative).read_text(encoding="utf-8")
        found.extend(
            f"{relative}: {match}"
            for match in ISSUE_REFERENCE.findall(text)
            if (relative, match) not in ISSUE_REFERENCE_ALLOWLIST
        )
    # Committed scripts only: import probes may leave `__pycache__` behind.
    for relative in files_of(project):
        if (
            not relative.startswith(".csarc/scripts/")
            or "__pycache__" in relative
        ):
            continue
        path = project / relative
        for text in visible_script_strings(path):
            found.extend(
                f"{relative}: {match}"
                for match in ISSUE_REFERENCE.findall(text)
                if (relative, match) not in ISSUE_REFERENCE_ALLOWLIST
            )
    assert found == []


@pytest.mark.parametrize("name", list(MATRIX))
def test_render_links_stay_resolvable(
    renders: dict[str, Path], name: str
) -> None:
    """#1081 AC4: one pinned template link per document at most, no
    `blob/main`, no template-only path, and no broken relative link."""
    project = renders[name]
    problems: list[str] = []
    for relative in files_of(project):
        path = project / relative
        text = path.read_text(encoding="utf-8", errors="ignore")
        if f"{TEMPLATE_REPOSITORY}/blob/main" in text:
            problems.append(f"{relative}: blob/main")
        if len(FULL_SHA_LINK.findall(text)) > 1:
            problems.append(f"{relative}: more than one pinned template link")
    for relative in scoped_documents(project):
        text = (project / relative).read_text(encoding="utf-8")
        problems.extend(
            f"{relative}: template-only {match}"
            for match in TEMPLATE_ONLY_PATH.findall(text)
            if not (project / match).exists()
        )
        if relative.endswith(".md"):
            problems.extend(broken_links(project, relative, text, MATRIX[name]))
    assert problems == []


def broken_links(
    project: Path, relative: str, text: str, data: dict[str, object]
) -> list[str]:
    """Return every relative Markdown link or anchor that does not resolve.

    An adopted repository keeps its own root README, CHANGELOG, and LICENSE,
    which the render never creates; links to them resolve in the product.
    """
    product_owned = (
        {"README.md", "CHANGELOG.md", "LICENSE"}
        if data.get("project_mode") == "existing"
        else set()
    )
    problems: list[str] = []
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if re.match(r"[a-z]+:", target) or target in product_owned:
            continue
        file_part, _, anchor = target.partition("#")
        source = project / relative
        linked = source.parent / file_part if file_part else source
        if not linked.exists():
            problems.append(f"{relative}: missing {target}")
        elif (
            anchor
            and linked.suffix == ".md"
            and anchor not in heading_slugs(linked.read_text("utf-8"))
        ):
            problems.append(f"{relative}: missing anchor {target}")
    return problems


def heading_slugs(text: str) -> set[str]:
    """Return GitHub's anchor slugs for every Markdown heading."""
    slugs: set[str] = set()
    for heading in re.findall(r"(?m)^#{1,6} +(.+?) *$", text):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        slugs.add(slug)
    return slugs


def guide(project: Path) -> str:
    """Return the rendered project operations guide."""
    return (project / ".csarc/docs/csarc.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", list(MATRIX))
def test_guide_describes_only_the_enabled_options(
    renders: dict[str, Path], name: str
) -> None:
    """#1081 AC3: the guide names this render's lifecycle, verification,
    release ownership, evidence, update, and recovery, and nothing else."""
    data = MATRIX[name]
    text = guide(renders[name])
    hosted = data["verification_mode"] == "hosted"
    lifecycle = cast(list[str], data.get("lifecycle", ["issues", "milestones"]))
    config = yaml.safe_load(
        (renders[name] / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    ownership = config["release_ownership"]
    for heading in (
        "## 本專案設定",
        "## 工作流程",
        "## 驗證與合併",
        "## Requirement evidence",
        "## 公版更新",
        "## 故障與恢復",
    ):
        assert heading in text, heading
    assert f"| 驗證 | `{data['verification_mode']}` |" in text
    assert f"| 發版 | `{ownership}` |" in text
    assert ("required `title`、`verify`、`review`" in text) is hosted
    assert ("self-attested-local" in text) is not hosted
    assert ("## 發版" in text) is (ownership == "csarc-owned")
    assert ("publish-release" in text) is (ownership == "csarc-owned")
    assert ("milestone-description.md" in text) is ("milestones" in lifecycle)
    assert ("dev/m<Milestone>" in text) is ("milestones" in lifecycle)
    assert "csarc update --apply-plan" in text
    # A render from a template copy has no Release commit to pin.
    assert FULL_SHA_LINK.search(text) is None
    assert "沒有固定的 Release commit" in text


def test_guide_links_the_installed_release_handbook(
    tmp_path: Path,
) -> None:
    """#1081 AC4: a Release render links its own handbook by full SHA."""
    from copier import run_copy

    source = tmp_path / "source"
    source.mkdir()
    generated_payload.template_copy(source)
    git(source, "init", "-q", "-b", "main")
    git(source, "add", "-A")
    git(
        source,
        "-c",
        "user.name=Payload Test",
        "-c",
        "user.email=payload@example.invalid",
        "commit",
        "-q",
        "-m",
        "test: template release",
    )
    sha = git(source, "rev-parse", "HEAD")
    project = tmp_path / "project"
    run_copy(
        str(source),
        project,
        data={**generated_payload.BASE_DATA, **NARROW},
        vcs_ref=sha,
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        quiet=True,
    )
    text = guide(project)
    expected = f"{TEMPLATE_REPOSITORY}/blob/{sha}/docs/handbook/handbook.md"
    assert FULL_SHA_LINK.findall(text) == [f"{TEMPLATE_REPOSITORY}/blob/{sha}/"]
    assert expected in text
    assert (ROOT / "docs/handbook/handbook.md").is_file()
    assert "沒有固定的 Release commit" not in text
    for relative in files_of_tree(project):
        if relative != ".csarc/docs/csarc.md":
            content = (project / relative).read_text("utf-8", errors="ignore")
            assert FULL_SHA_LINK.search(content) is None, relative


def files_of_tree(project: Path) -> list[str]:
    """Return every rendered file of an uncommitted project."""
    return sorted(
        path.relative_to(project).as_posix()
        for path in project.rglob("*")
        if path.is_file() and ".git" not in path.parts
    )
