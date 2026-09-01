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
        <p class="subtitle">Cyber-Arch 的可更新 repo 公版：建立新案、導入既有案、接收政策更新，都先驗證再由變更提案（PR）合併。</p>
        <p class="subtitle">標準模式給使用 AI／vibe coding 的一般開發者，不要求具備工程或 CI/CD 維運背景；維運模式才補充設定檔、程式與技術理由。快速導入指令請見 <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template#readme" target="_blank" rel="noreferrer">repo README</a>。</p>
        <div class="package-badges" aria-label="套件狀態">
          <span class="package-badge beta">v0.12.2</span><!-- x-release-please-version -->
          <span class="package-badge beta">beta</span>
          <span class="package-badge python">三個語言模組</span>
          <span class="package-badge">三種分支做法</span>
          <span class="package-badge">公版可持續更新</span>
          <span class="package-badge security">自動驗證／安全檢查</span>
          <span class="package-badge warning">免費私人 repo：無法強制保護 main</span>
        </div>
      </header>
      <div class="language-contract" aria-label="程式語言與公版設定">
        <p class="language-card"><strong>建立／導入時選擇程式語言</strong>Python、Rust、TypeScript 需要哪些就勾哪些；都不選時只準備共通工作流程。</p>
        <p class="language-card shared"><strong>一份公版設定</strong>模板把語言、分支與選用能力記在 <code>.csarc/config.yml</code>；更新時由公版維護，不必分散找設定。</p>
        <p class="language-card future"><strong>目前支援版本</strong>Python 3.14、Rust 1.98、TypeScript 使用 Node 24 長期支援版。Go 尚未支援，因此不產生空設定。</p>
      </div>
      <div class="product-start">
        <section class="product-scope" aria-label="公版提供的能力">
          <h3>公版會替 repo 準備</h3>
          <p class="scope-row"><strong>規劃與 AI 規範</strong><span>工作先寫清楚；大型成果才拆成主要工作與可獨立完成的子工作</span></p>
          <p class="scope-row"><strong>驗證與合併</strong><span>本機先跑相關檢查，提出變更後由 GitHub 自動重跑，再交由團隊審查</span></p>
          <p class="scope-row"><strong>依賴與交付證據</strong><span>固定使用的套件版本、先觀察一般新版、檢查已知漏洞，並記錄成品包含哪些套件</span></p>
          <p class="scope-row"><strong>可持續同步</strong><span>公版更新成為可審查差異，不會直接覆蓋產品程式</span></p>
        </section>
        <section class="start-paths" aria-label="三種導入方式">
          <h3>依你現在的 repo 狀態開始</h3>
          <article class="start-path"><h3>新 repo</h3><p>選專案種類與分支做法；多張工作需要一起交付時才建立里程碑。</p><button class="setup-trigger" type="button" data-setup="new" aria-expanded="false">建立指令</button></article>
          <article class="start-path"><h3>既有 repo</h3><p>先在獨立分支預覽差異，保留原有產品內容，再逐項處理衝突。</p><button class="setup-trigger" type="button" data-setup="existing" aria-expanded="false">導入指令</button></article>
          <article class="start-path"><h3>已使用公版</h3><p>選定已審查的公版版本，只審查這次更新帶來的差異。</p><button class="setup-trigger" type="button" data-setup="update" aria-expanded="false">更新指令</button></article>
        </section>
      </div>
      <div class="prerequisite-line product-prerequisites">
        <p><strong>開始前必裝</strong>Git、GitHub CLI、uv；選 Rust 另需 rustup，選 TypeScript 另需 Node 24+、pnpm 11。純本機驗證不用 token；套用 GitHub 設定與端到端測試前才登入 <code>gh</code>。</p>
        <button class="setup-trigger" type="button" data-setup="mac" aria-expanded="false">macOS 安裝</button>
        <button class="setup-trigger" type="button" data-setup="windows" aria-expanded="false">Windows 安裝</button>
      </div>
{{< /legacy >}}

{{< basic >}}
標準模式給使用 AI／vibe coding 的一般開發者，不要求具備工程或 CI/CD 維運背景；內容先說明要做什麼、會看到什麼結果。設定檔、程式與 GitHub Actions 留在維運模式。

| 可以直接選擇 | 目前提供的正式能力 |
| --- | --- |
| 程式語言 | Python、Rust、TypeScript 可獨立複選；都不選時只使用共通工作流程 |
| 分支做法 | 每個交付批次有自己的開發分支、所有修改直接進 `main`，或先集中到 `dev` |
| 公版設定 | 建立／導入時把選項寫入 `.csarc/config.yml`；之後由公版更新，不必到不同檔案重複設定 |
| 共用能力 | 工作單（Issue）與變更提案（PR）表單、AI 工作規範、自動驗證、依賴安全、版本記錄與公版更新 |

{{< detail key="capability-boundary" title="導入方法與目前範圍" >}}
- **新 repo：** 選專案種類與分支做法；大型成果才拆成主要工作與可獨立驗收的子工作。
- **既有 repo：** 公版先偵測現有語言並產生 `.csarc/config.yml`，再預覽導入差異、保留產品內容。
- **已使用公版：** 透過 `csarc update` 調整選項或升級；公版同步設定與必要檔案，只審查這次差異。
- **開始前必裝：** Git、GitHub CLI、uv；選 Rust 另需 rustup，選 TypeScript 另需 Node 24+ 與 pnpm 11。純本機驗證不需要 token。

公版只承諾已經實作並測試的能力。Go、通用部署、監控、AI 知識檢索與網站託管仍是未來或選配項目。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="flow" track="flow" eyebrow="CI/CD 流程" title="模板會帶你走完每次變更" subtitle="依表單填寫、提交 PR、查看結果；模板負責準備正確設定並指出要修正的地方。" class="legacy-slide pipeline-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>模板會把每次變更<span class="accent">帶到正確的位置</span></h2>
        <p class="subtitle">使用者依 Issue 與 PR 的提示工作；模板準備表單、設定與必要檢查。維運模式才需要知道實際流程名稱。</p>
      </header>
      <div class="pipeline-map">
        <div class="pipeline-track" aria-label="日常開發與交付主流程">
          <article class="pipeline-stage">
            <span class="pipeline-phase">第一步｜先說清楚</span>
            <h3>建立工作</h3>
            <p>Issue 表單會提示問題、完成條件與必要背景。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">第二步｜開始修改</span>
            <h3>完成變更</h3>
            <p>人或 AI 依 repo 內指引修改，先做最相關的本機檢查。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">第三步｜交給團隊</span>
            <h3>提出 PR</h3>
            <p>PR 範本會提示連回 Issue，並說明完成內容與驗證結果。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">第四步｜系統協助</span>
            <h3>驗證與依賴安全</h3>
            <p>依變更內容選擇必要驗證；相依變更先確認鎖定版本能正確安裝。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">第五步｜確認結果</span>
            <h3>審查與合併</h3>
            <p>結果與審查都清楚後再合併；強制程度依 GitHub 方案能力。</p>
          </article>
        </div>
        <div class="pipeline-loop" aria-label="CI 回饋迴圈">
          <strong>↶ 檢查失敗：依結果修正，再更新同一張 PR</strong>
          <span>合併後發現的新問題，另外建立一張範圍清楚的 Issue。</span>
        </div>
        <div class="pipeline-foundation" aria-label="支撐整體流程的平台能力">
          <div class="pipeline-foundation-label"><strong>模板先準備好</strong><span>一般使用者依提示操作；維運者才需要調整設定。</span></div>
          <article class="pipeline-foundation-card"><h3>工作格式</h3><p>Issue 與 PR 表單提示必要內容。</p></article>
          <article class="pipeline-foundation-card"><h3>驗證與安全規則</h3><p>依變更內容選擇必要檢查，並辨識相依風險。</p></article>
          <article class="pipeline-foundation-card"><h3>合併設定</h3><p>依 GitHub 方案套用可用保護。</p></article>
          <article class="pipeline-foundation-card best"><h3>版本發佈</h3><p>設定仍保留；Action 尚未啟用。</p></article>
        </div>
      </div>
{{< /legacy >}}

{{< basic >}}
| 你正在做什麼 | 模板會怎麼引導 |
| --- | --- |
| 建立工作 | Issue 表單提示你寫清楚問題、完成條件與必要背景 |
| 完成修改 | Repo 內指引告訴人與 AI 怎麼工作，以及先跑哪個本機檢查 |
| 提交 PR | PR 範本提示連回 Issue，並填寫完成內容與驗證結果 |
| 查看驗證與安全結果 | 模板依變更內容選擇必要檢查；套件變更另確認新版等待、已知漏洞與鎖定版本清單是否一致 |
| 審查與合併 | 檢查結果和人工審查都清楚後，再把變更合併到正確分支 |

一般使用者不必記 workflow 或 script 名稱；依畫面提示操作即可。目前自動化以工作單、PR 規則與必要驗證為主，版本與發佈流程尚未啟用。

{{< detail key="flow-foundation" title="橫跨全流程的四項基礎" >}}
- **07 規則治理：** 權限、分支、審查與合併規則一致。
- **08 模板升級：** Copier 將新政策帶回既有 repo，差異仍經 PR。
- **09 內部網站：** 讓做法、限制、證據與決策容易查找。
- **10 導入層級：** 基本能力先做；需求與平台條件成熟後才加進階能力。

檢查失敗就修正同一張 PR；合併後的新問題則另外建立 Issue。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="files" track="files" eyebrow="檔案地圖" title="模板把必要設定放到正確位置" subtitle="列出目前實際產生的主要檔案；公版可提出更新，但不會靜默覆寫產品內容。" class="legacy-slide managed-files-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>模板會把<span class="accent">必要設定放到正確位置</span></h2>
        <p class="subtitle">共用規則與 6 條現行 GitHub Actions 每個 repo 都有；語言工具與產品目錄才依未選語言、Python、Rust、TypeScript 或多語言模式產生。</p>
      </header>
      <div class="repo-map-window" aria-label="模板產生檔案的視覺對照">
        <div class="repo-map-toolbar">
          <span class="repo-map-dots" aria-hidden="true"><i></i><i></i><i></i></span>
          <span class="repo-map-address">your-project /</span>
          <span class="repo-map-profile">共通／Python／Rust／TypeScript／多語言｜依宣告產生</span>
        </div>
        <div class="repo-tree-head"><span>路徑（依 repo 結構）</span><span>功能／對應旅程編號</span><span>語言</span><span>模板影響</span></div>
        <div class="repo-tree-body">
          <div class="repo-tree-row"><span class="repo-tree-path">.csarc/config.yml</span><span class="repo-tree-purpose"><span class="journey-code">09</span><span class="purpose-copy">公版來源、語言、分支與選用能力</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path">.gitignore</span><span class="repo-tree-purpose"><span class="journey-code">02</span><span class="purpose-copy">環境雜訊／語言產物</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path folder">.github/</span><span class="repo-tree-purpose"><span class="journey-code">01／03／04／05</span><span class="purpose-copy">GitHub 表單、自動檢查與審查設定</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-1">CODEOWNERS＋REVIEWERS</span><span class="repo-tree-purpose"><span class="journey-code">07</span><span class="purpose-copy">指定 owner 與 reviewer 候選</span></span><span class="scope-badge shared">共用</span><span class="owner-badge shared">共同維護</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-1 folder">ISSUE_TEMPLATE/</span><span class="repo-tree-purpose"><span class="journey-code">01</span><span class="purpose-copy">工作單欄位／工作定義</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-1">pull_request_template.md</span><span class="repo-tree-purpose"><span class="journey-code">05</span><span class="purpose-copy">PR 必填內容</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-1 folder">workflows/</span><span class="repo-tree-purpose"><span class="journey-code">01／03／04／05</span><span class="purpose-copy">6 條現行自動流程</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">ci.yml</span><span class="repo-tree-purpose"><span class="journey-code">03</span><span class="purpose-copy">執行已宣告模組</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">issue-triage.yml</span><span class="repo-tree-purpose"><span class="journey-code">01</span><span class="purpose-copy">檢查並整理工作單</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">milestone-lifecycle.yml</span><span class="repo-tree-purpose"><span class="journey-code">01</span><span class="purpose-copy">同步交付批次狀態</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">osv.yml</span><span class="repo-tree-purpose"><span class="journey-code">04</span><span class="purpose-copy">每週與手動漏洞掃描</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">pr-policy.yml</span><span class="repo-tree-purpose"><span class="journey-code">05</span><span class="purpose-copy">Issue／分支／PR 規則</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path depth-2">spec-to-issue.yml</span><span class="repo-tree-purpose"><span class="journey-code">01</span><span class="purpose-copy">規格自動開單</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row project-owned"><span class="repo-tree-path folder">docs/specs/</span><span class="repo-tree-purpose"><span class="journey-code">01</span><span class="purpose-copy">功能規格／工作定義</span></span><span class="scope-badge shared">共用</span><span class="owner-badge project">專案持有</span></div>
          <div class="repo-tree-row project-owned"><span class="repo-tree-path folder">docs/＋site/</span><span class="repo-tree-purpose"><span class="journey-code">09</span><span class="purpose-copy">專案說明、決策與內部網站</span></span><span class="scope-badge shared">共用</span><span class="owner-badge shared">共同維護</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path folder">policies/</span><span class="repo-tree-purpose"><span class="journey-code">07</span><span class="purpose-copy">repo 規則／治理</span></span><span class="scope-badge shared">共用</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path folder">scripts/</span><span class="repo-tree-purpose"><span class="journey-code">01／03／07</span><span class="purpose-copy">開單、驗證與套用設定</span></span><span class="scope-badge mixed">混合</span><span class="owner-badge template">公版主導</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path">version source＋CHANGELOG＋release-please config／manifest</span><span class="repo-tree-purpose"><span class="journey-code">06</span><span class="purpose-copy">保留版本基線；發版 Action 未啟用</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge shared">共同維護</span></div>
          <div class="repo-tree-row project-owned"><span class="repo-tree-path folder">src/＋tests/；typescript/src/＋tests/</span><span class="repo-tree-purpose"><span class="journey-code">02／03</span><span class="purpose-copy">啟用模組的產品程式</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge project">專案持有</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path">README.md＋AGENTS.md＋CLAUDE.md</span><span class="repo-tree-purpose"><span class="journey-code">01–08</span><span class="purpose-copy">人與 AI 的使用規範</span></span><span class="scope-badge shared">共用</span><span class="owner-badge shared">共同維護</span></div>
          <div class="repo-tree-row"><span class="repo-tree-path">pyproject.toml／uv.lock／package.json／pnpm-lock.yaml</span><span class="repo-tree-purpose"><span class="journey-code">03／04</span><span class="purpose-copy">語言工具與相依版本</span></span><span class="scope-badge mixed">依 profile</span><span class="owner-badge shared">共同維護</span></div>
        </div>
        <div class="repo-map-legend"><span><strong>黃色編號：</strong>對照左側旅程 tag。<strong>模板影響：</strong>公版主導會在 update 提出差異；共同維護可能衝突並由人處理。</span><span><strong>橘線：</strong>專案持有且不改寫。</span></div>
      </div>
{{< /legacy >}}

{{< basic >}}
| 路徑 | 作用 | 責任 |
| --- | --- | --- |
| `.csarc/config.yml` | 記錄公版來源、語言、分支與選用能力 | 公版主導 |
| `.github/ISSUE_TEMPLATE/`、`pull_request_template.md` | 工作定義與 PR 契約 | 公版主導 |
| `.github/workflows/` | 6 條現行流程：工作單整理、里程碑同步、規格開單、PR 規則、必要驗證與漏洞排程 | 公版主導 |
| `AGENTS.md`、`README.md`、`CLAUDE.md` | Agent 工作方式與使用者入口 | 共同維護 |
| `policies/`、`CODEOWNERS`、`.github/REVIEWERS` | 期望設定、owner 與 reviewer | 共同維護 |
| `scripts/` | 本機驗證、工作同步與套用設定 | 公版主導 |
| `docs/`、`site/` | 專案說明、規格、決策與內部網站 | 共同維護 |
| `src/`、產品測試與規格 | 真正產品行為 | 專案持有 |

{{< detail key="files-update" title="更新時怎麼保護產品內容" >}}
Copier 在短分支嘗試更新；若有衝突，只列出檔案且不修改 repo，調整後重跑，再由 PR 審查。建立、既有 repo 導入與同一 repo 後續 update 都有 fixture；回歸測試會刻意加入產品檔案，再確認更新後內容沒有被覆寫。

Root 與 `template/` 同時使用的 workflow、policy、script 與文件由同步程式維持一致；只因專案選項而不同的檔案則以實際生成專案驗證。目前版本與發佈設定檔仍保留，但對應 GitHub Actions 尚未啟用。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="method" track="method" eyebrow="步驟 01" title="先把要做的事定義清楚" subtitle="把需求整理成可執行的 Issue；多張工作需要一起推進時，才建立里程碑。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 1｜<span class="accent">把需求整理成可以開始的工作</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>一張 Issue 定義一項可獨立完成的改變；多項工作需要共同目標與期限時，才使用里程碑。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>統一 Issue 與里程碑的內容，讓人與 agent 在動手前知道要解決什麼、怎樣算完成。</p>
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
          <summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">先定義單項工作，需要時才組成里程碑</span></summary>
          <ul class="work-definition-list">
            <li><strong>單項工作：</strong>先建立 Issue，寫清楚問題、完成條件、驗證方式與負責人；內容足以開始實作就不增加其他文件。</li>
            <li><strong>工作分支：</strong>開始實作時，一張 Issue 建立一個短期分支，以 <code>type/&lt;Issue&gt;-short-slug</code> 命名；同一分支不混入其他工作。</li>
            <li><strong>Issue 類型與拆分：</strong>先選工作類型，只在工作能獨立完成或超出原範圍時拆分。<details class="package-disclosure inline-disclosure"><summary><span class="tech-name">查看可用類型與拆分規則</span></summary><div class="package-health"><ul><li><strong>Feature：</strong>需要多項工作一起完成的成果。</li><li><strong>Task：</strong>可獨立完成與驗證的工作。</li><li><strong>Bug：</strong>結果不符合預期。</li><li><strong>Documentation：</strong>只修改文件或範例。</li><li><strong>拆分：</strong>同一個完成條件與同一份驗證能證明就不拆；能獨立完成或超出原範圍但必須補做，才建立 Sub-issue。Parent 表示未完成的共同成果，Dependency 表示先後順序。</li></ul></div></details></li>
            <li><strong>里程碑：</strong>多張 Issue 有共同目標、期限或交付批次時才建立，並指定一張生命週期追蹤 Issue。標題固定為 <code>Milestone &lt;編號&gt;: &lt;里程碑名稱&gt;</code>，冒號後須與里程碑名稱完全相同；核准、反駁與提前終止留在內文與留言。至少一位非提案者同意，且沒有尚未解決的反駁，才開始執行。</li>
            <li><strong>里程碑分支：</strong>採本模板預設的交付分支模式時，一個進行中的里程碑只使用一個 <code>dev/m&lt;里程碑&gt;-*</code>；所屬工作分支都合入這裡，里程碑之間不共用。</li>
            <li><strong>例外：</strong>Duplicate 是 Issue 的重複結案方式；緊急工作仍先定義為 Bug，如何快速交付由「PR／合併」處理。</li>
          </ul>
        </details>
      </div>
      <aside class="config-guidance" data-config-direct="true"><strong>固定與可調政策</strong><ul><li><strong>固定基線：</strong>Issue 必須有問題與完成條件、空白 Issue 關閉；標題、分類、工作層級與里程碑啟動門檻由公版統一，不提供停用開關。</li><li><strong>專案選擇：</strong><code>docs/specs/</code> 的 <code>tracking</code> 可選 <code>issue</code>、<code>story</code> 或 <code>none</code>，決定規格是否同步成追蹤工作。</li><li><strong>設定位置：</strong><code>.github/ISSUE_TEMPLATE/</code>、<code>AGENTS.md</code>、<code>docs/milestone-description.md</code> 與 <code>docs/specs/</code>。</li></ul></aside>
      <p class="method-reference reference">Ref. <a href="https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues" target="_blank" rel="noreferrer">GitHub sub-issues</a>。</p>
{{< /legacy >}}

{{< basic >}}
### 我們的選擇

- **整體：** 先把需求整理成一張可獨立完成與驗證的 Issue。
- **工作分支：** 開始實作時，每張 Issue 建立一個 `type/<Issue>-short-slug` 短期分支，不混入其他工作。
- **里程碑：** 多張工作有共同目標、期限或交付批次時才建立，並配一張生命週期追蹤 Issue。
  - 標題使用 `Milestone <編號>: <里程碑名稱>`；冒號後須與里程碑名稱完全相同。
  - 核准、反駁與提前終止寫在內文或留言，不放進標題。
  - 至少一位非提案者同意，且沒有尚未解決的反駁，才開始執行。
  - 採預設交付分支模式時，一個進行中的里程碑只使用一個 `dev/m<里程碑>-*`；所屬工作分支都合入這裡。
- **Issue：** 選擇 Feature、Task、Bug 或 Documentation 表單，再寫清楚問題、完成條件與驗證。
  - 標題使用清楚的英文；建立者預設負責這張 Issue。
- **例外：** 重複工作以 Duplicate 結案；緊急工作仍先定義為 Bug，交付方式由「PR／合併」處理。

{{< disclosure key="work-item-details" title="Issue 類型與拆分規則" >}}
- Feature＝需要多項工作一起完成的成果。
- Task＝可以獨立完成與驗證的工作。
- Bug＝實際結果與預期不同。
- Documentation＝只修改文件或範例。
- 同一個完成條件與同一份驗證能證明就不拆；能獨立完成或超出原範圍但必須補做，才拆成 Sub-issue。
- Parent 描述尚未達成的共同成果；Dependency 才表示先後阻擋。
{{< /disclosure >}}

### 其他常見做法

- **先做再補文件：**小而明確的工作直接完成；跨時段、有依賴或高風險時才補計畫。
- **規格先行：**先寫清楚需求、設計與工作拆分，再開始開發。
- **變更提案：**先獨立審查準備修改的內容，接受後才併回正式規格。
- **依複雜度分級：**小工作走短流程，大型工作才增加探索、設計、分工與審查。

{{< /basic >}}
{{< /slide >}}

{{< slide key="agents" track="agents" eyebrow="步驟 02" title="先定 AI 規範，再開始實作" subtitle="Issue 說明這次要做什麼；AGENTS.md 說明 agent 在 repo 裡怎麼做。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 2｜<span class="accent">先定 AI 規範，再開始實作</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>Issue 劃定這次工作；<code>AGENTS.md</code> 說明怎麼做；程式與測試提供證據，人保留需求方向與重大風險決策。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>自動產生並檢查 agent 開始前要讀什麼、可修改到哪裡、如何隔離平行工作與怎樣留下驗證；只有客製規範、重大決策與例外需要人判斷。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open><summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">常見的 AI 協作設計</span></summary><ul><li><strong>Repo 內指引：</strong>把固定命令與界線放在版本控制中，讓不同 agent 讀同一份規則。</li><li><strong>規格產物接力：</strong>大型工作先產生 spec、plan、tasks，再逐步交給 agent 執行。</li><li><strong>角色與調度：</strong>用專門角色、skills 或佇列安排多個 agent；適合工作量已大到需要額外協調時。</li><li><strong>人類檢查點：</strong>在需求、重大取捨、外部影響與不可逆操作前停下來取得決定。</li></ul></details>
        <details class="decision-step decision-fold recommended" open><summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">六項責任各有唯一位置</span></summary><ul class="work-definition-list"><li><strong>工作與脈絡：</strong>GitHub Issue／PR 記錄範圍、進度與證據；核准的 spec／ADR 保存長期決策，跨 session、高風險或難復原工作才增加 plan，不保存聊天逐字稿。</li><li><strong>AI 規範：</strong>根目錄 <code>AGENTS.md</code> 是唯一來源；<code>CLAUDE.md</code> 只做薄匯入，子目錄只有規則真的不同時才覆寫。</li><li><strong>修改隔離：</strong>每項可寫工作各用 branch／worktree，只平行處理互不依賴的範圍；唯讀工作不必另開 worktree。</li><li><strong>驗證證據：</strong>執行最小且相關的本機程式；Action 只負責事件、權限與呼叫同一程式，不複製邏輯。</li><li><strong>決策與授權：</strong>人負責需求、重大取捨、外部影響與不可逆操作；審查、合併資格與例外由「規則治理」定義。</li><li><strong>模板建立與更新：</strong>Copier 負責產生與更新共用基線；既有 repo 的更新契約由「模板升級」定義。</li></ul></details>
      </div>
      <aside class="config-guidance" data-config-direct="true"><strong>固定與可調政策</strong><ul><li><strong>固定基線：</strong><code>AGENTS.md</code> 是 AI 規範唯一來源；可寫工作使用 branch／worktree，驗證與治理不重複寫進提示詞。</li><li><strong>可以調整：</strong><code>.csarc/config.yml</code> 的 <code>project_run_command</code> 指定產品啟動方式；既有 repo 可用 <code>project_verification_hook</code> 增加一支專案驗證程式。</li><li><strong>設定位置：</strong><code>.csarc/config.yml</code>、<code>AGENTS.md</code>、<code>CLAUDE.md</code> 與 <code>scripts/cleanup-worktrees</code>。</li></ul></aside>
{{< /legacy >}}

{{< basic >}}
- **預設自動：** 模板會產生並檢查 AI 規範；只有客製規範、重大決策與例外需要人判斷。
- **工作與脈絡：** GitHub Issue／PR 記錄工作；核准的 spec／ADR 保存長期決策，必要時才加 plan。
- **AI 規範：** 根目錄 `AGENTS.md`；`CLAUDE.md` 只薄匯入。
- **修改隔離：** 每項可寫工作各用 branch／worktree；唯讀工作不用。
- **驗證證據：** 本機程式是唯一邏輯；Action 只呼叫它。
- **決策與授權：** 人保留重大決策；審查與合併規則只由「規則治理」定義。
- **模板建立與更新：** Copier 負責共用基線；既有 repo 更新由「模板升級」定義。

{{< /basic >}}
{{< /slide >}}

{{< slide key="contract" track="contract" eyebrow="步驟 03" title="先驗證改動，再讓 CI 重跑同一套規則" subtitle="日常改動跑必要檢查；準備發版或緊急修正才跑完整驗證。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 3｜<span class="accent">先驗證改動，再讓 CI 重跑同一套規則</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>開發時先跑與改動直接相關的測試；Issue PR 再由同一支 Action 依變更範圍選擇 docs、fast 或 full。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>把測試邏輯留在 repo 內可直接執行的 scripts／tests；GitHub Action 只負責何時啟動、使用哪些權限，以及呼叫同一份程式。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open><summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">依 repo 規模與風險選擇驗證範圍</span></summary><ul><li><strong>每次全跑：</strong>每張 PR 都取得完整信心，適合測試很小、執行很快的 repo。</li><li><strong>只跑受影響項目：</strong>依 dependency graph 或路徑縮小範圍，回饋快，但分流規則必須可測。</li><li><strong>獨立 pipeline runtime：</strong>本機與不同 CI 平台執行相同 pipeline，換來額外引擎與環境成本。</li><li><strong>分階段驗證：</strong>日常快速、整合候選完整；需要清楚定義何時升級與哪一份結果有效。</li></ul></details>
        <details class="decision-step decision-fold recommended" open><summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">一份邏輯、一支 Action、兩種 repo 範圍</span></summary><ul class="work-definition-list"><li><strong>開發中：</strong>人或 agent 只跑能證明這次修改的 focused check，先取得新鮮輸出再宣稱完成。</li><li><strong>Issue PR（工作分支 → dev）：</strong>系統依修改內容自動選擇適合的檢查；無法判斷時執行完整檢查。</li><li><strong>需要完整檢查時：</strong>準備發版、緊急修正，或系統無法安全縮小測試範圍時，執行完整檢查。</li><li><strong>同一套邏輯：</strong>GitHub Actions 只有一個 <code>verify</code> job，最多執行 30 分鐘，只呼叫 repo 內既有腳本。</li><li><strong>專案範圍：</strong>一般專案只檢查自己的改動；公版專案還會確認模板產生的新專案能正常使用。</li></ul></details>
      </div>
      <aside class="config-guidance" data-config-direct="true"><strong>固定與可調政策</strong><ul><li><strong>固定基線：</strong>本機與 CI 共用同一份 scripts／tests；Issue PR 依風險選 fast 或 full，發版與無法判斷的變更一定跑 full。</li><li><strong>可以調整：</strong><code>coverage_mode</code>、<code>coverage_threshold</code> 與 <code>enable_precommit</code>；進階團隊可用 <code>use_reusable_workflow</code> 搭配固定 SHA。</li><li><strong>設定位置：</strong><code>.csarc/config.yml</code>；執行入口是 <code>scripts/verify-fast</code>、<code>scripts/verify</code> 與 <code>.github/workflows/ci.yml</code>。</li></ul></aside>
{{< /legacy >}}

{{< basic >}}
- **開發中：**只跑能證明本次修改的 focused check。
- **Issue PR（工作分支 → dev）：**系統依修改內容自動選擇適合的檢查；無法判斷時執行完整檢查。
- **需要完整檢查時：**準備發版、緊急修正，或系統無法安全縮小測試範圍時，執行完整檢查。
- **Action：**只有一個 `verify` job，最多執行 30 分鐘，只呼叫 repo 內既有腳本。
- **專案範圍：**一般專案只檢查自己的改動；公版專案還會確認模板產生的新專案能正常使用。

測試邏輯只寫在 scripts／tests；本次只恢復 `.github/workflows/ci.yml`。
{{< /basic >}}
{{< /slide >}}

{{< slide key="languages" track="languages" eyebrow="步驟 04" title="選擇程式語言後，自動帶入適合的檢查" subtitle="每種語言各自定義工具與測試；共通規則只執行一次。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 4｜<span class="accent">每種程式語言各自管理</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>使用者只要選擇專案語言，模板就產生對應版本、鎖檔、格式、靜態檢查、測試與建置設定。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>依選擇的程式語言準備檢查；同時使用多種語言時，共通項目不重複執行。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open><summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">語言工具可以集中，也可以交回各生態圈</span></summary><ul><li><strong>單一跨語言工具：</strong>入口一致，但需要另外維護抽象層。</li><li><strong>各語言原生工具：</strong>開發者容易理解，版本與輸出則要由模板統一管理。</li><li><strong>每種組合各寫一套：</strong>初期直觀，組合增加後很容易重複與漂移。</li></ul></details>
        <details class="decision-step decision-fold recommended" open><summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">每種語言各自檢查需要的事情</span></summary><ul><li><strong>所有專案：</strong>檢查工作規則、文件、敏感資料與套件風險。</li><li><strong>Python：</strong>檢查程式格式、型別、測試，以及能否製作安裝包。</li><li><strong>Rust：</strong>檢查程式格式、常見錯誤、測試，以及正式版本能否建置與打包。</li><li><strong>TypeScript：</strong>檢查程式格式、型別、測試，以及能否製作安裝包。</li><li><strong>同時使用多種語言：</strong>合併各語言的檢查，共通項目只跑一次。</li></ul></details>
      </div>
      <aside class="config-guidance"><strong>固定與可調政策</strong><ul><li><strong>固定基線：</strong>每種語言使用自己的主流工具並由同一入口協調；不建立組合專屬流程。</li><li><strong>可以調整：</strong><code>languages</code>、<code>python_support_mode</code> 與 <code>python_min_version</code>；其餘進階參數直接使用各語言原生設定檔。</li><li><strong>Python：</strong><code>uv</code> 依 <code>uv.lock</code> 安裝；<code>Ruff</code> 負責格式與 lint（目前 80 字寬、Google docstring）；<code>ty</code> 檢查型別；<code>pytest</code> 執行測試；<code>coverage.py</code> 檢查覆蓋率；Hatch 驗證 wheel。集中在 <code>pyproject.toml</code>。</li><li><strong>Rust：</strong><code>rustfmt</code> 檢查格式；<code>Clippy</code> 將 lint 警告視為失敗；<code>Cargo</code> 依 <code>Cargo.lock</code> 執行測試、正式建置與打包。設定在 <code>rust-toolchain.toml</code> 與 <code>Cargo.toml</code>。</li><li><strong>TypeScript：</strong><code>pnpm</code> 依 <code>pnpm-lock.yaml</code> 安裝；<code>Biome</code> 負責格式與 lint；<code>TypeScript</code> 檢查型別並建置；<code>Vitest</code> 執行測試與覆蓋率；<code>npm pack</code> 驗證套件。設定在 <code>package.json</code>、<code>biome.json</code> 與 <code>tsconfig.json</code>。</li></ul></aside>
{{< /legacy >}}

{{< basic >}}
選擇專案語言後，模板會自動準備對應檢查：

- **所有專案：**檢查工作規則、文件、機密與套件安全。
- **Python：**檢查格式、型別、測試及安裝包。
- **Rust：**檢查格式、常見錯誤、測試、正式建置及安裝包。
- **TypeScript：**檢查格式、型別、測試及安裝包。

同一項共通檢查只跑一次。語言可以同時勾選，但不另外建立或說明每一種排列組合。
{{< /basic >}}
{{< /slide >}}

{{< slide key="pr" track="pr" eyebrow="步驟 06" title="讓完成的改動可審查、可交付" subtitle="工作 PR 先完成單項工作；發版 PR 再把已驗證的整批成果送進 main。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 6｜<span class="accent">讓完成的改動可審查、可交付</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>這一頁從準備開 PR 開始：工作 PR 完成一張 Issue，發版 PR 再確認整批成果。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>把完成的修改帶到正確分支，確認它連回原工作、通過驗證並在合併後結束對應工作。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open><summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">依團隊規模選擇不同合併模型</span></summary><ul><li><strong>GitHub Flow：</strong>每張完成的 PR 直接進 main，路徑最短，適合可持續交付的團隊。</li><li><strong>長期整合分支：</strong>多項工作先在 dev／release branch 集中驗收，代價是要處理同步。</li><li><strong>Stacked PR：</strong>把大型改動拆成相依的小 PR，審查較聚焦，但需要維護堆疊順序。</li><li><strong>Merge queue：</strong>把已核准 PR 依最新 main 重新驗證後排序合併，需要平台門禁支援。</li></ul></details>
        <details class="decision-step decision-fold recommended" open><summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">工作 PR 完成單項工作，發版 PR 完成交付批次</span></summary><ul><li><strong>Issue PR（工作分支 → dev）：</strong>一張 PR 只完成一張可驗收 Issue；內文以 <code>Closes #N</code> 連回同號未結案 Issue，合併後結束該工作。</li><li><strong>PR 標題：</strong>採用 Angular／Conventional Commits 格式，簡短說明這次改動與版本影響。<details class="package-disclosure inline-disclosure"><summary><span class="tech-name">查看可用格式與版本影響</span></summary><div class="package-health"><p><strong>格式：</strong><code>type(scope)!: English summary</code></p><ul><li><strong>type：</strong><code>feat</code> 新功能、<code>fix</code> 修錯、<code>docs</code> 文件、<code>refactor</code> 重構、<code>test</code> 測試、<code>build</code> 建置／相依、<code>ci</code> 自動化、<code>chore</code> 維護、<code>revert</code> 撤回。</li><li><strong>scope：</strong>可省略；使用小寫指出影響範圍。</li><li><strong>!</strong>：可省略；只在破壞相容性時使用。</li><li><strong>版本影響：</strong><code>feat</code>＝minor、<code>fix</code>／<code>revert</code>＝patch、<code>!</code>＝major；其餘不主動升版。</li></ul></div></details></li><li><strong>PR 資料：</strong>分類、里程碑與負責人都要完整。<details class="package-disclosure inline-disclosure"><summary><span class="tech-name">查看 Label、里程碑與負責人規則</span></summary><div class="package-health"><ul><li><strong>Label：</strong><code>enhancement</code>、<code>bug</code>、<code>documentation</code> 擇一，且必須和連結的 Issue 相同。</li><li><strong>里程碑：</strong>必須和連結的 Issue 相同；Issue 未加入里程碑時，PR 也不加入。</li><li><strong>負責人：</strong>PR 作者必須列為 Assignee；正式交接時可再加入其他負責人。</li></ul></div></details></li><li><strong>發版 PR（dev → main）：</strong>里程碑工作完成後才執行完整驗證，確認整批內容與證據；里程碑的結案仍由生命週期追蹤 Issue 控制。</li><li><strong>同步：</strong>main 前進後，以另一張 PR 把變更帶回仍在開發的 dev 分支；不直接推送或改寫歷史。</li><li><strong>例外與授權：</strong>Hotfix 可從 <code>fix/*</code> 直接進 main，但仍需 Issue、驗證與審查；審查者、Alpha 例外與平台門禁都由「規則治理」定義。</li></ul></details>
      </div>
      <aside class="config-guidance"><strong>固定與可調政策</strong><ul><li><strong>固定基線：</strong>PR 必須連回一張工作、符合標題與分類規則、通過驗證；工作 PR 與發版 PR 的責任不可混用。</li><li><strong>可以調整：</strong><code>branch_strategy</code> 選分支模型，<code>code_owner</code> 與 <code>reviewers</code> 指定擁有者和審查人選。</li><li><strong>設定位置：</strong><code>.csarc/config.yml</code>；產生到 <code>pull_request_template.md</code>、<code>CODEOWNERS</code>、<code>REVIEWERS</code> 與 PR policy。</li></ul></aside>
{{< /legacy >}}

{{< basic >}}
| PR 階段 | 目的地 | 這一步完成什麼 |
| --- | --- | --- |
| Issue PR | 工作分支 → `dev/m*` 或 `main` | 審查一項改動；合併後關閉連結的 Issue |
| 發版 PR | `dev/m*` 或 `dev/i*` → `main` | 完整驗證整批成果後交付；「版本／交付」再負責結束里程碑 |

{{< disclosure key="pr-version-intent" title="PR 標題、分支與例外" >}}
- 工作分支使用 `type/<Issue>-short-slug`，並連回同號未結案 Issue。
- PR 標題使用 Angular／Conventional Commits 格式：`type(scope)!: English summary`。type 可用 `feat` 新功能、`fix` 修錯、`docs` 文件、`refactor` 重構、`test` 測試、`build` 建置／相依、`ci` 自動化、`chore` 維護、`revert` 撤回；scope 與 `!` 可省略。版本意圖為 `feat`＝minor、`fix`／`revert`＝patch、`!`＝breaking／major，其餘不主動升版。
- 工作 Label 與里程碑要和 Issue 一致；PR 作者必須列為負責人。
- 里程碑工作進 `dev/m<里程碑>-*`；一般獨立工作從最新 `main` 建立並直接回 `main`。
- main 前進不會 fan out 同步；各里程碑到 final promotion 才用一張 `sync/main-to-m*` PR 納入最新 main，只有 owner 明列 dependency 時可提前同步。
- 文件化的獨立 canary 可使用一條短命 `dev/i<Issue>-*`；明確標示的 standalone hotfix 可直接進 main。誰能合併由「規則治理」決定。
{{< /disclosure >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="supply" track="supply" eyebrow="步驟 05" title="第三方套件分開更新、檢查與記錄" subtitle="一般新版先觀察，已知漏洞立即處理，發版成品留下可追查清單。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 5｜<span class="accent">第三方套件分開更新、檢查與記錄</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>套件從哪裡更新、能否重裝、有沒有已知漏洞，以及成品包含什麼，是四件需要分開確認的事。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>依賴異動必須能重裝與驗證；一般新版保留觀察期，已公開漏洞不等待，發版時再列出實際成品內容。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open><summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">依規模選擇不同組合</span></summary><ul><li><strong>自動更新服務：</strong>定期提出升版的變更提案（PR），適合不想人工巡查版本的團隊。</li><li><strong>套件安裝政策：</strong>固定可安裝版本並觀察剛發布的版本，降低每次安裝拿到不同內容的風險。</li><li><strong>漏洞掃描：</strong>比對公開漏洞資料庫；即使沒有升版 PR，也能發現既有風險。</li><li><strong>軟體成分清單（SBOM）：</strong>發版時列出成品包含的套件，供事件追查與使用者核對。</li></ul></details>
        <details class="decision-step decision-fold recommended" open>
          <summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">可重現安裝、更新與漏洞掃描各自負責</span></summary>
          <ul><li><strong>安裝：</strong>Python 與 TypeScript 都依鎖定版本清單（lockfile）重裝；TypeScript 另拒絕未滿三天的一般新版。</li><li><strong>更新：</strong>自動更新服務（Dependabot）每週依套件來源分組提出 PR；一般新版等三天，已知安全修補不等待。</li><li><strong>漏洞：</strong>已知漏洞掃描（OSV）檢查依賴變更與發版候選；每週與手動掃描補上沒有 PR 的期間。</li><li><strong>成品：</strong>軟體成分清單（SBOM）列出真正成品包含的套件，由清單工具 Syft 產生並接受同一套驗證。</li><li><strong>工具邊界：</strong>鎖定版本只證明每次安裝內容一致；漏洞掃描只認已公開資料；成分清單用來追查，不會主動阻擋漏洞。</li></ul>
        </details>
      </div>
      <aside class="config-guidance"><strong>固定與可調政策</strong><ul><li><strong>固定基線：</strong>lockfile 重裝、Dependabot、OSV 與成品 SBOM 各自負責，不能互相取代；一般新版觀察三天，安全更新不等待。</li><li><strong>可以調整：</strong><code>security_reporting_channel</code> 設定私密回報管道；<code>project_visibility</code> 與 <code>enable_codeql</code> 決定是否產生 CodeQL。</li><li><strong>設定位置：</strong><code>.csarc/config.yml</code>；產生到 lockfile、<code>dependabot.yml</code>、<code>osv.yml</code>、<code>codeql.yml</code> 與 <code>SECURITY.md</code>。</li></ul></aside>
{{< /legacy >}}

{{< basic >}}
模板會自動執行例行的更新與安全檢查；只有升級衝突、漏洞處置與風險接受需要人判斷。

| 這次要防什麼 | 模板目前怎麼處理 |
| --- | --- |
| 改了套件卻無法重裝 | PR 會依鎖定版本清單（lockfile）重新安裝，確認每次拿到同一批套件 |
| 剛發布的惡意版本 | 自動更新服務（Dependabot）分組提出 PR；一般新版等三天，安全更新不等待 |
| 已公開漏洞沒有被注意 | 已知漏洞掃描（OSV）會檢查依賴 PR 與發版候選；每週掃描補上沒有 PR 的期間 |
| 發版後不知道包含什麼 | 軟體成分清單（SBOM）列出成品包含的套件；依賴安全負責驗證，交付成品時產生 |

{{< detail key="supply-boundaries" title="這四種保護為什麼要分開" >}}
- **鎖定版本：**確認每次安裝使用同一批套件。
- **觀察期：**不在一般新版發布當天立刻採用。
- **漏洞掃描：**立即比對已公開的安全問題，不等待三天。
- **成品清冊（SBOM）：**列出發布成品實際包含的套件，方便追查；它本身不會阻擋漏洞。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="deploy" track="deploy" eyebrow="步驟 07" title="版本規則與成品接續" subtitle="先驗證 promotion 來源，再依平台當下能力選安全交付模式。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 7｜<span class="accent">版本規則與成品接續</span></h2>
        <p class="subtitle"><strong>Release 路徑依已驗證的 promotion 邊界與當下能力選擇：</strong>PR 與成品交接能力都確認時使用 release-please；否則只在最新 main 已含經審查的版本與 CHANGELOG 時直接交付，再不行就明確停在 verification-only。</p>
      </header>
      <p class="context-line"><strong>設計流程｜</strong>Issue PR 只宣告 patch／minor／major／no-release 意圖；里程碑完成、isolated canary 或 hotfix 形成 release 邊界，standalone 與 bot PR 直接進 main 後保留 intent，全部 no-release 就略過。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open><summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">不為版本號另加一套平台</span></summary><ul><li><strong>Changesets：</strong>適合 npm workspace；CI-only／Python 案會多背 Node 設定</li><li><strong>Nx release：</strong>適合既有 Nx 大型 workspace；本案只需一個 release unit</li><li><strong>profile 各自編號：</strong>會增加相依矩陣與升級對版成本</li></ul></details>
        <details class="decision-step decision-fold recommended" open><summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">里程碑完成後，依能力選擇交付方式</span></summary><p><strong>里程碑結案：</strong>發版成功並補齊交付證據後，關閉生命週期追蹤 Issue 與里程碑；提前終止時先寫明原因，並移轉或取消未完成 Issue。</p><p><strong>分支清理：</strong>工作 PR 合併後刪除該工作分支；發版完成且未完成工作已移轉或取消後，才刪除里程碑交付分支。GitHub 自動刪除已合併的來源分支，本機只清理乾淨且可確認已合併的 worktree。</p><details class="package-disclosure"><summary><span><span class="tech-name">promotion-gated adaptive release</span>＋單一 SemVer</span></summary><div class="package-health release-policy-health"><p><a href="https://github.com/googleapis/release-please" target="_blank" rel="noreferrer">googleapis/release-please</a>｜Apache-2.0｜持續維護。</p><p><strong>來源證據：</strong>release-source 先核對 promotion 的 full <code>verify</code>、canary state、納入 PR 與 main tree identity；非 promotion／hotfix 的 main commit 只能 verification-only。</p><p><strong>三態能力：</strong><code>allowed</code>、<code>blocked</code>、<code>unknown</code> 分別記錄 Actions PR、contents、Release 與 dispatch；403、409、無 remote 或無管理權都不會被誤當 allowed。</p><table class="release-policy-matrix" aria-label="Release policy capability matrix"><thead><tr><th>前提</th><th>選擇</th><th>行為與保證</th><th>限制與 fallback</th></tr></thead><tbody><tr><td>來源有效且四項 allowed</td><td>Release PR</td><td>可審查版本／changelog；合併後帶 source run ID dispatch 成品</td><td>任一能力漂移就不再選用</td></tr><tr><td>來源有效；PR blocked／unknown；其餘 allowed</td><td>Direct</td><td>只為已版本化且含 CHANGELOG 的最新 main 配置 tag；亂序 run no-op</td><td>缺少版本 commit 時轉為 verification-only，需維護者先開 PR</td></tr><tr><td>來源無效或任一交付寫入非 allowed</td><td>Verification only</td><td>保存 machine-readable artifact</td><td>不建立 release；後續 run 重新判斷</td></tr></tbody></table><p class="reference">Ref. <a href="https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow" target="_blank" rel="noreferrer">GitHub workflow trigger docs</a> and live workflow runs, accessed August 24, 2026.</p></div></details><p><strong>收斂：</strong>direct mode 重讀 default branch head，只有最新 main commit 且 source、tag、CHANGELOG、promotion evidence 一致時才能交付；concurrency 不必保證 FIFO。<br><strong>成品：</strong>workflow 不監聽任意 tag push，只接受 release-source run ID；tag checkout 產生 digest、SBOM／attestation，不重跑 promotion 已完成的 full runtime CI。</p></details>
      </div>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>promotion 與 release-source：</strong><code>promotion.yml</code>＋<code>scripts/promotion_gate.py</code>＋<code>release-please.yml</code></li><li><strong>能力與版本配置：</strong><code>scripts/release_policy.py</code>；CLI 做唯讀 preflight，workflow 每次重新偵測</li><li><strong>查詢證據：</strong>promotion／release-source artifact 保留 90 天，PR、Issue、里程碑、commit 與 tag 作長期索引</li></ul></aside>
      <aside class="selection-note"><strong>目前邊界</strong><span>不要求導入者建立 PAT、GitHub App 或修改無權控制的組織政策；若 contents、Release 或 dispatch 無法確認，workflow 只完成驗證並明確告警，不宣稱已自動發版。Python 排程升版 App 仍是另一個選配身份。</span></aside>
      <table class="decision-register" aria-label="版本來源與同步範圍">
        <thead><tr><th>版本範圍</th><th>單一來源</th><th>必須同步</th><th>獨立狀態</th></tr></thead>
        <tbody>
          <tr><td>公版與 CLI Release</td><td>root <code>.release-please-manifest.json</code></td><td>root 版本檔、README／docs current marker、CHANGELOG、tag、Release 與成品</td><td>無</td></tr>
          <tr><td>Copier 公版 revision</td><td>已發布 tag＋完整 commit SHA</td><td>Release provenance、<code>.csarc/config.yml</code> 的 <code>_commit</code></td><td>不另編版本</td></tr>
          <tr><td>生成專案 Release</td><td>生成後的 <code>.release-please-manifest.json</code></td><td>該專案自己的 manifest、package、CHANGELOG、tag 與成品</td><td>從 <code>0.1.0</code> 開始，不跟隨公版版本</td></tr>
        </tbody>
      </table>
      <p class="context-line"><strong>SemVer scope｜</strong>整份公版只用一個 SemVer：<code>fix(scope)</code> 升 patch、<code>feat(scope)</code> 升 minor、<code>!</code> 升 major；scope 可標 <code>ci</code>、<code>python</code>、<code>typescript</code> 或 <code>template</code>，只要任何已支援 profile 不相容，就視為整份公版的破壞性變更。</p>
      <aside class="selection-note"><strong>選配登記：PyPI／npm 發布</strong><span>GitHub Release 是所有 profile 的共同基線；registry 是生成專案依語言分開選配的能力，預設全部關閉。Root CLI 只隨 GitHub Release 交付，不發布到 PyPI，也沒有 registry publishing job。生成專案的 PyPI／npm job 使用 GitHub environment 與 OIDC 短效憑證，不讀取長效 registry token；CI/CD-only 不產生 registry job。啟用前，package owner 必須在 registry 登記完全相符的 organization／repository、workflow <code>release.yml</code> 與 environment。PyPI 首次發布可先建立 pending publisher；npm 則需由既有 package owner 建立 trusted publisher，並使用 GitHub-hosted runner、Node 22.14+ 與 npm 11.5.1+。</span></aside>
{{< /legacy >}}

{{< basic >}}
- **里程碑結案：**發版成功並補齊交付證據後，關閉生命週期追蹤 Issue 與里程碑；提前終止時先說明原因，並移轉或取消未完成 Issue。
- **分支清理：**工作 PR 合併後刪除工作分支；發版完成並處理完未完成工作後，才刪除該里程碑的交付分支。含未提交內容的本機工作區不會自動刪除。

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

{{< slide key="governance" track="governance" eyebrow="步驟 08" title="先辨識 GitHub 能力，再套用真的管制" subtitle="目前組織實測是 Free＋private，因此 main 尚未受 Ruleset 強制保護。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>先辨識 GitHub 方案，<span class="accent">再套用真的能生效的管制</span></h2>
        <p class="subtitle"><strong>基本導入｜</strong>同一份公版依 Free、Team、Enterprise 與實際 API 能力調整；不把付費功能假裝成已啟用。</p>
      </header>
      <p class="context-line"><strong>目前實測｜</strong><code>Innoguard-Cyber-Arch</code> API 回報 Free＋private；因此 <code>main</code> 現在確實沒有強制保護，CI 紅燈仍可能被有權限者繞過。</p>
      <div class="plan-grid">
        <article class="plan-card current"><h3>Free <span class="plan-state">目前</span></h3><p><strong>保留審查設定，強制能力降級：</strong><code>.github/REVIEWERS</code> 保存 reviewer 名單；private repo 只把期望 Ruleset 保留在 <code>policies/rulesets.json</code>，因為 REST 與 GraphQL 建立 API 都會拒絕。check 標示 DEGRADED。</p><ul><li>目前由人工指定 reviewer；自動輪派 Action 仍在封存區</li><li>沒有 team request 或 merge gate，審查紀錄不能取代強制門禁</li></ul></article>
        <article class="plan-card team"><h3>Team <span class="plan-state">最低建議</span></h3><p><strong>再加上：</strong>private repo Ruleset、protected branches、強制核准、CODEOWNER 與必要檢查。</p><ul><li>同一個 CODEOWNERS team 必須存在並有 repo write access</li><li>公版即可套用現有 repo Ruleset</li></ul></article>
        <article class="plan-card enterprise"><h3>Enterprise <span class="plan-state">組織級</span></h3><p><strong>再加上：</strong>SAML SSO／SCIM、internal repo、private/internal 部署保護、私有 Pages、稽核串流與 IP 限制。</p><ul><li>組織／Enterprise Ruleset 可集中治理</li><li>目前只偵測並提示，不自動改組織設定</li></ul></article>
      </div>
      <aside class="selection-note"><strong>部署原則</strong><span><code>plan</code> 先查帳號方案、repo 可見性、repository teams 與 Ruleset API；team 不存在、不可見或沒有 repo write access 時直接停止，不能再被 Free private 的降級路徑掩蓋。導入時可設定一到多位 reviewers；目前由人工指定，自動輪派 Action 尚未恢復。Free private 不支援 team request，也無法強制核准。Web UI 可供管理員人工預建 disabled Ruleset，但公開 REST／GraphQL API 無法自動建立。腳本本身不會改可見性。依序執行 <code>plan</code>、<code>apply</code>、<code>check</code>；可修正差異 fail-closed，不支援的 Ruleset 或受限制的管理欄位回報具體 DEGRADED。完整管理欄位驗證應由管理員在可信任 checkout 使用 Administration read 憑證，不把該 token 暴露給 PR 程式碼。GitHub 方案升級、不可逆操作與組織權限變更都需組織 owner 另案核准；模板不會自行執行。</span></aside>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>查方案與 API：</strong><code>scripts/apply-repository-settings.sh plan</code></li><li><strong>套用支援的設定：</strong><code>scripts/apply-repository-settings.sh apply</code></li><li><strong>比對全部可觀察設定：</strong><code>scripts/apply-repository-settings.sh check</code> 比對 CODEOWNERS、repository、Actions、政策標籤與有效 Ruleset</li><li><strong>檢查治理漂移：</strong><code>scripts/check-governance-drift</code> 可在本機執行；原本的 daily Action 位於 <code>archive/ci-cd/</code>，目前不會排程或自動開 Issue</li></ul></aside>
      <table class="decision-register" aria-label="GitHub 方案與 apply／check 行為對照">
        <thead><tr><th>GitHub 方案與可見性</th><th><code>apply</code> 結果</th><th><code>check</code>／PR／CI/CD 行為</th></tr></thead>
        <tbody>
          <tr><td>Free＋public</td><td>透過 REST 套用並啟用 Ruleset</td><td>驗證 <code>main</code> 的有效規則；缺少或不符即失敗</td></tr>
          <tr><td>Free organization＋private</td><td>套用基本設定，並把期望 Ruleset 保留在 <code>policies/rulesets.json</code>；公開 API 無法建立 Ruleset</td><td>標示 <code>DEGRADED</code>，由人工指定 reviewer；team request、紅燈或未核准都不能成為 merge gate</td></tr>
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
| Free organization＋private | 套基本設定，期望 Ruleset 留在 `policies/rulesets.json` | 標示 `DEGRADED`，人工指定 reviewer；無 merge gate |
| Pro 個人＋private | 套用 Ruleset | 與 Free public 相同 |
| Team／Enterprise organization＋private | 確認 CODEOWNERS team 後套用 Ruleset | 審查、CODEOWNER 與 status checks 成為 merge gate |

{{< detail key="governance-observation" title="實際操作與觀察限制" >}}
依序執行 `scripts/apply-repository-settings.sh plan`、`apply`、`check`。`check` 比對 CODEOWNERS、repository、Actions、政策 labels 與有效 Ruleset；`scripts/check-governance-drift` 可在本機執行，但原本的每日 Action 仍在 `archive/ci-cd/`，不會排程或自動開 Issue。

每次檢查都是快照：兩次執行之間曾變更又復原的事件仍需 GitHub audit log 或組織層監控。完整管理欄位應由管理員在可信任 checkout 使用 Administration read 憑證，不把 token 暴露給 PR 程式碼。GitHub 方案升級、不可逆操作與組織權限變更需組織 owner 另案核准。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="template-release" track="template-release" eyebrow="步驟 09" title="Copier 保持同步，公版也吃自己的規則" subtitle="模板錯誤會一次影響多個專案，因此建立、導入與更新都要實跑。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>Copier 保持同步，<span class="accent">公版本身也吃自己的規則</span></h2>
        <p class="subtitle"><strong>基本導入。</strong><code>template/</code> 是下發內容唯一來源；root 只因 GitHub 讀取慣例保留公版自己的治理設定，43 對逐位元組相同的檔案由產生腳本從 root 生成 <code>template/</code> 副本。</p>
      </header>
      <p class="context-line"><strong>問題與目的｜</strong>模板錯誤會一次影響多個專案；每次修改都要真的建立新案、導入既有案，再讓已導入的 repo 接收更新並通過完整驗證。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open><summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">這次不選，因為無法持續同步或驗證</span></summary><ul><li><strong>GitHub Template：</strong>只複製一次，不記得來源與答案</li><li><strong>PyScaffold：</strong>可參考 Python 結構，但會形成第二套更新機制</li><li><strong>只驗 YAML：</strong>無法證明新案、既有案與更新真的能跑</li></ul></details>
        <details class="decision-step decision-fold recommended" open><summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">Copier＋建立／更新回歸</span></summary><details class="package-disclosure"><summary><span><span class="tech-name">Copier</span>＋root dogfood＋建立／更新回歸</span></summary><div class="package-health"><p><a href="https://github.com/copier-org/copier" target="_blank" rel="noreferrer">copier-org/copier</a>｜MIT｜公開、未封存且持續維護。</p><p><strong>採用原因：</strong>記錄來源、語言與答案，能把新版模板套回既有 repo；衝突時保持 repo 不變，調整後重跑再由 PR 審查。</p></div></details><p><strong>建立：</strong>共通基線與 Python、Rust、TypeScript 模組各自實跑驗證；多選時合併模組，不建立組合專屬流程。<br><strong>導入與更新：</strong>adopt／update dry-run 先預覽，確認後只遷移舊 CSARC 結構；接著對同一 repo 執行下一版 Copier update、確認產品目錄未被覆寫，最後執行生成專案的完整驗證。<br><strong>版本：</strong>公版與所有語言模組共用一個 SemVer；各語言基線則依自己的穩定版政策前進。</p></details>
      </div>
      <p class="context-line"><strong>root／template 配對檔案｜</strong>43 對 workflow、policy、文件、script 與 test（例如 <code>promotion.yml</code>、<code>docs/ci-policy.md</code>、<code>scripts/promotion_gate.py</code>）在 root 與 <code>template/</code> 之間逐位元組相同；過去只靠 <code>verify-template.sh</code> 在 CI 用 <code>diff</code> 事後比對，任何一邊漏改要等驗證跑完才被抓到。現在 <code>scripts/sync-paired-files.sh</code> 把 root 當成唯一來源：本機執行它會立即重新產生每個 <code>template/</code> 副本；加 <code>--check</code> 則不寫檔，只驗證每個副本是否符合產生腳本的確定性輸出（內容與可執行位元），任何一對不一致就印出差異並失敗。<code>verify-template.sh</code> 已改成呼叫 <code>--check</code>，並用一段複製到暫存目錄、蓄意注入內容與權限落差、確認失敗、重新產生、確認通過的回歸測試證明這個機制會擋下漂移。<code>dependabot.yml</code>、<code>.gitignore</code> 等僅因 Jinja 變數不同的檔案不在此列，仍由既有的「產生一個實案並與 root 比對」測試把關；<code>AGENTS.md</code>／<code>README.md</code> 等文件因 root 與下游專案的治理內容本來就不同，不屬於重複維護，故未強行合併。</p>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>下發來源、所選語言模組、保留路徑與功能開關：</strong><code>template/</code>＋<code>copier.yml</code></li><li><strong>root-only CI 與建立／導入／更新驗證：</strong><code>.github/</code>＋<code>scripts/verify-template.sh</code>；生成 repo 不會收到這支腳本或 template release workflows</li><li><strong>語言基線與三十天觀察：</strong><code>profiles/catalog.yaml</code>；<strong>Python 自動升版：</strong><code>python-version-policy.yml</code></li><li><strong>root／template 配對檔案的單一來源與漂移檢查：</strong><code>scripts/sync-paired-files.sh</code></li></ul></aside>
{{< /legacy >}}

{{< basic >}}
- `template/` 是下發內容來源；root 保留公版本身的 GitHub 治理與 dogfood 設定。
- `.csarc/config.yml` 同時是 Copier 的更新紀錄與 repo 唯一的公版設定；語言、分支與選用能力都從這裡讀取，後續擴充也增加設定項目，不另建第二份設定檔。
- 共通基線與 Python、Rust、TypeScript 模組各自驗證；同時選取多個語言時合併執行，不建立組合專屬流程。
- 既有 repo 先用 adopt／update dry-run 預覽；確認後只遷移舊 CSARC 結構，再執行下一版 Copier update 並確認產品內容未被覆寫。

{{< disclosure key="copier-update" title="Copier＋root dogfood＋建立／更新回歸" >}}
[Copier](https://github.com/copier-org/copier) 記錄來源、語言與答案，能把新版公版套回可自行修改的既有 repo；衝突時不修改 repo，由人調整後重跑，再以 PR 審查。GitHub Template 只複製一次，PyScaffold 則會形成第二套更新機制，因此不採用。
{{< /disclosure >}}

{{< detail key="template-release-scope" title="單一來源、版本基線與 root-only 邊界" >}}
`.csarc/config.yml` 保留 Copier 必要的模板來源與版本，並保存這個 repo 選用的公版能力；設定變更透過 `csarc update --data` 寫回，避免手動修改後與 Copier 不同步。未來的繼承公版應在同一份 YAML 增加自己的設定，不複製 CSARC 已有欄位。

`scripts/sync-paired-files.sh` 讓 root 成為成對檔案的單一來源，`--check` 驗證副本內容與權限。`profiles/catalog.yaml` 保存語言基線與驗收證據；Python 與 Node 基線各自觀察三十天後才前進。

`scripts/verify-template.sh` 只在公版 repo 實跑建立／導入／更新 fixture，不會下發到 consuming repository；生成 repo 使用較小的 `scripts/verify`。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="docs-site" track="docs-site" eyebrow="步驟 10" title="單檔永遠可交付" subtitle="Hugo 管內容結構，既有 renderer 打包成可離線轉寄的 HTML。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>單檔永遠可交付，<span class="accent">平台能力只做加成</span></h2>
        <p class="subtitle"><strong>已確認選型。</strong><code>docs/index.html</code> 必須可下載、轉寄並用 <code>file://</code> 離線開啟；Pages、外部託管與 CDN 都不是 portable baseline。</p>
      </header>
      <p class="context-line"><strong>問題與目的｜</strong>保留特殊簡報設計與單檔交付，同時避免內容、樣式、互動、選型來源與逐字測試繼續綁在同一個人工維護檔案。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open><summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">不把交付限制誤當維護方式</span></summary><ul><li><strong>直接手改單檔：</strong>可以離線，但來源、呈現與測試高度耦合</li><li><strong>runtime 多檔載入：</strong>轉寄容易漏檔，<code>file://</code> 行為也受瀏覽器限制</li><li><strong>立刻導入文件平台：</strong>目前沒有多頁搜尋、翻譯或跨 repo catalog 的實證需求</li><li><strong>自動保存完整聊天：</strong>會混入未確認假設、敏感脈絡與噪音</li></ul></details>
        <details class="decision-step decision-fold recommended" open><summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">可維護來源產生可離線單檔</span></summary><details class="package-disclosure"><summary><span><span class="tech-name">可維護來源 → self-contained HTML</span></span></summary><div class="package-health"><p><strong>交付契約：</strong>CSS、JavaScript、font、SVG 與圖片全部內嵌；外部連結可保留，但離線時不影響內容與操作。</p><p><strong>來源契約：</strong><code>docs/adr/</code> 保存 canonical Architecture Decision Records（ADR）；renderer、基礎設計與驗證由公版維護，專案內容與允許的 theme overrides 由 consuming repo 維護。</p><p><strong>互動收納：</strong>agent 只把使用者已確認的 durable constraint 摘要進 Issue，再經 PR 寫入 ADR；不保存完整逐字稿。</p></div></details><p><strong>所有環境：</strong>產生並驗證 committed bundle。<br><strong>Actions allowed：</strong>再增加重建比對與 artifact。<br><strong>核准 host 與寫入權限 allowed：</strong>再增加 preview／publish／access control。<br><strong>blocked／unknown：</strong>回退單檔交付，不宣稱已部署。</p></details>
      </div>
      <aside class="config-guidance"><strong>決策與落地</strong><ul><li><strong>Canonical ADR：</strong><code>docs/adr/portable-decision-site.md</code></li><li><strong>可維護來源：</strong><code>site/</code> 分開內容、樣式、互動與原始圖片；renderer 產生 <code>docs/index.html</code> 並拒絕外部 runtime asset</li><li><strong>生成專案：</strong>公版更新 <code>site/</code> 與 renderer，專案保有 <code>docs/site-content.js</code> 與 <code>docs/site-theme.css</code></li><li><strong>網站存取：</strong><code>noindex</code>／<code>robots.txt</code> 只能降低誤分享，不是登入保護；需要限制讀者時，優先評估 Cloudflare Pages＋Access，host、身分提供者、資料政策與組織 owner 另案核准</li><li><strong>追蹤：</strong><a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/79" target="_blank" rel="noreferrer">存取 #79</a>／<a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/178" target="_blank" rel="noreferrer">網站 #178</a></li></ul></aside>
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

{{< slide key="rollout" track="rollout" eyebrow="步驟 11" title="分階段導入，每一步都能停" subtitle="成熟度看實際證據，不以日期或檔案存在假裝完成。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>分階段導入，<span class="accent">每一步都能驗證，也能停下來</span></h2>
        <p class="subtitle"><strong>三層導入｜</strong>基本能力現在就隨模板產生；未來與可選能力先寫清楚觸發門檻，不用空檔案假裝完成。</p>
      </header>
      <p class="context-line"><strong>問題與目的｜</strong>一次導入模板、CI、部署、監控與 AI，團隊很難判斷哪裡出錯；分期後每一步都有完成條件。</p>
      <div class="decision-strip">
        <details class="decision-step decision-fold" open><summary><span class="step-label">其他常見做法</span><span class="decision-fold-title">不按聲量或日期一次把功能全打開</span></summary><ul><li><strong>一次切換：</strong>錯誤會同時擴散到所有專案</li><li><strong>固定日期解鎖：</strong>時間到了不代表使用條件已成熟</li><li><strong>所有語言同時上：</strong>未驗證的 profile 只是空承諾</li></ul></details>
        <details class="decision-step decision-fold recommended" open><summary><span class="step-label">我們的選擇</span><span class="decision-fold-title">三層不是日期，而是導入條件</span></summary><p><strong>基本導入：</strong>共通基線與 Python、Rust、TypeScript 語言模組，以及 Issue／spec、PR／CI、本機驗證、OSV、依賴政策與 repo 內部網站已有可執行實作。Free 會先查能力並套可用設定；private repo 不宣稱有 Ruleset 強制保護。<br><strong>已完成線上驗證：</strong>release handoff、可追溯成品、Release attestation 消費端驗證，以及第一個真實 CI-only 下游 repo 的導入與 Copier 更新。<br><strong>語言模組已驗收：</strong>Python、Rust 與 TypeScript 都會實際建立、導入既有 repo、更新、測試、建置與封裝，因此列為 beta。<br><strong>未來／可選：</strong>中央 catalog／治理平台、多 repo、Go、網站託管／登入、Hugo、部署、監控、RAG、自主 Agent。</p></details>
      </div>
      <aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>哪些 profile 已可用或仍在規劃：</strong><code>profiles/catalog.yaml</code></li><li><strong>先查方案再套可用設定：</strong><code>scripts/apply-repository-settings.sh</code>；Ruleset／App 條件備妥後再啟用</li><li><strong>建立與更新路徑是否都能通過：</strong><code>scripts/verify-template.sh</code></li></ul></aside>
{{< /legacy >}}

{{< basic >}}
| 層級 | 目前狀態 |
| --- | --- |
| 基本能力 | 共通基線與 Python、Rust、TypeScript 語言模組，以及 Issue／spec、PR／CI、本機驗證、OSV、依賴政策與 repo 網站已有可執行檔案 |
| 已完成線上驗證 | release handoff、可追溯成品、attestation 消費端驗證、第一個 CI-only 下游導入與更新 |
| 語言模組已驗收 | Python、Rust、TypeScript 都通過建立、既有 repo 導入、更新、鎖檔、測試、建置與封裝 |
| 未來／選配 | 中央 catalog／治理平台、Go、託管登入、部署、監控、RAG、自主 Agent |

{{< detail key="rollout-evidence" title="為什麼不一次全部打開" >}}
一次切換會讓錯誤同時擴散，固定日期也不代表使用條件成熟。一個真實 consuming repo 證明共用導入、更新與線上 CI 邊界；各語言再用可重現的建立、既有 repo 導入、更新與原生工具鏈測試取得 beta，不另外建立重複的專用試行 repo。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="bridge" audience="maintainer" eyebrow="2026/05 內部分享簡報" title="回顧當時原則，對照目前實作" subtitle="回顧 2026 年 5 月內部分享的 SDLC 構想，標示目前保留、調整或延後的做法。" class="legacy-slide bridge-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>2026/05 內部分享簡報｜<span class="accent">SDLC 盤點</span></h2>
        <p class="subtitle">回顧 2026 年 5 月內部分享的構想：保留方法，修正實作與導入層級；點選每列可看三句判斷。</p>
      </header>
      <table class="bridge-table" aria-label="五月版簡報與目前設計的逐頁對照">
        <colgroup><col class="page-col"><col class="topic-col"><col class="status-col"><col class="decision-col"></colgroup>
        <thead><tr><th>頁次</th><th>五月版主題</th><th>結論</th><th>目前決定（點選）</th></tr></thead>
        <tbody>
          <tr><td>p.3</td><td>SDLC 核心階段</td><td><span class="bridge-status keep">保留</span></td><td><details class="bridge-detail drop-down"><summary>把計畫到監控集中在 GitHub</summary><div class="bridge-popover"><p><strong>五月版｜</strong>計畫、開發、測試、部署、監控的核心順序保留。</p><p><strong>本次判斷｜</strong>工作單、模板、合併申請、自動檢查與交付設定都放在 GitHub，方便持續維護。</p><p><strong>落地方式｜</strong>不是每個專案都要部署與監控，但都先遵守工作規劃、變更審查與驗證規則。</p></div></details></td></tr>
          <tr><td>p.4</td><td>Jira Ticket</td><td><span class="bridge-status adjust">調整</span></td><td><details class="bridge-detail drop-down"><summary>每次改動先有最小 GitHub Issue</summary><div class="bridge-popover"><p><strong>五月版｜</strong>原本用 Jira 的 Epic → Story → Task 分工；本次只保留必要的 GitHub Issue、里程碑與 spec。</p><p><strong>本次判斷｜</strong>一次性工作選一種類型、寫問題與完成條件；複雜需求先開規劃 Issue，再由核准 spec 建立實作 Issue。新增範圍另開 Issue。</p><p><strong>落地方式｜</strong><code>work-item.yml</code> 有類型、問題與完成條件兩個必填欄位，另加一個選填補充；<code>issue-triage.yml</code> 指派開單者；PR workflow 核對標籤、分支與同號未結案 Issue。</p></div></details></td></tr>
          <tr><td>p.5</td><td>版本控制</td><td><span class="bridge-status adjust">調整</span></td><td><details class="bridge-detail drop-down"><summary>delivery branch 是 CI 整合邊界，不假裝成實體環境</summary><div class="bridge-popover"><p><strong>五月版｜</strong>保留平行分支，但不要求每案具備實體 DEV 環境。</p><p><strong>本次判斷｜</strong><code>main</code> 是唯一永久 branch；並行里程碑各用短命 <code>dev/m*</code>，一般孤立工作直接回 main，獨立 canary 才用暫時 <code>dev/i*</code>。</p><p><strong>落地方式｜</strong>fast CI 驗證每次 Issue 整合，full CI＋可選 canary 驗證 promotion；各里程碑到 final promotion 才用一張 reviewed sync PR 納入最新 main，不 fan out 或 rewrite 歷史。</p></div></details></td></tr>
          <tr><td>p.6</td><td>PR 與審查</td><td><span class="bridge-status adjust">強化</span></td><td><details class="bridge-detail drop-down"><summary>Issue、編號分支與 PR 形成固定鏈</summary><div class="bridge-popover"><p><strong>五月版｜</strong>PR 是保護分支的唯一入口，方向保留；三層審查改成依風險增加審查者。</p><p><strong>本次判斷｜</strong>一般 PR 要有同編號 Issue、CI 與一位同事；高風險架構變更另附決策紀錄。</p><p><strong>落地方式｜</strong>分支固定 <code>type/123-short-slug</code>，PR 內文固定 <code>Closes #123</code>；Free private 目前由人工指定 reviewer，自動輪派 Action 尚未恢復；GitHub Team 以上才支援 team request 與強制核准。</p></div></details></td></tr>
          <tr><td>p.7</td><td>CI 自動化管線</td><td><span class="bridge-status keep">保留</span></td><td><details class="bridge-detail drop-down"><summary>本機與 CI 共用入口，依風險分層執行</summary><div class="bridge-popover"><p><strong>五月版｜</strong>自動觸發、測試、格式與靜態錯誤檢查全部保留。</p><p><strong>本次判斷｜</strong>一般 Issue PR 跑 fast；promotion、hotfix、merge queue 與未知高風險路徑跑 full；OSV、Zizmor 與 remote governance 另依 scope／schedule 執行。</p><p><strong>落地方式｜</strong>固定 <code>verify</code> aggregate 避免 skipped workflow 留下 Pending；delivery sync 併入 <code>title</code> policy，候選 full run 不取消，普通 PR 新 commit 則取消舊 run。Ruleset 可用時強制 <code>title</code>、<code>verify</code> 與 <code>promotion</code>。</p></div></details></td></tr>
          <tr><td>p.8</td><td>CD 專案管理</td><td><span class="bridge-status adjust">調整</span></td><td><details class="bridge-detail drop-down"><summary>promotion 才形成發版邊界，不為每張 Issue 狂發版</summary><div class="bridge-popover"><p><strong>五月版｜</strong>原本預設 DEV → STAGING → Canary → PROD；本次不要求每個專案照搬四層。</p><p><strong>本次判斷｜</strong>里程碑原則上在完成時 promotion 一次；只有後續驗收依賴同一里程碑的 immutable Release，才用受約束的 checkpoint promotion。Standalone 與 bot PR 直接進 main 後保留 release intent，獨立 canary 與 hotfix 才立即形成 release boundary。Canary 必須有環境與命令，否則只誠實保留 artifact-only。</p><p><strong>落地方式｜</strong>release-source 核對 promotion 的 full verify、canary state 與 tree identity；成品 workflow 只接受 source run ID，產生 digest、SBOM、attestation，不接受任意 tag push，也不重跑完整 runtime CI。</p></div></details></td></tr>
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
| Jira Ticket | 改為最小 GitHub Issue；明確 story 才加里程碑／spec |
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
        <p><strong>依賴安全選型：</strong>Dependabot 提出更新、OSV-Scanner 檢查已知漏洞、Syft 建立 SBOM；三者各自負責，不互相替代。</p>
        <p><strong>尚未啟用：</strong>Go、Scorecard、Harden-Runner、網站託管／登入（<a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/79" target="_blank" rel="noreferrer">#79</a>）、Hugo、RAG、通用部署與監控；repo 內部網站與生成內容模板已可用。</p>
      </aside>
      <p class="ecosystem-reference reference">Ref. Official project repositories linked above; logo assets from each project's brand kit.</p>
{{< /legacy >}}

{{< basic >}}
| 工具 | 解決什麼 | 現在的決定 |
| --- | --- | --- |
| ![Copier logo](assets/copier.svg) [Copier](https://github.com/copier-org/copier) | 可更新模板 | 基本導入；差異走 PR |
| ![zizmor logo](assets/zizmor.png) [zizmor](https://github.com/zizmorcore/zizmor) | GitHub Actions 安全 | 基本導入；workflow 變更與週期排程執行 |
| Dependabot、OSV、Syft | 依賴更新、漏洞與 SBOM | Dependabot 與 OSV 已啟用；SBOM 契約以真正發版成品驗證 |
| ![GitHub Community Projects logo](assets/github-community-projects.png) [Safe Settings](https://github.com/github-community-projects/safe-settings) | 多 repo 設定治理 | 規模與漂移門檻成立後才評估 |
| ![Renovate logo](assets/renovate.png) [Renovate](https://github.com/renovatebot/renovate) | 更彈性的更新 preset | 現階段不取代 Dependabot |
| ![GitHub Actions logo](assets/github-actions.svg) ![PyScaffold logo](assets/pyscaffold.svg) Starter Workflows、PyScaffold | 官方 workflow 與 Python 結構範例 | 只作內容檢查表，不照抄政策 |
| ![GitHub logo](assets/github.png) [GitHub Spec Kit](https://github.com/github/spec-kit) | AI 規格拆解 | 現階段保留 spec → Issue |
| ![Backstage logo](assets/backstage.svg) [Backstage](https://backstage.io/docs/features/software-catalog/) | Catalog、owner 與文件入口 | 跨團隊查找成本達門檻才 PoC |

{{< detail key="ecosystem-deferred" title="尚未啟用的能力" >}}
Go、Scorecard、Harden-Runner、網站託管與登入、RAG、通用部署與監控都等可測量需求再做。公版不建立空設定或 placeholder 來假裝支援。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="similar-tools" parity="supplemental" eyebrow="工具附錄｜相似工具" title="相似工具｜整體競品與局部參考" subtitle="標準模式先看整體目的接近的套件；維運模式可再按旅程檢查各項具體做法。" class="similar-tools-slide" legacy="true" >}}
{{< similar-tools >}}
{{< /slide >}}

{{< slide key="testing" audience="maintainer" parity="supplemental" eyebrow="維運附錄｜CI/CD 設定" title="CI/CD 設定｜依 Journey 檢查" subtitle="分開列出一般 repo 與 repo-template 在 Issue PR（工作分支 → dev）、發版 PR（dev → main）各自需要的測試與自動化。" class="similar-tools-slide testing-slide" legacy="true" >}}
{{< testing >}}
{{< /slide >}}

{{< slide key="access-control" audience="archive" eyebrow="存取決策" title="託管方案未定前的臨時防護" subtitle="目前只有降低誤分享的措施，沒有把提示語宣稱成安全控制。" class="legacy-slide review-notes-slide" legacy="true" >}}
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

{{< slide key="principles" audience="archive" eyebrow="關鍵決策" title="規則、理由與刻意不做" subtitle="這些是目前可由檔案與測試證明的決定。" class="legacy-slide review-notes-slide" legacy="true" >}}
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
          <tr><td>語言與程式品質</td><td>Python、Rust、TypeScript 為獨立模組，可任意複選；Python 採 uv、Ruff、ty、pytest，Rust 採 Rust 1.98、rustfmt、Clippy 與 Cargo，TypeScript 採 Node 24、pnpm、Biome、Vitest。</td></tr>
          <tr><td>CI、版本與交付</td><td>本機與 CI 共用 <code>scripts/verify</code>，PR policy 回歸案例證明錯誤 route 會被拒絕；日常 fast、promotion full，release-please 只在已驗證的批次邊界維護單一 SemVer。</td></tr>
          <tr><td>依賴與供應鏈</td><td>三天等待觀察未知惡意新版；OSV 查已公開漏洞；hash 驗內容一致；SBOM 列出成品套件；resolver 另證明版本上下界可安裝，五者互不取代。</td></tr>
          <tr><td>AI、文件與未來能力</td><td><code>AGENTS.md</code> 是 AI 規範，README 與 repo 網站服務人類；Hugo／託管登入、部署、監控、RAG、Go 都要有 owner、使用情境與驗證後才導入。</td></tr>
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
| 語言品質 | Python 用 src layout、uv、Ruff、ty、pytest；Rust 用 rustfmt、Clippy、Cargo；TypeScript 用 Node 24、pnpm 11、Biome、Vitest |
| CI 與版本 | 本機／CI 共用入口；日常 fast、promotion full、單一 SemVer |
| 供應鏈 | 等待、OSV、hash、SBOM 與 resolver 各解決不同問題 |
| AI 與文件 | `AGENTS.md` 是工作契約；README 與網站服務人類 |
| 驗證資源 | 只用本機暫存專案或本 repo，不為測試另開 GitHub repository |

{{< detail key="principles-transcript" title="決策如何留下來" >}}
Agent 不保存原始聊天。只有使用者已確認的 durable architecture、security、compatibility 或 platform constraint，才先摘要進 Issue，再透過有範圍的 PR 更新 `docs/adr/` 或 `docs/decisions/`。細節以可執行設定為準，條件改變時由 Issue／PR 同步修正。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="benchmark" audience="archive" eyebrow="外部基準與實測" title="有骨架，還不是完整平台" subtitle="新 repo、Copier 更新、OSV、Release 與第一個 CI-only pilot 已有證據；其餘邊界仍明列。" class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">決策附錄</span>
        <h2>外部基準與實測｜<span class="accent">有骨架，還不是完整平台</span></h2>
        <p class="subtitle">結論：已真正解決新 repo 建立、Copier 更新與本機／合成驗證；OSV、Release 與第一個 CI-only consuming repo 都有線上成功證據。治理仍受 GitHub 方案限制，語言模組則以可重現的生命週期與原生工具驗收。</p>
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
          <tr><td>真實 consuming repo 與採用證據</td><td><span class="tier-chip best">共用生命週期已證明</span></td><td><code>ai-guardrail</code> 已透過 Issue、兩支 PR 完成 v0.2.4 導入、產品客製化保留、v0.3.1 Copier update 與兩次完整線上檢查；Python、Rust 與 TypeScript 另有各自可執行的 beta 驗收證據。→ <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/100" target="_blank" rel="noreferrer">#100</a>／<a href="pilot-adoption.md">證據</a></td></tr>
        </tbody>
      </table>
      <p class="review-note-footer"><strong>簡潔度判斷：</strong>Copier＋GitHub Actions＋標準工具的方向夠簡潔；真實 CI-only pilot 已補上共用生命週期的線上證據。root-only <code>Live integration smoke</code> 持續驗證 OSV、Release Please、release handoff 與 governance drift；語言模組則由各自的可重現測試維持 beta。</p>
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
| 真實 consuming repo | 共用生命週期已證明 | `ai-guardrail` 已完成 v0.2.4 導入與 v0.3.1 update；語言模組另有可執行 beta 證據 |

{{< detail key="benchmark-gap" title="現階段缺口" >}}
沒有跨 repo catalog、全面託管治理或通用部署平台。Root-only `Live integration smoke` 持續驗證 OSV、Release Please、release handoff 與 governance drift；真實產品 repo 繼續累積營運證據，但不作為一次性的語言測試 fixture。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="fleet-inventory" audience="archive" eyebrow="Fleet 治理" title="採用盤點以真實 repo 為準" subtitle="2026-08-24：組織共 6 個 private repo，目前只有 1 個 consuming repo。" class="legacy-slide review-notes-slide" legacy="true" >}}
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

{{< slide key="fleet-governance-thresholds" audience="archive" eyebrow="Fleet 門檻" title="先量問題，再加平台" subtitle="Catalog 與 policy enforcement 解決不同問題，分開計數、分開選工具。" class="legacy-slide review-notes-slide" legacy="true" >}}
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

{{< slide key="spec-format" audience="archive" eyebrow="Spec 格式" title="預設 Issue，明確 Story 才建里程碑" subtitle="保留一種輕量格式，不在需求尚未出現時同時維護兩套系統。" class="legacy-slide review-notes-slide" legacy="true" >}}
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
          <p><strong>現行：</strong><code>docs/specs/*.md</code> 用 frontmatter 記錄狀態；預設以 <code>csarc-spec-id</code> marker 同步 Task Issue，明列 <code>tracking: story</code> 則同步 Feature parent，兩者都可重跑且不自動拆工作。里程碑另作有 due date 的 delivery／release bucket。</p>
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
| 現行 `docs/specs/*.md` | Front matter 記錄 ID、優先度、狀態與選用 tracking；marker 可重跑同步 Issue 或里程碑 |
| GitHub Spec Kit | `/specify → /plan → /tasks → /implement`，需額外 CLI 與支援的 AI 工具，沒有內建一份 spec 對一張 Issue 的同步 |

{{< detail key="spec-format-cost" title="目前不遷移的理由與重新評估條件" >}}
改採 Spec Kit 需重寫 `scripts/spec_to_issue.py`、轉換既有 specs、更新驗證斷言，並另行設計等價 Issue sync；雙格式則增加認知與維護負擔。當核准規格經常需要由 AI 穩定拆成多張子工作，且團隊願意維護額外 CLI／Agent 流程時再評估。決策追蹤於 Issue #77。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}
