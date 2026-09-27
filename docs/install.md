# 安裝說明

CSARC 交付的是 CI/CD 範本與治理流程，Python 只用來執行 init／adopt／update 的薄 CLI；`uvx --python 3.14` 會按次取得隔離 runtime，不要求使用者預先安裝或維護全域 Python。Windows 請在 WSL2 執行。

## 前置需求

一律需要 Git、GitHub CLI 2.93.0 以上與 `uv`；選擇的語言模組另需對應工具鏈；`languages` 全部不勾選（`language: ci`）時不需要任何額外語言工具鏈。

| 工具 | 何時需要 | macOS（Homebrew） | Windows（原生，winget／Chocolatey） | Linux／WSL2（Ubuntu，apt） |
| --- | --- | --- | --- | --- |
| Git | 一律需要 | `brew install git` | `winget install --id Git.Git -e` | `sudo apt install -y git` |
| GitHub CLI（`gh`）2.93.0+ | 使用 csarc CLI 一律需要；安裝後執行 `gh auth login` | `brew install gh` | `winget install --id GitHub.cli --source winget` | 使用 [GitHub 官方 apt repository](https://github.com/cli/cli/blob/trunk/docs/install_linux.md#debian)，不要使用 Ubuntu 內建套件 |
| uv | 一律需要 | `brew install uv` | `winget install --id=astral-sh.uv -e` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js 24+ | 只有選 `typescript` 時需要 | `brew install node` | `winget install --id OpenJS.NodeJS.LTS -e` | `curl -fsSL https://deb.nodesource.com/setup_24.x \| sudo -E bash -` 後 `sudo apt install -y nodejs` |
| pnpm 11 | 只有選 `typescript` 時需要 | `brew install pnpm` | `winget install -e --id pnpm.pnpm` | `sudo npm install -g pnpm@11` |
| rustup／Cargo | 只有選 `rust` 時需要；**Linux／WSL2 上另需 `build-essential`（系統 C linker）** | `brew install rustup` | `winget install -e --id Rustlang.Rustup` | `sudo apt install -y build-essential` 後 `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| Go 1.27.1 | 只有選 `go` 時需要；生成專案的驗證器要求精確的 go1.27.1 | 從 [Go 官方下載頁](https://go.dev/dl/) 安裝 `go1.27.1` 的 macOS `.pkg`；不要用 `brew install go`，它會安裝最新版而非固定版本 | 請在 WSL2 內使用 Linux／WSL2 欄位 | 依 [Go 官方安裝說明](https://go.dev/doc/install)：`curl -LO https://go.dev/dl/go1.27.1.linux-amd64.tar.gz && sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go1.27.1.linux-amd64.tar.gz`，再把 `/usr/local/go/bin` 加入 `PATH` |

Windows 欄位是在原生 Windows 單獨安裝個別工具用（例如先裝 `git`／`gh` 再進 WSL2）；WSL2 的 Ubuntu shell 裡請改用 Linux／WSL2 欄位，winget 裝的 rustup 進 WSL2 後用不上；Go 只在 WSL2 內安裝，不提供原生 Windows 路徑。WSL2 內的 `gh` 必須從 GitHub 官方 apt repository 安裝，並以 `gh --version` 確認至少為 2.93.0；Ubuntu 內建套件版本過舊，不支援必要的 Release 驗證。選 `rust` 時，Linux／WSL2 上除了 `rustup` 還需要 `build-essential`（系統 C linker）；即使是純 Rust、不呼叫 C 函式庫的專案也一樣，否則編譯階段的 `cargo test` 會報 `error: linker 'cc' not found`。

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

目標在其他組織時，以 `--data code_owner=@<organization>/<team>` 指定該 repo 的 team；個人 repo 則用 `--data code_owner=@<user>`，不需要 CODEOWNERS 時留空。尚未設定 remote 的本機 repo 會把有值的 owner 標成 `unknown`，允許先審查導入計畫；若 owner 留空，需同時傳入合法的 `--data repository_url=https://github.com/<owner>/<repository>`，即使文件模式關閉也不能省略。push 後再依序執行產生的 repository settings `plan`／`apply`／`check`。檢查不會自動授予 user／team 權限，owner 不存在或沒有 write 以上權限時會停止。

## 更新已導入的 repo

```bash
git switch -c chore/<issue-number>-update-repo-template
uvx --python 3.14 --from 'git+https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git@<approved-full-commit-sha>' csarc update --check --json
```

## 不確定目前狀態時

先用「自動判斷」：`csarc status` 只讀本機檔案與（若已導入）GitHub 上的公版版本與 repository 設定，判斷屬於 `create`／`adopt`／`adoption-pending`／`migrate`／`update`／`current`／`policy-only-update` 七種狀態之一，再依回傳的 `next_command` 走對應流程。`adoption-pending` 表示本機 checkpoint 有效但導入尚未完成，下一步是 `csarc adopt <path> --finalize`；`migrate` 表示既有 Copier answers 使用 release tag 或短 SHA，需依指示核對並綁回已驗證 Release 的完整 SHA。固定版本的完整 agent 安裝契約見 [`docs/agent-install.md`](agent-install.md)。

## 完整細節

`<approved-full-commit-sha>` 的取得方式、`project_description`／`project_run_command`／`security_reporting_channel` 等必填欄位、既有 repo 導入的 manual merge 清單、衝突處理與 troubleshooting，見根目錄 [`README.md`](../README.md#快速開始) 的「快速開始」「公版更新」章節與 [`docs/pilot-adoption.md`](pilot-adoption.md) 的實際導入證據。要理解「為什麼這樣設計」，請讀 [repo-site](index.html)。
