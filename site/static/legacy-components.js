(() => {
    const configExamples = {};

    Object.assign(configExamples, {
      agents: [
        {
          title: '固定基線｜人與 AI 各看一個清楚入口',
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
          title: '可調整｜產品啟動與額外驗證命令',
          goal: '讓 agent 知道怎麼啟動產品，以及共通驗證完成後還要執行哪一支專案檢查。',
          summary: '`project_run_command` 必填；既有 repo 可選填一支安全的 repository-relative 驗證程式。',
          file: '.csarc/config.yml＋AGENTS.md',
          code: `project_run_command: uv run my-product
project_verification_hook: scripts/verify-product`
        },
        {
          title: '固定基線｜平行可寫工作各自隔離',
          goal: '一項可寫工作對應一個 branch 與 worktree，只平行處理互不依賴的範圍。',
          summary: '唯讀工作不需另開 worktree；清理程式只回收已合併且乾淨的目錄。',
          file: 'AGENTS.md＋scripts/cleanup-worktrees＋scripts/test-worktree-cleanup',
          code: `git worktree add ../task-388 -b feat/388-align-ai-guidelines
./scripts/test-worktree-cleanup
./scripts/cleanup-worktrees`
        },
        {
          title: '固定基線｜規範、驗證與治理各有唯一責任',
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
          summary: '所有方案都先用 repository teams API 驗證 PR 內設定的 team 與 write access；Free private 的 REVIEWERS 名單仍保留，但目前由人工指定 reviewer，自動輪派 Action 尚未恢復。Ruleset 只保留 STAGED／MISSING 與 DEGRADED 紀錄。',
          file: 'policies/rulesets.json＋.github/CODEOWNERS＋.github/REVIEWERS',
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
          title: '治理漂移檢查保留本機入口，排程尚未恢復',
          goal: '先用同一支腳本檢查設定差異；需要持續監測時，再逐條恢復觸發、權限、timeout 與 Issue 通知。',
          summary: '`scripts/check-governance-drift` 會呼叫 `apply-repository-settings.sh check`，可在可信任的本機 checkout 執行。原本的 `governance-drift.yml` 位於 `archive/ci-cd/`，目前不會每日執行或自動開立追蹤 Issue。',
          file: 'scripts/check-governance-drift＋archive/ci-cd/2026-08-27/root-workflows/governance-drift.yml',
          code: `./scripts/check-governance-drift

# The scheduled workflow is archived and does not run.`
        }
      ],
      template: [
        {
          title: '獨立勾選語言，只產生需要的工具鏈',
          goal: 'Python、Rust、TypeScript 都是獨立模組；全不選時只產生共通 CI/CD 基線。',
          summary: '答案寫入 `.csarc/config.yml`；它同時是 repo 的公版設定與 Copier 更新依據，不再另存 profile JSON。',
          file: 'copier.yml',
          code: `languages:
  multiselect: true
  choices: [python, rust, typescript]
  default: [python]
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
          title: '共用生命週期與語言模組分開驗收',
          goal: '真實 repo 證明共用導入與線上邊界；語言模組以可重現的生命週期與原生工具驗收。',
          file: 'profiles/catalog.yaml',
          code: `template_version_policy:
  strategy: single_semver_for_all_compositions
  materialization: manual_reviewed_pull_request
  release_automation: blocked_pending_issue_369

profiles:
  python:
    stage: beta
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
  rust:
    stage: beta
    latest_reviewed_stable: "1.98.0"
    package_manager: cargo
  typescript:
    stage: beta
    latest_reviewed_active_lts: "24"
    package_manager: pnpm
  go: {stage: future}

compositions:
  ci: {stage: beta, profiles: []}
  language_modules:
    stage: beta
    selectable_profiles: [python, rust, typescript]
    selection: any_subset

version_policy:
  stable_release_observation_days: 30
  merge_after_full_verification: automatic

verification: selected_modules_plus_shared_checks_once`
        },
        {
          title: '既有 repo 在短分支同步審查過的模板內容',
          goal: 'Copier 保留來源與答案；先從核准 release tag 查出 40 字元 SHA，再決定實際套用內容。',
          file: '.csarc/config.yml',
          code: `gh release list --repo Innoguard-Cyber-Arch/csarc-repo-template --limit 5
gh api repos/Innoguard-Cyber-Arch/csarc-repo-template/commits/v0.1.0 --jq .sha
git switch -c chore/update-repo-template
uvx --from copier copier update --trust \
  --vcs-ref <reviewed-full-commit-sha>
./scripts/verify`
        }
      ],
      languages: [
        {
          title: '可調整｜選用語言與 Python 支援範圍',
          goal: 'Copier 將選擇寫進 repo；偵測器只負責提醒實際檔案與宣告不一致，不擅自改設定。',
          summary: '`languages` 決定要產生哪些語言模組；Python 另可選最新穩定版或最低支援版本。',
          file: '.csarc/config.yml＋scripts/detect-language-profile',
          code: `languages:
- python
- rust
- typescript
python_support_mode: latest  # latest | minimum
python_min_version: "3.12"  # minimum only
./scripts/detect-language-profile --suggest
./scripts/detect-language-profile`
        },
        {
          title: '固定基線｜各語言使用原生工具',
          goal: '共用治理不等於硬湊成同一套工具；每種語言使用其主流工具，再由同一驗證入口協調。',
          summary: 'Ruff／Biome／rustfmt 負責格式，Ruff／Biome／Clippy 負責 lint；ty／TypeScript 檢查型別，各語言再使用自己的測試與打包工具。',
          file: '各語言 manifest＋lockfile',
          code: `# Python module
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest --cov --cov-fail-under=80

# Rust module
cargo fmt --all -- --check
cargo clippy --locked --all-targets --all-features -- -D warnings
cargo test --locked --all-features
cargo build --release --locked
cargo package --locked --allow-dirty

# TypeScript module
pnpm install --frozen-lockfile --ignore-scripts
pnpm exec biome ci .
pnpm exec tsc --noEmit
pnpm exec vitest run --coverage`
        },
        {
          title: '固定基線｜一個入口驗證與打包',
          goal: '本機、AI 與 GitHub 執行同一入口；各語言只持有自己的檢查。',
          summary: 'fast 選必要子集，full 是其超集合，不為不同 PR 階段複製測試。',
          file: 'scripts/verify-fast＋scripts/verify＋.github/workflows/ci.yml',
          code: `./scripts/verify-fast
./scripts/verify`
        }
      ],
      method: [
        {
          title: '固定基線｜四種 Issue 表單與必填內容',
          goal: '提供 Feature、Task、Bug、Documentation 四個入口；都要求問題與完成條件，並關閉空白 Issue。',
          summary: '問題與完成條件必填，空白 Issue 關閉；這些是公版工作契約，不提供停用開關。',
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
          title: '固定基線｜標題、Label、負責人與工作層級',
          goal: '標題使用 12–80 個英文 ASCII 字元及至少三個詞；建立者自我指派，agent／CLI 使用 @me。',
          summary: '標題、分類與工作關係採同一套規則；組織若要改契約，應由公版政策變更而不是各 repo 自行關閉。',
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
          title: '專案選擇｜規格要不要建立追蹤工作',
          goal: '各專案在 `docs/specs/` 寫長期規格；front matter 決定同步 Task、Feature，或只保存文件。',
          summary: '現階段沿用單一輕量格式，不另導入 Spec Kit；需求真的需要完整 spec／plan／tasks 流程時再評估。',
          file: 'docs/specs/＋scripts/spec_to_issue.py',
          code: `tracking: issue  # Sync one Task
tracking: story  # Sync one Feature parent
tracking: none   # Keep the current contract only

python scripts/spec_to_issue.py validate`
        },
        {
          title: '固定基線｜里程碑的啟動門檻',
          goal: '每個里程碑使用一張生命週期追蹤 Issue，集中保存同意與反駁。',
          summary: '至少一位非提案者同意，且沒有尚未解決的反駁，工作才開始；里程碑結案方式由「版本／交付」定義。',
          file: 'docs/milestone-description.md',
          code: `## Problem
## Outcome
## Acceptance criteria
- [ ] Observable result
## Plan
- #123 — Independently deliverable work
## Kickoff decision
- Approval: one non-proposer agreement
- Objections: none unresolved
## Out of scope
## Verification
## References`
        }
      ],
      pr: [
        {
          title: '固定基線｜PR 格式與工作關聯',
          goal: '一張工作 PR 完成一張 Issue；里程碑工作由 Action 核對後關單，直接進 main 則沿用 GitHub 原生關單。',
          summary: '標題與目的分支符合規則；分類 Label 與里程碑必須和 Issue 相同，PR 作者必須列為 Assignee，內文使用 Closes #N 連回同號未結案 Issue。',
          file: 'pull_request_template.md＋.github/workflows/pr-policy.yml＋.github/workflows/work-item-closure.yml＋scripts/pr_lifecycle.py',
          code: `title: feat(scope): English summary
branch: feat/123-short-slug
body: Closes #123
label: enhancement
assignee: PR author
milestone: same as Issue #123`
        },
        {
          title: '可調整｜工作 PR 的分支模型',
          goal: '里程碑工作先進 dev/m*，一般獨立工作直接進 main；main 更新後以 PR 同步，不直接改寫開發分支。',
          summary: '`branch_strategy` 可選 delivery 或 main；validator 依所選模型檢查目的分支與同步鏈。',
          file: 'copier.yml＋.csarc/config.yml＋scripts/delivery_sync.py',
          code: `branch_strategy: delivery  # delivery | main

work:    type/123-short-slug -> dev/m8-*
release: dev/m8-* -> main
sync:    sync/main-to-m8-*-<sha> -> dev/m8-*`
        },
        {
          title: '可調整｜程式碼擁有者與審查人選',
          goal: '公版產生 CODEOWNERS 與可輪派名單；誰可以合併及例外仍只由規則治理定義。',
          summary: '`code_owner` 指定 GitHub team；`reviewers` 是可輪派的帳號名單。平台無法強制時仍需人工指定與確認。',
          file: '.csarc/config.yml＋.github/CODEOWNERS＋.github/REVIEWERS',
          code: `code_owner: "@organization/team"
reviewers: "@alice,@bob"

desired reviews: 1
require CODEOWNER: true
dismiss stale reviews: true
resolve review threads: true

# Run before relying on enforcement
./scripts/apply-repository-settings.sh check`
        }
      ],
      contract: [
        {
          title: '固定基線｜CI 依風險執行 fast 或 full',
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
          title: '可調整｜覆蓋率與本機便利功能',
          goal: '組織可以調整共用覆蓋率政策與 pre-commit，不需要修改每支驗證腳本。',
          summary: '覆蓋率可選全專案或只看本次差異，門檻預設 80%；pre-commit 預設關閉，CI 仍是必要證據。',
          file: '.csarc/config.yml',
          code: `coverage_mode: global  # global | diff
coverage_threshold: 80  # 1..100
enable_precommit: false`
        },
        {
          title: '專案選配｜改用固定版本的 reusable workflow',
          goal: 'Copier 預設關閉；啟用時必須輸入 40 字元 commit SHA，中央 private repo 另須允許 organization 存取。',
          file: 'copier.yml＋.github/workflows/reusable-ci.yml',
          code: `use_reusable_workflow: true
workflow_ref: <40-character-commit-sha>

uses: Innoguard-Cyber-Arch/csarc-repo-template/.github/workflows/reusable-ci.yml@<40-character-commit-sha>
with:
  language-profile: python

gh api --method PUT \\
  repos/Innoguard-Cyber-Arch/csarc-repo-template/actions/permissions/access \\
  -f access_level=organization`
        },
        {
          title: '固定基線｜zizmor 只在相關變更與排程執行',
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
# PR workflow changes are routed to the same audit by the CI tier rules.`
        }
      ],
      supply: [
        {
          title: '固定基線｜依鎖檔重裝，TypeScript 另等三天',
          goal: '先證明已提交的套件集合可以重現，不把「安裝成功」誤當成「沒有漏洞」。',
          summary: 'Python、Rust、TypeScript 都依 lockfile 重裝；pnpm 另拒絕發布未滿三天或 publisher trust 降級的版本。',
          file: 'template/scripts/verify-fast.jinja＋template/scripts/verify.jinja＋template/pnpm-workspace.yaml',
          code: `uv sync --locked
cargo test --locked
pnpm install --frozen-lockfile --ignore-scripts

minimumReleaseAge: 4320
minimumReleaseAgeStrict: true
trustPolicy: no-downgrade`
        },
        {
          title: '固定基線｜Dependabot 提出一般與安全更新 PR',
          goal: '一般新版先觀察三天；已知安全修補不等待，且更新 PR 繼續走相同 CI。',
          summary: '使用 GitHub 原生 automation identity，不要求每個 repo 安裝高權限 App；一般更新與安全更新 PR 都走相同審查與 CI。',
          file: '.github/dependabot.yml＋template/.github/dependabot.yml.jinja',
          code: `cooldown:
  default-days: 3

# Security updates are not delayed by the cooldown.`
        },
        {
          title: '固定基線｜OSV 共用本機、PR 與每週掃描',
          goal: '已公開漏洞立即處理，不和一般新版的三天觀察混在一起。',
          summary: '依賴檔變更與交付候選執行同一支本機程式；每週排程只補沒有 PR 的期間。workflow 不自行重寫掃描條件。',
          file: 'scripts/verify-dependencies＋.github/workflows/ci.yml＋.github/workflows/osv.yml',
          code: `Issue PR with dependency changes -> verify-dependencies
Delivery PR -> verify-dependencies
Weekly schedule -> verify-dependencies`
        },
        {
          title: '專案選配｜依 GitHub 方案啟用 CodeQL',
          goal: '需要跨函式資料流分析時啟用 SAST；不能把 lint 或套件漏洞掃描誤當成 CodeQL。',
          summary: 'public repo 預設開啟；private／internal repo 先確認 GitHub Code Security 授權，未選 Python 或 TypeScript 時不產生。',
          file: '.csarc/config.yml＋.github/workflows/codeql.yml',
          code: `project_visibility: public
enable_codeql: true`
        },
        {
          title: '條件式契約｜真正成品的 SPDX SBOM 與 checksum',
          goal: '清冊必須來自精確 tag 的真正成品，不能只從原始碼猜測。',
          summary: '成品存在時可用 Syft 產生 SPDX 2.3 SBOM；repo 程式驗證 root package、dependency graph、checksum、來源與 provenance。目前沒有 active publisher，因此不宣稱已產生成品證據。',
          file: 'scripts/release_assets.py＋tests/test_release_assets.py',
          code: `syft <extracted-artifacts> -o spdx-json=sbom.spdx.json
python scripts/release_assets.py build ...
python scripts/release_assets.py verify ...`
        },
        {
          title: '可調整｜回報本專案自身的漏洞',
          goal: '掃描工具只看得到已知模式；有人主動回報才補得到掃描漏抓的問題。Issue 是公開索引的，通報流程要先把人導離開 Issue。',
          summary: '不寫死聯絡信箱或 SLA：模板不知道下游專案的實際通報管道，假造一個反而誤導回報者。專案 owner 必須在 `SECURITY.md` 填入實際管道與回應期待後，這份政策才算生效。',
          file: '.csarc/config.yml＋SECURITY.md',
          code: `security_reporting_channel: >-
  Use the approved private reporting channel.

## Reporting a vulnerability

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
          title: '人工邊界｜交付與里程碑結案分開',
          goal: '合併到 main 不等於發版；里程碑完成仍須由 owner 確認 outcome 與必要證據。',
          summary: '#400 完成前，正常結案與提前終止都維持人工；不由 release workflow 推測完成。',
          file: 'docs/milestone-description.md＋scripts/sync_milestone_state.py＋.github/workflows/milestone-lifecycle.yml',
          code: `normal completion:
  delivery evidence: recorded
  unfinished Issues: none
  lifecycle Issue: completed

early termination:
  reason: recorded
  unfinished Issues: moved or not planned
  lifecycle Issue: not planned`
        },
        {
          title: '目前狀態｜發版 automation 未啟用',
          goal: '文件只宣稱目前 repository 能由 active file 與 current run 證明的能力。',
          summary: 'Release Please、promotion、成品發布與 consumption workflows 都在 archive；#369 決定唯一 owner 前維持 manual／conditional。',
          file: 'docs/adr/release-security-and-dependencies.md',
          code: `version intent: active
version + changelog: manual
tag + GitHub Release: blocked (#369)
artifact evidence: conditional
deployment: not applicable`
        },
        {
          title: '保留契約｜成品與消費驗證可在本機重跑',
          goal: '保留 exact-tag、checksum、SBOM、provenance 與 consumption 的 fail-closed 邊界，不假裝已有 publisher。',
          summary: 'scripts／tests 是 conditional contract；真正 workflow 必須另行定義 owner、trigger、最小權限、timeout、concurrency、成本與成功／受控失敗 evidence。',
          file: 'scripts/release_assets.py＋scripts/verify_release_consumption.py',
          code: `build exact-tag artifacts
verify SHA-256 + SPDX 2.3 + source identity
publish only after an owner is approved
consumer verifies its own policy`
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
          title: '語言模組依可重現證據分級',
          goal: '基本、未來與可選不是口號，而是對可用能力的承諾。',
          summary: '真實 consuming repo 已證明共用生命週期；Python、Rust 與 TypeScript 各自通過建立、導入、更新與原生工具鏈，列為 `beta`；Go 保持 `future`。',
          file: 'profiles/catalog.yaml',
          code: `ci: {stage: beta, profiles: []}
python: {stage: beta}
rust: {stage: beta}
typescript: {stage: beta}
go: {stage: future}`
        },
        {
          title: 'GitHub 設定隨模板產生，再依遠端方案分層套用',
          goal: '設定檔可以先審查；實際 repo 建立後才查方案與 API，不能使用的能力會明確略過。',
          summary: 'Free private 在 repo 保存 ACTIVE Ruleset policy；check 仍比對 repository、Actions 與政策標籤，再將 Ruleset 限制標示 DEGRADED，並在 PR、workflow log 與 annotation 留下具體紀錄。public／Pro／Team／Enterprise 以有效規則作為門禁，可修正設定對不上政策時 fail-closed。',
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
        },
        {
          title: 'Fleet 盤點與平台門檻',
          goal: '目前只有一個真實 consuming repo，先累積採用與漂移證據，不預先部署中央平台。',
          summary: '10 個活躍 consuming repo，或至少 3 個且反覆發生 owner／服務查找問題時才評估 catalog；至少 5 個且出現跨 repo 漂移或人工修正成本時才評估中央 policy enforcement。',
          file: 'profiles/catalog.yaml＋governance-drift runs',
          code: `Catalog review:
  - 10 active consuming repositories; or
  - 3+ repositories and repeated owner/service lookup delays

Policy review:
  - 5+ consuming repositories; and
  - repeated cross-repository drift or measurable manual repair cost`
        }
      ],
      'template-release': [
        {
          title: 'Copier 只詢問會改變骨架或驗證行為的選項',
          goal: '不提供關閉型別或秘密掃描的開關；嚴格門檻是公版契約。',
          summary: '語言與分支模式都在建立時明確選擇；main 是永久整合線，delivery 模式只為 Milestone 建立短期 dev/m*。`_skip_if_exists` 保護 src、tests、spec 不被更新覆寫。',
          file: 'copier.yml',
          code: `languages: [python]
branch_strategy: delivery  # delivery | main
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
          summary: 'root 以鎖定環境跑 Ruff、ty、完整 Git 歷史、目前工作樹與 Actions 掃描；無 Git 歷史的新案仍掃工作樹，腳本也逐組 diff root／template 的共用政策。',
          file: 'pyproject.toml＋uv.lock＋scripts/verify-template.sh',
          code: `uv sync --locked
uv lock --check
uv run ruff format --check
uv run ruff check
uv run ty check
./scripts/scan-secrets
# Large repositories may explicitly narrow history:
./scripts/scan-secrets --log-opts='--since=2026-01-01'
uv run zizmor . --format plain

# Paired root/template policies are diff-checked.`
        },
        {
          title: 'Python 新功能版本觀察三十天後再人工升級',
          goal: '保留穩定版觀察期與完整驗證，不假裝已有排程或 GitHub App。',
          summary: 'profiles/catalog.yaml 保存三十天觀察規則；維護者以一般受審查 PR 更新支援版本。舊 python-version-policy workflow 留在 archive，沒有 active bot identity。',
          file: 'profiles/catalog.yaml＋scripts/update_python_version.py',
          code: `version_policy:
  stable_release_observation_days: 30
  update_method: manual_reviewed_pull_request
  merge_after_full_verification: manual`
        },
        {
          title: '共通基線與每個語言模組都要真的執行',
          goal: '每個 beta 語言都必須真的建立、導入、更新並執行自己的原生工具。',
          summary: '共通生命週期由真實 repo 證明；每個語言模組則用可重現測試驗收，同時選取時合併執行，不另外維護組合測試。',
          file: 'scripts/verify-template.sh＋profiles/catalog.yaml',
          code: `./scripts/verify-template.sh

# Covers global coverage, diff coverage, optional features,
# reusable workflow and copier update.

ci: {stage: beta, profiles: []}
python: {stage: beta}
typescript: {stage: beta}
go: {stage: future}
rust: {stage: beta}`
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
        goal: 'CLI 讀取 .csarc/config.yml，解析核准 release，以 Copier smart update 顯示新版差異；衝突時保留差異並 fail closed。',
        location: '專案 repo 根目錄',
        code: `git switch -c chore/<issue-number>-update-repo-template
uvx --from csarc-repo-cli csarc update --check --json
uvx --from csarc-repo-cli csarc update`
      },
      mac: {
        title: 'macOS 本機需求',
        goal: '共同安裝 Git、GitHub CLI、uv；選 TypeScript 再使用 Node 與 pnpm，選 Rust 再使用 rustup 與 Cargo。只有 GitHub 連線操作需要登入。',
        location: 'Terminal',
        code: `brew install git gh uv node pnpm

# Only for repository settings and GitHub end-to-end tests.
gh auth login -h github.com
gh auth status`
      },
      windows: {
        title: 'Windows 本機需求',
        goal: '採用 WSL2（Ubuntu）並在 WSL 裡操作 repo；選 TypeScript 再安裝 Node 24 與 pnpm 11，選 Rust 再安裝 rustup。',
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
      heading.textContent = '固定與可調政策';
      const intro = document.createElement('p');
      intro.textContent = '只列公版主要政策、可調選項與設定位置。';
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
