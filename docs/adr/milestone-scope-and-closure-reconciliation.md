# Milestone scope-drift and closure-reconciliation ADR

- **狀態：**Accepted
- **日期：**2026-09-03
- **來源 Issues：**[#552](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/552)（沿用並延伸 [#512](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/512)／[#518](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/518)／[#546](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/546)／[#549](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/549)／[#550](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/550) 已完成的機制；不推翻重來），另參考 [#580](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/580) 記錄的 Ruleset bypass 成本
- **實作 PR：**[PR #609](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/609)
- **後續補完 Issues：**[#632](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/632)——把本 ADR「刻意不做的部分」明確保留給後續 Issue 的兩件事（CI 接線、核可 fingerprint-binding）補齊；[#816](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/816)——讓 `Delivered` 同時要求 leaf acceptance checklist 完成，並讓 completed closure 拒絕任何非 `Delivered` work Issue。兩者都不推翻本 ADR 的資料來源或 lifecycle 分工，見下方對應段落與「歷史 disposition」表

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
  標成 `Delivered`／`Closed without a merged PR`／`Pending`／`Acceptance incomplete or
  missing` 四種狀態之一。`#816` 起，只有 Issue 已關閉、closing PR 已合併，且 Issue body
  既有 checklist 存在並全部完成時才是 `Delivered`。
- 這是一張給人核對用的結構化清單，不嘗試自動比對 Milestone acceptance criteria 文字與
  交付內容的語意——`#552` 已確認那種語意分類目前不現實。客觀 delivery 狀態則由同一個
  shared decision 同時提供表格與 completed closure 使用；`#816` 起，只要任一 leaf Issue
  不是 `Delivered`，completed closure 就列出 Issue 編號與狀態並 fail closed。
- **Staleness 偵測：**段落開頭嵌入 `<!-- reconciliation-fingerprint: <hash> -->`，
  `<hash>` 是「tracker body 扣掉 Reconciliation 段落本身」內容的 SHA-256
  短雜湊（`_fingerprint()`／`_remove_section()`）。`regenerate_reconciliation()` 只改寫
  Reconciliation 段落本身，從不改動 body 其他部分，所以只要有人（或 agent）事後編輯了
  Proposal／Completion evidence／Early termination／Promotion 任何一段，這個雜湊就會
  對不上，`reconciliation_status()` 回報 `Reconciliation: stale, regenerate before
  closing`（逐字沿用 `#552` 提案的 marker 文字）。
- `closure_decision()` 的 completed 收尾路徑（`_completed_closure()`）要求所有 leaf Issue
  都通過上述 shared delivery decision，並保留既有的 acceptance／promotion checkbox、
  approval、evidence 與 Reconciliation freshness 門檻；表格新鮮但有非 `Delivered` 列仍
  必須失敗。`not_planned`（提前終止）路徑不受影響——那條路徑本來就不宣稱交付完成，不
  適用「核對交付內容」這件事。
- `#871` 的 release completer 在任何 machine-owned body 寫入前，先以 tracker 當下
  `updated_at` 重驗核可；寫入 exact promotion／Release evidence、重建 Reconciliation
  或切換 closed state 都會推進 `updated_at`，所以 completed closure 在這個 post-write
  邊界改由 Reconciliation fingerprint 綁定 body，仍獨立拒絕被編輯過的核可留言。只有
  exact evidence 已存在且 fingerprint fresh 的同一 candidate 才可在中斷後重跑。

**刻意不做的部分：**Reconciliation 不是 `TRACKER_SECTIONS` 的必要段落，不在建立 tracker
時要求存在——它必須先有一次 `regenerate-reconciliation` 執行才會出現，若列為建立時必要
段落會讓 tracker 永遠無法通過 `tracker_errors()`。Staleness 偵測只綁「tracker Issue body
自己的編輯」，刻意不綁「Milestone description（Acceptance criteria／Plan）被編輯」或
「某張 linked work Issue 的即時狀態改變」：後兩者屬於不同的 GitHub 物件，而
`regenerate_reconciliation()` 每次執行本來就會重新抓即時資料，不會回傳快取內容；
`#816` 起，completed closure 也會用同一個 delivery decision 直接重算 live Issue／PR／
checklist 狀態，所以 linked work Issue 在 regenerate 後又變動時仍會 fail closed，而不是
把表格 freshness 當成 delivery 通過。tracker fingerprint 仍只負責攔截「maintainer 在最近
一次 regenerate 之後、關閉之前，又動了 tracker body 本身」這個時間窗口。這個新機制當時只加進
`sync_milestone_state.py` 本身（純函式＋新增的 `check-scope`／
`regenerate-reconciliation` CLI 子指令），刻意不修改
`.github/workflows/milestone-lifecycle.yml` 的觸發條件——要不要讓某個 GitHub 事件自動
觸發 scope-gate 檢查或 reconciliation 重新產生，留給後續 Issue 決定，避免這次治理機制
變更的 diff 範圍失控。

**`#632` 後續補完（不推翻本 ADR，僅補齊上一段留下的兩個缺口）：**維護者盤點後確認
`check-scope` 從未被任何 workflow 呼叫過，一張宣告 `Tracker scope: expanded` 且從未核
可的 work Issue 實際上完全不會被擋下；同時 `approval_decision()`／`scope_decision()`
都沒有把核可綁定到特定版本的 body。`#632`（PR 見本節下方 Ownership）補上兩層，範圍嚴格
限定在上一段明確保留給「後續 Issue」的那兩件事，不重新設計 sentinel 偵測本身，也不擴大
`/milestone approve`／`admin-approve` 留言語彙：

- `pr-policy.yml` 新增一個呼叫新腳本 `scripts/check-scope-gate` 的 step，把
  `scope_decision()` 實際接上工作 PR 的合併流程（fail-closed，無連結 Issue 或無
  sentinel 時原樣放行）。
- `_approval_records()`／`_gate_decision()` 新增 `_approval_is_stale()`：預設的開工與
  合併前 gate 比對核可留言
  `created_at` 與其所在 Issue（tracker 或 work Issue）自己的 `updated_at`，超過 60 秒
  緩衝窗（吸收 GitHub 自己「留言建立」到「`updated_at` 反映該留言」之間的實測落差）即視
  為過期。這與 Reconciliation 的 `reconciliation-fingerprint`（比對 bot 自己寫入、可精
  確重算的內容雜湊）機制不同：GitHub REST 不提供 Issue body 的可查詢編輯歷史，核可留言
  又是人寫的，不是 bot 生成，所以退而求其次，用 `updated_at` 這個唯一可查訊號——代價是
  它也會被留言、label、Milestone、state 等與 body 編輯無關的活動一併觸發，因此判定刻意
  只往「提高需要重新核可的誤判率」這個保守方向走，缺少任一時間戳（沿用舊測試 fixture 的
  情境）一律視為「無法判斷」而非「一定過期」，不影響 `#552` 原有行為。

完整說明見 `docs/ci-policy.md`「Scope-drift gate enforcement 與核可
fingerprint-binding（#632）」一節；`docs/milestone-description.md` 同步更新對應段落。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | tracker 層級 `/milestone approve`／`admin-approve`／`object`／`resolve` 留言語彙不變，改抽出共用的 `_gate_decision()` 讓 scope gate 直接重用 | [#400](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/400)／[#518](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/518)／[#549](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/549)／[#550](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/550) → [#552](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/552) |
| Rejected | 每張 work Issue 一律要求核可，不論是否超出範圍 | [#552](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/552) 開放問題 → 本 ADR：只在 sentinel 存在時才加 gate |
| Rejected | 為 work PR 加裝 GitHub 原生 required review | [#512](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/512)／[#518](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/518)／[#546](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/546)／[#549](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/549)／[#550](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/550) 的 self-lock 事件鏈與 [#580](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/580) 的 bypass 成本 → 本 ADR：明確不加，`validate-pr-policy` 結構檢查維持唯一 gate |
| Superseded | 收尾盤點只掃描 checkbox 是否打勾 | 現況（`acceptance_complete()`／`promotion_complete()`）→ 本 ADR：加入 `reconciliation_status()` 作為額外的必要條件，不取代既有 checkbox 掃描 |
| Completed | `check-scope` 接進 `pr-policy.yml`；`approval_decision()`／`scope_decision()` 核可綁定 body fingerprint | 本 ADR「刻意不做的部分」留給後續 Issue → [#632](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/632) 補完，不重新設計 sentinel 偵測或 `/milestone` 留言語彙 |
| Superseded | fresh Reconciliation table 即足以通過 completed closure | [#816](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/816)：保留既有資料來源與 fingerprint，改由 shared delivery decision 同時產生狀態並拒絕任何非 `Delivered` leaf Issue |

## Ownership 與驗證

`scripts/sync_milestone_state.py`（與 `template/` 成對檔案）是這個機制唯一的 source of
truth；`tests/test_milestone_scope.py` 覆蓋 sentinel 偵測、scope gate 與（`#632` 起）核
可 fingerprint-binding 的 staleness 邊界，`tests/test_milestone_approval.py` 同樣覆蓋
tracker 層級核可的 staleness 邊界，`tests/test_milestone_closure.py` 覆蓋 reconciliation
產生、staleness 判定與 `closure_decision()` 的收尾把關。維護者（或 delegate）在真正把
tracker 關閉為 completed 之前，必須跑過一次 `regenerate-reconciliation`，讓
Reconciliation 段落反映關閉當下的即時狀態；`closure_decision()` 本身會在 staleness 判
定失敗時 fail closed，不需要額外人工記憶這個步驟。`scripts/check-scope-gate`（與
`scripts/test-check-scope-gate`，同樣與 `template/` 成對）是 `#632` 新增的 CI 接線層，
把 `check-scope` 實際接進 `pr-policy.yml`；它本身不含判斷邏輯，只負責從 PR body 解析
連結 Issue 編號後呼叫 `check-scope`。

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

## `#743`：沒有 Milestone 的 Issue 本身需要核可

- **狀態：**Accepted
- **日期：**2026-09-18
- **來源 Issue：**[#743](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/743)（Milestone 14 的一條 critical-path 起點；不推翻本 ADR 任何既有決定，只補上第 2 節從未涵蓋的另一半情境）

**問題：**上方「決定」第 2 節（`work PR 核可：明確決定「不加」native required
review`）與維護者的完整核准模型之間，一直存在一個未落地的落差。維護者實際期待的模型
分兩點：(1) 有 Milestone 的 Issue，tracker 核准後底下 Issue 視為已核准，這正是本 ADR
第 2 節與 `approval_decision()` 描述、且已經實作的行為；(2) **沒有 Milestone 的
Issue**（standalone、hotfix、release recovery）本身需要核可，工作 PR 才能合併——這一
點在 `#552`／`#632` 落地時從未實作：`_pull_decision()` 在 PR 沒有 Milestone 時直接放
行，`check-scope-gate` 對沒有 `Tracker scope: expanded` 的 Issue 也直接放行。結果是
同一件工作，留在 Milestone 裡要先經非提案者核准，拆成 standalone 或標成 hotfix 反而
完全不需要核可，讓 standalone／hotfix 路徑變成繞過批次治理的捷徑，與
`docs/ci-policy.md`「不能用 standalone 路徑繞過批次治理」的既有原則矛盾。

**決定：**新增 `standalone_issue_approval_decision()`／`check_issue_approval()`
（CLI：`check-issue-approval --repo --issue`），要求一張沒有 Milestone 的 Issue，在其
`Closes`／`Fixes`／`Resolves #N` 連結的工作 PR 合併前，必須先取得一次非提案者核可，
或同一套 `admin` collaborator 自核例外（理由必填）。核可語彙是維護者在 Issue #743
留言中（2026-09-18，實作開始前）明確決定的**獨立新詞彙**：純文字、不分大小寫的
`Approve`／`Admin-approve: <理由>`／`Object: <理由>`／`Resolve: <目標>`，刻意
**不**沿用 tracker 的 `/milestone approve`／`/milestone admin-approve:`／
`/milestone object:`／`/milestone resolve:`——理由是這張 Issue 根本沒有 Milestone，
套用「/milestone」語意本身就怪，且純文字關鍵字比斜線指令更符合協作者的自然直覺、
不必先查文件。判斷演算法（非提案者要求、admin self-approve 的 collaborator
permission 查核、反駁／解決追蹤、#632 的 fingerprint-binding staleness）與 tracker
核可、`scope_decision()` 結構相同，但用獨立的新函式實作
（`_issue_approval_records()`／`_issue_admin_self_approval()`），刻意不修改也不參數
化既有的 `_approval_records()`／`_admin_self_approval()`：兩套語彙保持並行、互不
影響，只共用與具體語彙無關的 `_gate_decision()`（組裝最終 pass/fail）與
`_approval_is_stale()`（staleness 判定）——「不建第二套系統」在這裡指的是一套共用的
判斷骨架搭配兩套獨立語彙，不是把新語彙合併進既有的比對函式。CI 接線不需要新增
workflow step：`pr-policy.yml` 既有的「Validate Milestone approval」（`check-pr`）與
merge queue 的「Revalidate queued Milestone approval」（`check-merge-group`）本來就
對每個 PR／merge-group commit 呼叫 `_pull_decision()`，`#743` 只改寫這個函式在「PR
沒有 Milestone」分支下的行為。找不到連結 Issue 的 PR（release 自動化、Dependabot、
`automation/*`、main-sync bridge）維持不受影響，與 `check-scope-gate` 既有的相同
carve-out 一致。`.github/ISSUE_TEMPLATE/bug.yml`／`task.yml`／`feature.yml`／
`documentation.yml`（root／`template/` 成對）補上一句提示，說明沒有 Milestone 的
Issue 需要另一位協作者留言 `Approve`，或 admin collaborator 提案者自留言
`Admin-approve: <理由>`。

**與本 ADR 第 2 節的關係：**這是同一份決定的另一半，不是推翻。第 2 節明確保留的範圍是
「**work PR** 不加裝 native required review，也不延伸 `/milestone` 語彙到個別 work
PR」——這裡核可的對象是**Issue**，不是 PR 本身，PR 合併授權依舊完全交給
`validate-pr-policy` 的結構檢查與 #719 的 exact-head review 機制，兩者是彼此獨立、互不
覆蓋的關卡。第 2 節「重新評估條件」寫明的觸發條件（organization 出現第二個真人帳號）已
經成立（例如 wayhong0928 已經在回報與核准），但這裡選擇的解法是「沒有 Milestone 的
Issue 需要核可」，而不是重新開放「work PR 需要 native required review」；後者的
self-lock 疑慮（單一真人帳號時代遺留、`#512`／`#518`／`#546`／`#549`／`#550`）在
Issue-level 核可加上 admin self-approval 例外之後同樣不會重演，因為例外機制的判斷
精神（非提案者要求、collaborator permission 查核、理由必填）原封不動沿用，只是換一
套獨立語彙、獨立函式實作。`#745`（後續 Issue，尚未實作）會依發布層級（alpha／beta
以上）進一步限縮 admin self-approval 是否允許；`#743` 落地的是現行「非提案者核准或
admin 自核」規則，不預先實作 `#745` 的分層邏輯。

完整說明見 `docs/ci-policy.md`「Standalone／hotfix／release recovery Issue 核可
gate（#743）」一節；`docs/milestone-description.md` 同步更新對應段落；
`tests/test_standalone_issue_approval.py`（與 `template/` 成對）是這個機制的回歸測試
來源。

## `#745`：發布層級決定 Issue 與 PR 核准強度

- **狀態：**Accepted
- **日期：**2026-09-19
- **來源 Issue：**[#745](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/745)

#745 取代本 ADR 早期「所有 work PR 都不加 review gate」與 #743「所有 standalone Issue
皆可 admin 自核」兩項過寬結論，但保留 scope sentinel、核准 fingerprint、不同留言語彙與
Milestone inheritance。Issue／tracker 的發布層級現在決定兩個 gate：alpha 可由 admin
提案者自核，且 PR 可使用 exact-head self authorization；beta／early／formal 的 Issue
與 PR 都要求非提案者／非作者核准，後續 push 使舊 PR 核准失效。

Milestone work Issue 一律繼承 tracker 層級；子 Issue 若自行宣告不同值即 fail closed。
只有 repository collaborator 建立的宣告可信，否則用設定預設值。beta 以上唯一自核例外
是 hotfix 緊急路徑：必須是 standalone hotfix Issue，由同一位即時具 admin 權限的提案者
對 exact head 留理由並執行 merge，合併後自動建立待同儕複核 Issue。必要 status checks
在任何層級與任何例外下都不能 bypass。
