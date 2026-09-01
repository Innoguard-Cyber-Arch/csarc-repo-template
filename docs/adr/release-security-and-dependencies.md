# Version, release, delivery, and supply-chain posture ADR

- **狀態：**Accepted；2026-08-24 的自動發版設計已由本次 current-state 盤點限縮
- **最近複核：**2026-09-01
- **來源 Issues：**[#29](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/29), [#30](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/30), [#35](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/35), [#36](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/36), [#64](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/64), [#98](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/98), [#99](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/99), [#104](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/104), [#123](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/123), [#142](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/142), [#183](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/183), [#321](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/321), [#322](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/322), [#341](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/341), [#369](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/369), [#372](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/372), [#373](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/373), [#399](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/399), [#400](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/400), [#401](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/401), [#403](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/403), [#406](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/406), [#407](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/407), [#426](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/426), [#428](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/428), [#429](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/429), [#430](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/430), [#439](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/439)

## 盤點基線

| 來源 | 2026-09-01 觀察 | 判讀方式 |
| --- | --- | --- |
| live default branch | `main` at `42834ea5f2f2f35877d7c931bd2ffc3b16338862` | 已交付現況；用 GitHub API 與 active files 交叉核對 |
| Milestone 8 candidate | `dev/m8-hugo-docs` at `be002c7bca21a06689b9e783c22049f5e2f45155` | #430 的 integration base；已包含 #429／PR #432，不提前當成 main |
| local checkout | 未提交差異存在 | 只當差異線索，不當成已交付能力 |
| root | 本模板 repository 自身的設定、scripts、tests 與文件 | 不自動等同生成專案能力 |
| `template/` | Copier 下發給新／既有專案的產品 | 只有實際產生且通過生成測試的內容可宣稱支援 |
| generated fixtures | create／adopt／update 的暫存專案 | 用來證明條件式輸出與產品內容 preservation |
| `archive/ci-cd/2026-08-27/` | 尚待其他 Journey 處置的舊 workflow | #430 已移除判定不恢復的版本／交付 YAML；Git／Issue／PR／runs 保存其歷史 |

## 決策摘要

截至 2026-09-01，版本與發版採 **manual**，不是 adaptive release：

- 合併到 `main` 是 repository delivery，不等於已建立版本或 Release。
- PR 標題只表達 SemVer 意圖；精確版本、CHANGELOG、tag、成品與 GitHub Release 必須由同一張受審查的發版變更一起配置。
- `.github/workflows/` 沒有版本配置、Release Please、promotion、成品發布、release consumption 或 live-integration workflow。沒有目前 run 的能力不得標成 active。
- [#369](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/369) 確認生成專案的 release ownership 前，不恢復發版 Action，也不假設檔名等於產品授權。
- `scripts/release_assets.py`、`scripts/verify_release_consumption.py` 與測試保留為 **conditional** 的本機安全契約；只有真正的 owner、成品與 workflow 接上後才會成為交付流程。
- CSARC 沒有 production target，因此只談 repository artifact delivery，不宣稱 deployment、監控或 rollback automation。

這個決定刻意讓發版寫入自動化為零。它保留既有安全驗證，又不新增 token、App、重複 tag owner 或無法由目前 repository 證明的成功宣稱。

## 統一用詞

| 用詞 | 在本專案的意思 | 不是什麼 |
| --- | --- | --- |
| 版本意圖（version intent） | PR 標題表達相容性影響：major、minor、patch 或 no-release | 精確版本號 |
| 正式版本（version materialization） | 在已審查變更中同步 manifest、package metadata、CHANGELOG 與 README marker | CI checkout 內的暫時改檔 |
| 發版（release） | 一個不可變 tag 加上 GitHub Release、明列的成品與可驗證證據 | 單純合併到 `main` |
| 交付（delivery） | 把受審查且已驗證的工作送入權威分支；若有消費者，再交付核准 Release | 一定等於發版 |
| 部署（deployment） | 把產品送入真實 runtime environment 並具備健康檢查與復原責任 | 本模板目前提供的能力 |
| 成品證據（artifact evidence） | 成品 checksum、SBOM、來源 commit、build identity 與必要 attestation | 「workflow 顯示綠燈」的同義詞 |

## 最佳實踐基準

本次判斷採官方或一手來源，觀察日均為 2026-09-01：

- [Semantic Versioning 2.0.0](https://semver.org/)：版本表達公開介面的相容性，已發布版本不可改寫。
- [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)：changelog 面向人、保留 Unreleased，且不是原樣傾倒 Git log。
- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)：workflow／job 明列最小 `permissions`、`timeout-minutes` 與適當的 `concurrency`；不能把 concurrency 當成 FIFO queue。
- [GitHub secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)：第三方 Action 鎖定完整 commit SHA，寫入 credential 不交給未受信任程式碼。
- [GitHub immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)：先建立 draft、上傳全部 assets，再發布；發布後 tag 與 assets 不可修改。
- [GitHub artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)：attestation 連結成品、來源與 build instructions，但不保證成品安全；消費端仍要定義並驗證 policy。
- [GitHub deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)：需要人類核准的發布／部署使用 environment protection rules；沒有真實 environment 時不建立空 gate。
- [GitHub flow](https://docs.github.com/en/get-started/using-github/github-flow)：可獨立交付的工作從預設分支建立短分支，經 PR review 後回到預設分支；不需要先建立長期整合分支。
- [GitHub repository security advisories](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/about-repository-security-advisories)：尚未公開的安全修補使用私密協作與 temporary private fork，不先建立公開 hotfix Issue。
- [Release Please](https://github.com/googleapis/release-please)、[semantic-release](https://github.com/semantic-release/semantic-release) 與 [Changesets](https://github.com/changesets/changesets)：三者分別偏向可審查的版本 PR、成功 CI 後全自動發布，以及以 changeset 檔管理多套件版本。工具選擇不能取代 owner、approval、artifact 與 consumption 契約。

任何要恢復的 Action 都必須另外證明：單一 owner、最小權限、完整 SHA pinning、固定 timeout、可重跑／冪等、併發不產生較舊版本、失敗時 fail closed、repo-local 入口、可接受的 runner 成本，以及目前 GitHub 方案上的正向與受控失敗 run。

### Standalone 與 Hotfix 的最佳實踐

兩條路徑都直接進 `main`，但目的不同，不能只靠 branch 名稱互換：

| 項目 | 一般 standalone | Hotfix |
| --- | --- | --- |
| 適用條件 | 一張 Issue 可獨立審查、驗證與交付，且沒有共同期限、批次驗收、跨 Issue 相依或獨立環境 | `main` 上的缺陷必須立即修正；不是一般工作的插隊標籤 |
| 提出 | 無里程碑的一般 Issue；若需求變成整批工作，實作前加入適當里程碑 | 無里程碑 Bug Issue＋`bug`／`hotfix`；未公開安全缺陷使用 GitHub Security Advisory |
| Branch／PR | 從最新 `main` 建立 `type/<Issue>-*`，target `main`，使用標準 PR title 與 `Closes #N` | 從最新 `main` 建立 `fix/<Issue>-*`，`fix(scope): summary` target `main`，使用 `Fixes #N`／`Closes #N` |
| 審查與驗證 | 正常 review；CI 依變更內容選 docs／fast／full | 正常 review；一律 full，緊急不能取代檢查或另一人的核准 |
| 合併與結案 | 精確 head 合併後由 GitHub native closure 結束 Issue；#401 補齊其他 work routes | 同樣由 native closure 結束 Issue；保存 PR、commit SHA、full run 與 rollback 說明 |
| 版本化 | 合併是 repository delivery，不一定發版 | `fix` 預設宣告 patch 意圖；`!` 表示 breaking，但精確版本、CHANGELOG、tag 與 Release 仍由唯一 release owner 另行核准 |

Standalone 必須改掛里程碑的判斷不是「工作看起來很大」，而是出現需要共同治理的事實：
多張 Issue 要同時完成、共同期限／版本、整批驗收、獨立 soak／canary，或下游工作必須等待同一
批次。這些條件任一成立，就改用 `dev/m*`；單純一張複雜但可獨立驗收的 Issue 仍可直接進
`main`。

## Current-state 契約

狀態定義：**active** 有現行檔案與目前事件證據；**manual** 由人執行且沒有專用 Action；**conditional** 有可測契約但尚未接上 owner／trigger；**archived** 只留歷史 snapshot；**retired** 不再是支援路徑；**blocked** 有另一張 Issue 擁有未決前提；**not applicable** 不屬本產品。

| 生命週期 | 狀態 | Canonical file／owner | Trigger／permission | 輸入、輸出、測試與 live evidence |
| --- | --- | --- | --- | --- |
| 版本意圖 | active | `scripts/validate-pr-policy`；Journey 06 | `pull_request`；workflow 的 metadata write 只用於既有 Issue／PR 同步 | PR title → major／minor／patch／no-release；`scripts/test-pr-policy`；[run 33486951833](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33486951833) |
| 正式版本配置 | manual | `.release-please-manifest.json`、`version.txt`、`pyproject.toml`、`uv.lock`、README marker；CSARC maintainer | 一張人工 PR；不使用 release write token | 同一 commit 的精確版本；`tests/test_release_policy.py` 驗同步與錯誤情境，沒有 current hosted run |
| CHANGELOG | manual | `CHANGELOG.md`；CSARC maintainer，生成專案則由產品 owner | 與版本相同的人工 PR | 面向人的 release note／`Unreleased` 內容；review 與版本同步測試 |
| tag | blocked | #369 決定 CSARC-owned 或 product-owned owner | 無 active trigger 或 `contents: write` | 不建立／移動 tag；歷史 `v0.12.2` 只證明當時 commit |
| 成品 build | conditional | 產品 build owner；`scripts/release_assets.py` | 目前只可本機明確呼叫；無 publisher permission | 明列 wheel／sdist／npm tarball／Cargo package 或 source archive；`tests/test_release_assets.py` |
| checksum | conditional | `scripts/release_assets.py`；產品 build owner | 與真正成品同一執行；無 active Action | `SHA256SUMS` 與竄改失敗測試 |
| SBOM | conditional | Journey 05 規則＋`scripts/release_assets.py` | 與真正成品同一執行；無 active Action | SPDX 2.3、root package、dependency graph 與 exact-source 驗證 |
| attestation | conditional | 未來 publisher | 需獨立核准的 `id-token: write`／`attestations: write` job | 來源聲明，不宣稱成品安全；目前沒有 current run |
| GitHub Release | blocked | #369 決定唯一 owner | 無 active trigger 或 write permission | 最新歷史證據是 immutable [v0.12.2](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/releases/tag/v0.12.2)，不代表現行自動化 |
| artifact consumption | conditional | 真實消費者；`scripts/verify_release_consumption.py` | 消費者明確呼叫；目前無 active Action | repository／tag／digest／signer policy；`tests/test_release_consumption.py` 正反向測試 |
| delivery 到 `main` | active／manual | `.github/workflows/ci.yml`、`.github/workflows/pr-policy.yml`；Journey 06／08 與 reviewer | PR 事件；CI `contents: read`，PR policy 使用最小 metadata 權限 | 精確 PR head 的 policy 與分級驗證；[CI run 33486217138](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/33486217138) |
| standalone delivery | active | `scripts/validate-pr-policy`、`scripts/ci_tier.py`；Journey 06／07 | 無里程碑 Issue 的 topic PR 直接 target `main`；一般 review 與風險分級 | `Closes #N` 由 GitHub native closure 結案；若需要整批驗收、共同期限、跨 Issue 相依或 canary，實作前改掛里程碑 |
| hotfix delivery | active | 同上；reviewer 與 release owner 分責 | 無里程碑 Bug Issue＋`bug`／`hotfix`；`fix/*` target `main`；full verification | PR、head SHA、full run、rollback 與 release decision；安全 embargo 改用 repository security advisory；合併不等於已發版 |
| Milestone 結案 | blocked | #400；Journey 09 | `milestone-lifecycle.yml` 尚未驗完整 approval／closure contract | 完成時人工確認 evidence；提前終止先移轉或取消未完成 Issue |
| 工作 Issue 結案 | blocked | #401；Journey 06 | 現有 PR policy 尚未自動完成 | 由工作 PR 負責，不由發版流程重複關閉 |
| branch cleanup | active／manual | #426；GitHub setting 與 `scripts/cleanup-worktrees` | merged branch 自動刪除＋維護者明確執行 | 不刪 dirty、locked、unmerged 或不可驗證 worktree；shell regression |
| registry publish | not applicable／conditional gap | root 無 registry owner；生成專案由產品 owner 決定；#439 對齊設定面 | 目前不生成 publisher job 或要求 token | 不宣稱 PyPI、npm 或 GHCR 已啟用；既有選項不等於 active |
| production deployment | not applicable | consuming product | 無通用 workflow 或 environment | 產品自行定義 runtime、health check、approval 與 rollback |

Live snapshot：default branch 是 `main`；active workflows 只有 CI、PR policy、Dependabot、Issue triage、Spec to Issue、Milestone lifecycle 與 OSV。Repository 的預設 `GITHUB_TOKEN` 是 read-only，Actions 不允許自行核准 PR，合併後自動刪除來源 branch。這些觀察只證明 2026-09-01 的狀態；active claim 仍須由 checked-in workflow 與當次 run 共同支持。

### Release ownership modes

| 模式 | 唯一 owner | 本模板目前行為 |
| --- | --- | --- |
| CSARC-owned | 公版維護者 | 版本 PR、tag 與 Release 目前人工；#369 定稿前不恢復 bot owner |
| Product-owned | 生成／既有產品維護者 | 產品 release workflow 與內容保留；模板不從檔名推測、不重複 dispatch，也不建立相同 tag／Release／assets |
| Verification-only | repo-local scripts／tests | 只驗版本同步、成品、checksum、SBOM 與 consumption policy；不取得 write permission、不發布 |

## 歷史 Action disposition

沒有 workflow 因為「曾經成功」而恢復。#430 判定不恢復的版本／交付 archived YAML 已移除，
避免它們被當成可複製設定；歷史由 Git、Issue、PR 與既有 runs 保存。

| 歷史能力 | 決定 | 理由／後續 owner |
| --- | --- | --- |
| Release Please | remove archived YAML；不恢復 | 可審查版本 PR 是合理模型，但 #369 尚未決定 template 與產品的 release owner；現行 token 也不得被推論成可開 PR |
| release-template artifact publish | remove archived YAML；保留本機契約 | build、checksum、SBOM 與 consumption 檢查仍適用；沒有真實 owner／trigger 前不取得 write、packages 或 attestation 權限 |
| release consumption | remove archived Action；保留 verifier | 消費端驗證是必要邊界，但不需要常駐 synthetic workflow 冒充實際消費者 |
| promotion／promotion post-merge | remove archived YAML；人工 | Milestone delivery 仍需完整 CI 與 human approval；未來需要自動化時從現行 branch policy 重新設計 |
| delivery maintenance | remove archived YAML；人工 | 只同步有實際 dependency 的 delivery branch；不對所有分支 fan-out |
| dev-next-close | retire and remove | 固定 `dev/next`／`promote/next` 路徑由 #429 移除，不再保留現行問題或恢復計畫 |
| release follow-up policy | remove archived Action；保留 regression | #403 已證明發版驗證應是 Issue PR 的超集合；目前沒有 bot-owned follow-up PR 可觸發 |
| live integration | retire and remove as current proof | 舊 run 只是一時的整合證據；目前狀態改由各 active workflow 與真實消費者分別證明 |
| Python version policy | remove archived YAML | runtime baseline 仍由 profile 與 dependency policy 管理；沒有必要為 release delivery 恢復專用 Action |
| reusable CI、Zizmor、governance workflows | 由 Journey 03／08 評估 | 不屬版本／交付 owner，本 ADR 不跨責任邊界恢復 |

其他 Journey 尚未處置的 archive 不是可複製範本。若未來恢復某一 workflow，同一項變更必須移除它的 archived root／template copy，讓 active file 成為唯一來源。

### Repo-local scripts and tests disposition

| 實作 | 決定 | 現行用途 |
| --- | --- | --- |
| `scripts/release_policy.py`／`tests/test_release_policy.py` | retain／rewrite wording | 保留 SemVer 意圖、版本檔同步、來源與重試的純函式契約；CLI 輸出只稱 planning snapshot，不宣稱 runtime release |
| `scripts/release_assets.py`／`tests/test_release_assets.py` | retain conditional | 只對呼叫者明列的真正成品建立並驗證 checksum／SPDX；不自行發布 |
| `scripts/verify_release_consumption.py`／`tests/test_release_consumption.py` | retain conditional | 保存消費端 fail-closed policy；沒有 active workflow 時不宣稱門禁已啟用 |
| `scripts/promotion_gate.py`／delivery sync tests | retain only where current branch policy consumes it | branch route 以 #429 為準；退役的 `dev/next`／`promote/next` 分支與 assertions 一併移除 |
| `scripts/test-release-follow-up-gates` | retain as dormant regression | active release workflows 不存在時明確 skip；未來恢復前可用來檢查 Issue PR 的超集合契約 |
| `release-please-config.json`／`.release-please-manifest.json` | retain as version metadata | 現階段由人工版本 PR 更新；檔名不表示 Release Please Action active |

Copier 目前仍會詢問 container mode、registry publisher 與 attestation 開關，但 active
workflow 沒有 consumer；[#439](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/439)
負責決定接線、降為明確 conditional，或安全移除。本 ADR 不在文件工作內改變這些功能。
既有產品自己的 release workflow 仍由 adoption ownership policy 保留。

## 舊問題 disposition

| 來源 | 結論 |
| --- | --- |
| #64 | Superseded：固定 `GITHUB_TOKEN` Release PR 已被 capability-aware 設計取代；本次再由 manual baseline 取代其 active claim |
| #98／#99／#104 | One-time evidence：證明 handoff、live integration 與 consumption 曾可運作，不是現行 workflow 證據 |
| #123 | Preserved as principle：unknown／blocked 不得當 allowed；不保留三模式自動發版宣稱 |
| #142 | One-time repair：版本 metadata 歷史修復完成，不轉成常駐待辦 |
| #183 | Preserved：版本批次發生在 delivery boundary；實際 branch route 由 #429 定稿 |
| #321 | One-time recovery：缺失 Release 的修復不是一般 happy path |
| #322／#341 | Superseded by Journey 05：dependency cooldown 與 SBOM 規格由依賴安全擁有 |
| #372／#373 | Preserved：automation 全面封存後，只逐支、以目前需求與成本恢復 |
| #399 | Preserved：工作 PR 結束單項工作；版本／交付處理批次進 main 與結案 |
| #403 | Preserved：完整交付驗證是 Issue PR 驗證的超集合 |
| #406／#407 | Resolved：Dependabot／OSV 已有現行 owner 與 Action，不在發版流程複製 |
| #426 | Preserved：工作分支與 delivery branch 使用不同 cleanup 時點 |

## 仍開放的單一 owner

| Issue | Owner／狀態 | 本 ADR 的邊界 |
| --- | --- | --- |
| [#369](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/369) | Open；release ownership | 在它完成前，tag／GitHub Release 維持 blocked，產品 workflow 只保留、不推測 |
| [#400](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/400) | Open；Milestone lifecycle | 本次只標 manual gap，不重做 closure validator |
| [#401](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/401) | Open；work Issue lifecycle | 本次只保留工作 PR 的責任分界 |
| [#408](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/408) | Closed；stage timing output | 現行驗證入口已輸出 stage timing，版本流程不另做 telemetry |
| [#416](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/416) | Closed；transactional update | update 已具交易性；本次只維持 product-owned release workflow preservation |
| [#428](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/428) | Closed／PR #431 merged；fast-path cost | 採用其 2026-09-01 實測：source fast 59 秒、policy／template 99 秒、hosted full verification 330 秒（整個 job 6 分 16 秒） |
| [#429](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/429) | Closed／PR #432 merged；standalone route | 一般 standalone 直接進 `main`；里程碑使用 `dev/m*`，獨立 canary 使用 `dev/i*`；不保留固定 `dev/next` |
| [#439](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/439) | Open；dormant delivery options | container／registry／attestation 選項有設定面但沒有 active consumer；不在 #430 偷刪或假裝啟用 |

## 重新評估條件

只有下列事件才重新評估自動發版：#369 明確選定 owner；真實 consuming repository 要求 GitHub Release 或 registry；#400／#401 的 lifecycle contract 已完成；branch route 已定稿；或平台能力／成本有實測變化。恢復時應從需求與最小權限重新設計，不從 archive wholesale copy。
