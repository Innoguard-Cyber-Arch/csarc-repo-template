# Bundled brand assets

這些圖檔原本由簡報在 runtime 向外部網站載入；為了讓 `docs/index.html` 真正離線可用，2026-08-24 將當時版本存入 repository，renderer 會把它們轉成 data URI。商標仍屬各自權利人。

| 檔案 | 原始來源 |
| --- | --- |
| `copier.svg` | `https://raw.githubusercontent.com/copier-org/copier/master/img/logo.svg` |
| `zizmor.png` | `https://raw.githubusercontent.com/zizmorcore/zizmor/main/docs/assets/favicon48x48.png` |
| `github-community-projects.png` | `https://github.com/github-community-projects.png?size=160` |
| `renovate.png` | `https://raw.githubusercontent.com/renovatebot/renovate/main/docs/usage/assets/images/logo.png` |
| `github-actions.svg` | `https://cdn.simpleicons.org/githubactions/2088FF` |
| `pyscaffold.svg` | `https://raw.githubusercontent.com/pyscaffold/pyscaffold/master/docs/gfx/logo.svg` |
| `github.png` | `https://github.com/github.png?size=160` |
| `backstage.svg` | `https://cdn.simpleicons.org/backstage/9BF0E1` |

更新資產時，先確認上游使用規範與 repository 授權，再重建 bundle 並做離線視覺檢查；不要把 URL 改回 runtime 依賴。
