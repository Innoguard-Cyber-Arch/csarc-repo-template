# Story Milestone description

下列內文以繁體中文示範；實際 description 請使用專案團隊慣用的語言。
保留英文 H2 標題，讓人與自動化都能辨識結構。Milestone 只保留足以理解、
規劃與驗收 story 的內容；完整設計細節請連回 spec、Issue 或決策紀錄。

Milestone title 使用專案慣用語言的 3–80 字元 outcome phrase，不要求英文或
三個單字；不得以 `Milestone`（含全形拉丁等價字）或狀態標記開頭，也不得只寫
序號。Issue title 另依 AGENTS.md 使用 12–80 個 ASCII 字元與至少三個單字；
delivery branch 則使用 `dev/m<編號>-<小寫 ASCII slug>`，不把 title 當 branch
名稱。建立前可用下列唯讀 dry-run 同時檢查 open 與待建立的 title；adopt／
update 的 description migration 不會自動改名。

```console
uv run --no-project python scripts/spec_to_issue.py audit-milestones \
  --repo owner/repo --title "Proposed outcome"
```

```markdown
## Problem

用一小段話交代受影響角色、目前情境、端到端缺口，以及為何現在值得處理；
先描述問題，不先指定解法。

## Outcome

用 user story 說明：完成後，哪個角色可以做到什麼，並得到哪個可觀察的價值。

## Acceptance criteria

- [ ] 列出 2–5 項 story-level、可獨立驗證的結果，不要抄寫 implementation tasks。

## Plan

1. #<issue> — 第一個可獨立交付的工作與目的。
2. #<issue> — 後續工作、順序或依賴；實作發現新資訊時同步調整。

## Out of scope

列出看似相關、但不影響本 story 驗收且刻意排除的工作。

## Verification

寫出 maintainer 如何端到端驗證 outcome，而不只列單元測試指令。

## References

- #N — 註明沿用、取代或駁回的既有決策與理由。
- 連結來源 spec、使用者研究或導入盤點；若沒有候選，記錄 bounded search 範圍。
```

只掛入直接推進 acceptance criteria 的 Issues，不要再掛其 pull requests
造成進度重複計算。只有真正期限才填 due date，不要把它當 release label。
關閉最後一張 Issue 前，須勾選所有已驗證的 acceptance items；否則 lifecycle
workflow 會讓未完成的 story 保持開啟。
建立前須閱讀相關 open／closed Issues 的內文、comments 與 linked pull requests；
不能只依 titles 或 labels 推翻既有決策。
