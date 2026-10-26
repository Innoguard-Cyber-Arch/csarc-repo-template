# 文件生命週期與授權契約

這份契約把「文件怎麼呈現」與「專案說了什麼」分開，讓公版可以更新版型，而不覆寫專案事實。

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
| `documentation_languages` | `zh-tw`／`en`／`zh-tw+en`／`en+zh-tw` | 第一個語言決定 `README.md` 與主要入口；有第二個語言時另產生 `README.<lang>.md` 並維護雙語公版入口。只管 project-owned 文件 |

授權與著作權人是 create／adopt 的一次性 seed，不是設定：`project_license`（`proprietary`／`MIT`／`Apache-2.0`，未明確選擇時一律 `proprietary`，不得推定為開源；`custom` 表示產品自行管理授權，CSARC 不產生 `LICENSE`、manifest 不寫 license 欄位）與 `copyright_holder`（不得由 GitHub 帳號、CODEOWNERS 或 commit 作者推定）只寫進 `LICENSE` 與 package manifest，之後以 `LICENSE` 為準。

舊設定由外部 CLI 的 migration registry 唯讀遷移：`features: repo-site` 為 `documentation_mode: template-and-content`，沒有 repo-site 為 `content-only`；`primary_language`＋`i18n`（或更早的 `readme_primary_language`）合併為 `documentation_languages`。遷移完成後只保留目前 schema。

## 持久化專案記憶（Durable Project Memory）

這份文件地圖由 CSARC 維護，說明跨 session、跨 agent 與跨時間都要留下的專案知識放在哪裡；`.csarc/scripts/verify` 只檢查這裡，不檢查專案擁有的 `docs/README.md` 內容。

| 問題 | 位置 |
| --- | --- |
| 現在必須做到什麼？ | `docs/specs/` 的 living Spec-Driven Development（SDD）契約 |
| 為什麼這樣選？ | `docs/adr/` 的 Architecture Decision Records（ADR） |
| 行為是否仍成立？ | Test-Driven Development（TDD）、Behavior-Driven Development（BDD）、CI 與 release evidence |

從舊版公版更新的專案可能仍有 project-owned `docs/decisions/`；搜尋時一併讀取，新紀錄寫入 `docs/adr/`，不自動搬移或覆寫既有內容。`docs/README.md` 是專案自己的文件入口，更新不會改寫它。

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

## 寫作指引

英文寫作指引 [`writing-guide.en.md`](writing-guide.en.md) 與中文寫作指引 `writing-guide.md`（文件語言含繁體中文時產生）和本文件放在同一目錄，屬於文件模板層：由 CSARC 公版維護，Copier update 會更新。模板產生的文字一律遵守。內容層的文件，agent 新寫或修改時依指引撰寫；既有內容不會被自動改寫。

## AI 文件一致性 review

每個非 Draft 交付候選都要由本機 AI 比對 changed paths、current specs、公開介面、設定、測試與專案文件，並在 PR 的「文件一致性」區塊記錄 exact head：

| Status | 是否可交付 | 意義 |
| --- | --- | --- |
| `aligned` | 是 | 需要的文件已更新，內容與候選版本一致 |
| `not-applicable` | 是，但必須寫理由 | 變更不影響使用者或維運者可觀察的文件事實 |
| `drift` | 否 | 已確認實作與文件不一致 |
| `inconclusive` | 否 | 資訊不足，無法可靠判斷 |

`off` 是專案模式，不是 review 結果。PR policy 只做確定性的欄位、狀態與 exact-head 檢查；它不在 GitHub runner 再呼叫 AI。新 push 會讓舊 head 失效，release PR 也必須針對自己的 exact head 更新紀錄。Release job 只消費通過門禁的候選版與既有驗證鏈，不增加 workflow、runner 或另一套測試矩陣。

adopt／update 另在 lifecycle report 的 `Policy documentation` 段落，針對新增或改變的 managed policy 以中英文 keyword map 離線掃描 project-owned README 與 `docs/`；不讀 `.csarc/`、不呼叫 AI、不自動改寫。PR 的 `Reason` 必須逐 key 記錄新值、四態結果與候選 `file:line`，aggregate `drift`／`inconclusive` 繼續阻擋交付；`not-applicable` 也保留理由。這個 deterministic 檢查只能找出已知語句，不能取代擁有者的語意審查。

## 授權同步

`LICENSE`、README、Python／npm／Cargo manifest、封裝內容、release metadata 與 SPDX SBOM 必須表達同一授權。專有模式使用 `LicenseRef-Proprietary`（Python／SPDX）、`UNLICENSED` 加禁止公開發布（npm），以及 `license-file = "LICENSE"`（Cargo）。既有專案已有授權時一律保留；設定與現有檔案衝突時停止更新並要求 owner 決定，不能猜測或自動換授權。
