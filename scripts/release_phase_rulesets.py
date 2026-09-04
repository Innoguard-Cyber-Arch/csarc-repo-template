#!/usr/bin/env python3
"""Gate the Ruleset self-approval bypass scope to `release_phase` (Issue #607).

`release_phase` (alpha/beta/release, declared by hand in
`policies/project-stage.json`) is this project's whole-project release
maturity axis. It is deliberately a THIRD, distinct concept from two other
"stage"-shaped axes that already exist in this repository -- do not
conflate any of the three:

* `scripts/generate_audit_trail.py`'s `governance_stage` (alpha/beta/stable)
  classifies a single pull request's *source branch pattern* on its way to
  its target branch. It is per-PR, not per-project, and its "stable"
  value has no relationship to `release_phase`'s "release" value.
* `profiles/catalog.yaml`'s per-profile `stage` classifies one language or
  tool profile's own maturity (alpha/beta/future, etc). It is per-profile,
  not per-project.
* `release_phase` (this module) classifies neither a PR nor a profile: it
  is a single, manually-declared value for the *whole project's* own
  release maturity, and it gates how far the Alpha self-approval Ruleset
  bypass (Issue #580, `docs/ci-policy.md` "Alpha 自我核准 bypass") is
  allowed to reach.

Background (see #580): a repository that structurally has only one real
human account cannot satisfy `require_code_owner_review` /
`required_approving_review_count` through a Ruleset -- GitHub refuses to
let anyone approve their own pull request, with no repo-side workaround.
The fix is a `bypass_actors` entry for the repository-admin role
(`{"actor_type": "RepositoryRole", "actor_id": 5, "bypass_mode":
"pull_request"}`). #580 also found that this bypass's actual reach is
wider than its name suggests: it does not only relax the `pull_request`
rule, it relaxes `required_status_checks` too, because GitHub's
`bypass_actors` field applies to an entire Ruleset, not to one rule type
inside it.

This module implements #607's decision: that wider reach must not be a
permanent, all-phases fact. `required_status_checks` bypass-exemption is
only acceptable in "alpha"; from "beta" onward, required checks must
really pass. Reaching that split needs the two rule types living in
separate Rulesets whenever they must diverge:

* alpha:   `required_status_checks` is folded into the review Ruleset, so
           it inherits the same `bypass_actors` (both bypassable).
* beta:    `required_status_checks` lives in its own Ruleset whose
           `bypass_actors` is always `[]` (never bypassable), while the
           review Ruleset keeps its declared `bypass_actors`.
* release: same two-Ruleset split as beta, but the review Ruleset's own
           `bypass_actors` must also be empty -- the bypass is retired
           entirely. `check_release_phase_bypass` below makes that a
           structural, CI-enforced guarantee instead of an operator's
           reminder to edit a file: `scripts/check-bypass-lifecycle`
           (wired into `./scripts/verify-fast`) fails closed if a
           `release_phase: "release"` commit still carries a non-empty
           `bypass_actors` anywhere.

`scripts/apply-repository-settings.sh` calls this module's `assemble`
command to compute the effective Ruleset payload(s) it pushes to GitHub;
`scripts/check-bypass-lifecycle` calls its `check` command as a
regression-tested, fail-closed gate.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_RELEASE_PHASES = ("alpha", "beta", "release")

JsonObject = dict[str, Any]


def load_release_phase(project_stage_path: Path) -> str:
    """Read and validate `release_phase` from policies/project-stage.json.

    This value is always hand-declared (never inferred from branch
    patterns or semver, per Issue #607's decision) -- the maintainer
    edits this file directly through a reviewed pull request when the
    project genuinely transitions phases.
    """
    data = json.loads(project_stage_path.read_text(encoding="utf-8"))
    phase = data.get("release_phase")
    if phase not in VALID_RELEASE_PHASES:
        raise ValueError(
            f"{project_stage_path}: release_phase must be one of "
            f"{VALID_RELEASE_PHASES}, got {phase!r}"
        )
    return phase


def assemble_rulesets(
    release_phase: str, review: JsonObject, required_checks: JsonObject
) -> list[JsonObject]:
    """Return the effective Ruleset payload(s) GitHub should enforce.

    Always returns exactly two payloads, `[review, required_checks]`, so
    the caller manages a stable two-Ruleset live layout across phases: a
    review Ruleset (`non_fast_forward` + `pull_request`) and a required
    checks Ruleset (`required_status_checks`). In "alpha" the
    required_checks rule is moved into the review payload instead (so it
    inherits the same `bypass_actors`), and the required_checks payload's
    own `rules` becomes empty. From "beta" onward the two stay separate,
    unchanged from their checked-in form.

    Neither input mapping is mutated; each returned payload is an
    independent deep copy.
    """
    if release_phase not in VALID_RELEASE_PHASES:
        raise ValueError(f"unknown release_phase: {release_phase!r}")
    review = copy.deepcopy(review)
    required_checks = copy.deepcopy(required_checks)
    if release_phase == "alpha":
        review["rules"] = [*review["rules"], *required_checks["rules"]]
        required_checks["rules"] = []
    return [review, required_checks]


def check_release_phase_bypass(
    release_phase: str, rulesets: list[JsonObject]
) -> list[str]:
    """Return Ruleset names violating the release-phase fail-closed rule.

    Only `release_phase == "release"` is checked: "alpha" and "beta" may
    legitimately declare a non-empty `bypass_actors`. An empty return
    means the check passes. Callers should pass the RAW, checked-in
    Ruleset payloads here (not the phase-`assemble_rulesets` output), so a
    mistake is caught even before assembly would fold it away -- see the
    module docstring's "release" bullet and Issue #607 acceptance
    criterion 3.
    """
    if release_phase != "release":
        return []
    return [
        ruleset.get("name", "<unnamed>")
        for ruleset in rulesets
        if ruleset.get("bypass_actors")
    ]


def _load_json(path: Path) -> JsonObject:
    return json.loads(path.read_text(encoding="utf-8"))


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("assemble", "check"),
        help=(
            "assemble: print the effective Ruleset payload(s) for the "
            "current release_phase as a JSON array (used by "
            "apply-repository-settings.sh). check: fail closed (exit 1) "
            "if release_phase is 'release' and any checked-in Ruleset "
            "still declares a non-empty bypass_actors (used by "
            "scripts/check-bypass-lifecycle)."
        ),
    )
    parser.add_argument(
        "--project-stage",
        type=Path,
        default=REPO_ROOT / "policies" / "project-stage.json",
    )
    parser.add_argument(
        "--review-ruleset",
        type=Path,
        default=REPO_ROOT / "policies" / "rulesets.json",
    )
    parser.add_argument(
        "--required-checks-ruleset",
        type=Path,
        default=REPO_ROOT / "policies" / "rulesets-required-checks.json",
    )
    args = parser.parse_args(argv)

    release_phase = load_release_phase(args.project_stage)
    review = _load_json(args.review_ruleset)
    required_checks = _load_json(args.required_checks_ruleset)

    if args.command == "assemble":
        assembled = assemble_rulesets(release_phase, review, required_checks)
        print(json.dumps(assembled))  # noqa: T201
        return 0

    offenders = check_release_phase_bypass(
        release_phase, [review, required_checks]
    )
    if offenders:
        print(  # noqa: T201
            "release_phase is 'release' but these Rulesets still declare "
            "a non-empty bypass_actors: "
            f"{', '.join(offenders)}. Clear bypass_actors in "
            f"{args.review_ruleset} and {args.required_checks_ruleset} "
            "before merging a release_phase transition to 'release' "
            "(Issue #607).",
            file=sys.stderr,
        )
        return 1
    print(  # noqa: T201
        f"release_phase is {release_phase!r}; no fail-closed "
        "bypass_actors violation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
