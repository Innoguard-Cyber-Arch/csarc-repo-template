# CI/CD archive — 2026-08-27

Milestone 8 suspended all CI/CD and dependency-update automation after the
repository exhausted its included GitHub Actions quota.

The files in this directory are historical reference only. GitHub does not
execute workflows outside `.github/workflows`, and Copier does not emit these
archived template files into generated repositories.

Do not restore this directory wholesale. Reintroduce one workflow at a time
through a dedicated Issue that defines its purpose, trigger, merge requirement,
and monthly cost ceiling.

Once a workflow is restored, its archived root and template copies are removed
in the same change. The active workflow is then the only source to inspect.
`ci`, `issue-triage`, `milestone-lifecycle`, `osv`, `pr-policy`, and
`spec-to-issue` have already moved back to their active locations. Dependabot
has also moved back to `.github/dependabot.yml`.

## 2026-09-01 disposition

Issue #430 reviewed every archived version and delivery workflow. None were
approved for restoration, so their root and template YAML copies were removed:
Release Please, artifact publishing and consumption, promotion and post-merge,
delivery maintenance, dev-next closure, release follow-up, live integration,
and Python version policy. Git, Issues, PRs, runs, and the release ADR retain
the historical decisions and evidence without leaving executable-looking
duplicates in this directory.

The files that remain here belong to other active Milestone 8 owners:
milestone lifecycle (#400), CI and Zizmor, governance, CodeQL, and template
updates. Their owner must either restore/rewrite the capability and remove its
archive copy, or retire the copy after a scoped decision. This README is an
index for that bounded follow-up, not permission to reuse the old YAML.
