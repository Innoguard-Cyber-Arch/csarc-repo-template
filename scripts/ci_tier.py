#!/usr/bin/env python3
"""Classify CI work by changed paths and delivery stage."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Plan:
    """Machine-readable CI routing decision."""

    tier: str
    stage: str
    reason: str
    review_state: str
    scopes: tuple[str, ...]
    risks: tuple[str, ...]
    run_governance: bool
    run_osv: bool
    run_zizmor: bool
    run_deep: bool
    upload_site: bool


def scope_for(path: str) -> str:
    """Map one repository path to its narrowest CI concern."""
    name = Path(path).name.removesuffix(".jinja")
    if path.startswith(("site/", "template/site/")) or path.startswith(
        ".github/ISSUE_TEMPLATE/"
    ):
        return "docs"
    if path == ".gitignore":
        return "source"
    if (
        path.startswith((".github/workflows/", ".github/actions/"))
        or "/.github/workflows/" in path
        or "/.github/actions/" in path
        or name in {"action.yml", "action.yaml", "zizmor.yml"}
    ):
        return "workflow"
    if path in {".github/CODEOWNERS", ".github/REVIEWERS", "AGENTS.md"} or (
        path.startswith(("policies/", "template/policies/"))
        or path.startswith("scripts/apply-repository-settings")
        or path.startswith("scripts/check-governance-drift")
    ):
        return "governance"
    if path.endswith(".sh") or (
        path.startswith(("scripts/", "template/scripts/")) and "." not in name
    ):
        return "shell"
    if (
        name
        in {
            "package.json",
            "pnpm-lock.yaml",
            "pyproject.toml",
            "uv.lock",
        }
        or path
        in {
            ".github/dependabot.yml",
            "template/.github/dependabot.yml",
            "template/.github/dependabot.yml.jinja",
        }
        or path.startswith(".github/dependency-review-config")
    ):
        return "dependency"
    if (
        path == "copier.yml"
        or path.startswith("profiles/")
        or (
            path.startswith("template/")
            and name
            not in {
                ".release-please-manifest.json",
                "release-please-config.json",
                "version.txt",
            }
        )
    ):
        return "template"
    if path.startswith("docs/") or path.endswith((".md", ".html")):
        return "docs"
    if path.startswith(("src/", "tests/", "scripts/")):
        return "source"
    return "unknown"


def affects_decision_site(path: str) -> bool:
    """Return whether a changed path affects the portable decision site."""
    return path.startswith(("site/", "template/site/")) or path in {
        "docs/index.html",
        "docs/site-content.js",
        "docs/site-theme.css",
        "scripts/render_site.py",
        "template/docs/site-content.js.jinja",
        "template/docs/site-theme.css.jinja",
        "template/scripts/render_site.py",
    }


def risks_for(path: str) -> set[str]:
    """Identify changes that require explicit, fail-closed routing."""
    name = Path(path).name.removesuffix(".jinja")
    scope = scope_for(path)
    risks = {scope} & {"workflow", "governance"}
    risks.update(
        ("verifier",)
        if path.startswith(("scripts/", "template/scripts/"))
        else ()
    )
    if path == "copier.yml" or path.startswith("template/"):
        risks.add("generator")
    if path.startswith("src/csarc_cli/") or path == "tests/test_cli.py":
        risks.add("cli-adoption-update")
    if (
        path in {"pyproject.toml", "template/pyproject.toml.jinja"}
        or path.startswith(("tests/", "template/tests/"))
        or name in {"verify-fast", "verify-template.sh", "verify"}
    ):
        risks.add("test-harness")
    if "release" in name or path in {
        ".release-please-manifest.json",
        "release-please-config.json",
        "version.txt",
    }:
        risks.add("release")
    if (
        name in {"SECURITY.md", "scan-secrets", "zizmor.yml", "osv.yml"}
        or scope == "dependency"
        or path.startswith(".github/dependency-review-config")
        or path
        in {".github/dependabot.yml", "template/.github/dependabot.yml.jinja"}
    ):
        risks.add("security")
    if "promotion" in name:
        risks.add("promotion")
    if "provenance" in path or name in {
        "verify_release_consumption.py",
        "test_release_consumption.py",
        "artifact-consumption.md",
    }:
        risks.add("provenance")
    if (
        name == "ci_tier.py"
        or path.endswith("/.github/workflows/ci.yml.jinja")
        or path
        in {
            ".github/workflows/ci.yml",
            ".github/workflows/reusable-ci.yml",
        }
    ):
        risks.add("ci-router")
    if scope == "unknown":
        risks.add("unknown")
    return risks


def full_risk_reason(
    stage: str, scopes: tuple[str, ...], risks: tuple[str, ...]
) -> str | None:
    """Explain why a candidate must escalate to the integrated full gate."""
    if "unknown" in scopes:
        return "unknown high-risk path"
    if stage == "integrated" and risks:
        return "direct-to-main risk: " + ", ".join(risks)
    return None


def classify(
    event: str,
    base: str,
    head: str,
    labels: set[str],
    changed_files: list[str],
    *,
    draft: bool = False,
    force_full: bool = False,
) -> Plan:
    """Select a safe tier from the event, delivery stage, and changed paths."""
    force_full = force_full or event == "schedule"
    scopes = tuple(sorted({scope_for(path) for path in changed_files}))
    risks = tuple(
        sorted({risk for path in changed_files for risk in risks_for(path)})
    )
    delivery = re.fullmatch(r"dev/(m[1-9][0-9]*-[a-z0-9][a-z0-9-]*)", base)
    sync = re.fullmatch(
        r"sync/main-to-(m[1-9][0-9]*-[a-z0-9][a-z0-9-]*)-[0-9a-f]{7,40}",
        head,
    )
    reviewed_sync = (
        event == "pull_request"
        and delivery is not None
        and sync is not None
        and delivery.group(1) == sync.group(1)
    )
    stage = (
        "post-merge"
        if event == "push"
        else "scheduled"
        if event == "schedule"
        else "manual"
        if force_full or event == "workflow_dispatch"
        else "sync"
        if reviewed_sync
        else "integrated"
        if base == "main"
        else "issue"
    )
    promotion = (
        event in {"pull_request", "merge_group"}
        and base == "main"
        and (
            re.fullmatch(r"dev/m[1-9][0-9]*-[a-z0-9][a-z0-9-]*", head)
            is not None
            or "promotion" in labels
        )
    )
    hotfix = event == "pull_request" and base == "main" and "hotfix" in labels
    recovery = (
        event == "pull_request"
        and base == "main"
        and "release-recovery" in labels
    )
    review_state = (
        ("draft" if event == "pull_request" and draft else "ready")
        if event == "pull_request"
        else "not-applicable"
    )
    if force_full:
        reason = (
            "scheduled deep verification"
            if event == "schedule"
            else "manual full verification"
        )
        tier = "full"
    elif review_state == "draft":
        tier = "docs" if scopes == ("docs",) and not risks else "fast"
        reason = (
            "draft work in progress; full verification deferred until ready"
        )
    elif promotion:
        tier, reason = "full", "delivery promotion"
    elif hotfix or recovery:
        tier = "full"
        reason = "hotfix to main" if hotfix else "release recovery to main"
    elif event == "merge_group":
        tier, reason = "full", "merge queue candidate"
    elif event == "push":
        tier, reason = "post-merge", "pull request result already verified"
    elif not changed_files:
        tier, reason = "full", "changed paths unavailable"
    elif risk_reason := full_risk_reason(stage, scopes, risks):
        tier, reason = "full", risk_reason
    elif scopes == ("docs",) and not reviewed_sync:
        tier, reason = "docs", "documentation-only change"
    else:
        tier = "fast"
        reason = (
            "reviewed main sync"
            if reviewed_sync
            else "change-aware pull request verification"
        )
    scheduled = stage == "scheduled"
    return Plan(
        tier=tier,
        stage=stage,
        reason=reason,
        review_state=review_state,
        scopes=scopes,
        risks=risks,
        run_governance=scheduled or "governance" in scopes,
        run_osv=scheduled or "dependency" in scopes,
        run_zizmor=scheduled or "workflow" in scopes,
        run_deep=review_state != "draft"
        and (
            event == "schedule"
            or (stage == "integrated" and "release" in risks)
        ),
        upload_site=(
            force_full
            or promotion
            or any(map(affects_decision_site, changed_files))
        ),
    )


def read_paths(path: Path) -> list[str]:
    """Read NUL-delimited paths without losing whitespace or newlines."""
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in path.read_bytes().split(b"\0")
        if item
    ]


def write_outputs(path: Path, plan: Plan) -> None:
    """Expose scalar plan fields as GitHub Actions step outputs."""
    values = {
        "tier": plan.tier,
        "stage": plan.stage,
        "reason": plan.reason,
        "review_state": plan.review_state,
        "scopes": ",".join(plan.scopes),
        "risks": ",".join(plan.risks),
        "run_governance": str(plan.run_governance).lower(),
        "run_osv": str(plan.run_osv).lower(),
        "run_zizmor": str(plan.run_zizmor).lower(),
        "run_deep": str(plan.run_deep).lower(),
        "upload_site": str(plan.upload_site).lower(),
    }
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def render_summary(plan: Plan) -> str:
    """Render the routing evidence shown in the workflow summary."""
    scopes = ", ".join(plan.scopes) or "none"
    return (
        "## CI routing\n\n"
        f"- Tier: `{plan.tier}`\n"
        f"- Stage: `{plan.stage}`\n"
        f"- Reason: {plan.reason}\n"
        f"- Review state: `{plan.review_state}`\n"
        f"- Scopes: `{scopes}`\n"
        f"- Risks: `{', '.join(plan.risks) or 'none'}`\n"
        f"- Remote governance: `{plan.run_governance}`\n"
        f"- OSV: `{plan.run_osv}`\n"
        f"- Zizmor: `{plan.run_zizmor}`\n"
        f"- Deep matrix: `{plan.run_deep}`\n"
        f"- Decision site artifact: `{plan.upload_site}`\n"
    )


def main() -> None:
    """Classify one workflow event and write its evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--labels", default="")
    parser.add_argument("--files-from", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--force-full", action="store_true")
    args = parser.parse_args()
    plan = classify(
        args.event,
        args.base,
        args.head,
        {label for label in args.labels.split(",") if label},
        read_paths(args.files_from),
        draft=args.draft,
        force_full=args.force_full,
    )
    args.output_json.write_text(
        json.dumps(asdict(plan), indent=2) + "\n", encoding="utf-8"
    )
    if args.github_output:
        write_outputs(args.github_output, plan)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as summary:
            summary.write(render_summary(plan))


if __name__ == "__main__":
    main()
