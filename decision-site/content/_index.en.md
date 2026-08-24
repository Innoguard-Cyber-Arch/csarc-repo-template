+++
title = "CSARC Repo Template | AI-assisted SDLC foundation"
notice = "Internal use only — do not share this link publicly"

[controls]
language = "Reading language"
detail = "Reading depth"
simple = "Simple"
technical = "Technical"
slides = "Presentation controls"
previous = "Previous slide"
next = "Next slide"
zoom = "Display zoom controls"
zoom_out = "Zoom out"
zoom_reset = "Fit to screen"
zoom_in = "Zoom in"
fit = "Fit"
+++

{{< slide key="capability" track="capability" eyebrow="CSARC Repo Template" title="An updatable repository foundation" subtitle="Create a new project, adopt an existing one, or receive policy updates through verified pull requests." >}}
The template puts work definition, AI instructions, verification, merging, dependencies, and delivery evidence into one reviewable flow.

- Supports CI/CD-only, Python, TypeScript, and mixed projects.
- New and existing repositories share the same policy sources.
- Daily verification starts with `./scripts/verify`.

{{< detail key="capability-boundary" title="Capability boundary" >}}
The template only claims capabilities backed by executable files and regression checks. Go, Rust, hosting, generic deployment, and monitoring remain future work.
{{< /detail >}}
{{< /slide >}}

{{< slide key="flow" track="flow" eyebrow="Developer journey" title="From a requirement to a deliverable version" subtitle="Every stage has observable input, gates, and evidence." >}}
1. Define an observable outcome in an Issue; create a Milestone only for an end-to-end story.
2. Implement in a numbered branch and isolated worktree; run focused checks before full verification.
3. Preserve intent, review, and CI evidence in the PR; only promotion reaches `main`.

{{< detail key="flow-foundation" title="Across the whole flow" >}}
Rulesets, Copier updates, the internal decision site, and staged adoption are maintained infrastructure rather than manual steps repeated for every change.
{{< /detail >}}
{{< /slide >}}

{{< slide key="files" track="files" eyebrow="Responsibility map" title="File ownership must stay explicit" subtitle="The template can propose updates without silently overwriting product content." >}}
| Category | Examples | Owner |
| --- | --- | --- |
| Working contract | `AGENTS.md`, `README.md` | Shared |
| Verification and policy | `scripts/`, `.github/`, `policies/` | Template-led |
| Product code | `src/`, product tests | Project-owned |

{{< detail key="files-update" title="Update rule" >}}
Copier brings changes through a short branch, leaves conflicts for human review in a PR, and regression tests prevent product-owned directories from being overwritten.
{{< /detail >}}
{{< /slide >}}

{{< slide key="method" track="method" eyebrow="Step 01" title="Define the problem before implementation" subtitle="An Issue bounds implementation; a Milestone is an optional story outcome." >}}
- Inspect open Milestones, open Issues, and relevant closed Issues before work starts.
- Summarize the outcome in an English Issue title; define the problem and acceptance criteria in its body.
- Open another Issue for work outside the boundary instead of hiding it in the current PR.

{{< disclosure key="spec-tracking" title="Specs default to Issues; explicit stories create Milestones" >}}
`docs/specs/*.md` records state in front matter. Only `tracking: story` synchronizes a spec to a Milestone. Synchronization is repeatable and never invents unconfirmed child work.
{{< /disclosure >}}

{{< detail key="method-lifecycle" title="Story lifecycle" >}}
A Milestone closes only when every acceptance item is checked and no Issue remains open. It reopens when an item or Issue becomes open again.
{{< /detail >}}
{{< /slide >}}

{{< slide key="agents" track="agents" eyebrow="Step 02" title="Set the AI working contract first" subtitle="README serves users; AGENTS.md keeps executable boundaries for agents." >}}
- Add a nearer `AGENTS.md` only when a subtree genuinely needs different rules.
- Give each parallel task its own branch and worktree, and parallelize only independent scopes.
- Automation does not replace Issues, PRs, CI, or human review.

{{< disclosure key="agents-standard" title="Standard AGENTS.md with local overrides" >}}
AGENTS.md is ordinary Markdown. Codex combines instructions from the repository root toward the working directory, with nearer rules taking precedence.
{{< /disclosure >}}

{{< detail key="agents-control" title="The actual control points" >}}
AGENTS.md describes the working method. GitHub permissions, Rulesets, CODEOWNERS, and required checks enforce the boundaries.
{{< /detail >}}
{{< /slide >}}

{{< slide key="contract" track="contract" eyebrow="Step 03" title="Use the same standard locally and in CI" subtitle="Each language keeps its native tools and converges on one stable verification entry point." >}}
- Run the narrowest relevant checks while iterating, then run full `./scripts/verify` before delivery.
- CI chooses fast or full work from change risk and reports one stable aggregate context.
- Invalid fixtures prove that gates reject bad input instead of remaining permanently green.

{{< disclosure key="language-toolchain" title="Python: uv, Ruff, mypy, pytest; TypeScript: pnpm, Biome, Vitest" >}}
Formatting, typing, tests, and packaging use each language's standard tools. Security, policy, and orchestration still share one entry point.
{{< /disclosure >}}

{{< detail key="contract-quota" title="Actions quota exception" >}}
The one-time local attestation applies only when a maintainer with billing visibility confirms that included minutes are exhausted and the job ran no step. It is bound to an exact SHA.
{{< /detail >}}
{{< /slide >}}

{{< slide key="pr" track="pr" eyebrow="Step 04" title="Merge small PRs after evidence passes" subtitle="Routing, Issue number, SemVer intent, and synchronization are checked together." >}}
- Branches use `type/123-short-slug`, and PRs link an open Issue.
- Milestone work enters its delivery branch first; promotion carries the integrated result to `main`.
- New commits dismiss stale approval, and review threads must be resolved.

{{< detail key="pr-version-intent" title="The PR title carries SemVer intent" >}}
After merge, `feat`, `fix`, and other Conventional Commit types determine the version from actual default-branch history. Open PRs never reserve version numbers.
{{< /detail >}}
{{< /slide >}}

{{< slide key="supply" track="supply" eyebrow="Step 05" title="Expose risk immediately; do not chase day-one upgrades" subtitle="Ordinary releases wait three days, while known vulnerabilities block immediately." >}}
- Dependabot manages `uv` and `npm` updates with a three-day delay for ordinary releases.
- `uv` and `pnpm` lock actual artifact integrity; OSV scans disclosed vulnerabilities.
- Release artifacts include SHA-256 checksums and a CycloneDX SBOM.

{{< disclosure key="supply-tools" title="Dependabot + OSV + anchore/sbom-action" >}}
Dependabot keeps GitHub's native automation identity, so adopters need no privileged App or long-lived PAT. pnpm `minimumReleaseAge` separately protects local and CI resolution.
{{< /disclosure >}}

{{< detail key="supply-boundaries" title="Separate responsibilities" >}}
Linters find code-quality defects, OSV finds disclosed dependency vulnerabilities, and CodeQL adds cross-function data-flow analysis. None substitutes for the others.
{{< /detail >}}
{{< /slide >}}

{{< slide key="deploy" track="deploy" eyebrow="Step 06" title="Connect version policy to artifacts" subtitle="Verify the promotion boundary, then select a safe delivery mode from current platform capabilities." >}}
- Only a verified promotion or qualified hotfix can become a release source.
- Platform capabilities are explicitly `allowed`, `blocked`, or `unknown`.
- When safe writes are unavailable, preserve a verification-only artifact and claim no release.

{{< disclosure key="adaptive-release" title="Promotion-gated adaptive release with one SemVer" >}}
Each runtime probe selects Release PR, direct, or verification-only mode. A 403, 409, missing remote, or missing administration access is never treated as allowed.
{{< /disclosure >}}

{{< detail key="deploy-ordering" title="Delivery ordering" >}}
Direct mode rereads the default-branch head before writing and handles only the newest main commit with consistent evidence. Workflow concurrency is not assumed to provide FIFO ordering.
{{< /detail >}}
{{< /slide >}}

{{< slide key="governance" track="governance" eyebrow="Step 07" title="Detect GitHub capability before applying controls" subtitle="Desired policy, stored settings, and actual enforcement are observed separately." >}}
- Every plan retains repository, Actions, label, and Ruleset policy sources.
- Free private repositories report degraded enforcement instead of claiming that Rulesets are active.
- A daily drift check shortens the time that configuration differences stay invisible.

{{< detail key="governance-observation" title="Observation limit" >}}
Scheduled checks are snapshots. A change made and reverted between two runs still requires GitHub audit logs or organization-level monitoring to reconstruct.
{{< /detail >}}
{{< /slide >}}

{{< slide key="template-release" track="template-release" eyebrow="Step 08" title="Copier keeps repositories aligned, and the template dogfoods its rules" subtitle="The template owns shared infrastructure; projects receive changes as reviewable diffs." >}}
- Creation, existing-repository adoption, and subsequent update of the same repository have real fixtures.
- CI/CD-only, Python, TypeScript, and mixed compositions share one template SemVer.
- Template updates do not overwrite project-owned product files.

{{< disclosure key="copier-update" title="Copier + root dogfood + create/update regression" >}}
Copier records source, language, and answers, then applies a newer template to an existing repository. Conflicts remain in a short branch and PR for human resolution.
{{< /disclosure >}}

{{< detail key="template-release-scope" title="Root-only boundary" >}}
`scripts/verify-template.sh` exercises lifecycle fixtures only in the template repository and is not shipped to consuming repositories.
{{< /detail >}}
{{< /slide >}}

{{< slide key="docs-site" track="docs-site" eyebrow="Step 09" title="A portable single file remains the baseline" subtitle="Hugo manages Markdown and layout; the unchanged renderer bundles each page without external runtime assets." >}}
- `decision-site/content/` is the candidate content source, with matching section keys in Chinese and English.
- `scripts/render_site.py` embeds CSS, JavaScript, fonts, and images.
- External reference links may remain, but offline reading and interaction do not depend on them.

{{< disclosure key="portable-bundle" title="Maintainable source → self-contained HTML" >}}
`docs/decisions/` preserves canonical choices. Hugo owns content structure and HTML; the renderer only embeds local assets and rejects external runtime assets.
{{< /disclosure >}}

{{< detail key="docs-site-access" title="Access boundary" >}}
`noindex` is not access control. An approved host can protect entry, but a downloaded offline file can still be forwarded.
{{< /detail >}}
{{< /slide >}}

{{< slide key="rollout" track="rollout" eyebrow="Step 10" title="Adopt in stages, with a stop after every step" subtitle="Start with a convergent baseline and add platform capability only after evidence appears." >}}
- **Baseline:** Issues, PRs, local verification, CI, dependency checks, and secret scanning.
- **Best:** enforce Rulesets, promotion, and delivery evidence when plan and permissions support them.
- **Optional:** enable hosting, cross-repository catalogs, or stronger platforms only for measured needs.

{{< detail key="rollout-evidence" title="Maturity is more than successful generation" >}}
The profile catalog separates synthetic verification from consuming-repository evidence. A composition is not described as mature without real adoption evidence.
{{< /detail >}}
{{< /slide >}}

{{< slide key="bridge" eyebrow="2025-05 → 2026-08" title="Keep the principles and adjust the implementation" subtitle="Earlier SDLC principles remain valid, while merge routing, updates, and capability detection are now explicit." >}}
- Keep repeatable verification, human review, dependency risk controls, and traceable delivery.
- Integrate parallel stories on a delivery branch before promotion reaches `main`.
- Reject capability guesses based on plan names and speculative platform construction.

{{< detail key="bridge-reason" title="Why the implementation changed" >}}
Recent probes show that GitHub plan, organization policy, and token identity all affect available capabilities, so runtime evidence replaces static assumptions.
{{< /detail >}}
{{< /slide >}}

{{< slide key="ecosystem" eyebrow="Tool selection" title="Tools implement the process; governance remains the through-line" subtitle="Baseline, future, and conditional adoption stay distinct." >}}
| Tool | Current decision |
| --- | --- |
| Copier, zizmor | Baseline |
| Dependabot, OSV, Syft | Baseline dependency and artifact evidence |
| Safe Settings, Backstage | Adopt only after scale and cross-team needs appear |
| Renovate | Do not replace Dependabot today |

{{< detail key="ecosystem-deferred" title="Not enabled yet" >}}
Go and Rust profiles, Scorecard, Harden-Runner, hosting and authentication, RAG, generic deployment, and monitoring wait for measurable demand.
{{< /detail >}}
{{< /slide >}}

{{< slide key="access-control" eyebrow="Access decision" title="Temporary protection before a hosting choice" subtitle="Reduce accidental spread without describing a notice as a security control." >}}
- The page marks itself internal; `robots.txt` and `noindex` reduce search-engine indexing.
- Only after maintainers approve a host, authentication, and write path can publication be called access-controlled.

{{< detail key="access-control-limit" title="Known limit" >}}
Anyone holding the offline HTML can forward it. Authentication at the hosting entry point cannot revoke files that have already been downloaded.
{{< /detail >}}
{{< /slide >}}

{{< slide key="principles" eyebrow="Key decisions" title="Rules, reasons, and deliberate omissions" subtitle="Only confirmed, durable constraints enter decision records." >}}
- Treat platform capability as detected state rather than a permanent assumption.
- Keep portable single-file delivery as the baseline and hosting as an enhancement.
- Separate project-owned content from template-led infrastructure.

{{< detail key="principles-transcript" title="Do not store raw conversations" >}}
An agent summarizes only user-confirmed durable constraints into an Issue, then records them through a reviewed change to the decision record.
{{< /detail >}}
{{< /slide >}}

{{< slide key="benchmark" eyebrow="External benchmark" title="A solid foundation, not a complete platform" subtitle="The current composition optimizes for clarity, portability, and maintainability." >}}
- Copier, GitHub Actions, and language-native tools cover the current small-template needs.
- A CI-only pilot adds real adoption evidence beyond synthetic fixtures.
- Other profiles advance in maturity only after their own pilots complete.

{{< detail key="benchmark-gap" title="Current gaps" >}}
There is no cross-repository catalog, comprehensive hosted governance, or generic deployment platform. Those should be triggered by recurring measured cost.
{{< /detail >}}
{{< /slide >}}

{{< slide key="fleet-inventory" eyebrow="Fleet governance" title="Inventory real repositories, not assumptions" subtitle="Current evidence does not justify a new platform." >}}
- Inventory answers and profiles, CODEOWNERS, unfinished update PRs, and governance-drift runs.
- A repository with no completed scheduled sample is not counted as zero drift.
- Recount after every new pilot and during quarterly review.

{{< detail key="fleet-inventory-source" title="Evidence source" >}}
Read current state through the GitHub API and preserve blocked and unknown results. Never infer an absence of problems from a missing run.
{{< /detail >}}
{{< /slide >}}

{{< slide key="fleet-thresholds" eyebrow="Fleet threshold" title="Measure the problem before adding a platform" subtitle="Recurring cost, ownership, and exit conditions must all be explicit." >}}
- Open an evaluation Issue when several consuming repositories repeatedly show the same drift or update blockage.
- Name a platform owner, cost ceiling, trial scope, and exit criteria in that Issue.

{{< detail key="fleet-thresholds-yagni" title="Do not prebuild a service" >}}
This decision defines a reevaluation threshold. It does not authorize Backstage, Safe Settings, or another persistent external service.
{{< /detail >}}
{{< /slide >}}

{{< slide key="spec-format" eyebrow="Spec format" title="Default to an Issue; create a Milestone only for an explicit story" subtitle="Keep one simple format instead of maintaining two systems before the need exists." >}}
- The current Markdown spec stores ID, priority, state, and optional tracking in front matter.
- By default, a marker idempotently synchronizes one Issue.
- Reevaluate Spec Kit when approved specs must be reliably split into multiple work items by AI.

{{< detail key="spec-format-cost" title="Cost of adopting Spec Kit" >}}
Adoption requires new parsing and synchronization, conversion of existing specs, new validation assertions, and an equivalent Issue-sync design. The current benefit does not justify that cost.
{{< /detail >}}
{{< /slide >}}
