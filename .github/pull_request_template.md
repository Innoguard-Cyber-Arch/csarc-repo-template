## Purpose

<!-- Draft 使用 Refs #N；完成所有 PR／Issue 項目並轉 Ready 前改成 Closes #N。 -->

Refs #N

<!-- Work PRs use type/N-short-slug and target the configured integration branch. -->

<!-- Draft 必填；請為每個欄位填入具體內容，沒有風險或依賴時填 None。 -->

- Scope:
- Completed verification:
- Pending verification:
- Known risks:
- Dependencies / non-parallel work:

## 完成清單

<!-- Draft 可保留未勾項目；closing keyword 與 Ready 要求此處及 Issue 全數完成。 -->

- [ ] 已依 CI plan 完成 scoped checks 並記錄指令與結果；PR assignee／label／Milestone 與 linked Issue 一致；work branch 已顯示於 Issue Development；恰選一個 change label（`fix`→`bug`、`docs`→`documentation`、其餘 type→`enhancement`）；未超出原 Issue 範圍
- [ ] 若本 PR 是最終整合候選，final tree 已固定，轉 Ready 將啟動 hosted `./scripts/verify-template.sh`；成功只由 required `verify` check 記錄，不需事後編輯本清單；僅在政策要求 fallback 時改由 integrator 本機只執行一次；否則標記 N/A
- [ ] 若 CI plan 包含 generator/template scope，已測試新專案產生並評估既有專案更新影響；否則標記 N/A；任何變更的第三方 Actions 固定完整 commit SHA

## 補充

<!-- 選填：風險、回退，或本 PR 對其他專案的額外影響。 -->
