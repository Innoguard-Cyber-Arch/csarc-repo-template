"""Payload budgets beyond total bytes (Issue #1231).

These tests cover the measures and the budget table without rendering;
`tests/test_generated_payload.py` (large) checks every fixture render.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generated_payload  # noqa: E402
import release_policy  # noqa: E402

# #1058 Targets file counts before #1231 tightened them.
M18_FILE_TARGETS = {
    "solo-default": 92,
    "solo-python": 95,
    "hosted-csarc-owned-python": 137,
    "consumer-a": 121,
    "consumer-b": 117,
}


def write(path: Path, text: str) -> Path:
    """Write one file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_canonical_bytes_ignore_docstrings_comments_and_wrapping(
    tmp_path: Path,
) -> None:
    """Formatting and prose do not change the canonical size of Python."""
    plain = write(
        tmp_path / "plain.py",
        "def check(value):\n"
        '    raise ValueError(f"Value {value}: bad. Fix it.")\n',
    )
    wrapped = write(
        tmp_path / "wrapped.py",
        '"""Module docstring."""\n\n\n'
        "def check(value):\n"
        '    """Explain the check at length.\n\n    More prose.\n    """\n'
        "    # A comment the reader needs.\n"
        "    raise ValueError(\n"
        "        f'Value {value}: bad. Fix it.'\n"
        "    )\n",
    )
    size = generated_payload.canonical_bytes(plain)
    assert size == generated_payload.canonical_bytes(wrapped)
    assert size < plain.stat().st_size


def test_python_is_detected_by_shebang(tmp_path: Path) -> None:
    """An extension-less Python script is parsed, not read as shell."""
    script = write(
        tmp_path / "tool",
        '#!/usr/bin/env python3\n"""Doc."""\nprint("OK: done.")  # note\n',
    )
    assert generated_payload.is_python(script)
    assert generated_payload.canonical_bytes(script) == len(
        "print('OK: done.')\n"
    )


def test_shell_counts_only_code_lines(tmp_path: Path) -> None:
    """Shell keeps non-blank, non-comment lines without indentation."""
    script = write(
        tmp_path / "tool.sh",
        "#!/usr/bin/env bash\n# comment\n\nif true; then\n    echo hi\nfi\n",
    )
    assert not generated_payload.is_python(script)
    expected = sum(len(line) + 1 for line in ("if true; then", "echo hi", "fi"))
    assert generated_payload.canonical_bytes(script) == expected


@pytest.mark.parametrize(
    ("text", "tokens"),
    [("", 0), ("abcd", 1), ("abcde", 2), ("中文", 2), ("中文\uff0cab", 4)],
)
def test_token_estimate(text: str, tokens: int) -> None:
    """CJK counts one token per character, other text one per four."""
    assert generated_payload.estimated_tokens(text) == tokens


def test_workflow_permissions_count_writes_and_pull_request_target(
    tmp_path: Path,
) -> None:
    """Top-level or job write grants and `pull_request_target` are counted."""
    flows = tmp_path / ".github/workflows"
    write(flows / "read.yml", "on: push\npermissions:\n  contents: read\n")
    write(
        flows / "job-write.yml",
        "on: [push]\njobs:\n  a:\n    permissions:\n      issues: write\n",
    )
    write(
        flows / "target.yml",
        "on:\n  pull_request_target:\npermissions: write-all\n",
    )
    write(flows / "target-read.yaml", "on: pull_request_target\n")
    assert generated_payload.workflow_permissions(tmp_path) == {
        "write_workflows": 2,
        "pull_request_target_workflows": 2,
    }


def test_every_template_runtime_belongs_to_one_group() -> None:
    """New runtime must be booked to exactly one capability group."""
    groups = generated_payload.RUNTIME_GROUPS
    names = [name for members in groups.values() for name in members]
    assert len(names) == len(set(names))
    shipped = {
        path.name.removesuffix(".jinja")
        for path in (ROOT / "template/.csarc/scripts").iterdir()
        if path.is_file()
    }
    assert shipped <= set(names), sorted(shipped - set(names))
    assert set(generated_payload.RUNTIME_GROUP_BUDGETS) == set(groups) - {
        "docs-site"
    }


def test_backstop_is_the_converted_raw_target() -> None:
    """AC2: each backstop is the raw Target minus its conversion offset."""
    assert generated_payload.CONVERSION_REF == "cd0b69d"
    for name, raw in generated_payload.RAW_TARGETS.items():
        offset = generated_payload.CONVERSION_OFFSETS[name]
        expected = (raw - offset) // 1000 * 1000
        assert generated_payload.TARGETS[name]["canonical_bytes"] == expected


def test_file_targets_only_tightened() -> None:
    """AC2: file budgets never exceed the #1058 Targets."""
    for name, files in M18_FILE_TARGETS.items():
        assert generated_payload.TARGETS[name]["files"] <= files
    assert (
        generated_payload.TARGETS["hosted-csarc-owned-python"]["files"] == 126
    )


def test_every_fixture_has_every_budget() -> None:
    """Each fixture carries the same budget keys."""
    keys = {
        "files",
        "canonical_bytes",
        "write_workflows",
        "pull_request_target_workflows",
        "agent_doc_tokens",
    }
    assert set(generated_payload.TARGETS) == set(generated_payload.FIXTURES)
    for budgets in generated_payload.TARGETS.values():
        assert set(budgets) == keys


def test_budget_failures_name_each_exceeded_measure() -> None:
    """A fixture over a budget or with unassigned runtime is reported."""
    name = "consumer-b"
    values = {
        **generated_payload.TARGETS[name],
        **{
            f"runtime:{group}": budget
            for group, budget in generated_payload.RUNTIME_GROUP_BUDGETS.items()
        },
        "runtime_unassigned": 0,
    }
    assert generated_payload.budget_failures(name, values) == []
    values["write_workflows"] += 1
    values["runtime:release"] += 1
    values["runtime_unassigned"] = 1
    assert generated_payload.budget_failures(name, values) == [
        "consumer-b write_workflows 8 > 7",
        "consumer-b runtime:release 166,001 > 166,000",
        "consumer-b runtime_unassigned 1 > 0",
    ]


def test_tree_churn_counts_files_and_lines() -> None:
    """AC4: churn counts added, removed, and modified files and lines."""
    old = {"keep": b"a\n", "edit": b"a\nb\nc\n", "gone": b"x\ny\n"}
    new = {"keep": b"a\n", "edit": b"a\nB\nc\nd\n", "new": b"z\n"}
    assert generated_payload.tree_churn(old, new) == {
        "files_added": 1,
        "files_removed": 1,
        "files_modified": 1,
        "lines_added": 3,
        "lines_removed": 3,
    }


def test_unknown_ref_is_an_error(tmp_path: Path) -> None:
    """A ref git cannot archive stops with a next step."""
    with pytest.raises(ValueError, match="Pass a commit or tag"):
        generated_payload.template_at_ref("no-such-ref-1231", tmp_path)


def test_churn_is_advisory_in_prepare_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4: stable candidates report churn; failures never raise."""
    assert (
        release_policy.generated_payload_churn(ROOT, "HEAD", "1.0.0-beta.1")
        is None
    )
    # A trusted-base run against another checkout never loads its code.
    assert release_policy.generated_payload_churn(
        tmp_path, "HEAD", "1.0.0"
    ) == {
        "available": False,
        "reason": "churn runs only from the repository's own scripts",
    }

    def broken(since: str, root: Path) -> dict[str, object]:
        raise RuntimeError(f"render failed for {since}")

    monkeypatch.setattr(generated_payload, "churn", broken)
    monkeypatch.setattr(
        release_policy, "git_output", lambda *_: "v9.9.9-beta.1\nv1.2.3"
    )
    report = release_policy.generated_payload_churn(ROOT, "HEAD", "1.3.0")
    assert report == {"available": False, "reason": "render failed for v1.2.3"}

    monkeypatch.setattr(
        release_policy, "git_output", lambda *_: "v2.0.0-beta.1"
    )
    assert release_policy.generated_payload_churn(ROOT, "HEAD", "2.0.0") == {
        "available": False,
        "reason": "no earlier stable tag",
    }


def test_churn_subcommand_requires_a_tag() -> None:
    """`churn` without `--since` is a usage error."""
    done = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts/generated_payload.py"), "churn"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2
    assert "--since" in done.stderr
