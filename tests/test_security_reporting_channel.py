"""Private vulnerability reporting channel contract (Issue #1084)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from copier import run_copy, run_recopy
from jinja2.sandbox import SandboxedEnvironment

ROOT = Path(__file__).resolve().parents[1]
ROOT_CONTACT = "justyn.jt.chen@tw.ey.com"
LEGACY_ISSUE_ROUTE = (
    "Open a GitHub Issue at https://github.com/example/fixture/issues/new; "
    "maintainers receive notifications for new Issues."
)
PUBLIC_REJECTION = "needs one maintainer-approved private reporting channel"
PLACEHOLDER_REJECTION = "without placeholder text"
GUARD_REJECTION = "A public repository needs security_reporting_channel"
# Copier validates the empty public default before rendering; the template
# guard is the second line of defense for any path that skips validation.
MISSING_REJECTION = (
    "(question 'security_reporting_channel'.*placeholder|"
    + GUARD_REJECTION
    + ")"
)


def _question() -> dict[str, str]:
    copier = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    return copier["security_reporting_channel"]


def _render(source: str, **context: object) -> str:
    environment = SandboxedEnvironment(
        extensions=["jinja2_ansible_filters.AnsibleCoreFiltersExtension"]
    )
    return environment.from_string(source).render(**context).strip()


def _validate(channel: str, visibility: str) -> str:
    return _render(
        _question()["validator"],
        security_reporting_channel=channel,
        project_visibility=visibility,
    )


@pytest.mark.parametrize(
    "channel",
    [
        "security@example.com",
        "mailto:security@example.com",
        "  security@sub.example.org  ",
        "https://security.example.com/report",
        "https://example.com/security?form=1#top",
        "https://github.com.example.net/report",
    ],
)
def test_public_accepts_private_email_or_https_entry(channel: str) -> None:
    """Accept the closed set of private entry formats outside GitHub."""
    assert _validate(channel, "public") == ""


@pytest.mark.parametrize(
    "channel",
    [
        LEGACY_ISSUE_ROUTE,
        "https://github.com/example/fixture/issues/new",
        "https://github.com/example/fixture/discussions",
        "https://GitHub.com/example/fixture/security/advisories/new",
        "https://gist.github.com/example/abc",
        "https://user@github.com/example/fixture/issues",
        "http://github.com/example/fixture/issues",
        "http://security.example.com/report",
        "Email security@example.com for help",
        "security at example dot com",
        "https://exa mple.com/report",
        "ftp://example.com/report",
        "security@localhost",
    ],
)
def test_public_rejects_github_routes_and_unparseable_values(
    channel: str,
) -> None:
    """Fail closed on public GitHub routes and untrusted formats."""
    assert PUBLIC_REJECTION in _validate(channel, "public")


@pytest.mark.parametrize("visibility", ["public", "private", "internal"])
@pytest.mark.parametrize("channel", ["", "   ", "TODO", "tbd", "<email>"])
def test_every_visibility_rejects_empty_and_placeholder_values(
    channel: str, visibility: str
) -> None:
    """Never accept a missing or placeholder channel for any visibility."""
    assert PLACEHOLDER_REJECTION in _validate(channel, visibility)


@pytest.mark.parametrize("visibility", ["private", "internal"])
@pytest.mark.parametrize(
    "channel",
    [LEGACY_ISSUE_ROUTE, "Contact the platform team privately."],
)
def test_non_public_keeps_issue_instructions(
    channel: str, visibility: str
) -> None:
    """Private and internal Issues are not world-readable."""
    assert _validate(channel, visibility) == ""


@pytest.mark.parametrize(
    ("visibility", "expected"),
    [
        ("public", ""),
        (
            "private",
            "Open a GitHub Issue at https://github.com/example/fixture/"
            "issues/new; maintainers receive notifications for new Issues.",
        ),
        (
            "internal",
            "Open a GitHub Issue at https://github.com/example/fixture/"
            "issues/new; maintainers receive notifications for new Issues.",
        ),
    ],
)
def test_default_never_invents_a_public_channel(
    visibility: str, expected: str
) -> None:
    """Leave the public default empty instead of inventing a contact."""
    assert (
        _render(
            _question()["default"],
            project_visibility=visibility,
            repository_url="https://github.com/example/fixture",
        )
        == expected
    )


def test_template_ships_no_maintainer_contact_or_test_value() -> None:
    """Keep this repository's contact and fixture values out of downstream."""
    shipped = [ROOT / "copier.yml"] + [
        path for path in (ROOT / "template").rglob("*") if path.is_file()
    ]
    for path in shipped:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert ROOT_CONTACT not in text, path
        assert "security@example.com" not in text, path


def test_root_policy_and_config_use_the_approved_private_channel() -> None:
    """Dogfood the public-repository rule on this template repository."""
    config = yaml.safe_load(
        (ROOT / ".csarc/config.yml").read_text(encoding="utf-8")
    )
    policy = (ROOT / ".github/SECURITY.md").read_text(encoding="utf-8")

    assert config["project_visibility"] == "public"
    assert config["security_reporting_channel"] == ROOT_CONTACT
    assert _validate(config["security_reporting_channel"], "public") == ""
    assert (
        "<!-- csarc-security-reporting-channel:start -->\n"
        f"{ROOT_CONTACT}\n"
        "<!-- csarc-security-reporting-channel:end -->"
    ) in policy
    assert "issues/new" not in policy
    assert "Do not open a GitHub Issue, Discussion" in policy


@pytest.mark.parametrize("channel", ["", "   "])
def test_policy_template_guard_rejects_empty_public_channel(
    channel: str,
) -> None:
    """Abort the render itself if an empty public channel reaches it."""
    template = (ROOT / "template/.github/SECURITY.md.jinja").read_text(
        encoding="utf-8"
    )
    with pytest.raises(Exception, match=GUARD_REJECTION):
        _render(
            template,
            security_reporting_channel=channel,
            project_visibility="public",
        )


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    return source


def _data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "languages": [],
        "project_name": "Security Fixture",
        "project_slug": "security-fixture",
        "project_description": "Exercises the security reporting contract.",
        "repository_url": "https://github.com/example/security-fixture",
        "documentation_mode": "off",
    }
    data.update(overrides)
    return data


def _copy(source: Path, project: Path, data: dict[str, object]) -> None:
    run_copy(
        str(source),
        project,
        data=data,
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        quiet=True,
    )


@pytest.mark.parametrize(
    "channel", ["security@example.com", "https://security.example.com/report"]
)
def test_public_render_publishes_only_the_private_channel(
    tmp_path: Path, channel: str
) -> None:
    """Render the approved entry and steer reporters away from Issues."""
    project = tmp_path / "project"
    _copy(
        _source(tmp_path),
        project,
        _data(project_visibility="public", security_reporting_channel=channel),
    )

    policy = (project / ".github/SECURITY.md").read_text(encoding="utf-8")
    assert f"start -->\n{channel}\n<!-- csarc" in policy
    assert "Do not open a GitHub Issue, Discussion, or pull" in policy
    assert "/issues/new" not in policy
    assert "private vulnerability reporting" not in policy.lower()
    assert ROOT_CONTACT not in policy


@pytest.mark.parametrize("project_mode", ["new", "existing"])
def test_public_render_without_channel_fails_closed(
    tmp_path: Path, project_mode: str
) -> None:
    """Fail before writing when no private channel was supplied.

    `existing` resolves release ownership to `verification-only`; the rule
    still follows visibility alone and never assumes a platform capability.
    """
    project = tmp_path / "project"
    with pytest.raises(Exception, match=MISSING_REJECTION):
        _copy(
            _source(tmp_path),
            project,
            _data(project_visibility="public", project_mode=project_mode),
        )
    assert not (project / ".github/SECURITY.md").exists()


@pytest.mark.parametrize(
    "channel", [LEGACY_ISSUE_ROUTE, "https://github.com/o/r/discussions"]
)
def test_public_render_rejects_supplied_github_route(
    tmp_path: Path, channel: str
) -> None:
    """Reject an explicit public GitHub route before rendering."""
    project = tmp_path / "project"
    with pytest.raises(ValueError, match=PUBLIC_REJECTION):
        _copy(
            _source(tmp_path),
            project,
            _data(
                project_visibility="public",
                security_reporting_channel=channel,
            ),
        )
    assert not (project / ".github/SECURITY.md").exists()


@pytest.mark.parametrize("visibility", ["private", "internal"])
def test_non_public_render_keeps_issue_default(
    tmp_path: Path, visibility: str
) -> None:
    """Private and internal projects keep the Issue instructions."""
    project = tmp_path / "project"
    _copy(_source(tmp_path), project, _data(project_visibility=visibility))

    policy = (project / ".github/SECURITY.md").read_text(encoding="utf-8")
    assert "https://github.com/example/security-fixture/issues/new" in policy
    assert f"Issues in this {visibility} repository" in policy


def test_legacy_public_issue_route_fails_closed_on_rerender(
    tmp_path: Path,
) -> None:
    """Migrate a stored Issue route only through an explicit private entry."""
    source = _source(tmp_path)
    project = tmp_path / "project"
    _copy(source, project, _data(project_visibility="private"))
    config = project / ".csarc/config.yml"
    answers = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert answers["security_reporting_channel"].startswith(
        "Open a GitHub Issue at"
    )
    # A legacy public consumer stored the old Issue-routing default.
    answers["project_visibility"] = "public"
    config.write_text(yaml.safe_dump(answers), encoding="utf-8")
    policy_path = project / ".github/SECURITY.md"
    before = policy_path.read_text(encoding="utf-8")

    with pytest.raises(Exception, match=MISSING_REJECTION):
        run_recopy(
            str(project),
            defaults=True,
            unsafe=True,
            skip_tasks=True,
            overwrite=True,
            answers_file=".csarc/config.yml",
            quiet=True,
        )
    assert policy_path.read_text(encoding="utf-8") == before

    run_recopy(
        str(project),
        data={"security_reporting_channel": "security@example.com"},
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        overwrite=True,
        answers_file=".csarc/config.yml",
        quiet=True,
    )
    migrated = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert migrated["security_reporting_channel"] == "security@example.com"
    assert "/issues/new" not in policy_path.read_text(encoding="utf-8")
