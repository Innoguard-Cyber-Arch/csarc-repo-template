"""Legacy governance setting migration and its SPEC-008 report classes.

The approved mapping (#1058 decision 1, Issue #1064) keeps every saved or
explicitly passed governance value. A missing ``admin_bypass`` becomes
``always`` and is reported as ``widened`` with the added authorization and
the way to restore the earlier scope. Every other missing governance key is
mapped only to an equivalent (``exact``) or narrower (``narrowed``) value;
an explicit choice that differs from the mapping is a ``decision``. Legacy
keys that the current schema no longer asks are ``retired`` and their
successors are ``exact``.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from csarc_cli import settings_schema

ADMIN_BYPASS_SCOPES = ("off", "beta-only", "always")
MIGRATED_ADMIN_BYPASS = "always"
POLICY_TOGGLES = (
    "policy_repository_settings",
    "policy_actions_permissions",
    "policy_labels",
    "policy_branch_ruleset",
)
LEGACY_LEVEL_REVIEWS = {
    "alpha": "self",
    "beta": "peer",
    "early": "peer",
    "formal": "peer",
}
# Every key the current schema no longer asks, mapped to the current key
# that carries its intent, if any. SPEC-009's migration registry (Issue
# #1071) is the single list; derived release observations are retired too.
RETIRED_SETTINGS: Mapping[str, str | None] = settings_schema.RETIRED_SETTINGS
GOVERNANCE_KEYS = frozenset(
    {
        "admin_bypass",
        "copilot_review",
        "governance_mode",
        "lifecycle",
        "project_maturity",
        "release_trigger",
        "verification_mode",
    }
)
# A governance key may only keep its value, move to an equivalent or
# narrower value, or ask for a human decision; a key the new schema drops
# is ``retired``. ``widened`` is reserved for the approved
# missing-``admin_bypass`` migration.
GOVERNANCE_CLASSES = frozenset(
    {"unchanged", "exact", "narrowed", "decision", "retired"}
)


class GovernanceMigrationError(ValueError):
    """A legacy governance value has no equivalent and needs a decision."""


def legacy_admin_bypass_scope(answers: Mapping[str, object]) -> str:
    """Return the admin self-review scope a legacy configuration granted."""
    review = answers.get("review")
    if review == "solo":
        return "always"
    if review == "peer":
        return "off"
    reviews = {
        level: answers.get(f"release_level_{level}_review", fallback)
        for level, fallback in LEGACY_LEVEL_REVIEWS.items()
    }
    if any(reviews[level] == "self" for level in ("early", "formal")):
        return "always"
    if any(reviews[level] == "self" for level in ("alpha", "beta")):
        return "beta-only"
    return "off"


def legacy_governance_mode(answers: Mapping[str, object]) -> str:
    """Map the four legacy policy toggles onto one governance mode."""
    values = [answers.get(key, True) for key in POLICY_TOGGLES]
    if all(value is True for value in values):
        return "managed"
    if all(value is False for value in values):
        return "observe"
    raise GovernanceMigrationError(
        "Legacy policy_* settings are mixed. Pass one explicit "
        "governance_mode=managed or governance_mode=observe choice."
    )


def legacy_copilot_review(answers: Mapping[str, object]) -> tuple[str, str]:
    """Return the migrated Copilot review value and its report class.

    A level cap other than ``unlimited`` has no current equivalent; allowing
    Copilot at every level would widen it, so the migration disables Copilot
    review and reports the narrower value.
    """
    if answers.get("pr_review_mode") != "copilot":
        return "off", "exact"
    if answers.get("copilot_review_max_level", "unlimited") != "unlimited":
        return "off", "narrowed"
    return "allowed", "exact"


def legacy_governance_values(
    answers: Mapping[str, object],
) -> dict[str, object]:
    """Return the approved current value for every governance key."""
    return {
        "admin_bypass": MIGRATED_ADMIN_BYPASS,
        "copilot_review": legacy_copilot_review(answers)[0],
        "governance_mode": legacy_governance_mode(answers),
        "lifecycle": ["issues", "milestones"],
        "project_maturity": (
            "formal"
            if answers.get("default_release_level") == "formal"
            else "early"
        ),
        "release_trigger": "main",
        # Older repositories were verified by hosted checks; migrating them
        # to local evidence would lower the existing protection.
        "verification_mode": "hosted",
    }


def admin_bypass_note(scope: str) -> str:
    """Explain the widened admin bypass and how to restore the old scope."""
    if scope == MIGRATED_ADMIN_BYPASS:
        prior = "already allowed admin self-review for beta and stable work"
    elif scope == "beta-only":
        prior = "allowed admin self-review only for beta work"
    else:
        prior = "required an independent maintainer approval"
    return (
        "No saved admin_bypass; the legacy settings "
        f"{prior} (equivalent to `{scope}`). Migrated to `always`: a live "
        "admin may replace peer approval with an exact-head authorization "
        "for beta and stable work. Required checks, verification, and the "
        "lifecycle still apply. To keep the earlier scope, run "
        f"`csarc update --data admin_bypass={scope}`."
    )


def _explicit_class(
    key: str, after: object, before: Mapping[str, object]
) -> str:
    """Classify an explicit choice for a key the saved settings lacked."""
    if key == "admin_bypass":
        scope = legacy_admin_bypass_scope(before)
        if after == scope:
            return "exact"
        if (
            isinstance(after, str)
            and after in ADMIN_BYPASS_SCOPES
            and ADMIN_BYPASS_SCOPES.index(after)
            < ADMIN_BYPASS_SCOPES.index(scope)
        ):
            return "narrowed"
        return "decision"
    try:
        expected = legacy_governance_values(before).get(key)
    except GovernanceMigrationError:
        return "decision"
    return "exact" if after == expected else "decision"


def setting_classes(  # noqa: C901
    before: Mapping[str, object],
    after: Mapping[str, object],
    explicit: Collection[str] = (),
) -> dict[str, tuple[str, str | None]]:
    """Return the report class and note for each migrated or retired key.

    Keys absent from the result keep the generic report classification.
    """
    classes: dict[str, tuple[str, str | None]] = {}
    successors: set[str] = set()
    for key, successor in RETIRED_SETTINGS.items():
        if key not in before or key in settings_schema.RELEASE_OBSERVATIONS:
            continue
        note = (
            f"Retired; `{successor}` carries this intent."
            if successor is not None
            else "Retired; the current schema has no equivalent setting."
        )
        if key in settings_schema.RETIRED_SITE_TOKENS:
            note += (
                f" Replace `[[{key}]]` in project-owned site content with "
                f"`[[{successor}]]`."
                if successor is not None
                else f" Remove `[[{key}]]` from project-owned site content."
            )
        classes[key] = ("retired", note)
        if successor is not None:
            successors.add(successor)
    for key in sorted(GOVERNANCE_KEYS):
        if key in before or key not in after:
            continue
        value = after[key]
        if key in explicit:
            classes[key] = (_explicit_class(key, value, before), None)
        elif key == "admin_bypass":
            if value == MIGRATED_ADMIN_BYPASS:
                scope = legacy_admin_bypass_scope(before)
                classes[key] = ("widened", admin_bypass_note(scope))
            else:
                classes[key] = ("decision", None)
        elif key == "copilot_review":
            expected, setting_class = legacy_copilot_review(before)
            if value != expected:
                classes[key] = ("decision", None)
            elif setting_class == "narrowed":
                classes[key] = (
                    "narrowed",
                    "copilot_review_max_level="
                    f"`{before.get('copilot_review_max_level')}` has no "
                    "current equivalent, so Copilot review is off. Run "
                    "`csarc update --data copilot_review=allowed` to accept "
                    "Copilot review at every level.",
                )
            else:
                classes[key] = ("exact", None)
        else:
            classes[key] = (_explicit_class(key, value, before), None)
    for key in sorted(successors - GOVERNANCE_KEYS):
        if key not in before and key in after and key not in explicit:
            classes[key] = ("exact", None)
    return classes


def governance_row_violations(
    rows: Collection[Mapping[str, object]],
) -> list[str]:
    """Return governance rows whose class the approved mapping forbids."""
    violations: list[str] = []
    for row in rows:
        key = row.get("key")
        if key not in GOVERNANCE_KEYS:
            continue
        setting_class = row.get("class")
        if setting_class in GOVERNANCE_CLASSES:
            continue
        if (
            key == "admin_bypass"
            and setting_class == "widened"
            and row.get("before") is None
            and row.get("after") == MIGRATED_ADMIN_BYPASS
            and row.get("source") == "derived"
        ):
            continue
        violations.append(f"{key}={setting_class}")
    return violations
