# Version, release, delivery, and supply-chain posture ADR

- **狀態：**Accepted；#430 candidate 實作
- **最近複核：**2026-09-01
- **主要決策：**[#369](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/369)、[#429](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/429)、[#430](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/430)、[#439](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/439)

## 決策

CSARC 採一條可審查、可重跑，並依 GitHub 能力降級的發版路徑：

1. 工作 PR 以 Conventional Commits 表達 major／minor／patch／no-release 意圖。
2. `main` 每次前進先跑一次完整驗證，並以同一份 repo-local 規則計算下一版。
3. **Automatic：**GitHub 允許 Action 建立 PR 時，由 Release Please 依計算結果建立或更新版本 PR。
4. **Guided：**上層政策禁止 Action 建立 PR 時，維護者或 agent 在本機執行 `python3 scripts/release_policy.py prepare-candidate`，再以輸出的 branch／title 開一般 PR；命令只改版本檔與 CHANGELOG，不建立 PR、tag 或 Release。
5. **Blocked：**若 tag 或 GitHub Release 的必要權限不可用，流程留下失敗證據並停止，不改走另一個發布器。
6. 兩種候選都使用同一組可信 actor／commit、允許檔案、版本、CHANGELOG 與可打包性檢查；`GITHUB_TOKEN` 建立的 PR 若等待人工核准，原 release run 會直接驗證精確 SHA 並回寫 `Release / candidate` status。
7. 人審查並合併任一版本 PR 後，唯一的 `release.yml` 建立 tag、draft GitHub Release、成品、checksum、SPDX SBOM 與 release evidence；下載重驗成功後才公開且確認 immutable。

流程只使用短效 `GITHUB_TOKEN`，不要求 PAT、GitHub App、自架 runner 或付費 GitHub 方案。Organization 不允許 Actions 建立 PR 時只切換候選的建立方式；workflow 不可自行核准版本 PR，也沒有第二個 tag／Release writer。

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
| `csarc-repo-template` root | CSARC | candidate `release.yml` 預計發布模板／CLI 的 GitHub Release 成品；待預設分支實跑證明後才算 active |
| 新生成 repo | 該 repo 內的 CSARC baseline | Copier 產生同一個薄 workflow；版本從該 repo 的 `0.1.0` 獨立開始 |
| 既有 repo | product owner | Copier 不產生 `release.yml`、不按檔名猜測、不 dispatch 或覆寫既有發布流程 |

這個界線解決 #369 的重複 tag／Release owner 問題。Registry publishing 與 production-side artifact attestation 由 #439 判定零 active 消費者後移除設定面，不因 GitHub Release 啟用就自動取得 token 或 OIDC 權限。

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
| 版本與 CHANGELOG | Candidate／Guided | `release_policy.py`＋Release Please config／manifest | 自動或本機候選共用版本決策；組織目前禁止 Actions 建 PR |
| tag／GitHub Release | Candidate／Blocked | `.github/workflows/release.yml` | 版本 PR 合併後才建立；待 default branch live run 才能標 Active |
| source／語言成品 | Candidate | `scripts/release_bundle.py` | 選到的 Python、TypeScript、Rust 原生 package 加 source archive |
| checksum／SBOM／release evidence | Candidate | `scripts/release_bundle.py`＋Syft | 缺檔、竄改、錯 tag、錯 commit 與重跑測試；待 live run |
| registry publishing／production-side attestation | Removed | #439 | `container_mode`、`enable_release_attestations`、`enable_pypi_publishing`、`enable_npm_publishing` 已由 #439 移除設定面：零 active workflow 消費這些值，不留下承諾不了結果的選項；需要真實 registry 或 attestation 時另開 Issue 明列 owner、權限與執行者 |
| artifact consumption（消費端 attestation 驗證） | Conditional | `scripts/verify_release_consumption.py` | 與上列產出端設定無關；真實消費者明確採用後才是門禁 |
| repository delivery | Active | CI、PR policy、#429 branch model | 精確 PR head、review、分級驗證與 closing evidence |
| production deployment | Not applicable | consuming product | 必須由有真實 runtime 的產品自行定義 |

## 實作與測試

| 檔案 | 責任 |
| --- | --- |
| `.github/workflows/release.yml` | 一支 GitHub event／permission wrapper；root 與新生成 repo 的發布入口 |
| `scripts/verify-release-candidate` | 驗證自動或 guided 版本 PR 的身分、變更範圍與精確 SHA，再回寫 status |
| `scripts/release_policy.py` | 共用 Conventional Commit／版本決策；本機只產生候選檔，不寫 GitHub |
| `scripts/release_bundle.py` | build、tag identity、checksum、SPDX、evidence 與重跑驗證 |
| `tests/test_release_policy.py` | 版本與候選 trust boundary 正反例 |
| `tests/test_release_bundle.py` | 缺檔、竄改、錯 tag、重跑與 bundle identity |
| `tests/test_journey07_release.py` | workflow 權限、pin、ownership 與 archive disposition |

## Archive disposition

舊 Release Please、artifact handoff、release follow-up、promotion、release consumption、delivery maintenance 與 live-integration workflows 不整批恢復。新 `release.yml` 取代前三者的版本／發布責任；其餘維持人工、conditional 或 product-owned。已作 restore／replace／retire 決定的 archived copies 已刪除，歷史由 Git、Issue、PR、Release 與 Actions runs 保存。

舊 `scripts/test-release-follow-up-gates` 以 workflow YAML 作測試來源，會複製規則且維護成本高，已由 `release_policy.py`、`verify-release-candidate` 與 Python tests 取代。`delivery-maintenance.yml` 不恢復：只有明列真實依賴時才同步特定 delivery branch，不在每次 `main` 前進時 fan-out 寫入所有分支。

## 歷史 Action 逐項複核（#64–#426）

以下逐一回答：原問題是否仍存在、是否已由後續 Issue 解決、是否仍屬本產品責任、是否有更小的 native／repo-local 做法、權限與 secret 是否最小、是否 idempotent／fail closed、是否能在目前 GitHub 方案下驗證、維護成本是否合理。狀態只用 preserved（能力保留且仍是唯一實作）、superseded（被後繼設計取代）、one-time evidence（一次性事件，不是常駐能力）三類；沒有 issue 落在「still applicable 待辦」，因為 current-state 契約已把每項未解決缺口顯式標成 candidate／conditional／blocked，不留隱性 TODO。

| Issue | 狀態 | 理由 |
| --- | --- | --- |
| [#64](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/64) Run release-please with the default token | superseded | 原問題（用哪個 token 建版本 PR）已不存在：`GITHUB_TOKEN` 建 PR 的假設先被 #123 的 adaptive release mode 取代，#142 再取代 ephemeral version materialization，現由本 ADR 的 Automatic／Guided 雙路徑取代整條決策鏈。單一 `release.yml`＋`release_policy.py` 是唯一 native repo-local 實作，權限維持短效 `GITHUB_TOKEN`，可由 `tests/test_release_policy.py` 驗證。 |
| [#98](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/98) Complete Release Please artifact handoff | superseded | 「artifact handoff」是獨立 workflow 銜接 Release Please 產出的舊設計；已由單一 `release.yml`＋`scripts/release_bundle.py` 直接在同一 job 內完成建置與發布取代，見上方「Archive disposition」。仍屬本產品責任，但責任已收斂到單一 workflow，維護成本下降。 |
| [#99](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/99) Add live workflow integration checks | superseded | `Live integration smoke` 已封存刪除（見 `docs/live-integration.md`），其驗證的 OSV／Release Please／handoff／governance drift 四項能力，現分別由各自 current-state 契約與 `tests/test_journey07_release.py` 承接；不再需要一支跨能力 smoke workflow，維護成本與權限面都更小。 |
| [#104](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/104) Verify attestations at artifact consumption | preserved（conditional） | 原問題仍存在（消費端要驗證 provenance），但尚無真實消費者採用，因此 `scripts/verify_release_consumption.py` 與其測試保留為 conditional 契約而非 active workflow——不取得 attestation／`id-token` 權限直到 #439 或真實消費者確認 owner。fail closed：無 evidence 時判定失敗，不預設信任。 |
| [#123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123) Select release behavior from GitHub Actions policy capabilities | preserved | 核心機制（依 organization policy／repository setting／token permission 分開回報並選擇 Automatic 或 Guided）直接是本 ADR 決策第 3–4 點的基礎，由 capability probe 延續實作，非重寫。 |
| [#142](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/142) Synchronize release metadata and repair historical records | one-time evidence | 「repair historical records」是針對當時既有資料的一次性回補，不是常駐能力；往後的版本／CHANGELOG 一致性改由 `release_policy.py` 在每次執行時即時計算，不需要重跑歷史修復。 |
| [#183](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/183) Batch releases at promotion boundaries | superseded | 「在 promotion 邊界批次發版」的前提（存在專屬 `promotion.yml`）已不成立：promotion 專用 workflow 判定不恢復（見 Archive disposition），現行模型是 #429 的 standalone／main-only 路徑加 #400 的 Milestone 交付批次，批次責任已轉移，不再需要獨立批次發版邊界。 |
| [#321](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/321) Complete the missing release after promotion | one-time evidence | 是針對舊 `promotion.yml` 特定事故的一次性補救；該 workflow 本身已退役，問題不會再以同一形式發生，不是需要常駐防範的能力。 |
| [#322](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/322) Enforce dependency cooldown and release SBOM evidence | superseded（部分） | GitHub 狀態為 `NOT_PLANNED`。SBOM 半部已由 #341 實作並保留（見下）；「dependency cooldown」半部從未實作且目前沒有 owner 認領，也沒有已知事故證明其必要性，維持 not planned，不在本次候選新增推測性能力。 |
| [#341](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/341) Generate release SBOMs with pinned Syft | preserved | 直接對應 current-state 契約「checksum／SBOM／release evidence」列，由 `scripts/release_bundle.py`＋pinned Syft 實作，`tests/test_release_bundle.py` 驗證缺檔／竄改／重跑。 |
| [#372](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/372) Suspend all CI and CD automation during Milestone 8 | one-time evidence | 是 Milestone 8 重建前的一次性封存動作，其結果（`archive/ci-cd/2026-08-27/` 快照）是本 ADR 與本表所有其他 disposition 判斷的既有基線，不是需要重跑的常駐流程。 |
| [#373](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/373) Document the development loop design contradictions | superseded | 指出的分支／流程矛盾已由 #426（分支生命週期）與 #429（standalone 路由）解決，現行「現行交付路徑」章節即是矛盾解決後的單一敘述，不再有並存的舊路徑文件。 |
| [#399](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/399) Separate work definition from merge guidance | preserved | 其責任分界（工作 PR 只關閉單項工作；版本／交付批次負責進入 `main`、正式版本與 Milestone 結案）直接寫入 `docs/ci-policy.md`「現行交付路徑」一節，是現行敘述的來源，不是待整合的舊決策。 |
| [#403](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/403) Make staged verification sets responsibility complete | preserved | 「交付驗證是 Issue／PR 驗證的超集合」原則仍是現行驗證分級（見「驗證分級與實測成本」章節）與 #458 精簡設計的共同前提，未被取代。 |
| [#406](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/406) Rewrite dependency security guidance and checks | preserved | 是 Dependency vulnerability 能力現行 owner；`scripts/verify-dependencies`、`tests/test_dependency_security.py` 與 `osv.yml` 都由其確立。狀態受限於 #407 同一則說明：候選尚未落地 `main`。 |
| [#407](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/407) Restore minimal dependency update and vulnerability automation | preserved | `osv.yml`＋`.github/dependabot.yml` 是其直接成果，見「Current automation」表；本 repository 因候選尚未落地 `main` 而標 candidate，新生成 repo 因 Copier 初始 commit 即落地而標 active——並非能力本身失效。 |
| [#426](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/426) Define branch lifecycle and cleanup rules | preserved | 直接對應 `docs/ci-policy.md`「現行交付路徑」與 `scripts/cleanup-worktrees`；固定 `dev/next`／`promote/next` 退役即是其規則的現行結果。 |

## Fallback

- GitHub 禁止 Actions 建 PR 時，在 `release/v<version>` 執行 `prepare-candidate` 並開 `chore(main): release <version>`；同一驗證仍不可略過。
- 版本候選失敗時修正來源 commit 並重新產生；不直接編輯 bot branch，也不由本機命令建立 tag／Release。
- draft 發布失敗可安全重跑；若 Release 已 immutable，只能驗證既有內容，不能覆寫。
- 需要 registry、production-side attestation 或部署時，#439 已移除設定面而非保留 conditional 選項；先開新 Issue／ADR 定義 owner、權限、復原與消費端驗證，不擴張這支 baseline workflow。
