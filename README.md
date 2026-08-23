# CSARC Repo Template

Cyber-Arch 的可更新 repo 公版，支援 CI/CD-only、Python、TypeScript 或兩者並用。新案、既有案與後續政策更新都經 Copier 形成可審查差異。

目前公版：v0.1.0 <!-- x-release-please-version -->

[開啟內部網站與完整決策說明](docs/index.html)

## 專案概述

本 repo 維護 Copier 模板、共用 CI、安全檢查與 GitHub 設定草案。`template/` 是下發內容；根目錄則讓公版本身使用同一套規則。

目前可用：CI/CD-only、Python-only、TypeScript-only、混合四種 profile，以及 Issue／spec、PR checks、驗證、打包、checksum 與 SBOM。GitHub 設定腳本會先辨識方案與實際 API 能力；release-please 自動化則要等專用 GitHub App。

## 快速開始

共同需求是 Git、GitHub CLI、uv；TypeScript／混合案另需 Node 24+ 與 pnpm 11。Windows 請在 WSL2 執行。

```bash
git clone https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git
cd csarc-repo-template
./scripts/verify-template.sh
./scripts/apply-repository-settings.sh plan
```

建立新案前，先從 release 清單選擇團隊核准的 tag；下例以 `v0.1.0` 示範如何取得 40 字元 commit SHA，再把輸出貼入 `--vcs-ref`。

```bash
gh release list --repo Innoguard-Cyber-Arch/csarc-repo-template --limit 5
gh api repos/Innoguard-Cyber-Arch/csarc-repo-template/commits/v0.1.0 --jq .sha

uvx --from copier copier copy --trust --overwrite \
  --vcs-ref <reviewed-full-commit-sha> \
  https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git \
  ./my-project
```

既有案請先開分支，並加上 `--data project_mode=existing`；Copier 會保留原有 `pyproject.toml`／`package.json`，相依與工具設定仍須人工合併。

## 技術與目錄

| 路徑 | 用途 |
| --- | --- |
| `copier.yml`、`template/` | 問題、下發檔案與建立後任務 |
| `profiles/catalog.yaml` | 已支援語言與版本政策 |
| `.github/`、`policies/` | 公版本身的 CI 與 GitHub 設定 |
| `scripts/verify-template.sh` | 建立、更新、語言與供應鏈回歸 |
| `docs/index.html` | 內部網站與完整設計說明 |

Python 目前以 3.14、uv、Ruff、mypy、pytest 與 src layout 為基線；TypeScript 以 Node 24、pnpm 11、Biome、strict TypeScript 與 Vitest 為基線。

## 開發與驗證

1. 簡單工作先開「開發工作」Issue；標題以 12–80 個英文 ASCII 字元及至少三個詞直接描述成果，例如 `Add dependency policy checks`。Issue 不使用 PR 的 Conventional Commit 格式。
2. 開單者會自動成為負責人，並從 `bug`、`enhancement`、`documentation` 選一種類型。
3. 從 `main` 或最終 PR 回 `main` 的未合併工作分支建立 `type/<issue-number>-short-slug`；一張 Issue 與 PR 只交付一個結果，若新增需求超出完成條件就另開 Issue 與分支。
4. 公版執行 `./scripts/verify-template.sh`；生成專案執行 `./scripts/verify`。
5. PR 指向 `main` 或 stack 中的直接上游分支；整條 open PR 鏈必須最終回到 `main`。內文寫 `Closes #<issue-number>`、選擇上述三種標籤之一，並使用英文標題 `type(scope): summary`。
6. CI 與人工審查都通過才合併；AI 不得自行合併。

本 repo 沒有共用測試環境，因此採 main-only。生成專案只有在確實有長期 dev 測試環境時，才改選 `dev` 模式。
驗證入口也會執行 Issue／PR 政策正反例；標題不合格的 Issue 會讓連結它的 PR 無法通過，公版另注入不合法的 Python／TypeScript 內容，確認語言門禁真的會拒絕。

`AGENTS.md` 是 AI 工作契約；工具細節以可執行設定為準，不在 README 重複。

## 設定與密鑰

- **依方案套用設定：**推送遠端後執行 `./scripts/apply-repository-settings.sh plan`。尚未設定 Git remote 時，明確指定 `GH_REPO=owner/repo`。不支援 Ruleset 的 private repo 會標示為 `BLOCKED`，而且 `apply` 會在任何變更前停止。標籤預設採 additive 更新並保留自訂項目；只有明確傳入 `--prune-labels` 才會依 plan 列出的清單刪除。確認計畫後再執行 `apply`。
- **GitHub App 尚未設定：**未提供 `CSARC_VERSION_BOT_CLIENT_ID` 與 private key 時，版本升級與 release-please job 會略過。
- **來源證明採明確啟用：**生成非 CI-only 專案時，可在 GitHub public repo 或支援的 Enterprise Cloud private／internal repo 啟用 artifact provenance 與 SBOM attestation；其他情況維持關閉，改用 GitHub Release 上的 SHA-256 驗證。
- Actions 憑證放 GitHub Secrets／Variables；本機 runtime 才使用未提交的 `.env`。不要把 token、私鑰或實際密碼寫進 repo。

> 若 plan 顯示 `BLOCKED required governance`，需要保密就請組織 owner 在 **Organization Settings → Billing & licensing** 升級至 GitHub Team 以上；只有已核准公開的程式碼才可由人員在 **Repository Settings → General → Danger Zone** 改為 public，腳本不會變更可見性。接著建立或確認 `.github/CODEOWNERS` 指定的 team，重新執行 `plan`，看到 `APPLY policies/rulesets.json` 後才執行 `apply`。若已明確接受沒有 required checks、approval 與 CODEOWNER review 的風險，才可執行 `apply --allow-unprotected`；輸出會留下 `DEGRADED` 紀錄。

## 發布與維運

公版版本以 `version.txt`、`.release-please-manifest.json` 與 `v*` tag 同步記錄；tag 觸發完整驗證。生成專案則依 profile 產生 wheel、npm tarball 或兩者，將 distributions、`SHA256SUMS`、CycloneDX SBOM 與包含 tag／commit／workflow run 的 metadata 附加至 GitHub Release；CI/CD-only 只有 GitHub Release 的來源封存檔，不假裝有語言成品。下載後可執行 `gh release download <tag>` 與 `shasum -a 256 -c SHA256SUMS`；有啟用 attestation 時再以 `gh attestation verify <artifact> --repo <owner/repo>` 驗證。現在只有持續交付，沒有通用部署流程。

整份公版只用一個 SemVer：`fix(scope)` 升 patch、`feat(scope)` 升 minor、`!` 升 major。scope 可標 `ci`、`python`、`typescript` 或 `template`；只要任何已支援 profile 不相容，就視為整份公版的破壞性變更。

release-please 設定已備妥，但要等專用 GitHub App 才會自動開 Release PR；未設定時可人工建立 tag，不影響 CI。

## 公版更新

各專案從分支套用已審查的完整 commit SHA：

先用 `gh release list --repo Innoguard-Cyber-Arch/csarc-repo-template` 選擇團隊核准的版本，再以 `gh api repos/Innoguard-Cyber-Arch/csarc-repo-template/commits/<approved-release-tag> --jq .sha` 取得 40 字元 SHA；檢查 GitHub 上的 commit 內容後，貼到下列參數，不要直接輸入預留字樣。

```bash
git switch -c chore/<issue-number>-update-repo-template
uvx --from copier copier update --trust --vcs-ref <reviewed-full-commit-sha>
./scripts/verify
./scripts/apply-repository-settings.sh plan
```

`docs/site-content.js` 是生成專案自行維護的網站內容；Copier 更新版型時不會覆寫它。

## 負責人與支援

程式與政策審查者以 `.github/CODEOWNERS` 為準。一般缺陷與可重現問題使用 GitHub Issue；疑似資安事件或敏感資料走組織核准的內部通報管道，不貼到 Issue。
