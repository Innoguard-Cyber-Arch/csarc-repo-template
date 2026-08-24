# CSARC Repo Template

Cyber-Arch 的可更新 repo 公版，支援 CI/CD-only、Python、TypeScript 或兩者並用。新案、既有案與後續政策更新都經 Copier 形成可審查差異。

目前公版：v0.8.2 <!-- x-release-please-version -->

[開啟內部網站與完整決策說明](docs/index.html)（內部限閱，請勿公開分享此連結；`noindex`／`robots.txt` 只是臨時防護，不是存取控制，詳見網站內「存取控制決策」章節與 [Issue #79](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/79)）

## 專案概述

本 repo 維護 Copier 模板、共用 CI、安全檢查與 GitHub 設定草案。`template/` 是下發內容；根目錄則讓公版本身使用同一套規則。

目前可用：CI/CD-only、Python-only、TypeScript-only、混合四種 profile，以及 Issue／spec、PR checks、驗證、打包、checksum、SBOM 與 capability-adaptive 自動升版。GitHub 設定腳本會先辨識方案與實際 API 能力。

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

Python 目前以 3.14、uv、Ruff、mypy、pytest 與 src layout 為基線；CI 會同時驗證精確下界 3.14.0 與最新 3.14.x。生成專案若選 minimum 模式，會驗證所選版本的 `.0` 下界，以及一路到 3.14 的每個 feature release 最新 patch；目前刻意不宣告 3.11 支援。TypeScript 以 Node 24、pnpm 11、Biome、strict TypeScript 與 Vitest 為基線。

## 開發與驗證

交付模型是「可選 Story Milestone → 1..N Issues → 各自 PR」。Milestone 只代表可端到端驗收的成果，不是每張 Issue 的必填分類；SDD、一般規劃、使用者 story 或導入盤點都可能成為來源。建立 Issue／Milestone 前，agent 會以具體關鍵字限量搜尋 open／closed Issues，閱讀候選內文、comments 與 linked PR，先向使用者摘要；若已獲准直接建立，則在補充或 `Related decisions` 記錄每項決策是沿用、取代或駁回及理由。description 使用 [`docs/milestone-description.md`](docs/milestone-description.md) 的完整結構；PR 不重複掛入 Milestone。最後一張 open Issue 關閉且所有 acceptance checkbox 已確認時，workflow 才會關閉 Milestone；Issue reopen、open Issue 掛入或 criterion 取消勾選時則重開。

1. 簡單工作先開「開發工作」Issue；標題以 12–80 個英文 ASCII 字元及至少三個詞直接描述成果，例如 `Add dependency policy checks`。Issue 不使用 PR 的 Conventional Commit 格式。
2. 開單者會自動成為負責人，並選一個分類：`bug`、`enhancement`、`documentation` 或 `duplicate`。前三者在 organization 啟用原生 Issue Types 時分別同步成 `Bug`、`Feature`、`Task`；不支援時仍以 label 正常運作。`duplicate` 是結案處置，不是假造的新 Issue Type。
3. 從 `main` 或最終 PR 回 `main` 的未合併工作分支建立 `type/<issue-number>-short-slug`；一張 Issue 與 PR 只交付一個結果，若新增需求超出完成條件就另開 Issue 與分支。若後來確認重複，連結 canonical Issue 並用 GitHub 的 Duplicate 原生原因關閉；純 triage 不改檔案，可不開分支與 PR。
4. 公版執行 `./scripts/verify-template.sh`；生成專案執行 `./scripts/verify`。
5. PR 指向 `main` 或 stack 中的直接上游分支；整條 open PR 鏈必須最終回到 `main`。使用 `Closes #<issue-number>` 前，PR 與 referenced Issue 不得留有未勾選 task；PR policy 會直接拒絕，避免局部完成卻自動結案。風險或回退放在選填補充；PR 沒有原生 Issue Type／Issue Form，只使用 Markdown template，並恰選一個 change label：`fix`→`bug`、`docs`→`documentation`，其餘允許的 Conventional Commit type→`enhancement`。
6. CI 與人工審查都通過才合併；AI 不得自行合併。

多個可寫 agents 平行執行時，一項任務使用一個 branch 與一個獨立 worktree，且只平行處理範圍互不依賴的工作；開始前先辨識目前是否已在 agent 平台管理的 worktree，不強制讓同一 branch 出現在多個 worktrees，也不自行刪除其他工具建立或含未提交變更的 worktree。原生 [`git worktree`](https://git-scm.com/docs/git-worktree) 是可攜基線；[Worktrunk](https://github.com/max-sixty/worktrunk) 可選擇簡化建立、切換與清理，但屬於本機／agent orchestration 輔助工具，不是本模板或生成 repo 的必要相依。worktree 只隔離工作目錄，整合仍以 PR、CI、人工審查及合併後完整驗證為準。

本 repo 沒有共用測試環境，因此採 main-only。生成專案只有在確實有長期 dev 測試環境時，才改選 `dev` 模式。
驗證入口也會執行 Issue／PR 政策正反例；標題不合格的 Issue 會讓連結它的 PR 無法通過，公版另注入不合法的 Python／TypeScript 內容，確認語言門禁真的會拒絕。

`./scripts/scan-secrets` 會在已有 commit 時掃描完整可達 Git 歷史，並一律另掃目前工作樹，因此已刪除與尚未提交的機密都不會靜默略過；尚未 `git init` 的新專案仍可安全掃描工作樹。大型 repo 若已明確接受縮小歷史範圍，可傳入例如 `--log-opts='--since=2026-01-01'`，預設仍掃完整歷史。

`AGENTS.md` 是 AI 工作契約；工具細節以可執行設定為準，不在 README 重複。

## 設定與密鑰

- **依方案套用設定：**GitHub 從模板建立 repo 或 Copier 導入只會複製檔案，不會複製 repository settings。有管理權且希望啟用較強門禁時，可在推送遠端後執行 `./scripts/apply-repository-settings.sh plan`，確認後執行 `apply`，最後以 `check` 唯讀驗證；這不是 portable release baseline 的必要步驟。尚未設定 Git remote 時，明確指定 `GH_REPO=owner/repo`。`apply` 會嘗試設定 Actions 建立 PR；組織政策回覆 403／409 時保留宣告、明確降級並繼續，其餘未知錯誤仍停止。標籤預設採 additive 更新並保留自訂項目；只有明確傳入 `--prune-labels` 才會刪除政策外標籤。
- **Release 路徑依能力自動選擇：**`csarc init`／`adopt`／`update` 會在 GitHub origin 與 API 可讀時顯示 preflight；每次 release workflow 仍以當下的 `GITHUB_TOKEN` 重測 Actions PR、contents、Release 與 workflow dispatch 能力。四項都確認可用時使用 release-please；PR 被禁止或無法確認但其餘交付能力完整時，direct mode 只接受已由人工 PR 寫入版本與 CHANGELOG 的最新 `main` commit，再建立 tag／draft release 並 dispatch 成品。版本化 commit 尚未存在或其餘交付能力不完整時，只驗證並輸出 `release-capabilities-<run-id>` artifact，不假裝已發版。PR check 只顯示 patch／minor／major／no-release 意圖，確切版本到 main 後才配置。這些路徑都不需要長效 PAT 或額外 GitHub App；`python-version-policy.yml` 的排程升版 PR 仍需要專用 App，未提供時略過。
- **選配整合依目前權限引導：**同一個唯讀 preflight 會辨識 personal／organization owner、目前 actor 的 repo admin 與 organization owner 狀態，並把 Renovate 標成 `available`、`request-owner` 或 `fallback`。`available` 只代表可以開啟 [Renovate App 安裝頁](https://github.com/apps/renovate/installations/new) 並由 GitHub 顯示權限、取得同意；請只選本 repo。organization member 即使有 repo admin，仍因 App 要求 organization members read 與 repository administration read 而顯示 `request-owner`。未知權限、API 失敗或無 admin 一律 `fallback`，繼續使用 Dependabot 與既有 CI/CD；CLI 不會靜默安裝 App，也不要求長效廣域 PAT。新 repo 尚未有 origin 時，先設定 `GH_REPO=owner/repo` 即可在 `csarc init` 階段檢查預定目標。
- **每日排程偵測治理漂移：**`apply-repository-settings.sh check` 原本只在 PR／push 觸發的 CI 裡執行，是一次性快照；`.github/workflows/governance-drift.yml`（daily cron，另可手動 `workflow_dispatch`）在 CI 之外每天重跑同一個 `check`，縮短只靠程式碼變更觸發檢查的盲區，並抓出排程執行時仍存在的偏離。偵測到偏離就由 `scripts/check-governance-drift` 自動開立或更新一張 `Repository governance drift detected` Issue，內容附上實際擷取到的差異；沒有偏離則不會建立或更新任何 Issue。若設定在兩次快照之間遭變更後又恢復，這個排程無法回溯偵測，仍需 GitHub audit log 或組織層事件監控。下發專案可在 Copier 問答啟用 `enable_governance_drift_check`（預設關閉）選配同一檢查。
- **線上整合證據：**`./scripts/verify-template.sh` 只證明靜態與合成驗證；root-only `Live integration smoke` 才會在本 repo 實際 dispatch OSV、Release Please、release handoff 與 governance drift，並為每項能力保存 JSON artifact。`Release consumption verification` 另會下載真正的 CLI wheel，驗證 immutable Release 的簽章、repository identity 與 artifact digest，再確認竄改內容會 fail closed。執行方式與邊界見 [`docs/live-integration.md`](docs/live-integration.md)及 [`docs/artifact-consumption.md`](docs/artifact-consumption.md)。
- **來源證明依可見度決定預設值：**Copier 問答新增 `project_visibility`（public／private／internal）；建立非 CI-only 專案且選擇 public 時，`enable_release_attestations` 預設開啟，自動產生 `actions/attest` provenance／SBOM attestation，`publish-evidence` job 也會拿到對應的 `id-token: write`／`attestations: write`。若同時啟用 PyPI 或 npm 發布，對應 job 會在再發布前以 `gh attestation verify` 強制比對 repository、tag ref、artifact digest 與 signer workflow；產生 attestation 與強制驗證是兩個不同狀態。private／internal 維持明確 opt-in、預設關閉；此預設值只在 Copier 建檔當下生效，不會回頭偵測或變更既有 repo 的可見度。
- **SAST 依方案啟用：**有 Python／TypeScript 的 public repo 預設產生最小 CodeQL workflow；private／internal repo 只有在已授權 GitHub Code Security 時才明確開啟 `enable_codeql`，否則 SAST 保持未涵蓋並由專案選用核准的替代工具。Ruff／TypeScript 負責 lint 與型別，OSV 負責已知相依漏洞，都不視為 SAST。CodeQL 只分析所選 profile 的語言，結果仍可能有誤報與漏報，需人工 triage。
- **Fleet 治理先看觸發門檻：**目前盤點為 1 個已導入的 consuming repo，因此維持 Copier／JSON policy／GitHub API／排程漂移檢查；只有服務與 owner 查找反覆失敗時才評估 Backstage，同類政策漂移跨 repo 重複或 Copier 更新長期逾期時才評估 Allstar／Safe Settings。實際盤點、數值門檻與季度重評方式記錄在文件網站的 `Fleet 治理門檻`。
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

公版的單一版本來源是 root `.release-please-manifest.json`；`version.txt`、`pyproject.toml`、`uv.lock`、README、docs、CHANGELOG、`v*` tag 與發布成品必須一致。`template/.release-please-manifest.json` 與模板內的 package/version 檔則是新生成專案自己的 `0.1.0` 起點，不跟隨公版 release number。tag 觸發完整驗證，且只能指向已包含相同版本與 CHANGELOG 條目的 commit。生成專案依 profile 產生 wheel、npm tarball 或兩者，將 distributions、`SHA256SUMS`、CycloneDX SBOM 與包含 tag／commit／workflow run 的 metadata 附加至 GitHub Release；CI/CD-only 只有 GitHub Release 的來源封存檔，不假裝有語言成品。attestation 產生後，只有 PyPI／npm 再發布路徑會在啟用對應選項時強制驗證；一般下載仍由消費者執行 `gh attestation verify`。現在只有持續交付，沒有通用部署流程。

| 版本範圍 | 單一來源 | 必須同步 | 獨立狀態 |
| --- | --- | --- | --- |
| 公版與 CLI Release | root `.release-please-manifest.json` | root 版本檔、README／docs current marker、CHANGELOG、tag、Release 與成品 | 無 |
| Copier 公版 revision | 已發布 tag＋完整 commit SHA | Release provenance、`.copier-answers.yml` 的 `_commit` | 不另編版本 |
| 生成專案 Release | 生成後的 `.release-please-manifest.json` | 該專案自己的 manifest、package、CHANGELOG、tag 與成品 | 從 `0.1.0` 開始，不跟隨公版版本 |

| Runtime 實測政策 | 模式與行為 | 保證、限制與 fallback |
| --- | --- | --- |
| PR、contents、Release、dispatch 都是 `allowed` | **Release PR：**release-please 維護可審查的版本／changelog PR；合併後建立 release 並明確 dispatch 成品 workflow | 保留最強的人類審查與來源 metadata 同步；任一必要能力漂移就不再選此模式 |
| PR 是 `blocked`／`unknown`，其餘三項都是 `allowed` | **Direct：**只由最新 `main` 配置 tag 與 draft release，再 dispatch 成品 workflow | 最新 commit 必須已由人工 PR 寫入正確版本與 CHANGELOG；否則 fail closed 為 verification-only |
| contents、Release 或 dispatch 任一不是 `allowed` | **Verification only：**保留測試與 machine-readable capability artifact，不建立 tag 或 release | 不會把不確定權限當成功；政策恢復後由後續 main run 重新計算並接續 |

GitHub Release 是所有 profile 的共同基線；registry 則依語言分開選配：純 Python 可開 PyPI、純 TypeScript 可開 npm、混合案可各自開啟、CI/CD-only 兩者皆無，預設全部關閉。本公版 repo 本身只把 Python `csarc-repo-cli` 當成可發布套件，因此根目錄只有選配的 PyPI job；它不代表生成專案固定使用 PyPI。該 job 只有在 repository variable `CSARC_ENABLE_PYPI_PUBLISHING=true` 時才執行，也不會阻擋基線 GitHub Release。PyPI／npm 都使用 GitHub environment 與 OIDC 短效憑證，發布 job 才有 `id-token: write`，不讀取長效 registry token。啟用前，package owner 必須在 registry 登記完全相符的 organization／repository、workflow 檔名 `release.yml`（公版為 `release-template.yml`）與 environment；PyPI 首次發布可先建立 pending publisher，npm 則需由既有 package owner 在 package Settings 建立 trusted publisher。npm 路徑需要 GitHub-hosted runner、Node 22.14+ 與 npm 11.5.1+，公版使用 Node 24。

整份公版只用一個 SemVer：`fix(scope)` 升 patch、`feat(scope)` 升 minor、`!` 升 major。scope 可標 `ci`、`python`、`typescript` 或 `template`；只要任何已支援 profile 不相容，就視為整份公版的破壞性變更。

release workflow 用內建 `GITHUB_TOKEN` 重測能力：支援時由 release-please 自動開、更新 Release PR；目前組織政策禁止 Actions PR 時，由維護者先開版本／CHANGELOG PR，合併後 direct mode 才能在最新 `main` 建立 draft 與 tag。兩種模式都以 tag 明確 dispatch `release-template.yml`。發布 workflow 不會再於 checkout 後暫時改寫版本；它會先驗證 tagged source、CHANGELOG 與 tag 一致，再附加 wheel、sdist、release-specific prompt 與 provenance，最後發布並鎖定 immutable GitHub Release；任一步驟失敗都保留 draft。選配 PyPI Trusted Publishing 在 GitHub Release 成功後獨立執行。發布後會以 `gh release verify` 重新驗證 attestation。一般 main push 不會重複發版。

## 公版更新

真實導入的可重複步驟、驗收證據與已知平台限制整理在 [`docs/pilot-adoption.md`](docs/pilot-adoption.md)。第一個 consuming repo `ai-guardrail` 已完成 v0.2.4 導入與 v0.3.1 更新，因此共用治理與 CI/CD-only composition 為 beta；尚未有真實採用證據的 Python、TypeScript 與混合 composition 維持 alpha。

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
