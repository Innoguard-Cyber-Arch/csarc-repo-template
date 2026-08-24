# Repository instructions

## Scope and sources of truth

- This file applies to the whole repository. Add a nearer `AGENTS.md` only when
  a subtree genuinely needs different commands, ownership, or safety rules.
- Treat this file as the entry point for AI instructions; `CLAUDE.md` only
  imports it, and task-specific details live in the linked repository docs.
- `README.md` is the adopter quick start, this file is the contributor
  contract, and `docs/index.html` is the decision appendix. Link across those
  layers instead of copying workflow rules.
- Treat `copier.yml`, `template/`, `policies/`, and `profiles/catalog.yaml`
  as the product. `template/` is what downstream repositories receive; root
  configuration governs this template repository.
- Use `docs/specs/` for accepted capability contracts and `docs/decisions/`
  for architecture, tooling, security, compatibility, and platform decisions.
- Edit the root presentation in `site/`, then rebuild `docs/index.html`;
  never hand-edit the generated bundle or claim a capability the template does
  not create and verify.

## Working loop

1. At the start of every task, run `./scripts/cleanup-worktrees` in its default
   dry-run mode and report any candidates; this startup safety net does not
   replace the creator's cleanup duty below.
2. Before planning or opening an Issue or Milestone, list open Milestones and
   open Issues, then search open and closed Issues with two to four concrete
   terms and at most 20 results per query. Inspect the body, comments, and linked
   pull requests of credible matches; titles and labels alone are not decisions.
3. When the user can respond, summarize prior decisions before creating work.
   When creation is already authorized, record each relevant `#N` as preserved,
   superseded, or rejected with a reason in `補充` or Milestone `References`;
   if none were found, record the bounded queries. Never store a raw conversation
   transcript or promote an unconfirmed inference. Never silently reverse an
   earlier decision.
4. Open or select one Issue before editing and keep its acceptance criteria as
   the scope boundary. Titles use 12-80 ASCII characters and at least three
   words, with no type prefix or trailing period. Issues use `類型`, `問題`,
   `完成條件`, and optional `補充`; pull requests use `Purpose`, `完成清單`,
   and optional `補充`, whether creating through the UI, CLI, or API.
5. Start from the Issue's delivery branch
   (`dev/m<milestone-number>-<slug>` or `dev/next`), or from an open work
   branch whose pull request chain ends there. Name normal branches
   `type/<issue-number>-short-slug`. Read `docs/ci-policy.md` before using an
   isolated `dev/i*`, hotfix, sync, promotion, canary, or release path.
6. Inspect the implementation, tests, and configuration; make the smallest
   coherent change and preserve unrelated user work. If the scope grows, stop
   and open a separate Issue.
7. Add or update the narrowest regression check that proves non-trivial
   behavior. Run targeted checks while iterating and the required final check
   before a PR.
8. Before using `Closes`, `Fixes`, or `Resolves`, complete every task in the pull
   request and referenced Issue. Open an Issue PR against its delivery branch or
   immediate parent in the stack. Never merge it yourself unless the repository
   explicitly permits author self-merge and every applicable gate is satisfied.
9. After a PR is merged, its worktree creator must leave that worktree, fetch
   the integration branch, and run `./scripts/cleanup-worktrees --apply
   --worktree <path> origin/<delivery-branch>` from another checkout. For
   abandoned work, remove only a clean worktree you created and keep the branch.
   Never remove a platform-managed, dirty, current, locked, detached, unmerged,
   or unverifiable worktree.
10. Report changed behavior, verification evidence, and remaining limitations.

A Milestone is an optional, independently verifiable story outcome, not an
Issue-count bucket. Follow `docs/milestone-description.md` when planning one;
do not attach its PRs as duplicate progress. Keep its promotion Issue open until
the acceptance criteria and promotion evidence are complete.

Parallel writable agents use one branch and one Git worktree per task, and only
independent tasks may run concurrently. Reuse a host-managed worktree when
present and never force one branch into multiple worktrees. Worktrees isolate
files, not review or integration.

If an authorized change alters an Issue or PR body shape, migrate existing
bodies before closing its Issue or create and link a follow-up Issue first. For
existing-repository adoption and migration, follow `docs/agent-install.md`.

## Commands

- Environment: `uv sync --locked --python 3.14`.
- Fast repository check: `./scripts/verify-fast`.
- Python iteration: `uv run ruff check <paths>`, `uv run mypy`, and
  `uv run pytest <test-path>`.
- Site check: `uv run python scripts/render_site.py --check`.
- Required final check: `./scripts/verify-template.sh`.
- Generated repositories use `./scripts/verify`; targeted checks never replace
  the applicable final check.

## Actions quota fallback

- Use the fallback only after a human maintainer with billing visibility
  confirms that the current period's included GitHub Actions minutes are
  exhausted. Payment, budget, platform, workflow, permission, unknown, and
  started-job failures remain blocked.
- Follow `docs/ci-policy.md#actions-quota-fallback` exactly. Its SHA-bound local
  verification, attestation, human authorization, non-local control, and later
  hosted-check requirements are mandatory.

## Editing boundaries

- Keep shared policy changes synchronized between root and `template/`
  wherever both layers consume them.
- Do not weaken generated-project checks to make template tests pass.
- Keep third-party GitHub Actions pinned to full commit SHAs with readable tags
  in comments.
- Generate lockfiles with uv or pnpm; never hand-edit integrity metadata.
- Use local temporary projects or this repository for validation; do not create
  a separate GitHub repository.
- Do not add a language, deployment target, integration, or placeholder config
  without a real consumer.
- Write source-code comments in English. Keep formatting and lint details in
  executable configuration instead of duplicating them here.

## Platform capability and automation

- Keep CI/CD behavior declarative and tested. Do not assume organization or
  enterprise administrator access.
- The portable baseline must not require a GitHub App, PAT, copied personal
  token, populated `.env`, or organization-policy change. Never persist
  `gh auth token` as project configuration.
- Represent capabilities as allowed, blocked, or unknown. Select the strongest
  safe supported mode and state any artifact-only or verification-only
  fallback; never report a skipped or blocked operation as successful.
- Pull request titles declare SemVer intent; assign exact versions only from
  merged default-branch history. Keep registry and cloud trust bootstrap
  optional and verifiable.

## Safety

- Never commit secrets, tokens, private keys, or populated `.env` files.
- Review repository-settings plan output before apply; do not operate production
  or external infrastructure without explicit authorization.
- Do not bypass required checks, human approval, CODEOWNER review, or
  supply-chain verification except for the exact quota fallback above. It never
  waives human authorization or a non-local control.
- Alpha permits author self-merge only after all documented gates pass; record
  `Alpha 自行合併 / self-merged` in the PR body.

## Code Review Rules

- Flag documentation or slide claims that do not match files the template
  creates.
- Flag reductions in required checks, permission safety, artifact verification,
  or product-source preservation during Copier updates.
- Require tests for behavior changes and synchronized lockfile updates for
  dependency changes.
- Treat public interfaces, releases, workflow permissions, and secret handling
  as high-risk review areas.
