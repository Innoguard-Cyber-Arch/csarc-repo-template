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
`Closes #<tracker>` 直接關閉該 Milestone 的 tracker Issue，並由 `milestone-lifecycle.yml`
的 `record-promotion-evidence` job 在合併後自動把 merge commit 網址回填進 tracker 的
`Completion evidence` 段落（見 #512）；#400 與 #401 的自動結案契約不再是 blocked gap。
delivery branch 清理仍由 worktree 清理流程負責，不由版本或發版流程重複處理。

## PR lifecycle single-writer

Agent 或 automation 若要變更 PR 的 ready／draft、授權或 metadata，必須先取得 remote
lease，並透過 `scripts/pr_lifecycle.py` 執行；`scripts/verify` 會拒絕另一套重複寫入者。
人工在 GitHub 上審查與合併不受這個工具限制。

`gh pr merge --admin` 只能用來繞過文件明列的已知例外，目前僅一項：`pr-policy.yml`
`title` job 的「Validate Milestone approval」step（要求非提案者在 #440 留言）在
#512 解決前的過渡期。繞過前必須先確認同一個 `title` job 的「Validate pull request
policy」step 本身是 success，不能只看整個 job 或整個 PR 的 conclusion 就一併略過——
用 #513 的 `scripts/check-pr-policy-status`（完成前，改用
`gh run view <run-id> --log | grep -E "Validate pull request policy|##\[error\]"`
手動確認）。

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

## Current automation

下表逐項列出 canonical file、owner、觸發（輸入）、權限／timeout、產物（輸出）、測試與
最新 live evidence；檔案存在或舊 run 成功不單獨算 active——見 Dependency vulnerability
與 Work Issue closure 兩列的落地與失敗證據。Live evidence 以 2026-09-01 對
`Innoguard-Cyber-Arch/csarc-repo-template` 的 `gh api actions/workflows` 與
`gh run list` 查詢結果為準；重跑本盤點請重新查詢，不沿用本表數字。

| 能力 | Canonical file | Owner | 事件（輸入） | 權限／timeout | 產物（輸出） | 測試 | 最新 live evidence | 狀態 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CI | `.github/workflows/ci.yml` | 驗證分級（#392／#403／#428） | `pull_request`、`merge_group`、`workflow_dispatch` | `contents: read`；30 分鐘；同一 PR 新 commit 取消舊 run | `scripts/ci_tier.py` 分類後，中央模板呼叫 `scripts/verify-fast` 或 `scripts/verify-template.sh`，生成 repo 呼叫 `scripts/verify`；輸出 `verify` check 與 step summary | `tests/test_ci_tier.py` | run [33519320562](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33519320562)，2026-09-01，success | active |
| PR policy | `.github/workflows/pr-policy.yml` | PR／交付政策 | PR metadata 事件（opened／edited／synchronize／labeled） | 只給需要的 Issue／PR metadata 權限；固定 timeout | title、Issue、route 與 review policy 判定 | `scripts/test-pr-policy` | run [33519320929](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33519320929)，2026-09-01，success；同日對 #448／#453／#457 等未完成 checklist 的候選 PR 正確擋下合併，證明門禁確實生效 | active |
| Dependency vulnerability | `.github/workflows/osv.yml` | 依賴安全（#406／#407） | weekly schedule、manual、相關 manifest／lockfile 變更 | `contents: read`；固定 timeout | OSV 掃描結果 | `tests/test_dependency_security.py` | 2026-09-01 以 `gh api repos/.../actions/workflows` 查詢：GitHub 僅註冊 7 支 workflow，**不含 `osv.yml`**——本檔尚未落地 `main`，且觸發條件不含 `pull_request`，候選分支無法預先註冊。前身「OSV scheduled scan」最後已知 run 於 2026-08-24 全部 failure，屬歷史證據，不代表本候選 | **root：candidate**（待 main 落地＋首次排程／手動觸發）；**新生成 repo：active**（Copier 初次 commit 即進入該 repo `main`，可立即註冊與觸發） |
| Issue triage | `.github/workflows/issue-triage.yml` | Issue 分流 | `issues` 事件 | 最小 Issue metadata write | label／milestone routing | `scripts/test-issue-triage` | run [33524318953](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33524318953)，2026-09-01，`main`，success | active |
| Spec to Issue | `.github/workflows/spec-to-issue.yml` | Spec 轉換 | spec 檔案變更事件／manual dispatch | 最小 Issue metadata write | 可審查 Issue 草稿 | `tests/test_spec_to_issue.py` | run [33490382161](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33490382161)，2026-09-01，success | active |
| Milestone lifecycle | `.github/workflows/milestone-lifecycle.yml` | #400 | milestone／Issue 事件、核准 comment 偵測 | 最小 metadata write | lifecycle gate 狀態、closure 同步 | `tests/test_milestone_lifecycle.py`（本候選尚未含 #444 已拆分的 `test_milestone_approval.py`／`test_milestone_closure.py`，待 #444 併入才更新） | run [33524281794](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33524281794)，2026-09-01，`main`，success | active；完整結案契約仍由 #400／PR #444 擁有（尚未合併） |
| Work Issue closure | `.github/workflows/work-item-closure.yml` | #401 | 里程碑工作 PR 合併進 `dev/m*`（`pull_request.closed`） | `contents: read`、Issue write；5 分鐘 | 對應 Issue 關閉 | `tests/test_work_pr_closure.py` | run [33502286588](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33502286588)，2026-09-01，**failure**（checkout 用 `pull_request.base.sha`，缺合併後才有的 `close-work` 指令） | active（workflow 已啟用並真的執行）；已知 live 失敗，修正候選見 #401／PR #453，尚未合併 |
| Dependabot | `.github/dependabot.yml` | GitHub 原生＋依賴安全 | schedule／manifest 變更 | GitHub 原生 bot 邊界，無 repo workflow 權限 | dependency PR | GitHub 原生功能，無 repo-local 測試；設定格式由 `scripts/sync-paired-files.sh --check` 涵蓋 | GitHub 註冊為 `Dependabot Updates`（`dynamic/dependabot/dependabot-updates`），state active（原生排程不透過 `gh run list` 查詢單筆 run） | active |
| Version／Release | `.github/workflows/release.yml` | #369／#430／#588／#591／#598 | `main` push（post-merge）、manual rerun | top-level read；單一 release job 才有 `contents`／PR／Issue／status write；30 分鐘 | Automatic 或 Guided 版本 PR；合併後由同一 workflow 發布 tag／GitHub Release／成品／checksum／SBOM | `tests/test_release_policy.py`、`tests/test_release_bundle.py`、`tests/test_journey07_release.py` | 已落地 `main` 並於 push 後實際觸發，`gh api tags`／`releases` 顯示過去確有真實 live 發版（`v0.12.2`／`v0.12.1`／`v0.12.0` 等）。`#588`（`docs/index.html` staleness）已由 `#593` 修正並於下一次 push 驗證：run [33763104406](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33763104406)（`6aa7724`，2026-09-03T13:47Z）的 `Static assets and paired files` 階段確實轉綠。但同一筆 run 在 `Regression tests` 階段仍以其他真實 pytest 失敗（`PR lifecycle blocked: Unleased PR lifecycle writer: .github/workflows/dependabot-auto-merge.yml`，導致生成專案 `scripts/verify` 失敗，牽連 `test_real_template_adoption_resumes_after_manifest_merge` 三種語言變體與 `test_real_existing_adoption_uses_fixed_ownership_policies`）——這是本輪盤點才發現、與 `#588`／`#591` 都無關的第四個獨立成因，尚未開對應 Issue。另外兩個較早的獨立成因：run [33719533651](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33719533651)（`9ed3594`）與 run [33730000169](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33730000169)（`99f52ef`）在 `Regression tests` 階段失敗於 `rm: cannot remove '.../work/.git': Directory not empty`，追蹤於 `#591`；run [33724898939](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33724898939)（`7719d2e4`）與 run [33729747815](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33729747815)（`ed7ab25`）在 `verify-template.sh` 全過後，於發版前 capability preflight 因 Actions policy HTTP 403 觸發 `#123` 既有設計的 fail-closed（`BLOCK_REASON: ... immutable_releases`），這是刻意行為、不是 bug | active for `verify`／`title`／`promotion`；`Regression tests` 階段三個獨立成因（PR-lifecycle writer 檢查 #602、`test_pr_lifecycle.py` 生成專案路徑 #617、zizmor template-injection #620）與 `#591` 均已修復並於 `verify-template.sh` 全綠驗證。但 hosted 版本發布（Automatic／Guided）確認為**已知永久限制**：`immutable_releases` capability probe 在 `GITHUB_TOKEN` 下結構性回傳 403（見 #626），`#123` 的 fail-closed 是刻意行為不會解除，也不透過本表修正——本機 `scripts/publish-release` 已升格為標準發版程序，見上方「hosted 發版路徑的已知限制」一節 |

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

## 驗證分級與實測成本

驗證契約只有兩個成本邊界，粒度由粗到細另有一種本機專用、不屬於 CI 政策的第零層：

1. **開發中 focused check（本機專用，不是 CI 的第三種政策）**——直接執行單一命令，例如
   `uv run pytest <path>`、`uv run ruff check <path>`，或針對
   `scripts/verify-template.sh` 其中一階段單獨重跑對應的
   `scripts/verify-stage-<name>`；不需要等待整條 pipeline，也不會被當成合併證據。
2. **日常 PR gate（`docs`／`fast`，同一個成本邊界）**——`scripts/ci_tier.py` 依事件、
   base／head、labels 與 changed paths 做 fail-closed 分類；未知或高風險內容升級為
   full。純文件／site 變更落在 `docs`，是 `fast` 的 early-exit 實作細節，不是獨立的第
   四套政策；其餘一般變更落在 `fast`。兩者入口都是 `scripts/verify-fast`。
3. **完整交付驗證（`full`）**——只在 Milestone／canary 交付、hotfix、merge queue、手動
   執行或未知高風險路徑觸發；中央模板入口是 `scripts/verify-template.sh`，生成 repo
   入口是 `scripts/verify`（不帶參數即預設 full）。PR owner／integrator 只在自己的 PR
   本身就落在這個邊界時，才需要在本機另外執行一次；一般 `fast`／`docs` PR 不需要在本機
   重跑 full。

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
| Regression tests | `scripts/verify-stage-regression-tests` | 完整 pytest（含 `large` 標記的 Copier create／existing-adoption／update 保存回歸）＋coverage 門檻，以及 Issue-triage／worktree-cleanup／PR-policy／base-only-remerge／gh-issue-create／check-branch-fresh／PR-policy-status／audit-fleet-adoption／`verify-template.sh` 聚合自我測試 | fast 只跑 `pytest -m "not large"`（略過 `large`），且只在 governance／template／workflow／shell scope 才跑 Issue-triage／worktree-cleanup／PR-policy 三個 shell 自我測試；base-only-remerge、`scripts/gh-issue-create`（開 Issue 前本機先擋不合規標題，見 AGENTS.md 工作迴圈）、`scripts/check-branch-fresh`（開工前本機核對既有分支是否仍等於 `origin/<branch>`，見 AGENTS.md 工作迴圈）、PR-policy-status 與 `scripts/audit-fleet-adoption`（本機即時查詢 fleet 採用門檻、只印 stdout，見 #521）五支本機專用工具的自我測試都只在這個 full 專屬階段跑，不進 `verify-fast`（分別見上方 Base-only re-merge 例外一節與下方 PR policy 逐 step 判讀一節）；`large` 覆蓋範圍只在 full 執行，是 Copier create／adopt／update 保存的唯一 regression source，未被任何字串比對或重複 profile 執行取代 |
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

本機在不同 worktree 重跑驗證時，可把 `CSARC_CACHE_ROOT` 設為同一個絕對路徑；`uv`、
`pnpm` 與固定版本工具會共用已驗證的下載內容並依版本與平台分隔。`.venv`、
`node_modules`、生成 fixture、checkout 與測試結果仍逐 worktree 隔離，快取命中不代表
測試通過；損壞內容依固定 checksum 重新下載或失敗。例如：

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

2026-09-03 的實際事故（#587）證明「發版」目前完全綁在 `release.yml` 這一支 workflow 是否能在 GitHub Actions 上成功執行：M8 promotion 後，`docs/index.html` 過期讓 full-tier 驗證卡住，`main` 上每一次 push 觸發的 `release.yml` run 全部失敗，加上同一天稍早出現的 `pull_request` webhook 投遞間歇性異常，讓「能不能發版」完全停擺超過 8 小時、沒有人自動被通知，直到人工檢查 Releases 頁面才發現。既有的「Actions 額度 fallback」（見 [staged-delivery-and-verification ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/staged-delivery-and-verification.md)）解決的是不同的觸發條件：額度用盡有 GitHub 回傳的明確錯誤訊息（zero-step billing block），可以機械式偵測；本節處理的觸發條件——hosted runner 卡住、webhook 沒有投遞、或其他導致 Actions 本身不健康的狀況——**沒有對應的機械式訊號**：它看起來就是「什麼都沒發生」，而「什麼都沒發生」本來就有可能只是因為沒有東西需要發版。這個不對稱是本節 fallback 刻意設計成「人或 agent 主動決定啟用」而非自動觸發的原因，也是為什麼另外需要一道獨立排程的存量檢查——這道檢查因範圍與時間考量從 #589 拆分為獨立追蹤：見 [#605](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/605)。

**設計：** Guided 模式（[版本／交付 ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/release-security-and-dependencies.md) 決策）原本只在「組織政策禁止 Actions 建立 PR」時啟用；本節把同一條路徑的啟用條件擴大為「維護者或 agent 判斷 Actions／webhook 目前不可信任」時同樣可以啟用，機制不變：`python3 scripts/release_policy.py prepare-candidate` 在本機計算版本與 CHANGELOG，人或 agent 開一般 PR，經過與其他 `main` PR 相同的 review 才能合併——本機執行不能成為省略審查的手段。合併後的發布步驟（建 tag、draft Release、build 成品、checksum、SPDX SBOM、`gh release` 系列指令）改抽成 `scripts/publish-release`，`release.yml` 與本機路徑呼叫同一份實作，不維持兩套邏輯。

**代價（不能只講好處）：**

- **放棄 hosted runner 的乾淨、一致環境保證。** 本機執行的環境不由 GitHub 控管；只有本機 `full` 驗證全綠才能視為等同 hosted 的證明強度。
- **需要本機或執行者持有具備 admin／write 權限的長效憑證，而不是 Actions 短效 `GITHUB_TOKEN`。** 這不是為所有 CSARC-owned repo 新增一項標準要求——`scripts/apply-repository-settings.sh apply` 本來就已經要求 repo admin 用自己的 `gh` 身分執行；本節只是讓同一位已經持有這個權限的維護者，多一個「用同一身分完成發版」的選項。
- **沒有 merge 後自動觸發，需要人或排程主動執行。** 需要另外一道獨立排程的存量檢查偵測「`main` 已經前進但過去 N 小時內沒有成功的 `release.yml` run 或本機發版紀錄」，取代目前完全仰賴人工檢查 Releases 頁面才會發現的狀態；這道檢查追蹤於 [#605](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/605)，尚未落地。
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
