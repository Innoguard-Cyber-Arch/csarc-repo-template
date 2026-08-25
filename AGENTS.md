# Repository instructions

## Scope and sources of truth

- This file applies to the whole repository. Read a nearer `AGENTS.md` only if a future subtree genuinely needs different commands or safety rules.
- Treat this file as the single source for AI instructions; `CLAUDE.md` only imports it.
- Three documents split by audience, each authoritative for its own layer: `README.md` targets general users adopting the template (what it is, whether to use it, how to start); this file targets contributors and agents working in this repository (executable workflow rules); `docs/index.html` is the appendix for decision rationale and technical detail. Do not restate this file's workflow rules in `README.md`; link to it instead.
- Treat `copier.yml`, `template/`, `policies/`, and `profiles/catalog.yaml` as the product.
- `template/` is what downstream repositories receive. Root configuration governs this template repository itself.
- Use root `docs/specs/` for SDD current contracts; `docs/README.md` maps durable project memory.
- Use `docs/adr/` for decisions. In updated projects, also search project-owned `docs/decisions/`; never move or overwrite it automatically.
- Edit the root presentation in `site/`, then rebuild `docs/index.html`; do not hand-edit the generated bundle.
- Keep decision records, the deck, and checked-in paths aligned. Do not describe a capability as active unless the template creates and verifies it.

## Working loop

1. At task start, run `./scripts/cleanup-worktrees` in its default dry-run mode and report any candidates; this startup safety net does not replace the creator's cleanup duty under worktree handoff. Before implementing, check open Draft PRs, remote branches, and existing worktrees; do not claim owned work without an explicit handoff or dependency stack. Before planning or opening an Issue or Milestone, list open Milestones and open Issues, then search open and closed Issues with two to four concrete problem or technology terms. Inspect the body, comments, and linked pull requests of credible matches; titles and labels alone are not decisions. Keep each query bounded to 20 candidates.
2. A Milestone is an optional, independently verifiable story outcome containing one or more Issues. It is not required for every Issue, is not selected by Issue count, and must not also contain the linked PRs. A spec is only one possible story source. Use the concise title, story, read-only title audit, and delivery plan in `docs/milestone-description.md`; keep its English H2 headings, but write the content in the project's working language.
3. Before creating the work item, present a short prior-decision summary when the user can respond. If creation is already authorized, record each relevant `#N` as preserved, superseded, or rejected with a reason in the Issue supplement or Milestone `References`; when none are found, record the bounded queries used. When a user confirms a durable architecture, tooling, security, compatibility, or platform constraint, summarize it in the work item and update the matching `docs/adr/` record through the scoped pull request. Never store a raw conversation transcript or promote an unconfirmed inference to a decision. Never silently reverse an earlier decision.
4. Use the exact checked-in body shape whether creating through the UI, CLI, or API: Issues use `類型`, `問題`, `完成條件`, and optional `補充`; pull requests use `Purpose`, `完成清單`, and optional `補充`. Fold verification, risk, rollback, impact, and decision details into those sections instead of adding parallel top-level sections.
5. Open or select one GitHub Issue before editing; use its acceptance criteria as the scope boundary. Write the Issue title in 12-80 ASCII characters and at least three words; describe the outcome without a type prefix or trailing period. Add it to the selected Milestone with GitHub's native association; necessary follow-up fixes may join the same open Milestone.
6. If new work exceeds that Issue, stop and open a separate Issue; do not silently widen the current branch or pull request.
7. Start from the Issue's delivery branch (`dev/m<milestone-number>-<slug>` for a Milestone or `dev/next` when standalone), or from an open work branch whose pull request chain ends there, and name the branch `type/<issue-number>-short-slug`. A standalone Issue that genuinely needs an independent soak or canary may instead use the temporary work-and-promotion branch `dev/i<issue-number>-<slug>`; its Issue must have no Milestone, use the `promotion` label, and close only through that branch's promotion PR. Only a standalone `fix/*` pull request labeled `hotfix` may otherwise target `main` directly.
8. Inspect the existing implementation, make the smallest coherent change, and preserve unrelated user work.
9. Add or update the narrowest regression check that proves non-trivial behavior.
10. Run targeted checks while iterating. Once the minimal solution is explainable and those checks pass, push and open a Draft PR that states scope, completed and pending verification, known risks, and dependencies or non-parallel work. Run `./scripts/verify-template.sh` before marking Ready or updating a Ready PR; Draft updates need only proportionate targeted checks.
11. Create a final Issue labeled `promotion` when planning a delivery Milestone, and keep it open while work merges into the Milestone branch. An isolated `dev/i*` Issue itself is the promotion Issue. Before closing either kind, re-check the acceptance criteria and promotion evidence. The lifecycle workflow closes a zero-open-Issue Milestone only when every acceptance checkbox is checked, and reopens it when open work or an unchecked criterion returns.
12. Drafts use `Refs #N` while work remains. Before using `Closes`, `Fixes`, or `Resolves`, or marking Ready, complete every task in the pull request and referenced Issue; do not check work without evidence. Open an Issue pull request against its delivery branch or immediate parent in the stack; only a promotion, release-please, or qualified hotfix may target `main`. Never merge it yourself except under an explicit repository self-merge policy and the quota fallback documented in `docs/ci-policy.md`.
13. After a pull request is merged, the agent that created its worktree must leave that worktree, fetch its delivery branch, and run `./scripts/cleanup-worktrees --apply --worktree <path> origin/<delivery-branch>` from another checkout. If the task is explicitly abandoned instead, its creator may remove only that clean worktree with `git worktree remove <path>`; keep the branch. Platform-managed worktrees stay under the platform lifecycle. For repository-wide maintenance, review the command's default dry run before omitting `--worktree`; it never removes main, current, locked, detached, dirty, unmerged, or unverifiable worktrees.
14. Report what changed, which verification ran, and any remaining limitation.

Parallel writable agents must use one branch and one Git worktree per task, and run concurrently only when their scopes are independent. Detect and reuse a host-managed worktree before creating one; never force the same branch into multiple worktrees, remove a worktree you did not create, or remove one with uncommitted changes. Worktrees isolate files, not integration: every result still follows this repository's pull request, CI, review, and final verification path.

Delivery routes, synchronization, promotion, release, canary, rollback, and quota procedures are canonical in [`docs/ci-policy.md`](docs/ci-policy.md). Never push directly to a delivery branch, invent successful canary evidence, create or dispatch release tags manually, or bypass its gates. Existing-repository lifecycle details are canonical in [`docs/agent-install.md`](docs/agent-install.md).

Duplicate triage may close an Issue without code changes when it links the canonical Issue and uses GitHub's native duplicate reason. If a change modifies an Issue or pull request body shape, migrate existing bodies before closing it; otherwise create and link a follow-up Issue first.

## Commands

- Environment setup: `uv sync --locked --python 3.14`.
- Python iteration: `uv run ruff check <paths>`, `uv run mypy <paths>`, and `uv run pytest <test-path>`.
- Site source check: `python3 scripts/render_site.py --check`.
- Required final check: `./scripts/verify-template.sh`.
- Use the narrowest relevant check while iterating, but never replace the required final check with a partial result.

## Actions quota fallback

- This repository's plan structurally runs over its included Actions minutes; a zero-step billing block is a standing, accepted operating condition, not an incident. All other failures remain blocked.
- Routine Issue PRs: once local verification passes and every failing check is mechanically confirmed as a zero-step billing block, leave the `Actions quota fallback note` and merge; no separate real-time human confirmation is required.
- Promotion PRs to `main` keep the stricter two-party attestation and authorization procedure.
- Follow the complete SHA/tree-bound procedure, including the non-release promotion path, in [`docs/ci-policy.md`](docs/ci-policy.md#actions-額度-fallback). Never create or falsify a successful Check Run.

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
- Do not bypass required checks, human approval, CODEOWNER review, or supply-chain verification except for the exact quota-only, SHA-bound local verification fallback defined above; that exception does not waive human authorization or any non-local control.
- Alpha 階段允許作者自行合併；在 PR 內文加註 `Alpha 自行合併 / self-merged`，作為 working loop 中「never merge it yourself」規則的已知例外。

## Code Review Rules

- Flag documentation or slide claims that do not match files the template actually creates.
- Flag changes that reduce required checks, permissions safety, artifact verification, or product-source preservation during Copier updates.
- Require tests for behavior changes and synchronized lockfile updates for dependency changes.
- Treat public interfaces, release behavior, workflow permissions, and secret handling as high-risk review areas.
