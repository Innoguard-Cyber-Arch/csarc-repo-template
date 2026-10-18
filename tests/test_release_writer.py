"""The one tree-bound Release writer's preflight and lease (Issue #1074).

`scripts/release_writer.py` decides whether `publish-release` may write and
serializes hosted and local writers through one remote lease. These tests
drive it against a real Git repository and an in-memory `gh` so the mode
matrix, merge-trace fail-closed rules, remote-state conflicts, and lease
contention are observed outcomes rather than source text.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_COPY = ROOT / "template" / ".csarc" / "scripts" / "release_writer.py"
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def load(name: str) -> ModuleType:
    """Import one script module by path."""
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


writer = load("release_writer")
merge_trace = load("merge_trace")


class FakeGh:
    """An in-memory `gh` covering the tag, Release, and lease endpoints."""

    def __init__(self, repo: str = "acme/fixture") -> None:
        """Start with no tags, Releases, refs, or lease commits."""
        self.repo = repo
        self.tags: dict[str, str] = {}
        self.releases: dict[str, dict[str, object]] = {}
        self.refs: dict[str, str] = {}
        self.commits: dict[str, dict[str, Any]] = {}
        self.login = "maintainer"

    def __call__(
        self, command: list[str], stdin: str | None
    ) -> tuple[int, str, str]:
        """Serve one `gh` invocation."""
        if command[:3] == ["gh", "release", "view"]:
            release = self.releases.get(command[3])
            if release is None:
                return 1, "", "release not found"
            return 0, json.dumps({"tagName": command[3], **release}), ""
        if command[:3] == ["gh", "api", "user"]:
            return 0, self.login + "\n", ""
        method, path = command[3], command[4]
        prefix = f"repos/{self.repo}/"
        assert path.startswith(prefix)
        path = path.removeprefix(prefix)
        body = json.loads(stdin) if stdin else {}
        return self.api(method, path, body)

    def api(  # noqa: C901
        self, method: str, path: str, body: dict[str, Any]
    ) -> tuple[int, str, str]:
        """Model GitHub's ref and commit endpoints."""
        missing = (1, "", "gh: Not Found (HTTP 404)")
        if path.startswith("git/ref/tags/"):
            sha = self.tags.get(path.removeprefix("git/ref/tags/"))
            if sha is None:
                return missing
            return 0, json.dumps({"object": {"sha": sha}}), ""
        if path == "git/commits" and method == "POST":
            sha = hashlib.sha1(  # noqa: S324 -- fixture object id
                json.dumps(body, sort_keys=True).encode()
            ).hexdigest()
            self.commits[sha] = {
                "sha": sha,
                "message": body["message"],
                "parents": [{"sha": item} for item in body["parents"]],
            }
            return 0, json.dumps({"sha": sha}), ""
        if path.startswith("git/commits/"):
            commit = self.commits.get(path.removeprefix("git/commits/"))
            return (0, json.dumps(commit), "") if commit else missing
        if path == "git/refs" and method == "POST":
            ref = str(body["ref"]).removeprefix("refs/")
            if ref in self.refs:
                return 1, "", "gh: Reference already exists (HTTP 422)"
            self.refs[ref] = str(body["sha"])
            return 0, "{}", ""
        ref = path.split("/", 2)[2]
        if method == "GET":
            sha = self.refs.get(ref)
            if sha is None:
                return missing
            return 0, json.dumps({"object": {"sha": sha}}), ""
        if method == "PATCH":
            parents = [
                item["sha"]
                for item in self.commits[str(body["sha"])]["parents"]
            ]
            if body.get("force") or self.refs.get(ref) not in parents:
                return 1, "", "gh: Update is not a fast forward (HTTP 422)"
            self.refs[ref] = str(body["sha"])
            return 0, "{}", ""
        if method == "DELETE":
            self.refs.pop(ref, None)
            return 0, "", ""
        raise AssertionError(f"unexpected {method} {path}")


def git(root: Path, *arguments: str) -> str:
    """Run one Git command in the fixture."""
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(root), *arguments],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit(root: Path, message: str, name: str = "work.txt") -> str:
    """Commit one file change and return the new commit."""
    path = root / name
    path.write_text(path.read_text() + "x\n" if path.exists() else "x\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def schema2_settings(ownership: str | None) -> str:
    """Return a complete schema 2 `.csarc/config.yml` for the fixture."""
    lines = [
        "schema_version: 2",
        "admin_bypass: off",
        "code_owner: '@acme'",
        "container: false",
        "copilot_review: off",
        "coverage_mode: global",
        "coverage_threshold: 80",
        "documentation_languages: en",
        "documentation_mode: off",
        "enable_codeql: false",
        "governance_mode: managed",
        "languages: []",
        "lifecycle: []",
        "project_maturity: early",
        "github_project_url: ''",
        "project_verification_hook: ''",
        "python_floor: latest",
        "release_trigger: manual",
        "scheduled_checks: []",
        "security_reporting_channel: security@example.com",
        "verification_mode: local",
    ]
    if ownership is not None:
        lines.append(f"release_ownership: {ownership}")
    return "\n".join(lines) + "\n"


def project(tmp_path: Path, ownership: str = "csarc-owned") -> Path:
    """Build a template-source checkout whose first commit is the baseline."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    for name in ("release_writer.py", "merge_trace.py", "csarc_config.py"):
        shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
    (root / "policies").mkdir()
    shutil.copy2(
        ROOT / "policies" / "merge-trailers.json",
        root / "policies" / "merge-trailers.json",
    )
    (root / ".csarc").mkdir()
    (root / ".csarc" / "config.yml").write_text(
        schema2_settings(ownership), encoding="utf-8"
    )
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    commit(root, "chore: install the merge trailer contract")
    return root


def context(root: Path, records: dict[str, str] | None = None) -> object:
    """Audit the fixture as the canonical template source."""

    def run_git(arguments: list[str]) -> tuple[int, str]:
        result = subprocess.run(  # noqa: S603
            ["git", "-C", str(root), *arguments],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout

    def api(endpoint: str) -> tuple[int, str]:
        comment = endpoint.rsplit("/", 1)[1]
        body = (records or {}).get(comment)
        if body is None:
            return 1, "gh: Not Found (HTTP 404)"
        return 0, json.dumps({"body": body})

    return merge_trace.AuditContext(
        run_git, api, lambda: merge_trace.CANONICAL_IDENTITY
    )


def trailers(tree: str) -> str:
    """Return a contract-valid trailer paragraph for one tree."""
    url = "https://github.com/acme/fixture/pull/7"
    return "\n".join(
        (
            f"CSARC-Evidence: {url}#issuecomment-42",
            "CSARC-Evidence-SHA256: sha256:" + "a" * 64,
            f"CSARC-Evidence-Tree: {tree}",
            "CSARC-Trust: github-hosted",
            "CSARC-Route: issue",
            "CSARC-Approval: review",
            f"CSARC-Authorization: {url}#issuecomment-43",
        )
    )


def test_template_copy_is_byte_identical() -> None:
    """Generated projects run the same writer guard as the template."""
    assert (
        TEMPLATE_COPY.read_bytes()
        == (ROOT / "scripts" / "release_writer.py").read_bytes()
    )


def test_checkout_must_be_the_exact_clean_candidate(tmp_path: Path) -> None:
    """A different HEAD or a modified tracked file never publishes."""
    root = project(tmp_path)
    first = git(root, "rev-parse", "HEAD")
    second = commit(root, "feat: more")
    assert writer.checkout_errors(root, second) == []
    assert writer.checkout_errors(root, first) == [
        f"checked-out commit {second} is not the candidate {first}"
    ]
    (root / "work.txt").write_text("changed\n")
    assert writer.checkout_errors(root, second) == [
        "tracked files differ from the candidate tree"
    ]


@pytest.mark.parametrize(
    ("message", "finding"),
    [
        ("feat: merged without trailers", "untraced"),
        ("feat: wrong tree\n\n" + trailers("b" * 40), "tree-mismatch"),
    ],
)
def test_csarc_owned_fails_closed_on_a_trace_finding(
    tmp_path: Path, message: str, finding: str
) -> None:
    """After the baseline, a missing trailer or tree mismatch blocks."""
    root = project(tmp_path)
    sha = commit(root, message)
    gh = FakeGh()
    with pytest.raises(writer.WriterError, match=finding):
        writer.preflight(
            root,
            writer.GitHub(gh.repo, gh),
            sha,
            "v0.2.0",
            "stage",
            audit_context=context(root),
        )


def test_csarc_owned_fails_closed_on_a_payload_mismatch(
    tmp_path: Path,
) -> None:
    """A durable record that disagrees with the trailers blocks."""
    root = project(tmp_path)
    (root / "work.txt").write_text("traced\n")
    git(root, "add", "-A")
    tree = git(root, "write-tree")
    git(root, "commit", "-q", "-m", "feat: traced\n\n" + trailers(tree))
    sha = git(root, "rev-parse", "HEAD")
    gh = FakeGh()
    audit = context(root, {"42": "not a merge evidence summary"})
    with pytest.raises(writer.WriterError, match="evidence-digest-mismatch"):
        writer.preflight(
            root,
            writer.GitHub(gh.repo, gh),
            sha,
            "v0.2.0",
            "stage",
            audit_context=audit,
        )


def test_product_owned_only_reports_drift(tmp_path: Path) -> None:
    """The product release writer keeps ownership; CSARC writes nothing."""
    root = project(tmp_path, "product-owned")
    sha = commit(root, "feat: wrong tree\n\n" + trailers("b" * 40))
    gh = FakeGh()
    decision = writer.preflight(
        root,
        writer.GitHub(gh.repo, gh),
        sha,
        "v0.2.0",
        "stage",
        audit_context=context(root),
    )
    assert decision["writer"] == "none"
    trace = decision["trace"]
    assert isinstance(trace, dict)
    assert trace["blocking"] is False
    assert "tree-mismatch" in trace["findings"][0]


def test_verification_only_has_no_release_to_block(tmp_path: Path) -> None:
    """Verification-only never audits or writes a CSARC Release."""
    root = project(tmp_path, "verification-only")
    sha = commit(root, "feat: untraced")
    gh = FakeGh()
    decision = writer.preflight(
        root,
        writer.GitHub(gh.repo, gh),
        sha,
        "v0.2.0",
        "stage",
        audit_context=context(root),
    )
    assert decision["writer"] == "none"
    assert "trace" not in decision


def test_missing_ownership_fails_closed(tmp_path: Path) -> None:
    """No saved owner means no writer, never a guessed one."""
    root = project(tmp_path)
    (root / ".csarc" / "config.yml").write_text(schema2_settings(None))
    sha = commit(root, "chore: drop ownership")
    gh = FakeGh()
    with pytest.raises(writer.WriterError, match="release_ownership"):
        writer.preflight(
            root,
            writer.GitHub(gh.repo, gh),
            sha,
            "v0.2.0",
            "stage",
            audit_context=context(root),
        )


def test_a_second_release_writer_workflow_blocks(tmp_path: Path) -> None:
    """A legacy release-please workflow is a second writer to retire."""
    root = project(tmp_path)
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "release.yml").write_text(
        "run: ./scripts/publish-release publish\n"
    )
    (workflows / "release-please.yml").write_text(
        "uses: googleapis/release-please-action@abc\n"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: baseline workflows")
    sha = git(root, "rev-parse", "HEAD")
    gh = FakeGh()
    with pytest.raises(writer.WriterError, match=r"release-please\.yml"):
        writer.preflight(
            root,
            writer.GitHub(gh.repo, gh),
            sha,
            "v0.2.0",
            "stage",
            audit_context=context(root),
        )


def test_remote_state_is_idempotent_for_the_same_candidate() -> None:
    """Only this candidate's tag and Release are ever reused."""
    gh = FakeGh()
    github = writer.GitHub(gh.repo, gh)
    sha, other = "1" * 40, "2" * 40
    assert writer.release_state(github, "v0.2.0", sha) == "none"
    gh.tags["v0.2.0"] = sha
    assert writer.release_state(github, "v0.2.0", sha) == "tagged"
    gh.releases["v0.2.0"] = {"isDraft": True, "isImmutable": False}
    assert writer.release_state(github, "v0.2.0", sha) == "draft"
    gh.releases["v0.2.0"] = {"isDraft": False, "isImmutable": True}
    assert writer.release_state(github, "v0.2.0", sha) == "published"
    with pytest.raises(writer.WriterError, match="never moved"):
        writer.release_state(github, "v0.2.0", other)


def test_remote_state_conflicts_stop_the_writer() -> None:
    """An unknown draft or a mutable published Release is never reused."""
    gh = FakeGh()
    github = writer.GitHub(gh.repo, gh)
    sha = "1" * 40
    gh.releases["v0.2.0"] = {"isDraft": True, "isImmutable": False}
    with pytest.raises(writer.WriterError, match="unknown Release"):
        writer.release_state(github, "v0.2.0", sha)
    gh.tags["v0.2.0"] = sha
    gh.releases["v0.2.0"] = {"isDraft": False, "isImmutable": False}
    with pytest.raises(writer.WriterError, match="mutable"):
        writer.release_state(github, "v0.2.0", sha)


def test_publish_needs_a_staged_draft(tmp_path: Path) -> None:
    """`publish` never creates the tag or draft itself."""
    root = project(tmp_path)
    sha = git(root, "rev-parse", "HEAD")
    gh = FakeGh()
    with pytest.raises(writer.WriterError, match="stage"):
        writer.preflight(
            root,
            writer.GitHub(gh.repo, gh),
            sha,
            "v0.2.0",
            "publish",
            audit_context=context(root),
        )
    gh.tags["v0.2.0"] = sha
    gh.releases["v0.2.0"] = {"isDraft": True, "isImmutable": False}
    decision = writer.preflight(
        root,
        writer.GitHub(gh.repo, gh),
        sha,
        "v0.2.0",
        "publish",
        audit_context=context(root),
    )
    assert decision["writer"] == "csarc"
    assert decision["release_state"] == "draft"


def test_lease_contention_admits_one_writer() -> None:
    """A second holder waits; the same holder retries; expiry reclaims."""
    gh = FakeGh()
    github = writer.GitHub(gh.repo, gh)
    sha, tree = "1" * 40, "3" * 40
    hosted = writer.acquire_lease(
        github, "v0.2.0", sha, tree, holder="actions:1", now=NOW
    )
    with pytest.raises(writer.WriterError, match="held by actions:1"):
        writer.acquire_lease(
            github, "v0.2.0", sha, tree, holder="local:maintainer", now=NOW
        )
    retry = writer.acquire_lease(
        github, "v0.2.0", sha, tree, holder="actions:1", now=NOW
    )
    with pytest.raises(writer.WriterError, match="no longer held"):
        writer.confirm_lease(github, "v0.2.0", hosted, now=NOW)
    later = NOW + timedelta(hours=2)
    local = writer.acquire_lease(
        github, "v0.2.0", sha, tree, holder="local:maintainer", now=later
    )
    with pytest.raises(writer.WriterError, match="no longer held"):
        writer.confirm_lease(github, "v0.2.0", retry, now=later)
    writer.confirm_lease(github, "v0.2.0", local, now=later)
    assert writer.release_lease(github, "v0.2.0", retry) is False
    assert writer.release_lease(github, "v0.2.0", local) is True
    assert gh.refs == {}


def test_an_expired_lease_cannot_write() -> None:
    """A writer that outlives its lease stops before the next write."""
    gh = FakeGh()
    github = writer.GitHub(gh.repo, gh)
    lease = writer.acquire_lease(
        github, "v0.2.0", "1" * 40, "3" * 40, holder="actions:1", now=NOW
    )
    with pytest.raises(writer.WriterError, match="expired"):
        writer.confirm_lease(
            github, "v0.2.0", lease, now=NOW + timedelta(hours=2)
        )


def test_a_forged_lease_commit_is_not_reclaimed() -> None:
    """A lease ref whose commit is not canonical fails closed."""
    gh = FakeGh()
    github = writer.GitHub(gh.repo, gh)
    gh.commits["f" * 40] = {
        "sha": "f" * 40,
        "message": "hand-made",
        "parents": [],
    }
    gh.refs[writer.lease_ref("v0.2.0")] = "f" * 40
    with pytest.raises(writer.WriterError, match="not a release lease"):
        writer.acquire_lease(
            github, "v0.2.0", "1" * 40, "3" * 40, holder="actions:1", now=NOW
        )


def test_lease_holder_names_the_hosted_run_or_local_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hosted and local fallback writers carry distinct lease holders."""
    gh = FakeGh()
    github = writer.GitHub(gh.repo, gh)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    assert writer.lease_holder(github) == "actions:123"
    monkeypatch.delenv("GITHUB_ACTIONS")
    assert writer.lease_holder(github) == "local:maintainer"
