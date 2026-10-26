"""Shared update planning inputs and normalized results (Issue #1063).

``csarc update --check`` and the apply path build one immutable
:class:`UpdatePlanning` through the same planner. The old side of the
three-way update is rebuilt only from answers the old template actually
asked for, plus a trusted provenance snapshot; current defaults and
questions the old template never asked are never injected into it. Both
paths then read the conflict set and file actions from the same normalized
diff, so a reviewed check and an apply against the same base agree.

This module holds the pure, Copier-free part of that contract so it can be
tested without rendering a template.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

OLD_SOURCE_LEGACY = "legacy-answers"
OLD_SOURCE_SNAPSHOT = "trusted-snapshot"
OLD_SOURCE_DEFAULT = "old-template-default"
OLD_SOURCES = (OLD_SOURCE_LEGACY, OLD_SOURCE_SNAPSHOT, OLD_SOURCE_DEFAULT)

RENDER_PARITY_EQUAL = "equal"
RENDER_PARITY_DIVERGED = "diverged"

# Verified provenance records the release contract under these fields. A
# legacy old template may still ask for the flattened release_* answers.
SNAPSHOT_RELEASE_FIELDS = {
    "immutable_releases": "release_immutable_releases",
    "ownership": "release_ownership",
    "reason": "release_ownership_reason",
    "required_inputs": "release_required_inputs",
    "selected_workflow": "release_workflow",
    "settings_owner": "release_settings_owner",
}


class UpdatePlanningError(ValueError):
    """Raised when update inputs cannot be trusted; nothing is written."""


def canonical_digest(value: object) -> str:
    """Return a stable SHA-256 digest of one JSON-compatible value."""
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class OldSideInputs:
    """Exact answers the old template receives, with each key's source.

    ``answers`` never contains a key the old template did not ask for.
    A key the old template asked for but no trusted input supplies is
    listed under ``OLD_SOURCE_DEFAULT``: Copier fills it from the old
    template's own default, never from the current template's default.

    ``context`` holds reviewed new-side values for keys the old template
    never asks. Copier evaluates the *new* template's ``_exclude`` rules
    while rebuilding the old side, so those rules need the same values the
    new side uses; the keys can never override an old answer, and the
    planner proves they did not change the old render by comparing the
    rebuilt baseline with the target (render parity).
    """

    answers: Mapping[str, object]
    sources: Mapping[str, str]
    dropped: tuple[str, ...]
    context: Mapping[str, object] = field(default_factory=dict)

    def copier_answers(self) -> dict[str, object]:
        """Return the exact answers written for Copier's old side."""
        merged = dict(self.context)
        merged.update(self.answers)
        return dict(sorted(merged.items()))

    def with_context(self, new_data: Mapping[str, object]) -> OldSideInputs:
        """Add new-side values for keys the old template never asks."""
        context = {
            key: value
            for key, value in sorted(new_data.items())
            if key not in self.sources
        }
        return OldSideInputs(self.answers, self.sources, self.dropped, context)

    def as_dict(self) -> dict[str, object]:
        """Return an auditable summary that names keys but not values."""
        return {
            "answers_sha256": canonical_digest(self.copier_answers()),
            "context_keys": sorted(self.context),
            "defaulted": sorted(
                key
                for key, source in self.sources.items()
                if source == OLD_SOURCE_DEFAULT
            ),
            "dropped": list(self.dropped),
            "keys": sorted(self.answers),
            "snapshot": sorted(
                key
                for key, source in self.sources.items()
                if source == OLD_SOURCE_SNAPSHOT
            ),
        }


def asked_keys(rendered_answers: Mapping[str, object]) -> frozenset[str]:
    """Return the questions a rendered Copier answers file recorded."""
    return frozenset(
        key
        for key in rendered_answers
        if isinstance(key, str) and not key.startswith("_")
    )


def trusted_snapshot(
    provenance: Mapping[str, object] | None,
) -> dict[str, object]:
    """Return release answers recorded by verified provenance only.

    Unverified or legacy-format provenance is never a trusted snapshot; it
    is only a hint that a migration is needed.
    """
    if provenance is None or provenance.get("verification") != "verified":
        return {}
    release = provenance.get("release")
    if not isinstance(release, Mapping):
        return {}
    snapshot: dict[str, object] = {}
    for field_name, answer_key in SNAPSHOT_RELEASE_FIELDS.items():
        if field_name not in release:
            continue
        value = release[field_name]
        if field_name == "selected_workflow":
            value = value or ""
        if value is None:
            continue
        snapshot[answer_key] = value
    return snapshot


def reconstruct_old_inputs(
    saved: Mapping[str, object],
    asked: Collection[str],
    snapshot: Mapping[str, object],
) -> OldSideInputs:
    """Rebuild the old-side answers from legacy answers and a snapshot.

    ``saved`` is the repository's persisted answers file without Copier's
    ``_`` metadata, ``asked`` is the set of questions the old template
    recorded when rendered with those answers, and ``snapshot`` is the
    verified provenance snapshot. Saved answers win over the snapshot
    because they are what the old render actually consumed.
    """
    answers: dict[str, object] = {}
    sources: dict[str, str] = {}
    for key in sorted(asked):
        if key in saved:
            answers[key] = saved[key]
            sources[key] = OLD_SOURCE_LEGACY
        elif key in snapshot:
            answers[key] = snapshot[key]
            sources[key] = OLD_SOURCE_SNAPSHOT
        else:
            sources[key] = OLD_SOURCE_DEFAULT
    dropped = tuple(
        sorted(
            key
            for key in saved
            if not key.startswith("_") and key not in set(asked)
        )
    )
    return OldSideInputs(answers, sources, dropped)


def require_stable_old_inputs(
    first: Collection[str], second: Collection[str]
) -> None:
    """Fail closed when filtering the inputs changes the old question set."""
    if set(first) != set(second):
        changed = sorted(set(first) ^ set(second))
        raise UpdatePlanningError(
            "Old template baseline cannot be rebuilt: it asks different "
            "questions once unused answers are removed ("
            + ", ".join(changed)
            + "). The target was not changed. Pass each listed answer with "
            "'--data KEY=VALUE', then run 'csarc update --check' again."
        )


def new_side_data(
    saved: Mapping[str, object],
    old: OldSideInputs,
    update_data: Mapping[str, object],
    hidden: Collection[str] = (),
) -> dict[str, object]:
    """Return the data the new side receives on top of the old answers.

    Answers dropped from the old side are still the repository's saved
    intent, so the new side receives them explicitly; reviewed update data
    (migrations, explicit ``--data`` and repository facts) wins. Copier
    never reuses the last answer of a ``when: false`` question, so each
    saved ``hidden`` setting is forwarded the same way (Issue #1298).
    """
    data = {key: saved[key] for key in old.dropped}
    data.update((key, saved[key]) for key in hidden if key in saved)
    data.update(update_data)
    return dict(sorted(data.items()))


@dataclass(frozen=True)
class UpdatePlanning:
    """One immutable update planning result shared by check and apply."""

    old_side: OldSideInputs
    new_data: Mapping[str, object]
    add: tuple[str, ...]
    overwrite: tuple[str, ...]
    merge: tuple[str, ...]
    delete: tuple[str, ...]
    conflicts: tuple[str, ...]
    render_parity: str
    parity_paths: tuple[str, ...] = field(default=())
    # Issue #1066: modified files kept instead of retired, and product
    # release state the update restored instead of reseeding.
    retained: tuple[str, ...] = field(default=())
    product_owned: tuple[str, ...] = field(default=())
    # Issue #1083: CSARC forwarding wrappers kept at moved scripts' old
    # paths while product files still call them.
    shims: tuple[str, ...] = field(default=())
    # Rendered files restored after Copier's update deleted them (#1083).
    restored: tuple[str, ...] = field(default=())
    # Issue #1298: the settings the candidate's Copier update wrote, so the
    # report reads the same values the apply keeps; None when the
    # candidate has no readable schema 2 settings file. The digest binds
    # the inputs that determine it (new_data and the old side).
    written_settings: Mapping[str, object] | None = field(
        default=None, compare=False
    )

    def changed_paths(self) -> frozenset[str]:
        """Return every path the plan expects the update to change."""
        return frozenset(
            (*self.add, *self.overwrite, *self.merge, *self.delete)
        )

    def digest(self) -> str:
        """Bind the inputs, normalized diff, and conflicts in one digest."""
        value: dict[str, object] = {
            "conflicts": list(self.conflicts),
            "files": {
                "add": list(self.add),
                "automatic_merge": list(self.merge),
                "delete": list(self.delete),
                "overwrite": list(self.overwrite),
            },
            "new_data": dict(self.new_data),
            "old_side": self.old_side.copier_answers(),
            "product_owned": list(self.product_owned),
            "render_parity": self.render_parity,
            "retained": list(self.retained),
        }
        if self.shims:
            # Only a plan with shims binds them, so earlier plans keep
            # their digest.
            value["shims"] = list(self.shims)
        if self.restored:
            value["restored"] = list(self.restored)
        return canonical_digest(value)

    def as_dict(self) -> dict[str, object]:
        """Return the machine-plan summary of this planning result."""
        return {
            "conflicts": list(self.conflicts),
            "digest": self.digest(),
            "old_side": self.old_side.as_dict(),
            "product_owned": list(self.product_owned),
            "render_parity": self.render_parity,
            "render_parity_paths": list(self.parity_paths),
            "retained": list(self.retained),
            "shims": list(self.shims),
            "restored": list(self.restored),
        }


def written_settings_view(
    answers: Mapping[str, object],
    written: Mapping[str, object] | None,
    keys: Collection[str],
) -> dict[str, object]:
    """Return ``answers`` with each listed setting as the candidate wrote it.

    The check report and ``answers_changed`` describe ``answers``; the
    apply keeps what Copier's update wrote. A listed setting the candidate
    changed takes the written value and one it removed is dropped, so a
    saved setting the update would lose is reported, never shown as
    unchanged (Issue #1298, #1153). Without a readable written file the
    answers are returned unchanged.
    """
    result = dict(answers)
    if written is None:
        return result
    for key in keys:
        if key in written:
            result[key] = written[key]
        else:
            result.pop(key, None)
    return result


def classify_changes(
    changes: Mapping[str, str],
    *,
    conflicts: Collection[str],
    excluded: Collection[str],
    customized: Collection[str],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Normalize ``git diff --name-status`` output into file actions.

    ``changes`` maps a path to its single-letter Git status. Paths in
    ``excluded`` (layout moves and retired files, reported separately) and
    in ``conflicts`` are skipped. A modified path the project had
    customized relative to the old render is an automatic merge; other
    modifications are template overwrites. Returns ``(add, overwrite,
    merge, delete)``.
    """
    add: list[str] = []
    overwrite: list[str] = []
    merge: list[str] = []
    delete: list[str] = []
    skipped = set(conflicts) | set(excluded)
    for path, status in sorted(changes.items()):
        if path in skipped:
            continue
        if status == "A":
            add.append(path)
        elif status == "D":
            delete.append(path)
        elif path in customized:
            merge.append(path)
        else:
            overwrite.append(path)
    return tuple(add), tuple(overwrite), tuple(merge), tuple(delete)


def realized_divergence(
    planning: UpdatePlanning,
    realized_changes: Collection[str],
    realized_conflicts: Collection[str],
) -> list[str]:
    """Describe how an apply run diverged from the reviewed planning.

    Template tasks only run at apply time, so the apply run may touch more
    paths than the plan; it must never leave a planned change out or find a
    conflict the plan did not list. The final candidate must still equal
    the approved transitions exactly before anything is written (#1066,
    ``file_transition.transition_divergence``).
    """
    problems: list[str] = []
    unexpected = sorted(set(realized_conflicts) - set(planning.conflicts))
    if unexpected:
        problems.append("unplanned conflicts: " + ", ".join(unexpected))
    missing = sorted(planning.changed_paths() - set(realized_changes))
    if missing:
        problems.append("planned changes not applied: " + ", ".join(missing))
    return problems
