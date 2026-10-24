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

格式版本：`2.3.0`（`LIFECYCLE_REPORT_FORMAT_VERSION`，`src/csarc_cli/lifecycle_report.py`）。`2.1.0` 由 Issue #1078 依 MINOR 規則提升，只新增 adopt 的 `setup` 紀錄並把 `setting-decision` 開放給 adopt；`2.2.0` 由 Issue #1083 依 MINOR 規則提升，只新增 `overwrite` 的 `compatibility-shim` 理由；`2.3.0` 由 Issue #1224 依 MINOR 規則提升，只新增唯讀的 `writing_guide` 提示；相容規則見 §7。

## Context

### 1. 適用範圍

- `adopt`：dry-run、`--finalize --dry-run`、`--apply-plan`、`--finalize --apply-plan`。
- `update`：`--check`（含 `--json`）、`--dry-run`、確認前的 plan、套用成功後，以及 release 無法使用時的 reinstall 路徑。
- `init` 沒有報告；寫作指引提示（§3 `writing_guide`）只印在 `init` 的終端機 plan。

### 2. 檔案

所有檔案寫在 target 外的同一個目錄；目錄位於 target 內，或經 symlink 解析進 target 時，在寫入前失敗。每個檔案都經 no-follow 的 hardened atomic writer（mode `0600`）寫入。

| Operation | 預設目錄 | Machine plan | Report JSON | Markdown |
| --- | --- | --- | --- | --- |
| adopt | `<parent>/<name>-csarc-adoption-report` | `csarc-adoption-plan.json` | `csarc-adoption-report.json` | `csarc-adoption-report.md` |
| update | `<parent>/<name>-csarc-update-report` | `csarc-update-plan.json` | `csarc-update-report.json` | `csarc-update-report.md` |

- `--report-dir PATH` 可改目錄；`adopt --apply-plan` 一律寫回被重播的 plan 所在的目錄，另外傳入不同的 `--report-dir` 時在寫入 target 前拒絕。
- 寫入順序：machine plan、report JSON、Markdown。Markdown 只由 report JSON 的位元組解析後 render；report 驗證失敗時三個檔案都不寫。
- adopt 的 machine plan 契約不變（`plan.as_dict()` 加 `plan_sha256`，`schema_version: 1`，可被 `--apply-plan` 重播，套用後照舊寫入 `adoption.applied`）。update 的 stage-1 machine plan 是同一次 `update --check --json` 的 plan 加上 `replayable: false` 與 `plan_sha256`，只供審閱，不能套用。
- update 的 final plan（Issue #1067）：`update --finalize-plan` 在 stage-1 plan 所在的同一目錄寫出 `csarc-update-final-plan.json`（`schema_version: 1`、`replayable: true`）。它要求 stage-1 plan 的 digest 有效、規劃 digest 與 template SHA 仍相同，且每個 `update-conflict` 恰有一個 `--decision PATH=keep-current|take-new|custom:FILE`。pin 漂移只有一條規則（Issue #1147）：`--pin-commit` 只在**被 finalize 的那份 stage-1 plan** 仍列出 blocking `action-pin` 時必填，值是只改這些 pin 的產品 commit，CLI 從該 commit 讀回並拒絕清單外的變更；stage-1 plan 沒有列出 pin 漂移時傳入 `--pin-commit` 一律拒絕。因為 `--check` 每次都重新比對 pin，先 commit pin 再重新 `--check` 所得的新 stage-1 plan 不再列出那些 pin，finalize 也就不需要 `--pin-commit`；文件建議走這條路，`--pin-commit` 只用於沿用 commit 之前的 stage-1 plan。plan 記錄 `toolchain`（Copier、Jinja2、Git、Python、csarc 版本）、`inputs`（新舊兩側 Copier answers、`--data` 與命令參數）、`live_facts`（repository 與 visibility、origin、權限、Release 與 target HEAD／status／檔案指紋）、`derived`（規劃結果、核准的檔案轉換、舊 render 指紋）、`decisions`（檔案決定與其確切內容、設定變更列、pin 決定）與內嵌報告，各區段有 digest，`final_plan_sha256` 綁定整份 plan。檔案已存在時拒絕覆寫；要重新決定時保留舊檔，以新的 `--report-dir` 重新 `--check` 與 `--finalize-plan`（Issue #1147）。
- update 的衝突三側（Issue #1147）：`--check`、`--dry-run` 與確認前的 plan 在報告目錄的 `conflicts/` 下，為每個 `update-conflict` 寫出 `conflicts/base/<path>`（記錄版本的 render）、`conflicts/current/<path>`（target 目前內容，即 `keep-current` 會記錄的位元組）與 `conflicts/new/<path>`（目標版本以同一份 answers render 的結果，即 `take-new` 會記錄的位元組）；某一側沒有檔案時不寫。`conflicts/` 是工具輸出，每次規劃整個取代；對應的 `file-conflict` 列在 `message` 寫出這三個路徑與 `--finalize-plan --decision` 指令，不新增欄位。
- `update --apply-plan <final plan>` 只用 plan 記錄的值 render 與套用，不接受 `--data`、`--to` 等會改變輸入的參數；套用前重新觀察工具版本與 live facts，任何不同都在寫入前停止。成功後 `.csarc/provenance.json` 記錄 `final_plan_sha256`，報告轉為 `applied` 並同時綁定 stage-1 與 final plan digest；對已套用的 plan 重跑時說明已套用並以 0 結束，不改任何檔案。
- 1.1.0 的 `csarc-adoption-dry-run.md` 在新檔寫完後，以同一個 no-follow 目錄 descriptor 刪除；它是 symlink 或非一般檔案時保留並警告，讓每個目錄只有一份報告。

### 3. Report JSON

每個鍵都一定存在，未知鍵被拒絕。`null` 表示這個 operation 不評估，或負責的 Issue 尚未實作；`[]` 表示評估過但沒有項目。輸出以 `sort_keys`、兩格縮排序列化；相同輸入產生相同位元組。

- `report_format_version`：`2.3.0`。
- `operation`：`adopt`｜`update`。
- `status`、`status_reason`、`applicable`（機器的 apply 閘門）。
- `generated_at`、`applied_at`：`applied_at` 只在 `status` 為 `applied` 時是字串。
- `plan`：{`path`（檔名）、`sha256`、`schema_version`、`mode`、`replayable`}。`sha256` 是使用者審閱並重播的 plan digest；套用後即使 adopt 照舊改寫 plan 檔，報告仍保留核准時的 digest。
- `final_plan`：與 `plan` 同形狀，只用於 update；`--finalize-plan` 之後與套用後的報告指向 final plan（`replayable: true`），其他情況為 `null`。決定後的 `update-conflict` 列帶 `keep-current`、`take-new` 或 `custom`，對應的 blocking `file-conflict` 不再列出。
- `target`：{`path`、`head`、`working_tree`、`changes`、`repository`、`visibility`、`visibility_source`}。
- `release`：{`source`、`from`、`to`}；`from` 為 {`tag`、`sha`、`verification`}，adopt 為 `null`；`to` 另含 `guide_url`。
- `summary`：`files` 依 action 計數、`settings` 依 class 計數（全部列出，包含 0）、`required_actions` 為 {`blocking`、`non_blocking`}；計數必須等於對應列的數量。
- `settings`：每列 {`key`、`before`、`after`、`class`、`source`、`note`}，依 key 排序且不重複；只列出 `REPORT_SETTING_KEYS` 允許的鍵，值保留 JSON 型別。
- `files`：每列 {`path`、`action`、`reason`、`from`、`decision`}，先依 action 順序、再依 path 排序；只有 `move` 有 `from`。
- `product`：{`release_ownership`、`code_owner`、`work_item_mapping`、`release_writers`、`version_surfaces`、`action_pins`、`reviewer_rotation`、`behavior_changes`}；後五項保留給後續 Issue，尚未實作時為 `null`。`code_owner` 是 adopt 對設定的 owner 所做的即時 repository 驗證 {`reason`、`state`、`value`}（`state` 為 `not-configured`、`verified`、`unknown` 或 `blocked`）；update 不即時驗證，為 `null`（reinstall 沿用 adopt 的驗證），設定的值只在 Settings 的 `code_owner` 列，由套用後的 repository settings `plan` 驗證（Issue #1167）。`action_pins` 由 Issue #1065 填入：update（不含 reinstall）為產品 Action pin preflight 的列，每列 {`file`、`line`、`action`、`old_sha`、`new_sha`、`reason`}，`reason` 為 `template-pin-changed`（產品 pin 等於目前受管 workflow 的 pin）或 `product-pin-diverged`；沒有漂移時為 `[]`，adopt 為 `null`。每列另產生 blocking 的 `action-pin`，`subject` 為 `file:line`。
- `required_actions`：每列 {`kind`、`subject`、`blocking`、`message`、`command`}。
- `verification`：{`candidate`、`hook`、`render_parity`}；`render_parity` 只有 `state`。update（不含 reinstall）由 Issue #1063 的共用規劃器填入：以舊 template 實際詢問的答案與可信快照重建的舊側 render，與 target 逐檔相同為 `equal`，否則為 `diverged`；adopt 與 reinstall 為 `null`。
- `writing_guide`（`2.3.0`，Issue #1224）：寫作指引的唯讀檢查提示，不需要提示時為 `null`。形狀為 {`reason`、`guides`、`files`、`instruction`}：`reason` 是 `first`（target provenance 沒有記錄指引版本）或 `changed`（記錄的版本與這次收到的不同）；`guides` 列出這次 render 的指引路徑（`.csarc/docs/writing-guide.en.md`，文件語言含繁體中文時另有 `.csarc/docs/writing-guide.md`）；`files` 列出 target 的 project-owned 文件：`README.md`、`documentation_languages` 有第二個語言時的 `README.<lang>.md`，以及 `docs/` 下的 Markdown 檔（不跟隨 symlink）；`instruction` 是 agent 可以直接執行的一句指示。指引版本是 render 後指引檔的 SHA-256；操作寫入 `.csarc/provenance.json` 時記為 `writing_guide_sha256`，同一版本之後不再提示。版本放在 provenance 而不是 `.csarc/config.yml`，因為它是 CLI 的狀態，不是擁有者的設定（SPEC-009 只把持久的意圖存進設定檔）。`documentation_mode: off` 一律為 `null`，也不記錄版本。提示只出現在報告與終端機 plan：不改寫任何檔案，也不產生 required action，不影響 `status` 與 `applicable`。dry-run 與 `--check` 不寫 provenance，所以套用前每次規劃都會提示。
- `next_steps`：每列 {`text`、`command`}，由 operation 與 status 算出。update 為 `blocked` 且 blocking 項目全是 `file-conflict` 時，依序列出帶 `--to`／`--expected-sha` 的 `--finalize-plan --decision` 指令與 `--apply-plan <報告目錄>/csarc-update-final-plan.json`（Issue #1147）。
- `setup`（`2.1.0` 新增，Issue #1078）：adopt 的設定問卷紀錄 {`work_mode`、`questions`、`warnings`、`approval_route`}；update 與沒有紀錄的 adopt（例如 `--finalize`）為 `null`。`work_mode` 是展開的工作模式（只顯示，不寫入設定檔）；`questions` 是 TTY 依序詢問的鍵，non-interactive 為 `[]`；`warnings` 每列 {`code`、`subject`、`message`、`command`}，`code` 是 SPEC-009 的穩定代碼（`W` 加兩位數字與名稱，例如 `W09-governance-observe`）；`approval_route` 只在 `admin_bypass` 為 `off` 或 `beta-only` 時是 {`state`、`reason`、`confirmation`}，其他為 `null`。`--apply-plan` 重播 plan 內的同一份紀錄，不再提問。

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
| `setup.work_mode` | `solo-local`、`solo-hosted`、`team`、`custom` |
| `setup.approval_route.state` | `route-observed`、`none-observed`、`inconclusive` |
| `setup.approval_route.confirmation` | `second-approver`、`copilot-entitlement`、`null` |

檔案 `action` 與 `reason`（依 action 順序）：

| Action | Reason |
| --- | --- |
| `add` | `template`、`lockfile` |
| `overwrite` | `template`、`automatic-merge`、`compatibility-shim`（`2.2.0`） |
| `move` | `layout-migration` |
| `remove` | `template-deleted` |
| `retire` | `obsolete-generated`、`excluded-orphan` |
| `preserve` | `untouched`、`product-owned`、`dirty-preserved` |
| `conflict` | `manual-merge`、`undetermined`、`move-collision`、`update-conflict`、`retire-modified` |

無法驗證（`unknown`）的 CODEOWNER 只在 `## Product state` 顯示，不算 required action；`blocked` 才產生 blocking 的 `code-owner`。

required action `kind`：`action-pin`、`code-owner`、`committed-resolution`、`file-conflict`、`mapping-decision`、`mapping-review`、`release-writer`、`render-parity`、`retire-modified`、`runtime-mismatch`、`setting-decision`、`verification`、`version-surface`、`working-tree`。`2.0.0` 的 `setting-decision` 只用於 update；`2.1.0` 也用於 adopt：non-interactive adopt 對沒有唯一來源的意圖採用建議值時（例如 `governance_mode`、偵測到 Dockerfile 時的 `container`），每個鍵各產生一列非 blocking 的 `setting-decision`。

狀態規則（validator 強制）：

- `blocked`：至少一項 `blocking: true`，`applicable` 為 false。
- `review-required`：有 required action，且沒有 blocking 項目。
- `ready`：沒有 required action，`applicable` 為 true。
- `current`：只用於 update，沒有變更也沒有 required action。
- `applied`：只由成功套用後的改寫設定，必須綁定同一個 plan digest；`blocked` 或已 `applied` 的報告不能再轉為 `applied`。
- 報告的 `status` 與 CLI exit code 是兩回事；`update --check` 的 exit code 不變。
- update 的檔案列與衝突來自 `--check` 與套用共用的同一個三方 update 規劃（Issue #1063）：衝突為 `conflict`／`update-conflict`，並產生 blocking 的 `file-conflict`；template 刪除的路徑為 `remove`／`template-deleted`。
- update 的檔案轉換只來自同一份核准 plan（Issue #1066）：不再 render 的 CSARC-owned 檔案只在與可信舊側 render byte-identical 時退役；修改過的檔案保留為 `conflict`／`retire-modified`（decision `keep-current`），並產生非 blocking 的 `retire-modified`。repository 已有的產品發版狀態（`.csarc/version.txt`、`.csarc/release-please-manifest.json`、`CHANGELOG.md`，以及搬移前的舊路徑）不被 template seed 或 update migration 改寫，列為 `preserve`／`product-owned`。套用前實際的新增、修改、搬移與刪除集合必須與核准 plan 相同，否則 fail closed；以 transaction 寫入，任一步失敗時 target 回到 byte-identical base。
- update 的 pilot 修正（Issue #1083）：所選的 product-owned Release workflow（`release_workflow`）即使由舊 render 產生，仍是產品唯一的 Release writer，不會退役或被刪除，列為 `preserve`／`product-owned`；action pin preflight 不再列出本次 plan 退役的 workflow；pin 決定的 commit 可同時更新同一行 SHA 後的版本註解。保留為 `retire-modified` 的舊路徑不是 layout 搬移來源，新位置以 `add` 列出；target 已有搬移目的地時，舊路徑也不再配對搬移。產品 ignore 規則隱藏任何 render 出的檔案時，plan 仍列出該檔，最終 candidate 則 fail closed，避免驗證過的 candidate 與實際寫入的 target 不同。移動到 `.csarc/` 的可執行 script 若仍被產品檔案（含保留的舊檔）以舊路徑或同目錄檔名呼叫，舊路徑留下 CSARC 擁有的轉呼叫 wrapper，列為 `overwrite`／`compatibility-shim`；之後的 update 在沒有任何呼叫時移除它。產品 workflow 的 action pin 若比 template pin 新且同一 major（依 `# vX.Y.Z` 註解判斷，無法判斷時維持 blocking），preflight 列為 `product-pin-newer` 且不 blocking，update 把 template workflow 對齊產品 pin，不降版。沒有已存 release owner、唯一 Release writer 又與舊 template 的非 Jinja workflow byte-identical 的 existing 專案，update 改為 `csarc-owned`：退役舊 writer、render `.github/workflows/release.yml`，版本狀態依 #1066 保留；目標 release 無法 render 該 workflow 時 fail closed。
- update 的 operator-run 修正（Issue #1146）：以 `--data` 明確確認與推導值相同的 `release_ownership`，產生的 plan 與不傳值時相同。本次將退役或刪除的 render 檔若仍被 plan 保留的檔案（未改動、`product-owned` 或自動合併的檔案）以完整路徑引用，或該檔是被呼叫工具自動讀取的設定（`zizmor.yml`、`.gitleaks.toml`、`.pre-commit-config.yaml`），改列 `preserve`／`product-owned`；`update-conflict` 的決定若保留這類引用，`--finalize-plan` 拒絕寫入。專案擁有的 repo-site 內容（`docs/site/content/`、`docs/site/data/navigation.json`、`docs/site/theme.css`，以及搬移前的舊路徑）比照產品發版狀態保留原內容，layout 搬移列為 `move`，網站產物依保留的內容重建。產品 ignore 規則會隱藏 render 檔時，`--check` 以該 ignore 檔為 subject 產生 blocking 的 `file-conflict`，`--finalize-plan` 依已決定的內容再檢查一次並拒絕仍會隱藏的決定。
- update 的 operator-run 修正（Issue #1153）：保留的 product-owned Release writer（`release_workflow`）若以完整路徑使用本次 layout 搬移的來源檔（含 release-please `simple` config 隱含的版本檔），產生以該 writer 為 subject 的 blocking `release-writer`（沿用既有詞彙），訊息列出每個 `來源 -> 目的地`；`--finalize-plan` 拒絕寫入。`conflicts/new/<path>` 與 `take-new` 記錄的位元組已含 `product-pin-newer` 對齊後的 pin，與 apply 實際寫入相同。Markdown `Impact analysis` 的 required actions 列在 blocking／non-blocking 後依 kind 列出與 `Items requiring your decision` 相同的計數；設定 `class` 仍只描述值的變化，live facts 或 native manifests 要求決定但保留原值的鍵維持 `unchanged`。這些只改 `message` 文字與 Markdown 措辭，報告形狀與 `2.2.0` 不變。
- update 的操作者決定（Issue #1154）：blocking `action-pin` 的 `message` 另寫出產品與模板 pin 的版本 tag（取自 pin 後的 `# vX.Y.Z` 註解）與 `major upgrade: yes|no|unknown`，任一側沒有 tag 或不是版本號時為 `unknown`；`.gitignore` 的 `update-conflict` 對應的 `file-conflict` 訊息最後列出新側有、current 沒有的忽略規則。`product.action_pins` 每列仍只有既有六個欄位，plan payload 也不新增欄位；報告形狀與 `2.2.0` 不變。
- update 的 operator-run 修正（Issue #1157）：保留為 `retire-modified` 的可執行 script（有執行權限或以 `#!` 開頭）若仍以完整路徑呼叫或讀取同一份 plan 退役、刪除，或沒有 compatibility shim 而搬移的檔案，對應的 `retire-modified` 改為 blocking（沿用既有詞彙），訊息列出每個 `路徑 (removed)` 或 `來源 -> 目的地`；以 `$var/路徑` 寫成的路徑也算使用。`--finalize-plan --decision <path>=take-new` 照新版本退役該檔（`retire-modified` 只接受 `take-new`，列的 `decision` 記為 `take-new`，對應的 `retire-modified` 不再列出，套用時刪除該檔）；沒有這個決定時 `--finalize-plan` 拒絕寫入。計畫保留的其他檔案仍使用被退役的檔案時，`--finalize-plan` 拒絕；`update-conflict` 決定保留的 script 內容若使用沒有 shim 的搬移來源也一樣拒絕。舊設定的 `reviewers` 退役（或 plan 刪除、退役、保留 `.github/REVIEWERS`）時，該設定列仍為 `retired`，`note` 改寫出原本的 reviewer、新的指派方式與恢復方式，並另產生一列 subject 為 `reviewers` 的非 blocking `setting-decision`，與 `widened` 一樣要求擁有者在 `--finalize-plan` 前確認。擁有者的回答以一次性 `--data reviewers=accept|pending` 給出（Issue #1168，不寫入設定）：`accept` 讓這一列不再列出，`reviewers` 設定列的 `source` 記為 `explicit`；`pending` 保留這一列並在訊息寫明待擁有者決定；沒有回答時 `--finalize-plan` 拒絕寫入，plan 沒有退役 reviewer 時帶這個值也拒絕。這些只改 `blocking`、`message` 與 `note` 的值，報告形狀與 `2.2.0` 不變。

設定分類（本 Issue 實作的通用規則；個別鍵的遷移分類由後續 Issue 補上）：adopt 的每列都是 `new`，`source` 與 `note` 取自 `setup`：問卷回答或明確 `--data` 為 `explicit`（回答的 `note` 為 `asked`），偵測、工作模式展開與建議值為 `derived`（`note` 寫出偵測來源、`work mode <name>` 或 `suggested default`）；update 前後相同為 `unchanged`、新出現為 `new`、消失為 `retired`、其他改變為 `decision`。來源不是 `explicit` 的 `decision` 產生非 blocking 的 `setting-decision`。

**Fail closed**：writer 與 renderer 先驗證整份 report；缺鍵、未知鍵、未知詞彙、`report_format_version` 不是 `2.3.0`、`2.2.0`、`2.1.0` 或 `2.0.0`、計數不符或狀態規則不成立時拋出錯誤，三個檔案都不寫，CLI 以錯誤結束。

### 5. Markdown

- H1 為 `# CSARC adoption report` 或 `# CSARC update report`，接著是 `> **Status: <banner>.** <status_reason>` 與 ``Report format version: `2.3.0` ``。
- banner：adopt 為 `Ready to adopt`、`Review required`、`Blocked`、`Adopted`；update 為 `Current`、`Ready to update`、`Review required`、`Blocked`、`Updated`。
- 九個 H2 依序一律出現，沒有內容時印 `None.`：
  1. `## Items requiring your decision`：blocking 項目在前；沒有項目時印 "No known file conflicts. This does not guarantee semantic or runtime compatibility."
  2. `## Snapshot`
  3. `## Summary of file changes`：`| Action | Files |`，七列，數量為 0 也列出。
  4. `## Impact analysis`：有 `widened` 設定時第一列固定為 `Widened settings: ... See Settings.`；`setup` 不是 `null` 時另列工作模式、提問數與 approval route，並以 H3 `### Warnings` 列出每個 WARNING（沒有時印 `None.`）。
  5. `## File changes`：`preserve` 只計數，逐列清單只在 JSON。
  6. `## Settings`
  7. `## Product state`：`- CODEOWNER verification:` 一列在 `product.code_owner` 不是 `null` 時寫出 `value` 與 `state`；是 `null`（update）時寫 `not run by this operation`，並引用 Settings 的 `code_owner` 值（沒有值時寫 no `code_owner` is configured），不再顯示 `(none)` 而與 Settings 矛盾（Issue #1167，只改 Markdown 措辭，報告形狀與 `2.2.0` 不變）。H3 只在 JSON 值不是 `null` 時出現，順序為 `### Release writers`、`### Version surfaces`、`### Action pins`、`### Reviewer rotation`、`### Behavior changes`、`### Work-item mapping`。
  8. `## Verification`
  9. `## Next steps`
- 第十個 H2 `## Writing guide` 只在 `writing_guide` 不是 `null` 時出現在最後：說明提示原因與 CSARC 沒有改任何 project-owned 文件，列出指引與最多 20 個檔案（其餘只在 JSON），最後一列是 `Agent instruction:`。
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
- 與上一個已發布 Release 相比，每個層級最多提升一次。1.1.0 是最後發布的格式；本規格定義 2.0.0。Milestone 18 中只有設定問卷的 Issue（#1078）可在 beta.2 前依 MINOR 提升一次到 2.1.0（並把 `setting-decision` 開放給 adopt）；其他 Issue 只填入已保留的欄位與詞彙。beta.2 之後，Pilot fixes 的 #1083 依擁有者 2026-10-15 決定提升一次到 `2.2.0`，只新增 `compatibility-shim`。
- `2.3.0` 相容結果（#1224）：reader 以各自規則驗證 `2.0.0`、`2.1.0` 與 `2.2.0` 報告，`writing_guide` 只在 `2.3.0` 存在；writer 只寫 `2.3.0`。Milestone 20（#1217）的 #1224 完成條件要求報告新增這一段，因此依 MINOR 規則提升一次。
- `2.2.0` 相容結果（#1083）：reader 以各自規則驗證 `2.0.0` 與 `2.1.0` 報告，`compatibility-shim` 從 `2.2.0` 起合法；當時 writer 只寫 `2.2.0`。
- `2.1.0` 相容結果（#1078 AC6）：`2.1.0` reader 以 `2.0.0` 規則驗證 `2.0.0` 報告（沒有 `setup`、`setting-decision` 只用於 update），例如舊 final plan 內嵌的報告；writer 只寫 `2.1.0`。已發布的 `2.0.0` reader 讀到 `2.1.0` 報告時以 `unsupported version '2.1.0'` fail closed，不寫任何檔案，也不部分解析；改用寫出該報告的 CLI 版本或更新的版本。
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
- [x] update 的退役保留與 product 保留欄位由 Issue #1066 填入。
- [x] update 的 final plan 由 Issue #1067 填入。
- [x] update 衝突的 base／current／new 三側檔案、指向 `--finalize-plan --decision` 的 `file-conflict` 訊息與 next steps，以及唯一的 pin 漂移規則由 Issue #1147 填入（只改 `message` 與 `next_steps` 的文字，不改報告形狀）。
- [x] `2.1.0`（Issue #1078）：adopt 的 `setup` 紀錄與 adopt `setting-decision`；`2.0.0` 報告依原規則可讀，其他版本 fail closed。
- [x] `2.2.0`（Issue #1083）：update 的 `overwrite`／`compatibility-shim` 列；`2.0.0` 與 `2.1.0` 報告依原規則可讀。
- [x] `2.3.0`（Issue #1224）：create、adopt 與 update 在首次收到或收到新版本的寫作指引時提示檢查 project-owned 文件；同一版本不重複，`documentation_mode: off` 不提示，不改寫任何檔案；`2.0.0`、`2.1.0` 與 `2.2.0` 報告依原規則可讀。

## Out of scope

- legacy migration 規則與個別設定分類。
- `update --check` 的 exit code。
- `init` 報告與報告標題在地化。
- 移除 adopt 套用後在 plan 寫入 `adoption.applied` 的既有改寫。

## Verification

- `uv run pytest tests/test_lifecycle_report.py`
- `uv run pytest tests/test_cli.py -k "report or adopt or update"`（含本機 `large` 測試）
- `python3 scripts/spec_to_issue.py validate`

## References

- [Issue #1062](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1062)：本規格的來源。
- [Issue #1078](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1078)：`2.1.0` 的 setup 紀錄與 adopt `setting-decision`。
- [Issue #530](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/530)：報告的獨立版本號；Markdown-only 改為以 report JSON 為唯一來源。
- [Issue #529](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/529)：試跑與正式執行更新同一份報告，每個目錄只有一份。
- [Issue #950](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/950)：設定 allowlist 與 secret 不出現。
- [Issue #219](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/219)：plan → confirm → apply，dry-run 零寫入。
- [SPEC-003](SPEC-003-reproducible-template-lifecycle.md)、[Transactional repository adoption ADR](../adr/transactional-repository-adoption.md)
