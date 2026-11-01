# Frozen response study assets

`index.json` pins four compressed Release assets by SHA-256. Keep the archives
compressed; the independent CLI reads them directly. `SHA256SUMS` provides
the same archive checksums for standard file-verification tools.

Download the four `BAR-study-*-v1.tar.gz` assets from the
[v0.1.0 Release](https://github.com/SugarRuy/BAR-Policy-Decision/releases/tag/v0.1.0)
and put them in this directory, next to `index.json`.

```bash
python3 scripts/reproduce_results.py --sources /data/bar-sources.json
```

See `docs/REPRODUCING.md` for source paths, full input verification, native
checks, expected metrics, and scope limits. These assets preserve 2,664
retained responses; source datasets and the eight published CQA control
prediction files are separately obtained inputs.
