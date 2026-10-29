# AI Security Scanner Readiness

This page prepares the repository for a separately authorized AI security
review. CSARC validation never runs an AI security scanner, and nothing here
authorizes a scan.

## Policy chain

Root `SECURITY.md`, or a nearer one for a real component, is the scanner
threat model; `.github/SECURITY.md` is the separate human disclosure policy.
`AGENTS.md` lists the validation commands.

## Providers

| Provider | Start a scan | Policy discovery | Output |
| --- | --- | --- | --- |
| Codex Security | Plugin prompt `Use $codex-security:security-scan to scan this repository for security vulnerabilities.`, or `npx @openai/codex-security scan "$REPOSITORY" --output-dir "$SCAN_DIR"` (`--dry-run` validates inputs first) | Reads root and nearer `SECURITY.md`; `AGENTS.md` supplies commands | Manifest, findings, coverage, report, optional SARIF in the chosen private directory |
| Claude Security | `/plugin install claude-security@claude-plugins-official`, then `/claude-security` and **Scan codebase** or **Scan changes** | Automatic `SECURITY.md` discovery is unavailable / not established; pass the threat context explicitly | `CLAUDE-SECURITY-<timestamp>/` with Markdown, JSONL, SARIF, and suggested patches that are never applied automatically |

Both providers need their own paid access, consume usage, and are
nondeterministic. Provider behavior changes independently of this repository;
recheck the official documentation before a scan.

## Scope

Include product-owned source plus the `.csarc/scripts/`, `.csarc/policies/`,
`.github/workflows/`, manifests, and release code that actually exist. On a
large repository, focus one real service boundary and record deferred areas.
Keep scan output private, remove unrelated credentials from the environment,
pin the target revision, and review coverage gaps before treating a result as
evidence. Scanner credentials never belong in project configuration.
