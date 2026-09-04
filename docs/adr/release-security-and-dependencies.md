# Version, release, delivery, and supply-chain posture ADR

- **狀態：**Accepted
- **日期：**2026-09-01
- **備註：**#430 candidate 實作
- **來源 Issues：**[#369](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/369)、[#429](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/429)、[#430](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/430)、[#439](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/439)
- **實作 PRs：**[#448](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/448)、[#463](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/463)、[#471](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/471)

## 問題與限制

CSARC 過去在版本、發版與供應鏈責任上有多套並存或半途而廢的設計（見下方「歷史 Action 逐項複核」）：曾用固定 token 假設觸發 Release Please（#64）、獨立 artifact handoff workflow（#98）、跨能力的 live smoke workflow（#99）、獨立 promotion／delivery-maintenance workflow（#183、#321、#372）。這些設計各自解決局部問題，但疊加後造成重複的 tag／Release owner（#369 具體描述的問題）、多套規則互相漂移、以及在 GitHub 方案或政策改變時無法一致降級的風險。

本 ADR 要解決的問題：需要單一、可審查、可重跑，且能依當下 GitHub 能力（organization policy、repository setting、token permission）明確降級的發版路徑，取代前述並存設計，同時把既有 repo 保留的 product-owned release workflow 與 CSARC 自己的 release 責任清楚分開（見 #369）。

已知限制：

- 流程只使用短效 `GITHUB_TOKEN`，不引入 PAT、GitHub App、自架 runner 或付費 GitHub 方案，因此 Free organization private repo 等能力受限的方案只能走 Guided，無法自動化到 Automatic。
- Registry publishing、production-side artifact attestation 與部署不在本 ADR 範圍內；#439 已判定零 active 消費者並移除相關設定面，真實需求需另開 Issue／ADR。
- 本 ADR 只涵蓋 repository delivery 到 GitHub Release 的邊界，不涵蓋成品進入真實 runtime 之後的責任。

## 決定

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
| `.github/workflows/release.yml` | 一支 GitHub event／permission wrapper；root 與新生成 repo 的發布入口；發布階段呼叫 `scripts/publish-release`，不保留自己的一份邏輯 |
| `scripts/publish-release`（#589） | 發布階段的單一實作：`stage`／`resolve`／`publish`／`rerun-verify` 子命令，涵蓋驗證並暫存已合併候選、判定 tag／Release 狀態、build 成品與 SBOM、上傳並公開、驗證重跑，以及發布失敗時把仍可變的 Release 收回 draft；`release.yml` 與本機／agent 執行呼叫同一份腳本 |
| `scripts/install-syft`（#589） | 本機／agent 發布路徑產生 SPDX SBOM 的直接 CLI 等效：抓取與 `release.yml` 的 `anchore/sbom-action` 相同 pin 版本的 Syft 二進位並驗證 checksum |
| `scripts/verify-release-candidate` | 驗證自動或 guided 版本 PR 的身分、變更範圍與精確 SHA，再回寫 status |
| `scripts/release_policy.py` | 共用 Conventional Commit／版本決策；本機只產生候選檔，不寫 GitHub；`detect`／`select_release_mode` 的 Guided 觸發條件（#589）已擴充為政策阻擋或維護者／agent 明示的 `--operator-reason` 兩者之一 |
| `scripts/release_bundle.py` | build、tag identity、checksum、SPDX、evidence 與重跑驗證 |
| `tests/test_release_policy.py` | 版本與候選 trust boundary 正反例；Guided 模式 operator override 觸發條件與 fail-closed 邊界（#589） |
| `tests/test_release_bundle.py` | 缺檔、竄改、錯 tag、重跑與 bundle identity |
| `tests/test_release_publish.py`（#589） | 對 mocked `gh` 與真實 Git fixture 驅動 `scripts/publish-release` 的行為回歸：staging 成功／fail-closed、state 判定、發布成功、發布失敗回退 draft、已發布重跑不重建 |
| `tests/test_journey07_release.py` | workflow 權限、pin、ownership 與 archive disposition；`release.yml`／`release.yml.jinja` 呼叫 `scripts/publish-release` 而非保留自己一份 bash 的來源層級驗證（#589） |
| `.github/workflows/dependabot-auto-merge.yml` | 只鎖定 `dependabot[bot]` 開出的 PR；minor／patch 排入 GitHub 原生 auto-merge 佇列，major 加標籤／留言、不合併 |
| `tests/test_dependabot_auto_merge.py` | 觸發條件、job 層級 actor 閘門、權限、pin 與 minor/patch／major 分流的 workflow 邏輯回歸測試 |

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

## Dependabot 自動合併取代 #322 cooldown 半部結論（#557，2026-09-03）

[#322](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/322) 上方列為 superseded（部分）：「dependency cooldown」半部（發行後延遲才開 PR）已由 #341 的 SBOM 與 #407 的
`.github/dependabot.yml` `cooldown.default-days: 3` 落地保留；但「cooldown 滿足後、checks 通過即可自動合併」這一段，
#322 當時判定維持 not planned——理由明列為「從未實作且目前沒有 owner 認領，也沒有已知事故證明其必要性」。本節不改寫、不刪除上方那一列，
只記錄取代其中這一段門檻：[#557](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/557) 提供 #322 當時缺的兩個前提——
明確 owner（維護者 matheme-justyn，同時是 Issue assignee）與明確事故（#543／#544／#545 三張 Dependabot PR 開出 2 小時仍無人處理的真實 backlog，
不是推測性需求）。

決定：新增 `.github/workflows/dependabot-auto-merge.yml`，只在 `github.event.pull_request.user.login == 'dependabot[bot]'`
時執行（不是可被偽造的 `github.actor`，見 zizmor `bot-conditions` audit），於 `pull_request`
（opened／synchronize／reopened）用 `dependabot/fetch-metadata` 讀 update-type；minor／patch 呼叫
`gh pr merge --auto --squash` 排入 GitHub 原生 auto-merge 佇列（不是自建輪詢腳本），major 只加 `needs-manual-review`
標籤並留言，不合併。這只是**排入**佇列，不是立即合併或繞過任何既有把關——實際合併仍完全由 GitHub 依
`policies/rulesets.json` 的 branch protection（1 個 code owner approving review）與既有 `title`／`promotion`／`verify`
required checks 全部通過後才執行；本決定沒有調整、放寬或繞過上述任何規則。

範圍邊界：本節只取代「PR 開出後如何自動合併」這一段判斷，不重新開放整個 #322，也不影響已經 preserved 的 cooldown／SBOM
半部——`.github/dependabot.yml` 的 `cooldown.default-days: 3` 維持原樣，不因本節新增而重新設定或延長。同步下發 `template/`
（新 workflow 與 `policies/labels.json` 的 `needs-manual-review` 標籤定義），下游生成專案取得同一份政策；`docs/ci-policy.md`
沿用既有「Current automation」表的 candidate／active 判斷慣例，待落地 `main` 並有 live run 證據後再登錄，不在本節預先宣告 active。

## 發版不依賴 Actions 健康度的本機 fallback（#589，2026-09-03）

2026-09-03 的實際事故（#587）證明「發版」目前完全綁在 `release.yml` 這一支 workflow 是否能在
GitHub Actions 上成功執行：M8 promotion 後，`docs/index.html` 過期讓 full-tier 驗證卡住，`main`
上每一次 push 觸發的 `release.yml` run 全部失敗，加上同一天稍早出現的 `pull_request` webhook 投遞
間歇性異常，讓「能不能發版」完全停擺超過 8 小時、沒有人自動被通知，直到人工檢查 Releases 頁面才
發現。既有的 Actions 額度 fallback（見 [staged-delivery-and-verification
ADR](staged-delivery-and-verification.md)）解決的是不同的觸發條件：額度用盡有 GitHub 回傳的明確
錯誤訊息（zero-step billing block），可以機械式偵測；本節處理的觸發條件——hosted runner 卡住、
webhook 沒有投遞、或其他導致 Actions 本身不健康的狀況——沒有對應的機械式訊號，只能由人或 agent
主動判斷後啟用，這是本節與額度 fallback 在觸發機制上的根本差異。

**決定：** 沿用本 ADR 決定第 4 點既有的 Guided 模式，只把它的啟用條件從單一觸發（「上層政策禁止
Action 建立 PR」）擴大為兩個觸發之一：原本的政策阻擋，或維護者／agent 判斷 Actions／webhook 目前
不可信任。兩者共用完全相同的機制與信任邊界：`python3 scripts/release_policy.py prepare-candidate`
在本機計算版本與 CHANGELOG，人或 agent 開一般 PR，經過與其他 `main` PR 相同的 review 才能合併——
本機執行不能成為省略審查的手段，也不構成第二個 tag／Release writer。合併後把 `release.yml` 原本
內聯在「Validate and stage the merged version candidate」到「Keep a failed mutable release in
draft」之間的 bash 抽成 `scripts/publish-release`（`stage`／`resolve`／`publish`／`rerun-verify`
子命令），`release.yml` 與本機／agent 執行的路徑呼叫同一份實作，不維持兩套邏輯；SBOM 產生同樣
只有一份規則：`release.yml` 仍呼叫 `anchore/sbom-action`（pin 版本不變），`scripts/publish-release`
在該檔案不存在時（本機沒有前置的 Actions 步驟）改用 `scripts/install-syft` 抓同一個 pin 版本的
Syft 二進位直接呼叫 `syft scan dir:. -o spdx-json=<output>`，兩條路徑產生的 SBOM 接受同一份
`scripts/release_bundle.py verify` 驗證，不是兩套互相可能漂移的規則。

**代價（不能只講好處）：**

- **放棄 hosted runner 的乾淨、一致環境保證。** 本機執行的環境不由 GitHub 控管；只有本機 `full`
  驗證全綠才能視為等同 hosted 的證明強度。
- **需要本機或執行者持有具備 admin／write 權限的長效憑證，而不是 Actions 短效 `GITHUB_TOKEN`。**
  這不是為所有 CSARC-owned repo 新增一項標準要求——`scripts/apply-repository-settings.sh apply`
  本來就已經要求 repo admin 用自己的 `gh` 身分執行；本節只是讓同一位已經持有這個權限的維護者，
  多一個「用同一身分完成發版」的選項。
- **沒有 merge 後自動觸發，需要人或排程主動執行。** 需要另外一道獨立排程的存量檢查偵測「`main`
  已經前進但過去 N 小時內沒有成功的 `release.yml` run 或本機發版紀錄」，取代目前完全仰賴人工檢查
  Releases 頁面才會發現的狀態；這道檢查因範圍與時間考量從 #589 拆分成獨立追蹤（見
  [#605](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/605)），本節本身不
  包含它。
- **本機執行結果的可稽核性不如 hosted run 的公開 log。** 緩解方式是強制在合併說明或 Issue 留言
  記錄執行者、commit SHA、指令與結果。
- **local-vs-hosted 邏輯漂移風險。** 緩解方式是本節設計的第一原則——單一 repo-local 腳本被兩種
  呼叫方式共用，不維持兩套實作。

**明確的非目標：** `verify`／`title`／`promotion` 三個 required status check 仍然、也必須繼續只由
hosted Actions 產生——它們的價值來自 GitHub 自己信任這份報告，本機執行無法滿足這個信任邊界，本節
不主張、也沒有把這三者改成可本機執行。CodeQL 上傳到 GitHub 原生 code-scanning 介面同樣不在本節
適用範圍。GitHub Actions 仍是預設／建議路徑，一般情況下仍建議走 hosted `release.yml`；本機路徑是
明確的 backup，不是取代。本節也不新增 Copier 選項：既有的 `release_ownership`
（`csarc-owned`／`product-owned`／`verification-only`）已經正確路由這個能力——`release.yml`／
`release.yml.jinja` 只下發給 `csarc-owned` 生成 repo；`scripts/publish-release` 與擴充後的 Guided
模式一旦存在於這兩個檔案，就隨同一套機制自動下發，不需要、也不新增第二個選配旗標。

## 評估過的替代方案

- **繼續維護多支專用 workflow**（獨立 artifact handoff、promotion、delivery-maintenance、live-integration smoke）：否決。這是本 ADR 要取代的既有設計，見上方「歷史 Action 逐項複核」；多支 workflow 各自維護規則、各自可能與 repo-local script 邏輯漂移，且權限面各自獨立，稽核與維護成本都高於單一 `release.yml`＋repo-local scripts 的組合。
- **固定假設 `GITHUB_TOKEN` 一定能建立 PR，不做能力降級**（#64 的原始設計）：否決。Free organization private repo 等方案本來就可能停用 Actions 建 PR；固定假設會讓流程在該方案下直接不可用，而不是明確降級為 Guided。
- **批次於 promotion 邊界統一發版**（#183，靠專屬 `promotion.yml`）：否決。前提是恢復已判定不恢復的 promotion workflow；現行 #429 standalone／main-only 路徑加 #400 的 Milestone 批次交付已承接原本想解決的「批次」需求，不需要獨立的批次發版邊界或額外 workflow。
- **在 CSARC 側直接串接 registry publishing／production-side attestation**：否決（見 #439）。零 active 消費者的情況下維持這些能力，只會留下「看起來能用、實際不會產生結果」的設定選項，違反本 ADR「不留下承諾不了結果的選項」的安全原則；有真實需求時應由消費端產品自行決定 owner 與權限，而非公版預先假設。

## 重新評估條件

以下任一情況發生時，應重新檢視本 ADR 的決定而非局部繞過：

- GitHub 改變 Actions 建立 PR 的預設或可控政策，使 Automatic／Guided 的能力降級判斷條件本身失效或需要新增第三種模式。
- 有消費端產品提出真實的 registry publishing 或 production-side attestation 需求，需要決定是否、以及如何在不違反「單一 tag／Release writer」原則下擴充 `release.yml` 或另開專用 workflow。
- `release.yml` 的候選驗證（`scripts/verify-release-candidate`）或 bundle 驗證（`scripts/release_bundle.py`）在 default branch 首次 live run 後發現與本 ADR 假設不符的落地行為，需要更新 Current-state 契約或決定本身。
- 既有 repo 保留的 product-owned release workflow 出現與本 ADR 的 ownership 邊界（#369）衝突的新情境，例如 product workflow 本身改變 trigger 或 input contract，需要重新檢視 #369 的 ownership schema 是否仍夠用。

## Fallback

- GitHub 禁止 Actions 建 PR 時，在 `release/v<version>` 執行 `prepare-candidate` 並開 `chore(main): release <version>`；同一驗證仍不可略過。
- 版本候選失敗時修正來源 commit 並重新產生；不直接編輯 bot branch，也不由本機命令建立 tag／Release。
- draft 發布失敗可安全重跑；若 Release 已 immutable，只能驗證既有內容，不能覆寫。
- 需要 registry、production-side attestation 或部署時，#439 已移除設定面而非保留 conditional 選項；先開新 Issue／ADR 定義 owner、權限、復原與消費端驗證，不擴張這支 baseline workflow。
