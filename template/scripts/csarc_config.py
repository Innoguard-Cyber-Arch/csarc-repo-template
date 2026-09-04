"""Read the flat, template-managed CSARC repository configuration."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

CONFIG_FILE = Path(".csarc/config.yml")
LANGUAGES = {"python", "rust", "typescript"}
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
    validate_config(result, path)
    return result


def validate_release_config(config: dict[str, object]) -> None:
    """Validate the flat release ownership contract."""
    ownership = config.get("release_ownership")
    if ownership is None:
        return
    if not isinstance(ownership, str) or ownership not in RELEASE_OWNERSHIPS:
        raise ValueError(f"Invalid release_ownership: {ownership!r}")
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
        "branch_strategy": {"delivery", "main"},
        "container_mode": {"none", "verify", "ghcr"},
        "coverage_mode": {"diff", "global"},
        "project_mode": {"existing", "new"},
        "project_visibility": {"internal", "private", "public"},
        "python_support_mode": {"latest", "minimum"},
        "release_ownership": RELEASE_OWNERSHIPS,
    }
    for key, allowed in choices.items():
        value = config.get(key)
        if value is not None and value not in allowed:
            expected = ", ".join(sorted(allowed))
            raise ValueError(
                f"Invalid {key} in {path}: {value!r}; expected {expected}"
            )

    languages = config.get("languages")
    if languages is not None:
        if not isinstance(languages, list) or any(
            not isinstance(language, str) or language not in LANGUAGES
            for language in languages
        ):
            expected = ", ".join(sorted(LANGUAGES))
            raise ValueError(
                f"Invalid languages in {path}; expected a list containing "
                f"only {expected}"
            )
        if len(languages) != len(set(languages)):
            raise ValueError(f"Duplicate languages in {path}")

    validate_release_config(config)

    for toggle in POLICY_TOGGLES:
        value = config.get(toggle)
        if value is not None and not isinstance(value, bool):
            raise ValueError(
                f"Invalid {toggle} in {path}: {value!r}; expected true or false"
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
        sys.stderr.write("Usage: scripts/csarc_config.py <key>\n")
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
