#!/usr/bin/env python3
"""Assemble and validate the fixed review/check Ruleset split.

GitHub applies ``bypass_actors`` to a whole Ruleset, so required status
checks must live in a separate Ruleset with no bypass actors. The review
Ruleset may retain only the known repository-admin pull-request bypass; the
level-aware review and lifecycle checks decide whether configured beta/stable
self-review may actually use it.

The filename is retained for update compatibility, but the former
whole-project ``release_phase`` switch no longer exists.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ADMIN_REVIEW_BYPASS = [
    {
        "actor_type": "RepositoryRole",
        "actor_id": 5,
        "bypass_mode": "pull_request",
    }
]

JsonObject = dict[str, Any]


def assemble_rulesets(
    review: JsonObject, required_checks: JsonObject
) -> list[JsonObject]:
    """Return independent copies of the two checked-in Rulesets."""
    return [copy.deepcopy(review), copy.deepcopy(required_checks)]


def check_ruleset_bypass(rulesets: list[JsonObject]) -> list[str]:
    """Return fail-closed structural bypass violations."""
    violations: list[str] = []
    for ruleset in rulesets:
        name = str(ruleset.get("name") or "<unnamed>")
        rule_types = {
            rule.get("type")
            for rule in ruleset.get("rules", [])
            if isinstance(rule, dict)
        }
        bypass = ruleset.get("bypass_actors")
        if "required_status_checks" in rule_types and bypass != []:
            violations.append(f"{name}: required checks must have no bypass")
        if "pull_request" in rule_types and bypass not in (
            [],
            ADMIN_REVIEW_BYPASS,
        ):
            violations.append(f"{name}: review bypass is not allowlisted")
    return violations


def _load_json(path: Path) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("assemble", "check"))
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
    try:
        rulesets = assemble_rulesets(
            _load_json(args.review_ruleset),
            _load_json(args.required_checks_ruleset),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print(  # noqa: T201
            f"Cannot load Ruleset policy: {error}", file=sys.stderr
        )
        return 1
    if args.command == "assemble":
        print(json.dumps(rulesets))  # noqa: T201
        return 0
    violations = check_ruleset_bypass(rulesets)
    if violations:
        print("; ".join(violations), file=sys.stderr)  # noqa: T201
        return 1
    print("Ruleset bypass boundaries are valid.")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
