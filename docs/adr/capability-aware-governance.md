# Capability-aware GitHub governance ADR

- **狀態：**Accepted
- **日期：**2026-08-25
- **來源 Issues：**[#18](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/18), [#28](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/28), [#62](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/62), [#65](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/65), [#87](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/87), [#123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123), [#146](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/146), [#163](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/163), [#199](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/199), [#254](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/254), [#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287), [#300](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/300), [#301](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/301), [#576](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/576), [#580](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/580), [#607](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/607)
- **實作 PRs：**[#25](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/25), [#59](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/59), [#63](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/63), [#66](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/66), [#90](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/90), [#128](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/128), [#154](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/154), [#165](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/165), [#306](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/306), [#579](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/579)

## 問題與限制

GitHub plan、visibility、organization policy、actor role 與 workflow token scope 會讓相同宣告在不同 repo 有不同可用性。403／404 也可能代表缺權限，而不是能力不存在。

## 決定

所有平台相依能力使用 `allowed`、`blocked`、`unknown` 三態。先保存 desired policy，再用 plan／apply／check 或 runtime probe 取得可觀察證據；只有 allowed 才啟用較強自動化。Blocked／unknown 採最安全可攜 fallback，且必須清楚顯示限制。

Free private repository 無法強制 Ruleset 或 team review 時，仍執行 repository-local checks、保留 desired policy 並輪派一位個別 reviewer，但標示 `DEGRADED`，不能宣稱有平台 merge gate。Portable baseline 不要求 PAT、GitHub App 或 organization policy 變更。

Projects 預設關閉；工作階層使用 GitHub 原生 Issue Type、subissue、dependency、Milestone 與 Development link。Issue Type 不可用時才退回 labels，並明示 degraded；不得用自訂 Project 欄位製造第二套狀態來源。

Hosted runner 同樣視為可觀測的平台能力：可用時收集 telemetry，受限或未知時保留誠實狀態與適用的本機驗證。不要求管理員調整帳單、升級方案或維護額外 runner 才能完成 portable 交付。

Public 轉換後 Ruleset 的 `require_code_owner_review`／`required_approving_review_count` 第一次真正生效，暴露 `Innoguard-Cyber-Arch` 目前結構性只有一個真人帳號、無法核准自己 PR 的問題（GitHub 全站限制，非本 repo 政策）；`gh pr merge --admin` 對 Ruleset 也不像舊版 classic branch protection 那樣自動取得 admin 身分繞過。2026-09-03 維護者在對話中明確授權，對 live ruleset（id `22178328`）加入 `{"actor_type": "RepositoryRole", "actor_id": 5, "bypass_mode": "pull_request"}`——`actor_id: 5` 經實測確認對應 repository admin 角色（以角色設定，不綁特定帳號）。同日稍後實測發現這個 bypass 涵蓋範圍比原本以為的更廣：`bypass_mode: "pull_request"` 不只放寬 review，也一併放寬 `required_status_checks` 規則本身，等於「alpha 期間 PR 相關規則全部不擋」；不影響 `non_fast_forward`。這個 bypass 已寫回 `policies/rulesets.json`（root）追蹤，具體程序與範圍見 `docs/ci-policy.md`「Alpha 自我核准 bypass」一節；`template/` 的 `bypass_actors` 刻意保留空白，不預設下發給下游生成 repo。是否長期保留、何時移除，由維護者決定，見 #580。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | 不可辨識的 capability error fail closed | [#18](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/18)／[#25](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/25) |
| Superseded | 缺少付費 Ruleset 時讓所有 CI／release 永久失敗 | [#62](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/62) → [#65](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/65)／[#66](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/66) |
| Preserved | Desired policy 留在 repo，live enforcement 另行驗證 | [#87](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/87)／[#90](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/90) |
| Rejected | 為 portable baseline 要求長效 PAT／額外 App 或繞過組織政策 | [#123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123)／[#128](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/128) |
| Superseded | Hosted Actions 必須由管理員恢復才能完成交付 | [#199](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/199) → [#254](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/254)／[#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287) |
| Preserved | `security_and_analysis` 獨立 PATCH，避免 GHAS 受限時拖累同一請求的基本設定；REST 沒有的 `issue_creation_policy` 改走專屬 GraphQL 區塊，而不是塞進會靜默忽略未知欄位的扁平 PATCH | [#576](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/576)／[#579](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/579) |
| Preserved（alpha 限定） | 單一真人帳號 org 撞上 GitHub 平台自我核准限制時，用 Ruleset `bypass_actors`（`RepositoryRole` admin、`bypass_mode: pull_request`）解除，寫回 root `policies/rulesets.json`；`template/` 保留空白，不預設下發 | [#580](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/580) |

## Ownership 與驗證

Repository 保存 desired policies；有管理權的 operator 決定是否 apply。PR code 不取得 administrator token。`apply-repository-settings.sh check` 分項比較可觀察狀態，actionable drift 失敗、結構性限制降級，排程結果不能把 degraded 寫成 aligned。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 只依 GitHub plan 名稱猜能力 | 不採用；organization policy 與 token scope 仍可能阻擋 |
| 所有未知狀態都放行 | 不採用；會把缺權限誤當已啟用 |
| 所有缺能力都永久阻擋 | 不採用；portable baseline 在 Free private 會永遠不可交付 |
| 提前導入 Safe Settings／Allstar | 延後；fleet 規模與漂移頻率尚未達門檻 |

## 2026-09-03 release_phase 收斂 Alpha 自我核准 bypass 範圍（#607）

#580 記錄並落地了目前 live 已套用的 Ruleset self-approval bypass（`RepositoryRole`
admin、`bypass_mode: "pull_request"`，寫回 root `policies/rulesets.json`），同時發現
它的實際涵蓋範圍比原本以為的更廣：因為 GitHub 的 `bypass_actors` 綁在整個 Ruleset
上、不是單一 rule type，這個 bypass 連 `required_status_checks` 都一併放寬，等於
「alpha 期間 PR 相關規則全部不擋」。#607 的問題：這個較寬的涵蓋範圍不能是永久、不分
專案發展階段的事實，尤其是 required_status_checks 這種「必要檢查真的有沒有過」的
保證，不該無限期依賴人工自律。

維護者的決定：把這個 bypass 的權限範圍綁定專案自己的發布階段
（`release_phase`：alpha／beta／release），而不是一個固定不變的設定。`release_phase`
寫在新增的 `policies/project-stage.json`，是人工宣告的單一權威來源（不像
`governance_stage` 或 `profiles/catalog.yaml` 的 `stage` 那樣分類單一 PR 或單一
profile——三者刻意保持不同軸線，避免命名碰撞，完整區分見
`scripts/release_phase_rulesets.py` 的 module docstring）。GitHub Ruleset 的
`bypass_actors` 是 Ruleset 層級欄位，要讓「review 可以 bypass、
required_status_checks 不行」同時成立，落地把兩種規則拆進兩個 Ruleset
（`policies/rulesets.json` 與新增的 `policies/rulesets-required-checks.json`），由
`scripts/apply-repository-settings.sh`（透過 `scripts/release_phase_rulesets.py`）
依 `release_phase` 決定 `required_status_checks` 規則實際生效在哪個 Ruleset：alpha
併入帶 bypass 的那個，beta 起強制留在永遠空 bypass 的那個。release 階段的自動失效是
結構性保證：`scripts/check-bypass-lifecycle`（已接進 `./scripts/verify-fast`）fail
closed 擋下「`release_phase` 是 `release` 但任一 Ruleset 仍有非空 `bypass_actors`」
這個狀態，不依賴人工記得清空。alpha／beta 期間每次實際使用 bypass 合併 PR，也新增
`bypass-trace:` 結構化留言的使用留痕要求，以及 `scripts/check-bypass-trace` 可執行的
查核工具（比對邏輯在 `scripts/check_bypass_trace.py`）。

自動判斷「哪些 PR 真的用了 bypass」（交叉核對 review／required-check 實際狀態）維持
未實作：`scripts/generate_audit_trail.py`（#535／#564）尚未併入 `main`，是獨立進行中
的 Milestone 13 work，#607 刻意不依賴它，改成 operator 針對已識別的單一 PR 主動查核
（跟 `scripts/check-pr-policy-status` 的用法一樣）；一旦該模組併入，可以再擴充做自動
交叉核對。這整套機制與 #580 一樣是 root-only：`template/policies/rulesets.json.jinja`
刻意保留空的 `bypass_actors`，不帶 `policies/project-stage.json` 或第二個 Ruleset
檔；`scripts/apply-repository-settings.sh` 對這兩個新政策檔案的存在與否是條件式
判斷，檔案不存在時（所有既有下游 repo）行為與 #607 之前完全一致。

## 重新評估條件

Repository 方案、organization policy、fleet 規模或實測 drift 頻率改變時，重新執行 capability preflight 與 fleet threshold review；不要把安裝時快照當永久真相。

`Innoguard-Cyber-Arch` 出現第二個真正的 human collaborator 後，重新檢視 Ruleset `bypass_actors` 的 admin self-approval 例外是否仍需保留；這是維護者的治理決定，不由本 ADR 預設方向（見 #580）。
