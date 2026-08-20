# Repository instructions

## Scope and sources of truth

- This file applies to the whole repository. Read a nearer `AGENTS.md` only if a future subtree genuinely needs different commands or safety rules.
- Treat this file as the single source for AI instructions; `CLAUDE.md` only imports it.
- Treat `copier.yml`, `template/`, `policies/`, and `profiles/catalog.yaml` as the product.
- `template/` is what downstream repositories receive. Root configuration governs this template repository itself.
- Keep the deck and checked-in paths aligned. Do not describe a capability as active unless the template creates and verifies it.

## Working loop

1. Start from one defined outcome and inspect the existing implementation before editing.
2. Make the smallest coherent change and preserve unrelated user work.
3. Add or update the narrowest regression check that proves non-trivial behavior.
4. Run targeted checks while iterating, then run `./scripts/verify-template.sh` before opening or updating a pull request.
5. Report what changed, which verification ran, and any remaining limitation.

## Commands

- Required final check: `./scripts/verify-template.sh`.
- Use the narrowest relevant check while iterating, but never replace the required final check with a partial result.

## Editing boundaries

- Keep shared policy changes synchronized between root and `template/` where both layers consume them.
- Do not weaken generated-project checks to make template tests pass.
- Keep GitHub Actions pinned to full commit SHAs and retain the readable release tag in a comment.
- Do not hand-edit generated lockfiles; use uv or pnpm so integrity metadata stays valid.
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
