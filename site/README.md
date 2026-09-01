# Hugo site source

`site/` is the maintainable source for the root decision presentation. Hugo
builds only this directory into an ignored staging directory; the existing
portable renderer then writes the committed deliverables. Do not edit
`docs/index.html`, `docs/index.en.html`, or either `llms.txt` output directly.

## Source layers

| Path | Responsibility |
| --- | --- |
| `content/` | Paired Chinese and English Markdown with matching content keys |
| `layouts/` | Hugo page, partial, shortcode, and `llms.txt` templates |
| `static/` | Presentation styles, interactions, and bundled local assets |
| `data/glossary.toml` | Shared glossary and `llms.txt` source |
| `data/navigation.json` | Bilingual rail labels, grouping, participation colours, and legend copy |
| `data/similar_tools.json` | Similar-tool comparisons and CI/CD appendix data |
| `legacy/index.html` | Replaced hand-authored page kept only as a fidelity fixture |
| `hugo.toml` | Pinned Hugo inputs and output formats |

The generated-repository handbook has a separate, smaller source map:

| Path | Responsibility |
| --- | --- |
| `template/docs/site-content.md.jinja` | Initial project-owned Markdown; Copier preserves later edits |
| `template/site/index.html.jinja` | Template-owned accessible shell and render markers |
| `template/site/styles.css` | Template-owned default presentation |
| `template/docs/site-theme.css.jinja` | Project-owned narrow theme overrides |
| `template/scripts/render_site.py` | Reads `.csarc/config.yml`, renders Markdown, and produces the offline bundle |

The root presentation and generated handbook intentionally use different layouts, but both keep authored content outside generated HTML and both produce deterministic, self-contained files.

The legacy fixture is not an authoring source. Its CSS, images, and retained
behaviour remain under `static/` while the parity check still needs them; do not
remove those files until repository search and the parity check prove they are
unused.

## Build and verify

```bash
./scripts/build-decision-site
./scripts/build-decision-site --check
```

The command pins Hugo 0.165.0, stages Hugo output under ignored `dist/`, and
passes both languages through the unchanged portable bundler. It commits only
the two presentation files and the two `llms.txt` indexes:

- `docs/index.html`
- `docs/index.en.html`
- `llms.txt`
- `docs/llms.txt`

The legacy view is generated only at `dist/hugo-fidelity.html` for local visual
comparison. Translation, navigation width, legacy parity, glossary links, and
generated-output drift are enforced by `./scripts/verify-template.sh`.

## Repository documentation boundary

Hugo mounts only `site/content/`, `site/layouts/`, `site/static/`, and
`site/data/`. Existing `docs/decisions/`, `docs/specs/`, runbooks, and TDD or
other engineering records stay independent Markdown sources with their own
lifecycles; link to them from the presentation instead of moving or copying
them into Hugo content. The Hugo publish directory stays under `dist/`, so a
build cannot overwrite those authored documents.

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
them in the Hugo partial.
