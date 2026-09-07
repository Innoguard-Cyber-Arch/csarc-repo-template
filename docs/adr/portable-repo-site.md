# Portable repo-site architecture ADR

- **狀態：**Accepted
- **日期：**2026-08-24
- **來源 Issues：**[Issue #177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/177)、[Issue #178](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/178)
- **實作 PRs：**[#185](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/185)、[#187](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/187)

## 問題與限制

使用者不一定能啟用 GitHub Pages、建立外部託管帳號，或取得 organization／enterprise 管理權。repo-site 同時需要保留特殊簡報設計、支援討論與交付，而且下載後仍能離線開啟。因此 Pages、CDN、web font、外部 JavaScript 與分離圖片都不能成為 portable baseline。

原本 root `docs/index.html` 把內容、樣式、互動與決策來源放在同一檔案；Copier 下發網站則在 runtime 載入 `docs/site-content.js`，讓非前端維護者必須編輯 JavaScript。現在 root 由 Hugo 讀取雙語 Markdown，生成專案則由輕量 renderer 讀取 `docs/site-content.md`；兩者都從 repository 內來源重建同一路徑的單檔交付物。

聊天也不是 repository source of truth。現有 Spec → Issue 流程不會擷取對話；若無條件保存完整逐字稿，會把未確認假設、敏感脈絡與噪音寫進版本歷史。

## 決定

採用「repository 內可維護來源 → 可重現的 self-contained HTML」：

1. `docs/index.html` 與 `docs/index.en.html` 保持已提交、可直接傳送、可用 `file://` 開啟的單檔交付物；CSS、JavaScript、font、SVG 與 raster images 全部內嵌。
2. 編輯來源與 bundled output 分離。`site/content/` 維護中英文 Markdown，`site/layouts/` 維護 Hugo 結構，`site/static/` 維護樣式、互動與媒體；`scripts/build-repo-site` 先由 Hugo 建置到 `dist/`，再沿用 `scripts/render_site.py` 產生交付檔。生成檔不是擴充點，也不直接手改。
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

**決定**：`scripts/build_repo_site.py` 是新的 renderer，僅用 Python 標準函式庫（`re`、`json`、`tomllib`、`pathlib`、`html`），不引入 Node、Markdown 套件或樣板引擎。`site/content/_index.{zh-tw,en}.md` 既有的 `{{< slide key="..." >}}...{{< /slide >}}` 區塊語法完全不變；新引擎（搭配共用的 `scripts/repo_site_blocks.py` 解析器）把原本 `site/layouts/` 下的每個 Hugo shortcode／partial／home layout 逐一改寫成讀取同一批 `site/data/*.json`／`*.toml` 的 Python 函式。新引擎的輸出（`dist/repo-site/` 下的雙語 pre-bundle HTML）交給 `scripts/render_site.py` 的 `render()`——完全未修改——內嵌資產並拒絕外部 runtime asset，這正是本 ADR「未修改的 renderer 只負責資產內嵌」約束的字面實作，延續不變。`scripts/install-hugo`、`site/hugo.toml`、`site/layouts/` 已刪除。

**Mermaid**：新引擎支援 ` ```mermaid ` fenced code block，輸出 `<pre class="mermaid">` 加一段簡短的本地 boot `<script>`；圖表函式庫本身以固定版本形式 vendor 在 `site/static/vendor/mermaid.min.js`（記錄來源網址與 SHA256），只在頁面真的包含 mermaid 區塊時才引用，其餘頁面零成本。

**版本**：新增 `site/version.json` 記錄渲染引擎（`engine`）與排版模板（`template`）各自獨立的版本號，以及引擎相容的模板版本範圍（`compatible_template_range`），不跟著 repo／CLI 整體 SemVer 走；`scripts/check-repo-site-versions` 驗證版本落在相容範圍內，fail closed。

**內容一致性**：切換前後以「拆解 HTML 標籤、正規化空白後比對逐頁可見文字」與「id／href／data-track／data-audience／data-content-key／aria-controls 屬性值集合」兩種方式核對雙語輸出，兩者皆完全相符。英文頁逐頁文字位元組相同；中文頁有 5 個投影片的差異，經追查是 Hugo 的 goldmark／CommonMark flanking-rule 對「`**標籤：**` 後緊接全形冒號與中文字、無空白」的既有排版寫法留下未轉換的字面 `**...**`（既有 bug，非本次引入）——新引擎改用簡單的正則比對兩個 `**` 之間任意字元，正確轉成 `<strong>`，等於順帶修正了這個既有渲染缺陷。`llms.txt` 與 `docs/llms.txt` 逐位元組相同。

**測試**：`tests/test_build_repo_site.py` 對每個渲染函式做 fixture 單元測試（不需要 Hugo、Node 或瀏覽器自動化），並涵蓋 config-guidance 的多行程式碼樣本換行保留、similar-tools 的排序邏輯與 mermaid 區塊的條件式輸出；原本需要實跑 Hugo 才能驗證的 `tests/test_config_guidance.py` 端對端測試已改用新引擎直接驗證，移除 Hugo 相依。

## 2026-09-03 根網站自訂主題（Issue #527）

Issue #527 要求：在 #524 讓渲染引擎與排版模板各自獨立版本、可替換之後，讓維護這個 repository 自己（fork 或 vendor 這份公版，不是 Copier 下發的生成專案）repo-site 的人，能不 fork 引擎或版面邏輯就換一套顏色主題。原則維持「盡可能簡單」：只開放顏色與既有區塊的窄範圍視覺覆寫，不開放任意 CSS／HTML。

**機制**：新增 `site/theme.css`，與生成專案既有的 `docs/site-theme.css`（`template/docs/site-theme.css.jinja`）同一套設計、不同路徑——因為根網站與生成專案的 handbook 是兩套不同 renderer（見上方「Ownership 與更新」與 2026-09-03 節）。`scripts/build_repo_site.py` 在 `<head>` 固定多輸出一個 `<link rel="stylesheet" href="../../site/theme.css">`（在 `site/static/styles.css` 之後，讓 CSS cascade 覆寫生效），`scripts/render_site.py` 既有的 stylesheet 內嵌步驟原樣處理它，不需要修改。此檔一律存在（committed，預設空白 `:root {}` 加說明註解），因此預設輸出的 `docs/index.html`／`docs/index.en.html` 不變；有需要時直接覆寫 `site/static/styles.css` 的 `:root` token 或既有 class 的顏色屬性即可，範圍與界線寫在檔案自己的開頭註解裡，由一般 PR review 把關，不另建驗證工具。

**不採用 `.csarc/config.yml`**：`scripts/build_repo_site.py` 已明確記載根網站內容不吃 `.csarc/config.yml`（該檔案是 repository 治理設定，`[[key]]` token 機制服務的是生成專案的 `docs/site-content.md`）。用 YAML 顏色鍵值再轉譯成 CSS 會是第二套主題機制，與既有 `site/static/styles.css` 的 CSS custom properties 重複；因此選擇同一種 CSS 覆寫檔案格式，只是換一個 repo 內路徑。

**版本**：這是排版模板結構契約的新增（一個一律存在、一律被 link 的新檔案），`site/version.json` 的 `engine`／`template` 由 `1.0.0` 一併調整為 `1.1.0`，仍落在既有 `compatible_template_range`（`>=1.0.0 <2.0.0`）內，`scripts/check-repo-site-versions` 驗證通過。

**驗證**：`tests/test_build_repo_site.py` 覆蓋 `render_page()` 一律輸出 `site/theme.css` 的 stylesheet link，以及一筆全流程 fixture（`build()` 接 `render()`）證明實際覆寫的 token 值會出現在最終內嵌後的 bundle 裡。手動以真實內容執行 `./scripts/build-repo-site`，先確認預設（空白覆寫）與既有輸出一致，再暫時填入一個顏色覆寫、重新產生、瀏覽器開啟確認生效，最後還原。

## 2026-09-03 稽核軌跡呈現與資料新鮮度（Issue #559）

Issue #535 已完成稽核軌跡的資料自動產生機制：`scripts/generate_audit_trail.py` 即時查詢 GitHub GraphQL API，輸出 PR 稽核表與規則變更（`policies/` 路徑）maker/checker 紀錄兩份 Markdown。呈現層當時留待 #524 的 Python 渲染引擎落地後才處理，因此拆成獨立的 #559；#524 已合併，本節記錄呈現機制與資料新鮮度的實際決定。

**決定**：這個 repo-site 是「重建後逐位元組相同、可用 `file://` 離線開啟」的靜態單檔（見本 ADR 最上方「決定」第 1 點），架構上不可能顯示即時查詢的結果，也不為了呈現這個模組破例。#535 的證據已建議比照 `scripts/check-governance-drift` 的既有先例——本模板 source repo 只保留腳本供本機／CI 驗證，不另外啟用排程；本 Issue 採用同一先例並延伸到「不提交快照」：既不加即時查詢（架構上做不到），也不加排程或 on-merge job 產生後提交進 repo（需要持續維護，且會讓使用者誤以為頁面上的資料是某個時間點的真實快照而非結構說明）。網站只呈現兩份輸出檔案各自的路徑與欄位結構，以及重新產生的確切指令，並在文案中明講「不嵌入即時或先前產生的資料列，也沒有排程」。

**機制**：新增 `site/data/audit_trail.json`（單一來源，兩語言共用同一組真實檔案路徑與欄位名稱，避免各自手打翻譯漂移）與 `scripts/build_repo_site.py` 的 `render_audit_trail()`／`{{< audit-trail >}}` shortcode，沿用既有 `render_config_guidance`／`render_file_map` 這類「結構化、手動維護（非即時抓取）資料 → slide」的既有模式，不新增資料流或渲染架構。新增的 slide（`governance-audit-trail`，`audience="archive"`、`parity="new"`）沿用 `fleet-inventory`／`spec-format` 等既有「決策附錄」slide 的呈現慣例。

**驗證**：`tests/test_build_repo_site.py` 新增 `render_audit_trail` 的單元測試，並以一則內容一致性測試（比照既有 `test_file_map_matches_real_workflow_directory_and_paths`）直接呼叫 `scripts/generate_audit_trail.py` 的 `render_pr_audit_table`／`render_rule_change_log`，比對其實際 Markdown 表頭欄位與 `site/data/audit_trail.json` 手寫的欄位清單逐字相符，避免兩邊日後各自修改而悄悄漂移。`./scripts/build-repo-site --check` 確認新增 slide 後仍逐位元組重建；`parity="new"` 讓 keys-only parity 檢查正確判定這是遷移後新增的內容，不會被誤判為遺漏既有 legacy slide。

## 2026-09-04 首頁與 README 對齊（Issue #526）

Issue #526 要求首頁（原「能力／導入」slide，`key="capability"`）與 repository 根目錄 `README.md` 「看到的東西要一模一樣」，不再各自維護一份漂移的內容；這獨立於 Issue #425（研究中、blocked，尚無維護者核准的內容模型結論）進行——維護者已明確決定 #526 不等待 #425，用自己的判斷先交付，兩者結論若未來衝突再另行調解。

**決定：README.md 使用的 GFM 語法**——只採用 GitHub 原生就能正確預覽、且本引擎（`scripts/build_repo_site.py`）也能安全渲染的最小交集：標題、段落、GFM pipe table、`> [!IMPORTANT]` alert（僅 README，GitHub 專屬語法，本引擎不解析 blockquote，因此網站側改用一般粗體段落表達同一段狀態說明）、連結。不使用 shields.io 或其他外部圖片徽章（README 目前完全不依賴外部圖片，維持零網路依賴的預覽）。

**內容模型**：兩份「版本／能力」表格逐字（byte-for-byte）同時存在於 `README.md` 與 `site/content/_index.zh-tw.md` 的 `{{< basic >}}`（首頁預設顯示的簡易模式）區塊——一份是新增的「項目／目前狀態」版本表（公版版本、支援語言、repo-site 排版模板版本、repo-site 渲染引擎版本），一份是既有的「可以直接選擇／目前提供的正式能力」能力表；`tests/test_homepage_readme_parity.py` 的 `test_capability_table_is_identical_in_readme_and_zh_home` 把第二份表格的逐字相同直接寫成回歸測試。英文首頁（`_index.en.md`，`legacy="false"`，本來就沒有 legacy／basic 雙模式）同步採用相同表格結構的英文翻譯，維持「雙語皆同步」，但不對應一份不存在的英文 README。zh-tw 首頁的技術（`{{< legacy >}}`）視圖只補上兩顆新徽章，其餘既有的互動式安裝指令 overlay（`setup-trigger`／`legacy-components.js`）不在本 Issue 範圍內變動。

**版本顯示**：支援語言、repo/CLI 版本號直接以文字呈現（repo/CLI 版本沿用既有 `<!-- x-release-please-version -->` 慣例，見下一段）；網站排版模板與渲染引擎版本使用 #524 已提供的 `[[site_template_version]]`／`[[site_engine_version]]` token（由 `site/version.json` 解析），因此模板／引擎版本升級後兩個語言的首頁都會自動更新，不需要人工同步；`README.md` 因為完全不經過本引擎的 token 替換，只能寫入當下的字面版本號，由 `tests/test_homepage_readme_parity.py` 的 `test_required_facts_appear_in_readme_and_both_home_slides` 檢查它與 `site/version.json` 的實際值相符，drift 時 fail closed。

**已知的渲染限制**：本引擎的 Markdown 表格 cell 一律經過 HTML escape（無真正的行內 HTML 解析），因此 `<!-- x-release-please-version -->` 這類 comment marker 放進表格 cell 會被跳脫成可見的字面文字，而不是被瀏覽器隱藏的真正 comment——GitHub 自己的渲染器能正確處理，本引擎不行。因此：README.md 的版本表格 cell 內仍可直接放 marker（GitHub 安全）；zh-tw 首頁當時把版本表格改成純文字版本號（不放 marker），真正會被 release-please 更新的 marker 留在既有、已驗證安全的技術視圖徽章（`<span>` 在 `{{< legacy >}}` 的 raw HTML 區塊內）；`tests/test_homepage_readme_parity.py` 的 `test_zh_home_repo_version_mentions_stay_in_sync` 確保這兩處版本號不會日後各自漂移。**這個 zh-tw 純文字版本號的安排已被下方「2026-09-07 zh-tw 首頁版本改用獨立 raw HTML 行」取代**——保留這段是為了記錄當時為什麼會先選純文字，而不是因為現在還這樣做。英文首頁沒有 legacy 視圖可以借用，改為在 basic body 內新增一行獨立的 raw HTML（`<p class="template-version">...`），單獨占一整行以觸發本引擎「整行以 `<` 開頭即原樣輸出」的既有 passthrough 規則，`test_en_home_release_marker_is_on_its_own_raw_html_line` 把這個結構要求寫成測試。`release-please-config.json` 的 `extra-files` 新增 `site/content/_index.en.md`、`docs/index.en.html` 兩筆（原本只追蹤 zh-tw 與其對應輸出），讓兩個語言在下一次真實發版時都會更新，`test_release_please_tracks_both_language_home_files` 驗證兩個語言檔都已註冊。

**內容長度限制**：定義在 `tests/test_homepage_readme_parity.py`——README hero（`# CSARC Repo Template` 到 `## 目錄` 之間）上限 1600 字元／28 個非空行；zh-tw 首頁 basic body（不含可摺疊的 `{{< detail >}}` 補充說明）上限 1200 字元／22 行；英文首頁上限 2400 字元／22 行（英文用字自然比中文長，門檻按語言分開訂，而非用單一跨語言門檻）。門檻是本 Issue 實際內容量（README 1141 字元／18 行、zh-tw 791 字元／14 行、en 1834 字元／14 行）加上合理但不過寬的緩衝，之後真的塞入完整 README 或整段無關內容會直接 fail closed。

**驗證**：`./scripts/build-repo-site` 手動重建後人工檢視 `docs/index.html`／`docs/index.en.html` 對應 slide 的實際渲染 HTML，確認 marker 未被跳脫成可見文字、`[[site_template_version]]`／`[[site_engine_version]]` 已正確代入實際版號。`tests/test_homepage_readme_parity.py` 新增的測試涵蓋上述所有主張；`scripts/check-repo-site-parity --keys-only`（透過 `./scripts/build-repo-site --check` 呼叫）只比對 slide 層級的 key（`id="capability"`／`data-track="capability"`），本 Issue 未變動這兩個屬性，因此不受影響。GitHub repo page 的實際渲染以推送後於瀏覽器開啟該分支的 `README.md` 預覽為準，記錄在 Issue #526 的完成證據留言中；本機沒有復現 GitHub 自己 Markdown 渲染管線的能力，因此這一步無法在合併前於本機完全重現，只能在推送後於 GitHub 上直接檢視。

## 2026-09-07 zh-tw 首頁版本改用獨立 raw HTML 行（Issue #694）

Issue #526 當時選擇讓 zh-tw 首頁的版本表格 cell 保留純文字（不放 marker），只用 `test_zh_home_repo_version_mentions_stay_in_sync` 事後偵測它與技術徽章是否漂移——這個測試能擋住 CI，但不能防止漂移本身發生：`scripts/release_policy.py`（`prepare-candidate`）只改寫帶 marker 的那一行，這格純文字永遠不會被自動更新，需要每次發版後手動修正。v0.14.0、v0.15.0 兩次連續發版都真的發生這個情況。

Issue #681/#682 為英文首頁引入的解法——把版本號搬出表格、改成獨立一行、以 `<p class="template-version">...</p>` 的 raw-HTML-passthrough 形式呈現（本引擎對整行以 `<` 開頭的行採 passthrough，不做 escape，因此可以安全帶 marker）——同樣適用於 zh-tw，且不需要犧牲 Issue #526 當時「表格 cell 不能安全帶 marker」的判斷：只是不再把版本號放進表格 cell，而不是放棄 marker。

**決定**：zh-tw 首頁採用與英文首頁相同的結構——`<p class="template-version"><strong>公版版本：</strong>vX.Y.Z<!-- x-release-please-version --></p>` 獨立一行，位置緊接在 basic body 開頭段落之後、版本／能力表格之前；表格本身移除「公版版本」這一列（其餘列不變）。`release-please-config.json` 的 `extra-files` 不需要新增項目——`site/content/_index.zh-tw.md` 早已在清單中，`prepare-candidate` 本來就會掃描整份檔案裡每一行含 marker 的文字，不是只認特定檔案或列。

**驗證**：`tests/test_homepage_readme_parity.py` 的 `test_zh_home_repo_version_mentions_stay_in_sync` 改為比對這行段落而非已刪除的表格 cell；新增 `test_zh_home_release_markers_are_each_on_their_own_raw_html_line`（比照英文首頁既有的 `test_en_home_release_markers_are_each_on_their_own_raw_html_line`）確保 marker 仍各自獨立成行。這兩則測試延續 Issue #526 原本的「事後偵測漂移」性質；本 Issue 額外新增 `tests/test_release_policy.py` 的 `test_zh_home_version_paragraph_updates_automatically_on_bump`，直接複製正式站台的 `site/content/_index.zh-tw.md` 到臨時 git repo、實際跑一次 `prepare_release_candidate` 版本升級，斷言這行版本文字**自動**跟著更新——這是「主動證明不會再漂移」而非「漂移後才發現」，能在這格版本文字被意外改回純文字表格 cell（即本 Issue 要修的舊行為）時直接讓測試失敗，而不必等到下次真的發版才發現。`./scripts/build-repo-site --check` 確認新結構仍能逐位元組重建、marker 未被跳脫成可見文字。

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

## 2026-09-03 GitHub Pages 宣告式政策（#571）

Repo 由 private 轉 public 後，維護者直接對 live GitHub 啟用了 GitHub Pages（`source.branch=main`、`source.path=/docs`，classic「deploy from branch」，`main` 有新 push 時自動重建）。Issue #571 把這個決定落地成 `policies/pages.json`（含可關閉的 `enabled` 欄位）與 `scripts/apply-repository-settings.sh` 的對應 apply／check 區塊，比照 `policies/rulesets.json` 既有的 plan-aware `DEGRADED` 偵測：GitHub Pages 對 private repository 需要 GitHub Enterprise Cloud，Free／Pro／Team 都無法在 private 啟用；public repository 則所有方案皆可免費使用。這正是上方「GitHub capability matrix」表格「核准的 Pages／內部 host 與寫入權限 allowed」一列描述的情境，本次只是把該能力從『可能可用』變成有實際宣告式政策與 live 驗證的具體案例。

這個變更只是在既有 committed bundle 之上「新增」一種發布管道，不改變本 ADR 的核心保證：`docs/index.html`／`docs/index.en.html` 仍是完整內嵌、可 `file://` 直接開啟的單檔交付物；`docs/.nojekyll` 只是避免 GitHub Pages 對這個純靜態、已建置完成的 bundle 執行不必要的 Jekyll 處理，不引入任何 runtime 依賴或外部資產。Pages 發布失敗或不可用時，repository 內已提交的 bundle 仍是不下降的最低交付保證，與「發布失敗時回退 artifact／committed bundle，不降低內容驗證」的既有承諾一致。

是否把這個能力開放成下游生成 repo 的可選 Copier 項目，留給後續 Issue 判斷；本次變更只涵蓋這個模板來源 repo 自己的宣告與驗證。

## 2026-09-06 下游生成專案改用同一套 repo-site 引擎（Issue #681 決定 N）

Issue #681 使用者要求：Standard／Ops 分層、雙語鉤稽、簡報式構圖（桌面版不出現內容區捲軸）與可重用元件，不能只修 root 自己的網站，也要進到 `template/`。本節取代（supersede）本 ADR最上方「決定」第 5 點（「root 可以增加 deck-specific 呈現，生成專案則使用 handbook layout」）與 2026-09-03 主題章節「因為根網站與生成專案的 handbook 是兩套不同 renderer」的既有分工判斷——維護者重新檢視後認定：這個分工本身就是先前的設計選擇，不是任何硬性技術限制造成的既有分岔，沒有理由維持兩套系統。

**決定**：下游生成專案的 repo-site 改用跟 root 完全相同的引擎與元件，不再是 `docs/site-content.md` 這份由 `scripts/render_site.py` 內建的獨立 Markdown-to-handbook renderer（單語言、無 Standard／Ops 分層、雙欄長卷軸）產生的簡化手冊：

- `scripts/build_repo_site.py`、`scripts/repo_site_blocks.py`、`scripts/check-repo-site-navigation`、`scripts/check-repo-site-translations`、`scripts/check-repo-site-versions` 現在也由 `scripts/sync-paired-files.sh` 逐位元組同步到 `template/scripts/`，跟既有的 `scripts/render_site.py`（本 ADR 原本唯一標記「未修改、雙方共用」的檔案）用同一套機制。下游專案跟 root 執行的是同一份程式碼，不是分頭維護的相似實作。
- `site/static/styles.css`、`detail-toggle.css`、`deck.js`、`legacy-components.js`、`detail-toggle.js` 同步複製到 `template/site/static/`，提供跟 root 相同的視覺語言、archetype（流程圖 `.step-flow`、能力地圖 `.capability-map`、關係圖 `.relation-map` 等）與 Standard／Ops 切換互動。
- 下游專案的雙語內容來源改成 `template/site/content/_index.zh-tw.md`／`_index.en.md`（純檔案複製，不經 Copier Jinja），精簡起始頁只含首頁、安裝說明、關於三頁——不是把 root 現有 11 段 Journey 內容整批搬過去，那些內容描述的是「這個模板 repo 自己」的治理示範，不是每個下游專案都適用的通用敘事。專案之後可依需要在 `site/content/` 自行擴充頁面。
- 下游專案的專案事實（`project_name`、`project_description`、`languages`、`branch_strategy`、`project_visibility`、`code_owner`、`reviewers`、`repository_url`）透過 `[[key]]` token 在**每次本機建置時**直接讀 `.csarc/config.yml`（`build_repo_site.py` 新增的 `_substitute_config_tokens`／`_load_downstream_config`，沿用既有 `_substitute_version_tokens` 的同一套 `[[key]]` 語法與 fail-closed 設計），不是像舊機制那樣只在 `copier copy`／`update` 當下用 Jinja 解析一次；`.csarc/config.yml` 之後若有變動，不必等下一次 Copier 更新就會反映到網站。允許的 key 就是「規則治理」`governance-config` 表格既有的核准清單，加上 `repository_url`（公開、非敏感，本來就在建立時詢問，用於安裝頁的 clone 指令）。
- `docs/site-theme.css`（Issue #527，專案自訂主題覆寫）維持不變，機制與路徑都不受影響；`build_repo_site.py`／`render_page()` 新增 `theme_href` 參數，root 傳入 `site/theme.css`、下游生成專案傳入 `docs/site-theme.css`，同一份 page-shell 程式碼服務兩種呼叫者。

**Ownership 更新**（取代上方表格 `docs/site-content.md` 那一列）：

| 內容 | Owner | Copier update 行為 |
| --- | --- | --- |
| `site/content/_index.zh-tw.md`／`_index.en.md`（下游生成專案） | consuming project | 首次建立後保留（`_skip_if_exists`），不靜默覆寫 |
| `site/data/navigation.json`（下游生成專案，若專案自行擴充頁面） | consuming project | 首次建立後保留（`_skip_if_exists`） |
| `docs/site-theme.css`（下游生成專案） | consuming project | 首次建立後保留，機制不變（Issue #527） |

**既有 `docs/site-content.md` 的遷移**：`template/docs/site-content.md.jinja` 已移除，新建立的專案不會再產生這個檔案。已經導入過的既有專案，這個檔案本身不會被刪除或覆寫（沿用「不靜默覆寫 project-owned content」的既有承諾），但已經沒有任何 renderer 讀取它；`scripts/build-repo-site`（下游專案版）偵測到該檔仍存在時，印出遷移提示，要求維護者把要保留的文字移入 `site/content/_index.*.md` 後自行刪除舊檔——沿用本 ADR 原本 `docs/site-content.js` → `docs/site-content.md` 遷移時「保留舊檔＋顯示提示＋不自動搬遷」的同一套先例，這次沒有再往輸出頁面內嵌提示（該機制原本就綁定舊 renderer 的 marker 注入，新引擎不重建這條路徑），改成建置時的終端機提示。

**驗證**：新增 `_substitute_config_tokens`／`_load_downstream_config`／`load_site_data` 容忍缺少非必要資料檔（`glossary.toml` 以外，`similar_tools.json`／`config_examples.json`／`file_map.json`／`audit_trail.json` 對精簡下游網站皆為選用）的單元測試（`tests/test_build_repo_site.py`）；`tests/test_render_site.py::test_copier_generated_project_builds_its_own_bilingual_repo_site` 實際呼叫 `copier.run_copy()`（真正跑過 Copier 樣板引擎本身，不是手動組出的等價 fixture）產生一個全新專案，確認 `_tasks` 的 `bash scripts/build-repo-site` 有實際執行、舊系統檔案完全不存在、雙語 `docs/index.html`／`docs/index.en.html` 正確產生且 `.csarc/config.yml` 各欄位（`project_name`／`project_description`／`code_owner`／`reviewers`／`repository_url`）都正確代入、無殘留 `{{< slide key=`／`[[project_name]]` 等未解析標記、無外部 runtime asset、Standard／Ops 兩個 `data-mode` 面板皆存在；`tests/test_render_site.py`／`tests/test_journey03_ci.py` 更新為驗證新路徑與 `./scripts/build-repo-site --check`（取代舊有 `render_site.py --check` 斷言）。既有 7 個 `audience="archive"` 封存投影片（`rollout`／`access-control`／`principles`／`benchmark`／`fleet-inventory`／`fleet-governance-thresholds`／`spec-format`）中英文結構不對稱的落差已在 Issue #681 決定 P 補齊（英文版翻譯並補上原本缺少的富結構面板）。

## 2026-09-06 12pt 字級下限與 Ops 模式內容瘦身（Issue #681 決定 Q）

使用者依實測螢幕（1512×982，deck 依 `min(innerWidth/1600, innerHeight/900)` 縮放，換算比例約 0.945）要求：桌面版任何顯示文字（除引用／註腳外）渲染後不得小於 12pt，並授權「該精簡的流暢精簡，該放在懸浮說明文字中的放在懸浮中」。12pt＝16px 實際尺寸；換算縮放後 CSS 原始字級下限抓 **18px**（18×0.945≈17px≈12.7pt，有安全餘裕，也是站上最常用的內文字級）。

**字級**：`site/static/styles.css`、`detail-toggle.css` 約 70 處 11–17.5px 字級提升到 18px，涵蓋表格、badge、標籤、標準／維運與語言切換鈕本身；豁免 `.reference`（引用，已是 12pt）與純裝飾圖示字符（+/−、▸/▾ 展開三角形）。`template/site/static/` 手動複製同步更新（非 `sync-paired-files.sh` 管轄範圍，既有限制見上）。

**意外發現與修正的量測缺口**：字級全面提升後，用原本「`.slide.scrollHeight <= .slide.clientHeight`」的稽核法仍回報零溢出，但這個方法量不到 `.markdown-body { overflow-y: auto }`（維運模式內容面板的 fail-safe）悄悄吸收掉的真實溢出。改用逐元素 `getBoundingClientRect()` 精確稽核後，發現維運模式在 deploy、governance、supply、method、files 等十餘頁的內容早就超出 900px 畫布，一直是靠這個「不該被依賴」的內部捲軸擋著——這是先於本次字級改動就存在的既有缺陷，本次改動只是讓它更嚴重，而精確稽核法首次讓它現形。

**決定**：`scripts/build_repo_site.py` 的 `render_config_guidance()` 改回輸出 `<details>`（收合，一鍵展開），**取代並取代 Issue #525**「config-guidance 一律靜態攤開、不留任何收合層」的決定——Issue #525 當時的理由（單一固定形狀、不再區分 direct／非 direct track）仍然成立且保留；本次只推翻「一定要攤開可見」這一點，因為 12pt 下限讓多範例、多程式碼片段的 track 無論如何都放不進 900px。同步更新 `tests/test_build_repo_site.py::test_config_guidance_renders_one_collapsed_block_regardless_of_direct`（原斷言「不能有 `<details>`」改為「剛好一個 `<details>`」）。另外把 method／agents／deploy／governance／docs-site 等頁「其他常見做法」清單、deploy／governance 的版本來源與方案對照表、7 個封存頁與 benchmark 的次要 `{{< detail >}}` 說明框，改成 `{{< disclosure >}}` 收合；`similar-tools`／`testing`／archive 審查頁的比較表改用有界捲動（`max-height` + `overflow-y: auto`，`<table>` 需額外加 `display: block` 才能在部分渲染引擎正確套用，否則 `max-height` 會被忽略）取代無界攤開，跟既有 `.similar-tools-table-wrap` 是同一套「表格可以內部捲動，畫面本身不捲動」設計慣例。`files` 頁的檔案樹（`.file-map-tree`）比照辦理。原本套用同一有界捲動手法的獨立「進階安裝」頁，後於決定 R 併入 `install` 頁本身，不再需要這條規則。

**驗證**：新的精確稽核法逐元素量測 `getBoundingClientRect()`，排除（a）自身或祖先是未展開 `<details>`、（b）祖先有 `overflow-y: auto`／`scroll` 且非 `.slide`／`.markdown-body` 本身（後兩者是已知 fail-safe，不算合法排除）。桌面 1600×900、雙語、Standard／Ops 雙模式全數複查，零溢出。`check-repo-site-translations`（83 個 keyed blocks，含新增的 disclosure key）、`pytest -m "not large"`、`ruff`、`ty`、`sync-paired-files.sh --check`、`build-repo-site --check` 全數通過。

## 2026-09-06 「進階安裝」併入 install 頁（Issue #681 決定 R）

使用者檢視 repo-site 側邊導覽，指出「備註」群組裡的獨立「進階安裝」頁（英文標籤只寫「Advanced」，脫離上下文看不出跟誰有關）本質上是 `install` 頁的維運限定加深版，兩者不該是分開的頁面。

**決定**：取代 Issue #531「Advanced install 獨立成一張 slide」的決定——Issue #531 當時的內容本身（capability-matrix 對照表、如何解讀結果、既有 DEGRADED workaround 三段）仍然成立且逐字保留，只推翻「獨立成頁」這一點。原本 `{{< slide key="advanced-install" audience="maintainer" ... >}}` 整頁，改成 `install` 頁 `{{< ops >}}` 面板裡的三個 `{{< disclosure >}}`（`advanced-install-capabilities`／`advanced-install-results`／`advanced-install-workarounds`），緊接在既有的 `install-policy-only`／`install-agent` 兩個 disclosure 之後；`audience="maintainer"` 標記不再需要，因為整段內容現在已經在只有維運模式才看得到的 `{{< ops >}}` 面板裡。`site/data/navigation.json` 移除 `advanced-install` 條目；原本因為它是獨立頁、內容量大而加上的有界捲動 CSS（`#advanced-install .markdown-body > table`）一併移除，改用跟其他頁一致的「內容包進 disclosure，收合時不佔空間，展開時自然撐開」處理，不再需要額外的捲動邊界。

跨檔案錨點更新：`docs/agent-install.md`、`docs/ci-policy.md`、`docs/adr/capability-aware-governance.md` 原本指向 `docs/index.html#advanced-install` 的說明文字與連結，改指向 `docs/index.html#install`（deck.js 依 slide key 做 hash 路由，`install` 才是現在唯一存在的 slide key）。`tests/test_advanced_install_content.py` 的 `test_navigation_declares_the_advanced_install_entry` 改寫為 `test_advanced_install_has_no_separate_navigation_entry`，斷言 `navigation.json` 不再有 `advanced-install` 條目；同檔的能力 id 對齊測試（`test_every_matrix_capability_id_is_mentioned_in_both_language_slides`）不變，因為 capability id 仍以行內程式碼形式出現在合併後的內容裡。

**驗證**：`check-repo-site-translations`（83 個 keyed blocks，數量不變——移除 1 個 slide key、新增 1 個 disclosure key，`advanced-install-results`／`advanced-install-workarounds` 兩個既有 disclosure key 原樣保留）、`check-repo-site-navigation`、`pytest -m "not large"`、`ruff`、`ty`、`sync-paired-files.sh --check`、`build-repo-site --check` 全數通過；桌面 1600×900、雙語、Standard／Ops 雙模式精確稽核零溢出（總頁數由 27 降為 26）。

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
