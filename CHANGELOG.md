# BAR changes

## Unreleased — Python package

- Add the installable `bar-policy-decision` package (`bar_policy`, package
  version 1.0.0.dev0) for BAR asset release 0.2.0: integrated revised Tax and
  Airline datasets with verbatim model-visible messages, separate references
  and provenance, existing scorers, component access and a `bar-policy`
  command. See `docs/API.md`.
- Move the `scripts/bar.py` and `scripts/rulearena.py` implementation into the
  shared `src/bar_policy/_core.py` without changing CLI behavior or outputs.
  The component inventory now also covers the package code and API guide.
- No change to components, references, patches, scoring semantics, study
  archives, saved responses or frozen release records. No model calls.

## 0.2.0 — 2026-11-04

- Add RuleArena Airline prompt errata, a 300-case Markdown zero-shot minimum-cost
  objective builder, and exact terminal-amount scoring as separate components.
- Add two source-bound RuleArena NBA localization errata with a 216-record
  original/revised builder.
- Add offline population checks, independent Airline policy arithmetic, native
  scoring-branch controls, and wrong-source rejection checks.
- Keep the three v0.1.0 components, four study archives, original response
  records, and their reported results unchanged. No new model experiment.
- Bind this release to the current 28-page paper and its arXiv source package.
- Refresh documentation checksums and provide a separate v0.1.0 inventory
  addendum. The earlier author-metadata edit rewrote the historical tag target;
  this release makes no further change to that tag or its scientific payloads.

## 0.1.0 — released

Three revisions: RuleArena Tax line-22 reference correction, LegalBench SARA
numeric scoring, and ConditionalQA full-denominator scoring. Four saved-response
studies and nine reporting-unit evidence entries. Original release metadata is
preserved in `releases/v0.1.0.json`. The four study archives and all experimental
results are unchanged. The documentation-only checksum correction is recorded
in `releases/v0.1.0-inventory-amendment.json`.
