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
- 新專案的 private 預設是 `self-hosted`，public 預設為 `hosted`（#1272，擁有者 2026-10-25 決定 8）；既有專案依原值遷移，行為不變，也不自動切換。
- Copier 問題與 `csarc init` 都提供 `self-hosted`；尚未登記時，`csarc init` 印出登記步驟，`csarc update` 在 private repository 建議改用（#1272）。
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
- `copier.yml` 的 `verification_mode_private` 依序提供 `self-hosted`、`local`、`hosted`，沒有已保存的 `verification_mode` 時預設 `self-hosted`（#1272；之前的 beta 以 choice validator 停用這個選項）。
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
- 既有專案不自動切換到 `self-hosted`。`csarc update` 在 private 或 internal repository、`verification_mode_private` 是 `local` 或 `hosted`、沒有以 `--data` 指定它、而且 `container` 沒有啟用時，印出一行 `Recommendation:`：說明新專案的預設、這次 update 保留已存的模式，並列出登記步驟（雙邊 Issue、雙方核准、在 governance-switch PR 設定 `verification_mode_private` 與 `self_hosted_runner`）。

## 5. 治理

- 改變 `verification_mode_private` 或 `verification_mode_public` 時，`hosted` 到 `local` 是放寬；任何切換到或離開 `self-hosted` 的變更都視為放寬。
- 任何 `self_hosted_runner` 或 `self_hosted_environments` 的變更都需要 `governance-switch` route。
- 舊鍵與新鍵在比較前先讀成同一組值，所以只改寫格式的 migration 不算放寬。
- 登記 PR（#1270）：改動 `verification_mode_private`、`self_hosted_runner` 或 `self_hosted_environments` 時，trusted base 先印出盤點（PR 關閉的 Issue、`registration` URL、每個設定的舊值→新值）。結果仍是 `self-hosted` 時，`registration` 必須符合 §1 的格式，`{}` 或其他 repo 的 URL 都 fail closed。離開 self-hosted 只需要 `governance-switch`。這項檢查只看格式，不讀 csarc-devops；登記是否有效由 VM 依允許清單強制（ADR D7、Q5）。

## 6. CLI

- 工作模式的 preset 改寫兩個模式設定：`csarc init` 預設的 `solo-self-hosted` 是 `self-hosted`／`hosted`（#1272），`solo-local` 兩者都是 `local`，`solo-hosted`、`team` 兩者都是 `hosted`。`custom` 各問一題，private 可以選 `self-hosted`、`local` 或 `hosted`（建議 `self-hosted`），public 只能選 `hosted` 或 `local`。
- `csarc adopt` 導入的是既有 repository，依 ADR D2「既有專案不自動切換」，預設維持 #1272 之前的 `solo-local`（`local`／`local`），不預設 `self-hosted`；要用 self-hosted 時明確選 `solo-self-hosted` 或以 `--data` 指定（#1317、ADR Q12）。
- 實際模式是 `self-hosted` 而 `self_hosted_runner` 是空的時，`csarc init` 與 `csarc adopt` 的 plan 印出設定警告 `W22-self-hosted-unregistered`（SPEC-009），列出登記步驟。設定已是 `self-hosted` 而尚未登記時，合併被拒絕的訊息也列出登記步驟（§2）。

## 7. VM 驗證與證據（#1269）

依 ADR D3、D4、D6（L3、L6）、D10 與 Q1。

**Runner 命名。**由 `self_hosted_runner.id`（下稱 `<id>`）與環境（`dev` 或 `uat`）推導，不含主機名稱。csarc-devops 開窗時依此註冊 runner（ADR C2）：

| 項目 | 值 |
| --- | --- |
| labels | `self-hosted`、`csarc-vm-<id>`、`csarc-env-<環境>` |
| `runner_name` | `csarc-<id>-<環境>` |
| runner group | `Default` |

Labels 必須恰好是表中的三個值。VM 註冊 runner 時使用 `--no-default-labels`，不得加入 GitHub runner 預設的 `Linux`、`X64` 等 label。

**環境。**目標分支是 `main` 時為 `uat`，是 `dev/m*` 或 `dev/i*` 時為 `dev`；其他分支沒有環境，派工與合併都被拒絕。環境必須列在 `self_hosted_environments`。

**`csarc-verify.yml`。**

- 只由 `workflow_dispatch` 觸發，在 PR 的目標分支上派工。輸入：`pull_request`、`head_sha`、`environment`（只列已登記的環境）、`window_end`（UTC，例如 `2026-10-25T09:00Z`）。run 名稱帶 PR 編號與 head SHA。
- 權限只有 `actions: read`、`contents: read`、`pull-requests: read`，不引用任何 secret；`runs-on` 是上表的三個 labels；尚未登記時 VM label 是 `csarc-vm-unregistered`，登記的 VM 都不帶這個 label。所有 Action 固定完整 SHA，checkout 一律 `persist-credentials: false`。
- 第一個 step「Check the dispatch before any candidate code」來自目標分支的定義，在任何 checkout 之前以唯讀 token 確認：事件是 `workflow_dispatch`、`GITHUB_WORKFLOW_REF` 是目標分支上的 `csarc-verify.yml`、repository 是 private、PR 的 head repo 是本 repository、head SHA 等於輸入且 PR 仍開啟、PR 的目標分支是派工分支、輸入的環境等於目標分支推出的環境。任一項不符就以 `ERROR:` 結束。`window_end` 缺少、格式不對、以 runner 時鐘計算超過 24 小時之後，或剩不到 30 分鐘（等於 job 的 `timeout-minutes`）時，也以 `ERROR:` 結束並提示 `csarc self-hosted extend --env <環境>`；直接 `gh workflow run` 派工一樣受這個門檻限制（#1320）。窗口剩不到 2 小時時，在輸出與 job summary 各印一行 `WARNING:`，提示執行 `csarc self-hosted extend --env <環境>`。
- 之後 checkout 目標分支（`github.sha`）並以 trusted executor（#1086）準備 control set，再 checkout exact candidate。control set 含 entry point、`.csarc/scripts/` 的每個檢查腳本與目標分支的 `.csarc/config.yml`（#1325），所以檢查腳本與決定步驟的設定都來自目標分支，candidate 只提供被檢查的檔案；candidate 自己的測試、lint 設定、相依與 project verification hook 仍會執行。trusted 的 Python helper 以 `python3 -I` 執行，不載入 candidate 目錄裡的同名模組；站台建置的設定 reader 與設定來自 control set。hosted CI 的 `ci.yml` 用同一個 control set；它的「Read release ownership」讀 candidate 的 `release_ownership`，所以任何 `release_ownership` 變更都走 governance-switch route。tier 是 trusted router 的 path tier 與 channel floor 中較強者；scopes 來自同一個 router。
- execution step 名稱是 `Execute self-hosted verification head=<head> tree=<tree> tier=<tier> scopes=<scopes> mode=self-hosted environment=<環境> window=<window_end>`，由 trusted-base 的 `verify` 或 `verify-fast` 對 candidate tree 執行。

**合併時的證據綁定。**`pr_lifecycle.py merge` 以操作者的登入，在 `csarc-verify.yml` 的 runs 中依 `event=workflow_dispatch`、目標分支與 lease 的 base SHA 查詢，取 run 名稱含 exact head 的最新一筆。只有這一筆算數：它失敗、被取消或尚未完成時，較舊的成功 run 也不採用，合併被拒絕並要求重新派工驗證（#1319）。這一筆必須全部成立：

1. run：`event` 是 `workflow_dispatch`、`path` 是 `.github/workflows/csarc-verify.yml`、`head_branch` 是目標分支、`head_sha` 等於 lease 的 trusted base SHA、`repository` 與 `head_repository` 都是本 repository、結論是 `success`。
2. job：只有一個 job，結論是 `success`；labels、`runner_name` 與 runner group 等於上表；第一個 step 與 execution step 都成功，而且第一個 step 在前。
3. execution step：head 與 tree 等於 lease，環境等於目標分支的環境，tier 不低於 trusted router 要求的強度。
4. job 完成時間在 24 小時內（`evidence_freshness.py`）。
5. PR 的 head repo 是本 repository；合併當下的實際模式是 `self-hosted`（§2）。

合併證據記錄 run URL、run 的 `actor` 與 `triggering_actor`、runner、環境、窗口與模式；窗口另記 `window_source: operator-declared`，表示結束時間來自派工輸入、不是 VM 證明，trace 行寫成 `window=<window_end> window_source=operator-declared`（#1320）。trailer 是 `CSARC-Trust: self-hosted-registered`，summary 多一行 `self-hosted-verification-trace`。窗口結束或登記撤銷不讓已完成的證據失效。

**離開 self-hosted 的出口（ADR Q1）。**trusted base 的 `verification_mode_private` 是 `self-hosted`，candidate 改成其他值，而且兩邊設定只有 `verification_mode_private`、`self_hosted_runner`、`self_hosted_environments` 不同、變更的路徑都在 `.csarc/`、`.github/` 或 `AGENTS.md` 下時，這張 governance-switch PR 改用 `local` 的本機證據合併。trailer 是 `CSARC-Trust: self-attested-local`，summary 多一行 `self-hosted-exit-trace` 說明原因。其他 PR 都不適用。出口的本機證據由 trusted base 的驗證器產生：在 base 的 worktree 執行 `CSARC_VERIFICATION_SUBJECT_ROOT=<candidate> <base>/.csarc/scripts/verify-fast`；記錄器與檢查腳本來自 base，是否記錄、要跑哪些步驟由 base 的設定決定（入口的 `check_root`、`local_verification.py record --control-root`、`csarc_config.py --config`）；腳本檢查 candidate 的檔案。base 提供檢查腳本與設定，只能防止 candidate 直接改掉自己的檢查；這不是隔離邊界：candidate 的測試與程式碼在同一台機器、以同一個使用者執行，可能改寫 base 的 worktree，所以證據仍是 `self-attested-local`。`retire` 的 public render 不帶記錄器，candidate 自己的 `verify-fast` 不會記錄。出口缺證據時，lifecycle 的錯誤訊息印出這個指令（#1318）。

**第一次登記（ADR Q12，#1317）。**新專案預設 `self-hosted`，`self_hosted_runner` 是 `{}`，VM 還不能執行這個 repository 的驗證，所以登記 PR 本身拿不到 VM 證據。trusted base 的 `verification_mode_private` 是 `self-hosted` 而且 `self_hosted_runner` 是空的，candidate 仍是 `self-hosted` 並填入 `self_hosted_runner`，兩邊設定只有 `self_hosted_runner`、`self_hosted_environments` 不同，而且變更的檔案（`git diff --no-renames`，搬移的兩端都算）只有 `.csarc/config.yml`、`.github/workflows/csarc-verify.yml` 與 `.csarc/provenance.json` 時，lifecycle 逐檔檢查：三個檔案在 base 與 head 都必須是 mode `100644` 的一般檔案；workflow 以 bytes 比對，必須等於 trusted base 的版本只把 `'csarc-vm-unregistered'` 換成 `'csarc-vm-<id>'`、`options` 換成新的環境清單；provenance 除了 `applied_at`、`previous` 與 settings 的 digest 之外都必須相同，`final_plan_sha256` 只能保留或移除、不能換成新值，settings 的 context 只能在兩個 self-hosted 設定不同（settings 的 digest 只供參考，CLI 下次寫入前自己檢查）。全部符合時，這張 governance-switch PR 改用 `local` 的本機證據合併。trailer 是 `CSARC-Trust: self-attested-local`，summary 多一行 `self-hosted-registration-trace`，寫出 VM ID 與 csarc-devops Issue URL。base 已經登記、candidate 清空或改掉 runner、改了其他設定時不是登記，仍要求 VM 證據。登記 PR 另外改了其他檔案或內容不符時，以 `Self-hosted registration: <路徑> changes more than registering self_hosted_runner renders (ADR Q12)` 停止。離開出口（Q1）只檢查設定與路徑前綴、不比對內容，路徑同樣以 `--no-renames` 列出。

## 8. 窗口指令與工具鏈 image（#1271）

依 ADR D7、D8、D9、D10、D11 與 Q4。指令都在 `csarc` CLI（`src/csarc_cli/self_hosted.py`），不進生成專案。

**共同規則。**

- 每個指令先印出唯讀盤點（`Inventory: <動作> (read-only)`）。會改變狀態的 `open`、`extend`、`close`、`verify`、`retire` 只在加上 `--apply` 時動作；沒有 `--apply` 時印出一行 `NOTICE:`，什麼都不改，以 0 結束。`status` 永遠唯讀。
- GitHub 呼叫一律使用操作者自己的 `gh` 登入，不讀取、不保存 `gh auth token`。設定以 contents API 從 trusted ref 讀取：`verify` 讀 PR 的目標分支，其他指令讀預設分支。
- `open`、`extend`、`close`、`retire` 需要 repository 管理員；`open` 與 `extend` 還要求 repository 是 private、`verification_mode_private` 是 `self-hosted`、已登記，而且環境列在 `self_hosted_environments`，任一項不符就在取得 token 之前停止。
- 窗口紀錄只在 VM 端，經交付管道讀取；不寫 repository variable。

**交付管道（ADR C1）。**csarc-devops 提供一個本機指令，操作者以環境變數 `CSARC_SELF_HOSTED_CHANNEL` 指定（以 shell 規則切成參數）。csarc 每次請求執行它一次：從標準輸入送一個 JSON 物件，從標準輸出讀一個 JSON 物件，不經命令列參數或檔案。子程序的環境移除 `GH_TOKEN`、`GITHUB_TOKEN`、`GH_ENTERPRISE_TOKEN` 與 `GITHUB_ENTERPRISE_TOKEN`。

| 欄位 | 方向 | 內容 |
| --- | --- | --- |
| `protocol` | 請求與回應 | `csarc-self-hosted-channel/1` |
| `action` | 請求 | `open`、`extend`、`close` 或 `status` |
| `repository`、`vm`、`environment`、`runner_name` | 請求 | repo 全名、`self_hosted_runner.id`、`dev` 或 `uat`、§7 的 runner 名稱；`open` 與 `status` 另帶 §7 的 `labels` |
| `ends_at` | 請求 | `open` 與 `extend` 的新結束時間（UTC，例如 `2026-10-25T09:00Z`） |
| `registration_token` | 請求 | 只有 `open` 帶；一小時內有效，用完即丟 |
| `result` | 回應 | `ok` 或 `refused`；`refused` 另帶 `reason`，例如 `registration expired` |
| `window` | 回應 | 沒有窗口時是 `null`；否則有 `runner_name`、`started_at`、`ends_at` 與 `registration`（`active` 或 `expired`） |

`open` 只有在 runner 已上線並等候 job 時才能回 `ok`；VM 必須先等到 runner 輸出 `Listening for Jobs`，讓後續 GitHub runner 讀回得到 `online`。尚未 ready 或等待逾時都不得回 `ok`。

- 沒有設定管道時 fail closed：`open`、`extend`、`status`、`verify` 以 `ERROR:` 結束，`open` 在取得註冊 token 之前就停止。`close` 仍以管理員憑證移除 runner，並以 `NOTICE:` 說明 VM 會在窗口到期時停止 runner。
- 回應不是 JSON 物件、`protocol` 不符、`result` 不是 `ok` 或 `refused`、時間或 `registration` 的值不符時都 fail closed，不當作成功。

**指令。**

| 指令 | 盤點 | `--apply` 之後 |
| --- | --- | --- |
| `csarc self-hosted open --env dev\|uat` | repo 與可見性、管理員、VM、登記 URL、環境、runner 名稱與 labels、窗口內只會執行唯讀的 `csarc-verify.yml`、既有 runner、結束時間（現在＋24 小時） | 已有出現預期之外的 runner 就拒絕。以操作者的 `gh` 取得註冊 token，只放在記憶體並經管道交給 VM；之後讀回 runner 清單，要求只有一個符合 §7 命名的線上 runner。出現任何預期之外的 runner 時移除全部 runner 並以錯誤結束。同一環境已有 runner 時等同 `extend`，不取得 token |
| `csarc self-hosted extend --env dev\|uat` | 目前與新的結束時間（現在＋24 小時，不累加） | 要求窗口有效、同一 runner 在線；不取得 token，經管道把結束時間改為現在＋24 小時。VM 回報的結束時間超過現在＋24 小時就以錯誤結束；讀回時仍只有一個 runner |
| `csarc self-hosted close --env dev\|uat` | 該環境的 runner | 以管理員憑證刪除該環境的 runner，並經管道通知 VM |
| `csarc self-hosted status [--env dev\|uat]` | 模式、登記、runner；每個環境的開始、結束與剩餘時間 | 唯讀。剩不到 2 小時印出 `WARNING:` 要求 `extend`；剩不到 30 分鐘印出 `WARNING:` 說明不再接受新的 job；登記到期印出 `WARNING:`；repo 是 public 但仍有 `csarc-verify.yml` 的 run 或 self-hosted 設定時，印出 `WARNING:` 要求 `retire`；尚未登記時以 `NOTICE:` 印出登記步驟 |
| `csarc self-hosted verify --pr <N>` | 可見性與實際模式、head repo、head SHA、目標分支、環境、窗口剩餘時間 | repo 是 public、實際模式不是 `self-hosted`、PR 不是 open、PR 來自 fork、目標分支沒有環境、尚未登記、環境未登記、沒有窗口或剩不到 30 分鐘時拒絕。剩不到 2 小時時印出 `WARNING:`。以 `workflow_dispatch` 在目標分支上觸發 `csarc-verify.yml`，輸入 PR 編號、head SHA、環境與窗口結束時間 |
| `csarc self-hosted retire [--private-mode hosted\|local] [--issue N]` | `csarc-verify.yml` 的 run、它們的 artifact、repository 的**全部** Actions cache（cache 不屬於特定 workflow，所以全部列出）、repository 的**全部** runner（不只 VM 的），以及設定變更；`verification_mode_private` 是 `self-hosted` 時，另以 `--apply` 使用的同一套 Copier 驗證檢查 public 模式的設定，列出每個不合格的設定與原因，並以非 0 結束（#1315） | 刪除盤點中的 artifact、run、cache 與 runner。`verification_mode_private` 是 `self-hosted` 時，開一張 Issue（或使用 `--issue N`），以下游的 `gh-issue-develop` 從預設分支建立並連結 `chore/<N>-leave-self-hosted`，在其上執行 `csarc update --data verification_mode_private=<模式> --data project_visibility=public`，建立以 `Closes #N` 連結、帶 `governance-switch` label 的 draft PR；失敗時不留下本機分支或工作目錄；新模式預設等於 `verification_mode_public`。不直接修改 repository 設定（Q4）。印出給 csarc-devops 的退出通知。任何一項失敗都以非 0 結束，並說明公開後哪些 log 仍會被看到 |

**`retire` 是轉成 public 之前的必要步驟。**先執行不帶 `--apply` 的盤點，確認後再加 `--apply`；public 模式不接受的設定要先以 governance-switch PR 改好，否則盤點與 `--apply` 都以非 0 結束，不刪除資料、不建立分支；合併它建立的 PR 之後，才改變 repository 的可見性。沒有先 `retire` 就公開時，`status`、`csarc update`（終端機與報告）和 lifecycle 的 `check`、`merge` 以同一個判斷（`merge_trace.retire_warning`）印出同一個 `WARNING:` 要求 `retire`；讀不到可見性或 run 清單時改印 `WARNING:` 說明沒有檢查，合併判斷不變（#1287）。repo 已是 public 而 trusted base 仍是 self-hosted render 時，lifecycle 拒絕所有 PR，訊息要求把 repo 轉回 private、執行 `retire --apply`、合併它的 PR 再公開；public 期間不開任何合併例外（ADR D9、Q13，#1318）。

**工具鏈 image（ADR D8、C9）。**`profiles/self-hosted-toolchain.json` 是給 csarc-devops 的機器可讀清單：image 以 sha256 digest 固定、每個 job 一個新容器並以非 root 執行，禁止 docker socket、privileged、host network、metadata endpoint 與長期 secret；基礎工具（含 trusted policy 用的 Python 與 uv）、`install-tool` 下載的掃描工具、依（repo, 環境）分開的快取，以及每個語言 profile 的工具版本。版本與 `profiles/catalog.yaml` 和 hosted workflow 的固定版本一致，由回歸測試檢查。`container` 模組需要 Docker daemon，VM 禁止 docker socket，所以啟用它的 repo 不能在 self-hosted 模式驗證。

## 9. `container` 模組的限制（#1281）

- **限制。**VM 目前不給 job Docker daemon（ADR D8 第 4 點），`verify_container` 因此無法在 VM 上執行。`container: true` 加上 `verification_mode_private: self-hosted` 一律 fail closed：root 與 template 的 reader（`csarc_config.py`，lifecycle 與 VM 證據 reader 都經過它）、`csarc update`／`csarc init` 寫入設定時的 schema 檢查，以及 Copier 的 `container` validator。訊息說明原因（ADR D8），並建議把 `verification_mode_private` 改成 `local` 或 `hosted`，或關閉 `container`。
- **判斷依據。**reader 看不到 repository 的可見性，所以以 `verification_mode_private` 判斷：只有它能讓實際模式成為 `self-hosted`（§1）。`verification_mode_public` 不受影響，`container` 加上 `hosted` 或 `local` 照常可用。
- **解除條件。**ADR 修訂（D8 第 7 點：job 容器內隔離的 Docker daemon）經擁有者核准，而且 csarc-devops 在 C11 確認可行之後，以後續 Issue 移除這個限制；`verify.jinja` 的 Docker 步驟不變。

## Acceptance criteria

- [x] 兩個模式設定、登記設定、依可見性 render 與 migration 如 §1–§6（#1268）。
- [x] self-hosted 的唯讀驗證 workflow、VM 證據綁定與離開出口如 §7（#1269）。
- [x] 登記 PR 的盤點與 `registration` 格式檢查如 §5（#1270）。
- [x] 窗口指令、交付管道與工具鏈 image 契約如 §8（#1271）。
- [x] `container` 加上 self-hosted 的限制與解除條件如 §9（#1281）。
- [x] 新專案預設切換為 `self-hosted`、Copier 與 `csarc init` 提供這個選項、`W22` 登記指引與 `csarc update` 的改用建議如 §1、§4、§6（#1272）。
- [x] 未登記 self-hosted base 的第一次登記 PR 以本機證據合併、`csarc adopt` 預設維持 `solo-local` 如 §6、§7（#1317）。
- [x] `retire` 退出 PR 以 trusted base 的驗證器取得本機證據、沒先 `retire` 就公開時的補救訊息與刪除範圍如 §7、§8（#1318）。
- [x] hosted CI 與 VM 的檢查腳本與決定步驟的設定來自 trusted base 的 control set，如 §7（#1325）。

## Out of scope

文件、登記指引與手冊由 `docs/ci-policy.md` 與手冊負責（#1272）。窗口指令（#1271）見 §8；交付管道本身、VM、hook 與 image 的建置由 csarc-devops 負責。

## Verification

- root 與 template 的回歸測試涵蓋三種模式與兩種可見性、migration 不改變行為、public 設成 `self-hosted` 被拒絕，以及合併時的模式判斷。
- payload：`solo-default` 量測 `solo-self-hosted` 預設（#1272）；`solo-local` fixture 量測原本的 `local` 預設，沿用同一組預算（ADR Q2）。
- #1272：`tests/test_verification_mode_settings.py` 涵蓋 Copier 與 `csarc init` 的新預設、payload fixture 與 `csarc update` 的改用建議；`tests/test_setup_questions.py` 涵蓋 `W22`。
- #1317：`tests/test_self_hosted_verification.py` 涵蓋 root 與 template 的第一次登記判斷、拒絕的情境、逐檔內容比對（以實際 `csarc-verify.yml.jinja` render 比對）、以真實 Git 搬移檔案時 Q1 與 Q12 都看到來源路徑、真實 Git 的 CRLF 不等於 render、symlink 與可執行檔被拒、`final_plan_sha256` 不能換成新值，以及從未登記 base 經 lifecycle 合併的 snapshot 與 `self-hosted-registration-trace`；`tests/test_setup_questions.py` 涵蓋 adopt 的預設工作模式。
- #1318：`tests/test_self_hosted_exit_evidence.py` 以實際 render 證明 `retire` 預設的 hosted 退出 PR 自己的 `verify-fast` 不記錄、base 的驗證器能記錄，而且 base 的 Q1 判斷與證據檢查都接受；`tests/test_local_verification.py` 涵蓋 `--control-root`；`tests/test_self_hosted_verification.py` 涵蓋公開後的補救訊息與出口缺證據的提示；`tests/test_self_hosted_window.py` 涵蓋刪除範圍。
- #1325：`tests/test_trusted_check_scripts.py` 以實際 hosted 與 self-hosted render，執行 `ci.yml` 與 `csarc-verify.yml` 的保存與執行 step：candidate 把檢查腳本改成 `exit 0` 並放入衝突標記時兩條路徑都失敗；對照組把入口改回讀 candidate 的檢查時同一個 candidate 通過。`tests/test_base_policy.py` 涵蓋 control set 的內容與 `release_ownership` 變更的 route；`test_candidate_cannot_shadow_the_trusted_interpreter` 在 candidate 放入 `json.py` 或 `json/` 時兩條路徑都通過且沒有載入它們，對照組拿掉 `-I` 時失敗；`tests/test_trusted_check_isolation.py` 涵蓋站台設定 reader、wheel 匯入檢查與 `--no-config`。
- §8：`tests/test_self_hosted_window.py` 以 GitHub 與交付管道的 stub 涵蓋每個指令的盤點與拒絕路徑、沒有 `--apply` 時不改變任何東西、沒有管道時 fail closed、`extend` 不取得 token 也不註冊第二個 runner、預期之外的 runner 被全部移除、token 不出現在命令列、輸出與檔案，以及工具鏈清單與語言 profile 一致。
- §9：`tests/test_verification_mode_settings.py` 的 container 測試涵蓋 root 與 template：self-hosted 加上 `container` 在 reader、CLI 寫入、lifecycle 與 Copier validator 都被拒絕；`hosted`、`local` 與每個 public 模式加上 `container` 不受影響。
