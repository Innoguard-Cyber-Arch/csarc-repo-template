---
id: SPEC-011
title: Choose the verification mode by repository visibility
owner: @matheme-justyn
priority: P1
estimate: ongoing
status: approved
tracking: none
---

## Problem

`verification_mode` 只有 `local` 與 `hosted`，而且與 repository 的可見性無關。[self-hosted verification ADR](../adr/self-hosted-verification.md) 新增第三種模式 `self-hosted`：驗證在 csarc-devops 登記的 VM 上執行。public repository 不能使用 self-hosted runner，所以模式必須依可見性決定（Issue #1268，ADR D2、D7、Q2、Q7、Q8）。

## Outcome

- 兩個模式設定取代 `verification_mode`：private 時用 `verification_mode_private`，public 時用 `verification_mode_public`。
- 新專案的 private 預設仍是 `local`，public 預設為 `hosted`；既有專案依原值遷移，行為不變。
- `self-hosted` 目前只由 reader、schema 與 migration 接受，還不在 Copier 問題與 `csarc init` 的選項中提供；開放與預設切換由 #1272 處理（擁有者 2026-10-25）。
- 「尚未登記」是合法狀態；任何不完整或不合法的設定都 fail closed。
- render 只產生當下實際模式需要的檔案；實際模式與已 render 的檔案不一致時 fail closed。

## 1. 設定

| 設定 | kind | 可用值 | 新專案預設 | 規則 |
| --- | --- | --- | --- | --- |
| `verification_mode_private` | `choice` | `self-hosted`、`hosted`、`local` | `local` | repository 是 private 或 internal 時使用；`self-hosted` 尚未提供為選項 |
| `verification_mode_public` | `choice` | `hosted`、`local` | `hosted` | repository 是 public 時使用；`self-hosted` 被拒絕 |
| `self_hosted_runner` | `map` | `{}`，或 `id` 與 `registration` 兩個鍵 | `{}` | 只在 `verification_mode_private: self-hosted` 時保存 |
| `self_hosted_environments` | `multi` | `dev`、`uat` 的非空子集合 | `[dev, uat]` | 只在 `verification_mode_private: self-hosted` 時保存 |

- `self_hosted_runner: {}` 表示尚未登記，設定驗證接受。登記後 `id` 是 VM ID（小寫英數字與 `-`，1 到 32 字元，第一個字元不是 `-`），`registration` 是 csarc-devops 登記 Issue 的完整 URL：`https://github.com/<owner>/csarc-devops/issues/<n>`。只有其中一個鍵、多出其他鍵，或格式不符，都 fail closed。
- private 模式不是 `self-hosted` 時，兩個 `self_hosted_*` 鍵都不保存；出現就 fail closed。private 模式是 `self-hosted` 時，兩個鍵都必須存在。
- 兩個 `self_hosted_*` 鍵都不提問，以 `--data` 設定。模板不讀取 csarc-devops；`registration` 只檢查格式（ADR Q5）。
- `copier.yml` 的 `self-hosted` 選項帶 choice validator：只有答案本來就是 `self-hosted`（已保存或以 `--data` 傳入）時才可用，新的互動回答不能選它。
- `copier.yml` 的 `verification_mode` 改為 render 時算出的變數（`render-derived`，不保存）：public 時等於 `verification_mode_public`，其他可見性等於 `verification_mode_private`。以 `--data` 傳入不一致的值時，render 失敗。

## 2. 實際模式

- 實際模式依 repository 當下的可見性決定：`public` 用 `verification_mode_public`，`private` 與 `internal` 用 `verification_mode_private`。
- render 使用 render 時的 `project_visibility`。合併時，lifecycle（`pr_lifecycle.py merge`）以操作者的登入讀取 repository 的 `private` 欄位；讀不到或不是布林值就 fail closed（ADR Q7）。設定本身只從 trusted base 讀取（#1069）。
- 實際模式是 `self-hosted` 時，治理與 `local` 相同，合併只接受 §7 的 VM 證據，不改用 `local` 或 `hosted` 的證據（#1269）。尚未登記時，訊息列出登記步驟。唯一的例外是 §7 的離開出口。
- `verify-fast` 在 self-hosted render 中照常執行，只記錄自我聲明的本機證據（`self-attested-local`），並印出一行 `NOTICE:` 說明這不是 VM 證據；在 VM 上由 `csarc-verify.yml` 執行時不印這一行。

## 3. Render

- `self-hosted` 的 render 等同 `local` 的 render，不產生任何 hosted workflow，只多兩個檔案：唯讀驗證 workflow `.github/workflows/csarc-verify.yml` 與 VM 證據 reader `.csarc/scripts/self_hosted_evidence.py`（#1269）。其他模式不 render 這兩個檔案。
- 只 render 當下實際模式需要的檔案（ADR Q2）。可見性改變後必須重新 render：轉 public 時由 `retire`（#1271）的 PR 以 public 模式重新 render；轉回 private 時執行 `csarc update`。
- 已 render 的檔案以兩個 workflow 判斷：只有 hosted render 產生 `.github/workflows/pr-policy.yml`，只有 self-hosted render 產生 `.github/workflows/csarc-verify.yml`。lifecycle 發現實際模式與已 render 的檔案不一致時 fail closed，訊息要求執行 `csarc update` 重新 render。

## 4. Migration

- 既有專案的 `verification_mode: <值>` 依原值同時成為兩個新設定，行為不變。`copier.yml` 的兩個新問題以已保存的 `verification_mode` 作為預設，所以 raw Copier update 也得到同樣的結果。
- 依 #1069 決定 8，trusted base 的 reader 先支援新 schema，writer 才切換。reader（`csarc_config.py`、`settings_schema.py`）接受單獨出現的舊鍵 `verification_mode`（`local` 或 `hosted`），並讀成兩個可見性的同一個模式；舊鍵與任一新鍵同時出現時 fail closed。
- `csarc update` 在目標 repository 的 reader 還不認識 `verification_mode_private` 時，仍寫入舊鍵；下一次 update 由新 reader 判斷，才寫入兩個新設定。這次 update 若要改變模式（兩個值不同，或包含 `self-hosted`），指令在寫入前停止，要求先合併這次 update。
- `--data verification_mode=...` 被拒絕，訊息列出兩個新設定。
- 既有專案不自動切換到 `self-hosted`。`csarc update` 的改用建議由 #1272 加入。

## 5. 治理

- 改變 `verification_mode_private` 或 `verification_mode_public` 時，`hosted` 到 `local` 是放寬；任何切換到或離開 `self-hosted` 的變更都視為放寬。
- 任何 `self_hosted_runner` 或 `self_hosted_environments` 的變更都需要 `governance-switch` route。
- 舊鍵與新鍵在比較前先讀成同一組值，所以只改寫格式的 migration 不算放寬。

## 6. CLI

- 工作模式的 preset 改寫兩個模式設定（`solo-local` 兩者都是 `local`；`solo-hosted`、`team` 兩者都是 `hosted`），預設仍是 `solo-local`。`custom` 各問一題，private 只能選 `local` 或 `hosted`。
- 沒有 preset 或問題提供 `self-hosted`；`csarc init` 的登記指引由 #1272 加入。設定已是 `self-hosted` 而尚未登記時，合併被拒絕的訊息列出登記步驟（§2）。

## 7. VM 驗證與證據（#1269）

依 ADR D3、D4、D6（L3、L6）、D10 與 Q1。

**Runner 命名。**由 `self_hosted_runner.id`（下稱 `<id>`）與環境（`dev` 或 `uat`）推導，不含主機名稱。csarc-devops 開窗時依此註冊 runner（ADR C2）：

| 項目 | 值 |
| --- | --- |
| labels | `self-hosted`、`csarc-vm-<id>`、`csarc-env-<環境>` |
| `runner_name` | `csarc-<id>-<環境>` |
| runner group | `Default` |

**環境。**目標分支是 `main` 時為 `uat`，是 `dev/m*` 或 `dev/i*` 時為 `dev`；其他分支沒有環境，派工與合併都被拒絕。環境必須列在 `self_hosted_environments`。

**`csarc-verify.yml`。**

- 只由 `workflow_dispatch` 觸發，在 PR 的目標分支上派工。輸入：`pull_request`、`head_sha`、`environment`（只列已登記的環境）、`window_end`（UTC，例如 `2026-10-25T09:00Z`）。run 名稱帶 PR 編號與 head SHA。
- 權限只有 `actions: read`、`contents: read`、`pull-requests: read`，不引用任何 secret；`runs-on` 是上表的三個 labels；尚未登記時 VM label 是 `csarc-vm-unregistered`，登記的 VM 都不帶這個 label。所有 Action 固定完整 SHA，checkout 一律 `persist-credentials: false`。
- 第一個 step「Check the dispatch before any candidate code」來自目標分支的定義，在任何 checkout 之前以唯讀 token 確認：事件是 `workflow_dispatch`、`GITHUB_WORKFLOW_REF` 是目標分支上的 `csarc-verify.yml`、repository 是 private、PR 的 head repo 是本 repository、head SHA 等於輸入且 PR 仍開啟、PR 的目標分支是派工分支、輸入的環境等於目標分支推出的環境。任一項不符就以 `ERROR:` 結束。窗口剩不到 2 小時時，在輸出與 job summary 各印一行 `WARNING:`，提示執行 `csarc self-hosted extend --env <環境>`。
- 之後 checkout 目標分支（`github.sha`）並以 trusted executor（#1086）準備 entry point，再 checkout exact candidate。tier 是 trusted router 的 path tier 與 channel floor 中較強者；scopes 來自同一個 router。
- execution step 名稱是 `Execute self-hosted verification head=<head> tree=<tree> tier=<tier> scopes=<scopes> mode=self-hosted environment=<環境> window=<window_end>`，由 trusted-base 的 `verify` 或 `verify-fast` 對 candidate tree 執行。

**合併時的證據綁定。**`pr_lifecycle.py merge` 以操作者的登入，在 `csarc-verify.yml` 的 runs 中依 `event=workflow_dispatch`、目標分支與 lease 的 base SHA 查詢，取 run 名稱含 exact head 的最新一筆，並要求全部成立：

1. run：`event` 是 `workflow_dispatch`、`path` 是 `.github/workflows/csarc-verify.yml`、`head_branch` 是目標分支、`head_sha` 等於 lease 的 trusted base SHA、`repository` 與 `head_repository` 都是本 repository、結論是 `success`。
2. job：只有一個 job，結論是 `success`；labels、`runner_name` 與 runner group 等於上表；第一個 step 與 execution step 都成功，而且第一個 step 在前。
3. execution step：head 與 tree 等於 lease，環境等於目標分支的環境，tier 不低於 trusted router 要求的強度。
4. job 完成時間在 24 小時內（`evidence_freshness.py`）。
5. PR 的 head repo 是本 repository；合併當下的實際模式是 `self-hosted`（§2）。

合併證據記錄 run URL、run 的 `actor` 與 `triggering_actor`、runner、環境、窗口與模式，trailer 是 `CSARC-Trust: self-hosted-registered`，summary 多一行 `self-hosted-verification-trace`。窗口結束或登記撤銷不讓已完成的證據失效。

**離開 self-hosted 的出口（ADR Q1）。**trusted base 的 `verification_mode_private` 是 `self-hosted`，candidate 改成其他值，而且兩邊設定只有 `verification_mode_private`、`self_hosted_runner`、`self_hosted_environments` 不同、變更的路徑都在 `.csarc/`、`.github/` 或 `AGENTS.md` 下時，這張 governance-switch PR 改用 `local` 的本機證據合併。trailer 是 `CSARC-Trust: self-attested-local`，summary 多一行 `self-hosted-exit-trace` 說明原因。其他 PR 都不適用。

## Acceptance criteria

- [x] 兩個模式設定、登記設定、依可見性 render 與 migration 如 §1–§6（#1268）。
- [x] self-hosted 的唯讀驗證 workflow、VM 證據綁定與離開出口如 §7（#1269）。

## Out of scope

登記 PR 的檢查（#1270）、窗口指令（#1271），以及文件與手冊（#1272）。

## Verification

- root 與 template 的回歸測試涵蓋三種模式與兩種可見性、migration 不改變行為、public 設成 `self-hosted` 被拒絕，以及合併時的模式判斷。
- payload：`solo-default` 維持量測 `local` 預設；另加 `solo-self-hosted` fixture，沿用同一組預算（ADR Q2）。#1272 切換預設時再調整 fixture 名稱。
