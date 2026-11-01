# BAR — Benchmark Audit and Revision

Resources for **Follow the Policy, Fail the Benchmark: Auditing and Revising
Policy-Based Decision Benchmarks**, by Yanru Xiao and Yifei Cai
(Iowa State University).

BAR provides scoped benchmark revisions and evidence for reassessing policy-based
decisions. The paper studies whether model-visible policies, cases, references,
supplied intermediate answers and scoring conditions represent the same decision.
An accepted answer is not automatically a correct derivation, and a revised
component does not certify an entire dataset.

## Start here

- [Three usable revision components](docs/COMPONENTS.md): Tax reference pairs,
  LegalBench SARA numeric scoring, and ConditionalQA full-coverage aggregation.
- [Reproduce the four reported studies](docs/REPRODUCING.md): score saved
  responses without generating new model answers.
- [Audit evidence index](evidence/README.md): nine reporting units, source
  versions, case locators, controls and unresolved findings.
- [Distribution notices](THIRD_PARTY.md): BAR-original code uses MIT;
  third-party code and data retain their own terms.

## Revisions in version 0.1.0

| Component | What changes | What remains fixed |
|---|---|---|
| RuleArena Tax | Apply the required line-22 zero floor; provide all 300 original/revised reference pairs, with 27 changed amounts. | Native inputs and other reference assumptions, including unresolved dependencies. |
| LegalBench SARA numeric | Preserve signed decimal amounts and correctly handle an exact-zero answer to a zero reference. | Original SARA labels and the native nonzero tolerance. |
| ConditionalQA | Keep all reference questions in the denominator and assign zero to missing predictions. | Reference labels and per-question scoring. An explicit empty answer is still a submitted answer. |

These are component revisions, not three newly authored source datasets.
No OpenExempt replacement key or fully repaired workflow environment is
claimed. Original source material is fetched separately at the revisions
specified in each component manifest.

## Saved-response studies

The versioned response archive accompanies the
[v0.1.0 Release](https://github.com/SugarRuy/BAR-Policy-Decision/releases/tag/v0.1.0).
It supports the reported Tax, SARA, ConditionalQA and supplied-step comparisons.
The reproduction guide identifies which pinned upstream inputs are additionally
required. Files retain failed/missing submissions and all evaluation denominators.
No model credentials or model calls are needed to rescore them.

The constructed TheAgentCompany budget states and official runtime records are
under [evidence/tac-budget](evidence/tac-budget/README.md). Verifying those saved
records does not rerun an agent or the service environment.

## Citation and status

Use [CITATION.cff](CITATION.cff) for authorship and repository metadata.
Please cite the original benchmark as well as this paper, and report the
component and source revision used. The arXiv identifier will be added after
submission; this repository is not a second manuscript repository.

This repository is staged privately. Its owner will make it public manually.
The paper repository, draft history, full source caches, operational logs and
model-review conversations are not distributed here.
