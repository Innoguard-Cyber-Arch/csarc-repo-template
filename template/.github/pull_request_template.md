## Purpose

<!-- Replace N with the Issue number used in the branch name. -->

Closes #N

<!-- Work PRs use type/N-short-slug and target the configured integration branch. -->
<!-- A Milestone promotion bridge (promote/m<N>-<slug>) closes its own tracker Issue here, like any other Issue. -->

## 完成清單

<!-- Closing keywords require every task here and in the linked Issue to be checked. -->

- [ ] CI 依風險自動選擇的 `verify` check（docs／fast／full）已通過；一般工作 PR 不必在本機另外重跑 `./scripts/verify`，只有此 PR 本身是 full-tier 交付邊界時，owner／integrator 才需在本機執行過一次（見 `docs/ci-policy.md`）；PR assignee／label／Milestone 與 linked Issue 一致；work branch 已顯示於 Issue Development；未超出原 Issue 範圍

## 補充

<!-- 選填：風險、回退，或本 PR 對其他專案的額外影響。 -->
