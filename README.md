# CSARC Repo Template

Cyber-Arch 的可更新 repo 公版，支援 CI/CD-only、Python、TypeScript 或兩者並用。新案、既有案與後續政策更新都經 Copier 形成可審查差異。

目前公版：v0.1.0 <!-- x-release-please-version -->

[開啟內部網站與完整決策說明](docs/index.html)（內部限閱，請勿公開分享此連結；`noindex`／`robots.txt` 只是臨時防護，不是存取控制，詳見網站內「存取控制決策」章節與 [Issue #79](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/79)）

## 專案概述

本 repo 維護 Copier 模板、共用 CI、安全檢查與 GitHub 設定草案。`template/` 是下發內容；根目錄則讓公版本身使用同一套規則。

目前可用：CI/CD-only、Python-only、TypeScript-only、混合四種 profile，以及 Issue／spec、PR checks、驗證、打包、checksum、SBOM 與 release-please 自動升版。GitHub 設定腳本會先辨識方案與實際 API 能力。

## 快速開始

共同需求是 Git、GitHub CLI、uv；TypeScript／混合案另需 Node 24+ 與 pnpm 11。Windows 請在 WSL2 執行。

```bash
uvx --from csarc-repo-cli csarc init ./my-project
uvx --from csarc-repo-cli csarc adopt .
uvx --from csarc-repo-cli csarc update
```

CLI 固定驗證 canonical repository numeric ID、immutable stable Release、release attestation、tag 指向與 commit signature，再把 GitHub Release 解析成完整 commit SHA 並顯示計畫；任何不一致都會在 Copier 寫檔前停止。互動模式等使用者確認，CI 或 agent 則要同時明確給 `--yes --non-interactive`。範本來源目前是 private repo，需先以 `gh auth login` 登入；第一個 CLI package 尚未發布前的開發用法見下方 troubleshooting。

## 技術與目錄

| 路徑 | 用途 |
| --- | --- |
| `copier.yml`、`template/` | 問題、下發檔案與建立後任務 |
| `profiles/catalog.yaml` | 已支援語言與版本政策 |
| `.github/`、`policies/` | 公版本身的 CI 與 GitHub 設定 |
| `scripts/verify-template.sh` | 建立、更新、語言與供應鏈回歸 |
| `src/csarc_cli/` | `csarc init`／`adopt`／`update` 的薄層 Copier orchestration |
| `docs/index.html` | 內部網站與完整設計說明；內部限閱，目前只有 `noindex`／`robots.txt` 臨時防護，尚無實際存取控制 |

Python 目前以 3.14、uv、Ruff、mypy、pytest 與 src layout 為基線；TypeScript 以 Node 24、pnpm 11、Biome、strict TypeScript 與 Vitest 為基線。

## 開發與驗證

交付模型是「可選 Story Milestone → 1..N Issues → 各自 PR」。Milestone 只代表可端到端驗收的成果，不是每張 Issue 的必填分類；SDD、一般規劃、使用者 story 或導入盤點都可能成為來源。description 使用 [`docs/milestone-description.md`](docs/milestone-description.md) 的 Problem、Outcome、Acceptance criteria、Out of scope、Verification 與 Source 結構；PR 不重複掛入 Milestone。最後一張 open Issue 關閉時 workflow 會重新讀取遠端狀態後關閉 Milestone，Issue reopen 或 open Issue 掛入已關閉 Milestone時則重開。

1. 簡單工作先開「開發工作」Issue；標題以 12–80 個英文 ASCII 字元及至少三個詞直接描述成果，例如 `Add dependency policy checks`。Issue 不使用 PR 的 Conventional Commit 格式。
2. 開單者會自動成為負責人，並選一個分類：`bug`、`enhancement`、`documentation` 或 `duplicate`。前三者在 organization 啟用原生 Issue Types 時分別同步成 `Bug`、`Feature`、`Task`；不支援時仍以 label 正常運作。`duplicate` 是結案處置，不是假造的新 Issue Type。
3. 從 `main` 或最終 PR 回 `main` 的未合併工作分支建立 `type/<issue-number>-short-slug`；一張 Issue 與 PR 只交付一個結果，若新增需求超出完成條件就另開 Issue 與分支。若後來確認重複，連結 canonical Issue 並用 GitHub 的 Duplicate 原生原因關閉；純 triage 不改檔案，可不開分支與 PR。
4. 公版執行 `./scripts/verify-template.sh`；生成專案執行 `./scripts/verify`。
5. PR 指向 `main` 或 stack 中的直接上游分支；整條 open PR 鏈必須最終回到 `main`。內文寫 `Closes #<issue-number>`、完成精簡清單，風險或回退放在選填補充；PR 沒有原生 Issue Type／Issue Form，只使用 Markdown template，並恰選一個 change label：`fix`→`bug`、`docs`→`documentation`，其餘允許的 Conventional Commit type→`enhancement`。
6. CI 與人工審查都通過才合併；AI 不得自行合併。

多個可寫 agents 平行執行時，一項任務使用一個 branch 與一個獨立 worktree，且只平行處理範圍互不依賴的工作；開始前先辨識目前是否已在 agent 平台管理的 worktree，不強制讓同一 branch 出現在多個 worktrees，也不自行刪除其他工具建立或含未提交變更的 worktree。原生 [`git worktree`](https://git-scm.com/docs/git-worktree) 是可攜基線；[Worktrunk](https://github.com/max-sixty/worktrunk) 可選擇簡化建立、切換與清理，但屬於本機／agent orchestration 輔助工具，不是本模板或生成 repo 的必要相依。worktree 只隔離工作目錄，整合仍以 PR、CI、人工審查及合併後完整驗證為準。

本 repo 沒有共用測試環境，因此採 main-only。生成專案只有在確實有長期 dev 測試環境時，才改選 `dev` 模式。
驗證入口也會執行 Issue／PR 政策正反例；標題不合格的 Issue 會讓連結它的 PR 無法通過，公版另注入不合法的 Python／TypeScript 內容，確認語言門禁真的會拒絕。

`./scripts/scan-secrets` 會在已有 commit 時掃描完整可達 Git 歷史，並一律另掃目前工作樹，因此已刪除與尚未提交的機密都不會靜默略過；尚未 `git init` 的新專案仍可安全掃描工作樹。大型 repo 若已明確接受縮小歷史範圍，可傳入例如 `--log-opts='--since=2026-01-01'`，預設仍掃完整歷史。

`AGENTS.md` 是 AI 工作契約；工具細節以可執行設定為準，不在 README 重複。

## 設定與密鑰

- **依方案套用設定：**GitHub 從模板建立 repo 或 Copier 導入只會複製檔案，不會複製 repository settings。推送遠端後先執行 `./scripts/apply-repository-settings.sh plan`，確認後執行 `apply`，最後以 `check` 唯讀驗證；尚未設定 Git remote 時，明確指定 `GH_REPO=owner/repo`。`apply` 也會允許 Actions 建立 release-please PR；workflow 預設權限仍為唯讀，只有 release job 取得 `pull-requests: write`。標籤預設採 additive 更新並保留自訂項目；只有明確傳入 `--prune-labels` 才會刪除政策外標籤。
- **GitHub App 只給 Python 自動升版用：**release-please 使用 Actions 內建 `GITHUB_TOKEN`，不需要另外設定；`python-version-policy.yml` 的排程升版 PR 仍需要 `CSARC_VERSION_BOT_CLIENT_ID` 與 private key，未提供時該 job 會略過。
- **每日排程偵測治理漂移：**`apply-repository-settings.sh check` 原本只在 PR／push 觸發的 CI 裡執行，是一次性快照；`.github/workflows/governance-drift.yml`（daily cron，另可手動 `workflow_dispatch`）在 CI 之外每天重跑同一個 `check`，縮短只靠程式碼變更觸發檢查的盲區，並抓出排程執行時仍存在的偏離。偵測到偏離就由 `scripts/check-governance-drift` 自動開立或更新一張 `Repository governance drift detected` Issue，內容附上實際擷取到的差異；沒有偏離則不會建立或更新任何 Issue。若設定在兩次快照之間遭變更後又恢復，這個排程無法回溯偵測，仍需 GitHub audit log 或組織層事件監控。下發專案可在 Copier 問答啟用 `enable_governance_drift_check`（預設關閉）選配同一檢查。
- **來源證明依可見度決定預設值：**Copier 問答新增 `project_visibility`（public／private／internal）；建立非 CI-only 專案且選擇 public 時，`enable_release_attestations` 預設開啟，自動產生 `actions/attest` provenance／SBOM attestation，`publish-evidence` job 也會拿到對應的 `id-token: write`／`attestations: write`——呼應 GitHub 在 2025–2026 年把公開 repo 的 build attestation 逐步轉為預設行為的方向。private／internal 維持現行明確 opt-in、預設關閉，改用 GitHub Release 上的 SHA-256 驗證；此預設值只在 Copier 建檔當下生效，不會回頭偵測或變更既有 repo 在 GitHub 上的實際可見度，PyPI／npm Trusted Publishing 也不受影響、仍為明確 opt-in。
- **SAST 依方案啟用：**有 Python／TypeScript 的 public repo 預設產生最小 CodeQL workflow；private／internal repo 只有在已授權 GitHub Code Security 時才明確開啟 `enable_codeql`，否則 SAST 保持未涵蓋並由專案選用核准的替代工具。Ruff／TypeScript 負責 lint 與型別，OSV 負責已知相依漏洞，都不視為 SAST。CodeQL 只分析所選 profile 的語言，結果仍可能有誤報與漏報，需人工 triage。
- **Fleet 治理先看觸發門檻：**目前盤點為 0 個已導入的 consuming repo，因此維持 Copier／JSON policy／GitHub API／排程漂移檢查；只有服務與 owner 查找反覆失敗時才評估 Backstage，同類政策漂移跨 repo 重複或 Copier 更新長期逾期時才評估 Allstar／Safe Settings。實際盤點、數值門檻與季度重評方式記錄在文件網站的 `Fleet 治理門檻`。
- Actions 憑證放 GitHub Secrets／Variables；本機 runtime 才使用未提交的 `.env`。不要把 token、私鑰或實際密碼寫進 repo。
- **內部網站存取控制現況：**`docs/index.html` 目前沒有登入或其他實際存取限制，只有 `noindex`／`docs/robots.txt` 臨時防護；已評估 Cloudflare Pages＋Access（候選，需另建 Cloudflare 帳號）、GitHub Pages＋IP 限制（需先升級 Enterprise Cloud）、內部登入平台（未來，服務變多才評估）三種方案，任一方案都需要組織 owner 另行建立並持有帳號權限，本 repo 不會自行申請或設定。詳見 `docs/index.html`「存取控制決策」章節與 [Issue #79](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/79)。

| GitHub 方案與可見性 | `apply` 結果 | `check`／PR／CI/CD 行為 |
| --- | --- | --- |
| Free＋public | 透過 REST 套用並啟用 Ruleset | 驗證 `main` 的有效規則；缺少或不符即失敗 |
| Free organization＋private | 套用基本設定，並把期望 Ruleset 保留在 `policies/rulesets.json`；公開 API 無法建立 Ruleset | 標示 `DEGRADED` 並讓 CI／release 繼續；PR 由 governance workflow 留下或更新警告留言。紅燈仍不能阻止直接 push 或手動合併 |
| Pro 個人帳號＋private | 套用並啟用 Ruleset | 與 Free public 相同 |
| Team／Enterprise organization＋private | 確認 CODEOWNERS team 後套用並啟用 Ruleset | 必要審查、CODEOWNER 與 status checks 成為 merge gate；不符政策時 fail-closed |

`policies/rulesets.json` 是所有方案共用的期望狀態。Free organization private repo 的設定頁雖提供 Ruleset 編輯器，但 GitHub REST 與 GraphQL 對建立／更新（包含 `disabled`）都回覆需升級或公開；因此 `gh` 無法自動預存。管理員可選擇在 Web UI 人工建立 disabled Ruleset，`check` 會將它顯示為 `STAGED`，但仍只代表已儲存，不代表 `main` 受保護。repo 改成 public 或組織升級後，請重新執行 `plan`／`apply`／`check`，由腳本套用 `active` 政策並驗證 CODEOWNERS team 與有效規則。腳本不會自行變更可見性。

## 發布與維運

公版版本以 `version.txt`、`.release-please-manifest.json` 與 `v*` tag 同步記錄；tag 觸發完整驗證。生成專案則依 profile 產生 wheel、npm tarball 或兩者，將 distributions、`SHA256SUMS`、CycloneDX SBOM 與包含 tag／commit／workflow run 的 metadata 附加至 GitHub Release；CI/CD-only 只有 GitHub Release 的來源封存檔，不假裝有語言成品。下載後可執行 `gh release download <tag>` 與 `shasum -a 256 -c SHA256SUMS`；有啟用 attestation 時再以 `gh attestation verify <artifact> --repo <owner/repo>` 驗證。現在只有持續交付，沒有通用部署流程。

Python 與 TypeScript profile 可分別啟用 PyPI／npm Trusted Publishing，預設都關閉。兩者使用 GitHub environment 與 OIDC 短效憑證，發布 job 才有 `id-token: write`，不讀取長效 registry token。啟用前，package owner 必須在 registry 登記完全相符的 organization／repository、workflow 檔名 `release.yml` 與 environment；PyPI 首次發布可先建立 pending publisher，npm 則需由既有 package owner 在 package Settings 建立 trusted publisher。npm 路徑需要 GitHub-hosted runner、Node 22.14+ 與 npm 11.5.1+，公版使用 Node 24。

整份公版只用一個 SemVer：`fix(scope)` 升 patch、`feat(scope)` 升 minor、`!` 升 major。scope 可標 `ci`、`python`、`typescript` 或 `template`；只要任何已支援 profile 不相容，就視為整份公版的破壞性變更。

release-please 用內建 `GITHUB_TOKEN` 自動開、更新 Release PR；合併後先建立 draft 與 tag，同一 workflow 只在 `release_created` 為真時取得 `actions: write`，並以 tag 明確 dispatch `release-template.yml`。發布 workflow 會先完整驗證、透過 `pypi` environment 的 Trusted Publisher 發布 `csarc-repo-cli`，再附加 wheel、sdist、release-specific prompt 與 provenance，最後才發布並鎖定 immutable GitHub Release；任一步驟失敗都保留 draft。發布後會以 `gh release verify` 重新驗證 attestation。一般 main push 不會重複發版。

## 公版更新

以下三條路徑都使用核准的 GitHub Release。CLI 只接受 `Innoguard-Cyber-Arch/csarc-repo-template`（repository ID `1340899393`），並確認 Release 已發布、非 draft、非 prerelease、immutable、attestation 有效、tag 未在驗證途中移動且 commit signature 有效。通過後才顯示完整 40 字元 commit SHA、固定版本的安裝指南、設定、新增／覆寫／保留／人工合併清單與衝突風險。成功後寫入 `.csarc/provenance.json`；來源或 provenance 漂移一律停止。

### 建立新 repo

```bash
uvx --from csarc-repo-cli csarc init ./my-project
```

### 導入既有 repo

在既有 repo 的工作分支執行；`project_mode=existing` 會保留原有 `pyproject.toml`、`package.json`、產品程式、測試、spec 與網站內容。

```bash
git switch -c chore/<issue-number>-adopt-csarc-template
uvx --from csarc-repo-cli csarc adopt . --dry-run
uvx --from csarc-repo-cli csarc adopt .
```

`adopt` 要求乾淨 Git working tree，以 `pyproject.toml`／`package.json` 建議 profile，並預設保留 manifest、產品程式、測試、spec 與網站內容。有無法 deterministic 合併的檔案時會保留可審查差異並回傳非零，不會無提示全面覆寫。

### 更新已導入的 repo

```bash
git switch -c chore/<issue-number>-update-repo-template
uvx --from csarc-repo-cli csarc update --check --json
uvx --from csarc-repo-cli csarc update
```

`update` 讀取現有 answers、執行 Copier smart update，並對 conflict marker 或 `.rej` fail closed。`update --check --json` 目前已是否最新時回傳 0，有更新時回傳 1，執行或輸入錯誤回傳 2。成功寫檔後 CLI 自動執行 `./scripts/verify` 與 repository settings `plan`；它不會執行 `apply`、push 或開 PR。

### Agent prompt

固定版本的安裝契約是 [`docs/agent-install.md`](docs/agent-install.md)。下列 prompt 只傳遞意圖與信任輸入；安裝邏輯仍由 CLI 執行。`<resolved-full-commit-sha>` 必須由正式 GitHub Release 驗證取得，不能用 `main`、`dev` 或 prompt 自稱的 SHA 代替。

新建：

```text
請在 ./my-project 建立新 repository 並導入 CSARC 公版。
目標路徑：./my-project
來源 repository：https://github.com/Innoguard-Cyber-Arch/csarc-repo-template
核准版本：最新穩定版
核准 commit：<resolved-full-commit-sha>
安裝指南：https://raw.githubusercontent.com/Innoguard-Cyber-Arch/csarc-repo-template/<resolved-full-commit-sha>/docs/agent-install.md
請先用 csarc init --dry-run 從正式 GitHub Release 驗證 repository ID、immutable release、attestation、tag、commit signature 並解析完整 SHA；顯示 SHA 給我確認後，才讀取該 SHA 的安裝指南。摘要新增、覆寫、保留與人工合併檔案並等待確認；不要自行 apply GitHub settings、push 或建立 PR。
```

既有導入：

```text
請在目前工作目錄的既有 repository 導入 CSARC 公版。
目標路徑：.
來源 repository：https://github.com/Innoguard-Cyber-Arch/csarc-repo-template
核准版本：最新穩定版
核准 commit：<resolved-full-commit-sha>
安裝指南：https://raw.githubusercontent.com/Innoguard-Cyber-Arch/csarc-repo-template/<resolved-full-commit-sha>/docs/agent-install.md
請先用 csarc adopt --dry-run 從正式 GitHub Release 驗證 repository ID、immutable release、attestation、tag、commit signature 並解析完整 SHA；顯示 SHA 給我確認後，才讀取該 SHA 的安裝指南。摘要新增、覆寫、保留與人工合併檔案並等待確認；不要自行 apply GitHub settings、push 或建立 PR。
```

更新：

```text
請更新目前已導入 CSARC 的 repository。
目標路徑：.
來源 repository：https://github.com/Innoguard-Cyber-Arch/csarc-repo-template
核准版本：最新穩定版
核准 commit：<resolved-full-commit-sha>
安裝指南：https://raw.githubusercontent.com/Innoguard-Cyber-Arch/csarc-repo-template/<resolved-full-commit-sha>/docs/agent-install.md
請先用 csarc update --dry-run 驗證既有 provenance，並從正式 GitHub Release 驗證 repository ID、immutable release、attestation、tag、commit signature與完整 SHA；顯示 SHA 給我確認後，才讀取該 SHA 的安裝指南。摘要 smart diff 與衝突風險並等待確認；不要自行 apply GitHub settings、push 或建立 PR。
```

### Troubleshooting／進階 Copier

只有本機開發可顯式使用 `--allow-unreleased`；它會顯示高風險警告並把 provenance 標為 `development-unreleased`，不得放進一般 prompt。第一個 `csarc-repo-cli` 尚未發布到核准 registry 時，可從已審查的 commit 執行，不用手動 clone：

```bash
uvx --from 'git+https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git@<full-commit-sha>' csarc --help
```

若要調整進階 Copier 答案，在 CLI 後重複加入 `--data KEY=VALUE`；若要固定特定正式版本，使用 `--to vX.Y.Z --expected-sha <full-commit-sha>`。舊 repo 沒有 provenance 時，先人工核對既有 answers，再以 `update --from-release <tag> --accept-legacy` 明確遷移，CLI 不會默認宣稱舊狀態已驗證。`docs/site-content.js` 是生成專案自行維護的網站內容；Copier 更新版型時不會覆寫它。

### 驗證邊界

本模板 repo 的 CI 執行 `./scripts/verify-template.sh`，用暫存 fixture 驗證上述三條生命週期；這支腳本、root 專用升版／同步工具與 template release workflows 都不會下發。生成 repo 的本機與 CI 唯一入口是 `./scripts/verify`；選用 reusable workflow 時也只會呼叫生成 repo 內的這支腳本。

## 負責人與支援

程式與政策審查者以 `.github/CODEOWNERS` 為準。一般缺陷與可重現問題使用 GitHub Issue；疑似資安事件或敏感資料走組織核准的內部通報管道，不貼到 Issue，詳見 [`SECURITY.md`](SECURITY.md)。
