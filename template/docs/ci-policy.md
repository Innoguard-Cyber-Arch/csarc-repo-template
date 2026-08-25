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
- `dev/* → main` 的 promotion、下述一次性 `promote/m* → main` bridge，以及標示
  `hotfix` 的緊急修正，必須跑 full tier。
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

### 單一 Issue path preflight

開始或接手工作，以及 GitHub 上的 Issue、PR、branch、review 或 checks 改變後，重跑
同一個唯讀入口：

```bash
./scripts/issue_path_status.py --issue <issue-number>
```

入口只使用 GitHub GET API 與 repo 內的 branch strategy 宣告，不會建立 branch、留言、
切換 Draft／Ready、偽造 check 或合併。JSON 固定回報 durable `state`、`guard`、推導出的
`route`／`risk`、repository `capability`、允許動作、必要與已觀察 evidence，以及唯一
`next_step`。有 Milestone 的 Issue 選唯一 `dev/m*`，standalone 選 `dev/next`；明確
`hotfix` 或 `promotion` 才能進 `main`。生成專案從 `.csarc/profile.json` 讀取
`branch_strategy`，中央模板 repo 則使用其已知的 delivery 模式；repository identity
預設從 GitHub origin 讀取，只有非標準本機 remote 才需另傳 `--repo`。
`guard=clear` 回傳 0、`guard=blocked` 回傳 1；GitHub／輸入讀取失敗回傳 2。

同號的多張 open PR／多條 remote work branch、必要 branch 缺少、非本 repo head、
非 promotion PR head 未符合 `<type>/<issue-number>-*`（hotfix 必須是 `fix/<issue-number>-*`）、
base ancestry 或 head ref 漂移、未勾選 acceptance、較新的 blocker、required check
失敗，以及 single-writer lifecycle interface 為 `blocked` 時，`guard` 都是 `blocked`，
且不會列出 merge 動作；Ruleset 為 `unknown` 時一般 merge 也維持 blocked，只有下述
完整驗證的 routine quota 例外可使用獨立驗證為 `available` 的 lease。Elevated、promotion 與 hotfix 還必須
有綁定目前 head、非作者本人、非 bot 的 maintainer approval。Draft 必須填完 Scope、
Completed verification、Pending verification、Known risks 與 Dependencies / non-parallel
work；未完成時使用 `Refs`，不可用 closing keyword。Stacked PR 必須有唯一鏈回 integration
branch；merged 狀態還會驗證該鏈及 terminal merge commit 確實包含在 live integration
ref，不能只憑 `merged_at` 宣稱 Integrated／Delivered。這個入口只指出下一步；真正的
metadata／merge mutation 仍由 lifecycle lease holder 或政策允許的 human maintainer
執行。

入口只接受 target branch 上宣告
`csarc-pr-lifecycle-lease-status/v1` 的 canonical lifecycle helper。它組合該 helper 的
GET-only `lease-status` 與 effective Ruleset：approval、stale-review、last-push、thread
resolution、required checks 或 no-bypass 任一無法證明即為 `blocked`／`unknown`。
GitHub Contents API 回傳的 base blob 必須能重算出同一 Git object SHA，且 bytes 與入口
實際 import 的本機 helper 完全相同；Issue branch 只保留 marker 卻改寫 helper 不會取得
capability。
`available` 只代表兩個 remote lease refs 都可由後續 atomic acquire 嘗試取得，不代表已
持有 lease；`held` 代表其他 status caller 只能唯讀。入口只會把 acquire 列為下一步，
實際 merge 仍由持有 raw capability 的 lifecycle owner 重新驗證授權與 live state。

Routine PR 若所有 live failed runs 都由 `promotion_gate.py` 證明為 exact-head zero-step
billing block，入口會列出既有 `note-quota-fallback` 命令。它只接受一則 repo、PR、
SHA、完整 run URL 集合與本機驗證結果都相符的 canonical note；note 有效、capability
不是明確 `blocked`，且 canonical lease 為 `available` 後才列出 lease／`merge-quota`。
Ruleset 可驗為 enforced 時 capability 為 `allowed`；Private Free API 回 403 而成為
`unknown` 時，也只允許這個獨立重驗所有 evidence 的 quota-only 入口。Elevated、promotion、hotfix 或任何
非 quota failure 不得走這條路；promotion／hotfix 的 zero-step 狀態只會導向既有雙方
attestation／authorization 流程。

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

## Draft ownership 與 Ready 邊界

開始實作前先查 open Draft PR、remote branch 與既有 worktree。沒有既有 owner 時，
在最小解法可說明且相關 targeted checks 通過後即可 push 並開 Draft PR；Draft 使用
`Refs #N`，並列出 scope、已完成與待完成驗證、已知風險，以及依賴或不可平行工作。
若使用 closing keyword，即使仍是 Draft，也必須先完成 PR 與 Issue 的所有項目。

Draft 的 change-aware CI plan 明確記為 `review_state=draft`，只跑 docs／fast tier 與變更範圍要求的
OSV、Zizmor、remote governance。Draft 的 `verify` 成功只表示這些 WIP checks 通過，
不得寫成 full verification 或可合併證據。`ready_for_review` 與
`converted_to_draft` 都會重新觸發 PR policy 與 CI；Ready plan 不套用 Draft 限制，
維持原有高風險 full 分類。

轉 Ready 或更新 Ready PR 前，必須在目前內容上通過完整本機 verifier，將 `Refs`
改成 closing keyword，並完成 PR 與 Issue checklist。任一條件缺少就 fail closed；
轉回 Draft 後可再次以 targeted checks 協作，但下一次 Ready 前仍須重新確認完整驗證。

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
squash merge 合併，不需暫時開啟 merge commits 或使用 admin override。PR policy 與
promotion preflight 優先接受 proposed head 對當前 `main` 的直接 ancestry；若 squash
使 ancestry 不再保留，
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

Promotion 的 squash fallback 使用與 PR policy 相同的 REST 證據鏈，並綁定 promotion
PR 的 base SHA 等於當前 `main`、head ref 等於正確 delivery branch，以及該 branch
包含已驗證的 sync squash commit；採用的 `direct-ancestry` 或 `squash-sync-pr-N` 會寫入
preflight evidence。Hotfix 不適用此 fallback，仍須直接包含當前 `main`。

若 reviewed squash sync 已讓 source delivery tree 包含 current main，但 GitHub 的三方
merge 仍把原 promotion 判為 conflicting，可從 source delivery 建立一次性的 sibling
bridge；不得 force-push 或直接推送到既有 delivery branch，也不得修改 merge settings：

```bash
git fetch origin main dev/m<編號>-<簡稱>
git switch -c promote/m<編號>-<簡稱> origin/dev/m<編號>-<簡稱>
git merge --no-ff -s ours origin/main
test "$(git rev-parse HEAD^{tree})" = \
  "$(git rev-parse origin/dev/m<編號>-<簡稱>^{tree})"
git push -u origin promote/m<編號>-<簡稱>
gh pr create --base main --head promote/m<編號>-<簡稱> --label promotion
```

Preflight 會把 `promote/mN-slug` 唯一對應到 `dev/mN-slug`，要求 bridge commit 的
first parent 是該 source delivery 最新 SHA、second parent 是 current main，並確認
bridge、workflow candidate 與 source tree 完全相同。Included PR provenance 只接受
bridge ancestry 中已合併到同一 Milestone `dev/mN-*` 的 PR；跨 Milestone、`dev/next`、
沒有 merged PR 的額外 commit、source ref 漂移或 tree 漂移都 fail closed。Bridge PR
完成後即刪除暫時 branch；原 delivery branch 不重寫。

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

## PR lifecycle single-writer

任何 agent 要把既有 PR 轉 Ready／Draft、改 label／milestone、準備 merge authorization
或合併前，必須先在 exact terminal policy-base SHA 的乾淨 detached checkout，以 `scripts/pr_lifecycle.py acquire` 對精確 repository、PR、head SHA
與 task owner 建立 lease evidence。工具會用 create-only atomic push 同時取得該 PR 的
remote ref 與以 base branch 雜湊命名的共用 destination-lane ref；任何兩張指向同一 base
的 PR 都不能同時持有 merge lane。取得失敗、lease
remote commit／base／head 漂移時一律停止。只有 remote commit 格式、parent、tree 與期限皆
可驗證的過期 lease 可用 atomic compare-and-swap 回收；新 audit 會保留被回收 commit。

持有 lease 的 task 只能透過同一工具的 `state` 執行 Ready／Draft，透過 `edit` 改
body／label／milestone，並用 `authorization-template` 產生綁定該 PR 與完整 head SHA 的唯一文字，
交由具 live maintain/admin 權限的人類原樣張貼。禁止直接呼叫 `gh pr ready`、`gh pr edit`
或 `gh pr merge`。其他 task 在 lease 釋放前只做唯讀複審，若找到 blocker，先通知 owner，
並用 `[P0]`、`[P1]` 或 `[merge-blocker]` 開頭；只有明確
`[merge-blocker-resolved]` 可解除。不得自行改 PR state。Owner 在動作完成或明確放棄後
才執行 `release`。Remote commit 與 audit comment 只公開隨機 capability 的 digest；raw
capability 只存在 owner 的本機 evidence，任何 state／edit／release 前都重新驗證。
GitHub App caller 必須從 pinned token action 的 `app-slug` 明確傳入 actor；一般 token 只
接受 `/user` 可驗證的 identity，無法驗證時 fail closed。Audit 建立回應與後續 refetch 都
必須吻合該 actor、repository、PR 與 canonical body。

任何 task 都可在不取得 lease 的情況下唯讀查詢：

```bash
./scripts/pr_lifecycle.py lease-status \
  --repo <owner/repo> --pr-number <number> --head-sha <full-sha>
```

輸出 schema v1、repository、PR、exact head/base、兩個計算後的 remote refs，以及
`available`、`held` 或 `unknown`。`available` 只允許下一步嘗試 atomic `acquire`；不能
當成已持有 lease，也不能單獨授權任何 mutation。所有 lifecycle write 都必須從 exact
terminal policy-base SHA 的乾淨 detached checkout 執行，並在 mutation 前驗證 HEAD、
origin 與 dirty state；PR candidate checkout 只作 live data，不能提供 writer 或其 policy
dependencies。
A stacked PR may remain a visible Draft, but lifecycle writers do not execute
from or against its mutable parent. After that parent integrates, retarget the
child directly to the terminal policy branch and re-run status before any
automated metadata or merge write.

`check` 與 `merge` 會在 lease 內分頁重讀 timeline、一般留言、inline review comments、
submitted COMMENTED review bodies、reviews、checklists、base、
exact-head required checks 與 effective Ruleset；較新的 Draft、blocker 或任何漂移都使授權
失效。即使 blocker 已明確解除，merge authorization 仍必須晚於最新 blocker 與 resolution
邊界，舊 authorization 不會恢復有效。`lease-status` 唯讀重用相同的 live PR、base 與
remote lease 驗證，只輸出 versioned JSON 的 `available`、`held` 或 `unknown`；可用
`available` 不代表已取得 lease。`merge` 在 REST PUT 前再對 PR 與 destination lane refs 執行 exact CAS，且只使用
SHA-bound synchronous REST merge。無法證明 approval、last-push、
thread resolution、required checks 與 no bypass 時，包含 GitHub Free private repository，
agent 必須停在 `human-only`，由人類在 GitHub 上手動合併。

Release Please action 會在回傳精確 PR number／head 前建立或修改 branch、Draft 與 labels，
無法原子綁定這個 exact-PR lease，因此 Private Free degraded mode 的 repository workflow
會停用自動 release PR 建立／更新，並明確 fail closed 為
`release pull request (human-only)`，且不授予 PR／contents write。Human maintainer 建立
或更新 release PR 後，後續 metadata／state 寫入仍必須走 lifecycle lease；不得把這個降級
宣稱為已序列化的自動 release writer。

## Actions 額度 fallback

本 repo 是 GitHub Teams private plan，結構性地會超出每月 included Actions
minutes；這是這個 repo 從一開始就會遇到的常態限制，不是需要升級方案或等待
「恢復」才能解決的一次性事故。

這個流程適用於 GitHub Actions job 出現 zero-step billing block：GitHub 的
runner 未啟動訊息提及 failed payments 或 spending limit，工具以其精確、泛用的
billing 註記文字機械式辨識，不判讀實際帳務子原因——GitHub 帳務方案的內部差異
不是這個 repo 的治理範圍。一般測試失敗、workflow／權限錯誤、平台事故、原因
不明，或任何已開始執行 step 後才失敗的 job，都不算 zero-step billing block，
仍然維持 blocked。

合併前必須確認 worktree 乾淨且 `HEAD` 等於 PR head SHA，執行完整本機驗證與每個可
忠實重現的 required check；任何失敗都停止，GitHub-only checks 則逐項列出。不得
建立或偽造成功 Check Run。fallback 不取代 release、publishing、deployment
approval、secrets、provenance、CODEOWNER review 或任何無法本機重現的控制。額度
恢復後須補跑該 SHA 的 GitHub checks 並記錄結果；平台不再允許補跑時，另開 Issue
保留缺口，不得宣稱追溯成功。

### 一般 Issue PR

用 `scripts/promotion_gate.py note-quota-fallback` 對每個受阻
run URL 機械式確認 zero-step billing block（拒絕任何已執行 step 的 job），在 PR
留下標題為 `Actions quota fallback note` 的留言，記錄 head SHA、受阻 run URL、
驗證命令與結果、未重現 checks。留言產生後即可合併，不需要 human maintainer 另外
即時確認或留言授權；新 commit 使既有 note 失效並須重新驗證、重新產生。只有 repo
現行政策已允許 author self-merge 時（見下方 Alpha 例外），agent 才可合併。
子命令只接受依 repository branch strategy 判定為非 promotion 的 PR，會要求乾淨
worktree 與精確 PR head、完整分頁讀取該 head 的 latest Check Runs，並要求所有
`--blocked-run-url` 精確等於自動發現的失敗 Actions run 集合；漏列失敗、非 Actions
失敗、未完成／不支援的 check 或非成功 commit status 都會 fail closed。工具執行 repo
內建完整 verifier 後會再次確認 live head 與 check 集合未變，並將固定的 `passed` 結果
與每個 `--unreproduced-check` 寫入 note；verification 失敗時不會輸出可用 note。

例如 delivery strategy 的一般 PR 可執行：

```bash
./scripts/promotion_gate.py note-quota-fallback \
  --repo owner/repo \
  --pr 42 \
  --branch-strategy delivery \
  --blocked-run-url https://github.com/owner/repo/actions/runs/123 \
  --unreproduced-check "GitHub-hosted runner identity"
```

stdout 會以單一留言格式輸出標題與 JSON binding；生成專案的 canonical verifier 是
`./scripts/verify`（公版來源 repo 則是 `./scripts/verify-template.sh`）：

```text
Actions quota fallback note

`{"head_sha":"<PR head SHA>","pull_request":42,"repository":"owner/repo","runs":["https://github.com/owner/repo/actions/runs/123"],"verification":{"command":"./scripts/verify","result":"passed","unreproduced_checks":["GitHub-hosted runner identity"]}}`
```

留言發布後，保留 candidate worktree 的 full verification evidence，另從 live status 回報的
`<terminal-base-ref>@<terminal-base-sha>` 建立乾淨 detached worktree；只在該 trusted
checkout 取得 exact-head lifecycle lease 並執行合併，不直接呼叫 `gh pr merge`：

```bash
git worktree add --detach /tmp/csarc-policy-base <terminal-base-sha>
cd /tmp/csarc-policy-base
./scripts/pr_lifecycle.py acquire \
  --repo owner/repo --pr-number 42 --head-sha <PR head SHA> \
  --owner <task-id> --output /tmp/pr-42-lease.json
./scripts/pr_lifecycle.py merge-quota \
  --repo owner/repo --pr-number 42 --head-sha <PR head SHA> \
  --owner <task-id> --lease /tmp/pr-42-lease.json
```

`merge-quota` 不接受 authorization URL；它會在 lease 內前後各重讀一次 live PR，要求
PR author 與 current lease actor 相同、內文含 `Alpha 自行合併 / self-merged`、恰一個本 repo closing Issue 且沒有未勾選
項目，重新列舉該 head 的完整 failed run 集合、逐一驗證 zero-step billing block，並核對
唯一 canonical note，且 note 必須晚於最新 blocker／resolution 與 Draft transition。
Promotion、hotfix、workflow／governance、dependency、template 與
unknown scope 一律拒絕；最後仍以 destination lease CAS、base SHA 與 merge response 驗證
封住併發漂移。

合併到非 default integration branch 時，GitHub 不會自動關閉 closing Issue，因此 lifecycle
會在同一個未過期 lease 內重新驗證 merged PR head/base、squash parent、route／containment 與
Issue／PR checklist，關閉（或確認已關閉）Issue 後才釋放 lease。若 merge 已成功但關閉或
lease release 回應失敗，可在該 lease 到期前以同一 actor 重跑 recovery：

```bash
./scripts/pr_lifecycle.py close-issue \
  --repo owner/repo --pr-number 42 --head-sha <PR head SHA> \
  --owner <task-id> --lease /tmp/pr-42-lease.json
```

route 尚未整合、containment 漂移、actor 不符、lease 到期或 evidence 不完整時一律 fail
closed；status 只有在 retained lease 的 identity、TTL 與目前 actor 都仍有效時才列出
`close-issue`。其餘狀態交由 maintainer 查明或修復 lease，不得改用未受 lease 保護的手動
`gh issue close` 取代。沒有 closing Issue、且符合 canonical branch route 的
sync／automation PR 會在 merge 驗證完成後直接釋放 lease；任意未連結 feature branch 不屬於此例外。

### `dev/next` promotion preservation

每一個 `dev/next` → `main` promotion（一般 hosted、merge queue、manual 或 quota
fallback）都必須先由管理者對精確 PR/head 執行 `delivery_sync.py prepare-dev-next`。
`policies/dev-next-ruleset.json` 只保護 `dev/next` 與
`csarc/dev-next-preservation-ledger`：兩者都禁止刪除與 non-fast-forward 更新，其他
`dev/*` branch 仍可按生命週期清理。gate 會重新讀取 ledger 的完整單 parent 歷史、live
PR/refs、effective rules 與 repository setting。只有兩個 ref 的 effective rules 都可驗證時
才採 `ruleset-protected`；private repository 無法讀取 rules API 時可採下述 temporary mode，
但任何無法綁定 exact prepared transaction 的情況仍一律 fail closed。

Temporary mode 的 ledger ref 可能不受保護，因此 ref 本身不是 trust anchor。工具輸出的
canonical authorization body 會綁定 repository、PR、base/head SHA、operation ID 與
exact prepared ledger commit SHA，且必須由兩位不同、當下仍具 admin／maintain 權限的
human maintainer 原樣留言授權。合併前 live ledger ref 必須仍精確指向該 SHA；合併或中止後
只能沿包含該 authorized SHA 的 canonical 單 parent history 完成 transaction。ref 被移動、
刪除、改寫或無法讀取時一律停止並交由人工恢復。

一般 promotion 的 preflight evidence 會綁定 exact prepared ledger commit；main
post-merge verifier 以同一 evidence append `restoring-complete`，再恢復暫停的
auto-delete 並 append `completed`。關閉未合併 PR 則由 `dev-next-close.yml` 發出 signal，
再由 `delivery-maintenance.yml` append `restoring-abort`、恢復並 append `aborted`。
`preparing` 配上已停用 setting、`prepared`
配上已恢復 setting，或 PATCH 結果不明時都不自動猜測 ownership，必須人工檢查後重跑
exact restoring operation。完成的 main base 不可重用；aborted operation 釋放該 base，
但同一 operation ID 不可 replay。

Hosted temporary restoration 只使用獨立的 `CSARC_SYNC_TOKEN`，不會退回
`github.token`。Prepare evidence 會以 secret metadata 標示 `hosted` 或 `human-only`；
hosted complete／abort 在 append restoring checkpoint 前，先用該 token 對目前 setting 做
no-op PATCH 並 refetch，以證明當下仍有 admin write。secret 缺失或驗證為 403 時不更新
ledger／setting，workflow 失敗並輸出綁定 exact transaction 的人工 command。
`promotion.yml` 與 `pr-policy.yml` 的 `pull_request`／`merge_group` jobs 只使用 read-only
`github.token`，不引用管理 secret；temporary prepare 必須事先由 human maintainer 或其他
受保護的 trusted path 完成。只有從 default branch 載入的
`promotion-post-merge.yml` push job、`delivery-sync.yml` main-push／manual reconcile 與
`delivery-maintenance.yml` workflow-run job 可取得 `CSARC_SYNC_TOKEN`。PR close 只觸發不含 secret 的 `dev-next-close.yml`；後續
trusted workflow 會重新查驗 workflow ID 與唯一 closed PR，且不得 checkout 或執行 PR
head 的程式碼。

### Promotion PR 的額外 fallback 證據

`dev/m*`、`dev/next`、`dev/i*` 或 delivery strategy 的 `dev` promotion 到 `main`
是實際的 release 邊界，風險層級不同，維持較嚴格的雙方確認，可使用同一個
quota-only 例外；一般 main PR、release follow-up 與 hotfix 不因此新增快速通道。
除前述共同條件外，必須使用既有 `scripts/promotion_gate.py`，依序完成：

1. 在乾淨、精確等於 promotion PR head 的 worktree 執行 `prepare`，且
   `--candidate-sha` 必須是該 head SHA；保存 candidate archive、SHA-256、base/head SHA、
   candidate tree、納入 PR、SemVer intent 與 canary 三態。
2. `dev/next` 的 standalone batch 必須先用相同 PR number 與 head SHA 執行
   `delivery_sync.py prepare-dev-next`。工具先在遠端 append-only Git ledger 以
   non-force fast-forward 建立唯一 transaction，綁定 repository、PR、base/head SHA 與
   原本為 `true` 的 auto-delete，再於平台 deletion protection 無法驗證時暫停
   auto-delete。若 API 不支援可信 ledger、已有其他 transaction，或 setting 原本就是
   `false`，一律 fail closed；中止 promotion 時先關閉未合併 PR，再以同 operation ID
   執行 `abort-dev-next` 恢復。
3. 在同一 PR 留下標題為 `Actions quota fallback attestation` 的標準留言，再由 human
   maintainer 留下 `Actions quota fallback authorization`。兩則留言都必須使用工具定義的
   canonical JSON，精確綁定 repository、PR、base/head SHA、candidate tree、archive digest、
   完整 blocked-run set 與上述 remote ledger commit／transaction。前者明示具 billing
   visibility 且確認為已授權的一次性 billing zero-step block 特例處理，後者明示一次性、
   無 admin bypass 的授權。
4. `finalize-quota-fallback` 只接受 preflight archive、兩則留言 URL 與所有 blocked run
   URL；工具會 refetch 同一 remote transaction，自行選擇 repo 內建 verifier（模板來源 repo 為
   `./scripts/verify-template.sh`，生成專案為 `./scripts/verify`），並以 live
   repository variables 重建 promotion preflight，
   不接受呼叫者提供的命令字串。若 canary 是 `allowed`，fallback 不得替代它；只有
   `blocked`／`unknown` 可維持 artifact-only。工具也會 refetch 留言、作者資格與 live
   GitHub identity；輸出的 gate 是 `quota-fallback`、`release_eligible` 固定為 `false`。
5. 僅以非 admin 的 squash merge 合併。更新乾淨的 `main` checkout 後執行
   `verify-quota-main`，確認 main tree 等於已驗證 candidate tree，並把結果留在 PR；
   `dev/next` route 還會重新讀取 canonical authorization 所綁定的 prepared ledger commit，
   只用同一 operation、merged PR、head SHA 與 current main SHA 執行
   `delivery_sync.py complete-dev-next`。工具確認長期 branch 未消失、tree lineage 一致後，
   才把該 transaction append 為 completed 並恢復原本的 auto-delete；任何一步不符都停止、
   revert／修正，不重寫歷史。

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
