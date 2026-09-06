# 安裝說明

CSARC 交付的是 CI/CD 範本與治理流程，Python 只用來執行 init／adopt／update 的薄 CLI；`uvx --python 3.14` 會按次取得隔離 runtime，不要求使用者預先安裝或維護全域 Python。Windows 請在 WSL2 執行。

## 前置需求

一律只需要 `uv`；選擇的語言模組另需對應工具鏈；`languages` 全部不勾選（`language: ci`）時不需要任何額外語言工具鏈。

| 工具 | 何時需要 | macOS（Homebrew） | Windows（winget／Chocolatey） |
| --- | --- | --- | --- |
| Git | 一律需要 | `brew install git` | `winget install --id Git.Git -e` |
| GitHub CLI（`gh`） | 只有 GitHub 連線操作需要 | `brew install gh` | `winget install --id GitHub.cli --source winget` |
| uv | 一律需要 | `brew install uv` | `winget install --id=astral-sh.uv -e` |
| Node.js 24+ | 只有選 `typescript` 時需要 | `brew install node` | `winget install --id OpenJS.NodeJS.LTS -e` |
| pnpm 11 | 只有選 `typescript` 時需要 | `brew install pnpm` | `winget install -e --id pnpm.pnpm` |
| rustup／Cargo | 只有選 `rust` 時需要 | `brew install rustup` | `winget install -e --id Rustlang.Rustup` |

## 建立新 repo

```bash
uvx --python 3.14 --from 'git+https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git@<approved-full-commit-sha>' csarc init ./my-project
```

## 導入既有 repo

```bash
git switch -c chore/<issue-number>-adopt-csarc-template
uvx --python 3.14 --from 'git+https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git@<approved-full-commit-sha>' csarc adopt
```

`adopt` 預設為 dry-run，只產生 repo 外的 Markdown 導入報告與 machine-readable plan，不修改 repo；確認後才用 `--apply-plan` 套用。

## 更新已導入的 repo

```bash
git switch -c chore/<issue-number>-update-repo-template
uvx --python 3.14 --from 'git+https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git@<approved-full-commit-sha>' csarc update --check --json
```

## 不確定目前狀態時

先用「自動判斷」：`csarc status` 只讀本機檔案與（若已導入）GitHub 上的公版版本與 repository 設定，判斷屬於 `create`／`adopt`／`update`／`current`／`policy-only-update` 五種狀態之一，再依回傳的 `next_command` 走對應流程。固定版本的完整 agent 安裝契約見 [`docs/agent-install.md`](agent-install.md)。

## 完整細節

`<approved-full-commit-sha>` 的取得方式、`project_description`／`project_run_command`／`security_reporting_channel` 等必填欄位、既有 repo 導入的 manual merge 清單、衝突處理與 troubleshooting，見根目錄 [`README.md`](../README.md#快速開始) 的「快速開始」「公版更新」章節與 [`docs/pilot-adoption.md`](pilot-adoption.md) 的實際導入證據。要理解「為什麼這樣設計」，請讀[內部決策網站](index.html)。
