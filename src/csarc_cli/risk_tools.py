"""Guided Issue creation, risk suggestions, register, and backfill (#1079).

These commands are CLI-only: none of them is a gate and none ships to a
generated project. They share the gate's parser (`risk_controls`) and never
write to GitHub except `issue create`, which runs `gh issue create` only after
the body passes the create stage. `risk suggest`, `risk register`, and
`risk backfill` are read-only.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from csarc_cli import risk_controls

Runner = Callable[[list[str]], str]
Prompt = Callable[[str], str]

REGISTER_FORMAT = "csarc-risk-register"
BACKFILL_FORMAT = "csarc-risk-backfill"
FORMAT_VERSION = "1.0.0"
TRACKER = re.compile(r"Milestone [0-9]+: ")
CLOSING = re.compile(
    r"(?<!\w)(?:Closes|Fixes|Resolves)[ \t]+#([1-9][0-9]*)(?!\w)"
)
EXEMPT_LABELS = frozenset({"promotion", "duplicate"})
BODY_FLAGS = ("--body", "-b", "--body-file", "-F")
# Suggestion vocabulary (SPEC-010): the gate accepts any lowercase-kebab
# category; these keywords only propose a starting point.
SUGGESTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "security",
        (
            "auth",
            "token",
            "secret",
            "credential",
            "permission",
            "bypass",
            "ruleset",
            "approval",
            "admin",
            "injection",
            "權限",
            "繞過",
            "核准",
        ),
    ),
    (
        "data",
        (
            "delete",
            "remove",
            "migration",
            "overwrite",
            "backup",
            "personal",
            "刪除",
            "覆寫",
            "遷移",
            "個資",
        ),
    ),
    (
        "availability",
        ("outage", "timeout", "quota", "stuck", "performance", "中斷", "逾時"),
    ),
    (
        "compliance",
        ("license", "copyright", "policy", "audit", "legal", "授權", "稽核"),
    ),
    (
        "supply-chain",
        (
            "dependency",
            "dependabot",
            "action pin",
            "lockfile",
            "sbom",
            "provenance",
            "release",
            "依賴",
            "發布",
        ),
    ),
    (
        "correctness",
        (
            "bug",
            "regression",
            "breaking",
            "compatibility",
            "parity",
            "回歸",
            "相容",
            "錯誤",
        ),
    ),
    (
        "operability",
        (
            "docs",
            "documentation",
            "cost",
            "minutes",
            "maintenance",
            "budget",
            "文件",
            "成本",
            "維護",
            "預算",
        ),
    ),
)
HEADER_LINES = (
    "| ID | 類別 | 等級 | 風險 | 控制 | 預計證據 | Owner |",
    "| --- | --- | --- | --- | --- | --- | --- |",
)


class RiskToolError(RuntimeError):
    """An expected risk-tool failure with an actionable message."""


def gh_runner(command: list[str]) -> str:
    """Run one `gh` command and return stdout, failing closed."""
    result = subprocess.run(  # noqa: S603
        ["gh", *command],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RiskToolError(f"gh {command[0]} failed: {detail}")
    return result.stdout


def suggest_categories(text: str, labels: set[str] | None = None) -> list[str]:
    """Return up to three suggested categories, most specific first."""
    folded = text.casefold()
    scores: list[tuple[int, int, str]] = []
    for order, (category, words) in enumerate(SUGGESTIONS):
        hits = sum(
            1
            for word in words
            if (
                re.search(rf"\b{re.escape(word)}\b", folded)
                if word.isascii()
                else word in folded
            )
        )
        hits += int(
            category == "operability" and "documentation" in (labels or set())
        )
        if hits:
            scores.append((-hits, order, category))
    chosen = [category for _, _, category in sorted(scores)[:3]]
    return chosen or ["correctness"]


def skeleton(categories: list[str], owner: str = "TODO") -> str:
    """Return a risk block whose free-text cells the author must write."""
    rows = [
        f"| R{index} | {category} | TODO | TODO | TODO | TODO | {owner} |"
        for index, category in enumerate(categories, start=1)
    ]
    return "\n".join((risk_controls.LABEL, "", *HEADER_LINES, *rows))


def create_problems(body: str) -> list[str]:
    """Return the create-stage problems of one Issue body."""
    out: list[str] = []
    risk_controls.parse_risks(body, out)
    risk_controls.parse_acs(body, out)
    return out


def append_block(body: str, block: str) -> str:
    """Append the block to 補充, keeping every original byte."""
    lines = risk_controls.lines_of(body)
    if any(line.rstrip() == "### 補充" for line in lines):
        return body.rstrip("\n") + "\n\n" + block + "\n"
    return body.rstrip("\n") + "\n\n### 補充\n\n" + block + "\n"


def split_body_argument(arguments: list[str]) -> tuple[int, str, bool]:
    """Return the index, kind, and stdin flag of the one body argument."""
    found: list[tuple[int, str, bool]] = []
    for index, argument in enumerate(arguments):
        flag, equals, value = argument.partition("=")
        if flag in BODY_FLAGS and equals:
            found.append((index, flag, value == "-"))
        elif argument in BODY_FLAGS and index + 1 < len(arguments):
            found.append((index, argument, arguments[index + 1] == "-"))
    if len(found) != 1:
        raise RiskToolError(
            "Pass exactly one --body or --body-file argument after `--`; "
            "the author writes every part of the Issue outside the block."
        )
    return found[0]


def option_values(arguments: list[str], *flags: str) -> list[str]:
    """Return every value of the given options in `gh` argument form."""
    values: list[str] = []
    for index, argument in enumerate(arguments):
        flag, equals, value = argument.partition("=")
        if flag in flags and equals:
            values.append(value)
        elif argument in flags and index + 1 < len(arguments):
            values.append(arguments[index + 1])
    return values


def interactive_block(
    text: str, labels: set[str], owner: str, ask: Prompt
) -> str:
    """Ask the author to confirm each suggested row; return the block."""
    rows: list[str] = []
    for category in suggest_categories(text, labels):
        answer = ask(
            f"Suggested category {category!r}: keep, edit, or drop? [k/e/d] "
        )
        if answer.strip().casefold().startswith("d"):
            continue
        if answer.strip().casefold().startswith("e"):
            category = ask("Category (lowercase-kebab): ").strip()
        values = [
            ask(f"{column} for {category}: ").strip()
            for column in ("等級 (low/medium/high)", "風險", "控制", "預計證據")
        ]
        row_owner = ask(f"Owner [{owner}]: ").strip() or owner
        rows.append(
            f"| R{len(rows) + 1} | {category} | "
            + " | ".join(values)
            + f" | {row_owner} |"
        )
    if not rows:
        raise RiskToolError(
            "Every suggestion was dropped; add at least one risk"
        )
    return "\n".join((risk_controls.LABEL, "", *HEADER_LINES, *rows))


def issue_create(
    arguments: list[str],
    body_out: Path | None = None,
    *,
    run: Runner = gh_runner,
    ask: Prompt = input,
    interactive: bool | None = None,
    stdin: TextIO | None = None,
) -> int:
    """Check, optionally complete, and create one governed Issue."""
    stream = stdin or sys.stdin
    titles = option_values(arguments, "--title", "-t")
    labels = {
        label.strip()
        for value in option_values(arguments, "--label", "-l")
        for label in value.split(",")
    }
    if (titles and TRACKER.match(titles[0])) or labels & EXEMPT_LABELS:
        run(["issue", "create", *arguments])
        return 0
    index, flag, from_stdin = split_body_argument(arguments)
    inline = "=" in arguments[index]
    value = (
        arguments[index].partition("=")[2] if inline else arguments[index + 1]
    )
    if from_stdin:
        body = stream.read()
    elif flag in {"--body-file", "-F"}:
        body = Path(value).read_text(encoding="utf-8")
    else:
        body = value
    problems = create_problems(body)
    can_ask = (
        interactive if interactive is not None else stream.isatty()
    ) and not from_stdin
    if problems and can_ask and problems[0].startswith("RK01"):
        assignees = option_values(arguments, "--assignee", "-a")
        owner = (
            f"@{assignees[0]}" if assignees and assignees[0] != "@me" else ""
        )
        block = interactive_block(
            " ".join(titles) + "\n" + body, labels, owner or "@", ask
        )
        candidate = append_block(body, block)
        sys.stdout.write(block + "\n")
        if ask("Add this block to 補充? [y/N] ").strip().casefold() != "y":
            raise RiskToolError("Issue creation cancelled; nothing was created")
        body, problems = candidate, create_problems(candidate)
    if problems:
        for line in problems:
            sys.stderr.write(f"requirement-trace: {line}\n")
        sys.stderr.write("Suggested block (replace every TODO):\n")
        text = " ".join(titles) + "\n" + body
        sys.stderr.write(skeleton(suggest_categories(text, labels)) + "\n")
        return 1
    rest = [
        item
        for position, item in enumerate(arguments)
        if position != index and (inline or position != index + 1)
    ]
    if body_out is not None:
        body_out.write_text(body, encoding="utf-8")
        wrapper = Path("scripts/gh-issue-create")
        entry = str(wrapper) if wrapper.is_file() else "gh issue create"
        command = [entry, *rest, "--body-file", str(body_out)]
        sys.stdout.write(" ".join(command) + "\n")
        return 0
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".md", delete=False
    ) as handle:
        handle.write(body)
    try:
        run(["issue", "create", *rest, "--body-file", handle.name])
    finally:
        Path(handle.name).unlink(missing_ok=True)
    return 0


def resolve_repository(repo: str, run: Runner) -> str:
    """Return the explicit repository or the current checkout's."""
    if repo:
        return repo
    return run(
        ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]
    ).strip()


def api_pages(run: Runner, endpoint: str) -> list[dict[str, Any]]:
    """Read every page of one REST collection through `gh api`."""
    pages = json.loads(run(["api", "--paginate", "--slurp", endpoint]) or "[]")
    return [item for page in pages for item in page if isinstance(item, dict)]


def exempt_reason(issue: dict[str, Any]) -> str | None:
    """Return why an Issue needs no block, if it is exempt."""
    labels = {str(label.get("name")) for label in issue.get("labels") or []}
    if TRACKER.match(str(issue.get("title") or "")):
        return "tracker"
    for label in sorted(labels & EXEMPT_LABELS):
        return label
    if issue.get("state_reason") in {"not_planned", "duplicate"}:
        return "not-planned"
    return None


def closing_evidence(pulls: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Map each closed Issue to its newest merged (else open) pull request."""
    result: dict[int, dict[str, Any]] = {}
    ordered = sorted(
        pulls, key=lambda pull: (bool(pull.get("merged_at")), pull["number"])
    )
    for pull in ordered:
        for number in CLOSING.findall(
            str(pull.get("body") or ""),
        ):
            result[int(number)] = pull
    return result


def path_exists(path: str, ref: str) -> bool | None:
    """Return whether a path exists at the local default-branch ref."""
    result = subprocess.run(  # noqa: S603
        ["git", "cat-file", "-e", f"{ref}:{path}"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def control_status(evidence: str, exists: Callable[[str], bool | None]) -> str:
    """Return the register status of one evidence value."""
    kind = risk_controls.evidence_kind(evidence)
    if kind == "accepted":
        return "accepted"
    if kind == "path":
        present = exists(evidence.partition("::")[0])
        return (
            "unchecked"
            if present is None
            else "evidenced"
            if present
            else "stale"
        )
    return "declared" if kind in {"manual", "check", "scope"} else "unknown"


def register(  # noqa: C901
    repo: str,
    *,
    milestone: int | None = None,
    state: str = "open",
    run: Runner = gh_runner,
    exists: Callable[[str], bool | None] | None = None,
) -> dict[str, Any]:
    """Compute the repository or Milestone risk register from Issues."""
    repo = resolve_repository(repo, run)
    query = f"state={state}&per_page=100"
    if milestone is not None:
        query += f"&milestone={milestone}"
    issues = [
        issue
        for issue in api_pages(run, f"repos/{repo}/issues?{query}")
        if issue.get("pull_request") is None
    ]
    pulls = closing_evidence(
        api_pages(run, f"repos/{repo}/pulls?state=all&per_page=100")
    )
    default = json.loads(run(["api", f"repos/{repo}"]) or "{}").get(
        "default_branch", "main"
    )
    check = exists or (lambda path: path_exists(path, f"origin/{default}"))
    rows: list[dict[str, Any]] = []
    no_material: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    index: dict[str, set[str]] = {}
    for issue in sorted(issues, key=lambda item: int(item["number"])):
        number = int(issue["number"])
        body = str(issue.get("body") or "")
        reason = exempt_reason(issue)
        problems: list[str] = []
        risks = risk_controls.parse_risks(body, problems)
        acs = risk_controls.parse_acs(body, problems)
        coverage = "exempt" if reason else "invalid" if problems else "valid"
        if not reason and problems and problems[0].startswith("RK01"):
            coverage = "missing"
        if coverage == "valid" and [r["ID"] for r in risks] == ["R0"]:
            coverage = "no-material-risk"
        pull = pulls.get(number)
        mapping: dict[str, str] = {}
        trace = "unmapped"
        if pull and coverage in {"valid", "no-material-risk"}:
            declared, digest, mapping = risk_controls.parse_evidence(
                str(pull.get("body") or ""), []
            )
            current = risk_controls.coverage_digest(acs, risks)
            trace = (
                "current"
                if declared == number and digest == current
                else "stale"
            )
        assignees = sorted(
            str(a.get("login")) for a in issue.get("assignees") or []
        )
        entry_risks = []
        for risk in risks:
            evidence = mapping.get(risk["ID"], "")
            status = control_status(evidence, check) if evidence else "planned"
            entry_risks.append(
                {
                    "id": risk["ID"],
                    "category": risk["類別"],
                    "level": risk["等級"],
                    "owner": risk["Owner"],
                    "evidence": evidence or None,
                    "status": status,
                }
            )
            if status == "accepted":
                accepted.append(
                    {
                        "issue": number,
                        "id": risk["ID"],
                        "level": risk["等級"],
                        "assignees": assignees,
                    }
                )
        for tid, evidence in mapping.items():
            if risk_controls.evidence_kind(evidence) == "path":
                index.setdefault(evidence, set()).add(f"#{number}/{tid}")
        if coverage == "no-material-risk":
            no_material.append(
                {
                    "issue": number,
                    "state": issue.get("state"),
                    "closed_by": pull["number"] if pull else None,
                }
            )
        rows.append(
            {
                "number": number,
                "title": issue.get("title"),
                "state": issue.get("state"),
                "milestone": (issue.get("milestone") or {}).get("number"),
                "assignees": assignees,
                "coverage": coverage,
                "exempt_reason": reason,
                "problems": [line.split()[0] for line in problems]
                if not reason
                else [],
                "acceptance": len(acs),
                "pull_request": pull["number"] if pull else None,
                "trace": trace,
                "risks": entry_risks,
            }
        )
    order = {"high": 0, "medium": 1, "low": 2}
    evidence_index = [
        {
            "evidence": key,
            "status": control_status(key, check),
            "refs": sorted(refs),
        }
        for key, refs in sorted(index.items())
    ]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["coverage"]] = counts.get(row["coverage"], 0) + 1
    return {
        "format": REGISTER_FORMAT,
        "format_version": FORMAT_VERSION,
        "repository": repo,
        "filter": {"milestone": milestone, "state": state},
        "summary": {
            "issues": len(rows),
            "coverage": dict(sorted(counts.items())),
        },
        "issues": rows,
        "no_material_risk": no_material,
        "accepted_risks": sorted(
            accepted,
            key=lambda item: (order.get(item["level"], 3), item["issue"]),
        ),
        "evidence_index": evidence_index,
        "stale": [
            {"issue": row["number"], "trace": row["trace"]}
            for row in rows
            if row["trace"] == "stale"
        ]
        + [
            {"evidence": item["evidence"], "refs": item["refs"]}
            for item in evidence_index
            if item["status"] == "stale"
        ],
    }


def render_register(data: dict[str, Any]) -> str:
    """Render the register Markdown from its JSON only."""
    lines = [f"# Risk register: {data['repository']}", "", "## Summary", ""]
    lines += [
        f"- {key}: {value}"
        for key, value in data["summary"]["coverage"].items()
    ]
    lines += ["", "## Coverage", ""]
    lines += [
        f"- #{row['number']} {row['coverage']} trace={row['trace']}"
        + (f" ({row['exempt_reason']})" if row["exempt_reason"] else "")
        for row in data["issues"]
    ] or ["None."]
    lines += ["", "## No material risk", ""]
    lines += [
        f"- #{item['issue']} {item['state']} closed_by={item['closed_by']}"
        for item in data["no_material_risk"]
    ] or ["None."]
    lines += ["", "## Accepted risks", ""]
    lines += [
        f"- #{item['issue']} {item['id']} {item['level']} "
        f"assignees={','.join(item['assignees'])}"
        for item in data["accepted_risks"]
    ] or ["None."]
    lines += ["", "## Evidence index", ""]
    lines += [
        f"- `{item['evidence']}` {item['status']}: {', '.join(item['refs'])}"
        for item in data["evidence_index"]
    ] or ["None."]
    lines += ["", "## Stale", ""]
    lines += [json.dumps(item, sort_keys=True) for item in data["stale"]] or [
        "None."
    ]
    return "\n".join(lines) + "\n"


def suggest(
    repo: str, *, issue: int | None, run: Runner = gh_runner
) -> list[dict[str, Any]]:
    """List create-stage problems and suggestions without writing anything."""
    repo = resolve_repository(repo, run)
    if issue is not None:
        candidates = [json.loads(run(["api", f"repos/{repo}/issues/{issue}"]))]
    else:
        candidates = api_pages(
            run, f"repos/{repo}/issues?state=open&per_page=100"
        )
    results = []
    for item in candidates:
        if item.get("pull_request") is not None:
            continue
        reason = exempt_reason(item)
        body = str(item.get("body") or "")
        problems = [] if reason else create_problems(body)
        if issue is None and (reason or not problems):
            continue
        labels = {str(label.get("name")) for label in item.get("labels") or []}
        results.append(
            {
                "issue": int(item["number"]),
                "exempt_reason": reason,
                "problems": problems,
                "suggestion": None
                if reason or not problems
                else skeleton(
                    suggest_categories(f"{item.get('title')}\n{body}", labels)
                ),
            }
        )
    return results


def canonical(data: object) -> bytes:
    """Serialize one manifest as canonical JSON bytes."""
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def backfill(
    repo: str, milestone: int, *, run: Runner = gh_runner
) -> dict[str, Any]:
    """Build the one-time manifest for merged pre-K1 Milestone work PRs."""
    repo = resolve_repository(repo, run)
    entries = []
    for pull in api_pages(run, f"repos/{repo}/pulls?state=closed&per_page=100"):
        body = str(pull.get("body") or "")
        if (
            not pull.get("merged_at")
            or (pull.get("milestone") or {}).get("number") != milestone
            or risk_controls.EVIDENCE in risk_controls.lines_of(body)
        ):
            continue
        numbers = sorted(
            {
                int(n)
                for n in CLOSING.findall(
                    body,
                )
            }
        )
        if len(numbers) != 1:
            continue
        issue = json.loads(run(["api", f"repos/{repo}/issues/{numbers[0]}"]))
        issue_body = str(issue.get("body") or "")
        problems: list[str] = []
        risks = risk_controls.parse_risks(issue_body, problems)
        acs = risk_controls.parse_acs(issue_body, problems)
        merge_sha = str(pull.get("merge_commit_sha") or "")
        entries.append(
            {
                "pull_request": int(pull["number"]),
                "issue": numbers[0],
                "merge_commit_sha": merge_sha,
                "head_sha": str((pull.get("head") or {}).get("sha") or ""),
                "issue_body_digest": risk_controls.digest(issue_body),
                "coverage_digest": risk_controls.coverage_digest(acs, risks),
                "acceptance": [f"AC{k}" for k in range(1, len(acs) + 1)],
                "risks": [risk["ID"] for risk in risks],
                "problems": [line.split()[0] for line in problems],
                "evidence": f"pre-K1 merge {merge_sha}",
            }
        )
    return {
        "format": BACKFILL_FORMAT,
        "format_version": FORMAT_VERSION,
        "repository": repo,
        "milestone": milestone,
        "entries": sorted(entries, key=lambda entry: entry["pull_request"]),
    }


def manifest_digest(manifest: dict[str, Any]) -> str:
    """Return the `sha256:` digest of one canonical manifest."""
    return "sha256:" + hashlib.sha256(canonical(manifest)).hexdigest()


def verify_backfill(
    path: Path, digest: str, *, live: bool = True, run: Runner = gh_runner
) -> list[str]:
    """Read a saved manifest back; return every mismatch."""
    data = path.read_bytes()
    manifest = json.loads(data)
    problems = []
    if canonical(manifest) != data:
        problems.append("manifest bytes are not canonical")
    if manifest_digest(manifest) != digest:
        problems.append("manifest digest does not match the saved digest")
    if live and not problems:
        fresh = backfill(manifest["repository"], manifest["milestone"], run=run)
        if fresh != manifest:
            problems.append("live readback differs from the saved manifest")
    return problems
