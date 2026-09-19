# CI/CD 設定與交付邊界

本頁只描述 2026-09-01 在 repository 內可執行、可由 live run 證明的設定。尚待其他 owner
處理的歷史設計位於 `archive/ci-cd/2026-08-27/` 且不下發；已決定不恢復的版本／交付
workflow 已刪除，歷史由 Git／Issue／PR 保存。舊 Issue 完成或舊 run 成功，都不等於目前
active。版本、發版與成品責任的完整盤點見中央模板的
[版本／交付 ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/release-security-and-dependencies.md)。

## 現行交付路徑

`main` 是唯一永久整合 branch。一般獨立 Issue 從最新 `main` 建立短分支，經 PR 直接回
`main`。只有需要共同整合與端到端驗收的 Milestone 才使用短生命週期
`dev/m<編號>-<簡稱>`；Milestone 內每張 Issue 仍以自己的 `type/<Issue>-*` PR 進入該
branch，最後由一張受審查的交付 PR 送回 `main`。

Reviewer assignment（`.github/workflows/governance-comment.yml`）已在本 repo 與所有生成
repo 啟用；治理漂移排程（`governance-drift.yml`）只在生成 repo 開啟
`enable_governance_drift_check` 時產生並每日執行，本模板 source repo 保留同一支
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

工作 PR 關閉單項工作；Milestone 交付負責批次進入 `main`。`promote/m<編號>-<簡稱>` PR 以
`Closes #<tracker>` 直接關閉該 Milestone 的 tracker Issue，並由 `work-item-lifecycle.yml`
的 `process` job（`record-promotion-evidence` step）在合併後自動把 merge commit 網址回填進
tracker 的 `Completion evidence` 段落（見 #512）；#400 與 #401 的自動結案契約不再是
blocked gap。
delivery branch 清理仍由 worktree 清理流程負責，不由版本或發版流程重複處理。

## Milestone 掛勾安全網（#551）

Milestone 8 收尾階段 #546–#550 五張 Issue／PR 全部沒有掛 Milestone，且沒有任何工具或
檢查會提醒——純粹是開 Issue 時忘記加 `--milestone`。#551 為此補上兩層非阻擋性提醒，
刻意不要求強制 fail-closed：許多 Issue／PR 本來就與任何 Milestone 無關（見 Issue #551
的「邊界」段落）。

- `scripts/gh-issue-create`：本機開 Issue 當下，若沒有帶 `--milestone`／`-m`，且
  `scripts/detect-open-milestone` 判定目前恰好只有一個 open Milestone，會印出提示；
  互動式終端機（`stdin` 是 tty）額外詢問是否要帶入該 Milestone，非互動環境
  （agent／CI／腳本呼叫）只印出提醒，不阻擋 Issue 建立。
- `scripts/validate-pr-policy`（CI 端：`pr-policy.yml` 的 `title` job「Validate
  pull request policy」step）：PR 與其 linked Issue 兩邊都沒有掛任何 Milestone、且同樣
  恰好有一個 open Milestone 時，於 PR 留言一次性提醒（內嵌 HTML comment marker 避免
  重複留言）；檢查本身仍維持 pass，不 fail-closed，留言失敗（例如暫時性 API 錯誤）也
  只印 `::notice::`，不影響結果。
- 兩者共用同一支 `scripts/detect-open-milestone` 判斷式：0 個或 2 個以上 open
  Milestone 都視為「無法判斷」，一律不提醒——避免在多 Milestone 並行時猜錯、誤導。
- 這兩個安全網只在**建立／驗證當下**新增這層提醒。既有的「Issue 已掛 Milestone 但 PR
  沒有（或反之、或兩者不同）」仍由 `scripts/validate-pr-policy` 既有的 fail-closed 比對
  規則擋下（見下方 PR policy 逐 step 判讀一節），未被本次變更影響或放寬。

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

Agent 或 automation 若要變更 PR 的 ready／draft、授權或 metadata，必須先取得 remote
lease，並透過 `scripts/pr_lifecycle.py` 執行；`scripts/verify` 會拒絕另一套重複寫入者。
人工在 GitHub 上審查與合併不受這個工具限制。

### Exact-head review 即為合併授權（#719）

一般有獨立 reviewer 的 PR，不需要再留一則重複的授權留言。`scripts/pr_lifecycle.py`
會把獨立 maintainer 對**目前 head SHA** 的最新有效 `APPROVED` review 直接視為合併授權；
它會即時確認 reviewer 仍有 `maintain`／`admin` 權限、不是執行 merge 的帳號，而且 review
的 `commit_id` 正好等於目前 head。任何後續 push 都會產生新 SHA，使舊 approval 自然
失效；`CHANGES_REQUESTED`、新的 Draft 事件、未解決的 blocking comment、未完成 checklist
或 required check 仍會 fail closed。

目前 alpha Ruleset 的已知 admin `pull_request` bypass 也只能由 lifecycle 在上述
exact-head approval 成立、GitHub 回報 `mergeable_state=clean`、必要檢查逐項重驗成功，且
live bypass actor 清單精確等於 repo 宣告值時使用；其他 bypass 形狀仍降級為 human-only。
這條路徑會在最後一次 merge snapshot 前自動留下 `bypass-trace:`。沒有獨立 review 的
Alpha self-merge 例外不變，仍必須使用取得 lease 後的 exact-head maintainer 授權留言。

### Copilot 審核模式（#752）

`.csarc/config.yml` 的 `pr_review_mode` 決定 PR 怎麼取得審核：

- `human`：Ruleset 要求一位 maintainer approval、CODEOWNER review 與 last-push approval，
  就是上一節的 exact-head review 流程。缺鍵時一律視為 `human`；`copier update` 對既有
  專案新增這個問題時也預設 `human`，不會悄悄改變既有 repo 的審核方式。
- `copilot`（新專案與 `csarc adopt` 的預設，本 repo 也採用）：Ruleset 要求 0 個 approval，
  改由 `copilot_code_review` 規則在每次 push 後自動請 GitHub Copilot 審核，並把
  `review` 列為 required check（`.github/workflows/pr-review.yml` → `scripts/review_gate.py
  check`）。`review` 在下列任一條件成立時通過：
  1. 獨立 maintainer 對**目前 head SHA** 的有效 `APPROVED`（沿用 #719 判斷，人工審核路徑
     仍然有效）；或
  2. Copilot 對**目前 head SHA** 的最新審核沒有任何 inline comment、內文沒有被隱藏的
     低信心意見（suppressed comments），且內文明確寫出沒有產生意見；或
  3.（#775）這是一張符合 `alpha_self_merge_opt_in` 條件（PR body 恰好一次
     `Alpha 自行合併 / self-merged` 標記、Milestone-less Issue 的 direct-to-main
     路由，或既有 `dev/mN` Issue 路由）的 Alpha self-merge PR，且已經有一則
     `pr_lifecycle.find_exact_head_authorization` 能找到的、綁定**目前 head SHA**
     的真人 maintainer 授權留言（跟 `pr_lifecycle.py merge` 要求的是同一則留言，
     不必另貼兩次）。

  Copilot 審核舊 head、仍在審核、留下意見、或內文格式無法辨識時一律 fail closed。
  Copilot 只會留下 `COMMENTED`，永遠不會 `APPROVED`，所以這個模式不能靠 GitHub 原生的
  approval 計數。未解決的 review thread 由 Ruleset 的 `required_review_thread_resolution`
  原生擋下。Draft PR 不審核，`review` 會失敗直到 PR 標為 ready。`.github/workflows/
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
   `copilot-review-trace: review=<URL> head=<SHA> actor=<login>`（alpha bypass 另外留下
   `bypass-trace: ... reason=exact-head-copilot-review`）。

自動合併由本機 agent 經 lifecycle 執行，不用 workflow 的 `GITHUB_TOKEN` 合併：
`GITHUB_TOKEN` 的合併不會觸發後續 `push` workflow（例如 release），也會繞過 lease；
本 repo 所屬 organization 也封鎖原生 auto-merge（#557）。

`copilot_review_max_level` 設定 Copilot 通過可以取代人工審核的最高發布層級，預設
`unlimited`。每件工作的發布層級要到 #745 才存在，所以在那之前設成 `unlimited` 以外的值
會讓 Copilot 路徑 fail closed、只接受 maintainer approval，不會假裝已經依層級判斷。

前提與限制：repo 需要有啟用 code review 的 Copilot 授權，每次審核消耗 premium requests
（取代 #241 的部分暫緩結論；Copilot coding agent 仍暫緩）。沒有授權或額度用盡時 Copilot
不會審核，`review` 維持失敗，只能走 maintainer approval。Copilot 沒有意見不等於沒有缺陷，
這是維護者 2026-09-18 接受的取捨。切回人工審核：把 `pr_review_mode` 改成 `human`，再由
管理員執行 `./scripts/apply-repository-settings.sh plan`／`apply`／`check`。

`gh pr merge --admin` 只能用來繞過文件明列的已知例外，目前有兩項：

1. `pr-policy.yml` `title` job 的「Validate Milestone approval」step（要求非提案者在
   #440 留言）在 #512 解決前的過渡期。繞過前必須先確認同一個 `title` job 的
   「Validate pull request policy」step 本身是 success，不能只看整個 job 或整個 PR
   的 conclusion 就一併略過——用 #513 的 `scripts/check-pr-policy-status`（完成前，
   改用 `gh run view <run-id> --log | grep -E "Validate pull request policy|##\[error\]"`
   手動確認）。
2. Ruleset 的 self-approval 結構性卡點，見下方「Alpha 自我核准 bypass」及其後的
   「Release phase 與 bypass 範圍收斂」。

**`--admin` 本身不足以繞過任何 Ruleset 規則。** 舊版 classic branch protection 會自動
給 repository admin 身分繞過，但 Ruleset 只認 `policies/rulesets.json`（或本節後述
拆分後的第二個 Ruleset 檔）頂層 `bypass_actors`（不在 `rules` 陣列內）明列的項目；
沒有對應 `bypass_actors` 項目時，`--admin` 對 Ruleset 直接無效，merge 會被拒絕（#580
的既有踩坑：`gh pr merge --admin` 對新版 Ruleset 也不生效，不像舊版 classic branch
protection 那樣自動給 admin 身分繞過）。

### Alpha 自我核准 bypass（#580）

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

**這段手動程序現在只是 fallback，不是唯一路徑（#775）。** 一張直接合併進 `main`、
`pr_review_mode: copilot` 但這個帳號沒有可用 Copilot 授權額度（`review` 這個
required check 永遠 `pending`）的 routine PR，只要滿足：分支名符合
`build|chore|ci|docs|feat|fix|refactor|revert|test/<issue>-<slug>` 格式、body 恰好
出現一次 `Alpha 自行合併 / self-merged` 標記、精確關閉一個仍是 open 且**沒有掛
Milestone** 的 Issue（有 Milestone 的必須走它自己的 `dev/mN` 分支，這條路不適用）——
`scripts/pr_lifecycle.py merge` 本身現在就會在 lease＋exact-head 授權留言齊全後直接
成功，不必再手動 `gh pr merge --admin`。不符合這個形狀的 PR（例如非 Issue-linked、
Issue 已有 Milestone、或是 Milestone 自己 `dev/mN` 分支上的 PR 需要繞過其他限制）仍
只能用上一段的手動程序。

這是只在「repo 結構性只有一個真人帳號」這段 alpha 期間才成立的例外，不是長期設計；
有第二個真正的 collaborator 後應重新檢視是否移除，方向由維護者決定（追蹤於 #580）。
與 #570（`required_status_checks` Ruleset 定義修復）及 #552（Milestone 核可重新設計，
同樣處理單一真人帳號 org 的自我核准風險）相關但範圍不同。Milestone tracker Issue 的
`/milestone admin-approve` 自核（見 `docs/milestone-description.md`）是另一個獨立機制，
只適用於 Milestone 核准留言，不是同一件事，不要混用。

這個 bypass 是否要在本 repo 之外的下游生成 repo 也預設套用，不在本節範圍——公版
`template/policies/rulesets.json.jinja` 刻意保留空的 `bypass_actors`，只有真的撞上
同一個「結構性只有一個真人帳號」問題的下游 repo，才需要自行在自己的
`policies/rulesets.json` 加上等效項目。

### Release phase 與 bypass 範圍收斂（#607）

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
範圍——公版 `template/policies/rulesets.json.jinja` 刻意保留空的 `bypass_actors`、
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
`template/.github/workflows/dependabot-auto-merge.yml`，#569 新增）裡的
`gh pr merge --auto --squash` 與 `gh pr edit --add-label
needs-manual-review` 兩處寫入向來未經過 lease，因此曾被 `scan_writers` 判定
為「Unleased PR lifecycle writer」而 fail closed，連帶讓三種語言生成專案的
`scripts/verify` 全部失敗（根因分析見 #597；例外本身見 #602）。維護者已確認
方向：不強行把這兩行改走 lease——`gh pr merge --auto` 語意是排進 GitHub
原生佇列，實際合併仍卡在 `title`／`promotion`／`verify` 必要檢查與
`policies/rulesets.json` 的 branch protection review requirement，不是
lease 機制原本要防的「立即搶寫」；`gh pr edit --add-label` 那行只在 major
版本更新、本就要人工複核而非自動合併時才觸發，同樣不構成即時寫入競態。因此
`scripts/pr_lifecycle.py` 新增一個與 `canonical_scanner_helper` 同風格、
共用同一段 symlink 安全檢查的姊妹函式 `dependabot_auto_merge_exemption`，
只正面表列這兩個精確路徑，不是放寬 pattern 本身——換一個檔名重現同樣的
`gh pr merge`／`gh pr edit --add-label` 寫法仍會被 `scan_writers` 抓到
（回歸測試見 `tests/test_pr_lifecycle.py` 的
`test_dependabot_auto_merge_exemption_is_an_exact_path_allowlist`）。

`.github/workflows/release.yml` 裡 `googleapis/release-please-action` 這一步
同樣未經過 lease 就會建立／更新自己的版本 PR，且從未有例外或對應 Issue 記錄過，
直到 #643 才發現。理由與 dependabot 例外一致但更直接：release-please 建立的 PR
不是本 repo 任何一條 task-PR 路線（獨立 Issue／Milestone Issue／`dev/i*`
canary／hotfix），而是第五條、由維護者直接人工審查合併的獨立路徑（見
`AGENTS.md`「Release execution」）；`release.yml` 本身已用
`concurrency: group: release-${{ github.repository }}` 把自己序列化，且
release-please 只會動到自己的 `release-please--branches--main--components--*`
head ref（`scripts/release_policy.py` 的 `expected_head`，`scripts/
promotion_gate.py` 對同一 ref 前綴的特殊處理），沒有任何 lease 保護的 agent
流程會寫這個 ref。因此 #643 為 `scripts/pr_lifecycle.py` 新增
`release_please_exemption`，只正面表列 `.github/workflows/release.yml` 這一個
精確路徑（`template/.github/workflows/release.yml.jinja` 是 Jinja 樣板，
`scan_writers` 的 glob 本來就不掃描它，不需要第二個路徑）（回歸測試見
`test_release_please_exemption_is_an_exact_path_allowlist`）。

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

**Issue #744／#745 部分取代（2026-09-17）：** 本節的 `policies/project-stage.json`
`release_phase`（alpha／beta／release 三值）繼續用於上面描述的 Ruleset
bypass 範圍收斂，本身不受影響。但本節「`release_phase` 是人工宣告、不從
分支模式或 semver 反推」的立場，以及「進入 `release` 後這整個 bypass
結構性消失」隱含的單向前進假設，被維護者 2026-09-17 的決定取代：版本號
本身現在就直接表示發布層級（見下面「版本、發版、交付與部署矩陣」與
`docs/adr/release-security-and-dependencies.md` 新增段落），alpha／beta 可以
在任何時候發布，不再是一段只會前進的一次性期間。審核與測試如何依層級分級
（取代本節 bypass 機制的下一步）是 #745 的範圍，尚未落地前本節機制照舊
生效；`policies/project-stage.json` 檔案本身與其三值不因 #744 改變。

### 不屬於里程碑的工作

一張 Issue 若能獨立審查、驗證與交付，且沒有共同期限、跨 Issue 相依、整批驗收或
soak／canary 需求，就不必加入里程碑。它從最新 `main` 建立 topic branch，PR 直接回
`main`，接受一般 review 與風險分級驗證，並以 `Closes #N` 在合併後結案。合併只代表
repository delivery；後續由 release workflow 判斷是否需要建立版本 PR。**這張 Issue
本身在合併前需要通過核可**（非提案者核准或 admin 自核），見下方「Standalone／
hotfix／release recovery Issue 核可 gate（#743）」——它與有 Milestone 的 Issue 自動
繼承 tracker 核可形成對稱，避免拆成 standalone 變成繞過批次治理的捷徑。

若工作開始需要多張互相依賴的 Issue、共同交付日期、整批驗收、獨立環境或正式發版
決策，必須在實作前加入適當里程碑，改走 `dev/m*`；不能用 standalone 路徑繞過批次治理。

### Hotfix

Hotfix 只用於必須立即修正 `main` 的缺陷，不是一般工作的優先通道：

1. 建立沒有里程碑的 Bug Issue，標上 `bug` 與 `hotfix`；若內容尚不能公開，改用
   GitHub Security Advisory 的私密協作流程。
2. 從最新 `main` 建立 `fix/<Issue>-<slug>`，PR 使用 `fix(scope): summary` 並直接 target
   `main`。它仍須正常 review，且 CI 一律執行 full；不得以緊急為由跳過。
3. PR 以 `Fixes #N`／`Closes #N` 連結 Issue。合併後保留 PR、commit SHA、full run、
   rollback 說明與是否發版的決策；#401 負責一般 GitHub native 關單契約。
4. `fix` 預設表達 patch 意圖；破壞相容性時明列 `!`。Release Please 會據此更新版本 PR；
   版本 PR 尚未審查、合併且正式成品尚未發布前，hotfix 仍只算已交付、尚未發版。
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
結果。tracker 尚未核准、核准因後續編輯失效，或仍有未解反駁時，`reconcile` 仍會把失敗
結果寫回 PR check，但以 notice 回報治理狀態並成功結束背景 run；PR 上的 required check
繼續 fail closed。tracker 缺漏／格式錯誤、GitHub API 錯誤或狀態寫入失敗仍讓背景 run
失敗，不會被當成等待核准。`#743` 剛落地時只做了「PR 合併前的 CI 接線」，沒有補上這
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

**Hotfix 的緊急路徑：**與 tracker、scope-expansion 核可相同精神的 admin
self-approval 例外在此保留——proposer 若同時是 repo `admin` collaborator，可以自己
留言 `Admin-approve: <理由>` 通過，理由必填，summary 明確標成「Issue admin
self-approved by」，不與一般非提案者核准混淆。這是唯一避免「等待核准而無路可
走」的路徑，適用真正緊急、沒有第二人可以核准的 hotfix 情境；`#745`（尚未實作）之後
會依發布層級（alpha／beta 以上）調整 admin self-approval 是否允許，`#743` 先落地
「非提案者核准或 admin 自核」這條現行規則。

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

### `promotion` 必要檢查的產生條件（#601）

`policies/rulesets-required-checks.json`（與 `template/policies/rulesets.json.jinja` 的 `required_status_checks`）
長期要求 `title`／`promotion`／`verify` 三個 context，但在 #601 之前，沒有任何 workflow 對一般（非 Milestone
交付）PR 產生 `promotion` 這個 check-run——`main`、`dev/m*` 交付分支與所有現存 PR 皆缺這個 context，required
check 因此對這類 PR 永遠卡在 pending。`.github/workflows/pr-policy.yml` 新增的 `promotion` job（與
`title` job同檔、同觸發條件，`template/` 同步一份）補上這個缺口，呼叫新增的 `scripts/promotion_gate.py
check-route` 子指令。

跟 `title` job 一樣，`promotion` job 對 `pull_request` 事件 checkout 的是 PR 的 base（trusted）commit，
不是 PR 自己的 head／merge commit——避免一個惡意 PR 改寫 `route_for()` 自我核准。這代表 `check-route`
子指令要等這個子指令本身合併進 `main` 之後，後續 PR 的 `promotion` job 才會真的執行到它；`promotion`
job 沿用 `title` job「Validate Milestone approval」step 已經在用的同一種 bootstrap 寫法——先用
`python3 scripts/promotion_gate.py --help | grep -q check-route` 探測 base commit 上是否已經有這個子
指令，沒有就印一則 `::notice::` 直接成功，不 fail closed；引入 `check-route` 本身的這個 PR 靠
`tests/test_promotion_gate.py` 的 `test_check_route_*` 在本機驗證新邏輯，不靠這個 PR 自己的即時 CI
執行到它。

這個 job 刻意不是獨立的 `promotion.yml` 檔案：本 repo 在 2026-08-27 的 workflow 全面暫停（#372／#375）之前
確實有過一支同名、遠更複雜的 `promotion.yml`（含 canary 證據、`prepare()`／`finalize()` 全流程）與其配對的
`promotion-post-merge.yml`（合併後 ref 清理），原始檔保留在 `git show
bc05942:archive/ci-cd/2026-08-27/root-workflows/promotion.yml` 可查，`tests/test_delivery_sync.py::
test_milestone_promotion_check_and_cleanup_cover_delivery_refs` 仍以「`.github/workflows/promotion.yml`
存在與否」為 skip 條件保留當年的斷言、等待那支被暫停的完整流程有一天正式復原。#601 的範圍與那支舊
workflow 不同（見 Issue 本文「補充」段的拆分說明），本節新增的 `promotion` check 只解決「required check
永遠 pending」這一個獨立問題，刻意不使用會誤觸該 skip 條件的檔名，也不重建那支已暫停、且已經跟現在的
`branch_strategy`／`route_for()` 設計脫節的舊流程；job 的 check-run context 由 job 的 `name:` 決定、跟
workflow 檔名無關，所以 `promotion` context 一樣被正確產生。

`check-route` 只重用既有的 `route_for()` 分類器（`prepare()` 產生完整交付證據時用的同一份函式），不重新實作
分支／標籤判斷邏輯，避免兩者對同一個 PR 的路由判斷不一致：

- `pull_request` 事件：直接從 webhook payload 讀 base／head／labels（不需要額外 `GH_TOKEN` 呼叫），呼叫
  `route_for()`。任何 `not-applicable`（一般 topic branch、`dependabot/*`、`automation/*`）或已知的合法路由
  （`milestone`／`isolated`／`hotfix`／`release-recovery`／`release-follow-up`）都回報成功；只有 target
  `main` 卻不符合任何已知路由的分支（`invalid-main-route`）才 fail closed。
- `merge_group` 事件：直接視為 `Route("merge-queue", False)`——來源 PR 開啟當下已經分類過，佇列重跑不必
  重新讀 event payload（與 `prepare()` 對非 `pull_request` 事件的既有 fallback 一致）。

這個 job **不**取代既有的 Milestone 交付驗證：`title` job（`scripts/validate-pr-policy`）仍然負責 tracker
Issue、Promotion 區塊 checklist 與 promotion 標籤的完整驗證；`.github/workflows/milestone-lifecycle.yml` 的
`Milestone approval` check（不在 `required_status_checks` 名單內）仍然獨立存在，兩者都不受本節變更影響。
`promotion` 這個 required check 的責任範圍只到「這個 PR 是否走一條被承認的路由」，不到「這條路由的證據是否
齊全」——後者仍由 `scripts/promotion_gate.py` 的 `prepare()`／`finalize()` 在正式的 Milestone 交付流程中
處理，範圍不變。

### `verify` 必要檢查改為本機驗證聲明（#661）

維護者決定：`verify` required check 的測試驗證本身要離開 GitHub Actions，改成固定在開發者本機執行
——不是 Actions 壞掉時的備援，是刻意選擇的常態架構。`.github/workflows/ci.yml`（與
`template/.github/workflows/ci.yml.jinja`）的 `verify` job 不再實際呼叫 `scripts/verify-fast`／
`scripts/verify-template.sh`（生成 repo 是 `scripts/verify`），只驗證這個 commit 是否已經帶有本機驗證
通過的證據。

**與 #171（已關閉）的區別**：`#171` 建立的「本機驗證聲明」機制範圍刻意收得很窄，只在 GitHub Actions 免費
額度確認耗盡時啟用，且每次都要 human maintainer 親自確認耗盡原因、逐 commit 重新授權——本質是授權例外
（Actions 壞掉時要不要放行這次合併的人為判斷）。本節機制本質不同：要驗證的是一個事實陳述（「這個 commit
的內容，本機真的跑過測試且通過」），不是要不要放行的判斷，因此不需要人在每個 PR 上點頭確認，只要能自動、
可靠地驗證這個事實陳述為真即可。兩者信任模型不同，`#171` 的 quota-only、human 每次確認流程不受本節影響，
也不合併成同一套機制。

**機制**：`scripts/verify-fast`／`scripts/verify-template.sh`（與生成 repo 對應的
`scripts/verify-fast`／`scripts/verify`）驗證成功（exit 0）時，在結尾呼叫
`scripts/write-verify-attestation <fast|full>`，於當下 HEAD commit 的訊息附加一行 trailer：

```text
Verified-locally: sha256=<tree hash> tier=fast|full at=<UTC ISO 8601>
```

- **`sha256=` 的值是 git 自己的 tree hash**（`git rev-parse HEAD^{tree}`），不是自製的檔案內容 hash——
  這個值本來就已經是 deterministic、collision-resistant、且免費可算，另外發明一種 hash 只會多一個兩者
  可能悄悄不同步的地方。欄位名稱固定寫 `sha256`，但實際演算法是這個 repository 設定的 git object format
  （幾乎所有 repository，包含本 repo，都是 SHA-1；只有明確以 `--object-format=sha256` 初始化的 repository
  才是 SHA-256）——欄位名稱是內容識別語意，不是演算法保證；驗證邏輯用完整字串比對，不靠固定長度判斷，見
  `scripts/verify_attestation.py` 的 module docstring。
- **寫入方式是 amend 現有 commit 的訊息，不是另開一個空 follow-up commit，也不是寫入本機檔案再轉成
  commit**：只改訊息、不動 index 的 amend 不會改變 tree（`scripts/write-verify-attestation` 的註解有完整
  推導），所以 amend 前算出的 tree hash，在 amend 後仍然正確描述同一個 commit；另外兩個方案都會讓「被驗證
  的東西」跟「帶著證據的東西」變成兩個物件，一旦 HEAD 後續被 amend、rebase 或 force-push，沒有機制能保證
  兩者不會悄悄分岔。代價是 HEAD 的 SHA 會變：如果這個 commit 已經 push 過，下一次 push 需要
  `--force-with-lease`——這對 PR 自己的 topic branch 是正常、預期的操作，不是對共享整合分支的
  force-push。
- **寫入前要求工作目錄乾淨**（`git status --porcelain` 必須全空）：attestation 的核心主張是「這個確切的
  tree 被測試過」，工作目錄若有未提交的變更，剛跑完的測試實際涵蓋的內容就不等於 `HEAD^{tree}`，繼續寫入
  會是一句不實聲明。`scripts/write-verify-attestation` 在這種情況下略過（exit 0，因為測試真的通過了，不
  是失敗），讓 hosted `verify` job 之後因為找不到 trailer 而 fail closed——這是刻意、安全的結果，逼著
  「先 commit、再驗證、再 push」這個順序，而不是安靜地寫一句可能不實的聲明。

**hosted `verify` job 現在只驗證三件事**（`scripts/check-verify-attestation`，核心邏輯在
`scripts/verify_attestation.py`、可獨立單元測試）：

1. **trailer 存在**——commit 訊息裡有格式正確的 `Verified-locally:` 一行。
2. **hash 相符**——trailer 的 `sha256=` 與這個 commit 實際的 `^{tree}` 完全一致，擋「複製舊 commit 的
   trailer、忘記重新驗證」這類非蓄意疏漏（新內容加進同一個 commit 卻沒重跑驗證，tree 會變、hash 就對不
   上）。
3. **timestamp 新鮮**——`at=` 距離現在不超過 24 小時（`--max-age-hours`，可覆寫），且不能是未來時間
   （超過 5 分鐘 clock skew 就視為異常，`--max-clock-skew-minutes`）。24 小時沿用本文件 `release-drift.yml`
   的 `RELEASE_DRIFT_HOURS` 同一個判斷慣例：長到不逼一般「本機驗證完、隔一段時間才 push」的正常工作節奏
   重跑，短到「拿很久以前的驗證結果冒充」（Issue #661 原文用語）不會是一條直線通過的路。這裡的 staleness
   本質不是防偽造——hash 已經把 trailer 綁死在確切內容上，同一段內容重放舊 trailer 只是在陳述一個依然為
   真的歷史事實——而是防環境漂移：同一個 tree 現在重跑，可能因為依賴版本、lint 規則等外部因素改變而不再
   通過，即使幾小時前確實通過過。**沒有「未來時間」檢查的話，staleness 判斷可以被一個刻意設在遙遠未來的
   `at=` 完全繞過**（未來時間永遠不會被判定為「太舊」）——這是設計本節時特別要擋的一種讓 freshness 檢查
   形同虛設的方式，不只是把日期往前搬那麼簡單的疏漏。

**額外的第四項：tier 是否足夠**（`--required-tier`，來自同一個 job 已經算出的
`scripts/ci_tier.py` 分類結果）。沒有這一項，任何人都可以永遠只跑便宜的 `scripts/verify-fast`（固定
attest `tier=fast`），即使這個 PR 改到 `.github/workflows/` 之類、`ci_tier.py` 會判定需要 `full` 的路徑
——hosted job 既然已經不重新執行任何東西，就完全沒有能力分辨兩者。`tier=full` 滿足任何要求；`tier=fast`
只滿足 `docs`／`fast` 要求，不滿足 `full`。這個比對不重新實作 `ci_tier.py` 的分類邏輯，只是拿它已經算出
的答案來比對，與 `promotion` job 重用 `route_for()` 是同一個原則。

**已知、記錄在案、不視為本節缺陷的殘餘風險**：這個機制無法阻止「蓄意造假」——本機真的沒跑測試，卻手算出
正確的 tree hash、手寫一行格式正確、timestamp 新鮮的 trailer。這在技術上完全可行（tree hash 不需要跑測試
就能算出來），且與現在「直接在 PR 描述裡寫假話」風險同一等級。本節機制解決的是「忘記跑」「跑錯版本」這類
非蓄意疏漏，不解決蓄意造假——這點與 #171 無關，`#171` 的 human 每次確認流程本來就不是為了解決同一個問題。

**這個變更牽動既有的「push 並信任 hosted `verify` check」語句**：下方「Base-only re-merge 例外
（#468）」原本容許已經本機全綠一次的 full-tier PR，之後因為重新合併 base 而直接 push、不用再本機重跑，
理由是「hosted CI 對這次合併結果仍會重新執行完整驗證」。本節生效後這個前提不成立了——hosted `verify` job
不再執行任何東西，重新合併產生的新 tip commit 沒有自己的 trailer，會被 hosted job 當成任何其他未經驗證
的 push 一樣 fail closed。這不是本 Issue 範圍內要解決的問題（#661 的邊界明確排除治理類與其他既有機制的
重新設計），下方 Base-only re-merge 一節已經加註這個交互作用；是否、以及如何讓 `#468` 的例外在新架構下
繼續有意義，留給後續 Issue 決定。

**回歸測試**：trailer 產生（成功時正確寫入、失敗時不寫入、工作目錄不乾淨時略過、重跑時取代而非疊加既有
trailer）見 `scripts/test-verify-attestation`（對真實、拋棄式的 git repository 操作）；hash 相符／不符、
timestamp 新鮮／過期／未來、trailer 缺失、tier 是否足夠等純邏輯見 `tests/test_verify_attestation.py`
（不需要 git，直接測 `scripts/verify_attestation.py` 的純函式與 CLI）。兩者都掛在
`scripts/verify-stage-regression-tests`（生成 repo 掛在 `scripts/verify` 的自我測試清單），並隨
`scripts/verify_attestation.py`／`scripts/write-verify-attestation`／`scripts/check-verify-attestation`
一起透過 `scripts/sync-paired-files.sh` 逐位元組下發到 `template/`。

**`policies/rulesets-required-checks.json` 不需要改動**：required check 仍然叫 `verify`（context 名稱由
job 的 `name:` 決定，不是由它做什麼決定），Ruleset 只認 context 名稱，不知道、也不需要知道 job 內部從「重
新執行測試」換成「驗證一個聲明」。

### Dependabot 的 hosted 執行例外（#753）

上方「本機驗證聲明」機制對 Dependabot 這類 PR 結構性地無解：Dependabot 的 commit 由 GitHub 自己直接產生
並推送，從未經過任何人的本機，永遠不可能帶有 `Verified-locally:` trailer——`verify` 因此對每一張
Dependabot PR 都 fail closed，包含安全性更新，`#557` 的 `dependabot-auto-merge.yml` 即使 arm 了
auto-merge 也永遠合不進來。

修法是一個正面表列的窄範圍例外（`scripts/hosted_verify_bots.py`，module docstring 有完整條件），目前只有
一筆：`dependabot[bot]`。`.github/workflows/ci.yml` 的 `verify` job 新增一個「Determine hosted-verification
bot eligibility」step，同時要求下列**全部**成立才視為符合例外，任一項不成立就沿用原本的 attestation 檢查：

1. PR 作者（`github.event.pull_request.user.login`，不是 `github.actor`）在白名單內。
2. head branch 符合該 bot 專屬的前綴（Dependabot 是 `dependabot/*`）。
3. head repository 就是這個 repository 本身，不是 fork（`github.event.pull_request.head.repo.full_name`
   對照 `github.repository`）。

符合的 PR，`verify` job 略過「Validate local verification attestation」step，改用「Run hosted verification
for an allowlisted bot pull request」step在 runner 上**真的執行**驗證：沿用同一個 job 裡
`scripts/ci_tier.py` 已經算出的 `tier`／`scopes`（與任何 standalone PR 的本機執行分級邏輯完全相同），
`tier=full` 時跑 `./scripts/verify-template.sh`（生成 repo：`./scripts/verify`），否則跑
`./scripts/verify-fast`。這兩支腳本在成功結尾都會呼叫 `scripts/write-verify-attestation` 對 HEAD 執行
`git commit --amend`，在這個一次性、不會被 push 回去的 runner checkout 裡需要一個本機 git 身分才能執行
（`persist-credentials: false` 已確保這個 step 完全沒有推送能力），所以 step 開頭先設定一個限定在這次
checkout 內的 `git config user.email`／`user.name`；產生出的 attestation commit 本身沒有意義，只是讓腳本
順利跑完，不會、也不需要被讀取。

白名單 bot 的 PR 仍然不需要連結 Issue（`scripts/validate-pr-policy` 現行行為不變），合併仍然要通過現行
Ruleset 的審核把關（Copilot 模式下是 `review` required check，見「Copilot 審核模式（#752）」一節；`human`
模式下是原生 maintainer approval）——這個例外只回答「`verify` 這一個 required check 怎麼通過」，不觸碰、
也不放寬任何審核要求。

新增一個 bot 到這份白名單，比照上方「通則（自 #602 起生效）」：要有自己的 tracking Issue 記錄理由與範圍，
不能只在程式碼註解裡說明。

**回歸測試**：`tests/test_hosted_verify_bots.py`（白名單成立／作者不符／branch 前綴不符／來自 fork／
head repository 缺失五種情況，以及 CLI 寫入 `$GITHUB_OUTPUT` 的格式）；`scripts/hosted_verify_bots.py`
隨 `scripts/sync-paired-files.sh` 逐位元組下發到 `template/`。

### 建立新 `dev/m*` delivery 分支（#754）

`CSARC protected branches` Ruleset 的 `conditions.ref_name.include` 涵蓋 `refs/heads/dev/m*`，讓每個
Milestone 自己的 delivery 分支（`docs/index.html` Journey 01／`AGENTS.md` 工作迴圈第 8 步）跟 `main` 一樣
受保護。但 `required_status_checks` 規則預設在**建立分支這個動作本身**就要求 `title`／`promotion`／
`verify`／`review` 全部先通過——一個尚不存在的新分支在建立當下沒有任何 commit 或 PR 能觸發這些 check，
`required_status_checks` 在這個情境下永遠無法被滿足：任何符合 `dev/m*` pattern 的全新分支都無法直接
`git push` 建立，僅有的 `bypass_actors`（admin，`bypass_mode: "pull_request"`）又只在「透過合併 PR」時生
效，而建立一個全新分支不可能先有一個以它為 base 的 PR，兩者互為前提、無路可通。

修法是 GitHub Rulesets 原生就為這個情境準備的欄位：`required_status_checks` 規則的
`do_not_enforce_on_create: true`（`policies/rulesets-required-checks.json`；生成 repo 對應
`template/policies/rulesets.json.jinja` 同一個規則區塊，兩者都不分 `pr_review_mode`／`branch_strategy`，因
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
   本身也是 paired 檔案）新增 `sync-template` job，跟既有 `auto-merge` job 同一個 `if:
   github.event.pull_request.user.login == 'dependabot[bot]'` 閘門與 `pull_request`（非 `_target`）觸發理由
   （Dependabot 直接推到這個 repository，從來不是 fork）：checkout PR head、跑
   `./scripts/sync-paired-files.sh`，有 drift 就 commit 並 push 回同一個分支。只執行這支腳本既有、已測試的
   逐位元組複製邏輯，不執行 PR 內容裡的其他任何東西；push 觸發的新 `synchronize` 事件會讓 `verify`（#753）
   對新 head 重新驗證，也會讓這個 job 自己重新跑一次、這次因為沒有 drift 而直接結束，不會無限迴圈。
   同步 commit 的訊息固定用 `fix(deps): ...`，不是 `chore:`——完成條件第五項要求「會改變 template/ 內容的
   依賴更新，合併後要進入下一次發版」，`release-please`（`release-type: simple`）只認 `fix`／`feat` 升版號；
   這裡只在 `sync-paired-files.sh` 真的找到 drift（代表這次 bump 確實改到 `copier update` 會下發的內容）時
   才 commit，所以是精準只對「真的動到 template 分發內容」的那次 bump 觸發發版，不會連帶讓每一張跟 template
   無關的 Dependabot commit 都被迫升版號。
2. 新增 `scripts/check_action_pins.py`（root 與 `template/scripts/check_action_pins.py` 逐位元組同步）：掃
   `.github/workflows/`、`template/.github/workflows/` 底下所有 `.yml`／`.yaml`／`.jinja` 檔案的
   `uses: owner/repo@sha` pin，同一個 action 在整個 repo 裡的 pin 必須完全一致，不一致就 fail closed 並點名
   哪個檔案落後、目前多數版本的 pin 是什麼。這是**跟 Dependabot 白名單無關**的獨立不變量檢查，專門補
   `.jinja` 這塊 Dependabot 結構性掃不到的缺口。掛進 `scripts/verify-fast`（`workflow` scope 時執行）與
   `scripts/verify-stage-github-actions-audit`（`verify-template.sh` 的一部分，跟 zizmor 同一階段）。
   建置過程中這支腳本立刻抓到一個真實既有 drift：`template/.github/workflows/release.yml.jinja` 的
   `anchore/sbom-action` 停在 `v0.24.0`，root 的 `.github/workflows/release.yml` 已經是 `v0.24.2`；已在本
   PR 一併修正到與 root 一致。

**回歸測試**：`tests/test_check_action_pins.py`（pin 一致／不一致回報／不同 action 互不干擾／檔案掃描範圍／
CLI fail closed 五個案例，只在 root 執行；#780 已停止把 root 治理測試複製進生成專案）。`sync-template`
job 目前沒有對應的本機可重跑回歸測試——它是一段會實際 push commit 的 workflow step，沒有安全、可重複執行的
方式在本機或 CI 對真實 GitHub repository 重放；正確性由 `scripts/sync-paired-files.sh` 自身既有的測試覆蓋
（它是唯一被呼叫的邏輯），實際行為待合併後第一張真的改到 paired workflow 的 Dependabot PR 驗證並回填證據。

## Current automation

下表逐項列出 canonical file、owner、觸發（輸入）、權限／timeout、產物（輸出）、測試與
最新 live evidence；檔案存在或舊 run 成功不單獨算 active——見 Dependency vulnerability
與 Work Issue closure 兩列的落地與失敗證據。Live evidence 以 2026-09-01 對
`Innoguard-Cyber-Arch/csarc-repo-template` 的 `gh api actions/workflows` 與
`gh run list` 查詢結果為準；重跑本盤點請重新查詢，不沿用本表數字。

| 能力 | Canonical file | Owner | 事件（輸入） | 權限／timeout | 產物（輸出） | 測試 | 最新 live evidence | 狀態 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CI | `.github/workflows/ci.yml` | 驗證分級（#392／#403／#428）；本機驗證聲明（#661）；Dependabot hosted 執行例外（#753） | `pull_request`、`merge_group`、`workflow_dispatch` | `contents: read`；15 分鐘；同一 PR 新 commit 取消舊 run | `scripts/ci_tier.py` 分類（仍在 runner 上執行，是變更路徑分類邏輯，不是測試）後，`scripts/hosted_verify_bots.py` 判斷這張 PR 是否符合白名單 bot 例外（見「Dependabot 的 hosted 執行例外（#753）」一節）：不符合則只用 `scripts/check-verify-attestation` 驗證這個 PR 的實際 HEAD commit（`pull_request` 事件讀 PR 自己的 head sha，不是 GitHub 產生的 merge commit）是否帶有格式正確、hash 與 tree 相符、timestamp 新鮮、tier 足夠的 `Verified-locally:` trailer；符合則改在 runner 上實際執行 `scripts/verify-fast`／`scripts/verify-template.sh`（生成 repo：`scripts/verify`），成功時由這些腳本呼叫 `scripts/write-verify-attestation` 寫入 trailer（僅供腳本正常結束，不被讀取）；輸出 `verify` check 與 step summary | `tests/test_ci_tier.py`；`tests/test_hosted_verify_bots.py`；`tests/test_journey03_ci.py` 的 `test_root_ci_is_one_bounded_verification_job`／`test_generated_ci_uses_the_same_one_job_contract`；`tests/test_verify_attestation.py`（純邏輯）與 `scripts/test-verify-attestation`（對真實 git repository） | run [33519320562](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33519320562)，2026-09-01，success——此 run 早於 #661／#753，只證明 `scripts/ci_tier.py` 分類與（當時仍在 runner 上執行的）驗證邏輯，不代表本機驗證聲明改造或 Dependabot 例外 | `scripts/ci_tier.py` 分類：active（邏輯未變）；本機驗證聲明改造（#661 本身）：active；Dependabot hosted 執行例外（#753 本身）：candidate（待 `main` 落地並於首張真實 Dependabot PR 觸發後轉 active） |
| PR policy | `.github/workflows/pr-policy.yml` | PR／交付政策 | PR metadata 事件（opened／edited／synchronize／labeled）、`merge_group` | 只給需要的 Issue／PR metadata 權限；固定 timeout | `title` job：Issue、route 與 review policy 判定；`promotion` job（#601）：呼叫 `scripts/promotion_gate.py check-route` 分類 route，回報 `promotion` required check（`not-applicable`／`milestone`／`isolated`／`hotfix`／`release-recovery`／`release-follow-up`／`merge-queue` 成功，`invalid-main-route` 失敗） | `scripts/test-pr-policy`；`promotion` job 見 `tests/test_promotion_gate.py` 的 `test_check_route_*` | run [33519320929](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33519320929)，2026-09-01，success；同日對 #448／#453／#457 等未完成 checklist 的候選 PR 正確擋下合併，證明門禁確實生效 | `title` job：active；`promotion` job：candidate（隨 #601 首次落地，尚無 live run，待 `main` 落地並於首次 PR 觸發後轉 active） |
| PR review（Copilot 審核模式，#752／#775） | `.github/workflows/pr-review.yml` | PR 審核授權（#752，銜接 #719／#745／#775） | `pull_request`（opened／synchronize／reopened／ready_for_review／converted_to_draft）、`pull_request_review`（submitted／dismissed）、`issue_comment`（created，篩選 PR 上以 `PR lifecycle merge authorization` 開頭的留言）、`merge_group` | `contents: read`、`pull-requests: read`；10 分鐘；同 PR 新事件取消舊 run | `review` job 呼叫 `scripts/review_gate.py check`：`pr_review_mode=copilot` 時，目前完整 head SHA 已獲 Copilot 乾淨審核、獨立 maintainer `APPROVED`、或符合條件的 Alpha self-merge 授權留言（#775）才過；`pr_review_mode=human` 時只回報，審核仍由 Ruleset 原生 required approval 把關 | `tests/test_review_gate.py`；`scripts/pr_lifecycle.py` 的 Copilot／Alpha self-merge 授權來源見 `tests/test_pr_lifecycle.py` | 尚未落地 `main`，無 live run | candidate（待 main 落地並於首次 PR 觸發後轉 active） |
| Dependency vulnerability | `.github/workflows/osv.yml` | 依賴安全（#406／#407） | weekly schedule、manual、相關 manifest／lockfile 變更 | `contents: read`；固定 timeout | OSV 掃描結果 | `tests/test_dependency_security.py` | 2026-09-01 以 `gh api repos/.../actions/workflows` 查詢：GitHub 僅註冊 7 支 workflow，**不含 `osv.yml`**——本檔尚未落地 `main`，且觸發條件不含 `pull_request`，候選分支無法預先註冊。前身「OSV scheduled scan」最後已知 run 於 2026-08-24 全部 failure，屬歷史證據，不代表本候選 | **root：candidate**（待 main 落地＋首次排程／手動觸發）；**新生成 repo：active**（Copier 初次 commit 即進入該 repo `main`，可立即註冊與觸發） |
| Work item lifecycle | `.github/workflows/work-item-lifecycle.yml` | #400／#401／#574（合併） | `issues`、`issue_comment`、`milestone` 事件；`pull_request.closed`（里程碑工作 PR 合併進 `dev/m*` 或 `promote/m*` 晉升 PR 合併進 `main`） | 單一 job 內所有 step 共用的最小權限集合：`checks: write`、`contents: read`、`issues: write`、`pull-requests: read`；5 分鐘 | label／milestone routing、lifecycle gate 狀態與 closure 同步、對應 Issue 關閉 | `scripts/test-issue-triage`、`tests/test_journey06_workflows.py`、`tests/test_milestone_lifecycle.py`（本候選尚未含 #444 已拆分的 `test_milestone_approval.py`／`test_milestone_closure.py`，待 #444 併入才更新）、`tests/test_work_pr_closure.py` | 尚未落地 `main`，無新 live run；三個前身 workflow（`issue-triage.yml`、`milestone-lifecycle.yml`、`work-item-closure.yml`）已刪除，其舊 run 證據（`33524318953`／`33524281794`／`33502286588`）不再代表現行檔案 | **root：candidate**（待 main 落地並觸發首次 issues／issue_comment／milestone／pull_request 事件才能取得新 live evidence）；#574 只把三個 workflow 檔的既有邏輯打包成一個 job 內的循序 step，不改變任一 step 本身的行為、權限需求或所呼叫的 script |
| Spec to Issue | `.github/workflows/spec-to-issue.yml` | Spec 轉換 | spec 檔案變更事件／manual dispatch | 最小 Issue metadata write | 可審查 Issue 草稿 | `tests/test_spec_to_issue.py` | run [33490382161](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33490382161)，2026-09-01，success | active |
| Dependabot | `.github/dependabot.yml` | GitHub 原生＋依賴安全；hosted verify 白名單（#753）；template 同步與 Actions pin 一致性（#755） | schedule／manifest 變更 | GitHub 原生 bot 邊界，無 repo workflow 權限 | dependency PR；`dependabot-auto-merge.yml` 的 `sync-template` job 在同一張 PR 內補齊 paired workflow 的 template 副本 | GitHub 原生功能，無 repo-local 測試；設定格式由 `scripts/sync-paired-files.sh --check` 涵蓋；Actions pin 一致性見 `tests/test_check_action_pins.py` | GitHub 註冊為 `Dependabot Updates`（`dynamic/dependabot/dependabot-updates`），state active（原生排程不透過 `gh run list` 查詢單筆 run） | active；`sync-template` job：candidate（待 `main` 落地並於首張真的改到 paired workflow 的 Dependabot PR 觸發後轉 active） |
| Version／Release | `.github/workflows/release.yml` | #369／#430／#588／#591／#598 | `main` push（post-merge）、manual rerun | top-level read；單一 release job 才有 `contents`／PR／Issue／status write；30 分鐘 | Automatic 或 Guided 版本 PR；合併後由同一 workflow 發布 tag／GitHub Release／成品／checksum／SBOM | `tests/test_release_policy.py`、`tests/test_release_bundle.py`、`tests/test_journey07_release.py` | 已落地 `main` 並於 push 後實際觸發，`gh api tags`／`releases` 顯示過去確有真實 live 發版（`v0.12.2`／`v0.12.1`／`v0.12.0` 等）。`#588`（`docs/index.html` staleness）已由 `#593` 修正並於下一次 push 驗證：run [33763104406](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33763104406)（`6aa7724`，2026-09-03T13:47Z）的 `Static assets and paired files` 階段確實轉綠。但同一筆 run 在 `Regression tests` 階段仍以其他真實 pytest 失敗（`PR lifecycle blocked: Unleased PR lifecycle writer: .github/workflows/dependabot-auto-merge.yml`，導致生成專案 `scripts/verify` 失敗，牽連 `test_real_template_adoption_resumes_after_manifest_merge` 三種語言變體與 `test_real_existing_adoption_uses_fixed_ownership_policies`）——這是本輪盤點才發現、與 `#588`／`#591` 都無關的第四個獨立成因，尚未開對應 Issue。另外兩個較早的獨立成因：run [33719533651](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33719533651)（`9ed3594`）與 run [33730000169](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33730000169)（`99f52ef`）在 `Regression tests` 階段失敗於 `rm: cannot remove '.../work/.git': Directory not empty`，追蹤於 `#591`；run [33724898939](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33724898939)（`7719d2e4`）與 run [33729747815](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33729747815)（`ed7ab25`）在 `verify-template.sh` 全過後，於發版前 capability preflight 因 Actions policy HTTP 403 觸發 `#123` 既有設計的 fail-closed（`BLOCK_REASON: ... immutable_releases`），這是刻意行為、不是 bug | active for `verify`／`title`／`promotion`；`Regression tests` 階段三個獨立成因（PR-lifecycle writer 檢查 #602、`test_pr_lifecycle.py` 生成專案路徑 #617、zizmor template-injection #620）與 `#591` 均已修復並於 `verify-template.sh` 全綠驗證。當時（2026-09-03）hosted 版本發布（Automatic／Guided）因 `immutable_releases` capability probe 在 `GITHUB_TOKEN` 下結構性回傳 403（見 #626）而**已知永久限制**；`#770`（2026-09-18）移除了這一項 pre-flight probe，改在 `scripts/publish-release` 內以 post-hoc 的 GitHub 簽發 release attestation 驗證取代，hosted Automatic／Guided 不再因這一項結構性卡死，見上方「hosted 發版路徑的已知限制」一節——本機 `scripts/publish-release` 仍是本節其餘 `verify`／`title`／`promotion` 等機制沿用的標準發版程序，不因此改變定位 |
| Release publish drift alert | `.github/workflows/release-drift.yml` | #605（源自 #589 item 4） | daily schedule＋`workflow_dispatch`（`hours` input） | `actions: read`、`contents: read`、`issues: write`；5 分鐘 | 偵測到 drift 時開立或更新追蹤 Issue；未偵測到時只印出證據 | `scripts/test-check-release-drift` | 尚未 merge 進 `main`，故無排程或手動觸發的 live run 證據 | candidate（待 main 落地＋首次排程／手動觸發） |

所有第三方 Actions 鎖定完整 commit SHA，旁註可讀 release tag。Workflow YAML 只負責
event、權限、環境與呼叫；分類與驗證規則留在本機可測的 scripts。Repository 預設
`GITHUB_TOKEN` 為 read-only；release job 只在自己的 workflow 提升必要權限。Automatic
模式必須允許 Actions 建立 PR；若上層政策禁止則使用 Guided，workflow 仍不能自行核准版本 PR。

上表只列本 repo 自己的 active automation。生成 repo 另有一個選用能力：開啟
`enable_template_update_notifications` 才產生 `template-update.yml`
（`schedule`／`workflow_dispatch`、`contents: read`＋`issues: write`、10 分鐘
timeout，只呼叫 `scripts/check-template-update`）。公開模板來源不需要 secret；
來源為 private repository 時，才由唯讀的 `CSARC_TEMPLATE_READ_TOKEN` repository
secret 提供存取，且只有 `schedule`／`workflow_dispatch` 路徑讀得到，不會流向
`pull_request` workflow。本 repo 是模板來源本身，不消費也不排程這個 workflow。

生成 repo 另有一個選用容器能力（Issue #554 決定）：開啟 `enable_docker` 才產生
`Dockerfile`、`docker-compose.yml` 兩份起始範本，以及
`.github/workflows/docker-build-scan.yml`（`pull_request`，限 Dockerfile／
docker-compose.yml／已選語言原始碼路徑變更，另加 `workflow_dispatch`；
`contents: read`；20 分鐘 timeout）。該 job 只呼叫 `docker/build-push-action`
（`push: false`）在 runner 本機建置映像，再用 `aquasecurity/trivy-action`
掃描同一本機映像的已知漏洞（`HIGH`／`CRITICAL` 失敗），全程不登入、不推送任何
registry，也不要求任何 secret。未開啟 `enable_docker` 的專案不會產生上述任一
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

驗證契約只有兩個成本邊界，粒度由粗到細另有一種本機專用、不屬於 CI 政策的第零層：

1. **開發中 focused check（本機專用，不是 CI 的第三種政策）**——直接執行單一命令，例如
   `uv run pytest <path>`、`uv run ruff check <path>`，或針對
   `scripts/verify-template.sh` 其中一階段單獨重跑對應的
   `scripts/verify-stage-<name>`；不需要等待整條 pipeline，也不會被當成合併證據。
2. **日常 PR gate（`docs`／`fast`，同一個成本邊界）**——`scripts/ci_tier.py` 依事件、
   base／head、labels 與 changed paths 做 fail-closed 分類；未知或高風險內容升級為
   full。純文件／site 變更落在 `docs`，是 `fast` 的 early-exit 實作細節，不是獨立的第
   四套政策；其餘一般變更落在 `fast`。兩者入口都是 `scripts/verify-fast`，且自 #661 起
   **一律本機執行**：hosted `verify` job 不再自己跑這個入口，只驗證它成功時留下的
   attestation（見上方「`verify` 必要檢查改為本機驗證聲明（#661）」一節），所以即使是
   `fast`／`docs` 這種輕量分級，push 前仍必須先在本機跑過一次。
3. **完整交付驗證（`full`）**——只在 Milestone／canary 交付、hotfix、merge queue、手動
   執行或未知高風險路徑觸發；中央模板入口是 `scripts/verify-template.sh`，生成 repo
   入口是 `scripts/verify`（不帶參數即預設 full）。PR owner／integrator 只在自己的 PR
   本身就落在這個邊界時，才需要在本機另外執行一次；一般 `fast`／`docs` PR 不需要在本機
   重跑 full（但仍需要跑一次 `fast`，見上一點）。

數據來自 #428／PR #431 在 2026-09-01 的最新 hosted run，目的是設定成本預期，不是永久 SLA；
`full` 一列已由 #458 在 2026-09-02 於同一本機環境重新量測（見下方階段盤點與 PR 內文的
before／after 紀錄）。

| 分級 | 適用範圍 | 入口與測試集合 | 實測 |
| --- | --- | --- | --- |
| docs | 純文件與 site 內容 | `scripts/verify-fast`；來源檢查、render、雙語／glossary／llms 契約 | 與 fast 共用 bounded path |
| fast | 一般工作 PR；依 scope 加 policy／template 檢查 | `scripts/verify-fast`；source fast 約 59 秒，policy／template scope 約 99 秒 | 約 1–4 分鐘的 PR feedback window（#428） |
| full | Milestone／canary 交付、hotfix、merge queue、manual、未知高風險路徑 | 中央模板用 `scripts/verify-template.sh`；生成 repo 用 `scripts/verify full`（不帶參數時的預設行為） | 中央模板 verification 502 秒（8 分 22 秒，獨占環境全綠）；同機器有其他 worktree 並行執行時量到 810 秒，差異來自並行負載，不是本次變更（#458，2026-09-02） |

相依 manifest／lockfile 變更加跑 `scripts/verify-dependencies`。CI 不建立 release asset，
也不把測試 artifact 當成正式成品。#408 已把更細的 stage timing 輸出納入現行入口。

### Base-only re-merge 例外（#468）

**#661 之後的現況（讀本節其餘部分前先看這段）**：本節原本的結論——四個條件同時成立時可以
「直接 push 並信任 hosted `verify` check，不必再本機重跑」——所依賴的前提是「hosted CI 對這次
合併結果仍會重新執行一次完整驗證」。`#661` 把 hosted `verify` job 改成只驗證本機留下的
attestation、不再重新執行任何東西之後，這個前提不成立了：重新合併產生的新 tip commit 沒有自己
的 trailer，會被 hosted job 當成任何其他未經驗證的 push 一樣 fail closed，不會因為它符合下列四
個條件就自動放行。這不是 `#661` 範圍內要解決的問題（`#661` 的邊界明確只處理 attestation 機制本
身，不重新設計本節），因此下列四個條件描述的判斷仍然正確、`scripts/check-base-only-remerge` 仍
然如實回答「這次重新合併乾不乾淨、有沒有動到驗證基礎設施」——只有最後一步「所以可以直接 push、不
用本機重跑」目前不成立：符合四個條件只證明重新合併本身沒有引入新風險，不能讓 hosted job 平白生出
一個它本來就不會再產生的驗證結果。在後續 Issue 重新調和這兩個機制之前，即使四個條件都成立，仍要在
本機對新的 tip 重跑一次 `./scripts/verify-template.sh`（生成 repo：`./scripts/verify`），取得它
自己的 attestation。

上表「full」列與 #458 規則只回答「這張 PR 要不要跑 full」：只有 PR 本身落在 full 邊界
時，owner／integrator 才需要在最終候選樹本機執行一次 `./scripts/verify-template.sh`
（生成 repo 是 `./scripts/verify`）。這條規則沒回答的是另一個問題：**同一張已經跑過
這一次本機全綠的 PR，之後因為共用整合分支（例如本 Milestone 的 `dev/m8-hugo-docs`）
持續前進、被迫重新合併 base 時，是不是每次都要重跑同一套完整驗證。** 本節是 #458 規
則的窄範圍例外，回答「同一張 PR 內，什麼時候可以不用每次都重跑」——**不是**放寬「full
-tier PR 永遠不用本機跑」，也不代表任何 PR 的第一次本機全綠可以省略。

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

以下情況**明確不符合**本節例外，一律仍要求本機重跑，不確定時也一律視為不符合：

- 重新合併產生真實衝突（無論是否已手動解決）。
- 上游變更觸及這個 branch 自己這一輪已驗證的任何檔案，即使只是同一檔案的不同行、不會
  造成文字衝突。
- 上游變更觸及上方條件 4 列出的驗證／CI／政策基礎設施。
- 這個 branch 在上次本機全綠之後，又有新的自有 commit（不是單純的 base 重新合併）。
- 這次 push 本身就是新的 full-tier 邊界起點（例如這是這張 PR 第一次落入 full 邊界，或
  是另一條獨立的 hotfix／canary／manual 路徑），而不是同一張已驗證 PR 的後續重新合併。

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
`template/scripts/verify-fast.jinja` 必須逐項相等（`tests/test_journey03_ci.py::
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
四種結果，掛在 `scripts/verify-fast` 的 governance／template／workflow／shell
scope 與 `scripts/verify-stage-regression-tests`）。這次變更不重新設計
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
| Static assets and paired files | `scripts/verify-stage-static-assets` | repo-site 可重現 render、workflow／shell 靜態分析、static-validation fixture 的正／反向覆蓋、root／template 配對檔案漂移 | fast 只在對應 scope 才跑其中個別項目（`docs` tier 跑 render 檢查；`workflow`／`shell` scope 才跑 lint）；full 一律跑全部四項，是唯一同時驗證全部四種風險的入口 |
| Python environment | `scripts/verify-stage-python-environment` | `uv.lock` 與 `pyproject.toml` 一致、環境可從鎖定版本安裝 | fast 的 `uv sync --locked` 是同一份鎖定契約；`uv lock --check` 只在 full 額外執行 |
| Python quality | `scripts/verify-stage-python-quality` | 格式、lint、靜態型別 | fast 對相同原始碼跑相同三個命令，兩者呼叫同一份工具鏈設定，無額外邏輯 |
| Regression tests | `scripts/verify-stage-regression-tests` | 完整 pytest（含 `large` 標記的 Copier create／existing-adoption／update 保存回歸）＋coverage 門檻，以及 Issue-triage／worktree-cleanup／PR-policy／scope-drift-gate／base-only-remerge／gh-issue-create／check-branch-fresh／PR-policy-status／release-drift／audit-fleet-adoption／create-milestone／`verify-template.sh` 聚合自我測試 | fast 只跑 `pytest -m "not large"`（略過 `large`），且只在 governance／template／workflow／shell scope 才跑 Issue-triage／worktree-cleanup／PR-policy／scope-drift-gate（`scripts/test-check-scope-gate`，見上方 Scope-drift gate enforcement 一節）四個 shell 自我測試；base-only-remerge、`scripts/gh-issue-create`（開 Issue 前本機先擋不合規標題，見 AGENTS.md 工作迴圈）、`scripts/check-branch-fresh`（開工前本機核對既有分支是否仍等於 `origin/<branch>`，見 AGENTS.md 工作迴圈）、PR-policy-status、`scripts/audit-fleet-adoption`（本機即時查詢 fleet 採用門檻、只印 stdout，見 #521）與 `scripts/create-milestone`（原子建立 Milestone 與其 tracker Issue，見 `docs/milestone-description.md`；#572）六支本機專用工具的自我測試都只在這個 full 專屬階段跑，不進 `verify-fast`（分別見上方 Base-only re-merge 例外一節與下方 PR policy 逐 step 判讀一節）；`scripts/test-check-release-drift`（mock `gh`，驗證上方「發版存量漂移偵測（`release-drift.yml`，#605）」一節的 drift 判定邏輯）也只掛在這個 full 專屬階段——`scripts/check-release-drift` 本身像 `release.yml` 一樣逐位元組下發到 `template/`，但比照 `release.yml`／`ci.yml` 沒有生成 repo 端本機再測試的既有慣例（下發前的 root 測試已足夠證明這份靜態、無 Jinja 條件式的實作正確），不隨腳本一起下發、也不掛進生成 repo 的 `scripts/verify`；`large` 覆蓋範圍只在 full 執行，是 Copier create／adopt／update 保存的唯一 regression source，未被任何字串比對或重複 profile 執行取代 |
| Package smoke test | `scripts/verify-stage-package-smoke` | wheel 可建置、已發布入口可從建置產物執行 | fast 不跑這個階段；改用範圍較窄的 Copier smoke copy（見下方 Journey 03 的 PR 級別 render/smoke） |
| GitHub Actions audit | `scripts/verify-stage-github-actions-audit` | workflow 權限與注入稽核（zizmor） | fast 不跑；workflow scope 的一般 PR 由 full 邊界（promotion／hotfix／merge queue／manual）覆蓋，不會被跳過 |

#### 驗證拓撲與可觀測性（#780）

驗證分成三種責任，不再把同一批 Python 測試複製到不同 repo 後重跑：

- **Root-only governance tests：**`tests/` 驗證本模板的 Milestone、PR、release、安全與
  Copier lifecycle；只由 root 的 fast／full 入口執行。`template/tests/` 只下發生成產品本身
  的 smoke test 與共用 marker policy hook，不再帶 21 個 root 治理模組及其 SBOM fixtures。
- **Generated-project contract checks：**每種語言組合仍實際經 Copier render，檢查 config、
  manifest 與語言專屬檔案；Python 相容性入口只跑 `runtime and not large` 的最小 smoke、
  建置 wheel 並從隔離環境 import。
- **One representative end-to-end profile：**full regression 只挑一個 Python＋TypeScript 組合
  執行生成專案的完整 `scripts/verify full`；Rust 只跑專屬 `scripts/verify rust`，不再重跑
  repository-wide checks。三種語言都有真實原生工具鏈證據；create／adopt／update 的保存契約
  則繼續由 root 的 `large` regression 提供，不用每種單語言 profile 再跑一次完整 verifier。

pytest marker 契約延續 #317／PR #364：`runtime` 表示每個受支援 Python runtime 都必須執行
的最小行為；`quarantine` 不會 skip、xfail 或 retry 測試，只附加追蹤資料。每個 quarantine
必須使用具名的 `owner`、完整 GitHub Issue URL `issue`、非空白 `reason`、ISO 日期
`expires` 與非空白 `remove_when`；欄位缺漏、格式錯誤或到期時，collection 直接 fail
closed。這個 marker 不得
用來讓 required gate 忽略失敗。

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
四個欄位；除了 `run_osv`（餵給 `scripts/verify-fast` 決定是否跑 `verify-dependencies`）
外，其餘三個目前只出現在 `GITHUB_STEP_SUMMARY` 的 routing evidence，沒有 workflow 依它
們另外調度執行——full tier 已涵蓋全部檢查，fast tier 直接用 `scopes` 決定子集，因此這幾
個欄位不構成第二套調度邏輯，暫不需要移除或重構；如果之後要精簡，需求方需先確認沒有其他
消費者依賴這些欄位的 evidence 呈現。

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

上方三層成本邊界只回答「這次改動落在哪一級」，Base-only re-merge 例外只回答「同一張已經
驗證過的 PR 要不要重跑」。這裡把兩者之間還沒寫清楚的問題——「這次到底要不要在本機跑一次
full」與「真的要跑時如何排序」——寫成可執行原則，延續這次 session 已經在用、源自
Milestone 8（#465／#466）教訓的 cheap-stage-first 模式，避免重演本機測試反覆鬼打牆
（redundant full rerun、網路瞬斷、環境競爭噪音耗掉大量時間）。

**先判斷要不要在本機跑，依序四步：**

1. 這張 PR 本身是不是 full-tier 邊界？不是的話，不必為了保險另外在本機跑一次 full；本機
   義務仍是對應分級的 `./scripts/verify-fast`（tier 由變更範圍決定），成功後留下的
   attestation 就是 hosted `verify` job 唯一驗證的東西（#661），不是「不必本機跑，直接信
   任 hosted」。
2. 是 full-tier 邊界：這個 branch 自己這一輪內容有沒有本機全綠跑過一次
   `./scripts/verify-template.sh`（生成 repo 是 `./scripts/verify`）？沒有的話，這正是
   #458 規則要求的那一次，不能省略。
3. 已經全綠過、現在只是因為 base 前進被迫重新合併：套用上方「Base-only re-merge 例外
   （#468）」四項條件，只回答「這次重新合併本身乾不乾淨、有沒有引入新風險」；但 #661 之
   後，即使四項條件全部成立，新的 tip commit 仍沒有自己的 attestation，仍要在本機對它重
   跑一次才能 push——見上方「#661 之後的現況」，這條例外目前省不下本機重跑本身。
4. 以上都不成立，才真的執行一次本機 full；開始前先確認沒有其他 worktree／`pytest`／
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

以上四步起頭判斷與 cheap-stage-first 排序，都不是放寬「full-tier PR 一定要本機全綠跑過
一次」的既有規則（#458），只回答「什麼時候該跑」與「真的要跑時怎麼跑最省時間」；merge
資格與 required check 仍由 Journey 08 與本文件既有規則決定。

## 版本、發版、交付與部署矩陣

| 邊界 | Issue／工作 PR | Milestone／canary 交付 PR | `main` | tag／manual event |
| --- | --- | --- | --- | --- |
| 版本意圖 | PR title 表達 major／minor／patch／no-release | 彙整已核准意圖，不自行配置版本 | 保留已審查內容 | 不從 tag 反推或改寫 source |
| 正式版本與 CHANGELOG | 一般工作不直接決定精確版本 | 交付 PR 不手改版本 | Automatic 由 Release Please 開版本 PR；受組織政策阻擋時，Guided 用同一規則在本機產生候選並開一般 PR | manual 只重跑同一流程，不另開版本來源 |
| CI | docs／fast／full 依風險 | 一律 full | release workflow 對目前 `main` 跑一次 full | 候選只跑版本／檔案／可打包 focused check；正式發布前已在 main 跑 full |
| 成品／checksum／SBOM | 不發布 | 不發布 | 版本 PR 合併後從精確 commit 建立 | draft Release 先上傳、下載重驗，成功才公開 |
| tag／GitHub Release | 不建立 | 不建立 | 版本 PR 合併後由唯一 release workflow 建立 | 重跑只驗同一 tag；不移動 tag、不重寫成品 |
| attestation／registry | 不建立 | 不建立 | 不自動啟用 | #439 已移除設定面（零 active 消費者），非留待選配 |
| deployment | 不適用 | 不適用 | 不適用 | 由有真實 runtime target 的產品 repo 定義 |

合併到 `main` 是 repository delivery，不等於 Release。公版本身與新生成 repo 使用 CSARC
提供的單一 workflow；既有 repo 保留 product-owned release workflow，Copier 不依檔名猜測、
不覆寫也不重複 dispatch。流程只用短效 `GITHUB_TOKEN`，不要求 GitHub App、PAT、registry
token 或空 deployment environment。GitHub 會把 `GITHUB_TOKEN` 建立或更新版本 PR 所產生的
PR workflows 設為等待人工核准；Automatic 由原 release run 驗證候選 SHA。若組織政策禁止
Action 建 PR，Guided 只在本機執行 `python3 scripts/release_policy.py prepare-candidate` 並由人
或 agent 開一般 PR；兩路共用版本計算、候選驗證與唯一 `release.yml` publisher。

### 版本號表示發布層級（Issue #744，2026-09-17）

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
（`template/scripts/` 與 `src/csarc_cli/release_phase.py` 各有一份逐位元組相同的
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
合併條件。下游 `csarc update` 若確認記錄的 `release_tag`在 canonical repository
已不存在（GitHub 回報 404，`ReleaseNotFoundError`），改走重新安裝流程：重用
`csarc adopt`（#219）同一套 transactional plan 機制列出新增／覆寫／保留／人工合併
項目，經使用者確認才套用，project-owned 檔案一律保留；只有 tag 確認不存在才觸發，
其他驗證失敗（attestation 不符、tag 指向改變、簽章無效、repository identity 不符）
一律維持 fail closed。詳見 `docs/adr/release-security-and-dependencies.md` 與
`docs/adr/transactional-repository-adoption.md` 的新增段落。

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

**設計：** Guided 模式（[版本／交付 ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/release-security-and-dependencies.md) 決策）原本只在「組織政策禁止 Actions 建立 PR」時啟用；本節把同一條路徑的啟用條件擴大為「維護者或 agent 判斷 Actions／webhook 目前不可信任」時同樣可以啟用，機制不變：`python3 scripts/release_policy.py prepare-candidate` 在本機計算版本與 CHANGELOG，人或 agent 開一般 PR，經過與其他 `main` PR 相同的 review 才能合併——本機執行不能成為省略審查的手段。合併後的發布步驟（建 tag、draft Release、build 成品、checksum、SPDX SBOM、`gh release` 系列指令）改抽成 `scripts/publish-release`，`release.yml` 與本機路徑呼叫同一份實作，不維持兩套邏輯。

**代價（不能只講好處）：**

- **放棄 hosted runner 的乾淨、一致環境保證。** 本機執行的環境不由 GitHub 控管；只有本機 `full` 驗證全綠才能視為等同 hosted 的證明強度。
- **需要本機或執行者持有具備 admin／write 權限的長效憑證，而不是 Actions 短效 `GITHUB_TOKEN`。** 這不是為所有 CSARC-owned repo 新增一項標準要求——`scripts/apply-repository-settings.sh apply` 本來就已經要求 repo admin 用自己的 `gh` 身分執行；本節只是讓同一位已經持有這個權限的維護者，多一個「用同一身分完成發版」的選項。
- **沒有 merge 後自動觸發，需要人或排程主動執行。** 需要另外一道獨立排程的存量檢查偵測「`main` 已經前進但過去 N 小時內沒有成功的 `release.yml` run 或 immutable stable GitHub Release」，取代目前完全仰賴人工檢查 Releases 頁面才會發現的狀態；這道檢查已由 `.github/workflows/release-drift.yml`／`scripts/check-release-drift` 落地，見下方「發版存量漂移偵測（`release-drift.yml`，#605）」一節。
- **本機執行結果的可稽核性不如 hosted run 的公開 log。** 緩解方式是強制在合併說明或 Issue 留言記錄執行者、commit SHA、指令與結果。
- **local-vs-hosted 邏輯漂移風險。** 緩解方式是本節設計的第一原則——單一 repo-local 腳本被兩種呼叫方式共用。

**明確保留 GitHub Actions 為預設／建議路徑，不是全面棄用**：`verify`／`title`／`promotion` 三個 required status check 仍然、也必須繼續只由 hosted Actions 產生；CodeQL 上傳到 GitHub 原生 code-scanning 介面同樣不在本節適用範圍。

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
為 `blocked`（現在只可能來自 `contents`／`release`／`actions_pull_requests`），維持 #123 的
fail-closed 結果並在工具鏈 setup 前停止。只有未被擋下的實際 release 路徑才先驗證既有
local attestation，接著安裝工具鏈並進入版本候選或發布步驟（#707）。這只把便宜判定移到
前面，不放寬驗證、權限或供應鏈要求。

### Release 說明文字的最低格式規範（#616）

M8 補發版（#587）過程中發現：`release.yml` 產生的 GitHub Release 說明文字，完全交給
`googleapis/release-please-action`（Automatic）或本機 candidate 產生，沒有任何規定
「一則正式 Release 的說明文字最低限度要包含什麼」。上兩節把本機 `scripts/publish-release`
從 fallback 升格為標準程序後，Release 內容理論上可能來自兩種不同執行環境（hosted
Actions 或本機），本節盤點實際程式碼路徑，回答這個風險是否需要額外規範或檢查。

**盤點結論：整個 repo 只有一個程式碼路徑會建立 Release 說明文字。**
`scripts/converge-release-tag` 是唯一呼叫 `gh release create` 的地方：

```bash
gh release create "$tag" --target "$sha" \
  --title "$tag" --draft --generate-notes
```

`scripts/publish-release stage`（Automatic 與 Guided 共用同一個進入點）呼叫這支腳本；
`release.yml` 與本機執行都呼叫同一份 `scripts/publish-release`。`googleapis/
release-please-action` 在 Automatic 路徑只負責開版本 PR、同步版本檔與 CHANGELOG，
不建立 Release 也不寫入 Release 說明；`release_policy.py prepare-candidate` 在 Guided
路徑同樣只改版本檔與 CHANGELOG，不建立 Release。兩條路徑最終都收斂到
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

1. `main` HEAD 未被最新 immutable stable GitHub Release 的精確 target 涵蓋，也不是最新一次成功 `release.yml` run（`gh api repos/{repo}/actions/workflows/release.yml/runs?branch=main&status=success`）所在的 commit。
2. 過去 N 小時內，既沒有有效的 immutable stable Release，也沒有成功的 `release.yml` run。

最新 eligible Release 必須由 GitHub API 明確回報 `immutable=true`；其 `target_commitish` 必須是精確 40 字元 SHA，且等於 `main` HEAD，或經 GitHub compare API 證明為其 ancestor；`published_at` 還必須不早於目前 `main` commit。精確 target 會持續視為涵蓋該 HEAD；ancestor target 只算 N 小時內的近期發布活動，不能永久掩蓋較新的 `main`。mutable Release、draft、非 ancestor target、移動中的 branch ref 或比目前 `main` 更早發布的 Release 都不能壓掉告警。這使 immutable GitHub Release 本身成為首要發布事實，不再要求一條已知會被 #123 fail closed 的 hosted run 偽裝成成功。

**Issue #744（版本號表示發布層級）之後：** `-alpha.N`／`-beta.N` 的 pre-release Release 不再被當成無效發布忽略——tag 必須是合法的 alpha/beta/early/formal 版本號，且 GitHub 回報的 `prerelease` 旗標必須與 tag 格式一致（兩者矛盾時同樣壓不下告警，`reason` 會標成 `ignored: prerelease flag does not match tag shape`），否則視為 `ignored: tag is not a legal release-phase version`。挑選「最新」時仍以 `published_at` 排序（本節要問的是「發版路徑最近是否真的動過」，不是「哪個版本號優先序最高」；CLI 選版才用 SemVer 優先序，見上面 README／`src/csarc_cli/cli.py` 的說明）。

`release.yml` 在每次 push 到 `main` 後都會執行，即使 `release_policy.py` 判定「今天不需要發版」也會正常執行完成（conclusion 仍是 success）；因此健康狀態下，最後一次成功 run 的 commit 幾乎總是等於當下 `main` HEAD，條件 1 不成立，不會誤報。只有在 `release.yml` 真的不再執行成功、而 `main` 仍透過一般 PR 合併前進時（兩者是各自獨立的觸發：merge 不需要 `release.yml` 成功），條件 1 才會成立；再疊上條件 2（N 小時內真的沒有任何成功活動），才判定為 drift。

**N 預設 24 小時**，可用 `RELEASE_DRIFT_HOURS` 環境變數或 workflow 的 `hours` workflow_dispatch input 覆寫。`release.yml` 正常在 push 後幾分鐘內就有結果；24 小時涵蓋「一整天沒有任何 release 相關 push」的正常空窗期，不誤報安靜的一天，同時仍能在同一個工作日內就被發現，不會像 #587 一樣拖過一整個週末。

**本機發版紀錄只作稽核用途**：#589 的既有約定仍要求在合併說明或 Issue／PR 留言留下：

```text
Release-publish-record: operator=<@handle> commit=<sha> command="<command>" result=<result>
```

這筆文字能補足本機執行缺少 hosted log 的公開稽核脈絡，但 commit 訊息與 Issue／PR 留言都是可變、可重播的聲明，無法證明 GitHub 上的 Release 狀態。`scripts/check-release-drift` 仍會讀取、驗證格式並在摘要與追蹤 Issue 顯示最新一筆作為診斷資訊，但不讓它改變 drift 結果；讀取稽核資料若失敗只會留下 warning 並當作無紀錄，不得阻斷權威判定與告警。有效紀錄只接受 `operator`、`commit`、`command`、`result` 四欄，其中 `command` 最長 512 字元且不得含反引號，以免稽核文字撐爆 Issue body 或跳脫行內 code。只有 GitHub API 回報的 immutable stable Release 與該 repository 的成功 `release.yml` run 能抑制告警。

**這支 workflow 只偵測與通知，不接手發版**：既不會自動觸發 `release.yml` 重跑，也不會自動執行 `scripts/publish-release`；是否接手仍由人或 agent 判斷，維持 #589 既有的「人或 agent 主動決定啟用」設計原則。

**下發到 `template/`**：`.github/workflows/release-drift.yml` 與 `scripts/check-release-drift` 透過 `scripts/sync-paired-files.sh` 與 root 保持逐位元組同步，並在 `copier.yml` 重用既有 `.github/workflows/release.yml` 的 `project_mode == 'new'` exclude 條件，不新增第二個 Copier 選項——生成 repo 只要擁有 `release.yml`（`release_ownership == csarc-owned`）就會同時擁有這支漂移檢查，兩者不會分開存在。
