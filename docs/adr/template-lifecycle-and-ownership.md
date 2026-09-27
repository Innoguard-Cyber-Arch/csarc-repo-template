# Template lifecycle and ownership ADR

- **狀態：**Accepted
- **日期：**2026-08-24
- **來源 Issues：**[#7](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/7), [#31](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/31), [#76](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/76), [#113](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/113), [#116](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/116), [#157](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/157), [#196](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/196), [#219](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/219), [#368](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/368), [#411](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/411), [#433](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/433), [#877](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/877), [#963](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/963), [#942](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/942)
- **實作 PRs：**[#8](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/8), [#53](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/53), [#88](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/88), [#115](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/115), [#124](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/124), [#160](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/160), [#217](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/217), [#231](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/231), [#412](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/412)

## 問題與限制

公版本身與 consuming project 共用大量治理檔案，但產品 source、spec、decision、README 與網站內容不能被模板更新靜默覆寫。Root 與 template 的重複檔若只靠人手同步，也會在測試前漂移。

## 決定

- `copier.yml`、`template/`、`policies/` 與 `profiles/catalog.yaml` 定義可版本化產品；root 是公版本身的 dogfood 實例。
- 完全相同的 root／template 檔案由 `scripts/sync-paired-files.sh` 以 root 為來源產生；參數化或刻意不同的檔案由生成 fixture 驗證。
- `docs/specs/**/*.md`、產品 source／tests 與網站內容等 project-owned 檔案在 update 時保留。
- `csarc init/adopt/update` 先解析 immutable release 與完整 SHA，dry-run 不改 target；正式操作仍不自動 push、開 PR 或套遠端 settings。
- 每個 Release 只發布一份綁定 canonical repository、tag、full SHA、安裝指南與 `copier.yml` 的 status-first agent prompt；agent 依同一份 Copier schema 分組詢問 applicable questions，並沿用 `--data` 與 dry-run JSON，不維護第二份問題或設定 schema。
- 既有 repo 導入的同一份 dry-run report／machine plan 唯讀盤點 GitHub Issue Types 與 labels，提供保守的 `preserve`／`map`／`decision-required` 建議；agent 可讓使用者整批接受安全建議或逐項確認，但 adopt 不改遠端 metadata，repository settings 仍維持獨立的 plan／apply／check 邊界。
- 任何 conflict marker 或 `.rej` 使驗證失敗；不能把 Copier 完成等同產品語意已整合。
- 成熟度證據分兩層：真實 consuming repo 證明共用導入、更新與線上 CI 邊界；各語言模組以建立、既有 repo 導入、更新與原生工具鏈的可重現測試取得 beta，不為每種語言建立專用測試 repo。
- 語言模組沒有真實 consuming repo 時，不以人造 pilot 或 nested sample repo 補證據；共用 lifecycle 沿用既有 `ai-guardrail` 證據，語言專屬 beta 只看測試期間在暫存目錄即時生成的 create、existing-repository adopt、Copier update 與原生工具鏈驗證。未來若出現真實 adopter，可另作 canary，但不列為門檻。
- Go 模組契約（#942）：reviewed stable 依 Go 官方下載清單（`https://go.dev/dl/?mode=json`，2026-09-24 查得 `go1.27.1`；1.26 系列最新為 `go1.26.8`），development runtime 為 Go 1.27.1，最低支援版本等於 reviewed stable 的 minor（Go 1.27，比照 Rust MSRV）；generated `go.mod` 只寫 `go 1.27.0`，不寫 `toolchain` directive，本機 verify、CLI 與 hosted CI 以 `GOTOOLCHAIN=local` 禁止自動下載工具鏈。新 stable 發布後觀察 14 天，再由人工審核的 PR 更新 catalog、生成檔與 CI pin。
- Go 原生驗證只用 Go 工具鏈本身：`gofmt`、`go vet ./...`、`go test ./...`、`go build ./...`；不加入第三方 formatter、linter、test runner 或 package manager。Go modules 是唯一依賴管理，`go.sum` 只在實際有依賴時存在，不製造空檔。
- Go 專案的版本與 Release 沿用 repository SemVer、Git tag、GitHub Release source archive、checksum 與 SBOM（release type `simple`）；`go.mod` 不承載版本，不發布 module proxy 或預編譯 binary。
- Milestone 過渡狀態：語言在 Milestone 交付期間可先成為可選模組，catalog 以 `candidate` 連到 tracker 並維持 `future`；只有 `promotion_requirements.language_module` 全部有可重現證據後，才由同一 Milestone 的文件驗收 Issue 改為 `beta`。
- Python 模組採用 Astral 工具鏈：uv 管理環境、鎖檔與執行，Ruff 負責格式與 lint，ty 負責型別檢查；ty 在 0.x 期間固定精確版本以避免規則漂移。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | 四種 profile、單一公版與 generated-project verification | [#7](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/7)／[#8](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/8) |
| Preserved | 更新衝突 fail closed | [#31](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/31)／[#53](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/53) |
| Superseded | 人工雙改 byte-identical root／template 檔案 | [#76](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/76)／[#88](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/88) |
| Preserved | adopt 在 manual merge 後的 resumability 與 transaction boundary（same-plan 重建、target／plan 漂移偵測、失敗時 target 不變） | [#196](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/196)／[#217](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/217)／[#219](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/219)／[#231](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/231) |
| Superseded in presentation | 四份 lifecycle prompts 改由一份 status-first prompt 選路徑；固定版本身份與 dry-run／確認邊界保留 | [#631](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/631)／[#877](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/877) |
| Superseded | Go 需先有真實 consuming repo 定義工具鏈與相容政策才可加入（舊 catalog `reason`） | [#411](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/411)／[#942](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/942) |
| Superseded | Go generated `go.mod` 寫 `go 1.26.0` 加 `toolchain go1.27.1`；預設 `GOTOOLCHAIN=auto` 會自動下載新工具鏈，使最低版本永不被實測 | [#942](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/942) |

## Ownership 與驗證

公版維護 renderer、governance、workflow 與 deterministic migration；專案維護產品 source、規格、決策與允許的內容覆寫。Create、adopt、update、conflict、preservation 與每個 beta 語言的原生工具鏈都必須出現在 `./scripts/verify-template.sh` 的實際生成測資。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 所有 root／template 檔案一律 byte-identical | 不採用；Jinja 參數化與不同 audience 是真實差異 |
| 更新時覆寫所有文件 | 不採用；會破壞產品自有記憶與操作內容 |
| 通用自動 merge engine | 未採用；目前使用固定 ownership 與明確 manual review 較安全 |
| 每個語言各養一個專用 GitHub 測試 repo | 不採用；重複驗證共用導入機制，且產生額外維運與漂移成本 |

## 重新評估條件

[#368](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/368)（首次導入不信任 PR head 的 bootstrap 邊界）完成條件已全部打勾，但保持 open 直到 [#433](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/433) 的整合候選證明 release-ownership 綁定、更新通知與文件對齊；#433 合併並關閉 #368 後可將本節精簡為單純的重新評估提醒。在此之前不得把候選行為寫成 active。
