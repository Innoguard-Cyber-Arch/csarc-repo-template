"""Render release-specific agent instructions and provenance assets."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPOSITORY = "Innoguard-Cyber-Arch/csarc-repo-template"
REPOSITORY_ID = 1_340_899_393
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def prompt(mode: str, tag: str, sha: str) -> str:
    """Return one release-specific, copyable agent prompt."""
    actions = {
        "init": "在目前 workspace 建立新的 CSARC repository",
        "adopt": "在目前開啟的既有 Git repository 導入 CSARC 公版",
        "update": "更新目前開啟且已導入 CSARC 的 Git repository",
    }
    command = (
        "uvx --python 3.14 --from "
        f"'git+https://github.com/{REPOSITORY}.git@{sha}' csarc {mode}"
    )
    target_instruction = (
        "自行依工作脈絡判斷名稱與位置，無法唯一判斷時先詢問；"
        if mode == "init"
        else "自行判斷 repo root；"
    )
    review = (
        "檢視 repo 外的 Markdown、PDF 與 machine plan，摘要新增、"
        "自動合併、覆寫、保留、人工合併及無法判定項目"
        if mode == "adopt"
        else "摘要將新增、覆寫、保留及需要人工合併的檔案"
    )
    apply_command = {
        "init": f"{command} <target-path> --apply-plan PATH",
        "adopt": f"{command} --apply-plan PATH",
        "update": f"{command} --apply-plan PATH",
    }[mode]
    return "\n".join(
        (
            f"請{actions[mode]}；{target_instruction}",
            "",
            f"來源 repository：https://github.com/{REPOSITORY}",
            f"核准版本：{tag}",
            f"核准 commit：{sha}",
            "安裝指南：https://raw.githubusercontent.com/"
            f"{REPOSITORY}/{sha}/docs/agent-install.md",
            "",
            "請先讀取該固定 commit 的安裝指南，以 "
            f"`{command}` 為基礎（init 另帶自行確認的 path），加上 "
            f"`--to {tag} --expected-sha {sha} --dry-run` 執行；"
            f"{review}。確認後只用 `{apply_command} --yes --non-interactive` "
            "套用 dry-run 產生且未漂移的 plan 並驗證；不要自行 stash、"
            "commit、apply GitHub settings、push 或建立 PR。",
        )
    )


def render(tag: str, sha: str, body: str) -> tuple[str, str, str]:
    """Render prompt text, provenance JSON, and appended release notes."""
    if not tag.startswith("v") or any(character.isspace() for character in tag):
        raise ValueError("release tag must be a non-space v-prefixed value")
    if FULL_SHA.fullmatch(sha) is None:
        raise ValueError(
            "release SHA must be 40 lowercase hexadecimal characters"
        )
    prompts = (
        "\n\n---\n\n".join(
            (
                prompt("init", tag, sha),
                prompt("adopt", tag, sha),
                prompt("update", tag, sha),
            )
        )
        + "\n"
    )
    provenance = (
        json.dumps(
            {
                "commit_sha": sha,
                "guide_url": (
                    "https://raw.githubusercontent.com/"
                    f"{REPOSITORY}/{sha}/docs/agent-install.md"
                ),
                "release_tag": tag,
                "repository": REPOSITORY,
                "repository_id": REPOSITORY_ID,
                "schema_version": 1,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    notes = body.rstrip() + "\n\n## Agent installation prompt\n\n```text\n"
    notes += prompt("adopt", tag, sha) + "\n```\n"
    return prompts, provenance, notes


def main() -> None:
    """Write immutable-release assets from validated command arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    prompts, provenance, notes = render(
        args.tag,
        args.sha,
        args.body_file.read_text(encoding="utf-8"),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "release-prompt.txt").write_text(
        prompts, encoding="utf-8"
    )
    (args.output_dir / "csarc-release-provenance.json").write_text(
        provenance, encoding="utf-8"
    )
    (args.output_dir / "release-notes.md").write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
