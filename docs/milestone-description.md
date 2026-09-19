# Delivery Milestone description

下列內文以繁體中文示範；實際 description 請使用專案團隊慣用的語言。
保留英文 H2 標題，讓人與自動化都能辨識結構。Feature parent Issue 保存 SDD
story；Milestone 只保留足以理解、排程與驗收一次 delivery／release 的內容，
完整設計細節請連回 Feature、spec 或決策紀錄。建立時必須填入真實 due date。

在既有或新建的 Milestone 底下指派工作前，先執行
`python3 scripts/sync_milestone_state.py preflight --repo <owner/repo>
--milestone <N>`，確認 due date、追蹤 Issue 標題、`Lifecycle Issue: #N` 連結
三者是否已經一致，不必等到第一張工作 Issue PR 卡在 `Validate Milestone
approval` 才回頭發現——Milestone 13 就是在這裡出事：編號、due date、追蹤
Issue 標題三者當時各自手打，沒有任何東西保證彼此一致（Issue #572）。本模板中央
repo 另提供 `scripts/create-milestone --repo <owner/repo> --title "<title>"
--due-on <YYYY-MM-DD> --proposal-file <path>`，取代分開在 GitHub UI 手動建立
Milestone 物件與追蹤 Issue 兩步：一次呼叫建立兩者，追蹤 Issue 標題直接用 GitHub
回傳的 Milestone 編號動態組成，不接受人工另外打一個序號，建立完成後自動執行上述
`preflight` 作為自我驗證，失敗時會印出手動修正或刪除半成品 Milestone 的指令
（GitHub 本身沒有跨物件 transaction，所以這裡的「原子」是「不驗證過關就不回報
成功」，不是底層機制保證）。採用此模板但沒有這支腳本的下游專案，可依上述流程手動
建立後跑 `preflight` 確認。

每個 Milestone 另建一張生命週期追蹤 Issue，標題固定為
`Milestone <編號>: <里程碑名稱>`，例如
`Milestone 8: Interactive docs and policy alignment`。冒號後的文字必須與 GitHub
Milestone 名稱完全相同；本文依序掛 `Proposal`／`Completion evidence`／
`Early termination`／`Promotion` 四個 H2 段落，核准、反駁與提前終止等狀態只寫在
Issue 內文與留言。Tracker 表單同時宣告這批工作的發布層級；底下 work Issue 繼承該值，
不得另填相衝突的層級。預設 alpha 可由對該 repo 有 `admin` collaborator 權限的提案者
留言 `/milestone admin-approve: <理由>` 自核；beta／early／formal 一律要求非提案者
留言 `/milestone approve`。自核理由必填，且會在 approval 紀錄與 summary 上明確標成
「Admin self-approved」，不得與一般非提案者核准混淆。此判斷查
`GET /repos/{repo}/collaborators/{username}/permission`
而非留言的 `author_association` 欄位——後者的值會受該帳號的 organization membership
公開／私密設定影響，若成員關係設為私密，workflow 自己的 `GITHUB_TOKEN` 可能看不到正確
關係，導致這項檢查不穩定；repo collaborator 權限不受此影響。

建立追蹤 Issue 時使用 `.github/ISSUE_TEMPLATE/milestone-tracker.yml`（Issue #555）：表單已
預先帶入 `Proposal`／`Completion evidence`／`Early termination`／`Promotion` 四個 H2 段落骨架
與說明文字，減少人工照抄漏段落的機率；`scripts/sync_milestone_state.py` 的 `tracker_errors()`
仍在建立後把關格式是否正確——表單降低出錯機率，不取代驗證。這份表單只建立追蹤 Issue 本身，
不是下方 GitHub Milestone 物件 `description` 使用的七段式格式，兩者不要混用同一份骨架。
只有 repository collaborator 建立的 tracker 層級宣告會被信任；不受信任的宣告改用
`.csarc/config.yml` 的預設層級。

底下每一張 work Issue 預設直接繼承 tracker 的核可狀態，不需要額外核可——維持「範圍內
工作零額外成本」的現況特性。只有當一張 work Issue 的 body 包含逐字獨立一行的
`Tracker scope: expanded`（`has_scope_sentinel()`，只認這個逐字 marker、不判斷語意），
才代表提案者自己宣告這張 Issue 已超出 tracker 最初的 Proposal／Acceptance criteria
範圍；此時這張 Issue 本身需要一次獨立核可：alpha 可用同一套 `admin` collaborator
權限自核例外，beta 以上則必須由非提案者核可（`scope_decision()`；CLI：
`check-scope --repo <repo> --issue <編號>`）。
核可留言語彙（`/milestone approve`／`/milestone admin-approve: <理由>`／
`/milestone object:`／`/milestone resolve:`）與判斷邏輯與 tracker 完全相同，只是核可
對象換成這張 work Issue 自己的留言，而不是 tracker 的留言。

個別 work PR 除了 `scripts/validate-pr-policy` 的結構檢查，還會依繼承的發布層級通過
`review` required check。alpha 允許 exact-head 自我授權；beta／early／formal 必須是
非 PR 作者的 exact-head 核准，後續 push 會使舊核准失效。GitHub Ruleset 永遠保留必要
status checks 且不設 bypass；只把 PR review 規則的 bypass 限在 alpha 或下述 hotfix
緊急路徑，並由 lifecycle 留下稽核證據。這是 #745 對早期「work PR 不加 review gate」
決定的明確取代；留言仍不沿用 `/milestone` 語彙。

上一段講的是「有 Milestone 的 work PR」不額外加裝核可；沒有 Milestone 的 Issue（見
`docs/ci-policy.md`「不屬於里程碑的工作」「Hotfix」「Release recovery」三節）情況相
反——這種 Issue 沒有任何 tracker 可以繼承核可，`#743` 之前實際上完全不需要核可就能
合併其工作 PR，變成繞過批次治理的捷徑。`#743` 補上這個缺口，#745 再依層級限縮：一張
沒有 Milestone 的 Issue，alpha 可由 `admin` collaborator 自核（理由必填），beta 以上
必須由非提案者核可，才能讓以 `Closes`／`Fixes`／`Resolves #N` 連結它的 PR 通過「Validate Milestone
approval」與 merge queue 的「Revalidate queued Milestone approval」
（`standalone_issue_approval_decision()`／`check_issue_approval()`；CLI：
`check-issue-approval --repo <repo> --issue <編號>`）。核可留言語彙是純文字、不分大小
寫的 `Approve`／`Admin-approve: <理由>`／`Object: <理由>`／`Resolve: <目標>`——刻意
與 tracker、scope-expansion 兩個既有 gate 的 `/milestone approve` 系列語彙保持獨立、
不互相沿用（維護者在 Issue #743 留言中的決定：沒有 Milestone 的 Issue 用不上「/milestone」
這個斜線指令，純文字關鍵字也不必先查文件），只是判斷演算法的結構相同，核可對象換成
這張沒有 Milestone 的 Issue 自己的留言。這與上一段「不延伸到 work PR」的決定並不衝突：核可對象仍然是
Issue，不是 PR 本身，PR 合併授權依舊由 `validate-pr-policy` 與 release-level-aware
review 共同負責。屬於 Milestone 的 work Issue 不受影響，繼續只靠 tracker 核可，不需要
逐張另外核可。唯一例外是 beta 以上 hotfix：admin 必須以自己的身分對 exact head 留理由，
系統驗證 Issue 提案者、授權者與 merge actor 相同，並在合併後自動建立待同儕複核 Issue。
細節見 `docs/ci-policy.md`「Standalone／hotfix／release recovery Issue 核可 gate（#743）」
一節。

Issue 核可之外，`#632` 另有一道窄範圍 gate：`pr-policy.yml` 額外呼叫
`scripts/check-scope-gate`，只在該 PR 連結的 work Issue 自己宣告了
`Tracker scope: expanded` 時才生效，把上方 `scope_decision()` 這個既有的 Issue-level
gate 實際接上合併流程；沒有宣告的 work PR（現況的絕大多數）完全不受影響，行為與之前一
致。這項 gate 沒有新增任何 `/milestone` 留言語彙——核可
對象仍是 work Issue 自己的留言，`check-scope-gate` 只是把既有判斷結果實際擋在合併之
前，而不是像 `#552` 落地時那樣只能靠人手動跑 `check-scope` CLI 才會被看見。核可另外綁定
了 body 內容的 fingerprint：核可留言之後 Issue 又被編輯（`updated_at` 晚於核可留言
`created_at` 超過緩衝窗），舊核可視為過期，需要重新核可，細節見
`docs/ci-policy.md`「Scope-drift gate enforcement 與核可 fingerprint-binding（#632）」
一節。

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

已評估（Issue #555）改用 GitHub 原生 sub-issues（`parent`／`subIssuesSummary` 欄位與對應新增
／移除 sub-issue REST 端點）取代上方純文字 `References` 列點，讓 tracker 直接掛住底下 work
Issue；結論是**不採用**，理由記錄於 `docs/adr/spec-story-and-work-items.md`：GitHub 的
sub-issue 關聯是單一 parent（一張 Issue 同時只能有一個 parent），這個 repo 已經把這個唯一的
parent 欄位用在 Feature／Task／Bug 既有階層（例如 #586、#590 皆已是 Feature #524 的
sub-issue）；若同時把 tracker 設成這些 work Issue 的 parent 會直接衝突，GitHub 不支援雙
parent。退而求其次只掛「未被 Feature 收編」的頂層 leaf Issue，又會讓 sub-issue 進度條與
`load_snapshot()` 既有的 `milestone=N` 查詢兩者涵蓋的集合系統性不一致（前者漏掉巢狀 Feature
底下的 work Issue），比現況的 `References` 列點更容易誤導。`milestone=N` 查詢已經是完整、經
測試驗證的 tracker↔work-Issue 連結來源，維持現況即可，不引入第二套會與既有 Feature 階層衝突
又不完整的關聯機制。
關閉最後一張 Issue 前，須勾選所有已驗證的 acceptance items；否則 lifecycle
workflow 會讓未完成的 story 保持開啟。
背景 lifecycle reconcile 只在 tracker Issue 的事件／留言、Milestone 事件，以及 Issue
移入、移出或改掛 Milestone 時同步狀態與刷新 PR check；一般 work Issue 的編輯、label 或
留言會成功 no-op。tracker 尚未核准、核准失效或有未解反駁屬於正常治理狀態：背景 run 以
notice 呈現並成功結束，但 PR 上的核准 check 仍維持失敗。tracker 缺漏／格式錯誤、API 或
狀態寫入錯誤才讓背景 run 失敗。
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
