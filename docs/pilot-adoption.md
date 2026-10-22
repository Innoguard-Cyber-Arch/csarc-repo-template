# 真實 repository 導入試行

這份 checklist 用來驗證 CSARC 公版能否在不取代產品程式與既有設定的前提下，完成導入、線上檢查與後續 Copier 更新。每次試行都使用既有產品 repository、Issue、短分支與 PR，不建立專用測試 repo。

## 可重複 checklist

### 導入前

- 選定有明確 owner、實際產品內容與可執行驗證的 repository。
- 建立一張 Issue，列出要保留的程式、設定、文件與驗收指令。
- 盤點預設分支、可見性、GitHub 方案、既有 workflows、CODEOWNERS、語言 manifest 與乾淨工作樹。
- 驗證目標 GitHub Release、immutable 狀態、attestation、完整 commit SHA 與 CLI artifact。
- 在編號分支執行 `csarc adopt --dry-run`，保存 repo 外的純 Markdown 導入報告（含新增／編輯／移除檔案數、衝擊分析與需要決策的項目清單）與 machine plan，並保留終端的 Milestone description migration；確認新增、自動合併、覆寫、保留、人工合併、無法判定項目及已知風險後，只用 `--apply-plan` 套用未漂移的同一份計畫。報告不是沒有語意或執行期衝突的保證。

### 導入與驗證

- 選最窄的 profile；容器化語言工具鏈不應被誤判為 host-language profile。
- 保留產品 manifest、程式、測試、spec、網站內容與安全邊界。
- 把既有 agent 指引整併到 `AGENTS.md`，讓 `CLAUDE.md` 只保留 `@AGENTS.md`。
- 確認舊 CSARC Milestone description 已升級，custom description 仍列入人工審查；不可改動其狀態、期限或 Issue 關聯。
- 將既有 README 內容放入公版要求的八個區段，不刪除產品操作資訊。
- 先檢視 `apply-repository-settings.sh plan`，再套用可用政策；不可用能力須記為明確降級。
- 執行 `./scripts/verify` 與產品原有驗證；本機無法執行的項目要記錄原因。若 base 已有可信任 verifier，再由 GitHub hosted runner 補足。
- 第一張導入 PR 的 base 尚無 verifier 時，保留 repo 外的 machine plan、本機驗證結果與來源 Release／SHA，由非作者人工核對後才合併；不得改成執行 PR head script 或宣稱 hosted checks 已通過。
- 記錄耗時、衝突、人工步驟與採用／覆寫政策；合併後的 PR 由 base 上的可信任 policy gate 與唯讀 CI 驗證 candidate。

### 後續更新

- 從更新後的預設分支另開編號分支，固定下一個已驗證 release 與完整 SHA。
- 先執行 `csarc update --dry-run`，確認 working tree 未改變，再計時執行正式 update。
- 檢查 conflict marker、`.rej`、產品專屬檔案與 `.csarc/provenance.json`。
- 重跑本機與 GitHub 驗證，以第二支 PR 合併更新。
- 依證據類型調整 maturity：真實 consuming repo 證明共用導入、更新與線上 CI 邊界；語言模組則以可重現的建立、既有 repo 導入、更新與原生工具鏈驗證判定。

## Pilot 紀錄格式

每個 pilot run 在該 consumer 自己的 pilot Issue 留下一筆紀錄，Milestone 的 regression Issue 只連結它。公開文件只放格式，不寫 consumer 名稱、owner、private URL 或其他敏感 identity。欄位逐一對應 Milestone tracker `### Pilot` 的「進場條件」與「紀錄」：

| 欄位 | 填什麼 |
| --- | --- |
| Exact base／head | pilot 分支的 base 與 head 完整 SHA |
| Release | 測試的不可變 beta tag 與完整 commit SHA |
| 指令 | 依序執行的每個指令（含 `csarc update --check --json`、`--finalize-plan`、`--apply-plan`）與 exit code |
| 衝突數 | plan 列出的衝突數，以及實際需要人工決定的數量 |
| 耗時 | 每個指令的耗時與總耗時 |
| 人工決策 | 每個衝突的 `keep-current`／`take-new`／`custom` 與理由 |
| Pin | 每筆人工 pin：`file:line`、action、舊 SHA、新 SHA、pin commit SHA；必須都在 preflight 清單內 |
| 產品 diff | pin 以外的產品檔案變更；進場條件要求為空 |
| 本機 candidate | `./.csarc/scripts/verify-fast` 的 exact head、tier 與結果 |
| Native checks | 產品原有檢查的指令與結果 |
| 遮蔽報告 | 去除 identity 後的導入／更新報告，或其連結 |
| 語言偵測 | 偵測到的語言、`uncertain` 項目與最終選擇 |
| Risk 工具摘要 | `csarc risk` 對該 run 的 Issue／PR 輸出摘要 |
| 結果 | `entered`（達到進場條件）或 `blocked`；`blocked` 另附擋點分類與失敗輸出 |

卡在 beta、到不了進場條件的 run 也用同一張表：已執行的欄位照填，未執行的寫 `not-reached`，「結果」寫 `blocked`、擋點屬於 migration 或 ownership 邊界，並貼上失敗指令的完整輸出（去除 identity）。這筆紀錄就是修正 Issue 的 regression 證據。

填寫範例（虛構）：

| 欄位 | 範例 |
| --- | --- |
| Exact base／head | `1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b`／`2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c` |
| Release | `v0.0.0-beta.2`／`3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d` |
| 指令 | `csarc update --check --json` → 0；`--finalize-plan --decision README.md=keep-current` → 0；`--apply-plan` → 0 |
| 衝突數 | 1／人工 1 |
| 耗時 | 42 秒、18 秒、35 秒；總計 95 秒 |
| 人工決策 | `README.md=keep-current`：保留產品說明 |
| Pin | `.github/workflows/product.yml:12`、`actions/checkout`、`0000…aaaa`→`1111…bbbb`、pin commit `4d5e…3e4f` |
| 產品 diff | 無 |
| 本機 candidate | head `5e6f…4f5a`、`fast`、passed |
| Native checks | `make test` passed |
| 遮蔽報告 | pilot Issue 附件 `report-redacted.md` |
| 語言偵測 | `python`；無 `uncertain` |
| Risk 工具摘要 | `csarc risk register`：0 unknown、0 uncovered |
| 結果 | `entered` |

## Operator-independence run

Stable promotion 前要證明：沒有參與實作的人，只靠已發布的文件就能完成同樣的升級。這個 run 由擁有者在最後一個 beta 發布後安排，結果決定 promotion checklist 的 operator-independence 項目能不能勾選。

**執行者條件：**全新的 agent session 或人；沒有參與該 Milestone 的實作；不讀該 Milestone 的 Issue 留言、PR 討論、對話紀錄或草稿。

**可讀的文件：**只限以 release tag 固定的核准手冊（`docs/handbook/`）、手冊明確連結的文件（同一個 tag）、該 Release 的 `release-prompt.txt`，以及 target 內生成的 `.csarc/docs/csarc.md`。需要其他資訊才能繼續時，記為文件 drift 並停止，不自行補問。

**禁止：**不 push default branch、不合併、不改 repository 設定（`apply-repository-settings.sh` 只能 `plan`）、不建立新的 GitHub repository。

**步驟：**

1. 記錄 release tag 與完整 SHA，從 `release-prompt.txt` 取得固定版本的 `csarc`。
2. 在 target 的乾淨 clone 開一般分支，執行 `csarc status` 與 `csarc update --check --json`。
3. 依手冊與 `docs/install.md` 處理衝突。install.md 要求的產品準備變更（例如把模板 workflow 裡的產品 job 搬到產品 workflow、更新 blocking 的 Action pin）以獨立的產品準備 commit 在 `--finalize-plan` 前提交，再重新 `--check`；之後 `--finalize-plan`、`--apply-plan`。以 `--decision <path>=take-new` 退役保留的舊 script（install.md「保留的舊檔與過時連結」）是 plan 的決定，不是產品準備 commit，記在「衝突與決定」，不算產品 diff。
4. apply 成功後把結果 commit 到同一個分支。install.md 步驟 6 列出的後續修正（刪除保留的舊檔、修正連到舊路徑的連結、補 ignore 規則）以獨立的後續修正 commit 接著提交。在最後一個已 commit 的 head 執行 `./.csarc/scripts/verify-fast` 與產品原有檢查；產品原有檢查也在 `main` 跑一次對照。
5. 依下表記錄。驗證通過後，可以把分支推成非 default branch 的 Draft PR，只用來承載 diff；這一步是本 run 的明確指派。

`release-prompt.txt` 的「commit 只限 docs/install.md 指定的三種」在每一步都適用：步驟 3 的產品準備 commit、步驟 4 apply 後的 commit，以及步驟 4 apply 之後的後續修正 commit。步驟 5 只另外放寬 push 非 default branch 與建立 Draft PR 這兩件事；stash、套用 GitHub settings 與 push default branch 一律不做。

**必填欄位：**

| 欄位 | 填什麼 |
| --- | --- |
| Release | tag 與完整 SHA |
| 步驟紀錄 | 每一步的指令、exit code 與結果摘要 |
| 衝突與決定 | 每個衝突的決定，以及依據手冊哪一節 |
| 產品 diff 摘要 | 套用後產品檔案的變更。只能是 install.md 列出的產品準備 commit（例如產品 job 搬移、Action pin）、apply 結果與後續修正 commit（例如刪除舊檔、修正舊路徑連結、補 ignore 規則）；每個產品準備 commit 與後續修正 commit 逐條記錄 SHA、內容與依據的 install.md 章節，沒有時寫 `none`。`take-new` 退役的舊檔不列在這裡 |
| Native checks | 每個產品原有檢查的指令，以及在 `main` 與 branch 的結果 |
| 產品檢查變化 | 結果與 `main` 不同的每個產品檢查，標 `待擁有者決定`（附文件章節與列出的選項）或 `regression`；沒有時寫 `none` |
| 無依據猜測 | 會改變產品行為或治理範圍、卻找不到文件依據的猜測；沒有時寫 `none` |
| 文件不清楚 | 其餘手冊沒寫清楚、需要判斷或與工具輸出不符的地方，每一條附追蹤 Issue 編號；沒有時寫 `none` |
| 實作者協助 | `no`，或需要哪些協助；`yes` 表示這次 run 不成立 |
| 結果 | `pass` 或 `fail`；`fail` 寫出未符合下方哪一條 |

**Pass 條件：**步驟 1–4 都執行完成，並同時符合下列四條：

1. **不需要實作者協助**：「實作者協助」為 `no`。
2. **沒有無依據的猜測**：「無依據猜測」為 `none`。依文件列出的選項所做的決定不算猜測；文件沒寫、由執行者自行決定的事，只要會改變產品行為或治理範圍，就算一項。
3. **其餘不清楚之處都有追蹤**：「文件不清楚」的每一條都已在模板 repository 開 Issue，並在紀錄列出編號。這些項目本身不讓 run fail；缺少 Issue 編號時才算 fail。
4. **產品檢查沒有 regression**：產品原有檢查的結果與 `main` 不同時，只有文件已列為擁有者決定、並寫出選項的變化（例如 install.md「產品自有的 workflow audit」）可以記為 `待擁有者決定`，不算 regression。其他變化，包括文件沒有寫出選項的變化，一律記為 `regression`，run 為 `fail`。

**紀錄位置：**正式紀錄只有一處：target repository 自己的 pilot Issue 留言（填上表）。步驟 5 的 Draft PR 只承載 diff，描述連回該留言；執行者本機的檔案只是草稿，不算紀錄。Milestone tracker 的 Promotion 只記 tag、結果（`pass`／`fail`）與「是否需要協助」，不寫 consumer 名稱或 URL。

## 2026-08-24 pilot 結果

公開文件不寫 consuming repository 的名稱或數量；原始 Issue、PR 與 run 保存在該 repository 自己的紀錄中。

| 項目 | 結果 |
| --- | --- |
| Pilot | 既有 private、container-first Python 產品 repo |
| 追蹤 | pilot repository 內的 pilot Issue、導入 PR 與更新 PR |
| Profile | `ci`；產品 Python 只在 Docker 內執行，未強迫加入 host Python package 結構 |
| 導入版本 | v0.2.4，commit `a4efc0cb61fe1f99cbd0d2ee7ecab7d2aa2e3095` |
| 導入 dry-run | 新增 48、保留 45、覆寫 0、Copier 衝突 0 |
| 導入耗時 | 14.04 秒；生成後人工整併 README／agent 指引，加入產品 Docker CI |
| 更新版本 | 經驗證且 immutable 的 v0.3.1，commit `172bfe101d7001c7abb96b92cf27f92132b8eec0` |
| 更新結果 | 35.23 秒、Copier 衝突 0、人工 merge 0；產品專屬變更全數保留 |
| 本機驗證 | `./scripts/verify` 通過；Docker Desktop 未啟動，因此產品 Docker regression 無法在本機執行 |
| 線上驗證 | 導入 run 32664191977 2 分 25 秒；更新 run 32664445831 2 分 17 秒；evaluation、telemetry、OSV、Zizmor、治理與 PR policy 全部通過 |

## 採用與覆寫決策

直接採用 additive labels、squash-only merge、merge 後刪 branch、least-privilege Actions、CODEOWNERS、Issue／PR policy、OSV、Zizmor、Gitleaks、治理漂移、更新通知與 release capability detection。

產品覆寫只有 profile 與驗證分工：公版使用 `ci` profile 管治理，產品專屬 `product-ci.yml` 執行既有 Docker evaluation 與 telemetry，避免為了公版改造產品封裝。GitHub Free private repo 無法強制 Ruleset，組織政策也禁止 Actions 建立或核准 PR；desired policy 留在 repo，發版維持產品自行負責且目前未自動化，沒有假裝已受保護或已能發布。

## 試行發現

- 首次導入存在平台邊界：base 尚未有 checker，而 PR head 不受信任，不能拿它新增的 script 自我驗證。安全路徑是在 repo 外使用固定 Release／SHA 的 CLI 產生 machine plan、套用同一份未漂移 plan，再由人核對來源、diff 與本機證據；合併後才由 base 上的 policy gate 與唯讀 CI 分工。
- 產品 evaluation container 固定非 root UID，Linux hosted runner 的 bind mount 原本不可寫。Pilot 將容器執行 UID 對齊 host，並只放寬模型 cache／report 目錄；兩次線上回歸都通過。
- Copier `--pretend` 可能不輸出檔案明細，即使正式 update 仍會修改檔案。CLI 不再把空輸出宣稱為「no file changes」；Issue #1063 起改為在可丟棄的 clone 執行同一個三方 update 規劃，`--check` 與套用列出相同的衝突與檔案動作，不再呼叫 `--pretend`。

### 2026-09-01 另一個 consuming repo 的首次導入邊界

- 該 repo 導入 PR 的 base `00ad182764bedb7ece7087fefa57051ac7888fb1` 尚無 `scripts/delivery_sync.py`，因此從 trusted base 執行的 PR policy 以 `127` 停止；這不是產品測試失敗，也不能靠執行 head 程式規避。
- 導入使用不可變來源 `v0.12.2@661b843c17730c5689c99e0e9012a1b425f0e192`，rollout head 為 `d0c5ace4ca18464b057a893587ddcfef2eaf2c8d`；local same-plan apply、`scripts/verify`、`scripts/verify-skills` 與 plan conformance 都有通過證據。
- 結論是人工核准首次導入，不建立 repo 內自我 checksum 或永久 bypass。若 canonical template 為 private，也不把可讀取來源的廣域 PAT 暴露給 PR 程式碼。

## 成熟度結論

共用治理與 CI/CD-only 基線已具備真實 consuming repo、owner、導入、更新及完整線上驗證證據，維持 beta。這份真實試行驗證共用生命週期，不要求為每種語言另外維護專用測試 repo。Python、TypeScript 與 Rust 各自具備可執行的建立、既有 repo 導入、Copier 更新、鎖檔、測試、建置與封裝驗證，因此語言模組也升為 beta。Go 以可重現的建立、既有 repo 導入、Copier 更新、原生工具鏈（gofmt、`go vet`、`go test`、`go build`）與 hosted 驗證證據同樣升為 beta；Go 發版只附 source archive。真實產品採用仍會累積營運證據，但不是重複驗證模板機制的第二道 beta 門檻；同時選取多個模組不形成另一種 composition。
