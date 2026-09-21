"""Tests for the root/rendered jinja workflow drift check (Issue #739)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

check_jinja_workflow_drift = importlib.import_module(
    "check_jinja_workflow_drift"
)


def test_identical_content_has_no_drift() -> None:
    """Two files with the same relevant content never disagree."""
    text = "name: CI\njobs:\n  verify:\n    steps:\n      - run: echo hi\n"

    assert check_jinja_workflow_drift.find_drift(text, text) == []


def test_comment_and_blank_line_differences_are_ignored() -> None:
    """Comment wording and blank-line placement never change CI behavior."""
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      # root-only explanation\n      - run: echo hi\n"
    )
    rendered = (
        "jobs:\n  verify:\n    steps:\n\n"
        "      # a differently worded, template-only explanation\n"
        "      - run: echo hi\n"
    )

    assert check_jinja_workflow_drift.find_drift(root, rendered) == []


def test_declared_allowed_difference_does_not_false_positive() -> None:
    """An explicitly declared line-level difference is not reported."""
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: ./scripts/verify-template.sh\n"
    )
    rendered = "jobs:\n  verify:\n    steps:\n      - run: ./scripts/verify\n"
    allowed = {
        ("- run: ./scripts/verify-template.sh", "- run: ./scripts/verify")
    }

    assert check_jinja_workflow_drift.find_drift(root, rendered, allowed) == []


def test_repeated_declared_difference_is_normalized_per_occurrence() -> None:
    """One declared substitution covers every matching paired occurrence."""
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: ./scripts/verify-template.sh\n"
        "      - run: ./scripts/verify-template.sh\n"
    )
    rendered = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: ./scripts/verify\n"
        "      - run: ./scripts/verify\n"
    )
    allowed = {
        ("- run: ./scripts/verify-template.sh", "- run: ./scripts/verify")
    }

    assert check_jinja_workflow_drift.find_drift(root, rendered, allowed) == []


def test_undeclared_difference_is_reported() -> None:
    """An artificially introduced, undeclared difference fails the check."""
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      - uses: actions/setup-node@abc\n"
        '        with:\n          node-version: "24"\n'
    )
    rendered = (
        "jobs:\n  verify:\n    steps:\n      - uses: actions/setup-node@abc\n"
        '        with:\n          node-version: "24"\n          cache: pnpm\n'
    )

    errors = check_jinja_workflow_drift.find_drift(root, rendered)

    assert len(errors) == 1
    assert "cache: pnpm" in errors[0]


def test_declared_difference_elsewhere_does_not_mask_a_real_one() -> None:
    """An allowlist entry only covers its own line pair, not every hunk."""
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: ./scripts/verify-template.sh\n"
        "      - uses: actions/setup-node@abc\n"
        "        with:\n"
        '          node-version: "24"\n'
    )
    rendered = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: ./scripts/verify\n"
        "      - uses: actions/setup-node@abc\n"
        "        with:\n"
        '          node-version: "24"\n'
        "          cache: pnpm\n"
    )
    allowed = {
        ("- run: ./scripts/verify-template.sh", "- run: ./scripts/verify")
    }

    errors = check_jinja_workflow_drift.find_drift(root, rendered, allowed)

    assert len(errors) == 1
    assert "cache: pnpm" in errors[0]
    assert "verify-template.sh" not in errors[0]


def test_adjacent_unrelated_change_does_not_break_a_declared_pair() -> None:
    """Regression for the code-review finding: hunk-boundary fragility.

    difflib.SequenceMatcher can bundle an unrelated deleted line into the
    same 'replace' opcode as a declared substitution just because it sits
    on an adjacent line. Matching used to require the whole hunk to equal
    one allowlist entry, so this harmless neighbor made the *declared*
    substitution fail too. It must now report only the unrelated line.
    """
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: ./scripts/verify-template.sh\n"
        "      - name: this step is about to be removed, unrelated to the\n"
        "          verify-script-name substitution declared below\n"
        "      - uses: actions/checkout@abc\n"
    )
    rendered = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: ./scripts/verify\n"
        "      - uses: actions/checkout@abc\n"
    )
    allowed = {
        ("- run: ./scripts/verify-template.sh", "- run: ./scripts/verify")
    }

    errors = check_jinja_workflow_drift.find_drift(root, rendered, allowed)

    assert len(errors) == 1
    assert "verify-template.sh" not in errors[0]
    assert "verify-script-name substitution declared below" in errors[0]


def test_diagnostic_output_is_already_stripped() -> None:
    """The printed lines must be pasteable straight into the allowlist.

    Regression for the code-review finding that the diagnostic used to
    print the original, indented line instead of the stripped text an
    ALLOWED_LINE_DIFFERENCES entry actually expects.
    """
    root = "jobs:\n  verify:\n    steps:\n          node-version: '24'\n"
    rendered = (
        "jobs:\n  verify:\n    steps:\n"
        "          node-version: '24'\n          cache: pnpm\n"
    )

    errors = check_jinja_workflow_drift.find_drift(root, rendered)

    assert len(errors) == 1
    assert '"cache: pnpm"' in errors[0]
    assert "          cache: pnpm" not in errors[0]


def test_paired_workflow_files_skips_jinja_without_a_root_counterpart(
    tmp_path: Path,
) -> None:
    """A downstream-only jinja workflow (no root file) is out of scope."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "template" / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n")
    (
        tmp_path / "template" / ".github" / "workflows" / "ci.yml.jinja"
    ).write_text("name: CI\n")
    (
        tmp_path / "template" / ".github" / "workflows" / "codeql.yml.jinja"
    ).write_text("name: CodeQL\n")

    pairs = check_jinja_workflow_drift.paired_workflow_files(tmp_path)

    assert [jinja.name for _root, jinja in pairs] == ["ci.yml.jinja"]


def test_real_repository_workflows_have_no_undeclared_drift() -> None:
    """The checked-in workflows have no undeclared behavioral drift."""
    assert check_jinja_workflow_drift.check(ROOT) == []

    for (
        jinja_name,
        allowed,
    ) in check_jinja_workflow_drift.ALLOWED_LINE_DIFFERENCES.items():
        root_workflow = ROOT / ".github" / "workflows" / jinja_name[:-6]
        root_text = root_workflow.read_text(encoding="utf-8")
        for root_line, _rendered_line in allowed:
            assert root_line in root_text, (
                f"allowlisted root line {root_line!r} no longer appears in "
                f"{root_workflow.relative_to(ROOT)} -- update or remove the "
                "ALLOWED_LINE_DIFFERENCES entry in "
                "scripts/check_jinja_workflow_drift.py"
            )


def test_generated_managed_paths_normalize_without_masking_other_drift() -> (
    None
):
    """Only ownership-path changes are normalized; behavior still differs."""
    root = (
        "run: python3 scripts/release_policy.py plan --mode safe\n"
        "config-file: release-please-config.json\n"
        "manifest-file: .release-please-manifest.json\n"
    )
    rendered = (
        "run: python3 .csarc/scripts/release_policy.py plan --mode safe\n"
        "config-file: .csarc/release-please-config.json\n"
        "manifest-file: .csarc/release-please-manifest.json\n"
    )
    changed_behavior = rendered.replace("--mode safe", "--mode unsafe")

    assert check_jinja_workflow_drift.find_drift(root, rendered) == []
    assert (
        len(check_jinja_workflow_drift.find_drift(root, changed_behavior)) == 1
    )


def test_a_recognized_covered_condition_has_no_problem() -> None:
    """A plain "lang" in languages check, direct or aliased, is covered."""
    jinja_text = (
        '{% set has_rust = "rust" in languages -%}\n'
        "{% if has_rust %}\nrust stuff\n{% endif %}\n"
        '{% if "python" in languages %}\npython stuff\n{% endif %}\n'
    )

    assert (
        check_jinja_workflow_drift.find_uncovered_conditionals(
            jinja_text, ["python", "rust", "typescript"]
        )
        == []
    )


def test_an_unrecognized_condition_shape_is_reported() -> None:
    """A conditional this check cannot prove covered must be surfaced.

    Regression for the code-review finding that REPRESENTATIVE_LANGUAGES
    coverage was not self-verifying: a future conditional gated on
    something other than a "lang" in languages check must fail loudly,
    not render silently unexercised.
    """
    jinja_text = '{% if python_support_mode == "latest" %}\nx\n{% endif %}\n'

    problems = check_jinja_workflow_drift.find_uncovered_conditionals(
        jinja_text, ["python", "rust", "typescript"]
    )

    assert len(problems) == 1
    assert "python_support_mode" in problems[0]


def test_a_language_missing_from_representative_languages_is_reported() -> None:
    """A recognized check for a language not in the fixture list is flagged."""
    jinja_text = '{% if "go" in languages %}\nx\n{% endif %}\n'

    problems = check_jinja_workflow_drift.find_uncovered_conditionals(
        jinja_text, ["python", "rust", "typescript"]
    )

    assert len(problems) == 1
    assert "'go'" in problems[0]


def test_every_paired_workflow_conditional_is_covered() -> None:
    """The real REPRESENTATIVE_LANGUAGES must cover both real templates."""
    for (
        _root_workflow,
        jinja_path,
    ) in check_jinja_workflow_drift.paired_workflow_files(ROOT):
        problems = check_jinja_workflow_drift.find_uncovered_conditionals(
            jinja_path.read_text(encoding="utf-8"),
            check_jinja_workflow_drift.REPRESENTATIVE_LANGUAGES,
        )
        assert problems == [], f"{jinja_path}: {problems}"


def test_comment_inside_a_block_scalar_is_kept_verbatim() -> None:
    """A '#'-prefixed shell line inside `run: |` is content, not YAML prose.

    Regression for the code-review finding that _relevant_lines used to
    strip any '#'-prefixed line unconditionally, which would also hide a
    genuine difference in a heredoc/shebang-style line that happens to
    start with '#' for non-comment reasons (a shebang, for example).
    """
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: |\n          #!/bin/bash\n          echo hi\n"
    )
    rendered = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: |\n          #!/usr/bin/env python3\n          echo hi\n"
    )

    errors = check_jinja_workflow_drift.find_drift(root, rendered)

    assert len(errors) == 1
    assert "#!/bin/bash" in errors[0]
    assert "#!/usr/bin/env python3" in errors[0]


def test_comment_outside_a_block_scalar_is_still_ignored() -> None:
    """A genuine YAML-level comment is still normalized away as before."""
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      # a root explanation\n      - run: echo hi\n"
    )
    rendered = (
        "jobs:\n  verify:\n    steps:\n"
        "      # a different explanation\n      - run: echo hi\n"
    )

    assert check_jinja_workflow_drift.find_drift(root, rendered) == []


def test_comment_after_a_block_scalar_closes_is_still_ignored() -> None:
    """A comment at/below the block scalar's own indent is real YAML prose."""
    root = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: |\n          echo hi\n"
        "      # back at step level, a real comment\n"
        "      - run: echo bye\n"
    )
    rendered = (
        "jobs:\n  verify:\n    steps:\n"
        "      - run: |\n          echo hi\n"
        "      # a differently worded real comment\n"
        "      - run: echo bye\n"
    )

    assert check_jinja_workflow_drift.find_drift(root, rendered) == []


def test_check_reports_a_render_failure_without_raising(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A template render failure is caught and formatted."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "template" / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n")
    (
        tmp_path / "template" / ".github" / "workflows" / "ci.yml.jinja"
    ).write_text("name: CI\n")
    (tmp_path / "copier.yml").write_text("{}\n")

    def broken_render(_repo_root: Path, _dest: Path) -> None:
        raise OSError("simulated render failure")

    monkeypatch.setattr(
        check_jinja_workflow_drift, "render_template", broken_render
    )

    errors = check_jinja_workflow_drift.check(tmp_path)

    assert len(errors) == 1
    assert "simulated render failure" in errors[0]
