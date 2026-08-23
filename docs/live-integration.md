# GitHub live integration smoke

`./scripts/verify-template.sh` 只代表靜態與合成驗證通過；它不證明 GitHub
repository settings、事件觸發、`GITHUB_TOKEN` 或 reusable workflow 權限在
線上可用。只有 `Live integration smoke` workflow 的成功 run 才算 GitHub
整合驗證通過。

## 執行方式

從 Actions 頁面手動執行 `Live integration smoke`。它沿用本 repo 與既有
`workflow_dispatch`，不建立測試 repo，並平行執行四個 probe：

| 能力 | 線上成功證據 | 副作用 | 失敗優先檢查 |
| --- | --- | --- | --- |
| OSV | `osv.yml` 的手動 run 成功 | 唯讀掃描 | reusable workflow 權限 |
| Release Please | `release-please.yml` 在最新 main 成功 | 同一 commit 已發版時不建立新版 | Actions 建立 PR 設定與 token 權限 |
| Release handoff | `release-template.yml` 對最新 immutable tag 成功 | 已發佈 immutable release 不變更成品 | event/ref、dispatch token 與 attestation 權限 |
| Governance drift | `governance-drift.yml` 在最新 main 成功 | 沒有漂移時不建立或更新 Issue | repository setting 與 issues token 權限 |

每個 probe 會上傳保留 30 天的 `live-<capability>-<run-id>` JSON artifact，
記錄 workflow、ref、child run URL、結論、時間與應檢查的權限層級。失敗時，
先從 artifact 和錯誤 annotation 指定的 setting、token、event/ref 或 reusable
workflow 權限層級開始排查。

這個 root-only workflow 是維護公版本身的 smoke，不會下發到 Copier 生成的
專案。每次會重用最新已發佈且 immutable 的 release；如果找不到符合條件的
release，測試會在 dispatch 前停止，避免把草稿或 prerelease 當成成功證據。
