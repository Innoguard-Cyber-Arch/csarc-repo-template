# Agent collaboration and durable handoff ADR

- **狀態：**Accepted
- **日期：**2026-08-25
- **來源 Issues：**[#126](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/126), [#145](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/145), [#155](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/155), [#171](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/171), [#177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/177), [#204](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/204), [#240](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/240), [#241](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/241), [#308](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/308), [#938](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/938), [#1076](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1076), [#1064](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1064), [#1071](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1071), [#1073](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1073), [#1082](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1082)
- **實作 PRs：**[#127](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/127), [#147](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/147), [#158](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/158), [#173](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/173), [#185](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/185)

## 問題與限制

多個 agent 若共用 working directory，checkout、未提交檔案與工具狀態會互相污染；即使分用 worktree，GitHub PR 的 Ready／Draft、comments 與 merge 仍是共用控制面。若新 session 不查歷史，也會重做或反轉先前決策。遠端 Actions 無法清理本機 worktree，agent 自述也不能取代平台 evidence。

GitHub Agents 頁籤可把 repository 工作交給 cloud coding agents，但 session 會依模型與處理 token 消耗 AI credits，並使用 GitHub Actions minutes。目前沒有實測證據顯示這項額外用量能抵銷既有本機 agent 與 GitHub delivery loop 的成本。

## 決定

- 每個平行可寫任務使用獨立 branch 與 worktree，只平行處理可分離範圍；PR、CI 與最終整合仍是共同門禁。
- 建立工作前以 2–4 個具體詞限量搜尋 open／closed Issues，閱讀 body、comments 與 linked PR；在新 work item 記錄沿用、取代或駁回。
- Durable constraint 經使用者確認後摘要進 Issue，再由 scoped PR 更新 decision record；不保存 raw conversation 或 unconfirmed inference。
- Agent 預設在非雲端同步的本機檔案系統操作 active checkout、worktree、environment 與 cache。若起始路徑由 File Provider 管理，例行工作不要求使用者額外確認或設定；agent 改用本機 checkout 並保留既有變更。
- 建立 worktree 的 agent 在 merge／abandon 後負責 scoped 安全清理；每次 agent 啟動只讀 worktree metadata，不執行全 repo 內容與網路掃描。全域 dry-run 保留為明確的 repository maintenance。
- Delegated agent 執行範圍內檢查並回報；PR owner 或 integrating agent 對每個最終 candidate tree 執行一次完整驗證。
- 本機驗證證據只在 `verification_mode: local` 成立：以 exact head、tree、base、tier、scope 與 freshness 綁定的 `self-attested-local` evidence，由 merge lifecycle 重驗後走有 trace 的 admin bypass（#908、[#1073](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1073)）；hosted 模式仍以 required `verify` 為唯一正常 merge evidence。原本「quota-only 條件＋human authorization」的本機 attestation 已隨 quota fallback 退役（#1071）。
- GitHub Issue、PR、review 與 CI 維持協作與治理基線；Agents 頁籤已評估但暫不納入，不新增 setup workflow、custom agent 或 repository policy。
- PR lifecycle 寫入以 repository remote ref 作 atomic single-writer lease；每張 PR 同時取得依 destination branch 決定的 lane lease。Lease 綁定 PR、base、完整 head SHA、期限與不公開的隨機 capability；只有可驗證的過期 lease 可被 atomic 回收。Agent 的 Ready／Draft、label／milestone、authorization preparation 與 merge 一律走 `scripts/pr_lifecycle.py`，其他 task 維持唯讀；無法在取得精確 PR/head 前綁定 lease 的 Release Please writer fail closed 為 human-only。
- Merge 前在 lease 內重讀 live timeline、comments、reviews、checklists 與 effective Ruleset。無法證明 review、last-push approval、required checks 與 no bypass 時，agent 不合併；GitHub Free private 的 fallback 是 human-only manual merge，唯一例外是下方 #1076 的 audited single-writer route。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | Native `git worktree` 是 portable isolation baseline；manager 僅為選配 | [#126](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/126)／[#127](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/127) |
| Preserved | 以 bounded GitHub history search 取代第一版向量／語意資料庫 | [#145](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/145)／[#147](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/147) |
| Rejected | Agent 自動保存完整聊天或把推論升格為決策 | [#177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/177)／[#185](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/185) |
| Preserved | Actions 無法替代 agent host 上的 worktree cleanup | [#155](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/155)／[#158](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/158) |
| Superseded | 每個 agent 啟動時全域掃描所有 worktree；實測在 43 個 worktree 與 File Provider 路徑下無界卡住，改由 creator-scoped cleanup 與明確維護取代 | [#204](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/204)／[PR #210](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/210)／[#308](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/308) |
| Preserved | Worktree isolation 不涵蓋 GitHub control plane；以遠端 PR／promotion lease 補足 | [#240](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/240) |
| Superseded（部分） | Free private 一律 human-only manual merge；API 完整讀回恰好一個寫入者時改走 audited single-writer route | [#1076](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1076) |

## Ownership 與驗證

`AGENTS.md` 是 agent workflow source；`docs/README.md` 是 memory map；spec 與 decision files 是內容來源。Worktree cleanup 用本機 fixture 驗證，PR lease 以兩個 process 競爭相同 remote ref 及 #236／#237 lifecycle drift fixtures 驗證。任何 agent handoff 都應交代 branch、SHA、verification 與尚未完成限制。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 多 agent 共用一個 working directory | 不採用；branch 無法隔離未提交狀態 |
| 強制安裝 Worktrunk／特定 orchestrator | 不採用作 baseline；native Git 必須可用 |
| 用背景 daemon 或 Actions 清本機 worktree | 不採用；遠端看不到 agent host，隱式刪除風險高 |
| 每個 agent 啟動時掃描全 repo worktrees | 不採用；成本隨 worktree、檔案 I/O 與 GitHub API 呼叫無界增加 |
| 在 cloud-synced File Provider 路徑操作 active repository | 不採用；placeholder hydration 與同步衝突不符合 Git 所需的穩定本機 I/O |
| 只靠 agent 記憶先前對話 | 不採用；session 與工具切換後不可依賴 |
| GitHub Agents 頁籤作為預設執行層 | 暫不採用；會增加依 token 計價的 AI credits 與 Actions 用量，現階段沒有成本效益證據 |
| 只用本機 lock file 或 worktree 路徑互斥 | 不採用；無法涵蓋另一個 process、host 或 GitHub client |
| 在 Free private 把 shared admin credential 視為 Ruleset | 不採用；repository-local tool 無法阻止刻意繞過，agent merge 必須停止 |

## 2026-09-23 Soft finalization queue 與完成邊界（#938）

平行工作繼續使用各自的 branch／worktree，實作與 focused checks 不互鎖。只有會被
upstream base、版本或共同治理檔案作廢的 finalization window，才依 destination base
排序：current-base sync、release materialization、一次 local full、Ready、hosted exact-head
verify、merge 與 release readback。共用 parent 的 subagents 先以
`READY_TO_FINALIZE` 訊息讓 parent 排序；沒有共同 parent、但位於同一 clone 的 sessions
使用 `scripts/finalization-queue` 在 Git common directory 公告有期限的 intent。等待者讓出
執行資源，不做 busy polling。

這個 queue 明確不是 lock：它不阻擋任何 Git 或 GitHub 命令、不授予 merge 權限、逾時後
自動不列入排序，也無法協調不同 clone。遠端 Ready／Draft／metadata／authorization／merge
仍一律由 #240 的 `pr_lifecycle.py` lease 與 live-state revalidation 保護。這保留跨 host 的
安全邊界，同時避免用長效鎖讓另一位協作者陷入無法解釋的等待。

未被使用者縮限的「實作／修正 Issue」以 post-merge closeout 為預設終點。Agent 只有在
確認 exact merge、Issue 狀態、configured release 或明確 no-release 結果與 readback、來源
branch／lease、本機 worktree，以及 final report 後才能回報 `DONE`；外部條件未完成時回報
`WAITING`，無安全進展時才回報 `BLOCKED`。Worker 最後回報 `ARCHIVE_READY` 並退出或 yield，
由 parent／client 在 final report 後封存。這遵守 OpenAI Docs 的平台邊界：`/agent`／
`/subagents` 可切換 spawned threads，而 `/archive` 在 task 執行中不可用，封存不能由同一個
仍在執行的 turn 冒充完成。官方說明：
<https://learn.chatgpt.com/docs/developer-commands#cli-archive-the-current-session-with-archive>。

不採用 background daemon、強制本機 mutex、輪詢服務或第二套 release／cleanup 工具；
這些方案會增加卡死與狀態漂移面，且沒有比短期 advisory intent 加現有遠端 lease 提供更多
可信保證。

## 2026-10-14 單一寫入者的可稽核 merge 路徑（#1076）

擁有者在 #1058 決定 10 與 27 確認：沒有 Ruleset 強制（`server_enforcement=none`）時，只有 API 完整、分頁讀回
觀察到恰好一個寫入者，而且就是合併者本人，lifecycle 才可合併；agent 以這位唯一維護者的身分執行，不另建
write 帳號。另有寫入者為 `multiple-writers`，任何讀取不完整（權限不足、分頁不完整、team 成員不可見、缺
`role_name`）為 `inconclusive`，兩者都只能人工合併並記為 untraced，`csarc-owned` 發版 fail closed。有 Ruleset
強制時，agent 使用獨立 write 身分且不持有 maintain／admin：一般 agent route 以即時 `role_name` 驗證合併者恰為
`write`，其他或讀不到的角色都拒絕；admin bypass 與 emergency hotfix 的合併者是 live admin 授權者本人，
維持允許，並在 trace 記為 `identity=admin-authorizer`，與獨立 agent 身分路線區分。

這不是 Ruleset 的替代品：trace 明記 `server_enforcement=none` 與 trust，不宣稱伺服器曾經阻擋；exact-head
授權、required checks、lease、verified tree 與 G4 durable trace 都不略過（#918、#908、#1073 保留）。上方
「shared admin credential 視為 Ruleset」的駁回維持不變：single-writer 路線不共用憑證，只在讀回能證明沒有其他
寫入者時成立。路由表與 local Dependabot route 見 `docs/ci-policy.md`「單一 maintainer 的可稽核合併路徑
（#1076）」。

重新評估條件：GitHub 提供可讀的 App 安裝寫入者清單、Free private 的 `rules/branches` 行為經 live 驗證，或
單人維護的 repository 升級到可強制 private Ruleset 的方案。

## Copilot code review 作為可選審核路徑（#752，2026-09-18）

現行契約：審核意圖只有 `admin_bypass: off|beta-only|always` 與 `copilot_review: allowed|off`（[SPEC-009](../specs/SPEC-009-project-settings.md)、[`simplified-project-configuration.md`](simplified-project-configuration.md)）。Ruleset 只有 A（hosted）、E1（local＋`beta-only`／`always`）與 C（local＋`off`）三種形狀；Copilot 對 exact head 的乾淨審核只在 0 個原生必要核准的 A／E1 形狀、而且 PR 沒有有效 admin-bypass 標記時才是 `review` 證據，其他情況與 `copilot_review: off` 相同（[#1082](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1082)，#1058 決定 4–6）。`review` check、`review_gate.py status` 與 `pr_lifecycle.py merge` 共用同一個判定。規則細節見 `docs/ci-policy.md`「Copilot 審核模式（#752）」與「單一 maintainer 的可稽核合併路徑（#1076）」。

#752 的 exact-head 證據與 fail-closed 行為保留；其餘原文已被 #900、#918 與 Milestone 18 取代，只留下列歷史處置。

| 狀態 | 原決策 | 處置與取代者 |
| --- | --- | --- |
| Superseded | 新增 `pr_review_mode`（`copilot`／`human`）與 `copilot_review_max_level`；新專案、`csarc adopt` 與本 repo 預設 `copilot`，`copier update` 對既有專案預設 `human` | [#900](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/900) 改為 `copilot_review`（`allowed`／`off`）；舊鍵由 SPEC-009 migration 轉換（`copilot` → `allowed`，有 level cap 時收窄為 `off`） |
| Superseded | #900 曾以 `review`（`solo`／`peer`）表示自審或同行審核 | `review` 已退役（SPEC-009 §3，[#1064](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1064)、[#1071](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1071)）：`solo` 等價 `admin_bypass: always`，`peer` 等價 `off` |
| Superseded（narrowed） | Copilot 模式下 Ruleset 自動請 Copilot 審核，Copilot 沒有意見即可通過 `review` | `copilot_review: allowed` 仍加入 `copilot_code_review` 規則，但 Copilot 證據只在 A／E1 形狀成立；C 形狀或有 admin-bypass 標記時不採用（[#1082](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1082)） |
| Preserved | `review` 接受 Copilot 對 exact head 沒有意見，或獨立 maintainer 對 exact head 的 approval；本機 agent 修正意見後由 `scripts/pr_lifecycle.py` 在 lease 下合併並留痕 | #752；合併者角色另依 #1058 決定 27 判斷 |
| Preserved（部分取代 #241） | Copilot code review 納入可選基線並消耗 premium requests；GitHub Agents 頁籤與 Copilot coding agent 仍暫緩，修正者仍是本機 agent | #752 |
| Superseded | #745 以 `copilot_review_max_level` 設定 Copilot 可通過的層級上限 | #900 移除 level cap；[#918](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/918) 以 beta／stable 雙通道與 `admin_bypass` 取代 per-level 設定 |
| Preserved | #719、#240：exact-head 真人 approval 仍是合併授權，lease、live state 重驗與 fail closed 同樣適用於 Copilot；#557：不採用原生 auto-merge 或 workflow 合併 | #752 |

重新評估條件：Copilot 審核品質或費用不可接受，或 GitHub 改變 Copilot review 的 API 形狀（例如不再以內文說明「沒有意見」）時。

## 重新評估條件

若 host platform 提供有 ownership、dirty-state 保護與可稽核 lifecycle 的原生 worktree 管理，可替代部分本機步驟；GitHub work item、repository memory 與合併門禁仍保留。若每個 automation 取得獨立最小權限 GitHub App identity，或 GitHub 提供可原子更新的原生 PR lease，可取代目前以 remote ref 與 audit comment 組成的互斥層。

當真實 backlog 出現足量、可獨立驗收的非同步工作，且可先訂出 AI credits／Actions 成本上限，再驗證 Agents 產生的 branch 與 PR 能通過本 repo policy 時，重新評估把 Agents 頁籤列為升級執行層。
