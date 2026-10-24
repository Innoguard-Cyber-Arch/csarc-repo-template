# Self-hosted verification mode ADR

- **狀態：**Proposed
- **日期：**2026-10-24
- **來源 Issues：**[#1266](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1266)、[#1265](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1265)（Milestone 21 tracker，擁有者 2026-10-24 決定）
- **實作 PR：**待擁有者核准本草稿後，由 #1266 的 PR 填入

## 問題與限制

目前只有兩種驗證模式。`local` 在開發者電腦上執行，結果只能自我證明（`self-attested-local`）；`hosted` 在 GitHub-hosted `ubuntu-latest` 執行，結果可信，但耗用 GitHub 運算額度，每次都從零建立環境。擁有者 2026-10-24 在 #1265 決定新增第三種 `verification_mode: self-hosted`：在 csarc-devops 提供的團隊 VM 上執行 GitHub 官方 self-hosted runner，由 GitHub 派工；只開放給登記的 repo，外部 fork 的 PR 一律不在 VM 執行；登記要由兩邊 Issue 互相連結、雙方核准。

擁有者同日審閱第一版草稿後修正了範圍（本版依此改寫）：

1. **不設常駐 runner，也不設常駐環境。**repo 管理員需要時以模板指令「開窗」：指令先輸出唯讀盤點，再以管理員**自己的**憑證取得這個 repo 的 runner 註冊 token 交給 VM；VM 檢查允許清單後讓 runner 上線 24 小時，時間到即停止並移除。開窗不另走核准流程，取得 token 本身就是授權動作；要繼續使用就再開一次。除了固定的 24 小時之外不另設上限。
2. **csarc-devops 只管 VM（載具），對下游 repo 沒有任何權限。**csarc-devops 可以使用只讀取自己 repo Issue 的憑證，處理一次性的雙邊登記核准。
3. **只有 DEV 與 UAT 兩個環境。**DEV＝Issue → Milestone（進 `dev/mN` 的 work PR）；UAT＝Milestone、standalone、hotfix → main（promotion、standalone、hotfix PR，也就是物化 stable 版本的地方）。不設 PRD 驗證環境：release 發布只發布已驗證的候選。
4. **窗外一律 fail closed。**self-hosted 模式的 repo 在沒有開窗時，required verification 失敗並提示開新窗，不改在 GitHub-hosted 執行。
5. **只有驗證 job 上 VM，**帶唯讀 job token、不帶 secret；持有寫入 token 的 job 留在 GitHub-hosted。
6. **模板 repo 本身維持 `hosted`；只用 repository 層級的 runner。**
7. **列為未來研究、不在本 Milestone：**release 後的部署驗收環境，以及常駐的產品測試服務。

撰寫本草稿時已查證的限制（2026-10-24，base `2035b0d`）：

1. **模板 repo 是 public。**GitHub 的說明是 self-hosted runner「幾乎不應該」用在 public repo，因為任何人都能開 PR 在機器上執行程式碼（[Security hardening：Hardening for self-hosted runners](https://docs.github.com/en/actions/reference/security/secure-use#hardening-for-self-hosted-runners)）。所以模板 repo 維持 `hosted`，self-hosted 只給已登記的 private 下游 repo，模板以測試與一個實際登記的下游 repo 驗證（#1265 AC1）。
2. **組織是 GitHub Free 方案。**只有 default runner group，建立其他 group 需要 Team 方案；default group 預設只讓 private repo 使用（[Managing access to self-hosted runners using groups](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access)）。組織層級 runner 放在 default group，組織內每個 private repo 都能用 label 派工上去；label 只是路由，不是存取控制。repository 層級 runner 只會收到該 repo 的 job。
3. **註冊 token 只能由 repo 管理員取得，一小時內有效。**`POST /repos/{owner}/{repo}/actions/runners/registration-token` 要求呼叫者對 repo 有 admin 權限，token 一小時後失效（[REST：Create a registration token for a repository](https://docs.github.com/en/rest/actions/self-hosted-runners#create-a-registration-token-for-a-repository)）。移除 repository runner 也需要管理員；離線超過 14 天的 runner 會被 GitHub 自動移除（[Removing self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/remove-runners)）。
4. **csarc-devops 是 private repo。**下游 workflow 的 `GITHUB_TOKEN` 讀不到它的 Issue，登記核准的唯讀讀取需要一個只讀 csarc-devops Issue 的憑證。AGENTS.md 不允許把 personal token 當成 portable baseline。
5. **現有證據只接受 GitHub-hosted runner。**`scripts/verification_evidence.py` 要求 job labels 含 `ubuntu-latest`、`runner_group_name` 等於 `GitHub Actions`，含 `self-hosted` label 一律拒絕；merge trace 的 `CSARC-Trust` 只有 `github-hosted` 與 `self-attested-local`（`scripts/merge_trace.py`）。
6. **hosted 專屬的 payload 全以 `verification_mode == 'hosted'` 決定是否 render**（`copier.yml` 的 `_exclude`，約 30 個條件）。self-hosted 需要同一組 workflow 與 script。`csarc` CLI 是獨立的 Python 套件（`src/csarc_cli`），不在生成專案的 payload 裡。
7. **trusted executor 不是 sandbox。**[trusted-base-gate](trusted-base-gate.md) 已寫明它防的是 candidate 改 gate 讓自己通過；candidate 的測試碼仍在同一台機器執行。GitHub-hosted VM 用完即丟；同一個 runner 連續接多個 job 時，前一個 job 可以留下影響後一個 job 的狀態（GitHub 同一份 hardening 說明）。
8. **`verify` 由 `pull_request_target` 載入 base 的 workflow，但會 checkout 並執行 candidate 的測試。**任何觸發 `verify` 的 PR，包含 fork PR，都會把 candidate 程式碼帶到執行機器上。不能依賴 repo 的 fork PR 核准設定（[Managing GitHub Actions settings：fork pull request workflows in private repositories](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#controlling-changes-from-forks-to-workflows-in-private-repositories)），排除必須寫在 workflow 與 lifecycle 裡。
9. **payload 餘裕很小。**`scripts/generated_payload.py` 在 `2035b0d` 實測：hosted fixture 距總閘 2,828 B；verification 分項在 hosted 只剩 810 B，Dependabot 分項約 1,000 B；agent 文件 token 在 hosted 剩 540；hosted 具寫入權限的 workflow 已達上限 10／10。#1231 規定預算只能下調，上調要修訂 ADR 並由擁有者核准。
10. **[先盤點、再動作](dry-run-inventory-before-action.md) 適用。**登記、開窗、派工都會讓設定或程式碼產生作用，必須先輸出唯讀盤點。

不在本 ADR 範圍：VM 的建置與維運、csarc-devops 允許清單本身的實作、產品部署管線（CD）、修改下游 repo 設定，以及上述第 7 點的未來研究。

## 決定

以下 D1–D9 是提交擁有者核准的設計。標示「建議」的項目有替代做法，列在「待決問題」。

### D1. 定位：hosted 的控制加上換一台執行機器

`self-hosted` 是 `hosted` 的變體，不是新的一套流程：

- required checks（`title`、`verify`、`review`）、Ruleset、GitHub Actions App integration ID 綁定（#835）、trusted executor（#1086、#1069）、exact-head 授權、remote lease、24 小時證據期限（[verification-evidence-freshness](verification-evidence-freshness.md)）與 merge trace（#1073）全部沿用，不放寬任何一項。
- 差別只有三處：執行 candidate 程式碼的驗證 job 改派到窗口內的登記 runner（`runs-on`）；證據多綁定 runner、環境與窗口；merge trace 使用新的信任值。
- **只有驗證 job 上 VM：**`verify`、#1264 的 Dependabot 重新驗證。這些 job 只拿唯讀 job token、不帶 secret、`persist-credentials: false`。PR policy、review、lifecycle 寫入、release 發布與 Pages 等持有寫入 token 或 secret 的 job 留在 GitHub-hosted；它們很短，仍會用到少量 hosted 額度。
- render 規則：所有以 `verification_mode == 'hosted'` render 的檔案，在 `self-hosted` 也 render；self-hosted 專屬的程式放在只有 `self-hosted` 才 render 的 sibling（沿用 #1177 hosted sibling 的做法）；開窗、延長、關窗與狀態查詢放在 `csarc` CLI（D5）。既有 `local`、`hosted` 專案的 payload 與行為不變。

### D2. 信任模型

| 項目 | `local` | `hosted` | `self-hosted` |
| --- | --- | --- | --- |
| 誰派工 | 操作者自己執行 | GitHub | GitHub |
| 在哪執行 | 操作者電腦 | GitHub-hosted VM，每個 job 全新 | csarc-devops VM 上、由 repo 管理員開窗註冊的 repository runner；每次開窗或延長後最多 24 小時，期間可接多個 job |
| workflow 與 gate 來源 | trusted base（#1069） | trusted base（`pull_request_target`、#1086） | 同 hosted |
| 結果由誰記錄 | 操作者寫入 Git metadata | GitHub Check Runs、Jobs API | 同 hosted；runner 名稱、labels、group 由 GitHub Jobs API 記錄，不由 VM 自行回報 |
| 能證明 | 某人聲稱在 exact head 跑過指定 tier | GitHub 在乾淨 VM 上以 base 的 workflow 對 exact tree 執行指定 command 並成功 | GitHub 把 base 的 workflow 派給這個 repo 在有效窗口內註冊的 runner，在預期環境對 exact tree 執行指定 command 並成功 |
| 不能證明 | 結果未被偽造；環境；GitHub 事件與權限 | candidate 測試碼本身無惡意（不是 sandbox） | 同 hosted；另外不能證明同一窗口內先前的 job 沒有留下影響、VM 的工具鏈未被改動，也不能排除 VM 管理者竄改執行環境 |
| 信任前提 | 操作者 | GitHub | GitHub＋開窗的 repo 管理員＋csarc-devops 的隔離契約（D6）＋一次性雙邊登記（D5） |
| `CSARC-Trust` | `self-attested-local` | `github-hosted` | `self-hosted-registered`（新值） |

結論：`self-hosted` 比 `local` 強，因為結果由 GitHub 記錄，操作者無法只靠寫一份 JSON 產生證據；比 `hosted` 弱，因為同一窗口內的 job 共用機器狀態，信任延伸到開窗者與 csarc-devops。窗口制讓這個「跨 job 共用」只在管理員明確開窗或延長的期間內存在（每次最多 24 小時），而且只在同一個 repo、同一個環境內；這比常駐 runner 的暴露面小得多。merge trace 用獨立的信任值，事後可以用 `merge_trace.py audit` 列出所有依賴 VM 的合併（D7 的事件處理需要它）。

**證據綁定。**hosted 證據的既有欄位（repository、exact head／tree、base、tier、scopes、command、toolchain、label set、release level、結果、完成時間）全部保留，`verify` 在 self-hosted 模式另外必須符合：

1. job 的 `labels` 含 `self-hosted`、登記的 runner label，以及**由 trusted base router 計算出的預期環境** label（D3）。`ubuntu-latest` 證據在 self-hosted 模式不被接受（D7）。
2. `runner_name` 符合窗口的命名規則（例如 `<vm-id>-<env>-<開窗時間>`），`runner_group_name` 為 `Default`；這些值來自 Jobs API。
3. execution step 名稱加上 `environment=<dev|uat>` 與 `window=<開窗時間>`，必須與 job labels、runner 名稱、router 的預期環境一致；任何一項不符即拒絕，訊息要求在正確環境重跑。
4. 證據 payload 與 canonical merge evidence 多記 `runner`、`environment`、`window`，`check-trusted-verification` 可以重查並顯示（#1265 AC1）。
5. 期限仍是 24 小時，從 job 完成時間起算。窗口結束不會讓窗口內完成的證據失效；登記被撤銷才會（D7）。

### D3. 環境對應：DEV 與 UAT，依目標分支決定

環境由 trusted base 的 router 依 PR 的目標分支決定，candidate 不能自選：

| 目標分支 | 典型 PR | 環境 |
| --- | --- | --- |
| `dev/m*`、`dev/i*` | Milestone 的 work PR、main→delivery 同步、checkpoint terminal（物化 beta） | `dev` |
| `main` | promotion、standalone、hotfix、release-recovery、`release/v*` guided candidate（物化 stable）；Dependabot PR | `uat` |

- merge queue 依同一規則：`dev/m*` 的 queue 用 `dev`，`main` 的 queue 用 `uat`。
- 環境與 tier（fast／full）互相獨立：tier 仍由 `ci_tier.py` 與 channel floor 決定。
- 預期環境不在 `self_hosted_environments` 裡、或該環境沒有有效窗口時 fail closed，不改用另一個環境，也不改用 hosted。
- **不設 PRD。**`release.yml` 只發布已驗證的候選：它照現行規則重用來源 PR 的證據（tree 相同且在期限內）。現行 hosted 模式在無法重用時會對 main tree 重跑 hosted full；self-hosted 模式改為 fail closed，訊息要求開 UAT 窗口後重新執行 release workflow。
- 不使用 Milestone 的 repo 可以只登記 `uat`；使用 Milestone 的 repo 需要兩個環境。

### D4. 只限登記 repo、排除 fork：五層防護

任何一層單獨失效，其他層仍然擋得住。

| 層 | 誰負責 | 控制 |
| --- | --- | --- |
| L1 GitHub 註冊 | repo 管理員（開窗） | 只用 repository 層級 runner：註冊 token 由該 repo 的管理員以自己的憑證取得，GitHub 只把該 repo 的 job 派給它（限制 2、3）。未登記的 repo 拿不到 VM 的配合，登記的 repo 沒開窗就沒有 runner。只接受 private repo。 |
| L2 workflow 派工條件 | 模板（#1269） | 派工前，一個不執行 candidate 程式碼的 GitHub-hosted route job 計算：PR head repo 是否等於本 repo、repo 是否為 private、目標分支與預期環境、設定是否完整、該環境的窗口是否有效（D5 的窗口紀錄）。任一項不成立，VM job 不啟動，`verify` 由 route job 回報失敗並說明原因；fork PR 永遠走這條路。`runs-on` 的 labels 由 route job 輸出，candidate 無法改變。 |
| L3 trusted base 設定 | 模板（#1268、#1069） | `verification_mode`、`self_hosted_*` 一律從 trusted base 讀取。PR 把模式改成 self-hosted 或改動登記設定時，新設定要等合併後才生效，這張 PR 本身仍依 base 的模式驗證。 |
| L4 lifecycle | 模板（#1269、#1270） | 合併時重新檢查證據：head repo 必須等於 base repo；runner、group、環境、窗口必須符合登記與命名；不符即拒絕。 |
| L5 VM | csarc-devops | 收到註冊 token 時核對允許清單（repo、環境）；不符就不註冊。每個（repo, 環境）獨立的 OS 帳號與目錄（D6）。 |

外部 fork 的 PR：L2 不派工，L4 拒絕其證據。需要接受外部貢獻時，由維護者把變更搬到本 repo 的分支重新開 PR。

### D5. 登記契約與開窗

**一次性登記（雙邊核准）。**登記決定「這個 repo 可以使用哪台 VM 的哪些環境」，之後每次開窗都不再核准。

Repo 端設定（`.csarc/config.yml`，#1268 實作 schema）：

| 設定 | 型別與預設 | 意義 |
| --- | --- | --- |
| `verification_mode` | 新增選項 `self-hosted`；預設不變（新專案 `local`） | 選用本模式 |
| `self_hosted_runner` | mapping，必填：`id`（登記的 VM ID，例如 `csarc-vm-01`）、`registration`（csarc-devops 登記 Issue 的完整 URL） | 指向哪台 VM，以及哪一張 csarc-devops Issue 承載核准；`id` 用來推導 runner label 與命名，確切命名由 csarc-devops 定案（C2） |
| `self_hosted_environments` | `dev`、`uat` 的非空子集合 | 這個 repo 登記了哪些環境 |
| `self_hosted_services` | **建議本 Milestone 不加入**（待決問題 O3） | 常駐產品測試服務已列為未來研究 |

csarc-devops 端維護允許清單，每筆至少記錄：repo 全名、VM `id`、環境、csarc-devops Issue、repo 端 Issue、核准時間。格式由 csarc-devops 的 Milestone 負責；模板不讀這份清單。

登記變更（開始使用、增減環境、更換 VM、撤銷）的流程：

1. Repo 端（模板或下游）與 csarc-devops 各開一張 Issue，兩張互相引用完整 URL（雙向連結）。
2. csarc-devops Issue 本文含一個固定格式的登記區塊，內容等於 repo 全名與變更後的 `self_hosted_*` 設定。
3. 兩邊各自核准。Repo 端沿用既有核准（Milestone tracker 或無 Milestone Issue 的核准）。csarc-devops 端的核准留言格式與 Milestone 核准相同；建議語彙 `/self-hosted approve`、`/self-hosted admin-approve: <理由>`、`/self-hosted object: <理由>`、`/self-hosted resolve: <目標>`，另加 `/self-hosted revoke: <理由>`（O2）。判斷演算法與 Milestone 核准相同：以 collaborator permission API 判斷核准者權限；最新的有效留言決定狀態；核准後 Issue 本文被修改，核准即失效。
4. 改動設定的 PR 帶 `governance-switch` label（#1069 既有 route）。#1270 的 gate 以唯讀 API 讀取 csarc-devops Issue 的本文與留言，確認雙向連結、登記區塊與 PR 的新設定逐字相符、核准有效。讀取失敗、缺少任一方核准、只有單向連結、核准失效或被反對、內容不符，都 fail closed，訊息說明原因並給下一步。
5. 讀取憑證：csarc-devops 提供一個**只讀取 csarc-devops 自己 Issue** 的 GitHub App（或同等憑證），下游以 secret 保存，只在 GitHub-hosted、只執行 trusted base 程式碼的 policy job 使用，永遠不交給 VM 上的 job。它對下游 repo 沒有任何權限。
6. 合併後 csarc-devops 依核准更新允許清單。

**建議：退出 self-hosted（改回 `hosted` 或 `local`、移除環境）只需要 repo 端核准**，並通知 csarc-devops 更新允許清單（O4）。改成 `local` 仍屬放寬治理值，照 #1069 走 governance-switch。

**開窗（每次使用，不另核准）。**repo 管理員執行 `csarc self-hosted open --env dev|uat`（#1271 實作，位於 `csarc` CLI）：

1. 唯讀盤點並印出：repo 與可見性、設定中的 VM 與環境、窗口長度（固定 24 小時）與結束時間、窗口內會執行什麼（只有 `verify` 類 job、唯讀 token、不帶 secret）、目前是否已有同環境的窗口與 runner。任一項不符就停止。
2. 以管理員自己的 `gh` 登入呼叫 registration-token API。管理員的 GitHub 憑證不離開本機、不寫入任何檔案；交給 VM 的只有這個一小時內有效的註冊 token。
3. 經 csarc-devops 指定的管道把 token、repo、環境交給 VM（管道由 csarc-devops 定案，C1）。VM 核對允許清單，以固定命名與 labels 註冊**一個**runner，24 小時後停止 runner，並刪除本機的 runner 憑證檔，使它不能再連線。
4. 指令讀回 runner 清單，確認這個 repo 只有一個符合命名的線上 runner；出現預期之外的 runner 時，移除全部並以錯誤結束（防止註冊 token 外洩後被用來註冊其他機器）。
5. 寫入窗口紀錄（見下方「窗口紀錄」），讓 route job 與驗證 job 能判斷窗口是否有效、還剩多久。

`csarc self-hosted close --env dev|uat` 以管理員憑證刪除該 runner 並清除窗口紀錄；不執行時，VM 到期停止 runner，離線 runner 不會再收到 job，GitHub 也會在離線 14 天後自動移除。

**窗口紀錄（最小權限）。**窗口的開始與結束時間記在兩處：

- **VM 端**：VM 依自己的紀錄在結束時間停止 runner，這是窗口真正結束的依據。
- **Repo 端**：repository variable `CSARC_SELF_HOSTED_WINDOW_<ENV>`，內容為 runner 名稱、開始時間、結束時間（UTC）。建議用它，因為 workflow 以 `vars` context 讀取 variable 不需要任何額外 job 權限，route job 與驗證 job 都能直接讀到；寫入只發生在管理員以自己的憑證開窗、延長或關窗時（寫入 variable 需要的權限在 #1271 實作時確認，O5）。替代方案是 commit 一個紀錄檔或在 Issue 留言，前者每次開窗都要一個 commit，後者需要額外的 Issue 讀取與格式判讀，都不比 variable 精簡。
- 窗口紀錄只用來讓窗外立即 fail closed 與提醒延長，**不是信任依據**；證據仍以 Jobs API 的 runner 資料為準。紀錄與 VM 不一致時（例如 VM 提早停止），以「runner 是否實際接到 job」為準，見 D7。

**剩餘時間與延長。**

- `csarc self-hosted status [--env dev|uat]`：唯讀顯示每個環境的 runner、開始與結束時間、剩餘時間、窗口紀錄與 VM 回報是否一致，以及工具鏈版本；呼叫者是管理員時另外顯示 runner 是否在線。它取代第一版的 `doctor`。
- **最後 2 小時提醒。**驗證 job 的 trusted step 讀窗口紀錄；剩餘時間少於 2 小時時，在輸出與 job summary 各印一行 `WARNING:`，句型依寫作指引，例如 `WARNING: The dev self-hosted window ends at 2026-10-25T09:00Z (1h40m left). Run 'csarc self-hosted extend --env dev' to keep verifying.`。提醒不改變 job 結果。2 小時的理由：fast 與 full 驗證都在 job timeout 30 分鐘內，2 小時讓管理員在下一輪 review 前有時間處理，又不會讓一天內大部分 job 都在提醒。
- **不在窗口尾端開始新 job。**剩餘時間少於 job timeout（30 分鐘）時，route job 不派工並以失敗結束，訊息要求先延長，避免 job 執行到一半被停止。
- **延長**：`csarc self-hosted extend --env dev|uat`；窗口仍有效時重新執行 `open` 等同 `extend`。指令先印出盤點（目前 runner、舊結束時間、新結束時間），再以管理員自己的憑證讀回 runner 清單，確認同一個 runner 在線，接著更新窗口紀錄，並經開窗時的同一管道（C1）要求 VM 把停止時間改為「現在＋24 小時」。不取得新的註冊 token、不註冊第二個 runner，所以沒有空窗。新的結束時間一律從延長當下起算 24 小時，不累加。窗口已過期時不能延長，只能重新 `open`，會註冊新的 runner。
- VM 只接受來自開窗管道、且 repo 與環境在允許清單內的延長要求；延長同樣不需要另外核准。

**為何 csarc-devops 不持有下游權限。**第一版草稿曾考慮讓 csarc-devops 以 GitHub App 替下游取得註冊 token。repository runner 的管理需要 Administration 寫入權限，而這個權限同時能改 Ruleset 與 branch protection、管理 collaborator、修改 Actions 設定，甚至刪除 repo（[Permissions required for GitHub Apps](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps)）。把它交給管理 VM 的團隊，等於讓載具可以關掉下游的全部治理。改由下游管理員每次以自己的憑證開窗，csarc-devops 只需要讀自己 repo Issue 的權限。

**24 小時固定窗口、不設次數上限的取捨。**窗口長度與證據期限一致，管理員一天開一次就能涵蓋一個工作日的 review 與合併；到期自動結束，忘了關窗也不會變成常駐。不設次數上限代表 repo 可以每天延長或重開、實際上接近常駐，而延長沿用同一個 runner，同一窗口內的 job 共用機器狀態的時間也會跟著拉長；擁有者接受這一點，因為每次延長或重開都是管理員明確的動作，並留在窗口紀錄裡。若觀察到某個 repo 長期連續開窗，依「重新評估條件」檢討。

### D6. 窗口內的 runner 與同一台 VM 上的隔離

一個窗口是一個非 ephemeral 的 repository runner，最多存活 24 小時、可以連續接多個 job。GitHub 建議 ephemeral 或 just-in-time runner（[Self-hosted runners reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)），但 ephemeral runner 每接一個 job 就要一個新的註冊 token，而 token 只能由管理員取得、一小時內有效；VM 不持有下游權限，做不到每個 job 重新註冊。窗口制是在「不給 VM 權限」與「不常駐」之間的取捨，殘留風險只在同一 repo、同一環境、同一天內。為了把它壓低：

1. **帳號與目錄。**每個（repo, 環境）一個專用 OS 帳號與 runner 目錄，彼此不可讀寫；runner 帳號不在 `docker`、`sudo` 群組。
2. **每個 job 的清理。**以 runner 的 job started／completed hook 清空工作目錄、結束殘留程序；窗口結束時整個 runner 目錄與 runner 憑證檔一併刪除。
3. **工具鏈。**依語言 profile 預先安裝在 root 擁有的唯讀路徑，版本由 #1271 的工具鏈契約固定。job 不能改動它，所以 VM 長期存在不會讓一個 job 汙染之後的工具鏈。
4. **快取。**依賴快取放在每個（repo, 環境）自己的目錄，以 lockfile digest 分 key，不跨 repo、不跨環境共用。DEV 執行的是尚未審查完成的 work PR 程式碼；UAT 不使用 DEV 的快取。建議 UAT 的快取在窗口結束時刪除，DEV 的快取可以跨窗口保留（C3）。
5. **Secrets。**VM 上不放長期 secret；驗證 job 不帶 secret、只有唯讀 job token。註冊 token 只在註冊時使用，之後不保存。封鎖雲端 metadata endpoint，對外網路依 csarc-devops 政策限制（C3）。不要以命令列參數傳遞任何機密，其他 job 可能從程序列表看到（GitHub hardening 說明）。
6. **紀錄。**runner log 在窗口結束、刪除目錄前轉存到 csarc-devops 的外部儲存，供事件調查（C4）。

### D7. 失效、撤銷與降級

原則：**不改在 GitHub-hosted 執行。**self-hosted 模式下，`ubuntu-latest` 的結果不被接受；無法在登記環境的有效窗口內完成驗證時，`verify` 失敗，合併被擋下，訊息說明原因與下一步。

| 情況 | 行為 | 下一步（訊息內容） |
| --- | --- | --- |
| 沒有開窗或窗口已過期 | route job 依窗口紀錄判斷，`verify` 立即失敗，不派工 | 請 repo 管理員執行 `csarc self-hosted open --env <環境>`，再重跑 `verify` |
| 窗口剩不到 2 小時 | 驗證照常執行，輸出與 job summary 印出 `WARNING:` | 執行 `csarc self-hosted extend --env <環境>` |
| 窗口剩不到 30 分鐘 | route job 不派工，`verify` 失敗 | 延長窗口後重跑 `verify` |
| 窗口紀錄有效，但 runner 離線（VM 故障、提早停止） | job 停在 queued，`verify` 沒有成功結果，合併被擋；GitHub 在 24 小時後讓 job 失敗 | 執行 `csarc self-hosted status`；請 csarc-devops 恢復 VM，或關窗後重新開窗 |
| 窗口在 job 執行中到期 | runner 停止，job 失敗 | 重新開窗後重跑 `verify` |
| 預期環境未登記 | route job 失敗，不派工 | 依 D5 登記該環境 |
| VM 拒絕註冊（不在允許清單） | `open` 指令以錯誤結束，不寫窗口紀錄 | 確認登記已合併，並請 csarc-devops 更新允許清單 |
| 出現預期之外的 runner | `open` 指令移除這個 repo 的全部 self-hosted runner 並以錯誤結束 | 視為註冊 token 外洩，通知 csarc-devops 並檢查 repo 稽核紀錄 |
| 登記被撤銷或核准失效 | VM 不再接受開窗；#1270 的登記 gate 失敗；合併時讀到撤銷則拒絕，即使已有 24 小時內的證據（O1） | 依 D5 重新登記，或開 PR 退出 self-hosted |
| 讀不到 csarc-devops | 需要讀取的步驟 fail closed | 確認唯讀憑證後重跑；不提供略過選項 |
| 證據的 runner、group、環境或窗口不符 | 拒絕 | 在正確環境的有效窗口內重跑 `verify` |
| release 無法重用來源證據 | `release.yml` fail closed | 開 UAT 窗口後重新執行 release workflow |
| 懷疑 VM 被入侵 | csarc-devops 停止該 VM 上所有 runner；各 repo 管理員以 `close` 移除；以 `merge_trace.py audit` 列出事件期間 `CSARC-Trust: self-hosted-registered` 且 runner 屬於該 VM 的合併，逐一重新驗證 | 依 `docs/security-response.md` 處理；恢復前必須重建 VM |

**VM 長期無法使用時的出口。**trusted base 決定模式，所以「把模式改回 hosted」的 PR 本身仍要求 self-hosted 證據；VM 完全不能用時這張 PR 會卡住。建議只為「把 `verification_mode` 從 `self-hosted` 改成 `hosted`、且只改這些設定」的 governance-switch PR 提供一次明確的 GitHub-hosted `verify`（維護者以 `workflow_dispatch` 要求），lifecycle 只在這條 route 接受該 hosted 證據，merge trace 記為 `github-hosted` 並註明原因。不採用時，唯一出口是 Journey 08 既有的 admin bypass 規則（O6）。

### D8. 先盤點、再動作

五個會產生作用的時點都先輸出唯讀盤點，有任何一項不符預期就停止（[dry-run-inventory-before-action](dry-run-inventory-before-action.md)）：

| 時點 | 盤點內容 | 之後的動作 |
| --- | --- | --- |
| 登記與變更（#1270） | 兩張 Issue 的 URL 與雙向連結、核准者與其權限、核准時間、Issue 最後修改時間、登記區塊與設定的逐項差異（舊值→新值） | 全部相符才讓 PR 通過 |
| 開窗（#1271） | repo 與可見性、VM、環境、窗口結束時間、窗口內會執行的 job 類型與權限、既有窗口與 runner | 印出後才取得註冊 token |
| 派工（#1269） | repo 與可見性、head repo、目標分支、預期環境、窗口紀錄、要求的 runner labels | 寫進 step summary 後，VM job 才啟動 |
| 延長（#1271） | 目前 runner 與是否在線、舊結束時間、新結束時間 | 印出後才更新紀錄與 VM 停止時間 |
| 關窗（#1271） | 要移除的 runner 與窗口紀錄 | 印出後才刪除 |

盤點只讀資料：設定以 trusted base 的 `csarc_config.py` 讀取，csarc-devops 的留言視為資料，不執行任何下載來的程式碼。

### D9. Ownership 與驗證

| 項目 | Issue | 驗證 |
| --- | --- | --- |
| 設定、schema、migration、governance-switch | #1268 | 三種模式的 root／template 回歸測試；預設值不改變既有專案 |
| 派工、窗口判斷、fork 排除、證據綁定 | #1269 | fork PR、未登記、缺環境、窗外、錯誤 runner 的拒絕測試；`check-trusted-verification` 讀回 runner、環境與窗口 |
| 雙方核准 gate | #1270 | 雙方核准通過；缺任一方、單向連結、核准失效、讀取失敗都擋下 |
| `open`、`extend`、`close`、`status`、工具鏈契約（原「常駐服務」範圍改為窗口指令，O3） | #1271 | 盤點與失敗路徑的 CLI 測試；延長不註冊第二個 runner；不寫入管理員憑證的測試 |
| 最後 2 小時提醒、30 分鐘內不派工 | #1269 | 以固定時間測試提醒與拒絕派工的邊界 |
| Dependabot 重新驗證 | #1264 | 依 #1264 AC5；self-hosted 模式在 UAT 窗口執行 |
| 文件、手冊 r6、下游通知 | #1272 | 文件一致性紀錄 |
| VM、允許清單、token 交付管道 | csarc-devops 對應 Issue | csarc-devops 自己的驗收 |

擁有者核准後，本 ADR 隨 #1266 的 PR 合併並改為 `Accepted`；之後實作與本 ADR 不同的地方，在該實作 PR 修訂本 ADR。

## Payload 影響估計（交給 #1267）

量測基準：`2035b0d`，`uv run python scripts/generated_payload.py`。數字是 canonical bytes 的粗估（±50%），實作時以實測為準。前提是 D1 的 render 規則：self-hosted 專屬程式只在 self-hosted render；開窗、延長、關窗與 `status` 在 `csarc` CLI，不進生成專案。與第一版相比，取消常駐服務、PRD 與常駐 runner 後，生成專案的增量變小。

| Issue | 內容 | 既有 fixture 增量（hosted、consumer-a、consumer-b；solo 視檔案而定） | 影響的分項 | self-hosted render 增量 |
| --- | --- | --- | --- | --- |
| #1268 | `csarc_config.py` 新選項與兩個設定的型別檢查；governance-switch 放寬順序加入 `self-hosted` | 每個 fixture（含 solo）+1.0–1.8 KB | settings 與 drift（consumer-a 餘裕 3,188 B）；PR lifecycle | 同左 |
| #1269 | `ci.yml` 的 route job、窗口判斷、到期提醒與 `runs-on`；證據接受窗口 runner；新的 `CSARC-Trust` 值 | `ci.yml` 以 Jinja 條件 render，hosted 為 0；共用 script 掛鉤約 +0.3–0.5 KB。**runner 判斷若直接寫進 `verification_evidence.py` 約 +1 KB，超過 verification 分項在 hosted 僅剩的 810 B**，因此放進 sibling | verification、PR lifecycle | +3–5 KB |
| #1270 | 跨 repo 唯讀讀取、雙向連結、登記區塊比對、核准判斷 | 只有 `validate-pr-policy` 掛鉤約 +0.3 KB | PR lifecycle、Milestone 與 Issue | +3–5 KB |
| #1271 | `open`、`extend`、`close`、`status`、工具鏈清單 | 0（在 `csarc` CLI） | 無（CLI 不在 #1231 的生成專案預算內） | 0 |
| #1264 | Dependabot 重新驗證與合併放行 | hosted、consumer +5–6 KB（擁有者 2026-10-24 估計） | Dependabot（餘裕約 1,000 B）；若新增有寫入權限的 workflow，hosted 已達 10／10 上限 | 同左 |
| #1272 | 文件 | 三種模式的共用說明每個 fixture +150–400 token；self-hosted 細節以條件 render 則為 0 | agent 文件 token（hosted 餘裕 540） | +800–1,500 token |

合計：self-hosted 本身在 hosted fixture 約 **1.6–2.6 KB**，勉強落在 2,828 B 的餘裕內，但 settings 與 verification 兩個分項需要空間；加上 #1264 的 5–6 KB，hosted 約需 **6.6–8.6 KB，缺口約 4–6 KB**，缺口主要來自 #1264。新的 self-hosted fixture 約等於 hosted 加 7–11 KB，需要新增一組 fixture 預算。依 #1231 第 8 點，新增或上調預算都要修訂 [generated-repository-layout](generated-repository-layout.md) 並由擁有者核准。

## 未來研究（不在 Milestone 21）

- **Release 後的部署驗收環境：**部署已發布的 artifact，再跑驗收或 smoke test。目前模板沒有這類測試，也沒有部署目標；需要先定義測試內容與部署契約，才談得上環境。
- **常駐的產品測試服務：**驗證時需要的資料庫、外部服務模擬等長時間運作的服務。它與「不常駐」的決定衝突，需要另外處理資源、隔離與關閉責任。

兩項都另開 Issue 研究，屆時重新評估 `self_hosted_services` 是否需要。

## 待決問題

第一版的 O1（跨 repo 憑證）、O2（模板 repo 維持 hosted）、O3（repository 層級 runner）、O4（runner 型態）、O5（只有驗證 job 上 VM）、O11（release 證據）、O12（Dependabot 環境）已由擁有者 2026-10-24 的決定解決，不再列出。

**給擁有者：**

| ID | 問題 | 本草稿建議 |
| --- | --- | --- |
| O1 | 合併時是否要重新讀取 csarc-devops 的登記狀態，讓撤銷立即擋下已有證據的合併？（需要唯讀憑證在 lifecycle 可用） | 是；本機 lifecycle 用操作者自己的 `gh` 登入讀取，hosted gate 用 csarc-devops 的唯讀憑證 |
| O2 | csarc-devops 核准留言用 `/self-hosted …` 語彙，還是逐字沿用 `/milestone approve`？`registration` URL 放在 `self_hosted_runner` 裡，還是另設一個設定？ | `/self-hosted …`；放在 `self_hosted_runner` 裡 |
| O3 | `self_hosted_services` 是否在本 Milestone 加入？#1271 的「常駐服務」範圍是否改為開窗、延長、關窗與 `status`？ | 不加入，留給未來研究；#1271 改為窗口指令（需要修改 #1271 的 AC） |
| O4 | 退出 self-hosted 是否只需要 repo 端核准？ | 是，並通知 csarc-devops |
| O5 | 窗口紀錄放在 repository variable（管理員開窗、延長、關窗時寫入）是否可接受？提醒門檻 2 小時、停止派工門檻 30 分鐘是否合適？ | 可接受；variable 只用來 fail closed 與提醒，不是信任依據；門檻照建議 |
| O6 | VM 長期無法使用時，是否提供 D7 的「改回 hosted」一次性出口？ | 提供，只限該 route |
| O7 | AC1 要求「ADR 與規格」：是否另開 `docs/specs/SPEC-011`？ | 在 #1268 隨 schema 一起寫 SPEC-011，本 ADR 只保留決定與理由 |
| O8 | #1267 取得空間的方式（瘦身、修訂預算或並用）與新的 self-hosted fixture 預算 | 由 #1267 依上表提出數字後決定 |
| O9 | 擁有者決定 4「DEV 一定要有測試機」是否改為「依目標分支需要」？ | 改為：使用 Milestone 的 repo 需要 `dev` 與 `uat`，不使用的只需要 `uat` |

**給 csarc-devops（需另開對方 Issue，雙方連結）：**

| ID | 問題 |
| --- | --- |
| C1 | 註冊 token 與延長要求的交付管道（例如管理員以自己的 VM 帳號透過 SSH 交付）；VM 如何核對允許清單、記錄開始與結束時間、延長時改停止時間、到期停止 runner 並刪除 runner 憑證檔；`status` 如何讀取 VM 端的紀錄 |
| C2 | runner label 與 `runner_name` 命名規則（建議 `csarc-<vm-id>`、`csarc-env-<env>`，`runner_name` 為 `<vm-id>-<env>-<開窗時間>`），以及 VM ID 是否穩定、可重查 |
| C3 | 每個（repo, 環境）的帳號、目錄與快取配置；UAT 快取在窗口結束時刪除；對外網路與 metadata endpoint 政策 |
| C4 | runner log 的轉存位置與保存期限；入侵事件時的停止與重建程序 |
| C5 | 允許清單的格式、核准者名單與權限、撤銷的處理時限與通知方式；只讀 csarc-devops Issue 的憑證由誰建立與輪替 |

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 維持 hosted，改用 GitHub larger runner 或快取 | 不採用；仍耗用 GitHub 額度（擁有者決定 2） |
| VM 自己跑測試再回報結果（不經 GitHub 派工） | 不採用；結果由 VM 自行聲明，信任等級與 `local` 相同 |
| 常駐 runner 與 DEV／UAT／PRD 常駐環境（第一版草稿） | 不採用；擁有者 2026-10-24 改為按需開窗，暴露面限於 24 小時內的同一 repo、同一環境 |
| csarc-devops 以 GitHub App 替下游取得註冊 token、管理 runner | 不採用；需要 Administration 寫入權限，同一權限可以改 Ruleset、collaborator、Actions 設定，甚至刪除 repo |
| 每個 job 一個 ephemeral／JIT runner | 不採用；每個 job 都要管理員憑證，或必須把下游權限交給 VM |
| 組織層級 runner 放在 default group，只用 label 區分 repo | 不採用；Free 方案下組織內每個 private repo 都能派工上去 |
| 設 PRD 驗證環境 | 不採用；release 只發布已驗證的候選，沒有獨立的 release 驗證內容 |
| 窗外或 VM 不可用時自動改派到 GitHub-hosted | 不採用；擁有者要求窗外 fail closed |
| fork PR 經維護者核准後可以上 VM | 不採用；擁有者決定 6 與 GitHub 的建議都排除 fork |
| 每次開窗也要雙邊核准 | 不採用；擁有者決定取得 token 本身就是授權動作，登記才需要雙邊核准 |
| 窗口次數或總時數上限 | 不採用；擁有者決定只用固定 24 小時，取捨見 D5 |
| self-hosted 程式碼直接加進共用 script | 不採用；hosted fixture 與 verification 分項已沒有空間，且會讓 `local`、`hosted` 專案承擔用不到的程式 |

## 重新評估條件

- 組織升級到 Team 或 Enterprise：可改用只開放選定 repo 的 runner group，或重新評估由集中管理的 runner。
- csarc-devops 能在不持有下游權限的情況下提供每個 job 一台新 VM（例如 GitHub 提供範圍更窄的 runner 權限）：重新評估 D6，可能提高信任等級。
- 模板 repo 改成 private，或有團隊以外的貢獻者需要使用 self-hosted：重新檢查限制 1 與 D4。
- 發生 VM 入侵、快取汙染或註冊 token 外洩事件：檢討 D5、D6。
- 觀察到某個 repo 長期每天延長或重開窗口，實際上接近常駐：檢討是否需要次數上限，或延長時改為換一個新 runner。
- 未來研究的部署驗收環境或常駐服務成案時：重新評估環境清單與 `self_hosted_services`。
- GitHub 改變 self-hosted runner、registration token、`pull_request_target` 或 Jobs API 回傳的 runner 欄位。
- #1267 無法取得足夠空間：重新評估哪些能力先做、哪些延後。
