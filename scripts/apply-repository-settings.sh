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
    --allow-unprotected)
      # Retain this parsed option for CLI compatibility.
      # shellcheck disable=SC2034
      allow_unprotected=true
      ;;
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
release_policy="$repo_root/policies/releases.json"
# issue_creation_policy has no REST field (an invalid value is silently
# ignored and the field never appears in REST GET responses), so it is kept
# out of policies/repository.json's flat REST PATCH and declared here
# instead; it is only readable/writable through the GraphQL API.
issue_creation_policy_payload="$repo_root/policies/issue-creation.json"
# security_and_analysis requires GitHub Advanced Security on a private repo
# (free on public). A rejected nested field can fail the entire repos/$repo
# PATCH atomically, so it is kept out of policies/repository.json and PATCHed
# in its own dedicated call instead.
security_scanning_payload="$repo_root/policies/security-scanning.json"
# release_phase (Issue #607): whole-project release maturity, hand-declared
# in policies/project-stage.json -- a THIRD axis, deliberately distinct
# from generate_audit_trail.py's per-PR governance_stage and
# profiles/catalog.yaml's per-profile stage (see
# scripts/release_phase_rulesets.py's module docstring for the full
# naming-collision warning). It gates how far the Alpha self-approval
# Ruleset bypass (#580) is allowed to reach: required_status_checks may
# only inherit the bypass in "alpha"; from "beta" onward it lives in its
# own Ruleset (policies/rulesets-required-checks.json) with an always-empty
# bypass_actors. Only this repository ships both policy files today --
# template-generated repositories keep the pre-#607 single-Ruleset layout
# and are unaffected by any logic gated on release_phase_gated below.
project_stage_payload="$repo_root/policies/project-stage.json"
required_checks_ruleset_payload="$repo_root/policies/rulesets-required-checks.json"
release_phase_module="$repo_root/scripts/release_phase_rulesets.py"
release_phase_gated=false
release_phase=""
if [[ -f "$project_stage_payload" && -f "$required_checks_ruleset_payload" ]]; then
  release_phase_gated=true
  release_phase="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["release_phase"])' "$project_stage_payload")"
fi
# effective_ruleset_payload / effective_required_checks_ruleset_payload are
# the per-Ruleset payload(s) actually pushed to or compared against GitHub.
# When release_phase_gated they are release_phase-assembled temp files
# (scripts/release_phase_rulesets.py assemble); otherwise they are exactly
# the checked-in files, unchanged from pre-#607 behavior.
effective_ruleset_payload="$ruleset_payload"
effective_required_checks_ruleset_payload="$required_checks_ruleset_payload"
if [[ "$release_phase_gated" == true ]]; then
  release_phase_tempdir="$(mktemp -d)"
  trap 'rm -rf "$release_phase_tempdir"' EXIT
  effective_ruleset_payload="$release_phase_tempdir/review-ruleset.json"
  effective_required_checks_ruleset_payload="$release_phase_tempdir/required-checks-ruleset.json"
  if ! release_phase_assembly_error="$(
    python3 "$release_phase_module" assemble \
      --project-stage "$project_stage_payload" \
      --review-ruleset "$ruleset_payload" \
      --required-checks-ruleset "$required_checks_ruleset_payload" \
      2>&1 1>"$release_phase_tempdir/assembled.json"
  )"; then
    echo "Cannot assemble release_phase-gated Rulesets." >&2
    echo "$release_phase_assembly_error" >&2
    exit 1
  fi
  python3 - "$release_phase_tempdir/assembled.json" \
    "$effective_ruleset_payload" "$effective_required_checks_ruleset_payload" <<'PY'
import json
import sys

rulesets = json.load(open(sys.argv[1], encoding="utf-8"))
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(rulesets[0], handle)
with open(sys.argv[3], "w", encoding="utf-8") as handle:
    json.dump(rulesets[1], handle)
PY
fi
# check_desired_rules_payload_extra is only used by the check-mode drift
# comparison below: the effective-rules-branches endpoint returns the
# union of rules enforced across every applicable Ruleset, not scoped by
# name, so verifying "is required_status_checks in effect" must compare
# against the union of both files' rules regardless of which live
# Ruleset object currently carries that rule.
check_desired_rules_payload_extra=""
if [[ -f "$required_checks_ruleset_payload" ]]; then
  check_desired_rules_payload_extra="$required_checks_ruleset_payload"
fi
ruleset_name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["name"])' "$ruleset_payload")"
desired_issue_creation_policy="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["issue_creation_policy"])' "$issue_creation_policy_payload")"
legacy_ruleset_name="CSARC preserve dev next"
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

pages_policy="$repo_root/policies/pages.json"
pages_policy_enabled="$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1], encoding="utf-8"))["enabled"]))' "$pages_policy")"
# GitHub Pages is free for public repositories on every plan; a private
# repository requires GitHub Enterprise Cloud regardless of Ruleset
# enforcement availability, so this is computed independently of
# ruleset_enforcement_available above.
pages_enforcement_available=true
if [[ "$repo_visibility" != "public" && "$plan_label" != "GitHub Enterprise" ]]; then
  pages_enforcement_available=false
fi

codeowners_validation=""
codeowners_inspection_error=""
codeowners_inspection_available=false
if [[ ! "$code_owner" =~ ^@([^/]+)/([^/[:space:]]+)$ ]]; then
  codeowners_validation="CODEOWNERS must use a GitHub team: @organization/team."
elif ! codeowners_state="$(gh api "repos/$repo/teams" --paginate --slurp 2>&1)"; then
  codeowners_inspection_error="$codeowners_state"
elif ! codeowners_validation="$(python3 - "$code_owner" "$codeowners_state" 2>&1 <<'PY'
import json
import sys

owner = sys.argv[1]
slug = owner.split("/", 1)[1].casefold()
pages = json.loads(sys.argv[2])
teams = [team for page in pages for team in page]
team = next((item for item in teams if item.get("slug", "").casefold() == slug), None)
if team is None:
    print(f"{owner} is missing, invisible, or lacks repository access.")
else:
    permissions = team.get("permissions") or {}
    writable = team.get("permission") in {"push", "maintain", "admin"} or any(
        permissions.get(level) is True for level in ("push", "maintain", "admin")
    )
    if not writable:
        print(
            f"{owner} lacks repository write access "
            f"(permission: {team.get('permission', 'unknown')})."
        )
PY
)"; then
  codeowners_inspection_error="$codeowners_validation"
  codeowners_validation=""
else
  codeowners_inspection_available=true
fi

if [[ "$mode" != "check" ]]; then
  if [[ -n "$codeowners_validation" ]]; then
    echo "CODEOWNERS validation failed: $codeowners_validation" >&2
    exit 1
  fi
  if [[ "$codeowners_inspection_available" != true ]]; then
    echo "Cannot inspect CODEOWNERS for $repo." >&2
    echo "$codeowners_inspection_error" >&2
    exit 1
  fi
fi

print_ruleset_guidance() {
  echo "- DEGRADED required governance: $default_branch is not protected on this private repository."
  echo "- PRESERVED desired Ruleset: policies/rulesets.json keeps main branch governance ready for a supported plan or public repository."
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
    # GraphQL variables are intentionally literal in the query document.
    # shellcheck disable=SC2016
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
  if ! graphql_state="$(python3 - "$ruleset_name" "$legacy_ruleset_name" "$graphql_result" <<'PY'
import json
import sys

ruleset_name = sys.argv[1]
legacy_ruleset_name = sys.argv[2]
repository = json.loads(sys.argv[3])["data"]["repository"]
if repository is None:
    raise SystemExit("Repository is unavailable through the GraphQL API.")
ruleset = next(
    (item for item in repository["rulesets"]["nodes"] if item["name"] == ruleset_name),
    None,
)
legacy_ruleset = next(
    (
        item
        for item in repository["rulesets"]["nodes"]
        if item["name"] == legacy_ruleset_name
    ),
    None,
)
print(
    ruleset["id"] if ruleset else "-",
    ruleset["enforcement"] if ruleset else "-",
    ruleset["target"] if ruleset else "-",
    legacy_ruleset["id"] if legacy_ruleset else "-",
    sep="|",
)
PY
  )"; then
    graphql_ruleset_error="$graphql_state"
    return 1
  fi
  IFS='|' read -r ruleset_node_id ruleset_enforcement ruleset_target legacy_ruleset_id \
    <<<"$graphql_state"
}

load_issue_creation_policy() {
  local graphql_result
  if ! graphql_result="$(
    # GraphQL variables are intentionally literal in the query document.
    # shellcheck disable=SC2016
    gh api graphql \
      -f query='query($owner: String!, $name: String!) {
        repository(owner: $owner, name: $name) { issueCreationPolicy }
      }' \
      -f owner="$owner" \
      -f name="${repo#*/}" 2>&1
  )"; then
    issue_creation_policy_error="$graphql_result"
    return 1
  fi
  if ! issue_creation_policy_live="$(
    python3 -c 'import json,sys; print(json.loads(sys.argv[1])["data"]["repository"]["issueCreationPolicy"])' \
      "$graphql_result" 2>&1
  )"; then
    issue_creation_policy_error="$issue_creation_policy_live"
    return 1
  fi
}

ruleset_enforcement_available=true
ruleset_inventory_available=true
ruleset_skip_reason=""
graphql_ruleset_error=""
ruleset_node_id="-"
ruleset_enforcement="-"
ruleset_target="-"
legacy_ruleset_id="-"
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
else
  legacy_ruleset_id="$(
    uv run --no-project python -c \
      'import json,sys; name=sys.argv[1]; print(next((item["id"] for item in json.load(sys.stdin) if item["name"] == name), "-"))' \
      "$legacy_ruleset_name" <<<"$ruleset_access"
  )"
fi

if [[ "$mode" == "check" ]]; then
  check_errors=0
  check_degraded=0
  repository_drift=""
  repository_state_available=false

  if [[ "$legacy_ruleset_id" != "-" ]]; then
    echo "Stale Ruleset must be removed: $legacy_ruleset_name ($legacy_ruleset_id)." >&2
    check_errors=$((check_errors + 1))
  fi

  if [[ -n "$codeowners_validation" ]]; then
    echo "CODEOWNERS validation failed: $codeowners_validation" >&2
    check_errors=$((check_errors + 1))
  elif [[ "$codeowners_inspection_available" != true ]]; then
    if [[ "$repo_admin" == "true" ]]; then
      echo "Cannot inspect CODEOWNERS for $repo." >&2
      echo "$codeowners_inspection_error" >&2
      check_errors=$((check_errors + 1))
    else
      [[ "${GITHUB_ACTIONS:-}" == "true" ]] &&
        echo "::warning title=CODEOWNERS inspection degraded::The token cannot validate configured owners."
      echo "DEGRADED CODEOWNERS inspection: token cannot validate configured owners."
      check_degraded=$((check_degraded + 1))
    fi
  else
    echo "CODEOWNERS owners are valid and have repository write access."
  fi

  if ! repository_state="$(gh api "repos/$repo" 2>&1)"; then
    echo "Cannot inspect repository settings for $repo." >&2
    echo "$repository_state" >&2
    check_errors=$((check_errors + 1))
  else
    repository_state_available=true
    if ! repository_drift="$(python3 - "$repo_root/policies/repository.json" "$repository_state" 2>&1 <<'PY'
import json
import sys

desired = json.load(open(sys.argv[1], encoding="utf-8"))
actual = json.loads(sys.argv[2])
drift = [
    f"{key}: desired {value!r}, live {actual.get(key)!r}"
    for key, value in desired.items()
    if key in actual and actual[key] != value
]
if drift:
    raise SystemExit("; ".join(drift))
PY
    )"; then
      echo "Repository settings drift: $repository_drift" >&2
      check_errors=$((check_errors + 1))
    fi
  fi
  if [[ "$repository_state_available" == "true" ]]; then
    repository_missing="$(python3 - "$repo_root/policies/repository.json" "$repository_state" <<'PY'
import json
import sys

desired = json.load(open(sys.argv[1], encoding="utf-8"))
actual = json.loads(sys.argv[2])
print(", ".join(key for key in desired if key not in actual))
PY
    )"
    if [[ -n "$repository_missing" ]]; then
      if [[ "$repo_admin" == "true" ]]; then
        echo "Cannot observe repository setting fields despite administrator access: $repository_missing" >&2
        check_errors=$((check_errors + 1))
      else
        [[ "${GITHUB_ACTIONS:-}" == "true" ]] &&
          echo "::warning title=Settings inspection degraded::The token cannot read administrator-only repository fields."
        echo "DEGRADED repository inspection: token cannot read administrator-only fields: $repository_missing"
        check_degraded=$((check_degraded + 1))
      fi
    elif [[ -z "$repository_drift" ]]; then
      echo "Repository settings match policies/repository.json."
    fi
  fi

  issue_creation_policy_error=""
  if ! load_issue_creation_policy; then
    echo "Cannot inspect issue creation policy for $repo." >&2
    echo "$issue_creation_policy_error" >&2
    check_errors=$((check_errors + 1))
  elif [[ "$issue_creation_policy_live" != "$desired_issue_creation_policy" ]]; then
    echo "Issue creation policy drift: desired $desired_issue_creation_policy, live $issue_creation_policy_live." >&2
    check_errors=$((check_errors + 1))
  else
    echo "Issue creation policy matches policies/issue-creation.json."
  fi

  # security_and_analysis is compared per field using the same repository
  # GET response fetched above; desired "enabled" but live "disabled" (or
  # missing) is treated as DEGRADED (a plan/GHAS limitation), any other
  # mismatch is treated as actionable drift. This mirrors the "DEGRADED
  # Actions PR policy" true-vs-false heuristic used for Actions permissions.
  if [[ "$repository_state_available" != "true" ]]; then
    echo "Cannot inspect security_and_analysis for $repo: repository settings were not observable." >&2
    check_errors=$((check_errors + 1))
  elif ! security_and_analysis_status="$(python3 - "$security_scanning_payload" "$repository_state" 2>&1 <<'PY'
import json
import sys

desired = json.load(open(sys.argv[1], encoding="utf-8"))["security_and_analysis"]
actual = (json.loads(sys.argv[2]) or {}).get("security_and_analysis") or {}
for field, expected in desired.items():
    expected_status = expected["status"]
    observed = (actual.get(field) or {}).get("status")
    if observed == expected_status:
        print(f"MATCH|{field}|{observed}")
    elif expected_status == "enabled" and observed in (None, "disabled"):
        print(f"DEGRADED|{field}|{observed}")
    else:
        print(f"DRIFT|{field}|{observed}")
PY
  )"; then
    echo "Cannot compare security_and_analysis for $repo." >&2
    echo "$security_and_analysis_status" >&2
    check_errors=$((check_errors + 1))
  else
    while IFS='|' read -r security_field_kind security_field_name security_field_value; do
      [[ -z "$security_field_kind" ]] && continue
      case "$security_field_kind" in
        MATCH)
          echo "security_and_analysis.$security_field_name matches policies/security-scanning.json (enabled)."
          ;;
        DEGRADED)
          [[ "${GITHUB_ACTIONS:-}" == "true" ]] &&
            echo "::warning title=Security scanning degraded::security_and_analysis.$security_field_name is disabled although policy requests it."
          echo "DEGRADED security_and_analysis.$security_field_name: desired enabled, live ${security_field_value:-disabled}; GitHub Advanced Security or an organization/plan policy may block this capability on this repository."
          check_degraded=$((check_degraded + 1))
          ;;
        DRIFT)
          echo "security_and_analysis drift: $security_field_name desired enabled, live ${security_field_value:-unknown}." >&2
          check_errors=$((check_errors + 1))
          ;;
      esac
    done <<<"$security_and_analysis_status"
  fi

  if ! release_state="$(gh api "repos/$repo/immutable-releases" 2>&1)"; then
    echo "Cannot inspect the required immutable Releases setting for $repo." >&2
    echo "$release_state" >&2
    check_errors=$((check_errors + 1))
  elif ! release_drift="$(python3 - "$release_policy" "$release_state" 2>&1 <<'PY'
import json
import sys

desired = json.load(open(sys.argv[1], encoding="utf-8"))
actual = json.loads(sys.argv[2])
if actual.get("enabled") is not desired["enabled"]:
    raise SystemExit(
        "enabled: desired "
        f"{desired['enabled']!r}, live {actual.get('enabled')!r}"
    )
PY
  )"; then
    echo "Release settings drift: $release_drift" >&2
    echo "Immutable Releases are required before the release workflow can publish." >&2
    check_errors=$((check_errors + 1))
  else
    echo "Immutable Releases match policies/releases.json."
  fi

  if [[ "$pages_policy_enabled" != "true" ]]; then
    echo "Pages policy disabled: policies/pages.json requests enabled=false; no live GitHub Pages check performed."
  elif [[ "$pages_enforcement_available" != true ]]; then
    [[ "${GITHUB_ACTIONS:-}" == "true" ]] &&
      echo "::warning title=GitHub Pages degraded::GitHub Pages is unavailable for this private repository on $plan_label."
    echo "DEGRADED GitHub Pages: private repositories require GitHub Enterprise Cloud; $plan_label cannot enable Pages while $repo is private. policies/pages.json stays enabled=true for when this repository is public or the account upgrades; the template must keep working on every GitHub plan and visibility, so this account-plan and visibility limitation does not fail closed."
    check_degraded=$((check_degraded + 1))
  elif ! pages_state="$(gh api "repos/$repo/pages" 2>&1)"; then
    if [[ "$pages_state" == *"Not Found"* ]]; then
      echo "Pages settings drift: GitHub Pages is not enabled for $repo; policies/pages.json requests enabled=true." >&2
      check_errors=$((check_errors + 1))
    else
      echo "Cannot inspect GitHub Pages settings for $repo." >&2
      echo "$pages_state" >&2
      check_errors=$((check_errors + 1))
    fi
  elif ! pages_drift="$(python3 - "$pages_policy" "$pages_state" 2>&1 <<'PY'
import json
import sys

desired = json.load(open(sys.argv[1], encoding="utf-8"))["source"]
actual = json.loads(sys.argv[2]).get("source", {})
drift = [
    f"source.{key}: desired {value!r}, live {actual.get(key)!r}"
    for key, value in desired.items()
    if actual.get(key) != value
]
if drift:
    raise SystemExit("; ".join(drift))
PY
  )"; then
    echo "Pages settings drift: $pages_drift" >&2
    check_errors=$((check_errors + 1))
  else
    echo "Pages settings match policies/pages.json."
  fi

  if ! actions_state="$(gh api "repos/$repo/actions/permissions/workflow" 2>&1)"; then
    if [[ "$repo_admin" != "true" && "$actions_state" == *"Resource not accessible by integration"* ]]; then
      [[ "${GITHUB_ACTIONS:-}" == "true" ]] &&
        echo "::warning title=Actions inspection degraded::The token cannot read administrator-only Actions settings."
      echo "DEGRADED Actions inspection: token cannot read administrator-only workflow permissions."
      check_degraded=$((check_degraded + 1))
    else
      echo "Cannot inspect Actions workflow permissions for $repo." >&2
      echo "$actions_state" >&2
      check_errors=$((check_errors + 1))
    fi
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
      echo "DEGRADED Actions PR policy: desired true, live false; an organization policy may block this capability. No release workflow is enabled by this script."
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
  elif ! ruleset_drift="$(python3 - "$ruleset_payload" "$branch_rules" "$check_desired_rules_payload_extra" 2>&1 <<'PY'
import json
import sys

desired = json.load(open(sys.argv[1], encoding="utf-8"))
effective = json.loads(sys.argv[2])
# Issue #607: required_status_checks may live in a separate Ruleset
# (policies/rulesets-required-checks.json) from beta onward. The
# effective-rules-branches endpoint returns the union of rules enforced
# across every applicable Ruleset, not scoped by name, so "desired" must
# be the union of both files' rules too -- see check_desired_rules_payload_extra
# where this script computes the third argument.
if len(sys.argv) > 3 and sys.argv[3]:
    extra_desired = json.load(open(sys.argv[3], encoding="utf-8"))
    desired = {**desired, "rules": [*desired["rules"], *extra_desired["rules"]]}
desired_by_type = {rule["type"]: rule for rule in desired["rules"]}
effective_by_type = {}
for rule in effective:
    effective_by_type.setdefault(rule["type"], []).append(rule.get("parameters", {}))

errors = []
for rule_type in ("non_fast_forward", "pull_request", "required_status_checks"):
    if rule_type not in effective_by_type:
        errors.append(f"missing {rule_type} rule")
    if rule_type not in desired_by_type:
        errors.append(f"policy is missing a {rule_type} rule")

if "pull_request" in desired_by_type:
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

if "required_status_checks" in desired_by_type:
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

echo "Repository: $repo"
echo "Mode: $mode"
echo "Account plan: $plan_label"
echo "Repository visibility: $repo_visibility"
echo "Deployment plan:"
echo "- APPLY policies/repository.json"
echo "- APPLY policies/issue-creation.json (issue_creation_policy via GraphQL)"
echo "- APPLY policies/releases.json (immutable Releases)"
if [[ "$pages_policy_enabled" != "true" ]]; then
  echo "- SKIP policies/pages.json (enabled=false)"
elif [[ "$pages_enforcement_available" == true ]]; then
  echo "- APPLY policies/pages.json (GitHub Pages)"
else
  echo "- DEGRADED policies/pages.json: GitHub Pages requires GitHub Enterprise Cloud for a private repository on $plan_label"
fi
echo "- APPLY policies/actions.json when account policy permits it"
echo "- APPLY policies/security-scanning.json (security_and_analysis) when GitHub Advanced Security or repository visibility permits it"
echo "- APPLY policies/labels.json (create or update policy labels)"
if [[ "$legacy_ruleset_id" != "-" ]]; then
  echo "- DELETE stale Ruleset: $legacy_ruleset_name ($legacy_ruleset_id)"
fi
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
  if [[ "$release_phase_gated" == true ]]; then
    echo "- APPLY policies/rulesets.json + policies/rulesets-required-checks.json (release_phase=$release_phase, enforced by GitHub)"
  else
    echo "- APPLY policies/rulesets.json (enforced by GitHub)"
  fi
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
# REST has no issue_creation_policy field, so this is applied through the
# GraphQL updateRepository mutation instead of the flat PATCH above. This
# capability has not been observed to be plan/visibility-gated, so a failure
# here is treated as a hard error like the other required baseline settings.
repository_node_id="$(gh api "repos/$repo" --jq .node_id)"
if ! issue_creation_policy_apply_error="$(
  # GraphQL variables are intentionally literal in the mutation document.
  # shellcheck disable=SC2016
  gh api graphql \
    -f query='mutation($id: ID!, $policy: RepositoryIssueCreationPolicy!) {
      updateRepository(input: {repositoryId: $id, issueCreationPolicy: $policy}) {
        repository { issueCreationPolicy }
      }
    }' \
    -f id="$repository_node_id" \
    -f policy="$desired_issue_creation_policy" 2>&1
)"; then
  echo "Cannot apply issue creation policy for $repo." >&2
  echo "$issue_creation_policy_apply_error" >&2
  exit 1
fi
if ! release_policy_error="$(
  gh api --method PUT "repos/$repo/immutable-releases" 2>&1
)"; then
  echo "Cannot enable required immutable Releases for $repo." >&2
  echo "$release_policy_error" >&2
  exit 1
fi
pages_policy_applied=true
if [[ "$pages_policy_enabled" == "true" ]]; then
  if [[ "$pages_enforcement_available" != true ]]; then
    pages_policy_applied=false
    echo "DEGRADED GitHub Pages: private repositories require GitHub Enterprise Cloud; $plan_label cannot enable Pages while $repo is private. policies/pages.json stays enabled=true for when this repository is public or the account upgrades."
  else
    pages_source_payload="$(python3 -c 'import json,sys; policy=json.load(open(sys.argv[1], encoding="utf-8")); print(json.dumps({"source": policy["source"]}))' "$pages_policy")"
    if gh api "repos/$repo/pages" >/dev/null 2>&1; then
      if ! pages_policy_error="$(echo "$pages_source_payload" | gh api --method PUT "repos/$repo/pages" --input - 2>&1)"; then
        echo "Cannot update GitHub Pages settings for $repo." >&2
        echo "$pages_policy_error" >&2
        exit 1
      fi
    elif ! pages_policy_error="$(echo "$pages_source_payload" | gh api --method POST "repos/$repo/pages" --input - 2>&1)"; then
      echo "Cannot enable GitHub Pages for $repo." >&2
      echo "$pages_policy_error" >&2
      exit 1
    fi
  fi
fi
actions_policy_applied=true
if ! actions_policy_error="$(
  gh api --method PUT "repos/$repo/actions/permissions/workflow" \
    --input "$repo_root/policies/actions.json" 2>&1
)"; then
  if [[ "$actions_policy_error" =~ (403|409|not\ permitted) ]]; then
    actions_policy_applied=false
    echo "DEGRADED Actions PR policy: $actions_policy_error"
    echo "No release workflow is enabled; record this degraded capability before designing one."
  else
    echo "Cannot apply Actions workflow permissions for $repo." >&2
    echo "$actions_policy_error" >&2
    exit 1
  fi
fi

# security_and_analysis gets its own dedicated PATCH (never merged into the
# repository.json PATCH above): a rejected nested field would fail that
# whole request atomically, taking basic unrelated settings down with it.
security_and_analysis_applied=true
if ! security_and_analysis_error="$(
  gh api --method PATCH "repos/$repo" --input "$security_scanning_payload" 2>&1
)"; then
  if [[ "$security_and_analysis_error" =~ (403|422|Advanced\ Security|not\ permitted) ]]; then
    security_and_analysis_applied=false
    echo "DEGRADED security_and_analysis: $security_and_analysis_error"
    echo "GitHub Advanced Security or an organization/plan policy may block secret scanning, push protection, or Dependabot security updates on this repository."
  else
    echo "Cannot apply security_and_analysis settings for $repo." >&2
    echo "$security_and_analysis_error" >&2
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

apply_ruleset_payload() {
  # Create-or-update a single live Ruleset by the `name` field inside the
  # given payload file, against the repository/rulesets inventory already
  # fetched into $ruleset_access. Shared by the always-present review
  # Ruleset and, when release_phase_gated, the required-checks Ruleset
  # (Issue #607) -- both follow the identical GitHub API shape.
  local payload_file="$1"
  local payload_name payload_id
  payload_name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["name"])' "$payload_file")"
  payload_id="$(
    uv run --no-project python -c \
      'import json,sys; name=sys.argv[1]; print(next((item["id"] for item in json.load(sys.stdin) if item["name"] == name), ""))' \
      "$payload_name" <<<"$ruleset_access"
  )"
  if [[ -n "$payload_id" ]]; then
    gh api --method PUT "repos/$repo/rulesets/$payload_id" \
      --input "$payload_file" >/dev/null
  else
    gh api --method POST "repos/$repo/rulesets" \
      --input "$payload_file" >/dev/null
  fi
}

if [[ "$ruleset_enforcement_available" == true ]]; then
  if [[ "$legacy_ruleset_id" != "-" ]]; then
    gh api --method DELETE "repos/$repo/rulesets/$legacy_ruleset_id" >/dev/null
  fi
  apply_ruleset_payload "$effective_ruleset_payload"
  if [[ "$release_phase_gated" == true ]]; then
    apply_ruleset_payload "$effective_required_checks_ruleset_payload"
  fi
fi

GH_REPO="$repo" "$0" check
if [[ "$ruleset_enforcement_available" == true && "$actions_policy_applied" == true &&
  "$pages_policy_applied" == true && "$security_and_analysis_applied" == true ]]; then
  echo "Required repository settings applied, including branch protection."
else
  echo "DEGRADED repository settings applied; unavailable policy remains declarative and runtime workflows adapt."
fi
