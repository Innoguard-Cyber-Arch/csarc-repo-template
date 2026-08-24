# Hugo decision-site candidate

This directory is the source for the Milestone 8 candidate. It does not
replace the delivered `site/` source or `docs/index.html` until Issue #209.

Build and verify the ignored preview:

```bash
./scripts/build-hugo-preview --check
```

The command pins Hugo 0.165.0, passes the Chinese-default and English candidate
pages through the unchanged portable bundler, and checks the committed LLM
indexes. Run it without `--check` to regenerate root `llms.txt` and
`docs/llms.txt` from `data/glossary.toml`; never edit those outputs directly.
The paired Markdown sources use the same ordered content keys, and the
verification scripts reject translation, glossary, link, format, or
generated-output drift. `llms-full.txt` is intentionally omitted because the
repository has no separate full-text corpus that would add useful content.
