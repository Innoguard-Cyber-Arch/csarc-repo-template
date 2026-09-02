"""Drive scripts/converge-release-tag against a fake `gh` and assert outcomes.

These are behavioral tests, not source-text assertions: a fake `gh` binary
backed by a small file-based store stands in for GitHub, and the real
scripts/converge-release-tag script is actually executed against it — once
sequentially twice (a rerun or a resent event) and once via two genuinely
concurrent processes synchronized on a barrier (a true race) — so the
assertions are about the observed end state (how many tags, how many
Releases, how many `gh release create` calls actually happened), not about
whether particular guard-clause strings exist in a workflow file.
"""

from __future__ import annotations

import concurrent.futures
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "converge-release-tag"

FAKE_GH = r"""#!/usr/bin/env bash
set -euo pipefail

state="$FIXTURE_STATE"
mkdir -p "$state/tags" "$state/releases" "$state/barrier"

barrier_wait() {
  local n="${FIXTURE_BARRIER_N:-1}"
  touch "$state/barrier/$$-$RANDOM"
  local waited=0
  while true; do
    count="$(find "$state/barrier" -maxdepth 1 -type f | wc -l | tr -d ' ')"
    [[ "$count" -ge "$n" ]] && break
    waited=$((waited + 1))
    [[ "$waited" -gt 100 ]] && break
    sleep 0.05
  done
}

if [[ "$1" == "api" ]]; then
  shift
  if [[ "$1" == "--method" && "$2" == "POST" ]]; then
    shift 2
    shift # endpoint (repos/OWNER/NAME/git/refs), unused: derived from -f ref=
    ref=""
    sha=""
    while (($#)); do
      case "$1" in
        -f)
          key="${2%%=*}"
          value="${2#*=}"
          case "$key" in
            ref) ref="$value" ;;
            sha) sha="$value" ;;
          esac
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done
    tag="${ref#refs/tags/}"
    if (
      set -C
      echo "$sha" >"$state/tags/$tag"
    ) 2>/dev/null; then
      exit 0
    fi
    echo "gh: reference already exists" >&2
    exit 1
  fi
  endpoint="$1"
  tag="${endpoint##*/tags/}"
  barrier_wait
  if [[ -f "$state/tags/$tag" ]]; then
    cat "$state/tags/$tag"
    exit 0
  fi
  exit 1
fi

if [[ "$1" == "release" ]]; then
  shift
  if [[ "$1" == "view" ]]; then
    tag="$2"
    [[ -f "$state/releases/$tag" ]]
    exit $?
  fi
  if [[ "$1" == "create" ]]; then
    tag="$2"
    if (
      set -C
      echo "created" >"$state/releases/$tag"
    ) 2>/dev/null; then
      echo "$tag" >>"$state/create-log"
      exit 0
    fi
    echo "gh: release already exists" >&2
    exit 1
  fi
  echo "unsupported gh release subcommand: $*" >&2
  exit 2
fi

echo "unsupported gh command: $*" >&2
exit 2
"""


def make_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Write the fake `gh` and an isolated state directory."""
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    gh = fixture / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    state = tmp_path / "state"
    (state / "tags").mkdir(parents=True)
    (state / "releases").mkdir(parents=True)
    (state / "barrier").mkdir(parents=True)
    return fixture, state


def run_converge(
    fixture: Path,
    state: Path,
    *,
    repo: str = "acme/project",
    sha: str,
    tag: str,
    barrier_n: int = 1,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{fixture}:{env['PATH']}"
    env["FIXTURE_STATE"] = str(state)
    env["FIXTURE_BARRIER_N"] = str(barrier_n)
    return subprocess.run(  # noqa: S603
        [str(SCRIPT), "--repo", repo, "--sha", sha, "--tag", tag],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_a_resent_event_converges_to_one_tag_and_one_release(
    tmp_path: Path,
) -> None:
    """A rerun or duplicate webhook for the same SHA creates nothing twice."""
    fixture, state = make_fixture(tmp_path)
    sha = "a" * 40

    first = run_converge(fixture, state, sha=sha, tag="v1.2.3")
    assert first.returncode == 0, first.stderr
    second = run_converge(fixture, state, sha=sha, tag="v1.2.3")
    assert second.returncode == 0, second.stderr

    assert (state / "tags" / "v1.2.3").read_text(
        encoding="utf-8"
    ).strip() == sha
    assert (state / "releases" / "v1.2.3").is_file()
    create_log = state / "create-log"
    assert create_log.read_text(encoding="utf-8").splitlines() == ["v1.2.3"]


def test_a_tag_at_a_different_sha_fails_closed_without_a_second_release(
    tmp_path: Path,
) -> None:
    """Never reuse or move a same-named tag that points elsewhere."""
    fixture, state = make_fixture(tmp_path)
    (state / "tags" / "v1.2.3").write_text("b" * 40, encoding="utf-8")

    result = run_converge(fixture, state, sha="a" * 40, tag="v1.2.3")

    assert result.returncode != 0
    assert not (state / "releases" / "v1.2.3").is_file()
    assert not (state / "create-log").exists()


def test_two_genuinely_concurrent_runs_never_produce_two_releases(
    tmp_path: Path,
) -> None:
    """A real race on tag creation converges to one Release, not two.

    Both processes are synchronized on a barrier so they read "tag does not
    exist yet" at the same time, guaranteeing an actual race on the create
    call rather than a timing-dependent one. Exactly one may win; the loser
    must fail closed (not silently succeed, not create a second Release).
    """
    fixture, state = make_fixture(tmp_path)
    sha = "c" * 40

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                run_converge,
                fixture,
                state,
                sha=sha,
                tag="v9.9.9",
                barrier_n=2,
            )
            for _ in range(2)
        ]
        results = [future.result(timeout=30) for future in futures]

    outcomes = [result.returncode for result in results]
    assert outcomes.count(0) == 1, [
        (result.returncode, result.stderr) for result in results
    ]
    assert outcomes.count(0) + outcomes.count(1) == 2

    assert (state / "tags" / "v9.9.9").is_file()
    assert (state / "releases" / "v9.9.9").is_file()
    create_log = state / "create-log"
    assert create_log.read_text(encoding="utf-8").splitlines() == ["v9.9.9"]
