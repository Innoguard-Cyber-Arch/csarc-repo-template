# Repository instructions

## Milestone 8 temporary operating mode

- CI/CD and dependency-update automation are suspended. Do not add workflow files under `.github/workflows`, enable GitHub Actions, dispatch workflows, apply required status checks, or make CI a merge condition.
- Review and implement one documentation page or section at a time. Maintainer-approved wording is the specification for that page; do not infer adjacent product work.
- Use the smallest relevant local check for the page being changed. The legacy full verification and release procedures below are historical guidance until their replacement is explicitly approved.
- Resume an automated workflow only through a separate Issue that states its purpose, trigger, required status, and cost ceiling.

## Scope and sources of truth

- This file applies to the whole repository. Read a nearer `AGENTS.md` only if a future subtree genuinely needs different commands or safety rules.
- Treat this file as the single source for AI instructions; `CLAUDE.md` only imports it.
- Three documents split by audience, each authoritative for its own layer: `README.md` targets general users adopting the template (what it is, whether to use it, how to start); this file targets contributors and agents working in this repository (executable workflow rules); `docs/index.html` is the appendix for decision rationale and technical detail. Do not restate this file's workflow rules in `README.md`; link to it instead.
- Treat `copier.yml`, `template/`, `policies/`, and `profiles/catalog.yaml` as the product.
- `template/` is what downstream repositories receive. Root configuration governs this template repository itself.
- Use root `docs/specs/` for SDD current contracts; `docs/README.md` maps durable project memory.
- Use `docs/adr/` for decisions. In updated projects, also search project-owned `docs/decisions/`; never move or overwrite it automatically.
- Edit the root presentation through the Hugo layers in `site/`: bilingual Markdown belongs in `site/content/`, templates and shortcodes in `site/layouts/`, styles and interactions in `site/static/`, and shared glossary data in `site/data/`. Run `./scripts/build-decision-site` to rebuild `docs/index.html`, `docs/index.en.html`, and the `llms.txt` indexes; do not hand-edit generated outputs. `site/legacy/index.html` is a read-only parity fixture.
- Keep decision records, the deck, and checked-in paths aligned. Do not describe a capability as active unless the template creates and verifies it.

## Working loop

1. At task start, run only `git worktree list --porcelain`; reserve unscoped cleanup for explicit maintenance. Creator cleanup after merge remains required. Before planning or opening an Issue or Milestone, list open Milestones and open Issues, then search open and closed Issues with two to four concrete problem or technology terms. Inspect the body, comments, and linked pull requests of credible matches; titles and labels alone are not decisions. Keep each query bounded to 20 candidates.
2. Use native Feature for an SDD story and Task or Bug subissues for independently deliverable work. Dependencies only express real ordering; a Bug inside a Feature must be its subissue, while a standalone Bug explains why it has no parent. Projects stay disabled. A Milestone is an optional dated delivery or release bucket: set a real due date, attach leaf Issues and PRs, omit the parent, and follow `docs/milestone-description.md`.
3. Before creating the work item, present a short prior-decision summary when the user can respond. If creation is already authorized, record each relevant `#N` as preserved, superseded, or rejected with a reason in the Issue supplement or Milestone `References`; when none are found, record the bounded queries used. When a user confirms a durable architecture, tooling, security, compatibility, or platform constraint, summarize it in the work item and update the matching `docs/adr/` record through the scoped pull request. Never store a raw conversation transcript or promote an unconfirmed inference to a decision. Never silently reverse an earlier decision.
4. Use the exact checked-in body shape whether creating through the UI, CLI, or API: Issues use `類型`, `問題`, `完成條件`, and optional `補充`; pull requests use `Purpose`, `完成清單`, and optional `補充`. Fold verification, risk, rollback, impact, and decision details into those sections instead of adding parallel top-level sections.
5. Open or select one GitHub Issue before editing and use its acceptance criteria as scope. Titles use 12-80 ASCII characters, at least three words, no type prefix, and no trailing period. Set one native Type, matching label, assignee, and applicable parent and Milestone.
6. If new work exceeds that Issue, stop and open a separate Issue; do not silently widen the current branch or pull request.
7. Start from the Issue's delivery branch (`dev/m<milestone-number>-<slug>` for a Milestone or `dev/next` when standalone), or from an open work branch whose pull request chain ends there. Use `gh issue develop <issue> --base <delivery> --name type/<issue-number>-short-slug` for the native Development link. For a conflicting squash-sync, use the matching `promote/m<milestone-number>-<slug>` or `promote/next` bridge per `docs/ci-policy.md`; never rewrite delivery. A standalone Issue needing an independent soak or canary may instead use `dev/i<issue-number>-<slug>`; its Issue must have no Milestone, use the `promotion` label, and close only through that branch's promotion PR. Only a qualified `fix/*` pull request labeled `hotfix` or `release-recovery` may otherwise target `main` directly.
8. Inspect the existing implementation, make the smallest coherent change, and preserve unrelated user work.
9. Add or update the narrowest regression check that proves non-trivial behavior.
10. Delegates run scoped checks; only the pull request owner or integrator runs `./scripts/verify-template.sh` once per final candidate tree.
11. Keep a final `promotion` Issue open while work lands in a delivery Milestone. If downstream acceptance needs an immutable Release first, use the `docs/ci-policy.md` checkpoint contract; otherwise add no intermediate promotion. An isolated `dev/i*` Issue is its promotion Issue. Checkboxes cover only pre-merge evidence; put closure/cleanup in a non-checkbox runbook. Before closure, recheck acceptance/evidence. Lifecycle closes a zero-open-Issue Milestone only when all boxes are checked, and reopens it for open work or unchecked criteria.
12. Use `Closes`, `Fixes`, or `Resolves` only after every PR and referenced-Issue item has evidence. Target the delivery branch or immediate stack parent; only promotion, release-please, qualified hotfix, or audited release recovery may target `main`. Keep the PR assignee, classification label, and Milestone synchronized from the linked Issue, and request a non-author reviewer when it leaves draft. Before any automated PR Ready/Draft, authorization, label/milestone, or merge write, acquire its remote lease and use `scripts/pr_lifecycle.py`; other tasks remain read-only. Never merge except under the documented self-merge and quota fallback.
13. After a pull request is merged, the agent that created its worktree must leave that worktree, fetch its delivery branch, and run `./scripts/cleanup-worktrees --apply --worktree <path> origin/<delivery-branch>` from another checkout. If the task is explicitly abandoned instead, its creator may remove only that clean worktree with `git worktree remove <path>`; keep the branch. Platform-managed worktrees stay under the platform lifecycle. For repository-wide maintenance, review the command's default dry run before omitting `--worktree`; it never removes main, current, locked, detached, dirty, unmerged, or unverifiable worktrees.
14. Report what changed, which verification ran, and any remaining limitation.

Writable agents use one branch and worktree per independent task. Reuse a host-managed worktree; never force a branch into multiple worktrees or remove one owned by another task or with uncommitted changes. Use local storage for active checkouts, worktrees, environments, and caches. If assigned a cloud-synced File Provider path, switch to a local checkout without routine user confirmation; preserve existing changes. Worktrees isolate files; integration still uses PR, CI, review, and final verification.

Delivery routes, synchronization, promotion, release, canary, rollback, and quota procedures are canonical in [`docs/ci-policy.md`](docs/ci-policy.md). Never push directly to a delivery branch, invent successful canary evidence, create or dispatch release tags manually, or bypass its gates. Existing-repository lifecycle details are canonical in [`docs/agent-install.md`](docs/agent-install.md).

Duplicate triage may close an Issue without code changes when it links the canonical Issue and uses GitHub's native duplicate reason. If a change modifies an Issue or pull request body shape, migrate existing bodies before closing it; otherwise create and link a follow-up Issue first.

## Commands

- Environment setup: `uv sync --locked --python 3.14`.
- Python iteration: `uv run ruff check <paths>`, `uv run mypy <paths>`, and `uv run pytest <test-path>`.
- Site source check: `./scripts/build-decision-site --check`.
- During Milestone 8, use the narrowest relevant local check for the approved page or section.
- `./scripts/verify-template.sh` belongs to the suspended CI/CD design and is not a merge requirement while this temporary mode is active.

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
- Alpha self-merge only covers a non-default routine Issue PR with a lease, exact authorization, all gates, and the exact body marker `Alpha 自行合併 / self-merged`; sync, main, hotfix, and release routes remain reviewed.

## Code Review Rules

- Flag documentation or slide claims that do not match files the template actually creates.
- Flag changes that reduce required checks, permissions safety, artifact verification, or product-source preservation during Copier updates.
- Require tests for behavior changes and synchronized lockfile updates for dependency changes.
- Treat public interfaces, release behavior, workflow permissions, and secret handling as high-risk review areas.
