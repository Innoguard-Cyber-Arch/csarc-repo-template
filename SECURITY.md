# Security Policy

## Supported versions

This repository ships one rolling release from `main`. Only the latest tagged
release receives security fixes; there are no maintained older-version
branches.

## Reporting a vulnerability

Do not open a public GitHub Issue for a suspected vulnerability. Issues are
public and indexed, so they must never contain exploit code, credentials,
tokens, or customer data.

Report through the organization-approved private channel instead of email or
a public Issue. This template does not invent a contact address or a
response-time commitment, because neither exists yet at the template level.

<!-- Project owner: replace this section with the actual private reporting
channel (for example GitHub private vulnerability reporting if enabled for
this repository, a security contact mailbox, or an internal ticketing
system) and the expected acknowledgement window before relying on this
document. -->

## Scope

This policy covers the code, workflows, and configuration in this
repository. It does not cover third-party dependencies; report those to the
upstream project. Dependency vulnerabilities that affect this repository are
also tracked automatically through `.github/dependabot.yml` and `osv.yml`.
