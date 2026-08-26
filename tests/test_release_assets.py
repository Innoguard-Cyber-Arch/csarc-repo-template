"""Tests for exact-tag release bindings over genuine Syft SPDX output."""

from __future__ import annotations

import copy
import json
import os
import runpy
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

DEFAULT_SCRIPT = Path(__file__).parents[1] / "scripts" / "release_assets.py"
SCRIPT_UNDER_TEST = Path(
    os.environ.get("CSARC_RELEASE_ASSETS_SCRIPT", str(DEFAULT_SCRIPT))
).resolve()
MODULE = runpy.run_path(str(SCRIPT_UNDER_TEST))
build = MODULE["build"]
verify = MODULE["verify"]
FIXTURES = Path(__file__).parent / "fixtures"
RUNTIME_FIXTURE = FIXTURES / "syft-v1.50.0-runtime.spdx.json"
SOURCE_FIXTURE = FIXTURES / "syft-v1.50.0-source.spdx.json"
SOURCE_COMPONENTS_FIXTURE = (
    FIXTURES / "syft-v1.50.0-source-components.spdx.json"
)
ROOT_PURL = "pkg:pypi/csarc-repo-cli@0.11.0"
SECOND_ROOT_PURL = "pkg:npm/csarc-repo-cli@0.11.0"
REPOSITORY = "owner/repo"
REPOSITORY_ID = 123456789
SOURCE_RUN = "123456"
RELEASE_RUN = "654321"


def git(root: Path, *arguments: str) -> str:
    """Run Git in a test repository."""
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(root), *arguments],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load(path: Path) -> dict[str, Any]:
    """Load a mutable test JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    """Write a mutated test JSON object."""
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def sbom_purls(sbom: dict[str, Any]) -> list[str]:
    """Return the sorted package-manager purl set from an SPDX fixture."""
    return sorted(
        {
            reference["referenceLocator"]
            for package in sbom["packages"]
            for reference in package.get("externalRefs", [])
            if reference.get("referenceCategory") == "PACKAGE-MANAGER"
            and reference.get("referenceType") == "purl"
        }
    )


def write_inventory(options: dict[str, Any], sbom: dict[str, Any]) -> None:
    """Write the exact package set used by a test SBOM."""
    options["inventory_file"].write_text(
        "".join(f"{purl}\n" for purl in sbom_purls(sbom)),
        encoding="utf-8",
    )


def root_id(sbom: dict[str, Any]) -> str:
    """Return the fixture's Python product package SPDX ID."""
    for package in sbom["packages"]:
        if any(
            reference.get("referenceLocator") == ROOT_PURL
            for reference in package.get("externalRefs", [])
        ):
            return str(package["SPDXID"])
    raise AssertionError("fixture root package is missing")


def release_fixture(tmp_path: Path) -> tuple[str, dict[str, Any]]:
    """Create one immutable-tag release input bundle."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Release Test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    version = tmp_path / "version.txt"
    version.write_text("0.11.0\n", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    artifact = assets / "not-a-package-name.whl"
    artifact.write_bytes(b"wheel bytes")
    sbom = assets / "sbom.spdx.json"
    shutil.copyfile(RUNTIME_FIXTURE, sbom)
    inventory = assets / "inventory.purls"
    inventory.write_text(
        "".join(f"{purl}\n" for purl in sbom_purls(load(sbom))),
        encoding="utf-8",
    )
    provenance = assets / "release-metadata.json"
    git(tmp_path, "add", "version.txt")
    environment = os.environ | {
        "GIT_AUTHOR_DATE": "2026-01-02T03:04:05Z",
        "GIT_COMMITTER_DATE": "2026-01-02T03:04:05Z",
    }
    subprocess.run(  # noqa: S603
        ["git", "-C", str(tmp_path), "commit", "-qm", "release"],  # noqa: S607
        check=True,
        env=environment,
    )
    commit = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "tag", "v0.11.0")
    provenance.write_text(
        json.dumps(
            {
                "commit_sha": commit,
                "guide_url": (
                    f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}/"
                    "docs/agent-install.md"
                ),
                "release_tag": "v0.11.0",
                "repository": REPOSITORY,
                "repository_id": REPOSITORY_ID,
                "schema_version": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return commit, {
        "tag": "v0.11.0",
        "commit": commit,
        "version_file": version,
        "repository": REPOSITORY,
        "repository_id": REPOSITORY_ID,
        "source_run": SOURCE_RUN,
        "release_run": RELEASE_RUN,
        "runtime_kind": "package",
        "root_name": "csarc-repo-cli",
        "root_purls": [ROOT_PURL],
        "inventory_file": inventory,
        "asset_root": assets,
        "artifact_paths": [artifact],
        "sbom_path": sbom,
        "manifest_path": assets / "release-manifest.json",
        "provenance_path": provenance,
    }


def use_source_fixture(options: dict[str, Any], fixture: Path) -> None:
    """Switch one test bundle to source-only runtime semantics."""
    shutil.copyfile(fixture, options["sbom_path"])
    options["inventory_file"].write_text("", encoding="utf-8")
    options["runtime_kind"] = "source"
    options["root_purls"] = []


def test_binds_explicit_artifacts_and_finalized_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unchanged SBOM and provenance feed the terminal manifest."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    sbom_before = options["sbom_path"].read_bytes()

    build(**options)
    verify(**options)

    assert options["sbom_path"].read_bytes() == sbom_before
    manifest = load(options["manifest_path"])
    provenance = load(options["provenance_path"])
    assert set(manifest["artifacts"]) == {"not-a-package-name.whl"}
    assert manifest["root_purls"] == [ROOT_PURL]
    assert manifest["source_run"] == SOURCE_RUN
    assert manifest["release_run"] == RELEASE_RUN
    assert manifest["inventory"] == {
        "name": "inventory.purls",
        "normalized_purls": MODULE["inventory_binding"](
            sbom_purls(load(options["sbom_path"]))
        ),
        "sha256": MODULE["digest"](options["inventory_file"]),
        "size": options["inventory_file"].stat().st_size,
    }
    assert manifest["provenance"]["sha256"] == MODULE["digest"](
        options["provenance_path"]
    )
    assert "artifact_manifest" not in provenance
    assert provenance["artifacts"] == manifest["artifacts"]
    assert provenance["inventory"] == manifest["inventory"]
    assert provenance["sbom"] == manifest["sbom"]


def test_accepts_generated_project_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generated repositories may retain an exact nested source boundary."""
    commit, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    save(
        options["provenance_path"],
        {
            "commit": commit,
            "release_source": {"main_sha": commit, "eligible": True},
            "tag": "v0.11.0",
            "workflow_run": (
                f"https://github.com/{REPOSITORY}/actions/runs/{RELEASE_RUN}"
            ),
        },
    )
    build(**options)
    verify(**options)


def test_verifies_a_freshly_downloaded_complete_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every special evidence file survives a fresh-download verification."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    build(**options)
    downloaded = tmp_path / "downloaded"
    shutil.copytree(options["asset_root"], downloaded)
    options["asset_root"] = downloaded
    options["artifact_paths"] = [
        downloaded / path.name for path in options["artifact_paths"]
    ]
    for key in (
        "inventory_file",
        "sbom_path",
        "manifest_path",
        "provenance_path",
    ):
        options[key] = downloaded / options[key].name

    verify(**options)


def test_accepts_equivalent_depends_on_direction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both SPDX dependency relationship directions normalize identically."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    sbom = load(options["sbom_path"])
    for relationship in sbom["relationships"]:
        if relationship["relationshipType"] == "DEPENDENCY_OF":
            relationship["relationshipType"] = "DEPENDS_ON"
            (
                relationship["spdxElementId"],
                relationship["relatedSpdxElement"],
            ) = (
                relationship["relatedSpdxElement"],
                relationship["spdxElementId"],
            )
    save(options["sbom_path"], sbom)
    build(**options)
    verify(**options)


def test_accepts_multiple_product_roots_and_rejects_any_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mixed ecosystems use union reachability without hiding orphans."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    sbom = load(options["sbom_path"])
    python_root = next(
        package
        for package in sbom["packages"]
        if package["SPDXID"] == root_id(sbom)
    )
    second_root = copy.deepcopy(python_root)
    second_root["SPDXID"] = "SPDXRef-Package-npm-csarc-repo-cli"
    second_root["externalRefs"] = [
        {
            "referenceCategory": "PACKAGE-MANAGER",
            "referenceType": "purl",
            "referenceLocator": SECOND_ROOT_PURL,
        }
    ]
    sbom["packages"].append(second_root)
    described = next(
        relationship["relatedSpdxElement"]
        for relationship in sbom["relationships"]
        if relationship["relationshipType"] == "DESCRIBES"
    )
    sbom["relationships"].append(
        {
            "spdxElementId": described,
            "relatedSpdxElement": second_root["SPDXID"],
            "relationshipType": "CONTAINS",
        }
    )
    save(options["sbom_path"], sbom)
    write_inventory(options, sbom)
    options["root_purls"] = [SECOND_ROOT_PURL, ROOT_PURL]

    build(**options)
    verify(**options)
    assert load(options["manifest_path"])["root_purls"] == sorted(
        [ROOT_PURL, SECOND_ROOT_PURL]
    )

    orphan = copy.deepcopy(second_root)
    orphan["SPDXID"] = "SPDXRef-Package-orphan-after-two-roots"
    orphan["name"] = "orphan"
    orphan["versionInfo"] = "1.0.0"
    orphan["externalRefs"][0]["referenceLocator"] = "pkg:npm/orphan@1.0.0"
    sbom["packages"].append(orphan)
    save(options["sbom_path"], sbom)
    write_inventory(options, sbom)
    with pytest.raises(ValueError, match="orphan package"):
        build(**options)


@pytest.mark.parametrize("fixture", [SOURCE_FIXTURE, SOURCE_COMPONENTS_FIXTURE])
def test_accepts_genuine_source_runtime_without_inventing_a_root_purl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixture: Path,
) -> None:
    """Source releases accept empty or component-rich genuine Syft scans."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    use_source_fixture(options, fixture)
    build(**options)
    verify(**options)
    assert load(options["manifest_path"])["root_purls"] == []


def test_source_runtime_rejects_fake_roots_and_uncontained_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Source mode requires zero roots and root containment for components."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    options["runtime_kind"] = "source"
    with pytest.raises(ValueError, match="must not declare"):
        build(**options)
    use_source_fixture(options, SOURCE_COMPONENTS_FIXTURE)
    options["root_name"] = "wrong-source"
    with pytest.raises(ValueError, match="source identity"):
        build(**options)
    options["root_name"] = "csarc-repo-cli"
    sbom = load(options["sbom_path"])
    component = next(
        package["SPDXID"]
        for package in sbom["packages"]
        if package.get("externalRefs")
    )
    sbom["relationships"] = [
        relationship
        for relationship in sbom["relationships"]
        if not (
            relationship["relationshipType"] == "CONTAINS"
            and relationship["relatedSpdxElement"] == component
        )
    ]
    save(options["sbom_path"], sbom)
    with pytest.raises(ValueError, match="does not contain"):
        build(**options)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("creator_149", "created by Syft"),
        ("creator_151", "created by Syft"),
        ("document_name", "source identity"),
        ("namespace", "created by Syft"),
        ("created", "created by Syft"),
        ("package_field", "required typed field"),
        ("relationship_field", "relationship fields"),
        ("describes", "exactly one package DESCRIBES"),
        ("containment", "does not contain"),
        ("dangling", "dangling edge"),
        ("truncated", "orphan package"),
        ("missing_purl", "one unique purl"),
        ("root_version", "version does not match"),
        ("orphan", "orphan package"),
    ],
)
def test_rejects_invalid_syft_documents(  # noqa: C901
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    message: str,
) -> None:
    """Schema, creators, roots, and dependency graphs fail closed."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    sbom = load(options["sbom_path"])
    if case.startswith("creator_"):
        version = {"creator_149": "1.49.0", "creator_151": "1.51.0"}[case]
        sbom["creationInfo"]["creators"] = [
            "Organization: Anchore, Inc",
            f"Tool: syft-{version}",
        ]
    elif case == "document_name":
        sbom["name"] = "wrong"
    elif case == "namespace":
        sbom["documentNamespace"] = "not-a-url"
    elif case == "created":
        sbom["creationInfo"]["created"] = "yesterday"
    elif case == "package_field":
        del sbom["packages"][0]["licenseDeclared"]
    elif case == "relationship_field":
        del sbom["relationships"][0]["relationshipType"]
    elif case == "describes":
        described = next(
            relationship
            for relationship in sbom["relationships"]
            if relationship["relationshipType"] == "DESCRIBES"
        )
        sbom["relationships"].append(copy.deepcopy(described))
    elif case == "containment":
        product = root_id(sbom)
        sbom["relationships"] = [
            relationship
            for relationship in sbom["relationships"]
            if not (
                relationship["relationshipType"] == "CONTAINS"
                and relationship["relatedSpdxElement"] == product
            )
        ]
    elif case == "dangling":
        sbom["relationships"].append(
            {
                "spdxElementId": root_id(sbom),
                "relatedSpdxElement": "SPDXRef-Package-missing",
                "relationshipType": "DEPENDS_ON",
            }
        )
    elif case == "truncated":
        sbom["relationships"] = [
            relationship
            for relationship in sbom["relationships"]
            if relationship["relationshipType"] != "DEPENDENCY_OF"
        ]
    elif case == "missing_purl":
        package = next(
            package
            for package in sbom["packages"]
            if package["SPDXID"] == root_id(sbom)
        )
        package["externalRefs"] = [
            reference
            for reference in package["externalRefs"]
            if reference.get("referenceCategory") != "PACKAGE-MANAGER"
        ]
    elif case == "root_version":
        package = next(
            package
            for package in sbom["packages"]
            if package["SPDXID"] == root_id(sbom)
        )
        package["versionInfo"] = "9.9.9"
    else:
        orphan = copy.deepcopy(sbom["packages"][0])
        orphan["SPDXID"] = "SPDXRef-Package-orphan"
        orphan["name"] = "orphan"
        orphan["versionInfo"] = "1.0.0"
        orphan["externalRefs"] = [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": "pkg:pypi/orphan@1.0.0",
            }
        ]
        sbom["packages"].append(orphan)
        write_inventory(options, sbom)
    save(options["sbom_path"], sbom)

    with pytest.raises(ValueError, match=message):
        build(**options)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("name", "name or version"),
        ("version", "name or version"),
        ("ecosystem", "ecosystem is not declared"),
        ("malformed", "purl is malformed"),
        ("bad_escape", "invalid name"),
        ("bad_qualifier", "invalid qualifiers"),
    ],
)
def test_rejects_invalid_transitive_purls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    message: str,
) -> None:
    """Every transitive purl must match its package and declared ecosystem."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    sbom = load(options["sbom_path"])
    package = next(
        package
        for package in sbom["packages"]
        if package["SPDXID"] != root_id(sbom)
        and any(
            reference.get("referenceCategory") == "PACKAGE-MANAGER"
            for reference in package.get("externalRefs", [])
        )
    )
    reference = next(
        reference
        for reference in package["externalRefs"]
        if reference.get("referenceCategory") == "PACKAGE-MANAGER"
    )
    if case == "name":
        reference["referenceLocator"] = (
            f"pkg:pypi/wrong-name@{package['versionInfo']}"
        )
    elif case == "version":
        reference["referenceLocator"] = f"pkg:pypi/{package['name']}@9.9.9"
    elif case == "ecosystem":
        reference["referenceLocator"] = (
            f"pkg:npm/{package['name']}@{package['versionInfo']}"
        )
    elif case == "bad_escape":
        reference["referenceLocator"] = (
            f"pkg:pypi/{package['name']}%ZZ@{package['versionInfo']}"
        )
    elif case == "bad_qualifier":
        reference["referenceLocator"] = (
            f"pkg:pypi/{package['name']}@{package['versionInfo']}?key"
        )
    else:
        reference["referenceLocator"] = "not-a-purl"
    save(options["sbom_path"], sbom)
    write_inventory(options, sbom)

    with pytest.raises(ValueError, match=message):
        build(**options)


@pytest.mark.parametrize("change", ["extra", "missing"])
def test_rejects_inventory_set_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    """The materialized runtime inventory must equal the SPDX package set."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    purls = sbom_purls(load(options["sbom_path"]))
    if change == "extra":
        purls.append("pkg:pypi/extra@1.0.0")
    else:
        purls.pop()
    options["inventory_file"].write_text(
        "".join(f"{purl}\n" for purl in sorted(purls)), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="inventory does not match"):
        build(**options)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("tamper", "provenance bound identity"),
        ("missing", "inventory file is missing"),
        ("extra", "unexpected or missing"),
    ],
)
def test_downloaded_inventory_evidence_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
    message: str,
) -> None:
    """Downloaded inventory bytes and the complete file set remain exact."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    build(**options)
    inventory_path = options["inventory_file"]
    if change == "tamper":
        lines = inventory_path.read_text(encoding="utf-8").splitlines()
        inventory_path.write_text(
            "".join(f"{purl}\n" for purl in reversed(lines)),
            encoding="utf-8",
        )
    elif change == "missing":
        inventory_path.unlink()
    else:
        shutil.copyfile(
            inventory_path, options["asset_root"] / "extra-inventory.purls"
        )

    with pytest.raises(ValueError, match=message):
        verify(**options)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("unexpected", "unexpected or missing"),
        ("nested", "immediate regular child"),
        ("missing", "immediate regular child"),
        ("duplicate", "duplicate release file"),
        ("empty", "release file is empty"),
        ("unsafe", "immediate regular child"),
    ],
)
def test_rejects_non_explicit_release_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    message: str,
) -> None:
    """Only explicitly listed flat non-empty artifacts may enter a release."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    artifact = options["artifact_paths"][0]
    if case == "unexpected":
        (options["asset_root"] / "unexpected.exe").write_bytes(b"unexpected")
    elif case == "nested":
        nested = options["asset_root"] / "nested"
        nested.mkdir()
        nested_artifact = nested / "package.whl"
        nested_artifact.write_bytes(b"nested")
        options["artifact_paths"] = [nested_artifact]
    elif case == "missing":
        options["artifact_paths"] = [options["asset_root"] / "missing.whl"]
    elif case == "empty":
        artifact.write_bytes(b"")
    elif case == "unsafe":
        unsafe = artifact.with_name("unsafe artifact.whl")
        artifact.rename(unsafe)
        options["artifact_paths"] = [unsafe]
    else:
        options["artifact_paths"] = [artifact, artifact]
    with pytest.raises(ValueError, match=message):
        build(**options)


def test_rejects_wrong_git_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A moved tag or mismatched checkout cannot create bindings."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    options["tag"] = "v0.11.1"
    with pytest.raises(ValueError, match="tag and version"):
        build(**options)
    options["tag"] = "v0.11.0"
    options["commit"] = "0" * 40
    with pytest.raises(ValueError, match="checked-out release commit"):
        build(**options)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_run", "01"),
        ("release_run", "not-a-run"),
        ("repository_id", 0),
        ("repository_id", True),
    ],
)
def test_rejects_invalid_external_identity_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    """Repository and workflow identities are strict trust-boundary inputs."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    options[field] = value
    with pytest.raises(ValueError, match=r"run ID|repository ID"):
        build(**options)


def test_rejects_artifact_and_sbom_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every artifact and the unchanged Syft SBOM remain digest-bound."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    build(**options)
    options["artifact_paths"][0].write_bytes(b"tampered")
    with pytest.raises(ValueError, match="provenance bound identity"):
        verify(**options)

    _, options = release_fixture(tmp_path / "second")
    monkeypatch.chdir(tmp_path / "second")
    build(**options)
    sbom = load(options["sbom_path"])
    sbom["documentNamespace"] = "https://anchore.com/syft/changed"
    save(options["sbom_path"], sbom)
    with pytest.raises(ValueError, match="provenance bound identity"):
        verify(**options)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "workflow_run",
            "https://github.com/owner/repo/actions/runs/1",
            "workflow run",
        ),
        ("workflow_run", None, "workflow run"),
        ("guide_url", "https://example.invalid/guide", "guide URL"),
        ("guide_url", None, "guide URL"),
        ("commit_sha", "0" * 40, "release identity"),
        ("release_tag", "v9.9.9", "release identity"),
        ("repository", "other/repo", "bound identity"),
        ("repository_id", 999, "repository ID"),
        ("schema_version", 2, "schema version"),
        ("source_run", "1", "bound identity"),
        ("release_run", "2", "bound identity"),
        ("version", "9.9.9", "bound identity"),
        ("release_source", {"main_sha": "0" * 40}, "source boundary"),
        ("release_source", None, "source boundary"),
        ("unexpected", True, "unexpected field"),
    ],
)
def test_rejects_tampered_provenance_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    message: str,
) -> None:
    """Known provenance fields are exact and unknown fields are rejected."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    build(**options)
    provenance = load(options["provenance_path"])
    provenance[field] = value
    save(options["provenance_path"], provenance)
    with pytest.raises(ValueError, match=message):
        verify(**options)


def test_manifest_binds_finalized_provenance_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Byte-different provenance breaks the terminal DAG."""
    _, options = release_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    build(**options)
    with options["provenance_path"].open("a", encoding="utf-8") as target:
        target.write("\n")
    with pytest.raises(ValueError, match="manifest bindings"):
        verify(**options)
