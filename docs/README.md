# 文件與 Durable Project Memory 地圖

本 repo 把 **Durable Project Memory（持久化專案記憶）** 定義成可版本控制、可審查、可追溯且能跨 session 讀取的專案知識。這是 SDD、ADR、GitHub history 與 executable evidence 的組合，不是一套新的工具或單一大文件。

## Canonical layers

| 問題 | Canonical source | 用途與維護方式 |
| --- | --- | --- |
| 現在必須做到什麼？ | `docs/specs/` | 多份 living SDD；每份能力有穩定 ID、狀態、驗收、驗證與來源 |
| 為什麼這樣選？ | `docs/adr/` | Architecture Decision Records（ADR）；flow-forward 保存 accepted、superseded、rejected 與 unresolved 理由 |
| 何時提案與交付？ | GitHub Issue／PR／commit | 原始工作時間線、討論、changed files 與交付證據，不批次重寫 |
| 行為是否仍成立？ | tests／CI／release／pilot evidence | TDD／BDD 的 durable executable evidence；失敗要能被重現 |
| Agent 如何找到以上內容？ | `AGENTS.md` 與本頁 | 穩定導航與工作規則，不複製所有細節 |

任務 plan、即時 status 與草稿可協助當下工作，但不是平行的永久真相來源。完成或重大轉向時，將必要摘要回 spec、decision record 或 work item。

## SDD, ADR, TDD, and BDD

- **SDD（Spec-Driven Development）** 以規格驅動工作；其 durable artifacts 位於 `docs/specs/`，保存 intent、constraints、non-goals 與 acceptance contract。不要與同樣常縮寫為 SDD 的 Software Design Document 混為單一強制格式。
- **ADR（Architecture Decision Records）** 位於 `docs/adr/`，保存選擇理由、替代方案、ownership、限制與重新評估條件。
- **TDD（Test-Driven Development）** 由 tests、修正 PR 與 CI 結果保存；不要求逐次記錄 red／green／refactor 暫態。
- **BDD（Behavior-Driven Development）** 只在跨角色、對外可觀察行為需要 living documentation 時，加入 declarative Given／When／Then 或等價 scenario；預設不新增 Cucumber／Gherkin dependency。

完整聊天、模型 chain-of-thought、敏感資訊與未確認推論都不屬於 project memory。

從舊版模板更新的專案可能仍有 project-owned `docs/decisions/`。搜尋與驗證時同時讀取該目錄；新紀錄使用 `docs/adr/`，模板不會自動移動或覆寫舊內容。

## Current specifications

- [`SPEC-001-example.md`](specs/SPEC-001-example.md) — draft schema example
- [`SPEC-002-durable-project-memory.md`](specs/SPEC-002-durable-project-memory.md) — memory layers、traceability 與 SDD／ADR／TDD／BDD 邊界
- [`SPEC-003-reproducible-template-lifecycle.md`](specs/SPEC-003-reproducible-template-lifecycle.md) — create／adopt／update 與 ownership
- [`SPEC-004-capability-aware-governed-delivery.md`](specs/SPEC-004-capability-aware-governed-delivery.md) — GitHub capabilities、branches、PR 與 promotion
- [`SPEC-005-continuous-verification-evidence.md`](specs/SPEC-005-continuous-verification-evidence.md) — verification tiers、regressions 與 evidence
- [`SPEC-006-trusted-release-provenance.md`](specs/SPEC-006-trusted-release-provenance.md) — release、security、dependencies 與 provenance
- [`SPEC-007-portable-decision-documentation.md`](specs/SPEC-007-portable-decision-documentation.md) — canonical docs 與 portable presentation

`tracking: issue` 或預設值會同步 Task Issue；`tracking: story` 同步可容納 native subissues 的 Feature parent；`tracking: none` 用於已存在、仍需持續維護但不應新建 work item 的 current spec。Milestone 另作有 due date 的 delivery／release bucket，不再兼任 story identity。

## Decision records

- [`durable-project-memory.md`](adr/durable-project-memory.md)
- [`template-lifecycle-and-ownership.md`](adr/template-lifecycle-and-ownership.md)
- [`capability-aware-governance.md`](adr/capability-aware-governance.md)
- [`staged-delivery-and-verification.md`](adr/staged-delivery-and-verification.md)
- [`release-security-and-dependencies.md`](adr/release-security-and-dependencies.md)
- [`spec-story-and-work-items.md`](adr/spec-story-and-work-items.md)
- [`agent-collaboration.md`](adr/agent-collaboration.md)
- [`portable-decision-site.md`](adr/portable-decision-site.md)

2026-08-24 的完整 GitHub 盤點、2026-08-25 的 work-item metadata normalization 與每條決策線對照，見 [`history-audit-2026-08.md`](history-audit-2026-08.md)。

## Other documentation

| 類型 | 路徑 | 用途與維護方式 |
| --- | --- | --- |
| 單檔交付物 | `docs/index.html` | 由 `site/` 重建的 portable presentation；內嵌樣式、程式與媒體，不直接編輯 |
| 網站來源 | `site/` | 分開維護 HTML 內容、特殊視覺、互動與原始圖片；詳見 `site/README.md` |
| 操作契約 | `docs/agent-install.md`、`docs/milestone-description.md` | 已發布且可能由固定版本 URL 讀取的介面；路徑保持穩定 |
| Runbook | `docs/live-integration.md`、`docs/artifact-consumption.md` | 維護者執行線上驗證或排查交付鏈時使用 |
| 實證 | `docs/pilot-adoption.md` | 真實 consuming repository 的採用、更新與限制證據 |

## 新決策如何進來

1. 先讀相關 current spec，再搜尋 `docs/adr/` 與 open／closed Issues。
2. 在既有或新 Issue 摘要已確認限制、替代方案與先前決策如何被沿用、取代或駁回。
3. 透過 scoped PR 更新 current spec 與對應 ADR；若只有實作細節改變，不製造無意義的 decision record。
4. 若決策需要出現在簡報，同一個 PR 更新 `site/` 並重建 `docs/index.html`。

## 維護原則

- 規格改變時更新 current SDD；重大取捨改變時新增或更新 ADR，舊理由以 flow-forward disposition 保留。
- 新增內容前先判斷它是使用指南、runbook、ADR、實證、規格或交付物，不以檔案格式決定分類。
- `docs/agent-install.md` 等公開契約優先維持穩定路徑；需要分類時由本頁導覽，不為整理目錄破壞既有 URL。
- `docs/index.html` 是 presentation，不是唯一來源；修改 `site/` 後執行 `uv run --no-project python scripts/render_site.py`，`--check` 只比對 committed bundle，不改檔案。
- `docs/index.html` 必須保持單檔、無 runtime 外部 CSS、JavaScript、font 或 image 依賴。超連結可以指向外部參考資料，但離線開啟不能因網路不可用而失去簡報內容或操作能力。`noindex`／`robots.txt` 不是 access control。
- 網站呈現、來源、模板 ownership 與 GitHub capability fallback 的完整選型見 [`adr/portable-decision-site.md`](adr/portable-decision-site.md)。
- Root 保存本 repo 的真實歷史；Copier template 只下發結構、說明與範例，並保留下游 project-owned memory。
