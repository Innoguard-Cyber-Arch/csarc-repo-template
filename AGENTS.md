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

1. At task start, check open Draft PRs, remote branches, and existing worktrees with `git worktree list --porcelain`; reserve unscoped cleanup. Before planning or opening an Issue or Milestone, list open Milestones and open Issues, then search open and closed Issues with two to four concrete problem or technology terms. Inspect the body, comments, and linked pull requests of credible matches; titles and labels alone are not decisions. Keep each query bounded to 20 candidates.
2. Use native Feature for an SDD story and Task or Bug subissues for independently deliverable work. Dependencies only express real ordering; a Bug inside a Feature must be its subissue, while a standalone Bug explains why it has no parent. Projects stay disabled. A Milestone is an optional dated delivery or release bucket: set a real due date, attach leaf Issues and PRs, omit the parent, and follow `docs/milestone-description.md`.
3. Before creating the work item, present a short prior-decision summary when the user can respond. If creation is already authorized, record each relevant `#N` as preserved, superseded, or rejected with a reason in the Issue supplement or Milestone `References`; when none are found, record the bounded queries used. When a user confirms a durable architecture, tooling, security, compatibility, or platform constraint, summarize it in the work item and update the matching `docs/adr/` record through the scoped pull request. Never store a raw conversation transcript or promote an unconfirmed inference to a decision. Never silently reverse an earlier decision.
4. Use the exact checked-in body shape whether creating through the UI, CLI, or API: Issues use `類型`, `問題`, `完成條件`, and optional `補充`; pull requests use `Purpose`, `完成清單`, and optional `補充`. Fold verification, risk, rollback, impact, and decision details into those sections instead of adding parallel top-level sections.
5. Open or select one GitHub Issue before editing and use its acceptance criteria as scope. Titles use 12-80 ASCII characters, at least three words, no type prefix, and no trailing period. Set one native Type, matching label, assignee, and applicable parent and Milestone.
6. If new work exceeds that Issue, stop and open a separate Issue; do not silently widen the current branch or pull request.
7. Use short-lived `dev/m<milestone-number>-<slug>` for Milestones; other work uses `main`. Create the native Development link with `gh issue develop <issue> --base <integration> --name type/<issue-number>-short-slug`, then stack toward that integration branch. Ordinary PRs need only delivery. Sync `main` at final promotion; early sync needs an owner-recorded dependency. Use matching `promote/m<milestone-number>-<slug>` for conflicts; never rewrite delivery. `main` is permanent.
8. Inspect the existing implementation, make the smallest coherent change, and preserve unrelated user work.
9. Add or update the narrowest regression check that proves non-trivial behavior.
10. Run targeted checks while iterating. After they pass, push a Draft PR stating scope, completed and pending verification, risks, and dependencies. Issue owners run the CI plan's scoped checks. On final integration, Ready starts the hosted `./scripts/verify-template.sh` gate once per final candidate tree; local only under documented fallback, not after hosted success. Draft updates need proportionate targeted checks.
11. Create a final Issue labeled `promotion` when planning a delivery Milestone, and keep it open while work merges into the Milestone branch. Before closing it, re-check the acceptance criteria and promotion evidence. The lifecycle workflow closes a zero-open-Issue Milestone only when every acceptance checkbox is checked, and reopens it when open work or an unchecked criterion returns.
12. Drafts use `Refs #N`; Ready uses a closing keyword only after every PR and Issue item has evidence. Milestone work targets delivery or its stack parent; standalone, hotfix, bot, release-please, and promotion work may target `main`. Keep Issue/PR metadata aligned and request a non-author reviewer outside Draft. Before automated state, metadata, authorization, or merge writes, acquire the remote lease with `scripts/pr_lifecycle.py`; other tasks stay read-only. Merge only under documented self-merge or quota fallback.
13. After a pull request is merged, the agent that created its worktree must leave that worktree, fetch its delivery branch, and run `./scripts/cleanup-worktrees --apply --worktree <path> origin/<delivery-branch>` from another checkout. If the task is explicitly abandoned instead, its creator may remove only that clean worktree with `git worktree remove <path>`; keep the branch. Platform-managed worktrees stay under the platform lifecycle. For repository-wide maintenance, review the command's default dry run before omitting `--worktree`; it never removes main, current, locked, detached, dirty, unmerged, or unverifiable worktrees.
14. Report what changed, which verification ran, and any remaining limitation.

Writable agents use one branch and worktree per independent task. Reuse a host-managed worktree; never force a branch into multiple worktrees or remove one owned by another task or with uncommitted changes. Use local storage for active checkouts, worktrees, environments, and caches. If assigned a cloud-synced File Provider path, switch to a local checkout without routine user confirmation; preserve existing changes. Worktrees isolate files; integration still uses PR, CI, review, and final verification.

Delivery routes, synchronization, promotion, release, canary, rollback, and quota procedures are canonical in [`docs/ci-policy.md`](docs/ci-policy.md). Never push directly to a delivery branch, invent successful canary evidence, create or dispatch release tags manually, or bypass its gates. Existing-repository lifecycle details are canonical in [`docs/agent-install.md`](docs/agent-install.md).

Duplicate triage may close an Issue without code changes when it links the canonical Issue and uses GitHub's native duplicate reason. If a change modifies an Issue or pull request body shape, migrate existing bodies before closing it; otherwise create and link a follow-up Issue first.

## Commands

- Environment setup: `uv sync --locked --python 3.14`.
- Python iteration: `uv run ruff check <paths>`, `uv run mypy <paths>`, and `uv run pytest <test-path>`.
- Site source check: `python3 scripts/render_site.py --check`.
- Final delivery: one hosted `./scripts/verify-template.sh` on the unchanged tree, or one local run only for documented fallback.
- Issue work: run the CI plan's narrowest scoped checks; do not duplicate the final delivery check.

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
- Dependabot targets `main`; routine updates wait three days and remain one PR per update, while security updates do not wait. Add grouping only for an explicit security-reviewed allowlist.
- Keep external trust bootstrap such as package-registry publishers or cloud identities optional and verifiable. Do not bypass or silently weaken platform policy to make automation pass.
- Keep the website aligned with the capability matrix. For each policy-dependent mode, document its prerequisites, selected behavior, guarantees, limitations, and fallback without presenting unavailable capabilities as active.

## Safety

- Never commit secrets, tokens, private keys, or populated `.env` files.
- Review the plan output before applying repository settings; do not operate production or external infrastructure without explicit authorization.
- Do not bypass required checks, human approval, CODEOWNER review, or supply-chain verification except for the exact quota-only, SHA-bound local verification fallback defined above; that exception does not waive human authorization or any non-local control.
- Alpha self-merge only covers a non-default routine Issue PR with a lease, exact authorization, all gates, and the exact body marker `Alpha 自行合併 / self-merged`; sync, main, hotfix, and release routes remain reviewed.

## Code Review Rules

- Flag documentation or slide claims that do not match files the template actually creates.
- Flag changes that reduce required checks, permissions safety, artifact verification, or product-source preservation during Copier updates.
- Require tests for behavior changes and synchronized lockfile updates for dependency changes.
- Treat public interfaces, release behavior, workflow permissions, and secret handling as high-risk review areas.
