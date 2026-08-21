#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:-plan}"

if [[ "$mode" != "plan" && "$mode" != "apply" ]]; then
  echo "Usage: $0 [plan|apply]"
  exit 2
fi

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
temporary_ruleset=""
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
if [[ "$owner_type" == "Organization" ]]; then
  account_endpoint="orgs/$owner"
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

  if [[ -n "${CSARC_VERSION_BOT_APP_ID:-}" ]]; then
    temporary_ruleset="$(mktemp)"
    trap 'rm -f "$temporary_ruleset"' EXIT
    uv run --no-project python - \
      "$ruleset_payload" \
      "$temporary_ruleset" \
      "$CSARC_VERSION_BOT_APP_ID" <<'PY'
import json
import sys

source, destination, app_id = sys.argv[1:]
payload = json.load(open(source, encoding="utf-8"))
payload["bypass_actors"] = [
    {
        "actor_id": int(app_id),
        "actor_type": "Integration",
        "bypass_mode": "pull_request",
    }
]
with open(destination, "w", encoding="utf-8") as output:
    json.dump(payload, output, indent=2)
    output.write("\n")
PY
    ruleset_payload="$temporary_ruleset"
  fi
fi

echo "Repository: $repo"
echo "Mode: $mode"
echo "Account plan: $plan_label"
echo "Repository visibility: $repo_visibility"
echo "Deployment plan:"
echo "- APPLY policies/repository.json"
echo "- APPLY policies/actions.json"
echo "- APPLY policies/labels.json (exact set; remove labels outside policy)"
if [[ "$ruleset_available" == true ]]; then
  echo "- APPLY policies/rulesets.json"
  echo "CODEOWNERS team: $code_owner"
else
  echo "- SKIP policies/rulesets.json: $ruleset_skip_reason"
  echo "- WARNING main is not protected: this private repository needs GitHub Team or public visibility before Rulesets can be enforced."
fi
if [[ "$plan_label" == "GitHub Enterprise" ]]; then
  echo "- INFO Enterprise-wide identity, audit, network, and organization Rulesets are outside this repository script."
fi

if [[ "$mode" == "plan" ]]; then
  echo "No changes applied. Re-run with 'apply' after review."
  exit 0
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

desired_labels="$({
  uv run --no-project python - "$repo_root/policies/labels.json" <<'PY'
import json
import sys

for label in json.load(open(sys.argv[1], encoding="utf-8")):
    print(label["name"])
PY
})"
while IFS= read -r existing_label; do
  [[ -z "$existing_label" ]] && continue
  if ! grep -Fxq "$existing_label" <<<"$desired_labels"; then
    gh label delete "$existing_label" --repo "$repo" --yes >/dev/null
  fi
done < <(gh label list --repo "$repo" --limit 1000 --json name --jq '.[].name')

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

echo "Available repository settings applied. Review the deployment plan above."
