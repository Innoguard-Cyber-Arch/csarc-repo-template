---
id: SPEC-009
title: Persist only settings that cannot be safely reconstructed
owner: @matheme-justyn
priority: P1
estimate: ongoing
status: approved
tracking: none
---

## Problem

v0.30.x 的 `.csarc/config.yml` 同時保存使用者意圖、一次性 seed（名稱、說明、授權、著作權人）、live facts（repository URL、visibility）、可推導的 context（slug、package、run command）、不可變的 `project_mode` 與歷史 alias。CLI、`copier.yml`、`.csarc/scripts/csarc_config.py` 與各個 runtime reader 各自支援一部分 legacy 欄位與預設，結果是 update、render 與 runtime 無法證明讀到同一份設定語意；舊鍵也會被不同 reader 默默補成不同的值。

## Outcome

本規格是 CSARC 專案設定唯一的封閉分類（Issue #1071，#1058 決定 3、14–17）。分類以「能否安全重建、是否影響後續行為」為準；欄位數量是分類的結果，不是目標。

- `.csarc/config.yml`（schema 2）只保存 persistent intent，加上 Copier 必要的 `_src_path`、`_commit` 與格式標記 `schema_version`。
- 一次性 seed 與 derived context 由 native source（product manifest、`LICENSE`、local origin）讀取；live facts 每次觀察；不可變的 `project_mode`、resolved render context 與 digest 寫在 CLI 擁有的 `.csarc/provenance.json`。
- repository 內只有 current-only parser；legacy 設定只由外部 pinned CLI 的 migration registry 唯讀載入，成功後只寫 schema 2。

## Context

### 1. 分類

| 類別 | 定義 | 保存位置 |
| --- | --- | --- |
| `persistent-intent` | 使用者的選擇，影響後續 render、gate 或 runtime，無法從 repository 或平台事實安全重建 | `.csarc/config.yml` |
| `derived-decision` | 可推導的 context；只有 native source 無法唯一推導時，才保存使用者一次明確決定 | 預設不保存；決定時寫在 `.csarc/config.yml` |
| `derived-context` | 由 repository 名稱或 manifest 唯一推導 | 不保存；render context 記在 provenance |
| `one-time-seed` | create／adopt 時的一次性輸入，之後以 native source 為準 | 不保存；render context 記在 provenance |
| `live-fact` | GitHub 或 Git 的即時事實，每次讀取 | 不保存；render context 記在 provenance |
| `machine-metadata` | 格式、模板來源與不可變模式 | `schema_version`、`_src_path`、`_commit` 在 config；`project_mode` 在 provenance |
| `render-derived` | 由其他設定在 render 時算出的模板變數 | 不保存 |
| `retired` | 舊版保存過、schema 2 不再保存的鍵 | 只由 migration registry 讀取 |

### 2. 設定表

`values` 欄是允許值；`kind` 為 `choice`、`multi`、`bool`、`int` 或 `text`。表格由 conformance 測試解析，與 `copier.yml`、CLI（`src/csarc_cli/settings_schema.py`）及 root／generated parser（`csarc_config.py`）逐列比對。

<!-- csarc-settings-table:start -->

| key | class | kind | values | native source / recovery |
| --- | --- | --- | --- | --- |
| `languages` | `persistent-intent` | `multi` | `go`, `python`, `rust`, `typescript` | `csarc update --data languages=...` |
| `python_floor` | `persistent-intent` | `choice` | `latest`, `3.12`, `3.13`, `3.14` | Python 支援意圖，不由 manifest 反推 |
| `documentation_mode` | `persistent-intent` | `choice` | `template-and-content`, `content-only`, `off` | `csarc update --data documentation_mode=...` |
| `documentation_languages` | `persistent-intent` | `choice` | `zh-tw`, `en`, `zh-tw+en`, `en+zh-tw` | 只管 project-owned 文件；第一個是主要語言 |
| `verification_mode` | `persistent-intent` | `choice` | `local`, `hosted` | 放寬只走 governance-switch |
| `admin_bypass` | `persistent-intent` | `choice` | `off`, `beta-only`, `always` | 缺值遷移為 `always`（`widened`） |
| `copilot_review` | `persistent-intent` | `choice` | `allowed`, `off` | review provider 意圖 |
| `governance_mode` | `persistent-intent` | `choice` | `managed`, `observe` | 舊 `policy_*` 遷移 |
| `release_ownership` | `persistent-intent` | `choice` | `csarc-owned`, `product-owned`, `verification-only` | 單一 Release writer（#1068） |
| `release_trigger` | `persistent-intent` | `choice` | `main`, `manual` | 只用於 hosted＋`csarc-owned` |
| `project_maturity` | `persistent-intent` | `choice` | `early`, `formal` | 舊 `default_release_level` 遷移 |
| `code_owner` | `persistent-intent` | `text` | `''`, `@user`, `@organization/team` | 空值不產生 CODEOWNERS |
| `enable_codeql` | `persistent-intent` | `bool` | `true`, `false` | visibility 或 entitlement 改變只列建議，不翻轉 |
| `scheduled_checks` | `persistent-intent` | `multi` | `governance-drift`, `template-update` | 舊兩個排程開關遷移 |
| `lifecycle` | `persistent-intent` | `multi` | `issues`, `milestones` | opt-in／opt-out 保留 |
| `coverage_mode` | `persistent-intent` | `choice` | `global`, `diff` | coverage 政策 |
| `coverage_threshold` | `persistent-intent` | `int` | `1`-`100` | coverage 政策 |
| `security_reporting_channel` | `persistent-intent` | `text` | 非空、非 placeholder | public 必須是 GitHub 以外的私密管道 |
| `container` | `persistent-intent` | `bool` | `true`, `false` | 舊 `features: docker`／`enable_docker` 遷移 |
| `project_verification_hook` | `persistent-intent` | `text` | `''` 或安全的 repository 相對路徑 | 空值停用 |
| `github_project_url` | `persistent-intent` | `text` | `''` 或完整 organization／user ProjectV2 URL | 空值停用；不提問，以 `--data` 設定（§9） |
| `package_name` | `derived-decision` | `text` | 小寫 Python identifier | native manifest；無法唯一推導時才保存一次決定 |
| `project_run_command` | `derived-decision` | `text` | 可執行指令 | native manifest；無法唯一推導時才保存一次決定 |
| `project_slug` | `derived-context` | `text` | repository／distribution 名稱 | repository 名稱或 manifest `name` |
| `project_name` | `one-time-seed` | `text` | 非空字串 | product manifest `name`，沒有時為目錄名 |
| `project_description` | `one-time-seed` | `text` | 非空、非 placeholder | product manifest `description` |
| `project_license` | `one-time-seed` | `choice` | `proprietary`, `MIT`, `Apache-2.0` | `LICENSE`；不是 starter 文字時為 product-owned（`custom`） |
| `copyright_holder` | `one-time-seed` | `text` | 非空字串 | `LICENSE` 的 `Copyright (c)` 行 |
| `repository_url` | `live-fact` | `text` | `https://github.com/<owner>/<repo>` | origin remote 或 GitHub API；明確 override 只綁單次 plan |
| `project_visibility` | `live-fact` | `choice` | `public`, `private`, `internal` | GitHub API |
| `project_mode` | `machine-metadata` | `choice` | `new`, `existing` | 不可變；寫在 provenance |
| `schema_version` | `machine-metadata` | `int` | `2` | 格式標記；current-only reader 用它 fail closed |
| `_src_path` | `machine-metadata` | `text` | 模板來源 | Copier 必要 |
| `_commit` | `machine-metadata` | `text` | 完整 commit SHA | Copier 必要 |
| `documentation_primary_language` | `render-derived` | `text` | `documentation_languages` 的第一個語言 | render 時計算 |
| `documentation_secondary_language` | `render-derived` | `text` | `documentation_languages` 的第二個語言或空字串 | render 時計算 |

<!-- csarc-settings-table:end -->

`github_project_url` 由 #1080（K2）加入本表（§9）；本規格不預先保存未使用的鍵。題數、preset 展開與 transcript 由 #1078（Q3）定義，repository detector 與唯一推導規則見 §8（#1072，Q2），payload 由 #1077（P2）定義；它們都只能使用本表的分類。

### 3. 退役鍵

每個曾被任一 Release 詢問、schema 2 不再保存的鍵都列在這裡，並對應承接的鍵。migration registry 逐鍵產生 SPEC-008 報告列：退役鍵為 `retired`，承接鍵為 `exact`（`source: derived`），沒有等價值時在任何寫入前要求 `--data` 決定（`decision`／`setting-decision`）。治理鍵沿用 #1064 的對應表：`admin_bypass` 缺值為 `always`（`widened`），其他只能是 `unchanged`、`exact` 或 `narrowed`。

<!-- csarc-retired-keys:start -->

| retired key | successor | mapping |
| --- | --- | --- |
| `actions_fallback` | — | quota fallback 退役；Actions 中斷改走 governance-switch 路線 |
| `branch_strategy` | — | branch route 由 Issue／Milestone metadata 推導 |
| `container_mode` | `container` | `none` 以外為 `true` |
| `container_smoke_command` | — | 退役 |
| `containerfile_path` | — | 退役 |
| `copilot_review_max_level` | `copilot_review` | `unlimited` 以外收窄為 `off`（`narrowed`） |
| `default_release_level` | `project_maturity` | `formal` 為 `formal`，其他為 `early` |
| `enable_attestations` | — | 退役 |
| `enable_docker` | `container` | `true` 為 `true` |
| `enable_governance_drift_check` | `scheduled_checks` | 缺值或 `true` 加入 `governance-drift` |
| `enable_npm_publishing` | — | 退役 |
| `enable_precommit` | — | adapter 退役；`.csarc/scripts/pre-commit` 不再 render |
| `enable_pypi_publishing` | — | 退役 |
| `enable_release_attestations` | — | 退役 |
| `enable_template_update_notifications` | `scheduled_checks` | `true` 加入 `template-update` |
| `features` | `container` | 含 `docker` 為 `true`；`repo-site` 決定 `documentation_mode` |
| `i18n` | `documentation_languages` | 與 `primary_language` 合併 |
| `language` | `languages` | `ci` 為 `[]`，其他以 `-` 拆開 |
| `npm_environment` | — | 退役 |
| `policy_actions_permissions` | `governance_mode` | 全開或缺值 `managed`，全關 `observe`，混合要求決定 |
| `policy_branch_ruleset` | `governance_mode` | 同上 |
| `policy_labels` | `governance_mode` | 同上 |
| `policy_repository_settings` | `governance_mode` | 同上 |
| `pr_review_mode` | `copilot_review` | `copilot` 為 `allowed`，其他為 `off` |
| `primary_language` | `documentation_languages` | `zh-tw`＋`en-zh-tw` 為 `zh-tw+en`；`en`＋`en-zh-tw` 為 `en+zh-tw`；`off` 只保留主要語言 |
| `pypi_environment` | — | 退役 |
| `python_min_version` | `python_floor` | 與 `python_support_mode` 合併 |
| `python_support_mode` | `python_floor` | `latest` 為 `latest`；`minimum`＋`X` 為 `X` |
| `readme_primary_language` | `documentation_languages` | 視為 `primary_language`，`i18n` 預設 `en-zh-tw` |
| `release_immutable_releases` | — | Release 衍生觀察，由 `release_ownership` 重新推導 |
| `release_level_alpha_review` | `admin_bypass` | #1064 對應表 |
| `release_level_alpha_verification` | — | verification 收斂為固定下限 |
| `release_level_beta_review` | `admin_bypass` | #1064 對應表 |
| `release_level_beta_verification` | — | verification 收斂為固定下限 |
| `release_level_early_review` | `admin_bypass` | #1064 對應表 |
| `release_level_early_verification` | — | verification 收斂為固定下限 |
| `release_level_formal_review` | `admin_bypass` | #1064 對應表 |
| `release_level_formal_verification` | — | verification 收斂為固定下限 |
| `release_levels_enabled` | — | 退役 |
| `release_ownership_reason` | — | Release 衍生觀察 |
| `release_required_inputs` | — | Release 衍生觀察 |
| `release_settings_owner` | — | Release 衍生觀察 |
| `release_workflow` | — | Release 衍生觀察 |
| `review` | `admin_bypass` | `solo` 等價 `always`，`peer` 等價 `off` |
| `reviewers` | — | 輪派由 live `maintain`／`admin` collaborator 承接 |
| `use_reusable_workflow` | — | 退役 |
| `work_item_mapping_review` | — | 改為 adopt 的一次性輸入，不寫入設定 |
| `workflow_ref` | — | 退役 |

<!-- csarc-retired-keys:end -->

`--data <退役鍵>=…` 在 init、adopt、update 都在任何寫入前拒絕，訊息寫出承接的鍵。

### 4. 儲存契約

- `.csarc/config.yml`：只含本表 `persistent-intent` 的每一個鍵、有明確決定時的 `derived-decision` 鍵、`schema_version: 2`，以及 generated repository 的 `_src_path`、`_commit`。CLI 以單一 canonical writer 寫出（排序、不折行）；raw Copier render 由 answers 模板寫出同一組鍵。
- `.csarc/provenance.json`：CLI 在 init、adopt、update 成功後寫入 `settings` 紀錄：`schema_version: 2`、`project_mode`、`context`（本表 seed、live fact、derived context 與 `project_mode` 的 resolved 值）、`context_sha256`、`config_sha256`（settings 檔位元組）與 `record_sha256`（紀錄本身）。這份紀錄不可手改。
- `csarc status` 與 `csarc update` 在任何 render 或寫入前驗證：未知或格式錯誤的 `schema_version`、settings 檔與 digest 不符、紀錄缺漏、紀錄被手改、context 含未知鍵，或 `project_mode` 缺漏／矛盾時，以穩定的 `CSARC settings error` fail closed，並寫出恢復方式：以 `git checkout -- .csarc/config.yml .csarc/provenance.json` 還原後，只用 `csarc update --data KEY=VALUE` 變更設定。
- update 的舊側：schema 2 target 以已驗證的 provenance context 加上已存 intent 重建，與舊 render 實際消耗的答案相同；legacy target 沿用 #1063 的 asked-key 重建。新側的 seed 沒有 native source 時沿用 provenance context。

### 5. Reader 邊界

- Repository runtime（`csarc_config.py`，root 與 generated 逐位元組相同）只接受 schema 2：沒有 `schema_version` 的 legacy 檔、未知 schema、退役或未知鍵、缺少 intent、不合法的值一律 fail closed，不補預設、不讀 alias。seed 由 `project_facts()`／`license_facts()` 從 manifest、`LICENSE` 與 local origin 讀取，不查 GitHub。
- G2 base reader（`trusted_executor.py read-config`）以同一個 current-only parser 讀 base 與 candidate；它在 trusted base 驗證 candidate 設定之後，writer 才切換到 schema 2（#1058 決定 8）。
- CLI 對宣告了未知 `schema_version` 的檔案，在任何寫入前 fail closed；legacy 檔只交給 migration registry。
- Copier 以 `jinja2.StrictUndefined` render，模板引用已移除的鍵時 render 直接失敗，不會靜默產生空值。

### 6. 非互動與一次性輸入

- non-interactive init／adopt 以 `--data` 傳齊 seed 時不提問（0 題）；seed 只進 render 與 provenance context，不進設定檔。
- `package_name`、`project_run_command` 只有以 `--data` 明確決定時才寫入設定檔（init、update）；adopt 只在 native manifest 有多個候選，或明確值與 manifest 矛盾時保存（§8）；其餘時候是 derived context。
- update 預設 0 題；seed 的修改只能用一次性 `--data`，列為 decision，結果只更新 provenance context。

### 7. Breaking change 與恢復

- 最低 CLI：寫入 schema 2 的第一個 Release（本 Milestone 的 beta.2）。更早的 CLI 不支援 schema 2；本版之後的 CLI 讀到更新的 schema 會在寫入前停止。
- 升級：`csarc update` 以 migration registry 讀舊設定、在報告列出每個 `retired`／`exact` 列，並在同一次寫入改為 schema 2。失敗時 target 不變。
- 既有 repository 的 product manifest、starter 與 lockfile 不被 seed（#1058 決定 25）。
- `actions_fallback` 退役是行為變更：quota fallback 入口一律拒絕，Actions 中斷改走 governance-switch 路線，required checks 不變。

### 8. Repository detector 與唯一推導（#1072）

CLI（`src/csarc_cli/repository_facts.py`）、本 repository（`scripts/repository_facts.py`）與 generated runtime（`.csarc/scripts/repository_facts.py`）執行逐位元組相同的 detector；它只讀不寫，Git 與 GitHub 讀取由呼叫端注入。每個 fact 的 `state` 是封閉詞彙：`known` 帶有此刻觀察到的 `value`；`unknown` 帶 `reason`、沒有值（離線、權限不足、沒有 GitHub origin），不以猜測或上次的結果冒充現況；`ambiguous` 列出 `candidates`，由使用者做一次明確決定。

| fact | 來源 | `unknown` 的典型原因 |
| --- | --- | --- |
| `origin` | target 本身是 Git root 時的 `origin` remote；沒有 origin 時才用 `GH_REPO` | 不是 Git root、origin 不是 GitHub URL；沒有 origin 時其他 remote 一律不猜（多個為 `ambiguous`） |
| `identity` | `GET repos/{owner}/{repo}` 的 `full_name`、`id`、owner | 離線、權限不足、回傳的 `full_name` 與 origin 不符 |
| `visibility`、`default_branch` | 同一次 repository 讀取 | 回傳缺值 |
| `permissions` | 同一次讀取的 `role_name`（#1058 決定 6） | 缺 `role_name` |
| `security` | 同一次讀取的 `security_and_analysis` 狀態 | 需要 admin 權限才看得到 |
| `plan` | organization 用 `GET orgs/{owner}`，個人帳號用 `GET user` | 只有 owner 本人看得到 |

- live facts 不寫入 `.csarc/config.yml`。render 仍需要 visibility 時，CLI 用明確 `--data`、上次 render 記錄的值或 safe default，但 detector 的 fact 維持 `unknown`；runtime 的 `project_facts()` 只在 origin 為 `known` 時給出 repository URL，否則為空字串。
- 唯一推導：`package_name` 在 `src/` 只有一個 package 時取它；有多個時，只有 `pyproject.toml` 的 `[project] name`（正規化為 identifier）選中其中一個才算唯一，否則為 `ambiguous`；沒有 `src/` package 時取正規化的 project name。`project_run_command` 依模板順序（python、typescript、rust、go）組合各語言指令，每個選取的語言都必須有 native manifest（`pyproject.toml`、`package.json`、`Cargo.toml`、`go.mod`），否則為 `unknown`；package 為 `ambiguous` 時它也是 `ambiguous`；沒有語言時為 `./.csarc/scripts/verify`。
- 已保存或明確傳入的 decision 永遠優先。adopt：唯一推導取代 slug 預設；`ambiguous` 在任何寫入前 fail closed，要求 `--data KEY=...`；`unknown` 沿用模板預設。update：唯一推導只補上 provenance 沒有記錄的值；與記錄值矛盾或為 `ambiguous` 時保留記錄值，在報告列 note 與非阻擋的 `setting-decision`，直到傳入一次明確決定；沒有記錄值而 `ambiguous` 時 fail closed；`unknown` 沿用記錄值。
- visibility、entitlement（`security` 顯示 `advanced_security`／`code_security` 未啟用）、模板或 preset 預設改變時，已存的 `enable_codeql`、`scheduled_checks`、`lifecycle`、`coverage_*` 與 `python_floor` 一律維持 `unchanged`；差異只寫在報告列的 note，不產生 required action。
- 身分：update 在任何 render 或寫入前，比較 origin 識別的 repository 與設定／provenance 記錄的 `repository_url`，不一致就 fail closed。一次性 `--data repository_url=...` 只核准這一次 plan，而且仍須指向 origin 識別的 repository；它不是設定鍵，只進 render 與 provenance context。origin 為 `unknown` 時不比較。

### 9. GitHub Project Roadmap（#1080）

`github_project_url` 是唯一的 Project 設定（#1058 決定 23）。它只保存完整的 organization 或 user ProjectV2 URL（`https://github.com/orgs/<org>/projects/<n>` 或 `https://github.com/users/<user>/projects/<n>`），預設空字串；不保存 project、field 或 item ID，也沒有其他 Project 鍵。init／adopt 不提問（題數不變），以 `--data github_project_url=<URL>` 設定，`csarc update --data github_project_url=` 清空。

- 空值：`csarc issue create` 與 `csarc issue sync-project` 完全不呼叫 Project API；repository 的 `has_projects` 維持 `false`，不新增 workflow 或 check。
- 有值：受管入口在任何寫入前即時解析 URL，讀回 owner、project URL、`closed`、`viewerCanUpdate`，以及唯一、型別為 DATE 的 `Project start`／`Project target` 欄位；token 能回報 scopes 時要求 `project`，否則明示 `unknown`。
- `Project start` 是 Issue 建立日的 UTC 日期；`Project target` 是目前 Milestone `due_on` 的 UTC 日期，沒有 due date 時必須明確傳入 `--target-date YYYY-MM-DD`。
- `csarc issue sync-project --issue <N>`／`--milestone <M>` 依目前的 Milestone 冪等同步；空欄直接寫入，既有值不同時先列 diff，經確認（互動確認或 `--yes`）才覆寫。只同步 Issue，不同步 PR。
- Issue 已建立但 Project 寫入失敗時保留 Issue，輸出單一可重跑的修復指令；加入 item 以 Issue 與 Project 的 identity upsert，重跑不產生重複 item。
- 只有經 `csarc issue create` 建立或 `csarc issue sync-project` 明確同步的 Issue 會進 Project；UI、`scripts/gh-issue-create` 或其他工具建立的 Issue 需要時再跑 `sync-project`。

## Acceptance criteria

- [x] 本規格封閉列出 persistent intent、one-time seed、live facts、derived context 與 machine metadata，並列出每個退役鍵與承接鍵（#1071 AC1）。
- [x] `.csarc/config.yml` 只保存 intent 與 Copier 必要 metadata；`project_mode`、resolved context 與 digest 寫在 `.csarc/provenance.json`（#1071 AC2）。
- [x] current parser 只接受 schema 2；legacy 設定只由 CLI migration registry 讀取並只寫 schema 2（#1071 AC3）。
- [x] status／update 在寫入前驗證 provenance 與 digest，手改、缺漏、未知 schema 或矛盾時 fail closed（#1071 AC4）。
- [x] conformance 測試讓本規格、`copier.yml`、CLI、root parser 與 generated parser 一致（#1071 AC7）。
- [x] `github_project_url` 是唯一的 Project 設定，預設空字串，只保存完整 organization／user ProjectV2 URL（#1080 AC1）。

## Out of scope

- 題數、preset 展開、WARNING 與 approval route preflight（#1078）。
- 依選項縮減的 payload 與預設值調整（#1077）。
- 網站 token 與 CLI hint 的全面清理（#1090）、文件中的過期說法（#1091）。

## Verification

- `python3 scripts/spec_to_issue.py validate`
- `uv run pytest tests/test_settings_spec.py tests/test_repository_facts.py`
- `uv run pytest tests/test_settings_migration.py tests/test_root_config.py tests/test_base_policy.py`
- `uv run pytest tests/test_project_roadmap.py`

## References

- [SPEC-008 lifecycle report format](SPEC-008-lifecycle-report-format.md)
- [Simplified project configuration ADR](../adr/simplified-project-configuration.md)
- [Issue #1071](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1071)
- [Issue #1072](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1072) — repository detector 與唯一推導
- [Issue #1080](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1080) — GitHub Project Roadmap 同步
- [Issue #1058](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1058) — 決定 3、8、14–17、23、25
- [Issue #900](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/900) — 平面、最少的設定
- [Issue #919](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/919) — 文件模式與語言
