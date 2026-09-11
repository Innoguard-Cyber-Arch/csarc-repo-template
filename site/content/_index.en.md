+++
title = "CSARC Repo Template | AI-assisted SDLC foundation"

[controls]
menu = "Slide outline"
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

{{< slide key="index" track="index" eyebrow="Home" title="CSARC Repo Template" subtitle="Cyber-Arch's updatable repository foundation: creating a new project, adopting an existing one, and receiving policy updates all preview and verify before a PR merges them." class="legacy-slide capability-slide" legacy="true" >}}
{{< legacy >}}
      <header class="package-hero">
        <p class="package-kicker">Innoguard-Cyber-Arch / repository infrastructure</p>
        <h1><code>csarc-repo-template</code></h1>
        <p class="subtitle lead-question">How does this template get every change -- human or AI -- defined, verified, reviewed, and evidenced?</p>
        <p class="subtitle"><!-- csarc-readme-preamble-tagline:start -->Cyber-Arch's updatable repository foundation: creating a new project, adopting an existing one, and receiving policy updates all preview and verify before a PR merges them. Use the common workflow alone, or opt into Python, Rust, and TypeScript independently.<!-- csarc-readme-preamble-tagline:end --></p>
        <p class="subtitle flow-line"><strong>Result:</strong> every change, human or AI, is scoped, checked, and reviewed before it merges -- leaving evidence behind.</p>
        <p class="subtitle">Standard mode is for general AI-assisted or vibe-coding developers; it does not assume an engineering or CI/CD operations background. Maintenance mode adds configuration files, code, and technical rationale. See the <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template#readme" target="_blank" rel="noreferrer">repo README</a> for quick-start commands.</p>
        <div class="package-badges" aria-label="Package status">
          <span class="package-badge beta">beta</span>
          <span class="package-badge python">3 language modules</span>
          <span class="package-badge">Continuously updatable template</span>
          <span class="package-badge muted">v0.15.3</span><!-- x-release-please-version -->
          <span class="package-badge muted">Site template v[[site_template_version]]</span>
          <span class="package-badge muted">Render engine v[[site_engine_version]]</span>
        </div>
      </header>
      <div class="language-contract" aria-label="Languages and template settings">
        <p class="language-card"><strong>Choose languages at creation or adoption</strong>Check whichever of Python, Rust, and TypeScript you need; select none for the shared workflow only.</p>
        <p class="language-card shared"><strong>One template configuration</strong>Languages, branching, and optional capabilities live in <code>.csarc/config.yml</code>, kept current by template updates.</p>
        <p class="language-card future"><strong>Currently supported versions</strong>Python 3.14, Rust 1.98, TypeScript on Node 24 LTS. Go is not supported yet, so it generates no empty config.</p>
      </div>
      <div class="product-start">
        <section class="product-scope" aria-label="What the template provides">
          <h3>What the template prepares</h3>
          <p class="scope-row"><strong>Planning and AI rules</strong><span>Work is scoped first; only large outcomes split into sub-items</span></p>
          <p class="scope-row"><strong>Verification and merging</strong><span>Checks run locally first; GitHub checks the proof, then the team reviews</span></p>
          <p class="scope-row"><strong>Dependency evidence</strong><span>Pinned versions, a soak period, vulnerability scans, a build manifest</span></p>
          <p class="scope-row"><strong>Continuous sync</strong><span>Template updates arrive as a reviewable diff, never a silent overwrite</span></p>
        </section>
        <section class="start-paths" aria-label="Three ways to start">
          <h3>Start from your repo's current state</h3>
          <article class="start-path primary"><h3>Create a new repo</h3><p>Settle on a type and branch approach first; nothing is created or pushed to GitHub before that.</p><button class="setup-trigger" type="button" data-setup="new" aria-expanded="false">Start now</button></article>
          <article class="start-path"><h3>Adopt an existing repo</h3><p>Preview the diff on an isolated branch, keeping your content untouched.</p><button class="setup-trigger" type="button" data-setup="existing" aria-expanded="false">Adoption command</button></article>
          <article class="start-path"><h3>Update a repo already on the template</h3><p>A dry run produces a reviewable diff first; it merges only after you confirm, never straight into main.</p><button class="setup-trigger" type="button" data-setup="update" aria-expanded="false">Update command</button></article>
        </section>
      </div>
      <div class="prerequisite-line product-prerequisites">
        <p><strong>Install before you start</strong>Git, GitHub CLI, and uv; see the full list, including optional Rust/TypeScript tooling, in Maintenance mode.</p>
        <button class="setup-trigger" type="button" data-setup="mac" aria-expanded="false">macOS setup</button>
        <button class="setup-trigger" type="button" data-setup="windows" aria-expanded="false">Windows setup</button>
      </div>
      <p class="subtitle bridge-line"><strong>Next:</strong> the Install guide page gives you one complete prompt to paste to your agent -- it previews first and acts only after you confirm; Maintenance mode covers the exact state-detection rules.</p>
{{< /legacy >}}

{{< basic >}}
<!-- csarc-readme-preamble-tagline:start -->Cyber-Arch's updatable repository foundation: creating a new project, adopting an existing one, and receiving policy updates all preview and verify before a PR merges them. Use the common workflow alone, or opt into Python, Rust, and TypeScript independently.<!-- csarc-readme-preamble-tagline:end --> Standard mode is for general AI-assisted or vibe-coding developers; it does not assume an engineering or CI/CD operations background. Files, scripts, and GitHub Actions stay in Maintenance mode. This page mirrors the <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template#readme" target="_blank" rel="noreferrer">repository README</a> and stays synchronized across both languages.

<p class="template-version"><strong>Template release:</strong> v0.15.3<!-- x-release-please-version --></p>

| Item | Current state |
| --- | --- |
| Supported languages | Python, Rust, and TypeScript (select independently; select none for the shared workflow only) |
| repo-site template version | [[site_template_version]] |
| repo-site render engine version | [[site_engine_version]] |

**Current state:** Milestone 13 is extending the repo site and adoption experience. Only reviewed workflows under `.github/workflows/` run today; the rest stay archived. See the CI/CD settings appendix for the per-stage status.

| Choice | Production capability available today |
| --- | --- |
| Programming languages | Select Python, Rust, and TypeScript independently; select none for the shared workflow only |
| Branch approach | One development branch per delivery batch, all changes directly into `main`, or one shared `dev` branch |
| Template settings | Creation or adoption writes choices to `.csarc/config.yml`; template updates maintain this single repository configuration |
| Shared capability | Work-item (Issue) and change-proposal (PR) forms, AI working rules, automated checks, dependency safety, version records, and template updates |

{{< disclosure key="capability-boundary" title="Adoption paths and current scope" >}}
- **New repository:** choose a project type and branch approach; split only larger outcomes into independently verifiable sub-items.
- **Existing repository:** the template detects current languages and creates `.csarc/config.yml`, then previews the adoption diff while preserving product content.
- **Repository already using the template:** change options or upgrade through `csarc update`; the template updates the configuration and managed files together.
- **Prerequisites:** Git, GitHub CLI, and uv; Rust needs rustup, while TypeScript needs Node 24+ and pnpm 11. Local verification needs no token.

The template promises only capabilities that are implemented and tested. Go, generic deployment, monitoring, AI knowledge retrieval, and hosted documentation remain future or optional work.
{{< /disclosure >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="install" parity="supplemental" eyebrow="Install guide" title="Paste one prompt to your agent; it figures out what happens next" subtitle="`csarc status` reads `.csarc/config.yml`, the Copier revision, and policies/ drift; the result never depends on agent judgment." class="dense" legacy="false" >}}
Whether the repository is brand new, an existing one, or already CSARC-managed, the way you find out is the same: you do not need to remember a command yourself -- paste the text below straight to your coding agent (Claude Code, Copilot, and the like) and let it run and judge for you.

{{< standard key="install-mode-standard" title="The prompt to paste to your agent" >}}
<div class="step-flow"><article class="step-flow-item"><span class="step-flow-number">1</span><h3>Paste it</h3><p>Paste the full prompt below to your coding agent -- no command to remember.</p></article><article class="step-flow-item"><span class="step-flow-number">2</span><h3>CLI decides</h3><p>The agent runs <code>csarc status</code>; the CLI itself (not the agent's own judgment) classifies create, adopt, update, or a policy-only change.</p></article><article class="step-flow-item"><span class="step-flow-number">3</span><h3>Preview first</h3><p>Whatever the result, the agent shows you the plan and waits for confirmation before doing anything.</p></article></div>

The result will be one of: **create** a new project, **adopt** an existing one, apply an available **update**, find it **already current** with nothing to do, or apply **policy-only** settings -- whichever it is, the agent always shows you the plan before touching anything.

<p class="install-promise"><strong>The promise at this step:</strong> this step only checks the current state and proposes a plan; nothing is modified, no GitHub setting changes, and no PR opens until you confirm.</p>

<div class="command-block"><div class="command-block-head"><span class="command-block-label">The full prompt to paste to your agent</span><button class="copy-command" type="button">Copy prompt</button></div><pre class="command-block-text">Using uv. First, find the latest published GitHub Release of https://github.com/Innoguard-Cyber-Arch/csarc-repo-template (for example, run `gh release view --repo Innoguard-Cyber-Arch/csarc-repo-template --json tagName,targetCommitish`, or check that repository's Releases page), and note that release's tag and full commit SHA -- always use this verified release, never `main` or an unconfirmed branch. Using that SHA, run the official csarc CLI's `status` subcommand to determine which installation state the current workspace/existing Git repository is in; uv should manage an isolated Python 3.14 per invocation, requiring no global Python. Run `csarc status --json` first -- do not judge or assume the current state yourself. Based on the returned state and next_command: for create, adopt, or update, switch to the matching init/adopt/update dry-run prompt and wait for confirmation; for current, report that no action is needed; for policy-only-update, only run `scripts/apply-repository-settings.sh plan`, summarize the diff, and wait for confirmation before running `apply` -- do not redo a full adopt or update. Never modify the global environment, push, or open a PR throughout.</pre></div>

The classification logic all lives in the CLI, so a different agent running it gets the same answer; the other three situation prompts (create/adopt/update) live in the [repository README](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template#readme).
{{< /standard >}}

{{< ops key="install-mode-ops" title="The exact detection rule and command for each state" >}}
Prefer to run the command yourself instead of going through an agent:

```bash
csarc status <path> --json
```

It only reads local files plus, once a repository is already managed, the resolved template release and live GitHub settings; it never writes anything. Running it again against unchanged repository state always returns the same answer.

| State (`state`) | How it is detected | Next step |
| --- | --- | --- |
| `create` (new repository) | The target path does not exist, or exists but is an empty directory | `csarc init <path>`: preview with `--dry-run`, then confirm with `--yes --non-interactive` |
| `adopt` (existing repository) | The target already has content but no `.csarc/config.yml` | `csarc adopt <path>`: write a dry-run plan, review it, then apply with `--apply-plan` |
| `update` (update available) | `.csarc/config.yml` exists and its pinned Copier revision is behind the resolved target release | `csarc update <path> --check` to preview, then `csarc update <path>` |
| `current` (nothing to do) | The Copier revision is current, and `policies/` matches the repository's live GitHub settings | No action needed |
| `policy-only-update` (policy settings changed) | The Copier revision is current, but `policies/` (for example, whether workarounds are allowed) no longer matches the live GitHub settings | `scripts/apply-repository-settings.sh plan` to preview, then `apply`; this **skips** a full adopt or update run |

{{< disclosure key="install-policy-only" title="Why a policy-only change skips a full readopt" >}}
Policy settings (branch protection, required checks, labels, CODEOWNER rules) live in `policies/*.json` and are applied to GitHub directly by `scripts/apply-repository-settings.sh`; they are separate from the Copier template files. Changing a policy never touches a template file and never moves the pinned Copier revision. When `csarc status` detects that the revision is unchanged but `apply-repository-settings.sh check` reports drift, it returns `policy-only-update` and points straight at the existing, standalone `plan`/`apply` flow instead of suggesting a full adopt or update.

If `apply-repository-settings.sh check` itself cannot run (for example, `gh` is not authenticated or there is no network), `csarc status` does not assume policy drift. It falls back to `current` and marks `policy_check.available` as `false`, leaving the confirmation to a human.
{{< /disclosure >}}

{{< disclosure key="install-agent" title="Where the agent install contract lives" >}}
The full machine-readable contract lives in [`docs/agent-install.md`](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/agent-install.md): an agent always runs `csarc status` first and follows the row matching its returned `state`, instead of guessing which situation applies. All of the classification logic lives in the CLI (`detect_install_state`); the agent only calls it and acts on the result, so the same repository state never produces a different answer just because a different agent ran it.
{{< /disclosure >}}

{{< disclosure key="advanced-install-capabilities" title="Know what this specific repository can actually enable" >}}
The Governance step's plan table (Step 08) answers "what does the account's GitHub *plan* allow." That is necessary but not sufficient: organization policy, CODEOWNERS team membership, and token scope can still block a capability on a plan that would otherwise support it. Beyond that plan probing, `policies/capability-matrix.json` names every capability this template relies on, its minimum requirement, and a documented workaround; `scripts/check-repo-capabilities` evaluates it against what this repository and token actually have, live:

```bash
./scripts/check-repo-capabilities        # human-readable report
./scripts/check-repo-capabilities --json # machine-readable capabilities + summary
```

| Capability | What it enables | Minimum requirement | If missing |
| --- | --- | --- | --- |
| `repository_admin` | Prerequisite for every row below | `permissions.admin == true` for the acting token | Ask an owner/admin to run `apply`, or request the Admin role |
| `ruleset_enforcement` | Branch protection Ruleset on the default branch | Public repository (any plan), or private on Pro/Team or above | DEGRADED marker; desired Ruleset stays declarative in `policies/rulesets.json` |
| `codeowners_enforcement` | CODEOWNERS review actually blocks merge | Ruleset above, plus a `@org/team` with write access | DEGRADED marker; fix the team, or use `scripts/request-reviewer` meanwhile |
| `actions_pr_approval` | Actions can auto-approve pull requests (for example Dependabot auto-merge) | Organization allows `can_approve_pull_request_reviews` | DEGRADED marker; fall back to manual human approval |
| `security_and_analysis` | Secret scanning, push protection, Dependabot security updates | Public repository, or GitHub Advanced Security if private | DEGRADED marker; rely on local `scripts/scan-secrets` instead |
| `github_pages` | Hosts `docs/index.html` as a live site | Public repository, or GitHub Enterprise Cloud if private | DEGRADED marker; distribute the committed HTML file instead |
| `repository_settings_inspection` | `check` mode can compare live admin-only fields | Same as `repository_admin` | DEGRADED marker; run `check` from a trusted admin checkout |
| `immutable_releases` | Required before hosted Automatic/Guided publish can run | A real admin identity, never the default `GITHUB_TOKEN` | Known permanent limitation (#123/#626); run `scripts/publish-release` locally |
{{< /disclosure >}}

{{< disclosure key="advanced-install-results" title="How to read a check-repo-capabilities result" >}}
Every row reports one of three states: `allowed` (usable now), `blocked` (a real, currently-missing requirement), or `unknown` (cannot be proven from a read-only probe alone -- for example, an Actions setting that is off might just be unset rather than organization-blocked). This is a diagnostic preflight, not a merge gate: it always exits `0` once the report is produced, and it never mutates GitHub. Whether live settings actually *match* declared policy remains `apply-repository-settings.sh check`'s job.

`--facts <file>` reads pre-built facts instead of calling `gh`, so the same matrix can be evaluated against a hypothetical permission combination without live access -- this is also how `scripts/test-check-repo-capabilities` proves the gap list for several permission/plan combinations without any network access.
{{< /disclosure >}}

{{< disclosure key="advanced-install-workarounds" title="Workarounds and the existing DEGRADED marker" >}}
This matrix does not replace or redesign `apply-repository-settings.sh`'s DEGRADED mechanism -- it documents it. Every row whose workaround says "DEGRADED marker" reuses the exact same fail-safe already printed by `apply-repository-settings.sh check`/`plan`/`apply` for that limitation; the two never disagree because the underlying detection (plan, visibility, admin permission) is the same. `docs/ci-policy.md` and [the capability-aware governance ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/capability-aware-governance.md) record the durable decision; this page and `policies/capability-matrix.json` are what stay current as the single source both consult.
{{< /disclosure >}}
{{< /ops >}}
{{< /slide >}}

{{< slide key="about" track="about" eyebrow="About" title="CSARC is an updatable governance baseline that keeps working alongside your repo" subtitle="Not a template that stops once it generates files; creating, adopting, and upgrading all preview the diff before anything applies." class="dense single-column" legacy="false" >}}
{{< standard key="about-mode-standard" title="What CSARC actually keeps doing" >}}
Most templates are done the moment they generate files. CSARC keeps working alongside your repo, through a full lifecycle:

<div class="capability-map"><div class="capability-node"><h3>1｜Preview the diff before you touch anything</h3><p>Whether you're creating a new repo or adopting an existing one, a preview is built on the side first, listing what would be added, kept, or needs your own judgment; you apply it only after reviewing, never as a silent overwrite.</p><span class="capability-pointer">See "Install guide" and "Template updates"</span></div><div class="capability-node"><h3>2｜Day-to-day changes follow rules and get verified</h3><p>Each piece of work starts as an Issue stating what to do and what "done" means; the change happens on its own branch, gets checked locally first, then GitHub checks the proof of that, while routine package and known-vulnerability checks run automatically on their own schedule.</p><span class="capability-pointer">See "Work", "Verify / CI", and "Supply chain"</span></div><div class="capability-node"><h3>3｜Merging leaves evidence behind</h3><p>A PR merges only after human review; when needed, a version and Release are created that record exactly which packages shipped, so "what actually happened" can always be checked later.</p><span class="capability-pointer">See "PR merge" and "Version / delivery"</span></div><div class="capability-node"><h3>4｜Future template updates still preview first</h3><p>A template update works the same way adoption does: it produces a reviewable diff first, and you confirm before it applies. This site itself is built on the same principle -- download <code>docs/index.html</code> and it opens offline.</p><span class="capability-pointer">See "Template updates" and "Repo-site"</span></div></div>

This rhythm fits you if: you already have a GitHub repository that cannot risk being overwritten wholesale; you want coding agents in day-to-day development with clear rule boundaries; or you want several projects to share one workflow. If you just want to scaffold an empty project quickly with no ongoing maintenance, a lighter template probably fits better.
{{< /standard >}}

{{< ops key="about-mode-ops" title="The thinking behind the governance baseline" >}}
CSARC is not just a file generator: creating a new project, adopting an existing one, and rolling out later policy updates all go through a process that previews, verifies, and stays traceable -- what it delivers is a verifiable way of working, not just files.

<div class="capability-map"><div class="capability-node"><h3>Adopting an existing repository safely</h3><p>Builds a full candidate in isolation and verifies it first; reconfirms no drift before applying; stops on conflict or failure without touching the target repo.</p></div><div class="capability-node"><h3>Rolling out governance policy continuously</h3><p>Keeps repository choices, the template revision, GitHub's desired policy, and the platform's actual state separate; a fixable gap is called out, an unsupported capability is labeled <code>DEGRADED</code>.</p></div><div class="capability-node"><h3>Keeping an evidence chain you can check</h3><p>Issue -&gt; PR -&gt; verification -&gt; delivery candidate -&gt; merge -&gt; release -&gt; checksum/SBOM -&gt; audit trail, each step pointing back to the exact version before it.</p></div></div>

{{< disclosure key="about-three-layers" title="Three layers: why a written policy doesn't always mean an enforced one" >}}
CSARC splits "governance" into three layers that can drift out of sync with each other, so no single layer alone proves a control is actually in effect:

1. **Template source:** `template/`, `policies/`, and `profiles/catalog.yaml` -- the shared definitions the template team maintains, describing what "should" be provided.
2. **The repo-local contract:** `.csarc/config.yml`, `policies/*.json`, and `AGENTS.md` left in this repository after generation or adoption -- what this repository chose from the template, and what it expects.
3. **What actually takes effect on GitHub:** branch protection, Rulesets, Actions permissions, and the GitHub plan's own limits -- what the platform is really enforcing right now.

A template update only touches layer 1; applying it to a repository only touches layer 2; and whether the policy written into layer 2 actually takes effect still depends on whether layer 3 -- the GitHub plan and permissions -- can support it. `apply-repository-settings.sh`'s `plan`/`apply`/`check` exist precisely to reconcile layer 2 against layer 3: when they agree, it applies and `check` verifies it; when the platform genuinely cannot support it, the result is marked `DEGRADED` and handed back to a person, never pretended as enforced.
{{< /disclosure >}}

{{< disclosure key="about-design-philosophy" title="Why it is designed this way: people/agent split, repo-local, who this fits" >}}
### Designed for people and coding agents together

CSARC gives agents a friendly way in, but never lets an agent guess at repository state or governance policy on its own. An agent's job is to help operate the system and explain it; the actual judgment lives in deterministic, testable CLI commands, scripts, and policies that anyone can rerun locally. Requirement trade-offs, irreversible actions, external impact, and merge authorization all stay with a human.

### Repo-local, not another platform to run

CSARC does not require standing up a developer portal, a long-lived PAT, an extra GitHub App, or a dedicated hosted service first. Policy, verification, documentation, and decision evidence all stay inside the repository, where they go through PR review, version control, and can be read offline. It does not replace Backstage, Minder, or a language's own native tooling -- it composes Copier, GitHub, uv, Cargo, pnpm, OSV, Syft, and Release Please into one repository lifecycle with clear ownership and clear failure boundaries.

### Who this fits

A good fit if you: already have a GitHub repository that cannot risk a template overwriting it; are starting to let coding agents into day-to-day development; want several repositories to share one governance baseline; care about supply-chain evidence, change history, and auditability; do not yet need, or cannot yet staff, a central platform. If you just want to scaffold an empty project quickly with no ongoing governance, a lighter project template probably fits better.
{{< /disclosure >}}

{{< disclosure key="about-beliefs" title="What we choose to believe" >}}
- Build and verify a candidate before writing anything.
- Product content always has a clear owner.
- A capability that cannot be proven is never claimed as working.
- Be honest about degrading when the platform cannot support something.
- Automation owns the repetitive judgment calls; people own the important decisions.
- Documentation is navigation -- specs, ADRs, GitHub history, and tests are what actually constitute durable project memory.
{{< /disclosure >}}
{{< /ops >}}
{{< /slide >}}

{{< slide key="flow" track="flow" eyebrow="CI/CD flow" title="The template guides every change" subtitle="Follow the Issue and PR prompts; the template prepares the right settings and tells you what needs attention." class="legacy-slide pipeline-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>The template carries every change<span class="accent"> to the right place</span></h2>
        <p class="subtitle"><strong>CI/CD here means:</strong> once a change is submitted, a separate clean environment re-checks it before deciding whether it can merge or ship -- it does not mean automatic deployment to production.</p>
        <p class="subtitle">For example: the team is adding a sign-in-timeout reminder to the product -- the five steps below all use this example.</p>
      </header>
      <div class="pipeline-map">
        <div class="pipeline-track" aria-label="Everyday development and delivery flow">
          <article class="pipeline-stage">
            <span class="pipeline-phase">Step 1｜State it clearly</span>
            <h3>Open the work</h3>
            <p><strong>Person:</strong> writes an Issue (a work item) -- "Add a sign-in-timeout reminder" -- with the completion condition that a reminder shows before timeout, backed by a test. <strong>Template:</strong> the form prompts for the required fields. <strong>Result:</strong> one clearly scoped, independently verifiable piece of work.</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">Step 2｜Make the change</span>
            <h3>Complete the change</h3>
            <p><strong>Person/AI:</strong> changes the code following in-repo guidance, running the most relevant local check first. <strong>Template:</strong> prepares that guidance and the check scripts. <strong>Result:</strong> a self-checked change ready to send for review.</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">Step 3｜Hand it to the team</span>
            <h3>Open a PR</h3>
            <p><strong>Person:</strong> opens a PR (a change proposal) linked back to the original Issue. <strong>Template:</strong> the template prompts for what changed and how it was verified. <strong>Result:</strong> a proposal a reviewer can understand quickly.</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">Step 4｜The system helps</span>
            <h3>Verify and check dependencies</h3>
            <p><strong>GitHub:</strong> checks that the local verification proof is fresh and covers a sufficient tier, without re-executing the checks themselves; a dependency change also gets checked against known vulnerabilities on its own hosted schedule. <strong>Template:</strong> selects the verification the change actually needs. <strong>Result:</strong> the verdict comes from that same local script every time, not just the author's own "looks fine to me" -- CI is checking the proof that script just produced.</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">Step 5｜Confirm the result</span>
            <h3>Review and merge</h3>
            <p><strong>Person:</strong> approves the merge once both the result and the review are clear. <strong>GitHub:</strong> enforces merge protection to whatever degree the plan supports. <strong>Result:</strong> the sign-in-timeout reminder lands in main, with a full record of this change.</p>
          </article>
        </div>
        <div class="pipeline-loop" aria-label="CI feedback loop">
          <strong>↺ A check fails → fix it on the same work branch → update the same PR → get a fresh result</strong>
          <span>A new problem found after merge gets its own, clearly scoped Issue, instead of reopening the branch that already merged.</span>
        </div>
        <div class="pipeline-foundation" aria-label="Platform capability underneath the whole flow">
          <div class="pipeline-foundation-label"><strong>The template prepares this first</strong><span>Most users just follow the prompts; only a maintainer adjusts settings.</span></div>
          <article class="pipeline-foundation-card"><h3>Work format</h3><p>Issue and PR forms prompt for the necessary content.</p></article>
          <article class="pipeline-foundation-card"><h3>Verification and security rules</h3><p>Selects the necessary checks by change content and flags dependency risk.</p></article>
          <article class="pipeline-foundation-card"><h3>Merge settings</h3><p>Applies the protection the GitHub plan actually supports.</p></article>
          <article class="pipeline-foundation-card best"><h3>Version and release</h3><p>The flow is configured as a candidate; it counts as active only after a successful default-branch run.</p></article>
        </div>
      </div>
{{< /legacy >}}

{{< basic >}}
| What you are doing | How the template guides you |
| --- | --- |
| Create the work | The Issue form prompts for the problem, completion conditions, and necessary context |
| Make the change | Repository guidance tells people and agents how to work and which local check to run first |
| Open a PR | The PR template prompts for the linked Issue, completed result, and verification evidence |
| Read verification and dependency results | The template selects the necessary checks; package changes also prove that the saved version list still installs |
| Review and merge | Merge into the correct branch after the result and human review are clear |

Users do not need to memorize workflow or script names. Current automation covers work items, PR rules, necessary verification, and a reviewed automatic version-and-release path.

**Responsibility handoff (local scripts → GitHub Actions → PR gate → Release):**

- **Local scripts (`Active`):** `scripts/verify-fast` / `scripts/verify-template.sh` run once locally by the developer first, catching most low-level mistakes.
- **GitHub Actions (`Active`):** once a PR opens, `.github/workflows/` only checks that the `Verified-locally:` proof left by that local run is fresh and covers a sufficient tier (Issue #661) -- it never re-executes that local policy, but it does not trust blindly either: a stale or missing proof still fails the check.
- **PR gate (depends on the GitHub plan):** where supported, a Ruleset / branch protection blocks a merge that failed checks or lacks review; where not supported, it is marked `DEGRADED` and falls back to human discipline (see "Rules governance").
- **Release (`Active`, but needs a human trigger):** version and release evidence is produced by someone with admin permission running `scripts/publish-release` locally; the hosted Automatic/Guided publish path is a known limitation, not the default path (see "Version / delivery").

{{< detail key="flow-foundation" title="Three foundations across the whole flow" >}}
- **08 Governance:** prepares repository policy, then applies only the controls the live GitHub plan supports.
- **09 Template updates:** Copier carries policy changes back through reviewable PRs.
- **10 Repo-site:** keeps practices, limits, evidence, and decisions discoverable.

A failed check is fixed in the same PR. A new problem found after merge becomes a separate, bounded Issue.
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="files" track="files" class="dense" eyebrow="File map" title="The template puts required settings in the right place" subtitle="This lists the major files currently generated; template updates never silently overwrite product-owned content." legacy="false" >}}
{{< standard key="files-mode-standard" title="Update flow and integrated tools" >}}
Where a file lives matters less than who can change it. Every file falls into one of three ownership categories: **template-led** (a template update may change it; avoid editing it directly after generation), **shared** (you can edit it directly, but the next template update may ask you to merge in a diff), or **project-owned** (entirely yours -- the template never overwrites it).

<div class="capability-map"><div class="capability-node"><h3>Template settings <span class="ownership-tag shared">Shared</span></h3><p><code>.csarc/config.yml</code>, <code>policies/</code>: languages, branch strategy, owners, and reviewers all live here.</p></div><div class="capability-node"><h3>GitHub workflow <span class="ownership-tag template">Template-led</span></h3><p><code>.github/</code>: Issue/PR forms and automated checks.</p></div><div class="capability-node"><h3>Agent rules <span class="ownership-tag shared">Shared</span></h3><p><code>AGENTS.md</code>: how an agent works in this repository.</p></div><div class="capability-node"><h3>Project docs <span class="ownership-tag shared">Shared</span></h3><p><code>README.md</code>, <code>docs/</code>, <code>site/</code>: docs for people, and the site you're reading right now.</p></div><div class="capability-node"><h3>Product code <span class="ownership-tag project">Project-owned</span></h3><p><code>src/</code>: the actual product code, tests, and specs.</p></div></div>

Switch to Maintenance mode for the full file tree and each file's owner.

When the template finds a file it can update, it first builds a candidate in an isolated environment on the side, without touching this repo, then compares files one by one:

<div class="plan-grid">
  <article class="plan-card current"><h3>Update the worktree when there's no conflict</h3><p>The update applies directly, no action needed.</p></article>
  <article class="plan-card team"><h3>Keep your content when there's a conflict</h3><p>Only the affected files are listed; your content stays untouched.</p></article>
  <article class="plan-card enterprise"><h3>Always reviewed by PR before reaching the real branch</h3><p>Either way, a person reviews and merges it; nothing silently overwrites your content.</p></article>
</div>

The template already wires up the tools you'd otherwise have to find and configure yourself: project generation and updates, code security scanning, dependency-update reminders, known-vulnerability scanning, release notes, and the repo site you're reading right now.
{{< /standard >}}

{{< ops key="files-mode-ops" title="Technical detail on the update mechanism and tools" >}}
{{< file-map >}}

{{< disclosure key="files-map-scope" title="Why the file map only lists path, purpose, and responsibility" >}}
The side navigation already links each item to its page, and the maintainer-only "CI/CD settings" appendix already lists verification entry points per step in more detail than this view could add; the tree view therefore avoids duplicating a page-name or verification-entry column.

The "responsibility" column is also editing guidance: avoid editing a `Template-led` file directly in a generated repo -- route the change through Template updates instead; a `Shared` file is a reasonable place to edit directly, but the next template update may ask you to merge in a diff; a `Project-owned` file is entirely yours, and the template never touches it.
{{< /disclosure >}}

{{< disclosure key="files-update" title="How updates protect product content" >}}
Copier attempts updates on a short branch. A conflict only lists the affected files and leaves the repository unchanged; adjust them, rerun, and then review the PR. Fixtures cover new project generation, existing-repository adoption, and a later update of the same repository. They add product-owned files and prove that an update does not overwrite them.

Workflows, policies, scripts, and documents shared by root and `template/` are kept in sync. Files that differ because of project choices are verified by generating a real project. New repositories receive the release Action; adopted repositories keep their product-owned workflow.
{{< /disclosure >}}

{{< disclosure key="files-tools" title="Tools actually used" >}}
Only tools this template directly integrates, executes, or produces into the repository. External alternatives stay on the Similar tools comparison; language toolchains (`uv`, `ty`, `pnpm`, `rustfmt`, `Clippy`, `Cargo`) stay on the Languages slide. Current versions live in `uv.lock`, the pinned Action SHA, or the install script named below; this table never restates them.

| Tool | Purpose | Where it appears | Scope | License |
| --- | --- | --- | --- | --- |
| [Copier](https://github.com/copier-org/copier) | Generates, adopts, and updates repositories from this template | `copier.yml`, `template/`, `.csarc/config.yml` | Every repository created from or adopting this template | [MIT](https://github.com/copier-org/copier/blob/master/LICENSE) |
| [zizmor](https://github.com/zizmorcore/zizmor) | Static security audit of GitHub Actions workflows | `pyproject.toml`, `scripts/verify-stage-github-actions-audit` | Local verification only (`github-actions-audit` stage); the hosted `verify` job validates a local-attestation trailer instead of re-running it | [MIT](https://github.com/zizmorcore/zizmor/blob/main/LICENSE) |
| [Dependabot](https://github.com/dependabot/dependabot-core) | Opens dependency-update pull requests | `.github/dependabot.yml` | Root and template package ecosystems | [MIT](https://github.com/dependabot/dependabot-core/blob/main/LICENSE) |
| [OSV-Scanner](https://github.com/google/osv-scanner) | Scans lockfiles for disclosed vulnerabilities | `scripts/verify-dependencies`, `scripts/install-osv-scanner`, `.github/workflows/osv.yml` | Dependency-change PRs, delivery candidates, weekly schedule | [Apache-2.0](https://github.com/google/osv-scanner/blob/main/LICENSE) |
| [Syft](https://github.com/anchore/syft) | Generates the release SPDX SBOM | `.github/workflows/release.yml` (`anchore/sbom-action`), `scripts/release_assets.py` | Delivery PR that creates a release | [Apache-2.0](https://github.com/anchore/syft/blob/main/LICENSE) |
| [Release Please](https://github.com/googleapis/release-please) | Maintains the version/changelog pull request and creates the GitHub Release | `.github/workflows/release.yml`, `release-please-config.json`, `.release-please-manifest.json` | Delivery branch to `main` | [Apache-2.0](https://github.com/googleapis/release-please/blob/main/LICENSE) |
| repo-site render engine | In-house, dependency-free Python engine that builds the bilingual repo-site and `llms.txt` from Markdown; replaced Hugo on 2026-09-03 | `scripts/build_repo_site.py`, `scripts/build-repo-site`, `scripts/render_site.py`, `site/version.json` | `docs/index.html`, `docs/index.en.html`, `llms.txt` | In-house (this repository) |
{{< /disclosure >}}
{{< /ops >}}
{{< /slide >}}

{{< slide key="method" track="method" eyebrow="Step 01" title="Define the work before implementation" subtitle="Turn a request into an actionable Issue; create a Milestone only when several work items must move together." class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>Step 1｜<span class="accent">Turn a request into work that is ready to start</span></h2>
        <p class="subtitle"><strong>Baseline.</strong> One Issue defines one change that can be completed independently; only use a Milestone when several work items share an outcome and deadline.</p>
      </header>
      <p class="context-line"><strong>What the template does｜</strong>keeps Issue and Milestone content consistent, so a person or an agent knows what to solve and what "done" means before starting.</p>
      <p class="context-line"><strong>For example｜</strong>Issue: add a sign-in-timeout reminder / completion condition: a reminder shows before timeout, backed by a test; the work branch matches this Issue; the PR delivers only this one change.</p>
      <div class="relation-map"><div class="relation-track"><div class="relation-col"><div class="relation-group"><span class="relation-group-label">Only when needed</span><strong>Milestone</strong><span class="relation-group-note">Only put multiple Issues into the same Milestone when they need a shared deadline or shared acceptance</span></div><span class="relation-group-arrow" aria-hidden="true">↓</span><article class="relation-node"><span class="relation-kind">State it clearly</span><h3>Issue</h3><p>Problem, completion criteria, verification, and owner; add no other document once that is enough to start.</p></article></div><article class="relation-node"><span class="relation-kind">Start implementing</span><h3>Work branch</h3><p>One short-lived branch per Issue; do not mix unrelated work into it.</p></article><article class="relation-node"><span class="relation-kind">Review, then merge</span><h3>PR</h3><p>Matches the same Issue; merges to main only after checks and human review pass.</p></article></div></div>
      <p class="context-line"><strong>Next step｜</strong>open an Issue and cut a work branch to start implementing; naming rules, Milestone detail, Issue splitting, and exceptions are covered in Maintenance mode.</p>
{{< /legacy >}}

{{< basic >}}
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

{{< disclosure key="method-alternatives" title="Other common approaches" >}}
- **Start first, document when needed:** finish small, clear work directly; add a plan only for work that spans sessions, has dependencies, or carries higher risk.
- **Specification first:** clarify requirements, design, and task breakdown before development begins.
- **Change proposal:** review a proposed change separately, then merge it into the official specification after acceptance.
- **Complexity-based workflow:** use a short path for small work and add discovery, design, roles, and review only for larger work.
{{< /disclosure >}}

{{< config-guidance track="method" >}}
<p class="method-reference reference">Ref. <a href="https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues" target="_blank" rel="noreferrer">GitHub sub-issues</a>.</p>
{{< /basic >}}
{{< /slide >}}

{{< slide key="agents" track="agents" eyebrow="Step 02" title="Define AI rules before implementation" subtitle="An Issue says what this change is; AGENTS.md says how an agent works in the repository." class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>Step 2｜<span class="accent">Define AI rules before implementation</span></h2>
        <p class="subtitle"><strong>Baseline.</strong> An Issue bounds the work; <code>AGENTS.md</code> explains how to work; code and tests provide evidence, and people retain product direction and material-risk decisions.</p>
      </header>
      <p class="context-line"><strong>What the template does｜</strong>generates and checks what an agent must read before starting, where it may change files, how to isolate parallel work, and what evidence to leave; only custom policy, material decisions, and exceptions need a person.</p>
      <div class="capability-map cols-3"><div class="capability-node"><h3>Issue: this time's scope</h3><p>States what to complete this time and what "done" means; scope and progress live here, while material decisions live in an approved spec/ADR (a written record of the requirement and the architecture decision behind it).</p></div><div class="capability-node"><h3>AGENTS.md: how to work in this repo</h3><p>The working rulebook that travels with the repository under version control; an agent reads it before starting anything, instead of guessing at convention.</p></div><div class="capability-node"><h3>Evidence and decisions</h3><p>scripts/tests provide verification evidence anyone can rerun; requirement direction, material trade-offs, and irreversible operations still stay with a person.</p></div></div>
      <p class="context-line"><strong>Next step｜</strong>point your agent at <code>AGENTS.md</code> and let it start working; change isolation, verification evidence, and template-update rules are covered in Maintenance mode.</p>
{{< /legacy >}}

{{< basic >}}
### Our choice

- **Automated by default:** the template generates and checks the AI rules; only custom policy, material decisions, and exceptions need a person.
- **Work and context:** GitHub Issues and PRs record work; approved specs and ADRs retain long-lived decisions, and a plan is added only when needed.
- **AI rules:** the root `AGENTS.md`; `CLAUDE.md` is only a thin import.
- **Change isolation:** each writable task uses its own branch and worktree; read-only work does not.
- **Verification evidence:** a local program is the only logic; an Action only calls it.
- **Decisions and authorization:** people keep material decisions; review and merge rules are defined only by Rules governance.
- **Template creation and updates:** Copier owns the shared baseline; an existing repository's updates are defined by Template upgrades.

{{< disclosure key="agents-priority-and-isolation" title="Rule priority and change isolation" >}}
- **Rule priority:** the root `AGENTS.md` governs the whole repository; add a nearer `AGENTS.md` in a subtree only when its commands or safety boundaries genuinely differ, in which case the nearer rule wins inside that subtree while everything else still falls back to the root. `CLAUDE.md` always just thinly imports the root `AGENTS.md` and never redefines rules of its own.
- **Change isolation:** each writable task uses its own Git branch and worktree, so parallel work never interferes; read-only work (for example, just looking something up) needs neither a branch nor a worktree.
{{< /disclosure >}}

{{< disclosure key="agents-alternatives" title="Other common approaches" >}}
- **In-repo guidance:** keep fixed commands and boundaries under version control so different agents read the same rules.
- **Spec-artifact relay:** produce a spec, plan, and tasks for large work first, then hand each step to an agent in turn.
- **Roles and orchestration:** use dedicated roles, skills, or queues to coordinate multiple agents; fits once the workload already needs extra coordination.
- **Human checkpoints:** pause for a decision before requirements, material trade-offs, external impact, and irreversible operations.
{{< /disclosure >}}

`README.md` serves people, `AGENTS.md` serves every agent, and `template/AGENTS.md.jinja` plus `copier.yml` emit only commands the selected profile can run. `scripts/cleanup-worktrees` and `scripts/test-worktree-cleanup` handle safe cleanup; `scripts/verify`, `.github/workflows/`, and `policies/` keep rules, evidence, automation, and governance separate.

{{< config-guidance track="agents" >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="contract" track="contract" eyebrow="Step 03" title="Verify locally first; CI only checks the proof" subtitle="Issue PRs are tiered by change scope; full verification is reserved for high-risk boundaries." legacy="false"  class="candidate-slide" >}}
{{< standard key="contract-mode-standard" title="Change size decides how heavy verification gets" >}}
Developers first run the tier-appropriate verification on their own machine; a successful run writes a "verified" attestation locally. Once a PR opens, GitHub only checks that this attestation is fresh and covers a sufficient tier against the same policy -- it never re-executes the checks themselves. Locally you only run the check that proves this change, no need to wait for the full pipeline. Once the PR is open, the system automatically decides which tier applies based on the change's scope:

<div class="plan-grid">
  <article class="plan-card current"><h3>docs</h3><p>Docs-only changes get the lightest check. Example: editing a single explainer document.</p></article>
  <article class="plan-card team"><h3>fast</h3><p>Ordinary changes default to this tier. Example: a routine code or config change.</p></article>
  <article class="plan-card enterprise"><h3>full</h3><p>Milestone delivery, a hotfix, or unpinnable risk. Example: Milestone/canary delivery, a hotfix, a merge queue.</p></article>
</div>

The same logic runs locally and in CI, so there is never a second, drifting copy of the rule.
{{< /standard >}}

{{< ops key="contract-mode-ops" title="The tiering rule and today's automation status" >}}
- **During development:** run only the focused check that proves the current change (for example `uv run pytest <path>` or `uv run ruff check <path>`), using fresh output before claiming completion, without waiting on the full pipeline.
- **Work PR (topic branch → main or `dev/m*`):** `scripts/ci_tier.py` classifies the change as `docs`, `fast`, or `full` from the event, base/head, labels, and changed paths. A pure documentation or site change lands on `docs` (an early-exit case of `fast`); an ordinary change lands on `fast`; any path the classifier cannot confidently place escalates, fail-closed, to `full`.
- **When full verification is needed:** only for a Milestone or canary delivery, an urgent fix, a merge queue, a manual dispatch, or an unknown high-risk path the system cannot safely narrow.
- **One implementation, nothing reruns on the hosted side (#661):** GitHub Actions has exactly one `verify` job with `contents: read` permission and a 15-minute timeout; a new commit on the same PR cancels the previous run. It never re-executes `scripts/verify-fast` / `scripts/verify-template.sh` (`scripts/verify` in a generated repository) -- it only validates the `Verified-locally:` trailer those scripts write onto the commit on a successful local run (tree hash, tier, and timestamp) for freshness and tier sufficiency. Skip the tier-appropriate local run before pushing, and this lightweight hosted job has nothing to validate -- it fails closed.
- **Repository scope:** an ordinary project verifies only its own change. The template repository's full verification also runs the `large`-marked Copier create / adopt / update regression tests, which actually generate a project and verify the components it preserves — not just check that files exist.

Verification logic lives only in repository scripts and tests; GitHub Actions only decides the event, the permissions, and which program to call, never a second copy of the logic.

{{< disclosure key="contract-root-state" title="Root repository state (2026-09-03)" >}}
<aside class="config-guidance" data-audience="maintainer"><p>Dependency vulnerability scanning (<code>osv.yml</code>) is still candidate on the template repository's own root: the workflow has landed on <code>main</code> and is registered active by GitHub, but its trigger set is only <code>schedule</code> (Mondays 03:17 UTC) and <code>workflow_dispatch</code> — no <code>pull_request</code> — so it cannot pre-register from a candidate branch, and no scheduled or dispatched run has fired yet, so it does not meet this page's (or <code>docs/ci-policy.md</code>'s) bar for live run evidence. A newly generated repository is active from its first commit, since Copier's first commit lands directly on that repository's own <code>main</code>.</p></aside>
{{< /disclosure >}}

{{< disclosure key="contract-automation" title="What automation is actually running today" >}}
The states below are checked line by line against `docs/ci-policy.md`'s "Current automation" table and a live query (2026-09-03), not carried forward from whatever this page said at build time:

- **Active:** CI (`ci.yml`), PR policy (`pr-policy.yml`), Work item lifecycle (`work-item-lifecycle.yml`, folding in Issue triage, Milestone sync, and Work Issue closure), Spec to Issue (`spec-to-issue.yml`), reviewer assignment (`governance-comment.yml`), and Dependabot (a native GitHub feature) are all registered with a recent successful live run.
- **A known limitation that is now fixed:** Work Issue closure used to check out `pull_request.base.sha`, so the `close-work` command — which only exists after the merge — could not be found and the run failed. #401 / PR #453 (merged 2026-09-02) switched it to `pull_request.merge_commit_sha`; a successful live run followed on 2026-09-03. Milestone lifecycle's approval/closure coverage (`tests/test_milestone_approval.py` / `tests/test_milestone_closure.py`) is also in this candidate; its tracking Issue #400 closed as completed on 2026-09-02.
- **Depends on which repository:** dependency vulnerability scanning (OSV) is active in a generated repository; it is still candidate on the template's own root, for the reason in the aside above.
- **Candidate, not re-verified here:** current Version/Release (`release.yml`) status lives in `docs/ci-policy.md`'s "Version, release, delivery, and deployment" matrix.
- **Not active:** dedicated promotion, release-handoff, registry-publisher, consumption, live-integration, and deployment workflows do not exist, and are not conditional options waiting to be wired in.
{{< /disclosure >}}

{{< disclosure key="contract-cost" title="What the three verification tiers actually cost" >}}
These numbers come from `docs/ci-policy.md`'s most recent measurement. They set cost expectations, not a permanent SLA — a rerun will report different numbers.

- `docs` and `fast` share one bounded path; `docs` is just `fast`'s early-exit case for a pure documentation or site change.
- `fast`: on 2026-09-01, with a warm cache on the same machine, a source-only scope took about 59 seconds and a scope also touching policy/template files took about 99 seconds; the full PR feedback window runs about 1-4 minutes (#428).
- `full`: 502 seconds (8m22s) with all seven stages PASSED on an exclusive machine; up to 810 seconds when another worktree's process runs concurrently — the difference is contention, not heavier verification content (#458, 2026-09-02). Of the seven stages, Regression tests (the full pytest run plus the `large`-marked Copier create/adopt/update matrix) is usually by far the longest; the other six stages together usually add up to well under a minute.
{{< /disclosure >}}

{{< config-guidance track="contract" >}}
{{< /ops >}}
{{< /slide >}}

{{< slide key="languages" track="languages" parity="new" eyebrow="Step 04" title="Choose a language and receive the matching checks" subtitle="Each language owns its tools and tests; shared rules run once." class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>Step 4｜<span class="accent">Each language manages itself</span></h2>
        <p class="subtitle"><strong>Baseline.</strong> Choose a project language and the template produces the matching version, lockfile, formatting, static checks, tests, and build configuration.</p>
      </header>
      <p class="context-line"><strong>What the template does｜</strong>you only select the languages this repo actually uses; the template wires up each language's native checks, while everything still flows through the same PR pipeline.</p>
      <p class="context-line"><strong>The shared pipeline｜</strong>select a language → generate its matching tooling and lockfile → run format/lint/test/package → hand the result to the same verification entry point (see "Verify / CI").</p>
      <div class="capability-map cols-3"><div class="capability-node"><h3>Python</h3><p>Checks formatting, types, tests, and the installable package.</p></div><div class="capability-node"><h3>Rust</h3><p>Checks formatting, common mistakes, tests, and whether the release build packages.</p></div><div class="capability-node"><h3>TypeScript</h3><p>Checks formatting, types, tests, and the installable package.</p></div></div>
      <p class="context-line"><strong>Next step｜</strong>just check the languages you need at creation or adoption; several at once combine checks and a shared item still runs once; other approaches are covered in Maintenance mode.</p>
{{< /legacy >}}

{{< basic >}}
### Our choice

Choose a project language and the template prepares the matching checks:

- **Every project:** checks work rules, documentation, secrets, and dependency safety.
- **Python:** checks formatting, types, tests, and the installable package.
- **Rust:** checks formatting, common mistakes, tests, the release build, and the installable package.
- **TypeScript:** checks formatting, types, tests, and the installable package.

Each language is its own independent component (module), selected independently. Selecting several languages combines their modules while each shared check still runs once; the documentation does not enumerate combinations. Version sources and lockfiles stay independent too: Python reads `pyproject.toml`/`uv.lock`, Rust reads `Cargo.toml`/`Cargo.lock`, and TypeScript reads `package.json`/`pnpm-lock.yaml`; after a change, just run the single verification entry point listed below under "Fixed baseline | One entry point verifies and packages."

### Other common approaches

- **A single cross-language tool:** one consistent entry point, but it needs its own abstraction layer to maintain.
- **Each language's native tools:** easy for developers to understand, but the template must unify versions and output itself.
- **A dedicated setup per combination:** intuitive at first, but duplication and drift grow with every added combination.

{{< config-guidance track="languages" >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="supply" track="supply" eyebrow="Step 05" title="Update, check, and record third-party packages separately" subtitle="Observe ordinary releases, act on known vulnerabilities immediately, and retain a traceable release inventory." class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>Step 5｜<span class="accent">Update, check, and record third-party packages separately</span></h2>
        <p class="subtitle"><strong>Baseline.</strong> Where a package updates from, whether it can be reinstalled, whether it has a known vulnerability, and what a release actually contains are four things worth confirming separately.</p>
      </header>
      <p class="context-line"><strong>For example｜</strong>when development adds or updates a third-party package, the template splits "can it be reinstalled," "is there an update," "is there a known vulnerability," and "what did the release actually install" into four separate, sequential steps:</p>
      <div class="capability-map"><div class="capability-node"><h3>1｜Lock what gets installed</h3><p>Reinstalls from the locked-version list (lockfile), so every run gets the same packages. <strong>You'll see:</strong> install/CI use the locked versions directly. <strong>Blocks merge?</strong> Yes, if the lockfile and the declared versions disagree.</p></div><div class="capability-node"><h3>2｜Dependabot opens an update PR</h3><p>The automated update service opens a PR weekly; ordinary releases wait a three-day observation window, security patches never do. <strong>You'll see:</strong> an update PR waiting for review. <strong>Blocks merge?</strong> Not automatically, but it still has to pass ordinary PR verification.</p></div><div class="capability-node"><h3>3｜OSV checks known vulnerabilities</h3><p>The known-vulnerability scan checks dependency changes and delivery candidates, without waiting for the observation window. <strong>You'll see:</strong> scan results attached to the PR or delivery candidate. <strong>Blocks merge?</strong> Yes, if a known vulnerability turns up.</p></div><div class="capability-node"><h3>4｜Release produces an SBOM</h3><p>At release time, lists the packages the artifact actually contains (a bill of materials), for later investigation. <strong>You'll see:</strong> the SBOM file attached to the Release. <strong>Blocks merge?</strong> No -- it's an inventory, not a gate.</p></div></div>
      <p class="context-line"><strong>Keep in mind｜</strong>a lockfile only guarantees the packages reinstall -- it says nothing about known vulnerabilities; a known security patch never waits out the three-day observation window; OSV only recognizes already-disclosed vulnerabilities, so it cannot guarantee catching every problem; and an SBOM is an inventory for investigation -- it does not, by itself, patch or block any vulnerability.</p>
      <p class="context-line"><strong>Next step｜</strong>a package update opens a PR on its own -- review and merge it when you see it; why each protection stays separate is covered in Maintenance mode.</p>
{{< /legacy >}}

{{< basic >}}
### Our choice

Routine updates and security checks run automatically. People step in only for upgrade conflicts, vulnerability response, and risk acceptance.

| Risk | What the template does today |
| --- | --- |
| A dependency change cannot be reproduced | PR verification reinstalls from the locked-version list (lockfile), so every run receives the same packages |
| A newly published malicious version | GitHub's automated update service (Dependabot) groups update PRs; ordinary releases wait three days, while security updates do not |
| A disclosed vulnerability goes unnoticed | The Open Source Vulnerabilities scan (OSV) checks dependency changes and delivery candidates; a weekly scan covers periods without PRs |
| Nobody knows what a release contains | A software bill of materials (SBOM) lists packages in the artifact; dependency security verifies it when delivery produces the artifact |

{{< disclosure key="supply-boundaries" title="Why these four protections stay separate" >}}
- **Locked versions:** reproduce the same package set on every install.
- **Observation window:** avoid adopting an ordinary release on day one.
- **Vulnerability scan:** check disclosed security issues immediately, without waiting three days.
- **Software bill of materials (SBOM):** list packages present in the released artifact for investigation; it does not block vulnerabilities by itself.
{{< /disclosure >}}

### Other common approaches

- **Automated update service:** periodically opens an upgrade PR, suited to a team that does not want to patrol versions by hand.
- **Package installation policy:** pins installable versions and observes a release right after it ships, lowering the risk that two installs differ.
- **Vulnerability scanning:** checks a public vulnerability database, catching an existing risk even with no update PR in sight.
- **Software bill of materials (SBOM):** lists the packages a release actually contains, for incident investigation and user verification.

{{< config-guidance track="supply" >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="pr" track="pr" eyebrow="Step 06" title="Make completed changes reviewable and deliverable" subtitle="Standalone work goes straight into main; only a Milestone that needs shared acceptance uses a delivery PR." class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>Step 6｜<span class="accent">Make completed changes reviewable and deliverable</span></h2>
        <p class="subtitle"><strong>Baseline.</strong> This page starts once a PR is ready: a work PR completes one Issue, and a delivery PR then confirms the whole batch -- the next page, "Version / delivery," is where the version PR comes in.</p>
      </header>
      <p class="context-line"><strong>What the template does｜</strong>carries a completed change to the right branch, confirms it links back to its work, passes verification, and closes that work once merged.</p>
      <div class="capability-map cols-3"><div class="capability-node"><h3>Standalone work</h3><p>topic → main: one PR completes one reviewable Issue; merging it closes the same-numbered Issue.</p></div><div class="capability-node"><h3>Milestone work</h3><p>topic → <code>dev/m*</code> → delivery PR → main: each PR in the batch lands in <code>dev/m*</code> first, then the delivery PR fully verifies and delivers the whole batch into main once everything is done.</p></div><div class="capability-node"><h3>Exception: hotfix</h3><p>A fix branch may target main directly, but still needs an Issue, review, and full verification.</p></div></div>
      <p class="context-line"><strong>Next step｜</strong>open a work PR once an Issue is done; PR title format, branch naming, and other merge-model comparisons are covered in Maintenance mode.</p>
{{< /legacy >}}

{{< basic >}}
### Our choice

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

### Other common approaches

- **GitHub Flow:** every completed PR goes straight to main -- the shortest path, suited to teams that deliver continuously.
- **Long-lived integration branches:** several work items are accepted together on a dev/release branch, at the cost of keeping them in sync.
- **Stacked PRs:** a large change splits into dependent smaller PRs for a more focused review, at the cost of maintaining stack order.
- **Merge queue:** approved PRs are re-verified against the latest main and merged in order, which needs platform gate support.

{{< config-guidance track="pr" >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="deploy" track="deploy" eyebrow="Step 07" title="Separate version, release, and delivery; deployment is the project's own call" subtitle="Work reaches main first; when a version is needed, the system opens a version PR for human review. The template's job ends at Release, not deployment." class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>Step 7｜<span class="accent">Version rules and what follows an artifact</span></h2>
        <p class="subtitle"><strong>Merging is not releasing, and releasing is not deploying.</strong> A work PR never edits the version directly; Release Please (a tool that automates version numbers) centralizes version and CHANGELOG updates.</p>
      </header>
      <p class="context-line"><strong>Design flow｜</strong>a work PR only declares its version impact; only after a person reviews and merges the version PR does the system create and verify the Release.</p>
      <div class="relation-map"><div class="relation-track cols-4"><article class="relation-node"><span class="relation-kind">1｜Work merges</span><h3>Standalone work</h3><p>When it can be reviewed on its own with no shared deadline or dependency, a reviewed PR may target main directly.</p></article><article class="relation-node"><span class="relation-kind">2｜Version prepared</span><h3>Version materialization</h3><p>When a new version is needed, the system opens a version PR from PR titles and syncs the version and CHANGELOG.</p></article><article class="relation-node"><span class="relation-kind">3｜Release created</span><h3>Release</h3><p>Once the version PR merges, the system verifies the artifact, checksum (a file-integrity code), and SBOM, then publishes an immutable GitHub Release.</p></article><article class="relation-node"><span class="relation-kind">4｜Not the template's job</span><h3>Deployment</h3><p>The template's job ends at Release; deploying to a real runtime is configured by each individual project.</p></article></div></div>
      <p class="context-line"><strong>Next step｜</strong>merging ordinary work into main already completes delivery; Milestone branches, hotfixes, and other version-tool comparisons are covered in Maintenance mode.</p>
{{< /legacy >}}

{{< basic >}}
### Our choice

- **Version intent:** a PR title states major, minor, patch, or no-release impact without reserving an exact number.
- **Version materialization:** Release Please opens one reviewed PR that updates version files, package metadata, and the changelog together. CI does not make a temporary version edit in its checkout.
- **Release:** after that PR merges and full verification passes, the system creates the immutable tag, GitHub Release, explicit artifacts, checksums, and SBOM.
- **Delivery:** merging to `main` is repository delivery and may happen without a new version. A work PR completes one item; a Milestone delivery PR carries the batch.
- **Standalone work:** when one Issue can be reviewed and verified independently and has no shared deadline or cross-Issue dependency, it needs no Milestone and may target `main` directly.
- **Hotfix:** only an urgent defect in `main` uses this route. It still needs a Bug Issue, another reviewer, and full verification; a reviewed version PR then materializes the patch release.
- **Deployment:** operating the product in a real runtime with health checks and recovery belongs to the consuming product, not this template.

{{< disclosure key="deploy-capability-status" title="Every capability's current status, side by side" >}}
| Capability | Current status | Current behavior |
| --- | --- | --- |
| SemVer intent in PRs | Active | `fix` / `revert` means patch, `feat` means minor, `!` means major, and other types mean no release |
| Exact version and changelog | Candidate / Guided | Automatic uses a reviewed Release Please PR; when platform policy blocks it, Guided uses a normal PR opened by a person or agent |
| Tag and GitHub Release | Candidate / Blocked | The sole workflow publishes after the version PR; activation awaits a default-branch run |
| Checksums and SBOM | Configured | Included in the same candidate path; Active only after its first successful run |
| Production-side attestation | Removed (#439) | Zero active workflow ever consumed the release-attestation settings; #439 removed the setting surface itself rather than leave an option that cannot deliver a result. A consuming product adds real attestation through a separate Issue/ADR |
| Consumption-side verification | Conditional | `scripts/verify_release_consumption.py` checks provenance independently of the production-side setting above; it becomes a gate only once a real consumer explicitly adopts it |
| PyPI, npm, and GHCR | Not applicable | The root publishes to no registry; #439 removed the dormant PyPI/npm/GHCR prompts because zero workflow consumed them, so generated projects no longer expose these settings either. A consuming product adds its own OIDC publisher through a separate Issue/ADR |
{{< /disclosure >}}

{{< disclosure key="standalone-delivery" title="When standalone work must join a Milestone" >}}
An Issue may branch from the latest `main`, target `main`, and close through `Closes #N` when it can be accepted on its own and has no shared deadline, batch acceptance, cross-Issue dependency, or isolated test environment. If any of those needs appears, assign the Issue to the appropriate Milestone before implementation and use `dev/m*`; the standalone route cannot bypass batch review.
{{< /disclosure >}}

{{< disclosure key="deploy-ordering" title="Delivery ordering, artifacts, and registry boundaries" >}}
Direct mode rereads the default-branch head before writing and delivers only when the latest `main`, source, tag, CHANGELOG, and promotion evidence agree; workflow concurrency is not treated as FIFO. The artifact workflow accepts only a release-source run ID, creates a digest and SBOM, ignores arbitrary tag pushes, and does not repeat full CI.

GitHub Release is the portable baseline for every profile. Registry publishing and container delivery are product-owned extensions because the template does not ship an active publisher for them. `scripts/release_policy.py` detects GitHub release capabilities and configures versions; `scripts/promotion_gate.py` validates promotion.
{{< /disclosure >}}

{{< disclosure key="hotfix-delivery" title="Hotfix review, verification, and evidence" >}}
A hotfix uses a Bug Issue without a Milestone, the `bug` and `hotfix` labels, `fix/<Issue>-*`, and a `fix(scope): summary` PR directly to `main`. Normal review and full verification still apply. Undisclosed security defects use a GitHub Security Advisory instead. After merge, retain the PR, commit SHA, full run, and rollback note. `fix` normally declares patch intent; the exact version is still reviewed in the Release Please version PR.
{{< /disclosure >}}

{{< disclosure key="manual-release-boundary" title="Automatic-release ownership" >}}
The template root and each new repository are configured to publish through their own release workflow. An adopted repository keeps its product-owned workflow. Every path still needs one owner, least privileges, full-SHA pins, a timeout, concurrency behavior, failure recovery, and a runner-cost ceiling; historical runs remain reference evidence only.

Adoption and update never infer this from a workflow filename. `.csarc/config.yml`, the adoption plan, the Markdown report, and `.csarc/provenance.json` all disclose the same explicit `release_ownership` — `csarc-owned`, `product-owned`, or `verification-only` — plus the selected workflow path, its required `workflow_dispatch` inputs, the settings owner, whether immutable Releases are required, and the reason a repository degrades to `verification-only` (no writer found, or more than one). CSARC never dispatches a product-owned workflow or infers its input contract from a name; it only reads what the workflow itself declares.

A generated repository with `release_ownership: csarc-owned` (including this template's own root) also gets a local publish backup that does not depend on GitHub Actions being healthy: the publish stage of `release.yml` is a single script, `scripts/publish-release`, and a maintainer or agent running locally (or in any environment holding admin/write permission) calls that same script to cut the tag, Release, artifacts, and SBOM. Guided mode's trigger also widens beyond an organization policy that blocks Actions from creating PRs, to also cover a maintainer or agent judging Actions or its webhook delivery currently unhealthy. This path still requires the version pull request to go through the same review as any other `main` PR. GitHub Actions remains the default, recommended path for verification (`verify`/`title`/`promotion` are hosted-only) — but for cutting the actual tag/Release, the hosted job's own `GITHUB_TOKEN` can never prove GitHub's Immutable Releases setting (a repo-administration capability outside any permission scope Actions can grant itself), so this local path is now the standard publish procedure, not a fallback; see [ci-policy.md](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/ci-policy.md) and the [release-security-and-dependencies ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/release-security-and-dependencies.md) for details. This is not a new Copier option — the existing `release_ownership` already routes this capability correctly.

A generated repository with `release_ownership: csarc-owned` (including this template's own root) also gets a local publish backup that does not depend on GitHub Actions being healthy: the publish stage of `release.yml` is a single script, `scripts/publish-release`, and a maintainer or agent running locally (or in any environment holding admin/write permission) calls that same script to cut the tag, Release, artifacts, and SBOM. Guided mode's trigger also widens beyond an organization policy that blocks Actions from creating PRs, to also cover a maintainer or agent judging Actions or its webhook delivery currently unhealthy. This path still requires the version pull request to go through the same review as any other `main` PR. GitHub Actions remains the default, recommended path for verification (`verify`/`title`/`promotion` are hosted-only) — but for cutting the actual tag/Release, the hosted job's own `GITHUB_TOKEN` can never prove GitHub's Immutable Releases setting (a repo-administration capability outside any permission scope Actions can grant itself), so this local path is now the standard publish procedure, not a fallback; see [ci-policy.md](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/ci-policy.md) and the [release-security-and-dependencies ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/release-security-and-dependencies.md) for details. This is not a new Copier option — the existing `release_ownership` already routes this capability correctly.

Milestone closure remains manual until #400 completes its lifecycle contract, and work-Issue closure remains owned by #401. Work branches are removed after merge; a Milestone delivery branch waits until closure and unfinished work are handled.
{{< /disclosure >}}

{{< disclosure key="release-notes-format" title="Where to read release history, and what the format means" >}}
To learn what actually changed in a version, why it shipped, and how it differs from the
prior one, go straight to GitHub's
[Releases page](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/releases): one
Release per version, always carrying three fields — the **version number** (the Release
title, equal to the `vMAJOR.MINOR.PATCH` tag), the **release date** (GitHub's own publish
timestamp, shown automatically), and a **change summary** (GitHub's auto-generated "What's
Changed" list built from the PR titles merged since the prior version, plus a full-compare
link back to it).

None of the three is hand-typed, and none varies by who runs the release: whether GitHub
Actions triggers it automatically or a maintainer runs `scripts/publish-release` locally
because Actions looks unhealthy, both paths call the exact same `scripts/converge-release-tag`
script and the same `gh release create ... --generate-notes` command to produce the Release
body — there is no second implementation that could drift into a different style.

The root `CHANGELOG.md` is a different, equally real view of the same history: it groups
changes by Conventional Commit type (Breaking Changes, Features, Bug Fixes), while the GitHub
Release body lists merged PRs under "What's Changed." The two are not expected to match word
for word — same underlying changes, two different groupings. Every Release is not required to
carry a "Known limitations" or "Backward compatibility" section: most versions have nothing
substantive to say there, and a limitation that holds across many releases (not one version in
particular) belongs here and in `docs/ci-policy.md` instead of being repeated release after
release. The full format contract and the reasoning behind this scope live in the "Release
說明文字的最低格式規範" section of
[ci-policy.md](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/ci-policy.md).
{{< /disclosure >}}

{{< disclosure key="deploy-alternatives" title="Other common approaches" >}}
- **Release Please:** centralizes version and CHANGELOG updates through a reviewable PR.
- **semantic-release:** publishes fully automatically from commit convention once CI succeeds.
- **Changesets:** manages version impact for multiple packages and a workspace through changeset files.
{{< /disclosure >}}

{{< config-guidance track="deploy" >}}

{{< disclosure key="deploy-version-sources" title="Version sources and what must stay in sync" >}}
<aside class="selection-note"><strong>Current boundary</strong><span>No PAT, GitHub App, registry token, or empty deployment environment is required. New repositories use the CSARC workflow; adopted repositories keep their own release process. Registry publishing and attestation remain optional.</span></aside>
<table class="decision-register" aria-label="Version sources and sync scope">
  <thead><tr><th>Version scope</th><th>Single source</th><th>Must stay in sync</th><th>Independent status</th></tr></thead>
  <tbody>
    <tr><td>Template and CLI release</td><td>root <code>.release-please-manifest.json</code></td><td>root version files, README/docs markers, CHANGELOG, tag, Release, and artifacts</td><td>Automatically prepared, human-reviewed</td></tr>
    <tr><td>Copier template revision</td><td>a published tag plus its full commit SHA</td><td>Release provenance and <code>.csarc/config.yml</code>'s <code>_commit</code></td><td>Carries no separate version number</td></tr>
    <tr><td>Generated project release</td><td>its own generated <code>.release-please-manifest.json</code></td><td>that project's own manifest, package, CHANGELOG, tag, and artifacts</td><td>Starts at <code>0.1.0</code>, independent of the template's version</td></tr>
  </tbody>
</table>
<p class="context-line"><strong>SemVer scope｜</strong>the whole template uses exactly one SemVer number: <code>fix(scope)</code> bumps patch, <code>feat(scope)</code> bumps minor, and <code>!</code> bumps major; scope may be tagged <code>ci</code>, <code>python</code>, <code>typescript</code>, or <code>template</code>, and any incompatibility in a supported profile counts as a breaking change for the whole template.</p>
<aside class="selection-note"><strong>Product-owned extension: package and container publishing</strong><span>GitHub Release is the portable baseline. PyPI, npm, GHCR, and artifact attestation have no active template publisher, so a setting toggle alone cannot claim they are enabled; a product with a real registry, owner, and deployment need implements these separately with short-lived OIDC, a dedicated environment, verification, and recovery.</span></aside>
{{< /disclosure >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="governance" track="governance" eyebrow="Step 08" title="Apply only the controls GitHub can enforce" subtitle="The template prepares one policy; a maintainer checks the live plan before relying on it." class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>Detect the GitHub plan first,<span class="accent"> then apply only what it can actually enforce</span></h2>
        <p class="subtitle"><strong>Baseline｜</strong>writing a rule into the repo doesn't mean GitHub can actually enforce it; the template checks the platform's capability first, then decides between enforcing it or degrading explicitly.</p>
      </header>
      <p class="context-line"><strong>Flow｜</strong>desired policy → check the GitHub plan and permissions → can enforce: apply and verify → cannot enforce: mark <code>DEGRADED</code> and leave the responsibility with a person.</p>
      <div class="relation-map"><div class="relation-track"><article class="relation-node"><span class="relation-kind">PR opened</span><h3>Human review</h3><p>The system auto-assigns one non-author reviewer and keeps a review record.</p></article><article class="relation-node"><span class="relation-kind">Check the plan and permissions</span><h3>Can it be enforced?</h3><p>The template checks the current plan, repository visibility, and permissions to judge whether it can create a Ruleset (GitHub's own enforced merge rule).</p></article><article class="relation-node"><span class="relation-kind">Two outcomes</span><h3>Apply and verify, or degrade explicitly</h3><p>When it can enforce, it applies the rule and verifies it took effect in <code>check</code>; when it cannot, it marks <code>DEGRADED</code> and falls back to human discipline, never pretending it is already enforced.</p></article></div></div>
      <p class="context-line"><strong>Next step｜</strong>after a plan change or upgrade, just reapply settings once; which outcome this repository is actually in today, and the full capability of the Team and Enterprise tiers, are covered in Maintenance mode.</p>
{{< /legacy >}}

{{< basic >}}
The template always prepares owners, reviewers, repository defaults, and the desired branch rules. A maintainer then checks the live repository:

- supported controls are applied and verified;
- an unavailable paid control is reported as `DEGRADED` and replaced with an explicit human step, never described as enforced;
- a fixable mismatch fails until corrected.

{{< disclosure key="governance-live-status" title="This repository's own real status right now (checked 2026-09-07)" >}}
The `Innoguard-Cyber-Arch` API reports this repository is on the Free plan with **public** visibility. GitHub already has an `enforcement: active` Ruleset named "CSARC protected branches" (created 2026-09-03), applied to `main` and `dev/m*`: it requires at least 1 approval, CODEOWNER review, and all three of the `title`/`promotion`/`verify` status checks to pass, and disallows force-push -- `main` genuinely does have enforced merge protection today.

This maps to the "Free + public, or Pro personal + private" row in the table below, not the **private** degraded scenario the Free row describes in the "Full capability at each Free/Team/Enterprise tier" cards further down (that card describes what happens on Free + *private*, where the REST/GraphQL Ruleset-creation API refuses the request, so only the desired state can be kept while it is marked `DEGRADED`); this repository is public, so it takes the path that applies and verifies directly. If the plan or visibility changes later, rerunning `plan`/`apply`/`check` reflects the latest state -- this records the fact as of when it was checked, not a permanent guarantee, and it does not mean every repository using this template looks the same.
{{< /disclosure >}}

{{< disclosure key="governance-capability" title="Plan capability, activation, and upgrade conditions" >}}
| GitHub state | What the template can do | Human responsibility |
| --- | --- | --- |
| Free + public, or Pro personal + private | Apply and check the repository Ruleset | Review the planned change before applying it |
| Free organization + private | Apply baseline settings and retain the desired Ruleset in `policies/rulesets.json` | A workflow assigns and records review automatically; there is no enforced merge gate |
| Team / Enterprise organization + private | Validate the CODEOWNERS team, then apply and check the Ruleset | Approve organization-level identity, network, audit, or irreversible changes separately |

Capability is enabled by evidence, not by a predefined maturity label or calendar date. Re-run `plan`, `apply`, and `check` after a visibility or plan change. A real unsupported capability stays `DEGRADED`; an unexpected API or configuration error stops.
{{< /disclosure >}}

{{< disclosure key="governance-plan-tiers" title="Full capability at each Free / Team / Enterprise tier" >}}
<div class="plan-grid">
  <article class="plan-card current"><h3>Free <span class="plan-state">Current</span></h3><p><strong>Review settings are kept; enforcement is degraded:</strong> <code>.github/REVIEWERS</code> holds the reviewer list; on a private repository the desired Ruleset only stays in <code>policies/rulesets.json</code>, since the REST and GraphQL creation APIs both refuse it. `check` reports it as DEGRADED.</p><ul><li><code>governance-comment.yml</code> auto-assigns one non-author reviewer</li><li>No team request or merge gate exists, so the review record cannot substitute for an enforced gate</li></ul></article>
  <article class="plan-card team"><h3>Team <span class="plan-state">Minimum recommended</span></h3><p><strong>Adds:</strong> a private-repository Ruleset, protected branches, required approval, CODEOWNER review, and required checks.</p><ul><li>The same CODEOWNERS team must exist with repository write access</li><li>The template can apply the repository's existing Ruleset directly</li></ul></article>
  <article class="plan-card enterprise"><h3>Enterprise <span class="plan-state">Organization-wide</span></h3><p><strong>Adds:</strong> SAML SSO/SCIM, internal repositories, private/internal deployment protection, private Pages, audit log streaming, and IP allow lists.</p><ul><li>An organization or Enterprise Ruleset can govern centrally</li><li>Currently only detected and reported, never changed automatically</li></ul></article>
</div>
{{< /disclosure >}}

{{< disclosure key="governance-config" title="One configuration source and its ownership layers" >}}
| Layer | `.csarc/config.yml` key | Default / allowed values | Generated or checked at |
| --- | --- | --- | --- |
| Required baseline | `branch_strategy` | `delivery` by default; `delivery` or `main` | branch guidance, `policies/rulesets.json`, and the internal site's delivery-route section |
| Organization policy | `code_owner` | one existing `@organization/team` with repository write access | `.github/CODEOWNERS`; checked by repository-settings plan/apply/check; the internal site's primary-owner line |
| Organization policy | `reviewers` | one or more GitHub usernames | `.github/REVIEWERS`; `governance-comment.yml` assigns automatically on every non-draft pull request |
| Project choice | `project_visibility` | `private` by default; `public`, `private`, or Enterprise `internal` | capability detection, optional security defaults, and the internal site's visible-audience line |
| Project choice | `project_name` | required non-empty string; defaults to `CSARC Project` | the internal site's title and heading |
| Project choice | `project_description` | required one-sentence purpose; rejects placeholder text | the internal site's introduction paragraph |
| Project choice | `languages` | zero or more of `python`, `rust`, `typescript` | repo-site's stated-languages line |
| Project choice | `repository_url`, `project_slug` | derived from `code_owner`/`project_name` unless overridden | repo-site's clone instructions |
| Project opt-in | `enable_governance_drift_check` | `false` by default; set `true` to generate the daily scheduled Action | `false` keeps only the local drift checker; `true` also generates `governance-drift.yml` |

The template repository uses the same public keys and validation as generated repositories. Only generated repositories add Copier `_src_path` and `_commit` metadata. Derived templates may add namespaced keys to this same YAML; they do not create another profile. Low-frequency GitHub details stay in native repository settings or `policies/` instead of expanding the CSARC schema.

A generated project's repo-site runs the same rendering engine and components as this template repository's own root site (Issue #681), just with much leaner content; it resolves its explicit `[[key]]` tokens only from the keys listed above, straight from `.csarc/config.yml`, and an unknown key stops the build, so the site cannot invent a second settings schema. Project content and theme choices outside these keys stay in `site/content/_index.zh-tw.md`, `_index.en.md`, and `docs/site-theme.css`, owned by the consuming project.
{{< /disclosure >}}

{{< disclosure key="governance-exceptions" title="How to record a temporary exception" >}}
Use a linked Issue to record the proposer, a different approver, expiry, evidence, and recovery action. The exception may narrow a control only when the platform cannot provide it or a time-bounded incident requires recovery. It cannot claim a missing check passed, expose a privileged token to pull-request code, or silently become permanent. Close the exception only after recovery is verified; renew it through another explicit approval.
{{< /disclosure >}}

{{< config-guidance track="governance" >}}

{{< disclosure key="governance-plan-behavior" title="GitHub plan vs. apply/check behavior, side by side" >}}
<aside class="selection-note"><strong>Rollout and exception principles</strong><span><code>plan</code> checks the account plan, repo visibility, repository teams, and the Ruleset API first; when the team does not exist, is not visible, or lacks repo write access, it stops outright instead of being masked by the Free-private degraded path. A capability activates only once a live check proves it works, never by assumed maturity or date. Free private supports no team request and cannot force approval; `governance-comment.yml` automatically assigns one non-author reviewer, which only opens a review request and is not a merge gate. Every temporary exception is recorded in an Issue with who requested it, a second approver, an expiry date, evidence, and a recovery plan; a check that never ran cannot be written up as passing. Full administrative-field verification uses an administrator's Administration-read credential from a trusted checkout, never a token exposed to PR code. A GitHub plan upgrade, an irreversible operation, and an organization permission change all need a separate organization-owner approval.</span></aside>
<table class="decision-register" aria-label="GitHub plan vs. apply/check behavior">
  <thead><tr><th>GitHub plan and visibility</th><th><code>apply</code> result</th><th><code>check</code>/PR/CI behavior</th></tr></thead>
  <tbody>
    <tr><td>Free + public</td><td>Applies and enables a Ruleset over REST</td><td>Verifies the effective rule on <code>main</code>; missing or mismatched fails</td></tr>
    <tr><td>Free organization + private</td><td>Applies the baseline settings and keeps the desired Ruleset in <code>policies/rulesets.json</code>; the public API cannot create a Ruleset here</td><td>Marked <code>DEGRADED</code>; the workflow automatically assigns one individual reviewer, and a team request, a red check, or a missing approval can never become a merge gate</td></tr>
    <tr><td>Pro individual account + private</td><td>Applies and enables a Ruleset</td><td>Same as Free public</td></tr>
    <tr><td>Team/Enterprise organization + private</td><td>Confirms the CODEOWNERS team, then applies and enables a Ruleset</td><td>Required review, CODEOWNER, and status checks become the merge gate; a policy mismatch fails closed</td></tr>
  </tbody>
</table>
<p class="reference">Ref. <a href="https://docs.github.com/en/get-started/learning-about-github/githubs-plans" target="_blank" rel="noreferrer">GitHub plans</a>; <a href="https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets" target="_blank" rel="noreferrer">About rulesets</a>. Accessed August 21, 2026.</p>
{{< /disclosure >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="template-release" track="template-release" eyebrow="Step 09" title="Copier keeps repositories aligned, and the template dogfoods its rules" subtitle="A template defect affects many projects, so creation, adoption, and update all run as real tests." legacy="false"  class="candidate-slide" >}}
{{< standard key="template-release-mode-standard" title="How template updates reach your repository safely" >}}
After the template publishes a new version, your repository gets an update notice or a person triggers it manually; Copier (the tool that creates and keeps updating the template) first produces a dry-run candidate **outside** your repository, then compares files one by one:

<div class="plan-grid">
  <article class="plan-card current"><h3>No conflict</h3><p>Updates the matching files in the worktree; main itself has not changed yet.</p></article>
  <article class="plan-card team"><h3>Conflict</h3><p>Only the affected files are listed, keeping your repository unchanged; you adjust and rerun.</p></article>
  <article class="plan-card enterprise"><h3>Human review, then merge</h3><p>Either way, a normal PR carries out full review and only merges into main once it passes -- no step ever skips review to touch main directly.</p></article>
</div>

Three places each own something different: `template/` is the single source of what the template delivers; `.csarc/config.yml` records what this project has chosen and which version it is currently updated to; your product code and specs are entirely yours, and the template always lists a conflict for you to confirm rather than silently overwriting it.
{{< /standard >}}

{{< ops key="template-release-mode-ops" title="Single source, verification flow, and current automation boundary" >}}
- `template/` is the only delivered source; root keeps the template repository's own GitHub governance and dogfood configuration only because that is how GitHub reads it, and `scripts/sync-paired-files.sh` generates root's paired-file copies under `template/`.
- `.csarc/config.yml` is both Copier's update record and the repository's only template configuration. Languages, branch strategy, and optional capabilities read from it; later extensions add settings here instead of creating another configuration file.
- A new repository selects its languages and capabilities, then receives a baseline it can verify directly. Selecting several languages only combines their independent components (modules); it never builds a combination-specific pipeline.
- A first adoption uses a pinned, full-SHA CLI release outside the repository to produce an external change plan, then applies that same undrifted plan. A person reviews the source, plan, diff, and local results in the first PR — the old default branch does not yet contain a trusted verifier, so a PR-head script is never executed and nothing claims automatic verification.
- After that first merge, the default branch supplies the trusted PR policy and read-only CI verifies the candidate. Updates still begin with a dry-run preview, and only apply to the target once the candidate content and conflicts are fully verified; a conflict leaves the repository unchanged so it can be corrected, rerun, and reviewed by a normal PR and trusted-base checks.
- The optional update notice checks weekly and only creates or refreshes one Issue; it never modifies the repository automatically.

{{< disclosure key="copier-update" title="Copier + root dogfood + create/adopt/update regression" >}}
[Copier](https://github.com/copier-org/copier) records source, language, and answers, then reapplies newer template revisions to an editable repository. A person approves the first adoption. A later update conflict leaves the repository unchanged so the affected files can be corrected, rerun, and reviewed in a PR. GitHub Template copies only once and forgets source and answers, while PyScaffold would create a second update mechanism, so neither fits this requirement.
{{< /disclosure >}}

{{< disclosure key="template-release-scope" title="Single source, runtime baselines, and the root-only boundary" >}}
Root `.csarc/config.yml` records the capabilities the template repository selects for itself. A generated repository additionally records Copier's source and revision and writes changes through `csarc update --data`. The template source does not invent `_src_path` or `_commit` values that point back to itself and would immediately go stale. A derived template should add namespaced settings to the same YAML instead of duplicating CSARC fields.

`enable_template_update_notifications` generates `template-update.yml` and `check-template-update` only when selected. Public sources need no secret; private sources use a repository secret limited to read-only access to that template source.

`scripts/sync-paired-files.sh` makes root the single source of paired files, and `--check` verifies copied content and executable bits. `profiles/catalog.yaml` records runtime baselines and their evidence. Python and Node baselines advance only after their own thirty-day observation period (`profiles/catalog.yaml`'s `stable_release_observation_days: 30`).

`scripts/verify-template.sh` runs create/adopt/update fixtures only in the template repository and is never delivered downstream; generated repositories use the smaller `scripts/verify` entry point. The first-adoption machine plan stays outside the target, so proposed files cannot rewrite their own evidence. After the first PR merges, its base supplies the trusted PR policy and read-only CI runs candidate verification.
{{< /disclosure >}}

{{< disclosure key="template-release-status" title="Current automation boundary" >}}
- **Active:** the CLI creates, adopts, or updates and verifies a candidate before writing the target. Template full verification's Regression tests stage reruns all three paths, including the `large`-marked Copier create/adopt/update matrix, and its Package smoke test stage separately confirms the wheel builds and its published entry point runs from the built artifact.
- **Manual:** a person approves the external plan, source, and first adoption PR.
- **Pending:** the update-notice workflow (`template-update.yml.jinja`) and checker script (`check-template-update`) are restored, and a Copier fixture test verifies they are generated only when selected; `tests/test_template_update_notifications.py` covers the checker's own update-detection and Issue create/edit logic, including its fail-closed behavior on a check error, but no hosted scheduled run has been observed, so live-schedule execution is not yet claimed.
- **Retired:** remote governance and delivery orchestration do not return with this page; reviewer assignment is restored and covered under Rules governance instead.
{{< /disclosure >}}

{{< config-guidance track="template-release" >}}
{{< /ops >}}
{{< /slide >}}

{{< slide key="docs-site" track="docs-site" eyebrow="Step 10" title="A portable single file remains the baseline" subtitle="A built-in Python render engine turns the site/content/ Markdown sources into content structure; the existing renderer produces a single offline, forwardable HTML file." class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>A single file stays deliverable forever,<span class="accent"> platform features are only a bonus</span></h2>
        <p class="subtitle"><strong>Choice confirmed.</strong> The single <code>docs/index.html</code> file can be downloaded, forwarded, and opened offline; GitHub Pages or any other hosting is an extra option, never a requirement.</p>
      </header>
      <p class="context-line"><strong>Following on from the last page｜</strong>if process and rules can only live inside config files, a team has a hard time understanding them together, so the same repository also produces a shareable write-up of how it works -- the site you're reading right now.</p>
      <p class="context-line"><strong>Problem and goal｜</strong>keep the distinctive presentation design and single-file delivery, without leaving content, styling, interaction, source choices, and word-for-word tests tangled inside one hand-maintained file.</p>
      <div class="step-flow"><article class="step-flow-item"><span class="step-flow-number">1</span><h3>Source</h3><p>Bilingual Markdown in <code>site/content/</code>, kept apart from layout and code so nothing needs manual syncing.</p></article><article class="step-flow-item"><span class="step-flow-number">2</span><h3>Render</h3><p>A built-in Python engine assembles the content structure -- no Node or extra templating engine needed.</p></article><article class="step-flow-item"><span class="step-flow-number">3</span><h3>Output</h3><p><code>docs/index.html</code> embeds every style, script, and image; each page fits one screen, nothing to scroll to find the point.</p></article><article class="step-flow-item"><span class="step-flow-number">4</span><h3>Reader</h3><p>Download it and open it in a browser to see the whole page; Pages or other hosting is only one more way to browse, never a requirement.</p></article></div>
      <p class="context-line"><strong>Next step｜</strong>download <code>docs/index.html</code> and it is ready to share offline; source structure, theme customization, and access-control detail are covered in Maintenance mode.</p>
{{< /legacy >}}

{{< basic >}}
### Our choice

- `site/content/` holds bilingual Markdown with matching content keys.
- `site/static/styles.css` retains the presentation identity; `scripts/repo_site_blocks.py`'s declarative block parser produces the shared content structure.
- `scripts/render_site.py` embeds CSS, JavaScript, fonts, and images and rejects external runtime assets.
- `./scripts/build-repo-site` regenerates the output; `./scripts/build-repo-site --check` only verifies the source and version compatibility, without writing files.

{{< disclosure key="portable-bundle" title="Markdown + the Python render engine → self-contained HTML" >}}
`docs/adr/` preserves canonical choices. `scripts/build_repo_site.py` owns content and HTML; the unchanged `scripts/render_site.py` only embeds assets and enforces safety checks. The final `docs/index.html` opens offline through `file://` without Pages, a CDN, or a JavaScript package runtime. This single downloadable HTML file is a committed baseline feature, not a stopgap -- even once Pages or other hosting exists, this downloadable, offline-capable output stays.
{{< /disclosure >}}

{{< disclosure key="docs-site-access" title="Access and maintenance boundaries" >}}
`noindex` and `robots.txt` reduce accidental spread but are not access control. An approved host can protect entry, but a downloaded HTML file can still be forwarded. An agent records only user-confirmed durable constraints in an Issue and a reviewed decision record, never a raw conversation transcript.

The renderer resolves the same Rules-governance-approved `.csarc/config.yml` keys documented in the governance configuration table above; it does not define a second, site-only list. Product-specific prose lives in `site/content/_index.zh-tw.md` / `_index.en.md`, theme overrides remain in `docs/site-theme.css`, and the generated `docs/index.html` / `docs/index.en.html` is never edited directly.

**Custom theme for this page (the root site, Issue #527):** the `.csarc/config.yml` / `docs/site-theme.css` path above belongs to a generated project's own repo-site. A maintainer who forks or vendors this template repository itself and wants to restyle its own root repo site uses `site/theme.css` instead. Scope stays deliberately narrow: only override CSS custom properties already declared in `site/static/styles.css`'s `:root` block, plus narrow, purely-visual declarations on existing block-level classes -- no new HTML, JavaScript, or layout rules; ordinary PR review is the only gate, no extra tooling. This file always exists and is always inlined by the engine; it ships empty, so the default output keeps the template's palette unchanged:

```css
:root {
  --yellow: #2e6b47;
}
```

Rebuild with `./scripts/build-repo-site` after editing. This is a structural addition to the presentation template, so `site/version.json`'s `template` version and the `scripts/check-repo-site-versions` compatibility check cover it; see the "根網站自訂主題" section of `docs/adr/portable-repo-site.md` for the full record.
{{< /disclosure >}}

{{< disclosure key="docs-site-alternatives" title="Other common approaches" >}}
- **Hand-edit the single file directly:** stays offline, but source, presentation, and tests end up tightly coupled.
- **Load multiple files at runtime:** easy to forget a file when forwarding it, and `file://` behavior is also limited by the browser.
- **Adopt a documentation platform right away:** no proven need yet for multi-page search, translation, or a cross-repo catalog.
- **Save a full conversation transcript automatically:** mixes in unconfirmed assumptions, sensitive context, and noise.
{{< /disclosure >}}

<aside class="config-guidance"><strong>Website access</strong><p>If reader restrictions become necessary, evaluate Cloudflare Pages + Access first. The host, identity provider, data policy, and organization owner still require separate approval.</p></aside>
{{< /basic >}}
{{< /slide >}}

{{< slide key="bridge" audience="maintainer" eyebrow="May 2026 internal presentation" title="Review the original principles against today's implementation" subtitle="Revisits the SDLC ideas shared internally in May 2026 and marks what is retained, adjusted, or deferred; click a row for the three-sentence call." class="legacy-slide bridge-slide" legacy="false" >}}
      <p class="bridge-intro">This page explains which May 2026 ideas were kept, adjusted, or deferred; day-to-day operation still follows each Journey and the current policy documents.</p>
      <table class="bridge-table" aria-label="Page-by-page comparison of the May deck and today's design">
        <colgroup><col class="page-col"><col class="topic-col"><col class="status-col"><col class="decision-col"></colgroup>
        <thead><tr><th>Page</th><th>May deck topic</th><th>Outcome</th><th>Current decision (click)</th></tr></thead>
        <tbody>
          <tr><td>p.3</td><td>Core SDLC stages</td><td><span class="bridge-status keep">Keep</span></td><td><details class="bridge-detail drop-down"><summary>Center plan-through-monitor on GitHub</summary><div class="bridge-popover"><p><strong>May deck｜</strong>The core order of plan, build, test, deploy, monitor is kept.</p><p><strong>This round｜</strong>Work items, templates, pull requests, automated checks, and delivery settings all live in GitHub, for easier ongoing maintenance.</p><p><strong>Implementation｜</strong>Not every project deploys or monitors, but all of them follow the same work-planning, change-review, and verification rules first.</p></div></details></td></tr>
          <tr><td>p.4</td><td>Jira ticket</td><td><span class="bridge-status adjust">Adjust</span></td><td><details class="bridge-detail drop-down"><summary>Every change starts as a minimal GitHub Issue</summary><div class="bridge-popover"><p><strong>May deck｜</strong>Jira's Epic → Story → Task split is replaced this round by only the necessary GitHub Issue, Milestone, and spec.</p><p><strong>This round｜</strong>A one-off task picks one type and states the problem and completion criteria; a complex request opens a planning Issue first, then an approved spec creates the implementation Issue. New scope gets its own Issue.</p><p><strong>Implementation｜</strong><code>work-item.yml</code> requires a type plus two required fields (problem, completion criteria) and one optional one; <code>work-item-lifecycle.yml</code> assigns the opener; the PR workflow checks the label, branch, and the matching open Issue.</p></div></details></td></tr>
          <tr><td>p.5</td><td>Version control</td><td><span class="bridge-status adjust">Adjust</span></td><td><details class="bridge-detail drop-down"><summary>A delivery branch is a CI integration boundary, not a pretend environment</summary><div class="bridge-popover"><p><strong>May deck｜</strong>Parallel branches are kept, but no project is required to have a physical DEV environment.</p><p><strong>This round｜</strong>Standalone work branches from the latest <code>main</code> and returns straight to <code>main</code>; only a Milestone needing joint acceptance uses <code>dev/m*</code>, an independent canary uses a temporary <code>dev/i*</code>, and a hotfix also fixes <code>main</code> directly.</p><p><strong>Implementation｜</strong>An ordinary PR runs the checks its risk requires; Milestone/canary delivery and a hotfix run full verification; syncing the latest main only happens at final delivery or when a dependency is explicitly recorded.</p></div></details></td></tr>
          <tr><td>p.6</td><td>PR and review</td><td><span class="bridge-status adjust">Strengthen</span></td><td><details class="bridge-detail drop-down"><summary>Issue, numbered branch, and PR form one fixed chain</summary><div class="bridge-popover"><p><strong>May deck｜</strong>A PR stays the only entry point into a protected branch; the direction holds. The three-tier review is replaced by adding reviewers based on risk.</p><p><strong>This round｜</strong>An ordinary PR needs its matching-numbered Issue, CI, and one peer; a high-risk architecture change also attaches a decision record.</p><p><strong>Implementation｜</strong>Branches are fixed as <code>type/123-short-slug</code>, and a PR body always carries <code>Closes #123</code>; <code>governance-comment.yml</code> auto-assigns one non-author reviewer on every non-draft PR; team requests and required approval need GitHub Team or above.</p></div></details></td></tr>
          <tr><td>p.7</td><td>CI automation pipeline</td><td><span class="bridge-status keep">Keep</span></td><td><details class="bridge-detail drop-down"><summary>Local and CI share one entry point, tiered by risk</summary><div class="bridge-popover"><p><strong>May deck｜</strong>Automatic triggers, tests, formatting, and static-error checks are all kept.</p><p><strong>This round｜</strong>An ordinary Issue PR runs fast; promotion, hotfix, merge queue, and unknown high-risk paths run full; OSV, Zizmor, and remote governance run on their own scope or schedule.</p><p><strong>Implementation｜</strong>A fixed <code>verify</code> aggregate keeps a skipped workflow from leaving a stuck Pending; delivery sync folds into the <code>title</code> policy; a candidate's full run is never cancelled, while an ordinary PR's new commit cancels its own stale run. A Ruleset, once available, requires <code>title</code>, <code>verify</code>, and <code>promotion</code>.</p></div></details></td></tr>
          <tr><td>p.8</td><td>CD project management</td><td><span class="bridge-status adjust">Adjust</span></td><td><details class="bridge-detail drop-down"><summary>Repository delivery completes first; version and release get reviewed after</summary><div class="bridge-popover"><p><strong>May deck｜</strong>The original default was DEV → STAGING → Canary → PROD; this round does not require every project to copy all four tiers.</p><p><strong>This round｜</strong>Merging a Milestone, standalone work, or a hotfix into <code>main</code> already counts as repository delivery; a reviewable version PR is opened only when a new version is actually needed.</p><p><strong>Implementation｜</strong>Release Please syncs the version and CHANGELOG; once the version PR merges, a single workflow creates the checksum, SBOM, artifact, and immutable GitHub Release. Attestation and consumption-side gates stay optional.</p></div></details></td></tr>
          <tr><td>p.9</td><td>Observability</td><td><span class="bridge-status defer">Phase 2</span></td><td><details class="bridge-detail"><summary>Monitoring and on-call are only for services actually running live</summary><div class="bridge-popover"><p><strong>May deck｜</strong>Runbooks, logs, metrics, tracing, recovery, and on-call stay a phase-two effort.</p><p><strong>This round｜</strong>Only introduced for continuously running services; tools are picked by the actual cloud, environment, and owner instead of committing to Datadog or PagerDuty upfront.</p><p><strong>Implementation｜</strong>Test data is managed separately as PII-free, creatable, disposable fixtures, instead of folding test-data management into live monitoring.</p></div></details></td></tr>
          <tr><td>p.10</td><td>Copilot → Agent</td><td><span class="bridge-status defer">Phased</span></td><td><details class="bridge-detail"><summary>Controlled AI collaboration first; automatic retry only once mature</summary><div class="bridge-popover"><p><strong>May deck｜</strong>The direction of AI growing from code completion into running full tasks is kept, but never to the point of reducing an engineer to writing only prompts.</p><p><strong>This round｜</strong>In this first phase, an agent researches, proposes a plan, makes the change, verifies it, and opens a PR against a clear work item; parallel writable tasks each use their own branch and Git worktree, and tooling convenience is handled by an agent kit.</p><p><strong>Implementation｜</strong><code>AGENTS.md</code> plus the shared verification commands bound how work happens; <code>actions.json</code> keeps Actions read-only by default and unable to approve a PR, and a Ruleset requires human approval. The worktree manager is not CI/CD and gets no extra secret or merge permission.</p></div></details></td></tr>
          <tr><td>p.11</td><td>AI first review</td><td><span class="bridge-status adjust">Adjust</span></td><td><details class="bridge-detail"><summary>Deterministic tools decide; AI only adds suggestions</summary><div class="bridge-popover"><p><strong>May deck｜</strong>AI first review is kept, but code formatting and common mistakes move to a formatter, linter, and static check running reliably instead.</p><p><strong>This round｜</strong>AI review only adds contextual-error notes, test-gap flags, a risk summary, and fix suggestions -- it is never treated as proof something passed.</p><p><strong>Implementation｜</strong>Only CI, peer review, and a named owner can decide to merge; AI holds no approval, merge, or secret-reading permission.</p></div></details></td></tr>
          <tr><td>p.12</td><td>AI CI/CD log</td><td><span class="bridge-status defer">Phase 2</span></td><td><details class="bridge-detail"><summary>Summarize failures first; automatic recovery only for mature deployments</summary><div class="bridge-popover"><p><strong>May deck｜</strong>AI may summarize a CI failure first; automatic rollback applies only to a deployment that already has a real environment and reliable health signals.</p><p><strong>This round｜</strong>A failing PR test blocks the merge and gets fixed with a new commit -- never skipped; if <code>main</code> itself breaks, a recovery PR lands plus a tracking work item.</p><p><strong>Implementation｜</strong>Automatic recovery is only considered once health signals, a stop threshold, reproducible recovery, and full logging are all mature.</p></div></details></td></tr>
          <tr><td>p.13</td><td>AI docs and knowledge base</td><td><span class="bridge-status defer">Phased</span></td><td><details class="bridge-detail"><summary>Maintain the in-repo site first; hosting and RAG wait</summary><div class="bridge-popover"><p><strong>May deck｜</strong>Keeping docs in sync is kept; letting AI search docs before answering (RAG) becomes optional.</p><p><strong>This round｜</strong>README, specs, and <code>docs/index.html</code> all travel through PRs with the code; a generated project separately keeps an updatable template and content files that are never overwritten.</p><p><strong>Implementation｜</strong>Cloudflare hosting is not wired up yet; site rendering already moved to the built-in Python engine, and Hugo was removed in Milestone 13 (Issue #524). AI semantic review only becomes a gate once the model endpoint and data policy are settled, and RAG only happens once the source, owner, access rules, citations, and test questions are all ready.</p></div></details></td></tr>
          <tr><td>p.14</td><td>Legacy modernization</td><td><span class="bridge-status remove">Optional</span></td><td><details class="bridge-detail"><summary>Legacy-system rework is a project's own need, not a shared template default</summary><div class="bridge-popover"><p><strong>May deck｜</strong>Mentioned using AI to help modernize a legacy system; this round does not fold it into the shared template every project must use.</p><p><strong>This round｜</strong>This is a specific project's own transformation work: first characterize current behavior with tests, then replace it in small steps reviewed through short PRs, keeping a rollback path.</p><p><strong>Implementation｜</strong>A dedicated template or guide gets built only once a real legacy system, its risk, and its benefit exist -- never by placing an empty tool into every new project upfront.</p></div></details></td></tr>
        </tbody>
      </table>

{{< detail key="bridge-reason" title="Evidence behind the changes" >}}
GitHub plan, repository visibility, organization policy, and token identity all affect capabilities, so runtime probes replace static guesses. Tiered CI separates daily feedback from full delivery confidence. Copier updates keep shared policy current without taking ownership of product content.
{{< /detail >}}

<p class="bridge-reference reference">Ref. GitHub Docs. <a href="https://docs.github.com/en/copilot/tutorials/cloud-agent/get-the-best-results" target="_blank" rel="noreferrer">AI agent practices</a>; <a href="https://docs.github.com/en/get-started/using-github/github-flow" target="_blank" rel="noreferrer">GitHub flow</a>; <a href="https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues" target="_blank" rel="noreferrer">Sub-issues</a>; <a href="https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets" target="_blank" rel="noreferrer">Rulesets</a>; <a href="https://docs.github.com/en/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site" target="_blank" rel="noreferrer">Pages visibility</a>. Accessed August 20, 2026.</p>
{{< /slide >}}

{{< slide key="similar-tools" parity="supplemental" eyebrow="Similar tools" title="Similar tools | Direct alternatives and focused references" subtitle="Standard mode shows projects with a similar overall purpose; Maintenance mode adds concrete comparisons by journey. Tools this template directly integrates are on the File map instead." class="similar-tools-slide" legacy="true" >}}
{{< similar-tools >}}
{{< /slide >}}

{{< slide key="testing" audience="maintainer" parity="supplemental" eyebrow="Maintenance appendix | CI/CD settings" title="CI/CD settings | Checks by step" subtitle="Separates the tests and automation that normal repositories and repo-template need for work and repository-delivery pull requests." class="similar-tools-slide testing-slide" legacy="true" >}}
{{< testing >}}
{{< /slide >}}

{{< slide key="rollout" track="rollout" audience="archive" eyebrow="Phased rollout" title="Phased rollout, verifiable and stoppable at every step" subtitle="Three tiers: basic capability ships today; future and optional capability states its own trigger condition." class="legacy-slide review-notes-slide" legacy="true" >}}
<aside class="selection-note"><strong>Current state｜2026-09-03</strong><span>The technical view below keeps the original three-tier rollout judgment for audit; each tier's actual state is authoritative in <code>profiles/catalog.yaml</code> and its verification scripts, not repeated here.</span></aside>
{{< legacy >}}
      <header>
        <h2>Phased rollout,<span class="accent"> verifiable and stoppable at every step</span></h2>
        <p class="subtitle"><strong>Three tiers｜</strong>basic capability already ships with the template; future and optional capability states its own trigger condition instead of an empty placeholder file pretending to be done.</p>
      </header>
      <p class="context-line"><strong>Problem and goal｜</strong>adopting a template, CI, deployment, monitoring, and AI all at once makes it hard to tell where something broke; phasing gives every step its own completion condition.</p>
      <div class="decision-strip">
        <article class="decision-step"><span class="step-label">Other common approach</span><h3>Turn everything on at once, by hype or by date</h3><ul><li><strong>Flip a single switch:</strong> a mistake spreads to every project at once</li><li><strong>Unlock by a fixed date:</strong> a date passing does not mean the conditions for use are met</li><li><strong>Ship every language together:</strong> an unverified profile is only an empty promise</li></ul></article>
        <article class="decision-step recommended"><span class="step-label">Our choice</span><h3>Three tiers are rollout conditions, not dates</h3><p><strong>Basic rollout:</strong> CI/CD-only, Python-only, TypeScript-only, and mixed profiles ship today, along with Issue/spec, PR/CI, local verification, OSV, dependency policy, and the repo site. Free plans detect their own capability and apply what is available; private repositories never claim Ruleset enforcement they cannot get.<br><strong>Verified in production:</strong> release handoff, traceable artifacts, and Release attestation consumer verification are live, together with the first real CI-only downstream repository's adoption and Copier update; shared governance and CI-only composition are beta.<br><strong>Still trialing:</strong> Python, TypeScript, and mixed composition each still need one more real consuming repository before promotion to beta.<br><strong>Future or optional:</strong> a central catalog/governance platform, multi-repository support, Go/Rust, site hosting/login, deployment, monitoring, RAG, and autonomous agents.</p></article>
      </div>
{{< /legacy >}}

{{< basic >}}
| Tier | Current state |
| --- | --- |
| Basic rollout | CI/CD-only, Python-only, TypeScript-only, and mixed profiles ship today, along with Issue/spec, PR/CI, local verification, OSV, dependency policy, and the repo site. Free plans detect their own capability and apply what is available; private repositories never claim Ruleset enforcement they cannot get. |
| Verified in production | Release handoff, traceable artifacts, and Release attestation consumer verification are live, together with the first real CI-only downstream repository's adoption and Copier update; shared governance and CI-only composition are beta. |
| Still trialing | Python, TypeScript, and mixed composition each still need one more real consuming repository before promotion to beta. |
| Future or optional | A central catalog/governance platform, multi-repository support, Go/Rust, site hosting/login, deployment, monitoring, RAG, and autonomous agents. |

{{< disclosure key="rollout-config" title="Where this is configured" >}}
- **Which profiles are available or still planned:** `profiles/catalog.yaml`
- **Detect the plan before applying settings:** `scripts/apply-repository-settings.sh`; only enable once Ruleset/App preconditions are met
- **Whether create and update paths both pass:** `scripts/verify-template.sh`
{{< /disclosure >}}

<aside class="config-guidance"><strong>Where this is configured</strong><ul><li><strong>Which profiles are available or still planned:</strong><code>profiles/catalog.yaml</code></li><li><strong>Detect the plan before applying settings:</strong><code>scripts/apply-repository-settings.sh</code>; only enable once Ruleset/App preconditions are met</li><li><strong>Whether create and update paths both pass:</strong><code>scripts/verify-template.sh</code></li></ul></aside>
{{< /basic >}}
{{< /slide >}}

{{< slide key="access-control" audience="archive" eyebrow="Access decision" title="Temporary protection before a hosting choice" subtitle="Current measures reduce accidental sharing; none is described as access control." class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">Decision appendix</span>
        <h2>Access control decision｜<span class="accent">Temporary protection before a hosting choice</span></h2>
        <p class="subtitle">Weighs the cost and limits of three access-control options; until one is finalized, <code>noindex</code>/<code>robots.txt</code> only reduce accidental exposure and are never described as access control.</p>
      </header>
      <div class="plan-grid">
        <article class="plan-card team"><h3>Cloudflare Pages + Access <span class="plan-state">Candidate</span></h3><p><strong>Cost:</strong> the free allowance covers a small team's login wall; requires setting up a Zero Trust policy, domain, and DNS.<strong>Limitation:</strong> needs a separate Cloudflare account and organization identity integration (Google/GitHub SSO or email OTP); data and audit policy must be confirmed first.<strong>Owner:</strong> an organization owner must create and hold the Cloudflare account permissions; not created or configured by this Issue.</p></article>
        <article class="plan-card enterprise"><h3>GitHub Pages + IP restriction <span class="plan-state">Restricted</span></h3><p><strong>Cost:</strong> reuses the existing GitHub organization; no separate external account needed.<strong>Limitation:</strong> a private Pages site requires GitHub Enterprise Cloud; an IP allow list is hard to maintain for a remote/hybrid team, and the organization is currently on the Free plan, which does not have this capability.<strong>Owner:</strong> an organization owner must upgrade the plan first before Enterprise network policy can be configured.</p></article>
        <article class="plan-card current"><h3>Internal login platform (Backstage, Confluence, etc.) <span class="plan-state">Future</span></h3><p><strong>Cost:</strong> can integrate with an existing identity system (SSO) and manage several internal documents centrally, not just this one page.<strong>Limitation:</strong> requires adopting and operating a separate platform; with only one repo-site today, the adoption cost exceeds the benefit.<strong>Owner:</strong> an IT/platform team must build and operate it; a future option to evaluate once there are more services.</p></article>
      </div>
      <aside class="selection-note"><strong>Current decision</strong><span>All three options need an external account or an organization upgrade, which is out of scope for this Issue; Cloudflare Pages + Access is the leading candidate for future evaluation. Until one is finalized, only <code>noindex</code>/<code>robots.txt</code> reduce accidental exposure. Once an option is finalized, open a separate implementation Issue and have an organization owner approve and hold the account.</span></aside>
{{< /legacy >}}

{{< basic >}}
| Option | Cost and benefit | Current limitation or owner |
| --- | --- | --- |
| Cloudflare Pages + Access | Free allowance can provide a small-team login wall | Organization owner must establish Cloudflare, domain, DNS, and SSO/OTP policy |
| GitHub Pages + IP restriction | Reuses the GitHub organization | Private Pages and IP allow lists require Enterprise Cloud; current Free plan cannot provide them |
| Backstage, Confluence, or another internal portal | Can govern several internal documents together | One site does not justify an IT/platform-operated service today |

{{< disclosure key="access-control-limit" title="What exists and what it cannot do" >}}
`docs/index.html` contains `noindex,nofollow`, while `docs/robots.txt` asks crawlers to stay away. Neither authenticates a reader, and anyone with the offline file can forward it. Issue #79 recorded this interim protection and closed as completed; selecting the actual host, identity provider, data policy, and audit policy has no open Issue yet and needs a new one once that decision is ready.
{{< /disclosure >}}

<aside class="config-guidance"><strong>Where this is configured</strong><ul><li><strong>Interim measure:</strong> <code>&lt;meta name="robots"&gt;</code> in <code>docs/index.html</code> plus <code>docs/robots.txt</code></li><li><strong>Decision record:</strong> <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/79" target="_blank" rel="noreferrer">Issue #79</a> (closed, records the interim protection; host selection has no open Issue yet, needs a new one)</li></ul></aside>
{{< /basic >}}
{{< /slide >}}

{{< slide key="principles" audience="archive" eyebrow="Key decisions" title="Rules, reasons, and deliberate omissions" subtitle="These decisions are backed by current files and checks." class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">Decision appendix</span>
        <h2>Key decisions｜<span class="accent">Rules, reasons, and deliberate omissions</span></h2>
        <p class="subtitle">The original supplementary document has been folded into this page; detail follows the executable configuration, updated through an Issue/PR when conditions change.</p>
      </header>
      <table class="decision-register" aria-label="Template core decision register">
        <thead><tr><th>Review question</th><th>Current decision and reason</th></tr></thead>
        <tbody>
          <tr><td>Plan and <code>main</code> protection</td><td>Free private applies baseline settings and preserves Ruleset policy, but the public API cannot create a Ruleset, so <code>main</code> is still not enforced; upgrading to Team plus a CODEOWNERS team, or an approved switch to public, is what turns approval and required checks into a real merge gate.</td></tr>
          <tr><td>Work scope and ownership</td><td>Issue-first; a title is a 12-80 character English summary of the outcome, the body may be written in any language; the opener becomes the default owner. New requirements beyond the acceptance criteria get a separate Issue.</td></tr>
          <tr><td>Template update boundary</td><td><code>template/</code> is the delivery source, and root lets the template govern itself; Copier updates policy while protecting product code and specs, and paired verification scripts prevent drift.</td></tr>
          <tr><td>Language and code quality</td><td>Python, Rust, and TypeScript are independent modules, selectable in any combination; Python uses uv, Ruff, ty, and pytest, Rust uses Rust 1.98, rustfmt, Clippy, and Cargo, and TypeScript uses Node 24, pnpm, Biome, and Vitest.</td></tr>
          <tr><td>CI, versioning, and delivery</td><td>Local and CI share <code>scripts/verify</code>; PR-policy regression cases prove a wrong route is rejected. Day-to-day work runs fast, promotion runs full, and Release Please maintains one SemVer only at verified delivery boundaries.</td></tr>
          <tr><td>Dependencies and supply chain</td><td>A three-day observation window watches for an unknown malicious release; OSV checks disclosed vulnerabilities; hashes verify content consistency; an SBOM lists an artifact's packages; and the resolver separately proves the version range is installable — none of the five substitutes for another.</td></tr>
          <tr><td>AI, documentation, and future capability</td><td><code>AGENTS.md</code> is the AI rulebook; the README and repo site serve people. Hugo/hosted login, deployment, monitoring, RAG, and Go all need an owner, a real use case, and verification before adoption.</td></tr>
          <tr><td>Verification and test resources</td><td>"Done" requires files and tests; verification only uses a local scratch project or this repository's own Issues, branches, PRs, and Actions — never a separate GitHub repository created only for testing.</td></tr>
        </tbody>
      </table>
{{< /legacy >}}

{{< basic >}}
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

{{< disclosure key="principles-transcript" title="How durable decisions are recorded" >}}
Agents do not save raw conversations. Only a user-confirmed durable architecture, security, compatibility, or platform constraint is summarized into an Issue and then written to `docs/adr/` or `docs/decisions/` through a scoped PR. Executable configuration remains authoritative, and changed conditions are updated through another Issue and PR.
{{< /disclosure >}}

<p class="review-note-footer"><strong>Verification commitment:</strong> <code>./scripts/verify-template.sh</code> actually runs a new project, an existing-project adoption, and the same adopted repository's Copier update plus its full post-update verification; this root-only script is never shipped downstream.</p>
{{< /basic >}}
{{< /slide >}}

{{< slide key="benchmark" audience="archive" eyebrow="External benchmark and live evidence" title="A solid foundation, not a complete platform" subtitle="Active capabilities use current files and runs; historical release evidence remains explicitly archived." class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">Decision appendix</span>
        <h2>External benchmark and live evidence｜<span class="accent">A solid foundation, not a complete platform</span></h2>
        <p class="subtitle">Conclusion: new-project creation, Copier updates, and local/synthetic verification are genuinely solved; OSV, Release, and the first real CI-only consuming repository all have live, successful evidence. Governance remains bound by the GitHub plan, and language modules are accepted through a reproducible lifecycle and native tooling.</p>
      </header>
      <table class="decision-register audit-register" aria-label="External benchmark and live-evidence comparison">
        <thead><tr><th>External benchmark / live evidence</th><th>Assessment</th><th>Research choice and current boundary</th></tr></thead>
        <tbody>
          <tr><td><a href="https://copier.readthedocs.io/en/stable/updating/" target="_blank" rel="noreferrer">Copier</a> vs <a href="https://projen.io/docs/introduction/" target="_blank" rel="noreferrer">projen</a></td><td><span class="tier-chip best">Good fit</span></td><td>The requirement is "editable after generation, still updatable later"; Copier's smart update fits better than projen, which has code continuously own the generated files — keeping the current choice.</td></tr>
          <tr><td><a href="https://engineering.atspotify.com/2020/08/how-we-use-golden-paths-to-solve-fragmentation-in-our-software-ecosystem" target="_blank" rel="noreferrer">Spotify Golden Path</a> + <a href="https://backstage.io/docs/features/software-catalog/" target="_blank" rel="noreferrer">Backstage Catalog</a></td><td><span class="tier-chip priority">Only one layer</span></td><td>This is currently a single-repository golden-path template, not a platform with a catalog, ownership, maturity, and fleet migration; adopt once cross-team service discovery becomes a repeated pain point. → <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/105" target="_blank" rel="noreferrer">#105</a></td></tr>
          <tr><td><a href="https://github.com/ossf/allstar" target="_blank" rel="noreferrer">Allstar</a> / <a href="https://github.com/github-community-projects/safe-settings" target="_blank" rel="noreferrer">Safe Settings</a></td><td><span class="tier-chip best">Sufficient today</span></td><td>Scheduled drift checking is already complete via <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/75" target="_blank" rel="noreferrer">#75</a>; switch to a central policy service once the fleet grows and the same class of drift keeps recurring.</td></tr>
          <tr><td><a href="https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets" target="_blank" rel="noreferrer">GitHub Rulesets</a> / Free private</td><td><span class="tier-chip priority">Partially solved</span></td><td>Platform capability can be detected and flagged, but Free private cannot enforce a Ruleset; <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/87" target="_blank" rel="noreferrer">#87</a> already records the unprotected state in policy, and the plan limitation remains explicit.</td></tr>
          <tr><td>Release Please live runs + <a href="https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow" target="_blank" rel="noreferrer"><code>GITHUB_TOKEN</code> trigger rules</a></td><td><span class="tier-chip best">Live loop closed</span></td><td><a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/32645380139" target="_blank" rel="noreferrer">An existing run</a> proves organization policy blocks an Actions-authored PR, so the flow picks release-please, direct, or verification-only based on current capability; the <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/32662029395" target="_blank" rel="noreferrer">v0.2.4 run</a> already completed governance, full verification, immutable release publication, and trust-chain verification.</td></tr>
          <tr><td>OSV reusable workflow + <a href="https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows" target="_blank" rel="noreferrer">permission propagation</a></td><td><span class="tier-chip best">Corrected</span></td><td>A caller's permissions can only stay the same or shrink, never top up a called workflow; after <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/92" target="_blank" rel="noreferrer">PR #92</a> restored the required permission, the <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/32646097257" target="_blank" rel="noreferrer">live run on main</a> succeeded.</td></tr>
          <tr><td><a href="https://docs.github.com/en/actions/concepts/security/artifact-attestations" target="_blank" rel="noreferrer">Artifact Attestations</a> + <a href="https://slsa.dev/spec/v1.2/build-track-basics" target="_blank" rel="noreferrer">SLSA Build</a></td><td><span class="tier-chip partial">Product extension</span></td><td>The template's current shared baseline is an immutable GitHub Release, checksums, an SBOM, and consumer-side verification; a product that needs a registry or artifact attestation should build a real publisher, OIDC trust, and verification of its own rather than get a setting toggle with no one actually running it.</td></tr>
          <tr><td><a href="https://github.com/ossf/scorecard" target="_blank" rel="noreferrer">OpenSSF Scorecard</a> security baseline</td><td><span class="tier-chip optional">Plan-aware</span></td><td>Pinned Actions, OSV, <code>SECURITY.md</code>, full Git history, and working-tree secret scanning already exist; a public repository enables CodeQL by default, while private/internal opts in explicitly once GitHub Code Security is licensed.</td></tr>
          <tr><td>Real consuming repository and adoption evidence</td><td><span class="tier-chip best">Shared lifecycle proven</span></td><td><code>ai-guardrail</code> completed v0.2.4 adoption, kept its product customization, ran a v0.3.1 Copier update, and passed two full live checks across two PRs and one Issue; Python, Rust, and TypeScript each carry their own executable beta acceptance evidence. → <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/100" target="_blank" rel="noreferrer">#100</a> / <a href="pilot-adoption.md">evidence</a></td></tr>
        </tbody>
      </table>
{{< /legacy >}}

{{< basic >}}
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

{{< disclosure key="benchmark-gap" title="Current gaps" >}}
There is no cross-repository catalog, comprehensive hosted governance, registry publisher, or generic deployment platform. Historical live-integration runs remain audit evidence only; active workflow claims must come from files under `.github/workflows/` and current runs. Production repositories will add operational evidence without serving as disposable language test fixtures.
{{< /disclosure >}}

<p class="review-note-footer"><strong>Simplicity assessment:</strong> Copier plus GitHub Actions plus standard tooling stays simple enough; the real CI-only pilot already adds live evidence for the shared lifecycle. The root-only <code>Live integration smoke</code> keeps verifying OSV, Release Please, release handoff, and governance drift; language modules keep their beta status through their own reproducible tests.</p>
{{< /basic >}}
{{< /slide >}}

{{< slide key="fleet-inventory" audience="archive" eyebrow="Fleet governance" title="Audit the fleet locally instead of publishing it" subtitle="This organization is private; a maintainer checks current adoption on demand instead of reading a static page." class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">Decision appendix</span>
        <h2>Fleet governance inventory｜<span class="accent">Audit locally, never published</span></h2>
        <p class="subtitle">This organization is private, and this template repository may eventually be shared with other groups; the real repository list is never written into site content or git history. A maintainer instead uses <code>scripts/audit-fleet-adoption</code> for a live, on-demand, terminal-only query.</p>
      </header>
      <table class="decision-register audit-register" aria-label="Fleet inventory evaluation method">
        <thead><tr><th>Evaluation input</th><th>How it is obtained</th></tr></thead>
        <tbody>
          <tr><td>Repository list</td><td><code>gh repo list</code> against the real organization; never written into site content or git history</td></tr>
          <tr><td>CODEOWNERS coverage</td><td>Presence of <code>.github/CODEOWNERS</code> checked per repository via <code>gh api</code></td></tr>
          <tr><td>Copier adoption state</td><td>Presence of <code>.csarc/config.yml</code> checked per repository via <code>gh api</code>; the source template repository is excluded since dogfooding Copier on itself also leaves this file, and it is never counted as a consuming repository</td></tr>
          <tr><td>Threshold comparison</td><td>Computed against the numeric triggers already defined on the <code>fleet-governance-thresholds</code> page</td></tr>
        </tbody>
      </table>
      <aside class="selection-note"><strong>How to run it</strong><span>A maintainer reproduces this evaluation locally with <code>./scripts/audit-fleet-adoption</code>: the script queries the organization live, computes whether the catalog and policy-enforcement thresholds are met, and prints only to standard output — it writes no file, creates no cache or artifact, and uploads nothing anywhere, so the real repository list never lands in this site or its history.</span></aside>
{{< /legacy >}}

{{< basic >}}
| Evaluation input | How a maintainer obtains it |
| --- | --- |
| Repository list | `gh repo list` against the live organization; never copied into site content or git history |
| CODEOWNERS coverage | Presence of `.github/CODEOWNERS` per repository, read live via `gh api` |
| Copier adoption | Presence of `.csarc/config.yml` per repository, read live via `gh api`, excluding template-source repositories that also carry it from dogfooding Copier on themselves |
| Threshold comparison | Computed against the numeric triggers on `fleet-governance-thresholds` |

Run `./scripts/audit-fleet-adoption` locally as a maintainer to reproduce this evaluation. The script queries the organization live, computes whether the fleet currently meets the catalog and policy-enforcement thresholds, and prints the result to standard output only. It never writes a file, never creates a cache or artifact, and never uploads anything anywhere, so the real repository list never lands in this site or its history.

{{< disclosure key="fleet-inventory-source" title="Inventory evidence and interpretation" >}}
The script reads GitHub repositories, CODEOWNERS presence, and Copier adoption markers directly from the API; a repository with no completed scheduled drift sample is never counted as zero drift. Re-run after each new pilot and during quarterly review — a printed result reflects that moment only, and no snapshot is retained afterward.
{{< /disclosure >}}

<p class="bridge-reference reference">Inventory method: GitHub repositories, CODEOWNERS, and Copier adoption markers, queried live via `gh api` / `gh repo list`.</p>
{{< /basic >}}
{{< /slide >}}

{{< slide key="fleet-governance-thresholds" audience="archive" eyebrow="Fleet thresholds" title="Measure the problem before adding a platform" subtitle="Catalog and policy enforcement solve different problems and use separate evidence." class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">Decision appendix</span>
        <h2>Fleet governance thresholds｜<span class="accent">Measure the problem before adding a platform</span></h2>
        <p class="subtitle">A catalog handles service visibility and ownership; policy enforcement handles cross-repository setting drift. The two problems are counted separately and get separate tools.</p>
      </header>
      <div class="decision-strip">
        <article class="decision-step recommended">
          <span class="step-label">Catalog threshold</span>
          <h3>Solves "who owns it, where does it run"</h3>
          <p>Start a Backstage proof of concept once either condition is met: <strong>10 active consuming repositories</strong>; or at least 3 consuming repositories with <strong>2 Issues in 90 days</strong> recording an owner/service lookup that took over <strong>30 minutes</strong>. Backstage owns catalog, ownership, system relationships, and maturity visibility — it is never used to force a repository setting.</p>
        </article>
        <article class="decision-step">
          <span class="step-label">Policy threshold</span>
          <h3>Solves "settings drift and cannot be fixed back"</h3>
          <p>With at least 5 consuming repositories, evaluate central enforcement once either condition is met: the same class of drift appears in <strong>2 or more repositories</strong> within 30 days; over <strong>20%</strong> of update PRs across two consecutive template releases stay open past <strong>5 workdays</strong>; or manual <code>apply</code>/repair work exceeds <strong>2 hours a month</strong>. Allstar suits continuous checking and enforcing security policy; Safe Settings suits pushing repository settings from a hierarchical config. Neither substitutes for a catalog.</p>
        </article>
      </div>
      <aside class="selection-note"><strong>Current decision</strong><span>0 consuming repositories, and no usable drift-frequency sample, so neither threshold is met. Keep Copier, JSON policy, the GitHub API, and daily drift checks; do not pre-deploy Backstage, Allstar, or Safe Settings.</span></aside>
{{< /legacy >}}

{{< basic >}}
| Need | Quantified reevaluation threshold |
| --- | --- |
| Catalog / Backstage | Ten active consuming repositories; or at least three plus two Issues within 90 days recording owner/service lookup over 30 minutes |
| Central policy enforcement | At least five consuming repositories plus the same drift in 2+ repositories within 30 days; or 20%+ update PRs older than five workdays for two releases; or more than two manual repair hours per month |

{{< disclosure key="fleet-thresholds-yagni" title="Conditions still required after a threshold triggers" >}}
Open an evaluation Issue that names a platform owner, cost ceiling, trial scope, and exit criteria. Backstage handles catalog, ownership, and system relationships; Allstar or Safe Settings handles continuing policy checks and settings delivery. They do not substitute for each other. Until a threshold is met, keep Copier, JSON policy, GitHub API checks, and daily drift detection without prebuilding an external service.
{{< /disclosure >}}

<aside class="config-guidance"><strong>Reevaluation</strong><ul><li>Each quarter and after every new pilot, use the GitHub API to count answers/profiles, CODEOWNERS, open update PRs, and governance-drift runs.</li><li>Drift frequency only counts a consuming repository with a completed scheduled sample; a repository with no run is never counted as zero drift.</li><li>Once triggered, open a separate Issue naming a platform owner, cost ceiling, trial scope, and exit criteria; this decision does not authorize building an external service.</li></ul></aside>
<p class="bridge-reference reference">Ref. <a href="https://backstage.io/docs/features/software-catalog/" target="_blank" rel="noreferrer">Backstage Software Catalog</a>; <a href="https://github.com/ossf/allstar" target="_blank" rel="noreferrer">OpenSSF Allstar</a>; <a href="https://github.com/github-community-projects/safe-settings" target="_blank" rel="noreferrer">GitHub Safe Settings</a>. Accessed August 24, 2026.</p>
{{< /basic >}}
{{< /slide >}}

{{< slide key="spec-format" audience="archive" eyebrow="Specification format" title="Default to an Issue; create a Milestone only for an explicit story" subtitle="Keep one lightweight format instead of maintaining two systems before the need exists." class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">Decision appendix</span>
        <h2>Specification format decision｜<span class="accent">Default to a Task; create a Feature only for an explicit story</span></h2>
        <p class="subtitle">Keeps the existing lightweight front matter; <code>tracking: story</code> is an explicit opt-in, never an automatic promotion just because a spec exists or work has grown.</p>
      </header>
      <div class="decision-strip">
        <article class="decision-step">
          <span class="step-label">GitHub Spec Kit</span>
          <h3>Open-sourced 2025-09, a de facto standard within half a year</h3>
          <ul>
            <li><strong>Lifecycle:</strong> four slash commands, <code>/specify → /plan → /tasks → /implement</code>, progressively produce spec.md/plan.md/tasks.md, designed for a coding agent to execute step by step.</li>
            <li><strong>Dependency:</strong> requires installing the <code>specify</code> CLI and pairing it with a supported AI tool (Claude Code, Copilot, etc.).</li>
            <li><strong>Sync:</strong> has no built-in idempotent "one spec maps to one GitHub Issue" sync mechanism; a project must build its own.</li>
            <li><strong>Project state:</strong> <a href="https://github.com/github/spec-kit" target="_blank" rel="noreferrer">github/spec-kit</a> | MIT | public, not archived, actively maintained.</li>
          </ul>
        </article>
        <article class="decision-step recommended">
          <span class="step-label">Our decision</span>
          <h3>Keep one format, using the native Issue hierarchy</h3>
          <p><strong>Current:</strong> <code>docs/specs/*.md</code> records state in front matter; by default a <code>csarc-spec-id</code> marker syncs a Task Issue, and explicitly setting <code>tracking: story</code> syncs a Feature parent instead — both are rerunnable and never auto-split work. A Milestone is a separate delivery/release bucket with its own due date.</p>
          <p><strong>Migration cost:</strong> switching to Spec Kit would mean rewriting <code>spec_to_issue.py</code>'s parsing and sync logic, converting every existing spec, updating verification assertions, and separately designing an equivalent Issue-sync mechanism; supporting both formats at once means maintaining two systems side by side and adds cognitive load — this Issue does neither.</p>
          <p><strong>Reason:</strong> the current volume of specs is small, the existing pipeline is stable and already covered by regression tests, and Spec Kit's CLI/agent dependency has no clear payoff yet for one small template repository.</p>
          <p><strong>Reevaluation condition:</strong> revisit migration or dual-format support once native sub-issues can no longer express how work actually splits and the team is willing to maintain an additional CLI/agent workflow — consistent with the existing position on the "Step 1: define the work" page.</p>
        </article>
      </div>
{{< /legacy >}}

{{< basic >}}
| Option | Current state |
| --- | --- |
| Current `docs/specs/*.md` | Front matter records ID, priority, state, and optional tracking; markers repeatably synchronize an Issue or Milestone |
| GitHub Spec Kit | `/specify → /plan → /tasks → /implement`; requires another CLI and supported AI tool, with no built-in one-spec-to-one-Issue synchronization |

{{< disclosure key="spec-format-cost" title="Why migration is deferred and what would trigger it" >}}
Adopting Spec Kit requires rewriting `scripts/spec_to_issue.py`, converting existing specs, updating verification assertions, and designing an equivalent Issue sync. Supporting both formats adds cognitive and maintenance cost. Reevaluate when approved specifications regularly need reliable AI decomposition into several work items and the team accepts an additional CLI/agent workflow. Issue #77 closed with this decision recorded; open a new Issue if the reevaluation conditions above are met.
{{< /disclosure >}}

<aside class="config-guidance"><strong>Where this is configured</strong><ul><li><strong>Current spec format and verification:</strong> <code>docs/specs/*.md</code> + <code>scripts/spec_to_issue.py</code></li><li><strong>Decision record:</strong> <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/77" target="_blank" rel="noreferrer">Issue #77</a> (closed, decided to keep the current format)</li></ul></aside>
{{< /basic >}}
{{< /slide >}}

{{< slide key="governance-audit-trail" audience="archive" parity="new" eyebrow="Governance audit" title="Audit trail: presentation and data freshness" subtitle="The audit trail module queries GitHub live; this static site only documents the output structure and how to regenerate it, and never embeds a fetched data row." class="legacy-slide review-notes-slide" legacy="true" >}}
{{< audit-trail >}}
{{< /slide >}}
