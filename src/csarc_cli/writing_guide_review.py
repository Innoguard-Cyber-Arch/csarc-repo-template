"""Read-only writing-guide review prompt for project-owned documents (#1224).

The template never rewrites content-layer documents. When a project
receives the writing guides for the first time, or receives a changed
version, the lifecycle report lists the project-owned documents and
recommends a review. This module only reads files; it never writes.

The guide version is the SHA-256 digest of the rendered guide files. The
CLI records the version it prompted for in `.csarc/provenance.json`
(``PROVENANCE_KEY``), so the same version is not prompted again.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Mapping
from pathlib import Path

GUIDE_PATHS = (
    ".csarc/docs/writing-guide.en.md",
    ".csarc/docs/writing-guide.md",
)
PROVENANCE_KEY = "writing_guide_sha256"
INSTRUCTION = (
    "Review each listed file against the listed guides, propose edits, "
    "and change only the text the owner approves."
)


def _regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def received_guides(root: Path) -> list[str]:
    """Return the guide paths that exist as regular files under ``root``."""
    return [name for name in GUIDE_PATHS if _regular_file(root / name)]


def guide_version(root: Path) -> str | None:
    """Return the digest of the guides under ``root``, or None without one."""
    guides = received_guides(root)
    if not guides:
        return None
    digest = hashlib.sha256()
    for name in guides:
        digest.update(name.encode() + b"\0")
        digest.update((root / name).read_bytes() + b"\0")
    return digest.hexdigest()


def project_documents(root: Path, languages: object) -> list[str]:
    """List the project-owned README files and Markdown files in ``docs/``."""
    names = ["README.md"]
    if isinstance(languages, str) and "+" in languages:
        names.append(f"README.{languages.split('+')[1]}.md")
    found = [name for name in names if _regular_file(root / name)]
    docs = root / "docs"
    if docs.is_dir() and not docs.is_symlink():
        for directory, subdirectories, files in os.walk(docs):
            subdirectories.sort()
            for name in files:
                path = Path(directory) / name
                if name.endswith(".md") and _regular_file(path):
                    found.append(path.relative_to(root).as_posix())
    return sorted(set(found))


def recorded_version(provenance: Mapping[str, object] | None) -> str | None:
    """Return the guide version the last operation prompted for."""
    value = None if provenance is None else provenance.get(PROVENANCE_KEY)
    return value if isinstance(value, str) else None


def version_to_record(root: Path, answers: Mapping[str, object]) -> str | None:
    """Return the version to record after an operation writes ``root``."""
    if answers.get("documentation_mode") == "off":
        return None
    return guide_version(root)


def review_prompt(
    received: Path,
    documents: Path,
    answers: Mapping[str, object],
    recorded: str | None,
) -> dict[str, object] | None:
    """Return the report prompt, or None when no review is due.

    ``received`` holds the rendered guides, ``documents`` the project-owned
    documents. ``documentation_mode: off`` never prompts.
    """
    version = version_to_record(received, answers)
    if version is None or version == recorded:
        return None
    return {
        "files": project_documents(
            documents, answers.get("documentation_languages")
        ),
        "guides": received_guides(received),
        "instruction": INSTRUCTION,
        "reason": "first" if recorded is None else "changed",
    }
