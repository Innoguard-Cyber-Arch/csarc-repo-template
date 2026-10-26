# Capability-aware GitHub governance ADR

- **狀態：**Accepted
- **日期：**2026-08-25
- **來源 Issues：**[#18](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/18), [#28](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/28), [#62](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/62), [#65](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/65), [#87](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/87), [#123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123), [#146](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/146), [#163](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/163), [#199](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/199), [#240](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/240), [#254](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/254), [#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287), [#300](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/300), [#301](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/301), [#576](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/576), [#580](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/580), [#607](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/607), [#719](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/719), [#531](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/531), [#325](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/325), [#746](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/746), [#775](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/775), [#826](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/826), [#918](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/918), [#932](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/932), [#1064](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1064), [#1071](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1071), [#1073](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1073), [#1076](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1076), [#1080](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1080), [#1082](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1082)
- **實作 PRs：**[#25](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/25), [#59](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/59), [#63](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/63), [#66](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/66), [#90](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/90), [#128](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/128), [#154](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/154), [#165](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/165), [#306](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/306), [#579](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/579), [#663](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/663)

## 問題與限制

GitHub plan、visibility、organization policy、actor role 與 workflow token scope 會讓相同宣告在不同 repo 有不同可用性。403／404 也可能代表缺權限，而不是能力不存在。

## 決定

自 #918 起，admin bypass 與發布成熟度解耦。`.csarc/config.yml` 的
`admin_bypass: off|beta-only|always` 是唯一現行設定；本 repo 使用 `always`，生成專案
預設也是 `always`（#1064）。即使是 `always`，required checks、path-risk 升級、可信證據、remote lease、
即時 admin 權限與 exact-head 授權都不能省略。`project_maturity: early|formal` 只靠明確
standalone stable 宣告改變，不能自動開啟或關閉 bypass。這項決定取代下方把 bypass
稱為 alpha 階段暫時措施的敘述；下方內容保留為歷史脈絡。

所有平台相依能力使用 `allowed`、`blocked`、`unknown` 三態。先保存 desired policy，再用 plan／apply／check 或 runtime probe 取得可觀察證據；只有 allowed 才啟用較強自動化。Blocked／unknown 採最安全可攜 fallback，且必須清楚顯示限制。

Free private repository 無法強制 Ruleset 或 team review 時，仍執行 repository-local checks、保留 desired policy 並標示 `DEGRADED`，不能宣稱有平台 merge gate。合併路線依 live 讀回決定，不再以「輪派一位個別 reviewer」作為 fallback（[#1076](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1076)，#1058 決定 4、5、10、27）：沒有 Ruleset、API 完整讀回恰好一個寫入者而且就是合併者時，走 audited `single-writer` route（`server_enforcement=none`）；另有寫入者時，有 exact head 的獨立 maintainer approval 才走 audited `independent-approval` route（[#1211](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1211)），否則與任何讀取不完整時一樣只能人工合併，記為 `untraced`。reviewer 仍可由 live `maintain`／`admin` collaborator best-effort 選取（SPEC-009），但這不是合併授權。Portable baseline 不要求 PAT、GitHub App 或 organization policy 變更。

工作階層使用 GitHub 原生 Issue Type、subissue、dependency、Milestone 與 Development link。Issue Type 不可用時才退回 labels，並明示 degraded。GitHub Project 是選用的 Roadmap 檢視：只有設定 `github_project_url` 時，受管入口才同步 `Project start`／`Project target` 日期，空值時完全不呼叫 Project API、`has_projects` 維持 `false`（[#1080](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1080)，SPEC-009 §10，#1058 決定 23）；Project 欄位不是工作狀態的第二來源。

工作 branch 由 repo-local `gh-issue-develop` 在建立遠端 ref 前驗證 canonical 名稱與
Issue 編號；錯名 ref 只在同 repository、local／remote exact head 一致、目標名稱不存在
且尚無 open PR 時才能由同一入口修復。PR policy 維持唯讀，因為 GitHub 重新命名 open
PR 的 head branch 會關閉該 PR；不得用 workflow branch writer 偽裝成透明修復（#932）。

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
| Superseded（narrowed） | Alpha self-merge 排除 default-branch 的邊界縮小為僅放寬審核（Milestone-less Issue 才適用，quota-fallback 不變）；`effective_protection` 信任的授權來源擴大納入 alpha self-merge 自己的 exact-head comment；正式 delivery sync 後續也重用同一個完整 route 驗證與 exact-head 授權，不再被 issue-only allowlist 誤擋 | [#325](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/325)／[#719](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/719) → [#775](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/775) → [#826](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/826) |

## Ownership 與驗證

Repository 保存 desired policies；有管理權的 operator 決定是否 apply。PR code 不取得 administrator token。`apply-repository-settings.sh check` 分項比較可觀察狀態，actionable drift 失敗、結構性限制降級，排程結果不能把 degraded 寫成 aligned。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 只依 GitHub plan 名稱猜能力 | 不採用；organization policy 與 token scope 仍可能阻擋 |
| 所有未知狀態都放行 | 不採用；會把缺權限誤當已啟用 |
| 所有缺能力都永久阻擋 | 不採用；portable baseline 在 Free private 會永遠不可交付 |
| 提前導入 Safe Settings／Allstar | 延後；fleet 規模與漂移頻率尚未達門檻 |

## 2026-09 Alpha 自我核准與 self-merge 路線的歷史處置（#607、#719、#775、#826、#905、#913）

這些段落記錄 alpha 階段逐步放寬自我核准的過程，已由 [#918](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/918) 的 `admin_bypass: off|beta-only|always`（與 `project_maturity` 解耦，見本 ADR「決定」第一段）、[#900](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/900) 的設定收斂，以及 Milestone 18 的 quota fallback 退役（[#1071](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1071)）與單一 maintainer 合併路線（[#1076](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1076)）取代。現行規則見 `docs/ci-policy.md`「Copilot 審核模式（#752）」、admin bypass 與「單一 maintainer 的可稽核合併路徑（#1076）」各節；原文只留下列處置。

| 狀態 | 原決策 | 處置與取代者 |
| --- | --- | --- |
| Superseded | #607：以人工宣告的 `release_phase`（alpha／beta／release，`policies/project-stage.json`）決定 Ruleset bypass 範圍；release 階段由 `check-bypass-lifecycle` 要求清空 bypass；#744 曾部分取代其單向前進假設 | #918 以 `admin_bypass` 取代階段式 bypass，`project-stage.json` 已移除；beta／stable 只是發布通道，不再決定 bypass |
| Preserved | #607：GitHub `bypass_actors` 綁在整個 Ruleset，因此 required checks 放在沒有 bypass actor 的獨立 Ruleset（`policies/rulesets-required-checks.json`），review 規則才依設定包含 admin 角色；每次 bypass 合併留下 `bypass-trace:` | #607 → #918；trace 現在寫進每張 PR 唯一的 durable summary（[#1073](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1073)） |
| Preserved | #719：獨立 human maintainer 對精確 head SHA 的 `APPROVED` review 直接成為合併授權，不再要求重複授權留言；push、`CHANGES_REQUESTED`、Draft、未完成 checklist 或 check failure 都會阻擋 | #719；review 判定與合併者角色另依 [#1082](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1082)（#1058 決定 27）；核准獨立性由 [#1211](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1211) 修訂為只排除作者與最後 push 者 |
| Superseded | #719：alpha 無獨立 reviewer 的 self-merge 只在 live bypass actor 精確等於 #580 宣告值時自動合併 | #918 的 admin bypass route；Ruleset 形狀改依 A／E1／C 判斷（[#1082](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1082)、[#1076](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1076)） |
| Superseded（narrowed） | #775：alpha self-merge 可直接進 `main`（只限沒有 Milestone 的 Issue）、`comment` 授權納入 `effective_protection` 信任集合、`review_gate.evaluate()` 認得 exact-head 授權留言並由 `issue_comment` 重新觸發；同時保留 quota fallback 對 default branch 的禁止 | 路由與 exact-head 授權留言保留為 `admin_bypass_opt_in`（#918）；alpha 限定與 `require_routine_quota_fallback` 已隨 quota fallback 退役（#1071） |
| Superseded（narrowed） | #826：正式 current-main delivery sync 納入 alpha self-merge（allowlist `{"issue", "sync"}`） | 路由保留為 `admin_bypass_opt_in` 的 sync route（#918）；alpha 與 quota fallback 例外已退役 |
| Superseded（narrowed） | #905：同 repository 的 Milestone promotion 納入 alpha self-merge；拒絕替 required-check Ruleset 增加 bypass actor | promotion route 保留於 `admin_bypass_opt_in`（#918）；拒絕 required-check bypass 的結論不變 |
| Superseded（narrowed） | #913：canonical `release/v<semver>` Guided release 納入 `review: solo` fallback | `review` 已退役（SPEC-009 §3，[#1064](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1064)、[#1071](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1071)）；release route 保留於 `admin_bypass_opt_in`（#918） |

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

## 2026-09-20 下游治理漂移檢查改為預設啟用（#746）

在既有下游 repository 以目前 workflow、`GITHUB_TOKEN` 與公開 GitHub API 實測後，
每日治理漂移檢查改為新專案預設啟用；不引入 PAT、額外 GitHub App、secret 或專用測試
repository。明確不選 `governance-drift`（Issue #1071 起為 `scheduled_checks`；舊 `enable_governance_drift_check: false` 由 migration registry 對應）仍是支援的 opt-out，Copier
update 必須保留既有的 `false`，只在計畫中提供一次啟用建議與影響，不得靜默翻轉。

檢查結果維持能力感知語意：可讀且不符 policy 才是 actionable drift；目前 workflow
token 無法讀取的管理員設定標成 `DEGRADED`，不得宣稱 drift 或 aligned。真正 drift
只使用單一 tracking Issue；輸出未改變時不得 edit 該 Issue，避免每天重複通知。無法辨識
的 API 錯誤仍依本 ADR 既有決定 fail closed。

## 2026-09-20 隔離 PR policy 的治理寫入權限（#829）

`pull_request`／`merge_group` 會執行候選 revision 的 workflow 定義；即使後續 checkout
base SHA，也不能改變 job 已取得的 token 權限。PR policy 的 required `title`／
promotion route classifier 因此只能放在唯讀的 `title` job，並以原生 job conclusion 表達 policy 決策；
metadata 同步與 `Milestone approval` check-run 改由 default branch 上的
`workflow_run` 執行，固定 checkout 該次 trusted workflow 的 `github.sha`，不得 checkout
PR head、執行 PR source 或下載並執行 PR artifact。寫入 job 依 metadata 與 check-run
職責分開授權，避免任一 job 同時取得不需要的治理能力。PR 寫入目標必須由
`workflow_run` 的 head SHA、repository 與 branch 重新查詢所有分頁，只有唯一相符的
open PR 才能繼續；零筆或多筆都 fail closed。同一完整 head identity 的 writer 必須序列化，
不能讓重複事件並行留下重複治理寫入。

這項決定保留 #745 的發布層級、exact-head review、Alpha self-merge 與 required checks
規則；#742 後續將 workflow 縮成薄層或搬移 scripts 時，仍必須維持同一個 read-only／
trusted-writer 邊界，不能以路徑搬移取代隔離。

## 2026-09-20 將 required checks 綁定可信 producer（#835）

Ruleset 的 required status check 不再只保存顯示名稱；`title`、`verify`、
`review` 都綁定 GitHub Actions App integration ID `15368`。policy 缺少、無法解析或取得
非正整數 ID 時，設定 readback 與 merge lifecycle 一律 fail closed；classic commit
status 即使同名且成功，也不能滿足 required context。

GitHub Actions App 是所有 workflow 共用的 producer，單獨綁 App 仍不足以區分可信與
PR-controlled workflow。因此上述四個 required-name job 改由 base-trusted
`pull_request_target`（以及既有的 default-branch review／merge queue 事件）載入 workflow
定義；`pr_lifecycle.py` 除 exact head、name、App 外，也核對 Actions run 的 repository、
workflow path 與事件。PR 新增或修改的 `pull_request` workflow 即使使用相同 job name 與
共用 Actions App，也不能成為 lifecycle 的 required evidence。#829 的 privileged
`workflow_run` writer 邊界保留，並改為接收新的 `pull_request_target` policy run。

這項決定保留 #745 的 required context 集合與 no-bypass 原則、#826 的 Alpha delivery
sync self-review 路線，以及 #829 的唯讀 gate／trusted writer 分離；驗證證據本身的
不可偽造性仍由 #834 負責，不在本決定中以名稱或 App 綁定取代。

## 2026-09-23 將預期治理狀態與自動化故障分開（#933）

維護者確認，自動化不應為了「fail closed」而把所有尚未完成或已成功處理的狀態都回報
為 failure。狀態契約改為三類：尚待審核或重新核可用 pending；已滿足條件或已成功發布
決定／告警用 success；確定的政策違規、負面審核或執行／寫入錯誤才用 failure。

`pr-review.yml` 因而由可信 base workflow 的 publisher 建立 `review` check-run，而不再
直接拿 publisher job 的 conclusion 當審核結論。check-run 以 exact head、Actions run URL
與 `csarc-review:<run-id>:<head-sha>` external ID 綁定來源；`pr_lifecycle.py` 仍驗證 GitHub
Actions App、repository、workflow path、event 與 exact head。pending check 不滿足 Ruleset，
所以等待狀態沒有紅燈，也不會被誤當成可合併。

同一原則套用到 trusted PR-policy writer 與 release drift：approval 尚待核可時發布 pending，
writer 成功送出決定後自身成功；release drift 成功建立或更新追蹤 Issue 後自身成功。GitHub
API 或寫入失敗仍失敗。真實的 title／branch route／Issue binding 違規仍由 `title` 失敗，
原本 zero-step Actions quota 的 #325 明示例外已隨 quota fallback 退役（#1071），未執行的 required check 一律不能以合成成功掩蓋。

## 2026-09-23 保持治理升級後的 delivery sync 可用（#958）

正式 current-main sync 不是 work Issue 或新的發版邊界。可信 CI 必須先以 #812／#826 的
exact current-main、base/head、同 repository 與雙父 merge topology 驗證辨識 sync，才可
略過 #925 為 release-bearing work PR 設計的單父 release-only materialization；下一張真正
的 Milestone work PR 仍從同步後的 delivery tip 物化 beta。`pr_lifecycle.py merge` 在最後
合併邊界重用 `require_routine_route()` 再驗一次相同 topology，不以 branch prefix 單獨放行。

`pr-review.yml` 一般情況仍執行 PR base 的可信 publisher；只有正式 sync 需要把新治理帶進
較舊 delivery base，因此改由 GitHub API 解析 current default branch 的 commit 並執行其中
的 trusted publisher。該 publisher 仍用 exact head 與完整 sync route 判定，不能執行 PR
head 的 evaluator，也不會把等待或真正的政策錯誤改成成功。

## 2026-10-26 治理漂移排程改為每週一次（#1289）

生成專案的 `governance-drift.yml` 從每日改為每週一執行一次，時間避開同為週一的
`template-update.yml` 與 `osv.yml`。設定偏離不常發生，每天執行耗用 Actions 額度，
產生的結果也多半沒有變化。這項決定取代 #72／#75 與上方 #746 段落中「每日」的頻率；
#746 的預設啟用、opt-out 保留與 tracking Issue 語意不變。漂移最多晚六天才被排程發現，
需要立即確認時，用 `workflow_dispatch` 手動觸發，或執行
`./.csarc/scripts/apply-repository-settings.sh check`。`release-drift.yml` 是另一個檢查，
維持每日。

## 重新評估條件

Repository 方案、organization policy、fleet 規模或實測 drift 頻率改變時，重新執行 capability preflight 與 fleet threshold review；不要把安裝時快照當永久真相。

`Innoguard-Cyber-Arch` 出現第二個真正的 human collaborator 後，重新檢視 Ruleset `bypass_actors` 的 admin self-approval 例外是否仍需保留；這是維護者的治理決定，不由本 ADR 預設方向（見 #580）。
