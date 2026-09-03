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
organization 結構性沒有第二個真人帳號可以核准時，repo owner（`author_association`
為 `OWNER`）才能對自己提出的 tracker 留言 `/milestone admin-approve: <理由>` 自核，
理由必填，且會在 approval 紀錄與 summary 上明確標成「Admin self-approved」，不得與
一般非提案者核准混淆。

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
建立前須閱讀相關 open／closed Issues 的內文、comments 與 linked pull requests；
不能只依 titles 或 labels 推翻既有決策。
