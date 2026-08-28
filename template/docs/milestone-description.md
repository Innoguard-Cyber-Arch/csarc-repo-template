# Delivery Milestone description

下列內文以繁體中文示範；實際 description 請使用專案團隊慣用的語言。
保留英文 H2 標題，讓人與自動化都能辨識結構。Feature parent Issue 保存 SDD
story；Milestone 只保留足以理解、排程與驗收一次 delivery／release 的內容，
完整設計細節請連回 Feature、spec 或決策紀錄。建立時必須填入真實 due date。

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
Promotion Issue 的 checkbox 只能描述合併前可驗證的條件；由 merge 觸發的 Issue／
Milestone 關閉與 branch／worktree 清理由 `## 補充` 的 post-merge runbook 記錄，不得
寫成必須在 merge 前勾選的 acceptance item。若後續工作必須先消費同一 Milestone 的
immutable Release，依 `docs/ci-policy.md` 建立獨立 checkpoint promotion Issue，明列
本次 included work Issues；final promotion Issue 保持無 checkpoint marker。
建立前須閱讀相關 open／closed Issues 的內文、comments 與 linked pull requests；
不能只依 titles 或 labels 推翻既有決策。
