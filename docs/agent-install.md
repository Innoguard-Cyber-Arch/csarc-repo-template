# CSARC agent install contract

1. Confirm the target path is the repository requested by the user.
2. Use only `https://github.com/Innoguard-Cyber-Arch/csarc-repo-template`.
3. Run the requested `csarc init`, `adopt`, or `update` command with
   `--dry-run` first. For a release-specific request, pass both `--to` and
   `--expected-sha`.
4. Summarize the verified release, full commit SHA, release capability
   preflight, settings, conflict risk, and every file classified as add,
   overwrite, preserve, or manual merge. Unknown capabilities are resolved by
   the runtime workflow and never treated as allowed.
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
   work item.
