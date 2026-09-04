"""Tests for immutable release prompt assets."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

PROMPT_MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "render_release_prompt.py")
)
REPOSITORY = PROMPT_MODULE["REPOSITORY"]
render = PROMPT_MODULE["render"]
status_prompt = PROMPT_MODULE["status_prompt"]


def test_render_uses_one_release_identity_everywhere() -> None:
    """Keep the release tag, SHA, guide URL, and provenance aligned."""
    sha = "a" * 40
    prompts, provenance_text, notes = render("v1.2.3", sha, "Release notes")
    provenance = json.loads(provenance_text)

    assert prompts.count(f"核准 commit：{sha}") == 4
    assert (
        prompts.count(f"https://raw.githubusercontent.com/{REPOSITORY}/{sha}/")
        == 4
    )
    source = f"git+https://github.com/{REPOSITORY}.git@{sha}"
    assert prompts.count(f"uvx --python 3.14 --from '{source}'") == 4
    assert "--from csarc-repo-cli" not in prompts
    assert "目標路徑：" not in prompts
    assert "csarc init" in prompts
    assert "csarc adopt" in prompts
    assert "--apply-plan" in prompts
    assert "repo-relative executable project_verification_hook" in prompts
    assert "檢視 repo 外的 Markdown、PDF 與 machine plan" in prompts
    assert "csarc update" in prompts
    assert "csarc status" in prompts
    assert provenance["commit_sha"] == sha
    assert provenance["guide_url"] in prompts
    assert provenance["release_tag"] == "v1.2.3"
    assert prompts.split("\n\n---", maxsplit=1)[0] not in notes
    assert "csarc adopt" in notes


@pytest.mark.parametrize(
    ("tag", "sha"),
    [("1.2.3", "a" * 40), ("v1.2.3", "A" * 40), ("v1.2.3", "a" * 39)],
)
def test_render_rejects_untrusted_release_inputs(tag: str, sha: str) -> None:
    """Reject malformed tags and non-canonical commit identifiers."""
    with pytest.raises(ValueError):
        render(tag, sha, "Release notes")


def test_status_prompt_is_the_fourth_pinned_prompt_in_render_output() -> None:
    """Keep the 4th pinned status prompt appended after init/adopt/update."""
    sha = "c" * 40
    prompts, _provenance_text, _notes = render("v9.9.9", sha, "Release notes")

    ordered_modes = [
        "csarc init",
        "csarc adopt",
        "csarc update",
        "csarc status",
    ]
    positions = [prompts.index(mode) for mode in ordered_modes]
    assert positions == sorted(positions)
    assert prompts.rstrip("\n").endswith(status_prompt("v9.9.9", sha))


def test_status_prompt_renders_pinned_tag_and_sha_correctly() -> None:
    """Verify tag/SHA substitution and install-status guidance content."""
    sha = "d" * 40
    rendered = status_prompt("v3.4.5", sha)

    assert "核准版本：v3.4.5" in rendered
    assert f"核准 commit：{sha}" in rendered
    assert (
        "安裝指南：https://raw.githubusercontent.com/"
        f"{REPOSITORY}/{sha}/docs/agent-install.md" in rendered
    )
    command = (
        "uvx --python 3.14 --from "
        f"'git+https://github.com/{REPOSITORY}.git@{sha}' csarc status"
    )
    assert f"`{command}`" in rendered
    assert f"--to v3.4.5 --expected-sha {sha} --json" in rendered
    # Mirrors every state the everyday, unpinned "自動判斷" prompt (README.md)
    # and `detect_install_state()` cover, so the pinned variant stays in sync.
    assert "create 或 adopt 或 update" in rendered
    assert "current 時回報不需動作" in rendered
    assert "policy-only-update" in rendered
    assert "scripts/apply-repository-settings.sh plan" in rendered
    assert "--dry-run" not in rendered
