# Delivery Milestone description

下列內文以繁體中文示範；實際 description 請使用專案團隊慣用的語言。
保留英文 H2 標題，讓人與自動化都能辨識結構。Feature parent Issue 保存 SDD
story；Milestone 只保留足以理解、排程與驗收一次 delivery／release 的內容，
完整設計細節請連回 Feature、spec 或決策紀錄。建立時必須填入真實 due date。

每個 Milestone 另建一張生命週期追蹤 Issue，標題固定為
`Milestone <編號>: <里程碑名稱>`，例如
`Milestone 8: Interactive docs and policy alignment`。冒號後的文字必須與 GitHub
Milestone 名稱完全相同；本文依序掛 `Proposal`／`Completion evidence`／
`Early termination`／`Promotion` 四個 H2 段落，核准、反駁與提前終止等狀態只寫在
Issue 內文與留言。核准一律要求非提案者留言 `/milestone approve`；只有當 GitHub
organization 結構性沒有第二個真人帳號可以核准時，對該 repo 有 `admin` collaborator
權限的提案者才能對自己提出的 tracker 留言 `/milestone admin-approve: <理由>` 自核，
理由必填，且會在 approval 紀錄與 summary 上明確標成「Admin self-approved」，不得與
一般非提案者核准混淆。此判斷查 `GET /repos/{repo}/collaborators/{username}/permission`
而非留言的 `author_association` 欄位——後者的值會受該帳號的 organization membership
公開／私密設定影響，若成員關係設為私密，workflow 自己的 `GITHUB_TOKEN` 可能看不到正確
關係，導致這項檢查不穩定；repo collaborator 權限不受此影響。

底下每一張 work Issue 預設直接繼承 tracker 的核可狀態，不需要額外核可——維持「範圍內
工作零額外成本」的現況特性。只有當一張 work Issue 的 body 包含逐字獨立一行的
`Tracker scope: expanded`（`has_scope_sentinel()`，只認這個逐字 marker、不判斷語意），
才代表提案者自己宣告這張 Issue 已超出 tracker 最初的 Proposal／Acceptance criteria
範圍；此時這張 Issue 本身需要一次獨立的非提案者核可，或同一套 `admin` collaborator
權限自核例外（`scope_decision()`；CLI：`check-scope --repo <repo> --issue <編號>`）。
核可留言語彙（`/milestone approve`／`/milestone admin-approve: <理由>`／
`/milestone object:`／`/milestone resolve:`）與判斷邏輯與 tracker 完全相同，只是核可
對象換成這張 work Issue 自己的留言，而不是 tracker 的留言。

個別 work PR 目前只跑 `scripts/validate-pr-policy` 的結構檢查（acceptance criteria
checkbox 全打勾、`Closes #N` 存在且對應正確），刻意**不**加裝 GitHub 原生 required
review（branch protection／Ruleset review gate），也不延伸 `/milestone` 留言語彙到
個別 work PR。這是盤點後的明確決定，不是遺漏：這個 repo 實質上是單一真人帳號（或由
agent 代為作者）撰寫每一張 work PR，GitHub 平台層級禁止「核准自己開的 PR」；在 tracker
層級要求非提案者核可正是 `#512`／`#518`／`#546`／`#549`／`#550` 一連串 self-lock 事件的
根因，若把同一機制套用在數量遠多於 tracker 的 work PR 上，會把同一個死結複製到每一張
PR，且沒有對應每張 work PR 的例外機制可用。詳見
`docs/adr/milestone-scope-and-closure-reconciliation.md`。

```markdown
## Problem

用一小段話交代這次 delivery 要收斂的問題與為何現在值得處理；先描述問題，
不先指定解法。

## Outcome

說明這次 delivery 完成後可觀察的價值，並連回對應 Feature parent。

## Acceptance criteria

- [ ] 列出 2–5 項 story-level、可獨立驗證的結果，不要抄寫 implementation tasks。

## Plan

1. #<leaf-issue> — 第一個可獨立交付的 Task／Bug 與目的。
2. #<leaf-issue> — 後續工作；只有真實順序限制才另設 native dependency。

## Out of scope

列出看似相關、但不影響本 story 驗收且刻意排除的工作。

## Verification

寫出 maintainer 如何端到端驗證 outcome，而不只列單元測試指令。

## References

- #N — 註明沿用、取代或駁回的既有決策與理由。
- 連結來源 spec、使用者研究或導入盤點；若沒有候選，記錄 bounded search 範圍。
```

只掛入直接推進 acceptance criteria 的 leaf Issues 與其 pull requests；Feature parent
不掛 Milestone，避免 parent、subissue、PR 三重計算。Milestone 必須代表有真實期限
的 delivery／release；沒有排程就不要建立 Milestone，也不要把它當 release label。
關閉最後一張 Issue 前，須勾選所有已驗證的 acceptance items；否則 lifecycle
workflow 會讓未完成的 story 保持開啟。
tracker 的 `Promotion` 段落只能描述合併前可驗證的條件（例如：其餘 Milestone Issue
皆已關閉、review ledger 已 resolved 且經 maintainer 確認、雙語／accessibility／
bundle／完整驗證通過、promotion evidence 已綁定 base／head／candidate tree）；由
merge 觸發的 tracker 關閉與 branch／worktree 清理則記錄在 `## 補充` 的 post-merge
runbook，不得寫成必須在 merge 前勾選的 acceptance item。一張 `promote/m<編號>-<簡稱>`
分支的 PR 以 `Closes #<tracker 編號>` 直接關閉這張 tracker Issue；merge 後 CI 自動把
merge commit 網址回填進 `Completion evidence` 段落。一個 Milestone 只維護一張
tracker Issue，不再另開獨立的 final promotion Issue——這捨棄了同一 Milestone 分多次
checkpoint promotion 的彈性，因為重複樣板成本已判斷高於保留彈性的價值。

把 tracker 收尾為 `completed` 前，`sync_milestone_state.py regenerate-reconciliation
--repo <repo> --milestone <編號>` 會在 tracker body 額外維護第五個 H2 段落
`Reconciliation`。這個段落不在建立 tracker 時要求存在——它只能在第一次執行
regenerate-reconciliation 之後才會出現——而是自動重新產生：逐列列出這個 Milestone
底下每一張非 tracker Issue 目前是否已關閉、其宣告 `Closes #N` 的 PR 是否已合併，標成
`Delivered`／`Closed without a merged PR`／`Pending` 三種狀態之一，是給人核對用的真實
交付清單，不只是「Milestone acceptance criteria checkbox 是否打勾」的形式檢查。段落
開頭嵌入一個內容雜湊 marker；只要 tracker body 其他部分（`Proposal`／`Completion
evidence`／`Early termination`／`Promotion` 任何一段）事後被編輯過，這個雜湊就會對不
上，`closure_decision()` 會回報 `Reconciliation: stale, regenerate before closing`
並拒絕把 Milestone 收尾為 completed，直到重新執行 regenerate-reconciliation 為止；
`not_planned`（提前終止）收尾路徑不受影響，因為那條路徑本來就不宣稱交付完成。

建立前須閱讀相關 open／closed Issues 的內文、comments 與 linked pull requests；
不能只依 titles 或 labels 推翻既有決策。
