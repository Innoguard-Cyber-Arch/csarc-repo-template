+++
title = "repo-template 技術手冊｜模板能力、操作與限制"
lang = "zh-Hant-TW"
status = "current"
footer_version = "版本日期 261026 r6"
baseline = "approved/261026r6_repo-template-handbook.html"
baseline_sha256 = "afe235062b54305fe457d41ec4e1e06a39a8a4420c59ecad6a424fb844d014ab"
+++

<!--
Authoritative source for docs/handbook/index.html (Issue #1081).
Render with scripts/build-handbook; check freshness with scripts/build-handbook --check.
Syntax beyond plain Markdown is documented in scripts/build_handbook.py.
An approved wording change replaces approved/ with the newly approved copy in the same change.
-->

::: sheet capabilities | 第 1 章 · repo-template 的功能與使用方式

架構組 · repo-template {: div.eyebrow}

# repo-template 技術手冊

`repo-template`（`Innoguard-Cyber-Arch/csarc-repo-template`）是架構組維護的 Repository 模板；`csarc` 是呼叫模板能力的 CLI 名稱。本手冊定義產品政策、使用者承諾、操作方式及限制。 {: .lead}

**適用範圍：**本手冊描述首個完整實作本文能力的 stable release；實際使用版本、來源與 full SHA 以該 Release 的 `release-prompt.txt` 為準。候選版本未通過手冊、SPEC、Repository 規則、程式與測試的一致性檢查前，不得宣稱已提供本文能力。 {: .compact}

**目前狀態：**CLI、Ready、migration 與 Roadmap 自 v0.35.x 起提供；設定開啟的 single-writer 合併與新設定盤點自 v0.41.x 起提供；寫作指引與訊息句型檢查隨 Milestone 20 的 stable 提供。版本：2026-10-26；核准 SHA-256 見 manifest。 {: .compact}

## 1. repo-template 的功能與使用方式

### 1.1 repo-template 會替專案做什麼

<figure class="diagram-frame">
  <div class="diagram-scroll">
    <svg class="diagram-svg" viewBox="0 0 680 286" role="img" aria-labelledby="capabilities-title capabilities-desc">
      <title id="capabilities-title">repo-template 端到端能力</title>
      <desc id="capabilities-desc">repo-template 從專案建立或導入開始，連接需求治理、AI 隔離實作、驗證、審核合併、發布與模板更新，並留下可重查的專案狀態。</desc>
      <defs>
        <marker id="cap-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#637582"/>
        </marker>
        <marker id="cap-arrow-focal" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#176b87"/>
        </marker>
      </defs>
      <line class="diagram-arrow" x1="178" y1="61" x2="256" y2="61" marker-end="url(#cap-arrow)"/>
      <line class="diagram-arrow" x1="424" y1="61" x2="502" y2="61" marker-end="url(#cap-arrow)"/>
      <path class="diagram-arrow" d="M582 92 V148" marker-end="url(#cap-arrow)"/>
      <line class="diagram-arrow" x1="502" y1="180" x2="424" y2="180" marker-end="url(#cap-arrow)"/>
      <line class="diagram-arrow-focal" x1="256" y1="180" x2="178" y2="180" marker-end="url(#cap-arrow-focal)"/>
      <rect class="node" x="18" y="30" width="160" height="62"/>
      <text class="node-title" x="98" y="56">建立或導入</text>
      <text class="node-sub" x="98" y="75">create · adopt · update</text>
      <rect class="node" x="256" y="30" width="168" height="62"/>
      <text class="node-title" x="340" y="56">需求與工單治理</text>
      <text class="node-sub" x="340" y="75">Issue · AC · risk</text>
      <rect class="node" x="502" y="30" width="160" height="62"/>
      <text class="node-title" x="582" y="56">AI 隔離實作</text>
      <text class="node-sub" x="582" y="75">branch · worktree · Draft</text>
      <rect class="node" x="502" y="148" width="160" height="64"/>
      <text class="node-title" x="582" y="175">風險導向驗證</text>
      <text class="node-sub" x="582" y="194">focused · fast · full</text>
      <rect class="node" x="256" y="148" width="168" height="64"/>
      <text class="node-title" x="340" y="175">審核與生命週期</text>
      <text class="node-sub" x="340" y="194">review · merge · release</text>
      <rect class="node node-focal" x="18" y="148" width="160" height="64"/>
      <text class="node-title" x="98" y="175">交付與持續更新</text>
      <text class="node-sub" x="98" y="194">evidence · Copier</text>
      <rect class="band" x="18" y="232" width="644" height="42" rx="6"/>
      <text class="band-title" x="340" y="250">可重查、可恢復、可持續更新的 Repository 基線</text>
      <text class="band-sub" x="340" y="266">設定 · 產物 · 決策 · 驗證證據 · 版本與平台狀態</text>
    </svg>
  </div>
  <figcaption>repo-template 把需求、實作、驗證及交付串成可重查的 Repository 流程；它不替使用者決定產品需求、風險接受或正式環境核准。</figcaption>
</figure>

### 1.2 Prompt-first 操作流程

使用者以自然語言描述要建立、導入、修改或交付的工作；AI 先讀取 Repository 規則並驗證 `release-prompt.txt`，再透過固定版本的 `csarc` CLI 判斷狀態、顯示計畫並等待確認。確認後才套用，後續日常工作由 Repository 工具箱執行；使用者不必記指令，實際操作仍由可重現的程式完成。

### 1.3 責任與能力邊界

{: table.stage-table.dense stage}
| 角色 | 負責 | 不負責 |
|---|---|---|
| 使用者 | 定義問題與驗收條件、確認風險、審閱產品結果、授予必要權限。 | 不必自行設計 CI；仍須保留產品與高風險決策。 |
| AI agent | 依 Repository 規則實作、執行檢查、整理證據與交接狀態。 | 不得擴大範圍、繞過控制或宣稱未取得的證據。 |
| repo-template | 產生設定、政策、驗證與生命週期工具；條件不足時停止或降級。 | 不取代產品測試、法遵、正式環境核准或組織管理權。 |
| GitHub | 保存 Issue、PR、review、Actions、Project、Release 與稽核紀錄。 | 能力仍受方案、visibility、權限、政策及額度影響。 |

**責任與邊界：**AI 產生的程式碼由指派 agent、實際主導修改的人負責；合併者可以是同一人或 reviewer。repo-template 不承諾無人監督開發，也不取代產品測試、部署核准、法遵判斷或 GitHub 付費能力。 {: .compact .mt-3}

:::

::: sheet installation | 第 2 章 · 安裝與導入

第 2 章 · 安裝與導入 {: div.eyebrow}

## 2. 安裝與導入

### 2.1 前置條件

create 在不存在、空的資料夾，或只含 `.git`、尚無 commit 與 tracked 檔的 repository 執行；adopt 與 update 在既有 Git repository 根目錄執行。一律需要 Git、`uv`／`uvx`、GitHub CLI 2.93.0 以上並完成 `gh auth login`；Windows 須在 WSL2 操作。下文的 `csarc` 代表 `release-prompt.txt` 給出的固定版本呼叫。選用語言另需該 Release 指定的工具鏈；ProjectV2 需要 `project` scope，Ruleset 與 Release 設定需要 repository admin。

### 2.2 給 AI agent 的啟動 Prompt

這段 Prompt 是建議入口。它要求 agent 從已發布版本取得固定內容，不直接使用 `main`，且在使用者確認前不得寫入：

```text
請從 https://github.com/Innoguard-Cyber-Arch/csarc-repo-template
的 published Releases 中，依官方 csarc CLI 選出最新 stable 且 immutable
的 Release，下載並讀取它的 release-prompt.txt，確認附件內的 repository、
tag 與 full SHA 一致後，完全依該 prompt 在目前 workspace 繼續。
不要使用 main、猜測目前安裝狀態，或在我確認前修改檔案、GitHub 設定、
push 或建立 PR。
```

### 2.3 先判斷狀態，再決定操作 {: .mt-3}

{: table.stage-table.compact stage}
| 狀態 | 判讀 | 下一步 |
|---|---|---|
| create | 目標尚未形成既有產品 Repository。 | 詢問必要選項，建立新的受管專案。 |
| adopt | 已有產品內容，但尚未由 repo-template 管理。 | 盤點、預覽衝突並保留專案內容後導入。 |
| adoption-pending | 導入計畫已有人工衝突尚未完成。 | 沿用原計畫完成合併，再執行 finalize。 |
| migrate | 已安裝，但 `_commit` 是 tag 或短 SHA，尚未綁定經驗證 Release 的 full SHA。 | 依 status 提示驗證來源，再檢查遷移報告與計畫；legacy 轉換仍在 update 內執行。 |
| update | 已有較舊的 repo-template 版本。 | 比較模板、設定與專案變更後產生更新計畫。 |
| current | 模板與設定已是目前版本。 | 不重複安裝；回報現況與可選檢查。 |
| policy-only-update | 檔案版本相同，但平台政策需補套用或重查。 | 只處理可觀察的 GitHub desired state。 |

<div class="callout compact mt-3">

**操作分工：**Prompt 是使用者入口；外部薄型 CLI 負責可信 bootstrap、狀態判讀與交易式導入；導入後由 Repository 內的 `.csarc/scripts/` 執行日常規則與驗證。

</div>

### 2.4 核心原則：先盤點、再動作 {: .mt-3}

凡是要帶入或執行未經驗證內容的流程（下游 Release、candidate PR、外部 repository 的設定或程式碼），都先以不執行的方式產生唯讀、人看得懂的盤點，逐項列出內容、來源與是否符合預期。有一項不符就停止，說明原因與下一步；需要外部程式碼的資訊時，只解析字面值，不執行、不 import。adopt 的 dry-run、`update --check`、`prepare-candidate` 與 6.1 的新設定盤點都依此設計；新流程不符時，須在 PR 說明理由並取得擁有者確認。依據見 [`dry-run-inventory-before-action`](../adr/dry-run-inventory-before-action.md)。 {: .compact}

:::

::: sheet adoption-lifecycle | 第 2 章 · 安裝與導入

第 2 章 · 安裝與導入（續） {: div.eyebrow}

## 2. 安裝與導入（續）

### 2.5 建立、導入、更新與移除

<figure class="diagram-frame diagram-process">
  <div class="diagram-scroll">
    <svg class="diagram-svg" viewBox="0 0 680 338" role="img" aria-labelledby="states-title states-desc">
      <title id="states-title">repo-template 建立、導入、更新與移除</title>
      <desc id="states-desc">新專案與既有專案經過預覽和確認成為受管專案；既有受管專案以可重播計畫更新；移除則由專案負責人人工審閱。</desc>
      <defs>
        <marker id="state-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#637582"/></marker>
        <marker id="state-arrow-manual" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#8a5a00"/></marker>
      </defs>
      <text class="lane-label" x="164" y="18">起始狀態</text>
      <text class="lane-label" x="365" y="18">受控操作</text>
      <text class="lane-label" x="569" y="18">結果</text>
      <line class="lane-rule" x1="18" y1="28" x2="662" y2="28"/>
      <line class="diagram-arrow" x1="254" y1="68" x2="476" y2="68" marker-end="url(#state-arrow)"/>
      <line class="diagram-arrow-focal" x1="254" y1="142" x2="476" y2="142" marker-end="url(#state-arrow)"/>
      <line class="diagram-arrow" x1="254" y1="216" x2="476" y2="216" marker-end="url(#state-arrow)"/>
      <line class="diagram-return" x1="254" y1="290" x2="476" y2="290" marker-end="url(#state-arrow-manual)"/>
      <rect x="280" y="37" width="170" height="20" rx="3" fill="#f8fafb"/>
      <text class="arrow-label" x="365" y="51">建立 · 預覽 · 確認</text>
      <rect x="280" y="111" width="170" height="20" rx="3" fill="#f8fafb"/>
      <text class="arrow-label" x="365" y="125">導入 · 計畫 · 套用</text>
      <rect x="280" y="185" width="170" height="20" rx="3" fill="#f8fafb"/>
      <text class="arrow-label" x="365" y="199">檢查 · 計畫 · 套用</text>
      <rect x="280" y="259" width="170" height="20" rx="3" fill="#f8fafb"/>
      <text class="arrow-label" x="365" y="273">人工移除 · 負責人審閱</text>
      <text class="lane-label" x="36" y="72">01</text>
      <rect class="node" x="74" y="40" width="180" height="56"/>
      <text class="node-title" x="164" y="64">尚未建立的專案</text>
      <text class="node-sub" x="164" y="82">new repository</text>
      <rect class="node" x="476" y="40" width="186" height="56"/>
      <text class="node-title" x="569" y="64">受管新專案</text>
      <text class="node-sub" x="569" y="82">config · baseline · checks</text>
      <text class="lane-label" x="36" y="146">02</text>
      <rect class="node" x="74" y="114" width="180" height="56"/>
      <text class="node-title" x="164" y="138">既有產品 Repository</text>
      <text class="node-sub" x="164" y="156">existing product</text>
      <rect class="node node-focal" x="476" y="114" width="186" height="56"/>
      <text class="node-title" x="569" y="138">受管既有專案</text>
      <text class="node-sub" x="569" y="156">產品內容已保留</text>
      <text class="lane-label" x="36" y="220">03</text>
      <rect class="node" x="74" y="188" width="180" height="56"/>
      <text class="node-title" x="164" y="212">舊版模板專案</text>
      <text class="node-sub" x="164" y="230">previous template</text>
      <rect class="node" x="476" y="188" width="186" height="56"/>
      <text class="node-title" x="569" y="212">目前模板版本</text>
      <text class="node-sub" x="569" y="230">報告與決策可重播</text>
      <text class="lane-label" x="36" y="294">04</text>
      <rect class="node" x="74" y="262" width="180" height="56"/>
      <text class="node-title" x="164" y="286">模板受管專案</text>
      <text class="node-sub" x="164" y="304">managed repository</text>
      <rect class="node node-manual" x="476" y="262" width="186" height="56"/>
      <text class="node-title" x="569" y="286">產品自主治理</text>
      <text class="node-sub" x="569" y="304">人工確認移除範圍</text>
    </svg>
  </div>
  <figcaption>任何寫入都先驗證來源與輸入並產生計畫；既有專案的內容擁有權與發布邊界須在 plan 中明示，不因新預設自行改變。</figcaption>
</figure>

{: table.stage-table.dense stage}
| 階段 | repo-template 行為 | 使用者確認 |
|---|---|---|
| 偵測 | 讀取 Repository、語言、文件與 GitHub 現況；不重問可可靠推導的值，必要答案不足時在任何寫入前停止。 | 專案、技術基線與治理模式是否正確。 |
| 建議 | 提供適用的建議預設；只有需要時才展開進階選項。 | 接受建議值或指定要自訂的類別。 |
| 預覽 | create：dry-run 列出檔案與設定，不產生報告；adopt：在目標外寫出 plan、report JSON 與 Markdown；update：`--check` 寫出報告與 stage-1 plan，人工決策寫入 final plan。 | 計畫沒有未授權的產品內容或外部變更。 |
| 套用 | create：以相同 tag、SHA 與答案套用；adopt：`--apply-plan <plan>`；update：`--apply-plan <final plan>`。全部交易式寫入，成功後報告標為 applied，失敗維持原狀。 | 明確確認後才可寫入、push、建立 PR 或修改 GitHub。 |

### 2.6 驗證模式與 self-hosted 登記 {: .mt-3}

{: table.stage-table.dense stage}
| 模式 | 在哪裡驗證 | 適用 |
|---|---|---|
| self-hosted | csarc-devops 登記的 VM，結果由 GitHub 記錄；治理與 local 相同。 | 新建 private 專案的預設。登記前 PR 不能合併；只限 private。 |
| local | 操作者電腦，證據是自我證明。 | private 或 public，不需要遠端證據時。 |
| hosted | GitHub-hosted runner。 | 新建 public 專案的預設；需要 Ruleset、Pages 或 release provenance 時。 |

**設定與限制：**模式依可見性分成 `verification_mode_private` 與 `verification_mode_public`，public 不能用 self-hosted。GitHub Free 的 private Repository 沒有 Ruleset，local 與 self-hosted 的合併只由 lifecycle 執行，在 UI 直接合併記為 untraced。啟用 container 時暫不能用 self-hosted。既有專案不自動切換，`csarc update` 只提出建議。 {: .compact}

**登記與使用：**本 Repository 與 csarc-devops 各開一張互相連結的 Issue，雙方人工核准，並列出可觸發驗證的帳號；再以 governance-switch PR 設定 `self_hosted_runner`，Actions log 建議保存 7 天。管理員以 `csarc self-hosted open` 開 24 小時窗口，可 `extend`，再以 `verify --pr` 派工。90 天未開窗，登記到期；轉 public 前必須先執行 `retire`。 {: .compact}

:::

::: sheet daily-workflow | 第 3 章 · 日常使用

第 3 章 · 日常使用 {: div.eyebrow}

## 3. 日常使用

### 3.1 從需求到合併

<figure class="diagram-frame diagram-process">
  <div class="diagram-scroll">
    <svg class="diagram-svg" viewBox="0 0 680 326" role="img" aria-labelledby="workflow-title workflow-desc">
      <title id="workflow-title">一般使用者、AI 與 repo-template 的日常交付流程</title>
      <desc id="workflow-desc">需求負責人核定 Issue，AI 隔離實作並整理證據，repo-template 執行 Ready 與可信驗證，審核者核准精確版本，再由生命週期工具合併；失敗則回到實作。</desc>
      <defs>
        <marker id="workflow-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#637582"/></marker>
        <marker id="workflow-arrow-focal" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#176b87"/></marker>
        <marker id="workflow-arrow-return" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#8a5a00"/></marker>
      </defs>
      <rect class="lane-fill" x="92" y="34" width="570" height="82"/>
      <rect x="92" y="116" width="570" height="82" fill="#fff"/>
      <rect class="lane-fill" x="92" y="198" width="570" height="82"/>
      <line class="lane-rule" x1="92" y1="34" x2="92" y2="280"/>
      <line class="lane-rule" x1="18" y1="34" x2="662" y2="34"/>
      <line class="lane-rule" x1="18" y1="116" x2="662" y2="116"/>
      <line class="lane-rule" x1="18" y1="198" x2="662" y2="198"/>
      <line class="lane-rule" x1="18" y1="280" x2="662" y2="280"/>
      <text class="lane-label" x="54" y="72">使用者</text>
      <text class="lane-label" x="54" y="154">AI</text>
      <text class="lane-label" x="50" y="236">模板</text>
      <path class="diagram-arrow" d="M232 78 H272 Q280 78 280 86 V132" marker-end="url(#workflow-arrow)"/>
      <line class="diagram-arrow" x1="344" y1="159" x2="360" y2="159" marker-end="url(#workflow-arrow)"/>
      <path class="diagram-arrow-focal" d="M488 159 H500 Q508 159 508 167 V214" marker-end="url(#workflow-arrow-focal)"/>
      <line class="diagram-arrow-focal" x1="516" y1="214" x2="516" y2="104" marker-end="url(#workflow-arrow-focal)"/>
      <path class="diagram-arrow" d="M616 78 H620 Q628 78 628 86 V214" marker-end="url(#workflow-arrow)"/>
      <path class="diagram-return" d="M472 268 V296 Q472 304 464 304 H288 Q280 304 280 296 V186" marker-end="url(#workflow-arrow-return)"/>
      <rect x="320" y="282" width="112" height="16" rx="3" fill="#f8fafb"/>
      <text class="arrow-label" x="376" y="293">修正 · 重跑</text>
      <rect class="node" x="104" y="52" width="128" height="52"/>
      <text class="node-title" x="168" y="74">核定 Issue</text>
      <text class="node-sub" x="168" y="91">AC · risk · scope</text>
      <rect class="node" x="216" y="132" width="128" height="54"/>
      <text class="node-title" x="280" y="155">隔離實作</text>
      <text class="node-sub" x="280" y="173">branch · worktree</text>
      <rect class="node" x="360" y="132" width="128" height="54"/>
      <text class="node-title" x="424" y="154">測試與證據</text>
      <text class="node-sub" x="424" y="172">tests · evidence</text>
      <rect class="node node-focal" x="408" y="214" width="128" height="54"/>
      <text class="node-title" x="472" y="236">Ready Gate</text>
      <text class="node-sub" x="472" y="254">coverage · verify</text>
      <rect class="node" x="476" y="52" width="140" height="52"/>
      <text class="node-title" x="546" y="74">核准精確版本</text>
      <text class="node-sub" x="546" y="91">human · Copilot</text>
      <rect class="node" x="544" y="214" width="112" height="54"/>
      <text class="node-title" x="600" y="236">合併與收尾</text>
      <text class="node-sub" x="600" y="254">lifecycle</text>
    </svg>
  </div>
  <figcaption>使用者主要負責定義、確認與核准；AI 與 repo-template 負責把實作、檢查及證據整理成可審查狀態。</figcaption>
</figure>

{: table.stage-table.dense stage}
| 階段 | 使用者對 AI 說什麼 | 完成條件 |
|---|---|---|
| 需求 | 說明問題、使用情境、可接受結果與已知風險。 | Issue 有可判定的 AC、範圍、負責人與工作關係。 |
| 實作 | 要求依 Issue 工作，保留既有內容，先建立 Draft PR。 | 分支與 worktree 隔離，變更未超出 Issue。 |
| 檢查 | 要求說明跑了哪些測試、每項 AC 的證據在哪裡。 | 測試與人工證據都對應目前 head。 |
| 交付 | 確認產品結果後，要求生命週期工具進入審核、合併與收尾。 | `csarc-owned` 且 release-worthy 的 PR 已物化版本；Milestone checkpoint 只有 terminal 物化，其餘以 deferred 合併。review、驗證、授權與 head／tree 一致後，再由 `pr_lifecycle.py` 合併。 |

<div class="callout compact mt-3">

**合併、核准與設定：**agent 不執行 `gh pr merge`、UI／auto-merge、force-push、push 到 main／`dev/m*`，也不改名有 open PR 的分支；不代發核准、Milestone approval 或 exact-head 授權。設定只以 `csarc update --data KEY=VALUE` 變更，不手改 `.csarc/config.yml`／`.csarc/scripts`，不直接執行 `copier update`。模板更新都走 governance-switch；新專案預設 `admin_bypass: always` 只取代同行核准，不能略過驗證、required checks 或 lifecycle。local 的 `csarc-owned` 發版由 maintainer 執行。

</div>

### 3.2 寫作指引與訊息句型

**兩份指引：**英文依 `docs/writing-guide.en.md`，以模板自己的文字參考 ASD-STE100 的精神，不收錄 STE 規則或詞典，也不宣稱合規；中文依 `docs/writing-guide.md`，整合 speak-human-tw v1.4.0 的規則並保留 MIT 授權聲明，標點依教育部《重訂標點符號手冊》。模板擁有的文字一律照指引寫。 {: .compact}

**訊息句型：**腳本訊息只用 `ERROR:`、`WARNING:`、`NOTICE:`、`OK:` 四種開頭；例外只限英文指引列出的條件，並在原始碼逐筆記錄理由。`check-message-style` 在 verify 檢查新增或修改的訊息行：模板 repository 已強制，生成專案則在更新到含 #1221 的 Release 後才執行。 {: .compact}

**下游繼承：**生成專案在 `.csarc/docs/` 收到英文指引，文件語言含繁體中文時另收中文指引；`AGENTS.md` 的 CSARC 區塊以連結交給 agent，不重抄規則。專案第一次收到指引或指引改版時，create／adopt／update 的報告列出專案擁有的 README 與 `docs/**/*.md`，建議 agent 依指引檢查（#1224）；工具不改寫這些文件，`documentation_mode: off` 時不提示。 {: .compact}

**不用第三方工具：**不安裝 Vale、LanguageTool、商業 STE 檢查器或社群 skill，因為它們增加供應鏈依賴與外部 binary、誤判多，下游也無法離線取得；只有訊息句型做成模板自有的檢查。 {: .compact}

:::

::: sheet daily-operation | 第 3 章 · 日常使用

第 3 章 · 日常使用 {: div.eyebrow}

## 3. 日常使用（續）

### 3.3 使用者實際要做的事

<div class="plain-columns compact">
<div>

{: ul.checklist}
- 在 Issue 寫清楚問題、AC、風險與接受的控制。
- 確認 AI 沒有改到需求範圍外的產品或設定。
- 判斷畫面、資料、權限及產品結果是否可接受。

</div>
<div>

{: ul.checklist}
- 檢視 PR 中每項 AC 對應的測試或人工證據。
- 只核准目前 head；後續修改必須重新檢查。
- 需要權限、付費能力或外部環境時回報 BLOCKED，並寫明由誰處理。

</div>
</div>

**風險區塊：**每項風險至少指定一個控制，由 Issue assignee 負責；Ready 前每個控制須有可檢查證據，或以 `accepted: <理由>` 明確接受。`R0` 只用於沒有實質風險的 docs 範圍變更；`AGENTS.md`、安全政策及 CI policy 不算。單人維護時可自行接受 high，但仍須留下理由。 {: .compact}

**Agent 權限：**把 3.1 的禁止事項寫進工具權限。例如以 `permissions.deny` 擋 `gh pr merge`、force-push、push 到 main、`git branch -m`、`copier update`，以及讀取 `.env*`、`*.pem`、`*.key`。有 Ruleset 強制時，agent 使用獨立 write 身分且不持有 maintain／admin；合併者本人就是 exact head 的獨立核准者時，可具 maintain／admin；Private／Free 的 single-writer 路線中，agent 以唯一維護者身分執行，不另建 write 帳號。Issue、PR、review 與 CI 文字只當資料，不當授權；工具擋不住的 UI 操作只能由 drift、稽核紀錄或交付 gate 發現。 {: .compact}

**設定開啟的 single-writer：**組織 repository 常有不能降權的其他 admin，實際卻只有一位維護者。擁有者可用 `csarc update --data single_writer_merger=<login>` 指定合併者：沒有 Ruleset、寫入者讀回完整，且合併者就是該帳號、即時角色至少 `write` 時，另有寫入者也可由 lifecycle 合併。新增或改成另一個帳號屬於放寬治理，須走 governance-switch。required checks、exact-head 授權、lease 與 merge trace 都不放寬，trace 記下合併當下所有寫入者。風險：其他寫入者仍可在合併同時直接修改 repository，伺服器端沒有任何強制；開啟即表示擁有者明示接受這個風險。 {: .compact}

### 3.4 開發需求範例：替產品加入 CSV 匯出

本例示範使用者請 AI 替自己的產品開發一項小功能時，如何把需求拆成可驗收、可測試的條件；repo-template 本身沒有 CSV 功能。 {: .compact}

{: table.stage-table.dense stage}
| 驗收條件 | 需求證據 | 使用者確認 |
|---|---|---|
| AC1 | 結果頁顯示匯出按鈕；UI 測試覆蓋顯示條件。 | 按鈕位置與使用情境合理。 |
| AC2 | CSV 欄位與畫面順序相同；回歸測試比對欄位。 | 欄位內容符合產品需求。 |
| AC3 | 無資料時仍下載標題列；測試涵蓋空集合。 | 空狀態行為可接受。 |
| 風險 | 匯出沿用畫面允許欄位清單，不包含未顯示個資。 | 確認資料用途與個資邊界。 |

### 3.5 GitHub Project Roadmap {: .mt-3}

設定完整的 organization／user `github_project_url` 後，以 `csarc issue create` 建立或 `csarc issue sync-project` 同步的 Issue 中，只有 Milestone tracker 與 standalone Issue（沒有 parent、不屬於有 tracker 的 Milestone）會加入 Project；work issue、sub-issue、PR 與其他方式建立的 Issue 不加入。Project 須事先各有一個 DATE 欄位 `Project start`／`Project target`；start 採 Issue 建立日的台北日期，target 投影 Milestone due date，沒有時為 start 後 14 天（可指定 target date）；Issue 關閉或 `Status` 為 Done 後，target 改為台北的實際完成日。Milestone 或歸屬改變後要重跑同步；既有值不同時先列差異，經確認才覆寫。工具即時查詢 ID，要求 `project` scope 與 Project 寫入權；不確定時回報 unknown。失敗時保留 Issue，以 `csarc issue sync-project --issue <N>` 冪等修復。Repository Projects 分頁維持關閉。 {: .compact}

### 3.6 交接 {: .mt-3}

交接內容至少包含 Issue、目前 branch／head、已完成與未完成 AC、測試及證據、外部等待條件、下一個安全動作。不得只留下聊天摘要；以 `csarc risk suggest --open` 列出缺少或無效風險區塊的 open Issue 與建議，以 `csarc risk register --state all --json` 交接目前風險、控制與證據狀態。 {: .compact}

:::

::: sheet test-inventory | 第 4 章 · 測試、證據與交付控制

第 4 章 · 測試、證據與交付控制 {: div.eyebrow}

## 4. 測試、證據與交付控制

實際檢查由 Repository 設定、變更路徑及可信 base 的政策自動選擇。新建的 private 專案預設在登記的 VM 驗證（self-hosted，見 2.6）；團隊可明確選擇 Hosted CI，由 GitHub Actions 在遠端 runner 驗證 PR 精確版本。使用者不必自行組合測試命令。

### 4.1 到底會測試哪些內容

共同基線適用所有 Repository；語言品質與原生建置只適用於設定中已選擇的語言。這裡列出檢查內容，何時執行由 4.2 的 tier 與變更範圍決定。 {: .compact}

<div class="table-scroll">

{: table.stage-table.test-table.dense stage-td}
| 檢查類別 | 適用範圍 | 實際檢查 |
|---|---|---|
| 共同基線 | 所有 Repository | 每次跑 diff hygiene、衝突標記與 secret；workflow、shell 或模板路徑變更時跑 lint 與 Action SHA pin；設定／政策格式、版本一致性及 PR writer ownership 只在 Full 執行。 |
| Python 品質 | 只限已選 Python | Ruff 格式與 lint、ty 型別、pytest、coverage、套件版本及依賴下限。 |
| TypeScript 品質 | 只限已選 TypeScript | Biome、tsc、Vitest 及 coverage。 |
| Rust 品質 | 只限已選 Rust | rustfmt、Clippy 與 `cargo test`。 |
| Go 品質 | 只限已選 Go | Go toolchain 版本、gofmt、`go vet` 與 `go test`。 |
| 原生建置與套件 | 只限各已選語言 | Python wheel／sdist、metadata 與隔離 import；TypeScript build／pack 與隔離 import；Rust release build／package；Go build。 |
| 依賴與供應鏈 | 存在支援的 manifest／lockfile 或 Actions | locked install、OSV 漏洞掃描及 Action pin；沒有支援的依賴檔時明確回報不適用。 |
| 治理與文件 | 所有 Repository；文件依所選模式 | 設定、JSON policy、Issue／PR 工具、規格與決策 metadata、文件 bundle 及 release 狀態。 |
| 選用：容器 | 啟用 container 能力 | Docker Compose、image build 與 Trivy HIGH／CRITICAL 掃描；不登入 registry、不 push image。 |
| 選用：產品 hook | 設定 `project_verification_hook`，或存在 executable `scripts/verify-product` | 由專案自訂 E2E、資料庫、服務或其他產品驗證；hook 失敗即整體失敗。 |

</div>

### 4.2 實際執行方式與時間 {: .mt-3}

{: table.stage-table.dense stage}
| 方式 | 何時執行 | 如何選擇內容 | 時間參考 |
|---|---|---|---|
| Focused（非 tier） | 實作期間，由 AI／開發者主動執行。 | 只跑變更 owner 的窄檢查；未選語言就不呼叫該語言工具鏈。 | 數秒至數分鐘。 |
| Fast | Milestone 工作 PR（beta）與 Dependabot 一般更新；路徑風險可升為 Full。 | 每次跑 diff hygiene、衝突標記與 secret；再加入受影響的已選語言、依賴、workflow 或文件檢查。 | 依產品與快取而定；repo-template 暖快取參考約 75 秒。 |
| Full | 沒有 Milestone 的 standalone（stable）、promotion、hotfix、release recovery、merge queue 或未知風險。 | 共同基線、全部已選語言的完整品質與原生建置，加上已啟用的容器及產品 hook。 | repo-template 目標 15 分鐘內；hosted job 上限 30 分鐘。 |

<div class="callout mt-3 compact">

**未選任何語言：**仍執行共同基線、治理及所選文件能力；依賴掃描在沒有支援檔案時回報不適用。除非另啟用 container 或產品 hook，否則不做原生 build／package，也不產生假的空套件。

**使用原則：**正式 tier 只有 Fast 與 Full；實際要求取發布通道下限（Milestone 為 Fast，standalone／hotfix 為 Full）與路徑風險中較強者。local 與 hosted 使用同一套判斷；沒有 Milestone 的工作每張 PR 都跑 Full。

</div>

:::

::: sheet delivery-controls | 第 4 章 · 測試、證據與交付控制

第 4 章 · 測試、證據與交付控制（續） {: div.eyebrow}

## 4. 測試、證據與交付控制（續）

### 4.3 本機檢查與 Hosted CI

{: table.stage-table.dense stage}
| 來源 | 用途 | 何時可作為交付證據 |
|---|---|---|
| 本機 | 選擇 local 時使用。在已 commit、乾淨的 exact head 執行一次 `verify-fast`；工具依相同判斷升級為 Full，結果綁定 SHA／tree，24 小時內有效。 | 證據只存在執行者的 Git metadata；寫入者可同時改程式與證據，因此不能證明 GitHub event、權限或遠端 runner。 |
| Hosted CI | 明確選擇 hosted 時，由可信 base 選擇 gate，在遠端 runner 驗證 exact head／tree。 | 作為 hosted 模式的合併證據；預設 24 小時內有效，逾期或 head 改變即重跑。 |

### 4.4 一項需求如何進入合併 {: .mt-3}

{: table.stage-table.dense stage}
| 階段 | repo-template 檢查 | 使用者看到的結果 |
|---|---|---|
| Issue | 網頁表單只要求「完成條件」非空；AC checkbox、數量與證據在 Ready 檢查。`csarc issue create` 另可在建立前檢查風險區塊。 | 需求有可判定起點；缺少 AC／風險區塊到 Ready 才阻擋。 |
| Draft PR | 連結 Issue、隔離工作區，允許證據尚未完成。 | 可持續實作，不會被誤認為可合併。 |
| Ready | `pr_lifecycle.py` 或 hosted policy 要求 AC 全勾選並逐項有證據；每個風險控制有證據或 `accepted: <理由>`。 | 缺項維持 Draft。`lifecycle` 含 `issues` 時，standalone／hotfix 另需有效 Approve 或 Admin-approve；Issue 變更後重新核准，緊急 hotfix 一律 Admin-approve。 |
| Review／Merge | 生命週期工具重查核准、驗證、head／tree、coverage digest 與授權。 | push 後舊核准失效；能用 lifecycle 時只經 `pr_lifecycle.py` 合併。人工合併記為 untraced。 |

工具狀態以 check／status 呈現，不為重複進度另加 PR 留言；生命週期、核准與稽核所需的固定紀錄仍保留。合併時只產生一則可識別、可重查的 durable summary。 {: .compact .mt-3}

### 4.5 Requirement evidence 最低要求 {: .mt-3}

PR 保留單一 Requirement evidence 區塊，逐項對應 AC1…ACn，記錄 regression test、目前 exact-head check，或附理由的人工證據；進入 Ready 時不得有 unknown 或 uncovered。確切欄位由目前版本的 PR template 與 SPEC-010 定義，不在手冊另造一套格式。 {: .compact}

### 4.6 GitHub 方案與權限差異 {: .mt-3}

{: table.stage-table.dense stage}
| Repository／權限條件 | 可用能力 | repo-template 的處理 |
|---|---|---|
| Public／Free+ | Actions、公開 Ruleset、公開安全掃描與 Pages。 | 依額度與組織政策啟用；未執行不算成功。 |
| Private／Free | 沒有 Ruleset 強制；API 完整讀回唯一維護者是唯一寫入身分時，lifecycle 才能合併。 | agent 以該維護者身分執行。另有寫入者時，有 exact head 的獨立核准，或合併者是擁有者以 `single_writer_merger` 指定的帳號（風險見 3.3），才由 lifecycle 合併；其餘或讀取不完整時只能人工合併並記為 untraced，後續改用 product-owned／verification-only 或升級方案。 |
| Private／Pro、Team+ | 可強制 private Ruleset；仍須 Repository admin 套用設定。 | 先 plan／回讀；權限不足時不宣稱已啟用。 |
| Private security entitlement | 私有程式碼的進階 CodeQL／安全能力。 | 未授權時回報缺口並執行既有替代檢查。 |
| Maintainer／Admin | maintain 可作一般核准；管理設定與 bypass 仍需 admin。 | 即時讀取角色，不由舊 permission 欄位猜測。 |
| Copilot／Project 存取 | 與 Repository 方案分開授權；organization／user Project 的寫入者不同。 | 無 Copilot 就改人工 review；Project 需 `project` scope 與該 Project 寫入權，無法確認時回報 unknown。 |

:::

::: sheet repository-map | 第 5 章 · 導入後的 Repository

第 5 章 · 導入後的 Repository {: div.eyebrow}

## 5. 導入後的 Repository

repo-template 只產生已選能力需要的內容；生成專案的驗證只測專案本身，不夾帶模板的 release／fixture 測試。

### 5.1 內容擁有權

{: table.stage-table.compact stage}
| 類別 | 範圍 | 更新原則 |
|---|---|---|
| 模板擁有 | `.csarc/` scripts／policies／操作文件／site 引擎；表單、PR template、Dependabot、workflows、`AGENTS.md`。 | 固定版本更新。 |
| 共同維護 | 語言工具設定檔與 `.gitignore`。 | 3-way／合併更新，衝突先確認。 |
| 共同維護（new） | README、LICENSE、安全文件、manifest 與容器檔。 | 3-way 更新，產品版本欄位不變。 |
| 專案擁有 | 產品程式、原生測試、產品 hook、商業規格、機密、部署與 docs 內容；existing 的 README／manifest。 | 模板不得覆寫或刪除。 |
| 產品狀態 | `.csarc/config.yml` 的使用者意圖、release manifest 與 `version.txt`。 | 設定由 `csarc update`、版本由發版流程寫入。 |

### 5.2 主要位置 {: .mt-3}

**提供條件：**「核心」是每個受管 Repository 都需要；「條件式」只在設定選到該能力時產生；「專案自有」由產品決定，repo-template 不強制建立。 {: .compact}

{: table.stage-table.dense stage}
| 提供條件 | 位置 | 內容與邊界 |
|---|---|---|
| 核心 | `.csarc/` | scripts、policies、文件由固定版本更新；設定／metadata 只經 `csarc update`，版本只由發版流程寫入。 |
| 條件式 | `.csarc/` | 選用能力的操作文件、repo-site 引擎及必要 runtime support；模板自測不下發，必要的工具測試只能放 `.csarc/tests/`。 |
| 核心 | `.github/` | Issue／PR 表單與安全通報入口；遠端 Repository 設定仍以 plan／apply 管理。 |
| 條件式 | `.github/` | Hosted CI、CodeQL、Dependabot 合併、Pages、容器等 workflow；`code_owner` 才有 CODEOWNERS。`dependabot.yml` 一律存在。 |
| 核心 | `AGENTS.md`、`.claude/CLAUDE.md`、`SECURITY.md` | AI 規則與掃描邊界；CLAUDE 只匯入 AGENTS；existing 的 SECURITY 屬產品。 |
| 條件式 | 語言程式、測試、manifest／lock | new 的 manifest 共同維護，程式／測試 seed 後歸專案；existing 不新增 starter 或 manifest。 |
| 專案自有 | `scripts/verify-product` 或設定的 hook | 只有產品需要額外 E2E／服務驗證時建立；不是 repo-template 工具或必要根目錄。 |
| 條件式／專案自有 | `docs/` | 依文件模式提供結構；規格、決策與內容由專案擁有，repo-site 產物才由工具重建。 |
| 條件式 | `Dockerfile`、`docker-compose.yml` | 只在啟用 container 能力時產生；啟用後仍需依產品調整。 |

**命名空間：**repo-template 的執行碼、fixture 與必要測試只在 `.csarc/`；平台、scanner、agent 固定位置與語言慣例設定檔除外。產品 lint、format、type check、test discovery 與 coverage 不涵蓋 `.csarc/`；根目錄 `tests/`、`scripts/` 及語言目錄留給產品。 {: .compact .mt-3}

### 5.3 權威文件 {: .mt-3}

本手冊是 repo-template 的產品政策與使用者承諾，隨 Release 放在模板 repository 的 `docs/handbook/`；生成專案不內含手冊，`.csarc/docs/csarc.md` 以 full SHA 連結所安裝版本。SPEC／ADR 保存精確契約與理由；`AGENTS.md`／CI policy 是 agent 的可執行規則。內容必須符合手冊，衝突即為 drift。 {: .compact}

:::

::: sheet updates-and-limits | 第 6 章 · 更新、故障與限制

第 6 章 · 更新、故障與限制 {: div.eyebrow}

## 6. 更新、故障與限制

### 6.1 模板更新

{: table.stage-table.compact stage}
| 階段 | 必要行為 | 安全條件 |
|---|---|---|
| 檢查 | 固定 CLI、模板 Release、Copier、Jinja 與 Git 行為版本，讀取 Repository、設定、平台現況及上次實際 render snapshot。 | 不使用浮動 `main`、未驗證的附件或 target 內可能過期的工具。 |
| 計畫 | 以 snapshot 重建舊側，再逐項列出新增、更新、刪除、衝突、設定變更、Action pin 漂移與 migration。 | 預覽與 apply 必須是同一份 final plan；舊側不得因缺值產生假衝突或幽靈檔案。 |
| 套用 | 交易式更新後重新驗證實際結果。 | 失敗維持原狀；不得留下部分寫入的修改。 |
| 平台 | Repository 檔案更新與 GitHub 設定分開處理並回讀。 | Copier 或 GitHub template 不會自動複製遠端設定。 |
| 治理 | 合併與驗證依可信 base 政策；放寬治理或修改 `.csarc/scripts` 使用專用 governance-switch 路線。 | schema 變更先讓 base reader 支援下一版，再切換 writer；candidate parser 只做自測。升級帶進 base 不認得的新設定時，PR 須帶 `governance-switch`，base 確認目標是已發布的 immutable 正式版，再以 `ast` 盤點該版的設定表，不執行其程式碼；不符就停止。 |

**舊版遷移：**外部 CLI 依來源 schema／Release 唯讀載入舊設定，每項改變都有 SPEC-008 報告列：退役鍵為 `retired`、承接鍵為 `exact`；既有 `admin_bypass` 保留，缺值改為 `always` 並以 `widened` 說明增加的權限與恢復方式。其他治理值只會是 `unchanged`、`exact` 或 `narrowed`；無等價值時以 `decision`／`setting-decision` 在寫入前決定。resolved render context 用來重建舊側；seed 沒有 native source 時，也提供新側 render 的值。runtime 只讀目前設定、native manifest、LICENSE 與受管常數，verify 不查 GitHub 取值。成功後只留 current schema，重跑不重複修改。 {: .compact .mt-3}

### 6.2 衝突、恢復與移除 {: .mt-3}

<div class="plain-columns compact">
<div>

**衝突：**不確定擁有權時先保留並回報，不以「模板較新」作為覆寫或刪除理由。

**恢復：**以計畫、報告及 Git 狀態判斷重跑點；外部寫入只完成一部分時，列出已完成與待修復的部分。

</div>
<div>

**移除：**由負責人決定保留哪些治理、文件與平台設定；確認產品仍可建置、測試、發布及維護。

**機密：**token、憑證及 populated `.env` 不得寫入 Repository 或更新報告。

</div>
</div>

### 6.3 狀態與外部故障

{: table.stage-table.compact stage}
| 狀態 | 常見原因 | 處理 |
|---|---|---|
| WAITING | Review、CI、權限、Release 或外部服務尚未完成。 | 保留工作與證據，等待精確條件；不重新開始。 |
| BLOCKED | 沒有安全且符合範圍的下一步，需取得決策或外部變更。 | 回報阻擋條件、已嘗試項目及責任人。 |
| DEGRADED | 平台無法強制控制，但 Repository-local 能力仍可用。 | 採替代控制，且不宣稱缺少的平台保證。 |
| 失敗 | 設定矛盾、驗證失敗、plan 不一致、stale evidence 或部分寫入。 | 依結構化輸出修正後重跑，不從訊息文字猜測成功。 |

### 6.4 已知限制 {: .mt-3}

repo-template 不提供通用部署、registry publishing、正式環境憑證或所有產品的 E2E，也無法阻止具權限者繞過工具直接修改 GitHub。UI 或 `gh pr merge --admin` 合併會略過 lifecycle，記為 untraced，並擋下下一次 `csarc-owned` 發版；local 搭配 `beta-only`／`always` 時，非 admin 寫入者也可能在 UI 合併。durable summary 也可被編輯或刪除，只能由 default branch 的 digest 發現。local 證據信任程度低於 hosted；不可觀察狀態一律回報 unknown。 {: .compact}

:::

::: sheet appendix | 附錄 · 快速參考

附錄 · 快速參考 {: div.eyebrow}

## 附錄：快速參考

### A.1 名詞

{: dl.terms.dense}
AC
: Issue「完成條件」的頂層 checkbox，依序識別為 AC1…ACn；Ready 後增刪或重排須重建對應。
Draft／Ready
: Draft 表示實作或證據未完成；Ready 表示 AC、風險控制及必要檢查已具備正式審核條件。
Focused／Fast／Full
: Focused 是開發中的局部檢查，不是 CI tier；Fast 與 Full 是由可信政策選擇的兩個正式驗證層級。
Head／tree
: PR 的提交版本與完整檔案樹識別，用於防止證據套用到不同內容。
Evidence
: 同時對應需求、精確版本、執行來源及結果；hosted 可重查，local 只留下 self-attested-local 紀錄。
Desired state
: Repository 保存的預期設定；是否真的生效仍須由 live capability check 證明。
ProjectV2
: GitHub Projects 的資料模型；Roadmap 使用其中的 Project item 與日期欄位。
物化／投影
: 物化是在交付 PR 寫入版本與 CHANGELOG；投影是把權威日期複製到 Project。
冪等／舊側
: 冪等是重跑不會重複修改；舊側是依上次 render context 重建、供三方合併的舊版。

### A.2 Prompt、CLI 與 Repository 工具箱 {: .mt-3}

{: table.stage-table.dense stage}
| 入口 | 功能 | 使用時機與限制 |
|---|---|---|
| Prompt | 描述目標，要求 agent 取得可信版本、顯示計畫並等待確認。 | Prompt 不執行或證明操作。 |
| 外部 CLI | 固定版本處理 bootstrap、status、migration 與 create／adopt／update。 | 由 agent 透過 `uvx` 暫時執行；更新時不信任 target 內舊工具。 |
| Repository 工具箱 | `.csarc/scripts/` 執行驗證、Issue／PR lifecycle、政策與 release。 | 隨專案版本化，供 AI、CI 與維護者使用。 |

### A.3 設定類別與常用指令 {: .mt-3}

`.csarc/config.yml` 只保存影響未來行為、無法安全重建的使用者意圖，鍵數由 schema 決定；CLI 只詢問偵測不到的選擇。 {: .compact}

{: table.stage-table.dense stage}
| 類別 | 持久設定 | 意義與限制 |
|---|---|---|
| 語言與文件 | `languages`、Python 支援（`latest` 或明確下限）、`documentation_mode`、`documentation_languages` | 決定產生的技術與文件能力；名稱與 package 不保存。Python 支援是使用者意圖，不由 manifest 反推。 |
| 治理與交付 | `verification_mode`、`admin_bypass`、`copilot_review`、`governance_mode`、`release_ownership`、`release_trigger`、`project_maturity`、`code_owner`、`single_writer_merger` | 保存無法由平台事實推導的政策；preset 不另存。`csarc-owned` 才發布；`product-owned` 只報 drift；`verification-only` 不管理發布。 |
| 安全與自動化 | CodeQL、排程、lifecycle 與 coverage 政策 | 初次確認後保存；live facts 或預設改變時維持 `unchanged`，只附建議。preset 只在 init／adopt 展開，update 不展開；名稱不保存。 |
| 安全通報 | `security_reporting_channel` | public 必填 GitHub 以外的私密管道；private 預設 Issue 說明句。 |
| 整合 | `container`、`project_verification_hook`、`github_project_url` | 空值停用；Project 只存完整 URL，不存 ID。 |

名稱、說明、授權與著作權人是 create／adopt 的一次性 seed，不存成設定；update 先讀 native source，沒有時沿用 snapshot，只能以一次性 `--data` 經 plan 修改。package／run command 能由 native manifest 唯一推導時不保存，否則保存一次決定。URL、visibility、方案與權限每次讀取；`schema_version`、模板來源、不可變 project mode 與舊側 snapshot 是不可手改的 metadata，缺漏或 digest 不符時先停止。 {: .compact .mt-3}

{: table.stage-table.command-table.dense headless}
| `csarc status` | 唯讀判斷 create／adopt／adoption-pending／update／current／policy-only-update／migrate。 |
| `csarc update --check --json` | 在寫入前產生可重查的更新報告與計畫。 |
| `./.csarc/scripts/verify-fast` | 依變更風險選擇日常驗證。 |
| `./.csarc/scripts/verify` | 執行完整專案驗證與產品 hook。 |
| `python3 .csarc/scripts/pr_lifecycle.py …` | 建立 Draft PR、進入審核、合併並留下稽核紀錄。 |
| `./.csarc/scripts/apply-repository-settings.sh plan` | 預覽需要管理員套用的 GitHub 設定。 |

<div class="callout mt-3 compact">

**使用原則：**本手冊定義「有哪些能力、如何使用、限制在哪裡」；Repository 內文件與工具提供目前版本的精確執行方式。兩者不一致就是 drift，不能自行選擇較寬鬆的說法。

</div>

:::

::: annex templates | 附錄 B · 範本格式

附錄 B · 範本格式 {: div.eyebrow}

## 附錄 B：範本格式

本附錄接在核准的 10 張主文之後，不屬於核准基準，也不受 10 張的頁數限制。它依使用者或 agent 實際經過的流程（建立／導入、規劃、開發、驗證與合併、發版、升級、例外與事後、整合）列出重要範本的實際格式。每個灰底區塊都在建置時，由它上方那段說明連結的權威檔案或工具程式直接產生，不是另外抄寫的版本；權威檔案一改，`scripts/build-handbook --check` 就會要求重建。`<…>` 是要填的位置，範例值都是虛構的。最後的 B.9 是所有範本的索引，列出位置與出現條件。 {: .compact}

### B.1 建立／導入 {: .mt-3}

建立或導入時沒有要手填的範本：`csarc init`／`adopt` 只詢問偵測不到的選擇，再產生 `.csarc/config.yml`、`.csarc/provenance.json`、兩份 `SECURITY.md`、LICENSE、`.csarc/docs/csarc.md` 與 agent 規則。設定只用 `csarc update --data KEY=VALUE` 修改，provenance 不可手改；各檔位置與出現條件見 B.9。 {: .compact}

### B.2 規劃 {: .mt-3}

**開 Issue：Task 表單**　誰填：使用者或 agent；何時：每一項能獨立交付的工作開始前。送出後的 Issue 本文就是下列格式，「完成條件」的每個頂層 checkbox 依序成為 AC1…ACn。來源：[`task.yml`](../../.github/ISSUE_TEMPLATE/task.yml) {: .compact .mt-3}

::: format issue-form .github/ISSUE_TEMPLATE/task.yml

**風險與控制區塊**　誰填：Issue assignee；何時：開 Issue 時填在「補充」，Ready 前會被檢查。每個風險一列；只改一般文件時改用唯一一列 `R0`。來源：[`SPEC-010`](../specs/SPEC-010-issue-risk-controls.md) {: .compact .mt-3}

::: format fence docs/specs/SPEC-010-issue-risk-controls.md #### 風險與控制

:::

::: annex templates-issues | 附錄 B · 範本格式

**開 Issue：Bug 表單**　誰填：使用者或 agent；何時：回報能重現的非預期行為，hotfix 也從這張開始。來源：[`bug.yml`](../../.github/ISSUE_TEMPLATE/bug.yml) {: .compact}

::: format issue-form .github/ISSUE_TEMPLATE/bug.yml

**開 Issue：Feature 表單**　誰填：需求負責人；何時：需要多張工作才能完成的共同成果。來源：[`feature.yml`](../../.github/ISSUE_TEMPLATE/feature.yml) {: .compact .mt-3}

::: format issue-form .github/ISSUE_TEMPLATE/feature.yml

:::

::: annex templates-issues-2 | 附錄 B · 範本格式

**開 Issue：Documentation 表單**　誰填：使用者或 agent；何時：只改一般文件，「補充」預填 `R0`。來源：[`documentation.yml`](../../.github/ISSUE_TEMPLATE/documentation.yml) {: .compact}

::: format issue-form .github/ISSUE_TEMPLATE/documentation.yml

**Milestone description**　誰填：Milestone 負責人；何時：建立有真實 due date 的 Milestone 時，填在 Milestone 本身的描述欄。來源：[`milestone-description.md`](../milestone-description.md) {: .compact .mt-3}

::: format fence docs/milestone-description.md ## Problem

:::

::: annex templates-milestone | 附錄 B · 範本格式

**Milestone tracker 本文**　誰填：Milestone 負責人；何時：與 Milestone 一起由 `scripts/create-milestone` 建立，`lifecycle` 含 `milestones` 時才有。來源：[`create-milestone`](../../scripts/create-milestone) {: .compact}

::: format tracker

**Checkpoints 區塊**　誰填：Milestone 負責人；何時：核准前寫在 tracker 的 Proposal 內，宣告哪些 Issue 一起發一個 beta。來源：[`milestone-description.md`](../milestone-description.md) {: .compact .mt-3}

::: format fence docs/milestone-description.md ### Checkpoints

### B.3 開發 {: .mt-3}

**Branch 名稱與 PR 標題**　誰填：agent 或 PR 作者；何時：建立 branch 與 PR 時。規則取自 `gh-issue-develop` 與 `title` check 實際使用的 pattern。來源：[`AGENTS.md`](../../AGENTS.md) 工作迴圈第 12 步 {: .compact .mt-3}

::: format conventions

:::

::: annex templates-develop | 附錄 B · 範本格式

**PR 本文**　誰填：PR 作者（通常是 agent）；何時：以 `pr_lifecycle.py create` 建立 Draft PR 時，Ready 前把完成清單、Requirement evidence 與文件一致性填好。來源：[`pull_request_template.md`](../../.github/pull_request_template.md) {: .compact}

::: format file .github/pull_request_template.md

:::

::: annex templates-evidence | 附錄 B · 範本格式

**Requirement evidence 填寫範例**　誰填：PR 作者；何時：Ready 前，每個 AC 與風險 ID 各一列 exact-head 證據。來源：[`SPEC-010`](../specs/SPEC-010-issue-risk-controls.md) {: .compact}

::: format fence docs/specs/SPEC-010-issue-risk-controls.md ## Requirement evidence

**ADR**　誰填：專案維護者或 agent；何時：使用者確認了會持續影響架構、工具或相容性的決定。生成專案在 `documentation_mode` 不是 `off` 時有同一份規則。來源：[`docs/adr/README.md`](../adr/README.md) {: .compact .mt-3}

::: format fence docs/adr/README.md # Choose a durable option

:::

::: annex templates-spec | 附錄 B · 範本格式

**SPEC**　誰填：專案維護者或 agent；何時：需要可驗收的能力規格時，從範例複製。來源：[`SPEC-001-example.md.jinja`](../../template/docs/specs/SPEC-001-example.md.jinja) {: .compact}

::: format file template/docs/specs/SPEC-001-example.md.jinja

:::

::: annex templates-merge | 附錄 B · 範本格式

### B.4 驗證與合併

**合併授權留言**　誰填：執行合併的 admin 本人；何時：`admin_bypass` 不是 `off`、以留言取代核准時，取得 lease 後貼在 PR。格式由 `pr_lifecycle.authorization_statement()` 產生。來源：[`pr_lifecycle.py`](../../scripts/pr_lifecycle.py) {: .compact .mt-3}

::: format authorization

**合併 commit trailer**　誰填：`pr_lifecycle.py merge` 自動寫入；何時：每次 squash 合併。它是稽核紀錄，不是驗證證據。來源：[`merge-trailers.json`](../../policies/merge-trailers.json) {: .compact .mt-3}

::: format trailers

### B.5 發版 {: .mt-3}

**CHANGELOG 段落**　誰填：`csarc-owned` 時由 `release_policy.py prepare-candidate` 在交付 PR 物化；何時：release-worthy 的最後一個 commit。下例是用同一個 writer 對虛構 commit 產生的結果；`docs`、`chore` 等類型不列入。GitHub Release notes 由 `--generate-notes` 依已合併 PR 標題列出 What's Changed 與比較連結，不另填。來源：[`release_policy.py`](../../scripts/release_policy.py) {: .compact .mt-3}

::: format changelog

:::

::: annex templates-upgrade | 附錄 B · 範本格式

### B.6 升級

**導入／更新報告**　誰填：CLI 產生，人閱讀與決定；何時：`csarc adopt`／`update --check` 時寫在 repository 外。Markdown 報告固定這九節，先看第一節。來源：[`SPEC-008`](../specs/SPEC-008-lifecycle-report-format.md) {: .compact .mt-3}

::: format report

### B.7 例外與事後 {: .mt-3}

**Hotfix 事後紀錄**　誰填：hotfix 作者；何時：hotfix 合併後，寫在 hotfix Issue「補充」或 PR 的 Requirement evidence。來源：[`ci-policy.md`](../ci-policy.md) {: .compact .mt-3}

::: format record docs/ci-policy.md Hotfix 事後紀錄（#1139）

:::

::: annex templates-security | 附錄 B · 範本格式

**安全通報私密紀錄**　誰填：收件維護者；何時：收到私密漏洞通報後，只存在私密管道。來源：[`security-response.md`](../security-response.md) {: .compact}

::: format record docs/security-response.md 私密紀錄格式

:::

::: annex templates-records | 附錄 B · 範本格式

**Pilot 紀錄**　誰填：pilot 執行者；何時：每次 consumer 導入試行，寫在該 consumer 的 pilot Issue。來源：[`pilot-adoption.md`](../pilot-adoption.md#pilot-紀錄格式) {: .compact}

::: format record docs/pilot-adoption.md Pilot 紀錄格式

**Operator-independence run 紀錄**　誰填：未參與該 Milestone 的新 session 或人；何時：stable promotion 前。來源：[`pilot-adoption.md`](../pilot-adoption.md#operator-independence-run) {: .compact .mt-3}

::: format record docs/pilot-adoption.md Operator-independence run

:::

::: annex templates-promotion | 附錄 B · 範本格式

**Promotion checklist**　誰填：Milestone 負責人或 agent；何時：每次 Milestone promotion，依序執行。來源：[`milestone-description.md`](../milestone-description.md#promotion-checklist) {: .compact}

::: format checklist docs/milestone-description.md Promotion checklist

### B.8 整合 {: .mt-3}

**ProjectV2 設定**　誰填：專案維護者；何時：設定 `github_project_url` 後、第一次同步前。生成的 `.csarc/docs/csarc.md` 只在設定時出現這一節。來源：[`csarc.md.jinja`](../../template/.csarc/docs/csarc.md.jinja) {: .compact .mt-3}

::: format section template/.csarc/docs/csarc.md.jinja Project Roadmap 設定

:::

::: annex templates-index | 附錄 B · 範本格式

### B.9 索引

{: table.stage-table.dense stage}
| 範本 | 用途 | 誰填 | 位置與出現條件 |
|---|---|---|---|
| 設定檔 | 只保存無法安全重建的使用者意圖；改值用 `csarc update --data KEY=VALUE` | CLI 產生，人只用指令改 | `.csarc/config.yml`；契約見 [`SPEC-009`](../specs/SPEC-009-project-settings.md)；一律 render |
| Provenance | schema、模板來源、`project_mode` 與舊側 snapshot；以 digest 防改 | CLI 寫入，不可手改 | `.csarc/provenance.json`；契約見 [`SPEC-009`](../specs/SPEC-009-project-settings.md)；一律寫入 |
| 掃描政策 | 說明安全掃描器的政策與範圍 | 工具產生 | [`SECURITY.md`](../../SECURITY.md)；新專案 render，既有專案保留自己的檔案 |
| 漏洞通報政策 | 人工私密通報入口；public repository 必須有 GitHub 以外的管道 | 維護者在 init／adopt 提供管道 | [`.github/SECURITY.md`](../../.github/SECURITY.md)；新專案依 visibility render，既有專案保留自己的檔案 |
| LICENSE | 授權條文 | init／adopt 的一次性 seed | [`template/LICENSE.jinja`](../../template/LICENSE.jinja)；`project_license` 不是 `custom` 的新專案；既有專案保留自己的檔案 |
| 操作指南 | 依本專案設定產生的設定表、工作流程、驗證與合併、發版、更新與恢復 | 工具產生，不手改 | [`template/.csarc/docs/csarc.md.jinja`](../../template/.csarc/docs/csarc.md.jinja)；生成 `.csarc/docs/csarc.md`，一律 render |
| Agent 工作規則 | agent 的可執行規則；`AGENTS.md` 只有 CSARC 區塊由工具更新 | 工具產生 | [`template/.csarc/docs/agent-workflow.md.jinja`](../../template/.csarc/docs/agent-workflow.md.jinja)；生成 `AGENTS.md` 與 `.csarc/docs/agent-workflow.md`，一律 render |
| 文件地圖 | 說明 specs、ADR、Issue 與測試各自回答什麼問題 | 工具產生，專案可改 | [`template/docs/README.md.jinja`](../../template/docs/README.md.jinja)；`documentation_mode` 不是 `off` 時 |
| Milestone description | Milestone 描述欄的七段格式與建立、預檢、收尾步驟 | Milestone 負責人 | [`docs/milestone-description.md`](../milestone-description.md)；生成 `.csarc/docs/milestone-description.md` 為精簡版；`lifecycle` 含 `milestones` 時 |
| Milestone tracker 表單 | 單一 tracker：Proposal、Completion evidence、Early termination、Promotion，可宣告 `### Checkpoints` | Milestone 負責人 | [`milestone-tracker.yml`](../../.github/ISSUE_TEMPLATE/milestone-tracker.yml)；`lifecycle` 含 `milestones` 時 |
| Issue 表單：Task | 一項能獨立完成、驗證、交付的工作；最常用 | 使用者或 agent | [`task.yml`](../../.github/ISSUE_TEMPLATE/task.yml)；一律 render |
| Issue 表單：Bug | 回報能重現的非預期行為；hotfix 也從這裡開始 | 使用者或 agent | [`bug.yml`](../../.github/ISSUE_TEMPLATE/bug.yml)；一律 render |
| Issue 表單：Feature | 需要多張工作才能完成的共同成果 | 需求負責人 | [`feature.yml`](../../.github/ISSUE_TEMPLATE/feature.yml)；一律 render |
| Issue 表單：Documentation | 只改一般文件；`AGENTS.md`、`SECURITY.md` 與 CI policy 不適用 | 使用者或 agent | [`documentation.yml`](../../.github/ISSUE_TEMPLATE/documentation.yml)；一律 render |

:::

::: annex templates-index-2 | 附錄 B · 範本格式

{: table.stage-table.dense stage}
| 範本 | 用途 | 誰填 | 位置與出現條件 |
|---|---|---|---|
| Issue 表單設定 | 關閉空白 Issue，只能從表單建立 | 不需填 | [`config.yml`](../../.github/ISSUE_TEMPLATE/config.yml)；一律 render |
| 風險與控制區塊 | 每個風險一列（ID、類別、等級、控制、預計證據、Owner），或唯一一列 `R0`；Ready 前檢查 | Issue assignee | 表單「補充」預填；契約見 [`SPEC-010`](../specs/SPEC-010-issue-risk-controls.md)；隨表單 render |
| Branch 命名 | `type/<Issue>-<slug>`；`gh-issue-develop` 建立前檢查名稱並連結 Issue | agent 或 PR 作者 | [`gh-issue-develop`](../../scripts/gh-issue-develop)；生成 `.csarc/scripts/gh-issue-develop`，一律 render |
| PR 標題與 commit 慣例 | `type(scope): summary`；squash commit 與 release notes 取自 PR 標題，類型決定 release intent | PR 作者 | [`AGENTS.md`](../../AGENTS.md) 工作迴圈第 12 步；生成 `.csarc/docs/agent-workflow.md` 第 12 步；由 `title` check 強制 |
| PR template | Purpose、完成清單、Requirement evidence、文件一致性、補充 | PR 作者（通常是 agent） | [`pull_request_template.md`](../../.github/pull_request_template.md)；一律 render |
| Requirement evidence | 每個 AC 與風險 ID 對應一項 exact-head 證據；Ready 前不得缺漏或未知 | PR 作者 | PR template 的 `## Requirement evidence`；契約見 [`SPEC-010`](../specs/SPEC-010-issue-risk-controls.md) |
| 文件一致性紀錄 | `aligned` 或附理由的 `not-applicable`；`drift`、`inconclusive` 擋下交付 | PR 作者 | PR template 的 `## 文件一致性`；規則見 [`documentation-policy.md`](../documentation-policy.md) |
| ADR | 記錄已確認、會持續影響架構、工具或相容性的決定 | 專案維護者或 agent | [`docs/adr/README.md`](../adr/README.md) 的規則與範例；生成專案在 `documentation_mode` 不是 `off` 時有同一份 |
| SPEC | front matter 與 Problem、Outcome、AC、Out of scope、Verification 等段落 | 專案維護者或 agent | [`SPEC-001-example.md`](../specs/SPEC-001-example.md)；生成 `docs/specs/SPEC-001-example.md` 在 `documentation_mode` 不是 `off` 時；`code_owner` 空白時 `owner` 為空 |
| 站台設定範例 | 網站上 `config-guidance` 區塊使用的設定範例 | 模板維護者 | [`config_examples.json`](../../site/data/config_examples.json)；只在模板 repository，不 render |
| 合併授權留言 | admin 以 exact-head 留言取代核准 | 執行合併的 admin | 生成的 `.csarc/docs/csarc.md`「驗證與合併」；`admin_bypass` 不是 `off` 時 |
| 合併 commit trailer | squash commit 固定的 `CSARC-*` trailer；是稽核紀錄，不是驗證證據 | `pr_lifecycle.py merge` 自動寫入 | [`merge-trailers.json`](../../policies/merge-trailers.json)；生成 `.csarc/policies/merge-trailers.json`，一律 render |
| 驗證證據 | hosted：綁定 repository、head／tree、tier 與 runner 的 `verify` 結果；local：self-attested 紀錄 | CI 或 `verify-fast` 自動產生 | hosted 以 `check-trusted-verification` 讀取；local 存在 Git metadata，不進 repository；規則見 [`ci-policy.md`](../ci-policy.md) |

:::

::: annex templates-index-3 | 附錄 B · 範本格式

{: table.stage-table.dense stage}
| 範本 | 用途 | 誰填 | 位置與出現條件 |
|---|---|---|---|
| 風險登錄冊 | 從 Issue 與 PR 計算的唯讀登錄冊 | `csarc risk register` 產生 | 不 commit；格式 `csarc-risk-register` 見 [`SPEC-010`](../specs/SPEC-010-issue-risk-controls.md) |
| CHANGELOG | 版本紀錄 | `csarc-owned` 時由 `prepare-candidate` 物化，其他由產品維護 | [`template/CHANGELOG.md`](../../template/CHANGELOG.md)；只有新專案 render，既有專案保留自己的 |
| Release notes | Release 說明文字的最低內容，取自已合併 PR 標題 | `publish-release` 產生 | [`ci-policy.md`](../ci-policy.md)「Release 說明文字的最低格式規範」；`release_ownership` 是 `csarc-owned` 時 |
| `release-prompt.txt` | 給使用者複製的固定版本 CLI 呼叫 | `publish-release` 產生 | 模板 Release 的 asset；只在模板 repository |
| 導入／更新報告 | plan、JSON 與 Markdown 報告、update 的 final plan；先看 Items requiring your decision | CLI 產生，人閱讀與決定 | repository 外；格式見 [`SPEC-008`](../specs/SPEC-008-lifecycle-report-format.md) |
| 設定 plan／apply | 遠端 repository 設定的預覽與套用；先看 plan 再 apply | 工具產生，管理員審核 | [`apply-repository-settings.sh`](../../template/.csarc/scripts/apply-repository-settings.sh)；一律 render |
| Hotfix 事後紀錄 | 原因、影響範圍、exact base／head、為何不能等 Milestone、授權來源、驗證證據、後續 Issue | hotfix 作者 | 寫在 hotfix Issue「補充」或 PR 的 Requirement evidence；欄位見 [`ci-policy.md`](../ci-policy.md)「Hotfix 事後紀錄」；只在模板 repository |
| 安全通報處理程序 | 收到私密通報後的記錄、確認、修正、公開與結案；細節只留私密管道 | 收件維護者 | [`security-response.md`](../security-response.md)；只在模板 repository，生成專案自訂 |
| Pilot 紀錄 | 記錄 consumer 導入試行，含未達進場條件的失敗 run | pilot 執行者 | [`docs/pilot-adoption.md`](../pilot-adoption.md#pilot-紀錄格式)；只在模板 repository，不 render |
| Operator-independence run | stable promotion 前證明未參與實作者只靠文件能完成升級 | 未參與該 Milestone 的新 session 或人 | [`docs/pilot-adoption.md`](../pilot-adoption.md#operator-independence-run)；只在模板 repository，不 render |
| Promotion checklist | Milestone promotion 的九步：凍結 `main`、sync、bridge、合併、Tag／Release 讀回、收尾與 tracker 關閉順序 | Milestone 負責人或 agent | [`milestone-description.md`](../milestone-description.md#promotion-checklist)；只在模板 repository |
| ProjectV2 設定 | 第一次同步前建立 DATE 欄位並確認 scope 與寫入權 | 專案維護者 | 生成的 `.csarc/docs/csarc.md`「Project Roadmap 設定」；設定 `github_project_url` 時 |
| 寫作指引 | 英文與中文文字的寫作規則、腳本訊息的四種句型與例外；agent 新寫或修改文字時遵守 | 模板維護者 | [`writing-guide.en.md`](../writing-guide.en.md)、[`writing-guide.md`](../writing-guide.md)；生成 `.csarc/docs/writing-guide.en.md` 一律 render，`writing-guide.md` 在文件語言含繁體中文時 |

:::
