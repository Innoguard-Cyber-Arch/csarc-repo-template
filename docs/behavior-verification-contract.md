# 行為驗證契約

本文件定義每類風險應由哪一層驗證，避免同一行為被單元測試、字串比對、
generated fixture 與 workflow 重複檢查。原則是先使用能重現失敗的最窄測試；
只有跨 runtime、候選版本或 GitHub 平台邊界無法在較窄層表達時，才升級證據層級。

## 各層責任

| 層級 | 唯一責任 | 不負責 |
| --- | --- | --- |
| Unit／policy test | 純函式、CLI 寫入邊界、路由與 fail-closed 決策；以故意輸入失敗案例鎖定可觀察行為 | 文件逐字內容、GitHub runner 是否真的啟動 |
| Generated fixture | Copier 各 profile 能產生、更新並執行宣告的命令；root／template 配對檔案一致 | 重跑已由 unit test 覆蓋的所有分支 |
| Workflow lint／static contract | YAML 語法、固定 action SHA、權限、job wiring 與 aggregate fail-closed | 模擬 hosted runner、Ruleset 或 environment approval |
| Cross-runtime | runtime-sensitive 相容性；Python 支援範圍各跑一次，TypeScript 不因 Python matrix 重複 | 與 runtime 無關的 policy test |
| Promotion E2E | 候選 archive、SHA／tree identity、完整 `verify`、canary 三態與 main handoff | 取代單元測試或把 artifact-only 宣稱成 live success |
| Live evidence | GitHub Ruleset、hosted job、權限、額度、environment、release／attestation identity 的實際結果 | 取代可在本機重現的失敗回歸 |

新 regression 先放在 unit／policy test。若同一失敗已由較窄測試覆蓋，不再加入文件
逐字 grep；static contract 只保留會改變執行邊界的結構。Generated fixture 只驗證
render 後才存在的行為，cross-runtime 只驗證 runtime 差異。

## 風險與最窄回歸對照

下表的「故意失敗」案例必須保留，讓每個 fail-closed 邊界都能由維護者直接觸發。

| 行為／風險 | 最窄可重現的失敗回歸 | E2E／live 證據 | 盤點結論 |
| --- | --- | --- | --- |
| Release 能力或來源不明不得發布 | `tests/test_release_policy.py::test_release_mode_is_fail_closed`、`test_release_source_must_match_the_tag_commit` | `release-please.yml` 的 release-source 與 artifact handoff；真實 tag／Release 屬 live | 保留；unit 決策與 hosted 發布邊界不同，不是重複 |
| Secret 不得留在 worktree 或 Git history | `scripts/verify-template.sh` 建立兩個合成 secret，要求 `scripts/scan-secrets` 拒絕 | CI fast／full 的 Gitleaks 執行結果 | 保留；合成 fixture 是可故意觸發的 negative regression |
| Supply-chain 變更不得略過掃描 | `tests/test_ci_tier.py::test_risk_scopes_enable_only_their_expensive_check` 以 `uv.lock` 要求 OSV；`test_promotion_and_hotfix_use_full_tier` 要求 OSV 與 Zizmor | hosted OSV reusable workflow、Zizmor 與週期性掃描 | 保留；standalone workflow 不再對每張 PR 重複，live 漏洞結果屬平台證據 |
| Provenance 身分或成品 digest 不符不得消費 | `tests/test_release_consumption.py::test_rejects_missing_attestation`、`test_rejects_wrong_repository_identity`、`test_rejects_tampered_artifact` | `release-consumption.yml` 下載真實 artifact 後再做 controlled tamper | 保留；本機 parser 與 GitHub attestation identity 分屬兩個邊界 |
| 未知路徑不得降為便宜 tier | `tests/test_ci_tier.py::test_unknown_and_missing_paths_fail_safe_to_full` | PR 的 `ci-plan-*` artifact 與穩定 `verify` context | 保留；live artifact 用來證明實際路由，不重複演算法測試 |
| Concurrency／同步：ordinary work 不追 main，final promotion 必須使用最新 main | `tests/test_delivery_sync.py::test_gate_does_not_block_stale_ordinary_or_stacked_work`、`test_second_main_advance_invalidates_previous_success`、`test_reconcile_handles_only_the_requested_delivery` | promotion preflight 與受審查的單一 `sync/main-to-*` PR | main push 不寫 stale status 或 fan-out；final candidate 與 explicit-dependency owner route 仍 fail closed，真正同時發生的事件競爭與 Ruleset enforcement 屬平台證據 |
| Promotion 不得接受失敗 canary 或不同 tree | `tests/test_promotion_gate.py::test_finalize_rejects_failed_configured_canary`、`test_verify_main_rejects_a_different_tree` | promotion evidence、完整 `verify`、environment canary 與合併後 tree identity | 保留；本機可驗資料不取代 hosted environment／main handoff |

## 重複、脆弱檢查與缺口

- **已消除的重複：**#201／#202 已把普通 PR 收斂為單一 fast 路徑，將 Python
  runtime-sensitive 驗證留在 full matrix，TypeScript 只跑一次；OSV／Zizmor 的
  standalone workflow 不再重跑每張 PR。
- **本次移除的脆弱檢查：**`scripts/verify-template.sh` 不再逐字比對
  `docs/agent-install.md` 內跨行的 dry-run 文案。`tests/test_cli.py` 已分別證明
  `init`、`adopt`、`update` 的 dry-run 不寫入目標，以及後續 apply 行為；改寫文件
  不應讓相同行為失敗。這是 #256 暴露的 implementation-detail assertion。
- **保留的 static contract：**action SHA、最低權限、job dependencies、required
  aggregate、runtime matrix 與 root／template 同步仍會影響執行或安全邊界，不能只靠
  prose 說明。
- **平台限定缺口：**本機無法證明 Ruleset 實際阻擋、hosted runner 是否啟動、Actions
  額度／帳務狀態、GitHub Environment approval、真實 canary、Release／attestation
  hosted identity。這些項目只能保留 live run URL／artifact；不得用 mock 或本機成功
  宣稱完成。

## 基線與量測

2026-08-25 以相同 repository 驗證入口記錄：

| 指標 | Before | After |
| --- | --- | --- |
| `main` pytest／完整驗證 | 223 cases；584.40 秒（既有主線量測） | 不適用；本次 stacked base 已包含後續變更 |
| `enhancement/267-outcome-milestone-titles` pytest collect | 232 cases | 232 cases |
| init／adopt／update characterization | 3 passed；33.01 秒 | 連同必要負向案例共 24 passed；33.69 秒 |
| `./scripts/verify-template.sh` | 不重跑 stacked base；沿用上述主線 wall time | 單次最終 full run 的 wall time 記錄於交付 PR |

Root `ci.yml` 有 8 個 job definitions；full tier 的 Python 2-entry matrix 展開後，
若所有條件式安全檢查都適用，最多 9 個 job executions。Generated project 的
`ci.yml` 有 7 個 job definitions；非 Python／latest Python／minimum 3.13／minimum
3.12 的 full runtime entries 分別為 1／2／3／4，因此最多展開為 7／8／9／10 個
job executions；本次 before／after 數量相同。`verify-template.sh` 機械檢查 3 個 Python minimum × inline／reusable，
共 6 種 runtime-policy fixture；TypeScript 仍只在每個 full job 執行一次。

After wall time 是本機證據，不等於 billed runner-minutes，也不能完成 #189 的 live
成本驗收。若環境或 cache 不同，應同時保留命令、SHA 與原始秒數，不把差異解讀成
測試削弱。
