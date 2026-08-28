+++
title = "CSARC Repo Template | AI-assisted SDLC foundation"

[controls]
language = "Reading language"
detail = "Reading mode"
simple = "Standard"
technical = "Maintenance"
slides = "Presentation controls"
previous = "Previous slide"
next = "Next slide"
zoom = "Display zoom controls"
zoom_out = "Zoom out"
zoom_reset = "Fit to screen"
zoom_in = "Zoom in"
fit = "Fit"
+++

{{< slide key="capability" track="capability" eyebrow="CSARC Repo Template · beta" title="An updatable repository foundation" subtitle="Create a new project, adopt an existing one, or receive policy updates through verified pull requests." legacy="false" class="presentation-slide" >}}
The template puts work definition, AI instructions, verification, merging, dependencies, and delivery evidence into one reviewable flow.

| Choice | Production capability available today |
| --- | --- |
| Project composition | CI/CD-only, Python 3.14, TypeScript with Node 24 and pnpm 11, or Python plus TypeScript |
| Branch strategy | Milestone delivery branches, `main`-only, or one long-lived `dev` |
| Shared baseline | SDD Features with Task/Bug subissues, dated delivery Milestones, tiered CI, promotion evidence, security checks, one SemVer, and Copier updates |

{{< detail key="capability-boundary" title="Real entry points and capability boundaries" >}}
- **New repository:** choose a profile and branch strategy; keep the story in an SDD Feature, deliver Task/Bug subissues through separate PRs, and use a Milestone only for dated delivery.
- **Existing repository:** preview adoption on a branch, preserve product content and legacy-debt boundaries, then resolve conflicts and gates explicitly.
- **Repository already using the template:** update from a reviewed template SHA and review only that revision's diff.
- **Prerequisites:** Git, GitHub CLI, and uv; TypeScript or mixed projects also need Node 24+ and pnpm 11. Local verification needs no token.

The template claims only capabilities backed by executable files and regression checks. Go, Rust, generic deployment, monitoring, RAG, and hosted documentation remain future or optional work.
{{< /detail >}}
{{< /slide >}}

{{< slide key="flow" track="flow" eyebrow="Developer journey" title="From a requirement to a deliverable version" subtitle="Steps 01–06 follow each change; 07–10 continuously support the flow." legacy="false"  class="candidate-slide" >}}
| Stage | Human and agent action | Automation evidence |
| --- | --- | --- |
| 01 Define work | State the problem and acceptance criteria in an Issue | Title, field, and prior-work checks |
| 02 Implement and test | Work from `AGENTS.md` on a short branch and isolated worktree | Focused local checks |
| 03 Open a PR | Link the Issue and explain purpose, verification, and rollback | PR policy and delivery route |
| 04 Run CI | Ordinary Issue PRs use the fast tier | Stable `verify` aggregate result |
| 05 Review and merge | Fix failures, resolve review, and merge to the delivery branch | Approval and required checks |
| 06 Version and deliver | Promotion batches version and artifact creation | Full verify, checksum, SBOM, attestation |

{{< detail key="flow-foundation" title="Four foundations across the whole flow" >}}
- **07 Governance:** consistent permissions, branch, review, and merge rules.
- **08 Template updates:** Copier carries policy changes back through reviewable PRs.
- **09 Internal site:** keeps practices, limits, evidence, and decisions discoverable.
- **10 Adoption levels:** start with the baseline and add platform capability only after conditions are met.

A CI failure returns to step 02 in the same PR. A problem found after delivery returns to step 01 as the next bounded Issue.
{{< /detail >}}
{{< /slide >}}

{{< slide key="files" track="files" class="dense" eyebrow="Responsibility map" title="Files the template actually creates and maintains" subtitle="The template may propose infrastructure updates without silently overwriting product-owned content." legacy="false" >}}
| Path | Purpose | Responsibility |
| --- | --- | --- |
| `.copier-answers.yml`, `.csarc/profile.json` | Template source, profile, and branch strategy | Template-led |
| `.github/ISSUE_TEMPLATE/`, `pull_request_template.md` | Work definition and PR contract | Template-led |
| `.github/workflows/` | CI, promotion, release, OSV, and governance drift | Template-led |
| `AGENTS.md`, `README.md` | Agent working rules and user entry point | Shared |
| `policies/`, `CODEOWNERS`, `.github/REVIEWERS` | Desired settings, owners, and reviewers | Shared |
| `scripts/verify` | Single verification entry point in generated projects | Template-led |
| `src/`, product tests, and product specifications | Product behavior | Project-owned |

{{< detail key="files-update" title="How updates protect product content" >}}
Copier carries updates into a short branch and leaves conflicts in the PR for human review. Fixtures cover new project generation, existing-repository adoption, and a later update of the same repository. They add product-owned files and prove that an update does not overwrite them.

Workflows, policies, scripts, and documents consumed by both root and `template/` are generated from root by `scripts/sync-paired-files.sh`; `--check` verifies content and executable bits. Files that differ because of Copier variables are checked by generating a real project.
{{< /detail >}}
{{< /slide >}}

{{< slide key="method" track="method" eyebrow="Step 01" title="Define the problem before implementation" subtitle="An Issue bounds implementation; a Milestone is an optional story outcome." legacy="false"  class="candidate-slide" >}}
- List open Milestones and Issues, then search open and closed Issues with two to four concrete terms before starting work.
- Use a 12–80 character ASCII Issue title with at least three words; keep the body shape to type, problem, acceptance criteria, and optional supplement.
- Open another Issue for work outside the acceptance criteria instead of hiding it in the current PR.

{{< disclosure key="spec-tracking" title="Specs default to Issues; explicit stories create Milestones" >}}
`docs/specs/*.md` records state in front matter. A `csarc-spec-id` marker idempotently synchronizes one Issue by default. Only `tracking: story` uses a `csarc-story-id` marker to synchronize a Milestone, without inventing child Issues.
{{< /disclosure >}}

{{< detail key="method-lifecycle" title="The lifecycle that actually runs in the repository" >}}
- A story description uses `Problem`, `Outcome`, `Acceptance criteria`, `Plan`, `Out of scope`, `Verification`, and `References`.
- A Milestone contains only Issues that directly advance the outcome, never their linked PRs as duplicates.
- The Milestone closes only when every acceptance checkbox is checked and no Issue remains open; it reopens when either condition changes.
- `scripts/spec_to_issue.py` performs spec synchronization, and `.github/workflows/milestone-lifecycle.yml` closes or reopens from current GitHub API state.
{{< /detail >}}
{{< /slide >}}

{{< slide key="agents" track="agents" eyebrow="Step 02" title="Set the AI working contract before implementation" subtitle="README serves users; AGENTS.md gives agents executable scope and safety boundaries." legacy="false"  class="candidate-slide" >}}
- The agent reads the work item, repository, and `AGENTS.md` before proposing, changing, and verifying code.
- Each writable task gets its own branch and Git worktree; only independent scopes run in parallel.
- Ruff, Biome, mypy, pytest, Vitest, and CI make repeatable formatting, typing, and test decisions.

{{< disclosure key="agents-standard" title="Standard AGENTS.md with local overrides" >}}
[AGENTS.md](https://github.com/agentsmd/agents.md) is ordinary Markdown. Codex combines instructions from the repository root toward the working directory, with nearer rules taking precedence. Add a local file only when that subtree genuinely needs different commands or safety rules.
{{< /disclosure >}}

{{< detail key="agents-control" title="Actual controls and human responsibility" >}}
AGENTS.md describes the working method. GitHub permissions, Rulesets, CODEOWNERS, and required checks enforce it. Humans still confirm requirements and technical direction, judge risk, review diffs, and authorize merges.

`scripts/cleanup-worktrees` removes only clean worktrees whose merge GitHub can verify. An Actions quota fallback can never be inferred by an agent: a maintainer with billing visibility must confirm exhausted included minutes before an exact PR SHA receives a full local-verification attestation and one-time authorization.
{{< /detail >}}
{{< /slide >}}

{{< slide key="contract" track="contract" eyebrow="Step 03" title="Use the same standard locally and in CI" subtitle="Keep daily feedback fast and concentrate complete evidence at delivery boundaries." legacy="false"  class="candidate-slide" >}}
| Verification tier | When it runs | Scope |
| --- | --- | --- |
| Focused | Development iteration | Only lint, type, and tests directly relevant to the change |
| Fast | Ordinary Issue PR | Secret scan, format, lint, type, unit tests, and necessary template smoke |
| Full | Promotion, hotfix, merge queue, or manual dispatch | Every runtime, profile, Copier update, release, and security regression |

{{< disclosure key="language-toolchain" title="Python: uv, Ruff, mypy, pytest; TypeScript: pnpm, Biome, Vitest" >}}
Each language uses its native formatting, typing, testing, and packaging tools. Gitleaks, security, policy, and workflow orchestration share one entry point. Generated repositories use `./scripts/verify`; the template repository uses `./scripts/verify-template.sh`.
{{< /disclosure >}}

{{< detail key="contract-quota" title="Conditional checks, stable gates, and the quota exception" >}}
Workflow changes add Zizmor, dependency changes add OSV, and governance declarations add remote governance. Unknown paths fail closed to full. The `verify` aggregate always reports; inapplicable heavy jobs are explicitly skipped so a required check never remains pending.

The Actions exception applies only when a maintainer with billing visibility confirms that included minutes are exhausted and the job ran no step. Payment, budget, platform, configuration, and test failures do not qualify. The full contract is in `docs/ci-policy.md`.
{{< /detail >}}
{{< /slide >}}

{{< slide key="pr" track="pr" eyebrow="Step 04" title="Merge small PRs after evidence passes" subtitle="Issues integrate on delivery branches; promotion brings verified outcomes to main." legacy="false"  class="candidate-slide" >}}
| Work type | PR base | Route into `main` |
| --- | --- | --- |
| Milestone Issue | `dev/m<Milestone>-*` | Milestone promotion PR |
| Ordinary standalone Issue | `dev/next` | Batched promotion in the release window |
| Issue requiring isolated soak or canary | Temporary `dev/i<Issue>-*` | That Issue's promotion PR |
| Emergency correction | `main` | Only a standalone `fix/*` PR labeled `hotfix` |

{{< detail key="pr-version-intent" title="Concrete branch, synchronization, and version-intent rules" >}}
- Work branches use `type/<Issue>-short-slug`, and the PR links the matching open Issue.
- When `main` advances, each active delivery owner integrates it through a reviewed `sync/main-to-*` PR without direct pushes or history rewrites.
- `feat`, `fix`, and `!` determine SemVer only after merge from actual default-branch history; open PRs never reserve versions.
- `pr-policy.yml`, `delivery-sync.yml`, and `promotion.yml` verify route, Issue, title, synchronization, and promotion evidence.
{{< /detail >}}
{{< /slide >}}

{{< slide key="supply" track="supply" eyebrow="Step 05" title="Expose risk immediately; do not chase day-one upgrades" subtitle="A malicious new release, a disclosed vulnerability, and artifact contents are different problems." legacy="false"  class="candidate-slide" >}}
| Problem | Current control | What it does not prove |
| --- | --- | --- |
| Brand-new package version | Dependabot and pnpm wait three days for ordinary releases | The package has no disclosed vulnerability |
| Disclosed vulnerability | OSV scans and alerts immediately | Downloaded content is identical |
| Content integrity | `uv.lock` SHA-256, pnpm integrity, release checksum | The publisher is trustworthy |
| Artifact composition | CycloneDX SBOM generated from the unpacked artifact | The SBOM blocks vulnerabilities by itself |

{{< disclosure key="supply-tools" title="Dependabot + OSV + anchore/sbom-action" >}}
Dependabot keeps GitHub's native automation identity, so its PRs trigger existing policy and change-aware checks without a privileged App or long-lived PAT in every repository. pnpm `minimumReleaseAge` protects local and CI resolution, while `trustPolicy: no-downgrade` rejects publisher-trust downgrades.
{{< /disclosure >}}

{{< detail key="supply-boundaries" title="Configuration locations and the Renovate decision" >}}
- Update delay: `.github/dependabot.yml` and `pnpm-workspace.yaml`.
- Frozen installation and lockfile integrity: `scripts/verify`.
- Vulnerability and release evidence: `osv.yml`, `release.yml`, and `SECURITY.md`.

Renovate offers a more flexible shared preset, but a self-hosted token cannot trigger every required check normally, while the Mend App asks for organization-member read, repository-administration read, and workflow/content/PR write. Dependabot remains the default until a real fleet policy cannot be expressed without Renovate.
{{< /detail >}}
{{< /slide >}}

{{< slide key="deploy" track="deploy" class="dense" eyebrow="Step 06" title="Connect version policy to artifacts" subtitle="Verify the promotion source, then select a safe delivery mode from current platform capabilities." legacy="false" >}}
| Preconditions | Mode | Behavior and guarantee |
| --- | --- | --- |
| Valid source; PR, contents, Release, and dispatch are all `allowed` | Release PR | Reviewable version and changelog; merge dispatches artifacts with the source run ID |
| Valid source; PR is `blocked/unknown`; all other writes are `allowed` | Direct | Tag only the latest versioned `main` with a CHANGELOG; out-of-order runs no-op |
| Invalid source or any delivery write is not `allowed` | Verification only | Preserve machine-readable evidence and create or claim no Release |

{{< disclosure key="adaptive-release" title="Promotion-gated adaptive release with one SemVer" >}}
The release source verifies full `verify`, canary state, included PRs, and main tree identity. Every profile shares one template SemVer: `fix(scope)` raises patch, `feat(scope)` raises minor, and `!` raises major. Incompatibility with any supported profile is a breaking change to the template.
{{< /disclosure >}}

{{< detail key="deploy-ordering" title="Delivery ordering, artifacts, and registry boundaries" >}}
Direct mode rereads the default-branch head before writing and delivers only when the latest `main`, source, tag, CHANGELOG, and promotion evidence agree; workflow concurrency is not treated as FIFO. The artifact workflow accepts only a release-source run ID, creates a digest, SBOM, and attestation, ignores arbitrary tag pushes, and does not repeat full CI.

GitHub Release is the baseline for every profile. PyPI and npm are separate opt-ins that default off and use a GitHub environment plus short-lived OIDC credentials, never stored registry tokens. `scripts/release_policy.py` detects capabilities and configures versions; `scripts/promotion_gate.py` validates promotion.
{{< /detail >}}
{{< /slide >}}

{{< slide key="governance" track="governance" class="dense" eyebrow="Step 07" title="Detect GitHub capability before applying controls" subtitle="The organization currently probes as Free plus private, so main is not protected by an enforced Ruleset." legacy="false" >}}
| GitHub state | `apply` result | Actual gate |
| --- | --- | --- |
| Free + public | Apply a Ruleset through REST | Missing or mismatched rules fail |
| Free organization + private | Apply baseline settings and retain desired Ruleset in `policies/rulesets.json` | Request one individual reviewer and report `DEGRADED`; no merge gate |
| Pro personal + private | Apply a Ruleset | Same as Free public |
| Team/Enterprise organization + private | Verify the CODEOWNERS team, then apply a Ruleset | Review, CODEOWNER, and status checks become merge gates |

{{< detail key="governance-observation" title="Concrete operations and observation limits" >}}
Run `scripts/apply-repository-settings.sh plan`, `apply`, then `check`. The check compares CODEOWNERS, repository settings, Actions, policy labels, and effective Rulesets. `.github/workflows/governance-drift.yml` reruns daily and opens or updates a tracking Issue for repairable drift.

Scheduled checks are snapshots. A setting changed and restored between runs still requires the GitHub audit log or organization monitoring. Complete administration fields should be checked from a trusted checkout with Administration read credentials, never by exposing that token to PR code.
{{< /detail >}}
{{< /slide >}}

{{< slide key="template-release" track="template-release" eyebrow="Step 08" title="Copier keeps repositories aligned, and the template dogfoods its rules" subtitle="A template defect affects many projects, so creation, adoption, and update all run as real tests." legacy="false"  class="candidate-slide" >}}
- `template/` is the delivered source; root retains the template repository's own GitHub governance and dogfood configuration.
- CI/CD-only, Python, TypeScript, mixed, and minimum-Python compositions are generated and verified.
- An existing repository is adopted and then updated from the next Copier revision, proving product content is preserved.

{{< disclosure key="copier-update" title="Copier + root dogfood + create/update regression" >}}
[Copier](https://github.com/copier-org/copier) records source, language, and answers, then reapplies newer template revisions to an editable repository. Conflicts remain in a short branch and PR for human review. GitHub Template copies only once, while PyScaffold would create a second update mechanism, so neither fits this requirement.
{{< /disclosure >}}

{{< detail key="template-release-scope" title="Single source, runtime baselines, and the root-only boundary" >}}
`scripts/sync-paired-files.sh` makes root the source of paired files and verifies copied content and permissions with `--check`. `profiles/catalog.yaml` records runtime baselines and real pilot status. Python and Node baselines advance only after their own thirty-day observation period.

`scripts/verify-template.sh` runs create/adopt/update fixtures only in the template repository and is never delivered downstream. Generated repositories use the smaller `scripts/verify` entry point.
{{< /detail >}}
{{< /slide >}}

{{< slide key="docs-site" track="docs-site" eyebrow="Step 09" title="A portable single file remains the baseline" subtitle="Hugo owns content structure; the existing renderer produces an offline, forwardable HTML file." legacy="false"  class="candidate-slide" >}}
- `site/content/` holds bilingual Markdown with matching content keys.
- `site/static/styles.css` retains the presentation identity; Hugo shortcodes produce the shared content structure.
- `scripts/render_site.py` embeds CSS, JavaScript, fonts, and images and rejects external runtime assets.

{{< disclosure key="portable-bundle" title="Markdown + Hugo → self-contained HTML" >}}
`docs/adr/` preserves canonical choices. Hugo owns content and HTML; the unchanged renderer only embeds assets and enforces safety checks. The final `docs/index.html` opens offline through `file://` without Pages, a CDN, or a JavaScript package runtime.
{{< /disclosure >}}

{{< detail key="docs-site-access" title="Access and maintenance boundaries" >}}
`noindex` and `robots.txt` reduce accidental spread but are not access control. An approved host can protect entry, but a downloaded HTML file can still be forwarded. An agent records only user-confirmed durable constraints in an Issue and a reviewed decision record, never a raw conversation transcript.
{{< /detail >}}
{{< /slide >}}

{{< slide key="rollout" track="rollout" eyebrow="Step 10" title="Adopt in stages, with a stop after every step" subtitle="Maturity follows operational evidence, not a date or the mere presence of files." legacy="false"  class="candidate-slide" >}}
| Level | Current state |
| --- | --- |
| Baseline capability | Four profiles, Issues/specs, PR/CI, local verification, OSV, dependency policy, and the repository site have executable implementations |
| Verified online | Release handoff, traceable artifacts, consumer attestation, and the first CI-only downstream adoption and update |
| Still piloting | Python, TypeScript, and mixed compositions each need one real consuming-repository pilot |
| Future/optional | Central catalog or governance, Go/Rust, authenticated hosting, deployment, monitoring, RAG, and autonomous agents |

{{< detail key="rollout-evidence" title="Why capabilities are not enabled all at once" >}}
A big-bang switch spreads defects across every project; a calendar date does not prove readiness; a profile without real adoption evidence is only a promise. `profiles/catalog.yaml` separates synthetic verification from consuming-repository evidence. `scripts/verify-template.sh` proves generation and update paths, but cannot replace a pilot.
{{< /detail >}}
{{< /slide >}}

{{< slide key="bridge" class="dense" eyebrow="2025-05 → 2026-08" title="Keep the principles and adjust the implementation" subtitle="The earlier SDLC direction remains valid, with more precise routing, capability detection, and delivery boundaries." legacy="false" >}}
| Earlier topic | Current decision |
| --- | --- |
| Core SDLC stages | Keep plan, build, test, deliver, and monitor in maintainable GitHub objects |
| Jira ticket | Use a minimal GitHub Issue; add a Milestone or spec only for an explicit story |
| Version control | A delivery branch is a CI integration boundary, not a pretend physical environment |
| PR and review | Issue, numbered branch, PR, CI, and human approval form one chain |
| CI pipeline | Ordinary work uses fast; promotion, hotfix, and unknown high-risk paths use full |
| CD management | Promotion forms the release boundary; without an environment, canary degrades to artifact-only |
| Observability | Select monitoring and on-call tools only for continuously running services |
| Copilot to agent | Start with controlled collaboration; consider autonomous retry and rollback only when mature |
| AI first review | Supplement advice only; never replace deterministic tools, peer review, or Rulesets |
| AI docs and RAG | Maintain repository docs first; evaluate RAG after hosting, data policy, and test questions exist |
| Legacy modernization | Keep it project-specific instead of imposing empty tools on every repository |

{{< detail key="bridge-reason" title="Evidence behind the changes" >}}
GitHub plan, repository visibility, organization policy, and token identity all affect capabilities, so runtime probes replace static guesses. Tiered CI separates daily feedback from full delivery confidence. Copier updates keep shared policy current without taking ownership of product content.
{{< /detail >}}
{{< /slide >}}

{{< slide key="ecosystem" class="dense" eyebrow="Tool selection" title="Tools implement the process; governance remains the through-line" subtitle="Every tool needs a current decision, not merely a logo on a page." legacy="false" >}}
| Tool | Need | Current decision |
| --- | --- | --- |
| ![Copier logo](../assets/copier.svg) [Copier](https://github.com/copier-org/copier) | Updatable templates | Baseline; changes arrive through PRs |
| ![zizmor logo](../assets/zizmor.png) [zizmor](https://github.com/zizmorcore/zizmor) | GitHub Actions security | Baseline; runs for workflow changes and on schedule |
| Dependabot, OSV, Syft | Dependency updates, vulnerabilities, and SBOM | Baseline |
| ![GitHub Community Projects logo](../assets/github-community-projects.png) [Safe Settings](https://github.com/github-community-projects/safe-settings) | Cross-repository settings | Evaluate after fleet and drift thresholds are met |
| ![Renovate logo](../assets/renovate.png) [Renovate](https://github.com/renovatebot/renovate) | Flexible update presets | Do not replace Dependabot today |
| ![GitHub Actions logo](../assets/github-actions.svg) ![PyScaffold logo](../assets/pyscaffold.svg) Starter Workflows, PyScaffold | Official workflow and Python structure examples | Content checklists only; do not copy policy blindly |
| ![GitHub logo](../assets/github.png) [GitHub Spec Kit](https://github.com/github/spec-kit) | AI specification decomposition | Keep the current spec-to-Issue flow today |
| ![Backstage logo](../assets/backstage.svg) [Backstage](https://backstage.io/docs/features/software-catalog/) | Catalog, ownership, and docs entry | PoC only after cross-team lookup cost reaches its threshold |

{{< detail key="ecosystem-deferred" title="Capabilities not enabled yet" >}}
Go and Rust profiles, Scorecard, Harden-Runner, authenticated hosting, RAG, generic deployment, and monitoring all wait for measurable demand. The template does not create empty configuration or placeholders to pretend support.
{{< /detail >}}
{{< /slide >}}

{{< slide key="similar-tools" parity="supplemental" eyebrow="Tools appendix | Similar tools" title="Similar tools | Direct alternatives and focused references" subtitle="Standard mode shows projects with a similar overall purpose; Maintenance mode adds concrete comparisons by journey." class="similar-tools-slide" legacy="true" >}}
{{< similar-tools >}}
{{< /slide >}}

{{< slide key="testing" audience="maintainer" parity="supplemental" eyebrow="Maintenance appendix | Tests" title="Tests | Journey 01 work definition" subtitle="Every repository verifies only its own work definition; repo-template adds one delivery check during promotion." class="similar-tools-slide testing-slide" legacy="true" >}}
{{< testing >}}
{{< /slide >}}

{{< slide key="access-control" class="dense" eyebrow="Access decision" title="Temporary protection before a hosting choice" subtitle="Current measures reduce accidental sharing; none is described as access control." legacy="false" >}}
| Option | Cost and benefit | Current limitation or owner |
| --- | --- | --- |
| Cloudflare Pages + Access | Free allowance can provide a small-team login wall | Organization owner must establish Cloudflare, domain, DNS, and SSO/OTP policy |
| GitHub Pages + IP restriction | Reuses the GitHub organization | Private Pages and IP allow lists require Enterprise Cloud; current Free plan cannot provide them |
| Backstage, Confluence, or another internal portal | Can govern several internal documents together | One site does not justify an IT/platform-operated service today |

{{< detail key="access-control-limit" title="What exists and what it cannot do" >}}
`docs/index.html` contains `noindex,nofollow`, while `docs/robots.txt` asks crawlers to stay away. Neither authenticates a reader, and anyone with the offline file can forward it. Maintainers must separately approve a host, identity provider, data policy, and audit policy. Issue #79 tracks that decision.
{{< /detail >}}
{{< /slide >}}

{{< slide key="principles" class="dense" eyebrow="Key decisions" title="Rules, reasons, and deliberate omissions" subtitle="These decisions are backed by current files and checks." legacy="false" >}}
| Review question | Current decision |
| --- | --- |
| `main` protection on Free private | Preserve Ruleset policy and report `DEGRADED`; never claim an enforced merge gate |
| Work scope | Issue-first; open a separate Issue for requirements outside acceptance criteria |
| Template update boundary | `template/` delivers infrastructure; Copier preserves product code and specs |
| Language quality | Python uses src layout, Ruff, strict mypy; TypeScript uses Node 24, pnpm 11, Biome, Vitest |
| CI and versioning | Local and CI share entry points; daily fast, promotion full, one SemVer |
| Supply chain | Delay, OSV, hashes, SBOM, and resolver checks address different risks |
| AI and docs | `AGENTS.md` is the working contract; README and the site serve people |
| Verification resources | Use local temporary projects or this repository; never create a GitHub repository only for testing |

{{< detail key="principles-transcript" title="How durable decisions are recorded" >}}
Agents do not save raw conversations. Only a user-confirmed durable architecture, security, compatibility, or platform constraint is summarized into an Issue and then written to `docs/adr/` or `docs/decisions/` through a scoped PR. Executable configuration remains authoritative, and changed conditions are updated through another Issue and PR.
{{< /detail >}}
{{< /slide >}}

{{< slide key="benchmark" class="dense" eyebrow="External benchmark and live evidence" title="A solid foundation, not a complete platform" subtitle="New projects, Copier updates, OSV, Release, and the first CI-only pilot have evidence; remaining boundaries stay explicit." legacy="false" >}}
| Benchmark or probe | Assessment | Current evidence and boundary |
| --- | --- | --- |
| Copier vs projen | Good fit | Editable output plus smart update matches the requirement |
| Spotify Golden Path / Backstage | Only one layer | This is a single-repository foundation, not a cross-team catalog platform |
| Allstar / Safe Settings | Sufficient today | Scheduled drift checks exist; revisit central enforcement as the fleet grows |
| GitHub Rulesets / Free private | Partial | Capability can be detected and reported, but the plan cannot enforce Rulesets |
| Release Please live runs | Online loop complete | Runtime capability selects Release PR, Direct, or Verification only |
| OSV reusable workflow | Corrected | A successful main run exists after permission propagation was fixed |
| Artifact Attestations / SLSA | Consumer gate complete | Repository, tag, digest, and signer workflow are verified |
| OpenSSF Scorecard | Plan-aware | Public enables CodeQL by default; private/internal explicitly opt in when licensed |
| Real consuming repository | CI-only proven | `ai-guardrail` adopted v0.2.4 and updated to v0.3.1; other profiles still need pilots |

{{< detail key="benchmark-gap" title="Current gaps" >}}
There is no cross-repository catalog, comprehensive hosted governance, or generic deployment platform. The root-only `Live integration smoke` continues to exercise OSV, Release Please, release handoff, and governance drift. Python, TypeScript, and mixed compositions advance to beta only after their own real pilots.
{{< /detail >}}
{{< /slide >}}

{{< slide key="fleet-inventory" class="dense" eyebrow="Fleet governance" title="Inventory real repositories, not assumptions" subtitle="As of 2026-08-24, the organization has six private repositories and one consuming repository." legacy="false" >}}
| Repository | Owner | Template state | Drift data |
| --- | --- | --- | --- |
| `csarc-repo-template` | `@Innoguard-Cyber-Arch/arch` | Source repository | Live integration proves the drift check can run |
| `GRC` | No CODEOWNERS declared | Not adopted | No template drift data |
| `LLM_Guard` | No CODEOWNERS declared | Not adopted | No template drift data |
| `ai-guardrail` | `@Innoguard-Cyber-Arch/repository-maintainers` | v0.3.1 / CI-only beta | Adoption and update PRs passed; daily samples are now accumulating |
| `claude-newsletter` | No CODEOWNERS declared | Not adopted | No template drift data |
| `csarc-agent-kit` | No CODEOWNERS declared | Not adopted | No template drift data |

{{< detail key="fleet-inventory-source" title="Inventory evidence and interpretation" >}}
The inventory reads GitHub repositories, default branches, CODEOWNERS, Copier answers, CSARC profiles, unfinished update PRs, and governance-drift runs. A repository with no completed scheduled sample is never counted as zero drift. Recount after each new pilot and during quarterly review.
{{< /detail >}}
{{< /slide >}}

{{< slide key="fleet-governance-thresholds" eyebrow="Fleet thresholds" title="Measure the problem before adding a platform" subtitle="Catalog and policy enforcement solve different problems and use separate evidence." legacy="false"  class="candidate-slide" >}}
| Need | Quantified reevaluation threshold |
| --- | --- |
| Catalog / Backstage | Ten active consuming repositories; or at least three plus two Issues within 90 days recording owner/service lookup over 30 minutes |
| Central policy enforcement | At least five consuming repositories plus the same drift in 2+ repositories within 30 days; or 20%+ update PRs older than five workdays for two releases; or more than two manual repair hours per month |

{{< detail key="fleet-thresholds-yagni" title="Conditions still required after a threshold triggers" >}}
Open an evaluation Issue that names a platform owner, cost ceiling, trial scope, and exit criteria. Backstage handles catalog, ownership, and system relationships; Allstar or Safe Settings handles continuing policy checks and settings delivery. They do not substitute for each other. Until a threshold is met, keep Copier, JSON policy, GitHub API checks, and daily drift detection without prebuilding an external service.
{{< /detail >}}
{{< /slide >}}

{{< slide key="spec-format" eyebrow="Specification format" title="Default to an Issue; create a Milestone only for an explicit story" subtitle="Keep one lightweight format instead of maintaining two systems before the need exists." legacy="false"  class="candidate-slide" >}}
| Option | Current state |
| --- | --- |
| Current `docs/specs/*.md` | Front matter records ID, priority, state, and optional tracking; markers repeatably synchronize an Issue or Milestone |
| GitHub Spec Kit | `/specify → /plan → /tasks → /implement`; requires another CLI and supported AI tool, with no built-in one-spec-to-one-Issue synchronization |

{{< detail key="spec-format-cost" title="Why migration is deferred and what would trigger it" >}}
Adopting Spec Kit requires rewriting `scripts/spec_to_issue.py`, converting existing specs, updating verification assertions, and designing an equivalent Issue sync. Supporting both formats adds cognitive and maintenance cost. Reevaluate when approved specifications regularly need reliable AI decomposition into several work items and the team accepts an additional CLI/agent workflow. Issue #77 tracks the decision.
{{< /detail >}}
{{< /slide >}}

{{< glossary >}}
