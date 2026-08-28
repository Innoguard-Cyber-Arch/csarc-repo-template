---
id: SPEC-005
title: Preserve continuous verification evidence
owner: @Innoguard-Cyber-Arch/arch
priority: P1
estimate: ongoing
status: approved
tracking: none
---

## Problem

文件、單一綠燈或 coverage 百分比都不能單獨證明模板、生成專案、平台整合與多 runtime 行為持續正確；反過來，每張小 PR 都跑完整矩陣也會浪費時間與 hosted runner 額度。

## Outcome

本機與 CI 共用 canonical verification，依變更風險與交付階段執行適當層級，並留下能區分靜態、合成、hosted 與 live integration 的證據。

## Context

本 repo 將 TDD 視為工程方法，不是逐步日誌格式。Durable evidence 是保留在 tests、bug regression、CI summaries、release／pilot evidence 與必要 attestation 的最後可重現結果。

## Acceptance criteria

- [x] Root 以 `./scripts/verify-template.sh`、生成專案以 `./scripts/verify` 作完整本機入口；語言工具、模板生成、Copier update 與政策 fixture 都由該入口涵蓋。
- [x] CI 分為 policy、fast、full 與 scheduled／release tiers；未知高風險變更 fail closed，常駐 aggregate context 不因 job skip 永久 Pending。
- [x] Python 驗證涵蓋精確最低 patch 與宣告範圍內每個 feature release；TypeScript、CI-only 與 mixed profiles 各自驗證真實輸出。
- [x] Coverage 作為未測程式碼訊號，不被描述成品質分數；門檻依風險與缺陷證據調整。
- [x] Workflow、permission、GitHub API 與 release 行為以 live probe 或 consuming-repo pilot 補足靜態 fixture，且清楚標示未驗證部分。
- [x] Actions quota fallback 只接受 human 確認的免費額度耗盡、零 step 啟動與精確 SHA；promotion 另綁定 candidate/main tree 並保持不可發布，不能取代 release、deployment、secret 或 provenance 控制。
- [x] Runner-minute 降幅保留為明確的規劃估算；hosted duration 與 `ci-plan` 是 runner 可用時的 optional telemetry。Hosted telemetry 不可用不阻塞產品交付，zero-step 也不記成成功。
- [x] 修 bug 時新增會在修正前失敗的最小 regression；不要求保存每一次 red／green 暫態。

## Plan

此 spec 是持續驗證基線。效能優化可以減少重複 runner 或 runtime-independent 工作，但不得縮減聲明的支援範圍或 promotion full verification；quota-only promotion fallback 必須保存等價的本機驗證與 tree evidence，並在 hosted checks 補跑前阻止 release。可用時收集 hosted telemetry 來校準規劃模型，不把改變帳單、方案或 runner 當作完成條件。

## Out of scope

- 用本機聲明偽造 GitHub Check Run。
- 以 coverage threshold 取代需求、風險與人工審查。
- 為了歷史記錄保存每次測試暫態或完整 console transcript。

## Verification

- `./scripts/verify-template.sh`
- 對一個受控錯誤 fixture 證明相關 check 會失敗。
- Hosted 或 live evidence 不可用時，明列限制、不記成成功；只有產品或安全缺口需要另開追蹤 Issue。

## References

- [Issue #37](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/37)／[PR #52](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/52)
- [Issue #99](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/99)／[PR #136](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/136)／[PR #137](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/137)
- [Issue #100](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/100)／[PR #138](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/138)
- [Issue #140](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/140)／[PR #150](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/150)
- [Issue #162](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/162)／[PR #164](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/164)
- [Issue #171](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/171)／[PR #173](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/173)
- [Issue #233](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/233)／[PR #236](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/236)
- [Issue #181](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/181)／[PR #190](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/190)
- Superseded hosted measurement／recovery gates: [#189](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/189), [#199](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/199) → [#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287); structural quota handling remains [#254](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/254)
- [Staged delivery and verification ADR](../adr/staged-delivery-and-verification.md)
