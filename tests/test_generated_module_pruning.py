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
    "delivery_sync.py": ("delivery_sync.py",),
    "promotion_gate.py": ("promotion_gate.py",),
    "release_policy.py": ("release_policy.py", "release_candidate.py"),
    "sync_milestone_state.py": ("sync_milestone_state.py",),
    "verification_cost.py": ("verification_cost.py",),
}
# Definitions that intentionally differ from root, or exist only in the
# generated copy; each value records why.
GENERATED_PATHS = "generated `.csarc/` layout paths"
ADAPTED: dict[str, dict[str, str]] = {
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


def definitions(*paths: Path) -> dict[str, ast.stmt]:
    """Return the named top-level definitions of one or more modules."""
    found: dict[str, ast.stmt] = {}
    for path in paths:
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
                if is_alias(node, name):
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
    generated = definitions(*(GENERATED / name for name in SPLITS[module]))
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
    """Pruning removed code; no generated split outgrows its root module."""
    for module, files in SPLITS.items():
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
