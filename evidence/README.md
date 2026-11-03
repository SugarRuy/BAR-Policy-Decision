# Evidence and interpretation

[`audit-index.json`](audit-index.json) maps the paper's nine reporting units
to source versions, case numbers, confirmed findings, controls and unresolved
questions. It is a compact reader index, not an estimated error rate or a
replacement answer key. LegalBench SARA and DeonticBench share source material.

The seven scoped repair components live separately under `components/`.
The four added RuleArena components are an unreleased update; their
offline checks are separate from the paper's saved-response studies.
[`rulearena-component-checks.json`](rulearena-component-checks.json) records
their population checks and constructed scoring controls, with source and
implementation hashes. All seven components passed the offline checker;
the four additions also passed in a clean copy with network access and access
to the private workspaces blocked.
Other findings remain audit findings; their presence in this index does not
promise a repaired dataset.

## Included controls

- [`policyguardbench-consistency.json`](policyguardbench-consistency.json):
  all six original/strict train/test/pooled rows. Minimum edits are lower bounds
  for consistency, not adjudicated wrong labels.
- [`sharc-exact-input-controls.json`](sharc-exact-input-controls.json):
  exact-input group hashes and source row IDs; the test split's zero-conflict
  result is retained.
- [`workarena-selected-controls.json`](workarena-selected-controls.json):
  native-method verdicts and constructed request states. Tight-priority and
  plain-tight controls differ in their risk/duration settings.
- [`tac-budget/`](tac-budget/README.md): observed official scoring behavior on
  four constructed conditions, including omitted and reversed judgments.

The index also retains historical banking repairs, the SOP discretion example,
a negative LegalBench diversity check and the Retail adaptation ambiguity.
These are not additional independent reporting units.

Raw policies, complete upstream datasets and review transcripts are not
included. The paper contains the source quotations and derivations needed
to understand its cases; immutable source identities here locate the original
assets. `index-source-bindings.json` records hashes of the underlying audit
records, while `paper_cases` gives stable case labels and displayed numbers.
