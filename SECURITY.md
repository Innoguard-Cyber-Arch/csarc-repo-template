# Security Review Policy

This file provides repository-wide context for human reviewers and AI security
scanners. Vulnerability reporting and supported versions are defined in
[`.github/SECURITY.md`](.github/SECURITY.md).

## System and Scope

Review checked-in product code and repository automation together.

In the CSARC template repository, the relevant implementation includes
`src/csarc_cli/`, `scripts/`, `template/`, `policies/`, and
`.github/workflows/`. In a generated or adopted repository, it includes the
project-owned source plus `.csarc/scripts/`, `.csarc/policies/`, and
`.github/workflows/`. Only paths that actually exist are applicable.

Read `README.md`, language manifests, `.csarc/config.yml` when present, and
`AGENTS.md` before selecting commands or inferring runtime behavior. Do not
infer deployed services, data classifications, identities, or protocols that
the repository does not define.

## Threat Model and Trust Boundaries

Treat repository content, Git metadata and configuration, file paths and
symlinks, template answers, Issue and pull-request metadata, workflow event
data, external command output, and downloaded release metadata or artifacts as
untrusted until validated.

Important boundaries are:

- read-only inspection versus approved execution or mutation;
- pull-request-controlled content versus trusted base-revision automation;
- self-attested local merge evidence versus trusted hosted merge evidence;
- CSARC-managed files versus project-owned files;
- source revisions versus published release artifacts.

## Security Invariants

- Status, planning, and dry-run operations must not execute target-controlled
  code or modify the target repository.
- Product verification hooks may run only after approval of an exact,
  unchanged plan.
- Repository writes must remain inside the selected target, reject symlink
  escapes and unexpected file types, and preserve the target on failure.
- Pull-request lifecycle mutations must use the repository's authorized
  single-writer path and a fresh remote lease.
- Untrusted pull-request code must not receive administrator credentials or
  control trusted workflow logic.
- Verification must bind the exact head and tree, base, tier, scopes, command,
  result, and freshness. Hosted mode additionally requires the repository,
  toolchain, and trusted producer identity; local mode must remain explicitly
  self-attested and use the audited lifecycle/admin-bypass path.
- Template adoption and updates must preserve project-owned files, surface
  collisions, and fail closed on ambiguous ownership or drift.
- Releases must bind the expected repository, tag, revision, artifact digest,
  and authorized single writer.
- Secrets and credentials must remain outside committed files and shared logs.

## Reportable Findings and Severity Context

Report a finding when checked-in behavior provides a realistic path to violate
one of the invariants above.

Unauthorized code execution, credential disclosure, writes outside the target,
forged merge evidence, release-artifact substitution, or destructive loss of
project-owned data are high impact when reachable through a supported path.
Lower severity requires a correspondingly bounded and reproducible impact.
Tests and configuration demonstrate intended controls but are not proof that a
finding is unreachable.

## Out of Scope, Exclusions, and Accepted Risk

- Vulnerabilities solely inside an upstream dependency belong upstream.
  Unsafe use, insecure integration, or a dependency compromise that bypasses
  this repository's controls remains in scope.
- Do not invent findings for authentication, tenants, databases, OAuth,
  webhooks, sessions, tokens, services, or deployment surfaces absent from the
  checked-in repository.
- A GitHub plan or permission limitation is not itself a vulnerability when
  the repository reports it accurately and fails closed.
- Local verification accepts that a repository writer can forge its
  self-attested evidence. It protects against stale or accidental mismatch,
  not a malicious maintainer, and must never be presented as hosted or release
  provenance.
- No vulnerability class is otherwise broadly excluded.

## Known Limitations and Compensating Controls

External GitHub behavior and administrator-owned settings require live
readback; checked-in desired policy alone cannot prove enforcement.

Generated and adopted repositories may have product-specific assets, exposure,
and trust boundaries that this shared baseline cannot infer. Their owners must
add evidence-backed details here or in a nearer `SECURITY.md`. Missing context
is an open question, not authority to suppress a finding.
