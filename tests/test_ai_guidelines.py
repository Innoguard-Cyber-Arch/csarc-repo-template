"""Structural tests for the generated AI-guidance contract."""

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
    assert ".csarc/docs/csarc.md#工作流程" in rendered
    assert ".csarc/docs/ci-policy.md#審查與合併資格" in rendered
    assert ".csarc/docs/ci-policy.md#驗證分級與實測成本" in rendered
    assert "docs/index.html#" not in rendered
    assert "docs/index.html#work" not in rendered
    assert "review requirements, merge eligibility" in rendered
    assert "Alpha self-merge" in rendered
    assert ".csarc/docs/csarc.md#公版更新" in rendered
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
    assert "automation are suspended" not in root_guidance

    template_guidance = TEMPLATE.read_text(encoding="utf-8")
    assert template_guidance.count("BEGIN CSARC MANAGED BLOCK") == 1
    assert template_guidance.count("END CSARC MANAGED BLOCK") == 1
    assert ".csarc/docs/agent-workflow.md" in template_guidance
    assert "## Responsibility map" not in template_guidance
    assert "## Responsibility map" in WORKFLOW_TEMPLATE.read_text(
        encoding="utf-8"
    )

    # Issue #681: template/README.md.jinja's destination name now depends on
    # the readme_primary_language answer, so its source filename is a Jinja
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
    assert ".csarc/docs/ci-policy.md#審查與合併資格" in readme


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
    assert readiness == (
        ROOT / "template/.csarc/docs/security-scanner-readiness.md"
    ).read_text(encoding="utf-8")
    for required in (
        "Codex Security",
        "Claude / Anthropic",
        "unavailable / not established",
        "./scripts/security-smoke",
        "./.csarc/scripts/security-smoke",
        "does not run an AI security scanner",
    ):
        assert required in readiness

    assert "docs/security-scanner-readiness.md" in (
        ROOT / "AGENTS.md"
    ).read_text(encoding="utf-8")
    assert ".csarc/docs/security-scanner-readiness.md" in (
        WORKFLOW_TEMPLATE.read_text(encoding="utf-8")
    )
    assert "{% if project_mode == 'existing' %}/SECURITY.md" in (
        ROOT / "copier.yml"
    ).read_text(encoding="utf-8")
