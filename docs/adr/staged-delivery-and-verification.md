# Staged delivery and verification ADR

- **狀態：**Accepted
- **日期：**2026-08-25
- **來源 Issues：**[#23](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/23), [#37](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/37), [#99](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/99), [#122](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/122), [#140](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/140), [#144](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/144), [#171](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/171), [#179](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/179), [#180](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/180), [#181](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/181), [#182](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/182), [#189](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/189), [#199](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/199), [#233](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/233), [#254](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/254), [#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287), [#301](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/301)
- **實作 PRs：**[#24](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/24), [#52](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/52), [#136](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/136), [#125](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/125), [#150](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/150), [#152](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/152), [#173](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/173), [#186](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/186), [#188](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/188), [#190](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/190), [#191](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/191), [#193](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/193), [#236](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/236), [#306](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/306)

## 問題與限制

每張 Issue 都直接進 main 會把整合風險、完整 CI 成本與 release 頻率綁在一起；只跑快速檢查則無法證明完整 story 與 main 組合可交付。GitHub 的 branch／path skip 也可能讓 required context 永久 Pending。

## 決定

- Milestone work 進 `dev/m*`，standalone work 預設進 `dev/next`；有獨立 soak／canary 需求才用暫時 `dev/i*`，hotfix 才直接 main。每條 work branch 都由 `gh issue develop` 建立，保留 GitHub Development 關係。
- Main advance 透過 reviewed sync PR 回灌 active delivery branches；promotion 前必須證明包含 current main。
- CI 分 policy、fast、full、scheduled／release 四層，以 stable aggregate context 收斂結果。
- Promotion 綁定 base／head SHA、candidate tree、full verification 與 canary 三態；artifact-only 不冒充 external canary。
- Human-confirmed quota-only、zero-step failure 可讓 promotion 以相同 full verification 與 SHA/tree evidence 合併 main；本機 evidence 固定不可發布，待 hosted checks 補跑。
- 14→3／4 job-minute 是明確標示的規劃估算；hosted duration 與 `ci-plan` 僅在 runner 可用時作 telemetry，不是交付關卡。Portable baseline 不要求管理員調整帳單、方案或維護額外 runner。
- Acceptance checklist 未完成時不得使用 closing keyword；PR metadata 從 linked Issue 同步 assignee、classification label 與 Milestone，離開 draft 時要求非作者 reviewer；Milestone 只在 outcome 與 promotion evidence 完成後關閉。
- TDD 留下最小 regression 與最終 evidence，不保存逐次 red／green 暫態。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Superseded | 預設 main-only／單一 dev 的固定整合模型 | [#7](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/7) → [#179](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/179)／[#186](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/186) |
| Preserved | Stacked PR 可用，但鏈末必須是正確 delivery branch | [#23](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/23)／[#24](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/24) |
| Preserved | Coverage 是風險訊號，不是品質分數 | [#37](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/37)／[#52](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/52) |
| Preserved | Quota fallback 僅限 human-confirmed、zero-step、SHA-bound 狀況 | [#171](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/171)／[#173](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/173) |
| Superseded | Promotion 必須等待 hosted runner 才能進 main；quota-only 時改用不可發布的 SHA/tree evidence | [#182](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/182) → [#233](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/233) |
| Superseded | M7 必須等待成功 hosted runner 量測或管理員恢復 Actions | [#189](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/189)／[#199](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/199) → [#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287) |
| Preserved | Zero-step block 不是 hosted success；本機 full、promotion tree、security 與 supply-chain gates 不因 telemetry 不可用而降低 | [#171](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/171)／[#254](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/254)／[#287](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/287) |

## Ownership 與驗證

Issue owner 負責 scope 與 acceptance；delivery owner 負責 sync conflict 與 promotion；workflow 保存 machine-readable route／evidence。完整操作以 `AGENTS.md` 與 `docs/ci-policy.md` 為準，行為由 policy fixtures、生成專案與 live probes 交叉驗證。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 每張 PR 都跑完整矩陣 | 不採用作日常預設；重型驗證移到 promotion／hotfix |
| 只用 path filter 跳過 workflow | 不採用；required context 可能永久 Pending |
| 為每張單建立 Milestone | 不採用；Milestone 只代表可獨立驗收的 story outcome |
| 把本機 quota fallback 當 hosted CI 或 release 成功 | 不採用；只能留下受限 attestation，額度恢復後仍須補跑 |
| 要求管理員恢復 hosted runner 才完成交付 | 不採用；runner 是外部 capability，可用時收集 telemetry 即可 |

## 重新評估條件

Hosted runner 可用時收集 duration、job-minute 與 `ci-plan` telemetry 校準模型。若實測成本、false routing 或 promotion latency 與模型顯著不符，以新 Issue 調整；telemetry 不可用不阻塞交付，也不降低安全與 full gate。
