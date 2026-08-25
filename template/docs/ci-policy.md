# 分層 CI 政策

CI 是沒有獨立測試環境時的可攜式 integration layer；外部環境與 canary
則在 promotion 階段補充端到端證據。分支策略與 workflow 分層必須一起使用：
只把 PR 改送 `dev/*`，但仍讓每張 PR 跑完整矩陣，不會降低使用量。

## 分支與驗證邊界

- Milestone 內的 Issue 從 `dev/m<編號>-<簡稱>` 分支工作；每張 Issue 仍有自己的
  `type/<Issue 編號>-<簡稱>` 分支與 PR。
- 沒有 Milestone 的一般孤立 Issue 進入 `dev/next`，等待下一次批次 promotion。
  若一張孤立 Issue 確實要獨立 soak／canary，才使用一次性的
  `dev/i<Issue 編號>-<簡稱>`；同號 Issue 不掛 Milestone、加上 `promotion` label，
  並由該 branch 的 promotion PR 關閉。完成後刪除 branch。
- `dev/* → main` 的 promotion，以及標示 `hotfix` 的緊急修正，必須跑 full tier。
- `main` 更新後，尚在進行的 delivery branch 先透過受審查的 `sync/main-to-*` PR
  納入新結果，再接受新的 Issue PR 或 promotion。

### 孤立 Issue 決策樹

```text
這張 Issue 屬於可端到端驗收的 Milestone 嗎？
├─ 是 → type/<issue>-* PR → dev/m<milestone>-*
└─ 否
   ├─ 能等待固定 release window 嗎？
   │  └─ 是 → type/<issue>-* PR → dev/next → 批次 promotion
   └─ 有文件化的獨立 soak／canary 需求嗎？
      ├─ 是 → dev/i<issue>-* → 單獨 promotion → 刪除暫時 branch
      └─ 否
         ├─ 是需要立即修復正式環境的緊急缺陷嗎？
         │  └─ 是 → standalone fix/* + hotfix label → main
         └─ 否 → 回到 dev/next，不建立假 Milestone 或永久 branch
```

`dev/i*` 不是讓普通 Issue 規避批次的捷徑；Issue 必須寫出為什麼不能與
`dev/next` 一起驗證、canary 目標與停止條件。Hotfix 也不是快速通道：它仍跑 full
tier、保留 promotion evidence 並立即形成 release 邊界。

## 四層執行契約

| 層次 | 事件 | 執行內容 | Required／取消規則 | 成本目的 |
| --- | --- | --- | --- | --- |
| Policy | 每張 PR | 同一個 runner 檢查 PR 標題／Issue 關聯、branch route、delivery sync 與 review policy | `title`、`promotion` 與 `verify` 都會產生；新 commit 可取消舊的一般 PR run | 先用便宜、確定性的規則拒絕錯誤流程 |
| Docs／fast | 純文件或一般 Issue／sync PR | secret scan、格式、lint、型別、單元與 policy tests；workflow／shell scope 加跑 actionlint／ShellCheck，模板範圍另做單一預設 profile smoke | 由穩定的 `verify` aggregate 彙總；同 PR 新 commit 取消舊 run | 每次整合保留快速回饋，不支付完整矩陣 |
| Full | promotion、hotfix、merge queue、手動 dispatch、未知高風險路徑 | 所有支援 runtime、profiles、Copier update、release policy、安全與整合回歸 | `verify` 與 `promotion` 必須成功；候選 run 不取消 | 只在交付邊界支付一次完整信心成本 |
| Periodic／release | daily／weekly schedule 或已驗證的發布邊界 | OSV、Zizmor、governance drift、artifact、digest、SBOM、provenance | 排程不阻塞普通 PR；發布只接受 release-source evidence，重跑採 idempotent | 把時間性風險與成品工作移出每個 commit |

Full tier 將 runtime 無關的 lint、文件、治理、profile、Copier create／adopt／update、
package metadata 與完整成品檢查集中在最新 Python 的 `canonical full` 一次執行。
Python compatibility jobs 只做 locked install 與 runtime-sensitive tests：精確最低版
`.0` 一定保留，從最低支援版到 3.14 的每個 feature release 也都保留；最新 3.14
由 canonical 覆蓋，其餘 runtime 不再重跑相同的完整 suite。混合 profile 的
TypeScript install、test、coverage、build 與 pack 另在單一 Node 24 job 執行，canonical
透過既有 `CSARC_VERIFY_TYPESCRIPT=false` 避免重複。TypeScript-only 仍由單一 canonical
Node job 完整驗證，Python-only 則不啟動 Node job。

`scripts/ci_tier.py` 依事件、base／head、labels 與 changed paths 做 fail-closed
分類。`site/**`、根目錄 Issue forms 與一般 Markdown 明確歸入 docs tier，根目錄
`.gitignore` 歸入 fast；workflow 變更加跑 Zizmor，相依 manifest／lockfile 加跑
OSV，治理宣告或 checker 加跑 remote governance。release／version 等未分類高風險
路徑仍升級為 full，不會只為省 runner 而直接放行。Portable decision site 的 render
check 在 fast job 內固定執行；只有 site 來源、相關 project docs、手動驗證或 promotion
才上傳 artifact。

## `main` 回同步到進行中的 delivery branch

`main` 每次前進後，delivery-sync workflow 會列舉 `dev/next`、所有
`dev/m*`，以及仍存在的 `dev/i*`。每條 branch 的 Issue／Milestone owner 對同步
負責；不是由 hotfix 作者直接改寫其他團隊的 branch。同步必須在接受下一張 Issue PR
或建立 promotion PR 前完成，避免較舊候選版本把已進入 `main` 的修正帶掉。

預設採手動、可審查流程：

```bash
git fetch origin main <delivery-branch>
git switch -c sync/main-to-<delivery>-<main-sha> origin/<delivery-branch>
git merge --no-ff origin/main
git push -u origin sync/main-to-<delivery>-<main-sha>
gh pr create --base <delivery-branch> --head sync/main-to-<delivery>-<main-sha>
```

Sync PR 使用 repository 允許的 merge method；squash-only repository 直接以一般
squash merge 合併，不需暫時開啟 merge commits 或使用 admin override。PR policy
優先接受 proposed head 對當前 `main` 的直接 ancestry；若 squash 使 ancestry 不再保留，
則透過 GitHub REST 核對 deterministic sync branch 對應的 PR 已合併至正確 delivery
branch、該 PR head 確實包含完整的當前 main SHA，且 PR 的 `merge_commit_sha` 已包含在
proposed head。任一 API 查詢失敗、main 已前進、PR 未合併、base 不符、sync head 未含
該 main SHA，或 proposed head 未含該 squash commit 時都 fail closed；branch 名稱與
commit message 本身不算證據。

若發生 conflict，owner 在 `sync/*` branch 解決、說明取捨並重新跑受影響 checks；
不得直接 push、force-push 或在 delivery branch 上解 conflict。若
`CSARC_AUTO_SYNC=true`、`CSARC_SYNC_TOKEN` 可觸發後續 PR checks，且 branch／PR
write probes 都是 `allowed`，workflow 才能自動建立相同 PR。任何能力為 `blocked`
或 `unknown` 都只輸出上述手動指令，不猜測權限、不把未同步視為成功。
main push 的 reconcile 只對過期 PR 的合併後 `title` policy context 寫入 failure，
不寫 success；同步後的新 SHA 必須重新通過完整 PR policy，不能用 status 繞過標題、
Issue 關聯或 branch route。

## Required checks 與 concurrency

Ruleset 固定要求 `title`、`promotion` 與 `verify`；delivery sync 已併入 `title`，
不再留下獨立 required context。穩定的 `verify` aggregate context
每次都建立，並彙總 fast、full、OSV、Zizmor 與 remote governance 的
`success`／`skipped` 結果；因此不適用的重型 job 不會因 workflow-level path filter
留下永久 Pending。

一般 PR 的新 commit 會取消同一 PR 的舊 run。Promotion、hotfix、release 與手動
full run 不取消進行中的驗證，避免候選版本遺失完整證據。CI 不再對合併後的同一
source tree 跑第二次完整 suite；`main` push 留給同步與 release 邊界工作。

## Promotion 與 canary 證據

Ruleset 另固定要求 `promotion` context。一般 Issue／sync PR 會得到明確的
not-applicable 成功結果；`dev/m* → main`、`dev/next → main`、`dev/i* → main` 與
hotfix 則必須先確認 branch 包含最新 `main`。Milestone promotion 還會檢查同一
Milestone 中，除 promotion Issue 外的工作均已關閉且沒有未勾選的 acceptance
criterion。`dev/i<編號>-*` 則核對同號、無 Milestone 且標示 `promotion` 的 open
Issue，不能借用別張 Issue 或偽裝 Milestone。

Promotion 會封裝候選 source archive，記錄 PR、base/head SHA、candidate tree、
Milestone 與納入 Issues，並把完整 CI 的 `verify` 當成並列 required gate。合併後
不重跑完整矩陣，而是下載該 PR 的 evidence、核對 `verify` 成功，並確認 `main`
tree 與候選 tree 相同；任一不符都停止後續 release。

外部 canary 採明確三態：

- 同時設定 repository variable `CSARC_CANARY_COMMAND` 與
  `CSARC_CANARY_ENVIRONMENT` 時為 `allowed`，候選 archive 會進入指定 GitHub
  Environment 執行 smoke；敏感值只透過 environment secret
  `CSARC_CANARY_TOKEN` 提供。
- 兩者都未設定時為 `blocked`，只保留 artifact-only evidence，不能宣稱已完成
  外部測試。
- 只設定其中一項時為 `unknown`，同樣只保留 artifact-only evidence，並要求維護者
  修正設定。這兩種 fallback 都不取代 full CI。

Promotion Issue 會維持 open；只有 gate 通過且 PR 真正合併到 `main` 後，GitHub
closing keyword 才關閉它。既有 Milestone lifecycle 會在所有 Issue 關閉且
Milestone acceptance criteria 全部勾選時關閉 Milestone，之後若 Issue reopen 或
criterion 取消勾選則重新開啟。

### Promotion checklist 與證據保留

Promotion owner 在請求合併前逐項確認：

- tracking Issue 仍 open，PR 以 closing keyword 指向它，所有 acceptance checkbox
  已完成；Milestone route 的其他工作 Issue 全部關閉。
- delivery head 包含目前 `main`；候選 source、base/head SHA 與 Git tree 已封存。
- full `verify` 與 `promotion` context 成功；或符合下方 quota-only promotion fallback，
  且其精確 SHA/tree 證據與人工授權完整。納入 PR 清單與最高 SemVer intent 必須相符。
- canary 為 `allowed` 且成功，或誠實記為 `blocked`／`unknown` artifact-only；後兩者
  不得在 release note 宣稱外部環境驗證成功。
- reviewer 知道 rollback 是 revert promotion PR／發布修正版，而不是重寫歷史。

合併後，release-source 再核對 `main` tree identity 和原本的成功 run。Promotion
evidence、release-source evidence 與 CI plan artifact 保留 90 天；GitHub PR、Issue、
Milestone、workflow URL、commit 與 tag 是長期索引。證據核對成功後才讓 closing
keyword 關閉 promotion Issue；Milestone lifecycle 再依 acceptance criteria 關閉
Milestone。若任一核對失敗，保持 Issue／Milestone open、停止 release 並另開修正
Issue，不回填假成功。`dev/i*` 只有在上述核對與 source handoff 成功後才刪除遠端
branch。

## 批次發版邊界

發版以 promotion 為單位，而不是以每張 Issue PR 為單位：Milestone 僅在完成時
promotion 一次；`dev/next` 建議由團隊固定每週一個 release window 批次 promotion，
沒有 release-worthy 變更時直接略過；`dev/i*` 在其獨立 canary 完成後單獨
promotion；hotfix 才是立即 promotion／release。若下一個 release PR 合併前又有
promotion，Release Please 更新同一張 PR，最後仍只建立一個 tag 與 GitHub Release。

Promotion evidence 會列出 delivery range 中實際合併的 PR、標題與各自的
major／minor／patch／no-release intent。Promotion PR 標題必須宣告其中最高等級，
使 squash commit 與整批內容一致；若全部只有 `docs`、`ci`、`chore` 等 no-release
變更，release jobs 會略過並留下原因，不建立空版本。

`main` push 的 release-source job 會再次核對每個 promotion 的 full `verify`、
canary 狀態與 tree identity，並把 delivery branch、Milestone／standalone batch／
isolated route、promotion PR、main SHA、evidence run、Issues 與納入 PR 彙整成 90 天
artifact 和 workflow summary。無關聯 PR、非 promotion／hotfix 或證據不符的 commit
只會得到 verification-only 結果，不能進入 capability detection 或發布。

Artifact workflow 不監聽任意 `v*` push，只接受 Release Please workflow 帶入
source run ID 的明確 dispatch。它先驗證 tag commit 與 release-source evidence，
再建置 distributions、digest、SBOM、attestation 與 registry／immutable Release
驗證；不重跑已由 promotion 通過的完整 runtime／template 測試矩陣。相同 source
的重跑會沿用既有 tag、draft Release 或成功 artifact run，不重複發布。

## Maintainer walkthrough

### 兩個 Milestone 同時進行

Milestone 7 的 Issues 各自由 `type/*` PR 進 `dev/m7-delivery`，Milestone 8 同理進
`dev/m8-auth`；普通 PR 都跑 fast。Milestone 7 先完成時，owner 先同步最新 `main`，
以 promotion PR 跑 full 與 canary，合併後形成一個 release 邊界。`main` 前進後，
Milestone 8 owner 透過 `sync/main-to-m8-auth-<sha>` PR 納入結果；Milestone 8 不需
重建 branch，也不能在未同步時繼續合併 Issue PR。兩條 delivery branch 可以平行，
但不互相 merge；共同結果只透過 `main` 回流。

### 孤立 Issue

一般文件、維護或小功能 Issue 由 `type/<issue>-*` PR 進 `dev/next`，在每週 release
window 與其他孤立工作一起 promotion。若 Issue #42 需要自己的外部 canary，Issue
先記錄理由與停止條件，再建立 `dev/i42-canary`、加 `promotion` label，直接以這條
branch 工作；full/canary 通過並 promotion 到 `main` 後刪除它。不能只因不想等待
`dev/next` 就建立 `dev/i*`，也不能為單一 Issue 建立內容空洞的 Milestone。

### 緊急 hotfix

正式環境的緊急缺陷由 standalone `fix/<issue>-*`、`hotfix` label 直接對 `main` 開
PR。它仍需 tracking Issue、人工審查、full `verify`、promotion evidence 和 tree
identity；合併後立即形成 patch release 邊界。接著由每條進行中的 `dev/m*`、
`dev/next` 與 `dev/i*` owner 各自建立 reviewed sync PR，把 hotfix 帶回去。

## 導入、回復與降級

- **既有 main-only：**不改寫歷史、不回填舊 PR。先合併 policy/workflow，再從目前
  `main` 建立 `dev/next`；新的 Milestone 才建立 `dev/m*`，open PR 在可安全 rebase
  或 retarget 時逐張遷移。第一個 promotion 前先完成一次手動 dry run 與 full gate。
- **既有單一 `dev`：**不把進行中工作硬拆成多條歷史。完成或凍結當前 `dev` 候選後，
  由目前 `main` 建 `dev/next`，新 Milestone 使用 `dev/m*`；舊 `dev` 維持唯讀到候選
  結束再刪除。
- **回復 policy：**若 staged delivery 本身需要撤回，以正常 PR 把新 work 暫時改回
  main-only 或單一 `dev` 設定；保留已產生的 evidence 與 branch，不 rewrite／force
  push。已發布錯誤使用 revert/fix promotion 和新版本處理，絕不移動既有 tag。
- **能力降級：**Ruleset 無法強制時標為 `DEGRADED`，仍產生可見 checks 供人工遵守；
  sync 寫入能力 blocked／unknown 時改走上述手動 PR；canary blocked／unknown 時只
  能宣告 artifact-only；release 權限不足時停在 verification-only。任何降級都不
  會把 full failure、未知權限或未啟動 runner 當成功。

## 安全掃描與治理頻率

- Gitleaks 留在每張 PR 的 docs／fast／full 路徑。
- actionlint 與 ShellCheck 在 workflow／shell 相關變更、full tier，以及既有每週
  workflow audit 排程執行；兩者固定版本並驗證下載 checksum。
- OSV 在相依或供應鏈設定變更、full tier，以及每週排程執行。
- Zizmor 在 workflow／action 相關變更、full tier，以及每週排程執行。
- Remote governance 在治理宣告／checker 變更、full tier，以及既有 daily drift
  schedule 執行；reviewer assignment 只在 opened、reopened 或 ready-for-review
  觸發，不在每次 synchronize 重做。

## Actions 額度 fallback

這個一次性流程只適用於具帳務可見性的 human maintainer 已明確確認當期 included
GitHub Actions minutes 耗盡。只提到 failed payments 或 spending limit 的 runner 註記
不足以證明符合條件；付款失敗、錯誤 budget、平台事故、workflow／權限錯誤、原因不明，
或任何已開始執行 step 後失敗的 job 都維持 blocked。

合併前必須確認 worktree 乾淨且 `HEAD` 等於 PR head SHA，執行完整本機驗證與每個可
忠實重現的 required check；任何失敗都停止，GitHub-only checks 則逐項列出。通過後，
在 PR 留下標題為 `Actions quota fallback attestation` 的留言，記錄 head SHA、受阻 run
URL 與 annotation、human quota confirmation、UTC 時間、環境與工具版本、完整命令、
結果及未重現 checks。Human maintainer 必須再針對該 PR 明確授權；新 commit 使聲明
失效並須重新驗證、記錄與授權。不得建立或偽造成功 Check Run。

只有 repo 現行政策已允許 author self-merge 時，agent 才可在上述條件完整後合併。
fallback 不取代 release、publishing、deployment approval、secrets、provenance、
CODEOWNER review 或任何無法本機重現的控制。額度恢復後須補跑該 SHA 的 GitHub
checks 並記錄結果；平台不再允許補跑時，另開 Issue 保留缺口，不得宣稱追溯成功。

### Promotion PR 的額外 fallback 證據

`dev/m*`、`dev/next`、`dev/i*` 或 delivery strategy 的 `dev` promotion 到 `main`
可使用同一個 quota-only 例外；一般 main PR、release follow-up 與 hotfix 不因此新增
快速通道。除前述共同條件外，必須使用既有 `scripts/promotion_gate.py`，依序完成：

1. 在乾淨、精確等於 promotion PR head 的 worktree 執行 `prepare`，且
   `--candidate-sha` 必須是該 head SHA；保存 candidate archive、SHA-256、base/head SHA、
   candidate tree、納入 PR、SemVer intent 與 canary 三態。
2. 執行完整本機驗證與所有可忠實重現的 required checks。若 canary 是 `allowed`，
   fallback 不得替代它；只有 `blocked`／`unknown` 可維持 artifact-only。
3. 先在同一 PR 留下標準 attestation，再由 human maintainer 對相同 head SHA 留下
   明確授權。使用兩則留言 URL、所有 zero-step blocked run URL 與實際驗證命令執行
   `finalize-quota-fallback`，產生 machine-readable evidence。此 evidence 的 gate 是
   `quota-fallback`、`release_eligible` 固定為 `false`；把 JSON 與 archive digest 留在 PR。
4. 僅以非 admin 的 squash merge 合併。更新乾淨的 `main` checkout 後執行
   `verify-quota-main`，確認 main tree 等於已驗證 candidate tree，並把結果留在 PR；
   不符時停止、revert／修正，不重寫歷史。

新 commit、base SHA 漂移、candidate tree 改變、任何非 zero-step 失敗，或 attestation／
authorization 不屬於同一 PR，都會使 fallback 失效。這份本機 evidence 只允許合併，
不會被 hosted `release-source` 接受；在原 promotion 與 main post-merge checks 真正補跑
成功前，不建立、移動或宣稱 tag、Release、package、provenance 或外部 canary 成功。

## 外部基準

下列活躍大型 repository 與 GitHub 官方文件於 2026-08-24 查閱；當日三者約有
90k、142k、116k GitHub stars，皆未 archived 且當天仍有 push。採用的是「依事件／
路徑分流、昂貴檢查集中在整合或發版邊界、維持穩定 required context、候選版本保留
完整證據」等原則，不照抄它們的 branch 名稱；本 repo 的 `dev/m*`、`dev/next` 與
`dev/i*` 是依本團隊工作單與並行交付需求定義。

- [Home Assistant core CI](https://github.com/home-assistant/core/blob/dev/.github/workflows/ci.yaml)
  展示大型矩陣依工作內容與 job 條件切分，而非讓每個步驟無條件執行。
- [Next.js build and test](https://github.com/vercel/next.js/blob/canary/.github/workflows/build_and_test.yml)
  與 [release branch workflow](https://github.com/vercel/next.js/blob/canary/.github/workflows/create_release_branch.yml)
  區分日常整合與發布邊界。
- [Rust CI entry](https://github.com/rust-lang/rust/blob/main/.github/workflows/ci.yml)
  與 [job definitions](https://github.com/rust-lang/rust/blob/main/src/ci/github-actions/jobs.yml)
  將龐大驗證矩陣集中管理，按事件組合工作。
- GitHub 官方的 [workflow branch/path filters](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
  說明事件過濾；required check 可能因整個 workflow 被略過而保持 Pending，因此本案讓
  workflow 建立穩定 aggregate job，再在 job 內把不適用項目標成 skipped。

## 成本與證據

模板 repo 的導入前基線是一般 PR update 約 14 billed Linux runner-minutes。
分層後的一般文件／來源 Issue PR，最多啟動 PR policy、CI fast 與 CI aggregate
三個 runner job；首次 reviewer assignment 再多一個 job。以每個短 job 至少計一分鐘，
14→3／4 job-minute 規劃模型分別估計減少約 79%／71%。這是明確標示的 job-minute 規劃估算，不是 hosted 實測
或實際帳單數字。

Runner 可用且 CI 已啟動時，workflow 會上傳 `ci-plan-<run-id>-<attempt>` artifact，並在
workflow summary 記錄 tier、原因、scopes、條件式檢查與 fast job 秒數。Hosted duration 與 `ci-plan` artifact 僅作
optional telemetry，用來校準規劃模型，不是 Milestone、promotion 或產品
交付的必要驗收條件。任何 zero-step job 都不算 hosted success 或成本測量；額度、付款、
平台或權限問題也不得被記成成功 telemetry。Portable baseline 不要求管理員升級 GitHub
方案、調整帳單、建立 PAT／GitHub App 或維護自架 runner。

[#189](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/189) 與
[#199](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/199) 原本把成功 hosted 量測或恢復視為完成前提；
[#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287) 已以 capability-adaptive telemetry 取代該前提。
Telemetry 可用性不改變本機 full verification、promotion tree evidence、security 或 supply-chain gates。
Promotion 的 quota-only fallback 仍須完整執行同一套本機 full verification，且不能冒充 hosted 成功。
Hosted runner 可用時，full tier 以 `canonical full`、`Python compatibility (<runtime>)` 與
`TypeScript (Node <version>)` 分開留下 job result、duration 與 billed runner telemetry；
`verify` aggregate 依 tier 與 profile 要求所有適用 job 必須 success，
只允許真正不適用的 job skipped，避免漏啟動被誤判成功。
