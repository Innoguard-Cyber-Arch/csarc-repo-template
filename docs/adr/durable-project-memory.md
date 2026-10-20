# Durable project memory ADR

- **狀態：**Accepted
- **日期：**2026-08-24
- **來源 Issues：**[#223](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/223), [#1081](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1081), [#1138](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1138), [#1139](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1139), [#1173](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/1173)
- **實作 PRs：**[#58](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/58), [#147](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/147), [#185](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/185), [#228](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/228)

## 問題與限制

本 repo 已有 spec-to-Issue、歷史搜尋、decision records、tests 與可攜式文件站，但它們分別成長，尚未形成一套能跨 session、跨 agent 與跨時間讀取的 project memory。歷史理由主要留在 GitHub 時間線與網站，只有一份正式 decision record 和一份 draft example spec。

完整對話不適合作為 canonical memory：它可能含未確認假設、敏感資訊、重複內容與模型推理。把 plan、tasks、Issue、spec 與網站全部視為同等真相，也會產生互相漂移的狀態。

## 決定

採用既有工具構成的混合持久性模型：

1. `docs/specs/` 是 living current state，保存能力、限制、驗收與驗證；一個能力域一份 SDD。
2. `docs/adr/` 採 flow-forward，保存選擇理由、替代方案與後續 disposition；舊決策不因被取代而刪除。
3. Issue、PR、commit 是不可改寫的工作時間線與原始證據；canonical 文件摘要並回鏈，不複製逐字稿。
4. Tests、CI、release 與 pilot evidence 是可執行／可觀察證據；文件不能把尚未驗證的能力寫成 active。
5. `AGENTS.md` 只保存穩定導航與工作規則，先導向 `docs/README.md`，再依問題讀 spec、decision 與來源。
6. 任務 plan 與 status 是協作狀態；完成或重大轉向時摘要回 canonical sources，不永久維護另一套平行真相。

這裡使用 **Durable Project Memory** 作正式能力名稱。OpenAI 已明確使用此詞描述長任務的 durable Markdown context；其他大型專案對相同原則有高度共識，但沒有標準化的單一目錄或 schema。

## 2026-10-15 產品手冊權威層（#1081）

- **決定（#1058 決定 24）**：核准的技術手冊是 repo-template 的產品政策與使用者承諾來源。`docs/handbook/handbook.md` 是可編輯的權威來源，`docs/handbook/index.html` 由 `./scripts/build-handbook` 生成；`docs/handbook/approved/` 保存擁有者核准的 HTML 原檔，`docs/handbook/manifest.json` 記錄核准原檔、來源與生成頁的 SHA-256。
- **分層**：手冊定義產品政策與承諾；`docs/specs/`／`docs/adr/` 提供精確契約與理由；`AGENTS.md`／`docs/ci-policy.md` 提供可執行規則；生成內容、程式與測試提供證據。下層不能推翻手冊，衝突即為 drift，由每張 leaf 與 promotion 的 documentation review 對 exact head 判定 `aligned` 或 `drift`。`AGENTS.md` 仍是 AI 工作指示唯一的可執行來源，手冊不直接對 agent 下指令。
- **核准與變更**：`tests/test_handbook.py` 要求生成頁主體與核准原檔的 DOM 事件序列（標籤、屬性、文字）完全相同，因此主體的文字、planned 標記與 A4 版面都不會在轉換中改變。主體之後附加的模板附錄頁（`class="sheet annex"`）不屬於核准原檔，也不受主體 10 張 A4 的限制，另行檢查位置、連結與列印溢出（擁有者 2026-10-16 決定，#1138、#1139）。修改手冊主體內容必須取得新的擁有者核准，並在同一個變更中替換 `approved/` 原檔與 digest。M18 stable 發布前，手冊描述的新能力一律是 planned（front matter `status = "planned"`）；M18 stable（v0.35.2）發布後，front matter 改為 `status = "current"`（#1173），只影響 manifest 與測試，不改變生成頁。主體內「目前狀態」一句屬核准內容，改寫仍需新的擁有者核准。
- **生成專案**：不內含手冊；`.csarc/docs/csarc.md` 只描述該 render 啟用的能力，並以所安裝 Release 的完整 SHA 連結手冊。

## 歷史 disposition

| 狀態 | 決策 | 來源 |
| --- | --- | --- |
| Preserved | 維持輕量 `docs/specs/*.md` 與 idempotent GitHub 同步 | [#34](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/34)／[PR #58](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/58) |
| Preserved | 建立工作前限量搜尋 closed／open history，摘要沿用或推翻理由 | [#145](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/145)／[PR #147](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/147) |
| Preserved | Markdown decision record 是 canonical；網站是 presentation | [#177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/177)／[PR #185](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/185) |
| Rejected | 自動保存完整聊天或模型 chain-of-thought | [#177](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/177)／[PR #185](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/185) |
| Rejected | 為第一版新增向量資料庫、RAG、MCP 或另一套 SDD CLI | [#145](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/145)／[#223](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/223) |

## SDD、TDD 與 BDD 邊界

- Spec-Driven Development（SDD）的 durable artifacts 是 `docs/specs/` 的 intent 與 acceptance contract；Software Design Document 也常使用 SDD 縮寫，但不是本 repo 強制的單一文件格式。
- Test-Driven Development（TDD）的 durable artifact 是 regression test 與 CI evidence，不是每一次 red／green／refactor transcript。
- Behavior-Driven Development（BDD）的 durable artifact 是需要跨角色共識的 declarative behavior example；沒有需求時不新增 Gherkin parser 或 Cucumber runtime。

## Ownership 與驗證

Root 維護本 repo 的真實 specs、decisions 與 history ledger。Copier template 只提供相同目錄、範例、說明與驗證，並透過 `_skip_if_exists` 保留下游 `docs/specs/**/*.md`；不得下發本 repo 的歷史內容。

`scripts/spec_to_issue.py validate` 驗證 spec schema 與 ID 唯一性；`./scripts/verify-template.sh` 另檢查 decision metadata、來源連結、文件導覽與生成 fixture。

## 評估過的替代方案

| 方案 | 結論 |
| --- | --- |
| 完整導入 Spec Kit／OpenSpec | 暫不採用；目前既有同步與 GitHub lifecycle 已足夠，額外 CLI 會建立第二套流程 |
| 所有狀態只留在 GitHub | 不採用；Issue／PR 適合時間線，但無法快速表達 current capability map |
| 只維護網站 | 不採用；presentation 不是 canonical source，且會把內容與版型耦合 |
| 保存完整對話 | 不採用；噪音、隱私與未確認推論風險高 |

## 外部參考

- [OpenAI: Run long horizon tasks with Codex](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)
- [OpenAI Codex best practices](https://developers.openai.com/codex/learn/best-practices)
- [GitHub Spec Kit: Spec persistence](https://github.com/github/spec-kit/blob/main/docs/concepts/spec-persistence.md)
- [OpenSpec](https://github.com/Fission-AI/OpenSpec)
- [Kubernetes KEP template](https://github.com/kubernetes/enhancements/blob/master/keps/NNNN-kep-template/README.md)
- [Rust RFC process](https://github.com/rust-lang/rfcs/blob/master/README.md)
- [Cucumber BDD](https://github.com/cucumber/docs/blob/main/content/docs/bdd/_index.md)

## 重新評估條件

當 spec 數量或跨 repo 導覽已使 bounded search 與 Markdown index 無法在可接受時間內工作，且有真實查找失敗資料時，再評估搜尋索引、catalog 或專用 spec tooling。新增工具前仍須保留 repository-local、可審查與可匯出的基線。
