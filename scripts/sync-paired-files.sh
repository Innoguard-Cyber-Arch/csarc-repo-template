#!/usr/bin/env bash
set -euo pipefail

# Keep only truly byte-identical root/template assets paired. Generated
# scripts and workflows intentionally use .csarc paths, so path-sensitive
# files are maintained and tested as separate adapters instead of being
# rewritten by an implicit transform.
#
# Usage:
#   scripts/sync-paired-files.sh          Regenerate every paired copy.
#   scripts/sync-paired-files.sh --check  Verify copies without writing.
paired_files=(
  "SECURITY.md|template/SECURITY.md"
  "docs/security-scanner-readiness.md|template/.csarc/docs/security-scanner-readiness.md"
  "scripts/authenticate_dependabot_head.py|template/.csarc/scripts/authenticate_dependabot_head.py"
  "scripts/check-trusted-verification|template/.csarc/scripts/check-trusted-verification"
  "scripts/csarc_config.py|template/.csarc/scripts/csarc_config.py"
  "scripts/delivery_sync.py|template/.csarc/scripts/delivery_sync.py"
  "scripts/gh-issue-edit|template/.csarc/scripts/gh-issue-edit"
  "scripts/local_verification.py|template/.csarc/scripts/local_verification.py"
  "scripts/release_level.py|template/.csarc/scripts/release_level.py"
  "scripts/release_phase.py|template/.csarc/scripts/release_phase.py"
  "scripts/request-reviewer|template/.csarc/scripts/request-reviewer"
  "scripts/review_gate.py|template/.csarc/scripts/review_gate.py"
  "scripts/security-smoke|template/.csarc/scripts/security-smoke"
  "scripts/test-worktree-cleanup|template/.csarc/scripts/test-worktree-cleanup"
  "scripts/validate-issue-title|template/.csarc/scripts/validate-issue-title"
  "scripts/verification-step|template/.csarc/scripts/verification-step"
  "scripts/verify_release_consumption.py|template/.csarc/scripts/verify_release_consumption.py"
  "policies/actions.json|template/.csarc/policies/actions.json"
  "policies/issue-creation.json|template/.csarc/policies/issue-creation.json"
  "policies/labels.json|template/.csarc/policies/labels.json"
  "policies/releases.json|template/.csarc/policies/releases.json"
  "policies/repository.json|template/.csarc/policies/repository.json"
  "policies/security-scanning.json|template/.csarc/policies/security-scanning.json"
  ".github/ISSUE_TEMPLATE/bug.yml|template/.github/ISSUE_TEMPLATE/bug.yml"
  ".github/ISSUE_TEMPLATE/config.yml|template/.github/ISSUE_TEMPLATE/config.yml"
  ".github/ISSUE_TEMPLATE/documentation.yml|template/.github/ISSUE_TEMPLATE/documentation.yml"
  ".github/ISSUE_TEMPLATE/feature.yml|template/.github/ISSUE_TEMPLATE/feature.yml"
  ".github/ISSUE_TEMPLATE/task.yml|template/.github/ISSUE_TEMPLATE/task.yml"
  "docs/adr/README.md|template/docs/adr/README.md"
)

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

mode="generate"
if [[ "${1:-}" == "--check" ]]; then
  mode="check"
elif [[ "${1:-}" != "" ]]; then
  echo "Usage: $0 [--check]" >&2
  exit 2
fi

drifted=0
for pair in "${paired_files[@]}"; do
  source_name="${pair%%|*}"
  target_name="${pair#*|}"
  source_file="$repo_root/$source_name"
  target_file="$repo_root/$target_name"

  if [[ ! -f "$source_file" ]]; then
    echo "Missing paired source file: $source_name" >&2
    exit 1
  fi

  if [[ "$mode" == "check" ]]; then
    if [[ ! -f "$target_file" ]]; then
      echo "$target_name is missing; run scripts/sync-paired-files.sh" >&2
      drifted=1
      continue
    fi
    if ! cmp -s "$source_file" "$target_file"; then
      echo "$target_name does not match $source_name:" >&2
      diff -u "$target_file" "$source_file" >&2 || true
      drifted=1
    fi
    if { [[ -x "$source_file" ]] && [[ ! -x "$target_file" ]]; } ||
      { [[ ! -x "$source_file" ]] && [[ -x "$target_file" ]]; }; then
      echo "$target_name has a different executable bit than $source_name" >&2
      drifted=1
    fi
  else
    mkdir -p "$(dirname "$target_file")"
    cp "$source_file" "$target_file"
    if [[ -x "$source_file" ]]; then
      chmod +x "$target_file"
    else
      chmod -x "$target_file"
    fi
  fi
done

if [[ "$mode" == "check" && "$drifted" -ne 0 ]]; then
  echo "Run ./scripts/sync-paired-files.sh to regenerate paired copies." >&2
  exit 1
fi
