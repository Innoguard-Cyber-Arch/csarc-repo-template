+++
title = "CSARC Repo Template｜AI 輔助 SDLC 團隊公版"
notice = "內部限閱・請勿公開分享此連結（Internal use only — do not share this link publicly）"

[controls]
language = "閱讀語言"
detail = "閱讀深度"
simple = "簡單"
technical = "技術"
slides = "簡報控制"
previous = "上一頁"
next = "下一頁"
zoom = "畫面縮放控制"
zoom_out = "縮小投影片"
zoom_reset = "恢復自動符合畫面"
zoom_in = "放大投影片"
fit = "符合畫面"
+++

{{< slide key="capability" track="capability" eyebrow="CSARC Repo Template" title="可更新的 repo 公版" subtitle="建立新案、導入舊案與接收政策更新，都先驗證再由 PR 合併。" >}}
公版把工作定義、AI 契約、驗證、合併、依賴與交付證據放進同一條可審查流程。

- 支援 CI/CD-only、Python、TypeScript 與混合專案。
- 新專案與既有 repo 共用同一組政策來源。
- 日常驗證從 `./scripts/verify` 開始。

{{< detail key="capability-boundary" title="能力邊界" >}}
公版只提供已有可執行檔案與回歸驗證的能力；Go、Rust、託管、通用部署與監控仍是未來項目。
{{< /detail >}}
{{< /slide >}}

{{< slide key="flow" track="flow" eyebrow="開發者旅程" title="從需求到可交付版本" subtitle="每一階段都有可觀察的輸入、門禁與證據。" >}}
1. 用 Issue 定義可驗收結果，需要端到端 story 時才建 Milestone。
2. 在編號分支與獨立 worktree 中實作，先跑小檢查再跑完整驗證。
3. PR 保留變更意圖、審查與 CI 證據；promotion 才進入 `main`。

{{< detail key="flow-foundation" title="橫跨全流程" >}}
Ruleset、Copier 更新、內部決策網站與分階段導入是長期基礎，不是每次手動重做的步驟。
{{< /detail >}}
{{< /slide >}}

{{< slide key="files" track="files" eyebrow="責任地圖" title="檔案擁有權要清楚" subtitle="模板可提更新，產品內容不被靜默覆寫。" >}}
| 類別 | 範例 | 負責方 |
| --- | --- | --- |
| 工作契約 | `AGENTS.md`、`README.md` | 共同維護 |
| 驗證與政策 | `scripts/`、`.github/`、`policies/` | 公版主導 |
| 產品程式 | `src/`、產品測試 | 專案持有 |

{{< detail key="files-update" title="更新原則" >}}
Copier 把差異帶進短分支，衝突留在 PR 中由人檢視；回歸測試明確阻擋產品目錄遭覆寫。
{{< /detail >}}
{{< /slide >}}

{{< slide key="method" track="method" eyebrow="步驟 01" title="先寫清楚要解決什麼" subtitle="Issue 是實作範圍；Milestone 是可選的 story 成果層。" >}}
- 開工前先查 open Milestones、open Issues 與有關的 closed Issues。
- Issue 用英文標題摘要結果，內文定義問題與完成條件。
- 超出範圍的需求另開 Issue，不偷塞進當前 PR。

{{< disclosure key="spec-tracking" title="spec 預設同步 Issue，明確 story 才建 Milestone" >}}
`docs/specs/*.md` 以 frontmatter 記錄狀態。`tracking: story` 才將規格同步為 Milestone；同步可重跑，不會自動拆出未經確認的子工作。
{{< /disclosure >}}

{{< detail key="method-lifecycle" title="Story 生命週期" >}}
只有當所有完成條件已勾選且沒有 open Issue 時才關閉 Milestone；條件退回或 Issue 重開時也會重開。
{{< /detail >}}
{{< /slide >}}

{{< slide key="agents" track="agents" eyebrow="步驟 02" title="先定 AI 工作契約" subtitle="README 服務使用者，AGENTS.md 留下可執行的 agent 邊界。" >}}
- 就近的 `AGENTS.md` 只覆寫真正需要不同的子目錄規則。
- 並行工作各用一個 branch 與 worktree，只在範圍獨立時並行。
- 自動化不取代 Issue、PR、CI 與人類審核。

{{< disclosure key="agents-standard" title="標準 AGENTS.md 與就近覆寫" >}}
AGENTS.md 是一般 Markdown；Codex 由 repo 根目錄往工作目錄合併指令，距離當前檔案較近的規則優先。
{{< /disclosure >}}

{{< detail key="agents-control" title="真正的控制點" >}}
AGENTS.md 說明工作方式；GitHub 權限、Ruleset、CODEOWNERS 與 required checks 才是不能繞過的控制。
{{< /detail >}}
{{< /slide >}}

{{< slide key="contract" track="contract" eyebrow="步驟 03" title="本機與 CI 用同一把尺" subtitle="每種語言保留自己的工具，最後匯整到穩定的驗證入口。" >}}
- 日常迭代先跑變更相關檢查，交付前跑完整 `./scripts/verify`。
- CI 依變更風險選 fast 或 full，再以穩定 aggregate context 匯整結果。
- 錯誤 fixture 證明門禁真的會拒絕壞輸入。

{{< disclosure key="language-toolchain" title="Python：uv／Ruff／mypy／pytest；TypeScript：pnpm／Biome／Vitest" >}}
格式、型別、測試與打包交給各語言的主流工具；安全、政策與進階驗證仍共用同一入口。
{{< /disclosure >}}

{{< detail key="contract-quota" title="Actions 額度例外" >}}
只有帳務可見的維護者明確確認本期額度用完，且 job 沒有執行任何 step，才能對精確 SHA 使用一次性本機驗證聲明。
{{< /detail >}}
{{< /slide >}}

{{< slide key="pr" track="pr" eyebrow="步驟 04" title="小 PR 通過證據再合併" subtitle="分支路由、Issue 編號、語意版本意圖與同步狀態一起檢查。" >}}
- 分支使用 `type/123-short-slug`，PR 連回未結案 Issue。
- Milestone 工作先進 delivery branch，promotion 再將已整合結果帶入 `main`。
- 新 commit 讓舊核准失效，review thread 須解決。

{{< detail key="pr-version-intent" title="PR 標題是 SemVer 意圖" >}}
`feat`、`fix` 與其他 Conventional Commit 類型在合併後由實際 default-branch history 決定版本；open PR 不預留版號。
{{< /detail >}}
{{< /slide >}}

{{< slide key="supply" track="supply" eyebrow="步驟 05" title="風險立即看見，升版不搶第一天" subtitle="一般新版觀察三天，已知漏洞則立即阻擋。" >}}
- Dependabot 管理 `uv` 與 `npm` 更新，一般版本延後三天。
- `uv` 與 `pnpm` 鎖定實際 artifact 完整性，OSV 掃公開漏洞。
- 發布成品附 SHA-256 與 CycloneDX SBOM。

{{< disclosure key="supply-tools" title="Dependabot＋OSV＋anchore/sbom-action" >}}
Dependabot 保留 GitHub 原生 automation identity，不要求每個專案安裝高權限 App 或長效 PAT；pnpm `minimumReleaseAge` 另外保護本機與 CI resolution。
{{< /disclosure >}}

{{< detail key="supply-boundaries" title="檢查職責" >}}
lint 找程式品質問題，OSV 找已登錄依賴漏洞，CodeQL 補跨函式資料流；彼此不互相冒充。
{{< /detail >}}
{{< /slide >}}

{{< slide key="deploy" track="deploy" eyebrow="步驟 06" title="版本規則與成品接續" subtitle="先驗證 promotion 邊界，再依當下平台能力選擇安全交付模式。" >}}
- 只從已驗證的 promotion 或合格 hotfix 建立發布來源。
- 平台能力明確分為 `allowed`、`blocked`、`unknown`。
- 不能安全寫入時只保留 verification-only artifact。

{{< disclosure key="adaptive-release" title="promotion-gated adaptive release 與單一 SemVer" >}}
Release PR、direct 與 verification-only 的選擇來自每次 runtime probe；403、409、沒有 remote 或沒有管理權都不會被誤當成 allowed。
{{< /disclosure >}}

{{< detail key="deploy-ordering" title="交付順序" >}}
Direct mode 在寫入前重讀 default branch head，只處理最新且證據一致的 main commit；不假設 workflow concurrency 提供 FIFO。
{{< /detail >}}
{{< /slide >}}

{{< slide key="governance" track="governance" eyebrow="步驟 07" title="先辨識 GitHub 能力，再套用真的管制" subtitle="希望的政策、API 已儲存設定與實際強制能力分開觀察。" >}}
- 所有方案都保留 repository、Actions、labels 與 Ruleset policy 來源。
- Free private 不誤稱 Ruleset 已強制，而是明列 degraded 狀態。
- 每日 drift check 縮短設定偏離的不可見時間。

{{< detail key="governance-observation" title="觀察限制" >}}
排程檢查是快照；兩次執行間曾變更後又復原的事件，仍需 GitHub audit log 或組織層監控追溯。
{{< /detail >}}
{{< /slide >}}

{{< slide key="template-release" track="template-release" eyebrow="步驟 08" title="Copier 保持同步，公版也吃自己的規則" subtitle="公版維護共用基礎，專案透過可審查差異接收更新。" >}}
- 建立、既有 repo 導入與同一 repo 後續更新都有實際 fixture。
- CI/CD-only、Python、TypeScript 與混合組合共用一個公版 SemVer。
- 模板更新不覆寫專案持有的產品檔案。

{{< disclosure key="copier-update" title="Copier＋root dogfood＋建立／更新回歸" >}}
Copier 記錄來源、語言與答案，將新版模板套回已有 repo；衝突保留在短分支與 PR 中由人處理。
{{< /disclosure >}}

{{< detail key="template-release-scope" title="Root-only 邊界" >}}
`scripts/verify-template.sh` 只在公版 repo 實跑生命週期 fixture，不下發到 consuming repository。
{{< /detail >}}
{{< /slide >}}

{{< slide key="docs-site" track="docs-site" eyebrow="步驟 09" title="單檔永遠可交付" subtitle="Hugo 管理 Markdown 與版型，未修改的 renderer 將頁面打包成無外部 runtime 依賴的 HTML。" >}}
- `decision-site/content/` 是候選內容來源，中英文使用相同 section keys。
- CSS、JavaScript、font 與圖片由 `scripts/render_site.py` 內嵌。
- 外部參考連結可保留，離線時不影響閱讀與操作。

{{< disclosure key="portable-bundle" title="可維護來源 → self-contained HTML" >}}
`docs/decisions/` 保存 canonical 選型；Hugo 負責內容結構與 HTML，renderer 只負責內嵌本地資產與拒絕外部 runtime asset。
{{< /disclosure >}}

{{< detail key="docs-site-access" title="存取邊界" >}}
`noindex` 不是存取控制；核准 host 可保護入口，但下載後的離線檔案仍可能被轉寄。
{{< /detail >}}
{{< /slide >}}

{{< slide key="rollout" track="rollout" eyebrow="步驟 10" title="分階段導入，每一步都能停" subtitle="先做可收敛的基本層，證據出現後才增加平台能力。" >}}
- **基本：** Issue、PR、本機驗證、CI、依賴與秘密掃描。
- **最佳：** 在方案與權限支援時強制 Ruleset、promotion 與交付證據。
- **可選：** 有實際需求再啟用託管、跨 repo 目錄或更強平台。

{{< detail key="rollout-evidence" title="成熟度不只看能不能建立" >}}
Profile catalog 分開合成驗證與 consuming repo 證據；沒有真實採用證據時不把能力寫成成熟。
{{< /detail >}}
{{< /slide >}}

{{< slide key="bridge" eyebrow="2025-05 → 2026-08" title="保留核心，調整實作方式" subtitle="舊版 SDLC 原則繼續有效，但合併路由、更新與能力偵測更明確。" >}}
- 保留：可重複驗證、人類審核、依賴風險與可追溯交付。
- 調整：delivery branch 先整合並行 story，promotion 再進 `main`。
- 不採用：從方案名稱猜測能力，或在沒有證據時提前建平台。

{{< detail key="bridge-reason" title="調整理由" >}}
近期實測顯示 GitHub 方案、組織政策與 token 身分都會影響可用能力，因此要以 runtime probe 取代靜態假設。
{{< /detail >}}
{{< /slide >}}

{{< slide key="ecosystem" eyebrow="工具選型" title="工具是手段，流程與治理才是主線" subtitle="基本導入、未來導入與條件式導入分開說明。" >}}
| 工具 | 現在的決定 |
| --- | --- |
| Copier、zizmor | 基本導入 |
| Dependabot、OSV、Syft | 基本依賴與成品證據 |
| Safe Settings、Backstage | 規模與跨團隊需求成立後再導入 |
| Renovate | 現階段不取代 Dependabot |

{{< detail key="ecosystem-deferred" title="尚未啟用" >}}
Go／Rust profile、Scorecard、Harden-Runner、網站託管與登入、RAG、通用部署與監控都等可測量需求再做。
{{< /detail >}}
{{< /slide >}}

{{< slide key="access-control" eyebrow="存取決策" title="託管方案未定前的臨時防護" subtitle="先降低意外擴散，不把提示語誤寫成安全控制。" >}}
- 頁首標示內部限閱，`robots.txt` 與 `noindex` 降低搜尋引擎收錄。
- 只有維護者核准 host、認證與寫入路徑後才能宣稱已受控發布。

{{< detail key="access-control-limit" title="已知限制" >}}
擁有離線 HTML 的人可繼續轉寄；託管入口的認證無法追回已下載檔案。
{{< /detail >}}
{{< /slide >}}

{{< slide key="principles" eyebrow="關鍵決策" title="規則、理由與刻意不做" subtitle="只將已確認且持久的限制寫進決策記錄。" >}}
- 將平台能力視為可偵測狀態，不視為不變假設。
- 把可攜帶的單檔交付當作 baseline，託管只做加成。
- 把專案持有內容與模板主導基礎分開。

{{< detail key="principles-transcript" title="不保存原始對話" >}}
Agent 只將使用者已確認的 durable constraint 摘要到 Issue，再經過 PR 寫入 decision record。
{{< /detail >}}
{{< /slide >}}

{{< slide key="benchmark" eyebrow="外部基準" title="有骨架，還不是完整平台" subtitle="現在的組合優先可理解、可攜帶與可維護。" >}}
- Copier＋GitHub Actions＋語言原生工具已覆蓋當前小型公版需求。
- CI-only pilot 補上合成 fixture 以外的真實採用證據。
- 其他 profile 各自完成 pilot 後才升級成熟度。

{{< detail key="benchmark-gap" title="現階段缺口" >}}
沒有跨 repo catalog、全面託管治理或通用部署平台；這些需求應由真實反覆成本觸發。
{{< /detail >}}
{{< /slide >}}

{{< slide key="fleet-inventory" eyebrow="Fleet 治理" title="採用盤點以真實 repo 為準" subtitle="目前證據不足以合理化新平台。" >}}
- 盤點 answers/profile、CODEOWNERS、未完成 update PR 與 governance-drift runs。
- 沒有完成的排程樣本不記為零漂移。
- 新 pilot 與每季回顧都重新計數。

{{< detail key="fleet-inventory-source" title="證據來源" >}}
用 GitHub API 讀取目前狀態，同時保留 blocked 與 unknown；不從沒有 run 的空白狀態推導沒有問題。
{{< /detail >}}
{{< /slide >}}

{{< slide key="fleet-thresholds" eyebrow="Fleet 門檻" title="先量問題，再加平台" subtitle="反覆成本、擁有者與退場條件都要明確。" >}}
- 多個 consuming repo 反覆出現同類 drift 或 update 堵塞時再開評估 Issue。
- Issue 要指定平台 owner、成本上限、試行範圍與退場條件。

{{< detail key="fleet-thresholds-yagni" title="不預建服務" >}}
本決策只定義重新評估門檻，不授權建置 Backstage、Safe Settings 或其他常駐外部服務。
{{< /detail >}}
{{< /slide >}}

{{< slide key="spec-format" eyebrow="Spec 格式" title="預設 Issue，明確 Story 才建 Milestone" subtitle="保留一種簡單格式，不在需求尚未出現時同時維護兩套系統。" >}}
- 現行 Markdown spec 使用 frontmatter 記錄 ID、優先度、狀態與選用 tracking。
- 預設以 marker idempotently 同步一張 Issue。
- 當核准規格需由 AI 穩定拆成多張工作，才重新評估 Spec Kit。

{{< detail key="spec-format-cost" title="改用 Spec Kit 的成本" >}}
需改寫 parser 與同步邏輯、轉換既有 spec、更新驗證斷言，並另行設計等價 Issue-sync；目前效益尚不足。
{{< /detail >}}
{{< /slide >}}
