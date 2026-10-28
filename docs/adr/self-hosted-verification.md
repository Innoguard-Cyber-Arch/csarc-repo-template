# Self-hosted verification mode ADR

- **狀態：**Proposed
- **日期：**2026-10-25
- **來源 Issues：**[#1266](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1266)、[#1265](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1265)（Milestone 21 tracker，擁有者 2026-10-24、2026-10-25 決定）；部分取代 [#908](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/908) 的新專案預設
- **實作 PR：**[#1273](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/1273)
- **修訂：**[#1281](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1281)（2026-10-26，`container` 模組與 VM 上的 Docker：限制 12、D8 第 7 點、C11）。這次修訂需要擁有者核准，以 #1281 PR 的合併授權作為核准。[#1272](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1272)（2026-10-26，D9 事後偵測的條件；擁有者 2026-10-26 核准）。[#1300](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1300)（2026-10-27，實機開窗確認 C1 ready 時序與 C2 exact labels）。

## 問題與限制

目前只有兩種驗證模式。`local` 由操作者在自己電腦上驗證並以指令治理，結果只能自我證明（`self-attested-local`）；`hosted` 由 GitHub-hosted workflow 驗證與治理，結果可信，但耗用 GitHub 運算額度，每次都從零建立環境。擁有者 2026-10-24 在 #1265 決定新增第三種模式 `self-hosted`，並在 2026-10-24 至 2026-10-25 審閱五版草稿後確認以下決定（本版依此撰寫，已沒有待擁有者決定的問題）：

1. **選項 Y：local 的治理＋VM 的驗證。**self-hosted 盡量不讓 GitHub 執行任何東西。PR policy、review 判定、合併、release 發布與 metadata 寫入都和 `local` 一樣，由操作者或管理員以指令執行（`pr_lifecycle.py`、`publish-release`、Issue wrapper）；不產生任何帶寫入 token 的 GitHub workflow，VM 永遠拿不到可寫入的 token。驗證由**一個唯讀 workflow** 在 VM 上執行：GitHub 只負責把它排程到 repository runner，不使用 GitHub-hosted 運算。
2. **按需開窗。**repo 管理員以模板指令開窗：先輸出唯讀盤點，再以管理員**自己的**憑證取得 runner 註冊 token 交給 VM；VM 檢查允許清單後讓 runner 上線 24 小時。開窗不另走核准，取得 token 本身就是授權動作；接近到期時提醒延長；除了固定 24 小時之外不設上限。
3. **csarc-devops 只管 VM（載具），對下游 repo 沒有任何權限；VM 是登記的權威。**未登記、已撤銷或已到期的 repo 開不了窗，因為 VM 拒絕接受註冊 token、不讓 runner 上線。模板**不跨 repo 讀取** csarc-devops：登記 PR 只需要連結 csarc-devops 的 Issue，雙邊 Issue 與雙方核准保留為人工流程（2026-10-25，取代草稿中「模板唯讀讀取 csarc-devops 核准留言」的做法）。
4. **只有 DEV 與 UAT。**DEV＝進 `dev/m*`、`dev/i*` 的 PR；UAT＝進 `main` 的 PR（promotion、standalone、hotfix，也就是物化 stable 版本的地方）。不設 PRD：release 只發布已驗證的候選。
5. **窗外一律 fail closed，不改用其他模式。**
6. **設定依可見性拆成兩個，新專案的 private 預設改為 `self-hosted`。**`verification_mode_private`（`self-hosted`｜`hosted`｜`local`，預設 `self-hosted`）、`verification_mode_public`（`hosted`｜`local`，預設 `hosted`，`self-hosted` 被拒）。實際模式依 repository **當下**的可見性決定。這部分取代 #908「新專案預設 `local`」。既有專案在登記後以 governance-switch PR 改用，絕不自動切換。模板 repo 是 public，自然維持 `hosted`。
7. **登記完成前 fail closed 並附登記指引。**
8. **可見性安全以 VM 為最後防線，**PR 無法改變；repo 轉成 public 後，VM 立即停止 runner 並刪除該 repo 的資料。
9. **log 隨 repo 公開而公開，**因此限制 log 內容、建議縮短保存期限，並提供 `retire` 指令在公開前清除。
10. **90 天未開窗的登記由 VM 端自動到期。**
11. **列為未來研究：**release 後的部署驗收環境、常駐的產品測試服務。
12. **觸發者允許清單（2026-10-25）。**登記時另列可以觸發 `csarc-verify.yml` 的 GitHub 帳號；清單存在 VM 端，VM 的 hook 拒絕清單外的人觸發的 job。不在清單上的寫入者即使能推分支，也不能在 VM 上執行程式碼。
13. **每個 job 一個新容器（2026-10-25）。**使用固定版本的工具鏈 image，依（repo, 環境）分開快取 volume；不掛 docker socket、不用 privileged、不用 host network、不能存取 metadata endpoint。
14. **#1264 只屬於模板 repository（2026-10-25）。**Dependabot 落後 main 的重新驗證不下發到 `template/`；它的 lifecycle 規則與模式無關。

撰寫本草稿時已查證的限制（2026-10-24，base `2035b0d`）：

1. **public repo 不應使用 self-hosted runner。**任何人都能開 PR 在機器上執行程式碼（[Security hardening：Hardening for self-hosted runners](https://docs.github.com/en/actions/reference/security/secure-use#hardening-for-self-hosted-runners)）。
2. **GitHub Free 的 private repo 不能使用 Ruleset 或 branch protection。**rules API 回應「Upgrade to GitHub Pro or make this repository public」（[#1210](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1210)）。所以和 `local` 一樣，self-hosted 的合併規則**由 lifecycle 指令執行，不由 GitHub 強制**：有寫入權限的人仍可以在 GitHub UI 或以 `gh pr merge` 直接合併，這種合併在 merge trace 稽核中顯示為 `untraced`。
3. **組織是 GitHub Free 方案。**只有 default runner group；組織層級 runner 放在 default group，組織內每個 private repo 都能用 label 派工上去（[Managing access to self-hosted runners using groups](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access)）。repository 層級 runner 只會收到該 repo 的 job。
4. **註冊 token 只能由 repo 管理員取得，一小時內有效**（[REST：Create a registration token for a repository](https://docs.github.com/en/rest/actions/self-hosted-runners#create-a-registration-token-for-a-repository)）。移除 repository runner 也需要管理員；離線超過 14 天的 runner 會被自動移除（[Removing self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/remove-runners)）。
5. **repository runner 信任所有寫入者。**窗口期間，任何有寫入權限的人都能從任一分支推一個指定該 runner labels 的 workflow，讓它在 VM 上執行。這是 GitHub 的模型，模板無法在 GitHub 端阻止。本 ADR 以 VM 的 hook 縮小信任邊界：只接受 `main`／`dev/*` 上的 `csarc-verify.yml`，而且觸發者必須在登記的觸發者允許清單裡（D6 L4、D7）。合併仍沒有 Ruleset 保護（限制 2），寫入者可以不經 lifecycle 直接合併，由 merge trace 稽核發現。
6. **csarc-devops 是 private repo。**下游的 `GITHUB_TOKEN` 讀不到它的 Issue；跨 repo 讀取需要額外的憑證或權限。本 ADR 因此不讓模板讀取 csarc-devops，登記的強制交給 VM。
7. **現有證據讀取只認 GitHub-hosted runner。**`scripts/verification_evidence.py` 要求 `ubuntu-latest` 與 `GitHub Actions` group，並拒絕 `self-hosted` label；merge trace 的 `CSARC-Trust` 只有 `github-hosted` 與 `self-attested-local`。`local` 模式不 render 這個 reader。
8. **trusted executor 不是 sandbox**（[trusted-base-gate](trusted-base-gate.md)）。同一個 runner 連續接多個 job 時，前一個 job 可以留下影響後一個 job 的狀態；本 ADR 以每個 job 一個新容器處理（D8）。
9. **repo 轉成 public 後，過去的 Actions log 也一起公開。**
10. **payload：**`scripts/generated_payload.py` 在 `2035b0d` 實測，solo-default（`local`）為 640,215／784,000 B、87／92 個檔案、寫入 workflow 0、agent 文件 token 12,829／13,500；hosted 距總閘 2,828 B。#1231 規定預算只能下調，上調要由擁有者核准。
11. **[先盤點、再動作](dry-run-inventory-before-action.md) 適用**於登記、開窗、派工與清除。
12. **`container` 模組需要 Docker daemon（#1281 補記 [#554](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/554)）。**#554（2026-09-03）決定的 Docker 能力包：`container: true` 產生可選的 `Dockerfile` 與 `docker-compose.yml`，並加上 build-and-scan 驗證。hosted 模式由 `docker-build-scan.yml` 在 GitHub runner 上執行；其他模式由 `verify` 的 `verify_container` 執行 `docker compose config`、`docker build` 與 Trivy 掃描。image 只在本機建置，不推送，不登入 registry，也不取得 registry 權限或 secret（[selective-ci-automation-adoption](selective-ci-automation-adoption.md) 的邊界）。#554 當時只有 `local` 與 `hosted`，兩者都有 Docker daemon，所以沒有另寫 ADR。self-hosted 的 job 容器禁止 docker socket（D8 第 4 點），所以啟用這個模組的 repo 目前不能在 self-hosted 模式驗證（D8 第 7 點）。

不在本 ADR 範圍：VM 的建置與維運、csarc-devops 允許清單本身的實作、產品部署管線（CD）、修改下游 repo 設定，以及未來研究項目。

## 決定

以下 D1–D12 是提交擁有者核准的設計。先前各版的待決問題已於 2026-10-25 全部決定，結果列在「已決（2026-10-25）」。

### D1. 定位：local 的治理加上 VM 的驗證（選項 Y）

| 面向 | `local` | `self-hosted` | `hosted` |
| --- | --- | --- | --- |
| PR policy、review 判定、合併、metadata 寫入 | 操作者指令（`pr_lifecycle.py`、Issue wrapper） | 同 `local` | GitHub workflow（`pr-policy`、`pr-review`、lifecycle workflow） |
| release 發布 | 指令（`publish-release`） | 同 `local` | `release.yml` |
| 驗證在哪執行 | 操作者電腦 | VM 上的 repository runner，由唯讀 workflow 執行 | GitHub-hosted runner |
| 合併需要的證據 | 本機證明（Git metadata） | VM 執行紀錄（GitHub 記錄） | hosted `verify` check |
| 帶寫入 token 的 workflow | 無 | **無** | 有 |
| Ruleset／required checks | 停用（Free private 本來就不能用） | 同 `local` | 啟用 |

- **render：**`self-hosted` 以 `local` 的 render 為基礎，只多三樣：一個唯讀驗證 workflow（暫名 `.github/workflows/csarc-verify.yml`）、lifecycle 讀取 VM 證據的 sibling，以及 D2 的設定。開窗、延長、關窗、派工、狀態查詢與清除都在 `csarc` CLI，不進生成專案。不 render 任何 hosted workflow。
- **合併的強制方式與 `local` 相同：**由 lifecycle 指令在合併前重新讀取 metadata、review、lease 與證據，再以既有路線合併（Free private 為 single-writer 或人工，見 #1210）；沒有 Ruleset 擋住 GitHub UI 的直接合併，稽核以 merge trace 發現。
- **比 `local` 強的地方只在證據：**驗證由機器執行、由 GitHub 記錄，不是操作者自我聲明。
- **VM 只執行驗證**，只拿唯讀 job token、不帶 secret、`persist-credentials: false`。

### D2. 設定、預設、實際模式與 render

| 設定 | 可用值 | 新專案預設 | 規則 |
| --- | --- | --- | --- |
| `verification_mode_private` | `self-hosted`、`hosted`、`local` | `self-hosted` | repo 為 private 時使用 |
| `verification_mode_public` | `hosted`、`local` | `hosted` | repo 為 public 時使用；設成 `self-hosted` 時設定驗證失敗 |

- **實際模式**依 repository 當下的可見性決定。派工時 `csarc` 讀取 repo 的 `private` 欄位，VM 的 hook 讀 event payload；合併時 lifecycle 以操作者的登入讀取 `private` 欄位，讀不到就 fail closed（Q7）。設定本身只從 trusted base 讀取（#1069）。
- **證據記錄使用的模式**；合併時與當下實際模式不同即無效。例如 PR 驗證後 repo 轉成 public，VM 證據要在 public 模式重做。
- **依可見性 render（Q2）：**只 render 當下實際模式需要的檔案；private 預設專案因此不帶任何 hosted workflow。可見性改變時必須重新 render：轉 public 的步驟（`retire`，D9）一併以 public 模式重新 render；轉回 private 時以 `csarc update` 重新 render。lifecycle 發現實際模式與已 render 的檔案不一致時 fail closed，訊息要求重新 render。另一個做法是同時 render 兩種模式，但 public 預設是 `hosted`，等於讓 private 專案也帶著全部 hosted workflow，與選項 Y 相反。
- **新專案預設改變，部分取代 #908。**#908 的「新專案預設 `local`」由本 ADR 取代：新專案 private 預設 `self-hosted`、public 預設 `hosted`。#908 的其餘內容保留：`local` 模式的行為，以及既有專案沒有欄位時維持 `hosted`。`docs/ci-policy.md` 的 #908 一節由 #1272 更新。
- **Migration：**既有 `verification_mode: <值>` 依原值同時寫入兩個新設定，行為不變。依 #1069 決定 8，trusted base 的 reader 先支援新 schema，writer 才切換；migration 在外部 pinned CLI 執行。
- **既有專案改用：**絕不自動切換。`csarc update` 報告在 private repo 建議改用並列出登記步驟；登記（D7）後，以 governance-switch PR 修改 `verification_mode_private`。
- **登記完成前 fail closed：**新專案預設 `self-hosted` 但還沒登記時，lifecycle 找不到可用的 VM 證據，合併被擋，訊息說明「尚未登記」並列出登記步驟；`csarc init` 建立專案時就印出同一份指引。不改用 hosted 或 local（離開 self-hosted 的出口見 D10、Q1）。

### D3. 驗證 workflow 與派工

GitHub 只做排程；派工由操作者的指令發起，不設 GitHub-hosted 的 route job：

1. 操作者執行 `csarc self-hosted verify --pr <N>`（CLI）。它先印出盤點：repo 與可見性、PR 的 head repo 與 head SHA、目標分支、預期環境（D5）、窗口剩餘時間。repo 是 public、PR 來自 fork、環境未登記、沒有窗口或窗口剩不到 30 分鐘時停止。
2. 指令以 `workflow_dispatch` 觸發**目標分支上的** `csarc-verify.yml`，輸入 PR 編號、head SHA、環境與窗口結束時間。觸發需要寫入權限，用的是操作者自己的登入。
3. workflow 的權限只有 `contents: read`、`pull-requests: read`、`actions: read`，沒有 secret。`runs-on` 為 `self-hosted`、VM label 與 `csarc-env-<環境>`。
4. 第一個 step 來自目標分支（trusted base）的定義，在 checkout candidate 之前以唯讀 token 重新確認：PR 的 head repo 等於本 repo、head SHA 等於輸入、目標分支推出的環境等於輸入、repo 是 private。任一項不符即失敗。
5. 接著沿用 trusted executor（#1086、#1069）：由 base 決定 tier 與 scopes，對 exact candidate tree 執行 `verify`／`verify-fast`；execution step 名稱帶上 candidate head、tree、tier、scopes、`mode=self-hosted`、`environment=`、`window=`。
6. 窗口剩不到 2 小時時，workflow 在輸出與 job summary 印出 `WARNING:`（D7）。
7. 30 分鐘的派工門檻也由第一個 step 執行（#1320），不只在 CLI：直接 `gh workflow run csarc-verify.yml` 一樣要通過。`window_end` 缺少、格式不對、超過 24 小時之後，或以 runner 的時鐘計算剩不到 30 分鐘（等於 job 的 `timeout-minutes`）時失敗。這是操作者宣告的結束時間，不是 VM 證明的；操作者寫錯時，VM 仍在真正的到期時間停止 runner，job 依 D10「窗口在 job 執行中到期」失敗，不會產生證據。由 VM 證明結束時間需要 csarc-devops 的 C12。

沒有自動觸發（不使用 `push`、`pull_request`、`pull_request_target`），所以窗外不會有 job 排隊，外部 fork 的 PR 也不會自動觸發任何執行。

### D4. 信任模型與證據綁定

| 項目 | `local` | `self-hosted` | `hosted` |
| --- | --- | --- | --- |
| 可用於 | private、public | 只有 private | private、public |
| 驗證由誰發起 | 操作者 | 操作者（`workflow_dispatch`） | GitHub 事件 |
| 在哪執行 | 操作者電腦 | 開窗註冊的 repository runner；每次開窗或延長後最多 24 小時 | GitHub-hosted VM，每個 job 全新 |
| workflow 與 gate 來源 | trusted base（#1069） | 目標分支（trusted base）上的 workflow 定義＋trusted executor | trusted base（`pull_request_target`、#1086） |
| 結果由誰記錄 | 操作者寫入 Git metadata | GitHub Actions run 與 Jobs API | GitHub Check Runs、Jobs API |
| 合併規則由誰執行 | lifecycle 指令 | lifecycle 指令 | Ruleset＋lifecycle |
| 能證明 | 某人聲稱在 exact head 跑過指定 tier | 這個 repo 的登記 runner，在預期環境、以 base 的 workflow 對 exact tree 執行指定 command 並成功，紀錄由 GitHub 保存 | GitHub 在乾淨 VM 上以 base 的 workflow 對 exact tree 執行並成功 |
| 不能證明 | 結果未被偽造；環境 | VM 主機與工具鏈 image 未被竄改；同一（repo, 環境）的快取 volume 未被先前的 job 汙染；合併沒有繞過 lifecycle | candidate 測試碼本身無惡意 |
| 信任前提 | 操作者 | 觸發者允許清單上的帳號＋開窗的管理員＋csarc-devops 的登記與隔離（VM 是登記的權威） | GitHub |
| `CSARC-Trust` | `self-attested-local` | `self-hosted-registered`（新值） | `github-hosted` |

**證據綁定。**lifecycle 合併前以操作者的登入讀取 Actions run 與 Jobs API，全部符合才接受：

1. run 的 `event` 是 `workflow_dispatch`、`path` 是 `.github/workflows/csarc-verify.yml`、`head_branch` 是 PR 的目標分支、`head_sha` 等於 lease 記錄的 trusted base SHA。這保證執行的是 base 的 workflow 定義，不是某個分支改過的版本。
2. 由 GitHub 記錄的 self-hosted 執行：job 的 labels 含 `self-hosted`、由登記的 `self_hosted_runner` 推導出的 VM label 與預期環境 label；`runner_name` 符合由同一設定推導出的窗口命名（不含主機名稱）；`runner_group_name` 為 `Default`。run 屬於本 repo。
3. execution step 宣告的 candidate head 等於 PR 當下的 exact head，tree 等於該 head 的 Git tree；tier 與 scopes 至少是 trusted router 對這張 PR 要求的強度；`mode`、`environment`、`window` 與上面一致。容器 image digest 由 VM 宣告，只記錄、不作為信任依據。
4. run、job 與 execution step 都是 `success`；完成時間在 24 小時內（[verification-evidence-freshness](verification-evidence-freshness.md) 的同一個判定）。
5. 證據的模式等於合併當下的實際模式。登記是否被撤銷或到期不由 lifecycle 判斷：VM 是登記的權威，撤銷或到期後 VM 不再接受開窗，也就不會產生新的證據（D7、D10）。
6. canonical merge evidence 記錄 run URL、run 的 `actor` 與 `triggering_actor`、runner、環境、窗口與模式，`CSARC-Trust: self-hosted-registered`。窗口記為 `window_source: operator-declared`：第一個 step 檢查過格式與剩餘時間，但結束時間來自派工輸入，不是 VM（#1320）。窗口結束不會讓窗口內完成的證據失效。

### D5. 環境對應：DEV 與 UAT，依目標分支決定

| 目標分支 | 典型 PR | 環境 |
| --- | --- | --- |
| `dev/m*`、`dev/i*` | Milestone 的 work PR、main→delivery 同步、checkpoint terminal（物化 beta） | `dev` |
| `main` | promotion、standalone、hotfix、release-recovery、`release/v*` guided candidate（物化 stable）；Dependabot PR | `uat` |

- 環境與 tier 互相獨立；tier 仍由 trusted router 與 channel floor 決定。
- 預期環境未登記或沒有有效窗口時 fail closed，不改用另一個環境或其他模式。
- **不設 PRD。**`publish-release` 只發布已驗證的候選，照 `local` 模式的發布規則執行；它不重新驗證。
- 不使用 Milestone 的 repo 可以只登記 `uat`。

### D6. 只限登記的 private repo、排除 fork：六層防護

任何一層單獨失效，其他層仍然擋得住。VM 端的兩層（L4、L5）設定在 VM 上、不在 repo 裡，是 PR 無法改變的最後防線。

| 層 | 誰負責 | 擋下什麼 | 控制 |
| --- | --- | --- | --- |
| L1 GitHub 註冊 | repo 管理員（開窗） | 其他 repo | 只用 repository 層級 runner，註冊 token 由該 repo 的管理員取得；未登記的 repo 拿不到 VM 的配合，沒開窗就沒有 runner。 |
| L2 開窗 | `csarc` CLI（#1271）＋VM | public、未登記、已撤銷、已到期 | `open` 讀到 repo 是 public 就拒絕；VM 是登記的權威，允許清單上沒有這個 repo（未登記、撤銷、到期）就拒絕註冊 runner。 |
| L3 派工 | `csarc` CLI＋workflow 第一個 step（#1269） | public、fork、窗外、未登記 | 派工指令先檢查；workflow 在 checkout candidate 前以 base 的定義再檢查一次（D3）。沒有自動觸發，fork PR 不會自己產生執行。 |
| L4 VM job-started hook | csarc-devops（C6） | public、非預期的 workflow、清單外的觸發者 | runner 的 job-started hook（設定在 VM 上）在任何 step 前讀 event payload、`GITHUB_WORKFLOW_REF`、`GITHUB_ACTOR` 與 `GITHUB_TRIGGERING_ACTOR`：repo 不是 private、事件不是 `workflow_dispatch`、workflow 不是 `main` 或 `dev/*` 上的 `csarc-verify.yml`、或任一 actor 不在觸發者允許清單裡，就以非 0 結束。不在清單上的寫入者因此不能在 VM 上執行程式碼（限制 5）。 |
| L5 VM 定期檢查 | csarc-devops（C7） | 窗口期間轉成 public | 窗口期間定期以不帶憑證的 GitHub API 查 repo，讀得到就是 public：立即停止 runner，刪除該 repo 在 VM 上的工作目錄與快取，並在 csarc-devops 開 Issue 記錄。 |
| L6 lifecycle | 模板（#1269） | 合併當下為 public、fork、錯誤的 run | 合併時重新判斷實際模式，repo 已是 public 時 VM 證據無效；另外依 D4 逐項比對 repo、workflow 路徑、runner、環境、窗口與 exact head。 |

Free private repo 沒有 Ruleset（限制 2），所以 L6 只約束經由 lifecycle 的合併；寫入者在 GitHub UI 直接合併不受 L6 約束，會在 merge trace 稽核中顯示為 `untraced`，這一點與 `local` 相同。

### D7. 登記契約、開窗與到期

**一次性登記（雙邊 Issue，人工核准）。**VM 是登記的權威；模板不跨 repo 讀取 csarc-devops（2026-10-25）。

| 設定 | 型別與預設 | 意義 |
| --- | --- | --- |
| `self_hosted_runner` | mapping；登記後必填：`id`（VM ID）、`registration`（csarc-devops 登記 Issue 的完整 URL） | 指向哪台 VM，以及承載登記的 csarc-devops Issue；`id` 用來推導 runner label 與命名（C2），lifecycle 以它比對證據。尚未登記時留空，設定驗證接受這個狀態 |
| `self_hosted_environments` | `dev`、`uat` 的非空子集合 | 這個 repo 登記了哪些環境 |
| `self_hosted_services` | 本 Milestone 不加入 | 常駐產品測試服務列為未來研究 |

csarc-devops 端維護允許清單，每筆至少記錄：repo 全名、VM `id`、環境、**觸發者允許清單**（可以觸發 `csarc-verify.yml` 的 GitHub 帳號）、兩邊的 Issue、核准時間、最後一次開窗時間。觸發者允許清單只存在 VM 端，不寫進 repo（C10）。

登記變更（開始使用、增減環境、更換 VM、修改觸發者允許清單、撤銷）的流程：

1. Repo 端與 csarc-devops 各開一張 Issue，互相引用完整 URL（雙向連結）。這是人工流程。
2. 兩邊各自依自己的規則核准：repo 端沿用既有核准（Milestone tracker 或無 Milestone Issue 的核准）；csarc-devops 端由它的核准者決定（C5）。
3. csarc-devops 依核准更新允許清單與觸發者允許清單。VM 只依這份清單接受註冊；未登記、撤銷或到期的 repo 開不了窗。
4. repo 端改動 `self_hosted_*` 或 `verification_mode_private` 的 PR 帶 `governance-switch` label（#1069 既有 route），並在 `self_hosted_runner.registration` 寫入 csarc-devops Issue 的 URL。lifecycle 只檢查 URL 的格式（指向 csarc-devops repo 的 Issue），**不讀取它的內容**。
5. 登記指引同時建議把 repo 的 Actions log 保存期限縮短為 7 天（D8）；修改 repo 設定由管理員自己執行。

這取代草稿中的擁有者決定 5（「雙邊 Issue 互相連結、雙方核准」，並由模板唯讀讀取 csarc-devops 的核准留言）：雙邊 Issue 與雙方核准保留為人工流程，只拿掉自動的跨 repo 讀取。理由：讀取需要下游管理員擁有 csarc-devops 的權限，或在本機保存另一份憑證；而 VM 本來就必須核對允許清單，由它強制登記比較少一份權限。

退出 self-hosted 只需要 repo 端核准，並通知 csarc-devops 更新允許清單。

**為何 csarc-devops 不持有下游權限。**repository runner 的管理需要 Administration 寫入權限，而這個權限同時能改 Ruleset 與 branch protection、管理 collaborator、修改 Actions 設定，甚至刪除 repo（[Permissions required for GitHub Apps](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps)）。交給管理 VM 的團隊，等於讓載具可以關掉下游的全部治理。

**開窗（每次使用，不另核准）：**`csarc self-hosted open --env dev|uat`

1. 唯讀盤點：repo 與可見性、VM 與環境、窗口結束時間（固定 24 小時）、窗口內會執行什麼（只有 `csarc-verify.yml`、唯讀 token、不帶 secret）、既有窗口與 runner。public、尚未登記或任一項不符就停止。
2. 以管理員自己的 `gh` 登入取得註冊 token。管理員的 GitHub 憑證不離開本機、不寫入檔案；交給 VM 的只有這個一小時內有效的 token。
3. 經 csarc-devops 指定的管道交給 VM（C1）。VM 核對允許清單，以通用命名註冊**一個** runner，記錄開始與結束時間，更新最後開窗時間。
4. 讀回 runner 清單，確認只有一個符合命名的線上 runner；出現預期之外的 runner 時移除全部並以錯誤結束（防註冊 token 外洩）。

**窗口紀錄放在 VM 端。**選項 Y 沒有需要事先判斷窗口的 GitHub-hosted job，因此不再寫 repository variable：VM 的紀錄是唯一來源，`csarc self-hosted status` 經同一管道讀取，派工時把結束時間當作 workflow 輸入傳入，用來印提醒與執行派工門檻（D3 第 7 點），不是信任依據；證據把它標成 `window_source: operator-declared`。

**剩餘時間、延長與關窗：**

- `csarc self-hosted status [--env]`：唯讀顯示 runner、開始與結束時間、剩餘時間、登記是否到期，以及 D9 的公開警告。
- **最後 2 小時：**`verify` 指令與 `csarc-verify.yml` 在輸出與 job summary 各印一行，依寫作指引的句型，例如 `WARNING: Self-hosted dev verification: the window ends at 2026-10-25T09:00Z (1h40m left). Run 'csarc self-hosted extend --env dev' before it closes.`。
- **剩不到 30 分鐘（job timeout）：**`verify` 指令不派工，要求先延長；直接派工時由 workflow 第一個 step 拒絕（#1320）。
- **延長：**`csarc self-hosted extend --env`（窗口有效時重跑 `open` 等同延長）。先印盤點，再以管理員憑證確認同一 runner 在線，要求 VM 把停止時間改為「現在＋24 小時」。不取得新 token、不註冊第二個 runner，沒有空窗；不累加。過期後只能重新 `open`。
- **關窗：**`csarc self-hosted close --env` 以管理員憑證刪除 runner。不執行時，VM 到期停止 runner 並刪除 runner 憑證檔；離線 runner 不會再收到 job，GitHub 也會在 14 天後自動移除。

**24 小時、不設上限的取捨：**窗口長度與證據期限一致，一個工作日用一個窗口即可，忘了關也會到期。不設上限代表 repo 可以每天延長、實際上接近常駐，同一 runner 跨 job 共用狀態的時間也跟著拉長；擁有者接受，因為每次延長都是管理員明確的動作並留下紀錄。

**登記到期：**連續 90 天沒有開窗，VM 從允許清單移除該 repo、刪除它的快取與資料，並在 csarc-devops 開 Issue 記錄；之後 `open` 回應 registration expired，要求重新登記。封存 repo 的偵測需要 Metadata 唯讀憑證，目前不做。

### D8. 窗口內的隔離與 log 衛生

一個窗口是一個非 ephemeral 的 repository runner。GitHub 建議 ephemeral 或 just-in-time runner（[Self-hosted runners reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)），但每個 job 都要一個新的註冊 token，只能由管理員取得；VM 不持有下游權限，做不到。所以隔離改在 runner 之下做：**每個 job 在一個新的容器裡執行**（擁有者 2026-10-25 決定）。

1. **每個 job 一個新容器，job 結束即丟棄。**由 VM 端的 runner 設定（例如 runner 的 container hook）強制，repo 的 workflow 不能選擇或關閉。本 ADR 採用「每個 job 丟棄」，不採用「窗口結束才丟棄」：後者讓同一窗口內的 job 共用檔案系統與背景程序，正是限制 8 的風險。若 csarc-devops 初期只能做到窗口結束才丟棄，要在 csarc-devops Issue 記錄為有期限的過渡，並由擁有者另行同意。
2. **固定版本的工具鏈 image。**依語言 profile 建置，以 digest 固定；建置、固定與更新節奏由 csarc-devops 負責（C9）。容器內的工具鏈因此每個 job 都相同，job 無法改動。
3. **快取 volume 依（repo, 環境）分開。**以 lockfile digest 分 key，不跨 repo、不跨環境共用。UAT 的快取在窗口結束時刪除；DEV 的快取保留到登記到期（90 天）或 `retire` 為止。快取是唯一跨 job 留存的狀態，D4 因此把「快取未被汙染」列為不能證明的項目。
4. **容器權限。**不掛 docker socket、不用 privileged、不用 host network、不能存取雲端 metadata endpoint；以非 root 帳號執行。每個（repo, 環境）在 VM 上另有專用 OS 帳號與目錄，彼此不可讀寫（C3）。
5. **Secrets。**VM 與容器內都不放長期 secret；job 只有唯讀 token；註冊 token 用完即丟。
6. **log 衛生。**job log 在 repo 公開後會被看到，所以 runner 名稱、容器內工作目錄（例如 `/runner/_work`）與 hook 輸出都不含主機名稱、內部網域、帳號或位址。登記指引建議 Actions log 保存 7 天。VM 自己的 runner log 轉存到 csarc-devops 的外部儲存供事件調查（C4）。
7. **job 容器內隔離的 Docker daemon（#1281，擁有者 2026-10-26 決定）。**為了讓 `container` 模組在 self-hosted 模式驗證，允許 VM 在每個 job 的容器內提供一個只屬於該 job 的 Docker daemon，例如 sysbox runtime 或 rootless Docker。daemon 隨 job 容器建立與丟棄，模板的驗證腳本不變。以下做法一律不允許：掛載主機的 docker socket、privileged 容器、host network、讓 job 看到主機或其他 job 的 daemon、image 或 volume，以及在 job 結束後保留 daemon 狀態。csarc-devops 確認可行（C11）之前，模板在設定階段拒絕 `container: true` 加上 self-hosted 的組合，訊息說明這一點並建議改用 `local` 或 `hosted`（SPEC-011 §9）；確認後以後續 Issue 移除這個限制。

### D9. 公開前清除（`retire`）與事後偵測

**公開前必須執行 `csarc self-hosted retire`。**這個動作不可回復，只由管理員以自己的憑證執行：

1. 預設只做唯讀盤點：`csarc-verify.yml` 的所有 run、它們的 artifact 與 Actions cache、目前的 runner。
2. `--apply` 依盤點刪除這些 run、artifact 與 cache，移除 runner，並建立一張 governance-switch PR：把 `verification_mode_private` 改離 `self-hosted`，並以 public 模式重新 render（D2）。設定變更一律經 PR，不由指令直接改 trusted 設定。同時產生給 csarc-devops 的退出通知內容。
3. 輸出刪除結果；任何一項失敗都以非 0 結束，訊息說明哪些 log 仍會在公開後被看到。

**事後偵測（沒有先 `retire` 就公開）：**

- VM 的定期檢查（L5）停止 runner、刪除資料，並在 csarc-devops 開 Issue 記錄。VM 對下游沒有權限，不在下游開 Issue。
- 模板端不依賴讀取 csarc-devops：`csarc self-hosted status`、`csarc update` 報告與 lifecycle 只要發現 repo 是 public，且 `verification_mode_private` 仍是 `self-hosted`，或仍有 `csarc-verify.yml` 的 run，就印出 `WARNING:` 要求執行 `retire`。條件不看 `CSARC-Trust: self-hosted-registered` 的 merge trace：trace 永遠留在 Git 歷史中，正確執行 `retire` 之後仍會一直警告（擁有者 2026-10-26 核准這項修訂，#1272）。
- 合併時 L6 讓 VM 證據失效；已 render 的檔案與 public 模式不一致時，lifecycle 要求重新 render。

### D10. 失效、撤銷與降級

原則：**不靜默改用其他模式。**無法在登記環境的有效窗口內取得 VM 證據時，lifecycle 拒絕合併，訊息說明原因與下一步。

| 情況 | 行為 | 下一步（訊息內容） |
| --- | --- | --- |
| 尚未登記（新專案預設） | `verify` 指令與 lifecycle 拒絕 | 依 D7 登記；指引見 `csarc self-hosted status` |
| 登記到期（90 天未開窗） | `open` 回應 registration expired | 依 D7 重新登記 |
| 沒有開窗、窗口過期或剩不到 30 分鐘 | `verify` 指令不派工；直接派工時 workflow 第一個 step 失敗 | 請管理員 `open` 或 `extend`，再執行 `verify` |
| 窗口剩不到 2 小時 | 照常驗證並印出 `WARNING:` | 執行 `csarc self-hosted extend --env <環境>` |
| runner 離線（VM 故障、提早停止） | 已派工的 job 停在 queued，24 小時後由 GitHub 判失敗；lifecycle 沒有可用證據 | 執行 `status`；請 csarc-devops 恢復 VM，或關窗後重新開窗 |
| 窗口在 job 執行中到期 | job 失敗 | 重新開窗後再執行 `verify` |
| VM 拒絕註冊 | `open` 以錯誤結束 | 確認登記已合併，並請 csarc-devops 更新允許清單 |
| 出現預期之外的 runner | `open` 移除全部並以錯誤結束 | 視為註冊 token 外洩，通知 csarc-devops 並檢查 repo 稽核紀錄 |
| repo 轉成 public | L4、L5 停止 VM 執行並刪除資料；L6 讓 VM 證據失效 | 執行 `retire`，在 public 模式重新驗證 |
| 登記被撤銷 | VM 從允許清單移除並停止該 repo 的 runner，之後開不了窗；lifecycle 不讀 csarc-devops，撤銷前完成的證據仍依 24 小時期限有效 | 依 D7 重新登記，或開 PR 退出 self-hosted。撤銷不會讓已完成的證據失效，這是不跨 repo 讀取的代價 |
| 觸發者不在允許清單 | L4 hook 讓 job 失敗，不執行任何 step | 由清單上的維護者執行 `verify`，或依 D7 修改清單 |
| 證據的 run、模式、runner、環境、窗口或 head 不符 | 拒絕 | 在正確環境重新 `verify` |
| 懷疑 VM 被入侵 | csarc-devops 停止該 VM 上所有 runner；以 `merge_trace.py audit` 列出事件期間 `CSARC-Trust: self-hosted-registered` 且 runner 屬於該 VM 的合併，逐一重新驗證 | 依 `docs/security-response.md` 處理；恢復前必須重建 VM |

**離開 self-hosted 的出口（Q1，已決）。**trusted base 決定模式，所以「把 `verification_mode_private` 改離 `self-hosted`」的 PR 本身仍要求 VM 證據；新專案尚未登記或 VM 長期無法使用時會卡住。選項 Y 的治理已經是本機指令，因此只為「只改模式設定、方向是離開 self-hosted」的 governance-switch PR 接受 `local` 的本機證明，merge trace 記為 `self-attested-local` 並註明原因。不需要任何 GitHub-hosted 執行。

### D11. 先盤點、再動作

| 時點 | 盤點內容 | 之後的動作 |
| --- | --- | --- |
| 登記與變更（#1270） | repo 端 Issue 與 `registration` URL、設定的逐項差異（舊值→新值）；不讀 csarc-devops 的內容 | URL 格式正確、PR 帶 `governance-switch` 才允許合併 |
| 開窗、延長、關窗（#1271） | repo 與可見性、VM、環境、新舊結束時間、窗口內會執行的 workflow 與權限、既有 runner | 印出後才取得 token、延長或刪除 |
| 派工（#1269、#1271） | 可見性與實際模式、head repo 與 head SHA、目標分支、預期環境、窗口剩餘時間 | 印出後才 `workflow_dispatch` |
| 清除（`retire`） | 要刪除的 run、artifact、cache、runner，與要修改的設定 | 預設只盤點；`--apply` 才刪除並建立 PR |

盤點只讀資料：設定以 trusted base 的 `csarc_config.py` 讀取，GitHub API 與 VM 的回應都視為資料，不執行任何下載來的程式碼。

### D12. Ownership、驗證與後續 Issue 的範圍

| 項目 | Issue | 驗證 |
| --- | --- | --- |
| 兩個模式設定、預設值、實際模式、依可見性 render、migration、「尚未登記」狀態 | #1268 | 三種模式與兩種可見性的 root／template 回歸測試；migration 不改變既有專案；public 設成 `self-hosted` 被拒 |
| `csarc-verify.yml`、workflow 第一個 step 的檢查、lifecycle 讀取 VM 證據、合併時的可見性與模式判斷 | #1269 | fork、public、未登記、錯誤分支上的 workflow、錯誤 runner、模式不符、head 改變的拒絕測試；`check` 能重查並顯示 runner、環境與窗口 |
| 登記 PR 的檢查（在本機 lifecycle）：`registration` URL 格式與 `governance-switch` | #1270 | URL 指向 csarc-devops 的 Issue 才通過；缺 URL、URL 指向其他 repo、缺 label 都擋下；確認不發出任何 csarc-devops 讀取 |
| `open`、`extend`、`close`、`status`、`verify`、`retire`、工具鏈契約 | #1271 | 盤點與失敗路徑的 CLI 測試；延長不註冊第二個 runner；`retire` 預設不刪除；不寫入管理員憑證 |
| Dependabot 落後 main 的重新驗證（只在模板 repository） | #1264 | 依 #1264 AC5，只在 root；不下發到 `template/` |
| 文件、登記指引、手冊 r6、下游通知、#908 一節 | #1272 | 文件一致性紀錄 |
| C11 確認前拒絕 `container: true` 加上 self-hosted（D8 第 7 點） | #1281 | reader、`csarc update`／`init` 與 lifecycle 的 root／template 回歸測試；`verification_mode_public` 不受影響 |
| VM、允許清單與觸發者允許清單、交付管道、hook、定期檢查、90 天到期、容器與工具鏈 image | csarc-devops 對應 Issue | csarc-devops 自己的驗收 |

**#1264 的範圍（Q10，已決）。**#1264（Dependabot PR 落後 main 時改為重新驗證）只屬於模板 repository，不下發到 `template/`；它的 lifecycle 規則與模式無關。下游的 self-hosted 專案仍由操作者在 UAT 窗口以 `verify` 驗證 Dependabot PR、以指令合併。下游 fixture 因此不需要為 #1264 保留空間。#1284 在逐位元組配對的 `check-trusted-verification` 加了一段不作用的 hook：只有旁邊有 `dependabot_reverify.py`（只在 root）時才生效，下游行為不變，產生的 payload 約多 561 B。

擁有者核准後，本 ADR 隨 #1266 的 PR 合併並改為 `Accepted`；之後實作與本 ADR 不同的地方，在該實作 PR 修訂本 ADR。#1264、#1268、#1269、#1270、#1271、#1272 的完成條件依本版改寫（Q9，已授權）。

## Payload 影響估計（交給 #1267）

量測基準：`2035b0d`。數字是 canonical bytes 的粗估（±50%）。前提：依可見性 render（D2、Q2）；所有窗口與派工指令都在 `csarc` CLI，不進生成專案；模板不跨 repo 讀取 csarc-devops；#1264 不下發。

**新的預設 render（private `self-hosted`）＝目前的 solo-local 加上：**

| 項目 | 增量 | 所屬分項 |
| --- | --- | --- |
| 兩個模式設定、實際模式、「尚未登記」狀態、governance-switch 放寬順序（#1268；所有 fixture 都有） | +2–3 KB | settings 與 drift |
| `csarc-verify.yml`（#1269，唯讀、`workflow_dispatch`） | +3–5 KB，1 個檔案 | 非 script，計原始 bytes |
| lifecycle 讀取 VM 證據的 sibling、新的信任值（#1269） | +4–8 KB，1 個檔案 | verification、PR lifecycle |
| 登記 PR 的 `registration` URL 格式檢查（#1270；第四版的跨 repo 讀取與核准判斷已移除） | +0.3–0.8 KB，0 個檔案 | PR lifecycle |
| 文件：三種模式、登記指引（#1272） | +300–800 token | agent 文件 token |

估計：canonical 約 649–657 KB（上限 784,000）、檔案 89 個（上限 92）、寫入 workflow 0、`pull_request_target` 0，都在 solo 預算內；agent 文件 token 約 13,100–13,600，可能碰到 13,500 的上限，需要以條件 render 或精簡文件處理。各分項都有足夠餘裕（verification 在 solo 為 77,364／101,000）。

**hosted fixture：**只有共用部分（設定、證據的 `mode` 欄位、render 與實際模式的比對）約 +2.5–4 KB，餘裕 2,828 B，缺口約 0–1.2 KB。#1264 只在模板 repository，不再占用任何下游 fixture 的空間。consumer-a 的 settings 分項餘裕 3,188 B，也要注意。

和第三版相比：不再需要新的大型 fixture 預算。依 Q2 的決定，solo-default 改量 self-hosted 預設，另加一個 solo-local fixture 沿用同一組預算。

## 未來研究（不在 Milestone 21）

- **Release 後的部署驗收環境：**部署已發布的 artifact，再跑驗收或 smoke test；目前沒有這類測試與部署目標。
- **常駐的產品測試服務：**與「不常駐」衝突，需要另外處理資源、隔離與關閉責任；屆時再評估 `self_hosted_services`。
- **封存 repo 的偵測：**需要 Metadata 唯讀憑證。

## 已決（2026-10-25）

擁有者 2026-10-25 確認全部問題，已沒有待擁有者決定的事項。第三版的 Q3（Ruleset 不一致）在 self-hosted 與 `local` 共用同一組設定後不存在，併入 Q2。

| ID | 問題 | 決定 |
| --- | --- | --- |
| Q1 | 離開 self-hosted 的 PR 在尚未登記或 VM 無法使用時取不到 VM 證據 | 只為「只改模式、方向是離開 self-hosted」的 PR 接受 `local` 本機證明，trace 註明原因；不需要 GitHub-hosted（D10） |
| Q2 | 依可見性 render，還是同時 render 兩種模式；fixture 如何調整 | 依可見性 render，轉 public 由 `retire` 的 PR 重新 render；solo-default 改量 self-hosted 預設、沿用現有預算，另加 solo-local fixture 沿用同一組預算 |
| Q4 | `retire --apply` 是否直接改設定 | 只刪資料並建立 PR，不直接改設定（D9） |
| Q5 | 模板是否讀取 csarc-devops 的登記與核准 | **改變：不讀。**VM 是登記的權威，未登記、撤銷、到期的 repo 開不了窗；登記 PR 只需連結 csarc-devops Issue；lifecycle 以證據的 runner 名稱與 labels 比對登記的 `self_hosted_runner`，並確認是 GitHub 記錄的 self-hosted 執行、exact head、repo 與 workflow 路徑；撤銷與到期由 VM 強制（C5、C8）。不要求管理員擁有 csarc-devops 的讀取權限。這取代草稿中的擁有者決定 5（「雙邊 Issue 互相連結、雙方核准」由模板自動讀取）：雙邊 Issue 保留為人工流程，只拿掉自動的跨 repo 讀取 |
| Q6 | 核准語彙與 `registration` 的位置 | `registration` 放在 `self_hosted_runner` 裡；csarc-devops 端的核准語彙由 csarc-devops 自訂（模板不再讀取，C5） |
| Q7 | 合併時如何判斷可見性 | lifecycle 以操作者的登入讀取 repo 的 `private` 欄位，讀不到就 fail closed；不帶憑證的 API 只給 VM 使用 |
| Q8 | AC1 的「規格」 | 在 #1268 隨 schema 寫成 `docs/specs/SPEC-011` |
| Q9 | 後續 Issue 的完成條件 | 授權依本 ADR 改寫 #1264、#1268、#1269、#1270、#1271、#1272 |
| Q10 | #1264 的範圍 | **改變：**只屬於模板 repository，不下發到 `template/`；lifecycle 規則與模式無關；下游 fixture 不需為它保留空間 |
| Q11 | 信任邊界 | **改變：縮小。**登記加入觸發者允許清單，存在 VM 端，修改走雙邊 Issue；L4 hook 拒絕 `actor` 或 `triggering_actor` 不在清單上的 job，清單外的寫入者不能在 VM 上執行程式碼。仍保留誠實的限制：Free private 沒有 Ruleset，寫入者可以不經 lifecycle 直接合併，由 merge trace 稽核發現 `untraced` 合併 |
| — | D8 隔離 | 每個 job 一個新容器、固定版本的工具鏈 image、依（repo, 環境）分開的快取 volume；容器不掛 docker socket、不用 privileged 與 host network、不能存取 metadata endpoint；採用每個 job 丟棄 |

## 給 csarc-devops 的事項（需另開對方 Issue，雙方連結）

| ID | 問題 |
| --- | --- |
| C1 | 註冊 token、延長與狀態查詢的交付管道（例如管理員以自己的 VM 帳號透過 SSH）；記錄開始與結束時間、延長時改停止時間、到期停止 runner 並刪除 runner 憑證檔；`open` 要等 runner 輸出 `Listening for Jobs` 並上線後才回 `ok` |
| C2 | runner label 與 `runner_name` 的通用命名（不含主機名稱或內部網域）、通用工作目錄路徑；VM ID 穩定、可重查；以 `--no-default-labels` 註冊，labels 恰好是 `self-hosted`、`csarc-vm-<id>`、`csarc-env-<環境>` |
| C3 | 每個（repo, 環境）的帳號、目錄與快取 volume；每個 job 一個新容器並在 job 結束時丟棄；容器不掛 docker socket、不用 privileged 與 host network、不能存取 metadata endpoint、以非 root 執行；UAT 快取在窗口結束時刪除，DEV 快取保留到到期或 `retire`；對外網路政策 |
| C4 | VM 端 runner log 的轉存與保存期限；入侵事件時的停止與重建程序；job log 不含內部資訊的檢查方式 |
| C5 | 允許清單的格式與核准者：誰可以核准登記、變更與撤銷；撤銷與到期如何讓 VM 拒絕開窗 |
| C6 | job-started hook：repo 不是 private、事件不是 `workflow_dispatch`、workflow 不是 `main`／`dev/*` 上的 `csarc-verify.yml`、或 `actor`／`triggering_actor` 不在觸發者允許清單時拒絕；hook 設定在 VM 上 |
| C7 | 窗口期間的定期可見性檢查：間隔（建議 10 分鐘；不帶憑證的 API 每 IP 每小時 60 次）；發現 public 時立即停止 runner、刪除該 repo 的工作目錄與快取，並在 csarc-devops 開 Issue |
| C8 | 90 天未開窗的登記到期：移除允許清單、刪除快取與資料、在 csarc-devops 開 Issue；`open` 回應 registration expired |
| C9 | 工具鏈 image：依語言 profile 建置、以 digest 固定、更新節奏與更新時的通知 |
| C10 | 觸發者允許清單的儲存位置（VM 端、與登記放在一起）與修改流程（雙邊 Issue） |
| C11 | job 容器內隔離的 Docker daemon（D8 第 7 點，#1281）：評估 sysbox runtime 或 rootless Docker 在 VM 上是否可行，以及 CPU、記憶體、磁碟與 image 快取的資源限制；確認不掛主機 docker socket、不用 privileged 與 host network、daemon 隨 job 丟棄；確認後在雙邊 Issue 記錄，模板再以後續 Issue 解除 `container` 的限制 |
| C12 | 由 VM 證明窗口結束時間（#1320）：job 開始時，runner 能讀到 VM 寫入的唯讀窗口紀錄（例如掛進容器的檔案，內容是 repo、環境、runner 名稱與 UTC 結束時間），延長時同步更新。有了這份紀錄，`csarc-verify.yml` 第一個 step 改用它判斷 30 分鐘門檻並寫進證據，`window_source` 改為 VM 提供；在這之前證據只標示操作者宣告 |

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 選項 X：hosted 的治理 workflow＋VM 驗證（第一到第三版） | 不採用；治理 workflow 仍在 GitHub-hosted 執行並持有寫入 token，private 預設專案會帶著全部 hosted workflow，與「盡量不讓 GitHub 執行」相反 |
| 維持 hosted，改用 larger runner 或快取 | 不採用；仍耗用 GitHub 額度 |
| VM 自己跑測試再回報結果（不經 GitHub 派工） | 不採用；結果由 VM 自行聲明，信任等級與 `local` 相同 |
| 以 `pull_request` 或 `pull_request_target` 自動觸發 VM 驗證 | 不採用；`pull_request` 執行 PR 自己的 workflow 定義，`pull_request_target` 會被 fork PR 觸發，兩者在窗外都會排隊；改由操作者以 `workflow_dispatch` 觸發 base 的定義 |
| 常駐 runner 與常駐環境（第一版） | 不採用；擁有者改為按需開窗 |
| csarc-devops 以 GitHub App 替下游取得註冊 token | 不採用；需要 Administration 寫入權限 |
| 每個 job 一個 ephemeral／JIT runner | 不採用；每個 job 都要管理員憑證，或必須把下游權限交給 VM |
| 組織層級 runner 放在 default group | 不採用；組織內每個 private repo 都能派工上去 |
| 同時 render private 與 public 兩種模式 | 不採用；private 預設專案會帶著全部 hosted workflow（Q2） |
| 窗口紀錄寫在 repository variable（第二、三版） | 不採用；選項 Y 沒有需要事先讀取它的 GitHub-hosted job，VM 端紀錄已足夠，也少一次寫入 repo 設定 |
| VM 發現 public 時在下游 repo 開 Issue | 不採用；VM 對下游沒有權限 |
| 模板唯讀讀取 csarc-devops 的核准留言（第一到第四版） | 不採用（2026-10-25）；需要下游管理員擁有 csarc-devops 權限或另一份憑證，而 VM 本來就核對允許清單 |
| 窗口結束才丟棄容器 | 不採用；同一窗口內的 job 會共用檔案系統與程序 |
| 信任所有寫入者（第四版） | 不採用（2026-10-25）；改以觸發者允許清單縮小 |
| 設 PRD 驗證環境 | 不採用；release 只發布已驗證的候選 |
| 窗外或 VM 不可用時自動改用其他模式 | 不採用；擁有者要求 fail closed |
| fork PR 經核准後可以上 VM | 不採用；擁有者決定與 GitHub 的建議都排除 fork |
| 每次開窗也要雙邊核准 | 不採用；取得 token 本身就是授權動作 |
| 窗口次數或總時數上限 | 不採用；擁有者決定只用固定 24 小時 |
| 既有專案更新時自動改用 self-hosted | 不採用；切換一律經 governance-switch PR |

## 重新評估條件

- 組織升級到 Team 或 Enterprise：private repo 可以使用 Ruleset 與只開放選定 repo 的 runner group，重新評估合併強制方式與 L1。
- csarc-devops 能在不持有下游權限的情況下提供每個 job 一台新 VM：重新評估 D8 的容器隔離，可能提高信任等級。
- 撤銷登記後需要立即讓既有證據失效：重新評估是否加入跨 repo 讀取。
- 發生 VM 入侵、快取汙染、註冊 token 外洩、寫入者濫用 runner，或 log 在公開後洩漏內部資訊：檢討 D6–D9。
- 觀察到某個 repo 長期每天延長窗口、實際上接近常駐：檢討是否需要上限，或延長時改換新 runner。
- 多數新專案長期停在「尚未登記」：檢討預設與登記流程。
- 未來研究成案時：重新評估環境清單與 `self_hosted_services`。
- GitHub 改變 self-hosted runner、registration token、runner hook、`workflow_dispatch`、不帶憑證 API 的限制，或 Jobs API 回傳的 runner 欄位。
- #1267 無法取得足夠空間：重新評估哪些能力先做、哪些延後。
- csarc-devops 確認 C11：以後續 Issue 解除 `container` 加上 self-hosted 的限制（D8 第 7 點）。
