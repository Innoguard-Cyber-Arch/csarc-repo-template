# Transactional repository adoption

- Status: Accepted
- Date: 2026-08-24
- Issue: [#219](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/219)

## 問題與限制

既有 repo 的產品內容、CSARC 管理內容與執行期產物具有不同 ownership。單靠同路徑檔案 byte comparison，會把可預期的差異永久列為 manual merge；直接寫入後才驗證，也可能留下不完整導入。Agent 不得為了滿足 clean-tree 前置條件自行 stash 或 commit 使用者工作。

Generic prompt 需要保持穩定且不硬編工作路徑，但不能因此移除供應鏈身分驗證。Windows 的正式執行環境是 WSL2；native Windows shell 並非目前契約。

## 決策

三個 lifecycle 各保留一條 generic agent prompt：`init`、`adopt`、`update`。CLI 從目前 workspace 判斷位置，解析 canonical immutable Release，依序驗證 repository numeric ID、Release 狀態、tag commit、commit signature與 attestation，並把 tag 與 full SHA 寫入 plan 和 provenance。Release-specific prompt 直接攜帶相同 tag 與 full SHA。

既有導入採兩階段流程：

1. `adopt --dry-run` 只讀目標 repo，在 repo 外原子更新 Markdown、PDF 與 machine-readable plan。dirty tree 可產生 review-only plan，但不可套用。
2. `adopt --apply-plan` 重新驗證 Release、repo identity、HEAD、working tree、answers、檔案決策與 digest；在暫存 clone 產生完整候選，執行 `./scripts/verify` 與 project hook，再以通過 `git apply --check` 的同一份 patch 寫入目標。

需要人工合併時，第一份 plan 只建立 resumable checkpoint。人工完成清單後，`adopt --finalize --dry-run` 會從已驗證 template 重新推導 managed／manual 集合，在隔離 clone 建立並驗證完成態候選，再把 checkpoint、人工結果、完整允許 working-tree state 與預期 artifacts 綁入新的 repo 外 plan。正式 finalize 只接受該 plan；直接 finalize、非預期檔案或確認前後的任何漂移都停止。

固定 ownership policy 如下：

- `README.md`、`CHANGELOG.md` 由產品擁有，existing mode 不產生同名檔案。
- `.gitignore` 保留產品順序，再附加模板尚未存在的行。
- `AGENTS.md` 只替換 `BEGIN/END CSARC MANAGED BLOCK` 之間內容；沒有 marker 時附加管理區塊，marker 不合法時停止。
- 產品 `.github/workflows/release.yml` 保留；existing mode 另產生 `.github/workflows/csarc-release.yml`。
- 其他無固定語意的碰撞維持明確人工處理與 resumable checkpoint，不導入通用三方合併引擎。

Python 以 `uvx --python 3.14` 逐次選擇，不修改 shell profile、`PATH` 或全域環境。Ubuntu 與 macOS 跑完整 adoption 測試；Windows 使用 WSL2，native Windows 明確 fail closed。

## 未採用方案

- 在 README generic prompt 固定 path 或 SHA：path 無法跨 repo 重用，SHA 也無法在包含自身內容的 commit 中自我引用。
- 讓 agent 自行 stash、commit 或逐檔決定：會改動使用者工作，也無法形成可重放契約。
- 對所有文字做通用三方合併：ownership 與語意不明，增加靜默破壞風險。
- 寫入目標後再驗證：失敗時會留下半套用狀態。
- 宣稱支援 native Windows：目前 shell 與工具鏈契約沒有相應證據。

## Ownership、驗證與重新評估

CLI、模板 ownership policy、release prompt 產生器與 lifecycle e2e 由本 repo 維護；產品自行維護 README、CHANGELOG、產品 release workflow與選配的 executable `scripts/verify-product`。`./scripts/verify-template.sh` 必須涵蓋 plan 漂移、固定碰撞策略、驗證失敗不寫入、特殊路徑與 OS matrix。

若未來要支援 native Windows、更多自動合併類型，或改變 Release trust chain，必須以新的 Issue、跨平台證據及 decision record 重新評估。
