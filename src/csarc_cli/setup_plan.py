"""Setup planner for ``csarc init`` and ``csarc adopt`` (Issue #1078).

The planner asks only for intent that no unique source decides (SPEC-009
"Setup questions"): detected or explicit values are never asked again, a
work-mode preset expands into ordinary, overridable intent, and a
non-interactive run that lacks a required decision stops before any render,
GitHub write, or file write with one repair line.

Everything here is pure: prompts go through an injected ``ask`` callable and
GitHub reads through an injected ``api`` runner, so the question transcript,
warnings, and the approval-route preflight are testable without Copier.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

WORK_MODES = ("solo-local", "solo-hosted", "team", "custom")
DEFAULT_WORK_MODE = "solo-local"
GOVERNANCE_KEYS = ("verification_mode", "admin_bypass", "copilot_review")
# #1058 decision 14: a preset only expands into saved intent; its name is
# never stored. The local preset also turns hosted-only automation off.
PRESET_VALUES: dict[str, dict[str, object]] = {
    "solo-local": {
        "verification_mode": "local",
        "admin_bypass": "always",
        "copilot_review": "allowed",
        "lifecycle": [],
        "scheduled_checks": [],
    },
    "solo-hosted": {
        "verification_mode": "hosted",
        "admin_bypass": "always",
        "copilot_review": "allowed",
    },
    "team": {"verification_mode": "hosted", "admin_bypass": "off"},
    "custom": {},
}
# Keys a preset leaves to one more question each.
PRESET_QUESTIONS: dict[str, tuple[str, ...]] = {
    "solo-local": (),
    "solo-hosted": (),
    "team": ("copilot_review",),
    "custom": GOVERNANCE_KEYS,
}
# New-project defaults the CLI applies (#1058 decision 14); copier.yml keeps
# its own defaults only for a raw Copier render.
NEW_PROJECT_DEFAULTS: dict[str, object] = {
    "documentation_mode": "content-only",
    "documentation_languages": "zh-tw",
}
LICENSES = ("proprietary", "MIT", "Apache-2.0")
LANGUAGES = ("go", "python", "rust", "typescript")
DOCUMENTATION_LANGUAGES = ("zh-tw", "en", "zh-tw+en", "en+zh-tw")
CHOICES: dict[str, tuple[str, ...]] = {
    "verification_mode": ("local", "hosted"),
    "admin_bypass": ("off", "beta-only", "always"),
    "copilot_review": ("allowed", "off"),
    "governance_mode": ("managed", "observe"),
    "release_trigger": ("main", "manual"),
    "project_visibility": ("public", "private", "internal"),
}
# The merge gate's peer-approver roles (scripts/pr_lifecycle.py
# MAINTAINER_PERMISSIONS); a parity test keeps the two sets equal.
MAINTAINER_ROLES = frozenset({"admin", "maintain"})
WRITE_ROLES = frozenset({"admin", "maintain", "write"})
ROUTE_OBSERVED = "route-observed"
NONE_OBSERVED = "none-observed"
INCONCLUSIVE = "inconclusive"
ROUTE_STATES = (ROUTE_OBSERVED, NONE_OBSERVED, INCONCLUSIVE)
CONFIRMATIONS = ("second-approver", "copilot-entitlement")
PLACEHOLDERS = frozenset({"todo", "tbd", "placeholder", "a cyber-arch project"})
GITHUB_REPOSITORY_URL = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
)
_EMAIL = (
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:[.][A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*[.][A-Za-z]{2,}"
)
_HTTPS = (
    r"https://[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:[.][A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*[.][A-Za-z]{2,}"
    r"(?::[0-9]{1,5})?(?:[/?#][^ <>]*)?"
)
PRIVATE_CHANNEL = re.compile(rf"^(?:(?:mailto:)?{_EMAIL}|{_HTTPS})$")
GITHUB_CHANNEL = re.compile(
    r"(?i)^https?://(?:[^/?#]*[.@])?github[.]com(?:[:/?#]|$)"
)
CHANNEL_CANDIDATE = re.compile(rf"(?:mailto:)?{_EMAIL}|{_HTTPS}")

# Stable warning codes (SPEC-009 "Setup warnings"); never renumbered.
WARNINGS = {
    "W01": "admin-bypass-always",
    "W02": "local-verification",
    "W03": "second-approver-confirmed",
    "W04": "copilot-entitlement-confirmed",
    "W05": "copilot-reference-only",
    "W06": "local-beta-only",
    "W07": "runner-not-admin",
    "W08": "no-ruleset-plan",
    "W09": "governance-observe",
    "W10": "coverage-relaxed",
    "W11": "public-proprietary",
    "W12": "documentation-scope",
    "W13": "public-codeql-off",
    "W15": "local-actions-minutes",
    "W20": "ui-merge-without-approval",
    "W21": "single-writer-unobserved",
}

Ask = Callable[[str], str]
Emit = Callable[[str], None]
Runner = Callable[[Sequence[str]], tuple[int, str, str]]


class SetupError(ValueError):
    """A setup decision is missing or invalid; nothing was rendered."""


@dataclass(frozen=True)
class Question:
    """One setup question generated from the SPEC-009 classification."""

    key: str
    prompt: str
    choices: tuple[str, ...] = ()
    default: str | None = None
    kind: str = "text"  # text, choice, multi, bool, confirm
    allow_empty: bool = False
    data_hint: str = "<value>"


@dataclass
class Session:
    """Ask setup questions on a TTY, or collect what a script must pass."""

    interactive: bool
    ask: Ask
    emit: Emit
    asked: list[str] = field(default_factory=list)
    confirmations: list[str] = field(default_factory=list)
    missing: list[tuple[str, str]] = field(default_factory=list)
    suggested: list[str] = field(default_factory=list)
    transcript: list[str] = field(default_factory=list)

    def _prompt(self, text: str) -> str:
        self.transcript.append(text)
        answer = self.ask(text)
        self.transcript.append(answer)
        return answer.strip()

    def question(self, question: Question) -> object:
        """Return one answer, its suggestion, or record it as missing."""
        if not self.interactive:
            if question.default is None:
                self.missing.append((question.key, question.data_hint))
                return None
            self.suggested.append(question.key)
            return parse_answer(question, question.default)
        number = len(self.asked) + 1
        self.asked.append(question.key)
        options = (
            f" ({', '.join(question.choices)})" if question.choices else ""
        )
        default = (
            f" [{question.default}]"
            if question.default is not None
            else " [none]"
            if question.allow_empty
            else ""
        )
        text = f"[{number}] {question.prompt}{options}{default}: "
        for _attempt in range(3):
            answer = self._prompt(text)
            if not answer and question.default is not None:
                answer = question.default
            try:
                return parse_answer(question, answer)
            except SetupError as error:
                self.emit(f"  {error}")
        raise SetupError(
            f"No valid answer for {question.key}; pass --data "
            f"{question.key}={question.data_hint} instead."
        )

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        """Ask one yes/no confirmation that is not a setup question."""
        if not self.interactive:
            return False
        self.confirmations.append(prompt)
        suffix = " [Y/n]: " if default else " [y/N]: "
        answer = self._prompt(prompt + suffix).casefold()
        if not answer:
            return default
        return answer in {"y", "yes"}

    def require_complete(self, command: str) -> None:
        """Fail before any render when a script omitted a required input."""
        if not self.missing:
            return
        flags = " ".join(
            f"--data {key}={hint}" for key, hint in dict(self.missing).items()
        )
        keys = ", ".join(dict(self.missing))
        raise SetupError(
            f"Missing required setup input ({keys}); nothing was rendered or "
            f"written. Rerun `csarc {command}` with {flags}, or answer in a "
            "terminal."
        )


def parse_answer(question: Question, answer: str) -> object:  # noqa: C901
    """Validate one answer and return it with its schema type."""
    if question.kind in {"bool", "confirm"}:
        lowered = answer.casefold()
        if lowered in {"y", "yes", "true", "1"}:
            return True
        if lowered in {"n", "no", "false", "0"}:
            return False
        raise SetupError("Answer yes or no.")
    if question.kind == "multi":
        if answer.casefold() in {"", "none"}:
            if question.allow_empty:
                return []
            raise SetupError("Select at least one value.")
        values = [part.strip() for part in answer.split(",") if part.strip()]
        unknown = [value for value in values if value not in question.choices]
        if unknown:
            raise SetupError(
                "Choose from "
                + ", ".join(question.choices)
                + " (comma-separated)."
            )
        return list(dict.fromkeys(values))
    if question.kind == "choice":
        if answer not in question.choices:
            raise SetupError(
                "Choose one of " + ", ".join(question.choices) + "."
            )
        return answer
    if not answer.strip():
        raise SetupError("A non-empty value is required.")
    if question.key == "project_description" and (
        answer.strip().casefold() in PLACEHOLDERS or "<" in answer
    ):
        raise SetupError("Enter the approved purpose without placeholder text.")
    if question.key == "repository_url" and not GITHUB_REPOSITORY_URL.fullmatch(
        answer
    ):
        raise SetupError("Use https://github.com/owner/repository.")
    if question.key == "security_reporting_channel" and not private_channel(
        answer
    ):
        raise SetupError(
            "Use a private channel outside GitHub: an email address, a "
            "mailto: link, or a non-GitHub https:// URL."
        )
    return answer.strip()


def private_channel(channel: str) -> bool:
    """Mirror copier.yml's public security_reporting_channel validator."""
    value = channel.strip()
    if not value or value.casefold() in PLACEHOLDERS or "<" in value:
        return False
    return (
        GITHUB_CHANNEL.search(value) is None
        and PRIVATE_CHANNEL.fullmatch(value) is not None
    )


def disclosure_channels(texts: Sequence[str]) -> list[str]:
    """Return distinct private reporting channels named by policy texts."""
    found: list[str] = []
    for text in texts:
        for match in CHANNEL_CANDIDATE.finditer(text):
            candidate = match.group().rstrip(".,;)")
            if private_channel(candidate) and candidate not in found:
                found.append(candidate)
    return found


@dataclass(frozen=True)
class Detection:
    """One adopt detection shown on the confirmation screen."""

    key: str
    value: object
    source: str
    state: str = "known"  # known, unknown, ambiguous
    candidates: tuple[str, ...] = ()


@dataclass
class SetupResult:
    """Resolved setup inputs, their sources, and the question transcript."""

    mode: str
    work_mode: str
    values: dict[str, object] = field(default_factory=dict)
    sources: dict[str, dict[str, str | None]] = field(default_factory=dict)

    def set(
        self, key: str, value: object, source: str, note: str | None
    ) -> None:
        """Record one resolved input with its SPEC-008 source and note."""
        self.values[key] = value
        self.sources[key] = {"note": note, "source": source}


def _text_question(key: str, prompt: str, hint: str) -> Question:
    return Question(key=key, prompt=prompt, data_hint=hint)


def _choice_question(key: str, prompt: str, default: str | None) -> Question:
    choices = CHOICES[key]
    return Question(
        key=key,
        prompt=prompt,
        choices=choices,
        default=default,
        kind="choice",
        data_hint="|".join(choices),
    )


def _resolve(
    session: Session,
    result: SetupResult,
    explicit: Mapping[str, str],
    question: Question,
) -> object:
    """Resolve one key from --data, a TTY answer, or its suggestion."""
    if question.key in explicit:
        return explicit[question.key]
    answered = len(session.asked)
    value = session.question(question)
    if value is None:
        return None
    if len(session.asked) > answered:
        result.set(question.key, value, "explicit", "asked")
    else:
        result.set(question.key, value, "derived", "suggested default")
    return value


def check_work_mode(requested: str | None) -> None:
    """Reject an unknown preset before any question is asked."""
    if requested is not None and requested not in WORK_MODES:
        raise SetupError(
            f"Unknown work mode {requested!r}; use --preset "
            + "|".join(WORK_MODES)
            + "."
        )


def plan_work_mode(
    session: Session,
    result: SetupResult,
    explicit: Mapping[str, str],
    requested: str | None,
) -> None:
    """Expand one work-mode preset; explicit --data always overrides it."""
    check_work_mode(requested)
    if requested is None:
        question = Question(
            key="work_mode",
            prompt="Work mode",
            choices=WORK_MODES,
            default=DEFAULT_WORK_MODE,
            kind="choice",
        )
        answered = len(session.asked)
        mode = str(session.question(question))
        chosen = len(session.asked) > answered
        if not chosen:
            # The documented non-interactive value, not a guess (#1058 d14).
            session.suggested.remove("work_mode")
    else:
        mode = requested
        chosen = True
    result.work_mode = mode
    source = "explicit" if chosen else "derived"
    note = f"work mode {mode}"
    for key, value in PRESET_VALUES[mode].items():
        if key not in explicit:
            result.set(key, value, source, note)
    for key in PRESET_QUESTIONS[mode]:
        default = {
            "verification_mode": "local",
            "admin_bypass": "always",
            "copilot_review": "allowed",
        }[key]
        _resolve(
            session,
            result,
            explicit,
            _choice_question(key, key.replace("_", " ").capitalize(), default),
        )


def _governance_value(
    result: SetupResult, explicit: Mapping[str, str], key: str, fallback: str
) -> str:
    return str(explicit.get(key, result.values.get(key, fallback)))


def plan_release_trigger(
    session: Session,
    result: SetupResult,
    explicit: Mapping[str, str],
    *,
    release_ownership: str,
) -> None:
    """Ask release_trigger only for a hosted csarc-owned release writer."""
    hosted = _governance_value(result, explicit, "verification_mode", "local")
    if hosted == "hosted" and release_ownership == "csarc-owned":
        _resolve(
            session,
            result,
            explicit,
            _choice_question("release_trigger", "Release trigger", "main"),
        )


def plan_init(
    session: Session,
    explicit: Mapping[str, str],
    requested_mode: str | None,
) -> SetupResult:
    """Resolve the six init questions plus preset and release follow-ups."""
    check_work_mode(requested_mode)
    result = SetupResult(mode="init", work_mode=DEFAULT_WORK_MODE)
    for key, value in NEW_PROJECT_DEFAULTS.items():
        if key not in explicit and key != "documentation_languages":
            result.set(key, value, "derived", "new-project default")
    _resolve(
        session,
        result,
        explicit,
        _text_question(
            "project_description",
            "One-sentence project purpose",
            "<one-sentence purpose>",
        ),
    )
    if "languages" not in explicit and "language" not in explicit:
        _resolve(
            session,
            result,
            explicit,
            Question(
                key="languages",
                prompt="Programming languages (comma-separated, or none)",
                choices=LANGUAGES,
                kind="multi",
                allow_empty=True,
                data_hint="<go,python,rust,typescript or empty>",
            ),
        )
    license_value = _resolve(
        session,
        result,
        explicit,
        Question(
            key="project_license",
            prompt="License",
            choices=LICENSES,
            default="proprietary",
            kind="choice",
            data_hint="|".join(LICENSES),
        ),
    )
    if license_value != "custom":
        _resolve(
            session,
            result,
            explicit,
            _text_question(
                "copyright_holder",
                "Copyright holder (never inferred from the repository owner)",
                "<legal holder>",
            ),
        )
    _resolve(
        session,
        result,
        explicit,
        Question(
            key="documentation_languages",
            prompt="Documentation language (first is primary)",
            choices=DOCUMENTATION_LANGUAGES,
            default=str(NEW_PROJECT_DEFAULTS["documentation_languages"]),
            kind="choice",
            data_hint="|".join(DOCUMENTATION_LANGUAGES),
        ),
    )
    plan_work_mode(session, result, explicit, requested_mode)
    plan_release_trigger(
        session,
        result,
        explicit,
        release_ownership=str(explicit.get("release_ownership", "csarc-owned")),
    )
    return result


def _detection_lines(detections: Sequence[Detection]) -> list[str]:
    lines = ["Detected repository facts:"]
    for item in detections:
        shown = (
            ", ".join(str(part) for part in item.value)
            if isinstance(item.value, list)
            else str(item.value)
        )
        lines.append(f"  {item.key}: {shown or '(none)'} ({item.source})")
    return lines


def plan_adopt(  # noqa: C901
    session: Session,
    explicit: Mapping[str, str],
    requested_mode: str | None,
    detections: Sequence[Detection],
    *,
    release_ownership: str,
    dockerfile: bool,
) -> SetupResult:
    """Confirm detections, then ask governance, work mode, and gaps."""
    check_work_mode(requested_mode)
    result = SetupResult(mode="adopt", work_mode=DEFAULT_WORK_MODE)
    shown = [
        item
        for item in detections
        if item.state == "known" and item.key not in explicit
    ]
    for item in shown:
        result.set(item.key, item.value, "derived", f"detected: {item.source}")
    if shown and session.interactive:
        for line in _detection_lines(shown):
            session.emit(line)
        accepted = session.question(
            Question(
                key="detected",
                prompt="Use these detected values",
                default="yes",
                kind="confirm",
            )
        )
        if accepted is False:
            raise SetupError(
                "Detected values were not accepted; nothing was written. "
                "Rerun csarc adopt with --data KEY=VALUE for each value to "
                "change."
            )
    for item in detections:
        if item.state == "known" or item.key in explicit:
            continue
        if item.key == "project_description":
            _resolve(
                session,
                result,
                explicit,
                _text_question(
                    item.key,
                    "One-sentence project purpose (no manifest description)",
                    "<one-sentence purpose>",
                ),
            )
        elif item.key == "copyright_holder":
            _resolve(
                session,
                result,
                explicit,
                _text_question(
                    item.key,
                    "Copyright holder for the new LICENSE",
                    "<legal holder>",
                ),
            )
        elif item.state == "ambiguous":
            _resolve(
                session,
                result,
                explicit,
                Question(
                    key=item.key,
                    prompt=f"{item.key} is ambiguous; choose one",
                    choices=item.candidates,
                    kind="choice" if item.candidates else "text",
                    data_hint="<value>",
                ),
            )
    _resolve(
        session,
        result,
        explicit,
        _choice_question(
            "governance_mode",
            "Governance mode (managed applies repository policies)",
            "managed",
        ),
    )
    plan_work_mode(session, result, explicit, requested_mode)
    if dockerfile:
        _resolve(
            session,
            result,
            explicit,
            Question(
                key="container",
                prompt="A Dockerfile exists; add the CSARC container scan",
                default="no",
                kind="bool",
                data_hint="true|false",
            ),
        )
    plan_release_trigger(
        session, result, explicit, release_ownership=release_ownership
    )
    return result


def plan_repository(
    session: Session,
    result: SetupResult,
    explicit: Mapping[str, str],
    *,
    resolved: bool,
    visibility_known: bool,
) -> None:
    """Ask for repository identity only when no origin resolves it."""
    if resolved or "repository_url" in explicit:
        pass
    else:
        _resolve(
            session,
            result,
            explicit,
            _text_question(
                "repository_url",
                "GitHub repository URL",
                "https://github.com/<owner>/<repository>",
            ),
        )
    if (
        not visibility_known
        and "project_visibility" not in explicit
        and session.interactive
    ):
        _resolve(
            session,
            result,
            explicit,
            _choice_question(
                "project_visibility", "Repository visibility", "private"
            ),
        )


def plan_security_channel(
    session: Session,
    result: SetupResult,
    explicit: Mapping[str, str],
    *,
    visibility: str,
    detected: str | None,
) -> None:
    """Require a private reporting channel for a public repository."""
    if visibility != "public" or "security_reporting_channel" in explicit:
        return
    if detected is not None:
        result.set(
            "security_reporting_channel",
            detected,
            "derived",
            "detected: disclosure policy",
        )
        return
    _resolve(
        session,
        result,
        explicit,
        _text_question(
            "security_reporting_channel",
            "Private vulnerability reporting channel outside GitHub",
            "<security@example.com>",
        ),
    )


def invalid_combinations(
    values: Mapping[str, object], explicit: Mapping[str, str], *, mode: str
) -> list[str]:
    """Return one repair line per invalid setup combination."""
    errors: list[str] = []
    languages = values.get("languages")
    language_set = set(languages) if isinstance(languages, list) else set()
    if (
        mode == "init"
        and "rust" in language_set
        and _truthy(values.get("container"))
    ):
        errors.append(
            "The Rust library starter builds no binary for the Docker "
            "starter; pass --data container=false."
        )
    if _truthy(values.get("enable_codeql")) and not language_set & {
        "go",
        "python",
        "typescript",
    }:
        errors.append(
            "enable_codeql needs go, python, or typescript; pass --data "
            "enable_codeql=false."
        )
    if "release_trigger" in explicit and not (
        values.get("verification_mode") == "hosted"
        and values.get("release_ownership", "csarc-owned") == "csarc-owned"
    ):
        errors.append(
            "release_trigger applies only to hosted verification with a "
            "csarc-owned release; drop --data release_trigger."
        )
    return errors


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).casefold() in {"1", "true", "yes", "on"}


def native_required_approvals(values: Mapping[str, object]) -> int:
    """Return the rendered Ruleset's native approval count (rulesets.json)."""
    return (
        1
        if values.get("verification_mode") == "local"
        and values.get("admin_bypass") == "off"
        else 0
    )


def copilot_route_possible(values: Mapping[str, object]) -> bool:
    """Copilot counts only when allowed and no native approval is required."""
    return (
        values.get("copilot_review") == "allowed"
        and native_required_approvals(values) == 0
    )


def _api_json(api: Runner, arguments: Sequence[str]) -> object:
    code, output, error = api(arguments)
    if code != 0:
        raise SetupError(error.strip() or "GitHub API request failed")
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise SetupError("GitHub returned invalid JSON") from exc


def _collaborators(api: Runner, repository: str) -> list[Mapping[str, object]]:
    pages = _api_json(
        api,
        [
            "--paginate",
            "--slurp",
            f"repos/{repository}/collaborators?affiliation=all&per_page=100",
        ],
    )
    if not isinstance(pages, list):
        raise SetupError("the collaborator list has an unexpected shape")
    rows: list[Mapping[str, object]] = []
    for page in pages:
        items = page if isinstance(page, list) else [page]
        for item in items:
            if not isinstance(item, Mapping):
                raise SetupError("a collaborator entry has no fields")
            rows.append(item)
    return rows


def observe_actor(api: Runner) -> str:
    """Return the authenticated login that runs this plan."""
    payload = _api_json(api, ["user"])
    login = payload.get("login") if isinstance(payload, Mapping) else None
    if not isinstance(login, str) or not login:
        raise SetupError("the authenticated GitHub login is unavailable")
    return login


def approval_route(  # noqa: C901
    api: Runner,
    repository: str | None,
    owner_type: str | None,
) -> tuple[str, str]:
    """Classify the peer-approval route the merge gate would accept.

    Only positive evidence is ``route-observed``: another ``User`` account
    whose live ``role_name`` the gate accepts. A complete read that shows
    none is ``none-observed``; any missing, partial, or unreadable fact is
    ``inconclusive``. The result describes what this read observed; it is
    never proof that no other approver exists.
    """
    if repository is None:
        return (
            INCONCLUSIVE,
            "the repository is not on GitHub yet, so its collaborators "
            "cannot be read",
        )
    try:
        actor = observe_actor(api)
        collaborators = _collaborators(api, repository)
    except SetupError as error:
        return INCONCLUSIVE, f"the collaborator read is incomplete: {error}"
    incomplete = ""
    for item in collaborators:
        login = item.get("login")
        role = item.get("role_name")
        account = item.get("type")
        if not isinstance(login, str) or not login:
            incomplete = "a collaborator entry has no login"
            continue
        if not isinstance(role, str) or not role:
            incomplete = f"collaborator {login} has no role_name"
            continue
        if (
            account == "User"
            and login.casefold() != actor.casefold()
            and role in MAINTAINER_ROLES
        ):
            return (
                ROUTE_OBSERVED,
                f"{login} was observed with the {role} role at plan time",
            )
    if incomplete:
        return INCONCLUSIVE, incomplete
    if str(owner_type or "").casefold() == "organization":
        organization = repository.split("/", 1)[0]
        try:
            membership = _api_json(
                api,
                [
                    "user/memberships/orgs/"
                    + urllib.parse.quote(organization, safe="")
                ],
            )
        except SetupError as error:
            return (
                INCONCLUSIVE,
                f"organization roles of {organization} are not readable: "
                f"{error}",
            )
        role = (
            membership.get("role") if isinstance(membership, Mapping) else None
        )
        if role != "admin":
            return (
                INCONCLUSIVE,
                f"organization roles of {organization} are visible only to "
                "its owners",
            )
    return (
        NONE_OBSERVED,
        "no account other than the runner was observed with a maintain or "
        "admin role",
    )


def preflight_applies(values: Mapping[str, object]) -> bool:
    """`off`, and the stable path of `beta-only`, need a peer approver."""
    return values.get("admin_bypass") in {"off", "beta-only"}


def resolve_approval(
    session: Session,
    values: Mapping[str, object],
    state: str,
    reason: str,
    *,
    confirm_second: bool,
    confirm_copilot: bool,
) -> dict[str, object]:
    """Apply the three-state approval preflight; block or record consent."""
    bypass = values.get("admin_bypass")
    scope = "stable work" if bypass == "beta-only" else "every merge"
    record: dict[str, object] = {
        "confirmation": None,
        "reason": reason,
        "state": state,
    }
    if state == ROUTE_OBSERVED:
        return record
    possible = copilot_route_possible(values)
    if confirm_copilot and not possible:
        raise SetupError(
            f"admin_bypass {bypass} needs a peer approver for {scope}; a "
            "Copilot review cannot replace it here because "
            + (
                "copilot_review is off"
                if values.get("copilot_review") != "allowed"
                else "local verification with admin_bypass off requires one "
                "native approval"
            )
            + ". Pass --data admin_bypass=always or add a maintainer."
        )
    if possible and (
        confirm_copilot
        or session.confirm(
            f"Approval route is {state} ({reason}). Does this repository "
            "have Copilot code review entitlement?"
        )
    ):
        record["confirmation"] = "copilot-entitlement"
        return record
    if state == INCONCLUSIVE:
        if confirm_second or session.confirm(
            f"Approval route is inconclusive ({reason}). Can another "
            "maintainer approve pull requests?"
        ):
            record["confirmation"] = "second-approver"
            return record
        raise SetupError(
            f"Approval route for admin_bypass {bypass} is inconclusive "
            f"({reason}); nothing was written. Pass "
            "--confirm-second-approver after checking that another "
            "maintainer can approve, or --data admin_bypass=always."
        )
    raise SetupError(
        f"No peer approver was observed for admin_bypass {bypass} ({reason}); "
        f"{scope} would wait for an approval nobody observed can give. Add a "
        "maintainer and plan again, or pass --data admin_bypass=always."
    )


def single_writer_observed(
    api: Runner, repository: str | None, owner_type: str | None
) -> bool:
    """Return True only when one read observes the runner as sole writer."""
    if repository is None or str(owner_type or "").casefold() != "user":
        return False
    try:
        actor = observe_actor(api)
        collaborators = _collaborators(api, repository)
        keys = _api_json(
            api,
            ["--paginate", "--slurp", f"repos/{repository}/keys?per_page=100"],
        )
    except SetupError:
        return False
    writers = set()
    for item in collaborators:
        login, role = item.get("login"), item.get("role_name")
        if not isinstance(login, str) or not isinstance(role, str):
            return False
        if role in WRITE_ROLES:
            writers.add(login.casefold())
    flat = [
        key
        for page in (keys if isinstance(keys, list) else [])
        for key in (page if isinstance(page, list) else [page])
    ]
    if any(
        not isinstance(key, Mapping) or type(key.get("read_only")) is not bool
        for key in flat
    ):
        return False
    if any(
        isinstance(key, Mapping) and key["read_only"] is False for key in flat
    ):
        return False
    return writers == {actor.casefold()}


def _warning(
    code: str, subject: str, message: str, command: str | None = None
) -> dict[str, object]:
    return {
        "code": f"{code}-{WARNINGS[code]}",
        "command": command,
        "message": message,
        "subject": subject,
    }


def setup_warnings(  # noqa: C901
    values: Mapping[str, object],
    *,
    approval: Mapping[str, object] | None,
    runner_role: str | None,
    plan_name: str | None,
    single_writer: bool | None,
) -> list[dict[str, object]]:
    """Return the stable, non-blocking setup warnings for one plan."""
    rows: list[dict[str, object]] = []
    bypass = values.get("admin_bypass")
    local = values.get("verification_mode") == "local"
    visibility = values.get("project_visibility")
    if bypass == "always":
        rows.append(
            _warning(
                "W01",
                "admin_bypass",
                "No second person reviews merges; evidence and the audit "
                "trail compensate, and a UI merge without a trailer is "
                "reported as untraced.",
                "csarc update --data admin_bypass=off",
            )
        )
    if local:
        rows.append(
            _warning(
                "W02",
                "verification_mode",
                "Local verification evidence is self-attested; anyone with "
                "write access can forge it.",
                "csarc update --data verification_mode=hosted",
            )
        )
    confirmation = None if approval is None else approval.get("confirmation")
    approval_reason = "" if approval is None else approval.get("reason")
    if confirmation == "second-approver":
        rows.append(
            _warning(
                "W03",
                "admin_bypass",
                "You confirmed another maintainer can approve although the "
                f"read was inconclusive ({approval_reason}); "
                "if that is wrong, pull requests cannot merge.",
                "csarc update --data admin_bypass=always",
            )
        )
    if confirmation == "copilot-entitlement":
        rows.append(
            _warning(
                "W04",
                "copilot_review",
                "A Copilot review may be the only merge route; if the "
                "entitlement or quota lapses, pull requests cannot merge.",
                "csarc update --data admin_bypass=always",
            )
        )
    if (
        bypass == "off"
        and values.get("copilot_review") == "allowed"
        and native_required_approvals(values) == 1
    ):
        rows.append(
            _warning(
                "W05",
                "copilot_review",
                "With local verification and admin_bypass off the Ruleset "
                "requires one native approval; a Copilot review is "
                "reference only.",
            )
        )
    if local and bypass == "beta-only":
        rows.append(
            _warning(
                "W06",
                "admin_bypass",
                "In local mode only the lifecycle tooling enforces the "
                "stable-only approval requirement.",
            )
        )
    if bypass != "off" and runner_role is not None and runner_role != "admin":
        rows.append(
            _warning(
                "W07",
                "admin_bypass",
                f"The runner's live role is {runner_role}, not admin; an "
                "admin must authorize bypass merges.",
            )
        )
    if visibility == "private" and plan_name == "free":
        rows.append(
            _warning(
                "W08",
                "verification_mode",
                "GitHub Free does not enforce Rulesets on private "
                "repositories; merges use server_enforcement=none.",
            )
        )
    if values.get("governance_mode") == "observe":
        rows.append(
            _warning(
                "W09",
                "governance_mode",
                "CSARC applies no Ruleset in observe mode; only manual "
                "merges are possible.",
                "csarc update --data governance_mode=managed",
            )
        )
    threshold = values.get("coverage_threshold")
    if values.get("coverage_mode") == "diff" or (
        isinstance(threshold, int) and threshold < 80
    ):
        rows.append(
            _warning(
                "W10",
                "coverage_mode",
                "Coverage measures only changed lines or uses a threshold "
                "below 80.",
            )
        )
    if (
        visibility == "public"
        and values.get("project_license") == "proprietary"
    ):
        rows.append(
            _warning(
                "W11",
                "project_license",
                "A public repository uses the proprietary license.",
            )
        )
    documentation = values.get("documentation_languages")
    if values.get("documentation_mode") == "off" or (
        isinstance(documentation, str) and "+" in documentation
    ):
        rows.append(
            _warning(
                "W12",
                "documentation_mode",
                "Documentation is unmanaged, or two languages must be "
                "maintained side by side.",
            )
        )
    languages = values.get("languages")
    codeql_languages = (
        set(languages) & {"go", "python", "typescript"}
        if isinstance(languages, list)
        else set()
    )
    if (
        visibility == "public"
        and codeql_languages
        and "enable_codeql" in values
        and not _truthy(values.get("enable_codeql"))
    ):
        rows.append(
            _warning(
                "W13",
                "enable_codeql",
                "A public repository with CodeQL-supported languages has "
                "CodeQL disabled.",
                "csarc update --data enable_codeql=true",
            )
        )
    scheduled = values.get("scheduled_checks")
    if local and (
        (isinstance(scheduled, list) and scheduled)
        or _truthy(values.get("enable_codeql", False))
    ):
        rows.append(
            _warning(
                "W15",
                "scheduled_checks",
                "Scheduled checks and CodeQL run on GitHub Actions and use "
                "Actions minutes even in local mode.",
            )
        )
    if local and bypass in {"beta-only", "always"}:
        rows.append(
            _warning(
                "W20",
                "admin_bypass",
                "The local Ruleset requires no native approval, so any "
                "writer can also merge in the GitHub UI.",
            )
        )
    if (
        visibility == "private"
        and plan_name == "free"
        and values.get("release_ownership", "csarc-owned") == "csarc-owned"
        and single_writer is False
    ):
        rows.append(
            _warning(
                "W21",
                "release_ownership",
                "Without Ruleset enforcement a csarc-owned release needs one "
                "observed writer; this read did not observe the runner as "
                "the only writer, so merges stay manual and untraced.",
            )
        )
    return rows


def setup_record(
    result: SetupResult,
    session: Session,
    *,
    warnings: Sequence[Mapping[str, object]],
    approval: Mapping[str, object] | None,
    explicit: Mapping[str, str],
) -> dict[str, object]:
    """Return the JSON setup record a plan and its report carry.

    ``sources`` gives each resolved key its SPEC-008 source and note: an
    explicit ``--data`` value or a TTY answer is ``explicit``, a detection,
    preset expansion, or suggestion is ``derived``. The work-mode name is
    shown here only; it never reaches the settings file.
    """
    sources: dict[str, dict[str, str | None]] = {
        key: dict(value) for key, value in result.sources.items()
    }
    for key in explicit:
        sources[key] = {"note": None, "source": "explicit"}
    return {
        "approval_route": None if approval is None else dict(approval),
        "questions": list(session.asked),
        "sources": dict(sorted(sources.items())),
        "suggested": sorted(set(session.suggested) - set(explicit)),
        "warnings": [dict(row) for row in warnings],
        "work_mode": result.work_mode,
    }
