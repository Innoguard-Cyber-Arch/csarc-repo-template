# Install

CSARC delivers a CI/CD template and governance workflow; Python only runs the thin init/adopt/update CLI. `uvx --python 3.14` acquires an isolated runtime per invocation, so nothing needs a pre-installed or globally maintained Python. Run this from WSL2 on Windows.

## Prerequisites

Git, GitHub CLI 2.93.0 or newer, and `uv` are always required; the language modules you choose need their own toolchain. Selecting none of `languages` (`language: ci`) needs no extra language toolchain at all.

| Tool | When needed | macOS (Homebrew) | Windows (native, winget/Chocolatey) | Linux/WSL2 (Ubuntu, apt) |
| --- | --- | --- | --- | --- |
| Git | Always | `brew install git` | `winget install --id Git.Git -e` | `sudo apt install -y git` |
| GitHub CLI (`gh`) 2.93.0+ | Always required by the csarc CLI; run `gh auth login` after installation | `brew install gh` | `winget install --id GitHub.cli --source winget` | Use the [official GitHub apt repository](https://github.com/cli/cli/blob/trunk/docs/install_linux.md#debian), not Ubuntu's bundled package |
| uv | Always | `brew install uv` | `winget install --id=astral-sh.uv -e` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js 24+ | Only with the `typescript` module | `brew install node` | `winget install --id OpenJS.NodeJS.LTS -e` | `curl -fsSL https://deb.nodesource.com/setup_24.x \| sudo -E bash -` then `sudo apt install -y nodejs` |
| pnpm 11 | Only with the `typescript` module | `brew install pnpm` | `winget install -e --id pnpm.pnpm` | `sudo npm install -g pnpm@11` |
| rustup/Cargo | Only with the `rust` module; **Linux/WSL2 also needs `build-essential` (a system C linker)** | `brew install rustup` | `winget install -e --id Rustlang.Rustup` | `sudo apt install -y build-essential` then `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| Go 1.27.1 | Only with the `go` module; the generated verifier requires exactly go1.27.1 | Install the `go1.27.1` macOS `.pkg` from the [official Go downloads page](https://go.dev/dl/); do not use `brew install go`, which installs the newest Go rather than the pinned version | Inside WSL2, use the Linux/WSL2 column | Per the [official Go install guide](https://go.dev/doc/install): `curl -LO https://go.dev/dl/go1.27.1.linux-amd64.tar.gz && sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go1.27.1.linux-amd64.tar.gz`, then add `/usr/local/go/bin` to `PATH` |

The Windows column is for installing an individual tool natively on Windows (e.g. installing `git`/`gh` before entering WSL2); inside the WSL2 Ubuntu shell, use the Linux/WSL2 column instead -- the rustup installed via winget is not on `PATH` there. Go is installed only inside WSL2; there is no native Windows path. Inside WSL2, install `gh` from GitHub's official apt repository and confirm `gh --version` is at least 2.93.0; Ubuntu's bundled package is too old for the required Release verification. Choosing Rust also needs `build-essential` (a system C linker) on Linux/WSL2 -- true even for a pure-Rust project with no C bindings; without it, `cargo test` fails at compile time with `error: linker 'cc' not found`.

## Create a new repo

```bash
uvx --python 3.14 --from 'git+https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git@<approved-full-commit-sha>' csarc init ./my-project
```

## Adopt an existing repo

```bash
git switch -c chore/<issue-number>-adopt-csarc-template
uvx --python 3.14 --from 'git+https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git@<approved-full-commit-sha>' csarc adopt
```

`adopt` defaults to a dry run: it only produces a machine-readable plan, the report JSON that is the only source, and the Markdown adoption report rendered from it ([SPEC-008](specs/SPEC-008-lifecycle-report-format.md)) outside the repo, without modifying it. Apply with `--apply-plan` only after confirming.

## Update an adopted repo

`csarc update` is the only update entry point; running `copier update` directly is unsupported. Below, `csarc` stands for `uvx --python 3.14 --from 'git+https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git@<approved-full-commit-sha>' csarc`, `<tag>` and `<full-sha>` are the approved Release tag and full commit SHA, and `<repo>` is the target folder name. Run these in a clean clone of the target:

```bash
git switch -c chore/<issue-number>-update-repo-template
csarc status . --to <tag> --expected-sha <full-sha> --json
csarc update . --to <tag> --expected-sha <full-sha> --check --json
csarc update . --to <tag> --expected-sha <full-sha> --finalize-plan --decision <path>=keep-current
csarc update . --apply-plan ../<repo>-csarc-update-report/csarc-update-final-plan.json --yes
./.csarc/scripts/verify-fast
```

1. **`status`**: when it reports `update`, follow `next_command`; it already carries `--to` and `--expected-sha`. A beta or a pinned release always needs both flags; without them the CLI selects the latest stable release.
2. **`--check`**: changes nothing in the target and writes the stage-1 plan (`csarc-update-plan.json`), the report JSON, and the Markdown report to `../<repo>-csarc-update-report/`. It exits 1 when an update is available, 0 when current, and 2 on an error. The report's `Items requiring your decision` lists what to handle. A `--data` value that confirms what the CLI would derive anyway (for example `release_ownership`) produces exactly the same plan as passing nothing. When the report's Settings show a `widened` row (for example `admin_bypass`), the owner must decide it explicitly before `--finalize-plan`; see "Widened settings" below. For `setting-decision` rows (for example `release_ownership` or `project_run_command`), see "Setting decisions" below.
3. **Read each conflict**: every `file-conflict` has three files under the report folder's `conflicts/`: `conflicts/base/<path>` (the recorded release's render), `conflicts/current/<path>` (the target's current content, which `keep-current` records), and `conflicts/new/<path>` (the new release rendered with the same settings, which `take-new` records). A missing file means that side has none. Jinja templates are already rendered, so there is no need to read template source or try an apply. `conflicts/` is rewritten on every plan.
4. **`--finalize-plan`**: writes the immutable `csarc-update-final-plan.json` in one run.
   - Repeat every `--to`, `--expected-sha`, `--data`, and `--report-dir` used for `--check`, plus `--from-release`, `--accept-legacy`, and `--allow-unreleased`. The CLI plans again and compares with the stage-1 plan; any different input stops and asks for a new `--check`. It cannot be combined with `--check`, `--json`, or `--dry-run`.
   - Give exactly one `--decision <path>=keep-current|take-new|custom:<file>` per `update-conflict`; a missing, duplicate, or unplanned path stops. Without conflicts, pass no `--decision`.
   - `custom:<file>` is the **complete final content** of that path, not a patch. `<file>` is absolute or relative to the directory you run the command from, must be a regular file outside the target repository (not a symlink), and must not contain conflict markers. Its content is copied into the final plan, so later edits to `<file>` do not change a written plan. Do not keep it under `conflicts/`, which every plan rewrites.
   - The target must be a clean working tree. Commit each product preparation change this page asks for (for example the product job move, Action pins, or ignore exceptions below) as its own product preparation commit before `--finalize-plan`, then run `--check` again; list those commits and the sections they follow in the PR.
   - A `.gitignore` conflict row lists the ignore rules the new release has and the current file lacks; when you keep the product `.gitignore` with `keep-current` or a `custom:<file>` built from it, see "`.gitignore` missing template rules" below.
   - When product ignore rules (for example `data/` in `.gitignore`) would hide files the new release delivers, `--check` lists a blocking `file-conflict` whose subject is that ignore file and whose message names the hidden paths and rules. Add exceptions (for example `!.csarc/site/data/`) to that ignore file: in its `custom:<file>` decision when it is itself a conflict, otherwise in a product commit followed by a new `--check`. `--finalize-plan` checks the decided content again and refuses decisions that still hide a file.
   - `--finalize-plan` refuses a decision that keeps a reference from a kept file to a file this update retires; use `take-new` or `custom`, or remove the reference in the product first.
5. **`--apply-plan`**: takes only the final plan path and rejects input-changing flags such as `--to`, `--data`, or `--decision`; `--report-dir` may only name the final plan's folder. Without `--yes` it shows the plan and asks `Apply this plan? [y/N]`; agents and runs without terminal input pass `--yes`. Before writing it re-observes the toolchain and live facts; any difference or verification failure stops before a write and leaves the target unchanged; a verification failure names the failed verify step and its reason (`Project verification failed: ...`).
6. **Commit and verify**: after a successful apply, review the diff, commit it on the same branch, then run `./.csarc/scripts/verify-fast` and the product's own checks on that committed, clean head (local results bind to the exact head; an uncommitted result is not evidence), and finally open a PR.

### Retry after a failure

A final plan is immutable; do not delete or edit it. To decide again (for example after apply verification failed, live facts changed, or you changed product files), keep the old folder and rerun in a new report folder:

```bash
csarc update . --to <tag> --expected-sha <full-sha> --check --json --report-dir ../<repo>-csarc-update-report-2
csarc update . --to <tag> --expected-sha <full-sha> --finalize-plan --decision <path>=keep-current --report-dir ../<repo>-csarc-update-report-2
csarc update . --apply-plan ../<repo>-csarc-update-report-2/csarc-update-final-plan.json --yes
```

The old final plan stays as a record; replaying a final plan that is already applied reports that and exits 0 without changing a file.

### Action pin drift

`--check` compares product-owned workflow Action pins with the new template pins, read-only, and lists each item in the plan's `action_pin_preflight` and the report's `product.action_pins`. `product-pin-newer` (the product pin is newer within the same major) does not block, and the CLI aligns the template workflows to the product pin; every other reason creates a blocking `action-pin`. A blocking row's message names the product and template pin release tags (read from the `# vX.Y.Z` comment after each pin) and `major upgrade: yes|no|unknown`: `yes` is a cross-major upgrade, so read the upstream changes first; `unknown` means a side has no tag or a non-version tag, so look up the tag for that SHA upstream before deciding. There is one rule: `--pin-commit` is required only when the stage-1 plan being finalized still lists blocking pin drift, and it is rejected when that plan lists none. The standard path is therefore:

1. Update the pins in the product workflow in one commit that changes only those pins (it may be a major upgrade; read the upstream changes first).
2. Run `--check` again; the new stage-1 plan no longer lists those pins.
3. Run `--finalize-plan` as usual, without `--pin-commit`.

To keep the stage-1 plan created before that commit instead, add `--pin-commit <full SHA of the pin commit>` to `--finalize-plan`; the CLI reads the pins back from that commit and stops when it changes a pin outside the list. An unreachable or untrusted template source always stops without writing the target.

### A template workflow conflict that contains product jobs

When an older template workflow (for example `.github/workflows/ci.yml`) gained product jobs and the new release rewrites that workflow, it conflicts: `take-new` drops the product jobs, `keep-current` keeps an old workflow that calls removed scripts, and merging the jobs into the new `pull_request_target` workflow changes which code they check. The standard handling:

1. Before the update, move the product jobs unchanged into a product-owned workflow (for example `.github/workflows/product-ci.yml`) in a separate product commit, keeping their original triggers.
2. Run `--check` again and decide that template workflow's conflict with `take-new`.
3. The moved jobs now belong to a product workflow and enter the Action pin comparison; handle any new blocking `action-pin` as in the previous section.

### Other conflicts and coexisting files

Ownership follows handbook 5.1: workflows, the `AGENTS.md` managed block, and `.claude/CLAUDE.md` belong to the template; `.gitignore` is co-maintained; product code and documentation content belong to the project.

- **A template workflow with a local fix that is not a product job**: compare `conflicts/base/<path>` with `conflicts/current/<path>`; the difference is the local change. If it contains product jobs, follow the previous section. If it only patches template behavior (for example a guard that skips a missing checker in the old release, or a workaround for an old bug), choose `take-new`: the file belongs to the template and the new release replaces that behavior, while `keep-current` keeps an old workflow that calls removed scripts. Read `conflicts/new/<path>` first; when the new release still lacks the same fix, still do not keep a modified template workflow: choose `take-new` and report it in an Issue on the template repository. Example: the old `governance-comment.yml` only gained a "skip when the checker is missing" guard and the new release rewrites the file as reviewer assignment, so the decision is `take-new`.
- **`AGENTS.md` without a CSARC managed block**: the part from `<!-- BEGIN CSARC MANAGED BLOCK -->` to `<!-- END CSARC MANAGED BLOCK -->` belongs to the template; text outside it belongs to the project. Use `custom:<file>`: the whole current file unchanged, then a blank line and the complete managed block from `conflicts/new/AGENTS.md`, the same layout `adopt` writes. When the current file already has one managed block, replace only that block with the new one. Do not use `take-new` (it drops the product guidance) or `keep-current` (it lacks the CSARC entry point). Example (run in the target root, then decide with `--decision AGENTS.md=custom:../AGENTS.custom.md`):

  ```bash
  report=../<repo>-csarc-update-report
  { cat AGENTS.md; echo; sed -n '/<!-- BEGIN CSARC MANAGED BLOCK -->/,/<!-- END CSARC MANAGED BLOCK -->/p' "$report/conflicts/new/AGENTS.md"; } > ../AGENTS.custom.md
  ```

- **A root `CLAUDE.md` next to `.claude/CLAUDE.md`**: `.claude/CLAUDE.md` belongs to the template and only imports `AGENTS.md`; `AGENTS.md` is the single source of AI instructions. When the update lists the old root `CLAUDE.md` as `retire-modified`, it is only a kept legacy file that CSARC no longer reads or updates. Claude Code may load both files; when they disagree, `AGENTS.md` wins. Move the product guidance you still need from the root `CLAUDE.md` into `AGENTS.md` outside the managed block, point product documents that rely on the root `CLAUDE.md` to `AGENTS.md`, then delete the root `CLAUDE.md` in a separate commit.
- **Product rows in `.github/pull_request_template.md`**: the PR template belongs to the template (handbook 5.1), but a product may have added its own checklist rows to the old version. Compare `conflicts/base/<path>` with `conflicts/current/<path>`; the difference is the rows the product added. Use `custom:<file>`: start from the full text of `conflicts/new/.github/pull_request_template.md`, put the product rows back unchanged in the section they came from (for example at the end of `## 完成清單`), and leave every template row as it is. Do not use `keep-current` (it keeps the old template text and misses the new sections and wording); use `take-new` when the product no longer needs those rows. List the restored rows in the PR. Whenever a later release changes the PR template, this file conflicts again; handle it the same way.
- **`.gitignore` missing template rules**: `.gitignore` is co-maintained, and its conflict row ends with the ignore rules the new release has and the current file lacks (`The current file lacks these template ignore rules ...`). `keep-current` leaves them out; a `custom:<file>` built from the current file must add the ones the project needs. The usual one is `dist/`: `./.csarc/scripts/verify-fast` writes `dist/repo-site/`, so without that rule the working tree is dirty after verify. When you deliberately leave a rule out, say why in the PR. After apply and verify, check `git status`; add a rule in a separate commit for any new untracked output.

### Product-owned workflow audits

The new template's `ci.yml`, `pr-policy.yml`, `pr-review.yml`, `pr-policy-writes.yml`, `governance-comment.yml`, `dependabot-auto-merge.yml`, and `dependabot-merge.yml` use `pull_request_target` or `workflow_run` on purpose. The trust boundary:

- `pull_request_target` loads the required-check, reviewer-assignment, and Dependabot-sync workflow definitions from the trusted base, so a PR cannot rewrite the code that checks it. PR policy and review check out only the trusted base with read-only permissions; reviewer assignment checks out only the base and calls the API only after the PR author and number pass strict format checks; the Dependabot sync first authenticates the GitHub-signed Dependabot head and its workflow-only diff, runs only the base's synchronizer, and pushes with an exact-SHA lease. CI reads the proposed head to verify it but has no secrets or write permissions.
- `workflow_run` keeps governance writes and the Dependabot merge in a default-branch workflow; it checks out only the default-branch commit, never the triggering head or its artifacts, uses only GitHub-supplied PR numbers and head SHAs as data, and re-verifies the exact head before writing.
- The template repository audits the same workflows with zizmor and records the reason for each `dangerous-triggers` exception in the template repository's root `zizmor.yml`.

When the product runs zizmor or a similar audit itself, these workflows report high `dangerous-triggers` findings and the audit may turn from green to red. That is not an update failure; CSARC does not change the product's audit configuration or add ignores for it. The product owner chooses one of these options; an agent only lists the before and after audit results and the options in the PR:

1. Scope the product audit to the product's own workflows (for example `.github/workflows/product-ci.yml`); per handbook 5.1 the template workflows belong to the template and change with the approved Release.
2. After reading the trust boundary above, add `dangerous-triggers` exceptions for these template workflows to the product's audit configuration, each with its reason, in a separate product commit.
3. Keep the update PR unmerged until the owner decides. Do not change the template workflows' triggers to turn the audit green.

### Widened settings

A Settings row whose class is `widened` means the governance scope is wider than before, and Impact analysis also lists `Widened settings`. Today only `admin_bypass` can be widened: legacy settings without the key migrate to `always` (an admin may replace peer approval with an exact-head authorization for beta and stable work), and the row's note names the earlier scope. The row does not make `--check` blocking, but the owner must decide it explicitly before `--finalize-plan`; an agent must not accept it on the owner's behalf:

1. Accept the wider scope: run `--check` again with `--data admin_bypass=always`; the row becomes an explicit choice (`decision`, or `exact` when the earlier scope was already `always`).
2. Keep the earlier scope: run `--check` again with `--data admin_bypass=<the value in the note>` (`off` or `beta-only`); the row becomes `exact`.

Repeat the same `--data` for `--finalize-plan`, and record the owner's decision in the PR. Recovery: to go back after `always` was already applied, plan again on a new branch, then finalize and apply as usual; after the push the owner runs the repository settings `plan`, reviews it, and runs `apply` so the Ruleset returns to the earlier scope as well.

```bash
csarc update . --to <tag> --expected-sha <full-sha> --check --json --data admin_bypass=beta-only --report-dir ../<repo>-csarc-update-report-2
csarc update . --to <tag> --expected-sha <full-sha> --finalize-plan --data admin_bypass=beta-only --decision <path>=keep-current --report-dir ../<repo>-csarc-update-report-2
csarc update . --apply-plan ../<repo>-csarc-update-report-2/csarc-update-final-plan.json --yes
```

Replace `beta-only` with the value in the note; give `--decision` for that report's conflicts as usual, and none when there are no conflicts.

### Setting decisions (`setting-decision`)

A `setting-decision` row under the report's `Items requiring your decision` does not make `--check` blocking, but handle every row before `--finalize-plan`: accept the reported value, or run `--check` again with an explicit `--data <key>=<value>` as described below, and repeat the same `--data` for `--finalize-plan`. For the `reviewers` row, see "Reviewer assignment changes" below.

**`release_ownership`** decides who owns versions and GitHub Releases; it is an owner decision. Its Settings row shows the previous value and the value this plan uses, and the `setting-decision` row asks you to confirm the new value or pass the one to keep. The two options:

1. `product-owned`: the product's own Release workflow (for example a release-please setup the product maintains) keeps owning versions and Releases; CSARC only reports drift. Choose it when the product maintains a writer it wants to keep using.
2. `csarc-owned`: CSARC's `release.yml` and version policy own versions, the CHANGELOG, and Releases; `version.txt` and the CHANGELOG keep their current values. Choose it when the old Release workflow was generated by an older template, the product has no release process of its own, or the owner wants CSARC to publish.

If `--check` lists a blocking `release-writer` after you choose `product-owned`, the kept writer uses files this update moves into `.csarc/` (the message lists each `old path -> new path`), and `--finalize-plan` refuses. Only two ways remain: choose `csarc-owned`, or first change the writer in a product preparation commit so it no longer uses those paths and run `--check` again; the latter adds a product diff. The agent records the choice, the reason under the rules above, and the `release-writer` message in the PR, and the owner confirms it before merge. Use `verification-only` (CSARC verifies but does not manage releases) only when the owner asks for it.

**`project_run_command`** is the product's shortest start or invoke command (`package_name` follows the same rule). When the CLI can derive it uniquely from the native manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`), it is not saved; the value an update uses lives in the render context of `.csarc/provenance.json`, and `.csarc/config.yml` does not list it. When the derived value differs from the recorded one, or cannot be derived uniquely, the report lists a `setting-decision` and the recorded value is kept:

- Pass no `--data`: the recorded value stays, and the product's behavior does not change.
- To use another command, decide it explicitly with `--data project_run_command=<command>`. The value is written to `.csarc/config.yml`, and every later update uses it instead of deriving one from the manifests.

### Reviewer assignment changes (`reviewers`)

The legacy `reviewers` setting and `.github/REVIEWERS` are retired: the Settings row stays `retired`, and its note names the earlier reviewers, the new assignment, and how to restore it; `Items requiring your decision` adds one non-blocking `setting-decision` row (subject `reviewers`). The new release requests one reviewer per ready pull request, by rotation, from the collaborators with maintain or admin permission other than the author. Like a `widened` row, it does not make `--check` blocking, but the owner must confirm it before `--finalize-plan`; an agent must not accept it on the owner's behalf. To keep the earlier reviewers, give maintain or admin permission only to them, or name them as code owners with `--data code_owner=<owners>` so GitHub requests their review on every pull request; record the owner's decision in the PR.

### README and LICENSE in an existing repo

An existing repo (`project_mode=existing`) owns its README and LICENSE (handbook 5.1 and appendix B.9). The update adds no `README.md`, `README.en.md`, `README.zh-tw.md`, or `LICENSE`, and never rewrites the ones the repo has.

- No `LICENSE`: the report's Settings show `project_license` as `custom` and an empty `copyright_holder`; the product manages its license, and no copyright holder is inferred from the project name. Verify accepts the missing `LICENSE` because provenance records `custom`.
- An existing `LICENSE`: the file is kept, whether or not it is a CSARC starter text.
- To have CSARC add a starter `LICENSE`, the owner passes both `--data project_license=<proprietary|MIT|Apache-2.0>` and `--data copyright_holder=<legal holder>` to `--check` and `--finalize-plan`; with a license but no holder, the update stops before any write. The product can also add its own `LICENSE` in a product commit.

### Kept legacy files and stale links

- Files still in use: a file the new release no longer renders is kept as `preserve`/`product-owned` instead of being deleted when a kept file references it by full path or when it is a configuration a tool reads automatically (`zizmor.yml`, `.gitleaks.toml`, `.pre-commit-config.yaml`); the product maintains it from then on. A script moved to `.csarc/scripts/` that product files still call by its old path leaves a forwarding wrapper there (`overwrite`/`compatibility-shim`). When the product's own Release writer (`release_ownership=product-owned`) still uses files this update moves into `.csarc/` (for example a release-please config, its manifest, and the `version.txt` it implies), the plan lists a blocking `release-writer` and `--finalize-plan` refuses to write; plan with `--data release_ownership=csarc-owned`, or first change the writer in a product commit so it no longer uses those paths, then run `--check` again. See "Setting decisions" for how to choose.
- `retire-modified`: a file the new release no longer renders but whose content differs from the old render (for example the root `scripts/verify`) stays in place, and the new version lives in `.csarc/scripts/`. CSARC no longer calls or updates the kept file; once no product file, document, or workflow references it, delete it in a separate commit so nobody uses the old copy by mistake. A kept script that still runs or reads a file the same plan removes or moves (for example a kept `scripts/verify` that calls the removed `scripts/test-pr-policy` or reads `policies/*.json`, which moves to `.csarc/policies/`) would fail after the apply: its `retire-modified` row becomes blocking and lists each used path. No product commit is needed: add `--decision scripts/verify=take-new` to `--finalize-plan` to retire the legacy script as the new release does (the new version lives in `.csarc/scripts/`). A `retire-modified` path takes only `take-new`; without it the file is kept and `--finalize-plan` refuses to write. `--finalize-plan` also refuses when another file the plan keeps (for example a product workflow or another kept legacy script) still calls the retired file; retire that legacy script too. To keep the script instead, change it in a product commit so it no longer uses these paths (for example, call the `.csarc/scripts/` version), then run `--check` again.
- Moves: the report's `move` rows list the paths the update moves (for example `CLAUDE.md` to `.claude/CLAUDE.md`, or `scripts/` to `.csarc/scripts/`). A product document kept with `keep-current` or `custom` (for example `docs/README.md`) may still link the old paths; after apply, search for each old path from the `move` rows and fix the links in a separate commit.
- Site content: the project-maintained `docs/site/content/`, `docs/site/data/navigation.json`, and `docs/site/theme.css` are kept byte-identical; their legacy locations `site/content/`, `site/data/navigation.json`, and `docs/site-theme.css` move there as `move` rows, and `docs/index.html`/`docs/index.en.html` are rebuilt from the kept content.
- `docs/README.md` is the project's own documentation entry point and can be kept with `keep-current`; the CSARC documentation map lives in `.csarc/docs/documentation-policy.md`, which is what verify checks.

### Messages printed by apply

- `CODEOWNERS validation failed: ... is missing, invisible, or lacks repository access`: the CODEOWNERS team does not exist, is not visible, or lacks repository access. The update is complete; the owner grants the team access or later updates it with `--data code_owner=...`.
- Repository settings: update only runs `.csarc/scripts/apply-repository-settings.sh plan` and never applies settings. It prints `Repository settings plan needs a GitHub origin remote` only when origin is not a GitHub repository; any other failure prints `Repository settings plan failed (exit N): <reason>`, for example a CODEOWNERS validation failure. After the push, the owner runs `plan`, reviews it, then runs `apply`.

### Parallel runs

Run one `csarc` command at a time per machine. Two concurrent `csarc` runs interfere in Copier's shared git cache and give unreliable results; update several repositories one after another.

## Not sure of the current state?

Start with auto-detection: `csarc status` reads only local files and, if already adopted, the template version and repository settings on GitHub, then classifies the repository into one of seven states: `create`/`adopt`/`adoption-pending`/`migrate`/`update`/`current`/`policy-only-update`. Follow the returned `next_command`. `adoption-pending` means the local checkpoint is valid but adoption still needs `csarc adopt <path> --finalize`; `migrate` means existing Copier answers use a release tag or short SHA and must be reviewed and bound to a verified Release's full SHA. A raw `copier update` (answers `_commit` differs from provenance, or `.rej` files remain) is also reported as `migrate`; that is a detection, not a completed migration, so restore the files and use `csarc update`. The pinned agent install contract lives at [`docs/agent-install.md`](agent-install.md).

## Full detail

For how `<approved-full-commit-sha>` is obtained, required inputs like `project_description`/`copyright_holder`/`security_reporting_channel` and the work mode ([SPEC-009 §9](specs/SPEC-009-project-settings.md)), the manual-merge list for an existing-repo adoption, conflict handling, and troubleshooting, see the root [`README.md`](../README.md#quick-start)'s "Quick start" and "Template updates" sections, and the real adoption evidence in [`docs/pilot-adoption.md`](pilot-adoption.md). For the "why" behind these choices, read the [repo-site](index.en.html).
