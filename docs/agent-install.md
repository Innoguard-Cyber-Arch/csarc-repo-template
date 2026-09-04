# CSARC agent install contract

> This file is the **agent's automated install contract** only (the machine-driven
> `csarc init`/`adopt`/`update` flow). Human prerequisite tool installation —
> macOS (Homebrew) and Windows (winget/Chocolatey) commands, split by "install
> and use a csarc-generated project" versus "contribute to this template
> repository itself" — lives in [README.md's Prerequisites
> section](../README.md#前置需求), not here.

1. Resolve the current Git repository root yourself. Ask only when a new
   repository's name or location cannot be inferred unambiguously; do not put
   a guessed path into the user prompt.
2. Use only `https://github.com/Innoguard-Cyber-Arch/csarc-repo-template`.
3. Run the CLI from the verified release commit:
   `uvx --python 3.14 --from 'git+https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git@<verified-full-sha>'`.
   `uv` obtains an isolated Python when needed; never require a global Python
   installation or edit a shell profile or global environment. Before doing
   anything else, run `csarc status <path> --json` (append `csarc` to the
   `uvx` invocation above). It deterministically classifies the repository
   into exactly one of five states — `create`, `adopt`, `update`, `current`,
   or `policy-only-update` — from `.csarc/config.yml`, the pinned Copier
   revision, and `policies/` drift; the classification logic lives entirely
   in the CLI, so never infer the state from context, memory, or free-form
   judgment, and running it again against unchanged repository state always
   returns the same answer. Follow the returned `next_command`: for
   `create`, `adopt`, or `update`, run the matching `csarc init`, `adopt`, or
   `update` command as a dry-run first; `adopt` and `adopt --finalize`
   default to dry-run when no `--apply-plan` is supplied. `current` needs no
   action. `policy-only-update` means the Copier revision is already current
   but live repository settings have drifted from `policies/`; skip Copier
   entirely and run `scripts/apply-repository-settings.sh plan`, then
   `apply` after the confirmation in step 5 — never rerun a full adopt or
   update just to change a policy setting. For a release-specific request,
   pass both `--to` and `--expected-sha`. Before `init` or `adopt`, confirm
   the project description,
   shortest working product command, and security reporting channel. For an
   existing repository, separately confirm an optional repository-relative
   executable `project_verification_hook`; the product run command is never a
   verification hook. The hook must not resolve to or re-enter canonical
   `scripts/verify`; update checks validate it before any target write. The
   default channel is the repository's public GitHub Issues page; warn users
   never to post secrets, credentials, personal data, or other sensitive
   details there. Never invent an email address, acknowledgement window, or
   resolution SLA.
4. Summarize the verified release, full commit SHA, release capability
   preflight, settings, conflict risk, and every file classified as add,
   overwrite, preserve, automatic merge, manual merge, or unable to determine.
   Review the generated Markdown and machine plan, plus the PDF when available,
   including the exact project verification hook path, result, and reason,
   then report
   the terminal's separate Milestone
   description classifications: upgrade, current, or manual review. Neither
   source guarantees the absence of semantic or runtime conflicts. Unknown
   capabilities are resolved by the runtime workflow and never treated as
   allowed.
5. Stop and wait for explicit confirmation before changing files.
   Treat an unverified `code_owner` as unknown and call it out before accepting
   the plan; a confirmed missing team is blocking.
6. After confirmation, apply an adoption only with the exact machine plan
   emitted by dry-run and `--yes --non-interactive`. For init or update, reuse
   the resolved tag and full SHA explicitly. Report the `./scripts/verify`
   result. If adoption creates a resumable manual-merge checkpoint, complete
   only the listed merges, run `adopt --finalize --dry-run`, review its new
   external plan, wait for confirmation again, then use `adopt --finalize
   --apply-plan PATH`. Direct finalize and any unplanned working-tree or manual
   result drift must stop.
7. Stop on any identity, immutability, attestation, signature, SHA,
   provenance, plan-drift, verification, or merge-conflict failure. Do not
   stash or commit existing user work. A failed adoption must leave the target
   unchanged or in its explicit resumable pending state.
8. Do not apply repository settings, change global agent configuration, push,
   open a pull request, or merge unless the user separately requests it.
9. During handoff, point out that the installed `AGENTS.md` requires a bounded
   search of open and closed Issues before creating an Issue or Milestone, and
   requires prior decisions and any reversal rationale to remain in the new
   work item. A confirmed adopt or update upgrades only recognized legacy
   CSARC Milestone descriptions; custom descriptions remain unchanged for
   manual review.
10. Existing-repository history changes start read-only: propose semantic
    story groups and exclusions, wait for explicit confirmation, then create
    or update Milestones and associations idempotently. Never infer groups
    from titles or labels alone, require every historical Issue to have a
    Milestone, or reopen completed Issues.
11. Explain that a closing pull request is rejected while either its own
    checklist or the referenced Issue still contains an unchecked task; the
    user must supply the missing evidence instead of checking it speculatively.
12. Explain that repository settings are not copied by GitHub templates or
    Copier. Administrators should run `apply-repository-settings.sh` in
    `plan`, `apply`, then `check` order; `check` compares repository, Actions,
    policy labels, and effective Rulesets. Report `DEGRADED` capability limits
    separately from actionable drift. The built-in `GITHUB_TOKEN` cannot read
    every administrator-only field; run the full check from a trusted checkout
    with repository Administration read access, and never expose that token to
    untrusted pull request code.
13. Beyond GitHub-plan probing, `scripts/check-repo-capabilities` reports which
    of this specific repository's own capabilities/permissions (Ruleset
    enforcement, CODEOWNERS review, Actions PR auto-approval, security
    scanning, GitHub Pages, and more) are `allowed`, `blocked`, or `unknown`
    against `policies/capability-matrix.json`, plus the documented workaround
    for each gap. It never writes anything, so an agent may run it and report
    the result without separate confirmation. See the "Advanced" appendix on
    the internal decision site (`docs/index.html#advanced-install`) for the
    full matrix and how to read a result.
