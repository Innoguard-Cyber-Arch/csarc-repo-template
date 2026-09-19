# Capability-aware GitHub governance ADR

- **狀態：**Accepted
- **日期：**2026-08-25
- **來源 Issues：**[#18](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/18), [#28](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/28), [#62](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/62), [#65](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/65), [#87](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/87), [#123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123), [#146](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/146), [#163](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/163), [#199](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/199), [#240](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/240), [#254](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/254), [#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287), [#300](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/300), [#301](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/301), [#576](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/576), [#580](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/580), [#607](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/607), [#719](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/719), [#531](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/531), [#325](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/325), [#775](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/775)
- **實作 PRs：**[#25](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/25), [#59](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/59), [#63](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/63), [#66](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/66), [#90](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/90), [#128](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/128), [#154](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/154), [#165](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/165), [#306](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/306), [#579](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/579), [#663](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/663)

## 問題與限制

GitHub plan、visibility、organization policy、actor role 與 workflow token scope 會讓相同宣告在不同 repo 有不同可用性。403／404 也可能代表缺權限，而不是能力不存在。

## 決定

所有平台相依能力使用 `allowed`、`blocked`、`unknown` 三態。先保存 desired policy，再用 plan／apply／check 或 runtime probe 取得可觀察證據；只有 allowed 才啟用較強自動化。Blocked／unknown 採最安全可攜 fallback，且必須清楚顯示限制。

Free private repository 無法強制 Ruleset 或 team review 時，仍執行 repository-local checks、保留 desired policy 並輪派一位個別 reviewer，但標示 `DEGRADED`，不能宣稱有平台 merge gate。Portable baseline 不要求 PAT、GitHub App 或 organization policy 變更。

Projects 預設關閉；工作階層使用 GitHub 原生 Issue Type、subissue、dependency、Milestone 與 Development link。Issue Type 不可用時才退回 labels，並明示 degraded；不得用自訂 Project 欄位製造第二套狀態來源。

Hosted runner 同樣視為可觀測的平台能力：可用時收集 telemetry，受限或未知時保留誠實狀態與適用的本機驗證。不要求管理員調整帳單、升級方案或維護額外 runner 才能完成 portable 交付。

Public 轉換後 Ruleset 的 `require_code_owner_review`／`required_approving_review_count` 第一次真正生效，暴露 `Innoguard-Cyber-Arch` 目前結構性只有一個真人帳號、無法核准自己 PR 的問題（GitHub 全站限制，非本 repo 政策）；`gh pr merge --admin` 對 Ruleset 也不像舊版 classic branch protection 那樣自動取得 admin 身分繞過。2026-09-03 維護者在對話中明確授權，對 live ruleset（id `22178328`）加入 `{"actor_type": "RepositoryRole", "actor_id": 5, "bypass_mode": "pull_request"}`——`actor_id: 5` 經實測確認對應 repository admin 角色（以角色設定，不綁特定帳號）。同日稍後實測發現這個 bypass 涵蓋範圍比原本以為的更廣：`bypass_mode: "pull_request"` 不只放寬 review，也一併放寬 `required_status_checks` 規則本身，等於「alpha 期間 PR 相關規則全部不擋」；不影響 `non_fast_forward`。這個 bypass 已寫回 `policies/rulesets.json`（root）追蹤，具體程序與範圍見 `docs/ci-policy.md`「Alpha 自我核准 bypass」一節；`template/` 的 `bypass_actors` 刻意保留空白，不預設下發給下游生成 repo。是否長期保留、何時移除，由維護者決定，見 #580。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | 不可辨識的 capability error fail closed | [#18](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/18)／[#25](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/25) |
| Superseded | 缺少付費 Ruleset 時讓所有 CI／release 永久失敗 | [#62](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/62) → [#65](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/65)／[#66](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/66) |
| Preserved | Desired policy 留在 repo，live enforcement 另行驗證 | [#87](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/87)／[#90](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/90) |
| Rejected | 為 portable baseline 要求長效 PAT／額外 App 或繞過組織政策 | [#123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123)／[#128](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/128) |
| Superseded | Hosted Actions 必須由管理員恢復才能完成交付 | [#199](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/199) → [#254](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/254)／[#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287) |
| Preserved | `security_and_analysis` 獨立 PATCH，避免 GHAS 受限時拖累同一請求的基本設定；REST 沒有的 `issue_creation_policy` 改走專屬 GraphQL 區塊，而不是塞進會靜默忽略未知欄位的扁平 PATCH | [#576](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/576)／[#579](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/579) |
| Preserved（alpha 限定） | 單一真人帳號 org 撞上 GitHub 平台自我核准限制時，用 Ruleset `bypass_actors`（`RepositoryRole` admin、`bypass_mode: pull_request`）解除，寫回 root `policies/rulesets.json`；`template/` 保留空白，不預設下發 | [#580](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/580) |
| Superseded | 一般 PR 已有 exact-head 獨立 maintainer approval 時仍要求第二則授權留言；review 本身即為該 SHA 的授權，後續 push 自動失效 | [#240](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/240) → [#719](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/719) |
| Superseded（narrowed） | Alpha self-merge 排除 default-branch 的邊界縮小為僅放寬審核（Milestone-less Issue 才適用，quota-fallback 不變）；`effective_protection` 信任的授權來源擴大納入 alpha self-merge 自己的 exact-head comment，修正它此前從未能讓 `pr_lifecycle.py merge` 真正成功的既有缺口 | [#325](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/325)／[#719](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/719) → [#775](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/775) |

## Ownership 與驗證

Repository 保存 desired policies；有管理權的 operator 決定是否 apply。PR code 不取得 administrator token。`apply-repository-settings.sh check` 分項比較可觀察狀態，actionable drift 失敗、結構性限制降級，排程結果不能把 degraded 寫成 aligned。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 只依 GitHub plan 名稱猜能力 | 不採用；organization policy 與 token scope 仍可能阻擋 |
| 所有未知狀態都放行 | 不採用；會把缺權限誤當已啟用 |
| 所有缺能力都永久阻擋 | 不採用；portable baseline 在 Free private 會永遠不可交付 |
| 提前導入 Safe Settings／Allstar | 延後；fleet 規模與漂移頻率尚未達門檻 |

## 2026-09-03 release_phase 收斂 Alpha 自我核准 bypass 範圍（#607）

#580 記錄並落地了目前 live 已套用的 Ruleset self-approval bypass（`RepositoryRole`
admin、`bypass_mode: "pull_request"`，寫回 root `policies/rulesets.json`），同時發現
它的實際涵蓋範圍比原本以為的更廣：因為 GitHub 的 `bypass_actors` 綁在整個 Ruleset
上、不是單一 rule type，這個 bypass 連 `required_status_checks` 都一併放寬，等於
「alpha 期間 PR 相關規則全部不擋」。#607 的問題：這個較寬的涵蓋範圍不能是永久、不分
專案發展階段的事實，尤其是 required_status_checks 這種「必要檢查真的有沒有過」的
保證，不該無限期依賴人工自律。

維護者的決定：把這個 bypass 的權限範圍綁定專案自己的發布階段
（`release_phase`：alpha／beta／release），而不是一個固定不變的設定。`release_phase`
寫在新增的 `policies/project-stage.json`，是人工宣告的單一權威來源（不像
`governance_stage` 或 `profiles/catalog.yaml` 的 `stage` 那樣分類單一 PR 或單一
profile——三者刻意保持不同軸線，避免命名碰撞，完整區分見
`scripts/release_phase_rulesets.py` 的 module docstring）。GitHub Ruleset 的
`bypass_actors` 是 Ruleset 層級欄位，要讓「review 可以 bypass、
required_status_checks 不行」同時成立，落地把兩種規則拆進兩個 Ruleset
（`policies/rulesets.json` 與新增的 `policies/rulesets-required-checks.json`），由
`scripts/apply-repository-settings.sh`（透過 `scripts/release_phase_rulesets.py`）
依 `release_phase` 決定 `required_status_checks` 規則實際生效在哪個 Ruleset：alpha
併入帶 bypass 的那個，beta 起強制留在永遠空 bypass 的那個。release 階段的自動失效是
結構性保證：`scripts/check-bypass-lifecycle`（已接進 `./scripts/verify-fast`）fail
closed 擋下「`release_phase` 是 `release` 但任一 Ruleset 仍有非空 `bypass_actors`」
這個狀態，不依賴人工記得清空。alpha／beta 期間每次實際使用 bypass 合併 PR，也新增
`bypass-trace:` 結構化留言的使用留痕要求，以及 `scripts/check-bypass-trace` 可執行的
查核工具（比對邏輯在 `scripts/check_bypass_trace.py`）。

對既有或人工合併 PR 自動判斷「哪些 PR 真的用了 bypass」（交叉核對
review／required-check 實際狀態）維持未實作：`scripts/generate_audit_trail.py`
（#535／#564）尚未併入 `main`，是獨立進行中
的 Milestone 13 work，#607 刻意不依賴它，改成 operator 針對已識別的單一 PR 主動查核
（跟 `scripts/check-pr-policy-status` 的用法一樣）；一旦該模組併入，可以再擴充做自動
交叉核對。這整套機制與 #580 一樣是 root-only：`template/policies/rulesets.json.jinja`
刻意保留空的 `bypass_actors`，不帶 `policies/project-stage.json` 或第二個 Ruleset
檔；`scripts/apply-repository-settings.sh` 對這兩個新政策檔案的存在與否是條件式
判斷，檔案不存在時（所有既有下游 repo）行為與 #607 之前完全一致。

**部分取代（Issue #744，2026-09-17）：** 上面「`release_phase` 是人工宣告的單一
權威來源」本身不變，`policies/project-stage.json` 與這裡描述的兩個 Ruleset
bypass 機制也繼續照原樣運作，不受 #744 影響。但 #744 的維護者決定改變了這件事
背後的假設：版本號現在直接表示發布層級，alpha／beta 可以在任何時候發布（包含
在早期版或正式版之後），不再是「一段只會往前走、走到 release 就結構性消失」的
一次性期間；本節第一段暗示的單向前進假設因此不再普遍成立於版本號本身（本節
`release_phase` 三值與其 Ruleset bypass 範圍仍是獨立、不受影響的另一條軸線）。
審核與測試依發布層級分級、是否需要調整或取代本節的 bypass 機制本身，是 #745
的範圍，本節在 #745 落地前維持現狀。詳見
`docs/adr/release-security-and-dependencies.md`「版本號表示發布層級與保留規則
（#744）」一節。

## 2026-09-09 exact-head review 直接授權 lifecycle merge（#719）

#240 建立的 remote lease、CAS 與 merge 前 live revalidation 保留，但一般 PR 不再要求
maintainer 在 `APPROVED` review 之外另貼內容重複的授權留言。獨立 human maintainer 的
review 只有在 GitHub 回報其 `commit_id` 精確等於目前 head SHA、reviewer 仍有
`maintain`／`admin` 權限、不是執行 merge 的帳號，而且目前 decisive review 狀態仍是
`APPROVED` 時，才直接成為合併授權；後續 push 換 SHA、`CHANGES_REQUESTED`、Draft、
blocking comment、未完成 checklist 或 check failure 都會阻擋。Alpha 無獨立 reviewer
的 self-merge 例外維持 #325 的 lease 後 exact-head comment，不混入一般路徑。

本 repo 的 alpha Ruleset 有 #580 的已知 admin `pull_request` bypass。Lifecycle 只在 live
bypass actor 清單精確等於已宣告值、上述 exact-head review 成立、必要 checks 重驗成功，
且 GitHub 回報 PR `mergeable_state=clean` 時才可自動合併；未知或擴大的 bypass 仍是
human-only。使用已知 bypass 時，lifecycle 會在最後一次 merge snapshot 前自動留下
#607 定義的 `bypass-trace:`，讓 reviewer 的同意與實際 bypass 使用各自有可稽核證據。

## Repo 能力矩陣：把「這個 repo 本身」也納入 capability preflight（#531）

上方所有 disposition 都聚焦在 GitHub *方案*（Free／Team／Enterprise）能不能支援某項
能力，由 `scripts/apply-repository-settings.sh` 的 plan／apply／check 偵測。Issue #531
指出這不是唯一變因：同一個方案下，organization 政策、CODEOWNERS team 是否存在且可寫、
token 權限範圍，仍可能個別擋住 `ruleset_enforcement`、`codeowners_enforcement`、
`actions_pr_approval` 這類能力，而這一層過去沒有集中定義、也沒有自動檢查。

維護者的決定：新增 `policies/capability-matrix.json` 作為聲明式的「repo 能力矩陣」，
把每一項能力對應到最低權限／方案需求、偵測方式與 workaround；`scripts/
repo_capabilities.py` 是可獨立單元測試的三態（`allowed`／`blocked`／`unknown`，延續本
ADR 第 14 行既有的三態慣例）evaluator，`scripts/check-repo-capabilities` 是即時對這個
repo 探測、組成 facts 後交給 evaluator 的唯讀入口，只回報缺口與對應 workaround，不寫入
GitHub、也不是新的合併關卡（那仍是 `apply-repository-settings.sh check` 的工作）。
repo-site「安裝說明」頁的維運模式新增雙語能力矩陣說明框（`docs/index.html#install`；
Issue #681/#682 決定 R 前是獨立的「進階安裝」附錄頁，後併入 install 頁的 Ops 面板）
說明矩陣內容與如何解讀檢查結果；`docs/ci-policy.md`「Repo 能力自我檢查與 workaround
對照」一節記錄同一決定的執行細節。

明確保留的邊界：這套機制不重新設計 `apply-repository-settings.sh` 既有的 `DEGRADED`
標記——矩陣裡對應既有限制的每一列，workaround 直接引用同一段既有訊息，不是另建一套
平行說法；`apply-repository-settings.sh` 本身在這個 Issue 沒有任何邏輯變動。

## 2026-09-18 修正 alpha self-merge 對 main 與既有 bypass_actors 的排除（#775）

修復 #757（GraphQL schema drift）合併 PR #765 時發現：`scripts/pr_lifecycle.py merge`
對任何直接合併進 `main` 的 alpha PR 一律失敗，導致 #758／#759／#762／#763／#765 全部
繞過 `merge()` 本身、只借用其 `acquire`／`authorization-template`／`release` 子指令
留痕，實際合併改用手動 `gh pr merge --admin --squash` 加人工現場打字的
`bypass-trace:` 留言——這已經悄悄違反 `AGENTS.md` 工作迴圈第 12 步「合併寫入一律要
透過 `scripts/pr_lifecycle.py`」。查證找到兩個各自獨立、都需要修正才能讓這條路徑真
的可用的原因：

1. `alpha_self_merge_opt_in` 依賴的 `require_routine_route`（與 #325 的 Actions
   quota/billing 必要檢查 fallback 共用）在 `base_ref == default_branch` 時直接
   raise。#325 完成條件明寫「default-branch promotion、hotfix 與 Release
   eligibility 不得因這個 fallback 放寬」，但這是 2026-09-03 就存在的既有邊界，早於
   2026-09-18 才確認的「這個 repo 的 Copilot code review 永久不可用」這個事實。維護
   者本次決定：narrow 這個邊界，只放寬審核繞過（不動 `require_routine_route` 本體，
   新增平行的 `require_default_branch_issue_route`，額外要求該 Issue **不得**掛
   Milestone——有 Milestone 的仍須走自己的 `dev/mN` 分支）；`require_routine_route`
   ／quota-fallback 對 default-branch 的禁止完全不變。
2. 更深層的問題：`effective_protection`（#719 導入）只在 `authorization_source in
   {"review", "copilot"}` 時，才把 live Ruleset 的非空 `bypass_actors` 當作「已驗
   證」；alpha self-merge 的 `authorization_source` 是 `"comment"`，不在這個集合
   裡。本 repo 正式 Ruleset（`rulesets/22178328`）目前同時具備：`pull_request` 規則
   直接宣告 `required_approving_review_count: 0`（`pr_review_mode: copilot` 的既
   有設定）**與** #580 的 admin `pull_request` bypass_actors——兩者原本各自為了不同
   目的加入，#719 制定「只信任 review／copilot」的規則時沒有預料到會同時出現在同一個
   repo。結果是 alpha self-merge（不分 main 或既有 `dev/mN` 路由）在這個 repo 從未
   真的能讓 `pr_lifecycle.py merge` 跑出 `merge_mode == "agent"`——每次都在
   `effective_protection` 這步被「an effective Ruleset permits an unverified
   bypass」擋下，只能退回手動合併。維護者本次決定：把 `"comment"` 併入這個信任集合
   （`authorization_source in {"review", "copilot", "comment"}`）——exact-head 授
   權留言本來就已經被 `authorization()` 獨立驗證（maintainer 權限、精確 body、精確
   head SHA），信任基礎跟 review／copilot 對等，且 `bypass_actors` 是否精確等於已宣
   告值的檢查完全不變，只是把可以通過這項檢查的授權來源多加一種。
3. 第三個獨立問題：即使前兩項都修好，GitHub 自己回報的 `mergeable_state` 也永遠不會
   是 `clean`——因為 `review` 這個 required check（`scripts/review_gate.py` 的
   `evaluate()`）只認真人 `APPROVED` review 或乾淨 Copilot review，完全不知道
   alpha self-merge 這條路徑的存在，對任何 alpha self-merge PR 永遠回報
   `failure`。`merge_snapshot` 自己那行 `if reviewed_bypass and
   mergeable_state != "clean": blocked` 因此永遠擋下，不管前兩項修正對不對。
   維護者本次決定：也讓 `evaluate()` 認得 alpha self-merge——新增
   `pr_lifecycle.find_exact_head_authorization`（掃描全部留言找出綁定目前 head
   SHA、通過 maintainer 權限驗證的授權留言，不像 `authorization()` 需要呼叫方先
   指定一則特定留言的 URL），`evaluate()` 在 Copilot 未過、無真人 approval 時，
   改用跟 `alpha_self_merge_opt_in` 相同的 marker／route 判斷（不含 release_phase
   檢查——`alpha_self_merge_opt_in` 本身也不檢查 release_phase，兩處各自加只會讓
   `review` check 跟 `pr_lifecycle.py merge` 對「這個 head 能不能合併」的判斷互相
   矛盾）＋這則留言是否存在，成立就一併通過。`.github/workflows/pr-review.yml`
   同步加上 `issue_comment: created` trigger（篩選 PR 上、開頭是 `PR lifecycle
   merge authorization` 的留言）：貼授權留言本身不會觸發 `pull_request` 事件，
   沒有這個 trigger 就要手動 `gh run rerun` 才會重新檢查。

三項修正都只動 `alpha_self_merge` 這條路徑本身；`require_routine_quota_fallback`
（quota/billing 必要檢查 fallback）與一般 `review`／`copilot` 授權路徑的既有行為完全
不變。root／`template/` 的 `scripts/pr_lifecycle.py`／`scripts/review_gate.py`／
`.github/workflows/pr-review.yml`／`tests/test_pr_lifecycle.py` 保持逐位元組同步
（`tests/test_review_gate.py` 不在配對清單內，只在 root 維護）。

## 重新評估條件

Repository 方案、organization policy、fleet 規模或實測 drift 頻率改變時，重新執行 capability preflight 與 fleet threshold review；不要把安裝時快照當永久真相。

`Innoguard-Cyber-Arch` 出現第二個真正的 human collaborator 後，重新檢視 Ruleset `bypass_actors` 的 admin self-approval 例外是否仍需保留；這是維護者的治理決定，不由本 ADR 預設方向（見 #580）。
