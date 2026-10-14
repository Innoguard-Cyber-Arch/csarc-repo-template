"""Template-owned files stay in `.csarc/` or an ADR fixed location (#1070).

`docs/adr/generated-repository-layout.md` owns the allowlist of paths a
fresh render may create outside `.csarc/`. Generated-render coverage of the
same list lives in tests/test_generated_self_tests.py.
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template"
ADR = ROOT / "docs/adr/generated-repository-layout.md"


def allowlist() -> list[str]:
    """Return the ADR's fixed-location patterns, without comments."""
    text = ADR.read_text(encoding="utf-8")
    section = text.split("## 固定位置 allowlist", 1)[1]
    block = re.search(r"```text\n(.*?)\n```", section, re.DOTALL)
    assert block is not None
    return [
        line.strip()
        for line in block.group(1).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def outside_control_layer(path: str, patterns: list[str]) -> bool:
    """Return whether one rendered path is outside every ADR pattern."""
    return not any(fnmatchcase(path, pattern) for pattern in patterns)


def rendered_names(relative: Path) -> list[str]:
    """Approximate the rendered path for one template source file."""
    text = relative.as_posix().removesuffix(".jinja")
    text = text.replace("{{project_slug}}", "project").replace(
        "{{package_name}}", "package"
    )
    if text.startswith("{% if") and "README" in text:
        return ["README.md", "README.en.md", "README.zh-tw.md"]
    return [text]


def test_allowlist_names_fixed_and_product_locations() -> None:
    """The ADR lists the platform, scanner, and agent fixed locations."""
    patterns = allowlist()
    for required in (
        ".github/workflows/*.yml",
        "SECURITY.md",
        ".github/SECURITY.md",
        "AGENTS.md",
        ".claude/CLAUDE.md",
        "pyproject.toml",
        "tests/test_smoke.py",
    ):
        assert required in patterns
    assert not any(pattern.startswith(".csarc") for pattern in patterns)
    assert not any(pattern.startswith("scripts/") for pattern in patterns)


def test_template_sources_outside_csarc_match_the_allowlist() -> None:
    """Every template source outside `.csarc/` renders to an allowed path."""
    patterns = allowlist()
    violations: list[str] = []
    for path in sorted(TEMPLATE.rglob("*")):
        relative = path.relative_to(TEMPLATE)
        if (
            not path.is_file()
            or relative.parts[0] == ".csarc"
            or "__pycache__" in relative.parts
            # Copier writes the answers file to .csarc/config.yml.
            or relative.name.startswith("{{ _copier_conf.answers_file }}")
        ):
            continue
        violations.extend(
            name
            for name in rendered_names(relative)
            if outside_control_layer(name, patterns)
        )
    assert violations == []
