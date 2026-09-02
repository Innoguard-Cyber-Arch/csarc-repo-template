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

工作 PR 關閉單項工作；Milestone 交付負責批次進入 `main`、結案與 delivery branch
清理。#400 與 #401 的自動結案契約仍是 blocked gap，因此現在由維護者人工確認，不由
版本或發版流程重複處理。

## PR lifecycle single-writer

Agent 或 automation 若要變更 PR 的 ready／draft、授權或 metadata，必須先取得 remote
lease，並透過 `scripts/pr_lifecycle.py` 執行；`scripts/verify` 會拒絕另一套重複寫入者。
人工在 GitHub 上審查與合併不受這個工具限制。

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
| Version／Release | `.github/workflows/release.yml` | #369／#430 | `main` push（post-merge）、manual rerun | top-level read；單一 release job 才有 `contents`／PR／Issue／status write；30 分鐘 | Automatic 或 Guided 版本 PR；合併後由同一 workflow 發布 tag／GitHub Release／成品／checksum／SBOM | `tests/test_release_policy.py`、`tests/test_release_bundle.py`、`tests/test_journey07_release.py` | 尚未落地 `main`，無 tag／Release live run；候選僅由本表 CI／PR policy 兩筆 run 驗證檔案與規則本身 | candidate／blocked，待 default branch 首次 live run |

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

`scripts/ci_tier.py` 依事件、base／head、labels 與 changed paths 做 fail-closed 分類；
未知或高風險內容升級為 full。數據來自 #428／PR #431 在 2026-09-01 的最新 hosted
run，目的是設定成本預期，不是永久 SLA。

| 分級 | 適用範圍 | 入口與測試集合 | #428 實測 |
| --- | --- | --- | --- |
| docs | 純文件與 site 內容 | `scripts/verify-fast`；來源檢查、render、雙語／glossary／llms 契約 | 與 fast 共用 bounded path |
| fast | 一般工作 PR；依 scope 加 policy／template 檢查 | `scripts/verify-fast`；source fast 約 59 秒，policy／template scope 約 99 秒 | 約 1–4 分鐘的 PR feedback window |
| full | Milestone／canary 交付、hotfix、merge queue、manual、未知高風險路徑 | 中央模板用 `scripts/verify-template.sh`；生成 repo 用 `scripts/verify full` | 中央模板 verification 330 秒；整個 job 6 分 16 秒 |

相依 manifest／lockfile 變更加跑 `scripts/verify-dependencies`。CI 不建立 release asset，
也不把測試 artifact 當成正式成品。#408 已把更細的 stage timing 輸出納入現行入口。

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
