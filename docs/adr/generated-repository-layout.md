# Consolidate generated repository infrastructure

- **狀態：**Accepted
- **日期：**2026-09-21
- **來源 Issues：**[#742](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/742)、[#1070](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1070)（2026-10-14 補充 runtime 邊界與固定位置 allowlist）
- **實作 PR：**[#860](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/860)

## 問題與限制

過去生成專案把 CSARC 腳本、政策、網站引擎與工具設定散落在 root，與產品程式、文件及 manifest 混在一起。使用者難以判斷哪些檔案由產品維護、哪些由公版更新，也容易把不同工具的衍生設定誤認為多份可編輯來源。

GitHub 與掃描工具只會從固定位置讀取部分檔案，例如 `.github/workflows/`、人類通報用的 `.github/SECURITY.md`、scanner guidance 用的 root `SECURITY.md`，以及 root `AGENTS.md`；語言工具也可能要求 root manifest。這些平台或產品檔案不能為了視覺整齊而搬走。

## 決定

生成專案採下列 ownership 邊界：

- `.csarc/config.yml` 是唯一由使用者編輯的 CSARC 設定來源；網站 `[[key]]`、政策開關、語言與交付選項都讀取它。
- `.csarc/scripts/` 是穩定 adapter layer。腳本直接把 `.csarc/config.yml` 轉成工具參數；Gitleaks 與 pre-commit 只能吃自己的格式，因此 adapter 只在執行當下於暫存目錄產生設定，結束時刪除。生成專案不提交這兩份工具設定，也不提交未使用的 Zizmor 設定。
- `.csarc/policies/*.json` 與 release-please config 是公版管理的唯讀政策／衍生實作資料，不是第二份使用者設定。使用者不得直接修改；變更來源仍是 `.csarc/config.yml` 或公版本身。
- `.csarc/release-please-manifest.json` 是工具必須提交的版本狀態，不是設定來源，因此持久保存。
- 平台固定檔保留在 `.github/`；root `SECURITY.md` 提供 scanner discovery 所需的 repository-wide policy，與 `.github/SECURITY.md` 的人類通報流程分工；root `AGENTS.md` 只作自動探索入口，詳細規則放 `.csarc/docs/agent-workflow.md`，`.claude/CLAUDE.md` 只引用 root 入口。
- 專案文件、ADR、spec 與網站內容屬於產品，保留在 `docs/`。網站來源固定在 `docs/site/`，產物仍是 `docs/index.html` 與 `docs/index.en.html`；renderer 與資產放 `.csarc/site/`。
- 產品程式、測試與語言 manifest 留在慣用 root 路徑，不移入 `.csarc`。
- 公版擁有的 runtime、fixture 與必要測試只放 `.csarc/`；`.csarc/` 以外只允許下方 allowlist 列出的 GitHub、scanner、agent 固定位置、語言工具設定與產品 starter。

## Runtime 與產品工具邊界

- 生成專案的 `.csarc/scripts/verify` 與 `verify-fast` 只驗證產品與自己的設定，不執行公版自測（`.csarc/scripts/test-*` 與 `.csarc/tests/`）。同一批案例由公版 CI 對代表性 render 執行，案例數不得減少；診斷改由 `csarc status` 提供。
- 產品 lint、format、type check、test discovery 與 coverage 不收集 `.csarc/`。`.csarc/.ignore` 讓遵守 ignore 檔的工具（Ruff、ty 等）跳過控制層的 Python 檔，Git 照常追蹤這些檔案；pytest 預設不遞迴進入點開頭的目錄。產品 manifest（`pyproject.toml`、`package.json`、`Cargo.toml`、`go.mod`）不寫 `.csarc`，也不把它列入套件、workspace 或 coverage 來源，所以採用既有專案時不必修改產品 manifest。代價是 ripgrep 這類工具搜尋整個 repository 時也會略過 `.csarc` 的 Python 檔，需要時直接指定檔案路徑。
- `.csarc/scripts` 的模組層 import 只載入入口必定需要的模組，其他 sibling 在命令第一次使用時才載入。合法 render 少了選用模組（例如 `documentation_mode` 不是 `template-and-content` 時的網站模組），其餘入口仍可獨立載入與執行。
- 本機與 hosted 驗證證據使用同一個正規化 record（`local_verification.normalized_record`），欄位與驗證規則相同，只保留各自的 trust label：`self-attested-local` 或 `trusted-hosted`。

## 固定位置 allowlist

fresh render 在 `.csarc/` 以外只能產生下列路徑（`*` 代表專案名稱、套件名稱或檔名）。新增項目必須先修改本 ADR；`tests/test_generated_layout_allowlist.py` 拿模板來源與代表性 render 對照這份清單。

```text
# GitHub fixed locations
.github/CODEOWNERS
.github/ISSUE_TEMPLATE/*.yml
.github/SECURITY.md
.github/dependabot.yml
.github/pull_request_template.md
.github/workflows/*.yml
# Scanner and agent discovery
SECURITY.md
AGENTS.md
.claude/CLAUDE.md
# Language tool settings, manifests, and lockfiles
.gitignore
.node-version
.python-version
Cargo.lock
Cargo.toml
Dockerfile
biome.json
docker-compose.yml
go.mod
package.json
pnpm-lock.yaml
pnpm-workspace.yaml
pyproject.toml
rust-toolchain.toml
tsconfig.build.json
tsconfig.json
uv.lock
vitest.config.ts
# Product-owned starters and documentation
CHANGELOG.md
LICENSE
README.md
README.*.md
cmd/*/main.go
docs/README.md
docs/adr/README.md
docs/index.html
docs/index.*.html
docs/site/content/_index.*.md
docs/site/data/navigation.json
docs/site/theme.css
docs/specs/SPEC-001-example.md
internal/*/*.go
src/*/__init__.py
src/lib.rs
tests/test_smoke.py
typescript/src/index.ts
typescript/tests/index.test.ts
```

## 四種 inventory

| 情境 | root 允許內容 | CSARC／平台內容 | 行為 |
| --- | --- | --- | --- |
| 最小新專案 | README、CHANGELOG、AGENTS、SECURITY、`.gitignore`、`docs/`、空的 `src/` 與忽略的 `dist/` 建置目錄 | `.csarc/`、`.github/`、`.claude/` | 不產生 root `scripts/`、`policies/` 或 `site/` |
| 完整新專案 | 最小集合加語言 manifest、lockfile、`src/`、`tests/`、`typescript/`、Go 的 `go.mod`／`cmd/`／`internal/` 與選用容器檔 | 同上，加選用 workflow | root 白名單由所選語言與功能決定 |
| 既有專案採用 | 原有產品檔、manifest、文件與驗證 hook 全數保留 | 僅新增已核准且無衝突的 CSARC／平台檔 | 同名文字差異需人工合併，特殊檔或目錄碰撞 fail closed |
| 舊版專案更新 | 既有產品檔保持原位 | 已知舊 CSARC 路徑搬到新位置 | plan 明列 add／move／preserve／delete；不同內容的目的檔碰撞時不寫入 |

## 更新搬移規則

`csarc update` 只搬移新模板仍認得的舊 CSARC 檔案：`scripts/`、`policies/`、兩個公版自測、網站引擎／資產、CSARC 操作文件、版本與仍需持久保存的工具狀態。舊 `.gitleaks.toml`、`.pre-commit-config.yaml` 與 `zizmor.yml` 由新 adapter 取代，plan 明列 delete。`site/content/**` 搬到 `docs/site/content/**` 且保留 consuming repository 的文字。既有專案的 root `SECURITY.md` 視為產品所有，不自動搬移或覆寫；缺少此檔案時可取得公版 scanner baseline。公版建立的新專案則由 Copier 把舊 root disclosure 更新成 scanner policy，並另外建立 `.github/SECURITY.md` 人類通報政策；#742 的一次性 root-to-`.github` move 因 #872 建立新的 root discovery contract 而不再適用。

搬移先在隔離 candidate clone 執行，再由 Copier 更新，完整驗證通過後才以單一 patch 寫回目標。若新舊位置同時存在且內容不同，整次更新停止；若內容相同，只移除舊副本。產品自訂 `scripts/*`、`tests/*` 與其他未知檔案一律保留。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 所有檔案都放 `.csarc/` | 不採用；GitHub 固定位置與語言工具慣例會失效 |
| 保留 root `site/` | 不採用；與 `docs/` 重複，網站內容改歸 `docs/site/` |
| 每個工具各自維護一份使用者設定 | 不採用；容易漂移，`.csarc/config.yml` 必須是唯一設定來源 |
| 更新時直接刪除舊 root 目錄 | 不採用；可能刪到產品檔，改採逐檔已知映射與碰撞保護 |

## Ownership 與驗證

公版維護 `.csarc/`、managed workflows 與搬移映射；consuming repository 維護產品程式、manifest、`docs/adr/`、`docs/specs/`、`docs/site/content/` 與 `docs/site/theme.css`。最小與完整生成專案以 root allowlist 測試；舊版更新以搬移／碰撞回歸測試；代表性四語言專案執行完整 verifier。`documentation_mode: off` 與代表性 lifecycle／release ownership render 由生成專案自己的 verifier 驗證；公版自測、import matrix，以及產品工具不收集 `.csarc/` 的負向測試留在公版 CI。

## 重新評估條件

只有平台或 scanner discovery 固定路徑改變、工具無法接受明確 config path，或新的持久狀態不能由 `.csarc/config.yml` 與公版重建時，才重新評估此決定。
