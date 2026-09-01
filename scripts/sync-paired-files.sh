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
  .github/ISSUE_TEMPLATE/config.yml
  .github/ISSUE_TEMPLATE/bug.yml
  .github/ISSUE_TEMPLATE/documentation.yml
  .github/ISSUE_TEMPLATE/feature.yml
  .github/ISSUE_TEMPLATE/task.yml
  .github/workflows/issue-triage.yml
  .github/workflows/milestone-lifecycle.yml
  .github/workflows/osv.yml
  .github/workflows/pr-policy.yml
  .github/workflows/spec-to-issue.yml
  .github/workflows/work-item-closure.yml
  policies/actions.json
  policies/labels.json
  policies/releases.json
  policies/repository.json
  docs/ci-policy.md
  docs/milestone-description.md
  docs/adr/README.md
  scripts/render_site.py
  scripts/apply-repository-settings.sh
  scripts/check-governance-drift
  scripts/ci_tier.py
  scripts/delivery_sync.py
  scripts/pr_lifecycle.py
  scripts/promotion_gate.py
  scripts/check-update-conflicts
  scripts/cleanup-worktrees
  scripts/csarc_config.py
  scripts/install-actionlint
  scripts/install-gitleaks
  scripts/install-osv-scanner
  scripts/install-shellcheck
  scripts/lint-workflows-shell
  scripts/release_bundle.py
  scripts/release_policy.py
  scripts/resolve-cache-root
  scripts/scan-secrets
  scripts/spec_to_issue.py
  scripts/sync_milestone_state.py
  scripts/sync_work_item_metadata.py
  scripts/test-issue-triage
  scripts/test-pr-policy
  scripts/test-worktree-cleanup
  scripts/verify-release-candidate
  scripts/validate-issue-policy
  scripts/validate-issue-title
  scripts/validate-pr-policy
  scripts/verify-dependencies
  tests/test_ci_tier.py
  tests/test_dependency_security.py
  tests/test_spec_to_issue.py
  tests/test_delivery_sync.py
  tests/test_pr_lifecycle.py
  tests/test_promotion_gate.py
  tests/test_milestone_lifecycle.py
  tests/test_release_policy.py
  tests/test_release_bundle.py
  tests/test_work_item_metadata.py
  tests/test_work_pr_closure.py
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
