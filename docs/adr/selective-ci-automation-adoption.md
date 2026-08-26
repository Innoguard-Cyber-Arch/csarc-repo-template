# Selective CI/CD automation adoption ADR

- **狀態：**Accepted
- **日期：**2026-08-25
- **來源 Issue：**[#255](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/255)
- **後續修正：**[#322](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/322) supersedes #255 的 catch-all grouping 決定；下方保留原決定作為歷史，現行預設為每個更新獨立審查。
- **保留的實作 Issues：**[#242](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/242), [#245](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/245)
- **實作 PRs：**[#247](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/247), [#248](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/248)

## 問題與限制

CI/CD 設定不能因為別處存在就整批搬入。每多一項 workflow 都會增加 runner 成本、權限、更新 PR、失敗模式與維護責任；與 repository 實際能力無關的設定只會製造錯誤保證。採用判斷必須以已確認需求、最小權限、可驗證結果及清楚回退範圍為準。

## 決定

只選擇性採用能解決已發生問題、且可由現有 regression 驗證的自動化，不預先建立推測性的發布或部署能力。

| 類別 | 決定 | 邊界與理由 |
| --- | --- | --- |
| 歷史決定（已由 #322 取代） | 將官方 `actions/*` 的 minor／patch 更新合併為一組 | #255 當時以共同 owner 與較低 PR 噪音為理由採用；此列只保留歷史，不再是現行設定。 |
| 現行決定（#322） | 每個 dependency update 維持獨立 PR | Build、release 與 security toolchain 不共享回退單位；只有未來明列且通過安全審查的 allowlist 才能分組。 |
| 能力具備才啟用 | 容器 profile 使用 `none`、`verify`、`ghcr` 三種模式 | `none` 是預設值且不產生容器 job。只有 repository 已有有效 Containerfile 與 smoke command 才能使用 `verify`；只有通過既有 release boundary 且 registry write capability 可用時才能使用 `ghcr`。 |
| 目前不採用 | 通用 Containerfile、雲端 runtime、Kubernetes、多架構 placeholder、長效 token、`workflow_run` 發布鏈與第二套相依更新身分 | 尚無跨 repository 的實際需求足以負擔額外權限、供應鏈與維護成本；需要時另開 Issue 以真實使用情境重新評估。 |

`verify` 在 PR 以 Buildx cache 建置、執行 smoke test 並以 Trivy 阻擋 HIGH／CRITICAL 漏洞，但不推送映像。`ghcr` 從已驗證 release source 建置並保存相同 image bytes，發布 immutable digest、provenance 與 SPDX SBOM，再以 digest 拉回執行 smoke test。只有發布 job 取得 `packages: write`；能力為 blocked 或 unknown 時保留 verification-only 結果，不宣稱已發布。

## Ownership 與驗證

Repository owner 負責宣告容器能力與 smoke command；dependency owner 審查每個更新，並只在已有明列安全 allowlist 與共同回退單位時另案啟用分組。`.github/dependabot.yml`、`profiles/catalog.yaml`、生成 workflow 與 `./scripts/verify-template.sh` 是 executable evidence；decision site 只摘要同一決策，不取代設定與回歸測試。

Dependabot 的預設是每個更新一張獨立審查的 PR；若未來的安全 allowlist 不再成立，移除該 `groups` 設定即可恢復此預設。回退容器能力則將模式設為 `none`；既有 Containerfile 與 repository 自有部署不由模板刪除。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 複製整套既有 CI/CD | 不採用；會把無關 job、權限與維護假設一併帶入。 |
| 將 Actions minor／patch 混成一組 | 不採用；不同 owner 與供應鏈風險不應共用回退單位。 |
| 所有 repository 預先產生容器工作 | 不採用；非容器專案不應支付 Docker runner 成本或取得 registry 權限。 |
| PR 建置成功後直接發布映像 | 不採用；驗證與發布使用不同 trust boundary，發布只能承接已驗證 release source。 |

## 限制

獨立 PR 會增加例行 PR 數量，但避免把不同 toolchain 與回退單位綁在一起；分組即使未來另案啟用，也不能取代 pinning、漏洞掃描或人工審查。容器 smoke test 與映像掃描也不能證明 runtime 部署成功；部署策略仍由產品自行決定。

## 重新評估條件

當官方 Actions 不再具有一致 owner／風險、分組造成難以定位的回歸，或 Dependabot 無法表達必要更新政策時，重新評估分組。當出現經驗證的雲端部署、多架構建置或跨 registry 需求，且 owner、權限與回退方式都已確認時，再以獨立 Issue 擴充容器交付。
