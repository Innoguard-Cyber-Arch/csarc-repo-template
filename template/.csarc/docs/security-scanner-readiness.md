# AI Security Scanner Readiness

Verified against official provider documentation on 2026-09-22. This document
prepares the repository for a separately authorized review; none of the
commands in the provider matrix are part of CSARC validation, and this change
does not run an AI security scanner.

## Provider capability matrix

| Capability | Codex Security | Claude / Anthropic |
| --- | --- | --- |
| Repository discovery | The Codex desktop plugin selects a repository or folder. The CLI accepts a local repository path, can discover authorized GitHub repositories for bulk scans, and supports repository, path, committed-diff, working-tree, and deep targets. | The Claude Security plugin first reads the current directory, then offers the whole codebase or a focused area. Change scans accept committed branch, pull-request, or commit diffs; full scans can read an uncommitted working tree. |
| Persistent policy | Root and nested `SECURITY.md` files are documented scan context; the nearest file wins. `AGENTS.md` supplies build and validation commands. | The cited Claude Security documentation does not document automatic `SECURITY.md` discovery, so that capability is **unavailable / not established**. Claude Code 2.1.277+ can load `AGENTS.md` directly in supported sessions; the committed thin `CLAUDE.md` import covers sessions where direct loading is unavailable. |
| On-demand command | Plugin prompt: `Use $codex-security:security-scan to scan this repository for security vulnerabilities.` CLI: `npx @openai/codex-security scan "$REPOSITORY" --output-dir "$SCAN_DIR" --dry-run` validates inputs, and the same command without `--dry-run` starts a scan. These are reference commands, not CSARC validation. | Install in Claude Code with `/plugin install claude-security@claude-plugins-official`; run `/claude-security` and choose **Scan codebase** or **Scan changes**. `/security-review` is a separate single-pass branch review, not the multi-agent plugin. These are reference commands, not CSARC validation. |
| Result handoff | CLI output includes a manifest, findings, coverage, report, and optional SARIF in the selected private output directory. Interactive accepted findings can become separate patch tasks; `--create-pr` is optional and must be separately authorized. | A scan writes `CLAUDE-SECURITY-<timestamp>/` in the checkout with Markdown, JSONL, SARIF, and a revision stamp. Suggested patches are reviewed and written under `patches/`, but are never applied automatically. |
| Access, cost, and limitations | The public npm package still requires Codex Security access and authentication; full scans may require Trusted Access for Cyber. Local scans inherit OS permissions and environment without pausing for approval. Node.js 22.13+ / 24 / 26 is required, and scan/history/export features also require Python 3.10+. Results can contain source or credentials. | The plugin requires a paid Claude plan, dynamic workflows, Python 3.9+, and an open local Claude Code session. Each scan consumes plan usage and is nondeterministic. Pull-request discovery is the only documented network step and requires an already authorized `gh`; the managed monitoring product is a separate Enterprise service. |

Official sources:

- [Codex Security overview](https://developers.openai.com/codex/security)
- [Codex Security plugin scans](https://developers.openai.com/codex/security/plugin/scans)
- [Codex Security CLI quickstart](https://developers.openai.com/codex/security/cli)
- [Claude Security plugin](https://code.claude.com/docs/en/claude-security)
- [Claude Code project instructions](https://code.claude.com/docs/en/memory)

Provider behavior changes independently of this repository. Recheck the
official pages before a future scan instead of treating this matrix as a
permanent provider contract.

## Policy and lifecycle chain

| Lifecycle | Scanner policy | Human disclosure | Agent and command discovery |
| --- | --- | --- | --- |
| This template repository | Root `SECURITY.md` applies repository-wide. No nested scanner policy exists. | `.github/SECURITY.md` owns supported versions and the public reporting channel. | Root `AGENTS.md`, with this document as its command inventory. Root `CLAUDE.md` imports `AGENTS.md`. |
| New generated repository | The paired root `SECURITY.md` baseline is created. A nearer project-owned policy may later narrow a real component. | `.github/SECURITY.md` is rendered from the approved `security_reporting_channel`. | Root `AGENTS.md` links `.csarc/docs/agent-workflow.md` and this paired document. `.claude/CLAUDE.md` imports the root entry point. |
| Existing repository adopt or update | A pre-existing root `SECURITY.md` is project-owned and preserved. When none exists, Copier can add the shared baseline. The preview must surface every collision before an approved write. | A pre-existing `.github/SECURITY.md` is preserved; otherwise the approved reporting channel can create it. | The same managed agent workflow, readiness document, and thin Claude import are added or updated through the reviewed Copier plan. |

`SECURITY.md` and `.github/SECURITY.md` deliberately have different owners and
purposes. Do not merge the scanner threat model into the disclosure page or
copy disclosure details into the scanner policy.

## Repository inventory and realistic scope

The applicable implementation is evidence from checked-in paths, not a
hypothetical deployed system:

- CLI and command execution: `src/csarc_cli/` and the repository-relative
  executable adapters under `scripts/` or `.csarc/scripts/`.
- Filesystem and Git boundaries: dry-run isolation, approved plan replay,
  symlink and special-file rejection, atomic writes, fresh remote leases, and
  exact revision checks.
- Template boundaries: `copier.yml`, `template/`, `.csarc/config.yml`, managed
  versus product-owned paths, new creation, existing adoption, and update.
- Hosted boundaries: `.github/workflows/`, least-privilege permissions,
  pull-request-controlled inputs, trusted check producers, and exact-head
  evidence.
- Supply chain and release boundaries: language manifests and lockfiles,
  downloaded tool checksums, dependency findings, release revisions, artifact
  digests, and single-writer publication.

No checked-in implementation establishes authentication, tenants, databases,
OAuth, webhooks, sessions, application tokens, or a deployed service. A review
must not invent those surfaces.

### Environment, fixtures, and services

- Local routing accepts `CSARC_CI_BASE`, `CSARC_CI_SCOPES`, `CSARC_CI_TIER`,
  `CSARC_CI_DRAFT`, `CSARC_RUN_OSV`, `CSARC_CACHE_ROOT`, `UV_CACHE_DIR`, and
  `CSARC_PYTHON_VERSION`. These select reproducible validation behavior; none
  is a credential.
- Pytest uses `tmp_path`; shell self-tests use temporary directories and fake
  `gh` responses. Generated-project checks copy the local template into a
  temporary repository. They do not need a second GitHub repository.
- `security-smoke` needs only the checked-in scripts plus local Bash, Python 3,
  and Git. It does not contact GitHub or a model provider.
- Hosted policy readback needs an already authorized `gh` identity. Cold-cache
  dependency and tool installation needs network access. Scanner credentials,
  such as `OPENAI_API_KEY`, are only for a separately authorized provider run
  and must not be added to project configuration.

## Exact repository commands

Run the narrow owner command for the files being changed. Angle-bracket
arguments below are caller-supplied paths, not literal placeholders in
configuration.

| Purpose | Template repository | Generated or adopted repository | Cost / service boundary |
| --- | --- | --- | --- |
| Install | `uv sync --locked --python 3.14` | Python: `uv sync --locked`; TypeScript: `corepack enable && pnpm install --frozen-lockfile`; Rust: `rustup show && cargo fetch --locked`; CI-only profile: none | Network and package registries may be needed on a cold cache. No repository credential is required. |
| Build | `uv build` | Python: `uv build`; TypeScript: `pnpm run build`; Rust: `cargo build --locked`; CI-only profile: none | Local toolchain after install. |
| Lint / format check | `uv run ruff format --check src scripts tests && uv run ruff check src scripts tests` | Python: `uv run ruff check <paths>`; TypeScript: `pnpm exec biome check <paths>`; Rust: `cargo fmt --all -- --check` | Local and offline after install. |
| Type / static check | `uv run ty check` | Python: `uv run ty check`; TypeScript: `pnpm exec tsc --noEmit`; Rust: `cargo clippy --locked --all-targets --all-features -- -D warnings` | Local and offline after install. |
| Fastest focused unit | `uv run pytest tests/test_ai_guidelines.py -q` | Python: `uv run pytest tests/test_smoke.py -q`; TypeScript: `pnpm exec vitest run typescript/tests/index.test.ts`; Rust: `cargo test --locked --lib`; CI-only profile: no product unit module | Local and offline after install. |
| One test | `uv run pytest tests/test_ai_guidelines.py::test_thin_imports_and_readme_do_not_duplicate_merge_policy -q` | Python: `uv run pytest tests/test_smoke.py::test_version_matches_installed_distribution -q`; TypeScript: `pnpm exec vitest run typescript/tests/index.test.ts -t "adds two numbers"`; Rust: `cargo test --locked version_is_declared` | Local and offline after install. |
| Security smoke | `./scripts/security-smoke` | `./.csarc/scripts/security-smoke` | Budget: 30 seconds. Offline, no credential, no scanner, and not a routine gate. |
| Broad fast diagnostic | `./scripts/verify-fast` | `./.csarc/scripts/verify-fast` | 120-second repository budget. A cold cache may download pinned tools; the existing secret check runs. |
| Full delivery verification | `./scripts/verify-template.sh` | `./.csarc/scripts/verify` | Full-tier boundary only. Requires selected language toolchains and may use package/tool download networks on a cold cache. |

The generated `AGENTS.md` contains only commands for its selected language
profile. The table above records the complete template capability without
creating a language-by-profile test matrix.

## Security smoke composition and owners

`security-smoke` is a selector, not a new test runner. It invokes four existing
owner self-tests and adds no cases:

1. `test-pr-policy` owns pull-request metadata and lifecycle decisions.
2. `test-apply-repository-settings` owns plan/apply/readback and permission
   boundaries.
3. `test-check-repo-capabilities` owns allowed, blocked, and unknown
   capability reporting.
4. `test-check-scope-gate` owns declared-scope drift detection.

The smoke does not run Codex Security, Claude Security, secret scanning,
dependency scanning, or network probes. `verify-fast` remains the broader
change-routed diagnostic. Full verification already invokes these four owner
tests in its regression stage, so cases are not copied into a provider-specific
suite.

### 2026-09-22 local measurement

Measured in the same worktree and environment. The before command ran the four
owner tests directly; the after command ran `./scripts/security-smoke`, which
selects the same four tests.

| Measure | Before | After |
| --- | ---: | ---: |
| Dedicated security-smoke entry points | 0 | 1 shared selector |
| Selected owner commands | 4 | 4 |
| Direct project + development dependencies | 9 | 9 |
| Collected pytest cases | 1,541 | 1,544 |
| Three wall times | 14.26s, 9.87s, 10.99s | 9.97s, 10.50s, 9.39s |
| Median wall time | 10.99s | 9.97s |

The three added pytest cases validate the shared policy/guidance wiring, the
thin selector, and symlink-safe policy preservation; they do not duplicate any
security behavior case. The
after median is below the declared 30-second smoke budget.

Other risks keep their existing owners: `tests/test_cli.py` covers isolated
plans, target-controlled commands, Git identity, filesystem writes, and
symlinks; `tests/test_authenticate_dependabot_head.py` and
`tests/test_verification_evidence.py` cover trusted revisions and hosted
evidence; `tests/test_dependency_security.py` owns dependency scanning; and
workflow tests own permissions and action pins.

## Suggested future scan scope

These are scope recommendations only; they are not authorization to scan.

- For this template repository, the smallest meaningful initial Codex Security
  or Claude Security codebase scan is the whole repository because CLI,
  template, workflow, and release controls cross directory boundaries. A
  subsequent change review can use the committed branch diff.
- For a generated or adopted repository, include product-owned source plus
  `.csarc/scripts/`, `.csarc/policies/`, `.github/workflows/`, manifests, and
  release code that actually exists. On a large repository, focus one real
  service or component boundary and record deferred areas.
- Codex can use root and nearer `SECURITY.md` policy automatically. Claude's
  documented automatic `SECURITY.md` policy discovery is unavailable, so pass
  relevant threat context explicitly and confirm `AGENTS.md` / `CLAUDE.md`
  loaded before relying on its command inventory.

Keep scan output private, remove unrelated credentials from the environment,
pin the target revision, and review coverage gaps before treating any result
as evidence. Starting either provider remains a separate, explicit action.
