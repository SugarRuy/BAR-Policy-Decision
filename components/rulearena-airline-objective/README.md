# RuleArena Airline minimum-cost objective

Use `scripts/bar.py dataset rulearena-airline-objective` to build all 300
source-bound rows from the pinned RuleArena checkout. This component implements
Markdown zero-shot only. It inserts `objective.txt` after the native case text;
the policy, system prompt, case facts and original response-format instruction
remain unchanged.

`references.jsonl` records original and amended message hashes and retains the
same 300 native reference amounts. Native rows contain no stored answer column:
these amounts are computed by the frozen author calculator. The independent
policy calculation checks those minima under the stated native workload.
Output rows contain both original and amended messages, the original case,
unchanged amounts, and the two diagnostic flags:

- `allocation_sensitive`: 94 cases admit different allocation totals; 74
  listed-order totals are above the minimum. These are not error or gain counts.
- `pe_dash_case`: four Premium Economy cases depend on interpreting the policy
  table dash via the general complimentary entitlement. These are retained and
  flagged, and are disjoint from the 94 allocation-sensitive cases.

The target is ticket plus baggage charges for the described journey and inventory,
minimized only over allowed fee-position assignments. The supplied passenger and
item facts are fixed. Reference calculations inherit the native item
classification and fee model; no missing membership, special-service or other
entitlement facts are silently asserted.

This input amendment requires new predictions before reporting performance.
Existing scores and model outputs do not become amended-input results. Numeric
references alone do not certify every policy interpretation. The separate
`rulearena-airline-scoring` component fixes the native amount scorer; identify it
explicitly when used with these inputs.

Prior identification of the allocation ambiguity belongs to Nair et al. (cited
in the paper) and [RuleArena issue 5](https://github.com/SkyRiver-2000/RuleArena/issues/5).
The saved issue reports 93 cases; the 94 count here comes from full subset
enumeration and an independent cardinality dynamic program. The issue does not
provide a complete ID list that would resolve the one-case discrepancy.
