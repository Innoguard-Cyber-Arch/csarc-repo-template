"""Read-only product action pin preflight for ``csarc update`` (#1065).

A consumer's verification fails when a product-owned workflow pins a
GitHub Action at a different commit than the template-managed workflows
(``check_action_pins.py``). An update that bumps a template pin therefore
breaks verification long after the plan was approved. This module lists
that drift before any Copier render, plan, or target write:

- the new pins are read from the template source at the exact reviewed
  commit through Git only; nothing is rendered;
- ownership comes from the template's own workflow names and the
  ``_exclude`` conditions evaluated against the reviewed answers;
- every product-owned workflow pin of an action the template also pins is
  compared with the template's single full-SHA pin.

The preflight never writes product files. A drift item is resolved by a
manual product commit; :func:`validate_pin_decisions` accepts only
decisions that name every item and read back from that commit, and
:func:`unlisted_pin_changes` proves a pin commit changed nothing else.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml  # type: ignore[import-untyped]

SCHEMA_VERSION = 1
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
# The same pin shape scripts/check_action_pins.py governs; a quoted or
# tag-pinned reference is outside that check and therefore never drifts.
USES = re.compile(
    r"^\s*(?:-\s+)?uses:\s*([\w.-]+/[\w.-]+(?:/[\w./-]+)?)@([0-9a-f]{40})"
)
WORKFLOW_DIRECTORY = ".github/workflows"
WORKFLOW_SUFFIXES = (".yml", ".yaml")
TEMPLATE_SUFFIX = ".jinja"
REASON_TEMPLATE_PIN_CHANGED = "template-pin-changed"
REASON_PRODUCT_PIN_DIVERGED = "product-pin-diverged"
REASONS = (REASON_TEMPLATE_PIN_CHANGED, REASON_PRODUCT_PIN_DIVERGED)
ITEM_KEYS = ("action", "file", "line", "new_sha", "old_sha", "reason")
DECISION_KEYS = (*ITEM_KEYS, "commit_sha")

GitRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class PinPreflightError(ValueError):
    """Raised when pins cannot be read or verified; the update stops."""


@dataclass(frozen=True)
class PinDrift:
    """One product-owned pin that disagrees with the new template pin."""

    file: str
    line: int
    action: str
    old_sha: str
    new_sha: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        """Return the stable machine-readable item."""
        return {
            "action": self.action,
            "file": self.file,
            "line": self.line,
            "new_sha": self.new_sha,
            "old_sha": self.old_sha,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PinPreflight:
    """The complete read-only preflight result for one update."""

    source_sha: str
    product_workflows: tuple[str, ...]
    items: tuple[PinDrift, ...]

    @property
    def state(self) -> str:
        """Return ``drift`` when any item exists, otherwise ``clean``."""
        return "drift" if self.items else "clean"

    def as_dict(self) -> dict[str, object]:
        """Return the plan payload; an empty ``items`` list means no drift."""
        return {
            "items": [item.as_dict() for item in self.items],
            "product_workflows": list(self.product_workflows),
            "schema_version": SCHEMA_VERSION,
            "source_sha": self.source_sha,
            "state": self.state,
        }


def parse_pins(text: str) -> list[tuple[int, str, str]]:
    """Return every full-SHA ``uses:`` pin as (1-based line, action, sha)."""
    pins: list[tuple[int, str, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = USES.match(line)
        if match is not None:
            pins.append((number, match.group(1), match.group(2)))
    return pins


def template_pins(files: Mapping[str, str]) -> dict[str, str]:
    """Return the single trusted pin per action across template workflows.

    The template's own ``check_action_pins.py`` keeps every pin of one
    action identical; disagreement means no single new SHA can be trusted.
    """
    seen: dict[str, set[str]] = {}
    for text in files.values():
        for _line, action, sha in parse_pins(text):
            seen.setdefault(action, set()).add(sha)
    ambiguous = sorted(action for action, shas in seen.items() if len(shas) > 1)
    if ambiguous:
        raise PinPreflightError(
            "Template source pins disagree for "
            + ", ".join(ambiguous)
            + "; no single trusted new SHA exists."
        )
    return {action: next(iter(shas)) for action, shas in seen.items()}


def _render_excludes(
    entries: Sequence[object], answers: Mapping[str, object]
) -> list[str]:
    """Render Copier ``_exclude`` entries with the reviewed answers."""
    from jinja2.sandbox import SandboxedEnvironment

    environment = SandboxedEnvironment(autoescape=False)
    rendered: list[str] = []
    for entry in entries:
        if not isinstance(entry, str):
            raise PinPreflightError("Template _exclude entries must be text.")
        try:
            rendered.append(
                environment.from_string(entry).render(dict(answers)).strip()
            )
        except Exception as error:
            raise PinPreflightError(
                f"Cannot evaluate template _exclude entry {entry!r}: {error}"
            ) from error
    return [item for item in rendered if item]


def _excluded(path: str, patterns: Sequence[str]) -> bool:
    """Match the plain gitwildmatch subset Copier exclusions use."""
    for pattern in patterns:
        anchored = pattern.lstrip("/").rstrip("/")
        if not anchored:
            continue
        if path == anchored or path.startswith(anchored + "/"):
            return True
        if "/" in pattern.strip("/"):
            if fnmatch.fnmatchcase(path, anchored):
                return True
        elif any(
            fnmatch.fnmatchcase(part, anchored)
            for part in PurePosixPath(path).parts
        ):
            return True
    return False


def managed_workflows(
    template_files: Mapping[str, str],
    copier_config: Mapping[str, object],
    answers: Mapping[str, object],
) -> set[str]:
    """Return the target workflow paths the template renders for answers."""
    raw_excludes = copier_config.get("_exclude", [])
    if not isinstance(raw_excludes, list):
        raise PinPreflightError("Template _exclude must be a list.")
    excludes = _render_excludes(raw_excludes, answers)
    managed: set[str] = set()
    for name in template_files:
        output = name.removesuffix(TEMPLATE_SUFFIX)
        if "{{" in output or "{%" in output:
            raise PinPreflightError(
                f"Template workflow name {name!r} is templated; ownership "
                "cannot be resolved without a render."
            )
        path = f"{WORKFLOW_DIRECTORY}/{output}"
        if not _excluded(path, excludes):
            managed.add(path)
    return managed


def _git_text(git: GitRunner, command: list[str], detail: str) -> str:
    result = git(command)
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip() or "git failed"
        raise PinPreflightError(f"{detail}: {output}")
    return result.stdout


def _clone_url(source: str) -> str:
    if source.startswith("gh:"):
        return f"https://github.com/{source.removeprefix('gh:')}.git"
    return source


def _source_repository(
    git: GitRunner, source: str, sha: str, scratch: Path
) -> list[str]:
    """Return a Git command prefix for a repository holding ``sha``."""
    local = Path(source).expanduser()
    if local.is_dir():
        repository = local.resolve()
    else:
        repository = scratch / "source.git"
        _git_text(
            git,
            ["git", "init", "--quiet", "--bare", str(repository)],
            "Cannot prepare the template pin source",
        )
        _git_text(
            git,
            [
                "git",
                "-C",
                str(repository),
                "fetch",
                "--quiet",
                "--depth",
                "1",
                "--no-tags",
                _clone_url(source),
                sha,
            ],
            "Template pin source is unreachable",
        )
    base = ["git", "-C", str(repository)]
    resolved = _git_text(
        git,
        [*base, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
        "Template pin source does not contain the reviewed commit",
    ).strip()
    if resolved != sha:
        raise PinPreflightError(
            f"Template pin source resolved {resolved!r}, not the reviewed "
            f"commit {sha}."
        )
    return base


def _read_copier_config(
    git: GitRunner, base: list[str], sha: str
) -> dict[str, object]:
    names = _git_text(
        git,
        [*base, "ls-tree", "--name-only", sha, "--", "copier.yml"],
        "Cannot list the template configuration",
    ).split()
    if names != ["copier.yml"]:
        raise PinPreflightError(
            "Template source has no copier.yml at the reviewed commit."
        )
    text = _git_text(
        git,
        [*base, "cat-file", "blob", f"{sha}:copier.yml"],
        "Cannot read the template configuration",
    )
    try:
        config = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise PinPreflightError(
            f"Template copier.yml cannot be parsed: {error}"
        ) from error
    if not isinstance(config, dict):
        raise PinPreflightError("Template copier.yml must be a mapping.")
    return config


def _read_template_workflows(
    git: GitRunner, base: list[str], sha: str, subdirectory: object
) -> dict[str, str]:
    if not isinstance(subdirectory, str):
        raise PinPreflightError("Template _subdirectory must be text.")
    prefix = PurePosixPath(subdirectory.strip("/"), WORKFLOW_DIRECTORY)
    listing = _git_text(
        git,
        [*base, "ls-tree", "-z", sha, f"{prefix.as_posix()}/"],
        "Cannot list template workflows",
    )
    files: dict[str, str] = {}
    for record in filter(None, listing.split("\0")):
        meta, _tab, path = record.partition("\t")
        mode, kind, _object = meta.split()
        name = PurePosixPath(path).name
        if kind != "blob" or mode not in {"100644", "100755"}:
            continue
        if name.removesuffix(TEMPLATE_SUFFIX).endswith(WORKFLOW_SUFFIXES):
            files[name] = _git_text(
                git,
                [*base, "cat-file", "blob", f"{sha}:{path}"],
                f"Cannot read template workflow {path}",
            )
    return files


def read_template_source(
    git: GitRunner, source: str, sha: str
) -> tuple[dict[str, object], dict[str, str]]:
    """Read ``copier.yml`` and template workflows at one exact commit.

    Returns the parsed Copier configuration and the template workflow files
    keyed by their name inside the template workflow directory. Nothing is
    checked out or rendered; every blob is read from the verified commit.
    """
    if FULL_SHA.fullmatch(sha) is None:
        raise PinPreflightError(
            f"Template revision {sha!r} is not a full commit SHA; the pin "
            "source cannot be verified."
        )
    with tempfile.TemporaryDirectory(prefix="csarc-pin-source-") as scratch:
        base = _source_repository(git, source, sha, Path(scratch))
        config = _read_copier_config(git, base, sha)
        files = _read_template_workflows(
            git, base, sha, config.get("_subdirectory", "")
        )
    return config, files


def _target_workflows(target: Path) -> dict[str, str]:
    """Read every target workflow file, failing closed on unsafe entries."""
    directory = target / WORKFLOW_DIRECTORY
    if directory.is_symlink():
        raise PinPreflightError(
            f"{WORKFLOW_DIRECTORY} is a symlink; workflow pins cannot be "
            "verified."
        )
    if not directory.is_dir():
        return {}
    files: dict[str, str] = {}
    for path in sorted(directory.iterdir()):
        if not path.name.endswith(WORKFLOW_SUFFIXES):
            continue
        relative = f"{WORKFLOW_DIRECTORY}/{path.name}"
        if path.is_symlink() or not path.is_file():
            raise PinPreflightError(
                f"{relative} is not a regular file; its pins cannot be parsed."
            )
        try:
            files[relative] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise PinPreflightError(
                f"{relative} cannot be parsed as UTF-8 text: {error}"
            ) from error
    return files


def evaluate(
    target_files: Mapping[str, str],
    managed: set[str],
    new_pins: Mapping[str, str],
    source_sha: str,
) -> PinPreflight:
    """Compare product-owned pins with the new template pins."""
    product = sorted(path for path in target_files if path not in managed)
    current_template: dict[str, set[str]] = {}
    for path, text in target_files.items():
        if path in managed:
            for _line, action, sha in parse_pins(text):
                current_template.setdefault(action, set()).add(sha)
    items: list[PinDrift] = []
    for path in product:
        for line, action, sha in parse_pins(target_files[path]):
            new_sha = new_pins.get(action)
            if new_sha is None or new_sha == sha:
                continue
            reason = (
                REASON_TEMPLATE_PIN_CHANGED
                if sha in current_template.get(action, set())
                else REASON_PRODUCT_PIN_DIVERGED
            )
            items.append(PinDrift(path, line, action, sha, new_sha, reason))
    return PinPreflight(source_sha, tuple(product), tuple(items))


def run_preflight(
    target: Path,
    source: str,
    sha: str,
    answers: Mapping[str, object],
    git: GitRunner,
) -> PinPreflight:
    """Run the complete read-only preflight for one reviewed revision."""
    config, files = read_template_source(git, source, sha)
    new_pins = template_pins(files)
    for action, pin in new_pins.items():
        if FULL_SHA.fullmatch(pin) is None:
            raise PinPreflightError(
                f"Template pin for {action} is not a full commit SHA."
            )
    managed = managed_workflows(files, config, answers)
    return evaluate(_target_workflows(target), managed, new_pins, sha)


def repair_commands(items: Sequence[PinDrift]) -> list[str]:
    """Return one manual repair instruction per drift item."""
    return [
        f"{item.file}:{item.line}: change {item.action}@{item.old_sha} to "
        f"{item.action}@{item.new_sha}"
        for item in items
    ]


def drift_error(preflight: PinPreflight) -> str:
    """Explain why an update refuses to plan for apply with drift."""
    lines = [
        "Product action pins drift from the new template pins; the target "
        "was not changed. Commit these product pin changes, then rerun the "
        "update:",
        *(f"  - {line}" for line in repair_commands(preflight.items)),
    ]
    return "\n".join(lines)


def _item_key(item: Mapping[str, object]) -> tuple[object, ...]:
    return tuple(item.get(key) for key in ITEM_KEYS)


def _read_back_decision(
    decision: Mapping[str, object], git: GitRunner, target: Path
) -> None:
    """Prove one decision's commit exists, is merged, and pins the line."""
    commit = decision["commit_sha"]
    if not isinstance(commit, str) or FULL_SHA.fullmatch(commit) is None:
        raise PinPreflightError(
            "A pin decision commit must be a full lowercase commit SHA."
        )
    base = ["git", "-C", str(target)]
    resolved = _git_text(
        git,
        [*base, "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
        f"Pin commit {commit} cannot be read back",
    ).strip()
    if resolved != commit:
        raise PinPreflightError(f"Pin commit {commit} cannot be read back.")
    ancestry = git([*base, "merge-base", "--is-ancestor", commit, "HEAD"])
    if ancestry.returncode != 0:
        raise PinPreflightError(
            f"Pin commit {commit} is not in the target's history."
        )
    text = _git_text(
        git,
        [*base, "cat-file", "blob", f"{commit}:{decision['file']}"],
        f"Pin commit {commit} has no {decision['file']}",
    )
    pinned = [pin for pin in parse_pins(text) if pin[0] == decision["line"]]
    if pinned != [(decision["line"], decision["action"], decision["new_sha"])]:
        raise PinPreflightError(
            f"Pin commit {commit} does not pin {decision['action']}@"
            f"{decision['new_sha']} at {decision['file']}:"
            f"{decision['line']}."
        )


def validate_pin_decisions(
    items: Sequence[Mapping[str, object]],
    decisions: Sequence[Mapping[str, object]],
    git: GitRunner,
    target: Path,
) -> list[dict[str, object]]:
    """Accept only complete manual pin decisions that read back by SHA.

    Every preflight item needs exactly one decision with identical fields
    plus ``commit_sha``; the commit must be in the target's history and
    must pin the new SHA on the recorded line. Returns the normalized
    decisions in item order.
    """
    expected = {_item_key(item) for item in items}
    if len(expected) != len(items):
        raise PinPreflightError("Preflight items must be unique.")
    accepted: dict[tuple[object, ...], dict[str, object]] = {}
    for decision in decisions:
        if set(decision) != set(DECISION_KEYS):
            raise PinPreflightError(
                "A pin decision must carry exactly "
                + ", ".join(DECISION_KEYS)
                + "."
            )
        key = _item_key(decision)
        where = f"{decision.get('file')}:{decision.get('line')}"
        if key not in expected:
            raise PinPreflightError(
                f"Pin decision for {where} is not a preflight item."
            )
        if key in accepted:
            raise PinPreflightError(f"Pin decision for {where} is duplicated.")
        _read_back_decision(decision, git, target)
        accepted[key] = {name: decision[name] for name in DECISION_KEYS}
    missing = [key for key in expected if key not in accepted]
    if missing:
        raise PinPreflightError(
            "Every preflight item needs a committed pin decision; missing "
            + ", ".join(sorted(f"{key[1]}:{key[2]}" for key in missing))
            + "."
        )
    return [accepted[_item_key(item)] for item in items]


_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class _FileDiff:
    """The zero-context changes Git reports for one file."""

    path: str
    headers: list[str]
    removed: list[tuple[int, str]]
    added: list[tuple[int, str]]


def _parse_patch(patch: str) -> list[_FileDiff]:
    """Split a ``--unified=0`` patch into per-file line changes."""
    files: list[_FileDiff] = []
    current: _FileDiff | None = None
    removed_at = added_at = 0
    for raw in patch.splitlines():
        if raw.startswith("diff --git "):
            current = _FileDiff(raw.partition(" b/")[2] or raw, [], [], [])
            files.append(current)
            removed_at = added_at = 0
        elif current is None:
            continue
        elif (match := _HUNK.match(raw)) is not None:
            removed_at, added_at = int(match.group(1)), int(match.group(2))
        elif not removed_at and not added_at:
            current.headers.append(raw)
        elif raw.startswith("-"):
            current.removed.append((removed_at, raw[1:]))
            removed_at += 1
        elif raw.startswith("+"):
            current.added.append((added_at, raw[1:]))
            added_at += 1
    return files


def _unlisted_in_file(
    change: _FileDiff, allowed: Mapping[tuple[str, int], Mapping[str, object]]
) -> list[str]:
    # Only index and ---/+++ headers are expected; a mode change, new,
    # deleted, or binary file is never a listed pin edit.
    unlisted = [
        f"{change.path}: {header}"
        for header in change.headers
        if not header.startswith(("index ", "--- ", "+++ "))
    ]
    if len(change.removed) != len(change.added):
        return [*unlisted, f"{change.path}: lines added or removed"]
    for (old_line, before), (new_line, after) in zip(
        change.removed, change.added, strict=True
    ):
        item = allowed.get((change.path, new_line))
        if (
            item is None
            or old_line != new_line
            or f"{item['action']}@{item['old_sha']}" not in before
            or before.replace(str(item["old_sha"]), str(item["new_sha"]))
            != after
        ):
            unlisted.append(f"{change.path}:{new_line}")
    return unlisted


def unlisted_pin_changes(
    items: Sequence[Mapping[str, object]],
    git: GitRunner,
    target: Path,
    commit: str,
) -> list[str]:
    """Return every change in one pin commit outside the preflight list.

    An allowed change replaces exactly one listed line, keeping the line
    identical except for the old SHA becoming the new SHA. An empty list
    proves the commit modified nothing beyond the preflight items.
    """
    if FULL_SHA.fullmatch(commit) is None:
        raise PinPreflightError("A pin commit must be a full commit SHA.")
    allowed = {
        (str(item["file"]), int(str(item["line"]))): item for item in items
    }
    patch = _git_text(
        git,
        [
            "git",
            "-C",
            str(target),
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "--unified=0",
            f"{commit}^",
            commit,
        ],
        f"Cannot read pin commit {commit}",
    )
    return [
        entry
        for change in _parse_patch(patch)
        for entry in _unlisted_in_file(change, allowed)
    ]
