# Version, release, delivery, and supply-chain posture ADR

- **狀態：**Accepted；#430 candidate 實作
- **最近複核：**2026-09-01
- **主要決策：**[#369](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/369)、[#429](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/429)、[#430](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/430)、[#439](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/439)

## 決策

CSARC 採一條可審查、可重跑的自動發版路徑：

1. 工作 PR 以 Conventional Commits 表達 major／minor／patch／no-release 意圖。
2. `main` 每次前進先跑一次完整驗證；Release Please 再建立或更新版本 PR，同步精確版本與 CHANGELOG。
3. `GITHUB_TOKEN` 建立的 PR 不會觸發另一支 PR workflow，因此同一個 release run 直接驗證該 PR 的精確 SHA，並回寫 `Release / candidate` status。
4. 候選驗證只接受 Release Please 的 branch、可信 actor／commits 與允許檔案，再檢查版本一致、CHANGELOG 與可打包性；不重跑已在 `main` 完成的整套語言測試。
5. 人審查並合併版本 PR 後，workflow 從精確 tag 建立成品、checksum、SPDX SBOM 與 release evidence，先放入 draft GitHub Release。
6. workflow 下載並重新驗證全部 assets，成功後才公開 Release，並在有限時間內確認 immutable；失敗且仍可變更時回到 draft。

流程只使用短效 `GITHUB_TOKEN`，不要求 PAT、GitHub App、自架 runner 或付費 GitHub 方案。Repository 必須允許 GitHub Actions 建立 PR，但 workflow 不可自行核准版本 PR。

## 名詞邊界

| 用詞 | 在本專案的意思 |
| --- | --- |
| 版本意圖 | PR 標題表達相容性影響，不是精確版本號 |
| 正式版本 | Release Please 在受審查的版本 PR 同步 manifest、package metadata 與 CHANGELOG |
| 交付 | 受審查且已驗證的工作進入 `main`；尚不等於發版 |
| 發版 | 精確 tag、GitHub Release、明列成品、checksum、SBOM 與來源證據都完成 |
| 部署 | 成品進入真實 runtime，另需環境、健康檢查與復原責任；不屬本模板通用能力 |

## Ownership

| Repository 類型 | 唯一 release owner | 模板行為 |
| --- | --- | --- |
| `csarc-repo-template` root | CSARC | active `release.yml` 發布模板／CLI 的 GitHub Release 成品 |
| 新生成 repo | 該 repo 內的 CSARC baseline | Copier 產生同一個薄 workflow；版本從該 repo 的 `0.1.0` 獨立開始 |
| 既有 repo | product owner | Copier 不產生 `release.yml`、不按檔名猜測、不 dispatch 或覆寫既有發布流程 |

這個界線解決 #369 的重複 tag／Release owner 問題。Registry publishing 與 artifact attestation 是 #439 的選配能力，不因 GitHub Release 啟用就自動取得 token 或 OIDC 權限。

## Standalone 與 Hotfix

兩條路徑都可直接進 `main`，但目的不同：

| 項目 | 一般 standalone | Hotfix |
| --- | --- | --- |
| 適用條件 | 一張 Issue 可獨立審查、驗證與交付，沒有共同期限、批次驗收、跨 Issue 相依或獨立環境 | `main` 上的缺陷必須立即修正；不是一般工作的插隊標籤 |
| 提出 | 無里程碑的一般 Issue | 無里程碑 Bug Issue＋`bug`／`hotfix`；未公開安全問題改用 GitHub Security Advisory |
| Branch／PR | 從最新 `main` 建立 `type/<Issue>-*`，PR target `main` | 從最新 `main` 建立 `fix/<Issue>-*`，PR target `main` |
| 審查與驗證 | 正常 review；CI 依風險選 docs／fast／full | 另一人 review 且一律 full；緊急不能略過必要檢查 |
| 合併與證據 | closing keyword 關 Issue，保留 PR 與精確 head evidence | 另保留 rollback 說明與是否立即發版的決策 |
| 版本影響 | 依 Conventional Commit 決定 | `fix` 預設 patch；實際版本仍由版本 PR 審查後確定 |

當工作開始需要多張 Issue 同時完成、共同期限／版本、整批驗收、獨立 soak／canary，或下游工作必須等待同一批次，就在實作前改掛里程碑並走 `dev/m*`。單張複雜但仍可獨立驗收的 Issue 不必為了規模硬掛里程碑。

## 安全與可靠性

- 第三方 Actions 固定完整 commit SHA；job 明列最小權限、30 分鐘 timeout 與不取消既有 run 的 concurrency。
- workflow 只負責 GitHub event、權限與呼叫；版本、候選與 bundle 規則放在可於本機測試的 repo-local scripts。
- 候選 status 先設 pending；fetch、API、allowlist、版本或打包任一步失敗，都保證回寫 failure。
- 版本 PR 只能修改 release config 允許的機械版本檔；不允許任意程式碼藏進 bot PR。
- 發布只接受指向目前 `HEAD` 的 SemVer tag；不移動 tag，也不接受 dirty Rust package。
- draft 重跑先清除舊 assets，避免改名或多餘檔案殘留；checksum 必須剛好涵蓋全部 bundle。
- Release 公開後以 bounded retry 等待 GitHub immutable 狀態與 `gh release verify`，避免 eventual consistency 假失敗。
- 已公開且 immutable 的同 tag 重跑只下載與重驗，不重建或覆寫資產。

判斷依據包括 [Semantic Versioning](https://semver.org/)、[Keep a Changelog](https://keepachangelog.com/en/1.1.0/)、[Release Please](https://github.com/googleapis/release-please)、[GitHub token trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)、[secure use](https://docs.github.com/en/actions/reference/security/secure-use) 與 [immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)。

## Current-state 契約

| 能力 | 狀態 | Canonical source | 證據／失敗邊界 |
| --- | --- | --- | --- |
| 版本意圖 | Active | PR policy／Conventional Commits | PR title regression |
| 版本與 CHANGELOG | Active | Release Please config／manifest | 候選精確 SHA、允許檔案與版本同步測試 |
| tag／GitHub Release | Active | `.github/workflows/release.yml` | 版本 PR 合併後才建立；draft 到 immutable 的 fail-closed flow |
| source／語言成品 | Active | `scripts/release_bundle.py` | 選到的 Python、TypeScript、Rust 原生 package 加 source archive |
| checksum／SBOM／release evidence | Active | `scripts/release_bundle.py`＋Syft | 缺檔、竄改、錯 tag、錯 commit 與重跑測試 |
| registry／attestation | Conditional | #439 | 未核准前不取得 registry token、`id-token` 或 attestation 權限 |
| artifact consumption | Conditional | `scripts/verify_release_consumption.py` | 真實消費者明確採用後才是門禁 |
| repository delivery | Active | CI、PR policy、#429 branch model | 精確 PR head、review、分級驗證與 closing evidence |
| production deployment | Not applicable | consuming product | 必須由有真實 runtime 的產品自行定義 |

## 實作與測試

| 檔案 | 責任 |
| --- | --- |
| `.github/workflows/release.yml` | 一支 GitHub event／permission wrapper；root 與新生成 repo 的發布入口 |
| `scripts/verify-release-candidate` | 驗證 Release Please PR 身分、變更範圍與精確 SHA，再回寫 status |
| `scripts/release_policy.py` | Conventional Commit、版本來源、候選 branch／actor／commit／allowlist 規則 |
| `scripts/release_bundle.py` | build、tag identity、checksum、SPDX、evidence 與重跑驗證 |
| `tests/test_release_policy.py` | 版本與候選 trust boundary 正反例 |
| `tests/test_release_bundle.py` | 缺檔、竄改、錯 tag、重跑與 bundle identity |
| `tests/test_journey07_release.py` | workflow 權限、pin、ownership 與 archive disposition |

## Archive disposition

舊 Release Please、artifact handoff、release follow-up、promotion、release consumption、delivery maintenance 與 live-integration workflows 不整批恢復。新 `release.yml` 取代前三者的版本／發布責任；其餘維持人工、conditional 或 product-owned。已作 restore／replace／retire 決定的 archived copies 已刪除，歷史由 Git、Issue、PR、Release 與 Actions runs 保存。

舊 `scripts/test-release-follow-up-gates` 以 workflow YAML 作測試來源，會複製規則且維護成本高，已由 `release_policy.py`、`verify-release-candidate` 與 Python tests 取代。`delivery-maintenance.yml` 不恢復：只有明列真實依賴時才同步特定 delivery branch，不在每次 `main` 前進時 fan-out 寫入所有分支。

## Fallback

- GitHub Actions 暫時不可用時，可在本機跑相同 repo-local 驗證並保存輸出，但 required check 不因此略過。
- 版本候選失敗時修正來源 commit 或重新產生版本 PR，不直接編輯 bot branch 來繞過 allowlist。
- draft 發布失敗可安全重跑；若 Release 已 immutable，只能驗證既有內容，不能覆寫。
- 需要 registry、attestation 或部署時，先由 #439 或產品自己的 Issue／ADR 定義 owner、權限、復原與消費端驗證，不擴張這支 baseline workflow。
