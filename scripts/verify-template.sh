#!/usr/bin/env bash
set -Eeuo pipefail

stage_names=()
stage_results=()
stage_durations=()
current_stage=""
current_stage_started=0
verification_started=0

record_stage() {
  stage_names+=("$1")
  stage_results+=("$2")
  stage_durations+=("$3")
}

print_timing_summary() {
  local index
  local total_duration=$((SECONDS - verification_started))

  printf '\n[verify-template] Timing summary\n'
  for ((index = 0; index < ${#stage_names[@]}; index++)); do
    printf '  %-8s %4ss  %s\n' \
      "${stage_results[$index]}" \
      "${stage_durations[$index]}" \
      "${stage_names[$index]}"
  done
  printf '  %-8s %4ss  %s\n' "TOTAL" "$total_duration" "Full verification"
}

report_failure() {
  local status=$?
  local duration=$((SECONDS - current_stage_started))

  trap - ERR
  if [[ -n "$current_stage" ]]; then
    record_stage "$current_stage" "FAILED" "$duration"
    printf '[verify-template] FAILED %s (%ss)\n' \
      "$current_stage" "$duration" >&2
  fi
  print_timing_summary >&2
  exit "$status"
}

run_stage() {
  local name=$1
  shift

  current_stage="$name"
  current_stage_started=$SECONDS
  printf '\n[verify-template] START %s\n' "$name"
  "$@"
  local duration=$((SECONDS - current_stage_started))
  record_stage "$name" "PASSED" "$duration"
  printf '[verify-template] PASSED %s (%ss)\n' "$name" "$duration"
  current_stage=""
}

verify_repository_contracts() {
  git diff --check
  ./scripts/check-update-conflicts
  ./scripts/scan-secrets
  ./scripts/verify-dependencies
}

verify_static_assets() {
  ./scripts/build-decision-site --check
  ./scripts/lint-workflows-shell
  ./scripts/test-static-validation
  ./scripts/sync-paired-files.sh --check
}

prepare_python_environment() {
  unset VIRTUAL_ENV
  uv sync --locked --python "$UV_PYTHON"
  uv lock --check
}

verify_python_quality() {
  uv run ruff format --check src scripts tests
  uv run ruff check src scripts tests
  uv run ty check
}

run_regression_tests() {
  uv run pytest --cov=csarc_cli --cov-report=term-missing --cov-fail-under=80
  ./scripts/test-issue-triage
  ./scripts/test-worktree-cleanup
  ./scripts/test-pr-policy
}

verify_package() {
  uv build

  local wheel
  wheel="$(find dist -maxdepth 1 -type f -name '*.whl' -print -quit)"
  test -n "$wheel"
  uvx --from "$wheel" csarc --help >/dev/null
}

audit_github_actions() {
  uv run zizmor . --format plain
}

main() {
  local repo_root
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  local cache_root
  cache_root="$("$repo_root/scripts/resolve-cache-root")"
  if [[ -n "${CSARC_CACHE_ROOT:-}" ]]; then
    export UV_CACHE_DIR="$cache_root/uv"
  else
    export UV_CACHE_DIR="${UV_CACHE_DIR:-$cache_root/uv}"
  fi
  export UV_PYTHON="${CSARC_PYTHON_VERSION:-3.14}"
  cd "$repo_root"

  verification_started=$SECONDS
  trap report_failure ERR

  # This is the template repository's single full-verification entry point.
  # GitHub Actions only selects when to call it; the checks stay runnable here.
  run_stage "Repository contracts" verify_repository_contracts
  run_stage "Static assets and paired files" verify_static_assets
  run_stage "Python environment" prepare_python_environment
  run_stage "Python quality" verify_python_quality
  run_stage "Regression tests" run_regression_tests
  run_stage "Package smoke test" verify_package
  run_stage "GitHub Actions audit" audit_github_actions

  print_timing_summary
  trap - ERR
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
