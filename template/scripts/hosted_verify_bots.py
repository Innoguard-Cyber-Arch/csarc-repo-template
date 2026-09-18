#!/usr/bin/env python3
"""Positive allowlist for bots that get real hosted verification (#753).

Issue #661 turned the `verify` required check into a check that no longer
runs any test itself: it only validates that the commit already carries a
`Verified-locally:` trailer written by a contributor's own
`./scripts/verify-fast` or `./scripts/verify-template.sh` run
(`scripts/verify_attestation.py`). Dependabot's commits are authored and
pushed by GitHub itself and never go through anyone's local checkout, so
they can never carry that trailer -- every Dependabot pull request fails
`verify` by design, including security updates.

This module answers one narrow question for one required check
(`.github/workflows/ci.yml`'s `verify` job): does this pull request belong
to an allowlisted bot, on that bot's own branch prefix, opened from this
repository itself (never a fork)? Only then does the workflow skip the
attestation check and instead run `./scripts/verify-fast` (or
`./scripts/verify-template.sh` for a full-tier change, chosen the same
way `scripts/ci_tier.py` would classify any standalone pull request)
directly on the hosted runner. Any PR that fails any one of these
conditions keeps today's attestation-only behavior -- this is a small,
exact exemption, not a blanket "any `[bot]` account" rule (see
`scripts/pr_lifecycle.py`'s `dependabot_auto_merge_exemption` for the
same positive-allowlist shape applied to a different check).
"""

from __future__ import annotations

import argparse
import sys

# Issue #753: first (and, for now, only) entry. Add a bot here only with
# its own tracking Issue recording why (see docs/ci-policy.md's "通則"
# for scan_writers exceptions -- the same discipline applies here).
BOT_HEAD_PREFIXES = {
    "dependabot[bot]": "dependabot/",
}


def hosted_verify_eligibility(
    author: str, head_ref: str, head_repo: str, base_repo: str
) -> tuple[bool, str]:
    """Return whether a PR may skip attestation for real hosted verification."""
    prefix = BOT_HEAD_PREFIXES.get(author)
    if prefix is None:
        return (
            False,
            f"author {author!r} is not on the hosted-verification allowlist",
        )
    if not head_ref.startswith(prefix):
        return (
            False,
            f"head ref {head_ref!r} does not match the {author!r} "
            f"prefix {prefix!r}",
        )
    if not head_repo or head_repo != base_repo:
        return (
            False,
            "head repository is not this repository (a fork cannot be "
            "allowlisted)",
        )
    return (
        True,
        f"{author} on {head_ref!r} in {head_repo!r} is eligible for "
        "hosted verification",
    )


def main(argv: list[str] | None = None) -> int:
    """Print the eligibility reason and write the GitHub Actions output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--author", default="")
    parser.add_argument("--head-ref", default="")
    parser.add_argument("--head-repo", default="")
    parser.add_argument("--base-repo", default="")
    parser.add_argument(
        "--github-output",
        help="Append eligible=true|false to this file ($GITHUB_OUTPUT).",
    )
    args = parser.parse_args(argv)
    eligible, reason = hosted_verify_eligibility(
        args.author, args.head_ref, args.head_repo, args.base_repo
    )
    sys.stderr.write(reason + "\n")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write(f"eligible={'true' if eligible else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
