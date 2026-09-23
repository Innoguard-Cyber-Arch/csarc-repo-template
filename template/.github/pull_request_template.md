## Purpose

<!-- Replace N with the Issue number used in the branch name. -->

Closes #N

<!-- Work PRs use type/N-short-slug and target the configured integration branch. -->
<!-- A CSARC-owned Milestone promotion bridge (promote/m<N>-<slug>) replaces the line above with Refs #N so release.yml closes the tracker only after publication succeeds. -->

## 完成清單

<!-- Closing keywords require every task here and in the linked Issue to be checked. -->

- [ ] 已完成變更 owner 的 focused checks，並由設定模式產生最終證據：local 模式在 committed、clean 的 exact candidate 跑一次 `./.csarc/scripts/verify-fast`（需要時自動升級 full）；hosted 模式只由 required `verify` check 在 exact candidate 執行所選 suite，不因選到 full 就在本機重跑（文件明定的 fallback／診斷除外，見 `.csarc/docs/ci-policy.md`）；PR assignee／label／Milestone 與 linked Issue 一致；work branch 已顯示於 Issue Development；未超出原 Issue 範圍

## 文件一致性

<!-- 由本機 AI 比對程式、設定、測試與文件；每次 push 後都要重填 exact head。 -->

- Status: `inconclusive`
- Reviewed head: `<40-character commit SHA>`
- Reason: Replace this text with the checked scope or why documentation is not applicable.

## 補充

<!-- 選填：風險、回退，或本 PR 對其他專案的額外影響。 -->
<!-- 若依 admin_bypass 使用自核，另加一行完全相同的：Admin bypass / 管理員略過審核 -->
