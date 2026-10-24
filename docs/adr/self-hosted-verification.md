# Self-hosted verification mode ADR

- **狀態：**Proposed
- **日期：**2026-10-24
- **來源 Issues：**[#1266](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1266)、[#1265](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1265)（Milestone 21 tracker，擁有者 2026-10-24 決定）；部分取代 [#908](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/908) 的新專案預設
- **實作 PR：**待擁有者核准本草稿後，由 #1266 的 PR 填入

## 問題與限制

目前只有兩種驗證模式。`local` 在開發者電腦上執行，結果只能自我證明（`self-attested-local`）；`hosted` 在 GitHub-hosted `ubuntu-latest` 執行，結果可信，但耗用 GitHub 運算額度，每次都從零建立環境。擁有者 2026-10-24 在 #1265 決定新增第三種模式 `self-hosted`：在 csarc-devops 提供的團隊 VM 上執行 GitHub 官方 self-hosted runner，由 GitHub 派工；只開放給登記的 private repo，外部 fork 的 PR 一律不在 VM 執行；登記要由兩邊 Issue 互相連結、雙方核准。

擁有者同日審閱兩版草稿後確認的決定（本版依此撰寫）：

1. **按需開窗，不設常駐 runner 或常駐環境。**repo 管理員以模板指令開窗：先輸出唯讀盤點，再以管理員**自己的**憑證取得這個 repo 的 runner 註冊 token 交給 VM；VM 檢查允許清單後讓 runner 上線 24 小時。開窗不另走核准，取得 token 本身就是授權動作。接近到期時提醒管理員延長；除了固定 24 小時之外不另設上限。
2. **csarc-devops 只管 VM（載具），對下游 repo 沒有任何權限。**它只能使用讀取自己 repo Issue 的憑證，處理一次性的雙邊登記核准。
3. **只有 DEV 與 UAT。**DEV＝進 `dev/m*`、`dev/i*` 的 PR；UAT＝進 `main` 的 PR（promotion、standalone、hotfix，也就是物化 stable 版本的地方）。不設 PRD：release 只發布已驗證的候選。
4. **窗外一律 fail closed，不改在 GitHub-hosted 執行。**
5. **只有驗證 job 上 VM，**帶唯讀 job token、不帶 secret；持有寫入 token 的 job 留在 GitHub-hosted。只用 repository 層級的 runner。
6. **設定依可見性拆成兩個，新專案的 private 預設改為 `self-hosted`。**`verification_mode_private`（`self-hosted`｜`hosted`｜`local`，預設 `self-hosted`）與 `verification_mode_public`（`hosted`｜`local`，預設 `hosted`，`self-hosted` 在驗證時被拒絕）。實際模式依 repository **當下**的可見性決定。這部分取代 #908「新專案預設 `local`」。既有專案也預期改用，但絕不自動切換。模板 repo 是 public，因此自然維持 `hosted`。
7. **登記完成前，驗證 fail closed 並附登記指引，**不靜默改用其他模式。
8. **可見性安全以 VM 為最後防線，**PR 無法改變；repo 轉成 public 後，VM 立即停止 runner 並刪除該 repo 的工作目錄與快取。
9. **log 隨 repo 公開而公開，**因此限制 log 內容、建議縮短保存期限，並提供 `retire` 指令在公開前清除。
10. **90 天未開窗的登記由 VM 端自動到期。**
11. **列為未來研究、不在本 Milestone：**release 後的部署驗收環境，以及常駐的產品測試服務。

撰寫本草稿時已查證的限制（2026-10-24，base `2035b0d`）：

1. **public repo 不應使用 self-hosted runner。**GitHub 的說明是 self-hosted runner「幾乎不應該」用在 public repo，因為任何人都能開 PR 在機器上執行程式碼（[Security hardening：Hardening for self-hosted runners](https://docs.github.com/en/actions/reference/security/secure-use#hardening-for-self-hosted-runners)）。
2. **組織是 GitHub Free 方案。**只有 default runner group，建立其他 group 需要 Team 方案；default group 預設只讓 private repo 使用（[Managing access to self-hosted runners using groups](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access)）。組織層級 runner 放在 default group，組織內每個 private repo 都能用 label 派工上去；label 只是路由，不是存取控制。repository 層級 runner 只會收到該 repo 的 job。
3. **註冊 token 只能由 repo 管理員取得，一小時內有效。**`POST /repos/{owner}/{repo}/actions/runners/registration-token` 要求呼叫者對 repo 有 admin 權限，token 一小時後失效（[REST：Create a registration token for a repository](https://docs.github.com/en/rest/actions/self-hosted-runners#create-a-registration-token-for-a-repository)）。移除 repository runner 也需要管理員；離線超過 14 天的 runner 會被 GitHub 自動移除（[Removing self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/remove-runners)）。
4. **csarc-devops 是 private repo。**下游 workflow 的 `GITHUB_TOKEN` 讀不到它的 Issue，登記核准的唯讀讀取需要一個只讀 csarc-devops Issue 的憑證。AGENTS.md 不允許把 personal token 當成 portable baseline。
5. **現有證據只接受 GitHub-hosted runner。**`scripts/verification_evidence.py` 要求 job labels 含 `ubuntu-latest`、`runner_group_name` 等於 `GitHub Actions`，含 `self-hosted` label 一律拒絕；merge trace 的 `CSARC-Trust` 只有 `github-hosted` 與 `self-attested-local`（`scripts/merge_trace.py`）。
6. **hosted 專屬的 payload 全以 `verification_mode == 'hosted'` 決定是否 render**（`copier.yml` 的 `_exclude`，約 30 個條件）。`csarc` CLI 是獨立的 Python 套件（`src/csarc_cli`），不在生成專案的 payload 裡。
7. **trusted executor 不是 sandbox。**[trusted-base-gate](trusted-base-gate.md) 已寫明它防的是 candidate 改 gate 讓自己通過；candidate 的測試碼仍在同一台機器執行。同一個 runner 連續接多個 job 時，前一個 job 可以留下影響後一個 job 的狀態（GitHub 同一份 hardening 說明）。
8. **`verify` 由 `pull_request_target` 載入 base 的 workflow，但會 checkout 並執行 candidate 的測試。**任何觸發 `verify` 的 PR，包含 fork PR，都會把 candidate 程式碼帶到執行機器上。不能依賴 repo 的 fork PR 核准設定（[Managing GitHub Actions settings：fork pull request workflows in private repositories](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#controlling-changes-from-forks-to-workflows-in-private-repositories)）。
9. **repo 轉成 public 後，過去的 Actions log 也一起公開。**private 期間在 VM 上執行的 log、runner 名稱與路徑，公開後任何人都看得到，直到 log 保存期限到期或被刪除。
10. **payload 餘裕很小。**`scripts/generated_payload.py` 在 `2035b0d` 實測：hosted fixture 距總閘 2,828 B；verification 分項在 hosted 只剩 810 B，Dependabot 分項約 1,000 B；agent 文件 token 在 hosted 剩 540；hosted 具寫入權限的 workflow 已達上限 10／10。solo-default fixture 目前是 `local`，總閘 784,000 B。#1231 規定預算只能下調，上調要修訂 ADR 並由擁有者核准。
11. **[先盤點、再動作](dry-run-inventory-before-action.md) 適用。**登記、開窗、派工、清除都會讓設定或程式碼產生作用，必須先輸出唯讀盤點。

不在本 ADR 範圍：VM 的建置與維運、csarc-devops 允許清單本身的實作、產品部署管線（CD）、修改下游 repo 設定，以及上述第 11 點的未來研究。

## 決定

以下 D1–D11 是提交擁有者核准的設計。標示「建議」的項目有替代做法，列在「待決問題」。

### D1. 定位：hosted 的控制加上換一台執行機器

`self-hosted` 是 `hosted` 的變體，不是新的一套流程：

- required checks（`title`、`verify`、`review`）、Ruleset、GitHub Actions App integration ID 綁定（#835）、trusted executor（#1086、#1069）、exact-head 授權、remote lease、24 小時證據期限（[verification-evidence-freshness](verification-evidence-freshness.md)）與 merge trace（#1073）全部沿用，不放寬任何一項。
- 差別只有三處：執行 candidate 程式碼的驗證 job 改派到窗口內的登記 runner（`runs-on`）；證據多綁定模式、runner、環境與窗口；merge trace 使用新的信任值。
- **只有驗證 job 上 VM：**`verify`、#1264 的 Dependabot 重新驗證。這些 job 只拿唯讀 job token、不帶 secret、`persist-credentials: false`。PR policy、review、lifecycle 寫入、release 發布與 Pages 等持有寫入 token 或 secret 的 job 留在 GitHub-hosted；它們很短，仍會用到少量 hosted 額度。
- render 規則：兩個模式設定中任一個是 `hosted` 或 `self-hosted`，就 render hosted 的 workflow 與 script；`verification_mode_private: self-hosted` 時另外 render self-hosted 專屬的 sibling（沿用 #1177 hosted sibling 的做法）。開窗、延長、關窗、狀態查詢與清除都放在 `csarc` CLI，不進生成專案。

### D2. 設定、預設與實際模式

**兩個設定（取代 `verification_mode`）：**

| 設定 | 可用值 | 新專案預設 | 規則 |
| --- | --- | --- | --- |
| `verification_mode_private` | `self-hosted`、`hosted`、`local` | `self-hosted` | repo 為 private 時使用 |
| `verification_mode_public` | `hosted`、`local` | `hosted` | repo 為 public 時使用；設成 `self-hosted` 時設定驗證失敗 |

- **實際模式（effective mode）**依 repository 當下的可見性，從可信來源取得：派工時讀 GitHub event payload 的 `repository.private`；合併時以不帶憑證的 `GET /repos/{owner}/{repo}` 判斷（讀得到就是 public）。PR 無法影響這兩個來源。兩個設定本身仍只從 trusted base 讀取（#1069）。
- **證據記錄使用的模式。**hosted 與 self-hosted 證據多一個 `mode` 欄位，local 證據本來就標示 `self-attested-local`。合併時證據的模式與當下的實際模式不同，證據即無效。例如 repo 在 PR 驗證後轉成 public，VM 證據就要在 hosted 重跑。
- **可見性改變與 repository 設定。**`local` 與 `hosted`／`self-hosted` 需要的 repository 設定不同（local 停用 required-checks Ruleset，見 `docs/ci-policy.md` #908 一節）。預設組合（private `self-hosted`、public `hosted`）兩邊用同一組 Ruleset，可見性改變不需要改設定；組合中有 `local` 時，可見性改變後實際模式與已套用的設定不一致，合併前要重新套用 repository 設定，governance drift check 會發現這種不一致（待決問題 Q3）。
- **新專案預設改變，部分取代 #908。**#908 的「新專案預設 `local`」由本 ADR 取代：新專案 private 預設 `self-hosted`、public 預設 `hosted`。#908 的其餘內容保留：`local` 模式的行為，以及既有專案沒有欄位時維持 `hosted`。`docs/ci-policy.md` 的 #908 一節由 #1272 更新。
- **Migration。**既有 `verification_mode: <值>` 依原值同時寫入兩個新設定（`local`→兩者 `local`；`hosted`→兩者 `hosted`），行為不變。依 #1069 決定 8，trusted base 的 reader 先支援新 schema，writer 才切換；migration 在外部 pinned CLI 的 migration registry 執行。
- **既有專案改用 self-hosted：**絕不自動切換。`csarc update` 的報告在 private repo 建議改用並列出登記步驟；完成登記（D6）後，以 governance-switch PR 修改 `verification_mode_private`。
- **登記完成前 fail closed。**新專案預設 `self-hosted`，但登記前沒有可用的 VM；這段期間 `verify` 失敗，訊息說明「尚未登記」並列出登記步驟與 `csarc self-hosted status` 指令，不改用 hosted 或 local。`csarc init` 在建立專案時印出同一份登記指引。

### D3. 信任模型與證據綁定

| 項目 | `local` | `hosted` | `self-hosted` |
| --- | --- | --- | --- |
| 可用於 | private、public | private、public | 只有 private |
| 誰派工 | 操作者自己執行 | GitHub | GitHub |
| 在哪執行 | 操作者電腦 | GitHub-hosted VM，每個 job 全新 | csarc-devops VM 上、由 repo 管理員開窗註冊的 repository runner；每次開窗或延長後最多 24 小時，期間可接多個 job |
| workflow 與 gate 來源 | trusted base（#1069） | trusted base（`pull_request_target`、#1086） | 同 hosted |
| 結果由誰記錄 | 操作者寫入 Git metadata | GitHub Check Runs、Jobs API | 同 hosted；runner 名稱、labels、group 由 GitHub Jobs API 記錄，不由 VM 自行回報 |
| 能證明 | 某人聲稱在 exact head 跑過指定 tier | GitHub 在乾淨 VM 上以 base 的 workflow 對 exact tree 執行指定 command 並成功 | GitHub 把 base 的 workflow 派給這個 repo 在有效窗口內註冊的 runner，在預期環境對 exact tree 執行指定 command 並成功 |
| 不能證明 | 結果未被偽造；環境；GitHub 事件與權限 | candidate 測試碼本身無惡意（不是 sandbox） | 同 hosted；另外不能證明同一窗口內先前的 job 沒有留下影響、VM 的工具鏈未被改動，也不能排除 VM 管理者竄改執行環境 |
| 信任前提 | 操作者 | GitHub | GitHub＋開窗的 repo 管理員＋csarc-devops 的隔離契約（D7）＋一次性雙邊登記（D6） |
| `CSARC-Trust` | `self-attested-local` | `github-hosted` | `self-hosted-registered`（新值） |

結論：`self-hosted` 比 `local` 強，因為結果由 GitHub 記錄，操作者無法只靠寫一份 JSON 產生證據；比 `hosted` 弱，因為同一窗口內的 job 共用機器狀態，信任延伸到開窗者與 csarc-devops。窗口制讓這個共用只在管理員明確開窗或延長的期間內存在，而且只在同一個 repo、同一個環境內。merge trace 用獨立的信任值，事後可以用 `merge_trace.py audit` 列出所有依賴 VM 的合併（D9 的事件處理需要它）。

**證據綁定。**hosted 證據的既有欄位（repository、exact head／tree、base、tier、scopes、command、toolchain、label set、release level、結果、完成時間）全部保留，另外：

1. 所有 GitHub 執行的證據都記錄 `mode`（`hosted` 或 `self-hosted`），合併時必須等於當下的實際模式（D2）。
2. self-hosted 證據的 job `labels` 含 `self-hosted`、登記的 runner label，以及**由 trusted base router 計算出的預期環境** label（D4）。實際模式是 `self-hosted` 時，`ubuntu-latest` 證據不被接受。
3. `runner_name` 符合窗口的命名規則（不含主機名稱，例如 `<vm-id>-<env>-<開窗時間>`），`runner_group_name` 為 `Default`；這些值來自 Jobs API。
4. execution step 名稱加上 `mode=`、`environment=<dev|uat>` 與 `window=<開窗時間>`，必須與 job labels、runner 名稱、router 的預期環境一致；任何一項不符即拒絕，訊息要求在正確環境重跑。
5. 證據 payload 與 canonical merge evidence 多記 `mode`、`runner`、`environment`、`window`，`check-trusted-verification` 可以重查並顯示（#1265 AC1）。
6. 期限仍是 24 小時，從 job 完成時間起算。窗口結束不會讓窗口內完成的證據失效；登記被撤銷、到期，或 repo 轉成 public 才會（D9）。

### D4. 環境對應：DEV 與 UAT，依目標分支決定

環境由 trusted base 的 router 依 PR 的目標分支決定，candidate 不能自選：

| 目標分支 | 典型 PR | 環境 |
| --- | --- | --- |
| `dev/m*`、`dev/i*` | Milestone 的 work PR、main→delivery 同步、checkpoint terminal（物化 beta） | `dev` |
| `main` | promotion、standalone、hotfix、release-recovery、`release/v*` guided candidate（物化 stable）；Dependabot PR | `uat` |

- merge queue 依同一規則：`dev/m*` 的 queue 用 `dev`，`main` 的 queue 用 `uat`。
- 環境與 tier（fast／full）互相獨立：tier 仍由 `ci_tier.py` 與 channel floor 決定。
- 預期環境不在 `self_hosted_environments` 裡、或該環境沒有有效窗口時 fail closed，不改用另一個環境，也不改用 hosted。
- **不設 PRD。**`release.yml` 只發布已驗證的候選：它照現行規則重用來源 PR 的證據（tree 相同、在期限內，且模式等於當下實際模式）。現行 hosted 模式在無法重用時會對 main tree 重跑 hosted full；self-hosted 模式改為 fail closed，訊息要求開 UAT 窗口後重新執行 release workflow。
- 不使用 Milestone 的 repo 可以只登記 `uat`；使用 Milestone 的 repo 需要兩個環境。

### D5. 只限登記的 private repo、排除 fork：多層防護

任何一層單獨失效，其他層仍然擋得住。VM 端的兩層（L4、L5）設定在 VM 上、不在 repo 裡，是 PR 無法改變的最後防線。

| 層 | 誰負責 | 擋下什麼 | 控制 |
| --- | --- | --- | --- |
| L1 GitHub 註冊 | repo 管理員（開窗） | 其他 repo | 只用 repository 層級 runner：註冊 token 由該 repo 的管理員以自己的憑證取得，GitHub 只把該 repo 的 job 派給它（限制 2、3）。未登記的 repo 拿不到 VM 的配合，登記的 repo 沒開窗就沒有 runner。 |
| L2 開窗 | 模板（`csarc` CLI，#1271） | public repo、未登記 | `open` 讀到 repo 是 public 就拒絕，不取得註冊 token；VM 也核對允許清單。 |
| L3 trusted router | 模板（#1269） | public repo、fork、窗外、未登記 | 派工前，一個不執行 candidate 程式碼的 GitHub-hosted route job 計算：event payload 的可見性、PR head repo 是否等於本 repo、目標分支與預期環境、設定是否完整、窗口是否有效（D6）。public repo 一律不派到 VM；任一項不成立，`verify` 由 route job 回報失敗並說明原因。`runs-on` 的 labels 由 route job 輸出，candidate 無法改變。 |
| L4 VM job-started hook | csarc-devops（C6） | public repo、fork | runner 的 job-started hook（`ACTIONS_RUNNER_HOOK_JOB_STARTED`，設定在 VM 上）在 job 執行任何步驟前讀 GitHub 提供的 event payload：repo 不是 private、或 PR head repo 不等於 base repo，就以非 0 結束，job 失敗。 |
| L5 VM 定期檢查 | csarc-devops（C7） | 窗口期間轉成 public | 窗口期間定期以不帶憑證的 GitHub API 查 repo；讀得到就是 public。發現 public 時立即停止 runner，刪除該 repo 在 VM 上的工作目錄與快取，並在 csarc-devops 開 Issue 記錄（D8）。 |
| L6 lifecycle | 模板（#1269、#1270） | 合併當下為 public、fork、錯誤 runner | 合併時重新判斷實際模式；repo 已是 public 時 VM 證據無效。另外檢查 head repo 等於 base repo，runner、group、環境、窗口符合登記與命名。 |

設定一律從 trusted base 讀取（#1069）。PR 把模式改成 self-hosted 或改動登記設定時，新設定要等合併後才生效，這張 PR 本身仍依 base 的模式驗證。

外部 fork 的 PR：L3 不派工，L4 拒絕執行，L6 拒絕其證據。需要接受外部貢獻時，由維護者把變更搬到本 repo 的分支重新開 PR。

### D6. 登記契約、開窗與到期

**一次性登記（雙邊核准）。**登記決定「這個 repo 可以使用哪台 VM 的哪些環境」，之後每次開窗都不再核准。

Repo 端設定（`.csarc/config.yml`，#1268 實作 schema），除 D2 的兩個模式設定外：

| 設定 | 型別與預設 | 意義 |
| --- | --- | --- |
| `self_hosted_runner` | mapping；`verification_mode_private: self-hosted` 時必填：`id`（登記的 VM ID，例如 `csarc-vm-01`）、`registration`（csarc-devops 登記 Issue 的完整 URL） | 指向哪台 VM，以及哪一張 csarc-devops Issue 承載核准；`id` 用來推導 runner label 與命名（C2） |
| `self_hosted_environments` | `dev`、`uat` 的非空子集合 | 這個 repo 登記了哪些環境 |
| `self_hosted_services` | **本 Milestone 不加入** | 常駐產品測試服務列為未來研究 |

新專案預設 `self-hosted` 但尚未登記時，`self_hosted_runner` 留空；設定驗證接受「尚未登記」這個狀態，`verify` 依 D2 fail closed 並附登記指引。

csarc-devops 端維護允許清單，每筆至少記錄：repo 全名、VM `id`、環境、csarc-devops Issue、repo 端 Issue、核准時間、最後一次開窗時間。格式由 csarc-devops 的 Milestone 負責；模板不讀這份清單。

登記變更（開始使用、增減環境、更換 VM、撤銷）的流程：

1. Repo 端（模板或下游）與 csarc-devops 各開一張 Issue，兩張互相引用完整 URL（雙向連結）。
2. csarc-devops Issue 本文含一個固定格式的登記區塊，內容等於 repo 全名與變更後的 `self_hosted_*` 設定。
3. 兩邊各自核准。Repo 端沿用既有核准（Milestone tracker 或無 Milestone Issue 的核准）。csarc-devops 端的核准留言格式與 Milestone 核准相同；建議語彙 `/self-hosted approve`、`/self-hosted admin-approve: <理由>`、`/self-hosted object: <理由>`、`/self-hosted resolve: <目標>`，另加 `/self-hosted revoke: <理由>`。判斷演算法與 Milestone 核准相同：以 collaborator permission API 判斷核准者權限；最新的有效留言決定狀態；核准後 Issue 本文被修改，核准即失效。
4. 改動設定的 PR 帶 `governance-switch` label（#1069 既有 route）。#1270 的 gate 以唯讀 API 讀取 csarc-devops Issue 的本文與留言，確認雙向連結、登記區塊與 PR 的新設定逐字相符、核准有效。讀取失敗、缺少任一方核准、只有單向連結、核准失效或被反對、內容不符，都 fail closed，訊息說明原因並給下一步。
5. 讀取憑證：csarc-devops 提供一個**只讀取 csarc-devops 自己 Issue** 的 GitHub App（或同等憑證），下游以 secret 保存，只在 GitHub-hosted、只執行 trusted base 程式碼的 policy job 使用，永遠不交給 VM 上的 job。它對下游 repo 沒有任何權限。
6. 合併後 csarc-devops 依核准更新允許清單。
7. 登記指引（`csarc init`、`csarc update` 報告與 #1272 的導入指南）同時建議把 repo 的 Actions log 保存期限縮短為 7 天（D7）；修改 repo 設定由管理員自己決定與執行。

退出 self-hosted（改用 `hosted` 或 `local`、移除環境）只需要 repo 端核准，並通知 csarc-devops 更新允許清單。改成 `local` 仍屬放寬治理值，照 #1069 走 governance-switch。

**為何 csarc-devops 不持有下游權限。**repository runner 的管理需要 Administration 寫入權限，而這個權限同時能改 Ruleset 與 branch protection、管理 collaborator、修改 Actions 設定，甚至刪除 repo（[Permissions required for GitHub Apps](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps)）。把它交給管理 VM 的團隊，等於讓載具可以關掉下游的全部治理。改由下游管理員每次以自己的憑證開窗，csarc-devops 只需要讀自己 repo Issue 的權限。

**開窗（每次使用，不另核准）。**repo 管理員執行 `csarc self-hosted open --env dev|uat`：

1. 唯讀盤點並印出：repo 與可見性、設定中的 VM 與環境、窗口長度（固定 24 小時）與結束時間、窗口內會執行什麼（只有驗證 job、唯讀 token、不帶 secret）、目前是否已有同環境的窗口與 runner。repo 是 public、尚未登記或任一項不符就停止。
2. 以管理員自己的 `gh` 登入呼叫 registration-token API。管理員的 GitHub 憑證不離開本機、不寫入任何檔案；交給 VM 的只有這個一小時內有效的註冊 token。
3. 經 csarc-devops 指定的管道把 token、repo、環境交給 VM（C1）。VM 核對允許清單，以固定命名與 labels 註冊**一個** runner，記錄開始與結束時間，並更新允許清單的最後開窗時間。
4. 指令讀回 runner 清單，確認這個 repo 只有一個符合命名的線上 runner；出現預期之外的 runner 時，移除全部並以錯誤結束（防止註冊 token 外洩後被用來註冊其他機器）。
5. 寫入窗口紀錄，讓 route job 與驗證 job 判斷窗口是否有效、還剩多久。

**窗口紀錄（最小權限）。**開始與結束時間記在兩處：VM 端（真正停止 runner 的依據），以及 repository variable `CSARC_SELF_HOSTED_WINDOW_<ENV>`（runner 名稱、開始與結束時間，UTC）。選 variable 是因為 workflow 以 `vars` context 讀取不需要任何額外 job 權限；寫入只發生在管理員以自己的憑證開窗、延長或關窗時。它只用來讓窗外立即 fail closed 與提醒延長，**不是信任依據**；證據仍以 Jobs API 的 runner 資料為準。

**剩餘時間、延長與關窗。**

- `csarc self-hosted status [--env dev|uat]`：唯讀顯示每個環境的 runner、開始與結束時間、剩餘時間、窗口紀錄與 VM 回報是否一致、登記是否到期，以及 D8 的公開警告。
- **最後 2 小時提醒：**驗證 job 的 trusted step 讀窗口紀錄；剩不到 2 小時時，在輸出與 job summary 各印一行，依寫作指引的句型，例如 `WARNING: The dev self-hosted window ends at 2026-10-25T09:00Z (1h40m left). Run 'csarc self-hosted extend --env dev' to keep verifying.`。提醒不改變 job 結果。
- **剩不到 30 分鐘（job timeout）不派工：**route job 失敗並要求先延長，避免 job 執行到一半被停止。
- **延長：**`csarc self-hosted extend --env dev|uat`，窗口仍有效時重跑 `open` 等同延長。先印盤點（目前 runner、舊與新結束時間），再以管理員自己的憑證確認同一 runner 在線，更新窗口紀錄，並經同一管道要求 VM 把停止時間改為「現在＋24 小時」。不取得新 token、不註冊第二個 runner，沒有空窗；不累加。窗口已過期只能重新 `open`。
- **關窗：**`csarc self-hosted close --env dev|uat` 以管理員憑證刪除 runner、清除窗口紀錄。不執行時，VM 到期停止 runner 並刪除 runner 憑證檔，使它不能再連線；離線 runner 不會再收到 job，GitHub 也會在離線 14 天後自動移除。

**24 小時固定窗口、不設次數上限的取捨。**窗口長度與證據期限一致，一個工作日的 review 與合併用一個窗口即可；忘了關窗也會到期。不設上限代表 repo 可以每天延長、實際上接近常駐，延長沿用同一 runner，同一窗口內 job 共用機器狀態的時間也跟著拉長；擁有者接受這一點，因為每次延長都是管理員明確的動作並留下紀錄。

**登記到期（VM 端）。**登記的 repo 連續 90 天沒有開窗，VM 從允許清單移除它、刪除它在 VM 上的快取與資料，並在 csarc-devops 開 Issue 記錄。之後 `open` 會收到「registration expired」並提示依本節重新登記；repo 的設定仍是 `self-hosted`，因此 `verify` 依 D2 fail closed 並附登記指引。是否另外偵測 repo 已封存（archived），需要 Metadata 唯讀憑證，目前不做。

### D7. 窗口內的隔離與 log 衛生

一個窗口是一個非 ephemeral 的 repository runner，最多存活 24 小時、可以連續接多個 job。GitHub 建議 ephemeral 或 just-in-time runner（[Self-hosted runners reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)），但 ephemeral runner 每接一個 job 就要一個新的註冊 token，只能由管理員取得；VM 不持有下游權限，做不到每個 job 重新註冊。殘留風險因此限於同一 repo、同一環境、同一窗口內。為了把它壓低：

1. **帳號與目錄。**每個（repo, 環境）一個專用 OS 帳號與 runner 目錄，彼此不可讀寫；runner 帳號不在 `docker`、`sudo` 群組。
2. **每個 job 的清理。**以 job started／completed hook 清空工作目錄、結束殘留程序；窗口結束時刪除整個 runner 目錄與 runner 憑證檔。
3. **工具鏈。**依語言 profile 預先安裝在 root 擁有的唯讀路徑，版本由 #1271 的工具鏈契約固定。
4. **快取。**依賴快取放在每個（repo, 環境）自己的目錄，以 lockfile digest 分 key，不跨 repo、不跨環境共用；UAT 不使用 DEV 的快取。建議 UAT 的快取在窗口結束時刪除，DEV 的快取可以跨窗口保留（C3）。
5. **Secrets。**VM 上不放長期 secret；驗證 job 不帶 secret、只有唯讀 job token。註冊 token 用完即丟。封鎖雲端 metadata endpoint，對外網路依 csarc-devops 政策限制。不以命令列參數傳遞任何機密。
6. **log 衛生。**job log 在 repo 轉成 public 後會公開（限制 9），所以 VM 寫進 job log 的內容要能公開：runner 名稱用通用格式（不含主機名稱或內部網域），工作目錄用通用路徑（例如 `/runner/_work`），hook 不印出內部位址、帳號或網路資訊。登記指引建議 Actions log 保存 7 天，縮短 private 期間 log 的公開窗口。VM 自己的 runner log 轉存到 csarc-devops 的外部儲存供事件調查（C4），不屬於 repo。

### D8. 公開前清除（`retire`）與事後偵測

**公開前必須執行 `csarc self-hosted retire`。**repo 從 private 轉成 public 之前，管理員必須執行它；#1272 的文件與 `status` 都標示為必要步驟。這個動作不可回復，只由管理員以自己的憑證執行：

1. 預設只做唯讀盤點：列出由 self-hosted runner 執行的 workflow run、它們的 artifact 與 Actions cache、目前的 runner 與窗口紀錄。
2. `--apply` 時依盤點刪除這些 run、artifact 與 cache，移除 runner 與窗口紀錄，並建立一張 governance-switch PR，把 `verification_mode_private` 改成 `hosted`（設定變更仍要經過 PR，不由指令直接改 trusted 設定）。同時產生給 csarc-devops 的退出通知內容，由管理員開 Issue（退出只需 repo 端核准）。
3. 輸出刪除結果與無法刪除的項目；任何一項失敗都以非 0 結束，訊息說明哪些 log 仍會在公開後被看到。

**事後偵測。**沒有先 `retire` 就公開時：

- VM 的定期檢查（L5）發現 public，立即停止 runner、刪除該 repo 的工作目錄與快取，並在 csarc-devops 開 Issue 記錄。VM 對下游沒有權限，不在下游 repo 開 Issue。
- 模板端不依賴讀取 csarc-devops：`csarc self-hosted status` 與下一次 `csarc update` 報告，只要發現 repo 是 public，且仍有 self-hosted 執行的 run 或 `CSARC-Trust: self-hosted-registered` 的 merge trace，就印出 `WARNING:`，要求執行 `retire`。能讀取 csarc-devops 時，另外顯示 VM 端的事件紀錄。
- 合併時 L6 讓 VM 證據失效，實際模式改為 `verification_mode_public`。

### D9. 失效、撤銷與降級

原則：**不靜默改用其他模式。**實際模式是 `self-hosted` 時，`ubuntu-latest` 的結果不被接受；無法在登記環境的有效窗口內完成驗證時，`verify` 失敗，合併被擋下，訊息說明原因與下一步。

| 情況 | 行為 | 下一步（訊息內容） |
| --- | --- | --- |
| 尚未登記（新專案預設） | route job 失敗，不派工 | 依 D6 登記；登記指引見 `csarc self-hosted status` |
| 登記到期（90 天未開窗） | `open` 收到 registration expired；`verify` 同上 | 依 D6 重新登記 |
| 沒有開窗或窗口已過期 | route job 依窗口紀錄判斷，`verify` 立即失敗 | 請 repo 管理員執行 `csarc self-hosted open --env <環境>`，再重跑 `verify` |
| 窗口剩不到 2 小時 | 驗證照常執行，輸出與 job summary 印出 `WARNING:` | 執行 `csarc self-hosted extend --env <環境>` |
| 窗口剩不到 30 分鐘 | route job 不派工，`verify` 失敗 | 延長窗口後重跑 `verify` |
| 窗口紀錄有效，但 runner 離線 | job 停在 queued，`verify` 沒有成功結果；GitHub 在 24 小時後讓 job 失敗 | 執行 `status`；請 csarc-devops 恢復 VM，或關窗後重新開窗 |
| 窗口在 job 執行中到期 | runner 停止，job 失敗 | 重新開窗後重跑 `verify` |
| 預期環境未登記 | route job 失敗 | 依 D6 登記該環境 |
| VM 拒絕註冊（不在允許清單） | `open` 以錯誤結束，不寫窗口紀錄 | 確認登記已合併，並請 csarc-devops 更新允許清單 |
| 出現預期之外的 runner | `open` 移除這個 repo 的全部 self-hosted runner 並以錯誤結束 | 視為註冊 token 外洩，通知 csarc-devops 並檢查 repo 稽核紀錄 |
| repo 轉成 public | L4、L5 停止 VM 上的執行並刪除資料；L6 讓 VM 證據失效；實際模式改用 `verification_mode_public` | 執行 `retire`；在 hosted 或 local 重新驗證 |
| 登記被撤銷或核准失效 | VM 不再接受開窗；#1270 的 gate 失敗；合併時讀到撤銷則拒絕，即使已有 24 小時內的證據（Q5） | 依 D6 重新登記，或開 PR 退出 self-hosted |
| 讀不到 csarc-devops | 需要讀取的步驟 fail closed | 確認唯讀憑證後重跑；不提供略過選項 |
| 證據的模式、runner、group、環境或窗口不符 | 拒絕 | 在正確模式與環境重跑 `verify` |
| release 無法重用來源證據 | `release.yml` fail closed | 開 UAT 窗口後重新執行 release workflow |
| 懷疑 VM 被入侵 | csarc-devops 停止該 VM 上所有 runner；各 repo 管理員以 `close` 移除；以 `merge_trace.py audit` 列出事件期間 `CSARC-Trust: self-hosted-registered` 且 runner 屬於該 VM 的合併，逐一重新驗證 | 依 `docs/security-response.md` 處理；恢復前必須重建 VM |

**改用其他模式的出口（建議，Q1）。**trusted base 決定模式，所以「把 `verification_mode_private` 從 `self-hosted` 改成 `hosted` 或 `local`」的 PR 本身仍要求 self-hosted 證據。新專案還沒登記、或 VM 長期無法使用時，這張 PR 會卡住。建議只為「只改模式設定、且方向是離開 self-hosted」的 governance-switch PR 提供一次明確的 GitHub-hosted `verify`（維護者以 `workflow_dispatch` 要求），lifecycle 只在這條 route 接受該 hosted 證據，merge trace 記為 `github-hosted` 並註明原因。不採用時，唯一出口是 Journey 08 既有的 admin bypass 規則。

### D10. 先盤點、再動作

會產生作用的時點都先輸出唯讀盤點，有任何一項不符預期就停止（[dry-run-inventory-before-action](dry-run-inventory-before-action.md)）：

| 時點 | 盤點內容 | 之後的動作 |
| --- | --- | --- |
| 登記與變更（#1270） | 兩張 Issue 的 URL 與雙向連結、核准者與其權限、核准時間、Issue 最後修改時間、登記區塊與設定的逐項差異（舊值→新值） | 全部相符才讓 PR 通過 |
| 開窗（#1271） | repo 與可見性、VM、環境、窗口結束時間、窗口內會執行的 job 類型與權限、既有窗口與 runner | 印出後才取得註冊 token |
| 派工（#1269） | 可見性與實際模式、head repo、目標分支、預期環境、窗口紀錄、要求的 runner labels | 寫進 step summary 後，VM job 才啟動 |
| 延長、關窗（#1271） | 目前 runner 與是否在線、舊與新結束時間；要移除的 runner 與紀錄 | 印出後才更新或刪除 |
| 清除（`retire`，#1271） | self-hosted 執行的 run、artifact、cache、runner、窗口紀錄，以及要修改的設定 | 預設只盤點；`--apply` 才刪除並建立 PR |

盤點只讀資料：設定以 trusted base 的 `csarc_config.py` 讀取，csarc-devops 的留言與 GitHub API 的回應都視為資料，不執行任何下載來的程式碼。

### D11. Ownership 與驗證

| 項目 | Issue | 驗證 |
| --- | --- | --- |
| 兩個模式設定、預設值、實際模式、migration、governance-switch、「尚未登記」狀態 | #1268 | 三種模式與兩種可見性的 root／template 回歸測試；migration 不改變既有專案行為；public 設成 `self-hosted` 被拒 |
| 派工、窗口判斷與提醒、fork 與 public 排除、證據的模式與 runner 綁定、合併時的可見性判斷 | #1269 | fork、public、未登記、缺環境、窗外、錯誤 runner、模式不符的拒絕測試；`check-trusted-verification` 讀回模式、runner、環境與窗口 |
| 雙方核准 gate | #1270 | 雙方核准通過；缺任一方、單向連結、核准失效、讀取失敗都擋下 |
| `open`、`extend`、`close`、`status`、`retire`、工具鏈契約 | #1271 | 盤點與失敗路徑的 CLI 測試；延長不註冊第二個 runner；`retire` 預設不刪除；不寫入管理員憑證 |
| Dependabot 重新驗證 | #1264 | 依 #1264 AC5；self-hosted 模式在 UAT 窗口執行 |
| 文件、登記指引、手冊 r6、下游通知、#908 一節更新 | #1272 | 文件一致性紀錄 |
| VM、允許清單、token 交付管道、hook、定期檢查、90 天到期 | csarc-devops 對應 Issue | csarc-devops 自己的驗收 |

擁有者核准後，本 ADR 隨 #1266 的 PR 合併並改為 `Accepted`；之後實作與本 ADR 不同的地方，在該實作 PR 修訂本 ADR。#1268、#1269、#1271 的完成條件需依本版調整（Q9）。

## Payload 影響估計（交給 #1267）

量測基準：`2035b0d`，`uv run python scripts/generated_payload.py`。數字是 canonical bytes 的粗估（±50%），實作時以實測為準。前提是 D1 的 render 規則：self-hosted 專屬程式只在 `verification_mode_private: self-hosted` 時 render；`open`、`extend`、`close`、`status`、`retire` 都在 `csarc` CLI，不進生成專案。

| Issue | 內容 | hosted、consumer fixture 增量 | 影響的分項 | self-hosted 專屬增量 |
| --- | --- | --- | --- | --- |
| #1268 | 兩個模式設定、實際模式判斷、「尚未登記」狀態、governance-switch 放寬順序 | 每個 fixture（含 solo）+2–3 KB | settings 與 drift（consumer-a 餘裕 3,188 B）；PR lifecycle | 同左 |
| #1269 | 證據的 `mode` 欄位、合併時的可見性判斷與模式比對（共用）；route job、窗口判斷與提醒、`runs-on`、runner 綁定（self-hosted 專屬） | 共用部分 +1–2 KB；**verification 分項在 hosted 只剩 810 B**，必須取得空間或放進 sibling | verification、PR lifecycle | +4–7 KB（含 `ci.yml` 的條件區塊） |
| #1270 | 跨 repo 唯讀讀取、雙向連結、登記區塊比對、核准判斷 | `validate-pr-policy` 掛鉤約 +0.3 KB | PR lifecycle、Milestone 與 Issue | +3–5 KB |
| #1271 | 窗口指令、`retire`、工具鏈清單 | 0（在 `csarc` CLI） | 無（CLI 不在 #1231 的生成專案預算內） | 0 |
| #1264 | Dependabot 重新驗證與合併放行 | +5–6 KB（擁有者 2026-10-24 估計） | Dependabot（餘裕約 1,000 B）；若新增有寫入權限的 workflow，hosted 已達 10／10 | 同左 |
| #1272 | 三種模式說明、登記指引 | +150–400 token；預設 render 另加登記指引 +300–800 token | agent 文件 token（hosted 餘裕 540） | 同左 |

**hosted fixture：**約需 **8.3–11.3 KB**，目前餘裕 2,828 B，**缺口約 5.5–8.5 KB**，其中 #1264 占 5–6 KB；verification、settings、Dependabot 三個分項與 agent 文件 token 也要取得空間。

**預設改變的影響（最大的一項）。**solo-default fixture 的定義是「全部用預設值」。預設改成 private `self-hosted`、public `hosted` 後，它會 render 全部 hosted workflow 與 self-hosted sibling：估計 canonical 約 930–940 KB、檔案約 125、寫入 workflow 10、`pull_request_target` workflow 5、agent 文件 token 約 15,500–16,000，遠超過目前 solo-default 的上限（784,000 B、92 個檔案、0、0、13,500）。這不是瘦身能解決的；需要擁有者決定 fixture 的定義（Q2）。

## 未來研究（不在 Milestone 21）

- **Release 後的部署驗收環境：**部署已發布的 artifact，再跑驗收或 smoke test。目前模板沒有這類測試，也沒有部署目標；需要先定義測試內容與部署契約。
- **常駐的產品測試服務：**驗證時需要的資料庫、外部服務模擬等長時間運作的服務。它與「不常駐」的決定衝突，需要另外處理資源、隔離與關閉責任；屆時再評估 `self_hosted_services`。
- **封存 repo 的偵測：**需要 Metadata 唯讀憑證；擁有者之後需要時再開 Issue。

## 待決問題

先前各版的 O1–O9 中，已由擁有者決定的不再列出；仍待決的併入下表。

**給擁有者：**

| ID | 問題 | 建議 |
| --- | --- | --- |
| Q1 | 新專案預設 `self-hosted` 但尚未登記，或 VM 長期無法使用時，「離開 self-hosted」的 PR 本身無法驗證。是否提供 D9 的一次性 hosted 出口？ | 提供，只限「只改模式設定、方向是離開 self-hosted」的 governance-switch PR；這在預設改變後成為必要 |
| Q2 | 預設改變後 solo-default fixture 超出所有上限，fixture 如何定義？ | 現有 solo fixture 改成明確指定 `local`／`local`（保留原預算與意義，改名 solo-local）；另加 default-self-hosted fixture，預算以 hosted 預算加實測增量訂定，依 #1231 第 8 點由您核准 |
| Q3 | 兩個模式設定中有 `local` 時，可見性改變會讓 repository 設定（required-checks Ruleset）與實際模式不一致，怎麼處理？ | 合併前比對已套用設定與實際模式，不一致就 fail closed 並要求執行 `apply-repository-settings`；預設組合不受影響 |
| Q4 | `retire --apply` 是否只刪除資料並建立 governance-switch PR，而不直接改設定？ | 是；設定變更一律經 PR |
| Q5 | 合併時是否重讀 csarc-devops 登記狀態，讓撤銷立即擋下已有證據的合併？ | 是；本機 lifecycle 用操作者自己的 `gh`，hosted gate 用 csarc-devops 的唯讀憑證 |
| Q6 | 核准語彙與 `registration` 的位置 | `/self-hosted …`；`registration` 放在 `self_hosted_runner` 裡 |
| Q7 | 合併時用不帶憑證的 API 判斷可見性：回應 404 時分不出 private 與已刪除或改名，且有每 IP 每小時 60 次的限制 | 200 判為 public；其他回應再以已驗證的讀取（`GITHUB_TOKEN` 或操作者的 `gh`）確認 `private: true`，無法確認就 fail closed |
| Q8 | AC1 的「規格」 | 在 #1268 隨 schema 寫成 `docs/specs/SPEC-011` |
| Q9 | #1268（兩個設定與新預設）、#1269（沒有 PRD、可見性判斷）、#1271（改為窗口指令與 `retire`）、#1272（#908 一節、登記指引）的完成條件需要改寫 | 核准本 ADR 時一併授權修改這四張 Issue 的完成條件 |

**給 csarc-devops（需另開對方 Issue，雙方連結）：**

| ID | 問題 |
| --- | --- |
| C1 | 註冊 token 與延長要求的交付管道（例如管理員以自己的 VM 帳號透過 SSH 交付）；記錄開始與結束時間、延長時改停止時間、到期停止 runner 並刪除 runner 憑證檔；`status` 如何讀取 VM 端紀錄 |
| C2 | runner label 與 `runner_name` 的通用命名（不含主機名稱或內部網域）、通用工作目錄路徑；VM ID 是否穩定、可重查 |
| C3 | 每個（repo, 環境）的帳號、目錄與快取配置；UAT 快取在窗口結束時刪除；對外網路與 metadata endpoint 政策 |
| C4 | VM 端 runner log 的轉存位置與保存期限；入侵事件時的停止與重建程序；job log 內不出現內部資訊的檢查方式 |
| C5 | 允許清單的格式、核准者名單與權限、撤銷的處理時限；只讀 csarc-devops Issue 的憑證由誰建立與輪替 |
| C6 | job-started hook：讀 event payload，repo 不是 private 或 PR 來自 fork 就拒絕；hook 設定在 VM 上、不受 repo 影響 |
| C7 | 窗口期間的定期可見性檢查：間隔（建議 10 分鐘，注意不帶憑證 API 每 IP 每小時 60 次）；發現 public 時立即停止 runner、刪除該 repo 的工作目錄與快取，並在 csarc-devops 開 Issue |
| C8 | 90 天未開窗的登記到期：移除允許清單、刪除快取與資料、在 csarc-devops 開 Issue 記錄；`open` 回應 registration expired |

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 維持 hosted，改用 GitHub larger runner 或快取 | 不採用；仍耗用 GitHub 額度 |
| VM 自己跑測試再回報結果（不經 GitHub 派工） | 不採用；結果由 VM 自行聲明，信任等級與 `local` 相同 |
| 常駐 runner 與 DEV／UAT／PRD 常駐環境（第一版草稿） | 不採用；擁有者改為按需開窗 |
| csarc-devops 以 GitHub App 替下游取得註冊 token、管理 runner | 不採用；需要 Administration 寫入權限，同一權限可以改 Ruleset、collaborator、Actions 設定，甚至刪除 repo |
| 每個 job 一個 ephemeral／JIT runner | 不採用；每個 job 都要管理員憑證，或必須把下游權限交給 VM |
| 組織層級 runner 放在 default group，只用 label 區分 repo | 不採用；Free 方案下組織內每個 private repo 都能派工上去 |
| 單一 `verification_mode` 加上「public 時自動改用 hosted」的隱含規則 | 不採用；擁有者選擇明確的兩個設定，public 的選擇看得見、可驗證 |
| 只在派工時判斷可見性 | 不採用；PR 驗證後才公開的情況要在合併時擋下，VM 也要能自己發現 |
| VM 發現 public 時在下游 repo 開 Issue | 不採用；VM 對下游沒有權限，改記在 csarc-devops，由模板端自行偵測 |
| 設 PRD 驗證環境 | 不採用；release 只發布已驗證的候選 |
| 窗外或 VM 不可用時自動改派到 GitHub-hosted | 不採用；擁有者要求 fail closed |
| fork PR 經維護者核准後可以上 VM | 不採用；擁有者決定與 GitHub 的建議都排除 fork |
| 每次開窗也要雙邊核准 | 不採用；取得 token 本身就是授權動作，登記才需要雙邊核准 |
| 窗口次數或總時數上限 | 不採用；擁有者決定只用固定 24 小時 |
| 既有專案在更新時自動改用 self-hosted | 不採用；切換一律由 governance-switch PR 明確完成 |
| self-hosted 程式碼直接加進共用 script | 不採用；hosted fixture 與 verification 分項已沒有空間 |

## 重新評估條件

- 組織升級到 Team 或 Enterprise：可改用只開放選定 repo 的 runner group。
- csarc-devops 能在不持有下游權限的情況下提供每個 job 一台新 VM：重新評估 D7，可能提高信任等級。
- 發生 VM 入侵、快取汙染、註冊 token 外洩，或 log 在公開後洩漏內部資訊：檢討 D6–D8。
- 觀察到某個 repo 長期每天延長窗口、實際上接近常駐：檢討是否需要上限，或延長時改為換新 runner。
- 預設改變後，多數新專案長期停在「尚未登記」：檢討預設與登記流程。
- 未來研究成案時：重新評估環境清單與 `self_hosted_services`。
- GitHub 改變 self-hosted runner、registration token、runner hook、`pull_request_target`、不帶憑證 API 的限制，或 Jobs API 回傳的 runner 欄位。
- #1267 無法取得足夠空間：重新評估哪些能力先做、哪些延後。
