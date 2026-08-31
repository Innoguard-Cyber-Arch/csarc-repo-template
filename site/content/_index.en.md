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

{{< slide key="flow" track="flow" eyebrow="CI/CD flow" title="The template guides every change" subtitle="Follow the Issue and PR prompts; the template prepares the right settings and tells you what needs attention." legacy="false"  class="candidate-slide" >}}
| What you are doing | How the template guides you |
| --- | --- |
| Create the work | The Issue form prompts for the problem, completion conditions, and necessary context |
| Make the change | Repository guidance tells people and agents how to work and which local check to run first |
| Open a PR | The PR template prompts for the linked Issue, completed result, and verification evidence |
| Read verification and dependency results | The template selects the necessary checks; dependency changes first prove that the locked package set still installs |
| Review and merge | Merge into the correct branch after the result and human review are clear |

Users do not need to memorize workflow or script names. Current automation focuses on work items, PR rules, and necessary verification; automated versioning and publishing are not enabled yet.

{{< detail key="flow-foundation" title="Four foundations across the whole flow" >}}
- **07 Governance:** consistent permissions, branch, review, and merge rules.
- **08 Template updates:** Copier carries policy changes back through reviewable PRs.
- **09 Internal site:** keeps practices, limits, evidence, and decisions discoverable.
- **10 Adoption levels:** start with the baseline and add platform capability only after conditions are met.

A failed check is fixed in the same PR. A new problem found after merge becomes a separate, bounded Issue.
{{< /detail >}}
{{< /slide >}}

{{< slide key="files" track="files" class="dense" eyebrow="File map" title="The template puts required settings in the right place" subtitle="This lists the major files currently generated; template updates never silently overwrite product-owned content." legacy="false" >}}
| Path | Purpose | Responsibility |
| --- | --- | --- |
| `.copier-answers.yml`, `.csarc/profile.json` | Template source, profile, and branch strategy | Template-led |
| `.github/ISSUE_TEMPLATE/`, `pull_request_template.md` | Work definition and PR contract | Template-led |
| `.github/workflows/` | Six active flows: Issue triage, Milestone sync, spec sync, PR rules, verification, and scheduled vulnerability scanning | Template-led |
| `AGENTS.md`, `README.md`, `CLAUDE.md` | Agent working rules and user entry point | Shared |
| `policies/`, `CODEOWNERS`, `.github/REVIEWERS` | Desired settings, owners, and reviewers | Shared |
| `scripts/` | Local verification, work synchronization, and repository settings | Template-led |
| `docs/`, `site/` | Project guidance, specifications, decisions, and internal site | Shared |
| `src/`, product tests, and product specifications | Product behavior | Project-owned |

{{< detail key="files-update" title="How updates protect product content" >}}
Copier carries updates into a short branch and leaves conflicts in the PR for human review. Fixtures cover new project generation, existing-repository adoption, and a later update of the same repository. They add product-owned files and prove that an update does not overwrite them.

Workflows, policies, scripts, and documents shared by root and `template/` are kept in sync. Files that differ because of project choices are verified by generating a real project. Version and publishing configuration remains present, but its GitHub Actions are not enabled yet.
{{< /detail >}}
{{< /slide >}}

{{< slide key="method" track="method" eyebrow="Step 01" title="Define the work before implementation" subtitle="Turn a request into an actionable Issue; create a Milestone only when several work items must move together." legacy="false"  class="candidate-slide dense single-column" >}}
### Our choice

- **Overall:** turn the request into one Issue that can be completed and verified independently.
- **Milestone:** create one only when several Issues share an outcome, deadline, or delivery batch, and give it one lifecycle tracking Issue.
  - Work may start only after at least one person other than the proposer agrees and no objection remains unresolved.
- **Issue:** choose the Feature, Task, Bug, or Documentation form, then state the problem, acceptance criteria, and verification.
  - Use a clear English title; the creator owns the Issue by default.
- **Exceptions:** close repeated work as Duplicate. Define urgent work as a Bug first; the PR / merge section owns its delivery route.

{{< disclosure key="work-item-details" title="Issue types and splitting rules" >}}
- Feature is an outcome that needs several pieces of work.
- Task is work that can be completed and verified independently.
- Bug is a result that differs from expectations.
- Documentation changes only documentation or examples.
- Keep work together when one completion condition and one body of evidence can prove it. Create a Sub-issue when work can be completed independently or required follow-up exceeds the original scope.
- A Parent describes the shared outcome that is not complete yet; Dependency expresses ordering instead.
{{< /disclosure >}}

### Other common approaches

- **Start first, document when needed:** finish small, clear work directly; add a plan only for work that spans sessions, has dependencies, or carries higher risk.
- **Specification first:** clarify requirements, design, and task breakdown before development begins.
- **Change proposal:** review a proposed change separately, then merge it into the official specification after acceptance.
- **Complexity-based workflow:** use a short path for small work and add discovery, design, roles, and review only for larger work.

<aside class="config-guidance"><strong>Specification format</strong><p>Keep the current lightweight Issue and spec format. Reconsider a separate Spec Kit workflow only when approved requirements routinely need a full spec, plan, and task breakdown.</p></aside>

{{< /slide >}}

{{< slide key="agents" track="agents" eyebrow="Step 02" title="Define AI rules before implementation" subtitle="An Issue says what this change is; AGENTS.md says how an agent works in the repository." legacy="false"  class="candidate-slide" >}}
**Baseline.** An Issue bounds the work, `AGENTS.md` explains how to work, and code plus tests provide evidence. People retain product direction and material-risk decisions.

- **Work and context:** GitHub Issues and PRs record scope, progress, and evidence. Approved specs and ADRs retain long-lived decisions; add a plan only for cross-session, high-risk, or hard-to-recover work, and never save chat transcripts.
- **AI rules:** the root `AGENTS.md` is the single source; `CLAUDE.md` is a thin import, and a child file exists only for a genuine scoped difference.
- **Change isolation:** each writable task uses its own branch and worktree. Parallelize only independent scopes; read-only work needs no extra worktree.
- **Verification evidence:** run the smallest relevant local program. Actions provide events and permissions and call the same program instead of copying logic.
- **Decisions and authorization:** people own requirements, material trade-offs, external impact, and irreversible operations. Rules governance defines review, merge eligibility, and exceptions.
- **Template creation and updates:** Copier generates and updates the shared baseline; the Template upgrades section defines existing-repository updates.

`README.md` serves people, `AGENTS.md` serves every agent, and `template/AGENTS.md.jinja` plus `copier.yml` emit only commands the selected profile can run. `scripts/cleanup-worktrees` and `scripts/test-worktree-cleanup` handle safe cleanup; `scripts/verify`, `.github/workflows/`, and `policies/` keep rules, evidence, automation, and governance separate.

{{< /slide >}}

{{< slide key="contract" track="contract" eyebrow="Step 03" title="Verify the change, then let CI rerun the same rules" subtitle="Issue PRs are tiered by change scope; full verification is reserved for high-risk boundaries." legacy="false"  class="candidate-slide" >}}
- **During development:** run only the focused check that proves the current change, using fresh output before claiming completion.
- **Issue PR (work branch → dev):** the system selects the appropriate checks from the change; when unsure, it runs full verification.
- **When full verification is needed:** run it before a release, for an urgent fix, or whenever the system cannot safely narrow the test scope.
- **One implementation:** GitHub Actions has one `verify` job with a 30-minute timeout and only calls repository scripts.
- **Repository scope:** a normal repository checks its own changes; the template repository also confirms that newly generated repositories work.

Verification logic lives only in scripts and tests. This step restores only `.github/workflows/ci.yml`; release, promotion, security scanning, remote governance, deployment, and scheduled workflows remain decisions for their own Journeys.
{{< /slide >}}

{{< slide key="pr" track="pr" eyebrow="Step 05" title="Make completed changes reviewable and deliverable" subtitle="A work PR completes one work item; a release PR then carries the verified batch into main." legacy="false"  class="candidate-slide" >}}
| PR stage | Destination | What this stage completes |
| --- | --- | --- |
| Issue PR | Work branch → dev | Review one change and close its linked Issue after merge |
| Release PR | dev → main | Fully verify and deliver the batch; Version / delivery then closes the Milestone |

{{< disclosure key="pr-version-intent" title="PR titles, branches, and exceptions" >}}
- Work branches use `type/<Issue>-short-slug`, and the PR links the matching open Issue.
- PR titles use the Angular / Conventional Commits form `type(scope)!: English summary`: `feat` adds a feature, `fix` corrects behavior, `docs` changes documentation, `refactor` restructures code, `test` changes tests, `build` changes builds or dependencies, `ci` changes automation, `chore` performs maintenance, and `revert` undoes a change. Scope and `!` are optional. Release intent is minor for `feat`, patch for `fix` / `revert`, major for `!`, and no release for the other types.
- The classification label and Milestone match the linked Issue; the PR author must be an assignee.
- Milestone work targets `dev/m<Milestone>-*`; ordinary standalone work targets `dev/next`.
- When main advances, a `sync/main-to-*` PR updates active dev branches without direct pushes or history rewrites.
- Only an explicitly labeled standalone hotfix may target main directly. Rules governance decides who may merge.
{{< /disclosure >}}
{{< /slide >}}

{{< slide key="supply" track="supply" eyebrow="Step 04" title="Update, check, and record third-party packages separately" subtitle="Observe ordinary releases, act on known vulnerabilities immediately, and retain a traceable release inventory." legacy="false"  class="candidate-slide" >}}
| Risk | What the template does today |
| --- | --- |
| A dependency change cannot be reproduced | PR verification reinstalls the locked versions and runs the required checks |
| A newly published malicious version | Dependabot opens grouped PRs; ordinary releases wait three days, while security updates do not |
| A disclosed vulnerability goes unnoticed | Dependency PRs and release candidates run OSV; a weekly scan covers periods without PRs |
| Nobody knows what a release contains | Dependency security owns and verifies the SBOM contract when delivery produces real artifacts |

{{< detail key="supply-boundaries" title="Why these four protections stay separate" >}}
- **Locked versions:** reproduce the same package set on every install.
- **Observation window:** avoid adopting an ordinary release on day one.
- **Vulnerability scan:** check disclosed security issues immediately, without waiting three days.
- **Software bill of materials (SBOM):** list packages present in the released artifact for investigation; it does not block vulnerabilities by itself.
{{< /detail >}}
{{< /slide >}}

{{< slide key="deploy" track="deploy" class="dense" eyebrow="Step 06" title="Connect version policy to artifacts" subtitle="Verify the promotion source, then select a safe delivery mode from current platform capabilities." legacy="false" >}}
**Milestone closure:** after a successful release records its delivery evidence, close the lifecycle tracking Issue and the Milestone. To stop early, state why and move or cancel every unfinished Issue first.

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
| Free organization + private | Apply baseline settings and retain desired Ruleset in `policies/rulesets.json` | Report `DEGRADED`, assign a reviewer manually, and provide no merge gate |
| Pro personal + private | Apply a Ruleset | Same as Free public |
| Team/Enterprise organization + private | Verify the CODEOWNERS team, then apply a Ruleset | Review, CODEOWNER, and status checks become merge gates |

{{< detail key="governance-observation" title="Concrete operations and observation limits" >}}
Run `scripts/apply-repository-settings.sh plan`, `apply`, then `check`. The check compares CODEOWNERS, repository settings, Actions, policy labels, and effective Rulesets. `scripts/check-governance-drift` can run locally, but its former daily Action remains under `archive/ci-cd/`; it neither runs on a schedule nor opens Issues automatically.

Each check is a snapshot. A setting changed and restored between runs still requires the GitHub audit log or organization monitoring. Complete administration fields should be checked from a trusted checkout with Administration read credentials, never by exposing that token to PR code. GitHub plan upgrades, irreversible operations, and organization-wide permission changes require separate approval from an organization owner.
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

<aside class="config-guidance"><strong>Website access</strong><p>If reader restrictions become necessary, evaluate Cloudflare Pages + Access first. The host, identity provider, data policy, and organization owner still require separate approval.</p></aside>
{{< /slide >}}

{{< slide key="rollout" track="rollout" eyebrow="Step 10" title="Adopt in stages, with a stop after every step" subtitle="Maturity follows operational evidence, not a date or the mere presence of files." legacy="false"  class="candidate-slide" >}}
| Level | Current state |
| --- | --- |
| Baseline capability | Four profiles, Issues/specs, PR/CI, local verification, lockfile policy, and the repository site have executable implementations |
| Verified online | Release handoff, traceable artifacts, consumer attestation, and the first CI-only downstream adoption and update |
| Still piloting | Python, TypeScript, and mixed compositions each need one real consuming-repository pilot |
| Future/optional | Central catalog or governance, Go/Rust, authenticated hosting, deployment, monitoring, RAG, and autonomous agents |

{{< detail key="rollout-evidence" title="Why capabilities are not enabled all at once" >}}
A big-bang switch spreads defects across every project; a calendar date does not prove readiness; a profile without real adoption evidence is only a promise. `profiles/catalog.yaml` separates synthetic verification from consuming-repository evidence. `scripts/verify-template.sh` proves generation and update paths, but cannot replace a pilot.
{{< /detail >}}

<aside class="config-guidance"><strong>Fleet platform thresholds</strong><p>Evaluate a catalog at ten active consuming repositories, or at three or more with repeated owner or service lookup delays. Evaluate central policy enforcement at five or more only after repeated cross-repository drift or measurable manual repair cost.</p></aside>
{{< /slide >}}

{{< slide key="bridge" audience="maintainer" class="dense" eyebrow="May 2026 internal presentation" title="Review the original principles against today's implementation" subtitle="Revisits the SDLC ideas shared internally in May 2026 and marks what is retained, adjusted, or deferred." legacy="false" >}}
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
| Dependabot, OSV, Syft | Dependency updates, vulnerabilities, and SBOM | Dependabot and OSV are active; the SBOM contract is verified against real release artifacts |
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

{{< slide key="testing" audience="maintainer" parity="supplemental" eyebrow="Maintenance appendix | CI/CD settings" title="CI/CD settings | Checks by Journey" subtitle="Separates the tests and automation that normal repositories and repo-template need for Issue PR (work branch → dev) and Release PR (dev → main)." class="similar-tools-slide testing-slide" legacy="true" >}}
{{< testing >}}
{{< /slide >}}

{{< slide key="access-control" audience="archive" class="dense" eyebrow="Access decision" title="Temporary protection before a hosting choice" subtitle="Current measures reduce accidental sharing; none is described as access control." legacy="false" >}}
| Option | Cost and benefit | Current limitation or owner |
| --- | --- | --- |
| Cloudflare Pages + Access | Free allowance can provide a small-team login wall | Organization owner must establish Cloudflare, domain, DNS, and SSO/OTP policy |
| GitHub Pages + IP restriction | Reuses the GitHub organization | Private Pages and IP allow lists require Enterprise Cloud; current Free plan cannot provide them |
| Backstage, Confluence, or another internal portal | Can govern several internal documents together | One site does not justify an IT/platform-operated service today |

{{< detail key="access-control-limit" title="What exists and what it cannot do" >}}
`docs/index.html` contains `noindex,nofollow`, while `docs/robots.txt` asks crawlers to stay away. Neither authenticates a reader, and anyone with the offline file can forward it. Maintainers must separately approve a host, identity provider, data policy, and audit policy. Issue #79 tracks that decision.
{{< /detail >}}
{{< /slide >}}

{{< slide key="principles" audience="archive" class="dense" eyebrow="Key decisions" title="Rules, reasons, and deliberate omissions" subtitle="These decisions are backed by current files and checks." legacy="false" >}}
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

{{< slide key="benchmark" audience="archive" class="dense" eyebrow="External benchmark and live evidence" title="A solid foundation, not a complete platform" subtitle="New projects, Copier updates, OSV, Release, and the first CI-only pilot have evidence; remaining boundaries stay explicit." legacy="false" >}}
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

{{< slide key="fleet-inventory" audience="archive" class="dense" eyebrow="Fleet governance" title="Inventory real repositories, not assumptions" subtitle="As of 2026-08-24, the organization has six private repositories and one consuming repository." legacy="false" >}}
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

{{< slide key="fleet-governance-thresholds" audience="archive" eyebrow="Fleet thresholds" title="Measure the problem before adding a platform" subtitle="Catalog and policy enforcement solve different problems and use separate evidence." legacy="false"  class="candidate-slide" >}}
| Need | Quantified reevaluation threshold |
| --- | --- |
| Catalog / Backstage | Ten active consuming repositories; or at least three plus two Issues within 90 days recording owner/service lookup over 30 minutes |
| Central policy enforcement | At least five consuming repositories plus the same drift in 2+ repositories within 30 days; or 20%+ update PRs older than five workdays for two releases; or more than two manual repair hours per month |

{{< detail key="fleet-thresholds-yagni" title="Conditions still required after a threshold triggers" >}}
Open an evaluation Issue that names a platform owner, cost ceiling, trial scope, and exit criteria. Backstage handles catalog, ownership, and system relationships; Allstar or Safe Settings handles continuing policy checks and settings delivery. They do not substitute for each other. Until a threshold is met, keep Copier, JSON policy, GitHub API checks, and daily drift detection without prebuilding an external service.
{{< /detail >}}
{{< /slide >}}

{{< slide key="spec-format" audience="archive" eyebrow="Specification format" title="Default to an Issue; create a Milestone only for an explicit story" subtitle="Keep one lightweight format instead of maintaining two systems before the need exists." legacy="false"  class="candidate-slide" >}}
| Option | Current state |
| --- | --- |
| Current `docs/specs/*.md` | Front matter records ID, priority, state, and optional tracking; markers repeatably synchronize an Issue or Milestone |
| GitHub Spec Kit | `/specify → /plan → /tasks → /implement`; requires another CLI and supported AI tool, with no built-in one-spec-to-one-Issue synchronization |

{{< detail key="spec-format-cost" title="Why migration is deferred and what would trigger it" >}}
Adopting Spec Kit requires rewriting `scripts/spec_to_issue.py`, converting existing specs, updating verification assertions, and designing an equivalent Issue sync. Supporting both formats adds cognitive and maintenance cost. Reevaluate when approved specifications regularly need reliable AI decomposition into several work items and the team accepts an additional CLI/agent workflow. Issue #77 tracks the decision.
{{< /detail >}}
{{< /slide >}}
