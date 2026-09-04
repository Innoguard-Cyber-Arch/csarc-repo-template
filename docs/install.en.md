# Install

CSARC delivers a CI/CD template and governance workflow; Python only runs the thin init/adopt/update CLI. `uvx --python 3.14` acquires an isolated runtime per invocation, so nothing needs a pre-installed or globally maintained Python. Run this from WSL2 on Windows.

## Prerequisites

Only `uv` is always required; the language modules you choose need their own toolchain. Selecting none of `languages` (`language: ci`) needs no extra language toolchain at all.

| Tool | When needed | macOS (Homebrew) | Windows (winget/Chocolatey) |
| --- | --- | --- | --- |
| Git | Always | `brew install git` | `winget install --id Git.Git -e` |
| GitHub CLI (`gh`) | Only for GitHub-connected operations | `brew install gh` | `winget install --id GitHub.cli --source winget` |
| uv | Always | `brew install uv` | `winget install --id=astral-sh.uv -e` |
| Node.js 24+ | Only with the `typescript` module | `brew install node` | `winget install --id OpenJS.NodeJS.LTS -e` |
| pnpm 11 | Only with the `typescript` module | `brew install pnpm` | `winget install -e --id pnpm.pnpm` |
| rustup/Cargo | Only with the `rust` module | `brew install rustup` | `winget install -e --id Rustlang.Rustup` |

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

Start with auto-detection: `csarc status` reads only local files and, if already adopted, the template version and repository settings on GitHub, then classifies the repository into one of `create`/`adopt`/`update`/`current`/`policy-only-update`, and follows the returned `next_command`. The pinned agent install contract lives at [`docs/agent-install.md`](agent-install.md).

## Full detail

For how `<approved-full-commit-sha>` is obtained, required fields like `project_description`/`project_run_command`/`security_reporting_channel`, the manual-merge list for an existing-repo adoption, conflict handling, and troubleshooting, see the root [`README.md`](../README.md#quick-start)'s "Quick start" and "Template updates" sections, and the real adoption evidence in [`docs/pilot-adoption.md`](pilot-adoption.md). For the "why" behind these choices, read the [internal decision site](index.en.html).
