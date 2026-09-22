"""Tests for the immutable release setup prompt."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

PROMPT_MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "render_release_prompt.py")
)
REPOSITORY = PROMPT_MODULE["REPOSITORY"]
render = PROMPT_MODULE["render"]


def test_render_uses_one_release_identity_and_existing_setup_contract() -> None:
    """Keep one prompt pinned without introducing a second question schema."""
    sha = "a" * 40
    prompt = render("v1.2.3", sha)

    assert prompt.count(f"核准 commit：{sha}") == 1
    raw = f"https://raw.githubusercontent.com/{REPOSITORY}/{sha}"
    assert f"安裝指南：{raw}/docs/agent-install.md" in prompt
    assert f"設定來源：{raw}/copier.yml" in prompt
    source = f"git+https://github.com/{REPOSITORY}.git@{sha}"
    assert f"uvx --python 3.14 --from '{source}' csarc status" in prompt
    assert f"--to v1.2.3 --expected-sha {sha} --json" in prompt
    assert "接受建議值" in prompt
    assert "逐項客製" in prompt
    assert "--data" in prompt
    assert "dry-run JSON" in prompt
    assert "current 時只回報不需動作" in prompt
    assert "policy-only-update" in prompt
    assert ".csarc/scripts/apply-repository-settings.sh plan" in prompt
    assert "init／adopt／update prompt" not in prompt


@pytest.mark.parametrize(
    ("tag", "sha"),
    [("1.2.3", "a" * 40), ("v1.2.3", "A" * 40), ("v1.2.3", "a" * 39)],
)
def test_render_rejects_untrusted_release_inputs(tag: str, sha: str) -> None:
    """Reject malformed tags and non-canonical commit identifiers."""
    with pytest.raises(ValueError):
        render(tag, sha)
