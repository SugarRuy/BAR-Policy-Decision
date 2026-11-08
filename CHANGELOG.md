# BAR changes

## Unreleased — Python package

- Package `1.0.0.dev1` adds post-publication API corrections:
  - Validate ConditionalQA prediction/reference IDs and answer structure
    before evaluation. Unknown or duplicate prediction IDs and malformed
    submissions now raise; absent predictions for reference IDs count as zero and
    legal empty answers retain native scoring. Results expose full-denominator
    coverage, missing/empty-answer IDs and the prediction hash.
    Validation and evaluator file reads both use UTF-8, preventing locale
    defaults from corrupting non-ASCII answers and conditions.
  - Default new Tax API evaluations to `rulearena-tax-numeric-v1`, which
    fixes truncated ungrouped amounts and rejects malformed grouping.
    The native phrase, sign and tolerance remain. The amount after the first
    answer phrase must be valid; a malformed amount is not skipped in favor
    of a later one.
    `scorer="rulearena-tax-native"` retains the previous parser exactly.
    This changes the API default, not the paper's frozen reproduction path.
  - Clarify nullable component revisions, per-scorer argument types and
    metadata for unapplied Airline errata.
- Correct the stale `release.json` entry in the current component inventory
  left by the paper-link update. No frozen release record is rewritten.

### Initial API (`1.0.0.dev0`)

- Add the installable `bar-policy-decision` package (`bar_policy`, package
  version 1.0.0.dev0) for BAR asset release 0.2.0: integrated revised Tax and
  Airline datasets with verbatim model-visible messages, separate references
  and provenance, existing scorers, component access and a `bar-policy`
  command. See `docs/API.md`.
- Move the `scripts/bar.py` and `scripts/rulearena.py` implementation into the
  shared `src/bar_policy/_core.py` without changing CLI behavior or outputs.
  The component inventory now also covers the package code and API guide.
- The initial API preserved the component scoring semantics. All component
  payloads, references, patches, study archives, saved responses and frozen
  release records remain unchanged in both API revisions. No model calls.

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
