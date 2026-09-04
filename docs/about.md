# 關於 CSARC Repo Template

CSARC Repo Template 是 Cyber-Arch 的可更新 repo 公版：建立新案、導入既有案、接收政策更新，都先驗證再由 PR 合併。可以只使用共通流程，或獨立選擇 Python、Rust、TypeScript。

## 這是什麼

本 repo 維護 Copier 模板、共用 CI、安全檢查與 GitHub 設定草案。`template/` 是下發給使用者專案的內容；根目錄則讓公版本身使用同一套規則（self-hosting）。

目前可用：共通 CI/CD 與可獨立勾選的 Python、Rust、TypeScript 語言模組，以及 Issue／spec、PR checks 與驗證；生成專案另可選配 `enable_docker`，取得 Dockerfile／docker-compose 起始範本與一支唯讀、不推送的容器建置掃描 CI job。自動版本 PR、GitHub Release、打包、checksum 與 SBOM 已進入候選，須由預設分支實跑證明後才算啟用；registry publishing 與通用部署流程仍未啟用，未開啟 `enable_docker` 的專案不會產生任何容器相關檔案、job 或權限。

## 可以直接選擇

| 項目 | 選項 |
| --- | --- |
| 程式語言 | Python、Rust、TypeScript 可獨立複選；都不選時只使用共通工作流程 |
| 分支做法 | 每個交付批次有自己的開發分支、所有修改直接進 `main`，或先集中到 `dev` |
| 公版設定 | 建立／導入時把選項寫入 `.csarc/config.yml`；之後由公版更新，不必到不同檔案重複設定 |

## 共用能力

工作單（Issue）與變更提案（PR）表單、AI 工作規範、自動驗證、依賴安全、版本記錄與公版更新。

## 這份文件的定位

`README.md` 給想導入或使用本範本的一般使用者看「是什麼、要不要用、怎麼開始、去哪裡找更多」；要在本 repo 本身開發，請讀 [`AGENTS.md`](../AGENTS.md)（可執行的工作規則）；要理解「為什麼這樣設計」的決策矩陣與技術細節，請讀[內部決策網站](index.html)。開始安裝或導入，請見[安裝說明](install.md)。
