# Agent collaboration and durable handoff ADR

- **狀態：**Accepted
- **日期：**2026-08-24
- **來源 Issues：**[#126](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/126), [#145](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/145), [#155](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/155), [#171](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/171), [#177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/177)
- **實作 PRs：**[#127](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/127), [#147](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/147), [#158](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/158), [#173](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/173), [#185](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/185)

## 問題與限制

多個 agent 若共用 working directory，checkout、未提交檔案與工具狀態會互相污染；若新 session 不查歷史，也會重做或反轉先前決策。遠端 Actions 無法清理本機 worktree，agent 自述也不能取代平台 evidence。

## 決定

- 每個平行可寫任務使用獨立 branch 與 worktree，只平行處理可分離範圍；PR、CI 與最終整合仍是共同門禁。
- 建立工作前以 2–4 個具體詞限量搜尋 open／closed Issues，閱讀 body、comments 與 linked PR；在新 work item 記錄沿用、取代或駁回。
- Durable constraint 經使用者確認後摘要進 Issue，再由 scoped PR 更新 decision record；不保存 raw conversation 或 unconfirmed inference。
- 建立 worktree 的 agent 在 merge／abandon 後負責安全清理；只清理自己建立、乾淨且可證明已整合的 worktree。
- 本機驗證 attestation 只有在精確 quota-only 條件與 human authorization 下成立，且只綁定一個 SHA。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | Native `git worktree` 是 portable isolation baseline；manager 僅為選配 | [#126](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/126)／[#127](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/127) |
| Preserved | 以 bounded GitHub history search 取代第一版向量／語意資料庫 | [#145](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/145)／[#147](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/147) |
| Rejected | Agent 自動保存完整聊天或把推論升格為決策 | [#177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/177)／[#185](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/185) |
| Preserved | Actions 無法替代 agent host 上的 worktree cleanup | [#155](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/155)／[#158](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/158) |
| Unresolved | 下一個 agent 的 startup cleanup 保險在 cutoff 時尚未合併 | [#204](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/204)／[PR #210](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/210) |

## Ownership 與驗證

`AGENTS.md` 是 agent workflow source；`docs/README.md` 是 memory map；spec 與 decision files 是內容來源。Worktree cleanup 用本機 fixture 驗證，任何 agent handoff 都應交代 branch、SHA、verification 與尚未完成限制。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 多 agent 共用一個 working directory | 不採用；branch 無法隔離未提交狀態 |
| 強制安裝 Worktrunk／特定 orchestrator | 不採用作 baseline；native Git 必須可用 |
| 用背景 daemon 或 Actions 清本機 worktree | 不採用；遠端看不到 agent host，隱式刪除風險高 |
| 只靠 agent 記憶先前對話 | 不採用；session 與工具切換後不可依賴 |

## 重新評估條件

若 host platform 提供有 ownership、dirty-state 保護與可稽核 lifecycle 的原生 worktree 管理，可替代部分本機步驟；GitHub work item、repository memory 與合併門禁仍保留。
