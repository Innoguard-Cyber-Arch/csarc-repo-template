"""Tests for trusted hosted verification execution evidence."""

from __future__ import annotations

import json
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "verification_evidence.py")
)
validate_verification_job = MODULE["validate_verification_job"]
TEMPLATE_MODULE = runpy.run_path(
    str(
        Path(__file__).parents[1]
        / "template"
        / ".csarc"
        / "scripts"
        / "verification_evidence.py"
    )
)
validate_template_verification_job = TEMPLATE_MODULE[
    "validate_verification_job"
]
CHECKER = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "check-trusted-verification")
)
resolve_merge_source = CHECKER["resolve_merge_source"]
find_reusable_evidence = CHECKER["find_reusable_evidence"]

NOW = datetime(2026, 9, 20, 12, tzinfo=UTC)
HEAD = "a" * 40
TREE = "b" * 40
BASE = "dev/m14-generated-project-fixes"
BASE_SHA = "f" * 40
LABELS = "c" * 64
ROOT_TOOLCHAIN = {
    "python-3.14",
    "uv-0.12.15",
    "pnpm-11.22.0",
    "node-24",
    "rust-1.98.0",
}


def reuse_annotation(**changes: object) -> dict[str, object]:
    """Build the structured annotation emitted by the trusted reuse step."""
    claim: dict[str, object] = {
        "schema_version": 1,
        "kind": "reuse",
        "tier": "fast",
        "scopes": "source",
        "tree": TREE,
        "command": "./scripts/verify-fast",
        "base": BASE,
        "base_sha": BASE_SHA,
        "labels": LABELS,
        "release": "beta",
        "source_run": 200,
        "source_job": 7,
        "source_check": 7,
    }
    claim.update(changes)
    return {
        "annotation_level": "notice",
        "title": "Trusted verification route evidence",
        "message": json.dumps(claim, separators=(",", ":"), sort_keys=True),
    }


def reuse_annotation_without(field: str) -> dict[str, object]:
    """Build a structured annotation with one required claim removed."""
    annotation = reuse_annotation()
    claim = json.loads(str(annotation["message"]))
    del claim[field]
    annotation["message"] = json.dumps(
        claim, separators=(",", ":"), sort_keys=True
    )
    return annotation


def sync_annotation(**changes: object) -> dict[str, object]:
    """Build the structured annotation emitted by the trusted sync step."""
    annotation = reuse_annotation(kind="sync", main="e" * 40)
    claim = json.loads(str(annotation["message"]))
    claim.update(changes)
    annotation["message"] = json.dumps(
        claim, separators=(",", ":"), sort_keys=True
    )
    return annotation


def evidence(
    *,
    tier: str = "fast",
    command: str = "./scripts/verify-fast",
    tree: str = TREE,
    completed_at: datetime = NOW - timedelta(minutes=2),
    run_id: int = 200,
    check_id: int = 7,
    reuse: tuple[int, int, int] | None = None,
    sync: tuple[str, int, int, int] | None = None,
    head: str = HEAD,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build one valid trusted run and job fixture."""
    url = f"https://github.com/owner/repo/actions/runs/{run_id}/job/{check_id}"
    check_run = {
        "id": check_id,
        "head_sha": head,
        "status": "completed",
        "conclusion": "success",
        "details_url": url,
        "output": {
            "text": (
                "Verified-locally: sha256=fake tier=full "
                "at=2099-01-01T00:00:00Z"
            )
        },
    }
    workflow_run = {
        "id": run_id,
        "run_attempt": 1,
        "head_sha": head,
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "owner/repo"},
    }
    evidence_step = (
        f"Execute trusted verification tier={tier} scopes=source "
        f"tree={tree} command={command} base={BASE} base-sha={BASE_SHA} "
        f"labels={LABELS} "
        "release=beta"
    )
    if reuse is not None:
        source_run, source_job, source_check = reuse
        evidence_step = (
            f"Reuse trusted verification tier={tier} scopes=source "
            f"tree={tree} command={command} base={BASE} base-sha={BASE_SHA} "
            f"labels={LABELS} "
            f"release=beta source-run={source_run} source-job={source_job} "
            f"source-check={source_check}"
        )
    if sync is not None:
        main_sha, source_run, source_job, source_check = sync
        evidence_step = (
            "Validate trusted clean sync tier=fast scopes=source "
            f"tree={tree} command=./scripts/verify-fast base={BASE} "
            f"base-sha={BASE_SHA} labels={LABELS} release=beta "
            f"main={main_sha} "
            f"source-run={source_run} source-job={source_job} "
            f"source-check={source_check}"
        )
    step_names = [
        "Select trusted verification plan",
        "Bind trusted verification identity",
        "Set up Python 3.14",
        "Set up uv 0.12.15",
        "Set up pnpm 11.22.0",
        "Set up Node.js 24",
        "Set up Rust 1.98.0",
        evidence_step,
    ]
    job = {
        "id": check_id,
        "run_id": run_id,
        "run_attempt": 1,
        "name": "verify",
        "head_sha": head,
        "html_url": url,
        "status": "completed",
        "conclusion": "success",
        "labels": ["ubuntu-latest"],
        "runner_id": 9,
        "runner_group_name": "GitHub Actions",
        "completed_at": completed_at.isoformat(),
        "steps": [
            {"name": name, "status": "completed", "conclusion": "success"}
            for name in step_names
        ],
    }
    return check_run, workflow_run, job


@pytest.mark.parametrize(
    ("tier", "command"),
    [
        ("docs", "./scripts/verify-fast"),
        ("fast", "./scripts/verify-fast"),
        ("full", "./scripts/verify-template.sh"),
    ],
)
def test_valid_trusted_execution_binds_all_claims(
    tier: str, command: str
) -> None:
    """A fresh GitHub-hosted job exposes the exact execution claims."""
    check_run, workflow_run, job = evidence(tier=tier, command=command)

    result = validate_verification_job(
        check_run,
        workflow_run,
        job,
        repo="owner/repo",
        head_sha=HEAD,
        tree_sha=TREE,
        now=NOW,
    )

    assert result["tier"] == tier
    assert result["tree_sha"] == TREE
    assert result["command"] == command
    assert result["base"] == BASE
    assert result["base_sha"] == BASE_SHA
    assert result["labels"] == LABELS
    assert result["release_level"] == "beta"
    assert result["reused"] is False
    assert result["toolchain"] == [
        "python-3.14",
        "uv-0.12.15",
        "pnpm-11.22.0",
        "node-24",
        "rust-1.98.0",
    ]


def test_generated_full_verifier_is_explicit() -> None:
    """Generated repositories bind their distinct full entry point."""
    check_run, workflow_run, job = evidence(
        tier="full", command="./scripts/verify"
    )
    result = validate_verification_job(
        check_run,
        workflow_run,
        job,
        repo="owner/repo",
        head_sha=HEAD,
        tree_sha=TREE,
        now=NOW,
        full_command="./scripts/verify",
    )
    assert result["command"] == "./scripts/verify"


def test_release_requires_full_tier_evidence() -> None:
    """A lower-tier PR run cannot be reused at a release boundary."""
    check_run, workflow_run, job = evidence(tier="fast")
    with pytest.raises(RuntimeError, match="tier is insufficient"):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
            required_tier="full",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("repository", {"full_name": "other/repo"}, "repository or exact head"),
        ("head_sha", "c" * 40, "repository or exact head"),
        ("run_attempt", 2, "run identity"),
    ],
)
def test_wrong_run_identity_fails_closed(
    field: str, value: object, message: str
) -> None:
    """Borrowed repository, head, and attempt identities are rejected."""
    check_run, workflow_run, job = evidence()
    workflow_run[field] = value
    with pytest.raises(RuntimeError, match=message):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("tier", "command", "tree", "message"),
    [
        ("full", "./scripts/verify-fast", TREE, "tier, scopes, or command"),
        ("fast", "./scripts/verify-fast", "c" * 40, "tree does not match"),
    ],
)
def test_wrong_command_or_tree_fails_closed(
    tier: str, command: str, tree: str, message: str
) -> None:
    """Claims must match the trusted command mapping and Git tree."""
    check_run, workflow_run, job = evidence(
        tier=tier, command=command, tree=tree
    )
    with pytest.raises(RuntimeError, match=message):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


def test_stale_evidence_fails_closed() -> None:
    """A once-valid run cannot be replayed outside the freshness window."""
    check_run, workflow_run, job = evidence(
        completed_at=NOW - timedelta(hours=24, seconds=1)
    )
    with pytest.raises(RuntimeError, match="stale"):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


def test_future_evidence_fails_closed() -> None:
    """A future completion time cannot extend the freshness window."""
    check_run, workflow_run, job = evidence(
        completed_at=NOW + timedelta(minutes=5, seconds=1)
    )
    with pytest.raises(RuntimeError, match="future"):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


def test_untrusted_runner_fails_closed() -> None:
    """A self-hosted label cannot impersonate the GitHub-hosted runner."""
    check_run, workflow_run, job = evidence()
    job["labels"] = ["self-hosted", "ubuntu-latest"]
    with pytest.raises(RuntimeError, match="untrusted runner"):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


def test_failed_execution_step_fails_closed() -> None:
    """A named execution step must itself have succeeded."""
    check_run, workflow_run, job = evidence()
    job["steps"][-1]["conclusion"] = "failure"
    with pytest.raises(
        RuntimeError, match="one execution, reuse, or sync step"
    ):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


def test_missing_toolchain_step_fails_closed() -> None:
    """A skipped setup command cannot satisfy the bound toolchain."""
    check_run, workflow_run, job = evidence()
    for step in job["steps"]:
        if step["name"] == "Set up Rust 1.98.0":
            step["conclusion"] = "skipped"
    with pytest.raises(RuntimeError, match="toolchain evidence"):
        validate_verification_job(
            check_run,
            workflow_run,
            job,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
            expected_toolchain=ROOT_TOOLCHAIN,
        )


def test_valid_reuse_retains_current_identity_and_original_freshness() -> None:
    """Keep current IDs and the direct source execution's completion time."""
    source = evidence(run_id=200, check_id=7)
    current = evidence(
        run_id=300,
        check_id=8,
        completed_at=NOW - timedelta(minutes=1),
        reuse=(200, 7, 7),
    )

    result = validate_verification_job(
        *current,
        repo="owner/repo",
        head_sha=HEAD,
        tree_sha=TREE,
        now=NOW,
        source_evidence=(*source, TREE),
    )

    assert result["run_id"] == 300
    assert result["job_id"] == 8
    assert result["check_run_id"] == 8
    assert result["reused"] is True
    assert result["source_run_id"] == 200
    assert result["completed_at"] == (NOW - timedelta(minutes=2)).isoformat()


def test_fixed_reuse_step_reads_structured_annotation() -> None:
    """GitHub may leave expressions literal in names; use the annotation."""
    source = evidence(run_id=200, check_id=7)
    current = evidence(run_id=300, check_id=8, reuse=(200, 7, 7))
    current[2]["steps"][-1]["name"] = "Reuse trusted verification"

    result = validate_verification_job(
        *current,
        repo="owner/repo",
        head_sha=HEAD,
        tree_sha=TREE,
        now=NOW,
        source_evidence=(*source, TREE),
        annotations=[reuse_annotation()],
    )

    assert result["reused"] is True
    assert result["source_run_id"] == 200
    assert result["source_job_id"] == 7
    assert result["source_check_run_id"] == 7


def test_template_consumer_reads_the_same_structured_annotation() -> None:
    """The generated-project consumer accepts its path-specific claim."""
    source = evidence(run_id=200, check_id=7)
    current = evidence(run_id=300, check_id=8, reuse=(200, 7, 7))
    for job in (source[2], current[2]):
        job["steps"][-1]["name"] = job["steps"][-1]["name"].replace(
            "./scripts/", "./.csarc/scripts/"
        )
    current[2]["steps"][-1]["name"] = "Reuse trusted verification"

    result = validate_template_verification_job(
        *current,
        repo="owner/repo",
        head_sha=HEAD,
        tree_sha=TREE,
        now=NOW,
        source_evidence=(*source, TREE),
        annotations=[reuse_annotation(command="./.csarc/scripts/verify-fast")],
        full_command="./.csarc/scripts/verify",
    )

    assert result["reused"] is True
    assert result["source_run_id"] == 200


def test_template_consumer_reads_structured_sync_annotation() -> None:
    """The generated-project consumer binds the clean-sync main SHA."""
    source = evidence(
        tier="full",
        command="./scripts/verify-template.sh",
        run_id=200,
        check_id=7,
        head="e" * 40,
    )
    current = evidence(
        run_id=300,
        check_id=8,
        sync=("e" * 40, 200, 7, 7),
    )
    for job in (source[2], current[2]):
        job["steps"][-1]["name"] = (
            job["steps"][-1]["name"]
            .replace("./scripts/verify-template.sh", "./.csarc/scripts/verify")
            .replace("./scripts/verify-fast", "./.csarc/scripts/verify-fast")
        )
    current[2]["steps"][-1]["name"] = "Validate trusted clean sync"

    result = validate_template_verification_job(
        *current,
        repo="owner/repo",
        head_sha=HEAD,
        tree_sha=TREE,
        now=NOW,
        source_evidence=(*source, TREE),
        annotations=[sync_annotation(command="./.csarc/scripts/verify-fast")],
        full_command="./.csarc/scripts/verify",
    )

    assert result["sync_main_sha"] == "e" * 40
    assert result["source_run_id"] == 200


def test_literal_reuse_step_expression_fails_closed() -> None:
    """Never interpret GitHub's unexpanded dynamic display-name as evidence."""
    source = evidence(run_id=200, check_id=7)
    current = evidence(run_id=300, check_id=8, reuse=(200, 7, 7))
    current[2]["steps"][-1]["name"] = (
        "Reuse trusted verification tier=${{ steps.effective.outputs.suite }} "
        "scopes=${{ steps.plan.outputs.scopes }}"
    )

    with pytest.raises(RuntimeError, match="evidence is malformed"):
        validate_verification_job(
            *current,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
            source_evidence=(*source, TREE),
        )


@pytest.mark.parametrize(
    ("annotations", "message"),
    [
        ([], "annotation is missing"),
        ([reuse_annotation(), reuse_annotation()], "annotation is missing"),
        (
            [
                {
                    **reuse_annotation(),
                    "message": "not-json",
                }
            ],
            "annotation is malformed",
        ),
        ([reuse_annotation_without("source_job")], "annotation is malformed"),
        ([reuse_annotation(source_check=9)], "source identity"),
        ([reuse_annotation(tree="d" * 40)], "tree does not match"),
        (
            [reuse_annotation(tier="full")],
            "tier, scopes, or command is invalid",
        ),
        ([reuse_annotation(base="main")], "route does not match"),
    ],
)
def test_structured_reuse_annotation_fails_closed(
    annotations: list[dict[str, object]], message: str
) -> None:
    """Malformed or mismatched structured claims never authorize reuse."""
    source = evidence(run_id=200, check_id=7)
    current = evidence(run_id=300, check_id=8, reuse=(200, 7, 7))
    current[2]["steps"][-1]["name"] = "Reuse trusted verification"

    with pytest.raises(RuntimeError, match=message):
        validate_verification_job(
            *current,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
            source_evidence=(*source, TREE),
            annotations=annotations,
        )


def test_clean_sync_uses_one_direct_full_source_execution() -> None:
    """A clean sync binds its own head to one fresh full main execution."""
    source = evidence(
        tier="full",
        command="./scripts/verify-template.sh",
        run_id=200,
        check_id=7,
        head="e" * 40,
    )
    current = evidence(
        run_id=300,
        check_id=8,
        sync=("e" * 40, 200, 7, 7),
    )

    result = validate_verification_job(
        *current,
        repo="owner/repo",
        head_sha=HEAD,
        tree_sha=TREE,
        now=NOW,
        source_evidence=(*source, TREE),
    )

    assert result["reused"] is True
    assert result["sync_main_sha"] == "e" * 40
    assert result["source_run_id"] == 200


@pytest.mark.parametrize(
    ("main_tree", "accepted"),
    [(TREE, True), ("d" * 40, False), (None, False)],
)
def test_clean_sync_accepts_only_a_tree_equal_squash_source(
    main_tree: str | None, accepted: bool
) -> None:
    """Cite the squash-merged source PR only when main has its exact tree."""
    source_head = "9" * 40
    source = evidence(
        tier="full",
        command="./scripts/verify-template.sh",
        run_id=200,
        check_id=7,
        head=source_head,
    )
    current = evidence(
        run_id=300,
        check_id=8,
        sync=("e" * 40, 200, 7, 7),
    )
    requested: list[str] = []

    def commit_tree(sha: str) -> str | None:
        requested.append(sha)
        return main_tree

    def validate(**changes: object) -> dict[str, object]:
        return validate_verification_job(
            *current,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
            source_evidence=(*source, TREE),
            **changes,
        )

    with pytest.raises(RuntimeError, match="main does not match"):
        validate()
    if accepted:
        result = validate(commit_tree=commit_tree)
        assert result["sync_main_sha"] == "e" * 40
        assert result["source_run_id"] == 200
    else:
        with pytest.raises(RuntimeError, match="main does not match"):
            validate(commit_tree=commit_tree)
    assert requested == ["e" * 40]


def test_fixed_sync_step_reads_structured_annotation() -> None:
    """A clean sync reads its main and source identities from one annotation."""
    source = evidence(
        tier="full",
        command="./scripts/verify-template.sh",
        run_id=200,
        check_id=7,
        head="e" * 40,
    )
    current = evidence(
        run_id=300,
        check_id=8,
        sync=("e" * 40, 200, 7, 7),
    )
    current[2]["steps"][-1]["name"] = "Validate trusted clean sync"

    result = validate_verification_job(
        *current,
        repo="owner/repo",
        head_sha=HEAD,
        tree_sha=TREE,
        now=NOW,
        source_evidence=(*source, TREE),
        annotations=[sync_annotation()],
    )

    assert result["sync_main_sha"] == "e" * 40
    assert result["source_run_id"] == 200


def test_literal_sync_step_expression_fails_closed() -> None:
    """Never interpret GitHub's unexpanded sync display-name as evidence."""
    current = evidence(
        run_id=300,
        check_id=8,
        sync=("e" * 40, 200, 7, 7),
    )
    current[2]["steps"][-1]["name"] = (
        "Validate trusted clean sync tier=fast "
        "scopes=${{ steps.plan.outputs.scopes }}"
    )

    with pytest.raises(RuntimeError, match="evidence is malformed"):
        validate_verification_job(
            *current,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("annotations", "message"),
    [
        ([], "annotation is missing"),
        ([sync_annotation(), sync_annotation()], "annotation is missing"),
        ([sync_annotation(main="f" * 40)], "main does not match"),
        ([sync_annotation(source_check=9)], "source identity"),
    ],
)
def test_structured_sync_annotation_fails_closed(
    annotations: list[dict[str, object]], message: str
) -> None:
    """Missing, duplicate, or mismatched sync claims never authorize reuse."""
    source = evidence(
        tier="full",
        command="./scripts/verify-template.sh",
        run_id=200,
        check_id=7,
        head="e" * 40,
    )
    current = evidence(
        run_id=300,
        check_id=8,
        sync=("e" * 40, 200, 7, 7),
    )
    current[2]["steps"][-1]["name"] = "Validate trusted clean sync"

    with pytest.raises(RuntimeError, match=message):
        validate_verification_job(
            *current,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
            source_evidence=(*source, TREE),
            annotations=annotations,
        )


def test_reuse_chain_fails_closed() -> None:
    """One reused job cannot become another reuse job's source."""
    source = evidence(run_id=200, check_id=7, reuse=(100, 6, 6))
    current = evidence(run_id=300, check_id=8, reuse=(200, 7, 7))

    with pytest.raises(RuntimeError, match="direct execution source"):
        validate_verification_job(
            *current,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
            source_evidence=(*source, TREE),
        )


@pytest.mark.parametrize(
    "mutation",
    ["source-id", "route", "head", "tree", "freshness"],
)
def test_reuse_source_mismatch_fails_closed(mutation: str) -> None:
    """Reuse never crosses identity, route, tree, or freshness boundaries."""
    source = evidence(run_id=200, check_id=7)
    current = evidence(run_id=300, check_id=8, reuse=(200, 7, 7))
    if mutation == "source-id":
        current[2]["steps"][-1]["name"] = current[2]["steps"][-1][
            "name"
        ].replace("source-check=7", "source-check=9")
    elif mutation == "route":
        source[2]["steps"][-1]["name"] = source[2]["steps"][-1]["name"].replace(
            f"base={BASE}", "base=main"
        )
    elif mutation == "head":
        source[0]["head_sha"] = "d" * 40
    elif mutation == "tree":
        source[2]["steps"][-1]["name"] = source[2]["steps"][-1]["name"].replace(
            f"tree={TREE}", f"tree={'d' * 40}"
        )
    else:
        source[2]["completed_at"] = (
            NOW - timedelta(hours=24, seconds=1)
        ).isoformat()

    with pytest.raises(RuntimeError):
        validate_verification_job(
            *current,
            repo="owner/repo",
            head_sha=HEAD,
            tree_sha=TREE,
            now=NOW,
            source_evidence=(*source, TREE),
        )


class ReuseGitHub:
    """Expose candidate check rows to the reusable-evidence selector."""

    def collection(
        self, _repo: str, _path: str, key: str
    ) -> list[dict[str, Any]]:
        assert key == "check_runs"
        return [{"id": 8}, {"id": 7}]


def test_reusable_selector_uses_only_an_original_identical_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metadata reruns select the newest matching execution, never a reuse."""

    def validate(
        _github: object,
        _repo: str,
        _head: str,
        _app: int,
        **kwargs: object,
    ) -> dict[str, object]:
        check = kwargs["check_runs"]
        assert isinstance(check, list)
        check_id = check[0]["id"]
        return {
            "check_run_id": check_id,
            "run_id": 300 if check_id == 8 else 200,
            "job_id": check_id,
            "tier": "fast",
            "scopes": ["source"],
            "command": "./scripts/verify-fast",
            "base": BASE,
            "base_sha": BASE_SHA,
            "labels": LABELS,
            "release_level": "beta",
            "reused": check_id == 8,
        }

    monkeypatch.setitem(
        find_reusable_evidence.__globals__,
        "require_trusted_verification",
        validate,
    )
    result = find_reusable_evidence(
        ReuseGitHub(),
        "owner/repo",
        HEAD,
        tier="fast",
        scopes="source",
        command="./scripts/verify-fast",
        base=BASE,
        base_sha=BASE_SHA,
        labels=LABELS,
        release_level="beta",
        exclude_run_id=300,
        max_age_hours=24,
    )

    assert result is not None
    assert result["run_id"] == 200


class MergeSourceGitHub:
    """Serve the exact source and tree identity needed by release reuse."""

    def __init__(self, source_tree: str = TREE, base: str = "main") -> None:
        self.source_tree = source_tree
        self.base = base

    def pages(self, _repo: str, _path: str) -> list[dict[str, Any]]:
        return [
            {
                "merged_at": NOW.isoformat(),
                "merge_commit_sha": "c" * 40,
                "base": {"ref": self.base},
                "head": {"sha": HEAD},
            }
        ]

    def get(self, _repo: str, path: str) -> dict[str, Any]:
        if path == f"git/commits/{'c' * 40}":
            return {"tree": {"sha": TREE}}
        if path == f"git/commits/{HEAD}":
            return {"tree": {"sha": self.source_tree}}
        raise AssertionError(path)


def test_release_reuse_requires_the_exact_merged_tree() -> None:
    """A squash result can reuse evidence only when its tree is identical."""
    assert (
        resolve_merge_source(MergeSourceGitHub(), "owner/repo", "c" * 40)
        == HEAD
    )
    with pytest.raises(RuntimeError, match="main tree does not match"):
        resolve_merge_source(
            MergeSourceGitHub("d" * 40), "owner/repo", "c" * 40
        )


def test_release_reuse_accepts_the_actual_delivery_branch() -> None:
    """A delivery-branch release reuses its own source PR, not only main's."""
    github = MergeSourceGitHub(base="dev/m17-cost")
    assert (
        resolve_merge_source(github, "owner/repo", "c" * 40, "dev/m17-cost")
        == HEAD
    )
    with pytest.raises(RuntimeError, match="merged-main source PR"):
        resolve_merge_source(github, "owner/repo", "c" * 40)
