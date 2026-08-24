# Architecture Decision Records (ADR)

本目錄保存 ADR-compatible decision records：已確認且會持續影響架構、工具、安全、相容性或平台能力的選型。一般操作步驟放在 runbook 或 README；尚未確認的想法留在 Issue，不要先寫成既定事實。ADR 與 SDD 不互相取代：`docs/specs/` 說明「現在必須成立什麼」，本目錄說明「為何這樣選、哪些選項被取代或駁回」。

每份 decision record 至少包含：

- 作為穩定識別的 lowercase kebab-case 檔名
- 狀態與日期
- 問題與已確認限制
- 採用方案與理由
- 評估但未採用的替代方案
- ownership、更新與驗證方式
- 限制、fallback 與重新評估條件
- 對應 Issue／PR

狀態使用 `Proposed`、`Accepted`、`Superseded` 或 `Rejected`。仍有部分已接受內容但存在後續缺口時，保留 `Accepted` 並在本文以 `Unresolved` 標示缺口；不要為了顯示最新狀態而刪除先前理由。每份非範例紀錄至少連回一張 Issue 與一張 PR。

Agent 不得自動保存完整聊天逐字稿。使用者確認 durable constraint 或 trade-off 後，先回查既有 decision records 與 open／closed Issues，再把精簡摘要寫入工作單；只有經 PR 審查的內容才成為本目錄的 canonical decision。

新專案可從這個最小範例開始；請把來源替換成實際 Issue 與完成實作的 PR：

```markdown
# Choose a durable option

- **狀態：**Accepted
- **日期：**2026-08-24
- **來源 Issue：**[Issue #1](https://github.com/owner/repo/issues/1)
- **實作 PR：**[PR #2](https://github.com/owner/repo/pull/2)

## 問題與限制
## 決定
## 評估過的替代方案
## 重新評估條件
```
