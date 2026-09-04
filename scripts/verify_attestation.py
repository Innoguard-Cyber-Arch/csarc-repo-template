#!/usr/bin/env python3
"""Local test-attestation trailer: format, and hosted-side validation.

Issue #661 moves the `verify` required check off GitHub Actions: instead
of a hosted runner re-executing `scripts/verify-fast` /
`scripts/verify-template.sh` (or, in a generated project,
`scripts/verify-fast` / `scripts/verify`), the developer runs them
locally, and on success the script appends a single-line trailer to the
current HEAD commit:

    Verified-locally: sha256=<tree hash> tier=fast|full at=<UTC ISO 8601>

The hosted `verify` job then does NOT re-run anything -- it only checks
that trailer against three independent conditions, all implemented here so
they are unit-testable without a GitHub-hosted runner:

1. presence  -- the commit actually carries a well-formed trailer.
2. hash      -- the trailer's `sha256=` value matches the commit's own
                `git rev-parse <sha>^{tree}` exactly.
3. freshness -- the trailer's `at=` timestamp is neither in the future
                (beyond a small clock-skew allowance) nor older than a
                bounded window.

A fourth, optional condition -- tier sufficiency -- exists because Issue
#661 explicitly asked for adversarial review of this design: without it, a
contributor could always run the cheap `scripts/verify-fast` locally (which
unconditionally writes `tier=fast`) even on a change that
`scripts/ci_tier.py` classifies as needing `full` verification (for example
one that edits `.github/workflows/`), and the hosted job -- which no longer
executes anything itself -- would have no way to tell the difference. When
`check_attestation()` is given `required_tier` (the tier `ci_tier.py`
already, independently, computed for this exact PR), `tier=fast` only
satisfies a `docs` or `fast` requirement; only `tier=full` satisfies a
`full` requirement. This function does not re-implement `ci_tier.py`'s
routing logic, only compares against its answer, matching this
repository's existing principle of reusing one classifier rather than
maintaining two (see `promotion_gate.py`'s `check-route` and
`docs/ci-policy.md`'s discussion of it).

## The field name says "sha256"; the value is git's own tree hash

The trailer's `sha256=` key is a content-identity label, not a promise
about which hash algorithm produced the value. In practice it holds
whatever `git rev-parse <sha>^{tree}` returns for that repository's
configured object format -- SHA-1 (40 hex characters) for the overwhelming
majority of real repositories, including this one, or SHA-256 (64 hex
characters) only for a repository explicitly initialized with
`--object-format=sha256`. This module accepts either length rather than
hardcoding one, and the actual verification is the exact-string comparison
against that same commit's own tree hash, not the length or algorithm.
Git's tree hash was chosen deliberately over a bespoke hash of file
contents: it is already deterministic, already collision-resistant, and
free to compute (`git rev-parse HEAD^{tree}`) -- inventing a second hash of
the same content would only add a place for the two to silently drift.

## Why this cannot be forged by mistake, only by deliberate fraud

`git commit --amend` (used to attach the trailer, see
`scripts/write-verify-attestation`) that only changes the commit message
-- never touching the index -- never changes the tree. That means the tree
hash computed *before* the amend is still that commit's real tree hash
*after* the amend, which is what makes condition 2 meaningful: a trailer
copy-pasted from an older commit, or left over after new changes were
folded into the same commit without re-verifying, will have the *wrong*
tree hash and fail closed. That is the accidental-omission case this
mechanism is built to catch ("forgot to rerun", "ran against the wrong
version" -- Issue #661's own framing).

What this mechanism does **not** defend against, and Issue #661 records as
an accepted residual risk rather than a design flaw: a contributor who
never ran verification at all, but knows `git rev-parse HEAD^{tree}` is
just a hash of already-visible file content, could hand-compute the
correct value and hand-write a completely well-formed, fresh, correctly
-hashed trailer without ever running a single check. That is
indistinguishable, by construction, from a genuine local pass -- the same
category of risk as writing false claims directly into a PR description
today. Detecting *that* would require remote attestation/provenance
tooling this repository does not have; Issue #171's quota-only local
-attestation fallback (a structurally different, human-confirmed-per-PR
exception, not a routine mechanism -- see that Issue and
`docs/ci-policy.md`) does not close this gap either. See
`scripts/write-verify-attestation` for the write-side half of this design,
including why the working tree must be clean before a trailer is written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TRAILER_TOKEN = "Verified-locally"  # noqa: S105 - a git trailer name, not a secret
VALID_TIERS = ("fast", "full")
# "docs" is a real scripts/ci_tier.py classification but never an attested
# tier -- scripts/verify-fast always attests tier=fast for both its "docs"
# and "fast" internal branches (see its own trailer-write call sites), so
# "docs" only ever appears on the *required* side of a tier-sufficiency
# check, never on the *attested* side.
VALID_REQUIRED_TIERS = (*VALID_TIERS, "docs")
_TIER_RANK = {"docs": 0, "fast": 1, "full": 2}

# One line, anywhere in the commit message:
#   Verified-locally: sha256=<hex> tier=(fast|full) at=<UTC ISO 8601>
# The hash length is intentionally unconstrained beyond "plausible hex" --
# see the module docstring for why 40 (SHA-1) and 64 (SHA-256) are both
# legitimate, and the real check is an exact-string comparison, not a
# length check.
TRAILER_PATTERN = re.compile(
    r"^Verified-locally:\s*sha256=(?P<sha256>[0-9a-fA-F]{32,64})\s+"
    r"tier=(?P<tier>fast|full)\s+"
    r"at=(?P<at>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Attestation:
    """One parsed `Verified-locally:` trailer."""

    sha256: str
    tier: str
    at: dt.datetime


@dataclass(frozen=True)
class CheckResult:
    """Outcome of validating one commit's attestation against reality."""

    ok: bool
    reason: str


def parse_trailer(message: str) -> Attestation | None:
    """Extract the last well-formed `Verified-locally:` trailer, or None.

    Takes the *last* match (mirroring `check_bypass_trace.parse_trace`) so
    a stray duplicate cannot silently shadow the one the verification
    scripts most recently wrote. `scripts/write-verify-attestation` always
    normalizes to exactly one trailer via `git interpret-trailers
    --if-exists replace`, so a well-behaved commit never actually has more
    than one; this function stays defensive regardless of how the commit
    message was produced.
    """
    matches = list(TRAILER_PATTERN.finditer(message))
    if not matches:
        return None
    match = matches[-1]
    try:
        at = dt.datetime.strptime(
            match.group("at"), "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=dt.UTC)
    except ValueError:
        return None
    return Attestation(
        sha256=match.group("sha256").lower(), tier=match.group("tier"), at=at
    )


def render_trailer(
    sha256: str, tier: str, at: dt.datetime | None = None
) -> str:
    """Build the single-line trailer text for one successful verification."""
    if tier not in VALID_TIERS:
        raise ValueError(f"tier must be one of {VALID_TIERS!r}, got {tier!r}")
    if not re.fullmatch(r"[0-9a-fA-F]{32,64}", sha256):
        raise ValueError(
            f"sha256 does not look like a git tree hash: {sha256!r}"
        )
    at = (at or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    at_text = at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{TRAILER_TOKEN}: sha256={sha256.lower()} tier={tier} at={at_text}"


def check_attestation(
    message: str,
    actual_tree_hash: str,
    *,
    now: dt.datetime | None = None,
    max_age_hours: float = 24.0,
    max_clock_skew_minutes: float = 5.0,
    required_tier: str | None = None,
) -> CheckResult:
    """Validate one commit's trailer against its real tree hash and the clock.

    Pure function: takes the commit message text and the tree hash as
    plain strings (both trivially obtained via `git log -1 --pretty=%B
    <sha>` / `git rev-parse <sha>^{tree}` by the CLI below) rather than
    shelling out itself, so it is unit-testable with plain strings and no
    git repository at all.

    `max_age_hours` defaults to 24: long enough that a normal gap between
    "verify locally" and "push" (writing the PR description, a lunch
    break, picking the work back up the next morning) does not force a
    needless rerun, short enough that "reuse a verification run from days
    or weeks ago" -- Issue #661's own stated threat ("拿很久以前的驗證結果
    冒充") -- is never a straight-line pass; it mirrors this repository's
    own precedent for the same kind of judgment call
    (`RELEASE_DRIFT_HOURS` in `scripts/check-release-drift`, also 24h
    by default). Note that the hash check already binds the trailer to
    exact tree *content* -- staleness here is not really about forgery
    (a stale-but-honest trailer for unchanged content is still an accurate
    historical fact), it is about environment drift: the same tree could
    plausibly fail today (a dependency got yanked, a lint rule changed)
    even though it genuinely passed N hours ago.

    `max_clock_skew_minutes` guards the *other* direction: without an
    explicit "not in the future" check, an attacker (or a badly-skewed
    local clock) could stamp `at=` far in the future, and staleness alone
    would never catch it -- a future timestamp is never "too old". Fresh
    is not just "not stale", it is "not stale, and not fabricated to look
    perpetually fresh".
    """
    attestation = parse_trailer(message)
    if attestation is None:
        return CheckResult(
            False, "no 'Verified-locally:' trailer found on this commit"
        )

    actual = actual_tree_hash.strip().lower()
    # Defensive, not merely stylistic: an empty `actual` would otherwise
    # only fail this comparison because parse_trailer() above already
    # guarantees attestation.sha256 is non-empty hex -- but that guarantee
    # living in a different function is exactly the kind of coupling worth
    # not trusting blindly. Treat a blank actual hash as a caller/plumbing
    # error, never as "vacuously equal to nothing in particular".
    if not re.fullmatch(r"[0-9a-f]{32,64}", actual):
        return CheckResult(
            False,
            f"could not determine this commit's actual tree hash "
            f"(got {actual_tree_hash!r}); this indicates a plumbing problem "
            "in the caller, not a missing or bad trailer",
        )
    if attestation.sha256 != actual:
        return CheckResult(
            False,
            "attested sha256 does not match this commit's actual tree hash "
            f"(attested={attestation.sha256}, actual={actual}); the commit "
            "was likely amended, cherry-picked, or the trailer was copied "
            "from a different commit -- rerun verification locally and "
            "let it rewrite the trailer",
        )

    now = now or dt.datetime.now(dt.UTC)
    age = now - attestation.at
    if age < -dt.timedelta(minutes=max_clock_skew_minutes):
        return CheckResult(
            False,
            f"attested at={attestation.at.isoformat()} is in the future "
            f"relative to now={now.isoformat()} by more than "
            f"{max_clock_skew_minutes} minutes -- clock skew or a "
            "fabricated timestamp",
        )
    if age > dt.timedelta(hours=max_age_hours):
        return CheckResult(
            False,
            f"attestation is stale: at={attestation.at.isoformat()} is "
            f"{age.total_seconds() / 3600:.1f}h old, older than the "
            f"{max_age_hours}h freshness window -- rerun verification "
            "locally and push again",
        )

    if required_tier is not None:
        if required_tier not in VALID_REQUIRED_TIERS:
            raise ValueError(f"unexpected required_tier: {required_tier!r}")
        if _TIER_RANK[attestation.tier] < _TIER_RANK[required_tier]:
            return CheckResult(
                False,
                f"this change needs '{required_tier}' verification "
                f"(scripts/ci_tier.py) but the attestation only claims "
                f"tier={attestation.tier!r} -- run "
                "./scripts/verify-template.sh (in a generated project, "
                "./scripts/verify) locally, not the fast entry point",
            )

    return CheckResult(
        True,
        f"verified: tier={attestation.tier} at={attestation.at.isoformat()}",
    )


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout


def _parse_utc(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.UTC
    )


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    render_parser = sub.add_parser(
        "render", help="Print one Verified-locally trailer line"
    )
    render_parser.add_argument("--sha256", required=True)
    render_parser.add_argument("--tier", required=True, choices=VALID_TIERS)
    render_parser.add_argument(
        "--at", default=None, help="UTC ISO 8601 timestamp; defaults to now"
    )

    check_parser = sub.add_parser(
        "check", help="Validate one commit's attestation against reality"
    )
    check_parser.add_argument(
        "commit", help="Commit-ish to validate, e.g. a SHA"
    )
    check_parser.add_argument("--max-age-hours", type=float, default=24.0)
    check_parser.add_argument(
        "--max-clock-skew-minutes", type=float, default=5.0
    )
    check_parser.add_argument(
        "--required-tier", default=None, choices=VALID_REQUIRED_TIERS
    )
    check_parser.add_argument(
        "--now", default=None, help="Override 'now' for testing, UTC ISO 8601"
    )
    check_parser.add_argument(
        "--repo", default=None, help="Path to the git repository (default: cwd)"
    )

    args = parser.parse_args(argv)

    if args.command == "render":
        at = _parse_utc(args.at) if args.at else None
        print(render_trailer(args.sha256, args.tier, at))  # noqa: T201
        return 0

    repo = Path(args.repo) if args.repo else None
    try:
        tree_hash = _run_git(
            ["rev-parse", f"{args.commit}^{{tree}}"], cwd=repo
        ).strip()
        message = _run_git(["log", "-1", "--pretty=%B", args.commit], cwd=repo)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)  # noqa: T201
        return 2

    now = _parse_utc(args.now) if args.now else None
    result = check_attestation(
        message,
        tree_hash,
        now=now,
        max_age_hours=args.max_age_hours,
        max_clock_skew_minutes=args.max_clock_skew_minutes,
        required_tier=args.required_tier,
    )
    stream = sys.stdout if result.ok else sys.stderr
    print(result.reason, file=stream)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
