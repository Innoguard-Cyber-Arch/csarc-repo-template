---
id: SPEC-008
title: Define one lifecycle report format for adopt and update
owner: @matheme-justyn
priority: P1
estimate: ongoing
status: approved
tracking: none
---

## Problem

`adopt` 原本只有一份從 Python 物件直接拼出的 Markdown（1.1.0），`update` 沒有報告。人讀的內容沒有可比對的結構化來源，設定以 Python repr 顯示，套用後的報告可能寫到使用者沒有審閱的目錄；後續 migration、衝突重播與設定分類也沒有共用的欄位與詞彙可以填。

## Outcome

`adopt` 與 `update` 每次規劃都由同一個 report model 在 target 外寫出 machine plan、report JSON 與從 report JSON render 的 Markdown。report JSON 是唯一來源，詞彙封閉，未知值 fail closed；套用成功後同一份報告轉為 `applied` 並綁定被重播的 plan digest。

格式版本：`2.0.0`（`LIFECYCLE_REPORT_FORMAT_VERSION`，`src/csarc_cli/lifecycle_report.py`）。

## Context

### 1. 適用範圍

- `adopt`：dry-run、`--finalize --dry-run`、`--apply-plan`、`--finalize --apply-plan`。
- `update`：`--check`（含 `--json`）、`--dry-run`、確認前的 plan、套用成功後，以及 release 無法使用時的 reinstall 路徑。
- `init` 沒有報告。

### 2. 檔案

所有檔案寫在 target 外的同一個目錄；目錄位於 target 內，或經 symlink 解析進 target 時，在寫入前失敗。每個檔案都經 no-follow 的 hardened atomic writer（mode `0600`）寫入。

| Operation | 預設目錄 | Machine plan | Report JSON | Markdown |
| --- | --- | --- | --- | --- |
| adopt | `<parent>/<name>-csarc-adoption-report` | `csarc-adoption-plan.json` | `csarc-adoption-report.json` | `csarc-adoption-report.md` |
| update | `<parent>/<name>-csarc-update-report` | `csarc-update-plan.json` | `csarc-update-report.json` | `csarc-update-report.md` |

- `--report-dir PATH` 可改目錄；`adopt --apply-plan` 一律寫回被重播的 plan 所在的目錄，另外傳入不同的 `--report-dir` 時在寫入 target 前拒絕。
- 寫入順序：machine plan、report JSON、Markdown。Markdown 只由 report JSON 的位元組解析後 render；report 驗證失敗時三個檔案都不寫。
- adopt 的 machine plan 契約不變（`plan.as_dict()` 加 `plan_sha256`，`schema_version: 1`，可被 `--apply-plan` 重播，套用後照舊寫入 `adoption.applied`）。update 的 machine plan 是同一次 `update --check --json` 的 plan 加上 `plan_sha256`，`replayable: false`；可重播的 final plan 由後續 Issue 定義，`final_plan` 在 2.0.0 一律為 `null`。
- 1.1.0 的 `csarc-adoption-dry-run.md` 在新檔寫完後，以同一個 no-follow 目錄 descriptor 刪除；它是 symlink 或非一般檔案時保留並警告，讓每個目錄只有一份報告。

### 3. Report JSON

每個鍵都一定存在，未知鍵被拒絕。`null` 表示這個 operation 不評估，或負責的 Issue 尚未實作；`[]` 表示評估過但沒有項目。輸出以 `sort_keys`、兩格縮排序列化；相同輸入產生相同位元組。

- `report_format_version`：`2.0.0`。
- `operation`：`adopt`｜`update`。
- `status`、`status_reason`、`applicable`（機器的 apply 閘門）。
- `generated_at`、`applied_at`：`applied_at` 只在 `status` 為 `applied` 時是字串。
- `plan`：{`path`（檔名）、`sha256`、`schema_version`、`mode`、`replayable`}。`sha256` 是使用者審閱並重播的 plan digest；套用後即使 adopt 照舊改寫 plan 檔，報告仍保留核准時的 digest。
- `final_plan`：與 `plan` 同形狀，只用於 update；2.0.0 為 `null`。
- `target`：{`path`、`head`、`working_tree`、`changes`、`repository`、`visibility`、`visibility_source`}。
- `release`：{`source`、`from`、`to`}；`from` 為 {`tag`、`sha`、`verification`}，adopt 為 `null`；`to` 另含 `guide_url`。
- `summary`：`files` 依 action 計數、`settings` 依 class 計數（全部列出，包含 0）、`required_actions` 為 {`blocking`、`non_blocking`}；計數必須等於對應列的數量。
- `settings`：每列 {`key`、`before`、`after`、`class`、`source`、`note`}，依 key 排序且不重複；只列出 `REPORT_SETTING_KEYS` 允許的鍵，值保留 JSON 型別。
- `files`：每列 {`path`、`action`、`reason`、`from`、`decision`}，先依 action 順序、再依 path 排序；只有 `move` 有 `from`。
- `product`：{`release_ownership`、`code_owner`、`work_item_mapping`、`release_writers`、`version_surfaces`、`action_pins`、`reviewer_rotation`、`behavior_changes`}；後五項保留給後續 Issue，2.0.0 為 `null`。
- `required_actions`：每列 {`kind`、`subject`、`blocking`、`message`、`command`}。
- `verification`：{`candidate`、`hook`、`render_parity`}；`render_parity` 只有 `state`。update（不含 reinstall）由 Issue #1063 的共用規劃器填入：以舊 template 實際詢問的答案與可信快照重建的舊側 render，與 target 逐檔相同為 `equal`，否則為 `diverged`；adopt 與 reinstall 為 `null`。
- `next_steps`：每列 {`text`、`command`}，由 operation 與 status 算出。

### 4. 封閉詞彙

| 欄位 | 值 |
| --- | --- |
| `status` | `applied`、`blocked`、`review-required`、`ready`、`current`（只用於 update） |
| 設定 `class` | `unchanged`、`exact`、`narrowed`、`widened`、`decision`、`new`、`retired` |
| 設定 `source` | `explicit`、`saved`、`derived` |
| `target.working_tree` | `clean`、`dirty-preserved`、`dirty-review-only` |
| `verification.candidate.state` | `pending-authorization`、`deferred-manual-merge`、`passed`、`failed`、`not-run` |
| `verification.render_parity.state` | `equal`、`diverged` |
| `files[].decision` | `pending`、`keep-current`、`take-new`、`custom`、`null` |

檔案 `action` 與 `reason`（依 action 順序）：

| Action | Reason |
| --- | --- |
| `add` | `template`、`lockfile` |
| `overwrite` | `template`、`automatic-merge` |
| `move` | `layout-migration` |
| `remove` | `template-deleted` |
| `retire` | `obsolete-generated`、`excluded-orphan` |
| `preserve` | `untouched`、`product-owned`、`dirty-preserved` |
| `conflict` | `manual-merge`、`undetermined`、`move-collision`、`update-conflict`、`retire-modified` |

無法驗證（`unknown`）的 CODEOWNER 只在 `## Product state` 顯示，不算 required action；`blocked` 才產生 blocking 的 `code-owner`。

required action `kind`：`action-pin`、`code-owner`、`committed-resolution`、`file-conflict`、`mapping-decision`、`mapping-review`、`release-writer`、`render-parity`、`retire-modified`、`runtime-mismatch`、`setting-decision`、`verification`、`version-surface`、`working-tree`。2.0.0 的 `setting-decision` 只用於 update。

狀態規則（validator 強制）：

- `blocked`：至少一項 `blocking: true`，`applicable` 為 false。
- `review-required`：有 required action，且沒有 blocking 項目。
- `ready`：沒有 required action，`applicable` 為 true。
- `current`：只用於 update，沒有變更也沒有 required action。
- `applied`：只由成功套用後的改寫設定，必須綁定同一個 plan digest；`blocked` 或已 `applied` 的報告不能再轉為 `applied`。
- 報告的 `status` 與 CLI exit code 是兩回事；`update --check` 的 exit code 不變。
- update 的檔案列與衝突來自 `--check` 與套用共用的同一個三方 update 規劃（Issue #1063）：衝突為 `conflict`／`update-conflict`，並產生 blocking 的 `file-conflict`；template 刪除的路徑為 `remove`／`template-deleted`。

設定分類（本 Issue 實作的通用規則；個別鍵的遷移分類由後續 Issue 補上）：adopt 的每列都是 `new`；update 前後相同為 `unchanged`、新出現為 `new`、消失為 `retired`、其他改變為 `decision`。來源不是 `explicit` 的 `decision` 產生非 blocking 的 `setting-decision`。

**Fail closed**：writer 與 renderer 先驗證整份 report；缺鍵、未知鍵、未知詞彙、`report_format_version` 不是 `2.0.0`、計數不符或狀態規則不成立時拋出錯誤，三個檔案都不寫，CLI 以錯誤結束。

### 5. Markdown

- H1 為 `# CSARC adoption report` 或 `# CSARC update report`，接著是 `> **Status: <banner>.** <status_reason>` 與 ``Report format version: `2.0.0` ``。
- banner：adopt 為 `Ready to adopt`、`Review required`、`Blocked`、`Adopted`；update 為 `Current`、`Ready to update`、`Review required`、`Blocked`、`Updated`。
- 九個 H2 依序一律出現，沒有內容時印 `None.`：
  1. `## Items requiring your decision`：blocking 項目在前；沒有項目時印 "No known file conflicts. This does not guarantee semantic or runtime compatibility."
  2. `## Snapshot`
  3. `## Summary of file changes`：`| Action | Files |`，七列，數量為 0 也列出。
  4. `## Impact analysis`：有 `widened` 設定時第一列固定為 `Widened settings: ... See Settings.`
  5. `## File changes`：`preserve` 只計數，逐列清單只在 JSON。
  6. `## Settings`
  7. `## Product state`：H3 只在 JSON 值不是 `null` 時出現，順序為 `### Release writers`、`### Version surfaces`、`### Action pins`、`### Reviewer rotation`、`### Behavior changes`、`### Work-item mapping`。
  8. `## Verification`
  9. `## Next steps`
- heading、標籤與詞彙值固定為英文，不依文件語言設定在地化，作為測試與 agent 搜尋的穩定錨點。值的格式：布林值 `true`／`false`、`null` 為 `(none)`、list 以 `, ` 連接，不出現 Python repr。

### 6. Redaction

- 設定只列出 allowlist 中的鍵；allowlist 以外的值（例如任意 `--data` 鍵）不出現。
- 每個字串值在驗證前遮蔽 GitHub token（`ghp_`、`gho_`、`ghu_`、`ghs_`、`ghr_`、`github_pat_`）、AWS access key、Slack token、private key 標頭與 URL 中的 `user:password@`，改為 `[redacted]`。
- validator 仍掃描整份 report；任何字串仍符合上述 pattern 時拒絕寫出。
- 報告不含檔案內容、檔案 digest 快照、token 或憑證。

### 7. 版本規則

`LIFECYCLE_REPORT_FORMAT_VERSION` 採 semver：

- MAJOR：改檔名；移除或改名 JSON 欄位，或改變欄位的型別或意義；移除、改名或重排 H2；移除或改名詞彙值。
- MINOR：新增 JSON 欄位、詞彙值、required action kind 或 H3；在不改變既有順序的前提下新增 H2。
- PATCH：只改措辭或跳脫。
- 與上一個已發布 Release 相比，每個層級最多提升一次。1.1.0 是最後發布的格式；本規格定義 2.0.0。Milestone 18 中只有設定問卷的 Issue 可在 beta.2 前依 MINOR 提升一次到 2.1.0（並把 `setting-decision` 開放給 adopt）；其他 Issue 只填入已保留的欄位與詞彙。
- machine plan 的 `schema_version` 另外計算。

### 8. 位置

本規格只放在 root `docs/specs/`，不放 `template/docs/specs/` 副本：`copier.yml` 把 `docs/specs/**/*.md` 設為 `_skip_if_exists`，副本在下游不會更新。

## Acceptance criteria

- [x] 共用的 report model、validator、JSON writer 與 Markdown renderer 位於 `src/csarc_cli/lifecycle_report.py`，adopt 與 update 都經 `lifecycle_report_model()` 建立 report。
- [x] adopt 的 dry-run、finalize dry-run 與兩種 `--apply-plan` 寫出 plan、report JSON 與 Markdown；applied 改寫寫回被重播的 plan 所在目錄並綁定核准的 plan digest。
- [x] update 的 `--check`、`--dry-run`、確認前 plan 與 reinstall 寫出同一組三個檔案；套用成功後 report 轉為 `applied`，失敗或未套用時維持原狀態。
- [x] 未知詞彙、缺鍵、計數不符與未遮蔽的憑證 fail closed。
- [ ] 個別設定的遷移分類（`exact`、`narrowed`、`widened`、`retired` 承接列）由後續 migration Issue 填入。
- [x] update 的 render parity、三方衝突列與 template 刪除列由 Issue #1063 填入。
- [ ] update 的 final plan 與 product 保留欄位由後續 Issue 填入。

## Out of scope

- legacy migration 規則、final conflict replay 與個別設定分類。
- `update --check` 的 exit code。
- `init` 報告與報告標題在地化。
- 移除 adopt 套用後在 plan 寫入 `adoption.applied` 的既有改寫。

## Verification

- `uv run pytest tests/test_lifecycle_report.py`
- `uv run pytest tests/test_cli.py -k "report or adopt or update"`（含本機 `large` 測試）
- `python3 scripts/spec_to_issue.py validate`

## References

- [Issue #1062](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1062)：本規格的來源。
- [Issue #530](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/530)：報告的獨立版本號；Markdown-only 改為以 report JSON 為唯一來源。
- [Issue #529](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/529)：試跑與正式執行更新同一份報告，每個目錄只有一份。
- [Issue #950](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/950)：設定 allowlist 與 secret 不出現。
- [Issue #219](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/219)：plan → confirm → apply，dry-run 零寫入。
- [SPEC-003](SPEC-003-reproducible-template-lifecycle.md)、[Transactional repository adoption ADR](../adr/transactional-repository-adoption.md)
