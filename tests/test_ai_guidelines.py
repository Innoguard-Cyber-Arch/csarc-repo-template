"""Structural tests for the generated AI-guidance contract."""

import re
import runpy
import subprocess
from pathlib import Path

import pytest
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template" / "AGENTS.md.jinja"
WORKFLOW_TEMPLATE = ROOT / "template/.csarc/docs/agent-workflow.md.jinja"
READINESS = ROOT / "docs/security-scanner-readiness.md"


@pytest.mark.parametrize(
    ("language", "python_command", "typescript_command", "rust_command"),
    [
        ("ci", False, False, False),
        ("python", True, False, False),
        ("typescript", False, True, False),
        ("rust", False, False, True),
        ("python-typescript", True, True, False),
    ],
)
def test_generated_guidance_has_one_source_and_real_commands(
    language: str,
    python_command: bool,
    typescript_command: bool,
    rust_command: bool,
) -> None:
    """Keep governance references stable and commands profile-specific."""
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    context = {
        "copilot_review": "allowed",
        "language": language,
        "languages": [] if language == "ci" else language.split("-"),
        "package_name": "guidance_fixture",
        "project_name": "Guidance fixture",
        "verification_mode": "hosted",
        "documentation_mode": "template-and-content",
        "documentation_secondary_language": "en",
        "python_floor": "latest",
        "lifecycle": ["issues", "milestones"],
        "release_ownership": "csarc-owned",
    }
    entry = environment.from_string(TEMPLATE.read_text(encoding="utf-8"))
    workflow = environment.from_string(
        WORKFLOW_TEMPLATE.read_text(encoding="utf-8")
    )
    rendered_entry = entry.render(**context)
    rendered = workflow.render(
        **context,
    )

    assert ".csarc/docs/agent-workflow.md" in rendered_entry
    assert "## Responsibility map" not in rendered_entry
    assert "## Responsibility map" in rendered
    assert "Approved specs and ADRs preserve durable context" in rendered
    assert "cross-session, high-risk, or hard-to-recover work" in rendered
    assert "never store raw chat transcripts" in rendered
    assert "single detailed CSARC workflow" in rendered
    assert "`.claude/CLAUDE.md` only imports the root entry point" in rendered
    assert "](csarc.md#工作流程)" in rendered
    assert "](ci-policy.md#審查與合併資格)" in rendered
    assert "](ci-policy.md#驗證分級)" in rendered
    assert "docs/index.html#" not in rendered
    assert "docs/index.html#work" not in rendered
    assert "review requirements, merge eligibility" in rendered
    assert "configured admin bypass" in rendered
    assert "do not rerun the aggregate suite solely because" in rendered
    assert "local full is reserved for a documented fallback" in rendered
    local_rendered = workflow.render(
        **{**context, "verification_mode": "local"}
    )
    assert "run `./.csarc/scripts/verify-fast` once" in local_rendered
    assert (
        "do not rerun the aggregate suite solely because" not in local_rendered
    )
    # Issue #1077: guidance names only payload the selected options render.
    narrow = workflow.render(
        **{
            **context,
            "verification_mode": "local",
            "documentation_mode": "off",
            "lifecycle": [],
            "release_ownership": "verification-only",
        }
    )
    for absent in (
        "milestone-description.md",
        "documentation-policy.md",
        "publish-release",
        "build-repo-site",
        "security-smoke",
    ):
        assert absent not in narrow, absent
    assert "publish-release" in rendered
    assert "milestone-description.md" in rendered
    assert ".csarc/scripts/gh-issue-develop" in rendered
    assert ".csarc/scripts/finalization-queue announce" in rendered
    assert "READY_TO_FINALIZE" in rendered
    assert "ARCHIVE_READY" in rendered
    assert "never rename or delete an open PR's head" in rendered
    assert "](csarc.md#公版更新)" in rendered
    assert "automation are suspended" not in rendered
    assert ("Python setup:" in rendered) is python_command
    assert ("TypeScript setup:" in rendered) is typescript_command
    assert ("Rust setup:" in rendered) is rust_command
    # Issue #737: a generated project's own Rust setup step must warn about
    # the Linux/WSL2 system C linker prerequisite (build-essential), not
    # just this template repo's own README/docs/install.md.
    assert ("build-essential" in rendered) is rust_command


def test_thin_imports_and_readme_do_not_duplicate_merge_policy() -> None:
    """Keep imports thin and leave merge authorization to Journey 07."""
    assert (ROOT / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (ROOT / "template/.claude/CLAUDE.md").read_text(
        encoding="utf-8"
    ) == "@../AGENTS.md\n"

    root_guidance = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Responsibility map" in root_guidance
    assert "Approved specs and ADRs preserve durable context" in root_guidance
    assert "Journey 08" in root_guidance
    assert "scripts/finalization-queue announce" in root_guidance
    assert "READY_TO_FINALIZE" in root_guidance
    assert "ARCHIVE_READY" in root_guidance
    assert (
        "does not rerun the aggregate fast or full suite locally"
        in root_guidance
    )
    assert "Run local full only for a documented fallback" in root_guidance
    assert "automation are suspended" not in root_guidance

    template_guidance = TEMPLATE.read_text(encoding="utf-8")
    assert template_guidance.count("BEGIN CSARC MANAGED BLOCK") == 1
    assert template_guidance.count("END CSARC MANAGED BLOCK") == 1
    assert ".csarc/docs/agent-workflow.md" in template_guidance
    assert "## Responsibility map" not in template_guidance
    assert "## Responsibility map" in WORKFLOW_TEMPLATE.read_text(
        encoding="utf-8"
    )

    # The template README's destination name depends on primary_language, so
    # its source filename is a Jinja
    # expression too (e.g. "{% if ... == 'zh-tw' %}README{% else %}...").
    # "zh-tw" always appears somewhere in that expression for the zh-tw
    # content file, and never in the English one, so it is a reliable glob.
    zh_tw_readme_matches = list((ROOT / "template").glob("*zh-tw*.md.jinja"))
    assert len(zh_tw_readme_matches) == 1, (
        f"expected exactly one zh-tw README template, found "
        f"{zh_tw_readme_matches}"
    )
    readme = zh_tw_readme_matches[0].read_text(encoding="utf-8")
    assert "一般情況下不能自行合併" not in readme
    assert "AGENTS.md" in readme
    assert "](ci-policy.md#審查與合併資格)" in (
        WORKFLOW_TEMPLATE.read_text(encoding="utf-8")
    )


def test_security_scanner_policy_and_guidance_are_shared() -> None:
    """Keep scanner context distinct from disclosure and present downstream."""
    root_policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert root_policy == (ROOT / "template/SECURITY.md").read_text(
        encoding="utf-8"
    )
    assert "## Threat Model and Trust Boundaries" in root_policy
    assert ".github/SECURITY.md" in root_policy

    disclosure = (ROOT / ".github/SECURITY.md").read_text(encoding="utf-8")
    assert "## Reporting a vulnerability" in disclosure
    assert "## Threat Model and Trust Boundaries" not in disclosure

    readiness = READINESS.read_text(encoding="utf-8")
    # Issue #1081: generated repositories get a project-scoped readiness
    # page without this repository's inventory or measurements.
    generated = (
        ROOT / "template/.csarc/docs/security-scanner-readiness.md"
    ).read_text(encoding="utf-8")
    for required in (
        "Codex Security",
        "Claude Security",
        "unavailable / not established",
        "never runs an AI security scanner",
        "`.github/SECURITY.md`",
    ):
        assert required in generated, required
    for absent in ("security-smoke", "verify-template", "src/csarc_cli"):
        assert absent not in generated, absent
    for required in (
        "Codex Security",
        "Claude / Anthropic",
        "unavailable / not established",
        "./scripts/security-smoke",
        "template CI runs the same owner self-tests",
        "does not run an AI security scanner",
    ):
        assert required in readiness

    assert "docs/security-scanner-readiness.md" in (
        ROOT / "AGENTS.md"
    ).read_text(encoding="utf-8")
    assert ".csarc/docs/security-scanner-readiness.md" in (
        WORKFLOW_TEMPLATE.read_text(encoding="utf-8")
    )
    assert (
        "{% if (project_mode | default('')) == 'existing' %}/SECURITY.md"
        in (ROOT / "copier.yml").read_text(encoding="utf-8")
    )


TITLE_CHECKS = (
    ROOT / "scripts/validate-pr-policy",
    ROOT / "template/.csarc/scripts/validate-pr-policy",
)
CONVENTION = re.compile(
    r"Pull request titles use `type\(scope\): summary` in ASCII: type is one "
    r"of (?P<types>[^;]+); the scope is optional lowercase "
    r"`\[(?P<scope>[^\]]+)\]`; `!` before the colon marks a breaking change; "
    r"the `title` check enforces this\. The squash commit and any release "
    r"notes take this title, and release intent reads its type \(`!` major, "
    r"`feat` minor, `fix` or `revert` patch, others none\)"
)


def _documented_convention(text: str) -> tuple[tuple[str, ...], str]:
    match = CONVENTION.search(text)
    assert match is not None, "PR title convention sentence is missing"
    return tuple(re.findall(r"`([a-z]+)`", match["types"])), match["scope"]


def _title_rule(script: Path) -> str:
    match = re.search(
        r'if \[\[ ! "\$PR_TITLE" =~ (.+?) \]\]; then',
        script.read_text(encoding="utf-8"),
    )
    assert match is not None, script
    return match.group(1)


def _title_check_accepts(rule: str, title: str) -> bool:
    # Run the exact Bash pattern the `title` check uses, then its ASCII guard.
    script = (
        f'[[ "$1" =~ {rule} ]] || exit 1; '
        "printf '%s' \"$1\" | LC_ALL=C grep -q '[^ -~]' && exit 1; exit 0"
    )
    result = subprocess.run(  # noqa: S603
        ["bash", "-c", script, "title-check", title],  # noqa: S607
        check=False,
    )
    return result.returncode == 0


def test_pr_title_convention_matches_the_title_check() -> None:
    """Issue #1139 AC3: the documented PR title rule is the `title` check."""
    environment = Environment(autoescape=False, undefined=StrictUndefined)  # noqa: S701
    workflow = environment.from_string(
        WORKFLOW_TEMPLATE.read_text(encoding="utf-8")
    )
    base = {
        "copilot_review": "disallowed",
        "languages": [],
        "project_name": "Title fixture",
        "documentation_mode": "off",
        "lifecycle": [],
        "release_ownership": "verification-only",
    }
    sources = [(ROOT / "AGENTS.md").read_text(encoding="utf-8")] + [
        workflow.render(**base, verification_mode=mode)
        for mode in ("local", "hosted")
    ]
    documented = {_documented_convention(text) for text in sources}
    assert len(documented) == 1
    types, scope = next(iter(documented))

    for script in TITLE_CHECKS:
        rule = _title_rule(script)
        group = re.match(r"\^\(([a-z|]+)\)", rule)
        assert group is not None
        assert tuple(group.group(1).split("|")) == types
        assert f"[{scope}]" in rule
        for kind in types:
            assert _title_check_accepts(rule, f"{kind}: add one summary")
            assert _title_check_accepts(rule, f"{kind}(a.b_c/d-1): summary")
            assert _title_check_accepts(rule, f"{kind}(cli)!: break it")
        for title in (
            "feature: add one summary",
            "feat(CLI): uppercase scope",
            "feat add one summary",
            "feat: 中文標題",
        ):
            assert not _title_check_accepts(rule, title), title

    # The documented intent mapping is the one release planning applies.
    release_intent = runpy.run_path(str(ROOT / "scripts/release_policy.py"))[
        "release_intent"
    ]
    expected = {"feat": "minor", "fix": "patch", "revert": "patch"}
    for kind in types:
        assert release_intent(f"{kind}: summary") == expected.get(
            kind, "no-release"
        )
        assert release_intent(f"{kind}(x)!: summary") == "major"
