#!/usr/bin/env python3
"""One-time migration of the four retired public alpha Releases (#918)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import release_bundle, release_policy
from scripts.render_release_prompt import render as render_release_prompt
from scripts.verify_release_consumption import (
    VerificationError,
    verify_consumption,
)

REPOSITORY = "Innoguard-Cyber-Arch/csarc-repo-template"


@dataclass(frozen=True)
class RetiredRelease:
    """Identify one immutable historical Release and its replacement."""

    source_tag: str
    replacement_tag: str
    commit: str


RETIRED_RELEASES = (
    RetiredRelease(
        "v0.18.0-alpha.1",
        "v0.18.0-beta.1",
        "01d94d4263233ffb6d44764a89543ee293ff536c",
    ),
    RetiredRelease(
        "v0.19.0-alpha.1",
        "v0.19.0-beta.1",
        "1ac74b3d8fe80aa03118c7e52e04b00fb5778096",
    ),
    RetiredRelease(
        "v0.20.0-alpha.1",
        "v0.20.0-beta.1",
        "bb5d1d7b819cab826bd11c9a59ce76d4f262ee33",
    ),
    RetiredRelease(
        "v0.21.0-alpha.1",
        "v0.21.0-beta.1",
        "e57c90d26261d05f3be422c64c838ebfc026b1eb",
    ),
)


class MigrationError(RuntimeError):
    """A historical release cannot be migrated without losing evidence."""


Run = Callable[..., subprocess.CompletedProcess[str]]


def run_command(
    arguments: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one bounded command without invoking a shell."""
    return subprocess.run(  # noqa: S603
        list(arguments),
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def gh_json(
    arguments: Sequence[str],
    *,
    root: Path,
    run: Run = run_command,
    optional: bool = False,
) -> object:
    """Run gh and decode one JSON response."""
    result = run(["gh", *arguments], cwd=root, check=not optional)
    if optional and result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MigrationError("GitHub returned invalid JSON") from error


def release_identity_errors(
    release: Mapping[str, object] | None,
    item: RetiredRelease,
    *,
    replacement: bool,
) -> list[str]:
    """Return exact identity failures for a source or replacement Release."""
    label = item.replacement_tag if replacement else item.source_tag
    if release is None:
        return [f"{label}: Release is missing"]
    errors: list[str] = []
    expected_tag = item.replacement_tag if replacement else item.source_tag
    expected_prerelease = True
    expected = {
        "tagName": expected_tag,
        "targetCommitish": item.commit,
        "isDraft": False,
        "isPrerelease": expected_prerelease,
        "isImmutable": True,
    }
    for key, value in expected.items():
        if release.get(key) != value:
            errors.append(
                f"{label}: {key}={release.get(key)!r}, expected {value!r}"
            )
    if release.get("tagCommit") != item.commit:
        errors.append(f"{label}: tag does not resolve to {item.commit}")
    if release.get("attestationVerified") is not True:
        errors.append(f"{label}: downloaded assets lack verified attestation")
    assets = release.get("assets")
    if not isinstance(assets, list) or not assets:
        errors.append(f"{label}: Release has no assets")
    return errors


def plan_identity_errors(plan: Mapping[str, object]) -> list[str]:
    """Require the saved plan to name only the four exact historical tags."""
    errors: list[str] = []
    if plan.get("schemaVersion") != 1 or plan.get("repository") != REPOSITORY:
        return ["migration plan identity is invalid"]
    records = plan.get("releases")
    if not isinstance(records, list) or len(records) != len(RETIRED_RELEASES):
        return ["migration plan does not contain the exact retired set"]
    planned = {
        str(record.get("sourceTag")): record
        for record in records
        if isinstance(record, dict)
    }
    for item in RETIRED_RELEASES:
        record = planned.get(item.source_tag)
        if record is None:
            errors.append(f"{item.source_tag}: missing from migration plan")
            continue
        if record.get("replacementTag") != item.replacement_tag:
            errors.append(f"{item.source_tag}: replacement changed since plan")
        if record.get("commit") != item.commit:
            errors.append(f"{item.source_tag}: commit changed since plan")
    return errors


def deletion_errors(
    plan: Mapping[str, object],
    replacements: Mapping[str, Mapping[str, object]],
) -> list[str]:
    """Fail closed unless every replacement is ready before any deletion."""
    errors = plan_identity_errors(plan)
    if errors:
        return errors
    for item in RETIRED_RELEASES:
        errors.extend(
            release_identity_errors(
                replacements.get(item.replacement_tag),
                item,
                replacement=True,
            )
        )
    return errors


def _release_json(
    repo: str,
    tag: str,
    root: Path,
    *,
    run: Run,
) -> dict[str, object] | None:
    payload = gh_json(
        [
            "release",
            "view",
            tag,
            "--repo",
            repo,
            "--json",
            (
                "tagName,targetCommitish,isDraft,isPrerelease,isImmutable,"
                "publishedAt,url,assets"
            ),
        ],
        root=root,
        run=run,
        optional=True,
    )
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise MigrationError(f"{tag}: invalid Release response")
    return payload


def _tag_commit(
    repo: str,
    tag: str,
    root: Path,
    *,
    run: Run,
) -> str | None:
    payload = gh_json(
        ["api", f"repos/{repo}/commits/{tag}"],
        root=root,
        run=run,
        optional=True,
    )
    return str(payload.get("sha")) if isinstance(payload, dict) else None


def _verify_assets(
    repo: str,
    tag: str,
    commit: str,
    root: Path,
    assets: Sequence[Mapping[str, object]],
    *,
    run: Run,
) -> bool:
    repository = gh_json(["api", f"repos/{repo}"], root=root, run=run)
    if not isinstance(repository, dict) or not isinstance(
        repository.get("id"), int
    ):
        raise MigrationError("GitHub repository identity is invalid")
    repository_id = repository["id"]
    verification = gh_json(
        ["release", "verify", tag, "--repo", repo, "--format", "json"],
        root=root,
        run=run,
    )
    with tempfile.TemporaryDirectory(prefix="csarc-release-plan-") as raw:
        download = Path(raw)
        run(
            ["gh", "release", "download", tag, "--repo", repo, "--dir", raw],
            cwd=root,
        )
        try:
            for asset in assets:
                name = asset.get("name")
                if not isinstance(name, str):
                    return False
                verify_consumption(
                    verification,
                    download / name,
                    repository=repo,
                    repository_id=str(repository_id),
                    tag=tag,
                    commit=commit,
                )
        except OSError, VerificationError:
            return False
    return True


def inspect_release(
    repo: str,
    tag: str,
    commit: str,
    root: Path,
    *,
    run: Run = run_command,
) -> dict[str, object] | None:
    """Read back one Release, its tag, assets, and signed attestation."""
    release = _release_json(repo, tag, root, run=run)
    if release is None:
        return None
    raw_assets = release.get("assets")
    assets = raw_assets if isinstance(raw_assets, list) else []
    normalized_assets = [
        {
            "name": asset.get("name"),
            "digest": asset.get("digest"),
            "size": asset.get("size"),
            "downloadCount": asset.get("downloadCount"),
            "url": asset.get("url"),
        }
        for asset in assets
        if isinstance(asset, dict)
    ]
    release["assets"] = normalized_assets
    release["tagCommit"] = _tag_commit(repo, tag, root, run=run)
    release["attestationVerified"] = _verify_assets(
        repo, tag, commit, root, normalized_assets, run=run
    )
    return release


def build_plan(
    repo: str,
    root: Path,
    *,
    run: Run = run_command,
) -> dict[str, object]:
    """Build the exact, read-only migration and deletion plan."""
    records: list[dict[str, object]] = []
    errors: list[str] = []
    for item in RETIRED_RELEASES:
        source = inspect_release(
            repo, item.source_tag, item.commit, root, run=run
        )
        replacement_tag_commit = _tag_commit(
            repo, item.replacement_tag, root, run=run
        )
        replacement = inspect_release(
            repo, item.replacement_tag, item.commit, root, run=run
        )
        errors.extend(release_identity_errors(source, item, replacement=False))
        if replacement_tag_commit not in {None, item.commit}:
            errors.append(
                f"{item.replacement_tag}: tag resolves to unexpected commit "
                f"{replacement_tag_commit}"
            )
        source_assets = source.get("assets", []) if source else []
        downloads = sum(
            int(asset.get("downloadCount", 0))
            for asset in source_assets
            if isinstance(asset, dict)
        )
        records.append(
            {
                "sourceTag": item.source_tag,
                "replacementTag": item.replacement_tag,
                "commit": item.commit,
                "source": source,
                "replacement": replacement,
                "replacementTagCommit": replacement_tag_commit,
                "documentationLinks": [
                    f"https://github.com/{repo}/releases/tag/{item.source_tag}",
                    f"https://raw.githubusercontent.com/{repo}/{item.commit}/docs/agent-install.md",
                    f"https://raw.githubusercontent.com/{repo}/{item.commit}/copier.yml",
                ],
                "knownDownstreamProvenance": {
                    "consumerIdentities": "not exposed by GitHub Releases",
                    "recordedAssetDownloads": downloads,
                },
                "action": (
                    "already-replaced"
                    if replacement is not None
                    and not release_identity_errors(
                        replacement, item, replacement=True
                    )
                    else "create-beta-replacement"
                ),
            }
        )
    if errors:
        raise MigrationError("; ".join(errors))
    return {
        "schemaVersion": 1,
        "repository": repo,
        "issue": 918,
        "policy": (
            "Create and verify every beta replacement before deleting any "
            "source Release or tag; never move or reuse a tag."
        ),
        "releases": records,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _publish_one(  # noqa: C901
    repo: str,
    item: RetiredRelease,
    root: Path,
    *,
    run: Run = run_command,
) -> None:
    existing = _release_json(repo, item.replacement_tag, root, run=run)
    if existing is not None and existing.get("isDraft") is False:
        verified = inspect_release(
            repo, item.replacement_tag, item.commit, root, run=run
        )
        errors = release_identity_errors(verified, item, replacement=True)
        if errors:
            raise MigrationError("; ".join(errors))
        return
    if existing is not None:
        tag_commit = _tag_commit(repo, item.replacement_tag, root, run=run)
        if existing.get("isDraft") is not True or tag_commit != item.commit:
            raise MigrationError(
                f"{item.replacement_tag}: existing draft identity is invalid"
            )
    else:
        run(
            [
                str(root / "scripts" / "converge-release-tag"),
                "--repo",
                repo,
                "--sha",
                item.commit,
                "--tag",
                item.replacement_tag,
            ],
            cwd=root,
        )
    run(
        [
            "git",
            "fetch",
            "--force",
            "origin",
            f"refs/tags/{item.replacement_tag}:refs/tags/{item.replacement_tag}",
        ],
        cwd=root,
    )

    temporary_root = Path(tempfile.mkdtemp(prefix="csarc-release-migration-"))
    worktree = temporary_root / "source"
    assets = temporary_root / "assets"
    downloaded = temporary_root / "downloaded"
    try:
        run(
            ["git", "worktree", "add", "--detach", str(worktree), item.commit],
            cwd=root,
        )
        version = item.replacement_tag.removeprefix("v")
        release_policy._write_release_version(worktree, version)
        release_policy._write_changelog(worktree, item.commit, version)
        release_bundle.build_artifacts(worktree, assets, version)
        syft = run(
            [str(root / "scripts" / "install-syft")], cwd=root
        ).stdout.strip()
        run(
            [
                syft,
                "scan",
                f"dir:{worktree}",
                "--source-name",
                repo,
                "--source-version",
                item.replacement_tag,
                "-o",
                f"spdx-json={assets / 'sbom.spdx.json'}",
            ],
            cwd=root,
        )
        (assets / "release-prompt.txt").write_text(
            render_release_prompt(item.replacement_tag, item.commit),
            encoding="utf-8",
        )
        _write_json(
            assets / "release-migration.json",
            {
                "schemaVersion": 1,
                "issue": 918,
                "sourceTag": item.source_tag,
                "replacementTag": item.replacement_tag,
                "commit": item.commit,
                "sourceTree": run(
                    ["git", "rev-parse", f"{item.commit}^{{tree}}"], cwd=root
                ).stdout.strip(),
                "buildOverlay": (
                    "Only release version surfaces and CHANGELOG were "
                    "materialized as beta for rebuilt package metadata; "
                    "the tag and source archive retain the exact source tree."
                ),
            },
        )
        release_bundle.finalize(worktree, assets, item.replacement_tag)
        release_bundle.verify(worktree, assets, item.replacement_tag)
        upload = [
            "gh",
            "release",
            "upload",
            item.replacement_tag,
            "--repo",
            repo,
            "--clobber",
            *[str(path) for path in sorted(assets.iterdir()) if path.is_file()],
        ]
        run(upload, cwd=root)
        downloaded.mkdir()
        run(
            [
                "gh",
                "release",
                "download",
                item.replacement_tag,
                "--repo",
                repo,
                "--dir",
                str(downloaded),
            ],
            cwd=root,
        )
        release_bundle.verify(worktree, downloaded, item.replacement_tag)
        run(
            [
                "gh",
                "release",
                "edit",
                item.replacement_tag,
                "--repo",
                repo,
                "--draft=false",
                "--prerelease",
                "--latest=false",
            ],
            cwd=root,
        )
        for attempt in range(12):
            replacement = inspect_release(
                repo, item.replacement_tag, item.commit, root, run=run
            )
            errors = release_identity_errors(
                replacement, item, replacement=True
            )
            if not errors:
                return
            if attempt == 11:
                raise MigrationError("; ".join(errors))
            time.sleep(5)
    except Exception:
        mutable = _release_json(repo, item.replacement_tag, root, run=run)
        if mutable is not None and mutable.get("isImmutable") is False:
            run(
                [
                    "gh",
                    "release",
                    "edit",
                    item.replacement_tag,
                    "--repo",
                    repo,
                    "--draft",
                ],
                cwd=root,
                check=False,
            )
        raise
    finally:
        if worktree.exists():
            run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=root,
                check=False,
            )
        shutil.rmtree(temporary_root, ignore_errors=True)


def apply_plan(repo: str, root: Path, plan: Mapping[str, object]) -> None:
    """Create and verify all replacement Releases without deleting history."""
    if repo != REPOSITORY:
        raise MigrationError(
            f"this one-time migration only supports {REPOSITORY}"
        )
    errors = plan_identity_errors(plan)
    if errors:
        raise MigrationError("; ".join(errors))
    for item in RETIRED_RELEASES:
        source = inspect_release(repo, item.source_tag, item.commit, root)
        source_errors = release_identity_errors(source, item, replacement=False)
        if source_errors:
            raise MigrationError("; ".join(source_errors))
    for item in RETIRED_RELEASES:
        _publish_one(repo, item, root)


def delete_sources(
    repo: str,
    root: Path,
    plan: Mapping[str, object],
    *,
    confirmed: bool,
    run: Run = run_command,
) -> None:
    """Delete the exact source set only after every replacement is verified."""
    if not confirmed:
        raise MigrationError("--confirm-exact-deletion is required")
    replacements = {
        item.replacement_tag: inspect_release(
            repo, item.replacement_tag, item.commit, root, run=run
        )
        for item in RETIRED_RELEASES
    }
    errors = deletion_errors(
        plan,
        {
            tag: release
            for tag, release in replacements.items()
            if release is not None
        },
    )
    if errors:
        raise MigrationError("; ".join(errors))
    for item in RETIRED_RELEASES:
        source = inspect_release(
            repo, item.source_tag, item.commit, root, run=run
        )
        source_errors = release_identity_errors(source, item, replacement=False)
        if source_errors:
            raise MigrationError("; ".join(source_errors))
    for item in RETIRED_RELEASES:
        run(
            [
                "gh",
                "release",
                "delete",
                item.source_tag,
                "--repo",
                repo,
                "--cleanup-tag",
                "--yes",
            ],
            cwd=root,
        )
        if _release_json(repo, item.source_tag, root, run=run) is not None:
            raise MigrationError(f"{item.source_tag}: Release still exists")
        if _tag_commit(repo, item.source_tag, root, run=run) is not None:
            raise MigrationError(f"{item.source_tag}: tag still exists")


def parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    """Parse the intentionally narrow one-time interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply", "delete-originals"))
    parser.add_argument("--repo", default=REPOSITORY)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm-exact-deletion", action="store_true")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    """Run a read-only plan, replacement publish, or guarded deletion."""
    args = parse_args(arguments)
    root = Path(__file__).resolve().parents[1]
    try:
        if args.action == "plan":
            payload = build_plan(args.repo, root)
            if args.output:
                _write_json(args.output.resolve(), payload)
            else:
                print(json.dumps(payload, indent=2, sort_keys=True))  # noqa: T201
            return 0
        if args.plan is None:
            raise MigrationError("--plan is required")
        payload = json.loads(args.plan.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise MigrationError("migration plan must be a JSON object")
        if args.action == "apply":
            apply_plan(args.repo, root, payload)
        else:
            delete_sources(
                args.repo,
                root,
                payload,
                confirmed=args.confirm_exact_deletion,
            )
    except (
        MigrationError,
        OSError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
        ValueError,
    ) as error:
        sys.stderr.write(f"Historical release migration failed: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
