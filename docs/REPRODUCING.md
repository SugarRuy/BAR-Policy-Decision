# Reproduce the four paper studies offline

The four compressed assets in `studies/` retain **2,664 original visible
responses**: Tax 900, SARA 288, ConditionalQA 855, and OpenExempt 621.
They contain the parsed submissions, invalid/missing-submission markers,
frozen scores, source and request hashes, and configuration bindings.
No model service, credential, network connection, or private project import
is needed to replay them.

Download the four `BAR-study-*-v1.tar.gz` assets from the
[v0.1.0 Release](https://github.com/SugarRuy/BAR-Policy-Decision/releases/tag/v0.1.0)
before going offline. Place all four archives **next to
`studies/index.json`**, inside `studies/`; do not unpack them. The tag is the
download location, and the archive names retain the study-format version `v1`.

`scripts/reproduce_results.py` is an independent CLI. It reads the archives
without extracting them, checks their hashes against `studies/index.json`,
parses every original visible response again, calculates scores, and compares
every result with the frozen per-case ledger. Saved scores are assertions,
not inputs to the scoring calculation. A mismatch terminates with a nonzero
exit code.

Selection follows the frozen cohort's retained-result bindings and recorded
continuation edges; it never uses answer values, correctness or scores.
Delivered invalid answers are not replaced or repaired. The archives retain
all 77 missing CQA submissions (24 Luna, 53 Gemma) with their original visible
text and parsed/invalid state, plus Luna's one invalid OpenExempt JSON
submission. They remain in the attempted/full-coverage denominators.

## Local source contract

Obtain upstream inputs separately under their own terms before disconnecting.
Original datasets, policy caches, and upstream evaluator source files are
not redistributed in these study assets. Numerical Tax reference pairs and
the amended OpenExempt study's numerical target inputs are included.
SARA references, CQA references, and the eight published CQA control files
are loaded from separately obtained, hash-pinned files.

Create a JSON file mapping the following names to local directories:

```json
{
  "rulearena": "/data/RuleArena",
  "legalbench_code": "/data/legalbench-code",
  "legalbench_data": "/data/legalbench-data",
  "conditionalqa": "/data/ConditionalQA",
  "codeprompting": "/data/emnlp2024-code-prompting",
  "openexempt": "/data/OpenExempt"
}
```

These are ordinary upstream roots, compatible with the `--source` directories
accepted by `scripts/bar.py`. Use original pinned files, not patched output
directories. The replay CLI does not depend on `bar.py`.

| Root | Pinned revision | Required files |
| --- | --- | --- |
| `rulearena` | `59f60f6b4eb93a9b6d187ec781349d4f15618903` | `tax/auto_test.py`, `tax/prompt.py`, `tax/synthesized_problems/comp_{0,1,2}.json` |
| `legalbench_code` | `b46bf4ffae90524b2b72aaa30e7745fe9db64481` | `tasks/sara_numeric/base_prompt.txt`; `evaluation.py` for source auditing |
| `legalbench_data` | `daec8237410aa23e3faf4bc41ad8b3a7e1696826` | `sara_numeric/test.tsv` |
| `conditionalqa` | `77bd295952daf415548b3244db10880d3d55cfe0` | `v1_0/dev.json`, `v1_0/documents.json`, `evaluate.py` |
| `codeprompting` | `34b3d0d2f8b7f1f5a5cabeb216d5b9d62884da0d` | Eight `outputs/ConditionalQA/.../output.json` files listed by `--list-inputs` |
| `openexempt` | dataset `842cedec770ff2e45636fb5cb526ba0708ceb908` | `data/reasoning_decomposition/rd_optimal_exemptions_4/test.parquet`, or the local alias `rd_optimal_exemptions_4-test.parquet` |

Code Prompting's [pinned official revision](https://github.com/UKPLab/emnlp2024-code-prompting/tree/34b3d0d2f8b7f1f5a5cabeb216d5b9d62884da0d)
is the commit `34b3d0d2f8b7f1f5a5cabeb216d5b9d62884da0d`
("Update citation", November 13, 2024). A November 1, 2026 availability
check confirmed it through both GitHub's commit API and `git ls-remote`.
All eight pinned control files were downloaded and matched their frozen
SHA-256 values, with 285 unique dev IDs each. `studies/upstream-availability.json`
records their exact paths, download URLs and checksums. The pin is unchanged.

The OpenExempt dataset is
[SergioServantez/OpenExempt](https://huggingface.co/datasets/SergioServantez/OpenExempt/tree/842cedec770ff2e45636fb5cb526ba0708ceb908).
Its original file is
[`data/reasoning_decomposition/rd_optimal_exemptions_4/test.parquet`](https://huggingface.co/datasets/SergioServantez/OpenExempt/resolve/842cedec770ff2e45636fb5cb526ba0708ceb908/data/reasoning_decomposition/rd_optimal_exemptions_4/test.parquet).
The check downloaded **114,322 bytes**, with SHA-256
`805b490c6991116764f6cd8f1fed513292745c95f751c030cd98584bb86daa27`,
matching both the frozen input and the dataset's LFS object hash.
Use the original path under the directory mapped by `openexempt`, or
download it under the accepted local alias:

```bash
mkdir -p /data/OpenExempt
curl -fL \
  'https://huggingface.co/datasets/SergioServantez/OpenExempt/resolve/842cedec770ff2e45636fb5cb526ba0708ceb908/data/reasoning_decomposition/rd_optimal_exemptions_4/test.parquet' \
  -o /data/OpenExempt/rd_optimal_exemptions_4-test.parquet
```

Download the actual Parquet bytes, not a Git LFS pointer. Downloads are
preparation steps performed before offline replay; the replay CLI does not
make network requests.

All exact file SHA-256 values and the eight long control paths are embedded
in the assets. Print the complete machine-readable contract with:

```bash
python3 scripts/reproduce_results.py --list-inputs
```

The input contract also recognizes the recorded flat-cache filenames for
LegalBench; this does not relax hash checking. No command downloads files.
The upstream repository identity for Code Prompting is
`UKPLab/emnlp2024-code-prompting`; CQA is `haitian-sun/ConditionalQA`;
LegalBench code is `HazyResearch/legalbench`, and data is `nguha/legalbench`.

## Commands

Run from the artifact repository, using Python 3.10 or later:

```bash
python3 scripts/reproduce_results.py \
  --sources /data/bar-sources.json \
  --output /tmp/bar-replay.json
```

The basic replay uses only the Python standard library. It requires the
SARA test TSV, CQA dev JSON, and all eight CQA control outputs. Other upstream
files are needed only for the additional checks below. The output must be a
new file; the program will not overwrite a previous report.

To verify input construction as well as scores:

```bash
python3 scripts/reproduce_results.py \
  --sources /data/bar-sources.json \
  --verify-inputs --native-checks \
  --output /tmp/bar-replay-with-inputs.json
```

`--verify-inputs` reconstructs all unique model-visible inputs and every
retained request's model/configuration binding, including Gemma's actual
wire request body. Tax uses only the inspected
native prompt-builder function from the pinned source, SARA substitutes the
native template, CQA joins complete document contents with its frozen
instruction suffix, and OpenExempt reconstructs all three amended inputs
from the pinned Parquet. Reading OpenExempt Parquet requires a separately
installed local `pyarrow`; the basic score replay does not.

`--native-checks` additionally executes only the pure CQA metric functions
from the hash-pinned user-supplied evaluator. It compares every answer-pair
calculation and runs literal native permutations for lists of at most seven
answers. Longer lists use the mathematically equivalent alignment computation
described below and are checked against every frozen native per-case score.
No upstream experiment entrypoint or model client is imported.

Select one study with `--study rulearena-tax`, `legalbench-sara-numeric`,
`conditionalqa`, or `openexempt`. Use `--studies-dir` if Release assets are
stored outside the repository. Keep `index.json` with them. Tax and
OpenExempt score-only replays require no external source files.

## Expected results

Model codes are H = Haiku 5.5, L = GPT6 Luna, G = Gemma 4 31B. Their
recorded IDs and full request configurations are retained inside every
asset. H/L request `xhigh`; G requests `high`. These are hosted configuration
bindings, not a claim that a provider's underlying checkpoint is immutable.

| Study | H | L | G |
| --- | --- | --- | --- |
| Tax original → revised, /300 | 209 → 224 (+16, −1) | 241 → 261 (+20, −0) | 195 → 220 (+25, −0) |
| SARA original / parsing / parsing+zero, /96 | 8 / 87 / 91 | 9 / 83 / 87 | 8 / 84 / 88 |
| CQA original → full denominator | 285 → 285 | 261 → 285 | 232 → 285 |
| OE released / revised / omitted, /69 | 50 / 68 / 69 | 66 / 68 / 69 | 65 / 64 / 69 |
| OE released → revised transitions | +18, −0 | +3, −1 | +2, −3 |

All CQA values below are percentages; the machine-readable report uses fractions.

| Model | Version | EM | EM+conditions | F1 | F1+conditions |
| --- | --- | ---: | ---: | ---: | ---: |
| H | original and revised | 58.63 | 34.64 | 65.81 | 40.22 |
| L | original | 52.34 | 38.56 | 61.97 | 46.75 |
| L | revised | 47.93 | 35.31 | 56.75 | 42.81 |
| G | original | 58.02 | 42.45 | 66.22 | 48.96 |
| G | revised | 47.23 | 34.55 | 53.91 | 39.86 |

The report also checks all four category-wise metrics and denominators,
valid empty submissions (9/17/16), and zero effect on all four metrics and
all category denominators for each of the eight complete published files.
Those historical control files retain their native `id`/`answers`
submissions; their original publisher extraction is not replaced with the
BAR response wrapper.

## Frozen semantics and boundaries

* **Tax:** the exact case-sensitive native regex selects the first owed/
  overpaid amount after removing `**`; overpayments are negative. The scalar
  acceptance calculation equals finite-scalar `numpy.isclose` with
  `rtol=1e-5`, `atol=1e-8`, with the reference as the second argument.
  All 300 IDs per model remain in the denominator. Only 27 reference pairs
  differ, limiting any fixed-output effect to 27/300. The archive retains
  model-assisted, unblinded trace annotations and exact response excerpts:
  48 gains explicitly state the floor, 13 gains show only a zero subtotal.
  The one loss is also in the latter category. These annotations are
  preserved human-readable evidence, not newly inferred semantic labels.
* **SARA:** the original parser deletes commas and periods and reads the
  first integer. The revised parser deletes commas and currency signs and
  reads the first signed decimal. Parsing-only retains the original
  `abs(p/(r+0.1)-1)<0.1` formula, including its zero-reference pathology.
  The final variant accepts exactly parsed zero for zero references. No
  later number or reference-aware extraction is substituted.
* **CQA:** the frozen BAR final-object parser and exact native-item shape
  validation are preserved. An explicit `answers: []` is a submission;
  a missing or invalid item is not. The original aggregation includes
  submitted IDs only; full coverage assigns missing IDs four zero scores.
  Answer normalization, token F1, exact condition-set F1, padding, four
  independently maximized alignments, and the exponential penalty using
  the full prediction length are retained. A small independent subset
  dynamic program computes the same maximum over injective alignments as
  the native permutations; it does not truncate extra predictions.
  The semantic label revision discussed elsewhere in the paper is not
  applied in this study.
* **OpenExempt:** all 69 federal-step cases, three models and three conditions
  are retained, including Luna's invalid JSON submission and Gemma's three
  new rejections. Acceptance requires a finite nonnegative numeric answer
  in an exact one-key JSON object, within $0.005 of the amended target.
  Decimal arithmetic independently recomputes each target from numerical
  asset values/categories under equal ownership and the added assumptions.
  The original study's released-ceiling optima are retained as sensitivity
  diagnostic inputs, not used as scoring targets. There are 20 positive
  and 49 zero targets, 65 changed tables, four unchanged-table controls,
  and 19 ceiling-sensitive cases. Native diagnostic overlap counts
  (36 second-claim cases, 19 sensitive; 14 terminal-conflict cases, 13
  sensitive) are retained and recounted, not reclassified as native errors.
  Overlapping groups must not be added as disjoint populations.

The basic CLI embeds independently written mathematical evaluators. It does
not claim to execute every upstream program. Per-case comparisons validate
these implementations against the frozen native scores, while input
verification and the optional native CQA checks provide separate checks.
The replay cannot reproduce a provider generation or turn scoped references
and experimental assumptions into a complete benchmark repair.

## Release validation

`studies/validation.json` records the tested script and archive hashes.
Validation copies the script, compressed assets, and required upstream files
to a fresh temporary directory. An audit hook rejects access to the private
project and network socket operations. Both the full input/native check and
a score-only Python `-S` run pass; the latter excludes installed site
packages and demonstrates the standard-library-only replay.

Separate checks compare all 900 Tax outputs against the frozen native parser
and real NumPy acceptance, and all 288 SARA outputs against the actual S0 and
S2 functions. CQA checks all submitted answer pairs and 3,050 literal native
permutation cases across study responses and published controls. Tests change
response text while updating its checksum, retain the old parsed submission
and scores, and require the replay to fail. Changed upstream files and
incorrect archive hashes also fail. These are offline verification steps;
they do not generate new performance responses.

## Archive contents and provenance

Each gzip-compressed tar contains `manifest.json`, `responses.json`,
`inputs.json`, and `expected.json`. Tax adds numerical `references.json`
and `attributions.json`; CQA adds `controls.json`; OpenExempt adds numerical
`targets.json` and `overlap.json`.

`responses.json` stores original visible text exactly as UTF-8, including
reasoning that was part of the visible response, plus parsed submissions,
invalid markers and scores. It excludes hidden/provider reasoning fields,
credentials, operational logs, and private review conversations.
`inputs.json` binds source IDs and exact model-visible input hashes.
Manifests contain the minimal BAR-authored reconstruction instructions,
source pins, request configurations, and historical authority paths/hashes.
The exporter verifies visible text against the delivered response receipt;
receipt hashes are retained without copying transport logs or provider metadata.
Historical paths are provenance labels only; the CLI never imports from
or requires those private paths.

BAR-original replay code uses MIT. Upstream materials remain subject to their
own terms; the study archive does not relicense them. The source map is a
local file and should not be included in a public release.
