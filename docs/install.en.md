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
2. **`--check`**: changes nothing in the target and writes the stage-1 plan (`csarc-update-plan.json`), the report JSON, and the Markdown report to `../<repo>-csarc-update-report/`. It exits 1 when an update is available, 0 when current, and 2 on an error. The report's `Items requiring your decision` lists what to handle. A `--data` value that confirms what the CLI would derive anyway (for example `release_ownership`) produces exactly the same plan as passing nothing.
3. **Read each conflict**: every `file-conflict` has three files under the report folder's `conflicts/`: `conflicts/base/<path>` (the recorded release's render), `conflicts/current/<path>` (the target's current content, which `keep-current` records), and `conflicts/new/<path>` (the new release rendered with the same settings, which `take-new` records). A missing file means that side has none. Jinja templates are already rendered, so there is no need to read template source or try an apply. `conflicts/` is rewritten on every plan.
4. **`--finalize-plan`**: writes the immutable `csarc-update-final-plan.json` in one run.
   - Repeat every `--to`, `--expected-sha`, `--data`, and `--report-dir` used for `--check`, plus `--from-release`, `--accept-legacy`, and `--allow-unreleased`. The CLI plans again and compares with the stage-1 plan; any different input stops and asks for a new `--check`. It cannot be combined with `--check`, `--json`, or `--dry-run`.
   - Give exactly one `--decision <path>=keep-current|take-new|custom:<file>` per `update-conflict`; a missing, duplicate, or unplanned path stops. Without conflicts, pass no `--decision`.
   - `custom:<file>` is the **complete final content** of that path, not a patch. `<file>` is absolute or relative to the directory you run the command from, must be a regular file outside the target repository (not a symlink), and must not contain conflict markers. Its content is copied into the final plan, so later edits to `<file>` do not change a written plan. Do not keep it under `conflicts/`, which every plan rewrites.
   - The target must be a clean working tree: commit product preparation and pin changes first.
   - When product ignore rules (for example `data/` in `.gitignore`) would hide files the new release delivers, `--check` lists a blocking `file-conflict` whose subject is that ignore file and whose message names the hidden paths and rules. Add exceptions (for example `!.csarc/site/data/`) to that ignore file: in its `custom:<file>` decision when it is itself a conflict, otherwise in a product commit followed by a new `--check`. `--finalize-plan` checks the decided content again and refuses decisions that still hide a file.
   - `--finalize-plan` refuses a decision that keeps a reference from a kept file to a file this update retires; use `take-new` or `custom`, or remove the reference in the product first.
5. **`--apply-plan`**: takes only the final plan path and rejects input-changing flags such as `--to`, `--data`, or `--decision`; `--report-dir` may only name the final plan's folder. Without `--yes` it shows the plan and asks `Apply this plan? [y/N]`; agents and runs without terminal input pass `--yes`. Before writing it re-observes the toolchain and live facts; any difference or verification failure stops before a write and leaves the target unchanged; a verification failure names the failed verify step and its reason (`Project verification failed: ...`).
6. **Commit and verify**: after a successful apply, review the diff, commit it on the same branch, run `./.csarc/scripts/verify-fast` and the product's own checks, then open a PR.

### Retry after a failure

A final plan is immutable; do not delete or edit it. To decide again (for example after apply verification failed, live facts changed, or you changed product files), keep the old folder and rerun in a new report folder:

```bash
csarc update . --to <tag> --expected-sha <full-sha> --check --json --report-dir ../<repo>-csarc-update-report-2
csarc update . --to <tag> --expected-sha <full-sha> --finalize-plan --decision <path>=keep-current --report-dir ../<repo>-csarc-update-report-2
csarc update . --apply-plan ../<repo>-csarc-update-report-2/csarc-update-final-plan.json --yes
```

The old final plan stays as a record; replaying a final plan that is already applied reports that and exits 0 without changing a file.

### Action pin drift

`--check` compares product-owned workflow Action pins with the new template pins, read-only, and lists each item in the plan's `action_pin_preflight` and the report's `product.action_pins`. `product-pin-newer` (the product pin is newer within the same major) does not block, and the CLI aligns the template workflows to the product pin; every other reason creates a blocking `action-pin`. There is one rule: `--pin-commit` is required only when the stage-1 plan being finalized still lists blocking pin drift, and it is rejected when that plan lists none. The standard path is therefore:

1. Update the pins in the product workflow in one commit that changes only those pins (it may be a major upgrade; read the upstream changes first).
2. Run `--check` again; the new stage-1 plan no longer lists those pins.
3. Run `--finalize-plan` as usual, without `--pin-commit`.

To keep the stage-1 plan created before that commit instead, add `--pin-commit <full SHA of the pin commit>` to `--finalize-plan`; the CLI reads the pins back from that commit and stops when it changes a pin outside the list. An unreachable or untrusted template source always stops without writing the target.

### A template workflow conflict that contains product jobs

When an older template workflow (for example `.github/workflows/ci.yml`) gained product jobs and the new release rewrites that workflow, it conflicts: `take-new` drops the product jobs, `keep-current` keeps an old workflow that calls removed scripts, and merging the jobs into the new `pull_request_target` workflow changes which code they check. The standard handling:

1. Before the update, move the product jobs unchanged into a product-owned workflow (for example `.github/workflows/product-ci.yml`) in a separate product commit, keeping their original triggers.
2. Run `--check` again and decide that template workflow's conflict with `take-new`.
3. The moved jobs now belong to a product workflow and enter the Action pin comparison; handle any new blocking `action-pin` as in the previous section.

### Kept legacy files and stale links

- Files still in use: a file the new release no longer renders is kept as `preserve`/`product-owned` instead of being deleted when a kept file references it by full path or when it is a configuration a tool reads automatically (`zizmor.yml`, `.gitleaks.toml`, `.pre-commit-config.yaml`); the product maintains it from then on. A script moved to `.csarc/scripts/` that product files still call by its old path leaves a forwarding wrapper there (`overwrite`/`compatibility-shim`).
- `retire-modified`: a file the new release no longer renders but whose content differs from the old render (for example the root `scripts/verify`) stays in place, and the new version lives in `.csarc/scripts/`. CSARC no longer calls or updates the kept file; once no product file, document, or workflow references it, delete it in a separate commit so nobody uses the old copy by mistake.
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
