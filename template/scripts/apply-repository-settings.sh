#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:-plan}"

if [[ "$mode" != "plan" && "$mode" != "apply" ]]; then
  echo "Usage: $0 [plan|apply]"
  exit 2
fi

command -v gh >/dev/null || { echo "Install and authenticate GitHub CLI first."; exit 1; }
repo="${GH_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
ruleset_payload="$repo_root/policies/rulesets.json"
temporary_ruleset=""
code_owner="$(awk '!/^#/ && NF {print $NF; exit}' "$repo_root/.github/CODEOWNERS")"

if ! ruleset_access="$(gh api "repos/$repo/rulesets" 2>&1)"; then
  echo "Cannot manage the required protected-branch Ruleset for $repo."
  if [[ "$ruleset_access" == *"Upgrade to GitHub Pro or make this repository public"* ]]; then
    echo "Private organization repositories require GitHub Team or above for Rulesets."
    echo "GitHub Free can enforce this policy only when the repository is public."
  else
    echo "$ruleset_access"
  fi
  echo "No settings changed."
  exit 1
fi

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
  uv run python - \
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

echo "Repository: $repo"
echo "Mode: $mode"
echo "CODEOWNERS team: $code_owner"
for policy in repository actions labels rulesets; do
  echo "- policies/$policy.json"
done

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
  uv run python - "$repo_root/policies/labels.json" <<'PY'
import json
import sys

for label in json.load(open(sys.argv[1], encoding="utf-8")):
    print(label["name"], label["color"], label["description"], sep="\t")
PY
)

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

echo "Repository settings applied. Review the Rulesets page in GitHub."
