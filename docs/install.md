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

`adopt` 預設為 dry-run，只在 repo 外產生 machine-readable plan、作為唯一來源的 report JSON 與由它 render 的 Markdown 導入報告（[SPEC-008](specs/SPEC-008-lifecycle-report-format.md)），不修改 repo；確認後才用 `--apply-plan` 套用。

`code_owner` 預設為空值（不產生 CODEOWNERS）；組織 repo 以 `--data code_owner=@<organization>/<team>` 指定 team，個人 repo 則用 `--data code_owner=@<user>`。`repository_url` 只取自 GitHub origin、`GH_REPO` 或明確傳入的值，不由 owner 推導。尚未設定 remote 的本機 repo 會把有值的 owner 標成 `unknown`，允許先審查導入計畫，但需傳入合法的 `--data repository_url=https://github.com/<owner>/<repository>`，即使文件模式關閉也不能省略。push 後再依序執行產生的 repository settings `plan`／`apply`／`check`。檢查不會自動授予 user／team 權限，owner 不存在或沒有 write 以上權限時會停止。

## 更新已導入的 repo

更新入口只有 `csarc update`；直接執行 `copier update` 不受支援。下面的 `csarc` 代表 `uvx --python 3.14 --from 'git+https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git@<approved-full-commit-sha>' csarc`，`<tag>` 與 `<full-sha>` 是核准的 Release tag 與完整 commit SHA，`<repo>` 是 target 資料夾名稱。在 target 的乾淨 clone 裡執行：

```bash
git switch -c chore/<issue-number>-update-repo-template
csarc status . --to <tag> --expected-sha <full-sha> --json
csarc update . --to <tag> --expected-sha <full-sha> --check --json
csarc update . --to <tag> --expected-sha <full-sha> --finalize-plan --decision <path>=keep-current
csarc update . --apply-plan ../<repo>-csarc-update-report/csarc-update-final-plan.json --yes
./.csarc/scripts/verify-fast
```

1. **`status`**：回報 `update` 時，照 `next_command` 走；它已帶上 `--to` 與 `--expected-sha`。beta 或指定版本一定要帶這兩個旗標，否則 CLI 會改用最新 stable。
2. **`--check`**：不修改 target，在 `../<repo>-csarc-update-report/` 寫出 stage-1 plan（`csarc-update-plan.json`）、報告 JSON 與 Markdown。有更新時 exit 1，已是最新時 0，錯誤時 2。報告的 `Items requiring your decision` 列出要處理的項目。`--data` 明確確認的值若與 CLI 推導值相同（例如 `release_ownership`），計畫與不傳值時完全相同。
3. **看衝突內容**：每個 `file-conflict` 在報告資料夾的 `conflicts/` 下有三個檔案：`conflicts/base/<path>`（目前版本的 render）、`conflicts/current/<path>`（target 現在的內容，也就是 `keep-current` 的結果）、`conflicts/new/<path>`（新版本以同一份設定 render 的結果，也就是 `take-new` 的結果）。某一側沒有檔案就是該側不存在。Jinja 模板已 render 完成，不必讀模板原始碼或試套用。`conflicts/` 每次規劃都會整個重寫。
4. **`--finalize-plan`**：一次寫出不可變的 `csarc-update-final-plan.json`。
   - 必須重帶 `--check` 用過的每個 `--to`、`--expected-sha`、`--data`、`--report-dir`，以及 `--from-release`、`--accept-legacy`、`--allow-unreleased`；CLI 會重新規劃並比對 stage-1 plan，任何輸入不同就停止，要求重新 `--check`。不能和 `--check`、`--json`、`--dry-run` 一起用。
   - 每個 `update-conflict` 恰好一個 `--decision <path>=keep-current|take-new|custom:<file>`，缺少、重複或不是衝突的路徑都會停止；沒有衝突時不帶 `--decision`。
   - `custom:<file>` 是該路徑**最終的完整檔案內容**，不是 patch。`<file>` 是絕對路徑或相對於執行指令時所在目錄的路徑，必須是 target repo 外的一般檔案（不能是 symlink），且不能含 conflict marker。內容會複製進 final plan，之後改 `<file>` 不會影響已寫出的 plan。不要放在 `conflicts/` 底下，因為那裡每次規劃都會重寫。
   - target 必須是乾淨的工作樹：產品準備變更與 pin 變更都要先 commit。
   - 產品 ignore 規則（例如 `.gitignore` 的 `data/`）會隱藏新版要放的檔案時，`--check` 以該 ignore 檔為 subject 列出 blocking 的 `file-conflict`，訊息寫出被隱藏的路徑與規則。在該 ignore 檔加上例外（例如 `!.csarc/site/data/`）：它本身是衝突時寫在它的 `custom:<file>` 決定裡，否則以產品 commit 加入後重新 `--check`。`--finalize-plan` 會依決定後的內容再檢查一次，仍會隱藏時拒絕寫入。
   - 決定若讓保留的檔案繼續引用本次要退役的檔案，`--finalize-plan` 會拒絕；改用 `take-new`、`custom`，或先在產品裡移除那個引用。
5. **`--apply-plan`**：只接受 final plan 路徑，`--to`、`--data`、`--decision` 等會改變輸入的旗標一律拒絕；`--report-dir` 只能等於 final plan 所在資料夾。沒有 `--yes` 時會顯示 plan 並詢問 `Apply this plan? [y/N]`；agent 或沒有終端輸入時要加 `--yes`。套用前重新觀察工具版本與 live facts，任何不同或驗證失敗都會在寫入前停止，target 不變；驗證失敗的訊息寫出失敗的 verify 步驟與原因（`Project verification failed: ...`）。
6. **commit 與驗證**：套用成功後檢查 diff，commit 到同一個分支，執行 `./.csarc/scripts/verify-fast` 與產品原有檢查，再開 PR。

### 失敗後重試

final plan 不可變，不要刪除或修改。要重新決定（例如 apply 的驗證失敗、live facts 改變，或改了產品檔案）時，保留舊資料夾，用新的報告資料夾重跑：

```bash
csarc update . --to <tag> --expected-sha <full-sha> --check --json --report-dir ../<repo>-csarc-update-report-2
csarc update . --to <tag> --expected-sha <full-sha> --finalize-plan --decision <path>=keep-current --report-dir ../<repo>-csarc-update-report-2
csarc update . --apply-plan ../<repo>-csarc-update-report-2/csarc-update-final-plan.json --yes
```

舊的 final plan 留著當紀錄；同一個 final plan 已套用過時重跑會說明已套用並以 0 結束，不改任何檔案。

### Action pin 漂移

`--check` 會唯讀比對產品自有 workflow 與新版模板的 Action pin，逐項列在 plan 的 `action_pin_preflight` 與報告的 `product.action_pins`。`product-pin-newer`（產品 pin 比模板新、同一 major）不擋，CLI 會把模板 workflow 對齊產品 pin；其他原因產生 blocking 的 `action-pin`。規則只有一條：`--pin-commit` 只在被 finalize 的那份 stage-1 plan 仍列出 blocking pin 時必填，沒列出時傳入會被拒絕。所以標準做法是：

1. 在產品 workflow 以一個只改這些 pin 的 commit 更新 pin（可能是 major 升級，請先讀 upstream 變更）。
2. 重新 `--check`；新的 stage-1 plan 不再列出這些 pin。
3. 照常 `--finalize-plan`，不需要 `--pin-commit`。

若要沿用 commit 之前的 stage-1 plan，則在 `--finalize-plan` 加 `--pin-commit <pin commit 的完整 SHA>`；CLI 從該 commit 讀回 pin，commit 改到清單外的 pin 會停止。模板來源無法讀取或不可信時一律停止，不寫入 target。

### 模板 workflow 的衝突裡有產品 job

舊版模板 workflow（例如 `.github/workflows/ci.yml`）若被加入產品 job，新版又改寫了這個 workflow，就會出現衝突：`take-new` 會丟掉產品 job，`keep-current` 會留下引用已移除 script 的舊 workflow，把產品 job 併進新版的 `pull_request_target` workflow 則會改變它檢查的程式碼版本。標準做法：

1. 在 update 前另開一個產品 commit，把產品 job 原樣搬到產品自有的 workflow（例如 `.github/workflows/product-ci.yml`），保留原本的觸發條件。
2. 重新 `--check`，該模板 workflow 的衝突改用 `take-new`。
3. 搬出的 job 現在屬於產品 workflow，會進入 Action pin 比對；新的 blocking `action-pin` 依上一節處理。

### 保留的舊檔與過時連結

- 仍被使用的舊檔：新版本不再產生的檔案若仍被保留的檔案以完整路徑引用，或是工具會自動讀取的設定（`zizmor.yml`、`.gitleaks.toml`、`.pre-commit-config.yaml`），計畫改列 `preserve`／`product-owned`，不會刪除；之後由產品自行維護。搬到 `.csarc/scripts/` 的 script 若仍被產品以舊路徑呼叫，舊路徑留下轉呼叫 wrapper（`overwrite`／`compatibility-shim`）。
- `retire-modified`：新版本不再產生、但內容和舊 render 不同的檔案（例如根目錄的 `scripts/verify`）會原地保留，新的版本在 `.csarc/scripts/`。保留的舊檔不再由 CSARC 呼叫或更新；確認沒有產品檔案、文件或 workflow 還在引用後，另開 commit 刪除，避免有人誤用舊版。
- 搬移：報告的 `move` 列是 update 搬動的路徑（例如 `CLAUDE.md` 移到 `.claude/CLAUDE.md`、`scripts/` 移到 `.csarc/scripts/`）。用 `keep-current` 或 `custom` 保留的產品文件（例如 `docs/README.md`）可能還連到舊路徑；套用後依 `move` 列搜尋舊路徑，另開 commit 修正連結。
- 網站內容：專案維護的 `docs/site/content/`、`docs/site/data/navigation.json` 與 `docs/site/theme.css` 原封不動保留；舊位置的 `site/content/`、`site/data/navigation.json`、`docs/site-theme.css` 以 `move` 搬到新位置，`docs/index.html`／`docs/index.en.html` 依保留的內容重建。
- `docs/README.md` 是專案自己的文件入口，可以 `keep-current`；CSARC 的文件地圖在 `.csarc/docs/documentation-policy.md`，verify 只檢查那裡。

### 套用時的附帶訊息

- `CODEOWNERS validation failed: ... is missing, invisible, or lacks repository access`：CODEOWNERS 指定的 team 不存在、看不到或沒有 repository 權限。update 已完成；請擁有者補 team 權限，或之後以 `--data code_owner=...` 更新。
- repository settings：update 只執行 `.csarc/scripts/apply-repository-settings.sh plan`，從不套用設定。只有 origin 不是 GitHub repository 時才印 `Repository settings plan needs a GitHub origin remote`；其他失敗印 `Repository settings plan failed (exit N): <原因>`，例如 CODEOWNERS 驗證失敗。push 後由擁有者執行 `plan`，審閱後再 `apply`。

### 平行執行

同一台機器一次只跑一個 `csarc` 指令。兩個 `csarc` 同時執行時，Copier 共用的 git 快取會互相干擾，結果不可靠；要更新多個 repo 時請依序執行。

## 不確定目前狀態時

先用「自動判斷」：`csarc status` 只讀本機檔案與（若已導入）GitHub 上的公版版本與 repository 設定，判斷屬於 `create`／`adopt`／`adoption-pending`／`migrate`／`update`／`current`／`policy-only-update` 七種狀態之一，再依回傳的 `next_command` 走對應流程。`adoption-pending` 表示本機 checkpoint 有效但導入尚未完成，下一步是 `csarc adopt <path> --finalize`；`migrate` 表示既有 Copier answers 使用 release tag 或短 SHA，需依指示核對並綁回已驗證 Release 的完整 SHA；偵測到直接執行過 `copier update`（answers 的 `_commit` 與 provenance 不符，或留下 `.rej`）時也回報 `migrate`，這只是偵測結果，不代表遷移完成，需還原後改用 `csarc update`。固定版本的完整 agent 安裝契約見 [`docs/agent-install.md`](agent-install.md)。

## 完整細節

`<approved-full-commit-sha>` 的取得方式、`project_description`／`copyright_holder`／`security_reporting_channel` 等必填輸入與工作模式（[SPEC-009 §9](specs/SPEC-009-project-settings.md)）、既有 repo 導入的 manual merge 清單、衝突處理與 troubleshooting，見根目錄 [`README.md`](../README.md#快速開始) 的「快速開始」「公版更新」章節與 [`docs/pilot-adoption.md`](pilot-adoption.md) 的實際導入證據。要理解「為什麼這樣設計」，請讀 [repo-site](index.html)。
