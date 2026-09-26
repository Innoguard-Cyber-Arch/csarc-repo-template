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

`adopt` defaults to a dry run: it only produces a Markdown adoption report and a machine-readable plan outside the repo, without modifying it. Apply with `--apply-plan` only after confirming.

## Update an adopted repo

```bash
git switch -c chore/<issue-number>-update-repo-template
uvx --python 3.14 --from 'git+https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git@<approved-full-commit-sha>' csarc update --check --json
```

## Not sure of the current state?

Start with auto-detection: `csarc status` reads only local files and, if already adopted, the template version and repository settings on GitHub, then classifies the repository into one of seven states: `create`/`adopt`/`adoption-pending`/`migrate`/`update`/`current`/`policy-only-update`. Follow the returned `next_command`. `adoption-pending` means the local checkpoint is valid but adoption still needs `csarc adopt <path> --finalize`; `migrate` means existing Copier answers use a release tag or short SHA and must be reviewed and bound to a verified Release's full SHA. The pinned agent install contract lives at [`docs/agent-install.md`](agent-install.md).

## Full detail

For how `<approved-full-commit-sha>` is obtained, required fields like `project_description`/`project_run_command`/`security_reporting_channel`, the manual-merge list for an existing-repo adoption, conflict handling, and troubleshooting, see the root [`README.md`](../README.md#quick-start)'s "Quick start" and "Template updates" sections, and the real adoption evidence in [`docs/pilot-adoption.md`](pilot-adoption.md). For the "why" behind these choices, read the [repo-site](index.en.html).
