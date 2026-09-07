# 移除 CSARC 公版（自助解除安裝指南）

本頁給決定不再採用 CSARC 的 repository owner：不用考古就能判斷哪些檔案、workflow 與
repository 設定是 CSARC 加入的、哪些可以刪、哪些必須用「移除 CSARC 相關內容」取代「整檔
刪除」，以及移除後如何確認乾淨。CSARC 沒有內建的 `csarc uninstall` 指令——移除永遠是
repository owner 自己審閱後的手動操作，這份文件只負責讓判斷不必逐檔案考古。

適用對象：已用 `csarc init` 或 `csarc adopt` 導入過公版的 repository。若只是評估中、還沒
實際套用任何 `init`/`adopt`/`update`，不需要本頁——回退未提交的變更即可。

## 開始之前

先確認這個 repository 是哪一種導入模式，因為模式決定「哪些檔案是 CSARC 的、哪些其實是
產品原本就有的」：

```bash
grep '^project_mode:' .csarc/config.yml
grep '^languages:' -A3 .csarc/config.yml
```

- `project_mode: new` — repository 是 CSARC `init` 建立的，本頁列出的所有路徑都是 CSARC
  管理的內容，可以直接刪除。
- `project_mode: existing`（`csarc adopt` 到既有 repository）— `README.md`、
  `SECURITY.md`、`CHANGELOG.md`、`pyproject.toml`、`package.json`、`Cargo.toml`
  這幾個檔案在既有專案上是**產品自己的檔案**，CSARC 只做選擇性合併、從不整檔覆寫或整檔
  刪除；見下方「產品自己的檔案：只移除 CSARC 加的部分」。

`languages:` 決定下面第 3 節裡哪些語言專屬路徑真的存在於這個 repository。

## 1. 先處理 repository 設定（GitHub 上、不在 Git 裡的部分）

`./scripts/apply-repository-settings.sh apply` 曾經寫入的內容不在檔案系統裡，刪檔案不會
連帶移除，要單獨處理：

- **Rulesets**：GitHub 上會有兩條名稱固定的 ruleset——`CSARC protected branches`（分支
  保護：擋 force-push、要求 PR、要求 `verify` 之類的 status check）與
  `CSARC required checks`（required checks 清單）。到 repository 的
  **Settings → Rules → Rulesets** 刪除這兩條，或用
  `gh api repos/<owner>/<repo>/rulesets --jq '.[] | select(.name | startswith("CSARC")) | .id'`
  找到 id 後 `gh api -X DELETE repos/<owner>/<repo>/rulesets/<id>`。
- **Actions 權限**：`policies/actions.json` 曾把
  `default_workflow_permissions` 設成 `read`、開放 `can_approve_pull_request_reviews`；
  不需要維持這個限制的話，到 **Settings → Actions → General** 依需求調整回組織預設值。
  這一步只影響權限寬鬆度，不影響能否移除公版，不確定就先保留。
  Runner 是否還在使用其中任何一支 `.github/workflows/*.yml`，以第 3 節的清單為準，不要
  只看這個政策檔案本身有沒有刪。
- **Issue 建立政策 / repository 選項**：`policies/issue-creation.json`
  （`issue_creation_policy: COLLABORATORS_ONLY`）與 `policies/repository.json`
  （merge 策略、`delete_branch_on_merge`、Issues/Projects/Wiki 開關）都是套用到
  repository 設定頁的一般選項，不是 CSARC 專屬的鎖，通常不需要因為移除 CSARC 而改回去；
  除非你確定要恢復到套用前的行為，否則跳過。
- **Pages / Security scanning**：`policies/pages.json`、
  `policies/security-scanning.json` 同理——這些是一般 repository 設定，不是 CSARC 留下
  的殘留物，只有你自己知道套用前的值時才需要手動改回去。

以上都是 **GitHub 平台設定**，`git rm` 不會動到；判斷「要不要改回去」看你自己需不需要那個
效果，跟「是否還有 CSARC」是兩件事。

## 2. CSARC 的狀態與追蹤檔案（一定可以刪）

```
.csarc/                  # config.yml、provenance.json；CSARC 唯一的狀態存放處
.copier-answers.yml      # 只有還沒升級到 .csarc/config.yml 的舊 schema 才會有
.csarc-adoption-pending.json   # 只有卡在未完成 adopt --finalize 時才會有
```

刪除前不需要備份：這些檔案只給 `csarc update`/`csarc adopt --finalize` 自己讀，不影響
產品程式碼或既有的 GitHub 歷史。

## 3. CSARC 自動化與 workflow（依 `project_mode`／`languages`／已啟用功能決定是否存在）

以下是 `csarc init`（`project_mode: new`、無額外語言模組）會建立的完整檔案清單，來自對本
模板實際跑一次 `init` 的輸出，不是手動整理、憑印象列的：

```
.github/CODEOWNERS
.github/ISSUE_TEMPLATE/bug.yml
.github/ISSUE_TEMPLATE/config.yml
.github/ISSUE_TEMPLATE/documentation.yml
.github/ISSUE_TEMPLATE/feature.yml
.github/ISSUE_TEMPLATE/task.yml
.github/REVIEWERS
.github/dependabot.yml
.github/pull_request_template.md
.github/workflows/ci.yml
.github/workflows/dependabot-auto-merge.yml
.github/workflows/governance-comment.yml
.github/workflows/osv.yml
.github/workflows/pr-policy.yml
.github/workflows/release-drift.yml
.github/workflows/release.yml
.github/workflows/spec-to-issue.yml
.github/workflows/work-item-lifecycle.yml
.gitignore
.gitleaks.toml
.release-please-manifest.json
docs/ci-policy.md
docs/csarc.md
docs/milestone-description.md
docs/README.md（CSARC 專案記憶地圖那一份；跟產品自己的頂層 README.md 是不同檔案）
docs/index.html、docs/index.en.html
docs/site-content.md、docs/site-theme.css
policies/*.json
release-please-config.json
scripts/*（除下面列出的例外全部都是 CSARC 的，見清單）
site/README.md、site/index.html、site/styles.css
zizmor.yml
```

`scripts/` 底下屬於 CSARC 的檔案（跟產品自己放在 `scripts/` 的東西分開判斷）：

```
scripts/__init__.py
scripts/apply-repository-settings.sh
scripts/check-project-metadata
scripts/check-release-drift
scripts/check-update-conflicts
scripts/check-verify-attestation
scripts/ci_tier.py
scripts/cleanup-worktrees
scripts/converge-release-tag
scripts/csarc_config.py
scripts/delivery_sync.py
scripts/detect-language-profile
scripts/install-actionlint
scripts/install-gitleaks
scripts/install-osv-scanner
scripts/install-shellcheck
scripts/install-syft
scripts/lint-workflows-shell
scripts/pr_lifecycle.py
scripts/promotion_gate.py
scripts/publish-release
scripts/release_assets.py
scripts/release_bundle.py
scripts/release_policy.py
scripts/render_site.py
scripts/request-reviewer
scripts/resolve-cache-root
scripts/scan-secrets
scripts/spec_to_issue.py
scripts/sync_milestone_state.py
scripts/sync_work_item_metadata.py
scripts/test-*（test-apply-repository-settings、test-issue-triage、test-pr-policy、
  test-verify-attestation、test-worktree-cleanup）
scripts/validate-issue-policy
scripts/validate-issue-title
scripts/verify
scripts/verify-dependencies
scripts/verify-fast
scripts/verify-release-candidate
scripts/verify_attestation.py
scripts/write-verify-attestation
```

### 只在你開了對應功能時才存在，才需要一併刪

- `.pre-commit-config.yaml` — 只在 `.csarc/config.yml` 的 `enable_precommit: true` 時存在。
- `.github/workflows/template-update.yml`、`scripts/check-template-update` — 只在
  `enable_template_update_notifications: true` 時存在。
- `.github/workflows/governance-drift.yml`、`scripts/check-governance-drift` — 只在
  `enable_governance_drift_check: true` 時存在。
- `.github/workflows/codeql.yml` — 只在 `enable_codeql: true` 時存在。

### 只在 `project_mode: existing`（`csarc adopt` 到既有 repo）時，這幾個反而不存在

`.github/workflows/release.yml`、`.github/workflows/release-drift.yml`、
`scripts/check-release-drift` 只在 `project_mode: new` 才由 CSARC 建立；`adopt` 到既有
repository 時，CSARC 會保留產品原有的 release workflow，不會建立這三個檔案。如果你的
repository 是用 `adopt` 導入、且這三個檔案存在，代表它們是產品原本就有的，不要刪。

## 4. 語言專屬檔案（只有 `languages:` 裡有列出的才存在）

- **python**：`.python-version`、`src/<package_name>/`、`tests/`；`project_mode: new`
  時另外建立 `pyproject.toml`、`uv.lock`。
- **typescript**：`.node-version`、`pnpm-workspace.yaml`、`biome.json`、
  `tsconfig.json`、`tsconfig.build.json`、`vitest.config.ts`、`typescript/`；
  `project_mode: new` 時另外建立 `package.json`、`pnpm-lock.yaml`。
- **rust**：`rust-toolchain.toml`、`src/lib.rs`；`project_mode: new` 時另外建立
  `Cargo.toml`、`Cargo.lock`。
- 完全沒有語言模組（`language=ci`）：`version.txt` 是 CSARC 建立的，可以刪。

`project_mode: existing` 時，`pyproject.toml`／`package.json`／`Cargo.toml` 是產品自己
的檔案，CSARC 只合併必要欄位進去，見下一節。

## 5. 產品自己的檔案：只移除 CSARC 加的部分，不要整檔刪

只有 `project_mode: existing` 才會遇到這節；`project_mode: new` 時這些檔案本來就是
CSARC 建立的，直接刪沒問題。

- `README.md`、`SECURITY.md`、`CHANGELOG.md` — 產品原本就有的檔案，CSARC 從不覆寫；不需要
  移除，頂多手動刪掉你自己當初加進去、引用 CSARC 流程的段落（例如指到
  `docs/csarc.md`、`./scripts/verify` 的說明文字）。
- `pyproject.toml`／`package.json`／`Cargo.toml` — CSARC 只合併了它需要的欄位／依賴／
  script（例如 lint、type-check 相關的 dev dependency）。整檔刪除會連產品自己的設定一起
  刪掉；改成手動比對、只移除明顯是 CSARC 加入的區塊或依賴。

## 6. 確認移除乾淨

```bash
git status --short                 # 看有沒有殘留、未預期的檔案
grep -rl "csarc\|CSARC" --include="*.yml" --include="*.md" . \
  | grep -v -e "^\./\.git/" -e node_modules   # 找還留著的引用
```

- `git status` 不該再顯示 `.csarc/`。
- `.github/workflows/` 底下不該再有第 3 節列出的 CSARC workflow；產品自己的 CI（如果是
  `adopt` 保留下來的）應該還在、還能正常跑。
- 若之前有依賴 `./scripts/verify` 當作 CI 或 pre-commit 的驗證入口，記得先換成產品自己的
  驗證指令，否則 CI 會找不到這支 script 而失敗。
- 上方「1. 先處理 repository 設定」列出的 ruleset、Actions 權限如果你選擇要改回去，到
  GitHub 網頁確認已經生效（`gh api repos/<owner>/<repo>/rulesets` 應該不再列出
  `CSARC protected branches`／`CSARC required checks`）。
- 提交這次移除時，用一個獨立的 PR、走正常審查流程；不要在移除 CSARC 的同一個 PR 裡混入
  不相關的產品變更，方便之後回頭確認移除範圍。
