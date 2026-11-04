# BAR — Benchmark Audit and Revision

Resources for **Follow the Policy, Fail the Benchmark: Auditing and Revising
Policy-Based Decision Benchmarks**, by Yanru Xiao and Yifei Cai.

Policy-based decision benchmarks ask a model to apply a written policy to a
case, but the policy, the case, the reference answer, any supplied intermediate
answers and the scoring rule do not always describe the same decision. When
they disagree, a policy-supported response can be rejected and an incomplete
one accepted.

Rescoring unchanged model responses shows how these defects change scores.
In RuleArena Tax, restoring the required zero floor changes 27 of 300
reference amounts and narrows one observed model gap from 14 to 4
accepted cases. In LegalBench's SARA numeric task, correcting decimal parsing
and zero-reference scoring raises accepted answers from 8–9 to 87–91 out of
96 across three models, with reference answers unchanged. The
[full results](docs/REPRODUCING.md#expected-results) give the per-model
comparisons.

BAR publishes the audit evidence behind these findings, along with scoped
revisions for reevaluating models.

**[Download v0.2.0](https://github.com/SugarRuy/BAR-Policy-Decision/releases/tag/v0.2.0)**
· [Usage and setup](docs/COMPONENTS.md)
· [Audit evidence](evidence/README.md)
· [Reproduce the studies](docs/REPRODUCING.md)

## Revised resources

BAR provides seven revision components across the five tasks below. Airline
has three separate components. Each revision targets a specific reference,
scorer or task text; usage and scope are in the
[component guide](docs/COMPONENTS.md).

| Benchmark / task | What BAR provides |
|---|---|
| RuleArena Tax | 300 original/revised reference pairs (27 changed amounts), an input builder and a scoped correction to the reference program |
| LegalBench SARA numeric | A revised numeric scorer; original labels unchanged |
| ConditionalQA | A revised scorer that counts missing predictions as zero instead of dropping them; original labels unchanged |
| RuleArena Airline | Separate revisions for policy transcription and examples, amount scoring, and an explicit minimum-cost objective that amends the task specification |
| RuleArena NBA | Corrections to two team/operation localization fields among 216 records; all binary verdicts unchanged |

## Audit evidence

The [evidence index](evidence/README.md) covers nine audit entries, including
controls and unresolved findings: RuleArena, OpenExempt, LegalBench SARA,
DeonticBench, ConditionalQA, ShARC, PolicyGuardBench, WorkArena++ and
TheAgentCompany. Findings differ across entries. Where no revision is listed
above, including the workflow environments, the entry is documented as audit
evidence.

## Reproducing the studies

Four saved-response studies cover RuleArena Tax, LegalBench SARA numeric,
ConditionalQA and an amended OpenExempt task with supplied intermediate
answers. The reported results can be rescored from the saved outputs in the
v0.2.0 release by following the [reproduction guide](docs/REPRODUCING.md).
Some upstream inputs are obtained separately under their original terms. The
Airline and NBA revisions come without new performance results.

## Citation and license

Please cite this paper using [CITATION.cff](CITATION.cff), cite the original
benchmarks you use, and report which BAR revisions and source versions your
results are based on. BAR-original code is released under the
[MIT License](LICENSE). Third-party code and data keep their own terms, listed
in [THIRD_PARTY.md](THIRD_PARTY.md).
