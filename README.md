# CSARC Repo Template

## 專案概述

Cyber-Arch 的跨語言 repo 公版來源。Copier 讓新專案與既有專案保留來源關係；後續政策更新會先成為可審查的變更，而不是直接改壞各專案。

## 技術與目錄

語言會決定套件管理、格式、型別檢查、測試與打包方式，因此必須在 Copier 建立或導入時宣告 `python`、`typescript` 或 `python-typescript`。選擇會寫進 `.csarc/profile.json`；`scripts/detect-language-profile --suggest` 依 `pyproject.toml` 與 `package.json` 判斷實際模組，`scripts/verify` 會阻擋宣告與檔案不一致。自動判斷只作防呆，不會在不知情下替團隊改變語言契約。

跨語言共用的是 GitHub 工作單、PR、CODEOWNERS、Ruleset、Actions 權限、Gitleaks、Zizmor、依賴警示與交付證據。`.gitignore` 固定涵蓋 macOS、Windows、Linux 與常見 IDE 暫存檔，再依 profile 只加入 Python、TypeScript 或兩者的產物規則；作業系統與 IDE 不做建立者限定，避免其他貢獻者的環境雜訊進入 repo。Python 模組使用 `src/`、`tests/`、`pyproject.toml`、`uv.lock`、uv、Ruff、mypy、pytest 與 wheel；TypeScript 模組使用 `typescript/src/`、`typescript/tests/`、`package.json`、`pnpm-lock.yaml`、Biome、TypeScript、Vitest 與 npm tarball。混合 repo 同時產生並驗證兩組；Go、Rust 維持 `future`。

Python 以 [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) 為基準，行寬採官方的 80 字元，沒有另設例外。Ruff 的對應如下：

- `ruff format`、`E` 與 80 字元行寬：排版、空白與行長。
- `I`：import 分組與排序；`N`：命名慣例。
- `D` 加上 `pydocstyle.convention = "google"`：Google 形式的 docstring。
- `ANN` 搭配 strict mypy：型別提示與型別正確性。
- `F`、`B`、`S`、`C901`、`T20`：未使用或未定義名稱、常見錯誤、安全、複雜度與遺留 debug print。

工具無法判斷名稱是否真的清楚、設計是否好懂，這些仍由 PR 審查確認。

Python 新案預設使用公版已審查的最新穩定功能版本，目前是 3.14；公版本身也使用相同版本。新功能版本正式發布滿三十天後，排程才會同步公版、模板、Ruff、mypy、CI 與鎖定檔，實跑完整驗證，再由專用 GitHub App 留下 PR 紀錄並自動合併；工具尚未支援或測試失敗就不合併。建立專案時不會上網解析 `latest`，所以同一份公版 commit 仍會產生相同結果。若專案必須支援舊版，可選 `python_support_mode=minimum` 並宣告最低版本；CI 同時驗證最低版本與 3.14。

TypeScript 以 Node 24 Active LTS（仍受積極維護的長期支援版）為目前基線，pnpm 11 管理相依；Biome 同時負責排版與 lint、TypeScript strict 模式檢查型別、Vitest 執行測試與 80% coverage，避免再疊加 ESLint 與 Prettier。Node 新 Active LTS 同樣先觀察三十天，再經 PR 更新 `.node-version`、`package.json`、CI 與 catalog 並跑三種 profile 的完整驗證。Go 與 Rust 日後分別依 stable toolchain 與 MSRV（最低支援 Rust 版本）設計，不套用 Python 名詞。

## `AGENTS.md` 標準版

`AGENTS.md` 是 AI 的工作契約，不是第二份 README。公版固定提供適用範圍與來源、工作迴圈、可執行命令、編輯邊界、安全規則與 `Code Review Rules`；語言迭代命令依 profile 產生，格式與 lint 細節仍以 `pyproject.toml`、`biome.json` 與 `./scripts/verify` 為準。`CLAUDE.md` 只匯入 `AGENTS.md`，避免維護兩份規則。

公版與生成專案都限制在 200 行內。只有子目錄真的有不同命令、owner 或安全邊界時才增加就近 `AGENTS.md`；不要預先建立空檔，也不要用文字重複 CI 已能確定檢查的規則。完整選型與高星 repo 比較記錄在上層 `SUPPLEMENT.md`。

## 哪些檔案由公版影響

`template/` 是下發到其他 repo 的唯一內容來源。根目錄的 `.github/`、`policies/` 與工具設定只服務公版本身；GitHub 必須從 repo 根目錄讀取這些檔案，所以不能全部移進 `template/`。兩層相同的政策與 workflow 由 `scripts/verify-template.sh` 自動比對，避免人工維護出現漂移。

| 類型 | 代表檔案 | 更新規則 |
| --- | --- | --- |
| 公版主導 | `.github/`、`policies/`、`.gitignore`、`scripts/verify`、`README.md`、`AGENTS.md`、`CLAUDE.md` | Copier 更新時提出差異，必須經 PR 審查 |
| 共同維護 | `pyproject.toml`、`package.json`、`CODEOWNERS` | 公版可補規則，專案可加依賴或說明；衝突由人處理 |
| 專案持有 | `src/`、`tests/`、`typescript/src/`、`typescript/tests/`、`docs/specs/` | 初次建立骨架後由專案維護；`_skip_if_exists` 防止後續模板改寫 |

`.copier-answers.yml` 記錄來源、版本與選項。Copier 更新只產生可檢查的 Git 差異，不會直接合併到 `main`。

`README.md` 是給人看的操作入口，公版規範必要章節與共同命令；專案仍可修改標題、說明並增加領域文件。`scripts/verify` 只檢查必要章節是否存在，不限制專案自行增加內容；Copier 更新 README 時若同一段同時被修改，必須在 PR 內人工解決衝突。

README 的最低標準是回答以下八件事：

| 必要章節 | 最少要回答 |
| --- | --- |
| 專案概述 | 解決什麼問題、誰會使用、主要輸出與使用範圍是什麼 |
| 快速開始 | 前置工具，以及最短可成功的安裝、啟動或呼叫範例 |
| 技術與目錄 | 語言 profile、重要目錄、技術基線與限制 |
| 開發與驗證 | 日常流程、測試／lint／build 的共同命令 |
| 設定與密鑰 | 設定名稱、用途、取得位置；敏感值不得寫入 README 或提交到 Git |
| 發布與維運 | 版本、成品、部署邊界；若有服務則附健康檢查、復原與 runbook |
| 負責人與支援 | CODEOWNER、一般問題入口與資安事件通報方式 |
| 公版更新 | Copier 更新、相依更新、衝突處理與驗證方式 |

GitHub 官方建議 README 至少說明專案做什麼、為何有用、如何開始、去哪裡求助及誰在維護；公版再補上內部工程需要的設定、驗證、發布與更新責任。完整參考比較記在上層 `SUPPLEMENT.md`。

## 快速開始

人工安裝的共同工具是 Git、GitHub CLI 與 uv；Copier 由 `uvx` 執行，不必另外安裝。TypeScript 或混合 profile 另需 Node 24 以上與 pnpm 11。`./scripts/verify` 還會使用 Bash、curl、tar、awk、`shasum` 與 coreutils 提供的基本指令（例如 `dirname`、`wc`、`cat`、`mkdir`、`chmod`）：macOS 已內建這些系統工具，可用 Homebrew 安裝：

```bash
brew install git gh uv node pnpm
```

Windows 建議使用 WSL2（Ubuntu），並在 WSL 裡操作 repo，因為公版的驗證入口使用 Bash：

```powershell
wsl --install -d Ubuntu
```

進入 Ubuntu 後：

```bash
sudo apt update
sudo apt install -y git gh curl ca-certificates bash coreutils tar gawk libdigest-sha-perl
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pnpm@11.22.0
```

`libdigest-sha-perl` 提供公版腳本使用的 `shasum`。Python、Ruff、mypy、pytest、Zizmor 與 Copier 由 uv／uvx 依鎖定版本準備；Biome、TypeScript 與 Vitest 由 pnpm 依鎖定檔準備；Gitleaks 由公版腳本下載並驗證 checksum，不必手動安裝。Python-only repo 不需要 Node／pnpm；TypeScript-only repo 也不要求系統 Python，少量共用平台腳本由 uv 提供隔離的直譯器，不會形成 Python 產品模組。

取得公版後，最短的成功路徑是先跑完整自我驗證：

```bash
git clone https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git
cd csarc-repo-template
./scripts/verify-template.sh
```

上面的純本機驗證不需要 GitHub token。只有 clone private repo、套用 GitHub 設定，或執行 Actions／release／Issue 的端到端測試時才需要登入；請在自己的終端執行，不要把 token 貼進文件或對話：

```bash
gh auth login -h github.com
gh auth status
```

## 建立新專案

執行來源要固定到已審查的完整 commit SHA，不能只信任可被移動的 tag：

```bash
uvx --from copier copier copy --trust --overwrite \
  --vcs-ref <reviewed-full-commit-sha> \
  https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git \
  ./my-project
cd ./my-project
./scripts/verify
```

Copier 會要求選擇 Python-only、TypeScript-only 或兩者都有；預設仍是 Python。兩種語言都採全專案 coverage 80%，並共用 PR、安全與交付規則。這些選項會記在 `.copier-answers.yml` 與 `.csarc/profile.json`，之後更新仍能重現同一個專案設定。

## 既有專案導入

先開分支，再讓 Copier 產生差異；不要直接在 `main` 覆寫：

```bash
git switch -c chore/adopt-csarc-template
uvx --from copier copier copy --trust \
  --vcs-ref <reviewed-full-commit-sha> \
  --data project_mode=existing \
  --data language=<python|typescript|python-typescript> \
  --data coverage_mode=diff \
  https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git \
  .
```

`--overwrite` 只讓公版管理的檔案採用本次內容；既有專案模式仍會保留原有 `pyproject.toml` 與 `package.json`，不會替你合併相依或打包設定。先把公版要求的 dev 相依、Ruff／mypy／coverage、`project.version`，以及 `src/<package>/__init__.py` 的 `__version__` 標記人工合併，再重新產生 lockfile。這個保護會讓尚未完成遷移的 `./scripts/verify` 明確失敗，但不會讓既有產品相依、版本或 build backend 被整份取代。

既有技術債不是降低全隊標準，而是把例外寫清楚：

```bash
# Apply deterministic formatting before reviewing remaining lint debt.
uv run ruff format .

# One-time migration: mark selected Ruff violations as explicit legacy debt.
uv run ruff check --add-noqa src/legacy_package
```

無法一次完成型別整理的舊模組，在 `pyproject.toml` 指定範圍，不可全域關閉 mypy：

```toml
[[tool.mypy.overrides]]
module = ["legacy_package.*"]
ignore_errors = true
```

`coverage_mode=diff` 只檢查這次改動的行，但門檻仍是 80%。第一次驗證前要先有 `origin/main`，或把 `DIFF_COVER_COMPARE_BRANCH` 指向實際存在的基準 commit；若 ref 不存在，腳本會直接告訴你該設定哪個變數，不再吐出 Python traceback。導入後執行 `./scripts/verify`，確認差異，再用 PR 合併。

## 開發與驗證

只有維護公版本身並執行 `scripts/verify-template.sh` 時，才額外需要 `rsync`、`diff` 與 `grep`。macOS 已內建；Ubuntu／WSL2 可執行 `sudo apt install -y rsync diffutils grep`。

公版本身也使用鎖定的 Python 工具、OSV、Zizmor 與 Gitleaks。每次修改先執行：

```bash
./scripts/verify-template.sh
```

這支腳本會驗證 root 與產出專案共用政策，產生 Python-only、TypeScript-only、混合、最低 Python 與 Copier 更新情境，並實跑 `./scripts/verify`。Python 會建 wheel、隔離匯入並檢查 metadata；TypeScript 會執行 Biome、strict typecheck、Vitest coverage、建 npm tarball，再安裝到乾淨目錄 import。混合 repo 必須兩套都通過，更新測試也會確認兩邊產品原始碼未被公版覆寫。

## 發布與維運

發布新版不再手動改版本號。合併到 `main` 的 squash commit 會保留 PR 標題；release-please 依 Conventional Commits（從標題判斷版本）維護 `pyproject.toml`、`uv.lock` 與 `CHANGELOG.md`，並開一張 Release PR。審查並合併該 PR 後，它才建立 `v*` tag 與 GitHub Release；tag 接著觸發既有 `release-template.yml` 驗證。`fix` 升修補版、`feat` 升次版；破壞性變更使用英文標題 `feat!: summary` 或 `feat(scope)!: summary`，由 `!` 觸發大版升級。PR 內文可使用中文。

本 repo 發布的是 Copier 公版，不是長駐服務；沒有部署環境、健康檢查或回復服務版本的 runbook。發生問題時撤回有問題的公版 tag，並以修正版重新走完整驗證與發布。

## 公版更新

發布後，把實際 commit SHA 提供給各專案更新。專案端應從分支執行：

```bash
git switch -c chore/update-repo-template
uvx --from copier copier update --trust --vcs-ref <reviewed-full-commit-sha>
./scripts/verify
```

## 已完成範圍

- Ruff、mypy、pytest、coverage.py／pytest-cov、diff-cover 與 Gitleaks 共用單一驗證入口。
- TypeScript 使用 Biome、TypeScript strict、Vitest coverage 與 npm 打包；混合 repo 同一入口兩套都跑。
- PR 標題、Issue Form、CODEOWNERS、Ruleset、Actions 權限、合併策略與 labels 以檔案管理。
- Spec 合併到 `main` 後，由標準函式庫腳本建立或更新一張對應 Issue。
- Dependabot 分別更新 uv 與 npm 生態，一般更新等待三天；pnpm resolver 也以嚴格模式拒絕發布未滿三天的版本，OSV 對已公開漏洞立即掃描。
- 發布時建立 SHA-256、CycloneDX SBOM，並可選 GitHub artifact attestation。
- 所有第三方 Actions 固定完整 commit SHA；Zizmor 每次 PR 都會檢查。

Go、Rust、部署環境、可觀測性、RAG 與自動 agent loop 仍是 `future`，有真實使用專案與責任人，且建立與更新測試都通過後才新增。

## 設定與密鑰

### 套用 GitHub 設定

管理者先看計畫，再套用版本化政策：

```bash
gh auth status
./scripts/apply-repository-settings.sh plan
./scripts/apply-repository-settings.sh apply
```

它會設定 squash-only、Actions 預設唯讀、labels 與 `main` Ruleset。執行者需要目標 repo 的管理權限及可讀取 Organization team 的授權；若 `gh auth status` 失敗，先用 `gh auth login -h github.com` 重新登入。腳本會先確認 `.github/CODEOWNERS` 指向真實存在且登入者可見的 team，避免唯一個人 owner 自己開 PR 後無人可核准。團隊存取權仍由 GitHub Organization 管理。

### 啟用無人值守的 Python 升版

建立一個只安裝在此 repo 的 GitHub App，給予 Contents 與 Pull requests 讀寫、Checks 唯讀權限；把 App ID 存成 repository variable `CSARC_VERSION_BOT_APP_ID`，private key 存成 repository secret `CSARC_VERSION_BOT_PRIVATE_KEY`。管理者套用 Ruleset 時帶入 App ID，腳本只讓這個 App 以 PR 形式略過人工核准，不允許直接寫入 `main`：

```bash
CSARC_VERSION_BOT_APP_ID=<app-id> \
  ./scripts/apply-repository-settings.sh apply
```

`.github/workflows/python-version-policy.yml` 每週查詢 Python 官方發布資料，並將各項直接 dev 相依的 PyPI 最新版交給 uv 實際解析，讓 Actions summary 顯示可升級項目或完整衝突鏈。新功能版本滿三十天後，`scripts/update_python_version.py` 會同步 root 與模板設定、保留既有最低版本選項、更新 `uv.lock` 並實跑完整驗證；GitHub App 接著建立 PR、等待所有門禁通過，再自動合併。沒有設定 App 憑證時，排程會明確失敗，不會退回權限較大的個人 token 或直接推送。

### 啟用 release-please

同一個 GitHub App 也供 `.github/workflows/release-please.yml` 使用。release-please 不要求新增 Ruleset bypass，Release PR 仍由人員合併。Organization 管理者只需設定一次：

1. 到 **Settings → Developer settings → GitHub Apps → New GitHub App** 建立專用 App；不需要 webhook。
2. Repository permissions 設為 **Contents: Read and write**、**Pull requests: Read and write**；若同時啟用 Python 無人值守升版，再加 **Checks: Read-only**。
3. 將 App 安裝到這個 repo、記下 App ID，並在 App 頁面產生 private key PEM 檔。
4. 在 repo 根目錄執行下列指令；完成後刪除本機下載的 PEM，或移入團隊核准的密鑰管理工具。

```bash
gh variable set CSARC_VERSION_BOT_APP_ID --body '<app-id>'
gh secret set CSARC_VERSION_BOT_PRIVATE_KEY < ./private-key.pem
```

workflow 每次執行才用 private key 產生短效 token，不需要人工建立或保存 token。使用 App token 是必要的：預設 `GITHUB_TOKEN` 建立的 tag 不會觸發下一支 Actions workflow，因此無法串到 `release-template.yml`。

`.env` 不是所有秘密的共同解法：Actions 用 GitHub Secrets／Variables，正式環境用雲端密鑰管理或 OIDC；只有本機程式確實需要環境變數時，才使用不提交的 `.env`。Python 與 uv 不會自動載入它，應由實際應用明確決定載入方式；repo 最多提交去除敏感值的 `.env.example`。目前公版本身沒有 runtime secret，因此不建立空的 `.env`。

`release-please-config.json` 依 profile 使用 Python 或 Node release type；混合 repo 以同一個 SemVer 同步 `package.json`、`pyproject.toml`、`uv.lock` 與 Python 套件版本。`.release-please-manifest.json` 記錄目前已發布版本，避免 Release PR 只更新其中一邊。

## 負責人與支援

程式與政策審查者以 `.github/CODEOWNERS` 為準。一般缺陷、功能需求與可重現的公版更新問題使用 GitHub Issue；驗證失敗先看失敗 job 的第一個實際錯誤。疑似資安事件、token、私鑰或其他敏感資料不可貼入 Issue，應走 Cyber-Arch 核准的內部通報管道。

## 供應鏈原則

版本號與 tag 方便人閱讀，但不足以證明實際內容。Python 的 `uv.lock` 與 TypeScript 的 `pnpm-lock.yaml` 都記錄下載成品的完整性雜湊；`uv sync --locked`、`pnpm install --frozen-lockfile` 會拒絕設定與 lockfile 不一致。Actions 使用完整 commit SHA、Gitleaks 下載會先驗證官方 checksum 清單及檔案雜湊；發布成品另附 checksum、SBOM 與可選來源證明。雜湊只能證明 bytes 一致，仍要搭配可信來源與審查。
