"""Regression checks for Issue #1091: active documentation claims.

Active guidance (README, the repo-site sources, AGENTS, install and policy
documents, and the generated guidance under ``template/``) must not describe
a setting that SPEC-009 retired as if it were still configurable, must not
present the retired routine quota fallback as an active route, and must not
identify or count consuming repositories in public text.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC_009 = ROOT / "docs/specs/SPEC-009-project-settings.md"

# Retired keys whose names are also ordinary words or current names, so a
# line-level search cannot tell a stale reference from current text:
# `review` is the required check name, `language` and `features` are prose,
# `reviewers` describes people, and `work_item_mapping_review` remains the
# one-time adopt input documented by SPEC-009.
AMBIGUOUS_RETIRED_KEYS = frozenset(
    {"features", "language", "review", "reviewers", "work_item_mapping_review"}
)

# A retired key may appear only on a line that marks it as retired, legacy,
# or migrated.
RETIREMENT_MARKER = re.compile(
    r"退役|retired|遷移|migrat|舊|\bold\b|legacy|former|原本|更早|當時"
)

ACTIVE_GUIDANCE = (
    "AGENTS.md",
    "README.md",
    "README.en.md",
    "docs/agent-install.md",
    "docs/install.md",
    "docs/install.en.md",
    "docs/uninstall.md",
    "docs/documentation-policy.md",
    "docs/ci-policy.md",
    "site/content/_index.zh-tw.md",
    "site/content/_index.en.md",
    "template/.csarc/docs/agent-workflow.md.jinja",
    "template/.csarc/docs/ci-policy.md",
    "template/.csarc/docs/documentation-policy.md",
)

PUBLIC_TEXT = (
    "README.md",
    "README.en.md",
    "site/content/_index.zh-tw.md",
    "site/content/_index.en.md",
    "docs/index.html",
    "docs/index.en.html",
    "docs/pilot-adoption.md",
    "docs/adr/template-lifecycle-and-ownership.md",
)


def retired_keys() -> list[str]:
    """Return the SPEC-009 retired keys that a line search can judge."""
    text = SPEC_009.read_text(encoding="utf-8")
    block = text.split("<!-- csarc-retired-keys:start -->", 1)[1]
    block = block.split("<!-- csarc-retired-keys:end -->", 1)[0]
    keys = re.findall(r"^\| `([a-z_]+)` \|", block, re.MULTILINE)
    assert keys, "SPEC-009 retired-key table is empty or unparsable"
    return [key for key in keys if key not in AMBIGUOUS_RETIRED_KEYS]


def test_active_guidance_mentions_retired_keys_only_as_retired() -> None:
    keys = retired_keys()
    findings = []
    for relative in ACTIVE_GUIDANCE:
        lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            for key in keys:
                if re.search(rf"(?<![a-z_]){key}(?![a-z_])", line) and not (
                    RETIREMENT_MARKER.search(line)
                ):
                    findings.append(f"{relative}:{number}: {key}")
    assert findings == []


def test_quota_fallback_is_never_described_as_an_owned_active_route() -> None:
    owners = {
        "AGENTS.md": "the former quota fallback is retired",
        "template/.csarc/docs/agent-workflow.md.jinja": (
            "the former quota fallback is retired"
        ),
    }
    for relative, retirement in owners.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert retirement in text
        assert "admin bypass, and quota fallback" not in text
    for relative in ("docs/ci-policy.md", "template/.csarc/docs/ci-policy.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "quota fallback 的唯一規範來源" not in text
    for relative in ("README.md", "README.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "quota fallback 才能涵蓋" not in text
        assert "A local fallback is only ever possible" not in text


def test_public_text_does_not_name_or_count_consumers() -> None:
    other_repository = re.compile(
        r"github\.com/Innoguard-Cyber-Arch/"
        r"(?!csarc-repo-template\b)[A-Za-z0-9_.-]+"
    )
    count_claim = re.compile(
        r"\b\d+ (?:active )?consuming repositor|\d+ 個 consuming"
    )
    threshold_context = re.compile(
        r"門檻|threshold|at least|至少|Ten active|10 個"
    )
    for relative in PUBLIC_TEXT:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert other_repository.findall(text) == [], relative
        for line in text.splitlines():
            if count_claim.search(line):
                # Platform thresholds name counts as conditions, not as the
                # number of repositories that exist.
                assert threshold_context.search(line), (relative, line[:120])
        assert "0 consuming repositories" not in text
        assert "0 個 consuming repo" not in text
