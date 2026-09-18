#!/usr/bin/env python3
"""Extend the paired-file drift check to jinja workflows (#739).

`scripts/sync-paired-files.sh --check` only compares byte-for-byte
identical root/`template/` file pairs, so it never looks at
`template/.github/workflows/*.jinja`: a `.jinja` file is never
byte-identical to anything, since it renders differently per language
selection (see `scripts/check_action_pins.py`'s docstring for the same
observation about action-pin drift, Issue #755). That left root and
`template/`'s workflow content free to quietly diverge -- a stale pinned
Action version or a config knob added on only one side -- with nothing
to catch it before it shipped to every downstream repository.

This module renders `template/` with fixed, representative answers
(every language module selected, so every conditional branch a root
workflow exercises unconditionally also renders) and compares the result
line-for-line against each paired root workflow. Comments and blank
lines are stripped before comparing, since GitHub Actions gives neither
any runtime meaning and two workflows that differ only in prose or
spacing behave identically -- normalizing them out keeps the allowlist
focused on differences that can actually change behavior, instead of
forcing every reworded comment to be re-declared.

Every remaining difference must be declared in `ALLOWED_LINE_DIFFERENCES`
below, together with a comment recording why it is legitimate and
permanent (a downstream-only script name, a language-conditional block
root never renders because it never varies its own toolchain, etc.) --
never as a blanket file exclusion. An undeclared difference fails
closed and prints the exact lines that disagree.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

# Answers chosen to render every conditional branch a root workflow
# exercises unconditionally (root always sets up Python, pnpm/Node, and
# Rust toolchains for its own release-candidate validation), so the
# rendered template can be compared to root line-for-line instead of
# comparing against a project that skipped whole blocks. See copier.yml
# for the full question schema; the three overrides below match the
# ones scripts/verify-fast already passes for its own render smoke test,
# plus `languages` to select every module.
REPRESENTATIVE_ANSWERS: dict[str, object] = {
    "languages": ["python", "rust", "typescript"],
    "project_slug": "jinja-workflow-drift-check",
    "package_name": "jinja_workflow_drift_check",
    "code_owner": "@Innoguard-Cyber-Arch/template-maintainers",
}

# Issue #739: a small, exact allowlist of permanent, intentional
# differences between a root workflow and its rendered `template/`
# counterpart. Keyed by the `.jinja` file's own name. Each entry pairs
# the *stripped* root line(s) that get replaced with the *stripped*
# rendered line(s) that replace them, exactly as
# difflib.SequenceMatcher's opcodes report the hunk. Add an entry only
# with a reason; do not widen this to a whole-file or whole-job
# exclusion.
ALLOWED_LINE_DIFFERENCES: dict[
    str, set[tuple[tuple[str, ...], tuple[str, ...]]]
] = {
    "ci.yml.jinja": {
        # Downstream generated projects run their own, simpler
        # scripts/verify entry point; this repository verifies itself
        # with scripts/verify-template.sh instead (see
        # scripts/sync-paired-files.sh's module docstring: root is
        # canonical for what this repository exercises directly, but a
        # generated project is a different, simpler product).
        (
            ("./scripts/verify-template.sh",),
            ("./scripts/verify",),
        ),
    },
}


def paired_workflow_files(root: Path) -> list[tuple[Path, Path]]:
    """Return (root workflow, jinja template) for every paired jinja file.

    A jinja workflow with no root counterpart (for example
    codeql.yml.jinja or template-update.yml.jinja) is downstream-only by
    design and out of scope for this check -- there is no root file to
    compare it against.
    """
    template_workflows = root / "template" / ".github" / "workflows"
    pairs = []
    for jinja_path in sorted(template_workflows.glob("*.jinja")):
        root_workflow = (
            root / ".github" / "workflows" / jinja_path.name[: -len(".jinja")]
        )
        if root_workflow.is_file():
            pairs.append((root_workflow, jinja_path))
    return pairs


def _relevant_lines(text: str) -> list[str]:
    """Return text's lines with blank lines and whole-line comments removed."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(line)
    return lines


def find_drift(
    root_text: str,
    rendered_text: str,
    allowed: set[tuple[tuple[str, ...], tuple[str, ...]]] | None = None,
) -> list[str]:
    """Return one formatted message per undeclared difference.

    Compares root_text against rendered_text after stripping comments and
    blank lines from both. Every changed hunk is checked against
    `allowed` (stripped root lines, stripped rendered lines); an
    unmatched hunk is real drift and is rendered into the returned
    message showing both sides.
    """
    import difflib

    allowed = allowed or set()
    root_lines = _relevant_lines(root_text)
    rendered_lines = _relevant_lines(rendered_text)
    matcher = difflib.SequenceMatcher(
        None, root_lines, rendered_lines, autojunk=False
    )
    errors: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed = tuple(line.strip() for line in root_lines[i1:i2])
        added = tuple(line.strip() for line in rendered_lines[j1:j2])
        if (removed, added) in allowed:
            continue
        removed_block = "\n".join(
            f"      - {line}" for line in root_lines[i1:i2]
        )
        added_block = "\n".join(
            f"      + {line}" for line in rendered_lines[j1:j2]
        )
        errors.append(
            "root has:\n"
            + (removed_block or "      (nothing)")
            + "\n    rendered template has:\n"
            + (added_block or "      (nothing)")
        )
    return errors


def render_template(repo_root: Path, dest: Path) -> None:
    """Render template/ into dest with REPRESENTATIVE_ANSWERS, tasks skipped.

    Uses the same `copier copy --trust --defaults --vcs-ref HEAD`
    invocation scripts/verify-fast already runs for its own render smoke
    test (and src/csarc_cli/cli.py's copier_copy for update revisions),
    parameterized with fixed language answers instead of reusing that
    smoke test's answers, which default to no language module selected
    and would not render the toolchain blocks being compared here.
    `--skip-tasks` avoids running post-generation hooks (uv lock, pnpm
    install, cargo generate-lockfile, the repo-site build) that this
    check never reads and do not touch workflow files.
    """
    data_file = dest.parent / "jinja-workflow-drift-answers.yml"
    data_file.write_text(
        yaml.safe_dump(REPRESENTATIVE_ANSWERS, sort_keys=True), encoding="utf-8"
    )
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "copier",
            "copy",
            "--trust",
            "--defaults",
            "--skip-tasks",
            "--vcs-ref",
            "HEAD",
            "--data-file",
            str(data_file),
            str(repo_root),
            str(dest),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def check(root: Path) -> list[str]:
    """Render template/ once and return one message per drifted pair."""
    pairs = paired_workflow_files(root)
    if not pairs:
        return []
    with tempfile.TemporaryDirectory(prefix="jinja-workflow-drift-") as raw_tmp:
        dest = Path(raw_tmp) / "rendered"
        try:
            render_template(root, dest)
        except subprocess.CalledProcessError as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            return [
                "failed to render template/ for the jinja workflow drift "
                f"check:\n{output}"
            ]
        errors = []
        for root_workflow, jinja_path in pairs:
            rendered_path = dest / ".github" / "workflows" / root_workflow.name
            root_rel = root_workflow.relative_to(root)
            jinja_rel = jinja_path.relative_to(root)
            if not rendered_path.is_file():
                errors.append(
                    f"{jinja_rel} did not render {rendered_path.name} "
                    "into template/.github/workflows/"
                )
                continue
            allowed = ALLOWED_LINE_DIFFERENCES.get(jinja_path.name, set())
            diffs = find_drift(
                root_workflow.read_text(encoding="utf-8"),
                rendered_path.read_text(encoding="utf-8"),
                allowed,
            )
            if diffs:
                errors.append(
                    f"{root_rel} and rendered {jinja_rel} disagree:\n    "
                    + "\n    ".join(diffs)
                )
        return errors


def main(argv: list[str] | None = None) -> int:
    """Fail closed and print every undeclared root-vs-rendered drift."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args(argv)
    errors = check(args.root)
    if errors:
        for error in errors:
            sys.stderr.write(f"jinja workflow drift: {error}\n")
        sys.stderr.write(
            "Undeclared difference between a root workflow and its "
            "rendered template/ counterpart. Fix root or the .jinja "
            "template so they agree, or add an explicit, reasoned entry "
            "to ALLOWED_LINE_DIFFERENCES in "
            "scripts/check_jinja_workflow_drift.py.\n"
        )
        return 1
    pairs = len(paired_workflow_files(args.root))
    sys.stdout.write(
        f"{pairs} paired jinja workflow(s) match root after rendering.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
