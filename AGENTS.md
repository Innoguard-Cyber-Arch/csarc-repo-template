# Repository instructions

## Scope and sources of truth

- This file applies to the whole repository. Read a nearer `AGENTS.md` only if a future subtree genuinely needs different commands or safety rules.
- Treat this file as the single source for AI instructions; `CLAUDE.md` only imports it.
- Treat `copier.yml`, `template/`, `policies/`, and `profiles/catalog.yaml` as the product.
- `template/` is what downstream repositories receive. Root configuration governs this template repository itself.
- Use root `docs/specs/` for medium- and long-term design; approved specs synchronize to Issues through the same pipeline shipped to downstream repositories.
- Keep the deck and checked-in paths aligned. Do not describe a capability as active unless the template creates and verifies it.

## Working loop

1. Before planning or opening an Issue, list open Milestones and read their descriptions and open Issues. Reuse an open story Milestone only when this work directly advances its acceptance criteria; otherwise create a new story Milestone or leave the Issue standalone.
2. A Milestone is an optional, independently verifiable story outcome containing one or more Issues. It is not required for every Issue, is not selected by Issue count, and must not also contain the linked PRs. A spec is only one possible story source. Use `docs/milestone-description.md` for its description.
3. Open or select one GitHub Issue before editing; use its acceptance criteria as the scope boundary. Write the Issue title in 12-80 ASCII characters and at least three words; describe the outcome without a type prefix or trailing period. Add it to the selected Milestone with GitHub's native association; necessary follow-up fixes may join the same open Milestone.
4. If new work exceeds that Issue, stop and open a separate Issue; do not silently widen the current branch or pull request.
5. Start from `main`, or from an open work branch whose pull request chain ends at `main`, and name the branch `type/<issue-number>-short-slug`.
6. Inspect the existing implementation, make the smallest coherent change, and preserve unrelated user work.
7. Add or update the narrowest regression check that proves non-trivial behavior.
8. Run targeted checks while iterating, then run `./scripts/verify-template.sh` before opening or updating a pull request.
9. Before closing the final open Issue in a Milestone, re-check the story acceptance criteria, mark every verified item complete, and add any genuinely required follow-up Issue. The lifecycle workflow closes a zero-open-Issue Milestone only when every acceptance checkbox is checked, and reopens it when open work or an unchecked criterion returns.
10. Open the pull request against `main` or its immediate parent in the stack, include `Closes #<issue-number>`, and never merge it yourself.
11. Report what changed, which verification ran, and any remaining limitation.

Parallel writable agents must use one branch and one Git worktree per task, and run concurrently only when their scopes are independent. Detect and reuse a host-managed worktree before creating one; never force the same branch into multiple worktrees, remove a worktree you did not create, or remove one with uncommitted changes. Worktrees isolate files, not integration: every result still follows this repository's pull request, CI, review, and final verification path.

Automated dependency, version-policy, and release-please branches may omit an Issue. This repository has no shared test environment, so it uses the main-only branch strategy.

Duplicate triage may close an Issue without a branch or pull request when no repository files change. Link the canonical Issue and use GitHub's native duplicate close reason; implementation work still follows the normal Issue, branch, and pull request loop.

For an existing repository, audit Milestones and Issues in bounded pages: propose semantic story groups and exclusions read-only, wait for confirmation, then idempotently create or update Milestones and associations. Do not infer grouping from titles or labels alone, require every historical Issue to have a Milestone, or reopen completed Issues during backfill.

## Commands

- Required final check: `./scripts/verify-template.sh`.
- Use the narrowest relevant check while iterating, but never replace the required final check with a partial result.

## Editing boundaries

- Keep shared policy changes synchronized between root and `template/` where both layers consume them.
- Do not weaken generated-project checks to make template tests pass.
- Keep GitHub Actions pinned to full commit SHAs and retain the readable release tag in a comment.
- Do not hand-edit generated lockfiles; use uv or pnpm so integrity metadata stays valid.
- Do not create a separate GitHub repository for testing or validation. Use local temporary projects or this repository's Issues, branches, pull requests, and Actions.
- Do not add a language, deployment target, platform integration, or placeholder configuration without a real consuming repository.
- Comments in source code must be written in English. Leave formatting and lint details in their executable configuration instead of duplicating them here.

## Platform capability and automation

- Keep desired CI/CD behavior declarative in the repository and enforce it with tests; agents may edit that declaration but must not assume organization or enterprise administrator access.
- The portable baseline must not require adopters to create a GitHub App or PAT, copy a personal token, populate `.env`, or change organization policy. Never extract or persist `gh auth token` as project configuration.
- Detect platform capabilities during init, adopt, and update when they are observable, and re-evaluate them during CI/CD. Distinguish allowed, blocked, and unknown; never treat a permission error as evidence that a capability is available.
- Select the highest safe supported mode and degrade explicitly to artifact-only or verification-only behavior when release or deployment writes are unavailable. Never claim that a release or deployment succeeded when it was skipped or blocked.
- Do not make the portable fallback the capability ceiling. When stronger controls are confirmed, prefer the mode with stronger review, ordering, provenance, and deployment guarantees.
- A pull request declares SemVer intent through its validated title. Assign the exact version only after merge from the actual default-branch history; do not reserve version numbers on open pull requests.
- Keep external trust bootstrap such as package-registry publishers or cloud identities optional and verifiable. Do not bypass or silently weaken platform policy to make automation pass.
- Keep the website aligned with the capability matrix. For each policy-dependent mode, document its prerequisites, selected behavior, guarantees, limitations, and fallback without presenting unavailable capabilities as active.

## Safety

- Never commit secrets, tokens, private keys, or populated `.env` files.
- Review the plan output before applying repository settings; do not operate production or external infrastructure without explicit authorization.
- Do not bypass required checks, human approval, CODEOWNER review, or supply-chain verification.
- Alpha 階段允許作者自行合併；在 PR 內文加註 `Alpha 自行合併 / self-merged`，作為第 7 點「never merge it yourself」的已知例外。

## Code Review Rules

- Flag documentation or slide claims that do not match files the template actually creates.
- Flag changes that reduce required checks, permissions safety, artifact verification, or product-source preservation during Copier updates.
- Require tests for behavior changes and synchronized lockfile updates for dependency changes.
- Treat public interfaces, release behavior, workflow permissions, and secret handling as high-risk review areas.
