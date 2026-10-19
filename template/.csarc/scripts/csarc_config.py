"""Read the current CSARC settings schema and native project facts.

SPEC-009 (Issue #1071) is the closed classification this reader enforces.
`.csarc/config.yml` stores only persistent intent: settings that change
later behavior and cannot be safely reconstructed. One-time seeds, live
repository facts, derived context, and machine metadata never live here;
seeds are read from native sources (LICENSE and language manifests), live
facts are observed by the pinned CLI, and the immutable project mode and
resolved render context live in `.csarc/provenance.json`.

This is a current-only parser. It never normalizes, defaults, or aliases a
legacy setting: an older or unknown schema, a retired or unknown key, a
missing intent, or an invalid value fails closed with one stable error that
points to `csarc update`. Legacy settings are read only by the pinned
CLI's migration registry, outside the repository.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path
from types import ModuleType

CONFIG_FILE = Path(".csarc/config.yml")
SCHEMA_KEY = "schema_version"
SCHEMA_VERSION = 2
# Copier needs these two keys to locate the template source and revision;
# they are the only machine metadata the settings file may carry.
COPIER_METADATA_KEYS = frozenset({"_commit", "_src_path"})
# Stable prefix for fail-closed settings errors shared by every reader.
SETTINGS_ERROR_PREFIX = "CSARC settings error"
MIGRATION_COMMAND = "csarc update"

KIND_CHOICE = "choice"
KIND_MULTI = "multi"
KIND_BOOL = "bool"
KIND_INT = "int"
KIND_TEXT = "text"

# Persistent intent (SPEC-009). Every key is required in schema 2.
INTENT_SETTINGS: dict[str, tuple[str, tuple[str, ...]]] = {
    "languages": (KIND_MULTI, ("go", "python", "rust", "typescript")),
    "python_floor": (KIND_CHOICE, ("latest", "3.12", "3.13", "3.14")),
    "documentation_mode": (
        KIND_CHOICE,
        ("template-and-content", "content-only", "off"),
    ),
    "documentation_languages": (
        KIND_CHOICE,
        ("zh-tw", "en", "zh-tw+en", "en+zh-tw"),
    ),
    "verification_mode": (KIND_CHOICE, ("local", "hosted")),
    "admin_bypass": (KIND_CHOICE, ("off", "beta-only", "always")),
    "copilot_review": (KIND_CHOICE, ("allowed", "off")),
    "governance_mode": (KIND_CHOICE, ("managed", "observe")),
    "release_ownership": (
        KIND_CHOICE,
        ("csarc-owned", "product-owned", "verification-only"),
    ),
    "release_trigger": (KIND_CHOICE, ("main", "manual")),
    "project_maturity": (KIND_CHOICE, ("early", "formal")),
    "code_owner": (KIND_TEXT, ()),
    "enable_codeql": (KIND_BOOL, ()),
    "scheduled_checks": (KIND_MULTI, ("governance-drift", "template-update")),
    "lifecycle": (KIND_MULTI, ("issues", "milestones")),
    "coverage_mode": (KIND_CHOICE, ("global", "diff")),
    "coverage_threshold": (KIND_INT, ()),
    "security_reporting_channel": (KIND_TEXT, ()),
    "container": (KIND_BOOL, ()),
    "project_verification_hook": (KIND_TEXT, ()),
    "github_project_url": (KIND_TEXT, ()),
}
OPTIONAL_DEFAULTS: dict[str, object] = {"github_project_url": ""}
# Derived context that is saved only as a one-time user decision when no
# native manifest resolves it uniquely (SPEC-009); otherwise it is absent.
DECISION_SETTINGS: dict[str, tuple[str, tuple[str, ...]]] = {
    "package_name": (KIND_TEXT, ()),
    "project_run_command": (KIND_TEXT, ()),
}
RELEASE_OWNERSHIPS = frozenset(INTENT_SETTINGS["release_ownership"][1])
ALLOWED_KEYS = frozenset(
    {SCHEMA_KEY, *COPIER_METADATA_KEYS, *INTENT_SETTINGS, *DECISION_SETTINGS}
)

CODE_OWNER = re.compile(
    r"^@(?:(?![A-Za-z0-9-]*--)[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
    r"|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)$"
)
PACKAGE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
HOOK_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")
PLACEHOLDERS = frozenset({"todo", "tbd", "placeholder"})


class SettingsError(ValueError):
    """A saved setting is missing, unknown, retired, or contradictory."""


def settings_error(path: Path, detail: str) -> SettingsError:
    """Return one stable fail-closed error that names the recovery path."""
    return SettingsError(
        f"{SETTINGS_ERROR_PREFIX}: {detail} in {path}. Settings change only "
        f"through `{MIGRATION_COMMAND} --data KEY=VALUE`; restore a hand "
        f"edit with `git checkout -- {CONFIG_FILE}` first."
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
        except (SyntaxError, ValueError):
            pass
    try:
        return int(value)
    except ValueError:
        return value


def parse_settings_text(text: str, path: Path) -> dict[str, object]:
    """Parse the flat scalar/list YAML subset without validating it.

    This is the shared tokenizer, not a settings reader: callers that need
    a trusted value must use :func:`load_config`.
    """
    result: dict[str, object] = {}
    active_key: str | None = None
    for raw_line in text.splitlines():
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
    return result


def declared_schema(values: dict[str, object], path: Path) -> int:
    """Return the declared schema or fail closed for a legacy file."""
    if SCHEMA_KEY not in values:
        raise SettingsError(
            f"{SETTINGS_ERROR_PREFIX}: {path} has no {SCHEMA_KEY}; it uses a "
            f"legacy settings schema. Run `{MIGRATION_COMMAND}` with the "
            "pinned CLI to migrate it; repository scripts never read legacy "
            "settings."
        )
    schema = values[SCHEMA_KEY]
    if type(schema) is not int or schema != SCHEMA_VERSION:
        raise SettingsError(
            f"{SETTINGS_ERROR_PREFIX}: {path} declares {SCHEMA_KEY} "
            f"{schema!r}; this reader accepts only schema {SCHEMA_VERSION}. "
            "Use the CLI release that wrote it instead of rewriting it."
        )
    return schema


def _validate_text(key: str, value: str, path: Path) -> None:
    """Validate the free-text settings that still have a fixed shape."""
    stripped = value.strip()
    if key == "code_owner":
        if value and CODE_OWNER.fullmatch(value) is None:
            raise settings_error(
                path, "code_owner must be '', @user, or @organization/team"
            )
    elif key == "security_reporting_channel":
        if not stripped or stripped.lower() in PLACEHOLDERS or "<" in value:
            raise settings_error(
                path, "security_reporting_channel needs an approved channel"
            )
    elif key == "project_verification_hook":
        if value and (
            stripped != value
            or value.startswith("/")
            or ".." in value.split("/")
            or HOOK_PATH.fullmatch(value) is None
        ):
            raise settings_error(
                path,
                "project_verification_hook must be a safe repository-"
                "relative path",
            )
    elif key == "package_name":
        if PACKAGE_NAME.fullmatch(value) is None:
            raise settings_error(
                path, "package_name must be a lowercase Python identifier"
            )
    elif key == "project_run_command" and (
        not stripped or stripped.lower() in PLACEHOLDERS or "<" in value
    ):
        raise settings_error(
            path, "project_run_command needs a working command"
        )


def _validate_value(  # noqa: C901
    key: str, spec: tuple[str, tuple[str, ...]], value: object, path: Path
) -> None:
    """Validate one setting against its SPEC-009 kind and values."""
    kind, allowed = spec
    if kind == KIND_CHOICE:
        if not isinstance(value, str) or value not in allowed:
            raise settings_error(
                path,
                f"{key} is {value!r}; expected one of " + ", ".join(allowed),
            )
    elif kind == KIND_MULTI:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or item not in allowed for item in value
        ):
            raise settings_error(
                path,
                f"{key} must be a list containing only " + ", ".join(allowed),
            )
        if len(value) != len(set(value)):
            raise settings_error(path, f"{key} repeats a value")
    elif kind == KIND_BOOL:
        if not isinstance(value, bool):
            raise settings_error(path, f"{key} must be true or false")
    elif kind == KIND_INT:
        if type(value) is not int or not 1 <= value <= 100:
            raise settings_error(
                path, f"{key} must be an integer from 1 to 100"
            )
    elif not isinstance(value, str):
        raise settings_error(path, f"{key} must be a string")
    else:
        _validate_text(key, value, path)


def validate_config(
    config: dict[str, object], path: Path = CONFIG_FILE
) -> None:
    """Fail closed unless `config` is exactly a valid schema 2 file."""
    declared_schema(config, path)
    unknown = sorted(key for key in config if key not in ALLOWED_KEYS)
    if unknown:
        raise settings_error(
            path,
            "unknown or retired settings "
            + ", ".join(unknown)
            + f" are not part of schema {SCHEMA_VERSION}",
        )
    missing = sorted(set(INTENT_SETTINGS) - {*config, *OPTIONAL_DEFAULTS})
    if missing:
        raise settings_error(
            path, "missing persistent settings " + ", ".join(missing)
        )
    for key, spec in {**INTENT_SETTINGS, **DECISION_SETTINGS}.items():
        if key in config:
            _validate_value(key, spec, config[key], path)


def load_config(path: Path = CONFIG_FILE) -> dict[str, object]:
    """Load and validate the current settings schema without defaults."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SettingsError(
            f"{SETTINGS_ERROR_PREFIX}: cannot read {path} ({error}); run "
            f"`{MIGRATION_COMMAND}` to restore the managed settings."
        ) from error
    config = parse_settings_text(text, path)
    validate_config(config, path)
    return config


def resolve_release_ownership(
    config: dict[str, object], path: Path = CONFIG_FILE
) -> str:
    """Return the single saved release owner or fail closed (Issue #1068).

    The saved value is the only authority: a missing owner is never
    re-derived from project_mode, live workflows, or Copier defaults, so
    every reader (CLI, shell adapters, workflows) sees the same answer.
    """
    ownership = config.get("release_ownership")
    if ownership is None:
        raise SettingsError(
            f"{SETTINGS_ERROR_PREFIX}: release_ownership is missing from "
            f"{path}; run `csarc update --data release_ownership=<"
            + "|".join(sorted(RELEASE_OWNERSHIPS))
            + ">` to record the single release writer before any release "
            "or settings write."
        )
    if not isinstance(ownership, str) or ownership not in RELEASE_OWNERSHIPS:
        raise SettingsError(
            f"{SETTINGS_ERROR_PREFIX}: release_ownership in {path} is "
            f"{ownership!r}; expected "
            + ", ".join(sorted(RELEASE_OWNERSHIPS))
            + "."
        )
    # project_mode is provenance, not a setting; the CLI passes it when it
    # checks a resolved render context.
    if ownership == "product-owned" and config.get("project_mode") == "new":
        raise SettingsError(
            f"{SETTINGS_ERROR_PREFIX}: release_ownership product-owned "
            f"contradicts project_mode new in {path}; a new project has no "
            "product release writer. Run `csarc update --data "
            "release_ownership=<csarc-owned|verification-only>`."
        )
    return ownership


def renders_release_workflow(
    config: dict[str, object], path: Path = CONFIG_FILE
) -> bool:
    """Return whether CSARC is the one Release writer for this project."""
    return resolve_release_ownership(config, path) == "csarc-owned"


def documentation_language_pair(config: dict[str, object]) -> tuple[str, str]:
    """Return the primary and optional secondary documentation language."""
    value = str(config["documentation_languages"])
    primary, _, secondary = value.partition("+")
    return primary, secondary


# ---------------------------------------------------------------------------
# Native project facts (SPEC-009 one-time seeds and derived context).
# ---------------------------------------------------------------------------

LICENSE_PROPRIETARY = "proprietary"
LICENSE_CUSTOM = "custom"
_PROPRIETARY_LINE = re.compile(
    r"^Copyright \(c\) (?P<holder>.+?)\. All rights reserved\.$"
)
_COPYRIGHT_LINE = re.compile(r"^\s*Copyright \(c\) (?P<holder>.+?)\s*$")


def license_facts(root: Path) -> tuple[str, str]:
    """Return the license and copyright holder declared by LICENSE.

    LICENSE is the native source for both one-time seeds. A text that is
    not one of the three CSARC starter licenses is ``custom``: it belongs to
    the product and its holder is not inferred.
    """
    path = root / "LICENSE"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return LICENSE_CUSTOM, ""
    lines = text.splitlines()
    first = next((line.strip() for line in lines if line.strip()), "")
    proprietary = _PROPRIETARY_LINE.fullmatch(first)
    if proprietary is not None:
        return LICENSE_PROPRIETARY, proprietary.group("holder")
    if first == "MIT License":
        identifier = "MIT"
    elif first == "Apache License" and "Version 2.0, January 2004" in text:
        identifier = "Apache-2.0"
    else:
        return LICENSE_CUSTOM, ""
    holders = [
        match.group("holder")
        for line in lines
        if (match := _COPYRIGHT_LINE.fullmatch(line)) is not None
        and "{" not in match.group("holder")
        and "[" not in match.group("holder")
    ]
    return identifier, holders[-1] if holders else ""


_DESCRIPTION_BLOCK = re.compile(
    r"<!-- csarc-project-description:start -->\n(?P<text>.*?)\n"
    r"<!-- csarc-project-description:end -->",
    re.DOTALL,
)


def _readme_identity(root: Path) -> tuple[str, str]:
    """Return the human name and description the README seed recorded."""
    try:
        text = (root / "README.md").read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return "", ""
    title = next(
        (
            line[2:].strip()
            for line in text.splitlines()
            if line.startswith("# ")
        ),
        "",
    )
    block = _DESCRIPTION_BLOCK.search(text)
    return title, block.group("text").strip() if block else ""


def _manifest_identity(root: Path) -> tuple[str, str]:
    """Return the product name and description from its native manifest."""
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get(
            "project", {}
        )
        if isinstance(project, dict) and isinstance(project.get("name"), str):
            return project["name"], str(project.get("description", ""))
    package = root / "package.json"
    if package.is_file():
        payload = json.loads(package.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("name"), str):
            return payload["name"], str(payload.get("description", ""))
    cargo = root / "Cargo.toml"
    if cargo.is_file():
        crate = tomllib.loads(cargo.read_text(encoding="utf-8")).get(
            "package", {}
        )
        if isinstance(crate, dict) and isinstance(crate.get("name"), str):
            return crate["name"], str(crate.get("description", ""))
    gomod = root / "go.mod"
    if gomod.is_file():
        for line in gomod.read_text(encoding="utf-8").splitlines():
            if line.startswith("module "):
                return line.split()[1].rsplit("/", 1)[-1], ""
    return root.resolve().name, ""


def _repository_facts() -> ModuleType:
    """Load the shared repository detector shipped beside this reader."""
    path = Path(__file__).with_name("repository_facts.py")
    spec = importlib.util.spec_from_file_location("repository_facts", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _origin_url(root: Path) -> str:
    """Return the GitHub URL the shared detector observes for origin.

    The URL is a live fact (SPEC-009, Issue #1072): it is read from local
    Git every time and is empty whenever the detector reports it unknown or
    ambiguous, never a guess or a value saved earlier.
    """
    detector = _repository_facts()
    origin = detector.observe_origin(root, detector.git_runner(root))
    return str(origin["value"]) if origin["state"] == detector.KNOWN else ""


def project_facts(root: Path) -> dict[str, object]:
    """Return the one-time seeds and offline facts read from native sources.

    Runtime never asks GitHub for these values (SPEC-009): the name and
    description come from the README seed or the product manifest, legal
    facts from LICENSE, and the repository URL from the local origin remote
    through the shared repository detector.
    """
    slug, manifest_description = _manifest_identity(root)
    title, readme_description = _readme_identity(root)
    project_license, holder = license_facts(root)
    return {
        "copyright_holder": holder,
        "project_description": readme_description or manifest_description,
        "project_license": project_license,
        "project_name": title or slug,
        "project_slug": slug,
        "repository_url": _origin_url(root),
    }


def main(argv: list[str] | None = None) -> int:
    """Print one configuration value for shell callers."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        sys.stderr.write("Usage: csarc_config.py <key>\n")
        return 2
    key = arguments[0]
    try:
        config = load_config()
        if key == "release_ownership":
            value: object = resolve_release_ownership(config)
        elif key not in INTENT_SETTINGS and key not in DECISION_SETTINGS:
            raise KeyError(
                f"{key} is not a schema {SCHEMA_VERSION} setting; see "
                "SPEC-009 for its native source"
            )
        else:
            value = config.get(key, OPTIONAL_DEFAULTS.get(key))
    except (OSError, KeyError, ValueError) as error:
        message = error.args[0] if isinstance(error, KeyError) else error
        sys.stderr.write(f"{message}\n")
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
