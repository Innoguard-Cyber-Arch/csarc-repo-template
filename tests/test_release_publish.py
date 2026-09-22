"""Drive scripts/publish-release against a fake `gh` and a real Git fixture.

These are behavioral tests, not source-text assertions: a fake `gh` binary
backed by a small file-based store stands in for GitHub (mirroring the
pattern in tests/test_release_convergence.py), and the real
scripts/publish-release script is actually executed -- through a real Git
repository fixture, real scripts/release_bundle.py and scripts/release_policy.py
calls, and real scripts/converge-release-tag / scripts/verify-release-candidate
calls -- so the assertions are about observed outcomes (a draft Release
becomes published and immutable, a failed publish reverts to draft, a
missing merged pull request fails closed) rather than about whether
particular strings exist in the script.

Issue #589 requires this extracted script to be the single implementation
release.yml and a local/agent run both call; these tests are the regression
proof for that extraction (see tests/test_journey07_release.py for the
source-level wiring checks that release.yml and the release.yml.jinja
template both call this same script).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = "scripts/publish-release"

FAKE_GH = r"""#!/usr/bin/env bash
set -euo pipefail

state="$FIXTURE_STATE"
repo_dir="$FIXTURE_REPO"
mkdir -p "$state/releases" "$state/pulls" "$state/statuses"
mkdir -p "$state/assets-by-id"

release_meta() { echo "$state/releases/$1/meta.json"; }

if [[ "$1" == "api" ]]; then
  shift
  method=GET
  fdata=()
  path=""
  jq_filter=""
  while (($#)); do
    case "$1" in
      --method) method="$2"; shift 2 ;;
      --paginate) shift ;;
      --slurp) shift ;;
      --jq) jq_filter="$2"; shift 2 ;;
      -f) fdata+=("$2"); shift 2 ;;
      -H) shift 2 ;;
      *)
        if [[ -z "$path" ]]; then path="$1"; fi
        shift
        ;;
    esac
  done
  bare_path="${path%%\?*}"

  if [[ "$method" == "POST" && "$bare_path" == */git/refs ]]; then
    ref="" ; sha=""
    for kv in "${fdata[@]}"; do
      key="${kv%%=*}"; value="${kv#*=}"
      case "$key" in ref) ref="$value" ;; sha) sha="$value" ;; esac
    done
    tag="${ref#refs/tags/}"
    git -C "$repo_dir" tag "$tag" "$sha"
    exit 0
  fi
  if [[ "$method" == "POST" && "$bare_path" == */statuses/* ]]; then
    echo "status-posted" >>"$state/statuses/log"
    exit 0
  fi
  if [[ "$bare_path" == */git/ref/tags/* ]]; then
    tag="${bare_path##*/tags/}"
    git -C "$repo_dir" rev-parse "refs/tags/$tag^{commit}"
    exit 0
  fi
  if [[ "$bare_path" == */commits/*/pulls ]]; then
    sha="${bare_path#*/commits/}"; sha="${sha%/pulls}"
    if [[ -f "$state/pulls/by-sha-$sha.numbers" ]]; then
      if [[ -n "$jq_filter" ]]; then
        cat "$state/pulls/by-sha-$sha.numbers"
      else
        python3 - "$state/pulls" "$state/pulls/by-sha-$sha.numbers" <<'PY'
import json, pathlib, sys
pulls = pathlib.Path(sys.argv[1])
numbers = pathlib.Path(sys.argv[2]).read_text().split()
items = [
    json.loads((pulls / f"{number}.json").read_text())
    for number in numbers
]
print(json.dumps(items))
PY
      fi
    elif [[ -z "$jq_filter" ]]; then
      echo '[]'
    fi
    exit 0
  fi
  if [[ "$bare_path" =~ /pulls/([0-9]+)/files$ ]]; then
    cat "$state/pulls/${BASH_REMATCH[1]}.files.json"
    exit 0
  fi
  if [[ "$bare_path" =~ /pulls/([0-9]+)/commits$ ]]; then
    cat "$state/pulls/${BASH_REMATCH[1]}.commits.json"
    exit 0
  fi
  if [[ "$bare_path" =~ /pulls/([0-9]+)$ ]]; then
    cat "$state/pulls/${BASH_REMATCH[1]}.json"
    exit 0
  fi
  if [[ "$method" == "DELETE" && "$bare_path" == */releases/assets/* ]]; then
    rm -f "$state/assets-by-id/${bare_path##*/assets/}"
    exit 0
  fi
  if [[ "$bare_path" =~ /releases/tags/([^/]+)$ ]]; then
    tag="${BASH_REMATCH[1]}"
    assets_dir="$state/releases/$tag/assets"
    mkdir -p "$assets_dir"
    python3 - "$assets_dir" "$state" "$tag" <<'PY'
import json, os, sys
assets_dir, state, tag = sys.argv[1], sys.argv[2], sys.argv[3]
mapping = os.path.join(state, "assets-by-id")
os.makedirs(mapping, exist_ok=True)
items = []
for name in sorted(os.listdir(assets_dir)):
    asset_id = f"{tag}-{name}"
    open(os.path.join(mapping, asset_id), "w").close()
    items.append({"id": asset_id, "name": name})
print(json.dumps({"assets": items}))
PY
    exit 0
  fi
  # Issue #770: `gh api repos/{repo} --jq .id` looks up the numeric
  # repository id verify_release_attestation cross-checks against the
  # attestation's `repositoryId` predicate field below.
  if [[ "$method" == "GET" && "$bare_path" =~ ^repos/[^/]+/[^/]+$ ]]; then
    echo "$FIXTURE_REPOSITORY_ID"
    exit 0
  fi
  echo "mock gh: unhandled api path: $method $bare_path" >&2
  exit 2
fi

if [[ "$1" == "release" ]]; then
  shift
  case "$1" in
    view)
      tag="$2"; shift 2
      meta="$(release_meta "$tag")"
      [[ -f "$meta" ]] || { echo "release not found: $tag" >&2; exit 1; }
      if [[ "$*" == *"--json"* ]]; then
        python3 - "$meta" "$@" <<'PY'
import json, sys
meta = json.load(open(sys.argv[1]))
args = sys.argv[2:]
fields = args[args.index("--json") + 1].split(",")
out = {f: meta.get(f) for f in fields}
if "--jq" in args:
    key = args[args.index("--jq") + 1].lstrip(".")
    val = out.get(key)
    print(str(val).lower() if isinstance(val, bool) else val)
else:
    print(json.dumps(out))
PY
      fi
      exit 0
      ;;
    create)
      tag="$2"; shift 2
      mkdir -p "$(dirname "$(release_meta "$tag")")"
      python3 -c "
import json, sys
meta = {'isDraft': True, 'isImmutable': False, 'tagName': sys.argv[1]}
json.dump(meta, open(sys.argv[2], 'w'))
" "$tag" "$(release_meta "$tag")"
      mkdir -p "$state/releases/$tag/assets"
      exit 0
      ;;
    upload)
      tag="$2"; shift 2
      assets_dir="$state/releases/$tag/assets"
      mkdir -p "$assets_dir"
      echo "$tag" >>"$state/upload-log"
      for arg in "$@"; do
        [[ "$arg" == "--clobber" ]] && continue
        [[ -f "$arg" ]] && cp "$arg" "$assets_dir/"
      done
      exit 0
      ;;
    download)
      tag="$2"; shift 2
      dir=""
      while (($#)); do
        [[ "$1" == "--dir" ]] && { dir="$2"; shift 2; continue; }
        shift
      done
      mkdir -p "$dir"
      cp "$state/releases/$tag/assets/"* "$dir/" 2>/dev/null || true
      exit 0
      ;;
    edit)
      tag="$2"; shift 2
      meta="$(release_meta "$tag")"
      draft_false=false
      make_draft=false
      saw_latest=false
      while (($#)); do
        case "$1" in
          --draft=false) draft_false=true; shift ;;
          --draft) make_draft=true; shift ;;
          --latest) saw_latest=true; shift ;;
          *) shift ;;
        esac
      done
      echo "$tag latest=$saw_latest" >>"$FIXTURE_STATE/edit-log"
      # A real Release does not become immutable the instant it is marked
      # non-draft (see the eventual-consistency retry loop this fixture is
      # exercising); this fake models that lag as "immediately immutable
      # unless the fixture is deliberately forcing `gh release verify` to
      # keep failing", which is the one scenario these tests use this
      # divergence for: proving a failed publish reverts a still-mutable
      # Release back to draft instead of leaving it half-public.
      python3 - "$meta" "$draft_false" "$make_draft" "$FIXTURE_STATE" <<'PY'
import json, os, sys
meta_path, draft_false, make_draft, fixture_state = sys.argv[1:5]
meta = json.load(open(meta_path))
fail_marker = os.path.join(fixture_state, "force-verify-fail")
forced_failure = os.path.exists(fail_marker)
if draft_false == "true":
    meta["isDraft"] = False
    meta["isImmutable"] = not forced_failure
if make_draft == "true":
    meta["isDraft"] = True
    meta["isImmutable"] = False
json.dump(meta, open(meta_path, "w"))
PY
      exit 0
      ;;
    verify)
      tag="$2"; shift 2
      meta="$(release_meta "$tag")"
      format=""
      while (($#)); do
        case "$1" in
          --repo) shift 2 ;;
          --format) format="$2"; shift 2 ;;
          *) shift ;;
        esac
      done
      [[ -f "$FIXTURE_STATE/force-verify-fail" ]] && exit 1
      [[ -f "$meta" ]]
      if [[ "$format" == "json" ]]; then
        # Issue #770: emit the same JSON shape a real `gh release verify
        # --format json` would, built from the real bytes of whatever
        # assets are currently staged for this tag, so the real
        # verify_release_attestation/verify_release_consumption.py code
        # under test runs unmodified against it. force-verify-fail above
        # already covers "no attestation at all" (a real `gh release
        # verify` fails outright in that case, --format json or not); these
        # two markers instead let a test simulate a *present but wrong*
        # attestation.
        assets_dir="$state/releases/$tag/assets"
        commit="$(git -C "$repo_dir" rev-parse "refs/tags/$tag^{commit}")"
        signer="https://dotcom.releases.github.com"
        [[ -f "$FIXTURE_STATE/force-attestation-signer-mismatch" ]] &&
          signer="https://attacker.example.com"
        digest_mismatch=""
        [[ -f "$FIXTURE_STATE/force-attestation-digest-mismatch" ]] &&
          digest_mismatch=1
        python3 - "$assets_dir" "$GITHUB_REPOSITORY" "$FIXTURE_REPOSITORY_ID" \
          "$tag" "$commit" "$signer" "$digest_mismatch" <<'PY'
import hashlib, json, os, sys

(
    assets_dir, repository, repository_id,
    tag, commit, signer, digest_mismatch,
) = sys.argv[1:8]
purl = f"pkg:github/{repository}@{tag}"
subjects = [{"uri": purl, "digest": {"sha1": commit}}]
mismatched = False
for name in sorted(os.listdir(assets_dir)):
    path = os.path.join(assets_dir, name)
    if not os.path.isfile(path):
        continue
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if digest_mismatch and not mismatched:
        digest = "0" * 64
        mismatched = True
    subjects.append({"name": name, "digest": {"sha256": digest}})
payload = {
    "verificationResult": {
        "signature": {"certificate": {"subjectAlternativeName": signer}},
        "verifiedTimestamps": [{"type": "TimestampAuthority"}],
        "statement": {
            "predicateType": "https://in-toto.io/attestation/release/v0.2",
            "predicate": {
                "repository": repository,
                "repositoryId": repository_id,
                "tag": tag,
            },
            "subject": subjects,
        },
    }
}
print(json.dumps(payload))
PY
      fi
      exit 0
      ;;
    *)
      echo "mock gh: unsupported release subcommand: $*" >&2
      exit 2
      ;;
  esac
fi

echo "mock gh: unsupported command: $*" >&2
exit 2
"""

FAKE_SLEEP = "#!/usr/bin/env bash\nexit 0\n"


def git(*arguments: str, cwd: Path) -> str:
    """Run one Git command against the fixture repository."""
    return subprocess.run(  # noqa: S603
        ["git", *arguments],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build_repo(tmp_path: Path) -> dict[str, str]:
    """Build a minimal real Git repo with a merged release candidate commit.

    Three commits: a tagged v0.1.0 release point, ordinary "feat" work on
    top of it (the version pull request's base commit), and a candidate
    commit that bumps every governed version surface to 0.2.0 (the version
    pull request's merge commit) -- the same shape
    scripts/release_policy.py's verify-candidate-version recomputes and
    checks independently of whatever the candidate commit claims.
    """
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    for name in (
        "release_bundle.py",
        "release_policy.py",
        # release_policy.py imports these modules at load time (Issue #667
        # for stale_branch_detection, Issue #744 for release_phase).
        "stale_branch_detection.py",
        "release_phase.py",
        "release_level.py",
        "csarc_config.py",
        "sync_milestone_state.py",
        "converge-release-tag",
        "verify-release-candidate",
        "publish-release",
        # Issue #770: publish-release's post-hoc attestation check reuses
        # this module's verify_consumption() rather than reimplementing it.
        "verify_release_consumption.py",
    ):
        source = ROOT / "scripts" / name
        destination = root / "scripts" / name
        shutil.copy2(source, destination)
        if os.access(source, os.X_OK):
            destination.chmod(0o755)

    git("init", "-q", "-b", "main", cwd=root)
    git("config", "user.email", "test@example.com", cwd=root)
    git("config", "user.name", "Test", cwd=root)

    (root / "release-please-config.json").write_text(
        json.dumps(
            {
                "release-type": "simple",
                "packages": {".": {"component": "fixture"}},
            }
        ),
        encoding="utf-8",
    )
    (root / ".release-please-manifest.json").write_text(
        json.dumps({".": "0.1.0"}), encoding="utf-8"
    )
    (root / "version.txt").write_text("0.1.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.1.0] - 2026-01-01\n\n* initial\n",
        encoding="utf-8",
    )
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "chore(main): release 0.1.0", cwd=root)
    release_point_sha = git("rev-parse", "HEAD", cwd=root)
    git("tag", "v0.1.0", cwd=root)

    (root / "feature.txt").write_text("widget\n", encoding="utf-8")
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "feat: add widget", cwd=root)
    base_sha = git("rev-parse", "HEAD", cwd=root)

    (root / "version.txt").write_text("0.2.0\n", encoding="utf-8")
    (root / ".release-please-manifest.json").write_text(
        json.dumps({".": "0.2.0"}), encoding="utf-8"
    )
    changelog = root / "CHANGELOG.md"
    changelog.write_text(
        changelog.read_text(encoding="utf-8").replace(
            "# Changelog\n\n",
            "# Changelog\n\n## [0.2.0] - 2026-01-02\n\n* add widget\n\n",
        ),
        encoding="utf-8",
    )
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "chore(main): release 0.2.0", cwd=root)
    candidate_sha = git("rev-parse", "HEAD", cwd=root)

    git("remote", "add", "origin", str(root), cwd=root)

    return {
        "root": str(root),
        "release_point_sha": release_point_sha,
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
    }


def write_pull_request_fixture(
    state: Path,
    *,
    number: int,
    repo: str,
    base_sha: str,
    candidate_sha: str,
    head_ref: str = "release-please--branches--main--components--fixture",
    actor: str = "github-actions[bot]",
    committer: str = "web-flow",
    verified: bool = True,
    changed_files: tuple[str, ...] = (
        ".release-please-manifest.json",
        "CHANGELOG.md",
        "version.txt",
    ),
) -> None:
    """Write the merged-pull-request fixtures the fake `gh` serves.

    Mirrors exactly what GitHub's REST API would return for one merged
    version pull request, so scripts/verify-release-candidate's real
    validation chain (release follow-up ownership, branch name, changed
    files, and an independent version recomputation from base_sha) runs
    unmodified against this fixture.
    """
    pulls = state / "pulls"
    pulls.mkdir(parents=True, exist_ok=True)
    (pulls / f"by-sha-{candidate_sha}.numbers").write_text(
        f"{number}\n", encoding="utf-8"
    )
    (pulls / f"{number}.json").write_text(
        json.dumps(
            {
                "number": number,
                "merge_commit_sha": candidate_sha,
                "head": {
                    "sha": candidate_sha,
                    "ref": head_ref,
                    "repo": {"full_name": repo},
                },
                "base": {"sha": base_sha, "ref": "main"},
                "user": {"login": actor},
                "title": "chore(main): release 0.2.0",
            }
        ),
        encoding="utf-8",
    )
    (pulls / f"{number}.files.json").write_text(
        json.dumps([[{"filename": name} for name in changed_files]]),
        encoding="utf-8",
    )
    (pulls / f"{number}.commits.json").write_text(
        json.dumps(
            [
                [
                    {
                        "sha": candidate_sha,
                        "author": {"login": actor},
                        "committer": {"login": committer},
                        "commit": {
                            "verification": {
                                "verified": verified,
                                "reason": "valid" if verified else "unsigned",
                            }
                        },
                    }
                ]
            ]
        ),
        encoding="utf-8",
    )


def fixture_bin(tmp_path: Path, *, fake_syft: bool = True) -> Path:
    """Write the fake `gh` (and, by default, a fake `syft`) onto a PATH dir."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    gh = bindir / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    sleep = bindir / "sleep"
    sleep.write_text(FAKE_SLEEP, encoding="utf-8")
    sleep.chmod(0o755)
    if fake_syft:
        syft = bindir / "syft"
        syft.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                out=""
                args=("$@")
                for ((i = 0; i < ${#args[@]}; i++)); do
                  if [[ "${args[$i]}" == -o ]]; then
                    out="${args[$((i + 1))]#spdx-json=}"
                  fi
                done
                mkdir -p "$(dirname "$out")"
                cat > "$out" <<'JSON'
                {"spdxVersion": "SPDX-2.3", "SPDXID": "SPDXRef-DOCUMENT",
                 "creationInfo": {"creators": ["Organization: Anchore, Inc",
                                                "Tool: syft-1.50.0"]}}
                JSON
                """
            ),
            encoding="utf-8",
        )
        syft.chmod(0o755)
    return bindir


def install_fake_syft_installer(repo: Path, syft_path: Path) -> None:
    """Replace scripts/install-syft with one that returns the fake binary.

    Keeps these tests offline and fast: the real scripts/install-syft
    (exercised by manual local runs, not this suite) downloads and
    checksum-verifies the pinned Syft release over the network.
    """
    installer = repo / "scripts" / "install-syft"
    installer.write_text(
        f'#!/usr/bin/env bash\necho "{syft_path}"\n', encoding="utf-8"
    )
    installer.chmod(0o755)


def clean_environment() -> dict[str, str]:
    """Keep fixture subprocesses out of the parent coverage session."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_")
        and key not in {"COVERAGE_FILE", "COVERAGE_PROCESS_START"}
    }


FIXTURE_REPOSITORY_ID = "1340899393"


def run_publish_release(
    *arguments: str,
    repo: Path,
    bindir: Path,
    state: Path,
    force_verify_fail: bool = False,
    force_attestation_digest_mismatch: bool = False,
    force_attestation_signer_mismatch: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run the real scripts/publish-release with the fake `gh` in front.

    Pins a fresh RUNNER_TEMP per invocation under the test's own state
    directory instead of leaving it unset. On a real GitHub Actions
    runner, RUNNER_TEMP is already set for the whole job -- inheriting
    that ambient value here (via clean_environment()'s os.environ copy)
    would make unrelated calls across tests, and across stage/publish
    calls within one test, silently share the same
    $RUNNER_TEMP/release-assets directory. scripts/publish-release then
    treats stale leftover files from a previous call as "already
    prepared" and skips rebuilding them, corrupting SHA256SUMS. Locally,
    where RUNNER_TEMP is normally unset, the script's own `mktemp -d`
    fallback happens to isolate each call, which is what made this bug
    invisible outside CI.
    """
    env = clean_environment()
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["FIXTURE_STATE"] = str(state)
    env["FIXTURE_REPO"] = str(repo)
    env["FIXTURE_REPOSITORY_ID"] = FIXTURE_REPOSITORY_ID
    env["CSARC_PUBLISH_CANDIDATE_STATUS"] = "false"
    env["GH_TOKEN"] = "fixture-token"  # noqa: S105 -- fixture value, not a secret
    runner_temp = Path(tempfile.mkdtemp(dir=state.parent))
    env["RUNNER_TEMP"] = str(runner_temp)
    if force_verify_fail:
        (state / "force-verify-fail").touch()
    if force_attestation_digest_mismatch:
        (state / "force-attestation-digest-mismatch").touch()
    if force_attestation_signer_mismatch:
        (state / "force-attestation-signer-mismatch").touch()
    return subprocess.run(  # noqa: S603
        [str(repo / SCRIPT), *arguments],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.large
def test_stage_validates_and_converges_a_merged_candidate(
    tmp_path: Path,
) -> None:
    """A genuinely merged version pull request stages a tag and Release."""
    fixture = build_repo(tmp_path)
    root = Path(fixture["root"])
    state = tmp_path / "state"
    state.mkdir()
    write_pull_request_fixture(
        state,
        number=1,
        repo="acme/fixture",
        base_sha=fixture["base_sha"],
        candidate_sha=fixture["candidate_sha"],
    )
    bindir = fixture_bin(tmp_path)

    result = run_publish_release(
        "stage",
        "--repo",
        "acme/fixture",
        "--sha",
        fixture["candidate_sha"],
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )

    assert result.returncode == 0, result.stderr
    assert (
        git("rev-parse", "v0.2.0^{commit}", cwd=root)
        == fixture["candidate_sha"]
    )
    meta = json.loads((state / "releases/v0.2.0/meta.json").read_text())
    assert meta == {"isDraft": True, "isImmutable": False, "tagName": "v0.2.0"}
    assert "tag=v0.2.0" in result.stdout


@pytest.mark.large
def test_stage_accepts_an_exact_materialized_milestone_promotion(
    tmp_path: Path,
) -> None:
    """A promotion candidate publishes without a follow-up version PR."""
    fixture = build_repo(tmp_path)
    root = Path(fixture["root"])
    git("checkout", "--detach", fixture["base_sha"], cwd=root)
    git("commit", "--allow-empty", "-m", "chore: prepare promotion", cwd=root)
    bridge_sha = git("rev-parse", "HEAD", cwd=root)
    prepared = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(root / "scripts" / "release_policy.py"),
            "prepare-candidate",
            "--root",
            str(root),
            "--sha",
            bridge_sha,
            "--phase",
            "early",
        ],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert prepared.returncode == 0, prepared.stderr
    git("add", "-A", cwd=root)
    git("commit", "--amend", "--no-edit", cwd=root)
    promotion_sha = git("rev-parse", "HEAD", cwd=root)
    state = tmp_path / "state"
    state.mkdir()
    write_pull_request_fixture(
        state,
        number=14,
        repo="acme/fixture",
        base_sha=fixture["base_sha"],
        candidate_sha=promotion_sha,
        head_ref="promote/m14-final-delivery",
    )
    bindir = fixture_bin(tmp_path)

    result = run_publish_release(
        "stage",
        "--repo",
        "acme/fixture",
        "--sha",
        promotion_sha,
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )

    assert result.returncode == 0, result.stderr
    assert git("rev-parse", "v0.2.0^{commit}", cwd=root) == promotion_sha
    assert (state / "releases/v0.2.0/meta.json").is_file()


def test_stage_fails_closed_without_exactly_one_merged_pull_request(
    tmp_path: Path,
) -> None:
    """No matching merged pull request must never converge a tag or Release."""
    fixture = build_repo(tmp_path)
    root = Path(fixture["root"])
    state = tmp_path / "state"
    state.mkdir()
    # Deliberately write no pull-request fixture for this commit: the fake
    # `gh` returns an empty pulls list, matching a candidate commit GitHub
    # has no record of (a forged or stale sha).
    bindir = fixture_bin(tmp_path)

    result = run_publish_release(
        "stage",
        "--repo",
        "acme/fixture",
        "--sha",
        fixture["candidate_sha"],
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )

    assert result.returncode != 0
    assert not (state / "releases/v0.2.0").exists()
    tags = git("tag", "-l", cwd=root).splitlines()
    assert "v0.2.0" not in tags


@pytest.mark.large
def test_resolve_reports_none_draft_and_published_states(
    tmp_path: Path,
) -> None:
    """Resolve derives state from GitHub, not from a prior step's memory."""
    fixture = build_repo(tmp_path)
    root = Path(fixture["root"])
    state = tmp_path / "state"
    state.mkdir()
    bindir = fixture_bin(tmp_path)

    # No tag at all yet: an ordinary push with no release this time.
    none_result = run_publish_release(
        "resolve",
        "--repo",
        "acme/fixture",
        "--sha",
        fixture["candidate_sha"],
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert none_result.returncode == 0, none_result.stderr
    assert "state=none" in none_result.stdout

    # Stage a candidate: a tag and draft Release now exist for this commit.
    write_pull_request_fixture(
        state,
        number=1,
        repo="acme/fixture",
        base_sha=fixture["base_sha"],
        candidate_sha=fixture["candidate_sha"],
    )
    stage_result = run_publish_release(
        "stage",
        "--repo",
        "acme/fixture",
        "--sha",
        fixture["candidate_sha"],
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert stage_result.returncode == 0, stage_result.stderr

    draft_result = run_publish_release(
        "resolve",
        "--repo",
        "acme/fixture",
        "--sha",
        fixture["candidate_sha"],
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert draft_result.returncode == 0, draft_result.stderr
    assert "state=draft" in draft_result.stdout

    # Publish it, then resolve again: an already-published rerun.
    install_fake_syft_installer(root, bindir / "syft")
    git("checkout", "--detach", fixture["candidate_sha"], cwd=root)
    publish_result = run_publish_release(
        "publish",
        "--repo",
        "acme/fixture",
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert publish_result.returncode == 0, publish_result.stderr

    published_result = run_publish_release(
        "resolve",
        "--repo",
        "acme/fixture",
        "--sha",
        fixture["candidate_sha"],
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert published_result.returncode == 0, published_result.stderr
    assert "state=published" in published_result.stdout


@pytest.mark.large
def test_publish_builds_uploads_and_marks_the_release_published(
    tmp_path: Path,
) -> None:
    """A draft Release gets real artifacts, an SBOM, and becomes immutable."""
    fixture = build_repo(tmp_path)
    root = Path(fixture["root"])
    state = tmp_path / "state"
    state.mkdir()
    write_pull_request_fixture(
        state,
        number=1,
        repo="acme/fixture",
        base_sha=fixture["base_sha"],
        candidate_sha=fixture["candidate_sha"],
    )
    bindir = fixture_bin(tmp_path)
    install_fake_syft_installer(root, bindir / "syft")

    stage_result = run_publish_release(
        "stage",
        "--repo",
        "acme/fixture",
        "--sha",
        fixture["candidate_sha"],
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert stage_result.returncode == 0, stage_result.stderr

    publish_result = run_publish_release(
        "publish",
        "--repo",
        "acme/fixture",
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert publish_result.returncode == 0, publish_result.stderr

    meta = json.loads((state / "releases/v0.2.0/meta.json").read_text())
    assert meta == {"isDraft": False, "isImmutable": True, "tagName": "v0.2.0"}
    assets = {p.name for p in (state / "releases/v0.2.0/assets").iterdir()}
    assert {"sbom.spdx.json", "SHA256SUMS", "release-evidence.json"} <= assets
    assert any(name.endswith(".tar") for name in assets)
    sbom = json.loads(
        (state / "releases/v0.2.0/assets/sbom.spdx.json").read_text()
    )
    assert sbom["spdxVersion"] == "SPDX-2.3"


@pytest.mark.large
def test_publish_marks_latest_only_for_an_unsuffixed_tag(
    tmp_path: Path,
) -> None:
    """Issue #744: --latest is conditional on the tag having no phase suffix.

    A stable v0.2.0 tag gets `--latest`; an alpha/beta tag does not. The
    beta candidate is a second, separate commit whose governed surfaces
    genuinely say "0.2.0-beta.1" (release_bundle.py's own `identity()`
    independently re-verifies the tag against those files via
    verify_release_version, so a mismatched tag would fail regardless of
    what created the Release). Its tag/draft-Release is created directly
    via scripts/converge-release-tag rather than `publish-release stage`,
    because `stage`'s verify-release-candidate recomputes only a bare
    core version with no phase input (declaring a phase for an automated
    candidate is Issue #745's job, not this one) and would reject a
    phase-suffixed candidate outright -- this test is only about
    cmd_publish's --latest conditional, not about the stage step.
    """
    fixture = build_repo(tmp_path)
    root = Path(fixture["root"])
    state = tmp_path / "state"
    state.mkdir()
    write_pull_request_fixture(
        state,
        number=1,
        repo="acme/fixture",
        base_sha=fixture["base_sha"],
        candidate_sha=fixture["candidate_sha"],
    )
    bindir = fixture_bin(tmp_path)
    install_fake_syft_installer(root, bindir / "syft")

    # Stable tag: the existing, already-proven stage -> publish path.
    git("checkout", "--detach", fixture["candidate_sha"], cwd=root)
    stage_result = run_publish_release(
        "stage",
        "--repo",
        "acme/fixture",
        "--sha",
        fixture["candidate_sha"],
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert stage_result.returncode == 0, stage_result.stderr
    publish_result = run_publish_release(
        "publish",
        "--repo",
        "acme/fixture",
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert publish_result.returncode == 0, publish_result.stderr

    # Beta tag: a second commit with self-consistent "0.2.0-beta.1"
    # surfaces, staged directly via converge-release-tag.
    (root / "version.txt").write_text("0.2.0-beta.1\n", encoding="utf-8")
    (root / ".release-please-manifest.json").write_text(
        json.dumps({".": "0.2.0-beta.1"}), encoding="utf-8"
    )
    changelog = root / "CHANGELOG.md"
    changelog.write_text(
        changelog.read_text(encoding="utf-8").replace(
            "# Changelog\n\n",
            "# Changelog\n\n## [0.2.0-beta.1] - 2026-01-03\n\n* beta\n\n",
        ),
        encoding="utf-8",
    )
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "chore(main): release 0.2.0-beta.1", cwd=root)
    beta_sha = git("rev-parse", "HEAD", cwd=root)

    env = clean_environment()
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["FIXTURE_STATE"] = str(state)
    env["FIXTURE_REPO"] = str(root)
    env["GH_TOKEN"] = "fixture-token"  # noqa: S105 -- fixture value, not a secret
    converge_result = subprocess.run(  # noqa: S603
        [
            str(root / "scripts" / "converge-release-tag"),
            "--repo",
            "acme/fixture",
            "--sha",
            beta_sha,
            "--tag",
            "v0.2.0-beta.1",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert converge_result.returncode == 0, converge_result.stderr

    publish_beta_result = run_publish_release(
        "publish",
        "--repo",
        "acme/fixture",
        "--tag",
        "v0.2.0-beta.1",
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert publish_beta_result.returncode == 0, publish_beta_result.stderr

    edit_log = (state / "edit-log").read_text(encoding="utf-8").splitlines()
    by_tag = dict(line.split(" ", 1) for line in edit_log)
    assert by_tag["v0.2.0"] == "latest=true"
    assert by_tag["v0.2.0-beta.1"] == "latest=false"


@pytest.mark.large
def test_publish_reverts_a_failed_release_back_to_draft(tmp_path: Path) -> None:
    """A failed publish never leaves a half-public, still-mutable Release.

    `force_verify_fail` makes the fake `gh release verify` call fail
    outright regardless of `--format json`, which is also exactly what a
    real `gh release verify` does when no release attestation exists at
    all -- so this doubles as the Issue #770 "missing attestation"
    fail-closed scenario: `verify_release_attestation` in
    scripts/publish-release never even gets to ask
    verify_release_consumption.py about signer/digest identity, because the
    single shared `gh release verify --format json` call it depends on
    already failed.
    """
    fixture = build_repo(tmp_path)
    root = Path(fixture["root"])
    state = tmp_path / "state"
    state.mkdir()
    write_pull_request_fixture(
        state,
        number=1,
        repo="acme/fixture",
        base_sha=fixture["base_sha"],
        candidate_sha=fixture["candidate_sha"],
    )
    bindir = fixture_bin(tmp_path)
    install_fake_syft_installer(root, bindir / "syft")

    stage_result = run_publish_release(
        "stage",
        "--repo",
        "acme/fixture",
        "--sha",
        fixture["candidate_sha"],
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert stage_result.returncode == 0, stage_result.stderr

    # Force `gh release verify` to keep failing so the immutability poll
    # loop exhausts its attempts after the Release is already non-draft --
    # the exact failure window the original "Keep a failed mutable release
    # in draft" step existed to cover.
    publish_result = run_publish_release(
        "publish",
        "--repo",
        "acme/fixture",
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
        force_verify_fail=True,
    )

    assert publish_result.returncode != 0
    meta = json.loads((state / "releases/v0.2.0/meta.json").read_text())
    assert meta["isDraft"] is True


def _stage_fixture(tmp_path: Path) -> dict[str, Path]:
    """Build and stage a candidate, returning everything publish needs.

    Shared setup for the Issue #770 attestation-verification scenarios
    below: each one only differs in which `force_attestation_*` fixture
    marker `run_publish_release` is asked to set before calling `publish`.
    """
    fixture = build_repo(tmp_path)
    root = Path(fixture["root"])
    state = tmp_path / "state"
    state.mkdir()
    write_pull_request_fixture(
        state,
        number=1,
        repo="acme/fixture",
        base_sha=fixture["base_sha"],
        candidate_sha=fixture["candidate_sha"],
    )
    bindir = fixture_bin(tmp_path)
    install_fake_syft_installer(root, bindir / "syft")

    stage_result = run_publish_release(
        "stage",
        "--repo",
        "acme/fixture",
        "--sha",
        fixture["candidate_sha"],
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )
    assert stage_result.returncode == 0, stage_result.stderr
    return {"root": root, "state": state, "bindir": bindir}


@pytest.mark.large
def test_publish_fails_closed_on_an_asset_digest_mismatch(
    tmp_path: Path,
) -> None:
    """Issue #770: an asset whose bytes disagree with the attestation.

    verify_release_consumption.py's verify_consumption() is reused
    unmodified here -- this proves scripts/publish-release actually wires
    it in, not just that the function itself rejects a mismatch (already
    covered by tests/test_release_consumption.py). Unlike the "missing
    attestation" scenario above, a real attestation legitimately exists by
    this point (only its content is wrong), which in this fixture's model
    of GitHub's eventual consistency means `isImmutable` has already
    flipped true and cannot be walked back -- the same asymmetry the
    pre-existing `revert_to_draft_on_failure` guard (`if isImmutable ==
    false`) already accounts for. The check's value here is failing loudly
    and never reporting success, not undoing GitHub's own immutability.
    """
    prepared = _stage_fixture(tmp_path)

    publish_result = run_publish_release(
        "publish",
        "--repo",
        "acme/fixture",
        "--tag",
        "v0.2.0",
        repo=prepared["root"],
        bindir=prepared["bindir"],
        state=prepared["state"],
        force_attestation_digest_mismatch=True,
    )

    assert publish_result.returncode != 0
    assert "digest mismatch" in publish_result.stderr.lower()
    meta = json.loads(
        (prepared["state"] / "releases/v0.2.0/meta.json").read_text()
    )
    assert meta["isImmutable"] is True
    assert meta["isDraft"] is False


@pytest.mark.large
def test_publish_fails_closed_on_a_signer_mismatch(tmp_path: Path) -> None:
    """Issue #770: an attestation signed by an unexpected identity.

    A real `gh release verify` only accepts GitHub's own
    `https://dotcom.releases.github.com` release-service signer; this
    proves scripts/publish-release's reuse of
    verify_release_consumption.py enforces that same identity check rather
    than trusting `gh release verify`'s bare exit code alone. See the
    digest-mismatch test above for why `isDraft` stays `False` here too.
    """
    prepared = _stage_fixture(tmp_path)

    publish_result = run_publish_release(
        "publish",
        "--repo",
        "acme/fixture",
        "--tag",
        "v0.2.0",
        repo=prepared["root"],
        bindir=prepared["bindir"],
        state=prepared["state"],
        force_attestation_signer_mismatch=True,
    )

    assert publish_result.returncode != 0
    assert "signer identity" in publish_result.stderr.lower()
    meta = json.loads(
        (prepared["state"] / "releases/v0.2.0/meta.json").read_text()
    )
    assert meta["isImmutable"] is True
    assert meta["isDraft"] is False


@pytest.mark.large
def test_rerun_verify_confirms_without_rebuilding_or_reuploading(
    tmp_path: Path,
) -> None:
    """A rerun of an already-published Release only re-verifies it."""
    fixture = build_repo(tmp_path)
    root = Path(fixture["root"])
    state = tmp_path / "state"
    state.mkdir()
    write_pull_request_fixture(
        state,
        number=1,
        repo="acme/fixture",
        base_sha=fixture["base_sha"],
        candidate_sha=fixture["candidate_sha"],
    )
    bindir = fixture_bin(tmp_path)
    install_fake_syft_installer(root, bindir / "syft")

    assert (
        run_publish_release(
            "stage",
            "--repo",
            "acme/fixture",
            "--sha",
            fixture["candidate_sha"],
            "--tag",
            "v0.2.0",
            repo=root,
            bindir=bindir,
            state=state,
        ).returncode
        == 0
    )
    assert (
        run_publish_release(
            "publish",
            "--repo",
            "acme/fixture",
            "--tag",
            "v0.2.0",
            repo=root,
            bindir=bindir,
            state=state,
        ).returncode
        == 0
    )
    uploads_after_publish = (state / "upload-log").read_text().splitlines()
    assert uploads_after_publish == ["v0.2.0"]

    rerun_result = run_publish_release(
        "rerun-verify",
        "--repo",
        "acme/fixture",
        "--tag",
        "v0.2.0",
        repo=root,
        bindir=bindir,
        state=state,
    )

    assert rerun_result.returncode == 0, rerun_result.stderr
    # A rerun never re-uploads: the log gains no second "v0.2.0" entry.
    assert (state / "upload-log").read_text().splitlines() == ["v0.2.0"]
    meta = json.loads((state / "releases/v0.2.0/meta.json").read_text())
    assert meta == {"isDraft": False, "isImmutable": True, "tagName": "v0.2.0"}
