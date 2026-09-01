#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$repo_root/.cache/uv}"
export UV_PYTHON="${CSARC_PYTHON_VERSION:-3.14}"
cd "$repo_root"

# This is the template repository's single full-verification entry point.
# GitHub Actions only selects when to call it; the checks stay runnable here.
git diff --check
./scripts/check-update-conflicts
./scripts/scan-secrets
./scripts/verify-dependencies
./scripts/build-decision-site --check
./scripts/lint-workflows-shell
./scripts/test-static-validation
./scripts/sync-paired-files.sh --check

unset VIRTUAL_ENV
uv sync --locked --python "$UV_PYTHON"
uv lock --check
uv run ruff format --check src scripts tests
uv run ruff check src scripts tests
uv run ty check
uv run pytest --cov=csarc_cli --cov-report=term-missing --cov-fail-under=80
./scripts/test-issue-triage
./scripts/test-worktree-cleanup
./scripts/test-pr-policy
./scripts/test-release-follow-up-gates
uv build

wheel="$(find dist -maxdepth 1 -type f -name '*.whl' -print -quit)"
test -n "$wheel"
uvx --from "$wheel" csarc --help >/dev/null
uv run zizmor . --format plain
