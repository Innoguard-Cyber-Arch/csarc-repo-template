# CSARC Repo Template

Cyber-Arch 的可更新 repo 公版，支援 Python、TypeScript 或兩者並用。新案、既有案與後續政策更新都經 Copier 形成可審查差異。

[開啟內部網站與完整決策說明](docs/index.html)

## 專案概述

本 repo 維護 Copier 模板、共用 CI、安全檢查與 GitHub 設定草案。`template/` 是下發內容；根目錄則讓公版本身使用同一套規則。

目前可用：三種語言 profile、Issue／spec、PR checks、驗證、打包、checksum 與 SBOM。Ruleset 要等 GitHub Team 與 CODEOWNERS team；release-please 自動化要等專用 GitHub App。

## 快速開始

共同需求是 Git、GitHub CLI、uv；TypeScript／混合案另需 Node 24+ 與 pnpm 11。Windows 請在 WSL2 執行。

```bash
git clone https://github.com/Innoguard-Cyber-Arch/csarc-repo-template.git
cd csarc-repo-template
./scripts/verify-template.sh
```

建立新案：

```bash
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

1. 用 Issue／`docs/specs/` 定義可獨立驗證的結果。
2. 在短分支修改；PR 標題用英文 `type(scope): summary`。
3. 公版執行 `./scripts/verify-template.sh`；生成專案執行 `./scripts/verify`。
4. CI、同事與 CODEOWNER 都通過後才合併。

`AGENTS.md` 是 AI 工作契約；工具細節以可執行設定為準，不在 README 重複。

## 設定與密鑰

- **Ruleset 尚未套用：**private organization repo 需 GitHub Team 與真實 CODEOWNERS team；條件備妥後才執行 `./scripts/apply-repository-settings.sh plan`／`apply`。
- **GitHub App 尚未設定：**未提供 `CSARC_VERSION_BOT_CLIENT_ID` 與 private key 時，版本升級與 release-please job 會略過。
- Actions 憑證放 GitHub Secrets／Variables；本機 runtime 才使用未提交的 `.env`。不要把 token、私鑰或實際密碼寫進 repo。

## 發布與維運

`v*` tag 觸發公版完整驗證；生成專案則依 profile 產生 wheel、npm tarball 或兩者，附 SHA-256 與非空 CycloneDX SBOM。現在只有持續交付，沒有通用部署流程。

release-please 設定已備妥，但要等專用 GitHub App 才會自動開 Release PR；未設定時可人工建立 tag，不影響 CI。

## 公版更新

各專案從分支套用已審查的完整 commit SHA：

```bash
git switch -c chore/update-repo-template
uvx --from copier copier update --trust --vcs-ref <reviewed-full-commit-sha>
./scripts/verify
```

`docs/site-content.js` 是生成專案自行維護的網站內容；Copier 更新版型時不會覆寫它。

## 負責人與支援

程式與政策審查者以 `.github/CODEOWNERS` 為準。一般缺陷與可重現問題使用 GitHub Issue；疑似資安事件或敏感資料走組織核准的內部通報管道，不貼到 Issue。
