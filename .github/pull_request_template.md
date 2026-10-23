## Purpose

<!-- Replace N with the Issue number used in the branch name. -->

Closes #N

<!-- Work PRs use type/N-short-slug and target the configured integration branch. -->
<!-- In a CSARC-owned Milestone promotion bridge (promote/m<N>-<slug>), replace the line above with Refs #N. Then release.yml closes the tracker only after publication succeeds. -->

## 完成清單

<!-- Before you use a closing keyword, check every task here and in the linked Issue. -->

- [ ] 已完成變更 owner 的 focused checks；hosted `verify` 會依風險在 exact candidate 執行 fast／full 並提供 required merge evidence，不因選到 full 就在本機重跑同一套 `./scripts/verify-template.sh`（文件明定的 fallback／診斷除外，見 `docs/ci-policy.md`）；PR assignee／label／Milestone 與 linked Issue 一致；work branch 已顯示於 Issue Development；未超出原 Issue 範圍
- [ ] 已測試新專案產生並評估既有專案更新影響；第三方 Actions 固定完整 commit SHA

## Requirement evidence

<!-- SPEC-010：Ready 前，依 Issue「完成條件」順序為每個 AC 與每個風險 ID 各填一列。證據形式：`path` 或 `path::name`（exact head 上的 regression）、`check:<name>`（exact-head check）、`manual: <https URL> <理由>`、`accepted: <理由>`（只限風險）、`scope:docs`（只限 R0）。Coverage 寫 Ready 檢查訊息列出的值；Issue 的 AC 或風險改變後要重新對應。 -->

Issue: #N
Coverage: sha256:replace-with-the-value-from-the-ready-check

| ID | 證據 |
| --- | --- |
| AC1 | replace-with-evidence |
| R1 | replace-with-evidence |

## 文件一致性

<!-- 由本機 AI 比對程式、設定、測試與文件；每次 push 後都要重填 exact head。 -->

- Status: `inconclusive`
- Reviewed head: `<40-character commit SHA>`
- Reason: Replace this text with the checked scope or why documentation is not applicable.

## 補充

<!-- 選填：風險、回退，或本 PR 對其他專案的額外影響。 -->
<!-- 若依 admin_bypass 使用自核，另加一行完全相同的：Admin bypass / 管理員略過審核 -->
