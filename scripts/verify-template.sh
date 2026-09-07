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
  # GitHub Actions only selects when to call it; the checks stay runnable
  # here. Each stage is also an independently runnable script under
  # scripts/verify-stage-*, so a single stage can be re-checked without
  # paying for the full run; this aggregator calls the same files in the
  # same order and keeps the pass/fail and timing-summary contract below
  # unchanged. See docs/ci-policy.md for the stage inventory and rationale.
  run_stage "Repository contracts" ./scripts/verify-stage-repository-contracts
  run_stage "Static assets and paired files" ./scripts/verify-stage-static-assets
  run_stage "Python environment" ./scripts/verify-stage-python-environment
  run_stage "Python quality" ./scripts/verify-stage-python-quality
  run_stage "Regression tests" ./scripts/verify-stage-regression-tests
  run_stage "Package smoke test" ./scripts/verify-stage-package-smoke
  run_stage "GitHub Actions audit" ./scripts/verify-stage-github-actions-audit

  # Issue #661: record the local-attestation trailer only after every stage
  # above has actually passed -- report_failure's `exit "$status"` inside
  # the ERR trap means this line is unreachable if any run_stage call
  # failed. Deliberately outside the run_stage/print_timing_summary
  # seven-stage inventory documented in docs/ci-policy.md: this is not a
  # verification stage that checks something about the tree, it is the
  # side effect of every stage above already having passed. See
  # scripts/write-verify-attestation and scripts/verify_attestation.py for
  # the trailer format and the design reasoning.
  ./scripts/write-verify-attestation full

  print_timing_summary
  trap - ERR
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
