# Decision site source

本目錄是 root 決策簡報的可維護來源；`docs/index.html` 是可直接交付的生成檔，不應手動編輯。

- `index.html`：內容與語意結構
- `styles.css`：特殊簡報視覺與響應式規則
- `app.js`：鍵盤、導覽與互動行為
- `assets/`：建置時轉成 data URI 的圖片與圖示

修改後執行：

```bash
uv run --no-project python scripts/render_site.py
uv run --no-project python scripts/render_site.py --check
```

Renderer 會拒絕外部 runtime CSS、JavaScript、font 或 image，並限制本機 asset 只能來自 repository 內。一般 `<a>` 超連結仍可指向外部參考資料。

送 PR 前直接用瀏覽器開啟 `docs/index.html`，在離線狀態重新載入並確認圖片完整；以 1440×900 與 390×844 viewport 檢查版面，窄螢幕可水平平移；再用方向鍵、Page Up／Down、Home／End 與畫面按鈕走過簡報。
