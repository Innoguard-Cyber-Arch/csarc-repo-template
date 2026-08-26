#!/usr/bin/env python3
"""Bind and verify exact-tag release artifacts and a Syft SPDX SBOM."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
PURL = re.compile(
    r"^pkg:(?P<ecosystem>[a-z][a-z0-9.+-]*)/(?P<name>[^@?#]+)"
    r"@(?P<version>[^?#]+)(?:\?(?P<qualifiers>[^#]+))?"
    r"(?:#(?P<subpath>.*))?$"
)
SAFE_BASENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
SYFT_CREATORS = {"Organization: Anchore, Inc", "Tool: syft-1.50.0"}


def digest(path: Path) -> str:
    """Return one file's lowercase SHA-256 digest."""
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    """Load one JSON object and reject every other top-level shape."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def version_from(path: Path) -> str:
    """Read the canonical release version."""
    version = path.read_text(encoding="utf-8").strip()
    if VERSION.fullmatch(version) is None:
        raise ValueError(f"{path} does not contain a supported version")
    return version


def git_output(*arguments: str) -> str:
    """Return stripped output from a read-only Git command."""
    return subprocess.run(  # noqa: S603
        ["git", *arguments],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def validate_identity(tag: str, commit: str, version: str) -> None:
    """Validate exact tag, commit, worktree, and version identity."""
    if FULL_SHA.fullmatch(commit) is None:
        raise ValueError("release commit must be a full lowercase SHA")
    if tag != f"v{version}":
        raise ValueError("release tag and version do not match")
    if git_output("rev-parse", "HEAD") != commit:
        raise ValueError("checked-out release commit does not match")
    if git_output("rev-list", "-n", "1", tag) != commit:
        raise ValueError("release tag does not point to the build commit")


def validate_run(value: str, name: str) -> None:
    """Require an exact positive decimal Actions run ID."""
    if re.fullmatch(r"[1-9][0-9]*", value) is None:
        raise ValueError(f"{name} must be an exact positive decimal run ID")


def release_files(
    asset_root: Path,
    artifact_paths: list[Path],
    evidence_paths: tuple[Path, Path, Path, Path],
    *,
    require_manifest: bool,
) -> dict[str, Path]:
    """Validate an explicit, flat, and complete release file set."""
    root = asset_root.resolve()
    if not asset_root.is_dir():
        raise ValueError("asset root must be a directory")
    manifest_path = evidence_paths[2]
    inventory_path = evidence_paths[1].resolve()
    required_paths = [
        *artifact_paths,
        evidence_paths[0],
        evidence_paths[1],
        evidence_paths[3],
    ]
    if require_manifest or manifest_path.exists():
        required_paths.append(manifest_path)
    resolved: dict[str, Path] = {}
    for path in required_paths:
        candidate = path.resolve()
        if (
            candidate.parent != root
            or not path.is_file()
            or path.is_symlink()
            or SAFE_BASENAME.fullmatch(path.name) is None
        ):
            raise ValueError(
                f"release file must be an immediate regular child: {path}"
            )
        if path.name in resolved or candidate in resolved.values():
            raise ValueError(f"duplicate release file: {path.name}")
        if path.stat().st_size == 0 and candidate != inventory_path:
            raise ValueError(f"release file is empty: {path}")
        resolved[path.name] = candidate
    if not artifact_paths:
        raise ValueError("release requires at least one explicit artifact")
    actual = {path.name: path.resolve() for path in asset_root.iterdir()}
    if actual != resolved:
        raise ValueError(
            "asset root contains an unexpected or missing release file"
        )
    evidence_names = {path.name for path in evidence_paths}
    return {
        name: path
        for name, path in resolved.items()
        if name not in evidence_names
    }


def decode_purl_part(value: str, label: str) -> str:
    """Decode one non-empty purl part after validating percent escapes."""
    if (
        not value
        or any(
            character.isspace() or ord(character) < 32 for character in value
        )
        or re.search(r"%(?![0-9A-Fa-f]{2})", value)
    ):
        raise ValueError(f"package purl has an invalid {label}")
    decoded = unquote(value)
    if not decoded or any(ord(character) < 32 for character in decoded):
        raise ValueError(f"package purl has an invalid {label}")
    return decoded


def purl_identity(purl: str) -> tuple[str, str, str]:  # noqa: C901
    """Parse the ecosystem, decoded package name, and version from a purl."""
    match = PURL.fullmatch(purl)
    if match is None:
        raise ValueError(f"package purl is malformed: {purl}")
    ecosystem = match.group("ecosystem")
    raw_name_parts = match.group("name").split("/")
    name_parts = [decode_purl_part(part, "name") for part in raw_name_parts]
    if any(part in {".", ".."} or "/" in part for part in name_parts):
        raise ValueError("package purl has an invalid name")
    qualifiers = match.group("qualifiers")
    if qualifiers:
        pairs = qualifiers.split("&")
        keys: list[str] = []
        for pair in pairs:
            if pair.count("=") != 1:
                raise ValueError("package purl has invalid qualifiers")
            key, value = pair.split("=", 1)
            if re.fullmatch(r"[a-z][a-z0-9._-]*", key) is None:
                raise ValueError("package purl has invalid qualifiers")
            decode_purl_part(value, "qualifier")
            keys.append(key)
        if len(keys) != len(set(keys)) or keys != sorted(keys):
            raise ValueError("package purl has invalid qualifiers")
    subpath = match.group("subpath")
    subpath_parts: list[str] = []
    if subpath is not None:
        subpath_parts = [
            decode_purl_part(part, "subpath") for part in subpath.split("/")
        ]
        if any(part in {".", ".."} or "/" in part for part in subpath_parts):
            raise ValueError("package purl has an invalid subpath")
    name = "/".join(name_parts)
    if ecosystem == "github" and subpath_parts:
        name = f"{name}/{'/'.join(subpath_parts)}"
    version = decode_purl_part(match.group("version"), "version")
    if "/" in version:
        raise ValueError("package purl has an invalid version")
    return ecosystem, name, version


def normalized_name(name: str, ecosystem: str) -> str:
    """Apply the ecosystem's package-name comparison rules."""
    if ecosystem == "pypi":
        return re.sub(r"[-_.]+", "-", name).lower()
    return unquote(name)


def validate_package(package: dict[str, Any]) -> str:
    """Validate the SPDX 2.3 fields required for one package."""
    package_id = package.get("SPDXID")
    string_fields = (
        "name",
        "versionInfo",
        "downloadLocation",
        "licenseConcluded",
        "licenseDeclared",
        "copyrightText",
    )
    if (
        not isinstance(package_id, str)
        or not package_id.startswith("SPDXRef-")
        or package_id == "SPDXRef-DOCUMENT"
        or any(
            not isinstance(package.get(field), str) or not package[field]
            for field in string_fields
        )
        or not isinstance(package.get("filesAnalyzed"), bool)
    ):
        raise ValueError("SPDX package is missing a required typed field")
    return package_id


def validate_package_purl(package: dict[str, Any], purl: str) -> str:
    """Require the purl name and version to match the SPDX package."""
    ecosystem, name, version = purl_identity(purl)
    package_name = package["name"]
    if (
        normalized_name(package_name, ecosystem)
        != normalized_name(name, ecosystem)
        or package["versionInfo"] != version
    ):
        raise ValueError("package purl name or version does not match SPDX")
    return ecosystem


def inventory(path: Path) -> list[str]:
    """Load a newline-separated, unique, canonical purl inventory."""
    if not path.is_file():
        raise ValueError("runtime inventory file is missing")
    lines = path.read_text(encoding="utf-8").splitlines()
    if any(not line or line.strip() != line for line in lines):
        raise ValueError("runtime inventory contains an invalid purl line")
    if len(lines) != len(set(lines)):
        raise ValueError("runtime inventory contains duplicate purls")
    for line in lines:
        purl_identity(line)
    return sorted(lines)


def inventory_binding(purls: list[str]) -> dict[str, Any]:
    """Bind the sorted inventory set rather than filesystem ordering."""
    payload = "".join(f"{purl}\n" for purl in purls).encode()
    return {
        "count": len(purls),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def inventory_evidence(path: Path, purls: list[str]) -> dict[str, Any]:
    """Bind both downloaded inventory bytes and its normalized purl set."""
    return {
        "name": path.name,
        "normalized_purls": inventory_binding(purls),
        "sha256": digest(path),
        "size": path.stat().st_size,
    }


def package_purls(package: dict[str, Any]) -> list[str]:
    """Return the package-manager purls from one SPDX package."""
    references = package.get("externalRefs", [])
    if not isinstance(references, list):
        raise ValueError("SPDX package externalRefs must be a list")
    purls: list[str] = []
    for reference in references:
        if not isinstance(reference, dict):
            raise ValueError("SPDX package externalRefs must contain objects")
        if reference.get("referenceType") != "purl":
            continue
        locator = reference.get("referenceLocator")
        if reference.get(
            "referenceCategory"
        ) != "PACKAGE-MANAGER" or not isinstance(locator, str):
            raise ValueError("SPDX package purl reference is malformed")
        purls.append(locator)
    return purls


def validate_root_purl(
    root_purl: str, package: dict[str, Any], version: str
) -> None:
    """Validate the root package ecosystem purl and version."""
    _, _, purl_version = purl_identity(root_purl)
    validate_package_purl(package, root_purl)
    if package.get("versionInfo") != version or purl_version != version:
        raise ValueError("root package version does not match purl")


def validate_sbom(  # noqa: C901
    sbom: dict[str, Any],
    *,
    runtime_kind: str,
    root_name: str,
    root_purls: list[str],
    inventory_purls: list[str],
    version: str,
) -> None:
    """Validate one Syft-produced SPDX 2.3 runtime dependency graph."""
    creation = sbom.get("creationInfo")
    creators = creation.get("creators") if isinstance(creation, dict) else None
    created = creation.get("created") if isinstance(creation, dict) else None
    namespace = sbom.get("documentNamespace")
    parsed_namespace = (
        urlparse(namespace) if isinstance(namespace, str) else None
    )
    try:
        created_at = (
            datetime.fromisoformat(created.replace("Z", "+00:00"))
            if isinstance(created, str)
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", created)
            else None
        )
    except ValueError:
        created_at = None
    if (
        sbom.get("spdxVersion") != "SPDX-2.3"
        or sbom.get("SPDXID") != "SPDXRef-DOCUMENT"
        or sbom.get("dataLicense") != "CC0-1.0"
        or not isinstance(namespace, str)
        or parsed_namespace is None
        or parsed_namespace.scheme not in {"http", "https"}
        or not parsed_namespace.netloc
        or parsed_namespace.fragment
        or any(character.isspace() for character in namespace)
        or created_at is None
        or created_at.utcoffset() != timedelta(0)
        or not isinstance(creators, list)
        or not all(isinstance(item, str) for item in creators)
        or len(creators) != len(SYFT_CREATORS)
        or set(creators) != SYFT_CREATORS
    ):
        raise ValueError("release SBOM must be SPDX 2.3 JSON created by Syft")

    raw_packages = sbom.get("packages")
    relationships = sbom.get("relationships")
    if not isinstance(raw_packages, list) or not raw_packages:
        raise ValueError("release SBOM must contain packages")
    if not isinstance(relationships, list) or not relationships:
        raise ValueError("release SBOM must contain relationships")
    packages: dict[str, dict[str, Any]] = {}
    for package in raw_packages:
        if not isinstance(package, dict):
            raise ValueError("SPDX packages must be objects")
        package_id = validate_package(package)
        if package_id in packages:
            raise ValueError("SPDX package IDs must be unique strings")
        packages[package_id] = package

    describes: list[str] = []
    contains: set[tuple[str, str]] = set()
    dependency_graph: dict[str, set[str]] = {
        package_id: set() for package_id in packages
    }
    for relationship in relationships:
        if not isinstance(relationship, dict):
            raise ValueError("SPDX relationships must be objects")
        source = relationship.get("spdxElementId")
        target = relationship.get("relatedSpdxElement")
        kind = relationship.get("relationshipType")
        if any(
            not isinstance(value, str) or not value
            for value in (source, target, kind)
        ):
            raise ValueError(
                "SPDX relationship fields must be non-empty strings"
            )
        if kind == "DESCRIBES":
            if source != "SPDXRef-DOCUMENT" or not isinstance(target, str):
                raise ValueError("SPDX DESCRIBES target must be a string")
            describes.append(target)
        if (
            kind == "CONTAINS"
            and isinstance(source, str)
            and isinstance(target, str)
        ):
            contains.add((source, target))
        if kind not in {"DEPENDS_ON", "DEPENDENCY_OF"}:
            continue
        if source not in packages or target not in packages:
            raise ValueError("SPDX dependency graph contains a dangling edge")
        parent, dependency = (
            (source, target) if kind == "DEPENDS_ON" else (target, source)
        )
        if parent == dependency:
            raise ValueError("SPDX dependency graph contains a self edge")
        dependency_graph[parent].add(dependency)
    if len(describes) != 1 or describes[0] not in packages:
        raise ValueError(
            "release SBOM must have exactly one package DESCRIBES root"
        )
    document_root = describes[0]
    described = packages[document_root]
    if (
        sbom.get("name") != root_name
        or described.get("name") != root_name
        or described.get("versionInfo") != version
    ):
        raise ValueError("SPDX DESCRIBES source identity does not match")

    if runtime_kind == "source":
        if root_purls:
            raise ValueError("source runtime must not declare a root purl")
        if inventory_purls:
            raise ValueError("source runtime inventory must be empty")
        if package_purls(described):
            raise ValueError("SPDX source root must not impersonate a package")
        for package_id, package in packages.items():
            if package_id == document_root:
                continue
            purls = package_purls(package)
            if len(purls) != 1:
                raise ValueError(
                    "each SPDX source component must have one package purl"
                )
            validate_package_purl(package, purls[0])
            if (document_root, package_id) not in contains:
                raise ValueError(
                    "SPDX source root does not contain every component"
                )
        return
    if runtime_kind != "package":
        raise ValueError("runtime kind must be package or source")
    if not root_purls or len(set(root_purls)) != len(root_purls):
        raise ValueError("package runtime requires unique root purls")

    purl_owners: dict[str, str] = {}
    purl_ecosystems: dict[str, str] = {}
    for package_id, package in packages.items():
        purls = package_purls(package)
        if package_id == document_root:
            if purls:
                raise ValueError(
                    "SPDX document root must not impersonate a package"
                )
            continue
        if len(purls) != 1 or purls[0] in purl_owners:
            raise ValueError(
                "each SPDX runtime package must have one unique purl"
            )
        purl_owners[purls[0]] = package_id
        purl_ecosystems[purls[0]] = validate_package_purl(package, purls[0])
    if any(PURL.fullmatch(root_purl) is None for root_purl in root_purls):
        raise ValueError("root package purl is malformed")
    root_ids = {purl_owners.get(root_purl) for root_purl in root_purls}
    if None in root_ids or len(root_ids) != len(root_purls):
        raise ValueError("release SBOM must contain every expected root purl")
    roots = {root_id for root_id in root_ids if root_id is not None}
    root_ecosystems = {purl_identity(purl)[0] for purl in root_purls}
    if set(purl_ecosystems.values()) - root_ecosystems:
        raise ValueError("SPDX package ecosystem is not declared by a root")
    if set(inventory_purls) != set(purl_owners):
        raise ValueError("runtime inventory does not match SPDX package purls")
    for root_purl in root_purls:
        validate_root_purl(root_purl, packages[purl_owners[root_purl]], version)
    if any((document_root, root_id) not in contains for root_id in roots):
        raise ValueError(
            "SPDX DESCRIBES root does not contain every release root"
        )

    reachable = set(roots)
    pending = list(roots)
    while pending:
        for dependency in dependency_graph[pending.pop()]:
            if dependency not in reachable:
                reachable.add(dependency)
                pending.append(dependency)
    if reachable != set(packages) - {document_root}:
        raise ValueError(
            "SPDX runtime dependency graph contains an orphan package"
        )


def identity_fields(
    tag: str,
    commit: str,
    version: str,
    repository: str,
    source_run: str,
) -> dict[str, str]:
    """Return the immutable release identity shared by all evidence."""
    return {
        "commit": commit,
        "repository": repository,
        "source_run": source_run,
        "tag": tag,
        "version": version,
    }


def runtime_fields(
    runtime_kind: str, root_name: str, root_purls: list[str]
) -> dict[str, Any]:
    """Return the exact runtime identity shared by all evidence."""
    return {
        "root_name": root_name,
        "root_purls": sorted(root_purls),
        "runtime_kind": runtime_kind,
    }


def validate_provenance(
    provenance: dict[str, Any],
    *,
    expected: dict[str, Any],
    tag: str,
    commit: str,
    repository: str,
    repository_id: int,
    release_run: str,
    finalized: bool,
) -> None:
    """Validate the closed provenance schema and exact release identity."""
    optional = {
        "commit_sha",
        "guide_url",
        "release_source",
        "release_tag",
        "workflow_run",
    }
    unknown = set(provenance) - set(expected) - optional
    if unknown:
        raise ValueError("provenance contains an unexpected field")
    commits = [
        provenance[key] for key in ("commit", "commit_sha") if key in provenance
    ]
    tags = [
        provenance[key] for key in ("tag", "release_tag") if key in provenance
    ]
    if (
        not commits
        or any(value != commit for value in commits)
        or not tags
        or any(value != tag for value in tags)
    ):
        raise ValueError("provenance release identity does not match")
    workflow_run = provenance.get("workflow_run")
    if "workflow_run" in provenance and workflow_run != (
        f"https://github.com/{repository}/actions/runs/{release_run}"
    ):
        raise ValueError("provenance workflow run does not match")
    guide_url = provenance.get("guide_url")
    if "guide_url" in provenance and guide_url != (
        f"https://raw.githubusercontent.com/{repository}/{commit}/"
        "docs/agent-install.md"
    ):
        raise ValueError("provenance guide URL does not match")
    if "repository_id" in provenance and (
        isinstance(provenance["repository_id"], bool)
        or provenance["repository_id"] != repository_id
    ):
        raise ValueError("provenance repository ID does not match")
    if "schema_version" in provenance and (
        isinstance(provenance["schema_version"], bool)
        or provenance["schema_version"] != 1
    ):
        raise ValueError("provenance schema version does not match")
    if any(
        key in provenance and provenance[key] != value
        for key, value in expected.items()
    ):
        raise ValueError("provenance bound identity does not match")
    if finalized and any(
        key not in provenance or provenance[key] != value
        for key, value in expected.items()
    ):
        raise ValueError("provenance is not fully bound")
    source = provenance.get("release_source")
    if "release_source" in provenance and (
        not isinstance(source, dict) or source.get("main_sha") != commit
    ):
        raise ValueError("provenance release source boundary does not match")


def build(
    *,
    tag: str,
    commit: str,
    version_file: Path,
    repository: str,
    repository_id: int,
    source_run: str,
    release_run: str,
    runtime_kind: str,
    root_name: str,
    root_purls: list[str],
    inventory_file: Path,
    asset_root: Path,
    artifact_paths: list[Path],
    sbom_path: Path,
    manifest_path: Path,
    provenance_path: Path,
) -> None:
    """Finalize provenance, then write the terminal release manifest."""
    version = version_from(version_file)
    validate_identity(tag, commit, version)
    validate_run(source_run, "source run")
    validate_run(release_run, "release run")
    if isinstance(repository_id, bool) or repository_id <= 0:
        raise ValueError("repository ID must be a positive integer")
    inventory_purls = inventory(inventory_file)
    sbom = load_object(sbom_path)
    validate_sbom(
        sbom,
        runtime_kind=runtime_kind,
        root_name=root_name,
        root_purls=root_purls,
        inventory_purls=inventory_purls,
        version=version,
    )
    evidence_paths = (
        sbom_path,
        inventory_file,
        manifest_path,
        provenance_path,
    )
    inputs = release_files(
        asset_root,
        artifact_paths,
        evidence_paths,
        require_manifest=False,
    )
    artifact_bindings = {
        name: {"sha256": digest(path), "size": path.stat().st_size}
        for name, path in inputs.items()
    }
    sbom_binding = {
        "name": sbom_path.name,
        "sha256": digest(sbom_path),
        "size": sbom_path.stat().st_size,
    }
    expected_provenance = {
        **identity_fields(tag, commit, version, repository, source_run),
        "artifacts": artifact_bindings,
        "inventory": inventory_evidence(inventory_file, inventory_purls),
        "release_run": release_run,
        "repository_id": repository_id,
        **runtime_fields(runtime_kind, root_name, root_purls),
        "schema_version": 1,
        "sbom": sbom_binding,
    }
    provenance = load_object(provenance_path)
    validate_provenance(
        provenance,
        expected=expected_provenance,
        tag=tag,
        commit=commit,
        repository=repository,
        repository_id=repository_id,
        release_run=release_run,
        finalized=False,
    )
    provenance.update(expected_provenance)
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = expected_provenance | {
        "provenance": {
            "name": provenance_path.name,
            "sha256": digest(provenance_path),
            "size": provenance_path.stat().st_size,
        }
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    release_files(
        asset_root,
        artifact_paths,
        evidence_paths,
        require_manifest=True,
    )


def verify(
    *,
    tag: str,
    commit: str,
    version_file: Path,
    repository: str,
    repository_id: int,
    source_run: str,
    release_run: str,
    runtime_kind: str,
    root_name: str,
    root_purls: list[str],
    inventory_file: Path,
    asset_root: Path,
    artifact_paths: list[Path],
    sbom_path: Path,
    manifest_path: Path,
    provenance_path: Path,
) -> None:
    """Fail closed unless release evidence matches every exact input."""
    version = version_from(version_file)
    validate_identity(tag, commit, version)
    validate_run(source_run, "source run")
    validate_run(release_run, "release run")
    if isinstance(repository_id, bool) or repository_id <= 0:
        raise ValueError("repository ID must be a positive integer")
    inventory_purls = inventory(inventory_file)
    sbom = load_object(sbom_path)
    validate_sbom(
        sbom,
        runtime_kind=runtime_kind,
        root_name=root_name,
        root_purls=root_purls,
        inventory_purls=inventory_purls,
        version=version,
    )
    inputs = release_files(
        asset_root,
        artifact_paths,
        (sbom_path, inventory_file, manifest_path, provenance_path),
        require_manifest=True,
    )
    artifact_bindings = {
        name: {"sha256": digest(path), "size": path.stat().st_size}
        for name, path in inputs.items()
    }
    expected_sbom = {
        "name": sbom_path.name,
        "sha256": digest(sbom_path),
        "size": sbom_path.stat().st_size,
    }
    expected_provenance = {
        **identity_fields(tag, commit, version, repository, source_run),
        "artifacts": artifact_bindings,
        "inventory": inventory_evidence(inventory_file, inventory_purls),
        "release_run": release_run,
        "repository_id": repository_id,
        **runtime_fields(runtime_kind, root_name, root_purls),
        "schema_version": 1,
        "sbom": expected_sbom,
    }
    provenance = load_object(provenance_path)
    validate_provenance(
        provenance,
        expected=expected_provenance,
        tag=tag,
        commit=commit,
        repository=repository,
        repository_id=repository_id,
        release_run=release_run,
        finalized=True,
    )
    expected_manifest = {
        **expected_provenance,
        "provenance": {
            "name": provenance_path.name,
            "sha256": digest(provenance_path),
            "size": provenance_path.stat().st_size,
        },
    }
    if load_object(manifest_path) != expected_manifest:
        raise ValueError("artifact manifest bindings do not match")


def main() -> None:
    """Build or verify one exact-tag release evidence bundle."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument(
        "--version-file", type=Path, default=Path("version.txt")
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", required=True, type=int)
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--release-run", required=True)
    parser.add_argument(
        "--runtime-kind", choices=("package", "source"), default="package"
    )
    parser.add_argument("--root-name", required=True)
    parser.add_argument("--root-purl", dest="root_purls", action="append")
    parser.add_argument("--inventory-file", required=True, type=Path)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument(
        "--artifact",
        dest="artifact_paths",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    args = parser.parse_args()
    options = {
        "tag": args.tag,
        "commit": args.commit,
        "repository": args.repository,
        "repository_id": args.repository_id,
        "source_run": args.source_run,
        "release_run": args.release_run,
        "runtime_kind": args.runtime_kind,
        "root_name": args.root_name,
        "root_purls": args.root_purls or [],
        "inventory_file": args.inventory_file,
        "version_file": args.version_file,
        "asset_root": args.asset_root,
        "artifact_paths": args.artifact_paths,
        "sbom_path": args.sbom,
        "manifest_path": args.manifest,
        "provenance_path": args.provenance,
    }
    if args.action == "build":
        build(**options)
    else:
        verify(**options)


if __name__ == "__main__":
    main()
