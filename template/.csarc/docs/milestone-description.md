# Delivery Milestone description

Milestone 只代表有真實 due date 的 delivery／release；沒有排程就不要建立，也不要把它當 label。下列內文以繁體中文示範，實際 description 使用專案團隊慣用的語言，但保留英文 H2 標題，讓人與自動化都能辨識結構。

## 建立與預檢

建立 GitHub Milestone 時填入真實 due date，再以 `.github/ISSUE_TEMPLATE/milestone-tracker.yml` 建立一張生命週期 tracker Issue，標題固定為 `Milestone <編號>: <里程碑名稱>`，冒號後的文字與 Milestone 名稱完全相同。指派工作前先執行：

```bash
python3 .csarc/scripts/sync_milestone_state.py preflight --repo <owner/repo> --milestone <N>
```

它確認 due date、tracker 標題與 `Lifecycle Issue: #N` 連結一致，並以原生 `parent_issue_url` 確認 Milestone 內的 sub-issue 都能找到同一 Milestone 的 parent Issue。表單降低漏段落的機率，`sync_milestone_state.py` 仍在建立後檢查格式。

## Tracker 與核可

tracker 本文依序有 `Proposal`、`Completion evidence`、`Early termination`、`Promotion` 四段，H2（`##`）或表單產生的 H3（`###`）都接受，同名時以 H2 為準，段落到下一個同級或更高標題為止；Release level 固定是 `stable`。只有 repository collaborator 建立的 tracker 會被信任。

| 留言 | 用途 |
| --- | --- |
| `/milestone approve` | 非提案者核准 |
| `/milestone admin-approve: <理由>` | `admin_bypass` 允許時，admin 提案者自核；紀錄標為 Admin self-approved |
| `/milestone object: <理由>` | 反駁，未解決前核可無效 |
| `/milestone resolve: <連結或摘要>` | 解決反駁 |

admin 身分以 collaborator permission API 即時判斷，不看留言的 `author_association`。tracker body 在核准後被編輯時，舊核准失效，需要重新核准。

Milestone 內的 work Issue 直接繼承 tracker 的核可。只有 body 含逐字獨立一行 `Tracker scope: expanded` 的 Issue 需要以同一套語彙另外核可；PR policy 在合併前檢查這項核可，Issue 之後再被編輯時核可同樣失效。沒有 Milestone 的 Issue 改用 `.csarc/docs/ci-policy.md`「審查與合併資格」的 `Approve` 語彙。

## Description 格式

GitHub Milestone 物件的 `description` 使用下列七段，不與 tracker 表單共用骨架：

```markdown
## Problem

用一小段話交代這次 delivery 要收斂的問題；先描述問題，不先指定解法。

## Outcome

完成後可觀察的價值，並連回對應的主 Issue 或 spec。

## Acceptance criteria

- [ ] 2–5 項 story-level、可獨立驗證的結果，不抄寫 implementation tasks。

## Plan

1. #<main-issue> — 第一張可獨立交付的主 Issue 與目的。

## Out of scope

看似相關、但刻意排除的工作。

## Verification

maintainer 如何端到端驗證 outcome。

## References

- #<issue> — 沿用、取代或駁回的既有決策與理由；沒有候選時記錄 bounded search 範圍。
```

結構固定為一張 tracker、多張直接掛入 Milestone 的主 Issue（不設 Feature parent），只有必要時才在主 Issue 下開 sub-Issue。主 Issue、sub-Issue 與 PR 都掛入 Milestone。

## 收尾

- 關閉最後一張 Issue 前，勾選所有已驗證的 acceptance items；否則 lifecycle 讓未完成的 story 保持開啟。
- 背景 reconcile 只在 tracker、Milestone 事件與 Issue 改掛 Milestone 時同步狀態；tracker 尚未核准是正常治理狀態，以 notice 呈現，PR 的核准 check 仍維持失敗。
- promotion PR 先依 [CI/CD 規範](ci-policy.md#milestone-promotion-的-adr-與文件對齊) 完成整批 ADR 與文件對齊紀錄，並綁定 exact head。
- `Promotion` 段落只寫合併前可驗證的條件；tracker 關閉與 branch／worktree 清理寫在補充的 post-merge runbook。`promote/m<編號>-<簡稱>` PR 以 `Closes #<tracker>` 關閉 tracker，合併後回填 `Completion evidence`。
- 以 `completed` 收尾前執行 `python3 .csarc/scripts/sync_milestone_state.py regenerate-reconciliation --repo <owner/repo> --milestone <N>`。它在 tracker 產生 `Reconciliation` 段落，逐列標示每張 Issue 是 `Delivered`、`Not planned`、`Pending`、`Closed without a merged PR` 或 `Acceptance incomplete or missing`。tracker 其他段落之後被編輯會讓段落過期；任一列不是已交付或不在計畫內時，拒絕以 `completed` 收尾。以 `not_planned` 提前終止不宣稱交付，不受這項檢查限制。

建立前閱讀相關 open／closed Issue 的內文、留言與 linked PR，不只依標題或 label 推翻既有決策。
