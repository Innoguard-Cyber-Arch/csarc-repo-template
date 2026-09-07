#!/usr/bin/env python3
"""Evaluate this repository's own capability/permission gaps (Issue #531).

`scripts/apply-repository-settings.sh` already probes what a GitHub *plan*
(Free/Team/Enterprise) allows before applying `policies/*.json`, and prints
a `DEGRADED` marker when a paid or organization-policy-gated capability is
unavailable -- see that script and `docs/adr/capability-aware-governance.md`
for the existing mechanism. This module adds the layer Issue #531 asks for
on top of it: a declarative matrix (`policies/capability-matrix.json`)
naming every capability this repository might rely on, its minimum
permission/plan requirement, and a documented workaround for when it is
missing, plus a pure evaluator that merges that matrix against *observed
facts about this specific repository* into a structured gap report.

This module deliberately does not redesign the DEGRADED mechanism itself
(out of scope per Issue #531's boundary): several matrix rows' workaround
text explicitly points back at the DEGRADED marker `apply-repository-
settings.sh` already prints for that same underlying limitation. This
module only adds the matrix mapping, the merged report, and (via
`scripts/check-repo-capabilities`) the live fact-gathering that feeds it.

Facts are supplied as a JSON object keyed by capability id, each value
`{"status": "allowed" | "blocked" | "unknown", "detail": "<short note>"}`.
`scripts/check-repo-capabilities` gathers these from live `gh api` calls;
tests and `--facts <file>` callers supply them directly from a fixture, so
the evaluation logic below never itself calls `gh` and is fully unit
testable against crafted permission combinations (Issue #531 completion
checklist item 5) without any network access or GitHub auth.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MATRIX_PATH = REPO_ROOT / "policies" / "capability-matrix.json"

VALID_STATUSES = ("allowed", "blocked", "unknown")
LANGUAGES = ("en", "zh-tw")

JsonObject = dict[str, Any]


class CapabilityDataError(ValueError):
    """Raised when the matrix or the supplied facts are malformed."""


def load_matrix(path: Path) -> list[JsonObject]:
    """Load and minimally validate `policies/capability-matrix.json`.

    Only checks the shape this module depends on (an `id` plus bilingual
    `title`/`behavior`/`requirement`/`detection`/`workaround` fields per
    entry) -- it does not re-validate free-form prose content.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise CapabilityDataError(
            f"{path}: 'capabilities' must be a non-empty list"
        )
    seen_ids: set[str] = set()
    for entry in capabilities:
        capability_id = entry.get("id")
        if not isinstance(capability_id, str) or not capability_id:
            raise CapabilityDataError(
                f"{path}: every capability needs a string 'id'"
            )
        if capability_id in seen_ids:
            raise CapabilityDataError(
                f"{path}: duplicate capability id {capability_id!r}"
            )
        seen_ids.add(capability_id)
        for field in (
            "title",
            "behavior",
            "requirement",
            "detection",
            "workaround",
        ):
            value = entry.get(field)
            if not isinstance(value, dict) or any(
                not value.get(language) for language in LANGUAGES
            ):
                raise CapabilityDataError(
                    f"{path}: capability {capability_id!r} field {field!r} "
                    f"must provide non-empty text for {LANGUAGES}"
                )
    return capabilities


def load_facts(raw: str) -> dict[str, JsonObject]:
    """Parse and validate a facts JSON object keyed by capability id."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise CapabilityDataError(
            "facts must be a JSON object keyed by capability id"
        )
    facts: dict[str, JsonObject] = {}
    for capability_id, entry in data.items():
        if not isinstance(entry, dict) or "status" not in entry:
            raise CapabilityDataError(
                f"facts[{capability_id!r}] must be an object with a "
                "'status' field"
            )
        status = entry["status"]
        if status not in VALID_STATUSES:
            raise CapabilityDataError(
                f"facts[{capability_id!r}].status must be one of "
                f"{VALID_STATUSES}, got {status!r}"
            )
        facts[capability_id] = {
            "status": status,
            "detail": entry.get("detail", ""),
        }
    return facts


def evaluate(
    matrix: list[JsonObject], facts: dict[str, JsonObject]
) -> list[JsonObject]:
    """Merge observed `facts` against the declarative `matrix`.

    Returns one result per matrix entry, in matrix order, each carrying the
    matrix's bilingual metadata plus the observed `status`/`detail`. Raises
    `CapabilityDataError` when `facts` and the matrix disagree on which
    capability ids exist -- a missing fact means a capability the matrix
    declares was never actually evaluated (a caller bug, not an unknown
    platform state, which is what the `unknown` status itself is for); an
    extra fact means the facts producer and the matrix have drifted apart.
    """
    matrix_ids = {entry["id"] for entry in matrix}
    fact_ids = set(facts)
    missing = matrix_ids - fact_ids
    if missing:
        raise CapabilityDataError(
            "facts is missing status for capabilities: "
            + ", ".join(sorted(missing))
        )
    extra = fact_ids - matrix_ids
    if extra:
        raise CapabilityDataError(
            "facts references capabilities absent from the matrix: "
            + ", ".join(sorted(extra))
        )

    results: list[JsonObject] = []
    for entry in matrix:
        fact = facts[entry["id"]]
        results.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "behavior": entry["behavior"],
                "requirement": entry["requirement"],
                "detection": entry["detection"],
                "workaround": entry["workaround"],
                "related_degraded_marker": entry.get("related_degraded_marker"),
                "status": fact["status"],
                "detail": fact["detail"],
            }
        )
    return results


def summarize(results: list[JsonObject]) -> dict[str, int]:
    """Count results per status, always including every valid status key."""
    summary = dict.fromkeys(VALID_STATUSES, 0)
    for result in results:
        summary[result["status"]] += 1
    return summary


def gaps(results: list[JsonObject]) -> list[JsonObject]:
    """Return only the non-`allowed` results -- the actual gap list."""
    return [result for result in results if result["status"] != "allowed"]


def render_report(results: list[JsonObject], *, language: str = "en") -> str:
    """Render the human-readable capability/gap report in one language."""
    if language not in LANGUAGES:
        raise CapabilityDataError(f"unsupported language: {language!r}")
    summary = summarize(results)
    lines = [
        "Repository capability check"
        if language == "en"
        else "Repository 能力檢查",
        "",
    ]
    for result in results:
        status = result["status"].upper()
        lines.append(f"[{status}] {result['id']}: {result['title'][language]}")
        if result["detail"]:
            lines.append(f"  observed: {result['detail']}")
        if result["status"] != "allowed":
            lines.append(f"  requirement: {result['requirement'][language]}")
            lines.append(f"  workaround: {result['workaround'][language]}")
    lines.append("")
    if language == "en":
        lines.append(
            f"{summary['allowed']} allowed, {summary['blocked']} blocked, "
            f"{summary['unknown']} unknown out of {len(results)} capabilities."
        )
    else:
        lines.append(
            f"共 {len(results)} 項能力、"
            f"{summary['allowed']} 項 allowed、"
            f"{summary['blocked']} 項 blocked、"
            f"{summary['unknown']} 項 unknown。"
        )
    return "\n".join(lines)


def _read_facts_source(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text(encoding="utf-8")


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("check",),
        help="check: evaluate --facts against --matrix and print the report.",
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=DEFAULT_MATRIX_PATH,
        help="Path to policies/capability-matrix.json.",
    )
    parser.add_argument(
        "--facts",
        required=True,
        help="Path to a facts JSON file, or '-' to read from standard input.",
    )
    parser.add_argument(
        "--language",
        choices=LANGUAGES,
        default="en",
        help="Human-readable report language (ignored with --json).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the machine-readable result instead of the human report.",
    )
    args = parser.parse_args(argv)

    try:
        matrix = load_matrix(args.matrix)
        facts = load_facts(_read_facts_source(args.facts))
        results = evaluate(matrix, facts)
    except (CapabilityDataError, OSError, json.JSONDecodeError) as error:
        print(f"repo_capabilities: {error}", file=sys.stderr)  # noqa: T201
        return 2

    if args.json:
        print(  # noqa: T201
            json.dumps(
                {"capabilities": results, "summary": summarize(results)},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(render_report(results, language=args.language))  # noqa: T201

    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
