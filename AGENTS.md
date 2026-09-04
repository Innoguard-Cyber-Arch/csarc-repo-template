# Repository instructions

## Responsibility map

- GitHub Issues and pull requests define work, progress, and evidence. Approved specs and ADRs preserve durable context; add a plan only for cross-session, high-risk, or hard-to-recover work, and never store raw chat transcripts. Follow [Journey 01](docs/index.html#method) for work-item relationships and fields.
- `AGENTS.md` is the single source for AI working instructions; `CLAUDE.md` only imports it.
- One writable task uses one Git branch and one worktree so concurrent changes stay isolated.
- Reusable validation lives in `scripts/` and tests. `./scripts/verify-fast` is the daily PR gate CI selects by risk (docs or fast); `./scripts/verify-template.sh` is full delivery verification, reserved for Milestone/canary delivery, hotfix, merge queue, manual dispatch, and unknown-risk paths — do not run it locally for an ordinary fast- or docs-tier PR, and after that one genuine local run, a later base-only re-merge of the same PR may skip a repeat local run under the narrow condition in `docs/ci-policy.md` (see working loop step 11). Checked-in files under `.github/workflows/` are the only active GitHub Actions. See [CI/CD settings](docs/index.html#testing) and [`docs/ci-policy.md`](docs/ci-policy.md) for the tier boundary and stage ownership.
- [Journey 08](docs/index.html#governance) and the [`docs/ci-policy.md` quota fallback](docs/ci-policy.md#failure-與-fallback) own review requirements, merge eligibility, Alpha self-merge, and quota fallback. Do not restate or invent exceptions here.
- Copier owns template creation and updates. Follow [Journey 09](docs/index.html#template-release) and [`docs/agent-install.md`](docs/agent-install.md) for existing-repository behavior.

## Scope and sources of truth

- This file applies to the whole repository. Read a nearer `AGENTS.md` only if a future subtree genuinely needs different commands or safety rules.
- Three documents split by audience, each authoritative for its own layer: `README.md` targets general users adopting the template (what it is, whether to use it, how to start); this file targets contributors and agents working in this repository (executable workflow rules); `docs/index.html` is the appendix for decision rationale and technical detail. Do not restate this file's workflow rules in `README.md`; link to it instead.
- Treat `copier.yml`, `template/`, `policies/`, and `profiles/catalog.yaml` as the product.
- `template/` is what downstream repositories receive. Root configuration governs this template repository itself.
- Use root `docs/specs/` for SDD current contracts; `docs/README.md` maps durable project memory.
- Use `docs/adr/` for decisions. In updated projects, also search project-owned `docs/decisions/`; never move or overwrite it automatically.
- Edit the root presentation through the Hugo layers in `site/`: bilingual Markdown belongs in `site/content/`, templates and shortcodes in `site/layouts/`, styles and interactions in `site/static/`, and shared glossary data in `site/data/`. Run `./scripts/build-decision-site` to rebuild `docs/index.html`, `docs/index.en.html`, and the `llms.txt` indexes; do not hand-edit generated outputs. `site/legacy/index.html` is a read-only parity fixture.
- Keep decision records, the deck, and checked-in paths aligned. Do not describe a capability as active unless the template creates and verifies it.

## Working loop

1. At task start, run only `git worktree list --porcelain`; reserve unscoped cleanup for explicit maintenance. Creator cleanup after merge remains required. Before planning or opening an Issue or Milestone, list open Milestones and open Issues, then search open and closed Issues with two to four concrete problem or technology terms. Inspect the body, comments, and linked pull requests of credible matches; titles and labels alone are not decisions. Keep each query bounded to 20 candidates.
2. Use the work-item model in [Journey 01](docs/index.html#method). A Milestone is an optional dated delivery or release bucket; follow `docs/milestone-description.md`. Projects stay disabled.
3. Before creating the work item, present a short prior-decision summary when the user can respond. If creation is already authorized, record each relevant `#N` as preserved, superseded, or rejected with a reason in the Issue supplement or Milestone `References`; when none are found, record the bounded queries used. When a user confirms a durable architecture, tooling, security, compatibility, or platform constraint, summarize it in the work item and update the matching `docs/adr/` record through the scoped pull request. Never store a raw conversation transcript or promote an unconfirmed inference to a decision. Never silently reverse an earlier decision.
4. Use the checked-in Issue form and pull request template whether creating through the UI, CLI, or API; do not create a second body format.
5. Open or select one GitHub Issue before editing and use its acceptance criteria as scope. Titles use 12-80 ASCII characters, at least three words, no type prefix, and no trailing period. Set one native Type, matching label, assignee, and applicable parent and Milestone. The creator is the default owner: UI creators assign themselves, while CLI and agents pass `--assignee @me`; change the assignee only for an explicit handoff.
6. If new work exceeds that Issue, stop and open a separate Issue; do not silently widen the current branch or pull request.
7. Check every acceptance-criteria box in the Issue, and every pull request checklist box, only once it carries real evidence, and finish all of them before opening a pull request or pushing a commit meant to satisfy the closing keyword — not incrementally, box by box, across separate pushes. Each push re-triggers the same PR policy gate; pushing a commit you already know is incomplete guarantees that gate fails, and doing this repeatedly is a retry storm, not progress (#430, PR #448 needed 49 pushes over 13 hours to learn this the hard way). Keep the pull request in draft while work is still incomplete: the acceptance-checklist gate does not enforce completeness on a draft, and revalidates in full the moment it is marked ready for review — see `docs/ci-policy.md`'s "Acceptance-checklist 驗證時機（#573）" section.
8. For a Milestone Issue, start from its one short-lived `dev/m<milestone>-short-slug` delivery branch. For an Issue without a Milestone, start from current `main`; if independent changes must soak or ship together, create a real Milestone instead of a catch-all branch. Use `gh issue develop <issue> --base <base> --name type/<issue-number>-short-slug` for the native Development link. Follow `docs/ci-policy.md` for the explicitly authorized `dev/i*` canary, synchronization, promotion, hotfix, and release-recovery routes. When a pull request is stacked on another work branch, retarget it to the shared integration branch as soon as the base pull request is ready to merge, before that branch is squash-merged and deleted. GitHub auto-closes (does not auto-retarget) a pull request whose base branch no longer exists; recovering it means opening a new pull request from the same head branch, which loses the original PR's number, reviews, and comment history.
9. Inspect the existing implementation, make the smallest coherent change, and preserve unrelated user work.
10. Add or update the narrowest regression check that proves non-trivial behavior.
11. Delegates run scoped or focused checks while iterating. CI selects docs, fast, or full automatically by changed paths and delivery stage (`docs/ci-policy.md`); an ordinary fast- or docs-tier PR relies on that gate and needs no local full run. Only when the PR itself is a full-tier delivery boundary (Milestone/canary delivery, hotfix, merge queue, manual dispatch, or an unknown-risk path) does the pull request owner or integrator run `./scripts/verify-template.sh` once, locally, on the final candidate tree. This "once" is literal, not merely the first time: after that genuine local full green run, a later required re-merge of the same PR that only brings in further upstream base movement — clean merge, zero file overlap with this branch's own already-verified changes, and no touch to verification/CI/policy infrastructure — does not need another local full run; push and trust the hosted `verify` check instead. This is a narrow exception to, not a relaxation of, the full-tier rule; see `docs/ci-policy.md`'s "Base-only re-merge 例外（#468）" section for the precise condition, what does not qualify, and `scripts/check-base-only-remerge` for a checkable version of it.
12. Before any automated PR Ready/Draft, authorization, metadata, or merge write, acquire the remote lease and use `scripts/pr_lifecycle.py`; otherwise remain read-only. Follow Journey 08 rather than duplicating merge rules here.
13. After merge, leave the task worktree and run `./scripts/cleanup-worktrees --apply --worktree <path> origin/<pull-request-base>` from another checkout. Never remove another task's worktree or any dirty, locked, detached, unmerged, or unverifiable worktree.
14. Report what changed, which verification ran, and any remaining limitation.
15. Open every new Issue through `scripts/gh-issue-create` (a thin wrapper that runs `scripts/validate-issue-title` on `--title` before ever calling `gh issue create`), or at minimum run `scripts/validate-issue-title "<title>"` by hand first, so the step 5 title rule is caught locally before the Issue exists rather than after by the hosted Issue triage classification.
16. Before starting or resuming work on an existing branch or pull request, run `scripts/check-branch-fresh <branch>` to confirm local still matches `origin/<branch>`'s current tip. Do not assume local reflects current state just because you worked there recently; origin may have advanced or been force-pushed/rebuilt by someone else since.

Writable agents use one branch and worktree per independent task. Reuse a host-managed worktree; never force a branch into multiple worktrees or remove one owned by another task or with uncommitted changes. Use local storage for active checkouts, worktrees, environments, and caches. If assigned a cloud-synced File Provider path, switch to a local checkout without routine user confirmation; preserve existing changes. Worktrees isolate files; integration still uses PR, CI, review, and final verification.

Never push directly to a delivery branch, invent successful evidence, create or dispatch release tags manually, or bypass the linked governance policy.

Duplicate triage may close an Issue without code changes when it links the canonical Issue and uses GitHub's native duplicate reason. If a change modifies an Issue or pull request body shape, migrate existing bodies before closing it; otherwise create and link a follow-up Issue first.

## Commands

- Environment setup: `uv sync --locked --python 3.14`.
- Python iteration: `uv run ruff check <paths>`, `uv run ty check <paths>`, and `uv run pytest <test-path>`.
- Site source check: `./scripts/build-decision-site --check`.
- Daily PR gate: `./scripts/verify-fast` (same tiered entry point CI runs).
- Full delivery verification: `./scripts/verify-template.sh` once by the pull request owner or integrator, only for a full-tier delivery boundary (see `docs/ci-policy.md`); a single `scripts/verify-stage-*` script reruns one of its stages without paying for the full run.
- Release execution: hosted `release.yml`'s Automatic/Guided publish is a known permanent limitation, not a bug to chase — `GITHUB_TOKEN` cannot prove the Immutable Releases setting and this fails closed by design (#123). Run `scripts/publish-release` locally under the maintainer's own admin identity instead; see `docs/ci-policy.md`'s "hosted 發版路徑的已知限制" section.
- Milestone creation: `scripts/create-milestone` atomically creates the GitHub Milestone (with a real due date) and its tracker Issue together, replacing the old two-step manual UI flow; `python3 scripts/sync_milestone_state.py preflight --repo <repo> --milestone <N>` re-validates an existing Milestone's due date, tracker title, and `Lifecycle Issue: #N` link before work is dispatched under it, instead of waiting for the first PR to fail `Validate Milestone approval` — see `docs/milestone-description.md`.

## Editing boundaries

- Keep shared policy changes synchronized between root and `template/` where both layers consume them.
- Do not weaken generated-project checks to make template tests pass.
- Keep GitHub Actions pinned to full commit SHAs and retain the readable release tag in a comment.
- Do not hand-edit generated lockfiles; use uv or pnpm so integrity metadata stays valid.
- Do not create a separate GitHub repository for testing or validation. Use local temporary projects or this repository's Issues, branches, pull requests, and Actions.
- Do not add a language without executable create, existing-repository adoption, update, and native-toolchain verification. Deployment targets and platform integrations still require a real consuming repository.
- Comments in source code must be written in English. Leave formatting and lint details in their executable configuration instead of duplicating them here.

## Platform capability and automation

- Keep desired automation declarative and testable; do not assume organization or enterprise administrator access.
- Never extract or persist `gh auth token` as project configuration, require a personal token for the portable baseline, or treat a permission error as proof that a capability is available.
- Report blocked or unavailable capability explicitly. Never claim a release, deployment, review gate, or other control succeeded when it was skipped or unsupported.

## Safety

- Never commit secrets, tokens, private keys, or populated `.env` files.
- Review the plan output before applying repository settings; do not operate production or external infrastructure without explicit authorization.
- Do not bypass required checks, review, CODEOWNER approval, or supply-chain verification. Journey 08 is the only source for any merge exception or Alpha self-merge authorization.
- When a shell pipeline's result is read from `$?`, the last stage of that pipeline must be the command actually being judged. `cmd | tail -N; echo $?` reports `tail`'s exit code, not `cmd`'s, and has produced false "it passed" claims in this repository's own Milestone 8 history. To keep both the output and the correct exit code, redirect to a file and check separately: `cmd >log 2>&1; status=$?`. For a pull request's checks specifically, use `scripts/check-pr-policy-status` (see `docs/ci-policy.md`'s "PR policy 逐 step 判讀（#513）" section) instead of grepping `gh run view --log` or trusting `gh pr checks`' job-level output by itself.

## Code Review Rules

- Flag documentation or slide claims that do not match files the template actually creates.
- Flag changes that reduce required checks, permissions safety, artifact verification, or product-source preservation during Copier updates.
- Require tests for behavior changes and synchronized lockfile updates for dependency changes.
- Treat public interfaces, release behavior, workflow permissions, and secret handling as high-risk review areas.
