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
| `package_name` | `derived-decision` | `text` | 小寫 Python identifier | native manifest；無法唯一推導時才保存一次決定 |
| `project_run_command` | `derived-decision` | `text` | 可執行指令 | native manifest；無法唯一推導時才保存一次決定 |
| `project_slug` | `derived-context` | `text` | repository／distribution 名稱 | repository 名稱或 manifest `name` |
| `project_name` | `one-time-seed` | `text` | 非空字串 | product manifest `name`，沒有時為目錄名 |
| `project_description` | `one-time-seed` | `text` | 非空、非 placeholder | product manifest `description` |
| `project_license` | `one-time-seed` | `choice` | `proprietary`, `MIT`, `Apache-2.0`, `custom` | `LICENSE`；不是 starter 文字時為 product-owned（`custom`）；init 選 `custom` 時不產生 `LICENSE` |
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

`github_project_url` 由 #1080（K2）加入本表；本規格不預先保存未使用的鍵。題數、preset 展開與 transcript 由 #1078（Q3）在 §9 定義，repository detector 與唯一推導規則見 §8（#1072，Q2），payload 由 #1077（P2）定義；它們都只能使用本表的分類。

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


### 9. 設定問卷、工作模式與 approval route（#1078）

`csarc init` 與 `csarc adopt`（`src/csarc_cli/setup_plan.py`）在查詢 Release、呼叫 GitHub 寫入、render 或寫檔之前完成問卷：先用 §8 的 detector 與本表的分類，只有未知、矛盾或沒有唯一來源的使用者意圖才成為問題（TTY）或必填輸入（non-interactive）。明確 `--data` 與偵測到的值不再詢問。`csarc update` 不提問，也不接受 `--preset`。

- **提問條件**：stdin 是 TTY，而且沒有 `--non-interactive` 與 `--json`。只用標準輸入；不合法的回答在同一題重問，不增加題數。阻擋後的確認（approval route、偵測結果被拒）不算題目。
- **Non-interactive**：缺少必填輸入時，在查詢 Release、render 或寫檔前以一行 `csarc: Missing required setup input (...)` 結束，列出每個 `--data KEY=`。必填：init 的 `project_description`、`languages`（可為空字串，表示只有 CI baseline）、`copyright_holder`；adopt 沒有 manifest description 時的 `project_description`、沒有 `LICENSE`（plan 會新建）時的 `copyright_holder`、`ambiguous` 的 `package_name`；public 而沒有偵測到揭露政策管道時的 `security_reporting_channel`（需要 live visibility，所以在唯讀 GitHub 讀取之後、render 之前檢查）。有建議值的題目（授權 `proprietary`、文件語言 `zh-tw`、`governance_mode: managed`、Dockerfile 時的 `container: false`、`team` 的 `copilot_review: allowed`、`release_trigger: main`）採用建議值；adopt 對其中沒有唯一來源的意圖各列一個非 blocking 的 `setting-decision`（SPEC-008 `2.1.0`）。repository 無法解析時 non-interactive 仍需要 `--data repository_url=`；visibility 依 §8 使用 safe default。
- **新專案預設**（#1058 決定 14）：init 由 CLI 採用 `documentation_mode: content-only`、`documentation_languages: zh-tw`；`copier.yml` 的預設只供 raw Copier render。
- **`custom` 授權**（#1058 決定 17）：init 的授權題可選 `custom`，表示產品自行管理授權：不問 `copyright_holder`，CSARC 不產生 `LICENSE`，Python、npm、Cargo manifest 不寫 license 欄位（npm 維持 `private: true`）。`check_license_metadata.py` 只在 provenance 記錄 `project_license: custom` 時接受缺少 `LICENSE`；沒有 provenance 的 raw Copier render 只在沒有任何 manifest 宣告授權時接受。其他授權缺少 `LICENSE` 仍然失敗；之後加入的 `LICENSE` 由產品擁有，不被解讀。
- **空 repository**：init 接受不存在的路徑、空資料夾，或只含 `.git`、沒有 commit 也沒有 tracked 檔的 repository（保留 `.git`）；`csarc status` 對後者回報 `create`。

#### 工作模式（preset）

一題決定工作模式；也可用 `--preset` 指定。preset 只展開成下表的 persistent intent，展開值可被明確 `--data` 逐鍵覆寫並照常保存；preset 名稱不寫入 `.csarc/config.yml` 或 provenance，只出現在 plan 與 adopt 報告的 `setup.work_mode`。non-interactive 採用 `solo-local`。preset 只在 init 與 adopt 展開，update 保留已存值。

| preset | `verification_mode` | `admin_bypass` | `copilot_review` | 另外展開 |
| --- | --- | --- | --- | --- |
| `solo-local`（預設） | `local` | `always` | `allowed` | `lifecycle: []`、`scheduled_checks: []` |
| `solo-hosted` | `hosted` | `always` | `allowed` | — |
| `team` | `hosted` | `off` | 追加一題（建議 `allowed`） | — |
| `custom` | 詢問（建議 `local`） | 詢問（建議 `always`） | 詢問（建議 `allowed`） | — |

#### 題數（以 transcript 測試斷言，`tests/test_setup_questions.py`）

init 的 6 題依序為 `project_description`、`languages`、`project_license`、`copyright_holder`、`documentation_languages`、工作模式。adopt 的 3 題為偵測結果確認（一個畫面，名稱、語言、說明、著作權人等；拒絕時不寫入並提示以 `--data` 修改）、`governance_mode`、工作模式。

| 情境 | 題數 |
| --- | --- |
| init，private、local（`solo-local`），授權不是 `custom` | 6 |
| public | ＋1（`security_reporting_channel`） |
| hosted 且 `csarc-owned` | ＋1（`release_trigger`） |
| `team` | ＋1（`copilot_review`） |
| `custom` | ＋3（`verification_mode`、`admin_bypass`、`copilot_review`） |
| repository 無法解析 | 最多＋2（`repository_url`、`project_visibility`） |
| 授權選 `custom` | －1（略過 `copyright_holder`） |
| adopt | 3；每個無法唯一偵測的值（沒有 manifest description、沒有 `LICENSE`、`ambiguous` package）＋1；public 而揭露政策沒有唯一的私密管道＋1；偵測到 `Dockerfile`＋1（`container`）；工作模式、`release_trigger` 與 repository 的追加題同 init |
| update | 0 |

#### Approval route preflight（#1058 決定 7）

`admin_bypass` 最後解析為 `off`，或為 `beta-only`（stable 工作仍需同儕核准）時，plan 在 render 前讀取 collaborator 清單；`always` 不讀。同儕條件與合併 gate 相同：執行者以外、類型為 `User`、live `role_name` 屬於 `admin`／`maintain` 的帳號（#1058 決定 6；`scripts/pr_lifecycle.py` 的 `MAINTAINER_PERMISSIONS`，parity 測試固定）。結果是讀取當下的觀察，不是「只有一位寫入者」或「必然卡住」的證明：

| 結果 | 條件 | 處理 |
| --- | --- | --- |
| `route-observed` | 至少一個符合同儕條件的帳號 | 通過 |
| `none-observed` | 讀取完整，執行者以外沒有符合條件的帳號 | 阻擋；`--confirm-second-approver` 無效；修復：加入 maintainer 後重新規劃，或 `--data admin_bypass=always` |
| `inconclusive` | repository 尚未在 GitHub、讀取失敗、帳號缺 `role_name`，或 organization 擁有而執行者不是 organization owner | 明確確認前阻擋：TTY 確認，或 `--confirm-second-approver`（記錄 `W03`） |

Copilot 路徑只在 `copilot_review: allowed`、而且 render 的 Ruleset 原生必要核准數為 0（hosted，或 local 而 `admin_bypass` 不是 `off`）時成立；此時 TTY 確認或 `--confirm-copilot-entitlement` 可放行 `none-observed` 與 `inconclusive`（記錄 `W04`）。local＋`off` 或 `copilot_review: off` 帶這個旗標仍然阻擋並寫明原因。`governance_mode: observe` 不改變觸發條件，只給 `W09`。兩個確認旗標只作用於單次 plan，不是設定鍵；adopt 的 `--apply-plan` 重播 plan 內的紀錄，不再詢問。

#### 設定警告（穩定代碼）

WARNING 在 plan 輸出（`Apply this plan?` 之前）與 adopt 報告的 `setup.warnings` 出現，不阻擋。代碼發布後不改；未列出的編號保留。

| code | 條件 |
| --- | --- |
| `W01-admin-bypass-always` | `admin_bypass: always`：沒有第二個人審查，以證據與稽核補償 |
| `W02-local-verification` | `verification_mode: local`：證據是自我聲明 |
| `W03-second-approver-confirmed` | approval route `inconclusive`，使用者確認另有核准者 |
| `W04-copilot-entitlement-confirmed` | 使用者確認 Copilot 授權，Copilot 可能是唯一合併路徑 |
| `W05-copilot-reference-only` | local＋`off`＋`allowed`：原生核准仍必要，Copilot 只供參考 |
| `W06-local-beta-only` | local＋`beta-only`：stable 限制只由 lifecycle 執行 |
| `W07-runner-not-admin` | `admin_bypass` 不是 `off`，執行者的 live `role_name` 不是 `admin` |
| `W08-no-ruleset-plan` | private repository 在 GitHub Free：Ruleset 不強制，合併採 `server_enforcement=none` |
| `W09-governance-observe` | `governance_mode: observe`：不套用 Ruleset，只能人工合併 |
| `W10-coverage-relaxed` | `coverage_mode: diff` 或 `coverage_threshold` 低於 80 |
| `W11-public-proprietary` | public repository 使用 `proprietary` |
| `W12-documentation-scope` | `documentation_mode: off`，或雙語 `documentation_languages` |
| `W13-public-codeql-off` | public、有 CodeQL 支援的語言，明確設 `enable_codeql: false` |
| `W15-local-actions-minutes` | local 而 `scheduled_checks` 不是空的或 `enable_codeql: true` |
| `W20-ui-merge-without-approval` | local＋`beta-only`／`always`：0 個原生必要核准，任何寫入者都能在 UI 合併 |
| `W21-single-writer-unobserved` | private、GitHub Free、`csarc-owned`，讀取沒有觀察到執行者是唯一寫入者（#1058 決定 27） |

#### 不合法組合

在 render 前以一行修復指令結束：new＋`rust`＋`container: true`（`--data container=false`）；`enable_codeql: true` 而沒有 `go`、`python` 或 `typescript`（`--data enable_codeql=false`）；明確 `release_trigger` 而不是 hosted＋`csarc-owned`（移除該 `--data`）；未知的 `--preset`。

## Acceptance criteria

- [x] 本規格封閉列出 persistent intent、one-time seed、live facts、derived context 與 machine metadata，並列出每個退役鍵與承接鍵（#1071 AC1）。
- [x] `.csarc/config.yml` 只保存 intent 與 Copier 必要 metadata；`project_mode`、resolved context 與 digest 寫在 `.csarc/provenance.json`（#1071 AC2）。
- [x] current parser 只接受 schema 2；legacy 設定只由 CLI migration registry 讀取並只寫 schema 2（#1071 AC3）。
- [x] status／update 在寫入前驗證 provenance 與 digest，手改、缺漏、未知 schema 或矛盾時 fail closed（#1071 AC4）。
- [x] conformance 測試讓本規格、`copier.yml`、CLI、root parser 與 generated parser 一致（#1071 AC7）。
- [x] init／adopt 只詢問沒有唯一來源的輸入，preset 只展開成可覆寫的已存意圖，non-interactive 缺值在 render 前失敗，approval route preflight 為三態（#1078，§9）。

## Out of scope

- 依選項縮減的 payload 與預設值調整（#1077）。
- `github_project_url`（#1080）。
- 網站 token 與 CLI hint 的全面清理（#1090）、文件中的過期說法（#1091）。

## Verification

- `python3 scripts/spec_to_issue.py validate`
- `uv run pytest tests/test_settings_spec.py tests/test_repository_facts.py tests/test_setup_questions.py`
- `uv run pytest tests/test_settings_migration.py tests/test_root_config.py tests/test_base_policy.py`

## References

- [SPEC-008 lifecycle report format](SPEC-008-lifecycle-report-format.md)
- [Simplified project configuration ADR](../adr/simplified-project-configuration.md)
- [Issue #1071](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1071)
- [Issue #1072](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1072) — repository detector 與唯一推導
- [Issue #1078](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1078) — 設定問卷、工作模式與 approval route preflight
- [Issue #1058](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1058) — 決定 3、8、14–17、25
- [Issue #900](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/900) — 平面、最少的設定
- [Issue #919](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/919) — 文件模式與語言
