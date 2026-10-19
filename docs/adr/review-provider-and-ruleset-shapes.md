# Review provider and Ruleset shapes ADR

- **狀態：**Accepted
- **日期：**2026-10-19
- **來源 Issues：**[#1078](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1078), [#1082](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1082), [#1174](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1174)
- **實作 PRs：**[#1132](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/1132), [#1135](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/1135)

## 問題與限制

`review` check、`review_gate.py status` 與 `pr_lifecycle.py merge` 曾對 Copilot 證據與 maintainer 身分各用一套判斷，可能一個入口通過、另一個拒絕；merge 讀 legacy `permission` 欄位，會把 `maintain` 誤判成 `write`。設定也可能組合出平台無法執行的審核路線，例如 Ruleset 要求原生核准、PR 卻只有 Copilot 證據，因此永遠合不了。

已確認的限制：

- Copilot 只會留下 `COMMENTED`，不會 `APPROVED`，不能計入原生核准數。
- 模板不能從方案或 API 推斷 Copilot entitlement 或 billing，只接受明確確認。
- E1 形狀，以及 E6（沒有 Copilot 授權時套用含 `copilot_code_review` 規則的 Ruleset）都未經 live 驗證；E2 以唯讀 GET 或 stub 驗證。

## 決定

擁有者在 #1058 決定 4–7 確認以下規則。逐條件的判定、reason code 與讀回欄位由 [`docs/ci-policy.md`](../ci-policy.md)「Copilot 審核模式（#752）」「單一 maintainer 的可稽核合併路徑（#1076）」兩節，以及 [SPEC-009](../specs/SPEC-009-project-settings.md)「Approval route preflight」負責：

1. **兩個選項各管一件事。**`verification_mode` 只決定證據的 trust；`copilot_review` 只決定可接受的 review provider。Copilot 是可選證據，永遠不是必要條件；沒有 Copilot 審核時，其他合法路徑的結果與 `copilot_review: off` 相同。
2. **只有三種 Ruleset 形狀，不新增。**平台能否執行 Copilot 路線只由形狀決定：
   - **A**（hosted）：0 個原生必要核准，由必要的 `review` check 強制。
   - **E1**（local＋`beta-only`／`always`）：0 個原生必要核准，只有 admin 角色 bypass actor。local 採這個備援形狀；恢復 1 個原生核准的形狀另開 Issue。
   - **C**（local＋`off`）：1 個原生核准加 last-push approval，沒有 bypass actor；只有 Copilot 證據時不能合併。
3. **三個入口共用一個判定。**`review` check、`status` 與 `merge` 呼叫同一個 `review_gate.decide()`，輸入與 reason code 相同。
4. **Maintainer 以 `role_name` 判斷。**只讀即時 `role_name`；缺漏時回報 `unknown` 並 fail closed，不讀 legacy `permission`。admin 專用檢查仍要求 `admin`。
5. **Approval route preflight。**`admin_bypass: off`，以及 `beta-only` 的 stable 路徑，在 render 前做三態 preflight（`route-observed`、`none-observed`、`inconclusive`）；`governance_mode: observe` 只給 `W09`；確認旗標只作用於單次 plan，不是設定鍵。

Ownership：`scripts/review_gate.py`、`scripts/pr_lifecycle.py` 與 CLI setup plan 的維護者負責；以 gate／status／merge 的 contract matrix（self／peer、allowed／off、admin marker、maintain／admin／write、三種形狀）與 preflight fixtures 驗證。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 把 Copilot 設為必要審核者 | 不採用；沒有授權或額度時所有 PR 都會卡住 |
| 依方案、API 或 billing 探測 Copilot 是否可用 | 不採用；方案不等於 entitlement，探測結果無法證明可用 |
| 為每種設定組合新增 Ruleset 形狀 | 不採用；形狀越多，gate、merge 與文件越容易分歧 |
| 繼續以 legacy `permission` 判斷 maintainer | 不採用；`maintain` 會被回報成 `write`，造成誤拒 |
| 在 plan 階段直接認定「只有一位寫入者」並阻擋 | 不採用；collaborator 讀回只是當下觀察，改為三態結果與明確確認 |

## 重新評估條件

- E1 或 E6 取得 live 驗證結果，或 GitHub 改變 Copilot review 的 API 形狀（例如開始產生 `APPROVED`）。
- GitHub 改變 `role_name` 或 Ruleset bypass actor 的語意。
- 恢復 local 1 個原生核准形狀的後續 Issue 完成時，更新 E1 的描述。
