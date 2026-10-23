# 安全通報處理程序

本頁說明維護者收到經 [`.github/SECURITY.md`](../.github/SECURITY.md) 私密管道送來的漏洞通報後，
如何記錄、修正與公開（#1139）。通報入口與「不在公開位置揭露」的規則以 `.github/SECURITY.md`
為準；本頁只補處理步驟，不新增管道，也不改變它的承諾範圍。

## 步驟

1. **記錄**：收到通報的維護者在私密位置建立紀錄，寫下收件時間、通報者聯絡方式、受影響的
   版本或元件、重現狀態。私密位置是通報管道的往來紀錄，或 repository 已啟用時的
   GitHub Security Advisory 草稿；不放在公開 Issue、PR、Discussion、commit message 或 Actions log。
2. **確認時限**：`.github/SECURITY.md` 不對外承諾確認或修正時間，本頁也不承諾。維護者在私密
   紀錄寫下第一次回覆通報者的時間；若之後決定對外承諾時限，先以受審查的 PR 寫進
   `.github/SECURITY.md`，再更新本頁。
3. **修正**：確認可重現且需要立即修正時，走 `docs/ci-policy.md`「Hotfix」路由。公開的 Issue、
   PR 標題、commit 與 Release notes 只寫修正範圍（例如「強化某參數的輸入驗證」），不寫重現步驟、
   exploit 細節、受影響的秘密值或通報者身分。「Hotfix 事後紀錄（#1139）」的敏感欄位只留在私密紀錄，公開
   紀錄改寫「見私密紀錄」。
4. **秘密外洩**：通報涉及已外洩的 token、key 或密碼時，先撤銷並輪替，再處理程式修正；任何位置
   都不貼出該值。
5. **公開與關聯**：修正版本發布並讀回後，才決定是否公開細節。公開前先通知通報者；公開時以
   advisory 或 Release notes 連到修正 PR 與版本。修正前不公開。
6. **結案**：私密紀錄寫明結果（已修正的版本、判定不構成漏洞，或屬第三方 dependency 而轉交
   上游），並回覆通報者。

## 私密紀錄格式

每件通報一筆，只存在第 1 步的私密位置；公開的 Issue、PR 與 Release notes 不放這張表。

| 欄位 | 填什麼 |
| --- | --- |
| 收件 | 收件時間、通報管道與收件維護者 |
| 通報者 | 聯絡方式，以及是否同意公開署名 |
| 影響 | 受影響的版本、元件與設定條件 |
| 重現狀態 | `reproduced`、`not-reproduced` 或 `pending`，附重現環境 |
| 第一次回覆 | 回覆通報者的時間與內容摘要 |
| 秘密外洩 | `none`，或已撤銷與輪替的項目（不寫值） |
| 修正 | 公開 Issue 與 PR 編號、修正版本與 Release 讀回結果 |
| 公開 | 公開日期與 advisory 或 Release notes 連結；未公開寫 `not-yet` |
| 結案 | `fixed`、`not-a-vulnerability` 或 `upstream`，以及回覆通報者的時間 |

## 生成專案

生成專案的 `.github/SECURITY.md` 只規定通報入口與不得公開揭露；收到通報後的處理程序屬於各專案
自己的政策。本頁不下發到生成專案，以維持 #1058 `Targets`。
