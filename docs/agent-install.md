# CSARC agent install contract

1. Confirm the target path is the repository requested by the user.
2. Use only `https://github.com/Innoguard-Cyber-Arch/csarc-repo-template`.
3. Run the requested `csarc init`, `adopt`, or `update` command with
   `--dry-run` first. For a release-specific request, pass both `--to` and
   `--expected-sha`. For `adopt`, also pass `--report-dir` with a location
   outside the target repository. Before `init` or `adopt`, obtain the
   approved project description, shortest working product command, and
   private security reporting channel. Pass an explicit
   `security_reporting_channel` answer; never invent an email address, URL,
   acknowledgement window, or resolution SLA.
4. Summarize the verified release, full commit SHA, release capability
   preflight, settings, conflict risk, and every file classified as add,
   overwrite, preserve, manual merge, or unable to determine. Review both the
   generated Markdown and PDF, then report the terminal's separate Milestone
   description classifications: upgrade, current, or manual review. Neither
   source guarantees the absence of semantic or runtime conflicts. Unknown
   capabilities are resolved by the runtime workflow and never treated as
   allowed.
5. Stop and wait for explicit confirmation before changing files.
6. After confirmation, repeat the same command with
   `--yes --non-interactive` and report the `./scripts/verify` result.
7. Stop on any identity, immutability, attestation, signature, SHA,
   provenance, verification, or merge-conflict failure. Preserve the diff for
   review.
8. Do not apply repository settings, change global agent configuration, push,
   open a pull request, or merge unless the user separately requests it.
9. During handoff, point out that the installed `AGENTS.md` requires a bounded
   search of open and closed Issues before creating an Issue or Milestone, and
   requires prior decisions and any reversal rationale to remain in the new
   work item. A confirmed adopt or update upgrades only recognized legacy
   CSARC Milestone descriptions; custom descriptions remain unchanged for
   manual review.
10. Explain that a closing pull request is rejected while either its own
    checklist or the referenced Issue still contains an unchecked task; the
    user must supply the missing evidence instead of checking it speculatively.
11. Explain that repository settings are not copied by GitHub templates or
    Copier. Administrators should run `apply-repository-settings.sh` in
    `plan`, `apply`, then `check` order; `check` compares repository, Actions,
    policy labels, and effective Rulesets. Report `DEGRADED` capability limits
    separately from actionable drift. The built-in `GITHUB_TOKEN` cannot read
    every administrator-only field; run the full check from a trusted checkout
    with repository Administration read access, and never expose that token to
    untrusted pull request code.
