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

**使用留痕（alpha／beta 都要）**：每次真的用這個 bypass（`gh pr merge --admin`）合併
PR，必須在同一張 PR 上、合併之前，用 `gh pr comment` 留下一行結構化訊息：

```text
bypass-trace: release_phase=<alpha|beta> actor=<github-login> reason=<簡短原因>
```

`scripts/check-bypass-trace <PR 編號> --repo <owner/repo>`（核心比對邏輯在
`scripts/check_bypass_trace.py`，回歸測試在 `tests/test_check_bypass_trace.py`）
查核一張已合併 PR 是否在合併時間之前留有符合格式的留痕註解；PR 未合併時回報
「尚無需查核」，已合併但找不到留痕則 fail closed（exit 1）。自動判斷「這張 PR
是否真的用了 bypass」（交叉核對 review／required-check 實際狀態，
`scripts/generate_audit_trail.py` 已在抓這些欄位）目前不在這個查核工具範圍內：
`generate_audit_trail.py`（#535／#564）尚未併入 `main`，屬於獨立進行中的
Milestone 13 work，本 Issue（#607）維持獨立、不依賴它；一旦它併入 `main`，可以
再擴充 `check-bypass-trace` 交叉核對哪些 PR 疑似用了 bypass。目前的查核方式是
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

### 不屬於里程碑的工作

一張 Issue 若能獨立審查、驗證與交付，且沒有共同期限、跨 Issue 相依、整批驗收或
soak／canary 需求，就不必加入里程碑。它從最新 `main` 建立 topic branch，PR 直接回
`main`，接受一般 review 與風險分級驗證，並以 `Closes #N` 在合併後結案。合併只代表
repository delivery；後續由 release workflow 判斷是否需要建立版本 PR。

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
fallback（#589）」一節的責任，兩者是各自獨立的問題，不合併成同一節。

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

## Current automation

下表逐項列出 canonical file、owner、觸發（輸入）、權限／timeout、產物（輸出）、測試與
最新 live evidence；檔案存在或舊 run 成功不單獨算 active——見 Dependency vulnerability
與 Work Issue closure 兩列的落地與失敗證據。Live evidence 以 2026-09-01 對
`Innoguard-Cyber-Arch/csarc-repo-template` 的 `gh api actions/workflows` 與
`gh run list` 查詢結果為準；重跑本盤點請重新查詢，不沿用本表數字。

| 能力 | Canonical file | Owner | 事件（輸入） | 權限／timeout | 產物（輸出） | 測試 | 最新 live evidence | 狀態 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CI | `.github/workflows/ci.yml` | 驗證分級（#392／#403／#428）；本機驗證聲明（#661） | `pull_request`、`merge_group`、`workflow_dispatch` | `contents: read`；15 分鐘；同一 PR 新 commit 取消舊 run | `scripts/ci_tier.py` 分類（仍在 runner 上執行，是變更路徑分類邏輯，不是測試）後，只用 `scripts/check-verify-attestation` 驗證這個 PR 的實際 HEAD commit（`pull_request` 事件讀 PR 自己的 head sha，不是 GitHub 產生的 merge commit）是否帶有格式正確、hash 與 tree 相符、timestamp 新鮮、tier 足夠的 `Verified-locally:` trailer；不再於 runner 上執行 `scripts/verify-fast`／`scripts/verify-template.sh`（生成 repo：`scripts/verify`）——測試改在本機執行，成功時由這些腳本呼叫 `scripts/write-verify-attestation` 寫入 trailer；輸出 `verify` check 與 step summary | `tests/test_ci_tier.py`；`tests/test_journey03_ci.py` 的 `test_root_ci_is_one_bounded_verification_job`／`test_generated_ci_uses_the_same_one_job_contract`；`tests/test_verify_attestation.py`（純邏輯）與 `scripts/test-verify-attestation`（對真實 git repository） | run [33519320562](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33519320562)，2026-09-01，success——此 run 早於 #661，只證明 `scripts/ci_tier.py` 分類與（當時仍在 runner 上執行的）驗證邏輯，不代表本機驗證聲明改造 | `scripts/ci_tier.py` 分類：active（邏輯未變）；本機驗證聲明改造（#661 本身）：candidate（待 `main` 落地並於首次 PR 觸發後轉 active） |
| PR policy | `.github/workflows/pr-policy.yml` | PR／交付政策 | PR metadata 事件（opened／edited／synchronize／labeled）、`merge_group` | 只給需要的 Issue／PR metadata 權限；固定 timeout | `title` job：Issue、route 與 review policy 判定；`promotion` job（#601）：呼叫 `scripts/promotion_gate.py check-route` 分類 route，回報 `promotion` required check（`not-applicable`／`milestone`／`isolated`／`hotfix`／`release-recovery`／`release-follow-up`／`merge-queue` 成功，`invalid-main-route` 失敗） | `scripts/test-pr-policy`；`promotion` job 見 `tests/test_promotion_gate.py` 的 `test_check_route_*` | run [33519320929](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33519320929)，2026-09-01，success；同日對 #448／#453／#457 等未完成 checklist 的候選 PR 正確擋下合併，證明門禁確實生效 | `title` job：active；`promotion` job：candidate（隨 #601 首次落地，尚無 live run，待 `main` 落地並於首次 PR 觸發後轉 active） |
| Dependency vulnerability | `.github/workflows/osv.yml` | 依賴安全（#406／#407） | weekly schedule、manual、相關 manifest／lockfile 變更 | `contents: read`；固定 timeout | OSV 掃描結果 | `tests/test_dependency_security.py` | 2026-09-01 以 `gh api repos/.../actions/workflows` 查詢：GitHub 僅註冊 7 支 workflow，**不含 `osv.yml`**——本檔尚未落地 `main`，且觸發條件不含 `pull_request`，候選分支無法預先註冊。前身「OSV scheduled scan」最後已知 run 於 2026-08-24 全部 failure，屬歷史證據，不代表本候選 | **root：candidate**（待 main 落地＋首次排程／手動觸發）；**新生成 repo：active**（Copier 初次 commit 即進入該 repo `main`，可立即註冊與觸發） |
| Work item lifecycle | `.github/workflows/work-item-lifecycle.yml` | #400／#401／#574（合併） | `issues`、`issue_comment`、`milestone` 事件；`pull_request.closed`（里程碑工作 PR 合併進 `dev/m*` 或 `promote/m*` 晉升 PR 合併進 `main`） | 單一 job 內所有 step 共用的最小權限集合：`checks: write`、`contents: read`、`issues: write`、`pull-requests: read`；5 分鐘 | label／milestone routing、lifecycle gate 狀態與 closure 同步、對應 Issue 關閉 | `scripts/test-issue-triage`、`tests/test_journey06_workflows.py`、`tests/test_milestone_lifecycle.py`（本候選尚未含 #444 已拆分的 `test_milestone_approval.py`／`test_milestone_closure.py`，待 #444 併入才更新）、`tests/test_work_pr_closure.py` | 尚未落地 `main`，無新 live run；三個前身 workflow（`issue-triage.yml`、`milestone-lifecycle.yml`、`work-item-closure.yml`）已刪除，其舊 run 證據（`33524318953`／`33524281794`／`33502286588`）不再代表現行檔案 | **root：candidate**（待 main 落地並觸發首次 issues／issue_comment／milestone／pull_request 事件才能取得新 live evidence）；#574 只把三個 workflow 檔的既有邏輯打包成一個 job 內的循序 step，不改變任一 step 本身的行為、權限需求或所呼叫的 script |
| Spec to Issue | `.github/workflows/spec-to-issue.yml` | Spec 轉換 | spec 檔案變更事件／manual dispatch | 最小 Issue metadata write | 可審查 Issue 草稿 | `tests/test_spec_to_issue.py` | run [33490382161](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33490382161)，2026-09-01，success | active |
| Dependabot | `.github/dependabot.yml` | GitHub 原生＋依賴安全 | schedule／manifest 變更 | GitHub 原生 bot 邊界，無 repo workflow 權限 | dependency PR | GitHub 原生功能，無 repo-local 測試；設定格式由 `scripts/sync-paired-files.sh --check` 涵蓋 | GitHub 註冊為 `Dependabot Updates`（`dynamic/dependabot/dependabot-updates`），state active（原生排程不透過 `gh run list` 查詢單筆 run） | active |
| Version／Release | `.github/workflows/release.yml` | #369／#430／#588／#591／#598 | `main` push（post-merge）、manual rerun | top-level read；單一 release job 才有 `contents`／PR／Issue／status write；30 分鐘 | Automatic 或 Guided 版本 PR；合併後由同一 workflow 發布 tag／GitHub Release／成品／checksum／SBOM | `tests/test_release_policy.py`、`tests/test_release_bundle.py`、`tests/test_journey07_release.py` | 已落地 `main` 並於 push 後實際觸發，`gh api tags`／`releases` 顯示過去確有真實 live 發版（`v0.12.2`／`v0.12.1`／`v0.12.0` 等）。`#588`（`docs/index.html` staleness）已由 `#593` 修正並於下一次 push 驗證：run [33763104406](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33763104406)（`6aa7724`，2026-09-03T13:47Z）的 `Static assets and paired files` 階段確實轉綠。但同一筆 run 在 `Regression tests` 階段仍以其他真實 pytest 失敗（`PR lifecycle blocked: Unleased PR lifecycle writer: .github/workflows/dependabot-auto-merge.yml`，導致生成專案 `scripts/verify` 失敗，牽連 `test_real_template_adoption_resumes_after_manifest_merge` 三種語言變體與 `test_real_existing_adoption_uses_fixed_ownership_policies`）——這是本輪盤點才發現、與 `#588`／`#591` 都無關的第四個獨立成因，尚未開對應 Issue。另外兩個較早的獨立成因：run [33719533651](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33719533651)（`9ed3594`）與 run [33730000169](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33730000169)（`99f52ef`）在 `Regression tests` 階段失敗於 `rm: cannot remove '.../work/.git': Directory not empty`，追蹤於 `#591`；run [33724898939](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33724898939)（`7719d2e4`）與 run [33729747815](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33729747815)（`ed7ab25`）在 `verify-template.sh` 全過後，於發版前 capability preflight 因 Actions policy HTTP 403 觸發 `#123` 既有設計的 fail-closed（`BLOCK_REASON: ... immutable_releases`），這是刻意行為、不是 bug | active for `verify`／`title`／`promotion`；`Regression tests` 階段三個獨立成因（PR-lifecycle writer 檢查 #602、`test_pr_lifecycle.py` 生成專案路徑 #617、zizmor template-injection #620）與 `#591` 均已修復並於 `verify-template.sh` 全綠驗證。但 hosted 版本發布（Automatic／Guided）確認為**已知永久限制**：`immutable_releases` capability probe 在 `GITHUB_TOKEN` 下結構性回傳 403（見 #626），`#123` 的 fail-closed 是刻意行為不會解除，也不透過本表修正——本機 `scripts/publish-release` 已升格為標準發版程序，見上方「hosted 發版路徑的已知限制」一節 |
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
fail」（#572，本文件更新時仍為 open、尚未併入 `main`）。本節先記錄操作慣例與依賴關係；
#572 併入前沒有可執行指令可用，不因此阻塞本 Issue 其餘的合併範圍。#572 併入後應回頭
補上實際指令與呼叫方式。

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
| Static assets and paired files | `scripts/verify-stage-static-assets` | decision site 可重現 render、workflow／shell 靜態分析、static-validation fixture 的正／反向覆蓋、root／template 配對檔案漂移 | fast 只在對應 scope 才跑其中個別項目（`docs` tier 跑 render 檢查；`workflow`／`shell` scope 才跑 lint）；full 一律跑全部四項，是唯一同時驗證全部四種風險的入口 |
| Python environment | `scripts/verify-stage-python-environment` | `uv.lock` 與 `pyproject.toml` 一致、環境可從鎖定版本安裝 | fast 的 `uv sync --locked` 是同一份鎖定契約；`uv lock --check` 只在 full 額外執行 |
| Python quality | `scripts/verify-stage-python-quality` | 格式、lint、靜態型別 | fast 對相同原始碼跑相同三個命令，兩者呼叫同一份工具鏈設定，無額外邏輯 |
| Regression tests | `scripts/verify-stage-regression-tests` | 完整 pytest（含 `large` 標記的 Copier create／existing-adoption／update 保存回歸）＋coverage 門檻，以及 Issue-triage／worktree-cleanup／PR-policy／base-only-remerge／gh-issue-create／check-branch-fresh／PR-policy-status／release-drift／audit-fleet-adoption／create-milestone／`verify-template.sh` 聚合自我測試 | fast 只跑 `pytest -m "not large"`（略過 `large`），且只在 governance／template／workflow／shell scope 才跑 Issue-triage／worktree-cleanup／PR-policy 三個 shell 自我測試；base-only-remerge、`scripts/gh-issue-create`（開 Issue 前本機先擋不合規標題，見 AGENTS.md 工作迴圈）、`scripts/check-branch-fresh`（開工前本機核對既有分支是否仍等於 `origin/<branch>`，見 AGENTS.md 工作迴圈）、PR-policy-status、`scripts/audit-fleet-adoption`（本機即時查詢 fleet 採用門檻、只印 stdout，見 #521）與 `scripts/create-milestone`（原子建立 Milestone 與其 tracker Issue，見 `docs/milestone-description.md`；#572）六支本機專用工具的自我測試都只在這個 full 專屬階段跑，不進 `verify-fast`（分別見上方 Base-only re-merge 例外一節與下方 PR policy 逐 step 判讀一節）；`scripts/test-check-release-drift`（mock `gh`，驗證上方「發版存量漂移偵測（`release-drift.yml`，#605）」一節的 drift 判定邏輯）也只掛在這個 full 專屬階段——`scripts/check-release-drift` 本身像 `release.yml` 一樣逐位元組下發到 `template/`，但比照 `release.yml`／`ci.yml` 沒有生成 repo 端本機再測試的既有慣例（下發前的 root 測試已足夠證明這份靜態、無 Jinja 條件式的實作正確），不隨腳本一起下發、也不掛進生成 repo 的 `scripts/verify`；`large` 覆蓋範圍只在 full 執行，是 Copier create／adopt／update 保存的唯一 regression source，未被任何字串比對或重複 profile 執行取代 |
| Package smoke test | `scripts/verify-stage-package-smoke` | wheel 可建置、已發布入口可從建置產物執行 | fast 不跑這個階段；改用範圍較窄的 Copier smoke copy（見下方 Journey 03 的 PR 級別 render/smoke） |
| GitHub Actions audit | `scripts/verify-stage-github-actions-audit` | workflow 權限與注入稽核（zizmor） | fast 不跑；workflow scope 的一般 PR 由 full 邊界（promotion／hotfix／merge queue／manual）覆蓋，不會被跳過 |

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

### Release 發版不依賴 Actions 健康度的 fallback（#589，2026-09-03）

2026-09-03 的實際事故（#587）證明「發版」目前完全綁在 `release.yml` 這一支 workflow 是否能在 GitHub Actions 上成功執行：M8 promotion 後，`docs/index.html` 過期讓 full-tier 驗證卡住，`main` 上每一次 push 觸發的 `release.yml` run 全部失敗，加上同一天稍早出現的 `pull_request` webhook 投遞間歇性異常，讓「能不能發版」完全停擺超過 8 小時、沒有人自動被通知，直到人工檢查 Releases 頁面才發現。既有的「Actions 額度 fallback」（見 [staged-delivery-and-verification ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/staged-delivery-and-verification.md)）解決的是不同的觸發條件：額度用盡有 GitHub 回傳的明確錯誤訊息（zero-step billing block），可以機械式偵測；本節處理的觸發條件——hosted runner 卡住、webhook 沒有投遞、或其他導致 Actions 本身不健康的狀況——**沒有對應的機械式訊號**：它看起來就是「什麼都沒發生」，而「什麼都沒發生」本來就有可能只是因為沒有東西需要發版。這個不對稱是本節 fallback 刻意設計成「人或 agent 主動決定啟用」而非自動觸發的原因，也是為什麼另外需要一道獨立排程的存量檢查——這道檢查因範圍與時間考量從 #589 拆分為獨立追蹤，已落地為下方「發版存量漂移偵測（`release-drift.yml`，#605）」一節。

**設計：** Guided 模式（[版本／交付 ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/release-security-and-dependencies.md) 決策）原本只在「組織政策禁止 Actions 建立 PR」時啟用；本節把同一條路徑的啟用條件擴大為「維護者或 agent 判斷 Actions／webhook 目前不可信任」時同樣可以啟用，機制不變：`python3 scripts/release_policy.py prepare-candidate` 在本機計算版本與 CHANGELOG，人或 agent 開一般 PR，經過與其他 `main` PR 相同的 review 才能合併——本機執行不能成為省略審查的手段。合併後的發布步驟（建 tag、draft Release、build 成品、checksum、SPDX SBOM、`gh release` 系列指令）改抽成 `scripts/publish-release`，`release.yml` 與本機路徑呼叫同一份實作，不維持兩套邏輯。

**代價（不能只講好處）：**

- **放棄 hosted runner 的乾淨、一致環境保證。** 本機執行的環境不由 GitHub 控管；只有本機 `full` 驗證全綠才能視為等同 hosted 的證明強度。
- **需要本機或執行者持有具備 admin／write 權限的長效憑證，而不是 Actions 短效 `GITHUB_TOKEN`。** 這不是為所有 CSARC-owned repo 新增一項標準要求——`scripts/apply-repository-settings.sh apply` 本來就已經要求 repo admin 用自己的 `gh` 身分執行；本節只是讓同一位已經持有這個權限的維護者，多一個「用同一身分完成發版」的選項。
- **沒有 merge 後自動觸發，需要人或排程主動執行。** 需要另外一道獨立排程的存量檢查偵測「`main` 已經前進但過去 N 小時內沒有成功的 `release.yml` run 或本機發版紀錄」，取代目前完全仰賴人工檢查 Releases 頁面才會發現的狀態；這道檢查已由 `.github/workflows/release-drift.yml`／`scripts/check-release-drift` 落地，見下方「發版存量漂移偵測（`release-drift.yml`，#605）」一節。
- **本機執行結果的可稽核性不如 hosted run 的公開 log。** 緩解方式是強制在合併說明或 Issue 留言記錄執行者、commit SHA、指令與結果。
- **local-vs-hosted 邏輯漂移風險。** 緩解方式是本節設計的第一原則——單一 repo-local 腳本被兩種呼叫方式共用。

**明確保留 GitHub Actions 為預設／建議路徑，不是全面棄用**：`verify`／`title`／`promotion` 三個 required status check 仍然、也必須繼續只由 hosted Actions 產生；CodeQL 上傳到 GitHub 原生 code-scanning 介面同樣不在本節適用範圍。

### hosted 發版路徑的已知限制，本機路徑升格為標準程序（2026-09-03）

上一段原本建議「一般情況下仍走 hosted `release.yml`」；當天稍後的補發版嘗試（接續 #587）證明這個建議不成立，予以修正：

`scripts/release_policy.py::detect_runtime_capabilities()` 對 `immutable_releases` 的 capability probe（`GET repos/{repo}/immutable-releases`）在 hosted release job 自己的 `GITHUB_TOKEN` 下**結構性、永久性**回傳無法判斷（HTTP 403）——這個端點屬於 repo administration 層級設定，GitHub Actions 的 `permissions:` 區塊沒有對應的合法 key 能開放給 `GITHUB_TOKEN`（曾誤加 `administration: read` 這個不存在的 key，直接讓 workflow YAML 整個 parse 失敗，見 #623／#624 的踩坑與回退記錄）。`select_release_mode()` 的 `PUBLISH_CAPABILITIES` 判定是 all-or-nothing（`contents`／`release`／`immutable_releases` 任一項 `blocked` 或 `unknown` 就整組判 `blocked`），Automatic 與 Guided 共用同一個前置關卡，兩條路徑都永遠過不了這一關——不是暫時性環境問題，也不是這次補發版才出現的新退化。

`docs/ci-policy.md` 更早已經記錄過同一現象源自 #123 的既有設計：HTTP 403 時 fail-closed 是**刻意的安全姿態**（拿不到證據就不發版），不是 bug。盤點過三個修法方向後（見 [#626](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/626) 完整記錄）：

1. 改成信任 `policies/releases.json` 宣告值、不再即時 probe——會推翻 #123 的立場，驗證變裝飾性，**不採用**。
2. 給 release job 一個只有 `administration: read` 的窄範圍 PAT repo secret——技術可行、不推翻 #123，但需要新增並之後輪替一個 secret，維護者評估管理成本後**不採用**。
3. **採用**：正式承認 hosted Automatic／Guided 對 `immutable_releases` 永遠無法自證，把本節上方的本機 `scripts/publish-release` 路徑從「fallback」升格為**標準發版程序**——不是備援，是預設做法；由 agent（Claude Code session）在維護者授權下本機執行，用維護者自己的 admin 身份，天生就能真的讀到這個設定，不需要額外 secret，也不推翻 #123。「自動化」的著力點從「push 進 main 自動觸發」改成「agent 執行、人不用碰指令」。

hosted `release.yml` 保留在 repo 裡（`verify`／`title`／`promotion` 仍然只能由它產生，不受影響），但它的 Automatic／Guided 版本發布功能正式標註為**已知限制，非待修復項目**——除非之後方向一或方向三的取捨改變，不會投入資源讓它自己成功發布。

### 發版存量漂移偵測（`release-drift.yml`，#605）

上面兩節解決「怎麼發版」與「hosted 路徑為什麼結構性過不了關」；兩者都沒有回答「發版流程本身停擺了，誰會知道」。2026-09-03 的 #587 事故正是在完全沒有人被通知的情況下，靠人工檢查 Releases 頁面才發現發版已經停擺超過 8 小時——本節把 #589 決定裡列為代價、當時尚未落地的那道獨立排程存量檢查做成具體實作。

**設計：** 新增獨立、只讀、與 `release.yml` 完全解耦的排程 workflow `.github/workflows/release-drift.yml`（`schedule` 每日一次＋`workflow_dispatch`，權限只有 `actions: read`／`contents: read`／`issues: write`，5 分鐘 timeout），鏡射既有 `.github/workflows/governance-drift.yml` 的模式：排程呼叫可獨立在本機執行的 `scripts/check-release-drift`，偵測到 drift 時開立或更新一張標題固定的追蹤 Issue（先找既有同標題 open Issue 就更新，避免重複開票），未偵測到 drift 時只印出證據、不建立或更新 Issue。刻意不是 `release.yml` 自己的一個 step——一支已經卡住或壞掉的 release pipeline 沒辦法可靠地告警自己的壞掉。

**偵測條件（兩者同時成立才判定為 drift）：**

1. `main` HEAD 不是最新一次成功 `release.yml` run（`gh api repos/{repo}/actions/workflows/release.yml/runs?branch=main&status=success`）所在的 commit，也不是最新一筆本機發版紀錄所在的 commit。
2. 過去 N 小時內，既沒有成功的 `release.yml` run，也沒有找到本機發版紀錄。

`release.yml` 在每次 push 到 `main` 後都會執行，即使 `release_policy.py` 判定「今天不需要發版」也會正常執行完成（conclusion 仍是 success）；因此健康狀態下，最後一次成功 run 的 commit 幾乎總是等於當下 `main` HEAD，條件 1 不成立，不會誤報。只有在 `release.yml` 真的不再執行成功、而 `main` 仍透過一般 PR 合併前進時（兩者是各自獨立的觸發：merge 不需要 `release.yml` 成功），條件 1 才會成立；再疊上條件 2（N 小時內真的沒有任何成功活動），才判定為 drift。

**N 預設 24 小時**，可用 `RELEASE_DRIFT_HOURS` 環境變數或 workflow 的 `hours` workflow_dispatch input 覆寫。`release.yml` 正常在 push 後幾分鐘內就有結果；24 小時涵蓋「一整天沒有任何 release 相關 push」的正常空窗期，不誤報安靜的一天，同時仍能在同一個工作日內就被發現，不會像 #587 一樣拖過一整個週末。

**本機發版紀錄的具體格式**（本節把 #589 只用文字描述的既有約定變成可被機器判讀的格式）：出現在 `main` 上一則 commit 訊息（即合併說明）、或本檢查自己開立的追蹤 Issue 留言中，符合：

```text
Release-publish-record: operator=<@handle> commit=<sha> command="<command>" result=<result>
```

`scripts/check-release-drift` 同時掃描這兩個來源；找到的紀錄若在 N 小時內，即使 `main` 已經前進到紀錄所在 commit 之後，仍視為「有人正在主動處理」而不誤報。

**這支 workflow 只偵測與通知，不接手發版**：既不會自動觸發 `release.yml` 重跑，也不會自動執行 `scripts/publish-release`；是否接手仍由人或 agent 判斷，維持 #589 既有的「人或 agent 主動決定啟用」設計原則。

**下發到 `template/`**：`.github/workflows/release-drift.yml` 與 `scripts/check-release-drift` 透過 `scripts/sync-paired-files.sh` 與 root 保持逐位元組同步，並在 `copier.yml` 重用既有 `.github/workflows/release.yml` 的 `project_mode == 'new'` exclude 條件，不新增第二個 Copier 選項——生成 repo 只要擁有 `release.yml`（`release_ownership == csarc-owned`）就會同時擁有這支漂移檢查，兩者不會分開存在。
