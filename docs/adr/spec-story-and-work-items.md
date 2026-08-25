# Spec, story, and work-item boundaries ADR

- **狀態：**Accepted
- **日期：**2026-08-24
- **來源 Issues：**[#15](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/15), [#17](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/17), [#34](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/34), [#67](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/67), [#77](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/77), [#91](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/91), [#122](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/122), [#144](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/144), [#148](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/148), [#159](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/159)
- **實作 PRs：**[#20](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/20), [#22](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/22), [#58](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/58), [#69](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/69), [#89](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/89), [#109](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/109), [#125](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/125), [#152](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/152), [#153](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/153), [#161](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/161)

## 問題與限制

Spec、Story Milestone、Issue 與 PR 若沒有不同責任，容易把大目標誤當單一實作、把每份設計強制升格為 Milestone，或在 PR 中靜默加入新範圍。

## 決定

- Spec 保存中長期 intent、constraints 與 acceptance contract；核准後預設同步一張 Issue，明列 `tracking: story` 才同步 Milestone，`tracking: none` 可保存沒有新 work item 的 current capability。
- Milestone 是選用的端到端 story outcome，可含 1..N Issues；不是每張 Issue 都要有，也不重複掛 linked PR。
- Issue 是可獨立實作與關閉的 scope boundary；新需求超出 acceptance 時另開 Issue。
- PR 是該 Issue 的交付與驗證單位；closing keyword 前 PR 與 Issue checklist 都必須完成。
- 使用固定但精簡的 body shape；來源、風險、verification 與 prior decisions 收進既有補充區，不再增加平行表單。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | Issue-first 與超出 scope 另開工作單 | [#15](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/15)／[#20](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/20) |
| Preserved | Spec ID 放 hidden marker，不塞進 Issue title | [#17](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/17)／[#22](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/22) |
| Rejected | 現階段全面遷移 GitHub Spec Kit 或同時維護兩種 spec 格式 | [#77](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/77)／[#89](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/89) |
| Preserved | Story Milestone 不由 Issue 數量或標題／label 自動推斷 | [#122](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/122)／[#125](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/125) |
| Superseded | 精簡 body 後把歷史遷移只留在 PR 備註、未建 follow-up | [#67](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/67) → [#148](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/148)／[#153](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/153) |

## Ownership 與驗證

Spec owner 維護 current contract；Milestone owner 驗 story outcome；Issue owner 控制工作邊界；PR author 提供測試與影響證據。Spec sync 以 hidden stable ID idempotently 更新 work item，並驗證 status、required sections 與 ID uniqueness。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 每張 Issue 都先寫完整 RFC | 不採用；小工作成本過高 |
| 每份 spec 都建 Milestone | 不採用；spec 來源與 story outcome 不是同一概念 |
| 用標題／label 自動回填歷史分群 | 不採用；缺乏足夠語意證據 |
| 只靠 Issue title | 不採用；缺少 outcome、acceptance 與 verification |

## 重新評估條件

當一份 spec 需要穩定拆成多層 dependency graph，或現有單檔 schema 無法表達反覆變更時，再評估更完整的 spec toolchain；仍必須保留 GitHub traceability 與 migration plan。
