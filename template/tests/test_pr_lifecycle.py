"""Tests for serialized pull-request lifecycle writes."""

from __future__ import annotations

import hashlib
import json
import re
import runpy
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE = runpy.run_path(str(SCRIPTS / "pr_lifecycle.py"))
acquire = MODULE["acquire"]
audit_message = MODULE["audit_message"]
authorization = MODULE["authorization"]
authorization_statement = MODULE["authorization_statement"]
authorization_template = MODULE["authorization_template"]
base_lane_ref = MODULE["base_lane_ref"]
confirm_refs = MODULE["confirm_refs"]
create_refs = MODULE["create_refs"]
edit_metadata = MODULE["edit_metadata"]
edit_standalone_issue = MODULE["edit_standalone_issue"]
effective_protection = MODULE["effective_protection"]
close_integrated_issue = MODULE["close_integrated_issue"]
expired_remote_lease = MODULE["expired_remote_lease"]
GitHub = MODULE["GitHub"]
LEASE_CORE_FIELDS = MODULE["LEASE_CORE_FIELDS"]
lease_message = MODULE["lease_message"]
lease_status_snapshot = MODULE["lease_status_snapshot"]
lifecycle_main = MODULE["main"]
merged_lease_status_snapshot = MODULE["merged_lease_status_snapshot"]
merge = MODULE["merge"]
merge_quota = MODULE["merge_quota"]
merged_issue_snapshot = MODULE["merged_issue_snapshot"]
merge_snapshot = MODULE["merge_snapshot"]
routine_quota_snapshot = MODULE["routine_quota_snapshot"]
read_lease = MODULE["read_lease"]
require_lease = MODULE["require_lease"]
require_trusted_checkout = MODULE["require_trusted_checkout"]
require_successful_checks = MODULE["require_successful_checks"]
release_refs = MODULE["release_refs"]
remote_repository = MODULE["remote_repository"]
scan_writers = MODULE["scan_writers"]
validate_audit_comment = MODULE["validate_audit_comment"]
writer_violations = MODULE["writer_violations"]
_GIT = shutil.which("git")
if _GIT is None:
    raise RuntimeError("Git is required for PR lifecycle tests")
GIT: str = _GIT


class FakeGitHub:
    """Serve the mutable GitHub state needed by lifecycle tests."""

    def __init__(self, head: str) -> None:
        self.head = head
        self.draft = False
        self.authorization_created_at = "2026-08-25T01:01:00Z"
        self.authorization_actor = "maintainer"
        self.authenticated_actor = "agent"
        self.author = "agent"
        self.timeline: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self.comment_snapshots: list[list[dict[str, Any]]] = []
        self.inline_comments: list[dict[str, Any]] = []
        self.inline_comment_snapshots: list[list[dict[str, Any]]] = []
        self.reviews: list[dict[str, Any]] = [
            {
                "user": {"login": "reviewer"},
                "state": "APPROVED",
                "submitted_at": "2026-08-25T01:00:30Z",
            }
        ]
        self.audit_comments: list[str] = []
        self.protected = True
        self.authorization_type = "User"
        self.authorization_body: str | None = None
        self.permission = "maintain"
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
        self.body = "Closes #266\n\nAlpha 自行合併 / self-merged"
        self.files = ["src/app.py"]
        self.head_ref = "feat/266-lifecycle"
        self.head_repo = "owner/repo"
        self.issue_state = "open"
        self.issue_labels: set[str] = set()
        self.issue_milestone: int | None = None
        self.contained = True
        self.closed_issues: list[int] = []
        self.extra_branches: dict[str, str] = {}
        self.extra_pulls: list[dict[str, Any]] = []

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
            "merged_at": "2026-08-25T02:00:00Z" if self.merged else None,
            "merge_commit_sha": "d" * 40 if self.merged else None,
            "draft": self.draft,
            "title": "fix(ci): serialize lifecycle writes",
            "body": self.body,
            "user": {"login": self.author, "type": "User"},
            "labels": [{"name": name} for name in sorted(self.labels)],
            "milestone": (
                {"title": self.milestone}
                if self.milestone is not None
                else None
            ),
            "base": {"ref": self.base_ref, "sha": self.base_sha},
            "head": {
                "ref": self.head_ref,
                "sha": self.head,
                "repo": {"full_name": self.head_repo},
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
        if path == f"git/ref/heads/{self.base_ref.replace('/', '%2F')}":
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
                "author_association": "OWNER",
                "user": {
                    "login": self.authorization_actor,
                    "type": self.authorization_type,
                },
                "created_at": self.authorization_created_at,
                "body": self.authorization_body
                or authorization_statement("owner/repo", 42, self.head),
            }
        if path == f"collaborators/{self.authorization_actor}/permission":
            return {
                "permission": self.permission,
                "user": {"login": self.authorization_actor},
            }
        if path == "issues/266":
            return {
                "number": 266,
                "state": self.issue_state,
                "body": "- [x] Done",
                "labels": [
                    {"name": name} for name in sorted(self.issue_labels)
                ],
                "milestone": (
                    {"number": self.issue_milestone}
                    if self.issue_milestone is not None
                    else None
                ),
            }
        if path.startswith("compare/"):
            return {"status": "ahead" if self.contained else "diverged"}
        if path == f"rules/branches/{self.base_ref.replace('/', '%2F')}":
            if not self.protected:
                raise RuntimeError("Upgrade to GitHub Pro")
            return [
                {
                    "type": "pull_request",
                    "ruleset_id": 7,
                    "parameters": {
                        "required_approving_review_count": 1,
                        "dismiss_stale_reviews_on_push": True,
                        "require_code_owner_review": True,
                        "require_last_push_approval": True,
                        "required_review_thread_resolution": True,
                    },
                },
                {
                    "type": "required_status_checks",
                    "ruleset_id": 7,
                    "parameters": {
                        "required_status_checks": [{"context": "verify"}]
                    },
                },
            ]
        if path == "rulesets/7":
            return {"enforcement": "active", "bypass_actors": []}
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
                    "name": "verify",
                    "head_sha": self.head,
                    "status": "completed",
                    "conclusion": "success",
                }
            ]
        if key == "statuses" and path.startswith(f"commits/{self.head}/"):
            return []
        raise AssertionError(path)

    def pages(self, _repo: str, path: str) -> list[dict[str, Any]]:
        """Return one paginated fixture."""
        if path.startswith("issues/42/timeline"):
            return self.timeline
        if path.startswith("issues/42/comments"):
            if self.comment_snapshots:
                return self.comment_snapshots.pop(0)
            return self.comments
        if path.startswith("pulls/42/comments"):
            if self.inline_comment_snapshots:
                return self.inline_comment_snapshots.pop(0)
            return self.inline_comments
        if path.startswith("pulls/42/reviews"):
            return self.reviews
        if path.startswith("pulls/42/files"):
            return [{"filename": name} for name in self.files]
        if path.startswith("branches?"):
            live_base = "d" * 40 if self.merged else self.destination_sha
            branches = {
                "main": live_base if self.base_ref == "main" else "f" * 40,
                "dev/next": (
                    live_base if self.base_ref == "dev/next" else "e" * 40
                ),
                self.head_ref: self.head,
                **self.extra_branches,
            }
            return [
                {"name": name, "commit": {"sha": sha}}
                for name, sha in branches.items()
            ]
        if path.startswith("pulls?state=all"):
            return [self.pull(), *self.extra_pulls]
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

    def merge(
        self, _repo: str, _number: int, head_sha: str, _title: str
    ) -> dict[str, Any]:
        """Record one synchronous exact-head merge."""
        assert head_sha == self.head
        self.merged = True
        return {"merged": True, "sha": "d" * 40}

    def close_issue(self, _repo: str, issue_number: int) -> dict[str, Any]:
        """Record one verified Issue close."""
        self.closed_issues.append(issue_number)
        self.issue_state = "closed"
        return {"number": issue_number, "state": "closed"}


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
        "gh pr create --base dev/next --head fix/x --label bug",
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
                issue_type=None,
                remove_type=False,
            ),
            github,
        )


def test_writer_scanner_allows_pr_creation_without_state_or_metadata() -> None:
    """Creating a plain PR is followed by a separately leased edit."""
    assert not writer_violations(
        "gh pr create --base dev/next --head fix/x --title fix --body body"
    )


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


def test_effective_protection_requires_identity_on_every_rule() -> None:
    """One valid Ruleset ID cannot bless another unidentified rule."""

    class FakeGitHub:
        def get(self, _repo: str, path: str) -> object:
            if path.startswith("rules/branches/"):
                return [
                    {
                        "type": "pull_request",
                        "parameters": {
                            "required_approving_review_count": 1,
                            "dismiss_stale_reviews_on_push": True,
                            "require_code_owner_review": True,
                            "require_last_push_approval": True,
                            "required_review_thread_resolution": True,
                        },
                    },
                    {
                        "type": "required_status_checks",
                        "ruleset_id": 7,
                        "parameters": {
                            "required_status_checks": [{"context": "verify"}]
                        },
                    },
                ]
            if path == "rulesets/7":
                return {"enforcement": "active", "bypass_actors": []}
            raise AssertionError(path)

    state, reason, contexts = effective_protection(
        FakeGitHub(), "owner/repo", "main"
    )
    assert state == "unknown"
    assert "every effective rule" in reason
    assert contexts == set()


@pytest.mark.parametrize(
    "tampered_path",
    [
        "scripts/pr_lifecycle.py",
        "scripts/ci_tier.py",
        "scripts/promotion_gate.py",
        "scripts/issue_path_status.py",
    ],
)
def test_mutation_checkout_rejects_a_clean_pr_head_with_policy_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tampered_path: str
) -> None:
    """A writer cannot run from a candidate-controlled policy checkout."""
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init")
    git(work, "config", "user.name", "Policy Test")
    git(work, "config", "user.email", "policy@example.invalid")
    git(
        work,
        "remote",
        "add",
        "origin",
        "https://github.com/owner/repo.git",
    )
    target = work / tampered_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("trusted\n", encoding="utf-8")
    git(work, "add", tampered_path)
    git(work, "commit", "-m", "test: create trusted base")
    base_sha = git(work, "rev-parse", "HEAD")
    git(work, "checkout", "--detach")
    target.write_text("candidate change\n", encoding="utf-8")
    git(work, "add", tampered_path)
    git(work, "commit", "-m", "test: tamper with policy helper")
    monkeypatch.chdir(work)
    with pytest.raises(RuntimeError, match="terminal base SHA"):
        require_trusted_checkout("owner/repo", "main", base_sha)


def test_mutation_checkout_requires_detached_clean_policy_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The trusted writer checkout is exact, detached, and clean."""
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init")
    git(work, "config", "user.name", "Policy Test")
    git(work, "config", "user.email", "policy@example.invalid")
    git(
        work,
        "remote",
        "add",
        "origin",
        "https://github.com/owner/repo.git",
    )
    tracked = work / "policy.txt"
    tracked.write_text("trusted\n", encoding="utf-8")
    git(work, "add", "policy.txt")
    git(work, "commit", "-m", "test: create trusted base")
    base_sha = git(work, "rev-parse", "HEAD")
    monkeypatch.chdir(work)
    with pytest.raises(RuntimeError, match="detached checkout"):
        require_trusted_checkout("owner/repo", "main", base_sha)
    git(work, "checkout", "--detach")
    require_trusted_checkout("owner/repo", "main", base_sha)
    tracked.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="clean checkout"):
        require_trusted_checkout("owner/repo", "main", base_sha)


def test_cli_checks_the_trusted_base_before_dispatching_a_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public writer command cannot bypass trusted-checkout validation."""

    class FakeParser:
        def parse_args(self) -> SimpleNamespace:
            return SimpleNamespace(handler_name="release")

    called = False

    def reject(*_args: object) -> None:
        raise RuntimeError("candidate-controlled checkout")

    def unexpected(*_args: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setitem(lifecycle_main.__globals__, "parser", FakeParser)
    monkeypatch.setitem(
        lifecycle_main.__globals__, "require_cli_mutation_checkout", reject
    )
    monkeypatch.setitem(lifecycle_main.__globals__, "release", unexpected)
    with pytest.raises(SystemExit):
        lifecycle_main()
    assert not called


def test_workflow_callers_prepare_a_detached_policy_base() -> None:
    """Shipped writer callers must leave candidate code before mutation."""
    repo_root = Path(__file__).parents[1]
    triage = (repo_root / ".github/workflows/issue-triage.yml").read_text(
        encoding="utf-8"
    )
    assert "ref: ${{ github.event.repository.default_branch }}" in triage
    assert triage.index("git checkout --detach HEAD") < triage.index(
        "pr_lifecycle.py issue-edit"
    )
    assert triage.index("git clean -ffd") < triage.index(
        "pr_lifecycle.py issue-edit"
    )

    version_policy = repo_root / ".github/workflows/python-version-policy.yml"
    if not version_policy.exists():
        return
    workflow = version_policy.read_text(encoding="utf-8")
    ordered = (
        'head_sha="$(git rev-parse HEAD)"',
        "--json baseRefName,baseRefOid",
        'git checkout --detach "$base_sha"',
        "git clean -ffd",
        "pr_lifecycle.py acquire",
        "pr_lifecycle.py edit",
    )
    positions = [workflow.index(fragment) for fragment in ordered]
    assert positions == sorted(positions)


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
        merge_snapshot.__globals__, "local_branch_strategy", lambda: "main"
    )


def bind_canonical_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make remote refs point to the canonical fixture commit."""
    monkeypatch.setitem(
        require_lease.__globals__, "require_origin", lambda _repo: None
    )
    monkeypatch.setitem(
        require_lease.__globals__, "remote_ref", lambda _ref: "c" * 40
    )


def retained_lease_fixture() -> dict[str, object]:
    """Return an unexpired canonical lease for a non-default merged PR."""
    lease = lease_fixture()
    lease["base_ref"] = "dev/next"
    lease["refs"] = [
        "refs/heads/csarc/leases/pr-42",
        base_lane_ref("dev/next"),
    ]
    acquired = datetime.now(UTC) - timedelta(minutes=15)
    lease["acquired_at"] = acquired.isoformat().replace("+00:00", "Z")
    lease["expires_at"] = (
        (acquired + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    )
    return lease


@pytest.mark.parametrize(
    ("actor", "expires_in", "expected"),
    [("agent", 45, "held"), ("other", 45, "blocked"), ("agent", 0, "blocked")],
)
def test_merged_lease_status_requires_current_actor_and_time(
    actor: str,
    expires_in: int,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovery is advertised only to the live unexpired lease actor."""
    lease = retained_lease_fixture()
    acquired = datetime.now(UTC) - timedelta(minutes=15)
    lease["acquired_at"] = acquired.isoformat().replace("+00:00", "Z")
    lease["expires_at"] = (
        (datetime.now(UTC) + timedelta(minutes=expires_in))
        .isoformat()
        .replace("+00:00", "Z")
    )
    github = FakeGitHub("a" * 40)
    github.base_ref = "dev/next"
    github.merged = True
    github.canonical_lease = lease
    monkeypatch.setitem(
        merged_lease_status_snapshot.__globals__,
        "require_origin",
        lambda _repo: None,
    )
    monkeypatch.setitem(
        merged_lease_status_snapshot.__globals__,
        "remote_ref",
        lambda _ref: "c" * 40,
    )
    snapshot = merged_lease_status_snapshot(
        github, "owner/repo", 42, "a" * 40, actor
    )
    assert snapshot["state"] == expected


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

    github.get = tampered_get  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="canonical evidence"):
        require_lease(github, canonical, "owner/repo", 42, "a" * 40)


def test_retargeting_requires_the_destination_lane_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A base retarget cannot change the lane covered by an active lease."""
    bind_canonical_remote(monkeypatch)
    canonical = lease_fixture()
    canonical["base_ref"] = "dev/next"
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

    github.get = edited_comment  # type: ignore[assignment]
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

    github.collection = stale_collection  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", "a" * 40, {("verify", None)}
        )


def test_required_check_must_match_its_pinned_github_app() -> None:
    """A same-name check from another integration cannot satisfy protection."""
    github = FakeGitHub("a" * 40)
    with pytest.raises(RuntimeError, match="exact head: verify"):
        require_successful_checks(
            github, "owner/repo", "a" * 40, {("verify", 1234)}
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


def test_authorization_must_postdate_resolved_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolving a blocker cannot revive an older merge authorization."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.comments = [
        {
            "created_at": "2026-08-25T01:02:00Z",
            "body": "[merge-blocker] A regression remains.",
            "html_url": "https://github.com/owner/repo/pull/42#issuecomment-97",
            "author_association": "MEMBER",
        },
        {
            "created_at": "2026-08-25T01:03:00Z",
            "body": "[merge-blocker-resolved] Fixed and re-reviewed.",
            "html_url": "https://github.com/owner/repo/pull/42#issuecomment-98",
            "author_association": "OWNER",
        },
    ]
    with pytest.raises(RuntimeError, match="postdate"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )
    github.authorization_created_at = "2026-08-25T01:04:00Z"
    assert (
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )["merge_mode"]
        == "agent"
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
    """Only enforced no-bypass protection permits an agent merge."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    snapshot = merge_snapshot(
        github,
        lease_fixture(),
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["merge_mode"] == "agent"
    github.protected = False
    snapshot = merge_snapshot(
        github,
        lease_fixture(),
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["merge_mode"] == "human-only"


@pytest.mark.parametrize(
    "body",
    [
        "Closes other/repo#266",
        "Closes #266\n\nFixes owner/repo#267",
    ],
)
def test_merge_snapshot_requires_exactly_one_local_closer(
    body: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A foreign or extra closer cannot pass the final merge snapshot."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.head_ref = "feat/266-policy"
    github.body = body
    with pytest.raises(RuntimeError, match="closing reference"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_merge_snapshot_allows_an_unlinked_sync_pull_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Infrastructure syncs do not invent a closing Issue requirement."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.base_ref = "dev/next"
    github.head_ref = "sync/main-to-next-abcdef0"
    github.body = "Synchronize main into the delivery branch."
    lease = lease_fixture()
    lease["base_ref"] = "dev/next"
    monkeypatch.setitem(
        merge_snapshot.__globals__, "local_branch_strategy", lambda: "delivery"
    )
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["close_issue"] is False


def test_merge_snapshot_rejects_an_unlinked_arbitrary_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero-closing-reference merges are limited to known automation routes."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.base_ref = "dev/next"
    github.head_ref = "feature/untracked"
    github.body = "Unlinked work."
    lease = lease_fixture()
    lease["base_ref"] = "dev/next"
    monkeypatch.setitem(
        merge_snapshot.__globals__, "local_branch_strategy", lambda: "delivery"
    )
    with pytest.raises(RuntimeError, match="canonical automation route"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


@pytest.mark.parametrize(
    "head_ref",
    ["sync/main-to-next-abcdef0", "dependabot/pip/pytest-9"],
)
def test_merge_snapshot_rejects_foreign_unlinked_automation(
    head_ref: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fork cannot claim a trusted zero-closer automation branch name."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.base_ref = "dev/next"
    github.head_ref = head_ref
    github.head_repo = "attacker/fork"
    github.body = "Unlinked automation."
    lease = lease_fixture()
    lease["base_ref"] = "dev/next"
    monkeypatch.setitem(
        merge_snapshot.__globals__, "local_branch_strategy", lambda: "delivery"
    )
    with pytest.raises(RuntimeError, match="canonical automation route"):
        merge_snapshot(
            github,
            lease,
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


def test_merge_snapshot_allows_the_canonical_dev_promotion_without_a_closer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dev strategy keeps its explicit long-lived promotion route."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.head_ref = "dev"
    github.body = "Promote the reviewed dev branch."
    monkeypatch.setitem(
        merge_snapshot.__globals__, "local_branch_strategy", lambda: "dev"
    )
    snapshot = merge_snapshot(
        github,
        lease_fixture(),
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["close_issue"] is False


@pytest.mark.parametrize(
    ("head_ref", "passes"),
    [("dev/m9-sdlc", True), ("dev/m8-unrelated", False)],
)
def test_merge_snapshot_binds_a_promotion_closer_to_its_issue_route(
    head_ref: str, passes: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A promotion closer must identify the Issue owning that delivery ref."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.head_ref = head_ref
    github.issue_labels = {"promotion"}
    github.issue_milestone = 9
    github.extra_branches = {"dev/m9-sdlc": github.head}
    monkeypatch.setitem(
        merge_snapshot.__globals__, "local_branch_strategy", lambda: "delivery"
    )
    call = lambda: merge_snapshot(  # noqa: E731
        github,
        lease_fixture(),
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    if passes:
        assert call()["merge_mode"] == "agent"
    else:
        with pytest.raises(RuntimeError, match="canonical route"):
            call()


def test_merge_snapshot_marks_a_direct_delivery_issue_for_atomic_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A direct non-default Issue merge closes before lease release."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.base_ref = "dev/next"
    github.head_ref = "feat/266-delivery"
    lease = lease_fixture()
    lease["base_ref"] = "dev/next"
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "local_branch_strategy",
        lambda: "delivery",
    )
    snapshot = merge_snapshot(
        github,
        lease,
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["merge_mode"] == "agent"
    assert snapshot["close_issue"] is True


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
            "user": {"login": "agent"},
            "state": "APPROVED",
            "submitted_at": "2026-08-25T01:00:30Z",
        }
    ]
    with pytest.raises(RuntimeError, match="independent approving review"):
        merge_snapshot(
            github,
            lease_fixture(),
            "https://github.com/owner/repo/pull/42#issuecomment-99",
        )


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


def test_executing_actor_cannot_authorize_its_own_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared authorization and execution identity forces human-only mode."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.authorization_actor = "agent"
    snapshot = merge_snapshot(
        github,
        lease_fixture(),
        "https://github.com/owner/repo/pull/42#issuecomment-99",
    )
    assert snapshot["merge_mode"] == "human-only"
    assert "executing GitHub actor" in snapshot["protection_reason"]


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


def test_lease_status_reports_available_when_refs_are_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Available means an atomic acquire may be attempted, not ownership."""
    monkeypatch.setitem(
        lease_status_snapshot.__globals__, "require_origin", lambda _repo: None
    )
    monkeypatch.setitem(
        lease_status_snapshot.__globals__, "remote_ref", lambda _ref: None
    )
    status = lease_status_snapshot(
        FakeGitHub("a" * 40), "owner/repo", 42, "a" * 40
    )
    assert status["schema_version"] == 1
    assert status["state"] == "available"
    assert status["base_ref"] == "main"
    assert status["base_sha"] == "b" * 40
    assert status["lease_refs"] == [
        "refs/heads/csarc/leases/pr-42",
        base_lane_ref("main"),
    ]
    assert "holder" not in status


def test_lease_status_reports_a_canonical_active_holder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An active canonical remote lease is visible without its capability."""
    monkeypatch.setitem(
        lease_status_snapshot.__globals__, "require_origin", lambda _repo: None
    )
    monkeypatch.setitem(
        lease_status_snapshot.__globals__,
        "remote_ref",
        lambda _ref: "c" * 40,
    )
    github = FakeGitHub("a" * 40)
    canonical = lease_fixture()
    canonical["acquired_at"] = (
        (datetime.now(UTC) - timedelta(minutes=1))
        .isoformat()
        .replace("+00:00", "Z")
    )
    github.canonical_lease = canonical
    status = lease_status_snapshot(github, "owner/repo", 42, "a" * 40)
    assert status["state"] == "held"
    assert status["holder"] == {
        "pull_request": 42,
        "head_sha": "a" * 40,
        "base_ref": "main",
        "base_sha": "b" * 40,
        "owner": "task/merge",
        "actor": "agent",
        "expires_at": github.canonical_lease["expires_at"],
        "lease_commit": "c" * 40,
    }


def test_lease_status_reports_a_shared_lane_held_by_another_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second PR observes the destination lane owner without acquiring."""
    monkeypatch.setitem(
        lease_status_snapshot.__globals__, "require_origin", lambda _repo: None
    )
    lane = base_lane_ref("main")
    monkeypatch.setitem(
        lease_status_snapshot.__globals__,
        "remote_ref",
        lambda ref: "c" * 40 if ref == lane else None,
    )
    github = FakeGitHub("a" * 40)
    canonical = lease_fixture()
    canonical.update(
        {
            "pull_request": 43,
            "owner": "task/parallel",
            "acquired_at": (datetime.now(UTC) - timedelta(minutes=1))
            .isoformat()
            .replace("+00:00", "Z"),
            "refs": ["refs/heads/csarc/leases/pr-43", lane],
        }
    )
    github.canonical_lease = canonical
    status = lease_status_snapshot(github, "owner/repo", 42, "a" * 40)
    assert status["state"] == "held"
    holder = status["holder"]
    assert isinstance(holder, dict)
    assert holder["pull_request"] == 43
    assert holder["owner"] == "task/parallel"


def test_lease_status_fails_closed_on_malformed_remote_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed remote commits are unknown rather than held or available."""
    monkeypatch.setitem(
        lease_status_snapshot.__globals__, "require_origin", lambda _repo: None
    )
    monkeypatch.setitem(
        lease_status_snapshot.__globals__,
        "remote_ref",
        lambda _ref: "c" * 40,
    )
    github = FakeGitHub("a" * 40)
    github.commit_payloads[f"git/commits/{'c' * 40}"] = {
        "sha": "c" * 40,
        "message": "not a lease",
    }
    status = lease_status_snapshot(github, "owner/repo", 42, "a" * 40)
    assert status["state"] == "unknown"
    assert "canonical" in str(status["reason"])


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


def test_routine_quota_snapshot_reuses_exact_note_and_zero_step_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A routine exception needs one exact note and every live failed run."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.head_ref = "feat/266-routine"
    run_url = "https://github.com/owner/repo/actions/runs/123"
    zero_step: list[str] = []
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "local_branch_strategy",
        lambda: "main",
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "failed_pull_request_run_urls",
        lambda *_: [run_url],
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "require_zero_step_run",
        lambda url, *_: zero_step.append(url),
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "has_exact_quota_note",
        lambda comments, repo, number, sha, urls, signer, boundary: (
            comments == []
            and repo == "owner/repo"
            and number == 42
            and sha == "a" * 40
            and urls == [run_url]
            and signer == "agent"
            and boundary is None
        ),
    )
    snapshot = routine_quota_snapshot(github, lease_fixture())
    assert snapshot["merge_mode"] == "routine-quota"
    assert snapshot["blocked_run_urls"] == [run_url]
    assert snapshot["close_issue"] is False
    assert zero_step == [run_url]


@pytest.mark.parametrize(
    ("note_matches", "zero_step_error", "message"),
    [
        (False, None, "canonical routine quota note"),
        (True, "job ran steps", "job ran steps"),
    ],
)
def test_routine_quota_snapshot_rejects_stale_or_nonzero_evidence(
    note_matches: bool,
    zero_step_error: str | None,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale note or executed job cannot authorize the quota exception."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.head_ref = "feat/266-routine"
    run_url = "https://github.com/owner/repo/actions/runs/123"
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "local_branch_strategy",
        lambda: "main",
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "failed_pull_request_run_urls",
        lambda *_: [run_url],
    )

    def require_run(*_args: object) -> None:
        if zero_step_error:
            raise RuntimeError(zero_step_error)

    monkeypatch.setitem(
        routine_quota_snapshot.__globals__, "require_zero_step_run", require_run
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "has_exact_quota_note",
        lambda *_: note_matches,
    )
    with pytest.raises(RuntimeError, match=message):
        routine_quota_snapshot(github, lease_fixture())


def test_routine_quota_snapshot_requires_the_pull_request_author(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Another lease-capable actor cannot self-merge the author's PR."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.head_ref = "feat/266-routine"
    github.author = "other-author"
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "local_branch_strategy",
        lambda: "main",
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "classify_ci",
        lambda *_: SimpleNamespace(tier="fast", scopes=("source",)),
    )
    with pytest.raises(RuntimeError, match="pull request author"):
        routine_quota_snapshot(github, lease_fixture())


def test_routine_quota_note_must_postdate_the_latest_draft_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returning to Draft invalidates an older same-head quota note."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.head_ref = "feat/266-routine"
    github.timeline = [
        {"event": "convert_to_draft", "created_at": "2026-08-25T02:00:00Z"}
    ]
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "local_branch_strategy",
        lambda: "main",
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "classify_ci",
        lambda *_: SimpleNamespace(tier="fast", scopes=("source",)),
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "failed_pull_request_run_urls",
        lambda *_: ["https://github.com/owner/repo/actions/runs/123"],
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "require_zero_step_run",
        lambda *_: None,
    )
    observed: list[datetime | None] = []

    def reject_old_note(*args: object) -> bool:
        observed.append(args[-1] if isinstance(args[-1], datetime) else None)
        return False

    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "has_exact_quota_note",
        reject_old_note,
    )
    with pytest.raises(RuntimeError, match="canonical routine quota note"):
        routine_quota_snapshot(github, lease_fixture())
    assert observed == [datetime(2026, 8, 25, 2, 0, tzinfo=UTC)]


@pytest.mark.parametrize("kind", ["standard", "quota"])
def test_merge_snapshots_reject_a_closed_linked_issue(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An Issue closed after status cannot be merged by either writer path."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.head_ref = "feat/266-routine"
    github.issue_state = "closed"
    if kind == "standard":
        with pytest.raises(RuntimeError, match="is not open"):
            merge_snapshot(
                github,
                lease_fixture(),
                "https://github.com/owner/repo/pull/42#issuecomment-99",
            )
    else:
        monkeypatch.setitem(
            routine_quota_snapshot.__globals__,
            "classify_ci",
            lambda *_: SimpleNamespace(tier="fast", scopes=("source",)),
        )
        monkeypatch.setitem(
            routine_quota_snapshot.__globals__,
            "local_branch_strategy",
            lambda: "main",
        )
        with pytest.raises(RuntimeError, match="is not open"):
            routine_quota_snapshot(github, lease_fixture())


def test_routine_quota_snapshot_rejects_the_wrong_issue_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A milestone Issue cannot use quota merge against dev/next."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.base_ref = "dev/next"
    github.head_ref = "feat/266-routine"
    github.issue_milestone = 9
    github.extra_branches = {"dev/m9-sdlc": "9" * 40}
    lease = lease_fixture()
    lease["base_ref"] = "dev/next"
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "local_branch_strategy",
        lambda: "delivery",
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "promotion_route_for",
        lambda *_: SimpleNamespace(kind="not-applicable"),
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "classify_ci",
        lambda *_: SimpleNamespace(tier="fast", scopes=("source",)),
    )
    with pytest.raises(
        RuntimeError, match=r"chain|canonical route|open parent"
    ):
        routine_quota_snapshot(github, lease)


def test_routine_quota_snapshot_rejects_an_open_stack_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quota merge waits for a stack parent and a direct route retarget."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.base_ref = "enhancement/254-parent"
    github.head_ref = "feat/266-routine"
    github.issue_milestone = 9
    github.extra_branches = {
        "dev/m9-sdlc": "9" * 40,
        "enhancement/254-parent": "b" * 40,
    }
    github.extra_pulls = [
        {
            "number": 41,
            "state": "open",
            "draft": False,
            "base": {"ref": "dev/m9-sdlc", "sha": "9" * 40},
            "head": {
                "ref": "enhancement/254-parent",
                "sha": "b" * 40,
                "repo": {"full_name": "owner/repo"},
            },
        }
    ]
    lease = lease_fixture()
    lease["base_ref"] = "enhancement/254-parent"
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "local_branch_strategy",
        lambda: "delivery",
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "promotion_route_for",
        lambda *_: SimpleNamespace(kind="not-applicable"),
    )
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "classify_ci",
        lambda *_: SimpleNamespace(tier="fast", scopes=("source",)),
    )
    with pytest.raises(RuntimeError, match="canonical route"):
        routine_quota_snapshot(github, lease)


@pytest.mark.parametrize(
    ("labels", "files"),
    [({"promotion"}, ["src/app.py"]), ({"bug"}, [".github/workflows/ci.yml"])],
)
def test_routine_quota_snapshot_rejects_promotion_and_elevated_work(
    labels: set[str], files: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The no-authorization exception cannot cross its routine risk boundary."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.head_ref = "feat/266-routine"
    github.labels = labels
    github.files = files
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "local_branch_strategy",
        lambda: "main",
    )
    with pytest.raises(
        RuntimeError, match="rejects promotion, hotfix, elevated"
    ):
        routine_quota_snapshot(github, lease_fixture())


def test_routine_quota_snapshot_rejects_a_foreign_closer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A same-number foreign Issue cannot be closed by the quota path."""
    bind_remote_lease(monkeypatch)
    github = FakeGitHub("a" * 40)
    github.head_ref = "feat/266-routine"
    github.body = "Closes other/repo#266\n\nAlpha 自行合併 / self-merged"
    monkeypatch.setitem(
        routine_quota_snapshot.__globals__,
        "local_branch_strategy",
        lambda: "main",
    )
    with pytest.raises(RuntimeError, match="exactly one closing reference"):
        routine_quota_snapshot(github, lease_fixture())


def test_merge_quota_rechecks_the_snapshot_without_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The quota mutation takes a final snapshot without an authorization."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    snapshots = 0
    close_issue: bool | None = None

    def snapshot(*_args: object) -> dict[str, object]:
        nonlocal snapshots
        snapshots += 1
        return {
            "title": "fix(ci): merge a routine quota PR",
            "close_issue": False,
        }

    def merge_once(*_args: object, **_kwargs: object) -> None:
        nonlocal close_issue
        close_issue = bool(_kwargs["close_issue"])

    monkeypatch.setitem(
        merge_quota.__globals__, "routine_quota_snapshot", snapshot
    )
    monkeypatch.setitem(merge_quota.__globals__, "merge_exact", merge_once)
    merge_quota(
        SimpleNamespace(
            repo="owner/repo",
            pr_number=42,
            head_sha="a" * 40,
            owner="task/merge",
            lease=lease_path,
            actor="agent",
        ),
        FakeGitHub("a" * 40),
    )
    assert snapshots == 2
    assert close_issue is False


def test_merge_quota_stops_when_the_final_snapshot_finds_a_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blocker arriving after preflight prevents the quota merge mutation."""
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease_fixture()), encoding="utf-8")
    snapshots = 0

    def snapshot(*_args: object) -> dict[str, object]:
        nonlocal snapshots
        snapshots += 1
        if snapshots == 2:
            raise RuntimeError("An unresolved blocking comment prevents merge")
        return {"title": "fix(ci): merge a routine quota PR"}

    monkeypatch.setitem(
        merge_quota.__globals__, "routine_quota_snapshot", snapshot
    )
    monkeypatch.setitem(
        merge_quota.__globals__,
        "merge_exact",
        lambda *_: pytest.fail("merge mutation was reached"),
    )
    with pytest.raises(RuntimeError, match="unresolved blocking comment"):
        merge_quota(
            SimpleNamespace(
                repo="owner/repo",
                pr_number=42,
                head_sha="a" * 40,
                owner="task/merge",
                lease=lease_path,
                actor="agent",
            ),
            FakeGitHub("a" * 40),
        )


@pytest.mark.parametrize("already_closed", [False, True])
def test_close_issue_revalidates_integration_and_releases_retained_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    already_closed: bool,
) -> None:
    """The retained merge lease makes non-default Issue close auditable."""
    lease = lease_fixture()
    lease["base_ref"] = "dev/next"
    lease["refs"] = [
        "refs/heads/csarc/leases/pr-42",
        base_lane_ref("dev/next"),
    ]
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease), encoding="utf-8")
    github = FakeGitHub("a" * 40)
    github.base_ref = "dev/next"
    github.head_ref = "feat/266-path-status"
    github.merged = True
    github.issue_state = "closed" if already_closed else "open"
    github.canonical_lease = lease
    monkeypatch.setitem(
        merged_issue_snapshot.__globals__, "require_origin", lambda _repo: None
    )
    monkeypatch.setitem(
        merged_issue_snapshot.__globals__, "remote_ref", lambda _ref: "c" * 40
    )
    monkeypatch.setitem(
        merged_issue_snapshot.__globals__,
        "local_branch_strategy",
        lambda: "delivery",
    )
    released = False

    def record_release(_lease: dict[str, Any]) -> None:
        nonlocal released
        released = True

    monkeypatch.setitem(
        close_integrated_issue.__globals__, "release_refs", record_release
    )
    close_integrated_issue(
        SimpleNamespace(
            repo="owner/repo",
            pr_number=42,
            head_sha="a" * 40,
            owner="task/merge",
            lease=lease_path,
            actor="agent",
        ),
        github,
    )
    assert github.issue_state == "closed"
    assert github.closed_issues == ([] if already_closed else [266])
    assert released


@pytest.mark.parametrize(
    "failure", ["containment", "checklist", "branch", "expired"]
)
def test_close_issue_fails_closed_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    """Drifted containment or incomplete acceptance keeps the Issue open."""
    lease = lease_fixture()
    lease["base_ref"] = "dev/next"
    lease["refs"] = [
        "refs/heads/csarc/leases/pr-42",
        base_lane_ref("dev/next"),
    ]
    if failure == "expired":
        lease["expires_at"] = "2026-08-25T01:01:00Z"
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease), encoding="utf-8")
    github = FakeGitHub("a" * 40)
    github.base_ref = "dev/next"
    github.head_ref = "feat/266-path-status"
    github.merged = True
    github.canonical_lease = lease
    if failure == "containment":
        github.contained = False
    elif failure == "checklist":
        github.body += "\n\n- [ ] unfinished"
    elif failure == "branch":
        github.head_ref = "feat/999-wrong-issue"
    monkeypatch.setitem(
        merged_issue_snapshot.__globals__, "require_origin", lambda _repo: None
    )
    monkeypatch.setitem(
        merged_issue_snapshot.__globals__, "remote_ref", lambda _ref: "c" * 40
    )
    monkeypatch.setitem(
        merged_issue_snapshot.__globals__,
        "local_branch_strategy",
        lambda: "delivery",
    )
    monkeypatch.setitem(
        close_integrated_issue.__globals__,
        "release_refs",
        lambda _lease: pytest.fail("unexpected lease release"),
    )
    with pytest.raises(RuntimeError):
        close_integrated_issue(
            SimpleNamespace(
                repo="owner/repo",
                pr_number=42,
                head_sha="a" * 40,
                owner="task/merge",
                lease=lease_path,
                actor="agent",
            ),
            github,
        )
    assert github.issue_state == "open"
    assert not github.closed_issues


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
        },
    )
    monkeypatch.setitem(merge.__globals__, "require_lease", lambda *_: None)
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
    assert mutations == ["lease-cas", "merge-put"]
    assert github.merged
    assert released


def test_non_default_issue_merge_closes_before_releasing_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A delivery merge closes its Issue before releasing the lease."""
    lease = lease_fixture()
    lease["base_ref"] = "dev/next"
    lease["refs"] = [
        "refs/heads/csarc/leases/pr-42",
        base_lane_ref("dev/next"),
    ]
    lease_path = tmp_path / "lease.json"
    lease_path.write_text(json.dumps(lease), encoding="utf-8")
    monkeypatch.setitem(
        merge.__globals__,
        "merge_snapshot",
        lambda *_: {
            "merge_mode": "agent",
            "title": "fix(ci): serialize lifecycle writes",
            "close_issue": True,
        },
    )
    monkeypatch.setitem(merge.__globals__, "confirm_refs", lambda _lease: None)
    mutations: list[str] = []
    monkeypatch.setitem(
        merge.__globals__,
        "release_refs",
        lambda _lease: mutations.append("release"),
    )
    monkeypatch.setitem(
        merge.__globals__,
        "close_merged_issue_under_lease",
        lambda *_: mutations.append("close"),
    )
    github = FakeGitHub("a" * 40)
    github.base_ref = "dev/next"
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
    assert github.merged
    assert mutations == ["close", "release"]


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
        merge.__globals__,
        "release_refs",
        lambda _lease: pytest.fail("lease was released"),
    )
    monkeypatch.setitem(merge.__globals__, "confirm_refs", lambda _lease: None)
    github = FakeGitHub("a" * 40)
    github.merge = lambda *_: {"merged": False, "sha": None}  # type: ignore[method-assign]
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
