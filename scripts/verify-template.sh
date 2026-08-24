#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture_root="$(mktemp -d)"
trap 'rm -rf "$fixture_root"' EXIT
cd "$repo_root"

test "$(wc -c < AGENTS.md)" -le 13000
test "$(wc -c < template/AGENTS.md.jinja)" -le 14000
if grep -Eq 'step [0-9]+|第 [0-9]+ 點|第 [0-9]+點' \
  AGENTS.md template/AGENTS.md.jinja; then
  echo "Agent guidance must not use numeric step cross-references."
  exit 1
fi
grep -q 'uv sync --locked --python 3.14' AGENTS.md
grep -q 'uv run pytest <test-path>' AGENTS.md
grep -q 'scripts/render_site.py --check' AGENTS.md
grep -q 'Actions quota fallback attestation' docs/ci-policy.md
for summary_file in AGENTS.md README.md template/AGENTS.md.jinja \
  template/README.md.jinja; do
  grep -q 'docs/ci-policy.md#actions-額度-fallback' "$summary_file"
  if grep -q 'Actions quota fallback attestation' "$summary_file"; then
    echo "$summary_file duplicates the canonical quota fallback procedure."
    exit 1
  fi
done

assert_agent_guidance() {
  local project_root="$1"
  test "$(wc -c < "$project_root/AGENTS.md")" -le 14000
  test "$(cat "$project_root/CLAUDE.md")" = "@AGENTS.md"
  grep -q 'git rev-parse --show-toplevel' "$project_root/README.md"
  grep -q 'pwd -P' "$project_root/README.md"
  grep -q 'docs/ci-policy.md#actions-額度-fallback' \
    "$project_root/README.md"
  grep -q 'docs/ci-policy.md#actions-額度-fallback' \
    "$project_root/AGENTS.md"
  grep -q 'scripts/render_site.py --check' "$project_root/AGENTS.md"
  grep -q 'propose semantic story groups and exclusions' \
    "$project_root/AGENTS.md"
  grep -q 'reopen completed Issues' "$project_root/AGENTS.md"
}

./scripts/check-update-conflicts
python3 scripts/render_site.py --check

prime_gitleaks_cache() {
  local project_root="$1"
  mkdir -p "$project_root/.cache"
  cp -R "$repo_root/.cache/gitleaks" "$project_root/.cache/gitleaks"
}

unset VIRTUAL_ENV
export UV_PYTHON="${CSARC_PYTHON_VERSION:-3.14}"
uv sync --locked --python "$UV_PYTHON"
uv lock --check
uv run ruff format --check \
  src/csarc_cli \
  tests/test_cli.py \
  tests/test_milestone_lifecycle.py \
  tests/test_ci_tier.py \
  tests/test_promotion_gate.py \
  tests/test_delivery_sync.py \
  tests/test_release_policy.py \
  tests/test_release_prompt.py \
  tests/test_release_consumption.py \
  tests/test_render_site.py \
  scripts/report_dependency_ceiling.py \
  scripts/ci_tier.py \
  scripts/delivery_sync.py \
  scripts/promotion_gate.py \
  scripts/render_release_prompt.py \
  scripts/render_site.py \
  scripts/release_policy.py \
  scripts/spec_to_issue.py \
  scripts/sync_milestone_state.py \
  scripts/update_python_version.py \
  scripts/verify_release_consumption.py \
  tests/test_spec_to_issue.py
uv run ruff check \
  src/csarc_cli \
  tests/test_cli.py \
  tests/test_milestone_lifecycle.py \
  tests/test_ci_tier.py \
  tests/test_promotion_gate.py \
  tests/test_delivery_sync.py \
  tests/test_release_policy.py \
  tests/test_release_prompt.py \
  tests/test_release_consumption.py \
  tests/test_render_site.py \
  scripts/report_dependency_ceiling.py \
  scripts/ci_tier.py \
  scripts/delivery_sync.py \
  scripts/promotion_gate.py \
  scripts/render_release_prompt.py \
  scripts/render_site.py \
  scripts/release_policy.py \
  scripts/spec_to_issue.py \
  scripts/sync_milestone_state.py \
  scripts/update_python_version.py \
  scripts/verify_release_consumption.py \
  tests/test_spec_to_issue.py
uv run mypy \
  src/csarc_cli \
  scripts/report_dependency_ceiling.py \
  scripts/ci_tier.py \
  scripts/delivery_sync.py \
  scripts/promotion_gate.py \
  scripts/render_release_prompt.py \
  scripts/render_site.py \
  scripts/release_policy.py \
  scripts/spec_to_issue.py \
  scripts/sync_milestone_state.py \
  scripts/update_python_version.py \
  scripts/verify_release_consumption.py \
  tests/test_spec_to_issue.py
uv run pytest \
  --cov=csarc_cli --cov-report=term-missing --cov-fail-under=80
uv build
uvx --from "$(find dist -maxdepth 1 -type f -name '*.whl' -print -quit)" \
  csarc --help >/dev/null
uv run python scripts/spec_to_issue.py validate
bash -n scripts/apply-repository-settings.sh
bash -n template/scripts/apply-repository-settings.sh
bash -n scripts/check-update-conflicts
bash -n template/scripts/check-update-conflicts
bash -n scripts/cleanup-worktrees
bash -n template/scripts/cleanup-worktrees
bash -n scripts/check-governance-drift
bash -n template/scripts/check-governance-drift
bash -n scripts/verify-fast
grep -q 'CODEOWNERS、repository、Actions、政策標籤與有效 Ruleset' README.md
grep -q 'policy labels, and effective Rulesets' docs/agent-install.md
grep -q 'Administration read access' docs/agent-install.md
grep -q 'Existing-repository history changes start read-only' \
  docs/agent-install.md
grep -q 'Never infer groups' docs/agent-install.md
grep -q 'from titles or labels alone' docs/agent-install.md
grep -q 'CODEOWNERS、repository、Actions、政策標籤與有效 Ruleset' docs/index.html
grep -q '^## Actions quota fallback$' AGENTS.md
grep -q '^## Actions quota fallback$' template/AGENTS.md.jinja
grep -q 'included Actions minutes are exhausted' AGENTS.md
grep -q 'included Actions minutes are exhausted' template/AGENTS.md.jinja
grep -q 'failed payments.*spending limit' docs/ci-policy.md
grep -q 'HEAD.*PR head SHA' docs/ci-policy.md
grep -q 'Actions quota fallback attestation' docs/ci-policy.md
grep -q 'runner 註記本身不構成證據' README.md
grep -q 'runner 註記本身不構成證據' template/README.md.jinja
grep -q '額度耗盡.*human' docs/index.html
grep -q '額度 fallback.*human' template/site/index.html.jinja
bash -n scripts/run-live-workflow-probe
bash -n scripts/test-pr-policy
./scripts/test-pr-policy
bash -n scripts/test-issue-triage
bash -n scripts/validate-issue-title
bash -n template/scripts/validate-issue-title
./scripts/test-issue-triage
bash -n scripts/test-worktree-cleanup
./scripts/test-worktree-cleanup

# The live probe must preserve valid run JSON and emit reusable evidence.
live_probe_fixture="$fixture_root/live-probe"
mkdir -p "$live_probe_fixture/bin"
cat > "$live_probe_fixture/bin/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

case "$1 $2" in
  "run list")
    if [[ "$*" == *"--limit 1"* ]]; then
      printf '40\n'
    else
      printf '41\n'
    fi
    ;;
  "workflow run" | "run watch") ;;
  "run view")
    printf '%s\n' \
      '{"conclusion":"success","url":"https://example.invalid/actions/runs/41"}'
    ;;
  *)
    echo "Unexpected gh command: $*" >&2
    exit 2
    ;;
esac
SH
chmod +x "$live_probe_fixture/bin/gh"
PATH="$live_probe_fixture/bin:$PATH" \
  GITHUB_REPOSITORY="acme/project" \
  CSARC_LIVE_TIMEOUT_SECONDS=1 \
  "$repo_root/scripts/run-live-workflow-probe" \
  "OSV" "osv.yml" "main" "$live_probe_fixture/evidence.json" \
  "reusable workflow permissions"
jq -e \
  '.status == "passed" and .conclusion == "success" and .run_id == 41' \
  "$live_probe_fixture/evidence.json" >/dev/null

# Repository settings must follow the account plan and actual API capability.
github_plan_fixture="$fixture_root/github-plan"
mkdir -p "$github_plan_fixture/bin"
cat > "$github_plan_fixture/bin/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

if [[ "$1" == "api" && "$2" == "--method" ]]; then
  if [[ "$*" == *"actions/permissions/workflow"* && -n "${MOCK_ACTIONS_ERROR:-}" ]]; then
    echo "$MOCK_ACTIONS_ERROR" >&2
    exit 1
  fi
  printf '%s\n' "$*" >> "$MOCK_GH_LOG"
  exit 0
fi
if [[ "$1" == "label" && "$2" == "list" ]]; then
  if [[ "$*" == *"name,color,description"* ]]; then
    if [[ "${MOCK_LABELS_STATE:-match}" == "mismatch" ]]; then
      printf '%s\n' '[{"name":"bug","color":"ffffff","description":"Something is not working"},{"name":"enhancement","color":"A2EEEF","description":"New feature or improvement"},{"name":"documentation","color":"0075CA","description":"Documentation improvement"},{"name":"duplicate","color":"CFD3D7","description":"This issue already exists"},{"name":"hotfix","color":"B60205","description":"Urgent standalone change promoted directly to main"},{"name":"promotion","color":"5319E7","description":"Final delivery branch promotion to main"},{"name":"task","color":"000000","description":"Custom"}]'
    else
      printf '%s\n' '[{"name":"bug","color":"D73A4A","description":"Something is not working"},{"name":"enhancement","color":"A2EEEF","description":"New feature or improvement"},{"name":"documentation","color":"0075CA","description":"Documentation improvement"},{"name":"duplicate","color":"CFD3D7","description":"This issue already exists"},{"name":"hotfix","color":"B60205","description":"Urgent standalone change promoted directly to main"},{"name":"promotion","color":"5319E7","description":"Final delivery branch promotion to main"},{"name":"task","color":"000000","description":"Custom"}]'
    fi
  else
    printf 'bug\nduplicate\nhotfix\npromotion\ntask\n'
  fi
  exit 0
fi
if [[ "$1" == "label" ]]; then
  printf '%s\n' "$*" >> "$MOCK_GH_LOG"
  exit 0
fi
if [[ "$1" == "repo" && "$2" == "view" ]]; then
  echo "no git remotes found" >&2
  exit 1
fi
if [[ "$1" == "issue" && "$2" == "list" ]]; then
  printf '%s\n' "${MOCK_EXISTING_ISSUE:-}"
  exit 0
fi
if [[ "$1" == "issue" ]]; then
  printf '%s\n' "$*" >> "$MOCK_GH_LOG"
  exit 0
fi
if [[ "$1" != "api" ]]; then
  echo "Unexpected gh command: $*" >&2
  exit 2
fi
case "$2" in
  graphql)
    if [[ "${MOCK_STAGED_RULESET:-present}" == "absent" ]]; then
      printf '%s\n' '{"data":{"repository":{"id":"R_test","rulesets":{"nodes":[]}}}}'
    elif [[ "${MOCK_STAGED_RULESET:-present}" == "stale" ]]; then
      printf '%s\n' '{"data":{"repository":{"id":"R_test","rulesets":{"nodes":[{"id":"RRS_test","name":"CSARC protected branches","enforcement":"DISABLED","target":"BRANCH"}]}}}}'
    else
      printf '%s\n' '{"data":{"repository":{"id":"R_test","rulesets":{"nodes":[{"id":"RRS_test","name":"CSARC protected branches","enforcement":"ACTIVE","target":"BRANCH"}]}}}}'
    fi
    ;;
  repos/acme/project)
    if [[ "$*" == *"--jq"* ]]; then
      printf 'acme\tOrganization\t%s\t%s\tmain\n' \
        "$MOCK_GITHUB_VISIBILITY" "${MOCK_REPO_ADMIN:-true}"
    elif [[ "${MOCK_REPOSITORY_STATE:-match}" == "mismatch" ]]; then
      printf '%s\n' '{"owner":{"login":"acme","type":"Organization"},"visibility":"private","permissions":{"admin":true},"default_branch":"main","allow_auto_merge":false,"allow_merge_commit":false,"allow_rebase_merge":false,"allow_squash_merge":true,"delete_branch_on_merge":true,"has_issues":true,"has_projects":false,"has_wiki":true}'
    elif [[ "${MOCK_REPOSITORY_STATE:-match}" == "limited" ]]; then
      printf '%s\n' '{"owner":{"login":"acme","type":"Organization"},"visibility":"private","permissions":{"admin":false},"default_branch":"main","has_issues":true,"has_projects":false,"has_wiki":false}'
    else
      printf '%s\n' '{"owner":{"login":"acme","type":"Organization"},"visibility":"private","permissions":{"admin":true},"default_branch":"main","allow_auto_merge":false,"allow_merge_commit":false,"allow_rebase_merge":false,"allow_squash_merge":true,"delete_branch_on_merge":true,"has_issues":true,"has_projects":false,"has_wiki":false}'
    fi
    ;;
  repos/acme/project/actions/permissions/workflow)
    if [[ "${MOCK_ACTIONS_STATE:-match}" == "integration-error" ]]; then
      echo "Resource not accessible by integration" >&2
      exit 1
    elif [[ "${MOCK_ACTIONS_STATE:-match}" == "error" ]]; then
      echo "503 Actions settings unavailable" >&2
      exit 1
    elif [[ "${MOCK_ACTIONS_STATE:-match}" == "default-mismatch" ]]; then
      printf '%s\n' '{"default_workflow_permissions":"write","can_approve_pull_request_reviews":true}'
    elif [[ "${MOCK_ACTIONS_STATE:-match}" == "degraded" ]]; then
      printf '%s\n' '{"default_workflow_permissions":"read","can_approve_pull_request_reviews":false}'
    else
      printf '%s\n' '{"default_workflow_permissions":"read","can_approve_pull_request_reviews":true}'
    fi
    ;;
  repos/acme/project/teams)
    if [[ "${MOCK_CODEOWNERS_STATE:-valid}" == "unavailable" ]]; then
      echo "Resource not accessible by integration" >&2
      exit 1
    elif [[ "${MOCK_CODEOWNERS_STATE:-valid}" == "invalid" ]]; then
      printf '%s\n' '[[{"slug":"arch","permission":"pull","permissions":{"pull":true,"push":false,"maintain":false,"admin":false}}]]'
    elif [[ "${MOCK_CODEOWNERS_STATE:-valid}" == "missing" ]]; then
      printf '%s\n' '[[]]'
    else
      printf '%s\n' '[[{"slug":"arch","permission":"push","permissions":{"pull":true,"push":true,"maintain":false,"admin":false}}]]'
    fi
    ;;
  orgs/acme)
    printf '%s\n' "$MOCK_GITHUB_PLAN"
    ;;
  repos/acme/project/rulesets)
    if [[ -n "${MOCK_RULESET_ERROR:-}" ]]; then
      echo "$MOCK_RULESET_ERROR" >&2
      exit 1
    fi
    if [[ "$MOCK_GITHUB_PLAN" == "free" && "$MOCK_GITHUB_VISIBILITY" != "public" ]]; then
      echo "Upgrade to GitHub Pro or make this repository public to enable this feature" >&2
      exit 1
    fi
    printf '[]\n'
    ;;
  repos/acme/project/rules/branches/main)
    if [[ "${MOCK_GOVERNANCE:-protected}" == "error" ]]; then
      echo "403 cannot inspect effective rules" >&2
      exit 1
    fi
    if [[ "${MOCK_GOVERNANCE:-protected}" == "incomplete" ]]; then
      printf '[]\n'
      exit 0
    fi
    printf '%s\n' '[{"type":"deletion"},{"type":"non_fast_forward"},{"type":"pull_request","parameters":{"dismiss_stale_reviews_on_push":true,"require_code_owner_review":true,"require_last_push_approval":true,"required_review_thread_resolution":true,"required_approving_review_count":1}},{"type":"required_status_checks","parameters":{"strict_required_status_checks_policy":true,"required_status_checks":[{"context":"delivery-sync"},{"context":"promotion"},{"context":"verify"},{"context":"title"}]}}]'
    ;;
  *)
    echo "Unexpected gh API path: $2" >&2
    exit 2
    ;;
esac
SH
chmod +x "$github_plan_fixture/bin/gh"

run_settings_fixture() {
  local plan="$1"
  local mode="${2:-plan}"
  local ruleset_error="${3:-}"
  local prune_labels="${4:-false}"
  local allow_unprotected="${5:-false}"
  local governance="${6:-protected}"
  local staged_ruleset="${7:-present}"
  local actions_error="${8:-}"
  local repository_state="${9:-match}"
  local actions_state="${10:-match}"
  local labels_state="${11:-match}"
  local repo_admin="${12:-true}"
  local codeowners_state="${13:-valid}"
  local suffix=""
  local arguments=("$mode")
  if [[ "$prune_labels" == true ]]; then
    suffix="-prune"
    arguments+=(--prune-labels)
  fi
  if [[ "$allow_unprotected" == true ]]; then
    suffix="$suffix-allow-unprotected"
    arguments+=(--allow-unprotected)
  fi
  if [[ "$staged_ruleset" != "present" ]]; then
    suffix="$suffix-$staged_ruleset"
  fi
  local call_log="$github_plan_fixture/$plan-$mode$suffix.log"
  : > "$call_log"
  rm -f "$call_log.staged"
  PATH="$github_plan_fixture/bin:$PATH" \
    GH_REPO="acme/project" \
    MOCK_GITHUB_PLAN="$plan" \
    MOCK_GITHUB_VISIBILITY="private" \
    MOCK_RULESET_ERROR="$ruleset_error" \
    MOCK_GOVERNANCE="$governance" \
    MOCK_STAGED_RULESET="$staged_ruleset" \
    MOCK_ACTIONS_ERROR="$actions_error" \
    MOCK_REPOSITORY_STATE="$repository_state" \
    MOCK_ACTIONS_STATE="$actions_state" \
    MOCK_LABELS_STATE="$labels_state" \
    MOCK_REPO_ADMIN="$repo_admin" \
    MOCK_CODEOWNERS_STATE="$codeowners_state" \
    MOCK_GH_LOG="$call_log" \
    ./scripts/apply-repository-settings.sh "${arguments[@]}"
}

if no_remote="$({
  cd "$github_plan_fixture"
  env -u GH_REPO PATH="$github_plan_fixture/bin:$PATH" \
    MOCK_GH_LOG="$github_plan_fixture/no-remote.log" \
    "$repo_root/scripts/apply-repository-settings.sh" plan
} 2>&1)"; then
  echo "Repository settings must stop when no Git remote is available."
  exit 1
fi
grep -q 'Run inside a Git repository with a GitHub remote, or set GH_REPO=owner/repo.' \
  <<<"$no_remote"

if unknown_ruleset="$(run_settings_fixture team plan "403 service unavailable" 2>&1)"; then
  echo "Unknown Ruleset API errors must stop repository settings."
  exit 1
fi
grep -q 'Cannot determine Ruleset capability' <<<"$unknown_ruleset"
grep -q '403 service unavailable' <<<"$unknown_ruleset"

for settings_mode in plan apply check; do
  for codeowners_state in invalid missing; do
    if invalid_codeowners="$(
      run_settings_fixture free "$settings_mode" "" false false protected \
        absent "" match match match true "$codeowners_state" 2>&1
    )"; then
      echo "$settings_mode must reject $codeowners_state CODEOWNERS."
      exit 1
    fi
    grep -q 'CODEOWNERS validation failed:' <<<"$invalid_codeowners"
    grep -Eq 'lacks repository (write )?access' <<<"$invalid_codeowners"
  done
done

free_plan="$(run_settings_fixture free plan "" false false protected absent)"
grep -q 'Account plan: GitHub Free' <<<"$free_plan"
grep -q 'PRESERVE policies/rulesets.json locally' <<<"$free_plan"
grep -q 'OPTIONAL MANUAL STAGING' <<<"$free_plan"
grep -q 'REST and GraphQL reject Ruleset creation' <<<"$free_plan"
grep -q 'DEGRADED required governance' <<<"$free_plan"
grep -q 'ask the owner to upgrade to GitHub Team or above' \
  <<<"$free_plan"
grep -q 'https://github.com/organizations/acme/settings/billing' <<<"$free_plan"
grep -q 'ALTERNATIVE only when public access is approved' <<<"$free_plan"
grep -q 'GH_REPO=acme/project ./scripts/apply-repository-settings.sh apply' \
  <<<"$free_plan"
grep -q 'KEEP labels outside policy' <<<"$free_plan"
free_prune_plan="$(run_settings_fixture free plan "" true)"
grep -q 'PRUNE labels outside policy' <<<"$free_prune_plan"
grep -q 'DELETE label: task' <<<"$free_prune_plan"
if grep -q 'DELETE label: duplicate' <<<"$free_prune_plan"; then
  echo "The duplicate policy label must not be pruned."
  exit 1
fi
for delivery_label in hotfix promotion; do
  if grep -q "DELETE label: $delivery_label" <<<"$free_prune_plan"; then
    echo "The $delivery_label policy label must not be pruned."
    exit 1
  fi
done
team_plan="$(run_settings_fixture team)"
grep -q 'Account plan: GitHub Team' <<<"$team_plan"
grep -q 'APPLY policies/rulesets.json' <<<"$team_plan"
enterprise_plan="$(run_settings_fixture business_plus)"
grep -q 'Account plan: GitHub Enterprise' <<<"$enterprise_plan"
grep -q 'Enterprise-wide identity, audit, network' <<<"$enterprise_plan"

free_check="$(run_settings_fixture free check)"
grep -q 'STAGED manually configured Ruleset' <<<"$free_check"
grep -q 'DEGRADED required governance' <<<"$free_check"
free_missing_check="$(run_settings_fixture free check "" false false protected absent)"
grep -q 'MISSING remote Ruleset' <<<"$free_missing_check"
team_check="$(run_settings_fixture team check)"
grep -q 'Repository governance ready' <<<"$team_check"
grep -q 'All observable repository settings match policy' <<<"$team_check"
if repository_mismatch="$(run_settings_fixture team check "" false false protected present "" mismatch 2>&1)"; then
  echo "Repository setting mismatches must fail checks."
  exit 1
fi
grep -q 'Repository settings drift: has_wiki' <<<"$repository_mismatch"
if actions_mismatch="$(run_settings_fixture team check "" false false protected present "" match default-mismatch 2>&1)"; then
  echo "Actionable Actions setting mismatches must fail checks."
  exit 1
fi
grep -q 'Actions settings drift: default_workflow_permissions' <<<"$actions_mismatch"
if actions_unavailable="$(run_settings_fixture team check "" false false protected present "" match error 2>&1)"; then
  echo "Unreadable Actions settings must fail closed."
  exit 1
fi
grep -q 'Cannot inspect Actions workflow permissions' <<<"$actions_unavailable"
grep -q '503 Actions settings unavailable' <<<"$actions_unavailable"
limited_token_check="$(run_settings_fixture team check "" false false protected present "" limited integration-error match false)"
grep -q 'DEGRADED repository inspection: token cannot read administrator-only fields' \
  <<<"$limited_token_check"
grep -q 'DEGRADED Actions inspection: token cannot read administrator-only workflow permissions' \
  <<<"$limited_token_check"
actions_degraded_check="$(run_settings_fixture team check "" false false protected present "" match degraded)"
grep -q 'DEGRADED Actions PR policy: desired true, live false' <<<"$actions_degraded_check"
grep -q 'completed with 1 degraded capability difference' <<<"$actions_degraded_check"
limited_codeowners_check="$(
  run_settings_fixture team check "" false false protected present "" \
    limited integration-error match false unavailable
)"
grep -q 'DEGRADED CODEOWNERS inspection: token cannot validate configured owners' \
  <<<"$limited_codeowners_check"
if labels_mismatch="$(run_settings_fixture team check "" false false protected present "" match match mismatch 2>&1)"; then
  echo "Policy label mismatches must fail checks."
  exit 1
fi
grep -q "Label settings drift: 'bug' color differs" <<<"$labels_mismatch"
if incomplete_check="$(run_settings_fixture team check "" false false incomplete 2>&1)"; then
  echo "Incomplete effective branch rules must fail governance checks."
  exit 1
fi
grep -q 'missing deletion rule' <<<"$incomplete_check"
if unavailable_check="$(run_settings_fixture team check "" false false error 2>&1)"; then
  echo "Unreadable effective branch rules must fail governance checks."
  exit 1
fi
grep -q 'Cannot inspect effective rules' <<<"$unavailable_check"

# The scheduled drift check must open, update, or skip a tracking Issue
# based on the real apply-repository-settings.sh check output.
run_drift_check() {
  local governance="$1"
  local existing_issue="${2:-}"
  local log_file="$3"
  local plan="${4:-team}"
  local actions_state="${5:-match}"
  local staged_ruleset="${6:-present}"
  : > "$log_file"
  PATH="$github_plan_fixture/bin:$PATH" \
    GH_REPO="acme/project" \
    MOCK_GITHUB_PLAN="$plan" \
    MOCK_GITHUB_VISIBILITY="private" \
    MOCK_GOVERNANCE="$governance" \
    MOCK_ACTIONS_STATE="$actions_state" \
    MOCK_STAGED_RULESET="$staged_ruleset" \
    MOCK_EXISTING_ISSUE="$existing_issue" \
    MOCK_GH_LOG="$log_file" \
    "$repo_root/scripts/check-governance-drift"
}
drift_create_log="$github_plan_fixture/drift-create.log"
if run_drift_check incomplete "" "$drift_create_log" >/dev/null 2>&1; then
  echo "check-governance-drift must fail when governance drift is detected."
  exit 1
fi
grep -q '^issue create .*--label bug' "$drift_create_log"
drift_update_log="$github_plan_fixture/drift-update.log"
if run_drift_check incomplete 91 "$drift_update_log" >/dev/null 2>&1; then
  echo "check-governance-drift must fail when governance drift is detected."
  exit 1
fi
grep -q '^issue edit 91 ' "$drift_update_log"
drift_clean_log="$github_plan_fixture/drift-clean.log"
run_drift_check protected "" "$drift_clean_log" >/dev/null
test ! -s "$drift_clean_log"
drift_degraded_log="$github_plan_fixture/drift-degraded.log"
drift_degraded="$(run_drift_check protected "" "$drift_degraded_log" free match absent)"
grep -q 'MISSING remote Ruleset' <<<"$drift_degraded"
grep -q 'Repository settings have degraded capability differences' <<<"$drift_degraded"
if grep -q 'No repository settings drift detected' <<<"$drift_degraded"; then
  echo "Degraded settings must not be reported as fully aligned."
  exit 1
fi
test ! -s "$drift_degraded_log"

free_degraded="$(run_settings_fixture free apply "" false false protected absent)"
grep -q 'DEGRADED repository settings applied' <<<"$free_degraded"
free_actions_degraded="$(
  run_settings_fixture free apply "" false false protected absent \
    "409 GitHub Actions is not permitted to create pull requests"
)"
grep -q 'DEGRADED Actions PR policy' <<<"$free_actions_degraded"
grep -q 'select direct or verification-only mode' <<<"$free_actions_degraded"
grep -q 'api --method PATCH repos/acme/project' \
  "$github_plan_fixture/free-apply-absent.log"
if grep -Eq 'createRepositoryRuleset|updateRepositoryRuleset|api --method (POST|PUT) repos/acme/project/rulesets' \
  "$github_plan_fixture/free-apply-absent.log"; then
  echo "GitHub Free private repositories must not receive unsupported Ruleset API mutations."
  exit 1
fi
if grep -q 'label delete' \
  "$github_plan_fixture/free-apply-absent.log"; then
  echo "Default repository setup must preserve labels outside policy."
  exit 1
fi
run_settings_fixture free apply "" true true >/dev/null
grep -q 'label delete task' \
  "$github_plan_fixture/free-apply-prune-allow-unprotected.log"
if grep -q 'label delete duplicate' \
  "$github_plan_fixture/free-apply-prune-allow-unprotected.log"; then
  echo "The duplicate policy label must not be deleted."
  exit 1
fi
if grep -q 'label delete bug' \
  "$github_plan_fixture/free-apply-prune-allow-unprotected.log"; then
  echo "Labels declared in policy must not be deleted."
  exit 1
fi
if grep -Eq 'api --method (POST|PUT) repos/acme/project/rulesets' \
  "$github_plan_fixture/free-apply-prune-allow-unprotected.log"; then
  echo "GitHub Free private repositories must preserve Rulesets locally."
  exit 1
fi
run_settings_fixture team apply >/dev/null
grep -q 'api --method POST repos/acme/project/rulesets' \
  "$github_plan_fixture/team-apply.log"

secret_scan_fixture="$fixture_root/secret-scan"
clean_secret_fixture="$secret_scan_fixture/clean"
history_secret_fixture="$secret_scan_fixture/history-leak"
worktree_secret_fixture="$secret_scan_fixture/worktree-leak"
for secret_fixture in \
  "$clean_secret_fixture" \
  "$history_secret_fixture" \
  "$worktree_secret_fixture"; do
  mkdir -p "$secret_fixture"
  printf '%s\n' \
    'title = "CSARC secret scan fixture"' \
    '[[rules]]' \
    'id = "csarc-fixture-secret"' \
    'description = "Synthetic fixture marker"' \
    "regex = '''CSARC_FIXTURE_[A-Z]{16}'''" \
    > "$secret_fixture/.gitleaks.toml"
done
printf '%s\n' 'safe fixture' > "$clean_secret_fixture/example.txt"
./scripts/scan-secrets "$clean_secret_fixture"

git -C "$history_secret_fixture" init -b main
git -C "$history_secret_fixture" config user.name "Template Test"
git -C "$history_secret_fixture" config user.email "template-test@example.invalid"
printf '%s\n' 'CSARC_FIXTURE_ABCDEFGHIJKLMNOP' \
  > "$history_secret_fixture/removed-secret.txt"
git -C "$history_secret_fixture" add .
git -C "$history_secret_fixture" commit -m "test: add synthetic leak"
git -C "$history_secret_fixture" rm removed-secret.txt
git -C "$history_secret_fixture" commit -m "test: remove synthetic leak"
if ./scripts/scan-secrets "$history_secret_fixture"; then
  echo "Secret scan must reject a synthetic marker retained in Git history."
  exit 1
fi

printf '%s\n' 'CSARC_FIXTURE_QRSTUVWXYZABCDEF' \
  > "$worktree_secret_fixture/uncommitted-secret.txt"
if ./scripts/scan-secrets "$worktree_secret_fixture"; then
  echo "Secret scan must reject a synthetic marker in a non-Git working tree."
  exit 1
fi

./scripts/scan-secrets
uv run zizmor . --format plain

# Prove that every declared direct dependency lower bound still works.
lower_bounds_root="$fixture_root/root-lower-bounds"
mkdir -p "$lower_bounds_root"
if ! uv pip compile \
  pyproject.toml \
  --group dev \
  --resolution lowest-direct \
  --python-version 3.14 \
  --output-file "$lower_bounds_root/requirements-min.txt"; then
  echo "Root dev dependency lower bounds cannot be resolved."
  exit 1
fi
uv venv --python 3.14 "$lower_bounds_root/.venv"
if ! uv pip install \
  --python "$lower_bounds_root/.venv/bin/python" \
  --requirements "$lower_bounds_root/requirements-min.txt"; then
  echo "Root dev dependency lower bounds cannot be installed."
  exit 1
fi
uv pip check --python "$lower_bounds_root/.venv/bin/python"
if ! "$lower_bounds_root/.venv/bin/python" -m pytest \
  tests/test_delivery_sync.py tests/test_milestone_lifecycle.py tests/test_release_policy.py \
  tests/test_spec_to_issue.py; then
  echo "Root tests fail with the declared direct dependency lower bounds."
  exit 1
fi

# The next stable feature release must update every governed version surface.
version_policy_fixture="$fixture_root/version-policy"
rsync -a --exclude=.git --exclude=.venv \
  "$repo_root/" "$version_policy_fixture/"
uv run python scripts/update_python_version.py \
  --repo-root "$version_policy_fixture" \
  --candidate next
current_python="$(
  sed -n 's/.*latest_reviewed_stable: "\(3\.[0-9]*\)".*/\1/p' \
    "$repo_root/profiles/catalog.yaml"
)"
current_minor="${current_python#3.}"
next_python="3.$((current_minor + 1))"
following_python="3.$((current_minor + 2))"
next_ruff="${next_python/./}"
test "$(cat "$version_policy_fixture/.python-version")" = "$next_python"
grep -q "^requires-python = \">=$next_python,<$following_python\"$" \
  "$version_policy_fixture/pyproject.toml"
grep -q "^target-version = \"py$next_ruff\"$" \
  "$version_policy_fixture/pyproject.toml"
grep -q "latest_reviewed_stable: \"$next_python\"" \
  "$version_policy_fixture/profiles/catalog.yaml"
grep -q "^    - \"$current_python\"$" \
  "$version_policy_fixture/copier.yml"
grep -q "^    - \"$next_python\"$" \
  "$version_policy_fixture/copier.yml"

test -f AGENTS.md
test "$(wc -l < AGENTS.md)" -le 200
test "$(cat CLAUDE.md)" = "@AGENTS.md"
test -f docs/index.html
test -f site/index.html
test -f site/styles.css
test -f site/app.js
test -f scripts/render_site.py
test -f docs/README.md
test -f docs/adr/README.md
test -f docs/adr/portable-decision-site.md
grep -q '可重現的 self-contained HTML' \
  docs/adr/portable-decision-site.md
grep -q '不自動保存聊天逐字稿' \
  docs/adr/portable-decision-site.md
grep -q 'Durable Project Memory' docs/README.md
grep -q 'Spec-Driven Development' docs/README.md
grep -q 'Architecture Decision Records' docs/README.md
grep -q 'Test-Driven Development' docs/README.md
grep -q 'Behavior-Driven Development' docs/README.md
test -f docs/pilot-adoption.md
test -f docs/artifact-consumption.md
grep -q '產生 attestation 只證明' docs/artifact-consumption.md
grep -q 'docs/artifact-consumption.md' README.md
grep -q 'ai-guardrail' docs/pilot-adoption.md
grep -q 'run 32664445831' docs/pilot-adoption.md
grep -q 'docs/pilot-adoption.md' README.md
test "$(grep -c '^[[:space:]]*stage: beta$' profiles/catalog.yaml)" -eq 2
test "$(grep -c '^[[:space:]]*stage: alpha$' profiles/catalog.yaml)" -eq 5
grep -q '<title>CSARC Repo Template｜AI 輔助 SDLC 團隊公版</title>' \
  docs/index.html
grep -q '先辨識 GitHub 方案' docs/index.html
grep -q 'Code Security／Secret Protection 另購' docs/index.html
grep -q '外部基準與實測｜' docs/index.html
grep -q 'actions/runs/32645380139' docs/index.html
grep -q '真實 consuming repo 與採用證據' docs/index.html
grep -q 'issues/74' docs/index.html
grep -q 'issues/79' docs/index.html
grep -q 'Spec 格式決策｜' docs/index.html
grep -q '預設 Issue，明確 Story 才建 Milestone' docs/index.html
grep -q '<meta name="robots" content="noindex,nofollow">' docs/index.html
grep -q 'internal-notice' docs/index.html
grep -q '請勿公開分享此連結' docs/index.html
grep -q '存取控制決策｜' docs/index.html
grep -q '可維護來源 → self-contained HTML' docs/index.html
grep -q 'docs/adr/portable-decision-site.md' docs/index.html
grep -q 'durable project memory' docs/index.html
grep -q 'Spec-Driven Development' docs/index.html
grep -q 'Architecture Decision Records' docs/index.html
grep -q 'Test-Driven Development' docs/index.html
grep -q 'Behavior-Driven Development' docs/index.html
grep -q 'actions/runs/32662029395' docs/index.html
grep -q 'Live integration smoke' docs/index.html
test -f docs/robots.txt
grep -q '^Disallow: /$' docs/robots.txt
test -f docs/agent-install.md
grep -q 'Run the requested `csarc init`, `adopt`, or `update` command with' \
  docs/agent-install.md
grep -q 'docs/index.html' README.md
grep -q '內部限閱' README.md
grep -q '線上整合證據' README.md
test -f docs/live-integration.md
test -f docs/ci-policy.md
grep -q '模板 repo 的導入前基線是一般 PR update 約 14' docs/ci-policy.md
grep -q '孤立 Issue 決策樹' docs/ci-policy.md
grep -q 'dev/i<Issue 編號>-<簡稱>' docs/ci-policy.md
grep -q 'Maintainer walkthrough' docs/ci-policy.md
grep -q 'Home Assistant core CI' docs/ci-policy.md
grep -q 'promotion 批次建立 SemVer' docs/index.html
grep -q '只代表靜態與合成驗證通過' docs/live-integration.md
test -x scripts/run-live-workflow-probe
test -f .github/workflows/live-integration.yml
test -f .github/workflows/release-consumption.yml
grep -q '^  decision-site:$' .github/workflows/ci.yml
grep -q 'name: portable-decision-site' .github/workflows/ci.yml
test ! -e template/.github/workflows/live-integration.yml
test ! -e template/.github/workflows/release-consumption.yml
test ! -e template/scripts/run-live-workflow-probe
test ! -e template/scripts/verify_release_consumption.py
grep -q '^      actions: write$' .github/workflows/live-integration.yml
grep -q '^            capability: OSV$' .github/workflows/live-integration.yml
grep -q '^            capability: Release Please$' .github/workflows/live-integration.yml
grep -q '^            capability: Release handoff$' .github/workflows/live-integration.yml
grep -q '^            capability: Governance drift$' .github/workflows/live-integration.yml
grep -q '^  workflow_dispatch:$' .github/workflows/osv.yml
grep -q '^  workflow_dispatch:$' template/.github/workflows/osv.yml
grep -q 'uvx --from csarc-repo-cli csarc init' README.md
grep -q 'uvx --from csarc-repo-cli csarc adopt' README.md
grep -q 'uvx --from csarc-repo-cli csarc update' README.md
grep -q -- '--report-dir ../csarc-adoption-report' README.md
grep -q 'generated Markdown and PDF' docs/agent-install.md
grep -q 'csarc-adoption-report' docs/index.html
grep -q 'repo 外路徑' docs/pilot-adoption.md
test "$(grep -c '^目標路徑：' README.md)" -eq 3
test "$(grep -c '^來源 repository：https://github.com/Innoguard-Cyber-Arch/csarc-repo-template$' README.md)" -eq 3
test "$(grep -c '^核准版本：最新穩定版$' README.md)" -eq 3
test "$(grep -c '^核准 commit：<resolved-full-commit-sha>$' README.md)" -eq 3
test "$(grep -c '^安裝指南：https://raw.githubusercontent.com/Innoguard-Cyber-Arch/csarc-repo-template/<resolved-full-commit-sha>/docs/agent-install.md$' README.md)" -eq 3
grep -q '"draft": true' release-please-config.json
grep -q '"force-tag-creation": true' release-please-config.json
grep -q 'gh release verify "$RELEASE_TAG"' \
  .github/workflows/release-template.yml
grep -q '^      attestations: read$' .github/workflows/release-template.yml
grep -q 'isImmutable,isDraft,isPrerelease' \
  .github/workflows/release-template.yml
grep -q 'Release is already published and immutable' \
  .github/workflows/release-template.yml
grep -q 'for attempt in {1..24}; do' \
  .github/workflows/release-template.yml
if grep -q 'repos/${GITHUB_REPOSITORY}/immutable-releases' \
  .github/workflows/release-template.yml; then
  echo "Release jobs must not require the admin-only immutable-releases endpoint." >&2
  exit 1
fi
grep -q 'render_release_prompt.py' .github/workflows/release-template.yml
test "$(grep -c 'release_policy.py prepare' \
  .github/workflows/release-template.yml)" = 2
grep -q 'source_run_id:' .github/workflows/release-template.yml
grep -q 'release_policy.py verify-boundary' \
  .github/workflows/release-template.yml
if grep -q 'tags: \["v\*"\]' .github/workflows/release-template.yml; then
  echo "Release artifacts must require an explicit verified-source dispatch."
  exit 1
fi
grep -q 'gh release create "$RELEASE_TAG" --verify-tag --draft --generate-notes' \
  .github/workflows/release-template.yml
grep -q "CSARC_ENABLE_PYPI_PUBLISHING == 'true'" \
  .github/workflows/release-template.yml
test -f scripts/release_policy.py
test -f version.txt
release_tag="$(git tag --points-at HEAD --list 'v[0-9]*' --sort=-version:refname | head -1)"
version_args=(verify-version --root .)
if [[ -n "$release_tag" ]]; then
  version_args+=(--tag "$release_tag")
fi
uv run --no-project python scripts/release_policy.py "${version_args[@]}"
uv run python - <<'PY'
import json
from pathlib import Path

release_config = json.loads(
    Path("release-please-config.json").read_text(encoding="utf-8")
)
if release_config["release-type"] != "simple":
    raise SystemExit("The template repository must use the simple release type.")
extra_paths = {
    item["path"] for item in release_config["packages"]["."]["extra-files"]
}
if not {"pyproject.toml", "uv.lock", "README.md", "docs/index.html"} <= extra_paths:
    raise SystemExit("The template release does not update every visible version.")
template_manifest = json.loads(
    Path("template/.release-please-manifest.json").read_text(encoding="utf-8")
)["."]
if template_manifest != "0.1.0" or Path("template/version.txt").read_text().strip() != "0.1.0":
    raise SystemExit("Generated projects must keep their independent 0.1.0 baseline.")
PY
grep -q '^## Working loop$' AGENTS.md
grep -q '^## Commands$' AGENTS.md
grep -q '^## Code Review Rules$' AGENTS.md
grep -q "pull request chain ends there" AGENTS.md
grep -q "against its delivery branch or immediate parent in the stack" AGENTS.md
grep -q 'complete every task in the pull request and referenced Issue' AGENTS.md
grep -q 'one branch and one Git worktree per task' AGENTS.md
grep -q 'Alpha 自行合併 / self-merged' AGENTS.md
grep -q 'search open and closed Issues' AGENTS.md
grep -q 'Never silently reverse an earlier decision' AGENTS.md
grep -q 'whether creating through the UI, CLI, or API' AGENTS.md
grep -q 'create and link a follow-up Issue first' AGENTS.md
grep -Fq 'run `./scripts/cleanup-worktrees` in its default dry-run mode and report any candidates' \
  AGENTS.md
grep -Fq 'run `./scripts/cleanup-worktrees` in its default dry-run mode and report any candidates' \
  template/AGENTS.md.jinja
grep -q '^## References$' docs/milestone-description.md
grep -q 'bounded' docs/agent-install.md
grep -q '沿用、取代或駁回' docs/index.html
required_readme_headings=(
  "專案概述"
  "快速開始"
  "技術與目錄"
  "開發與驗證"
  "設定與密鑰"
  "發布與維運"
  "負責人與支援"
  "公版更新"
)
for heading in "${required_readme_headings[@]}"; do
  if ! grep -qFx "## $heading" README.md; then
    echo "README.md is missing required section: $heading"
    exit 1
  fi
done
unsupported_instruction_paths=(
  .cursorrules
  .windsurfrules
  .clinerules
  GEMINI.md
  .github/copilot-instructions.md
  .cursor/rules
  .claude/rules
)
for unsupported_path in "${unsupported_instruction_paths[@]}"; do
  test ! -e "$unsupported_path"
done

bash -n scripts/sync-paired-files.sh
./scripts/sync-paired-files.sh --check

# The check must compare template/ with the generator's deterministic output:
# corrupt one generated copy, confirm --check rejects it, confirm the plain
# generator run reproduces the exact source content, and confirm --check
# accepts the regenerated result.
sync_regression_fixture="$fixture_root/sync-paired-files"
rsync -a --exclude=.git --exclude=.venv "$repo_root/" "$sync_regression_fixture/"
printf '# drift injected by verify-template.sh regression test\n' \
  >> "$sync_regression_fixture/template/zizmor.yml"
if (cd "$sync_regression_fixture" && ./scripts/sync-paired-files.sh --check); then
  echo "sync-paired-files.sh --check must fail on a drifted template/ copy."
  exit 1
fi
(cd "$sync_regression_fixture" && ./scripts/sync-paired-files.sh)
cmp -s "$sync_regression_fixture/zizmor.yml" \
  "$sync_regression_fixture/template/zizmor.yml"
(cd "$sync_regression_fixture" && ./scripts/sync-paired-files.sh --check)

# Executable bits are part of Git's file mode and must match in both directions.
chmod +x "$sync_regression_fixture/template/zizmor.yml"
if (cd "$sync_regression_fixture" && ./scripts/sync-paired-files.sh --check); then
  echo "sync-paired-files.sh --check must fail on executable-bit drift."
  exit 1
fi
(cd "$sync_regression_fixture" && ./scripts/sync-paired-files.sh)
test ! -x "$sync_regression_fixture/template/zizmor.yml"
(cd "$sync_regression_fixture" && ./scripts/sync-paired-files.sh --check)

# A source file with no template/ counterpart must fail loudly instead of
# silently skipping the pair.
rm "$sync_regression_fixture/template/CLAUDE.md"
if (cd "$sync_regression_fixture" && ./scripts/sync-paired-files.sh --check); then
  echo "sync-paired-files.sh --check must fail when a template/ copy is missing."
  exit 1
fi

test "$(grep -c '^    id:' .github/ISSUE_TEMPLATE/work-item.yml)" -eq 4
test "$(grep -c '^      required: true$' .github/ISSUE_TEMPLATE/work-item.yml)" -eq 3
test "$(grep -c '^      required: false$' .github/ISSUE_TEMPLATE/work-item.yml)" -eq 1
grep -q '^    id: kind$' .github/ISSUE_TEMPLATE/work-item.yml
grep -q '^    id: problem$' .github/ISSUE_TEMPLATE/work-item.yml
grep -q '^    id: acceptance$' .github/ISSUE_TEMPLATE/work-item.yml
grep -q '^    id: supplement$' .github/ISSUE_TEMPLATE/work-item.yml
test "$(grep -Ec '^      label: (類型|問題|完成條件|補充)$' \
  .github/ISSUE_TEMPLATE/work-item.yml)" -eq 4
grep -q '搜尋相關 open／closed Issues' .github/ISSUE_TEMPLATE/work-item.yml
grep -q '^        - duplicate$' .github/ISSUE_TEMPLATE/work-item.yml
test "$(grep -c '^## ' .github/pull_request_template.md)" -eq 3
grep -q '^## Purpose$' .github/pull_request_template.md
grep -q '^## 完成清單$' .github/pull_request_template.md
grep -q '^## 補充$' .github/pull_request_template.md
grep -q '^  pull_request:$' .github/workflows/governance-comment.yml
grep -q 'types: \[opened, reopened, ready_for_review\]' \
  .github/workflows/governance-comment.yml
grep -q '^  pull-requests: write$' .github/workflows/governance-comment.yml
if grep -q '^  pull_request_target:$' .github/workflows/governance-comment.yml; then
  echo "Reviewer workflow must not use pull_request_target."
  exit 1
fi
if grep -q 'synchronize' .github/workflows/governance-comment.yml; then
  echo "Reviewer assignment must not repeat on every pull request update."
  exit 1
fi
grep -q '!github.event.pull_request.draft' \
  .github/workflows/governance-comment.yml
grep -q 'ref: \${{ github.event.pull_request.base.sha }}' \
  .github/workflows/governance-comment.yml
grep -q 'configured_reviewers.*\.github/REVIEWERS' \
  .github/workflows/governance-comment.yml
grep -Fq '== "$PR_AUTHOR"' .github/workflows/governance-comment.yml
grep -q 'repos/\$GITHUB_REPOSITORY/pulls/\$PR_NUMBER/requested_reviewers' \
  .github/workflows/governance-comment.yml
grep -Fq -- '-f "reviewers[]=$reviewer"' \
  .github/workflows/governance-comment.yml
grep -q 'DEFAULT_OWNER = "@Innoguard-Cyber-Arch/arch"' src/csarc_cli/cli.py
grep -Fqx '* @Innoguard-Cyber-Arch/arch' .github/CODEOWNERS
grep -Fqx '@jachline28' .github/REVIEWERS
grep -q '所有方案都先用 repository teams API 驗證' docs/index.html
grep -q 'Free private 不支援 team review request' template/site/index.html.jinja

grep -q "'## Purpose'" .github/workflows/python-version-policy.yml
grep -q "'## 完成清單'" .github/workflows/python-version-policy.yml
grep -q "'## 補充'" .github/workflows/python-version-policy.yml
grep -q 'Validate pull request policy' .github/workflows/pr-policy.yml
grep -q 'Select exactly one PR label' .github/workflows/pr-policy.yml
grep -q 'duplicate label is an Issue disposition' .github/workflows/pr-policy.yml
grep -q 'type/<issue-number>-short-slug' .github/workflows/pr-policy.yml
grep -q 'Complete every pull request checklist item' \
  .github/workflows/pr-policy.yml
grep -q 'still has unchecked acceptance tasks' \
  .github/workflows/pr-policy.yml
grep -q 'Only dev promotion or release-please may target main in dev mode.' \
  .github/workflows/pr-policy.yml
grep -q '^  merge_group:$' .github/workflows/ci.yml
grep -q '^  workflow_dispatch:$' .github/workflows/ci.yml
if grep -q '^  push:$' .github/workflows/ci.yml; then
  echo "CI must not repeat a pull request suite after merge."
  exit 1
fi
grep -q '^  schedule:$' .github/workflows/osv.yml
if grep -q '^  pull_request:$' .github/workflows/osv.yml; then
  echo "Standalone OSV must not duplicate change-aware CI scans."
  exit 1
fi
grep -q 'gh pr edit "$pr_url" --add-label enhancement' \
  .github/workflows/python-version-policy.yml
if grep -Eq -- '--admin|gh pr merge|CSARC_VERSION_BOT_APP_ID' \
  .github/workflows/python-version-policy.yml \
  scripts/apply-repository-settings.sh \
  template/scripts/apply-repository-settings.sh; then
  echo "Version automation must not bypass or perform repository merges."
  exit 1
fi
test "$(grep -c '^      security-events: write$' .github/workflows/osv.yml)" -eq 1
test "$(grep -c '^      security-events: write$' template/.github/workflows/osv.yml)" -eq 1
grep -q '^  schedule:$' .github/workflows/zizmor.yml
if grep -q '^  pull_request:$' .github/workflows/zizmor.yml; then
  echo "Standalone Zizmor must not duplicate change-aware CI audits."
  exit 1
fi
grep -q 'target-branch: dev/next' .github/dependabot.yml
grep -q '"name": "CSARC protected branches"' policies/rulesets.json

# Issues #74 and #110: keep the native dependency updater so its PRs trigger
# required checks without another privileged identity. pnpm also enforces the
# waiting window during local and CI resolution; trustPolicy stays independent.
grep -q 'consolidation_status: native_tools_retained' profiles/catalog.yaml
grep -q 'automation: github_dependabot' profiles/catalog.yaml
grep -q 'stays_independent_of_renovate: true' profiles/catalog.yaml
grep -q '決定｜保留 Dependabot 與 pnpm 的原生門禁' \
  docs/index.html
grep -q 'Optional integration capability matrix' docs/index.html
grep -q 'available.*request-owner.*fallback' docs/index.html
grep -q 'optional_integration_preflight' scripts/release_policy.py
grep -q '選配整合依目前權限引導' README.md
for renovate_config_path in \
  renovate.json renovate.json5 .github/renovate.json .renovaterc.json; do
  test ! -e "$renovate_config_path"
  test ! -e "template/$renovate_config_path"
done
uv run python - <<'PY'
import json
from pathlib import Path

ruleset = json.loads(Path("policies/rulesets.json").read_text(encoding="utf-8"))
rules = {rule["type"]: rule.get("parameters", {}) for rule in ruleset["rules"]}
pull_request = rules["pull_request"]
checks = {
    check["context"]
    for check in rules["required_status_checks"]["required_status_checks"]
}
if ruleset["enforcement"] != "active":
    raise SystemExit("The repository Ruleset must be active.")
if pull_request["required_approving_review_count"] < 1:
    raise SystemExit("The repository Ruleset must require approval.")
if not pull_request["require_code_owner_review"]:
    raise SystemExit("The repository Ruleset must require CODEOWNER review.")
if not {
    "delivery-sync",
    "promotion",
    "verify",
    "title",
} <= checks:
    raise SystemExit("The repository Ruleset is missing required checks.")
PY
grep -q '"refs/heads/dev/\*"' policies/rulesets.json

pr_title_pattern='^(feat|fix|docs|refactor|test|build|ci|chore|revert)(\([a-z0-9._/-]+\))?(!)?: .+'
valid_pr_title() {
  local title="$1"
  [[ "$title" =~ $pr_title_pattern ]] &&
    ! printf '%s' "$title" | LC_ALL=C grep -q '[^ -~]'
}
valid_pr_title "feat: add report export"
valid_pr_title "feat!: drop v1 endpoint"
valid_pr_title "feat(api)!: drop v1 endpoint"
if valid_pr_title "feat: 新增報表功能"; then
  echo "PR titles containing non-ASCII characters must be rejected."
  exit 1
fi

# Invalid trust-boundary values must fail before producing a usable project.
if uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_slug="Invalid/Slug" \
  --data language=ci \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  "$repo_root" "$fixture_root/invalid-slug" >/dev/null 2>&1; then
  echo "Copier accepted an invalid project slug."
  exit 1
fi
if uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_slug="valid-project" \
  --data package_name="9invalid" \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  "$repo_root" "$fixture_root/invalid-package" >/dev/null 2>&1; then
  echo "Copier accepted an invalid Python package name."
  exit 1
fi
if uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_slug="valid-project" \
  --data language=ci \
  --data use_reusable_workflow=true \
  --data workflow_ref="gggggggggggggggggggggggggggggggggggggggg" \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  "$repo_root" "$fixture_root/invalid-workflow-ref" >/dev/null 2>&1; then
  echo "Copier accepted a non-hexadecimal workflow commit SHA."
  exit 1
fi

# Issue #140: every selectable minimum must generate the exact .0 lower bound
# plus the latest patch of each supported feature release. Inline and reusable
# workflows must describe the same runtime set while keeping one required
# aggregate check.
for python_minimum in 3.12 3.13 3.14; do
  for reusable in false true; do
    fixture_name="python-matrix-${python_minimum//./-}-${reusable}"
    matrix_fixture="$fixture_root/$fixture_name"
    copier_args=(
      --trust --defaults --vcs-ref HEAD
      --data "project_slug=$fixture_name"
      --data "package_name=${fixture_name//-/_}"
      --data code_owner="@Innoguard-Cyber-Arch/template-maintainers"
      --data python_support_mode=minimum
      --data "python_min_version=$python_minimum"
      --data "use_reusable_workflow=$reusable"
    )
    if [[ "$reusable" == true ]]; then
      copier_args+=(
        --data workflow_ref=1111111111111111111111111111111111111111
      )
    fi
    uv run copier copy "${copier_args[@]}" "$repo_root" "$matrix_fixture"

    expected_ruff="py${python_minimum//./}"
    grep -q "^requires-python = \">=$python_minimum\"$" \
      "$matrix_fixture/pyproject.toml"
    grep -q "^target-version = \"$expected_ruff\"$" \
      "$matrix_fixture/pyproject.toml"
    grep -q "^python_version = \"$python_minimum\"$" \
      "$matrix_fixture/pyproject.toml"
    uv run python - \
      "$matrix_fixture/.github/workflows/ci.yml" \
      "$matrix_fixture/policies/rulesets.json" \
      "$python_minimum" "$reusable" <<'PY'
import json
import re
import sys
from pathlib import Path

workflow_path, ruleset_path, minimum, reusable_text = sys.argv[1:]
latest_minor = 14
minimum_minor = int(minimum.split(".")[1])
expected = [f"{minimum}.0"] + [
    f"3.{minor}" for minor in range(minimum_minor, latest_minor + 1)
]
workflow = Path(workflow_path).read_text(encoding="utf-8")
if reusable_text == "true":
    match = re.search(r"python-versions: >-\n\s+(\[[^\n]+\])", workflow)
    if match is None:
        raise SystemExit("Reusable workflow runtime input is missing")
    actual = json.loads(match.group(1))
else:
    match = re.search(
        r"runtime:\n((?:\s+- \"[^\"]+\"\n)+)", workflow
    )
    if match is None:
        raise SystemExit("Inline workflow runtime matrix is missing")
    actual = re.findall(r'- "([^\"]+)"', match.group(1))
if actual != expected:
    raise SystemExit(f"Unexpected Python matrix: {actual!r} != {expected!r}")
ruleset = json.loads(Path(ruleset_path).read_text(encoding="utf-8"))
checks = next(
    rule["parameters"]["required_status_checks"]
    for rule in ruleset["rules"]
    if rule["type"] == "required_status_checks"
)
if "verify" not in {check["context"] for check in checks}:
    raise SystemExit("Missing required aggregate check: verify")
PY
  done
done

# Default project: strict global coverage and optional features disabled.
uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_name='Template "Smoke" Test' \
  --data project_slug="template-smoke-test" \
  --data $'project_description=A "quoted" project\n第二行' \
  --data package_name="template_smoke_test" \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  "$repo_root" "$fixture_root/default-project"
prime_gitleaks_cache "$fixture_root/default-project"
assert_agent_guidance "$fixture_root/default-project"

git -C "$fixture_root/default-project" init -q -b main
git -C "$fixture_root/default-project" add .
git -C "$fixture_root/default-project" diff --cached --check

test -f "$fixture_root/default-project/.copier-answers.yml"
root_only_paths=(
  scripts/verify-template.sh
  scripts/sync-paired-files.sh
  scripts/update_python_version.py
  scripts/report_dependency_ceiling.py
  .github/workflows/reusable-ci.yml
  .github/workflows/release-template.yml
  .github/workflows/python-version-policy.yml
)
for root_only_path in "${root_only_paths[@]}"; do
  if [[ -e "$fixture_root/default-project/$root_only_path" ]]; then
    echo "Generated projects must not receive template-repository-only file: $root_only_path"
    exit 1
  fi
done
diff -B -w "$repo_root/.github/dependabot.yml" \
  "$fixture_root/default-project/.github/dependabot.yml"
for renovate_config_path in \
  renovate.json renovate.json5 .github/renovate.json .renovaterc.json; do
  test ! -e "$fixture_root/default-project/$renovate_config_path"
done
grep -q 'language: python' "$fixture_root/default-project/.copier-answers.yml"
grep -q 'project_visibility: private' \
  "$fixture_root/default-project/.copier-answers.yml"
grep -q 'enable_codeql: false' \
  "$fixture_root/default-project/.copier-answers.yml"
test ! -f "$fixture_root/default-project/.github/workflows/codeql.yml"
grep -q '"language_profile": "python"' \
  "$fixture_root/default-project/.csarc/profile.json"
grep -q '"branch_strategy": "delivery"' \
  "$fixture_root/default-project/.csarc/profile.json"
test "$("$fixture_root/default-project/scripts/detect-language-profile" --suggest)" = \
  "python"
test -f "$fixture_root/default-project/CHANGELOG.md"
test -f "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q 'gh release upload "$GITHUB_REF_NAME"' \
  "$fixture_root/default-project/.github/workflows/release.yml"
grep -q 'release-metadata.json' \
  "$fixture_root/default-project/.github/workflows/release.yml"
grep -q 'No release distribution was created' \
  "$fixture_root/default-project/.github/workflows/release.yml"
if grep -q 'actions/attest@' \
  "$fixture_root/default-project/.github/workflows/release.yml"; then
  echo "Release attestations must remain opt-in."
  exit 1
fi
if grep -q '^  publish-python:\|^  publish-npm:' \
  "$fixture_root/default-project/.github/workflows/release.yml"; then
  echo "Registry publishing must remain opt-in."
  exit 1
fi

# Public projects default release attestations on; private/internal stay explicit opt-in.
uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_slug="public-visibility-test" \
  --data package_name="public_visibility_test" \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  --data reviewers="@alice,@bob" \
  --data project_visibility=public \
  "$repo_root" "$fixture_root/public-visibility-project"
prime_gitleaks_cache "$fixture_root/public-visibility-project"
grep -q 'project_visibility: public' \
  "$fixture_root/public-visibility-project/.copier-answers.yml"
grep -q 'enable_release_attestations: true' \
  "$fixture_root/public-visibility-project/.copier-answers.yml"
grep -q 'enable_codeql: true' \
  "$fixture_root/public-visibility-project/.copier-answers.yml"
test -f "$fixture_root/public-visibility-project/.github/workflows/codeql.yml"
grep -q 'language: \["python"\]' \
  "$fixture_root/public-visibility-project/.github/workflows/codeql.yml"
grep -q 'security-events: write' \
  "$fixture_root/public-visibility-project/.github/workflows/codeql.yml"
test "$(sed '/^#/d; /^$/d' "$fixture_root/public-visibility-project/.github/REVIEWERS")" = \
  $'@alice\n@bob'
grep -q 'github/codeql-action/init@4c0873ef8656cb3c50b3f42fb63bc1ade0cfa827' \
  "$fixture_root/public-visibility-project/.github/workflows/codeql.yml"
test "$(grep -c 'actions/attest@' \
  "$fixture_root/public-visibility-project/.github/workflows/release.yml")" -eq 2
grep -q 'attestations: write' \
  "$fixture_root/public-visibility-project/.github/workflows/release.yml"
grep -q 'id-token: write' \
  "$fixture_root/public-visibility-project/.github/workflows/release.yml"

uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_slug="internal-visibility-test" \
  --data package_name="internal_visibility_test" \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  --data project_visibility=internal \
  "$repo_root" "$fixture_root/internal-visibility-project"
prime_gitleaks_cache "$fixture_root/internal-visibility-project"
grep -q 'project_visibility: internal' \
  "$fixture_root/internal-visibility-project/.copier-answers.yml"
grep -q 'enable_release_attestations: false' \
  "$fixture_root/internal-visibility-project/.copier-answers.yml"
grep -q 'enable_codeql: false' \
  "$fixture_root/internal-visibility-project/.copier-answers.yml"
test ! -f "$fixture_root/internal-visibility-project/.github/workflows/codeql.yml"
grep -q 'id="fleet-governance-thresholds"' docs/index.html
grep -q '10 個活躍 consuming repo' docs/index.html
grep -q '30 天內同類漂移' docs/index.html
if grep -q 'actions/attest@' \
  "$fixture_root/internal-visibility-project/.github/workflows/release.yml"; then
  echo "Internal projects must keep release attestations opt-in by default."
  exit 1
fi
test ! -f "$fixture_root/default-project/.github/workflows/template-update.yml"
test ! -f "$fixture_root/default-project/scripts/check-template-update"
test ! -f "$fixture_root/default-project/.github/workflows/governance-drift.yml"
test ! -f "$fixture_root/default-project/scripts/check-governance-drift"
test -f "$fixture_root/default-project/release-please-config.json"
test -f "$fixture_root/default-project/.release-please-manifest.json"
test "$(cat "$fixture_root/default-project/.python-version")" = "3.14"
test -f "$fixture_root/default-project/AGENTS.md"
test -f "$fixture_root/default-project/docs/index.html"
test -f "$fixture_root/default-project/docs/site-content.js"
test -f "$fixture_root/default-project/docs/site-theme.css"
test -f "$fixture_root/default-project/site/index.html"
test -f "$fixture_root/default-project/site/styles.css"
test -f "$fixture_root/default-project/site/app.js"
test -f "$fixture_root/default-project/scripts/render_site.py"
test -f "$fixture_root/default-project/docs/README.md"
test -f "$fixture_root/default-project/docs/adr/README.md"
grep -q '不得保存完整聊天逐字稿' \
  "$fixture_root/default-project/docs/README.md"
grep -q 'Durable Project Memory' \
  "$fixture_root/default-project/docs/README.md"
grep -q 'Spec-Driven Development' \
  "$fixture_root/default-project/docs/README.md"
grep -q 'Architecture Decision Records' \
  "$fixture_root/default-project/docs/README.md"
grep -q 'Test-Driven Development' \
  "$fixture_root/default-project/docs/README.md"
grep -q 'Behavior-Driven Development' \
  "$fixture_root/default-project/docs/README.md"
grep -q 'docs/decisions/' \
  "$fixture_root/default-project/docs/README.md"
grep -q 'Never store a raw conversation transcript' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'GitHub 方案與門禁' \
  "$fixture_root/default-project/docs/index.html"
grep -q 'id="release-modes"' \
  "$fixture_root/default-project/docs/index.html"
grep -q 'Verification only' \
  "$fixture_root/default-project/docs/index.html"
grep -q 'apply-repository-settings.sh plan' \
  "$fixture_root/default-project/README.md"
grep -q 'available.*request-owner.*fallback' \
  "$fixture_root/default-project/README.md"
grep -q '導入 preflight 會把 Renovate' \
  "$fixture_root/default-project/docs/site-content.js"
uv run python - "$fixture_root/default-project/pyproject.toml" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as pyproject:
    project = tomllib.load(pyproject)["project"]
assert project["description"] == 'A "quoted" project\n第二行'
PY
grep -Fq 'Template \"Smoke\" Test' \
  "$fixture_root/default-project/docs/site-content.js"
grep -q 'window.CSARC_SITE_CONTENT' \
  "$fixture_root/default-project/docs/site-content.js"
grep -q 'schemaVersion: 1' \
  "$fixture_root/default-project/docs/site-content.js"
grep -q 'data-bundled-from="../docs/site-content.js"' \
  "$fixture_root/default-project/docs/index.html"
if grep -Eq '<link[^>]+rel="stylesheet"|<script[^>]+src=' \
  "$fixture_root/default-project/docs/index.html"; then
  echo "Generated decision site contains an external runtime asset."
  exit 1
fi
grep -q 'stage: "alpha"' \
  "$fixture_root/default-project/docs/site-content.js"
grep -q '^## Scope and sources of truth$' \
  "$fixture_root/default-project/AGENTS.md"
grep -q '^## Commands$' "$fixture_root/default-project/AGENTS.md"
grep -q '^## Code Review Rules$' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'pull request chain ends there' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'against its delivery branch or immediate parent in the stack' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'complete every task in the pull request and referenced Issue' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'one branch and one Git worktree per task' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'search open and closed Issues' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'whether creating through the UI, CLI, or API' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'create and link a follow-up Issue first' \
  "$fixture_root/default-project/AGENTS.md"
grep -Fq 'run `./scripts/cleanup-worktrees` in its default dry-run mode and report any candidates' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'uv run pytest <test-path>' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'Python setup: `uv sync --locked`' \
  "$fixture_root/default-project/AGENTS.md"
if grep -q 'TypeScript setup:' "$fixture_root/default-project/AGENTS.md"; then
  echo "Python-only AGENTS.md must not include TypeScript setup."
  exit 1
fi
if grep -q 'pnpm exec vitest' "$fixture_root/default-project/AGENTS.md"; then
  echo "Python-only AGENTS.md must not include TypeScript commands."
  exit 1
fi
test "$(cat "$fixture_root/default-project/CLAUDE.md")" = "@AGENTS.md"
test -f "$fixture_root/default-project/policies/rulesets.json"
test -f "$fixture_root/default-project/.github/workflows/governance-comment.yml"
test -f "$fixture_root/default-project/.github/workflows/promotion.yml"
test -f "$fixture_root/default-project/docs/ci-policy.md"
grep -q '穩定的 `verify` aggregate context' \
  "$fixture_root/default-project/docs/ci-policy.md"
grep -q '孤立 Issue 決策樹' \
  "$fixture_root/default-project/docs/ci-policy.md"
grep -q 'dev/i<Issue 編號>-<簡稱>' \
  "$fixture_root/default-project/docs/ci-policy.md"
grep -q 'Delivery route' \
  "$fixture_root/default-project/docs/index.html"
grep -q 'dev/i<Issue 編號>-<簡稱>' \
  "$fixture_root/default-project/README.md"
grep -Fqx '@jachline28' "$fixture_root/default-project/.github/REVIEWERS"
grep -q '^  pull_request:$' \
  "$fixture_root/default-project/.github/workflows/governance-comment.yml"
if grep -q 'apply-repository-settings.sh check' \
  "$fixture_root/default-project/.github/workflows/governance-comment.yml"; then
  echo "Reviewer assignment must not repeat remote governance checks."
  exit 1
fi
if grep -q -- '--slurp' \
  "$fixture_root/default-project/.github/workflows/governance-comment.yml"; then
  echo "Governance comments must use gh flags supported by GitHub-hosted runners."
  exit 1
fi
grep -q 'Free organization＋private' \
  "$fixture_root/default-project/README.md"
grep -q 'DEGRADED' \
  "$fixture_root/default-project/README.md"
grep -q '"context": "verify"' \
  "$fixture_root/default-project/policies/rulesets.json"
grep -q '"context": "delivery-sync"' \
  "$fixture_root/default-project/policies/rulesets.json"
grep -q '"context": "promotion"' \
  "$fixture_root/default-project/policies/rulesets.json"
grep -q '"refs/heads/dev/\*"' \
  "$fixture_root/default-project/policies/rulesets.json"
test -x "$fixture_root/default-project/scripts/apply-repository-settings.sh"
test -x "$fixture_root/default-project/scripts/check-update-conflicts"
test -x "$fixture_root/default-project/scripts/install-gitleaks"
test -x "$fixture_root/default-project/scripts/verify-fast"
test -f "$fixture_root/default-project/scripts/ci_tier.py"
test -x "$fixture_root/default-project/scripts/promotion_gate.py"
test ! -f "$fixture_root/default-project/.pre-commit-config.yaml"
test ! -f "$fixture_root/default-project/package.json"
test ! -f "$fixture_root/default-project/pnpm-workspace.yaml"
test ! -d "$fixture_root/default-project/typescript"
grep -q 'Coverage 是找出未測程式碼的訊號' \
  "$fixture_root/default-project/README.md"
grep -q 'CODEOWNERS、repository、Actions、政策標籤與有效 Ruleset' \
  "$fixture_root/default-project/README.md"
grep -q '^## Actions quota fallback$' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'Actions quota fallback attestation' \
  "$fixture_root/default-project/docs/ci-policy.md"
grep -q '付款失敗、budget.*平台.*設定.*權限.*未知原因.*測試失敗' \
  "$fixture_root/default-project/docs/index.html"
grep -q '一般 Issue PR 跑 change-aware fast checks' \
  "$fixture_root/default-project/docs/site-content.js"
grep -q 'CODEOWNERS、repository、Actions、政策標籤與有效 Ruleset' \
  "$fixture_root/default-project/docs/index.html"
grep -q 'Administration read' \
  "$fixture_root/default-project/docs/index.html"
grep -q '新案看全域、既有案先看 changed lines' \
  "$fixture_root/default-project/docs/site-content.js"
grep -q '^\.DS_Store$' "$fixture_root/default-project/.gitignore"
grep -q '^Thumbs\.db$' "$fixture_root/default-project/.gitignore"
grep -q '^\.vscode/\*$' "$fixture_root/default-project/.gitignore"
grep -q '^\.venv\*/$' "$fixture_root/default-project/.gitignore"
grep -q '^__pycache__/$' "$fixture_root/default-project/.gitignore"
printf '<<<<<<< ours\n=======\n>>>>>>> theirs\n' > \
  "$fixture_root/default-project/conflict-probe.txt"
if "$fixture_root/default-project/scripts/check-update-conflicts" >/dev/null 2>&1; then
  echo "Copier conflict markers must fail verification."
  exit 1
fi
rm "$fixture_root/default-project/conflict-probe.txt"
: > "$fixture_root/default-project/copier-update.rej"
if "$fixture_root/default-project/scripts/check-update-conflicts" >/dev/null 2>&1; then
  echo "Copier rejection files must fail verification."
  exit 1
fi
rm "$fixture_root/default-project/copier-update.rej"
"$fixture_root/default-project/scripts/check-update-conflicts"
if grep -q '^node_modules/$' "$fixture_root/default-project/.gitignore"; then
  echo "Python-only .gitignore must not contain TypeScript artifacts."
  exit 1
fi
grep -q '^blank_issues_enabled: false$' \
  "$fixture_root/default-project/.github/ISSUE_TEMPLATE/config.yml"
test "$(grep -c '^    id:' \
  "$fixture_root/default-project/.github/ISSUE_TEMPLATE/work-item.yml")" -eq 4
grep -q '^    id: supplement$' \
  "$fixture_root/default-project/.github/ISSUE_TEMPLATE/work-item.yml"
test "$(grep -Ec '^      label: (類型|問題|完成條件|補充)$' \
  "$fixture_root/default-project/.github/ISSUE_TEMPLATE/work-item.yml")" -eq 4
test "$(grep -c '^## ' \
  "$fixture_root/default-project/.github/pull_request_template.md")" -eq 3
grep -q '^## Purpose$' \
  "$fixture_root/default-project/.github/pull_request_template.md"
grep -q '^## 完成清單$' \
  "$fixture_root/default-project/.github/pull_request_template.md"
grep -q '^## 補充$' \
  "$fixture_root/default-project/.github/pull_request_template.md"
grep -q 'Closing keywords require every task' \
  "$fixture_root/default-project/.github/pull_request_template.md"
grep -q 'referenced Issue checklist' \
  "$fixture_root/default-project/docs/index.html"
test -f "$fixture_root/default-project/.github/workflows/issue-triage.yml"
test -f "$fixture_root/default-project/.github/workflows/milestone-lifecycle.yml"
test -f "$fixture_root/default-project/docs/milestone-description.md"
test -f "$fixture_root/default-project/scripts/sync_milestone_state.py"
grep -q '^## Plan$' \
  "$fixture_root/default-project/docs/milestone-description.md"
grep -q '^## References$' \
  "$fixture_root/default-project/docs/milestone-description.md"
grep -q '專案團隊慣用的語言' \
  "$fixture_root/default-project/docs/milestone-description.md"
grep -q 'types: \[closed, reopened, milestoned\]' \
  "$fixture_root/default-project/.github/workflows/milestone-lifecycle.yml"
grep -q 'github.event.issue.milestone.number' \
  "$fixture_root/default-project/.github/workflows/milestone-lifecycle.yml"
grep -q 'docs/milestone-description.md' \
  "$fixture_root/default-project/AGENTS.md"
grep -q '^## References$' \
  "$fixture_root/default-project/docs/milestone-description.md"
grep -q '搜尋 open／closed 歷史工作' \
  "$fixture_root/default-project/docs/index.html"
grep -q '既有決策是沿用、取代或駁回' \
  "$fixture_root/default-project/docs/site-content.js"
grep -q '^# tracking: story$' \
  "$fixture_root/default-project/docs/specs/SPEC-001-example.md"
test -x "$fixture_root/default-project/scripts/test-issue-triage"
test -x "$fixture_root/default-project/scripts/validate-issue-title"
grep -q 'branches: \[main, dev, "dev/\*\*"\]' \
  "$fixture_root/default-project/.github/workflows/spec-to-issue.yml"
grep -q 'target-branch: dev/next' \
  "$fixture_root/default-project/.github/dependabot.yml"
grep -q '^requires-python = ">=3.14,<3.15"$' \
  "$fixture_root/default-project/pyproject.toml"
grep -q '^target-version = "py314"$' \
  "$fixture_root/default-project/pyproject.toml"
grep -q 'python-version:.*$' \
  "$fixture_root/default-project/.github/workflows/ci.yml"
grep -q -- '- "3.14.0"' \
  "$fixture_root/default-project/.github/workflows/ci.yml"
grep -q -- '- "3.14"' \
  "$fixture_root/default-project/.github/workflows/ci.yml"
grep -q '^    needs: \[fast, full, governance, osv, zizmor\]$' \
  "$fixture_root/default-project/.github/workflows/ci.yml"
grep -q '^  governance:$' \
  "$fixture_root/default-project/.github/workflows/ci.yml"
grep -q 'apply-repository-settings.sh check' \
  "$fixture_root/default-project/.github/workflows/ci.yml"
grep -q '^  decision-site:$' \
  "$fixture_root/default-project/.github/workflows/ci.yml"
grep -q 'name: portable-decision-site' \
  "$fixture_root/default-project/.github/workflows/ci.yml"
grep -q '^    needs: governance$' \
  "$fixture_root/default-project/.github/workflows/release.yml"
grep -q '^    needs: source$' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q 'googleapis/release-please-action@45996ed1f6d02564a971a2fa1b5860e934307cf7' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q 'config-file: release-please-config.json' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
# Release automation must adapt with the default token, not wait on a GitHub App.
grep -q 'token: \${{ secrets.GITHUB_TOKEN }}' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q '^      release_created: \${{ steps.release.outputs.release_created }}$' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q '^      tag_name: \${{ steps.release.outputs.tag_name }}$' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q "needs.release-pr.outputs.release_created == 'true'" \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q '^      actions: write$' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q 'gh workflow run "$workflow" --ref "$RELEASE_TAG"' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q 'release_policy.py detect' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q 'release_policy.py release' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q 'Non-default branch run is diagnostic-only' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q "mode == 'verification-only'" \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q 'release-capabilities-\${{ github.run_id }}' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q 'release_policy.py prepare' \
  "$fixture_root/default-project/.github/workflows/release.yml"
grep -q 'release_policy.py verify-boundary' \
  "$fixture_root/default-project/.github/workflows/release.yml"
grep -q 'source_run_id:' \
  "$fixture_root/default-project/.github/workflows/release.yml"
grep -q 'aggregate-boundary' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q -- '-f source_run_id="$GITHUB_RUN_ID"' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
if grep -q 'run: ./scripts/verify$' \
  "$fixture_root/default-project/.github/workflows/release.yml"; then
  echo "Release artifacts must reuse promotion CI instead of rerunning it."
  exit 1
fi
if grep -q './scripts/verify-template.sh' .github/workflows/release-template.yml; then
  echo "Template releases must reuse promotion CI instead of rerunning it."
  exit 1
fi
test -f "$fixture_root/default-project/scripts/release_policy.py"
if grep -Eq 'CSARC_VERSION_BOT|create-github-app-token' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"; then
  echo "release-please must not depend on the GitHub App bot."
  exit 1
fi
uv run --no-project python - \
  "$fixture_root/default-project/policies/actions.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    policy = json.load(source)
assert policy["default_workflow_permissions"] == "read"
assert policy["can_approve_pull_request_reviews"] is True
PY
# Write permissions must be scoped to the release job, not the whole workflow.
grep -q '^  contents: read$' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"

# Release Please must update the project version and uv lock entry together.
uv run python - \
  "$fixture_root/default-project/pyproject.toml" \
  "$fixture_root/default-project/uv.lock" \
  "$fixture_root/default-project/release-please-config.json" \
  "$fixture_root/default-project/.release-please-manifest.json" \
  "$fixture_root/default-project/src/template_smoke_test/__init__.py" <<'PY'
import json
import re
import sys
import tomllib


with open(sys.argv[1], "rb") as pyproject_file:
    project = tomllib.load(pyproject_file)["project"]
with open(sys.argv[2], "rb") as lock_file:
    packages = tomllib.load(lock_file)["package"]
with open(sys.argv[3], encoding="utf-8") as config_file:
    config = json.load(config_file)
with open(sys.argv[4], encoding="utf-8") as manifest_file:
    manifest = json.load(manifest_file)
with open(sys.argv[5], encoding="utf-8") as package_file:
    package_source = package_file.read()

project_version = project["version"]
locked_version = next(
    package["version"]
    for package in packages
    if package["name"] == project["name"]
)
version_match = re.search(r'^__version__ = "([^"]+)"', package_source, re.MULTILINE)
if version_match is None:
    raise SystemExit("Generated package does not expose __version__.")
package_version = version_match.group(1)
extra_files = config["packages"]["."]["extra-files"]
lock_extra_file = extra_files[0]
package_extra_file = extra_files[1]
expected_path = f'$.package[?(@.name.value=="{project["name"]}")].version'
if config["release-type"] != "python":
    raise SystemExit("Release Please must use the Python release type.")
if lock_extra_file != {
    "type": "toml",
    "path": "uv.lock",
    "jsonpath": expected_path,
}:
    raise SystemExit("Release Please does not target this project's uv.lock entry.")
if package_extra_file != {
    "type": "generic",
    "path": "src/template_smoke_test/__init__.py",
}:
    raise SystemExit("Release Please does not target the import package version.")
if not project_version == locked_version == package_version == manifest["."]:
    raise SystemExit(
        "pyproject.toml, uv.lock, package, and release manifest versions differ."
    )
PY

# Shared dev dependency ranges must match in root and generated projects.
uv run python - \
  "$repo_root/pyproject.toml" \
  "$fixture_root/default-project/pyproject.toml" <<'PY'
import re
import sys
import tomllib


def dev_dependencies(path):
    with open(path, "rb") as pyproject:
        dependencies = tomllib.load(pyproject)["dependency-groups"]["dev"]
    return {
        re.split(r"[\[<>=!~]", dependency, maxsplit=1)[0]: dependency
        for dependency in dependencies
    }


root = dev_dependencies(sys.argv[1])
generated = dev_dependencies(sys.argv[2])
for package in root.keys() & generated.keys():
    if root[package] != generated[package]:
        raise SystemExit(
            f"Dev dependency range drift for {package}: "
            f"{root[package]} != {generated[package]}"
        )
PY

(
  cd "$fixture_root/default-project"
  printf '%s\n' 'window.STALE_BUNDLE_PROBE = true;' >> docs/site-content.js
  if uv run --no-project python scripts/render_site.py --check >/dev/null 2>&1; then
    echo "Site bundle check accepted stale project content."
    exit 1
  fi
  uv run --no-project python scripts/render_site.py
  grep -q 'window.STALE_BUNDLE_PROBE = true;' docs/index.html
  ./scripts/verify
  "$repo_root/.venv/bin/zizmor" . --format plain
)

# A broken Python change must be rejected by the generated CI command.
printf 'import os\n' > \
  "$fixture_root/default-project/src/template_smoke_test/invalid_policy_probe.py"
if (
  cd "$fixture_root/default-project"
  uv run ruff check src/template_smoke_test/invalid_policy_probe.py >/dev/null 2>&1
); then
  echo "Ruff accepted an intentionally invalid Python change."
  exit 1
fi
rm "$fixture_root/default-project/src/template_smoke_test/invalid_policy_probe.py"

# CI/CD-only project: shared governance and release versioning without a
# language package or language-specific toolchain.
uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_name="CI Only Test" \
  --data project_slug="ci-only-test" \
  --data language=ci \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  "$repo_root" "$fixture_root/ci-only-project"
prime_gitleaks_cache "$fixture_root/ci-only-project"
assert_agent_guidance "$fixture_root/ci-only-project"

git -C "$fixture_root/ci-only-project" init -q -b main
git -C "$fixture_root/ci-only-project" add .
git -C "$fixture_root/ci-only-project" diff --cached --check
grep -q 'language: ci' "$fixture_root/ci-only-project/.copier-answers.yml"
grep -q '"language_profile": "ci"' \
  "$fixture_root/ci-only-project/.csarc/profile.json"
grep -q 'stage: "beta"' \
  "$fixture_root/ci-only-project/docs/site-content.js"
test "$("$fixture_root/ci-only-project/scripts/detect-language-profile" --suggest)" = \
  "ci"
test "$(cat "$fixture_root/ci-only-project/version.txt")" = "0.1.0"
grep -q '"release-type": "simple"' \
  "$fixture_root/ci-only-project/release-please-config.json"
test ! -f "$fixture_root/ci-only-project/pyproject.toml"
test ! -f "$fixture_root/ci-only-project/package.json"
test ! -d "$fixture_root/ci-only-project/src"
test ! -d "$fixture_root/ci-only-project/tests"
test ! -d "$fixture_root/ci-only-project/typescript"
grep -q 'no language toolchain install is required' \
  "$fixture_root/ci-only-project/AGENTS.md"
if grep -Eq 'Python setup:|TypeScript setup:' \
  "$fixture_root/ci-only-project/AGENTS.md"; then
  echo "CI-only AGENTS.md must not include language setup commands."
  exit 1
fi
if grep -q 'publish-evidence\|release-evidence' \
  "$fixture_root/ci-only-project/.github/workflows/release.yml"; then
  echo "CI/CD-only releases must not require package evidence."
  exit 1
fi
if grep -q '^  publish-python:\|^  publish-npm:' \
  "$fixture_root/ci-only-project/.github/workflows/release.yml"; then
  echo "CI/CD-only releases must not publish packages."
  exit 1
fi
if grep -q 'gh attestation verify' \
  "$fixture_root/ci-only-project/.github/workflows/release.yml"; then
  echo "CI-only release workflow must not contain artifact verification."
  exit 1
fi
if grep -q '^\.venv\*/\|^node_modules/$' \
  "$fixture_root/ci-only-project/.gitignore"; then
  echo "CI/CD-only .gitignore must not contain language artifacts."
  exit 1
fi
(
  cd "$fixture_root/ci-only-project"
  ./scripts/verify
  "$repo_root/.venv/bin/zizmor" . --format plain
)

# Main-only projects keep the same guidance contract without delivery wording.
uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_name="Main Branch Test" \
  --data project_slug="main-branch-test" \
  --data language=ci \
  --data branch_strategy=main \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  "$repo_root" "$fixture_root/main-branch-project"
assert_agent_guidance "$fixture_root/main-branch-project"
grep -q 'pull request chain ends at `main`' \
  "$fixture_root/main-branch-project/AGENTS.md"
grep -q 'against `main` or its immediate parent in the stack' \
  "$fixture_root/main-branch-project/AGENTS.md"

# A release version bump must not make the generated smoke test stale.
release_bump_project="$fixture_root/release-bump-project"
rsync -a --exclude=.git --exclude=.venv --exclude=.cache --exclude=.ruff_cache \
  "$fixture_root/default-project/" "$release_bump_project/"
uv run python - "$release_bump_project" <<'PY'
import json
import pathlib
import sys


root = pathlib.Path(sys.argv[1])
pyproject = root / "pyproject.toml"
package = root / "src/template_smoke_test/__init__.py"
manifest = root / ".release-please-manifest.json"
pyproject.write_text(
    pyproject.read_text().replace('version = "0.1.0"', 'version = "0.2.0"'),
    encoding="utf-8",
)
package.write_text(
    package.read_text().replace(
        '__version__ = "0.1.0"', '__version__ = "0.2.0"'
    ),
    encoding="utf-8",
)
manifest.write_text(json.dumps({".": "0.2.0"}) + "\n", encoding="utf-8")
PY
(
  cd "$release_bump_project"
  uv lock
  uv run pytest tests/test_smoke.py
)

# TypeScript-only project: the same quality, packaging, and release gates apply.
uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_name="TypeScript Test" \
  --data project_slug="typescript-test" \
  --data $'project_description=A "quoted" project\n第二行' \
  --data language=typescript \
  --data branch_strategy=dev \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  "$repo_root" "$fixture_root/typescript-project"
prime_gitleaks_cache "$fixture_root/typescript-project"
assert_agent_guidance "$fixture_root/typescript-project"

git -C "$fixture_root/typescript-project" init -q -b main
git -C "$fixture_root/typescript-project" add .
git -C "$fixture_root/typescript-project" diff --cached --check

grep -q 'language: typescript' \
  "$fixture_root/typescript-project/.copier-answers.yml"
uv run python - "$fixture_root/typescript-project/package.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as package_json:
    package = json.load(package_json)
assert package["description"] == 'A "quoted" project\n第二行'
assert package["repository"]["url"] == (
    "https://github.com/Innoguard-Cyber-Arch/typescript-test.git"
)
PY
grep -q '"language_profile": "typescript"' \
  "$fixture_root/typescript-project/.csarc/profile.json"
grep -q '"branch_strategy": "dev"' \
  "$fixture_root/typescript-project/.csarc/profile.json"
grep -q 'pull request chain ends at `dev`' \
  "$fixture_root/typescript-project/AGENTS.md"
grep -q 'against `dev` or its immediate parent in the stack' \
  "$fixture_root/typescript-project/AGENTS.md"
grep -q '^  merge_group:$' \
  "$fixture_root/typescript-project/.github/workflows/ci.yml"
if grep -q '^  push:$' \
  "$fixture_root/typescript-project/.github/workflows/ci.yml"; then
  echo "Generated CI must not repeat a verified tree after merge."
  exit 1
fi
grep -q 'target-branch: dev' \
  "$fixture_root/typescript-project/.github/dependabot.yml"
grep -q '"refs/heads/dev"' \
  "$fixture_root/typescript-project/policies/rulesets.json"
test "$("$fixture_root/typescript-project/scripts/detect-language-profile" --suggest)" = \
  "typescript"
test -f "$fixture_root/typescript-project/package.json"
test -f "$fixture_root/typescript-project/pnpm-lock.yaml"
test -f "$fixture_root/typescript-project/pnpm-workspace.yaml"
test -f "$fixture_root/typescript-project/typescript/src/index.ts"
test -f "$fixture_root/typescript-project/typescript/tests/index.test.ts"
test ! -f "$fixture_root/typescript-project/pyproject.toml"
test ! -f "$fixture_root/typescript-project/.python-version"
grep -q 'pnpm exec vitest run <test-path>' \
  "$fixture_root/typescript-project/AGENTS.md"
grep -q 'TypeScript setup: `corepack enable && pnpm install --frozen-lockfile`' \
  "$fixture_root/typescript-project/AGENTS.md"
if grep -q 'uv run pytest' "$fixture_root/typescript-project/AGENTS.md"; then
  echo "TypeScript-only AGENTS.md must not include Python commands."
  exit 1
fi
grep -q '^node_modules/$' "$fixture_root/typescript-project/.gitignore"
grep -q '^\*\.tsbuildinfo$' "$fixture_root/typescript-project/.gitignore"
if grep -q '^\.venv\*/$' "$fixture_root/typescript-project/.gitignore"; then
  echo "TypeScript-only .gitignore must not contain Python artifacts."
  exit 1
fi
grep -q '"node": ">=24"' "$fixture_root/typescript-project/package.json"
grep -q '"@biomejs/biome": "2.5.8"' \
  "$fixture_root/typescript-project/package.json"
grep -q '"vitest": "4.1.10"' "$fixture_root/typescript-project/package.json"
grep -q '^minimumReleaseAge: 4320$' \
  "$fixture_root/typescript-project/pnpm-workspace.yaml"
grep -q '^minimumReleaseAgeStrict: true$' \
  "$fixture_root/typescript-project/pnpm-workspace.yaml"
grep -q '^trustPolicy: no-downgrade$' \
  "$fixture_root/typescript-project/pnpm-workspace.yaml"
grep -q 'integrity:' "$fixture_root/typescript-project/pnpm-lock.yaml"
grep -q 'node-version: "24"' \
  "$fixture_root/typescript-project/.github/workflows/ci.yml"
grep -q 'package-ecosystem: npm' \
  "$fixture_root/typescript-project/.github/dependabot.yml"
grep -q '"release-type": "node"' \
  "$fixture_root/typescript-project/release-please-config.json"
grep -q 'Build TypeScript package' \
  "$fixture_root/typescript-project/.github/workflows/release.yml"

(
  cd "$fixture_root/typescript-project"
  ./scripts/verify
  "$repo_root/.venv/bin/zizmor" . --format plain
)

# A badly formatted TypeScript change must be rejected by the generated CI command.
printf 'export const invalid={value:1}\n' > \
  "$fixture_root/typescript-project/typescript/src/invalid-policy-probe.ts"
if (
  cd "$fixture_root/typescript-project"
  pnpm exec biome ci typescript/src/invalid-policy-probe.ts >/dev/null 2>&1
); then
  echo "Biome accepted an intentionally invalid TypeScript change."
  exit 1
fi
rm "$fixture_root/typescript-project/typescript/src/invalid-policy-probe.ts"

# Combined project: reusable CI and local pre-commit support.
uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_name="All Features Test" \
  --data project_slug="all-features-test" \
  --data package_name="all_features_test" \
  --data language=python-typescript \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  --data use_reusable_workflow=true \
  --data workflow_ref=1111111111111111111111111111111111111111 \
  --data enable_precommit=true \
  --data enable_template_update_notifications=true \
  --data enable_governance_drift_check=true \
  --data enable_codeql=true \
  --data enable_release_attestations=true \
  --data enable_pypi_publishing=true \
  --data pypi_environment=pypi-release \
  --data enable_npm_publishing=true \
  --data npm_environment=npm-release \
  "$repo_root" "$fixture_root/all-features-project"
prime_gitleaks_cache "$fixture_root/all-features-project"
assert_agent_guidance "$fixture_root/all-features-project"

test -f "$fixture_root/all-features-project/.pre-commit-config.yaml"
test -f "$fixture_root/all-features-project/.github/workflows/template-update.yml"
test -x "$fixture_root/all-features-project/scripts/check-template-update"
grep -q 'copier check-update --quiet' \
  "$fixture_root/all-features-project/scripts/check-template-update"
grep -q 'CSARC_TEMPLATE_READ_TOKEN' \
  "$fixture_root/all-features-project/.github/workflows/template-update.yml"
test -f "$fixture_root/all-features-project/.github/workflows/governance-drift.yml"
test -f "$fixture_root/all-features-project/.github/workflows/codeql.yml"
grep -q 'language: \["python", "javascript-typescript"\]' \
  "$fixture_root/all-features-project/.github/workflows/codeql.yml"
test -x "$fixture_root/all-features-project/scripts/check-governance-drift"
grep -q 'schedule:' \
  "$fixture_root/all-features-project/.github/workflows/governance-drift.yml"
grep -q 'issues: write' \
  "$fixture_root/all-features-project/.github/workflows/governance-drift.yml"
grep -q './scripts/check-governance-drift' \
  "$fixture_root/all-features-project/.github/workflows/governance-drift.yml"
grep -q 'apply-repository-settings.sh check' \
  "$fixture_root/all-features-project/scripts/check-governance-drift"
for issue_creator in check-template-update check-governance-drift; do
  issue_creator_path="$fixture_root/all-features-project/scripts/$issue_creator"
  test "$(grep -c '^### ' "$issue_creator_path")" -eq 4
  for heading in 類型 問題 完成條件 補充; do
    grep -qFx "### $heading" "$issue_creator_path"
  done
done
template_update_fixture="$fixture_root/template-update-check"
mkdir -p "$template_update_fixture/bin"
cat > "$template_update_fixture/bin/copier" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

if [[ " $* " == *" --quiet "* ]]; then
  exit "${MOCK_COPIER_EXIT:-0}"
fi
printf '{"update_available":true,"current_version":"v0.1.0","latest_version":"v0.2.0"}\n'
SH
cat > "$template_update_fixture/bin/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

if [[ "$1 $2" == "issue list" ]]; then
  printf '%s\n' "${MOCK_EXISTING_ISSUE:-}"
  exit 0
fi
printf '%s\n' "$*" >> "$MOCK_GH_LOG"
SH
chmod +x "$template_update_fixture/bin/copier" "$template_update_fixture/bin/gh"
: > "$template_update_fixture/create.log"
PATH="$template_update_fixture/bin:$PATH" \
  MOCK_COPIER_EXIT=2 \
  MOCK_GH_LOG="$template_update_fixture/create.log" \
  "$fixture_root/all-features-project/scripts/check-template-update" >/dev/null
grep -q '^issue create .*--label enhancement' \
  "$template_update_fixture/create.log"
: > "$template_update_fixture/update.log"
PATH="$template_update_fixture/bin:$PATH" \
  MOCK_COPIER_EXIT=2 \
  MOCK_EXISTING_ISSUE=42 \
  MOCK_GH_LOG="$template_update_fixture/update.log" \
  "$fixture_root/all-features-project/scripts/check-template-update" >/dev/null
grep -q '^issue edit 42 ' "$template_update_fixture/update.log"
: > "$template_update_fixture/current.log"
PATH="$template_update_fixture/bin:$PATH" \
  MOCK_COPIER_EXIT=0 \
  MOCK_GH_LOG="$template_update_fixture/current.log" \
  "$fixture_root/all-features-project/scripts/check-template-update" >/dev/null
test ! -s "$template_update_fixture/current.log"
grep -q 'reusable-ci.yml@1111111111111111111111111111111111111111' \
  "$fixture_root/all-features-project/.github/workflows/ci.yml"
grep -q 'language-profile: "python-typescript"' \
  "$fixture_root/all-features-project/.github/workflows/ci.yml"
grep -q '\["3.14.0", "3.14"\]' \
  "$fixture_root/all-features-project/.github/workflows/ci.yml"
grep -q 'actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
test "$(grep -c \
  'actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6' \
  "$fixture_root/all-features-project/.github/workflows/release.yml")" -eq 2
grep -q 'attestations: write' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
grep -q 'id-token: write' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
grep -q 'subject-checksums: release-evidence/SHA256SUMS' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
grep -q 'sbom-path: release-evidence/sbom.cdx.json' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
grep -q '外部 registry 發布會先以 `gh attestation verify` 強制比對' \
  "$fixture_root/all-features-project/README.md"
grep -q '^  publish-python:$' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
test "$(grep -c '^      attestations: read$' \
  "$fixture_root/all-features-project/.github/workflows/release.yml")" -eq 2
test "$(grep -c 'gh attestation verify' \
  "$fixture_root/all-features-project/.github/workflows/release.yml")" -eq 2
test "$(grep -c -- '--signer-workflow' \
  "$fixture_root/all-features-project/.github/workflows/release.yml")" -eq 2
test "$(grep -c -- '--source-ref \"\$GITHUB_REF\"' \
  "$fixture_root/all-features-project/.github/workflows/release.yml")" -eq 2
test "$(grep -c -- '--source-digest \"\$GITHUB_SHA\"' \
  "$fixture_root/all-features-project/.github/workflows/release.yml")" -eq 2
grep -q '^      name: "pypi-release"$' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
grep -q 'pypa/gh-action-pypi-publish@a892a5a61159132606e93a2fa6f4358831b04d26' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
grep -q '^  publish-npm:$' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
grep -q '^      name: "npm-release"$' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
grep -q 'npm publish "${packages\[0\]}" --provenance --access public' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
if grep -Eq 'PYPI_API_TOKEN|NPM_TOKEN|NODE_AUTH_TOKEN' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"; then
  echo "Trusted publishing must not require a long-lived registry token."
  exit 1
fi
grep -q '"context": "verify"' \
  "$fixture_root/all-features-project/policies/rulesets.json"
test -f "$fixture_root/all-features-project/pyproject.toml"
test -f "$fixture_root/all-features-project/package.json"
test -f "$fixture_root/all-features-project/uv.lock"
test -f "$fixture_root/all-features-project/pnpm-lock.yaml"
test -f "$fixture_root/all-features-project/pnpm-workspace.yaml"
grep -q '^trustPolicy: no-downgrade$' \
  "$fixture_root/all-features-project/pnpm-workspace.yaml"
grep -q 'uv run pytest <test-path>' \
  "$fixture_root/all-features-project/AGENTS.md"
grep -q 'pnpm exec vitest run <test-path>' \
  "$fixture_root/all-features-project/AGENTS.md"
grep -q 'Python setup: `uv sync --locked`' \
  "$fixture_root/all-features-project/AGENTS.md"
grep -q 'TypeScript setup: `corepack enable && pnpm install --frozen-lockfile`' \
  "$fixture_root/all-features-project/AGENTS.md"
diff -B -w "$repo_root/.gitignore" \
  "$fixture_root/all-features-project/.gitignore"
test "$("$fixture_root/all-features-project/scripts/detect-language-profile" --suggest)" = \
  "python-typescript"
git -C "$fixture_root/all-features-project" init -q -b main
git -C "$fixture_root/all-features-project" add .
git -C "$fixture_root/all-features-project" diff --cached --check

(
  cd "$fixture_root/all-features-project"
  ./scripts/verify
  uv run pre-commit run --all-files
  "$repo_root/.venv/bin/zizmor" . --format plain
)

# Changed-line coverage keeps the same 80% threshold across the runtime matrix.
uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_name="Existing Project Test" \
  --data project_slug="existing-project-test" \
  --data package_name="existing_project_test" \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  --data python_support_mode=minimum \
  --data python_min_version=3.12 \
  --data coverage_mode=diff \
  "$repo_root" "$fixture_root/existing-project"
prime_gitleaks_cache "$fixture_root/existing-project"

grep -q '^requires-python = ">=3.12"$' \
  "$fixture_root/existing-project/pyproject.toml"
grep -q '^target-version = "py312"$' \
  "$fixture_root/existing-project/pyproject.toml"
for expected_python in 3.12.0 3.12 3.13 3.14; do
  grep -q -- "- \"$expected_python\"" \
    "$fixture_root/existing-project/.github/workflows/ci.yml"
done

git -C "$fixture_root/existing-project" init -b main
git -C "$fixture_root/existing-project" config user.name "Template Test"
git -C "$fixture_root/existing-project" config user.email "template-test@example.invalid"
git -C "$fixture_root/existing-project" add .
git -C "$fixture_root/existing-project" commit -m "test: generated baseline"
if diff_error="$(
  cd "$fixture_root/existing-project"
  CSARC_PYTHON_VERSION=3.12 \
    UV_PROJECT_ENVIRONMENT=.venv-minimum \
    ./scripts/verify 2>&1
)"; then
  echo "Diff coverage without origin/main must fail with setup guidance."
  exit 1
fi
if ! grep -qF \
  'Set DIFF_COVER_COMPARE_BRANCH to an existing ref (current: origin/main).' \
  <<<"$diff_error"; then
  echo "$diff_error"
  exit 1
fi
(
  cd "$fixture_root/existing-project"
  for python_runtime in 3.12.0 3.12 3.13 3.14; do
    CSARC_PYTHON_VERSION="$python_runtime" \
      UV_PROJECT_ENVIRONMENT=".venv-$python_runtime" \
      DIFF_COVER_COMPARE_BRANCH=HEAD \
      ./scripts/verify
  done
)

# Adoption must never replace existing product manifests.
adoption_project="$fixture_root/adoption-project"
mkdir -p "$adoption_project"
cat > "$adoption_project/pyproject.toml" <<'TOML'
[project]
name = "legacy-product"
version = "0.4.2"
dependencies = ["httpx>=0.28"]

[build-system]
requires = ["setuptools>=80"]
build-backend = "setuptools.build_meta"
TOML
cat > "$adoption_project/package.json" <<'JSON'
{
  "name": "legacy-product-ui",
  "version": "0.4.2",
  "dependencies": {"typescript": "5.9.3"}
}
JSON
uv run copier copy --trust --defaults --overwrite --vcs-ref HEAD \
  --data project_mode=existing \
  --data project_name="Legacy Product" \
  --data project_slug="legacy-product" \
  --data package_name="legacy_product" \
  --data language=python-typescript \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  --data coverage_mode=diff \
  "$repo_root" "$adoption_project"
grep -q '^version = "0.4.2"$' "$adoption_project/pyproject.toml"
grep -q 'httpx>=0.28' "$adoption_project/pyproject.toml"
grep -q 'setuptools.build_meta' "$adoption_project/pyproject.toml"
grep -q '"version": "0.4.2"' "$adoption_project/package.json"
grep -q '"typescript": "5.9.3"' "$adoption_project/package.json"
grep -q 'project_mode: existing' "$adoption_project/.copier-answers.yml"
grep -q '"template_mode": "existing"' \
  "$adoption_project/.csarc/profile.json"

# Verify that an adopted repository can receive a later template version.
update_source="$fixture_root/update-source"
update_project="$fixture_root/update-project"
mkdir -p "$update_source"
legacy_memory_base=f1ecc6e4fa2bb03e7c322e5d8dd69265a7c34513
git cat-file -e "$legacy_memory_base^{commit}"
git archive "$legacy_memory_base" | tar -x -C "$update_source"

git -C "$update_source" init -b main
git -C "$update_source" config user.name "Template Test"
git -C "$update_source" config user.email "template-test@example.invalid"
git -C "$update_source" add .
git -C "$update_source" commit -m "test: template v0.1.0"
git -C "$update_source" tag v0.1.0

uv run copier copy --trust --defaults --vcs-ref v0.1.0 \
  --data language=python-typescript \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  "$update_source" "$update_project"

# Reuse a valid generated project as a compatible legacy fixture without
# template history, so the lifecycle test does not duplicate full manifests.
rm "$update_project/.copier-answers.yml"
printf '%s\n' '' '[tool.product]' 'owner = "legacy"' \
  >> "$update_project/pyproject.toml"
printf '%s\n' 'PROJECT_OWNED = True' \
  >> "$update_project/src/csarc_project/__init__.py"
printf '%s\n' 'export const projectOwned = true;' \
  >> "$update_project/typescript/src/index.ts"
printf '%s\n' 'window.PROJECT_OWNED_SITE = true;' \
  >> "$update_project/docs/site-content.js"
printf '%s\n' '/* PROJECT_OWNED_THEME */' \
  >> "$update_project/docs/site-theme.css"
cp "$repo_root/docs/adr/agent-collaboration.md" \
  "$update_project/docs/decisions/project-owned.md"
printf '%s\n' '' 'PROJECT_OWNED_MEMORY' \
  >> "$update_project/docs/decisions/project-owned.md"
printf '%s\n' '' 'PROJECT_OWNED_SPEC' \
  >> "$update_project/docs/specs/SPEC-001-example.md"
uv run copier copy --trust --defaults --overwrite --vcs-ref v0.1.0 \
  --data project_mode=existing \
  --data language=python-typescript \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  "$update_source" "$update_project"
grep -q 'project_mode: existing' "$update_project/.copier-answers.yml"
grep -q '"template_mode": "existing"' \
  "$update_project/.csarc/profile.json"
grep -q '^owner = "legacy"$' "$update_project/pyproject.toml"

git -C "$update_project" init -b main
git -C "$update_project" config user.name "Template Test"
git -C "$update_project" config user.email "template-test@example.invalid"
git -C "$update_project" add .
git -C "$update_project" commit -m "test: adopted project"

rsync -a --delete --exclude=.git --exclude=.venv --exclude=.cache \
  --exclude=.ruff_cache "$repo_root/" "$update_source/"
cp "$update_source/template/.gitignore.jinja" \
  "$update_source/template/update-marker"
printf '%s\n' 'window.TEMPLATE_SITE_V2 = true;' \
  >> "$update_source/template/site/app.js"
git -C "$update_source" add -A
git -C "$update_source" commit -m "test: template v0.1.1"
git -C "$update_source" tag v0.1.1

(
  cd "$update_project"
  "$repo_root/.venv/bin/copier" update --trust --defaults --vcs-ref v0.1.1
)

test -f "$update_project/update-marker"
grep -q '^owner = "legacy"$' "$update_project/pyproject.toml"
grep -q '^PROJECT_OWNED = True$' \
  "$update_project/src/csarc_project/__init__.py"
grep -q '^export const projectOwned = true;$' \
  "$update_project/typescript/src/index.ts"
grep -q '^window.PROJECT_OWNED_SITE = true;$' \
  "$update_project/docs/site-content.js"
grep -q '^/\* PROJECT_OWNED_THEME \*/$' \
  "$update_project/docs/site-theme.css"
grep -q 'window.PROJECT_OWNED_SITE = true;' \
  "$update_project/docs/index.html"
grep -q 'PROJECT_OWNED_THEME' \
  "$update_project/docs/index.html"
grep -q '^PROJECT_OWNED_MEMORY$' \
  "$update_project/docs/decisions/project-owned.md"
grep -q '^PROJECT_OWNED_SPEC$' \
  "$update_project/docs/specs/SPEC-001-example.md"
grep -q 'window.TEMPLATE_SITE_V2 = true;' \
  "$update_project/site/app.js"
grep -q 'window.TEMPLATE_SITE_V2 = true;' \
  "$update_project/docs/index.html"
test -f "$update_project/docs/adr/README.md"
grep -q 'docs/decisions/' "$update_project/AGENTS.md"
grep -q 'docs/decisions/' "$update_project/docs/README.md"
grep -q 'Never store a raw conversation transcript' \
  "$update_project/AGENTS.md"
grep -q '_commit: v0.1.1' "$update_project/.copier-answers.yml"
prime_gitleaks_cache "$update_project"
(
  cd "$update_project"
  ./scripts/verify
)
