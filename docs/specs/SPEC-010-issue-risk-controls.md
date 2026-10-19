---
id: SPEC-010
title: Trace Issue requirements to risks and exact-head evidence
owner: @matheme-justyn
priority: P1
estimate: ongoing
status: approved
tracking: none
---

## Problem

Work Issue 的風險原本只是「補充」裡的自由文字；PR gate 只看 checkbox 是否勾選。完成條件（AC）、風險控制與 exact-head 證據沒有可解析的一對一關係，也沒有 repository／Milestone 的風險登錄冊，完成狀態可能和實際風險或需求證據脫節（Issue #1079，#1058 決定 22）。

## Outcome

- 每張 work Issue 的「補充」帶一個可解析的「風險與控制」區塊；每個風險至少一個控制，由 Issue assignee 擁有。
- Issue「完成條件」的頂層 checkbox 依序就是 AC1…ACn。
- PR body 只有一節 `## Requirement evidence`，把每個 AC 與每個風險 ID 對應到 exact-head 證據或明示的例外。
- Ready 預檢、base 的 `validate-pr-policy` 與 `merge_snapshot` 用同一個 parser；不完整時 PR 維持 Draft、拒絕合併。
- 合併的 canonical evidence payload 保存 Issue body digest、coverage digest 與每個 ID 的證據；Ready 後增刪或重排 AC，coverage 就 stale，合併前會重新驗證。
- 登錄冊、建議與引導建立只在 CSARC CLI；生成專案只多一支 gate 用的 `risk_controls.py`。

## Principles

1. **Issue body 是唯一來源**（#223）。區塊、AC 與登錄冊都從 Issue 與 PR body 計算，不 commit、不寫進 tracker、不另建 requirements database／RTM。
2. **一律啟用、沒有寬限期、沒有 opt-out**（決定 22.6）。不新增 workflow、required check 或公開設定；規則加在既有 gate 內。
3. **確定性檢查只看格式與綁定**。證據是否真的涵蓋風險，由 PR 審查判斷；不做 AI 語意比對。
4. **Issue 與 PR 內容是不可信資料**。parser 不執行任何儲存格；訊息只回顯列號、ID、固定詞彙與符合證據文法的值，因此內容無法注入 Actions `::` workflow command。
5. **只下發 gate**（決定 22.5）：`risk_controls.py` 至多 300 行、只用標準函式庫、從 trusted base 載入、不需要 CLI。

## Issue block

區塊放在「補充」（表單 `supplement` 欄位預填骨架，欄位、id 與 required 都不變）。標籤行在 fenced code block 之外、整個 body 恰好一行：

```markdown
#### 風險與控制

| ID | 類別 | 等級 | 風險 | 控制 | 預計證據 | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | data | high | adopt 覆寫產品既有檔案 | adopt 預設試跑並保留產品檔 | 試跑 regression | @alice |
```

封閉文法：

- 解析前把 `\r\n` 與 `\r` 換成 `\n`。標籤行也接受 M18 規劃格式 `#### 風險與控制（SPEC-010 規劃格式）`，此時表頭是不含 `等級` 的 6 欄 `| ID | 類別 | 風險 | 控制 | 預計證據 | Owner |`，等級視為 `unrated`。這是唯一的第二種表頭。
- 1–10 列、整個區塊 8,000 字元內、每格 300 字元內；每列恰好表頭的欄數。
- `ID` 是 `R0` 或 `R1`–`R99`，不得重複（duplicate fail closed）。一列是一個風險與它的控制。
- `類別`（category）是小寫 kebab token `[a-z][a-z0-9-]{1,31}`，`none` 只給 `R0`。CLI 的建議詞彙是 `security`、`data`、`availability`、`compliance`、`supply-chain`、`correctness`、`operability`；gate 不限制詞彙，讓既有 M18 Issue 的分類照樣有效。
- `等級`（severity）是 `low`、`medium`、`high`；`R0` 為 `—`。
- `風險`、`控制`、`預計證據` 不得空白、不得含完整字詞 `TODO` 或整格 `<…>` 占位符。
- `Owner` 是單一 `@login`；Ready 時必須是 Issue 的 assignee（決定 22.4）。
- 任何儲存格像 token、私鑰或 email 時拒絕，訊息不回顯內容並要求輪替。

`R0`（No material risk）必須是唯一一列：`| R0 | none | — | <理由> | <控制> | scope:docs | @owner |`。

## Acceptance criteria IDs

`### 完成條件`（機器產生的 Issue 也接受 `### Acceptance criteria`）之下、下一個標題之前，行首的 `- [ ]`／`- [x]` 依序成為 AC1…ACn（1–50 項）。巢狀項目不算。項目文字以 `ACk` 開頭時，`k` 必須等於它的位置，否則視為重排錯誤。

## Requirement evidence

PR body 恰好一節：

```markdown
## Requirement evidence

Issue: #123
Coverage: sha256:<64 hex>

| ID | 證據 |
| --- | --- |
| AC1 | tests/test_report.py::test_report_renders |
| AC2 | check:verify |
| R1 | accepted: 單人維護者接受這個殘餘風險 |
```

證據形式（其他一律 unknown，fail closed）：

| 形式 | 適用 | Ready 檢查 | 合併檢查 |
| --- | --- | --- | --- |
| `<path>` 或 `<path>::<name>` | 全部 | PR head 上是檔案；`<name>` 的每個 `::` 段落以完整識別字出現 | 同左（`merge_snapshot` 重新讀取） |
| `check:<name>` | 全部 | 只檢查文法（check 可能仍在執行） | 該 check 在 exact head 以 success 完成；local 模式的 `check:verify` 由 local verification evidence 滿足 |
| `manual: <https URL> <理由>` | 全部 | 文法；理由至少 10 字元 | 同左 |
| `accepted: <理由>` | 只限 `R1`–`R99` | 理由至少 10 字元 | 同左；Ready 輸出另列一行 |
| `scope:docs` | 只限 `R0` | PR 每個變更路徑都屬 `ci_tier.scope_for` 的 `docs`，而且不是下列安全相關文件 | 同左 |

Ready 要求 complete 且無 unknown：每個 AC 與風險 ID 都有一列、沒有不存在的 ID、`Issue:` 等於 closing Issue、`Coverage:` 等於目前 Issue 計算出的 coverage digest。錯誤訊息會列出正確的 coverage digest；作者重新對應證據後寫入。

### R0 restrictions

`R0` 在 PR 含 docs 以外的路徑，或改到下列任一路徑時被拒絕（決定 22.2），root 與生成專案共用：`AGENTS.md`（含生成專案 render 的 `AGENTS.md`）、`SECURITY.md`、`.github/SECURITY.md`、`docs/ci-policy.md`、`.csarc/docs/ci-policy.md`。訊息只列 scope 名稱與 `security-docs`，不回顯路徑。

### Visible exceptions

Ready 與合併通過時各印一行：`requirement-trace: #<n> R0 declared; <k> paths are docs`，以及 `requirement-trace: #<n> self-accepted: <ids>`（`high` 加 `(high)`）。單人維護時 assignee 可自行接受 `high`，但永遠可見（決定 22.4）。

## Digests and staleness

- **coverage digest**：`sha256` of the JSON array `[AC texts in order, [[ID, 類別, 等級, 控制, Owner] per risk]]`（`ensure_ascii=false`、`,`／`:` 分隔）。勾選 checkbox 不改變它；增刪、重排或改寫 AC 或風險控制都會改變它，PR 記錄的值因此變成 stale。
- **body digest**：正規化換行後整個 Issue body 的 `sha256`，只記錄、不比較。
- `merge_snapshot` 把 `requirement_trace` = {`issue`、`body_digest`、`coverage_digest`、`evidence`} 放進 snapshot，`merge_evidence` 把它加入 #1073 的 canonical payload（`head_sha`／`tree_sha` 已在 payload 內），所以 `CSARC-Evidence-SHA256` trailer 也覆蓋它。

## Routes

只有 work PR 受檢查：head 為 `release-please--*`、`release/v*`、`sync/main-to-*`、`automation/*`、`dependabot/*`，或以 `dev/m*`、`promote/m*`、`dev/i*` 指向 `main` 的 promotion，都不檢查。PR body 沒有 closing keyword 時 lifecycle 不建立 trace（`validate-pr-policy` 已要求 work PR 帶 `Closes #N`）；一張 traced PR 只能關閉一張 Issue。

## Enforcement points

| 位置 | 行為 |
| --- | --- |
| `pr_lifecycle.py state --state ready` | 呼叫 `gh pr ready` 之前檢查；不完整時 PR 維持 Draft |
| `validate-pr-policy`（base） | 非 Draft 時執行 `pr_lifecycle.py trace`，以唯讀 GitHub GET 讀 Issue、PR files 與 head 檔案 |
| `merge_snapshot` | 合併前重新讀取 Issue 與 PR，重算 coverage、檢查 `check:` 證據並寫入 payload |
| hotfix post-review Issue | lifecycle 先以 create 階段驗證固定區塊，再交給既有建立入口（模板 repository 的 `gh-issue-create`，生成專案的 `gh issue create`） |

gate 一律由 trusted base 的 scripts 執行；新增本 gate 的 PR 不受它自己檢查。M18 中 K1 之前合併的 work PR 由一次性 backfill manifest 承接（見下）。

## CLI

`csarc` CLI 的指令都不下發，也不是 gate：

- `csarc issue create [--body-out FILE] -- <gh issue create 參數>`：恰好一個 body 參數（`--body`、`-b`、`--body-file`、`-F`）。通過 create 階段時原樣交給 `gh issue create`（body 以暫存檔傳入）。缺區塊而且 stdin 是 TTY（body 不是來自 stdin）時，依關鍵字逐列建議類別，由作者保留、改寫或刪除並填寫內容，`[y/N]` 確認後才加到「補充」末端；原 body 一字不變。non-interactive 缺完整區塊時在呼叫 `gh` 前以 exit 1 失敗並印出建議骨架。Milestone tracker 標題與 `promotion`／`duplicate` label 豁免。
- `csarc risk suggest (--issue N | --open) [--json]`：唯讀列出缺少或無效區塊的 open Issue、RC 代碼與建議骨架。
- `csarc risk register [--milestone N] [--state open|closed|all] [--json]`：唯讀從 Issue 與 PR 計算登錄冊（`format: csarc-risk-register`、`format_version: 1.0.0`）。每張 Issue 有 `coverage`（`valid`、`no-material-risk`、`missing`、`invalid`、`exempt`）與 `trace`（`current`、`stale`、`unmapped`）；`evidence_index` 反查每份路徑證據承擔哪些 `#Issue/ID`，路徑不在本機 `origin/<default branch>` 時標 `stale`。固定列出 `no_material_risk` 與 `accepted_risks` 兩節（Markdown：`## No material risk`、`## Accepted risks`），沒有內容時寫 `None.`。輸出不含時間戳，同樣輸入得到同樣結果。
- `csarc risk backfill --milestone N [--out FILE | --json]`：為 K1 之前已合併、PR body 沒有 `## Requirement evidence` 的 Milestone work PR 產生一次性 manifest（`format: csarc-risk-backfill`），每列記錄 PR、Issue、merge／head SHA、Issue body 與 coverage digest、AC 與風險 ID，並印出 canonical bytes 的 `sha256` digest。`--verify FILE --digest D` 檢查檔案 canonical、digest 相符，並從 GitHub 重新產生後比對，promotion 可直接讀回。P4（#1081）在物化 beta.2 前產生並保存：`docs/evidence/m18-risk-backfill.json`（25 張 PR）、digest `sha256:32d064261642befebb51ca272ea264a6cb32a3b4942ecc72dc5bc1180cd0f7f6`；K1 與之後的 work PR 自帶 `## Requirement evidence`，不列入。

模板 repository 的 `scripts/gh-issue-create`（只在 root）在呼叫 `gh` 前以同一 parser 檢查 body。

## Adoption

沒有寬限期：缺少有效區塊的 open Issue，它的 PR 在離開 Draft 前必須補上。`csarc update` 在 plan 新增 `.csarc/scripts/risk_controls.py` 時，報告寫一列 `product.behavior_changes`（`subject: risk-controls`），提示以 `csarc risk suggest --open` 列出待補的 Issue。

## Known limitations

- 證據存在不代表涵蓋風險；這項判斷屬於 PR 審查。
- GitHub UI 直接按 Ready 不經過 Ready 預檢；hosted PR policy 在 `ready_for_review` 時重新執行並阻擋，lifecycle 合併前也會重新檢查。GitHub UI 合併只依 `pr-policy` 最後一次結果。
- `check:` 在 Ready 時只檢查文法，exact-head 結果在合併時檢查。
- RK12 只攔常見形式，不能證明區塊中沒有敏感資料。

## Acceptance criteria

- [x] 封閉文法、R0、類別／等級、控制、證據、AC ID、Requirement evidence、coverage digest 與 stale 判定如上（#1079 AC1）。
- [x] 表單骨架、Owner 與 R0／accepted 規則（AC2）。
- [x] Ready、`validate-pr-policy`、`merge_snapshot` 共用 parser（AC4–AC7）。
- [x] CLI 與 backfill（AC3、AC8、AC10）。

## Out of scope

- AI 語意比對、requirements database／RTM、新 workflow、required check、hosted 留言或提醒、專案自訂類別或安全文件清單。

## Verification

- `uv run pytest tests/test_risk_controls.py tests/test_risk_tools.py`
- `uv run pytest tests/test_pr_lifecycle.py -k "trace or post_review or untraced or preflight"`
- `scripts/test-pr-policy`、`scripts/test-gh-issue-create`

## References

- [SPEC-008 lifecycle report format](SPEC-008-lifecycle-report-format.md) — `product.behavior_changes`
- [Issue #1079](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1079)
- [Issue #1073](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1073) — canonical merge evidence payload
- [Issue #573](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/573) — Draft 不檢查完成度
