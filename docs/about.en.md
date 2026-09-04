# About CSARC Repo Template

CSARC Repo Template is Cyber-Arch's updatable repository foundation: creating a new repo, adopting an existing one, and receiving policy updates all preview and verify before a PR merges them. Use the common workflow alone, or opt into Python, Rust, and TypeScript independently.

## What this is

This repository maintains a Copier template, shared CI, security checks, and GitHub configuration drafts. `template/` is what downstream projects receive; the root of this repository follows the same rules on itself (self-hosting).

Available today: a common CI/CD baseline plus independently selectable Python, Rust, and TypeScript language modules, along with Issue/spec, PR checks, and verification. A generated project can also opt into `enable_docker` for a Dockerfile/docker-compose starter and a read-only, non-pushing container build-scan CI job. Automated version PRs, GitHub Releases, packaging, checksums, and SBOMs are candidates that still need a default-branch live run before they count as enabled; registry publishing and general-purpose deployment pipelines are not enabled, and a project that does not opt into `enable_docker` gets none of the container-related files, jobs, or permissions.

## Choose directly

| Item | Options |
| --- | --- |
| Language | Python, Rust, TypeScript are independently multi-selectable; choosing none uses only the common workflow |
| Branching | Each delivery batch gets its own development branch, changes merge straight to `main`, or work first collects on `dev` |
| Template configuration | Choices made at create/adopt time are written to `.csarc/config.yml`; later template updates read the same file instead of duplicating settings elsewhere |

## Shared capabilities

Issue and pull request forms, AI working rules, automated verification, dependency security, version records, and template updates.

## What this document is for

`README.md` tells a general adopter what this is, whether to use it, how to start, and where to learn more. To contribute to this repository itself, read [`AGENTS.md`](../AGENTS.md) (the executable working rules). For the "why" behind these choices, read the [internal decision site](index.en.html). To start installing or adopting, see [Install](install.en.md).
