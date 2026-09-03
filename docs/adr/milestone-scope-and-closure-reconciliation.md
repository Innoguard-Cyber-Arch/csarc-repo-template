# Milestone scope-drift and closure-reconciliation ADR

- **狀態：**Accepted
- **日期：**2026-09-03
- **來源 Issues：**[#552](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/552)（沿用並延伸 [#512](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/512)／[#518](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/518)／[#546](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/546)／[#549](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/549)／[#550](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/550) 已完成的機制；不推翻重來），另參考 [#580](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/580) 記錄的 Ruleset bypass 成本
- **實作 PR：**[PR #609](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/609)

## 問題與限制

`sync_milestone_state.py` 既有的 Milestone 生命週期機制只做到兩件事：tracker Issue
本身要有非提案者 `/milestone approve`（或 owner／admin-permission 自核例外）才能「解鎖」
整個 Milestone；`closure_decision()`／`acceptance_complete()` 在收尾時掃描 Promotion
段落與 Milestone acceptance criteria 的 checkbox 是否全部打勾。這留下兩個結構性落差：

1. Tracker 核可之後，底下每一張 work Issue 完全繼承這個核可，不論其內容是否明顯超出
   tracker 最初的 Proposal／Acceptance criteria 範圍（scope creep）——現況沒有偵測、
   也沒有要求額外核可的機制。
2. 收尾盤點只是「checkbox 是否打勾」的形式檢查，不會重新核對「這些 work Issue 的實際
   交付內容（是否關閉、其 `Closes #N` PR 是否真的合併）是否真的對應 Milestone 最初宣稱
   的 acceptance criteria」。一份全打勾的 Promotion 段落無法證明底下工作真的交付。

`#552` 額外把「work PR 是否也要核可」列為待決問題，並明確提出這個 repo 是單一真人帳號
組織（或由 agent 代為提案），GitHub 平台本身禁止「核准自己開的 PR」，這正是
`#512`／`#518`／`#546`／`#549`／`#550` 一連串 self-lock 事件的根因：`/milestone
admin-approve` 例外機制本身就是為了解開 tracker 層級的這個死結而生（先後嘗試
`author_association == OWNER`、`OWNER或MEMBER`，最終落在 `#549`／`#550` 的
collaborator-permission 判斷，因為 `author_association` 在 `GITHUB_TOKEN` 底下不可靠）。
`#580` 之後在 Ruleset 層級再次撞到同一問題：Public 化後 `required_approving_review_count:
1` 第一次真正生效，`gh pr merge --admin` 對新版 Ruleset 不生效，最終得用
`bypass_actors`（`RepositoryRole` id 5、`bypass_mode: pull_request`）繞過，這是一個
需要 admin 權限、且被獨立追蹤重新評估的臨時處置，不是一個可以無痛套用在「每一張 work
PR」上的機制。

## 決定

維護者已在對話中確認採用以下設計；本 ADR 把它落成書面紀錄。

### 1. Scope-drift 偵測：自我宣告 sentinel，而非人工判斷或 NLP 比對

一張 work Issue 的 body 若包含逐字獨立一行的 `Tracker scope: expanded`
（`has_scope_sentinel()`，`(?m)^Tracker scope: expanded\s*$`，逐字比對、不判斷語意），
就代表提案者自己宣告這張 Issue 已超出 tracker 最初範圍。

- **沒有 sentinel（預設，也是現況）：**不需要任何額外核可，直接沿用 tracker 的核可狀態
  開發——維持現行機制對「範圍內工作」完全零成本這個特性。
- **有 sentinel：**這張 work Issue 本身需要一次獨立的非提案者核可，或 `admin`
  collaborator 權限的提案者自核（`scope_decision()`，`check-scope` CLI 子指令）。這條
  gate 直接重用 tracker 既有的 `/milestone approve`／`/milestone admin-approve:
  <理由>`／`/milestone object:`／`/milestone resolve:` 留言語彙與判斷邏輯
  （`_approval_records()`／新抽出的共用 `_gate_decision()`），只是換一組 summary 前綴
  （`Scope expansion approved by` / `Scope expansion admin self-approved by`）與讀取
  對象（該 Issue 自己的 comments，`load_issue_snapshot()`，而非 tracker 的 comments）。

判定「是否超出範圍」本身仍是人工判斷——由提案者自己在 body 寫下 sentinel、由核可者決定
是否同意——這裡只負責偵測宣告是否存在與核可是否到位，不嘗試自動判斷語意上是否真的超出
Proposal。

### 2. Work PR 核可：明確決定「不加」native required review

這是一個經過盤點後的有意識決定，不是從未被檢視過的現況延續：**不**在 work PR 上加裝
GitHub 原生 required review（branch protection／Ruleset review gate），也不延伸
`/milestone` 語彙到個別 work PR 層級。既有 `scripts/validate-pr-policy` 的結構檢查
（acceptance criteria checkbox 全打勾、`Closes #N` 存在且對應正確）維持是 work PR 唯一
的合併前置檢查。

理由：這個 repo 實質上是單一真人帳號（或由 agent 代為作者）撰寫每一張 work PR，GitHub
平台層級禁止「核准自己開的 PR」（`Review Can not approve your own pull request`，這是
GitHub 全站限制，不是本 repo 政策，無法繞過）。在 tracker 層級要求 native required
review，正是 `#512`／`#518`／`#546`／`#549`／`#550` 那一連串事件的根因與修補過程；若把
同一機制套用在數量遠多於 tracker（一個 Milestone 常有 30-90 張 work Issue／PR）的
work PR 上，會把同一個 self-lock 複製到每一張 work PR，而且沒有對應的
`/milestone admin-approve` 式例外可用（那條例外是綁在 tracker 這個單一 Issue 上設計
的，沒有為每張 work PR 重建一套的必要性）。`#580` 顯示：即使願意在 Ruleset 層級加裝
`bypass_actors` 繞過，也需要 admin 權限、需要被獨立追蹤與重新評估，成本明顯高於
`validate-pr-policy` 現有的結構檢查所能提供的邊際效益。

### 3. Reconciliation 段落：tracker Issue body 新增第五個 H2 段落，自動重新產生

`sync_milestone_state.py` 新增 `regenerate_reconciliation()`／`record_reconciliation()`
（CLI：`regenerate-reconciliation --repo --milestone <N>`），在 tracker Issue body 既有
的 `Proposal`／`Completion evidence`／`Early termination`／`Promotion` 四段之外，維護一個
獨立、清楚分隔的 `## Reconciliation` 段落：

- 內容是一張逐列對照表：走訪這個 Milestone 底下每一張非 tracker、非 PR 的 Issue
  （`_linked_work_items()`，與 `closure_decision()` 既有的「未關閉項目」判斷用同一組活資
  料，不另外解析 Milestone body 的 `Plan` 條列文字），列出它目前是否關閉、宣告
  `Closes #N` 的 PR 是否已合併（`_closing_pull_requests()`／`_merged_at()`，直接讀
  GitHub REST `issues` 端點回傳的 `pull_request.merged_at` 欄位，不需要額外呼叫），並
  標成 `Delivered`／`Closed without a merged PR`／`Pending` 三種狀態之一。
- 這是一張給人核對用的結構化清單，不是自動判定「完全等於通過」的語意驗證——`#552`
  自己的開放問題已經確認「完全自動化比對 acceptance criteria 文字語意與交付內容」目前
  不現實；折衷是收尾前強制產生逐條對照，交給人核對簽核，而不是像現在這樣完全隱性。
- **Staleness 偵測：**段落開頭嵌入 `<!-- reconciliation-fingerprint: <hash> -->`，
  `<hash>` 是「tracker body 扣掉 Reconciliation 段落本身」內容的 SHA-256
  短雜湊（`_fingerprint()`／`_remove_section()`）。`regenerate_reconciliation()` 只改寫
  Reconciliation 段落本身，從不改動 body 其他部分，所以只要有人（或 agent）事後編輯了
  Proposal／Completion evidence／Early termination／Promotion 任何一段，這個雜湊就會
  對不上，`reconciliation_status()` 回報 `Reconciliation: stale, regenerate before
  closing`（逐字沿用 `#552` 提案的 marker 文字）。
- `closure_decision()` 的 completed 收尾路徑（`_completed_closure()`）在既有的
  acceptance／promotion checkbox 掃描與 approval 判斷之後，新增最後一道門檻：
  Reconciliation 段落必須存在且新鮮（`reconciliation_status(body).allowed`），否則收尾
  失敗，不能只靠 checkbox 打勾就關閉 Milestone。`not_planned`（提前終止）路徑不受影響
  ——那條路徑本來就不宣稱交付完成，不適用「核對交付內容」這件事。

**刻意不做的部分：**Reconciliation 不是 `TRACKER_SECTIONS` 的必要段落，不在建立 tracker
時要求存在——它必須先有一次 `regenerate-reconciliation` 執行才會出現，若列為建立時必要
段落會讓 tracker 永遠無法通過 `tracker_errors()`。Staleness 偵測只綁「tracker Issue body
自己的編輯」，刻意不綁「Milestone description（Acceptance criteria／Plan）被編輯」或
「某張 linked work Issue 的即時狀態改變」：後兩者屬於不同的 GitHub 物件，而
`regenerate_reconciliation()` 每次執行本來就會重新抓即時資料，不會回傳快取內容；唯一需
要攔截的，是「maintainer 在最近一次 regenerate 之後、關閉之前，又動了 tracker body
本身」這個時間窗口，而這正是 `#552` 原文描述的 staleness 情境。這個新機制目前只加進
`sync_milestone_state.py` 本身（純函式＋新增的 `check-scope`／
`regenerate-reconciliation` CLI 子指令），刻意不修改
`.github/workflows/milestone-lifecycle.yml` 的觸發條件——要不要讓某個 GitHub 事件自動
觸發 scope-gate 檢查或 reconciliation 重新產生，留給後續 Issue 決定，避免這次治理機制
變更的 diff 範圍失控。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | tracker 層級 `/milestone approve`／`admin-approve`／`object`／`resolve` 留言語彙不變，改抽出共用的 `_gate_decision()` 讓 scope gate 直接重用 | [#400](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/400)／[#518](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/518)／[#549](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/549)／[#550](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/550) → [#552](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/552) |
| Rejected | 每張 work Issue 一律要求核可，不論是否超出範圍 | [#552](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/552) 開放問題 → 本 ADR：只在 sentinel 存在時才加 gate |
| Rejected | 為 work PR 加裝 GitHub 原生 required review | [#512](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/512)／[#518](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/518)／[#546](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/546)／[#549](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/549)／[#550](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/550) 的 self-lock 事件鏈與 [#580](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/580) 的 bypass 成本 → 本 ADR：明確不加，`validate-pr-policy` 結構檢查維持唯一 gate |
| Superseded | 收尾盤點只掃描 checkbox 是否打勾 | 現況（`acceptance_complete()`／`promotion_complete()`）→ 本 ADR：加入 `reconciliation_status()` 作為額外的必要條件，不取代既有 checkbox 掃描 |

## Ownership 與驗證

`scripts/sync_milestone_state.py`（與 `template/` 成對檔案）是這個機制唯一的 source of
truth；`tests/test_milestone_scope.py` 覆蓋 sentinel 偵測與 scope gate，
`tests/test_milestone_closure.py` 覆蓋 reconciliation 產生、staleness 判定與
`closure_decision()` 的收尾把關。維護者（或 delegate）在真正把 tracker 關閉為
completed 之前，必須跑過一次 `regenerate-reconciliation`，讓 Reconciliation 段落反映
關閉當下的即時狀態；`closure_decision()` 本身會在 staleness 判定失敗時 fail closed，
不需要額外人工記憶這個步驟。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 每張 work Issue 一律要求非提案者核可（不論是否在範圍內） | 不採用；會讓現況「範圍內工作零額外成本」的特性消失，且 30-90 張 Issue 逐一核可的樣板成本已在 `#512` 判斷過高於保留彈性的價值 |
| Native required PR review（branch protection／Ruleset review gate） | 不採用；單一真人帳號組織下會重演 `#512`／`#518`／`#546`／`#549`／`#550` 的 self-lock，且沒有對應每張 work PR 的例外機制可用 |
| 延伸 `/milestone` 留言語彙到個別 work PR 核可 | 不採用；效果等同重建一套 review gate，仍需要解決同一個 self-lock 問題，且會讓 PR 合併速度依賴留言而非既有結構檢查 |
| Reconciliation 完全自動化語意比對（acceptance criteria 文字 vs 交付內容） | 不採用；`#552` 已判斷目前不現實，改採結構化逐行表格＋人工簽核 |
| Reconciliation 內嵌進既有 `Promotion` 段落，而非獨立段落 | 不採用；分開段落讓「自動生成內容」與「人工勾選內容」的邊界清楚，staleness 偵測也不必和人工 checkbox 混在同一段落判斷 |
| Staleness 判定同時綁定 Milestone description（Acceptance criteria／Plan）編輯 | 不採用（本次範圍內）；那是不同的 GitHub 物件，且每次 regenerate 都重新抓即時資料，真正需要攔截的只有「regenerate 之後、關閉之前，tracker body 本身又被動過」這個時間窗口 |
| 立刻把 scope-gate／reconciliation 自動觸發寫進 `.github/workflows/milestone-lifecycle.yml` | 延後；本次先落地 `sync_milestone_state.py` 的機制本身並補齊測試，觸發時機留給後續 Issue 決定，避免這次治理變更的 diff 範圍失控 |

## 重新評估條件

若這個 organization 未來真的擁有第二個真人帳號、且 native required review 不再會複製
`#512`／`#518`／`#546`／`#549`／`#550` 的 self-lock，重新評估是否要為 work PR 加上核可
機制。若 reconciliation 的 staleness 判定在實務上被證明不足以涵蓋「Milestone
description 被編輯後、tracker body 沒有對應更新」的情境，重新評估是否要把 Milestone
description 一併納入雜湊來源。若決定要自動觸發 scope-gate 或 reconciliation
重新產生，屆時再擴充 `.github/workflows/milestone-lifecycle.yml`。
