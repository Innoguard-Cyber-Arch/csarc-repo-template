#!/usr/bin/env python3
"""Canonical merge evidence, durable summaries, and squash trailers (#1073).

One evidence payload binds a merge to the exact verified tree. The payload
is a JSON object serialized with a subset of RFC 8785 (JCS); its SHA-256
digest, the locator of the pull request's single durable summary comment,
and the verified tree travel in fixed `CSARC-*` trailers on the squash
commit. The trailers are an after-the-fact audit record, never evidence:
they cannot satisfy `verify` or any merge or release gate.

The governance baseline (where the merge audit starts) and the audit of the
merges after it live here too, so `csarc status` and the release path read
one implementation. `python3 merge_trace.py audit --strict` exits non-zero
when a merge after the baseline lacks valid trailers or evidence.

Shared verbatim between `scripts/`, `template/.csarc/scripts/`, and
`src/csarc_cli/merge_trace.py`. The third copy exists only because the
distributed `csarc` wheel ships `src/csarc_cli` alone. Keep all three copies
byte-identical; this module must parse under the Python 3.12 grammar
because hosted workflows may run it before Python 3.14 is set up.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENVELOPE_VERSION = 1
CONTRACT_SCHEMA = 1
CONTRACT_RELATIVE = Path("policies") / "merge-trailers.json"
# The writer marker for the governance baseline: the template source keeps
# the contract at the root, generated projects under `.csarc/`.
CONTRACT_TREE_PATHS = (
    ".csarc/policies/merge-trailers.json",
    "policies/merge-trailers.json",
)
ANSWERS_PATHS = (".csarc/config.yml", ".copier-answers.yml")
PROVENANCE_PATH = ".csarc/provenance.json"
WATCHED_PATHS = (*CONTRACT_TREE_PATHS, *ANSWERS_PATHS, PROVENANCE_PATH)
CANONICAL_REPOSITORY = "Innoguard-Cyber-Arch/csarc-repo-template"
CANONICAL_REPOSITORY_ID = 1_340_899_393
MAX_SAFE_INTEGER = 2**53 - 1
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
GITHUB_URL = re.compile(
    r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/"
    r"(?:pull|issues)/[1-9][0-9]*"
    r"(?:#(?:issuecomment|pullrequestreview|discussion_r)-[1-9][0-9]*)?"
)
COMMENT_LOCATOR = re.compile(
    r"https://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/"
    r"(?:pull|issues)/(?P<number>[1-9][0-9]*)"
    r"#issuecomment-(?P<comment>[1-9][0-9]*)"
)
TRAILER_LINE = re.compile(r"^(CSARC-[A-Za-z0-9-]+): (.+)$")
BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:")
ANSWER_COMMIT = re.compile(r"(?m)^_commit:[ \t]*['\"]?([^'\"\s]*)['\"]?[ \t]*$")
NOT_FOUND = re.compile(r"\(HTTP 404\)\s*$")
SUMMARY_MARKER = "csarc-merge-evidence: v1"
STATUS_PREFIX = "status: "
SUMMARY_STATUSES = ("attempt", "merged", "tree-mismatch", "trailer-mismatch")
ENVELOPE_PREFIX = "envelope: "
PAYLOAD_PREFIX = "payload: "
# Arrays whose order carries no meaning; producers sort them first.
SET_ARRAYS = frozenset({"labels", "runner_labels", "scopes", "toolchain"})
TIME_FIELDS = frozenset({"completed_at", "started_at"})
TRUST_VALUES = ("github-hosted", "self-attested-local")
MERGE_FINDINGS = (
    "traced",
    "untraced",
    "tree-mismatch",
    "evidence-missing",
    "evidence-digest-mismatch",
    "trailer-invalid",
    "inconclusive",
)
BLOCKING_FINDINGS = frozenset(MERGE_FINDINGS) - {"traced", "untraced"}


class EvidenceError(ValueError):
    """A payload, record, or trailer violates the documented contract."""


class RecordUnavailableError(RuntimeError):
    """GitHub could not be read, so a durable record is inconclusive."""


# A tuple keeps the handler valid under the Python 3.12 grammar.
CONTRACT_READ_ERRORS = (json.JSONDecodeError, EvidenceError)


def _validate_string(value: str, where: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise EvidenceError(f"{where} is not valid Unicode") from error
    if not unicodedata.is_normalized("NFC", value):
        raise EvidenceError(f"{where} is not NFC-normalized")


def _validate(value: object, where: str, key: str = "") -> None:  # noqa: C901
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise EvidenceError(f"{where} is outside the safe integer range")
        return
    if isinstance(value, float):
        raise EvidenceError(f"{where} is a floating-point number")
    if isinstance(value, str):
        _validate_string(value, where)
        if key in TIME_FIELDS and TIMESTAMP.fullmatch(value) is None:
            raise EvidenceError(f"{where} is not a YYYY-MM-DDTHH:MM:SSZ time")
        return
    if isinstance(value, list):
        if key in SET_ARRAYS and value != sorted(value):
            raise EvidenceError(f"{where} is a set-like array but unsorted")
        for index, item in enumerate(value):
            _validate(item, f"{where}[{index}]")
        return
    if isinstance(value, dict):
        for item_key, item in value.items():
            if not isinstance(item_key, str) or not item_key.isascii():
                raise EvidenceError(f"{where} has a non-ASCII key")
            _validate(item, f"{where}.{item_key}", item_key)
        return
    raise EvidenceError(f"{where} has an unsupported JSON type")


def canonical_bytes(payload: Mapping[str, object]) -> bytes:
    """Serialize one payload with the documented JCS subset, or refuse."""
    if not isinstance(payload, Mapping):
        raise EvidenceError("Evidence payload is not a JSON object")
    _validate(dict(payload), "payload")
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def payload_digest(data: bytes) -> str:
    """Return the `sha256:` digest of canonical payload bytes."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"Evidence payload repeats key {key!r}")
        result[key] = value
    return result


def _reject_float(text: str) -> object:
    raise EvidenceError(f"Evidence payload has a non-integer number {text}")


def parse_canonical(data: bytes) -> dict[str, Any]:
    """Parse stored bytes and require that they are already canonical."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise EvidenceError("Evidence payload starts with a byte-order mark")
    try:
        text = data.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError("Evidence payload is not valid JSON") from error
    if not isinstance(value, dict):
        raise EvidenceError("Evidence payload is not a JSON object")
    if canonical_bytes(value) != data:
        raise EvidenceError("Evidence payload bytes are not canonical")
    return value


def payload_schema(payload: Mapping[str, object]) -> int:
    """Return the payload's own schema version, or refuse a payload without.

    Readers accept any positive version: later payloads (for example the K1
    risk fields) add keys, and the digest covers every byte regardless.
    """
    version = payload.get("schema_version")
    if type(version) is not int or version < 1:
        raise EvidenceError("Evidence payload has no positive schema_version")
    return version


def envelope(data: bytes, *, trust: str, route: str) -> dict[str, object]:
    """Return the unhashed envelope stored beside one canonical payload."""
    payload = parse_canonical(data)
    payload_schema(payload)
    if trust not in TRUST_VALUES or payload.get("trust") != trust:
        raise EvidenceError("Evidence trust does not match its payload")
    return {
        "digest": payload_digest(data),
        "envelope_version": ENVELOPE_VERSION,
        "route": route,
        "trust": trust,
    }


@dataclass(frozen=True)
class Summary:
    """The one durable merge-evidence comment of a pull request."""

    status: str
    lines: tuple[str, ...]
    record: dict[str, Any]
    data: bytes


def summary_comment(
    record: Mapping[str, object],
    data: bytes,
    status: str = "attempt",
    lines: Iterable[str] = (),
) -> str:
    """Render the single durable summary comment for one pull request.

    The comment's own URL is the `locator`, carried in the `CSARC-Evidence`
    trailer. Only the status section may change after the merge.
    """
    if status not in SUMMARY_STATUSES:
        raise EvidenceError(f"Unknown summary status {status!r}")
    status_lines = [line for line in lines if line]
    if any("\n" in line or "\r" in line for line in status_lines):
        raise EvidenceError("Summary status lines must be single lines")
    return "\n".join(
        (
            SUMMARY_MARKER,
            STATUS_PREFIX + status,
            *status_lines,
            "",
            "Durable CSARC merge evidence for this pull request (one per "
            "pull request). The payload is replaced only while the status is "
            "`attempt` and never changes after the merge; the squash commit's "
            "CSARC-Evidence-SHA256 trailer detects any later edit.",
            "",
            "```text",
            ENVELOPE_PREFIX + canonical_bytes(record).decode("utf-8"),
            PAYLOAD_PREFIX + data.decode("utf-8"),
            "```",
        )
    )


def is_summary(body: str) -> bool:
    """Return whether one comment body claims to be the summary."""
    return body.split("\n", 1)[0].removesuffix("\r") == SUMMARY_MARKER


def parse_summary(body: str) -> Summary:
    """Return the status, envelope, and exact payload bytes of a summary."""
    lines = [line.removesuffix("\r") for line in body.split("\n")]
    if len(lines) < 2 or lines[0] != SUMMARY_MARKER:
        raise EvidenceError("Comment is not a CSARC merge evidence summary")
    status = lines[1].removeprefix(STATUS_PREFIX)
    if not lines[1].startswith(STATUS_PREFIX) or status not in (
        SUMMARY_STATUSES
    ):
        raise EvidenceError("Merge evidence summary has no valid status")
    end = lines.index("", 2) if "" in lines[2:] else len(lines)
    records = [line for line in lines if line.startswith(ENVELOPE_PREFIX)]
    payloads = [line for line in lines if line.startswith(PAYLOAD_PREFIX)]
    if len(records) != 1 or len(payloads) != 1:
        raise EvidenceError("Merge evidence summary is malformed")
    record = parse_canonical(
        records[0].removeprefix(ENVELOPE_PREFIX).encode("utf-8")
    )
    data = payloads[0].removeprefix(PAYLOAD_PREFIX).encode("utf-8")
    parse_canonical(data)
    return Summary(status, tuple(lines[2:end]), record, data)


def default_contract_path() -> Path:
    """Return the contract shipped beside this module's scripts directory."""
    return Path(__file__).resolve().parents[1] / CONTRACT_RELATIVE


def load_contract(path: Path | None = None) -> dict[str, Any]:
    """Read the machine-readable trailer contract, failing closed."""
    target = path or default_contract_path()
    try:
        contract = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceError(
            f"Merge trailer contract {target} is missing or invalid; "
            "the lifecycle refuses to merge without it"
        ) from error
    return validate_contract(contract)


def validate_contract(contract: object) -> dict[str, Any]:  # noqa: C901
    """Require the exact contract shape this module knows how to apply."""
    if not isinstance(contract, dict):
        raise EvidenceError("Merge trailer contract is not an object")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise EvidenceError("Merge trailer contract schema is unsupported")
    keys = contract.get("keys")
    order = contract.get("order")
    if not isinstance(keys, dict) or not isinstance(order, list):
        raise EvidenceError("Merge trailer contract has no keys or order")
    if sorted(order) != sorted(keys) or len(order) != len(set(order)):
        raise EvidenceError("Merge trailer contract order is inconsistent")
    for name, rule in keys.items():
        if (
            not isinstance(name, str)
            or TRAILER_LINE.fullmatch(f"{name}: x") is None
        ):
            raise EvidenceError(f"Merge trailer key {name!r} is invalid")
        if not isinstance(rule, dict) or not isinstance(
            rule.get("required"), bool
        ):
            raise EvidenceError(f"Merge trailer rule {name} is invalid")
        kind = rule.get("value")
        if kind == "enum":
            values = rule.get("values")
            if not isinstance(values, list) or not values:
                raise EvidenceError(f"Merge trailer {name} has no values")
        elif kind not in {"digest", "sha", "url"}:
            raise EvidenceError(f"Merge trailer {name} has an unknown value")
    return contract


def _value_valid(rule: Mapping[str, Any], value: str) -> bool:
    kind = rule["value"]
    if kind == "enum":
        return value in rule["values"]
    pattern = {"digest": DIGEST, "sha": SHA, "url": GITHUB_URL}[kind]
    return pattern.fullmatch(value) is not None


def trailer_errors(
    contract: Mapping[str, Any], pairs: list[tuple[str, str]]
) -> list[str]:
    """Return every contract violation in one ordered trailer list."""
    keys: Mapping[str, Any] = contract["keys"]
    errors: list[str] = []
    seen: dict[str, int] = {}
    for name, value in pairs:
        rule = keys.get(name)
        if rule is None:
            errors.append(f"unknown key {name}")
            continue
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1 and not rule.get("repeatable", False):
            errors.append(f"repeated key {name}")
        if not _value_valid(rule, value):
            errors.append(f"value of {name} is outside its domain")
    errors.extend(
        f"missing key {name}"
        for name, rule in keys.items()
        if rule["required"] and name not in seen
    )
    return errors


def build_trailers(
    contract: Mapping[str, Any], values: Mapping[str, str | list[str]]
) -> list[tuple[str, str]]:
    """Return contract-ordered trailers, refusing any invalid value."""
    pairs: list[tuple[str, str]] = []
    for name in contract["order"]:
        value = values.get(name)
        if value is None:
            continue
        for item in value if isinstance(value, list) else [value]:
            pairs.append((name, item))
    unknown = sorted(set(values) - set(contract["keys"]))
    errors = [f"unknown key {name}" for name in unknown]
    errors.extend(trailer_errors(contract, pairs))
    if errors:
        raise EvidenceError("Merge trailers are invalid: " + "; ".join(errors))
    return pairs


def breaking_footers(messages: Iterable[str]) -> list[str]:
    """Collect each `BREAKING CHANGE:` footer line from the PR commits."""
    footers: list[str] = []
    for message in messages:
        for line in message.splitlines():
            stripped = line.strip()
            if BREAKING_FOOTER.match(stripped) and stripped not in footers:
                footers.append(stripped)
    return footers


def squash_message(footers: list[str], trailers: list[tuple[str, str]]) -> str:
    """Build the squash body: kept footers, a blank line, then trailers.

    Keeping the trailers in their own final paragraph leaves the text that
    `release_policy.py` reads after a BREAKING CHANGE footer unchanged.
    """
    paragraphs = []
    if footers:
        paragraphs.append("\n".join(footers))
    paragraphs.append("\n".join(f"{name}: {value}" for name, value in trailers))
    return "\n\n".join(paragraphs)


def parse_trailers(message: str) -> list[tuple[str, str]]:
    """Return every `CSARC-*` trailer line in one commit message."""
    pairs: list[tuple[str, str]] = []
    for line in message.splitlines():
        match = TRAILER_LINE.fullmatch(line.strip())
        if match is not None:
            pairs.append((match.group(1), match.group(2)))
    return pairs


def trailer_map(pairs: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Group trailer values by key, keeping their order."""
    result: dict[str, list[str]] = {}
    for name, value in pairs:
        result.setdefault(name, []).append(value)
    return result


def record_findings(trailers: Mapping[str, list[str]], record_body: str) -> str:
    """Compare one durable summary with the trailers that cite it."""
    try:
        summary = parse_summary(record_body)
        payload = parse_canonical(summary.data)
        payload_schema(payload)
    except EvidenceError:
        return "evidence-digest-mismatch"
    record = summary.record
    digest = trailers["CSARC-Evidence-SHA256"][0]
    trust = trailers["CSARC-Trust"][0]
    if (
        payload_digest(summary.data) != digest
        or record.get("digest") != digest
        or record.get("envelope_version") != ENVELOPE_VERSION
        or record.get("trust") != trust
        or payload.get("trust") != trust
        or record.get("route") != trailers["CSARC-Route"][0]
        or payload.get("tree_sha") != trailers["CSARC-Evidence-Tree"][0]
    ):
        return "evidence-digest-mismatch"
    return "traced"


def classify_merge(
    tree_sha: str,
    message: str,
    contract: Mapping[str, Any],
    read_record: Callable[[str], str | None],
) -> tuple[str, str]:
    """Classify one first-parent merge for the post-merge audit.

    `read_record` returns the record body, None when the record no longer
    exists, or raises `RecordUnavailableError` when GitHub cannot be read.
    """
    pairs = parse_trailers(message)
    if not pairs:
        return "untraced", "no CSARC-* trailer"
    errors = trailer_errors(contract, pairs)
    if errors:
        return "trailer-invalid", "; ".join(errors)
    trailers = trailer_map(pairs)
    if trailers["CSARC-Evidence-Tree"][0] != tree_sha:
        return "tree-mismatch", "commit tree differs from CSARC-Evidence-Tree"
    locator = trailers["CSARC-Evidence"][0]
    if COMMENT_LOCATOR.fullmatch(locator) is None:
        return "trailer-invalid", "CSARC-Evidence is not a PR comment URL"
    try:
        body = read_record(locator)
    except RecordUnavailableError as error:
        return "inconclusive", str(error)
    if body is None:
        return "evidence-missing", f"record {locator} is unavailable"
    finding = record_findings(trailers, body)
    if finding != "traced":
        return finding, f"record {locator} does not match the trailers"
    return "traced", locator


def trusted_provenance(
    provenance: object,
    commit: object,
    repository: str,
    repository_id: int,
) -> str:
    """Return why saved provenance is untrusted, or "" when it is trusted."""
    if not isinstance(commit, str) or SHA.fullmatch(commit) is None:
        return "_commit is not a full SHA"
    if not isinstance(provenance, dict):
        return "no .csarc/provenance.json"
    if provenance.get("verification") != "verified":
        return f"provenance verification is {provenance.get('verification')!r}"
    tag = provenance.get("release_tag")
    if (
        provenance.get("schema_version") != 1
        or provenance.get("repository") != repository
        or provenance.get("repository_id") != repository_id
        or not isinstance(tag, str)
        or not tag
    ):
        return "provenance fields are not trusted"
    if provenance.get("commit_sha") != commit:
        return "updated-outside-csarc: provenance commit differs from _commit"
    return ""


def commit_state(
    *,
    has_contract: bool,
    canonical_source: bool,
    provenance: object,
    commit: object,
    repository: str = CANONICAL_REPOSITORY,
    repository_id: int = CANONICAL_REPOSITORY_ID,
) -> tuple[str, str]:
    """Apply the ordered governance-baseline rules to one commit."""
    if not has_contract:
        return "absent", "no merge trailer contract in the tree"
    if canonical_source:
        return "contains", "template source repository"
    reason = trusted_provenance(provenance, commit, repository, repository_id)
    if not reason:
        return "contains", "trusted installation provenance"
    return "unresolved", reason


def derive_baseline(
    start_state: str, commits: list[tuple[str, str, str]]
) -> dict[str, object]:
    """Derive the baseline over one first-parent range.

    `commits` lists `(sha, state, reason)` oldest first, excluding the
    start. Only commits that change the contract, answers, or provenance can
    change the state, so callers may pass just those commits.
    """
    if start_state == "contains":
        return {
            "result": "resolved",
            "baseline": None,
            "reason": "the range starts after the baseline",
            "unresolved": [],
            "candidates": [],
        }
    unresolved: list[dict[str, str]] = []
    for sha, state, reason in commits:
        if state == "unresolved":
            unresolved.append({"sha": sha, "reason": reason})
        if state != "contains":
            continue
        if unresolved:
            return {
                "result": "inconclusive",
                "baseline": None,
                "reason": "unresolved commits precede the first trusted one",
                "unresolved": unresolved,
                "candidates": [item["sha"] for item in unresolved] + [sha],
            }
        return {
            "result": "resolved",
            "baseline": sha,
            "reason": reason,
            "unresolved": [],
            "candidates": [],
        }
    if unresolved:
        return {
            "result": "inconclusive",
            "baseline": None,
            "reason": "no commit proves an installed trailer writer",
            "unresolved": unresolved,
            "candidates": [item["sha"] for item in unresolved],
        }
    return {
        "result": "not-installed",
        "baseline": None,
        "reason": "no commit contains the merge trailer writer",
        "unresolved": [],
        "candidates": [],
    }


def confirm_baseline(
    derived: Mapping[str, object], sha: str
) -> dict[str, object]:
    """Accept an explicit confirmation only for a listed candidate."""
    candidates = derived.get("candidates")
    if derived.get("result") != "inconclusive" or not isinstance(
        candidates, list
    ):
        raise EvidenceError("Only an inconclusive baseline can be confirmed")
    if sha not in candidates:
        raise EvidenceError(
            f"{sha} is not a candidate governance baseline; choose one of "
            + ", ".join(str(item) for item in candidates)
        )
    return {
        **derived,
        "result": "confirmed",
        "baseline": sha,
        "reason": "explicitly confirmed candidate",
    }


@dataclass(frozen=True)
class Identity:
    """The repository identity GitHub reports, when it can be read."""

    full_name: str
    repository_id: int


GitRunner = Callable[[list[str]], tuple[int, str]]
ApiReader = Callable[[str], tuple[int, str]]
CANONICAL_IDENTITY = Identity(CANONICAL_REPOSITORY, CANONICAL_REPOSITORY_ID)


class AuditContext:
    """Read one repository's history and its GitHub records."""

    def __init__(
        self,
        git: GitRunner,
        api: ApiReader,
        identity: Callable[[], Identity | None],
    ) -> None:
        """Bind the Git and GitHub readers used by one audit."""
        self.git = git
        self.api = api
        self._identity = identity
        self._identity_loaded = False
        self._identity_value: Identity | None = None

    def identity(self) -> Identity | None:
        """Return the repository identity, read once and only when needed."""
        if not self._identity_loaded:
            self._identity_value = self._identity()
            self._identity_loaded = True
        return self._identity_value

    def output(self, *args: str) -> str | None:
        """Return Git output, or None when the command fails."""
        code, text = self.git(list(args))
        return text if code == 0 else None

    def show(self, sha: str, path: str) -> str | None:
        """Return one file at one commit, or None when it does not exist."""
        return self.output("show", f"{sha}:{path}")


def _answers_commit(context: AuditContext, sha: str) -> object:
    for path in ANSWERS_PATHS:
        text = context.show(sha, path)
        if text is not None:
            match = ANSWER_COMMIT.search(text)
            return match.group(1).lower() if match else None
    return None


def history_state(context: AuditContext, sha: str) -> tuple[str, str]:
    """Apply the baseline rules to the tree of one commit in history."""
    has_contract = any(
        context.show(sha, path) is not None for path in CONTRACT_TREE_PATHS
    )
    commit = _answers_commit(context, sha)
    canonical_source = False
    if has_contract and commit is None:
        identity = context.identity()
        if identity is None:
            return "unresolved", "repository identity is unavailable"
        canonical_source = identity == CANONICAL_IDENTITY
    raw = context.show(sha, PROVENANCE_PATH)
    provenance: object = None
    if raw is not None:
        try:
            provenance = json.loads(raw)
        except json.JSONDecodeError:
            provenance = "invalid"
    return commit_state(
        has_contract=has_contract,
        canonical_source=canonical_source,
        provenance=provenance,
        commit=commit,
    )


def governance_baseline(
    context: AuditContext, ref: str, confirm: str | None = None
) -> dict[str, object]:
    """Derive, and optionally confirm, the baseline over all of `ref`."""
    listed = context.output(
        "log",
        "--first-parent",
        "--reverse",
        "--format=%H",
        ref,
        "--",
        *WATCHED_PATHS,
    )
    if listed is None:
        derived: dict[str, object] = {
            "result": "not-installed",
            "baseline": None,
            "reason": "the default branch history is unavailable",
            "unresolved": [],
            "candidates": [],
        }
    else:
        commits = [
            (sha, *history_state(context, sha)) for sha in listed.split() if sha
        ]
        derived = derive_baseline("absent", commits)
    if confirm:
        return confirm_baseline(derived, confirm.lower())
    return derived


def read_record(context: AuditContext, locator: str) -> str | None:
    """Read one durable PR-comment record through the GitHub API."""
    match = COMMENT_LOCATOR.fullmatch(locator)
    if match is None:
        return None
    code, text = context.api(
        f"repos/{match.group('repo')}/issues/comments/{match.group('comment')}"
    )
    if code != 0:
        if NOT_FOUND.search(text):
            return None
        raise RecordUnavailableError(f"GitHub could not read {locator}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise RecordUnavailableError(
            f"GitHub returned invalid JSON for {locator}"
        ) from error
    body = payload.get("body") if isinstance(payload, dict) else None
    return body if isinstance(body, str) else None


def _contract_at(
    context: AuditContext, *revisions: str
) -> dict[str, Any] | None:
    for revision in revisions:
        for path in CONTRACT_TREE_PATHS:
            text = context.show(revision, path)
            if text is None:
                continue
            try:
                return validate_contract(json.loads(text))
            except CONTRACT_READ_ERRORS:
                return None
    return None


def merge_audit(
    context: AuditContext,
    ref: str,
    baseline: Mapping[str, object],
    *,
    strict: bool = False,
) -> dict[str, object]:
    """Classify each first-parent merge after a resolved baseline.

    `strict` (the release path) also blocks on an untraced merge.
    """
    start = baseline.get("baseline")
    if baseline.get("result") not in {"resolved", "confirmed"} or not start:
        return {"merges": [], "blocking": [], "untraced": []}
    listed = context.output(
        "rev-list", "--first-parent", "--reverse", f"{start}..{ref}"
    )
    contract = _contract_at(context, ref, str(start))
    blocking_findings = (
        BLOCKING_FINDINGS | {"untraced"} if strict else BLOCKING_FINDINGS
    )
    merges: list[dict[str, str]] = []
    for sha in (listed or "").split():
        tree = (context.output("rev-parse", f"{sha}^{{tree}}") or "").strip()
        message = context.output("log", "-1", "--format=%B", sha) or ""
        if contract is None:
            finding, detail = "trailer-invalid", "no merge trailer contract"
        else:
            finding, detail = classify_merge(
                tree,
                message,
                contract,
                lambda locator: read_record(context, locator),
            )
        merges.append({"sha": sha, "finding": finding, "detail": detail})
    return {
        "merges": merges,
        "blocking": [
            item for item in merges if item["finding"] in blocking_findings
        ],
        "untraced": [
            item["sha"] for item in merges if item["finding"] == "untraced"
        ],
    }


def audit(
    context: AuditContext,
    ref: str,
    confirm: str | None = None,
    *,
    strict: bool = False,
) -> dict[str, object]:
    """Return the baseline, the merge findings, and whether either blocks."""
    baseline = governance_baseline(context, ref, confirm)
    merges = merge_audit(context, ref, baseline, strict=strict)
    # An inconclusive baseline audits no merge, so it is a missing proof
    # rather than a bad merge: a notice in `csarc status`, and blocking only
    # on the strict release path.
    blocking = (strict and baseline["result"] == "inconclusive") or bool(
        merges["blocking"]
    )
    return {"baseline": baseline, "merges": merges, "blocking": blocking}


def _subprocess_reader(command: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(  # noqa: S603
            command, check=False, capture_output=True, text=True
        )
    except OSError as error:
        return 1, str(error)
    if result.returncode:
        return result.returncode, result.stderr.strip()
    return 0, result.stdout


def local_context(root: Path) -> AuditContext:
    """Build an audit context over one local checkout and `gh api`."""

    def git(arguments: list[str]) -> tuple[int, str]:
        return _subprocess_reader(["git", "-C", str(root), *arguments])

    def api(endpoint: str) -> tuple[int, str]:
        return _subprocess_reader(["gh", "api", "--method", "GET", endpoint])

    def identity() -> Identity | None:
        code, remote = git(["remote", "get-url", "origin"])
        match = re.search(
            r"github\.com[:/]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?$",
            remote.strip(),
        )
        if code or match is None:
            return None
        code, text = api(f"repos/{match.group(1)}")
        try:
            payload = json.loads(text) if code == 0 else None
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        name, number = payload.get("full_name"), payload.get("id")
        if not isinstance(name, str) or type(number) is not int:
            return None
        return Identity(name, number)

    return AuditContext(git, api, identity)


def main(arguments: list[str] | None = None) -> int:
    """Audit default-branch merges; exit 1 when a finding blocks."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    audit_parser = commands.add_parser("audit")
    audit_parser.add_argument("--root", type=Path, default=Path.cwd())
    audit_parser.add_argument("--ref", default="HEAD")
    audit_parser.add_argument("--confirm-baseline", metavar="FULL_SHA")
    audit_parser.add_argument(
        "--strict",
        action="store_true",
        help="release path: an untraced merge after the baseline blocks",
    )
    args = parser.parse_args(arguments)
    try:
        result = audit(
            local_context(args.root),
            args.ref,
            args.confirm_baseline,
            strict=args.strict,
        )
    except EvidenceError as error:
        sys.stderr.write(f"merge_trace: {error}\n")
        return 2
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 1 if result["blocking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
