# Hugo decision-site candidate

This directory is the source for the Milestone 8 candidate. It does not
replace the delivered `site/` source or `docs/index.html` until Issue #209.

Build and verify the ignored preview:

```bash
./scripts/build-hugo-preview --check
```

The command pins Hugo 0.165.0, writes only below `dist/`, and passes the
Chinese-default and English candidate pages through the unchanged portable
bundler. The paired Markdown sources use the same ordered content keys;
`scripts/check-decision-site-translations` rejects missing translation blocks.
