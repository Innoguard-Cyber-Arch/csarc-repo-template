"""Self-hosted VM verification route and evidence (Issue #1269).

ADR self-hosted-verification D3, D4, D6 (L3, L6), D10, and Q1: a read-only
`csarc-verify.yml` runs only on `workflow_dispatch`, its first step checks
the dispatch before any candidate code, and the lifecycle accepts only a VM
run that GitHub recorded for the exact head on the registered runner. The
root and generated copies of the evidence reader are checked alike.
"""

from __future__ import annotations

import io
import json
import re
import runpy
import subprocess
import tempfile
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jinja2
import pytest
import yaml
from settings_support import settings_text
from test_pr_lifecycle import (
    MODULE,
    bind_remote_lease,
    human_review_mode,
    lease_fixture,
    merge_snapshot,
)
from test_single_writer_merge import (
    AUTHORIZATION_URL,
    SingleWriterGitHub,
    use_local_mode,
)

# Re-export the autouse fixture so this module pins the same review mode.
__all__ = ["human_review_mode"]

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "template/.github/workflows/csarc-verify.yml.jinja"
READERS = {
    "root": ROOT / "scripts/self_hosted_evidence.py",
    "template": ROOT / "template/.csarc/scripts/self_hosted_evidence.py",
}
REPO = "acme/product"
HEAD, TREE, BASE = "a" * 40, "e" * 40, "b" * 40
REGISTRATION = "https://github.com/acme/csarc-devops/issues/7"
CONFIG = (
    settings_text(
        "",
        verification_mode=None,
        verification_mode_private="self-hosted",
        verification_mode_public="hosted",
    )
    + "self_hosted_environments:\n- dev\n- uat\n"
)
REGISTERED = (
    f"self_hosted_runner:\n  id: vm-01\n  registration: {REGISTRATION}\n"
)
COPIER = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))


def render(runner: dict[str, str], environments: list[str]) -> dict[Any, Any]:
    """Render the workflow template and parse it."""
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)  # noqa: S701
    text = env.from_string(WORKFLOW.read_text(encoding="utf-8")).render(
        self_hosted_runner=runner, self_hosted_environments=environments
    )
    data = yaml.safe_load(text)
    data["_text"] = text
    return data


def registered_workflow() -> dict[Any, Any]:
    """Return the workflow for a registered dev and uat repository."""
    return render({"id": "vm-01", "registration": REGISTRATION}, ["dev", "uat"])


# ---------------------------------------------------------------------------
# AC1/AC5: the read-only, dispatch-only workflow.
# ---------------------------------------------------------------------------


def test_workflow_is_read_only_and_dispatch_only() -> None:
    """AC1/R1: only workflow_dispatch, read permissions, and no secrets."""
    data = registered_workflow()
    assert data["run-name"] == (
        "Self-hosted verify PR #${{ inputs.pull_request }} "
        "${{ inputs.head_sha }}"
    )
    triggers = data[True]
    assert list(triggers) == ["workflow_dispatch"]
    assert set(triggers["workflow_dispatch"]["inputs"]) == {
        "pull_request",
        "head_sha",
        "environment",
        "window_end",
    }
    assert data["permissions"] == {
        "actions": "read",
        "contents": "read",
        "pull-requests": "read",
    }
    assert "secrets." not in data["_text"]
    assert list(data["jobs"]) == ["verify"]
    job = data["jobs"]["verify"]
    assert "permissions" not in job
    assert job["runs-on"] == [
        "self-hosted",
        "${{ 'csarc-vm-vm-01' }}",
        "csarc-env-${{ inputs.environment }}",
    ]
    for step in job["steps"]:
        if "uses" in step:
            assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", step["uses"])
            assert step["with"]["persist-credentials"] is False


def test_workflow_offers_only_registered_environments() -> None:
    """AC1: the environment choice lists only registered environments."""
    data = render({}, ["uat"])
    inputs = data[True]["workflow_dispatch"]["inputs"]
    assert inputs["environment"]["options"] == ["uat"]
    # An unregistered render routes to a label no registered VM carries.
    assert "csarc-vm-unregistered" in data["jobs"]["verify"]["runs-on"][1]


@pytest.mark.parametrize(
    ("mode", "rendered"),
    [("self-hosted", True), ("local", False), ("hosted", False)],
)
def test_only_a_self_hosted_render_ships_the_route(
    mode: str, rendered: bool
) -> None:
    """AC1/AC5: Copier excludes the workflow and reader outside self-hosted."""
    env = jinja2.Environment()  # noqa: S701
    excluded = {
        env.from_string(rule).render(verification_mode=mode)
        for rule in COPIER["_exclude"]
        if "csarc_verify" in rule or "self_hosted_evidence" in rule
    }
    assert len(excluded) == 2
    for path in (
        ".github/workflows/csarc-verify.yml",
        ".csarc/scripts/self_hosted_evidence.py",
    ):
        assert (path not in excluded) is rendered


def test_dispatch_check_runs_first_and_execution_declares_its_identity() -> (
    None
):
    """AC2/R3: the base-defined check precedes the candidate checkout."""
    steps = registered_workflow()["jobs"]["verify"]["steps"]
    names = [step["name"] for step in steps]
    reader = runpy.run_path(str(READERS["root"]))
    assert names[0] == reader["CHECK_STEP"]
    candidate = names.index("Check out the exact candidate")
    trusted = names.index("Check out the trusted verification policy")
    assert 0 < trusted < candidate
    assert steps[trusted]["with"]["ref"] == "${{ github.sha }}"
    execute = steps[-1]
    assert execute["name"].startswith("Execute self-hosted verification ")
    for field in ("head", "tree", "tier", "scopes", "environment", "window"):
        assert f" {field}=${{{{ steps." in " " + execute["name"]
    assert "mode=self-hosted" in execute["name"]
    assert "trusted_executor.py" in execute["run"]
    assert "CSARC_VERIFICATION_SUBJECT_ROOT" in execute["run"]
    assert execute["env"]["CSARC_SELF_HOSTED_VM"] == "true"


# ---------------------------------------------------------------------------
# AC2/R1/R3: the first step, executed against a stubbed GitHub API.
# ---------------------------------------------------------------------------


def dispatch_script() -> str:
    """Return the Python body of the first step."""
    run = registered_workflow()["jobs"]["verify"]["steps"][0]["run"]
    lines = run.splitlines()
    assert lines[0] == "python3 - <<'PY'"
    return "\n".join(lines[1 : lines.index("PY")])


def run_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    base: str = "dev/m21-self-hosted",
    environment: str = "dev",
    window: datetime | None = None,
    private: object = True,
    head_repo: str | None = REPO,
    head_sha: str = HEAD,
    workflow_ref: str = "",
) -> tuple[int, str, str, str]:
    """Execute the first step; return its exit code, stdout, summary, output."""
    end = window or datetime.now(UTC) + timedelta(hours=20)
    summary = tmp_path / "summary"
    output = tmp_path / "output"
    environ = {
        "GITHUB_API_URL": "https://api.github.test",
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_REF_NAME": base,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_WORKFLOW_REF": workflow_ref
        or f"{REPO}/.github/workflows/csarc-verify.yml@refs/heads/{base}",
        "GITHUB_STEP_SUMMARY": str(summary),
        "GITHUB_OUTPUT": str(output),
        "GH_TOKEN": "token",
        "PR_NUMBER": "7",
        "HEAD_SHA": HEAD,
        "ENVIRONMENT": environment,
        "WINDOW_END": end.strftime("%Y-%m-%dT%H:%MZ"),
    }
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    pull = {
        "state": "open",
        "head": {
            "sha": head_sha,
            "ref": "feat/1-change",
            "repo": {"full_name": head_repo} if head_repo else None,
        },
        "base": {"ref": base},
        "labels": [{"name": "promotion"}, {"name": "documentation"}],
    }

    def urlopen(request: urllib.request.Request, timeout: int) -> io.BytesIO:
        assert timeout == 30
        assert request.get_header("Authorization") == "Bearer token"
        url = request.full_url
        body = (
            {"private": private}
            if url.endswith(f"/repos/{REPO}")
            else pull
            if url.endswith("/pulls/7")
            else None
        )
        assert body is not None, url
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout)
    try:
        exec(dispatch_script(), {"__name__": "__main__"})  # noqa: S102
        code = 0
    except SystemExit as error:
        code = int(error.code or 0)

    def read(path: Path) -> str:
        return path.read_text("utf-8") if path.exists() else ""

    return code, stdout.getvalue(), read(summary), read(output)


def test_dispatch_check_accepts_a_same_repository_private_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: a valid dispatch passes its facts on without a warning."""
    code, stdout, summary, output = run_dispatch(tmp_path, monkeypatch)
    assert code == 0, stdout
    assert "WARNING" not in stdout
    assert summary == ""
    assert f"head={HEAD}\n" in output
    assert "head_ref=feat/1-change\n" in output
    assert "labels=documentation,promotion\n" in output
    assert "environment=dev\n" in output


@pytest.mark.parametrize(
    ("case", "kwargs", "message"),
    [
        ("fork", {"head_repo": "fork/product"}, "the head is a fork"),
        ("deleted fork", {"head_repo": None}, "the head is a fork"),
        ("public", {"private": False}, "repository is public"),
        ("moved head", {"head_sha": "c" * 40}, "the head moved"),
        ("wrong environment", {"environment": "uat"}, "needs 'dev'"),
        (
            "main needs uat",
            {"base": "main", "environment": "dev"},
            "needs 'uat'",
        ),
        (
            "other branch definition",
            {
                "workflow_ref": (
                    f"{REPO}/.github/workflows/csarc-verify.yml"
                    "@refs/heads/feat/9-evil"
                )
            },
            "not this workflow on a branch",
        ),
        (
            "unsupported branch",
            {"base": "release/v1", "environment": "dev"},
            "needs 'dev or uat'",
        ),
    ],
)
def test_dispatch_check_rejects_before_any_candidate_code(
    case: str,
    kwargs: dict[str, Any],
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2/AC4/R1/R3: fork, public, moved, and misrouted dispatches stop."""
    code, stdout, _summary, output = run_dispatch(
        tmp_path, monkeypatch, **kwargs
    )
    assert code == 1, case
    assert stdout.startswith("ERROR: Self-hosted dispatch: ")
    assert message in stdout
    assert output == ""


def test_dispatch_check_warns_in_the_last_two_hours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2 (ADR D7): under two hours left prints one WARNING twice."""
    window = datetime.now(UTC) + timedelta(hours=1, minutes=40)
    code, stdout, summary, _output = run_dispatch(
        tmp_path, monkeypatch, base="main", environment="uat", window=window
    )
    assert code == 0
    line = summary.strip()
    assert line.startswith("WARNING: Self-hosted uat verification: the window ")
    assert "Run 'csarc self-hosted extend --env uat' before it closes." in line
    assert re.search(r"\((1h3\d|1h40)m left\)", line)
    assert line in stdout


# ---------------------------------------------------------------------------
# AC3/AC4/R2/R3: the lifecycle reads and binds the VM run.
# ---------------------------------------------------------------------------


def reader(name: str) -> dict[str, Any]:
    """Load one self_hosted_evidence.py namespace."""
    return runpy.run_path(str(READERS[name]))


def lease(base: str = "dev/m21-self-hosted") -> dict[str, Any]:
    """Return the lease fields the evidence binds to."""
    return {
        "head_sha": HEAD,
        "head_tree": TREE,
        "base_ref": base,
        "base_sha": BASE,
    }


def vm_run(**changes: object) -> dict[str, Any]:
    """Return one successful dispatched run of the base definition."""
    return {
        "id": 501,
        "run_attempt": 1,
        "event": "workflow_dispatch",
        "path": ".github/workflows/csarc-verify.yml",
        "head_branch": "dev/m21-self-hosted",
        "head_sha": BASE,
        "display_title": f"Self-hosted verify PR #7 {HEAD}",
        "status": "completed",
        "conclusion": "success",
        "html_url": f"https://github.com/{REPO}/actions/runs/501",
        "repository": {"full_name": REPO},
        "head_repository": {"full_name": REPO},
        "actor": {"login": "maintainer"},
        "triggering_actor": {"login": "operator"},
        **changes,
    }


def vm_job(
    completed: datetime | None = None,
    env: str = "dev",
    tier: str = "fast",
    head: str = HEAD,
    tree: str = TREE,
    **changes: object,
) -> dict[str, Any]:
    """Return the one successful job on the registered runner."""
    done = completed or datetime.now(UTC) - timedelta(hours=1)
    execute = (
        f"Execute self-hosted verification head={head} tree={tree} "
        f"tier={tier} scopes=docs,source mode=self-hosted "
        f"environment={env} window=2026-10-26T09:00Z"
    )
    return {
        "id": 601,
        "status": "completed",
        "conclusion": "success",
        "labels": ["self-hosted", "csarc-vm-vm-01", f"csarc-env-{env}"],
        "runner_name": f"csarc-vm-01-{env}",
        "runner_group_name": "Default",
        "started_at": (done - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "completed_at": done.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "steps": [
            {"name": "Set up job", "conclusion": "success"},
            {
                "name": "Check the dispatch before any candidate code",
                "conclusion": "success",
            },
            {"name": "Check out the exact candidate", "conclusion": "success"},
            {"name": execute, "conclusion": "success"},
        ],
        **changes,
    }


def loaded_config(text: str = CONFIG + REGISTERED) -> dict[str, object]:
    """Return a self-hosted configuration through the trusted reader."""
    namespace = runpy.run_path(str(ROOT / "scripts/csarc_config.py"))
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "config.yml"
        path.write_text(text, encoding="utf-8")
        return namespace["load_config"](path)


@pytest.mark.parametrize("name", READERS)
def test_vm_run_binds_to_the_exact_head_and_registered_runner(
    name: str,
) -> None:
    """AC3/R2: a matching run becomes self-hosted-registered evidence."""
    namespace = reader(name)
    evidence = namespace["validate_run"](
        vm_run(),
        [vm_job()],
        repo=REPO,
        lease=lease(),
        config=loaded_config(),
        required_tier="fast",
    )
    assert evidence["trust"] == "self-hosted-registered"
    assert (evidence["head_sha"], evidence["tree_sha"]) == (HEAD, TREE)
    assert evidence["mode"] == "self-hosted"
    assert evidence["environment"] == "dev"
    assert evidence["scopes"] == ["docs", "source"]
    assert evidence["command"] == "./.csarc/scripts/verify-fast"
    assert evidence["runner_labels"] == [
        "csarc-env-dev",
        "csarc-vm-vm-01",
        "self-hosted",
    ]
    executor = evidence["executor"]
    assert executor["runner_name"] == "csarc-vm-01-dev"
    assert executor["actor"] == "maintainer"
    assert executor["triggering_actor"] == "operator"
    assert executor["run_url"].endswith("/actions/runs/501")
    lines = namespace["trace_lines"](
        {"self_hosted_verification": evidence}, "pr=7"
    )
    assert lines == [
        "self-hosted-verification-trace: "
        f"run=https://github.com/{REPO}/actions/runs/501 actor=maintainer "
        "triggering_actor=operator runner=csarc-vm-01-dev environment=dev "
        f"window=2026-10-26T09:00Z mode=self-hosted head={HEAD} tier=fast "
        "pr=7 trust=self-hosted-registered"
    ]
    merge_trace = runpy.run_path(str(ROOT / "scripts/merge_trace.py"))
    data = merge_trace["canonical_bytes"](evidence)
    assert merge_trace["envelope"](
        data, trust="self-hosted-registered", route="milestone"
    )["trust"] == ("self-hosted-registered")
    freshness = runpy.run_path(str(ROOT / "scripts/evidence_freshness.py"))
    record = freshness["normalized_record"](evidence, "self-hosted-registered")
    assert record["trust"] == "self-hosted-registered"


def rejected(
    run: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
    *,
    base: str = "dev/m21-self-hosted",
    required_tier: str = "fast",
    config: str = CONFIG + REGISTERED,
    now: datetime | None = None,
) -> str:
    """Return why the reader rejects one run."""
    with pytest.raises(RuntimeError) as error:
        reader("template")["validate_run"](
            run or vm_run(),
            [job or vm_job()],
            repo=REPO,
            lease=lease(base),
            config=loaded_config(config),
            required_tier=required_tier,
            now=now,
        )
    return str(error.value)


@pytest.mark.parametrize(
    ("case", "run", "job", "message"),
    [
        ("push event", {"event": "push"}, {}, "not a workflow_dispatch"),
        (
            "other workflow",
            {"path": ".github/workflows/evil.yml"},
            {},
            "not .github/workflows/csarc-verify.yml",
        ),
        (
            "definition on another branch",
            {"head_branch": "feat/9-evil"},
            {},
            "trusted base definition",
        ),
        (
            "definition at another commit",
            {"head_sha": "c" * 40},
            {},
            "trusted base definition",
        ),
        (
            "fork run",
            {"head_repository": {"full_name": "fork/product"}},
            {},
            "not this repository",
        ),
        ("failed run", {"conclusion": "failure"}, {}, "did not succeed"),
        ("wrong runner", {}, {"runner_name": "csarc-vm-02-dev"}, "runner is"),
        (
            "unregistered labels",
            {},
            {"labels": ["self-hosted", "csarc-vm-vm-02", "csarc-env-dev"]},
            "labels are not",
        ),
        (
            "GitHub-hosted runner",
            {},
            {"labels": ["ubuntu-latest"], "runner_name": "GitHub Actions 1"},
            "labels are not",
        ),
        (
            "other runner group",
            {},
            {"runner_group_name": "GitHub Actions"},
            "runner group",
        ),
        ("no dispatch check", {}, {"steps": []}, "dispatch check"),
    ],
)
def test_vm_run_rejects_every_unbound_fact(
    case: str, run: dict[str, Any], job: dict[str, Any], message: str
) -> None:
    """AC4/R2/R3: workflow, branch, repository, and runner must all bind."""
    assert message in rejected(vm_run(**run), vm_job(**job)), case


@pytest.mark.parametrize(
    ("case", "job", "kwargs"),
    [
        ("head changed", {"head": "c" * 40}, {}),
        ("tree changed", {"tree": "f" * 40}, {}),
        ("tier too weak", {}, {"required_tier": "full"}),
        (
            "uat run for a dev base",
            {
                "env": "uat",
                "labels": ["self-hosted", "csarc-vm-vm-01", "csarc-env-dev"],
                "runner_name": "csarc-vm-01-dev",
            },
            {},
        ),
    ],
)
def test_vm_run_rejects_a_changed_head_or_weaker_run(
    case: str, job: dict[str, Any], kwargs: dict[str, Any]
) -> None:
    """AC4: the declared head, tree, environment, and tier must hold."""
    message = rejected(vm_run(), vm_job(**job), **kwargs)
    assert "not the exact head" in message, case


def test_vm_run_rejects_stale_evidence() -> None:
    """AC3: VM evidence older than 24 hours is stale."""
    old = datetime.now(UTC) - timedelta(hours=25)
    assert "stale" in rejected(job=vm_job(completed=old))


@pytest.mark.parametrize(
    ("config", "base", "message"),
    [
        (CONFIG + "self_hosted_runner: {}\n", "dev/m1-x", "Register with"),
        (
            CONFIG.replace("- dev\n", "") + REGISTERED,
            "dev/m1-x",
            "registered 'dev' environment",
        ),
        (CONFIG + REGISTERED, "release/v1", "'dev or uat'"),
    ],
)
def test_vm_run_needs_a_registered_environment(
    config: str, base: str, message: str
) -> None:
    """AC4 (ADR D5/D10): unregistered repositories and environments fail."""
    assert message in rejected(
        vm_run(head_branch=base), config=config, base=base
    )


class RunsGitHub:
    """Serve dispatched runs and their jobs."""

    def __init__(
        self, runs: list[dict[str, Any]], jobs: dict[int, Any]
    ) -> None:
        self.runs, self.jobs = runs, jobs
        self.paths: list[str] = []

    def collection(
        self, repo: str, path: str, key: str
    ) -> list[dict[str, Any]]:
        """Return the runs or one run's jobs."""
        assert repo == REPO
        self.paths.append(path)
        if key == "workflow_runs":
            return self.runs
        run_id = int(path.split("/")[2])
        return self.jobs[run_id]


def write_config(tmp_path: Path, text: str = CONFIG + REGISTERED) -> Path:
    """Write one configuration file and return its path."""
    path = tmp_path / "config.yml"
    path.write_text(text, encoding="utf-8")
    return path


def pull(head_repo: str | None = REPO) -> dict[str, Any]:
    """Return the live pull request head."""
    return {"head": {"repo": {"full_name": head_repo} if head_repo else None}}


@pytest.mark.parametrize("name", READERS)
def test_lookup_takes_the_newest_bound_run(name: str, tmp_path: Path) -> None:
    """AC3: the newest run for the head wins; other heads are skipped."""
    github = RunsGitHub(
        [
            vm_run(id=499),
            vm_run(
                id=502, display_title="Self-hosted verify PR #7 " + "c" * 40
            ),
            vm_run(id=501),
        ],
        {499: [vm_job()], 501: [vm_job()]},
    )
    evidence = reader(name)["require"](
        github, REPO, lease(), pull(), write_config(tmp_path), "fast"
    )
    assert evidence["executor"]["run_id"] == 501
    query = github.paths[0]
    assert query.startswith("actions/workflows/csarc-verify.yml/runs?")
    assert "event=workflow_dispatch" in query
    assert f"head_sha={BASE}" in query
    assert "branch=dev%2Fm21-self-hosted" in query
    assert all("/502/" not in path for path in github.paths)


@pytest.mark.parametrize(
    ("github", "pull_request", "config", "message"),
    [
        (RunsGitHub([], {}), pull("fork/product"), CONFIG + REGISTERED, "fork"),
        (RunsGitHub([], {}), pull(None), CONFIG + REGISTERED, "fork"),
        (
            RunsGitHub([], {}),
            pull(),
            CONFIG + "self_hosted_runner: {}\n",
            "Register with",
        ),
        (RunsGitHub([], {}), pull(), CONFIG + REGISTERED, "no VM run"),
        (
            RunsGitHub([vm_run()], {501: [vm_job(runner_name="other")]}),
            pull(),
            CONFIG + REGISTERED,
            "runner is not",
        ),
    ],
)
def test_lookup_rejects_forks_unregistered_and_missing_runs(
    github: RunsGitHub,
    pull_request: dict[str, Any],
    config: str,
    message: str,
    tmp_path: Path,
) -> None:
    """AC4/R1: a fork, an unregistered repository, or no bound run fails."""
    with pytest.raises(RuntimeError, match=message):
        reader("template")["require"](
            github,
            REPO,
            lease(),
            pull_request,
            write_config(tmp_path, config),
            "fast",
        )


# ---------------------------------------------------------------------------
# AC4 (ADR D10/Q1): leaving self-hosted on local evidence.
# ---------------------------------------------------------------------------


def exit_git(candidate: str, changed: str) -> Callable[[list[str]], str]:
    """Return a Git stub that serves one candidate config and diff."""

    def git(args: list[str]) -> str:
        if args[0] == "show":
            assert args[1] == f"{HEAD}:.csarc/config.yml"
            return candidate
        assert args == ["diff", "--name-only", f"{BASE}...{HEAD}"]
        return changed

    return git


LEFT = CONFIG.replace(
    "verification_mode_private: self-hosted\n",
    "verification_mode_private: local\n",
).replace("self_hosted_environments:\n- dev\n- uat\n", "")
RENDER = ".csarc/config.yml\n.github/workflows/csarc-verify.yml\nAGENTS.md\n"


@pytest.mark.parametrize("name", READERS)
@pytest.mark.parametrize(
    ("case", "base", "candidate", "changed", "qualifies"),
    [
        ("leaves to local", REGISTERED, LEFT, RENDER, True),
        (
            "leaves to hosted",
            REGISTERED,
            LEFT.replace("private: local", "private: hosted"),
            RENDER,
            True,
        ),
        ("unregistered leaves", "self_hosted_runner: {}\n", LEFT, RENDER, True),
        (
            "stays self-hosted",
            REGISTERED,
            CONFIG + "self_hosted_runner: {}\n",
            RENDER,
            False,
        ),
        (
            "changes another setting",
            REGISTERED,
            LEFT.replace("public: hosted", "public: local"),
            RENDER,
            False,
        ),
        (
            "changes product code",
            REGISTERED,
            LEFT,
            RENDER + "src/app.py\n",
            False,
        ),
    ],
)
def test_only_a_pure_switch_away_leaves_on_local_evidence(
    name: str,
    case: str,
    base: str,
    candidate: str,
    changed: str,
    qualifies: bool,
    tmp_path: Path,
) -> None:
    """AC4 (Q1): only the mode switch away from self-hosted qualifies."""
    reason = reader(name)["exit_reason"](
        tmp_path,
        write_config(tmp_path, CONFIG + base),
        lease(),
        exit_git(candidate, changed),
    )
    assert bool(reason) is qualifies, case
    if qualifies:
        assert "from self-hosted to" in reason
        assert "(ADR Q1)" in reason


def test_no_exit_when_the_base_is_not_self_hosted(tmp_path: Path) -> None:
    """AC4 (Q1): a local base never takes the self-hosted exit."""
    base = write_config(tmp_path, LEFT)
    assert (
        reader("root")["exit_reason"](
            tmp_path, base, lease(), exit_git(LEFT, RENDER)
        )
        == ""
    )


# ---------------------------------------------------------------------------
# #1317 (ADR Q12): the first registration of an unregistered base.
# ---------------------------------------------------------------------------

UNREGISTERED = "self_hosted_runner: {}\n"
UAT_ONLY = CONFIG.replace("- dev\n- uat\n", "- uat\n")


@pytest.mark.parametrize("name", READERS)
@pytest.mark.parametrize(
    ("case", "base", "candidate", "changed", "qualifies"),
    [
        ("registers", CONFIG + UNREGISTERED, CONFIG + REGISTERED, RENDER, True),
        (
            "registers fewer environments",
            CONFIG + UNREGISTERED,
            UAT_ONLY + REGISTERED,
            RENDER,
            True,
        ),
        (
            "base already registered",
            CONFIG + REGISTERED,
            CONFIG + REGISTERED.replace("vm-01", "vm-02"),
            RENDER,
            False,
        ),
        (
            "stays unregistered",
            CONFIG + UNREGISTERED,
            UAT_ONLY + UNREGISTERED,
            RENDER,
            False,
        ),
        ("also leaves self-hosted", CONFIG + UNREGISTERED, LEFT, RENDER, False),
        (
            "changes another setting",
            CONFIG + UNREGISTERED,
            CONFIG.replace("public: hosted", "public: local") + REGISTERED,
            RENDER,
            False,
        ),
        (
            "changes product code",
            CONFIG + UNREGISTERED,
            CONFIG + REGISTERED,
            RENDER + "src/app.py\n",
            False,
        ),
        ("base is local", LEFT, CONFIG + REGISTERED, RENDER, False),
    ],
)
def test_only_a_first_registration_merges_on_local_evidence(
    name: str,
    case: str,
    base: str,
    candidate: str,
    changed: str,
    qualifies: bool,
    tmp_path: Path,
) -> None:
    """#1317 AC1 (Q12): only filling an empty runner qualifies."""
    reason = reader(name)["registration_reason"](
        tmp_path,
        write_config(tmp_path, base),
        lease(),
        exit_git(candidate, changed),
    )
    assert bool(reason) is qualifies, case
    if qualifies:
        assert reason == (
            "the pull request only registers self_hosted_runner vm-01 "
            f"({REGISTRATION}) on an unregistered self-hosted base (ADR Q12)"
        )


@pytest.mark.parametrize("name", READERS)
def test_registration_fails_closed_on_an_unreadable_candidate(
    name: str, tmp_path: Path
) -> None:
    """#1317 AC1: a candidate the base cannot read never qualifies."""

    def broken(args: list[str]) -> str:
        raise subprocess.CalledProcessError(128, args)

    base = write_config(tmp_path, CONFIG + UNREGISTERED)
    assert (
        reader(name)["registration_reason"](tmp_path, base, lease(), broken)
        == ""
    )


# ---------------------------------------------------------------------------
# AC3: merge snapshot, evidence trust, and trace through the lifecycle.
# ---------------------------------------------------------------------------


def use_self_hosted_mode(
    monkeypatch: pytest.MonkeyPatch,
    exit_reason: str = "",
    registration_reason: str = "",
) -> dict[str, Any]:
    """Select self-hosted with local governance and stubbed VM evidence."""
    use_local_mode(monkeypatch)
    monkeypatch.setitem(
        merge_snapshot.__globals__,
        "configured_verification_mode",
        lambda *_: "self-hosted",
    )
    monkeypatch.setitem(
        merge_snapshot.__globals__, "subject_repository_root", lambda: ROOT
    )
    evidence = reader("root")["validate_run"](
        vm_run(head_branch="main"),
        [
            vm_job(
                env="uat",
                tier="full",
                head="a" * 40,
                labels=["self-hosted", "csarc-vm-vm-01", "csarc-env-uat"],
                runner_name="csarc-vm-01-uat",
            )
        ],
        repo=REPO,
        lease=lease("main"),
        config=loaded_config(),
        required_tier="full",
    )
    sibling = MODULE["self_hosted_evidence"]
    monkeypatch.setattr(sibling, "exit_reason", lambda *_: exit_reason)
    monkeypatch.setattr(
        sibling, "registration_reason", lambda *_: registration_reason
    )
    monkeypatch.setattr(sibling, "require", lambda *_: evidence)
    return evidence


def test_self_hosted_merge_uses_vm_evidence_and_local_governance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3: VM evidence replaces local evidence; governance stays local."""
    bind_remote_lease(monkeypatch)
    evidence = use_self_hosted_mode(monkeypatch)
    snapshot = merge_snapshot(
        SingleWriterGitHub(), lease_fixture(), AUTHORIZATION_URL
    )
    assert snapshot["protection"] == "single-writer"
    assert snapshot["local_verification"] is None
    assert snapshot["self_hosted_verification"] == evidence
    assert snapshot["self_hosted_exit"] == ""
    assert snapshot["required_check_evidence"] == "self-hosted-registered"
    assert snapshot["verification_record"]["trust"] == "self-hosted-registered"
    payload, trust = MODULE["merge_evidence"](snapshot, lease_fixture())
    assert trust == "self-hosted-registered"
    assert json.loads(payload)["executor"]["triggering_actor"] == "operator"
    lines = MODULE["trace_lines"](snapshot, lease_fixture(), "pr=42")
    assert any(
        line.startswith("self-hosted-verification-trace: run=")
        for line in lines
    )


def test_self_hosted_exit_merges_on_local_evidence_with_its_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC4 (Q1): the exit records self-attested-local and why."""
    bind_remote_lease(monkeypatch)
    use_self_hosted_mode(monkeypatch, "it only leaves self-hosted (ADR Q1)")
    snapshot = merge_snapshot(
        SingleWriterGitHub(), lease_fixture(), AUTHORIZATION_URL
    )
    assert snapshot["self_hosted_verification"] is None
    assert snapshot["required_check_evidence"] == "local-self-attested"
    _payload, trust = MODULE["merge_evidence"](snapshot, lease_fixture())
    assert trust == "self-attested-local"
    lines = MODULE["trace_lines"](snapshot, lease_fixture(), "pr=42")
    assert (
        "self-hosted-exit-trace: pr=42 trust=self-attested-local because it "
        "only leaves self-hosted (ADR Q1)"
    ) in lines


def use_unregistered_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, changed: str
) -> dict[str, Any]:
    """Run the real Q1 and Q12 checks against an unregistered base."""
    bind_remote_lease(monkeypatch)
    use_self_hosted_mode(monkeypatch)
    sibling = MODULE["self_hosted_evidence"]
    base = write_config(tmp_path, CONFIG + UNREGISTERED)
    stub = exit_git(CONFIG + REGISTERED, changed)
    real = reader("root")
    for function in ("exit_reason", "registration_reason"):
        monkeypatch.setattr(
            sibling,
            function,
            lambda subject, _config, held, f=function: real[f](
                subject, base, held, stub
            ),
        )

    def no_vm(*_args: object) -> None:
        raise real["unregistered"]()

    monkeypatch.setattr(sibling, "require", no_vm)
    return real


def test_unregistered_base_merges_its_registration_pull_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#1317 AC2: lifecycle merges the registration PR on local evidence."""
    use_unregistered_base(monkeypatch, tmp_path, RENDER)
    snapshot = merge_snapshot(
        SingleWriterGitHub(), lease_fixture(), AUTHORIZATION_URL
    )
    assert snapshot["self_hosted_verification"] is None
    assert snapshot["self_hosted_exit"] == ""
    assert snapshot["required_check_evidence"] == "local-self-attested"
    _payload, trust = MODULE["merge_evidence"](snapshot, lease_fixture())
    assert trust == "self-attested-local"
    lines = MODULE["trace_lines"](snapshot, lease_fixture(), "pr=42")
    assert (
        "self-hosted-registration-trace: pr=42 trust=self-attested-local "
        "because the pull request only registers self_hosted_runner vm-01 "
        f"({REGISTRATION}) on an unregistered self-hosted base (ADR Q12)"
    ) in lines
    assert not any(line.startswith("self-hosted-exit-trace") for line in lines)


def test_unregistered_base_still_fails_closed_for_other_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#1317 AC1/R1: any other PR on an unregistered base stays blocked."""
    use_unregistered_base(monkeypatch, tmp_path, RENDER + "src/app.py\n")
    with pytest.raises(RuntimeError, match="no registered VM evidence"):
        merge_snapshot(SingleWriterGitHub(), lease_fixture(), AUTHORIZATION_URL)


@pytest.mark.parametrize("name", ["root", "template"])
def test_public_repository_never_uses_vm_evidence(
    name: str, tmp_path: Path
) -> None:
    """AC4/R1: a public repository reads its public mode, never self-hosted."""
    path = {
        "root": ROOT / "scripts/pr_lifecycle.py",
        "template": ROOT / "template/.csarc/scripts/pr_lifecycle.py",
    }[name]
    function = runpy.run_path(str(path))["configured_verification_mode"]
    (tmp_path / ".csarc").mkdir()
    (tmp_path / ".csarc/config.yml").write_text(
        CONFIG + REGISTERED, encoding="utf-8"
    )
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/csarc-verify.yml").write_text("", "utf-8")
    function.__globals__["repository_root"] = lambda: tmp_path

    class Visibility:
        def __init__(self, private: bool) -> None:
            self.private = private

        def get(self, _repo: str, _path: str) -> object:
            return {"private": self.private}

    assert function(Visibility(True), REPO) == "self-hosted"
    # Public: the mode is hosted, so the self-hosted render must re-render.
    with pytest.raises(RuntimeError, match="csarc update"):
        function(Visibility(False), REPO)
    # Self-hosted without its workflow is a render mismatch too.
    (tmp_path / ".github/workflows/csarc-verify.yml").unlink()
    with pytest.raises(RuntimeError, match="csarc update"):
        function(Visibility(True), REPO)
