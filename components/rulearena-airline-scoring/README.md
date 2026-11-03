# RuleArena Airline exact amount scoring

The native amount-scoring branch strips every period and allows a substring
match to the reference. For reference 1198, it rejects the exact response
`The total cost is $1,198.00` and accepts the wrong response
`The total cost is $11,980 USD`. These are constructed-response probes.

The BAR-original `evaluator.py` provides `parse_total(response)` and
`score_total(response, reference)`. It retains the first case-sensitive
`The total cost is` marker and native removal of Markdown bold markers.
It parses the complete terminal amount, validates US comma grouping, permits
an optional sign, one or two decimal places, optional `USD`, terminal period
and whitespace, then compares exact decimal values. Missing, malformed or
multiple final answers score false; no substring or rounding tolerance applies.
Invalid or nonfinite reference values raise `ValueError`.

This is a stricter terminal-format contract, not a universal semantic grader.
An earlier `The total cost is calculated below` phrase followed by a later
amount is rejected because the first marker is retained. These numerically
correct forms are also rejected: `The total cost is: $1,198.`,
`The total cost is $ 1,198.`, a closing quote or parenthesis, and a sentence
after the amount. The native scorer accepts these particular examples. The
checker records both scores; their rejection must not be interpreted as a
policy-reasoning error.

For standalone scoring, import these functions from this file.
`scripts/bar.py prepare rulearena-airline-scoring` writes the patched native
`airline/auto_test.py` and the helper `airline/bar_airline_scoring.py` to a new
directory. This is a source overlay; native model-running dependencies are not
bundled or executed by BAR. The offline checker executes the same patched
scoring branch with the installed helper and confirms that unrelated native
AST, including reference calculation and rule-attribution calls, is unchanged.
The native `--start_idx` log-reading path is also patched. It calls
`score_saved_log` on the original response and stored reference, ignoring the
old `GPT Predicted` value so that old parser errors are not retained.
Constructed native logs verify identical live and resumed scores for completed
responses. Upstream exception handling can still make a failed live run differ
from later rescoring of its saved response; that execution-failure path is
outside this amount-scoring repair.

The 1,200 format echoes of 300 native amounts and constructed controls are diagnostics, not model
performance results. Policy, case, reference amounts and the separate
rule-attribution metric are unchanged. The prompt-errata overlay also modifies
`auto_test.py`; do not combine them by overwriting files or bypassing source
hash checks. The objective dataset can be scored directly with these functions.
