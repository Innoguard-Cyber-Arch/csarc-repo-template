# Portable decision site architecture ADR

- **狀態：**Accepted
- **日期：**2026-08-24
- **來源 Issues：**[Issue #177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/177)、[Issue #178](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/178)
- **實作 PRs：**[#185](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/185)、[#187](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/187)

## 問題與限制

使用者不一定能啟用 GitHub Pages、建立外部託管帳號，或取得 organization／enterprise 管理權。內部決策網站同時需要保留特殊簡報設計、支援討論與交付，而且下載後仍能離線開啟。因此 Pages、CDN、web font、外部 JavaScript 與分離圖片都不能成為 portable baseline。

原本 root `docs/index.html` 把內容、樣式、互動與決策來源放在同一檔案；Copier 下發網站則在 runtime 載入 `docs/site-content.js`，讓非前端維護者必須編輯 JavaScript。現在 root 由 Hugo 讀取雙語 Markdown，生成專案則由輕量 renderer 讀取 `docs/site-content.md`；兩者都從 repository 內來源重建同一路徑的單檔交付物。

聊天也不是 repository source of truth。現有 Spec → Issue 流程不會擷取對話；若無條件保存完整逐字稿，會把未確認假設、敏感脈絡與噪音寫進版本歷史。

## 決定

採用「repository 內可維護來源 → 可重現的 self-contained HTML」：

1. `docs/index.html` 與 `docs/index.en.html` 保持已提交、可直接傳送、可用 `file://` 開啟的單檔交付物；CSS、JavaScript、font、SVG 與 raster images 全部內嵌。
2. 編輯來源與 bundled output 分離。`site/content/` 維護中英文 Markdown，`site/layouts/` 維護 Hugo 結構，`site/static/` 維護樣式、互動與媒體；`scripts/build-decision-site` 先由 Hugo 建置到 `dist/`，再沿用 `scripts/render_site.py` 產生交付檔。生成檔不是擴充點，也不直接手改。
3. 採用固定版本的 Hugo 空白畫布模板，不導入 Docusaurus、Backstage 或另一套前端 runtime。Hugo 只負責編譯，交付物仍維持單檔、離線、零外部 runtime 依賴。
4. canonical Architecture Decision Records（ADR）放在 `docs/adr/`。簡報呈現決策摘要與連結，但不再是唯一可編輯來源；runbook、實證與 spec 各自維持不同生命週期。
5. root 與 Copier 下發專案遵守相同 portable contract，但可以有不同 presentation layout。共用設計基礎由公版維護，root 可以增加 deck-specific 呈現，生成專案則使用 handbook layout。

## 2026-09-01 生成專案改用 Markdown

Issue #436 將生成專案的內容來源從 JavaScript object 改為 `docs/site-content.md`。renderer 只支援標題、段落、清單、粗體、連結與程式碼等文件需要的 Markdown 子集，不加入前端框架或 runtime dependency；二級標題建立導覽，三級標題收納進階內容。

Markdown 中的明確 `[[key]]` token 直接從 `.csarc/config.yml` 讀取；未知 key 會停止建置。這讓名稱、說明、語言、負責人與分支策略維持同一設定來源，同時讓其餘專案文字仍可由 consuming repository 直接編輯。

## 2026-09-02 內部網站設定與「規則治理」核准清單對齊

Issue #436 盤點時發現：內部網站（`docs/site-content.md` 生成的手冊）已經在讀 `project_name`、`project_description`、`languages`、`repository_url`、`project_slug` 等 `.csarc/config.yml` key，但「規則治理」頁的 `governance-config` 核准清單只列出 `branch_strategy`、`code_owner`、`reviewers`、`project_visibility`、`enable_governance_drift_check`，兩邊已經走樣。Issue #474 把這些既有、已被消費、卻未核准登記的 key 一併補進同一份 `governance-config` 表格，不建立第二份平行 schema；`branch_strategy` 的 delivery／main 分流本來就已經切換手冊內容（標準／維運模式切換），只是先前沒有對應測試證明。

`project_visibility`（可見受眾）原本已核准卻完全沒被內部網站讀取；本次在 `template/docs/site-content.md.jinja` 的「責任邊界」段落加入 `[[project_visibility]]`，讓手冊明確標示目前設定的儲存庫可見度。「規則治理」與「內部網站」（`docs-site-access`）兩處說明過去各自重複列出同一批 key，現在只有 `governance-config` 表格是唯一列表，`docs-site-access` 改為指回該表格，避免兩份定義各自漂移；`tests/test_render_site.py` 的 `test_internal_site_keys_are_documented_once` 把這個「只定義一次」的要求變成可執行的回歸測試。

## 2026-08-25 Hugo 正式切換

Issue #205 以兩次真實 spike 重新檢查第 3 點。mdBook 的書本導覽與現有卡片式簡報衝突；Hugo 0.165.0 的自訂單頁 output format 則能保留既有視覺，並把輸出直接交給未修改的 `scripts/render_site.py`。因此只局部取代「不導入 Hugo」的限制，保留單檔、離線 `file://`、零外部 runtime asset 與 checked-in output 的全部契約。

Issue #209 經維護者實際檢視後，Hugo source 收斂到通用的 `site/` 結構，正式取代手寫 `site/index.html`，並輸出 `docs/index.html` 與 `docs/index.en.html`。Hugo publish directory 固定在已忽略的 `dist/`，不會掃描或覆寫 `docs/adr/`、`docs/specs/` 與其他既有文件。舊頁移到 `site/legacy/index.html`，只作文字、圖片與視覺回歸基準；仍被基準頁引用的樣式、互動與資產保留在 `site/static/`，確認不再使用後才移除。

## 2026-09-03 移除 Hugo，改用純 Python 渲染引擎

Issue #524 重新檢視「頁面呈現架構」「首頁重做」「自訂排版模板」三個後續 Issue 共同依賴的最底層基礎設施。維護者判斷：Hugo 太重、太通用，不符合「輕量、單純、簡報感」的產品定位；下游使用者應該只需要維護 Markdown 內容與選色，不需要理解一套通用靜態網站產生器。本節取代（supersede）上一節「2026-08-25 Hugo 正式切換」——Hugo 不再是本模板採用的 renderer。

**決定**：`scripts/build_decision_site.py` 是新的 renderer，僅用 Python 標準函式庫（`re`、`json`、`tomllib`、`pathlib`、`html`），不引入 Node、Markdown 套件或樣板引擎。`site/content/_index.{zh-tw,en}.md` 既有的 `{{< slide key="..." >}}...{{< /slide >}}` 區塊語法完全不變；新引擎（搭配共用的 `scripts/decision_site_blocks.py` 解析器）把原本 `site/layouts/` 下的每個 Hugo shortcode／partial／home layout 逐一改寫成讀取同一批 `site/data/*.json`／`*.toml` 的 Python 函式。新引擎的輸出（`dist/decision-site/` 下的雙語 pre-bundle HTML）交給 `scripts/render_site.py` 的 `render()`——完全未修改——內嵌資產並拒絕外部 runtime asset，這正是本 ADR「未修改的 renderer 只負責資產內嵌」約束的字面實作，延續不變。`scripts/install-hugo`、`site/hugo.toml`、`site/layouts/` 已刪除。

**Mermaid**：新引擎支援 ` ```mermaid ` fenced code block，輸出 `<pre class="mermaid">` 加一段簡短的本地 boot `<script>`；圖表函式庫本身以固定版本形式 vendor 在 `site/static/vendor/mermaid.min.js`（記錄來源網址與 SHA256），只在頁面真的包含 mermaid 區塊時才引用，其餘頁面零成本。

**版本**：新增 `site/version.json` 記錄渲染引擎（`engine`）與排版模板（`template`）各自獨立的版本號，以及引擎相容的模板版本範圍（`compatible_template_range`），不跟著 repo／CLI 整體 SemVer 走；`scripts/check-decision-site-versions` 驗證版本落在相容範圍內，fail closed。

**內容一致性**：切換前後以「拆解 HTML 標籤、正規化空白後比對逐頁可見文字」與「id／href／data-track／data-audience／data-content-key／aria-controls 屬性值集合」兩種方式核對雙語輸出，兩者皆完全相符。英文頁逐頁文字位元組相同；中文頁有 5 個投影片的差異，經追查是 Hugo 的 goldmark／CommonMark flanking-rule 對「`**標籤：**` 後緊接全形冒號與中文字、無空白」的既有排版寫法留下未轉換的字面 `**...**`（既有 bug，非本次引入）——新引擎改用簡單的正則比對兩個 `**` 之間任意字元，正確轉成 `<strong>`，等於順帶修正了這個既有渲染缺陷。`llms.txt` 與 `docs/llms.txt` 逐位元組相同。

**測試**：`tests/test_build_decision_site.py` 對每個渲染函式做 fixture 單元測試（不需要 Hugo、Node 或瀏覽器自動化），並涵蓋 config-guidance 的多行程式碼樣本換行保留、similar-tools 的排序邏輯與 mermaid 區塊的條件式輸出；原本需要實跑 Hugo 才能驗證的 `tests/test_config_guidance.py` 端對端測試已改用新引擎直接驗證，移除 Hugo 相依。

## 2026-09-03 根網站自訂主題（Issue #527）

Issue #527 要求：在 #524 讓渲染引擎與排版模板各自獨立版本、可替換之後，讓維護這個 repository 自己（fork 或 vendor 這份公版，不是 Copier 下發的生成專案）內部決策網站的人，能不 fork 引擎或版面邏輯就換一套顏色主題。原則維持「盡可能簡單」：只開放顏色與既有區塊的窄範圍視覺覆寫，不開放任意 CSS／HTML。

**機制**：新增 `site/theme.css`，與生成專案既有的 `docs/site-theme.css`（`template/docs/site-theme.css.jinja`）同一套設計、不同路徑——因為根網站與生成專案的 handbook 是兩套不同 renderer（見上方「Ownership 與更新」與 2026-09-03 節）。`scripts/build_decision_site.py` 在 `<head>` 固定多輸出一個 `<link rel="stylesheet" href="../../site/theme.css">`（在 `site/static/styles.css` 之後，讓 CSS cascade 覆寫生效），`scripts/render_site.py` 既有的 stylesheet 內嵌步驟原樣處理它，不需要修改。此檔一律存在（committed，預設空白 `:root {}` 加說明註解），因此預設輸出的 `docs/index.html`／`docs/index.en.html` 不變；有需要時直接覆寫 `site/static/styles.css` 的 `:root` token 或既有 class 的顏色屬性即可，範圍與界線寫在檔案自己的開頭註解裡，由一般 PR review 把關，不另建驗證工具。

**不採用 `.csarc/config.yml`**：`scripts/build_decision_site.py` 已明確記載根網站內容不吃 `.csarc/config.yml`（該檔案是 repository 治理設定，`[[key]]` token 機制服務的是生成專案的 `docs/site-content.md`）。用 YAML 顏色鍵值再轉譯成 CSS 會是第二套主題機制，與既有 `site/static/styles.css` 的 CSS custom properties 重複；因此選擇同一種 CSS 覆寫檔案格式，只是換一個 repo 內路徑。

**版本**：這是排版模板結構契約的新增（一個一律存在、一律被 link 的新檔案），`site/version.json` 的 `engine`／`template` 由 `1.0.0` 一併調整為 `1.1.0`，仍落在既有 `compatible_template_range`（`>=1.0.0 <2.0.0`）內，`scripts/check-decision-site-versions` 驗證通過。

**驗證**：`tests/test_build_decision_site.py` 覆蓋 `render_page()` 一律輸出 `site/theme.css` 的 stylesheet link，以及一筆全流程 fixture（`build()` 接 `render()`）證明實際覆寫的 token 值會出現在最終內嵌後的 bundle 裡。手動以真實內容執行 `./scripts/build-decision-site`，先確認預設（空白覆寫）與既有輸出一致，再暫時填入一個顏色覆寫、重新產生、瀏覽器開啟確認生效，最後還原。

## Ownership 與更新

| 內容 | Owner | Copier update 行為 |
| --- | --- | --- |
| Renderer、基礎設計 tokens、共用元件與驗證 | 公版 | 隨公版更新，產生可審查差異 |
| `docs/site-content.md` 與允許的 theme overrides | consuming project | 首次建立後保留，不靜默覆寫 |
| `site/theme.css`（root 網站自己的顏色／窄範圍區塊覆寫，Issue #527） | 這個 repository 的 fork／vendor 者 | 不經 Copier；root 本身預設保持空白，git 層面的分歧與合併由各自的 fork 自行處理 |
| `docs/index.html`、`docs/index.en.html` | renderer output | 由來源重建；CI 驗證沒有 stale 或人工修改 |
| Decision records、specs 與產品實證 | owning repository | 專案擁有；公版只提供結構與規則 |

舊版 `docs/site-content.js` 的 `schemaVersion: 1` 仍可由 renderer 驗證，供更新中的 repository 辨識舊來源；新內容不再建立 JavaScript schema。更新時舊檔保持原樣，產物顯示遷移提示，直到維護者把要保留的文字移入 Markdown 並自行刪除舊檔；不能靠模板靜默覆寫 project-owned content。

## GitHub capability matrix

平台方案只增加自動化，不改變最低交付保證。實際選擇依可觀察能力判斷為 `allowed`、`blocked` 或 `unknown`，不能只看方案名稱推測。

| 可用能力 | 行為 | 保證、限制與 fallback |
| --- | --- | --- |
| 無 Actions／Pages 或能力 unknown | 本機產生並提交 `docs/index.html` | 單檔可離線交付；PR diff 與本機驗證仍可審查，不宣稱已部署 |
| Actions allowed | 重建、比對 committed bundle，並上傳 workflow artifact | stale output 或外部 runtime asset 使 check 失敗；artifact 不是公開網站 |
| 核准的 Pages／內部 host 與寫入權限 allowed | 在相同 bundle 上增加 preview／publish | 發布失敗時回退 artifact／committed bundle，不降低內容驗證 |
| Ruleset、CODEOWNERS、environment 或 organization controls allowed | 將文件 check、指定審查與部署核准變成強制門禁 | 未支援時明確標示 DEGRADED；不能假裝較高階控制已生效 |

`noindex` 與 `robots.txt` 不是存取控制。即使較高方案提供登入、IP 限制或受控發布，離線檔案一旦下載仍可能被轉寄；簡報必須持續標示資料邊界。

## 互動決策收納

不自動保存聊天逐字稿。Agent 遇到 durable constraint 或 trade-off 時執行下列流程：

1. 搜尋 `docs/adr/`、open／closed Issues、comments 與 linked pull requests。
2. 區分使用者已確認決策、仍在比較的選項與 agent 推論。
3. 將已確認內容摘要到既有或新 Issue，記錄先前決策是沿用、取代或駁回及理由。
4. 經使用者授權後，以該 Issue 的 PR 更新 canonical decision record；若簡報需要呈現，再由同一變更更新或重建 bundle。
5. CI 只驗證結構、來源同步與交付契約；不能把沒有人工確認的模型輸出升格成決策。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 繼續直接維護單一 HTML | 保留交付形式但不採用作為長期 source；內容、樣式、互動與 exact-string tests 已高度耦合 |
| runtime 載入 CSS／JavaScript／圖片 | 不採用；離線轉寄時容易遺漏檔案，且 `file://` 行為受瀏覽器限制 |
| 立即導入完整文件平台 | 暫緩；增加依賴、建置與主題維護，但目前沒有多頁搜尋或跨 repo catalog 的實證需求 |
| 只部署 Pages、不提交 bundle | 不採用；把高階平台能力錯當最低需求，無法服務受限方案或離線討論 |
| 自動保存完整聊天 | 不採用；包含噪音、未確認假設與可能的敏感資訊，也缺少可審查的決策邊界 |

## 相近模板與文件實務

以下比較的是 2026-08-24 可見的 repository 結構，不代表直接採用其完整工具鏈：

| 參考 | 可借鑑做法 | 本公版的取捨 |
| --- | --- | --- |
| [GitHub Spec Kit](https://github.com/github/spec-kit) | 將 constitution、spec／plan／tasks 與生成模板分開，讓 agent 讀取穩定的專案原則與工作產物 | 採用 durable source 與工作產物分離；不導入其完整指令流程 |
| [OpenSpec](https://github.com/Fission-AI/OpenSpec) | 區分目前有效的 specs、提案中的 changes 與 archive，避免討論稿和現況混為一談 | 採用「已確認 decision」與「Issue 中待決內容」分離；保留現有輕量 spec → Issue 流程 |
| [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD) | 將使用文件、agent／workflow 資產與安裝產物分層，文件本身使用任務導向結構 | 採用清楚的 owner 與閱讀入口；不複製其角色或大型流程框架 |
| [GitHub starter workflows](https://github.com/actions/starter-workflows) | 可執行 workflow 與描述／呈現 metadata 分檔維護，再由平台組合 | 採用 source／presentation 分離與機器驗證，不讓產物成為唯一來源 |
| [Backstage TechDocs](https://backstage.io/docs/features/techdocs/) | docs-as-code，從 repository source 建置並可集中發佈與搜尋 | 保留作為多 repo catalog 的升級路徑；目前因需額外平台與託管而不作 baseline |

共同模式是把可審查的文字來源、模板／workflow 資產與發布產物分開。本公版額外受限於「收件者可能沒有託管能力」，因此把最後產物收斂成 repository 內已提交的單一 HTML，而不是把網站服務當成交付前提。

## 驗證契約

後續 renderer 實作至少驗證：

- 從 repository 來源重建 `docs/index.html` 後逐位元組一致。
- HTML 不含 runtime 外部 stylesheet、script、font 或 image；外部超連結可以存在。
- `file://` 開啟時簡報內容、鍵盤操作與內嵌媒體可用。
- 常用窄螢幕與簡報尺寸維持可讀；不為此先加入大型視覺測試平台。
- Copier create／adopt／update fixture 證明模板檔可更新、project-owned Markdown 與 overrides 保留，且未知設定 key、舊 schema 不相容時 fail closed。

## 重新評估條件

只有出現多頁搜尋、翻譯、跨 repo owner／服務探索反覆耗時，或現有 renderer 已有可量測的維護失敗時，才評估 MkDocs、Backstage TechDocs 或其他文件平台。較高 GitHub 方案可讓發布更自動化，但不能移除 self-contained bundle。
