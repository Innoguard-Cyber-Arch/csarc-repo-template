# 寫作指引與腳本訊息句型

- **狀態：**Accepted
- **日期：**2026-10-23
- **來源 Issues：**[#1217](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1217)、[#1218](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1218)
- **實作 PR：**[#1226](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/1226)

## 問題與限制

模板與它產生的專案沒有共同的寫作規則。腳本錯誤訊息句型不一，同一種失敗有多種說法；文件、表單與 agent 指示各自累積不同的語氣、用詞與標點。agent 依現有文字寫新內容，只會把不一致繼續複製下去，下游專案也沒有可以照著寫的標準。

已確認的限制：

- ASD-STE100 Issue 9 的規則原文與詞典受 ASD 著作權保護，不能放進公開的模板，ASD 也不認證任何工具。模板只能以自有文字參考它的精神，不能宣稱合規。
- STE 只定義英文。繁體中文需要另一套規則。
- 生成專案的 payload 有 #1058 `Targets`，hosted fixture 的餘裕已經不多；不能為了指引調高 `Targets`。
- `docs/documentation-policy.md` 的模板層與內容層分界維持不變：Copier 不覆寫下游的內容層文件。

## 決定

擁有者在 2026-10-23 決定：

1. 正式採用英文寫作指引 `docs/writing-guide.en.md`。規則以模板自有文字撰寫，只註明參考 ASD-STE100 Issue 9；不收錄 STE 規則原文或詞典，不宣稱 STE 合規。專案術語以 `site/data/glossary.toml` 與現行規格為準。
2. 採用中文寫作指引 `docs/writing-guide.md`。它整合 speak-human-tw v1.4.0（commit `72279f8`）的規則重點，保留 MIT 授權聲明（Copyright (c) 2026 Raymond Hou）並註明版本；完整規則以連結指向原專案。標點以教育部《重訂標點符號手冊》為準。下游可以自行使用該 skill 校稿，模板不安裝、也不依賴它。
3. 模板替下游決定寫作風格：模板擁有的文字一律遵守；指引經 root `AGENTS.md` 與生成專案的 `AGENTS.md` 以連結交給 agent，不重抄規則；下游既有的內容層文件只收到檢查提示，不會被自動改寫。
4. 腳本訊息採用固定句型（error、warning、notice、success 各一種），例外只限英文指引列出的條件，並在原始碼中逐筆記錄理由。`scripts/check-message-style` 在模板 repo 的 fast 與 full verify 檢查相對 base 新增或修改的訊息行，`--all` 供全量盤點（#1219）。模板 repo 的檢查範圍也包含 `src/csarc_cli`。生成專案的 `.csarc/scripts/verify` 與 `verify-fast` 也執行同一支檢查（#1221）。
5. 不安裝第三方工具或社群 skill，包括 Vale、LanguageTool 與商業 STE 檢查器。
6. 指引屬於文件模板層。生成專案在 `.csarc/docs/` 收到英文指引；文件語言含繁體中文時另外收到中文指引。中文指引與 root 版本逐位元組相同，由 `scripts/sync-paired-files.sh --check` 驗證；英文指引只在術語來源與相關連結上不同，由 `tests/test_writing_guides.py` 驗證。

## 評估過的替代方案

- **正式 STE 合規**：需要 ASD 書面授權或商業檢查器，詞典不能公開散布，也無法涵蓋中文。駁回。
- **只在 root 採用、不下發**：下游 agent 沒有可以照著寫的標準，與「替下游決定寫作風格」的決定衝突。駁回。
- **安裝社群 STE skill 或 speak-human-tw**：增加 prompt 供應鏈依賴，且下游無法離線取得。駁回；中文規則改為整合重點並註明出處。
- **Vale 或其他 prose linter**：需要在 CI 安裝外部 binary，誤判多，且要另外處理中英混排。駁回；只有腳本訊息句型做成模板自有的可執行檢查。
- **一律下發兩份指引**：純英文專案用不到中文指引，會佔用 payload 餘裕。改為依 `documentation_languages` 決定。

## 重新評估條件

- ASD 改變授權條件，允許在開源專案中重製規則或詞典。
- speak-human-tw 發布會改變本指引所整理規則的新版本；更新時同步修改版本、commit 與授權聲明。
- 腳本訊息檢查的例外持續增加，表示句型不適合實際用途。
- 新增中英文以外的文件語言。
- 指引讓生成專案超出 `Targets`；先精簡指引，不調高 `Targets`。
