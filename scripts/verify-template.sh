#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture_root="$(mktemp -d)"
trap 'rm -rf "$fixture_root"' EXIT
cd "$repo_root"

unset VIRTUAL_ENV
export UV_PYTHON=3.14
uv sync --locked --python 3.14
uv lock --check
uv run ruff format --check \
  scripts/report_dependency_ceiling.py \
  scripts/update_python_version.py \
  template/scripts \
  template/tests/test_spec_to_issue.py
uv run ruff check \
  scripts/report_dependency_ceiling.py \
  scripts/update_python_version.py \
  template/scripts \
  template/tests/test_spec_to_issue.py
uv run mypy \
  scripts/report_dependency_ceiling.py \
  scripts/update_python_version.py \
  template/scripts \
  template/tests/test_spec_to_issue.py
uv run pytest template/tests/test_spec_to_issue.py
bash -n scripts/apply-repository-settings.sh
bash -n template/scripts/apply-repository-settings.sh
bash -n scripts/validate-pr-policy
bash -n scripts/test-pr-policy
./scripts/test-pr-policy
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
if ! "$lower_bounds_root/.venv/bin/python" \
  -m pytest template/tests/test_spec_to_issue.py; then
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
grep -q '<title>CSARC Repo Template｜AI 輔助 SDLC 團隊公版</title>' \
  docs/index.html
test -f version.txt
uv run python - <<'PY'
import json
import tomllib
from pathlib import Path

version = Path("version.txt").read_text(encoding="utf-8").strip()
with Path("pyproject.toml").open("rb") as source:
    project_version = tomllib.load(source)["project"]["version"]
with Path("uv.lock").open("rb") as source:
    lock_packages = tomllib.load(source)["package"]
lock_version = next(
    package["version"]
    for package in lock_packages
    if package["name"] == "csarc-repo-template"
)
manifest_version = json.loads(
    Path(".release-please-manifest.json").read_text(encoding="utf-8")
)["."]
if len({version, project_version, lock_version, manifest_version}) != 1:
    raise SystemExit("Template release versions do not match.")
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
for path in (Path("README.md"), Path("docs/index.html")):
    content = path.read_text(encoding="utf-8")
    if f"v{version}" not in content or "x-release-please-version" not in content:
        raise SystemExit(f"{path} does not expose the current release version marker.")
PY
grep -q '^## Working loop$' AGENTS.md
grep -q '^## Commands$' AGENTS.md
grep -q '^## Code Review Rules$' AGENTS.md
grep -q 'Start from `main` and name the branch' AGENTS.md
grep -q 'Open the pull request against `main`' AGENTS.md
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

paired_files=(
  .release-please-manifest.json
  .github/ISSUE_TEMPLATE/config.yml
  .github/ISSUE_TEMPLATE/work-item.yml
  .github/workflows/pr-policy.yml
  .github/workflows/release-please.yml
  policies/actions.json
  policies/labels.json
  policies/repository.json
  scripts/apply-repository-settings.sh
  scripts/install-gitleaks
  scripts/scan-secrets
  scripts/test-pr-policy
  scripts/validate-pr-policy
  zizmor.yml
)
for relative_file in "${paired_files[@]}"; do
  diff -B -w "$repo_root/$relative_file" "$repo_root/template/$relative_file"
done

test "$(grep -c '^    id:' .github/ISSUE_TEMPLATE/work-item.yml)" -eq 3
grep -q '^    id: problem$' .github/ISSUE_TEMPLATE/work-item.yml
grep -q '^    id: acceptance$' .github/ISSUE_TEMPLATE/work-item.yml
grep -q '^    id: verification$' .github/ISSUE_TEMPLATE/work-item.yml
grep -q 'Validate pull request policy' .github/workflows/pr-policy.yml
grep -q './scripts/validate-pr-policy' .github/workflows/pr-policy.yml
grep -q 'type/<issue-number>-short-slug' scripts/validate-pr-policy
grep -q 'Only dev promotion or release-please may target main in dev mode.' \
  scripts/validate-pr-policy
grep -q 'branches: \[main\]' .github/workflows/ci.yml
grep -q 'branches: \[main\]' .github/workflows/osv.yml
grep -q 'branches: \[main\]' .github/workflows/zizmor.yml
grep -q 'target-branch: main' .github/dependabot.yml
grep -q '"name": "CSARC protected branches"' policies/rulesets.json
if grep -q '"refs/heads/dev"' policies/rulesets.json; then
  echo "The template repository must remain in main-only mode."
  exit 1
fi

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

# Default project: strict global coverage and optional features disabled.
uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_name="Template Smoke Test" \
  --data project_slug="template-smoke-test" \
  --data package_name="template_smoke_test" \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  "$repo_root" "$fixture_root/default-project"

git -C "$fixture_root/default-project" init -q -b main
git -C "$fixture_root/default-project" add .
git -C "$fixture_root/default-project" diff --cached --check

test -f "$fixture_root/default-project/.copier-answers.yml"
diff -B -w "$repo_root/.github/dependabot.yml" \
  "$fixture_root/default-project/.github/dependabot.yml"
grep -q 'language: python' "$fixture_root/default-project/.copier-answers.yml"
grep -q '"language_profile": "python"' \
  "$fixture_root/default-project/.csarc/profile.json"
grep -q '"branch_strategy": "main"' \
  "$fixture_root/default-project/.csarc/profile.json"
test "$("$fixture_root/default-project/scripts/detect-language-profile" --suggest)" = \
  "python"
test -f "$fixture_root/default-project/CHANGELOG.md"
test -f "$fixture_root/default-project/.github/workflows/release-please.yml"
test -f "$fixture_root/default-project/release-please-config.json"
test -f "$fixture_root/default-project/.release-please-manifest.json"
test "$(cat "$fixture_root/default-project/.python-version")" = "3.14"
test -f "$fixture_root/default-project/AGENTS.md"
test "$(wc -l < "$fixture_root/default-project/AGENTS.md")" -le 200
test -f "$fixture_root/default-project/docs/index.html"
test -f "$fixture_root/default-project/docs/site-content.js"
grep -q 'Template Smoke Test' \
  "$fixture_root/default-project/docs/site-content.js"
grep -q 'window.CSARC_SITE_CONTENT' \
  "$fixture_root/default-project/docs/site-content.js"
grep -q '^## Scope and sources of truth$' \
  "$fixture_root/default-project/AGENTS.md"
grep -q '^## Commands$' "$fixture_root/default-project/AGENTS.md"
grep -q '^## Code Review Rules$' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'Start from `main` and name the branch' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'Open the pull request against `main`' \
  "$fixture_root/default-project/AGENTS.md"
grep -q 'uv run pytest <test-path>' \
  "$fixture_root/default-project/AGENTS.md"
if grep -q 'pnpm exec vitest' "$fixture_root/default-project/AGENTS.md"; then
  echo "Python-only AGENTS.md must not include TypeScript commands."
  exit 1
fi
test "$(cat "$fixture_root/default-project/CLAUDE.md")" = "@AGENTS.md"
test -f "$fixture_root/default-project/policies/rulesets.json"
grep -q '"context": "verify"' \
  "$fixture_root/default-project/policies/rulesets.json"
grep -q '"context": "scan-pr / osv-scan"' \
  "$fixture_root/default-project/policies/rulesets.json"
if grep -q '"refs/heads/dev"' \
  "$fixture_root/default-project/policies/rulesets.json"; then
  echo "The default main-only Ruleset must not target dev."
  exit 1
fi
test -x "$fixture_root/default-project/scripts/apply-repository-settings.sh"
test -x "$fixture_root/default-project/scripts/install-gitleaks"
test ! -f "$fixture_root/default-project/.pre-commit-config.yaml"
test ! -f "$fixture_root/default-project/package.json"
test ! -f "$fixture_root/default-project/pnpm-workspace.yaml"
test ! -d "$fixture_root/default-project/typescript"
grep -q '^\.DS_Store$' "$fixture_root/default-project/.gitignore"
grep -q '^Thumbs\.db$' "$fixture_root/default-project/.gitignore"
grep -q '^\.vscode/\*$' "$fixture_root/default-project/.gitignore"
grep -q '^\.venv\*/$' "$fixture_root/default-project/.gitignore"
grep -q '^__pycache__/$' "$fixture_root/default-project/.gitignore"
if grep -q '^node_modules/$' "$fixture_root/default-project/.gitignore"; then
  echo "Python-only .gitignore must not contain TypeScript artifacts."
  exit 1
fi
grep -q '^blank_issues_enabled: false$' \
  "$fixture_root/default-project/.github/ISSUE_TEMPLATE/config.yml"
test "$(grep -c '^    id:' \
  "$fixture_root/default-project/.github/ISSUE_TEMPLATE/work-item.yml")" -eq 3
grep -q 'branches: \[main, dev\]' \
  "$fixture_root/default-project/.github/workflows/spec-to-issue.yml"
grep -q 'target-branch: main' \
  "$fixture_root/default-project/.github/dependabot.yml"
grep -q '^requires-python = ">=3.14,<3.15"$' \
  "$fixture_root/default-project/pyproject.toml"
grep -q '^target-version = "py314"$' \
  "$fixture_root/default-project/pyproject.toml"
grep -q 'python-version: "3.14"' \
  "$fixture_root/default-project/.github/workflows/ci.yml"
grep -q 'googleapis/release-please-action@45996ed1f6d02564a971a2fa1b5860e934307cf7' \
  "$fixture_root/default-project/.github/workflows/release-please.yml"
grep -q 'config-file: release-please-config.json' \
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

git -C "$fixture_root/ci-only-project" init -q -b main
git -C "$fixture_root/ci-only-project" add .
git -C "$fixture_root/ci-only-project" diff --cached --check
grep -q 'language: ci' "$fixture_root/ci-only-project/.copier-answers.yml"
grep -q '"language_profile": "ci"' \
  "$fixture_root/ci-only-project/.csarc/profile.json"
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
  --data language=typescript \
  --data branch_strategy=dev \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  "$repo_root" "$fixture_root/typescript-project"

git -C "$fixture_root/typescript-project" init -q -b main
git -C "$fixture_root/typescript-project" add .
git -C "$fixture_root/typescript-project" diff --cached --check

grep -q 'language: typescript' \
  "$fixture_root/typescript-project/.copier-answers.yml"
grep -q '"language_profile": "typescript"' \
  "$fixture_root/typescript-project/.csarc/profile.json"
grep -q '"branch_strategy": "dev"' \
  "$fixture_root/typescript-project/.csarc/profile.json"
grep -q 'Start from `dev` and name the branch' \
  "$fixture_root/typescript-project/AGENTS.md"
grep -q 'Open the pull request against `dev`' \
  "$fixture_root/typescript-project/AGENTS.md"
grep -q 'branches: \[main, dev\]' \
  "$fixture_root/typescript-project/.github/workflows/ci.yml"
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

# Combined project: reusable CI, attestations, and local pre-commit support.
uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_name="All Features Test" \
  --data project_slug="all-features-test" \
  --data package_name="all_features_test" \
  --data language=python-typescript \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  --data use_reusable_workflow=true \
  --data workflow_ref=1111111111111111111111111111111111111111 \
  --data enable_attestations=true \
  --data enable_precommit=true \
  "$repo_root" "$fixture_root/all-features-project"

test -f "$fixture_root/all-features-project/.pre-commit-config.yaml"
grep -q 'reusable-ci.yml@1111111111111111111111111111111111111111' \
  "$fixture_root/all-features-project/.github/workflows/ci.yml"
grep -q 'language-profile: "python-typescript"' \
  "$fixture_root/all-features-project/.github/workflows/ci.yml"
grep -q 'uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6' \
  "$fixture_root/all-features-project/.github/workflows/release.yml"
grep -q '"context": "verify / verify"' \
  "$fixture_root/all-features-project/policies/rulesets.json"
grep -q '"context": "scan-pr / osv-scan"' \
  "$fixture_root/all-features-project/policies/rulesets.json"
test -f "$fixture_root/all-features-project/pyproject.toml"
test -f "$fixture_root/all-features-project/package.json"
test -f "$fixture_root/all-features-project/uv.lock"
test -f "$fixture_root/all-features-project/pnpm-lock.yaml"
test -f "$fixture_root/all-features-project/pnpm-workspace.yaml"
grep -q 'uv run pytest <test-path>' \
  "$fixture_root/all-features-project/AGENTS.md"
grep -q 'pnpm exec vitest run <test-path>' \
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

# Existing-project mode: changed-line coverage keeps the same 80% threshold.
uv run copier copy --trust --defaults --vcs-ref HEAD \
  --data project_name="Existing Project Test" \
  --data project_slug="existing-project-test" \
  --data package_name="existing_project_test" \
  --data code_owner="@Innoguard-Cyber-Arch/template-maintainers" \
  --data python_support_mode=minimum \
  --data python_min_version=3.12 \
  --data coverage_mode=diff \
  "$repo_root" "$fixture_root/existing-project"

grep -q '^requires-python = ">=3.12"$' \
  "$fixture_root/existing-project/pyproject.toml"
grep -q '^target-version = "py312"$' \
  "$fixture_root/existing-project/pyproject.toml"
grep -q 'python-version: "3.12"' \
  "$fixture_root/existing-project/.github/workflows/ci.yml"
grep -q 'python-version: "3.14"' \
  "$fixture_root/existing-project/.github/workflows/ci.yml"

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
  CSARC_PYTHON_VERSION=3.12 \
    UV_PROJECT_ENVIRONMENT=.venv-minimum \
    DIFF_COVER_COMPARE_BRANCH=HEAD \
    ./scripts/verify
  CSARC_PYTHON_VERSION=3.14 \
    UV_PROJECT_ENVIRONMENT=.venv-latest \
    DIFF_COVER_COMPARE_BRANCH=HEAD \
    ./scripts/verify
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

# Verify that an existing generated repository can receive a later template version.
update_source="$fixture_root/update-source"
update_project="$fixture_root/update-project"
mkdir -p "$update_source"
rsync -a --exclude=.git --exclude=.venv --exclude=.cache --exclude=.ruff_cache \
  "$repo_root/" "$update_source/"

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

git -C "$update_project" init -b main
git -C "$update_project" config user.name "Template Test"
git -C "$update_project" config user.email "template-test@example.invalid"
printf '%s\n' 'PROJECT_OWNED = true' \
  > "$update_project/src/csarc_project/__init__.py"
printf '%s\n' 'export const projectOwned = true;' \
  > "$update_project/typescript/src/index.ts"
printf '%s\n' 'window.PROJECT_OWNED_SITE = true;' \
  > "$update_project/docs/site-content.js"
git -C "$update_project" add .
git -C "$update_project" commit -m "test: generated project"

cp "$update_source/template/.gitignore.jinja" \
  "$update_source/template/update-marker"
git -C "$update_source" add template/update-marker
git -C "$update_source" commit -m "test: template v0.1.1"
git -C "$update_source" tag v0.1.1

(
  cd "$update_project"
  "$repo_root/.venv/bin/copier" update --trust --defaults --vcs-ref v0.1.1
)

test -f "$update_project/update-marker"
grep -q '^PROJECT_OWNED = true$' \
  "$update_project/src/csarc_project/__init__.py"
grep -q '^export const projectOwned = true;$' \
  "$update_project/typescript/src/index.ts"
grep -q '^window.PROJECT_OWNED_SITE = true;$' \
  "$update_project/docs/site-content.js"
grep -q '_commit: v0.1.1' "$update_project/.copier-answers.yml"
