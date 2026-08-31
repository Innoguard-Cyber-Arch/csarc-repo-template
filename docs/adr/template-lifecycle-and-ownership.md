# Template lifecycle and ownership ADR

- **狀態：**Accepted
- **日期：**2026-08-24
- **來源 Issues：**[#7](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/7), [#31](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/31), [#76](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/76), [#113](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/113), [#116](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/116), [#157](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/157), [#411](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/411)
- **實作 PRs：**[#8](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/8), [#53](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/53), [#88](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/88), [#115](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/115), [#124](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/124), [#160](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/160), [#412](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/412)

## 問題與限制

公版本身與 consuming project 共用大量治理檔案，但產品 source、spec、decision、README 與網站內容不能被模板更新靜默覆寫。Root 與 template 的重複檔若只靠人手同步，也會在測試前漂移。

## 決定

- `copier.yml`、`template/`、`policies/` 與 `profiles/catalog.yaml` 定義可版本化產品；root 是公版本身的 dogfood 實例。
- 完全相同的 root／template 檔案由 `scripts/sync-paired-files.sh` 以 root 為來源產生；參數化或刻意不同的檔案由生成 fixture 驗證。
- `docs/specs/**/*.md`、產品 source／tests 與網站內容等 project-owned 檔案在 update 時保留。
- `csarc init/adopt/update` 先解析 immutable release 與完整 SHA，dry-run 不改 target；正式操作仍不自動 push、開 PR 或套遠端 settings。
- 任何 conflict marker 或 `.rej` 使驗證失敗；不能把 Copier 完成等同產品語意已整合。
- 成熟度證據分兩層：真實 consuming repo 證明共用導入、更新與線上 CI 邊界；各語言模組以建立、既有 repo 導入、更新與原生工具鏈的可重現測試取得 beta，不為每種語言建立專用測試 repo。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | 四種 profile、單一公版與 generated-project verification | [#7](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/7)／[#8](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/8) |
| Preserved | 更新衝突 fail closed | [#31](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/31)／[#53](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/53) |
| Superseded | 人工雙改 byte-identical root／template 檔案 | [#76](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/76)／[#88](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/88) |
| Unresolved | 現有 adopt 在 manual merge 後的 resumability 與 transaction boundary | [#196](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/196)／[#219](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/219) |

## Ownership 與驗證

公版維護 renderer、governance、workflow 與 deterministic migration；專案維護產品 source、規格、決策與允許的內容覆寫。Create、adopt、update、conflict、preservation 與每個 beta 語言的原生工具鏈都必須出現在 `./scripts/verify-template.sh` 的實際生成測資。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 所有 root／template 檔案一律 byte-identical | 不採用；Jinja 參數化與不同 audience 是真實差異 |
| 更新時覆寫所有文件 | 不採用；會破壞產品自有記憶與操作內容 |
| 通用自動 merge engine | 未採用；目前使用固定 ownership 與明確 manual review 較安全 |
| 每個語言各養一個專用 GitHub 測試 repo | 不採用；重複驗證共用導入機制，且產生額外維運與漂移成本 |

## 重新評估條件

Open adoption Issues 完成後，依實際 transaction、plan replay 與 metadata contract 更新本紀錄；在它們合併前不得把候選行為寫成 active。
