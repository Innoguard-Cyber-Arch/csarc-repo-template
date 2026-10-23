#!/usr/bin/env python3
"""Guard the one tree-bound CSARC Release writer (Issue #1074).

`publish-release` is the only writer of CSARC tags, draft Releases, assets,
and published immutable Releases, whether a hosted workflow or a maintainer
runs it locally. Before any write it asks this module two questions:

`preflight` decides whether this checkout may write at all. The checkout
must be the exact candidate commit with an unmodified tracked tree; the
saved `release_ownership` decides the mode (`csarc-owned` writes and fails
closed on any blocking merge-trace finding after the governance baseline,
`product-owned` only reports drift, `verification-only` has no CSARC Release
to block); no other workflow may write Releases; and the remote tag and
Release must either be absent or belong to this exact candidate. An existing
tag on another commit, a Release without the tag, or a published mutable
Release stops the writer: an immutable tag is never moved or reused.

`lease` serializes writers across hosted runs and local fallbacks through
one remote branch ref per tag. Acquisition creates the ref atomically; a
renewal or an expired-lease reclaim is a fast-forward-only update, so two
writers can never both believe they hold it.

Shared verbatim between `scripts/` and `template/.csarc/scripts/`. Sibling
modules load lazily from this file's own directory, and this module must
parse under the Python 3.12 grammar because hosted workflows may run it
before Python 3.14 is set up.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

NOT_WRITER_EXIT = 3
CSARC_OWNED = "csarc-owned"
# The one workflow allowed to call the writer; any other Release writer is a
# second writer the publisher refuses to race (#1063, #1068).
WRITER_WORKFLOW = "release.yml"
# The markers are assembled so the repository's own writer scanners
# (tests/test_release_notes_format.py, pr_lifecycle.py scan-writers) do not
# read this detection list as a Release writer; chr(64) is "@".
RELEASE_WRITER_MARKERS = (
    *(f"gh release {verb}" for verb in ("create", "edit", "upload")),
    "scripts/publish-release publish",
    "googleapis/release-please-action" + chr(64),
    "ncipollo/release-action@",
    "softprops/action-gh-release@",
)
TAG = re.compile(
    r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-beta\.[1-9][0-9]*)?"
)
SHA = re.compile(r"[0-9a-f]{40}")
NOT_FOUND = re.compile(r"(HTTP 404|[Nn]ot [Ff]ound)")
LEASE_SCHEMA = 1
LEASE_TITLE = "csarc release lease"
LEASE_FIELDS = (
    "acquired_at",
    "expires_at",
    "holder",
    "repository",
    "schema_version",
    "sha",
    "tag",
    "tree",
)
DEFAULT_TTL_SECONDS = 3600
MAX_TTL_SECONDS = 4 * 3600


class WriterError(RuntimeError):
    """The writer must stop before (or instead of) any Release write."""


def _sibling(name: str) -> ModuleType:
    """Load one script module that sits beside this file."""
    path = Path(__file__).resolve().with_name(f"{name}.py")
    cached = sys.modules.get(name)
    cached_file = getattr(cached, "__file__", None)
    if (
        cached is not None
        and cached_file
        and Path(cached_file).resolve() == path
    ):
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"Missing sibling module: {path}. Reinstall.")
    module = importlib.util.module_from_spec(spec)
    if cached is None:
        sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(name) is module:
            del sys.modules[name]
        raise
    return module


Runner = Callable[[list[str], "str | None"], "tuple[int, str, str]"]


def _run(command: list[str], stdin: str | None = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(  # noqa: S603
            command,
            check=False,
            capture_output=True,
            text=True,
            input=stdin,
        )
    except OSError as error:
        return 1, "", str(error)
    return result.returncode, result.stdout, result.stderr


@dataclass
class GitHub:
    """A thin `gh` client so tests can replace the transport."""

    repo: str
    run: Runner = _run

    def api(
        self, method: str, path: str, body: dict[str, object] | None = None
    ) -> tuple[int, str, str]:
        """Call one REST endpoint, sending `body` as JSON on stdin."""
        command = ["gh", "api", "--method", method, f"repos/{self.repo}/{path}"]
        payload = None
        if body is not None:
            command += ["--input", "-"]
            payload = json.dumps(body, sort_keys=True)
        return self.run(command, payload)

    def json(
        self, method: str, path: str, body: dict[str, object] | None = None
    ) -> object:
        """Call one endpoint and decode its JSON, failing closed."""
        code, out, err = self.api(method, path, body)
        if code != 0:
            raise WriterError(f"{method} {path} failed: {err.strip()}. Retry.")
        try:
            return json.loads(out)
        except json.JSONDecodeError as error:
            raise WriterError(
                f"{method} {path} failed: invalid JSON. Retry."
            ) from error


def git(root: Path, *arguments: str) -> str:
    """Return Git output, failing closed."""
    code, out, err = _run(["git", "-C", str(root), *arguments])
    if code != 0:
        raise WriterError(f"git {' '.join(arguments)}: {err.strip()}. Fix it.")
    return out.strip()


def checkout_errors(root: Path, sha: str) -> list[str]:
    """Require the checkout to be the exact candidate with a clean tree."""
    errors: list[str] = []
    head = git(root, "rev-parse", "HEAD")
    if head != sha:
        errors.append(f"checked-out commit {head} is not the candidate {sha}")
    dirty = git(root, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        errors.append("tracked files differ from the candidate tree")
    return errors


def release_ownership(root: Path) -> str:
    """Return the saved release owner; a missing owner fails closed."""
    config = _sibling("csarc_config")
    path = root / config.CONFIG_FILE
    try:
        loaded = config.load_config(path)
        return str(config.resolve_release_ownership(loaded, path))
    except (OSError, ValueError) as error:
        raise WriterError(str(error)) from error


def writer_workflow_errors(root: Path) -> list[str]:
    """Reject every workflow besides release.yml that writes a Release."""
    directory = root / ".github" / "workflows"
    if not directory.is_dir():
        return []
    errors = []
    for path in sorted((*directory.glob("*.yml"), *directory.glob("*.yaml"))):
        if path.name == WRITER_WORKFLOW or not path.is_file():
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        if any(marker in source for marker in RELEASE_WRITER_MARKERS):
            errors.append(
                f".github/workflows/{path.name} also writes Releases; "
                "publish-release must be the only Release writer"
            )
    return errors


def trace_decision(
    context: object, sha: str, ownership: str
) -> dict[str, object]:
    """Audit the merges after the governance baseline for one owner.

    A csarc-owned writer runs the strict release audit and blocks on any
    finding; a product-owned project only gets the drift report.
    """
    merge_trace = _sibling("merge_trace")
    strict = ownership == CSARC_OWNED
    try:
        result = merge_trace.audit(context, sha, strict=strict)
    except merge_trace.EvidenceError as error:
        raise WriterError(
            f"Merge audit: {str(error).rstrip('.')}. Fix it."
        ) from error
    merges = result["merges"]
    findings = [
        f"{item['sha']}: {item['finding']} ({item['detail']})"
        for item in merges["blocking"]
    ]
    if strict and result["baseline"]["result"] == "inconclusive":
        findings.append(
            "governance baseline is inconclusive: "
            + str(result["baseline"]["reason"])
        )
    return {
        "baseline": result["baseline"],
        "blocking": bool(result["blocking"]) and strict,
        "findings": findings,
        "untraced": merges["untraced"],
    }


def remote_tag(github: GitHub, tag: str) -> str | None:
    """Return the commit the remote tag ref names, or None when absent."""
    code, out, err = github.api("GET", f"git/ref/tags/{tag}")
    if code != 0:
        if NOT_FOUND.search(err):
            return None
        raise WriterError(f"Cannot read tag {tag}: {err.strip()}. Retry.")
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        payload = None
    sha = (
        (payload.get("object") or {}).get("sha")
        if isinstance(payload, dict)
        else None
    )
    if not isinstance(sha, str) or SHA.fullmatch(sha) is None:
        raise WriterError(f"Bad GitHub reply: invalid tag {tag}. Retry.")
    return sha


def remote_release(github: GitHub, tag: str) -> dict[str, Any] | None:
    """Return the Release for one tag (drafts included), or None."""
    code, out, err = github.run(
        [
            "gh",
            "release",
            "view",
            tag,
            "--repo",
            github.repo,
            "--json",
            "isDraft,isImmutable,tagName",
        ],
        None,
    )
    if code != 0:
        if NOT_FOUND.search(err):
            return None
        raise WriterError(f"Cannot read Release {tag}: {err.strip()}. Retry.")
    try:
        payload = json.loads(out)
    except json.JSONDecodeError as error:
        raise WriterError(
            f"Bad GitHub reply: invalid Release {tag}. Retry."
        ) from error
    if not isinstance(payload, dict) or payload.get("tagName") != tag:
        raise WriterError(f"Bad GitHub reply: wrong Release for {tag}. Retry.")
    return payload


def release_state(github: GitHub, tag: str, sha: str) -> str:
    """Classify the remote tag and Release for this exact candidate.

    Returns `none`, `tagged`, `draft`, or `published`; raises on any state
    that belongs to something else, so a retry never moves or reuses it.
    """
    tagged = remote_tag(github, tag)
    if tagged is not None and tagged != sha:
        raise WriterError(
            f"Tag {tag} names {tagged}, not {sha}: it is never moved. Bump the "
            "version."
        )
    release = remote_release(github, tag)
    if release is None:
        return "none" if tagged is None else "tagged"
    if tagged is None:
        raise WriterError(
            f"Unknown Release {tag} has no tag: it is never reused. Inspect it."
        )
    if release.get("isDraft") is True:
        return "draft"
    if release.get("isImmutable") is True:
        return "published"
    raise WriterError(
        f"Release {tag} is published but mutable: never reused. Inspect it."
    )


def preflight(
    root: Path,
    github: GitHub,
    sha: str,
    tag: str,
    command: str,
    audit_context: object = None,
) -> dict[str, object]:
    """Decide whether this checkout may write the Release for `tag`."""
    if TAG.fullmatch(tag) is None:
        raise WriterError(f"Bad release tag {tag}: unsupported format. Fix it.")
    if SHA.fullmatch(sha) is None:
        raise WriterError(f"Bad candidate {sha}: not a full SHA. Fix it.")
    errors = checkout_errors(root, sha)
    if errors:
        raise WriterError("; ".join(errors))
    ownership = release_ownership(root)
    tree = git(root, "rev-parse", f"{sha}^{{tree}}")
    decision: dict[str, object] = {
        "command": command,
        "ownership": ownership,
        "sha": sha,
        "tag": tag,
        "tree": tree,
    }
    if ownership == "verification-only":
        return {
            **decision,
            "writer": "none",
            "reason": "verification-only has no CSARC Release to publish",
        }
    context = audit_context or _sibling("merge_trace").local_context(root)
    trace = trace_decision(context, sha, ownership)
    decision["trace"] = trace
    if ownership != CSARC_OWNED:
        return {
            **decision,
            "writer": "none",
            "reason": f"{ownership} owns Releases; CSARC reports drift",
        }
    errors = writer_workflow_errors(root)
    findings = trace["findings"]
    if isinstance(findings, list):
        errors.extend(str(item) for item in findings)
    if errors:
        raise WriterError("; ".join(errors))
    state = release_state(github, tag, sha)
    if command == "publish" and state in {"none", "tagged"}:
        raise WriterError(
            f"Release {tag} has no draft: nothing to publish. Run "
            "'publish-release stage' first."
        )
    return {**decision, "writer": "csarc", "release_state": state}


def lease_ref(tag: str) -> str:
    """Return the one collision-resistant lease branch for a tag."""
    digest = hashlib.sha256(tag.encode()).hexdigest()
    return f"heads/csarc/leases/release-{digest}"


def lease_holder(github: GitHub) -> str:
    """Name the writer: one hosted run, or one local maintainer."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        run_id = os.environ.get("GITHUB_RUN_ID", "")
        if not run_id.isdigit():
            raise WriterError("Lease holder unknown: no GITHUB_RUN_ID. Set it.")
        return f"actions:{run_id}"
    code, out, err = github.run(["gh", "api", "user", "--jq", ".login"], None)
    login = out.strip()
    if code != 0 or not re.fullmatch(r"[A-Za-z0-9-]+(\[bot\])?", login):
        raise WriterError(
            f"Unknown GitHub identity: {err.strip()}. Run 'gh auth login'."
        )
    return f"local:{login}"


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def lease_message(core: dict[str, object]) -> str:
    """Render the canonical lease commit message."""
    return f"{LEASE_TITLE}\n\n" + json.dumps(
        core, sort_keys=True, separators=(",", ":")
    )


def read_lease(github: GitHub, commit: str) -> dict[str, Any]:
    """Return the canonical core of one lease commit, failing closed."""
    payload = github.json("GET", f"git/commits/{commit}")
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, str) or "\n\n" not in message:
        raise WriterError(f"Lease {commit}: not a release lease. Check it.")
    try:
        core = json.loads(message.split("\n\n", 1)[1])
    except json.JSONDecodeError as error:
        raise WriterError(
            f"Lease {commit}: not a release lease. Check it."
        ) from error
    if (
        not isinstance(core, dict)
        or set(core) != set(LEASE_FIELDS)
        or core.get("schema_version") != LEASE_SCHEMA
        or message.rstrip("\n") != lease_message(core)
    ):
        raise WriterError(f"Lease {commit}: not a canonical lease. Check it.")
    return core


def _expired(core: dict[str, Any], now: datetime) -> bool:
    try:
        expires = datetime.strptime(
            str(core["expires_at"]), "%Y-%m-%dT%H:%M:%SZ"
        )
    except ValueError as error:
        raise WriterError("Bad lease expiry: not a time. Check it.") from error
    return expires.replace(tzinfo=UTC) <= now


def current_lease(github: GitHub, tag: str) -> str | None:
    """Return the lease commit the remote lease ref names, if any."""
    code, out, err = github.api("GET", f"git/ref/{lease_ref(tag)}")
    if code != 0:
        if NOT_FOUND.search(err):
            return None
        raise WriterError(
            f"Cannot read the release lease: {err.strip()}. Retry."
        )
    try:
        sha = json.loads(out)["object"]["sha"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise WriterError(
            "Bad GitHub reply: invalid lease ref. Retry."
        ) from error
    if not isinstance(sha, str) or SHA.fullmatch(sha) is None:
        raise WriterError("Bad GitHub reply: invalid lease ref. Retry.")
    return sha


def acquire_lease(
    github: GitHub,
    tag: str,
    sha: str,
    tree: str,
    *,
    holder: str,
    ttl: int = DEFAULT_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Hold the release lease for this candidate and return its commit."""
    if not 60 <= ttl <= MAX_TTL_SECONDS:
        raise WriterError("Bad --ttl: not between 60 s and 4 hours. Fix it.")
    moment = now or datetime.now(UTC)
    core: dict[str, object] = {
        "acquired_at": _timestamp(moment),
        "expires_at": _timestamp(moment + timedelta(seconds=ttl)),
        "holder": holder,
        "repository": github.repo,
        "schema_version": LEASE_SCHEMA,
        "sha": sha,
        "tag": tag,
        "tree": tree,
    }
    existing = current_lease(github, tag)
    parent = sha
    if existing is not None:
        held = read_lease(github, existing)
        same_writer = held["holder"] == holder and held["sha"] == sha
        if not same_writer and not _expired(held, moment):
            raise WriterError(
                f"Lease for {tag} is busy: held by {held['holder']} for "
                f"{held['sha']} until {held['expires_at']}. Retry later."
            )
        parent = existing
    created = github.json(
        "POST",
        "git/commits",
        {"message": lease_message(core), "tree": tree, "parents": [parent]},
    )
    commit = created.get("sha") if isinstance(created, dict) else None
    if not isinstance(commit, str) or SHA.fullmatch(commit) is None:
        raise WriterError("Bad GitHub reply: no release lease commit. Retry.")
    if existing is None:
        code, _out, err = github.api(
            "POST", "git/refs", {"ref": f"refs/{lease_ref(tag)}", "sha": commit}
        )
    else:
        # A fast-forward-only update is a compare-and-swap on `existing`.
        code, _out, err = github.api(
            "PATCH",
            f"git/refs/{lease_ref(tag)}",
            {"sha": commit, "force": False},
        )
    if code != 0:
        raise WriterError(
            f"Another writer took the lease for {tag}: {err.strip()}. Retry."
        )
    confirm_lease(github, tag, commit, now=moment)
    return commit


def confirm_lease(
    github: GitHub, tag: str, commit: str, *, now: datetime | None = None
) -> None:
    """Require that this writer still holds an unexpired lease."""
    if current_lease(github, tag) != commit:
        raise WriterError(f"Lost lease for {tag}: no longer held. Retry.")
    if _expired(read_lease(github, commit), now or datetime.now(UTC)):
        raise WriterError(f"Lost lease for {tag}: it expired. Retry.")


def release_lease(github: GitHub, tag: str, commit: str) -> bool:
    """Delete the lease ref only while it still names this lease."""
    if current_lease(github, tag) != commit:
        return False
    code, _out, err = github.api("DELETE", f"git/refs/{lease_ref(tag)}")
    if code != 0 and not NOT_FOUND.search(err):
        raise WriterError(f"Cannot release the lease: {err.strip()}. Retry.")
    return True


def main(arguments: list[str] | None = None) -> int:
    """Run one preflight or lease command."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("preflight")
    check.add_argument("--root", type=Path, required=True)
    check.add_argument("--repo", required=True)
    check.add_argument("--sha", required=True)
    check.add_argument("--tag", required=True)
    check.add_argument(
        "--for", dest="purpose", choices=("stage", "publish"), required=True
    )
    lease = commands.add_parser("lease")
    lease.add_argument("action", choices=("acquire", "confirm", "release"))
    lease.add_argument("--root", type=Path, required=True)
    lease.add_argument("--repo", required=True)
    lease.add_argument("--tag", required=True)
    lease.add_argument("--sha")
    lease.add_argument("--lease")
    lease.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
    args = parser.parse_args(arguments)
    github = GitHub(args.repo)
    try:
        if args.command == "preflight":
            decision = preflight(
                args.root, github, args.sha, args.tag, args.purpose
            )
            sys.stdout.write(json.dumps(decision, sort_keys=True) + "\n")
            return 0 if decision["writer"] == "csarc" else NOT_WRITER_EXIT
        if args.action == "acquire":
            if not args.sha:
                parser.error("lease acquire needs --sha")
            tree = git(args.root, "rev-parse", f"{args.sha}^{{tree}}")
            commit = acquire_lease(
                github,
                args.tag,
                args.sha,
                tree,
                holder=lease_holder(github),
                ttl=args.ttl,
            )
            sys.stdout.write(commit + "\n")
            return 0
        if not args.lease:
            parser.error(f"lease {args.action} needs --lease")
        if args.action == "confirm":
            confirm_lease(github, args.tag, args.lease)
            return 0
        if not release_lease(github, args.tag, args.lease):
            sys.stderr.write("WARNING: Lease gone: not released. Check it.\n")
        return 0
    except WriterError as error:
        sys.stderr.write(f"ERROR: {error}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
