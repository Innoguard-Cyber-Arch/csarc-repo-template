# Spec, story, and work-item boundaries ADR

- **狀態：**Accepted
- **日期：**2026-08-25
- **備註：**2026-10-19 依擁有者決定改為 Milestone 的「tracker → 主 Issue → 必要時 sub-Issue」結構（#1174），並補記 Issue 風險控制不另建需求資料庫的理由（#1079）
- **來源 Issues：**[#15](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/15), [#17](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/17), [#34](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/34), [#67](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/67), [#77](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/77), [#91](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/91), [#122](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/122), [#144](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/144), [#148](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/148), [#159](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/159), [#300](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/300), [#301](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/301), [#555](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/555), [#961](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/961), [#962](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/962), [#1079](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1079), [#1174](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1174)
- **實作 PRs：**[#20](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/20), [#22](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/22), [#58](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/58), [#69](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/69), [#89](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/89), [#109](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/109), [#125](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/125), [#152](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/152), [#153](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/153), [#161](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/161), [#306](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/306), [#1130](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/1130)

## 問題與限制

Spec、Feature、subissue、Milestone 與 PR 若沒有不同責任，容易把產品成果、工作拆解與交付批次混在一起，或在 PR 中靜默加入新範圍。

## 決定

- Spec 保存中長期 intent、constraints 與 acceptance contract；預設同步 Task Issue，明列 `tracking: story` 時同步 native Feature parent，`tracking: none` 可保存沒有新 work item 的 current capability。
- 每張 Issue 是可獨立指派、測試與關閉的 scope boundary，工作種類由 native Type 表達。只有一張主 Issue 無法以單一完成條件與單一份證據收尾時，才在它底下開 Task 或 Bug sub-Issue；只有真實先後限制才另設 blocked by／blocking。
- 主 Issue 內發現、屬於原範圍的 Bug 掛為它的 sub-Issue；獨立 regression 可以是 standalone Bug，但必須記錄沒有 parent 的理由。新需求超出 acceptance 時另開 sub-Issue 或 Issue。
- Milestone 是選用且有真實 due date 的 delivery／release bucket。無真實排程就不建立。Milestone 的 Issue 結構固定為三層（擁有者 2026-10-19 決定，#1174）：
  1. 一張 lifecycle tracker Issue（標題 `Milestone <N>: <名稱>`），它不是任何 Issue 的 parent；
  2. 多張主 Issue 直接掛入 Milestone，不再另設 Feature parent 收編它們；研究或 Feature Issue 擴展成有期限的 delivery 時，原 Issue 本身成為其中一張主 Issue；
  3. 只有必要時才在主 Issue 底下開 sub-Issue，sub-Issue 與它的 parent 掛在同一 Milestone。
  主 Issue、sub-Issue 與對應 PR 都掛入同一 Milestone；避免重複計數只能影響報表呈現，不能把實際交付範圍從 Milestone metadata 排除。Milestone 18（#1058）與 Milestone 19（#1180）即採此結構。
- Milestone tracker Issue 與底下 work Issue 的關聯維持 `References` 段落文字列點加上 `milestone=N` 查詢，不改用 GitHub 原生 sub-issues：sub-issue 的 parent 欄位是單一值，而這個 repo 已經把它用在 Feature／Task／Bug 階層（上述第二點），tracker 若也要求同一個欄位會與已經是某張主 Issue sub-issue 的 work Issue 直接衝突；只掛頂層主 Issue 又會讓 sub-issue 進度條系統性漏掉巢狀 work Issue，比純文字列點更容易誤導。`.github/ISSUE_TEMPLATE/milestone-tracker.yml`（Issue #555）改為預先帶入 tracker body 的四個 H2 段落骨架，把「表單防呆」與「連結機制」分開處理，不是同一個決定。
- Issue 的工作種類由 native Type 表達；`documentation`、`hotfix`、`promotion` 等 Label 只補充 Type 沒有表達的分類。Issue form 先帶小寫分類 Label 作為不支援 native Type 時的 portable fallback；Type 設定成功後，lifecycle automation 移除重複 Label。PR 是 leaf Issue 的交付與驗證單位，保留一個由 Issue Type（或 fallback Label）推導的小寫 classification Label，並同步 assignee 與 Milestone；work branch 使用 native Development link，closing keyword 前 PR 與 Issue checklist 都必須完成。
- TDD 的 test 與 implementation 留在同一 leaf Issue／PR；不把 red、green、refactor 拆成三張管理單。
- 使用固定但精簡的 body shape；來源、風險、verification 與 prior decisions 收進既有補充區，不再增加平行表單。
- Issue 的風險與控制（SPEC-010，#1058 決定 22）只放在 Issue 本文「補充」的可解析區塊，由「完成條件」的頂層 AC 與 PR 的 `Requirement evidence` 單層對應；登錄冊由 Issue 即時計算，不 commit、不寫入 tracker。不另建需求資料庫或 RTM，也不做 hosted PR 留言、triage 留言或提醒：Issue body 已是工作範圍與 AC 的唯一來源（#223），第二份資料會與它漂移；Ready 預檢、`validate-pr-policy` 與 `merge_snapshot` 共用同一個 trusted-base parser 就足以擋下不完整的區塊，留言 bot 只會多一條需要權限與維護、卻不決定結果的路徑。契約見 [SPEC-010](../specs/SPEC-010-issue-risk-controls.md)。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | Issue-first 與超出 scope 另開工作單 | [#15](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/15)／[#20](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/20) |
| Preserved | Spec ID 放 hidden marker，不塞進 Issue title | [#17](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/17)／[#22](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/22) |
| Rejected | 現階段全面遷移 GitHub Spec Kit 或同時維護兩種 spec 格式 | [#77](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/77)／[#89](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/89) |
| Superseded in part | Milestone 不由 Issue 數量或標題／label 自動推斷仍保留；story identity 改由 Feature parent 表達，Milestone 收斂為 dated delivery | [#122](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/122)／[#125](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/125) → [#300](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/300) |
| Superseded in part | 只用 labels 模擬工作類型，先改用 native Type 並在 Issue／PR 都保留同名 Label；#961 再收斂為 Issue 只用 Type、PR 保留小寫 classification Label，Label 在不支援 Type 時才作 fallback | [#91](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/91)／[#109](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/109) → [#301](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/301) → [#961](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/961) |
| Superseded | 精簡 body 後把歷史遷移只留在 PR 備註、未建 follow-up | [#67](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/67) → [#148](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/148)／[#153](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/153) |
| Rejected | 改用 GitHub 原生 sub-issues 連結 Milestone tracker 與底下 work Issue（取代 `References` 文字列點） | [#555](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/555) |
| Preserved | 新增 `.github/ISSUE_TEMPLATE/milestone-tracker.yml`，預先帶入 tracker 四個 H2 段落骨架降低照抄漏段落機率；`tracker_errors()` 驗證邏輯不變 | [#555](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/555) |
| Rejected | Feature parent 不掛 Milestone 以避免三重計數；這是把 hierarchy 誤當成 delivery membership 的排除條件。2026-10-19 起 Milestone 不再設 Feature parent，但任何有 sub-Issue 的主 Issue 仍須與 sub-Issue 掛在同一 Milestone | [#300](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/300)／[#301](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/301) → [#962](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/962) |
| Superseded | Milestone 內以 Feature parent 收編 Task／Bug sub-Issue 的「SDD → Feature parent → sub-Issue」交付結構；改為 tracker → 主 Issue → 必要時 sub-Issue（擁有者 2026-10-19 決定）。Spec 的 `tracking: story` 仍可同步一張可容納 sub-Issue 的 Feature Issue | [#300](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/300) → [#1174](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1174) |
| Rejected | Issue 風險控制另建需求資料庫／RTM，或以 hosted PR 留言、triage 留言與提醒呈現 | [#1079](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1079)／[#1130](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/1130) |

## Ownership 與驗證

Spec owner 維護 current contract；Milestone tracker owner 驗 delivery outcome；主 Issue owner 控制工作邊界並決定是否需要 sub-Issue；delivery owner 管理 Milestone；PR author 提供測試與影響證據。Spec sync 以 hidden stable ID idempotently 更新 Task 或 Feature Issue，並驗證 status、required sections 與 ID uniqueness。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 每張 Issue 都先寫完整 RFC | 不採用；小工作成本過高 |
| 每份 spec 都建 Milestone | 不採用；spec／story identity 與 delivery deadline 不是同一概念 |
| 每個 checklist item 都拆 subissue | 不採用；只有可獨立負責、測試或交付的工作才值得成為 subissue |
| 用 dependency 取代 parent | 不採用；composition 與 ordering 是不同關係 |
| 用標題／label 自動回填歷史分群 | 不採用；缺乏足夠語意證據 |
| 只靠 Issue title | 不採用；缺少 outcome、acceptance 與 verification |
| 用原生 sub-issue 取代 tracker 的 `References` 列點 | 不採用；單一 parent 欄位已被主 Issue／sub-Issue 階層占用，會與既有階層衝突且無法完整覆蓋巢狀 work Issue |
| Milestone 內每項成果都先建 Feature parent，再拆 Task／Bug sub-Issue | 不採用（#1174）；多一層 parent 只重複 tracker 已有的 outcome，收尾時還要另外關閉 parent，Milestone 18 實際以主 Issue 直接交付 |
| 建立需求資料庫／RTM 保存 AC 與風險對應 | 不採用（#1079）；Issue body 是唯一來源，第二份資料會漂移，單層 AC 對應已足夠 |

## 重新評估條件

當主 Issue 經常需要多層 sub-Issue，或 tracker 的 `References` 列點已無法讓人看懂交付範圍時，重新評估是否恢復 Feature parent 層。單層 AC 對應無法表達實際需求追溯（例如外部稽核要求 RTM）時，重新評估需求資料庫，但仍以 Issue body 為來源。

當一份 spec 需要穩定拆成多層 dependency graph，或現有單檔 schema 無法表達反覆變更時，再評估更完整的 spec toolchain；仍必須保留 GitHub traceability 與 migration plan。
