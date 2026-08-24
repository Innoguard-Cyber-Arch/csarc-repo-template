# Changelog

本檔案由 release-please 依合併到 `main` 的 Conventional Commits 維護。2026-08-24
以前的版本依既有 tags、合併紀錄與 GitHub Release notes 回填；`v0.1.0`、
`v0.2.0`、`v0.2.1` 是 tag-only 歷史版本，沒有可驗證的正式 Release 成品。
`v0.2.2`～`v0.10.0` 的正式成品版本與 tag 一致，但 tagged source 的版本欄位
仍停在 `0.1.0`；從 `v0.10.1` 起改為只發布已在 source commit 完整寫入版本與
CHANGELOG 的 tag。

## [0.11.0] - 2026-08-24

### Added

- 升級 Milestone story planning 契約，並在 adopt/update 中安全遷移可辨識的
  舊版 description
  ([#161](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/161))。

## [0.10.1] - 2026-08-24

### Fixed

- 將公版 source、tag、CHANGELOG、文件與成品納入同一個 fail-closed 版本契約，
  並依可驗證紀錄補正 release 與 Milestone 歷史
  ([#151](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/151))。

## [0.10.0] - 2026-08-24

### Added

- 為 `csarc adopt --dry-run` 產生可分享的 Markdown 與 PDF 導入報告
  ([#160](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/160))。

## [0.9.1] - 2026-08-24

### Fixed

- 強制 Issue 與 pull request 採用精簡且一致的 body 格式
  ([#153](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/153))。

## [0.9.0] - 2026-08-24

### Added

- 安全清理由 agent 建立且已合併的 Git worktree
  ([#158](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/158))。

## [0.8.2] - 2026-08-24

### Fixed

- 完整驗證 repository、Actions、政策標籤與有效 Ruleset 的設定漂移
  ([#154](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/154))。

## [0.8.1] - 2026-08-24

### Fixed

- 要求完成 Milestone acceptance criteria 後才能自動關閉
  ([#152](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/152))。

## [0.8.0] - 2026-08-24

### Added

- 在建立工作前搜尋並保留既有決策脈絡
  ([#147](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/147))。

## [0.7.0] - 2026-08-24

### Added

- 依 repository 與 organization 權限引導選配整合安裝，並保留 Dependabot
  與既有 CI/CD 作為 fallback
  ([#156](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/156))。

## [0.6.0] - 2026-08-24

### Added

- 對每個宣告支援的 Python minor version 執行 CI，並記錄 runtime support
  contract
  ([#150](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/150))。

## [0.5.0] - 2026-08-24

### Added

- 驗證正式 Release artifact 的 repository identity、tag、commit、digest 與
  release-service attestation，並確認竄改內容會 fail closed
  ([#139](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/139))。

## [0.4.0] - 2026-08-24

### Added

- 記錄 `ai-guardrail` 真實導入與 Copier 更新證據，將共用治理與 CI-only
  composition 提升為 beta
  ([#138](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/138))。

## [0.3.1] - 2026-08-24

### Fixed

- 保留 live workflow probe 的完整 JSON 結果
  ([#137](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/137))。

## [0.3.0] - 2026-08-24

### Added

- 加入 OSV、Release Please、release handoff 與 governance drift 的真實 GitHub
  整合檢查
  ([#136](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/136))。

## [0.2.4] - 2026-08-24

### Fixed

- 提供 Release 驗證所需的 attestation read 權限
  ([#134](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/134))。

## [0.2.3] - 2026-08-24

### Fixed

- 發布後等待 immutable Release attestation 可用再驗證
  ([#132](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/132))。

## [0.2.2] - 2026-08-24

### Fixed

- 移除 Release 對管理員限定 API 的依賴
  ([#130](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/130))。

## [0.2.1] - 2026-08-24

### Fixed

- 在 ephemeral build checkout 寫入版本前先完整驗證模板
  ([#129](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/pull/129))。

## [0.2.0] - 2026-08-24

### Added

- 建立可版本化、可由 Copier 更新的 CI/CD-only、Python、TypeScript 與混合模板。
- 加入 Issue-first 治理、可選 Story Milestone、spec 同步與分支／PR 政策。
- 加入依 GitHub 能力選擇 release-please、direct 或 verification-only 的發布流程。
- 加入 wheel／npm artifact、checksum、SBOM、provenance、registry trusted publishing
  與 template update 通知。
- 加入 OSV、Zizmor、Gitleaks、CodeQL、依賴版本政策與 governance drift 檢查。
- 加入 `csarc init`／`adopt`／`update` repository lifecycle CLI。

完整變更見
[`v0.1.0...v0.2.0`](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.1.0...v0.2.0)。

## [0.1.0] - 2026-08-21

### Added

- 建立第一個可追蹤的公版基線與 artifact／SBOM 完整性檢查。

[0.11.0]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.10.1...v0.11.0
[0.10.1]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.9.1...v0.10.0
[0.9.1]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.8.2...v0.9.0
[0.8.2]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.2.4...v0.3.0
[0.2.4]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/tree/v0.1.0
