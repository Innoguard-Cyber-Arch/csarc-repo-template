# Historical decision coverage ledger — 2026-08-24

本檔是 Issue [#223](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/223) 的一次性 backfill ledger。它證明哪些 GitHub 歷史被讀取、如何重跑，以及哪些內容沒有存在於平台；它不是另一份 current spec 或 decision log。

## Cutoff and result

- **Repository:** `Innoguard-Cyber-Arch/csarc-repo-template`
- **Cutoff:** `2026-08-24T13:08:45Z`（#223 建立時間），納入編號不晚於 `#221` 的既有項目
- **Retrieval:** 2026-08-24，以 GitHub REST／GraphQL API 的當時內容建立快照
- **Issues:** 103/103 讀取成功；84 closed、19 open；讀取全部 body 與 51 則 comments（分布於 33 張 Issues）
- **Pull requests:** 118/118 讀取成功；86 merged、21 closed without merge、11 open；讀取全部 body、90 則 comments、219 個 commit entries 與 1,079 個 changed-file entries
- **Review evidence:** 118/118 張 PR 的 reviews endpoint 與 GraphQL `reviewThreads` 讀取成功，共 0 reviews、0 review threads；這是「沒有該類資料」，不是漏讀
- **Closing relationships:** 91/118 張 PR 有 GitHub `closingIssuesReferences`；其餘 27 張包含制度建立前的 #1–#5、被後繼 PR 取代的 stacked work，以及 cutoff 時仍 open 的 #210–#221
- **格式觀察:** 102/103 張 Issues 符合目前「類型／問題／完成條件／補充」結構；116/118 張 PRs 符合目前「Purpose／完成清單／補充」結構。格式一致不代表決策已成為 canonical ADR。

本盤點沒有改寫、重開或重新分類任何歷史 work item。Open Issue／PR 只記為 proposed／unresolved，不因 acceptance checkbox 已勾選就冒充已合併能力。

## Read method

使用已登入的 GitHub CLI。先以 REST issues endpoint 分頁抓取 Issue 與 PR 共用的 221 筆 body，再依 `number <= 221` 與 `pull_request` 欄位固定集合；接著對每個編號分頁抓取 comments 與 timeline，對每張 PR 分頁抓取 reviews、commits 與 files。最後用 GraphQL 分頁交叉核對 `closingIssuesReferences`：

```bash
repo=Innoguard-Cyber-Arch/csarc-repo-template
gh api --paginate --slurp \
  "repos/$repo/issues?state=all&per_page=100&direction=asc"
gh api --paginate --slurp "repos/$repo/issues/<number>/comments?per_page=100"
gh api --paginate --slurp "repos/$repo/issues/<number>/timeline?per_page=100"
gh api --paginate --slurp "repos/$repo/pulls/<number>/reviews?per_page=100"
gh api --paginate --slurp "repos/$repo/pulls/<number>/commits?per_page=100"
gh api --paginate --slurp "repos/$repo/pulls/<number>/files?per_page=100"
gh api graphql -f query='<paginated pullRequests query with
reviewThreads and closingIssuesReferences>'
```

實際 endpoint coverage 為：item body 221/221、comments 221/221、timeline 221/221、PR reviews 118/118、PR commits 118/118、PR files 118/118、GraphQL review threads／closing relationships 118/118；0 個 endpoint error、0 個最終缺口。Issues 依 `7–40`、`41–80`、`81–120`、`121–160`、`161–200`、`201–221` 分批閱讀；PR 依 `1–40`、`41–80`、`81–120`、`121–160`、`161–193`、`210–221` 分批閱讀。遇到輸出截斷時，改用較小編號集合重讀。

重跑時應把每個 `--slurp` 結果依 endpoint／編號分檔，保存新的 retrieval time 與 cutoff，不直接覆寫本快照；平台內容可能在其後新增或修改。API 失敗時保留已完成頁面與失敗編號，只重試缺少的 endpoint／page，全部成功後才重算 ledger；不得以 title／label 補推論。

## Covered Issues

#7, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #23, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #62, #64, #65, #67, #70, #71, #72, #73, #74, #75, #76, #77, #78, #79, #87, #91, #93, #94, #98, #99, #100, #101, #102, #103, #104, #105, #106, #107, #108, #110, #113, #116, #122, #123, #126, #140, #141, #142, #144, #145, #146, #148, #155, #157, #159, #162, #163, #166, #167, #168, #169, #170, #171, #177, #178, #179, #180, #181, #182, #183, #184, #189, #194, #195, #196, #197, #198, #199, #200, #201, #202, #203, #204, #205, #206, #207, #208, #209, #219.

## Covered pull requests

#1, #2, #3, #4, #5, #6, #8, #19, #20, #21, #22, #24, #25, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, #51, #52, #53, #54, #55, #56, #57, #58, #59, #60, #61, #63, #66, #68, #69, #80, #81, #82, #83, #84, #85, #86, #88, #89, #90, #92, #95, #96, #97, #109, #111, #112, #114, #115, #117, #118, #119, #120, #121, #124, #125, #127, #128, #129, #130, #131, #132, #133, #134, #135, #136, #137, #138, #139, #143, #147, #149, #150, #151, #152, #153, #154, #156, #158, #160, #161, #164, #165, #172, #173, #174, #175, #176, #185, #186, #187, #188, #190, #191, #192, #193, #210, #211, #212, #213, #214, #215, #216, #217, #218, #220, #221.

## Canonical backfill map

| Decision line | Current SDD | ADR／decision record | Representative history | Cutoff status |
| --- | --- | --- | --- | --- |
| Durable project memory | [SPEC-002](specs/SPEC-002-durable-project-memory.md) | [Durable project memory](adr/durable-project-memory.md) | #34/#58, #145/#147, #177/#185, #223 | Accepted by #223; delivery pending |
| Template and update ownership | [SPEC-003](specs/SPEC-003-reproducible-template-lifecycle.md) | [Template lifecycle and ownership](adr/template-lifecycle-and-ownership.md) | #7/#8, #31/#53, #76/#88, #116/#124 | Current plus explicit open gaps |
| GitHub governance and capabilities | [SPEC-004](specs/SPEC-004-capability-aware-governed-delivery.md) | [Capability-aware governance](adr/capability-aware-governance.md) | #18/#25, #65/#66, #87/#90, #123/#128, #146/#154 | Current; hosted billing unresolved |
| Branching and delivery | [SPEC-004](specs/SPEC-004-capability-aware-governed-delivery.md) | [Staged delivery and verification](adr/staged-delivery-and-verification.md) | #122/#125, #179–#184/#186–#193 | Current |
| Continuous verification | [SPEC-005](specs/SPEC-005-continuous-verification-evidence.md) | [Staged delivery and verification](adr/staged-delivery-and-verification.md) | #37/#52, #99/#136–#137, #140/#150, #171/#173 | Current; hosted measurement unresolved |
| Release and provenance | [SPEC-006](specs/SPEC-006-trusted-release-provenance.md) | [Release, security, and dependencies](adr/release-security-and-dependencies.md) | #29/#60, #98/#118/#129–#135, #123/#128, #142/#151 | Current plus open distribution work |
| Security and dependencies | [SPEC-006](specs/SPEC-006-trusted-release-provenance.md) | [Release, security, and dependencies](adr/release-security-and-dependencies.md) | #35/#92, #36/#51, #74/#111, #101/#119, #103/#120, #110/#143 | Current |
| Spec, story, and work item | [SPEC-002](specs/SPEC-002-durable-project-memory.md) | [Spec, story, and work-item boundaries](adr/spec-story-and-work-items.md) | #15/#20, #34/#58, #77/#89, #122/#125, #148/#153, #159/#161 | Current |
| Agent collaboration | [SPEC-002](specs/SPEC-002-durable-project-memory.md) | [Agent collaboration and durable handoff](adr/agent-collaboration.md) | #126/#127, #145/#147, #155/#158, #171/#173 | Current; startup cleanup open |
| Documentation and presentation | [SPEC-007](specs/SPEC-007-portable-decision-documentation.md) | [Portable decision site](adr/portable-decision-site.md) | #166–#169/#172–#176, #177/#185, #178/#187, #205–#209 | Current renderer; Hugo cutover not active |

## Historical cautions retained

- PRs #38–#49 與 #80、#83、#85、#86、#131、#133、#135、#149 是 closed／superseded work，不當作 merged state；其後繼 PR 仍保留來源。
- #35／PR #50 曾移除 OSV permission，live startup failure 後由 PR #92 恢復；最後決策以實際 upstream permission requirement 為準。
- #62 的全面 fail-closed governance gate 被 #65 收窄；GitHub Free private 的結構性限制是 `DEGRADED`，可修正 drift 仍失敗。
- #64 的 default-token Release PR 假設被 #123 的 adaptive release mode 取代；#142 又取代 ephemeral version materialization。
- #74 的 Renovate 評估最後由 #110 決定保留 Dependabot；候選設定不是 active capability。
- #205–#209 與 PR #211、#215、#218 在 cutoff 時仍是候選／open；現行交付物仍由 `site/` 與 `scripts/render_site.py` 產生。
- #171 的 local attestation 是 narrow quota fallback，不等於 hosted checks；#199 與 #189 仍追蹤恢復與量測。

## Privacy and omissions

Ledger 只保存可公開稽核的編號、統計、查詢方法與摘要。不複製完整 comments、驗證 console、聊天逐字稿、credentials、敏感內部脈絡或模型 chain-of-thought。若來源不足，狀態保持 unresolved；不得為填滿文件而捏造原因。
