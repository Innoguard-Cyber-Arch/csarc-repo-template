"""Schema 2 settings fixtures shared by the root regression suite.

SPEC-009 (Issue #1071) made `.csarc/config.yml` a closed, current-only
schema: every persistent intent must be stated. Tests that care about one
or two settings build a complete, valid file from these defaults and their
own overrides instead of writing a partial legacy file.
"""

from __future__ import annotations

import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PARSE = runpy.run_path(str(ROOT / "scripts/csarc_config.py"))[
    "parse_settings_text"
]

DEFAULTS: dict[str, object] = {
    "schema_version": 2,
    "admin_bypass": "always",
    "code_owner": "",
    "container": False,
    "copilot_review": "allowed",
    "coverage_mode": "global",
    "coverage_threshold": 80,
    "documentation_languages": "zh-tw+en",
    "documentation_mode": "template-and-content",
    "enable_codeql": False,
    "governance_mode": "managed",
    "languages": ["python"],
    "lifecycle": ["issues", "milestones"],
    "project_maturity": "early",
    "github_project_url": "",
    "project_verification_hook": "",
    "python_floor": "latest",
    "release_ownership": "csarc-owned",
    "release_trigger": "main",
    "scheduled_checks": ["governance-drift"],
    "security_reporting_channel": "security@example.com",
    "verification_mode": "hosted",
}
_PLAIN_UNSAFE = {"", "off", "on", "yes", "no", "true", "false", "null", "~"}


def _scalar(value: object) -> str:
    """Render one scalar the way both settings readers parse it."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if (
        text.lower() in _PLAIN_UNSAFE
        or text != text.strip()
        or text[0] in "@*&!%{[\"'#|>-?:,"
        or ": " in text
        or " #" in text
    ):
        return json.dumps(text)
    return text


def settings_text(partial: str = "", **overrides: object) -> str:
    """Return a complete schema 2 file with partial text and overrides.

    ``partial`` uses the settings file syntax; an override of ``None``
    removes the key so a test can prove a missing value fails closed.
    """
    values = dict(DEFAULTS)
    values.update(_PARSE(partial, Path("partial.yml")))
    values.update(overrides)
    lines: list[str] = []
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, list):
            lines.append(f"{key}:" if value else f"{key}: []")
            lines.extend(f"- {_scalar(item)}" for item in value)
        else:
            lines.append(f"{key}: {_scalar(value)}")
    return "\n".join(lines) + "\n"


def write_settings(path: Path, partial: str = "", **overrides: object) -> Path:
    """Write one complete schema 2 settings file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(settings_text(partial, **overrides), encoding="utf-8")
    return path


# Issue #1078: init and adopt ask only for intent no source decides, and a
# non-interactive run without one of those inputs stops before rendering.
# Tests about other contracts pass the same explicit seeds a script would;
# tests/test_setup_questions.py proves the missing-input failure itself.
SETUP_SEEDS: dict[str, dict[str, str]] = {
    "init": {
        "project_description": "Example product used by the CLI tests.",
        "copyright_holder": "Example Maintainers",
        "languages": "python",
    },
    "adopt": {
        "project_description": "Example product used by the CLI tests.",
        "copyright_holder": "Example Maintainers",
        "governance_mode": "managed",
    },
}


def seeded_setup(arguments: list[str] | None) -> list[str] | None:
    """Add the explicit init/adopt setup inputs a script must pass."""
    if (
        not arguments
        or arguments[0] not in SETUP_SEEDS
        or {"--apply-plan", "--finalize"} & set(arguments)
    ):
        return arguments
    given = {
        arguments[index + 1].partition("=")[0]
        for index, item in enumerate(arguments[:-1])
        if item == "--data"
    }
    seeded = list(arguments)
    for key, value in SETUP_SEEDS[arguments[0]].items():
        if key in given or (key == "languages" and "language" in given):
            continue
        seeded.extend(["--data", f"{key}={value}"])
    return seeded
