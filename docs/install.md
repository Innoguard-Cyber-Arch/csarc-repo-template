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
2. **`--check`**：不修改 target，在 `../<repo>-csarc-update-report/` 寫出 stage-1 plan（`csarc-update-plan.json`）、報告 JSON 與 Markdown。有更新時 exit 1，已是最新時 0，錯誤時 2。報告的 `Items requiring your decision` 列出要處理的項目。`--data` 明確確認的值若與 CLI 推導值相同（例如 `release_ownership`），計畫與不傳值時完全相同。報告的 Settings 有 `widened` 列（例如 `admin_bypass`）時，`--finalize-plan` 前要由擁有者明確決定，見下方「放寬的設定」。`setting-decision` 列（例如 `release_ownership`、`project_run_command`）見下方「設定決定」。
3. **看衝突內容**：每個 `file-conflict` 在報告資料夾的 `conflicts/` 下有三個檔案：`conflicts/base/<path>`（目前版本的 render）、`conflicts/current/<path>`（target 現在的內容，也就是 `keep-current` 的結果）、`conflicts/new/<path>`（新版本以同一份設定 render 的結果，也就是 `take-new` 的結果）。某一側沒有檔案就是該側不存在。Jinja 模板已 render 完成，不必讀模板原始碼或試套用。`conflicts/` 每次規劃都會整個重寫。
4. **`--finalize-plan`**：一次寫出不可變的 `csarc-update-final-plan.json`。
   - 必須重帶 `--check` 用過的每個 `--to`、`--expected-sha`、`--data`、`--report-dir`，以及 `--from-release`、`--accept-legacy`、`--allow-unreleased`；CLI 會重新規劃並比對 stage-1 plan，任何輸入不同就停止，要求重新 `--check`。不能和 `--check`、`--json`、`--dry-run` 一起用。
   - 每個 `update-conflict` 恰好一個 `--decision <path>=keep-current|take-new|custom:<file>`，缺少、重複或不是衝突的路徑都會停止；沒有衝突時不帶 `--decision`。
   - `custom:<file>` 是該路徑**最終的完整檔案內容**，不是 patch。`<file>` 是絕對路徑或相對於執行指令時所在目錄的路徑，必須是 target repo 外的一般檔案（不能是 symlink），且不能含 conflict marker。內容會複製進 final plan，之後改 `<file>` 不會影響已寫出的 plan。不要放在 `conflicts/` 底下，因為那裡每次規劃都會重寫。
   - target 必須是乾淨的工作樹。本頁要求的產品準備變更（例如下方的產品 job 搬移、Action pin、ignore 例外、把舊 `scripts/verify` 裡的產品測試搬到產品驗證 hook）以獨立的產品準備 commit 在 `--finalize-plan` 前提交，提交後重新 `--check`；在 PR 逐條列出這些 commit 與依據的章節。
   - `.gitignore` 衝突的報告列會列出 current 沒有、新版有的忽略規則；用 `keep-current` 或以 current 為底的 `custom:<file>` 保留產品 `.gitignore` 時，見下方「`.gitignore` 缺少模板規則」。
   - 產品 ignore 規則（例如 `.gitignore` 的 `data/`）會隱藏新版要放的檔案時，`--check` 以該 ignore 檔為 subject 列出 blocking 的 `file-conflict`，訊息寫出被隱藏的路徑與規則。在該 ignore 檔加上例外（例如 `!.csarc/site/data/`）：它本身是衝突時寫在它的 `custom:<file>` 決定裡，否則以產品 commit 加入後重新 `--check`。`--finalize-plan` 會依決定後的內容再檢查一次，仍會隱藏時拒絕寫入。
   - 決定若讓保留的檔案繼續引用本次要退役的檔案，`--finalize-plan` 會拒絕；改用 `take-new`、`custom`，或先在產品裡移除那個引用。衝突的 current 內容（例如模板 workflow 裡的產品 job）已引用要退役的檔案時，`--check` 就在該檔的 `file-conflict` 列寫出被引用的檔案；要保留這個行為，依下方「模板 workflow 的衝突裡有產品 job」以產品準備 commit 把產品 job 搬到產品 workflow，重新 `--check` 後該檔改用 `take-new`，被引用的檔案就留給產品。
5. **`--apply-plan`**：只接受 final plan 路徑，`--to`、`--data`、`--decision` 等會改變輸入的旗標一律拒絕；`--report-dir` 只能等於 final plan 所在資料夾。沒有 `--yes` 時會顯示 plan 並詢問 `Apply this plan? [y/N]`；agent 或沒有終端輸入時要加 `--yes`。套用前重新觀察工具版本與 live facts，任何不同或驗證失敗都會在寫入前停止，target 不變；驗證失敗的訊息寫出失敗的 verify 步驟與原因（`Project verification failed: ...`）。
6. **commit 與驗證**：套用成功後檢查 diff，commit 到同一個分支，再在這個已 commit、乾淨的 head 執行 `./.csarc/scripts/verify-fast` 與產品原有檢查（本機結果綁定 exact head，未 commit 的結果不算證據），最後開 PR。
   - **後續修正 commit**：下方「根目錄 `CLAUDE.md` 與 `.claude/CLAUDE.md` 並存」「`.gitignore` 缺少模板規則」「保留的舊檔與過時連結」要求的修正（刪除保留的舊檔、修正連到舊路徑的連結、補 ignore 規則）由執行 update 的人或 agent 在同一個分支、apply 結果 commit 之後提交，每個修正一個獨立 commit，在 PR 逐條列出 SHA、內容與依據的章節。這是產品準備 commit、apply 結果 commit 之外唯一允許的第三種 commit；它不改模板管理的檔案，也不取代 plan 的決定。最後一個後續修正 commit 之後，在新的 head 重新執行 `./.csarc/scripts/verify-fast` 與產品原有檢查，以這個 head 的結果當證據。

### 失敗後重試

final plan 不可變，不要刪除或修改。要重新決定（例如 apply 的驗證失敗、live facts 改變，或改了產品檔案）時，保留舊資料夾，用新的報告資料夾重跑：

```bash
csarc update . --to <tag> --expected-sha <full-sha> --check --json --report-dir ../<repo>-csarc-update-report-2
csarc update . --to <tag> --expected-sha <full-sha> --finalize-plan --decision <path>=keep-current --report-dir ../<repo>-csarc-update-report-2
csarc update . --apply-plan ../<repo>-csarc-update-report-2/csarc-update-final-plan.json --yes
```

舊的 final plan 留著當紀錄；同一個 final plan 已套用過時重跑會說明已套用並以 0 結束，不改任何檔案。

### Action pin 漂移

`--check` 會唯讀比對產品自有 workflow 與新版模板的 Action pin，逐項列在 plan 的 `action_pin_preflight` 與報告的 `product.action_pins`。`product-pin-newer`（產品 pin 比模板新、同一 major）不擋，CLI 會把模板 workflow 對齊產品 pin；其他原因產生 blocking 的 `action-pin`。blocking 列的訊息寫出產品與模板 pin 的版本 tag（取自 pin 後面的 `# vX.Y.Z` 註解）與 `major upgrade: yes|no|unknown`：`yes` 是跨 major 升級，先讀 upstream 的變更；任一側沒有 tag 或不是版本號時寫 `unknown`，這時到 upstream 查該 SHA 對應的 tag 再判斷。規則只有一條：`--pin-commit` 只在被 finalize 的那份 stage-1 plan 仍列出 blocking pin 時必填，沒列出時傳入會被拒絕。所以標準做法是：

1. 在產品 workflow 以一個只改這些 pin 的 commit 更新 pin（可能是 major 升級，請先讀 upstream 變更）。
2. 重新 `--check`；新的 stage-1 plan 不再列出這些 pin。
3. 照常 `--finalize-plan`，不需要 `--pin-commit`。

若要沿用 commit 之前的 stage-1 plan，則在 `--finalize-plan` 加 `--pin-commit <pin commit 的完整 SHA>`；CLI 從該 commit 讀回 pin，commit 改到清單外的 pin 會停止。模板來源無法讀取或不可信時一律停止，不寫入 target。

### 模板 workflow 的衝突裡有產品 job

舊版模板 workflow（例如 `.github/workflows/ci.yml`）若被加入產品 job，新版又改寫了這個 workflow，就會出現衝突：`take-new` 會丟掉產品 job，`keep-current` 會留下引用已移除 script 的舊 workflow，把產品 job 併進新版的 `pull_request_target` workflow 則會改變它檢查的程式碼版本。標準做法：

1. 在 update 前另開一個產品 commit，把產品 job 原樣搬到產品自有的 workflow（例如 `.github/workflows/product-ci.yml`），保留原本的觸發條件。
2. 重新 `--check`，該模板 workflow 的衝突改用 `take-new`。
3. 搬出的 job 現在屬於產品 workflow，會進入 Action pin 比對；新的 blocking `action-pin` 依上一節處理。

### 其他衝突與並存檔案

擁有權依手冊 5.1：workflow、`AGENTS.md` 的 managed block 與 `.claude/CLAUDE.md` 屬模板；`.gitignore` 共同維護；產品程式與文件內容屬專案。

- **模板 workflow 有在地修正，但不是產品 job**：比對 `conflicts/base/<path>` 與 `conflicts/current/<path>`，差異就是在地修改。含產品 job 時依上一節。只是修補模板行為（例如舊版缺少 checker 時略過的 guard、舊 bug 的 workaround）時選 `take-new`：檔案屬模板，新版會取代舊行為，`keep-current` 則會留下引用已移除 script 的舊 workflow。選之前看 `conflicts/new/<path>`；新版仍缺同一個修正時，也不要保留改過的模板 workflow，`take-new` 後到模板 repository 開 Issue 回報。範例：舊版 `governance-comment.yml` 只多了「checker 不存在就略過」的 guard，新版把它改寫成 reviewer assignment，決定是 `take-new`。
- **`AGENTS.md` 沒有 CSARC managed block**：`<!-- BEGIN CSARC MANAGED BLOCK -->` 到 `<!-- END CSARC MANAGED BLOCK -->` 這一段屬模板，block 外的文字屬專案。用 `custom:<file>`：current 全文不動，最後空一行接上 `conflicts/new/AGENTS.md` 的整段 managed block，結果與 `adopt` 寫入的格式相同；current 已有一段 managed block 時，只把那一段換成新版。不要用 `take-new`（會丟掉產品指引）或 `keep-current`（少了 CSARC 入口）。範例（在 target 根目錄執行，再以 `--decision AGENTS.md=custom:../AGENTS.custom.md` 決定）：

  ```bash
  report=../<repo>-csarc-update-report
  { cat AGENTS.md; echo; sed -n '/<!-- BEGIN CSARC MANAGED BLOCK -->/,/<!-- END CSARC MANAGED BLOCK -->/p' "$report/conflicts/new/AGENTS.md"; } > ../AGENTS.custom.md
  ```

- **根目錄 `CLAUDE.md` 與 `.claude/CLAUDE.md` 並存**：`.claude/CLAUDE.md` 屬模板，只匯入 `AGENTS.md`；AI 規則以 `AGENTS.md` 為唯一來源。update 把舊的根目錄 `CLAUDE.md` 列為 `retire-modified` 時，它只是保留的舊檔，CSARC 不再讀取或更新。Claude Code 可能兩份都載入；內容不一致時以 `AGENTS.md` 為準。處理方式：把根目錄 `CLAUDE.md` 裡仍需要的產品指引搬到 `AGENTS.md` 的 managed block 外；產品文件若依賴根目錄 `CLAUDE.md`，改指向 `AGENTS.md`；最後以後續修正 commit（見上方步驟 6）刪除根目錄 `CLAUDE.md`。
- **`.github/pull_request_template.md` 有產品自加的列**：PR template 依手冊 5.1 屬模板，但產品可能在舊版裡加了自己的 checklist 列。比對 `conflicts/base/<path>` 與 `conflicts/current/<path>`，差異就是產品加的列。用 `custom:<file>`：以 `conflicts/new/.github/pull_request_template.md` 全文為底，把產品加的列原樣放回它原本所在的區段（例如 `## 完成清單` 的最後），模板的列一字不改。不要用 `keep-current`（會留下舊版模板內容，少了新版的區段與文字）；產品不再需要這些列時用 `take-new`。在 PR 列出放回的列。之後的 update 只要新版改了 PR template，這個檔案會再次衝突，照同樣方式處理。
- **`.gitignore` 缺少模板規則**：`.gitignore` 共同維護，衝突的報告列會在最後列出 current 沒有、新版有的忽略規則（`The current file lacks these template ignore rules ...`）。`keep-current` 會漏掉它們；以 current 為底的 `custom:<file>` 要把專案需要的規則加進去。最常見的是 `dist/`：`./.csarc/scripts/verify-fast` 會產生 `dist/repo-site/`，少了這條規則，verify 後工作樹會變 dirty。刻意不收某條規則時，在 PR 寫明理由。套用並執行 verify 後看 `git status`；仍有新的未追蹤產物時，以後續修正 commit 補規則，再重新 verify。

### 產品自有的 workflow audit

新版模板的 `ci.yml`、`pr-policy.yml`、`pr-review.yml`、`pr-policy-writes.yml`、`governance-comment.yml`、`dependabot-auto-merge.yml`、`dependabot-merge.yml` 刻意使用 `pull_request_target` 或 `workflow_run`。信任邊界如下：

- `pull_request_target` 讓 required check、reviewer 指派與 Dependabot 同步的 workflow 定義來自可信 base，PR 不能改寫檢查自己的程式。PR policy 與 review 只 checkout 可信 base，權限唯讀；reviewer 指派只 checkout base，PR 作者與編號通過嚴格格式檢查後才呼叫 API；Dependabot 同步先驗證 GitHub 簽署的 Dependabot head 與只改 workflow 的 diff，只執行 base 的同步程式，並以 exact-SHA lease push。CI 讀取 proposed head 來驗證，但沒有 secret 與寫入權限。
- `workflow_run` 把治理寫入與 Dependabot 合併留在 default branch 的 workflow；它只 checkout default branch 的 commit，不 checkout 觸發 run 的 head、不下載它的 artifact，只把 GitHub 提供的 PR 編號與 head SHA 當資料；寫入前重新驗證 exact head。
- 模板 repository 用 zizmor 稽核同一組 workflow，每個 `dangerous-triggers` 例外的理由寫在模板 repository 根目錄的 `zizmor.yml`。

產品自己跑 zizmor 或同類 audit 時，這些 workflow 會出現 high 等級的 `dangerous-triggers`，結果可能由綠轉紅。這不是 update 失敗；CSARC 不會修改產品的 audit 設定，也不替產品新增 ignore。由產品擁有者從下列選項決定，agent 只在 PR 列出 audit 前後的結果與選項：

1. 讓產品 audit 只掃產品自有的 workflow（例如 `.github/workflows/product-ci.yml`）；模板 workflow 依手冊 5.1 屬模板，隨核准的 Release 更新。
2. 讀過上面的信任邊界後，在產品 audit 設定為這些模板 workflow 加上 `dangerous-triggers` 例外並寫明理由，以獨立的產品 commit 提交。
3. 擁有者決定前，update PR 保持未合併。不要為了讓 audit 變綠而修改模板 workflow 的觸發條件。

### 放寬的設定（`widened`）

報告 Settings 裡 class 為 `widened` 的列表示治理範圍比以前寬，Impact analysis 也會列出 `Widened settings`。目前只有 `admin_bypass`：舊設定沒有這個鍵時遷移為 `always`（admin 可用 exact-head 授權取代同行核准，beta 與 stable 都適用），該列的 note 寫出原本的範圍。這一列不會讓 `--check` 變成 blocking，但 `--finalize-plan` 前必須由擁有者明確決定，agent 不能代為接受：

1. 接受較寬的範圍：重新 `--check` 並加 `--data admin_bypass=always`，該列改為明確選擇（`decision`，原本就是 `always` 時為 `exact`）。
2. 維持原本的範圍：重新 `--check` 並加 `--data admin_bypass=<note 寫的原值>`（`off` 或 `beta-only`），該列改為 `exact`。

`--finalize-plan` 要重帶同一個 `--data`；在 PR 記錄擁有者的決定。恢復方式：已經套用 `always` 之後才要改回時，在新的分支重新規劃，照同樣流程 finalize 與 apply；推送後由擁有者執行 repository settings 的 `plan`，審閱後再 `apply`，讓 Ruleset 也回到原本的範圍。

```bash
csarc update . --to <tag> --expected-sha <full-sha> --check --json --data admin_bypass=beta-only --report-dir ../<repo>-csarc-update-report-2
csarc update . --to <tag> --expected-sha <full-sha> --finalize-plan --data admin_bypass=beta-only --decision <path>=keep-current --report-dir ../<repo>-csarc-update-report-2
csarc update . --apply-plan ../<repo>-csarc-update-report-2/csarc-update-final-plan.json --yes
```

`beta-only` 換成 note 寫的原值；`--decision` 依該次報告的衝突照常給，沒有衝突時不帶。

### 設定決定（`setting-decision`）

報告 `Items requiring your decision` 的 `setting-decision` 列不會讓 `--check` 變成 blocking，但每一列都要在 `--finalize-plan` 前處理：接受報告的值，或依下列規則以 `--data <key>=<value>` 重新 `--check` 明確選值；`--finalize-plan` 重帶同一個 `--data`。`reviewers` 列見下方「Reviewer 指派改變」。

**`release_ownership`**：決定誰負責版本與 GitHub Release，是擁有者決定。報告 Settings 的這一列寫出原值與這份 plan 採用的值，`setting-decision` 列要求確認新值或傳入要保留的值。兩個選項：

1. `product-owned`：產品自己維護的 Release workflow（例如產品設定的 release-please）繼續負責版本與 Release，CSARC 只回報 drift。產品有自己維護、仍要繼續使用的 writer 時選這項。
2. `csarc-owned`：CSARC 的 `release.yml` 與 version policy 負責版本、CHANGELOG 與 Release，`version.txt` 與 CHANGELOG 沿用原本的值。原本的 Release workflow 是舊版模板產生的、產品沒有自己的發版流程，或擁有者要改由 CSARC 發版時選這項。

選 `product-owned` 後，若 `--check` 列出 blocking 的 `release-writer`，表示保留的 writer 用到這次要搬進 `.csarc/` 的檔案（訊息逐項寫出 `原路徑 -> 新路徑`），`--finalize-plan` 會拒絕。這時只有兩條路：改選 `csarc-owned`，或先以產品準備 commit 讓 writer 不再使用這些路徑，再重新 `--check`；後者會產生產品 diff。agent 依上面的判斷方式在 PR 寫出選擇、理由與 `release-writer` 訊息，合併前由擁有者確認。`verification-only`（CSARC 只驗證、不管理發布）只在擁有者明確要求時使用。

**`project_run_command`**：產品最短的啟動或呼叫指令（`package_name` 規則相同）。CLI 能從 native manifest（`pyproject.toml`、`package.json`、`Cargo.toml`、`go.mod`）唯一推導時不保存這個值；update 使用的值記在 `.csarc/provenance.json` 的 render context，`.csarc/config.yml` 不會列出它。推導結果與記錄值不同、或無法唯一推導時，報告列出 `setting-decision`，記錄值繼續保留：

- 不傳 `--data`：沿用記錄值，產品行為不變。
- 要改用其他指令：以 `--data project_run_command=<command>` 明確決定。這個值寫進 `.csarc/config.yml`，之後的 update 一律優先使用它，不再依 manifest 推導。

### Reviewer 指派改變（`reviewers`）

舊設定的 `reviewers` 與 `.github/REVIEWERS` 已退役：Settings 那一列仍是 `retired`，note 寫出原本的 reviewer、新的指派方式與恢復方式；`Items requiring your decision` 另列一列非 blocking 的 `setting-decision`（subject `reviewers`）。新版本在每個 ready PR 從具 maintain 或 admin 權限、且不是作者的協作者中輪流請求一位 reviewer。這一列和 `widened` 一樣不會讓 `--check` 變成 blocking，但 `--finalize-plan` 前必須由擁有者確認，agent 不能代為接受。要維持原本的 reviewer，只給他們 maintain 或 admin 權限，或用 `--data code_owner=<owners>` 把他們設為 code owner，讓 GitHub 在每個 PR 請求他們審查；在 PR 記錄擁有者的決定。

### 保留的舊檔與過時連結

- 仍被使用的舊檔：新版本不再產生的檔案若仍被保留的檔案以完整路徑引用，或是工具會自動讀取的設定（`zizmor.yml`、`.gitleaks.toml`、`.pre-commit-config.yaml`），計畫改列 `preserve`／`product-owned`，不會刪除；之後由產品自行維護。搬到 `.csarc/scripts/` 的 script 若仍被產品以舊路徑呼叫，舊路徑留下轉呼叫 wrapper（`overwrite`／`compatibility-shim`）。產品自有的 Release writer（`release_ownership=product-owned`）若仍使用本次要搬進 `.csarc/` 的檔案（例如 release-please 的 config、manifest 與它隱含的 `version.txt`），計畫列出 blocking 的 `release-writer`，`--finalize-plan` 拒絕寫入；改用 `--data release_ownership=csarc-owned`，或先以產品 commit 讓 writer 不再使用這些路徑，再重新 `--check`。怎麼選見「設定決定」。
- `retire-modified`：新版本不再產生、但內容和舊 render 不同的檔案（例如根目錄的 `scripts/verify`）會原地保留，新的版本在 `.csarc/scripts/`。保留的舊檔不再由 CSARC 呼叫或更新；確認沒有產品檔案、文件或 workflow 還在引用後，以後續修正 commit（見上方步驟 6）刪除，避免有人誤用舊版。保留的舊 script 若仍呼叫或讀取同一份計畫刪除或搬走的檔案（例如保留的 `scripts/verify` 呼叫被刪除的 `scripts/test-pr-policy`、讀取搬到 `.csarc/policies/` 的 `policies/*.json`），套用後就無法執行：該列 `retire-modified` 改為 blocking，訊息列出每個用到的路徑。不需要產品 commit：在 `--finalize-plan` 加 `--decision scripts/verify=take-new`，照新版本的做法把這個舊 script 退役（新版本在 `.csarc/scripts/`）；`retire-modified` 只接受 `take-new`，不帶就保留，保留時 `--finalize-plan` 拒絕寫入。若計畫保留的其他檔案（例如產品 workflow、另一個保留的舊 script）仍呼叫被退役的檔案，`--finalize-plan` 也拒絕，請一併退役那個舊 script。要保留這個 script 時，改以產品 commit 讓它不再使用這些路徑（例如改呼叫 `.csarc/scripts/` 的版本），再重新 `--check`。保留的舊 script 若含有產品自己加入的測試呼叫（舊 render 沒有、會執行產品檔案或測試工具的那一行，例如 `./scripts/test-sync-skills`），`retire-modified` 列的訊息會逐行列出這些呼叫。退役後 CSARC verify 不再執行它們，驗證範圍會靜默縮小，所以在 `take-new` 或刪除之前，先把產品測試搬到產品驗證 hook：把這些呼叫寫進產品自己的可執行 script（沒有設定 hook 時，CSARC 會使用可執行的 `scripts/verify-product`；也可以用 `--data project_verification_hook=<path>` 指定其他路徑），以產品準備 commit 提交，再重新 `--check` 並在之後的步驟帶同一個 `--data`。hook 不得呼叫舊的 `scripts/verify`。
- 搬移：報告的 `move` 列是 update 搬動的路徑（例如 `CLAUDE.md` 移到 `.claude/CLAUDE.md`、`scripts/` 移到 `.csarc/scripts/`）。用 `keep-current` 或 `custom` 保留的產品文件（例如 `docs/README.md`）可能還連到舊路徑；套用後依 `move` 列搜尋舊路徑，以後續修正 commit 修正連結。
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
