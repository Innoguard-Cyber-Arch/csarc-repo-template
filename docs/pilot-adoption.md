# 真實 repository 導入試行

這份 checklist 用來驗證 CSARC 公版能否在不取代產品程式與既有設定的前提下，完成導入、線上檢查與後續 Copier 更新。每次試行都使用既有產品 repository、Issue、短分支與 PR，不建立專用測試 repo。

## 可重複 checklist

### 導入前

- 選定有明確 owner、實際產品內容與可執行驗證的 repository。
- 建立一張 Issue，列出要保留的程式、設定、文件與驗收指令。
- 盤點預設分支、可見性、GitHub 方案、既有 workflows、CODEOWNERS、語言 manifest 與乾淨工作樹。
- 驗證目標 GitHub Release、immutable 狀態、attestation、完整 commit SHA 與 CLI artifact。
- 在編號分支執行 `csarc adopt --dry-run`，保存 repo 外的 Markdown、machine plan 與可選 PDF，並保留終端的 Milestone description migration；確認新增、自動合併、覆寫、保留、人工合併、無法判定項目及已知風險後，只用 `--apply-plan` 套用未漂移的同一份計畫。報告不是沒有語意或執行期衝突的保證。

### 導入與驗證

- 選最窄的 profile；容器化語言工具鏈不應被誤判為 host-language profile。
- 保留產品 manifest、程式、測試、spec、網站內容與安全邊界。
- 把既有 agent 指引整併到 `AGENTS.md`，讓 `CLAUDE.md` 只保留 `@AGENTS.md`。
- 確認舊 CSARC Milestone description 已升級，custom description 仍列入人工審查；不可改動其狀態、期限或 Issue 關聯。
- 將既有 README 內容放入公版要求的八個區段，不刪除產品操作資訊。
- 先檢視 `apply-repository-settings.sh plan`，再套用可用政策；不可用能力須記為明確降級。
- 執行 `./scripts/verify` 與產品原有驗證；本機無法執行的項目要記錄原因。若 base 已有可信任 verifier，再由 GitHub hosted runner 補足。
- 第一張導入 PR 的 base 尚無 verifier 時，保留 repo 外的 machine plan、本機驗證結果與來源 Release／SHA，由非作者人工核對後才合併；不得改成執行 PR head script 或宣稱 hosted checks 已通過。
- 記錄耗時、衝突、人工步驟與採用／覆寫政策；合併後的 PR 由 base 上的可信任 policy gate 與唯讀 CI 驗證 candidate。

### 後續更新

- 從更新後的預設分支另開編號分支，固定下一個已驗證 release 與完整 SHA。
- 先執行 `csarc update --dry-run`，確認 working tree 未改變，再計時執行正式 update。
- 檢查 conflict marker、`.rej`、產品專屬檔案與 `.csarc/provenance.json`。
- 重跑本機與 GitHub 驗證，以第二支 PR 合併更新。
- 依證據類型調整 maturity：真實 consuming repo 證明共用導入、更新與線上 CI 邊界；語言模組則以可重現的建立、既有 repo 導入、更新與原生工具鏈驗證判定。

## 2026-08-24 `ai-guardrail` 結果

| 項目 | 結果 |
| --- | --- |
| Pilot | [`Innoguard-Cyber-Arch/ai-guardrail`](https://github.com/Innoguard-Cyber-Arch/ai-guardrail)，既有 private、container-first Python 產品 repo |
| 追蹤 | [pilot Issue #1](https://github.com/Innoguard-Cyber-Arch/ai-guardrail/issues/1)、[導入 PR #2](https://github.com/Innoguard-Cyber-Arch/ai-guardrail/pull/2)、[更新 PR #3](https://github.com/Innoguard-Cyber-Arch/ai-guardrail/pull/3) |
| Profile | `ci`；產品 Python 只在 Docker 內執行，未強迫加入 host Python package 結構 |
| 導入版本 | v0.2.4，commit `a4efc0cb61fe1f99cbd0d2ee7ecab7d2aa2e3095` |
| 導入 dry-run | 新增 48、保留 45、覆寫 0、Copier 衝突 0 |
| 導入耗時 | 14.04 秒；生成後人工整併 README／agent 指引，加入產品 Docker CI |
| 更新版本 | 經驗證且 immutable 的 v0.3.1，commit `172bfe101d7001c7abb96b92cf27f92132b8eec0` |
| 更新結果 | 35.23 秒、Copier 衝突 0、人工 merge 0；產品專屬變更全數保留 |
| 本機驗證 | `./scripts/verify` 通過；Docker Desktop 未啟動，因此產品 Docker regression 無法在本機執行 |
| 線上驗證 | 導入 [run 32664191977](https://github.com/Innoguard-Cyber-Arch/ai-guardrail/actions/runs/32664191977) 2 分 25 秒；更新 [run 32664445831](https://github.com/Innoguard-Cyber-Arch/ai-guardrail/actions/runs/32664445831) 2 分 17 秒；evaluation、telemetry、OSV、Zizmor、治理與 PR policy 全部通過 |

## 採用與覆寫決策

直接採用 additive labels、squash-only merge、merge 後刪 branch、least-privilege Actions、CODEOWNERS、Issue／PR policy、OSV、Zizmor、Gitleaks、治理漂移、更新通知與 release capability detection。

產品覆寫只有 profile 與驗證分工：公版使用 `ci` profile 管治理，產品專屬 `product-ci.yml` 執行既有 Docker evaluation 與 telemetry，避免為了公版改造產品封裝。GitHub Free private repo 無法強制 Ruleset，組織政策也禁止 Actions 建立或核准 PR；desired policy 留在 repo，發版維持產品自行負責且目前未自動化，沒有假裝已受保護或已能發布。

## 試行發現

- 首次導入存在平台邊界：base 尚未有 checker，而 PR head 不受信任，不能拿它新增的 script 自我驗證。安全路徑是在 repo 外使用固定 Release／SHA 的 CLI 產生 machine plan、套用同一份未漂移 plan，再由人核對來源、diff 與本機證據；合併後才由 base 上的 policy gate 與唯讀 CI 分工。
- 產品 evaluation container 固定非 root UID，Linux hosted runner 的 bind mount 原本不可寫。Pilot 將容器執行 UID 對齊 host，並只放寬模型 cache／report 目錄；兩次線上回歸都通過。
- Copier `--pretend` 可能不輸出檔案明細，即使正式 update 仍會修改檔案。CLI 不再把空輸出宣稱為「no file changes」。

### 2026-09-01 `csarc-ai-setup` 首次導入邊界

- PR #35 的 base `00ad182764bedb7ece7087fefa57051ac7888fb1` 尚無 `scripts/delivery_sync.py`，因此從 trusted base 執行的 PR policy 以 `127` 停止；這不是產品測試失敗，也不能靠執行 head 程式規避。
- 導入使用不可變來源 `v0.12.2@661b843c17730c5689c99e0e9012a1b425f0e192`，rollout head 為 `d0c5ace4ca18464b057a893587ddcfef2eaf2c8d`；local same-plan apply、`scripts/verify`、`scripts/verify-skills` 與 plan conformance 都有通過證據。
- 結論是人工核准首次導入，不建立 repo 內自我 checksum 或永久 bypass。若 canonical template 為 private，也不把可讀取來源的廣域 PAT 暴露給 PR 程式碼。

## 成熟度結論

共用治理與 CI/CD-only 基線已具備一個真實 consuming repo、owner、導入、更新及完整線上驗證證據，維持 beta。這份真實試行驗證共用生命週期，不要求為每種語言另外維護專用測試 repo。Python、TypeScript 與 Rust 各自具備可執行的建立、既有 repo 導入、Copier 更新、鎖檔、測試、建置與封裝驗證，因此語言模組也升為 beta。真實產品採用仍會累積營運證據，但不是重複驗證模板機制的第二道 beta 門檻；同時選取多個模組不形成另一種 composition。
