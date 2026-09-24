# Changelog

目前由維護者在受審查的版本 PR 中更新；2026-08-27 前曾由 release-please 維護。
2026-08-24 以前的版本依既有 tags、合併紀錄與 GitHub Release notes 回填；`v0.1.0`、
`v0.2.0`、`v0.2.1` 是 tag-only 歷史版本，沒有可驗證的正式 Release 成品。
`v0.2.2`～`v0.10.0` 的正式成品版本與 tag 一致，但 tagged source 的版本欄位
仍停在 `0.1.0`；從 `v0.10.1` 起改為只發布已在 source commit 完整寫入版本與
CHANGELOG 的 tag。

## [0.26.4] - 2026-09-24

### Bug Fixes

* fix: reconcile GitHub Pages desired and live state (9de3774)

## [0.26.3] - 2026-09-24

### Bug Fixes

* fix(release): keep draft tag when annotating release (b8c86ca)

## [0.26.2] - 2026-09-24

### Bug Fixes

* fix(release): locate draft Releases by tag name (dcd7b71)

## [0.26.1] - 2026-09-24

### Bug Fixes

* fix: align docs-off operational guidance (5efdda9)
* fix: keep docs-off lifecycle wording neutral (0bef2a3)

## [0.26.0] - 2026-09-24

### Features

* feat(adoption): suggest work item mappings (78389d6)

### Bug Fixes

* fix(adoption): preserve observed label metadata (249c729)
* fix(adoption): bind reviewed work item mappings (8faaa94)
* fix(adoption): close mapping confirmation gaps (99c47ab)

## [0.25.8] - 2026-09-24

### Bug Fixes

* fix(governance): keep milestone metadata aligned (6fbc7e0)

## [0.25.7] - 2026-09-24

### Bug Fixes

* fix: repair language promotion evidence (5c798ff)

## [0.25.6] - 2026-09-24

### Bug Fixes

* fix(governance): normalize work item labels (904510c)
* fix(governance): guard automated issue edits (0531082)

## [0.25.5] - 2026-09-24

### Bug Fixes

* fix(release): keep beta ahead of stable (f0ab57f)

## [0.25.4] - 2026-09-24

### Bug Fixes

* fix(governance): keep delivery sync compatible (4018341)

## [0.25.3] - 2026-09-23

### Bug Fixes

* fix(ci): isolate package smoke wheel (5e1f6d1)

## [0.25.2] - 2026-09-23

### Bug Fixes

* fix(ci): preserve reused verification evidence (fcd93fe)
* fix(ci): bind clean sync evidence (6d7656f)

## [0.25.1] - 2026-09-23

### Bug Fixes

* fix(ci): eliminate duplicate hosted full runs (e33c5a2)

## [0.25.0] - 2026-09-23

### Features

* feat(agent): coordinate finalization lifecycle (60a6840)

## [0.24.2] - 2026-09-23

### Bug Fixes

* fix(governance): report expected states accurately (957800a)

## [0.24.1] - 2026-09-23

### Bug Fixes

* fix(governance): prevent invalid work branches (b2b506b)

## [0.24.0] - 2026-09-23

### Features

* feat(release): materialize versions before merge (5713345)

## [0.23.1] - 2026-09-23

### Bug Fixes

* fix(governance): route standalone issue refresh (#875) (b0437a7)

## [0.23.0] - 2026-09-23

### Features

* feat: govern documentation and licensing lifecycle (09f117c)

### Bug Fixes

* fix(ci): install reused release tools (c3abd45)

## [0.22.0] - 2026-09-23

### Features

* feat: define beta and stable release governance (9a521a3)

### Bug Fixes

* fix: bridge final alpha version to stable (f7f9d0f)

## [0.21.0-alpha.1] - 2026-09-23

### Features

* feat: simplify generated project configuration (fa1e6b6)
* feat: make local verification the default (d9ed351)

### Bug Fixes

* fix: accept compact release configuration (bf8992f)
* fix: allow alpha release self-review (2ce14d1)

## [0.20.0-alpha.1] - 2026-09-22

### Features

* feat: restore guided release setup (#884) (260c992)

### Bug Fixes

* fix(promotion): use bridge for main freshness (3e2ef57)
* fix(release): verify materialized promotion bridges (28089da)
* fix(ci): suppress non-actionable verify runners (ff252c8)
* fix(governance): allow alpha promotion self-merge (e9131dc)

## [0.19.0-alpha.1] - 2026-09-22

### Features

* feat(release): publish milestones from promotion PRs (#873) (eaa3672)
* feat: prepare AI security scanner guidance (#874) (cd9d756)

## [0.18.0-alpha.1] - 2026-09-22

### Features

* feat: promote Milestone 14 delivery (#860) (db4888b)
* feat: promote Milestone 14 final delivery (#867) (7ff192f)

### Bug Fixes

* fix(ci): accept guided prerelease branches (9d569c0)

## [0.17.3] - 2026-09-21

### Bug Fixes

* fix(ci): bootstrap trusted pull request triggers (8ce8ae4)
* fix: bind required checks to trusted producers (ddd81cc)
* fix: bootstrap trusted hosted verification (412f127)
* fix(security): replace forgeable verification evidence (1f77c12)
* fix(cli): harden repository Git inspection (6beebd7)
* fix(ci): authenticate Dependabot heads before atomic merge (dc00567)

## [0.17.2] - 2026-09-20

### Bug Fixes

* fix(cli): defer Copier tasks until approval (dc2e7a4)
* fix(ci): isolate pull request policy writes (048b447)
* fix(cli): defer dependency tooling until approval (30b8b36)

## [0.17.1] - 2026-09-20

### Bug Fixes

* fix(governance): allow alpha delivery sync self-review (7970057)

## [0.17.0] - 2026-09-20

### Features

* feat(governance): enable drift checks by default (5b7f525)

### Bug Fixes

* fix(governance): reject incomplete Milestone closure (057b83e)
* fix(release): revalidate candidates when main advances (b91fc40)
* fix(release): silence cleanup trap shellcheck warning (48e7ffb)

## [0.16.0] - 2026-09-20

### Features

* feat: add optional Copilot review path with automatic merge (#756) (a4f3f50)
* feat(ci): allow routine Milestone-less alpha PRs to self-merge into main (#776) (caf750a)
* feat(release): verify release attestation instead of immutable_releases probe (#773) (2eae2fc)

### Bug Fixes

* fix(ci): run hosted verification for allowlisted dependency bot pull requests (#758) (a60ad24)
* fix(ci): allow creating new dev/m* delivery branches under the Ruleset (#759) (9f63652)
* fix(ci): release dependency security updates and sync template action pins (#762) (2ac5b75)
* fix(cli): resolve release ownership before persisting current-stage capabilities (#763) (9c18b10)
* fix(ci): use current GraphQL type for issue creation policy mutation (#765) (6f371b9)
* fix(tests): make copier import lazy in paired dependabot auto-merge test (#774) (75be40a)
* fix(ci): detect approval comments edited long after posting (#779) (8ebbc70)
* fix(ci): stop trusting author_association for maintainer checks (#787) (8c1ed8b)
* fix(ci): surface why alpha self-merge authorization did not apply (030bda0)
* fix(release): distinguish guided no-op drift runs (bec6c76)
* fix(ci): install tools before hosted bot verification (e0828ef)

## [0.15.6] - 2026-09-11

### Bug Fixes

* fix: require fresh adoption replay authorization (#721) (1c04726)
* fix(cli): gate repository execution on approval (#722) (f26303d)
* fix(cli): reject symlinked lifecycle writes (#723) (212b047)

## [0.15.5] - 2026-09-11

### Bug Fixes

* fix: align public repository identity (#713) (db0d7cf)

## [0.15.4] - 2026-09-11

### Bug Fixes

* fix: trust canonical release evidence (#712) (dd4c43f)

## [0.15.3] - 2026-09-10

### Bug Fixes

* fix: short circuit blocked release setup (#711) (2016f7a)

## [0.15.2] - 2026-09-10

### Bug Fixes

* fix: update vulnerable Vitest packages (#720) (b9ec196)
* fix: use exact-head approval for merge authorization (#724) (060edcd)
* fix: synchronize bilingual release metadata (#710) (68cbdd8)

## [0.15.1] - 2026-09-07

### Bug Fixes

* fix: legacy two-file schema breaks every csarc update (#691) (ac97030)
* fix(ci): stop release.yml from re-verifying and self-attesting (#684) (#692) (bec66d3)
* fix(site): keep zh-tw home version cell synced automatically on release bump (#698) (9bb28a3)
* fix(ci): resolve release.yml's attestation check to the merged PR head (#700) (e7e12dc)
* fix(template): skip root-only zh-tw version markers downstream (#703) (4e61993)

## [0.15.0] - 2026-09-07

### Features

* feat(site): promote Milestone 13 repo-site rewrite and adoption redesign (#689) (f89d2de)

### Bug Fixes

* fix(packaging): rename Python distribution to csarc-repo-template (#680) (2d1a6c8)
* fix(site): replace unresolvable uvx examples in legacy-components.js (#679) (09103d7)
* fix(test): read the repo version from the manifest, not a literal (#696) (e8b5d03)

## [0.14.0] - 2026-09-04

### Features

* feat(governance): gate self-approval bypass scope to release phase (#615) (876aa9c)
* feat(scripts): default the tool cache root to a shared user-level path (#650) (c0f5bfc)
* feat(governance): merge Issue triage, Milestone lifecycle, and Work Issue closure into one job (#653) (fb18b73)
* feat(ci): produce the promotion required check for ordinary PRs (#654) (baa9666)
* feat(governance): add Milestone creation preflight and atomic creation tool (#655) (5161454)
* feat(ci): add scheduled release-publish drift alert (#656) (39258f2)
* feat(ci): verify PRs via local attestation instead of hosted Actions (#671) (a52022d)

### Bug Fixes

* fix(release): use gh release view for draft asset listing (#644) (152c6a7)
* fix(release): remove redundant asset cleanup and stray gitignore (#647) (8687e6b)
* fix(docs): render README bold-prefix line correctly on GitHub (#640) (b66f36a)
* fix(ci): exempt release-please and narrow the writer scanner (#643) (#649) (c8d3efc)
* fix(governance): stop the acceptance-checklist retry storm (#651) (51fe2b7)

## [0.13.0] - 2026-09-04

### Features

* feat(delivery): allow audited milestone checkpoints (#367) (9893822)
* feat(governance): use native issue forms (#384) (0bc1429)
* feat(governance): restore Journey 01 actions (#386) (42834ea)
* feat(site): promote Milestone 8 interactive docs and policy alignment (#542) (9ed3594)
* feat(ci): auto-merge Dependabot pull requests after checks pass (#569) (49fcfe1)
* feat(governance): collaborator-only creation and security scanning (#579) (1177157)
* feat(release): make the publish stage runnable without Actions (#608) (f39f0b4)
* feat(governance): declare and enforce a GitHub Pages policy (#578) (37b956b)

### Bug Fixes

* fix(governance): admin self-approval rejects organization MEMBER association (#548) (996abaf)
* fix(governance): base admin self-approval on collaborator permission (#550) (7719d2e)
* fix(governance): declare the required_status_checks Ruleset rule (#575) (6bdfc6c)
* fix(ci): run the docs staleness check on mixed-scope fast-tier PRs (#593) (6aa7724)
* fix(ci): run spec validation on mixed-scope docs PRs too (#598) (#600) (6c4f200)
* fix(ci): retry the check-branch-fresh fixture teardown (#591) (#606) (4297604)
* fix(ci): exempt dependabot-auto-merge.yml from the writer scanner (#611) (b9516e4)
* fix(template): declare pyyaml for generated python projects (#614) (971bb98)
* fix(tests): skip the template path in generated-project scanner test (#618) (c2c136e)
* fix(ci): route release.yml template expressions through env vars (#621) (cfd38f4)
* fix(ci): grant administration:read for the release capability probe (#623) (14bcb71)
* fix(ci): revert the invalid administration permission key (#625) (aa98e55)

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
