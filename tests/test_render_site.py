import json
import runpy
from pathlib import Path

import pytest

SITE_MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "render_site.py")
)
PARITY_MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "check-decision-site-parity")
)
BundleError = SITE_MODULE["BundleError"]
render = SITE_MODULE["render"]
parse_parity = PARITY_MODULE["parse"]


def test_render_inlines_local_runtime_assets(tmp_path: Path) -> None:
    site = tmp_path / "site"
    docs = tmp_path / "docs"
    site.mkdir()
    docs.mkdir()
    (site / "pixel.png").write_bytes(b"png")
    (site / "style.css").write_text(
        '.hero { background: url("pixel.png"); }', encoding="utf-8"
    )
    (site / "app.js").write_text(
        'document.body.dataset.ready = "yes";', encoding="utf-8"
    )
    (docs / "site-content.js").write_text(
        "window.CONTENT = { schemaVersion: 1 };", encoding="utf-8"
    )
    source = site / "index.html"
    source.write_text(
        """<!doctype html>
<link rel="stylesheet" href="style.css">
<script src="../docs/site-content.js"></script>
<script src="app.js"></script>
<img src="pixel.png" alt="">
<a href="https://example.com/reference">Reference</a>
""",
        encoding="utf-8",
    )

    bundled = render(source, root=tmp_path)

    assert '<style data-bundled-from="style.css">' in bundled
    assert '<script data-bundled-from="app.js">' in bundled
    assert "data:image/png;base64,cG5n" in bundled
    assert 'href="https://example.com/reference"' in bundled
    assert "stylesheet" not in bundled
    assert "<script src=" not in bundled


@pytest.mark.parametrize(
    "runtime_asset",
    [
        '<link rel="stylesheet" href="https://cdn.example/style.css">',
        '<script src="https://cdn.example/app.js"></script>',
        '<img src="https://cdn.example/image.png" alt="">',
    ],
)
def test_render_rejects_external_runtime_assets(
    tmp_path: Path, runtime_asset: str
) -> None:
    source = tmp_path / "index.html"
    source.write_text(runtime_asset, encoding="utf-8")

    with pytest.raises(BundleError, match="External runtime asset"):
        render(source, root=tmp_path)


def test_render_rejects_unsupported_content_schema(tmp_path: Path) -> None:
    site = tmp_path / "site"
    docs = tmp_path / "docs"
    site.mkdir()
    docs.mkdir()
    (docs / "site-content.js").write_text(
        "window.CONTENT = { schemaVersion: 2 };", encoding="utf-8"
    )
    source = site / "index.html"
    source.write_text(
        '<script src="../docs/site-content.js"></script>', encoding="utf-8"
    )

    with pytest.raises(BundleError, match="schemaVersion"):
        render(source, root=tmp_path)


@pytest.mark.parametrize(
    ("url", "message"),
    [("missing.js", "does not exist"), ("../outside.js", "escapes")],
)
def test_render_rejects_missing_or_outside_assets(
    tmp_path: Path, url: str, message: str
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.js").write_text("", encoding="utf-8")
    source = root / "index.html"
    source.write_text(f'<script src="{url}"></script>', encoding="utf-8")

    with pytest.raises(BundleError, match=message):
        render(source, root=root)


def test_render_accepts_legacy_content_as_schema_one(tmp_path: Path) -> None:
    site = tmp_path / "site"
    docs = tmp_path / "docs"
    site.mkdir()
    docs.mkdir()
    (docs / "site-content.js").write_text(
        "window.CONTENT = {};", encoding="utf-8"
    )
    source = site / "index.html"
    source.write_text(
        '<script src="../docs/site-content.js"></script>', encoding="utf-8"
    )

    assert "window.CONTENT = {};" in render(source, root=tmp_path)


def test_overview_matches_active_workflows_and_uses_plain_language() -> None:
    root = Path(__file__).parents[1]
    chinese = (root / "site/content/_index.zh-tw.md").read_text(
        encoding="utf-8"
    )
    flow = chinese.split('{{< slide key="flow"', 1)[1].split(
        "{{< /slide >}}", 1
    )[0]
    file_map = chinese.split('{{< slide key="files"', 1)[1].split(
        "{{< /slide >}}", 1
    )[0]
    workflows = {
        path.name.removesuffix(".jinja")
        for path in (root / "template/.github/workflows").iterdir()
        if path.is_file()
    }

    assert workflows == {
        "ci.yml",
        "issue-triage.yml",
        "milestone-lifecycle.yml",
        "pr-policy.yml",
        "spec-to-issue.yml",
    }
    assert "5 條現行自動流程" in file_map
    for workflow in workflows:
        assert workflow in file_map
    for inactive in ("osv.yml", "release-please.yml", "release.yml"):
        assert inactive not in file_map
    assert "一般使用者不必記 workflow 或 script 名稱" in flow
    assert "版本與發佈流程尚未啟用" in flow


def test_bilingual_maintainer_controls_and_similar_tools_stay_in_sync() -> None:
    root = Path(__file__).parents[1]
    chinese = (root / "site/content/_index.zh-tw.md").read_text(
        encoding="utf-8"
    )
    english = (root / "site/content/_index.en.md").read_text(encoding="utf-8")
    data = json.loads(
        (root / "site/data/similar_tools.json").read_text(encoding="utf-8")
    )
    shortcode = (root / "site/layouts/shortcodes/similar-tools.html").read_text(
        encoding="utf-8"
    )
    testing_shortcode = (
        root / "site/layouts/shortcodes/testing.html"
    ).read_text(encoding="utf-8")
    journey_rail = (root / "site/layouts/partials/journey-rail.html").read_text(
        encoding="utf-8"
    )
    presentation = (root / "site/layouts/home.presentation.html").read_text(
        encoding="utf-8"
    )
    deck = (root / "site/static/deck.js").read_text(encoding="utf-8")
    glossary = (root / "site/layouts/shortcodes/glossary.html").read_text(
        encoding="utf-8"
    )
    styles = (root / "site/static/styles.css").read_text(encoding="utf-8")
    controls = (root / "site/static/detail-toggle.css").read_text(
        encoding="utf-8"
    )
    active_components = (root / "site/static/legacy-components.js").read_text(
        encoding="utf-8"
    )

    for source in (chinese, english):
        assert 'key="similar-tools" parity="supplemental"' in source
        assert "{{< similar-tools >}}" in source
        assert (
            'key="testing" audience="maintainer" parity="supplemental"'
            in source
        )
        assert "{{< testing >}}" in source
    assert shortcode.count('data-audience="maintainer"') == 1
    assert "data-similar-tools-tab-testing" not in shortcode
    assert "similar-tools-testing-matrix" in testing_shortcode
    assert 'id="testing-tab-duration"' in testing_shortcode
    assert 'id="testing-panel-duration"' in testing_shortcode
    assert "statusLabel" not in data["testing"]["labels"]["zh-tw"]
    assert "statusLabel" not in data["testing"]["labels"]["en"]
    assert (
        'appendix maintainer-bookend{{ if eq .Key "testing" }}' in journey_rail
    )
    assert (
        journey_rail.index('href="#testing"')
        < journey_rail.index('href="#bridge"')
        < journey_rail.index('href="#glossary"')
    )
    assert "五月盤點" in journey_rail
    assert "決策附錄" not in journey_rail
    assert 'data-audience="maintainer"' in glossary
    assert "備忘\uff5c名詞表" in glossary
    assert "testing.after(bridge)" in presentation
    assert "slide.dataset.audience !== 'archive'" in deck
    assert "Cloudflare Pages" in chinese
    assert "存取 #79" in chinese
    assert "不另導入 Spec Kit" in active_components
    assert "Fleet 盤點與平台門檻" in active_components
    for source in (chinese, english):
        assert 'key="bridge" audience="maintainer"' in source
        for key in (
            "access-control",
            "principles",
            "benchmark",
            "fleet-inventory",
            "fleet-governance-thresholds",
            "spec-format",
        ):
            assert f'key="{key}" audience="archive"' in source
    assert ".journey-bookend.maintainer-bookend.active-selection" in styles
    assert '.detail-level-control button[aria-pressed="true"]' in controls
    assert "background: var(--yellow);" in controls
    assert "overflow-y: auto;" in styles
    assert ".journey-rail {\n      position: fixed;" in styles
    assert ".slide.active > .legacy-content > * { flex-shrink: 0; }" in styles
    assert ".similar-tools-tabs button {\n      flex: 0 0 auto;" in styles
    assert "min-width: 210px;" not in styles
    assert chinese.count('data-config-direct="true"') == 3
    assert "guidance.dataset.configDirect === 'true'" in (
        root / "site/static/detail-toggle.js"
    ).read_text(encoding="utf-8")
    assert "規則治理單獨定義合併資格、權限與例外" in active_components
    assert "AI 能執行工作，但不能自行合併" not in active_components  # noqa: RUF001

    assert 'simple = "標準"' in chinese
    assert 'simple = "Standard"' in english
    assert len(data["features"]) == 13
    assert len(data["featureGroups"]) == 4
    assert data["featureGroups"][0]["features"] == [
        "repositoryTruth",
        "declarativeState",
        "proposalLifecycle",
        "rightSizedWork",
    ]
    assert data["featureGroups"][1]["features"] == [
        "agentInstructions",
        "durableAgentContext",
        "parallelAgentIsolation",
        "humanDecisionBoundary",
    ]
    assert data["featureGroups"][2]["features"] == [
        "sharedVerificationEntry",
        "riskBasedSelection",
        "freshCompletionEvidence",
        "generatedProjectVerification",
    ]
    assert data["featureGroups"][3]["features"] == ["templateLifecycle"]
    assert len(data["testing"]["groups"]) == 3
    duration_rows = data["testing"]["duration"]["rows"]
    assert [row["key"] for row in duration_rows] == ["issue", "release"]
    assert all(len(row["shared"]["items"]) == 3 for row in duration_rows)
    assert all(len(row["templateOnly"]["items"]) == 3 for row in duration_rows)
    assert duration_rows[0]["shared"]["total"]["zh-tw"] == "約 1\u20137 分鐘"
    assert duration_rows[1]["templateOnly"]["total"]["zh-tw"] == (
        "約 9\u201314 分鐘"
    )
    assert data["testing"]["groups"][0]["journey"] == "01"
    testing_rows = data["testing"]["groups"][0]["rows"]
    assert [row["purpose"]["zh-tw"]["title"] for row in testing_rows] == [
        "Issue 工作邊界",
        "PR 與 Issue 可追溯性",
        "Spec 契約與 Issue 同步",
        "Milestone 完成條件",
        "Journey 01 整體回歸",
    ]
    assert testing_rows[0]["shared"]["milestone"]["files"][0] == {
        "path": "tests/test_work_definition.py",
        "pending": True,
        "issue": 382,
    }
    assert testing_rows[0]["shared"]["milestone"]["automation"][0] == {
        "path": ".github/workflows/issue-triage.yml",
        "job": "classify",
        "trigger": {
            "zh-tw": "Issue opened／edited／reopened／closed",  # noqa: RUF001
            "en": "Issue opened, edited, reopened, or closed",
        },
        "timeout": "5 min",
    }
    assert (
        testing_rows[1]["shared"]["milestone"]["automation"][0]["timeout"]
        == "10 min"
    )
    assert testing_rows[-1]["templateOnly"]["release"]["files"][1] == {
        "path": "tests/test_template_work_definition.py",
        "pending": True,
        "issue": 382,
    }
    agent_rows = data["testing"]["groups"][1]["rows"]
    assert data["testing"]["groups"][1]["journey"] == "02"
    assert agent_rows[0]["shared"]["release"]["files"] == [
        {"path": "scripts/verify"}
    ]
    assert agent_rows[0]["templateOnly"]["milestone"]["files"] == [
        {"path": "tests/test_ai_guidelines.py"}
    ]
    assert agent_rows[1]["shared"]["milestone"]["files"] == [
        {"path": "scripts/test-worktree-cleanup"}
    ]
    assert all(
        "automation" not in stage
        for row in agent_rows
        for scope in (row["shared"], row["templateOnly"])
        for stage in scope.values()
    )
    verification_rows = data["testing"]["groups"][2]["rows"]
    assert data["testing"]["groups"][2]["journey"] == "03"
    assert [row["purpose"]["zh-tw"]["title"] for row in verification_rows] == [
        "判斷這次要跑多少",
        "Issue PR 的快速回饋",
        "發版候選的完整證據",
    ]
    assert verification_rows[0]["shared"]["milestone"]["files"] == [
        {"path": "scripts/ci_tier.py"}
    ]
    assert verification_rows[0]["shared"]["milestone"]["automation"] == [
        {
            "path": ".github/workflows/ci.yml",
            "job": "verify",
            "trigger": {
                "zh-tw": "Issue PR\uff08工作分支 → dev\uff09",
                "en": "Issue PR (work branch → dev)",
            },
            "timeout": "30 min",
        }
    ]
    assert verification_rows[0]["templateOnly"] == {}
    assert data["testing"]["labels"]["zh-tw"]["release"] == (
        "發版 PR\uff08dev → main\uff09"
    )
    assert data["testing"]["labels"]["en"]["release"] == (
        "Release PR (dev → main)"
    )
    assert "archived" not in data["testing"]["labels"]["zh-tw"]
    assert "archived" not in testing_shortcode

    assert len(data["tools"]) == 15
    assert sum(len(tool["comparisons"]) for tool in data["tools"]) == 64
    assert data["comparisonDate"] == "2026-08-31"
    assert data["releaseCutoff"] == "2026-02-28"
    assert data["threshold"] == 5
    assert data["starThreshold"] == 1000
    assert 'class="tool-meta"' in shortcode
    assert shortcode.count('class="capture-date"') == 2
    assert data["labels"]["zh-tw"]["stars"] == "GitHub Stars"
    assert data["labels"]["en"]["stars"] == "GitHub Stars"

    def recent(tool: dict[str, object]) -> bool:
        released = str(tool["released"])
        return len(released) == 10 and released >= data["releaseCutoff"]

    def coverage_count(tool: dict[str, object]) -> int:
        coverage = tool["coverage"]
        assert isinstance(coverage, dict)
        return len(coverage["full"]) + len(coverage["partial"])

    primary = [
        tool
        for tool in data["tools"]
        if recent(tool) and coverage_count(tool) >= data["threshold"]
    ]
    primary.sort(
        key=lambda tool: (
            -len(tool["coverage"]["full"]),
            -len(tool["coverage"]["partial"]),
            tool["name"].lower(),
        )
    )
    assert [tool["name"] for tool in primary] == [
        "projen",
        "Repository Harness",
    ]

    ecosystem = {
        tool["name"]
        for tool in data["tools"]
        if recent(tool)
        and coverage_count(tool) < data["threshold"]
        and int(tool["stars"].replace(",", "")) >= data["starThreshold"]
    }
    assert ecosystem == {
        "Backlog.md",
        "Backstage",
        "BMAD",
        "Copier",
        "OpenRewrite",
        "OpenSpec",
        "Ruler",
        "Spec Kit",
        "Superpowers",
        "Dagger",
        "Nx",
    }
    assert {tool["name"] for tool in data["tools"]} - {
        tool["name"] for tool in primary
    } - ecosystem == {"AGENTS.md", "Minder"}
    superpowers = next(
        tool for tool in data["tools"] if tool["name"] == "Superpowers"
    )
    assert superpowers["coverage"] == {
        "full": ["02"],
        "partial": ["01", "03", "04"],
    }
    comparison_keys = {
        tool["name"]: {comparison["key"] for comparison in tool["comparisons"]}
        for tool in data["tools"]
    }
    assert comparison_keys["AGENTS.md"] == {"agentInstructions"}
    assert comparison_keys["Ruler"] == {"agentInstructions"}
    for tool in data["tools"]:
        for comparison in tool["comparisons"]:
            assert comparison["feature"]
            assert comparison["docs"].startswith("https://")
            assert set(comparison["description"]) == {"zh-tw", "en"}


def test_parity_ignores_explicit_supplemental_slides(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.html"
    candidate = tmp_path / "candidate.html"
    legacy.write_text(
        '<section class="slide" data-track="journey">Shared copy</section>',
        encoding="utf-8",
    )
    candidate.write_text(
        """<section class="slide" id="journey">
<div class="legacy-content">Shared copy</div>
</section>
<section class="slide" id="similar-tools" data-audience="maintainer">
<div class="legacy-content">Supplemental maintainer copy</div>
</section>
<section class="slide" id="public-supplement" data-parity="supplemental">
<div class="legacy-content">Supplemental public copy</div>
</section>
""",
        encoding="utf-8",
    )

    assert parse_parity(legacy, candidate=False) == parse_parity(
        candidate, candidate=True
    )
