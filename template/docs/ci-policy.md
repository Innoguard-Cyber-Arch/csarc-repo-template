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
repository delivery，不會自動建立新版本或 Release。

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
4. `fix` 預設只表達 patch 意圖；破壞相容性時明列 `!`。精確版本、tag 與 Release 仍由
   唯一 release owner 另行核准，不能把 hotfix 合併冒充已發版。

## Active automation

| 能力 | 事件 | Repo-local 入口 | 權限／timeout | 產物與狀態 |
| --- | --- | --- | --- | --- |
| CI | `pull_request`、`merge_group`、`workflow_dispatch` | `scripts/ci_tier.py`，再呼叫 `scripts/verify-fast` 或 `scripts/verify-template.sh` | `contents: read`；30 分鐘；同一 PR 新 commit 取消舊 run | `verify` check、step summary；active |
| PR policy | PR metadata 事件 | `scripts/validate-pr-policy` 與本機 regression | 只給需要的 Issue／PR metadata 權限；固定 timeout | title、Issue、route 與 review policy；active |
| Dependency vulnerability | weekly、manual、相關變更 | `scripts/verify-dependencies` | `contents: read`；固定 timeout | OSV 結果；active，邏輯由依賴安全擁有 |
| Issue triage | Issue 事件 | workflow 內的 bounded routing | 最小 Issue metadata write | label／milestone routing；active |
| Spec to Issue | spec 事件／manual | checked-in spec conversion entrypoint | 最小 Issue metadata write | 可審查 Issue；active |
| Milestone lifecycle | milestone／Issue 事件 | 現行 workflow | 最小 metadata write | 部分自動化；完整結案仍由 #400 擁有 |
| Dependabot | schedule／manifest | `.github/dependabot.yml` | GitHub 原生 bot 邊界 | dependency PR；active |

所有第三方 Actions 鎖定完整 commit SHA，旁註可讀 release tag。Workflow YAML 只負責
event、權限、環境與呼叫；分類與驗證規則留在本機可測的 scripts。Repository 預設
`GITHUB_TOKEN` 為 read-only，Actions 不可自行核准 PR。

## 驗證分級與實測成本

`scripts/ci_tier.py` 依事件、base／head、labels 與 changed paths 做 fail-closed 分類；
未知或高風險內容升級為 full。數據來自 #428／PR #431 在 2026-09-01 的最新 hosted
run，目的是設定成本預期，不是永久 SLA。

| 分級 | 適用範圍 | 入口與測試集合 | #428 實測 |
| --- | --- | --- | --- |
| docs | 純文件與 site 內容 | `scripts/verify-fast`；來源檢查、render、雙語／glossary／llms 契約 | 與 fast 共用 bounded path |
| fast | 一般工作 PR；依 scope 加 policy／template 檢查 | `scripts/verify-fast`；source fast 約 59 秒，policy／template scope 約 99 秒 | 約 1–4 分鐘的 PR feedback window |
| full | Milestone／canary 交付、hotfix、merge queue、manual、未知高風險路徑 | `scripts/verify-template.sh`；完整 profiles、Copier create／adopt／update、runtime 與安全回歸 | verification 330 秒；整個 job 6 分 16 秒 |

相依 manifest／lockfile 變更加跑 `scripts/verify-dependencies`。CI 不建立 release asset，
也不把測試 artifact 當成正式成品。#408 已把更細的 stage timing 輸出納入現行入口。

## 版本、發版、交付與部署矩陣

| 邊界 | Issue／工作 PR | Milestone／canary 交付 PR | `main` | tag／manual event |
| --- | --- | --- | --- | --- |
| 版本意圖 | PR title 表達 major／minor／patch／no-release | 彙整已核准意圖，不自行配置版本 | 保留已審查內容 | 不從 tag 反推或改寫 source |
| 正式版本與 CHANGELOG | 一般工作不直接決定精確版本 | 若本批確實發版，以單一人工 PR 同步全部版本來源與 CHANGELOG | 合併只代表 repository delivery | 目前沒有自動 materialization |
| CI | docs／fast／full 依風險 | 一律 full | 不重跑同一 source tree 的第二套 release suite | manual dispatch 一律 full |
| 成品／checksum／SBOM | 不發布 | 不發布 | 不發布 | repo-local builder 只屬 conditional contract，沒有 active workflow |
| tag／GitHub Release／attestation | 不建立 | 不建立 | 不建立 | blocked by #369；無 current writer 或成功 run |
| deployment | 不適用 | 不適用 | 不適用 | 由有真實 runtime target 的產品 repo 定義 |

合併到 `main` 是 repository delivery，不等於 Release。精確版本、CHANGELOG、tag、成品與
GitHub Release 必須有唯一 owner；#369 定稿前保持 manual／blocked。生成或既有產品的
release workflow 屬 product owner，Copier 不依檔名猜測、不重複 dispatch，也不要求
GitHub App、PAT、registry token 或空 deployment environment。

## Conditional 與退役能力

`scripts/release_assets.py`、`scripts/verify_release_consumption.py` 與其測試保留為
conditional 的 repo-local 安全契約。只有真實產品 owner 接上明確成品與核准 workflow
後，checksum、SPDX SBOM、attestation 或 consumption 才能成為交付證據。

Release Please、artifact handoff、release consumption、promotion、delivery maintenance、
release follow-up 與 live integration 專用 workflow 目前都不在 active `.github/workflows/`，
且 #430 判定不恢復後已移除 archived YAML。需要重建時必須逐支重新確認 owner、最小權限、
timeout、concurrency、冪等／fail-closed、成本與目前候選上的正反向 live evidence；不得從
Git history 整批復活。Zizmor 與 remote-governance 的舊 workflow 由各自 Journey 另行決定。

## Failure 與 fallback

- 分類器無法判斷時升級 full，不以 skipped 或 zero-step 當成功證據。
- Hosted Actions 不可用時，維護者執行相同 repo-local 入口並附上 commit、命令與結果；
  required check 仍不得被繞過。
- Milestone delivery branch 只在 final delivery 前同步當時最新 `main`；只有明列真實相依
  才提前同步，不對所有 branch fan-out。
- 合併後自動刪除一般來源 branch；Milestone／canary branch 等人工確認結案與 evidence 後
  刪除。`scripts/cleanup-worktrees --apply` 只清除乾淨、未鎖定且可證明已合併的本機 worktree。
- 沒有真實成品、owner、權限或 live run 時，狀態保持 manual、conditional、blocked 或
  not applicable，不以歷史成功補足。
