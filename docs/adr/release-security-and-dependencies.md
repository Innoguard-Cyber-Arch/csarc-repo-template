# Release, security, and dependency posture ADR

- **狀態：**Accepted
- **日期：**2026-08-24
- **來源 Issues：**[#29](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/29), [#30](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/30), [#35](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/35), [#36](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/36), [#64](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/64), [#98](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/98), [#101](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/101), [#104](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/104), [#110](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/110), [#123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123), [#142](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/142), [#242](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/242), [#250](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/250)
- **實作 PRs：**[#60](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/60), [#61](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/61), [#92](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/92), [#51](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/51), [#118](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/118), [#119](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/119), [#128](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/128), [#139](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/139), [#143](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/143), [#151](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/151)

## 問題與限制

Release automation 會跨越 Git history、GitHub workflow permissions、immutable Release、artifact、attestation 與 registry。任一段的「成功」都不能自動證明其他段，依賴更新工具也不能取代漏洞、來源與成品驗證。

## 決定

- 精確版本只在 merge／promotion 後由 default-branch history 配置；tag 必須指到已包含該版本與 CHANGELOG 的 source commit。
- GitHub Release 是 portable durable evidence：保存 distribution、checksum、非空 SBOM、source metadata，並在能力允許時加 attestation。
- Release consumer 與 registry publisher 驗 repository、tag、source digest、artifact digest 與 signer workflow identity。
- PyPI／npm publishing 只供生成專案按語言 opt-in；沒有 package owner、license 或 trusted publisher 時不宣稱已啟用。Root CLI 沒有 PyPI 發布需求，只隨 GitHub Release 交付，release prompt 以 exact commit 從 canonical repository 執行。
- 容器交付只為已有產品 Containerfile 的既有 repo 選配。`verify` 模式僅在 PR build、啟動與掃描；`ghcr` 模式才從已驗證 release source 建置一次、保存相同 image bytes，發布 GHCR 後附加 provenance／SBOM 並以 digest 重跑 smoke test。非容器 repo 不產生 job 或 registry write permission。
- Dependabot 保留為能觸發既有 checks 的 native update identity；pnpm 等待與 publisher trust、OSV、Gitleaks、CodeQL 各負責不同風險。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Superseded | 固定用 `GITHUB_TOKEN` 建 Release PR | [#64](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/64) → [#123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123)／[#128](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/128) |
| Superseded | 只在 ephemeral checkout 改版本後發布 | [#98](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/98) → [#142](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/142)／[#151](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/151) |
| Rejected | 以 Renovate 取代 native update automation，卻沒有可持續的高權限 identity | [#74](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/74)／[#110](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/110)／[#143](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/143) |
| Preserved | 上游 OSV reusable workflow 的實際 permission requirement 優先於靜態推測 | [#35](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/35)／[#92](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/92) |
| Preserved | Buildx cache、啟動測試、映像掃描與 attestation 只在真實 Containerfile 存在且明確選用時生成 | [#242](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/242) |
| Rejected | 從 dormant root PyPI job 推論公開發布與 license 決策，或把 CLI runtime 綁到生成專案 Python matrix | [#170](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/170), [#195](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/195), [#250](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/250) |
| Superseded | 為沒有 root PyPI 消費者的路徑維護 cross-registry build-once 邏輯 | [#203](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/203) → [#250](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/250) |

## Ownership 與驗證

Repository owner 決定公開授權與 registry identity；root 未經新決策不建立 registry job。Workflow 只取得各 job 所需最小權限。Source、release、artifact 與 consumption tests 必須能製造受控錯誤並證明 fail closed；live evidence 則在 Issue／PR 留下 run、tag 與 digest。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 長效 PyPI／npm token | 不採用；使用 trusted publishing OIDC |
| 只保留短期 Actions artifact | 不採用；正式證據附在 immutable Release |
| 用單一 security scanner 取代其他控制 | 不採用；來源、依賴、secret、SAST 與成品是不同風險 |
| 為早期 release 補造證據 | 不採用；缺失必須明記為歷史限制 |

## 重新評估條件

Owner 決定新增 root distribution channel、生成專案實際啟用 registry，或 GitHub attestation API 行為變更時，重新檢查整條 trust chain。任何優化都必須維持相同 source 與 artifact identity。
