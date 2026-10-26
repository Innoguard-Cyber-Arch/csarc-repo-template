"""Public self-hosted log warning in update and lifecycle (Issue #1287).

ADR self-hosted-verification D9: a repository made public without
`csarc self-hosted retire` gets the same `WARNING:` from
`csarc self-hosted status`, `csarc update` (terminal and report), and
lifecycle `check` and `merge`. One shared check decides it; an unknown
visibility or an unreadable run list prints a "not checked" warning, and no
merge decision changes. GitHub is a stub here.
"""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from settings_support import settings_text

from csarc_cli import cli, merge_trace, self_hosted

ROOT = Path(__file__).resolve().parents[1]
REPO = "acme/product"
PUBLIC = "are public: the repository is public"
UNCHECKED = "not checked"
WORKFLOWS = "actions/workflows?per_page=100"
RUNS = "actions/workflows/9/runs?per_page=1"
LIFECYCLES = {
    "root": ROOT / "scripts/pr_lifecycle.py",
    "template": ROOT / "template/.csarc/scripts/pr_lifecycle.py",
}


def empty(_path: str) -> object:
    """Answer nothing; used where the check must not read."""
    return {}


class Repository:
    """GitHub stub: visibility, csarc-verify.yml runs, and failures."""

    def __init__(
        self, private: object = False, runs: int = 0, fail: str | None = None
    ) -> None:
        self.private = private
        self.runs = runs
        self.fail = fail
        self.paths: list[str] = []

    def read(self, path: str) -> object:
        """Answer one path below `repos/<repo>/`."""
        self.paths.append(path)
        if path == self.fail:
            raise RuntimeError("GitHub request failed: HTTP 502.")
        if path == "":
            return {"private": self.private}
        if path == WORKFLOWS:
            flows = [{"id": 1, "path": ".github/workflows/ci.yml"}]
            if self.runs:
                flows.append({"id": 9, "path": self_hosted.WORKFLOW_PATH})
            return {"workflows": flows}
        if path == RUNS:
            return {"total_count": self.runs}
        return {"unexpected": True}

    # Lifecycle's client: get(repo, path).
    def get(self, repo: str, path: str) -> object:
        assert repo == REPO
        return self.read(path)


class SelfHostedClient:
    """The `csarc self-hosted` and `csarc update` client: get(endpoint)."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def get(self, endpoint: str) -> object:
        """Strip `repos/<repo>/` and answer like the repository stub."""
        prefix = f"repos/{REPO}"
        assert endpoint == prefix or endpoint.startswith(f"{prefix}/")
        return self.repository.read(endpoint[len(prefix) + 1 :])


def client(private: object = False, runs: int = 0) -> self_hosted.GitHub:
    """Return the self-hosted client typed as the window commands use it."""
    return cast(self_hosted.GitHub, SelfHostedClient(Repository(private, runs)))


@pytest.mark.parametrize(
    ("private", "mode", "runs", "expected"),
    [
        (True, "self-hosted", 3, ""),
        (False, "self-hosted", 0, PUBLIC),
        (False, "local", 2, PUBLIC),
        (False, "hosted", 0, ""),
        (None, "local", 0, UNCHECKED),
    ],
)
def test_shared_check_matches_adr_d9(
    private: object, mode: str, runs: int, expected: str
) -> None:
    """R1: public with self-hosted settings or runs warns; private never."""
    github = Repository(private, runs)
    text = merge_trace.retire_warning(REPO, private, mode, github.read)
    assert (expected in text) if expected else text == ""
    if expected == PUBLIC:
        assert "Run 'csarc self-hosted retire'" in text
    # A self-hosted mode decides without reading the run list.
    if mode == "self-hosted" or private is not False:
        assert github.paths == []


@pytest.mark.parametrize("fail", [WORKFLOWS, RUNS])
def test_unreadable_runs_are_never_silent(fail: str) -> None:
    """AC3: an unreadable or malformed answer says it was not checked."""
    github = Repository(False, runs=1, fail=fail)
    text = merge_trace.retire_warning(REPO, False, "local", github.read)
    assert text.startswith(f"Self-hosted logs on '{REPO}': not checked (")
    assert "HTTP 502" in text
    assert text.endswith("Run 'csarc self-hosted status' when GitHub answers.")
    text = merge_trace.retire_warning(REPO, False, "local", lambda _p: [])
    assert "GitHub answered unexpectedly" in text


def test_every_copy_of_the_check_is_identical() -> None:
    """The lifecycle, template, and CLI copies stay byte-identical."""
    copies = {
        (ROOT / path).read_bytes()
        for path in (
            "scripts/merge_trace.py",
            "template/.csarc/scripts/merge_trace.py",
            "src/csarc_cli/merge_trace.py",
        )
    }
    assert len(copies) == 1


def resolved_repository(
    visibility: str, verified: bool
) -> cli.RepositoryContext:
    return cli.RepositoryContext(
        REPO, "acme", "Organization", visibility, "github", verified
    )


@pytest.mark.parametrize(
    ("visibility", "verified", "mode", "runs", "expected"),
    [
        ("public", True, "self-hosted", 0, PUBLIC),
        ("public", True, "local", 4, PUBLIC),
        ("public", True, "hosted", 0, ""),
        ("private", True, "self-hosted", 4, ""),
        ("internal", True, "self-hosted", 4, ""),
        ("public", False, "local", 0, UNCHECKED),
    ],
)
def test_update_prints_the_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    visibility: str,
    verified: bool,
    mode: str,
    runs: int,
    expected: str,
) -> None:
    """AC1/AC3: `csarc update` warns on standard error, stdout stays clean."""
    monkeypatch.setattr(self_hosted, "GhApi", lambda: client(False, runs))
    saved = {
        "verification_mode_private": mode,
        "verification_mode_public": "hosted",
    }
    text = cli.update_retire_warning(
        resolved_repository(visibility, verified), saved
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    if expected:
        assert expected in text
        assert captured.err == f"WARNING: {text}\n"
    else:
        assert text == captured.err == ""


def test_update_without_github_origin_reads_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No GitHub repository means no Actions logs to check."""
    monkeypatch.setattr(self_hosted, "GhApi", lambda: pytest.fail("read"))
    context = cli.RepositoryContext(None, None, None, "public", "saved", False)
    assert cli.update_retire_warning(context, {}) == ""


def update_report(tmp_path: Path, retire: str) -> dict[str, object]:
    """Build one update report with the given warning text."""
    answers = cli.resolve_release_answers(
        tmp_path, {"language": "ci", "project_mode": "existing"}
    )
    revision = cli.Revision("v1.1.0", "d" * 40, "https://example.invalid/t")
    plan = cli.ResolvedPlan(
        mode="update",
        target=tmp_path / "product",
        revision=revision,
        repository=resolved_repository("public", True),
        answers=answers,
        capabilities={},
        files=cli.Plan((), (), (), ("kept.txt",), (), (), ()),
        update={
            "project_verification_hook": {
                "configured": False,
                "path": None,
                "reason": "Configuration validated.",
                "result": "not-run",
            },
            "update_available": False,
        },
    )
    return cli.lifecycle_report_model(
        plan,
        operation="update",
        plan_name=cli.UPDATE_PLAN_BASENAME,
        plan_sha256="a" * 64,
        generated_at="2026-10-26T00:00:00+00:00",
        before=answers,
        previous=revision,
        target_head="c" * 40,
        target_changes=(),
        retire_warning=retire,
    )


def test_update_report_lists_retire_as_the_next_step(tmp_path: Path) -> None:
    """AC1: the report carries one non-blocking item naming `retire`."""
    assert update_report(tmp_path, "")["required_actions"] == []
    text = merge_trace.retire_warning(REPO, False, "self-hosted", empty)
    report = update_report(tmp_path, text)
    assert report["required_actions"] == [
        {
            "blocking": False,
            "command": "csarc self-hosted retire",
            "kind": "verification",
            "message": text,
            "subject": "self-hosted logs",
        }
    ]
    # Non-blocking: the plan stays applicable.
    assert report["status"] == "review-required"
    assert report["applicable"] is True
    unchecked = merge_trace.retire_warning(REPO, None, "local", empty)
    rows = update_report(tmp_path, unchecked)["required_actions"]
    assert isinstance(rows, list)
    assert rows[0]["command"] == "csarc self-hosted status"


def lifecycle(
    name: str, root: Path, private: str, render: str
) -> Callable[..., str]:
    """Load one lifecycle's mode reader against a rendered root."""
    function = runpy.run_path(str(LIFECYCLES[name]))[
        "configured_verification_mode"
    ]
    (root / ".csarc").mkdir(parents=True, exist_ok=True)
    text = settings_text(
        "",
        verification_mode=None,
        verification_mode_private=private,
        verification_mode_public="hosted",
    )
    if private == "self-hosted":
        text += "self_hosted_runner: {}\nself_hosted_environments:\n- dev\n"
    (root / ".csarc/config.yml").write_text(text, encoding="utf-8")
    (root / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (root / ".github/workflows" / render).write_text("", "utf-8")
    function.__globals__["repository_root"] = lambda: root
    return function


@pytest.mark.parametrize("name", LIFECYCLES)
@pytest.mark.parametrize(
    ("private", "mode", "runs", "expected"),
    [
        (False, "self-hosted", 0, PUBLIC),
        (False, "local", 5, PUBLIC),
        (False, "local", 0, ""),
        (True, "self-hosted", 5, ""),
    ],
)
def test_lifecycle_warns_without_changing_the_mode(
    name: str,
    private: bool,
    mode: str,
    runs: int,
    expected: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC2: check and merge read this mode; the warning changes nothing."""
    effective = mode if private else "hosted"
    render = (
        "csarc-verify.yml" if effective == "self-hosted" else "pr-policy.yml"
    )
    function = lifecycle(name, tmp_path, mode, render)
    assert function(Repository(private, runs), REPO) == effective
    captured = capsys.readouterr()
    assert captured.out == ""
    if expected:
        assert captured.err.startswith("WARNING: Self-hosted logs on ")
        assert expected in captured.err
    else:
        assert captured.err == ""


@pytest.mark.parametrize("name", LIFECYCLES)
def test_lifecycle_keeps_failing_closed_on_a_stale_render(
    name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC2: a self-hosted render on a public repository still must re-render."""
    function = lifecycle(name, tmp_path, "self-hosted", "csarc-verify.yml")
    with pytest.raises(RuntimeError, match="csarc update"):
        function(Repository(False), REPO)
    assert PUBLIC in capsys.readouterr().err


@pytest.mark.parametrize("name", LIFECYCLES)
def test_lifecycle_never_skips_an_unreadable_run_list(
    name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC3: unknown visibility fails closed; unreadable runs say so."""
    function = lifecycle(name, tmp_path, "local", "pr-policy.yml")
    with pytest.raises(RuntimeError, match="Repository visibility"):
        function(Repository(None), REPO)
    assert function(Repository(False, 1, fail=RUNS), REPO) == "hosted"
    err = capsys.readouterr().err
    assert err.startswith(f"WARNING: Self-hosted logs on '{REPO}': not checked")


def test_status_uses_the_same_check(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`status` prints the shared text through its own client."""
    github = client(False, runs=2)
    text = self_hosted.retire_warning(github, REPO, False, "local")
    assert text == merge_trace.retire_warning(
        REPO, False, "local", Repository(False, 2).read
    )
    assert PUBLIC in text
    assert self_hosted.retire_warning(github, REPO, True, "local") == ""
    assert capsys.readouterr().err == ""
