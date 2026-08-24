# 分層 CI 政策

CI 是沒有獨立測試環境時的可攜式 integration layer；外部環境與 canary
則在 promotion 階段補充端到端證據。分支策略與 workflow 分層必須一起使用：
只把 PR 改送 `dev/*`，但仍讓每張 PR 跑完整矩陣，不會降低使用量。

## 分支與驗證邊界

- Milestone 內的 Issue 從 `dev/m<編號>-<簡稱>` 分支工作；每張 Issue 仍有自己的
  `type/<Issue 編號>-<簡稱>` 分支與 PR。
- 沒有 Milestone 的孤立 Issue 進入 `dev/next`，等待下一次批次 promotion；不為
  每張孤立 Issue 建立另一條永久 dev branch。
- `dev/* → main` 的 promotion，以及標示 `hotfix` 的緊急修正，必須跑 full tier。
- `main` 更新後，尚在進行的 delivery branch 先透過受審查的 `sync/main-to-*` PR
  納入新結果，再接受新的 Issue PR 或 promotion。

## 四層執行契約

| 層次 | 何時執行 | 內容 |
| --- | --- | --- |
| Policy | 每張 PR | PR 標題／Issue 關聯、delivery sync、review policy，以及穩定的 `verify` aggregate context |
| Docs／fast | 文件或一般 Issue PR | secret scan、格式、lint、型別、單元測試、policy tests；模板範圍另產生一個預設 profile smoke |
| Full | promotion、hotfix、merge queue、手動 dispatch、未知高風險路徑 | 所有支援 runtime、profiles、Copier update、release policy、安全與整合回歸 |
| Periodic／release | 週期排程或發布邊界 | OSV、Zizmor、governance drift、artifact／provenance；不在每個普通 commit 重跑 |

`scripts/ci_tier.py` 依事件、base／head、labels 與 changed paths 做 fail-closed
分類。純 `docs/` 或 Markdown 只跑 docs tier；workflow 變更加跑 Zizmor，相依
manifest／lockfile 加跑 OSV，治理宣告或 checker 加跑 remote governance；無法分類
的路徑升級為 full，不會以檔名判斷後直接放行。

## Required checks 與 concurrency

Ruleset 固定要求 `title`、`delivery-sync` 與 `verify`。`verify` 每次都建立，並彙總
fast、full、OSV、Zizmor 與 remote governance 的 `success`／`skipped` 結果；因此
不適用的重型 job 不會因 workflow-level path filter 留下永久 Pending。

一般 PR 的新 commit 會取消同一 PR 的舊 run。Promotion、hotfix、release 與手動
full run 不取消進行中的驗證，避免候選版本遺失完整證據。CI 不再對合併後的同一
source tree 跑第二次完整 suite；`main` push 留給同步與 release 邊界工作。

## 安全掃描與治理頻率

- Gitleaks 留在每張 PR 的 docs／fast／full 路徑。
- OSV 在相依或供應鏈設定變更、full tier，以及每週排程執行。
- Zizmor 在 workflow／action 相關變更、full tier，以及每週排程執行。
- Remote governance 在治理宣告／checker 變更、full tier，以及既有 daily drift
  schedule 執行；reviewer assignment 只在 opened、reopened 或 ready-for-review
  觸發，不在每次 synchronize 重做。

## 成本與證據

模板 repo 的導入前基線是一般 PR update 約 14 billed Linux runner-minutes。
分層後的一般 Issue PR 預期啟動 CI fast、CI aggregate、PR policy 與 delivery sync
四個 job，估計 4 billed minutes，即約減少 71%；PR 首次開啟另有一次 reviewer
assignment。這是 job-minute 模型估計，不是實際帳單數字。

每次 CI 都會上傳 `ci-plan-<run-id>-<attempt>` artifact，並在 workflow summary
記錄 tier、原因、scopes、條件式檢查與 fast job 秒數。Actions 可正常啟動後，應以
一般 Issue PR 的實際 run/job duration 驗證至少 70% 降幅，營運驗收由
[#189](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/189) 追蹤；
額度、付款或平台問題不得被記成成功測量，也不得用來跳過 promotion 的 full gate。
