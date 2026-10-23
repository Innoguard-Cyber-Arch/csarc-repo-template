# Dry-run inventory before action（先盤點、再動作）ADR

- **狀態：**Accepted
- **日期：**2026-10-23
- **來源 Issue：**[#1239](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1239)
- **實作 PR：**[#1241](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/1241)

## 問題與限制

有些流程要把尚未驗證的內容帶進來，或依它採取動作：下游 release、candidate PR、外部 repo 的設定或程式碼。如果直接執行或套用這些內容，錯誤或惡意內容在任何人看清楚之前就已經生效。#1239 的初版做法是執行已發布 release 的 `csarc_config.py` 來判讀新設定。release 雖然 immutable，這仍等於在持有 token 的 trusted base 裡執行下載來的程式碼。擁有者 2026-10-23 否決了這個做法，並把以下原則定為核心設計。

已確認的限制：

- 盤點只能確認形狀與來源，不能取代完整驗證。完整的值驗證要等內容真正落地（例如下游升級完成），由當時的 reader 執行。
- 盤點本身也只讀可驗證的來源：immutable release、exact commit、GitHub API 讀回的資料。PR 自己提供的內容永遠不能拿來證明它自己。

## 決定

凡是會帶入或執行未經驗證內容的流程，都先產生唯讀、人看得懂的盤點，再決定要不要動作：

1. **先盤點。**以不執行的方式讀取內容（解析、比對、計算 digest），逐項列出要帶入什麼、來自哪裡、是否符合預期。
2. **意外就停。**盤點只要有一項不符預期，就 fail closed。訊息依寫作指引句型說明原因，附上盤點，並給出具體的下一步。
3. **不執行下載來的程式碼。**需要從外部程式碼取得資訊時，用 `ast` 或資料檔讀取字面值，不 `exec`、不 import。

既有先例：

- `csarc adopt` 預設 dry-run，產生 machine plan 與報告，授權後才套用同一份 plan（[transactional-repository-adoption](transactional-repository-adoption.md)）。
- `csarc update --check` 先產出更新計畫並驗證 hook 設定，不執行 hook。
- `release_policy.py prepare-candidate` 先檢查並物化 release 候選，經 PR 審查後才發布。
- #1239：trusted base 用 `ast` 讀取 release 的設定表，逐一盤點 base 不認得的新設定（是否為該 release 所知、值的基本型別），全部相符才放行，並記錄 `schema_source=release:<tag>`。

設計審查必須檢查新流程是否符合這三點；不符合時，要在 PR 說明理由並取得擁有者確認。Ownership：引入外部內容的各流程維護者負責。#1239 的回歸由 `tests/test_release_schema_upgrade.py` 驗證，其中包含「release 程式碼不會被執行」的測試。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 執行 immutable release 的 reader，取得完整驗證 | 不採用；等於在 trusted base 內執行下載的程式碼，違反第 3 點 |
| 信任 PR 內 candidate 自己的 reader | 不採用；candidate 不能證明自己（[trusted-base-gate](trusted-base-gate.md)） |
| 一律人工合併新設定 | 不採用；每次模板升級都會失去 merge trace |

## 重新評估條件

如果某個流程的盤點無法在不執行的情況下取得必要資訊，要先開 Issue 由擁有者決定，不能默默放寬。若 `csarc_config.py` 的設定表不再是字面值，#1239 的盤點會 fail closed；屆時改以資料檔發布 schema，或重新評估本決定。
