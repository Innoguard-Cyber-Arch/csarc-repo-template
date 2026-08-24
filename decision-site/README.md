# Hugo decision-site candidate

This directory is the source for the Milestone 8 candidate. It does not
replace the delivered `site/` source or `docs/index.html` until Issue #209.

Build and verify the ignored preview:

```bash
./scripts/build-hugo-preview --check
```

The command pins Hugo 0.165.0, writes only below `dist/`, and passes the
candidate page through the unchanged portable bundler. During the transition,
the Hugo layout reads the reviewed legacy body and mounts its local assets;
later Milestone issues replace that bridge with Markdown content.
