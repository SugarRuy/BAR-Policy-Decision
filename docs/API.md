# BAR Python API

The `bar-policy-decision` package (import name `bar_policy`) loads BAR's
revised RuleArena Tax and Airline datasets, returns their exact model-visible
inputs separately from references and provenance, and exposes the existing
BAR and native scorers. It bundles BAR's own payloads only. Upstream
benchmark sources are supplied by you as local, pinned checkouts; nothing is
downloaded on import, load or scoring.

- [Installation](#installation)
- [Versions](#versions)
- [Upstream sources](#upstream-sources)
- [Datasets](#datasets)
- [Examples and model-visible input](#examples-and-model-visible-input)
- [Scoring](#scoring)
- [Components and low-level access](#components-and-low-level-access)
- [Capabilities](#capabilities)
- [Errors](#errors)
- [Command line](#command-line)
- [Running the tests](#running-the-tests)

## Installation

Python 3.11 or newer. From a checkout of this repository:

```bash
python3 -m pip install .            # core API, standard library only
python3 -m pip install ".[sara]"    # adds NumPy for SARA numeric scoring
```

The wheel contains the package code plus every file listed in
`inventory.json` (component payloads, manifests, component documentation and
scripts), the root license and all upstream license notices. It contains no
study archives, audit evidence, figures or upstream source files.

## Versions

BAR uses one version for the repository, Python package and current data:
**0.3.0**. `bar_policy.__version__`, `bar_policy.ASSET_RELEASE` and
`release_info()["version"]` all identify this release.

Component revision names (such as Tax `t1-t2-1`) and manifest hashes identify
particular materials within a release. Some components have no named revision;
their source pins and manifest hash identify them instead. These are provenance
identifiers, not separate package releases.

Report the BAR version and selected scorer with results. When explicitly
loading historical data, also report the selected historical release.

Every loader accepts `release=`. Only the releases in
`bar_policy.SUPPORTED_RELEASES` (`("0.2.0", "0.3.0")`) are accepted; anything else,
including `"latest"` or `"v0.2.0"`, raises `UnsupportedError`. There is no
remote resolution. `release_info()` returns the bundled `release.json`
(paper binding, component list and boundaries).

## Upstream sources

Pass the root of a local checkout (or a directory with the same relative
layout) as `source`. Every pinned file is hash-checked before it is parsed or
executed; a missing file raises `SourceNotFoundError`, a changed one
`SourceMismatchError`.

| Use | `source` | Pinned revision |
| --- | --- | --- |
| Tax and Airline datasets, NBA rows | RuleArena root | `SkyRiver-2000/RuleArena@59f60f6b4eb93a9b6d187ec781349d4f15618903` |
| ConditionalQA scoring | ConditionalQA root | `haitian-sun/ConditionalQA@77bd295952daf415548b3244db10880d3d55cfe0` |
| Optional LegalBench adapter | path to `evaluation.py` | `HazyResearch/legalbench@b46bf4ffae90524b2b72aaa30e7745fe9db64481` |

`get_component(id).source_pins()` lists each required path, official URL and
SHA-256. The [component guide](COMPONENTS.md) shows a fetch command that
downloads only these pinned files.

## Datasets

```python
import bar_policy as bar

tax = bar.load_dataset("rulearena-tax", "/data/RuleArena")
airline = bar.load_dataset("rulearena-airline", "/data/RuleArena")
```

`load_dataset(name, source, *, release="0.3.0", variant=None, mode=None, scorer=None)`.
The default variant is the final integrated revised configuration; users do
not combine components themselves. Release, variant and mode are validated
before any source is read.

| Dataset | Variant | Model-visible input | Reference | Scorer |
| --- | --- | --- | --- | --- |
| `rulearena-tax` | `revised` (default) | Native | T1+T2 (`0.3.0`: 43 of 300 differ from original); T1 only (`0.2.0`: 27 differ) | BAR numeric parser (native scorer optional) |
| `rulearena-tax` | `original` | Native | Original RuleArena reference | BAR numeric parser (native scorer optional) |
| `rulearena-airline` | `revised` (default) | Native + minimum-cost objective amendment; prompt errata applied | Native amounts (unchanged) | BAR exact amount scorer |
| `rulearena-airline` | `original-input` | Native, without the objective | Native amounts (unchanged) | BAR exact amount scorer |

Scorer selection is independent of reference selection. Tax accepts
`rulearena-tax-numeric-v1` (default) and `rulearena-tax-native`; Airline accepts
only `rulearena-airline-scoring`. `capabilities()["datasets"]` lists each
default and its supported scorers.

For Tax, `release="0.3.0"` selects `t1-t2-1`; `release="0.2.0"` selects
`line22-only-2`. There are 21 changes between them, including five cases
already affected by T1. New example references also expose `previous` and
`changed_from_previous`; metadata identifies `previous_revision` and
`resolved_dependencies`. `remaining_dependencies` retains T3. The 20 loss
cases follow the supplied formulas and therefore have negative self-employment
tax and deductions. See the [T2 revision record](../components/rulearena-tax/revisions/t1-t2-1/README.md).
Other component payloads are identical across the two releases.
BAR scores final Tax amounts. The upstream model-assisted `analyze_response`
is not exposed and retains its old stepwise threshold check.

Supported modes are `zero-shot` for Tax (native `distractor=False`,
`textual=False`, no example) and `markdown-zero-shot` for Airline. The Tax
modes `one-shot`, `textual` and `distractor` and the Airline modes
`markdown-one-shot`, `textual-zero-shot` and `textual-one-shot` raise
`UnsupportedError`: BAR does not build them and makes no correction claim for
them. The Airline prompt-errata patches for those modes remain available as
source overlays through `prepare_component`.

The integrated Airline configuration combines three components:

- `rulearena-airline-objective` adds the BAR objective amendment (identified
  in `dataset.info["amendments"]` and in each example's `amendments`).
- `rulearena-airline-prompt-errata` is applied in memory to the pinned
  sources and checked against its pinned result hashes. In Markdown zero-shot
  it changes nothing the model sees: the loader rebuilds all 300 inputs from
  the patched sources and requires them to be identical. The errata affect
  only the one-shot example and the textual policy.
- `rulearena-airline-scoring` is the scorer.

Per-case flags remain in `example.metadata`: `allocation_sensitive` (94
cases), `listed_order_reference` and the allocation minimum/maximum, and the
four unresolved `pe_dash_case` Premium Economy cases. All original source
identities and message hashes are retained. These revisions are scoped; they
are not a certification of complete ground truth. Amended inputs need new
predictions before any performance is reported.

`dataset.info` records the applied components with their manifest hashes and
revisions, amendments, scorer, flag counts, accepted scopes, remaining limits
and source pins. `len(dataset)`, iteration, `dataset[i]`, `dataset["tax/comp_0/0"]`
and `dataset.ids` are supported.

The other benchmarks have no dataset loader. `load_dataset` raises
`UnsupportedError` with a pointer for `rulearena-nba`, `conditionalqa`,
`legalbench-sara-numeric` and individual component IDs.

## Examples and model-visible input

```python
example = airline[0]
example.messages          # canonical [{"role": "system", ...}, {"role": "user", ...}]
example.model_input()     # {"messages": [...]} — everything a model may see
example.reference         # reference for this variant (not model-visible)
example.references        # {"original": ..., "revised": ..., "changed": ...}
example.metadata          # flags and remaining dependencies
example.source            # repository, revision, file, SHA-256, record index
example.source_record     # the complete raw native record (may contain annotations)
```

`messages` preserve the selected variant's exact system and user prompts, in
their original order and format, as built by the shared CLI implementation.
Use `messages` (or `model_input()`) for the canonical prompt. Role views below
also expose the text for methods that process policies, cases and task
directives separately. References, provenance and the raw record, which can
contain calculator annotations, are not model input.

The selected `reference`, example ID and dataset configuration are read-only.
Use an explicit variant to select different references, or pass an explicit
reference to a standalone scorer for a separate diagnostic.

`example.segments` decomposes each message into verbatim `Segment`s
(`message_index`, `roles`, `text`, `origin`, `provenance`, `note`). The
segments of a message concatenate exactly to its content. BAR does not
rewrite, reconstruct or synthetically split native text:

| Accessor | Tax | Airline |
| --- | --- | --- |
| `instructions` | Native system prompt and template text | Native system prompt and template text, plus the selected BAR objective |
| `policy` | One native segment with roles `("policy", "case")` | `airline/reference_rules.txt` |
| `case` | The same mixed segment | The native `prompt` field of the case record |
| `question` | Native task directives before and after the forms | Native system and template task directives, plus the selected BAR objective |
| `amendments` | Empty | Revised variant: the BAR objective text (`origin="bar"`) |

These are overlapping views, not disjoint prompt parts. In Tax, the pinned
native renderer fills case values into the policy forms, so `policy` and
`case` refer to the same segment. Do not concatenate the role views to
reconstruct a prompt: that would duplicate text and change its order. The
ordered `segments` preserve the full input, while `messages` provide it ready
to use.

`question` includes existing task directives even when the source has no
column named “question”. Airline's selected objective retains its
`amendment` role and `origin="bar"` while also appearing in `question`.
No question text is invented. A question view may be empty when policy or
case already states the task without a separate directive. Each upstream
segment's provenance names the repository, revision, file, SHA-256 and
template symbol or record index. Provenance mappings are read-only;
`to_dict()` returns a separately mutable, serializable copy.

`example.to_dict(include_source_record=False)` returns a JSON-ready record
with `input`, `reference(s)`, `metadata` and `source` kept apart.

## Scoring

Single responses:

```python
example.score("... The total cost is $1,166.")          # ItemScore
bar.score_tax_response("The total tax owed is $1,234.50.", 1234.5)
bar.score_airline_response("The total cost is $1,198.00", 1198)
```

`ItemScore` has `accepted`, `parsed` (`None` if no answer was found),
`reference` and `scorer`.

- **Tax** defaults to `rulearena-tax-numeric-v1`. It reads the complete amount
  in the native answer phrase, with or without correctly grouped commas:
  `$1234.50` and `$1,234.50` both parse as `1234.5`. Malformed grouping,
  such as `$1,23`, is rejected. Currency suffixes require a separator, as in
  `$1234 USD`. The native case-sensitive phrase, removal of
  `**`, negative sign for overpayment, and tolerance (`rtol=1e-5`, `atol=1e-8`,
  reference as second argument) are retained. The parser validates the amount
  immediately after the first native answer phrase. If that amount is
  malformed, the response is rejected even if a later phrase has a valid
  amount. It does not select the last conclusion. Tax scoring needs no NumPy.
- **Airline** uses the bundled `rulearena-airline-scoring` evaluator
  unchanged; see its [README](../components/rulearena-airline-scoring/README.md)
  for the exact terminal-format contract. References may be finite numeric
  amounts or numeric strings. The native substring scorer is not exposed.

The numeric parser is a post-publication API revision. To reproduce the
paper's Tax scores, select the unchanged native scorer explicitly:

```python
tax_native = bar.load_dataset(
    "rulearena-tax", "/data/RuleArena", release="0.2.0", scorer="rulearena-tax-native"
)
bar.score_tax_response(
    "The total tax owed is $1234.", 1234, scorer="rulearena-tax-native"
)  # parsed=123.0, accepted=False: an inherited native parsing defect
```

Reproducing the paper requires both the `0.2.0` reference release and native
scoring. Native mode calls `decode_tax` and `tax_accept` from
`scripts/reproduce_results.py` unchanged, including partial-number matching.
The published reproduction scripts and saved results retain this mode.

A whole dataset, with the full dataset as denominator:

```python
result = tax.score({"tax/comp_0/0": "...", ...})        # BatchScore
result.accepted, result.denominator, result.accuracy, result.missing, result.items
result.release, result.mode, result.variant, result.scorer
```

Responses are a mapping from example ID to text. An empty string is a
response. An absent ID raises `MissingResponsesError` unless
`allow_missing=True`, in which case it counts as not accepted, appears in
`result.missing` and has `items[id] is None`. Unknown IDs raise
`ResponseError`; non-string values raise `TypeError`.

SARA numeric is a batch scorer (mean over the population, `numpy.float64`),
with no per-item variant:

```python
bar.score_sara_numeric(generations, answers)
evaluation = bar.load_legalbench_evaluator("/data/legalbench/evaluation.py")
evaluation.evaluate("sara_numeric", generations, answers)
```

The adapter checks the file hash before executing it and replaces only
`evaluate_sara_numeric_acc` in memory; LegalBench's own dependencies are
needed for it. No SARA inputs or labels are bundled.

ConditionalQA is scored by the patched native `evaluate`, file or batch:

```python
bar.score_conditionalqa_file("predictions.json", source="/data/ConditionalQA")
bar.score_conditionalqa([{"id": "dev-0", "answers": []}, ...], source="/data/ConditionalQA")
```

The user's `evaluate.py` is hash-checked, `denominator.patch` is applied in
memory and the result is checked against its pinned hash before it runs; its
progress message is suppressed and file reads explicitly use UTF-8, matching
validation regardless of the system locale. All reference IDs stay in every denominator:
absent IDs score zero, `answers: []` is a valid submission, and categories
without references are `None`. Aggregation is the native one, not a mean of
per-example scores. The default references are the pinned `v1_0/dev.json`;
another `reference_file` requires `allow_unpinned_reference=True` and is
reported in `result.reference_pinned` and `result.reference_sha256`.

Before evaluation, the API validates both files as UTF-8 JSON without a byte
order mark. Each ID must be unique and
each prediction ID must occur in the selected references. `answers` must be
a list of `[answer_text, [condition_text, ...]]` pairs, with string text.
Malformed JSON, duplicate object keys, duplicate record IDs, unknown IDs and
invalid answer shapes raise `ResponseError`; invalid reference files raise
`ConfigurationError`. Additional native metadata fields are permitted.
No IDs or answers are silently rewritten.

`ConditionalQAResult` includes `denominator`, `submitted`, `missing` IDs,
`empty_answers` IDs and `prediction_sha256`. The file API hashes the exact
submitted bytes; the in-memory API hashes its generated UTF-8 JSON, which
can differ from an equivalent file's formatting. A completely empty prediction
list is valid: all reference cases remain in the denominator and score zero.
An explicit empty answer list is distinct and can receive credit for an
unanswerable case. Empty reference files are rejected.

These input checks (`input_validation="conditionalqa-input-v1"`) were added
during the public API review after publication; they are not additional
label-error findings from the paper. Valid submissions use the unchanged
full-denominator evaluator. The `prepare_component` CLI still produces the
frozen scorer patch; use the API for these additional validation checks.

Tax references must be finite `int` or `float` values (not booleans).
SARA references may be finite numeric values or numeric strings accepted by
its currency parser. Wrong scalar types, invalid numeric references, and
source or asset problems raise rather than count as model errors.

## Components and low-level access

```python
bar.list_components()                       # seven Component objects
c = bar.get_component("rulearena-tax")
c.manifest(); c.revision; c.manifest_sha256; c.source_pins(); c.patches()
c.read_bytes("components/rulearena-tax/labels.json")   # hash-checked payload
bar.load_references("rulearena-tax")       # bundled records, no source needed
bar.component_rows("rulearena-airline-objective", "/data/RuleArena")
bar.write_component_dataset("rulearena-tax", "/data/RuleArena", "/tmp/new-dir")
bar.prepare_component("rulearena-airline-scoring", "/data/RuleArena", "/tmp/new-dir")
bar.verify_assets()
```

`component_rows` returns, in memory, exactly the rows that
`scripts/bar.py dataset <component>` writes, for `rulearena-tax`,
`rulearena-airline-objective` and `rulearena-nba-location-errata`. These rows
include both original and revised fields and are intended for reproduction;
use `load_dataset` for model inputs. `write_component_dataset` and
`prepare_component` are the CLI `dataset` and `prepare` commands; they write a
new directory only, outside the source and package trees. `prepare_component`
needs the `patch` command for patch-based components.

RuleArena NBA has raw-record access only: `component_rows(
"rulearena-nba-location-errata", source)` returns all 216 original/revised
records with change flags, `load_references` returns the two guarded errata,
and `prepare_component` writes the two corrected JSON files. No NBA
policy-decision dataset with model-visible messages is implemented.

## Capabilities

`bar.capabilities()` returns this information in machine-readable form;
`Component.operations` lists one component's operations. Any other operation
raises `UnsupportedError`.

| Component | Operations | Dataset |
| --- | --- | --- |
| `rulearena-tax` | `load_references`, `component_rows`, `write_component_dataset`, `prepare_component` | `rulearena-tax` |
| `legalbench-sara-numeric` | `score_sara_numeric`, `load_legalbench_evaluator`, `prepare_component` | — |
| `conditionalqa-scoring` | `score_conditionalqa`, `score_conditionalqa_file`, `prepare_component` | — |
| `rulearena-airline-prompt-errata` | `prepare_component` | `rulearena-airline` |
| `rulearena-airline-objective` | `load_references`, `component_rows`, `write_component_dataset` | `rulearena-airline` |
| `rulearena-airline-scoring` | `score_airline_response`, `prepare_component` | `rulearena-airline` |
| `rulearena-nba-location-errata` | `load_references`, `component_rows`, `write_component_dataset`, `prepare_component` | — |

## Errors

All deliberate errors derive from `bar_policy.BARError` and from the matching
built-in exception.

| Exception | Also a | Raised for |
| --- | --- | --- |
| `ConfigurationError` | `ValueError` | Unknown dataset, component, variant or mode; bad argument; invalid or non-finite reference; unusable output directory |
| `UnsupportedError` | `ConfigurationError` | Unsupported release, mode, scorer or operation |
| `SourceNotFoundError` | `FileNotFoundError` | Missing source directory or pinned file |
| `SourceMismatchError` | `ValueError` | Source file or record differs from its pin (raised before any upstream code runs) |
| `AssetIntegrityError` | `ValueError` | Bundled BAR file missing or changed |
| `PatchError` | `ValueError` | A distributed patch does not produce its pinned result |
| `ResponseError` | `ValueError` | Unknown dataset response IDs; malformed ConditionalQA submissions, unknown or duplicate IDs |
| `MissingResponsesError` | `ResponseError` | Missing IDs in `Dataset.score` unless `allow_missing=True`; ConditionalQA always counts missing predictions as zero |
| `DependencyError` | `ImportError` | NumPy missing for SARA scoring |

Wrong response or scalar reference types, including non-string responses and
boolean or string Tax references, raise `TypeError`. Wrong types for dataset
selection options or scorer IDs raise `ConfigurationError`.

## Command line

`scripts/bar.py` (from a checkout) and the installed `bar-policy` command
share one implementation with the API and accept the same commands:
`list`, `verify`, `prepare <component> --source DIR --output NEW_DIR` and
`dataset <component> --source DIR --output NEW_DIR`. Each command accepts
`--release 0.2.0` or `--release 0.3.0` (the default); for example:

```bash
bar-policy dataset rulearena-tax --release 0.2.0 \
  --source /data/RuleArena --output /tmp/paper-tax-data
```

See the
[component guide](COMPONENTS.md).

## Running the tests

```bash
PYTHONPATH="$(pwd)/src" python3 -m unittest discover -s tests
```

Offline tests run without upstream sources. Source-dependent and parity tests
run when the environment variables documented in `tests/_support.py` point to
local pinned sources and reference outputs; `BAR_TEST_PACKAGING=1`
additionally builds the sdist and wheel and reruns the suite against the
installed wheel outside the source tree. No test calls a model or the network.

The pre-API CLI at `bca817a` has a stale `release.json` checksum in
`inventory.json`. For baseline parity tests, use a scratch copy with only
that inventory entry recalculated; leave the source commit and its payloads
unchanged. Current inventories already include that correction.
