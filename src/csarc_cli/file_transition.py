"""Approved file transitions and product release state (Issue #1066).

An update may only create, modify, move, or delete exactly the paths the
reviewed plan approved. This module holds the Copier-free rules that keep
the apply step inside that boundary:

- product-owned release state (version, release manifest, and the release
  writer's changelog) is never rewritten or removed by a template seed or
  an update migration once the repository has it;
- a CSARC-owned file the new render no longer produces is retired only
  when its content is byte-identical to the trusted old render; a modified
  file is kept and reported as a ``retire-modified`` conflict;
- the realized candidate effects must equal the approved transitions
  before anything is written; and
- the target receives the approved writes and deletions as one
  transaction that restores the byte-identical base on any failure.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# Product-owned release state: the template only seeds these files. Once a
# repository has one, only its approved release writer may change it.
PRODUCT_RELEASE_STATE = (
    ".csarc/release-please-manifest.json",
    ".csarc/version.txt",
    "CHANGELOG.md",
)
# Legacy locations of the same state; the layout migration relocates them
# with their product content instead of replacing them with a new seed.
LEGACY_PRODUCT_RELEASE_STATE = {
    ".release-please-manifest.json": ".csarc/release-please-manifest.json",
    "version.txt": ".csarc/version.txt",
}


class TransitionError(ValueError):
    """Raised when realized effects leave the approved transitions."""


def fingerprint(path: Path) -> str | None:
    """Hash one file's content and type, or return ``None`` when absent.

    This matches the CLI's managed-file fingerprint: symlink targets and
    the executable bit are part of the identity.
    """
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    digest = hashlib.sha256()
    if stat.S_ISLNK(mode):
        digest.update(b"symlink\0")
        digest.update(os.readlink(path).encode())
    elif stat.S_ISREG(mode):
        digest.update(b"file\0")
        digest.update(b"executable" if mode & 0o111 else b"regular")
        digest.update(b"\0")
        digest.update(path.read_bytes())
    else:
        return None
    return digest.hexdigest()


def render_fingerprints(files: Mapping[str, Path]) -> dict[str, str]:
    """Fingerprint one rendered tree indexed by relative path."""
    result: dict[str, str] = {}
    for name, path in sorted(files.items()):
        value = fingerprint(path)
        if value is not None:
            result[name] = value
    return result


def split_retirements(
    names: Iterable[str],
    target: Path,
    old_render: Mapping[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split retirement candidates into verified retirements and keepers.

    A file is retired only when the trusted old render produced it with the
    exact same bytes and type. Anything else may hold user changes and is
    kept as a ``retire-modified`` conflict. Returns ``(retire, retained)``.
    """
    retire: list[str] = []
    retained: list[str] = []
    for name in sorted(set(names)):
        expected = old_render.get(name)
        if expected is not None and fingerprint(target / name) == expected:
            retire.append(name)
        else:
            retained.append(name)
    return tuple(retire), tuple(retained)


def protect_product_state(
    candidate: Path,
    baseline_files: Collection[str],
    moves: Sequence[tuple[str, str]],
    restore: Callable[[Sequence[str]], None],
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Put the repository's own release state back after a template update.

    ``baseline_files`` lists the paths the candidate held before Copier
    ran and ``restore`` checks those paths out again. A canonical path
    keeps its baseline content; a legacy path that the layout migration
    moves carries its product content to the canonical path. A seed only
    reaches a repository that has no such state yet. Returns the protected
    canonical paths and the layout moves this step already completed.
    """
    baseline = set(baseline_files)
    sources: dict[str, str] = {}
    for canonical in PRODUCT_RELEASE_STATE:
        if canonical in baseline:
            sources[canonical] = canonical
            continue
        for source, destination in moves:
            if destination == canonical and source in baseline:
                sources[canonical] = source
                break
    if not sources:
        return (), ()
    restore(sorted(set(sources.values())))
    completed: list[tuple[str, str]] = []
    for canonical, source in sorted(sources.items()):
        if source == canonical:
            continue
        origin = candidate / source
        destination = candidate / canonical
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            destination.unlink()
        origin.replace(destination)
        completed.append((source, canonical))
    return tuple(sorted(sources)), tuple(completed)


def protect_deletions(
    candidate: Path,
    baseline_files: Collection[str],
    old_render: Mapping[str, str],
    skip: Collection[str],
    restore: Callable[[Sequence[str]], None],
) -> tuple[str, ...]:
    """Undo every deletion the trusted old render cannot justify.

    Copier removes a file whenever the old render had it and the new render
    does not, even when the repository changed it. Each such path is
    checked out again; it is deleted only when its content equals the
    trusted old render. Returns the retained, user-modified paths.
    """
    skipped = set(skip)
    deleted = sorted(
        name
        for name in baseline_files
        if name not in skipped
        and not (candidate / name).exists()
        and not (candidate / name).is_symlink()
    )
    if not deleted:
        return ()
    restore(deleted)
    retained: list[str] = []
    for name in deleted:
        path = candidate / name
        expected = old_render.get(name)
        if expected is not None and fingerprint(path) == expected:
            path.unlink()
        else:
            retained.append(name)
    return tuple(retained)


@dataclass(frozen=True)
class ApprovedTransitions:
    """Every target path an approved update plan may create or change.

    ``optional`` lists CLI-owned metadata (answers and provenance) that the
    apply step rewrites from the same reviewed inputs; it may change but is
    never required to.
    """

    create: frozenset[str]
    modify: frozenset[str]
    delete: frozenset[str]
    optional: frozenset[str]
    protected: frozenset[str]

    def as_dict(self) -> dict[str, list[str]]:
        """Return the approved transitions as sorted lists."""
        return {
            "create": sorted(self.create),
            "delete": sorted(self.delete),
            "modify": sorted(self.modify),
            "optional": sorted(self.optional),
            "protected": sorted(self.protected),
        }


def approved_transitions(
    *,
    add: Collection[str],
    overwrite: Collection[str],
    merge: Collection[str],
    delete: Collection[str],
    retire: Collection[str],
    moves: Collection[tuple[str, str]],
    target_files: Collection[str],
    metadata: Collection[str],
    protected: Collection[str] = (),
) -> ApprovedTransitions:
    """Build the exact transition set an update plan approved."""
    existing = set(target_files)
    create = set(add)
    modify = set(overwrite) | set(merge)
    removed = set(delete) | set(retire)
    optional = set(metadata)
    for source, destination in moves:
        removed.add(source)
        if destination in existing:
            # An identical destination stays as it is; the move only
            # removes the legacy copy.
            optional.add(destination)
        else:
            create.add(destination)
    return ApprovedTransitions(
        frozenset(create - optional),
        frozenset(modify - optional),
        frozenset(removed - optional),
        frozenset(optional),
        frozenset(protected),
    )


def transition_divergence(
    approved: ApprovedTransitions,
    writes: Collection[str],
    deletions: Collection[str],
    target_files: Collection[str],
) -> list[str]:
    """Describe every realized effect outside the approved transitions."""
    existing = set(target_files)
    created = {name for name in writes if name not in existing}
    modified = {name for name in writes if name in existing}
    removed = set(deletions)
    problems: list[str] = []
    touched_protected = sorted(
        approved.protected & ((modified | removed) - approved.optional)
    )
    if touched_protected:
        problems.append(
            "product release state changed: " + ", ".join(touched_protected)
        )
    for label, realized, planned in (
        ("create", created, approved.create),
        ("modify", modified, approved.modify),
        ("delete", removed, approved.delete),
    ):
        extra = sorted(realized - planned - approved.optional)
        if extra:
            problems.append(f"unapproved {label}: " + ", ".join(extra))
        missing = sorted(planned - realized)
        if missing:
            problems.append(
                f"approved {label} not realized: " + ", ".join(missing)
            )
    return problems


def tree_digest(root: Path) -> str:
    """Digest every path under ``root`` except ``.git`` metadata."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] == ".git":
            continue
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            digest.update(b"dir\0" + relative.as_posix().encode() + b"\0")
            continue
        digest.update(relative.as_posix().encode() + b"\0")
        digest.update((fingerprint(path) or "special").encode() + b"\0")
    return digest.hexdigest()


def _copy_entry(source: Path, destination: Path) -> None:
    """Copy one regular file or symlink with its mode."""
    if source.is_symlink():
        destination.symlink_to(os.readlink(source))
    else:
        shutil.copy2(source, destination)


def _remove_entry(path: Path) -> None:
    """Remove one file or symlink when present."""
    if path.is_symlink() or path.exists():
        path.unlink()


def _staging_path(path: Path) -> Path:
    """Return the sibling temporary name one transactional write uses."""
    return path.parent / f".{path.name}.csarc-transaction"


class _Transaction:
    """Backed-up, reversible file writes and deletions in one target."""

    def __init__(self, target: Path, backup_root: Path) -> None:
        self.target = target
        self.backup_root = backup_root
        self.saved: dict[str, Path] = {}
        self.changed: list[str] = []
        self.created_directories: list[Path] = []

    def backup(self, names: Sequence[str]) -> None:
        """Copy every existing path before anything changes."""
        for index, name in enumerate(names):
            path = self.target / name
            if path.is_symlink() or path.exists():
                copy = self.backup_root / str(index)
                _copy_entry(path, copy)
                self.saved[name] = copy

    def write(self, name: str, source: Path) -> None:
        """Replace one path atomically with the candidate content."""
        path = self.target / name
        self.changed.append(name)
        missing: list[Path] = []
        parent = path.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        path.parent.mkdir(parents=True, exist_ok=True)
        self.created_directories.extend(reversed(missing))
        staged = _staging_path(path)
        _remove_entry(staged)
        _copy_entry(source, staged)
        staged.replace(path)

    def delete(self, name: str) -> None:
        """Remove one path; its backup restores it on rollback."""
        self.changed.append(name)
        _remove_entry(self.target / name)

    def rollback(self) -> None:
        """Restore every changed path and remove created directories."""
        for name in reversed(self.changed):
            path = self.target / name
            _remove_entry(_staging_path(path))
            _remove_entry(path)
            if name in self.saved:
                path.parent.mkdir(parents=True, exist_ok=True)
                _copy_entry(self.saved[name], path)
        for directory in reversed(self.created_directories):
            try:
                directory.rmdir()
            except OSError:
                continue


def _realized_mismatches(
    target: Path, writes: Mapping[str, str], deletions: Sequence[str]
) -> list[str]:
    """Return paths whose applied state differs from the approved one."""
    mismatched = [
        name
        for name, expected in sorted(writes.items())
        if fingerprint(target / name) != expected
    ]
    mismatched.extend(
        name
        for name in sorted(deletions)
        if (target / name).exists() or (target / name).is_symlink()
    )
    return mismatched


def _remove_empty_parents(target: Path, deletions: Sequence[str]) -> None:
    """Remove directories a committed deletion left empty."""
    for name in deletions:
        parent = (target / name).parent
        while parent != target:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def apply_transaction(
    target: Path,
    candidate: Path,
    writes: Mapping[str, str],
    deletions: Sequence[str],
    *,
    on_step: Callable[[str], None] | None = None,
) -> None:
    """Apply approved writes and deletions to the target atomically.

    ``writes`` maps each path to the fingerprint the candidate must hold.
    Every existing path is backed up first; each write lands through a
    sibling temporary file and an atomic rename. Any failure, including a
    final content mismatch, restores the byte-identical base: backed-up
    files return, created files and directories disappear, and no
    ``.rej`` file or conflict marker is ever produced. ``on_step`` runs
    before each path changes; tests use it to inject failures.
    """
    touched = sorted(set(writes) | set(deletions))
    with tempfile.TemporaryDirectory(prefix="csarc-transaction-") as backup:
        transaction = _Transaction(target, Path(backup))
        transaction.backup(touched)
        try:
            for name in touched:
                if on_step is not None:
                    on_step(name)
                if name in writes:
                    transaction.write(name, candidate / name)
                else:
                    transaction.delete(name)
            mismatched = _realized_mismatches(target, writes, deletions)
            if mismatched:
                raise TransitionError(
                    "Applied content differs from the approved candidate: "
                    + ", ".join(mismatched)
                )
        except BaseException:
            transaction.rollback()
            raise
    _remove_empty_parents(target, deletions)
