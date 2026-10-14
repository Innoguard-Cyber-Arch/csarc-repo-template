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
import re
import sys
import tempfile
from pathlib import Path

from jinja2 import Environment, StrictUndefined, TemplateError

# Answers chosen to match root behavior while rendering every language
# branch a root workflow exercises during full verification. See copier.yml
# for the full question schema. The downstream-only release-trigger variant
# has its own explicit contract test in tests/test_journey07_release.py.
#
# Kept as its own typed constant (not just a value inside
# REPRESENTATIVE_ANSWERS) because find_uncovered_conditionals() below
# also needs it directly: REPRESENTATIVE_ANSWERS must keep exercising
# every conditional branch either paired workflow template has, and that
# check reads this list to prove it.
REPRESENTATIVE_LANGUAGES: list[str] = ["go", "python", "rust", "typescript"]

REPRESENTATIVE_ANSWERS: dict[str, object] = {
    "languages": REPRESENTATIVE_LANGUAGES,
    "python_support_mode": "latest",
    "python_min_version": "3.12",
    "project_slug": "jinja-workflow-drift-check",
    "package_name": "jinja_workflow_drift_check",
    "code_owner": "@Innoguard-Cyber-Arch/template-maintainers",
    "lifecycle": ["issues", "milestones"],
    "release_trigger": "manual",
}

# A paired workflow may have a downstream-only configuration branch that the
# root deliberately does not use. Keep this list exact and require a separate
# regression test for every entry instead of teaching the drift checker a
# broad expression language.
ALLOWED_CONDITIONS: frozenset[str] = frozenset({"release_trigger == 'main'"})

# Issue #739: a small, exact allowlist of permanent, intentional
# differences between a root workflow and its rendered `template/`
# counterpart. Keyed by the `.jinja` file's own name. Each entry is one
# *stripped* root line paired with the one *stripped* rendered line that
# legitimately replaces it. Matching happens per individual line (see
# _subtract_allowed_pairs), not per whole difflib hunk, so an unrelated
# change that happens to land in the same hunk (for example, on an
# adjacent line) cannot break an already-declared, unrelated
# substitution. Add an entry only with a reason; do not widen this to a
# whole-file or whole-job exclusion. The diagnostic printed for an
# undeclared difference (see find_drift) already prints stripped lines,
# so they can be pasted straight into a new entry here.
_ROOT_ACTIVE = (
    "if: ${{ steps.sync.outputs.clean != 'true' && "
    "(steps.reuse.outputs.reuse != 'true' || "
    "(github.event_name == 'pull_request_target' && "
    "github.event.pull_request.base.ref == 'main' && "
    "startsWith(github.event.pull_request.head.ref, 'release/v') && "
    "steps.release.outputs.ownership == 'csarc-owned')) }}"
)
_ROOT_FULL = (
    "if: ${{ steps.reuse.outputs.reuse != 'true' && "
    "steps.sync.outputs.clean != 'true' && "
    "steps.effective.outputs.suite == 'full' }}"
)
_DOWNSTREAM_PRODUCT_OR_OSV = (
    "if: ${{ steps.sync.outputs.clean != 'true' && "
    "((steps.reuse.outputs.reuse != 'true' && "
    "(steps.effective.outputs.suite == 'full' || "
    "steps.plan.outputs.run_project == 'true' || "
    "steps.plan.outputs.run_osv == 'true')) || "
    "(github.event_name == 'pull_request_target' && "
    "github.event.pull_request.base.ref == 'main' && "
    "startsWith(github.event.pull_request.head.ref, 'release/v') && "
    "steps.release.outputs.ownership == 'csarc-owned')) }}"
)
_DOWNSTREAM_PRODUCT = (
    "if: ${{ steps.sync.outputs.clean != 'true' && "
    "((steps.reuse.outputs.reuse != 'true' && "
    "(steps.effective.outputs.suite == 'full' || "
    "steps.plan.outputs.run_project == 'true')) || "
    "(github.event_name == 'pull_request_target' && "
    "github.event.pull_request.base.ref == 'main' && "
    "startsWith(github.event.pull_request.head.ref, 'release/v') && "
    "steps.release.outputs.ownership == 'csarc-owned')) }}"
)


# Issue #1086: the root hosted `verify` loads its entry point, stage gate,
# router, and config reader from the trusted pull request base and records
# `executor=trusted-base`. Generated projects keep their `.csarc/scripts`
# entry points until #1069 (G2) ports the same executor to the template, so
# these root lines are declared instead of rendered.
_EXECUTE_NAME = (
    "- name: Execute trusted verification "
    "tier=${{ steps.effective.outputs.suite }} "
    "scopes=${{ steps.plan.outputs.scopes }} "
    "tree=${{ steps.identity.outputs.tree }} "
    "command=${{ steps.identity.outputs.command }} "
    "base=${{ steps.identity.outputs.base }} "
    "base-sha=${{ steps.identity.outputs.base_sha }} "
    "labels=${{ steps.identity.outputs.labels }} "
    "release=${{ steps.identity.outputs.release }}"
)
_EXECUTOR_CLAIM = (
    "${{ steps.trusted.outputs.executor == 'trusted-base' && "
    "' executor=trusted-base' || '' }}"
)
_OWNERSHIP_READER = (
    'python3 "$RUNNER_TEMP/trusted-verification/csarc_config.py" '
    "release_ownership"
)
_TRUSTED_EXECUTOR_BLOCKS: tuple[tuple[str, ...], ...] = (
    # Issue #1111: the root trusted steps run `python3 scripts/...` from the
    # base before the toolchain setup, so root installs Python 3.14 first.
    # Generated projects get the same need with #1069's executor port.
    (
        "- name: Set up Python 3.14 for the trusted verification policy",
        "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 "
        "# v7.0.0",
        "with:",
        'python-version: "3.14"',
    ),
    ("id: trusted",),
    (
        "# Issue #1086: the entry point, stage gate, router, and config",
        "# reader that decide the required result come from this trusted",
        "# base, never from the candidate checked out next.",
        "if [[ -f scripts/trusted_executor.py ]]; then",
        "python3 scripts/trusted_executor.py prepare \\",
        '--source "$GITHUB_WORKSPACE" \\',
        '--destination "$RUNNER_TEMP/trusted-executor"',
        'echo "executor=trusted-base" >> "$GITHUB_OUTPUT"',
        "else",
        'echo "::warning title=Trusted verification executor::This pull '
        "request base predates the trusted executor (Issue #1086); "
        "verification runs the candidate entry point and is recorded as "
        'candidate-legacy until the base is synchronized."',
        'echo "executor=candidate-legacy" >> "$GITHUB_OUTPUT"',
        "fi",
    ),
    (
        f'ownership="$({_OWNERSHIP_READER})"',
        'echo "ownership=$ownership" >> "$GITHUB_OUTPUT"',
    ),
    (
        'cp ci-plan.json "$RUNNER_TEMP/trusted-ci-plan.json"',
        "printf '%s\\0' --event \"$EVENT_NAME\" "
        '--base "${PR_BASE#refs/heads/}" --head "${PR_HEAD#refs/heads/}" '
        '--labels "$LABELS" --draft "$PR_DRAFT" --files-from "$files" '
        '"${args[@]}" "${sync_args[@]}" > "$RUNNER_TEMP/trusted-router-args"',
    ),
    ("EXECUTOR: ${{ steps.trusted.outputs.executor }}",),
    (
        "# The authoritative entry point is the trusted-base copy staged",
        "# before checkout; it runs the checks inside the exact candidate",
        "# tree. Only a base that predates Issue #1086 falls back to the",
        "# candidate entry point, and its evidence omits "
        "executor=trusted-base.",
        'entry_root="$GITHUB_WORKSPACE"',
        'if [[ "$EXECUTOR" == "trusted-base" ]]; then',
        'entry_root="$RUNNER_TEMP/trusted-executor"',
        'python3 "$RUNNER_TEMP/trusted-verification/trusted_executor.py" \\',
        'verify --destination "$entry_root"',
        'export CSARC_VERIFICATION_SUBJECT_ROOT="$GITHUB_WORKSPACE"',
        "fi",
    ),
    (
        "- name: Candidate gate self-test (non-authoritative)",
        "if: ${{ !cancelled() && "
        "steps.trusted.outputs.executor == 'trusted-base' && "
        "steps.plan.outcome == 'success' }}",
        "continue-on-error: true",
        "timeout-minutes: 5",
        "env:",
        "TRUSTED_OWNERSHIP: ${{ steps.release.outputs.ownership }}",
        "run: |",
        'python3 "$RUNNER_TEMP/trusted-verification/trusted_executor.py" '
        "self-test \\",
        '--candidate-root "$GITHUB_WORKSPACE" \\',
        '--router-args "$RUNNER_TEMP/trusted-router-args" \\',
        '--trusted-plan "$RUNNER_TEMP/trusted-ci-plan.json" \\',
        '--trusted-ownership "$TRUSTED_OWNERSHIP" \\',
        '--changed-files "$RUNNER_TEMP/changed-files" \\',
        '--summary "$GITHUB_STEP_SUMMARY"',
    ),
)


ALLOWED_LINE_DIFFERENCES: dict[str, set[tuple[str, str]]] = {
    "ci.yml.jinja": {
        # Issue #1086 (root only until #1069): the execution claim, the
        # staged trusted entry points, and the fail-closed ownership read.
        (_EXECUTE_NAME + _EXECUTOR_CLAIM, _EXECUTE_NAME),
        ('"$entry_root/scripts/verify-template.sh"', "./scripts/verify"),
        ('"$entry_root/scripts/verify-fast"', "./scripts/verify-fast"),
        (
            "run: |",
            f'run: echo "ownership=$({_OWNERSHIP_READER})" >> "$GITHUB_OUTPUT"',
        ),
        # Downstream generated projects run their own, simpler
        # scripts/verify entry point; this repository verifies itself
        # with scripts/verify-template.sh instead (see
        # scripts/sync-paired-files.sh's module docstring: root is
        # canonical for what this repository exercises directly, but a
        # generated project is a different, simpler product).
        ("./scripts/verify-template.sh", "./scripts/verify"),
        (
            'command="./scripts/verify-template.sh"',
            'command="./scripts/verify"',
        ),
        # Root release packaging is Python-only; generated projects install
        # only their selected package toolchains. Outside a guided release,
        # generated projects can still skip product toolchains when the
        # selected scopes do not run project or dependency checks.
        (_ROOT_ACTIVE, _DOWNSTREAM_PRODUCT_OR_OSV),
        (_ROOT_FULL, _DOWNSTREAM_PRODUCT_OR_OSV),
        (_ROOT_FULL, _DOWNSTREAM_PRODUCT),
    },
    "release.yml.jinja": {
        # Generated repositories expose scripts/verify; this template
        # repository keeps the full release aggregator under its longer name.
        (
            "./scripts/verify-template.sh",
            "./scripts/verify",
        ),
    },
}

# Issue #1036: pull_request_target always runs the workflow YAML from main,
# so a toolchain a delivery branch will require must be prepared on main
# before the template can offer that language. Each entry is one exact,
# contiguous run of stripped root lines with no rendered counterpart; it is
# consumed at most once per file, so it cannot hide any other drift.
# #944 gave the template its own Go setup; #1086 declares the root-only
# trusted-executor lines until #1069 ports them to generated projects.
ROOT_ONLY_BLOCKS: dict[str, tuple[tuple[str, ...], ...]] = {
    "ci.yml.jinja": _TRUSTED_EXECUTOR_BLOCKS,
}

# Issue #742 moved generated-project internals under .csarc/ while the
# template repository intentionally keeps its own tools and release metadata
# at the root. Normalize only those two established ownership boundaries;
# command names, arguments, and every other line still compare exactly.
TEMPLATE_PATH_NORMALIZATIONS: tuple[tuple[str, str], ...] = (
    (".csarc/scripts/", "scripts/"),
    (".csarc/release-please-config.json", "release-please-config.json"),
    (".csarc/release-please-manifest.json", ".release-please-manifest.json"),
)

_JINJA_CONDITION_TAG = re.compile(r"{%-?\s*(?:if|elif)\s+(.+?)\s*-?%}")
_SET_ALIAS = re.compile(r"{%-?\s*set\s+(\w+)\s*=\s*(.+?)\s*-?%}")
_LANGUAGE_MEMBERSHIP = re.compile(r"""^["'](\w+)["']\s+in\s+languages$""")

# Heuristic, not a full YAML parser: a line whose value opens a literal
# (`|`) or folded (`>`) block scalar, optionally with a chomping/indent
# indicator. Good enough for the workflow files this check reads today;
# see _relevant_lines for why it matters.
_BLOCK_SCALAR_OPEN = re.compile(r":\s*[|>][+-]?\d?\s*$")


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


def find_uncovered_conditionals(
    jinja_text: str, languages: list[str]
) -> list[str]:
    """Return one message per `{% if/elif %}` condition not provably true.

    REPRESENTATIVE_ANSWERS must keep exercising every conditional branch
    a paired workflow template has, or a stale value inside an
    unrendered branch would drift silently -- this check would never see
    it. This recognizes only a bare `"lang" in languages` check, given
    directly or through a `{% set name = "lang" in languages %}` alias
    referenced by name -- the only shape either paired workflow uses
    today. A condition of any other shape cannot be proven covered and
    is reported, so a future conditional gated on something else (a
    different copier.yml question, for example) forces
    REPRESENTATIVE_LANGUAGES and this function to be extended
    deliberately, instead of silently rendering incomplete forever.
    """
    aliases = dict(_SET_ALIAS.findall(jinja_text))
    problems: list[str] = []
    for raw_condition in _JINJA_CONDITION_TAG.findall(jinja_text):
        condition = raw_condition.strip()
        if condition in ALLOWED_CONDITIONS:
            continue
        expr = aliases.get(condition, condition).strip()
        match = _LANGUAGE_MEMBERSHIP.match(expr)
        if match is None:
            problems.append(
                f"condition {condition!r} is not a recognized "
                '"lang" in languages check (directly, or through a '
                "{% set name = ... %} alias) -- extend "
                "find_uncovered_conditionals in "
                "scripts/check_jinja_workflow_drift.py (and "
                "REPRESENTATIVE_LANGUAGES if needed) before trusting "
                "this check for it"
            )
            continue
        language = match.group(1)
        if language not in languages:
            problems.append(
                f"condition {condition!r} needs {language!r} added to "
                "REPRESENTATIVE_LANGUAGES in "
                "scripts/check_jinja_workflow_drift.py so this branch "
                "actually renders"
            )
    return problems


def _relevant_lines(text: str) -> list[str]:
    """Return text's lines with blank lines and YAML-level comments removed.

    A line is only ever treated as a comment when it sits outside any
    `key: |` / `key: >` block scalar (a `run:` step's shell script, for
    example). Inside one, a leading '#' can be meaningful content (a
    shebang, or a shell comment whose exact wording is itself the
    behavior difference this check exists to catch) rather than YAML
    prose, so lines there are always kept verbatim. Not triggered by any
    current workflow content -- both real files only ever comment at the
    YAML level -- but a future `run: |` block could add one.
    """
    lines: list[str] = []
    block_scalar_indent: int | None = None
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if block_scalar_indent is not None:
            if stripped and indent <= block_scalar_indent:
                block_scalar_indent = None  # scalar just ended; re-evaluate
            else:
                if stripped:
                    lines.append(line)
                continue
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        lines.append(line)
        if _BLOCK_SCALAR_OPEN.search(line):
            block_scalar_indent = indent
    return lines


def _normalize_template_paths(lines: list[str]) -> list[str]:
    """Map generated-project-owned paths to their root counterparts."""
    normalized: list[str] = []
    for line in lines:
        for template_path, root_path in TEMPLATE_PATH_NORMALIZATIONS:
            line = line.replace(template_path, root_path)
        normalized.append(line)
    return normalized


def _subtract_allowed_pairs(
    removed: list[str], added: list[str], allowed: set[tuple[str, str]]
) -> tuple[list[str], list[str]]:
    """Remove every declared (root-line, rendered-line) pair from a hunk.

    Matching happens per individual line rather than treating the whole
    hunk as one unit: difflib.SequenceMatcher groups nearby changes into
    a single opcode based on line similarity, so an unrelated edit next
    to a declared substitution (for example, on an adjacent line) can
    land in the same hunk as that substitution. Requiring the entire
    hunk to match one allowlist entry would then fail closed on a
    harmless, unrelated neighbor. Consuming declared pairs individually
    instead reports only what is actually left over -- the real,
    undeclared drift, if any -- regardless of how difflib happened to
    group the surrounding lines.
    """
    remaining_removed = list(removed)
    remaining_added = list(added)
    for root_line, rendered_line in allowed:
        while (
            root_line in remaining_removed and rendered_line in remaining_added
        ):
            remaining_removed.remove(root_line)
            remaining_added.remove(rendered_line)
    return remaining_removed, remaining_added


def _subtract_root_only_blocks(
    removed: list[str], blocks: list[tuple[str, ...]]
) -> list[str]:
    """Remove each still-unused declared root-only block from one hunk."""
    remaining = list(removed)
    for block in list(blocks):
        width = len(block)
        for start in range(len(remaining) - width + 1):
            if tuple(remaining[start : start + width]) == block:
                del remaining[start : start + width]
                blocks.remove(block)
                break
    return remaining


def find_drift(
    root_text: str,
    rendered_text: str,
    allowed: set[tuple[str, str]] | None = None,
    root_only: tuple[tuple[str, ...], ...] = (),
) -> list[str]:
    """Return one formatted message per undeclared difference.

    Compares root_text against rendered_text after stripping comments and
    blank lines from both. Every changed hunk has its declared
    (`allowed`) line pairs subtracted out first; whatever remains is real
    drift and is rendered into the returned message, printing the exact
    stripped lines -- the same form an ALLOWED_LINE_DIFFERENCES entry
    expects, so they can be pasted in directly.
    """
    import difflib

    allowed = allowed or set()
    unused_root_only = list(root_only)
    root_lines = _relevant_lines(root_text)
    rendered_lines = _normalize_template_paths(_relevant_lines(rendered_text))
    matcher = difflib.SequenceMatcher(
        None, root_lines, rendered_lines, autojunk=False
    )
    errors: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed = [line.strip() for line in root_lines[i1:i2]]
        added = [line.strip() for line in rendered_lines[j1:j2]]
        remaining_removed, remaining_added = _subtract_allowed_pairs(
            removed, added, allowed
        )
        remaining_removed = _subtract_root_only_blocks(
            remaining_removed, unused_root_only
        )
        if not remaining_removed and not remaining_added:
            continue
        removed_block = "\n".join(
            f'      "{line}"' for line in remaining_removed
        )
        added_block = "\n".join(f'      "{line}"' for line in remaining_added)
        errors.append(
            "root has:\n"
            + (removed_block or "      (nothing)")
            + "\n    rendered template has:\n"
            + (added_block or "      (nothing)")
            + "\n    (lines above are already stripped -- paste a "
            "(root_line, rendered_line) pair straight into "
            "ALLOWED_LINE_DIFFERENCES to declare it, if it is "
            "legitimate)"
        )
    return errors


def render_template(repo_root: Path, dest: Path) -> None:
    """Render only paired workflow templates without invoking Copier."""
    workflows = dest / ".github" / "workflows"
    workflows.mkdir(parents=True)
    environment = Environment(
        autoescape=False,  # noqa: S701 - renders trusted local YAML
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    for root_workflow, jinja_path in paired_workflow_files(repo_root):
        rendered = environment.from_string(
            jinja_path.read_text(encoding="utf-8")
        ).render(**REPRESENTATIVE_ANSWERS)
        (workflows / root_workflow.name).write_text(rendered, encoding="utf-8")


def check(root: Path) -> list[str]:
    """Verify conditional coverage, then render template/ once and diff."""
    pairs = paired_workflow_files(root)
    if not pairs:
        return []

    coverage_errors: list[str] = []
    for _root_workflow, jinja_path in pairs:
        jinja_rel = jinja_path.relative_to(root)
        for problem in find_uncovered_conditionals(
            jinja_path.read_text(encoding="utf-8"), REPRESENTATIVE_LANGUAGES
        ):
            coverage_errors.append(f"{jinja_rel}: {problem}")
    if coverage_errors:
        return coverage_errors

    with tempfile.TemporaryDirectory(prefix="jinja-workflow-drift-") as raw_tmp:
        dest = Path(raw_tmp) / "rendered"
        try:
            render_template(root, dest)
        except (TemplateError, OSError) as exc:
            return [f"failed to render the paired jinja workflows check: {exc}"]
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
                ROOT_ONLY_BLOCKS.get(jinja_path.name, ()),
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
            "rendered template/ counterpart (or an unproven "
            "REPRESENTATIVE_LANGUAGES coverage gap). Fix root or the "
            ".jinja template so they agree, or add an explicit, reasoned "
            "(root_line, rendered_line) entry to ALLOWED_LINE_DIFFERENCES "
            "in scripts/check_jinja_workflow_drift.py.\n"
        )
        return 1
    pairs = len(paired_workflow_files(args.root))
    sys.stdout.write(
        f"{pairs} paired jinja workflow(s) match root after rendering.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
