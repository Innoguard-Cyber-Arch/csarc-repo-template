# Simplified project configuration ADR

- **狀態：**Accepted
- **日期：**2026-09-22
- **來源 Issues：**[#900](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/900)、[#919](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/919)、[#926](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/926)
- **實作 PR：**https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/907
- **補充決策：**[#908](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/908)

## 問題與限制

舊設定把使用者意圖、GitHub 方案、即時權限、帳務狀態與可推導資料混在一起。導入者必須理解 `reviewers`、`branch_strategy`、多組 review／verification、四個 `policy_*` 及 release 衍生欄位，卻仍無法回答「要不要網站、Docker、main push 發版或只手動發版」等直接產品問題。

GitHub 方案只能提供能力線索，不能證明 repository visibility、organization policy、token permission、Actions billing、Copilot entitlement 或 Pages 可用性。設定也不能關閉 `title`／`verify`／`review` 等安全門禁。

## 決定

公開設定收斂為平面、只含使用者意圖的最小 schema。精確的鍵、分類、儲存位置與退役對應以 [SPEC-009](../specs/SPEC-009-project-settings.md) 為準（Issue #1071 取代原本列在這裡的範例）：`.csarc/config.yml` 只保存無法安全重建的 persistent intent 與 Copier 必要 metadata；名稱、說明、授權與著作權人是一次性 seed，repository URL 與 visibility 是 live facts，`project_mode` 與 render context 寫在 `.csarc/provenance.json`。設定檔維持無依賴 YAML reader 只需的頂層 scalar／list，不增加巢狀 parser。

- `governance_mode` 只描述 CSARC 管理或觀察政策；live capability 另回報 `allowed`／`blocked`／`unknown`。
- `lifecycle` 只列 `issues`、`milestones` 能力；產生出的 workflow 在 runner 前固定判斷，且保留 #886 owner guard。
- `admin_bypass` 新專案預設 `always`（#1058 決定 1、#1064），可明確選擇 `beta-only` 或 `off`；`copilot_review: allowed` 讓乾淨 exact-head Copilot review 可作為證據。不可用、額度不足、舊 head、有意見或未解 thread 時回到同行核准或設定允許的管理員授權。
- reviewer 從 live repository `maintain`／`admin` 權限 best-effort 選取，不保存靜態名單；`code_owner` 可省略，仍只表示 ownership。
- branch route 由可信 Issue／Milestone metadata 推導，不再另設 `branch_strategy`。
- `release_trigger: main` 在每次 main push 執行既有 Conventional Commit 判定；`manual` 完全不註冊 push trigger，只接受明確 dispatch 或本機入口。兩者共用 major／minor／patch／no-release、materialization、freshness、single-writer 與 immutable evidence。本模板 root 採 `manual`，避免每次主幹更新都建立無效發版 run。
- release workflow、required inputs、reason、settings owner 與 immutable setting 都是衍生或稽核輸出，不再是一般答案。
- `documentation_mode` 是文件能力的唯一控制面，搭配 `documentation_languages`（Issue #1071 合併原本的 `primary_language` 與 `i18n`）；Docker 選配是 `container`。Issue #919 取代原本將 repo-site 放在 `features` 的決定。
- `project_license` 與 `copyright_holder` 是 create／adopt 的一次性 seed，寫入 `LICENSE` 與 package manifest 後以 `LICENSE` 為準；未宣告時採 proprietary，不從 repository identity 推定開源授權。
- `actions_fallback` 已退役（Issue #1071，#1058 決定 3）：quota fallback 入口一律拒絕，Actions 中斷改走 governance-switch 路線，required checks 照常要求。
- `verification_mode: local` 是新專案預設值：沿用同一個 risk-owned fast／full router 與 runner，成功後只寫入 Git metadata 的 self-attested evidence；merge lifecycle 重驗 clean worktree、exact head/tree、base、tier、scope、freshness、review 與 remote lease，再走有 trace 的 admin bypass。它不產生 hosted CI、PR policy／writer、review／reviewer assignment、spec sync、work-item lifecycle、Pages 或 release workflow；這些操作改走既有本機 wrapper，平台 UI 的直接變更只由手動或低頻 drift check 發現。`hosted` 才保留 #834／#835 的 trusted Actions、Pages deployment 與可信 release provenance。
- `documentation_mode: template-and-content` 只負責產生可離線使用的 `docs/**`；只有同時選 `verification_mode: hosted` 才產生 Pages workflow 與 enabled policy。Pages 改用 `build_type: workflow`，只在 `docs/**` 變動或手動 dispatch 時部署。

## 遷移

舊設定只由外部 pinned CLI 的 migration registry 唯讀轉換（SPEC-009），成功後只寫 schema 2：全開／全關 `policy_*` 分別成 `managed`／`observe`，混合值要求使用者選擇；`enable_docker` 與 `features: docker` 轉成 `container`；舊 `features: repo-site` 轉成 `documentation_mode: template-and-content`，沒有 repo-site 時轉成 `content-only`；`primary_language`＋`i18n`（或 `readme_primary_language`）轉成 `documentation_languages`；`python_support_mode`＋`python_min_version` 轉成 `python_floor`；兩個排程開關轉成 `scheduled_checks`；舊 `pr_review_mode` 轉成 `copilot_review`（有 level cap 時收窄為 `off`）；已存或明確傳入的 `admin_bypass` 保留，缺值寫成 `always` 並在報告列為 `widened`，附舊 `review`／per-level review 的等價範圍與恢復指令；退役鍵列為 `retired`、承接鍵列為 `exact`，舊 `default_release_level` 轉成 `project_maturity`，verification 收斂為固定下限且路徑風險只能升級。既有發版行為遷移成 `release_trigger: main`。為避免更新時靜默降低既有保護，沒有 `verification_mode` 的 repository 一律遷移為 `hosted`；只有新建專案預設 `local`。舊 reviewer、branch、level cap、per-level 與 release 衍生答案不再持久化。

## 方案與能力邊界

Free／Pro／Team／Enterprise 與 public／private 的組合只影響 Ruleset、Pages 等能力探測；Copilot 與 Actions 帳務必須分別以實際 entitlement／billing 結果判斷。local mode 能驗 lint、型別、單元／整合測試、本機服務、build、package、secret、dependency scan，以及選用 Docker 時的 Compose 設定、image build 與 Trivy scan，但不能證明執行者誠信、GitHub event／權限、第三方服務、實際部署、遠端 runner 或 release provenance；這些邊界不得顯示為通過。repo-site 產物存在不表示 Pages 已發布；Docker feature 也不增加 registry、deployment 或 secret。

## 取代與保留

- 取代 #532 的四個 policy 布林值、#752 的 `pr_review_mode`／level cap、#745 的 per-level review／verification 設定，以及 #742「網站沒有選項」的部分。
- 保留 #369 release ownership、#430 單一版本演算法與 writer、#871 Milestone materialization、#886 runner guard、#554 Docker 能力包、#178／#681 的 portable repo-site 契約。

## Ownership 與驗證

`copier.yml` 與 `.csarc/config.yml` 是公開 desired schema；`scripts/csarc_config.py`、CLI migration、workflow Jinja、repository settings、review／release／lifecycle scripts 消費它。root／template 測試涵蓋遷移、review、trigger、lifecycle、feature 組合與 capability fallback；公共 workflow／Ruleset／release 變更以 full-tier 驗證。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 保存方案名稱或 `copilot_available` | 不採用；方案不等於 entitlement、額度、權限或實際可用性。 |
| 繼續提供每個政策與功能各一個布林值 | 不採用；產生重疊與矛盾狀態。 |
| 增加 schedule 或手選 major／minor／patch | 不採用；沒有需求足以負擔第二套發版演算法。 |
| 以 repository variable 即時切 lifecycle | 不採用；會建立第二份可在 UI 漂移的設定真相。 |

## 重新評估條件

只有出現無法以 scalar／list 表達的真實設定需求，或 GitHub 提供可被可靠探測且跨方案一致的新能力契約時，才重新評估巢狀 schema 或新選項。新選項必須代表使用者決策，不能只是觀測結果。
