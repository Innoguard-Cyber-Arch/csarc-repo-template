"""Setup question transcripts, presets, and approval preflight (#1078).

Every case here drives the planner with a scripted TTY or a script's
``--data`` and stubbed GitHub reads; none renders Copier. The question
counts are the #1058 Targets table, asserted from the recorded transcript.
"""

from __future__ import annotations

import argparse
import json
import runpy
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

import csarc_cli.cli as cli
from csarc_cli import settings_schema, setup_plan
from csarc_cli.setup_plan import Session, SetupError

ROOT = Path(__file__).resolve().parents[1]


class Script:
    """A scripted TTY: answers in order, recording every prompt."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError(f"unexpected question: {prompt}")
        return self.answers.pop(0)


def tty(*answers: str) -> Session:
    return Session(interactive=True, ask=Script(*answers), emit=lambda _: None)


def script() -> Session:
    def refuse(prompt: str) -> str:
        raise AssertionError(f"a script was asked: {prompt}")

    return Session(interactive=False, ask=refuse, emit=lambda _: None)


INIT_ANSWERS = (
    "Inventory service for warehouse teams.",  # project_description
    "python",  # languages
    "",  # project_license -> proprietary
    "Example Holder",  # copyright_holder
    "",  # documentation_languages -> zh-tw
)


def init_transcript(
    *mode_answers: str,
) -> tuple[Session, setup_plan.SetupResult]:
    session = tty(*INIT_ANSWERS, *mode_answers)
    result = setup_plan.plan_init(session, {}, None)
    return session, result


# --- Question counts (#1058 Targets) ---------------------------------------


def test_init_solo_local_private_asks_six_questions() -> None:
    session, result = init_transcript("")

    assert session.asked == [
        "project_description",
        "languages",
        "project_license",
        "copyright_holder",
        "documentation_languages",
        "work_mode",
    ]
    assert result.work_mode == "solo-local"
    assert result.values["verification_mode"] == "local"
    assert result.values["admin_bypass"] == "always"
    assert result.values["lifecycle"] == []
    assert result.values["scheduled_checks"] == []
    assert result.values["documentation_languages"] == "zh-tw"
    assert result.values["documentation_mode"] == "content-only"
    assert result.sources["project_description"] == {
        "note": "asked",
        "source": "explicit",
    }
    # Prompt numbers follow the counted questions only.
    assert session.transcript[0].startswith("[1] One-sentence project purpose")
    assert session.transcript[-2].startswith("[6] Work mode")


@pytest.mark.parametrize(
    ("mode_answers", "extra"),
    [
        (("solo-hosted", ""), ["release_trigger"]),
        (("team", "", ""), ["copilot_review", "release_trigger"]),
        (
            ("custom", "local", "", ""),
            ["verification_mode", "admin_bypass", "copilot_review"],
        ),
        (
            ("custom", "hosted", "", "", "manual"),
            [
                "verification_mode",
                "admin_bypass",
                "copilot_review",
                "release_trigger",
            ],
        ),
    ],
)
def test_init_preset_follow_up_questions(
    mode_answers: tuple[str, ...], extra: list[str]
) -> None:
    session, result = init_transcript(*mode_answers)

    assert len(session.asked) == 6 + len(extra)
    assert session.asked[6:] == extra
    assert result.work_mode == mode_answers[0]


def test_custom_license_skips_the_copyright_question() -> None:
    """Targets: choosing the `custom` license asks one question fewer."""
    session = tty(
        "Inventory service for warehouse teams.",
        "python",
        "custom",
        "",
        "",
    )
    result = setup_plan.plan_init(session, {}, None)

    assert session.asked == [
        "project_description",
        "languages",
        "project_license",
        "documentation_languages",
        "work_mode",
    ]
    assert result.values["project_license"] == "custom"
    assert "copyright_holder" not in result.values
    scripted = script()
    setup_plan.plan_init(
        scripted,
        {
            "project_description": "Inventory service.",
            "languages": "python",
            "project_license": "custom",
        },
        None,
    )
    scripted.require_complete("init")


def test_public_and_unresolved_repository_add_their_questions() -> None:
    session, result = init_transcript("")
    session.ask = Script(
        "https://github.com/owner/product", "public", "security@example.com"
    )
    setup_plan.plan_repository(
        session, result, {}, resolved=False, visibility_known=False
    )
    setup_plan.plan_security_channel(
        session, result, {}, visibility="public", detected=None
    )

    assert session.asked[6:] == [
        "repository_url",
        "project_visibility",
        "security_reporting_channel",
    ]
    assert len(session.asked) == 9
    assert result.values["security_reporting_channel"] == "security@example.com"


def test_explicit_inputs_and_preset_ask_zero_questions() -> None:
    """AC3: seeds and required intent passed explicitly ask nothing."""
    explicit = {
        "project_description": "Inventory service.",
        "languages": "python",
        "project_license": "MIT",
        "copyright_holder": "Example Holder",
        "documentation_languages": "en",
    }
    session = tty()
    result = setup_plan.plan_init(session, explicit, "solo-local")
    setup_plan.plan_repository(
        session, result, explicit, resolved=True, visibility_known=True
    )
    setup_plan.plan_security_channel(
        session, result, explicit, visibility="private", detected=None
    )

    assert session.asked == []
    assert session.transcript == []
    assert result.values["verification_mode"] == "local"
    assert result.sources["verification_mode"] == {
        "note": "work mode solo-local",
        "source": "explicit",
    }


def adopt_detections(**overrides: object) -> list[setup_plan.Detection]:
    detections = {
        "languages": setup_plan.Detection(
            "languages", ["python"], "manifests: pyproject.toml"
        ),
        "project_description": setup_plan.Detection(
            "project_description", "Inventory service.", "pyproject.toml"
        ),
        "copyright_holder": setup_plan.Detection(
            "copyright_holder", "Example Holder", "LICENSE"
        ),
    }
    for key, value in overrides.items():
        if value is None:
            detections.pop(key)
        else:
            assert isinstance(value, setup_plan.Detection)
            detections[key] = value
    return list(detections.values())


def test_adopt_asks_three_questions_when_detection_is_certain() -> None:
    session = tty("", "", "")
    result = setup_plan.plan_adopt(
        session,
        {},
        None,
        adopt_detections(),
        release_ownership="product-owned",
        dockerfile=False,
    )

    assert session.asked == ["detected", "governance_mode", "work_mode"]
    assert result.values["governance_mode"] == "managed"
    assert result.sources["project_description"] == {
        "note": "detected: pyproject.toml",
        "source": "derived",
    }


def test_adopt_uncertain_detection_dockerfile_and_policy_add_questions() -> (
    None
):
    session = tty(
        "",  # detected values
        "Inventory service.",  # missing description
        "Example Holder",  # LICENSE the plan would create
        "beta",  # ambiguous package
        "observe",  # governance_mode
        "",  # work mode
        "yes",  # container (Dockerfile)
        "security@example.com",  # public, no disclosure policy
    )
    detections = adopt_detections(
        project_description=setup_plan.Detection(
            "project_description", None, "no manifest description", "unknown"
        ),
        copyright_holder=setup_plan.Detection(
            "copyright_holder", None, "no LICENSE", "unknown"
        ),
        package_name=setup_plan.Detection(
            "package_name",
            None,
            "native manifests",
            "ambiguous",
            ("alpha", "beta"),
        ),
    )
    result = setup_plan.plan_adopt(
        session,
        {},
        None,
        detections,
        release_ownership="product-owned",
        dockerfile=True,
    )
    setup_plan.plan_security_channel(
        session, result, {}, visibility="public", detected=None
    )

    assert session.asked == [
        "detected",
        "project_description",
        "copyright_holder",
        "package_name",
        "governance_mode",
        "work_mode",
        "container",
        "security_reporting_channel",
    ]
    assert result.values["package_name"] == "beta"
    assert result.values["container"] is True


def test_adopt_disclosure_policy_channel_is_detected_not_asked() -> None:
    session = tty("", "", "")
    result = setup_plan.plan_adopt(
        session,
        {},
        None,
        adopt_detections(),
        release_ownership="product-owned",
        dockerfile=False,
    )
    channel = setup_plan.disclosure_channels(
        ["Report privately to security@example.com within 90 days."]
    )
    setup_plan.plan_security_channel(
        session,
        result,
        {},
        visibility="public",
        detected=channel[0],
    )

    assert len(session.asked) == 3
    assert result.values["security_reporting_channel"] == "security@example.com"
    assert setup_plan.disclosure_channels(
        ["https://github.com/o/r/security", "a@example.com b@example.com"]
    ) == ["a@example.com", "b@example.com"]


def test_rejected_detection_stops_before_anything_is_written() -> None:
    session = tty("n")
    with pytest.raises(SetupError, match="--data KEY=VALUE"):
        setup_plan.plan_adopt(
            session,
            {},
            None,
            adopt_detections(),
            release_ownership="product-owned",
            dockerfile=False,
        )


def test_update_has_no_preset_or_setup_question() -> None:
    """Presets expand only in init and adopt (#1058 decision C4)."""
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["update", "--preset", "team"])
    init = cli.parser().parse_args(["init", "x", "--preset", "team"])
    assert init.preset == "team"


def test_invalid_answer_is_asked_again_without_counting() -> None:
    session = tty(
        "TODO",
        "Inventory service.",
        "cobol",
        "python",
        "",
        "Example Holder",
        "",
        "",
    )
    setup_plan.plan_init(session, {}, None)

    assert len(session.asked) == 6
    assert session.transcript.count(session.transcript[0]) == 2


# --- Non-interactive input -------------------------------------------------


def test_script_missing_required_inputs_names_every_data_flag() -> None:
    session = script()
    setup_plan.plan_init(session, {}, None)

    with pytest.raises(SetupError) as error:
        session.require_complete("init")
    message = str(error.value)
    assert "\n" not in message
    for flag in (
        "--data project_description=",
        "--data languages=",
        "--data copyright_holder=",
    ):
        assert flag in message
    assert session.asked == []


def test_script_takes_documented_defaults_and_solo_local() -> None:
    session = script()
    result = setup_plan.plan_init(
        session,
        {
            "project_description": "Inventory service.",
            "languages": "",
            "copyright_holder": "Example Holder",
        },
        None,
    )
    session.require_complete("init")

    assert result.work_mode == "solo-local"
    assert sorted(session.suggested) == [
        "documentation_languages",
        "project_license",
    ]
    assert result.values["project_license"] == "proprietary"


def test_script_custom_preset_requires_no_guess() -> None:
    session = script()
    result = setup_plan.plan_init(
        session,
        {
            "project_description": "Inventory service.",
            "languages": "go",
            "copyright_holder": "Example Holder",
            "admin_bypass": "off",
        },
        "custom",
    )
    session.require_complete("init")

    assert result.work_mode == "custom"
    assert "admin_bypass" not in result.values
    assert result.values["verification_mode"] == "local"
    assert result.sources["verification_mode"]["note"] == "suggested default"


def test_preset_override_keeps_explicit_values_and_never_saves_name() -> None:
    """AC2: a preset only expands; explicit --data overrides one key."""
    session = script()
    explicit = {
        "project_description": "Inventory service.",
        "languages": "python",
        "copyright_holder": "Example Holder",
        "admin_bypass": "beta-only",
        "scheduled_checks": "governance-drift",
    }
    result = setup_plan.plan_init(session, explicit, "solo-local")
    inputs = cli.setup_inputs(result, explicit)

    assert inputs["admin_bypass"] == "beta-only"
    assert inputs["scheduled_checks"] == "governance-drift"
    assert inputs["verification_mode"] == "local"
    assert inputs["lifecycle"] == []
    assert inputs["languages"] == "python"
    for name in ("work_mode", "preset", "solo-local"):
        assert name not in inputs
        assert name not in settings_schema.classification()
    record = setup_plan.setup_record(
        result, session, warnings=[], approval=None, explicit=explicit
    )
    assert record["work_mode"] == "solo-local"
    assert record["sources"]["admin_bypass"] == {  # type: ignore[index]
        "note": None,
        "source": "explicit",
    }


def test_unknown_preset_fails_closed() -> None:
    with pytest.raises(SetupError, match="Unknown work mode"):
        setup_plan.plan_init(tty(), {}, "solo")


# --- CLI wiring: failure before release lookup, Copier, or writes ----------


def copy_args(path: Path, *data: str, **flags: object) -> argparse.Namespace:
    arguments = ["init", str(path)]
    for item in data:
        arguments.extend(["--data", item])
    for flag, value in flags.items():
        option = "--" + flag.replace("_", "-")
        arguments.extend([option] if value is True else [option, str(value)])
    return cli.parser().parse_args(arguments)


@pytest.fixture
def no_render(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def refuse(name: str) -> Callable[..., object]:
        def call(*_args: object, **_kwargs: object) -> object:
            calls.append(name)
            raise AssertionError(f"{name} ran before setup completed")

        return call

    for name in ("resolve_revision", "copier_copy", "repository_context"):
        monkeypatch.setattr(cli, name, refuse(name))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False, raising=False)
    return calls


def test_non_interactive_init_fails_before_lookup_render_or_write(
    tmp_path: Path,
    no_render: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "product"
    code = cli.main(
        [
            "init",
            str(target),
            "--data",
            "repository_url=https://github.com/owner/product",
            "--yes",
            "--non-interactive",
        ]
    )

    assert code == 2
    assert no_render == []
    assert not target.exists()
    error = capsys.readouterr().err.strip()
    assert error.count("\n") == 0
    assert error.startswith("csarc: Missing required setup input")
    assert "--data project_description=" in error


def test_rejected_combinations_stop_before_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for values, explicit, mode, fragment in (
        (
            {"languages": ["rust"], "container": True},
            {},
            "init",
            "--data container=false",
        ),
        (
            {"languages": [], "enable_codeql": "true"},
            {},
            "init",
            "--data enable_codeql=false",
        ),
        (
            {"languages": ["go"], "verification_mode": "local"},
            {"release_trigger": "manual"},
            "init",
            "drop --data release_trigger",
        ),
    ):
        errors = setup_plan.invalid_combinations(values, explicit, mode=mode)
        assert len(errors) == 1
        assert fragment in errors[0]
    assert (
        setup_plan.invalid_combinations(
            {"languages": ["rust"], "container": True}, {}, mode="adopt"
        )
        == []
    )
    repository = cli.RepositoryContext(
        "owner/product", "owner", "user", "private", "github", True
    )
    with pytest.raises(cli.CliError, match="Nothing was rendered"):
        cli.finish_setup(
            script(),
            setup_plan.SetupResult(mode="init", work_mode="solo-local"),
            {"languages": [], "enable_codeql": True},
            {},
            repository,
            "init",
            copy_args(tmp_path / "x"),
        )


# --- Empty repository (AC4) ------------------------------------------------


def git(path: Path, *arguments: str) -> None:
    cli.run(["git", "-C", str(path), *arguments], capture=True)


def test_init_accepts_missing_empty_and_git_only_targets(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    empty = tmp_path / "empty"
    empty.mkdir()
    git_only = tmp_path / "git-only"
    git_only.mkdir()
    git(git_only, "init", "-q", "-b", "main")

    for target in (missing, empty, git_only):
        assert cli.repository_target_is_new(target)
        cli.validate_copy_target(target, "init")
        state = cli.detect_install_state(target)
        assert state["state"] == cli.INSTALL_STATE_CREATE

    staged = tmp_path / "staged"
    staged.mkdir()
    git(staged, "init", "-q", "-b", "main")
    (staged / "README.md").write_text("draft\n", encoding="utf-8")
    assert not cli.repository_target_is_new(staged)
    git(staged, "add", "README.md")
    (staged / "README.md").unlink()
    assert not cli.repository_target_is_new(staged)
    committed = tmp_path / "committed"
    committed.mkdir()
    git(committed, "init", "-q", "-b", "main")
    git(
        committed,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@e.invalid",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "init",
    )
    assert not cli.repository_target_is_new(committed)
    with pytest.raises(cli.CliError, match="empty Git repository"):
        cli.validate_copy_target(committed, "init")


# --- Approval route preflight (AC5) ----------------------------------------


def api_stub(
    responses: Mapping[str, object],
) -> Callable[[Sequence[str]], tuple[int, str, str]]:
    """Serve gh api reads by endpoint; a missing endpoint returns HTTP 403."""

    def run(arguments: Sequence[str]) -> tuple[int, str, str]:
        endpoint = arguments[-1]
        if endpoint not in responses:
            return 1, "", "HTTP 403: Must have admin rights"
        return 0, json.dumps(responses[endpoint]), ""

    return run


COLLABORATORS = "repos/owner/product/collaborators?affiliation=all&per_page=100"


def collaborators(*rows: tuple[str, str, str]) -> dict[str, object]:
    return {
        "user": {"login": "runner"},
        COLLABORATORS: [
            [
                {"login": login, "role_name": role, "type": account}
                for login, role, account in rows
            ]
        ],
    }


@pytest.mark.parametrize(
    ("responses", "owner_type", "state"),
    [
        (
            collaborators(
                ("runner", "admin", "User"), ("peer", "maintain", "User")
            ),
            "user",
            "route-observed",
        ),
        (collaborators(("runner", "admin", "User")), "user", "none-observed"),
        (
            collaborators(
                ("runner", "admin", "User"), ("helper", "write", "User")
            ),
            "user",
            "none-observed",
        ),
        (
            collaborators(("runner", "admin", "User"), ("bot", "admin", "Bot")),
            "user",
            "none-observed",
        ),
        ({"user": {"login": "runner"}}, "user", "inconclusive"),
        (
            {
                "user": {"login": "runner"},
                COLLABORATORS: [[{"login": "x", "type": "User"}]],
            },
            "user",
            "inconclusive",
        ),
        (
            collaborators(("runner", "admin", "User")),
            "organization",
            "inconclusive",
        ),
        (
            {
                **collaborators(("runner", "admin", "User")),
                "user/memberships/orgs/owner": {"role": "admin"},
            },
            "organization",
            "none-observed",
        ),
        (
            {
                "user": {"login": "runner"},
                COLLABORATORS: [
                    [
                        {"login": "x", "type": "User"},
                        {"login": "peer", "role_name": "admin", "type": "User"},
                    ]
                ],
            },
            "user",
            "route-observed",
        ),
    ],
)
def test_approval_route_states(
    responses: Mapping[str, object], owner_type: str, state: str
) -> None:
    observed, reason = setup_plan.approval_route(
        api_stub(responses), "owner/product", owner_type
    )

    assert observed == state
    for claim in ("only one writer", "guarantee", "always blocked", "proof"):
        assert claim not in reason


def test_approval_route_is_inconclusive_before_the_repository_exists() -> None:
    state, reason = setup_plan.approval_route(api_stub({}), None, None)

    assert state == "inconclusive"
    assert "not on GitHub yet" in reason


HOSTED_OFF = {
    "verification_mode": "hosted",
    "admin_bypass": "off",
    "copilot_review": "allowed",
}
LOCAL_OFF = {**HOSTED_OFF, "verification_mode": "local"}


def test_none_observed_blocks_even_with_second_approver_confirmation() -> None:
    with pytest.raises(SetupError) as error:
        setup_plan.resolve_approval(
            script(),
            LOCAL_OFF,
            "none-observed",
            "no other maintainer",
            confirm_second=True,
            confirm_copilot=False,
        )
    message = str(error.value)
    assert "--data admin_bypass=always" in message
    assert "No peer approver was observed" in message


def test_inconclusive_needs_explicit_confirmation() -> None:
    with pytest.raises(SetupError, match="--confirm-second-approver"):
        setup_plan.resolve_approval(
            script(),
            LOCAL_OFF,
            "inconclusive",
            "HTTP 403",
            confirm_second=False,
            confirm_copilot=False,
        )
    record = setup_plan.resolve_approval(
        script(),
        LOCAL_OFF,
        "inconclusive",
        "HTTP 403",
        confirm_second=True,
        confirm_copilot=False,
    )
    assert record["confirmation"] == "second-approver"
    session = tty("y")
    asked = setup_plan.resolve_approval(
        session,
        LOCAL_OFF,
        "inconclusive",
        "HTTP 403",
        confirm_second=False,
        confirm_copilot=False,
    )
    assert asked["confirmation"] == "second-approver"
    assert session.asked == []  # a confirmation is not a setup question
    assert len(session.confirmations) == 1


def test_copilot_route_counts_only_without_native_approval() -> None:
    record = setup_plan.resolve_approval(
        script(),
        HOSTED_OFF,
        "none-observed",
        "no other maintainer",
        confirm_second=False,
        confirm_copilot=True,
    )
    assert record["confirmation"] == "copilot-entitlement"
    for values in (LOCAL_OFF, {**HOSTED_OFF, "copilot_review": "off"}):
        with pytest.raises(SetupError, match="cannot replace it"):
            setup_plan.resolve_approval(
                script(),
                values,
                "none-observed",
                "no other maintainer",
                confirm_second=False,
                confirm_copilot=True,
            )


def test_preflight_runs_for_off_and_beta_only_but_not_always() -> None:
    assert setup_plan.preflight_applies({"admin_bypass": "off"})
    assert setup_plan.preflight_applies({"admin_bypass": "beta-only"})
    assert not setup_plan.preflight_applies({"admin_bypass": "always"})


def test_finish_setup_skips_collaborator_reads_for_always(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_reads(arguments: Sequence[str]) -> tuple[int, str, str]:
        raise AssertionError(f"read {arguments}")

    monkeypatch.setattr(cli, "detector_api", no_reads)
    repository = cli.RepositoryContext(
        "owner/product", "owner", "user", "private", "github", True
    )
    record = cli.finish_setup(
        script(),
        setup_plan.SetupResult(mode="init", work_mode="solo-local"),
        {
            "admin_bypass": "always",
            "verification_mode": "local",
            "languages": [],
        },
        {},
        repository,
        "init",
        copy_args(tmp_path / "x"),
    )
    assert record["approval_route"] is None


def test_finish_setup_blocks_team_without_observed_approver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "detector_api",
        api_stub(collaborators(("runner", "admin", "User"))),
    )
    repository = cli.RepositoryContext(
        "owner/product", "owner", "user", "private", "github", True
    )
    values = {**HOSTED_OFF, "copilot_review": "off", "languages": []}
    with pytest.raises(cli.CliError, match="No peer approver was observed"):
        cli.finish_setup(
            script(),
            setup_plan.SetupResult(mode="init", work_mode="team"),
            values,
            {},
            repository,
            "init",
            copy_args(tmp_path / "x", confirm_second_approver=True),
        )
    record = cli.finish_setup(
        script(),
        setup_plan.SetupResult(mode="init", work_mode="team"),
        {**HOSTED_OFF, "languages": []},
        {},
        repository,
        "init",
        copy_args(tmp_path / "x", confirm_copilot_entitlement=True),
    )
    codes = [row["code"] for row in record["warnings"]]  # type: ignore[union-attr]
    assert "W04-copilot-entitlement-confirmed" in codes


def test_cli_peer_roles_match_the_merge_gate() -> None:
    """The preflight uses the gate's own maintainer role set (#719, #785)."""
    lifecycle = runpy.run_path(str(ROOT / "scripts" / "pr_lifecycle.py"))

    assert lifecycle["MAINTAINER_PERMISSIONS"] == setup_plan.MAINTAINER_ROLES
    assert lifecycle["WRITE_ROLES"] == setup_plan.WRITE_ROLES


# --- Warnings --------------------------------------------------------------

BASE = {
    "admin_bypass": "off",
    "verification_mode": "hosted",
    "copilot_review": "off",
    "governance_mode": "managed",
    "coverage_mode": "global",
    "coverage_threshold": 80,
    "project_visibility": "private",
    "project_license": "proprietary",
    "documentation_mode": "content-only",
    "documentation_languages": "zh-tw",
    "languages": ["go"],
    "scheduled_checks": [],
    "release_ownership": "product-owned",
}


@pytest.mark.parametrize(
    ("overrides", "context", "code"),
    [
        ({"admin_bypass": "always"}, {}, "W01-admin-bypass-always"),
        (
            {"verification_mode": "local", "admin_bypass": "always"},
            {},
            "W02-local-verification",
        ),
        (
            {},
            {"approval": {"confirmation": "second-approver", "reason": "403"}},
            "W03-second-approver-confirmed",
        ),
        (
            {},
            {"approval": {"confirmation": "copilot-entitlement", "reason": ""}},
            "W04-copilot-entitlement-confirmed",
        ),
        (
            {"verification_mode": "local", "copilot_review": "allowed"},
            {},
            "W05-copilot-reference-only",
        ),
        (
            {"verification_mode": "local", "admin_bypass": "beta-only"},
            {},
            "W06-local-beta-only",
        ),
        (
            {"admin_bypass": "always"},
            {"runner_role": "write"},
            "W07-runner-not-admin",
        ),
        ({}, {"plan_name": "free"}, "W08-no-ruleset-plan"),
        ({"governance_mode": "observe"}, {}, "W09-governance-observe"),
        ({"coverage_threshold": 70}, {}, "W10-coverage-relaxed"),
        ({"project_visibility": "public"}, {}, "W11-public-proprietary"),
        (
            {"documentation_languages": "zh-tw+en"},
            {},
            "W12-documentation-scope",
        ),
        (
            {"project_visibility": "public", "enable_codeql": False},
            {},
            "W13-public-codeql-off",
        ),
        (
            {
                "verification_mode": "local",
                "scheduled_checks": ["governance-drift"],
            },
            {},
            "W15-local-actions-minutes",
        ),
        (
            {"verification_mode": "local", "admin_bypass": "always"},
            {},
            "W20-ui-merge-without-approval",
        ),
        (
            {"release_ownership": "csarc-owned"},
            {"plan_name": "free", "single_writer": False},
            "W21-single-writer-unobserved",
        ),
    ],
)
def test_each_warning_has_a_stable_code(
    overrides: dict[str, object], context: dict[str, object], code: str
) -> None:
    values = {**BASE, **overrides}
    rows = setup_plan.setup_warnings(
        values,
        approval=context.get("approval"),  # type: ignore[arg-type]
        runner_role=context.get("runner_role"),  # type: ignore[arg-type]
        plan_name=context.get("plan_name"),  # type: ignore[arg-type]
        single_writer=context.get("single_writer"),  # type: ignore[arg-type]
    )
    codes = [row["code"] for row in rows]

    assert code in codes
    assert all(
        set(row) == {"code", "command", "message", "subject"} for row in rows
    )
    baseline = setup_plan.setup_warnings(
        BASE,
        approval=None,
        runner_role=None,
        plan_name=None,
        single_writer=None,
    )
    assert code not in [row["code"] for row in baseline]


def test_warning_codes_are_documented_in_spec_009() -> None:
    spec = (ROOT / "docs/specs/SPEC-009-project-settings.md").read_text(
        encoding="utf-8"
    )
    for number, name in setup_plan.WARNINGS.items():
        assert f"`{number}-{name}`" in spec


def test_observe_mode_gets_only_a_warning(tmp_path: Path) -> None:
    """AC5: governance observe never blocks the plan; it warns once."""
    repository = cli.RepositoryContext(
        "owner/product", "owner", "user", "private", "github", True
    )
    record = cli.finish_setup(
        script(),
        setup_plan.SetupResult(mode="adopt", work_mode="solo-local"),
        {
            "admin_bypass": "always",
            "verification_mode": "local",
            "governance_mode": "observe",
            "languages": [],
        },
        {},
        repository,
        "adopt",
        copy_args(tmp_path / "x"),
    )
    codes = [row["code"] for row in record["warnings"]]  # type: ignore[union-attr]
    assert codes.count("W09-governance-observe") == 1


# --- Adopt detection and report rows ---------------------------------------


def test_adoption_detections_read_native_sources(tmp_path: Path) -> None:
    target = tmp_path / "product"
    target.mkdir()
    (target / "pyproject.toml").write_text(
        '[project]\nname = "product"\ndescription = "Inventory service."\n',
        encoding="utf-8",
    )
    (target / "LICENSE").write_text(
        "Copyright (c) 2026 Example Holder. All rights reserved.\n",
        encoding="utf-8",
    )
    (target / ".github").mkdir()
    (target / ".github" / "SECURITY.md").write_text(
        "Email security@example.com to report a vulnerability.\n",
        encoding="utf-8",
    )
    detections = {
        item.key: item for item in cli.adoption_detections(target, {})
    }

    assert detections["languages"].value == ["python"]
    assert detections["project_description"].value == "Inventory service."
    assert detections["copyright_holder"].value == "Example Holder"
    assert cli.detected_disclosure_channel(target) == "security@example.com"
    (target / "LICENSE").unlink()
    (target / "pyproject.toml").write_text(
        '[project]\nname = "product"\n', encoding="utf-8"
    )
    missing = {item.key: item for item in cli.adoption_detections(target, {})}
    assert missing["project_description"].state == "unknown"
    assert missing["copyright_holder"].state == "unknown"


def test_adopt_suggestions_become_setting_decisions() -> None:
    """AC1/AC6: intent with no unique source is a non-blocking decision."""
    actions = cli.setup_decision_actions(
        {"suggested": ["governance_mode", "container", "detected"]},
        {"governance_mode": "managed", "container": False},
    )

    assert [action["subject"] for action in actions] == [
        "container",
        "governance_mode",
    ]
    assert all(action["kind"] == "setting-decision" for action in actions)
    assert all(action["blocking"] is False for action in actions)
    rows = cli.setup_setting_rows(
        [
            {
                "after": "managed",
                "before": None,
                "class": "new",
                "key": "governance_mode",
                "note": None,
                "source": "derived",
            }
        ],
        {
            "sources": {
                "governance_mode": {"note": "asked", "source": "explicit"}
            }
        },
    )
    assert rows[0]["source"] == "explicit"
    assert rows[0]["note"] == "asked"


def test_questions_need_a_tty_without_script_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC7: TTY asks; --non-interactive, --json, or no TTY never asks."""
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)
    assert cli.setup_interactive(copy_args(tmp_path / "x"))
    assert not cli.setup_interactive(
        copy_args(tmp_path / "x", non_interactive=True)
    )
    assert not cli.setup_interactive(copy_args(tmp_path / "x", json=True))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False, raising=False)
    assert not cli.setup_interactive(copy_args(tmp_path / "x"))


@pytest.mark.large
def test_raw_render_with_custom_license_writes_no_license(
    tmp_path: Path,
) -> None:
    """Issue #1078: `custom` renders no LICENSE or manifest license field."""
    from copier import run_copy

    target = tmp_path / "custom"
    run_copy(
        str(ROOT),
        target,
        data={
            "project_name": "Custom Product",
            "project_description": "A product that ships its own terms.",
            "project_license": "custom",
            "languages": ["python", "typescript", "rust"],
            "repository_url": "https://github.com/example/custom",
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        quiet=True,
        vcs_ref="HEAD",
    )

    assert not (target / "LICENSE").exists()
    pyproject = (target / "pyproject.toml").read_text(encoding="utf-8")
    assert "license" not in pyproject
    package = json.loads((target / "package.json").read_text(encoding="utf-8"))
    assert "license" not in package
    assert package["private"] is True
    cargo = (target / "Cargo.toml").read_text(encoding="utf-8")
    assert "license" not in cargo
    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "CSARC 不產生也不解讀授權文件" in readme
    result = cli.run(
        ["python3", ".csarc/scripts/check_license_metadata.py"],
        cwd=target,
        capture=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
