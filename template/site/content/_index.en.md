+++
title = "[[project_name]]"

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

{{< slide key="index" track="index" eyebrow="Home" title="[[project_name]]" subtitle="[[project_description]]" class="dense" legacy="false" >}}
{{< standard key="index-mode-standard" title="This repo's current governance setup" >}}
This repo is created and kept up to date with [csarc-repo-template](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template), so its way of working can be versioned, verified, and upgraded like its code:

<div class="capability-map"><div class="capability-node"><h3>Languages</h3><p>[[languages]]</p></div><div class="capability-node"><h3>Branch strategy</h3><p>[[branch_strategy]]</p></div><div class="capability-node"><h3>Visibility</h3><p>[[project_visibility]]</p></div><div class="capability-node"><h3>Next step</h3><p>Switch to "Install" to get started, or "About" to see what this governance baseline does.</p></div></div>
{{< /standard >}}

{{< ops key="index-mode-ops" title="Where this configuration comes from" >}}
This repo's governance configuration lives in `.csarc/config.yml`, created and kept updatable by [csarc-repo-template](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template):

| Setting | Current value |
| --- | --- |
| Code owner | `[[code_owner]]` |
| Reviewers | `[[reviewers]]` |
| Branch strategy | `[[branch_strategy]]` |
| Visibility | `[[project_visibility]]` |
| Languages | `[[languages]]` |

Run `csarc status` to check whether this repo is current; when an update is available, it previews the diff before anything applies, so it never silently overwrites content already written here.
{{< /ops >}}
{{< /slide >}}

{{< slide key="install" track="install" eyebrow="Install" title="Clone this repo and you are ready to start" subtitle="The standard flow is clone, run verification once, then start changing things." class="dense" legacy="false" >}}
{{< standard key="install-mode-standard" title="Three steps to start" >}}
<div class="step-flow"><article class="step-flow-item"><span class="step-flow-number">1</span><h3>Clone</h3><p>Clone this repository to your machine.</p></article><article class="step-flow-item"><span class="step-flow-number">2</span><h3>Verify</h3><p>Run local verification once to confirm your environment is set up correctly.</p></article><article class="step-flow-item"><span class="step-flow-number">3</span><h3>Start working</h3><p>Follow the workflow on the "About" page: open an Issue before making a change.</p></article></div>

<div class="command-block"><div class="command-block-head"><span class="command-block-label">Clone command</span><button class="copy-command" type="button" data-copy-text="git clone [[repository_url]]">Copy</button></div></div>
{{< /standard >}}

{{< ops key="install-mode-ops" title="Verification command and requirements" >}}
```bash
git clone [[repository_url]]
./scripts/verify-fast
```

`scripts/verify-fast` is this repo's day-to-day PR verification entry point; run it before every push, since hosted CI no longer re-executes it and only checks the `Verified-locally:` attestation it leaves on success. Only a Milestone/canary delivery, a hotfix, or the merge queue needs the full `scripts/verify-template.sh`. Local requirements (language toolchains, `gh` login, and so on) depend on which languages this repo uses ([[languages]]); see the README for detail.
{{< /ops >}}
{{< /slide >}}

{{< slide key="about" track="about" eyebrow="About" title="This repo is governed with csarc-repo-template" subtitle="Its way of working can be versioned, verified, and upgraded like its code -- not just a one-shot file generator." class="dense single-column" legacy="false" >}}
{{< standard key="about-mode-standard" title="What this governance baseline keeps doing" >}}
<div class="capability-map"><div class="capability-node"><h3>Every piece of work is one Issue</h3><p>States what to do and what "done" means; the change happens on its own branch so work never collides.</p></div><div class="capability-node"><h3>Every change goes through review</h3><p>Automated checks run first, then a person reviews the PR; nothing reaches the main branch without both.</p></div><div class="capability-node"><h3>Template updates preview first</h3><p>When `csarc-repo-template` has an update, you review the diff before it applies.</p></div><div class="capability-node"><h3>Routine security checks run alone</h3><p>Package versions and known vulnerabilities are checked on a schedule; you only step in on a real conflict.</p></div></div>
{{< /standard >}}

{{< ops key="about-mode-ops" title="How the governance baseline works" >}}
This repo's governance rules live in three places, each with a distinct role: `AGENTS.md` (the rules an agent and a person both follow), `policies/*.json` (the GitHub settings this repo expects), and `.csarc/config.yml` (this project's actual choices):

- **`AGENTS.md`:** an agent always reads this before starting work; the equivalent guidance for human contributors is in the README.
- **`policies/*.json`:** expected settings (branch protection, required checks, labels) applied and verified by `scripts/apply-repository-settings.sh`.
- **`.csarc/config.yml`:** this repo's actual choices (languages, branch strategy, code owner, and so on), kept in sync with template updates via `csarc update` while this file's own project content is preserved.

This site is itself an example of the same principle: `docs/index.html` embeds every style and script, so it opens offline once downloaded, with no separate hosting needed.
{{< /ops >}}
{{< /slide >}}
