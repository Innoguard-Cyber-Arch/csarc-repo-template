# Artifact consumption verification

產生 attestation 只證明成品有可驗證的來源聲明；消費端真的執行驗證並在失敗時停止，才形成門禁。

## 實際消費路徑

| 路徑 | 消費行為 | 強制驗證 |
| --- | --- | --- |
| 生成專案的 PyPI 發布 | `publish-python` 下載 build job 的 wheel／sdist，再發布到 PyPI | 同時啟用 release attestation 與 PyPI publishing 時，逐一執行 `gh attestation verify` |
| 生成專案的 npm 發布 | `publish-npm` 下載 build job 的 npm tarball，再發布到 npm | 同時啟用 release attestation 與 npm publishing 時，發布前執行 `gh attestation verify` |
| 公版 CLI Release smoke | `Release consumption verification` 下載最新 immutable Release 的 wheel，驗證後開啟壓縮檔 | `gh release verify` 驗簽，再檢查 repository、repository ID、tag、commit、artifact SHA-256 與 GitHub Release signer |

生成專案的 registry gate 會把 repository、`refs/tags/<tag>` 與 signer workflow 固定為目前 repo 的 `.github/workflows/release.yml`；`gh` 也會以本機檔案重新計算 digest。attestation 缺失、來源 repo／workflow 不符、ref 不符或 digest 不符都會讓發布 job 失敗。

公版目前是 GitHub Free private repo，不能產生 Actions build attestation。它的 immutable Release attestation 由 `https://dotcom.releases.github.com` 簽署，沒有 Actions workflow identity；因此 root-only smoke 明確驗證該 release-service signer，不能拿它宣稱已驗證 build workflow。生成專案在支援 artifact attestation 的方案上，才由 registry gate 強制驗證 Actions workflow identity。

## 條件與邊界

- 只有建立語言成品、啟用對應 registry publishing，而且啟用 release attestation 時，才產生 registry verification step。
- CI/CD-only profile 沒有語言成品或 registry 消費路徑，不產生空 verification job。
- 只附加 GitHub Release assets 是發布，不算消費；人工指令是除錯方式，不算自動門禁。
- 本模板沒有可泛化的部署目標，因此不新增通用 deploy workflow。產品有真實部署路徑時，應在部署下載成品後套用同一個 fail-closed 原則。

## 線上證據

從 Actions 手動執行 `Release consumption verification` 可指定 immutable release tag，留白則使用 latest。workflow 會保存成功驗證 JSON，再複製同名 wheel、修改內容並確認 digest mismatch 被拒絕；受控失敗若意外通過，整個 job 反而失敗。證據 artifact 保留 30 天。
