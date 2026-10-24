# Trusted-base merge and verification gate ADR

- **狀態：**Accepted
- **日期：**2026-10-19
- **來源 Issues：**[#1069](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1069), [#1086](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1086), [#1174](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1174)
- **實作 PRs：**[#1092](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/1092), [#1108](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/1108), [#1122](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/1122)

## 問題與限制

Milestone 18 之前，local merge 會讀 candidate PR 自己的設定與 gate，hosted `verify` 也可能執行 candidate 的 entrypoint。PR 因此能修改驗證或合併規則，再用改過的規則判定自己通過；改設定 schema 的 PR 也沒有一個可信的 reader 能判讀新格式。

已確認的限制：

- `pull_request_target` gate 的 workflow YAML 永遠來自 default branch，delivery branch 上的 gate 變更需要先在 `main` 生效（#1086 因此以 standalone 先於 Milestone 18 完成）。
- trusted base 防的是 candidate 改 gate 讓自己通過，不是惡意測試碼的 sandbox；最終仍靠 required checks、唯讀權限與人工審查。
- 啟動 lifecycle 的入口仍由操作者執行；要完全不經 candidate 程式碼，操作者需從 detached base worktree 執行（步驟見 `docs/ci-policy.md`）。

## 決定

擁有者在 #1058 決定 8、9 確認以下規則。詳細操作與限制由 [`docs/ci-policy.md`](../ci-policy.md)「`verify` 的可信 hosted execution evidence（#834）」與「Base-commit merge 與驗證政策（#1069）」兩節負責，本 ADR 不重抄：

1. **依 base commit 決定。**合併、驗證與 route 判定在 hosted 與 local 兩種模式都只用 trusted base 的政策、gate、router 與 config reader；candidate 只是被驗的 exact head。root 由 #1086 先在 `main` 完成，template 由 #1069 完成，兩者共用 byte-identical 的 `trusted_executor.py`。
2. **Candidate 只做不決定結果的自我測試。**candidate 自己的 parser、gate 與 route 只在 `policy_self_test` 重播，差異列在輸出，不改變 base 的決定。
3. **Schema 先讀後寫。**新的設定 schema 必須先由 trusted base 的唯讀、fail-closed reader 支援，writer 才切換；未知 schema、退役或未知鍵一律 fail closed，不補預設。
4. **Schema 1 證據只能讀。**schema 1 的驗證證據可以讀取與顯示，但永遠不能用於合併；lifecycle 改印出以 base gate 重跑的指令。
5. **`governance-switch` route。**改動 `.csarc/scripts/`、放寬治理值、變更設定 schema，或無法取得完整變更清單時，PR 必須帶 `governance-switch` label；每張 `csarc update` PR 都走這條 route。它不放寬任何控制：required checks、exact-head 授權與 remote lease 照常要求。hosted 一般 PR 只跑一次 gate；改動 gate 的 PR 另跑一次不決定結果的候選自我測試。

Ownership：`scripts/trusted_executor.py`、`scripts/pr_lifecycle.py` 與 `validate-pr-policy` 的維護者負責；回歸由 malicious-candidate、unknown-schema、governance-switch 與一般 PR 的 contract tests 驗證，hosted 證據由 `scripts/check-trusted-verification` 讀回。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 繼續執行 candidate 的 gate，靠審查發現竄改 | 不採用；審查無法可靠發現讓自己通過的 gate 變更 |
| reader 與 writer 在同一張 PR 切換新 schema | 不採用；base 讀不懂新格式，schema PR 會永久阻塞，或被迫信任 candidate parser |
| 過渡期讓 schema 1 證據仍可合併 | 不採用；舊證據沒有綁定 trusted base 的 control set |
| 治理放寬走一般 route，只靠 PR 說明 | 不採用；放寬必須在 route 上可辨識，才能要求額外審查 |
| 加一個 required check 取代 base 載入 | 不採用；只增加檢查數量，沒有解決 candidate 決定結果的問題 |

## 重新評估條件

- GitHub 改變 `pull_request_target` 或 workflow 載入模型，使 trusted base 無法在不暴露 token 的情況下讀到 candidate tree。
- 需要讓 candidate 程式碼在 sandbox 中執行並取得可信結果（例如惡意測試碼成為實際威脅）時，另開 Issue 評估隔離執行。
- governance-switch 變成多數 PR 的常態路線時，重新檢查放寬值清單是否過寬。
