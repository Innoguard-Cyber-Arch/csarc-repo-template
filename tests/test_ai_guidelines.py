"""Structural tests for the generated AI-guidance contract."""

from pathlib import Path

import pytest
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template" / "AGENTS.md.jinja"


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
    template = environment.from_string(TEMPLATE.read_text(encoding="utf-8"))
    rendered = template.render(
        branch_strategy="delivery",
        language=language,
        languages=[] if language == "ci" else language.split("-"),
        package_name="guidance_fixture",
        project_name="Guidance fixture",
    )

    assert "## Responsibility map" in rendered
    assert "Approved specs and ADRs preserve durable context" in rendered
    assert "cross-session, high-risk, or hard-to-recover work" in rendered
    assert "never store raw chat transcripts" in rendered
    assert "`AGENTS.md` is the single source" in rendered
    assert "`CLAUDE.md` only imports it" in rendered
    assert "docs/index.html#method" in rendered
    assert "docs/index.html#work" not in rendered
    assert "Journey 08" in rendered
    assert "Alpha self-merge" in rendered
    assert "Journey 09" in rendered
    assert "automation are suspended" not in rendered
    assert ("Python setup:" in rendered) is python_command
    assert ("TypeScript setup:" in rendered) is typescript_command
    assert ("Rust setup:" in rendered) is rust_command


def test_thin_imports_and_readme_do_not_duplicate_merge_policy() -> None:
    """Keep imports thin and leave merge authorization to Journey 07."""
    assert (ROOT / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (ROOT / "template" / "CLAUDE.md").read_text(
        encoding="utf-8"
    ) == "@AGENTS.md\n"

    root_guidance = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Responsibility map" in root_guidance
    assert "Approved specs and ADRs preserve durable context" in root_guidance
    assert "Journey 08" in root_guidance
    assert "automation are suspended" not in root_guidance

    template_guidance = TEMPLATE.read_text(encoding="utf-8")
    assert template_guidance.count("BEGIN CSARC MANAGED BLOCK") == 1
    assert template_guidance.count("END CSARC MANAGED BLOCK") == 1

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
    assert "08 規則治理" in readme
