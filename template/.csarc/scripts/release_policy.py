#!/usr/bin/env python3
"""Plan and verify one release path from observable GitHub capabilities."""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    csarc_config = importlib.import_module("csarc_config")
    stale_branch_detection = importlib.import_module("stale_branch_detection")
    release_phase = importlib.import_module("release_phase")
else:
    csarc_config = importlib.import_module(f"{__package__}.csarc_config")
    stale_branch_detection = importlib.import_module(
        f"{__package__}.stale_branch_detection"
    )
    release_phase = importlib.import_module(f"{__package__}.release_phase")

STATES = {"allowed", "blocked", "unknown"}


CHECKPOINT_ROLES = ("none", "terminal", "deferred")


# Issue #770: `immutable_releases` used to be a third pre-flight, admin-scope
# probe here (`GET repos/{repo}/immutable-releases`) that the hosted
# `GITHUB_TOKEN` can never pass -- there is no `administration` key in the
# Actions `permissions:` schema, so this capability was permanently `blocked`
# or `unknown` for every hosted run and single-handedly forced
# select_release_mode() to `blocked` regardless of `contents`/`release`
# (see #123/#622/#623/#624/#626 and the "hosted 發版路徑的已知限制"
# section in .csarc/docs/ci-policy.md). It is deliberately not part of this
# gate any more.
# The same guarantee -- a release was only published because Immutable
# Releases was actually enabled -- is now proven post-hoc, after publish,
# by .csarc/scripts/publish-release verifying GitHub's own signed release
# attestation (reusing .csarc/scripts/verify_release_consumption.py) instead of
# guessing about it before publication starts.
PUBLISH_CAPABILITIES = ("contents", "release")


RENOVATE_INSTALL_URL = "https://github.com/apps/renovate/installations/new"


DEPENDABOT_FALLBACK = (
    "Keep GitHub Dependabot via .github/dependabot.yml and the existing "
    "required CI/CD checks."
)


@dataclass(frozen=True)
class Capability:
    """One observed permission state and its evidence."""

    state: str
    reason: str

    def __post_init__(self) -> None:
        """Reject states outside the public tri-state contract."""
        if self.state not in STATES:
            raise ValueError(f"invalid capability state: {self.state}")


def select_release_mode(
    capabilities: dict[str, Capability], *, operator_reason: str | None = None
) -> tuple[str, str]:
    """Choose Automatic, Guided, or Blocked without a second publisher.

    Guided mode has one automatically-detected trigger (Actions pull
    requests are blocked or unknown per observed capabilities) and one
    operator-asserted trigger: `operator_reason` is a non-empty, human- or
    agent-authored justification recording a live decision that Actions or
    its webhook delivery is currently unhealthy (see Issue #589 and #587,
    and the "Release 發版不依賴 Actions 健康度的 fallback" section in
    .csarc/docs/ci-policy.md). There is no capability probe for
    "Actions/webhooks are unhealthy": an idle hosted runner or a dropped
    `pull_request` webhook
    delivery looks identical to "nothing to release right now" from the
    GitHub REST API this module probes, so this trigger is deliberately
    manual rather than auto-detected. An operator override can only steer
    an otherwise-automatic release toward the same reviewed Guided path
    (prepare-candidate -> ordinary pull request -> ordinary review); it
    never turns a genuinely blocked publish capability into a usable one,
    and it never skips review.
    """
    pull_requests = capabilities["actions_pull_requests"]
    blocked = [
        name
        for name in PUBLISH_CAPABILITIES
        if capabilities[name].state == "blocked"
    ]
    unknown = [
        name
        for name in PUBLISH_CAPABILITIES
        if capabilities[name].state == "unknown"
    ]
    if blocked or unknown:
        return (
            "blocked",
            "GitHub tag or Release publication is unavailable or unproven: "
            + ", ".join([*blocked, *unknown]),
        )
    if operator_reason:
        return (
            "guided",
            "Operator judged Actions or webhook delivery unhealthy: "
            + operator_reason,
        )
    if pull_requests.state == "allowed":
        return (
            "automatic",
            "Actions pull requests and the artifact handoff are allowed",
        )
    if pull_requests.state != "allowed":
        return (
            "guided",
            f"Actions pull requests are {pull_requests.state}; prepare a "
            "reviewed version candidate locally",
        )
    raise AssertionError("release mode selection is incomplete")


def unknown_capabilities(reason: str) -> dict[str, Capability]:
    """Return a complete unknown result for unavailable observation."""
    return {
        name: Capability("unknown", reason)
        for name in (
            "actions_pull_requests",
            "contents",
            "release",
        )
    }


def preflight_capabilities(repo: str) -> dict[str, Capability]:
    """Leave token permissions unknown until the workflow runs."""
    del repo
    return unknown_capabilities("requires the runtime workflow token")


def preflight_policy_observations(repo: str) -> dict[str, Capability]:
    """Read org/repository settings without treating them as token access."""
    unknown = {
        name: Capability("unknown", "GitHub CLI is unavailable")
        for name in ("organization_policy", "repository_setting")
    }
    executable = shutil.which("gh")
    if executable is None:
        return unknown

    def observe(endpoint: str, scope: str) -> Capability:
        result = subprocess.run(  # noqa: S603
            [executable, "api", endpoint],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return Capability(
                "unknown",
                f"{scope} Actions policy is not readable with the current "
                "identity",
            )
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError:
            response = None
        allowed = (
            response.get("can_approve_pull_request_reviews")
            if isinstance(response, dict)
            else None
        )
        if not isinstance(allowed, bool):
            return Capability(
                "unknown", f"{scope} Actions policy response is incomplete"
            )
        return Capability(
            "allowed" if allowed else "blocked",
            f"{scope} Actions policy "
            + ("allows" if allowed else "blocks")
            + " pull requests",
        )

    owner = repo.split("/", 1)[0]
    return {
        "organization_policy": observe(
            f"orgs/{owner}/actions/permissions/workflow", "organization"
        ),
        "repository_setting": observe(
            f"repos/{repo}/actions/permissions/workflow", "repository"
        ),
    }


def gh_json(executable: str, endpoint: str) -> dict[str, object] | None:
    """Read one GitHub API object without treating failure as permission."""
    result = subprocess.run(  # noqa: S603
        [executable, "api", endpoint],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def renovate_result(
    state: str,
    reason: str,
    *,
    observed: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the optional Renovate integration decision."""
    if state == "available":
        next_step = (
            "Open the installation page, choose only this repository, and "
            "review the App permissions before approving."
        )
    elif state == "request-owner":
        next_step = (
            "Ask the account or organization owner to review the installation "
            "page and grant access only to this repository. Until approved, "
            "keep GitHub Dependabot and the existing required CI/CD checks."
        )
    else:
        next_step = DEPENDABOT_FALLBACK
    return {
        "state": state,
        "reason": reason,
        "next_step": next_step,
        "install_url": RENOVATE_INSTALL_URL,
        "fallback": DEPENDABOT_FALLBACK,
        "requested_access": (
            "The App installation screen is authoritative; Renovate currently "
            "requests organization members read access and repository "
            "administration read plus workflow/content/PR write access."
        ),
        "observed": observed
        or {
            "owner": None,
            "owner_type": None,
            "actor": None,
            "repository_admin": None,
            "organization_owner": None,
        },
    }


def optional_integration_preflight(repo: str) -> dict[str, dict[str, object]]:
    """Classify optional App setup from read-only repository observations."""
    executable = shutil.which("gh")
    if executable is None:
        return {
            "renovate": renovate_result("fallback", "GitHub CLI is unavailable")
        }

    repository = gh_json(executable, f"repos/{repo}")
    if repository is None:
        return {
            "renovate": renovate_result(
                "fallback",
                "Repository permissions are unavailable; installation was "
                "not assumed",
            )
        }
    owner_payload = repository.get("owner")
    permissions = repository.get("permissions")
    owner = (
        owner_payload.get("login")
        if isinstance(owner_payload, dict)
        and isinstance(owner_payload.get("login"), str)
        else None
    )
    owner_type = (
        owner_payload.get("type")
        if isinstance(owner_payload, dict)
        and isinstance(owner_payload.get("type"), str)
        else None
    )
    repository_admin = (
        permissions.get("admin")
        if isinstance(permissions, dict)
        and isinstance(permissions.get("admin"), bool)
        else None
    )
    actor_payload = gh_json(executable, "user")
    actor = (
        actor_payload.get("login")
        if isinstance(actor_payload, dict)
        and isinstance(actor_payload.get("login"), str)
        else None
    )
    observed: dict[str, object] = {
        "owner": owner,
        "owner_type": owner_type,
        "actor": actor,
        "repository_admin": repository_admin,
        "organization_owner": None,
    }
    if owner is None or owner_type not in {"User", "Organization"}:
        return {
            "renovate": renovate_result(
                "fallback",
                "Repository owner type is unknown; installation was not "
                "assumed",
                observed=observed,
            )
        }
    if actor is None or repository_admin is None:
        return {
            "renovate": renovate_result(
                "fallback",
                "Actor or repository permission is unknown; installation was "
                "not assumed",
                observed=observed,
            )
        }
    if not repository_admin:
        return {
            "renovate": renovate_result(
                "fallback",
                "The current actor is not a repository administrator",
                observed=observed,
            )
        }

    if owner_type == "User":
        if actor == owner:
            return {
                "renovate": renovate_result(
                    "available",
                    "The personal repository owner can review an App "
                    "installation",
                    observed=observed,
                )
            }
        return {
            "renovate": renovate_result(
                "request-owner",
                "A repository collaborator cannot install an App for another "
                "personal account",
                observed=observed,
            )
        }

    membership = gh_json(executable, f"orgs/{owner}/memberships/{actor}")
    if membership is None:
        return {
            "renovate": renovate_result(
                "fallback",
                "Organization ownership is unknown; installation was not "
                "assumed",
                observed=observed,
            )
        }
    organization_owner = (
        membership.get("state") == "active"
        and membership.get("role") == "admin"
    )
    if organization_owner:
        return {
            "renovate": renovate_result(
                "available",
                "The current actor is an organization owner and repository "
                "administrator",
                observed={**observed, "organization_owner": True},
            )
        }
    return {
        "renovate": renovate_result(
            "request-owner",
            "Renovate requests organization permissions, so a repository "
            "admin who is only a member must ask an organization owner",
            observed={**observed, "organization_owner": False},
        )
    }


def report(
    capabilities: dict[str, Capability],
    source: str,
    *,
    policies: dict[str, Capability] | None = None,
    operator_reason: str | None = None,
    **extra: object,
) -> dict[str, object]:
    """Build the machine-readable decision record."""
    policy = policies or {
        "organization_policy": Capability("unknown", "not observed"),
        "repository_setting": Capability("unknown", "not observed"),
    }
    effective_capabilities = dict(capabilities)
    policy_blocks = [
        name
        for name in ("organization_policy", "repository_setting")
        if policy[name].state == "blocked"
    ]
    if policy_blocks:
        effective_capabilities["actions_pull_requests"] = Capability(
            "blocked",
            "Actions pull requests are blocked by " + ", ".join(policy_blocks),
        )
    mode, reason = select_release_mode(
        effective_capabilities, operator_reason=operator_reason
    )
    token_permissions = {
        name: asdict(capability)
        for name, capability in sorted(capabilities.items())
    }
    return {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "source": source,
        "mode": mode,
        "reason": reason,
        "operator_override": operator_reason,
        "organization_policy": asdict(policy["organization_policy"]),
        "repository_setting": asdict(policy["repository_setting"]),
        "token_permissions": token_permissions,
        "effective": {
            "mode": mode,
            "reason": reason,
            "actions_pull_requests": asdict(
                effective_capabilities["actions_pull_requests"]
            ),
        },
        # Compatibility alias for callers that predate the split evidence.
        "capabilities": token_permissions,
        **extra,
    }


def write_report(
    payload: dict[str, object], output: Path | None, github_output: Path | None
) -> None:
    """Write JSON plus stable GitHub Actions outputs."""
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    if github_output is not None:
        with github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"mode={payload['mode']}\n")
            handle.write(f"reason={payload['reason']}\n")
            if payload.get("tag"):
                handle.write(f"tag={payload['tag']}\n")
    print(rendered, end="")  # noqa: T201


def parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    result = argparse.ArgumentParser()
    subparsers = result.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--repo", required=True)

    detect = subparsers.add_parser("detect")
    detect.add_argument("--repo", required=True)
    detect.add_argument("--sha", required=True)
    detect.add_argument("--branch", required=True)
    detect.add_argument("--output", type=Path)
    detect.add_argument("--github-output", type=Path)
    detect.add_argument(
        "--operator-reason",
        default=None,
        help=(
            "Non-empty justification for forcing Guided mode because an "
            "operator or agent judged Actions or webhook delivery "
            "currently unhealthy, rather than because Actions pull "
            "requests are blocked by policy. Never forces Automatic or "
            "overrides a genuinely blocked publish capability; see "
            "select_release_mode()."
        ),
    )

    plan = subparsers.add_parser("plan")
    plan.add_argument("--sha", default="HEAD")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--output", type=Path)
    plan.add_argument("--github-output", type=Path)
    plan.add_argument(
        "--phase",
        choices=release_phase.PHASES,
        default=None,
        help=(
            "Release channel to apply to a freshly computed version "
            "(beta/stable); omit it to report the bare core."
        ),
    )
    plan.add_argument(
        "--checkpoint-role", choices=CHECKPOINT_ROLES, default="none"
    )
    plan.add_argument(
        "--source-sha",
        help="Exact reviewed source head of a supported squash merge.",
    )
    candidate = subparsers.add_parser("prepare-candidate")
    candidate.add_argument("--sha", default="HEAD")
    candidate.add_argument("--root", type=Path, default=Path.cwd())
    candidate.add_argument(
        "--phase", choices=release_phase.PHASES, default=None
    )
    verify = subparsers.add_parser("verify-version")
    verify.add_argument("--tag")
    verify.add_argument("--root", type=Path, default=Path.cwd())
    verify_candidate = subparsers.add_parser("verify-candidate-version")
    verify_candidate.add_argument("--base-sha", required=True)
    verify_candidate.add_argument("--root", type=Path, default=Path.cwd())
    verify_delivery = subparsers.add_parser("verify-delivery-version")
    verify_delivery.add_argument("--base-sha", required=True)
    verify_delivery.add_argument("--head-sha", required=True)
    verify_delivery.add_argument("--root", type=Path, default=Path.cwd())
    delivery_version = verify_delivery.add_mutually_exclusive_group(
        required=True
    )
    delivery_version.add_argument("--phase", choices=release_phase.PHASES)
    delivery_version.add_argument("--tag")
    verify_delivery.add_argument(
        "--checkpoint-role", choices=CHECKPOINT_ROLES, default="none"
    )
    verify_promotion = subparsers.add_parser("verify-promotion-version")
    verify_promotion.add_argument("--source-sha", required=True)
    verify_promotion.add_argument("--head-sha", required=True)
    verify_promotion.add_argument("--root", type=Path, default=Path.cwd())
    promotion_version = verify_promotion.add_mutually_exclusive_group(
        required=True
    )
    promotion_version.add_argument("--phase", choices=release_phase.PHASES)
    promotion_version.add_argument("--tag")
    retention = subparsers.add_parser(
        "retention-plan",
        help=(
            "List which Releases should be kept vs. deleted under the "
            "retention policy (dry-run only; never deletes anything)."
        ),
    )
    retention.add_argument("--repo", required=True)
    retention.add_argument("--output", type=Path)
    retention.add_argument("--github-output", type=Path)
    verify_follow_up = subparsers.add_parser("verify-release-follow-up")
    verify_follow_up.add_argument("--repo", required=True)
    verify_follow_up.add_argument("--head", required=True)
    verify_follow_up.add_argument("--head-repo", required=True)
    verify_follow_up.add_argument("--head-sha", required=True)
    verify_follow_up.add_argument("--actor", required=True)
    verify_follow_up.add_argument("--actor-permission", default="")
    verify_follow_up.add_argument("--changed-files", type=Path, required=True)
    verify_follow_up.add_argument("--commits", type=Path, required=True)
    verify_follow_up.add_argument("--root", type=Path, default=Path.cwd())
    return result


def release_candidate() -> ModuleType:
    """Load the CSARC release commands beside this file.

    Only `release_ownership: csarc-owned` renders
    `.csarc/scripts/release_candidate.py`; every other project keeps the
    capability `preflight` the CSARC CLI runs (#1129).
    """
    name = (
        "release_candidate"
        if __package__ in {None, ""}
        else f"{__package__}.release_candidate"
    )
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name != name:
            raise
        raise SystemExit(
            "This release command needs release_ownership: csarc-owned; "
            ".csarc/scripts/release_candidate.py is not rendered here"
        ) from error


def __getattr__(name: str) -> object:
    """Keep `release_policy.<release function>` reads working."""
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(release_candidate(), name)


def main(arguments: list[str] | None = None) -> int:
    """Run capability preflight, or one CSARC release command."""
    args = parser().parse_args(arguments)
    if args.command == "preflight":
        policies = preflight_policy_observations(args.repo)
        write_report(
            report(
                preflight_capabilities(args.repo),
                "cli-preflight",
                policies=policies,
                integrations=optional_integration_preflight(args.repo),
                # Issue #667: advisory, non-blocking repo-hygiene review
                # list -- never affects `mode`/`reason` above, and a
                # transport failure degrades to "available": False rather
                # than raising. See stale_branch_detection's module
                # docstring for what this does and does not catch.
                repo_hygiene=stale_branch_detection.stale_branch_report(
                    args.repo
                ),
            ),
            None,
            None,
        )
        return 0
    return release_candidate().dispatch(args)


if __name__ == "__main__":
    raise SystemExit(main())
