(() => {
    const configExamples = {};

    Object.assign(configExamples, {
      agents: [
        {
          title: '人與 AI 各看一個清楚入口',
          goal: 'README 服務人；根目錄 AGENTS.md 是 AI 規範唯一來源，CLAUDE.md 只薄匯入。',
          summary: '子目錄只有命令或安全界線真的不同時才增加 AGENTS.md，避免多份規範漂移。',
          file: 'README.md＋AGENTS.md＋CLAUDE.md',
          code: `# README.md
## Quick start
## Verification
## Support

# AGENTS.md
## Scope and sources of truth
## Working loop
## Commands
## Editing boundaries
## Safety`
        },
        {
          title: '依專案語言只產生真的可執行的指令',
          goal: 'CI/CD-only 不假裝有語言指令；Python-only 不看到 pnpm；TypeScript-only 不看到 uv；混合案才同時列出兩套。',
          summary: 'Copier 依 `language` 渲染指令；四種組合最後都回到 `./scripts/verify`，公版驗證也會阻擋錯誤 profile。',
          file: 'template/AGENTS.md.jinja＋scripts/verify-template.sh',
          code: `{% if language in ["python", "python-typescript"] %}
- Python iteration: uv run ruff check <paths>
{% endif %}
{% if language in ["typescript", "python-typescript"] %}
- TypeScript iteration: pnpm exec biome check <paths>
{% endif %}
- Required final check: ./scripts/verify`
        },
        {
          title: '平行可寫工作各自隔離',
          goal: '一項可寫工作對應一個 branch 與 worktree，只平行處理互不依賴的範圍。',
          summary: '唯讀工作不需另開 worktree；清理程式只回收已合併且乾淨的目錄。',
          file: 'AGENTS.md＋scripts/cleanup-worktrees＋scripts/test-worktree-cleanup',
          code: `git worktree add ../task-388 -b feat/388-align-ai-guidelines
./scripts/test-worktree-cleanup
./scripts/cleanup-worktrees`
        },
        {
          title: 'AI 規範、驗證與治理各有唯一責任',
          goal: 'AGENTS.md 說明怎麼做；scripts 提供證據；Action 只包裝執行；規則治理單獨定義合併資格、權限與例外。',
          summary: '人保留需求、重大取捨、外部影響與不可逆操作；本頁不重複定義合併權限。',
          file: 'AGENTS.md＋scripts/verify＋.github/workflows/＋policies/',
          code: `# Local and Action use the same logic
./scripts/verify

# Governance and merge eligibility live under Rules governance
policies/actions.json
policies/rulesets.json`
        }
      ],
      governance: [
        {
          title: '分開檢查 Ruleset policy、遠端儲存與實際強制能力',
          goal: 'Copier 建檔時可能還沒有遠端 repo；真正套用前再向 GitHub 查詢，避免依使用者手填的方案猜測。',
          summary: '先確認登入者具有 repo admin；REST endpoint 判斷 GitHub 是否會強制規則。Free private 的 REST 與 GraphQL mutation 都會回 403；GraphQL query 僅用來偵測管理員是否曾從 Web UI 人工預建。其他未知錯誤會停止。',
          file: 'scripts/apply-repository-settings.sh',
          code: `gh api "repos/$repo" \
  --jq '[.owner.login, .owner.type, .visibility, .permissions.admin] | @tsv'
gh api "orgs/$owner" --jq '.plan.name'
gh api "repos/$repo/rulesets"
# Free private keeps the desired policy in the repository.

./scripts/apply-repository-settings.sh plan`
        },
        {
          title: '所有方案都套基本設定並保留政策來源',
          goal: 'Free private repo 不整包放棄；合併方式、Actions 預設權限、標籤與未來要啟用的 Ruleset 都跟著公版。',
          summary: 'Free private 直接套用 squash-only、刪除已合併分支、Actions 預設唯讀與標籤，並在 repo 內保留 ACTIVE Ruleset policy。公開 API 不能建立該 Ruleset，因此輸出保留 DEGRADED。',
          file: 'policies/repository.json＋policies/actions.json＋policies/labels.json',
          code: `./scripts/apply-repository-settings.sh plan
# Review the APPLY and PRESERVE list first.
./scripts/apply-repository-settings.sh apply
./scripts/apply-repository-settings.sh check`
        },
        {
          title: '方案決定 Ruleset 是否成為真正門禁',
          goal: 'Free private 先在 repo 保存相同政策；public、Pro、Team 或 Enterprise 可強制 PR、一位核准、CODEOWNER 與必要檢查。Enterprise 的組織規則仍另審。',
          summary: '所有方案都先用 repository teams API 驗證 PR 內設定的 team 與 write access；Free private 另從 REVIEWERS 名單輪派一位個別 reviewer，但 Ruleset 只保留 STAGED／MISSING 與 DEGRADED 紀錄。',
          file: 'policies/rulesets.json＋.github/CODEOWNERS＋governance-comment.yml',
          code: `# The same policy is stored in every repository and enforced when supported.
required reviews: 1
require CODEOWNER review: true
required checks:
  - verify
  - title
  - scan-pr / osv-scan
  - audit

# Enterprise organization controls are report-only here.`
        },
        {
          title: '排程每天重跑 check，縮短 CI-only 的檢查間隔',
          goal: 'CI 觸發的 check 只是一次性快照；daily cron 能抓出排程執行時仍存在的偏離，降低沒有程式碼變更時長期失察的風險。不需要另外導入 GitHub App 或第三方常駐服務，沿用同一個 check 邏輯即可。',
          summary: '`governance-drift.yml` 用 daily cron 呼叫 `scripts/check-governance-drift`，它包一層 `apply-repository-settings.sh check`；可修正偏離會用 `gh issue create`／`gh issue edit` 開立或更新單一追蹤 Issue，內容附上 repository、Actions、政策標籤或 Ruleset 的實際差異。方案或組織限制造成的 DEGRADED 不讓 portable CI 永久失敗，也不會誤稱為沒有 drift；具體差異保留在 workflow log 與 warning annotation。這仍是快照檢查：若設定在兩次執行之間遭變更後又恢復，需由 GitHub audit log 或組織層事件監控追溯。下發專案透過 `enable_governance_drift_check`（預設關閉）選配同一 workflow。',
          file: '.github/workflows/governance-drift.yml＋scripts/check-governance-drift',
          code: `on:
  schedule:
    - cron: "13 4 * * *"
  workflow_dispatch:

permissions:
  contents: read
  issues: write

- run: ./scripts/check-governance-drift

# Inside the script:
./scripts/apply-repository-settings.sh check
# On drift, open/update one tracking Issue:
gh issue list --state open --json number,title \
  --jq '.[] | select(.title == "Repository governance drift detected") | .number'
gh issue create --label bug --body-file "$body_file"
gh issue edit "$issue_number" --body-file "$body_file"`
        }
      ],
      template: [
        {
          title: '先宣告語言組合，再只產生需要的工具鏈',
          goal: '可選 CI/CD-only、Python-only、TypeScript-only 或兩者；Python 另提供 latest／minimum。',
          summary: '答案寫入 `.csarc/profile.json`；驗證入口會依實際 `pyproject.toml`／`package.json` 自動核對。Python minimum 目前刻意從 3.12 起；CI 會跑所選版本的精確 `.0` 下界，以及一路到 reviewed stable 的每個 feature release 最新 patch，最後以穩定的 `verify` context 彙總。',
          file: 'copier.yml',
          code: `language:
  choices: [ci, python, typescript, python-typescript]
  default: python
python_support_mode:
  type: str
  choices: [latest, minimum]
  default: latest
python_min_version:
  choices: ["3.12", "3.13", "3.14"]
  when: minimum
use_reusable_workflow:
  type: bool
  default: false

# 3.11 is intentionally outside the declared support range.
# CI checks the selected .0 lower bound and every feature release through 3.14.`
        },
        {
          title: '可用性與真實採用成熟度分開標示',
          goal: 'profile 清單同時記錄合成驗證與 consuming repo 證據，不把可建立誤寫成已成熟。',
          file: 'profiles/catalog.yaml',
          code: `template_release_policy:
  strategy: single_semver_for_all_compositions

profiles:
  python:
    stage: alpha
    latest_reviewed_stable: "3.14"
    default_support_mode: latest
    support_modes:
      minimum:
        selectable_minimums: ["3.12", "3.13", "3.14"]
        minimum_patch_policy: first_patch
        ci_tests_exact_minimum_and_every_feature_release: true
    style_guide:
      name: Google Python Style Guide
      line_length: 80
  typescript:
    stage: alpha
    latest_reviewed_active_lts: "24"
    package_manager: pnpm
  go: {stage: future}

compositions:
  ci: {stage: beta, profiles: []}
  python: {stage: alpha, profiles: [python]}
  typescript: {stage: alpha, profiles: [typescript]}
  python_typescript: {stage: alpha, profiles: [python, typescript]}
  rust: {stage: future}

version_policy:
  stable_release_observation_days: 30
  merge_after_full_verification: automatic

compositions:
  python: {stage: alpha, profiles: [python]}
  typescript: {stage: alpha, profiles: [typescript]}
  python_typescript: {stage: alpha, profiles: [python, typescript]}`
        },
        {
          title: '既有 repo 在短分支同步審查過的模板內容',
          goal: 'Copier 保留來源與答案；先從核准 release tag 查出 40 字元 SHA，再決定實際套用內容。',
          file: '.copier-answers.yml',
          code: `gh release list --repo Innoguard-Cyber-Arch/csarc-repo-template --limit 5
gh api repos/Innoguard-Cyber-Arch/csarc-repo-template/commits/v0.1.0 --jq .sha
git switch -c chore/update-repo-template
uvx --from copier copier update --trust \
  --vcs-ref <reviewed-full-commit-sha>
./scripts/verify`
        }
      ],
      contract: [
        {
          title: '先宣告 repo 使用 CI/CD-only、Python、TypeScript 或兩者',
          goal: 'Copier 將選擇寫進 repo；偵測器只負責提醒實際檔案與宣告不一致，不擅自改設定。',
          summary: '`language_profile` 是唯一依據；`--suggest` 可依根目錄的 `pyproject.toml` 與 `package.json` 提示最可能的組合。',
          file: '.csarc/profile.json＋scripts/detect-language-profile',
          code: `{
  "language_profile": "python-typescript",
  "modules": {
    "ci_cd": true,
    "python": true,
    "typescript": true
  }
}

./scripts/detect-language-profile --suggest
./scripts/detect-language-profile`
        },
        {
          title: '各語言保留自己的品質、測試與鎖定設定',
          goal: '共用治理不等於硬湊成同一套工具；每種語言使用其主流工具，再由同一驗證入口協調。',
          summary: 'Python 使用 uv、Ruff、mypy、pytest；TypeScript 使用 pnpm、Biome、TypeScript strict、Vitest，兩邊都鎖定實際相依與完整性資料。',
          file: 'pyproject.toml／package.json＋兩種 lockfile',
          code: `# Python module
uv sync --locked
uv run ruff check .
uv run mypy
uv run pytest --cov --cov-fail-under=80

# TypeScript module
pnpm install --frozen-lockfile --ignore-scripts
pnpm exec biome ci .
pnpm exec tsc --noEmit
pnpm exec vitest run --coverage`
        },
        {
          title: '一個入口驗證、打包，也證明錯誤會被拒絕',
          goal: '本機、AI 與 GitHub 執行同一入口；正向測試證明可交付，負向測資證明門禁不是永遠綠燈。',
          summary: 'Issue 標題與 PR policy 回歸案例檢查標籤、標題、stack base、Issue，以及 main／dev／delivery routes；公版再注入錯誤 Python／TypeScript 檔。',
          file: 'scripts/verify＋scripts/test-pr-policy＋.github/workflows/ci.yml',
          code: `./scripts/test-pr-policy
./scripts/verify

on:
  pull_request:
  merge_group:
    types: [checks_requested]
  workflow_dispatch:

uses: Cyber-Arch/csarc-repo-template/
  .github/workflows/reusable-ci.yml@<full-commit-sha>
with:
  language-profile: python-typescript`
        }
      ],
      method: [
        {
          title: '四種 Issue 表單與必填內容',
          goal: '提供 Feature、Task、Bug、Documentation 四個入口；都要求問題與完成條件，並關閉空白 Issue。',
          summary: '調整表單說明、必填內容，以及是否允許沒有結構的空白 Issue。',
          file: '.github/ISSUE_TEMPLATE/{feature,task,bug,documentation}.yml＋config.yml',
          code: `Feature       -> Type: Feature; label: enhancement
Task          -> Type: Task; label: enhancement
Bug           -> Type: Bug; label: bug
Documentation -> Type: Task; label: documentation

Required fields:
  - problem
  - acceptance

# config.yml
blank_issues_enabled: false
contact_links: []`
        },
        {
          title: '標題、Label、負責人與工作層級',
          goal: '標題使用 12–80 個英文 ASCII 字元及至少三個詞；建立者自我指派，agent／CLI 使用 @me。',
          summary: '調整精確欄位限制，以及 duplicate、hotfix、promotion、Parent 與 Dependency 的使用規則。',
          file: '.github/ISSUE_TEMPLATE/*.yml＋AGENTS.md＋policies/labels.json＋docs/adr/spec-story-and-work-items.md',
          code: `Title: 12-80 ASCII characters; at least 3 words
Assignee: creator; agent/CLI uses @me

Other classifications:
  documentation -> Task + documentation label
  duplicate     -> duplicate close reason
  hotfix        -> Bug + hotfix label + fix/<Issue>-* -> main
  promotion     -> delivery tracking only

Parent     -> shared outcome still incomplete
Dependency -> actual execution order`
        },
        {
          title: '規格要不要建立追蹤工作',
          goal: '各專案在 `docs/specs/` 寫長期規格；front matter 決定同步 Task、Feature，或只保存文件。',
          summary: '決定一份 Spec 建立 Task、Feature，或只保存為長期契約。',
          file: 'docs/specs/＋scripts/spec_to_issue.py',
          code: `tracking: issue  # Sync one Task
tracking: story  # Sync one Feature parent
tracking: none   # Keep the current contract only

python scripts/spec_to_issue.py validate`
        },
        {
          title: '交付批次的說明格式',
          goal: 'Milestone 只在多張工作需要同一期限、整合或發版時建立，並使用一致的可驗收說明。',
          summary: '定義多張工作同批交付時，Milestone 要寫哪些驗收內容。',
          file: 'docs/milestone-description.md',
          code: `## Problem
## Outcome
## Acceptance criteria
- [ ] Observable result
## Plan
- #123 — Independently deliverable work
## Out of scope
## Verification
## References`
        }
      ],
      pr: [
        {
          title: '選定的保護分支要求一位核准、CODEOWNER 與必要檢查',
          goal: '新提交會讓舊核准失效，不能直接推送或 force push。',
          summary: '要求一位核准、CODEOWNER、最後推送者以外的人核准，並解完 review thread；新 commit 會撤銷舊核准。',
          file: 'policies/rulesets.json',
          code: `{
  "type": "pull_request",
  "parameters": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews_on_push": true,
    "require_code_owner_review": true,
    "require_last_push_approval": true,
    "required_review_thread_resolution": true
  }
}`
        },
        {
          title: 'PR 自動輪派一位同事審查',
          goal: 'Free private 先可靠通知同事；支援 Ruleset 時再把核准變成 merge gate。',
          summary: 'workflow 只 checkout base branch，從 REVIEWERS 設定排除作者後輪派一人；不執行 PR 分支程式碼。',
          file: '.github/CODEOWNERS＋.github/REVIEWERS＋.github/workflows/governance-comment.yml',
          code: `* {{ code_owner }}`
        },
        {
          title: 'PR 同時核對標籤、Issue 編號、stack 來源與版本標題',
          goal: '先有工作紀錄再改程式；標題仍是版本計算依據，內文可以用中文。',
          summary: 'PR 至少選一個工作標籤；分支須為 `type/123-short-slug`，base 的 open PR 鏈須回到 main／dev，且連結 Issue 必須未結案、標題合格。',
          file: '.github/workflows/pr-policy.yml＋scripts/test-pr-policy＋pull_request_template.md',
          code: `^(feat|fix|docs|refactor|test|build|ci|chore|revert)(\([a-z0-9._/-]+\))?(!)?: .+

if printf '%s' "$PR_TITLE" | LC_ALL=C \
  grep -q '[^ -~]'; then
  echo "The PR body may be written in Chinese."
  exit 1
fi

branch: feat/123-short-slug
base: feat/122-parent -> main
body: Closes #123
label: enhancement

## Purpose
## Checklist
## Supplement`
        }
      ],
      ci: [
        {
          title: 'CI 在 PR 依風險執行 fast 或 full，main 不重跑同一套測試',
          goal: '預設路徑不依賴中央 workflow；穩定 aggregate context 兼顧成本與 required checks。',
          file: '.github/workflows/ci.yml',
          code: `on:
  pull_request:
  merge_group:
    types: [checks_requested]
  workflow_dispatch:
permissions:
  actions: read
  contents: read
jobs:
  fast: # docs／fast routing
  full: # promotion／hotfix／merge queue／manual
  verify: # always-present aggregate context`
        },
        {
          title: '流程穩定後，可改用完整 SHA 呼叫 reusable workflow',
          goal: 'Copier 預設關閉；啟用時必須輸入 40 字元 commit SHA，中央 private repo 另須允許 organization 存取。',
          file: 'copier.yml＋.github/workflows/reusable-ci.yml',
          code: `use_reusable_workflow: true
workflow_ref: <40-character-commit-sha>

uses: Innoguard-Cyber-Arch/csarc-repo-template/.github/workflows/reusable-ci.yml@<40-character-commit-sha>
with:
  language-profile: python-typescript

gh api --method PUT \\
  repos/Innoguard-Cyber-Arch/csarc-repo-template/actions/permissions/access \\
  -f access_level=organization`
        },
        {
          title: 'zizmor 依 workflow 風險與週期排程執行',
          goal: 'workflow／action 變更與 promotion 由 CI 條件式掃描；每週另掃一次，普通 source／docs PR 不重複付費。',
          file: '.github/workflows/ci.yml＋.github/workflows/zizmor.yml',
          code: `name: Zizmor scheduled audit
on:
  workflow_dispatch:
  schedule:
    - cron: "43 3 * * 1"
permissions:
  contents: read
jobs:
  audit:
    steps:
      - run: uvx --from zizmor==1.29.0 zizmor . --format plain
# PR workflow changes are routed to the same audit by ci_tier.py.`
        }
      ],
      supply: [
        {
          title: '一般套件新版觀察三天，再由測試與人員決定是否合併',
          goal: '安全更新不等待；三天規則主要降低剛發布惡意版本的早期風險。',
          summary: 'Dependabot 同時管理 `uv` 與 `npm` 生態；`cooldown.default-days=3` 延後一般升版，安全更新仍立即提出。',
          file: '.github/dependabot.yml',
          code: `updates:
  - package-ecosystem: uv
    directory: /
    schedule:
      interval: weekly
    cooldown:
      default-days: 3
  - package-ecosystem: npm
    directory: /
    cooldown:
      default-days: 3`
        },
        {
          title: '兩種 lockfile 都驗內容；pnpm 本機也嚴格等三天',
          goal: '版本號只供人閱讀；Python 比對 artifact SHA-256，npm 比對 integrity hash。',
          summary: '`uv sync --locked` 與 `pnpm install --frozen-lockfile --ignore-scripts` 都會拒絕設定漂移；pnpm resolver 另阻擋發布未滿三天的直接與間接套件。',
          file: 'uv.lock＋pnpm-lock.yaml＋pnpm-workspace.yaml＋scripts/verify',
          code: `uv sync --locked
pnpm install --frozen-lockfile --ignore-scripts

minimumReleaseAge: 4320
minimumReleaseAgeStrict: true
trustPolicy: no-downgrade`
        },
        {
          title: '相依下界要能測，天花板要能指出是誰擋住',
          goal: 'Ruff／mypy 的 Python target 只管語法；uv resolver 另外證明 dev 相依範圍可安裝。這不是漏洞掃描。',
          summary: '`lowest-direct` 將直接相依降到宣告下界並重跑測試；每週排程逐一嘗試 PyPI 最新版，把 uv 的完整衝突鏈寫入 Actions summary。',
          file: 'scripts/verify＋scripts/report_dependency_ceiling.py',
          code: `uv pip compile pyproject.toml --group dev \
  --resolution lowest-direct
uv pip check --python <lower-bound-python>

# Weekly ceiling report uses an exact requirement:
uv pip compile pyproject.toml --group dev \
  --upgrade-package "<package>==<latest>"`
        },
        {
          title: 'PR、main 與每週排程掃描已公開登錄的漏洞',
          goal: 'OSV 發現漏洞就失敗，不和一般新版的三天觀察混在一起。',
          summary: '在 PR、main push 與每週一排程執行 OSV；掃到已登錄漏洞就讓檢查失敗，不套用三天等待。',
          file: '.github/workflows/osv.yml',
          code: `on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  schedule:
    - cron: "17 3 * * 1"`
        },
        {
          title: '方案感知的 CodeQL SAST，只分析實際語言',
          goal: 'Ruff／TypeScript lint 找程式品質問題，OSV 找已知相依漏洞；CodeQL 另補跨函式資料流與安全查詢，三者不互相冒充。',
          summary: 'Python／TypeScript public repo 預設產生 CodeQL；private／internal 只有確認 GitHub Code Security 授權後才 opt-in，否則明列 SAST 未涵蓋並由產品選核准替代工具。CI-only 不產生空 job。CodeQL 仍可能誤報或漏報，結果需人工 triage。',
          file: 'copier.yml＋.github/workflows/codeql.yml',
          code: `enable_codeql: true

permissions:
  contents: read
  security-events: write

matrix:
  language: ["python", "javascript-typescript"]`
        },
        {
          title: 'tag 發布時建立交付成品、SHA-256 與 CycloneDX SBOM',
          goal: 'anchore/sbom-action 以 Syft 盤點內容；來源證明依專案可見度決定預設值。',
          summary: '依 profile 打包並計算 SHA-256；先把真正成品解壓到隔離目錄，再由 Syft 產生 CycloneDX。`components` 為空就讓 workflow 失敗；tag、commit 與 workflow run metadata 連同成品附加到 GitHub Release。Copier 的 `project_visibility` 選 public 時，`enable_release_attestations` 預設開啟，`publish-evidence` job 自動取得 `id-token: write`／`attestations: write` 並執行兩次 `actions/attest`；private／internal 維持現行明確 opt-in、預設關閉。',
          file: '.github/workflows/release.yml',
          code: `- run: uv build               # Python
- run: pnpm run build && pnpm pack --pack-destination dist # TypeScript
- run: shasum -a 256 dist/* > SHA256SUMS
- name: Extract release artifacts
  run: |
    mkdir -p "\${RUNNER_TEMP}/sbom-root"
    # Extract each archive into the isolated SBOM input directory.
- uses: anchore/sbom-action@e22c389904149dbc22b58101806040fa8d37a610
  with:
    path: \${{ runner.temp }}/sbom-root
    format: cyclonedx-json
    output-file: sbom.cdx.json`
        },
        {
          title: '決定｜保留 Dependabot 與 pnpm 的原生門禁',
          goal: '讓 dependency PR 繼續觸發既有 CI/CD checks，且不要求每個導入者安裝高權限 App 或保存長效 PAT。',
          summary: '不導入 Renovate：Dependabot 使用 GitHub 原生 automation identity，現有 PR checks 可直接執行。Dependabot cooldown 管理自動升版 PR 的三天等待；pnpm minimumReleaseAge 也保護本機與 CI resolution，並非完全重複。pnpm trustPolicy、OSV、resolver 上下界檢查與 SBOM 各自保留原本職責。若未來 Dependabot 無法表達已發生的跨 repo 需求，而且已有可維護的非 GITHUB_TOKEN 身分，再另案重評。',
          file: '.github/dependabot.yml＋pnpm-workspace.yaml＋profiles/catalog.yaml',
          code: `# Native updater; no extra App or long-lived token.
.github/dependabot.yml

# Install-time observation and publisher-trust gates.
minimumReleaseAge: 4320
minimumReleaseAgeStrict: true
trustPolicy: no-downgrade`
        },
        {
          title: '回報本專案自身的漏洞，不是掃相依套件',
          goal: '掃描工具只看得到已知模式；有人主動回報才補得到掃描漏抓的問題。Issue 是公開索引的，通報流程要先把人導離開 Issue。',
          summary: '不寫死聯絡信箱或 SLA：模板不知道下游專案的實際通報管道，假造一個反而誤導回報者。專案 owner 必須在 `SECURITY.md` 填入實際管道與回應期待後，這份政策才算生效。',
          file: 'SECURITY.md',
          code: `## Reporting a vulnerability

Do not open a public GitHub Issue for a
suspected vulnerability, exploit code,
credentials, tokens, or customer data.

<!-- Project owner: replace with the actual
private reporting channel and expected
acknowledgement window. -->`
        }
      ],
      deploy: [
        {
          title: '待啟用｜GitHub App 只給 Python 排程升版用',
          goal: 'Client ID 放 Variable、private key 放 Secret；App 只建立 PR，不取得 Ruleset bypass，也不把長期憑證寫進 repo 或 .env。',
          summary: 'release-please 已改用 GITHUB_TOKEN，不再需要這個 App。目前尚未建立 App，python-version-policy.yml 的排程升版 job 會略過；啟用時只給 Contents、Pull requests 讀寫權限。',
          file: 'Repository Settings／Secrets and variables／Actions',
          code: `# Settings > Developer settings > GitHub Apps
# Install App in this repo; generate a private-key PEM.
gh variable set CSARC_VERSION_BOT_CLIENT_ID \
  --body '<client-id>'
gh secret set CSARC_VERSION_BOT_PRIVATE_KEY \
  < ./private-key.pem

# Local runtime secrets only:
.env          # ignored; never commit
.env.example  # placeholders only`
        },
        {
          title: '已配置｜每次依 GitHub capability 選 release mode',
          goal: '不要求導入者提供長效憑證或修改無權控制的組織政策；未知能力一律 fail closed。',
          summary: 'Actions PR、contents、Release、dispatch 各自輸出 allowed／blocked／unknown；四項都確認才用 release-please，否則交付能力完整才 direct release，再不行就 verification-only。',
          file: 'scripts/release_policy.py＋release-please.yml',
          code: `{
  "mode": "release-pr | direct | verification-only",
  "capabilities": {
    "actions_pull_requests": {"state": "allowed | blocked | unknown"},
    "contents": {"state": "allowed | blocked | unknown"},
    "release": {"state": "allowed | blocked | unknown"},
    "dispatch": {"state": "allowed | blocked | unknown"}
  }
}`
        },
        {
          title: '已接通｜main 後配置版本並明確啟動成品 workflow',
          goal: '版本、成品與來源沿用同一條可追溯鏈；並行或亂序 run 不能替舊 commit 配置新 tag。',
          summary: 'PR 只顯示 SemVer 意圖；direct mode 重讀 main head 與可達 tags，只在版本與 CHANGELOG 已由 PR 寫入時建立 draft release 後 dispatch。判斷 JSON 保存 30 天。',
          file: 'release_policy.py＋release-please.yml＋release.yml',
          code: `if remote_main_sha != workflow_sha:
    mode = "verification-only"
    reason = "superseded"

next_tag = bump(latest_reachable_tag, merged_commits)
create_draft_release(next_tag)
dispatch_artifacts(next_tag)`
        }
      ],
      knowledge: [
        {
          title: 'README 只保留開始使用與日常入口',
          goal: '完整設計放在 repo 內部網站，避免 README 再次膨脹。',
          summary: '公版內部網站從 repository 內來源重建成單檔 HTML，不需要另外安裝框架；它仍和程式一起走 PR。',
          file: 'README.md＋site/＋docs/index.html',
          code: `[開啟內部網站與完整決策說明](docs/index.html)`
        },
        {
          title: '來源分工、輸出維持單檔',
          goal: 'Copier 更新公版版型時，不能覆寫每個專案自行補充的內容。',
          summary: '`site/` 與 renderer 由公版更新；專案內容與 theme overrides 保留，再重建 `docs/index.html`。',
          file: 'template/site/＋template/docs/＋copier.yml',
          code: `_skip_if_exists:
  - docs/site-content.js
  - docs/site-theme.css`
        }
      ],
      rollout: [
        {
          title: '可用組合依真實採用證據分級',
          goal: '基本、未來與可選不是口號，而是對可用能力的承諾。',
          summary: '共用治理與 CI/CD-only 已有真實 pilot，維持 `beta`；Python、TypeScript 與混合組合可建立但尚無 consuming repo，維持 `alpha`；Go、Rust 保持 `future`。',
          file: 'profiles/catalog.yaml',
          code: `ci: {stage: beta, profiles: []}
python: {stage: alpha}
typescript: {stage: alpha}
go: {stage: future}
rust: {stage: future}

python_typescript: {stage: alpha}`
        },
        {
          title: 'GitHub 設定隨模板產生，再依遠端方案分層套用',
          goal: '設定檔可以先審查；實際 repo 建立後才查方案與 API，不能使用的能力會明確略過。',
          summary: 'Free private 在 repo 保存 ACTIVE Ruleset policy；check 仍比對 repository、Actions 與政策標籤，再將 Ruleset 限制標示 DEGRADED，並在 PR、workflow log 與 annotation 留下具體紀錄。public／Pro／Team／Enterprise 以有效規則作為門禁，可修正設定對不上政策時 fail-closed。GitHub App 仍是另一項獨立條件。',
          file: 'policies/＋scripts/apply-repository-settings.sh',
          code: `policies/repository.json
policies/actions.json
policies/labels.json
policies/rulesets.json
scripts/apply-repository-settings.sh`
        },
        {
          title: '每次修改都測新案、既有案導入與後續更新',
          goal: '可導入的條件是三條生命週期都通過，不是只看檔案存在。',
          summary: '測試會真的執行 CLI init、adopt dry-run／報告／apply、update check／dry-run／apply 與衝突 fail-closed；adopt 報告會以同一份分析輸出 Markdown 與一頁 PDF，且不修改 target repo。CLI 內部仍以 Copier 產生與 smart update。root-only 測試資產若混入生成 repo 也會失敗。',
          file: 'src/csarc_cli/＋tests/test_cli.py＋scripts/verify-template.sh',
          code: `csarc init ./my-project
csarc adopt . --dry-run --report-dir ../csarc-adoption-report
csarc update --check --json
csarc update`
        }
      ],
      'template-release': [
        {
          title: 'Copier 只詢問會改變骨架或驗證行為的選項',
          goal: '不提供關閉型別或秘密掃描的開關；嚴格門檻是公版契約。',
          summary: '語言與分支模式都在建立時明確選擇；delivery 模式把 CI 當整合層，main／dev 仍保留給適合的 repo。`_skip_if_exists` 保護 src、tests、spec 不被更新覆寫。',
          file: 'copier.yml',
          code: `language: python
branch_strategy: delivery  # delivery | main | dev
python_support_mode: latest  # latest | minimum
python_min_version: "3.12"  # Used only in minimum mode
coverage_mode: global  # global | diff
coverage_threshold: 80
enable_precommit: false
project_visibility: private  # public defaults CodeQL on
enable_codeql: false         # private/internal require GitHub Code Security
use_reusable_workflow: false

_skip_if_exists:
  - "src/**"
  - "tests/**"
  - "docs/specs/**"`
        },
        {
          title: '公版 root 鎖工具、跑 OSV，並檢查共用設定沒有漂移',
          goal: '中央模板不能要求下游做到自己做不到的事；PR 說明模板是唯一刻意差異。',
          summary: 'root 以鎖定環境跑 Ruff、mypy、完整 Git 歷史、目前工作樹與 Actions 掃描；無 Git 歷史的新案仍掃工作樹，腳本也逐組 diff root／template 的共用政策。',
          file: 'pyproject.toml＋uv.lock＋scripts/verify-template.sh',
          code: `uv sync --locked
uv lock --check
uv run ruff format --check
uv run ruff check
uv run mypy
./scripts/scan-secrets
# Large repositories may explicitly narrow history:
./scripts/scan-secrets --log-opts='--since=2026-01-01'
uv run zizmor . --format plain

# Paired root/template policies are diff-checked.`
        },
        {
          title: 'Python 新功能版本滿三十天後，自動建立升版 PR',
          goal: '不靠人記得升級，也不繞過 Ruff、mypy、CI、人工審查或模板更新測試。',
          summary: '排程讀取 Python 官方發布日期；專用 GitHub App 建立帶 enhancement label 的 PR，通過全部門禁與人工審查後再由維護者合併。',
          file: 'python-version-policy.yml＋scripts/update_python_version.py',
          code: `version_policy:
  stable_release_observation_days: 30
  update_method: scheduled_verified_pull_request
  merge_after_full_verification: human

# Required repository settings
CSARC_VERSION_BOT_CLIENT_ID
CSARC_VERSION_BOT_PRIVATE_KEY`
        },
        {
          title: '四種 profile 與 Copier 更新都要真的執行',
          goal: 'beta 必須同時有合成生命週期與真實 consuming repo 證據。',
          summary: '四種組合都通過合成建立／更新；目前只有 CI/CD-only 完成真實產品導入、客製化保留與線上 update。',
          file: 'scripts/verify-template.sh＋profiles/catalog.yaml',
          code: `./scripts/verify-template.sh

# Covers global coverage, diff coverage, optional features,
# reusable workflow and copier update.

ci: {stage: beta, profiles: []}
python: {stage: alpha}
typescript: {stage: alpha}
go: {stage: future}
rust: {stage: future}
python_typescript: {stage: alpha}`
        }
      ]
    });

    const setupExamples = {
      new: {
        title: '建立新 repo',
        goal: 'CLI 會選取核准 release、解析完整 commit SHA、顯示計畫，確認後才以 Copier 建立與驗證。',
        location: 'Terminal',
        code: `uvx --from csarc-repo-cli csarc init ./my-project

# CI or an explicitly authorized agent:
uvx --from csarc-repo-cli csarc init ./my-project \\
  --yes --non-interactive`
      },
      existing: {
        title: '把公版導入既有 repo',
        goal: '先用 --dry-run 在 repo 外產生短版 Markdown 與一頁 PDF，預覽新增、覆寫、保留、人工合併與無法判定項目；必須是乾淨 Git working tree，預設保留產品內容。報告只描述已知風險，不保證沒有語意或執行期衝突。',
        location: '既有 repo 根目錄',
        code: `git switch -c chore/<issue-number>-adopt-csarc-template
uvx --from csarc-repo-cli csarc adopt . --dry-run \\
  --report-dir ../csarc-adoption-report
uvx --from csarc-repo-cli csarc adopt .`
      },
      update: {
        title: '更新已使用公版的 repo',
        goal: 'CLI 讀取 .copier-answers.yml，解析核准 release，以 Copier smart update 顯示新版差異；衝突時保留差異並 fail closed。',
        location: '專案 repo 根目錄',
        code: `git switch -c chore/<issue-number>-update-repo-template
uvx --from csarc-repo-cli csarc update --check --json
uvx --from csarc-repo-cli csarc update`
      },
      mac: {
        title: 'macOS 本機需求',
        goal: '共同安裝 Git、GitHub CLI、uv；TypeScript／混合案再使用 Node 與 pnpm。只有 GitHub 連線操作需要登入。',
        location: 'Terminal',
        code: `brew install git gh uv node pnpm

# Only for repository settings and GitHub end-to-end tests.
gh auth login -h github.com
gh auth status`
      },
      windows: {
        title: 'Windows 本機需求',
        goal: '採用 WSL2（Ubuntu）並在 WSL 裡操作 repo；TypeScript／混合案再安裝 Node 24 與 pnpm 11。',
        location: 'PowerShell（管理員）→ Ubuntu',
        code: `# PowerShell (Administrator)
wsl --install -d Ubuntu

# Ubuntu in WSL2
sudo apt update
sudo apt install -y git gh curl ca-certificates bash coreutils tar gawk libdigest-sha-perl
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pnpm@11.22.0

# Only for repository settings and GitHub end-to-end tests.
gh auth login -h github.com
gh auth status`
      }
    };

    const capabilitySlide = document.querySelector('.capability-slide');
    if (!capabilitySlide) return;

    function closeConfigOverlays() {
      document.querySelectorAll('.config-overlay').forEach(overlay => {
        overlay.hidden = true;
        overlay.removeAttribute('data-item-index');
      });
      document.querySelectorAll('.config-trigger[aria-expanded="true"], .setup-trigger[aria-expanded="true"], .term-trigger[aria-expanded="true"]').forEach(trigger => {
        trigger.setAttribute('aria-expanded', 'false');
      });
    }

    function closePackageDisclosures(except = null) {
      document.querySelectorAll('.package-disclosure[open]').forEach(detail => {
        if (detail !== except) detail.open = false;
      });
    }

    function closeBridgeDetails(except = null) {
      document.querySelectorAll('.bridge-detail[open]').forEach(detail => {
        if (detail !== except) detail.open = false;
      });
    }

    document.querySelectorAll('.package-disclosure').forEach(detail => {
      detail.addEventListener('toggle', () => {
        if (detail.open) closePackageDisclosures(detail);
      });
    });

    const setupOverlay = document.createElement('aside');
    setupOverlay.id = 'setup-overlay';
    setupOverlay.className = 'config-overlay';
    setupOverlay.hidden = true;
    setupOverlay.setAttribute('role', 'region');
    setupOverlay.setAttribute('aria-label', '導入與安裝指令');
    setupOverlay.innerHTML = `<div class="config-overlay-card"><button class="config-overlay-close" type="button" aria-label="關閉指令">×</button><h3></h3><p class="config-overlay-goal"></p><p class="config-overlay-path">執行位置：<code></code></p><pre class="code"></pre></div>`;
    capabilitySlide.append(setupOverlay);
    capabilitySlide.querySelectorAll('.setup-trigger').forEach(trigger => {
      trigger.setAttribute('aria-controls', setupOverlay.id);
      trigger.addEventListener('click', () => {
        const key = trigger.dataset.setup;
        const setting = setupExamples[key];
        const isSameOpen = !setupOverlay.hidden && setupOverlay.dataset.itemIndex === key;
        closeConfigOverlays();
        if (!setting || isSameOpen) return;
        setupOverlay.querySelector('h3').textContent = setting.title;
        setupOverlay.querySelector('.config-overlay-goal').textContent = setting.goal;
        setupOverlay.querySelector('.config-overlay-path code').textContent = setting.location;
        setupOverlay.querySelector('pre').textContent = setting.code;
        setupOverlay.dataset.itemIndex = key;
        setupOverlay.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
      });
    });
    setupOverlay.querySelector('.config-overlay-close').addEventListener('click', closeConfigOverlays);

    document.querySelectorAll('.term-trigger').forEach(trigger => {
      const overlay = document.querySelector(`#${trigger.getAttribute('aria-controls')}`);
      if (!overlay) return;
      trigger.addEventListener('click', () => {
        const isOpen = !overlay.hidden;
        closeConfigOverlays();
        if (isOpen) return;
        overlay.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
      });
      overlay.querySelector('.config-overlay-close').addEventListener('click', closeConfigOverlays);
    });

    document.querySelectorAll('.decision-slide').forEach(slide => {
      const track = slide.dataset.track;
      const settings = configExamples[track];
      const guidance = slide.querySelector('.config-guidance');
      if (!settings || !guidance) return;

      const direct = guidance.dataset.configDirect === 'true';
      const heading = document.createElement('strong');
      heading.textContent = direct ? '模板功能與客製化' : '需要設定的項目';
      const intro = document.createElement('p');
      intro.textContent = '設定內容與對應檔案如下。';
      const actions = document.createElement('div');
      actions.className = 'config-actions';

      if (direct) {
        settings.forEach(setting => {
          const item = document.createElement('details');
          item.className = 'config-inline-detail';
          const itemSummary = document.createElement('summary');
          const title = document.createElement('span');
          title.className = 'config-trigger-title';
          title.textContent = setting.title;
          const description = document.createElement('span');
          description.className = 'config-trigger-summary';
          description.textContent = (setting.summary || setting.goal).replaceAll('`', '');
          itemSummary.append(title, description);

          const body = document.createElement('div');
          body.className = 'config-inline-body';
          const goal = document.createElement('p');
          goal.textContent = setting.goal;
          const path = document.createElement('p');
          path.className = 'config-inline-path';
          path.append('設定檔：');
          const code = document.createElement('code');
          code.textContent = setting.file;
          path.append(code);
          const example = document.createElement('pre');
          example.className = 'code';
          example.textContent = setting.code;
          body.append(goal, path, example);
          item.append(itemSummary, body);
          actions.append(item);
        });

        const disclosure = document.createElement('details');
        disclosure.className = 'config-guidance-fold';
        disclosure.open = true;
        const summary = document.createElement('summary');
        summary.textContent = heading.textContent;
        disclosure.append(summary, actions);
        guidance.replaceChildren(disclosure);
        return;
      }

      const overlay = document.createElement('aside');
      overlay.id = `config-overlay-${track}`;
      overlay.className = 'config-overlay';
      overlay.hidden = true;
      overlay.setAttribute('role', 'region');
      overlay.setAttribute('aria-label', '設定實作覆蓋卡');
      overlay.innerHTML = `<div class="config-overlay-card"><button class="config-overlay-close" type="button" aria-label="關閉設定實作">×</button><h3></h3><p class="config-overlay-goal"></p><p class="config-overlay-path">設定檔：<code></code></p><pre class="code"></pre></div>`;

      settings.forEach((setting, index) => {
        const trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'config-trigger';
        trigger.setAttribute('aria-expanded', 'false');
        trigger.setAttribute('aria-controls', overlay.id);

        const title = document.createElement('span');
        title.className = 'config-trigger-title';
        title.textContent = setting.title;
        const file = document.createElement('span');
        file.className = 'config-trigger-file';
        file.textContent = setting.file;
        const summary = document.createElement('span');
        summary.className = 'config-trigger-summary';
        summary.textContent = (setting.summary || setting.goal).replaceAll('`', '');
        trigger.append(title, file, summary);

        trigger.addEventListener('click', () => {
          const isSameOpen = !overlay.hidden && overlay.dataset.itemIndex === String(index);
          closeConfigOverlays();
          if (isSameOpen) return;
          overlay.querySelector('h3').textContent = setting.title;
          overlay.querySelector('.config-overlay-goal').textContent = setting.goal;
          overlay.querySelector('.config-overlay-path code').textContent = setting.file;
          overlay.querySelector('pre').textContent = setting.code;
          overlay.dataset.itemIndex = String(index);
          overlay.hidden = false;
          trigger.setAttribute('aria-expanded', 'true');
        });
        actions.append(trigger);
      });

      overlay.querySelector('.config-overlay-close').addEventListener('click', closeConfigOverlays);
      guidance.replaceChildren(heading, intro, actions);
      slide.append(overlay);
    });

    addEventListener('click', event => {
      if (!(event.target instanceof Element)) return;
      if (!event.target.closest('.package-disclosure')) closePackageDisclosures();
      if (!event.target.closest('.bridge-detail')) closeBridgeDetails();
      if (event.target.closest('.config-overlay-card, .config-trigger, .setup-trigger, .term-trigger')) return;
      closeConfigOverlays();
    });
})();
