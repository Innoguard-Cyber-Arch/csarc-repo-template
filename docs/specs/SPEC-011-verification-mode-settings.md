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
- 新專案的 private 預設為 `self-hosted`，public 預設為 `hosted`；既有專案依原值遷移，行為不變。
- 「尚未登記」是合法狀態；任何不完整或不合法的設定都 fail closed。
- render 只產生當下實際模式需要的檔案；實際模式與已 render 的檔案不一致時 fail closed。

## 1. 設定

| 設定 | kind | 可用值 | 新專案預設 | 規則 |
| --- | --- | --- | --- | --- |
| `verification_mode_private` | `choice` | `self-hosted`、`hosted`、`local` | `self-hosted` | repository 是 private 或 internal 時使用 |
| `verification_mode_public` | `choice` | `hosted`、`local` | `hosted` | repository 是 public 時使用；`self-hosted` 被拒絕 |
| `self_hosted_runner` | `map` | `{}`，或 `id` 與 `registration` 兩個鍵 | `{}` | 只在 `verification_mode_private: self-hosted` 時保存 |
| `self_hosted_environments` | `multi` | `dev`、`uat` 的非空子集合 | `[dev, uat]` | 只在 `verification_mode_private: self-hosted` 時保存 |

- `self_hosted_runner: {}` 表示尚未登記，設定驗證接受。登記後 `id` 是 VM ID（小寫英數字與 `-`，1 到 32 字元，第一個字元不是 `-`），`registration` 是 csarc-devops 登記 Issue 的完整 URL：`https://github.com/<owner>/csarc-devops/issues/<n>`。只有其中一個鍵、多出其他鍵，或格式不符，都 fail closed。
- private 模式不是 `self-hosted` 時，兩個 `self_hosted_*` 鍵都不保存；出現就 fail closed。private 模式是 `self-hosted` 時，兩個鍵都必須存在。
- 兩個 `self_hosted_*` 鍵都不提問，以 `--data` 設定。模板不讀取 csarc-devops；`registration` 只檢查格式（ADR Q5）。
- `copier.yml` 的 `verification_mode` 改為 render 時算出的變數（`render-derived`，不保存）：public 時等於 `verification_mode_public`，其他可見性等於 `verification_mode_private`。以 `--data` 傳入不一致的值時，render 失敗。

## 2. 實際模式

- 實際模式依 repository 當下的可見性決定：`public` 用 `verification_mode_public`，`private` 與 `internal` 用 `verification_mode_private`。
- render 使用 render 時的 `project_visibility`。合併時，lifecycle（`pr_lifecycle.py merge`）以操作者的登入讀取 repository 的 `private` 欄位；讀不到或不是布林值就 fail closed（ADR Q7）。設定本身只從 trusted base 讀取（#1069）。
- 實際模式是 `self-hosted` 時，在 VM 證據的讀取上線（#1269）之前，lifecycle 一律拒絕合併，不改用 `local` 或 `hosted`。尚未登記時，訊息列出登記步驟；已登記時，訊息要求更新 CSARC。
- `verify-fast` 在 self-hosted render 中照常執行，只記錄自我聲明的本機證據（`self-attested-local`），並印出一行 `NOTICE:` 說明這不是 VM 證據。

## 3. Render

- `self-hosted` 的 render 等同 `local` 的 render，不產生任何 hosted workflow。唯讀驗證 workflow 與 VM 證據 reader 由 #1269 加入。
- 只 render 當下實際模式需要的檔案（ADR Q2）。可見性改變後必須重新 render：轉 public 時由 `retire`（#1271）的 PR 以 public 模式重新 render；轉回 private 時執行 `csarc update`。
- 已 render 的檔案以 `.github/workflows/pr-policy.yml` 判斷：只有 hosted render 產生它。lifecycle 發現實際模式與已 render 的檔案不一致（實際模式是 `hosted` 卻沒有這個檔案，或反過來）時 fail closed，訊息要求執行 `csarc update` 重新 render。

## 4. Migration

- 既有專案的 `verification_mode: <值>` 依原值同時成為兩個新設定，行為不變。`copier.yml` 的兩個新問題以已保存的 `verification_mode` 作為預設，所以 raw Copier update 也得到同樣的結果。
- 依 #1069 決定 8，trusted base 的 reader 先支援新 schema，writer 才切換。reader（`csarc_config.py`、`settings_schema.py`）接受單獨出現的舊鍵 `verification_mode`（`local` 或 `hosted`），並讀成兩個可見性的同一個模式；舊鍵與任一新鍵同時出現時 fail closed。
- `csarc update` 在目標 repository 的 reader 還不認識 `verification_mode_private` 時，仍寫入舊鍵；下一次 update 由新 reader 判斷，才寫入兩個新設定。這次 update 若要改變模式（兩個值不同，或包含 `self-hosted`），指令在寫入前停止，要求先合併這次 update。
- `--data verification_mode=...` 被拒絕，訊息列出兩個新設定。
- 既有專案不自動切換到 `self-hosted`。private repository 的 `csarc update` 報告以 `Recommendation:` 建議改用，並列出登記步驟。

## 5. 治理

- 改變 `verification_mode_private` 或 `verification_mode_public` 時，`hosted` 到 `local` 是放寬；任何切換到或離開 `self-hosted` 的變更都視為放寬。
- 任何 `self_hosted_runner` 或 `self_hosted_environments` 的變更都需要 `governance-switch` route。
- 舊鍵與新鍵在比較前先讀成同一組值，所以只改寫格式的 migration 不算放寬。

## 6. CLI

- `csarc init` 的預設工作模式改為 `solo-self-hosted`：`verification_mode_private: self-hosted`、`verification_mode_public: hosted`、`admin_bypass: always`、`copilot_review: allowed`、`lifecycle: []`、`scheduled_checks: []`。`csarc adopt` 的預設維持 `solo-local`。
- 實際模式是 `self-hosted` 而且尚未登記時，plan 印出 `W16-self-hosted-unregistered`，內容是登記步驟。

## 7. 驗證

- root 與 template 的回歸測試涵蓋三種模式與兩種可見性、migration 不改變行為、public 設成 `self-hosted` 被拒絕，以及合併時的模式判斷。
- payload：`solo-default` 量測新的預設（private `self-hosted`），沿用原預算；另加 `solo-local` fixture，沿用同一組預算（ADR Q2）。

## 8. 不在本規格範圍

唯讀驗證 workflow、VM 證據的讀取與綁定（#1269）、登記 PR 的檢查（#1270）、窗口指令（#1271），以及文件與手冊（#1272）。
