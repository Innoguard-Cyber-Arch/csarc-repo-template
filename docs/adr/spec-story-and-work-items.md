# Spec, story, and work-item boundaries ADR

- **狀態：**Accepted
- **日期：**2026-08-25
- **來源 Issues：**[#15](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/15), [#17](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/17), [#34](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/34), [#67](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/67), [#77](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/77), [#91](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/91), [#122](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/122), [#144](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/144), [#148](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/148), [#159](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/159), [#300](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/300), [#301](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/301)
- **實作 PRs：**[#20](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/20), [#22](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/22), [#58](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/58), [#69](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/69), [#89](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/89), [#109](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/109), [#125](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/125), [#152](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/152), [#153](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/153), [#161](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/161), [#306](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/306)

## 問題與限制

Spec、Feature、subissue、Milestone 與 PR 若沒有不同責任，容易把產品成果、工作拆解與交付批次混在一起，或在 PR 中靜默加入新範圍。

## 決定

- Spec 保存中長期 intent、constraints 與 acceptance contract；預設同步 Task Issue，明列 `tracking: story` 時同步 native Feature parent，`tracking: none` 可保存沒有新 work item 的 current capability。
- Feature Issue 是 SDD story parent；Task 或 Bug subissue 是可獨立指派、測試與關閉的 scope boundary。只有真實先後限制才另設 blocked by／blocking。
- Feature 內發現的 Bug 掛為 subissue；獨立 regression 可以是 standalone Bug，但必須記錄沒有 parent 的理由。新需求超出 acceptance 時另開 subissue 或 Issue。
- Milestone 是選用且有真實 due date 的 delivery／release bucket。它掛 leaf Issues 與對應 PR，Feature parent 不掛入，避免三重計算；無真實排程就不建立。
- PR 是該 leaf Issue 的交付與驗證單位；assignee、classification label、Milestone 與 Issue 一致，work branch 使用 native Development link，closing keyword 前 PR 與 Issue checklist 都必須完成。
- TDD 的 test 與 implementation 留在同一 leaf Issue／PR；不把 red、green、refactor 拆成三張管理單。
- 使用固定但精簡的 body shape；來源、風險、verification 與 prior decisions 收進既有補充區，不再增加平行表單。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | Issue-first 與超出 scope 另開工作單 | [#15](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/15)／[#20](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/20) |
| Preserved | Spec ID 放 hidden marker，不塞進 Issue title | [#17](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/17)／[#22](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/22) |
| Rejected | 現階段全面遷移 GitHub Spec Kit 或同時維護兩種 spec 格式 | [#77](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/77)／[#89](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/89) |
| Superseded in part | Milestone 不由 Issue 數量或標題／label 自動推斷仍保留；story identity 改由 Feature parent 表達，Milestone 收斂為 dated delivery | [#122](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/122)／[#125](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/125) → [#300](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/300) |
| Superseded | 只用 labels 模擬工作類型，改用 native Type；labels 保留跨 Issue／PR 的篩選語意 | [#91](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/91)／[#109](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/109) → [#301](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/301) |
| Superseded | 精簡 body 後把歷史遷移只留在 PR 備註、未建 follow-up | [#67](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/67) → [#148](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/148)／[#153](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/153) |

## Ownership 與驗證

Spec owner 維護 current contract；Feature owner 驗 story outcome；leaf Issue owner 控制工作邊界；delivery owner 管理 Milestone；PR author 提供測試與影響證據。Spec sync 以 hidden stable ID idempotently 更新 Task 或 Feature Issue，並驗證 status、required sections 與 ID uniqueness。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 每張 Issue 都先寫完整 RFC | 不採用；小工作成本過高 |
| 每份 spec 都建 Milestone | 不採用；spec／story identity 與 delivery deadline 不是同一概念 |
| 每個 checklist item 都拆 subissue | 不採用；只有可獨立負責、測試或交付的工作才值得成為 subissue |
| 用 dependency 取代 parent | 不採用；composition 與 ordering 是不同關係 |
| 用標題／label 自動回填歷史分群 | 不採用；缺乏足夠語意證據 |
| 只靠 Issue title | 不採用；缺少 outcome、acceptance 與 verification |

## 重新評估條件

當一份 spec 需要穩定拆成多層 dependency graph，或現有單檔 schema 無法表達反覆變更時，再評估更完整的 spec toolchain；仍必須保留 GitHub traceability 與 migration plan。
