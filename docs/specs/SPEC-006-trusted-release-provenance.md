---
id: SPEC-006
title: Deliver verifiable releases and supply chain evidence
owner: @Innoguard-Cyber-Arch/arch
priority: P1
estimate: ongoing
status: approved
tracking: none
---

## Problem

通過 CI 不代表 release 的 source、tag、版本 metadata、成品、SBOM、attestation 與下游取得內容一致。平台權限、非同步 propagation 與 registry 身分也可能讓流程只完成一半。

## Outcome

每個正式 release 都能從 promotion／hotfix evidence 追到 exact source，再驗證 tag、immutable GitHub Release、artifact digest、SBOM 與 provenance。Registry publishing 由有實際需求的產品自行擁有；能力不足時停止或明確降級，不產生假成功。

## Context

早期 release-please、手動 tag 與 ephemeral version materialization 曾在 live runs 暴露權限、handoff、attestation 延遲與 source-version 漂移。本契約以實測修正後的 atomic source history 與 consumer-side verification 為準。

## Acceptance criteria

- [x] PR 只宣告 SemVer intent；精確版本由已合併 default-branch history 與 promotion boundary 決定。
- [x] Tagged source、版本欄位、CHANGELOG、prompt 與 provenance 指向同一版本與 commit。
- [x] Root GitHub Release 從已驗證 tagged source 建置 wheel／sdist；沒有實際 root registry 消費者時不維護跨 registry 發布路徑。
- [x] Release 保存 distributions／來源封存檔、SHA-256、固定 Syft 版本產生的 SPDX JSON SBOM 與 source metadata；manifest 以 digest 綁定 exact tag，不要求不同執行間的 Syft JSON byte-identical。
- [x] Conditional consumer verifier 在使用成品前驗 repository、tag、source／artifact digest 與 signer；公版不宣稱它是自動門禁。
- [x] 公版不提供 PyPI／npm／GHCR publisher 選項；需要 registry 的產品另案採 OIDC trusted publishing，不使用長效 token。
- [x] Dependency 與 source safety 由 lockfile、Dependabot、等待政策、publisher trust、OSV、Gitleaks 與 plan-aware CodeQL 分工，不用一項工具冒充全部供應鏈控制。
- [x] 已發布 immutable Release 不被重寫；歷史缺失證據明記為缺失，不補造 attestation。

## Plan

此 spec 維持已落地 trust chain；root CLI 從核准 GitHub Release commit 執行，新增 distribution channel 必須等 owner 提出實際需求後再重新評估。

## Out of scope

- 未經 owner／法務決策公開發布套件。
- 以 PAT、GitHub App 或降低平台政策換取自動化。
- 對早期歷史 release 捏造不存在的 artifact、signature 或 attestation。

## Verification

- `./scripts/verify-template.sh`
- `scripts/release_policy.py` 對 proposed tag 與既有 source metadata 做 fail-closed 驗證；root release workflow 只從通過驗證的 tagged checkout 建置一次 GitHub Release artifacts。
- `scripts/verify_release_consumption.py` 同時證明成功 consumption 與受控 digest mismatch 失敗。
- Live release evidence 連回 immutable GitHub Release 與 workflow run。

## References

- [Issue #29](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/29)／[PR #60](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/60)
- [Issue #30](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/30)／[PR #61](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/61)
- [Issue #98](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/98)／[PRs #118, #129, #130, #132](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/118)
- [Issue #101](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/101)／[PR #119](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/119)
- [Issue #104](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/104)／[PR #139](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/139)
- [Issue #110](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/110)／[PR #143](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/143)
- [Issue #123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123)／[PR #128](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/128)
- [Issue #142](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/142)／[PR #151](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/151)
- Distribution correction: [#170](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/170), [#195](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/195), and [#203](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/203) are superseded by [#250](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/250).
- [Release, security, and dependency ADR](../adr/release-security-and-dependencies.md)
