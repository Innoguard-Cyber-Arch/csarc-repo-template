# Security Policy

## Supported versions

This repository ships one rolling release from `main`. Only the latest tagged
release receives security fixes; there are no maintained older-version
branches.

## Reporting a vulnerability

Report suspected vulnerabilities privately through this maintainer-approved
channel:

<!-- csarc-security-reporting-channel:start -->
justyn.jt.chen@tw.ey.com
<!-- csarc-security-reporting-channel:end -->

This repository is public. Do not open a GitHub Issue, Discussion, or pull
request for a suspected vulnerability, and do not post exploit details,
secrets, credentials, personal data, or other sensitive information in any
public channel. This policy does not invent an acknowledgement or resolution
SLA.

## Scope

This policy covers the code, workflows, and configuration in this
repository. It does not cover third-party dependencies; report those to the
upstream project. Dependency vulnerabilities that affect this repository are
also tracked automatically through `.github/dependabot.yml` and `osv.yml`.
