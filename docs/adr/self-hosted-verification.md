# Self-hosted verification mode ADR

- **狀態：**Proposed
- **日期：**2026-10-24
- **來源 Issues：**[#1266](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1266)、[#1265](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1265)（Milestone 21 tracker，擁有者 2026-10-24 決定）
- **實作 PR：**待擁有者核准本草稿後，由 #1266 的 PR 填入

## 問題與限制

目前只有兩種驗證模式。`local` 在開發者電腦上執行，結果只能自我證明（`self-attested-local`）；`hosted` 在 GitHub-hosted `ubuntu-latest` 執行，結果可信，但耗用 GitHub 運算額度，每次都從零建立環境。擁有者 2026-10-24 在 #1265 決定新增第三種 `verification_mode: self-hosted`：csarc-devops 提供的團隊 VM 安裝 GitHub 官方 self-hosted runner，由 GitHub 派工；DEV、UAT、PRD 三個常駐環境分別承接 Issue、Milestone、Release 的驗證；只開放給登記的 repo，外部 fork 的 PR 一律不在 VM 執行；登記變更要由兩邊 Issue 互相連結、雙方核准。本 ADR 把這些決定落成可實作、可測試的設計，核准前不開始 #1268 之後的實作。

撰寫本草稿時已查證的限制（2026-10-24，base `2035b0d`）：

1. **模板 repo 是 public。**GitHub 的說明是 self-hosted runner「幾乎不應該」用在 public repo，因為任何人都能開 PR 在機器上執行程式碼（[Security hardening：Hardening for self-hosted runners](https://docs.github.com/en/actions/reference/security/secure-use#hardening-for-self-hosted-runners)）。tracker 的 Out of scope 也排除 public repo。因此模板 repo 本身維持 `hosted`；self-hosted 只給已登記的 private 下游 repo，模板以測試與一個實際登記的下游 repo 驗證（#1265 AC1）。
2. **組織是 GitHub Free 方案。**只有一個 default runner group，要建立其他 runner group 需要 Team 方案；default group 預設只讓 private repo 使用（[Managing access to self-hosted runners using groups](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access)）。組織層級的 runner 若放在 default group，組織內每個 private repo 都能用 label 派工上去，等於沒有「只限登記 repo」。label 只是路由，不是存取控制。
3. **csarc-devops 是 private repo。**下游 workflow 的 `GITHUB_TOKEN` 只能讀自己的 repo，讀不到 csarc-devops 的 Issue 留言。跨 repo 唯讀需要另一個憑證（見待決問題 O1）；AGENTS.md 不允許把 personal token 當成 portable baseline。
4. **現有證據只接受 GitHub-hosted runner。**`scripts/verification_evidence.py` 要求 job labels 含 `ubuntu-latest`、`runner_group_name` 等於 `GitHub Actions`，含 `self-hosted` label 一律拒絕；merge trace 的 `CSARC-Trust` 只有 `github-hosted` 與 `self-attested-local` 兩個值（`scripts/merge_trace.py`）。
5. **hosted 專屬的 payload 全以 `verification_mode == 'hosted'` 決定是否 render**（`copier.yml` 的 `_exclude`，約 30 個條件）。self-hosted 需要同一組 workflow 與 script。
6. **trusted executor 不是 sandbox。**[trusted-base-gate](trusted-base-gate.md) 已寫明：它防的是 candidate 改 gate 讓自己通過，candidate 的測試碼仍在同一台機器執行。GitHub-hosted VM 用完即丟，所以這個限制只影響單一 job；常駐 VM 上，惡意或出錯的測試碼可以留下影響後續 job 的狀態（GitHub 同一份說明：persistent runner 被入侵後可能持續存在，也會影響之後其他 repo 的 workflow）。
7. **`verify` 由 `pull_request_target` 載入 base 的 workflow，但會 checkout 並執行 candidate 的測試。**任何會觸發 `verify` 的 PR，包含 fork PR，都會把 candidate 程式碼帶到執行 `verify` 的機器上。不能依賴 repo 的 fork PR 核准設定擋住它（[Managing GitHub Actions settings：fork pull request workflows in private repositories](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#controlling-changes-from-forks-to-workflows-in-private-repositories)），排除必須寫在 workflow 與 lifecycle 裡。
8. **payload 餘裕很小。**`scripts/generated_payload.py` 在 `2035b0d` 實測：hosted fixture 距總閘 2,828 B；verification 分項在 hosted 只剩 810 B，Dependabot 分項約 1,000 B；agent 文件 token 在 hosted 剩 540；hosted 具寫入權限的 workflow 已達上限 10／10。#1231 規定預算只能下調，上調要修訂 ADR 並由擁有者核准。
9. **[先盤點、再動作](dry-run-inventory-before-action.md) 適用。**登記、派工與服務啟動都會讓尚未驗證的設定或程式碼產生作用，必須先輸出唯讀盤點。

不在本 ADR 範圍：VM 的建置與維運、csarc-devops 允許清單本身的實作、產品部署管線（CD）、修改下游 repo 設定。

## 決定

以下 D1–D9 是提交擁有者核准的設計。標示「建議」的項目有替代做法，列在「待決問題」，核准時一併決定。

### D1. 定位：hosted 的控制加上換一台執行機器

`self-hosted` 是 `hosted` 的變體，不是新的一套流程：

- required checks（`title`、`verify`、`review`）、Ruleset、GitHub Actions App integration ID 綁定（#835）、trusted executor（#1086、#1069）、exact-head 授權、remote lease、24 小時證據期限（[verification-evidence-freshness](verification-evidence-freshness.md)）與 merge trace（#1073）全部沿用，不放寬任何一項。
- 差別只有三處：執行 candidate 程式碼的 job 改派到登記的 runner（`runs-on`）；證據多綁定 runner 與環境；merge trace 使用新的信任值。
- render 規則：所有以 `verification_mode == 'hosted'` render 的檔案，在 `self-hosted` 也 render；self-hosted 專屬的程式放在只有 `self-hosted` 才 render 的 sibling（沿用 #1177 hosted sibling 的做法），既有 `local`、`hosted` 專案的 payload 與行為不變。
- **建議：只有會執行 candidate 程式碼的驗證 job 派到 VM。**`verify`、release workflow 的重新驗證、#1264 的 Dependabot 重新驗證屬於這類。PR policy、review、lifecycle 寫入、release 發布與 Pages 等持有寫入 token 或 secret 的 job 留在 GitHub-hosted，避免寫入權限出現在常駐機器上。這些 job 很短，仍會用到少量 hosted 額度（待決問題 O5）。

### D2. 信任模型

| 項目 | `local` | `hosted` | `self-hosted` |
| --- | --- | --- | --- |
| 誰派工 | 操作者自己執行 | GitHub | GitHub |
| 在哪執行 | 操作者電腦 | GitHub-hosted VM，每個 job 全新 | 登記的 runner，在 csarc-devops 的常駐 VM |
| workflow 與 gate 來源 | trusted base（#1069） | trusted base（`pull_request_target`、#1086） | 同 hosted |
| 結果由誰記錄 | 操作者寫入 Git metadata | GitHub Check Runs、Jobs API | 同 hosted；runner 名稱、labels、group 由 GitHub Jobs API 記錄，不由 VM 自行回報 |
| 能證明 | 某人聲稱在 exact head 跑過指定 tier | GitHub 在乾淨 VM 上以 base 的 workflow 對 exact tree 執行指定 command 並成功 | GitHub 把 base 的 workflow 派給這個 repo 登記的 runner，在預期環境對 exact tree 執行指定 command 並成功 |
| 不能證明 | 結果未被偽造；環境；GitHub 事件與權限 | candidate 測試碼本身無惡意（不是 sandbox） | 同 hosted；另外不能證明 VM 在 job 開始時是乾淨的、工具鏈與快取未被先前 job 改動，也不能排除 VM 管理者竄改執行環境 |
| 信任前提 | 操作者 | GitHub | GitHub＋csarc-devops 的隔離契約（D6）＋登記雙方核准（D5） |
| `CSARC-Trust` | `self-attested-local` | `github-hosted` | `self-hosted-registered`（新值） |

結論：`self-hosted` 比 `local` 強，因為結果由 GitHub 記錄、操作者無法只靠寫一份 JSON 就產生證據；比 `hosted` 弱，因為機器狀態跨 job 存在，信任延伸到 csarc-devops。merge trace 用獨立的信任值，事後可以用 `merge_trace.py audit` 列出所有依賴 VM 的合併（D7 的事件處理需要它）。

**證據綁定。**hosted 證據的既有欄位（repository、exact head／tree、base、tier、scopes、command、toolchain、label set、release level、結果、完成時間）全部保留，`verify` 在 self-hosted 模式另外必須符合：

1. job 的 `labels` 含 `self-hosted`、登記的 runner label，以及**由 trusted base router 計算出的預期環境** label（D3）。`ubuntu-latest` 證據在 self-hosted 模式不被接受（不靜默改回 hosted，D7）。
2. `runner_name` 符合登記的 runner 命名（`self_hosted_runner`，D5），`runner_group_name` 符合登記的 group；這些值來自 Jobs API。
3. execution step 名稱加上 `environment=<dev|uat|prd>` 與 `runner-mode=<ephemeral|persistent>`，必須與 job labels、router 的預期環境一致；任何一項不符即拒絕，訊息要求在正確環境重跑。
4. 證據 payload 與 canonical merge evidence 多記 `runner`、`environment`、`runner_mode`，`check-trusted-verification` 可以重查並顯示（#1265 AC1）。期限仍是 24 小時，不因常駐環境延長。

### D3. 環境對應：DEV↔Issue、UAT↔Milestone、PRD↔Release

環境由 trusted base 的 router 決定，candidate 不能自選。規則與 release channel floor 一樣「取較強者」，順序為 `dev` < `uat` < `prd`：

| 情況 | 環境 |
| --- | --- |
| 一般 work PR（route `issue`），不物化版本；包含 standalone 的非發版變更 | `dev` |
| 物化 beta 版本的 PR（checkpoint terminal、未宣告 checkpoint 的 Milestone work）、main→delivery 同步、`dev/m*` 與 `dev/i*` 的 merge queue | `uat` |
| 物化 stable 版本的 PR（standalone、hotfix）、`promotion`、`release-recovery`、`release/v*` guided candidate、`release.yml` 對 main tree 的重新驗證 | `prd` |

- 環境與 tier（fast／full）互相獨立：tier 仍由 `ci_tier.py` 與 channel floor 決定。
- 預期環境不在 `self_hosted_environments` 裡時 fail closed，不改用較低的環境，也不改用 hosted。
- `dev` 是必填環境（擁有者決定 4）。沒有 Milestone 流程的 repo 可以只登記 `dev` 與 `prd`；只登記 `dev` 的 repo 不能發 stable，訊息會說明要先登記 `prd`。
- Dependabot PR（#1264）依同一規則：會物化 stable 版本時用 `prd`，否則 `dev`（待決問題 O12）。

### D4. 只限登記 repo、排除 fork：五層防護

任何一層單獨失效，其他層仍然擋得住。

| 層 | 誰負責 | 控制 |
| --- | --- | --- |
| L1 GitHub 註冊 | csarc-devops | **建議用 repository 層級的 runner**：每個（repo, 環境）各自註冊，GitHub 只把該 repo 的 job 派給它。在 Free 方案這是唯一能讓 GitHub 本身拒絕其他 repo 的做法（限制 2）。組織升級到 Team 後，可改用只開放選定 repo 的 runner group。只接受 private repo。 |
| L2 workflow 派工條件 | 模板（#1269） | 派工前，一個不執行 candidate 程式碼的 GitHub-hosted route job 計算：PR head repo 是否等於本 repo、repo 是否為 private、route 與預期環境、設定是否完整。任一項不成立，VM job 不啟動，`verify` 由 hosted 的 route job 回報失敗並說明原因；fork PR 永遠走這條路。`runs-on` 的 labels 由 route job 輸出，candidate 無法改變。 |
| L3 trusted base 設定 | 模板（#1268、#1069） | `verification_mode`、`self_hosted_*` 一律從 trusted base 讀取。PR 把模式改成 self-hosted 或改動登記設定時，新設定要等合併後才生效，這張 PR 本身仍依 base 的模式驗證。 |
| L4 lifecycle | 模板（#1269、#1270） | 合併時重新檢查證據：head repo 必須等於 base repo；runner、group、環境必須屬於登記內容；不符即拒絕。 |
| L5 VM | csarc-devops | 允許清單、每個（repo, 環境）獨立的 OS 帳號與工作目錄（D6）；未列入允許清單的 repo 不註冊 runner。 |

外部 fork 的 PR：L2 不派工，L4 拒絕其證據。需要接受外部貢獻時，由維護者把變更搬到本 repo 的分支重新開 PR，與現行人工審查流程一致。

### D5. 與 csarc-devops 的登記契約

**Repo 端（`.csarc/config.yml`，#1268 實作 schema）：**

| 設定 | 型別與預設 | 意義 |
| --- | --- | --- |
| `verification_mode` | 新增選項 `self-hosted`；預設不變（新專案 `local`） | 選用本模式 |
| `self_hosted_runner` | mapping，必填：`id`（登記的機器 ID，例如 `csarc-vm-01`）、`registration`（csarc-devops 登記 Issue 的完整 URL） | 指向哪台登記機器，以及哪一張 csarc-devops Issue 承載核准。`id` 用來推導 runner label 與命名（例如 label `csarc-vm-01`、`csarc-env-dev`；`runner_name` 以 `csarc-vm-01-` 開頭），確切命名由 csarc-devops 定案（待決問題 C2） |
| `self_hosted_environments` | `dev`、`uat`、`prd` 的子集合，必含 `dev`；`csarc init` 依是否使用 Milestone 建議 `[dev, uat, prd]` 或 `[dev, prd]` | 這個 repo 登記了哪些環境 |
| `self_hosted_services` | 依環境分組的服務清單，預設空（`{}`） | 驗證用的常駐服務；每項只有名稱、啟動指令、健康檢查、停止方式，資源上限由 csarc-devops 管理（#1271） |

擁有者指定的是三個設定名稱。`registration` 放進 `self_hosted_runner` 是本草稿的建議，因為 runner 與核准 Issue 是一對一的；也可以改成獨立設定（待決問題 O7）。設定不完整、環境名稱不合法、URL 不是 csarc-devops 的 Issue，都依 schema 規則 fail closed。

**csarc-devops 端（允許清單）：**csarc-devops 維護一份允許清單，每筆至少記錄：repo 全名、runner `id`、環境、服務名稱、csarc-devops Issue、模板或下游 repo 的 Issue、核准時間。檔案格式與 runner 註冊自動化由 csarc-devops 的 Milestone 負責。模板不讀這份清單；VM 端依清單決定為哪些 repo 註冊 runner（L5）。

**變更流程。**下列任何一項都算登記變更：開始使用、增減環境、更換 runner、增改服務、撤銷登記。每次變更：

1. Repo 端開一張 Issue（模板或下游），csarc-devops 開一張 Issue，兩張互相引用完整 URL（雙向連結）。
2. csarc-devops Issue 本文含一個固定格式的登記區塊，內容等於 repo 端變更後的 `self_hosted_*` 設定與 repo 全名。
3. 兩邊各自核准。Repo 端沿用既有核准（Milestone tracker 或無 Milestone Issue 的核准）；csarc-devops 端的核准留言格式與 Milestone 核准相同：建議用 `/self-hosted approve`、`/self-hosted admin-approve: <理由>`、`/self-hosted object: <理由>`、`/self-hosted resolve: <目標>`，再加一個 `/self-hosted revoke: <理由>`（待決問題 O7）。判斷演算法與 Milestone 核准相同：以 collaborator permission API 判斷核准者權限（不看 `author_association`）；最新的有效留言決定狀態；核准之後 Issue 本文被修改，核准即失效。
4. 改動設定的 PR 帶 `governance-switch` label（#1069 既有 route）。#1270 的 gate 以唯讀 API 讀取 csarc-devops Issue 的本文與留言，確認雙向連結、登記區塊與 PR 的新設定逐字相符、核准有效。下列任一情況 fail closed，訊息依寫作指引說明原因並給下一步：讀取失敗（權限、404、API 錯誤、rate limit）、缺少任一方核准、只有單向連結、核准已失效或被反對、登記區塊與設定不符。
5. 合併後 csarc-devops 依允許清單註冊 runner。

**建議：退出 self-hosted（改回 `hosted` 或 `local`、移除環境）只需要 repo 端核准**，並開一張 csarc-devops Issue 通知回收 runner。這個方向不會增加 VM 的風險，不應被另一方卡住（待決問題 O8）。改成 `local` 仍屬於放寬治理值，照 #1069 走 governance-switch。

**跨 repo 讀取的憑證。**唯讀讀取 csarc-devops Issue 需要一個能讀 private repo 的憑證（限制 3）。建議：由 csarc-devops 建立一個只有 Issues 讀取權限、只安裝在 csarc-devops 的 GitHub App，下游 repo 以 secret 保存其憑證，只在 GitHub-hosted、只執行 trusted base 程式碼的 policy job 使用，永遠不交給 VM 上的 job。另一個選項是只在操作者本機執行的 lifecycle（`pr_lifecycle.py check`／`merge`，使用維護者自己的 `gh` 登入）讀取，hosted gate 只檢查形狀並標為待確認。兩者的取捨列在待決問題 O1。

### D6. Runner 型態與同一台 VM 上的隔離

GitHub 建議 self-hosted 使用 ephemeral（每個 runner 只接一個 job）或 just-in-time runner，並不建議以 persistent runner 做自動擴展（[Self-hosted runners reference：Ephemeral runners、Just-in-time runners](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)）。擁有者要的是「工具鏈與快取常駐」，不是「工作目錄常駐」，兩者可以分開：

| 型態 | 優點 | 風險 |
| --- | --- | --- |
| Persistent runner（一個 runner 程序長期接 job） | 安裝最簡單；工作目錄、工具鏈、快取全部保留 | 前一個 job 的程式碼可以留下檔案、背景程序或改動工具鏈，影響下一個 job，包含別的 PR 的驗證結果；GitHub 指出 persistent runner 被入侵後會持續存在 |
| Ephemeral／JIT runner，VM 本身常駐 | 每個 job 拿到新的 runner 與空的工作目錄；接完一個 job 就註銷 | 需要 csarc-devops 寫一個 supervisor 在每個 job 後重新註冊；同一台硬體仍可能殘留資料，GitHub 提醒要由自動化清理 |
| 每個 job 一台新 VM 或容器 | 隔離最好 | 失去「常駐」的好處，維運成本最高；容器 job 需要 docker 權限，docker group 等同 root |

**建議：VM 常駐、runner ephemeral、工具鏈唯讀常駐、快取依（repo, 環境）分開。**

1. **帳號與目錄。**每個（repo, 環境）一個專用 OS 帳號與 runner 目錄，彼此不可讀寫；runner 帳號不在 `docker`、`sudo` 群組。
2. **工作目錄。**每個 job 從空目錄開始，job 結束後由 supervisor 刪除（ephemeral）。如果 csarc-devops 初期只能提供 persistent runner，最低要求是：每個（repo, 環境）一個 runner、以 runner 的 job started／completed hook 清空工作目錄並結束殘留程序，證據記 `runner-mode=persistent`，讓 merge trace 看得出來；這個降級要擁有者明確接受（待決問題 O4）。
3. **工具鏈。**依語言 profile 預先安裝在 root 擁有的唯讀路徑，版本由 #1271 的工具鏈契約固定。job 不能改動，所以「常駐」不會讓一個 job 汙染下一個 job 的工具鏈。
4. **快取。**依賴快取（uv、pnpm、cargo、Go module 等）放在每個（repo, 環境）自己的目錄，以 lockfile digest 分 key，不跨 repo、不跨環境共用。DEV 執行的是尚未審查完成的 work PR 程式碼，它的快取可能被汙染；PRD 永遠不使用 DEV 或 UAT 的快取。建議 PRD 的快取只在 stable 候選驗證時建立，並可隨時丟棄重建。
5. **Secrets。**VM 上不放長期 secret。`verify` 本來就不帶 secret、只有唯讀 token、`persist-credentials: false`；runner 註冊憑證只由 supervisor 帳號持有。封鎖雲端 metadata endpoint，對外網路依 csarc-devops 政策限制（待決問題 C4）。不要以命令列參數傳遞任何機密，其他 job 可能從程序列表看到（GitHub 同一份說明）。
6. **常駐服務。**`self_hosted_services` 只為驗證服務，預設關閉；每個服務在對應的（repo, 環境）帳號下執行，有資源上限與停止方式（#1271、待決問題 C5）。服務的啟動指令取自 trusted base 的設定，不取自 candidate。
7. **紀錄。**ephemeral runner 的 log 在註銷前轉存到 csarc-devops 的外部儲存，供事件調查。

### D7. 失效、撤銷與降級

原則：**不靜默改回 hosted。**self-hosted 模式下，`ubuntu-latest` 的結果不被接受；無法在登記環境完成驗證時，`verify` 維持未成功，合併被擋下，訊息說明原因與下一步。

| 情況 | 行為 | 下一步（訊息內容） |
| --- | --- | --- |
| Runner 離線、沒有符合 labels 的 runner | job 停在 queued，`verify` 沒有成功結果，合併被擋；GitHub 在 24 小時後讓 job 失敗。route job 的盤點會列出它派出的 labels，方便對照 | 執行 `csarc self-hosted doctor`（#1271，唯讀）確認；請 csarc-devops 恢復 runner 後重跑 `verify` |
| 預期環境未登記 | route job 失敗，不派工 | 依 D5 流程登記該環境 |
| 登記被撤銷（csarc-devops 留言 `/self-hosted revoke`，並移除 runner） | 新 job 無 runner 可接；合併時讀不到有效核准則拒絕，即使已有 24 小時內的證據 | 依 D5 重新登記，或開 PR 退出 self-hosted |
| 核准失效（Issue 本文在核准後被改、被反對） | 視同撤銷 | 依 D5 重新核准 |
| 讀不到 csarc-devops（權限、API 錯誤） | fail closed | 確認憑證（O1）後重跑；不提供略過選項 |
| 證據的 runner、group 或環境不符 | 拒絕 | 在正確環境重跑 `verify` |
| 懷疑 VM 被入侵 | csarc-devops 撤銷該機器所有 runner；以 `merge_trace.py audit` 列出事件期間 `CSARC-Trust: self-hosted-registered` 且 runner 為該機器的合併，逐一重新驗證 | 事件處理依 `docs/security-response.md`；恢復前必須重建 VM |

**VM 長期無法使用時的出口（建議，待決問題 O6）。**trusted base 決定模式，所以「把模式改回 hosted」的 PR 本身仍要求 self-hosted 證據；VM 完全不能用時，這張 PR 會卡住。建議提供一條明確、留下紀錄的出口：只有「把 `verification_mode` 從 `self-hosted` 改成 `hosted`」且只改這些設定的 governance-switch PR，可以由維護者以 `workflow_dispatch` 明確要求一次 GitHub-hosted `verify`；lifecycle 只在這條 route 接受該 hosted 證據，merge trace 記為 `github-hosted` 並註明出口原因。不採用時，唯一出口是 Journey 08 既有的 admin bypass 規則。

### D8. 先盤點、再動作

三個會產生作用的時點都先輸出唯讀盤點，盤點有任何一項不符預期就停止（[dry-run-inventory-before-action](dry-run-inventory-before-action.md)）：

| 時點 | 盤點內容 | 之後的動作 |
| --- | --- | --- |
| 登記與變更（#1270） | 兩張 Issue 的 URL 與雙向連結、核准者與其權限、核准時間、Issue 最後修改時間、登記區塊與設定的逐項差異（舊值→新值） | 全部相符才讓 PR 通過 |
| 派工（#1269） | repo 與可見性、head repo、route、release level、預期環境、要求的 runner labels、已登記環境 | 寫進 step summary 後，VM job 才啟動 |
| 服務啟動（#1271） | 要啟動的服務、環境、啟動與停止指令、健康檢查，以及這些值來自 trusted base 的哪個 commit | 盤點相符才啟動；`doctor` 只盤點、不改動 |

盤點只讀資料：設定以 trusted base 的 `csarc_config.py` 讀取，csarc-devops 的留言視為資料，不執行任何下載來的程式碼。

### D9. Ownership 與驗證

| 項目 | Issue | 驗證 |
| --- | --- | --- |
| 設定、schema、migration、governance-switch | #1268 | 三種模式的 root／template 回歸測試；預設值不改變既有專案 |
| 派工、fork 排除、證據綁定 | #1269 | fork PR、未登記、缺環境、錯誤 runner 的拒絕測試；`check-trusted-verification` 讀回 runner 與環境 |
| 雙方核准 gate | #1270 | 雙方核准通過；缺任一方、單向連結、核准失效、讀取失敗都擋下 |
| 工具鏈契約、`doctor`、常駐服務 | #1271 | 唯讀盤點測試；服務預設不啟動 |
| Dependabot 重新驗證 | #1264 | 依 #1264 AC5 |
| 文件、手冊 r6、下游通知 | #1272 | 文件一致性紀錄 |
| VM、允許清單、runner 註冊 | csarc-devops 對應 Issue | csarc-devops 自己的驗收 |

擁有者核准後，本 ADR 隨 #1266 的 PR 合併並改為 `Accepted`；之後實作與本 ADR 不同的地方，在該實作 PR 修訂本 ADR。

## Payload 影響估計（交給 #1267）

量測基準：`2035b0d`，`uv run python scripts/generated_payload.py`。數字是 canonical bytes 的粗估（±50%），實作時以實測為準。前提是 D1 的 render 規則：self-hosted 專屬程式只在 self-hosted render，既有 fixture 只承擔共用檔案裡的小幅掛鉤。

| Issue | 內容 | 既有 fixture 增量（hosted、consumer-a、consumer-b；solo 視檔案而定） | 影響的分項 | self-hosted render 增量 |
| --- | --- | --- | --- | --- |
| #1268 | `csarc_config.py` 新選項與三個設定的型別檢查；governance-switch 放寬順序加入 `self-hosted` | 每個 fixture（含 solo）+1.5–2.5 KB | settings 與 drift（consumer-a 餘裕 3,188 B）；PR lifecycle | 同左 |
| #1269 | `ci.yml` 的 route job 與 `runs-on`；證據接受 self-hosted runner；新的 `CSARC-Trust` 值 | `ci.yml` 以 Jinja 條件 render，hosted 為 0；共用 script 掛鉤約 +0.3–0.5 KB。**若 runner 判斷直接寫進 `verification_evidence.py` 約 +1–1.5 KB，超過 verification 分項在 hosted 僅剩的 810 B**，因此建議放進 sibling | verification、PR lifecycle | +5–8 KB |
| #1270 | 跨 repo 唯讀讀取、雙向連結、登記區塊比對、核准判斷 | 只有 `validate-pr-policy` 掛鉤約 +0.3 KB | PR lifecycle、Milestone 與 Issue | +4–7 KB |
| #1271 | `doctor`、工具鏈清單、服務設定 | 0 | verification 或新分組 | +3–6 KB（含約 1 KB 資料檔） |
| #1264 | Dependabot 重新驗證與合併放行 | hosted、consumer +5–6 KB（擁有者 2026-10-24 估計） | Dependabot（餘裕約 1,000 B）；若新增有寫入權限的 workflow，hosted 已達 10／10 上限 | 同左 |
| #1272 | 文件 | 若三種模式的說明寫成共用段落，每個 fixture +150–400 token；self-hosted 細節以條件 render 則為 0 | agent 文件 token（hosted 餘裕 540） | +1,000–2,000 token |

合計：hosted fixture 約需 **7.5–10 KB**，目前餘裕 2,828 B，**缺口約 5–7 KB**；另外 verification、Dependabot 兩個分項必須取得空間或修訂上限；若 #1264 需要新的寫入 workflow，攻擊面預算也要修訂。新的 self-hosted fixture 約等於 hosted 加 15–25 KB，需要新增一組 fixture 預算；依 #1231 第 8 點，新增或上調預算都要修訂 [generated-repository-layout](generated-repository-layout.md) 並由擁有者核准。

## 待決問題

**給擁有者：**

| ID | 問題 | 本草稿建議 |
| --- | --- | --- |
| O1 | 跨 repo 唯讀讀取 csarc-devops 用什麼憑證？ | 由 csarc-devops 建立只有 Issues 讀取權限的 GitHub App，憑證只在 GitHub-hosted policy job 使用；替代方案是只在操作者本機的 lifecycle 讀取 |
| O2 | 模板 repo 是 public，是否確認模板 repo 本身維持 `hosted`，只由下游 private repo 實際使用 self-hosted？ | 確認 |
| O3 | Free 方案沒有額外 runner group，是否接受以 repository 層級 runner 達成「只限登記 repo」？或升級 Team？ | 接受 repository 層級 runner |
| O4 | Runner 型態：ephemeral（建議），或在 csarc-devops 還做不到時暫時接受 persistent 加清理 hook？ | ephemeral；persistent 只作為有期限的過渡，證據標示 `runner-mode=persistent` |
| O5 | 只有執行 candidate 的驗證 job 上 VM，policy 與寫入 job 留在 GitHub-hosted（仍用少量 hosted 額度）？ | 是 |
| O6 | VM 長期無法使用時，是否提供 D7 的「改回 hosted」一次性出口？ | 提供，只限該 route |
| O7 | csarc-devops 核准留言用 `/self-hosted …` 語彙，還是逐字沿用 `/milestone approve`？`registration` URL 放在 `self_hosted_runner` 裡，還是另設一個設定？ | `/self-hosted …`；放在 `self_hosted_runner` 裡 |
| O8 | 退出 self-hosted 是否只需要 repo 端核准？ | 是，並通知 csarc-devops 回收 |
| O9 | AC1 要求「ADR 與規格」：是否另開 `docs/specs/SPEC-011`，或由本 ADR 的 D2–D7 兼任規格？ | 規格條文在 #1268 隨 schema 一起寫成 SPEC-011，本 ADR 只保留決定與理由 |
| O10 | #1267 取得空間的方式：瘦身、修訂預算，或兩者並用；新的 self-hosted fixture 預算 | 由 #1267 依上表提出數字後決定 |
| O11 | release 發布 job 留在 GitHub-hosted，發布前的重新驗證在 PRD；是否接受 release 證據的信任值為 `self-hosted-registered`？ | 接受，release notes 標示信任值 |
| O12 | Dependabot PR 的環境 | 物化 stable 時 `prd`，否則 `dev` |

**給 csarc-devops（需另開對方 Issue，雙方連結）：**

| ID | 問題 |
| --- | --- |
| C1 | 能否提供 ephemeral／JIT runner supervisor？時程？做不到時 persistent 過渡期多長？ |
| C2 | runner label 與 `runner_name` 命名規則（建議 `csarc-<vm-id>`、`csarc-env-<env>`，`runner_name` 以 `<vm-id>-` 開頭），以及機器 ID 是否穩定、可重查 |
| C3 | 允許清單的檔案格式、核准者名單與權限、`/self-hosted revoke` 的處理時限與通知方式 |
| C4 | 每個（repo, 環境）的帳號、目錄與快取配置；PRD 快取的建立與丟棄；對外網路與 metadata endpoint 政策 |
| C5 | 常駐服務的資源上限、停止與清理方式 |
| C6 | runner log 的轉存位置與保存期限；入侵事件時的撤銷與重建程序 |
| C7 | O1 的 GitHub App 由誰建立與維護、憑證輪替方式 |

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 維持 hosted，改用 GitHub larger runner 或快取 | 不採用；仍耗用 GitHub 額度，也沒有常駐環境（擁有者決定 2） |
| VM 自己跑測試再回報結果（不經 GitHub 派工） | 不採用；結果由 VM 自行聲明，信任等級與 `local` 相同 |
| 組織層級 runner 放在 default group，只用 label 區分 repo | 不採用；Free 方案下組織內每個 private repo 都能派工上去，label 不是存取控制 |
| 一個 persistent runner 同時服務 DEV、UAT、PRD | 不採用；DEV 的 work PR 程式碼可以汙染 PRD 驗證用的快取與工具鏈 |
| VM 不可用時自動改派到 GitHub-hosted | 不採用；擁有者要求不靜默改回 hosted，而且會讓模式的證據意義混在一起 |
| fork PR 經維護者核准後可以上 VM | 不採用；擁有者決定 6 與 GitHub 的建議都排除 fork |
| 模板讀 csarc-devops 的允許清單檔，而不是核准留言 | 不採用；擁有者決定讀核准留言，且讀檔一樣需要跨 repo 憑證 |
| 每個 job 一台新 VM 或容器 | 暫不採用；失去常駐的好處，容器需要 docker 權限；隔離需求提高時重新評估 |
| self-hosted 程式碼直接加進共用 script | 不採用；hosted fixture 與 verification 分項已沒有空間，且會讓 `local`、`hosted` 專案承擔用不到的程式 |

## 重新評估條件

- 組織升級到 Team 或 Enterprise：改用只開放選定 repo 的 runner group，取代或補強 repository 層級 runner。
- csarc-devops 能提供每個 job 一台新 VM 或 Kubernetes（ARC）：重新評估 D6，可能提高信任等級。
- 模板 repo 改成 private，或有團隊以外的貢獻者需要使用 self-hosted：重新檢查限制 1 與 D4。
- 發生 VM 入侵或快取汙染事件：檢討 D6，並評估是否暫停 self-hosted 證據用於 stable。
- GitHub 改變 self-hosted runner、`pull_request_target` 或 Jobs API 回傳的 runner 欄位。
- #1267 無法取得足夠空間：重新評估哪些能力先做、哪些延後。
