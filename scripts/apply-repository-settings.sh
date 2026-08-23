#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:-plan}"
prune_labels=false
allow_unprotected=false

if [[ "$mode" != "plan" && "$mode" != "apply" ]]; then
  echo "Usage: $0 [plan|apply] [--prune-labels] [--allow-unprotected]"
  exit 2
fi
shift $(( $# > 0 ? 1 : 0 ))
for option in "$@"; do
  case "$option" in
    --prune-labels) prune_labels=true ;;
    --allow-unprotected) allow_unprotected=true ;;
    *)
      echo "Usage: $0 [plan|apply] [--prune-labels] [--allow-unprotected]"
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
code_owner="$(awk '!/^#/ && NF {print $NF; exit}' "$repo_root/.github/CODEOWNERS")"

if ! repo_context="$({
  gh api "repos/$repo" \
    --jq '[.owner.login, .owner.type, (.visibility // (if .private then "private" else "public" end)), .permissions.admin] | @tsv'
} 2>&1)"; then
  echo "Cannot read repository metadata for $repo."
  echo "$repo_context"
  exit 1
fi
IFS=$'\t' read -r owner owner_type repo_visibility repo_admin <<<"$repo_context"
if [[ "$repo_admin" != "true" ]]; then
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

ruleset_available=true
ruleset_skip_reason=""
if ! ruleset_access="$(gh api "repos/$repo/rulesets" 2>&1)"; then
  ruleset_available=false
  if [[ "$ruleset_access" == *"Upgrade to GitHub Pro or make this repository public"* ]]; then
    ruleset_skip_reason="Private repositories on GitHub Free do not support Rulesets; use Team or above."
  else
    echo "Cannot determine Ruleset capability for $repo."
    echo "$ruleset_access"
    exit 1
  fi
fi

if [[ "$ruleset_available" == true ]]; then
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
echo "- APPLY policies/actions.json"
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
if [[ "$ruleset_available" == true ]]; then
  echo "- APPLY policies/rulesets.json"
  echo "CODEOWNERS team: $code_owner"
else
  echo "- SKIP policies/rulesets.json: $ruleset_skip_reason"
  echo "- BLOCKED required governance: main is not protected; this private repository needs GitHub Team or public visibility before Rulesets can be enforced."
  echo "- NEXT STEP keep it private: ask the owner to upgrade to $private_ruleset_plan."
  echo "  $billing_url"
  echo "- ALTERNATIVE only when public access is approved: change repository visibility."
  echo "  https://github.com/$repo/settings"
  echo "- THEN create or confirm the CODEOWNERS team $code_owner and rerun:"
  echo "  GH_REPO=$repo ./scripts/apply-repository-settings.sh plan"
  echo "  GH_REPO=$repo ./scripts/apply-repository-settings.sh apply"
  echo "- EXPLICIT DEGRADED MODE: apply --allow-unprotected continues without branch protection and records that state in command output."
fi
if [[ "$plan_label" == "GitHub Enterprise" ]]; then
  echo "- INFO Enterprise-wide identity, audit, network, and organization Rulesets are outside this repository script."
fi

if [[ "$mode" == "plan" ]]; then
  echo "No changes applied. Re-run with 'apply' after review."
  exit 0
fi
if [[ "$ruleset_available" != true && "$allow_unprotected" != true ]]; then
  echo "Refusing to apply incomplete governance without --allow-unprotected." >&2
  echo "Upgrade the account plan or explicitly accept degraded mode." >&2
  exit 1
fi

gh api --method PATCH "repos/$repo" --input "$repo_root/policies/repository.json" >/dev/null
gh api --method PUT "repos/$repo/actions/permissions/workflow" \
  --input "$repo_root/policies/actions.json" >/dev/null

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

if [[ "$ruleset_available" == true ]]; then
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

if [[ "$ruleset_available" == true ]]; then
  echo "Required repository settings applied, including branch protection."
else
  echo "DEGRADED repository settings applied without required branch protection because --allow-unprotected was explicitly provided."
fi
