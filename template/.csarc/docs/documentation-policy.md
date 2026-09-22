# 文件生命週期與授權契約

這份契約把「文件怎麼呈現」與「專案實際說了什麼」分開，讓公版可以更新版型，而不覆寫專案事實。

## 兩層責任

| 層級 | Owner | 內容 |
| --- | --- | --- |
| 文件模板 | CSARC 公版 | renderer、layout、theme tokens、navigation schema、i18n 切換、輸出路徑、遷移與結構檢查 |
| 文件內容 | consuming project | 功能、安裝與使用方式、API／CLI／設定、架構理由、維運與支援事實 |

Copier update 可以更新第一層；第二層首次建立後必須保留。若結構遷移無法無損完成，更新應提出人工步驟並 fail closed，不得靜默覆寫或搬移內容。

## 核心設定

| 設定 | 值 | 行為 |
| --- | --- | --- |
| `documentation_mode` | `template-and-content` | 產生並更新公版呈現層，建立專案內容起始檔，驗證兩層 |
|  | `content-only` | 不產生公版網站；只建立、保留並整理專案內容與 README |
|  | `off` | 不產生、不整理，也不要求文件一致性 review；既有 project-owned 文件不會被刪除 |
| `primary_language` | `en`／`zh-tw` | 決定 `README.md` 與主要入口使用的語言 |
| `i18n` | `en-zh-tw`／`off` | 雙語時產生另一語言的 `README.<lang>.md`，並維護雙語公版入口；關閉時只保證主要語言 |
| `project_license` | `proprietary`／`MIT`／`Apache-2.0` | 未明確選擇時一律採 `proprietary`，不得推定為開源 |
| `copyright_holder` | 非空字串 | 寫入 `LICENSE`；不得由 GitHub 帳號、CODEOWNERS 或 commit 作者推定 |

舊設定 `features: repo-site` 遷移為 `documentation_mode: template-and-content`，沒有 repo-site 的舊設定遷移為 `content-only`；`readme_primary_language` 遷移為 `primary_language`。遷移完成後只保留新設定。

## 共同資訊架構

文件只需要覆蓋適用的五種讀者任務，不強制五個目錄或五份檔案；一份文件可以同時承擔多個角色，沒有內容時不要建立空頁。

| 角色 | 預設應回答的問題 |
| --- | --- |
| 開始使用 | 這是什麼、適不適合我、如何安裝、最短成功路徑是什麼？ |
| 日常使用 | 常見工作怎麼做、輸入輸出與範例是什麼？ |
| 精確參考 | API、CLI、設定、相容性與錯誤行為是什麼？ |
| 理解與維運 | 架構與限制為何、如何部署、觀測、復原與除錯？ |
| 專案生命週期 | 如何貢獻、回報安全問題、升級、閱讀變更紀錄與授權？ |

README 只作為濃縮入口：標題與一句話、少量徽章、二至五項價值、安裝、最小 quick start、文件連結、相容性、支援／安全、貢獻與授權。不要放 badge wall、大型目錄、完整治理矩陣、架構全文或 changelog 副本。README 與深度文件不要求逐字或逐段一致，但公開事實、命令、連結、支援狀態與授權不得互相矛盾。

## AI 文件一致性 review

每個非 Draft 交付候選都要由本機 AI 比對 changed paths、current specs、公開介面、設定、測試與專案文件，並在 PR 的「文件一致性」區塊記錄 exact head：

| Status | 是否可交付 | 意義 |
| --- | --- | --- |
| `aligned` | 是 | 需要的文件已更新，內容與候選版本一致 |
| `not-applicable` | 是，但必須寫理由 | 變更不影響使用者或維運者可觀察的文件事實 |
| `drift` | 否 | 已確認實作與文件不一致 |
| `inconclusive` | 否 | 資訊不足，無法可靠判斷 |

`off` 是專案模式，不是 review 結果。PR policy 只做確定性的欄位、狀態與 exact-head 檢查；它不在 GitHub runner 再呼叫 AI。新 push 會讓舊 head 失效，release PR 也必須針對自己的 exact head 更新紀錄。Release job 只消費通過門禁的候選版與既有驗證鏈，不增加 workflow、runner 或另一套測試矩陣。

## 授權同步

`LICENSE`、README、Python／npm／Cargo manifest、封裝內容、release metadata 與 SPDX SBOM 必須表達同一授權。專有模式使用 `LicenseRef-Proprietary`（Python／SPDX）、`UNLICENSED` 加禁止公開發布（npm），以及 `license-file = "LICENSE"`（Cargo）。既有專案已有授權時一律保留；設定與現有檔案衝突時停止更新並要求 owner 決定，不能猜測或自動換授權。
