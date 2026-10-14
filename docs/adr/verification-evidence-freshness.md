# Verification evidence freshness ADR

- **狀態：**Accepted
- **日期：**2026-10-14
- **來源 Issue：**[#1075](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1075)（[#1058](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1058) decision 12）
- **實作 PR：**PR_PLACEHOLDER

## 問題與限制

驗證 evidence 已綁定 repository、exact head／tree、base、tier、scopes、command、toolchain、runner 與 result。這些 identity 能擋下「換了程式碼還沿用舊結果」，卻擋不下「程式碼沒變，但驗證當時依賴的外部狀態已經變了」。過去每個 consumer 各自寫一份 24 小時與 5 分鐘的判斷，沒有文件說明這個期限防的是什麼，也無法保證 local、hosted、merge、release 與 fallback 對同一份 evidence 得到同一個結論。

已確認限制：

- 保留預設 24 小時，不新增設定、不延長或取消期限（#1058 decision 12）。
- 時間判定不能取代 head／tree／toolchain identity；只有 exact identity 相符的可信 evidence 可重用（[#964](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/964) preserved）。
- 本機 evidence 仍是 self-attested，新的 freshness 規則不提高它的可信度（[#908](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/908) preserved）。
- Evidence payload 以 [#1073](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1073) 的 canonical merge evidence 為準；期限不能進入 payload 或 schema。

## 威脅模型

期限防範的威脅：**在 identity 完全相同的情況下，重播一份成功結果，而它所依賴、但不在 Git tree 裡的外部輸入已經改變。** 下列輸入會隨時間改變，且不被 head／tree identity 涵蓋：

| 外部輸入 | 為何會變 | 未設期限的後果 |
| --- | --- | --- |
| GitHub-hosted `ubuntu-latest` runner image | GitHub 定期滾動映像檔、系統套件與預裝工具 | 舊映像上的成功結果代表不了現在的執行環境 |
| 執行時解析的工具版本 | setup step 依 major／minor 線（例如 `Node.js 24`、`Python 3.x`）解析最新 patch | 同一 claim 名稱對應到不同 binary |
| 套件 registry 與 advisory 資料庫 | PyPI、npm、crates、Go proxy 的撤回或新增套件；OSV 等 advisory 每天更新 | 相依性或漏洞檢查的結論已過期 |
| 時間相依的檢查 | 憑證、日期邏輯、到期判斷 | 測試在今天會失敗，舊結果仍顯示成功 |
| GitHub 平台與 Actions 保存期限 | log、annotation 與 job 資料會過期或被重跑覆蓋 | 事後無法重新讀回並核對 evidence |
| 本機環境（local mode） | 操作者的工具鏈與機器狀態隨時可改 | self-attested 結果被無限期重播 |

會被 identity 擋下、因此**不**靠期限處理的變化：程式碼（head／tree）、目標 branch 前進（base／base SHA）、tier 與 scopes、release level 與 tier labels、使用的 command 與 toolchain 宣告、runner 種類、執行結果。

## 決定

1. **單一判定函式。**`scripts/evidence_freshness.py` 的 `require_fresh` 是唯一的 freshness 判定，`policy_max_age_hours` 是唯一的期限來源；生成專案在 `.csarc/scripts/evidence_freshness.py` 收到 byte-identical 副本（`scripts/sync-paired-files.sh` 配對）。所有 consumer 只能呼叫它，不再自行計算時間差：

   | 路徑 | Consumer | 進入點 |
   | --- | --- | --- |
   | Hosted CI | `ci.yml` 的 merge-source 與 same-head reuse 查詢 | `check-trusted-verification` → `pr_lifecycle.require_trusted_verification` → `verification_evidence.validate_verification_job` |
   | Merge queue | `merge_group` 事件 | 同上，由同一份 `ci.yml` 執行 |
   | Merge（hosted） | `pr_lifecycle.py merge` | `require_successful_checks` → `require_trusted_verification` |
   | Merge（local） | `pr_lifecycle.py merge` 在 local mode | `local_verification.require` |
   | Release | `release.yml` | `check-trusted-verification --resolve-merge-source` |
   | Promotion | `promotion_gate.py` | `check-trusted-verification --required-tier full` |
   | Quota fallback | `pr_lifecycle.py merge` 的 quota fallback 路徑 | 成功的 `verify` 仍走 `require_trusted_verification`；fallback 不能替代 `verify` |
   | Clean sync／same-head reuse | `ci.yml` reuse 與 sync step | 以原始 direct Execute 的完成時間計算，reuse run 自己的時間不能刷新期限 |

   不屬於 evidence freshness、因此不由本函式管理的時間窗：`finalization-queue` 的 intent 到期（只是協調提示）、remote lifecycle lease TTL，以及 `check-release-drift` 的發版落後門檻。

2. **時間語意。**一律以 aware UTC 比較；完成時間或參考時間缺少 timezone 時 fail closed，不以主機時區猜測。完成時間缺漏、空字串或格式錯誤時 fail closed。期限含端點：恰好 24 小時仍算 fresh，再晚任何一刻即 stale。完成時間最多可超前參考時間 5 分鐘，以吸收 runner、GitHub API 與本機 NTP 的時鐘偏差；超過即拒絕，避免未來時間延長期限。

3. **24 小時預設的理由。**一個 PR 從 Ready、review 到 merge 通常在一個工作日內完成，跨時區或隔夜 review 也落在 24 小時內；runner image 與 advisory 資料以天或週為更新單位，24 小時把外部漂移限制在至多一天。期限也遠短於 Actions log 保存期，merge 時仍能重新讀回 job 與 annotation。核准版技術手冊 §4.3 對使用者承諾 local 與 hosted 證據都「24 小時內有效，逾期或 head 改變即重跑」。

4. **期限是 trusted policy parameter。**期限寫在受信任的 script 常數，不寫入 local evidence（固定欄位集合，多一個欄位即視為 malformed）、hosted payload 或 merge trace schema。呼叫端只能**縮短**期限：`--max-age-hours` 或 `max_age_hours` 大於 24、非正數、非有限值或布林值都 fail closed。Hosted gate 從 trusted base 複製 script 後才驗證 candidate，所以 candidate 即使改了自己的 `evidence_freshness.py`，也影響不了審查它的那一次 gate。

5. **Freshness 只是必要條件。**通過 freshness 之後，repository、head、tree、base、tier、scopes、command、toolchain、runner 與 result 綁定仍然逐項檢查；任何一項不符，新鮮的 evidence 一樣被拒絕。

## False negative 與可用性的取捨

- 結果相同、只是超過期限的 evidence 會被拒絕（false negative）。代價是多跑一次驗證；在 Actions 額度受限的 repository 中，這會消耗 hosted 額度。期限內的 metadata、label 等同 head 事件已能引用原始 Execute，不必重跑。
- 更短（例如 4 小時）會讓隔夜 review 幾乎必然重跑，額度與等待時間都變差；更長（例如 7 天）等於接受一整個 runner image 週期的漂移。
- 5 分鐘時鐘偏差容忍讓 GitHub 與本機時間的小誤差不會隨機阻擋 merge；超過這個值通常代表時鐘錯誤，應修正時鐘而不是放寬判定。

## 重新驗證路徑

- **Hosted：**在同一個 exact head 重新執行 `verify`（re-run workflow、Ready 或 label 事件）。期限已過時 same-head reuse 查不到可引用的原始 Execute，因此會實際執行一次新的驗證。
- **Local：**在乾淨的 exact head 重新執行 `./scripts/verify-fast`（或 full），寫入新的完成時間。
- **Merge：**`pr_lifecycle.py merge` 在 merge 當下重讀 evidence；stale 時錯誤訊息要求在 exact head 重新驗證，不提供 override。
- **Release：**`release.yml` 在發版當下重新檢查來源 PR 的 evidence，它必須仍在期限內；若發版延誤超過期限，依 `docs/ci-policy.md` 的 release-recovery 路徑處理，不手動放寬期限。

## 評估過的替代方案

| 結論 | 方案 | 理由 |
| --- | --- | --- |
| Rejected | 取消期限，只靠 identity | 擋不下上表的外部輸入漂移 |
| Rejected | 在 `.csarc/config.yml` 提供可調期限 | 新增設定違反範圍，且設定由 candidate 控制 |
| Rejected | 把期限寫進 evidence payload | candidate 或寫入者可以替自己的舊 evidence 延長期限 |
| Rejected | 各 consumer 保留自己的判定 | 邊界與時區不一致會造成隨機阻擋，也無法保證同一結論 |
| Preserved | 24 小時預設與 5 分鐘時鐘偏差 | 見上方理由 |

## Ownership 與驗證

`tests/test_evidence_freshness.py` 驗證邊界（恰好到期、未來時間、時鐘偏差、缺漏或 naive 時間、時區換算、政策收緊與重新驗證、拒絕放寬），並逐一掃描兩層 consumer，確認它們不再自行計算期限；`tests/test_verification_evidence.py` 與 `tests/test_local_verification.py` 在真實 consumer 上驗證同一組邊界、拒絕放寬、payload 不能夾帶期限，以及新鮮 evidence 仍需全部 identity 綁定；`tests/test_verification_evidence.py` 也以生成專案的 `.csarc` reader 驗證同一邊界與拒絕放寬。

## 重新評估條件

- runner image 或工具鏈可以完全鎖定（例如固定 image digest），外部漂移明顯降低時，可評估延長期限。
- 觀察到期限造成的重跑大量消耗 Actions 額度或延誤 merge。
- 新增任何 evidence consumer 時，必須呼叫 `require_fresh` 並加入 consumer 掃描清單。
