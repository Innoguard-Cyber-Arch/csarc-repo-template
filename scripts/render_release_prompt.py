"""Render the release-specific agent setup prompt."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPOSITORY = "Innoguard-Cyber-Arch/csarc-repo-template"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def render(tag: str, sha: str) -> str:
    """Return one status-first prompt bound to an immutable release."""
    if not tag.startswith("v") or any(character.isspace() for character in tag):
        raise ValueError("release tag must be a non-space v-prefixed value")
    if FULL_SHA.fullmatch(sha) is None:
        raise ValueError(
            "release SHA must be 40 lowercase hexadecimal characters"
        )

    source = f"git+https://github.com/{REPOSITORY}.git@{sha}"
    raw = f"https://raw.githubusercontent.com/{REPOSITORY}/{sha}"
    status = (
        f"uvx --python 3.14 --from '{source}' csarc status <path> "
        f"--to {tag} --expected-sha {sha} --json"
    )
    return (
        "\n".join(
            (
                "請依這份固定版本契約，在目前 workspace 設定或更新 CSARC。",
                "",
                f"來源 repository：https://github.com/{REPOSITORY}",
                f"核准版本：{tag}",
                f"核准 commit：{sha}",
                f"安裝指南：{raw}/docs/agent-install.md",
                f"設定來源：{raw}/copier.yml",
                "",
                "請先讀取固定 commit 的安裝指南與 copier.yml，再以 "
                f"`{status}` 判斷狀態；不要自行推測。create、adopt 或 "
                "update 時，"
                "先讓我選擇「接受建議值」或「逐項客製」；逐項客製只依同一份 "
                "copier.yml 中目前適用的問題分組確認，並透過既有 `--data` "
                "傳值。先執行 dry-run JSON，摘要解析後的答案、檔案與政策計畫，"
                "等我確認後"
                "才用相同 tag、SHA 與答案執行。adoption-pending 時依 "
                "next_command 繼續 finalize；current 時只回報不需動作；"
                "policy-only-update 時只執行 `.csarc/scripts/"
                "apply-repository-settings.sh plan`，摘要後等待確認。"
                "能力未知或不可用時"
                "要明確回報，不得宣稱已啟用。全程不要自行 stash、commit、套用 "
                "GitHub settings、push 或建立 PR。",
            )
        )
        + "\n"
    )


def main() -> None:
    """Write the immutable release prompt from validated arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(args.tag, args.sha), encoding="utf-8")


if __name__ == "__main__":
    main()
