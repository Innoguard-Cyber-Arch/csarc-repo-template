# Consolidate generated repository infrastructure

- **狀態：**Accepted
- **日期：**2026-09-21
- **來源 Issues：**[#742](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/742)、[#1070](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1070)（2026-10-14 補充 runtime 邊界與固定位置 allowlist）、[#1077](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1077)（2026-10-14 補充依選項 render 的 payload 規則）、[#1129](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1129)（2026-10-15 補充模板 repository 專用工具與精簡後的共用模組）、[#1177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1177)（2026-10-19 補充 hosted 專用 sibling 與 payload 餘裕提醒）、[#1208](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1208)（2026-10-21 補充只在 Milestone 或 hosted render 的 Milestone script）、[#1227](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1227)（2026-10-23 補充生成副本只保留 docstring 摘要行）、[#1230](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1230)（2026-10-23 補充 hosted 專用的 lifecycle 路徑）、[#1231](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1231)（2026-10-23 修訂 payload 度量：總閘加分項預算）、[#1267](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1267)（2026-10-25 補充 hosted 不 render 本機證據工具，並調整 solo agent 文件 token 上限）；Milestone 18 對齊：[#1066](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1066)、[#1067](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1067)、[#1071](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1071)、[#1081](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1081)、[#1146](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1146)、[#1153](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1153)、[#1157](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1157)
- **實作 PR：**[#860](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/860)

## 問題與限制

過去生成專案把 CSARC 腳本、政策、網站引擎與工具設定散落在 root，與產品程式、文件及 manifest 混在一起。使用者難以判斷哪些檔案由產品維護、哪些由公版更新，也容易把不同工具的衍生設定誤認為多份可編輯來源。

GitHub 與掃描工具只會從固定位置讀取部分檔案，例如 `.github/workflows/`、人類通報用的 `.github/SECURITY.md`、scanner guidance 用的 root `SECURITY.md`，以及 root `AGENTS.md`；語言工具也可能要求 root manifest。這些平台或產品檔案不能為了視覺整齊而搬走。

## 決定

生成專案採下列 ownership 邊界：

- `.csarc/config.yml` 是唯一由使用者編輯的 CSARC 設定來源；網站 `[[key]]`、政策開關、語言與交付選項都讀取它。
- `.csarc/scripts/` 是穩定 adapter layer。腳本直接把 `.csarc/config.yml` 轉成工具參數；Gitleaks 只能吃自己的 TOML 格式，因此 `scan-secrets` 只在執行當下於暫存目錄產生設定，結束時刪除。pre-commit adapter 與 `enable_precommit` 已退役（SPEC-009 §3，#1071），`.csarc/scripts/pre-commit` 不再 render。生成專案不提交 Gitleaks、pre-commit 或未使用的 Zizmor 設定。
- `.csarc/policies/*.json` 與 release-please config 是公版管理的唯讀政策／衍生實作資料，不是第二份使用者設定。使用者不得直接修改；變更來源仍是 `.csarc/config.yml` 或公版本身。
- `.csarc/release-please-manifest.json` 是工具必須提交的版本狀態，不是設定來源，因此持久保存。
- 平台固定檔保留在 `.github/`；root `SECURITY.md` 提供 scanner discovery 所需的 repository-wide policy，與 `.github/SECURITY.md` 的人類通報流程分工；root `AGENTS.md` 只作自動探索入口，詳細規則放 `.csarc/docs/agent-workflow.md`，`.claude/CLAUDE.md` 只引用 root 入口。
- 專案文件、ADR、spec 與網站內容屬於產品，保留在 `docs/`。網站來源固定在 `docs/site/`，產物仍是 `docs/index.html` 與 `docs/index.en.html`；renderer 與資產放 `.csarc/site/`。
- 產品程式、測試與語言 manifest 留在慣用 root 路徑，不移入 `.csarc`。
- 公版擁有的 runtime、fixture 與必要測試只放 `.csarc/`；`.csarc/` 以外只允許下方 allowlist 列出的 GitHub、scanner、agent 固定位置、語言工具設定與產品 starter。

## Runtime 與產品工具邊界

- 生成專案的 `.csarc/scripts/verify` 與 `verify-fast` 只驗證產品與自己的設定，不執行也不下發公版自測（`test-*`、`security-smoke` 與 `.csarc/tests/`）。同一批案例由公版 CI 安裝到代表性 render 執行，案例數不得減少；診斷改由 `csarc status` 提供。
- 產品 lint、format、type check、test discovery 與 coverage 不收集 `.csarc/`。`.csarc/.ignore` 讓遵守 ignore 檔的工具（Ruff、ty 等）跳過控制層的 Python 檔，Git 照常追蹤這些檔案；pytest 預設不遞迴進入點開頭的目錄。產品 manifest（`pyproject.toml`、`package.json`、`Cargo.toml`、`go.mod`）不寫 `.csarc`，也不把它列入套件、workspace 或 coverage 來源，所以採用既有專案時不必修改產品 manifest。代價是 ripgrep 這類工具搜尋整個 repository 時也會略過 `.csarc` 的 Python 檔，需要時直接指定檔案路徑。
- `.csarc/scripts` 的模組層 import 只載入入口必定需要的模組，其他 sibling 在命令第一次使用時才載入。合法 render 少了選用模組（例如 `documentation_mode` 不是 `template-and-content` 時的網站模組），其餘入口仍可獨立載入與執行。
- 本機與 hosted 驗證證據使用同一個正規化 record（`evidence_freshness.normalized_record`；`local_verification.py` 保留同名別名，#1267），欄位與驗證規則相同，只保留各自的 trust label：`self-attested-local` 或 `github-hosted`（與合併 evidence payload 同一個標籤）。

## 固定位置 allowlist

fresh render 在 `.csarc/` 以外只能產生下列路徑（`*` 代表專案名稱、套件名稱或檔名）。新增項目必須先修改本 ADR；`tests/test_generated_layout_allowlist.py` 拿模板來源與代表性 render 對照這份清單。

```text
# GitHub fixed locations
.github/CODEOWNERS
.github/ISSUE_TEMPLATE/*.yml
.github/SECURITY.md
.github/dependabot.yml
.github/pull_request_template.md
.github/workflows/*.yml
# Scanner and agent discovery
SECURITY.md
AGENTS.md
.claude/CLAUDE.md
# Language tool settings, manifests, and lockfiles
.gitignore
.node-version
.python-version
Cargo.lock
Cargo.toml
Dockerfile
biome.json
docker-compose.yml
go.mod
package.json
pnpm-lock.yaml
pnpm-workspace.yaml
pyproject.toml
rust-toolchain.toml
tsconfig.build.json
tsconfig.json
uv.lock
vitest.config.ts
# Product-owned starters and documentation
CHANGELOG.md
LICENSE
README.md
README.*.md
cmd/*/main.go
docs/README.md
docs/adr/README.md
docs/index.html
docs/index.*.html
docs/site/content/_index.*.md
docs/site/data/navigation.json
docs/site/theme.css
docs/specs/SPEC-001-example.md
internal/*/*.go
src/*/__init__.py
src/lib.rs
tests/test_smoke.py
typescript/src/index.ts
typescript/tests/index.test.ts
```

## 依選項 render 的 payload（#1077）

每支下發的 script、workflow 與操作文件都必須有一個由已啟用選項帶來的呼叫者：workflow、`verify`／`verify-fast`、其他已 render 的 script、pinned CLI，或 render 後的 agent／操作入口文件（`AGENTS.md`、`.csarc/docs/agent-workflow.md`、`.csarc/docs/csarc.md`）。沒有呼叫者就不 render。`copier.yml` 的 `_exclude` 是唯一的條件來源；`csarc update` 以新舊 render 的差集退役選項不再 render 的 CSARC 檔（只退役與可信舊 render 位元組相同者，改過的檔案仍列為衝突），所以 root CLI 與模板共用同一組規則。

- 公版自測（`test-*`、`security-smoke` 與 `.csarc/tests/`）不下發；來源在模板 repository 的 `tests/generated_self_tests/`，由公版 CI 安裝到代表性 render 執行，案例數不減。
- `verification-only` 與 `product-owned` 不下發 CSARC Release publisher；`csarc-owned` 只有一組 publisher，hosted 時另有 `release.yml`。任何 render 都只有一組 `verify`／`verify-fast`。
- 既有專案採用（`project_mode: existing`）不下發 starter code、product manifest、lockfile、語言工具設定、容器 starter 或產品 test／script；只新增 `.csarc/` runtime 與本 ADR 的平台固定位置。
- `.csarc/docs/ci-policy.md` 與 `.csarc/docs/security-scanner-readiness.md` 是描述整個模板的參考文件：它們不構成呼叫者，可提到其他選項才 render 的 script，但不得提到任何 render 都不存在的 `.csarc/scripts/` 路徑。依專案選項精簡的操作指南由 #1081 取代 `ci-policy.md`。

下表列出 `.csarc/` 與 `.github/` 內依選項 render 的路徑與保留條件；`tests/test_generated_payload.py` 拿它對照 `copier.yml`，並以 render matrix 驗證呼叫者、allowlist、單一 verifier／publisher、existing adopt 與 import。

```text
# path | rendered when
.csarc/docs/documentation-policy.md | documentation_mode != 'off'
.csarc/docs/milestone-description.md | 'milestones' in lifecycle
.csarc/docs/writing-guide.md | 'zh-tw' in documentation_languages
.csarc/scripts/authenticate_dependabot_hosted.py | verification_mode == 'hosted'
.csarc/scripts/build-repo-site | documentation_mode == 'template-and-content'
.csarc/scripts/build_repo_site.py | documentation_mode == 'template-and-content'
.csarc/scripts/check-governance-drift | 'governance-drift' in scheduled_checks
.csarc/scripts/check-release-drift | release_ownership == 'csarc-owned' and verification_mode == 'hosted' and (project_mode == 'new' or csarc_release_workflow | default(false))
.csarc/scripts/check-repo-site-navigation | documentation_mode == 'template-and-content'
.csarc/scripts/check-repo-site-translations | documentation_mode == 'template-and-content'
.csarc/scripts/check-repo-site-versions | documentation_mode == 'template-and-content'
.csarc/scripts/check-scope-gate | verification_mode == 'hosted'
.csarc/scripts/check-template-update | 'template-update' in scheduled_checks
.csarc/scripts/check-trusted-verification | verification_mode == 'hosted'
.csarc/scripts/converge-release-tag | release_ownership == 'csarc-owned'
.csarc/scripts/delivery_sync.py | verification_mode == 'hosted' or 'milestones' in lifecycle
.csarc/scripts/detect-open-milestone | verification_mode == 'hosted'
.csarc/scripts/local_verification.py | verification_mode != 'hosted'
.csarc/scripts/pr_lifecycle_hosted.py | verification_mode == 'hosted'
.csarc/scripts/promotion_gate.py | verification_mode == 'hosted' or 'milestones' in lifecycle
.csarc/scripts/publish-release | release_ownership == 'csarc-owned'
.csarc/scripts/release_bundle.py | release_ownership == 'csarc-owned'
.csarc/scripts/release_candidate.py | release_ownership == 'csarc-owned'
.csarc/scripts/release_writer.py | release_ownership == 'csarc-owned'
.csarc/scripts/render_site.py | documentation_mode == 'template-and-content'
.csarc/scripts/repo_site_blocks.py | documentation_mode == 'template-and-content'
.csarc/scripts/request-reviewer | verification_mode == 'hosted'
.csarc/scripts/self_hosted_evidence.py | verification_mode == 'self-hosted'
.csarc/scripts/spec_to_issue.py | verification_mode == 'hosted' or documentation_mode != 'off'
.csarc/scripts/sync_milestone_state.py | verification_mode == 'hosted' or 'milestones' in lifecycle
.csarc/scripts/sync_milestone_state_hosted.py | verification_mode == 'hosted'
.csarc/scripts/sync_work_item_metadata.py | verification_mode == 'hosted'
.csarc/scripts/validate-issue-policy | verification_mode == 'hosted' and 'issues' in lifecycle
.csarc/scripts/verification_evidence.py | verification_mode == 'hosted'
.csarc/scripts/verify-release-candidate | release_ownership == 'csarc-owned'
.csarc/scripts/verify_release_consumption.py | release_ownership == 'csarc-owned'
.csarc/site | documentation_mode == 'template-and-content'
.csarc/version.txt | not ('python' in languages or 'rust' in languages or 'typescript' in languages)
.github/CODEOWNERS | code_owner
.github/ISSUE_TEMPLATE/milestone-tracker.yml | 'milestones' in lifecycle
.github/workflows/ci.yml | verification_mode == 'hosted'
.github/workflows/codeql.yml | verification_mode == 'hosted' and enable_codeql | default(false)
.github/workflows/csarc-verify.yml | verification_mode == 'self-hosted'
.github/workflows/dependabot-auto-merge.yml | verification_mode == 'hosted'
.github/workflows/dependabot-merge.yml | verification_mode == 'hosted'
.github/workflows/docker-build-scan.yml | verification_mode == 'hosted' and container
.github/workflows/governance-comment.yml | verification_mode == 'hosted'
.github/workflows/governance-drift.yml | 'governance-drift' in scheduled_checks
.github/workflows/osv.yml | verification_mode == 'hosted'
.github/workflows/pages.yml | verification_mode == 'hosted' and documentation_mode == 'template-and-content'
.github/workflows/pr-policy-writes.yml | verification_mode == 'hosted'
.github/workflows/pr-policy.yml | verification_mode == 'hosted'
.github/workflows/pr-review.yml | verification_mode == 'hosted'
.github/workflows/release-drift.yml | release_ownership == 'csarc-owned' and verification_mode == 'hosted' and (project_mode == 'new' or csarc_release_workflow | default(false))
.github/workflows/release.yml | release_ownership == 'csarc-owned' and verification_mode == 'hosted' and (project_mode == 'new' or csarc_release_workflow | default(false))
.github/workflows/spec-to-issue.yml | verification_mode == 'hosted'
.github/workflows/template-update.yml | 'template-update' in scheduled_checks
.github/workflows/work-item-lifecycle.yml | verification_mode == 'hosted' and lifecycle
```

### 模板 repository 專用工具與精簡後的共用模組（#1129）

- 沒有任何生成專案 caller 的工具只留在模板 repository root，不 render：`check-repo-capabilities`、`repo_capabilities.py` 與 `policies/capability-matrix.json`。
- 生成專案的共用模組可以比 root 少：已退役的功能（Actions quota fallback）、只有模板 repository 使用的路由，以及沒有生成專案 caller 的子命令（例如 `promotion_gate.py prepare`／`finalize`／`verify-main`、`delivery_sync.py reconcile`、`release_policy.py` 的 boundary 指令、`verification_cost.py report`）只存在 root。生成副本只能刪除 root 程式碼；保留的每個頂層定義都必須與 root 同名定義一致，例外逐一列在 `tests/test_generated_module_pruning.py` 並附理由。
- 一個 root 模組可以在生成專案拆成依選項 render 的檔案：`release_policy.py` 只保留每個專案的 CLI 都會執行的 capability `preflight`，CSARC 發版指令放在只有 `csarc-owned` render 的 `release_candidate.py`，由 `release_policy.py` 的同一組命令列轉交。
- 只由 hosted workflow 或 hosted PR policy 呼叫的 `check-trusted-verification`、`verification_evidence.py` 與 `detect-open-milestone` 只在 `verification_mode: hosted` render。依分支名稱就會到達的 Milestone 路由（`dev/m*`、`promote/m*`）不依 `lifecycle` 移除，因為 local 與只開 `issues` 的專案仍可能使用它們；local render 的這項例外已由 #1208 取代（見下方）。

### 恢復 payload 餘裕（#1177）

- 共用模組中只有 hosted 會執行的部分拆到只在 `verification_mode: hosted` render 的同名 sibling：`pr_lifecycle_hosted.py`（hosted check run、可信 `verify` evidence 與 hosted Dependabot eligibility 的讀取）、`sync_milestone_state_hosted.py`（PR／merge queue 的 `Milestone approval`、scope 與 standalone Issue approval gate、work-item reconciliation）與 `authenticate_dependabot_hosted.py`（hosted Dependabot workflow 的命令列）。原模組保留同名轉交函式與完整命令列，第一次呼叫時才載入 sibling；local 專案從不呼叫這些函式。`tests/test_generated_module_pruning.py` 逐一列出轉交的名稱。
- 四個 pinned 工具安裝器與 Syft 安裝器合併成一支 `install-tool <tool>`，版本、digest 與 cache 路徑不變。
- 生成專案從不 render `verify-template.sh`，生成副本因此不保留只檢查模板 repository toolchain 的程式碼。
- `scripts/generated_payload.py` 在任一 fixture 距離 `Targets` 剩不到 1 個檔案或 20 KB 時印出 `WARNING`；提醒不改變 `Targets`，也不改變 exit status。

### 只服務 Milestone 的 script（#1208）

- `sync_milestone_state.py`（Milestone 核准、收尾與 reconciliation）、`promotion_gate.py`（Milestone promotion）與 `delivery_sync.py`（delivery branch 與 main 的同步）只在 `'milestones' in lifecycle` 時 render。hosted 的 PR policy、merge queue 與 release workflow 在每個 hosted 專案都會呼叫它們（包括 standalone Issue approval 與 head 必須包含 main 的檢查），所以 `verification_mode: hosted` 一律保留；只有未啟用 Milestone 的 local render 省略這三支。
- 這取代 #1129 對 local render 的例外：未啟用 Milestone 的 local 專案不再支援 `dev/m*`、`promote/m*` 路由。呼叫端把缺少的模組視為未啟用 Milestone：`pr_lifecycle.py` 仍分類 hotfix、release recovery、release follow-up 與 isolated 路由，Milestone delivery 的 routine sync 以清楚訊息失敗；`validate-pr-policy` 拒絕 Milestone promotion 並說明需要 `lifecycle: milestones`；`publish-release` 略過 Milestone 收尾；`gh-issue-edit` 不檢查 approval（沒有任何 local 檢查讀取 Issue approval）。
- 既有專案 update 時，這三支的移除列在 update plan；產品檔案仍在使用的那一支依 #1146 保留為 product-owned。

### hosted 專用的 lifecycle 路徑（#1230）

- 只由 hosted workflow 呼叫的 `pr_lifecycle.py close-work`（work-item lifecycle workflow 在 Milestone work PR 合併後關閉 Issue）與 `actions_run_url`（只讀 hosted Actions check run）移到 `pr_lifecycle_hosted.py`。生成的 `pr_lifecycle.py` 保留 `close_work_issue` 轉交函式與完整命令列；local render 執行 `close-work` 時以 exit 1 失敗並說明需要 `verification_mode: hosted`。沒有新增或停止 render 的檔案，`copier.yml` 與下方 payload 表不變。
- 既有 local 專案 update 時，`pr_lifecycle.py` 的縮減列為一般的模板修改，不會新增 `pr_lifecycle_hosted.py`；hosted 專案兩個檔案一起更新，沒有檔案被移除（`tests/test_hosted_lifecycle_split.py`）。

### hosted 不 render 本機證據工具（#1267）

- `local_verification.py` 只有 local 會執行的部分（記錄、讀取與要求本機證據）留在原檔，只在 `verification_mode != 'hosted'` render。兩種模式共用的正規化 record（`normalized_record`、`TRUST_LOCAL`、`TRUST_HOSTED`、`RECORD_KEYS`、`RECORD_TIERS`）移到每個 render 都有的 `evidence_freshness.py`；`local_verification.py` 保留同名別名，`pr_lifecycle.py` 直接從 `evidence_freshness.py` 讀取。行為與文件文字都不變。
- 這項條件只依 `verification_mode` 判斷，hosted 專案因此少 1 個檔案，canonical 總量與 verification 分項都騰出空間給 Milestone 21 的共用設定（`tests/test_local_verification_render.py`）。

### 生成副本只保留 docstring 摘要行（#1227）

- 沒有與 root 逐位元組配對（`scripts/sync-paired-files.sh`）的生成 Python 副本，函式與類別的 docstring 只保留第一行摘要；完整說明只留在 root 模組一份，不再於每個生成專案重複付出 payload。模組 docstring 會成為 `--help` 說明，維持不變；註解與程式碼不變，因此行為不變，也不改變任何 render 的檔案清單。`tests/test_generated_module_pruning.py` 的 `test_generated_python_keeps_summary_docstrings` 防止多行 docstring 回到生成副本；`test_generated_copy_only_removes_root_code` 本來就忽略 docstring 比對定義。

### Payload 度量：總閘加分項預算（#1231）

#1058 的 `Targets` 以原始總 bytes 當主要預算。2026-10-23 的檢討發現，原始 bytes 對應不到它要保護的成本：85% 是使用者不會修改、update 時整份替換的 `.csarc/scripts`；中文每字 3 bytes；docstring、註解與 `ruff format` 的換行縮排都算進去，所以 #1227 用刪說明換空間，而訊息改寫（#1219–#1221）約七成的增量只是格式化換行。本節改成「一個不放寬的總閘，加上直接對應成本的分項預算」。

**1. 總閘：canonical bytes。** 每個 fixture 量一個總量：`.csarc/scripts` 以外的檔案算原始 bytes；`.csarc/scripts` 內的每支 runtime 算 canonical code bytes：

- Python（副檔名 `.py`，或 shebang 含 `python`）：以 `ast.parse` 解析，移除 module、class 與 function 的 docstring，以 `ast.unparse` 輸出，每行去掉前後空白後計 bytes 加 1 個換行。註解、空行、縮排、格式換行與引號風格都不計。
- 其他 runtime（shell）：非空白、不以 `#` 開頭的行，去掉前後空白後計 bytes 加 1。

canonical bytes 以 lock 的 Python 3.14 計算，因為 `ast.unparse` 的輸出可能隨 Python 版本改變。總閘數字由 #1058 的 bytes `Targets` 換算，不另訂：在換算基準 `cd0b69d`（#1227 合併後、本 Issue 核准時的 `dev/m20-writing-guidelines`），每個 fixture 的新上限＝舊 `Targets` −（原始 bytes − canonical bytes），再向下取整到 1,000 B。換算點的餘裕因此與舊規則相同（只因取整少不到 1,000 B），舊的原始 bytes 數字沒有調高；之後只能下調。原始總 bytes 仍會印出供參考，不再是預算。

| Fixture | 舊 `Targets` bytes | `cd0b69d` 原始 | `cd0b69d` canonical | 新總閘 | 換算點餘裕（舊／新） |
| --- | ---: | ---: | ---: | ---: | ---: |
| solo-default | 1,000,000 | 832,993 | 617,537 | 784,000 | 167,007／166,463 |
| solo-python | 1,010,000 | 836,501 | 621,025 | 794,000 | 173,499／172,975 |
| hosted-csarc-owned-python | 1,200,000 | 1,166,727 | 887,846 | 921,000 | 33,273／33,154 |
| consumer-a | 1,050,000 | 993,740 | 764,616 | 820,000 | 56,260／55,384 |
| consumer-b | 1,050,000 | 984,913 | 756,226 | 821,000 | 65,087／64,774 |

**2. 檔案數上限收緊。** 新上限＝min（舊 `Targets`，本 Issue 實作 head 的實測值＋6）。以實作 base `096987b`（含 #1219、#1220、#1230）實測：solo-default 92、solo-python 95（不變，實測＋6 會超過舊值）、hosted 126（原 137）、consumer-a 112（原 121）、consumer-b 108（原 117）。

**3. 攻擊面預算。** 每個 fixture 的 `.github/workflows` 中，(a) 頂層或任一 job 的 `permissions` 有 `write` 或為 `write-all` 的 workflow 數，(b) 觸發條件含 `pull_request_target` 的 workflow 數，上限等於實測值、沒有緩衝：hosted 10／5、consumer-a 9／5、consumer-b 7／5、solo 0／0。新增一個具寫入權限或 `pull_request_target` 的 workflow 必須修訂本節並由擁有者核准。

**4. Agent 文件 token 預算。** 量 `AGENTS.md` 加 `.csarc/docs/*.md` 的估計 token：中日韓字與全形標點每字 1 token，其餘字元每 4 個 1 token（無條件進位）。上限＝實作 head 實測值×1.05，向上取整到 500：solo-default 13,500、solo-python 13,500、hosted 15,500、consumer-a 15,000、consumer-b 15,000。它取代 #1058 文件預算中 solo `.csarc/docs` 60 KB 與 `agent-workflow.md` 12 KB 兩個 bytes 上限；行數上限（600、300、360、90、90 行）保留。solo-default 與 solo-python 之後經 #1267 調為 14,000：[self-hosted ADR](self-hosted-verification.md) 估計新預設 render 的 agent 文件 token 約 13,100–13,600（以 solo-default 12,829 加三種模式與登記指引的 +300–800），可能超過 13,500；solo-python 在 12,880 加上同樣增量時最多約 13,680。盤點後，條件 render 只剩約 137 token 可省，而且要改寫既有文字，擁有者決定不再精簡文字。擁有者 2026-10-25 依第 8 點「上調要修訂本節並由擁有者核准」核准這次上調；hosted、consumer-a、consumer-b 的 token 上限與其他預算都不變。

**5. Runtime 能力分帳。** `scripts/generated_payload.py` 以封閉對照表把每支 `.csarc/scripts` 歸入一組：PR lifecycle 與 review、release、Milestone 與 Issue、verification、settings 與 drift、Dependabot。沒有歸組的 script 讓測試失敗，新功能因此必須記到某一組。每組上限＝實作 head 上該組在所有 fixture 中最大的 canonical code bytes ×1.03，向上取整到 1,000。以實作 base `096987b`（含 #1219、#1220、#1230）實測：PR lifecycle 257,000、release 166,000、Milestone 與 Issue 130,000、verification 101,000、settings 與 drift 87,000、Dependabot 18,000。PR lifecycle 之後經 #1248 調為 266,000：main 的 #1239（trusted base 以唯讀盤點判讀新設定，「先盤點、再動作」原則的第一個實作）在 `trusted_executor.py` 加入必要的新功能，它是 #1231 定案之後才加入的；第二次 main→delivery 同步（#1247）合併後，這組在 hosted、consumer-a、consumer-b 都是 257,655，超過原上限。新上限依同一算法計算：257,655×1.03＝265,384.65，向上取整到 266,000。擁有者 2026-10-24 核准這次上調；其他組與總閘都不變。只在 `documentation_mode: site` render 的網站引擎另記一組 docs-site；沒有任何 fixture 選這個模式，所以只量測、不設上限。組間不得自行挪用；調整任何一組的上限要修訂本節並由擁有者核准。分組加總可以略高於總閘，總量仍由總閘決定。

**6. 餘裕提醒與底線。** #1177 的提醒保留，改用總閘的單位：任一 fixture 距離總閘不到 1 個檔案或 20,000 B 時印出 `WARNING`，不改變 exit status。Milestone 20 Checkpoint Scripts 的 hosted 至少保留 5,000 B（擁有者 2026-10-23 決定）同樣改用 canonical bytes 判斷。分項預算超過即失敗，沒有提醒區間。

**7. 發版 churn（只提醒）。** `scripts/generated_payload.py churn --since <tag>` 用上一個 stable tag 的 `copier.yml` 與 `template/` 和目前的 working tree，以同一組 fixture 各 render 一次，列出新增、刪除、修改的檔案數與增刪行數。stable 的 `release_policy.py prepare-candidate` 在模板 repository 把結果放進候選報告的 `generated_payload_churn` 欄位；計算失敗只記 `available: false` 與原因，不改變 exit status，也不擋任何發版。量測程式只從執行中的 `release_policy.py` 所在的 `scripts/` 載入，而且只在這個目錄屬於 `--root` 時執行；以可信 base 對另一份 checkout 執行（例如 Dependabot 同步 job）時只記 `available: false`，不載入或 render candidate 的程式。生成專案的 `release_policy.py` 副本不含這段程式。

**8. 與既有決定的關係。** #1227 的 docstring 摘要規則保留，本 Issue 不還原；在新度量下 docstring 與註解不再占預算，是否還原生成副本的完整 docstring 另開 Issue 決定。#1177 的 hosted sibling、#1208 的 Milestone script 規則與 #1129 的精簡規則都保留。每個預算都只能下調；任何上調都要修訂本節並由擁有者核准。

#1058（Milestone 18 tracker）逐項處理如下：

| #1058 項目 | 處理 | 說明 |
| --- | --- | --- |
| `Targets`「Payload 只以檔案數與總大小（bytes）衡量」（2026-10-15） | 部分取代 | 檔案數與總量保留；總量改以 canonical bytes 量測（第 1 點），另加第 3–5 點的分項預算。「腳本支數與行數不是預算」保留：分帳量的是 canonical bytes，不是支數或原始行數 |
| `Targets` 表：檔案數 | 保留並收緊 | 第 2 點 |
| `Targets` 表：bytes | 取代（換算，不調高） | 第 1 點；原始 bytes 數字凍結為換算來源 |
| `Targets`「抵銷」（K1 的 `risk_controls.py`） | 保留 | `risk_controls.py` 記在 PR lifecycle 組 |
| `Targets`「文件」 | 部分取代 | 兩個 bytes 上限改為 token 預算（第 4 點）；行數上限保留 |
| `Targets`「參照」「可達性與命名空間」「import」「自測時間」 | 保留 | 不受影響 |
| Kill criteria 4 | 保留 | Milestone 18 已關閉；「預算不放寬」原則以新單位延續 |
| 決定 10（`server_enforcement=none`） | 保留 | 與度量無關 |
| 決定 11（發版檢查 trailer） | 保留 | 與度量無關 |
| 決定 12（證據期限） | 保留 | 與度量無關 |
| 決定 13（generated verify 不跑模板自測） | 保留 | 自測仍不下發，`自測時間` 仍為 0 |
| 決定 14（solo 優先與 preset 展開） | 保留 | fixture 定義不變 |
| 決定 15（local 不 render `codeql.yml`） | 保留 | 攻擊面基準已反映 |
| 決定 21（`Targets` 核准時固定、預算不放寬） | 保留 | bytes 只換單位、不調高；之後只能下調 |
| 決定 22.1（`Targets` 不放寬，K1 增量由 P1、P2 抵銷） | 保留 | 歷史紀錄，不受影響 |
| 決定 22.5（gate 只下發 `risk_controls.py`，不需要 CLI 也不下載程式） | 保留 | 不改成套件或執行時下載 |

`scripts/generated_payload.py` 量測上述 fixture；`tests/test_generated_payload.py` 斷言每個量測不超過上限，上限只能下降。`.csarc/scripts` 支數、腳本行數與原始總 bytes 仍會量測並印出，但只供參考，不是預算。

## 四種 inventory

| 情境 | root 允許內容 | CSARC／平台內容 | 行為 |
| --- | --- | --- | --- |
| 最小新專案 | README、CHANGELOG、AGENTS、SECURITY、`.gitignore`、`docs/`、空的 `src/` 與忽略的 `dist/` 建置目錄 | `.csarc/`、`.github/`、`.claude/` | 不產生 root `scripts/`、`policies/` 或 `site/` |
| 完整新專案 | 最小集合加語言 manifest、lockfile、`src/`、`tests/`、`typescript/`、Go 的 `go.mod`／`cmd/`／`internal/` 與選用容器檔 | 同上，加選用 workflow | root 白名單由所選語言與功能決定 |
| 既有專案採用 | 原有產品檔、manifest、文件與驗證 hook 全數保留；不新增 starter、manifest、lockfile 或語言工具設定 | 僅新增已核准且無衝突的 CSARC／平台檔 | 同名文字差異需人工合併，特殊檔或目錄碰撞 fail closed |
| 舊版專案更新 | 既有產品檔保持原位 | 已知舊 CSARC 路徑搬到新位置 | plan 明列 add／move／preserve／delete；不同內容的目的檔碰撞時不寫入 |

## 更新搬移規則

`csarc update` 只搬移新模板仍認得的舊 CSARC 檔案：`scripts/`、`policies/`、兩個公版自測、網站引擎／資產、CSARC 操作文件、版本與仍需持久保存的工具狀態。舊 `.gitleaks.toml`、`.pre-commit-config.yaml` 與 `zizmor.yml` 由新 adapter 取代：與可信舊側 render byte-identical、也沒有被使用時 plan 明列 delete；仍被 plan 保留的檔案以路徑引用，或保留的檔案會執行自動讀取它的工具（gitleaks、pre-commit、zizmor）時，改列 `preserve`／`product-owned`（#1146、#1157，SPEC-008）；修改過的舊檔保留為 `retire-modified`（#1066）。`site/content/**` 搬到 `docs/site/content/**` 且保留 consuming repository 的文字。既有專案的 root `SECURITY.md` 視為產品所有，不自動搬移或覆寫；缺少此檔案時可取得公版 scanner baseline。公版建立的新專案則由 Copier 把舊 root disclosure 更新成 scanner policy，並另外建立 `.github/SECURITY.md` 人類通報政策；#742 的一次性 root-to-`.github` move 因 #872 建立新的 root discovery contract 而不再適用。

搬移先在隔離 candidate clone 執行，再由 Copier 更新，完整驗證通過後才寫回目標。新舊位置同時存在而內容相同時只移除舊副本；內容不同時不再整次停止，而是在 plan 列為需要決定的衝突，由 `update --finalize-plan` 對每個衝突取得一個 `keep-current`／`take-new`／`custom:FILE` 決定（#1067）。套用時實際的新增、修改、搬移與刪除集合必須與核准 plan 相同，寫入以 transaction 進行，任一步失敗時 target 回到 byte-identical base（#1066，SPEC-008）。產品自訂 `scripts/*`、`tests/*` 與其他未知檔案一律保留。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 所有檔案都放 `.csarc/` | 不採用；GitHub 固定位置與語言工具慣例會失效 |
| 保留 root `site/` | 不採用；與 `docs/` 重複，網站內容改歸 `docs/site/` |
| 每個工具各自維護一份使用者設定 | 不採用；容易漂移，`.csarc/config.yml` 必須是唯一設定來源 |
| 更新時直接刪除舊 root 目錄 | 不採用；可能刪到產品檔，改採逐檔已知映射與碰撞保護 |

## Ownership 與驗證

公版維護 `.csarc/`、managed workflows 與搬移映射；consuming repository 維護產品程式、manifest、`docs/adr/`、`docs/specs/`、`docs/site/content/` 與 `docs/site/theme.css`。最小與完整生成專案以 root allowlist 測試；舊版更新以搬移／碰撞回歸測試；代表性四語言專案執行完整 verifier。`documentation_mode: off` 與代表性 lifecycle／release ownership render 由生成專案自己的 verifier 驗證；公版自測、import matrix，以及產品工具不收集 `.csarc/` 的負向測試留在公版 CI。

## 重新評估條件

只有平台或 scanner discovery 固定路徑改變、工具無法接受明確 config path，或新的持久狀態不能由 `.csarc/config.yml` 與公版重建時，才重新評估此決定。
