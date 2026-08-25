# Low-friction AI SDLC policy（提案）

> **尚未全面生效。** 本頁是 [Issue #264](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/264)
> 的可驗收草案。#240 與 #266 已由目前的 #266 candidate 整合；現行操作仍以
> `AGENTS.md` 與 [`docs/ci-policy.md`](ci-policy.md) 為準。#266 完成 review／full
> verification／merge 且 #268 留下實際 walkthrough evidence 後，才能把本頁改為 Accepted。

設計依據、外部比較、現況摩擦與 decision disposition 見
[`low-friction-ai-sdlc.md`](adr/low-friction-ai-sdlc.md)。這份草案只保留團隊使用者與
agent 執行工作需要知道的最短路徑。

## 預設 happy path

1. **選一張 Issue。** 先查 open／closed Issue、open Draft PR、remote branch 與既有
   worktree；若已有 owner 就 review 或協調接手，不再建立第二條 branch。
2. **讓 route 可推導。** 有 Milestone 的 Issue 從對應 `dev/m*` 開 `type/<issue>-*`；
   沒有 Milestone就從 `dev/next` 開。除非 Issue 已記錄獨立 soak／canary 或正式環境
   hotfix，不要求使用者再選 branch 類型。
3. **及早開 Draft。** 有可說明的最小解法且 targeted check 通過後即可 push／開 Draft；
   body 寫 scope、已完成／待完成驗證、風險、依賴與不可平行合併項目。acceptance 未完成
   時不使用 `Closes`、`Fixes` 或 `Resolves`。
4. **跑最短 TDD loop。** 非 trivial 行為先以最窄 regression 看到失敗，再實作到通過並
   refactor。文件或純資料變更不為文字順序造假測試；security 與資料損失邊界不能省。
5. **只在 Ready gate 收斂。** acceptance 完成、targeted checks 與一次 exact-head
   `./scripts/verify-template.sh` 通過、branch 跟上 live base、沒有較新的 blocker，才標
   Ready 並請求正式 review。
6. **依風險合併 delivery。** Routine PR 跑 policy／fast／stable aggregate；elevated PR
   升 full 並要求 human review。只有持有 #240 lifecycle lease 的 writer，或 degraded
   模式下的 human maintainer，可以執行 Ready／Draft／metadata／merge 寫入。非 default
   Issue merge 會在同一個未過期 lease 內以 canonical `close-issue` 驗證 route／containment
   與 checklist，補正 GitHub 不會自動關閉的 Issue，再釋放 lease。
7. **在 delivery boundary 才 promotion。** delivery owner 等 batch／Milestone scope
   完成，先以 reviewed PR 同步 current `main`，再以 immutable base/head/tree 跑 full、
   canary 三態與 promotion evidence。合併 `main` 後核對 tree identity，才進 release。

`main → dev/*` 只走 reviewed sync，`Issue → dev/*` 只走 Issue PR，`dev/* → main` 只走
promotion。不同 delivery branches 不互相 merge，也不直接 push。

## 例外只看四類

| 類別 | 何時使用 | 比預設多出的要求 |
| --- | --- | --- |
| Routine | 預設；docs、局部行為、已知低風險路徑 | 無。classifier 無法解釋時不算 routine。 |
| Elevated | workflow、權限、security、dependency、governance、release、跨 profile 或 unknown | full tier、獨立 human review；只有 human maintainer 可接受 risk downgrade。 |
| Promotion／hotfix | 任何進 `main` 的 delivery candidate；hotfix 只限正式環境緊急缺陷 | current-main、full、tree identity、human authority、canary 三態；quota 不取消雙重證據。 |
| Periodic／release | drift、OSV、Zizmor、artifact、SBOM、provenance | 不阻塞無關 routine PR，但失敗阻止受影響的 promotion／release。 |

## 失敗時怎麼回復

| 觀察 | 動作 | 恢復條件 |
| --- | --- | --- |
| 找不到正確 base、risk 不明或必要 `dev/next` 不存在 | 停止建立／合併；讓 owner 或 automation 修正 metadata／branch lifecycle | route 可由 live Issue 與 refs 唯一推導。 |
| Targeted／full test 失敗 | 保留 Draft，修正 production code 或測試；不把 check 改成無條件成功 | 同一 head 的必要 checks 全部通過。 |
| `main` 或 PR head 漂移 | 使舊 verification／authorization 失效；重新 sync、解 conflict、重跑受影響 checks | 新 source、destination、tree 重新綁定 evidence。 |
| 新 Draft event、blocking review、未完成 checklist | lease holder 中止 merge，不自動轉回 Ready | blocker 由有權者明確解除，重新完成 Ready gate。 |
| Actions zero-step billing block | Routine 依下節；elevated／promotion 走 human fallback | exact SHA、完整本機驗證與未重現 controls 都有記錄。 |
| Canary `blocked`／`unknown`（包含只設定一半） | 保存 artifact-only，不宣稱 external canary | full gate 仍成功；若產品要求 canary，維持 blocked。 |
| Post-merge tree／release evidence 不符 | 停止 release，開修正 Issue，使用 revert／fix flow | 不重寫 history；新 candidate 重新通過邊界。 |

## Quota fallback

- **Routine、非 elevated Issue PR：**現行 #254 流程會確認所有失敗 jobs 都是相同 exact
  head 的 zero-step billing block，由 canonical tool 重跑完整本機驗證並留一則
  `Actions quota fallback note`；在 Alpha self-merge 政策下不要求每張 PR 另等 human
  authorization。#266 candidate 已整合 #240 lease／live destination guard；它在 #266
  通過 review、full verification 並合入 delivery 後序列化同一路徑，但不撤回或延後已
  生效的 #254 fallback。
- **Elevated Issue PR：**不因 quota 自動降級；由 human maintainer 判斷是否可用現行
  SHA-bound fallback。
- **Promotion／hotfix：**維持 attestation + authorization、candidate archive、tree
  identity 與 `scripts/promotion_gate.py`；本機 evidence 固定不可建立 release。
- 任一路徑都不得建立或偽造成功 Check Run；runner annotation 本身不是帳務或內容成功。

## 可驗收 scenarios

每個 scenario 都要保存起始 refs、PR base/head、選到的 tier、人工接觸點、等待、結果與
恢復動作。#266 candidate 已提供自動推導與 fixture regressions，但不代表 #268 已完成真實
operational walkthrough；以下 `Then` 仍是該 walkthrough 的 acceptance contract。

### 1. 一般 Milestone Issue

- **Given** 一張 open Milestone Issue、對應 `dev/m*` 存在且沒有 Draft／branch owner。
- **When** agent 建 Issue branch、targeted check 後開 Draft、完成 acceptance 與 full local
  verify、標 Ready 並通過 policy／fast／review。
- **Then** exact candidate 只合併到該 `dev/m*`；不跑 release、不要求 contributor 選
  promotion 路徑，非 default base 未自動關 Issue 時由 lifecycle 可稽核地補正。

### 2. Standalone Issue

- **Given** open Issue 沒有 Milestone、沒有獨立 soak／canary 理由且不是 hotfix。
- **When** 開始工作並建立 PR。
- **Then** base 自動選 `dev/next`；流程與 routine 相同，工作整合後等待批次 window，
  不建立假 Milestone、永久 per-Issue dev branch 或直接送 `main`。

### 3. Hotfix

- **Given** Issue 記錄正式環境緊急缺陷、human maintainer 接受 hotfix 分類。
- **When** standalone `fix/*` PR 對 `main` 建立。
- **Then** 即使變更很小也跑 full、review、promotion evidence 與 tree identity；合併後
  active delivery owners 各自以 reviewed sync 回灌，不直接 push。

### 4. 平行 agents

- **Given** agent A 已用 Draft 認領 Issue，或持有某 PR／destination lane lease。
- **When** agent B 查到相同 Issue，或嘗試 Ready／Draft／metadata／merge 寫入。
- **Then** B 只能 review／協調接手；lease 取得失敗即停止。A merge 前若看到新的 Draft、
  blocker、source 或 live destination drift，也必須中止並使舊 authorization 失效。

### 5. Routine PR 遇到 quota block

- **Given** 所有 required Actions jobs 都在 exact head 以相同 billing annotation zero-step，
  內容屬 routine，完整本機驗證成功。
- **When** 現行 #254 canonical tool 證明完整 failed-run set 與本機驗證，並產生綁定
  SHA、run URLs、命令、結果與未重現 checks 的 note。
- **Then** Alpha self-merge 可在 live head/base 未變時透過 #240 lease 與 canonical
  `merge-quota` 執行非 admin squash merge，不需逐 PR human authorization；不得繞過
  lease 直接呼叫 merge API。

### 6. Milestone promotion

- **Given** 非 promotion Issues 全部完成，delivery 包含 current `main`，candidate
  base/head/tree 已固定。
- **When** promotion PR 跑 full 與 canary capability check。
- **Then** allowed canary 必須成功；blocked／unknown 可留下 artifact-only；只有
  promotion evidence 與 post-merge tree identity 都成立才交給 release-source。quota
  fallback 仍要 human 雙重證據，且不能發布。

### 7. `dev/next` promotion 後被平台刪除

- **Given** repository 開啟 `delete_branch_on_merge`，`dev/next → main` promotion 完成。
- **When** GitHub 嘗試刪 head branch或 hosted workflow 無法啟動。
- **Then**平台 protection 應保留 branch；degraded fallback 只能依 exact merged PR／main
  identity 冪等恢復。`delivery-sync` 遇到 missing `dev/next` 必須失敗，不能把空集合當成功。

## Ready 與 promotion 的最小 evidence

| 邊界 | 必留 evidence |
| --- | --- |
| Draft | owner、scope、base、依賴、targeted checks 與未完成項目。 |
| Ready | acceptance、exact head、targeted results、`verify-template.sh`、risk tier、blocker 狀態。 |
| Delivery merge | PR、exact source/live destination、review、required checks、lease／human actor。 |
| Promotion | base/head/tree、納入 Issues／PRs、current-main、full、canary state、quota 限制。 |
| Post-merge／release | main tree identity、source evidence URL、release eligibility、artifact／SBOM／provenance 結果。 |

## 生效條件

#254、#261 與 #265 已是 delivery 基線；#266 candidate 已整合 #238、#240、path status、
root／template parity 與 regressions。剩餘 activation evidence 是 #266 的獨立 final review、
exact-head full template verification 與 delivery merge，以及 #268 保存的實際 walkthrough
artifact／comment。完成前本 ADR 維持 Proposed，任何尚未生效的自動化都維持 fail-closed
手動流程。
