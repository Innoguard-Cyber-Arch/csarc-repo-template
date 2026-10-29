"""Deterministic policy checks for project-owned documentation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from csarc_cli import settings_schema, writing_guide_review

BLOCKING = frozenset({"drift", "inconclusive"})

# These are the saved settings that can change repository policy or an
# operator's delivery instructions. Exact key names remain valid keywords.
POLICY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "admin_bypass": (
        "admin_bypass",
        "admin bypass",
        "approve own change",
        "approve their own change",
        "核准自己的變更",
        "管理員略過",
    ),
    "code_owner": ("code_owner", "code owner", "codeowners", "程式碼擁有者"),
    "container": ("container", "容器"),
    "copilot_review": ("copilot_review", "copilot review", "copilot 審核"),
    "coverage_mode": ("coverage_mode", "coverage mode", "覆蓋率模式"),
    "coverage_threshold": (
        "coverage_threshold",
        "coverage threshold",
        "覆蓋率門檻",
    ),
    "documentation_languages": (
        "documentation_languages",
        "documentation languages",
        "文件語言",
    ),
    "documentation_mode": (
        "documentation_mode",
        "documentation mode",
        "文件模式",
    ),
    "enable_codeql": ("enable_codeql", "codeql", "codeql 啟用"),
    "github_project_url": (
        "github_project_url",
        "github project",
        "github 專案",
    ),
    "governance_mode": ("governance_mode", "governance mode", "治理模式"),
    "languages": ("languages", "language modules", "語言模組"),
    "lifecycle": ("lifecycle", "work item lifecycle", "工作項生命週期"),
    "project_maturity": ("project_maturity", "project maturity", "專案成熟度"),
    "project_verification_hook": (
        "project_verification_hook",
        "verification hook",
        "驗證 hook",
    ),
    "python_floor": ("python_floor", "python floor", "python 最低版本"),
    "release_ownership": (
        "release_ownership",
        "release ownership",
        "發布權責",
    ),
    "release_trigger": ("release_trigger", "release trigger", "發布觸發"),
    "scheduled_checks": ("scheduled_checks", "scheduled checks", "排程檢查"),
    "security_reporting_channel": (
        "security_reporting_channel",
        "security reporting channel",
        "安全通報管道",
    ),
    "single_writer_merger": (
        "single_writer_merger",
        "single writer merger",
        "單一寫入者",
    ),
    "self_hosted_environments": (
        "self_hosted_environments",
        "self-hosted environments",
        "self-hosted 環境",
    ),
    "self_hosted_runner": (
        "self_hosted_runner",
        "self-hosted runner",
        "self-hosted 登記",
    ),
    # Milestone 21 (#1265) split the single verification_mode setting by
    # repository visibility; each half keeps its own keyword map.
    "verification_mode_private": (
        "verification_mode_private",
        "private verification mode",
        "private 驗證模式",
    ),
    "verification_mode_public": (
        "verification_mode_public",
        "public verification mode",
        "public 驗證模式",
    ),
}

ADMIN_ALIGNMENT = {
    "always": (
        "can approve own change",
        "can approve their own change",
        "may approve own change",
        "may approve their own change",
        "可核准自己的變更",
        "可以核准自己的變更",
    ),
    "off": (
        "cannot approve own change",
        "cannot approve their own change",
        "can't approve own change",
        "can't approve their own change",
        "不能核准自己的變更",
        "不得核准自己的變更",
        "不可核准自己的變更",
    ),
}
ADMIN_CONTRADICTIONS = {
    "always": ADMIN_ALIGNMENT["off"],
    "off": ADMIN_ALIGNMENT["always"],
}


def _contains(text: str, term: str) -> bool:
    folded = text.casefold()
    candidate = term.casefold()
    if re.fullmatch(r"[a-z0-9_.-]+", candidate):
        return (
            re.search(
                rf"(?<![a-z0-9_.-]){re.escape(candidate)}(?![a-z0-9_.-])",
                folded,
            )
            is not None
        )
    return candidate in folded


def _scalar_terms(value: object) -> tuple[str, ...]:
    if isinstance(value, bool):
        return (
            ("true", "enabled", "on", "啟用")
            if value
            else ("false", "disabled", "off", "停用")
        )
    if value is None:
        return ("null", "none", "unset", "未設定")
    if isinstance(value, (str, int)):
        text = str(value)
        return tuple(dict.fromkeys((text, text.replace("-", " "))))
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")),)


def _matches_value(line: str, value: object) -> bool:
    if isinstance(value, list):
        if not value:
            return any(_contains(line, term) for term in ("[]", "none", "無"))
        return all(
            any(_contains(line, term) for term in _scalar_terms(item))
            for item in value
        )
    return any(_contains(line, term) for term in _scalar_terms(value))


def _other_values(key: str, expected: object) -> tuple[object, ...]:
    kind, allowed = settings_schema.INTENT_SETTINGS[key]
    if kind == settings_schema.CHOICE:
        return tuple(value for value in allowed if value != expected)
    if kind == settings_schema.BOOL:
        return (not expected,) if isinstance(expected, bool) else (True, False)
    return ()


def _classify_line(key: str, value: object, line: str) -> str:
    if key == "admin_bypass" and isinstance(value, str):
        if any(
            _contains(line, term)
            for term in ADMIN_CONTRADICTIONS.get(value, ())
        ):
            return "drift"
        if any(
            _contains(line, term) for term in ADMIN_ALIGNMENT.get(value, ())
        ):
            return "aligned"
    expected = _matches_value(line, value)
    other = any(
        _matches_value(line, candidate)
        for candidate in _other_values(key, value)
    )
    if expected and not other:
        return "aligned"
    if other and not expected:
        return "drift"
    return "inconclusive"


def review(
    root: Path,
    settings: Sequence[Mapping[str, object]],
    languages: object,
) -> list[dict[str, object]]:
    """Review changed policy settings against README and docs Markdown."""
    documents = writing_guide_review.project_documents(root, languages)
    readable: list[tuple[str, int, str]] = []
    unreadable: list[str] = []
    for name in documents:
        try:
            lines = (root / name).read_text(encoding="utf-8").splitlines()
        except OSError, UnicodeError:
            unreadable.append(f"{name}:1")
            continue
        readable.extend(
            (name, number, line) for number, line in enumerate(lines, 1)
        )

    rows: list[dict[str, object]] = []
    for setting in sorted(settings, key=lambda row: str(row.get("key", ""))):
        key = setting.get("key")
        if (
            not isinstance(key, str)
            or key not in POLICY_KEYWORDS
            or setting.get("class") == "unchanged"
        ):
            continue
        value = setting.get("after")
        matches = [
            (name, number, _classify_line(key, value, line))
            for name, number, line in readable
            if any(_contains(line, term) for term in POLICY_KEYWORDS[key])
        ]
        locations = sorted(
            {*unreadable, *(f"{name}:{number}" for name, number, _ in matches)}
        )
        states = {state for _name, _number, state in matches}
        if unreadable:
            status = "inconclusive"
            reason = "At least one project-owned Markdown file is unreadable."
        elif "drift" in states:
            status = "drift"
            reason = "At least one candidate line states another policy value."
        elif "inconclusive" in states:
            status = "inconclusive"
            reason = "A candidate line does not state one supported value."
        elif matches:
            status = "aligned"
            reason = "Every candidate line agrees with the new value."
        else:
            status = "not-applicable"
            reason = (
                "No project-owned README or docs line mentions this policy key."
            )
        rows.append(
            {
                "key": key,
                "locations": locations,
                "reason": reason,
                "status": status,
                "value": value,
            }
        )
    return rows


def blocking(rows: Sequence[Mapping[str, object]]) -> bool:
    """Return whether any policy-documentation result blocks delivery."""
    return any(row.get("status") in BLOCKING for row in rows)
