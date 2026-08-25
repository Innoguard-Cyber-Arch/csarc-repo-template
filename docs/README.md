# 文件地圖

`docs/index.html` 與 `docs/index.en.html` 是可下載、轉寄並以 `file://` 離線開啟的簡報交付物；它們不是唯一的可編輯決策來源。需要理解或修改內容時，先依下表找到對應來源，不要直接把新決策只寫進簡報。

| 類型 | 路徑 | 用途與維護方式 |
| --- | --- | --- |
| 單檔交付物 | `docs/index.html`、`docs/index.en.html` | 由 Hugo 來源重建的中英文 portable presentation；內嵌樣式、程式與媒體，不直接編輯 |
| AI 閱讀索引 | `llms.txt`、`docs/llms.txt` | 由 Hugo 從 `site/data/glossary.toml` 同源產生；兩份輸出都不直接編輯 |
| 網站來源 | `site/` | 分開維護 Markdown 內容、Hugo 模板、特殊視覺、互動與原始圖片；詳見 `site/README.md` |
| 選型與決策 | `docs/decisions/` | 已確認的架構、工具、安全、相容性與平台能力取捨；保留狀態、理由、替代方案與重評條件 |
| 規格 | `docs/specs/` | 中長期成果與驗收條件；核准後可同步成 Issue 或 Story Milestone |
| 操作契約 | `docs/agent-install.md`、`docs/milestone-description.md` | 已發布且可能由固定版本 URL 讀取的介面；路徑保持穩定 |
| Runbook | `docs/live-integration.md`、`docs/artifact-consumption.md` | 維護者執行線上驗證或排查交付鏈時使用 |
| 實證 | `docs/pilot-adoption.md` | 真實 consuming repository 的採用、更新與限制證據 |

## 新決策如何進來

人與 agent 的聊天不會自動成為正式決策，也不保存完整逐字稿。當使用者確認會持續影響架構、工具、安全、相容性或平台能力的限制時：

1. 先搜尋 `docs/decisions/` 與 open／closed Issues，確認是否已有決定。
2. 在既有或新 Issue 摘要已確認的限制、替代方案與既有決策如何被沿用、取代或駁回。
3. 以該 Issue 為範圍，透過 PR 更新對應的 canonical decision record。
4. 若決策會出現在簡報，同一個 PR 更新或重建 `docs/index.html`，並由驗證阻止兩者漂移。

未確認的建議仍留在討論；敏感資訊與完整聊天內容不得因自動化而寫入 repository。

## 維護原則

- 新增內容前先判斷它是使用指南、runbook、決策、實證、規格或交付物，不以檔案格式決定分類。
- `docs/agent-install.md` 等公開契約優先維持穩定路徑；需要分類時由本頁導覽，不為整理目錄破壞既有 URL。
- `docs/index.html` 與 `docs/index.en.html` 必須各自保持單檔、無 runtime 外部 CSS、JavaScript、font 或 image 依賴。超連結可以指向外部參考資料，但離線開啟不能因網路不可用而失去簡報內容或操作能力。
- `docs/decisions/`、`docs/specs/`、runbook、TDD 與其他工程文件保持各自的 Markdown 生命週期，不放入 Hugo content tree；簡報只連結或摘要它們。
- 修改 `site/` 後執行 `./scripts/build-decision-site`；`--check` 只比對 committed outputs，不改檔案。
- 公版維護者負責 `site/data/glossary.toml`；同一建置指令會重建並驗證兩份 `llms.txt` 產物。`csarc-ai-setup` 的 `docs/proposal-deck.html`／`SDD.md` 沒有共用此內容來源，本次不跨 repository 同步；若該 repo 需要相同能力，另開獨立 Issue 評估。
- 網站呈現、來源、模板 ownership 與 GitHub capability fallback 的完整選型見 [`decisions/portable-decision-site.md`](decisions/portable-decision-site.md)。
