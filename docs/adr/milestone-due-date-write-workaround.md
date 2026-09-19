# Milestone due-date write workaround ADR

- **狀態：**Accepted
- **日期：**2026-09-18
- **來源 Issue：**[#741](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/741)
- **實作 PR：**[#767](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/767)

## 問題與限制

`scripts/create-milestone` 建立 Milestone 時，原本以 UTC 午夜（`due_on=<date>T00:00:00Z`）寫入 due date。Milestone 14（#740）建立時親身遇到：傳入 `--due-on 2026-10-01`，GitHub 實際儲存並回傳的是 `2026-09-30T00:00:00Z`——早了一天。

尚未找到 GitHub 官方文件或既有 Issue 記錄這個行為的確切觸發條件；不確定是伺服器端固定的正規化規則、時區相關的邊界換算，還是其他機制。已知的是：改用 `due_on=<date>T12:00:00Z`（UTC 中午）寫入，目前已重現的案例都不再出現這個位移。由於機制未確認，不能保證中午寫入涵蓋所有情況，也不能排除 GitHub 之後改變這個行為。

## 決定

`scripts/create-milestone` 一律以 `<date>T12:00:00Z` 寫入 due date（見 script 內建立 Milestone 的 `gh api --method POST` 呼叫），並在寫入後立即讀回 `due_on`、逐字比對日期部分與請求值是否一致；不一致時 fail closed，印出 Requested／Actual 兩個值，且不繼續建立 tracker Issue。

這是兩層獨立防禦：中午寫入是目前已知能避開重現案例的具體做法，讀回比對則是不依賴任何特定機制假設的安全網——即使日後出現中午寫入仍然位移的新案例，或 GitHub 改變行為，這層比對仍會攔下不一致，不會讓錯誤的 due date 悄悄流入後續的 tracker Issue 建立與 preflight 檢查。

程式碼與說明文字刻意用「GitHub sometimes stores/returns an earlier date... under a mechanism this repo hasn't root-caused」這類保守措辭，不斷言確切成因（例如不斷言是「時區」造成），避免文件與訊息主張一個尚未驗證的機制。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 只改寫入時間點（`T12:00:00Z`），不加讀回比對 | 不採用；機制未確認，無法保證涵蓋所有情況，讀回比對是必要的獨立安全網。 |
| 只加讀回比對，寫入時間仍用 `T00:00:00Z` | 不採用；已知重現案例下一定會 fail closed，體驗比先用目前已知較不易觸發的時間點差，且每次都要人工介入。 |
| 改用 GitHub 網頁 UI 的日期選擇器建立 Milestone，避開 API 寫入 | 不採用；違反 #572 既定「一次呼叫原子建立 Milestone 與 tracker」設計，且無法自動化、無法在 CI 或腳本中重現。 |
| 從 POST 回應本身讀 `due_on`，省略額外的 GET 讀回 | 不採用為預設；POST 回應理論上也可能反映相同的儲存值，但額外一次獨立讀取能確認 preflight 及任何之後的讀者看到的是同一個持久化值，而非單次寫入請求在任何最終一致性延遲穩定前回顯的內容。額外的 API 呼叫成本很低，換取的驗證獨立性值得保留。 |

## Ownership 與驗證

`scripts/test-create-milestone` 的 fake `gh` 有 `FAKE_GH_DUE_ON_BUG` 開關，模擬 GitHub 把 due date 存成前一天，驗證讀回比對會 fail closed 並印出正確的 Requested／Actual 值（Case 8），以及一致情境下正常成功（Case 5、Case 9 涵蓋的一般成功路徑）。

## 重新評估條件

GitHub 官方確認或修正這個 due_on 儲存行為時，或本 repo 觀察到 `T12:00:00Z` 寫入仍然被錯誤儲存的新案例時，重新評估寫入時間點的選擇與讀回比對邏輯是否仍然足夠。
