"""Generated copies of shared modules only remove root code (Issue #1129).

The template repository keeps the full `scripts/` modules; the copies under
`template/.csarc/scripts/` drop routes no generated project calls (retired
features, template-repository-only routes, and subcommands without a
generated caller) so the generated payload meets the #1058 Targets. A root
module may also be split into several generated files so an option renders
only the part it calls. This guard keeps that pruning honest: every
top-level definition left in the generated files must match the root
definition of the same name, except the declared adapters below, and no
other definition may exist only in the generated copy.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "template/.csarc/scripts"

# Root module -> the generated files that together hold its kept code.
SPLITS: dict[str, tuple[str, ...]] = {
    "authenticate_dependabot_head.py": (
        "authenticate_dependabot_head.py",
        "authenticate_dependabot_hosted.py",
    ),
    "delivery_sync.py": ("delivery_sync.py",),
    "pr_lifecycle.py": ("pr_lifecycle.py", "pr_lifecycle_hosted.py"),
    "promotion_gate.py": ("promotion_gate.py",),
    "release_policy.py": ("release_policy.py", "release_candidate.py"),
    "sync_milestone_state.py": (
        "sync_milestone_state.py",
        "sync_milestone_state_hosted.py",
    ),
    "verification_cost.py": ("verification_cost.py",),
    "verification_evidence.py": ("verification_evidence.py",),
}
# Issue #1177: names the first generated file only forwards to the hosted
# file that holds the root definition. Local renders omit that file.
FORWARDED: dict[str, frozenset[str]] = {
    "authenticate_dependabot_head.py": frozenset({"main"}),
    "pr_lifecycle.py": frozenset(
        {
            "close_work_issue",
            "declared_required_contexts",
            "require_successful_checks",
            "require_trusted_dependabot_head",
        }
    ),
    "sync_milestone_state.py": frozenset(
        {
            "check_issue_approval",
            "check_merge_group",
            "check_pr",
            "check_scope",
            "reconcile",
            "refresh_issue_pr_checks",
        }
    ),
}
HOSTED_FORWARDER = "loads the hosted-only sibling local renders omit (#1177)"
# Definitions that intentionally differ from root, or exist only in the
# generated copy; each value records why.
GENERATED_PATHS = "generated `.csarc/` layout paths"
NO_TEMPLATE_ISSUE = "messages name no template-repository Issue"
# Issue #1264 (ADR #1266 rev 5): Dependabot reverification never ships.
ROOT_ONLY_REVERIFY = "Dependabot reverification is template-repository only"
ADAPTED: dict[str, dict[str, str]] = {
    "authenticate_dependabot_head.py": {},
    "pr_lifecycle.py": {
        "hosted_checks": HOSTED_FORWARDER,
        "_hosted_only": HOSTED_FORWARDER,
        "_hosted_globals": HOSTED_FORWARDER,
        "__getattr__": HOSTED_FORWARDER,
        "acquire": ROOT_ONLY_REVERIFY,
        "merge": ROOT_ONLY_REVERIFY,
        "merge_evidence": ROOT_ONLY_REVERIFY,
        "merge_snapshot": ROOT_ONLY_REVERIFY,
        "merge_trailers": ROOT_ONLY_REVERIFY,
        "parser": ROOT_ONLY_REVERIFY,
        "require_lease": ROOT_ONLY_REVERIFY,
        "require_successful_checks": ROOT_ONLY_REVERIFY,
        "trace_lines": ROOT_ONLY_REVERIFY,
        "require_trusted_verification": (
            "drops the template-repository toolchain check; no generated "
            "project renders verify-template.sh"
        ),
        "require_head_contains_base": NO_TEMPLATE_ISSUE,
        "require_routine_quota_fallback": NO_TEMPLATE_ISSUE,
        "resolve_release_level": GENERATED_PATHS,
        "revalidate_release_candidate": GENERATED_PATHS,
        "review_settings": GENERATED_PATHS,
        "scan_writers": GENERATED_PATHS,
    },
    "delivery_sync.py": {
        "main": "drops the `reconcile` subcommand no generated caller runs",
    },
    "promotion_gate.py": {
        "parser": (
            "drops prepare/finalize/verify-main (no generated caller) and "
            "the retired quota-fallback commands"
        ),
    },
    "release_policy.py": {
        "_write_changelog": GENERATED_PATHS,
        "_write_release_version": GENERATED_PATHS,
        "release_follow_up_errors": GENERATED_PATHS,
        "release_plan": GENERATED_PATHS,
        "release_version_errors": GENERATED_PATHS,
        "verify_candidate_version": GENERATED_PATHS,
        "verify_release_version": GENERATED_PATHS,
        "parser": "drops the boundary and prepare commands no caller runs",
        "main": "keeps preflight and dispatches release commands",
        "dispatch": "the release-command half of root `main`",
        "release_candidate": "loads the csarc-owned release module",
        "__getattr__": "keeps `release_policy.<name>` reads working",
    },
    "sync_milestone_state.py": {
        "main": "drops record-promotion-evidence (no generated caller)",
        "_dispatch": "drops record-promotion-evidence (no generated caller)",
        "hosted_gates": HOSTED_FORWARDER,
        "_hosted_only": HOSTED_FORWARDER,
    },
    "verification_evidence.py": {
        # Issue #1284: only root accepts a pre-validated Dependabot
        # reverification as a clean-sync source; the generated copy also
        # names its own `.csarc/scripts/verify` full entry point.
        "validate_verification_job": ROOT_ONLY_REVERIFY,
    },
    "verification_cost.py": {
        "main": "drops the `report` command no generated caller runs",
    },
}
# String rewrites from the generated layout back to the root layout.
PATH_REWRITES = (
    (".csarc/scripts/", "scripts/"),
    (".csarc/docs/", "docs/"),
)


class _Normalize(ast.NodeTransformer):
    """Blank docstrings and map generated paths to the root layout."""

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, str):
            value = node.value
            for generated, root in PATH_REWRITES:
                value = value.replace(generated, root)
            return ast.copy_location(ast.Constant(value), node)
        return node

    def generic_visit(self, node: ast.AST) -> ast.AST:
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body[0] = ast.Expr(ast.Constant(""))
        return super().generic_visit(node)


def normalized(node: ast.AST) -> str:
    """Return one definition's AST dump without docstrings or layout paths."""
    tree = ast.parse(ast.unparse(node))
    return ast.dump(_Normalize().visit(tree))


def is_alias(node: ast.stmt, name: str) -> bool:
    """Return whether `name = <module>.name` re-exports a split sibling."""
    return (
        isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == name
        and isinstance(node.value.value, ast.Name)
    )


def definitions(
    *paths: Path, forwarded: frozenset[str] = frozenset()
) -> dict[str, ast.stmt]:
    """Return the named top-level definitions of one or more modules.

    A `forwarded` name defined in the first module is a forwarder to the
    real definition in a later one and is skipped.
    """
    found: dict[str, ast.stmt] = {}
    for index, path in enumerate(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            names: list[str] = []
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.Assign):
                names = [
                    target.id
                    for target in node.targets
                    if isinstance(target, ast.Name)
                ]
            elif isinstance(node, ast.AnnAssign) and isinstance(
                node.target, ast.Name
            ):
                names = [node.target.id]
            for name in names:
                if is_alias(node, name) or (index == 0 and name in forwarded):
                    continue
                assert name not in found, f"{name} defined twice"
                found[name] = node
    return found


def test_every_pruned_module_declares_its_adapters() -> None:
    """Each split names its root module and exactly one adapter table."""
    assert set(SPLITS) == set(ADAPTED)
    for module, files in SPLITS.items():
        assert (ROOT / "scripts" / module).is_file()
        assert all((GENERATED / name).is_file() for name in files)


@pytest.mark.parametrize("module", sorted(SPLITS))
def test_generated_copy_only_removes_root_code(module: str) -> None:
    """Kept definitions match root unless they are declared adapters."""
    root = definitions(ROOT / "scripts" / module)
    forwarded = FORWARDED.get(module, frozenset())
    generated = definitions(
        *(GENERATED / name for name in SPLITS[module]), forwarded=forwarded
    )
    # Every forwarded name keeps its real definition in a hosted file.
    assert forwarded <= set(generated), "forwarder without a definition"
    adapted = ADAPTED[module]
    assert set(adapted) <= set(generated), "stale adapter declaration"
    assert set(generated) - set(root) <= set(adapted), "undeclared addition"
    drifted = sorted(
        name
        for name, node in generated.items()
        if name not in adapted and normalized(node) != normalized(root[name])
    )
    assert drifted == []
    unused = sorted(
        name
        for name in adapted
        if name in root
        and normalized(generated[name]) == normalized(root[name])
    )
    assert unused == [], "adapter matches root; drop the declaration"


def test_generated_copies_shrink() -> None:
    """Pruning removed code; no generated split outgrows its root module.

    A hosted split (#1177) moves code without removing it, so only the half
    every render receives must shrink.
    """
    for module, files in SPLITS.items():
        if module in FORWARDED:
            files = files[:1]
        root_lines = len(
            (ROOT / "scripts" / module).read_text(encoding="utf-8").splitlines()
        )
        generated_lines = sum(
            len((GENERATED / name).read_text(encoding="utf-8").splitlines())
            for name in files
        )
        assert generated_lines < root_lines, module


def test_adr_payload_rules_match_copier() -> None:
    """The generated-layout ADR lists exactly the option-rendered paths."""
    adr = (ROOT / "docs/adr/generated-repository-layout.md").read_text(
        encoding="utf-8"
    )
    table = adr.split("# path | rendered when\n", 1)[1].split("```", 1)[0]
    documented = dict(
        line.split(" | ", 1) for line in table.splitlines() if line.strip()
    )
    config = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    rendered: dict[str, str] = {}
    for rule in config["_exclude"]:
        match = re.fullmatch(
            r"\{% if (.+?) %\}__keep_\w+__\{% else %\}(\S+?)\{% endif %\}", rule
        )
        if match and match.group(2).startswith((".csarc/", ".github/")):
            rendered[match.group(2)] = match.group(1)
    assert documented == rendered


def paired_copies() -> set[str]:
    """Return generated scripts kept byte-identical to a root copy."""
    pairs = (ROOT / "scripts/sync-paired-files.sh").read_text(encoding="utf-8")
    return set(re.findall(r'\|template/\.csarc/scripts/([^"]+)"', pairs))


def test_generated_python_keeps_summary_docstrings() -> None:
    """Generated copies keep one-line def and class docstrings (#1227).

    The root module keeps the full explanation once; a generated copy that
    is not byte-paired with root ships only each summary line, so the same
    text is not paid for again in every project's payload.
    """
    paired = paired_copies()
    assert paired, "no paired copies found"
    long_docstrings = []
    for path in sorted(GENERATED.iterdir()):
        if not path.is_file() or path.name in paired:
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix != ".py" and not text.startswith(
            "#!/usr/bin/env python"
        ):
            continue
        for node in ast.walk(ast.parse(text)):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                docstring = ast.get_docstring(node)
                if docstring and "\n" in docstring.strip():
                    long_docstrings.append(f"{path.name}:{node.lineno}")
    assert long_docstrings == []
