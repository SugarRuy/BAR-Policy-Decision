# TheAgentCompany budget task: runtime evidence

The original task asks the agent to report equipment totals and budget
sufficiency to three managers. This audit sends manually constructed replies
to real private chats and calls the unmodified official evaluation entrypoint.
The fixed trajectory input contains a constructed directory marker; it is not
a recorded browser visit. No model generates any reply.

| Condition | Final replies | Checkpoints | Points | Converted score |
|---|---|---|---|---|
| A | Expected totals with consistent budget judgments | 1, 1, 2 | 4/4 | 1.00 |
| B | Same totals; judgments omitted | 1, 1, 2 | 4/4 | 1.00 |
| C | Same totals; all judgments reversed | 1, 1, 2 | 4/4 | 1.00 |
| D | A with only 11917 changed to 11918 | 1, 1, 0 | 2/4 | 0.25 |

Every condition restores the same initial database snapshot and uses the same
trajectory. Original chat reading, all checkpoints, the final-checkpoint bonus
and the official score conversion execute. The converted score is not the raw
point fraction. Because earlier checkpoints already pass, this comparison does
not separately measure the bonus's contribution.

The result establishes the tested scoring path's sensitivity to total strings
and its failure to enforce the requested budget judgments. The reference totals
come from the evaluator: the product prices and amount GT have not been
independently certified. No real-agent failure frequency follows.

## Records

- Each `A/` through `D/` directory contains the original sent/read messages,
  the official-helper readback, native evaluation result and converted score.
- `source-binding.json` pins task and scoring sources to
  `98b68ef82a47690c316f42fddb05baafaab56851`.
- `runtime-binding.json` verifies the mounted code against those sources.
- `images.json` records actual image digests and source-declared tags.
- `export-binding.json` binds these selected records to their original hashes.
  Authentication responses, database dumps and operational logs are omitted.

The upstream task/evaluator source is available at:
`https://github.com/TheAgentCompany/TheAgentCompany/tree/98b68ef82a47690c316f42fddb05baafaab56851/workspaces/tasks/admin-check-employees-budget-and-reply`.
The original runner enters through `workspaces/base_image/eval.py`; final score
conversion uses `evaluation/summarise_results.py` at that same revision.

The prior task/grader mismatch was reported in
[upstream PR #888](https://github.com/TheAgentCompany/TheAgentCompany/pull/888),
which amended the task wording without adding a budget-judgment check.
This release supplies runtime evidence, not a repaired budget evaluator.

Run `python3 scripts/check_audit_records.py` from the repository root to verify
the exported records' content, controls and conversions. That command checks
saved observations; it does not start the service environment or repeat this
runtime experiment.
