# Repository instructions

## Scope and sources of truth

- This file applies to the whole repository. Read a nearer `AGENTS.md` only if a future subtree genuinely needs different commands or safety rules.
- Treat this file as the single source for AI instructions; `CLAUDE.md` only imports it.
- Treat `copier.yml`, `template/`, `policies/`, and `profiles/catalog.yaml` as the product.
- `template/` is what downstream repositories receive. Root configuration governs this template repository itself.
- Use root `docs/specs/` for medium- and long-term design; approved specs synchronize to Issues through the same pipeline shipped to downstream repositories.
- Keep the deck and checked-in paths aligned. Do not describe a capability as active unless the template creates and verifies it.

## Working loop

1. Open or select one GitHub Issue before editing; use its acceptance criteria as the scope boundary. Write the Issue title in 12-80 ASCII characters and at least three words; describe the outcome without a type prefix or trailing period.
2. If new work exceeds that Issue, stop and open a separate Issue; do not silently widen the current branch or pull request.
3. Start from `main`, or from an open work branch whose pull request chain ends at `main`, and name the branch `type/<issue-number>-short-slug`.
4. Inspect the existing implementation, make the smallest coherent change, and preserve unrelated user work.
5. Add or update the narrowest regression check that proves non-trivial behavior.
6. Run targeted checks while iterating, then run `./scripts/verify-template.sh` before opening or updating a pull request.
7. Open the pull request against `main` or its immediate parent in the stack, include `Closes #<issue-number>`, and never merge it yourself.
8. Report what changed, which verification ran, and any remaining limitation.

Automated dependency, version-policy, and release-please branches may omit an Issue. This repository has no shared test environment, so it uses the main-only branch strategy.

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

## Safety

- Never commit secrets, tokens, private keys, or populated `.env` files.
- Review the plan output before applying repository settings; do not operate production or external infrastructure without explicit authorization.
- Do not bypass required checks, human approval, CODEOWNER review, or supply-chain verification.

## Code Review Rules

- Flag documentation or slide claims that do not match files the template actually creates.
- Flag changes that reduce required checks, permissions safety, artifact verification, or product-source preservation during Copier updates.
- Require tests for behavior changes and synchronized lockfile updates for dependency changes.
- Treat public interfaces, release behavior, workflow permissions, and secret handling as high-risk review areas.
