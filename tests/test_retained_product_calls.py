"""A retired legacy verifier must not silently drop product tests (#1169).

A product that added its own test calls to a generated ``scripts/verify``
loses them once the kept ``retire-modified`` script is retired: the new
verifier never runs them. ``--check`` lists those calls and points to the
product verification hook. No consumer identity is recorded here.
"""

from __future__ import annotations

from pathlib import Path

from test_cli import write_executable
from test_operator_run_regressions import write

from csarc_cli import cli, file_transition

ROOT = Path(__file__).resolve().parents[1]
OLD_VERIFY = (
    "#!/usr/bin/env bash\nset -euo pipefail\n"
    'repo_root="$(git rev-parse --show-toplevel)"\n'
    "./scripts/test-pr-policy\n"
)
PRODUCT_VERIFY = (
    OLD_VERIFY
    + "# ./scripts/test-commented-out\n"
    + "echo running product checks\n"
    + "./scripts/test-sync-skills\n"
    + '"$repo_root/scripts/test-mcp-configs" --strict\n'
    + "uv run pytest tests/eval\n"
    + "./scripts/test-sync-skills\n"
    + "./scripts/missing-helper\n"
)


def product_target(tmp_path: Path) -> tuple[Path, Path]:
    """Return a target with a product-extended verifier and its old render."""
    target = tmp_path / "target"
    old_stage = tmp_path / "old"
    write_executable(old_stage / "scripts/verify", OLD_VERIFY)
    write_executable(old_stage / "scripts/test-pr-policy", "true\n")
    write_executable(target / "scripts/verify", PRODUCT_VERIFY)
    write_executable(target / "scripts/test-pr-policy", "true\n")
    for name in ("test-sync-skills", "test-mcp-configs", "test-commented-out"):
        write_executable(target / "scripts" / name, "#!/bin/sh\ntrue\n")
    return target, old_stage


def test_retained_product_calls_lists_added_product_tests(
    tmp_path: Path,
) -> None:
    """AC1/AC2: only added, non-comment product test calls are listed."""
    target, old_stage = product_target(tmp_path)
    write(target / "CLAUDE.md", "Run ./scripts/test-sync-skills.\n")

    rows = cli.retained_product_calls(
        target,
        old_stage,
        ("CLAUDE.md", "scripts/verify"),
        {"scripts/verify", "scripts/test-pr-policy"},
    )
    assert rows == [
        {"call": "./scripts/test-sync-skills", "script": "scripts/verify"},
        {
            "call": '"$repo_root/scripts/test-mcp-configs" --strict',
            "script": "scripts/verify",
        },
        {"call": "uv run pytest tests/eval", "script": "scripts/verify"},
    ]
    # A verifier equal to the old render adds no product call.
    write_executable(target / "scripts/verify", OLD_VERIFY)
    assert (
        cli.retained_product_calls(
            target, old_stage, ("scripts/verify",), {"scripts/verify"}
        )
        == []
    )


def test_a_generated_file_is_not_a_product_call() -> None:
    """AC1: a call into a rendered CSARC file is not a product test."""
    content = b"#!/bin/sh\n./scripts/test-pr-policy\n./scripts/x\n"
    assert file_transition.added_product_calls(
        "scripts/verify",
        content,
        b"#!/bin/sh\n",
        lambda name: name == "scripts/x",
    ) == ("./scripts/x",)


def test_retire_modified_row_names_product_calls_and_the_hook() -> None:
    """AC1/R1: the row lists each call and points to the hook."""
    files = cli.Plan((), (), (), (), (), (), (), retained=("scripts/verify",))
    calls = [
        {"call": "./scripts/test-sync-skills", "script": "scripts/verify"},
        {"call": "./scripts/test-tier1-eval", "script": "scripts/verify"},
    ]
    [plain] = cli.update_required_actions(files, ())
    assert "project_verification_hook" not in str(plain["message"])

    [action] = cli.update_required_actions(files, (), product_calls=calls)
    message = str(action["message"])
    assert action["kind"] == "retire-modified"
    assert action["blocking"] is False
    assert "`./scripts/test-sync-skills`; `./scripts/test-tier1-eval`" in (
        message
    )
    assert "project_verification_hook" in message
    assert "product preparation commit" in message

    # A blocking kept script keeps its block and also names the calls.
    uses = [
        {
            "destination": "",
            "path": "scripts/test-pr-policy",
            "script": "scripts/verify",
        }
    ]
    [blocked] = cli.update_required_actions(
        files, (), retained_uses=uses, product_calls=calls
    )
    assert blocked["blocking"] is True
    assert "scripts/test-pr-policy (removed)" in str(blocked["message"])
    assert "`./scripts/test-tier1-eval`" in str(blocked["message"])


def test_plan_rows_are_read_back_from_the_recorded_key() -> None:
    """AC1: the report reads the recorded calls from the plan."""
    update = {
        "retained_product_calls": [
            {"call": "./scripts/test-sync-skills", "script": "scripts/verify"}
        ]
    }
    assert cli.update_retained_uses(update, "retained_product_calls") == [
        {"call": "./scripts/test-sync-skills", "script": "scripts/verify"}
    ]
    assert cli.update_retained_uses(update) == []


def test_install_docs_describe_moving_product_tests_to_the_hook() -> None:
    """AC1/R1: both install guides describe the move and allow the commit."""
    for name in ("docs/install.md", "docs/install.en.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "project_verification_hook" in text
        assert "#1169" not in text
    zh = (ROOT / "docs/install.md").read_text(encoding="utf-8")
    en = (ROOT / "docs/install.en.md").read_text(encoding="utf-8")
    assert "把產品測試搬到產品驗證 hook" in zh
    assert "move the product tests to the product verification hook" in en
