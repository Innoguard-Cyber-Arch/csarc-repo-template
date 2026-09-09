+++
title = "CSARC Repo Template｜AI 輔助 SDLC 團隊公版"

[controls]
menu = "投影片目錄"
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

{{< slide key="index" track="index" eyebrow="首頁" title="CSARC Repo Template" subtitle="Cyber-Arch 的可更新 repo 公版：建立新案、導入既有案、接收政策更新，都先驗證再由 PR 合併。" class="legacy-slide capability-slide" legacy="true" >}}
{{< legacy >}}
      <header class="package-hero">
        <p class="package-kicker">Innoguard-Cyber-Arch / repository infrastructure</p>
        <h1><code>csarc-repo-template</code></h1>
        <p class="subtitle lead-question">這套公版如何讓人和 AI 的每次修改，都經過定義、驗證、審查並留下證據？</p>
        <p class="subtitle"><!-- csarc-readme-preamble-tagline:start -->Cyber-Arch 的可更新 repo 公版：建立新案、導入既有案、接收政策更新，都先驗證再由 PR 合併。可以只使用共通流程，或獨立選擇 Python、Rust、TypeScript。<!-- csarc-readme-preamble-tagline:end --></p>
        <p class="subtitle flow-line"><strong>結果：</strong>不論是人或 AI 提出的修改，都要先說清楚要做什麼、通過檢查、再經人工審查，才會真的合併，並留下當時的證據。</p>
        <p class="subtitle">標準模式給使用 AI／vibe coding 的一般開發者，不要求具備工程或 CI/CD 維運背景；維運模式才補充設定檔、程式與技術理由。快速導入指令請見 <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template#readme" target="_blank" rel="noreferrer">repo README</a>。</p>
        <p class="subtitle"><strong>公開狀態：</strong>本 repository 與 GitHub Pages repo-site 目前均為公開可讀；<code>noindex</code>／<code>robots.txt</code> 只降低索引，不限制讀取或分享。後續 hosting／access-control 決策留在 <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/425" target="_blank" rel="noreferrer">Issue #425</a>。</p>
        <div class="package-badges" aria-label="套件狀態">
          <span class="package-badge beta">beta</span>
          <span class="package-badge python">三個語言模組</span>
          <span class="package-badge">公版可持續更新</span>
          <span class="package-badge muted">v0.15.1</span><!-- x-release-please-version -->
          <span class="package-badge muted">網站排版模板 v[[site_template_version]]</span>
          <span class="package-badge muted">渲染引擎 v[[site_engine_version]]</span>
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
          <p class="scope-row"><strong>驗證與合併</strong><span>本機先跑相關檢查，GitHub 只核對這份證明，再交由團隊審查</span></p>
          <p class="scope-row"><strong>依賴與交付證據</strong><span>固定使用的套件版本、先觀察一般新版、檢查已知漏洞，並記錄成品包含哪些套件</span></p>
          <p class="scope-row"><strong>可持續同步</strong><span>公版更新成為可審查差異，不會直接覆蓋產品程式</span></p>
        </section>
        <section class="start-paths" aria-label="三種導入方式">
          <h3>依你現在的 repo 狀態開始</h3>
          <article class="start-path primary"><h3>建立新 repo</h3><p>選好種類與分支做法才產生檔案；完成前不會建立或推送任何 GitHub 內容。</p><button class="setup-trigger" type="button" data-setup="new" aria-expanded="false">立即開始</button></article>
          <article class="start-path"><h3>導入既有 repo</h3><p>先在獨立分支預覽差異，保留原有產品內容，再逐項處理衝突。</p><button class="setup-trigger" type="button" data-setup="existing" aria-expanded="false">導入指令</button></article>
          <article class="start-path"><h3>更新已使用公版的 repo</h3><p>先產生可審查的差異（dry-run），確認後才合併，不會直接覆蓋 main。</p><button class="setup-trigger" type="button" data-setup="update" aria-expanded="false">更新指令</button></article>
        </section>
      </div>
      <div class="prerequisite-line product-prerequisites">
        <p><strong>開始前必裝</strong>Git、GitHub CLI、uv；完整清單（含 Rust／TypeScript 選用工具）請切換「維運」模式查看。</p>
        <button class="setup-trigger" type="button" data-setup="mac" aria-expanded="false">macOS 安裝</button>
        <button class="setup-trigger" type="button" data-setup="windows" aria-expanded="false">Windows 安裝</button>
      </div>
      <p class="subtitle bridge-line"><strong>下一步：</strong>「安裝說明」頁提供一句貼給 agent 的完整指令，先預覽、才動手；維運模式另有狀態判斷的精確條件。</p>
{{< /legacy >}}

{{< basic >}}
Cyber-Arch 的可更新 repo 公版：建立新案、導入既有案、接收政策更新，都先驗證再由 PR 合併。標準模式給使用 AI／vibe coding 的一般開發者，不要求具備工程或 CI/CD 維運背景；設定檔、程式與 GitHub Actions 留在維運模式。本頁內容與 [repo README](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template#readme) 對齊、雙語同步維護。本 repository 與 GitHub Pages repo-site 目前均為公開可讀；`noindex`／`robots.txt` 不限制讀取或分享。

<p class="template-version"><strong>公版版本：</strong>v0.15.1<!-- x-release-please-version --></p>

| 項目 | 目前狀態 |
| --- | --- |
| 支援語言 | Python、Rust、TypeScript（可獨立複選；都不選時只使用共通流程） |
| repo-site 排版模板版本 | [[site_template_version]] |
| repo-site 渲染引擎版本 | [[site_engine_version]] |

**目前狀態：**Milestone 13 正在擴充 repo-site 與導入體驗；只有已審查且位於 `.github/workflows/` 的流程會執行，其他流程仍封存，啟用狀態以「CI/CD 設定」附錄為準。

| 可以直接選擇 | 目前提供的正式能力 |
| --- | --- |
| 程式語言 | Python、Rust、TypeScript 可獨立複選；都不選時只使用共通工作流程 |
| 分支做法 | 每個交付批次有自己的開發分支、所有修改直接進 `main`，或先集中到 `dev` |
| 公版設定 | 建立／導入時把選項寫入 `.csarc/config.yml`；之後由公版更新，不必到不同檔案重複設定 |
| 共用能力 | 工作單（Issue）與變更提案（PR）表單、AI 工作規範、自動驗證、依賴安全、版本記錄與公版更新 |

{{< disclosure key="capability-boundary" title="導入方法與目前範圍" >}}
- **新 repo：** 選專案種類與分支做法；大型成果才拆成主要工作與可獨立驗收的子工作。
- **既有 repo：** 公版先偵測現有語言並產生 `.csarc/config.yml`，再預覽導入差異、保留產品內容。
- **已使用公版：** 透過 `csarc update` 調整選項或升級；公版同步設定與必要檔案，只審查這次差異。
- **開始前必裝：** Git、GitHub CLI、uv；選 Rust 另需 rustup，選 TypeScript 另需 Node 24+ 與 pnpm 11。純本機驗證不需要 token。

公版只承諾已經實作並測試的能力。Go、通用部署、監控、AI 知識檢索與網站託管仍是未來或選配項目。
{{< /disclosure >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="install" parity="supplemental" eyebrow="安裝說明" title="一句話貼給 agent，自動判斷目前該做什麼" subtitle="`csarc status` 讀 `.csarc/config.yml`、Copier 版本與 policies/ 現況，決定結果、不靠 agent 自由判斷。" class="dense" legacy="false" >}}
不管是新 repo、舊 repo 還是已經導入過公版的 repo，判斷方式都一樣：不用自己記指令，把下面這段話直接貼給你的 coding agent（Claude Code、Copilot 等），它會自己執行、自己判斷。

{{< standard key="install-mode-standard" title="貼給 agent 的一句話" >}}
<div class="step-flow"><article class="step-flow-item"><span class="step-flow-number">1</span><h3>貼上</h3><p>把下面這段完整指令貼給你的 coding agent，不用自己記指令。</p></article><article class="step-flow-item"><span class="step-flow-number">2</span><h3>CLI 判斷</h3><p>Agent 執行 <code>csarc status</code>，由 CLI（不是 agent 自由判斷）自動分類這是新建、既有導入、有更新，還是只是政策變動。</p></article><article class="step-flow-item"><span class="step-flow-number">3</span><h3>先預覽</h3><p>不管哪一種結果，agent 都會先讓你看過計畫，確認後才真的動手。</p></article></div>

結果會是以下其中一種：**建立**新專案、**導入**既有專案、套用可用**更新**、**已是最新**不用做事，或**只有政策設定**要補套用；不論哪一種，agent 都會先讓你確認才動手。

<p class="install-promise"><strong>這一步的承諾：</strong>這一步只檢查目前狀態並提出計畫；在你確認前，不修改檔案、不變更 GitHub 設定，也不會建立 PR。</p>

<div class="command-block"><div class="command-block-head"><span class="command-block-label">貼給 agent 的完整指令</span><button class="copy-command" type="button">複製指令</button></div><pre class="command-block-text">請使用 uv。先從 https://github.com/Innoguard-Cyber-Arch/csarc-repo-template 查出目前最新的正式 GitHub Release（例如執行 `gh release view --repo Innoguard-Cyber-Arch/csarc-repo-template --json tagName,targetCommitish`，或直接看該 repository 的 Releases 頁面），記下這個 release 的 tag 與完整 commit SHA——一律使用這個已驗證的 release，不要用 main 或未經確認的分支。用這個 SHA 執行官方 csarc CLI 的 `status` 子指令，判斷目前 workspace／既有 Git repository 屬於哪一種安裝狀態；uv 應按次管理隔離的 Python 3.14，不要求全域 Python。先執行 `csarc status --json`，不要自行判斷或假設目前狀態。依回傳的 state 與 next_command：create 或 adopt 或 update 時，改用對應的 init／adopt／update dry-run prompt 並等待確認；current 時回報不需動作；policy-only-update 時只執行 `scripts/apply-repository-settings.sh plan`、摘要差異並等待確認，確認後才 `apply`，不要重新走完整 adopt 或 update。全程不要修改全域環境、push 或開 PR。</pre></div>

判斷邏輯全部在 CLI 裡，換一個 agent 執行也會得到同樣答案；其他三種情境（新建／既有導入／更新）的完整 prompt 收在 [repo README](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template#readme)。
{{< /standard >}}

{{< ops key="install-mode-ops" title="狀態判斷的精確條件與下一步指令" >}}
不想透過 agent、想自己直接跑指令時：

```bash
csarc status <path> --json
```

指令只讀取本機檔案與（若已導入）GitHub 上的公版版本、repository 設定，不會寫入任何東西，也不會執行 target repo 裡的 helper；同一個狀態重複執行永遠得到同一個結果。

| 狀態（`state`） | 判斷依據 | 下一步 |
| --- | --- | --- |
| `create`（新 repo 建立） | 目標路徑不存在，或存在但是空目錄 | `csarc init <path>`：先 `--dry-run` 預覽，確認後加 `--yes --non-interactive` |
| `adopt`（舊 repo 導入） | 目標已存在內容，但沒有 `.csarc/config.yml` | `csarc adopt <path>`：先寫出 dry-run 計畫，審查後用 `--apply-plan` 套用 |
| `update`（有可用更新） | 已有 `.csarc/config.yml`，其中記錄的 Copier revision 落後目前可用版本 | `csarc update <path> --check` 預覽差異，確認後執行 `csarc update <path>` |
| `current`（已是最新，不用做事） | Copier revision 已是最新，且 `policies/` 與 GitHub 上實際設定一致 | 不需要動作 |
| `policy-only-update`（已是最新，但政策設定變了） | Copier revision 已是最新，但 `policies/`（例如允不允許 workaround）與 GitHub 上實際設定不一致 | `scripts/apply-repository-settings.sh plan` 預覽，確認後 `apply`；**不必**重新走一次完整 adopt／update |

{{< disclosure key="install-policy-only" title="為什麼「已最新版但政策異動」不用重新導入" >}}
政策設定（分支保護、必要檢查、標籤、CODEOWNER 規則）記錄在 `policies/*.json`，由 `scripts/apply-repository-settings.sh` 直接讀取並套用到 GitHub，跟 Copier 範本檔案是兩件事：改政策不需要改到任何範本檔案，Copier revision 也不會變。`csarc status` 使用已驗證 Release 重新產生的完整 helper closure 執行 `check`，不信任或執行 target repo 內的同名腳本；偵測到 revision 相同但政策有落差時，回傳 `policy-only-update` 並直接指向 `plan`／`apply`，不會建議重跑整個 adopt 或 update。

若受信任的 `apply-repository-settings.sh check` 跑不動（例如 Release 未驗證、`gh` 未登入或沒有網路），`csarc status` 不會冒然回報「政策已變」；會退回 `current` 並在 `policy_check.available` 標示 `false`，保留由人工再次確認。
{{< /disclosure >}}

{{< disclosure key="install-agent" title="agent 安裝契約寫在哪" >}}
安裝流程的完整機器可讀契約在 [`docs/agent-install.md`](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/agent-install.md)：agent 一律先執行 `csarc status`，依回傳的 `state` 走上表對應流程，不自行判斷現在是哪一種情境。判斷邏輯全部寫在 CLI 裡（`detect_install_state`），agent 只負責呼叫與依結果行動，同一個 repo 狀態不會因為換一次 agent 執行就得到不同答案。
{{< /disclosure >}}

{{< disclosure key="advanced-install-capabilities" title="搞清楚這個 repo 實際能啟用什麼" >}}
「規則治理」（Step 08）的方案能力表回答的是「這個帳號的 GitHub *方案* 允許什麼」；這是必要條件，但不夠：organization 政策、CODEOWNERS team 是否真的存在、token 權限範圍，都可能在方案本身支援的情況下仍然擋住某項能力。除了上述方案探測，`policies/capability-matrix.json` 列出這個模板依賴的每一項能力、各自的最低需求與已記錄的 workaround；`scripts/check-repo-capabilities` 會即時對照這個 repo 與 token 本身實際具備什麼：

```bash
./scripts/check-repo-capabilities        # 人類可讀報告
./scripts/check-repo-capabilities --json # 機器可讀的能力清單與統計
```

| 能力 | 啟用了什麼 | 最低需求 | 缺少時 |
| --- | --- | --- | --- |
| `repository_admin` | 以下每一項能力的前提 | 目前 token 的 `permissions.admin == true` | 請 owner／admin 執行 `apply`，或申請 Admin 角色 |
| `ruleset_enforcement` | 預設分支的 Ruleset 分支保護 | public repository（任何方案），或 private 且 Pro／Team 以上 | DEGRADED 標記；`policies/rulesets.json` 保留為 desired state |
| `codeowners_enforcement` | CODEOWNERS review 真的能擋下合併 | 需先具備上一項，且 `@org/team` 具寫入權限 | DEGRADED 標記；修正 team，或先用 `scripts/request-reviewer` |
| `actions_pr_approval` | Actions 能自動核准 PR（例如 Dependabot auto-merge） | organization 允許 `can_approve_pull_request_reviews` | DEGRADED 標記；降級為人工核准 |
| `security_and_analysis` | secret scanning、push protection、Dependabot security updates | public repository，或 private 且具備 GitHub Advanced Security | DEGRADED 標記；改用本機 `scripts/scan-secrets` |
| `github_pages` | 將 `docs/index.html` 發布成 hosted 網站 | public repository，或 private 且為 GitHub Enterprise Cloud | DEGRADED 標記；改分享 commit 進 repo 的 HTML 檔案 |
| `repository_settings_inspection` | `check` 模式能比對即時的管理員專屬欄位 | 與 `repository_admin` 相同 | DEGRADED 標記；改在具 admin 身分的可信環境執行 `check` |
| `immutable_releases` | hosted Automatic／Guided 發版的必要條件 | 真人 admin 身分，絕非預設 `GITHUB_TOKEN` | 已知永久限制（#123／#626）；改在本機執行 `scripts/publish-release` |
{{< /disclosure >}}

{{< disclosure key="advanced-install-results" title="怎麼解讀 check-repo-capabilities 的結果" >}}
每一列會回報三態之一：`allowed`（現在就能用）、`blocked`（確實缺少某個條件）、`unknown`（單靠唯讀探測無法證實——例如某個 Actions 設定目前是關的，可能只是還沒開，不代表被 organization 政策擋住）。這是診斷用的 preflight，不是合併關卡：報告產出後一律回傳 `0`，也不會對 GitHub 做任何寫入。「即時設定是否真的符合宣告政策」仍然是 `apply-repository-settings.sh check` 的工作。

`--facts <file>` 可以讀取預先準備好的 facts，不必呼叫 `gh`，因此同一份矩陣可以在沒有即時存取的情況下對照假設的權限組合——`scripts/test-check-repo-capabilities` 就是用這個方式，在完全不連網路的情況下驗證多種權限／方案組合的缺口清單是否正確。
{{< /disclosure >}}

{{< disclosure key="advanced-install-workarounds" title="Workaround 與既有的 DEGRADED 標記" >}}
這份矩陣不是要取代或重新設計 `apply-repository-settings.sh` 既有的 DEGRADED 機制，而是把它寫清楚。凡是 workaround 寫「DEGRADED 標記」的列，用的都是 `apply-repository-settings.sh check`／`plan`／`apply` 對同一個限制本來就會印出的那個 fail-safe；兩邊不會互相矛盾，因為底層偵測（方案、visibility、admin 權限）完全相同。長期決策記錄在 `docs/ci-policy.md` 與[能力導向治理 ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/capability-aware-governance.md)；這一頁與 `policies/capability-matrix.json` 是兩邊共同參照、保持最新的單一來源。
{{< /disclosure >}}
{{< /ops >}}
{{< /slide >}}

{{< slide key="about" track="about" eyebrow="關於" title="CSARC 是一套會持續跟著 repo 維護的治理基線" subtitle="不是產生檔案就結束的模板；建立、導入既有 repo、升級政策都先讓你看過差異，再套用。" class="dense single-column" legacy="false" >}}
{{< standard key="about-mode-standard" title="CSARC 實際上持續在做什麼" >}}
大部分模板做完「產生檔案」就結束了；CSARC 會繼續跟著你的 repo 一起運作，陪你走完一個完整的生命週期：

<div class="capability-map"><div class="capability-node"><h3>1｜導入前先看差異</h3><p>不論建立新 repo 或導入既有 repo，都先在旁邊產生預覽，列出哪些會新增、保留、需要你自己判斷；看過再套用，不會直接覆寫。</p><span class="capability-pointer">見「安裝說明」「模板升級」</span></div><div class="capability-node"><h3>2｜日常修改有規範與驗證</h3><p>每項工作先寫成一張 Issue，說清楚要做什麼、怎樣算完成；改動在自己的分支進行，本機先檢查一輪，GitHub 只核對這份證明，套件與已知漏洞的例行檢查也排定自動執行。</p><span class="capability-pointer">見「工作定義」「驗證／CI」「依賴安全」</span></div><div class="capability-node"><h3>3｜合併後留下證據</h3><p>PR 經人審查通過才合併；需要時建立版本與 Release，記錄成品包含哪些套件，讓「當時到底發生了什麼」隨時可以核對。</p><span class="capability-pointer">見「PR／合併」「版本／交付」</span></div><div class="capability-node"><h3>4｜未來公版更新仍先看差異</h3><p>公版更新的做法跟導入時一樣：先產生可審查的差異，你確認後才套用。這個網站本身也是用同一套原則做出來的，下載 <code>docs/index.html</code> 就能離線打開。</p><span class="capability-pointer">見「模板升級」「repo-site」</span></div></div>

這樣的節奏適合你，如果：已經有 GitHub repository、不能冒險被模板整個蓋過去；想讓 AI coding agent 加入日常開發，但要有清楚的規則邊界；或想讓好幾個專案共用同一套流程。只想快速生出一個空白專案、不需要後續維護，更輕量的模板可能更適合。
{{< /standard >}}

{{< ops key="about-mode-ops" title="治理基線背後的設計理念" >}}
CSARC 不只產生檔案：新專案建立、既有專案導入與後續政策升級，都經過可預覽、可驗證、可追溯的流程，導入的是一套可驗證的工作方式，不只是檔案。

<div class="capability-map"><div class="capability-node"><h3>安全導入既有 repository</h3><p>先在隔離環境建立完整候選並驗證；正式套用前再次確認沒有漂移；衝突或驗證失敗就停止，不修改目標 repo。</p></div><div class="capability-node"><h3>持續升級治理政策</h3><p>分開保存 repo 選擇、公版版本、GitHub 期望政策與平台實際狀態；可修正的差異被指出，平台不支援的能力標示 <code>DEGRADED</code>。</p></div><div class="capability-node"><h3>保留可核對的證據鏈</h3><p>Issue → PR → 驗證 → 交付候選 → 合併 → Release → checksum／SBOM → 稽核軌跡，每段都指回上一段實際發生的版本。</p></div></div>

{{< disclosure key="about-three-layers" title="三層架構：為什麼設定檔寫了，平台不一定真的執行" >}}
CSARC 把「治理」拆成三層，各自可能不同步，因此不能只看其中一層就宣稱某項管制已生效：

1. **公版來源：** `template/`、`policies/`、`profiles/catalog.yaml`——公版團隊維護的共用定義，描述「應該」提供什麼。
2. **repo-local 契約：** 生成或導入後留在這個 repo 裡的 `.csarc/config.yml`、`policies/*.json`、`AGENTS.md`——這個 repo 從公版選了什麼、記錄了什麼期望。
3. **GitHub 上實際生效的狀態：** 分支保護、Ruleset、Actions 權限、GitHub 方案本身的限制——平台當下真正在強制什麼。

公版更新只影響第 1 層；套用到 repo 只影響第 2 層；第 2 層寫的政策要真的生效，還要看第 3 層那個 GitHub 方案與權限支不支援。`apply-repository-settings.sh` 的 `plan`／`apply`／`check` 做的正是核對第 2 層與第 3 層是否一致：一致就套用並在 `check` 驗證；平台真的不支援，就標示 `DEGRADED` 並交回人工處理，不會假裝已經強制。
{{< /disclosure >}}

{{< disclosure key="about-design-philosophy" title="為什麼這樣設計：人與 agent 分工、repo-local、適合誰" >}}
### 為人與 coding agent 共同設計

CSARC 提供 agent-friendly 的操作入口，但不讓 agent 自由猜測 repository 狀態或治理政策。Agent 負責協助操作與說明；真正的判斷放在 deterministic、可測試、可在本機重跑的 CLI、scripts 與 policies 裡。需求取捨、不可逆操作、外部影響與合併授權仍由人負責。

### Repo-local，而不是另一座平台

CSARC 不要求先維護 developer portal、長效 PAT、額外 GitHub App 或專用 hosted service。政策、驗證、文件與決策證據都留在 repository 內，可以接受 PR 審查、版本控制與離線閱讀。它不取代 Backstage、Minder 或各語言原生工具，而是把 Copier、GitHub、uv、Cargo、pnpm、OSV、Syft 與 Release Please 等能力組成一套有明確 ownership 和失敗邊界的 repository lifecycle。

### 適合哪些團隊

適合：已有 GitHub repository、不能冒險由模板直接覆寫；開始讓 coding agent 參與日常開發；希望多個 repository 共用治理基線；重視供應鏈、變更證據與可稽核性；尚不需要或沒有資源維護中央平台。只想快速產生空白專案、不需要後續治理，較輕量的專案模板可能更適合。
{{< /disclosure >}}

{{< disclosure key="about-beliefs" title="我們選擇相信什麼" >}}
- 寫入前先產生並驗證候選。
- 產品內容永遠有明確 owner。
- 無法證明的能力不宣稱成功。
- 平台能力不足時誠實降級。
- 自動化負責重複判斷，人負責重要決策。
- 文件是導航，spec、ADR、GitHub history 與 tests 才共同構成 durable project memory。
{{< /disclosure >}}
{{< /ops >}}
{{< /slide >}}

{{< slide key="flow" track="flow" eyebrow="CI/CD 流程" title="模板會帶你走完每次變更" subtitle="依表單填寫、提交 PR、查看結果；模板負責準備正確設定並指出要修正的地方。" class="legacy-slide pipeline-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>模板會把每次變更<span class="accent">帶到正確的位置</span></h2>
        <p class="subtitle"><strong>CI/CD 在這裡的意思是：</strong>修改送出後，由另一個乾淨環境重新檢查，再決定能否合併或發布；不代表自動部署到正式環境。</p>
        <p class="subtitle">舉例：團隊要替產品新增「登入逾時提醒」——以下五步都用這個例子說明。</p>
      </header>
      <div class="pipeline-map">
        <div class="pipeline-track" aria-label="日常開發與交付主流程">
          <article class="pipeline-stage">
            <span class="pipeline-phase">第一步｜先說清楚</span>
            <h3>建立工作</h3>
            <p><strong>人：</strong>寫一張 Issue（工作單）——「新增登入逾時提醒」，完成條件是逾時前顯示提醒、且有測試證明。<strong>模板：</strong>表單提示必填欄位。<strong>結果：</strong>一張範圍清楚、可獨立驗收的工作。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">第二步｜開始修改</span>
            <h3>完成變更</h3>
            <p><strong>人／AI：</strong>依 repo 內的規範修改程式，先在本機跑最相關的檢查。<strong>模板：</strong>準備規範與檢查腳本。<strong>結果：</strong>一份已自我檢查過、準備送審的修改。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">第三步｜交給團隊</span>
            <h3>提出 PR</h3>
            <p><strong>人：</strong>提出 PR（變更提案），連回原本的 Issue。<strong>模板：</strong>範本提示要說明改了什麼、驗證結果如何。<strong>結果：</strong>一張審查者能快速理解的提案。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">第四步｜系統協助</span>
            <h3>驗證與依賴安全</h3>
            <p><strong>GitHub：</strong>核對本機驗證留下的證明是否新鮮、範圍是否足夠，不重新執行檢查本身；改到套件時另有 hosted 排程比對已知漏洞。<strong>模板：</strong>依變更內容選擇必要驗證。<strong>結果：</strong>判定只出自本機那套同樣的腳本，不是提出者自稱「看起來沒問題」——CI 核對的是這套腳本剛成功執行留下的證明。</p>
          </article>
          <article class="pipeline-stage">
            <span class="pipeline-phase">第五步｜確認結果</span>
            <h3>審查與合併</h3>
            <p><strong>人：</strong>結果與審查都清楚後才核准合併。<strong>GitHub：</strong>依方案能力決定合併保護的強制程度。<strong>結果：</strong>「登入逾時提醒」進入 main，並留下這次改動的完整紀錄。</p>
          </article>
        </div>
        <div class="pipeline-loop" aria-label="CI 回饋迴圈">
          <strong>↺ 檢查失敗 → 回到同一個工作分支修正 → 更新同一張 PR → 重新取得結果</strong>
          <span>合併後才發現的新問題，另外建立一張範圍清楚的 Issue，不回頭改已經合併的分支。</span>
        </div>
        <div class="pipeline-foundation" aria-label="支撐整體流程的平台能力">
          <div class="pipeline-foundation-label"><strong>模板先準備好</strong><span>一般使用者依提示操作；維運者才需要調整設定。</span></div>
          <article class="pipeline-foundation-card"><h3>工作格式</h3><p>Issue 與 PR 表單提示必要內容。</p></article>
          <article class="pipeline-foundation-card"><h3>驗證與安全規則</h3><p>依變更內容選擇必要檢查，並辨識相依風險。</p></article>
          <article class="pipeline-foundation-card"><h3>合併設定</h3><p>依 GitHub 方案套用可用保護。</p></article>
          <article class="pipeline-foundation-card best"><h3>版本發佈</h3><p>流程已設定為候選；預設分支實跑成功後才算啟用。</p></article>
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

一般使用者不必記 workflow 或 script 名稱；依畫面提示操作即可。目前自動化涵蓋工作單、PR 規則與必要驗證；需人審查版本 PR 的發版流程仍是候選。

**責任交接（本機 scripts → GitHub Actions → PR gate → Release）：**

- **本機 scripts（`Active`）：** `scripts/verify-fast`／`scripts/verify-template.sh` 由開發者在本機先跑一次，篩掉大部分低階錯誤。
- **GitHub Actions（`Active`）：** PR 開出後，`.github/workflows/` 只核對本機執行留下的 `Verified-locally:` 證明是否新鮮、tier 是否足夠（Issue #661），不重新執行本機那套政策——證明過期或缺漏一樣會被擋下，不是照單信任。
- **PR gate（依 GitHub 方案而定）：** 支援時由 Ruleset／branch protection 強制擋下未過檢查或未審查的合併；不支援時標示 `DEGRADED`，改由人工自律（見「規則治理」）。
- **Release（`Active`，但需人工觸發）：** 版本與發版證據由具 admin 權限者在本機執行 `scripts/publish-release` 產生；hosted 的 Automatic／Guided 發版路徑是已知限制，不是預設路徑（見「版本／交付」）。

{{< detail key="flow-foundation" title="橫跨全流程的三項基礎" >}}
- **08 規則治理：** 先準備 repo 政策，再依 GitHub 實際方案套用能生效的管制。
- **09 模板升級：** Copier 將新政策帶回既有 repo，差異仍經 PR。
- **10 repo-site：** 讓做法、限制、證據與決策容易查找。

檢查失敗就修正同一張 PR；合併後的新問題則另外建立 Issue。
{{< /detail >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="files" track="files" eyebrow="檔案地圖" title="模板把必要設定放到正確位置" subtitle="列出目前實際產生的主要檔案；公版可提出更新，但不會靜默覆寫產品內容。" class="dense" legacy="false" >}}
{{< standard key="files-mode-standard" title="更新流程與已整合工具" >}}
檔案放在哪裡不是重點；誰能改它才是。每個檔案屬於三種歸屬之一：**公版主導**（模板更新時可能改動，通常不要在生成後直接改）、**共同維護**（你可以直接改，但下次公版更新可能要你合併差異）、**專案持有**（完全由你決定，公版永遠不會覆寫）。

<div class="capability-map"><div class="capability-node"><h3>公版設定 <span class="ownership-tag shared">共同維護</span></h3><p><code>.csarc/config.yml</code>、<code>policies/</code>：語言、分支規則、負責人與審查者都記在這裡。</p></div><div class="capability-node"><h3>GitHub 工作流程 <span class="ownership-tag template">公版主導</span></h3><p><code>.github/</code>：Issue／PR 表單與自動檢查流程。</p></div><div class="capability-node"><h3>Agent 規範 <span class="ownership-tag shared">共同維護</span></h3><p><code>AGENTS.md</code>：agent 在這個 repo 裡怎麼做事。</p></div><div class="capability-node"><h3>專案文件 <span class="ownership-tag shared">共同維護</span></h3><p><code>README.md</code>、<code>docs/</code>、<code>site/</code>：給人看的說明，以及你正在看的這個網站。</p></div><div class="capability-node"><h3>產品程式 <span class="ownership-tag project">專案持有</span></h3><p><code>src/</code>：真正的產品程式碼、測試與規格。</p></div></div>

完整檔案樹與每個檔案的責任歸屬，請切換「維運」模式查看。

公版發現有檔案可以更新時：先在旁邊的隔離環境產生候選（不動這個 repo），再逐一比對檔案：

<div class="plan-grid">
  <article class="plan-card current"><h3>無衝突時更新工作樹</h3><p>直接套用更新，不需要你動手。</p></article>
  <article class="plan-card team"><h3>有衝突時保持原內容</h3><p>只列出受影響的檔案，不動你寫的內容。</p></article>
  <article class="plan-card enterprise"><h3>一律由 PR 審查後才進正式分支</h3><p>不管哪一種結果，最後都要經過人審查才合併，不會有人或程式偷偷覆寫你的內容。</p></article>
</div>

模板已經幫你接好常用工具：專案產生與更新、程式碼安全掃描、相依套件更新提醒、已知漏洞掃描、發版紀錄，還有你正在看的這個 repo-site——不用自己另外找或設定。
{{< /standard >}}

{{< ops key="files-mode-ops" title="更新機制與工具清單的技術細節" >}}
{{< file-map >}}

{{< disclosure key="files-map-scope" title="為什麼檔案地圖只列路徑、作用與責任三欄" >}}
側邊簡報目錄已可直接連到每個項目對應的頁面，僅維運可見的「CI/CD 設定」附錄也已逐步驟詳列驗證入口，細節比這裡能呈現的更完整；樹狀呈現因此不重複加上「對應頁名」或「驗證入口」欄位。

「責任」欄位同時是編輯建議：`公版主導` 通常不要在生成後的 repo 直接改，調整請走「模板升級」這條路徑；`共同維護` 是建議的修改入口，可以直接改，但下次公版更新可能需要你合併差異；`專案持有` 完全由你決定，公版不會觸碰。
{{< /disclosure >}}

{{< disclosure key="files-update" title="更新時怎麼保護產品內容" >}}
Copier 在短分支嘗試更新；若有衝突，只列出檔案且不修改 repo，調整後重跑，再由 PR 審查。建立、既有 repo 導入與同一 repo 後續 update 都有 fixture；回歸測試會刻意加入產品檔案，再確認更新後內容沒有被覆寫。

Root 與 `template/` 同時使用的 workflow、policy、script 與文件由同步程式維持一致；只因專案選項而不同的檔案則以實際生成專案驗證。新 repo 會取得發版 Action；既有 repo 保留自己的 product-owned workflow。
{{< /disclosure >}}

{{< disclosure key="files-tools" title="實際使用的工具" >}}
只列這個模板直接整合、實際執行或會產生到 repository 的工具；外部方案比較留在「相似工具」，語言工具鏈（`uv`、`ty`、`pnpm`、`rustfmt`、`Clippy`、`Cargo`）留在「程式語言」頁。目前版本以 `uv.lock`、已固定的 Action SHA 或下方安裝腳本為準，這裡不重複標註。

| 工具 | 用途 | 出現／設定位置 | 適用範圍 | 授權 |
| --- | --- | --- | --- | --- |
| [Copier](https://github.com/copier-org/copier) | 產生、導入與更新使用此模板的 repository | `copier.yml`、`template/`、`.csarc/config.yml` | 每個由此模板建立或導入的 repository | [MIT](https://github.com/copier-org/copier/blob/master/LICENSE) |
| [zizmor](https://github.com/zizmorcore/zizmor) | 靜態稽核 GitHub Actions workflow 的安全性 | `pyproject.toml`、`scripts/verify-stage-github-actions-audit` | 只在本機驗證（`github-actions-audit` 階段）；hosted `verify` job 改驗證本機驗證聲明的 trailer，不再重新執行 | [MIT](https://github.com/zizmorcore/zizmor/blob/main/LICENSE) |
| [Dependabot](https://github.com/dependabot/dependabot-core) | 開立相依套件更新 PR | `.github/dependabot.yml` | Root 與 template 的套件生態圈 | [MIT](https://github.com/dependabot/dependabot-core/blob/main/LICENSE) |
| [OSV-Scanner](https://github.com/google/osv-scanner) | 掃描 lockfile 中已公開的漏洞 | `scripts/verify-dependencies`、`scripts/install-osv-scanner`、`.github/workflows/osv.yml` | 依賴變更 PR、交付候選、每週排程 | [Apache-2.0](https://github.com/google/osv-scanner/blob/main/LICENSE) |
| [Syft](https://github.com/anchore/syft) | 產生發版用的 SPDX SBOM | `.github/workflows/release.yml`（`anchore/sbom-action`）、`scripts/release_assets.py` | 建立發版的交付 PR | [Apache-2.0](https://github.com/anchore/syft/blob/main/LICENSE) |
| [Release Please](https://github.com/googleapis/release-please) | 維護版本／CHANGELOG PR 並建立 GitHub Release | `.github/workflows/release.yml`、`release-please-config.json`、`.release-please-manifest.json` | 交付分支到 `main` | [Apache-2.0](https://github.com/googleapis/release-please/blob/main/LICENSE) |
| repo-site 渲染引擎 | 自製、無外部依賴的 Python 引擎，從 Markdown 建置雙語 repo-site 與 `llms.txt`；2026-09-03 取代 Hugo | `scripts/build_repo_site.py`、`scripts/build-repo-site`、`scripts/render_site.py`、`site/version.json` | `docs/index.html`、`docs/index.en.html`、`llms.txt` | 自製（本 repository） |
{{< /disclosure >}}
{{< /ops >}}
{{< /slide >}}

{{< slide key="method" track="method" eyebrow="步驟 01" title="先把要做的事定義清楚" subtitle="把需求整理成可執行的 Issue；多張工作需要一起推進時，才建立里程碑。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 1｜<span class="accent">把需求整理成可以開始的工作</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>一張 Issue 定義一項可獨立完成的改變；多項工作需要共同目標與期限時，才使用里程碑。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>統一 Issue 與里程碑的內容，讓人與 agent 在動手前知道要解決什麼、怎樣算完成。</p>
      <p class="context-line"><strong>例如｜</strong>Issue：新增登入逾時提醒／完成條件：逾時前顯示提醒，且有測試證明；工作分支對應這張 Issue；PR 只交付這一項修改。</p>
      <div class="relation-map"><div class="relation-track"><div class="relation-col"><div class="relation-group"><span class="relation-group-label">只有需要時才建立</span><strong>里程碑</strong><span class="relation-group-note">只有多張 Issue 需要共同期限或共同驗收時，才把它們放進同一個里程碑</span></div><span class="relation-group-arrow" aria-hidden="true">↓</span><article class="relation-node"><span class="relation-kind">先寫清楚</span><h3>Issue</h3><p>問題、完成條件、驗證方式與負責人，內容足以開始實作就不加其他文件。</p></article></div><article class="relation-node"><span class="relation-kind">開始實作</span><h3>工作分支</h3><p>一張 Issue 建立一個短期分支，同一分支不混入其他工作。</p></article><article class="relation-node"><span class="relation-kind">審查後合併</span><h3>PR</h3><p>對應同一張 Issue，通過檢查與人審查才進主要分支。</p></article></div></div>
      <p class="context-line"><strong>下一步｜</strong>建立 Issue、切好工作分支就能開始實作；命名規則、里程碑細節、Issue 拆分與例外請切換「維運」模式查看。</p>
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

{{< disclosure key="method-alternatives" title="其他常見做法" >}}
- **先做再補文件：**小而明確的工作直接完成；跨時段、有依賴或高風險時才補計畫。
- **規格先行：**先寫清楚需求、設計與工作拆分，再開始開發。
- **變更提案：**先獨立審查準備修改的內容，接受後才併回正式規格。
- **依複雜度分級：**小工作走短流程，大型工作才增加探索、設計、分工與審查。
{{< /disclosure >}}

{{< config-guidance track="method" >}}
<p class="method-reference reference">Ref. <a href="https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues" target="_blank" rel="noreferrer">GitHub sub-issues</a>。</p>
{{< /basic >}}
{{< /slide >}}

{{< slide key="agents" track="agents" eyebrow="步驟 02" title="先定 AI 規範，再開始實作" subtitle="Issue 說明這次要做什麼；AGENTS.md 說明 agent 在 repo 裡怎麼做。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 2｜<span class="accent">先定 AI 規範，再開始實作</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>Issue 劃定這次工作；<code>AGENTS.md</code> 說明怎麼做；程式與測試提供證據，人保留需求方向與重大風險決策。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>自動產生並檢查 agent 開始前要讀什麼、可修改到哪裡、如何隔離平行工作與怎樣留下驗證；只有客製規範、重大決策與例外需要人判斷。</p>
      <div class="capability-map cols-3"><div class="capability-node"><h3>Issue：這次要做什麼</h3><p>說明這次要完成什麼、怎樣算完成；範圍與進度都記在這裡，重大決策記在核准的 spec／ADR（規格與架構決策紀錄）。</p></div><div class="capability-node"><h3>AGENTS.md：在這個 repo 怎麼做</h3><p>跟著 repository 版本控制的工作守則；agent 開始前一律先讀這份，不必臆測慣例。</p></div><div class="capability-node"><h3>證據與決策</h3><p>scripts／tests 提供任何人都能重跑的驗證證據；需求方向、重大取捨與不可逆操作仍由人決定。</p></div></div>
      <p class="context-line"><strong>下一步｜</strong>照 <code>AGENTS.md</code> 開始讓 agent 工作；修改隔離、驗證證據與模板更新規則的細節請切換「維運」模式查看。</p>
{{< /legacy >}}

{{< basic >}}
### 我們的選擇

- **預設自動：** 模板會產生並檢查 AI 規範；只有客製規範、重大決策與例外需要人判斷。
- **工作與脈絡：** GitHub Issue／PR 記錄工作；核准的 spec／ADR 保存長期決策，必要時才加 plan。
- **AI 規範：** 根目錄 `AGENTS.md`；`CLAUDE.md` 只薄匯入。
- **修改隔離：** 每項可寫工作各用 branch／worktree；唯讀工作不用。
- **驗證證據：** 本機程式是唯一邏輯；Action 只呼叫它。
- **決策與授權：** 人保留重大決策；審查與合併規則只由「規則治理」定義。
- **模板建立與更新：** Copier 負責共用基線；既有 repo 更新由「模板升級」定義。

{{< disclosure key="agents-priority-and-isolation" title="規則優先順序與修改隔離" >}}
- **規則優先順序：** 根目錄 `AGENTS.md` 對整個 repository 有效；只有子目錄的指令或安全界線真的不同時，才另外放一份更近的 `AGENTS.md`，此時該子目錄內以較近的規則為準，其餘仍回到根目錄規則。`CLAUDE.md` 一律只薄匯入根目錄 `AGENTS.md`，不重複定義規則。
- **修改隔離：** 每項可寫的工作各自使用一個 Git branch 與一個 worktree，讓平行進行的工作不互相干擾；唯讀工作（例如只是查資料）不需要建立分支或 worktree。
{{< /disclosure >}}

{{< disclosure key="agents-alternatives" title="其他常見做法" >}}
- **Repo 內指引：**把固定命令與界線放在版本控制中，讓不同 agent 讀同一份規則。
- **規格產物接力：**大型工作先產生 spec、plan、tasks，再逐步交給 agent 執行。
- **角色與調度：**用專門角色、skills 或佇列安排多個 agent；適合工作量已大到需要額外協調時。
- **人類檢查點：**在需求、重大取捨、外部影響與不可逆操作前停下來取得決定。
{{< /disclosure >}}

{{< config-guidance track="agents" >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="contract" track="contract" eyebrow="步驟 03" title="先在本機驗證，CI 只驗證這份驗證證明" subtitle="Issue 與 PR 依變更範圍分級；只有高風險交付邊界才跑完整驗證。" class="candidate-slide" legacy="false" >}}
{{< standard key="contract-mode-standard" title="改動大小決定驗證輕重" >}}
開發者先在自己的電腦跑完對應分級的驗證；成功時本機會寫下一份「已驗證」聲明。PR 開出後，GitHub 只依同一份政策核對這份聲明是否新鮮、範圍是否足夠，不重新執行檢查本身——本機只跑能證明這次修改的檢查，不用等整條流程；PR 開出後，系統自動依變更範圍決定要跑哪一級：

<div class="plan-grid">
  <article class="plan-card current"><h3>docs</h3><p>純文件變更，檢查最輕量。例如：只改一份說明文件。</p></article>
  <article class="plan-card team"><h3>fast</h3><p>一般變更，日常開發預設走這一級。例如：一般程式或設定修改。</p></article>
  <article class="plan-card enterprise"><h3>full</h3><p>里程碑交付、Hotfix，或抓不準風險的變更。例如：里程碑／canary 交付、Hotfix、merge queue。</p></article>
</div>

本機與 CI 共用同一套判斷邏輯，不會兩邊各自維護一份規則。
{{< /standard >}}

{{< ops key="contract-mode-ops" title="分級邏輯與目前自動化現況" >}}
- **開發中：**只跑能證明本次修改的 focused check（例如 `uv run pytest <path>`、`uv run ruff check <path>`），用新鮮輸出才宣稱完成，不等待整條 pipeline。
- **工作 PR（工作分支 → main 或 `dev/m*`）：**`scripts/ci_tier.py` 依事件、base／head、labels 與變更路徑分類為 `docs`、`fast` 或 `full`；純文件／site 內容落在 `docs`（`fast` 的 early-exit 情境），一般變更落在 `fast`；無法判斷的路徑一律 fail-closed 升級為 `full`。
- **需要完整驗證時：**只在 Milestone／canary 交付、緊急修正、merge queue、手動執行，或系統無法安全縮小範圍的未知高風險路徑才觸發。
- **同一套邏輯，Hosted 端不重跑（#661）：**GitHub Actions 只有一個 `verify` job，`contents: read` 權限、最多 15 分鐘，同一 PR 新 commit 會取消舊 run；它不重新執行 `scripts/verify-fast`／`scripts/verify-template.sh`（生成 repo 是 `scripts/verify`），只驗證這些腳本本機執行成功時寫入 commit 的 `Verified-locally:` trailer（tree hash、tier 與時間戳記）夠新鮮、tier 是否足夠。push 前沒有先跑過對應分級，hosted 這個輕量 job 就沒有東西可驗證，會直接失敗。
- **專案範圍：**一般專案只驗證自己的改動；公版專案的完整驗證還包含標記 `large` 的 Copier 建立／既有導入／更新回歸測試，實際生成新專案元件並驗證其保存的產品內容，不只是「檔案存在」。

驗證邏輯只放在 repo 內可執行的 `scripts`／`tests`；GitHub Action 只負責事件、權限與呼叫同一份程式，不重複邏輯。

{{< disclosure key="contract-root-state" title="Root repo 狀態（2026-09-03）" >}}
<aside class="config-guidance" data-audience="maintainer"><p>依賴安全（<code>osv.yml</code>）在公版 root 自己身上仍是 candidate：這支 workflow 已落地 <code>main</code> 並由 GitHub 註冊為 active，但觸發條件只有 <code>schedule</code>（UTC 週一 03:17）與 <code>workflow_dispatch</code>，不含 <code>pull_request</code>，所以無法在候選分支預先註冊；<code>gh run list</code> 尚未查到任一次排程或手動觸發的 run，不構成本頁與 <code>docs/ci-policy.md</code> 定義的 live run 證據。新生成的 repo 因為 Copier 初次 commit 就進入該 repo 的 <code>main</code>，可以立即註冊與觸發，狀態是 active。</p></aside>
{{< /disclosure >}}

{{< disclosure key="contract-automation" title="目前有哪些自動化真的在跑" >}}
以下狀態逐項對照 `docs/ci-policy.md` 的「Current automation」表與即時查詢（2026-09-03），不沿用建置當下可能已過期的數字：

- **Active：**CI（`ci.yml`）、PR policy（`pr-policy.yml`）、工作單生命週期（`work-item-lifecycle.yml`，整合 Issue triage、里程碑同步與 Work Issue closure）、Spec to Issue（`spec-to-issue.yml`）、reviewer 指派（`governance-comment.yml`）與 Dependabot（GitHub 原生功能）都已註冊並有近期成功的 live run。
- **已修正的已知限制：**Work Issue closure 過去用 `pull_request.base.sha` checkout，合併後才存在的 `close-work` 指令因此找不到而失敗；#401／PR #453（2026-09-02 合併）已改用 `pull_request.merge_commit_sha`，2026-09-03 已有成功 live run。Milestone lifecycle 的核准／結案驗證覆蓋（`tests/test_milestone_approval.py`／`tests/test_milestone_closure.py`）也已在本候選中；追蹤 Issue #400 已於 2026-09-02 結案為 completed。
- **依情境而定：**依賴安全（OSV）在生成 repo 是 active；在公版 root 自己身上仍是 candidate，理由見上方 aside。
- **Candidate，本頁不重複驗證：**Version／Release（`release.yml`）目前確切狀態請直接查 `docs/ci-policy.md` 的「版本、發版、交付與部署矩陣」一節。
- **未啟用：**專用的 promotion、release-handoff、registry publisher、consumption、live-integration 與 deployment workflow 都不存在，也不是留待接上的 conditional 選項。
{{< /disclosure >}}

{{< disclosure key="contract-cost" title="三種驗證分級的實際耗時" >}}
數字取自 `docs/ci-policy.md` 記錄的最近一次量測，是設定成本預期的參考點，不是永久 SLA；重跑會拿到不同數字。

- `docs` 與 `fast` 共用同一條 bounded path；`docs` 只是純文件／site 內容時的 early-exit 情境。
- `fast`：2026-09-01 同機暖快取下，只碰 source 的 scope 約 59 秒，同時碰 policy／template 的 scope 約 99 秒；整條 PR feedback window 約 1–4 分鐘（#428）。
- `full`：獨占環境下七個階段全數 PASSED 共 502 秒（8 分 22 秒）；同機器有其他 worktree 並行執行時量到 810 秒，差異來自資源競爭，不是驗證內容本身變重（#458，2026-09-02）。七個階段中，Regression tests（完整 pytest 加上標記 `large` 的 Copier 建立／導入／更新矩陣）通常是耗時最長的一段，其餘六個階段合計通常只有數十秒。
{{< /disclosure >}}

{{< config-guidance track="contract" >}}
{{< /ops >}}
{{< /slide >}}

{{< slide key="languages" track="languages" parity="new" eyebrow="步驟 04" title="選擇程式語言後，自動帶入適合的檢查" subtitle="每種語言各自定義工具與測試；共通規則只執行一次。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 4｜<span class="accent">每種程式語言各自管理</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>使用者只要選擇專案語言，模板就產生對應版本、鎖檔、格式、靜態檢查、測試與建置設定。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>使用者只選 repo 真正使用的語言；模板替每種語言接上原生檢查，但整體仍走同一條 PR 流程。</p>
      <p class="context-line"><strong>共通流程｜</strong>選擇語言 → 產生對應工具與鎖檔 → 執行格式／靜態檢查／測試／打包 → 結果交給同一個驗證入口（見「驗證／CI」）。</p>
      <div class="capability-map cols-3"><div class="capability-node"><h3>Python</h3><p>檢查程式格式、型別、測試，以及能否製作安裝包。</p></div><div class="capability-node"><h3>Rust</h3><p>檢查程式格式、常見錯誤、測試，以及正式版本能否建置與打包。</p></div><div class="capability-node"><h3>TypeScript</h3><p>檢查程式格式、型別、測試，以及能否製作安裝包。</p></div></div>
      <p class="context-line"><strong>下一步｜</strong>建立或導入時勾選需要的語言即可，同時使用多種語言時共通項目只跑一次；其他做法的比較請切換「維運」模式查看。</p>
{{< /legacy >}}

{{< basic >}}
### 我們的選擇

選擇專案語言後，模板會自動準備對應檢查：

- **所有專案：**檢查工作規則、文件、機密與套件安全。
- **Python：**檢查格式、型別、測試及安裝包。
- **Rust：**檢查格式、常見錯誤、測試、正式建置及安裝包。
- **TypeScript：**檢查格式、型別、測試及安裝包。

每種語言是各自獨立的元件（模組），同一項共通檢查只跑一次；語言可以同時勾選，但不另外建立或說明每一種排列組合。版本來源與鎖檔各自獨立：Python 讀 `pyproject.toml`／`uv.lock`，Rust 讀 `Cargo.toml`／`Cargo.lock`，TypeScript 讀 `package.json`／`pnpm-lock.yaml`；改動後執行下方「固定基線｜一個入口驗證與打包」列出的單一驗證入口即可。

### 其他常見做法

- **單一跨語言工具：**入口一致，但需要另外維護抽象層。
- **各語言原生工具：**開發者容易理解，版本與輸出則要由模板統一管理。
- **每種組合各寫一套：**初期直觀，組合增加後很容易重複與漂移。

{{< config-guidance track="languages" >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="supply" track="supply" eyebrow="步驟 05" title="第三方套件分開更新、檢查與記錄" subtitle="一般新版先觀察，已知漏洞立即處理，發版成品留下可追查清單。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 5｜<span class="accent">第三方套件分開更新、檢查與記錄</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>套件從哪裡更新、能否重裝、有沒有已知漏洞，以及成品包含什麼，是四件需要分開確認的事。</p>
      </header>
      <p class="context-line"><strong>舉例｜</strong>開發時要新增或更新一個第三方套件，模板把「裝得回來」「有沒有更新」「有沒有已知漏洞」「發版時裝了什麼」拆成四個各自獨立、依序發生的步驟：</p>
      <div class="capability-map"><div class="capability-node"><h3>1｜鎖定安裝內容</h3><p>依鎖定版本清單（lockfile）重裝，確保每次拿到同一批套件。<strong>你會看到：</strong>安裝／CI 直接使用鎖定版本。<strong>會阻擋合併嗎：</strong>鎖檔與宣告不一致就會。</p></div><div class="capability-node"><h3>2｜Dependabot 提出更新 PR</h3><p>自動更新服務每週提出 PR；一般新版等三天觀察期，已知安全修補不等待。<strong>你會看到：</strong>一張待審查的更新 PR。<strong>會阻擋合併嗎：</strong>不會自動阻擋，但仍要通過一般 PR 驗證。</p></div><div class="capability-node"><h3>3｜OSV 比對已知漏洞</h3><p>已知漏洞掃描檢查依賴變更與發版候選，不等待新版觀察期。<strong>你會看到：</strong>掃描結果附在 PR 或發版候選上。<strong>會阻擋合併嗎：</strong>掃到已知漏洞會。</p></div><div class="capability-node"><h3>4｜Release 時產生 SBOM</h3><p>發版時列出成品實際包含的套件（成品清冊），方便事後追查。<strong>你會看到：</strong>Release 附帶的 SBOM 檔案。<strong>會阻擋合併嗎：</strong>不會，它是清冊不是關卡。</p></div></div>
      <p class="context-line"><strong>務必記得｜</strong>lockfile 只保證「裝得回來」，不代表沒有已知漏洞；已知安全修補不適用三天觀察期；OSV 只能認得已公開揭露的漏洞，不保證找到所有問題；SBOM 是追查用的清冊，本身不會修補或阻擋任何漏洞。</p>
      <p class="context-line"><strong>下一步｜</strong>套件更新會自動提出 PR，看到就審查合併；各項保護為何要分開的細節請切換「維運」模式查看。</p>
{{< /legacy >}}

{{< basic >}}
### 我們的選擇

模板會自動執行例行的更新與安全檢查；只有升級衝突、漏洞處置與風險接受需要人判斷。

| 這次要防什麼 | 模板目前怎麼處理 |
| --- | --- |
| 改了套件卻無法重裝 | PR 會依鎖定版本清單（lockfile）重新安裝，確認每次拿到同一批套件 |
| 剛發布的惡意版本 | 自動更新服務（Dependabot）分組提出 PR；一般新版等三天，安全更新不等待 |
| 已公開漏洞沒有被注意 | 已知漏洞掃描（OSV）會檢查依賴 PR 與交付候選；每週掃描補上沒有 PR 的期間 |
| 發版後不知道包含什麼 | 軟體成分清單（SBOM）列出成品包含的套件；依賴安全負責驗證，交付成品時產生 |

{{< disclosure key="supply-boundaries" title="這四種保護為什麼要分開" >}}
- **鎖定版本：**確認每次安裝使用同一批套件。
- **觀察期：**不在一般新版發布當天立刻採用。
- **漏洞掃描：**立即比對已公開的安全問題，不等待三天。
- **成品清冊（SBOM）：**列出發布成品實際包含的套件，方便追查；它本身不會阻擋漏洞。
{{< /disclosure >}}

### 其他常見做法

- **自動更新服務：**定期提出升版的變更提案（PR），適合不想人工巡查版本的團隊。
- **套件安裝政策：**固定可安裝版本並觀察剛發布的版本，降低每次安裝拿到不同內容的風險。
- **漏洞掃描：**比對公開漏洞資料庫；即使沒有升版 PR，也能發現既有風險。
- **軟體成分清單（SBOM）：**發版時列出成品包含的套件，供事件追查與使用者核對。

{{< config-guidance track="supply" >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="pr" track="pr" eyebrow="步驟 06" title="讓完成的改動可審查、可交付" subtitle="獨立工作直接進 main；只有需要共同驗收的 Milestone 才使用交付 PR。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 6｜<span class="accent">讓完成的改動可審查、可交付</span></h2>
        <p class="subtitle"><strong>基本導入。</strong>這一頁從準備開 PR 開始：工作 PR 完成一張 Issue，交付 PR 再確認整批成果——下一頁「版本／交付」才會談到版本 PR。</p>
      </header>
      <p class="context-line"><strong>模板的作用｜</strong>把完成的修改帶到正確分支，確認它連回原工作、通過驗證並在合併後結束對應工作。</p>
      <div class="capability-map cols-3"><div class="capability-node"><h3>獨立工作</h3><p>topic → main：一張 PR 只完成一張可驗收 Issue；合併後連動關閉同號 Issue。</p></div><div class="capability-node"><h3>Milestone 工作</h3><p>topic → <code>dev/m*</code> → 交付 PR → main：批次內每張 PR 先進 <code>dev/m*</code>，全部完成後由交付 PR 整批驗證進 main。</p></div><div class="capability-node"><h3>例外：Hotfix</h3><p>修正分支可直接進 main，但仍要 Issue、審查與完整驗證。</p></div></div>
      <p class="context-line"><strong>下一步｜</strong>完成一張 Issue 就開一張工作 PR；PR 標題格式、分支命名與其他合併模型比較請切換「維運」模式查看。</p>
{{< /legacy >}}

{{< basic >}}
### 我們的選擇

| PR 階段 | 目的地 | 這一步完成什麼 |
| --- | --- | --- |
| 獨立工作 PR | topic → main | 審查一項改動；合併後關閉連結的 Issue |
| Milestone 工作 PR | topic → `dev/m*` | 審查批次內的一項改動 |
| 交付 PR | `dev/m*` 或明列的 `dev/i*` → main | 完整驗證整批成果後交付；維護者再結束里程碑與清理交付分支 |

{{< disclosure key="pr-version-intent" title="PR 標題、分支與例外" >}}
- 工作分支使用 `type/<Issue>-short-slug`，並連回同號未結案 Issue。
- PR 標題使用 Angular／Conventional Commits 格式：`type(scope)!: English summary`。type 可用 `feat` 新功能、`fix` 修錯、`docs` 文件、`refactor` 重構、`test` 測試、`build` 建置／相依、`ci` 自動化、`chore` 維護、`revert` 撤回；scope 與 `!` 可省略。版本意圖為 `feat`＝minor、`fix`／`revert`＝patch、`!`＝breaking／major，其餘不主動升版。
- 工作 Label 與里程碑要和 Issue 一致；PR 作者必須列為負責人。
- 里程碑工作進 `dev/m<里程碑>-*`；一般獨立工作直接進 `main`。
- `sync/main-to-*` PR 在 Milestone／canary 最終交付前納入最新 main；只有 owner 記錄真實相依時才提前同步，不對所有分支 fan-out。
- 只有明確標示的 standalone hotfix 可直接進 main；誰能合併由「規則治理」決定。
{{< /disclosure >}}

### 其他常見做法

- **GitHub Flow：**每張完成的 PR 直接進 main，路徑最短，適合可持續交付的團隊。
- **長期整合分支：**多項工作先在 dev／release branch 集中驗收，代價是要處理同步。
- **Stacked PR：**把大型改動拆成相依的小 PR，審查較聚焦，但需要維護堆疊順序。
- **Merge queue：**把已核准 PR 依最新 main 重新驗證後排序合併，需要平台門禁支援。

{{< config-guidance track="pr" >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="deploy" track="deploy" eyebrow="步驟 07" title="先分清版本、發版與交付；部署交給專案自己決定" subtitle="工作先交付到 main；需要新版本時，系統建立一張仍須人工審查的版本 PR。模板負責到 Release，不含部署。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>步驟 7｜<span class="accent">版本規則與成品接續</span></h2>
        <p class="subtitle"><strong>合併不等於發版，發版也不等於部署。</strong>工作 PR 不直接改版本；Release Please（自動整理版本號的工具）集中更新版本與 CHANGELOG。</p>
      </header>
      <p class="context-line"><strong>設計流程｜</strong>工作 PR 只宣告版本影響；版本 PR 經人審查合併後，系統才建立並驗證 Release。</p>
      <div class="relation-map"><div class="relation-track cols-4"><article class="relation-node"><span class="relation-kind">1｜工作完成並合併</span><h3>獨立工作</h3><p>能自己驗收且沒有共同期限或相依時，受審查 PR 可直接進 main。</p></article><article class="relation-node"><span class="relation-kind">2｜準備版本</span><h3>正式版本</h3><p>需要新版本時，系統依 PR 標題建立版本 PR，同步版本與 CHANGELOG。</p></article><article class="relation-node"><span class="relation-kind">3｜建立 Release</span><h3>Release</h3><p>版本 PR 合併後，系統驗證成品、checksum（檔案校驗碼）與 SBOM，成功才公開不可變 GitHub Release。</p></article><article class="relation-node"><span class="relation-kind">4｜模板不負責這步</span><h3>部署</h3><p>模板負責到 Release；實際部署到 runtime，由個別專案自行設定。</p></article></div></div>
      <p class="context-line"><strong>下一步｜</strong>一般工作合併到 main 就完成交付；里程碑分支、Hotfix 與其他版本工具比較請切換「維運」模式查看。</p>
{{< /legacy >}}

{{< basic >}}
### 我們的選擇

- **版本意圖：**PR title 只回答這次改動是 major、minor、patch 或 no-release，不預約精確版本號。
- **正式版本：**Release Please 用同一張受審查 PR 更新版本檔、package metadata 與 CHANGELOG；CI 不在 checkout 內暫時改版本。
- **發版：**版本 PR 合併並通過完整驗證後，系統建立不可變 tag、GitHub Release、成品、checksum 與 SBOM。
- **交付：**合併到 `main` 代表 repository delivery；它可以不產生新版本。工作 PR 結束單項工作，Milestone delivery PR 才交付整批。
- **獨立工作：**能單獨審查與驗證、沒有共同期限或跨 Issue 相依時，不必加入里程碑；PR 可直接進 `main`。
- **Hotfix：**只用於立即修正 `main` 的缺陷；仍要有 Bug Issue、另一人審查與完整驗證，合併後由版本 PR完成 patch 發版審查。
- **部署：**把產品送進真實 runtime、檢查健康狀態與復原，屬 consuming product，不是本模板目前提供的能力。

{{< disclosure key="deploy-capability-status" title="各項能力目前狀態逐一對照" >}}
| 能力 | 目前狀態 | 現在怎麼做 |
| --- | --- | --- |
| PR 的 SemVer 意圖 | Active | `fix`／`revert` 為 patch、`feat` 為 minor、`!` 為 major，其餘 no-release |
| 正式版本與 CHANGELOG | Candidate／Guided | Automatic 由 Release Please 建立受審查 PR；受平台政策限制時，Guided 由人或 agent 開一般 PR |
| tag／GitHub Release | Candidate／Blocked | 版本 PR 合併後由唯一 workflow 發布；待預設分支實跑證明 |
| checksum／SBOM | Configured | 已納入同一候選流程；首次成功實跑後才算 Active |
| Production-side attestation | Removed（#439） | 沒有任何 active workflow 消費 release attestation 設定；#439 已移除該設定面，不留下承諾不了結果的選項。有真實需求的產品另開 Issue／ADR 加入 attestation |
| Consumption-side verification | Conditional | `scripts/verify_release_consumption.py` 與上列產出端設定無關；真實消費者明確採用後才是門禁 |
| PyPI／npm／GHCR | Not applicable | root 不發布 registry；#439 已移除閒置的 PyPI／npm／GHCR 設定項，因為沒有任何 workflow 消費它們，生成專案現在也不再提供這些設定。有真實需求的產品另開 Issue／ADR 自行加入 OIDC publisher |
{{< /disclosure >}}

{{< disclosure key="standalone-delivery" title="獨立工作何時必須改掛里程碑" >}}
一張 Issue 能自己驗收、沒有共同期限、整批驗收、跨 Issue 相依或獨立測試環境時，從最新 `main` 建立工作分支，PR 直接回 `main`，用 `Closes #N` 在合併後結案。若出現上述任一批次需求，必須在實作前加入適當里程碑並改走 `dev/m*`；不能用獨立工作路徑繞過共同驗收。
{{< /disclosure >}}

{{< disclosure key="deploy-ordering" title="交付順序、成品與 registry 邊界" >}}
Direct mode 在寫入前重讀 default branch head，只有最新 `main` 且 source、tag、CHANGELOG、promotion evidence 一致才交付，不假設 workflow concurrency 提供 FIFO。成品 workflow 只接受 release-source run ID，產生 digest 與 SBOM，不監聽任意 tag push，也不重跑已完成的 full CI。

GitHub Release 是所有 profile 的共同基線。PyPI、npm、GHCR 與 artifact attestation 屬產品自行實作的交付擴充，公版不提供只有設定、沒有執行者的假選項。能力偵測與版本配置在 `scripts/release_policy.py`，promotion gate 在 `scripts/promotion_gate.py`。
{{< /disclosure >}}

{{< disclosure key="hotfix-delivery" title="Hotfix 的審查、驗證與證據" >}}
Hotfix 建立不屬於里程碑的 Bug Issue，使用 `bug`＋`hotfix`、`fix/<Issue>-*` 與 `fix(scope): summary`，直接對 `main` 開 PR；仍須正常 review 與 full verification。未公開的安全問題改用 GitHub Security Advisory 私密處理。合併後保留 PR、commit SHA、full run 與 rollback 說明；`fix` 預設是 patch 意圖，精確版本仍要在 Release Please 版本 PR 由人審查。
{{< /disclosure >}}

{{< disclosure key="manual-release-boundary" title="自動發版的責任邊界" >}}
公版與新 repo 各自由自己的 release workflow 發布；既有 repo 保留 product-owned workflow。所有流程都要有唯一 owner、最小權限、完整 SHA pinning、timeout、concurrency、失敗復原與 runner 成本；歷史 run 只能當歷史資料。

Adoption 與 update 不從 workflow 檔名推測 ownership。`.csarc/config.yml`、adoption plan、Markdown report 與 `.csarc/provenance.json` 一致揭露同一個明確的 `release_ownership`——`csarc-owned`、`product-owned` 或 `verification-only`——以及選定的 workflow 路徑、其 `workflow_dispatch` 必要 inputs、settings owner、是否要求 immutable Releases，以及降級為 `verification-only` 的原因（沒有找到 writer，或找到一個以上）。CSARC 不會 dispatch product-owned workflow，也不從名稱推測其 input contract；只讀取該 workflow 自己宣告的內容。

`release_ownership: csarc-owned` 的生成 repo（含本模板 root 自己）另外取得一條不依賴 GitHub Actions 是否健康的本機發版 backup：`release.yml` 的發布階段抽成單一腳本 `scripts/publish-release`，維護者或 agent 在本機（或任何持有 admin／write 權限的環境）呼叫同一份腳本即可完成 tag、Release、成品與 SBOM，Guided 模式的啟用條件也從「組織政策擋住 Actions 建 PR」擴大為包含「判斷 Actions／webhook 目前不可信任」。這條路徑仍要求版本 PR 經過與其他 `main` PR 相同的 review。驗證（`verify`／`title`／`promotion`）仍只能、也仍建議由 hosted Actions 產生；但實際切版本／發 Release 這一步，hosted job 自己的 `GITHUB_TOKEN` 永遠無法證明 GitHub 的 Immutable Releases 設定（這是一個 GitHub Actions 任何 permission 都無法開放的 repo administration 能力）——所以這條本機路徑現在是標準發版程序，不是備援；細節見 [ci-policy.md](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/ci-policy.md) 與 [release-security-and-dependencies ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/release-security-and-dependencies.md)。這不是一個新的 Copier 選項——既有的 `release_ownership` 已經正確路由這個能力。

`release_ownership: csarc-owned` 的生成 repo（含本模板 root 自己）另外取得一條不依賴 GitHub Actions 是否健康的本機發版 backup：`release.yml` 的發布階段抽成單一腳本 `scripts/publish-release`，維護者或 agent 在本機（或任何持有 admin／write 權限的環境）呼叫同一份腳本即可完成 tag、Release、成品與 SBOM，Guided 模式的啟用條件也從「組織政策擋住 Actions 建 PR」擴大為包含「判斷 Actions／webhook 目前不可信任」。這條路徑仍要求版本 PR 經過與其他 `main` PR 相同的 review。驗證（`verify`／`title`／`promotion`）仍只能、也仍建議由 hosted Actions 產生；但實際切版本／發 Release 這一步，hosted job 自己的 `GITHUB_TOKEN` 永遠無法證明 GitHub 的 Immutable Releases 設定（這是一個 GitHub Actions 任何 permission 都無法開放的 repo administration 能力）——所以這條本機路徑現在是標準發版程序，不是備援；細節見 [ci-policy.md](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/ci-policy.md) 與 [release-security-and-dependencies ADR](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/adr/release-security-and-dependencies.md)。這不是一個新的 Copier 選項——既有的 `release_ownership` 已經正確路由這個能力。

里程碑完成時人工確認交付證據後再結案；#400、#401 尚未完成的 lifecycle gap 不在本頁複製 validator。工作分支合併後清理，里程碑 delivery branch 則等結案與未完成工作處置完成後才清理。
{{< /disclosure >}}

{{< disclosure key="release-notes-format" title="發版紀錄在哪裡看、格式代表什麼" >}}
想知道某個版本實際變了什麼、為什麼發、跟上一版差在哪，直接看 GitHub 的
[Releases 頁面](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/releases)：每個
版本一則 Release，固定包含三項：**版本號**（Release 標題，等於 `vMAJOR.MINOR.PATCH` tag）、
**發布日期**（GitHub 自動標示的發布時間，不需要另外找）、**變更摘要**（GitHub 依這段期間
merge 進來的 PR 標題自動整理成「What's Changed」清單，附上跟前一版的完整比較連結）。

這三項不是靠人手動填寫、也不會因為誰執行發版而有不同風格：不管是 hosted GitHub Actions
自動觸發，還是維護者判斷 Actions 不健康時改在本機執行 `scripts/publish-release`，兩條路徑
最終都呼叫同一支 `scripts/converge-release-tag`、用同一個 `gh release create ...
--generate-notes` 指令產生 Release 說明，結構上不存在兩份可能各自長出不同格式的實作。

根目錄的 `CHANGELOG.md` 是另一個同樣真實、但分類方式不同的視角：它依 Conventional
Commit 類型把變更分成 Breaking Changes／Features／Bug Fixes；GitHub Release 說明文字則是
依 PR 列出「What's Changed」。兩者不會逐字對照，也不需要——同一批變更，兩種排列方式。
沒有另外要求每則 Release 都寫「已知限制」或「回溯相容性」段落：多數版本沒有實質內容可
填，跨版本持續有效的已知限制改記在這裡與 `docs/ci-policy.md`，不在每則 Release 裡重複。
完整規範與為什麼採取這個範圍，見
[ci-policy.md](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/blob/main/docs/ci-policy.md)
的「Release 說明文字的最低格式規範」一節。
{{< /disclosure >}}

{{< disclosure key="deploy-alternatives" title="其他常見做法" >}}
- **Release Please：**以可審查 PR 集中更新版本與 CHANGELOG。
- **semantic-release：**成功 CI 後依 commit 慣例全自動發版。
- **Changesets：**以 changeset 檔管理多套件與 workspace 的版本影響。
{{< /disclosure >}}

{{< config-guidance track="deploy" >}}

{{< disclosure key="deploy-version-sources" title="版本來源與同步範圍對照" >}}
<aside class="selection-note"><strong>目前邊界</strong><span>不要求 PAT、GitHub App、registry token 或空 deployment environment。新 repo 使用 CSARC workflow；既有 repo 保留自己的發布流程。Registry 與 attestation 仍是選配。</span></aside>
<table class="decision-register" aria-label="版本來源與同步範圍">
  <thead><tr><th>版本範圍</th><th>單一來源</th><th>必須同步</th><th>獨立狀態</th></tr></thead>
  <tbody>
    <tr><td>公版與 CLI Release</td><td>root <code>.release-please-manifest.json</code></td><td>root 版本檔、README／docs marker、CHANGELOG、tag、Release 與成品</td><td>自動準備、人工審查</td></tr>
    <tr><td>Copier 公版 revision</td><td>已發布 tag＋完整 commit SHA</td><td>Release provenance、<code>.csarc/config.yml</code> 的 <code>_commit</code></td><td>不另編版本</td></tr>
    <tr><td>生成專案 Release</td><td>生成後的 <code>.release-please-manifest.json</code></td><td>該專案自己的 manifest、package、CHANGELOG、tag 與成品</td><td>從 <code>0.1.0</code> 開始，不跟隨公版版本</td></tr>
  </tbody>
</table>
<p class="context-line"><strong>SemVer scope｜</strong>整份公版只用一個 SemVer：<code>fix(scope)</code> 升 patch、<code>feat(scope)</code> 升 minor、<code>!</code> 升 major；scope 可標 <code>ci</code>、<code>python</code>、<code>typescript</code> 或 <code>template</code>，只要任何已支援 profile 不相容，就視為整份公版的破壞性變更。</p>
<aside class="selection-note"><strong>產品自行擴充：套件與容器發布</strong><span>GitHub Release 是公版共同基線。PyPI、npm、GHCR 與 artifact attestation 沒有現行公版 publisher，不能只靠設定開關宣稱已啟用；有真實 registry、owner 與部署需求的產品，另以短效 OIDC、專用 environment、驗證與復原流程實作。</span></aside>
{{< /disclosure >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="governance" track="governance" eyebrow="步驟 08" title="只套用 GitHub 真正能強制的管制" subtitle="公版先準備同一套政策，維運者再依實際方案確認哪些會生效。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>先辨識 GitHub 方案，<span class="accent">再套用真的能生效的管制</span></h2>
        <p class="subtitle"><strong>基本導入｜</strong>把規則寫進 repo，不代表 GitHub 一定有能力強制它；模板會先檢查平台能力，再決定強制或明確降級。</p>
      </header>
      <p class="context-line"><strong>流程｜</strong>期望政策 → 檢查 GitHub 方案與權限 → 可以強制：套用並驗證 → 無法強制：標示 <code>DEGRADED</code>，留下人工責任。</p>
      <div class="relation-map"><div class="relation-track"><article class="relation-node"><span class="relation-kind">提出 PR</span><h3>人審查</h3><p>系統自動指派一位非作者的審查者，並保留審查紀錄。</p></article><article class="relation-node"><span class="relation-kind">檢查方案與權限</span><h3>能不能強制</h3><p>模板查目前方案、repo 可見性與權限，判斷能不能建立 Ruleset（GitHub 強制執行的合併規則）。</p></article><article class="relation-node"><span class="relation-kind">兩種結果</span><h3>套用驗證，或明確降級</h3><p>能強制就套用並在 <code>check</code> 驗證是否生效；不能強制就標示 <code>DEGRADED</code>，改由人工自律把關，不假裝已經強制。</p></article></div></div>
      <p class="context-line"><strong>下一步｜</strong>方案改變或升級後，重新套用一次設定即可；這個 repo 目前實際處於哪一種結果，以及 Team／Enterprise 各方案的完整能力，請切換「維運」模式查看。</p>
{{< /legacy >}}

{{< basic >}}
公版會準備負責人、審查人、repo 基本設定與預期的分支規則。維運者檢查 GitHub 實際方案後：

- 支援的管制才套用並驗證。
- 付費方案才有的功能若不可用，會標成 `DEGRADED` 並改由人工處理，不會假裝已強制。
- 原本可以套用、但目前設定不一致的項目會停止，修正後才能繼續。

{{< disclosure key="governance-live-status" title="這個 repo 本身現在的真實狀態（查詢日期：2026-09-07）" >}}
`Innoguard-Cyber-Arch` API 回報這個 repository 是 Free 方案、**public** 可見度。GitHub 上已有一個 `enforcement: active` 的 Ruleset「CSARC protected branches」（建立於 2026-09-03），套用在 `main` 與 `dev/m*`：要求至少 1 個核准、CODEOWNER 審查、`title`／`promotion`／`verify` 三項狀態檢查全部通過，且不允許 force-push——`main` 目前確實有強制的合併保護。

這對應下表「Free＋public，或 Pro 個人＋private」那一列，不是下面「Free／Team／Enterprise 各方案完整能力」卡片裡 Free 方案描述的 **private** 降級情境（那張卡片說明的是 Free＋*private* 時，REST／GraphQL 建立 Ruleset 的 API 會拒絕、只能保留期望狀態並標示 `DEGRADED`）；這個 repo 選擇公開，因此適用的是可以直接套用並驗證的那條路徑。方案或可見度之後若改變，重跑 `plan`／`apply`／`check` 就會反映最新狀態——這裡記錄的是查詢當下的事實，不是永久保證，也不代表每個使用這套公版的 repo 都跟這裡一樣。
{{< /disclosure >}}

{{< disclosure key="governance-capability" title="方案能力、啟用與升級條件" >}}
| GitHub 狀態 | 公版能做什麼 | 需要人處理什麼 |
| --- | --- | --- |
| Free＋public，或 Pro 個人＋private | 套用並檢查 repo Ruleset | 套用前先審查變更內容 |
| Free organization＋private | 套基本設定，期望 Ruleset 留在 `policies/rulesets.json` | workflow 自動輪派 reviewer 並留下審查紀錄；沒有強制合併門禁 |
| Team／Enterprise organization＋private | 確認 CODEOWNERS team 後套用並檢查 Ruleset | 組織身分、網路、稽核或不可逆變更另由 organization owner 核准 |

能力以實際證據啟用，不以預設成熟度或日期判定。Repo 可見性或方案變更後重跑 `plan`、`apply`、`check`；真的不支援就保留 `DEGRADED`，非預期的 API 或設定錯誤則停止。
{{< /disclosure >}}

{{< disclosure key="governance-plan-tiers" title="Free／Team／Enterprise 各方案完整能力" >}}
<div class="plan-grid">
  <article class="plan-card current"><h3>Free <span class="plan-state">目前</span></h3><p><strong>保留審查設定，強制能力降級：</strong><code>.github/REVIEWERS</code> 保存 reviewer 名單；private repo 只把期望 Ruleset 保留在 <code>policies/rulesets.json</code>，因為 REST 與 GraphQL 建立 API 都會拒絕。check 標示 DEGRADED。</p><ul><li><code>governance-comment.yml</code> 自動輪派一位非作者 reviewer</li><li>沒有 team request 或 merge gate，審查紀錄不能取代強制門禁</li></ul></article>
  <article class="plan-card team"><h3>Team <span class="plan-state">最低建議</span></h3><p><strong>再加上：</strong>private repo Ruleset、protected branches、強制核准、CODEOWNER 與必要檢查。</p><ul><li>同一個 CODEOWNERS team 必須存在並有 repo write access</li><li>公版即可套用現有 repo Ruleset</li></ul></article>
  <article class="plan-card enterprise"><h3>Enterprise <span class="plan-state">組織級</span></h3><p><strong>再加上：</strong>SAML SSO／SCIM、internal repo、private/internal 部署保護、私有 Pages、稽核串流與 IP 限制。</p><ul><li>組織／Enterprise Ruleset 可集中治理</li><li>目前只偵測並提示，不自動改組織設定</li></ul></article>
</div>
{{< /disclosure >}}

{{< disclosure key="governance-config" title="單一設定來源與責任層級" >}}
| 層級 | `.csarc/config.yml` key | 預設／允許值 | 產生或驗證位置 |
| --- | --- | --- | --- |
| 必要基線 | `branch_strategy` | 預設 `delivery`；可選 `delivery`、`main` | 分支指引、`policies/rulesets.json`，以及 repo-site 的交付路線段落 |
| 組織政策 | `code_owner` | 一個存在且有 repo write access 的 `@organization/team` | `.github/CODEOWNERS`；由 repository settings plan／apply／check 驗證；repo-site 的主要負責人欄位 |
| 組織政策 | `reviewers` | 一個或多個 GitHub 使用者名稱 | `.github/REVIEWERS`；`governance-comment.yml` 在每張非 draft PR 自動輪派 |
| 專案選擇 | `project_visibility` | 預設 `private`；可選 `public`、`private`、Enterprise `internal` | 能力偵測、選配安全預設，以及 repo-site 的可見受眾欄位 |
| 專案選擇 | `project_name` | 必填非空字串；預設 `CSARC Project` | repo-site 的標題與頁首 |
| 專案選擇 | `project_description` | 必填一句話用途說明，拒絕佔位文字 | repo-site 的簡介段落 |
| 專案選擇 | `languages` | 零到多個 `python`、`rust`、`typescript` | repo-site 的「使用語言」欄位 |
| 專案選擇 | `repository_url`、`project_slug` | 未覆寫時由 `code_owner`／`project_name` 推導 | repo-site 的複製（clone）指引 |
| 專案選配 | `enable_governance_drift_check` | 預設 `false`；設為 `true` 產生每日排程 Action | `false` 只保留本機 drift checker；`true` 另生成 `governance-drift.yml` |

公版 root 與生成 repo 使用同一批公開 keys 與驗證；只有生成 repo 另有 Copier `_src_path`、`_commit`。衍生公版可在同一份 YAML 增加 namespaced keys，不另建 profile。低頻 GitHub 細節留在原生 repository settings 或 `policies/`，不擴張 CSARC schema。

生成專案的 repo-site 與這個公版根網站同一套渲染引擎與元件（Issue #681），只是內容精簡許多；只從上表 key 讀取明確的 `[[key]]` token，直接對照 `.csarc/config.yml`，未知 key 會讓建置直接失敗，因此網站不會另建第二份設定 schema。上表以外的專案文字與樣式選擇，留在 `site/content/_index.zh-tw.md`、`_index.en.md`、`docs/site-theme.css`，由專案自行維護。
{{< /disclosure >}}

{{< disclosure key="governance-exceptions" title="暫時例外怎麼留下紀錄" >}}
每個例外使用一張連結的 Issue，寫明提出者、另一位核准者、到期日、證據與復原方式。只有平台確實無法提供功能，或限時事故復原時可以縮小管制；不能把未執行的檢查寫成通過、不能把高權限 token 暴露給 PR 程式，也不能默默變成永久做法。確認復原後才關單；延期必須再次明確核准。
{{< /disclosure >}}

{{< config-guidance track="governance" >}}

{{< disclosure key="governance-plan-behavior" title="GitHub 方案與 apply／check 行為對照" >}}
<aside class="selection-note"><strong>部署與例外原則</strong><span><code>plan</code> 先查帳號方案、repo 可見性、repository teams 與 Ruleset API；team 不存在、不可見或沒有 repo write access 時直接停止，不能被 Free private 的降級路徑掩蓋。能力只在 live check 證明可用後啟用，不以預設成熟度或日期判斷。Free private 不支援 team request，也無法強制核准；`governance-comment.yml` 自動輪派一位非作者 reviewer，僅提出 review request，不構成 merge gate。每個暫時例外都用 Issue 記錄提出者、另一位核准者、到期日、證據與復原方式，不能把未執行的檢查寫成通過。完整管理欄位驗證由管理員在可信任 checkout 使用 Administration read 憑證，不把 token 暴露給 PR 程式碼。GitHub 方案升級、不可逆操作與組織權限變更都需 organization owner 另案核准。</span></aside>
<table class="decision-register" aria-label="GitHub 方案與 apply／check 行為對照">
  <thead><tr><th>GitHub 方案與可見性</th><th><code>apply</code> 結果</th><th><code>check</code>／PR／CI/CD 行為</th></tr></thead>
  <tbody>
    <tr><td>Free＋public</td><td>透過 REST 套用並啟用 Ruleset</td><td>驗證 <code>main</code> 的有效規則；缺少或不符即失敗</td></tr>
    <tr><td>Free organization＋private</td><td>套用基本設定，並把期望 Ruleset 保留在 <code>policies/rulesets.json</code>；公開 API 無法建立 Ruleset</td><td>標示 <code>DEGRADED</code>；workflow 自動輪派一位個別 reviewer，team request、紅燈或未核准都不能成為 merge gate</td></tr>
    <tr><td>Pro 個人帳號＋private</td><td>套用並啟用 Ruleset</td><td>與 Free public 相同</td></tr>
    <tr><td>Team／Enterprise organization＋private</td><td>確認 CODEOWNERS team 後套用並啟用 Ruleset</td><td>必要審查、CODEOWNER 與 status checks 成為 merge gate；不符政策時 fail-closed</td></tr>
  </tbody>
</table>
<p class="reference">Ref. <a href="https://docs.github.com/en/get-started/learning-about-github/githubs-plans" target="_blank" rel="noreferrer">GitHub plans</a>；<a href="https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets" target="_blank" rel="noreferrer">About rulesets</a>. Accessed August 21, 2026.</p>
{{< /disclosure >}}
{{< /basic >}}
{{< /slide >}}

{{< slide key="template-release" track="template-release" eyebrow="步驟 09" title="Copier 保持同步，公版也吃自己的規則" subtitle="模板錯誤會一次影響多個專案，因此建立、導入與更新都要實跑。" class="candidate-slide" legacy="false" >}}
{{< standard key="template-release-mode-standard" title="公版怎麼把更新安全地帶回你的 repo" >}}
公版發布新版後，你的 repo 收到更新通知或由人工啟動；Copier（用來建立並持續更新公版的工具）先在 repo **之外**產生一份 dry-run 候選，逐一比對檔案：

<div class="plan-grid">
  <article class="plan-card current"><h3>無衝突</h3><p>更新工作樹裡對應的檔案；main 本身還沒有任何改動。</p></article>
  <article class="plan-card team"><h3>有衝突</h3><p>只列出受影響的檔案，保持你的 repo 不變；你調整後重跑一次。</p></article>
  <article class="plan-card enterprise"><h3>人審查後合併</h3><p>不管哪一種結果，都由一般 PR 走完整審查，通過才進 main——沒有任何一步會跳過審查直接改到 main。</p></article>
</div>

三個地方各自負責不同內容：`template/` 是公版下發內容的唯一來源；`.csarc/config.yml` 記錄這個專案選了什麼、目前更新到哪個版本；你的產品程式與規格則完全由你持有，公版遇到衝突一律先列出來讓你確認，不會靜默覆寫。
{{< /standard >}}

{{< ops key="template-release-mode-ops" title="單一來源、驗證流程與目前自動化邊界" >}}
- `template/` 是下發內容唯一來源；root 只因 GitHub 讀取慣例保留公版自己的治理與 dogfood 設定，配對檔案由 `scripts/sync-paired-files.sh` 從 root 產生 `template/` 副本。
- `.csarc/config.yml` 同時是 Copier 的更新紀錄與 repo 唯一的公版設定；語言、分支與選用能力都從這裡讀取，後續擴充也增加設定項目，不另建第二份設定檔。
- 新 repo 先選語言與功能，再產生可直接驗證的基線；多個語言只是合併各自元件（模組），不建立組合專屬流程。
- 既有 repo 首次導入時，先用固定 Release 與完整 SHA 的 CLI 在 repo 外產生 machine plan；dry-run 不執行 target-owned helper 或 product hook。人核准同一份未漂移的 plan 後，CLI 才在隔離候選執行驗證，通過後寫入；第一張 PR 再由人核對來源、plan、diff 與本機結果。
- 第一次導入合併後，預設分支已有可信任的 PR policy，唯讀 CI 再驗證候選內容；升級仍先用 dry-run 預覽，候選內容與衝突全部驗證完成才修改 target，若有衝突就保持 repo 不變，修正後重跑，再由一般 PR 與 trusted-base checks 審查。
- 可選的更新通知每週檢查一次；有新版只建立或更新一張 Issue，不會自動修改 repo。

{{< disclosure key="copier-update" title="Copier＋root dogfood＋建立／導入／更新回歸" >}}
[Copier](https://github.com/copier-org/copier) 記錄來源、語言與答案，能把新版公版套回可自行修改的既有 repo。首次導入先由人確認；後續更新若衝突就不修改 repo，調整後重跑，再以 PR 審查。GitHub Template 只複製一次不記得來源與答案，PyScaffold 則會形成第二套更新機制，因此都不採用。
{{< /disclosure >}}

{{< disclosure key="template-release-scope" title="單一來源、版本基線與 root-only 邊界" >}}
Root `.csarc/config.yml` 記錄公版自己選用的能力；生成 repo 另外記錄 Copier 的來源與版本，並透過 `csarc update --data` 寫回變更。模板來源不會偽造指回自己、且很快就過期的 `_src_path`／`_commit`。繼承公版可在同一份 YAML 加 namespaced 欄位，不複製 CSARC 已有設定。

`enable_template_update_notifications` 開啟時才產生 `template-update.yml` 與 `check-template-update`；公開來源不需 secret，private 來源才使用限於唯讀模板存取的 repository secret。

`scripts/sync-paired-files.sh` 讓 root 成為成對檔案的單一來源，`--check` 驗證副本內容與可執行位元。`profiles/catalog.yaml` 保存語言基線與驗收證據；Python 與 Node 基線各自觀察三十天後才前進（`profiles/catalog.yaml` 的 `stable_release_observation_days: 30`）。

`scripts/verify-template.sh` 只在公版 repo 實跑建立／導入／更新 fixture，不會下發到 consuming repository；生成 repo 使用較小的 `scripts/verify`。首次導入的 machine plan 留在 target 外，不能和待審內容一起被改寫成假證據；第一張 PR 合併後，base 才有可信任的 PR policy，唯讀 CI 再執行候選內容的驗證。
{{< /disclosure >}}

{{< disclosure key="template-release-status" title="目前自動化邊界" >}}
- **Active：**CLI 的 dry-run 只建立靜態 candidate 並把 target 當資料；核准 plan 後才在 candidate 內執行 target-owned 驗證，成功後才寫入 target。公版完整驗證的 Regression tests 階段會重跑三條路徑（含標記 `large` 的 Copier create／adopt／update 矩陣），Package smoke test 階段則另外確認 wheel 可建置、已發布的入口可從建置產物直接執行。
- **Manual：**首次導入的外部 plan、來源與第一張 PR 由人核准。
- **Pending：**通知 workflow（`template-update.yml.jinja`）與 checker script（`check-template-update`）已恢復，Copier fixture 測試也驗證只在選用時才會產生；`tests/test_template_update_notifications.py` 已涵蓋 checker 自身的更新判斷與 Issue create/edit 邏輯，包含 check-update 發生錯誤時的 fail-closed 行為，但尚未觀察到排程的 hosted 執行，因此不宣稱排程已能自動通知。
- **Retired：**remote governance 與 delivery orchestration 不隨本頁恢復；reviewer assignment 已恢復，改由「規則治理」頁說明。
{{< /disclosure >}}

{{< config-guidance track="template-release" >}}
{{< /ops >}}
{{< /slide >}}

{{< slide key="docs-site" track="docs-site" eyebrow="步驟 10" title="單檔永遠可交付" subtitle="site/content/ 的 Markdown 來源交給內建 Python 渲染引擎組出內容結構，既有 renderer 打包成可離線轉寄的單一 HTML。" class="legacy-slide decision-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <h2>單檔永遠可交付，<span class="accent">平台能力只做加成</span></h2>
        <p class="subtitle"><strong>已確認選型。</strong>單一 <code>docs/index.html</code> 檔案即可下載、轉寄與離線開啟；GitHub Pages 或其他網站託管只是額外選項，不是必要條件。</p>
      </header>
      <p class="context-line"><strong>承接上一頁｜</strong>流程與規則若只能藏在設定檔裡，團隊就難以共同理解；因此同一份 repo 也產生可分享的操作說明——你正在看的這個網站。</p>
      <p class="context-line"><strong>問題與目的｜</strong>保留特殊簡報設計與單檔交付，同時避免內容、樣式、互動、選型來源與逐字測試繼續綁在同一個人工維護檔案。</p>
      <div class="step-flow"><article class="step-flow-item"><span class="step-flow-number">1</span><h3>來源</h3><p><code>site/content/</code> 的中英文 Markdown，跟排版、程式分開存放，不用手動同步。</p></article><article class="step-flow-item"><span class="step-flow-number">2</span><h3>渲染</h3><p>內建 Python 引擎組出內容結構，不需要 Node 或額外的樣板引擎。</p></article><article class="step-flow-item"><span class="step-flow-number">3</span><h3>產出</h3><p><code>docs/index.html</code> 內嵌所有樣式、程式與圖片；每一頁固定一個畫面，桌面版不用往下捲動找重點。</p></article><article class="step-flow-item"><span class="step-flow-number">4</span><h3>使用者</h3><p>下載後用瀏覽器直接開啟就能看到完整內容；有 Pages 或其他託管只是多一個瀏覽管道，不影響離線使用。</p></article></div>
      <p class="context-line"><strong>下一步｜</strong>下載 <code>docs/index.html</code> 就能離線分享；來源結構、主題自訂與存取控制細節請切換「維運」模式查看。</p>
{{< /legacy >}}

{{< basic >}}
### 我們的選擇

- `site/content/` 是中英文 Markdown 來源；兩種語言必須有相同 content keys。
- `site/static/styles.css` 保留特殊簡報視覺；`scripts/repo_site_blocks.py` 的宣告式區塊解析器將內容轉成共用結構。
- `scripts/render_site.py` 內嵌 CSS、JavaScript、font 與圖片，拒絕外部 runtime asset。
- `./scripts/build-repo-site` 重新產生輸出；`./scripts/build-repo-site --check` 只驗證來源與版本相容性，不寫檔。

{{< disclosure key="portable-bundle" title="Markdown＋Python 渲染引擎 → self-contained HTML" >}}
`docs/adr/` 保存 canonical 選型；`scripts/build_repo_site.py` 負責內容與 HTML；未修改的 `scripts/render_site.py` 只處理資產內嵌與安全檢查。最終的 `docs/index.html` 可用 `file://` 離線開啟，不依賴 Pages、CDN 或 JavaScript package runtime。這份單一可下載 HTML 是本站的既定基準特色，不是過渡方案：即使未來加上 Pages 或其他託管，仍要保留可下載、離線可用的這份輸出。
{{< /disclosure >}}

{{< disclosure key="docs-site-access" title="存取與維護邊界" >}}
`noindex` 與 `robots.txt` 只能降低意外擴散，不是存取控制。核准 host 可保護入口，但下載後的離線 HTML 仍可能被轉寄。Agent 只把使用者已確認的 durable constraint 摘要進 Issue，再經 PR 寫入 decision record，不保存原始對話逐字稿。

renderer 讀取的是上方「規則治理」設定表核准的同一批 `.csarc/config.yml` key，不另定義第二份網站專用清單。專案文字寫在 `site/content/_index.zh-tw.md`／`_index.en.md`，樣式覆寫留在 `docs/site-theme.css`，產生的 `docs/index.html`／`docs/index.en.html` 不直接編輯。

**自訂本頁（根網站）主題（Issue #527）：**上述 `.csarc/config.yml`／`docs/site-theme.css` 是生成專案自己 repo-site 的路徑；fork 或 vendor 這份公版本身、想調整這份根 repo-site 配色的維護者，改用 `site/theme.css`。範圍嚴格限制在 `site/static/styles.css` 既有 `:root` 顏色 token，以及既有 class 的窄範圍視覺屬性，不開放新增 HTML、JavaScript 或版面配置；由一般 PR review 把關，不建立額外驗證工具。此檔一律存在、一律被引擎內嵌，預設為空白覆寫，因此預設輸出保持公版配色不變：

```css
:root {
  --yellow: #2e6b47;
}
```

編輯後執行 `./scripts/build-repo-site` 重新產生 `docs/index.html`／`docs/index.en.html`。這是排版模板結構的新增，`site/version.json` 的 `template` 版本與 `scripts/check-repo-site-versions` 的相容範圍檢查涵蓋這次擴充；詳見 `docs/adr/portable-repo-site.md` 的「根網站自訂主題」一節。
{{< /disclosure >}}

{{< disclosure key="docs-site-alternatives" title="其他常見做法" >}}
- **直接手改單檔：**可以離線，但來源、呈現與測試高度耦合。
- **runtime 多檔載入：**轉寄容易漏檔，`file://` 行為也受瀏覽器限制。
- **立刻導入文件平台：**目前沒有多頁搜尋、翻譯或跨 repo catalog 的實證需求。
- **自動保存完整聊天：**會混入未確認假設、敏感脈絡與噪音。
{{< /disclosure >}}

<aside class="config-guidance"><strong>決策與落地</strong><ul><li><strong>Canonical ADR：</strong><code>docs/adr/portable-repo-site.md</code></li><li><strong>可維護來源：</strong><code>site/</code> 分開內容、樣式、互動與原始圖片；renderer 產生 <code>docs/index.html</code> 並拒絕外部 runtime asset</li><li><strong>生成專案：</strong>公版更新 <code>site/</code> 與 renderer，專案保有 <code>site/content/_index.zh-tw.md</code>、<code>_index.en.md</code> 與 <code>docs/site-theme.css</code></li><li><strong>網站存取：</strong><code>noindex</code>／<code>robots.txt</code> 只能降低誤分享，不是登入保護；需要限制讀者時，優先評估 Cloudflare Pages＋Access，host、身分提供者、資料政策與組織 owner 另案核准</li><li><strong>追蹤：</strong><a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/79" target="_blank" rel="noreferrer">存取 #79</a>／<a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/178" target="_blank" rel="noreferrer">網站 #178</a></li></ul></aside>
{{< /basic >}}
{{< /slide >}}

{{< slide key="bridge" audience="maintainer" eyebrow="2026/05 內部分享簡報" title="回顧當時原則，對照目前實作" subtitle="回顧 2026 年 5 月內部分享的 SDLC 構想，標示目前保留、調整或延後的做法；點選每列可看三句判斷。" class="legacy-slide bridge-slide" legacy="false" >}}
      <p class="bridge-intro">這一頁用來解釋 2026/05 構想哪些被保留、調整或延後；目前操作仍以各 Journey 與現行政策文件為準。</p>
      <table class="bridge-table" aria-label="五月版簡報與目前設計的逐頁對照">
        <colgroup><col class="page-col"><col class="topic-col"><col class="status-col"><col class="decision-col"></colgroup>
        <thead><tr><th>頁次</th><th>五月版主題</th><th>結論</th><th>目前決定（點選）</th></tr></thead>
        <tbody>
          <tr><td>p.3</td><td>SDLC 核心階段</td><td><span class="bridge-status keep">保留</span></td><td><details class="bridge-detail drop-down"><summary>把計畫到監控集中在 GitHub</summary><div class="bridge-popover"><p><strong>五月版｜</strong>計畫、開發、測試、部署、監控的核心順序保留。</p><p><strong>本次判斷｜</strong>工作單、模板、合併申請、自動檢查與交付設定都放在 GitHub，方便持續維護。</p><p><strong>落地方式｜</strong>不是每個專案都要部署與監控，但都先遵守工作規劃、變更審查與驗證規則。</p></div></details></td></tr>
          <tr><td>p.4</td><td>Jira Ticket</td><td><span class="bridge-status adjust">調整</span></td><td><details class="bridge-detail drop-down"><summary>每次改動先有最小 GitHub Issue</summary><div class="bridge-popover"><p><strong>五月版｜</strong>原本用 Jira 的 Epic → Story → Task 分工；本次只保留必要的 GitHub Issue、里程碑與 spec。</p><p><strong>本次判斷｜</strong>一次性工作選一種類型、寫問題與完成條件；複雜需求先開規劃 Issue，再由核准 spec 建立實作 Issue。新增範圍另開 Issue。</p><p><strong>落地方式｜</strong><code>work-item.yml</code> 有類型、問題與完成條件兩個必填欄位，另加一個選填補充；<code>work-item-lifecycle.yml</code> 指派開單者；PR workflow 核對標籤、分支與同號未結案 Issue。</p></div></details></td></tr>
          <tr><td>p.5</td><td>版本控制</td><td><span class="bridge-status adjust">調整</span></td><td><details class="bridge-detail drop-down"><summary>delivery branch 是 CI 整合邊界，不假裝成實體環境</summary><div class="bridge-popover"><p><strong>五月版｜</strong>保留平行分支，但不要求每案具備實體 DEV 環境。</p><p><strong>本次判斷｜</strong>獨立工作從最新 <code>main</code> 建立並直接回 <code>main</code>；只有需共同驗收的里程碑使用 <code>dev/m*</code>，獨立 canary 才用暫時 <code>dev/i*</code>，hotfix 也直接修正 main。</p><p><strong>落地方式｜</strong>一般 PR 依變更風險執行必要檢查，里程碑／canary 交付與 hotfix 執行完整檢查；只在 final delivery 或明列 dependency 時同步最新 main。</p></div></details></td></tr>
          <tr><td>p.6</td><td>PR 與審查</td><td><span class="bridge-status adjust">強化</span></td><td><details class="bridge-detail drop-down"><summary>Issue、編號分支與 PR 形成固定鏈</summary><div class="bridge-popover"><p><strong>五月版｜</strong>PR 是保護分支的唯一入口，方向保留；三層審查改成依風險增加審查者。</p><p><strong>本次判斷｜</strong>一般 PR 要有同編號 Issue、CI 與一位同事；高風險架構變更另附決策紀錄。</p><p><strong>落地方式｜</strong>分支固定 <code>type/123-short-slug</code>，PR 內文固定 <code>Closes #123</code>；<code>governance-comment.yml</code> 在每張非 draft PR 自動輪派一位非作者 reviewer；GitHub Team 以上才支援 team request 與強制核准。</p></div></details></td></tr>
          <tr><td>p.7</td><td>CI 自動化管線</td><td><span class="bridge-status keep">保留</span></td><td><details class="bridge-detail drop-down"><summary>本機與 CI 共用入口，依風險分層執行</summary><div class="bridge-popover"><p><strong>五月版｜</strong>自動觸發、測試、格式與靜態錯誤檢查全部保留。</p><p><strong>本次判斷｜</strong>一般 Issue PR 跑 fast；promotion、hotfix、merge queue 與未知高風險路徑跑 full；OSV、Zizmor 與 remote governance 另依 scope／schedule 執行。</p><p><strong>落地方式｜</strong>固定 <code>verify</code> aggregate 避免 skipped workflow 留下 Pending；delivery sync 併入 <code>title</code> policy，候選 full run 不取消，普通 PR 新 commit 則取消舊 run。Ruleset 可用時強制 <code>title</code>、<code>verify</code> 與 <code>promotion</code>。</p></div></details></td></tr>
          <tr><td>p.8</td><td>CD 專案管理</td><td><span class="bridge-status adjust">調整</span></td><td><details class="bridge-detail drop-down"><summary>先完成 repository delivery，再審查版本與發版</summary><div class="bridge-popover"><p><strong>五月版｜</strong>原本預設 DEV → STAGING → Canary → PROD；本次不要求每個專案照搬四層。</p><p><strong>本次判斷｜</strong>里程碑、獨立工作與 hotfix 合併到 <code>main</code> 都先算 repository delivery；需要新版本時再建立一張可審查版本 PR。</p><p><strong>落地方式｜</strong>Release Please 同步版本與 CHANGELOG；版本 PR 合併後，單一 workflow 建立 checksum、SBOM、成品與 immutable GitHub Release。Attestation 與消費端門禁仍是選配。</p></div></details></td></tr>
          <tr><td>p.9</td><td>可觀測性</td><td><span class="bridge-status defer">第二階段</span></td><td><details class="bridge-detail"><summary>只有上線服務才做監控和值班</summary><div class="bridge-popover"><p><strong>五月版｜</strong>操作手冊、日誌、指標、追蹤、復原與值班流程保留為第二階段。</p><p><strong>本次判斷｜</strong>只對持續運行的服務導入；先依使用的雲端、環境與負責人選工具，不先綁定 Datadog 或 PagerDuty。</p><p><strong>落地方式｜</strong>測試資料另外管理成不含個資、可建立、可清除的範例，不把測資管理混成線上監控。</p></div></details></td></tr>
          <tr><td>p.10</td><td>Copilot → Agent</td><td><span class="bridge-status defer">分階段</span></td><td><details class="bridge-detail"><summary>先受控 AI 協作；成熟後再自動重試</summary><div class="bridge-popover"><p><strong>五月版｜</strong>鼓勵 AI 從補完程式進步到能執行完整任務，方向保留，但不把工程師縮減成只會下提示詞。</p><p><strong>本次判斷｜</strong>第一階段讓 Agent 依清楚工作單研究、提計畫、修改、驗證並開 PR；平行可寫任務各自使用 branch 與 Git worktree，工具便利性由 agent-kit 管理。</p><p><strong>落地方式｜</strong><code>AGENTS.md</code> 與共同驗證命令限制工作方式；<code>actions.json</code> 設定 Actions 預設唯讀且不能核准 PR，Ruleset 要求人類核准。worktree manager 不是 CI/CD，也不取得額外 secret 或合併權限。</p></div></details></td></tr>
          <tr><td>p.11</td><td>AI 初審</td><td><span class="bridge-status adjust">調整</span></td><td><details class="bridge-detail"><summary>固定工具負責判定；AI 只補充建議</summary><div class="bridge-popover"><p><strong>五月版｜</strong>AI 初審保留，但程式碼格式與常見錯誤改由 formatter、linter 與靜態檢查穩定執行。</p><p><strong>本次判斷｜</strong>AI 審查只補充情境性錯誤、測試缺口、風險摘要與修正建議，不能當成通過證明。</p><p><strong>落地方式｜</strong>CI、同事審查與指定負責人才有合併決定權；AI 沒有核准、合併或讀取密鑰的權限。</p></div></details></td></tr>
          <tr><td>p.12</td><td>AI CI/CD log</td><td><span class="bridge-status defer">第二階段</span></td><td><details class="bridge-detail"><summary>先摘要失敗；自動復原只給成熟部署</summary><div class="bridge-popover"><p><strong>五月版｜</strong>AI 可先摘要 CI 失敗紀錄；自動退版只適用於已有正式環境與可靠健康指標的部署。</p><p><strong>本次判斷｜</strong>PR 測試失敗就阻擋合併並用新提交修正，不跳過錯誤提交；若 <code>main</code> 已出問題，就用復原 PR 並建立工作單追蹤。</p><p><strong>落地方式｜</strong>只有健康指標、停止門檻、可重現復原與完整紀錄都成熟後，才考慮讓系統自動復原。</p></div></details></td></tr>
          <tr><td>p.13</td><td>AI 文件與知識庫</td><td><span class="bridge-status defer">分階段</span></td><td><details class="bridge-detail"><summary>先維護 repo 內網站；託管與 RAG 延後</summary><div class="bridge-popover"><p><strong>五月版｜</strong>文件同步方向保留；讓 AI 搜尋文件再回答（RAG）改成選配。</p><p><strong>本次判斷｜</strong>README、規格與 <code>docs/index.html</code> 都和程式一起走 PR；生成專案另有可更新版型與不被覆寫的內容檔。</p><p><strong>落地方式｜</strong>Cloudflare 託管尚未接入；網站渲染已改用內建 Python 引擎，Hugo 已於 Milestone 13（Issue #524）移除。AI 語意審查也要等模型端點與資料政策確定後才成為門禁，只有來源、owner、存取規則、引用與測試題都準備好時才做 RAG。</p></div></details></td></tr>
          <tr><td>p.14</td><td>Legacy modernization</td><td><span class="bridge-status remove">可選</span></td><td><details class="bridge-detail"><summary>舊系統改造是專案需求，不放共同模板</summary><div class="bridge-popover"><p><strong>五月版｜</strong>提到用 AI 協助舊系統現代化；本次不放進所有專案都必須使用的共同模板。</p><p><strong>本次判斷｜</strong>這是特定專案的轉型工作，做法是先用測試記錄目前行為，再小步替換、用短 PR 審查，並保留復原方法。</p><p><strong>落地方式｜</strong>有真實舊系統、風險與效益後再建立專用模板或指南，不先把空工具放進所有新案。</p></div></details></td></tr>
        </tbody>
      </table>

{{< detail key="bridge-reason" title="這次調整的實證理由" >}}
GitHub plan、repo visibility、organization policy 與 token 身分都會影響可用能力，因此使用 runtime probe 而非從方案名稱靜態猜測。分層 CI 將日常回饋與完整交付信心分開；Copier update 讓共用政策持續同步，同時保留產品內容所有權。
{{< /detail >}}

<p class="bridge-reference reference">Ref. GitHub Docs. <a href="https://docs.github.com/en/copilot/tutorials/cloud-agent/get-the-best-results" target="_blank" rel="noreferrer">AI agent practices</a>; <a href="https://docs.github.com/en/get-started/using-github/github-flow" target="_blank" rel="noreferrer">GitHub flow</a>; <a href="https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues" target="_blank" rel="noreferrer">Sub-issues</a>; <a href="https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets" target="_blank" rel="noreferrer">Rulesets</a>; <a href="https://docs.github.com/en/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site" target="_blank" rel="noreferrer">Pages visibility</a>. Accessed August 20, 2026.</p>
{{< /slide >}}

{{< slide key="similar-tools" parity="supplemental" eyebrow="相似工具" title="相似工具｜整體競品與局部參考" subtitle="標準模式先看整體目的接近的套件；維運模式可再按旅程檢查各項具體做法。這個模板直接整合的工具改列在「檔案地圖」。" class="similar-tools-slide" legacy="true" >}}
{{< similar-tools >}}
{{< /slide >}}

{{< slide key="testing" audience="maintainer" parity="supplemental" eyebrow="維運附錄｜CI/CD 設定" title="CI/CD 設定｜依步驟檢查" subtitle="分開列出一般 repo 與 repo-template 在工作 PR 與 repository delivery PR 各自需要的測試與自動化。" class="similar-tools-slide testing-slide" legacy="true" >}}
{{< testing >}}
{{< /slide >}}

{{< slide key="rollout" track="rollout" audience="archive" eyebrow="分階段導入策略" title="分階段導入，每一步都能停下來" subtitle="三層導入：基本能力現在就有，未來與可選能力先寫清楚觸發門檻。" class="legacy-slide review-notes-slide" legacy="true" >}}
<aside class="selection-note"><strong>Current state｜2026-09-03</strong><span>下方 technical view 保留原始三層導入判斷供稽核；各層現況以 <code>profiles/catalog.yaml</code> 與相關驗證腳本為準，不在此頁重複更新。</span></aside>
{{< legacy >}}
      <header>
        <h2>分階段導入，<span class="accent">每一步都能驗證，也能停下來</span></h2>
        <p class="subtitle"><strong>三層導入｜</strong>基本能力現在就隨模板產生；未來與可選能力先寫清楚觸發門檻，不用空檔案假裝完成。</p>
      </header>
      <p class="context-line"><strong>問題與目的｜</strong>一次導入模板、CI、部署、監控與 AI，團隊很難判斷哪裡出錯；分期後每一步都有完成條件。</p>
      <div class="decision-strip">
        <article class="decision-step"><span class="step-label">其他常見做法</span><h3>不按聲量或日期一次把功能全打開</h3><ul><li><strong>一次切換：</strong>錯誤會同時擴散到所有專案</li><li><strong>固定日期解鎖：</strong>時間到了不代表使用條件已成熟</li><li><strong>所有語言同時上：</strong>未驗證的 profile 只是空承諾</li></ul></article>
        <article class="decision-step recommended"><span class="step-label">我們的選擇</span><h3>三層不是日期，而是導入條件</h3><p><strong>基本導入：</strong>CI/CD-only、Python-only、TypeScript-only、混合 profile，以及 Issue／spec、PR／CI、本機驗證、OSV、依賴政策與 repo-site 已完成。Free 會先查能力並套可用設定；private repo 不宣稱有 Ruleset 強制保護。<br><strong>已完成線上驗證：</strong>release handoff、可追溯成品、Release attestation 消費端驗證，以及第一個真實 CI-only 下游 repo 的導入與 Copier 更新；共用治理與 CI-only composition 為 beta。<br><strong>仍在試行：</strong>Python、TypeScript 與混合 composition 仍各需一個真實 consuming repo 才能升為 beta。<br><strong>未來／可選：</strong>中央 catalog／治理平台、多 repo、Go／Rust、網站託管／登入、Hugo、部署、監控、RAG、自主 Agent。</p></article>
      </div>
{{< /legacy >}}

{{< basic >}}
| 導入層級 | 目前狀態 |
| --- | --- |
| 基本導入 | CI/CD-only、Python-only、TypeScript-only、混合 profile；Issue／spec、PR／CI、本機驗證、OSV、依賴政策與 repo-site 已完成 |
| 已完成線上驗證 | Release handoff、可追溯成品、Release attestation 消費端驗證，以及第一個真實 CI-only 下游 repo 的導入與 Copier update |
| 仍在試行 | Python、TypeScript 與混合 composition 各需一個真實 consuming repo 才能升為 beta |
| 未來／可選 | 中央 catalog／治理平台、多 repo、Go／Rust、網站託管／登入、部署、監控、RAG、自主 Agent |

{{< disclosure key="rollout-config" title="設定方式" >}}
- **哪些 profile 已可用或仍在規劃：** `profiles/catalog.yaml`
- **先查方案再套可用設定：** `scripts/apply-repository-settings.sh`；Ruleset／App 條件備妥後再啟用
- **建立與更新路徑是否都能通過：** `scripts/verify-template.sh`
{{< /disclosure >}}

<aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>哪些 profile 已可用或仍在規劃：</strong><code>profiles/catalog.yaml</code></li><li><strong>先查方案再套可用設定：</strong><code>scripts/apply-repository-settings.sh</code>；Ruleset／App 條件備妥後再啟用</li><li><strong>建立與更新路徑是否都能通過：</strong><code>scripts/verify-template.sh</code></li></ul></aside>
{{< /basic >}}
{{< /slide >}}

{{< slide key="access-control" audience="archive" eyebrow="存取決策" title="目前公開，存取控制仍待決策" subtitle="Repository 與 Pages 公開可讀；noindex 只降低索引，不是安全控制。" class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">決策附錄</span>
        <h2>存取控制決策｜<span class="accent">目前公開，正式方案尚未定案</span></h2>
        <p class="subtitle">本 repository 與 GitHub Pages 目前公開可讀；<code>noindex</code>／<code>robots.txt</code> 只降低搜尋引擎索引，不能限制讀取或分享。</p>
      </header>
      <div class="plan-grid">
        <article class="plan-card team"><h3>Cloudflare Pages＋Access <span class="plan-state">候選</span></h3><p><strong>成本：</strong>免費額度可覆蓋小團隊登入牆；設定 Zero Trust 政策、網域與 DNS。<strong>限制：</strong>需要另建 Cloudflare 帳號與組織身分整合（Google／GitHub SSO 或 email OTP），資料與稽核政策需先確認。<strong>持有者：</strong>需組織 owner 建立並持有 Cloudflare 帳號權限，本 Issue 不建立或設定。</p></article>
        <article class="plan-card enterprise"><h3>GitHub Pages＋IP 限制 <span class="plan-state">受限</span></h3><p><strong>成本：</strong>沿用既有 GitHub 組織，不需另一個外部帳號。<strong>限制：</strong>私有 Pages 網站限定 GitHub Enterprise Cloud；IP allow list 對遠端／混合團隊不易維護，且組織目前是 Free plan，尚未具備此能力。<strong>持有者：</strong>需組織 owner 先升級方案，才能設定 Enterprise 網路政策。</p></article>
        <article class="plan-card current"><h3>內部登入平台（Backstage／Confluence 等） <span class="plan-state">未來</span></h3><p><strong>成本：</strong>可與既有身分系統（SSO）整合，統一管理多份內部文件，不只這一頁。<strong>限制：</strong>需要另外導入與維運一套平台，目前只有一份 repo-site，導入成本大於效益。<strong>持有者：</strong>需 IT／平台團隊建立與維運，屬於未來、服務變多才評估的選項。</p></article>
      </div>
      <aside class="selection-note"><strong>目前決定</strong><span>本 repository 與 Pages 維持公開，不把 <code>noindex</code>／<code>robots.txt</code> 說成存取控制；#79 保留過渡紀錄，Cloudflare Pages＋Access、改回 private 或升級 GitHub 方案的取捨留在 #425。任何方案定案後，仍需另開實作用 Issue 並由組織 owner 核准。</span></aside>
{{< /legacy >}}

{{< basic >}}
| 方案 | 成本與優點 | 目前限制／持有者 |
| --- | --- | --- |
| Cloudflare Pages＋Access | 免費額度可提供小團隊登入牆 | 需組織 owner 建立 Cloudflare、網域、DNS 與 SSO／OTP 政策 |
| GitHub Pages＋IP 限制 | 沿用 GitHub 組織 | Private Pages 與 IP allow list 需 Enterprise Cloud；目前 Free 不可用 |
| Backstage／Confluence 等登入平台 | 可統一管理多份內部文件 | 現在只有一份網站，需 IT／平台團隊導入維運，成本高於效益 |

{{< disclosure key="access-control-limit" title="目前已做與仍然做不到的事" >}}
`docs/index.html` 內有 `noindex,nofollow`，`docs/robots.txt` 也拒絕 crawler，但 repository 與 GitHub Pages 仍公開可讀。這些都不是 authentication；任何人仍可讀取、下載或轉寄內容。Issue #79 保留過渡紀錄，正式 host、身分提供者、資料與稽核政策由 Issue #425 規劃。若未來改回 private，須先盤點公開期間的 Issue、PR 與 commit；敏感資訊另依安全事件流程處理，不能把改 visibility 當成清除外洩。
{{< /disclosure >}}

<aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>目前狀態：</strong><code>.csarc/config.yml</code> 記錄 <code>project_visibility: public</code>，<code>policies/pages.json</code> 維持由 <code>main:/docs</code> 發布</li><li><strong>索引偏好：</strong><code>docs/index.html</code> 的 <code>&lt;meta name="robots"&gt;</code>＋<code>docs/robots.txt</code>，不構成存取控制</li><li><strong>決策記錄：</strong><a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/79" target="_blank" rel="noreferrer">Issue #79</a>（過渡紀錄）／<a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/425" target="_blank" rel="noreferrer">Issue #425</a>（現行 hosting／access-control 規劃）</li></ul></aside>
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
{{< /legacy >}}

{{< basic >}}
| 審閱問題 | 目前決定 |
| --- | --- |
| Free private 的 `main` 保護 | 保存 Ruleset policy 並回報 `DEGRADED`，不宣稱已有 merge gate |
| 工作範圍 | Issue-first；新增需求超出完成條件就另開 Issue |
| 公版更新邊界 | `template/` 下發基礎設施；Copier 保護產品程式與規格 |
| 語言品質 | Python 用 src layout、uv、Ruff、ty、pytest；Rust 用 rustfmt、Clippy、Cargo；TypeScript 用 Node 24、pnpm 11、Biome、Vitest |
| CI 與版本 | 本機／CI 共用入口；一般工作依風險分級、Milestone／canary 交付 full；精確版本與 CHANGELOG 人工同步 |
| 供應鏈 | 等待、OSV、hash、SBOM 與 resolver 各解決不同問題 |
| AI 與文件 | `AGENTS.md` 是工作契約；README 與網站服務人類 |
| 驗證資源 | 只用本機暫存專案或本 repo，不為測試另開 GitHub repository |

{{< disclosure key="principles-transcript" title="決策如何留下來" >}}
Agent 不保存原始聊天。只有使用者已確認的 durable architecture、security、compatibility 或 platform constraint，才先摘要進 Issue，再透過有範圍的 PR 更新 `docs/adr/` 或 `docs/decisions/`。細節以可執行設定為準，條件改變時由 Issue／PR 同步修正。
{{< /disclosure >}}

<p class="review-note-footer"><strong>驗證承諾：</strong><code>./scripts/verify-template.sh</code> 會實跑新案、既有案導入，以及同一個已導入 repo 的 Copier 更新與更新後完整驗證；這支 root-only 腳本不會下發。</p>
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
          <tr><td><a href="https://docs.github.com/en/actions/concepts/security/artifact-attestations" target="_blank" rel="noreferrer">Artifact Attestations</a>＋<a href="https://slsa.dev/spec/v1.2/build-track-basics" target="_blank" rel="noreferrer">SLSA Build</a></td><td><span class="tier-chip partial">產品擴充</span></td><td>公版目前以 immutable GitHub Release、checksum、SBOM 與消費端驗證作共同基線；需要 registry 或 artifact attestation 的產品，應另案建立真實 publisher、OIDC 信任與驗證，不只提供無執行者的設定開關。</td></tr>
          <tr><td><a href="https://github.com/ossf/scorecard" target="_blank" rel="noreferrer">OpenSSF Scorecard</a> 安全基線</td><td><span class="tier-chip optional">方案感知</span></td><td>已有 pinned Actions、OSV、<code>SECURITY.md</code>、完整 Git 歷史與工作樹 secret scan；public repo 預設啟用 CodeQL，private／internal 則依 GitHub Code Security 授權明確 opt-in。</td></tr>
          <tr><td>真實 consuming repo 與採用證據</td><td><span class="tier-chip best">共用生命週期已證明</span></td><td><code>ai-guardrail</code> 已透過 Issue、兩支 PR 完成 v0.2.4 導入、產品客製化保留、v0.3.1 Copier update 與兩次完整線上檢查；Python、Rust 與 TypeScript 另有各自可執行的 beta 驗收證據。→ <a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/100" target="_blank" rel="noreferrer">#100</a>／<a href="pilot-adoption.md">證據</a></td></tr>
        </tbody>
      </table>
{{< /legacy >}}

{{< basic >}}
| 外部基準／實測 | 判斷 | 目前證據與邊界 |
| --- | --- | --- |
| Copier vs projen | 選擇合適 | 需求是產生後可修改又能更新，Copier smart update 較合適 |
| Spotify Golden Path／Backstage | 只完成一段 | 現在是單 repo 公版，不是跨團隊 catalog 平台 |
| Allstar／Safe Settings | 目前夠用 | 已有排程 drift check；fleet 變大後再評估中央 enforcement |
| GitHub Rulesets／Free private | 部分解決 | 可偵測並告警，方案仍不能強制 Ruleset |
| 歷史 Release Please runs | 只保留封存證據 | 舊 run 證明的是已退役的兩段式設計；現行單一 workflow 與安全邊界以 release ADR 為準 |
| OSV reusable workflow | 已修正 | 權限傳遞修正後已有成功 main run |
| Artifact Attestations／SLSA | Conditional contract | 本機測試保留 repository、tag、digest 與 signer 核對；目前沒有 active consumer workflow |
| OpenSSF Scorecard | 方案感知 | public 預設 CodeQL；private/internal 依授權 opt-in |
| 真實 consuming repo | 共用生命週期已證明 | `ai-guardrail` 已完成 v0.2.4 導入與 v0.3.1 update；語言模組另有可執行 beta 證據 |

{{< disclosure key="benchmark-gap" title="現階段缺口" >}}
沒有跨 repo catalog、全面託管治理、registry publisher 或通用部署平台。歷史 live-integration run 只保留為稽核證據；現行能力必須同時有 `.github/workflows/` 內的 active file 與近期 run。真實產品 repo 繼續累積營運證據，但不作為一次性的語言測試 fixture。
{{< /disclosure >}}

<p class="review-note-footer"><strong>簡潔度判斷：</strong>Copier＋GitHub Actions＋標準工具的方向夠簡潔；真實 CI-only pilot 已補上共用生命週期的線上證據。root-only <code>Live integration smoke</code> 持續驗證 OSV、Release Please、release handoff 與 governance drift；語言模組則由各自的可重現測試維持 beta。</p>
{{< /basic >}}
{{< /slide >}}

{{< slide key="fleet-inventory" audience="archive" eyebrow="Fleet 治理" title="本機查詢採用盤點，不對外公開清單" subtitle="這個 repository 與頁面公開可讀，因此不在靜態內容列出可能含 private repository 的 fleet 清單。" class="legacy-slide review-notes-slide" legacy="true" >}}
{{< legacy >}}
      <header>
        <span class="selection-sequence">決策附錄</span>
        <h2>Fleet 治理盤點｜<span class="accent">本機查詢，不對外公開</span></h2>
        <p class="subtitle">這個模板 repository 與 repo-site 公開可讀；真實 fleet 清單可能包含 private repository，因此不寫進網站內容或 git 歷史。維護者改用 <code>scripts/audit-fleet-adoption</code> 在本機即時查詢、即時計算、只印在終端機。</p>
      </header>
      <table class="decision-register audit-register" aria-label="Fleet 盤點評估方式">
        <thead><tr><th>評估項目</th><th>取得方式</th></tr></thead>
        <tbody>
          <tr><td>Repository 清單</td><td>對真實組織執行 <code>gh repo list</code>，不寫入網站內容或 git 歷史</td></tr>
          <tr><td>CODEOWNERS 覆蓋率</td><td>逐一以 <code>gh api</code> 檢查 <code>.github/CODEOWNERS</code> 是否存在</td></tr>
          <tr><td>Copier 採用狀態</td><td>逐一以 <code>gh api</code> 檢查 <code>.csarc/config.yml</code> 是否存在；來源模板 repo 因為對自己跑過 Copier 也會有這個檔案，會被排除，不計為 consuming repo</td></tr>
          <tr><td>門檻比對</td><td>對照 <code>fleet-governance-thresholds</code> 頁面既有的量化門檻計算</td></tr>
        </tbody>
      </table>
      <aside class="selection-note"><strong>執行方式</strong><span>維護者在本機執行 <code>./scripts/audit-fleet-adoption</code> 重現這次評估：腳本即時查詢組織、計算是否達到 catalog 與 policy enforcement 門檻，只印在標準輸出——不寫入任何檔案、不建立 cache 或 artifact、不上傳到任何地方，真實 repository 清單不會留在這個網站或它的歷史裡。</span></aside>
{{< /legacy >}}

{{< basic >}}
| 評估項目 | 取得方式 |
| --- | --- |
| Repository 清單 | 對真實組織執行 `gh repo list`，不寫入網站內容或 git 歷史 |
| CODEOWNERS 覆蓋率 | 逐一以 `gh api` 檢查 `.github/CODEOWNERS` 是否存在 |
| Copier 採用狀態 | 逐一以 `gh api` 檢查 `.csarc/config.yml` 是否存在；來源模板 repo 會被排除，不計為 consuming repo |
| 門檻比對 | 對照 `fleet-governance-thresholds` 頁面既有的量化門檻計算 |

維護者在本機執行 `./scripts/audit-fleet-adoption` 重現這次評估：腳本即時查詢組織、計算是否達到 catalog 與 policy enforcement 門檻，只印在標準輸出——不寫入任何檔案、不建立 cache 或 artifact、不上傳到任何地方，真實 repository 清單不會留在這個網站或它的歷史裡。

{{< disclosure key="fleet-inventory-source" title="盤點證據與判讀方式" >}}
腳本即時讀取 GitHub repositories、CODEOWNERS 是否存在、`.csarc/config.yml` 採用標記；沒有完成排程樣本的 repo 不記為「零漂移」。新 pilot 與每季回顧都重新執行，每次印出的結果只反映當下狀態，執行結束後不留下任何紀錄。
{{< /disclosure >}}

<p class="bridge-reference reference">盤點方法：GitHub repositories、CODEOWNERS、Copier 採用標記，透過 <code>gh api</code>／<code>gh repo list</code> 即時查詢。</p>
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
{{< /legacy >}}

{{< basic >}}
| 需求 | 開始評估的量化門檻 |
| --- | --- |
| Catalog／Backstage | 10 個活躍 consuming repos；或至少 3 個，且 90 天內有 2 次 owner／服務查找超過 30 分鐘的 Issue 記錄 |
| 中央 policy enforcement | 至少 5 個 consuming repos，且同類 drift 30 天內出現在 2+ repos；或連續兩版有 20%+ update PR 超過 5 個工作天；或每月人工修正超過 2 小時 |

{{< disclosure key="fleet-thresholds-yagni" title="觸發後仍需具備的條件" >}}
觸發後另開 Issue，指定平台 owner、成本上限、試行範圍與退場條件。Backstage 管 catalog／owner／系統關係；Allstar 或 Safe Settings 才處理持續政策檢查與設定下發，兩者不能互相取代。目前維持 Copier、JSON policy、GitHub API 與 daily drift check，不預建外部服務。
{{< /disclosure >}}

<aside class="config-guidance"><strong>重新評估</strong><ul><li>每季與每次新增 pilot 後，以 GitHub API 重點數 answers／profile、CODEOWNERS、未完成 update PR 與 governance-drift runs。</li><li>漂移頻率只計「有完成排程樣本」的 consuming repo；沒有 run 不記為零漂移。</li><li>觸發後另開 Issue，指定平台 owner、成本上限、試行範圍與退場條件；本決策不授權建置外部服務。</li></ul></aside>
<p class="bridge-reference reference">Ref. <a href="https://backstage.io/docs/features/software-catalog/" target="_blank" rel="noreferrer">Backstage Software Catalog</a>; <a href="https://github.com/ossf/allstar" target="_blank" rel="noreferrer">OpenSSF Allstar</a>; <a href="https://github.com/github-community-projects/safe-settings" target="_blank" rel="noreferrer">GitHub Safe Settings</a>. Accessed August 24, 2026.</p>
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
{{< /legacy >}}

{{< basic >}}
| 選項 | 現況 |
| --- | --- |
| 現行 `docs/specs/*.md` | Front matter 記錄 ID、優先度、狀態與選用 tracking；marker 可重跑同步 Issue 或里程碑 |
| GitHub Spec Kit | `/specify → /plan → /tasks → /implement`，需額外 CLI 與支援的 AI 工具，沒有內建一份 spec 對一張 Issue 的同步 |

{{< disclosure key="spec-format-cost" title="目前不遷移的理由與重新評估條件" >}}
改採 Spec Kit 需重寫 `scripts/spec_to_issue.py`、轉換既有 specs、更新驗證斷言，並另行設計等價 Issue sync；雙格式則增加認知與維護負擔。當核准規格經常需要由 AI 穩定拆成多張子工作，且團隊願意維護額外 CLI／Agent 流程時再評估。Issue #77 已結案並記錄此決定；如需重新評估，請另開新 Issue。
{{< /disclosure >}}

<aside class="config-guidance"><strong>設定方式</strong><ul><li><strong>現行 spec 格式與驗證：</strong><code>docs/specs/*.md</code>＋<code>scripts/spec_to_issue.py</code></li><li><strong>決策記錄：</strong><a href="https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/77" target="_blank" rel="noreferrer">Issue #77</a>（已結案，決定維持現行格式）</li></ul></aside>
{{< /basic >}}
{{< /slide >}}

{{< slide key="governance-audit-trail" audience="archive" parity="new" eyebrow="治理稽核" title="稽核軌跡：呈現機制與資料新鮮度" subtitle="稽核軌跡模組即時查詢 GitHub；這個靜態網站只說明輸出結構與如何重新產生，不嵌入任何即時或先前產生的資料列。" class="legacy-slide review-notes-slide" legacy="true" >}}
{{< audit-trail >}}
{{< /slide >}}
