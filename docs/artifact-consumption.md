# Artifact consumption contract and historical evidence

> [!IMPORTANT]
> 現行 release workflow 會建立並驗證 GitHub Release 成品，但沒有 release consumption 或 registry publisher Action。
> 本頁區分仍保留的本機安全契約與 2026-08 的一次性線上證據。

Attestation 只連結成品、來源與 build identity，不保證成品安全。只有真實消費者依核准
policy 驗證 repository、tag、digest 與 signer，並在不符時停止，才形成消費端門禁。

## Current state

| 路徑 | 狀態 | 現在保留的契約 |
| --- | --- | --- |
| 公版 GitHub Release | Active | `release.yml` 在受審查版本 PR 合併後發布 verified immutable Release |
| checksum 與 SPDX SBOM | Active | `scripts/release_bundle.py` 建立、下載並重驗 exact-tag 成品 |
| attestation consumption | Conditional | `scripts/verify_release_consumption.py` 及測試保留 fail-closed policy |
| PyPI／npm／GHCR | Product-owned | 模板不提供 publisher 選項或 job；需要 registry 時由產品另案設定 OIDC 與 environment |
| production deployment | Not applicable | 由產品自行定義環境、健康檢查、核准與復原 |

## Historical evidence

2026-08 的 `Release consumption verification` 曾下載當時最新的 immutable Release wheel，
核對 GitHub release-service signer、repository、repository ID、tag、commit 與 SHA-256，
並以竄改副本證明 digest mismatch 會被拒絕。該 run 只證明當時的 tag 與 workflow；它不
證明目前有 active build attestation、publisher 或 consumption gate。

當時公版是 GitHub Free private repository，無法產生 Actions build attestation，因此歷史
Release 使用 `https://dotcom.releases.github.com` signer。這不能用來宣稱 build workflow
identity 已驗證。

## 擴充條件

真實產品需要 registry 或 attestation 時，先在自己的 Issue／ADR 明列成品、唯一 publisher、OIDC
或 environment approval、最小權限、tag policy、失敗復原與消費端 policy，再用本機契約
建立薄 workflow。只上傳 Release assets 不算消費驗證，人工除錯指令也不算自動門禁。

完整 lifecycle 與歷史 Action disposition 見
[`adr/release-security-and-dependencies.md`](adr/release-security-and-dependencies.md)。
