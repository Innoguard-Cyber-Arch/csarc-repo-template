# CI 與交付政策

這份文件定義 branch topology、PR routing、驗證、promotion 與 release evidence。`AGENTS.md` 定義工作行為；workflow 與 scripts 是可執行的 enforcement。

## Branch topology

`main` 是唯一永久整合 branch。不得建立或恢復另一條固定開發 trunk。

- 有 Milestone 的工作使用該 Milestone 專屬、短命的 `dev/m<編號>-<簡稱>`。Issue branch 以 PR 進入 delivery branch；Milestone 完成後 delivery branch 以 promotion PR 進入 `main`，驗證完成便刪除。
- 沒有 Milestone 的 standalone Issue 從 `main` 建立 `type/<Issue>-<簡稱>`，並直接以 PR 回到 `main`。
- `fix/*` 加 `hotfix` label 可直接 target `main`，但仍須完整 gate。
- Dependabot 與其他 `automation/*` branch 直接 target `main`。
- 不提供永久 shared-development branch 或每案 isolated delivery branch。需要 soak／canary 時，將它列為同一 PR 的風險升級條件，不建立另一套 branch lifecycle。

Delivery branch 必須對應 open Milestone；Milestone 關閉後不得再接收新工作。一般 Issue 沒有 Milestone 時不可假造 Milestone，只需走 direct-to-main。

## PR routing

PR policy 由 live Issue metadata、head、base 與 open stacked PR chain 推導唯一目的地：

| 工作 | 合法目的地 | 說明 |
| --- | --- | --- |
| Milestone Issue | matching `dev/m*` | stack 的最上游必須回到同一 delivery branch |
| Standalone Issue | `main` | 一個短分支、一張 PR |
| Dependabot／automation | `main` | 不經 delivery branch |
| Hotfix | `main` | `fix/*`、`hotfix` label、完整 gate |
| Milestone promotion | `main` | exact delivery candidate、`promotion` label |
| Release follow-up | `main` | 只接受可信 release automation 或具 maintain 權限的維護者 |

Draft PR 可用 `Refs #N`，但必須列出 scope、已完成／待完成驗證、風險與非平行依賴。Ready 或帶 closing keyword 的 PR 不得有未勾選 PR／Issue acceptance task。

### Draft ownership 與 Ready 邊界

Issue owner 負責 ordinary PR 的 scoped checks，完成後即可轉 Ready；不在 Ready 前先跑本機 full。Final promotion 的 tree 先固定，PR checklist 在轉 Ready 前聲明「Ready 將啟動 hosted full」，再由 hosted workflow 對 exact integrated candidate 跑唯一一次 full gate；成功只由 required `verify` check 記錄，不需事後編輯 PR body 並觸發同一 tree 重跑。只有 hosted job 未執行且文件明定的 fallback 適用時，integrator 才改跑一次相同本機入口，不能兩邊重複。Draft 階段可疊加同一 Milestone 的後續工作，但每張 PR 仍要清楚列出 owner、依賴與未完成項目。只有 acceptance、metadata、closing Issue 關聯與最窄必要驗證都完成後才轉 Ready；push 新 head 會使舊 review、authorization 與 evidence 失效。

Agent 不得把 Draft、未處理 review thread、真實測試失敗或 scope 漂移當成平台限制。Alpha reviewer 例外只適用政策明列的 routine Issue route，且不改變 Issue owner、integrator、required checks 或 exact SHA/tree 責任。

## Main 同步與 Milestone promotion

Ordinary `type/* → dev/m*` PR 只需跟上自己的 live base，不因較新的 `main` 被判 stale。`main` push 不改寫 ordinary PR status，也不逐條掃描 active delivery 或 fan-out sync PR；standalone、bot 與 hotfix 的新結果預設等每個 Milestone 自己進入 final promotion 才回流。

Final promotion preflight 會把 exact `dev/m* → main` 或 `promote/m* → main` candidate 與當下 `main` 比較。若 stale，只能針對該 Milestone 執行一次 `delivery-maintenance.yml`，輸入 exact `delivery_branch`、requesting promotion `pr_number` 與 `reason=promotion`，建立或指出 deterministic `sync/main-to-m<編號>-<簡稱>-<main短SHA>` reviewed PR。禁止直接 push、force push、改寫 delivery history或同步其他 Milestone。

若 ordinary Issue 在完成前確實需要已進 `main` 的功能，其 PR owner 必須先在 Draft contract 的 `Dependencies / non-parallel work` 明列依賴，再以自己的 PR number 與 `reason=explicit-dependency` dispatch 同一個單 branch workflow。Workflow 會重讀 live PR、owner、base、dependency、delivery ref 與 open Milestone；任一不符便 fail closed。這是例外，不是定期更新 delivery 的機制。

若 current `main` 可乾淨合入 delivery，promotion head 可直接使用 exact `dev/m*`。若 GitHub 無法以 squash merge 保留 exact candidate tree，建立同 Milestone 的一次性 `promote/m<編號>-<簡稱>` bridge：first parent 是 delivery head、second parent 是 current main，bridge tree 必須仍等於 delivery tree。Bridge 不承接新工作，完成或 abort 後刪除。

Promotion gate 必須驗證：

1. base 是 current `main`，head 與 linked promotion Issue 的 Milestone 相符。
2. delivery 已納入 current main，或 bridge 的 parent／tree identity 完全符合規格。
3. Milestone 內非 promotion Issues 已完成，included PR provenance 可追溯且沒有跨 Milestone工作。
4. exact candidate SHA／tree 只接受同 repo、同 PR、同 run 的證據。
5. full verify 與已配置 canary 結果符合政策；未配置 canary 明確記錄 artifact-only，不能宣稱成功部署。

Promotion 可使用 merge queue，但 queue ref、base SHA、source PR 與 candidate tree 任一漂移都 fail closed。整合後的 workflow 只核對 merged main SHA、tree、唯一 squash source 與 provenance，不重跑完整矩陣。

### 兩個 Milestone 的操作 walkthrough

假設 `dev/m7-api` 與 `dev/m8-auth` 同時進行，而一張 standalone PR 已合併到 `main`：

1. M7、M8 的 ordinary Issue PR 繼續各自進 delivery，不建立 sync PR、不寫 stale status，也不互相 merge。
2. M7 建立 final promotion PR；preflight 若發現缺少最新 `main`，只為 M7 指出一次 `delivery-maintenance.yml` action。M7 owner dispatch `delivery_branch=dev/m7-api`、`reason=promotion` 與該 promotion PR number。
3. `sync/main-to-m7-api-<SHA>` 經正常 review／checks 合併後，M7 重新固定 candidate SHA/tree、只跑一次 full gate，再 promotion。M8 沒有任何 mutation。
4. M8 日後進入自己的 final promotion 時，才以相同步驟納入當時最新 `main`，其中自然包含 standalone 與已 promotion 的 M7。
5. 若 M8 某張 ordinary PR 在此之前真的依賴 standalone 結果，該 PR owner 先明列 dependency，再以 `reason=explicit-dependency` 只同步 M8；沒有這份 live owner evidence 就拒絕。

## CI 分層

`scripts/ci_tier.py` 將 changed paths 分成 docs、source、template、workflow、governance、dependency、shell 與 unknown。unknown、promotion、hotfix、merge queue 或明確手動要求一律升級 full；一般 Issue PR 先跑 scoped fast checks。穩定 required aggregate 必須在所有路徑產生成功或失敗結論，routing 留在 job 層，不能因 job 未建立而讓 required check 永久 pending。

- docs：結構與文件驗證；網站來源變更才產生 preview artifact。
- fast：lint、型別與受影響測試。
- full：完整 canonical verification 與 template rendering；runtime matrix、remote governance、OSV 與 Zizmor 仍由 stage／changed scope 個別路由，scheduled 才全部執行。
- post-merge：SHA／tree／provenance identity，不重跑已通過的 full matrix。
- scheduled／release：全歷史、最深矩陣與長時間供應鏈檢查。

Workflow、governance、generator、CLI adoption/update、release、安全、promotion、provenance、unknown path、hotfix 與 merge_group 都屬 fail-closed 風險範圍；直接進 main 時升級 full，ordinary Issue PR 則保留 scoped fast 與對應 auxiliary job。完整測試責任與 flaky／quarantine 規則另見 behavior verification contract。

### 選配容器交付

只有既有 repo 明確設定 `container_mode` 並提供產品自己的 Dockerfile／Containerfile 與 `$IMAGE` smoke command，才建立容器工作。PR 只建置、不 push，並執行 smoke 與 Trivy HIGH／CRITICAL 掃描；已驗證 release-source 才能保存 image bytes、checksum、SPDX SBOM，發布 job 才取得 registry、OIDC 與 attestation 寫入權限。發布後必須以 digest pull 同一份 bytes 再驗證與 smoke test。

`container_mode=none` 不生成容器 job、Docker Dependabot 或 registry 權限。公版不代替產品設計 Dockerfile、Kubernetes、雲端部署或 multi-arch matrix。

Issue owner 只執行 plan 宣告的 scoped checks；`verify-fast` 跳過 `large`，但不跳過
`quarantine`。Hosted full 是 final unchanged tree 的預設唯一完整 gate；integrator 只在
文件明定的 fallback 改跑一次本機入口，不會在 Ready 前與 hosted full 重複。
`runtime` 是 cross-runtime job 唯一重跑的集合；scheduled／release 才承擔最深矩陣與
長時間檢查。Changed-file discovery 使用 rename-safe 的 old/new path 語意，不能把
workflow、security 或 verifier rename 到 docs path 來降級。

## Actions 額度 fallback

一般情況必須等 required checks 成功。若 GitHub 明確因 included Actions minutes 耗盡，在 runner 尚未分配、steps 為空且 billing annotation 可驗證時擋住工作，可使用 quota fallback；真實測試失敗、取消、逾時或證據不完整都不可套用。

工具只接受 failed payments 或 spending limit 類型的 zero-step billing block；任何已執行 step 的 run 都不是 quota fallback。合併前工作樹的 `HEAD` 必須等於 PR head SHA，且本機須完成所有可忠實重現的 required checks。標題為 `Actions quota fallback note` 的留言記錄 exact head、run URL、指令與未重現的 hosted-only checks；新 commit 使它失效。

- Routine PR：對 exact PR/head 獨立執行完整本機驗證，留言綁定 run URLs、指令與未重現的 hosted-only checks。
- Milestone promotion：先產生 exact candidate archive 與 preflight evidence；PR owner／integrator 執行固定完整驗證。獨立 maintainer 的 attestation 與另一位 human maintainer 的 exact-head merge authorization 必須分開，且 fallback 永不成為 release-eligible evidence。

Promotion fallback 另要求不同 maintainer 留下 `Actions quota fallback attestation` 與 authorization，並只透過 `promotion_gate.py finalize-quota-fallback` 產生 `release_eligible: false` 的 evidence；merge 後由 `promotion_gate.py verify-quota-main` 核對 main identity。

任何 PR head、base、Draft、label、Issue、Milestone、canary 或 run identity 改變都使既有 fallback 失效。不得把本機成功寫成 GitHub check success，也不得跳過 branch protection。

Alpha 的 reviewer 例外只接受 policy 明列、關閉同號 open Milestone Issue 的 routine `type/* → dev/m*` route；reviewed sync、default-branch、promotion、hotfix 與 release 一律不適用。Free private 無法讀取 effective Ruleset 時仍停在 human-only，不得推定 server-side enforcement。

## PR lifecycle single-writer

任何 agent 要把既有 PR 轉 Ready／Draft、改 label／milestone、準備 merge authorization 或合併前，都必須以 `scripts/pr_lifecycle.py acquire` 對 exact repository、PR、head SHA 與 task owner 建立 lease evidence。工具同時取得 PR ref 與 destination-lane ref；取得失敗、lease remote commit／base／head 漂移都停止，只有完整 remote commit、parent、tree 與期限可驗證的過期 lease可用 atomic compare-and-swap 回收。

持有 lease 的 task 只透過 lifecycle 工具執行 state、edit、authorization-template、check、merge 與 release。其他 task 只做唯讀複審；blocker 留言使用 `[P0]`、`[P1]` 或 `[merge-blocker]`，只有明確的 `[merge-blocker-resolved]` 可解除。Remote audit 只公開 capability digest；raw capability 留在 owner 的本機 evidence，且每次 read-check-write 都重讀 live state。

`check` 與 `merge` 會分頁重讀 timeline、comments、reviews、checklists、base、exact-head required checks 與 effective Ruleset。`merge` 在同步 REST merge 前再次 CAS PR 與 destination refs；無法證明 approval、last-push、thread resolution、required checks 與 no-bypass 時必須停在 human-only。`release pull request (human-only)` 同樣不會被 agent 自動寫入或合併。

Release follow-up 的 trusted workflow 只從 default branch 載入，重讀 live PR、destination、files 與 commits，並在驗證前後確認 destination SHA 未移動；Rules API 不可驗證或 live ref 漂移時 fail closed，候選 branch 內同名 job 不算可信 gate。

## Concurrency 與外部 mutation

PR metadata 與 merge 等 read-check-write 操作必須以 `scripts/pr_lifecycle.py` 的 repository-scoped lease 序列化。lease 綁定 operation、actor、target PR、expected head 與 TTL；取鎖後立即重讀 live state，完成或失敗皆釋放。Git push 仍使用 explicit refspec 與 `--force-with-lease`；不得依賴未解析 glob。

Promotion、release、hotfix 與 bot route 共享 main，因此每次 mutation 都要驗證 destination SHA 未移動。單 branch Milestone sync／promotion 另以 branch-scoped concurrency 避免同一 delivery branch 同時被同步與交付。

## Repository settings

`scripts/apply-repository-settings.sh` 只套用 `policies/rulesets.json`、labels、repository settings 與 Actions policy。治理檢查必須確認 default branch protection、required checks、review、signed commits、allowed actions 與 immutable releases；不會暫時修改 repository-wide branch auto-delete 設定。

`plan` 只顯示差異，`apply` 需要管理權限，`check` 對任何缺失 fail closed。權限不足或 API 回應不完整時不可推定設定正確。

## 安全掃描與治理頻率

每張適用 PR 的 change-aware fast/full route 會執行 secret scan、workflow audit，並依 dependency、workflow、governance 或未知高風險路徑升級 OSV、Zizmor 與 remote governance；promotion、hotfix、release recovery 與 merge queue 一律 full。排程負責全歷史、長時間與最新漏洞資料，不重跑與 PR tree 相同的完整產品矩陣。

任何掃描無法取得必要資料、action pin 無法驗證、Rules API 回應不完整或 provenance identity 不明，都必須 fail closed 並保留明確 blocked／degraded evidence；不得把「沒有執行」寫成成功。

## Release boundary 與證據

Milestone promotion 或 hotfix 可形成 release boundary；普通 direct-to-main PR 只累積 SemVer intent，由 release follow-up 在 `main` 上聚合。`fix`／`revert` 是 patch、`feat` 是 minor、`!` 是 major，其餘為 no-release；全為 no-release 時不建立空版本。

Release follow-up 必須掃描上一個 tag 到自身 parent 的完整 first-parent 歷史，逐一下載並核對每個 promotion／hotfix 的成功 post-merge identity evidence。缺少 evidence、quota fallback 的 `release_eligible: false` 或失敗的 tree identity 都 fail closed；後續普通 PR 或 release follow-up 不得把先前不合格的 boundary 洗白。

Release source 必須綁定 current main、唯一來源 PR、promotion evidence（若適用）、版本與 CHANGELOG。Artifact workflow 只接受明確 dispatch 的已驗證 source run，不接受任意 tag push，也不在 checkout 後改寫版本。tag、source SHA、artifact digest、SBOM 或 provenance 任一失配都保留 draft／pending 並停止發布。

Release draft 先上傳 wheel、sdist、release prompt、SPDX SBOM、manifest、provenance 與 digest inventory；fresh-download 必須逐檔比對、驗證 package metadata、dependency graph／purl 與 GitHub attestation。只有 exact tag、source SHA、版本、八項資產與發布順序全部相符，才可轉為 immutable Release。缺少任何一項不得用 quota、人工文字或本機檔案冒充。

### Maintainer hotfix 與 release recovery

Hotfix 由同號 Issue 的最小 `fix/*` branch 直接進 `main`，但仍需 full、review、tree identity 與 post-merge evidence；合併後不主動同步所有 active Milestone，等各 Milestone final promotion 自行納入。缺失 Release 使用 `release-recovery` label 與同號 branch，保留專用 promotion/post-merge evidence；它可保留 canonical Milestone 追蹤資訊，但不能降格成普通 direct-main boundary。

## Migration

既有 repo 更新後：

1. 先確認所有舊整合工作已在 `main`，且沒有 open PR 依賴舊 branch。
2. Copier update 會把舊 `branch_strategy: dev` answer 明確改成 `main`；更新後 `.copier-answers.yml` 與 `.csarc/profile.json` 不得再保留 `dev`。
3. 將 standalone、hotfix 與 bot PR retarget 或重建為由 `main` 分出的短 branch；若 squash history 造成巨大 diff，關閉舊 PR 並讓 bot 從 main 重建，不做危險 retarget。
4. 保留仍 open Milestone 的 `dev/m*`；不要因 main push 批次同步，等各自 final promotion 再用一張 reviewed sync PR 納入當時最新 main。
5. 移除舊 branch 專用 workflow／ruleset／ledger；不要重建已刪除的固定 branch。
6. 執行 `./scripts/verify` 與 `./scripts/apply-repository-settings.sh check`，確認 generated template 與 root policy 一致。

`apply-repository-settings.sh plan` 必須明列遠端舊 `CSARC preserve dev next` Ruleset；`check` 對它 fail closed，`apply` 只依 exact Ruleset name／ID 刪除後再驗證，不以模糊名稱或 repository-wide 設定替代。更新中若任何 migration hash、Copier conflict 或 live route 不明，停止並保留舊 checkout 供人工回復，不做部分套用。

此 migration 不弱化 review、security、release、provenance、tree identity 或 concurrency controls；它只刪除永久中間 trunk 與其衍生的全域設定 mutation。
