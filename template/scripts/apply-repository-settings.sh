#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:-plan}"
prune_labels=false
allow_unprotected=false

if [[ "$mode" != "plan" && "$mode" != "apply" && "$mode" != "check" ]]; then
  echo "Usage: $0 [plan|apply|check] [--prune-labels] [--allow-unprotected]"
  exit 2
fi
shift $(( $# > 0 ? 1 : 0 ))
for option in "$@"; do
  case "$option" in
    --prune-labels) prune_labels=true ;;
    --allow-unprotected) allow_unprotected=true ;;
    *)
      echo "Usage: $0 [plan|apply|check] [--prune-labels] [--allow-unprotected]"
      exit 2
      ;;
  esac
done

command -v gh >/dev/null || { echo "Install and authenticate GitHub CLI first."; exit 1; }
repo="${GH_REPO:-}"
if [[ -z "$repo" ]]; then
  if ! repo="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>&1)"; then
    echo "Cannot identify the GitHub repository."
    echo "Run inside a Git repository with a GitHub remote, or set GH_REPO=owner/repo."
    echo "GitHub CLI: $repo"
    exit 1
  fi
fi
ruleset_payload="$repo_root/policies/rulesets.json"
ruleset_name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["name"])' "$ruleset_payload")"
code_owner="$(awk '!/^#/ && NF {print $NF; exit}' "$repo_root/.github/CODEOWNERS")"

if ! repo_context="$({
  gh api "repos/$repo" \
    --jq '[.owner.login, .owner.type, (.visibility // (if .private then "private" else "public" end)), .permissions.admin, .default_branch] | @tsv'
} 2>&1)"; then
  echo "Cannot read repository metadata for $repo."
  echo "$repo_context"
  exit 1
fi
IFS=$'\t' read -r owner owner_type repo_visibility repo_admin default_branch <<<"$repo_context"
if [[ "$mode" != "check" && "$repo_admin" != "true" ]]; then
  echo "Repository administrator permission is required before any settings can be applied."
  exit 1
fi

account_endpoint="users/$owner"
private_ruleset_plan="GitHub Pro"
billing_url="https://github.com/settings/billing"
if [[ "$owner_type" == "Organization" ]]; then
  account_endpoint="orgs/$owner"
  private_ruleset_plan="GitHub Team or above"
  billing_url="https://github.com/organizations/$owner/settings/billing"
fi
account_plan="$(gh api "$account_endpoint" --jq '.plan.name // "unknown"' 2>/dev/null || echo unknown)"
case "$account_plan" in
  free) plan_label="GitHub Free" ;;
  team) plan_label="GitHub Team" ;;
  business|business_plus|enterprise) plan_label="GitHub Enterprise" ;;
  pro) plan_label="GitHub Pro" ;;
  *) plan_label="Unknown ($account_plan)" ;;
esac

print_ruleset_guidance() {
  echo "- DEGRADED required governance: $default_branch is not protected on this private repository."
  echo "- PRESERVED desired Ruleset: policies/rulesets.json remains ready for a supported plan or public repository."
  echo "- API LIMIT: GitHub REST and GraphQL reject Ruleset creation and updates on this plan, even with enforcement disabled."
  echo "- OPTIONAL: an administrator may preconfigure a disabled Ruleset in the GitHub web UI; this script can detect but cannot create it."
  echo "  https://github.com/$repo/settings/rules"
  echo "- NEXT STEP keep it private: ask the owner to upgrade to $private_ruleset_plan."
  echo "  $billing_url"
  echo "- ALTERNATIVE only when public access is approved: change repository visibility."
  echo "  https://github.com/$repo/settings"
  echo "- THEN create or confirm the CODEOWNERS team $code_owner and rerun:"
  echo "  GH_REPO=$repo ./scripts/apply-repository-settings.sh plan"
  echo "  GH_REPO=$repo ./scripts/apply-repository-settings.sh apply"
}

load_graphql_ruleset() {
  local graphql_result graphql_state
  if ! graphql_result="$(
    gh api graphql \
      -f query='query($owner: String!, $name: String!) {
        repository(owner: $owner, name: $name) {
          rulesets(first: 100) {
            nodes { id name enforcement target }
          }
        }
      }' \
      -f owner="$owner" \
      -f name="${repo#*/}" 2>&1
  )"; then
    graphql_ruleset_error="$graphql_result"
    return 1
  fi
  if ! graphql_state="$(python3 - "$ruleset_name" "$graphql_result" <<'PY'
import json
import sys

ruleset_name = sys.argv[1]
repository = json.loads(sys.argv[2])["data"]["repository"]
if repository is None:
    raise SystemExit("Repository is unavailable through the GraphQL API.")
ruleset = next(
    (item for item in repository["rulesets"]["nodes"] if item["name"] == ruleset_name),
    None,
)
print(
    ruleset["id"] if ruleset else "-",
    ruleset["enforcement"] if ruleset else "-",
    ruleset["target"] if ruleset else "-",
    sep="|",
)
PY
  )"; then
    graphql_ruleset_error="$graphql_state"
    return 1
  fi
  IFS='|' read -r ruleset_node_id ruleset_enforcement ruleset_target \
    <<<"$graphql_state"
}

ruleset_enforcement_available=true
ruleset_inventory_available=true
ruleset_skip_reason=""
graphql_ruleset_error=""
ruleset_node_id="-"
ruleset_enforcement="-"
ruleset_target="-"
if ! ruleset_access="$(gh api "repos/$repo/rulesets" 2>&1)"; then
  ruleset_enforcement_available=false
  if [[ "$ruleset_access" == *"Upgrade to GitHub Pro or make this repository public"* ]]; then
    ruleset_skip_reason="Private repositories on GitHub Free do not enforce Rulesets; use Team or above."
    if ! load_graphql_ruleset; then
      ruleset_inventory_available=false
    fi
  else
    echo "Cannot determine Ruleset capability for $repo."
    echo "$ruleset_access"
    exit 1
  fi
fi

if [[ "$mode" == "check" ]]; then
  check_errors=0
  check_degraded=0

  if ! repository_state="$(gh api "repos/$repo" 2>&1)"; then
    echo "Cannot inspect repository settings for $repo." >&2
    echo "$repository_state" >&2
    check_errors=$((check_errors + 1))
  elif ! repository_drift="$(python3 - "$repo_root/policies/repository.json" "$repository_state" 2>&1 <<'PY'
import json
import sys

desired = json.load(open(sys.argv[1], encoding="utf-8"))
actual = json.loads(sys.argv[2])
drift = [
    f"{key}: desired {value!r}, live {actual.get(key)!r}"
    for key, value in desired.items()
    if actual.get(key) != value
]
if drift:
    raise SystemExit("; ".join(drift))
PY
  )"; then
    echo "Repository settings drift: $repository_drift" >&2
    check_errors=$((check_errors + 1))
  else
    echo "Repository settings match policies/repository.json."
  fi

  if ! actions_state="$(gh api "repos/$repo/actions/permissions/workflow" 2>&1)"; then
    echo "Cannot inspect Actions workflow permissions for $repo." >&2
    echo "$actions_state" >&2
    check_errors=$((check_errors + 1))
  elif ! actions_comparison="$(python3 - "$repo_root/policies/actions.json" "$actions_state" 2>&1 <<'PY'
import json
import sys

desired = json.load(open(sys.argv[1], encoding="utf-8"))
actual = json.loads(sys.argv[2])
default_drift = desired["default_workflow_permissions"] != actual.get("default_workflow_permissions")
desired_pr = desired["can_approve_pull_request_reviews"]
actual_pr = actual.get("can_approve_pull_request_reviews")
print(
    str(default_drift).lower(),
    str(desired_pr is True and actual_pr is False).lower(),
    str(desired_pr != actual_pr and not (desired_pr is True and actual_pr is False)).lower(),
    sep="|",
)
PY
  )"; then
    echo "Cannot compare Actions workflow permissions for $repo." >&2
    echo "$actions_comparison" >&2
    check_errors=$((check_errors + 1))
  else
    IFS='|' read -r actions_default_drift actions_pr_degraded actions_pr_drift \
      <<<"$actions_comparison"
    if [[ "$actions_default_drift" == "true" ]]; then
      echo "Actions settings drift: default_workflow_permissions differs from policies/actions.json." >&2
      check_errors=$((check_errors + 1))
    fi
    if [[ "$actions_pr_drift" == "true" ]]; then
      echo "Actions settings drift: can_approve_pull_request_reviews differs from policies/actions.json." >&2
      check_errors=$((check_errors + 1))
    elif [[ "$actions_pr_degraded" == "true" ]]; then
      [[ "${GITHUB_ACTIONS:-}" == "true" ]] &&
        echo "::warning title=Actions policy degraded::Actions cannot approve pull requests although policies/actions.json requests it."
      echo "DEGRADED Actions PR policy: desired true, live false; an organization policy may block this capability. Runtime release workflows adapt."
      check_degraded=$((check_degraded + 1))
    fi
    if [[ "$actions_default_drift" != "true" && "$actions_pr_degraded" != "true" && "$actions_pr_drift" != "true" ]]; then
      echo "Actions workflow permissions match policies/actions.json."
    fi
  fi

  if ! labels_state="$(gh label list --repo "$repo" --limit 1000 --json name,color,description 2>&1)"; then
    echo "Cannot inspect labels for $repo." >&2
    echo "$labels_state" >&2
    check_errors=$((check_errors + 1))
  elif ! labels_drift="$(python3 - "$repo_root/policies/labels.json" "$labels_state" 2>&1 <<'PY'
import json
import sys

desired = {item["name"]: item for item in json.load(open(sys.argv[1], encoding="utf-8"))}
actual = {item["name"]: item for item in json.loads(sys.argv[2])}
drift = []
for name, expected in desired.items():
    observed = actual.get(name)
    if observed is None:
        drift.append(f"missing {name!r}")
        continue
    if observed.get("color", "").lower() != expected["color"].lower():
        drift.append(f"{name!r} color differs")
    if (observed.get("description") or "") != expected["description"]:
        drift.append(f"{name!r} description differs")
if drift:
    raise SystemExit("; ".join(drift))
PY
  )"; then
    echo "Label settings drift: $labels_drift" >&2
    check_errors=$((check_errors + 1))
  else
    echo "Policy labels match policies/labels.json; extra labels are allowed."
  fi

  if [[ "$ruleset_enforcement_available" != true ]]; then
    [[ "${GITHUB_ACTIONS:-}" == "true" ]] &&
      echo "::warning title=Repository governance degraded::Required branch protection is unavailable for this private repository; continuing without it."
    if [[ "$ruleset_inventory_available" != true ]]; then
      echo "Cannot inspect manually staged Rulesets: $graphql_ruleset_error"
    elif [[ "$ruleset_node_id" == "-" ]]; then
      echo "MISSING remote Ruleset: desired state is preserved in policies/rulesets.json."
    elif [[ "$ruleset_target" != "BRANCH" ]]; then
      echo "STALE manually staged Ruleset: $ruleset_name must target branches."
    else
      echo "STAGED manually configured Ruleset: $ruleset_name is $ruleset_enforcement but is not enforced on this plan."
    fi
    print_ruleset_guidance
    echo "DEGRADED required governance: $ruleset_skip_reason The template must keep working on every GitHub plan and visibility, so this account-plan limitation does not fail closed; a capable plan with rules that do not match policy still does."
    check_degraded=$((check_degraded + 1))
  elif ! branch_rules="$(gh api "repos/$repo/rules/branches/$default_branch" 2>&1)"; then
    echo "Cannot inspect effective rules for $repo:$default_branch." >&2
    echo "$branch_rules" >&2
    check_errors=$((check_errors + 1))
  elif ! ruleset_drift="$(python3 - "$ruleset_payload" "$branch_rules" 2>&1 <<'PY'
import json
import sys

desired = json.load(open(sys.argv[1], encoding="utf-8"))
effective = json.loads(sys.argv[2])
desired_by_type = {rule["type"]: rule for rule in desired["rules"]}
effective_by_type = {}
for rule in effective:
    effective_by_type.setdefault(rule["type"], []).append(rule.get("parameters", {}))

errors = []
for rule_type in ("deletion", "non_fast_forward", "pull_request", "required_status_checks"):
    if rule_type not in effective_by_type:
        errors.append(f"missing {rule_type} rule")

desired_pull_request = desired_by_type["pull_request"]["parameters"]
pull_request_rules = effective_by_type.get("pull_request", [])
if pull_request_rules:
    if max(rule.get("required_approving_review_count", 0) for rule in pull_request_rules) < desired_pull_request["required_approving_review_count"]:
        errors.append("approval requirement is too weak")
    for setting in (
        "dismiss_stale_reviews_on_push",
        "require_code_owner_review",
        "require_last_push_approval",
        "required_review_thread_resolution",
    ):
        if desired_pull_request[setting] and not any(rule.get(setting) for rule in pull_request_rules):
            errors.append(f"{setting} is not enforced")

desired_checks = {
    check["context"]
    for check in desired_by_type["required_status_checks"]["parameters"]["required_status_checks"]
}
effective_checks = {
    check["context"]
    for rule in effective_by_type.get("required_status_checks", [])
    for check in rule.get("required_status_checks", [])
}
missing_checks = sorted(desired_checks - effective_checks)
if missing_checks:
    errors.append("missing required checks: " + ", ".join(missing_checks))

if errors:
    raise SystemExit("; ".join(errors))
PY
  )"; then
    echo "Ruleset settings drift: $ruleset_drift" >&2
    check_errors=$((check_errors + 1))
  else
    echo "Repository governance ready: $default_branch has the required effective rules."
  fi

  if (( check_errors > 0 )); then
    echo "Repository settings check failed with $check_errors actionable difference(s)." >&2
    exit 1
  fi
  if (( check_degraded > 0 )); then
    echo "Repository settings check completed with $check_degraded degraded capability difference(s)."
  else
    echo "All observable repository settings match policy."
  fi
  exit 0
fi

if [[ "$ruleset_enforcement_available" == true ]]; then
  if [[ ! "$code_owner" =~ ^@([^/]+)/([^/[:space:]]+)$ ]]; then
    echo "CODEOWNERS must use an existing GitHub team: @organization/team."
    exit 1
  fi
  owner_org="${BASH_REMATCH[1]}"
  owner_team="${BASH_REMATCH[2]}"
  if ! gh api "orgs/$owner_org/teams/$owner_team" >/dev/null; then
    echo "CODEOWNERS team does not exist or is not visible: $code_owner"
    exit 1
  fi
fi

echo "Repository: $repo"
echo "Mode: $mode"
echo "Account plan: $plan_label"
echo "Repository visibility: $repo_visibility"
echo "Deployment plan:"
echo "- APPLY policies/repository.json"
echo "- APPLY policies/actions.json when account policy permits it"
echo "- APPLY policies/labels.json (create or update policy labels)"
existing_labels="$(gh label list --repo "$repo" --limit 1000 --json name --jq '.[].name')"
desired_labels="$({
  uv run --no-project python - "$repo_root/policies/labels.json" <<'PY'
import json
import sys

for label in json.load(open(sys.argv[1], encoding="utf-8")):
    print(label["name"])
PY
})"
if [[ "$prune_labels" == true ]]; then
  echo "- PRUNE labels outside policy (explicit --prune-labels)"
  while IFS= read -r existing_label; do
    [[ -z "$existing_label" ]] && continue
    if ! grep -Fxq "$existing_label" <<<"$desired_labels"; then
      echo "  - DELETE label: $existing_label"
    fi
  done <<<"$existing_labels"
else
  echo "- KEEP labels outside policy (default additive mode)"
fi
if [[ "$ruleset_enforcement_available" == true ]]; then
  echo "- APPLY policies/rulesets.json (enforced by GitHub)"
  echo "CODEOWNERS team: $code_owner"
elif [[ "$ruleset_inventory_available" == true ]]; then
  echo "- PRESERVE policies/rulesets.json locally (public APIs cannot create a Ruleset on this plan)"
  if [[ "$ruleset_node_id" == "-" ]]; then
    echo "- OPTIONAL MANUAL STAGING: configure a disabled Ruleset in the GitHub web UI"
  else
    echo "- DETECTED manually staged Ruleset: $ruleset_name ($ruleset_enforcement)"
  fi
  print_ruleset_guidance
else
  echo "- PRESERVE policies/rulesets.json locally (cannot inspect manually staged Rulesets: $graphql_ruleset_error)"
  print_ruleset_guidance
fi
if [[ "$plan_label" == "GitHub Enterprise" ]]; then
  echo "- INFO Enterprise-wide identity, audit, network, and organization Rulesets are outside this repository script."
fi

if [[ "$mode" == "plan" ]]; then
  echo "No changes applied. Re-run with 'apply' after review."
  exit 0
fi
gh api --method PATCH "repos/$repo" --input "$repo_root/policies/repository.json" >/dev/null
actions_policy_applied=true
if ! actions_policy_error="$(
  gh api --method PUT "repos/$repo/actions/permissions/workflow" \
    --input "$repo_root/policies/actions.json" 2>&1
)"; then
  if [[ "$actions_policy_error" =~ (403|409|not\ permitted) ]]; then
    actions_policy_applied=false
    echo "DEGRADED Actions PR policy: $actions_policy_error"
    echo "The release workflow will select direct or verification-only mode at runtime."
  else
    echo "Cannot apply Actions workflow permissions for $repo." >&2
    echo "$actions_policy_error" >&2
    exit 1
  fi
fi

while IFS=$'\t' read -r name color description; do
  gh label create "$name" --repo "$repo" --color "$color" \
    --description "$description" --force >/dev/null
done < <(
  uv run --no-project python - "$repo_root/policies/labels.json" <<'PY'
import json
import sys

for label in json.load(open(sys.argv[1], encoding="utf-8")):
    print(label["name"], label["color"], label["description"], sep="\t")
PY
)

if [[ "$prune_labels" == true ]]; then
  while IFS= read -r existing_label; do
    [[ -z "$existing_label" ]] && continue
    if ! grep -Fxq "$existing_label" <<<"$desired_labels"; then
      gh label delete "$existing_label" --repo "$repo" --yes >/dev/null
    fi
  done <<<"$existing_labels"
fi

if [[ "$ruleset_enforcement_available" == true ]]; then
  ruleset_id="$(
    uv run --no-project python -c \
      'import json,sys; print(next((item["id"] for item in json.load(sys.stdin) if item["name"] == "CSARC protected branches"), ""))' \
      <<<"$ruleset_access"
  )"
  if [[ -n "$ruleset_id" ]]; then
    gh api --method PUT "repos/$repo/rulesets/$ruleset_id" \
      --input "$ruleset_payload" >/dev/null
  else
    gh api --method POST "repos/$repo/rulesets" \
      --input "$ruleset_payload" >/dev/null
  fi
fi

GH_REPO="$repo" "$0" check
if [[ "$ruleset_enforcement_available" == true && "$actions_policy_applied" == true ]]; then
  echo "Required repository settings applied, including branch protection."
else
  echo "DEGRADED repository settings applied; unavailable policy remains declarative and runtime workflows adapt."
fi
