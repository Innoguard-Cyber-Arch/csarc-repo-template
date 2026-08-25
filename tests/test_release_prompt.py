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
prompt = PROMPT_MODULE["prompt"]


def test_render_uses_one_release_identity_everywhere() -> None:
    """Keep the release tag, SHA, guide URL, and provenance aligned."""
    sha = "a" * 40
    prompts, provenance_text, notes = render("v1.2.3", sha, "Release notes")
    provenance = json.loads(provenance_text)

    assert prompts.count(f"核准 commit：{sha}") == 3
    assert (
        prompts.count(f"https://raw.githubusercontent.com/{REPOSITORY}/{sha}/")
        == 3
    )
    source = f"git+https://github.com/{REPOSITORY}.git@{sha}"
    assert prompts.count(f"uvx --python 3.14 --from '{source}'") == 3
    assert "--from csarc-repo-cli" not in prompts
    assert "目標路徑：" not in prompts
    assert "csarc init" in prompts
    assert "csarc adopt" in prompts
    assert "--apply-plan" in prompts
    assert "檢視 repo 外的 Markdown、PDF 與 machine plan" in prompts
    assert "csarc update" in prompts
    assert provenance["commit_sha"] == sha
    assert provenance["guide_url"] in prompts
    assert provenance["release_tag"] == "v1.2.3"
    assert prompts.split("\n\n---", maxsplit=1)[0] not in notes
    assert "csarc adopt" in notes


@pytest.mark.parametrize(
    ("mode", "apply_command"),
    [
        (
            "init",
            "csarc init <target-path> --apply-plan PATH "
            "--yes --non-interactive",
        ),
        ("adopt", "csarc adopt --apply-plan PATH --yes --non-interactive"),
        ("update", "csarc update --apply-plan PATH --yes --non-interactive"),
    ],
)
def test_release_prompt_applies_only_the_reviewed_plan(
    mode: str, apply_command: str
) -> None:
    """Keep every release prompt aligned with the transactional CLI."""
    rendered = prompt(mode, "v1.2.3", "a" * 40)
    after_confirmation = rendered.split("確認後", maxsplit=1)[1]

    assert f"`{apply_command}`" in after_confirmation
    assert "--to" not in after_confirmation
    assert "--expected-sha" not in after_confirmation
    assert "相同 tag" not in after_confirmation


@pytest.mark.parametrize(
    ("tag", "sha"),
    [("1.2.3", "a" * 40), ("v1.2.3", "A" * 40), ("v1.2.3", "a" * 39)],
)
def test_render_rejects_untrusted_release_inputs(tag: str, sha: str) -> None:
    """Reject malformed tags and non-canonical commit identifiers."""
    with pytest.raises(ValueError):
        render(tag, sha, "Release notes")
