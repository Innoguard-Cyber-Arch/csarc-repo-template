# This project's repo-site

`docs/site/content/_index.zh-tw.md` and `_index.en.md` are the Markdown sources for
this project's own presentation-style site (`docs/index.html` /
`docs/index.en.html`), built by `.csarc/scripts/build-repo-site`. Once generated,
both files are yours to edit -- a later `csarc update` never overwrites them.

- Add a page by adding a new `{{< slide key="..." track="..." ... >}}...{{< /slide >}}`
  block to both language files (same `key`, same structure) and a matching
  entry to `docs/site/data/navigation.json`'s `items` array.
- `{{< standard >}}` holds the plain-language pane most readers see;
  `{{< ops >}}` holds the maintainer-facing detail shown in Maintenance mode.
- `[[project_name]]`, `[[project_description]]`, `[[languages]]`,
  `[[branch_strategy]]`, `[[project_visibility]]`, `[[code_owner]]`,
  `[[reviewers]]`, and `[[repository_url]]` resolve from `.csarc/config.yml`
  at build time -- editing that file (or running `csarc update`) is enough to
  refresh them, no template update needed.
- `.csarc/scripts/check-repo-site-translations` fails the build when the two
  language files' slide/content keys drift apart; keep both in sync.
- Never hand-edit `docs/index.html` / `docs/index.en.html` -- they are
  rebuilt from these sources.

This is the same engine and component set (`.csarc/site/static/styles.css`,
`detail-toggle.css`, `deck.js`, ...) as the
[csarc-repo-template](https://github.com/Innoguard-Cyber-Arch/csarc-repo-template)
project's own root site; see that project's `docs/site/content/_index.zh-tw.md`
for a much larger example of the same block syntax in use.
