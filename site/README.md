# Decision-site source

`site/` is the maintainable source for the root decision presentation.
`scripts/build_decision_site.py` (Issue #524) is a pure-Python, stdlib-only
render engine that reads this directory and stages plain HTML under ignored
`dist/decision-site/`; the existing portable renderer
(`scripts/render_site.py`) then writes the committed deliverables. Do not
edit `docs/index.html`, `docs/index.en.html`, or either `llms.txt` output
directly.

## Source layers

| Path | Responsibility |
| --- | --- |
| `content/` | Paired Chinese and English Markdown with matching content keys, using the same `{{< slide key="..." >}}...{{< /slide >}}`-style block syntax the engine parses |
| `static/` | Template-owned presentation styles, interactions, bundled local assets, and the vendored Mermaid build under `static/vendor/` |
| `theme.css` | Project- or fork-owned colour/theme overrides (Issue #527); ships empty, always linked and inlined, narrowly scoped to `:root` custom properties and existing block-level selectors -- see the file's own header comment |
| `data/glossary.toml` | Shared glossary and `llms.txt` source |
| `data/navigation.json` | Bilingual rail labels, grouping, participation colours, and legend copy |
| `data/config_examples.json` | Fixed/adjustable policy examples rendered by `render_config_guidance()` |
| `data/similar_tools.json` | Similar-tool comparisons and CI/CD appendix data |
| `legacy/index.html` | Replaced hand-authored page kept only as a fidelity fixture |
| `version.json` | Independent engine and presentation-template versions and their compatibility range, checked by `scripts/check-decision-site-versions` |

The generated-repository handbook has a separate, smaller source map:

| Path | Responsibility |
| --- | --- |
| `template/docs/site-content.md.jinja` | Initial project-owned Markdown; Copier preserves later edits |
| `template/site/index.html.jinja` | Template-owned accessible shell and render markers |
| `template/site/styles.css` | Template-owned default presentation |
| `template/docs/site-theme.css.jinja` | Project-owned narrow theme overrides |
| `template/scripts/render_site.py` | Reads `.csarc/config.yml`, renders Markdown, and produces the offline bundle |

The root presentation and generated handbook intentionally use different
engines and layouts, but both keep authored content outside generated HTML,
both produce deterministic self-contained files, and both share the same
`scripts/render_site.py` asset-inlining/external-scheme-rejection step.

The legacy fixture is not an authoring source. Its CSS, images, and retained
behaviour remain under `static/` while the parity check still needs them; do not
remove those files until repository search and the parity check prove they are
unused.

## Build and verify

```bash
./scripts/build-decision-site
./scripts/build-decision-site --check
```

The command validates navigation label width and the engine/template version
range, renders both languages under ignored `dist/decision-site/`, and passes
each through the unchanged portable bundler. It commits only the two
presentation files and the two `llms.txt` indexes:

- `docs/index.html`
- `docs/index.en.html`
- `llms.txt`
- `docs/llms.txt`

Translation structure, navigation width, legacy parity, glossary links, and
generated-output drift are enforced by `./scripts/verify-template.sh`.

## Repository documentation boundary

The engine only reads `site/content/`, `site/static/`, `site/data/`, and the
single project-owned `site/theme.css` override file. Existing
`docs/decisions/`, `docs/specs/`, runbooks, and TDD or other
engineering records stay independent Markdown sources with their own
lifecycles; link to them from the presentation instead of moving or copying
them into `site/content/`. The engine's own output stays under ignored
`dist/`, so a build cannot overwrite those authored documents.

## Reading modes

The presentation defaults to **Overview** and keeps the established visual
components in both modes. Classify content by purpose, not by the reader's
technical ability:

- Overview answers what the template does, why a choice was made, what the
  user must do, and which limits affect that choice. Supported profiles,
  prerequisites, the end-to-end flow, and ownership legends stay visible.
- Maintenance adds file paths, commands, configuration examples, permission
  matrices, fallbacks, evidence retention, and source references.

Use the existing maintenance selectors in `static/detail-toggle.js` for
implementation-only blocks. Long setting lists and maintenance appendices use
the paged in-slide overlay instead of making the presentation itself scroll.

The rail uses yellow for steps that require a human decision, green for work
the template or CI can complete, and blue for maintainer-only appendices. Edit
the labels and classifications in `data/navigation.json`; do not duplicate
them in `scripts/build_decision_site.py`.

## Mermaid diagrams

Content authors write a plain ` ```mermaid ` fenced block; the engine emits
`<pre class="mermaid">` plus a small boot `<script>` and only references the
vendored `static/vendor/mermaid.min.js` build on a page that actually
contains one, so a page without a diagram pays no cost for it.
