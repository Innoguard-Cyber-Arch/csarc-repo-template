# CI/CD 設定與交付邊界

本頁只描述 2026-09-01 在 repository 內可執行、可由 live run 證明的設定。已決定不恢復的
版本／交付 workflow 已刪除，歷史只由 Git／Issue／PR 保存，不在目前 tree 保留副本。舊 Issue 完成或舊 run 成功，都不等於目前
active。版本、發版與成品責任的完整盤點見中央模板的
[版本／交付 ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/release-security-and-dependencies.md)。

## 審查與合併資格

本文件在每個 repository 內都是審查、required checks、合併資格、admin bypass 與
quota fallback 的唯一規範來源；`AGENTS.md` 與 README 只連到這裡，不另寫第二套例外。任何 PR 都必須符合
下方對應交付路徑、目前 head 的審查或明確授權，以及該風險層級的 local self-attested 或 hosted
trusted evidence；草稿不具合併資格。有 Milestone 的工作繼承 tracker 核准，standalone、hotfix 與
release recovery 則依本文件各自的 Issue 核可 gate。所有 fallback 都必須使用本文件明列
的條件與留痕，不得把 runner、方案或權限限制當成略過檢查的理由。

## 現行交付路徑

`main` 是唯一永久整合 branch。一般獨立 Issue 從最新 `main` 建立短分支，經 PR 直接回
`main`。只有需要共同整合與端到端驗收的 Milestone 才使用短生命週期
`dev/m<編號>-<簡稱>`；Milestone 內每張 Issue 仍以自己的 `type/<Issue>-*` PR 進入該
branch，最後由一張受審查的交付 PR 送回 `main`。

Reviewer assignment（`.github/workflows/governance-comment.yml`）已在本 repo 與所有生成
repo 啟用；生成 repo 預設產生治理漂移排程（`governance-drift.yml`）並每日執行，
可用 `enable_governance_drift_check: false` 關閉。本模板 source repo 保留同一支
`scripts/check-governance-drift` 供本機驗證，不另外啟用排程。

`dev/i<Issue>-*` 只適用於 Issue 已寫明獨立環境、soak／canary 目標與停止條件的例外。
Hotfix 可由 `fix/<Issue>-*` 直接進 `main`，但仍須 Issue、review 與 full verification。
固定 `dev/next` 與 `promote/next` 已退役，不是一般工作路徑。

```text
獨立 Issue ──────────────── topic PR ───────────────→ main
Milestone Issue ─ topic PR → dev/m* ─ 交付 PR ─────→ main
明列 canary 的 Issue ─────→ dev/i* ─ 交付 PR ─────→ main
緊急修正 ──────────────── reviewed hotfix PR ─────→ main
```

工作 PR 關閉單項工作；Milestone 交付負責批次進入 `main`。每張 CSARC-owned
release-worthy work／promotion PR 都在同一張 PR 的 final release-only commit materialize 精確版本與
CHANGELOG；Milestone work 使用 beta，`promote/m<編號>-<簡稱>`、standalone 與 hotfix
使用 stable。Promotion PR 用 `Refs #<tracker>` 保持 tracker open。合併後由
hosted／本機共用的 publisher 發布並驗證 Release，再把
promotion commit 與 Release 網址回填進 tracker 的 `Completion evidence`，接著關閉 tracker
與 Milestone；發布失敗時維持 open，成功重跑可安全收尾（#871）。Product-owned／
verification-only repository 不套用這段 CSARC 發版與結案責任。
delivery branch 清理仍由 worktree 清理流程負責，不由版本或發版流程重複處理。
正式 `sync/main-to-mN-*` 只是把 current `main` 的已審查內容帶入 delivery branch，不是
work Issue 或新的發版邊界；它先通過 exact current-main、base/head、同 repository 與雙父
merge topology 驗證後，才略過互斥的單父 release-only 檢查。下一張真正的 Milestone work
PR 仍須依最新 delivery tip 重新計算並物化 beta。

`complete-release` 在任何 tracker body 寫入前先用當下 `updated_at` 重驗既有核可，再以
同一次 snapshot 產生 exact promotion／Release evidence 與 Reconciliation。因為這些
machine-owned 寫入與 close state 本身一定會推進 `updated_at`，completed closure 不用該
欄位反過來把自己的收尾動作判成 stale；它改由 fresh Reconciliation fingerprint 綁定
目前 body，且仍拒絕事後編輯過的核可留言。中途失敗的 retry 只有在同一組 exact evidence
已存在且 fingerprint 仍 fresh 時才沿用這個 post-write 邊界。

## Milestone 掛勾與持續同步（#551／#962）

Milestone 8 收尾階段 #546–#550 五張 Issue／PR 全部沒有掛 Milestone；#551 先補上兩層
非阻擋性提醒。#962 進一步修正 M16 的 Feature #939 漏掛，並補齊 linked Issue 的
Milestone 後續變更不會同步既有 open PR 的缺口。許多 Issue／PR 本來就與任何 Milestone
無關，因此只有明確的 Issue→PR 關係會自動同步，不從標題或目前有哪些 Milestone 猜測。
Milestone preflight 與 lifecycle reconciliation 另以原生 `parent_issue_url` 驗證
Feature parent 與 sub-issues 位於同一個 delivery bucket，防止 #939 類型的遺漏復發。

- `scripts/gh-issue-create`：本機開 Issue 當下，若沒有帶 `--milestone`／`-m`，且
  `scripts/detect-open-milestone` 判定目前恰好只有一個 open Milestone，會印出提示；
  互動式終端機（`stdin` 是 tty）額外詢問是否要帶入該 Milestone，非互動環境
  （agent／CI／腳本呼叫）只印出提醒，不阻擋 Issue 建立。
- `scripts/sync_work_item_metadata.py`（CI 端：可信任 default branch 定義的
  `pr-policy-writes.yml` `metadata` job）：PR 事件發生時，從唯一 linked Issue 同步
  classification、assignee 與 Milestone；Issue 收到 `milestoned`／`demilestoned` 事件時，
  `work-item-lifecycle.yml` 反向尋找並同步所有 linked open PR。若 PR 指向多張 Issue，會
  fail closed，不猜測哪張才是 metadata 來源。只有 PR 與 linked Issue 兩邊都沒有
  Milestone 時，才沿用 #551 的一次性提醒。
- 兩者共用同一支 `scripts/detect-open-milestone` 判斷式：0 個或 2 個以上 open
  Milestone 都視為「無法判斷」，一律不提醒——避免在多 Milestone 並行時猜錯、誤導。
- 建立／驗證當下的提醒不負責推測 Issue 所屬批次；但一旦 Issue 已明確選定 Milestone，
  既有 open PR 會持續同步。任何剩餘的 Issue／PR Milestone 不一致仍由
  `scripts/validate-pr-policy` fail closed（見下方 PR policy 逐 step 判讀一節）。

**Milestone 一旦關閉，事後補掛不能用 `gh issue edit --milestone <name>`**——它只用
名稱查找 open milestone，Milestone 關閉後查不到，會誤以為沒有這個 Milestone、或誤報
找不到。正確做法是改用 REST API 直接指定 milestone number：

```bash
gh api repos/{owner}/{repo}/issues/{n} --method PATCH -f milestone=<number>
```

`<number>` 是 Milestone 的數字 ID（不是標題），可用下列指令查出，closed Milestone 也
查得到：

```bash
gh api repos/{owner}/{repo}/milestones --method GET -f state=all \
  --jq '.[] | "\(.number)\t\(.title)\t\(.state)"'
```

## 核准後 body 編輯提醒（#799）

核准綁定內容的 gate 會在 Issue body 後續變動時要求重新核准，但遠端 CI 只能在變動
已經發生後才看見。要從本機或 agent 編輯 Issue body，使用
`scripts/gh-issue-edit` 取代直接呼叫 `gh issue edit`：

```bash
scripts/gh-issue-edit 740 --body-file tracker.md
```

wrapper 只在 `--body`、`--body-file` 或 `--attach` 真正會改動 body 時執行預測；title、
label、assignee、Milestone 等 metadata-only 編輯原樣直通。它讀取目前 Issue 與留言，
用既有 `_approval_is_stale()` 對「目前 `updated_at`」與「假設現在完成編輯」各判斷一
次，並沿用 tracker／scope expansion 的 `/milestone approve` 語彙與 #743 standalone／
hotfix／release-recovery Issue 的 `Approve` 語彙。若這次編輯會讓最後一組有效核准失
效，訊息會列出核准留言連結、核准者與應重新留言的語彙；仍有另一則核准落在既有 60
秒 grace window 內時不誤報。

互動式終端機會詢問是否繼續；非互動 agent／CI 只印提醒，仍以完全相同的參數執行
`gh issue edit`，並保留其 exit status。預測查詢本身失敗也只印 notice、不把 advisory
變成新的 fail-closed gate。這是 checked-in 本機／agent 路徑的安全網，無法攔截 GitHub
網頁 UI 或直接 REST／GraphQL API 編輯；繞過 wrapper 時仍由既有遠端 gate 事後
fail closed。

### 新發現問題的預設歸屬（#668）

在 Milestone 工作過程中發現的新問題，開新 Issue 時預設留在同一個 Milestone（掛該
Milestone、以其 `dev/m<N>` 為 base），不預設拆成 standalone。只有明顯符合下列任一
例外才 standalone：問題本身跨越多個 Milestone，或是影響所有未來 Milestone 的治理／
工具機制本身（不是這個 Milestone 自己的功能範圍）；緊急生產事故，等不到 Milestone
收尾；問題來源明確是外部回報（其他協作者或 peer session），與本 Milestone 工作內容
沒有直接因果關係。不確定屬於例外時，預設留在 Milestone 內——例外是窄範圍判準，不是
圖方便的預設退路。完整規則見 `AGENTS.md` working loop 步驟 6。

## PR lifecycle single-writer

Agent 先用 `scripts/pr_lifecycle.py create` 從已 push、乾淨的 exact head 直接建立 Draft PR；
不先建立 Ready PR 再切回 Draft，因此反覆修改不會啟動 hosted runner。後續若要變更
ready／draft、授權或 metadata，必須先取得 remote lease，並透過 `scripts/pr_lifecycle.py`
執行；`scripts/verify` 會拒絕另一套重複寫入者。
人工在 GitHub 上審查與合併不受這個工具限制。

### Exact-head review 即為合併授權（#719）

一般有獨立 reviewer 的 PR，不需要再留一則重複的授權留言。`scripts/pr_lifecycle.py`
會把獨立 maintainer 對**目前 head SHA** 的最新有效 `APPROVED` review 直接視為合併授權；
它會即時確認 reviewer 仍有 `maintain`／`admin` 權限、不是執行 merge 的帳號，而且 review
的 `commit_id` 正好等於目前 head。任何後續 push 都會產生新 SHA，使舊 approval 自然
失效；`CHANGES_REQUESTED`、新的 Draft 事件、未解決的 blocking comment、未完成 checklist
或 required check 仍會 fail closed。

目前設定允許的 admin `pull_request` bypass 也只能由 lifecycle 在上述
exact-head approval 成立、GitHub 回報 `mergeable_state=clean`、必要檢查逐項重驗成功，且
live bypass actor 清單精確等於 repo 宣告值時使用；其他 bypass 形狀仍降級為 human-only。
這條路徑會在最後一次 merge snapshot 前自動留下 `bypass-trace:`。沒有獨立 review 的
admin self-merge 仍必須使用取得 lease 後的 exact-head maintainer 授權留言。

### Copilot 審核模式（#752）

`.csarc/config.yml` 用兩個互不重疊的選項描述審核意圖：`admin_bypass` 可選
`off`、`beta-only` 或 `always`；`copilot_review` 可選 `allowed` 或 `off`。
`allowed` 是明確 opt-in，不是 Copilot entitlement 或額度已存在的宣告。舊的
`review`／per-level review 設定只在更新時轉成等價的 `admin_bypass`，不再是現行設定面。

- `admin_bypass: off` 要求獨立 maintainer approval；`beta-only` 只允許 beta；`always`
  同時允許 beta 與 stable。所有模式都不把靜態 reviewer 名單當作權限來源。
- `copilot_review: allowed`：Ruleset 要求 0 個原生 approval，改由
  `copilot_code_review` 規則在每次 push 後自動請 GitHub Copilot 審核，並把
  `review` 列為 required check（`.github/workflows/pr-review.yml` → `scripts/review_gate.py
  publish`）。`review` 在下列任一條件成立時通過：
  1. 獨立 maintainer 對**目前 head SHA** 的有效 `APPROVED`（沿用 #719 判斷，人工審核路徑
     仍然有效）；或
  2. Copilot 對**目前 head SHA** 的最新審核沒有任何 inline comment、內文沒有被隱藏的
     低信心意見（suppressed comments），且內文明確寫出沒有產生意見；或
  3.（#775／#826／#905／#918）這是一張符合 `admin_bypass_opt_in` 條件（PR body恰好一次
     `Admin bypass / 管理員略過審核` 標記、Milestone-less Issue 的 direct-to-main
     路由、既有 `dev/mN` Issue 路由、經 `require_routine_route()` 完整驗證的正式
     current-main delivery sync 路由、canonical `release/v*` 的同 repository
     current-main release 路由，或由 `promotion_gate.route_for()` 分類為 Milestone
     promotion 的同 repository 路由）的 admin-bypass PR，且已經有一則
     `pr_lifecycle.find_exact_head_authorization` 能找到的、綁定**目前 head SHA**
     的真人 maintainer 授權留言（跟 `pr_lifecycle.py merge` 要求的是同一則留言，
     不必另貼兩次）。

  workflow 會把判定發布成獨立的三態 check-run：Draft、尚未審核或只審過舊 head 時為
  `queued`（pending）；exact-head 審核符合上列條件時為 `success`；已留下意見、內文格式
  無法辨識或授權路由無效時才是 `failure`。發布 job 本身只在判定或 GitHub API 寫入失敗
  時失敗，避免把預期等待誤報成自動化故障。
  一般 PR 仍使用 PR base 的可信 publisher；正式 current-main sync 因為目的就是把新治理
  帶進較舊的 delivery base，改用 GitHub API 解析出的 current default-branch commit 作為
  可信 publisher。該 evaluator 仍以 exact head 與 `require_routine_route()` 驗證 sync
  branch、base、同 repository、current main containment 與雙父 topology，不執行 PR-controlled
  程式碼。
  Copilot 只會留下 `COMMENTED`，永遠不會 `APPROVED`，所以這個模式不能靠 GitHub 原生的
  approval 計數。未解決的 review thread 由 Ruleset 的 `required_review_thread_resolution`
  原生擋下。Draft PR 不審核，`review` 維持 pending 直到 PR 標為 ready。`.github/workflows/
  pr-review.yml` 額外監聽 `issue_comment: [created]`（篩選成 PR 上、內文開頭是
  `PR lifecycle merge authorization` 的留言）：貼授權留言本身不會觸發 `pull_request`
  事件，沒有這個 trigger，第 3 條路徑就要手動 `gh run rerun` 才會重新檢查。

本機修正迴圈（由本機 agent 修，不使用 Copilot coding agent）：

1. `python3 scripts/review_gate.py status --repo <owner/repo> --pr <N>` 取得 Copilot 對目前
   head 的意見與尚未解決的 thread。
2. 修正、push；每次 push 產生新 head，Copilot 自動重新審核。回覆並 resolve 已處理的 thread。
3. 重複直到 `status` 回報 `copilot.state = clean`，`review` check 轉綠。
4. 依上方 single-writer 規則取得 lease，`scripts/pr_lifecycle.py merge` 以
   `authorization_source=copilot` 合併；lifecycle 在合併前重新驗證同一個 exact-head
   Copilot 審核、required checks、Draft、checklist 與 lease，並自動留下
   `copilot-review-trace: review=<URL> head=<SHA> actor=<login>`（admin bypass 另外留下
   `bypass-trace: ... reason=exact-head-copilot-review`）。

自動合併由本機 agent 經 lifecycle 執行，不用 workflow 的 `GITHUB_TOKEN` 合併：
`GITHUB_TOKEN` 的合併不會觸發後續 `push` workflow（例如 release），也會繞過 lease；
本 repo 所屬 organization 也封鎖原生 auto-merge（#557）。

前提與限制：repo 需要有啟用 code review 的 Copilot 授權，每次審核消耗 premium requests
（取代 #241 的部分暫緩結論；Copilot coding agent 仍暫緩）。沒有授權或額度用盡時 Copilot
不會審核，`review` 維持 pending，只能走 maintainer approval。Copilot 沒有意見不等於沒有缺陷，
這是維護者 2026-09-18 接受的取捨。系統不會從 Free／Pro／Team／Enterprise 方案名稱推測
Copilot 是否可用；能力只以實際 review／API 結果判斷。切回純人工審核：把
`copilot_review` 改成 `off`，再由
管理員執行 `./scripts/apply-repository-settings.sh plan`／`apply`／`check`。

`gh pr merge --admin` 只能用來繞過文件明列的已知例外，目前有兩項：

1. `pr-policy.yml` `title` job 的「Validate Milestone approval」step（要求非提案者在
   #440 留言）在 #512 解決前的過渡期。繞過前必須先確認同一個 `title` job 的
   「Validate pull request policy」step 本身是 success，不能只看整個 job 或整個 PR
   的 conclusion 就一併略過——用 #513 的 `scripts/check-pr-policy-status`（完成前，
   改用 `gh run view <run-id> --log | grep -E "Validate pull request policy|##\[error\]"`
   手動確認）。
2. Ruleset 的 self-approval 結構性卡點，見下方「Admin bypass」與發布通道規則。

**`--admin` 本身不足以繞過任何 Ruleset 規則。** 舊版 classic branch protection 會自動
給 repository admin 身分繞過，但 Ruleset 只認 `policies/rulesets.json`（或本節後述
拆分後的第二個 Ruleset 檔）頂層 `bypass_actors`（不在 `rules` 陣列內）明列的項目；
沒有對應 `bypass_actors` 項目時，`--admin` 對 Ruleset 直接無效，merge 會被拒絕（#580
的既有踩坑：`gh pr merge --admin` 對新版 Ruleset 也不生效，不像舊版 classic branch
protection 那樣自動給 admin 身分繞過）。

### 已取代：Alpha 自我核准 bypass（#580）

> 本節保留歷史背景。現行規則以「Beta／stable 發布通道與 admin bypass（#918）」為準。

Repository 結構性只有一個真人帳號、沒有第二人可核准時，`require_code_owner_review`／
`required_approving_review_count` 一旦透過 Ruleset 生效，任何人都無法核准自己開的
PR——GitHub 回報「Review Can not approve your own pull request」，這是 GitHub 平台
全站限制，不是本 repo 政策，review 端無法繞過。

解法是在 Ruleset 的 `bypass_actors` 加入：

```json
{"actor_type": "RepositoryRole", "actor_id": 5, "bypass_mode": "pull_request"}
```

`actor_id: 5` 經實測確認對應 repository **admin** 角色（以角色身份設定，不綁特定帳號）。
`bypass_mode: "pull_request"` 的實際涵蓋範圍比字面看起來寬：不只放寬 `pull_request`
規則本身（`require_code_owner_review`、`required_approving_review_count`），也一併
放寬 `required_status_checks` 規則——實測見 #580：required check 完全沒有產生
check-run 時，加了這個 bypass 仍可成功 merge，且不會出現「Required status check ...
is expected」錯誤，先前沒有這個 bypass 時會明確卡在這個錯誤。也就是說目前的設定等於
「alpha 期間 PR 相關規則全部不擋」，不是原本想像的「只放寬 review」。它不影響
`non_fast_forward`：force-push／history rewrite 仍被禁止。這個「alpha 期間」的暫時性
範圍其後由 #607 正式收斂為可宣告、可查核的 `release_phase` 機制，見下一節「Release
phase 與 bypass 範圍收斂」。

用這個 bypass 合併一張只卡在 self-approve、內容已獨立驗證的 PR：本機
`verify-fast`（或適用時 `verify-template.sh`）綠燈，加上另一個獨立管道（例如 review
agent）對 diff 內容做審查確認，再執行 `gh pr merge --admin`。這條路徑不依賴 hosted
CI／webhook 是否正常運作（#580 驗證過：同日 GitHub `pull_request` webhook 投遞異常
期間，仍可只靠本機驗證＋這個 bypass 完成合併）。

**這段手動程序現在只是 fallback，不是唯一路徑（#775／#826）。** 在
`copilot_review: allowed` 但帳號沒有可用 Copilot 授權額度時，符合下列任一路由的
Alpha PR 可由 `scripts/pr_lifecycle.py merge` 在 lease＋exact-head 授權留言齊全後直接
合併，不必再手動 `gh pr merge --admin`：

- direct-to-main：分支名符合
  `build|chore|ci|docs|feat|fix|refactor|revert|test/<issue>-<slug>`，精確關閉一個仍是
  open 且沒有掛 Milestone 的 Issue（#775）；
- delivery work：既有 `dev/mN` Issue route，且 Issue Milestone 與 base 相符（#775）；
- delivery sync：正式 `sync/main-to-mN-<slug>-<current-main-short-sha>` route，且
  `require_routine_route()` 已驗證同 repository、base／head 命名、current `main`
  containment 與 merge parent 拓撲（#826）。
- Milestone promotion：`promotion_gate.route_for()` 已分類為 `milestone` 的同 repository
  `dev/mN-*`／`promote/mN-*` route；既有 `title` 與 `verify` required checks 繼續驗證
  tracker、Milestone、bridge topology 與 exact candidate（#905）。
- Legacy in-flight release：#925 落地前已存在的同 repository canonical
  `release/v<semver>` route 仍可依 current `main`、exact head、candidate freshness、版本與
  檔案範圍完成（#913）；新工作不得建立這條 route，而是在原交付 PR 物化版本。

五者的 PR body 都必須恰好出現一次 `Alpha 自行合併 / self-merged` 標記。未通過上述
既有 route 驗證、不是 Alpha self-merge、或缺少綁定目前 head 的 maintainer 授權留言，
仍走原本的人工審核／fail-closed 路徑；非 canonical release、beta／early／formal 與 quota
fallback 不因 #913 擴大。

這是只在「repo 結構性只有一個真人帳號」這段 alpha 期間才成立的例外，不是長期設計；
有第二個真正的 collaborator 後應重新檢視是否移除，方向由維護者決定（追蹤於 #580）。
與 #570（`required_status_checks` Ruleset 定義修復）及 #552（Milestone 核可重新設計，
同樣處理單一真人帳號 org 的自我核准風險）相關但範圍不同。Milestone tracker Issue 的
`/milestone admin-approve` 自核（見 `docs/milestone-description.md`）是另一個獨立機制，
只適用於 Milestone 核准留言，不是同一件事，不要混用。

這個 bypass 是否要在本 repo 之外的下游生成 repo 也預設套用，不在本節範圍——公版
`template/.csarc/policies/rulesets.json.jinja` 刻意保留空的 `bypass_actors`，只有真的撞上
同一個「結構性只有一個真人帳號」問題的下游 repo，才需要自行在自己的
`policies/rulesets.json` 加上等效項目。

### Beta／stable 發布通道與 admin bypass（#918）

公開發布只有兩個通道；專案成熟度是另一條、只靠明確宣告改變的軸線：

| 通道 | 版本 | 來源 | 最低驗證組合 |
| --- | --- | --- | --- |
| beta | `X.Y.Z-beta.N` | 每張 Milestone work Issue 合併進 `dev/m*` 後 | `fast`，路徑風險可升為 `full` |
| stable | `X.Y.Z` | Milestone promotion、standalone 或 hotfix | `full` |

`alpha` 只代表發布前的本機開發，不是公開版本，也沒有 `-alpha.N` tag 或 Release。
RC 不另立階段；通過 stable 的完整門檻就直接發布 stable。Milestone 開發期間若
`main` 已有新的 stable，下一個 beta 以目前 stable 為基準重新計算，不鎖死舊 core。
即使正式 main→delivery 同步最後以 squash 合併而使 stable tag 不再位於 delivery 的
祖先鏈上，版本基準仍只取 authoritative `main` 版本面相符且 `main` 可達的 stable
tag；release intent 的 commit range 則維持從 delivery 可達的最新 tag 計算，不能把
其他 branch 的變更重複列入。

`.csarc/config.yml` 的 `project_maturity: early|formal` 只描述整個專案的成熟度。
預設永遠是 `early`；只有一張明確宣告此變更的 standalone stable PR 才能改成
`formal`。成熟度不改寫 beta/stable 通道，也不從版本號或 branch 自動推斷。

`admin_bypass: off|beta-only|always` 控制 admin 是否可用 exact-head 自我授權取代
同行核准。本 repo 設為 `always`；生成專案預設 `off`，可明確選擇另外兩種模式。
無論設定值為何，bypass 都不能略過 release-level/path-risk 選出的 suite、required
checks、候選版本檢查、remote lease、即時 admin 身分或 exact-head 綁定。實際使用由
`scripts/pr_lifecycle.py` 寫入：

```text
bypass-trace: release_level=<beta|stable> route=<beta|stable|hotfix> actor=<github-login> reason=<原因>
```

GitHub 的 Ruleset bypass 是整個 ruleset 層級的能力，因此 required checks 保持在
沒有 bypass actor 的獨立 Ruleset；review 規則才依 `admin_bypass` 決定是否包含 admin
角色。`--admin` 不是直接操作捷徑，所有自動合併仍只經 lifecycle single-writer。

### 已取代：每件工作的四層發布模型（#745）

> 以下保留歷史設計脈絡；現行行為以上方 #918 的雙通道／獨立成熟度模型為準。

發布成熟度由 Issue 的 `Release level / 發布層級` 宣告，不再是整個
repository 共用的階段開關。Milestone 工作一律繼承 tracker 的層級；子 Issue
宣告不同值時 fail closed。只有 repository collaborator 建立的 Issue 宣告
會被採信，其餘回到 `.csarc/config.yml` 的預設值。

| 發布層級 | 版本 | PR 與 Issue／Milestone 核可 | 最低驗證組合 |
| --- | --- | --- | --- |
| alpha | `X.Y.Z-alpha.N` | 可使用綁定 exact head 的自審授權 | `fast` |
| beta | `X.Y.Z-beta.N` | 需非作者同行核准 | `fast` |
| early | `0.y.z` | 需非作者同行核准 | `fast` |
| formal | `1.0.0` 起 | 需非作者同行核准 | `full` |

`.csarc/config.yml` 可開關此模組、設預設層級，也可調整各層的 review
與 verification 要求。公版 root 關閉一般工作的分層宣告、預設採 `alpha`，並把所有層級
都映射為 `self`／`fast`；新生成專案預設啟用分層且採 `alpha`，既有專案
adopt 時預設採 `beta`，兩者都可在導入時改選。Dependabot 固定當作 `beta`。發版批次由
`scripts/release_level.py release-batch` 列出上次版本以來的工作，取最高
層級交給版本規則，並寫入版本 PR 與 GitHub Release 說明。

Ruleset 拆成兩個單一責任檔案：

* `policies/rulesets-required-checks.json` 只放 required checks，
  `bypass_actors` 永遠是 `[]`。
* `policies/rulesets.json` 放 `non_fast_forward` 與 `pull_request`；admin
  review bypass 只能由 lifecycle 工具在 alpha 自審或 beta 以上 hotfix
  緊急合併時使用。

`review` required check 讀取同一份層級決定：beta／early／formal 需 exact-head
非作者 approval；alpha 可使用既有 lease 與 exact-head authorization 自審。
`verify` required check 要求的 attestation 是「層級下限」與「路徑風險」取較強者，
不會因宣告 alpha 而略過高風險路徑所需檢查。

每次實際使用 review bypass 都由 lifecycle 留下結構化記錄：

```text
bypass-trace: release_level=<alpha|beta|early|formal> route=<alpha|hotfix> actor=<github-login> reason=<原因>
```

beta 以上只有 standalone `hotfix` 可用緊急路徑：Issue 提案者必須是
repo admin，先在 Issue 留 `Admin-approve: <理由>`，再用同一帳號為當前
PR head 留 exact-head 授權並執行合併。工具會再查即時權限、授權者與
merge actor，合併後自動建立 `needs-manual-review` 事後補審 Issue。一般
beta 以上 PR 沒有這個例外。

### 已取代的全專案 release phase（#607）

> 本節以下僅保留歷史設計脈絡。#745 已刪除 `policies/project-stage.json`
> 與所有讀取點；現行行為以上方每件工作的四層決定為準。

如上一節所述，#580 記錄並落地了目前 live 已套用的 Ruleset self-approval bypass
（`RepositoryRole` admin、`bypass_mode: "pull_request"`），同時發現它的實際涵蓋範圍
比原本以為的更廣：因為 GitHub 的 `bypass_actors` 是綁在整個 Ruleset 上，沒有「只對
某個 rule type 生效」的欄位，這個 bypass 連 `required_status_checks` 都一併放寬。
#607 的問題：這個較寬的涵蓋範圍不能是永久、不分專案發展階段的事實，尤其是
required_status_checks 這種「必要檢查真的有沒有過」的保證，不該無限期依賴人工自律。

**`release_phase`** 是這個 repo 自己的整案發布成熟度宣告，寫在
`policies/project-stage.json`（`{"release_phase": "alpha"}`），只有三個合法值：
`alpha`／`beta`／`release`。它跟本 repo 既有兩個外形相似但軸線不同的「stage」概念
刻意分開，避免第三次命名碰撞——`scripts/generate_audit_trail.py` 的
`governance_stage`（alpha/beta/**stable**）分類的是「單一 PR 用哪種來源分支模式
抵達 target」，`profiles/catalog.yaml` 的 `stage` 分類的是「單一語言／工具 profile
自己的成熟度」；`release_phase` 兩者都不是，它是整個專案自己的發布階段，且第三個
值是 **release**、不是 stable。三者的完整區分寫在
`scripts/release_phase_rulesets.py` 的 module docstring。跟 `profiles/catalog.yaml`
的 per-profile `stage` 一樣，`release_phase` 是人工宣告、不是自動推斷（不從分支
模式或 semver 反推）——維護者判斷專案真的進入下一階段時，手動改這個值並送 PR。

| release_phase | required_status_checks 可否 bypass | review self-approve 可否 bypass | 使用留痕 |
| --- | --- | --- | --- |
| alpha | 可以 | 可以 | 每次使用都必須留痕 |
| beta | **不行**（必要檢查一定要真的過） | 可以 | 每次使用都必須留痕 |
| release | 不行 | 不行（bypass 整體自動失效） | N/A（bypass 已經不存在） |

`bypass_actors` 是 Ruleset 層級欄位，要達成「review 可以 bypass、
required_status_checks 不行」，必須把兩種規則拆進兩個 Ruleset：

* `policies/rulesets.json`（"CSARC protected branches"）——`non_fast_forward` ＋
  `pull_request` 規則，`bypass_actors` 帶上述 admin 角色項目。
* `policies/rulesets-required-checks.json`（"CSARC required checks"）——只有
  `required_status_checks` 規則，`bypass_actors` 永遠是 `[]`。

`scripts/release_phase_rulesets.py`（`apply-repository-settings.sh` 呼叫它的
`assemble` 子命令）依 `release_phase` 決定 `required_status_checks` 規則實際生效在
哪個 Ruleset：alpha 時把它併入帶 bypass 的 Ruleset（兩個規則一起被 bypass）；beta
起維持分離，`required_status_checks` 留在永遠空 bypass 的第二個 Ruleset。
`scripts/apply-repository-settings.sh check` 的既有 drift 比對（比較
`gh api repos/{repo}/rules/branches/{branch}` 回傳的「該分支目前有效的規則聯集」）
也相應改為比較兩個檔案 `rules` 的聯集，不管哪個規則實際放在哪個 Ruleset 物件裡。

**release 階段的自動失效是結構性保證，不是人工步驟**：`scripts/check-bypass-lifecycle`
（已接進 `./scripts/verify-fast`，每次 PR 都跑）讀取 `policies/project-stage.json`，
只要 `release_phase` 是 `"release"`，`policies/rulesets.json` 或
`policies/rulesets-required-checks.json` 裡有任何非空 `bypass_actors`，就直接
fail——逼著「release_phase 已經正式進入 release，但 bypass_actors 忘記清空」這個
狀態不可能被合併，而不是靠人記得清空。回歸測試在
`tests/test_release_phase_rulesets.py`。

**使用留痕（alpha／beta 都要）**：每次真的用這個 bypass 合併 PR，必須在同一張 PR
上、合併之前留下一行結構化訊息；#719 的 exact-head reviewed lifecycle 路徑會自動留下，
人工 `gh pr merge --admin` 則必須先用 `gh pr comment` 留下：

```text
bypass-trace: release_phase=<alpha|beta> actor=<github-login> reason=<簡短原因>
```

`scripts/check-bypass-trace <PR 編號> --repo <owner/repo>`（核心比對邏輯在
`scripts/check_bypass_trace.py`，回歸測試在 `tests/test_check_bypass_trace.py`）
查核一張已合併 PR 是否在合併時間之前留有符合格式的留痕註解；PR 未合併時回報
「尚無需查核」，已合併但找不到留痕則 fail closed（exit 1）。#719 已讓 lifecycle 對
自己執行的 exact-head reviewed merge 自動判斷並留痕；對既有或人工合併 PR 的事後掃描
（交叉核對 review／required-check 實際狀態，
`scripts/generate_audit_trail.py` 已在抓這些欄位）目前不在這個查核工具範圍內：
`generate_audit_trail.py`（#535／#564）尚未併入 `main`，屬於獨立進行中的
Milestone 13 work，本 Issue（#607）維持獨立、不依賴它；一旦它併入 `main`，可以
再擴充 `check-bypass-trace` 交叉核對哪些 PR 疑似用了 bypass。目前人工路徑的查核方式是
operator 在每次 bypass-merge 後主動對該 PR 執行這個工具確認留痕存在，跟
`scripts/check-pr-policy-status` 的用法一樣是針對單一 PR 主動查核，不是排程掃描。

這是只在「repo 結構性只有一個真人帳號」這段 alpha／beta 期間才成立的例外，不是長期
設計；`release_phase` 進入 `release` 後這整個 bypass 結構性消失。與 #570
（`required_status_checks` Ruleset 定義修復）及 #552（Milestone 核可重新設計，同樣
處理單一真人帳號 org 的自我核准風險）相關但範圍不同。Milestone tracker Issue 的
`/milestone admin-approve` 自核（見 `docs/milestone-description.md`）是另一個獨立
機制，只適用於 Milestone 核准留言，不是同一件事，不要混用。

這整套 `release_phase` 機制是否要在本 repo 之外的下游生成 repo 也套用，不在本節
範圍——公版 `template/.csarc/policies/rulesets.json.jinja` 刻意保留空的 `bypass_actors`、
不帶 `policies/project-stage.json` 或第二個 Ruleset 檔，只有真的撞上同一個「結構性
只有一個真人帳號」問題的下游 repo，才需要自行決定是否套用等效機制（沿用 #580 已
落地的判斷）。`scripts/apply-repository-settings.sh` 對這兩個新政策檔案的存在與否
是條件式判斷：檔案不存在時（所有既有下游 repo）行為與本 Issue 之前完全一致。

`scripts/pr_lifecycle.py` 的 `scan_writers`（`command_writer_violations`／
`declarative_writer_violations`）掃描 `.github/workflows/`、`scripts/`
與各自的 `template/` 對應目錄，對任何繞過 lease 直接寫入 PR 狀態的 `gh pr`／
GraphQL／REST 呼叫 fail closed；`canonical_scanner_helper` 只白名單
`pr_lifecycle.py` 自己這一支腳本（root 與 `template/` 兩份精確路徑，且逐段
拒絕 symlink）。`.github/workflows/dependabot-auto-merge.yml`（root 與
`template/.github/workflows/dependabot-auto-merge.yml`，#569 新增）曾有
`gh pr merge --auto --squash` 與 `gh pr edit --add-label
needs-manual-review` 兩處未經 lease 的寫入，因此 #602 以精確路徑暫時豁免。
#830 已移除 native auto-merge，minor／patch 改由
`.github/workflows/dependabot-merge.yml` 呼叫 `pr_lifecycle.py`；豁免只剩 major
版本更新的人工複核標籤／留言，不會授權或執行合併，也不占用共同 main lane 的
lease。`dependabot_auto_merge_exemption` 仍只正面表列兩個精確 workflow 路徑，
不是放寬 pattern 本身——換一個檔名重現同樣的 `gh pr edit --add-label` 寫法仍
會被 `scan_writers` 抓到
（回歸測試見 `tests/test_pr_lifecycle.py` 的
`test_dependabot_auto_merge_exemption_is_an_exact_path_allowlist`）。

#643 曾為 `.github/workflows/release.yml` 內未經 lease 建立版本 PR 的
`googleapis/release-please-action` 加入精確路徑豁免。#925 改成原交付 PR 在 merge 前
materialize 版本，release workflow 只發布，因此 action 與 `release_please_exemption`
已一起移除；任何 workflow 再加入同一個未租約 PR writer 都會被 `scan_writers` 擋下。

同一次調查也發現 `command_writer_violations` 本身兩個誤判：它把整份檔案接成
一個 block 比對，導致 `scripts/gh-issue-create` 裡兩句不相干的 `#` 註解（一句
提到 `` `gh issue edit` ``、另一句列出 `--milestone` 這個透傳 flag）被誤判成
「gh issue metadata write」；`scripts/validate-pr-policy`（#551 的 Milestone
安全網）組給人看的 PR 留言訊息時，用反斜線跳脫的 `` \`...\` `` Markdown code
span 描述維護者該手動下的指令，跳脫反引號在雙引號字串裡是字面字元、不是
command substitution，這段文字從未被執行，但掃描器分不出「描述指令的文字」
跟「真的呼叫」。#643 修正 `command_writer_violations`：比對前拿掉整行 `#`
註解與反斜線跳脫的 `` \`...\` `` 區段，不放寬其餘偵測範圍——沒被註解、沒被
跳脫的真實寫入仍會 fail closed（回歸測試見
`test_writer_scanner_ignores_unrelated_comment_lines`、
`test_writer_scanner_ignores_escaped_backtick_documentation`、
`test_writer_scanner_still_catches_live_writes_beside_similar_text`）。

**通則（自 #602 起生效）**：往後每新增一個 `scan_writers` 例外，都必須有
自己對應的 tracking Issue 記錄理由與範圍（不能只在程式碼註解裡說明，也不能
一次開一張 Issue 涵蓋多個例外）；且所有既有例外都要在專案脫離 beta 階段後
重新審核一次，確認當時的安全假設（例如「排隊等 required check」這類語意）
仍然成立。這不是本節唯一的例外——`canonical_scanner_helper` 對
`pr_lifecycle.py` 自身的例外也適用同一條通則，往後新增例外一律比照辦理。

### 不屬於里程碑的工作

一張 Issue 若能獨立審查、驗證與交付，且沒有共同期限、跨 Issue 相依、整批驗收或
soak／canary 需求，就不必加入里程碑。它從最新 `main` 建立 topic branch，PR 直接回
`main`，接受一般 review 與風險分級驗證，並以 `Closes #N` 在合併後結案。合併只代表
repository delivery；release-worthy 工作必須在這張 PR 仍為 Draft 時先 materialize stable
版本與 CHANGELOG，通過 exact-tree 與 current-base 驗證後才可 Ready／merge；merge 後的
release workflow 只發布，不建立第二張版本 PR。**這張 Issue
本身在合併前需要通過核可**（非提案者核准或 admin 自核），見下方「Standalone／
hotfix／release recovery Issue 核可 gate（#743）」——它與有 Milestone 的 Issue 自動
繼承 tracker 核可形成對稱，避免拆成 standalone 變成繞過批次治理的捷徑。

一般工作 branch 由 `scripts/gh-issue-develop` 建立；工具在呼叫 GitHub 前要求名稱符合
`type/<Issue>-<slug>` 且 Issue 編號一致。若錯名 branch 已存在但尚未開 PR，可用同一工具的
`--repair-from` 修復；它只接受目前 checkout 與指定 repository 相同、local／remote exact
head 一致、目標名稱不存在且沒有 open PR 的情況。GitHub 會在重新命名 open PR 的 head
branch 時關閉該 PR，因此 PR policy 保持唯讀、只回報這項限制，不取得 branch write 權限，
也不以刪除 branch 或另開 PR 偽裝成原 PR 已被修復（#932）。

若工作開始需要多張互相依賴的 Issue、共同交付日期、整批驗收、獨立環境或正式發版
決策，必須在實作前加入適當里程碑，改走 `dev/m*`；不能用 standalone 路徑繞過批次治理。

### Hotfix

Hotfix 只用於必須立即修正 `main` 的缺陷，不是一般工作的優先通道：

1. 建立沒有里程碑的 Bug Issue，Issue 只標 `hotfix`；PR 才使用由 Bug Type 推導的 `bug`
   與 `hotfix`。若內容尚不能公開，改用
   GitHub Security Advisory 的私密協作流程。
2. 從最新 `main` 建立 `fix/<Issue>-<slug>`，PR 使用 `fix(scope): summary` 並直接 target
   `main`。它仍須正常 review，且 CI 一律執行 full；不得以緊急為由跳過。
3. PR 以 `Fixes #N`／`Closes #N` 連結 Issue。合併後保留 PR、commit SHA、full run、
   rollback 說明與是否發版的決策；#401 負責一般 GitHub native 關單契約。
4. `fix` 預設表達 patch 意圖；破壞相容性時明列 `!`。Agent 在同一張 hotfix PR 物化
   stable 候選；exact-tree 驗證、PR 審查與正式成品發布任一步尚未完成前，都不能宣稱已發版。
5. Hotfix Issue 本身在合併前需要核可（非提案者核准，或 proposer 同時是 repo `admin`
   collaborator 時的自核例外，理由必填）——見下方「Standalone／hotfix／release
   recovery Issue 核可 gate（#743）」。這與第 2 步的 PR review 是兩道獨立關卡：真正
   緊急、找不到第二人核准時，admin self-approval 保證這條路徑不會因為等待核准而卡死。

### Release recovery

`release-recovery` 標籤（`policies/labels.json`）標出「`main` 缺少一次應有發版、需要直接對
`main` 提出稽核過的修正」這條路徑，與 hotfix 結構相近但目的不同：hotfix 修正 `main` 上的
缺陷本身，release recovery 修正「發版流程沒有正確完成」這件事。`scripts/promotion_gate.py`
的 `route_for()` 只在分支符合 `fix/<Issue>-<slug>`、PR 標題型別為 `fix`、target `main`，且
**沒有**同時掛 `hotfix` 標籤時，才把掛了 `release-recovery` 標籤的 PR 分類為
`release-recovery` route；`scripts/validate-pr-policy` 對同一組條件做本機可重跑的驗證，違反
任一條就擋下合併。`scripts/ci_tier.py` 讓這條路徑比照 hotfix 一律升級為 `full` 驗證分級，不
得降級為 `fast`。這一節只回答「一次 release recovery PR 如何審查後進入 `main`」；`main` 進去
之後如何算出版本、建 tag、發布 Release 與成品，是上方「Release 發版不依賴 Actions 健康度的
fallback（#589）」一節的責任，兩者是各自獨立的問題，不合併成同一節。這類 PR 連結的
release-recovery Issue 沒有 Milestone，同樣落在下方「Standalone／hotfix／release
recovery Issue 核可 gate（#743）」的範圍內，合併前需要核可。

### Standalone／hotfix／release recovery Issue 核可 gate（#743）

維護者的核准模型分兩點：(1) 有 Milestone 的 Issue，Milestone tracker 一旦核准，底下
Issue 視為已核准，不需要逐張另外核准——這是 `approval_decision()` 一直以來的行為；
(2) 沒有 Milestone 的 Issue（上方「不屬於里程碑的工作」「Hotfix」「Release
recovery」三種路徑都屬此類），Issue 本身需要核可，其工作 PR 才能合併。截至
`main@488f874` 的盤點：只有第 1 點被實作，`_pull_decision()` 在 PR 沒有 Milestone 時
直接回傳放行，讓 standalone／hotfix 路徑變成繞過批次治理的捷徑——同一件工作，放進
Milestone 要先經非提案者核准，拆成 standalone 或標成 hotfix 就不用。`#743` 補上第 2
點，且不動第 1 點既有行為。

**核可對象與語彙：**新增 `standalone_issue_approval_decision()`／`check_issue_approval()`
（CLI 子指令 `check-issue-approval --repo --issue`），核可對象是「該 PR 用
`Closes`／`Fixes`／`Resolves #N` 連結的 Issue 本身」。核可留言語彙是維護者在 Issue
#743 留言中（2026-09-18，本次實作開始前）明確決定的**獨立新詞彙**，刻意**不**沿用
tracker 的 `/milestone approve` 系列——純文字、不分大小寫、取留言第一行非空白內容：

| 用途 | 留言內容（不分大小寫） |
| --- | --- |
| 非提案者核准 | `Approve` |
| admin collaborator 自核（理由必填） | `Admin-approve: <理由>` |
| 反駁 | `Object: <理由>` |
| 解決反駁 | `Resolve: <目標留言連結或摘要>` |

理由（詳見 Issue #743 留言）：`/` 開頭的斜線指令留給 tracker 專用，這張 Issue 根本沒有
Milestone 可以「/milestone」；純文字關鍵字讓任何協作者不用先查文件就知道怎麼核准。
判斷演算法——非提案者要求、admin self-approve 的 collaborator permission 查核、反駁
／解決追蹤、#632 的 fingerprint-binding staleness——與 tracker／scope-expansion 兩個
既有 gate 結構相同。這套演算法本身抽成一個共用的 `_ApprovalVocabulary`（純資料：
`approve`／`admin_prefix`／`object_prefix`／`resolve_prefix`／`case_sensitive` 五個
欄位）與唯一一份 `_vocabulary_approval_records()` 實作（code review 發現重複實作是
維護風險後的重構）；`_approval_records()`（tracker）與 `_issue_approval_records()`
（#743）都只是傳入各自 `_TRACKER_VOCABULARY`／`_ISSUE_VOCABULARY` 的薄封裝，不重新
實作演算法本身。兩套語彙仍然刻意保持並行、互不影響——`_ApprovalVocabulary.normalize()`
確保每套語彙只跟自己的比對規則相符，兩者從不會互相誤判（`tests/test_standalone_issue_
approval.py` 的 `test_milestone_slash_vocabulary_does_not_count_on_a_standalone_issue`
鎖定這個邊界）；「不建第二套系統」在這裡指的是一套共用的判斷骨架與唯一一份演算法
實作，搭配兩份資料形式的獨立語彙定義，不是「兩套完全獨立、各自維護的程式碼」。這裡
核可的對象是**Issue**，不是 work PR 本身——
`docs/adr/milestone-scope-and-closure-reconciliation.md`「work PR 不加裝 native
required review、不延伸 `/milestone` 語彙到個別 work PR」的既有決定維持不變，PR 合併
授權仍完全是 #719／`validate-pr-policy` 的責任，兩者是彼此獨立的關卡。

`.github/ISSUE_TEMPLATE/bug.yml`／`task.yml`／`feature.yml`／`documentation.yml`
（會產生 standalone／hotfix Issue 的四個表單；`milestone-tracker.yml`／`config.yml`
不受影響，root／`template/` 兩份同步）各自補上一句提示，說明沒有掛 Milestone 的
Issue 需要另一位協作者留言 `Approve`，或提案者以 `admin` collaborator 身分留言
`Admin-approve: <理由>` 自核；有掛 Milestone 則不需要，直接沿用該 Milestone tracker
的核准。

**PR 合併前的 CI 接線：**不需要新增 workflow step——`pr-policy.yml` 既有的「Validate
Milestone approval」（呼叫 `check-pr`）與 merge queue 的「Revalidate queued
Milestone approval」（呼叫 `check-merge-group`）本來就對每個 PR／merge-group commit
執行 `_pull_decision()`；`#743` 只改寫這個函式在「PR 沒有 Milestone」分支下的行為：
從硬編碼的 `Decision(True, "This pull request is not part of a Milestone")`，改成
新增的 `_standalone_pull_decision()`。

這個函式對 PR body 的解析行為比初版更嚴謹（皆為 code review 發現後修正）：

- 先比對 PR 的 head branch 是否落在 `_AUTOMATED_PULL_REQUEST_HEAD_PREFIXES`
  （`dependabot/`、`automation/`、`release-please--`、`sync/main-to-`，與
  `scripts/validate-pr-policy` 既有的四種自動化路徑一致），符合就直接放行，不看 body
  內容。這是防禦自動化 PR body 內文「意外像」`Fixes #N` 的假陽性——例如 Dependabot
  把上游 changelog 逐字帶進 PR 說明，剛好包含這個字串。這不是「只要是 bot 帳號就跳
  過」的寬鬆規則（見 `scripts/hosted_verify_bots.py` 自己「不是只要 `[bot]` 就跳過」
  的既有先例），而是與既有四種自動化路徑完全對應的精確 allowlist。
- 再用 `_CLOSING_KEYWORD.finditer()`（不是 `.search()`）收集 body 裡**所有**相異的
  Issue 編號：找不到就放行（沒有連結 work Issue，Dependabot、release-please、
  `automation/*`、main-sync bridge 等本來就沒有連結 Issue，維持不受影響）；剛好一個
  就照常呼叫 `check_issue_approval()`；超過一個相異編號則直接 fail closed，訊息列出
  每個編號，不會像只用 `.search()` 那樣悄悄只看第一個、漏掉其餘。`scripts/
  validate-pr-policy` 已經對一般工作 PR 要求「剛好一個連結 Issue」，所以這裡的檢查
  對走完整流程的 PR 是防禦性重複；但 `check_issue_approval()` 同時也是一個獨立 CLI
  子指令，不會經過 `validate-pr-policy`，所以 `_standalone_pull_decision()` 自己也要
  正確處理這個情況，不能只靠上游的既有檢查。
- 這裡的 pattern 在形狀上接近、但不是逐字等於 `scripts/check-scope-gate` 自己的
  inline pattern：`_CLOSING_KEYWORD`（這裡用的）不分大小寫，`check-scope-gate` 的
  inline pattern 區分大小寫。目前沒有已知理由需要兩者行為不同，這裡刻意不去改動
  `check-scope-gate`（已經上線、有自己獨立測試的既有 script），留給後續視需要再統一。

找到剛好一個相異 Issue 編號後，呼叫 `check_issue_approval()`。

**Milestone-scoped Issue 不受影響：**`check_issue_approval()` 先讀該 Issue 自己的
`milestone` 欄位——有 Milestone 就轉呼叫既有的 `approval_decision()`（該 Milestone
tracker 的核可判斷），完全不套用這個新 gate，維持「Milestone-scoped Issue 不需要逐
張核可」不變。這個分支在 `_pull_decision()` 的正常流程裡理論上碰不到
（`scripts/validate-pr-policy` 已經要求 PR 的 Milestone 必須與其連結 Issue 的
Milestone 一致，PR 沒有 Milestone 時連結 Issue 也不會有），但 `check-issue-approval`
同時是一個獨立 CLI 子指令，不能假設呼叫端已經驗證過這個不變量，所以直接從 Issue 自
己的即時資料重新判斷，屬於防禦性設計，不是重複邏輯。

**核可留言到達時重新觸發 CI（code review 發現，`work-item-lifecycle.yml`）：**上面
「PR 合併前的 CI 接線」只回答「PR 事件與 merge-group 事件發生時，怎麼判斷」；但
tracker 路徑除此之外還有另一層——`work-item-lifecycle.yml` 的「Milestone lifecycle:
reconcile lifecycle and refresh PR checks」step，會把事件中的 Issue 編號與 action 傳給
`reconcile()`；只有 tracker Issue 的事件／留言、Milestone 事件，以及 Issue 移入、移出
或改掛 Milestone 時，才真正同步狀態並呼叫 `refresh_pr_checks()`。一般 work Issue 的編輯、
label 或留言會成功 no-op，不寫狀態也不刷新 PR check。符合條件的事件會把新核可（或新失
效）狀態推回其下每張 PR 的 check-run，讓 reviewer 不必等到 PR 本身有新事件才看到最新
結果。tracker 尚未核准或核准因後續編輯失效時，`reconcile` 會把 pending 結果寫回 PR
check；未解反駁與結構錯誤則寫入 failure。兩者都以 notice 回報治理狀態並成功結束已完成
寫入的背景 run；PR 上的 policy gate 繼續 fail closed。GitHub API 錯誤或狀態寫入失敗仍讓
背景 run 失敗，不會被當成等待核准。`#743` 剛落地時只做了「PR 合併前的 CI 接線」，沒有補上這
一層對稱——沒有 Milestone 的 Issue 收到
`Approve` 等留言時，`pr-policy.yml` 完全不監聽 `issue_comment`，`work-item-
lifecycle.yml` 原本的 refresh step 條件又要求 `.milestone.number != null`，所以核可
留言送出後，其連結 PR 的「Validate Milestone approval」check-run 會停在核可前的舊狀
態，直到 PR 自己發生下一次事件（push、reopen 等）才會重新算過——結果是 fail **closed
但卡住**（不會誤判成已核可，但 reviewer 看不到已經核可的事實），不是 fail open，但
違反 ADR 宣稱「與 tracker 路徑對稱」的說法。

修正：`work-item-lifecycle.yml` 新增一個步驟「Milestone lifecycle: refresh
standalone Issue PR check」，條件是 `github.event_name == 'issue_comment' &&
github.event.issue.pull_request == null && github.event.issue.milestone.number ==
null`（只在留言事件、留言對象是 Issue 不是 PR、且這張 Issue 沒有 Milestone 時觸
發——對稱於既有 step 用 `!= null` 涵蓋 Milestone 情境，這裡用 `== null` 涵蓋沒有
Milestone 的情境），呼叫新增的 `scripts/sync_milestone_state.py
refresh-issue-pr-checks --repo --issue`。新函式 `refresh_issue_pr_checks()` 掃描
repo 內所有開啟中的 PR，找出 body 的 closing keyword 涵蓋這個 Issue 編號、且自己沒有
Milestone 的 PR，對每一個呼叫既有的 `check_pr()` 重新算過並回寫 check-run；找不到符
合的 PR 就是無害的 no-op。刻意不在這裡重複「剛好一個相異 Issue」的判斷——`_standalone_
pull_decision()` 在 `check_pr()` 實際執行時已經會做這個判斷，refresh 這一層只負責觸
發重新評估，不重複下判斷的邏輯。`tests/test_journey06_workflows.py` 鎖定這個 step 的
觸發條件與呼叫指令；`tests/test_standalone_issue_approval.py` 對 `refresh_issue_pr_
checks()` 本身做單元測試（只重新整理真正符合的 PR、涵蓋一個 PR 同時連結多個 Issue、
找不到符合 PR 時的 no-op 三種情況）。

**核可綁定 Issue 目前的開啟狀態：**`standalone_issue_approval_decision()`（與
`check_issue_approval()`，皆有 `require_open` 參數，預設 `True`）比照
`approval_decision()` 對 tracker 的既有檢查——Issue 若不是 `open` 狀態就直接判定未
核可，即使先前確實有一則有效的 `Approve` 留言。這修正了 code review 抓到的一個
fail-open 漏洞：一張 Issue 在開啟狀態下取得非提案者核可後，若之後被獨立關閉（誤判為
重複、改分類等），而其 `Fixes #N` 連結的 PR 仍然開著，`check-pr`／`check-merge-group`
每次重新評估時，舊有實作仍會回傳「已核可」，等於允許在一個已經失效的核可基礎上合
併。與 tracker 路徑一樣，這裡沒有對應「完成收尾」的情境需要 `require_open=False`（那
是 tracker 專屬的 `closure_decision()` 收尾路徑），所以每個真實呼叫端都維持預設值。

**Hotfix 的緊急路徑：**hotfix 是 stable；`admin_bypass: always` 時可用
admin 例外，`off` 或 `beta-only` 時仍須同行核准。提案者先在 Issue 留
`Admin-approve: <理由>`，再在作用中的
lifecycle lease 內對 exact PR head 授權；`review` check 與合併當下都重讀 admin
權限、Issue／PR 的 `hotfix` 路徑、授權者與 merge actor。成功合併後，
`pr_lifecycle.py` 自動建立一張 `needs-manual-review` 事後補審 Issue，其內綁定
原始 Issue 理由、PR、head SHA、授權與實際合併者。非 hotfix 不得使用。

`tests/test_standalone_issue_approval.py`（與 `template/` 成對，42 案例）涵蓋：
standalone Issue 未核可時 fail closed、非提案者核可後放行（含大小寫與前後空白不敏
感）、admin 自核放行（含理由必填、非 admin 權限被拒）、反駁與解決反駁（含**反駁只能
由原作者本人用 `Resolve:` 解除，其他人代為解除不算數**）、核可後編輯 Issue 使其失效
（沿用 #632 的 60 秒緩衝窗）、**tracker 的 `/milestone approve` 語彙在沒有 Milestone
的 Issue 上完全不生效**（證明兩套語彙真的互相獨立、不會誤判）、Milestone-scoped
Issue 繼續繼承 tracker 核可不需要逐張核可、沒有連結 Issue 的自動化 PR 不受影響、
`check-pr`／`check-merge-group` 兩個既有 CI 接線點都正確套用新 gate（含**同一個
merge-group 內有多張 PR，其中一張未核可即整體擋下、其餘不受影響**的多 PR 情境）、
**Issue 核可後被獨立關閉即不再算已核可**（含 `check-merge-group` 端到端重現、
`require_open=True` 時的 happy path 不受影響、`require_open=False` 的既有防禦式選項
仍可用）、**PR body 連結多個相異 Issue 時 fail closed**（含同一個 Issue 編號重複出現
不算多個）、**自動化 PR 的 head branch carve-out**（四種既有自動化路徑各自搭配一段
「內文剛好長得像 Fixes #N」的假陽性 body，確認不受影響；一般 `fix/<n>-<slug>` head
不受這個 carve-out 影響，仍正常受檢）、`refresh_issue_pr_checks()` 本身（只重新整理
真正連結這個 Issue 的 PR、一個 PR 同時連結多個 Issue 時仍會重新整理、找不到符合 PR
時的 no-op）。`tests/test_journey06_workflows.py` 額外鎖定 `work-item-lifecycle.yml`
新增 step 的觸發條件與呼叫的 CLI 指令。

**核可留言事後被編輯的既有缺口，已由 #778 修正：**`#743` 開發期間的 code review 曾
指出 `_approval_is_stale()`（#632，tracker、scope-expansion、standalone 三條路徑共
用）只比對核可留言的 `created_at` 與 Issue／tracker 的 `updated_at`，從未讀取核可
留言自己的 `updated_at`——如果有人事後**編輯**一則已存在的留言（例如把一則不相干
的留言改成 `Approve`），staleness 判定看不出這則留言本身被動過。這不是 `#743` 新增
的問題，是 `#632` 落地時就有的既有行為，只是 `#743` 讓沒有 Milestone 的 Issue 也開
始依賴這個機制，風險面因此變大。這個缺口牽動三條路徑共用的核心機制，範圍超出
`#743` 這張 leaf Issue，當時決定不在 `#743` 分支上修，留給獨立的後續 Issue 處理。
`#778`（PR #779，standalone、無 Milestone、Alpha self-merge，已合併到 `main`）獨立
完成了這項修正：`_approval_is_stale()` 新增 `comment_updated_at` 參數，額外以 OR
判斷留言自己的編輯間隔，細節見上方「Scope-drift gate enforcement 與核可
fingerprint-binding（#632）」一節的「留言編輯本身的過期判斷（#778）」段落。`#743`
分支之後合併 `main`（經 `dev/m14-generated-project-fixes` 的 main-sync）時，直接沿
用了 `#778` 修正過的 `_approval_is_stale()`／`_approval_records()`，`#743` 自己重
構出的共用 `_vocabulary_approval_records()` 也已經正確帶入這個新參數（呼叫時傳入
`comment.get("updated_at")`），不需要在 `#743` 這張分支上重複實作。

### Promotion route 併入 PR policy（#601、#876）

#601 曾新增獨立的 `promotion` required check，補上 Ruleset 要求一個沒有 producer 的 context
而永久 pending 的缺口。#876 重新盤點後確認它與 `title` 使用相同事件、trusted base checkout、
權限與生命週期，而且唯一額外工作只有 `scripts/promotion_gate.py check-route`。因此 route classifier
現在是 `title` job 內的一個 step，Ruleset 不再要求第四個 `promotion` context。這省掉一個 runner job，
但沒有刪除 route 判定。

`check-route` 仍重用交付流程的 `route_for()` 分類器。`pull_request_target` 直接從 webhook payload
讀取 base／head／labels；合法的一般或交付路由成功，target `main` 卻不符合任何已知路由時 fail closed。
`merge_group` 則辨識為 merge queue。workflow 一律 checkout trusted base，候選 PR 不能改寫分類器來
自我核准。

`title` 同時負責 Issue、Promotion checklist、scope 與 Milestone approval 的唯讀判定；正式 Milestone
交付仍由 `promotion_gate.py prepare/finalize` 產生與驗證證據。`.github/workflows/milestone-lifecycle.yml`
的 `Milestone approval` 是 comment refresh 用的非 Ruleset check，由 #875 另行處理，不在 #876 偷改其
觸發或狀態語意。

### Required check producer 綁定（#835）

Ruleset 對 `title`、`verify`、`review` 不只比對 context 名稱，也逐項綁定 GitHub Actions
App integration ID `15368`。設定缺少 ID、ID 格式錯誤或 live readback 不完全相同時，repository settings
檢查與 PR lifecycle 都 fail closed；同名 classic commit status 不再能滿足 required context。

App 身分本身仍不足以區分同一 repository 內由 PR 控制的 workflow。三個 required-name job 因此只由
base-trusted `pull_request_target`、既有的 default-branch review 事件或 `merge_group` 載入 workflow
定義。lifecycle 對每個 exact-head check run 再核對名稱、App、check suite、Actions run repository、workflow
path 與允許事件；只借用可信 run 的 `details_url` 也無法拼接成有效證據。PR policy 與 review 只 checkout
可信 base 並維持唯讀權限；CI 沒有 secret 或寫入權限，雖會讀取 proposed head 來驗證聲明，但驗證證據本身
的不可偽造性仍由 #834 負責。

### Gate owner 盤點（#876）

| 邊界 | 唯一 owner 與失敗模式 | 結論 |
| --- | --- | --- |
| Path／release-level 分類 | `ci_tier.py` 與 `release_level.py` 決定要跑 `fast` 或 `full`；未知路徑與高風險交付 fail closed | 保留，但把沒有獨立執行內容的 `baseline`／`docs` 正規化為 `fast` |
| PR policy | `title` 驗證 Issue 關係、metadata、scope、Milestone 與 delivery route | 保留單一 job；`promotion` classifier 併入此處 |
| Candidate verification | `verify` 在 trusted runner 對 exact tree 執行 risk-owned suite | 保留，不能由本機結果或 policy check 取代 |
| Review | `review` 驗證 exact-head self／peer／Copilot 決定與未解決 thread | 保留，不能由測試結果取代 |
| Acceptance checklist | Issue 定義工作完成條件，PR checklist 定義這次交付包裝與 metadata | 保留，兩者範圍不同；draft 期間不要求完成 |
| Trusted evidence | 驗證 repo、head/tree、tier、scopes、command、toolchain、runner、結果與 freshness | 保留，阻止舊 run、錯誤 runner 或錯誤候選被重用 |
| Merge writer | remote lease 加上合併前 snapshot revalidation | 保留，避免兩個自動 writer 同時改寫 mutable PR 狀態 |
| Milestone comment refresh | 非 Ruleset 的 `Milestone approval` check 只處理核可留言後重新計算 | #875 已有獨立 ownership；#876 不重複改動 |

這份盤點的刪減標準是「是否產生別層無法取代的證據」，不是 gate 名稱或歷史存在時間。

### 本機與 hosted 驗證模式（#908）

新專案預設 `verification_mode: local`；既有 repository 沒有此欄位時維持 `hosted`，避免更新時靜默降低保護。兩種模式共用同一個 `ci_tier.py` router，以及同一組 focused／fast／full 驗證入口；切換模式不增加第二套 runner、matrix 或測試清單。

`local` 模式不產生 `ci.yml`、`pr-policy.yml`、`pr-policy-writes.yml`、`pr-review.yml`、reviewer assignment、spec sync、work-item lifecycle、Pages、OSV、CodeQL、Docker scan、Dependabot auto-merge、release 或 release-drift workflow，required-checks Ruleset 與 Pages policy 也保持 disabled，因此不會建立永遠等不到的 check、在 `main` 重跑完整驗證或製造無意義告警。Issue／PR／Milestone 操作改用既有本機 wrapper；外部協作者若直接在 GitHub UI 修改 metadata，local mode 不會即時自動修正，只能由人工或可選的低頻 governance drift check 發現。repo-local 發版工具仍保留，需要可信 release provenance 或 Pages deployment 時先切換成 `hosted` 再更新模板。fast／full 成功後只做常數時間的 metadata 寫入：已 commit 且 clean 的候選會把 exact head/tree、base、tier、scopes、command、success 與 24 小時 freshness 綁到 Git metadata；尚未建立 commit 或仍有未提交修改時，測試結果維持成功但不產生可合併的證明。`pr_lifecycle.py` 在 merge 前重新讀取 GitHub metadata、review、lease 與這份證明，執行既有 PR policy checker，並留下清楚標為 `self-attested-local` 的 trace，再使用受控 admin bypass。

hosted 模式仍保留 required `verify`／`title`／`review`。實作中與一般 push 前只跑變更 owner 的 focused checks；`verify-fast` 是可選的廣泛診斷，不因 trusted plan 選到 `full` 就再於本機跑一次 aggregate suite。required `verify` 在 exact candidate 執行所選 fast／full，並提供唯一的正常 merge evidence；本機 full 只留給本文件明定的 Actions／發布 fallback 或明確診斷，且不會在 fallback 邊界外取代 hosted evidence。Draft 的 CI、policy、review 與 reviewer assignment 都在 runner 前略過；`PR policy writes` 只接續上游 `success`／`failure`，不為 `skipped`／`cancelled` 開 runner。Pages 只在 `documentation_mode: template-and-content` 時產生，採 Actions deployment，僅回應 `docs/**` 變更或手動 dispatch。`policies/pages.json` 的 `enabled` 是維護者的 desired-state 選擇，不是能力判定：public repository 在 GitHub Free 可以發布 Pages，但不代表必須發布；`enabled=true` 時 `plan` 顯示 ENABLE／UPDATE／NO-OP，`enabled=false` 是明確 opt-out，live 仍已發布時顯示 DISABLE，`check` 雙向比對 desired 與 live，`apply` 依同一動作建立、更新或停用站台後再以 `check` 讀回（#985）。private repository 缺少 GitHub Enterprise Cloud 時仍回報 `DEGRADED`，無法判讀的 Pages API 錯誤一律失敗，不視為已發布或 compliant。`release_trigger: manual` 完全不註冊 push trigger；本模板 root 採此設定。

這份本機證明能防止誤拿舊結果、錯誤 branch／base、測完又改檔或跑錯 tier，但不能防止有寫入權限的人偽造 JSON，也不能證明 GitHub event／權限、第三方服務、實際部署、遠端 runner 或 release provenance。local mode 不把這些項目標成成功；需要這些信任性質時，改成 `verification_mode: hosted`，更新模板並重新套用 repository settings。切換到 hosted 後，下節 #834／#835 的規則完整生效。

### `verify` 的可信 hosted execution evidence（#834）

#834 supersede #661 將 unsigned commit trailer 當作 required evidence 的設計；#661 希望保留低成本本機回饋
的目標不變。`scripts/verify-fast`、`scripts/verify-template.sh`（生成 repo 是 `.csarc/scripts/verify`）仍是本機與
hosted 共用的驗證入口，但本機執行只提供開發回饋，不改寫 commit，也不能單獨滿足 merge 或 release gate。

`.github/workflows/ci.yml` 的單一 `verify` job 由 base-trusted `pull_request_target` 或 `merge_group` workflow
定義執行。它先保存 base 版本的 verification policy scripts，再 checkout exact candidate；因此 PR 不能靠修改
自己的 router 或 evidence validator 降低 tier。一般新 head 接著在 GitHub-hosted `ubuntu-latest` runner 安裝固定
工具鏈，依可信 plan 實際執行 `scripts/verify-fast` 或 full verifier。Dependabot 與一般 contributor 共用同一路徑，
不再有 bot 白名單。

`verify` 的 job-level guard 在 runner 排程前排除 Draft PR 活動與不會改變 tier 的 label 事件。轉成 Ready、
非 Draft 的新 head／`edited`、`promotion`／`hotfix`／`release-recovery` label、merge queue 與手動執行仍會啟動；
label payload 缺少名稱或事件無法可靠分類時也預設執行。這個 guard 只節省非必要 runner，不產生可信成功證據，
也不改變下方 exact-head 驗證條件。無關 label 的 skipped job 使用非 required 名稱，既有同-head `verify`
成功或失敗仍是 authoritative result，不會被 skipped conclusion 覆蓋。

`scripts/check-trusted-verification` 與 `scripts/verification_evidence.py` 消費 GitHub Check Runs、Actions run 與
Jobs API，並重用 `scripts/pr_lifecycle.py` 的 required-check producer selector。有效證據必須同時符合：

1. required check 名稱與 Ruleset GitHub Actions App integration ID 完全相同；
2. check、check suite、Actions run 與 job 綁定同一 repository、exact head SHA、可信 workflow path/event 與
   run attempt；
3. job 由 GitHub-hosted `ubuntu-latest` runner 執行，routing 與選用工具鏈步驟成功；
4. 唯一 execution／same-head reuse／clean-sync step 內的 tier、scopes、tree、command、base SHA、label set 與
   release level 相互一致，且 tree 等於 exact head 的 Git tree；
5. check、run、job 與 execution step 都真正 `success`；`neutral`、`skipped`、zero-step 或同名 classic status
   均不能滿足 `verify`；
6. 完成時間不超過 24 小時，且不能超前目前時間超過 5 分鐘。

quota fallback 永遠不能替代缺少或失敗的 `verify`。新專案預設 `actions_fallback: off`；只有明確設為
`admin`，且 exact head 已有上述可信成功證據時，其他確認為 GitHub billing zero-step 的 required check
才可沿用 quota fallback。真正執行失敗或狀態未知仍 fail closed。Ruleset 的 admin bypass 無法把來源 check
改寫成成功結果，因此這是刻意保留的唯一預期紅燈例外，不得用合成綠燈掩蓋「實際上未執行」的事實。
這項例外只在帳務失敗時有效，所以 lifecycle 必須重驗 exact head／base、review policy、適用本機 suite、
remote lease 並留下 bypass trace。release 先解析唯一 merged-main source
PR，且只有 main tree 與 source head tree 完全相同時才重用證據；來源不唯一、tree 漂移、證據過期或任何欄位
無法驗證時，release workflow 對 exact main tree 重新執行 hosted full verification，而不是退回 unsigned
trailer。

workflow 的可信 base 定義固定 entry command 與 setup steps；被驗的 script／tests 則屬 exact candidate tree，
與一般 CI 相同，仍由 review、CODEOWNERS 與 required checks 防止惡意弱化。這個邊界不宣稱 candidate 自己的
測試內容不可修改，只證明可信 runner 確實對該 exact tree 執行 workflow 指定的 command/toolchain 並成功。

### Risk-owned execution 與有限證據沿用（#812）

單一 `verify` required context 保持不變，不新增 path-filtered workflow、matrix runner、stage registry 或跨 commit
evidence DAG。路由只使用既有 `ci_tier.py` scopes：docs-only 不啟動 Python environment／regression；dependency-only
只跑鎖檔與 OSV owner；workflow／shell／template 直接跑 workflow 與 shell lint，workflow／template 另驗 action
pins；source、template、governance、shell、workflow 與 unknown 維持 Python safety floor。所有真正的 Copier
create／adopt／update subprocess 與代表性 Rust native 驗證只在 full suite 執行；fast 保留不需真 render 的
安全、狀態與資料保全回歸。

root `verify-fast` 直接重用 plan 已算出的 scopes，不另判斷 tier。它一定納入本次直接修改的 `tests/test_*.py`
與存在的同名 `scripts/foo.py → tests/test_foo.py`；再依 source、template、governance、workflow、shell 加上固定的
核心 owner 檔案。多個 scope 取聯集並去重，unknown 則回到完整 `tests/` fail closed。docs-only 與
dependency-only 不啟動 pytest；生成 repo 測試量本來就小，仍對自己的 product tests 執行 `not large`。

| 事件／邊界 | `verify` 行為 |
| --- | --- |
| Draft PR 活動（opened／reopened／synchronize／edited／labeled／unlabeled／converted-to-draft） | job-level guard 在 runner 前略過；skipped／zero-step 不構成可信 `verify` 證據 |
| `ready_for_review`（同一 head） | 一律啟動，重新解析 release level、tier、scopes；若需要 full 就在該 exact head 執行 full |
| 非 Draft 新 head（opened／reopened／synchronize） | 不跨 commit 沿用結果；按新 diff 的 scopes 執行 |
| 非 Draft `edited` | 啟動並重新解析 release metadata 與完整 route；所有 evidence identity 欄位相同時才可一跳引用原始 hosted Execute |
| 非 Draft `labeled`／`unlabeled` | 只有事件本身變動 `promotion`／`hotfix`／`release-recovery` 才啟動 required `verify` 並重算 tier；其他 label 只留下非 required skipped check、不啟動 runner，缺少 label name 則 fail closed 執行 |
| 無衝突 `main → dev/m*` sync | 先以可信 base script 驗 authorization route、live refs、雙親順序與自動 merge tree，再直接引用 current main 對應來源 PR 的 fresh full Execute |
| 衝突／人工整合 sync | 同樣先驗 route、live refs 與雙親；不沿用 main tree，改跑 affected owners 與 fast |
| Promotion／hotfix／merge queue／manual dispatch | 對 exact final head 執行 full |
| Release | 只消費 exact-tree full evidence、artifact、SBOM 與 immutable-release 驗證，不重跑測試 |
| 協調器輪詢、cleanup、archive | 只讀狀態或做生命週期清理，不執行測試 |

沿用只允許一次：reuse step 必須直接指向原始 Execute 的 run／job／check，不能再指向另一個 reuse。來源證據
的 24 小時 freshness 以原始 Execute 完成時間計算；任何欄位不符、來源缺漏、來源本身是 reuse，或新 commit
即使碰巧有相同 tree，都回到正常執行或 fail closed。工具與相依套件可用既有 cache，但 cache 不是 required
test result。現階段只實作完全相同的 effective tier／scopes 沿用；較高 tier 或 scope 超集合覆蓋留待有實測需求
時再做，避免在 #812 引入另一套依賴圖。

same-head reuse 與 clean-sync 的 step 使用固定名稱；可信 workflow 透過 workflow command 在該 check 寫入
一筆版本化的 JSON notice annotation，承載 route identity、原始 Execute 的 run／job／check ID，以及 sync
專屬的 main SHA。consumer 只接受唯一且 schema 完整的 annotation，再依上述契約遞迴驗證 direct evidence。
GitHub API 若回傳未展開的 step-name expression、重複 annotation、未知欄位或任一 identity 不符，一律
fail closed；不把顯示名稱當資料通道（#964）。

同步結構預檢位於工具鏈安裝與 verifier 之前。分支名稱只決定「需要檢查」而不構成授權；可信 script 仍核對
PR route、requesting PR、base/head SHA、`[base, main]` 雙親與 tree。這可讓錯誤拓撲在秒級失敗，避免先跑 full
才由 merge lifecycle 發現。clean sync 的 required check 仍綁定自身 exact repo/head/tree/run/job/App 與來源
main full Execute；manual/conflict 路徑則不借用 tree 證據。

#852 run `35556649274` 是本次刪減前的固定 full 成本證據：full regression 652 秒、其中 pytest 631 秒；其他
stages 合計約 14 秒。重複 real-template 工作主要來自 #739 update 66.27 秒、#744 update 55.43 秒、legacy
two-file update 55.10 秒、#743 update 53.57 秒、Python／TypeScript／Rust adoption 42.66／40.76／30.69 秒、
representative generated full 31.99 秒與 fixed-ownership adopt 23.42 秒。#812 以 generic previous-release update、
代表 create（含 Rust）與代表 adopt 收斂成功 lifecycle canary；不為 #742 增加語言 × lifecycle 矩陣。

回歸測試集中在 `tests/test_verification_evidence.py`、`tests/test_pr_lifecycle.py`、
`tests/test_journey03_ci.py`、`tests/test_journey07_release.py` 與 `tests/test_promotion_gate.py`；涵蓋偽造 trailer
不構成輸入、錯誤 repo/head/tree/tier/command、過期證據、不可信 runner、quota 與 release reuse。

### 歷史決策：unsigned 本機聲明與 bot 例外（#661／#753，已由 #834 supersede）

#661 曾為降低 hosted 成本，讓本機驗證成功後把 tree、tier 與時間寫入 unsigned commit trailer；#753
再為無法產生該 trailer 的 Dependabot 加入 hosted 白名單。#834 證實 contributor 可自行計算並偽造整份
聲明，因此移除 trailer consumer、writer 與 bot 特例。保留的決策只有分級入口與本機快速回饋；required
merge／release evidence 一律改用上節的可信 hosted execution。

### 建立新 `dev/m*` delivery 分支（#754）

`CSARC protected branches` Ruleset 的 `conditions.ref_name.include` 涵蓋 `refs/heads/dev/m*`，讓每個
Milestone 自己的 delivery 分支（`docs/index.html` Journey 01／`AGENTS.md` 工作迴圈第 8 步）跟 `main` 一樣
受保護。但 `required_status_checks` 規則預設在**建立分支這個動作本身**就要求 `title`／
`verify`／`review` 全部先通過——一個尚不存在的新分支在建立當下沒有任何 commit 或 PR 能觸發這些 check，
`required_status_checks` 在這個情境下永遠無法被滿足：任何符合 `dev/m*` pattern 的全新分支都無法直接
`git push` 建立，僅有的 `bypass_actors`（admin，`bypass_mode: "pull_request"`）又只在「透過合併 PR」時生
效，而建立一個全新分支不可能先有一個以它為 base 的 PR，兩者互為前提、無路可通。

修法是 GitHub Rulesets 原生就為這個情境準備的欄位：`required_status_checks` 規則的
`do_not_enforce_on_create: true`（`policies/rulesets-required-checks.json`；生成 repo 對應
`template/.csarc/policies/rulesets.json.jinja` 同一個規則區塊；這項行為由可信 Issue／Milestone route 決定，因
為這個欄位只影響「這個 ref 第一次被建立的那個瞬間」，跟審核模式或是否啟用 `dev/m*` 無關）。這個欄位**只**
放寬 ref 第一次出現的那一刻；建立之後對這個分支的每一次 push、每一張 PR、合併進它或它合併出去，仍然要通過
上面列的全部 required checks，跟 `main` 完全一樣——不影響、也不繞過 `main` 既有的任何保護，因為 `main` 從
未經歷「被建立」這個事件。

`scripts/apply-repository-settings.sh` 的 drift-check 原本只比對 `required_status_checks` 的 context 清
單，沒有比對 `do_not_enforce_on_create`；本次一併補上這個比較（desired 要求時，live 沒有同步設定就回報
`do_not_enforce_on_create is not enforced`），讓 `check` 真的能證明「新分支建得起來」這件事，而不只是證明
check 清單對得上。

**回歸驗證**：`tests/test_apply_repository_settings.py` 的
`test_do_not_enforce_on_create_matching_passes_cleanly`／`test_missing_do_not_enforce_on_create_is_reported`
涵蓋 drift-check 邏輯本身；`do_not_enforce_on_create` 是否真的送進 assembled payload，見
`scripts/release_phase_rulesets.py assemble` 的既有輸出（純函式，不需要 live API）。live 分支建立本身無法
純單元測試（需要真的對 GitHub 送出請求），驗證步驟改為文件化的手動步驟：管理員執行
`./scripts/apply-repository-settings.sh apply` 套用新設定後，對一個目前不存在、符合 `dev/m*` pattern 的分
支執行 `git push origin main:refs/heads/dev/m<N>-<slug>`（或等義的 `git branch` + push），成功建立且不報
`required status checks` 錯誤即為通過；同一次操作後，對 `main` 或既有分支做一次不通過 `verify` 的 push 仍
應被擋下，確認既有保護未受影響。

### Dependabot 依賴更新的發版與 template 同步（#755）

**`uvx --from git+...@<sha>` 不吃 `uv.lock`（實測，2026-09-18）**：本機對 `git+file://` 本地來源、當下
`pyproject.toml` 宣告 `copier>=9.17,<10`、`uv.lock` 鎖定 `copier==9.17.2` 的狀態實測
`uvx --from "git+file://<repo>@<sha>" python -c "import copier; print(copier.__version__)"`，實際裝出
`9.18.2`（範圍內當下最新版），不是 lock 檔鎖定的版本。結論：`uvx --from git+URL@<sha>` 安裝時直接依
`pyproject.toml` 的版本範圍重新解析，不讀取目標 repo 的 `uv.lock`——`uv.lock` 只服務這個 repo 自己的
`uv sync`／`uv run` 情境。

因此 root 的 `.github/dependabot.yml` 的 `uv` 區段**維持現行 `build(deps)` 前綴，不區分 runtime／dev 依賴**：
一般（非安全性）runtime 依賴的版本 bump，只要新版本仍落在既有範圍內，`uvx` 使用者下次執行就會自動拿到最新
版本，`build(deps)` 造成「release-please 不升版號」不影響實際交付結果，強改前綴只會製造不必要的版本噪音。
只有當修正需要**改動 `pyproject.toml` 本身宣告的版本範圍**（例如提高下限排除某個已知有漏洞的版本區間）才會
影響「使用者手上那個 `<approved-full-commit-sha>`」是否要更新，而那是修改 `pyproject.toml` 這個動作本身的
事，不是 Dependabot commit 前綴能解決的問題。`template/.github/dependabot.yml.jinja` 不受此結論影響：由
CSARC 接管發版的下游專案是被 `uv sync --locked` 消費的一般服務／應用，`uv.lock` 對它們是真的有效力的鎖定，
runtime 依賴觸發 patch 發版的既有邏輯繼續適用——`release_ownership == 'csarc-owned'` 時，`uv`／`npm`／
`cargo` 三個 ecosystem 區塊各自加上 `commit-message: {prefix: fix, prefix-development: build}`（Dependabot
原生欄位，依它自己對「這個依賴是不是 development dependency」的判斷選前綴，不需要額外邏輯）；
`product-owned`／`verification-only` 不加這段，維持 Dependabot 預設的 Conventional Commits 偵測。
`github-actions` 區塊完全不受影響，維持不觸發發版。

**root／template 的 Actions 版本同步**：比較過兩個方案——擴大 Dependabot 監看目錄到 `template/`，或在同一張
PR 內自動同步——選擇後者，理由記錄於本 Issue 討論（維護者 2026-09-18 核准）：前者會對「跟 root 逐位元組相同」
的 paired workflow 開出**兩張獨立、不保證同時落地**的 bump PR，其中一張先合併就會讓另一張的
`sync-paired-files.sh --check` 回報 drift、卡住合併，是持續性而非一次性成本；且不管選哪個方案，Dependabot
都讀不懂 `.jinja` 語法，凡是模板化（非逐位元組 paired）的 workflow（如 `ci.yml.jinja`）永遠不會被它掃到，
都需要另一套靜態一致性檢查。

實作：

1. `.github/workflows/dependabot-auto-merge.yml`（root 與 `template/.github/workflows/dependabot-auto-merge.yml`，
   本身也是 paired 檔案）新增 `sync-template` job。#830 將這條具寫入權限的路徑改為
   `pull_request_target`，所以 workflow 與 synchronizer 都固定取自可信任的 base SHA；PR head 只作為資料，
   不提供可執行程式碼。唯讀的 `authenticate-dependabot-head` job 會重新讀取目前 PR head，先要求 live base SHA
   與觸發事件的可信 base SHA 完全相同，再驗證 opener、同 repo branch 前綴、GitHub API 對 commit 的
   `dependabot[bot]` author、`web-flow` committer、有效 GitHub 簽章、
   單一 head commit 全部成立，並只允許 `main` 上 `dependabot/github_actions/main/*` 分支修改 root
   `.github/workflows/` 內既有 YAML。同步後 PR 若關閉再重開，current head 會是 unsigned
   `github-actions[bot]` child；這個例外不靠顯示名稱放行，而是先驗證其 parent 為上述 Dependabot commit，再
   用 parent 原始 base 的 trusted synchronizer 重建完整 Git tree，tree hash 完全相同才通過。任一條件不符就
   不啟動寫入 job。

   寫入 job 只執行 base checkout 內的 `scripts/sync-paired-files.sh`，同步結果只能是本次已驗證 root workflow
   對應的 `template/.github/workflows/` 檔；其他 staged 或 untracked path 一律失敗。push 使用已驗證的 bot ref 與
   exact-SHA `--force-with-lease`，若遠端 head 在驗證後移動就失敗，不會改寫新 head。有 drift 才 commit 並 push
   回同一個分支；push 觸發的新 `synchronize` 事件會讓 `verify`（#834）在可信 runner 對新 head 重新驗證。workflow 的
   concurrency 以 PR 編號串行且不取消進行中的 run，所以同步 producer 能完成，而下一個 head 事件一定在前一個
   run 後處理。minor／patch 只為沒有被 sync push 取代、且已完成上述驗證的 exact head 產生
   `dependabot-merge-eligible` check；它不是 Ruleset required context，也不能單獨授權合併。

   `.github/workflows/dependabot-merge.yml` 從 default branch 接續 `CI`／`PR policy`／`PR review`／上述 eligibility
   workflow 的 completed event。它先以唯讀 required-check 狀態避免提早取得 lease，再由
   `scripts/pr_lifecycle.py acquire → check → merge` 重新驗證 live PR、Bot account type、同 repo ref、current commit
   簽章（或 exact sync-child parent）、eligibility check 的 GitHub Actions App／workflow／event、review、Ruleset 與
   required checks；`check` 與 `merge` 都重新讀取同一份 mutable state，REST merge 另帶 exact `sha`。任何漂移都
   fail closed，且不建立 GitHub 原生 auto-merge 的 persistent PR state。Actions token 的 merge 不會產生新的
   `push` workflow，因此 `release_ownership: csarc-owned` 成功合併後明確 dispatch repository-owned `release.yml`；
   不猜測或 dispatch product-owned workflow。

   同步 commit 的訊息固定用 `fix(deps): ...`，不是 `chore:`——完成條件第五項要求「會改變 template/ 內容的
   依賴更新，合併後要進入下一次發版」，`release-please`（`release-type: simple`）只認 `fix`／`feat` 升版號；
   這裡只在 `sync-paired-files.sh` 真的找到 drift（代表這次 bump 確實改到 `copier update` 會下發的內容）時
   才 commit，所以是精準只對「真的動到 template 分發內容」的那次 bump 觸發發版，不會連帶讓每一張跟 template
   無關的 Dependabot commit 都被迫升版號。
2. 新增 `scripts/check_action_pins.py`（root 與 `template/.csarc/scripts/check_action_pins.py` 逐位元組同步）：掃
   `.github/workflows/`、`template/.github/workflows/` 底下所有 `.yml`／`.yaml`／`.jinja` 檔案的
   `uses: owner/repo@sha` pin，同一個 action 在整個 repo 裡的 pin 必須完全一致，不一致就 fail closed 並點名
   哪個檔案落後、目前多數版本的 pin 是什麼。這是**跟 Dependabot 白名單無關**的獨立不變量檢查，專門補
   `.jinja` 這塊 Dependabot 結構性掃不到的缺口。掛進 `scripts/verify-fast`（`workflow` scope 時執行）與
   `scripts/verify-stage-github-actions-audit`（`verify-template.sh` 的一部分，跟 zizmor 同一階段）。
   建置過程中這支腳本立刻抓到一個真實既有 drift：`template/.github/workflows/release.yml.jinja` 的
   `anchore/sbom-action` 停在 `v0.24.0`，root 的 `.github/workflows/release.yml` 已經是 `v0.24.2`；已在本
   PR 一併修正到與 root 一致。

**回歸測試**：`tests/test_check_action_pins.py`（pin 一致／不一致回報／不同 action 互不干擾／檔案掃描範圍／
CLI fail closed 五個案例，root 與 `template/tests/test_check_action_pins.py` 逐位元組同步）。`sync-template`
的 trust boundary 由 `tests/test_authenticate_dependabot_head.py` 驗證 head 身分、簽章與 changed-path allowlist，並由
`tests/test_dependabot_auto_merge.py` 驗證 base-code checkout、authenticated head checkout 與 exact-ref push。
實際 GitHub push 行為仍待合併後第一張真的改到 paired workflow 的 Dependabot PR 驗證並回填證據。

## Current automation

下表逐項列出 canonical file、owner、觸發（輸入）、權限／timeout、產物（輸出）、測試與
最新 live evidence；檔案存在或舊 run 成功不單獨算 active——見 Dependency vulnerability
與 Work Issue closure 兩列的落地與失敗證據。Live evidence 以 2026-09-01 對
`Innoguard-Cyber-Arch/csarc-repo-template` 的 `gh api actions/workflows` 與
`gh run list` 查詢結果為準；重跑本盤點請重新查詢，不沿用本表數字。

| 能力 | Canonical file | Owner | 事件（輸入） | 權限／timeout | 產物（輸出） | 測試 | 最新 live evidence | 狀態 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CI | `.github/workflows/ci.yml` | 驗證分級（#392／#403／#428／#812）；可信 hosted execution（#834）；runner guard（#901） | `pull_request_target`、`merge_group`、`workflow_dispatch`；Draft 活動與無關 label 由 job guard 在 runner 前排除，Ready、非 Draft code／edited 與三種 tier label 保留 | `actions`／`checks`／`contents`／Issues／PR read；30 分鐘；同一 PR 新 commit 取消舊 run | base-trusted `scripts/ci_tier.py` 分類後，在 GitHub-hosted `ubuntu-latest` 對 exact candidate 執行 risk-owned `scripts/verify-fast`／full verifier；同 head 的 `edited`／tier-label run 可單跳引用相同 route 的原始 Execute，且只有 `promotion`／`hotfix`／`release-recovery` 三種 label 會啟動 required `verify` 並納入 evidence identity；其他 label 的 skipped check 使用非 required 名稱，不能覆蓋既有 `verify` 結果；clean main-to-delivery sync 先做結構預檢再引用 current main 的 fresh full Execute；所有證據綁定 repository、head/tree、base、tier/scopes、command、toolchain、tier labels、release level、runner、result 與 24 小時 freshness | `tests/test_ci_tier.py`；`tests/test_journey03_ci.py`；`tests/test_verification_evidence.py`；`tests/test_pr_lifecycle.py`；`tests/test_delivery_sync.py` | #834 hosted execution active；#812 risk-owned/reuse/sync route active；#901 guard 待首次 Ready／label 事件 live evidence |
| PR policy | `.github/workflows/pr-policy.yml` | PR／交付政策 | `pull_request_target` PR metadata 事件（opened／edited／synchronize／labeled）、`merge_group` | `contents`／Issues／pull requests 只讀；固定 timeout | 單一 `title` job：draft 期間不啟動 runner，`ready_for_review` 後才完整驗證 Issue、route、review policy、promotion route 與 Milestone approval，以原生 job conclusion 回報結果 | `scripts/test-pr-policy`；`tests/test_journey05_workflows.py`；route classifier 見 `tests/test_promotion_gate.py` 的 `test_check_route_*` | 歷史 run [33519320929](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33519320929) 證明既有 policy 判定；#876 合併後首張 PR 補 live consolidated-job evidence | 既有 policy：active；#876 consolidation：candidate |
| PR policy writes | `.github/workflows/pr-policy-writes.yml` | PR metadata 與 Milestone check-run 寫入（#829／#886／#926／#933） | default branch 的 `workflow_run`，只接續 `success`／`failure` 的 `PR policy` run；`skipped`／`cancelled` 不啟動 runner，同 head 較新事件取消舊 writer | top-level 無權限；單一 trusted job 只取得其循序 steps 合計所需的 `checks`／`issues`／`pull-requests: write` 與 `contents: read`；10 分鐘 | 一次 checkout 後以完整 head identity 跨頁解析唯一 open PR、同步 metadata／#551 提醒，再發布 `Milestone approval` custom check；等待核可時 check 維持 pending，確定違規才 failure，而 publisher 成功寫入後本身通過；metadata step 失敗不會掩蓋後續 check publication；零筆或多筆都 fail closed，不執行 PR source 或 artifact | `tests/test_work_item_metadata.py`；`tests/test_milestone_approval.py`；`tests/test_journey05_workflows.py` | #829 trust boundary 已落地；#886 單一 job；#926 skipped writer guard 待 live evidence | candidate |
| PR review（Copilot 審核模式，#752／#775／#826／#900／#926／#933） | `.github/workflows/pr-review.yml` | PR 審核授權 | `pull_request_target`（opened／synchronize／reopened／ready_for_review）、`pull_request_review`（submitted／dismissed）、`issue_comment`（created，篩選 PR 上以 `PR lifecycle merge authorization` 開頭的留言）、`merge_group` | publisher 取得 `checks: write` 與必要讀權限；10 分鐘；同 PR 新事件取消舊 run；draft PR 一般事件不啟動 runner | trusted publisher 呼叫 `scripts/review_gate.py publish`，把等待、通過與確定拒絕分別發布為 `review` 的 queued／success／failure；publisher 只有判定或 API 寫入失敗才失敗。merge queue 沿用已通過的 PR head review | `tests/test_review_gate.py`；`scripts/pr_lifecycle.py` 的授權來源與 custom check provenance 見 `tests/test_pr_lifecycle.py` | #900 candidate | candidate |
| Dependency vulnerability | `.github/workflows/osv.yml` | 依賴安全（#406／#407） | weekly schedule、manual、相關 manifest／lockfile 變更 | `contents: read`；固定 timeout | OSV 掃描結果 | `tests/test_dependency_security.py` | 2026-09-01 以 `gh api repos/.../actions/workflows` 查詢：GitHub 僅註冊 7 支 workflow，**不含 `osv.yml`**——本檔尚未落地 `main`，且觸發條件不含 `pull_request`，候選分支無法預先註冊。前身「OSV scheduled scan」最後已知 run 於 2026-08-24 全部 failure，屬歷史證據，不代表本候選 | **root：candidate**（待 main 落地＋首次排程／手動觸發）；**新生成 repo：active**（Copier 初次 commit 即進入該 repo `main`，可立即註冊與觸發） |
| Work item lifecycle | `.github/workflows/work-item-lifecycle.yml` | #400／#401／#574（合併）／#886（runner guard） | `issues`、`issue_comment`、`milestone`、`pull_request.closed` 事件；job guard 在 runner 前排除 PR comment、非 delivery-branch PR close 與沒有任何 owner step 的 Issue 事件 | 單一 job 內所有 step 共用的最小權限集合：`checks: write`、`contents: read`、`issues: write`、`pull-requests: read`；5 分鐘 | label／milestone routing、lifecycle gate 狀態與 closure 同步、對應 Issue 關閉 | `scripts/test-issue-triage`、`tests/test_journey06_workflows.py`、`tests/test_milestone_approval.py`、`tests/test_milestone_closure.py`、`tests/test_work_pr_closure.py` | #574 單一 job 已落地；#886 job guard 待 live evidence | candidate |
| Spec to Issue | `.github/workflows/spec-to-issue.yml` | Spec 轉換 | spec 檔案變更事件／manual dispatch | 最小 Issue metadata write | 可審查 Issue 草稿 | `tests/test_spec_to_issue.py` | run [33490382161](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33490382161)，2026-09-01，success | active |
| Dependabot | `.github/dependabot.yml`、`.github/workflows/dependabot-auto-merge.yml`、`.github/workflows/dependabot-merge.yml` | GitHub 原生＋依賴安全；與一般 PR 共用可信 hosted verification（#834）；template 同步、Actions pin 一致性（#755）與 exact-head merge（#830／#886） | schedule／manifest 變更；`pull_request_target`；只有 `dependabot/**` branch 的 trusted workflow completions | authentication 只讀；sync 精確 branch write；merge 透過 lifecycle lease 使用必要 PR／contents write | dependency PR；同張 PR 補齊 paired template 副本；minor／patch 在 required checks 後重新驗證並 atomic merge，major 保留人工審核；一般 PR 不建立 exact-merge workflow run | `tests/test_authenticate_dependabot_head.py`；`tests/test_dependabot_auto_merge.py`；`tests/test_pr_lifecycle.py`；`scripts/sync-paired-files.sh --check` | GitHub 原生 Dependabot active；`dependabot/**` pre-trigger filter 待 live evidence | candidate |
| Version／Release | `.github/workflows/release.yml` | #369／#430／#588／#591／#598／#699／#834／#900 | `release_trigger=main` 時接 main push；`manual` 時只接受明確 dispatch／本機入口 | top-level read；release job 另有 `actions: read`、`checks: read`、`contents`／PR／Issue／status write；60 分鐘 | 固定以 Conventional Commits 判定 major／minor／patch／no-release；no-release 不建候選，只有 materialized 且驗證完成的候選才發布 GitHub Release、checksum 與 SBOM | `tests/test_release_policy.py`、`tests/test_release_bundle.py`、`tests/test_journey07_release.py`、`tests/test_verification_evidence.py` | #900 trigger candidate；Immutable Release post-hoc 驗證沿用 #770 |
| Pages | `.github/workflows/pages.yml` | #926 路徑限定的靜態文件部署 | hosted＋`documentation_mode=template-and-content` 才產生；`docs/**` push 或手動 dispatch | `contents: read`、`pages: write`、`id-token: write`；10 分鐘 | 上傳已 commit 的 `docs/` 並部署，不在 hosted runner 重建網站 | `tests/test_language_profiles.py`、`tests/test_root_config.py`、`tests/test_apply_repository_settings.py` | 合併後須由管理員套用 `build_type=workflow` policy 並觀察首次部署 | candidate |
| Release publish drift alert | `.github/workflows/release-drift.yml` | #605／#933（源自 #589 item 4） | daily schedule＋`workflow_dispatch`（`hours` input） | `actions: read`、`contents: read`、`issues: write`；5 分鐘 | 偵測到 drift 時開立或更新追蹤 Issue 後成功；未偵測到時只印出證據；偵測或通知寫入失敗才讓 run 失敗 | `scripts/test-check-release-drift` | 尚未 merge 進 `main`，故無排程或手動觸發的 live run 證據 | candidate（待 main 落地＋首次排程／手動觸發） |

所有第三方 Actions 鎖定完整 commit SHA，旁註可讀 release tag。Workflow YAML 只負責
event、權限、環境與呼叫；分類與驗證規則留在本機可測的 scripts。Repository 預設
`GITHUB_TOKEN` 為 read-only；release job 只在自己的 workflow 提升必要權限。Release job
只發布 merge 前已在原 PR 受審的候選，不需要也不允許 Actions 另建或自行核准版本 PR。

上表只列本 repo 自己的 active automation。生成 repo 另有一個選用能力：開啟
`enable_template_update_notifications` 才產生 `template-update.yml`
（`schedule`／`workflow_dispatch`、`contents: read`＋`issues: write`、10 分鐘
timeout，只呼叫 `scripts/check-template-update`）。公開模板來源不需要 secret；
來源為 private repository 時，才由唯讀的 `CSARC_TEMPLATE_READ_TOKEN` repository
secret 提供存取，且只有 `schedule`／`workflow_dispatch` 路徑讀得到，不會流向
`pull_request` workflow。本 repo 是模板來源本身，不消費也不排程這個 workflow。

生成 repo 另有一個選用容器能力（Issue #554／#900 決定）：在 `features` 選入 `docker` 才產生
`Dockerfile`、`docker-compose.yml` 兩份起始範本，以及
`.github/workflows/docker-build-scan.yml`（`pull_request`，限 Dockerfile／
docker-compose.yml／已選語言原始碼路徑變更，另加 `workflow_dispatch`；
`contents: read`；20 分鐘 timeout）。該 job 只呼叫 `docker/build-push-action`
（`push: false`）在 runner 本機建置映像，再用 `aquasecurity/trivy-action`
掃描同一本機映像的已知漏洞（`HIGH`／`CRITICAL` 失敗），全程不登入、不推送任何
registry，也不要求任何 secret。未選 `docker` 的專案不會產生上述任一
檔案，不會多一個觸發中的 job，也不會取得任何新權限；這維持
`docs/adr/selective-ci-automation-adoption.md` 記錄的既有決定──「不預先幫所有
repo 產生 container job，非容器專案不應支付 Docker runner 成本或取得 registry
權限」──只是把它從「完全不提供」明確擴充為「非容器專案零影響的選配項」，兩者
並不衝突：該 ADR 拒絕的是「預先幫『所有』repo 產生」，不是「讓明確選擇容器化的
專案自行選用」。本模板 repo 自己的開發／CI 流程不引入 Docker，範圍僅限於是否
提供這個選配能力給下游生成的專案。

### 大規模派工前的 Milestone 合規預檢（#572／#574）

M13 一次開 20 張 Issue、6 條平行線同時動的派工模式沒有節流機制：單一 Issue／PR 事件會
同時觸發多個各自獨立的 workflow（見上表 Work item lifecycle 一列合併前的歷史狀態），
GitHub Actions 依 job 計費（各自捨入到最近 1 分鐘、各自佔一個 concurrency slot）；3 天
內累積 1203 次 run，約 1600-1800 分鐘。#574 決定兩項緩解：一是把 Issue triage／
Milestone lifecycle／Work Issue closure 合併成單一 job（見上表），減少計費 job 數與
concurrency slot 競爭；二是操作面規則——**大規模派工（多張 Issue／多個平行 agent）
前，先手動跑一次 Milestone 合規預檢，確認目標 Milestone 本身沒問題，再一次性開多個
Issue／PR，不要邊開邊試錯**。

#886 的 2026-09-22 追蹤顯示，`CI / verify` 已明顯加速，但每張 PR 的 workflow／job 數仍上升；
因此後續節流以「runner 啟動前排除無 owner 的事件」與「同一 trusted writer 內串行短工作」為主。
`Dependabot exact merge` 只接收 `dependabot/**` branch 的 upstream completion；Work item lifecycle
不為 PR comment 或無關 PR close 啟動 runner；draft PR 的 policy／review 等到 `ready_for_review`；
`CI / verify` 也不為 Draft 活動或一般分類 label 啟動 runner，Ready、非 Draft code／edited 與三種 tier label
仍重新分類；一般分類 label 不再使同 head 的可信 CI evidence 失效。這些過濾不得用 skipped required check
覆蓋既有失敗，也不得放寬 exact-head、workflow provenance、權限或 Ruleset。

這個 `preflight` 子指令定義在「Enforce Milestone metadata at creation, not after PRs
fail」（#572，已併入 `main` 為 #655；本 Milestone delivery branch 尚未同步當時的
`main`，#667 直接把這個子指令原樣移入本分支，理由與作法見下方「過時 delivery branch
偵測（#667）」一節）。實際呼叫方式：

```console
python3 scripts/sync_milestone_state.py preflight --repo <owner>/<repo> --milestone <N>
```

`preflight` 驗證 due date、tracker 標題與 `Lifecycle Issue:` 連結是否就緒，成功會印出
`Milestone metadata is ready for work`；失敗會列出缺漏並以非零結束碼結束，供派工前手動
確認一次。同一次呼叫也會附帶 #667 的過時 branch review 清單（純提示，不影響這個
Milestone 本身是否就緒的判定）。

## 驗證分級與實測成本

驗證契約只有 `fast` 與 `full` 兩種組合，另有一種本機專用、不屬於 CI 政策的
focused check。最後要求是發布層級下限與 `scripts/ci_tier.py` 路徑分類取較強者。
`scripts/verify-fast` 從 `branch.<name>.gh-merge-base`（必要時以 `CSARC_CI_BASE` 指定）找出 PR base，
對 merge-base 到 `HEAD` 以 `git diff --no-renames` 取得路徑，再自行執行同一份 plan；base 無法判定時
直接 fail closed。舊有 `CSARC_CI_TIER`／`CSARC_CI_SCOPES`／`CSARC_RUN_OSV` 只能增加 suite 或 scope，
不能移除自動算出的要求：

既有下游設定中的 `baseline`／`docs` 在 update migration 與 runtime 都會正規化為 `fast`；新設定只提供
`fast`／`full`，避免同一套執行內容繼續以多個 tier 名稱存在。

1. **開發中 focused check（本機專用，不是 CI 的第三種政策）**——實作中與一般 push 前直接執行
   變更 owner 的單一命令，例如
   `uv run pytest <path>`、`uv run ruff check <path>`，或針對
   `scripts/verify-template.sh` 其中一階段單獨重跑對應的
   `scripts/verify-stage-<name>`；不需要等待整條 pipeline，也不會被當成合併證據。
2. **日常 PR gate（`fast`）**——`scripts/ci_tier.py` 依事件、base／head、labels 與
   changed paths 做 fail-closed 分類；未知或高風險內容升級為 full。純文件／site 變更仍是
   `fast`，由 docs scope 只啟動對應 owner，不再建立一個只有名稱不同的 `docs` tier。
   入口是 `scripts/verify-fast`。本機可在需要廣泛
   診斷時選擇執行這個入口，但一般 push 不再先重跑整套；hosted `verify` 在可信 runner 對
   exact candidate 執行一次 risk-owned suite，並產生上方 #834 定義的 required merge evidence。
3. **完整交付驗證（`full`）**——只在 Milestone／canary 交付、hotfix、merge queue、手動
   執行或未知高風險路徑觸發；中央模板入口是 `scripts/verify-template.sh`，生成 repo
   入口是 `.csarc/scripts/verify`（不帶參數即預設 full）。hosted 模式由 required `verify`
   在 exact candidate 執行一次，owner／integrator 不因 tier 是 `full` 就在本機重跑；local
   模式則由 committed、clean 的 exact candidate 執行 `verify-fast`，依同一 router 自動升級
   full 並記錄 self-attested evidence。hosted 模式的本機 full 只保留給明定 fallback 或診斷。

數據來自 #428／PR #431 在 2026-09-01 的最新 hosted run，目的是設定成本預期，不是永久 SLA；
`full` 一列已由 #458 在 2026-09-02 於同一本機環境重新量測（見下方階段盤點與 PR 內文的
before／after 紀錄）。

| 組合 | 最低層級 | 入口與累加測試集合 | 實測 |
| --- | --- | --- | --- |
| fast | beta | 共同 hygiene／secret，加上變更 scope 的 owner checks；docs-only 不啟動產品語言工具鏈，dependency 只做鎖檔與 OSV；路徑風險仍可升為 full | 目標三次 warm-cache 中位數不超過 75 秒（#812／#918） |
| full | stable | fast owners ＋ `large` 的代表 create／adopt／previous-release update（create 含 Rust native）與 coverage | 目標三次 warm-cache 中位數不超過 15 分鐘（#812／#918） |

#812 的固定 clean-tree 基準是 #815 合併後 PR #853 的 exact tree：hosted `verify-fast`
收集 1,530 個 pytest cases、排除 49 個 `large`、執行 1,481 個，pytest／regression stage／
整個 job 分別為 112.05 秒／113 秒／3 分 13 秒；同一 tree 的本機 full 基準為 4 分 24 秒。
套用 #812 的刪減與 owner routing 後，在同一部 macOS 開發機與 warm cache 執行 1,143 個 cases，
三次 `verify-fast` 為 69.91、65.77、64.45 秒，中位數 65.77 秒；對應 pytest 為 55.56、
52.32、50.90 秒，中位數 52.32 秒。較長的 shell lifecycle integration 仍由 full regression
執行，沒有刪除其驗證責任；hosted 與本機總時間因環境不同，只用各自的 stage 證據比對，不把
兩者混成單一速度倍率。

#940／PR #953 在 2026-09-23 的同一候選提供了重複成本基準：本機 full 為 919 秒，hosted
full 為 400 秒；hosted 的 Regression tests 佔 387 秒，其餘六階段合計 13 秒。#955 因此移除
hosted 模式「本機 full 後再跑 hosted full」的強制重複；這是執行位置與次數的收斂，不是降低
full 的 stage、測試集合、風險路由或 required evidence。

相依 manifest／lockfile 變更加跑 `scripts/verify-dependencies`。CI 不建立 release asset，
也不把測試 artifact 當成正式成品。#408 已把更細的 stage timing 輸出納入現行入口。

直接打到 `main` 的一般 PR 若修改 generator 或 CLI adoption／update 路徑（`template/` 的產品內容、
`copier.yml`、`profiles/`、`src/csarc_cli/`），或分級／驗證器本身（`ci_tier.py`、`verify-fast`、
`verify-template.sh`、`verify-stage-*`、attestation scripts），path tier 為 `full`，因為後面沒有 promotion
可補跑。workflow 與其他 scripts 維持 `fast`，但仍依 scope 執行 actionlint／ShellCheck、workflow drift、
Zizmor、治理 self-tests 等對應檢查。打到 `dev/m*` 的 Milestone 工作 PR 維持 fast；完整套件在
promotion 邊界對最終候選執行。

### Base-only re-merge 例外（#468）

**#834 之後的現況**：hosted `verify` 已恢復在 exact candidate 上實際執行所選 tier，因此本節原本
「四個條件同時成立時可直接 push，讓 hosted full 驗證新 tip」的前提重新成立。#661 期間因 unsigned
trailer 造成的暫時限制已由 #834 supersede；`scripts/check-base-only-remerge` 的四項判斷與下方流程恢復
完整效力。

#955 之後，hosted 模式不再要求 full-tier PR 先於本機執行 full；required `verify` 直接在
exact candidate 執行並產生可信證據。這個歷史例外只在文件明定的 fallback 或明確診斷已經
產生一份本機 full，之後 base 又前進時，回答「需不需要為本機用途重跑」；它不會讓本機結果
取代 hosted evidence。local 模式的 self-attested evidence 必須綁定 exact head/tree，base
改變後直接依 local 模式規則重新執行，不套用本節例外。

一次重新合併（re-merge）只在下列四個條件**同時**成立時，才算「base-only re-merge」、
才可以直接 push 並信任 hosted `verify` check，不必再本機重跑：

1. **這個 branch 已經對自己這一輪真正的內容，跑過一次全綠的本機
   `./scripts/verify-template.sh`（或生成 repo 的 `./scripts/verify`）。** own-verified-
   head 必須是那次全綠時的 commit；如果那之後這個 branch 又有新的自有 commit（不是單純
   重新合併 base），own-verified-head 就不等於目前 tip，這條例外不適用，仍照 #458 規則
   本機重跑。
2. **這次重新合併乾淨、不會產生任何衝突**——用 `git merge-tree` 在不動 working
   tree／index／任何 ref 的前提下確認（三個引數版本：`--merge-base <old-base-tip>
   <own-verified-head> <new-base-tip>`），不是只看實際合併當下有沒有手動解過衝突。
3. **上游帶進來的檔案，跟這個 branch 自己這一輪已驗證的檔案完全沒有重疊**——即「incoming
   diff 的檔案」（`git diff --stat <old-base-tip> <new-base-tip>`，`old-base-tip` 是
   own-verified-head 當初同步到的那個共用 base commit）與「這個 branch 自己這一輪的檔
   案」（`git diff --stat <old-base-tip> <own-verified-head>`）交集為空。
4. **上游帶進來的變更沒有觸碰驗證／CI／政策基礎設施本身**——`scripts/verify*`、
   `.github/workflows/`、`scripts/ci_tier.py`、`scripts/pr_lifecycle.py`、
   `scripts/validate-*-policy`、`scripts/test-issue-triage`、
   `scripts/test-worktree-cleanup`、`scripts/test-pr-policy`、`policies/` 等。就算與這
   個 branch 自己的檔案完全沒有重疊，上游一旦動到「驗證本身的定義」（例如新增或修改一
   個 verify-stage、調整 CI tier 分類邏輯、放寬 PR policy），先前的本機全綠就不能直接
   沿用其涵蓋範圍，仍要求本機重跑。

四項同時成立時，PR owner／integrator 可以直接 push 這次重新合併的結果，不必再本機重跑
`./scripts/verify-template.sh`，改為信任 hosted `verify` check 作為這次重新合併後的最
終驗證。這**不代表**降低驗證涵蓋範圍：hosted CI 對這次合併結果執行的仍是同一支
`scripts/verify-template.sh`／`scripts/verify-stage-*`（生成 repo 是同一支
`scripts/verify`），差別只在「誰的環境跑」從本機換成乾淨、不受本機 worktree 並行負載或
網路瞬斷（#466）影響的 hosted runner，而且只在合併沒有引入新風險（條件 2–4）時才適用。
`own-verified-head` 本身不會因為用了這條例外 push 過就往前移——只有真的又在本機重跑過
一次全綠，才把它往前移；因此同一張 PR 即使因為 base 連續前進被迫重新合併多次，也可以連
續套用本節例外，只要每次都用同一個原始 own-verified-head 重新檢查最新的
`new-base-tip`。

以下情況**明確不符合**本節例外；若 fallback／診斷仍要求本機 full，就必須重跑，不確定時也視為不符合：

- 重新合併產生真實衝突（無論是否已手動解決）。
- 上游變更觸及這個 branch 自己這一輪已驗證的任何檔案，即使只是同一檔案的不同行、不會
  造成文字衝突。
- 上游變更觸及上方條件 4 列出的驗證／CI／政策基礎設施。
- 這個 branch 在上次本機全綠之後，又有新的自有 commit（不是單純的 base 重新合併）。
- 這次 push 開始了一次新的 fallback／診斷需求，而不是同一張已驗證 PR 的後續重新合併。

`scripts/check-base-only-remerge <own-verified-head> <new-base-tip> [<old-base-tip>]`
提供上述四項判斷的可執行版本：省略 `<old-base-tip>` 時預設為
`git merge-base <own-verified-head> <new-base-tip>`；符合條件印出 `QUALIFIES` 並以
exit 0 結束，任何一項不符合印出 `REQUIRES-FULL-RERUN` 與具體原因並以非 0 結束。它只讀
取 refs 並用 `git merge-tree` 做唯讀的三方合併模擬，從不修改 working tree、index 或任
何 ref，也從不自己執行或略過驗證——只回答「這次重新合併符不符合條件」。
`scripts/test-check-base-only-remerge` 對合格案例與三種不合格案例（檔案重疊、觸及驗證
基礎設施、檔名不重疊但仍衝突）做回歸測試，掛在 `scripts/verify-template.sh` 的
Regression tests 階段下（與 `test-issue-triage`／`test-worktree-cleanup`／
`test-pr-policy` 同一組 self-test）。它不掛在 `scripts/verify-fast`：`verify-fast` 的
governance／template／workflow／shell scope 自我測試集合與生成 repo 的
`template/.csarc/scripts/verify-fast.jinja` 必須逐項相等（`tests/test_journey03_ci.py::
test_release_verification_contains_issue_pr_regressions` 對此做回歸測試），而
`scripts/check-base-only-remerge` 只存在於中央模板 repo、不會下發到生成 repo（生成
repo 的 full 入口是單一 `scripts/verify`，沒有本模板這種多階段重新合併場景），所以只加
在 full 專屬的 Regression tests 階段，不加進 fast／docs 都會執行的 `verify-fast`。

沒有先跑這支腳本，也可以用等價的手動程序判斷：對照 `git diff --stat <old-base-tip>
<own-verified-head>` 與 `git diff --stat <old-base-tip> <new-base-tip>` 兩份檔案清單有
沒有交集，人工確認合併乾淨（沒有留下 `<<<<<<<`／`=======`／`>>>>>>>` 標記，`git diff
--check` 與 `scripts/check-update-conflicts` 兩者都乾淨），並確認上游變更沒有觸及上方
條件 4 列出的路徑。

### Acceptance-checklist 驗證時機（#573）

歷史案例 #430（PR #448）示範過一種重試風暴：作者在 13 小時內邊做邊 push、邊勾
checklist。`pr-policy.yml` 的觸發清單（`opened`／`edited`／`synchronize`／
`reopened`／`ready_for_review`／`labeled` 等）讓幾乎每個動作都重新執行整支
`scripts/validate-pr-policy`，其中包含兩個 acceptance-checklist 檢查——PR 本文自己
的完成清單（「Complete every pull request checklist item...」）與連結 Issue 的
acceptance criteria（「Issue #N still has unchecked acceptance tasks.」）。在工作
真的還沒做完的中間狀態，這兩個檢查必然失敗；13 小時內因此重跑了 49 次，不是規則擋
下的，只是恰好沒被更早發現。

`scripts/validate-pr-policy` 現在讀取 `PR_DRAFT`（`.github/workflows/pr-policy.yml`
的「Validate pull request policy」step 從 `github.event.pull_request.draft` 帶入），
**只**在 `PR_DRAFT == "true"` 時略過這兩個 checklist 檢查；同一支腳本的其他規則——分
支命名、`Closes #N` 是否存在、title 格式、label／assignee／Milestone 與 Issue 是否
一致、base branch 鏈、Milestone tracker 的 Promotion checklist 等——不受影響，草稿
PR 仍會在每次觸發時得到這些結構性錯誤的即時回饋。略過時會印
`::notice::Skipping acceptance-checklist validation while the pull request is a
draft...`，不是靜默跳過。

這個時機收斂是安全的：GitHub 本來就不允許合併草稿 PR，草稿階段的 checklist 是否完
整不影響任何合併資格判斷。把 PR 標記為 ready for review 會觸發自己的
`ready_for_review` 事件（此次改動之前就已在觸發清單內），對當下這個即將被判定能否合
併的 head commit 重新跑一次完整驗證，兩個 checklist 檢查都在其中。等於把「必驗證的
時機」從「每一次 push，包括明知還沒做完的那些」收斂成「草稿轉 ready 的那一刻，以及
之後的每一次 push／edit」——只要作者在完成前把 PR 留在草稿狀態，就不會再為每個中間
commit 製造一個註定失敗的 check run。

`scripts/test-pr-policy` 新增回歸案例，涵蓋：`PR_DRAFT=true` 時，PR 本文與連結
Issue 個別未勾選都會被接受；`PR_DRAFT=false`（顯式或預設）時，同樣的未勾選狀態仍會
被擋下；`PR_DRAFT=true` 不會連帶放行其他失敗原因（例如缺少 `Closes #N`），證明這個
略過只收斂在兩個 checklist 檢查上。本節只改變「什麼時候驗證完整性」，不改變「什麼算
完成」——打勾必須有真實證據的規則不變，也不在本節放寬；配套的流程規則見 AGENTS.md
working loop。

### PR policy 逐 step 判讀（#513）

`gh pr checks` 只回報每個 job 的整體 conclusion。`pr-policy.yml` 的 `title`
job 依序執行多個 step，其中「Validate pull request policy」與「Validate
Milestone approval」是彼此獨立的兩個 step；只要任一個失敗，job 整體就顯示
`failure`，即使另一個 step 本身乾淨通過。手動用 `gh run view <run-id> --log
| grep -E "Validate pull request policy|##\[error\]"` 逐次判讀容易誤判——本
repo 在 Milestone 8 多 agent 並行協作期間就至少發生過一次誤讀——而且很慢。

`scripts/check-pr-policy-status <pr-number> [--repo <owner/repo>] [--json]`
改用 `gh api repos/{repo}/commits/{sha}/check-runs` 找出該 PR 目前 head
commit 最新的 `verify`／`title` check run，再用
`gh api repos/{repo}/actions/jobs/{job_id}` 讀 `title` job 的逐 step
conclusion——不靠 log 文字比對，直接讀 step 本身的結構化結果。輸出三個獨立
布林：`verify` check 是否 pass、「Validate pull request policy」step 是否
success、「Validate Milestone approval」step 是否 success。預設印可讀摘要；
`--json` 輸出結構化結果供 agent 直接解析。本機沒有裝 `gh`／`gh` 未認證，或
PR 不存在時，明確報錯並以非 0 結束，不靜默給錯誤答案。

往後任何人或 agent 要判斷「這個 PR 的 policy 檢查有沒有真的過」，一律用這支
工具讀三個獨立布林，不要手動 grep log，也不要只看 `gh pr checks` 的 job 層級
輸出。它只讀取 GitHub API、不修改任何 PR、check run 或 workflow，也不做
「能不能合併」的最終判斷——那仍由 Journey 08 與本文件既有的 review／required
check 規則決定；本工具只負責把 job 層級噪音拆成正確的 step 層級事實。

`scripts/test-check-pr-policy-status` 用 mock `gh`（不打真實網路）對「job
整體 fail 但目標 step success」與「目標 step 真的 fail」兩種情況各自回歸
測試，也涵蓋 `gh` 未安裝與 PR 不存在兩種誤用場景，掛在
`scripts/verify-template.sh` 的 Regression tests 階段下（與
`test-check-base-only-remerge` 同一組 self-test）。`scripts/check-pr-policy-status`
只存在於中央模板 repo、不下發到生成 repo：它是這個 repo 自己在 Milestone 8
多 agent 並行協作期間需要的本機／agent 診斷工具，不是任何 `.github/workflows/`
呼叫的 product surface；`pr-policy.yml` 本身（含其 job/step 結構）仍照原樣
下發給生成 repo，不受影響。

### Scope-drift gate enforcement 與核可 fingerprint-binding（#632）

`#552`（PR #609）落地了 `sync_milestone_state.py` 的 `has_scope_sentinel()`／
`scope_decision()`：一張 work Issue 若在 body 逐字獨立一行寫下
`Tracker scope: expanded`，就需要一次獨立的非提案者核可（或 `admin`
collaborator 自核例外）才算通過，判斷邏輯與 tracker 層級的 `/milestone approve`
完全共用。但 `#552` 當時只落地 `check-scope` CLI 子指令本身，刻意不接進任何
`.github/workflows/*.yml`（見 `docs/adr/milestone-scope-and-closure-reconciliation.md`
的「刻意不做的部分」），也沒有把核可綁定到特定版本的 body 內容。`#632` 補齊這兩
個缺口：

- **CI 接線：**`pr-policy.yml` 的 `title` job 新增「Validate the scope-drift
  gate」step，在「Validate pull request policy」之後、`merge_group` 專屬 step
  之前執行，呼叫新腳本 `scripts/check-scope-gate`。這支腳本從 PR body 解析
  `Closes|Fixes|Resolves #<n>`（與 `scripts/validate-pr-policy` 自己用來核對
  branch-derived Issue 編號的同一個 pattern，`#632` 不重新推導、只重用其結
  論），找到連結的 work Issue 後呼叫 `sync_milestone_state.py check-scope`；
  找不到連結 Issue（release 自動化、dependabot、main-sync bridge 等本來就沒
  有連結 work Issue 的 PR）則直接放行、不擋。`check-scope` 回報未通過時腳本
  以非 0 結束，比照本檔其他 gate 一貫的 fail-closed 模式擋下該 job；PR 沒有
  宣告 `Tracker scope: expanded`，或已通過核可，都正常放行。這個 step 比照
  `check-pr`／`check-merge-group` 既有的 rollout-safety 寫法：因為
  `title` job 用 `pull_request.base.sha` checkout（刻意不信任 PR 自己送來的
  policy 腳本），`scripts/check-scope-gate` 這支新腳本要等到落地 `#632` 的
  這次 PR 本身合併進 base branch 之後才會出現在該 checkout 裡；因此 step 先
  判斷腳本是否存在（`[[ -x ./scripts/check-scope-gate ]]`），不存在只印
  `::notice::` 放行，同一張 PR 在自己身上驗證時不會因為這個 chicken-and-egg
  落差而誤擋（PR #633 落地時已由真實 CI run 實測到這個落差並修正）。
- **Fingerprint-binding：**`approval_decision()`（tracker 核可）與
  `scope_decision()`（work Issue scope 核可）共用的 `_approval_records()`／
  `_gate_decision()`，現在額外比對每則 `/milestone approve`／
  `admin-approve:` 留言的 `created_at` 與該 Issue（或 tracker）自己的
  `updated_at`。GitHub REST 不像 Reconciliation 段落的
  `reconciliation-fingerprint`（bot 自己寫入、可以精確重算比對）那樣提供可
  查詢的 body 編輯歷史；`updated_at` 是唯一可查的訊號，但它也會因為新留言、
  label／Milestone／state 變更等與 body 編輯無關的活動而更新
  （`_approval_is_stale()` 的 docstring 記錄了完整理由）。因此判定刻意走保
  守方向：只要留言的 `created_at` 早於 `updated_at` 超過 60 秒的緩衝窗（吸收
  GitHub 自己「留言建立」到「Issue.updated_at 反映該留言」之間，經對本
  repo 既有 Issue 歷史實測約 1 秒的落差),就視為過期，需要重新核可——寧可提
  高「需要重新核可」的誤判率，也不讓核可默默套用在已經變動過的 body 版本
  上。缺少任一時間戳（例如舊測試 fixture 沒有填 `created_at`／`updated_at`）
  一律視為「無法判斷」而非「一定過期」，維持 `#552` 既有行為不變。

`tests/test_milestone_approval.py`／`tests/test_milestone_scope.py` 覆蓋
staleness 邊界（含 60 秒緩衝窗、跨過緩衝窗即過期、過期後重新核可即恢復通過）；
`scripts/test-check-scope-gate` 對 `check-scope-gate` 本身做端到端回歸測試
（無連結 Issue、無 sentinel、有 sentinel 未核可、有 sentinel 已核可、核可過期
四種結果，掛在 `scripts/verify-stage-regression-tests`）。routine fast 由同一 Python suite
裡的窄版 policy 測試負責，避免再串行重跑完整 shell fixture。這次變更不重新設計
`has_scope_sentinel()` 的偵測邏輯，也不擴大 `/milestone approve`／
`admin-approve` 留言語彙本身——只在既有機制上補上 CI 接線與版本綁定這兩層。

**留言編輯本身的過期判斷（#778）：**上面的 fingerprint-binding 只比對核可留言
的 `created_at` 與 item 的 `updated_at`，從未讀取留言自己的 `updated_at`。缺
口是：一則早於（或落在緩衝窗內）item `updated_at` 的舊留言，如果本來不是核
可語彙，很久以後才被**編輯**成 `/milestone approve`，`created_at` 完全不受編
輯影響，判斷式看到的仍是「舊留言、舊 item，兩者時間點很接近」，因而誤判為
新鮮、允許通過——即使核可語彙實際上是編輯當下才寫入，從未針對任何特定版本
的 body 做過核可。`_approval_is_stale()` 現在多一個獨立、以 OR 相接的判斷：
留言自己的 `updated_at` 與 `created_at` 的差距若也超過 60 秒緩衝窗，同樣視
為過期，不論 item 那一側看起來多新鮮。這個新判斷只會讓結果**更保守**（多抓
出過期案例），不會讓既有的 item-vs-`created_at` 判斷結果被推翻回「新鮮」：
一則已經因為 `created_at` 早於 item `updated_at` 而過期的留言，就算之後的編
輯時間點晚於該次 item 更新，也維持過期，不能靠編輯「洗新」。從未編輯的留言
（`updated_at` 等於或缺少 `created_at`）行為完全不變。

### `scripts/verify-template.sh` 階段盤點（#458）

`scripts/verify-template.sh` 是一個薄聚合器：七個階段各自是 `scripts/verify-stage-*`
底下一支可獨立執行的腳本，聚合器仍依相同順序呼叫，並保留原有的
START／PASSED／FAILED／timing summary 輸出格式與 pass/fail 語意；
`scripts/test-verify-template-stages` 對這個聚合契約（呼叫順序、腳本存在且可執行、
PASSED／FAILED／TOTAL 回報）做回歸測試，並同時掛在 `scripts/verify-fast` 的
`shell` scope 與 `scripts/verify-template.sh` 的 Regression tests 階段下。

盤點結論：七個階段各自覆蓋不重疊的風險，且 `scripts/verify-fast` 對同一批底層腳本只是
依 scope 收斂呼叫範圍（例如只在 dependency scope 才跑 `verify-dependencies`），不是另一
套重複邏輯——每個保留下來的風險都只有一個可執行的 regression source。本次盤點沒有找到可
以在不流失獨立風險覆蓋的前提下安全移除的檢查，因此沒有刪除任何既有檢查，只拆分了檔案邊
界、補上獨立重跑入口，並在下表記錄取捨依據。

| 階段（`run_stage` 名稱） | 獨立入口 | 涵蓋風險 | 與 fast tier／其他檢查的關係 |
| --- | --- | --- | --- |
| Repository contracts | `scripts/verify-stage-repository-contracts` | changed-tree hygiene、未解決的 Copier／Git 衝突標記、機密掃描、已知漏洞掃描 | fast 每次都跑 `git diff --check`／`check-update-conflicts`／`scan-secrets`；`verify-dependencies` 只在 dependency scope 才跑，呼叫同一支腳本，不是重複邏輯 |
| Static assets and paired files | `scripts/verify-stage-static-assets` | repo-site 可重現 render、workflow／shell 靜態分析、static-validation fixture 的正／反向覆蓋、root／template 配對檔案漂移 | fast 只在對應 scope 才跑其中個別項目（`docs` scope 跑 render 檢查；`workflow`／`shell` scope 才跑 lint）；full 一律跑全部四項，是唯一同時驗證全部四種風險的入口 |
| Python environment | `scripts/verify-stage-python-environment` | `uv.lock` 與 `pyproject.toml` 一致、環境可從鎖定版本安裝 | fast 的 `uv sync --locked` 是同一份鎖定契約；`uv lock --check` 只在 full 額外執行 |
| Python quality | `scripts/verify-stage-python-quality` | 格式、lint、靜態型別 | fast 對相同原始碼跑相同三個命令，兩者呼叫同一份工具鏈設定，無額外邏輯 |
| Regression tests | `scripts/verify-stage-regression-tests` | 完整 pytest（含 `large` 標記的 Copier create／existing-adoption／update 保存回歸）＋coverage 門檻，以及 Issue-triage／worktree-cleanup／PR-policy／scope-drift-gate／base-only-remerge／gh-issue-create／gh-issue-develop／check-branch-fresh／PR-policy-status／release-drift／audit-fleet-adoption／create-milestone／`verify-template.sh` 聚合自我測試 | fast 只跑 `pytest -m "not large"`（略過 `large`）；較長的 shell lifecycle fixtures 留在 full，routine fast 由同一 Python suite 的窄版 policy 測試涵蓋。base-only-remerge、`scripts/gh-issue-create`（開 Issue 前本機先擋不合規標題，見 AGENTS.md 工作迴圈）、`scripts/gh-issue-develop`（建立遠端 ref 前擋不合規分支，只在尚無 open PR 時修復錯名，見 #932）、`scripts/check-branch-fresh`（開工前本機核對既有分支是否仍等於 `origin/<branch>`，見 AGENTS.md 工作迴圈）、PR-policy-status、`scripts/audit-fleet-adoption`（本機即時查詢 fleet 採用門檻、只印 stdout，見 #521）與 `scripts/create-milestone`（原子建立 Milestone 與其 tracker Issue，見 `docs/milestone-description.md`；#572）七支本機專用工具的自我測試都只在這個 full 專屬階段跑，不進 `verify-fast`（分別見上方 Base-only re-merge 例外一節與下方 PR policy 逐 step 判讀一節）；`scripts/test-check-release-drift`（mock `gh`，驗證上方「發版存量漂移偵測（`release-drift.yml`，#605）」一節的 drift 判定邏輯）也只掛在這個 full 專屬階段——`scripts/check-release-drift` 本身像 `release.yml` 一樣逐位元組下發到 `template/`，但比照 `release.yml`／`ci.yml` 沒有生成 repo 端本機再測試的既有慣例（下發前的 root 測試已足夠證明這份靜態、無 Jinja 條件式的實作正確），不隨腳本一起下發、也不掛進生成 repo 的 `scripts/verify`；`large` 覆蓋範圍只在 full 執行，是 Copier create／adopt／update 保存的唯一 regression source，未被任何字串比對或重複 profile 執行取代 |
| Package smoke test | `scripts/verify-stage-package-smoke` | wheel 可建置、已發布入口可從建置產物執行 | fast 不跑這個階段，也不執行真實 Copier；由 full 的代表 create canary 與本階段證明 |
| GitHub Actions audit | `scripts/verify-stage-github-actions-audit` | workflow 權限與注入稽核（zizmor） | root `verify-fast` 在 workflow scope 直接執行；full 仍執行同一支 stage，不依賴未啟用的 merge queue 或後續 promotion 補跑 |

#### 驗證拓撲與可觀測性（#780）

驗證分成三種責任，不再把同一批 Python 測試複製到不同 repo 後重跑：

- **Root-only governance tests：**`tests/` 驗證本模板的 Milestone、PR、release、安全與
  Copier lifecycle；只由 root 的 fast／full 入口執行。`template/tests/` 只下發生成產品本身
  的 smoke test，不再帶 root 治理模組、marker policy hook 或其 SBOM fixtures。
- **Generated-project contract checks：**代表組合實際經 Copier render，檢查 config、
  manifest 與三種語言專屬檔案；Python 相容性入口只跑 `runtime and not large` 的最小 smoke、
  建置 wheel 並從隔離環境 import。
- **One representative end-to-end profile：**full regression 只挑一個 Python＋TypeScript＋Rust 組合；
  生成 repo 用 `scripts/verify full` 一次涵蓋三種真實原生工具鏈，不再按語言重跑
  repository-wide checks。create／adopt／update 的保存契約
  則繼續由 root 的 `large` regression 提供，不用每種單語言 profile 再跑一次完整 verifier。

pytest marker 契約只保留有執行責任的兩種標記：`runtime` 表示每個受支援 Python runtime 都必須執行
的最小行為，`large` 表示只由 full regression 執行的真實 Copier lifecycle、release publication
transaction 或原生工具鏈案例。
#812 確認 `quarantine` 沒有現役使用者後，刪除其 collection hook、專用 policy script 與測試，避免維護
不會影響執行結果的空框架。

所有本機驗證入口共用 `scripts/verification-step`：每一步在開始與結束時印出名稱與 wall
time；執行超過 60 秒時每 60 秒輸出 heartbeat；失敗時先指出第一個失敗步驟、exit status、
`log=stdout`，再印出 shell-quoted 的單步 `RERUN` 指令。`scripts/verify-template.sh` 仍維持
七階段摘要，並在 stage failure 另列可獨立重跑的 `scripts/verify-stage-*` 指令。可用
`CSARC_VERIFICATION_HEARTBEAT_SECONDS` 將 heartbeat 間隔改為其他正整數秒數；這只改變
顯示頻率，不改變命令、重試或 pass/fail 語意。Root 的 fast／full pytest 另用 verbose
node ID 顯示目前案例，結束時列出最慢 20 個案例；沒有自動 retry。

#### 逐階段耗時量測（#465）

上表只記錄涵蓋範圍與取捨依據，沒有留下逐階段秒數；聚合器本身每次執行都會印出
timing summary（`PASSED/FAILED <秒數> <階段名>`），但這份資料原本只存在單次終端機
輸出裡，Regression tests 這種本身就重（完整 pytest＋`large` 標記的 Copier
create／adopt／update 矩陣）的階段沒有可查證據，只能自己跑一次全部七階段才知道量級。
下表把一次完整 run 的 timing summary 轉存成文件，補上這個缺口。

量測日期：2026-09-02；環境：本機（不是 hosted runner），與上方 full/fast 實測欄位
同一台機器。本次量測**不是**獨占環境：同一次任務裡先後跑了三次
`./scripts/verify-template.sh`，前兩次都不能當作乾淨樣本——第一次在 Repository
contracts 階段因暫時性網路錯誤（`curl: (92) HTTP/2 stream 1 was not closed
cleanly: PROTOCOL_ERROR`）於 212 秒處中止；第三次（跑之前已確認沒有其他
pytest／verify／copier 程序在跑）前四個階段各只花 5s／5s／0s／1s，但 Regression
tests 內一個需要對外連線的 adoption 保存測試又踩到同一種暫時性網路錯誤，於 1107 秒
處失敗，同樣沒有跑完七個階段。下表數字取自第二次、七個階段全部 PASSED 的那次執行；
量測期間偵測到另一個 worktree（`csarc-repo-template-issue-472`）同時開始執行自己的
`uv run pytest`，系統 load average 從量測開始時約 3.5 上升到量測結束後約 5.5，因此
TOTAL（4002 秒／66 分 42 秒，尤其是 Regression tests 一階段的 3971 秒）明顯高於
#458 記錄的 502 秒獨占基準，不代表典型耗時，只保留為「同機器有其他背景負載時」的
量測示例；三次嘗試合計已重試兩次，之後沒有再重跑，若需要乾淨的獨占基準，需在確認
沒有其他 worktree／verify 活動、且網路連線穩定時重新量測，不宣稱本次數字為恆定 SLA。

| 階段（`run_stage` 名稱） | 獨立入口 | 秒數（本次量測，非獨占） |
| --- | --- | --- |
| Repository contracts | `scripts/verify-stage-repository-contracts` | 10 |
| Static assets and paired files | `scripts/verify-stage-static-assets` | 10 |
| Python environment | `scripts/verify-stage-python-environment` | 2 |
| Python quality | `scripts/verify-stage-python-quality` | 2 |
| Regression tests | `scripts/verify-stage-regression-tests` | 3971 |
| Package smoke test | `scripts/verify-stage-package-smoke` | 6 |
| GitHub Actions audit | `scripts/verify-stage-github-actions-audit` | 1 |
| TOTAL | — | 4002 |

七個階段秒數總和（10+10+2+2+3971+6+1）等於同次執行回報的 TOTAL 4002 秒。

`scripts/ci_tier.py` 另外輸出 `run_governance`／`run_osv`／`run_zizmor`／`upload_site`
四個欄位，供 plan 摘要與相容呼叫端使用；本機與 hosted `verify-fast` 直接以同一份 plan 的 `scopes`
調度子集，不維護第二套分類邏輯。

`scripts/resolve-cache-root` 預設已經是使用者層級、跨 worktree 共用的位置（macOS 為
`~/Library/Caches/csarc`；Linux／WSL2 依 XDG Base Directory 慣例，優先讀
`$XDG_CACHE_HOME`，沒設定則用 `~/.cache/csarc`；判斷邏輯依 `uname` 明確分流平台，找
不到或無法寫入時 fail-safe 退回 repo-local 的 `.cache/`，快取只是效能優化，不影響驗
證正確性），`uv`、`pnpm` 與固定版本工具因此預設就會共用已驗證的下載內容並依版本與平
台分隔，不必手動設定。`.venv`、`node_modules`、生成 fixture、checkout 與測試結果仍
逐 worktree 隔離，快取命中不代表測試通過；損壞內容依固定 checksum 重新下載或失敗。
想改用團隊約定的其他持久路徑，仍可用 `CSARC_CACHE_ROOT` 明確覆寫，例如：

```bash
CSARC_CACHE_ROOT="$HOME/.cache/csarc" ./scripts/verify-template.sh
```

### 本機驗證分級判斷原則（cheap-stage-first，#538）

上方三層成本邊界只回答「這次改動落在哪一級」，Base-only re-merge 例外只回答「既有本機
full 能不能沿用」。這裡把「這次到底要不要在本機跑 full」與「真的要跑時如何排序」寫成
可執行原則，延續這次 session 已經在用、源自
Milestone 8（#465／#466）教訓的 cheap-stage-first 模式，避免重演本機測試反覆鬼打牆
（redundant full rerun、網路瞬斷、環境競爭噪音耗掉大量時間）。

**先判斷要不要在本機跑，依序四步：**

1. 先看 `verification_mode`。hosted 模式只跑變更 owner 的 focused checks；
   `./scripts/verify-fast` 留作可選廣泛診斷，不因 plan 選到 full 就在本機重跑 aggregate suite。
   required merge evidence 由 hosted `verify` 對 exact candidate 執行一次。
2. local 模式在 committed、clean 的最終候選執行一次 `verify-fast`；同一 router 需要時會自動
   升級 full，並把結果記成 exact-head self-attested evidence，不再為了證明重跑第二次。
3. hosted 模式只有文件明定的 fallback 或 maintainer 明確要求診斷時才需要本機 full。若同一
   branch 已經有一輪本機 full、只是 base 前進，先套用上方「Base-only re-merge 例外（#468）」；
   符合全部條件即可沿用本機結果，新的 exact tip 仍由 hosted `verify` 驗證。
4. fallback／診斷確實需要新的本機 full 時，開始前先確認沒有其他 worktree／`pytest`／
   `verify`／`copier` 程序同時佔用本機資源——上方「逐階段耗時量測（#465）」記錄的 4002
   秒即混入另一個 worktree 的背景負載，不是乾淨基準，容易把負載噪音誤判成回歸。

**真的要在本機跑一次全套時，依 cheap-stage-first 排序，不要悶頭跑到底才發現問題：**

- 先跑上方「`scripts/verify-template.sh` 階段盤點（#458）」六個便宜階段（Repository
  contracts、Static assets and paired files、Python environment、Python quality、
  Package smoke test、GitHub Actions audit；#465 量測每階段 ≤10 秒），用對應的
  `scripts/verify-stage-<name>` 逐一單獨執行，不必等待整條聚合器。
- 六個便宜階段全部 PASSED，才進入唯一昂貴的 Regression tests 階段（#465 量測 3971 秒，
  佔同次 TOTAL 九成以上）；任一便宜階段先失敗，就先處理該階段本身，不必先跑完昂貴階段。
- Regression tests 若因暫時性錯誤中止（例如 #465 記錄的
  `curl: (92) HTTP/2 stream ... PROTOCOL_ERROR` 網路瞬斷），只用
  `scripts/verify-stage-regression-tests` 單獨重跑這一階段，不必連同已經 PASSED 的六個
  便宜階段一起重跑整支聚合器。
- 任務進行中一旦發現「其實有更便宜的路徑」（例如原本以為要本機全跑，後來發現符合
  base-only re-merge 例外，或某階段本次 session 已經驗證過），立刻重新評估同一 session
  內所有**還沒開始**的驗證步驟，不要因為原計畫已經寫好就照舊執行；已經真正執行並拿到結果
  的步驟不必重跑。

以上四步不減少 full 的內容：hosted 模式只是把 authoritative full 固定留在 trusted runner
執行一次；local 模式與 fallback 仍依各自證據契約執行。merge 資格與 required check 仍由
Journey 08 與本文件既有規則決定。

## 版本、發版、交付與部署矩陣

| 邊界 | Issue／工作 PR | Milestone／canary 交付 PR | `main` | tag／manual event |
| --- | --- | --- | --- | --- |
| 版本意圖 | PR title 表達 major／minor／patch／no-release | 彙整已核准意圖，不自行配置版本 | 保留已審查內容 | 不從 tag 反推或改寫 source |
| 精確版本與 CHANGELOG | 原 Milestone work PR 的 final release-only commit materialize 下一個 beta | promotion bridge materialize stable 與 CHANGELOG | standalone／hotfix 原 PR materialize stable | manual 只重跑同一流程，不另開版本來源 |
| CI | beta 的最低組合是 fast，路徑風險可升 full | stable 一律 full | release workflow 重用 exact candidate 的可信證據，缺少時只補跑所需 tier | 不重複已具備且仍有效的 routine suite |
| 成品／checksum／SBOM | 合併進 `dev/m*` 後從精確 commit 發 beta prerelease | 合併後從精確 main commit 發 stable | stable 候選合併後從精確 commit建立 | draft Release 先上傳、下載重驗，成功才公開 |
| tag／GitHub Release | `X.Y.Z-beta.N` | `X.Y.Z`；成功才關 tracker 與 Milestone | `X.Y.Z` | 重跑只驗同一 tag；不移動 tag、不重寫成品 |
| attestation／registry | 不建立 | 不建立 | 不自動啟用 | #439 已移除設定面（零 active 消費者），非留待選配 |
| deployment | 不適用 | 不適用 | 不適用 | 由有真實 runtime target 的產品 repo 定義 |

合併到 `main` 是 repository delivery，不等於 Release。CSARC-owned Milestone 把版本檔與
CHANGELOG 納入同一張 promotion PR，但 tracker 與 Milestone 要等唯一 `release.yml` 成功
發布並驗證後才關閉；promotion body 用 `Refs #N`，不使用會在 merge 當下提早結案的
`Closes #N`。發布失敗時維持 open，重跑沿用同一候選與 Release。Standalone work 與 hotfix
也在原 PR 物化 stable；既有 repo 保留 product-owned release workflow，Copier 不依檔名
猜測、不覆寫也不重複 dispatch。流程只用短效 `GITHUB_TOKEN`，不要求 GitHub App、PAT、
registry token 或空 deployment environment。

### 版本通道與專案成熟度（Issue #918，2026-09-23）

公開版本只接受 `X.Y.Z-beta.N` 與 `X.Y.Z`。前者是 beta prerelease，後者是 stable；
沒有公開 alpha，也沒有獨立 RC。`early`／`formal` 不再出現在版本後綴或每張 Issue 的
發布層級，而是 `.csarc/config.yml` 的 `project_maturity` 宣告。它只會在一張明確的
standalone stable 變更中由 `early` 改為 `formal`；沒有宣告時維持 `early`。

CLI 預設只選最新 stable，使用者明確傳入 `--channel beta` 才選 beta。解析器不保留
`alpha` 相容路徑；記錄到已退役、格式錯誤或無法理解的版本時，`csarc update` 會改以
最新 stable 重建模板管理的基線，沿用 adopt 的交易式差異計畫，盡可能保留
`.csarc/config.yml`、專案自有內容與已分歧檔案，並把無法安全合併的項目交給人工處理。
身分、簽章、attestation 或 tag 移動等信任失敗仍 fail closed，不能偽裝成版本格式問題。

歷史 `v0.18.0-alpha.1` 至 `v0.21.0-alpha.1` 以同一 commit 建立 `-beta.1` replacement，
驗證新 Release 的 commit、prerelease 旗標、immutable attestation 與 assets 後，才刪除
舊 Release/tag；任一檢查失敗就保留原件並停止。

### 已取代：四層版本號模型（Issue #744，2026-09-17）

> 以下保留歷史決策脈絡；現行版本規則以上方 #918 為準。

版本號本身就是發布層級，不是另外一個側欄狀態：alpha 為 `X.Y.Z-alpha.N`；beta 為
`X.Y.Z-beta.N`（0.x 或 1.x 都可以）；早期版為不帶後綴的 `0.y.z`；正式版為 `1.0.0`
起不帶後綴。同一版本號的後續 pre-release 遞增 `.N`（tag 名稱不能重用）；alpha／beta
任何時候都可以發布，包含在早期版或正式版之後。發版層級取自上次發版以來所含工作的
最高宣告層級——**宣告與計算機制由 #745 提供**，本節與 `scripts/release_policy.py`／
`scripts/publish-release`／`scripts/converge-release-tag` 只負責把一個已宣告的層級
轉成合法版本號並正確發布：`release_policy.py plan`／`prepare-candidate` 接受
`--phase {alpha,beta,early,formal}`。**pre-release 後綴代表發布層級，不保證之後
會發該版本的無後綴版本**：`X.Y.Z-alpha.N`／`X.Y.Z-beta.N` 只承諾「這是目前宣告的
成熟度」，不承諾同一個 `X.Y.Z` 之後一定會有對應的無後綴（早期版或正式版）發布——
下一次發版可能直接跳到更高的版本號，或維持原地再發一次更高的 `.N`。版本號合法性由
`scripts/release_phase.py`
（`template/.csarc/scripts/` 與 `src/csarc_cli/release_phase.py` 各有一份逐位元組相同的
副本，後者是因為 `csarc` 發行的 wheel 只包含 `src/csarc_cli`，見其模組
docstring）驗證：主版本號為 0 時不帶後綴即為早期版，主版本號 ≥ 1 時不帶後綴即為
正式版，後綴只接受 `alpha.N`／`beta.N`，其他一律 fail closed。`gh release create`
依 tag 是否帶後綴決定要不要傳 `--prerelease`；`gh release edit ... --draft=false`
只在無後綴版本才加 `--latest`（pre-release 不該被標成「最新」）。

CLI（`src/csarc_cli/cli.py`）的 `release_identity()` 接受 immutable、已發布的
pre-release Release：tag 必須是合法版本號，且 GitHub 回報的 `prerelease` 旗標要與
tag 格式一致，其餘既有驗證（immutable、attestation、tag 指向未移動、commit
signature）全部保留。選「最新」版本改用 SemVer 優先序（`GhReleaseClient._latest()`
分頁列出所有已發布、非 draft 的 Release 再挑最高者），不再依賴 GitHub
`releases/latest` API（該 API 不回傳 `prerelease: true` 的 Release）。

保留規則（decision 5）：保留所有不帶後綴的版本（早期版與正式版），外加依
major.minor 分組後最新一組的最新一個 pre-release；較舊分組或同分組較舊的
pre-release 列為應刪除。`scripts/release_policy.py retention-plan --repo OWNER/NAME`
只列出清單（dry-run），不呼叫任何刪除 API；實際刪除是 Milestone 14 promotion 後
由維護者人工執行的動作，記錄在 #740 的 Completion evidence，不是任何工作 PR 的
合併條件。下游 `csarc update` 若確認記錄的 `release_tag` 在 canonical repository
已不存在（GitHub 回報 404，`ReleaseNotFoundError`），改走重新安裝流程：重用
`csarc adopt`（#219）同一套 transactional plan 機制列出新增／覆寫／保留／人工合併
項目，經使用者確認才套用，project-owned 檔案一律保留；只有 tag 確認不存在才觸發，
其他驗證失敗（attestation 不符、tag 指向改變、簽章無效、repository identity 不符）
一律維持 fail closed。詳見 `docs/adr/release-security-and-dependencies.md` 與
`docs/adr/transactional-repository-adoption.md` 的新增段落。

同 PR 候選的成功檢查只對當時的 destination base 有效。正式
`scripts/pr_lifecycle.py merge` 會在 remote lease 綁定的 current base 上重跑
`release_policy.py verify-delivery-version`，確認 head 的最後一個 commit 恰好是從前一個
implementation commit 產生的 release surfaces；`scripts/publish-release stage` 在發布前再以
來源 PR 與 merge tree 重驗。Base 一旦前進，agent 必須先同步並重新 materialize，舊 base 的
成功 status 不得滿足最終邊界（#817、#925）。

## Conditional 與退役能力

`scripts/verify_release_consumption.py` 與其測試保留為 conditional 的消費端安全契約。
checksum 與 SPDX SBOM 已由 `scripts/release_bundle.py` 納入 GitHub Release；production-side
attestation 與 registry publishing 已由 #439 判定零 active 消費者並移除設定面，不是留待接上
的 conditional 選項——需要時另開 Issue 明列真實 owner、權限與執行者。消費端門禁仍是獨立的
conditional 契約，與此無關。

歷史的 Release Please、artifact handoff 與 release follow-up 已由一支 `release.yml` 和兩個
repo-local 入口取代；promotion、delivery maintenance、release consumption 與 live integration
專用 workflow 不恢復。已決定的 archive copy 已刪除，歷史由 Git／Issue／PR 保存。Zizmor
與 remote-governance 的舊 workflow 由各自 Journey 另行決定。

## Failure 與 fallback

- 分類器無法判斷時升級 full，不以 skipped 或 zero-step 當成功證據。
- Hosted Actions 不可用時，維護者執行相同 repo-local 入口並附上 commit、命令與結果；
  required check 仍不得被繞過。
- 版本候選驗證失敗時，候選 SHA 明確收到 failure status；GitHub 拒絕 tag／Release write 時
  明確標示 Blocked，不改走本機直接發布；發布失敗時 Release 保持 draft。
  重跑會先清掉 draft 的舊 assets，再建立並驗證同一精確 bundle。
- Milestone delivery branch 只在 final delivery 前同步當時最新 `main`；只有明列真實相依
  才提前同步，不對所有 branch fan-out。
- 合併後自動刪除一般來源 branch；Milestone／canary branch 等人工確認結案與 evidence 後
  刪除。`scripts/cleanup-worktrees --apply` 只清除乾淨、未鎖定且可證明已合併的本機 worktree。
- 沒有真實成品、owner、權限或 live run 時，狀態保持 manual、conditional、blocked 或
  not applicable，不以歷史成功補足。

### 過時 delivery branch 偵測（stale branch detection，#667）

2026-09-04 人工盤點遠端 branch 時找到 9 個長期殘留的過時 branch（例如
`type/524-lightweight-render-engine`、`fix/441-delivery-manual-contract`、
`dev/m9-decision-site-adoption`）。逐一查證：全部對應 PR 都是**關閉但未合併**，實際
work 都已透過後續重新命名或重新開的 PR 落地，只能手動刪除。

**根因**：上面「合併後自動刪除一般來源 branch」這條 fallback 依賴的是
`delete_branch_on_merge`（`policies/repository.json`）——這個設定只在 PR **合併**時
觸發，一個 PR 被**關閉但未合併**時，它的來源 branch 完全不受這個設定保護，會無限期
殘留，過去沒有任何偵測機制。這批 debris 本身是這個設定生效之前留下的舊帳，不是設定
持續在漏；但設定本身也從未被驗證過仍是 `true`，且 Milestone-adjacent 但被遺忘的
branch（如 `dev/m9-decision-site-adoption`）沒有任何提醒機制，只能靠人工偶然發現。

**分工（兩者互補，不重疊）：**

| 機制 | 觸發時機 | 涵蓋範圍 | 動作 |
| --- | --- | --- | --- |
| `delete_branch_on_merge`（既有） | PR 合併瞬間 | 合併成功的 PR 來源 branch | 自動刪除 |
| `scripts/apply-repository-settings.sh check`（既有，本節確認涵蓋） | 手動／CI 執行時 | `delete_branch_on_merge` 這個 repo 設定本身是否仍是 `true` | 只回報 drift，不刪除任何 branch |
| `scripts/stale_branch_detection.py`（本節新增） | Milestone preflight／release preflight 執行時 | 關閉未合併、或從未開過 PR 的過時 branch | 只回報候選清單，**不刪除** |

**`apply-repository-settings.sh check` 的確認結果**：`delete_branch_on_merge` 已經是
`policies/repository.json` 的既有欄位，`check` 子指令既有的 repository-settings drift
比對是對這個檔案裡每一個欄位做通用逐一比對（與 `pull_request_creation_policy` 完全
同一段邏輯，沒有各自獨立的程式碼），因此 `delete_branch_on_merge` 被意外關閉時本來就
會被這段既有邏輯抓到——不需要新增專屬程式碼，只需要補上一個回歸測試案例證明涵蓋範圍
（`scripts/test-apply-repository-settings` 的 Case 3b）。

**偵測邏輯（`scripts/stale_branch_detection.py`）**：列出遠端 branch 中同時符合以下
三項的候選：(a) 沒有對應的 open PR（含跨 repo fork PR 不算數，因為那個 PR 的
`headRefName` 是 fork 裡的 branch，不是本 repo 的）、(b) 不是 `main`、`dev/m<N>-<slug>`
（Milestone delivery branch，形狀與 `promotion_gate.py` 的 `MILESTONE_BRANCH` 一致）、
或 `csarc/*`（機器管理的基礎設施 ref：`scripts/pr_lifecycle.py` 寫入的
`csarc/leases/*` PR lifecycle lease，與交易 ledger `csarc/dev-next-preservation-ledger`
——兩者都不是 work branch）、(c) 最後一次 commit 距今超過門檻天數。只回報候選清單，
**從不自動刪除**——沒有 PR 的 branch 也可能只是還沒開 PR 的進行中工作，自動刪除風險
太高。

**門檻：預設 30 天。** 一個關閉未合併的 branch 幾乎肯定永久不會再有新 commit，所以門檻
本身對「真的殘留」而言不敏感；真正的風險方向相反——誤判仍在進行中的正常工作為
「過時」。本 repo 常態同時有數十條各自獨立 worktree／branch 平行推進（見本文件多處
描述的派工模式），因 review 排隊或依賴其他 PR 而安靜一到數週是正常現象，不代表放棄。
30 天足以涵蓋這種正常空窗期，同時仍能在大約一個月內就攔截真正的殘留，不會像這次找到
的 9 個 branch 一樣累積數月才被人工發現。可用 `threshold_days` 參數覆寫。

**掛載點（兩個既有自我檢核入口，刻意不新開排程 workflow）：**

- `scripts/sync_milestone_state.py preflight`：每次驗證 Milestone metadata 時，一併
  印出過時 branch review 清單（純提示，never 影響 `preflight` 本身的 pass/fail —
  這與這個 Milestone 的 metadata 是否就緒無關）。
- `scripts/release_policy.py preflight`：與既有 `integrations`（Renovate 安裝建議）
  同一種 advisory 資料，掛在 JSON 報告的 `repo_hygiene` 欄位下——發版是另一個天然的
  「該回頭看一下 repo 衛生狀況」時機點，同樣純提示，never 讓一次發版因為有過時 branch
  候選而被擋下。任何 `gh` 呼叫失敗都會被吸收成 `"available": false` 而不是拋出例外，
  因為這個檢查不應該因為自己不可用就連帶擋住不相關的 Milestone 或發版流程。

### Repo 能力自我檢查與 workaround 對照（capability matrix，#531）

`scripts/apply-repository-settings.sh` 既有的 `DEGRADED` 機制回答的是「這個帳號的
GitHub 方案允許什麼」；但同一個方案上，organization 政策、CODEOWNERS team 是否存在、
token 權限範圍，仍可能個別擋住某一項能力——這一層目前沒有自動檢查，也沒有把 workaround
集中寫清楚。`policies/capability-matrix.json` 補上這份「repo 能力矩陣」：每一項能力
（`repository_admin`、`ruleset_enforcement`、`codeowners_enforcement`、
`actions_pr_approval`、`security_and_analysis`、`github_pages`、
`repository_settings_inspection`、`immutable_releases`）各自對應最低權限／方案需求、
偵測方式與已記錄的 workaround。`scripts/repo_capabilities.py` 是純邏輯的 evaluator（三態
`allowed`／`blocked`／`unknown`，與 `docs/adr/capability-aware-governance.md` 既有的
三態慣例一致），`scripts/check-repo-capabilities` 則是即時對這個 repo 探測、組成 facts
再交給 evaluator 的唯讀入口——只回報，不寫入 GitHub，也不是新的合併關卡。

刻意的邊界（Issue #531）：這套機制不重新設計 `apply-repository-settings.sh` 既有的
`DEGRADED` 標記本身；矩陣裡每一列的 workaround，只要底層限制原本就有對應的
`DEGRADED` 字樣（Ruleset、CODEOWNERS 檢查、Actions PR 政策、`security_and_analysis`、
GitHub Pages 五項），就直接引用同一段既有訊息，而不是另建一套平行說法。`policies/
capability-matrix.json` 與 repo-site「安裝說明」頁維運模式下的能力矩陣說明框
（`docs/index.html#install`）互為單一來源：矩陣是機器可讀的權威內容，頁面是給人看的雙語呈現，兩者由
`tests/test_advanced_install_content.py` 的每一個能力 id 都必須同時出現在雙語頁面這條
規則機械式對齊。`immutable_releases` 一列例外：它無法單靠 repository 權限探測判斷，一律
回報 `unknown`，並指向上面「hosted 發版路徑的已知限制」一節，而不是假裝可以自動判定。

### Release 發版不依賴 Actions 健康度的 fallback（#589，2026-09-03）

2026-09-03 的實際事故（#587）證明「發版」目前完全綁在 `release.yml` 這一支 workflow 是否能在 GitHub Actions 上成功執行：M8 promotion 後，`docs/index.html` 過期讓 full-tier 驗證卡住，`main` 上每一次 push 觸發的 `release.yml` run 全部失敗，加上同一天稍早出現的 `pull_request` webhook 投遞間歇性異常，讓「能不能發版」完全停擺超過 8 小時、沒有人自動被通知，直到人工檢查 Releases 頁面才發現。既有的「Actions 額度 fallback」（見 [staged-delivery-and-verification ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/staged-delivery-and-verification.md)）解決的是不同的觸發條件：額度用盡有 GitHub 回傳的明確錯誤訊息（zero-step billing block），可以機械式偵測；本節處理的觸發條件——hosted runner 卡住、webhook 沒有投遞、或其他導致 Actions 本身不健康的狀況——**沒有對應的機械式訊號**：它看起來就是「什麼都沒發生」，而「什麼都沒發生」本來就有可能只是因為沒有東西需要發版。這個不對稱是本節 fallback 刻意設計成「人或 agent 主動決定啟用」而非自動觸發的原因，也是為什麼另外需要一道獨立排程的存量檢查——這道檢查因範圍與時間考量從 #589 拆分為獨立追蹤，已落地為下方「發版存量漂移偵測（`release-drift.yml`，#605）」一節。

**設計：** #589 的 Guided 名稱現在只表示「由維護者或 agent 在本機呼叫 publisher」，不再表示另開版本 PR。#925 要求所有候選都已在原交付 PR 內產生並通過同一 review；Actions／webhook 不健康時，只把合併後的發布步驟（建 tag、draft Release、build 成品、checksum、SPDX SBOM、`gh release` 系列指令）切到本機執行。`release.yml` 與本機路徑呼叫同一份 `scripts/publish-release`，不維持兩套邏輯，也不能藉本機執行省略審查。

**代價（不能只講好處）：**

- **放棄 hosted runner 的乾淨、一致環境保證。** 本機執行的環境不由 GitHub 控管；只有本機 `full` 驗證全綠才能視為等同 hosted 的證明強度。
- **需要本機或執行者持有具備 admin／write 權限的長效憑證，而不是 Actions 短效 `GITHUB_TOKEN`。** 這不是為所有 CSARC-owned repo 新增一項標準要求——`scripts/apply-repository-settings.sh apply` 本來就已經要求 repo admin 用自己的 `gh` 身分執行；本節只是讓同一位已經持有這個權限的維護者，多一個「用同一身分完成發版」的選項。
- **沒有 merge 後自動觸發，需要人或排程主動執行。** 需要另外一道獨立排程的存量檢查偵測「`main` 已經前進，但過去 N 小時內沒有明確的 `no-release` run 或有效的 immutable stable GitHub Release」，取代目前完全仰賴人工檢查 Releases 頁面才會發現的狀態；這道檢查已由 `.github/workflows/release-drift.yml`／`scripts/check-release-drift` 落地，見下方「發版存量漂移偵測（`release-drift.yml`，#605）」一節。
- **本機執行結果的可稽核性不如 hosted run 的公開 log。** 緩解方式是強制在合併說明或 Issue 留言記錄執行者、commit SHA、指令與結果。
- **local-vs-hosted 邏輯漂移風險。** 緩解方式是本節設計的第一原則——單一 repo-local 腳本被兩種呼叫方式共用。

**明確保留 GitHub Actions 為預設／建議路徑，不是全面棄用**：`verify`／`title`／`review` 三個 required status check 仍然、也必須繼續只由 hosted Actions 產生；CodeQL 上傳到 GitHub 原生 code-scanning 介面同樣不在本節適用範圍。

### hosted 發版路徑的已知限制，本機路徑升格為標準程序（2026-09-03）

上一段原本建議「一般情況下仍走 hosted `release.yml`」；當天稍後的補發版嘗試（接續 #587）證明這個建議不成立，予以修正：

`scripts/release_policy.py::detect_runtime_capabilities()` 對 `immutable_releases` 的 capability probe（`GET repos/{repo}/immutable-releases`）在 hosted release job 自己的 `GITHUB_TOKEN` 下**結構性、永久性**回傳無法判斷（HTTP 403）——這個端點屬於 repo administration 層級設定，GitHub Actions 的 `permissions:` 區塊沒有對應的合法 key 能開放給 `GITHUB_TOKEN`（曾誤加 `administration: read` 這個不存在的 key，直接讓 workflow YAML 整個 parse 失敗，見 #623／#624 的踩坑與回退記錄）。`select_release_mode()` 的 `PUBLISH_CAPABILITIES` 判定是 all-or-nothing（`contents`／`release`／`immutable_releases` 任一項 `blocked` 或 `unknown` 就整組判 `blocked`），Automatic 與 Guided 共用同一個前置關卡，兩條路徑都永遠過不了這一關——不是暫時性環境問題，也不是這次補發版才出現的新退化。

`docs/ci-policy.md` 更早已經記錄過同一現象源自 #123 的既有設計：HTTP 403 時 fail-closed 是**刻意的安全姿態**（拿不到證據就不發版），不是 bug。當時盤點過三個修法方向後（見 [#626](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/626) 完整記錄）：

1. 改成信任 `policies/releases.json` 宣告值、不再即時 probe——會推翻 #123 的立場，驗證變裝飾性，**不採用**。
2. 給 release job 一個只有 `administration: read` 的窄範圍 PAT repo secret——技術可行、不推翻 #123，但需要新增並之後輪替一個 secret，維護者評估管理成本後**不採用**。
3. **當時採用**：正式承認 hosted Automatic／Guided 對 `immutable_releases` 永遠無法自證，把本節上方的本機 `scripts/publish-release` 路徑從「fallback」升格為**標準發版程序**——不是備援，是預設做法；由 agent（Claude Code session）在維護者授權下本機執行，用維護者自己的 admin 身份，天生就能真的讀到這個設定，不需要額外 secret，也不推翻 #123。「自動化」的著力點從「push 進 main 自動觸發」改成「agent 執行、人不用碰指令」。

**2026-09-18 追加第四個方向，取代上面「當時採用」的結論（#770）：** #626 當時只盤點了「換一種需要額外憑證的 token」的方向（方向二的 PAT），沒有評估「用另一種、這個 repo 已經信任的機制去證明同一件事」。實測證實：GitHub 只在 Immutable Releases 真的啟用時，才會為一則 Release 自動簽發一份 signed release attestation（in-toto predicate `https://in-toto.io/attestation/release/v0.2`，signer `https://dotcom.releases.github.com`，Sigstore-backed）；查詢這份 attestation（`GET /repos/{owner}/{repo}/attestations/{digest}`）對 public repo 是匿名可讀的公開 API，不需要 admin scope，`GITHUB_TOKEN` 讀得到。`gh release verify <tag> --repo <repo> --format json` 的輸出剛好就是既有 `scripts/verify_release_consumption.py::verify_consumption()` 期待的 `--verification-json` 輸入格式（注意：是 `gh release verify`，不是 `gh attestation verify`——後者的預設 cert-oidc-issuer／identity 政策是為一般 Actions workflow 簽署設計，對這個 GitHub 自己簽的 release-predicate attestation 類型會誤報「no attestations found」）。

**因此，`scripts/release_policy.py` 移除了 `immutable_releases` 這一項 pre-flight probe**（`PUBLISH_CAPABILITIES` 現在只有 `contents`／`release` 兩項），不再讓它單獨造成 `select_release_mode()` 整組判 `blocked`。取而代之，`scripts/publish-release`（`publish`／`rerun-verify` 子命令）在 Release 轉為正式發布、GitHub 回報 `isImmutable` 之後，新增一道 post-hoc 驗證：呼叫 `gh release verify --format json` 取得同一份 attestation，重用（不重寫）`verify_consumption()` 對每一個上傳成品核對 signer、repository、repositoryId、tag、commit 與 SHA-256 digest。任一失敗都會讓既有的 `revert_to_draft_on_failure` 介入——若 GitHub 尚未把這次發布判定為 immutable（常見情形：Immutable Releases 從未被真的啟用），Release 會被收回 draft；若 GitHub 已經判定 immutable（理論上的攻擊或竄改情境，而非「設定沒開」的常見情形），已經無法再改回 draft——這是 Immutable Releases 這個 GitHub 功能本身的定義，不是本次變更引入的新限制，此時腳本仍會以非零結束、絕不回報假成功。

**hosted Automatic／Guided 的實際狀態變化：** 移除這一項 pre-flight probe 後，hosted `release.yml` 不再因為這一項**結構性、永久性**卡死——只要 `contents`／`release` 兩項能力可用（過去實測通常可用），流程會實際跑到 `publish` 步驟，而不是像過去一樣連工具鏈安裝都到不了。是否真的成功發布，現在取決於這個 repo 的 Immutable Releases 設定是否已由 admin 用 `scripts/apply-repository-settings.sh apply` 真的開啟過（見上面「Repo 能力自我檢查與 workaround 對照」一節）——沒開啟時，發布會在 post-hoc 驗證這一步 fail closed 並收回 draft，而不是完全無法開始；已開啟時，hosted Automatic／Guided 現在可以真正端到端成功，不再是「已知限制，非待修復項目」。這不推翻 #123 的 fail-closed 立場，也沒有落入 #626 當時否決的 PAT／GitHub App 範疇——只是把同一個問題換一種這個 repo 已經信任、且 `GITHUB_TOKEN` 讀得到的機制去自證。

`release.yml` 仍在每次 `main` push 上執行，但只在 checkout 後先用 runner 內建的 Python／Git
完成 release plan；`no-release` 直接結束，不探測 capability、不驗證 attestation，也不安裝
Python 3.14、uv、pnpm、Node 或 Rust。需要發版時才探測 capability；若 publication
為 `blocked`（現在只可能來自 `contents`／`release`），維持 #123 的
fail-closed 結果並在工具鏈 setup 前停止。只有未被擋下的實際 release 路徑才先嘗試重用來源 PR
的可信 hosted verification；來源與 main tree 不同、證據過期或查證失敗時，改在 release workflow
對 exact main tree 重跑 full，接著才驗證已物化候選並發布（#707）。這只把便宜判定移到前面，
不放寬驗證、權限或供應鏈要求。

### Release 說明文字的最低格式規範（#616）

M8 補發版（#587）過程中曾發現：當時的 `release.yml` 把 GitHub Release 說明文字交給
`googleapis/release-please-action`（Automatic）或本機 candidate 產生，卻沒有規定
「一則正式 Release 的說明文字最低限度要包含什麼」。#925 已移除 post-merge version PR；
現在版本與 CHANGELOG 一律由原交付 PR 物化，而 hosted Actions 與本機仍共用下列唯一 publisher。

**盤點結論：整個 repo 只有一個程式碼路徑會建立 Release 說明文字。**
`scripts/converge-release-tag` 是唯一呼叫 `gh release create` 的地方：

```bash
gh release create "$tag" --target "$sha" \
  --title "$tag" --draft --generate-notes
```

`scripts/publish-release stage`（hosted 與本機共用同一個進入點）呼叫這支腳本；
`release.yml` 與本機執行都呼叫同一份 `scripts/publish-release`。版本與 CHANGELOG 已由
原交付 PR 的 `release_policy.py prepare-candidate` 產生；合併後不再執行 Release Please 或
建立另一張 PR。所有路徑最終都收斂到
`converge-release-tag` 這同一行呼叫——不是兩套各自維護、恰好長得很像的邏輯，而是結構上
只有一份實作，呼應 #589 決定本身的第一原則（單一 repo-local 腳本被兩種呼叫方式共用）。
`scripts/publish-release` 之後唯二對同一 Release 的寫入是 `gh release edit "$tag"
--draft` 與 `gh release edit "$tag" --draft=false --latest`（`cmd_publish`／
`revert_to_draft_on_failure`），兩者都不帶 `--notes`／`--notes-file`，不會覆寫或附加任何
自由格式文字到 `--generate-notes` 已寫入的內容。

**最低必要欄位——已經是結構保證，不是待補的規範：**

| 欄位 | 來源 | 保證方式 |
| --- | --- | --- |
| 版本號 | `gh release create "$tag" --title "$tag"` | Release 標題固定等於 `release_policy.py` 算出的 tag；不存在自由輸入版本號的路徑 |
| 發布日期 | GitHub 平台的 Release 建立／`publishedAt` metadata | `--draft=false` 轉為正式發布時由 GitHub 自動蓋章；不需要、也不必在說明文字內容裡重複 |
| 變更摘要 | `--generate-notes` 產生的「What's Changed」PR 清單＋前一版比較連結 | GitHub 依 merged PR 標題（本 repo 的合併 commit 標題慣例採 Conventional Commits，`release_policy.py::release_intent` 依此判斷版本影響）自動彙整；沒有人工輸入步驟可以省略或打錯 |

**刻意不要求「已知限制」／「回溯相容性」等額外欄位，不強制每則 Release 都要有這兩段：**

1. 大部分 patch／dependency-bump 等級的 Release 沒有實質已知限制或破壞性變更；逐則
   要求填寫只會製造樣板空段落，稀釋真正需要注意的內容，不會提高訊號。
2. 破壞性變更本身已經有機制承載：PR／commit 標題的 `!` 標記與 `BREAKING CHANGE:` 會被
   `release_policy.py::release_intent` 判成 major，反映在 Guided 路徑
   `_write_changelog` 產生的 CHANGELOG.md「Breaking Changes」小節與 Automatic 路徑
   release-please 自己產生的 CHANGELOG 段落；`--generate-notes` 的 PR 清單本身也會列出
   該次變更對應的 PR，讀者可從 PR 內容取得細節，不需要在 Release 說明文字裡重述一次。
3. 真正跨版本持續有效、不是「這一版特有」的已知限制（例如上一節的 hosted
   Automatic／Guided 對 `immutable_releases` 永遠無法自證），本來就屬於維護一次、隨時
   查閱的專案文件，而不是需要在每一則 Release 說明文字裡重複貼一次、還容易隨時間跟實際
   狀況脫節的內容——這類內容留在 `docs/ci-policy.md` 與 repo-site，Release 說明文字不必
   自我複製（見下方 repo-site 頁面章節）。

**CHANGELOG.md 與 GitHub Release 說明文字是兩個各自獨立、都真實但不相同的視角，刻意不
強制兩者逐字一致：** `CHANGELOG.md`（Guided 路徑的 `_write_changelog`，或 Automatic 路徑
release-please 自己的產生邏輯）以 Conventional Commit 的 intent 分類（Breaking
Changes／Features／Bug Fixes）列出 commit 層級的變更；GitHub Release 說明文字
（`--generate-notes`）以 PR 層級列出「What's Changed」＋作者＋比較連結。兩者的分類軸線
不同，但共同來源都是同一批 merged 內容，不會出現「這個環境看得到的變更、另一個環境看
不到」的實質落差，只是呈現角度不同——讀者在任一邊都能找到同一批變更。

**評估結論：不需要額外的結構化格式一致性檢查腳本。** 理由：

1. 上面盤點已經證明 hosted 與本機路徑呼叫的是同一支 `scripts/publish-release`（進而
   呼叫同一支 `scripts/converge-release-tag`）——不存在兩份平行實作會長期漂移的風險；
   #589 設計本身的第一原則已經涵蓋這裡，不需要為這個 Issue 另外重新解決一次。
2. 一個額外的格式檢查腳本，若要驗證的對象是 `--generate-notes` 產生的自由格式文字內容
   本身，等於要對 GitHub 平台自己產生、不受本 repo 控制的文字做格式驗證；其確切呈現
   （標題階層、項目符號、compare 連結措辭）屬於 GitHub 產品行為，寫死格式斷言容易在
   GitHub 調整呈現方式時變成假陽性失敗，卻不代表本 repo 自己的邏輯真的壞了。
3. 真正值得防的風險——未來有人繞過 `converge-release-tag`、另開一個呼叫路徑，各自帶
   不同 flag（例如漏掉 `--generate-notes`，或加上覆寫用的 `--notes`）——是程式碼結構
   層級的問題，用回歸測試斷言「整個 repo 只有一個 `gh release create` 呼叫點，且該
   呼叫點的 flag 組合不變、沒有其他地方對 Release 呼叫 `--notes`／`--notes-file`」就能
   可靠涵蓋，不需要解析或驗證產生出來的自由格式文字內容本身。
   `tests/test_release_notes_format.py` 落地這個斷言，掛在 `scripts/verify-fast`
   既有的 `uv run pytest` 範圍內，每次 PR 都跑，不需要另外的 full-tier 專屬階段。

**下發到 `template/`：** `scripts/converge-release-tag`／`scripts/publish-release` 已
透過 `scripts/sync-paired-files.sh` 與 root 逐位元組同步（見上兩節），本節的格式契約
不需要第二份實作，也不需要另外的 Copier 選項或下發決定。

### 發版存量漂移偵測（`release-drift.yml`，#605）

上面兩節解決「怎麼發版」與「hosted 路徑為什麼結構性過不了關」；兩者都沒有回答「發版流程本身停擺了，誰會知道」。2026-09-03 的 #587 事故正是在完全沒有人被通知的情況下，靠人工檢查 Releases 頁面才發現發版已經停擺超過 8 小時——本節把 #589 決定裡列為代價、當時尚未落地的那道獨立排程存量檢查做成具體實作。

**設計：** 新增獨立、只讀、與 `release.yml` 完全解耦的排程 workflow `.github/workflows/release-drift.yml`（`schedule` 每日一次＋`workflow_dispatch`，權限只有 `actions: read`／`contents: read`／`pull-requests: read`／`issues: write`，5 分鐘 timeout），鏡射既有 `.github/workflows/governance-drift.yml` 的模式：排程呼叫可獨立在本機執行的 `scripts/check-release-drift`，偵測到 drift 時開立或更新一張標題固定的追蹤 Issue（先找既有同標題 open Issue 就更新，避免重複開票），未偵測到 drift 時只印出證據、不建立或更新 Issue。刻意不是 `release.yml` 自己的一個 step——一支已經卡住或壞掉的 release pipeline 沒辦法可靠地告警自己的壞掉。

**偵測條件（兩者同時成立才判定為 drift）：**

1. `main` HEAD 未被最新 immutable stable GitHub Release 的精確 target 涵蓋，也沒有被最新一次成功 `release.yml` run 明確判定為 `no-release`。
2. 過去 N 小時內，既沒有有效的 immutable stable Release，也沒有明確的 `no-release` run。

最新 eligible Release 必須由 GitHub API 明確回報 `immutable=true`；其 `target_commitish` 必須是精確 40 字元 SHA，且等於 `main` HEAD，或經 GitHub compare API 證明為其 ancestor；`published_at` 還必須不早於目前 `main` commit。精確 target 會持續視為涵蓋該 HEAD；ancestor target 只算 N 小時內的近期發布活動，不能永久掩蓋較新的 `main`。mutable Release、draft、非 ancestor target、移動中的 branch ref 或比目前 `main` 更早發布的 Release 都不能壓掉告警。這使 immutable GitHub Release 本身成為首要發布事實，不再要求一條已知會被 #123 fail closed 的 hosted run 偽裝成成功。

`release.yml` 在每次 push 到 `main` 後都會執行，但 workflow 的綠燈本身不是發布證據：`release_policy.py` 明確判定 `no-release` 時會成功結束；若 release-worthy commit 未在 merge 前物化，workflow 必須失敗，不能用人工指示或第二張 PR 把它視為成功。Detector 會讀取該 success run 的 job steps；只有「Plan the next version from repository history」成功，且後續「Detect the available release path」因 plan 為 `no-release` 而 skipped，才把該 run 視為健康證據。真正的發布仍只能由上段的 immutable stable Release 證明。

**N 預設 24 小時**，可用 `RELEASE_DRIFT_HOURS` 環境變數或 workflow 的 `hours` workflow_dispatch input 覆寫。`release.yml` 正常在 push 後幾分鐘內就有結果；24 小時涵蓋「一整天沒有任何 release 相關 push」的正常空窗期，不誤報安靜的一天，同時仍能在同一個工作日內就被發現，不會像 #587 一樣拖過一整個週末。失敗或未發布的 run 不是活動證據，因此重跑不會重新起算門檻。

**本機發版紀錄只作稽核用途**：#589 的既有約定仍要求在合併說明或 Issue／PR 留言留下：

```text
Release-publish-record: operator=<@handle> commit=<sha> command="<command>" result=<result>
```

這筆文字能補足本機執行缺少 hosted log 的公開稽核脈絡，但 commit 訊息與 Issue／PR 留言都是可變、可重播的聲明，無法證明 GitHub 上的 Release 狀態。`scripts/check-release-drift` 仍會讀取、驗證格式並在摘要與追蹤 Issue 顯示最新一筆作為診斷資訊，但不讓它改變 drift 結果；讀取稽核資料若失敗只會留下 warning 並當作無紀錄，不得阻斷權威判定與告警。有效紀錄只接受 `operator`、`commit`、`command`、`result` 四欄，其中 `command` 最長 512 字元且不得含反引號，以免稽核文字撐爆 Issue body 或跳脫行內 code。只有 GitHub API 回報的 immutable stable Release，或 job steps 證明明確判定 `no-release` 的成功 `release.yml` run，能抑制告警。

**這支 workflow 只偵測與通知，不接手發版**：既不會自動觸發 `release.yml` 重跑，也不會自動執行 `scripts/publish-release`；是否接手仍由人或 agent 判斷，維持 #589 既有的「人或 agent 主動決定啟用」設計原則。
偵測到 drift 且成功建立或更新追蹤 Issue 後，workflow 以 success 結束；只有偵測器、GitHub
API 或通知寫入本身失敗才回報 failure。Drift 事實由追蹤 Issue 承接，不以故意失敗的排程
run 重複表達。

**下發到 `template/`**：`.github/workflows/release-drift.yml` 與 `scripts/check-release-drift` 透過 `scripts/sync-paired-files.sh` 與 root 保持逐位元組同步，並在 `copier.yml` 重用既有 `.github/workflows/release.yml` 的 `project_mode == 'new'` exclude 條件，不新增第二個 Copier 選項——生成 repo 只要擁有 `release.yml`（`release_ownership == csarc-owned`）就會同時擁有這支漂移檢查，兩者不會分開存在。
