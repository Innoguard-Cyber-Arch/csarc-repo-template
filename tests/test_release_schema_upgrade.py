"""New settings from a template upgrade get a release inventory (#1239).

The trusted base reads a candidate configuration with its own schema. When
a template upgrade adds a setting the base does not know, the base builds a
read-only inventory of those settings against the schema tables of the
immutable stable release `_commit` names, parsed with `ast` from that
release commit and never executed, only on the governance-switch route
(docs/adr/dry-run-inventory-before-action.md). Anything unexpected fails
closed and prints the inventory. Each contract runs against the root and
the template copy of the shared executor.
"""

from __future__ import annotations

import base64
import json
import os
import runpy
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from test_base_policy import (
    COPIES,
    REPO_ROOT,
    commit_all,
    config_text,
    git,
    write_config,
)

TAG = "v9.1.0"
COMMIT = "a" * 40
REPO = "repos/Innoguard-Cyber-Arch/csarc-repo-template"
SCHEMA_PATH = "template/.csarc/scripts/csarc_config.py"
CURRENT_SCHEMA = (REPO_ROOT / "scripts" / "csarc_config.py").read_text(
    encoding="utf-8"
)
ANCHOR = '    "single_writer_merger": (KIND_TEXT, ()),\n'
# The released reader declares one setting the trusted base does not.
NEWER_SCHEMA = CURRENT_SCHEMA.replace(
    ANCHOR, ANCHOR + '    "future_flag": (KIND_BOOL, ()),\n', 1
)
LABELS = {"governance-switch"}
NEXT_STEPS = (
    "Add the governance-switch label, confirm the upgrade targets a "
    "published stable CSARC release, or merge by hand."
)


def endpoints(
    schema: str = NEWER_SCHEMA, *, commit: str = COMMIT, **release: object
) -> dict[str, object]:
    """Return the GitHub API objects of one published release."""
    return {
        f"{REPO}/releases/tags/{TAG}": {
            "tag_name": TAG,
            "draft": False,
            "prerelease": False,
            "published_at": "2026-10-23T00:00:00Z",
            "immutable": True,
            **release,
        },
        f"{REPO}/git/ref/tags/{TAG}": {
            "object": {"type": "tag", "sha": "b" * 40}
        },
        f"{REPO}/git/tags/{'b' * 40}": {
            "object": {"type": "commit", "sha": commit}
        },
        f"{REPO}/contents/{SCHEMA_PATH}?ref={COMMIT}": {
            "content": base64.b64encode(schema.encode()).decode()
        },
    }


def api_from(payloads: dict[str, object]) -> Callable[[str], object]:
    """Serve fixed GitHub objects; any other endpoint is unavailable."""

    def read(endpoint: str) -> object:
        if endpoint not in payloads:
            raise RuntimeError(f"GitHub cannot read {endpoint}")
        return payloads[endpoint]

    return read


@pytest.fixture(params=sorted(COPIES), name="executor")
def executor_fixture(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Load one shipped copy of the base-policy module."""
    return runpy.run_path(str(COPIES[request.param]))


def upgraded(path: Path, value: object = True, **overrides: object) -> Path:
    """Write a candidate that an upgrade gave one new setting."""
    return write_config(
        path,
        f"_commit: {COMMIT}\n" + config_text(future_flag=value, **overrides),
    )


def saved(tmp_path: Path, tag: object = TAG) -> Path:
    """Write the candidate provenance that names one release tag."""
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps({"release_tag": tag}), encoding="utf-8")
    return path


def test_release_inventory_reads_new_settings(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """AC1/AC3: label + stable immutable release judge the new setting."""
    path = upgraded(tmp_path / "candidate.yml")
    config, source = executor["read_candidate_config"](
        path, LABELS, saved(tmp_path), api_from(endpoints())
    )
    assert config["future_flag"] is True
    assert source == f"release:{TAG}"
    base = executor["read_config"](write_config(tmp_path / "b", config_text()))
    route = executor["classify_route"]([], base, config)
    assert route.route == "ordinary"


@pytest.mark.parametrize(
    ("labels", "tag", "payloads", "why", "item"),
    [
        (
            set(),
            TAG,
            endpoints(),
            "the PR has no governance-switch label",
            "future_flag not checked",
        ),
        (
            LABELS,
            TAG,
            endpoints(prerelease=True),
            "not a published immutable",
            "future_flag not checked",
        ),
        (
            LABELS,
            TAG,
            endpoints(draft=True),
            "not a published immutable",
            "future_flag not checked",
        ),
        (
            LABELS,
            TAG,
            endpoints(immutable=False),
            "not a published immutable",
            "future_flag not checked",
        ),
        (LABELS, TAG, {}, "GitHub cannot read", "future_flag not checked"),
        (
            LABELS,
            "v9.1.0-beta.1",
            endpoints(),
            "not a stable CSARC release",
            "future_flag not checked",
        ),
        (
            LABELS,
            None,
            endpoints(),
            "not a stable CSARC release",
            "future_flag not checked",
        ),
        (
            LABELS,
            TAG,
            endpoints(commit="c" * 40),
            "does not point to _commit",
            "future_flag not checked",
        ),
        (
            LABELS,
            TAG,
            endpoints(CURRENT_SCHEMA),
            "the inventory has unexpected items",
            f"future_flag unknown to {TAG}",
        ),
    ],
)
def test_unverifiable_new_settings_fail_closed(
    executor: dict[str, Any],
    tmp_path: Path,
    labels: set[str],
    tag: object,
    payloads: dict[str, object],
    why: str,
    item: str,
) -> None:
    """AC2/AC3: a missing label or unverifiable release stays closed."""
    path = upgraded(tmp_path / "candidate.yml")
    with pytest.raises(ValueError, match="come from a newer CSARC") as error:
        executor["read_candidate_config"](
            path, labels, saved(tmp_path, tag), api_from(payloads)
        )
    message = str(error.value)
    assert why in message
    assert f"Inventory: {item}. " in message
    assert message.endswith(NEXT_STEPS)


def test_wrong_value_shape_prints_the_inventory(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """A value that does not match the released kind stops with the list."""
    path = upgraded(tmp_path / "candidate.yml", value="yes")
    with pytest.raises(ValueError) as error:
        executor["read_candidate_config"](
            path, LABELS, saved(tmp_path), api_from(endpoints())
        )
    assert (
        f"Inventory: future_flag bool from {TAG}, value does not match. "
        in str(error.value)
    )


def test_release_schema_code_is_never_executed(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """The release reader is parsed with `ast`; its code never runs."""
    marker = tmp_path / "executed"
    hostile = (
        f"open({str(marker)!r}, 'w').write('ran')\n"
        "raise SystemExit('ran')\n" + NEWER_SCHEMA
    )
    path = upgraded(tmp_path / "candidate.yml")
    config, source = executor["read_candidate_config"](
        path, LABELS, saved(tmp_path), api_from(endpoints(hostile))
    )
    assert (config["future_flag"], source) == (True, f"release:{TAG}")
    assert not marker.exists()
    assert "exec(" not in COPIES["root"].read_text(encoding="utf-8")


def test_existing_settings_never_ask_github(
    executor: dict[str, Any], tmp_path: Path
) -> None:
    """AC4: settings this base knows keep the unchanged base path."""
    path = write_config(tmp_path / "candidate.yml", config_text())
    config, source = executor["read_candidate_config"](
        path, set(), None, api_from({})
    )
    assert (source, config["admin_bypass"]) == ("base", "off")
    invalid = write_config(tmp_path / "bad.yml", config_text(admin_bypass="x"))
    with pytest.raises(ValueError, match="admin_bypass is 'x'"):
        executor["read_candidate_config"](
            invalid, LABELS, saved(tmp_path), api_from({})
        )


def stub_gh(tmp_path: Path, payloads: dict[str, object]) -> dict[str, str]:
    """Put a `gh` on PATH that serves fixed API objects."""
    data = tmp_path / "gh.json"
    data.write_text(json.dumps(payloads), encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gh = fake_bin / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"data = json.load(open({str(data)!r}))\n"
        "if sys.argv[2] not in data:\n"
        "    sys.exit(1)\n"
        "print(json.dumps(data[sys.argv[2]]))\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    return {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}


@pytest.mark.parametrize("copy", sorted(COPIES))
def test_hosted_route_reads_the_release_schema(
    tmp_path: Path, copy: str
) -> None:
    """The hosted PR policy reader takes the same narrow exception."""
    base = write_config(tmp_path / "base.yml", config_text())
    candidate = upgraded(tmp_path / "candidate.yml")
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps({"release_tag": TAG}), "utf-8")
    environment = stub_gh(tmp_path, endpoints())

    def route(labels: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - repository-owned entry point
            [
                sys.executable,
                str(COPIES[copy]),
                "route",
                "--base-config",
                str(base),
                "--candidate-config",
                str(candidate),
                "--candidate-provenance",
                str(provenance),
                "--labels",
                labels,
                "--enforce",
            ],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    accepted = route("governance-switch")
    assert accepted.returncode == 0, accepted.stderr
    assert f"schema_source=release:{TAG}" in accepted.stdout
    refused = route("")
    assert refused.returncode == 1
    assert refused.stderr.startswith(
        "ERROR: Trusted base cannot read the configuration: settings "
        "future_flag come from a newer CSARC template release"
    )
    assert "Inventory: future_flag not checked." in refused.stderr


@pytest.mark.parametrize("layout", ["root", "template"])
def test_local_lifecycle_traces_the_release_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: str
) -> None:
    """AC3: the merge snapshot and trace name the release schema."""
    source = REPO_ROOT / (
        "scripts" if layout == "root" else "template/.csarc/scripts"
    )
    lifecycle = runpy.run_path(str(source / "pr_lifecycle.py"))
    repo = tmp_path / "generated"
    scripts = repo / ".csarc" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("trusted_executor.py", "csarc_config.py"):
        shutil.copy2(source / name, scripts / name)
    write_config(repo / ".csarc" / "config.yml", config_text())
    git(repo, "init", "-q", "-b", "main")
    base_sha = commit_all(repo, "base")
    upgraded(repo / ".csarc" / "config.yml")
    (repo / ".csarc" / "provenance.json").write_text(
        json.dumps({"release_tag": TAG}), "utf-8"
    )
    head_sha = commit_all(repo, "upgrade")
    monkeypatch.setenv("PATH", stub_gh(tmp_path, endpoints())["PATH"])
    decide = lifecycle["base_policy_decision"]
    monkeypatch.setitem(decide.__globals__, "repository_root", lambda: repo)
    monkeypatch.chdir(repo)
    (repo / ".csarc" / "config.yml").write_text(
        git(repo, "show", f"{base_sha}:.csarc/config.yml") + "\n", "utf-8"
    )
    lease = {"base_sha": base_sha, "head_sha": head_sha, "base_ref": "main"}
    pull = {"head": {"ref": "fix/1239-upgrade"}}
    decision = decide(lease, pull, LABELS)
    assert decision["schema_source"] == f"release:{TAG}"
    assert decision["route"] == "ordinary"
    lines = lifecycle["trace_lines"](
        {"schema_source": decision["schema_source"]},
        {"actor": "agent", "head_sha": head_sha},
        "suffix",
    )
    assert lines == [f"schema-trace: schema_source=release:{TAG} suffix"]
    assert lifecycle["trace_lines"]({"schema_source": "base"}, {}, "s") == []
