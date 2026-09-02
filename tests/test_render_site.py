import json
import runpy
from pathlib import Path

import pytest
from jinja2 import Environment, StrictUndefined

SITE_MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "render_site.py")
)
PARITY_MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "check-decision-site-parity")
)
BundleError = SITE_MODULE["BundleError"]
render = SITE_MODULE["render"]
parse_parity = PARITY_MODULE["parse"]


def _write_markdown_site(
    tmp_path: Path,
    markdown: str,
    *,
    name: str = "Demo",
    description: str = "Safe <demo>",
    visibility: str = "private",
) -> Path:
    """Create the managed shell and its single configuration source."""
    site = tmp_path / "site"
    docs = tmp_path / "docs"
    scripts = tmp_path / "scripts"
    config = tmp_path / ".csarc"
    site.mkdir()
    docs.mkdir()
    scripts.mkdir()
    config.mkdir()
    root = Path(__file__).parents[1]
    (scripts / "csarc_config.py").write_text(
        (root / "scripts/csarc_config.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (config / "config.yml").write_text(
        f"project_name: {name}\n"
        f"project_description: {description}\n"
        f"project_visibility: {visibility}\n"
        "languages:\n"
        "- python\n"
        "- rust\n",
        encoding="utf-8",
    )
    (docs / "site-content.md").write_text(markdown, encoding="utf-8")
    source = site / "index.html"
    source.write_text(
        "<title><!-- CSARC_SITE_TITLE --></title>"
        "<nav><!-- CSARC_SITE_NAV --></nav>"
        "<main><!-- CSARC_SITE_CONTENT --></main>",
        encoding="utf-8",
    )
    return source


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


def test_render_injects_markdown_and_existing_config(tmp_path: Path) -> None:
    source = _write_markdown_site(
        tmp_path,
        """# [[project_name]]

[[project_description]]

## Start here

- Languages: **[[languages]]**
- Run `./scripts/verify`

### 進階: Details

Read [reference](https://example.com/docs).
""",
    )

    bundled = render(source, root=tmp_path)

    assert "<title>Demo — 內部專案網站</title>" in bundled
    assert '<a href="#start-here">Start here</a>' in bundled
    assert "Safe &lt;demo&gt;" in bundled
    assert "<strong>python、rust</strong>" in bundled
    assert (
        '<details class="advanced"><summary>進階: Details</summary>' in bundled
    )
    assert 'target="_blank" rel="noreferrer"' in bundled


def test_render_rejects_unknown_markdown_config_key(tmp_path: Path) -> None:
    source = _write_markdown_site(tmp_path, "# [[unknown_setting]]")

    with pytest.raises(BundleError, match="Unknown site content setting"):
        render(source, root=tmp_path)


def test_render_reflects_different_project_visibility_values(
    tmp_path: Path,
) -> None:
    """The internal site's visible-audience line must change with the
    Rules-governance-approved `project_visibility` key, not stay hardcoded."""
    markdown = "# [[project_name]]\n\nVisibility: **[[project_visibility]]**\n"
    private_root = tmp_path / "private"
    public_root = tmp_path / "public"
    private_root.mkdir()
    public_root.mkdir()

    private_source = _write_markdown_site(
        private_root, markdown, visibility="private"
    )
    public_source = _write_markdown_site(
        public_root, markdown, visibility="public"
    )

    private_bundle = render(private_source, root=private_root)
    public_bundle = render(public_source, root=public_root)

    assert "Visibility: <strong>private</strong>" in private_bundle
    assert "Visibility: <strong>public</strong>" in public_bundle
    assert private_bundle != public_bundle


def test_render_reflects_different_project_name_values(tmp_path: Path) -> None:
    """The internal site's title/heading (site name) must change with the
    existing `project_name` key instead of a hardcoded string."""
    markdown = "# [[project_name]]\n"
    alpha_root = tmp_path / "alpha"
    beta_root = tmp_path / "beta"
    alpha_root.mkdir()
    beta_root.mkdir()

    alpha_source = _write_markdown_site(
        alpha_root, markdown, name="Alpha Project"
    )
    beta_source = _write_markdown_site(beta_root, markdown, name="Beta Project")

    alpha_bundle = render(alpha_source, root=alpha_root)
    beta_bundle = render(beta_source, root=beta_root)

    assert "<title>Alpha Project — 內部專案網站</title>" in alpha_bundle
    assert "<title>Beta Project — 內部專案網站</title>" in beta_bundle
    assert alpha_bundle != beta_bundle


def test_branch_strategy_switches_generated_site_content() -> None:
    """The already-approved `branch_strategy` key must actually switch the
    handbook's standard-vs-delivery guidance at Copier generation time,
    proving that "mode switching" is config-driven rather than a second,
    site-only setting."""
    root = Path(__file__).parents[1]
    template = (root / "template/docs/site-content.md.jinja").read_text(
        encoding="utf-8"
    )
    environment = Environment(autoescape=True, undefined=StrictUndefined)

    def render_for(branch_strategy: str) -> str:
        return environment.from_string(template).render(
            branch_strategy=branch_strategy,
            enable_governance_drift_check=False,
            project_mode="new",
        )

    delivery = render_for("delivery")
    standard = render_for("main")

    assert "Delivery route" in delivery
    assert "批次邊界" in delivery
    assert "Delivery route" not in standard
    assert "批次邊界" not in standard
    assert delivery != standard


def test_internal_site_keys_are_documented_once() -> None:
    """Rules governance's configuration table stays the single description
    of internal-site settings; the internal-site page must reference it
    instead of redefining the same key list independently."""
    root = Path(__file__).parents[1]
    for source in (
        (root / "site/content/_index.zh-tw.md").read_text(encoding="utf-8"),
        (root / "site/content/_index.en.md").read_text(encoding="utf-8"),
    ):
        governance_config = source.split('key="governance-config"', 1)[1].split(
            "{{< /detail >}}", 1
        )[0]
        docs_site_access = source.split('key="docs-site-access"', 1)[1].split(
            "{{< /detail >}}", 1
        )[0]
        for key in (
            "project_name",
            "project_description",
            "repository_url",
            "project_slug",
        ):
            assert key in governance_config
            assert key not in docs_site_access
        assert "project_visibility" in governance_config
        assert "branch_strategy" in governance_config


def test_render_surfaces_preserved_legacy_content(tmp_path: Path) -> None:
    source = _write_markdown_site(tmp_path, "# [[project_name]]")
    legacy = tmp_path / "docs/site-content.js"
    legacy.write_text("window.CONTENT = {};", encoding="utf-8")

    bundled = render(source, root=tmp_path)

    assert "需要遷移舊網站內容" in bundled
    assert legacy.read_text(encoding="utf-8") == "window.CONTENT = {};"


def test_generated_site_uses_project_owned_markdown() -> None:
    root = Path(__file__).parents[1]
    copier = (root / "copier.yml").read_text(encoding="utf-8")
    shell = (root / "template/site/index.html.jinja").read_text(
        encoding="utf-8"
    )
    content = (root / "template/docs/site-content.md.jinja").read_text(
        encoding="utf-8"
    )

    assert '  - "docs/site-content.md"' in copier
    assert "site-content.js" not in copier
    assert "CSARC_SITE_CONTENT" in shell
    assert "site-content.js" not in shell
    assert "[[project_name]]" in content
    assert "[[languages]]" in content
    assert "[[project_visibility]]" in content
    assert not (root / "template/site/app.js").exists()
    assert not (root / "template/docs/site-content.js.jinja").exists()


def test_render_rejects_incomplete_markdown_shell(tmp_path: Path) -> None:
    source = tmp_path / "index.html"
    source.write_text("<!-- CSARC_SITE_CONTENT -->", encoding="utf-8")

    with pytest.raises(BundleError, match="incomplete Markdown marker"):
        render(source, root=tmp_path)


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
    english = (root / "site/content/_index.en.md").read_text(encoding="utf-8")
    chinese_home = chinese.split('{{< slide key="capability"', 1)[1].split(
        "{{< /slide >}}", 1
    )[0]
    english_home = english.split('{{< slide key="capability"', 1)[1].split(
        "{{< /slide >}}", 1
    )[0]
    flow = chinese.split('{{< slide key="flow"', 1)[1].split(
        "{{< /slide >}}", 1
    )[0]
    supply = chinese.split('{{< slide key="supply"', 1)[1].split(
        "{{< /slide >}}", 1
    )[0]
    chinese_delivery = chinese.split('{{< slide key="deploy"', 1)[1].split(
        "{{< /slide >}}", 1
    )[0]
    english_delivery = english.split('{{< slide key="deploy"', 1)[1].split(
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
    optional_workflows = {"template-update.yml"}

    assert workflows - optional_workflows == {
        "ci.yml",
        "governance-comment.yml",
        "governance-drift.yml",
        "issue-triage.yml",
        "milestone-lifecycle.yml",
        "osv.yml",
        "pr-policy.yml",
        "release.yml",
        "spec-to-issue.yml",
        "work-item-closure.yml",
    }
    assert optional_workflows <= workflows
    assert "9 條共用流程" in file_map
    workflow_labels = {
        "ci.yml": "必要驗證",
        "governance-comment.yml": "reviewer 指派",
        "governance-drift.yml": "治理漂移",
        "issue-triage.yml": "工作單整理",
        "milestone-lifecycle.yml": "里程碑同步",
        "osv.yml": "漏洞排程",
        "pr-policy.yml": "PR 規則",
        "release.yml": "候選發版",
        "spec-to-issue.yml": "規格開單",
        "template-update.yml": "模板更新通知",
        "work-item-closure.yml": "工作關單",
    }
    assert workflows == set(workflow_labels)
    for workflow, label in workflow_labels.items():
        assert label in file_map, (
            f"{workflow} lost its file-map mention ({label!r})"
        )
    assert "選配的治理漂移與模板更新通知排程" in file_map
    for inactive in ("release-please.yml",):
        assert inactive not in file_map
    assert "一般使用者不必記 workflow 或 script 名稱" in flow
    assert "需人審查版本 PR 的發版流程仍是候選" in flow
    assert "一支候選 release workflow" in chinese_delivery
    assert "Candidate／Blocked" in chinese_delivery  # noqa: RUF001
    assert "promotion-gated adaptive release" not in chinese_delivery
    assert "下方 technical view 保留 2026-08" not in chinese_delivery
    assert "the system opens a version PR for human review" in english_delivery
    assert "Candidate / Blocked" in english_delivery
    assert "使用 AI／vibe coding 的一般開發者" in chinese_home  # noqa: RUF001
    assert "不要求具備工程或 CI/CD 維運背景" in chinese_home
    assert "general AI-assisted or vibe-coding developers" in english_home
    assert "does not assume an engineering or CI/CD operations background" in (
        english_home
    )
    assert "Milestone <編號>: <里程碑名稱>" in chinese
    assert "Milestone <number>: <Milestone title>" in english
    for explanation in (
        "鎖定版本清單（lockfile）",  # noqa: RUF001
        "自動更新服務（Dependabot）",  # noqa: RUF001
        "已知漏洞掃描（OSV）",  # noqa: RUF001
        "軟體成分清單（SBOM）",  # noqa: RUF001
    ):
        assert explanation in supply
    journey_decisions = chinese.split('{{< slide key="method"', 1)[1].split(
        '{{< slide key="similar-tools"', 1
    )[0]
    assert '<article class="decision-step' not in journey_decisions
    assert journey_decisions.count('class="decision-step decision-fold') == 18
    assert (
        journey_decisions.count('class="decision-step decision-fold" open') == 9
    )
    assert (
        journey_decisions.count(
            'class="decision-step decision-fold recommended" open'
        )
        == 9
    )


def test_bilingual_maintainer_controls_and_similar_tools_stay_in_sync() -> None:  # noqa: C901
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
    navigation = json.loads(
        (root / "site/data/navigation.json").read_text(encoding="utf-8")
    )
    presentation = (root / "site/layouts/home.presentation.html").read_text(
        encoding="utf-8"
    )
    deck = (root / "site/static/deck.js").read_text(encoding="utf-8")
    styles = (root / "site/static/styles.css").read_text(encoding="utf-8")
    controls = (root / "site/static/detail-toggle.css").read_text(
        encoding="utf-8"
    )
    config_examples = json.loads(
        (root / "site/data/config_examples.json").read_text(encoding="utf-8")
    )
    active_components = (root / "site/static/legacy-components.js").read_text(
        encoding="utf-8"
    )
    template_verify = (root / "template/scripts/verify.jinja").read_text(
        encoding="utf-8"
    )
    assert "policies/dev-next-ruleset.json" not in template_verify

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
        'class="journey-bookend appendix {{ .participation }}' in journey_rail
    )
    assert 'class="journey-item {{ .participation }}' in journey_rail
    assert navigation["appendices"][-2]["key"] == "testing"
    assert navigation["appendices"][-1]["key"] == "bridge"
    assert navigation["appendices"][-2]["audience"] == "maintainer"
    assert navigation["labels"]["zh-tw"]["human"] == "需要人決策"
    assert navigation["labels"]["zh-tw"]["automated"] == "預設自動完成"
    assert navigation["labels"]["zh-tw"]["maintainer"] == "僅維運可見"
    workflow_participation = {
        item["key"]: item["participation"]
        for item in navigation["items"]
        if item["group"] == "workflow"
    }
    assert workflow_participation == {
        "method": "human",
        "agents": "automated",
        "contract": "automated",
        "languages": "automated",
        "supply": "automated",
        "pr": "human",
        "deploy": "human",
        "governance": "human",
    }
    assert 'class="journey-legend"' in journey_rail
    assert "決策附錄" not in journey_rail
    assert 'href="#glossary"' not in journey_rail
    for source in (chinese, english):
        assert 'key="notes"' not in source
        assert "{{< glossary >}}" not in source
    assert (
        "0 steps 表示程式尚未執行"
        in data["testing"]["duration"]["labels"]["zh-tw"]["runnerNote"]
    )
    assert (
        "archive/ci-cd/ 只供參考"
        in data["testing"]["duration"]["labels"]["zh-tw"]["archiveNote"]
    )
    assert "名詞與約定" not in chinese
    assert "testing.after(bridge)" in presentation
    assert "supply.before(pr)" in presentation
    assert "slide.dataset.audience !== 'archive'" in deck
    assert "Cloudflare Pages" in chinese
    assert "存取 #79" in chinese
    # Issue #472: this content used to be a hardcoded, zh-tw-only
    # `configExamples` object inside legacy-components.js; it now lives in
    # site/data/config_examples.json (bilingual) and is server-rendered by
    # the config-guidance shortcode, so legacy-components.js no longer
    # contains any of this prose at all.
    method_summaries = " ".join(
        item.get("summary", {}).get("zh-tw", "")
        for item in config_examples["tracks"]["method"]["items"]
    )
    assert "不另導入 Spec Kit" in method_summaries
    template_release_summaries = " ".join(
        item.get("summary", {}).get("zh-tw", "")
        for item in config_examples["tracks"]["template-release"]["items"]
    )
    assert "沒有 active bot identity" in template_release_summaries
    assert "CSARC_VERSION_BOT_CLIENT_ID" not in active_components
    assert (
        config_examples["tracks"]["governance"]["items"][0]["title"]["zh-tw"]
        == "單一來源｜治理只保存高價值選項"  # noqa: RUF001
    )
    assert (
        "提出者、另一位核准者、到期日、證據與復原方式"
        in (
            config_examples["tracks"]["governance"]["items"][-1]["summary"][
                "zh-tw"
            ]
        )
    )
    assert "template" not in config_examples["tracks"]
    assert "knowledge" not in config_examples["tracks"]
    assert "rollout" not in config_examples["tracks"]
    assert "rollout:" not in active_components
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
    assert ".journey-bookend.maintainer.active-selection" in styles
    assert ".journey-item.human" in styles
    assert ".journey-item.automated" in styles
    assert ".journey-legend" in styles
    assert '.detail-level-control button[aria-pressed="true"]' in controls
    assert "background: var(--yellow);" in controls
    assert "overflow-y: auto;" in styles
    assert ".journey-rail {\n      position: fixed;" in styles
    assert ".slide.active > .legacy-content > * { flex-shrink: 0; }" in styles
    assert ".similar-tools-tabs button {\n      flex: 0 0 auto;" in styles
    assert "min-width: 210px;" not in styles
    direct_tracks = {
        track
        for track, spec in config_examples["tracks"].items()
        if spec["direct"]
    }
    assert direct_tracks == {"method", "agents", "contract"}
    for source in (chinese, english):
        for track in direct_tracks:
            assert f'{{{{< config-guidance track="{track}" >}}}}' in source
    guidance_shortcode = (
        root / "site/layouts/shortcodes/config-guidance.html"
    ).read_text(encoding="utf-8")
    assert 'data-config-direct="true"' in guidance_shortcode
    assert "guidance.dataset.configDirect === 'true'" not in active_components
    assert (
        'not([data-config-direct="true"]) .config-trigger'
    ) in active_components
    assert "guidance.dataset.configDirect === 'true'" in (
        root / "site/static/detail-toggle.js"
    ).read_text(encoding="utf-8")
    assert (
        "規則治理單獨定義合併資格、權限與例外"
        in config_examples["tracks"]["agents"]["items"][-1]["goal"]["zh-tw"]
    )
    assert "AI 能執行工作，但不能自行合併" not in active_components  # noqa: RUF001
    for track in ("method", "agents", "contract", "languages", "supply", "pr"):
        titles = " ".join(
            item["title"]["zh-tw"]
            for item in config_examples["tracks"][track]["items"]
        )
        assert "固定基線｜" in titles  # noqa: RUF001
        assert any(
            label in titles
            for label in ("可調整｜", "專案選擇｜", "專案選配｜")  # noqa: RUF001
        )
    assert (
        config_examples["tracks"]["languages"]["items"][0]["title"]["zh-tw"]
        == "可調整｜選用語言與 Python 支援範圍"  # noqa: RUF001
    )
    assert (
        config_examples["tracks"]["languages"]["items"][1]["title"]["zh-tw"]
        == "固定基線｜各語言使用原生工具"  # noqa: RUF001
    )
    assert (
        config_examples["labels"]["zh-tw"]["intro"]
        == "只列公版主要政策、可調選項與設定位置。"
    )
    # Issue #472: the 6 removed hand-authored EN <aside class="config-guidance"
    # data-audience="maintainer"> placeholders (method, agents, contract,
    # languages, pr, supply) used to hide this content behind the
    # simple/technical detail toggle even though the equivalent zh-tw content
    # was always visible. The config-guidance shortcode's output carries no
    # data-audience attribute, so English readers now see the same
    # config-trigger content zh-tw readers always saw, without an extra
    # click; only the one unrelated "Root repository state" maintainer note
    # keeps that gating.
    assert english.count('data-audience="maintainer"') == 1

    assert 'simple = "標準"' in chinese
    assert 'simple = "Standard"' in english
    assert len(data["features"]) == 34
    assert len(data["featureGroups"]) == 9
    assert data["featureGroups"][0]["features"] == [
        "repositoryTruth",
        "workItemStructure",
        "milestoneKickoff",
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
    assert data["featureGroups"][3]["features"] == [
        "languageSelection",
        "nativeLanguageChecks",
        "composableLanguageModules",
        "languageConfiguration",
    ]
    assert data["featureGroups"][4]["features"] == [
        "dependencyUpdatePolicy",
        "lockedDependencyResolution",
        "knownVulnerabilityDetection",
        "releaseArtifactInventory",
    ]
    assert data["featureGroups"][5]["features"] == [
        "pullRequestUnit",
        "integrationRoute",
        "mergeReadiness",
        "baseSynchronization",
        "proposalLifecycle",
    ]
    assert data["featureGroups"][6]["features"] == [
        "versionIntent",
        "versionMaterialization",
        "releaseOwnership",
        "releaseEvidence",
    ]
    assert data["featureGroups"][7]["features"] == [
        "governancePolicyLocation",
        "governanceCapabilityBoundary",
        "governanceExceptionRecord",
    ]
    assert data["featureGroups"][8]["features"] == [
        "declarativeState",
        "templateLifecycle",
    ]
    assert [group["journey"] for group in data["testing"]["groups"]] == [
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
    ]
    duration_rows = data["testing"]["duration"]["rows"]
    assert [row["key"] for row in duration_rows] == ["issue", "release"]
    assert all(len(row["shared"]["items"]) == 8 for row in duration_rows)
    assert all(len(row["templateOnly"]["items"]) == 8 for row in duration_rows)
    for row in duration_rows:
        for scope in ("shared", "templateOnly"):
            assert [
                item["label"]["zh-tw"][:2] for item in row[scope]["items"]
            ] == ["01", "02", "03", "04", "05", "06", "08", "09"]
    assert duration_rows[0]["shared"]["total"]["zh-tw"] == "約 1\u20137 分鐘"
    assert duration_rows[0]["templateOnly"]["total"]["zh-tw"] == (
        "約 1\u20134 分鐘（fast 實測 59\u201399 秒）"  # noqa: RUF001
    )
    assert duration_rows[1]["templateOnly"]["total"]["zh-tw"] == (
        "約 6\u20138 分鐘（完整 job 實測 6 分 16 秒）"  # noqa: RUF001
    )
    assert (
        "2026-09-01" in data["testing"]["duration"]["labels"]["zh-tw"]["scope"]
    )
    assert "不另計" not in json.dumps(
        data["testing"]["duration"], ensure_ascii=False
    )
    assert "no separate minutes" not in json.dumps(data["testing"]["duration"])
    assert all(
        [item["label"]["en"] for item in row[scope]["items"]][:2]
        == ["01 Work definition", "02 AI rules"]
        for row in duration_rows
        for scope in ("shared", "templateOnly")
    )
    language_durations = [
        item["value"]["en"]
        for row in duration_rows
        for scope in ("shared", "templateOnly")
        for item in row[scope]["items"]
        if item["label"]["en"] == "04 Programming languages"
    ]
    assert language_durations
    assert all(
        value.index("Python") < value.index("Rust") < value.index("TypeScript")
        for value in language_durations
    )
    assert data["testing"]["groups"][0]["journey"] == "01"
    testing_rows = data["testing"]["groups"][0]["rows"]
    assert [row["purpose"]["zh-tw"]["title"] for row in testing_rows] == [
        "Issue 工作邊界",
        "Spec 契約與 Issue 同步",
        "里程碑啟動門檻",
    ]
    assert data["testing"]["groups"][0]["stageLabels"]["zh-tw"] == {
        "milestone": "工作開始前",
        "release": "工作結束時",
    }
    assert testing_rows[0]["shared"]["milestone"]["files"][0] == {
        "path": "scripts/test-issue-triage"
    }
    assert testing_rows[0]["shared"]["release"]["files"] == [
        {"path": "scripts/test-issue-triage"}
    ]
    assert testing_rows[0]["shared"]["milestone"]["automation"][0] == {
        "path": ".github/workflows/issue-triage.yml",
        "job": "classify",
        "trigger": {
            "zh-tw": "Issue opened／edited／reopened／closed",  # noqa: RUF001
            "en": "Issue opened, edited, reopened, or closed",
        },
        "timeout": "5 min",
    }
    assert testing_rows[2]["shared"]["milestone"]["files"] == [
        {
            "path": "tests/test_milestone_approval.py",
            "pending": True,
            "issue": 400,
        }
    ]
    assert testing_rows[0]["templateOnly"]["release"]["files"] == [
        {"path": "tests/test_work_item_forms.py"}
    ]
    assert "release" not in testing_rows[2]["shared"]
    agent_rows = data["testing"]["groups"][1]["rows"]
    assert data["testing"]["groups"][1]["journey"] == "02"
    assert agent_rows[0]["shared"] == {}
    assert agent_rows[0]["templateOnly"]["milestone"]["files"] == [
        {"path": "tests/test_ai_guidelines.py"}
    ]
    assert agent_rows[0]["templateOnly"]["release"]["files"] == [
        {"path": "tests/test_ai_guidelines.py"}
    ]
    assert agent_rows[1]["shared"]["milestone"]["files"] == [
        {"path": "scripts/test-worktree-cleanup"}
    ]
    assert agent_rows[1]["shared"]["release"]["files"] == [
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
        "交付候選的完整證據",
    ]
    assert verification_rows[0]["shared"]["milestone"]["files"] == [
        {"path": "scripts/ci_tier.py"}
    ]
    language_rows = data["testing"]["groups"][3]["rows"]
    assert data["testing"]["groups"][3]["journey"] == "04"
    assert [row["purpose"]["zh-tw"]["title"] for row in language_rows] == [
        "設定與實際檔案一致",
        "各語言使用自己的檢查",
    ]
    assert language_rows[0]["shared"]["milestone"]["files"][0] == {
        "path": ".csarc/config.yml"
    }
    supply_rows = data["testing"]["groups"][4]["rows"]
    assert data["testing"]["groups"][4]["journey"] == "05"
    assert [row["purpose"]["zh-tw"]["title"] for row in supply_rows] == [
        "鎖定版本可重現安裝",
        "一般更新自動提出 PR",
        "已公開漏洞立即檢查",
        "發版成品清冊與雜湊",
    ]
    assert supply_rows[1]["shared"]["milestone"]["files"] == [
        {"path": ".github/dependabot.yml"}
    ]
    assert supply_rows[2]["shared"]["milestone"]["files"] == [
        {"path": "scripts/verify-dependencies"}
    ]
    assert supply_rows[2]["shared"]["release"]["automation"][1]["path"] == (
        ".github/workflows/osv.yml"
    )
    assert data["testing"]["groups"][6]["journey"] == "07"
    delivery_rows = data["testing"]["groups"][6]["rows"]
    assert [row["purpose"]["zh-tw"]["title"] for row in delivery_rows] == [
        "獨立工作直接交付",
        "Hotfix 完整驗證與證據",
        "版本與 Release ownership",
        "版本候選與發布證據",
        "里程碑結案",
    ]
    assert delivery_rows[0]["shared"]["milestone"]["files"] == [
        {"path": "scripts/test-pr-policy"},
        {"path": "tests/test_ci_tier.py"},
    ]
    assert delivery_rows[1]["shared"]["milestone"]["files"] == [
        {"path": "scripts/test-pr-policy"},
        {"path": "tests/test_ci_tier.py"},
    ]
    assert delivery_rows[2]["shared"]["milestone"]["files"] == [
        {"path": "docs/adr/release-security-and-dependencies.md"}
    ]
    assert delivery_rows[2]["shared"]["release"]["files"] == [
        {"path": "scripts/release_policy.py"},
        {"path": "scripts/release_bundle.py"},
        {"path": "tests/test_release_bundle.py"},
    ]
    assert delivery_rows[3]["shared"]["milestone"]["files"] == [
        {"path": "scripts/verify-release-candidate"}
    ]
    assert delivery_rows[3]["shared"]["release"]["files"] == [
        {"path": "scripts/release_bundle.py"},
        {"path": "tests/test_release_bundle.py"},
    ]
    assert delivery_rows[4]["shared"]["release"]["files"] == [
        {"path": "tests/test_milestone_lifecycle.py"},
        {
            "path": "tests/test_milestone_closure.py",
            "pending": True,
            "issue": 400,
        },
    ]
    governance_rows = data["testing"]["groups"][7]["rows"]
    assert data["testing"]["groups"][7]["journey"] == "08"
    assert [row["purpose"]["zh-tw"]["title"] for row in governance_rows] == [
        "輪派審查人",
        "偵測治理設定漂移",
    ]
    assert governance_rows[0]["shared"]["milestone"]["automation"] == [
        {
            "path": ".github/workflows/governance-comment.yml",
            "job": "request-reviewer",
            "trigger": {
                "zh-tw": "PR 開啟、重開或轉為 ready",
                "en": "PR opened, reopened, or marked ready",
            },
            "timeout": "5 min",
        }
    ]
    assert all(
        "pending" not in automation
        for automation in governance_rows[1]["shared"]["release"]["automation"]
    )
    template_rows = data["testing"]["groups"][8]["rows"]
    assert data["testing"]["groups"][8]["journey"] == "09"
    assert [row["purpose"]["zh-tw"]["title"] for row in template_rows] == [
        "建立新 repo",
        "首次導入既有 repo",
        "後續更新與衝突",
        "通知有新版公版",
    ]
    assert template_rows[1]["shared"]["milestone"]["automationNote"][
        "zh-tw"
    ].startswith("人工門檻")
    assert "automation" not in template_rows[1]["shared"]["milestone"]
    assert all(
        "verify-template.sh" not in item.get("path", "")
        for row in template_rows
        for stage in row["shared"].values()
        for item in stage.get("files", [])
    )
    update_notification = template_rows[3]["shared"]["milestone"]["automation"][
        0
    ]
    assert update_notification["path"] == (
        ".github/workflows/template-update.yml"
    )
    assert "pending" not in update_notification
    assert verification_rows[0]["shared"]["milestone"]["automation"] == [
        {
            "path": ".github/workflows/ci.yml",
            "job": "verify",
            "trigger": {
                "zh-tw": "工作 PR\uff08topic → main 或 dev/m*\uff09",
                "en": "Work PR (topic → main or dev/m*)",
            },
            "timeout": "30 min",
        }
    ]
    assert verification_rows[0]["templateOnly"] == {}
    merge_rows = data["testing"]["groups"][5]["rows"]
    assert data["testing"]["groups"][5]["journey"] == "06"
    assert [row["purpose"]["zh-tw"]["title"] for row in merge_rows] == [
        "PR 資料與目的分支",
        "候選內容包含最新基準",
        "工作 PR 合併後結束 Issue",
    ]
    assert (
        merge_rows[0]["shared"]["milestone"]["automation"][0]["path"]
        == ".github/workflows/pr-policy.yml"
    )
    assert merge_rows[2]["shared"]["milestone"]["files"] == [
        {"path": "tests/test_work_pr_closure.py"},
        {"path": "scripts/pr_lifecycle.py"},
    ]
    assert merge_rows[2]["shared"]["milestone"]["automation"] == [
        {
            "path": ".github/workflows/work-item-closure.yml",
            "job": "close-work",
            "trigger": {
                "zh-tw": "里程碑工作 PR 合併進 dev/m*",
                "en": "Milestone work PR merged into dev/m*",
            },
            "timeout": "5 min",
        }
    ]
    assert data["testing"]["labels"]["zh-tw"]["release"] == (
        "交付 PR\uff08dev/m*\uff0fdev/i* → main\uff09"
    )
    assert data["testing"]["labels"]["en"]["release"] == (
        "Delivery PR (dev/m* or dev/i* → main)"
    )
    assert "archived" not in data["testing"]["labels"]["zh-tw"]
    assert "archived" not in testing_shortcode

    assert len(data["tools"]) == 28
    assert sum(len(tool["comparisons"]) for tool in data["tools"]) == 113
    assert data["comparisonDate"] == "2026-09-01"
    assert data["releaseCutoff"] == "2026-03-01"
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
        "Git Town",
        "Nx",
        "Dependabot",
        "Renovate",
        "pnpm",
        "ty",
        "uv",
        "Rust / Cargo",
        "OSV-Scanner",
        "Syft",
        "Sapling",
        "Release Please",
        "semantic-release",
        "Changesets",
    }
    assert {tool["name"] for tool in data["tools"]} - {
        tool["name"] for tool in primary
    } - ecosystem == {"AGENTS.md", "Minder"}
    superpowers = next(
        tool for tool in data["tools"] if tool["name"] == "Superpowers"
    )
    assert superpowers["coverage"] == {
        "full": ["02"],
        "partial": ["01", "03", "06"],
    }
    comparison_keys = {
        tool["name"]: {comparison["key"] for comparison in tool["comparisons"]}
        for tool in data["tools"]
    }
    assert comparison_keys["AGENTS.md"] == {"agentInstructions"}
    assert comparison_keys["Ruler"] == {"agentInstructions"}
    assert comparison_keys["Release Please"] == {
        "versionIntent",
        "versionMaterialization",
        "releaseOwnership",
    }
    assert comparison_keys["semantic-release"] == {
        "versionIntent",
        "versionMaterialization",
        "releaseOwnership",
    }
    assert comparison_keys["Changesets"] == {
        "versionIntent",
        "versionMaterialization",
        "releaseOwnership",
    }
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
