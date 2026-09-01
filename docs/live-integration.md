# Historical GitHub live-integration evidence

> [!IMPORTANT]
> `Live integration smoke` 已封存，現行 `.github/workflows/` 沒有這支 Action。
> 本頁記錄 2026-08 的一次性證據，不是目前可執行的操作手冊。

`./scripts/verify-template.sh` 只能證明靜態與合成驗證通過；GitHub repository
settings、事件觸發、`GITHUB_TOKEN` 與 reusable workflow 權限，必須由當時實際存在的
workflow run 證明。歷史 smoke 曾平行探測 OSV、Release Please、release handoff 與
governance drift，並保存 30 天的 machine-readable artifact。

## 現行判斷

| 能力 | 2026-08 證據 | 2026-09-01 狀態 |
| --- | --- | --- |
| OSV | 手動與 main run 曾成功 | `osv.yml` 已恢復；以目前 workflow 與近期 run 判斷 |
| Release Please | 曾驗證組織政策會阻擋 Actions PR | workflow 判定不恢復後已刪除；版本與 CHANGELOG 目前人工處理 |
| Release handoff | 曾對 immutable Release 驗證 | workflow 判定不恢復後已刪除；本機安全契約為 conditional |
| Governance drift | 曾在線上讀取 repository settings | live smoke 已退役並刪除；治理能力由各自 owner 評估 |

完整 disposition 位於 `docs/adr/release-security-and-dependencies.md`；#430 判定不恢復後，
歷史 workflow YAML 已從 archive 移除，Git／Issue／PR 與既有 runs 保存稽核證據。任何能力
要恢復，都必須透過新的 Issue 明列 owner、trigger、最小權限、timeout、concurrency、
成本、失敗復原，以及目前 GitHub 方案上的正向與受控失敗證據；不得把舊 run 當成現行成功。

版本、發版、交付與成品證據的 current-state 契約見
[`adr/release-security-and-dependencies.md`](adr/release-security-and-dependencies.md)。
