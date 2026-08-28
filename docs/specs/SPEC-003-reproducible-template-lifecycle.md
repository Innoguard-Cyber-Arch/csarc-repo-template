---
id: SPEC-003
title: Preserve a reproducible template lifecycle
owner: @Innoguard-Cyber-Arch/arch
priority: P1
estimate: ongoing
status: approved
tracking: none
---

## Problem

同一份公版同時服務新 repo、既有產品與後續更新。若 template-owned 與 project-owned 檔案沒有明確邊界，導入或更新可能覆寫產品內容、留下衝突，或讓 root 與下發內容漂移。

## Outcome

維護者能用同一個 versioned Copier template 建立、導入與更新 repository；每次操作可預覽、可驗證並保留產品自有內容，公版本身也持續驗證下發結果。

## Context

Root configuration 驗證公版本身；`template/` 是 downstream contract。逐位元組相同的 root／template 檔案由同步腳本維持，Jinja 化與專案自有檔案則用 generated fixtures 驗證。既有導入的已知交易性缺口由 open Issues 追蹤，不在本 spec 中冒充已完成。

## Acceptance criteria

- [x] `copier.yml` 明確區分 profile、template-owned output 與建立後應保留的 project-owned source、tests、specs、decisions 與網站內容。
- [x] 新建、既有導入與 update 都由真實生成 fixture 驗證，且 unresolved conflict markers／`.rej` 會 fail closed。
- [x] 可逐位元組共用的 root／template 檔案由 `scripts/sync-paired-files.sh` 產生並檢查，不靠人工雙改。
- [x] Lifecycle CLI 驗證 canonical repository、immutable release、tag、完整 commit SHA 與 provenance，dry-run 不寫入 target。
- [x] Template update 通知只建立／更新一張去重 Issue，不自動改產品 repository。
- [x] 尚未落地的 resumable／transactional adoption 與 metadata 完整性只列為 open work，不宣稱為現況。

## Plan

此 spec 是 current capability contract；變更從獨立 Issue／PR 進行，完成後更新本文件與對應 decision record。

## Out of scope

- 通用三方語意 merge engine。
- 在未確認時 stash、commit、push、開 PR 或套用 repository settings。
- 把 root repository 的歷史 decision records 複製到 consuming project。

## Verification

- `./scripts/sync-paired-files.sh --check`
- `./scripts/verify-template.sh`
- 檢查 create／adopt／update fixtures 保留 product-owned files 與 `docs/specs/**/*.md`。

## References

- [Issue #7](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/7)／[PR #8](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/8)
- [Issue #31](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/31)／[PR #53](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/53)
- [Issue #76](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/76)／[PR #88](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/88)
- [Issue #113](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/113)／[PR #115](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/115)
- [Issue #116](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/116)／[PR #124](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/124)
- [Issue #157](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/157)／[PR #160](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/160)
- Distribution correction: [#195](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/195) was superseded by [#250](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/250); the CLI runs from the approved GitHub Release commit instead of an unpublished registry package.
- Other follow-ups: [#196](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/196), [#197](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/197), [#198](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/198), [#219](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/219)
- [Template lifecycle and ownership ADR](../adr/template-lifecycle-and-ownership.md)
