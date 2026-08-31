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
`ci`, `issue-triage`, `milestone-lifecycle`, `pr-policy`, and `spec-to-issue`
have already moved back to their active locations.
