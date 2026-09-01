"""Generated-repository checks for optional template update notices."""

import shutil
from pathlib import Path

import pytest
import yaml
from copier import run_copy

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("enabled", [False, True])
def test_template_update_notification_is_opt_in(
    tmp_path: Path, enabled: bool
) -> None:
    """Generate the updater only when the repository selected it."""
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(ROOT / "template", source / "template")
    project = tmp_path / "project"
    run_copy(
        str(source),
        project,
        data={
            "enable_template_update_notifications": enabled,
            "languages": [],
            "project_description": "A generated update-notification fixture.",
            "project_name": "Update notification fixture",
            "project_slug": "update-notification-fixture",
            "repository_url": (
                "https://github.com/example/update-notification-fixture"
            ),
            "security_reporting_channel": "Use the private security contact.",
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    workflow_path = project / ".github/workflows/template-update.yml"
    checker_path = project / "scripts/check-template-update"
    assert workflow_path.exists() is enabled
    assert checker_path.exists() is enabled
    assert (
        "每週一或手動執行 template update workflow"
        in (project / "README.md").read_text(encoding="utf-8")
    ) is enabled

    if not enabled:
        return

    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert workflow["permissions"] == {
        "contents": "read",
        "issues": "write",
    }
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert set(workflow["jobs"]) == {"check"}
    assert workflow["jobs"]["check"]["timeout-minutes"] == 10
    source = workflow_path.read_text(encoding="utf-8")
    assert "run: ./scripts/check-template-update" in source
    assert "CSARC_TEMPLATE_READ_TOKEN" in source
    assert "pull_request" not in source


def test_template_repository_does_not_run_generated_update_notices() -> None:
    """Keep Copier provenance checks in generated repositories only."""
    assert not (ROOT / ".github/workflows/template-update.yml").exists()
