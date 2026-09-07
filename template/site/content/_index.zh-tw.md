+++
title = "[[project_name]]"

[controls]
menu = "投影片目錄"
language = "閱讀語言"
detail = "閱讀模式"
simple = "標準"
technical = "維運"
slides = "簡報控制"
previous = "上一頁"
next = "下一頁"
zoom = "畫面縮放控制"
zoom_out = "縮小投影片"
zoom_reset = "恢復自動符合畫面"
zoom_in = "放大投影片"
fit = "符合畫面"
+++

{{< slide key="index" track="index" eyebrow="首頁" title="[[project_name]]" subtitle="[[project_description]]" class="dense" legacy="false" >}}
{{< standard key="index-mode-standard" title="這個 repo 目前的治理設定" >}}
這個 repo 使用 [csarc-repo-template](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template) 建立與維護，工作方式跟程式碼一樣可版本化、驗證與升級：

<div class="capability-map"><div class="capability-node"><h3>使用語言</h3><p>[[languages]]</p></div><div class="capability-node"><h3>分支策略</h3><p>[[branch_strategy]]</p></div><div class="capability-node"><h3>可見度</h3><p>[[project_visibility]]</p></div><div class="capability-node"><h3>下一步</h3><p>切換「安裝說明」看怎麼開始，或切換「關於」看這個治理基線做了什麼。</p></div></div>
{{< /standard >}}

{{< ops key="index-mode-ops" title="設定來源" >}}
這個 repo 的治理設定記錄在 `.csarc/config.yml`，由 [csarc-repo-template](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template) 產生並可持續更新：

| 設定 | 目前值 |
| --- | --- |
| 負責人 | `[[code_owner]]` |
| 審查者 | `[[reviewers]]` |
| 分支策略 | `[[branch_strategy]]` |
| 可見度 | `[[project_visibility]]` |
| 使用語言 | `[[languages]]` |

執行 `csarc status` 可確認目前是否已是最新版本；有更新可用時，會先讓你看過差異再套用，不會靜默覆寫本專案已寫的內容。
{{< /ops >}}
{{< /slide >}}

{{< slide key="install" track="install" eyebrow="安裝說明" title="把這個 repo clone 下來就能開始" subtitle="標準工作流程是 clone、跑一次驗證、再開始改動。" class="dense" legacy="false" >}}
{{< standard key="install-mode-standard" title="三步驟開始" >}}
<div class="step-flow"><article class="step-flow-item"><span class="step-flow-number">1</span><h3>Clone</h3><p>把這個 repository clone 到本機。</p></article><article class="step-flow-item"><span class="step-flow-number">2</span><h3>驗證</h3><p>跑一次本機驗證，確認環境設定正確。</p></article><article class="step-flow-item"><span class="step-flow-number">3</span><h3>開始工作</h3><p>照「關於」頁說明的工作方式，先開 Issue 再開始改動。</p></article></div>

<div class="command-block"><div class="command-block-head"><span class="command-block-label">Clone 指令</span><button class="copy-command" type="button" data-copy-text="git clone [[repository_url]]">複製指令</button></div></div>
{{< /standard >}}

{{< ops key="install-mode-ops" title="驗證指令與需求" >}}
```bash
git clone [[repository_url]]
./scripts/verify-fast
```

`scripts/verify-fast` 是這個 repo 日常 PR 走的驗證分層入口；push 前務必先跑過，因為 hosted CI 不再重新執行它，只核對它成功時留下的 `Verified-locally:` 驗證聲明。只有 Milestone／canary 交付、hotfix 或 merge queue 才需要跑完整的 `scripts/verify-template.sh`。本機需求（語言工具鏈、`gh` 登入等）與這個 repo 選用的語言（[[languages]]）有關，詳見 README。
{{< /ops >}}
{{< /slide >}}

{{< slide key="about" track="about" eyebrow="關於" title="這個 repo 用 csarc-repo-template 治理" subtitle="工作方式跟程式碼一樣可版本化、驗證與升級，不只是產生檔案的模板。" class="dense single-column" legacy="false" >}}
{{< standard key="about-mode-standard" title="這套治理基線持續在做什麼" >}}
<div class="capability-map"><div class="capability-node"><h3>每項工作是一張 Issue</h3><p>寫清楚要做什麼、怎樣算完成，改動在自己的分支進行，不會互相干擾。</p></div><div class="capability-node"><h3>每次改動都要通過審查</h3><p>自動檢查先跑過一輪，PR 經人審查合併，沒通過就不會進主要分支。</p></div><div class="capability-node"><h3>公版更新先給你看差異</h3><p>`csarc-repo-template` 之後有更新，一樣先讓你看過差異，確認後才套用。</p></div><div class="capability-node"><h3>例行安全檢查是自動的</h3><p>套件版本與已知漏洞排好定期執行，只在真的有衝突時才需要你判斷。</p></div></div>
{{< /standard >}}

{{< ops key="about-mode-ops" title="治理基線的機制" >}}
這個 repo 的治理規則放在 `AGENTS.md`（AI 與人共用的工作規則）、`policies/*.json`（GitHub 設定的期望狀態）與 `.csarc/config.yml`（本專案的實際選擇）三個地方，各自有明確的角色：

- **`AGENTS.md`：** agent 開始工作前一律先讀這份；人類貢獻者的等效說明在 README。
- **`policies/*.json`：** 分支保護、必要檢查、標籤等期望設定，由 `scripts/apply-repository-settings.sh` 套用與驗證。
- **`.csarc/config.yml`：** 這個 repo 的實際選擇（語言、分支策略、負責人等），由 `csarc update` 持續同步公版更新，同時保留這裡的專案內容。

這個網站本身就是同一套原則的示範：`docs/index.html` 內嵌所有樣式與程式，下載後可離線打開，不需要另外架站。
{{< /ops >}}
{{< /slide >}}
