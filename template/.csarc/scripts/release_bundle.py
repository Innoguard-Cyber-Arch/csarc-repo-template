#!/usr/bin/env python3
"""Build and verify the portable GitHub Release bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_phase import is_valid_version
from release_policy import verify_release_version


def run(*arguments: str, cwd: Path) -> str:
    """Run one trusted local build command."""
    executable = shutil.which(arguments[0])
    if executable is None:
        raise ValueError(f"required executable is unavailable: {arguments[0]}")
    return subprocess.run(  # noqa: S603
        [executable, *arguments[1:]],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def digest(path: Path) -> str:
    """Return the SHA-256 digest for one file."""
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def project_license_metadata(root: Path) -> tuple[str, str, str] | None:
    """Return the explicit project package name, license, and copyright."""
    config_path = root / ".csarc/config.yml"
    if not config_path.is_file():
        return None
    config_script = root / "scripts/csarc_config.py"
    if not config_script.is_file():
        config_script = root / ".csarc/scripts/csarc_config.py"
    load_config = runpy.run_path(str(config_script))["load_config"]
    config = load_config(config_path)
    declared = str(config["project_license"])
    if declared == "proprietary":
        declared = "LicenseRef-Proprietary"
    return (
        str(config["project_slug"]),
        declared,
        str(config["copyright_holder"]),
    )


def annotate_sbom(root: Path, sbom_path: Path, version: str) -> None:
    """Bind the explicit project license to the SPDX release document."""
    metadata = project_license_metadata(root)
    if metadata is None:
        return
    name, declared, holder = metadata
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    package_id = "SPDXRef-CSARCProject"
    packages = sbom.setdefault("packages", [])
    if not isinstance(packages, list):
        raise ValueError("release SBOM packages must be a list")
    packages[:] = [
        package for package in packages if package.get("SPDXID") != package_id
    ]
    packages.append(
        {
            "SPDXID": package_id,
            "copyrightText": f"Copyright (c) {holder}",
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": declared,
            "licenseDeclared": declared,
            "name": name,
            "versionInfo": version,
        }
    )
    described = sbom.setdefault("documentDescribes", [])
    if not isinstance(described, list):
        raise ValueError("release SBOM documentDescribes must be a list")
    if package_id not in described:
        described.append(package_id)
    if declared == "LicenseRef-Proprietary":
        extracted = sbom.setdefault("hasExtractedLicensingInfos", [])
        if not isinstance(extracted, list):
            raise ValueError(
                "release SBOM hasExtractedLicensingInfos must be a list"
            )
        extracted[:] = [
            item for item in extracted if item.get("licenseId") != declared
        ]
        extracted.append(
            {
                "extractedText": (root / "LICENSE").read_text(encoding="utf-8"),
                "licenseId": declared,
                "name": "Proprietary",
            }
        )
    sbom_path.write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def identity(root: Path, tag: str) -> tuple[str, str]:
    """Validate the release tag and return its version and commit.

    Issue #918: a tag may carry the legal `-beta.N` prerelease suffix;
    `is_valid_version` (.csarc/scripts/release_phase.py) is the one canonical
    parser for that shape, reused here instead of a second hand-rolled
    regex that could drift from it.
    """
    if not tag.startswith("v") or not is_valid_version(tag):
        raise ValueError(f"invalid release tag: {tag}")
    version = verify_release_version(root, tag.removeprefix("v"))
    commit = run("git", "rev-parse", "HEAD", cwd=root)
    tagged = run("git", "rev-parse", f"{tag}^{{commit}}", cwd=root)
    if tagged != commit:
        raise ValueError(f"{tag} does not identify the checked-out commit")
    return version, commit


def build_artifacts(root: Path, output: Path, version: str) -> None:
    """Build source and each detected language-native package."""
    if output == root or root in output.parents:
        raise ValueError("release output must be outside the repository")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    component = json.loads(
        (root / ".csarc/release-please-config.json").read_text(encoding="utf-8")
    )["packages"]["."]["component"]
    source = output / f"{component}-{version}.tar"
    git = shutil.which("git")
    if git is None:
        raise ValueError("required executable is unavailable: git")
    with source.open("wb") as target:
        subprocess.run(  # noqa: S603
            [
                git,
                "archive",
                "--format=tar",
                f"--prefix={component}-{version}/",
                "HEAD",
            ],
            cwd=root,
            check=True,
            stdout=target,
        )

    if (root / "pyproject.toml").is_file():
        run("uv", "build", "--out-dir", str(output), cwd=root)
        # uv build writes its own `.gitignore` (content: "*") into
        # --out-dir as a build-tool convention marker; it is not release
        # content and must not become part of the checksummed bundle.
        (output / ".gitignore").unlink(missing_ok=True)
    if (root / "package.json").is_file():
        run("pnpm", "pack", "--pack-destination", str(output), cwd=root)
    if (root / "Cargo.toml").is_file():
        run("cargo", "package", "--locked", cwd=root)
        crates = sorted((root / "target" / "package").glob("*.crate"))
        if len(crates) != 1:
            raise ValueError("expected exactly one Rust package")
        shutil.copy2(crates[0], output / crates[0].name)


def candidate(root: Path, output: Path) -> None:
    """Verify version surfaces and prove the candidate remains packageable."""
    build_artifacts(root, output, verify_release_version(root))


def prepare(root: Path, output: Path, tag: str) -> None:
    """Build source and language-native packages for one exact tag."""
    version, _ = identity(root, tag)
    build_artifacts(root, output, version)


def finalize(root: Path, output: Path, tag: str) -> None:
    """Bind every release file to its source commit and checksum."""
    version, commit = identity(root, tag)
    sbom = output / "sbom.spdx.json"
    if not sbom.is_file():
        raise ValueError("sbom.spdx.json is missing")
    annotate_sbom(root, sbom, version)
    files = sorted(path for path in output.iterdir() if path.is_file())
    evidence = {
        "schema_version": 1,
        "repository": os.environ.get("GITHUB_REPOSITORY", "local"),
        "release_run": os.environ.get("GITHUB_RUN_ID", "local"),
        "tag": tag,
        "version": version,
        "commit": commit,
        "artifacts": {path.name: digest(path) for path in files},
    }
    evidence_path = output / "release-evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    files.append(evidence_path)
    (output / "SHA256SUMS").write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in sorted(files)),
        encoding="utf-8",
    )


def verify(root: Path, output: Path, tag: str) -> None:
    """Reject incomplete, altered, or wrongly bound release bundles."""
    version, commit = identity(root, tag)
    checksum = output / "SHA256SUMS"
    expected_files = {
        path.name
        for path in output.iterdir()
        if path.is_file() and path != checksum
    }
    observed: set[str] = set()
    for line in checksum.read_text(encoding="utf-8").splitlines():
        expected, separator, name = line.partition("  ")
        path = output / name
        if (
            len(expected) != 64
            or separator != "  "
            or Path(name).name != name
            or not path.is_file()
            or digest(path) != expected
        ):
            raise ValueError(f"invalid checksum entry: {line}")
        observed.add(name)
    if observed != expected_files:
        raise ValueError("SHA256SUMS does not cover the exact release bundle")
    required = {"release-evidence.json", "sbom.spdx.json"}
    if not required.issubset(observed) or not any(
        name.endswith(".tar") for name in observed
    ):
        raise ValueError("release bundle is missing required evidence")
    sbom = json.loads((output / "sbom.spdx.json").read_text(encoding="utf-8"))
    if (
        sbom.get("spdxVersion") != "SPDX-2.3"
        or sbom.get("SPDXID") != "SPDXRef-DOCUMENT"
    ):
        raise ValueError("release SBOM is not an SPDX 2.3 document")
    license_metadata = project_license_metadata(root)
    if license_metadata is not None:
        _, expected_license, _ = license_metadata
        project_packages = [
            package
            for package in sbom.get("packages", [])
            if package.get("SPDXID") == "SPDXRef-CSARCProject"
        ]
        if (
            len(project_packages) != 1
            or project_packages[0].get("licenseDeclared") != expected_license
        ):
            raise ValueError("release SBOM license does not match config")
    evidence = json.loads(
        (output / "release-evidence.json").read_text(encoding="utf-8")
    )
    if (
        evidence.get("tag") != tag
        or evidence.get("version") != version
        or evidence.get("commit") != commit
    ):
        raise ValueError("release evidence does not match the exact tag")
    bound = evidence.get("artifacts")
    if (
        not isinstance(bound, dict)
        or set(bound) != observed - {"release-evidence.json"}
        or any(Path(name).name != name for name in bound)
        or any(digest(output / name) != value for name, value in bound.items())
    ):
        raise ValueError("release evidence artifact binding is invalid")


def main() -> None:
    """Run the requested release bundle operation."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=("candidate", "prepare", "finalize", "verify")
    )
    parser.add_argument("--tag")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    try:
        if args.action == "candidate":
            candidate(root, args.output.resolve())
        elif args.tag is None:
            raise ValueError(f"--tag is required for {args.action}")
        else:
            globals()[args.action](root, args.output.resolve(), args.tag)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
