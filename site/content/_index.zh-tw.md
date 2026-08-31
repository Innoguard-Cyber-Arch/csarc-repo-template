+++
title = "CSARC Repo Template｜AI 輔助 SDLC 團隊公版"

[controls]
language = "閱讀語言"
detail = "閱讀模式"
simple = "標準"
technical = "維運"
slides = "簡報控制"
previous = "上一頁"
next = "下一頁"
zoom = "畫面縮放控制"
zoom_out = "縮小投影片"
zoom_reset = "恢復自動符合畫面"
zoom_in = "放大投影片"
fit = "符合畫面"
+++

{{< slide key="capability" track="capability" eyebrow="CSARC Repo Template · beta" title="可更新的 repo 公版" subtitle="建立新案、導入舊案與接收政策更新，都先驗證再由 PR 合併。" class="legacy-slide capability-slide" legacy="true" >}}
{{< legacy >}}
      <header class="package-hero">
        <p class="package-kicker">Innoguard-Cyber-Arch / repository infrastructure</p>
        <h1><code>csarc-repo-template</code></h1>
        <p class="subtitle">Cyber-Arch 的可更新 repo 公版：建立新案、導入既有案、接收政策更新，都先驗證再由 PR 合併。</p>
        <p class="subtitle">本頁是技術決策附錄，服務對象是想理解「為什麼這樣設計」的人；一般使用者的快速上手與導入指令請見 <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template#readme" target="_blank" rel="noreferrer">repo README</a>。</p>
        <div class="package-badges" aria-label="套件狀態">
          <span class="package-badge beta">v0.12.2</span><!-- x-release-please-version -->
          <span class="package-badge beta">beta</span>
          <span class="package-badge python">CI-only／Python／TypeScript／兩者</span>
          <span class="package-badge">delivery 分層／main／dev</span>
          <span class="package-badge">Copier 可更新</span>
          <span class="package-badge security">CI／安全檢查</span>
          <span class="package-badge warning">Free private：main 尚未受保護</span>
        </div>
      </header>
      <div class="language-contract" aria-label="程式語言 profile 決策">
        <p class="language-card"><strong>建立時必選｜四種組合</strong>只要 CI/CD 基線、Python、TypeScript，或兩者都有；宣告會寫入 repo 並由檔案自動核對。</p>
        <p class="language-card shared"><strong>四種組合共用</strong>SDD Feature＋Task／Bug subissues、有期限的 delivery Milestone、分層 CI、promotion evidence、安全檢查、單一 SemVer 與 Copier 更新；建立時可選 delivery、main-only 或單一 dev。</p>
        <p class="language-card future"><strong>版本基線</strong>Python 3.14；TypeScript 採 Node 24 Active LTS。Go／Rust 仍是 future，不先建立空設定。</p>
      </div>
      <div class="product-start">
        <section class="product-scope" aria-label="公版提供的能力">
          <h3>公版會替 repo 準備</h3>
          <p class="scope-row"><strong>規劃與 AI 規範</strong><span>SDD → Feature parent → Task／Bug subissues → 各自 PR；Milestone 只管理有期限的交付</span></p>
          <p class="scope-row"><strong>驗證與合併</strong><span><code>./scripts/verify</code>＋分層 CI＋PR；並行 Milestone 各自整合，promotion 才進 main</span></p>
          <p class="scope-row"><strong>依賴與交付證據</strong><span>新版先等三天；OSV 查已公開漏洞；checksum 驗檔案一致；SBOM 列成品套件；已有 Containerfile 可選配容器驗證／GHCR</span></p>
          <p class="scope-row"><strong>可持續同步</strong><span>公版更新成為可審查差異，不會直接覆蓋產品程式</span></p>
        </section>
        <section class="start-paths" aria-label="三種導入方式">
          <h3>依你現在的 repo 狀態開始</h3>
          <article class="start-path"><h3>新 repo</h3><p>選語言與分支模式；需要端到端 story 時先建 Milestone，再由 Issue 進 PR。</p><button class="setup-trigger" type="button" data-setup="new" aria-expanded="false">建立指令</button></article>
          <article class="start-path"><h3>既有 repo</h3><p>在導入分支保留舊債邊界，逐項解決衝突與門禁。</p><button class="setup-trigger" type="button" data-setup="existing" aria-expanded="false">導入指令</button></article>
          <article class="start-path"><h3>已使用公版</h3><p>指定已審查的公版 SHA，只審查本次版本差異。</p><button class="setup-trigger" type="button" data-setup="update" aria-expanded="false">更新指令</button></article>
        </section>
      </div>
      <div class="prerequisite-line product-prerequisites">
        <p><strong>開始前必裝</strong>Git、GitHub CLI、uv；TypeScript／混合案另需 Node 24+、pnpm 11。純本機驗證不用 token；套用 GitHub 設定與端到端測試前才登入 <code>gh</code>。</p>
        <button class="setup-trigger" type="button" data-setup="mac" aria-expanded="false">macOS 安裝</button>
        <button class="setup-trigger" type="button" data-setup="windows" aria-expanded="false">Windows 安裝</button>
      </div>
{{< /legacy >}}

{{< basic >}}
公版把工作定義、AI 規範、驗證、合併、依賴與交付證據放進同一條可審查流程。

| 可以直接選擇 | 目前提供的正式能力 |
| --- | --- |
| 專案組合 | CI/CD-only、Python 3.14、TypeScript（Node 24／pnpm 11）、Python＋TypeScript |
| 分支模式 | Milestone delivery branches、`main`-only、單一 `dev` |
| 共用基線 | SDD Feature＋Task／Bug subissues、有期限的 delivery Milestone、分層 CI、promotion evidence、安全檢查、單一 SemVer、Copier 更新 |

{{< detail key="capability-boundary" title="真正的導入入口與能力邊界" >}}
- **新 repo：** 選 profile 與分支模式；以 SDD Feature 保存 story，Task／Bug subissues 各自進 PR，Milestone 只管理有期限的交付。
- **既有 repo：** 在導入分支先做 dry-run，保留既有產品內容與技術債邊界，再逐項解決衝突與門禁。
- **已使用公版：** 指定已審查的公版 SHA 執行 Copier update，只審查這次版本差異。
- **開始前必裝：** Git、GitHub CLI、uv；TypeScript／混合案另需 Node 24+ 與 pnpm 11。純本機驗證不需要 token。

公版只宣告已有可執行檔案與回歸驗證的能力。Go、Rust、通用部署、監控、RAG 與網站託管仍是未來或選配項目。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="flow" track="flow" eyebrow="開發者旅程" title="從需求到可交付版本" subtitle="01–06 跟著工作走；07–10 持續支撐整套流程。" class="legacy-slide pipeline-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>一張圖看懂：<span class="accent">程式怎麼從需求走到可交付版本</span></h2>
        <p class="subtitle">CI 是 PR 上的自動檢查與回饋；CD 是合併後建立可追溯版本與成品。01–06 跟著工作走，07–10 在底層維持整套流程。</p>
      </header>
      <div class="pipeline-map">
        <div class="pipeline-track" aria-label="日常開發與交付主流程">
          <article class="pipeline-stage">
            <span class="pipeline-phase">PLAN｜先決定要做什麼</span>
            <div class="pipeline-tags"><span class="pipeline-tag">01</span></div>
            <h3>定義工作</h3>
            <p>用 Issue 說清楚問題與完成條件，其餘選填寫進補充。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">CODE｜在短分支完成</span>
            <div class="pipeline-tags"><span class="pipeline-tag">02</span></div>
            <h3>實作與測試</h3>
            <p>人或 AI 依 AGENTS.md 修改，先在本機驗證。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">PR｜把變更交給團隊看</span>
            <div class="pipeline-tags"><span class="pipeline-tag">04</span></div>
            <h3>提出 PR</h3>
            <p>連回 Issue，說明目的、測試與回退方式。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">CI｜機器先找明確錯誤</span>
            <div class="pipeline-tags"><span class="pipeline-tag">03</span><span class="pipeline-tag">05</span></div>
            <h3>自動檢查</h3>
            <p>Issue PR 跑 fast；promotion 才跑 full 與可選 canary。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">REVIEW｜人判斷是否合理</span>
            <div class="pipeline-tags"><span class="pipeline-tag">04</span></div>
            <h3>審查與合併</h3>
            <p>修到檢查通過、同事核准，先進對應 delivery branch。</p>
          </article>
          <article class="pipeline-stage best">
            <span class="pipeline-phase">CD｜交付同一份成品</span>
            <div class="pipeline-tags"><span class="pipeline-tag best">06</span></div>
            <h3>版本與交付</h3>
            <p>promotion 批次建立 SemVer、artifact、checksum 與 SBOM；部署另訂。</p>
          </article>
        </div>
        <div class="pipeline-loop" aria-label="CI 回饋迴圈">
          <strong>↶ 檢查失敗：回到 02 修正，再更新同一張 PR</strong>
          <span>交付後的新問題回到 01，成為下一張有邊界的 Issue。</span>
        </div>
        <div class="pipeline-foundation" aria-label="支撐整體流程的平台能力">
          <div class="pipeline-foundation-label"><strong>一直支撐全流程</strong><span>不是每次手動執行，而是公版持續維護的基礎設施。</span></div>
          <article class="pipeline-foundation-card"><h3><span class="pipeline-tag">07</span>規則治理</h3><p>權限、分支與合併規則一致。</p></article>
          <article class="pipeline-foundation-card"><h3><span class="pipeline-tag">08</span>模板升級</h3><p>用 Copier 把政策更新帶回 repo。</p></article>
          <article class="pipeline-foundation-card"><h3><span class="pipeline-tag">09</span>內部網站</h3><p>讓做法、限制與決策容易查找。</p></article>
          <article class="pipeline-foundation-card best"><h3><span class="pipeline-tag best">10</span>導入層級</h3><p>基本先做；條件成熟再加進階能力。</p></article>
        </div>
      </div>
{{< /legacy >}}

{{< basic >}}
| 階段 | 人與 agent 做什麼 | 自動化證據 |
| --- | --- | --- |
| 01 定義工作 | Issue 說清楚問題與完成條件 | 標題、欄位與重複工作檢查 |
| 02 實作測試 | 依 `AGENTS.md` 在短分支與獨立 worktree 修改 | 本機 focused checks |
| 03 提出 PR | 連回 Issue，說明目的、驗證與回退 | PR policy 與 delivery route |
| 04 自動檢查 | 一般 Issue PR 跑 fast | `verify` aggregate 回報結果 |
| 05 審查合併 | 修正失敗、解決 review、先進 delivery branch | 核准與 required checks |
| 06 版本交付 | promotion 才批次建立版本與成品 | full verify、checksum、SBOM、attestation |

{{< detail key="flow-foundation" title="橫跨全流程的四項基礎" >}}
- **07 規則治理：** 權限、分支、審查與合併規則一致。
- **08 模板升級：** Copier 將新政策帶回既有 repo，差異仍經 PR。
- **09 內部網站：** 讓做法、限制、證據與決策容易查找。
- **10 導入層級：** 基本能力先做；需求與平台條件成熟後才加進階能力。

CI 失敗就回到 02 修正同一張 PR；交付後的新問題回到 01，成為下一張有邊界的 Issue。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="files" track="files" eyebrow="責任地圖" title="模板實際加入與維護的檔案" subtitle="公版可提更新，但不靜默覆寫專案持有的產品內容。" class="legacy-slide managed-files-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>模板會把這些<span class="accent">工程基礎設施放進你的 repo</span></h2>
        <p class="subtitle">先選 CI/CD-only、Python、TypeScript 或兩者；共用 GitHub 層不變，只有所選語言的工具與產品目錄會出現。</p>
      </header>
      <div class="repo-map-window" aria-label="模板產生檔案的視覺對照">
        <div class="repo-map-toolbar">
          <span class="repo-map-dots" aria-hidden="true"><i></i><i></i><i></i></span>
          <span class="repo-map-address">your-project /</span>
          <span class="repo-map-profile">CI-only／Python／TypeScript／混合｜依宣告產生</span>
        </div>
        <div class="repo-tree-head"><span>路徑（依 repo 結構）</span><span>功能／對應旅程編號</span><span>語言</span><span>模板影響</span></div>
        <div class="repo-tree-body">
          <div class="repo-tree-row"><span class="repo-tree-path">.copier-answers.yml＋.csarc/profile.json</span><span class="repo-tree-purpose"><span class="journey-code">08</span><span class="purpose-copy">來源、語言與分支模式</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path">.gitignore</span><span class="repo-tree-purpose"><span class="journey-code">02</span><span class="purpose-copy">環境雜訊／語言產物</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path folder">.github/</span><span class="repo-tree-purpose"><span class="journey-code">03–06</span><span class="purpose-copy">GitHub 自動化入口</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-1">CODEOWNERS＋REVIEWERS＋governance workflow</span><span class="repo-tree-purpose"><span class="journey-code">04</span><span class="purpose-copy">指定並輪派個別 reviewer</span></span><span class="scope-badge shared">共用</span><span class="owner-badge shared">共同維護</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-1 folder">ISSUE_TEMPLATE/</span><span class="repo-tree-purpose"><span class="journey-code">01</span><span class="purpose-copy">工作單欄位／工作定義</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-1">dependabot.yml</span><span class="repo-tree-purpose"><span class="journey-code">05</span><span class="purpose-copy">依語言更新相依</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-1">pull_request_template.md</span><span class="repo-tree-purpose"><span class="journey-code">04</span><span class="purpose-copy">PR 必填內容</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-1 folder">workflows/</span><span class="repo-tree-purpose"><span class="journey-code">01／03–06</span><span class="purpose-copy">八條自動流程</span></span><span class="scope-badge mixed">混合</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">ci.yml</span><span class="repo-tree-purpose"><span class="journey-code">03</span><span class="purpose-copy">執行已宣告模組</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">osv.yml</span><span class="repo-tree-purpose"><span class="journey-code">05</span><span class="purpose-copy">跨生態漏洞掃描</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">pr-policy.yml</span><span class="repo-tree-purpose"><span class="journey-code">04</span><span class="purpose-copy">Issue／分支／PR 規則</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">release-please.yml</span><span class="repo-tree-purpose"><span class="journey-code">06</span><span class="purpose-copy">版本與 Release PR</span></span><span class="scope-badge mixed">混合</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">release.yml</span><span class="repo-tree-purpose"><span class="journey-code">05／06</span><span class="purpose-copy">依語言打包與 SBOM</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">spec-to-issue.yml</span><span class="repo-tree-purpose"><span class="journey-code">01</span><span class="purpose-copy">規格自動開單</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">zizmor.yml</span><span class="repo-tree-purpose"><span class="journey-code">03</span><span class="purpose-copy">Actions 安全</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row project-owned"><span class="repo-tree-path folder">docs/specs/</span><span class="repo-tree-purpose"><span class="journey-code">01</span><span class="purpose-copy">功能規格／工作定義</span></span><span class="scope-badge shared">共用</span><span class="owner-badge project">專案持有</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path folder">policies/</span><span class="repo-tree-purpose"><span class="journey-code">07</span><span class="purpose-copy">repo 規則／治理</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path folder">scripts/</span><span class="repo-tree-purpose"><span class="journey-code">01／03／07</span><span class="purpose-copy">開單、驗證與套用設定</span></span><span class="scope-badge mixed">混合</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path">version source＋CHANGELOG＋release-please config／manifest</span><span class="repo-tree-purpose"><span class="journey-code">06</span><span class="purpose-copy">單一版號與變更紀錄</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge shared">共同維護</span></div>
          <div class="repo-tree-row project-owned"><span class="repo-tree-path folder">src/＋tests/；typescript/src/＋tests/</span><span class="repo-tree-purpose"><span class="journey-code">02／03</span><span class="purpose-copy">啟用模組的產品程式</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge project">專案持有</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path">README.md＋AGENTS.md＋CLAUDE.md</span><span class="repo-tree-purpose"><span class="journey-code">01–08</span><span class="purpose-copy">人與 AI 的使用規範</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path">pyproject／package／兩種 lockfile</span><span class="repo-tree-purpose"><span class="journey-code">03／05</span><span class="purpose-copy">版本與語言工具</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge shared">共同維護</span></div>
        </div>
        <div class="repo-map-legend"><span><strong>黃色編號：</strong>對照左側旅程 tag。<strong>模板影響：</strong>公版主導會在 update 提出差異；共同維護可能衝突並由人處理。</span><span><strong>橘線：</strong>專案持有且不改寫。</span></div>
      </div>
{{< /legacy >}}

{{< basic >}}
| 路徑 | 作用 | 責任 |
| --- | --- | --- |
| `.copier-answers.yml`、`.csarc/profile.json` | 記錄公版來源、profile 與分支模式 | 公版主導 |
| `.github/ISSUE_TEMPLATE/`、`pull_request_template.md` | 工作定義與 PR 契約 | 公版主導 |
| `.github/workflows/` | CI、promotion、release、OSV 與治理漂移 | 公版主導 |
| `AGENTS.md`、`README.md` | Agent 工作方式與使用者入口 | 共同維護 |
| `policies/`、`CODEOWNERS`、`.github/REVIEWERS` | 期望設定、owner 與 reviewer | 共同維護 |
| `scripts/verify` | 生成 repo 的單一驗證入口 | 公版主導 |
| `src/`、產品測試與規格 | 真正產品行為 | 專案持有 |

{{< detail key="files-update" title="更新時怎麼保護產品內容" >}}
Copier 把更新帶進短分支，衝突留在 PR 由人檢視。建立、既有 repo 導入與同一 repo 後續 update 都有 fixture；回歸測試會刻意加入產品檔案，再確認更新後內容沒有被覆寫。

Root 與 `template/` 同時消費的 workflow、policy、script 與文件由 `scripts/sync-paired-files.sh` 從 root 產生副本；`--check` 驗證內容與可執行位元沒有漂移。僅因 Copier 變數而不同的檔案則由實際生成專案比對。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="method" track="method" eyebrow="步驟 01" title="先把工作說清楚" subtitle="先寫清楚問題、完成條件與驗證；工作變大時才增加分組或交付批次。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 1｜<span class="accent">工作如何從需求走到合併</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>一張 Issue 定義一項可驗收的改變，一張 PR 負責交付；多項工作需要同批完成時，才使用 Milestone。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>統一 Issue、PR 與 Milestone 的寫法，讓人與 agent 清楚工作範圍與完成條件。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open>
          <summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">常見的工作設計思路</span></summary>
          <ul class="work-definition-list">
            <li><strong>先做再補文件：</strong>小而明確的工作直接完成；跨時段、有依賴或高風險時才補計畫。</li>
            <li><strong>規格先行：</strong>先寫清楚需求、設計與工作拆分，再開始開發；適合大型或不確定性高的改變。</li>
            <li><strong>變更提案：</strong>先把準備修改的內容獨立審查，接受後才併回正式規格；適合把規格差異當成審查核心的團隊。</li>
            <li><strong>依複雜度分級：</strong>小工作走短流程，大型工作才增加探索、設計、分工與審查。</li>
          </ul>
        </details>
        <details class="decision-step decision-fold recommended" open>
          <summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">一條工作線，按需要增加分組</span></summary>
          <ul class="work-definition-list">
            <li><strong>整體：</strong>Issue 說清楚 → branch 實作 → PR 審查與交付；本模板提供一致的表單、規則與驗證入口。</li>
            <li><strong>Milestone：</strong>多張工作有共同期限、整合或發版時才建立；收錄 Task／Bug 與對應 PR。</li>
            <li><strong>Issue：</strong><ul><li><strong>標題：</strong>英文 ASCII 12–80 字元、至少三個詞；不加類型前綴，結尾不加句點。</li><li><strong>內文：</strong>類型、問題與完成條件必填；補充可寫關聯、驗證與風險。</li><li><strong>工作類別：</strong>Feature＝共同成果；Task＝可獨立完成的工作；Bug＝不符合預期；Documentation＝純文件工作。GitHub 原生 Type 只使用 Feature／Task／Bug；Duplicate 與 Hotfix 都不是 Type。</li><li><strong>Label：</strong>工作分類擇一：enhancement、bug、documentation；重複案件使用 duplicate，交付追蹤才使用 promotion。</li><li><strong>Assignee：</strong>建立者在送出時自我指派；agent／CLI 建立時明確指定 <code>@me</code>，正式交接時再更換。</li><li><strong>何時拆 Sub-issue：</strong>同一張 PR 能完成並用同一組結果驗證就不拆；能獨立實作、驗證與交付，或超出原範圍但必須補做才拆。</li><li><strong>Parent：</strong>描述仍未完整達成的共同成果；必要 Sub-issues 完成後才能結案。先後順序另用 Dependency。</li></ul></li>
            <li><strong>PR：</strong><ul><li><strong>標題：</strong><code>type(scope)!: English summary</code>；scope 選填，<code>!</code> 表示破壞性變更。</li><li><strong>Angular types：</strong><code>feat</code> 新功能、<code>fix</code> 修錯、<code>docs</code> 文件、<code>refactor</code> 重構、<code>test</code> 測試、<code>build</code> 建置／相依、<code>ci</code> 自動化、<code>chore</code> 維護、<code>revert</code> 撤銷。</li><li><strong>內文：</strong>Purpose 與 <code>Closes #N</code>、完成清單必填；補充可寫風險、回退與額外影響。</li><li><strong>Label：</strong>enhancement、bug、documentation 擇一；特殊交付才另加 promotion（正式交付）、hotfix（緊急修正）或 release-recovery（補建遺漏的 Release，詳見 06），不能使用 duplicate。</li><li><strong>Assignee：</strong>建立者在送出後自我指派；交接時可更換，但作者仍列為 Assignee。</li></ul></li>
            <li><strong>例外：</strong>Duplicate 是 Issue 的重複結案方式，不開 PR；Hotfix 是 Bug 的緊急交付 Label，可直接進 main，但仍須 Issue、驗證與審查。</li>
          </ul>
        </details>
      </div>
      <aside class="config-guidance" data-config-direct="true"><strong>模板設定與客製化位置</strong><ul><li><strong>工作單欄位：</strong><code>.github/ISSUE_TEMPLATE/*.yml</code> 定義各工作入口的原生 Type、Label、問題與完成條件，<code>config.yml</code> 關閉空白 Issue</li><li><strong>工作層級：</strong><code>AGENTS.md</code> 定義 Feature／Task／Bug 的使用規則，<code>docs/adr/spec-story-and-work-items.md</code> 保存長期理由；團隊只改操作方式時調整前者，改變角色責任時兩者一起更新</li><li><strong>規格同步：</strong><code>docs/specs/</code> 放各專案的長期規格，<code>scripts/spec_to_issue.py</code> 定義 <code>tracking: issue</code>、<code>story</code>、<code>none</code> 的同步行為；一般客製只新增或修改 spec，不必改同步程式</li><li><strong>交付批次：</strong><code>docs/milestone-description.md</code> 定義 Milestone 的 Problem、Outcome、Acceptance criteria 與 Verification；可改團隊用語與範例，但仍要保留真實 due date 與可驗收結果</li></ul></aside>
      <p class="method-reference reference">Ref. <a href="https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues" target="_blank" rel="noreferrer">GitHub sub-issues</a>。具體工具、功能名稱與資料來源統一整理於<a href="#similar-tools">相似工具</a>。</p>
{{< /legacy >}}

{{< basic >}}
### 我們的選擇

- **整體：** Issue 說清楚 → branch 實作 → PR 審查與交付。
- **Milestone：** 多張工作有共同期限、整合或發版時才建立。
- **Issue：** 寫問題、完成條件與驗證；Type 可為 Feature、Task 或 Bug。
  - Feature＝共同成果；Task＝可獨立完成的工作；Bug＝不符合預期。
  - 標題使用 12–80 個英文 ASCII 字元；內文必填類型、問題與完成條件。
  - 工作 Label 從 enhancement、bug、documentation 擇一；建立者在送出時自我指派。
  - 同一張 PR 能完成並用同一組結果驗證就不拆；能獨立實作與驗證，或超出原範圍但必須補做，才拆成 Sub-issue。
  - Parent 描述仍未完整達成的共同成果；所有必要 Sub-issues 完成後才能結案。Dependency 才表示先後阻擋。
- **PR：** 標題使用 <code>type(scope)!: English summary</code>；內文必填 Purpose、<code>Closes #N</code> 與完成清單，建立者在送出後自我指派。
- **例外：** Duplicate 是 Issue 的重複結案方式；Hotfix 是 Bug 的緊急交付 Label。兩者都不是 Issue Type。

### 其他常見做法

- **先做再補文件：**小而明確的工作直接完成；跨時段、有依賴或高風險時才補計畫。
- **規格先行：**先寫清楚需求、設計與工作拆分，再開始開發。
- **變更提案：**先獨立審查準備修改的內容，接受後才併回正式規格。
- **依複雜度分級：**小工作走短流程，大型工作才增加探索、設計、分工與審查。

具體工具、功能名稱與資料來源見[相似工具](#similar-tools)。

{{< /basic >}}
{{< /slide >}}

{{< slide key="agents" track="agents" eyebrow="步驟 02" title="先定 AI 規範，再開始實作" subtitle="Issue 說明這次要做什麼；AGENTS.md 說明 agent 在 repo 裡怎麼做。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 2｜<span class="accent">先定 AI 規範，再開始實作</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>Issue 劃定這次工作；<code>AGENTS.md</code> 說明怎麼做；程式與測試提供證據，人保留需求方向與重大風險決策。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>把 agent 開始前要讀什麼、可修改到哪裡、如何隔離平行工作、怎樣留下驗證，以及何時必須停下來問人寫進 repo；文字規範本身不是自動門禁。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open><summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">常見的 AI 協作設計</span></summary><ul><li><strong>Repo 內指引：</strong>把固定命令與界線放在版本控制中，讓不同 agent 讀同一份規則。</li><li><strong>規格產物接力：</strong>大型工作先產生 spec、plan、tasks，再逐步交給 agent 執行。</li><li><strong>角色與調度：</strong>用專門角色、skills 或佇列安排多個 agent；適合工作量已大到需要額外協調時。</li><li><strong>人類檢查點：</strong>在需求、重大取捨、外部影響與不可逆操作前停下來取得決定。</li></ul></details>
        <details class="decision-step decision-fold recommended" open><summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">六項責任各有唯一位置</span></summary><ul class="work-definition-list"><li><strong>工作與脈絡：</strong>GitHub Issue／PR 記錄範圍、進度與證據；核准的 spec／ADR 保存長期決策，跨 session、高風險或難復原工作才增加 plan，不保存聊天逐字稿。</li><li><strong>AI 規範：</strong>根目錄 <code>AGENTS.md</code> 是唯一來源；<code>CLAUDE.md</code> 只做薄匯入，子目錄只有規則真的不同時才覆寫。</li><li><strong>修改隔離：</strong>每項可寫工作各用 branch／worktree，只平行處理互不依賴的範圍；唯讀工作不必另開 worktree。</li><li><strong>驗證證據：</strong>執行最小且相關的本機程式；Action 只負責事件、權限與呼叫同一程式，不複製邏輯。</li><li><strong>決策與授權：</strong>人負責需求、重大取捨、外部影響與不可逆操作；審查、合併資格與例外由 Journey 07 單獨定義。</li><li><strong>模板建立與更新：</strong>Copier 負責產生與更新共用基線；既有 repo 的更新契約由 Journey 08 定義。</li></ul></details>
      </div>
      <aside class="config-guidance" data-config-direct="true"><strong>模板功能與客製化</strong><ul><li><strong>人與 AI 各看哪份文件：</strong><code>README.md</code> 給人，<code>AGENTS.md</code> 給所有 agent；<code>CLAUDE.md</code> 只匯入同一份規範。</li><li><strong>只產生 profile 真能執行的指令：</strong><code>template/AGENTS.md.jinja</code> 與 <code>copier.yml</code> 依語言產生內容，<code>scripts/verify-template.sh</code> 驗證結果。</li><li><strong>平行可寫工作用 branch／worktree 隔離：</strong><code>AGENTS.md</code> 定義做法；<code>scripts/cleanup-worktrees</code> 與 <code>scripts/test-worktree-cleanup</code> 負責安全清理。</li><li><strong>規範、驗證與治理分開：</strong><code>AGENTS.md</code> 說明做法，<code>scripts/verify</code> 提供證據，<code>.github/workflows/</code> 只包裝執行，<code>policies/</code> 保存治理設定。</li></ul></aside>
      <p class="method-reference reference">具體工具、功能名稱與資料來源統一整理於<a href="#similar-tools">相似工具</a>；Journey 02 的本機檢查與 Action 現況見<a href="#testing">CI/CD 設定</a>。</p>
{{< /legacy >}}

{{< basic >}}
- **工作與脈絡：** GitHub Issue／PR 記錄工作；核准的 spec／ADR 保存長期決策，必要時才加 plan。
- **AI 規範：** 根目錄 `AGENTS.md`；`CLAUDE.md` 只薄匯入。
- **修改隔離：** 每項可寫工作各用 branch／worktree；唯讀工作不用。
- **驗證證據：** 本機程式是唯一邏輯；Action 只呼叫它。
- **決策與授權：** 人保留重大決策；審查與合併規則只由 Journey 07 定義。
- **模板建立與更新：** Copier 負責共用基線；既有 repo 更新由 Journey 08 定義。

具體工具見[相似工具](#similar-tools)，執行方式見 [CI/CD 設定](#testing)。
{{< /basic >}}
{{< /slide >}}

{{< slide key="contract" track="contract" eyebrow="步驟 03" title="先驗證改動，再讓 CI 重跑同一套規則" subtitle="Issue PR 依變更範圍分級；高風險邊界才跑完整驗證。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 3｜<span class="accent">先驗證改動，再讓 CI 重跑同一套規則</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>開發時先跑與改動直接相關的測試；Issue PR 再由同一支 Action 依變更範圍選擇 docs、fast 或 full。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>把測試邏輯留在 repo 內可直接執行的 scripts／tests；GitHub Action 只負責何時啟動、使用哪些權限，以及呼叫同一份程式。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open><summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">四種都合理，但成本不同</span></summary><ul><li><strong>每次全跑：</strong>每張 PR 都取得完整信心，適合測試很小、執行很快的 repo。</li><li><strong>只跑受影響項目：</strong>依 dependency graph 或路徑縮小範圍，回饋快，但分流規則必須可測。</li><li><strong>獨立 pipeline runtime：</strong>本機與不同 CI 平台執行相同 pipeline，換來額外引擎與環境成本。</li><li><strong>分階段驗證：</strong>日常快速、整合候選完整；需要清楚定義何時升級與哪一份結果有效。</li></ul></details>
        <details class="decision-step decision-fold recommended" open><summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">一份邏輯、一支 Action、兩種 repo 範圍</span></summary><ul class="work-definition-list"><li><strong>開發中：</strong>人或 agent 只跑能證明這次修改的 focused check，先取得新鮮輸出再宣稱完成。</li><li><strong>Issue PR → dev：</strong><code>ci_tier.py</code> 依變更路徑選 docs 或 fast；未知路徑才升級為 full。</li><li><strong>高風險邊界：</strong>promotion、hotfix、release recovery、merge queue 與手動執行都走 full。</li><li><strong>同一套邏輯：</strong>GitHub Actions 只有一個 <code>verify</code> job，最多執行 30 分鐘，只呼叫 repo 內既有腳本。</li><li><strong>一般 repo：</strong>完整入口是 <code>scripts/verify</code>；<strong>repo-template：</strong>改用 <code>scripts/verify-template.sh</code>，額外驗證模板、生成結果與既有 repo 導入。</li></ul></details>
      </div>
      <aside class="config-guidance" data-config-direct="true"><strong>模板功能與客製化</strong><ul><li><strong>分級依據：</strong><code>scripts/ci_tier.py</code> 判斷變更範圍；<code>docs/ci-policy.md</code> 說明階段與升級條件。</li><li><strong>快速驗證：</strong><code>scripts/verify-fast</code> 已存在於 root 與生成模板；一般 repo 的完整入口是 <code>scripts/verify</code>。</li><li><strong>模板額外驗證：</strong><code>scripts/verify-template.sh</code> 只屬於 repo-template，不應成為每個採用 repo 的成本。</li><li><strong>目前邊界：</strong>只恢復 <code>.github/workflows/ci.yml</code>；release、promotion、安全掃描、遠端治理、部署與排程仍由各自 Journey 決定。</li></ul></aside>
      <p class="method-reference reference">具體工具與功能來源見<a href="#similar-tools">相似工具</a>；每個階段實際使用的程式與 Action 現況見<a href="#testing">CI/CD 設定</a>。</p>
{{< /legacy >}}

{{< basic >}}
- **開發中：**只跑能證明本次修改的 focused check。
- **Issue PR → dev：**依路徑選 docs 或 fast；未知路徑才升級為 full。
- **高風險邊界：**promotion、hotfix、release recovery、merge queue 與手動執行走 full。
- **Action：**只有一個 `verify` job，最多執行 30 分鐘，只呼叫 repo 內既有腳本。
- **責任：**一般 repo 的完整入口是 `scripts/verify`；repo-template 改用 `scripts/verify-template.sh`。

測試邏輯只寫在 scripts／tests；本次只恢復 `.github/workflows/ci.yml`。具體比較見[相似工具](#similar-tools)，執行位置見 [CI/CD 設定](#testing)。
{{< /basic >}}
{{< /slide >}}

{{< slide key="pr" track="pr" eyebrow="步驟 04" title="小 PR 通過證據再合併" subtitle="Issue 先進整合分支；promotion 才把已驗證成果送進 main。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 4｜<span class="accent">小 PR 通過證據再合併</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>CI 就是可攜式 integration layer；Issue 先進 delivery branch，完成 Milestone 或固定批次時才 promotion 到 main。</p>
      </header>
      <p class="context-line"><strong>問題與目的｜</strong>每張 PR 都送 main 會同時放大完整 CI 與發版次數；分支與 workflow 必須一起分層，才能在日常保留快回饋、在交付邊界集中完整信心。</p>
      <div class="decision-strip">
        <article class="decision-step"><span class="step-label">其他常見做法</span><h3>不把所有變更都當成一種交付</h3><ul><li><strong>每張 PR 進 main：</strong>一般變更也重跑完整矩陣並推動發版</li><li><strong>單一永久 dev：</strong>多個 Milestone 互相等待，候選內容難以隔離</li><li><strong>每張孤立 Issue 建 Milestone：</strong>失去 Story 的意義，只是在規避批次</li></ul></article>
        <article class="decision-step recommended"><span class="step-label">我們的選擇</span><h3>不同 Issue 進對應 delivery branch，main 再受審查地回流</h3><p><strong>Milestone：</strong><code>type/&lt;Issue&gt;-*</code> PR 進 <code>dev/m&lt;Milestone&gt;-*</code>；可同時有多條，完成後各自跑 full＋canary promotion。<br><strong>孤立工作：</strong>一般 Issue 進 <code>dev/next</code>，固定 release window 批次 promotion；確實要獨立 soak／canary 才使用一次性的 <code>dev/i&lt;Issue&gt;-*</code>，完成後刪除。只有 standalone <code>fix/*</code>＋<code>hotfix</code> 可直接 main。<br><strong>同步：</strong><code>main</code> 前進後，每條 active delivery branch 的 owner 以 <code>sync/main-to-*</code> PR 納入結果；blocked／unknown 自動寫入能力回到同一套手動 PR，不直接 push 或改寫歷史。</p></article>
      </div>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>選 delivery、main-only 或 dev：</strong><code>copier.yml</code> → <code>branch_strategy</code>，結果存入 <code>.csarc/profile.json</code></li><li><strong>核對 route、Issue、branch 編號、標題與同步：</strong><code>pr-policy.yml</code>＋<code>delivery-maintenance.yml</code>＋<code>promotion.yml</code></li><li><strong>完整操作與遷移：</strong><code>docs/ci-policy.md</code> 含孤立 Issue 決策樹、雙 Milestone walkthrough、promotion checklist、回復與降級</li></ul></aside>
      <p class="reference">Ref. <a href="https://github.com/home-assistant/core/blob/dev/.github/workflows/ci.yaml" target="_blank" rel="noreferrer">Home Assistant CI</a>; <a href="https://github.com/vercel/next.js/blob/canary/.github/workflows/build_and_test.yml" target="_blank" rel="noreferrer">Next.js build/test</a>; <a href="https://github.com/rust-lang/rust/blob/main/.github/workflows/ci.yml" target="_blank" rel="noreferrer">Rust CI</a>; <a href="https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore" target="_blank" rel="noreferrer">GitHub workflow filters</a>. Accessed August 24, 2026. 採用的是分流與交付邊界原則，不照抄其 branch 名稱。</p>
{{< /legacy >}}

{{< basic >}}
| 工作類型 | PR 目的地 | 進入 `main` 的方式 |
| --- | --- | --- |
| Milestone Issue | `dev/m<Milestone>-*` | Milestone promotion PR |
| 一般 standalone Issue | `dev/next` | 固定 release window 批次 promotion |
| 需獨立 soak／canary 的 Issue | 暫時 `dev/i<Issue>-*` | 該 Issue 的 promotion PR |
| 緊急修正 | `main` | 僅限 standalone `fix/*`＋`hotfix` label |

{{< detail key="pr-version-intent" title="分支、同步與版本意圖的實際規則" >}}
- 工作分支固定為 `type/<Issue>-short-slug`，PR 連回同號未結案 Issue。
- `main` 前進後，active delivery branch owner 以 `sync/main-to-*` PR 納入結果，不直接 push 或改寫歷史。
- `feat`、`fix` 與 `!` 只在合併後由 default-branch history 決定 SemVer；open PR 不預留版本號。
- `pr-policy.yml`、`delivery-sync.yml` 與 `promotion.yml` 核對 route、Issue、標題、同步與 promotion 證據。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="supply" track="supply" eyebrow="步驟 05" title="風險立即看見，升版不搶第一天" subtitle="未知惡意新版、已公開漏洞與成品內容是三種不同問題。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 5｜<span class="accent">風險立即看見，升版不搶第一天</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>安全、檔案證據與「版本能否安裝」是不同問題；依賴更新也是日常維護的一環。</p>
      </header>
      <p class="context-line"><strong>問題與目的｜</strong>第三方套件出現漏洞時要立刻知道；一般新版則先等三天，避免成為供應鏈攻擊最早一批受害者。</p>
      <div class="decision-strip">
        <article class="decision-step"><span class="step-label">其他常見做法</span><h3>不把所有風險都當成同一種更新</h3><ul><li><strong>新版一出就升：</strong>可能成為惡意版本最早一批使用者</li><li><strong>漏洞也等三天：</strong>已知風險不應延後處理</li><li><strong>換成 Renovate：</strong><button class="term-trigger" type="button" aria-expanded="false" aria-controls="renovate-preset-overlay">中央共用更新規則（preset）</button>較靈活，但目前會額外依賴高權限身分</li></ul></article>
        <article class="decision-step recommended">
          <span class="step-label">我們的選擇</span>
          <details class="package-disclosure"><summary><span><span class="tech-name">Dependabot＋OSV＋anchore/sbom-action</span> 已完成</span></summary><div class="package-health"><p><a href="https://github.com/google/osv-scanner" target="_blank" rel="noreferrer">OSV-Scanner</a>｜Apache-2.0；<a href="https://github.com/anchore/syft" target="_blank" rel="noreferrer">Syft</a>｜Apache-2.0。</p><p><strong>Renovate：</strong>AGPL-3.0；#110 決定不換手。Dependabot 使用 GitHub 原生 automation identity，PR 會觸發既有 policy 與 change-aware verify；相依變更才加跑 OSV，workflow 變更才加跑 Zizmor，promotion 與週期排程則兩者都跑，不需要第三方 App 或長效 PAT。pnpm <code>minimumReleaseAge</code> 另保護本機與 CI resolution，<code>trustPolicy: no-downgrade</code> 則保護發布者信任，兩者都保留。</p></div></details>
          <p class="recommendation-copy"><strong>等待：</strong>Dependabot 一般升版先等三天；pnpm 另以嚴格 resolver 阻擋發布未滿三天的直接或間接套件，並拒絕 publisher trust 降級。遇到 trust downgrade 時先確認發布者與 provenance，不要直接停用 policy。<br><strong>漏洞：</strong>OSV 對已公開漏洞立即通知，不套用等待期。<br><strong>內容：</strong><code>uv.lock</code> 保存 SHA-256；<code>pnpm-lock.yaml</code> 保存 integrity hash；發布時解壓真正成品，再附 checksum 與非空 SBOM。<br><strong>限制：</strong>雜湊不證明來源善意，SBOM 也不會自行阻擋漏洞。</p>
        </article>
      </div>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>兩種生態的一般升版等三天：</strong><code>.github/dependabot.yml</code>；<strong>pnpm 本機也嚴格等待：</strong><code>pnpm-workspace.yaml</code></li><li><strong>凍結安裝並比對兩種 lockfile 雜湊：</strong><code>scripts/verify</code></li><li><strong>掃已知漏洞：</strong><code>osv.yml</code>　<strong>發布 checksum／SBOM：</strong><code>release.yml</code></li><li><strong>回報本專案自身的漏洞：</strong><code>SECURITY.md</code>；預設使用實際 repository 的公開 GitHub Issues，不寫死未核准的 email 或 SLA，也不得張貼敏感內容</li></ul></aside>
      <aside id="renovate-preset-overlay" class="config-overlay term-overlay" hidden role="region" aria-label="中央共用更新規則說明">
        <div class="config-overlay-card">
          <button class="config-overlay-close" type="button" aria-label="關閉名詞說明">×</button>
          <h3>中央共用更新規則（preset）是什麼？</h3>
          <p class="term-overlay-copy"><strong>白話說：</strong>把套件更新規則放在一個共用設定；其他 repo 只要寫「沿用這套規則」，之後改一次就能同步等待天數、排程與分組。</p>
          <p class="term-overlay-copy"><strong>何時需要：</strong>repo 變多、各專案設定開始不一致，或 Dependabot 已無法表達共同規則時。</p>
          <p class="term-overlay-copy"><strong>目前決定：</strong>預設保留 Dependabot 與既有 CI/CD checks。自架 Renovate 的 <code>GITHUB_TOKEN</code> 不能建立可正常觸發所有必要檢查的 PR；Mend Renovate App 又要求 organization members read、repository administration read 與 workflow／content／PR write。只有 Dependabot 已無法表達實際跨 repo 政策時才考慮選配安裝。</p>
          <table class="release-policy-matrix" aria-label="Optional integration capability matrix"><thead><tr><th>preflight 狀態</th><th>誰會看到</th><th>下一步</th></tr></thead><tbody><tr><td><code>available</code></td><td>personal repo owner，或同時具 repo admin 的 organization owner</td><td>開啟 <a href="https://github.com/apps/renovate/installations/new" target="_blank" rel="noreferrer">Renovate App 安裝頁</a>，檢查 GitHub 顯示的權限並只選目標 repo；CLI 不代為同意或安裝</td></tr><tr><td><code>request-owner</code></td><td>有 repo admin、但不是 account／organization owner</td><td>把同一安裝入口交給 owner 核准；等待期間保留 Dependabot</td></tr><tr><td><code>fallback</code></td><td>無 admin、權限未知、API 失敗或尚無 GitHub origin</td><td>不假設可安裝，繼續使用 Dependabot 與 required CI/CD checks；推送遠端後可重跑 preflight</td></tr></tbody></table>
          <p class="term-overlay-copy"><strong>導入時檢查：</strong><code>csarc init</code>／<code>adopt</code>／<code>update</code> 會在 origin 可讀時查 owner 類型、repo admin 與 organization membership。新 repo 尚未有 origin 時可先設定 <code>GH_REPO=owner/repo</code>，推送後也能執行 <code>python scripts/release_policy.py preflight --repo owner/repo</code> 重查；整段只讀，不要求長效廣域 PAT。</p>
        </div>
      </aside>
{{< /legacy >}}

{{< basic >}}
| 問題 | 現行控制 | 不代表什麼 |
| --- | --- | --- |
| 太新的套件 | Dependabot 與 pnpm 一般版本等待三天 | 不代表套件沒有既知漏洞 |
| 已公開漏洞 | OSV 立即掃描與告警 | 不驗證下載內容相同 |
| 內容完整性 | `uv.lock` SHA-256、pnpm integrity、release checksum | 不證明發布者善意 |
| 成品組成 | 解壓真正 artifact 後產生 CycloneDX SBOM | SBOM 不會自行阻擋漏洞 |

{{< disclosure key="supply-tools" title="Dependabot＋OSV＋anchore/sbom-action" >}}
Dependabot 保留 GitHub 原生 automation identity，PR 可直接觸發既有 policy 與 change-aware checks，不要求每個 repo 安裝高權限 App 或長效 PAT。pnpm `minimumReleaseAge` 保護本機與 CI resolution，`trustPolicy: no-downgrade` 拒絕 publisher trust 降級。
{{< /disclosure >}}

{{< detail key="supply-boundaries" title="設定位置與 Renovate 決策" >}}
- 更新等待：`.github/dependabot.yml` 與 `pnpm-workspace.yaml`。
- 凍結安裝與 lockfile 完整性：`scripts/verify`。
- 漏洞與發布證據：`osv.yml`、`release.yml`、`SECURITY.md`。

Renovate 的中央 preset 更靈活，但自架 token 無法正常觸發所有必要 checks；Mend App 又要求 organization members read、repository administration read，以及 workflow／content／PR write。目前保留 Dependabot；只有多 repo 政策真的無法表達時才重新評估。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="deploy" track="deploy" eyebrow="步驟 06" title="版本規則與成品接續" subtitle="先驗證 promotion 來源，再依平台當下能力選安全交付模式。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 6｜<span class="accent">版本規則與成品接續</span></h2>
        <p class="subtitle"><strong>Release 路徑依已驗證的 promotion 邊界與當下能力選擇：</strong>PR 與成品交接能力都確認時使用 release-please；否則只在最新 main 已含經審查的版本與 CHANGELOG 時直接交付，再不行就明確停在 verification-only。</p>
      </header>
      <p class="context-line"><strong>設計流程｜</strong>Issue PR 只宣告 patch／minor／major／no-release 意圖；Milestone 完成、<code>dev/next</code> 固定窗口、isolated canary 或 hotfix 才形成 release 邊界，整批取最高意圖，全部 no-release 就略過。</p>
      <div class="decision-strip">
        <article class="decision-step"><span class="step-label">其他常見做法</span><h3>不為版本號另加一套平台</h3><ul><li><strong>Changesets：</strong>適合 npm workspace；CI-only／Python 案會多背 Node 設定</li><li><strong>Nx release：</strong>適合既有 Nx 大型 workspace；本案只需一個 release unit</li><li><strong>profile 各自編號：</strong>會增加相依矩陣與升級對版成本</li></ul></article>
        <article class="decision-step recommended"><span class="step-label">我們的選擇</span><details class="package-disclosure"><summary><span><span class="tech-name">promotion-gated adaptive release</span>＋單一 SemVer</span></summary><div class="package-health release-policy-health"><p><a href="https://github.com/googleapis/release-please" target="_blank" rel="noreferrer">googleapis/release-please</a>｜Apache-2.0｜持續維護。</p><p><strong>來源證據：</strong>release-source 先核對 promotion 的 full <code>verify</code>、canary state、納入 PR 與 main tree identity；非 promotion／hotfix 的 main commit 只能 verification-only。</p><p><strong>三態能力：</strong><code>allowed</code>、<code>blocked</code>、<code>unknown</code> 分別記錄 Actions PR、contents、Release 與 dispatch；403、409、無 remote 或無管理權都不會被誤當 allowed。</p><table class="release-policy-matrix" aria-label="Release policy capability matrix"><thead><tr><th>前提</th><th>選擇</th><th>行為與保證</th><th>限制與 fallback</th></tr></thead><tbody><tr><td>來源有效且四項 allowed</td><td>Release PR</td><td>可審查版本／changelog；合併後帶 source run ID dispatch 成品</td><td>任一能力漂移就不再選用</td></tr><tr><td>來源有效；PR blocked／unknown；其餘 allowed</td><td>Direct</td><td>只為已版本化且含 CHANGELOG 的最新 main 配置 tag；亂序 run no-op</td><td>缺少版本 commit 時轉為 verification-only，需維護者先開 PR</td></tr><tr><td>來源無效或任一交付寫入非 allowed</td><td>Verification only</td><td>保存 machine-readable artifact</td><td>不建立 release；後續 run 重新判斷</td></tr></tbody></table><p class="reference">Ref. <a href="https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow" target="_blank" rel="noreferrer">GitHub workflow trigger docs</a> and live workflow runs, accessed August 24, 2026.</p></div></details><p><strong>收斂：</strong>direct mode 重讀 default branch head，只有最新 main commit 且 source、tag、CHANGELOG、promotion evidence 一致時才能交付；concurrency 不必保證 FIFO。<br><strong>成品：</strong>workflow 不監聽任意 tag push，只接受 release-source run ID；tag checkout 產生 digest、SBOM／attestation，不重跑 promotion 已完成的 full runtime CI。</p></article>
      </div>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>promotion 與 release-source：</strong><code>promotion.yml</code>＋<code>scripts/promotion_gate.py</code>＋<code>release-please.yml</code></li><li><strong>能力與版本配置：</strong><code>scripts/release_policy.py</code>；CLI 做唯讀 preflight，workflow 每次重新偵測</li><li><strong>查詢證據：</strong>promotion／release-source artifact 保留 90 天，PR、Issue、Milestone、commit 與 tag 作長期索引</li></ul></aside>
      <aside class="selection-note"><strong>目前邊界</strong><span>不要求導入者建立 PAT、GitHub App 或修改無權控制的組織政策；若 contents、Release 或 dispatch 無法確認，workflow 只完成驗證並明確告警，不宣稱已自動發版。Python 排程升版 App 仍是另一個選配身份。</span></aside>
      <table class="decision-register" aria-label="版本來源與同步範圍">
        <thead><tr><th>版本範圍</th><th>單一來源</th><th>必須同步</th><th>獨立狀態</th></tr></thead>
        <tbody>
          <tr><td>公版與 CLI Release</td><td>root <code>.release-please-manifest.json</code></td><td>root 版本檔、README／docs current marker、CHANGELOG、tag、Release 與成品</td><td>無</td></tr>
          <tr><td>Copier 公版 revision</td><td>已發布 tag＋完整 commit SHA</td><td>Release provenance、<code>.copier-answers.yml</code> 的 <code>_commit</code></td><td>不另編版本</td></tr>
          <tr><td>生成專案 Release</td><td>生成後的 <code>.release-please-manifest.json</code></td><td>該專案自己的 manifest、package、CHANGELOG、tag 與成品</td><td>從 <code>0.1.0</code> 開始，不跟隨公版版本</td></tr>
        </tbody>
      </table>
      <p class="context-line"><strong>SemVer scope｜</strong>整份公版只用一個 SemVer：<code>fix(scope)</code> 升 patch、<code>feat(scope)</code> 升 minor、<code>!</code> 升 major；scope 可標 <code>ci</code>、<code>python</code>、<code>typescript</code> 或 <code>template</code>，只要任何已支援 profile 不相容，就視為整份公版的破壞性變更。</p>
      <aside class="selection-note"><strong>選配登記：PyPI／npm 發布</strong><span>GitHub Release 是所有 profile 的共同基線；registry 是生成專案依語言分開選配的能力，預設全部關閉。Root CLI 只隨 GitHub Release 交付，不發布到 PyPI，也沒有 registry publishing job。生成專案的 PyPI／npm job 使用 GitHub environment 與 OIDC 短效憑證，不讀取長效 registry token；CI/CD-only 不產生 registry job。啟用前，package owner 必須在 registry 登記完全相符的 organization／repository、workflow <code>release.yml</code> 與 environment。PyPI 首次發布可先建立 pending publisher；npm 則需由既有 package owner 建立 trusted publisher，並使用 GitHub-hosted runner、Node 22.14+ 與 npm 11.5.1+。</span></aside>
{{< /legacy >}}

{{< basic >}}
| 前提 | 模式 | 行為與保證 |
| --- | --- | --- |
| 來源有效，PR／contents／Release／dispatch 都 `allowed` | Release PR | 版本與 changelog 可審查；合併後以 source run ID 產生成品 |
| 來源有效，PR `blocked/unknown`，其餘 `allowed` | Direct | 只為已版本化且含 CHANGELOG 的最新 `main` 建 tag；亂序 run no-op |
| 來源無效或任一交付寫入不是 `allowed` | Verification only | 保存 machine-readable evidence，不建立或宣稱 Release |

{{< disclosure key="adaptive-release" title="promotion-gated adaptive release＋單一 SemVer" >}}
Release source 先核對 full `verify`、canary state、納入 PR 與 main tree identity。所有 profile 共用一個公版 SemVer：`fix(scope)` 升 patch、`feat(scope)` 升 minor、`!` 升 major；任何已支援 profile 不相容都視為整份公版的 breaking change。
{{< /disclosure >}}

{{< detail key="deploy-ordering" title="交付順序、成品與 registry 邊界" >}}
Direct mode 在寫入前重讀 default branch head，只有最新 `main` 且 source、tag、CHANGELOG、promotion evidence 一致才交付，不假設 workflow concurrency 提供 FIFO。成品 workflow 只接受 release-source run ID，產生 digest、SBOM 與 attestation，不監聽任意 tag push，也不重跑已完成的 full CI。

GitHub Release 是所有 profile 的共同基線。PyPI／npm 分開選配、預設關閉，使用 GitHub environment 與 OIDC 短效憑證；不保存 registry token。能力偵測與版本配置在 `scripts/release_policy.py`，promotion gate 在 `scripts/promotion_gate.py`。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="governance" track="governance" eyebrow="步驟 07" title="先辨識 GitHub 能力，再套用真的管制" subtitle="目前組織實測是 Free＋private，因此 main 尚未受 Ruleset 強制保護。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>先辨識 GitHub 方案，<span class="accent">再套用真的能生效的管制</span></h2>
        <p class="subtitle"><strong>基本導入｜</strong>同一份公版依 Free、Team、Enterprise 與實際 API 能力調整；不把付費功能假裝成已啟用。</p>
      </header>
      <p class="context-line"><strong>目前實測｜</strong><code>Innoguard-Cyber-Arch</code> API 回報 Free＋private；因此 <code>main</code> 現在確實沒有強制保護，CI 紅燈仍可能被有權限者繞過。</p>
      <div class="plan-grid">
        <article class="plan-card current"><h3>Free <span class="plan-state">目前</span></h3><p><strong>提出審查要求，強制能力降級：</strong>governance workflow 會從 <code>.github/REVIEWERS</code> 輪派一位非作者 reviewer；private repo 只把期望 Ruleset 保留在 <code>policies/rulesets.json</code>，因為 REST 與 GraphQL 建立 API 都會拒絕。check 標示 DEGRADED，CI 與 release 照常執行。</p><ul><li>一位設定的同事會收到 review request，但 team request 與 merge gate 仍不可用</li><li>CI 與留言提供紀錄，但無法取代 merge gate</li></ul></article>
        <article class="plan-card team"><h3>Team <span class="plan-state">最低建議</span></h3><p><strong>再加上：</strong>private repo Ruleset、protected branches、強制核准、CODEOWNER 與必要檢查。</p><ul><li>同一個 CODEOWNERS team 必須存在並有 repo write access</li><li>公版即可套用現有 repo Ruleset</li></ul></article>
        <article class="plan-card enterprise"><h3>Enterprise <span class="plan-state">組織級</span></h3><p><strong>再加上：</strong>SAML SSO／SCIM、internal repo、private/internal 部署保護、私有 Pages、稽核串流與 IP 限制。</p><ul><li>組織／Enterprise Ruleset 可集中治理</li><li>目前只偵測並提示，不自動改組織設定</li></ul></article>
      </div>
      <aside class="selection-note"><strong>部署原則</strong><span><code>plan</code> 先查帳號方案、repo 可見性、repository teams 與 Ruleset API；team 不存在、不可見或沒有 repo write access 時直接停止，不能再被 Free private 的降級路徑掩蓋。導入時可設定一到多位 reviewers；非 draft PR 的 workflow 只 checkout base branch，排除作者後輪派一位。Free private 不支援 team request，也無法強制核准。Web UI 可供管理員人工預建 disabled Ruleset，但公開 REST／GraphQL API 無法自動建立。腳本本身不會改可見性。依序執行 <code>plan</code>、<code>apply</code>、<code>check</code>；可修正差異 fail-closed，不支援的 Ruleset 或受限制的管理欄位回報具體 DEGRADED。完整管理欄位驗證應由管理員在可信任 checkout 使用 Administration read 憑證，不把該 token 暴露給 PR 程式碼。Enterprise 的身分、網路與稽核政策另經組織層審查；Code Security／Secret Protection 另購。</span></aside>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>查方案與 API：</strong><code>scripts/apply-repository-settings.sh plan</code></li><li><strong>套用支援的設定：</strong><code>scripts/apply-repository-settings.sh apply</code></li><li><strong>比對全部可觀察設定：</strong><code>scripts/apply-repository-settings.sh check</code> 比對 CODEOWNERS、repository、Actions、政策標籤與有效 Ruleset</li><li><strong>排程偵測漂移：</strong><code>.github/workflows/governance-drift.yml</code>（daily cron）每天重跑 <code>check</code>；可修正 drift 會開立或更新追蹤 Issue，DEGRADED 的具體差異留在 workflow log 與 warning annotation，不會誤稱為沒有 drift。兩次快照之間曾變更又恢復的事件仍需 audit log 或組織層監控，下發專案以 <code>enable_governance_drift_check</code> 選配</li></ul></aside>
      <table class="decision-register" aria-label="GitHub 方案與 apply／check 行為對照">
        <thead><tr><th>GitHub 方案與可見性</th><th><code>apply</code> 結果</th><th><code>check</code>／PR／CI/CD 行為</th></tr></thead>
        <tbody>
          <tr><td>Free＋public</td><td>透過 REST 套用並啟用 Ruleset</td><td>驗證 <code>main</code> 的有效規則；缺少或不符即失敗</td></tr>
          <tr><td>Free organization＋private</td><td>套用基本設定，並把期望 Ruleset 保留在 <code>policies/rulesets.json</code>；公開 API 無法建立 Ruleset</td><td>從設定名單輪派一位個別 reviewer，並標示 <code>DEGRADED</code>；team request、紅燈或未核准都不能成為 merge gate</td></tr>
          <tr><td>Pro 個人帳號＋private</td><td>套用並啟用 Ruleset</td><td>與 Free public 相同</td></tr>
          <tr><td>Team／Enterprise organization＋private</td><td>確認 CODEOWNERS team 後套用並啟用 Ruleset</td><td>必要審查、CODEOWNER 與 status checks 成為 merge gate；不符政策時 fail-closed</td></tr>
        </tbody>
      </table>
      <p class="reference">Ref. <a href="https://docs.github.com/en/get-started/learning-about-github/githubs-plans" target="_blank" rel="noreferrer">GitHub plans</a>；<a href="https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets" target="_blank" rel="noreferrer">About rulesets</a>. Accessed August 21, 2026.</p>
{{< /legacy >}}

{{< basic >}}
| GitHub 狀態 | `apply` 結果 | 實際門禁 |
| --- | --- | --- |
| Free＋public | 透過 REST 套用 Ruleset | 缺少或不符即失敗 |
| Free organization＋private | 套基本設定，期望 Ruleset 留在 `policies/rulesets.json` | 輪派個別 reviewer 並標示 `DEGRADED`；無 merge gate |
| Pro 個人＋private | 套用 Ruleset | 與 Free public 相同 |
| Team／Enterprise organization＋private | 確認 CODEOWNERS team 後套用 Ruleset | 審查、CODEOWNER 與 status checks 成為 merge gate |

{{< detail key="governance-observation" title="實際操作與觀察限制" >}}
依序執行 `scripts/apply-repository-settings.sh plan`、`apply`、`check`。`check` 比對 CODEOWNERS、repository、Actions、政策 labels 與有效 Ruleset；`.github/workflows/governance-drift.yml` 每日重跑，可修正 drift 會開立或更新追蹤 Issue。

排程檢查是快照：兩次執行之間曾變更又復原的事件仍需 GitHub audit log 或組織層監控。完整管理欄位應由管理員在可信任 checkout 使用 Administration read 憑證，不把 token 暴露給 PR 程式碼。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="template-release" track="template-release" eyebrow="步驟 08" title="Copier 保持同步，公版也吃自己的規則" subtitle="模板錯誤會一次影響多個專案，因此建立、導入與更新都要實跑。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>Copier 保持同步，<span class="accent">公版本身也吃自己的規則</span></h2>
        <p class="subtitle"><strong>基本導入。</strong><code>template/</code> 是下發內容唯一來源；root 只因 GitHub 讀取慣例保留公版自己的治理設定，43 對逐位元組相同的檔案由產生腳本從 root 生成 <code>template/</code> 副本。</p>
      </header>
      <p class="context-line"><strong>問題與目的｜</strong>模板錯誤會一次影響多個專案；每次修改都要真的建立新案、導入既有案，再讓已導入的 repo 接收更新並通過完整驗證。</p>
      <div class="decision-strip">
        <article class="decision-step"><span class="step-label">其他常見做法</span><h3>這次不選，因為無法持續同步或驗證</h3><ul><li><strong>GitHub Template：</strong>只複製一次，不記得來源與答案</li><li><strong>PyScaffold：</strong>可參考 Python 結構，但會形成第二套更新機制</li><li><strong>只驗 YAML：</strong>無法證明新案、既有案與更新真的能跑</li></ul></article>
        <article class="decision-step recommended"><span class="step-label">我們的選擇</span><details class="package-disclosure"><summary><span><span class="tech-name">Copier</span>＋root dogfood＋建立／更新回歸</span></summary><div class="package-health"><p><a href="https://github.com/copier-org/copier" target="_blank" rel="noreferrer">copier-org/copier</a>｜MIT｜公開、未封存且持續維護。</p><p><strong>採用原因：</strong>記錄來源、語言與答案，能把新版模板套回既有 repo；衝突留給 PR 由人處理。</p></div></details><p><strong>建立：</strong>CI/CD-only、Python-only、TypeScript-only、混合與最低 Python 都實跑驗證。<br><strong>導入與更新：</strong>adopt／update dry-run 先預覽，確認後只遷移舊 CSARC 結構；接著對同一 repo 執行下一版 Copier update、確認產品目錄未被覆寫，最後執行生成專案的完整驗證。<br><strong>版本：</strong>公版四種組合共用一個 SemVer；Python 與 Node 基線則各自滿三十天觀察後再前進。</p></article>
      </div>
      <p class="context-line"><strong>root／template 配對檔案｜</strong>43 對 workflow、policy、文件、script 與 test（例如 <code>promotion.yml</code>、<code>docs/ci-policy.md</code>、<code>scripts/promotion_gate.py</code>）在 root 與 <code>template/</code> 之間逐位元組相同；過去只靠 <code>verify-template.sh</code> 在 CI 用 <code>diff</code> 事後比對，任何一邊漏改要等驗證跑完才被抓到。現在 <code>scripts/sync-paired-files.sh</code> 把 root 當成唯一來源：本機執行它會立即重新產生每個 <code>template/</code> 副本；加 <code>--check</code> 則不寫檔，只驗證每個副本是否符合產生腳本的確定性輸出（內容與可執行位元），任何一對不一致就印出差異並失敗。<code>verify-template.sh</code> 已改成呼叫 <code>--check</code>，並用一段複製到暫存目錄、蓄意注入內容與權限落差、確認失敗、重新產生、確認通過的回歸測試證明這個機制會擋下漂移。<code>dependabot.yml</code>、<code>.gitignore</code> 等僅因 Jinja 變數不同的檔案不在此列，仍由既有的「產生一個實案並與 root 比對」測試把關；<code>AGENTS.md</code>／<code>README.md</code> 等文件因 root 與下游專案的治理內容本來就不同，不屬於重複維護，故未強行合併。</p>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>下發來源、語言組合、保留路徑與功能開關：</strong><code>template/</code>＋<code>copier.yml</code></li><li><strong>root-only CI 與建立／導入／更新驗證：</strong><code>.github/</code>＋<code>scripts/verify-template.sh</code>；生成 repo 不會收到這支腳本或 template release workflows</li><li><strong>語言基線與三十天觀察：</strong><code>profiles/catalog.yaml</code>；<strong>Python 自動升版：</strong><code>python-version-policy.yml</code></li><li><strong>root／template 配對檔案的單一來源與漂移檢查：</strong><code>scripts/sync-paired-files.sh</code></li></ul></aside>
{{< /legacy >}}

{{< basic >}}
- `template/` 是下發內容來源；root 保留公版本身的 GitHub 治理與 dogfood 設定。
- CI/CD-only、Python、TypeScript、混合與最低 Python 組合都建立後驗證。
- 既有 repo 先用 adopt／update dry-run 預覽；確認後只遷移舊 CSARC 結構，再執行下一版 Copier update 並確認產品內容未被覆寫。

{{< disclosure key="copier-update" title="Copier＋root dogfood＋建立／更新回歸" >}}
[Copier](https://github.com/copier-org/copier) 記錄來源、語言與答案，能把新版公版套回可自行修改的既有 repo；衝突保留在短分支與 PR 由人處理。GitHub Template 只複製一次，PyScaffold 則會形成第二套更新機制，因此不採用。
{{< /disclosure >}}

{{< detail key="template-release-scope" title="單一來源、版本基線與 root-only 邊界" >}}
`scripts/sync-paired-files.sh` 讓 root 成為成對檔案的單一來源，`--check` 驗證副本內容與權限。`profiles/catalog.yaml` 保存語言基線與真實 pilot 狀態；Python 與 Node 基線各自觀察三十天後才前進。

`scripts/verify-template.sh` 只在公版 repo 實跑建立／導入／更新 fixture，不會下發到 consuming repository；生成 repo 使用較小的 `scripts/verify`。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="docs-site" track="docs-site" eyebrow="步驟 09" title="單檔永遠可交付" subtitle="Hugo 管內容結構，既有 renderer 打包成可離線轉寄的 HTML。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>單檔永遠可交付，<span class="accent">平台能力只做加成</span></h2>
        <p class="subtitle"><strong>已確認選型。</strong><code>docs/index.html</code> 必須可下載、轉寄並用 <code>file://</code> 離線開啟；Pages、外部託管與 CDN 都不是 portable baseline。</p>
      </header>
      <p class="context-line"><strong>問題與目的｜</strong>保留特殊簡報設計與單檔交付，同時避免內容、樣式、互動、選型來源與逐字測試繼續綁在同一個人工維護檔案。</p>
      <div class="decision-strip">
        <article class="decision-step"><span class="step-label">不採用</span><h3>不把交付限制誤當維護方式</h3><ul><li><strong>直接手改單檔：</strong>可以離線，但來源、呈現與測試高度耦合</li><li><strong>runtime 多檔載入：</strong>轉寄容易漏檔，<code>file://</code> 行為也受瀏覽器限制</li><li><strong>立刻導入文件平台：</strong>目前沒有多頁搜尋、翻譯或跨 repo catalog 的實證需求</li><li><strong>自動保存完整聊天：</strong>會混入未確認假設、敏感脈絡與噪音</li></ul></article>
        <article class="decision-step recommended"><span class="step-label">我們的選擇</span><details class="package-disclosure"><summary><span><span class="tech-name">可維護來源 → self-contained HTML</span></span></summary><div class="package-health"><p><strong>交付契約：</strong>CSS、JavaScript、font、SVG 與圖片全部內嵌；外部連結可保留，但離線時不影響內容與操作。</p><p><strong>來源契約：</strong><code>docs/adr/</code> 保存 canonical Architecture Decision Records（ADR）；renderer、基礎設計與驗證由公版維護，專案內容與允許的 theme overrides 由 consuming repo 維護。</p><p><strong>互動收納：</strong>agent 只把使用者已確認的 durable constraint 摘要進 Issue，再經 PR 寫入 ADR；不保存完整逐字稿。</p></div></details><p><strong>所有環境：</strong>產生並驗證 committed bundle。<br><strong>Actions allowed：</strong>再增加重建比對與 artifact。<br><strong>核准 host 與寫入權限 allowed：</strong>再增加 preview／publish／access control。<br><strong>blocked／unknown：</strong>回退單檔交付，不宣稱已部署。</p></article>
      </div>
      <aside class="config-guidance"><strong>決策與落地</strong><ul><li><strong>Canonical ADR：</strong><code>docs/adr/portable-decision-site.md</code></li><li><strong>可維護來源：</strong><code>site/</code> 分開內容、樣式、互動與原始圖片；renderer 產生 <code>docs/index.html</code> 並拒絕外部 runtime asset</li><li><strong>生成專案：</strong>公版更新 <code>site/</code> 與 renderer，專案保有 <code>docs/site-content.js</code> 與 <code>docs/site-theme.css</code></li><li><strong>安全邊界：</strong><code>noindex</code> 不是存取控制；受控發布保護入口，但下載後的離線檔仍可能被轉寄</li><li><strong>追蹤：</strong><a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/178" target="_blank" rel="noreferrer">Issue #178</a></li></ul></aside>
{{< /legacy >}}

{{< basic >}}
- `site/content/` 是中英文 Markdown 來源；兩種語言必須有相同 content keys。
- `site/static/styles.css` 保留特殊簡報視覺；Hugo shortcode 將內容轉成共用結構。
- `scripts/render_site.py` 內嵌 CSS、JavaScript、font 與圖片，拒絕外部 runtime asset。

{{< disclosure key="portable-bundle" title="Markdown＋Hugo → self-contained HTML" >}}
`docs/adr/` 保存 canonical 選型；Hugo 負責內容與 HTML；未修改的 renderer 只處理資產內嵌與安全檢查。最終的 `docs/index.html` 可用 `file://` 離線開啟，不依賴 Pages、CDN 或 JavaScript package runtime。
{{< /disclosure >}}

{{< detail key="docs-site-access" title="存取與維護邊界" >}}
`noindex` 與 `robots.txt` 只能降低意外擴散，不是存取控制。核准 host 可保護入口，但下載後的離線 HTML 仍可能被轉寄。Agent 只把使用者已確認的 durable constraint 摘要進 Issue，再經 PR 寫入 decision record，不保存原始對話逐字稿。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="rollout" track="rollout" eyebrow="步驟 10" title="分階段導入，每一步都能停" subtitle="成熟度看實際證據，不以日期或檔案存在假裝完成。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>分階段導入，<span class="accent">每一步都能驗證，也能停下來</span></h2>
        <p class="subtitle"><strong>三層導入｜</strong>基本能力現在就隨模板產生；未來與可選能力先寫清楚觸發門檻，不用空檔案假裝完成。</p>
      </header>
      <p class="context-line"><strong>問題與目的｜</strong>一次導入模板、CI、部署、監控與 AI，團隊很難判斷哪裡出錯；分期後每一步都有完成條件。</p>
      <div class="decision-strip">
        <article class="decision-step"><span class="step-label">其他常見做法</span><h3>不按聲量或日期一次把功能全打開</h3><ul><li><strong>一次切換：</strong>錯誤會同時擴散到所有專案</li><li><strong>固定日期解鎖：</strong>時間到了不代表使用條件已成熟</li><li><strong>所有語言同時上：</strong>未驗證的 profile 只是空承諾</li></ul></article>
        <article class="decision-step recommended"><span class="step-label">我們的選擇</span><h3>三層不是日期，而是導入條件</h3><p><strong>基本導入：</strong>CI/CD-only、Python-only、TypeScript-only、混合 profile，以及 Issue／spec、PR／CI、本機驗證、OSV、依賴政策與 repo 內部網站已完成。Free 會先查能力並套可用設定；private repo 不宣稱有 Ruleset 強制保護。<br><strong>已完成線上驗證：</strong>release handoff、可追溯成品、Release attestation 消費端驗證，以及第一個真實 CI-only 下游 repo 的導入與 Copier 更新；共用治理與 CI-only composition 為 beta。<br><strong>仍在試行：</strong>Python、TypeScript 與混合 composition 仍各需一個真實 consuming repo 才能升為 beta。<br><strong>未來／可選：</strong>中央 catalog／治理平台、多 repo、Go／Rust、網站託管／登入、Hugo、部署、監控、RAG、自主 Agent。</p></article>
      </div>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>哪些 profile 已可用或仍在規劃：</strong><code>profiles/catalog.yaml</code></li><li><strong>先查方案再套可用設定：</strong><code>scripts/apply-repository-settings.sh</code>；Ruleset／App 條件備妥後再啟用</li><li><strong>建立與更新路徑是否都能通過：</strong><code>scripts/verify-template.sh</code></li></ul></aside>
{{< /legacy >}}

{{< basic >}}
| 層級 | 目前狀態 |
| --- | --- |
| 基本能力 | 四種 profile、Issue／spec、PR／CI、本機驗證、OSV、依賴政策與 repo 網站已有可執行檔案 |
| 已完成線上驗證 | release handoff、可追溯成品、attestation 消費端驗證、第一個 CI-only 下游導入與更新 |
| 仍在試行 | Python、TypeScript、混合 composition 各缺一個真實 consuming repo pilot |
| 未來／選配 | 中央 catalog／治理平台、Go／Rust、託管登入、部署、監控、RAG、自主 Agent |

{{< detail key="rollout-evidence" title="為什麼不一次全部打開" >}}
一次切換會讓錯誤同時擴散；固定日期不代表使用條件成熟；沒有真實採用證據的 profile 只是空承諾。`profiles/catalog.yaml` 分開記錄合成驗證與 consuming repo evidence，`scripts/verify-template.sh` 證明建立與更新路徑能跑，但不能取代 pilot。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="bridge" eyebrow="2025-05 → 2026-08" title="保留核心，調整實作方式" subtitle="五月版 SDLC 原則持續有效，但路由、能力偵測與交付邊界更精確。" class="legacy-slide bridge-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>五月版 SDLC 盤點｜<span class="accent">保留核心，調整實作方式</span></h2>
        <p class="subtitle">給已看過五月版的團隊承先啟後：保留方法，修正實作與導入層級；點選每列可看三句判斷。</p>
      </header>
      <table class="bridge-table" aria-label="五月版簡報與目前設計的逐頁對照">
        <colgroup><col class="page-col"><col class="topic-col"><col class="status-col"><col class="decision-col"></colgroup>
        <thead><tr><th>頁次</th><th>五月版主題</th><th>結論</th><th>目前決定（點選）</th></tr></thead>
        <tbody>
          <tr><td>p.3</td><td>SDLC 核心階段</td><td><span class="bridge-status keep">保留</span></td><td><details class="bridge-detail drop-down"><summary>把計畫到監控集中在 GitHub</summary><div class="bridge-popover"><p><strong>五月版｜</strong>計畫、開發、測試、部署、監控的核心順序保留。</p><p><strong>本次判斷｜</strong>工作單、模板、合併申請、自動檢查與交付設定都放在 GitHub，方便持續維護。</p><p><strong>落地方式｜</strong>不是每個專案都要部署與監控，但都先遵守工作規劃、變更審查與驗證規則。</p></div></details></td></tr>
          <tr><td>p.4</td><td>Jira Ticket</td><td><span class="bridge-status adjust">調整</span></td><td><details class="bridge-detail drop-down"><summary>每次改動先有最小 GitHub Issue</summary><div class="bridge-popover"><p><strong>五月版｜</strong>原本用 Jira 的 Epic → Story → Task 分工；本次只保留必要的 GitHub Issue、Milestone 與 spec。</p><p><strong>本次判斷｜</strong>一次性工作選一種類型、寫問題與完成條件；複雜需求先開規劃 Issue，再由核准 spec 建立實作 Issue。新增範圍另開 Issue。</p><p><strong>落地方式｜</strong><code>work-item.yml</code> 有類型、問題與完成條件兩個必填欄位，另加一個選填補充；<code>issue-triage.yml</code> 指派開單者；PR workflow 核對標籤、分支與同號未結案 Issue。</p></div></details></td></tr>
          <tr><td>p.5</td><td>版本控制</td><td><span class="bridge-status adjust">調整</span></td><td><details class="bridge-detail drop-down"><summary>delivery branch 是 CI 整合邊界，不假裝成實體環境</summary><div class="bridge-popover"><p><strong>五月版｜</strong>保留平行分支，但不要求每案具備實體 DEV 環境。</p><p><strong>本次判斷｜</strong>並行 Milestone 各用 <code>dev/m*</code>，一般孤立工作進 <code>dev/next</code>，獨立 canary 才用暫時 <code>dev/i*</code>；完成時 promotion 到 main，hotfix 才直達 main。</p><p><strong>落地方式｜</strong>fast CI 驗證每次 Issue 整合，full CI＋可選 canary 驗證 promotion；main 前進後由 owner 以 reviewed sync PR 回流，不 rewrite 歷史。</p></div></details></td></tr>
          <tr><td>p.6</td><td>PR 與審查</td><td><span class="bridge-status adjust">強化</span></td><td><details class="bridge-detail drop-down"><summary>Issue、編號分支與 PR 形成固定鏈</summary><div class="bridge-popover"><p><strong>五月版｜</strong>PR 是保護分支的唯一入口，方向保留；三層審查改成依風險增加審查者。</p><p><strong>本次判斷｜</strong>一般 PR 要有同編號 Issue、CI 與一位同事；高風險架構變更另附決策紀錄。</p><p><strong>落地方式｜</strong>分支固定 <code>type/123-short-slug</code>，PR 內文固定 <code>Closes #123</code>；governance workflow 在 Free private 從設定名單輪派一位個別 reviewer，GitHub Team 以上才支援 team request 與強制核准。</p></div></details></td></tr>
          <tr><td>p.7</td><td>CI 自動化管線</td><td><span class="bridge-status keep">保留</span></td><td><details class="bridge-detail drop-down"><summary>本機與 CI 共用入口，依風險分層執行</summary><div class="bridge-popover"><p><strong>五月版｜</strong>自動觸發、測試、格式與靜態錯誤檢查全部保留。</p><p><strong>本次判斷｜</strong>一般 Issue PR 跑 fast；promotion、hotfix、merge queue 與未知高風險路徑跑 full；OSV、Zizmor 與 remote governance 另依 scope／schedule 執行。</p><p><strong>落地方式｜</strong>固定 <code>verify</code> aggregate 避免 skipped workflow 留下 Pending；delivery sync 併入 <code>title</code> policy，候選 full run 不取消，普通 PR 新 commit 則取消舊 run。Ruleset 可用時強制 <code>title</code>、<code>verify</code> 與 <code>promotion</code>。</p></div></details></td></tr>
          <tr><td>p.8</td><td>CD 專案管理</td><td><span class="bridge-status adjust">調整</span></td><td><details class="bridge-detail drop-down"><summary>promotion 才形成發版邊界，不為每張 Issue 狂發版</summary><div class="bridge-popover"><p><strong>五月版｜</strong>原本預設 DEV → STAGING → Canary → PROD；本次不要求每個專案照搬四層。</p><p><strong>本次判斷｜</strong>Milestone 原則上在完成時 promotion 一次；只有後續驗收依賴同一 Milestone 的 immutable Release，才用受約束的 checkpoint promotion。<code>dev/next</code> 固定窗口批次 promotion，全部 no-release 就略過版本；hotfix 才立即發布。Canary 必須有環境與命令，否則只誠實保留 artifact-only。</p><p><strong>落地方式｜</strong>release-source 核對 promotion 的 full verify、canary state 與 tree identity；成品 workflow 只接受 source run ID，產生 digest、SBOM、attestation，不接受任意 tag push，也不重跑完整 runtime CI。</p></div></details></td></tr>
          <tr><td>p.9</td><td>可觀測性</td><td><span class="bridge-status defer">第二階段</span></td><td><details class="bridge-detail"><summary>只有上線服務才做監控和值班</summary><div class="bridge-popover"><p><strong>五月版｜</strong>操作手冊、日誌、指標、追蹤、復原與值班流程保留為第二階段。</p><p><strong>本次判斷｜</strong>只對持續運行的服務導入；先依使用的雲端、環境與負責人選工具，不先綁定 Datadog 或 PagerDuty。</p><p><strong>落地方式｜</strong>測試資料另外管理成不含個資、可建立、可清除的範例，不把測資管理混成線上監控。</p></div></details></td></tr>
          <tr><td>p.10</td><td>Copilot → Agent</td><td><span class="bridge-status defer">分階段</span></td><td><details class="bridge-detail"><summary>先受控 AI 協作；成熟後再自動重試</summary><div class="bridge-popover"><p><strong>五月版｜</strong>鼓勵 AI 從補完程式進步到能執行完整任務，方向保留，但不把工程師縮減成只會下提示詞。</p><p><strong>本次判斷｜</strong>第一階段讓 Agent 依清楚工作單研究、提計畫、修改、驗證並開 PR；平行可寫任務各自使用 branch 與 Git worktree，工具便利性由 agent-kit 管理。</p><p><strong>落地方式｜</strong><code>AGENTS.md</code> 與共同驗證命令限制工作方式；<code>actions.json</code> 設定 Actions 預設唯讀且不能核准 PR，Ruleset 要求人類核准。worktree manager 不是 CI/CD，也不取得額外 secret 或合併權限。</p></div></details></td></tr>
          <tr><td>p.11</td><td>AI 初審</td><td><span class="bridge-status adjust">調整</span></td><td><details class="bridge-detail"><summary>固定工具負責判定；AI 只補充建議</summary><div class="bridge-popover"><p><strong>五月版｜</strong>AI 初審保留，但程式碼格式與常見錯誤改由 formatter、linter 與靜態檢查穩定執行。</p><p><strong>本次判斷｜</strong>AI 審查只補充情境性錯誤、測試缺口、風險摘要與修正建議，不能當成通過證明。</p><p><strong>落地方式｜</strong>CI、同事審查與指定負責人才有合併決定權；AI 沒有核准、合併或讀取密鑰的權限。</p></div></details></td></tr>
          <tr><td>p.12</td><td>AI CI/CD log</td><td><span class="bridge-status defer">第二階段</span></td><td><details class="bridge-detail"><summary>先摘要失敗；自動復原只給成熟部署</summary><div class="bridge-popover"><p><strong>五月版｜</strong>AI 可先摘要 CI 失敗紀錄；自動退版只適用於已有正式環境與可靠健康指標的部署。</p><p><strong>本次判斷｜</strong>PR 測試失敗就阻擋合併並用新提交修正，不跳過錯誤提交；若 <code>main</code> 已出問題，就用復原 PR 並建立工作單追蹤。</p><p><strong>落地方式｜</strong>只有健康指標、停止門檻、可重現復原與完整紀錄都成熟後，才考慮讓系統自動復原。</p></div></details></td></tr>
          <tr><td>p.13</td><td>AI 文件與知識庫</td><td><span class="bridge-status defer">分階段</span></td><td><details class="bridge-detail"><summary>先維護 repo 內網站；託管與 RAG 延後</summary><div class="bridge-popover"><p><strong>五月版｜</strong>文件同步方向保留；讓 AI 搜尋文件再回答（RAG）改成選配。</p><p><strong>本次判斷｜</strong>README、規格與 <code>docs/index.html</code> 都和程式一起走 PR；生成專案另有可更新版型與不被覆寫的內容檔。</p><p><strong>落地方式｜</strong>Cloudflare／Hugo 尚未接入；AI 語意審查也要等模型端點與資料政策確定後才成為門禁。只有來源、owner、存取規則、引用與測試題都準備好時才做 RAG。</p></div></details></td></tr>
          <tr><td>p.14</td><td>Legacy modernization</td><td><span class="bridge-status remove">可選</span></td><td><details class="bridge-detail"><summary>舊系統改造是專案需求，不放共同模板</summary><div class="bridge-popover"><p><strong>五月版｜</strong>提到用 AI 協助舊系統現代化；本次不放進所有專案都必須使用的共同模板。</p><p><strong>本次判斷｜</strong>這是特定專案的轉型工作，做法是先用測試記錄目前行為，再小步替換、用短 PR 審查，並保留復原方法。</p><p><strong>落地方式｜</strong>有真實舊系統、風險與效益後再建立專用模板或指南，不先把空工具放進所有新案。</p></div></details></td></tr>
        </tbody>
      </table>
      <p class="bridge-reference reference">Ref. GitHub Docs. <a href="https://docs.github.com/en/copilot/tutorials/cloud-agent/get-the-best-results" target="_blank" rel="noreferrer">AI agent practices</a>; <a href="https://docs.github.com/en/get-started/using-github/github-flow" target="_blank" rel="noreferrer">GitHub flow</a>; <a href="https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues" target="_blank" rel="noreferrer">Sub-issues</a>; <a href="https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets" target="_blank" rel="noreferrer">Rulesets</a>; <a href="https://docs.github.com/en/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site" target="_blank" rel="noreferrer">Pages visibility</a>. Accessed August 20, 2026.</p>
{{< /legacy >}}

{{< basic >}}
| 五月版主題 | 現在的決定 |
| --- | --- |
| SDLC 核心階段 | 保留計畫、開發、測試、交付與監控順序，集中在 GitHub 可維護物件 |
| Jira Ticket | 改為最小 GitHub Issue；明確 story 才加 Milestone／spec |
| 版本控制 | delivery branch 是 CI 整合邊界，不假裝成實體 DEV 環境 |
| PR 與審查 | Issue、編號分支、PR、CI 與人類核准形成固定鏈 |
| CI 管線 | 一般工作 fast；promotion、hotfix 與未知高風險路徑 full |
| CD 管理 | promotion 才形成 release 邊界；沒有環境時 canary 降級為 artifact-only |
| 可觀測性 | 只有持續運行的服務才選監控與值班工具 |
| Copilot → Agent | 先受控協作；成熟後才考慮自動重試與復原 |
| AI 初審 | 只補充建議，不能取代固定工具、同事審查與 Ruleset |
| AI 文件／RAG | 先維護 repo 內文件；託管、資料政策與題庫就緒後才評估 RAG |
| Legacy modernization | 屬特定專案工作，不塞入所有 repo 的共同模板 |

{{< detail key="bridge-reason" title="這次調整的實證理由" >}}
GitHub plan、repo visibility、organization policy 與 token 身分都會影響可用能力，因此使用 runtime probe 而非從方案名稱靜態猜測。分層 CI 將日常回饋與完整交付信心分開；Copier update 讓共用政策持續同步，同時保留產品內容所有權。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="ecosystem" eyebrow="工具選型" title="工具是手段，流程與治理才是主線" subtitle="每個工具都要有現在的決定，不能只把 logo 放上頁面。" class="legacy-slide ecosystem-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">附錄｜技術選型依據</span>
        <h2>工具是實作手段，<span class="accent">流程與治理才是主線</span></h2>
        <p class="subtitle">供已看過五月版的人查核選型：基本導入、未來導入與可選導入分開看；日常操作請回到前面的開發者旅程。</p>
      </header>
      <div class="tool-landscape eight">
        <article class="tool-profile adopt">
          <div class="tool-logo-box"><img class="tool-logo" src="assets/copier.svg" alt="Copier logo"></div>
          <div><h3><a href="https://github.com/copier-org/copier" target="_blank" rel="noreferrer">Copier</a></h3><p><strong>可更新模板｜</strong>建立新案，也同步舊案。<strong>決定｜</strong>基本導入；差異走 PR。</p><p class="tool-health"><span class="tool-status">已完成</span>· MIT · 持續維護</p></div>
        </article>
        <article class="tool-profile adopt">
          <div class="tool-logo-box"><img class="tool-logo" src="assets/zizmor.png" alt="zizmor logo"></div>
          <div><h3><a href="https://github.com/zizmorcore/zizmor" target="_blank" rel="noreferrer">zizmor</a></h3><p><strong>Actions 安全｜</strong>檢查權限與不安全寫法。<strong>決定｜</strong>基本導入；PR 自動跑。</p><p class="tool-health"><span class="tool-status">已完成</span>· MIT · 持續維護</p></div>
        </article>
        <article class="tool-profile next">
          <div class="tool-logo-box"><img class="tool-logo" src="assets/github-community-projects.png" alt="GitHub Community Projects logo"></div>
          <div><h3><a href="https://github.com/github-community-projects/safe-settings" target="_blank" rel="noreferrer">GitHub Safe Settings</a></h3><p><strong>多 repo 治理｜</strong>集中套用、找出差異。<strong>決定｜</strong>未來；目前 JSON＋<code>gh api</code>＋排程漂移檢查已足夠。</p><p class="tool-health"><span class="tool-status">未來導入</span>· ISC · 持續維護</p></div>
        </article>
        <article class="tool-profile conditional">
          <div class="tool-logo-box"><img class="tool-logo" src="assets/renovate.png" alt="Renovate logo"></div>
          <div><h3><a href="https://github.com/renovatebot/renovate" target="_blank" rel="noreferrer">Renovate</a></h3><p><strong>套件更新｜</strong>等待與分組更細。<strong>決定｜</strong>不導入；保留能直接觸發既有 CI/CD checks 的 Dependabot。<a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/74" target="_blank" rel="noreferrer">#74 評估</a>、<a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/110" target="_blank" rel="noreferrer">#110 決策</a>。</p><p class="tool-health"><span class="tool-status">不採用</span>· AGPL · 持續維護</p></div>
        </article>
        <article class="tool-profile">
          <div class="tool-logo-box"><img class="tool-logo" src="assets/github-actions.svg" alt="GitHub Actions logo"></div>
          <div><h3><a href="https://github.com/actions/starter-workflows" target="_blank" rel="noreferrer">Starter Workflows</a></h3><p><strong>GitHub Actions 目錄｜</strong>官方範例。<strong>決定｜</strong>只參考分類，不照抄政策。</p><p class="tool-health"><span class="tool-status">內容參考</span>· GitHub · 持續維護</p></div>
        </article>
        <article class="tool-profile">
          <div class="tool-logo-box"><img class="tool-logo" src="assets/pyscaffold.svg" alt="PyScaffold logo"></div>
          <div><h3><a href="https://github.com/pyscaffold/pyscaffold" target="_blank" rel="noreferrer">PyScaffold</a></h3><p><strong>Python 骨架｜</strong>成熟結構與測試做法。<strong>決定｜</strong>只當內容檢查表。</p><p class="tool-health"><span class="tool-status">內容參考</span>· MIT · 持續維護</p></div>
        </article>
        <article class="tool-profile next">
          <div class="tool-logo-box"><img class="tool-logo" src="assets/github.png" alt="GitHub logo"></div>
          <div><h3><a href="https://github.com/github/spec-kit" target="_blank" rel="noreferrer">GitHub Spec Kit</a></h3><p><strong>AI 規格拆解｜</strong>串起規格、計畫與工作。<strong>決定｜</strong>未來；目前用 spec → Issue。</p><p class="tool-health"><span class="tool-status">未來導入</span>· MIT · 持續維護</p></div>
        </article>
        <article class="tool-profile conditional">
          <div class="tool-logo-box"><img class="tool-logo" src="assets/backstage.svg" alt="Backstage logo"></div>
          <div><h3><a href="https://backstage.io/docs/features/software-catalog/" target="_blank" rel="noreferrer">Backstage</a></h3><p><strong>開發者入口｜</strong>集中服務、owner 與文件。<strong>決定｜</strong>等跨團隊找 owner／服務開始反覆耗時才導入。</p><p class="tool-health"><span class="tool-status">條件式導入</span>· Apache-2.0 · 持續維護</p></div>
        </article>
      </div>
      <aside class="tool-deferred" aria-label="未來選配與暫不採用工具">
        <p><strong>基本方案另已採用：</strong>Dependabot、OSV-Scanner、anchore/sbom-action（底層使用 Syft）。</p>
        <p><strong>尚未啟用：</strong>Go／Rust profile、Scorecard、Harden-Runner、網站託管／登入（<a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/79" target="_blank" rel="noreferrer">#79</a>）、Hugo、RAG、通用部署與監控；repo 內部網站與生成內容模板已可用。</p>
      </aside>
      <p class="ecosystem-reference reference">Ref. Official project repositories linked above; logo assets from each project's brand kit.</p>
{{< /legacy >}}

{{< basic >}}
| 工具 | 解決什麼 | 現在的決定 |
| --- | --- | --- |
| ![Copier logo](assets/copier.svg) [Copier](https://github.com/copier-org/copier) | 可更新模板 | 基本導入；差異走 PR |
| ![zizmor logo](assets/zizmor.png) [zizmor](https://github.com/zizmorcore/zizmor) | GitHub Actions 安全 | 基本導入；workflow 變更與週期排程執行 |
| Dependabot、OSV、Syft | 依賴更新、漏洞與 SBOM | 基本導入 |
| ![GitHub Community Projects logo](assets/github-community-projects.png) [Safe Settings](https://github.com/github-community-projects/safe-settings) | 多 repo 設定治理 | 規模與漂移門檻成立後才評估 |
| ![Renovate logo](assets/renovate.png) [Renovate](https://github.com/renovatebot/renovate) | 更彈性的更新 preset | 現階段不取代 Dependabot |
| ![GitHub Actions logo](assets/github-actions.svg) ![PyScaffold logo](assets/pyscaffold.svg) Starter Workflows、PyScaffold | 官方 workflow 與 Python 結構範例 | 只作內容檢查表，不照抄政策 |
| ![GitHub logo](assets/github.png) [GitHub Spec Kit](https://github.com/github/spec-kit) | AI 規格拆解 | 現階段保留 spec → Issue |
| ![Backstage logo](assets/backstage.svg) [Backstage](https://backstage.io/docs/features/software-catalog/) | Catalog、owner 與文件入口 | 跨團隊查找成本達門檻才 PoC |

{{< detail key="ecosystem-deferred" title="尚未啟用的能力" >}}
Go／Rust profile、Scorecard、Harden-Runner、網站託管與登入、RAG、通用部署與監控都等可測量需求再做。公版不建立空設定或 placeholder 來假裝支援。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="similar-tools" parity="supplemental" eyebrow="工具附錄｜相似工具" title="相似工具｜整體競品與局部參考" subtitle="標準模式先看整體目的接近的套件；維運模式可再按旅程檢查各項具體做法。" class="similar-tools-slide" legacy="true" >}}
{{< similar-tools >}}
{{< /slide >}}

{{< slide key="testing" audience="maintainer" parity="supplemental" eyebrow="維運附錄｜CI/CD 設定" title="CI/CD 設定｜依 Journey 檢查" subtitle="分開列出一般 repo 與 repo-template 在 Issue PR → dev、dev → main 各自需要的測試與自動化。" class="similar-tools-slide testing-slide" legacy="true" >}}
{{< testing >}}
{{< /slide >}}

{{< slide key="access-control" eyebrow="存取決策" title="託管方案未定前的臨時防護" subtitle="目前只有降低誤分享的措施，沒有把提示語宣稱成安全控制。" class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">決策附錄</span>
        <h2>存取控制決策｜<span class="accent">託管方案未定前的臨時防護</span></h2>
        <p class="subtitle">評估三種存取控制方案的成本與限制；正式方案定案前，先以 <code>noindex</code>／<code>robots.txt</code> 降低意外曝光，這不是存取控制。</p>
      </header>
      <div class="plan-grid">
        <article class="plan-card team"><h3>Cloudflare Pages＋Access <span class="plan-state">候選</span></h3><p><strong>成本：</strong>免費額度可覆蓋小團隊登入牆；設定 Zero Trust 政策、網域與 DNS。<strong>限制：</strong>需要另建 Cloudflare 帳號與組織身分整合（Google／GitHub SSO 或 email OTP），資料與稽核政策需先確認。<strong>持有者：</strong>需組織 owner 建立並持有 Cloudflare 帳號權限，本 Issue 不建立或設定。</p></article>
        <article class="plan-card enterprise"><h3>GitHub Pages＋IP 限制 <span class="plan-state">受限</span></h3><p><strong>成本：</strong>沿用既有 GitHub 組織，不需另一個外部帳號。<strong>限制：</strong>私有 Pages 網站限定 GitHub Enterprise Cloud；IP allow list 對遠端／混合團隊不易維護，且組織目前是 Free plan，尚未具備此能力。<strong>持有者：</strong>需組織 owner 先升級方案，才能設定 Enterprise 網路政策。</p></article>
        <article class="plan-card current"><h3>內部登入平台（Backstage／Confluence 等） <span class="plan-state">未來</span></h3><p><strong>成本：</strong>可與既有身分系統（SSO）整合，統一管理多份內部文件，不只這一頁。<strong>限制：</strong>需要另外導入與維運一套平台，目前只有一份內部網站，導入成本大於效益。<strong>持有者：</strong>需 IT／平台團隊建立與維運，屬於未來、服務變多才評估的選項。</p></article>
      </div>
      <aside class="selection-note"><strong>目前決定</strong><span>三個方案都需要外部帳號或組織升級，本 Issue 範圍不包含實際申請或設定；候選以 Cloudflare Pages＋Access 為優先評估對象，決定前只維持 <code>noindex</code>／<code>robots.txt</code> 以降低意外曝光。任何一個方案定案後，需另開實作用 Issue 並由組織 owner 核准與持有帳號。</span></aside>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>臨時措施：</strong><code>docs/index.html</code> 的 <code>&lt;meta name="robots"&gt;</code>＋<code>docs/robots.txt</code></li><li><strong>決策追蹤：</strong><a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/79" target="_blank" rel="noreferrer">Issue #79</a></li></ul></aside>
{{< /legacy >}}

{{< basic >}}
| 方案 | 成本與優點 | 目前限制／持有者 |
| --- | --- | --- |
| Cloudflare Pages＋Access | 免費額度可提供小團隊登入牆 | 需組織 owner 建立 Cloudflare、網域、DNS 與 SSO／OTP 政策 |
| GitHub Pages＋IP 限制 | 沿用 GitHub 組織 | Private Pages 與 IP allow list 需 Enterprise Cloud；目前 Free 不可用 |
| Backstage／Confluence 等登入平台 | 可統一管理多份內部文件 | 現在只有一份網站，需 IT／平台團隊導入維運，成本高於效益 |

{{< detail key="access-control-limit" title="目前已做與仍然做不到的事" >}}
`docs/index.html` 內有 `noindex,nofollow`，`docs/robots.txt` 也拒絕 crawler。這些都不是 authentication；擁有離線 HTML 的人仍可轉寄。正式 host、身分提供者、資料與稽核政策需由維護者另行核准，追蹤於 Issue #79。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="principles" eyebrow="關鍵決策" title="規則、理由與刻意不做" subtitle="這些是目前可由檔案與測試證明的決定。" class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">決策附錄</span>
        <h2>關鍵決策｜<span class="accent">規則、理由與刻意不做</span></h2>
        <p class="subtitle">原補充文件已收斂於此；細節以可執行設定為準，條件改變時以 Issue／PR 同步更新。</p>
      </header>
      <table class="decision-register" aria-label="公版核心決策登錄">
        <thead><tr><th>審閱問題</th><th>目前決定與原因</th></tr></thead>
        <tbody>
          <tr><td>方案與 <code>main</code> 保護</td><td>Free private 會套基本設定並保存 Ruleset policy，但公開 API 無法建立 Ruleset，<code>main</code> 仍未受強制保護；至少升 Team 並建立 CODEOWNERS team，或經核准改為 public，核准與必要檢查才成為 merge gate。</td></tr>
          <tr><td>工作範圍與責任</td><td>Issue-first；標題用 12–80 字元英文摘要成果，內文可用中文；開單者自動成為負責人。新增需求超出完成條件就另開 Issue。</td></tr>
          <tr><td>公版更新邊界</td><td><code>template/</code> 是下發來源，root 讓公版自我治理；Copier 更新政策但保護產品程式與規格，成對設定由驗證腳本防止漂移。</td></tr>
          <tr><td>語言與程式品質</td><td>共用治理支援四種 profile；Python 採 src layout、Ruff 80 字元與 <a href="https://google.github.io/styleguide/pyguide.html" target="_blank" rel="noreferrer">Google Python Style</a>、strict mypy；TypeScript 採 Node 24、pnpm 11、Biome、Vitest。</td></tr>
          <tr><td>CI、版本與交付</td><td>本機與 CI 共用 <code>scripts/verify</code>，PR policy 回歸案例證明錯誤 route 會被拒絕；日常 fast、promotion full，release-please 只在已驗證的批次邊界維護單一 SemVer。</td></tr>
          <tr><td>依賴與供應鏈</td><td>三天等待觀察未知惡意新版；OSV 查已公開漏洞；hash 驗內容一致；SBOM 列出成品套件；resolver 另證明版本上下界可安裝，五者互不取代。</td></tr>
          <tr><td>AI、文件與未來能力</td><td><code>AGENTS.md</code> 是 AI 規範，README 與 repo 網站服務人類；Hugo／託管登入、部署、監控、RAG、Go／Rust 都要有 owner、使用情境與驗證後才導入。</td></tr>
          <tr><td>驗證與測試資源</td><td>「已完成」必須有檔案與測試；驗證只用本機暫存專案或本 repo 的 Issue、分支、PR、Actions，禁止為測試另開 GitHub repo。</td></tr>
        </tbody>
      </table>
      <p class="review-note-footer"><strong>驗證承諾：</strong><code>./scripts/verify-template.sh</code> 會實跑新案、既有案導入，以及同一個已導入 repo 的 Copier 更新與更新後完整驗證；這支 root-only 腳本不會下發。</p>
{{< /legacy >}}

{{< basic >}}
| 審閱問題 | 目前決定 |
| --- | --- |
| Free private 的 `main` 保護 | 保存 Ruleset policy 並回報 `DEGRADED`，不宣稱已有 merge gate |
| 工作範圍 | Issue-first；新增需求超出完成條件就另開 Issue |
| 公版更新邊界 | `template/` 下發基礎設施；Copier 保護產品程式與規格 |
| 語言品質 | Python 用 src layout、Ruff、strict mypy；TypeScript 用 Node 24、pnpm 11、Biome、Vitest |
| CI 與版本 | 本機／CI 共用入口；日常 fast、promotion full、單一 SemVer |
| 供應鏈 | 等待、OSV、hash、SBOM 與 resolver 各解決不同問題 |
| AI 與文件 | `AGENTS.md` 是工作契約；README 與網站服務人類 |
| 驗證資源 | 只用本機暫存專案或本 repo，不為測試另開 GitHub repository |

{{< detail key="principles-transcript" title="決策如何留下來" >}}
Agent 不保存原始聊天。只有使用者已確認的 durable architecture、security、compatibility 或 platform constraint，才先摘要進 Issue，再透過有範圍的 PR 更新 `docs/adr/` 或 `docs/decisions/`。細節以可執行設定為準，條件改變時由 Issue／PR 同步修正。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="benchmark" eyebrow="外部基準與實測" title="有骨架，還不是完整平台" subtitle="新 repo、Copier 更新、OSV、Release 與第一個 CI-only pilot 已有證據；其餘邊界仍明列。" class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">決策附錄</span>
        <h2>外部基準與實測｜<span class="accent">有骨架，還不是完整平台</span></h2>
        <p class="subtitle">結論：已真正解決新 repo 建立、Copier 更新與本機／合成驗證；OSV、Release 與第一個 CI-only consuming repo 都有線上成功證據。治理仍受 GitHub 方案限制，語言 profile 尚待各自試行。</p>
      </header>
      <table class="decision-register audit-register" aria-label="外部基準與線上實測比較">
        <thead><tr><th>外部基準／實測</th><th>判斷</th><th>研究選擇與目前邊界</th></tr></thead>
        <tbody>
          <tr><td><a href="https://copier.readthedocs.io/en/stable/updating/" target="_blank" rel="noreferrer">Copier</a> vs <a href="https://projen.io/docs/introduction/" target="_blank" rel="noreferrer">projen</a></td><td><span class="tier-chip best">選擇合適</span></td><td>需求是「產生後可修改，之後仍能更新」；Copier 的 smart update 比由程式持續擁有生成檔的 projen 更合適，維持現況。</td></tr>
          <tr><td><a href="https://engineering.atspotify.com/2020/08/how-we-use-golden-paths-to-solve-fragmentation-in-our-software-ecosystem" target="_blank" rel="noreferrer">Spotify Golden Path</a>＋<a href="https://backstage.io/docs/features/software-catalog/" target="_blank" rel="noreferrer">Backstage Catalog</a></td><td><span class="tier-chip priority">只完成一段</span></td><td>目前是單 repo golden-path 模板，不是有 catalog、owner、成熟度與 fleet migration 的平台；跨團隊尋找服務反覆變痛點時才導入。→ <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/105" target="_blank" rel="noreferrer">#105</a></td></tr>
          <tr><td><a href="https://github.com/ossf/allstar" target="_blank" rel="noreferrer">Allstar</a>／<a href="https://github.com/github-community-projects/safe-settings" target="_blank" rel="noreferrer">Safe Settings</a></td><td><span class="tier-chip best">目前夠用</span></td><td>排程漂移檢查已由 <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/75" target="_blank" rel="noreferrer">#75</a> 完成；repo 數量增加、同類漂移重複發生時，再換中央政策服務。</td></tr>
          <tr><td><a href="https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets" target="_blank" rel="noreferrer">GitHub Rulesets</a>／Free private</td><td><span class="tier-chip priority">部分解決</span></td><td>能查出平台能力並告警，但 Free private 無法強制 Ruleset；<a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/87" target="_blank" rel="noreferrer">#87</a> 已把未受保護狀態寫入 policy，平台方案限制仍明確保留。</td></tr>
          <tr><td>Release Please 線上執行＋<a href="https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow" target="_blank" rel="noreferrer"><code>GITHUB_TOKEN</code> 觸發規則</a></td><td><span class="tier-chip best">線上閉環完成</span></td><td><a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/32645380139" target="_blank" rel="noreferrer">既有 run</a> 證明 Actions PR 會被組織政策阻擋，因此流程會依當下能力選 release-please、direct 或 verification-only；<a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/32662029395" target="_blank" rel="noreferrer">v0.2.4 run</a> 已完成治理、完整驗證、immutable release 發佈與 trust-chain 驗證。</td></tr>
          <tr><td>OSV reusable workflow＋<a href="https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows" target="_blank" rel="noreferrer">權限傳遞</a></td><td><span class="tier-chip best">已修正</span></td><td>呼叫端權限只能維持或縮小，不能替被呼叫 workflow 補權限；<a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/92" target="_blank" rel="noreferrer">PR #92</a> 補回必要權限後，<a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/actions/runs/32646097257" target="_blank" rel="noreferrer">main 線上 run</a> 已成功。</td></tr>
          <tr><td><a href="https://docs.github.com/en/actions/concepts/security/artifact-attestations" target="_blank" rel="noreferrer">Artifact Attestations</a>＋<a href="https://slsa.dev/spec/v1.2/build-track-basics" target="_blank" rel="noreferrer">SLSA Build</a></td><td><span class="tier-chip best">消費端門禁完成</span></td><td>生成專案的 PyPI／npm 再發布路徑會在啟用 attestation 時，強制比對 repository、tag、artifact digest 與 signer workflow；CI-only 不產生空 job。公版另以真實 immutable Release wheel 完成線上成功與受控 digest mismatch 驗證，細節見 <a href="artifact-consumption.md">artifact consumption evidence</a>。→ <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/104" target="_blank" rel="noreferrer">#104</a></td></tr>
          <tr><td><a href="https://github.com/ossf/scorecard" target="_blank" rel="noreferrer">OpenSSF Scorecard</a> 安全基線</td><td><span class="tier-chip optional">方案感知</span></td><td>已有 pinned Actions、OSV、<code>SECURITY.md</code>、完整 Git 歷史與工作樹 secret scan；public repo 預設啟用 CodeQL，private／internal 則依 GitHub Code Security 授權明確 opt-in。</td></tr>
          <tr><td>真實 consuming repo 與採用證據</td><td><span class="tier-chip best">CI-only 已證明</span></td><td><code>ai-guardrail</code> 已透過 Issue、兩支 PR 完成 v0.2.4 導入、產品客製化保留、v0.3.1 Copier update 與兩次完整線上檢查；Python、TypeScript 與混合 composition 仍缺各自的真實 pilot。→ <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/100" target="_blank" rel="noreferrer">#100</a>／<a href="pilot-adoption.md">證據</a></td></tr>
        </tbody>
      </table>
      <p class="review-note-footer"><strong>簡潔度判斷：</strong>Copier＋GitHub Actions＋標準工具的方向夠簡潔；真實 CI-only pilot 已補上合成測試以外的證據。root-only <code>Live integration smoke</code> 持續驗證 OSV、Release Please、release handoff 與 governance drift；其餘語言 profile 各完成 pilot 後才升 beta。</p>
{{< /legacy >}}

{{< basic >}}
| 外部基準／實測 | 判斷 | 目前證據與邊界 |
| --- | --- | --- |
| Copier vs projen | 選擇合適 | 需求是產生後可修改又能更新，Copier smart update 較合適 |
| Spotify Golden Path／Backstage | 只完成一段 | 現在是單 repo 公版，不是跨團隊 catalog 平台 |
| Allstar／Safe Settings | 目前夠用 | 已有排程 drift check；fleet 變大後再評估中央 enforcement |
| GitHub Rulesets／Free private | 部分解決 | 可偵測並告警，方案仍不能強制 Ruleset |
| Release Please live runs | 線上閉環完成 | 能依能力選 Release PR、Direct 或 Verification only |
| OSV reusable workflow | 已修正 | 權限傳遞修正後已有成功 main run |
| Artifact Attestations／SLSA | 消費端門禁完成 | 核對 repository、tag、digest 與 signer workflow |
| OpenSSF Scorecard | 方案感知 | public 預設 CodeQL；private/internal 依授權 opt-in |
| 真實 consuming repo | CI-only 已證明 | `ai-guardrail` 已完成 v0.2.4 導入與 v0.3.1 update；其他 profile 尚缺 pilot |

{{< detail key="benchmark-gap" title="現階段缺口" >}}
沒有跨 repo catalog、全面託管治理或通用部署平台。Root-only `Live integration smoke` 持續驗證 OSV、Release Please、release handoff 與 governance drift；Python、TypeScript 與混合 composition 各完成真實 pilot 後才能升為 beta。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="fleet-inventory" eyebrow="Fleet 治理" title="採用盤點以真實 repo 為準" subtitle="2026-08-24：組織共 6 個 private repo，目前只有 1 個 consuming repo。" class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">決策附錄</span>
        <h2>Fleet 治理盤點｜<span class="accent">1 個 consuming repo</span></h2>
        <p class="subtitle">2026-08-24 完成第一個真實 pilot：組織共 6 個 private repo，<code>ai-guardrail</code> 已導入並更新至 v0.3.1；其餘 4 個產品／工具 repo 尚未導入。門檻未達前不部署中央平台。</p>
      </header>
      <table class="decision-register audit-register" aria-label="Repository 採用盤點">
        <thead><tr><th>Repository</th><th>Owner</th><th>模板版本</th><th>漂移資料</th></tr></thead>
        <tbody>
          <tr><td><code>csarc-repo-template</code></td><td><code>@Innoguard-Cyber-Arch/arch</code></td><td>來源 repo，版本見頁首</td><td>非 consuming repo；live integration 已驗證 governance drift 可執行。</td></tr>
          <tr><td><code>GRC</code></td><td>未宣告 CODEOWNERS</td><td>未導入</td><td>無模板漂移資料</td></tr>
          <tr><td><code>LLM_Guard</code></td><td>未宣告 CODEOWNERS</td><td>未導入</td><td>無模板漂移資料</td></tr>
          <tr><td><code>ai-guardrail</code></td><td><code>@Innoguard-Cyber-Arch/repository-maintainers</code></td><td><code>v0.3.1</code>／CI-only beta</td><td>導入與更新 PR 全綠；後續由 daily governance drift 累積頻率資料</td></tr>
          <tr><td><code>claude-newsletter</code></td><td>未宣告 CODEOWNERS</td><td>未導入</td><td>無模板漂移資料</td></tr>
          <tr><td><code>csarc-agent-kit</code></td><td>未宣告 CODEOWNERS</td><td>未導入</td><td>無模板漂移資料</td></tr>
        </tbody>
      </table>
      <aside class="selection-note"><strong>盤點結論</strong><span>目前只有一個下游 repo，足以證明導入與更新生命週期，不足以合理化中央平台。漂移頻率只計完成的排程樣本；「沒有 run」不記為「零漂移」。</span></aside>
      <p class="bridge-reference reference">Inventory: GitHub repositories, default branches, CODEOWNERS, Copier answers and CSARC profiles; accessed August 24, 2026.</p>
{{< /legacy >}}

{{< basic >}}
| Repository | Owner | 模板狀態 | 漂移資料 |
| --- | --- | --- | --- |
| `csarc-repo-template` | `@Innoguard-Cyber-Arch/arch` | 來源 repo | live integration 已證明 drift check 可執行 |
| `GRC` | 未宣告 CODEOWNERS | 未導入 | 無模板漂移資料 |
| `LLM_Guard` | 未宣告 CODEOWNERS | 未導入 | 無模板漂移資料 |
| `ai-guardrail` | `@Innoguard-Cyber-Arch/repository-maintainers` | v0.3.1／CI-only beta | 導入與 update PR 全綠，開始累積 daily drift samples |
| `claude-newsletter` | 未宣告 CODEOWNERS | 未導入 | 無模板漂移資料 |
| `csarc-agent-kit` | 未宣告 CODEOWNERS | 未導入 | 無模板漂移資料 |

{{< detail key="fleet-inventory-source" title="盤點證據與判讀方式" >}}
盤點 GitHub repositories、default branches、CODEOWNERS、Copier answers、CSARC profiles、未完成 update PR 與 governance-drift runs。沒有完成排程樣本的 repo 不記為「零漂移」；新 pilot 與每季回顧都重新計數。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="fleet-governance-thresholds" eyebrow="Fleet 門檻" title="先量問題，再加平台" subtitle="Catalog 與 policy enforcement 解決不同問題，分開計數、分開選工具。" class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">決策附錄</span>
        <h2>Fleet 治理門檻｜<span class="accent">先量問題，再加平台</span></h2>
        <p class="subtitle">Catalog 處理服務可見性與 owner；policy enforcement 處理跨 repo 設定偏離。兩種問題分開計數、分開選工具。</p>
      </header>
      <div class="decision-strip">
        <article class="decision-step recommended">
          <span class="step-label">Catalog 門檻</span>
          <h3>解決「是誰、服務在哪」</h3>
          <p>滿足任一條才開始 Backstage proof of concept：<strong>10 個活躍 consuming repo</strong>；或至少 3 個 consuming repo，且 90 天內有 <strong>2 次 owner／服務查找超過 30 分鐘</strong>的 Issue 記錄。Backstage 負責 catalog、owner、系統關係與成熟度可見性，不當 repository setting 強制工具。</p>
        </article>
        <article class="decision-step">
          <span class="step-label">Policy 門檻</span>
          <h3>解決「設定偏離且修不回來」</h3>
          <p>至少 5 個 consuming repo 後，滿足任一條才評估中央 enforcement：30 天內同類漂移出現於 <strong>2 個以上 repo</strong>；連續兩個模板 release 都有超過 <strong>20%</strong> 的 update PR 逾 <strong>5 個工作天</strong>；或每月人工 <code>apply</code>／修正超過 <strong>2 小時</strong>。Allstar 適合持續檢查與執行安全政策；Safe Settings 適合用階層設定檔統一下發 repository settings。兩者不取代 catalog。</p>
        </article>
      </div>
      <aside class="selection-note"><strong>目前決定</strong><span>0 個 consuming repo，且沒有可用的漂移頻率樣本，不達任一門檻。維持 Copier／JSON policy／GitHub API／每日漂移檢查；不預先部署 Backstage、Allstar 或 Safe Settings。</span></aside>
      <aside class="config-guidance"><strong>重新評估</strong><ul><li>每季與每次新增 pilot 後，以 GitHub API 重點數 answers／profile、CODEOWNERS、未完成 update PR 與 governance-drift runs。</li><li>漂移頻率只計「有完成排程樣本」的 consuming repo；沒有 run 不記為零漂移。</li><li>觸發後另開 Issue，指定平台 owner、成本上限、試行範圍與退場條件；本決策不授權建置外部服務。</li></ul></aside>
      <p class="bridge-reference reference">Ref. <a href="https://backstage.io/docs/features/software-catalog/" target="_blank" rel="noreferrer">Backstage Software Catalog</a>; <a href="https://github.com/ossf/allstar" target="_blank" rel="noreferrer">OpenSSF Allstar</a>; <a href="https://github.com/github-community-projects/safe-settings" target="_blank" rel="noreferrer">GitHub Safe Settings</a>. Accessed August 24, 2026.</p>
{{< /legacy >}}

{{< basic >}}
| 需求 | 開始評估的量化門檻 |
| --- | --- |
| Catalog／Backstage | 10 個活躍 consuming repos；或至少 3 個，且 90 天內有 2 次 owner／服務查找超過 30 分鐘的 Issue 記錄 |
| 中央 policy enforcement | 至少 5 個 consuming repos，且同類 drift 30 天內出現在 2+ repos；或連續兩版有 20%+ update PR 超過 5 個工作天；或每月人工修正超過 2 小時 |

{{< detail key="fleet-thresholds-yagni" title="觸發後仍需具備的條件" >}}
觸發後另開 Issue，指定平台 owner、成本上限、試行範圍與退場條件。Backstage 管 catalog／owner／系統關係；Allstar 或 Safe Settings 才處理持續政策檢查與設定下發，兩者不能互相取代。目前維持 Copier、JSON policy、GitHub API 與 daily drift check，不預建外部服務。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="spec-format" eyebrow="Spec 格式" title="預設 Issue，明確 Story 才建 Milestone" subtitle="保留一種輕量格式，不在需求尚未出現時同時維護兩套系統。" class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">決策附錄</span>
        <h2>Spec 格式決策｜<span class="accent">預設 Task，明確 Story 才建 Feature</span></h2>
        <p class="subtitle">沿用輕量 frontmatter；<code>tracking: story</code> 是顯式選項，不因 spec 存在或工作數量自動升格。</p>
      </header>
      <div class="decision-strip">
        <article class="decision-step">
          <span class="step-label">GitHub Spec Kit</span>
          <h3>2025-09 開源，半年內成為事實標準</h3>
          <ul>
            <li><strong>生命週期：</strong><code>/specify → /plan → /tasks → /implement</code> 四段 slash command，逐步產出 spec.md／plan.md／tasks.md，設計給 AI coding agent 逐步執行。</li>
            <li><strong>相依：</strong>需安裝 <code>specify</code> CLI，並綁定支援的 AI 工具（Claude Code、Copilot 等）。</li>
            <li><strong>同步：</strong>沒有內建「一份 spec 對應一張 GitHub Issue」的 idempotent 同步機制，需要自行銜接。</li>
            <li><strong>專案狀態：</strong><a href="https://github.com/github/spec-kit" target="_blank" rel="noreferrer">github/spec-kit</a>｜MIT｜公開、未封存、持續維護。</li>
          </ul>
        </article>
        <article class="decision-step recommended">
          <span class="step-label">我們的決定</span>
          <h3>保留單一格式，使用原生 Issue hierarchy</h3>
          <p><strong>現行：</strong><code>docs/specs/*.md</code> 用 frontmatter 記錄狀態；預設以 <code>csarc-spec-id</code> marker 同步 Task Issue，明列 <code>tracking: story</code> 則同步 Feature parent，兩者都可重跑且不自動拆工作。Milestone 另作有 due date 的 delivery／release bucket。</p>
          <p><strong>遷移成本：</strong>改採 Spec Kit 需要重寫 <code>spec_to_issue.py</code> 的解析與同步邏輯、既有 spec 全部轉檔、更新驗證腳本的斷言，且需另外設計 Issue-sync 等價機制；雙格式支援則讓兩套系統同時維護，增加認知負擔，本 Issue 不做這兩件事。</p>
          <p><strong>理由：</strong>目前規格量小、現行管線穩定且已納入回歸測試；Spec Kit 的 CLI／Agent 相依對單一小型公版 repo 效益還不明確。</p>
          <p><strong>重新評估條件：</strong>native subissues 無法表達實際工作拆解，且團隊願意維護額外 CLI／Agent 流程時，再重新評估遷移或雙格式支援；與「步驟一規劃工作」頁既有立場一致。</p>
        </article>
      </div>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>現行 spec 格式與驗證：</strong><code>docs/specs/*.md</code>＋<code>scripts/spec_to_issue.py</code></li><li><strong>決策追蹤：</strong><a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/77" target="_blank" rel="noreferrer">Issue #77</a></li></ul></aside>
{{< /legacy >}}

{{< basic >}}
| 選項 | 現況 |
| --- | --- |
| 現行 `docs/specs/*.md` | Front matter 記錄 ID、優先度、狀態與選用 tracking；marker 可重跑同步 Issue 或 Milestone |
| GitHub Spec Kit | `/specify → /plan → /tasks → /implement`，需額外 CLI 與支援的 AI 工具，沒有內建一份 spec 對一張 Issue 的同步 |

{{< detail key="spec-format-cost" title="目前不遷移的理由與重新評估條件" >}}
改採 Spec Kit 需重寫 `scripts/spec_to_issue.py`、轉換既有 specs、更新驗證斷言，並另行設計等價 Issue sync；雙格式則增加認知與維護負擔。當核准規格經常需要由 AI 穩定拆成多張子工作，且團隊願意維護額外 CLI／Agent 流程時再評估。決策追蹤於 Issue #77。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< glossary >}}
