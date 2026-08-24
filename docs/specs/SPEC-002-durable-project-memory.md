---
id: SPEC-002
title: Establish durable project memory and backfill records
owner: @Innoguard-Cyber-Arch/arch
priority: P1
estimate: 1-3 days
status: approved
tracking: issue
---

## Problem

專案已有 spec、Issue、PR、測試、決策文件與可攜式網站，重要理由卻仍大量散落在時間線中。人或 agent 在換 session、換工具或隔一段時間後，無法只從 repository 快速分辨目前契約、決策理由、尚未落地的提案與可執行證據。

## Outcome

Repository 提供一套 **Durable Project Memory（持久化專案記憶）**：Spec-Driven Development（SDD）在 `docs/specs/` 保存 living specifications，說明現在必須成立什麼；`docs/adr/` 的 Architecture Decision Records（ADR）說明為何如此選擇；GitHub 與 Git history 保存工作時間線，測試／CI 保存可執行證據，`AGENTS.md` 則把人與 agent 導向正確來源。

## Context

`durable project memory` 是 OpenAI 在 2026 年長任務實務中明確使用的名稱；spec、plan、decision log、狀態與驗證也廣泛出現在其他 spec-driven／RFC 流程。外部實務對「保存意圖、理由、歷史與證據」已收斂，但沒有共同強制的資料夾名稱或單一工具。本專案因此沿用既有 Markdown、GitHub 與測試管線，不導入第二套 SDD CLI 或資料庫。

### Canonical layers

| 問題 | Canonical source | 更新方式 |
| --- | --- | --- |
| 現在應具備什麼能力？ | `docs/specs/` | living spec；契約改變時在同一份 spec 更新現況與來源 |
| 為何選這個方案？ | `docs/adr/` | Architecture Decision Records；flow-forward 保留 accepted、superseded、rejected 與 unresolved 狀態 |
| 何時提案、討論與交付？ | Issue、PR、commit | 保留平台時間線，不批次重寫歷史 |
| 行為是否仍成立？ | tests、CI、release／pilot evidence | 以可執行檢查與外部證據驗證，不用文件宣稱取代測試 |
| Agent 應先讀什麼、如何工作？ | `AGENTS.md` 與 `docs/README.md` | 只放穩定導航與操作規則，細節回鏈 canonical source |

任務中的 plan、進度訊息與暫存筆記可用來協作，但結案後應摘要回上述來源；它們不是與 spec 並列的永久真相來源。

### SDD, TDD, and BDD

- **SDD（Spec-Driven Development）**：spec 是 intent、constraints、non-goals 與 acceptance contract；本 repo 的 durable artifacts 位於 `docs/specs/`。Software Design Document 也常縮寫為 SDD，但這裡不強制單一大型設計文件。
- **TDD（Test-Driven Development）**：測試、修正 PR 與 CI evidence 保存最後可重現的行為。除非某次失敗本身改變設計，否則不逐步保存 red／green／refactor 暫態。
- **BDD（Behavior-Driven Development）**：只有跨角色、對外可觀察的行為需要 living example 時，才用 declarative Given／When／Then 或等價 scenario；不因採用 BDD 思維就加入 Cucumber／Gherkin dependency。

### Behavior example

**Given** 一個沒有先前聊天內容的新 agent 開始維護工作，

**When** 它依 `AGENTS.md` 先讀 `docs/README.md`，再查相關 spec、decision record 與來源 Issue／PR，

**Then** 它能分辨目前契約、被取代或駁回的選項、尚未落地的 open work，以及應執行的驗證，而不需要重建原始對話。

## Traceability examples

| Evidence | Stable path |
| --- | --- |
| 新增 current spec 的 `tracking: none` 與 ADR/link validation | 本規格 → [Issue #223](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/223) → `scripts/spec_to_issue.py` → [TDD regression](../../tests/test_spec_to_issue.py) |
| Superseded decision | [Capability-aware governance ADR](../adr/capability-aware-governance.md) 的 #62 → #65／PR #66 disposition |
| Rejected proposal | [Release/security ADR](../adr/release-security-and-dependencies.md) 的 Renovate proposal → #110／PR #143 disposition |
| BDD-suitable fixture | 本規格的 Given／When／Then「新 agent 無聊天內容仍能重建脈絡」scenario；以 validator 與導航 assertion 實作，不新增 Cucumber |

## Acceptance criteria

- [x] `docs/specs/` 有本總規格及多份按能力域拆分的 current SDD。
- [x] `docs/adr/` 以最少量 Architecture Decision Records 回填既有重要決策，並保留來源與 disposition。
- [x] cutoff 前 103 張 Issues 與 118 張 PRs 的 body、comments、review／closing 關聯、commits 與 changed files 有可重跑 coverage ledger。
- [x] Root 保存本 repo 的真實歷史；Copier template 只下發結構、指引、範例與驗證，不複製本 repo 歷史。
- [x] Spec ID、必要段落、ADR status／date／sources 與 root／template contract 由本機驗證。
- [x] `AGENTS.md` 明確指向 `docs/README.md`、`docs/specs/` 與 `docs/adr/`。
- [x] 文件說清楚 SDD／TDD／BDD 的分工、隱私邊界與 raw transcript 禁令。
- [x] 現有網站只呈現相同摘要，不成為 canonical source，也不重做 Hugo／雙語／`llms.txt` 管線。

## Plan

1. 盤點 cutoff 前全部 GitHub 工作歷史並建立 coverage ledger。
2. 從已實作能力回填 current specs，再依理由與被取代方案回填 decision records。
3. 更新 root／template 導覽與輕量驗證；以既有 renderer 重建網站交付物。
4. 執行 targeted tests 與完整 template verification，將證據留在 Issue／PR。

## Out of scope

- 保存完整聊天、模型 chain-of-thought、secret 或未確認推論。
- 建立向量資料庫、RAG、MCP、外部知識庫，或強制導入 Spec Kit／OpenSpec／Cucumber。
- 把每個 TDD 暫態、每張歷史 Issue 或每個 implementation detail 複製成文件。
- 重寫歷史 Issue／PR，或取代 Milestone #8 的 Hugo、雙語與 `llms.txt` 工作。

## Verification

- `uv run pytest tests/test_spec_to_issue.py -q`
- `./scripts/verify-template.sh`
- 以 coverage ledger 的明確 cutoff、數量與編號清單交叉核對 GitHub API 結果。
- 從全新 session 依 `AGENTS.md` 導航至本規格、至少一份能力 spec、decision record 與原始 Issue／PR。

## References

- [Issue #223](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/223)
- [Issue #34](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/34)／[PR #58](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/58) — root spec pipeline
- [Issue #145](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/145)／[PR #147](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/147) — prior-decision lookup
- [Issue #177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/177)／[PR #185](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/185) — canonical decision sources
- [OpenAI: Run long horizon tasks with Codex](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)
- [GitHub Spec Kit: Spec persistence](https://github.com/github/spec-kit/blob/main/docs/concepts/spec-persistence.md)
- [OpenSpec](https://github.com/Fission-AI/OpenSpec)
- [Kubernetes KEP template](https://github.com/kubernetes/enhancements/blob/master/keps/NNNN-kep-template/README.md)
- [Rust RFC process](https://github.com/rust-lang/rfcs/blob/master/README.md)
- [Cucumber BDD](https://github.com/cucumber/docs/blob/main/content/docs/bdd/_index.md)
- [Durable project memory ADR](../adr/durable-project-memory.md)
- [Historical coverage ledger](../history-audit-2026-08.md)
