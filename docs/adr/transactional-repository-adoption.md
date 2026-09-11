# Transactional repository adoption

- **狀態：**Accepted
- **日期：**2026-08-24
- **來源 Issues：**[#219](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/219), [#250](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/250), [#714](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/714), [#715](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/715), [#716](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/716)
- **實作 PR：**[#231](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/231)

## 問題與限制

既有 repo 的產品內容、CSARC 管理內容與執行期產物具有不同 ownership。單靠同路徑檔案 byte comparison，會把可預期的差異永久列為 manual merge；直接寫入後才驗證，也可能留下不完整導入。Agent 不得為了滿足 clean-tree 前置條件自行 stash 或 commit 使用者工作。

Generic prompt 需要保持穩定且不硬編工作路徑，但不能因此移除供應鏈身分驗證。Windows 的正式執行環境是 WSL2；native Windows shell 並非目前契約。

## 決定

三個 lifecycle 各保留一條 generic agent prompt：`init`、`adopt`、`update`。CLI 從目前 workspace 判斷位置，解析 canonical immutable Release，依序驗證 repository numeric ID、Release 狀態、tag commit、commit signature與 attestation，並把 tag 與 full SHA 寫入 plan 和 provenance。Release-specific prompt 直接攜帶相同 tag 與 full SHA。

既有導入採兩階段流程：

1. `adopt` 在沒有 `--apply-plan` 時預設為 dry-run，只讀目標 repo，並在 repo 外原子更新純 Markdown 導入報告（獨立版本號記錄在報告內，見 [#530](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/530)）與 machine-readable plan；明確的 `--dry-run` 仍相容。初始 plan 可從核准 Release 建立靜態候選，但不得執行 target-owned policy helper 或 product hook，驗證狀態明列為等待授權。只有未 staged 的 tracked modifications 且全由 plan 明列為 `preserve` 時，dirty paths 才可連同原始 bytes 建立候選並套用同一份 plan；其他 dirty tree 只產生 review-only plan。`adopt --finalize` 使用相同安全預設。
2. `adopt --apply-plan` 先顯示保存的 plan 並取得確認，再重新驗證 Release、repo identity、HEAD、working tree、所有實際 render inputs（包含未寫入 Copier answers 的條件式衍生值）、檔案決策與 digest；在暫存 clone 產生完整候選，執行 `./scripts/verify` 與獨立的 `project_verification_hook`，再以通過 `git apply --check` 的同一份 patch 寫入目標。hook 只接受 repo 內存在、可執行的相對檔案，不透過 shell，且不得解析成或重新進入 canonical `scripts/verify`；未設定時才沿用 `scripts/verify-product`。路徑與來源綁入授權前 plan，執行結果與原因則在授權後產生；失敗不寫入 target。`update --check` 只驗證 hook 設定、不執行 hook，正式 update 也只套用已在暫存 clone 通過驗證的 patch。若靜態 binding 不同，錯誤會列出精確 JSON path 與前後值，同時維持 fail closed。

`status` 與 `update --check` 的 policy／capability inspection 也不得執行 target checkout 內的 shell 或 Python。CLI 只從已驗證 Release 重新產生完整 helper closure，再把 target 當成資料與 GitHub context 檢查；unreleased 或無法驗證的來源回報 unavailable／unknown，不把 target helper 當成可信執行入口。

Candidate 內的 provenance、pending checkpoint 與 repo 外報告共用 hardened same-directory atomic writer：從可信 root 的 directory descriptor 逐層以 no-follow 語意開啟 ancestor，拒絕 destination symlink／special file，再用隨機且 exclusive 的同目錄暫存檔寫入、同步並 replace。可預測 `.tmp` symlink、ancestor symlink 或 destination symlink 都不得把資料寫到 root 外，也不得被靜默取代。

Machine plan 與 pending checkpoint 只保存可比對資料，不承載新的程式執行權。若來源是開發用 unreleased commit，每一次 replay 都必須由當次 invocation 重新提供相同本機 source、完整 SHA 與 `--allow-unreleased`；正式 verified Release 則拒絕這些開發旗標。Replay 在執行 Copier task、target policy script 或 product hook 前，先顯示保存的完整 plan 並取得確認，確認後仍重建候選並維持原有 same-plan 比對。

需要人工合併時，第一份 plan 只建立 resumable checkpoint。人工完成清單後，`adopt --finalize --dry-run` 會從已驗證 template 重新推導 managed／manual 集合，在隔離 clone 建立靜態完成態候選，再把 checkpoint、人工結果、完整允許 working-tree state 與預期 artifacts 綁入新的 repo 外 plan。正式 finalize 只接受該 plan，並在核准後才執行候選驗證；直接 finalize、驗證失敗、非預期檔案或確認前後的任何漂移都停止。

固定 ownership policy 如下：

- `README.md`、`CHANGELOG.md` 由產品擁有，existing mode 不產生同名檔案。
- `.gitignore` 保留產品順序，再附加模板尚未存在的行。
- `AGENTS.md` 只替換 `BEGIN/END CSARC MANAGED BLOCK` 之間內容；沒有 marker 時附加管理區塊，marker 不合法時停止。
- 產品 `.github/workflows/release.yml` 保留；existing mode 不產生第二支 CSARC release workflow，也不從檔名推測其 owner 或功能。
- 其他無固定語意的碰撞維持明確人工處理與 resumable checkpoint，不導入通用三方合併引擎。

Release prompt 以 exact commit 從 canonical GitHub repository 執行 CLI；`uvx --python 3.14` 逐次取得隔離 runtime，不要求預先安裝全域 Python，也不修改 shell profile、`PATH` 或全域環境。Ubuntu 與 macOS 跑完整 adoption 測試；Windows 使用 WSL2，native Windows 明確 fail closed。

## 評估過的替代方案

- 在 README generic prompt 固定 path 或 SHA：path 無法跨 repo 重用，SHA 也無法在包含自身內容的 commit 中自我引用。
- 讓 agent 自行 stash、commit 或逐檔決定：會改動使用者工作，也無法形成可重放契約。
- 對所有文字做通用三方合併：ownership 與語意不明，增加靜默破壞風險。
- 寫入目標後再驗證：失敗時會留下半套用狀態。
- 宣稱支援 native Windows：目前 shell 與工具鏈契約沒有相應證據。

## Ownership 與驗證

CLI、模板 ownership policy、release prompt 產生器與 lifecycle e2e 由本 repo 維護；產品自行維護 README、CHANGELOG、產品 release workflow與選配的 executable `scripts/verify-product`。`./scripts/verify-template.sh` 必須涵蓋 plan 漂移、固定碰撞策略、驗證失敗不寫入、特殊路徑與 OS matrix。

## 重新評估條件

若未來要支援 native Windows、更多自動合併類型，或改變 Release trust chain，必須以新的 Issue、跨平台證據及 decision record 重新評估。
