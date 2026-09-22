## Purpose

<!-- Replace N with the Issue number used in the branch name. -->

Closes #N

<!-- Work PRs use type/N-short-slug and target the configured integration branch. -->
<!-- A CSARC-owned Milestone promotion bridge (promote/m<N>-<slug>) replaces the line above with Refs #N so release.yml closes the tracker only after publication succeeds. -->

## 完成清單

<!-- Closing keywords require every task here and in the linked Issue to be checked. -->

- [ ] 設定模式所需的最終驗證證據已通過：local 模式在 committed、clean 的 exact candidate 跑一次 `./.csarc/scripts/verify-fast`（需要時會自動升級 full），hosted 模式由 `verify` check 執行；沒有為了證明而重跑同一 suite（見 `.csarc/docs/ci-policy.md`）；PR assignee／label／Milestone 與 linked Issue 一致；work branch 已顯示於 Issue Development；未超出原 Issue 範圍

## 補充

<!-- 選填：風險、回退，或本 PR 對其他專案的額外影響。 -->
