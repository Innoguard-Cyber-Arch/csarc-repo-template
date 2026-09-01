# Decision site source

本目錄由 CSARC 公版維護，只定義 portable presentation 的版型與樣式。請在下列 project-owned 檔案維護專案差異：

- `docs/site-content.md`：一般 Markdown 內容；`[[key]]` 從 `.csarc/config.yml` 讀取
- `docs/site-theme.css`：允許的色彩、字型與少量版面覆寫
- `docs/adr/`：經確認與 PR 審查的 Architecture Decision Records（ADR）

修改後執行 `uv run --no-project python scripts/render_site.py`。`docs/index.html` 會把 CSS、JavaScript、font 與 image 內嵌成可離線交付的單一檔案，不要直接修改它。

Markdown 支援標題、段落、粗體、連結、行內／區塊程式碼與清單。二級標題會產生左側導覽；三級標題會顯示成預設收合的進階說明。網站名稱、說明、語言、負責人與分支策略沿用 `.csarc/config.yml`，不要建立另一份網站設定。

送 PR 前直接用瀏覽器開啟 `docs/index.html`，在離線狀態重新載入，並以桌面與約 390px 寬的 viewport 檢查導覽、表格與內容是否可讀；用 Tab 走過 skip link 與導覽連結。自動檢查成功不代表外部託管或存取控制已啟用。
