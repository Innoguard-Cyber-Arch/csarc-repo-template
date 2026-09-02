# Selective CI/CD automation adoption ADR

- **狀態：**Superseded
- **日期：**2026-08-25
- **備註：**由 #430 部分取代；只保留 official Actions 更新分組
- **來源 Issue：**[#255](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/255)
- **保留的實作 Issues：**[#242](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/242), [#245](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/245)
- **實作 PRs：**[#247](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/247), [#248](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/248)

## 問題與限制

CI/CD 設定不能因為別處存在就整批搬入。每多一項 workflow 都會增加 runner 成本、權限、更新 PR、失敗模式與維護責任；與 repository 實際能力無關的設定只會製造錯誤保證。採用判斷必須以已確認需求、最小權限、可驗證結果及清楚回退範圍為準。

## 決定

只選擇性採用能解決已發生問題、且可由現有 regression 驗證的自動化，不預先建立推測性的發布或部署能力。

| 類別 | 決定 | 邊界與理由 |
| --- | --- | --- |
| 立即採用 | 將官方 `actions/*` 的 minor／patch 更新合併為一組 | 這些更新具有共同 owner 與相近審查風險，可降低例行 PR 噪音；major 及第三方 Actions 仍各自成 PR，避免擴大審查與回退範圍。 |
| 不採用 | 公版容器驗證／發布與 registry attestation 選項 | 目前沒有 active build、scan 或 publisher；移除無執行者的設定，避免產生錯誤保證。 |
| 目前不採用 | 通用 Containerfile、雲端 runtime、Kubernetes、多架構 placeholder、長效 token、`workflow_run` 發布鏈與第二套相依更新身分 | 尚無跨 repository 的實際需求足以負擔額外權限、供應鏈與維護成本；需要時另開 Issue 以真實使用情境重新評估。 |

原容器設計的 Buildx、smoke、Trivy、GHCR 與 attestation 路徑只保留在 Git／Issue 歷史，不能當成現行能力。模板不再詢問或保存這些無執行者的選項，也不生成容器 build／publish job 或 registry 權限。

## Ownership 與驗證

Dependency owner 審查官方 Actions 分組是否仍維持共同來源與相近風險。`.github/dependabot.yml` 與回歸測試是這項保留決策的 executable evidence；decision site 只摘要同一決策，不取代設定與測試。

回退官方 Actions 分組只需移除 `groups.official-actions`，個別更新仍會繼續提出。既有產品的 Containerfile、workflow 與部署仍由產品擁有；Copier 不接管、覆寫或宣稱已驗證這些能力。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 複製整套既有 CI/CD | 不採用；會把無關 job、權限與維護假設一併帶入。 |
| 將所有 Actions minor／patch 混成一組 | 不採用；不同 owner 與供應鏈風險不應共用回退單位。 |
| 所有 repository 預先產生容器工作 | 不採用；非容器專案不應支付 Docker runner 成本或取得 registry 權限。 |
| PR 建置成功後直接發布映像 | 不採用；驗證與發布使用不同 trust boundary，發布只能承接已驗證 release source。 |

## 限制

分組只能降低 PR 數量，不能取代 pinning、漏洞掃描或人工審查。容器 smoke test 與映像掃描也不能證明 runtime 部署成功；部署策略仍由產品自行決定。

## 重新評估條件

當官方 Actions 不再具有一致 owner／風險、分組造成難以定位的回歸，或 Dependabot 無法表達必要更新政策時，重新評估分組。當出現經驗證的雲端部署、多架構建置或跨 registry 需求，且 owner、權限與回退方式都已確認時，再以獨立 Issue 擴充容器交付。
