# Changelog

目前由維護者在受審查的版本 PR 中更新；2026-08-27 前曾由 release-please 維護。
2026-08-24 以前的版本依既有 tags、合併紀錄與 GitHub Release notes 回填；`v0.1.0`、
`v0.2.0`、`v0.2.1` 是 tag-only 歷史版本，沒有可驗證的正式 Release 成品。
`v0.2.2`～`v0.10.0` 的正式成品版本與 tag 一致，但 tagged source 的版本欄位
仍停在 `0.1.0`；從 `v0.10.1` 起改為只發布已在 source commit 完整寫入版本與
CHANGELOG 的 tag。

## [0.12.2](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.12.1...v0.12.2) (2026-08-27)


### Bug Fixes

* allow exact preserved dirty adoption ([#362](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/362)) ([d6d8042](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/d6d8042d0da4bafdf1d222b44b47b0d4b105d5b2))

## [0.12.1](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.12.0...v0.12.1) (2026-08-26)


### Bug Fixes

* **ci:** make hosted verification self-contained ([#356](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/356)) ([d46ddc8](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/d46ddc8f4ceb1ced8669900477470e8c1b72808c))
* **cli:** run configured project verification hooks ([#358](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/358)) ([94e2a9c](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/94e2a9c51413e75f198d0e85865268c694c9b21d))

## [0.12.0](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/compare/v0.11.0...v0.12.0) (2026-08-26)


### Features

* build portable decision site bundle ([#187](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/187)) ([e7c08d1](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/e7c08d13ba386f172eb21a729d5ba85dcd6bc974))
* **ci:** accept quota-only local attestations ([#173](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/173)) ([620683b](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/620683b36cb2b74e07a7cb0c900ef6f632bd0e7e))
* **ci:** document isolated delivery operations ([#193](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/193)) ([2c08abc](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/2c08abc7fb05d5833da6bcf6d5112f2b5a47c010))
* **ci:** enforce delivery branch synchronization ([#188](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/188)) ([9ce13d4](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/9ce13d468ef6dbb3664a4588bf67f89d1314f607))
* **ci:** gate promotions with canary evidence ([#191](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/191)) ([5028891](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/50288913dbcefc011b86ce97ba0aebaeb3f8f8aa))
* **ci:** promote staged CI delivery train ([#298](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/298)) ([3ea6134](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/3ea6134e82916f24d37b5c7fa988f9ca9a6beaa7))
* **governance:** add delivery branch routing ([#186](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/186)) ([b07ea19](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/b07ea19467b310c3c8d2a396d023e0150755e0b1))
* **governance:** complete native hierarchy delivery ([#336](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/336)) ([4e73e22](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/4e73e22ed17d6a061438068be07bd2f1fc8e89af))
* **governance:** promote native issue hierarchy ([#331](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/331)) ([2a42d79](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/2a42d7960e2d5a110b2457b102ae33314a6fb390))
* promote completed standalone fixes ([#316](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/316)) ([932b0cb](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/932b0cbf9a3b26fb688197bb15ba846486b73167))
* promote standalone delivery batch ([#237](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/237)) ([a0f537c](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/a0f537cfccfa63935a42f13d534397a70f1a8a04)), refs [#232](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/232)
* **release:** batch releases at promotion boundaries ([#192](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/192)) ([6139e36](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/6139e36b643ae33dff5341ea499a12ad17658321))


### Bug Fixes

* **ci:** exclude large tests from routine verification ([#345](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/345)) ([6870570](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/6870570bb1e32f3d9db06b4cf03b1d43735bf69b)), refs [#343](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/343)
* **ci:** honor routine quota lifecycle ([#339](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/339)) ([147e80c](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/147e80c3c010cd00d7f641be0597b57c84ccd2ec))
* **ci:** ignore superseded check runs ([#344](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/344)) ([5f0c7f0](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/5f0c7f047047085da277722fc3024fdb4db5e04e))
* **ci:** validate live pull request metadata ([#338](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/338)) ([f9ad223](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/f9ad223857a6e5e6c5635cdd73e12ecf5d207a56))
* **governance:** request configured pull request reviewers ([#165](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/165)) ([e2a3baf](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/e2a3baf6a55982caae62e8618351de41d7492bf9))
* **release:** generate SPDX SBOMs with pinned Syft ([#347](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/347)) ([aa2396d](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/aa2396dcd67b9058bb9b0f243e5b034731552ec4))
* **release:** recover missing v0.12.0 ([#348](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/issues/348)) ([0064297](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template/commit/0064297d46c13af3c11ee02d3a6c61d265e797c3))

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
