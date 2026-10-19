"""Copyable merge authorization and ProjectV2 setup in `csarc.md` (#1138).

AC4: when `admin_bypass` is not `off`, the generated operations guide shows
the exact comment `pr_lifecycle.authorization_statement()` accepts, so the
documented format can never drift from the tool. AC5: the ProjectV2 setup
steps appear only when `github_project_url` is configured.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import jinja2
import pytest

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "template/.csarc/docs/csarc.md.jinja"
LIFECYCLE = runpy.run_path(
    str(ROOT / "template/.csarc/scripts/pr_lifecycle.py")
)
REPOSITORY = "example/guide-fixture"
PROJECT = "https://github.com/orgs/example/projects/7"
# Placeholder values the guide asks the reader to replace.
PR_SENTINEL = 987654321
HEAD_SENTINEL = "f" * 40


def render(**overrides: object) -> str:
    """Render the guide with Copier's strict undefined handling."""
    context: dict[str, object] = {
        "_copier_conf": {"vcs_ref_hash": ""},
        "verification_mode": "local",
        "documentation_mode": "content-only",
        "admin_bypass": "always",
        "copilot_review": "allowed",
        "release_ownership": "verification-only",
        "lifecycle": [],
        "scheduled_checks": [],
        "github_project_url": "",
        "repository_url": f"https://github.com/{REPOSITORY}",
        "project_mode": "new",
        "release_trigger": "main",
        **overrides,
    }
    environment = jinja2.Environment(  # noqa: S701 - renders Markdown
        undefined=jinja2.StrictUndefined, keep_trailing_newline=True
    )
    return environment.from_string(GUIDE.read_text("utf-8")).render(context)


def documented_statement() -> str:
    """Return the tool's statement with the guide's placeholders."""
    statement = LIFECYCLE["authorization_statement"](
        REPOSITORY, PR_SENTINEL, HEAD_SENTINEL
    )
    return statement.replace(str(PR_SENTINEL), "<PR>").replace(
        HEAD_SENTINEL, "<head SHA>"
    )


@pytest.mark.parametrize("admin_bypass", ["off", "beta-only", "always"])
def test_guide_shows_the_exact_authorization_comment(
    admin_bypass: str,
) -> None:
    """AC4/R2: the copyable comment equals `authorization_statement()`."""
    text = render(admin_bypass=admin_bypass)
    shown = documented_statement() in text
    assert shown is (admin_bypass != "off")
    assert ("authorization-template" in text) is shown
    assert ("head 改變" in text) is shown


@pytest.mark.parametrize("project", ["", PROJECT])
def test_guide_shows_project_setup_only_when_configured(project: str) -> None:
    """AC5: ProjectV2 steps render only with a configured Project URL."""
    text = render(github_project_url=project)
    configured = bool(project)
    assert ("## Project Roadmap 設定" in text) is configured
    for required in (
        "`Project start`",
        "`Project target`",
        "target 改為實際完成日",
        "`project` scope",
        "寫入權",
        "csarc issue sync-project --issue <N>",
        "只以 stub 驗證",
        "未經 live ProjectV2 驗證",
    ):
        assert (required in text) is configured, required
    assert (PROJECT in text) is configured
