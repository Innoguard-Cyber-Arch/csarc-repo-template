#!/usr/bin/env bash
set -euo pipefail

# Single source of truth for the root files that template/ ships byte-for-byte
# unchanged to downstream repositories. Root is canonical: these files are the
# ones this repository exercises directly (its own workflows, scripts, and
# tests), so edits belong there and template/ receives an exact copy.
#
# Usage:
#   scripts/sync-paired-files.sh          Regenerate every template/ copy.
#   scripts/sync-paired-files.sh --check  Verify copies without writing files;
#                                         exits non-zero and prints details for
#                                         each pair that has drifted.
paired_files=(
  CLAUDE.md
  SECURITY.md
  .release-please-manifest.json
  .github/ISSUE_TEMPLATE/config.yml
  .github/ISSUE_TEMPLATE/work-item.yml
  .github/workflows/governance-comment.yml
  .github/workflows/governance-drift.yml
  .github/workflows/issue-triage.yml
  .github/workflows/milestone-lifecycle.yml
  .github/workflows/pr-policy.yml
  .github/workflows/release-please.yml
  .github/workflows/spec-to-issue.yml
  policies/actions.json
  policies/labels.json
  policies/repository.json
  docs/milestone-description.md
  scripts/apply-repository-settings.sh
  scripts/check-governance-drift
  scripts/check-update-conflicts
  scripts/cleanup-worktrees
  scripts/install-gitleaks
  scripts/release_policy.py
  scripts/scan-secrets
  scripts/spec_to_issue.py
  scripts/sync_milestone_state.py
  scripts/test-issue-triage
  scripts/test-pr-policy
  scripts/test-worktree-cleanup
  scripts/validate-issue-title
  tests/test_spec_to_issue.py
  tests/test_milestone_lifecycle.py
  tests/test_release_policy.py
  zizmor.yml
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
for relative_file in "${paired_files[@]}"; do
  source_file="$repo_root/$relative_file"
  target_file="$repo_root/template/$relative_file"

  if [[ ! -f "$source_file" ]]; then
    echo "Missing paired source file: $relative_file" >&2
    exit 1
  fi

  if [[ "$mode" == "check" ]]; then
    if [[ ! -f "$target_file" ]]; then
      echo "template/$relative_file is missing; run scripts/sync-paired-files.sh" >&2
      drifted=1
      continue
    fi
    if ! cmp -s "$source_file" "$target_file"; then
      echo "template/$relative_file does not match the sync-paired-files.sh output:" >&2
      diff -u "$target_file" "$source_file" >&2 || true
      drifted=1
    fi
    if { [[ -x "$source_file" ]] && [[ ! -x "$target_file" ]]; } ||
      { [[ ! -x "$source_file" ]] && [[ -x "$target_file" ]]; }; then
      echo "template/$relative_file has a different executable bit than $relative_file" >&2
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
  echo "Run ./scripts/sync-paired-files.sh to regenerate template/ copies." >&2
  exit 1
fi
