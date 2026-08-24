# Portable decision site architecture

- **狀態：**Accepted
- **日期：**2026-08-24
- **追蹤：**[Issue #177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/177)
- **工程實作：**[Issue #178](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/178)

## 問題與限制

使用者不一定能啟用 GitHub Pages、建立外部託管帳號，或取得 organization／enterprise 管理權。內部決策網站同時需要保留特殊簡報設計、支援討論與交付，而且下載後仍能離線開啟。因此 Pages、CDN、web font、外部 JavaScript 與分離圖片都不能成為 portable baseline。

目前 root `docs/index.html` 把內容、樣式、互動與決策來源放在同一檔案；Copier 下發網站則把版型與 `docs/site-content.js` 分開，方便更新但失去單檔交付。兩者都缺少明確的 source／output、模板／專案 ownership 與 schema migration 契約。

聊天也不是 repository source of truth。現有 Spec → Issue 流程不會擷取對話；若無條件保存完整逐字稿，會把未確認假設、敏感脈絡與噪音寫進版本歷史。

## 決定

採用「repository 內可維護來源 → 可重現的 self-contained HTML」：

1. `docs/index.html` 保持已提交、可直接傳送、可用 `file://` 開啟的單檔交付物；CSS、JavaScript、font、SVG 與 raster images 全部內嵌。
2. 編輯來源與 bundled output 分離。來源保留特殊設計所需的版型、內容、樣式、互動與媒體；repository-local renderer 負責產生 `docs/index.html`。生成檔不是擴充點，也不直接手改。
3. 不導入 Hugo、Docusaurus、Backstage 或另一套前端 toolchain。現階段的需求是單一簡報，最小 renderer 與既有 `uv` baseline 即可；只有多頁搜尋、跨 repo catalog 或翻譯需求實際出現時才重新評估。
4. canonical decision records 放在 `docs/decisions/`。簡報呈現決策摘要與連結，但不再是唯一可編輯來源；runbook、實證與 spec 各自維持不同生命週期。
5. root 與 Copier 下發專案遵守相同 portable contract，但可以有不同 presentation layout。共用設計基礎由公版維護，root 可以增加 deck-specific 呈現，生成專案則使用 handbook layout。

## Ownership 與更新

| 內容 | Owner | Copier update 行為 |
| --- | --- | --- |
| Renderer、基礎設計 tokens、共用元件與驗證 | 公版 | 隨公版更新，產生可審查差異 |
| 專案內容與允許的 theme overrides | consuming project | 首次建立後保留，不靜默覆寫 |
| `docs/index.html` | renderer output | 由來源重建；CI 驗證沒有 stale 或人工修改 |
| Decision records、specs 與產品實證 | owning repository | 專案擁有；公版只提供結構與規則 |

專案內容契約必須宣告 `schemaVersion`。同一 major 版本新增欄位時提供相容預設；移除或改變語意時提供明確 migration 與可審查報告，不能靠覆寫 project-owned content 解決。

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

1. 搜尋 `docs/decisions/`、open／closed Issues、comments 與 linked pull requests。
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

## 驗證契約

後續 renderer 實作至少驗證：

- 從 repository 來源重建 `docs/index.html` 後逐位元組一致。
- HTML 不含 runtime 外部 stylesheet、script、font 或 image；外部超連結可以存在。
- `file://` 開啟時簡報內容、鍵盤操作與內嵌媒體可用。
- 常用窄螢幕與簡報尺寸維持可讀；不為此先加入大型視覺測試平台。
- Copier create／adopt／update fixture 證明模板檔可更新、project-owned content 與 overrides 保留、schema 不相容時 fail closed。

## 重新評估條件

只有出現多頁搜尋、翻譯、跨 repo owner／服務探索反覆耗時，或現有 renderer 已有可量測的維護失敗時，才評估 MkDocs、Backstage TechDocs 或其他文件平台。較高 GitHub 方案可讓發布更自動化，但不能移除 self-contained bundle。
