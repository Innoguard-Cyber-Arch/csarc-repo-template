#!/usr/bin/env python3
"""Validate spec documents and synchronize approved specs to GitHub Issues."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

SPEC_ID = re.compile(r"^SPEC-[0-9]{3,}$")
PRIORITIES = {"P0", "P1", "P2", "P3"}
STATUSES = {"draft", "proposed", "approved"}
LOGGER = logging.getLogger(__name__)


class SpecError(ValueError):
    """Raised when a spec violates the repository contract."""


@dataclass(frozen=True)
class Spec:
    """One validated specification and its GitHub Issue metadata."""

    path: Path
    spec_id: str
    title: str
    owner: str
    priority: str
    estimate: str
    status: str
    body: str


def _parse_front_matter(
    path: Path, lines: list[str]
) -> tuple[dict[str, str], int]:
    if not lines or lines[0].strip() != "---":
        raise SpecError(f"{path}: front matter must start with ---")

    try:
        end = next(
            index
            for index, line in enumerate(lines[1:], 1)
            if line.strip() == "---"
        )
    except StopIteration as error:
        raise SpecError(f"{path}: front matter must end with ---") from error

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise SpecError(f"{path}: invalid front-matter line: {line}")
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")

    return metadata, end


def _validate_metadata(path: Path, metadata: dict[str, str]) -> None:
    required = {"id", "title", "owner", "priority", "estimate", "status"}
    missing = sorted(required - metadata.keys())
    if missing:
        raise SpecError(f"{path}: missing metadata: {', '.join(missing)}")
    if not SPEC_ID.fullmatch(metadata["id"]):
        raise SpecError(f"{path}: id must match SPEC-<number>")
    if metadata["priority"] not in PRIORITIES:
        raise SpecError(f"{path}: priority must be one of {sorted(PRIORITIES)}")
    if metadata["status"] not in STATUSES:
        raise SpecError(f"{path}: status must be one of {sorted(STATUSES)}")


def _validate_body(path: Path, body: str) -> None:
    if not body:
        raise SpecError(f"{path}: spec body is empty")
    required_sections = (
        "Problem",
        "Outcome",
        "Acceptance criteria",
        "Out of scope",
        "Verification",
    )
    missing_sections = [
        section
        for section in required_sections
        if not re.search(
            rf"^## {re.escape(section)}\s*$",
            body,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    ]
    if missing_sections:
        raise SpecError(f"{path}: add an '## {missing_sections[0]}' section")
    if "- [ ]" not in body:
        raise SpecError(
            f"{path}: add at least one unchecked acceptance criterion"
        )


def parse_spec_text(path: Path, text: str) -> Spec:
    """Parse and validate one specification string."""
    lines = text.splitlines()
    metadata, end = _parse_front_matter(path, lines)
    _validate_metadata(path, metadata)

    body = "\n".join(lines[end + 1 :]).strip()
    _validate_body(path, body)

    return Spec(
        path=path,
        spec_id=metadata["id"],
        title=metadata["title"],
        owner=metadata["owner"],
        priority=metadata["priority"],
        estimate=metadata["estimate"],
        status=metadata["status"],
        body=body,
    )


def parse_spec(path: Path) -> Spec:
    """Read and validate one specification file."""
    return parse_spec_text(path, path.read_text(encoding="utf-8"))


def build_issue_body(spec: Spec, source_url: str) -> str:
    """Build the managed body stored in the matching GitHub Issue."""
    return "\n".join(
        [
            f"<!-- csarc-spec-id: {spec.spec_id} -->",
            f"> Source: [{spec.path.as_posix()}]({source_url})  ",
            f"> Owner: {spec.owner}  ",
            f"> Priority: {spec.priority}  ",
            f"> Expected size: {spec.estimate}  ",
            f"> Spec status: {spec.status}",
            "",
            spec.body,
            "",
        ]
    )


def run_gh(arguments: list[str]) -> str:
    """Run GitHub CLI without invoking a shell."""
    gh_binary = shutil.which("gh")
    if gh_binary is None:
        raise RuntimeError(
            "GitHub CLI (gh) is required for Issue synchronization"
        )
    # The executable is resolved locally.
    # Arguments are passed without a shell.
    result = subprocess.run(  # noqa: S603
        [gh_binary, *arguments],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def find_issue(repo: str, spec_id: str) -> int | None:
    """Return the existing managed Issue number, if one exists."""
    result = run_gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--search",
            f'"[{spec_id}]" in:title',
            "--json",
            "number,title",
            "--limit",
            "100",
        ]
    )
    for item in json.loads(result or "[]"):
        if item["title"].startswith(f"[{spec_id}]"):
            return int(item["number"])
    return None


def sync_spec(spec: Spec, repo: str, source_ref: str, server_url: str) -> None:
    """Create or update the GitHub Issue that corresponds to one spec."""
    if spec.status == "draft":
        LOGGER.info("skip draft: %s", spec.path)
        return

    repo_root = Path.cwd().resolve()
    absolute_path = spec.path.resolve()
    if not absolute_path.is_relative_to(repo_root):
        raise SpecError(f"{spec.path}: spec must be inside the repository")
    relative_path = absolute_path.relative_to(repo_root)
    source_url = (
        f"{server_url}/{repo}/blob/{source_ref}/{relative_path.as_posix()}"
    )
    body = build_issue_body(spec, source_url)
    title = f"[{spec.spec_id}] {spec.title}"
    issue_number = find_issue(repo, spec.spec_id)

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False
    ) as handle:
        handle.write(body)
        body_path = Path(handle.name)
    try:
        if issue_number is None:
            output = run_gh(
                [
                    "issue",
                    "create",
                    "--repo",
                    repo,
                    "--title",
                    title,
                    "--body-file",
                    str(body_path),
                    "--label",
                    "spec",
                    "--label",
                    spec.priority,
                ]
            )
            LOGGER.info("created: %s", output)
        else:
            run_gh(
                [
                    "issue",
                    "edit",
                    str(issue_number),
                    "--repo",
                    repo,
                    "--title",
                    title,
                    "--body-file",
                    str(body_path),
                    "--add-label",
                    "spec",
                    "--add-label",
                    spec.priority,
                ]
            )
            LOGGER.info("updated: #%s", issue_number)
    finally:
        body_path.unlink(missing_ok=True)


def discover_specs(paths: list[str]) -> list[Path]:
    """Resolve explicit spec paths or discover all default spec files."""
    candidates = (
        [Path(item) for item in paths]
        if paths
        else sorted(Path("docs/specs").glob("*.md"))
    )
    return [path for path in candidates if path.is_file()]


def load_labels(path: Path) -> list[dict[str, str]]:
    """Load the repository label policy used by Issue synchronization."""
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SpecError(f"{path}: labels policy must be a list")

    labels: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise SpecError(f"{path}: every label must be an object")
        name = item.get("name")
        color = item.get("color")
        description = item.get("description")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(color, str)
            or not color
            or not isinstance(description, str)
            or not description
        ):
            raise SpecError(
                f"{path}: every label needs name, color, and description"
            )
        labels.append(
            {"name": name, "color": color, "description": description}
        )
    return labels


def main() -> int:
    """Validate specs or synchronize approved specs to GitHub Issues."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("paths", nargs="*")

    sync = subparsers.add_parser("sync")
    sync.add_argument("paths", nargs="*")
    sync.add_argument("--repo", required=True)
    sync.add_argument("--source-ref", required=True)
    sync.add_argument(
        "--server-url",
        default=os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
    )

    args = parser.parse_args()
    specs = [parse_spec(path) for path in discover_specs(args.paths)]
    if not specs:
        LOGGER.info("no spec files found")
        return 0

    if args.command == "validate":
        for spec in specs:
            LOGGER.info("valid: %s (%s)", spec.path, spec.status)
        return 0

    for label in load_labels(Path("policies/labels.json")):
        run_gh(
            [
                "label",
                "create",
                label["name"],
                "--repo",
                args.repo,
                "--color",
                label["color"],
                "--description",
                label["description"],
                "--force",
            ]
        )
    for spec in specs:
        sync_spec(spec, args.repo, args.source_ref, args.server_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
