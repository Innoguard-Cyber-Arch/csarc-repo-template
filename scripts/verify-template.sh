#!/usr/bin/env bash
set -Eeuo pipefail

verification_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$verification_root/scripts/verification-step"

stage_names=()
stage_results=()
stage_durations=()
current_stage=""
current_stage_started=0
current_stage_command=""
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
    printf '[verify-template] RERUN %s\n' "$current_stage_command" >&2
  fi
  print_timing_summary >&2
  exit "$status"
}

run_stage() {
  local name=$1
  shift

  current_stage="$name"
  current_stage_started=$SECONDS
  current_stage_command="$(verification_command_string "$@")"
  printf '\n[verify-template] START %s\n' "$name"
  # Issue #1340: recheck the pinned control set before each stage.
  verification_check_controls
  "$@"
  local duration=$((SECONDS - current_stage_started))
  record_stage "$name" "PASSED" "$duration"
  printf '[verify-template] PASSED %s (%ss)\n' "$name" "$duration"
  current_stage=""
  current_stage_command=""
}

main() {
  # Issue #1086: stages come from this entry point's own (trusted) tree and
  # run against the subject tree named by CSARC_VERIFICATION_SUBJECT_ROOT.
  local control_root="$verification_root"
  local repo_root
  repo_root="$(verification_subject_root "$control_root")"
  # Only the control-set stage scripts read this; each one unsets it again.
  export CSARC_VERIFICATION_SUBJECT_ROOT="$repo_root"
  local cache_root
  cache_root="$("$control_root/scripts/resolve-cache-root")"
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
  run_stage "Repository contracts" "$control_root"/scripts/verify-stage-repository-contracts
  run_stage "Static assets and paired files" "$control_root"/scripts/verify-stage-static-assets
  run_stage "Python environment" "$control_root"/scripts/verify-stage-python-environment
  run_stage "Python quality" "$control_root"/scripts/verify-stage-python-quality
  run_stage "Regression tests" "$control_root"/scripts/verify-stage-regression-tests
  run_stage "Package smoke test" "$control_root"/scripts/verify-stage-package-smoke
  run_stage "GitHub Actions audit" "$control_root"/scripts/verify-stage-github-actions-audit

  print_timing_summary
  trap - ERR
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
