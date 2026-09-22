#!/usr/bin/env python3
"""Classify CI work by changed paths and delivery stage."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path

VALID_SCOPES = frozenset(
    {
        "dependency",
        "docs",
        "governance",
        "shell",
        "source",
        "template",
        "unknown",
        "workflow",
    }
)
PROJECT_SCOPES = frozenset(
    {"governance", "shell", "source", "template", "unknown", "workflow"}
)


@dataclass(frozen=True)
class Plan:
    """Machine-readable CI routing decision."""

    tier: str
    reason: str
    scopes: tuple[str, ...]
    run_project: bool
    run_governance: bool
    run_osv: bool
    run_zizmor: bool
    upload_site: bool


def scope_for(path: str) -> str:
    """Map one repository path to its narrowest CI concern."""
    name = Path(path).name.removesuffix(".jinja")
    if path.startswith(("docs/site/", ".csarc/site/")) or path.startswith(
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
    if path in {
        ".csarc/config.yml",
        ".github/CODEOWNERS",
        ".csarc/REVIEWERS",
        "AGENTS.md",
    } or (
        path.startswith((".csarc/policies/", "template/.csarc/policies/"))
        or path.startswith(".csarc/scripts/apply-repository-settings")
        or path.startswith(".csarc/scripts/check-governance-drift")
        or path.startswith(".csarc/scripts/request-reviewer")
    ):
        return "governance"
    if path.endswith(".sh") or (
        path.startswith((".csarc/scripts/", "template/.csarc/scripts/"))
        and "." not in name
    ):
        return "shell"
    if (
        name
        in {
            "Cargo.lock",
            "Cargo.toml",
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "pyproject.toml",
            "uv.lock",
            "yarn.lock",
        }
        or name in {"dependabot.yml", "pnpm-workspace.yaml"}
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
                ".csarc/release-please-manifest.json",
                ".csarc/release-please-config.json",
                ".csarc/version.txt",
            }
        )
    ):
        return "template"
    if path.startswith("docs/") or path.endswith((".md", ".html")):
        return "docs"
    if path.startswith(("src/", "tests/", ".csarc/scripts/")):
        return "source"
    return "unknown"


def affects_repo_site(path: str) -> bool:
    """Return whether a changed path affects the portable repo-site build."""
    return path.startswith(("docs/site/", ".csarc/site/")) or path in {
        "docs/index.html",
        "docs/site-content.js",
        "docs/site-content.md",
        "docs/site/theme.css",
        ".csarc/scripts/render_site.py",
    }


def requires_full_on_main(path: str) -> bool:
    """Return whether a standalone change needs the full local suite."""
    name = Path(path).name.removesuffix(".jinja")
    if path == "copier.yml" or path.startswith(("profiles/", "src/csarc_cli/")):
        return True
    if path.startswith("template/") and not path.startswith(
        (
            "template/.github/workflows/",
            "template/.github/actions/",
            "template/.csarc/scripts/",
        )
    ):
        return True
    return path.startswith(
        (".csarc/scripts/", "template/.csarc/scripts/")
    ) and (
        name
        in {
            "check-verify-attestation",
            "ci_tier.py",
            "verify",
            "verify-fast",
            "verify-template.sh",
            "verify_attestation.py",
            "write-verify-attestation",
        }
        or name.startswith("verify-stage-")
    )


def add_scopes(plan: Plan, extra_scopes: set[str]) -> Plan:
    """Add explicitly requested checks without weakening the computed plan."""
    unknown = extra_scopes - VALID_SCOPES
    if unknown:
        raise ValueError(f"unknown CI scope(s): {', '.join(sorted(unknown))}")
    scopes = tuple(sorted(set(plan.scopes) | extra_scopes))
    full = plan.tier == "full"
    return replace(
        plan,
        scopes=scopes,
        run_project=plan.run_project
        or full
        or bool(PROJECT_SCOPES & set(scopes)),
        run_governance=plan.run_governance or full or "governance" in scopes,
        run_osv=plan.run_osv or full or "dependency" in scopes,
        run_zizmor=plan.run_zizmor or full or "workflow" in scopes,
    )


def classify(  # noqa: C901
    event: str,
    base: str,
    head: str,
    labels: set[str],
    changed_files: list[str],
    *,
    force_full: bool = False,
    draft: bool = False,
    verified_sync: bool = False,
) -> Plan:
    """Select a safe tier from the event, delivery stage, and changed paths."""
    scopes = tuple(sorted({scope_for(path) for path in changed_files}))
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
    if force_full:
        tier, reason = "full", "manual full verification"
    elif draft and scopes == ("docs",):
        tier, reason = "fast", "draft documentation change"
    elif draft:
        tier, reason = "fast", "draft risk-owner verification"
    elif promotion:
        tier, reason = "full", "delivery promotion"
    elif hotfix or recovery:
        tier = "full"
        reason = "hotfix to main" if hotfix else "release recovery to main"
    elif event == "merge_group":
        tier, reason = "full", "merge queue candidate"
    elif event == "push":
        tier, reason = "post-merge", "pull request result already verified"
    elif verified_sync:
        tier, reason = "fast", "verified clean delivery synchronization"
    elif not changed_files:
        tier, reason = "full", "changed paths unavailable"
    elif "unknown" in scopes:
        tier, reason = "full", "unknown high-risk path"
    elif (
        event == "pull_request"
        and base == "main"
        and any(map(requires_full_on_main, changed_files))
    ):
        tier, reason = "full", "standalone generator or verifier change"
    elif scopes == ("docs",):
        tier, reason = "fast", "documentation-only change"
    else:
        tier, reason = "fast", "change-aware pull request verification"
    full = tier == "full"
    return Plan(
        tier=tier,
        reason=reason,
        scopes=scopes,
        run_project=full or bool(PROJECT_SCOPES & set(scopes)),
        run_governance=full or "governance" in scopes,
        run_osv=(
            full
            or "dependency" in scopes
            or any(
                Path(path).name
                in {"install-osv-scanner", "verify-dependencies"}
                for path in changed_files
            )
        ),
        run_zizmor=full or "workflow" in scopes,
        upload_site=(
            force_full
            or promotion
            or any(map(affects_repo_site, changed_files))
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
        "reason": plan.reason,
        "scopes": ",".join(plan.scopes),
        "run_project": str(plan.run_project).lower(),
        "run_governance": str(plan.run_governance).lower(),
        "run_osv": str(plan.run_osv).lower(),
        "run_zizmor": str(plan.run_zizmor).lower(),
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
        f"- Reason: {plan.reason}\n"
        f"- Scopes: `{scopes}`\n"
        f"- Project checks: `{plan.run_project}`\n"
        f"- Remote governance: `{plan.run_governance}`\n"
        f"- OSV: `{plan.run_osv}`\n"
        f"- Zizmor: `{plan.run_zizmor}`\n"
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
    parser.add_argument("--force-full", action="store_true")
    parser.add_argument("--draft", choices=("true", "false"), default="false")
    parser.add_argument("--verified-sync", action="store_true")
    parser.add_argument("--extra-scopes", default="")
    args = parser.parse_args()
    try:
        plan = add_scopes(
            classify(
                args.event,
                args.base,
                args.head,
                {label for label in args.labels.split(",") if label},
                read_paths(args.files_from),
                force_full=args.force_full,
                draft=args.draft == "true",
                verified_sync=args.verified_sync,
            ),
            {scope for scope in args.extra_scopes.split(",") if scope},
        )
    except ValueError as error:
        parser.error(str(error))
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
