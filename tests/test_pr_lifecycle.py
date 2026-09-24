"""Tests for serialized pull-request lifecycle writes."""

from __future__ import annotations

import hashlib
import json
import re
import runpy
import shutil
import subprocess
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "pr_lifecycle.py")
)
ADMIN_BYPASS_MARKER = MODULE["ADMIN_BYPASS_MARKER"]
acquire = MODULE["acquire"]
audit_message = MODULE["audit_message"]
authorization = MODULE["authorization"]
authorization_statement = MODULE["authorization_statement"]
authorization_template = MODULE["authorization_template"]
base_lane_ref = MODULE["base_lane_ref"]
confirm_refs = MODULE["confirm_refs"]
create_refs = MODULE["create_refs"]
create_draft_pull = MODULE["create_draft_pull"]
edit_metadata = MODULE["edit_metadata"]
edit_standalone_issue = MODULE["edit_standalone_issue"]
exact_head_approval = MODULE["exact_head_approval"]
expired_remote_lease = MODULE["expired_remote_lease"]
GitHub = MODULE["GitHub"]
ensure_hotfix_post_review = MODULE["ensure_hotfix_post_review"]
hotfix_emergency_evidence = MODULE["hotfix_emergency_evidence"]
LEASE_CORE_FIELDS = MODULE["LEASE_CORE_FIELDS"]
lease_message = MODULE["lease_message"]
merge = MODULE["merge"]
merge_snapshot = MODULE["merge_snapshot"]
read_lease = MODULE["read_lease"]
require_lease = MODULE["require_lease"]
require_successful_checks = MODULE["require_successful_checks"]
require_trusted_dependabot_head = MODULE["require_trusted_dependabot_head"]
trusted_check_run_matches_context = MODULE["trusted_check_run_matches_context"]
promotion_gate = MODULE["promotion_gate"]
release_refs = MODULE["release_refs"]
revalidate_release_candidate = MODULE["revalidate_release_candidate"]
remote_repository = MODULE["remote_repository"]
scan_writers = MODULE["scan_writers"]
validate_audit_comment = MODULE["validate_audit_comment"]
writer_violations = MODULE["writer_violations"]
_GIT = shutil.which("git")
if _GIT is None:
    raise RuntimeError("Git is required for PR lifecycle tests")
GIT: str = _GIT


@pytest.fixture(autouse=True)
def human_review_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the maintainer-approval mode unless a test opts into Copilot."""
    monkeypatch.setitem(
        MODULE["merge_snapshot"].__globals__,
        "review_settings",
        lambda: ("human", "unlimited"),
    )

    def resolved_level(
        github: object, repo: str, pull: dict[str, Any]
    ) -> object:
        del github, repo
        base = str((pull.get("base") or {}).get("ref") or "")
        level = "beta" if base.startswith(("dev/m", "dev/i")) else "stable"
        self_review = ADMIN_BYPASS_MARKER in str(pull.get("body") or "")
        return MODULE["release_level"].Decision(
            level,
            "self" if self_review else "peer",
            "fast" if level == "beta" else "full",
            "test",
        )

    monkeypatch.setitem(
        MODULE["merge_snapshot"].__globals__,
        "resolve_release_level",
        resolved_level,
    )


class FakeGitHub:
    """Serve the mutable GitHub state needed by lifecycle tests."""

    def __init__(self, head: str) -> None:
        self.head = head
        self.head_ref = "hotfix/42-lifecycle"
        self.draft = False
        self.authorization_created_at = "2026-08-25T01:01:00Z"
        self.authorization_actor = "maintainer"
        self.authenticated_actor = "agent"
        self.timeline: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self.comment_snapshots: list[list[dict[str, Any]]] = []
        self.inline_comments: list[dict[str, Any]] = []
        self.inline_comment_snapshots: list[list[dict[str, Any]]] = []
        self.reviews: list[dict[str, Any]] = [
            {
                "user": {"login": "reviewer", "type": "User"},
                "author_association": "MEMBER",
                "state": "APPROVED",
                "submitted_at": "2026-08-25T01:01:00Z",
                "commit_id": self.head,
                "html_url": (
                    "https://github.com/owner/repo/pull/42#pullrequestreview-1"
                ),
            }
        ]
        self.audit_comments: list[str] = []
        self.protected = True
        self.required_review_count: object = 1
        self.additional_pull_rules: list[dict[str, object]] = []
        self.additional_check_rules: list[dict[str, object]] = []
        self.required_status_checks: list[dict[str, object]] = [
            {"context": "verify", "integration_id": 15368},
            {"context": "review", "integration_id": 15368},
        ]
        self.authorization_type = "User"
        self.authorization_body: str | None = None
        self.authorization_association = "OWNER"
        self.permission = "admin"
        self.merged = False
        self.base_ref = "main"
        self.base_sha = "b" * 40
        self.destination_sha = self.base_sha
        self.merge_parent = self.base_sha
        self.default_branch = "main"
        self.canonical_lease: dict[str, object] | None = None
        self.commit_payloads: dict[str, dict[str, Any]] = {}
        self.labels = {"bug"}
        self.milestone: str | None = None
        self.issue_state = "open"
        self.issue_milestone_number: int | None = None
        self.issue_user = "agent"
        self.issue_labels: set[str] = set()
        self.hotfix_comments: list[dict[str, Any]] = []
        self.post_review_issues: list[dict[str, Any]] = []
        self.body = "Ready for review."
        self.check_conclusion = "success"
        self.additional_check_runs: list[dict[str, Any]] = []
        self.statuses: list[dict[str, Any]] = []
        self.check_details_url = (
            "https://github.com/owner/repo/actions/runs/200/job/7"
        )
        self.verification_completed_at = datetime.now(UTC).isoformat()
        self.run_paths = {
            199: ".github/workflows/ci.yml",
            200: ".github/workflows/ci.yml",
            201: ".github/workflows/pr-review.yml",
        }
        self.run_events = {
            199: "pull_request_target",
            200: "pull_request_target",
            201: "pull_request_target",
        }
        self.run_suite_ids = {199: 9199, 200: 9200, 201: 9201}
        self.quota_note_body: str | None = None
        self.quota_runner_id = 0
        self.quota_steps: list[dict[str, Any]] = []
        self.compare_status = "ahead"
        self.ruleset_response: dict[str, object] = {
            "enforcement": "active",
            "bypass_actors": [],
        }
        self.mergeable_state = "clean"

    def viewer(self, explicit_actor: str = "") -> str:
        """Return the task's authenticated actor."""
        self.authenticated_actor = explicit_actor or self.authenticated_actor
        return self.authenticated_actor

    def pull(self, number: int = 42) -> dict[str, Any]:
        """Return one live PR fixture."""
        return {
            "number": number,
            "state": "closed" if self.merged else "open",
            "merged": self.merged,
            "merge_commit_sha": "d" * 40 if self.merged else None,
            "draft": self.draft,
            "title": "fix(ci): serialize lifecycle writes",
            "body": self.body,
            "labels": [{"name": name} for name in sorted(self.labels)],
            "milestone": (
                {"title": self.milestone}
                if self.milestone is not None
                else None
            ),
            "base": {"ref": self.base_ref, "sha": self.base_sha},
            "mergeable_state": self.mergeable_state,
            "head": {
                "ref": self.head_ref,
                "sha": self.head,
                "repo": {"full_name": "owner/repo"},
            },
        }

    def get(self, _repo: str, path: str) -> object:  # noqa: C901
        """Return one REST fixture."""
        if path in self.commit_payloads:
            return self.commit_payloads[path]
        if path == "":
            return {"default_branch": self.default_branch}
        pull_match = re.fullmatch(r"pulls/([1-9][0-9]*)", path)
        if pull_match:
            pull = self.pull()
            pull["number"] = int(pull_match.group(1))
            return pull
        if path == "git/ref/heads/main":
            return {
                "object": {
                    "sha": "d" * 40 if self.merged else self.destination_sha
                }
            }
        if path == "issues/comments/99":
            return {
                "html_url": (
                    "https://github.com/owner/repo/pull/42#issuecomment-99"
                ),
                "issue_url": "https://api.github.com/repos/owner/repo/issues/42",
                "author_association": self.authorization_association,
                "user": {
                    "login": self.authorization_actor,
                    "type": self.authorization_type,
                },
                "created_at": self.authorization_created_at,
                "body": self.authorization_body
                or authorization_statement("owner/repo", 42, self.head),
            }
        if path == "issues/comments/98" and self.quota_note_body:
            return {
                "html_url": (
                    "https://github.com/owner/repo/pull/42#issuecomment-98"
                ),
                "issue_url": "https://api.github.com/repos/owner/repo/issues/42",
                "created_at": "2026-08-25T01:00:45Z",
                "body": self.quota_note_body,
            }
        if path in {"issues/42", "issues/43"}:
            number = int(path.split("/")[1])
            return {
                "number": number,
                "pull_request": None,
                "state": self.issue_state,
                "milestone": (
                    {"number": self.issue_milestone_number}
                    if self.issue_milestone_number is not None
                    else None
                ),
                "body": "- [x] Acceptance verified",
                "labels": [
                    {"name": label} for label in sorted(self.issue_labels)
                ],
                "user": {"login": self.issue_user, "type": "User"},
            }
        run_match = re.fullmatch(r"actions/runs/(199|200|201)", path)
        if run_match:
            run_id = int(run_match.group(1))
            return {
                "id": run_id,
                "html_url": (
                    f"https://github.com/owner/repo/actions/runs/{run_id}"
                ),
                "run_attempt": 1,
                "check_suite_id": self.run_suite_ids[run_id],
                "head_sha": self.head,
                "head_branch": self.head_ref,
                "event": self.run_events[run_id],
                "status": "completed",
                "conclusion": (
                    self.check_conclusion if run_id == 200 else "failure"
                ),
                "repository": {"full_name": "owner/repo"},
                "head_repository": {"full_name": "owner/repo"},
                "pull_requests": [{"number": 42}],
                "path": self.run_paths[run_id],
            }
        jobs_match = re.fullmatch(
            r"actions/runs/(199|200)/jobs\?per_page=100&page=1", path
        )
        if jobs_match:
            run_id = int(jobs_match.group(1))
            return {
                "total_count": 1,
                "jobs": [
                    {
                        "id": 7 if run_id == 200 else 8,
                        "runner_id": self.quota_runner_id,
                        "steps": self.quota_steps,
                        "conclusion": "failure",
                    }
                ],
            }
        if re.fullmatch(
            r"check-runs/[78]/annotations\?per_page=100&page=1", path
        ):
            return [{"message": promotion_gate.BILLING_GATE_ANNOTATION_MESSAGE}]
        collaborator = re.fullmatch(r"collaborators/([^/]+)/permission", path)
        if collaborator:
            login = urllib.parse.unquote(collaborator.group(1))
            return {
                "permission": self.permission,
                "user": {"login": login},
            }
        if path == f"rules/branches/{self.base_ref.replace('/', '%2F')}":
            if not self.protected:
                raise RuntimeError("Upgrade to GitHub Pro")
            return [
                {
                    "type": "pull_request",
                    "ruleset_id": 7,
                    "parameters": {
                        "required_approving_review_count": (
                            self.required_review_count
                        ),
                        "dismiss_stale_reviews_on_push": True,
                        "require_code_owner_review": True,
                        "require_last_push_approval": True,
                        "required_review_thread_resolution": True,
                    },
                },
                *self.additional_pull_rules,
                {
                    "type": "required_status_checks",
                    "ruleset_id": 7,
                    "parameters": {
                        "required_status_checks": self.required_status_checks
                    },
                },
                *self.additional_check_rules,
            ]
        if path == "rulesets/7":
            return self.ruleset_response
        if path == (f"compare/{self.destination_sha}...{self.head}"):
            return {"status": self.compare_status}
        if path == f"git/commits/{'a' * 40}":
            return {"sha": "a" * 40, "tree": {"sha": "e" * 40}}
        if path == f"git/commits/{'c' * 40}" and self.canonical_lease:
            return {
                "sha": "c" * 40,
                "message": lease_message(self.canonical_lease),
                "parents": [{"sha": "a" * 40}],
                "tree": {"sha": "e" * 40},
            }
        if path == f"git/commits/{'d' * 40}" and self.merged:
            return {
                "sha": "d" * 40,
                "parents": [{"sha": self.merge_parent}],
            }
        if path == "issues/comments/1" and self.canonical_lease:
            actor = str(self.canonical_lease["actor"])
            return {
                "html_url": self.canonical_lease["audit_url"],
                "issue_url": "https://api.github.com/repos/owner/repo/issues/42",
                "user": {
                    "login": actor,
                    "type": "Bot" if actor.endswith("[bot]") else "User",
                },
                "body": audit_message(self.canonical_lease),
            }
        raise AssertionError(path)

    def collection(
        self,
        _repo: str,
        path: str,
        key: str,
        response_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return successful exact-head check fixtures."""
        assert response_sha in {None, self.head}
        if key == "check_runs" and path.startswith(f"commits/{self.head}/"):
            return [
                {
                    "id": 7,
                    "name": "verify",
                    "head_sha": self.head,
                    "status": "completed",
                    "conclusion": self.check_conclusion,
                    "details_url": self.check_details_url,
                    "app": {"id": 15368},
                    "check_suite": {"id": self.run_suite_ids[200]},
                },
                {
                    "id": 8,
                    "name": "review",
                    "head_sha": self.head,
                    "status": "completed",
                    "conclusion": "success",
                    "details_url": (
                        "https://github.com/owner/repo/actions/runs/201/job/8"
                    ),
                    "app": {"id": 15368},
                    "check_suite": {"id": self.run_suite_ids[201]},
                },
                *self.additional_check_runs,
            ]
        if key == "jobs" and path == (
            "actions/runs/200/jobs?filter=latest&per_page=100"
        ):
            names = [
                "Select trusted verification plan",
                "Bind trusted verification identity",
                "Set up Python 3.14",
                "Set up uv 0.12.15",
                (
                    "Execute trusted verification tier=fast scopes=source "
                    f"tree={'e' * 40} command=./scripts/verify-fast"
                ),
            ]
            return [
                {
                    "id": 7,
                    "run_id": 200,
                    "run_attempt": 1,
                    "name": "verify",
                    "head_sha": self.head,
                    "html_url": self.check_details_url,
                    "status": "completed",
                    "conclusion": self.check_conclusion,
                    "labels": ["ubuntu-latest"],
                    "runner_id": 9,
                    "runner_group_name": "GitHub Actions",
                    "completed_at": self.verification_completed_at,
                    "steps": [
                        {
                            "name": name,
                            "status": "completed",
                            "conclusion": "success",
                        }
                        for name in names
                    ],
                }
            ]
        if key == "statuses" and path.startswith(f"commits/{self.head}/"):
            return self.statuses
        raise AssertionError(path)

    def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
        """Return one paginated fixture."""
        if path.startswith("issues/42/timeline"):
            return self.timeline
        if path.startswith("issues/42/comments"):
            if self.comment_snapshots:
                return self.comment_snapshots.pop(0)
            return self.comments
        if path.startswith("issues/43/comments"):
            return self.hotfix_comments
        if path.startswith("issues?state=all&labels=needs-manual-review"):
            return self.post_review_issues
        if path.startswith("pulls/42/comments"):
            if self.inline_comment_snapshots:
                return self.inline_comment_snapshots.pop(0)
            return self.inline_comments
        if path.startswith("pulls/42/reviews"):
            return self.reviews
        raise AssertionError(path)

    def comment(self, _repo: str, number: int, body: str) -> dict[str, Any]:
        """Record a lease audit comment."""
        self.audit_comments.append(body)
        return {
            "html_url": (
                f"https://github.com/owner/repo/pull/{number}#issuecomment-1"
            ),
            "issue_url": (
                f"https://api.github.com/repos/owner/repo/issues/{number}"
            ),
            "user": {
                "login": self.authenticated_actor,
                "type": (
                    "Bot"
                    if self.authenticated_actor.endswith("[bot]")
                    else "User"
                ),
            },
            "body": body,
        }

    def create_issue(
        self,
        _repo: str,
        title: str,
        body: str,
        assignee: str,
    ) -> dict[str, Any]:
        """Record one emergency post-review task."""
        issue = {
            "html_url": "https://github.com/owner/repo/issues/99",
            "title": title,
            "body": body,
            "assignee": assignee,
        }
        self.post_review_issues.append(issue)
        return issue

    def merge(
        self, _repo: str, _number: int, head_sha: str, _title: str
    ) -> dict[str, Any]:
        """Record one synchronous exact-head merge."""
        assert head_sha == self.head
        self.merged = True
        return {"merged": True, "sha": "d" * 40}


def git(path: Path, *arguments: str) -> str:
    """Run Git in one fixture repository."""
    return subprocess.run(  # noqa: S603
        [GIT, *arguments],
        cwd=path,
        text=True,
        check=True,
        capture_output=True,
    ).stdout.strip()


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
        "git@github.com:owner/repo.git",
    ],
)
def test_origin_must_resolve_to_the_exact_github_repository(url: str) -> None:
    """Common authenticated GitHub origin forms resolve safely."""
    assert remote_repository(url) == "owner/repo"


@pytest.mark.parametrize(
    "source",
    [
        "run: |\n  gh pr \\\n    edit 42 --add-label bug\n",
        'subprocess.run(["gh", "pr", "ready", "42"])',
        'requests.request("PATCH", f"repos/{repo}/pulls/" f"{number}")',
        "gh api -X PATCH repos/owner/repo/pulls/42 --field draft=true",
        'query = "mutation { markPullRequest" "ReadyForReview(input: $x) }"',
        "gh pr create --base dev/m7-staged-ci --head fix/x --label bug",
        (
            "requests.patch("
            'f"https://api.github.com/repos/{repo}/pulls/{number}", '
            'json={"draft": True})'
        ),
        (
            "requests.post("
            '"https://api.github.com/repos/o/r/issues/42/labels", '
            'json={"labels": ["bug"]})'
        ),
        (
            "requests.delete("
            '"https://api.github.com/repos/o/r/issues/42/labels/bug")'
        ),
        "gh api --method PATCH repos/o/r/pulls/42 -f draft=true",
        "gh api --method POST repos/o/r/issues/42/labels -f labels[]=bug",
        (
            "gh api --method DELETE "
            '"repos/$GITHUB_REPOSITORY/issues/$PR_NUMBER/labels/bug"'
        ),
        "gh issue edit 42 --add-label bug",
        "gh issue edit 42 --remove-label bug",
        "gh issue edit 42 --milestone v1",
    ],
)
def test_writer_scanner_catches_split_lifecycle_mutations(source: str) -> None:
    """Whitespace and source-string concatenation cannot evade the scan."""
    assert writer_violations(source)


def test_writer_scanner_parses_multiline_subprocess_argv() -> None:
    """A Python argv list cannot hide an Issue label mutation."""
    source = """
import subprocess

subprocess.run(
    [
        "gh",
        "issue",
        "edit",
        "42",
        "--add-" "label",
        "bug",
    ],
    check=True,
)
"""
    assert "gh issue metadata write" in writer_violations(source)


def test_writer_scanner_tracks_augmented_subprocess_argv() -> None:
    """Ordered list concatenation cannot hide a lifecycle command."""
    source = """
import subprocess

command = ["gh", "issue"]
command += ["edit", "42"]
command += ["--add-" "label", "bug"]
subprocess.run(command, check=True)
"""
    assert "gh issue metadata write" in writer_violations(source)


@pytest.mark.parametrize(
    "source",
    [
        """
import requests

requests.request(
    method="PA" "TCH",
    url="https://api.github.com/repos/o/r/pulls/42",
)
""",
        """
import requests

requests.Session().delete(
    "https://api.github.com/repos/o/r/issues/42/labels/bug"
)
""",
        """
import requests

session = requests.Session()
session.delete("https://api.github.com/repos/o/r/issues/42/labels/bug")
""",
        """
import httpx

httpx.Client().post("https://api.github.com/repos/o/r/issues/42/labels")
""",
        """
import urllib.request

urllib.request.Request(
    "https://api.github.com/repos/o/r/pulls/42",
    method="PATCH",
)
""",
    ],
)
def test_writer_scanner_parses_http_client_calls(source: str) -> None:
    """Known HTTP clients cannot hide lifecycle writes behind syntax."""
    assert "Python HTTP client lifecycle mutation" in writer_violations(source)


def test_writer_scanner_fails_closed_on_an_unknown_http_method() -> None:
    """Dynamic methods cannot make lifecycle endpoints look read-only."""
    source = """
import requests

requests.request(
    method=selected_method,
    url=selected_url,
)
"""
    assert "Python HTTP method cannot be proven read-only" in writer_violations(
        source
    )


@pytest.mark.parametrize(
    "source",
    [
        """
import urllib.request

urllib.request.Request(
    "https://api.github.com/repos/o/r/pulls/42",
    method=selected_method,
)
""",
        """
import urllib.request

urllib.request.Request(selected_url, method="PATCH")
""",
        """
import urllib.request

urllib.request.urlopen(
    "https://api.github.com/repos/o/r/issues/42/labels",
    data=b"{}",
)
""",
    ],
)
def test_writer_scanner_fails_closed_on_urllib_writes(source: str) -> None:
    """Dynamic Requests and urlopen payloads cannot bypass the scan."""
    assert writer_violations(source)


@pytest.mark.parametrize("fold", [">", ">-"])
def test_writer_scanner_normalizes_folded_yaml_and_dynamic_methods(
    fold: str,
) -> None:
    """A folded workflow command cannot hide an unknown write method."""
    source = f"""
steps:
  - run: {fold}
      gh api
      --method "$HTTP_METHOD"
      "repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER"
"""
    assert "REST pull-request or issue metadata write" in writer_violations(
        source
    )


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_writer_scanner_allows_static_read_only_gh_api(method: str) -> None:
    """Explicit read-only methods remain available to automation."""
    assert not writer_violations(f"gh api --method {method} repos/o/r/pulls/42")


def test_writer_scanner_allows_proven_read_only_http_calls() -> None:
    """Known GET calls do not block ordinary API inspection."""
    source = """
import requests
import urllib.request

requests.request("GET", "https://api.github.com/repos/o/r/pulls/42")
urllib.request.Request("https://api.github.com/repos/o/r/issues/42")
"""
    assert not writer_violations(source)


def test_writer_scanner_allows_the_shipped_pr_policy_validator() -> None:
    """The real validator must never trip its own writer scan.

    scripts/validate-pr-policy's non-blocking Milestone reminder comment
    (Issue #551) once quoted a literal `gh api ... --method PATCH` /
    `gh issue edit --milestone` example as human guidance. writer_violations
    cannot distinguish that quoted example from an actual unleased write, so
    every downstream project's own scripts/verify (rendered from
    template/.csarc/scripts/verify.jinja, which runs
    `pr_lifecycle.py scan-writers`)
    failed before its configured verification hook ever ran -- this was only
    ever caught by the full-tier, real-template adoption tests. Regression
    coverage for Issue #645: scan the exact shipped files directly so a
    reintroduced literal example fails fast, without needing a real render.
    """
    root = Path(__file__).resolve().parents[1]
    relative_paths = (
        "scripts/validate-pr-policy",
        "template/.csarc/scripts/validate-pr-policy",
    )
    for relative in relative_paths:
        candidate = root / relative
        if not candidate.is_file():
            # A generated/adopted project's own copy of this paired test
            # file has no "template/" tree at all -- only the meta-repo
            # that produces generated projects does. Skip a path this
            # repository genuinely does not have instead of failing closed
            # on a layout difference the test never intended to assert on
            # (same established pattern as the dependabot-auto-merge writer
            # scan test below).
            continue
        text = candidate.read_text(encoding="utf-8")
        assert writer_violations(text) == [], relative


def test_writer_scanner_covers_root_and_template_automation(
    tmp_path: Path,
) -> None:
    """Both shipped workflow layers and automation scripts are mandatory."""
    workflow = tmp_path / "template/.github/workflows/example.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("run: gh pr ready 42\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"template/\.github/workflows"):
        scan_writers(tmp_path)


def test_writer_scanner_does_not_trust_a_nested_canonical_basename(
    tmp_path: Path,
) -> None:
    """Only the two exact canonical helper paths bypass their own scan."""
    imposter = tmp_path / "scripts/helpers/pr_lifecycle.py"
    imposter.parent.mkdir(parents=True)
    imposter.write_text(
        'requests.post("https://api.github.com/repos/o/r/issues/42")\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match=r"helpers/pr_lifecycle\.py"):
        scan_writers(tmp_path)


def test_writer_scanner_ignores_python_bytecode_cache(tmp_path: Path) -> None:
    """Generated Python bytecode must not make a local scan nondeterministic."""
    cache = tmp_path / "scripts/__pycache__/helper.pyc"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"\x8d\x00")
    scan_writers(tmp_path)


def test_writer_scanner_checks_source_inside_bytecode_cache(
    tmp_path: Path,
) -> None:
    """A cache directory name must not hide a lifecycle writer."""
    source = tmp_path / "scripts/__pycache__/evil.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        'import requests\nrequests.patch("https://api.github.com/repos/o/r/issues/42")\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match=r"__pycache__/evil\.py"):
        scan_writers(tmp_path)


def test_writer_scanner_rejects_non_utf8_automation(tmp_path: Path) -> None:
    """Unreadable automation must fail closed with its repository path."""
    binary = tmp_path / "scripts/__pycache__/evil.bin"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"\x8d\x00")
    with pytest.raises(RuntimeError, match=r"__pycache__/evil\.bin"):
        scan_writers(tmp_path)


@pytest.mark.parametrize("symlink_part", ["leaf", "ancestor"])
def test_writer_scanner_does_not_trust_symlinked_canonical_paths(
    tmp_path: Path, symlink_part: str
) -> None:
    """Every canonical helper path component must remain inside the root."""
    outside = tmp_path / "outside"
    outside.mkdir()
    rogue = outside / "pr_lifecycle.py"
    rogue.write_text(
        'requests.patch("https://api.github.com/repos/o/r/pulls/42")\n',
        encoding="utf-8",
    )
    if symlink_part == "leaf":
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "pr_lifecycle.py").symlink_to(rogue)
    else:
        (tmp_path / "scripts").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match=r"scripts/pr_lifecycle\.py"):
        scan_writers(tmp_path)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_writer_scanner_trusts_the_real_dependabot_auto_merge_workflows(
    tmp_path: Path,
) -> None:
    """The two exact dependabot-auto-merge.yml paths pass scan_writers.

    Regression test for #602: this copies the exact workflow allowlist with
    its major-update label write into a scratch root and proves it still scans.
    """
    for relative in (
        ".github/workflows/dependabot-auto-merge.yml",
        "template/.github/workflows/dependabot-auto-merge.yml",
    ):
        candidate = REPO_ROOT / relative
        if not candidate.is_file():
            # A generated/adopted project's own copy of this paired test
            # file has no "template/" tree at all -- only the meta-repo
            # that produces generated projects does. Skip a path this
            # repository genuinely does not have instead of failing
            # closed on a layout difference the test never intended to
            # assert on.
            continue
        source = candidate.read_text(encoding="utf-8")
        assert "gh pr merge --auto" not in source
        assert "--disable-auto" not in source
        assert 'gh pr edit "$PR_URL" --add-label needs-manual-review' in source
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")
    scan_writers(tmp_path)  # must not raise


@pytest.mark.parametrize(
    "workflow_body",
    [
        'run: gh pr edit "$PR_URL" --add-label needs-manual-review\n',
    ],
)
@pytest.mark.parametrize(
    "relative",
    [
        ".github/workflows/some-other-workflow.yml",
        "template/.github/workflows/some-other-workflow.yml",
    ],
)
def test_dependabot_auto_merge_exemption_is_an_exact_path_allowlist(
    tmp_path: Path, relative: str, workflow_body: str
) -> None:
    """The exemption trusts two exact paths only, not the write pattern.

    Regression test for #602: a different workflow file reusing the same
    unleased `gh pr edit --add-label` command text must
    still be caught by scan_writers, proving the #602 exemption is a
    positive list of exact paths rather than a relaxation of the pattern
    those two commands trip.
    """
    imposter = tmp_path / relative
    imposter.parent.mkdir(parents=True, exist_ok=True)
    imposter.write_text(workflow_body, encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"some-other-workflow\.yml"):
        scan_writers(tmp_path)


def test_real_release_workflow_has_no_unleased_pr_writer(
    tmp_path: Path,
) -> None:
    """The release workflow publishes only and needs no writer exemption."""
    candidate = REPO_ROOT / ".github/workflows/release.yml"
    if not candidate.is_file():
        # The template/ tree only ships release.yml.jinja (rendered to
        # release.yml in a generated/adopted project); running this paired
        # copy from inside template/tests/ against the meta-repo's own
        # template/ source tree has no literal release.yml to copy, so
        # there is nothing to prove here -- mirrors the "no template/ tree
        # at all" skip in test_writer_scanner_trusts_the_real_dependabot_
        # auto_merge_workflows above.
        return
    source = candidate.read_text(encoding="utf-8")
    assert "googleapis/release-please-action@" not in source
    destination = tmp_path / ".github/workflows/release.yml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source, encoding="utf-8")
    scan_writers(tmp_path)  # must not raise


@pytest.mark.parametrize(
    "relative",
    [
        ".github/workflows/release.yml",
        ".github/workflows/some-other-release.yml",
        "template/.github/workflows/some-other-release.yml",
    ],
)
def test_retired_release_please_action_is_rejected_everywhere(
    tmp_path: Path, relative: str
) -> None:
    """The retired post-merge PR writer has no scanner exemption."""
    imposter = tmp_path / relative
    imposter.parent.mkdir(parents=True, exist_ok=True)
    imposter.write_text(
        "uses: googleapis/release-please-action@abc123 # v5\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match=re.escape(relative)):
        scan_writers(tmp_path)


def test_writer_scanner_ignores_unrelated_comment_lines() -> None:
    """Two separate comments describing different things must not combine.

    Regression test for #643: `scripts/gh-issue-create` has a `#` comment
    mentioning `gh issue edit` (describing the workflow it improves on) and
    a separate `#` comment listing `--milestone` among passed-through
    flags. Neither line is an invocation; the old whole-file joined block
    used to fold them into a false "gh issue metadata write".
    """
    source = (
        "#!/usr/bin/env bash\n"
        "# A follow-up `gh issue edit` fixes the title post-hoc.\n"
        "# Passes through --title/-t, --milestone/-m, --label/-l.\n"
        'exec gh issue create "$@"\n'
    )
    assert not writer_violations(source)


def test_writer_scanner_ignores_escaped_backtick_documentation() -> None:
    """A human-facing message quoting example commands is not an invocation.

    Regression test for #643: `scripts/validate-pr-policy`'s Issue #551
    Milestone safeguard builds a PR-comment message that *describes*, in
    backslash-escaped (literal, non-command-substitution) Markdown code
    spans, the manual commands a maintainer should run. Neither described
    command is ever executed by the script.
    """
    source = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'reminder_body="Run \\`gh api repos/${GITHUB_REPOSITORY}/issues/'
        "${issue_number} --method PATCH -f milestone=${hint_number}\\`, "
        'not \\`gh issue edit --milestone\\`."\n'
    )
    assert not writer_violations(source)


def test_writer_scanner_still_catches_live_writes_beside_similar_text() -> None:
    """Narrowing the false positives above must not blind real detection.

    A genuine, unescaped, non-commented `gh issue edit --milestone` next to
    the same kind of prose that #643 taught the scanner to ignore must
    still fail closed.
    """
    source = (
        "# Passes through --title/-t, --milestone/-m, --label/-l.\n"
        "gh issue edit 42 --milestone v1\n"
    )
    assert "gh issue metadata write" in writer_violations(source)


def test_issue_label_helper_rejects_a_pull_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue automation cannot use its canonical helper to mutate a PR."""
    github = FakeGitHub("a" * 40)
    monkeypatch.setattr(
        github,
        "get",
        lambda _repo, _path: {
            "number": 42,
            "pull_request": {"url": "https://api.github.com/pulls/42"},
        },
    )
    monkeypatch.setitem(
        edit_standalone_issue.__globals__,
        "run",
        lambda *_args, **_kwargs: pytest.fail("unexpected issue write"),
    )
    with pytest.raises(RuntimeError, match="standalone Issue"):
        edit_standalone_issue(
            SimpleNamespace(
                repo="owner/repo",
                issue_number=42,
                add_label=["bug"],
                remove_label=[],
                add_assignee=[],
                body_file=None,
                issue_type=None,
                remove_type=False,
            ),
            github,
        )


def test_issue_helper_updates_a_standalone_issue_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Route automated Issue body changes through the guarded helper."""
    github = FakeGitHub("a" * 40)
    monkeypatch.setattr(
        github,
        "get",
        lambda _repo, _path: {"number": 42},
    )
    body_file = tmp_path / "issue.md"
    body_file.write_text("Updated body\n", encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setitem(
        edit_standalone_issue.__globals__,
        "run",
        lambda command, **_kwargs: calls.append(command) or "",
    )

    edit_standalone_issue(
        SimpleNamespace(
            repo="owner/repo",
            issue_number=42,
            add_label=[],
            remove_label=[],
            add_assignee=[],
            body_file=body_file,
            issue_type=None,
            remove_type=False,
        ),
        github,
    )

    assert calls == [
        [
            "gh",
            "issue",
            "edit",
            "42",
            "--repo",
            "owner/repo",
            "--body-file",
            str(body_file),
        ]
    ]


def test_writer_scanner_requires_the_managed_pr_creation_path() -> None:
    """Agents cannot bypass the canonical direct-to-Draft creator."""
    assert "direct gh pr creation" in writer_violations(
        "gh pr create --base dev/m7-staged-ci --head fix/x "
        "--title fix --body body"
    )


def test_managed_pr_creation_starts_draft_and_checks_remote_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Create one clean pushed PR without a Ready-to-Draft transition."""
    head_sha = "a" * 40
    github = FakeGitHub(head_sha)
    github.head_ref = "ci/926-reduce-hosted-automation"
    github.body = "Closes #926\n"
    github.draft = True
    body_path = tmp_path / "body.md"
    body_path.write_text(github.body, encoding="utf-8")
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(
        command: list[str], *, input_text: str | None = None, **_kwargs: object
    ) -> str:
        calls.append((command, input_text))
        if command[:3] == ["git", "branch", "--show-current"]:
            return github.head_ref
        if command[:3] == ["git", "status", "--porcelain"]:
            return ""
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return head_sha
        if command[:3] == ["gh", "pr", "create"]:
            return "https://github.com/owner/repo/pull/42"
        return ""

    monkeypatch.setitem(
        create_draft_pull.__globals__, "require_origin", lambda *_: None
    )
    monkeypatch.setitem(
        create_draft_pull.__globals__,
        "branch_sha",
        lambda _github, _repo, branch: (
            head_sha if branch == github.head_ref else github.base_sha
        ),
    )
    monkeypatch.setitem(create_draft_pull.__globals__, "run", fake_run)

    create_draft_pull(
        SimpleNamespace(
            repo="owner/repo",
            base="main",
            head=github.head_ref,
            title="fix(ci): serialize lifecycle writes",
            body_file=body_path,
        ),
        github,
    )

    create_call = next(
        call for call in calls if call[0][:3] == ["gh", "pr", "create"]
    )
    assert "--draft" in create_call[0]
    assert create_call[1] == github.body


def test_github_app_actor_must_come_from_trusted_caller_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installation token never guesses identity from an invalid endpoint."""

    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> str:
        calls.append(command)
        raise RuntimeError("Resource not accessible by integration")

    monkeypatch.setitem(GitHub.viewer.__globals__, "run", fake_run)
    assert GitHub().viewer("csarc-version-bot[bot]") == (
        "csarc-version-bot[bot]"
    )
    with pytest.raises(RuntimeError, match="must pass --actor"):
        GitHub().viewer()
    assert calls == [["gh", "api", "user"]]


def test_github_get_repository_omits_trailing_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use GitHub's canonical repository endpoint for root metadata."""
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> str:
        calls.append(command)
        return '{"default_branch": "main"}'

    monkeypatch.setitem(GitHub.get.__globals__, "run", fake_run)
    assert GitHub().get("owner/repo", "") == {"default_branch": "main"}
    assert calls == [["gh", "api", "repos/owner/repo"]]


def test_concurrent_prs_cannot_acquire_the_same_destination_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Different PRs targeting one base cannot race their merge writes."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "init", str(work))
    git(work, "config", "user.name", "Lease Test")
    git(work, "config", "user.email", "lease@example.invalid")
    (work / "README.md").write_text("fixture\n", encoding="utf-8")
    git(work, "add", "README.md")
    git(work, "commit", "-m", "test: create fixture")
    head = git(work, "rev-parse", "HEAD")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "origin", f"{head}:refs/heads/main")
    monkeypatch.chdir(work)
    monkeypatch.setitem(
        acquire.__globals__, "remote_repository", lambda _url: "owner/repo"
    )
    github = FakeGitHub(head)
    first = SimpleNamespace(
        repo="owner/repo",
        pr_number=42,
        head_sha=head,
        owner="task/merge",
        ttl_seconds=600,
        output=tmp_path / "first.json",
    )
    second = SimpleNamespace(
        **{
            **vars(first),
            "pr_number": 43,
            "owner": "task/draft",
            "output": tmp_path / "second.json",
        }
    )
    barrier = Barrier(2)
    original_create = create_refs

    def simultaneous_create(
        commit: str, refs: list[str], expected: dict[str, str | None]
    ) -> None:
        barrier.wait(timeout=5)
        original_create(commit, refs, expected)

    monkeypatch.setitem(acquire.__globals__, "create_refs", simultaneous_create)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(acquire, arguments, github)
            for arguments in (first, second)
        ]
    errors = [future.exception() for future in futures]
    assert sum(error is None for error in errors) == 1
    assert sum(isinstance(error, RuntimeError) for error in errors) == 1
    outputs = [path for path in (first.output, second.output) if path.exists()]
    assert len(outputs) == 1
    lease = read_lease(outputs[0])
    assert len(lease["refs"]) == 2
    assert base_lane_ref("main") in lease["refs"]
    assert github.audit_comments
    commit_message = git(
        work, "show", "-s", "--format=%B", lease["lease_commit"]
    )
    assert lease["capability"] not in commit_message
    assert lease["capability"] not in github.audit_comments[0]
    release_refs(lease)


def lease_fixture() -> dict[str, object]:
    """Return an unexpired in-memory lease."""
    acquired = datetime(2026, 8, 25, 1, 0, tzinfo=UTC)
    return {
        "schema_version": 2,
        "repository": "owner/repo",
        "pull_request": 42,
        "head_sha": "a" * 40,
        "head_tree": "e" * 40,
        "base_ref": "main",
        "base_sha": "b" * 40,
        "default_branch": "main",
        "owner": "task/merge",
        "actor": "agent",
        "capability": "f" * 64,
        "capability_digest": hashlib.sha256(("f" * 64).encode()).hexdigest(),
        "acquired_at": acquired.isoformat().replace("+00:00", "Z"),
        "expires_at": (datetime.now(UTC) + timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z"),
        "lease_commit": "c" * 40,
        "refs": [
            "refs/heads/csarc/leases/pr-42",
            base_lane_ref("main"),
        ],
        "reclaimed_commits": [],
        "audit_url": "https://github.com/owner/repo/pull/42#issuecomment-1",
    }


def test_merge_confirmation_cas_covers_pr_and_destination_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final merge window fences both exact remote lease refs."""
    commands: list[list[str]] = []

    def record_run(command: list[str], **_kwargs: object) -> str:
        commands.append(command)
        return ""

    monkeypatch.setitem(
        confirm_refs.__globals__,
        "run",
        record_run,
    )
    lease = lease_fixture()
    confirm_refs(lease)
    command = commands[0]
    refs = lease["refs"]
    assert isinstance(refs, list)
    for ref in refs:
        assert f"--force-with-lease={ref}:{lease['lease_commit']}" in command
        assert f"{lease['lease_commit']}:{ref}" in command


def bind_remote_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make remote ref checks observe the fixture lease."""
    monkeypatch.setitem(
        merge_snapshot.__globals__, "require_lease", lambda *_: None
    )
    monkeypatch.setitem(
        merge.__globals__, "revalidate_release_candidate", lambda *_: ""
    )


def bind_canonical_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make remote refs point to the canonical fixture commit."""
    monkeypatch.setitem(
        require_lease.__globals__, "require_origin", lambda _repo: None
    )
    monkeypatch.setitem(
        require_lease.__globals__, "remote_ref", lambda _ref: "c" * 40
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("owner", "task/attacker"),
        ("expires_at", "2099-01-01T00:00:00Z"),
    ],
)
def test_lease_evidence_must_match_the_remote_commit(
    field: str, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Editing owner or expiry cannot forge remote lease ownership."""
    bind_canonical_remote(monkeypatch)
    canonical = lease_fixture()
    github = FakeGitHub("a" * 40)
    github.canonical_lease = canonical
    tampered = {**canonical, field: value}
    with pytest.raises(RuntimeError, match="canonical evidence"):
        require_lease(github, tampered, "owner/repo", 42, "a" * 40)


@pytest.mark.parametrize("part", ["parent", "tree"])
def test_remote_lease_must_reuse_the_exact_head_commit(
    part: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A same-message commit cannot substitute another parent or tree."""
    bind_canonical_remote(monkeypatch)
    canonical = lease_fixture()
    github = FakeGitHub("a" * 40)
    github.canonical_lease = canonical
    original_get = github.get

    def tampered_get(repo: str, path: str) -> object:
        payload = original_get(repo, path)
        if path == f"git/commits/{'c' * 40}" and isinstance(payload, dict):
            payload = dict(payload)
            if part == "parent":
                payload["parents"] = [{"sha": "9" * 40}]
            else:
                payload["tree"] = {"sha": "9" * 40}
        return payload

    github.get = tampered_get  # ty: ignore[invalid-assignment]
    with pytest.raises(RuntimeError, match="canonical evidence"):
        require_lease(github, canonical, "owner/repo", 42, "a" * 40)


def test_retargeting_requires_the_destination_lane_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A base retarget cannot change the lane covered by an active lease."""
    bind_canonical_remote(monkeypatch)
    canonical = lease_fixture()
    canonical["base_ref"] = "dev/m7-staged-ci"
    canonical["refs"] = ["refs/heads/csarc/leases/pr-42"]
    github = FakeGitHub("a" * 40)
    github.canonical_lease = canonical
    with pytest.raises(RuntimeError, match="Lease refs are invalid"):
        require_lease(github, canonical, "owner/repo", 42, "a" * 40)


def test_destination_branch_advance_invalidates_the_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live destination ref must remain at the lease's exact base SHA."""
    bind_canonical_remote(monkeypatch)
    canonical = lease_fixture()
    github = FakeGitHub("a" * 40)
    github.canonical_lease = canonical
    github.destination_sha = "9" * 40
    with pytest.raises(RuntimeError, match="destination branch advanced"):
        require_lease(github, canonical, "owner/repo", 42, "a" * 40)


def test_only_a_canonical_expired_remote_lease_can_be_reclaimed() -> None:
    """Expiry alone cannot authorize replacing an arbitrary remote commit."""
    expired = lease_fixture()
    expired["acquired_at"] = "2019-12-31T23:55:00Z"
    expired["expires_at"] = "2020-01-01T00:00:00Z"
    core = {field: expired[field] for field in LEASE_CORE_FIELDS}
    github = FakeGitHub("a" * 40)
    github.commit_payloads[f"git/commits/{'c' * 40}"] = {
        "sha": "c" * 40,
        "message": lease_message(core),
        "parents": [{"sha": "a" * 40}],
        "tree": {"sha": "e" * 40},
    }
    assert (
        expired_remote_lease(
            github,
            "owner/repo",
            "c" * 40,
            "refs/heads/csarc/leases/pr-42",
        )["expires_at"]
        == "2020-01-01T00:00:00Z"
    )
    github.commit_payloads[f"git/commits/{'c' * 40}"]["tree"] = {
        "sha": "9" * 40
    }
    with pytest.raises(RuntimeError, match="parent or tree"):
        expired_remote_lease(
            github,
            "owner/repo",
            "c" * 40,
            "refs/heads/csarc/leases/pr-42",
        )


def test_capability_and_audit_url_cannot_be_forged(tmp_path: Path) -> None:
    """Local evidence must hold the capability and exact PR audit URL."""
    for field, value in (
        ("capability", "0" * 64),
        (
            "audit_url",
            "https://github.com/other/repo/pull/42#issuecomment-1",
        ),
    ):
        payload = lease_fixture()
        payload[field] = value
        path = tmp_path / f"{field}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(RuntimeError):
            read_lease(path)


def test_remote_audit_comment_is_refetched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deleting or editing the public audit record invalidates the lease."""
    bind_canonical_remote(monkeypatch)
    canonical = lease_fixture()
    github = FakeGitHub("a" * 40)
    github.canonical_lease = canonical
    original_get = github.get

    def edited_comment(repo: str, path: str) -> object:
        payload = original_get(repo, path)
        if path == "issues/comments/1" and isinstance(payload, dict):
            return {**payload, "body": "edited"}
        return payload

    github.get = edited_comment  # ty: ignore[invalid-assignment]
    with pytest.raises(RuntimeError, match="audit comment"):
        require_lease(github, canonical, "owner/repo", 42, "a" * 40)


def test_audit_response_must_match_the_declared_actor() -> None:
    """An explicit App actor is accepted only when GitHub reports that actor."""
    lease = lease_fixture()
    lease["actor"] = "trusted-app[bot]"
    comment = {
        "html_url": lease["audit_url"],
        "issue_url": "https://api.github.com/repos/owner/repo/issues/42",
        "user": {"login": "other-app[bot]", "type": "Bot"},
        "body": audit_message(lease),
    }
    with pytest.raises(RuntimeError, match="audit comment"):
        validate_audit_comment(lease, comment)


def test_audit_response_must_match_the_declared_actor_type() -> None:
    """A human response cannot impersonate the declared GitHub App actor."""
    lease = lease_fixture()
    lease["actor"] = "trusted-app[bot]"
    comment = {
        "html_url": lease["audit_url"],
        "issue_url": "https://api.github.com/repos/owner/repo/issues/42",
        "user": {"login": "trusted-app[bot]", "type": "User"},
        "body": audit_message(lease),
    }
    with pytest.raises(RuntimeError, match="audit comment"):
        validate_audit_comment(lease, comment)


@pytest.mark.parametrize(
    ("actor_type", "body"),
    [
        ("Bot", None),
        ("User", "Authorization revoked"),
    ],
)
def test_authorization_requires_an_exact_affirmative_human_statement(
    actor_type: str, body: str | None
) -> None:
    """Bot identities and non-affirmative text cannot authorize a merge."""
    github = FakeGitHub("a" * 40)
    github.authorization_type = actor_type
    github.authorization_body = body
    with pytest.raises(RuntimeError, match="exact maintainer statement"):
        authorization(
            github,
            "owner/repo",
            42,
            "a" * 40,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_authorization_accepts_a_web_ui_crlf_body() -> None:
    """Issue #991: a template pasted through the web UI still authorizes."""
    github = FakeGitHub("a" * 40)
    github.authorization_body = (
        authorization_statement("owner/repo", 42, "a" * 40).replace(
            "\n", "\r\n"
        )
        + "\n"
    )
    payload = authorization(
        github,
        "owner/repo",
        42,
        "a" * 40,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert payload["body"] == github.authorization_body


def test_authorization_rejects_a_crlf_body_for_another_head() -> None:
    """Issue #991: line-ending tolerance never relaxes the head binding."""
    github = FakeGitHub("a" * 40)
    github.authorization_body = authorization_statement(
        "owner/repo", 42, "b" * 40
    ).replace("\n", "\r\n")
    with pytest.raises(RuntimeError, match="exact maintainer statement"):
        authorization(
            github,
            "owner/repo",
            42,
            "a" * 40,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_authorization_template_outputs_the_exact_accepted_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Piping the generated template must not add an invalid trailing byte."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    monkeypatch.setitem(
        authorization_template.__globals__, "require_caller", lambda *_: None
    )
    monkeypatch.setitem(
        authorization_template.__globals__, "require_lease", lambda *_: None
    )
    authorization_template(
        SimpleNamespace(
            repo="owner/repo",
            pr_number=42,
            head_sha="a" * 40,
            owner="task/merge",
            actor="",
            lease=lease_path,
        ),
        FakeGitHub("a" * 40),
    )
    assert capsys.readouterr().out == authorization_statement(
        "owner/repo", 42, "a" * 40
    )


def test_authorization_requires_live_maintainer_permission() -> None:
    """A stale MEMBER association cannot replace live repository permission."""
    github = FakeGitHub("a" * 40)
    github.permission = "read"
    with pytest.raises(RuntimeError, match="lacks maintainer permission"):
        authorization(
            github,
            "owner/repo",
            42,
            "a" * 40,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_authorization_ignores_author_association() -> None:
    """Issue #785: a downgraded association must not block a real maintainer.

    A restricted `GITHUB_TOKEN` reports a genuine org member's comment as
    `COLLABORATOR` instead of `MEMBER` (confirmed live on PR #782, see also
    #549's identical finding for `sync_milestone_state.py`). The live
    `collaborators/{login}/permission` lookup is the only source of truth.
    """
    github = FakeGitHub("a" * 40)
    github.authorization_association = "COLLABORATOR"
    payload = authorization(
        github,
        "owner/repo",
        42,
        "a" * 40,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert payload["author_association"] == "COLLABORATOR"


def test_keyed_github_collections_flatten_every_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Required-check discovery cannot silently ignore later pages."""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> str:
        commands.append(command)
        return json.dumps(
            [
                {"check_runs": [{"name": "first"}]},
                {"check_runs": [{"name": "second"}]},
            ]
        )

    monkeypatch.setitem(GitHub.collection.__globals__, "run", fake_run)
    assert [
        item["name"]
        for item in GitHub().collection(
            "owner/repo", "commits/abc/check-runs?per_page=100", "check_runs"
        )
    ] == ["first", "second"]
    assert "--paginate" in commands[0]


def test_required_check_must_succeed_on_the_exact_head() -> None:
    """A successful check attached to another SHA cannot satisfy protection."""
    github = FakeGitHub("a" * 40)

    def stale_collection(
        _repo: str,
        _path: str,
        key: str,
        _response_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        if key == "check_runs":
            return [
                {
                    "name": "verify",
                    "head_sha": "f" * 40,
                    "status": "completed",
                    "conclusion": "success",
                }
            ]
        return []

    github.collection = stale_collection  # ty: ignore[invalid-assignment]
    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", "a" * 40, {("verify", 15368)}
        )


def test_required_check_accepts_the_exact_github_app() -> None:
    """The expected App may satisfy its exact-name check on the exact head."""
    github = FakeGitHub("a" * 40)

    assert (
        require_successful_checks(
            github, "owner/repo", github.head, {("verify", 15368)}
        )
        == "success"
    )


def test_forged_commit_trailer_cannot_replace_hosted_execution() -> None:
    """Contributor-written commit text is not trusted verification input."""
    github = FakeGitHub("a" * 40)
    github.commit_payloads[f"git/commits/{github.head}"] = {
        "sha": github.head,
        "tree": {"sha": "e" * 40},
        "message": (
            "change\n\nVerified-locally: sha256="
            f"{'e' * 40} tier=full at=2099-01-01T00:00:00Z"
        ),
    }

    def no_checks(
        _repo: str,
        path: str,
        key: str,
        response_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        assert response_sha in {None, github.head}
        if key in {"check_runs", "statuses"}:
            return []
        raise AssertionError((path, key))

    github.collection = no_checks  # ty: ignore[invalid-assignment]
    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", github.head, {("verify", 15368)}
        )


@pytest.mark.parametrize("conclusion", ["neutral", "skipped"])
def test_verify_requires_an_actual_success(conclusion: str) -> None:
    """A trusted verify run must execute and succeed, not merely terminate."""
    github = FakeGitHub("a" * 40)
    github.check_conclusion = conclusion
    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", github.head, {("verify", 15368)}
        )


def test_newer_pending_verify_blocks_stale_success_on_same_head() -> None:
    """A base-edit rerun must supersede earlier lower-tier evidence."""
    github = FakeGitHub("a" * 40)
    github.run_paths[201] = ".github/workflows/ci.yml"
    github.additional_check_runs = [
        {
            "id": 8,
            "name": "verify",
            "head_sha": github.head,
            "status": "queued",
            "conclusion": None,
            "details_url": (
                "https://github.com/owner/repo/actions/runs/201/job/8"
            ),
            "app": {"id": 15368},
            "check_suite": {"id": github.run_suite_ids[201]},
        }
    ]
    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", github.head, {("verify", 15368)}
        )


def test_quota_cannot_replace_trusted_verify_execution() -> None:
    """Zero-step billing evidence cannot substitute for test execution."""
    github = FakeGitHub("a" * 40)
    github.check_conclusion = "failure"
    with pytest.raises(RuntimeError, match="cannot replace trusted verify"):
        require_successful_checks(
            github,
            "owner/repo",
            github.head,
            {("verify", 15368)},
            {"https://github.com/owner/repo/actions/runs/200"},
        )


@pytest.mark.parametrize(
    ("context", "path", "event"),
    [
        ("title", ".github/workflows/pr-policy.yml", "pull_request_target"),
        ("verify", ".github/workflows/ci.yml", "pull_request_target"),
        (
            "review",
            ".github/workflows/pr-review.yml",
            "pull_request_review",
        ),
    ],
)
def test_required_contexts_pin_their_trusted_workflow(
    context: str, path: str, event: str
) -> None:
    """Each template-owned context has one exact trusted producer route."""
    github = FakeGitHub("a" * 40)
    github.run_paths[200] = path
    github.run_events[200] = event
    item = github.collection(
        "owner/repo",
        f"commits/{github.head}/check-runs?filter=latest&per_page=100",
        "check_runs",
    )[0]
    item["name"] = context

    assert trusted_check_run_matches_context(
        github,
        "owner/repo",
        github.head,
        item,
        context,
        15368,
        {},
    )


def test_published_review_check_binds_to_its_trusted_workflow_run() -> None:
    """A three-state review check may use a separate GitHub check suite."""
    github = FakeGitHub("a" * 40)
    github.run_paths[201] = ".github/workflows/pr-review.yml"
    github.run_events[201] = "pull_request_target"
    item = {
        "id": 9,
        "name": "review",
        "head_sha": github.head,
        "status": "in_progress",
        "conclusion": None,
        "details_url": "https://github.com/owner/repo/actions/runs/201",
        "external_id": f"csarc-review:201:{github.head}",
        "app": {"id": 15368},
        "check_suite": {"id": 9999},
    }

    assert trusted_check_run_matches_context(
        github,
        "owner/repo",
        github.head,
        item,
        "review",
        15368,
        {},
    )

    item["external_id"] = f"csarc-review:200:{github.head}"
    assert not trusted_check_run_matches_context(
        github,
        "owner/repo",
        github.head,
        item,
        "review",
        15368,
        {},
    )

    item["external_id"] = f"csarc-review:201:{github.head}"
    item["check_suite"] = None
    assert not trusted_check_run_matches_context(
        github,
        "owner/repo",
        github.head,
        item,
        "review",
        15368,
        {},
    )


class DependabotGitHub(FakeGitHub):
    """Serve exact Dependabot provenance plus one trusted eligibility run."""

    def __init__(self) -> None:
        super().__init__("a" * 40)
        self.head_ref = "dependabot/uv/copier-9.18.2"
        self.run_paths[201] = ".github/workflows/dependabot-auto-merge.yml"
        self.run_events[201] = "pull_request_target"
        self.additional_check_runs = [
            {
                "id": 8,
                "name": "dependabot-merge-eligible",
                "head_sha": self.head,
                "status": "completed",
                "conclusion": "success",
                "details_url": (
                    "https://github.com/owner/repo/actions/runs/201/job/8"
                ),
                "app": {"id": 15368},
                "check_suite": {"id": self.run_suite_ids[201]},
            }
        ]
        self.dependabot_author = "dependabot[bot]"

    def pull(self, number: int = 42) -> dict[str, Any]:
        pull = super().pull(number)
        pull["user"] = {"login": "dependabot[bot]", "type": "Bot"}
        pull["base"]["repo"] = {"full_name": "owner/repo"}
        return pull

    def get(self, _repo: str, path: str) -> object:
        if path == f"commits/{self.head}":
            return {
                "sha": self.head,
                "author": {
                    "login": self.dependabot_author,
                    "type": (
                        "Bot"
                        if self.dependabot_author == "dependabot[bot]"
                        else "User"
                    ),
                },
                "committer": {"login": "web-flow"},
                "commit": {
                    "verification": {"verified": True, "reason": "valid"}
                },
                "parents": [{"sha": self.base_sha}],
            }
        if path == f"compare/{self.base_sha}...{self.head}":
            return {
                "ahead_by": 1,
                "files": [{"filename": "uv.lock", "status": "modified"}],
            }
        if path == f"commits/{self.base_sha}":
            return {}
        if path == f"compare/{self.base_sha}...{self.base_sha}":
            return {}
        return super().get(_repo, path)


class DependabotSyncChildGitHub(DependabotGitHub):
    """Serve the deterministic unsigned child of one signed Actions bump."""

    def __init__(self) -> None:
        super().__init__()
        self.head = "c" * 40
        self.head_ref = "dependabot/github_actions/main/actions-checkout-7"
        self.additional_check_runs[0]["head_sha"] = self.head

    def get(self, _repo: str, path: str) -> object:
        if path == f"commits/{self.head}":
            identity = {
                "name": "github-actions[bot]",
                "email": "actions@github.com",
            }
            return {
                "sha": self.head,
                "author": {"login": "github-actions[bot]", "type": "Bot"},
                "committer": {
                    "login": "github-actions[bot]",
                    "type": "Bot",
                },
                "commit": {
                    "message": (
                        "fix(deps): sync template copies of this dependency "
                        "bump (#755)"
                    ),
                    "author": identity,
                    "committer": identity,
                    "verification": {"verified": False, "reason": "unsigned"},
                },
                "parents": [{"sha": "a" * 40}],
            }
        if path == f"commits/{'a' * 40}":
            return {
                "sha": "a" * 40,
                "author": {"login": "dependabot[bot]", "type": "Bot"},
                "committer": {"login": "web-flow"},
                "commit": {
                    "verification": {"verified": True, "reason": "valid"}
                },
                "parents": [{"sha": self.base_sha}],
            }
        if path == f"compare/{self.base_sha}...{'a' * 40}":
            return {
                "ahead_by": 1,
                "files": [
                    {
                        "filename": ".github/workflows/ci.yml",
                        "status": "modified",
                    }
                ],
            }
        if path == f"compare/{self.base_sha}...{self.head}":
            return {"ahead_by": 2, "files": []}
        return super().get(_repo, path)


def test_dependabot_merge_reauthenticates_head_and_trusted_eligibility() -> (
    None
):
    """The merge boundary accepts only an exact trusted eligibility run."""
    github = DependabotGitHub()

    assert (
        require_trusted_dependabot_head(
            github, "owner/repo", github.pull(), github.head, github.base_sha
        )
        == "direct"
    )


def test_dependabot_merge_accepts_a_reconstructed_sync_child() -> None:
    """The unsigned child is bound to its signed parent and trusted check."""
    github = DependabotSyncChildGitHub()

    assert (
        require_trusted_dependabot_head(
            github, "owner/repo", github.pull(), github.head, github.base_sha
        )
        == "sync-child"
    )


def test_dependabot_merge_rejects_a_human_replacement_head() -> None:
    """A bot-opened PR cannot carry a human-authored current head to merge."""
    github = DependabotGitHub()
    github.dependabot_author = "contributor"

    with pytest.raises(RuntimeError, match="not authenticated"):
        require_trusted_dependabot_head(
            github, "owner/repo", github.pull(), github.head, github.base_sha
        )


def test_dependabot_merge_rejects_a_same_name_untrusted_check() -> None:
    """The shared Actions App cannot move eligibility to another workflow."""
    github = DependabotGitHub()
    github.run_paths[201] = ".github/workflows/attacker.yml"

    with pytest.raises(RuntimeError, match="no trusted merge eligibility"):
        require_trusted_dependabot_head(
            github, "owner/repo", github.pull(), github.head, github.base_sha
        )


def test_dependabot_merge_rejects_the_wrong_github_app() -> None:
    """A same-name eligibility check from another App is not authorization."""
    github = DependabotGitHub()
    github.additional_check_runs[0]["app"] = {"id": 1234}

    with pytest.raises(RuntimeError, match="no trusted merge eligibility"):
        require_trusted_dependabot_head(
            github, "owner/repo", github.pull(), github.head, github.base_sha
        )


def test_required_check_must_match_its_pinned_github_app() -> None:
    """A same-name check from another integration cannot satisfy protection."""
    github = FakeGitHub("a" * 40)
    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", "a" * 40, {("verify", 1234)}
        )


def test_pr_controlled_actions_workflow_cannot_satisfy_required_check() -> None:
    """The shared Actions App does not make a PR-controlled run trusted."""
    github = FakeGitHub("a" * 40)
    github.check_conclusion = "failure"
    github.run_paths[201] = ".github/workflows/attacker.yml"
    github.run_events[201] = "pull_request"
    github.additional_check_runs = [
        {
            "id": 201,
            "name": "verify",
            "head_sha": github.head,
            "status": "completed",
            "conclusion": "success",
            "details_url": (
                "https://github.com/owner/repo/actions/runs/201/job/8"
            ),
            "app": {"id": 15368},
            "check_suite": {"id": github.run_suite_ids[201]},
        }
    ]

    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", github.head, {("verify", 15368)}
        )


@pytest.mark.parametrize(
    ("path", "event"),
    [
        (".github/workflows/attacker.yml", "pull_request_target"),
        (".github/workflows/ci.yml", "pull_request"),
    ],
)
def test_required_check_rejects_wrong_workflow_provenance(
    path: str, event: str
) -> None:
    """Both workflow path and base-trusted event must match the policy."""
    github = FakeGitHub("a" * 40)
    github.run_paths[200] = path
    github.run_events[200] = event

    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", github.head, {("verify", 15368)}
        )


def test_required_check_rejects_borrowed_trusted_run_url() -> None:
    """A check cannot splice its result onto another run's provenance."""
    github = FakeGitHub("a" * 40)
    github.check_conclusion = "failure"
    github.additional_check_runs = [
        {
            "id": 201,
            "name": "verify",
            "head_sha": github.head,
            "status": "completed",
            "conclusion": "success",
            "details_url": github.check_details_url,
            "app": {"id": 15368},
            "check_suite": {"id": github.run_suite_ids[201]},
        }
    ]

    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", github.head, {("verify", 15368)}
        )


def test_classic_status_cannot_satisfy_a_required_check() -> None:
    """A same-name classic success status is not trusted check evidence."""
    github = FakeGitHub("a" * 40)

    def classic_status_only(
        _repo: str,
        _path: str,
        key: str,
        _response_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        if key == "check_runs":
            return []
        if key == "statuses":
            return [{"context": "verify", "state": "success"}]
        raise AssertionError(key)

    github.collection = classic_status_only  # ty: ignore[invalid-assignment]
    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", github.head, {("verify", 15368)}
        )


@pytest.mark.parametrize("app_id", [True, 1.0, "1", 0, -1, None])
def test_pinned_check_rejects_malformed_github_app_id(app_id: object) -> None:
    """Only an exact positive integer App ID satisfies a pinned context."""
    github = FakeGitHub("a" * 40)

    def malformed_collection(
        _repo: str,
        path: str,
        key: str,
        _response_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        if key == "check_runs" and path.startswith(f"commits/{github.head}/"):
            return [
                {
                    "name": "verify",
                    "head_sha": github.head,
                    "status": "completed",
                    "conclusion": "success",
                    "app": {"id": app_id},
                }
            ]
        if key == "statuses":
            return []
        raise AssertionError(path)

    github.collection = malformed_collection  # ty: ignore[invalid-assignment]
    with pytest.raises(RuntimeError, match="Check run identity is malformed"):
        require_successful_checks(
            github, "owner/repo", github.head, {("verify", 1)}
        )


@pytest.mark.parametrize("app_id", [True, 1.0, "1", 0, -1, None])
def test_quota_fallback_rejects_malformed_github_app_id(
    app_id: object,
) -> None:
    """Quota evidence cannot satisfy a differently pinned App context."""
    github = FakeGitHub("a" * 40)
    github.check_conclusion = "failure"
    github.additional_check_runs = []

    def malformed_collection(
        _repo: str,
        path: str,
        key: str,
        _response_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        if key == "check_runs" and path.startswith(f"commits/{github.head}/"):
            return [
                {
                    "name": "verify",
                    "head_sha": github.head,
                    "status": "completed",
                    "conclusion": "failure",
                    "details_url": github.check_details_url,
                    "app": {"id": app_id},
                }
            ]
        if key == "statuses":
            return []
        raise AssertionError(path)

    github.collection = malformed_collection  # ty: ignore[invalid-assignment]
    with pytest.raises(RuntimeError, match="Check run identity is malformed"):
        require_successful_checks(
            github,
            "owner/repo",
            github.head,
            {("verify", 1)},
            {"https://github.com/owner/repo/actions/runs/200"},
        )


def test_236_newer_draft_event_invalidates_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Ready state cannot hide a concurrent post-authorization Draft event."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.timeline = [
        {"event": "convert_to_draft", "created_at": "2026-08-25T01:02:00Z"},
        {"event": "ready_for_review", "created_at": "2026-08-25T01:03:00Z"},
    ]
    with pytest.raises(RuntimeError, match="newer Draft event"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_237_unresolved_blocker_survives_ready_and_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later Ready or authorization does not erase a blocking comment."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.authorization_created_at = "2026-08-25T01:03:00Z"
    github.comments = [
        {
            "created_at": "2026-08-25T01:02:00Z",
            "body": (
                "Blocked: keep this PR Draft until the regression is fixed."
            ),
            "html_url": "https://github.com/owner/repo/pull/42#issuecomment-98",
            "author_association": "MEMBER",
        }
    ]
    github.timeline = [
        {"event": "ready_for_review", "created_at": "2026-08-25T01:04:00Z"}
    ]
    with pytest.raises(RuntimeError, match="unresolved blocking comment"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


@pytest.mark.parametrize("source", ["inline", "review"])
def test_inline_and_commented_review_blockers_are_enforced(
    source: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every paginated review discussion surface participates in the gate."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    blocker = {
        "created_at": "2026-08-25T01:02:00Z",
        "submitted_at": "2026-08-25T01:02:00Z",
        "body": "[P1] The reviewed implementation is still unsafe.",
        "html_url": "https://github.com/owner/repo/pull/42#discussion_r1",
        "author_association": "MEMBER",
        "state": "COMMENTED",
        "user": {"login": "maintainer"},
    }
    if source == "inline":
        github.inline_comments = [blocker]
    else:
        github.reviews.append(blocker)
    with pytest.raises(RuntimeError, match="unresolved blocking comment"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_merge_snapshot_allows_agent_only_with_enforced_no_bypass_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exact-head approval needs no separate authorization comment."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    snapshot = merge_snapshot(github, lease_fixture())
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["authorization_source"] == "review"
    assert snapshot["authorization_actor"] == "reviewer"
    github.protected = False
    snapshot = merge_snapshot(github, lease_fixture())
    assert snapshot["merge_mode"] == "human-only"


def test_local_mode_uses_exact_local_evidence_without_hosted_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lifecycle reuses local policy and suite evidence on one head."""
    bind_remote_lease(monkeypatch)
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "configured_verification_mode",
        lambda: "local",
    )
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "require_local_pull_policy",
        lambda *_: None,
    )
    evidence = {
        "trust": "self-attested-local",
        "tree_sha": "e" * 40,
        "tier": "fast",
        "scopes": ["source"],
    }
    monkeypatch.setattr(
        MODULE["local_verification"],
        "require",
        lambda **kwargs: evidence,
    )
    github = FakeGitHub("a" * 40)
    github.required_status_checks = []
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_type": "RepositoryRole",
                "actor_id": 5,
                "bypass_mode": "pull_request",
            }
        ],
    }

    snapshot = merge_snapshot(github, lease_fixture())

    assert snapshot["merge_mode"] == "agent"
    assert snapshot["required_check_evidence"] == "local-self-attested"
    assert snapshot["local_verification"] == evidence


def test_exact_head_review_allows_the_known_alpha_ruleset_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifecycle may enforce the repository's exact reviewed-merge bypass."""
    bind_remote_lease(monkeypatch)
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "resolve_release_level",
        lambda github, repo, pull: MODULE["release_level"].Decision(
            "stable", "peer", "full", "test"
        ),
    )
    github = FakeGitHub("a" * 40)
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_type": "RepositoryRole",
                "actor_id": 5,
                "bypass_mode": "pull_request",
            }
        ],
    }
    snapshot = merge_snapshot(github, lease_fixture())
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["authorization_source"] == "review"


def test_reviewed_merge_rejects_an_unknown_ruleset_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any bypass beyond the pinned Alpha exception remains human-only."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_type": "RepositoryRole",
                "actor_id": 4,
                "bypass_mode": "pull_request",
            }
        ],
    }
    snapshot = merge_snapshot(github, lease_fixture())
    assert snapshot["merge_mode"] == "human-only"


def test_beta_reviewed_bypass_rejects_the_alpha_bypass_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The native Copilot rule never relaxes a peer-review level."""
    bind_remote_lease(monkeypatch)
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "resolve_release_level",
        lambda github, repo, pull: MODULE["release_level"].Decision(
            "beta", "peer", "fast", "test"
        ),
    )
    github = FakeGitHub("a" * 40)
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_type": "RepositoryRole",
                "actor_id": 5,
                "bypass_mode": "pull_request",
            }
        ],
    }
    github.mergeable_state = "blocked"
    github.additional_pull_rules = [
        {
            "type": "copilot_code_review",
            "ruleset_id": 7,
            "parameters": {"review_on_push": True},
        }
    ]
    snapshot = merge_snapshot(github, lease_fixture())
    assert snapshot["merge_mode"] == "human-only"
    assert "does not report" in snapshot["protection_reason"]


def quota_snapshot_fixture() -> tuple[FakeGitHub, dict[str, object], str]:
    """Return a routine PR whose only required-check failure is quota."""
    github = FakeGitHub("a" * 40)
    github.base_ref = "dev/m7-staged-ci"
    github.head_ref = "fix/42-quota-fallback"
    github.issue_milestone_number = 7
    github.body += "\n\nCloses #42"
    github.required_status_checks.append(
        {"context": "title", "integration_id": 15368}
    )
    github.run_paths[199] = ".github/workflows/pr-policy.yml"
    github.additional_check_runs = [
        {
            "id": 8,
            "name": "title",
            "head_sha": github.head,
            "status": "completed",
            "conclusion": "failure",
            "details_url": (
                "https://github.com/owner/repo/actions/runs/199/job/8"
            ),
            "app": {"id": 15368},
            "check_suite": {"id": github.run_suite_ids[199]},
        }
    ]
    lease = lease_fixture()
    lease["base_ref"] = github.base_ref
    lease["refs"] = [
        "refs/heads/csarc/leases/pr-42",
        base_lane_ref(github.base_ref),
    ]
    run_url = "https://github.com/owner/repo/actions/runs/199"
    github.quota_note_body = promotion_gate.quota_fallback_note(
        "owner/repo", 42, "a" * 40, [run_url]
    )
    return (
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-98",
    )


def alpha_quota_snapshot_fixture(
    *, sync: bool = False
) -> tuple[FakeGitHub, dict[str, object], str]:
    """Return an exact-marker Alpha candidate with no reviewer."""
    github, lease, note_url = quota_snapshot_fixture()
    github.authorization_actor = "agent"
    github.reviews = []
    github.body += f"\n\n{ADMIN_BYPASS_MARKER}"
    if sync:
        base_ref = "dev/m10-release-backed-adoption"
        github.destination_sha = "f" * 40
        github.commit_payloads[f"git/commits/{github.head}"] = {
            "sha": github.head,
            "tree": {"sha": "e" * 40},
            "parents": [
                {"sha": github.base_sha},
                {"sha": github.destination_sha},
            ],
        }
        github.base_ref = base_ref
        github.head_ref = promotion_gate.delivery_sync.sync_branch_name(
            base_ref, github.destination_sha
        )
        lease["base_ref"] = base_ref
        lease["refs"] = [
            "refs/heads/csarc/leases/pr-42",
            base_lane_ref(base_ref),
        ]
    return github, lease, note_url


def alpha_copilot_blocked_snapshot_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    threads: list[dict[str, object]] | None = None,
) -> tuple[FakeGitHub, dict[str, object]]:
    """Reproduce PR #813's rollout boundary with every local gate green."""
    bind_remote_lease(monkeypatch)
    copilot_mode(monkeypatch)
    monkeypatch.setattr(
        MODULE["review_gate"],
        "unresolved_threads",
        lambda *_: list(threads or []),
    )
    github, lease, _note_url = alpha_quota_snapshot_fixture()
    github.check_conclusion = "success"
    github.required_review_count = 0
    github.mergeable_state = "blocked"
    github.permission = "admin"
    github.additional_pull_rules = [
        {
            "type": "copilot_code_review",
            "ruleset_id": 7,
            "parameters": {"review_on_push": True},
        }
    ]
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_type": "RepositoryRole",
                "actor_id": 5,
                "bypass_mode": "pull_request",
            }
        ],
    }
    return github, lease


def test_alpha_sync_uses_the_exact_head_self_review_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #826: a validated delivery sync may use Alpha self-review."""
    bind_remote_lease(monkeypatch)
    github, lease, _note_url = alpha_quota_snapshot_fixture(sync=True)
    github.required_review_count = 0
    github.check_conclusion = "success"
    github.required_status_checks = [
        {"context": "verify", "integration_id": 15368},
        {"context": "review", "integration_id": 15368},
    ]
    github.additional_check_runs = []
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["admin_bypass"] is True
    assert snapshot["authorization_source"] == "comment"
    assert snapshot["merge_mode"] == "agent"


def test_alpha_copilot_bypass_rejects_another_effective_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not attribute blocked state to Copilot with another live rule."""
    github, lease = alpha_copilot_blocked_snapshot_fixture(monkeypatch)
    github.additional_pull_rules.append(
        {
            "type": "required_deployments",
            "ruleset_id": 7,
            "parameters": {"required_deployment_environments": ["prod"]},
        }
    )
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["merge_mode"] == "human-only"
    assert "does not report" in snapshot["protection_reason"]


@pytest.mark.parametrize("invalid_sync", ["missing-main", "wrong-parents"])
def test_alpha_sync_rejects_a_forged_deterministic_branch(
    invalid_sync: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deterministic name cannot substitute for real sync topology."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture(sync=True)
    if invalid_sync == "missing-main":
        github.compare_status = "behind"
        message = "does not contain current main"
    else:
        github.commit_payloads[f"git/commits/{github.head}"]["parents"] = [
            {"sha": github.base_sha},
            {"sha": "9" * 40},
        ]
        message = "merge current main into the exact base"
    with pytest.raises(RuntimeError, match=message):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_alpha_same_actor_needs_future_zero_review_server_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a future explicit zero-review policy permits an agent merge."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.required_review_count = 0
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
        quota_fallback_note_url=note_url,
    )
    assert snapshot["authorization_actor"] == "agent"
    assert snapshot["merge_mode"] == "agent"


def test_non_alpha_candidate_still_requires_an_independent_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No marker means the ordinary independent-review contract applies."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    github.reviews = []
    with pytest.raises(RuntimeError, match="exact head"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_alpha_marker_must_be_an_exact_body_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prose that merely resembles the marker does not opt in."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    github.reviews = []
    github.body += f"\n\n{ADMIN_BYPASS_MARKER}."
    with pytest.raises(RuntimeError, match="exact head"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


@pytest.mark.parametrize("invalid_route", ["branch", "fork"])
def test_alpha_marker_rejects_non_routine_routes(
    invalid_route: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The marker cannot weaken arbitrary-branch or fork controls."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    if invalid_route == "branch":
        github.head_ref = "promote/m10-release-backed-adoption"
    else:
        github.pull = lambda number=42: {  # ty: ignore[invalid-assignment]
            **FakeGitHub.pull(github, number),
            "head": {
                "ref": github.head_ref,
                "sha": github.head,
                "repo": None,
            },
        }
    with pytest.raises(RuntimeError, match=r"default-branch|Routine fallback"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_default_branch_alpha_route_rejects_a_milestone_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Milestone Issue must use its own dev/mN branch, not default."""
    bind_remote_lease(monkeypatch)
    github, _lease, note_url = alpha_quota_snapshot_fixture()
    github.base_ref = "main"
    lease = lease_fixture()
    with pytest.raises(RuntimeError, match="Milestone-less Issue"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_default_branch_alpha_route_allows_a_milestone_less_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #775: a routine, Milestone-less Issue PR may self-merge into main.

    Uses the repository's actual live `bypass_actors` shape (RepositoryRole
    admin, `pull_request` mode -- confirmed via `gh api
    repos/.../rulesets/22178328` against
    Innoguard-Cyber-Arch/csarc-repo-template), not the fixture's empty
    default: alpha self-merge must clear the same "unverified bypass"
    check a real reviewed merge does, not just the route/marker checks in
    isolation.
    """
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews = []
    github.required_review_count = 0
    github.head_ref = "fix/42-lifecycle"
    github.body = f"Closes #42\n\n{ADMIN_BYPASS_MARKER}"
    github.authorization_actor = "agent"
    github.authorization_actor = "agent"
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_type": "RepositoryRole",
                "actor_id": 5,
                "bypass_mode": "pull_request",
            }
        ],
    }
    lease = lease_fixture()
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["admin_bypass"] is True
    assert snapshot["authorization_source"] == "comment"
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["reviewed_bypass"] is True


def test_alpha_promotion_uses_the_exact_head_self_review_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #905: a recognized Alpha promotion may use self-review."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews = []
    github.required_review_count = 0
    github.head_ref = "promote/m12-agent-workflow-contract"
    github.labels = {"enhancement", "promotion"}
    github.body = f"Refs #42\n\n{ADMIN_BYPASS_MARKER}"
    github.authorization_actor = "agent"
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_type": "RepositoryRole",
                "actor_id": 5,
                "bypass_mode": "pull_request",
            }
        ],
    }
    snapshot = merge_snapshot(
        github,
        lease_fixture(),
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["admin_bypass"] is True
    assert snapshot["authorization_source"] == "comment"
    assert snapshot["merge_mode"] == "agent"


def test_alpha_release_uses_the_exact_head_self_review_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #913: a canonical Alpha release may use solo review."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews = []
    github.required_review_count = 0
    github.head_ref = "release/v0.21.0-beta.1"
    github.body = f"Refs #42\n\n{ADMIN_BYPASS_MARKER}"
    github.authorization_actor = "agent"
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_type": "RepositoryRole",
                "actor_id": 5,
                "bypass_mode": "pull_request",
            }
        ],
    }
    snapshot = merge_snapshot(
        github,
        lease_fixture(),
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["admin_bypass"] is True
    assert snapshot["authorization_source"] == "comment"
    assert snapshot["merge_mode"] == "agent"


def test_alpha_release_rejects_a_fork(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A canonical release branch name cannot authorize another repository."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews = []
    github.required_review_count = 0
    github.head_ref = "release/v0.21.0-beta.1"
    github.body = f"Refs #42\n\n{ADMIN_BYPASS_MARKER}"
    github.pull = lambda number=42: {  # ty: ignore[invalid-assignment]
        **FakeGitHub.pull(github, number),
        "head": {
            "ref": github.head_ref,
            "sha": github.head,
            "repo": {"full_name": "fork/repo"},
        },
    }
    with pytest.raises(RuntimeError, match="same-repository head"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_admin_bypass_clears_the_known_reviewed_bypass_ruleset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #775: the existing non-default alpha route had the same gap.

    Before this fix, `effective_protection` treated any `bypass_actors`
    other than empty as "unverified" for every authorization source except
    `review`/`copilot` -- so a `dev/mN` alpha self-merge PR was *also*
    permanently blocked by this repository's own live bypass (added by
    #580 for exactly the self-approval case alpha self-merge exists for).
    """
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.required_review_count = 0
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_type": "RepositoryRole",
                "actor_id": 5,
                "bypass_mode": "pull_request",
            }
        ],
    }
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
        quota_fallback_note_url=note_url,
    )
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["reviewed_bypass"] is True


def test_admin_bypass_still_rejects_an_unknown_ruleset_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Widening reviewed_merge to "comment" must not accept any bypass shape."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews = []
    github.required_review_count = 0
    github.head_ref = "fix/42-lifecycle"
    github.body = f"Closes #42\n\n{ADMIN_BYPASS_MARKER}"
    github.authorization_actor = "agent"
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_type": "RepositoryRole",
                "actor_id": 4,
                "bypass_mode": "pull_request",
            }
        ],
    }
    lease = lease_fixture()
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["merge_mode"] == "human-only"


@pytest.mark.parametrize(
    "invalid_route", ["multiple", "closed", "wrong-prefix", "fork"]
)
def test_default_branch_alpha_route_requires_a_live_matching_issue(
    invalid_route: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default-branch route rechecks the same Issue shape as non-default."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews = []
    github.required_review_count = 0
    github.head_ref = "fix/42-lifecycle"
    github.body = f"Closes #42\n\n{ADMIN_BYPASS_MARKER}"
    lease = lease_fixture()
    if invalid_route == "multiple":
        github.body += "\n\nCloses #99"
        message = "close its matching Issue exactly"
    elif invalid_route == "closed":
        github.issue_state = "closed"
        message = "Issue is not open"
    elif invalid_route == "wrong-prefix":
        github.head_ref = "promote/42-lifecycle"
        github.body = f"Closes #42\n\n{ADMIN_BYPASS_MARKER}"
        message = "Issue work branch"
    else:
        github.pull = lambda number=42: {  # ty: ignore[invalid-assignment]
            **FakeGitHub.pull(github, number),
            "head": {
                "ref": github.head_ref,
                "sha": github.head,
                "repo": None,
            },
        }
        message = "same-repository head"
    with pytest.raises(RuntimeError, match=message):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_alpha_work_branch_must_close_its_matching_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A numbered branch alone cannot claim the no-review exception."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.body = f"Ready for review.\n\n{ADMIN_BYPASS_MARKER}"
    with pytest.raises(RuntimeError, match="close its matching Issue"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


@pytest.mark.parametrize(
    "body",
    [
        "NotCloses #42",
        "Discloses #42",
        "Closes #42junk",
        "Closes #4\u0662",
        "F\u0130XES #42",
        "Clo\u017fes #42",
        "closes #42",
        "Closes\n#42",
    ],
)
def test_alpha_work_branch_rejects_false_closing_tokens(
    body: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text that GitHub would not link cannot establish the Issue route."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.body = f"{body}\n\n{ADMIN_BYPASS_MARKER}"
    with pytest.raises(RuntimeError, match="close its matching Issue"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_alpha_work_branch_rejects_non_integer_issue_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A JSON float cannot masquerade as the exact live Issue number."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    original_get = github.get

    def malformed_issue(repo: str, path: str) -> object:
        if path == "issues/42":
            return {
                "number": 42.0,
                "pull_request": None,
                "state": "open",
                "milestone": None,
            }
        return original_get(repo, path)

    monkeypatch.setattr(github, "get", malformed_issue)
    with pytest.raises(RuntimeError, match="Issue is not open"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


@pytest.mark.parametrize("invalid_route", ["multiple", "closed", "milestone"])
def test_alpha_work_branch_requires_one_live_matching_issue(
    invalid_route: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routine fallback rechecks the Issue route without hosted policy."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    if invalid_route == "multiple":
        github.body += "\n\nCloses #99"
        message = "close its matching Issue exactly"
    elif invalid_route == "closed":
        github.issue_state = "closed"
        message = "Issue is not open"
    else:
        github.base_ref = "dev/m10-release-backed-adoption"
        github.issue_milestone_number = 9
        lease["base_ref"] = github.base_ref
        lease["refs"] = [
            "refs/heads/csarc/leases/pr-42",
            base_lane_ref(github.base_ref),
        ]
        message = "Milestone does not match"
    with pytest.raises(RuntimeError, match=message):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_alpha_work_branch_accepts_matching_delivery_milestone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live Milestone Issue may use its matching delivery branch."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.base_ref = "dev/m10-release-backed-adoption"
    github.issue_milestone_number = 10
    github.required_review_count = 0
    lease["base_ref"] = github.base_ref
    lease["refs"] = [
        "refs/heads/csarc/leases/pr-42",
        base_lane_ref(github.base_ref),
    ]
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
        quota_fallback_note_url=note_url,
    )
    assert snapshot["admin_bypass"] is True
    assert snapshot["merge_mode"] == "agent"


@pytest.mark.parametrize(
    ("base_ref", "milestone"),
    [
        ("dev/m10-release-backed-adoption", {"number": "10"}),
        ("dev/m1-delivery", {"number": True}),
    ],
)
def test_alpha_work_branch_rejects_malformed_issue_milestone(
    base_ref: str,
    milestone: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed live metadata cannot masquerade as a standalone Issue."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.base_ref = base_ref
    lease["base_ref"] = base_ref
    lease["refs"] = [
        "refs/heads/csarc/leases/pr-42",
        base_lane_ref(base_ref),
    ]
    original_get = github.get

    def malformed_issue(repo: str, path: str) -> object:
        if path == "issues/42":
            return {
                "number": 42,
                "pull_request": None,
                "state": "open",
                "milestone": milestone,
                "body": "- [x] Acceptance verified",
            }
        return original_get(repo, path)

    monkeypatch.setattr(github, "get", malformed_issue)
    with pytest.raises(RuntimeError, match="Issue Milestone is invalid"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_alpha_work_branch_rejects_legacy_dev_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy dev/next is not a routine delivery route."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.base_ref = "dev/next"
    lease["base_ref"] = github.base_ref
    lease["refs"] = [
        "refs/heads/csarc/leases/pr-42",
        base_lane_ref(github.base_ref),
    ]
    with pytest.raises(RuntimeError, match="same-repository delivery route"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_alpha_mixed_review_rules_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One zero-review rule cannot hide another rule requiring approval."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.required_review_count = 0
    github.additional_pull_rules = [
        {
            "type": "pull_request",
            "ruleset_id": 8,
            "parameters": {
                "required_approving_review_count": 1,
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": True,
                "require_last_push_approval": True,
                "required_review_thread_resolution": True,
            },
        }
    ]
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
        quota_fallback_note_url=note_url,
    )
    assert snapshot["protection"] == "blocked"
    assert snapshot["merge_mode"] == "human-only"


@pytest.mark.parametrize("review_count", [False, 0.0, "0", None])
def test_alpha_malformed_zero_review_rule_fails_closed(
    review_count: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only an integer zero can prove the Alpha review policy."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.required_review_count = review_count
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
        quota_fallback_note_url=note_url,
    )
    assert snapshot["protection"] == "unknown"
    assert snapshot["merge_mode"] == "human-only"


@pytest.mark.parametrize("review_count", [True, 1.0, "1", None, -1])
def test_non_alpha_malformed_review_count_fails_closed(
    review_count: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed approval counts cannot prove ordinary branch protection."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.required_review_count = review_count
    snapshot = merge_snapshot(
        github,
        lease_fixture(),
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["protection"] == "unknown"
    assert snapshot["merge_mode"] == "human-only"


@pytest.mark.parametrize(
    "parameters",
    [
        "malformed",
        {"required_status_checks": "verify"},
        {"required_status_checks": [{"context": "verify"}]},
        {
            "required_status_checks": [
                {"context": "verify", "integration_id": None}
            ]
        },
        {
            "required_status_checks": [
                {"context": "verify", "integration_id": True}
            ]
        },
        {
            "required_status_checks": [
                {"context": "verify", "integration_id": 0}
            ]
        },
        {
            "required_status_checks": [
                {"context": "verify", "integration_id": -1}
            ]
        },
    ],
)
def test_alpha_malformed_check_rule_fails_closed(
    parameters: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One valid check rule cannot hide malformed effective parameters."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.required_review_count = 0
    github.additional_check_rules = [
        {
            "type": "required_status_checks",
            "ruleset_id": 8,
            "parameters": parameters,
        }
    ]
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
        quota_fallback_note_url=note_url,
    )
    assert snapshot["protection"] == "unknown"
    assert snapshot["merge_mode"] == "human-only"


def test_alpha_rule_without_ruleset_identity_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every effective rule must expose an auditable Ruleset identity."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.required_review_count = 0
    github.additional_pull_rules = [
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 0,
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": True,
                "require_last_push_approval": True,
                "required_review_thread_resolution": True,
            },
        }
    ]
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
        quota_fallback_note_url=note_url,
    )
    assert snapshot["protection"] == "unknown"
    assert snapshot["merge_mode"] == "human-only"


def test_alpha_changes_requested_remains_a_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alpha removes reviewer quorum, never an explicit change request."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = alpha_quota_snapshot_fixture()
    github.reviews = [
        {
            "user": {"login": "reviewer"},
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2026-08-25T01:00:30Z",
        }
    ]
    with pytest.raises(RuntimeError, match="Changes are still requested"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_routine_quota_note_satisfies_failed_required_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mechanically verified zero-step run can satisfy a routine PR gate."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
        quota_fallback_note_url=note_url,
    )
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["required_check_evidence"] == "quota-fallback"


def test_routine_quota_note_rejects_an_arbitrary_non_default_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quota evidence cannot turn an unrelated branch into a routine PR."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    github.head_ref = "misc/not-a-routine-route"
    with pytest.raises(RuntimeError, match="Routine fallback"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_routine_quota_note_rejects_a_successful_same_head_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quota evidence may only name exact failed zero-step runs."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    github.quota_note_body = promotion_gate.quota_fallback_note(
        "owner/repo",
        42,
        "a" * 40,
        [
            "https://github.com/owner/repo/actions/runs/199",
            "https://github.com/owner/repo/actions/runs/200",
        ],
    )
    with pytest.raises(RuntimeError, match="failed PR head"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_routine_quota_uses_newest_strict_check_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Superseded workflow generations do not block the latest result."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    github.additional_check_runs.extend(
        [
            {
                "id": 198,
                "name": "verify",
                "head_sha": "a" * 40,
                "status": "completed",
                "conclusion": "failure",
                "details_url": (
                    "https://github.com/owner/repo/actions/runs/199/job/8"
                ),
                "app": {"id": 15368},
            },
            {
                "id": 197,
                "name": "workflow audit",
                "head_sha": "a" * 40,
                "status": "completed",
                "conclusion": "cancelled",
                "details_url": (
                    "https://github.com/owner/repo/actions/runs/199/job/9"
                ),
                "app": {"id": 15368},
            },
            {
                "id": 201,
                "name": "workflow audit",
                "head_sha": "a" * 40,
                "status": "completed",
                "conclusion": "skipped",
                "details_url": (
                    "https://github.com/owner/repo/actions/runs/200/job/10"
                ),
                "app": {"id": 15368},
            },
        ]
    )
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
        quota_fallback_note_url=note_url,
    )
    assert snapshot["required_check_evidence"] == "quota-fallback"


@pytest.mark.parametrize(
    "replacement",
    [
        {
            "id": 200,
            "name": "verify",
            "app": {"id": 15368},
            "status": "completed",
            "conclusion": "cancelled",
        },
        {
            "id": 201,
            "name": "verify",
            "app": {"id": 15368},
            "status": "completed",
            "conclusion": "cancelled",
        },
        {
            "id": 199,
            "name": "verify",
            "app": {"id": 7},
            "status": "completed",
            "conclusion": "cancelled",
        },
        {
            "id": 199,
            "name": "other check",
            "app": {"id": 15368},
            "status": "completed",
            "conclusion": "cancelled",
        },
        {
            "id": 199,
            "name": "verify",
            "app": {"id": True},
            "status": "completed",
            "conclusion": "cancelled",
        },
        {
            "id": 201,
            "name": "verify",
            "app": {"id": 15368},
            "status": "in_progress",
            "conclusion": None,
        },
        {
            "id": 201,
            "name": "verify",
            "app": {"id": 15368},
            "status": "completed",
            "conclusion": "failure",
        },
    ],
)
def test_routine_quota_rejects_non_authoritative_replacements(
    replacement: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Latest, unmatched, malformed, pending, or unlisted checks block."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    replacement = {
        **replacement,
        "head_sha": "a" * 40,
        "details_url": ("https://github.com/owner/repo/actions/runs/201/job/8"),
    }
    github.additional_check_runs = [replacement]
    with pytest.raises(
        RuntimeError,
        match=(
            r"Non-quota check failures|Required checks have not succeeded|"
            r"Check run identity is malformed"
        ),
    ):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


@pytest.mark.parametrize(
    "malformed",
    [
        {"id": True, "app": {"id": 15368}, "conclusion": "success"},
        {"id": 201, "app": {"id": True}, "conclusion": "skipped"},
        {"id": 201, "app": None, "conclusion": "success"},
    ],
)
def test_routine_quota_rejects_malformed_successful_identity(
    malformed: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed successful checks cannot satisfy a required context."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    github.additional_check_runs = [
        {
            **malformed,
            "name": "verify",
            "head_sha": "a" * 40,
            "status": "completed",
            "details_url": (
                "https://github.com/owner/repo/actions/runs/201/job/8"
            ),
        }
    ]
    with pytest.raises(RuntimeError, match="Check run identity is malformed"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_routine_quota_rejects_wrong_head_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A newer check from another commit cannot replace this candidate."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    github.check_details_url = (
        "https://github.com/owner/repo/actions/runs/201/job/7"
    )
    github.additional_check_runs = [
        {
            "id": 201,
            "name": "verify",
            "head_sha": "b" * 40,
            "status": "completed",
            "conclusion": "success",
            "details_url": (
                "https://github.com/owner/repo/actions/runs/201/job/8"
            ),
            "app": {"id": 15368},
        }
    ]
    with pytest.raises(RuntimeError, match="verify"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_routine_quota_rejects_optional_pending_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An authoritative pending check blocks even when it is not required."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    github.additional_check_runs = [
        {
            "id": 201,
            "name": "optional scan",
            "head_sha": "a" * 40,
            "status": "in_progress",
            "conclusion": None,
            "details_url": (
                "https://github.com/owner/repo/actions/runs/201/job/8"
            ),
            "app": {"id": 15368},
        }
    ]
    with pytest.raises(RuntimeError, match="optional scan"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


@pytest.mark.parametrize(
    ("extra_check_runs", "statuses", "failure_name"),
    [
        (
            [
                {
                    "id": 201,
                    "name": "optional scan",
                    "head_sha": "a" * 40,
                    "status": "completed",
                    "conclusion": "failure",
                    "details_url": (
                        "https://github.com/owner/repo/actions/runs/201/job/8"
                    ),
                    "app": {"id": 15368},
                }
            ],
            [],
            "optional scan",
        ),
        (
            [],
            [{"context": "external audit", "state": "failure"}],
            "external audit",
        ),
    ],
)
def test_routine_quota_note_rejects_every_uncovered_failure(
    extra_check_runs: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
    failure_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional checks and legacy statuses cannot hide real failures."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    github.additional_check_runs = extra_check_runs
    github.statuses = statuses
    with pytest.raises(RuntimeError, match=failure_name):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_routine_quota_note_cannot_authorize_default_branch_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Promotion, hotfix, and release routes keep their stricter gates."""
    bind_remote_lease(monkeypatch)
    github, _lease, note_url = quota_snapshot_fixture()
    github.base_ref = "main"
    lease = lease_fixture()
    with pytest.raises(RuntimeError, match="default-branch routes"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_routine_quota_note_rejects_a_started_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real required-check execution remains blocked by lifecycle."""
    bind_remote_lease(monkeypatch)
    github, lease, note_url = quota_snapshot_fixture()
    github.quota_runner_id = 12
    github.quota_steps = [
        {
            "name": "Run tests",
            "status": "completed",
            "conclusion": "failure",
        }
    ]
    with pytest.raises(RuntimeError, match="zero-step hosted jobs"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            quota_fallback_note_url=note_url,
        )


def test_commented_review_does_not_clear_requested_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only approval or dismissal clears a review blocker."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews = [
        {
            "user": {"login": "Reviewer"},
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2026-08-25T01:01:30Z",
        },
        {
            "user": {"login": "independent"},
            "state": "APPROVED",
            "submitted_at": "2026-08-25T01:00:30Z",
        },
        {
            "user": {"login": "Reviewer"},
            "state": "COMMENTED",
            "submitted_at": "2026-08-25T01:02:00Z",
        },
    ]
    with pytest.raises(RuntimeError, match="reviewer"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_executing_actor_cannot_approve_its_own_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shared execution identity cannot also supply independent review."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews = [
        {
            "user": {"login": "agent", "type": "User"},
            "author_association": "OWNER",
            "state": "APPROVED",
            "submitted_at": "2026-08-25T01:00:30Z",
            "commit_id": github.head,
            "html_url": (
                "https://github.com/owner/repo/pull/42#pullrequestreview-2"
            ),
        }
    ]
    with pytest.raises(RuntimeError, match="exact head"):
        merge_snapshot(github, lease_fixture())


def test_new_head_invalidates_an_earlier_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An approval for a prior commit cannot authorize the current head."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.reviews[0]["commit_id"] = "9" * 40
    with pytest.raises(RuntimeError, match="exact head"):
        merge_snapshot(github, lease_fixture())


def test_exact_head_approval_requires_live_maintainer_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Historical association alone cannot authorize an automated merge."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.permission = "read"
    with pytest.raises(RuntimeError, match="exact head"):
        merge_snapshot(github, lease_fixture())


def test_exact_head_approval_ignores_author_association() -> None:
    """Issue #785: a downgraded association must not hide a real approval.

    Same finding as `test_authorization_ignores_author_association`: a
    restricted `GITHUB_TOKEN` can report a genuine maintainer's review as
    `COLLABORATOR` instead of `MEMBER`. Only the live
    `collaborators/{login}/permission` lookup should decide this.
    """
    github = FakeGitHub("a" * 40)
    review = {
        "user": {"login": "reviewer", "type": "User"},
        "author_association": "COLLABORATOR",
        "state": "APPROVED",
        "commit_id": github.head,
        "submitted_at": "2026-08-25T01:01:00Z",
    }
    approval = exact_head_approval(
        github, "owner/repo", {"reviewer": review}, github.head, "author"
    )
    assert approval is review


def test_merge_snapshot_revalidates_the_authenticated_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A credential change after acquisition blocks the merge snapshot."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.authenticated_actor = "different-agent"
    with pytest.raises(RuntimeError, match="actor changed"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_untrusted_comment_cannot_resolve_a_maintainer_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a maintainer lifecycle marker can resolve a merge blocker."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.comments = [
        {
            "created_at": "2026-08-25T01:02:00Z",
            "body": "Blocked: a regression remains.",
            "html_url": "https://github.com/owner/repo/pull/42#issuecomment-97",
            "author_association": "MEMBER",
        },
        {
            "created_at": "2026-08-25T01:03:00Z",
            "body": "Merge blocker resolved: looks fine.",
            "html_url": "https://github.com/owner/repo/pull/42#issuecomment-98",
            "author_association": "NONE",
        },
    ]
    with pytest.raises(RuntimeError, match="unresolved blocking comment"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


@pytest.mark.parametrize("marker", ["-", "*", "+"])
def test_all_markdown_list_markers_block_unchecked_items(
    marker: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every CommonMark bullet form preserves the checklist merge gate."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    original_pull = github.pull

    def unchecked_pull() -> dict[str, Any]:
        pull = original_pull()
        pull["body"] = f"{marker} [ ] unresolved"
        return pull

    monkeypatch.setattr(github, "pull", unchecked_pull)
    with pytest.raises(RuntimeError, match="unchecked checklist"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_tampered_lease_cannot_delete_an_arbitrary_ref(tmp_path: Path) -> None:
    """Edited evidence cannot turn release into an arbitrary ref delete."""
    payload = lease_fixture()
    payload["refs"] = ["refs/heads/main"]
    path = tmp_path / "lease.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="refs are invalid"):
        read_lease(path)


def test_label_and_milestone_edits_run_inside_two_lease_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metadata callers cannot omit the pre-write or post-write lease guard."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    checks = 0
    github = FakeGitHub("a" * 40)

    def check_lease(*_arguments: object) -> None:
        nonlocal checks
        checks += 1

    def edit(_command: list[str], **_kwargs: object) -> str:
        github.labels = {"enhancement"}
        github.milestone = "M1"
        return ""

    monkeypatch.setitem(edit_metadata.__globals__, "require_lease", check_lease)
    monkeypatch.setitem(edit_metadata.__globals__, "run", edit)
    edit_metadata(
        SimpleNamespace(
            repo="owner/repo",
            pr_number=42,
            head_sha="a" * 40,
            owner="task/merge",
            lease=lease_path,
            add_label=["enhancement"],
            remove_label=["bug"],
            milestone="M1",
            remove_milestone=False,
        ),
        github,
    )
    assert checks == 2


def test_body_edit_runs_inside_two_lease_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checklist update uses the canonical writer and verifies the result."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    body_path = tmp_path / "body.md"
    body_path.write_text("- [x] Reviewed\n", encoding="utf-8")
    checks = 0
    github = FakeGitHub("a" * 40)

    def check_lease(*_arguments: object) -> None:
        nonlocal checks
        checks += 1

    def edit(
        command: list[str], *, input_text: str | None = None, **_kwargs: object
    ) -> str:
        assert command[-2:] == ["--body-file", "-"]
        body_path.write_text("replacement", encoding="utf-8")
        assert input_text == "- [x] Reviewed\n"
        github.body = input_text or ""
        return ""

    monkeypatch.setitem(edit_metadata.__globals__, "require_lease", check_lease)
    monkeypatch.setitem(edit_metadata.__globals__, "run", edit)
    edit_metadata(
        SimpleNamespace(
            repo="owner/repo",
            pr_number=42,
            head_sha="a" * 40,
            owner="task/merge",
            lease=lease_path,
            body_file=body_path,
            add_label=[],
            remove_label=[],
            milestone=None,
            remove_milestone=False,
        ),
        github,
    )
    assert checks == 2


def test_merge_never_calls_gh_when_protection_is_degraded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Private Free or unknown protection fails before any merge mutation."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    monkeypatch.setitem(
        merge.__globals__,
        "merge_snapshot",
        lambda *_: {"merge_mode": "human-only"},
    )
    called = False

    def unexpected_run(_command: list[str], **_kwargs: object) -> str:
        nonlocal called
        called = True
        return ""

    monkeypatch.setitem(merge.__globals__, "run", unexpected_run)
    with pytest.raises(RuntimeError, match="human maintainer"):
        merge(
            SimpleNamespace(
                repo="owner/repo",
                pr_number=42,
                head_sha="a" * 40,
                owner="task/merge",
                lease=lease_path,
                authorization_url=(
                    "https://github.com/owner/repo/pull/42#issuecomment-99"
                ),
            ),
            FakeGitHub("a" * 40),
        )
    assert not called


def test_merge_uses_synchronous_sha_bound_rest_and_confirms_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A merge cannot become queued auto-merge or target a later head."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    monkeypatch.setitem(
        merge.__globals__,
        "merge_snapshot",
        lambda *_: {
            "merge_mode": "agent",
            "title": "fix(ci): serialize lifecycle writes",
            "reviewed_bypass": True,
            "release_level": "stable",
            "bypass_route": "stable",
        },
    )
    monkeypatch.setitem(merge.__globals__, "require_lease", lambda *_: None)
    monkeypatch.setitem(
        merge.__globals__, "revalidate_release_candidate", lambda *_: ""
    )
    released = False

    def record_release(_lease: dict[str, Any]) -> None:
        nonlocal released
        released = True

    mutations: list[str] = []
    monkeypatch.setitem(merge.__globals__, "release_refs", record_release)
    monkeypatch.setitem(
        merge.__globals__,
        "confirm_refs",
        lambda _lease: mutations.append("lease-cas"),
    )
    github = FakeGitHub("a" * 40)
    original_merge = github.merge

    def record_merge(
        repo: str, number: int, head_sha: str, title: str
    ) -> dict[str, Any]:
        mutations.append("merge-put")
        return original_merge(repo, number, head_sha, title)

    monkeypatch.setattr(github, "merge", record_merge)
    merge(
        SimpleNamespace(
            repo="owner/repo",
            pr_number=42,
            head_sha="a" * 40,
            owner="task/merge",
            lease=lease_path,
            authorization_url=(
                "https://github.com/owner/repo/pull/42#issuecomment-99"
            ),
        ),
        github,
    )
    assert github.audit_comments == [
        "bypass-trace: release_level=stable route=stable actor=agent "
        "reason=exact-head-review"
    ]
    assert mutations == ["lease-cas", "merge-put"]
    assert github.merged
    assert released


@pytest.mark.parametrize(
    "head_ref",
    ("release/v0.18.0-beta.1", "release/v0.18.0-beta.2"),
)
def test_revalidation_includes_canonical_prerelease_branches(
    head_ref: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Alpha and beta candidates cannot skip the final freshness check."""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> str:
        commands.append(command)
        return "candidate is current"

    monkeypatch.setitem(
        revalidate_release_candidate.__globals__,
        "require_lease",
        lambda *_: None,
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__, "run", fake_run
    )

    result = revalidate_release_candidate(
        FakeGitHub("a" * 40), lease_fixture(), head_ref, "beta"
    )

    assert result == "candidate is current"
    assert len(commands) == 1
    assert commands[0][0].endswith("scripts/verify-release-candidate")


def test_revalidation_rebuilds_a_csarc_owned_promotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final merge boundary rechecks promotion release materialization."""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> str:
        commands.append(command)
        if command[0] == "git":
            return "b" * 40
        return "promotion version is exact"

    monkeypatch.setattr(
        MODULE["csarc_config"],
        "load_config",
        lambda *_: {"release_ownership": "csarc-owned"},
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__,
        "require_lease",
        lambda *_: None,
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__, "run", fake_run
    )

    result = revalidate_release_candidate(
        FakeGitHub("a" * 40),
        lease_fixture(),
        "promote/m14-final-delivery",
        "beta",
    )

    assert result == "promotion version is exact"
    assert commands[0][-1] == f"{'a' * 40}^1"
    assert "verify-promotion-version" in commands[1]
    assert commands[1][-2:] == ["--phase", "beta"]


def test_revalidation_rebuilds_an_ordinary_same_pr_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final merge boundary rechecks every CSARC-owned delivery."""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> str:
        commands.append(command)
        return "delivery version is exact"

    monkeypatch.setattr(
        MODULE["csarc_config"],
        "load_config",
        lambda *_: {"release_ownership": "csarc-owned"},
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__,
        "require_lease",
        lambda *_: None,
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__, "run", fake_run
    )

    result = revalidate_release_candidate(
        FakeGitHub("a" * 40),
        lease_fixture(),
        "task/925-stable-release-materialization",
        "stable",
    )

    assert result == "delivery version is exact"
    assert len(commands) == 1
    assert "verify-delivery-version" in commands[0]
    assert commands[0][-6:] == [
        "--base-sha",
        "b" * 40,
        "--head-sha",
        "a" * 40,
        "--phase",
        "stable",
    ]


def test_revalidation_skips_a_formal_delivery_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A topology-validated sync is not a release-bearing work PR."""
    monkeypatch.setattr(
        MODULE["csarc_config"],
        "load_config",
        lambda *_: {"release_ownership": "csarc-owned"},
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__,
        "require_lease",
        lambda *_: None,
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__,
        "live_pull",
        lambda *_: {"number": 42},
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__,
        "require_routine_route",
        lambda *_: "sync",
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__,
        "run",
        lambda *_args, **_kwargs: pytest.fail("must not validate a release"),
    )

    assert (
        revalidate_release_candidate(
            FakeGitHub("a" * 40),
            lease_fixture(),
            "sync/main-to-m15-repository-lifecycle-abcdef012345",
            "beta",
        )
        == ""
    )


def test_revalidation_rejects_an_unverified_sync_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sync-looking branch cannot bypass the exact routine route."""
    monkeypatch.setattr(
        MODULE["csarc_config"],
        "load_config",
        lambda *_: {"release_ownership": "csarc-owned"},
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__,
        "require_lease",
        lambda *_: None,
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__,
        "live_pull",
        lambda *_: {"number": 42},
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__,
        "require_routine_route",
        lambda *_: "issue",
    )

    with pytest.raises(RuntimeError, match="formal sync route"):
        revalidate_release_candidate(
            FakeGitHub("a" * 40),
            lease_fixture(),
            "sync/main-to-m15-repository-lifecycle-abcdef012345",
            "beta",
        )


def test_revalidation_leaves_product_owned_promotions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Product-owned promotion contents remain outside CSARC release policy."""
    monkeypatch.setattr(
        MODULE["csarc_config"],
        "load_config",
        lambda *_: {"release_ownership": "product-owned"},
    )
    monkeypatch.setitem(
        revalidate_release_candidate.__globals__,
        "run",
        lambda *_args, **_kwargs: pytest.fail("must not run"),
    )

    assert (
        revalidate_release_candidate(
            FakeGitHub("a" * 40),
            lease_fixture(),
            "promote/m14-final-delivery",
            "beta",
        )
        == ""
    )


def test_merge_revalidates_a_release_candidate_before_the_final_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An earlier successful status cannot satisfy the final merge boundary."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    monkeypatch.setitem(
        merge.__globals__,
        "merge_snapshot",
        lambda *_: {
            "merge_mode": "agent",
            "title": "chore(main): release 0.2.0",
            "reviewed_bypass": False,
            "head_ref": "release/v0.2.0",
        },
    )
    monkeypatch.setitem(merge.__globals__, "require_lease", lambda *_: None)
    monkeypatch.setitem(merge.__globals__, "release_refs", lambda _lease: None)
    monkeypatch.setitem(merge.__globals__, "confirm_refs", lambda _lease: None)
    github = FakeGitHub("a" * 40)
    github.head_ref = "release/v0.2.0"

    def stale_candidate(
        _github: object,
        _lease: object,
        head_ref: str,
        release_phase_name: str,
    ) -> str:
        assert head_ref == "release/v0.2.0"
        assert release_phase_name == ""
        raise RuntimeError("current base adds release-worthy commits")

    monkeypatch.setitem(
        merge.__globals__,
        "revalidate_release_candidate",
        stale_candidate,
    )
    with pytest.raises(RuntimeError, match="release-worthy commits"):
        merge(
            SimpleNamespace(
                repo="owner/repo",
                pr_number=42,
                head_sha="a" * 40,
                owner="task/merge",
                lease=lease_path,
                authorization_url=(
                    "https://github.com/owner/repo/pull/42#issuecomment-99"
                ),
            ),
            github,
        )
    assert not github.merged


def test_final_merge_snapshot_rejects_a_new_p1_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blocker arriving after the first check wins before the merge PUT."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    bind_remote_lease(monkeypatch)
    monkeypatch.setitem(merge.__globals__, "release_refs", lambda _lease: None)
    github = FakeGitHub("a" * 40)
    github.comment_snapshots = [
        [],
        [
            {
                "created_at": "2026-08-25T01:02:00Z",
                "body": "[P1] A late security regression remains.",
                "html_url": (
                    "https://github.com/owner/repo/pull/42#issuecomment-101"
                ),
                "author_association": "MEMBER",
            }
        ],
    ]
    with pytest.raises(RuntimeError, match="unresolved blocking comment"):
        merge(
            SimpleNamespace(
                repo="owner/repo",
                pr_number=42,
                head_sha="a" * 40,
                owner="task/merge",
                lease=lease_path,
                authorization_url=(
                    "https://github.com/owner/repo/pull/42#issuecomment-99"
                ),
            ),
            github,
        )
    assert not github.merged


def test_final_merge_snapshot_rejects_a_new_inline_p1_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The final snapshot also paginates inline review comments."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.inline_comment_snapshots = [
        [],
        [
            {
                "created_at": "2026-08-25T01:02:00Z",
                "body": "[P1] Late inline blocker.",
                "html_url": (
                    "https://github.com/owner/repo/pull/42#discussion_r2"
                ),
                "author_association": "MEMBER",
            }
        ],
    ]
    with pytest.raises(RuntimeError, match="unresolved blocking comment"):
        merge(
            SimpleNamespace(
                repo="owner/repo",
                pr_number=42,
                head_sha="a" * 40,
                owner="task/merge",
                lease=lease_path,
                authorization_url=(
                    "https://github.com/owner/repo/pull/42#issuecomment-99"
                ),
            ),
            github,
        )
    assert not github.merged


def test_merge_rejects_the_wrong_destination_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A merge response is insufficient without target and parent identity."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    monkeypatch.setitem(
        merge.__globals__,
        "merge_snapshot",
        lambda *_: {
            "merge_mode": "agent",
            "title": "fix(ci): serialize lifecycle writes",
        },
    )
    monkeypatch.setitem(merge.__globals__, "release_refs", lambda _lease: None)
    monkeypatch.setitem(merge.__globals__, "confirm_refs", lambda _lease: None)
    github = FakeGitHub("a" * 40)
    github.merge_parent = "9" * 40
    with pytest.raises(RuntimeError, match="does not match"):
        merge(
            SimpleNamespace(
                repo="owner/repo",
                pr_number=42,
                head_sha="a" * 40,
                owner="task/merge",
                lease=lease_path,
                authorization_url=(
                    "https://github.com/owner/repo/pull/42#issuecomment-99"
                ),
            ),
            github,
        )


def test_merge_does_not_release_a_lease_for_an_unconfirmed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ambiguous REST result remains locked for manual inspection."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    monkeypatch.setitem(
        merge.__globals__,
        "merge_snapshot",
        lambda *_: {
            "merge_mode": "agent",
            "title": "fix(ci): serialize lifecycle writes",
        },
    )
    monkeypatch.setitem(merge.__globals__, "require_lease", lambda *_: None)
    monkeypatch.setitem(
        merge.__globals__, "revalidate_release_candidate", lambda *_: ""
    )
    monkeypatch.setitem(
        merge.__globals__,
        "release_refs",
        lambda _lease: pytest.fail("lease was released"),
    )
    monkeypatch.setitem(merge.__globals__, "confirm_refs", lambda _lease: None)
    github = FakeGitHub("a" * 40)
    github.merge = lambda *_: {  # ty: ignore[invalid-assignment]
        "merged": False,
        "sha": None,
    }
    with pytest.raises(RuntimeError, match="synchronously merge"):
        merge(
            SimpleNamespace(
                repo="owner/repo",
                pr_number=42,
                head_sha="a" * 40,
                owner="task/merge",
                lease=lease_path,
                authorization_url=(
                    "https://github.com/owner/repo/pull/42#issuecomment-99"
                ),
            ),
            github,
        )


COPILOT_REVIEW_URL = "https://github.com/owner/repo/pull/42#pullrequestreview-9"


class CopilotGitHub(FakeGitHub):
    """Serve a Copilot-mode Ruleset and Copilot's exact-head review."""

    def __init__(self, head: str) -> None:
        super().__init__(head)
        self.required_review_count = 0
        self.run_paths[201] = ".github/workflows/pr-review.yml"
        self.copilot_inline: list[dict[str, Any]] = []
        self.copilot_body = (
            "Copilot reviewed 3 out of 3 changed files in this pull request "
            "and generated no comments."
        )
        self.reviews = [self.copilot_review(head)]
        self.additional_pull_rules = [
            {
                "type": "copilot_code_review",
                "ruleset_id": 7,
                "parameters": {"review_on_push": True},
            }
        ]
        self.additional_check_rules = [
            {
                "type": "required_status_checks",
                "ruleset_id": 7,
                "parameters": {
                    "required_status_checks": [
                        {"context": "review", "integration_id": 15368}
                    ]
                },
            }
        ]
        self.additional_check_runs = [
            {
                "id": 201,
                "name": "review",
                "head_sha": head,
                "status": "completed",
                "conclusion": "success",
                "details_url": "https://github.com/owner/repo/actions/runs/201/job/8",
                "app": {"id": 15368},
                "check_suite": {"id": self.run_suite_ids[201]},
            }
        ]

    def copilot_review(self, commit: str) -> dict[str, Any]:
        """Return one Copilot review of ``commit``."""
        return {
            "id": 9,
            "user": {
                "login": "copilot-pull-request-reviewer[bot]",
                "type": "Bot",
            },
            "author_association": "NONE",
            "state": "COMMENTED",
            "submitted_at": "2026-08-25T01:01:00Z",
            "commit_id": commit,
            "body": self.copilot_body if hasattr(self, "copilot_body") else "",
            "html_url": COPILOT_REVIEW_URL,
        }

    def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
        """Serve Copilot's inline comments separately from the reviews."""
        if path.startswith("pulls/42/reviews/9/comments"):
            return self.copilot_inline
        if path.startswith("pulls/42/reviews"):
            for review in self.reviews:
                if review.get("id") == 9:
                    review["body"] = self.copilot_body
        return super().pages(_repo, path)


def copilot_mode(
    monkeypatch: pytest.MonkeyPatch,
    cap: str = "unlimited",
    level: str = "beta",
    review: str = "self",
) -> None:
    """Switch the lifecycle to pr_review_mode=copilot."""
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "review_settings",
        lambda: ("copilot", cap),
    )
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "resolve_release_level",
        lambda github, repo, pull: MODULE["release_level"].Decision(
            level, review, "fast", "test"
        ),
    )


def test_copilot_clean_exact_head_review_authorizes_agent_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #752: a clean Copilot review of the exact head is enough."""
    bind_remote_lease(monkeypatch)
    copilot_mode(monkeypatch)
    snapshot = merge_snapshot(CopilotGitHub("a" * 40), lease_fixture())
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["authorization_source"] == "copilot"
    assert snapshot["authorization_url"] == COPILOT_REVIEW_URL


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("stale", "not reviewed the current head"),
        ("inline", "left 1 comment"),
        ("suppressed", "suppressed"),
        ("unrecognized", "does not state"),
    ],
)
def test_copilot_review_that_is_not_clean_blocks_merge(
    monkeypatch: pytest.MonkeyPatch, change: str, message: str
) -> None:
    """Issue #752: stale, commented, or unrecognized reviews fail closed."""
    bind_remote_lease(monkeypatch)
    copilot_mode(monkeypatch)
    github = CopilotGitHub("a" * 40)
    if change == "stale":
        github.reviews = [github.copilot_review("f" * 40)]
    elif change == "inline":
        github.copilot_inline = [{"path": "a.py", "line": 3, "body": "Bug"}]
    elif change == "suppressed":
        github.copilot_body = (
            "Generated no comments. Comments suppressed due to low "
            "confidence (1)"
        )
    else:
        github.copilot_body = "Copilot wasn't able to review any files."
    with pytest.raises(RuntimeError, match=message):
        merge_snapshot(github, lease_fixture())


def test_copilot_mode_still_accepts_a_maintainer_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #752: the human path stays available in Copilot mode."""
    bind_remote_lease(monkeypatch)
    copilot_mode(monkeypatch)
    github = CopilotGitHub("a" * 40)
    github.reviews = FakeGitHub("a" * 40).reviews
    snapshot = merge_snapshot(github, lease_fixture())
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["authorization_source"] == "review"


def test_copilot_mode_requires_copilot_rule_and_review_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #752: zero approvals are unsafe without the Copilot controls."""
    bind_remote_lease(monkeypatch)
    copilot_mode(monkeypatch)
    for missing in ("rule", "check"):
        github = CopilotGitHub("a" * 40)
        if missing == "rule":
            github.additional_pull_rules = []
        else:
            github.required_status_checks = [
                {"context": "verify", "integration_id": 15368}
            ]
            github.additional_check_rules = []
        snapshot = merge_snapshot(github, lease_fixture())
        assert snapshot["merge_mode"] == "human-only", missing
        assert "Copilot review-on-push" in str(snapshot["protection_reason"])


def test_human_mode_ignores_a_clean_copilot_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #752: pr_review_mode=human keeps requiring a maintainer."""
    bind_remote_lease(monkeypatch)
    github = CopilotGitHub("a" * 40)
    with pytest.raises(RuntimeError, match="independent maintainer approval"):
        merge_snapshot(github, lease_fixture())


def test_copilot_level_cap_blocks_higher_release_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Copilot cannot authorize work above its configured level ceiling."""
    bind_remote_lease(monkeypatch)
    copilot_mode(monkeypatch, "beta", "stable")
    with pytest.raises(RuntimeError, match="does not allow Copilot"):
        merge_snapshot(CopilotGitHub("a" * 40), lease_fixture())


def test_beta_release_level_requires_peer_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clean Copilot review cannot satisfy a peer-review level."""
    bind_remote_lease(monkeypatch)
    copilot_mode(monkeypatch, level="beta", review="peer")
    with pytest.raises(RuntimeError, match="beta release level requires"):
        merge_snapshot(CopilotGitHub("a" * 40), lease_fixture())


def emergency_hotfix_snapshot_fixture() -> tuple[FakeGitHub, dict[str, object]]:
    """Return a beta hotfix with admin reason and exact-head authorization."""
    github = FakeGitHub("a" * 40)
    github.reviews = []
    github.labels = {"bug", "hotfix"}
    github.body = "Ready for review.\n\nFixes #43"
    github.head_ref = "fix/43-production-outage"
    github.issue_user = "maintainer"
    github.issue_labels = {"bug", "hotfix"}
    github.hotfix_comments = [
        {
            "body": "Admin-approve: production outage",
            "user": {"login": "maintainer", "type": "User"},
            "created_at": "2026-08-25T00:59:00Z",
            "html_url": (
                "https://github.com/owner/repo/issues/43#issuecomment-8"
            ),
        }
    ]
    github.permission = "admin"
    github.authorization_actor = "maintainer"
    github.authenticated_actor = "maintainer"
    github.required_review_count = 0
    github.ruleset_response = {
        "enforcement": "active",
        "bypass_actors": [
            {
                "actor_type": "RepositoryRole",
                "actor_id": 5,
                "bypass_mode": "pull_request",
            }
        ],
    }
    lease = lease_fixture()
    lease["actor"] = "maintainer"
    return github, lease


def test_beta_hotfix_merge_binds_admin_authorization_to_merge_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lifecycle accepts the exception only for the authenticated actor."""
    bind_remote_lease(monkeypatch)
    github, lease = emergency_hotfix_snapshot_fixture()

    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
        "maintainer",
    )

    assert snapshot["merge_mode"] == "agent"
    assert snapshot["authorization_source"] == "hotfix-emergency"
    assert snapshot["authorization_actor"] == "maintainer"
    assert snapshot["hotfix_evidence"] == {
        "issue_number": 43,
        "actor": "maintainer",
        "permission": "admin",
        "reason": "production outage",
        "reason_url": (
            "https://github.com/owner/repo/issues/43#issuecomment-8"
        ),
    }


def test_beta_hotfix_merge_rejects_a_different_merge_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An admin cannot leave reusable evidence for a different merger."""
    bind_remote_lease(monkeypatch)
    github, lease = emergency_hotfix_snapshot_fixture()
    github.authenticated_actor = "agent"
    lease["actor"] = "agent"

    with pytest.raises(RuntimeError, match="must be the merge actor"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
            "agent",
        )


def test_copilot_merge_leaves_a_review_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #752: a Copilot-authorized merge records review and head."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    monkeypatch.setitem(
        merge.__globals__,
        "merge_snapshot",
        lambda *_: {
            "merge_mode": "agent",
            "title": "fix(ci): serialize lifecycle writes",
            "reviewed_bypass": True,
            "authorization_source": "copilot",
            "authorization_url": COPILOT_REVIEW_URL,
            "release_level": "stable",
            "bypass_route": "stable",
        },
    )
    monkeypatch.setitem(merge.__globals__, "require_lease", lambda *_: None)
    monkeypatch.setitem(
        merge.__globals__, "revalidate_release_candidate", lambda *_: ""
    )
    monkeypatch.setitem(merge.__globals__, "release_refs", lambda _lease: None)
    monkeypatch.setitem(merge.__globals__, "confirm_refs", lambda _lease: None)
    github = FakeGitHub("a" * 40)
    merge(
        SimpleNamespace(
            repo="owner/repo",
            pr_number=42,
            head_sha="a" * 40,
            owner="task/merge",
            lease=lease_path,
            authorization_url="",
        ),
        github,
    )
    assert github.audit_comments == [
        "bypass-trace: release_level=stable route=stable actor=agent "
        "reason=exact-head-copilot-review",
        f"copilot-review-trace: review={COPILOT_REVIEW_URL} "
        f"head={'a' * 40} actor=agent",
    ]
    assert github.merged
