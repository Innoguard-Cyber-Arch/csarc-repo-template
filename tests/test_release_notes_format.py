"""Regression proof for the release-notes format contract (Issue #616).

The design decision (recorded in docs/ci-policy.md's "Release 說明文字的最低
格式規範" section) is that no extra format-consistency *checker* is needed
because there is only one code path that ever writes a GitHub Release body:
scripts/converge-release-tag calling `gh release create ... --generate-notes`.
That single call site is what these tests protect -- not the free-form text
GitHub itself generates, which this repository does not control and should
not assert against.

Two things could quietly break the "hosted and local paths cannot drift"
guarantee documented above:

1. scripts/converge-release-tag stops passing --generate-notes (or --title),
   so the Release body is no longer GitHub's deterministic, PR-derived
   summary.
2. A second call site is introduced somewhere in scripts/ or
   .github/workflows/ (root or the template/ mirror) that creates or edits a
   Release with free-form --notes/--notes-file text, defeating the
   single-implementation guarantee the ci-policy.md section relies on.

Both are cheap, source-level invariants -- exactly the kind of check
tests/test_journey07_release.py already uses for the surrounding release
wiring -- so this module follows the same source-text-assertion style rather
than re-testing converge-release-tag's runtime behavior (already covered by
tests/test_release_convergence.py and tests/test_release_publish.py).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]

# The one legitimate place a GitHub Release is created. Every other script
# or workflow in the scan scope below must not create or edit a Release with
# its own free-form notes text.
NOTES_OWNER = "scripts/converge-release-tag"

SCAN_GLOBS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "template/.github/workflows/*.yml",
    "template/.github/workflows/*.yaml",
)
SCAN_DIRS = ("scripts", "template/scripts")


def test_converge_release_tag_is_the_single_generate_notes_call() -> None:
    """The only `gh release create` call must trust GitHub's own notes."""
    source = (ROOT / NOTES_OWNER).read_text(encoding="utf-8")

    assert 'gh release create "$tag" --target "$sha" \\' in source
    assert '--title "$tag" --draft --generate-notes' in source
    # Never pair --generate-notes with a competing free-form flag: GitHub
    # rejects --notes/--notes-file alongside --generate-notes, but a future
    # edit could still drop --generate-notes in favor of one of them.
    assert "--notes" not in source
    assert "--notes-file" not in source


def test_no_other_release_notes_writer_exists_in_scope() -> None:
    """Guard the single-implementation claim the ci-policy.md section makes.

    Scans the same scope tests/test_release_convergence.py and
    scripts/pr_lifecycle.py::scan_writers already treat as "repository
    automation" (root and template/ workflows and scripts) for any call
    that creates or edits a Release with its own notes text. Only
    scripts/converge-release-tag (and its byte-identical template/ mirror,
    synced by scripts/sync-paired-files.sh) may create a Release at all.
    """
    candidates: list[Path] = []
    for pattern in SCAN_GLOBS:
        candidates.extend(ROOT.glob(pattern))
    for directory in SCAN_DIRS:
        candidates.extend((ROOT / directory).rglob("*"))

    owners = {ROOT / NOTES_OWNER, ROOT / "template" / NOTES_OWNER}
    violations: list[str] = []
    for path in sorted(set(candidates)):
        if not path.is_file() or path in owners:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "gh release create" in text:
            violations.append(f"{path.relative_to(ROOT)}: gh release create")
        if "--notes" in text or "--notes-file" in text:
            violations.append(f"{path.relative_to(ROOT)}: --notes flag")

    assert not violations, (
        "Found a release-notes writer outside scripts/converge-release-tag "
        f"(see docs/ci-policy.md's release-notes format section): {violations}"
    )


def test_publish_release_never_overwrites_generated_notes() -> None:
    """scripts/publish-release only flips draft state, never rewrites notes."""
    source = (ROOT / "scripts/publish-release").read_text(encoding="utf-8")

    assert 'gh release edit "$tag" --draft' in source
    assert 'gh release edit "$tag" --draft=false --latest' in source
    assert "--notes" not in source
    assert "--notes-file" not in source


def test_converge_release_tag_is_synced_to_the_template_mirror() -> None:
    """The format contract has one implementation, not a root/template pair."""
    root_text = (ROOT / NOTES_OWNER).read_text(encoding="utf-8")
    template_text = (ROOT / "template" / NOTES_OWNER).read_text(
        encoding="utf-8"
    )

    assert root_text == template_text


def test_ci_policy_records_the_minimum_release_notes_fields() -> None:
    """The format decision (#616) must stay legible in docs/ci-policy.md."""
    policy = (ROOT / "docs/ci-policy.md").read_text(encoding="utf-8")

    assert "Release 說明文字的最低格式規範（#616）" in policy  # noqa: RUF001
    assert "只有一個程式碼路徑會建立 Release 說明文字" in policy
    assert "不需要額外的結構化格式一致性檢查腳本" in policy
    assert "tests/test_release_notes_format.py" in policy


def test_decision_site_explains_where_to_read_release_history() -> None:
    """An adopter must be able to find this without reading raw Release JSON."""
    zh = (ROOT / "site/content/_index.zh-tw.md").read_text(encoding="utf-8")
    en = (ROOT / "site/content/_index.en.md").read_text(encoding="utf-8")

    for source in (zh, en):
        assert 'key="release-notes-format"' in source
        assert "--generate-notes" in source
        assert "CHANGELOG.md" in source
