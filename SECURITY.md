# Security Policy

## Supported versions

This repository ships one rolling release from `main`. Only the latest tagged
release receives security fixes; there are no maintained older-version
branches.

## Reporting a vulnerability

Do not open a public GitHub Issue for a suspected vulnerability. Issues are
public and indexed, so they must never contain exploit code, credentials,
tokens, or customer data.

No organization-approved private security reporting channel is currently
published for this repository. Do not disclose sensitive details in a public
Issue or guess a maintainer's email address. Maintainers must publish an
approved private channel before this repository can accept vulnerability
reports. This policy does not invent an acknowledgement or resolution SLA.

## Scope

This policy covers the code, workflows, and configuration in this
repository. It does not cover third-party dependencies; report those to the
upstream project. Dependency vulnerabilities that affect this repository are
also tracked automatically through `.github/dependabot.yml` and `osv.yml`.
