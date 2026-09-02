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
Standard mode is for general AI-assisted or vibe-coding developers; it does not assume an engineering or CI/CD operations background. It explains what to do and what result to expect. Files, scripts, and GitHub Actions stay in Maintenance mode.

| Choice | Production capability available today |
| --- | --- |
| Programming languages | Select Python, Rust, and TypeScript independently; select none for the shared workflow only |
| Branch approach | One development branch per delivery batch, all changes directly into `main`, or one shared `dev` branch |
| Template settings | Creation or adoption writes choices to `.csarc/config.yml`; template updates maintain this single repository configuration |
| Shared capability | Work-item (Issue) and change-proposal (PR) forms, AI working rules, automated checks, dependency safety, version records, and template updates |

{{< detail key="capability-boundary" title="Adoption paths and current scope" >}}
- **New repository:** choose a project type and branch approach; split only larger outcomes into independently verifiable sub-items.
- **Existing repository:** the template detects current languages and creates `.csarc/config.yml`, then previews the adoption diff while preserving product content.
- **Repository already using the template:** change options or upgrade through `csarc update`; the template updates the configuration and managed files together.
- **Prerequisites:** Git, GitHub CLI, and uv; Rust needs rustup, while TypeScript needs Node 24+ and pnpm 11. Local verification needs no token.

The template promises only capabilities that are implemented and tested. Go, generic deployment, monitoring, AI knowledge retrieval, and hosted documentation remain future or optional work.
{{< /detail >}}
{{< /slide >}}

{{< slide key="flow" track="flow" eyebrow="CI/CD flow" title="The template guides every change" subtitle="Follow the Issue and PR prompts; the template prepares the right settings and tells you what needs attention." legacy="false"  class="candidate-slide" >}}
| What you are doing | How the template guides you |
| --- | --- |
| Create the work | The Issue form prompts for the problem, completion conditions, and necessary context |
| Make the change | Repository guidance tells people and agents how to work and which local check to run first |
| Open a PR | The PR template prompts for the linked Issue, completed result, and verification evidence |
| Read verification and dependency results | The template selects the necessary checks; package changes also prove that the saved version list still installs |
| Review and merge | Merge into the correct branch after the result and human review are clear |

Users do not need to memorize workflow or script names. Current automation covers work items, PR rules, necessary verification, and a reviewed automatic version-and-release path.

{{< detail key="flow-foundation" title="Three foundations across the whole flow" >}}
- **08 Governance:** prepares repository policy, then applies only the controls the live GitHub plan supports.
- **09 Template updates:** Copier carries policy changes back through reviewable PRs.
- **10 Internal site:** keeps practices, limits, evidence, and decisions discoverable.

A failed check is fixed in the same PR. A new problem found after merge becomes a separate, bounded Issue.
{{< /detail >}}
{{< /slide >}}

{{< slide key="files" track="files" class="dense" eyebrow="File map" title="The template puts required settings in the right place" subtitle="This lists the major files currently generated; template updates never silently overwrite product-owned content." legacy="false" >}}
| Path | Purpose | Responsibility |
| --- | --- | --- |
| `.csarc/config.yml` | Template source, languages, branch strategy, and optional capabilities | Template-led |
| `.github/ISSUE_TEMPLATE/`, `pull_request_template.md` | Work definition and PR contract | Template-led |
| `.github/workflows/` | Nine shared flows: Issue triage, Milestone sync, spec sync, PR rules, verification, scheduled vulnerability scanning, reviewer assignment, work item closure, and a candidate release flow, plus the optional governance-drift schedule | Template-led |
| `AGENTS.md`, `README.md`, `CLAUDE.md` | Agent working rules and user entry point | Shared |
| `policies/`, `CODEOWNERS`, `.github/REVIEWERS` | Desired settings, owners, and reviewers | Shared |
| `scripts/` | Local verification, work synchronization, and repository settings | Template-led |
| `docs/`, `site/` | Project guidance, specifications, decisions, and internal site | Shared |
| `src/`, product tests, and product specifications | Product behavior | Project-owned |

{{< detail key="files-update" title="How updates protect product content" >}}
Copier attempts updates on a short branch. A conflict only lists the affected files and leaves the repository unchanged; adjust them, rerun, and then review the PR. Fixtures cover new project generation, existing-repository adoption, and a later update of the same repository. They add product-owned files and prove that an update does not overwrite them.

Workflows, policies, scripts, and documents shared by root and `template/` are kept in sync. Files that differ because of project choices are verified by generating a real project. New repositories receive the release Action; adopted repositories keep their product-owned workflow.
{{< /detail >}}
{{< /slide >}}

{{< slide key="method" track="method" eyebrow="Step 01" title="Define the work before implementation" subtitle="Turn a request into an actionable Issue; create a Milestone only when several work items must move together." legacy="false"  class="candidate-slide dense single-column" >}}
### Our choice

- **Overall:** turn the request into one Issue that can be completed and verified independently.
- **Work branch:** when implementation starts, create one short-lived `type/<Issue>-short-slug` branch per Issue and do not mix unrelated work into it.
- **Milestone:** create one only when several Issues share an outcome, deadline, or delivery batch, and give it one lifecycle tracking Issue.
  - Title it `Milestone <number>: <Milestone title>`; the text after the colon must exactly match the Milestone title.
  - Keep approvals, objections, and early termination in the body or comments, not the title.
  - Work may start only after at least one person other than the proposer agrees and no objection remains unresolved.
  - Under the default delivery-branch strategy, use exactly one active `dev/m<Milestone>-*` branch for the Milestone; all of its work branches merge there.
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

<aside class="config-guidance" data-audience="maintainer"><strong>Fixed and adjustable policy</strong><ul><li><strong>Fixed baseline:</strong>Issues require a problem and acceptance criteria, blank Issues are disabled, and the template owns title, classification, hierarchy, and Milestone-start rules.</li><li><strong>Project choice:</strong><code>docs/specs/</code> may use <code>tracking: issue</code>, <code>story</code>, or <code>none</code> to control work-item synchronization.</li><li><strong>Locations:</strong><code>.github/ISSUE_TEMPLATE/</code>, <code>AGENTS.md</code>, <code>docs/milestone-description.md</code>, and <code>docs/specs/</code>.</li></ul></aside>

{{< /slide >}}

{{< slide key="agents" track="agents" eyebrow="Step 02" title="Define AI rules before implementation" subtitle="An Issue says what this change is; AGENTS.md says how an agent works in the repository." legacy="false"  class="candidate-slide" >}}
**Automated by default.** The template generates and checks the AI rules. People step in only to customize policy, make material decisions, or approve exceptions.

**Baseline.** An Issue bounds the work, `AGENTS.md` explains how to work, and code plus tests provide evidence. People retain product direction and material-risk decisions.

- **Work and context:** GitHub Issues and PRs record scope, progress, and evidence. Approved specs and ADRs retain long-lived decisions; add a plan only for cross-session, high-risk, or hard-to-recover work, and never save chat transcripts.
- **AI rules:** the root `AGENTS.md` is the single source; `CLAUDE.md` is a thin import, and a child file exists only for a genuine scoped difference.
- **Change isolation:** each writable task uses its own branch and worktree. Parallelize only independent scopes; read-only work needs no extra worktree.
- **Verification evidence:** run the smallest relevant local program. Actions provide events and permissions and call the same program instead of copying logic.
- **Decisions and authorization:** people own requirements, material trade-offs, external impact, and irreversible operations. Rules governance defines review, merge eligibility, and exceptions.
- **Template creation and updates:** Copier generates and updates the shared baseline; the Template upgrades section defines existing-repository updates.

`README.md` serves people, `AGENTS.md` serves every agent, and `template/AGENTS.md.jinja` plus `copier.yml` emit only commands the selected profile can run. `scripts/cleanup-worktrees` and `scripts/test-worktree-cleanup` handle safe cleanup; `scripts/verify`, `.github/workflows/`, and `policies/` keep rules, evidence, automation, and governance separate.

<aside class="config-guidance" data-audience="maintainer"><strong>Fixed and adjustable policy</strong><ul><li><strong>Fixed baseline:</strong><code>AGENTS.md</code> is the only AI-rules source; writable tasks use branches and worktrees, while prompts do not duplicate verification or governance logic.</li><li><strong>Adjustable:</strong><code>project_run_command</code> names how to invoke the product; existing repositories may set one repository-relative <code>project_verification_hook</code>.</li><li><strong>Locations:</strong><code>.csarc/config.yml</code>, <code>AGENTS.md</code>, <code>CLAUDE.md</code>, and <code>scripts/cleanup-worktrees</code>.</li></ul></aside>

{{< /slide >}}

{{< slide key="contract" track="contract" eyebrow="Step 03" title="Verify the change, then let CI rerun the same rules" subtitle="Issue PRs are tiered by change scope; full verification is reserved for high-risk boundaries." legacy="false"  class="candidate-slide" >}}
- **During development:** run only the focused check that proves the current change, using fresh output before claiming completion.
- **Work PR (topic → main or `dev/m*`):** the system selects the appropriate checks from the change; when unsure, it runs full verification.
- **When full verification is needed:** run it for a Milestone or canary delivery, an urgent fix, a merge queue, a manual run, or whenever the system cannot safely narrow the test scope.
- **One implementation:** GitHub Actions has one `verify` job with a 30-minute timeout and only calls repository scripts.
- **Repository scope:** a normal repository checks its own changes; the template repository also confirms that newly generated repositories work.

Verification logic lives only in scripts and tests. CI, PR policy, Issue triage, spec-to-Issue, Milestone lifecycle, Work Issue closure, reviewer assignment, and Dependabot are active in a newly generated repository from its first commit. One release workflow is configured as a candidate pending a successful default-branch run. Dedicated promotion, release-handoff, registry publication, consumption, live-integration, remote-governance, and deployment workflows are not active.

<aside class="config-guidance" data-audience="maintainer"><strong>Root repository state</strong><p>In <code>csarc-repo-template</code> itself, OSV is also candidate: its workflow has not yet landed on this repository's own <code>main</code>, and its trigger set does not include <code>pull_request</code>, so it cannot pre-register from a candidate branch. See the CI/CD settings page's current-automation table for the exact live-registration check and timestamp.</p></aside>

<aside class="config-guidance" data-audience="maintainer"><strong>Fixed and adjustable policy</strong><ul><li><strong>Fixed baseline:</strong>local and CI execution share scripts and tests; work PRs select fast or full by risk, while Milestone or canary delivery, hotfix, merge queue, manual, and unknown high-risk changes run full.</li><li><strong>Adjustable:</strong><code>coverage_mode</code>, <code>coverage_threshold</code>, and <code>enable_precommit</code>; advanced teams may enable <code>use_reusable_workflow</code> with a full commit SHA.</li><li><strong>Locations:</strong><code>.csarc/config.yml</code>, <code>scripts/verify-fast</code>, <code>scripts/verify</code>, and <code>.github/workflows/ci.yml</code>.</li></ul></aside>
{{< /slide >}}

{{< slide key="languages" track="languages" eyebrow="Step 04" title="Choose a language and receive the matching checks" subtitle="Each language owns its tools and tests; shared rules run once." legacy="false" class="candidate-slide" >}}
Choose a project language and the template prepares the matching checks:

- **Every project:** checks work rules, documentation, secrets, and dependency safety.
- **Python:** checks formatting, types, tests, and the installable package.
- **Rust:** checks formatting, common mistakes, tests, the release build, and the installable package.
- **TypeScript:** checks formatting, types, tests, and the installable package.

Each language is selected independently. Selecting several languages combines their modules while each shared check still runs once; the documentation does not enumerate combinations.

<aside class="config-guidance" data-audience="maintainer"><strong>Fixed and adjustable policy</strong><ul><li><strong>Fixed baseline:</strong>each language uses its native tools behind one verification entry point; combinations do not create separate workflows.</li><li><strong>Adjustable:</strong><code>languages</code>, <code>python_support_mode</code>, and <code>python_min_version</code>; advanced options remain in each language's native configuration.</li><li><strong>Python:</strong><code>uv</code> installs from <code>uv.lock</code>; <code>Ruff</code> formats and lints (currently 80 columns and Google docstrings); <code>ty</code> checks types; <code>pytest</code> runs tests; <code>coverage.py</code> checks coverage; Hatch verifies the wheel. These settings live in <code>pyproject.toml</code>.</li><li><strong>Rust:</strong><code>rustfmt</code> checks formatting; <code>Clippy</code> treats lint warnings as failures; <code>Cargo</code> installs from <code>Cargo.lock</code>, tests, builds a release, and verifies the package. Settings live in <code>rust-toolchain.toml</code> and <code>Cargo.toml</code>.</li><li><strong>TypeScript:</strong><code>pnpm</code> installs from <code>pnpm-lock.yaml</code>; <code>Biome</code> formats and lints; TypeScript checks types and builds; <code>Vitest</code> tests and measures coverage; <code>npm pack</code> verifies the package. Settings live in <code>package.json</code>, <code>biome.json</code>, and <code>tsconfig.json</code>.</li></ul></aside>
{{< /slide >}}

{{< slide key="pr" track="pr" eyebrow="Step 06" title="Make completed changes reviewable and deliverable" subtitle="A work PR completes one work item; a delivery PR then carries the verified batch into main." legacy="false"  class="candidate-slide" >}}
| PR stage | Destination | What this stage completes |
| --- | --- | --- |
| Standalone work PR | Topic branch → main | Review one change and close its linked Issue after merge |
| Milestone work PR | Topic branch → `dev/m*` | Review one change inside a real delivery batch |
| Delivery PR | `dev/m*` or explicit `dev/i*` → main | Fully verify and deliver the batch; maintainers then close the Milestone and clean up the delivery branch |

{{< disclosure key="pr-version-intent" title="PR titles, branches, and exceptions" >}}
- Work branches use `type/<Issue>-short-slug`, and the PR links the matching open Issue.
- PR titles use the Angular / Conventional Commits form `type(scope)!: English summary`: `feat` adds a feature, `fix` corrects behavior, `docs` changes documentation, `refactor` restructures code, `test` changes tests, `build` changes builds or dependencies, `ci` changes automation, `chore` performs maintenance, and `revert` undoes a change. Scope and `!` are optional. Release intent is minor for `feat`, patch for `fix` / `revert`, major for `!`, and no release for the other types.
- The classification label and Milestone match the linked Issue; the PR author must be an assignee.
- Milestone work targets `dev/m<Milestone>-*`; ordinary standalone work targets `main` directly.
- A `sync/main-to-*` PR updates a Milestone or explicit canary branch before final delivery, or earlier only when its owner records a real dependency. It never fans out to every branch.
- Only an explicitly labeled standalone hotfix may target main directly. Rules governance decides who may merge.
{{< /disclosure >}}

<aside class="config-guidance" data-audience="maintainer"><strong>Fixed and adjustable policy</strong><ul><li><strong>Fixed baseline:</strong>a PR links one work item, follows title and classification rules, and passes verification; work and delivery PRs keep separate responsibilities.</li><li><strong>Adjustable:</strong><code>branch_strategy</code> selects the branch model; <code>code_owner</code> and <code>reviewers</code> select ownership and review candidates.</li><li><strong>Locations:</strong><code>.csarc/config.yml</code>, the PR template, <code>CODEOWNERS</code>, <code>REVIEWERS</code>, and PR policy.</li></ul></aside>
{{< /slide >}}

{{< slide key="supply" track="supply" eyebrow="Step 05" title="Update, check, and record third-party packages separately" subtitle="Observe ordinary releases, act on known vulnerabilities immediately, and retain a traceable release inventory." legacy="false"  class="candidate-slide" >}}
Routine updates and security checks run automatically. People step in only for upgrade conflicts, vulnerability response, and risk acceptance.

| Risk | What the template does today |
| --- | --- |
| A dependency change cannot be reproduced | PR verification reinstalls from the locked-version list (lockfile), so every run receives the same packages |
| A newly published malicious version | GitHub's automated update service (Dependabot) groups update PRs; ordinary releases wait three days, while security updates do not |
| A disclosed vulnerability goes unnoticed | The Open Source Vulnerabilities scan (OSV) checks dependency changes and delivery candidates; a weekly scan covers periods without PRs |
| Nobody knows what a release contains | A software bill of materials (SBOM) lists packages in the artifact; dependency security verifies it when delivery produces the artifact |

{{< detail key="supply-boundaries" title="Why these four protections stay separate" >}}
- **Locked versions:** reproduce the same package set on every install.
- **Observation window:** avoid adopting an ordinary release on day one.
- **Vulnerability scan:** check disclosed security issues immediately, without waiting three days.
- **Software bill of materials (SBOM):** list packages present in the released artifact for investigation; it does not block vulnerabilities by itself.
{{< /detail >}}

<aside class="config-guidance" data-audience="maintainer"><strong>Fixed and adjustable policy</strong><ul><li><strong>Fixed baseline:</strong>lockfile installs, Dependabot, OSV, and artifact SBOMs have separate jobs; ordinary releases wait three days while security updates do not.</li><li><strong>Adjustable:</strong><code>security_reporting_channel</code> names the private reporting path; <code>project_visibility</code> and <code>enable_codeql</code> decide whether CodeQL is generated.</li><li><strong>Locations:</strong><code>.csarc/config.yml</code>, lockfiles, <code>dependabot.yml</code>, <code>osv.yml</code>, <code>codeql.yml</code>, and <code>SECURITY.md</code>.</li></ul></aside>
{{< /slide >}}

{{< slide key="deploy" track="deploy" class="dense" eyebrow="Step 07" title="Separate version, release, delivery, and deployment" subtitle="Work reaches main first; when a version is needed, the system opens a version PR for human review." legacy="false" >}}
- **Version intent:** a PR title states major, minor, patch, or no-release impact without reserving an exact number.
- **Version materialization:** Release Please opens one reviewed PR that updates version files, package metadata, and the changelog together. CI does not make a temporary version edit in its checkout.
- **Release:** after that PR merges and full verification passes, the system creates the immutable tag, GitHub Release, explicit artifacts, checksums, and SBOM.
- **Delivery:** merging to `main` is repository delivery and may happen without a new version. A work PR completes one item; a Milestone delivery PR carries the batch.
- **Standalone work:** when one Issue can be reviewed and verified independently and has no shared deadline or cross-Issue dependency, it needs no Milestone and may target `main` directly.
- **Hotfix:** only an urgent defect in `main` uses this route. It still needs a Bug Issue, another reviewer, and full verification; a reviewed version PR then materializes the patch release.
- **Deployment:** operating the product in a real runtime with health checks and recovery belongs to the consuming product, not this template.

| Capability | Current status | Current behavior |
| --- | --- | --- |
| SemVer intent in PRs | Active | `fix` / `revert` means patch, `feat` means minor, `!` means major, and other types mean no release |
| Exact version and changelog | Candidate / Guided | Automatic uses a reviewed Release Please PR; when platform policy blocks it, Guided uses a normal PR opened by a person or agent |
| Tag and GitHub Release | Candidate / Blocked | The sole workflow publishes after the version PR; activation awaits a default-branch run |
| Checksums and SBOM | Configured | Included in the same candidate path; Active only after its first successful run |
| Attestations and consumption | Conditional | Products opt in when registry and supply-chain needs justify them |
| PyPI, npm, and GHCR | Conditional gap | The root publishes to no registry; generated projects expose settings but receive no publisher job, tracked by #439 |

{{< detail key="standalone-delivery" title="When standalone work must join a Milestone" >}}
An Issue may branch from the latest `main`, target `main`, and close through `Closes #N` when it can be accepted on its own and has no shared deadline, batch acceptance, cross-Issue dependency, or isolated test environment. If any of those needs appears, assign the Issue to the appropriate Milestone before implementation and use `dev/m*`; the standalone route cannot bypass batch review.
{{< /detail >}}

{{< detail key="deploy-ordering" title="Delivery ordering, artifacts, and registry boundaries" >}}
Direct mode rereads the default-branch head before writing and delivers only when the latest `main`, source, tag, CHANGELOG, and promotion evidence agree; workflow concurrency is not treated as FIFO. The artifact workflow accepts only a release-source run ID, creates a digest and SBOM, ignores arbitrary tag pushes, and does not repeat full CI.

GitHub Release is the portable baseline for every profile. Registry publishing and container delivery are product-owned extensions because the template does not ship an active publisher for them. `scripts/release_policy.py` detects GitHub release capabilities and configures versions; `scripts/promotion_gate.py` validates promotion.
{{< /detail >}}

{{< detail key="hotfix-delivery" title="Hotfix review, verification, and evidence" >}}
A hotfix uses a Bug Issue without a Milestone, the `bug` and `hotfix` labels, `fix/<Issue>-*`, and a `fix(scope): summary` PR directly to `main`. Normal review and full verification still apply. Undisclosed security defects use a GitHub Security Advisory instead. After merge, retain the PR, commit SHA, full run, and rollback note. `fix` normally declares patch intent; the exact version is still reviewed in the Release Please version PR.
{{< /detail >}}

{{< detail key="manual-release-boundary" title="Automatic-release ownership" >}}
The template root and each new repository are configured to publish through their own release workflow. An adopted repository keeps its product-owned workflow. Every path still needs one owner, least privileges, full-SHA pins, a timeout, concurrency behavior, failure recovery, and a runner-cost ceiling; historical runs remain reference evidence only.

Milestone closure remains manual until #400 completes its lifecycle contract, and work-Issue closure remains owned by #401. Work branches are removed after merge; a Milestone delivery branch waits until closure and unfinished work are handled.
{{< /detail >}}
{{< /slide >}}

{{< slide key="governance" track="governance" class="dense" eyebrow="Step 08" title="Apply only the controls GitHub can enforce" subtitle="The template prepares one policy; a maintainer checks the live plan before relying on it." legacy="false" >}}
The template always prepares owners, reviewers, repository defaults, and the desired branch rules. A maintainer then checks the live repository:

- supported controls are applied and verified;
- an unavailable paid control is reported as `DEGRADED` and replaced with an explicit human step, never described as enforced;
- a fixable mismatch fails until corrected.

{{< detail key="governance-capability" title="Plan capability, activation, and upgrade conditions" >}}
| GitHub state | What the template can do | Human responsibility |
| --- | --- | --- |
| Free + public, or Pro personal + private | Apply and check the repository Ruleset | Review the planned change before applying it |
| Free organization + private | Apply baseline settings and retain the desired Ruleset in `policies/rulesets.json` | A workflow assigns and records review automatically; there is no enforced merge gate |
| Team / Enterprise organization + private | Validate the CODEOWNERS team, then apply and check the Ruleset | Approve organization-level identity, network, audit, or irreversible changes separately |

Capability is enabled by evidence, not by a predefined maturity label or calendar date. Re-run `plan`, `apply`, and `check` after a visibility or plan change. A real unsupported capability stays `DEGRADED`; an unexpected API or configuration error stops.
{{< /detail >}}

{{< detail key="governance-config" title="One configuration source and its ownership layers" >}}
| Layer | `.csarc/config.yml` key | Default / allowed values | Generated or checked at |
| --- | --- | --- | --- |
| Required baseline | `branch_strategy` | `delivery` by default; `delivery` or `main` | branch guidance and `policies/rulesets.json` |
| Organization policy | `code_owner` | one existing `@organization/team` with repository write access | `.github/CODEOWNERS`; checked by repository-settings plan/apply/check |
| Organization policy | `reviewers` | one or more GitHub usernames | `.github/REVIEWERS`; `governance-comment.yml` assigns automatically on every non-draft pull request |
| Project choice | `project_visibility` | `private` by default; `public`, `private`, or Enterprise `internal` | capability detection and optional security defaults |
| Project opt-in | `enable_governance_drift_check` | `false` by default; set `true` to generate the daily scheduled Action | `false` keeps only the local drift checker; `true` also generates `governance-drift.yml` |

The template repository uses the same public keys and validation as generated repositories. Only generated repositories add Copier `_src_path` and `_commit` metadata. Derived templates may add namespaced keys to this same YAML; they do not create another profile. Low-frequency GitHub details stay in native repository settings or `policies/` instead of expanding the CSARC schema.

The internal site renders `docs/site-content.md` and resolves its explicit `[[key]]` tokens from the existing `project_name`, `project_description`, `repository_url`, `code_owner`, `languages`, and `branch_strategy` settings. Project content and theme remain in `docs/site-content.md` and `docs/site-theme.css`; the site does not create another configuration schema.
{{< /detail >}}

{{< detail key="governance-exceptions" title="How to record a temporary exception" >}}
Use a linked Issue to record the proposer, a different approver, expiry, evidence, and recovery action. The exception may narrow a control only when the platform cannot provide it or a time-bounded incident requires recovery. It cannot claim a missing check passed, expose a privileged token to pull-request code, or silently become permanent. Close the exception only after recovery is verified; renew it through another explicit approval.
{{< /detail >}}
{{< /slide >}}

{{< slide key="template-release" track="template-release" eyebrow="Step 09" title="Copier keeps repositories aligned, and the template dogfoods its rules" subtitle="A template defect affects many projects, so creation, adoption, and update all run as real tests." legacy="false"  class="candidate-slide" >}}
- `template/` is the delivered source; root retains the template repository's own GitHub governance and dogfood configuration.
- `.csarc/config.yml` is both Copier's update record and the repository's only template configuration. Languages, branch strategy, and optional capabilities read from it; later extensions add settings here instead of creating another configuration file.
- A new repository selects its languages and capabilities, then receives a baseline it can verify directly. Selecting several languages only combines their independent modules.
- A first adoption uses a pinned CLI outside the repository to produce an external change plan, then applies that same plan. A person reviews the first PR because the old default branch does not yet contain a trusted verifier.
- After that first merge, the default branch supplies the trusted PR policy and read-only CI verifies the candidate. Updates still begin with a preview; a conflict leaves the repository unchanged so it can be corrected and rerun.
- The optional update notice checks weekly and only creates or refreshes one Issue; it never modifies the repository automatically.

{{< disclosure key="copier-update" title="Copier + root dogfood + create/update regression" >}}
[Copier](https://github.com/copier-org/copier) records source, language, and answers, then reapplies newer template revisions to an editable repository. A person approves the first adoption. A later update conflict leaves the repository unchanged so the affected files can be corrected, rerun, and reviewed in a PR. GitHub Template copies only once, while PyScaffold would create a second update mechanism, so neither fits this requirement.
{{< /disclosure >}}

{{< detail key="template-release-scope" title="Single source, runtime baselines, and the root-only boundary" >}}
Root `.csarc/config.yml` records the capabilities selected by the template repository itself. A generated repository additionally records Copier's source and revision and writes changes through `csarc update --data`. The template source does not invent `_src_path` or `_commit` values that point back to itself or immediately become stale. A derived template should add namespaced settings to the same YAML instead of duplicating CSARC fields.

`enable_template_update_notifications` generates `template-update.yml` and `check-template-update` only when selected. Public sources need no secret; private sources use a repository secret limited to read-only access to that template source.

`scripts/sync-paired-files.sh` makes root the source of paired files and verifies copied content and permissions with `--check`. `profiles/catalog.yaml` records runtime baselines and their evidence. Python and Node baselines advance only after their own thirty-day observation period.

`scripts/verify-template.sh` runs create/adopt/update fixtures only in the template repository and is never delivered downstream. Generated repositories use the smaller `scripts/verify` entry point. The first-adoption machine plan stays outside the target, so proposed files cannot rewrite their own evidence. After the first PR merges, its base supplies the trusted PR policy and read-only CI runs candidate verification.
{{< /detail >}}

{{< detail key="template-release-status" title="Current automation boundary" >}}
- **Active:** the CLI creates, adopts, or updates and verifies a candidate before writing the target; template full verification reruns all three paths.
- **Manual:** a person approves the external plan, source, and first adoption PR.
- **Pending:** the update-notice workflow and checker script are restored, and a Copier fixture test verifies they are generated only when selected; the checker's own update-detection and Issue-notification logic has no dedicated regression test, and no hosted scheduled run has been observed, so live-schedule execution is not yet claimed.
- **Retired:** remote governance and delivery orchestration do not return with this page; reviewer assignment is restored and covered under Rules governance instead.
{{< /detail >}}
{{< /slide >}}

{{< slide key="docs-site" track="docs-site" eyebrow="Step 10" title="A portable single file remains the baseline" subtitle="Hugo owns content structure; the existing renderer produces an offline, forwardable HTML file." legacy="false"  class="candidate-slide" >}}
- `site/content/` holds bilingual Markdown with matching content keys.
- `site/static/styles.css` retains the presentation identity; Hugo shortcodes produce the shared content structure.
- `scripts/render_site.py` embeds CSS, JavaScript, fonts, and images and rejects external runtime assets.

{{< disclosure key="portable-bundle" title="Markdown + Hugo → self-contained HTML" >}}
`docs/adr/` preserves canonical choices. Hugo owns content and HTML; the unchanged renderer only embeds assets and enforces safety checks. The final `docs/index.html` opens offline through `file://` without Pages, a CDN, or a JavaScript package runtime.
{{< /disclosure >}}

{{< detail key="docs-site-access" title="Access and maintenance boundaries" >}}
`noindex` and `robots.txt` reduce accidental spread but are not access control. An approved host can protect entry, but a downloaded HTML file can still be forwarded. An agent records only user-confirmed durable constraints in an Issue and a reviewed decision record, never a raw conversation transcript.

The renderer reads project identity, owner, languages, repository URL, and branch guidance from the existing `.csarc/config.yml`. Product-specific prose lives in `docs/site-content.md`, theme overrides remain in `docs/site-theme.css`, and the generated `docs/index.html` is never edited directly.
{{< /detail >}}

<aside class="config-guidance"><strong>Website access</strong><p>If reader restrictions become necessary, evaluate Cloudflare Pages + Access first. The host, identity provider, data policy, and organization owner still require separate approval.</p></aside>
{{< /slide >}}

{{< slide key="bridge" audience="maintainer" class="dense" eyebrow="May 2026 internal presentation" title="Review the original principles against today's implementation" subtitle="Revisits the SDLC ideas shared internally in May 2026 and marks what is retained, adjusted, or deferred." legacy="false" >}}
| Earlier topic | Current decision |
| --- | --- |
| Core SDLC stages | Keep plan, build, test, deliver, and monitor in maintainable GitHub objects |
| Jira ticket | Use a minimal GitHub Issue; add a Milestone or spec only for an explicit story |
| Version control | A delivery branch is a CI integration boundary, not a pretend physical environment |
| PR and review | Issue, numbered branch, PR, CI, and human approval form one chain |
| CI pipeline | Ordinary work uses fast; promotion, hotfix, and unknown high-risk paths use full |
| CD management | Delivery to main is distinct from Release; no deployment is claimed without a real runtime target |
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
| ![zizmor logo](../assets/zizmor.png) [zizmor](https://github.com/zizmorcore/zizmor) | GitHub Actions security | The local contract remains; its dedicated workflow is archived |
| Dependabot, OSV, Syft | Dependency updates, vulnerabilities, and SBOM | Dependabot is active; OSV is active in a new repository and candidate here pending this repository's own `main` landing; the SBOM contract is conditional and locally tested |
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

{{< slide key="testing" audience="maintainer" parity="supplemental" eyebrow="Maintenance appendix | CI/CD settings" title="CI/CD settings | Checks by Journey" subtitle="Separates the tests and automation that normal repositories and repo-template need for work and repository-delivery pull requests." class="similar-tools-slide testing-slide" legacy="true" >}}
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
| Language quality | Python uses src layout, uv, Ruff, ty, and pytest; Rust uses rustfmt, Clippy, and Cargo; TypeScript uses Node 24, pnpm 11, Biome, and Vitest |
| CI and versioning | Local and CI share entry points; daily fast, promotion full, one SemVer |
| Supply chain | Delay, OSV, hashes, SBOM, and resolver checks address different risks |
| AI and docs | `AGENTS.md` is the working contract; README and the site serve people |
| Verification resources | Use local temporary projects or this repository; never create a GitHub repository only for testing |

{{< detail key="principles-transcript" title="How durable decisions are recorded" >}}
Agents do not save raw conversations. Only a user-confirmed durable architecture, security, compatibility, or platform constraint is summarized into an Issue and then written to `docs/adr/` or `docs/decisions/` through a scoped PR. Executable configuration remains authoritative, and changed conditions are updated through another Issue and PR.
{{< /detail >}}
{{< /slide >}}

{{< slide key="benchmark" audience="archive" class="dense" eyebrow="External benchmark and live evidence" title="A solid foundation, not a complete platform" subtitle="Active capabilities use current files and runs; historical release evidence remains explicitly archived." legacy="false" >}}
| Benchmark or probe | Assessment | Current evidence and boundary |
| --- | --- | --- |
| Copier vs projen | Good fit | Editable output plus smart update matches the requirement |
| Spotify Golden Path / Backstage | Only one layer | This is a single-repository foundation, not a cross-team catalog platform |
| Allstar / Safe Settings | Sufficient today | Scheduled drift checks exist; revisit central enforcement as the fleet grows |
| GitHub Rulesets / Free private | Partial | Capability can be detected and reported, but the plan cannot enforce Rulesets |
| Historical Release Please runs | Archived evidence only | Earlier runs prove a retired design, not a current workflow; the manual baseline and restoration criteria are recorded in the release ADR |
| OSV reusable workflow | Corrected | A successful main run exists after permission propagation was fixed |
| Artifact Attestations / SLSA | Conditional contract | Local tests retain repository, tag, digest, and signer checks; no active consumer workflow exists |
| OpenSSF Scorecard | Plan-aware | Public enables CodeQL by default; private/internal explicitly opt in when licensed |
| Real consuming repository | Shared lifecycle proven | `ai-guardrail` adopted v0.2.4 and updated to v0.3.1; language modules carry separate executable beta evidence |

{{< detail key="benchmark-gap" title="Current gaps" >}}
There is no cross-repository catalog, comprehensive hosted governance, registry publisher, or generic deployment platform. Historical live-integration runs remain audit evidence only; active workflow claims must come from files under `.github/workflows/` and current runs. Production repositories will add operational evidence without serving as disposable language test fixtures.
{{< /detail >}}
{{< /slide >}}

{{< slide key="fleet-inventory" audience="archive" class="dense" eyebrow="Fleet governance" title="Inventory real repositories, not assumptions" subtitle="As of 2026-08-24, the organization has six private repositories and one consuming repository." legacy="false" >}}
| Repository | Owner | Template state | Drift data |
| --- | --- | --- | --- |
| `csarc-repo-template` | `@Innoguard-Cyber-Arch/arch` | Source repository | Historical live integration proved one earlier design; no current drift sample is claimed |
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
