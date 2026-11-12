# RuleArena Tax: T1 + T2 (`t1-t2-1`)

This revision keeps the line-22 zero floor (T1) and removes the reference
calculator's unsupported branch that sets self-employment tax and its
deduction to zero when adjusted earnings are below $400 (T2).
It recalculates all downstream fields using the supplied formulas.
The native policy, case, question, rounding rules and scorers are unchanged.

Compared with `line22-only-2`, **21 of 300 final amounts change and 279 do not**.
The changed IDs exactly match the earlier T2 flags. Five also have T1 changes;
the combined revision therefore differs from the original key in 43 cases.

The affected population contains 20 losses and one positive amount below $400.
Schedule SE line 4c preserves nonpositive earnings, and lines 10–13 continue
the arithmetic without an earnings floor. Consequently the 20 loss cases have
negative self-employment tax and deductions. No additional zero floor is
introduced. Downstream, other taxes become negative in 15 cases, total tax
becomes negative in five, and three final answers change from owed to refund.
This is consistency with the provided policy packet, not a
restoration of complete real-world tax rules.

T3, the zero default for unavailable Schedule 3 line 15, remains explicit.
The old references and published model results are unchanged. This release
adds no model runs or rescored model-performance claims.

The patch revises `compute_answer`. The upstream model-assisted
`analyze_response` still has its own `$400` check and is not a supported scorer
for the revised intermediate fields. BAR exposes final-amount scorers, which
retain their existing parsing and tolerance.

## Loading

```python
import bar_policy as bar

tax = bar.load_dataset("rulearena-tax", "/data/RuleArena", release="0.3.0")
paper_tax = bar.load_dataset(
    "rulearena-tax", "/data/RuleArena", release="0.2.0",
    scorer="rulearena-tax-native",
)
```

The new default is `0.3.0`. Select `variant="original"` to use the original key.
The old component files remain in `components/rulearena-tax/`; this directory
contains the additive revision. All versions use the same pinned upstream
commit, `59f60f6b4eb93a9b6d187ec781349d4f15618903`.

## Evidence and offline validation

- `labels.json` and `reference_pairs.jsonl`: all 300 original, T1 and T1+T2 amounts.
- `corrections.json`: the 21 changes relative to T1.
- `label_differences.jsonl`: all 300 differences, source hashes and SE quantities.
- `field_differences.jsonl`: the recomputed intermediate-field differences.
- `validation.json`: exact replays, independent Decimal SE arithmetic, unchanged
  inputs, unchanged unmarked intermediates, and sign/threshold/wage controls.
- `reference.patch`: the composed T1+T2 patch against the pinned original program.

The policy evidence is `tax/prompt.py`, `self_employ_forms`, Schedule SE
lines 4c and 8–13; the removed branch is in `tax/micro_evaluation.py`,
`compute_answer`. `component.json` supplies their immutable source pins.

From the repository root, with NumPy and Pydantic installed:

```bash
python3 scripts/check_tax_t2.py --source /data/RuleArena --output /tmp/bar-tax-t2-check
python3 scripts/bar.py prepare rulearena-tax --release 0.3.0 \
  --source /data/RuleArena --output /tmp/bar-tax-t2-code
```

Output directories must be new and outside the repository and upstream source.
Validation runs the pinned calculator functions, never its model entrypoints.
BAR code is MIT; the upstream MIT notice is retained in the parent component.
