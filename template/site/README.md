# Decision site source

本目錄由 CSARC 公版維護，定義 portable presentation 的結構、樣式與互動。請在下列 project-owned 檔案維護專案差異：

- `docs/site-content.js`：文字與結構化內容；必須保留支援的 `schemaVersion`
- `docs/site-theme.css`：允許的色彩、字型與少量版面覆寫
- `docs/adr/`：經確認與 PR 審查的 Architecture Decision Records（ADR）

修改後執行 `uv run --no-project python scripts/render_site.py`。`docs/index.html` 會把 CSS、JavaScript、font 與 image 內嵌成可離線交付的單一檔案，不要直接修改它。

送 PR 前直接用瀏覽器開啟 `docs/index.html`，在離線狀態重新載入，並以桌面與約 390px 寬的 viewport 檢查導覽、表格與內容是否可讀；用 Tab 走過 skip link 與導覽連結。自動檢查成功不代表外部託管或存取控制已啟用。
