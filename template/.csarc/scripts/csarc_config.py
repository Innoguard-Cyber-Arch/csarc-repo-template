"""Read and normalize the template-managed CSARC configuration."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

CONFIG_FILE = Path(".csarc/config.yml")
LANGUAGES = {"python", "rust", "typescript"}
FEATURES = {"docker", "repo-site"}
GOVERNANCE_MODES = {"managed", "observe"}
LIFECYCLE_CAPABILITIES = {"issues", "milestones"}
HUMAN_REVIEW_MODES = {"peer", "solo"}
COPILOT_REVIEW_MODES = {"allowed", "off"}
ACTIONS_FALLBACK_MODES = {"admin", "off"}
ADMIN_BYPASS_MODES = {"off", "beta-only", "always"}
PROJECT_MATURITIES = {"early", "formal"}
VERIFICATION_MODES = {"hosted", "local"}
RELEASE_TRIGGERS = {"main", "manual"}
RELEASE_OWNERSHIPS = {"csarc-owned", "product-owned", "verification-only"}
RELEASE_SETTINGS = {
    "csarc-owned": ("csarc-admin", "required"),
    "product-owned": ("product-admin", "product-defined"),
    "verification-only": ("none", "not-required"),
}
# One flat boolean per template-owned policy area a project can opt out of
# (Issue #532). A key absent from .csarc/config.yml means "on" -- the
# pre-toggle behavior -- so upgrading an older answers file never silently
# drops coverage. Immutable Releases has no toggle here: it reuses the
# existing release_immutable_releases contract instead of a duplicate key.
POLICY_TOGGLES = (
    "policy_repository_settings",
    "policy_actions_permissions",
    "policy_labels",
    "policy_branch_ruleset",
)

# Issue #752: how a pull request earns merge approval. "copilot" accepts a
# clean GitHub Copilot review of the exact head (or a maintainer approval);
# "human" keeps the maintainer-approval-only Ruleset. A key absent from an
# older answers file means "human", the behavior before this option existed.
PR_REVIEW_MODES = {"copilot", "human"}
COPILOT_REVIEW_MAX_LEVELS = {
    "unlimited",
    "alpha",
    "beta",
    "stable",
    "early",
    "release",
}
RELEASE_LEVELS = {"beta", "stable"}
RELEASE_LEVEL_REVIEWS = {"self", "peer"}
RELEASE_LEVEL_VERIFICATION = {"baseline", "fast", "docs", "full"}
LEGACY_REVIEW_DEFAULTS = {
    "alpha": "self",
    "beta": "peer",
    "early": "peer",
    "formal": "peer",
}


def _legacy_admin_bypass(config: dict[str, object]) -> str:
    """Preserve the effective self-review scope of older configurations."""
    review = config.get("review")
    if review == "solo":
        return "always"
    if review == "peer":
        return "off"
    beta_reviews = {
        config.get("release_level_alpha_review", "self"),
        config.get("release_level_beta_review", "peer"),
    }
    stable_reviews = {
        config.get("release_level_early_review", "peer"),
        config.get("release_level_formal_review", "peer"),
    }
    if stable_reviews == {"self"}:
        return "always"
    if "self" in beta_reviews:
        return "beta-only"
    return "off"


def _list_setting(
    config: dict[str, object], key: str, allowed: set[str], path: Path
) -> None:
    value = config.get(key)
    if value is None:
        return
    if not isinstance(value, list) or any(
        not isinstance(item, str) or item not in allowed for item in value
    ):
        expected = ", ".join(sorted(allowed))
        raise ValueError(
            f"Invalid {key} in {path}; expected a list containing only "
            f"{expected}"
        )
    if len(value) != len(set(value)):
        raise ValueError(f"Duplicate {key} in {path}")


def _legacy_default(  # noqa: C901
    config: dict[str, object], key: str
) -> object:
    """Return one new setting from a pre-#900 answers file."""
    if key == "governance_mode":
        values = [config.get(toggle, True) for toggle in POLICY_TOGGLES]
        for toggle, value in zip(POLICY_TOGGLES, values, strict=True):
            if not isinstance(value, bool):
                raise ValueError(
                    f"Invalid {toggle} in {CONFIG_FILE}: expected true or false"
                )
        if all(value is True for value in values):
            return "managed"
        if all(value is False for value in values):
            return "observe"
        raise ValueError(
            "Legacy policy_* settings are mixed; choose governance_mode "
            "explicitly before updating"
        )
    if key == "lifecycle":
        return ["issues", "milestones"]
    if key == "actions_fallback":
        return "off"
    if key == "admin_bypass":
        return _legacy_admin_bypass(config)
    if key == "project_maturity":
        return (
            "formal"
            if config.get("default_release_level") == "formal"
            else "early"
        )
    if key == "verification_mode":
        return "hosted"
    if key == "review":
        reviews = [
            config.get(
                f"release_level_{level}_review",
                LEGACY_REVIEW_DEFAULTS[level],
            )
            for level in LEGACY_REVIEW_DEFAULTS
        ]
        return "peer" if "peer" in reviews else "solo"
    if key == "copilot_review":
        return "allowed" if config.get("pr_review_mode") == "copilot" else "off"
    if key == "release_trigger":
        return "main"
    if key == "features":
        features = ["repo-site"]
        if config.get("enable_docker") is True:
            features.append("docker")
        return features
    raise KeyError(key)


def normalize_config(config: dict[str, object]) -> dict[str, object]:
    """Add the small public schema to legacy Copier answers in memory."""
    result = dict(config)
    for key in (
        "governance_mode",
        "lifecycle",
        "actions_fallback",
        "admin_bypass",
        "project_maturity",
        "verification_mode",
        "review",
        "copilot_review",
        "release_trigger",
        "features",
    ):
        if key not in result:
            result[key] = _legacy_default(result, key)
    return result


def _scalar(value: str) -> object:
    """Parse the scalar forms emitted by Copier's YAML serializer."""
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "~"}:
        return None
    if value.startswith(("'", '"', "[")):
        try:
            return ast.literal_eval(value)
        except SyntaxError:
            pass
        except ValueError:
            pass
    try:
        return int(value)
    except ValueError:
        return value


def load_config(path: Path = CONFIG_FILE) -> dict[str, object]:
    """Load Copier's flat scalar/list answers without a runtime dependency."""
    result: dict[str, object] = {}
    active_key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith("- "):
            if active_key is None:
                raise ValueError(f"Unexpected list item in {path}: {raw_line}")
            active_list = result[active_key]
            if not isinstance(active_list, list):
                raise ValueError(f"Unexpected list item in {path}: {raw_line}")
            active_list.append(_scalar(raw_line[2:].strip()))
            continue
        if raw_line[0].isspace():
            if active_key is None or not isinstance(result[active_key], str):
                raise ValueError(
                    f"Unexpected indentation in {path}: {raw_line}"
                )
            result[active_key] = f"{result[active_key]} {raw_line.strip()}"
            continue
        key, separator, raw_value = raw_line.partition(":")
        if not separator or not key:
            raise ValueError(f"Invalid setting in {path}: {raw_line}")
        raw_value = raw_value.strip()
        result[key] = _scalar(raw_value) if raw_value else []
        active_key = key
    result = normalize_config(result)
    validate_config(result, path)
    return result


def validate_release_config(config: dict[str, object]) -> None:
    """Validate ownership and any legacy persisted release observations."""
    ownership = config.get("release_ownership")
    if ownership is None:
        return
    if not isinstance(ownership, str) or ownership not in RELEASE_OWNERSHIPS:
        raise ValueError(f"Invalid release_ownership: {ownership!r}")
    legacy_keys = {
        "release_workflow",
        "release_required_inputs",
        "release_ownership_reason",
        "release_settings_owner",
        "release_immutable_releases",
    }
    if not legacy_keys.intersection(config):
        return
    workflow = config.get("release_workflow")
    inputs = config.get("release_required_inputs")
    reason = config.get("release_ownership_reason")
    settings = (
        config.get("release_settings_owner"),
        config.get("release_immutable_releases"),
    )
    if ownership == "verification-only" and workflow:
        raise ValueError(
            "verification-only release ownership cannot select a workflow"
        )
    if ownership != "verification-only" and not workflow:
        raise ValueError(f"{ownership} release ownership needs a workflow")
    if not isinstance(reason, str) or not reason:
        raise ValueError("release ownership needs a non-empty reason")
    if not isinstance(inputs, list) or any(
        not isinstance(item, str) or not item for item in inputs
    ):
        raise ValueError("release_required_inputs must contain strings")
    if len(inputs) != len(set(inputs)):
        raise ValueError("Duplicate release_required_inputs")
    if settings != RELEASE_SETTINGS[ownership]:
        raise ValueError("Release repository settings do not match ownership")


def validate_config(
    config: dict[str, object], path: Path = CONFIG_FILE
) -> None:
    """Validate the managed settings consumed by repository automation."""
    choices = {
        "actions_fallback": ACTIONS_FALLBACK_MODES,
        "admin_bypass": ADMIN_BYPASS_MODES,
        "project_maturity": PROJECT_MATURITIES,
        "verification_mode": VERIFICATION_MODES,
        "branch_strategy": {"delivery", "main"},
        "copilot_review": COPILOT_REVIEW_MODES,
        "copilot_review_max_level": COPILOT_REVIEW_MAX_LEVELS,
        "container_mode": {"none", "verify", "ghcr"},
        "coverage_mode": {"diff", "global"},
        "default_release_level": {
            "alpha",
            "beta",
            "early",
            "formal",
            "stable",
        },
        "governance_mode": GOVERNANCE_MODES,
        "project_mode": {"existing", "new"},
        "project_visibility": {"internal", "private", "public"},
        "pr_review_mode": PR_REVIEW_MODES,
        "python_support_mode": {"latest", "minimum"},
        "release_trigger": RELEASE_TRIGGERS,
        "release_ownership": RELEASE_OWNERSHIPS,
        "review": HUMAN_REVIEW_MODES,
        **{
            f"release_level_{level}_review": RELEASE_LEVEL_REVIEWS
            for level in RELEASE_LEVELS
        },
        **{
            f"release_level_{level}_verification": RELEASE_LEVEL_VERIFICATION
            for level in RELEASE_LEVELS
        },
    }
    for key, allowed in choices.items():
        value = config.get(key)
        if value is not None and value not in allowed:
            expected = ", ".join(sorted(allowed))
            raise ValueError(
                f"Invalid {key} in {path}: {value!r}; expected {expected}"
            )

    _list_setting(config, "languages", LANGUAGES, path)
    _list_setting(config, "features", FEATURES, path)
    _list_setting(config, "lifecycle", LIFECYCLE_CAPABILITIES, path)

    validate_release_config(config)

    for toggle in POLICY_TOGGLES:
        value = config.get(toggle)
        if value is not None and not isinstance(value, bool):
            raise ValueError(
                f"Invalid {toggle} in {path}: {value!r}; expected true or false"
            )

    release_levels_enabled = config.get("release_levels_enabled")
    if release_levels_enabled is not None and not isinstance(
        release_levels_enabled, bool
    ):
        raise ValueError(
            f"Invalid release_levels_enabled in {path}: "
            f"{release_levels_enabled!r}; expected true or false"
        )

    threshold = config.get("coverage_threshold")
    if threshold is not None and (
        isinstance(threshold, bool)
        or not isinstance(threshold, int)
        or not 1 <= threshold <= 100
    ):
        raise ValueError(
            f"Invalid coverage_threshold in {path}: {threshold!r}; "
            "expected an integer from 1 to 100"
        )


def main(argv: list[str] | None = None) -> int:
    """Print one configuration value for shell callers."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        sys.stderr.write("Usage: csarc_config.py <key>\n")
        return 2
    try:
        value = load_config()[arguments[0]]
    except (OSError, KeyError, ValueError) as error:
        sys.stderr.write(f"{error}\n")
        return 1
    if isinstance(value, list):
        sys.stdout.write(",".join(str(item) for item in value) + "\n")
    elif isinstance(value, bool):
        sys.stdout.write(f"{str(value).lower()}\n")
    elif value is not None:
        sys.stdout.write(f"{value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
