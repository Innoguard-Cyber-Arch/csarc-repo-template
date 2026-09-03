---
id: SPEC-007
title: Maintain portable decision documentation
owner: @Innoguard-Cyber-Arch/arch
priority: P2
estimate: ongoing
status: approved
tracking: none
---

## Problem

README、agent instructions、深入決策與簡報若各自重述同一件事，會快速漂移；若唯一來源是巨大 HTML 或外部網站，受限環境、離線交付與後續維護又會失敗。

## Outcome

一般使用者、維護者與 agent 各有清楚入口；canonical Markdown 與網站來源可重建一份 self-contained `docs/index.html`，即使沒有 Pages、CDN 或外部服務也能閱讀與交付。

## Context

目前 root presentation 由 `site/` 維護，生成專案則由 template renderer 與 project-owned content／theme 組合。Hugo 已由 Issue #524（Milestone 13）完全取代為本機 Python 渲染引擎，不再是候選或 open work；雙語與 `llms.txt` 已隨同一批改動落地。

## Acceptance criteria

- [x] README 服務一般採用者、`AGENTS.md` 服務 repository 工作規則、`docs/README.md` 導覽深度來源，三者不完整複製彼此。
- [x] `docs/specs/` 是 current SDD，`docs/adr/` 是 Architecture Decision Records；`docs/index.html` 只呈現摘要與連結，不是唯一可編輯來源。
- [x] `docs/index.html` 由 repository source 重建、可用 `file://` 離線開啟，且無 runtime 外部 CSS、JavaScript、font 或 image dependency。
- [x] Root 保存自身真實內容；Copier template 保存 renderer／結構，並保留 consuming project 的內容與 theme overrides。
- [x] `noindex`／`robots.txt` 只標示資料邊界，不被描述成 access control。
- [x] 聊天只在使用者確認後摘要進 work item／decision record；不保存完整逐字稿、敏感資訊或模型 chain-of-thought。
- [x] Hugo 已由 Issue #524（Milestone 13）正式 cutover 為本機 Python 渲染引擎；i18n（雙語）與 `llms.txt`（AI-readable output）已隨同一批改動落地，不再是候選狀態。

## Plan

現有 source-to-bundle contract 持續由小型 renderer 驗證；未來 cutover 必須由獨立 Issue 更新本 spec、decision record 與維護指引。

## Out of scope

- 把 `docs/index.html` 當 access control。
- 在本 spec 中導入、發布或切換 Hugo／Pages／外部 host。
- 讓 AI 未經確認自動將對話寫入 repository。

## Verification

- `uv run --no-project python scripts/render_site.py --check`
- `./scripts/verify-template.sh`
- 離線、鍵盤與窄螢幕檢查依 `site/README.md` 執行。

## References

- [Issues #166–#169](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/166)／[PRs #172–#176](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/172)
- [Issue #177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/177)／[PR #185](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/185)
- [Issue #178](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/178)／[PR #187](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/187)
- Planned work: [#194](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/194), [#205–#209](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/205)
- [Portable decision site architecture ADR](../adr/portable-decision-site.md)
