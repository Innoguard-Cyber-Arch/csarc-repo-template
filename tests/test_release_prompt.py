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
    assert "adoption-pending 時依 next_command 繼續 finalize" in prompt
    assert "current 時只回報不需動作" in prompt
    assert "policy-only-update" in prompt
    assert ".csarc/scripts/apply-repository-settings.sh plan" in prompt
    assert "init／adopt／update prompt" not in prompt


ROOT = Path(__file__).parents[1]
COMMIT_RULE = "commit 只限 docs/install.md 指定的兩種"


def operator_run() -> str:
    """Return the operator-independence run section of the pilot guide."""
    pilot = (ROOT / "docs" / "pilot-adoption.md").read_text(encoding="utf-8")
    return pilot.split("## Operator-independence run", 1)[1].split("\n## ", 1)[
        0
    ]


def test_prompt_and_pilot_record_rules_agree() -> None:
    """Issue #1147 AC6: one record location and one allowed-action rule."""
    restriction = "全程不要自行 stash、套用 GitHub settings、push 或建立 PR"
    prompt = render("v1.2.3", "a" * 40)
    assert restriction in prompt
    assert "pilot-adoption.md 的 operator-independence run 步驟 5" in prompt
    run = operator_run()
    assert "5. 依下表記錄。驗證通過後" in run
    assert "正式紀錄只有一處：target repository 自己的 pilot Issue 留言" in run
    assert "Draft PR 只承載 diff" in run


def test_commit_timing_agrees_across_prompt_pilot_install_and_handbook() -> (
    None
):
    """Issue #1158 AC2/R2: one commit-timing rule in every operator source.

    Product preparation commits come before ``--finalize-plan`` and
    ``verify-fast`` runs on the committed head after apply, in the release
    prompt, the operator-independence run, both install guides, and the
    handbook's local evidence row.
    """
    prompt = render("v1.2.3", "a" * 40)
    run = operator_run()
    assert COMMIT_RULE in prompt
    assert COMMIT_RULE in run
    # The prompt names both allowed commits, in order.
    preparation = prompt.index("`--finalize-plan` 前的產品準備 commit")
    applied = prompt.index("apply 成功後把結果 commit 到同一分支")
    verify = prompt.index("已 commit 的 head 執行 `verify-fast`")
    assert preparation < applied < verify
    # The old rule forbidding every commit before step 5 is gone.
    assert "全程不要自行 stash、commit" not in prompt
    assert "全程不要自行 stash、commit" not in run
    # The pilot steps order the same three events.
    step3 = run.index("3. 依手冊與 `docs/install.md` 處理衝突")
    step4 = run.index("4. apply 成功後把結果 commit 到同一個分支")
    assert step3 < step4
    assert "產品準備 commit 在 `--finalize-plan` 前提交" in run[step3:step4]
    assert (
        "在這個已 commit 的 head 執行 `./.csarc/scripts/verify-fast`"
        in run[step4:]
    )
    install = (ROOT / "docs" / "install.md").read_text(encoding="utf-8")
    assert "產品準備 commit 在 `--finalize-plan` 前提交" in install
    assert (
        "commit 到同一個分支，再在這個已 commit、乾淨的 head 執行 "
        "`./.csarc/scripts/verify-fast`"
    ) in install
    english = (ROOT / "docs" / "install.en.md").read_text(encoding="utf-8")
    assert "product preparation commit before `--finalize-plan`" in english
    assert (
        "run `./.csarc/scripts/verify-fast` and the product's own checks on "
        "that committed, clean head"
    ) in english
    handbook = (ROOT / "docs" / "handbook" / "handbook.md").read_text(
        encoding="utf-8"
    )
    assert "在已 commit、乾淨的 exact head 執行一次 `verify-fast`" in handbook


def test_operator_run_pass_rule_is_measurable() -> None:
    """Issue #1158 AC1/AC3/R1: the owner's 2026-10-18 pass rule.

    The record names a field for each condition, every unclear point needs
    a tracking Issue, and only an owner decision the documents already list
    with options may be recorded as pending instead of a regression.
    """
    run = operator_run()
    fields = [
        line.split("|")[1].strip()
        for line in run.split("**必填欄位：**", 1)[1]
        .split("**Pass 條件：**", 1)[0]
        .splitlines()
        if line.startswith("| ") and not line.startswith("| 欄位")
    ]
    for field in (
        "產品 diff 摘要",
        "Native checks",
        "產品檢查變化",
        "無依據猜測",
        "文件不清楚",
        "實作者協助",
        "結果",
    ):
        assert field in fields, field
    # The unreachable "no extra prompt at all" rule is gone.
    assert "額外提示或文件 drift" not in run
    assert "額外提示為 `none`" not in run
    rule = run.split("**Pass 條件：**", 1)[1].split("**紀錄位置：**", 1)[0]
    for condition in (
        "1. **不需要實作者協助**",
        "2. **沒有無依據的猜測**",
        "3. **其餘不清楚之處都有追蹤**",
        "4. **產品檢查沒有 regression**",
    ):
        assert condition in rule, condition
    assert "會改變產品行為或治理範圍" in rule
    assert "開 Issue" in rule
    # R1: only a documented owner decision with options may be pending.
    assert "只有文件已列為擁有者決定、並寫出選項的變化" in rule
    assert "其他變化，包括文件沒有寫出選項的變化，一律記為 `regression`" in (
        rule
    )
    # AC3: the expected product diff follows install.md's preparation
    # commits, each recorded, instead of "empty or only pins".
    assert "預期為空或只有 preflight pin" not in run
    assert "只能是 install.md 列出的產品準備 commit" in run
    assert "逐條記錄 SHA、內容與依據的 install.md 章節" in run


@pytest.mark.parametrize(
    ("tag", "sha"),
    [("1.2.3", "a" * 40), ("v1.2.3", "A" * 40), ("v1.2.3", "a" * 39)],
)
def test_render_rejects_untrusted_release_inputs(tag: str, sha: str) -> None:
    """Reject malformed tags and non-canonical commit identifiers."""
    with pytest.raises(ValueError):
        render(tag, sha)
