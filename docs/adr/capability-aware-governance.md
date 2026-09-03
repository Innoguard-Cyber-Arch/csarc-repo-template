# Capability-aware GitHub governance ADR

- **狀態：**Accepted
- **日期：**2026-08-25
- **來源 Issues：**[#18](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/18), [#28](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/28), [#62](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/62), [#65](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/65), [#87](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/87), [#123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123), [#146](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/146), [#163](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/163), [#199](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/199), [#254](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/254), [#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287), [#300](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/300), [#301](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/301), [#576](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/576)
- **實作 PRs：**[#25](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/25), [#59](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/59), [#63](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/63), [#66](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/66), [#90](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/90), [#128](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/128), [#154](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/154), [#165](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/165), [#306](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/306)

## 問題與限制

GitHub plan、visibility、organization policy、actor role 與 workflow token scope 會讓相同宣告在不同 repo 有不同可用性。403／404 也可能代表缺權限，而不是能力不存在。

## 決定

所有平台相依能力使用 `allowed`、`blocked`、`unknown` 三態。先保存 desired policy，再用 plan／apply／check 或 runtime probe 取得可觀察證據；只有 allowed 才啟用較強自動化。Blocked／unknown 採最安全可攜 fallback，且必須清楚顯示限制。

Free private repository 無法強制 Ruleset 或 team review 時，仍執行 repository-local checks、保留 desired policy 並輪派一位個別 reviewer，但標示 `DEGRADED`，不能宣稱有平台 merge gate。Portable baseline 不要求 PAT、GitHub App 或 organization policy 變更。

Projects 預設關閉；工作階層使用 GitHub 原生 Issue Type、subissue、dependency、Milestone 與 Development link。Issue Type 不可用時才退回 labels，並明示 degraded；不得用自訂 Project 欄位製造第二套狀態來源。

Hosted runner 同樣視為可觀測的平台能力：可用時收集 telemetry，受限或未知時保留誠實狀態與適用的本機驗證。不要求管理員調整帳單、升級方案或維護額外 runner 才能完成 portable 交付。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | 不可辨識的 capability error fail closed | [#18](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/18)／[#25](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/25) |
| Superseded | 缺少付費 Ruleset 時讓所有 CI／release 永久失敗 | [#62](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/62) → [#65](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/65)／[#66](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/66) |
| Preserved | Desired policy 留在 repo，live enforcement 另行驗證 | [#87](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/87)／[#90](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/90) |
| Rejected | 為 portable baseline 要求長效 PAT／額外 App 或繞過組織政策 | [#123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123)／[#128](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/128) |
| Superseded | Hosted Actions 必須由管理員恢復才能完成交付 | [#199](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/199) → [#254](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/254)／[#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287) |
| Preserved | `security_and_analysis` 獨立 PATCH，避免 GHAS 受限時拖累同一請求的基本設定；REST 沒有的 `issue_creation_policy` 改走專屬 GraphQL 區塊，而不是塞進會靜默忽略未知欄位的扁平 PATCH | [#576](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/576) |

## Ownership 與驗證

Repository 保存 desired policies；有管理權的 operator 決定是否 apply。PR code 不取得 administrator token。`apply-repository-settings.sh check` 分項比較可觀察狀態，actionable drift 失敗、結構性限制降級，排程結果不能把 degraded 寫成 aligned。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 只依 GitHub plan 名稱猜能力 | 不採用；organization policy 與 token scope 仍可能阻擋 |
| 所有未知狀態都放行 | 不採用；會把缺權限誤當已啟用 |
| 所有缺能力都永久阻擋 | 不採用；portable baseline 在 Free private 會永遠不可交付 |
| 提前導入 Safe Settings／Allstar | 延後；fleet 規模與漂移頻率尚未達門檻 |

## 重新評估條件

Repository 方案、organization policy、fleet 規模或實測 drift 頻率改變時，重新執行 capability preflight 與 fleet threshold review；不要把安裝時快照當永久真相。
