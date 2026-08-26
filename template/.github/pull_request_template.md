## Purpose

<!-- Draft: use Refs #N. Before Ready, complete both checklists and change it to Closes #N. -->

Refs #N

<!-- Work PRs use type/N-short-slug and target the configured integration branch. -->

<!-- Required on Drafts; enter None when there is no known risk or dependency. -->

- Scope:
- Completed verification:
- Pending verification:
- Known risks:
- Dependencies / non-parallel work:

## 完成清單

<!-- Drafts may keep unchecked work; closing keywords and Ready require completion here and in the Issue. -->

- [ ] The CI plan's scoped checks pass with commands and results recorded; PR assignee/label/Milestone match the linked Issue; work branch appears in Issue Development; exactly one change label (`fix`→`bug`, `docs`→`documentation`, other types→`enhancement`); stays within the Issue
- [ ] If this PR is the final integration candidate, the integrator ran `./scripts/verify` exactly once on the unchanged tree; otherwise marked N/A
- [ ] If the CI plan includes generator/template scope, new-project generation is tested and existing-project updates are considered; otherwise marked N/A; changed lockfiles are reviewed and third-party Actions are pinned to full commit SHAs

## 補充

<!-- Optional: risks, rollback, or extra effects on other projects. -->
