# Seven scoped BAR components

The update contains the seven revisions below. Original labels, policies,
case text and saved model outputs are not overwritten. These revisions do not
certify complete benchmark correctness. The four saved-response studies are
documented separately and are not part of this component inventory.

| Component ID | Delivered material | Accepted scope |
| --- | --- | --- |
| `rulearena-tax` | MIT native patch, 300 three-way references, unchanged native-input builder | T1 line-22 floor plus T2 supplied-policy calculation: 21 changes beyond T1, 43 from the original key. T3's zero default remains. |
| `legalbench-sara-numeric` | BAR-original MIT numeric evaluator, in-memory adapter, synthetic conformance vectors | Signed decimal parsing and zero-reference handling; original reference labels retained. The 100 label echoes comprise 4 train and 96 test rows; performance scope is the 96 test rows. |
| `conditionalqa-scoring` | BSD-2-Clause evaluator patch and upstream notice | All reference IDs remain in denominators; absent predictions contribute zero; empty categories return JSON `null`. Per-item answer and condition metrics remain native. |
| `rulearena-airline-prompt-errata` | Two native prompt patches | Example attribution and textual-policy transcription; 900/1,200 prompt variants change, amounts do not. |
| `rulearena-airline-objective` | Objective text, 300 reference/hash records and input builder | Explicit minimum-cost objective in Markdown zero-shot inputs; 94 allocation-sensitive cases, four separately flagged PE cases; no amount changes. |
| `rulearena-airline-scoring` | Native scoring patch and BAR-original decimal helper | Exact terminal-amount comparison, with native first-marker selection; no substring acceptance. |
| `rulearena-nba-location-errata` | Two native JSON patches, guarded errata and 216-record builder | Two localization fields only; binary verdicts and other labels unchanged. |

The [Python API](API.md) provides the same operations from Python and loads
the Tax and Airline revisions as integrated datasets; `scripts/bar.py` and the
API share one implementation.

The manifests selected by `components.json` bind the exact upstream revision and
SHA-256 of all source inputs, patches and prepared programs. Preparation rejects
wrong source versions, changed payloads, wrong result hashes, existing output
directories and output paths inside source or artifact trees.

## Requirements and source acquisition

Use Python 3.11 or newer and the `patch` command. The checked environment uses
Python 3.12.3, NumPy 2.3.5 and Pydantic 2.13.1. Airline calculator replay
additionally uses pandas. Full LegalBench adapter verification
also uses scikit-learn 1.8.0 and NLTK 3.9.4. No NLTK data download is needed.
The standalone SARA numeric function needs only NumPy; the CQA scorer needs
only the Python standard library. No model SDKs, credentials or model calls
are required.

```bash
python3 -m venv /tmp/bar-env
/tmp/bar-env/bin/pip install numpy==2.3.5 pydantic==2.13.1 scikit-learn==1.8.0 nltk==3.9.4 pandas==2.3.3
python3 scripts/bar.py list
python3 scripts/bar.py verify
/tmp/bar-env/bin/python scripts/check_components.py \
  --sources /tmp/bar-pinned-sources --fetch-sources \
  --output /tmp/bar-components-check.json
```

The optional fetch flag downloads only required files directly from fixed
official repository revisions, verifies every SHA-256 before saving, and never
downloads from a project-private cache. Use a fresh output filename per run.
After acquisition, repeat without `--fetch-sources` for an offline check:

```bash
/tmp/bar-env/bin/python scripts/check_components.py \
  --sources /tmp/bar-pinned-sources --output /tmp/bar-components-offline.json
```

Users who already hold the pinned source repositories can arrange or symlink
their repository roots to this layout:

| Directory under `--sources` | Exact source |
| --- | --- |
| `rulearena-tax-code` | `SkyRiver-2000/RuleArena@59f60f6b4eb93a9b6d187ec781349d4f15618903` |
| `legalbench-sara-numeric-code` | `HazyResearch/legalbench@b46bf4ffae90524b2b72aaa30e7745fe9db64481` |
| `legalbench-sara-numeric-data` | `nguha/legalbench@daec8237410aa23e3faf4bc41ad8b3a7e1696826` on Hugging Face |
| `conditionalqa-scoring-code` | `haitian-sun/ConditionalQA@77bd295952daf415548b3244db10880d3d55cfe0` |
| `rulearena-airline-prompt-errata-code`, `rulearena-airline-objective-code`, `rulearena-airline-scoring-code`, `rulearena-nba-location-errata-code` | Each points to `SkyRiver-2000/RuleArena@59f60f6b4eb93a9b6d187ec781349d4f15618903`. All may reference the same complete pinned checkout. |

The manifests contain the exact official file URLs and expected hashes.
Data acquisition and use remain subject to upstream terms; no raw SARA or
ConditionalQA data are bundled.

## RuleArena Tax

```bash
python3 scripts/bar.py prepare rulearena-tax \
  --source /tmp/bar-pinned-sources/rulearena-tax-code --output /tmp/bar-tax-code
python3 scripts/bar.py dataset rulearena-tax \
  --source /tmp/bar-pinned-sources/rulearena-tax-code --output /tmp/bar-tax-data
```

Preparation writes the revised `tax/micro_evaluation.py`, license notice and a
hash receipt into a new directory. It does not run the upstream experiment
entrypoint. `labels.json` and `reference_pairs.jsonl` contain the same 300
source-bound records. In release `0.3.0`, `corrections.json` contains the 21
changes relative to T1; the final key differs from the original in 43 cases.
Positive signed answers mean amounts owed; negative answers mean refunds.
Original IDs and source indices are preserved.

The dataset builder joins those references to user-supplied native cases and
reconstructs the native zero-shot messages with `distractor=False` and
`textual=False`. Its `data.jsonl` retains `id`, `source_file`, `source_index`,
`case_sha256`, `native_case`, `messages`, `original_reference`,
`revised_reference`, `reference_changed` and `remaining_dependencies`.
It changes neither the native case nor policy/question/prompt text.
`dataset.json` records the source and output hashes and sign convention.
T3 denotes the preserved zero default for unavailable Schedule 3 line 15.
T2 is resolved by removing the calculator's unsupported `$400` branch and
recomputing downstream fields with the supplied formulas. This produces
negative self-employment tax and deductions in 20 loss cases; no additional
zero floor is introduced. Native `np.isclose` grading is unchanged.

The new rows also include `previous_reference`, `previous_revision`,
`reference_changed_from_previous` and `resolved_dependencies`.
All three reference sets, source-bound field differences and validation are
in the [T2 revision record](../components/rulearena-tax/revisions/t1-t2-1/README.md).
Use `--release 0.2.0` on `prepare` or `dataset` to retain the original T1-only
patch and its 27 changes. The same version selector is available in the API.

```bash
python3 scripts/check_tax_t2.py \
  --source /tmp/bar-pinned-sources/rulearena-tax-code --output /tmp/bar-tax-t2-check
```

This independently checks SE arithmetic, all 300 calculator replays, preserved
inputs and unmarked intermediates, the T1 floor, the T3 default and 18 boundary
controls. It requires NumPy and Pydantic, and makes no network or model calls.
The patch revises `compute_answer`; the upstream model-assisted
`analyze_response` retains its old stepwise checks and is not supported for
scoring the revised intermediates. Use BAR's final-amount scorers.

## LegalBench SARA numeric

```bash
python3 scripts/bar.py prepare legalbench-sara-numeric \
  --source /tmp/bar-pinned-sources/legalbench-sara-numeric-code \
  --output /tmp/bar-sara-code
```

This produces a small BAR-original `evaluation.py`, not a modified copy of the
full upstream module. For the standalone function:

```python
import importlib.util
spec = importlib.util.spec_from_file_location("bar_sara", "/tmp/bar-sara-code/evaluation.py")
bar_sara = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bar_sara)
score = bar_sara.evaluate_sara_numeric_acc(["$1,234.00", "0"], ["$1234", "$0"])
```

For the original LegalBench dispatch and other public APIs, bind your pinned
upstream source in memory:

```python
evaluation = bar_sara.load_upstream_evaluator(
    "/tmp/bar-pinned-sources/legalbench-sara-numeric-code/evaluation.py"
)
score = evaluation.evaluate("sara_numeric", ["$1,234.00"], ["$1234"])
```

The adapter verifies the upstream file before loading it, replaces only
`evaluate_sara_numeric_acc` in memory, and leaves other functions and dispatch
behavior unchanged. Upstream dependencies are needed for this adapter. No
upstream source or bytecode is written by the adapter.

The parser removes `$` and commas and reads the first signed decimal amount
with a digit before the decimal point.
The first-number convention, including a line-leading minus, is intentional.
For nonzero references the exact native binary-float expression is retained:
`abs(float(prediction) / (float(reference) + 0.1) - 1) < 0.1`.
A zero reference requires a parsed exact zero. Missing/unparseable outputs
receive zero credit; empty populations and unequal lengths raise `ValueError`.
The return type remains `numpy.float64`.
Unicode minus, scientific notation, non-US separators and unrestricted prose
are outside the accepted parser contract. No claim is made that SARA tax
labels or omitted source context have been repaired.

The conformance fixture records scores from the accepted frozen corrected
scorer (`928d66dd…e7e4c0b`), synthetic inputs, and IDs/echo counts; it contains
no LegalBench source context or native reference labels.

## ConditionalQA

```bash
python3 scripts/bar.py prepare conditionalqa-scoring \
  --source /tmp/bar-pinned-sources/conditionalqa-scoring-code \
  --output /tmp/bar-cqa-code
python3 /tmp/bar-cqa-code/evaluate.py \
  --pred_file=/path/to/predictions.json \
  --ref_file=/tmp/bar-pinned-sources/conditionalqa-scoring-code/v1_0/dev.json
```

The API remains `evaluate(prediction_filename, reference_filename)`. All four
metrics (`EM`, `EM_with_conditions`, `F1`, `F1_with_conditions`) and all four
categories (`total`, `yesno`, `extractive`, `conditional`) are retained.
An explicit `answers: []` is a valid prediction for an unanswerable question;
an absent ID receives zero. Duplicate-ID and malformed-answer handling retain
upstream behavior and are outside this repair.

## Added Airline and NBA components

Use the same pinned RuleArena checkout with each command, and a different fresh
output directory each time:

```bash
python3 scripts/bar.py prepare rulearena-airline-prompt-errata \
  --source /path/to/pinned/RuleArena --output /tmp/airline-prompt-overlay
python3 scripts/bar.py dataset rulearena-airline-objective \
  --source /path/to/pinned/RuleArena --output /tmp/airline-objective-data
python3 scripts/bar.py prepare rulearena-airline-scoring \
  --source /path/to/pinned/RuleArena --output /tmp/airline-scoring-overlay
python3 scripts/bar.py prepare rulearena-nba-location-errata \
  --source /path/to/pinned/RuleArena --output /tmp/nba-location-overlay
python3 scripts/bar.py dataset rulearena-nba-location-errata \
  --source /path/to/pinned/RuleArena --output /tmp/nba-location-data
```

The objective builder returns original and amended messages, unchanged references,
source IDs/hashes and per-case ambiguity flags. It implements only Markdown
zero-shot and does not apply the other components; the Python API's
`rulearena-airline` dataset integrates all three Airline components. The two Airline code overlays
both modify `auto_test.py`; they must not be combined by overwriting one another.
For objective-data scoring, the standalone `parse_total` and `score_total`
functions in `components/rulearena-airline-scoring/evaluator.py` can be used
directly. The NBA builder returns all original/revised records and change flags.

Component READMEs give the exact parser contract, conditional reference
interpretations and residual issues. The new checks use constructed responses;
they make no claim about model gains or losses.

## Verification coverage

The portable checker executes the distributed outputs. It checks all 300 Tax
references, six floor boundaries, native inputs and grading preservation; 100
SARA echoes, 11 original format/zero controls, 54 nonzero tolerance controls,
the frozen conformance vectors and real upstream API adaptation; and all 285
CQA single-ID omissions against independent aggregation of native per-item
scores. CQA comparisons cover all four metrics and categories exactly, complete
and mixed submissions, fractional answer/condition F1, valid empty answers,
empty submissions and empty categories.

Deliberately wrong before/after hashes, reapplication and changed Tax prompt
inputs must fail. Every checked upstream file and packaged payload is verified
again after the run. Results include source hashes, IDs, counts, runtime versions
and `model_calls: 0`.

Additional checks replay all 300 Airline references against the native calculator
and independent policy arithmetic, enumerate 6,145 free-bag subsets with a second
dynamic-program check, compare all 1,200 prompt variants, and verify the exact
input amendment and its hash bindings. Airline scoring tests execute the patched
native branch plus its installed helper, with decimal, grouping, wrong-value,
multiple-answer and substring controls and 1,200 native amount echoes. Native log
replay uses the same parser and is checked against live scores for completed
responses, including old logs with incorrect stored parser values. Upstream
execution-failure handling is outside this repair. NBA checks
compare all 216 records, both native score witnesses, and unchanged binary labels.
Wrong-source tests must reject each new component before writing output.

The component inventory covers these seven revisions;
the study archives and complete release have separate inventories.
