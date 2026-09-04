# Template policy manifest ADR

- **狀態：**Accepted
- **日期：**2026-09-04
- **來源 Issue：**[#532](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/532)
- **實作 PR：**[#637](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/637)

## 問題與限制

`scripts/apply-repository-settings.sh` 目前無條件套用並檢查全部五類模板內建政策（repository、releases、Actions、labels、branch Ruleset），沒有一個統一的地方讓導入者宣告「這個模板內建政策我要用、那個我不要用」。既有 `.csarc/config.yml` 已有 `release_ownership`／`release_immutable_releases` 描述發版擁有權，但沒有任何鍵控制 repository、Actions、labels、Ruleset 四類政策是否套用；重新設計這些既有非政策鍵不在本決策範圍內。

## 決定

在 `.csarc/config.yml` 新增四個平面布林鍵，各自對應一份 `policies/*.json`：`policy_repository_settings`（`policies/repository.json`）、`policy_actions_permissions`（`policies/actions.json`）、`policy_labels`（`policies/labels.json`）、`policy_branch_ruleset`（`policies/rulesets.json`）。四鍵預設 `true`，維持新增本功能前「全套用」的行為；`.csarc/config.yml` 缺鍵一律視為開啟，既有 repo 更新後不會悄悄少掉涵蓋範圍。

Immutable Releases（`policies/releases.json`）不重複開一個新鍵，改沿用既有 `release_ownership` 已經計算出的 `release_immutable_releases`：只有 `required`（`csarc-owned`）套用，`product-defined`（`product-owned`）與 `not-required`（`verification-only`）皆視為「不是本模板的決定」而略過，交由既有 release ownership 契約決定。

Schema 選擇平面鍵而非巢狀 `policies:` 區塊，因為 `scripts/csarc_config.py` 的手寫、無依賴 YAML 子集解析器目前只支援平面 scalar／list，且既有 `enable_precommit`／`enable_docker` 等切換鍵已經是同樣的平面、以前綴分組的風格；比照既有風格可以避免擴充解析器的額外風險，同時保留單一 `policy_` 前綴讓後續（例如 Issue #531 的能力檢查層）可以列舉並消費同一組鍵。

`scripts/apply-repository-settings.sh` 的 `plan`／`apply`／`check` 三種模式在每一類政策的既有邏輯前面加一道開關判斷：關閉時印出對應的 `SKIP`／`SKIPPED` 行、不呼叫該政策對應的 GitHub API，也不計入 `check` 的 drift 或 `DEGRADED` 計數；開啟時邏輯與新增本功能前完全相同。CODEOWNERS 驗證與 stale legacy Ruleset 探測維持原有的能力探測邏輯不變，只有訊息輸出依 `policy_branch_ruleset` 分流，避免把「使用者主動關閉」誤植為「平台能力不足」的 `DEGRADED` 語意。

## Ownership 與驗證

`csarc adopt`／`update`／`init` 透過既有 `copier` 呼叫模式（`--defaults`）讀取這四個新問題，行為與既有 `enable_*` 布林鍵一致，不需要額外的 CLI 程式碼；`csarc status` 呼叫的 `scripts/apply-repository-settings.sh check` 自動吃到同一套開關邏輯，`policy-only-update` 狀態偵測不需修改。`tests/test_apply_repository_settings_policy.py` 以假 `gh` 執行真正的 script，涵蓋全部政策關閉、全部政策開啟（Ruleset 除外）與沒有這些鍵的舊設定檔三種組合；`tests/test_root_config.py` 涵蓋新鍵的型別驗證與預設行為。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 巢狀 `policies:` YAML 區塊 | 不採用；`scripts/csarc_config.py` 目前的解析器只支援平面 scalar／list，擴充解析器的風險與範圍超出本 Issue。 |
| 也為 immutable Releases 新增獨立開關鍵 | 不採用；`release_immutable_releases` 已經表達同一件事，重複會製造兩個可能互相矛盾的真相來源，違反「不重新設計既有非政策鍵」的邊界。 |
| 政策關閉時仍照舊呼叫唯讀 GitHub API 只是不套用寫入 | 不採用；使用者明確表示不要某項政策時，連讀取比對都應視為不相關，且能省下不必要的 API 呼叫與 rate limit 消耗。 |

## 重新評估條件

當 Issue #531 的能力檢查層需要在同一組開關上疊加「這個 repo 本身是否具備套用某政策的權限」時，重新檢視是否需要把平面鍵升級為結構化資料；當 `scripts/csarc_config.py` 因其他原因需要支援巢狀映射時，一併重新評估是否改用巢狀 `policies:` 區塊。
