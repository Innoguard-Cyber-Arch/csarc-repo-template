---
id: SPEC-004
title: Govern delivery according to verified platform capabilities
owner: @Innoguard-Cyber-Arch/arch
priority: P1
estimate: ongoing
status: approved
tracking: none
---

## Problem

GitHub plan、repository visibility、organization policy 與 token scope 會改變可用的 Ruleset、review、PR automation、release 與 canary 能力。多個 agent worktree 也會共用相同 PR control plane。若流程假設所有能力都存在或把 worktree 當成遠端互斥，就會失敗、競速 merge，或把未受保護狀態誤報成安全。

## Outcome

工作從 Issue／Story 經正確 delivery branch、PR 與 promotion boundary 交付；automation 依 runtime 證據選擇最高安全模式，對 blocked／unknown 能力明確降級且不虛構 enforcement。

## Context

早期 main-only 與「缺 Ruleset 就全面阻擋」設計已被實際 GitHub Free private 行為修正。現在的 portable baseline 以 repository declaration、短效 `GITHUB_TOKEN`、人工審查與可稽核降級為核心；較強平台能力存在時才提升強制性。

## Acceptance criteria

- [x] 每個一般工作先有 Issue；Milestone 是可選的端到端 story，不因 Issue 數量或 spec 存在自動建立。
- [x] Delivery 策略以 `dev/m*`、`dev/next`、受限的 `dev/i*` 與 hotfix 路徑區分整合風險，PR base 由 linked Issue 實際狀態驗證。
- [x] Main 前進後，active delivery branch 透過受審查 sync PR 納入；不直接 push 或在 main 解衝突。
- [x] 平台能力使用 allowed／blocked／unknown，只有已確認可用時啟用較強 automation；未知不當作 allowed。
- [x] GitHub Free private 缺少 Ruleset／team review enforcement 時顯示 `DEGRADED`，但仍執行可攜式 checks 與個別 reviewer request。
- [x] 平行 task 的 Ready／Draft／label／milestone／authorization／merge 寫入只能透過 repository remote lease 工具序列化；default-branch PR 另共用 promotion lane lease。
- [x] Agent merge 只在 live review、last-push approval、required checks 與 no-bypass Ruleset 可證明時啟用；Free private 或 unknown capability 一律停在 human-only manual merge。
- [x] 不要求長效 PAT、額外 GitHub App、降低 branch protection 或修改 organization policy 才能使用 baseline。
- [x] Promotion、release 與 Milestone completion 由完整 acceptance 與 evidence gate，而不是只看分支名稱或 open Issue 數。

## Plan

此 spec 描述已落地的 delivery contract；新平台能力或 route 需由獨立 work item 修改 policies、tests、文件與本 spec。

## Out of scope

- 宣稱 repository 內 policy 等於平台已強制。
- 未經授權修改 organization／enterprise 設定。
- 自動由標題或 labels 推斷歷史 Milestone 關係。

## Verification

- `./scripts/test-pr-policy`
- `uv run pytest tests/test_pr_lifecycle.py`
- `./scripts/apply-repository-settings.sh check`
- `./scripts/verify-template.sh`
- promotion 與 sync evidence 必須綁定實際 base／head SHA 或 candidate tree。

## References

- [Issue #18](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/18)／[PR #25](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/25)
- [Issue #65](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/65)／[PR #66](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/66)
- [Issue #87](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/87)／[PR #90](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/90)
- [Issue #122](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/122)／[PR #125](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/125)
- [Issue #163](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/163)／[PR #165](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/165)
- [Issues #179–#184](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/179)／[PRs #186–#193](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/186)
- [Capability-aware governance ADR](../adr/capability-aware-governance.md)
- [Staged delivery and verification ADR](../adr/staged-delivery-and-verification.md)
- [Issue #240](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/240)
